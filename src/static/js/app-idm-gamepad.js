// app-idm-gamepad: a game controller on the IDM Locator tab. The crew
// pairs a PlayStation or Xbox pad with the computer (Bluetooth or a cable,
// no driver) and walks the wall with it: the D-pad steps the live highlight
// one module at a time, a press of A / Cross marks or clears the
// highlighted module, held while moving it paints. The browser's Gamepad
// API reads the pad in its "standard" layout, the same button numbers for
// both makes:
//
//   D-pad, left stick      move one module (held: a short wait, then a
//                          steady repeat); with LB / L1 or RB / R1 held,
//                          one cabinet (Cabinet jump)
//   A / Cross              mark or clear the highlighted module; held while
//                          moving, every module passed takes the first
//                          module's change (mark or clear, never both)
//   B / Circle             undo
//   X / Square             the next field color (White, Red, Green, Blue,
//                          Black)
//   Y / Triangle           the next screen
//   View / Share           clear the highlight
//
// Every move, mark, undo and field change goes through the very calls the
// keyboard and the pad in the panel use (app-idm-locator.js), so locked
// screens, undo and every other rule hold the same. The pad is read once a
// frame only while one is connected AND the tab is open, and acts only
// while this window has the focus: nothing runs when no pad is there.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The standard layout's button numbers.
export const PAD_BUTTONS = {
    A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, LT: 6, RT: 7, VIEW: 8, MENU: 9,
    LS: 10, RS: 11, UP: 12, DOWN: 13, LEFT: 14, RIGHT: 15, HOME: 16,
};
// A held direction: the first step at once, the next after REPEAT_DELAY_MS,
// then one every REPEAT_EVERY_MS. The stick counts past DEADZONE.
export const REPEAT_DELAY_MS = 350;
export const REPEAT_EVERY_MS = 90;
export const DEADZONE = 0.5;
// X / Square walks the field through the panel's quick colors.
const FIELD_CYCLE = ['#ffffff', '#ff0000', '#00ff00', '#0000ff', '#000000'];

function pressed(pad, i) {
    const b = pad && pad.buttons ? pad.buttons[i] : null;
    if (!b) return false;
    return typeof b === 'object' ? !!b.pressed || Number(b.value) > 0.5 : Number(b) > 0.5;
}

// The direction the pad holds: the D-pad first, then the left stick past
// the deadzone along its stronger axis. 'up' | 'down' | 'left' | 'right' |
// null.
export function idmPadDirection(pad) {
    if (!pad) return null;
    if (pressed(pad, PAD_BUTTONS.UP)) return 'up';
    if (pressed(pad, PAD_BUTTONS.DOWN)) return 'down';
    if (pressed(pad, PAD_BUTTONS.LEFT)) return 'left';
    if (pressed(pad, PAD_BUTTONS.RIGHT)) return 'right';
    const axes = pad.axes || [];
    const x = Number(axes[0]) || 0, y = Number(axes[1]) || 0;
    if (Math.max(Math.abs(x), Math.abs(y)) < DEADZONE) return null;
    if (Math.abs(x) >= Math.abs(y)) return x > 0 ? 'right' : 'left';
    return y > 0 ? 'down' : 'up';
}

// One frame of one pad: what it asks for, from what it held last frame
// (`prev`, {buttons: [bool], dir, nextAt} or null) and the time `now` in
// ms. Returns {state, actions}; each action is {type: 'move', dir, cabinet}
// or {type: 'press' | 'release', button}. Pure, so the repeat and the
// button edges are tested apart from the app.
export function idmPadFrame(prev, pad, now) {
    const was = prev || { buttons: [], dir: null, nextAt: 0 };
    const buttons = [];
    const n = Math.max((pad && pad.buttons ? pad.buttons.length : 0), was.buttons.length);
    for (let i = 0; i < n; i++) buttons.push(pressed(pad, i));
    const actions = [];
    // Presses and releases first, so A pressed with a move this frame marks
    // the module it started on, then paints the next.
    for (let i = 0; i < buttons.length; i++) {
        if (i >= PAD_BUTTONS.UP && i <= PAD_BUTTONS.RIGHT) continue;
        if (buttons[i] && !was.buttons[i]) actions.push({ type: 'press', button: i });
        else if (!buttons[i] && was.buttons[i]) actions.push({ type: 'release', button: i });
    }
    const dir = idmPadDirection(pad);
    const cabinet = buttons[PAD_BUTTONS.LB] || buttons[PAD_BUTTONS.RB];
    let nextAt = was.nextAt;
    if (dir && dir !== was.dir) {
        actions.push({ type: 'move', dir, cabinet });
        nextAt = now + REPEAT_DELAY_MS;
    } else if (dir && now >= was.nextAt) {
        actions.push({ type: 'move', dir, cabinet });
        // a late frame never fires a burst: the next step is a beat on
        nextAt = Math.max(was.nextAt + REPEAT_EVERY_MS, now + REPEAT_EVERY_MS / 2);
    }
    return { state: { buttons, dir, nextAt: dir ? nextAt : 0 }, actions };
}

