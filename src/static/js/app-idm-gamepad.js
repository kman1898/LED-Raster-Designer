// app-idm-gamepad: a game controller on the IDM Locator tab. The crew
// pairs a PlayStation or Xbox pad with the computer (Bluetooth or a cable,
// no driver) and walks the wall with it: the D-pad steps the live highlight
// one module at a time, a press of A / Cross marks or clears the
// highlighted module, held while moving it paints. Which button does what
// is ONE table, idm-pad.js PAD_MAP, which the phone page (idm-phone.js)
// reads too; this file gives each job its code on the computer
// (_idmPadHost) and the panel's button list is built from the table.
//
// Moves, the next screen and the start of a highlight keep to the canvas
// the highlight is on (owner, 2026-11-17: the controls stay on the active
// canvas); only the next-canvas button takes it to another canvas. The
// keyboard's arrows keep to their canvas as they always did.
//
// Every move, mark, undo and field change goes through the very calls the
// keyboard and the pad in the panel use (app-idm-locator.js), so locked
// screens, undo and every other rule hold the same. The pad is read once a
// frame only while one is connected AND the tab is open, and acts only
// while this window has the focus: nothing runs when no pad is there.
//
// On the computer running the app, the controller is read natively
// instead when the app's controller reader has it
// (app-idm-native-pad.js): the same frame code runs on its states, with
// no focus needed, and the browser's reading of the pad steps aside.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import {
    PAD_BUTTONS, REPEAT_DELAY_MS, REPEAT_EVERY_MS, DEADZONE, FIELD_CYCLE,
    idmPadDirection, idmPadFrame, idmPadName, idmPadDispatch, idmPadFillHelp,
} from './idm-pad.js';
import {
    idmActiveCanvas, idmNextScreenFrom, idmNextCanvasFrom, idmCanvasList, idmTargetOf, idmCanvasIdOf,
} from './idm-core.js';

// The tests read these from here, as they always have.
export { PAD_BUTTONS, REPEAT_DELAY_MS, REPEAT_EVERY_MS, DEADZONE, idmPadDirection, idmPadFrame, idmPadName };

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
        // The button list, from the one table.
        idmPadFillHelp(document.querySelector('#idm-pad-help .idm-pad-help-map'));
        // The computer's own reader (app-idm-native-pad.js).
        if (typeof this._idmNativeWire === 'function') this._idmNativeWire();
        // A pad paired before the page loaded shows once it is used.
        this._idmPadSyncHelp();
    }

    _idmPadList() {
        // The native reader's controllers when it has any: never both
        const native = typeof this._idmNativePads === 'function' ? this._idmNativePads() : null;
        if (native && native.length) return native;
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
        // the native reader has it already and said so
        const quiet = typeof this._idmNativeNames === 'function' && this._idmNativeNames();
        if (quiet) {
            this._idmPadSyncHelp();
            return;
        }
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
        const quiet = typeof this._idmNativeNames === 'function' && this._idmNativeNames();
        if (!quiet) this._toast(`Controller disconnected: ${name}`);
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
        const native = typeof this._idmNativeNames === 'function' ? this._idmNativeNames() : null;
        const names = native || [...ps.known.values()];
        card.hidden = names.length === 0 && !ps.preview;
        const who = document.getElementById('idm-pad-help-name');
        if (who) who.textContent = names.length ? names.join(', ') : (ps.preview ? '(none connected)' : '');
        if (typeof this._idmNativeSyncPanel === 'function') this._idmNativeSyncPanel();
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
        // the server hears the tab open or close (app-idm-native-pad.js)
        if (typeof this._idmNativeWatch === 'function') this._idmNativeWatch(false);
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
            // the native reader's pad acts with the window behind another
            if (!focused && !pad.native) continue;
            for (const a of actions) this._idmPadAct(a);
        }
        return true;
    }

    _idmPadAct(a) {
        idmPadDispatch(this._idmPadHost(), a);
    }

    // Each job of the table (idm-pad.js PAD_ACTIONS) on the computer.
    _idmPadHost() {
        if (this._idmPadJobs) return this._idmPadJobs;
        this._idmPadJobs = {
            move: (dir, cabinet) => {
                this._idmStep(dir, cabinet || !!this._idmState().cabinetJump, { canvasId: this._idmPadCanvas() });
                this._idmPadKeepCanvas();
                this._idmPadPaintHere();
            },
            mark: {
                press: () => this._idmPadStartPaint(),
                release: () => this._idmPadEndPaint(),
            },
            undo: () => {
                if (this._idmState().stroke) return;      // not in the middle of a paint
                sendClientLog('idm_pad_undo', {});
                if (typeof this.undo === 'function') this.undo();
            },
            fieldColor: () => {
                const cur = this._idmFieldNow().color;
                const i = FIELD_CYCLE.indexOf(cur);
                this._idmSetField({ color: FIELD_CYCLE[(i + 1) % FIELD_CYCLE.length] });
            },
            nextScreen: () => this._idmNextScreen(),
            nextCanvas: () => this._idmNextCanvas(),
            clearHighlight: () => this._idmClearHighlight(),
        };
        return this._idmPadJobs;
    }

    // The canvas the controller is on: the highlight's, else the module
    // the mouse last left, else the one it was last on, else the show's
    // active canvas (idm-core idmActiveCanvas).
    _idmPadCanvas() {
        const r = window.canvasRenderer;
        const ps = this._idmPadState();
        const st = this._idmState();
        let remembered = ps.canvas;
        const left = st.hoverLast ? idmTargetOf(r, this.project, st.hoverLast) : null;
        if (left) remembered = idmCanvasIdOf(r, left.layer);
        return idmActiveCanvas(r, this.project, this._idmHl(), remembered);
    }

    _idmPadKeepCanvas() {
        const t = this._idmHighlightTarget();
        if (t) this._idmPadState().canvas = idmCanvasIdOf(window.canvasRenderer, t.layer);
    }

    // A / Cross down: the highlighted module marked or cleared - the click's
    // rules - and the paint begun; with no highlight, it starts one.
    _idmPadStartPaint() {
        const st = this._idmState();
        const t = this._idmHighlightTarget();
        if (!t) {
            if (!this._idmResumeHover()) this._idmStartHighlight({ canvasId: this._idmPadCanvas() });
            this._idmPadKeepCanvas();
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
    // ON THIS CANVAS (the Screens order), round to the first after the last.
    _idmNextScreen() {
        const r = window.canvasRenderer;
        const next = idmNextScreenFrom(r, this._idmHl(), this._idmPadCanvas());
        if (!next) return false;
        this._idmSetHighlight(next.layerId, next.key);
        this._idmPadKeepCanvas();
        return true;
    }

    // View / Share: the highlight to the first module of the next canvas
    // that has modules, round to the first; its name in a toast.
    _idmNextCanvas() {
        const r = window.canvasRenderer;
        const from = this._idmPadCanvas();
        const next = idmNextCanvasFrom(r, this.project, from);
        if (!next) {
            if (idmCanvasList(r, this.project).length < 2) this._toast('This show has one canvas with screens.');
            return false;
        }
        this._idmSetHighlight(next.layerId, next.key);
        this._idmPadState().canvas = next.canvasId;
        const c = idmCanvasList(r, this.project).find(x => x.id === next.canvasId);
        sendClientLog('idm_pad_canvas', { from, to: next.canvasId });
        this._toast(`Canvas: ${(c && c.name) || 'Canvas'}`);
        return true;
    }
}

for (const k of Object.getOwnPropertyNames(_IdmGamepad.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_IdmGamepad.prototype, k));
    }
}
