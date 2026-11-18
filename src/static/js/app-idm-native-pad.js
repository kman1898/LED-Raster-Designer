// app-idm-native-pad: the computer's own game controller on the IDM
// Locator tab, read natively (native_pad_reader.py, a process the app
// starts beside its server) rather than by the browser. Two things come of
// it that the browser's Gamepad API cannot give:
//
//   * a PlayStation touchpad: sliding a finger glides the highlight across
//     the wall like a mouse, module to module, at the speed set in the
//     panel (idmTouchGlide). Its click does nothing.
//   * the controller acts whenever this window has the IDM Locator tab
//     open, even with the Output to Display window or another app in front
//     (owner, 2026-11-17). On any other tab it does nothing.
//
// Only a designer page on the computer running the app hears of it, and
// only one at a time: the server sends the states to the host page that
// last opened the tab or took the focus with it open (native_pad.py
// NativePadBridge). A tablet or phone keeps the browser's Gamepad API.
//
// ONE map drives both: the native states come in the browser's standard
// layout and go through app-idm-gamepad.js's frame code (_idmPadTick,
// _idmPadAct, idm-pad.js's one button table) exactly as a browser pad
// does, a phone's too. While the native reader has a
// controller, the browser's own reading of it is set aside
// (_idmPadList), so a press never acts twice.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import { PAD_BUTTONS } from './idm-pad.js';

// The touchpad speed, 1 to 9, kept per viewer. At the middle setting a
// slide the whole width of the touchpad moves TOUCH_MODULES_MID modules;
// each setting up or down moves 1.4 times as far or less.
export const TOUCH_SPEED_KEY = 'lrdIdmTouchSpeed';
export const TOUCH_SPEED_DEFAULT = 5;
export const TOUCH_MODULES_MID = 16;
// One state never moves more than this many modules along an axis: a
// glitch never throws the highlight across the wall.
export const TOUCH_MAX_STEPS = 8;
// A held button is sent again 30 times a second; a state older than this
// is taken as let go (the reader went quiet, or another page took over).
export const NATIVE_STALE_MS = 400;

const BATTERY_WORDS = {
    empty: 'battery empty', low: 'battery low', medium: 'battery medium',
    full: 'battery full', max: 'battery full', wired: 'on a cable',
};

export function idmTouchSpeed(value) {
    const n = Math.round(Number(value));
    return Number.isFinite(n) && n >= 1 && n <= 9 ? n : TOUCH_SPEED_DEFAULT;
}

export function idmTouchModulesPerWidth(speed) {
    return TOUCH_MODULES_MID * Math.pow(1.4, idmTouchSpeed(speed) - TOUCH_SPEED_DEFAULT);
}

// A slide (dx, dy in touchpad widths) turned into module steps, with what
// is left over below one module (`rest`, [x, y]) carried to the next
// slide, the way a mouse keeps its fraction of a pixel. Returns {rest,
// steps}: steps are 'left' | 'right' | 'up' | 'down', across and down
// taken in turn so a slant walks as a slant. Pure, for the tests.
export function idmTouchGlide(rest, dx, dy, speed) {
    const k = idmTouchModulesPerWidth(speed);
    let fx = (rest ? Number(rest[0]) || 0 : 0) + (Number(dx) || 0) * k;
    let fy = (rest ? Number(rest[1]) || 0 : 0) + (Number(dy) || 0) * k;
    let nx = Math.trunc(fx), ny = Math.trunc(fy);
    fx -= nx;
    fy -= ny;
    nx = Math.max(-TOUCH_MAX_STEPS, Math.min(TOUCH_MAX_STEPS, nx));
    ny = Math.max(-TOUCH_MAX_STEPS, Math.min(TOUCH_MAX_STEPS, ny));
    const steps = [];
    const ax = Math.abs(nx), ay = Math.abs(ny);
    for (let i = 0; i < Math.max(ax, ay); i++) {
        if (i < ax) steps.push(nx > 0 ? 'right' : 'left');
        if (i < ay) steps.push(ny > 0 ? 'down' : 'up');
    }
    return { rest: [fx, fy], steps };
}