// The pad's name without the browser's vendor and product tail.
export function idmPadName(id) {
    const text = String(id || '').trim();
    const cut = text.search(/\s*\((?:STANDARD GAMEPAD|Vendor|vendor)/);
    const name = (cut > 0 ? text.slice(0, cut) : text).trim();
    return name || 'Controller';
}

class _IdmGamepad {
    _idmPadState() {
        if (!this._idmPad) {
            this._idmPad = { wired: false, frame: 0, pads: new Map(), known: new Map() };
        }
        return this._idmPad;
    }

    // Once, from setupEventListeners (app-core), after _idmWire.
    _idmPadWire() {
        const ps = this._idmPadState();
        if (ps.wired || typeof window.addEventListener !== 'function') return;
        ps.wired = true;
        window.addEventListener('gamepadconnected', (e) => this._idmPadConnected(e && e.gamepad));
        window.addEventListener('gamepaddisconnected', (e) => this._idmPadDisconnected(e && e.gamepad));
        // A pad paired before the page loaded shows once it is used.
        this._idmPadSyncHelp();
    }

    _idmPadList() {
        let list = [];
        try {
            list = typeof navigator.getGamepads === 'function' ? Array.from(navigator.getGamepads() || []) : [];
        } catch (_) { list = []; }
        return list.filter(p => p && p.connected !== false);
    }

    _idmPadConnected(pad) {
        const ps = this._idmPadState();
        if (!pad) return;
        ps.known.set(pad.index, idmPadName(pad.id));
        const odd = pad.mapping !== 'standard';
        this._toast(`Controller connected: ${idmPadName(pad.id)}`
            + (odd ? '. Its buttons are not in the standard layout, so some may not match the list.' : ''));
        sendClientLog('idm_pad_connected', { id: String(pad.id || '').slice(0, 120), mapping: pad.mapping || '' });
        this._idmPadSyncHelp();
        this._idmPadRun();
    }

    _idmPadDisconnected(pad) {
        const ps = this._idmPadState();
        const index = pad ? pad.index : -1;
        const name = ps.known.get(index) || idmPadName(pad && pad.id);
        ps.known.delete(index);
        const held = ps.pads.get(index);
        ps.pads.delete(index);
        // a paint under way ends as one edit, the way a mouse let go does
        if (held && held.buttons[PAD_BUTTONS.A]) this._idmPadEndPaint();
        this._toast(`Controller disconnected: ${name}`);
        sendClientLog('idm_pad_disconnected', { index });
        this._idmPadSyncHelp();
        this._idmPadRun();
    }

    // The help card shows while a pad is connected (and while the guide
    // shows it, _idmPadPreviewHelp).
    _idmPadSyncHelp() {
        const ps = this._idmPadState();
        const card = document.getElementById('idm-pad-help');
        if (!card) return;
        const names = [...ps.known.values()];
        card.hidden = names.length === 0 && !ps.preview;
        const who = document.getElementById('idm-pad-help-name');
        if (who) who.textContent = names.length ? names.join(', ') : (ps.preview ? '(none connected)' : '');
    }

    // The guide's step shows the list with no controller there.
    _idmPadPreviewHelp(on) {
        this._idmPadState().preview = !!on;
        this._idmPadSyncHelp();
    }

    // The frame loop runs while a pad is connected and the tab is open;
    // otherwise it stops (and nothing reads the pad).
    _idmPadRun() {
        const ps = this._idmPadState();
        const st = typeof this._idmState === 'function' ? this._idmState() : null;
        const want = !!(st && st.active) && ps.known.size > 0;
        if (want && !ps.frame) {
            const tick = () => {
                ps.frame = 0;
                if (!this._idmPadTick()) return;
                ps.frame = requestAnimationFrame(tick);
            };
            ps.frame = requestAnimationFrame(tick);
        } else if (!want && ps.frame) {
            cancelAnimationFrame(ps.frame);
            ps.frame = 0;
        }
        if (!want) {
            if (ps.pads.size && [...ps.pads.values()].some(s => s.buttons[PAD_BUTTONS.A])) this._idmPadEndPaint();
            ps.pads.clear();
        }
    }

    // One frame: every connected pad read and acted on. False stops the
    // loop (no pad, or the tab closed).
    _idmPadTick(now = (typeof performance !== 'undefined' ? performance.now() : Date.now())) {
        const ps = this._idmPadState();
        const st = this._idmState();
        if (!st.active || !ps.known.size) return false;
        const focused = typeof document.hasFocus !== 'function' || document.hasFocus();
        for (const pad of this._idmPadList()) {
            if (!ps.known.has(pad.index)) ps.known.set(pad.index, idmPadName(pad.id));
            // Out of focus the pad is ignored: what it holds is taken as
            // where it starts when the window comes back, so nothing fires.
            const { state, actions } = idmPadFrame(ps.pads.get(pad.index), pad, now);
            ps.pads.set(pad.index, state);
            if (!focused) continue;
            for (const a of actions) this._idmPadAct(a);
        }
        return true;
    }

    _idmPadAct(a) {
        const B = PAD_BUTTONS;
        if (a.type === 'move') {
            this._idmStep(a.dir, a.cabinet || !!this._idmState().cabinetJump);
            this._idmPadPaintHere();
            return;
        }
        if (a.type === 'release') {
            if (a.button === B.A) this._idmPadEndPaint();
            return;
        }
        // presses
        const st = this._idmState();
        if (a.button === B.A) {
            this._idmPadStartPaint();
        } else if (a.button === B.B) {
            if (st.stroke) return;           // not in the middle of a paint
            sendClientLog('idm_pad_undo', {});
            if (typeof this.undo === 'function') this.undo();
        } else if (a.button === B.X) {
            const cur = this._idmFieldNow().color;
            const i = FIELD_CYCLE.indexOf(cur);
            this._idmSetField({ color: FIELD_CYCLE[(i + 1) % FIELD_CYCLE.length] });
        } else if (a.button === B.Y) {
            this._idmNextScreen();
        } else if (a.button === B.VIEW) {
            this._idmClearHighlight();
        }
    }

    // A / Cross down: the highlighted module marked or cleared - the click's
    // rules - and the paint begun; with no highlight, it starts one.
    _idmPadStartPaint() {
        const st = this._idmState();
        const t = this._idmHighlightTarget();
        if (!t) {
            this._idmStartHighlight();
            return;
        }
        if (this._layerLocked(t.layer)) {
            this._showLockedError([t.layer]);
            return;
        }
        const before = JSON.stringify(t.layer.idm || null);
        const block = this._idmEnsureBlock(t.layer);
        st.stroke = { layerId: t.layer.id, mode: block.marks[t.key] ? 'clear' : 'mark', touched: new Set(), before, pad: true };
        this._idmApply(t.layer, t.key);
        this._idmPadRender();
    }

    // A move with A / Cross held: the module reached takes the paint's
    // change (on the paint's own screen, the way a drag stays on its screen).
    _idmPadPaintHere() {
        const st = this._idmState();
        const stroke = st.stroke;
        if (!stroke || !stroke.pad) return;
        const t = this._idmHighlightTarget();
        if (!t || t.layer.id !== stroke.layerId || stroke.touched.has(t.key)) return;
        this._idmApply(t.layer, t.key);
        this._idmPadRender();
    }

    // A / Cross up: the paint is one edit, one undo step.
    _idmPadEndPaint() {
        const st = this._idmState();
        if (!st.stroke || !st.stroke.pad) return;
        this._idmPointerUp();
        this._idmPadRender();
    }

    _idmPadRender() {
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Y / Triangle: the highlight to the first module of the next screen
    // (the Screens order), round to the first after the last.
    _idmNextScreen() {
        const r = window.canvasRenderer;
        if (!r || typeof r.idmModuleRects !== 'function') return false;
        const mods = r.idmModuleRects();
        if (!mods.length) return false;
        const order = [];
        mods.forEach(m => { if (!order.includes(m.layer)) order.push(m.layer); });
        const hl = this._idmHl();
        const at = hl ? order.findIndex(l => l.id === hl.layerId) : -1;
        const next = order[(at + 1) % order.length];
        const own = mods.filter(m => m.layer === next);
        const first = own.reduce((a, m) => ((m.y < a.y - 0.5 || (Math.abs(m.y - a.y) <= 0.5 && m.x < a.x)) ? m : a));
        this._idmSetHighlight(next.id, first.key);
        return true;
    }
}

for (const k of Object.getOwnPropertyNames(_IdmGamepad.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_IdmGamepad.prototype, k));
    }
}