// The controller's name as the panel shows it: the name, then its battery
// when SDL gives one.
export function idmNativePadLabel(info) {
    const name = String((info && info.name) || 'Controller');
    const battery = BATTERY_WORDS[info && info.battery];
    return battery ? `${name}, ${battery}` : name;
}

const ZEROS = (n) => Array.from({ length: n }, () => 0);

class _IdmNativePad {
    _idmNativeState() {
        if (!this._idmNative) {
            let speed = TOUCH_SPEED_DEFAULT;
            try { speed = idmTouchSpeed(localStorage.getItem(TOUCH_SPEED_KEY)); } catch (_) { /* per viewer only */ }
            this._idmNative = {
                wired: false, host: false, status: null, pads: new Map(),
                rest: [0, 0], speed, sentIdm: null,
            };
        }
        return this._idmNative;
    }

    // Once, from _idmPadWire (app-idm-gamepad.js).
    _idmNativeWire() {
        const ns = this._idmNativeState();
        const s = this.socket;
        if (ns.wired || !s || typeof s.on !== 'function') return;
        ns.wired = true;
        s.on('native_pad_status', (data) => this._idmNativeStatus(data));
        s.on('native_pad_state', (data) => this._idmNativeInput(data));
        s.on('native_pad_idle', () => this._idmNativeIdle());
        // A reconnect is a new socket to the server: say again where we are.
        s.on('connect', () => this._idmNativeWatch(true));
        // Two designer windows on this computer, both on the tab: the one
        // last used gets the controller.
        window.addEventListener('focus', () => {
            if (this._idmState().active) this._idmNativeWatch(true);
        });
        const speed = document.getElementById('idm-pad-touch-speed');
        if (speed) {
            speed.value = String(ns.speed);
            speed.addEventListener('input', () => {
                ns.speed = idmTouchSpeed(speed.value);
                try { localStorage.setItem(TOUCH_SPEED_KEY, String(ns.speed)); } catch (_) { /* per viewer only */ }
            });
        }
        if (s.connected) this._idmNativeWatch(true);
    }

    // The server hears when this page's IDM Locator tab opens or closes
    // (_idmPadRun runs on both), and on a connect or a focus.
    _idmNativeWatch(force) {
        const ns = this._idmNativeState();
        const s = this.socket;
        if (!ns.wired || !s || typeof s.emit !== 'function') return;
        const idm = !!this._idmState().active;
        if (!force && ns.sentIdm === idm) return;
        ns.sentIdm = idm;
        s.emit('native_pad_watch', { idm });
    }

    // The reader's status: which controllers it has (the server sends it
    // to designer pages on this computer only). The page's first status
    // takes the controllers already there in silence: a load or a reload
    // is not a controller connecting. Only a change after that is toasted.
    _idmNativeStatus(data) {
        if (!data || typeof data !== 'object') return;
        const ns = this._idmNativeState();
        const ps = this._idmPadState();
        const quiet = !ns.host;
        ns.host = true;
        ns.status = data;
        const list = Array.isArray(data.pads) ? data.pads : [];
        const ids = new Set(list.map(p => String(p.id)));
        for (const [id, pad] of [...ns.pads]) {
            if (ids.has(id)) continue;
            ns.pads.delete(id);
            const key = 'native:' + id;
            ps.known.delete(key);
            const held = ps.pads.get(key);
            ps.pads.delete(key);
            if (held && held.buttons[PAD_BUTTONS.A]) this._idmPadEndPaint();
            this._toast(`Controller disconnected: ${pad.info.name || 'Controller'}`);
            sendClientLog('idm_native_pad_disconnected', { name: String(pad.info.name || '').slice(0, 80) });
        }
        const before = ns.pads.size;
        for (const p of list) {
            const id = String(p.id);
            const had = ns.pads.get(id);
            if (had) {
                had.info = p;
            } else {
                ns.pads.set(id, { info: p, buttons: ZEROS(17), axes: ZEROS(4), at: 0 });
                if (!quiet) {
                    this._toast(`Controller connected: ${idmNativePadLabel(p)}`);
                    sendClientLog('idm_native_pad_connected', { name: String(p.name || '').slice(0, 80), battery: p.battery || '' });
                }
            }
            ps.known.set('native:' + id, String(p.name || 'Controller'));
        }
        // The browser's reading of a pad steps aside while the reader has
        // one: what it held is forgotten, so nothing fires on the way back.
        if (!before && ns.pads.size) {
            for (const key of [...ps.pads.keys()]) if (!String(key).startsWith('native:')) ps.pads.delete(key);
        }
        this._idmPadSyncHelp();
        this._idmPadRun();
    }

    // One state of one controller: through the same frame code as a
    // browser pad, then the touchpad's slide.
    _idmNativeInput(data) {
        if (!data || typeof data !== 'object') return;
        const ns = this._idmNativeState();
        const pad = ns.pads.get(String(data.id));
        if (!pad) return;
        pad.buttons = Array.isArray(data.buttons) ? data.buttons.map(Number) : ZEROS(17);
        pad.axes = Array.isArray(data.axes) ? data.axes.map(Number) : ZEROS(4);
        pad.at = this._idmNativeNow();
        if (!this._idmState().active) return;
        // Run now, not at the next frame: a window behind another may get
        // no frames at all.
        if (typeof this._idmPadTick === 'function') this._idmPadTick(pad.at);
        const touch = Array.isArray(data.touch) ? data.touch : [0, 0];
        const dx = Number(touch[0]) || 0, dy = Number(touch[1]) || 0;
        if (!dx && !dy) return;
        const g = idmTouchGlide(ns.rest, dx, dy, ns.speed);
        ns.rest = g.rest;
        const cabinet = Number(pad.buttons[PAD_BUTTONS.LB]) > 0.5 || Number(pad.buttons[PAD_BUTTONS.RB]) > 0.5;
        for (const dir of g.steps) this._idmPadAct({ type: 'move', dir, cabinet });
    }

    // The controller went to another page: let go of what it held here.
    _idmNativeIdle() {
        const ns = this._idmNativeState();
        for (const pad of ns.pads.values()) pad.at = 0;
        ns.rest = [0, 0];
        if (this._idmState().active && typeof this._idmPadTick === 'function') this._idmPadTick();
    }

    _idmNativeNow() {
        return typeof performance !== 'undefined' ? performance.now() : Date.now();
    }

    // The native controllers as Gamepad-like objects for _idmPadList, or
    // null when the reader has none.
    _idmNativePads() {
        const ns = this._idmNative;
        if (!ns || !ns.pads.size) return null;
        const now = this._idmNativeNow();
        return [...ns.pads.entries()].map(([id, p]) => {
            const fresh = p.at > 0 && now - p.at < NATIVE_STALE_MS;
            return {
                index: 'native:' + id, id: String(p.info.name || 'Controller'),
                connected: true, mapping: 'standard', native: true,
                buttons: fresh ? p.buttons : ZEROS(17), axes: fresh ? p.axes : ZEROS(4),
            };
        });
    }

    // The panel's names for the native controllers, or null.
    _idmNativeNames() {
        const ns = this._idmNative;
        if (!ns || !ns.pads.size) return null;
        return [...ns.pads.values()].map(p => idmNativePadLabel(p.info));
    }

    // The controller lines in the panel (from _idmPadSyncHelp): the touchpad
    // and its speed, and whether the window must stay in front. With no
    // controller the panel says nothing about one (owner, 2026-11-17); the
    // reader's state goes to the app log only.
    _idmNativeSyncPanel() {
        const ns = this._idmNativeState();
        const ps = this._idmPadState();
        const native = ns.pads.size > 0;
        const touchpad = [...ns.pads.values()].some(p => p.info && p.info.touchpad);
        const touch = document.getElementById('idm-pad-touch');
        if (touch) touch.hidden = !(touchpad || ps.preview);
        const focus = document.getElementById('idm-pad-help-focus');
        if (focus) {
            focus.textContent = native
                ? 'Works while this tab is open, even with another window in front.'
                : 'Keep this window in front: the controller works only while the app has the focus.';
        }
    }
}

for (const k of Object.getOwnPropertyNames(_IdmNativePad.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_IdmNativePad.prototype, k));
    }
}
