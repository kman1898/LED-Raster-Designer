// app-stage3d-panel: the 3D Placement panel's figures, and the corner
// picker in the view (owner, 2026-11-10: "we need these to be like real 3D
// software not just text boxes").
//
// THE FIGURES. Position (X, Y, Z) and Rotation (pitch, yaw, roll) sit on
// one row each, three compact fields, each with its axis tag colored as the
// view's move arrows and rings are (X and pitch red, Y and yaw green, Z and
// roll blue). Each field works the way fields in 3D software do:
//   press and drag sideways   changes the figure (the cursor says so), the
//                             view following live; Shift for fine steps,
//                             Ctrl (Cmd on a Mac) snaps to 1 in or 1 cm, or
//                             15 degrees. The whole drag is ONE undo step;
//                             Esc during it puts everything back.
//   press, drag down, then    gathers the next fields of the row (a field
//   sideways                  height of travel each, up gathers the ones
//                             before), and the sideways drag moves them all
//                             by the same amount, one undo step
//   < > on hover              step the figure by 1 in, 1 cm or 1 degree
//   click without dragging    puts the caret where you clicked, to type;
//                             a double-click selects the whole figure
//   typing                    Math OK (16.4+2), *2 and /2 scale the figure,
//                             and a length takes its own unit: 6' 6", 6ft
//                             6in, 2m, 250mm, whatever the ft | m switch
//                             says. A figure that is not one goes back, and
//                             a short note under the row says so
//   Enter / Esc               keeps it and lets go / puts it back
//   Tab / Shift+Tab           X, Y, Z, Pitch, Yaw, Roll and back
//   Up / Down                 nudge 1 in, 1 cm or 1 degree (Shift a tenth,
//                             Ctrl / Cmd a snap step); the run of nudges is
//                             one undo step, saved when the field lets go
//   the wheel                 does nothing (too easy to do by accident)
//   right-click               Reset, Copy value, Paste value, Copy all
//                             three, Paste all three; Pitch, Yaw and Roll
//                             also +90 and -90
// Each section has a reset icon: Position goes back to the Show Look place,
// Rotation to upright and facing the audience.
//
// THE CURVE is the Header/Footer tab's (the owner's calculator): shown here
// as it stands, read-only, with a link to its settings. CORNERS are 90
// degrees only, Interior or Exterior: a click on a seam, or on a panel's
// middle, of the selected screen opens a small picker beside the cursor,
// None / Interior 90 / Exterior 90, written through app-corners.js
// setRiggingCornerAt, the same riggingCorners the Header/Footer tab
// writes, so the two tabs always agree.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import {
    DEG, round, wrap180, s3dCornersOn, s3dCornerSeams, s3dCurveOn, s3dParseLength, s3dStoredFrom,
} from './app-stage3d.js';
import { cornerSpotLabel } from './app-corners.js';

const LENGTH_KEYS = ['x', 'y', 'z'];
const ANGLE_KEYS = ['pitch', 'yaw', 'roll'];
const KEYS = LENGTH_KEYS.concat(ANGLE_KEYS);
const DRAG_PX = 3;               // a press that travels this far sideways is a drag
const GATHER_PX = 8;             // ...or this far down (or up) first gathers fields
const GATHER_STEP = 22;          // px of downward travel per field gathered
// A drag's step per page pixel, and the snap and nudge steps, in mm or
// degrees: feet move an inch a pixel, meters a centimeter.
const PX_STEP = { ft: 25.4, m: 10, deg: 0.5 };
const SNAP = { ft: 25.4, m: 10, deg: 15 };
const NUDGE = { ft: 25.4, m: 10, deg: 1 };
const FINE = 0.1;
const NOTE_MS = 3500;

const isLength = (key) => LENGTH_KEYS.includes(key);

// A typed sum as a number, or null when it is not one: only figures, + - *
// / and brackets, at least one figure, and a finite answer ("abc" and "2+"
// are not figures; the app's lenient evaluator would read them as 0).
function strictMath(text) {
    const t = String(text == null ? '' : text).trim();
    if (!t || !/\d/.test(t) || !/^[\d\s.+\-*/()]+$/.test(t)) return null;
    try {
        const v = new Function(`return (${t});`)();
        return typeof v === 'number' && Number.isFinite(v) ? v : null;
    } catch (e) {
        return null;
    }
}
const rowOf = (key) => (isLength(key) ? LENGTH_KEYS : ANGLE_KEYS);

class _Stage3DPanel {
    // ── wiring ────────────────────────────────────────────────────────────

    _s3dWirePanel() {
        document.querySelectorAll('#s3d-fields [data-s3d-key]').forEach(input => {
            const key = input.dataset.s3dKey;
            const field = input.closest('.s3d-field') || input;
            field.addEventListener('mousedown', (ev) => {
                if (ev.button === 0 && document.activeElement !== input) ev.preventDefault();
            });
            field.addEventListener('pointerdown', (ev) => this._s3dFieldPress(input, field, ev));
            field.addEventListener('pointermove', (ev) => this._s3dFieldMove(ev));
            field.addEventListener('pointerup', (ev) => this._s3dFieldRelease(ev, false));
            field.addEventListener('pointercancel', (ev) => this._s3dFieldRelease(ev, true));
            field.addEventListener('lostpointercapture', (ev) => this._s3dFieldRelease(ev, true));
            field.addEventListener('contextmenu', (ev) => this._s3dFieldMenu(key, ev));
            input.addEventListener('keydown', (ev) => this._s3dFieldKey(input, ev));
            input.addEventListener('change', () => this._s3dFieldFinish(input));
            input.addEventListener('blur', () => this._s3dFieldFinish(input));
            input.addEventListener('dblclick', () => input.select());
            field.querySelectorAll('[data-s3d-nudge]').forEach(btn => {
                const stop = (ev) => { ev.preventDefault(); ev.stopPropagation(); };
                btn.addEventListener('pointerdown', stop);
                btn.addEventListener('mousedown', stop);
                btn.addEventListener('click', (ev) => {
                    stop(ev);
                    this._s3dFieldStep(key, Number(btn.dataset.s3dNudge), ev.shiftKey);
                });
            });
        });
        const on = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        on('s3d-reset-position', () => this._s3dResetPosition());
        on('s3d-reset-rotation', () => this._s3dResetRotation());
        on('s3d-curve-edit', () => this._s3dOpenCurve());
        // Where the pointer last was over the view: G and R start there.
        const view = document.getElementById('s3d-view');
        if (view) {
            view.addEventListener('pointermove', (ev) => {
                this._s3dState().pointer = { x: ev.clientX, y: ev.clientY };
            });
        }
        document.querySelectorAll('#s3d-corner-pop [data-s3d-corner]').forEach(btn => {
            btn.addEventListener('click', () => this._s3dCornerChoose(btn.dataset.s3dCorner));
        });
    }

    // ── what a field shows ────────────────────────────────────────────────

    _s3dFieldUnit(key) {
        return isLength(key) ? this._s3dUnits() : 'deg';
    }

    _s3dFieldText(key, value) {
        return isLength(key) ? this._s3dFormatLength(value) : String(round(wrap180(Number(value) || 0), 2));
    }

    // A typed figure in mm or degrees, or null. A leading * or / scales the
    // figure the field holds (`current`): *2 doubles it, /2 halves it.
    _s3dFieldParse(key, text, current = null) {
        const t = String(text == null ? '' : text).trim();
        const scale = t.match(/^([*/])\s*(.+)$/);
        if (scale) {
            if (current === null || !Number.isFinite(current)) return null;
            const k = strictMath(scale[2]);
            if (k === null || (scale[1] === '/' && k === 0)) return null;
            return scale[1] === '*' ? current * k : current / k;
        }
        if (isLength(key)) return s3dParseLength(t, this._s3dUnits(), strictMath);
        return strictMath(t.replace(/°/g, ''));
    }

    // The screen's figure as the panel shows it (X, Y and Z at the datum).
    _s3dFieldModel(layer, key) {
        return this._s3dShownOf(layer, this._s3dPlacementOf(layer))[key];
    }

    // The six figures written into their fields: the one being typed in or
    // dragged keeps its own (`force` rewrites it too).
    _s3dPanelFigures(shown, force = false) {
        const st = this._s3dState();
        const dragging = st.field && st.field.moved ? st.field.keys : [];
        for (const key of KEYS) {
            const el = document.getElementById(`s3d-${key}`);
            if (!el) continue;
            const text = this._s3dFieldText(key, shown[key]);
            if (!force && (document.activeElement === el || dragging.includes(key))) continue;
            if (el.value !== text) el.value = text;
            el.dataset.text = text;
            delete el.dataset.pending;
        }
    }

    // A short note under the field's row, gone after a moment.
    _s3dFieldNote(key, text) {
        const el = document.querySelector(`[data-s3d-note="${isLength(key) ? 'position' : 'rotation'}"]`);
        if (!el) return;
        const st = this._s3dState();
        el.textContent = text || '';
        el.hidden = !text;
        clearTimeout(st.noteTimer);
        if (text) st.noteTimer = setTimeout(() => { el.hidden = true; el.textContent = ''; }, NOTE_MS);
    }

    // ── press and drag ────────────────────────────────────────────────────

    _s3dFieldPress(input, field, ev) {
        if (ev.button !== 0 || document.activeElement === input) return;
        if (ev.target && ev.target.closest && ev.target.closest('[data-s3d-nudge]')) return;
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        ev.preventDefault();
        const st = this._s3dState();
        const key = input.dataset.s3dKey;
        st.field = {
            key, keys: [key], input, field, layerId: layer.id, pointerId: ev.pointerId,
            x0: ev.clientX, y0: ev.clientY, lastX: ev.clientX, moved: false, gather: false, refused: false,
            starts: { [key]: this._s3dFieldModel(layer, key) }, raw: 0, values: null,
        };
        try { field.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
    }

    // The fields a gather has crossed: from the pressed one, one more per
    // field height of travel down (or up, the ones before it), in its row.
    _s3dGatherKeys(f, dy) {
        const row = rowOf(f.key);
        const i0 = row.indexOf(f.key);
        const n = Math.trunc(dy / GATHER_STEP + (dy >= 0 ? 0.5 : -0.5));
        const i1 = Math.max(0, Math.min(row.length - 1, i0 + n));
        return row.slice(Math.min(i0, i1), Math.max(i0, i1) + 1);
    }

    _s3dGatherShow(keys) {
        KEYS.forEach(k => {
            const el = document.getElementById(`s3d-${k}`);
            const f = el && el.closest('.s3d-field');
            if (f) f.classList.toggle('s3d-gathered', !!keys && keys.length > 1 && keys.includes(k));
        });
    }

    _s3dFieldMove(ev) {
        const st = this._s3dState();
        const f = st.field;
        if (!f || ev.pointerId !== f.pointerId || f.refused) return;
        const dx = ev.clientX - f.x0, dy = ev.clientY - f.y0;
        if (!f.moved) {
            if (!f.gather && Math.abs(dy) >= GATHER_PX && Math.abs(dx) < DRAG_PX) {
                f.gather = true;
                f.gx = ev.clientX;
            }
            if (f.gather) {
                // down (or up) picks the fields; sideways from here drags them
                if (Math.abs(ev.clientX - f.gx) < DRAG_PX) {
                    f.keys = this._s3dGatherKeys(f, dy);
                    this._s3dGatherShow(f.keys);
                    return;
                }
                f.x0 = f.gx;
            } else if (Math.abs(dx) < DRAG_PX) {
                return;
            }
            const layer = this._s3dFieldLayer(f);
            if (!layer || this._lockedRefused(layer)) {
                f.refused = true;
                this._s3dGatherShow(null);
                return;
            }
            f.moved = true;
            f.lastX = f.x0;
            f.keys.forEach(k => { f.starts[k] = this._s3dFieldModel(layer, k); });
            document.body.classList.add('s3d-scrubbing');
            f.esc = (e) => {
                if (e.key !== 'Escape') return;
                e.preventDefault();
                e.stopPropagation();
                this._s3dFieldCancel();
            };
            window.addEventListener('keydown', f.esc, true);
        }
        const unit = this._s3dFieldUnit(f.key);
        const fine = ev.shiftKey ? FINE : 1;
        f.raw += (ev.clientX - f.lastX) * PX_STEP[unit] * fine;
        f.lastX = ev.clientX;
        const snap = ev.ctrlKey || ev.metaKey;
        f.values = {};
        for (const k of f.keys) {
            const v = f.starts[k] + f.raw;
            f.values[k] = snap ? Math.round(v / SNAP[unit]) * SNAP[unit] : v;
            const el = document.getElementById(`s3d-${k}`);
            if (el) el.value = this._s3dFieldText(k, f.values[k]);
        }
        this._s3dFieldPreview(this._s3dFieldLayer(f), f.values);
    }

    _s3dFieldRelease(ev, cancelled) {
        const st = this._s3dState();
        const f = st.field;
        if (!f || (ev && ev.pointerId !== undefined && ev.pointerId !== f.pointerId)) return;
        st.field = null;
        document.body.classList.remove('s3d-scrubbing');
        this._s3dGatherShow(null);
        if (f.esc) window.removeEventListener('keydown', f.esc, true);
        try { f.field.releasePointerCapture(f.pointerId); } catch (e) { /* not held */ }
        if (f.refused) {
            this._s3dRefreshPanel(true);
            return;
        }
        if (!f.moved) {
            // A click: the caret goes in where it was clicked, to type.
            if (!cancelled && !f.gather) this._s3dFieldCaret(f.input, ev ? ev.clientX : null);
            return;
        }
        const layer = this._s3dFieldLayer(f);
        this._s3dFieldEndPreview(cancelled || !layer);
        if (cancelled || !layer || !f.values) {
            this._s3dRefreshPanel(true);
            return;
        }
        sendClientLog('stage3d_field_drag', { keys: f.keys, from: f.starts, to: f.values });
        this._s3dFieldCommitValues(layer, f.values);
    }

    // Focus the field with the caret at the page x clicked (the figure is
    // right-aligned, so the text's left edge is measured from the right).
    _s3dFieldCaret(input, clientX) {
        input.focus();
        const text = input.value || '';
        let at = text.length;
        if (clientX !== null && text) {
            const cs = getComputedStyle(input);
            const ctx = (this._s3dMeasure || (this._s3dMeasure = document.createElement('canvas').getContext('2d')));
            ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
            const r = input.getBoundingClientRect();
            const right = r.right - (parseFloat(cs.paddingRight) || 0) - (parseFloat(cs.borderRightWidth) || 0);
            const left = right - ctx.measureText(text).width;
            const x = clientX - left;
            at = 0;
            while (at < text.length && ctx.measureText(text.slice(0, at + 1)).width - ctx.measureText(text[at]).width / 2 < x) at++;
        }
        try { input.setSelectionRange(at, at); } catch (e) { /* not a text field */ }
    }

    _s3dFieldLayer(f) {
        const layer = this._s3dCurrentScreen();
        return layer && f && layer.id === f.layerId ? layer : null;
    }

    // Esc during a drag: the screen goes back and nothing is saved.
    _s3dFieldCancel() {
        const st = this._s3dState();
        const f = st.field;
        if (!f) return false;
        this._s3dFieldRelease({ pointerId: f.pointerId }, true);
        return true;
    }

    // ── the view follows ──────────────────────────────────────────────────

    // The screen (and its group) drawn where the figures put them, without
    // saving anything: the stage keeps the preview until the drag ends
    // (app-stage3d.js _s3dUpdateEntry leaves a screen in st.drag alone).
    _s3dFieldPreview(layer, values) {
        if (!layer) return;
        const st = this._s3dState();
        const shown = { ...this._s3dShownOf(layer, this._s3dPlacementOf(layer)), ...values };
        const plan = this._s3dPlanEdit(layer, s3dStoredFrom(layer, shown, this._s3dFooterMm(layer)));
        if (!st.drag || st.drag.kind !== 'field') {
            const layout = this._s3dLayout();
            st.drag = {
                kind: 'field', active: true,
                starts: new Map([...plan.values()].map(({ layer: l }) => [l.id, this._s3dPlacementOf(l, layout)])),
            };
        }
        for (const [id, { placed }] of plan) {
            const e = st.entries.get(id);
            if (!e) continue;
            e.obj.position.set(placed.x, placed.y, placed.z);
            e.obj.rotation.set(placed.pitch * DEG, placed.yaw * DEG, placed.roll * DEG, 'YXZ');
        }
        this._s3dRequestRender();
    }

    _s3dFieldEndPreview(revert) {
        const st = this._s3dState();
        const d = st.drag;
        if (!d || d.kind !== 'field') return;
        st.drag = null;
        if (revert) this._s3dRevertPreview(d);
    }

    // ── typing and the keys ───────────────────────────────────────────────

    _s3dFieldKey(input, ev) {
        const key = input.dataset.s3dKey;
        if (ev.key === 'Escape') {
            ev.preventDefault();
            ev.stopPropagation();
            input.value = input.dataset.text || input.value;
            delete input.dataset.pending;
            this._s3dFieldEndPreview(true);
            input.blur();
            return;
        }
        if (ev.key === 'Tab' && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
            // X, Y, Z, Pitch, Yaw, Roll, and back: past either end, the
            // page's own order takes over.
            const next = KEYS[KEYS.indexOf(key) + (ev.shiftKey ? -1 : 1)];
            const el = next ? document.getElementById(`s3d-${next}`) : null;
            if (!el) return;
            ev.preventDefault();
            el.focus();
            el.select();
            return;
        }
        if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
        ev.preventDefault();
        ev.stopPropagation();
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        if (this._lockedRefused(layer)) {
            this._s3dRefreshPanel(true);
            return;
        }
        const unit = this._s3dFieldUnit(key);
        const dir = ev.key === 'ArrowUp' ? 1 : -1;
        const model = this._s3dFieldModel(layer, key);
        const pending = input.dataset.pending !== undefined && input.value === input.dataset.pendingText
            ? Number(input.dataset.pending) : null;
        const typed = pending === null && input.value !== input.dataset.text
            ? this._s3dFieldParse(key, input.value, model) : null;
        const base = pending !== null ? pending : (typed !== null ? typed : model);
        let value;
        if (ev.ctrlKey || ev.metaKey) {
            value = (Math.round(base / SNAP[unit]) + dir) * SNAP[unit];
        } else {
            value = base + dir * NUDGE[unit] * (ev.shiftKey ? FINE : 1);
        }
        input.value = this._s3dFieldText(key, value);
        input.dataset.pending = String(value);
        input.dataset.pendingText = input.value;
        this._s3dFieldPreview(layer, { [key]: value });
    }

    // The field lets go (Enter, Tab, a click elsewhere) or its text
    // changed: the figure it holds is saved, once. Unchanged text saves
    // nothing; text that is no figure puts the old one back, with a note.
    _s3dFieldFinish(input) {
        const key = input.dataset.s3dKey;
        const layer = this._s3dCurrentScreen();
        const text = String(input.value || '').trim();
        let value = null;
        if (input.dataset.pending !== undefined && input.value === input.dataset.pendingText) {
            value = Number(input.dataset.pending);
        } else if (text !== (input.dataset.text || '')) {
            value = layer ? this._s3dFieldParse(key, text, this._s3dFieldModel(layer, key)) : null;
            if (value === null) {
                delete input.dataset.pending;
                this._s3dFieldEndPreview(true);
                const was = input.dataset.text || '';
                this._s3dRefreshPanel(true);
                const name = input.getAttribute('aria-label') || key;
                this._s3dFieldNote(key, `"${text}" is not a figure; ${name} is back to ${was}.`);
                return;
            }
        }
        delete input.dataset.pending;
        if (value === null || !layer) {
            this._s3dFieldEndPreview(true);
            return;
        }
        this._s3dFieldEndPreview(false);
        input.dataset.text = input.value;
        this._s3dFieldCommitValues(layer, { [key]: value });
    }

    // One step of a field's < or > (Shift a tenth): one undo step.
    _s3dFieldStep(key, dir, fine) {
        const layer = this._s3dCurrentScreen();
        if (!layer || !(dir === 1 || dir === -1)) return;
        const unit = this._s3dFieldUnit(key);
        const now = this._s3dFieldModel(layer, key);
        this._s3dFieldCommitValues(layer, { [key]: now + dir * NUDGE[unit] * (fine ? FINE : 1) });
    }

    // Figures saved together: one undo step, the group following.
    _s3dFieldCommitValues(layer, values) {
        const shown = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        const keys = Object.keys(values).filter(k => Number.isFinite(values[k]));
        const changed = keys.filter(k => Math.abs((Number(shown[k]) || 0) - values[k]) >= 1e-9);
        if (!changed.length) {
            this._s3dRefreshPanel(true);
            return;
        }
        const next = { ...shown };
        changed.forEach(k => { next[k] = values[k]; });
        this._s3dCommitShown(layer, next, changed.every(isLength) ? 'Move Screen (3D)'
            : (changed.some(isLength) ? 'Place Screen (3D)' : 'Rotate Screen (3D)'));
    }

    // ── reset icons and the right-click menu ──────────────────────────────

    // Back to the Show Look place, the rotation kept.
    _s3dResetPosition() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const p = this._s3dPlacementOf(layer);
        const home = this._s3dShowLookPlacement(layer);
        if (['x', 'y', 'z'].every(k => Math.abs(p[k] - home[k]) < 1e-6)) return;
        this._s3dCommit(layer, { ...p, x: home.x, y: home.y, z: home.z }, 'Reset Position (3D)');
    }

    // Upright and facing the audience, the point X, Y and Z show kept.
    _s3dResetRotation() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const shown = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        if (!shown.pitch && !shown.yaw && !shown.roll) return;
        this._s3dCommitShown(layer, { ...shown, pitch: 0, yaw: 0, roll: 0 }, 'Reset Rotation (3D)');
    }

    // The figure Reset gives one field: X, Y or Z as Reset position would
    // put them, an angle 0.
    _s3dFieldHome(layer, key) {
        if (!isLength(key)) return 0;
        const p = this._s3dPlacementOf(layer);
        const home = this._s3dShowLookPlacement(layer);
        return this._s3dShownOf(layer, { ...p, x: home.x, y: home.y, z: home.z })[key];
    }

    // Copied figures: kept here (and put on the system clipboard as text
    // too), so Paste works whatever the browser allows.
    _s3dCopy(kind, texts) {
        const st = this._s3dState();
        st.clip = { kind, texts };
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texts.join(', ')).catch(() => {});
        } catch (e) { /* no clipboard here */ }
    }

    _s3dFieldMenu(key, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        this._s3dCloseFieldMenu();
        const st = this._s3dState();
        const kind = isLength(key) ? 'length' : 'angle';
        const row = rowOf(key);
        const label = (k) => (document.getElementById(`s3d-${k}`) || {}).getAttribute?.('aria-label') || k;
        const textOf = (k) => {
            const v = this._s3dFieldModel(layer, k);
            return isLength(k) ? `${this._s3dFormatLength(v)} ${this._s3dUnits()}` : `${round(wrap180(v), 2)}°`;
        };
        const clip = st.clip && st.clip.kind === kind ? st.clip : null;
        const live = () => this._s3dCurrentScreen();
        const items = [
            ['reset', 'Reset', () => this._s3dFieldCommitValues(live(), { [key]: this._s3dFieldHome(live(), key) })],
            ['copy', 'Copy value', () => this._s3dCopy(kind, [textOf(key)])],
            ['paste', 'Paste value', () => {
                const v = this._s3dFieldParse(key, clip.texts[0]);
                if (v !== null) this._s3dFieldCommitValues(live(), { [key]: v });
            }, !clip],
            ['copy-all', 'Copy all three', () => this._s3dCopy(kind, row.map(textOf))],
            ['paste-all', 'Paste all three', () => {
                const values = {};
                row.forEach((k, i) => { const v = this._s3dFieldParse(k, clip.texts[i]); if (v !== null) values[k] = v; });
                this._s3dFieldCommitValues(live(), values);
            }, !clip || clip.texts.length !== 3],
        ];
        if (!isLength(key)) {
            items.push(['+90', '+90°', () => this._s3dFieldCommitValues(live(), { [key]: wrap180(this._s3dFieldModel(live(), key) + 90) })]);
            items.push(['-90', '-90°', () => this._s3dFieldCommitValues(live(), { [key]: wrap180(this._s3dFieldModel(live(), key) - 90) })]);
        }
        const menu = document.createElement('div');
        menu.id = 's3d-field-menu';
        menu.setAttribute('role', 'menu');
        menu.setAttribute('aria-label', label(key));
        for (const [id, text, act, off] of items) {
            const b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('role', 'menuitem');
            b.dataset.s3dMenu = id;
            b.textContent = text;
            b.disabled = !!off;
            b.addEventListener('click', () => {
                this._s3dCloseFieldMenu();
                if (live()) act();
            });
            menu.appendChild(b);
        }
        document.body.appendChild(menu);
        const w = menu.offsetWidth, h = menu.offsetHeight;
        menu.style.left = `${Math.max(4, Math.min(ev.clientX, window.innerWidth - w - 4))}px`;
        menu.style.top = `${Math.max(4, Math.min(ev.clientY, window.innerHeight - h - 4))}px`;
        st.fieldMenuClose = (e) => {
            if (e.type === 'keydown' && e.key !== 'Escape') return;
            if (e.type === 'pointerdown' && menu.contains(e.target)) return;
            this._s3dCloseFieldMenu();
        };
        window.addEventListener('pointerdown', st.fieldMenuClose, true);
        window.addEventListener('keydown', st.fieldMenuClose, true);
        window.addEventListener('blur', st.fieldMenuClose);
    }

    _s3dCloseFieldMenu() {
        const st = this._s3dState();
        const menu = document.getElementById('s3d-field-menu');
        if (menu) menu.remove();
        if (st.fieldMenuClose) {
            window.removeEventListener('pointerdown', st.fieldMenuClose, true);
            window.removeEventListener('keydown', st.fieldMenuClose, true);
            window.removeEventListener('blur', st.fieldMenuClose);
            st.fieldMenuClose = null;
        }
    }

    // ── the Curve and the corners, as they stand ──────────────────────────

    // "Curve: 7.5° per joint, concave, 45° in all." The Curve is the
    // Header/Footer tab's; a corner's seam takes no curve angle, so it is
    // left out.
    _s3dCurveText(layer, p) {
        if (!s3dCurveOn(layer)) return 'No curve. The Curve on the Header/Footer tab bends the column joints.';
        const cannot = typeof this._curveCannot === 'function' ? this._curveCannot(layer) : '';
        if (cannot) return `The Curve is on but cannot be laid: ${cannot}.`;
        const cols = this._s3dGridCounts(layer).cols;
        const seams = s3dCornerSeams(layer, cols);
        const angles = [];
        for (let j = 0; j < cols - 1; j++) {
            if (!seams.has(j)) angles.push(Number((p.jointsCol || {})[String(j)]) || 0);
        }
        const bent = angles.filter(a => Math.abs(a) > 1e-9);
        if (!bent.length) return 'Curve on, every joint flat.';
        const deg = (a) => `${round(Math.abs(a), 2)}°`;
        const mags = [...new Set(bent.map(a => round(Math.abs(a), 2)))].sort((a, b) => a - b);
        const bend = (layer.riggingCurve && layer.riggingCurve.bend) === 'convex' ? 'convex' : 'concave';
        const total = `${round(Math.abs(bent.reduce((s, a) => s + a, 0)), 1)}° in all`;
        if (mags.length === 1 && bent.length === angles.length) return `Curve: ${deg(mags[0])} per joint, ${bend}, ${total}.`;
        const at = `${bent.length} of ${angles.length} joints`;
        if (mags.length === 1) return `Curve: ${deg(mags[0])} at ${at}, ${bend}, ${total}.`;
        return `Curve: ${deg(mags[0])} to ${deg(mags[mags.length - 1])} at ${at}, ${bend}, ${total}.`;
    }

    _s3dPanelReadouts(layer, p) {
        const curve = document.getElementById('s3d-curve-info');
        if (curve) {
            const text = this._s3dCurveText(layer, p);
            if (curve.textContent !== text) curve.textContent = text;
        }
        const host = document.getElementById('s3d-corner-info');
        if (host) {
            const list = s3dCornersOn(layer, this._s3dGridCounts(layer).cols);
            const lines = list.length
                ? list.map(c => `${cornerSpotLabel(c.at)}: ${c.side === 'exterior' ? 'Exterior' : 'Interior'} 90°`)
                : ['None.'];
            const sig = lines.join('\n');
            if (host.dataset.sig !== sig) {
                host.dataset.sig = sig;
                host.innerHTML = '';
                lines.forEach(t => {
                    const row = document.createElement('div');
                    row.textContent = t;
                    host.appendChild(row);
                });
            }
        }
        const st = this._s3dState();
        if (st.corner && st.corner.layerId !== layer.id) this._s3dPickCorner(null);
        else if (st.corner) this._s3dFillCornerPop();
    }

    // The Curve's settings, on the Header/Footer tab, for this screen.
    _s3dOpenCurve() {
        const tab = document.querySelector('#view-tabs .view-tab[data-mode="rigging"]');
        if (!tab) return;
        sendClientLog('stage3d_open_curve', {});
        tab.click();
        requestAnimationFrame(() => {
            const box = document.getElementById('rigging-curve');
            if (!box) return;
            box.scrollIntoView({ block: 'nearest' });
            box.classList.remove('s3d-flash');
            void box.offsetWidth;
            box.classList.add('s3d-flash');
            setTimeout(() => box.classList.remove('s3d-flash'), 1400);
            const check = document.getElementById('rigging-curve-on');
            if (check) check.focus({ preventScroll: true });
        });
    }

    // ── corners picked in the view ────────────────────────────────────────

    // The corner spot a click on the picked screen lands on, in half steps
    // (3 the middle of panel 3, 3.5 the seam between 3 and 4), or null: a
    // seam between two columns, or the middle of a panel, within a short
    // reach. COLUMNS ONLY (owner, 2026-11-10: "it is allowing me to make
    // horizontal joints which is not right"): a click on or near a seam
    // between two rows picks nothing.
    _s3dSpotAt(hit) {
        if (!hit || !hit.entry || !hit.entry.built) return null;
        const built = hit.entry.built;
        const q = built.quads[hit.quad];
        if (!q) return null;
        const local = hit.entry.obj.worldToLocal(hit.point.clone());
        const p = [local.x, local.y, local.z];
        const ax = [q.tr[0] - q.tl[0], q.tr[1] - q.tl[1], q.tr[2] - q.tl[2]];
        const W = Math.hypot(ax[0], ax[1], ax[2]);
        const H = Math.hypot(q.bl[0] - q.tl[0], q.bl[1] - q.tl[1], q.bl[2] - q.tl[2]);
        if (!W || !H) return null;
        const u = ((p[0] - q.tl[0]) * ax[0] + (p[1] - q.tl[1]) * ax[1] + (p[2] - q.tl[2]) * ax[2]) / W;
        const across = q.u0 + u * ((q.u1 - q.u0) / W);
        const len = built.colLen[q.ci];
        const n = built.colLen.length;
        const near = Math.min(120, 0.18 * Math.min(len, H));
        const cands = [];
        if (q.ci > 0) cands.push([across, q.ci + 0.5]);
        if (q.ci < n - 1) cands.push([len - across, q.ci + 1.5]);
        cands.push([Math.abs(across - len / 2), q.ci + 1]);
        const best = cands.filter(c => c[0] < near).sort((a, b) => a[0] - b[0])[0];
        if (!best) return null;
        // nearer a seam between two rows than to the column spot: nothing
        const down = ((p[0] - q.tl[0]) * (q.bl[0] - q.tl[0]) + (p[1] - q.tl[1]) * (q.bl[1] - q.tl[1])
            + (p[2] - q.tl[2]) * (q.bl[2] - q.tl[2])) / H;
        const nRows = built.rowLen.length;
        const rowLen = built.rowLen[q.ri] || H;
        const along = q.w0 + down;
        const rowSeam = Math.min(q.ri > 0 ? along : Infinity, q.ri < nRows - 1 ? rowLen - along : Infinity);
        if (rowSeam < near && rowSeam <= best[0]) return null;
        return best[1];
    }

    // Pick spot `at` of screen `layerId` for a corner (null lets go): the
    // spot is marked on the screen and the picker opens beside the click.
    _s3dPickCorner(layerId, at = null, clientX = null, clientY = null) {
        const st = this._s3dState();
        const pop = document.getElementById('s3d-corner-pop');
        const was = st.corner;
        if (layerId == null || at === null) {
            st.corner = null;
            if (pop) pop.hidden = true;
            this._s3dCornerPopListen(false);
        } else {
            st.corner = { layerId, at };
            this._s3dFillCornerPop();
            if (pop) {
                pop.hidden = false;
                this._s3dPlaceCornerPop(pop, clientX, clientY);
            }
            this._s3dCornerPopListen(true);
            sendClientLog('stage3d_corner_pick', { id: layerId, at });
        }
        if ((was || st.corner) && st.T && st.renderer) {
            this._s3dHighlight(this._s3dTokens());
            this._s3dRequestRender();
        }
    }

    _s3dFillCornerPop() {
        const st = this._s3dState();
        const c = st.corner;
        const pop = document.getElementById('s3d-corner-pop');
        if (!c || !pop) return;
        const layer = ((this.project && this.project.layers) || []).find(l => l.id === c.layerId);
        if (!layer) return;
        const list = typeof this.riggingCornersOf === 'function' ? this.riggingCornersOf(layer) : [];
        const had = list.find(x => x.at === c.at) || null;
        const free = had || typeof this._cornerSpotFree !== 'function'
            || this._cornerSpotFree(c.at, list.map(x => x.at));
        const title = document.getElementById('s3d-corner-pop-title');
        if (title) title.textContent = `Corner, ${cornerSpotLabel(c.at).toLowerCase()}`;
        pop.querySelectorAll('[data-s3d-corner]').forEach(b => {
            const side = b.dataset.s3dCorner;
            b.classList.toggle('active', side === (had ? had.side : 'none'));
            b.disabled = side !== 'none' && !free;
        });
        const note = document.getElementById('s3d-corner-pop-note');
        if (note) {
            note.hidden = !!free;
            note.textContent = free ? '' : 'Too close to another corner. Corners need a panel of their own for their corner bars.';
        }
    }

    // Beside the click, inside the view.
    _s3dPlaceCornerPop(pop, clientX, clientY) {
        const host = pop.offsetParent || pop.parentElement;
        if (!host) return;
        const r = host.getBoundingClientRect();
        const w = pop.offsetWidth, h = pop.offsetHeight;
        const x = clientX === null ? r.width / 2 - w / 2 : clientX - r.left + 14;
        const y = clientY === null ? r.height / 2 - h / 2 : clientY - r.top + 14;
        pop.style.left = `${Math.max(6, Math.min(x, r.width - w - 6))}px`;
        pop.style.top = `${Math.max(6, Math.min(y, r.height - h - 6))}px`;
    }

    // While the picker is up, a press anywhere else or Esc closes it.
    _s3dCornerPopListen(on) {
        const st = this._s3dState();
        if (st.cornerPopClose) {
            window.removeEventListener('pointerdown', st.cornerPopClose, true);
            window.removeEventListener('keydown', st.cornerPopClose, true);
            st.cornerPopClose = null;
        }
        if (!on) return;
        st.cornerPopClose = (e) => {
            const pop = document.getElementById('s3d-corner-pop');
            if (e.type === 'keydown') {
                if (e.key !== 'Escape') return;
                e.preventDefault();
                e.stopPropagation();
            } else if (pop && pop.contains(e.target)) {
                return;
            }
            this._s3dPickCorner(null);
        };
        window.addEventListener('pointerdown', st.cornerPopClose, true);
        window.addEventListener('keydown', st.cornerPopClose, true);
    }

    // A choice in the picker: written as the Header/Footer tab writes it.
    _s3dCornerChoose(side) {
        const st = this._s3dState();
        const c = st.corner;
        if (!c) return;
        const layer = ((this.project && this.project.layers) || []).find(l => l.id === c.layerId);
        this._s3dPickCorner(null);
        if (!layer || typeof this.setRiggingCornerAt !== 'function') return;
        this.setRiggingCornerAt(layer, c.at, side === 'none' ? null : side);
        this._s3dSchedule();
        this._s3dRefreshPanel();
    }

    // Where on the page a corner spot is drawn (client px): a point on the
    // screen 20 mm left of the seam or of the panel's middle, a third of
    // the way down the middle row, so a test can click it the way a person
    // would. Changes nothing.
    _s3dDebugSpot(layerId, at) {
        const st = this._s3dState();
        const e = st.entries.get(layerId);
        if (!e || !e.built || !st.renderer) return null;
        const b = e.built;
        const where = this._s3dSpotColumn(b, at);
        if (!where) return null;
        const k = Math.floor(b.rowLen.length / 2);
        const local = where.u > 0
            ? b.point(where.i, where.u - 20, k, b.rowLen[k] / 3)
            : b.point(where.i - 1, b.colLen[where.i - 1] - 20, k, b.rowLen[k] / 3);
        e.obj.updateMatrixWorld(true);
        const v = new st.T.Vector3(local[0], local[1], local[2]).applyMatrix4(e.obj.matrixWorld).project(st.camera);
        const rect = st.renderer.domElement.getBoundingClientRect();
        return [rect.left + (v.x + 1) / 2 * rect.width, rect.top + (1 - v.y) / 2 * rect.height];
    }
}

for (const k of Object.getOwnPropertyNames(_Stage3DPanel.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Stage3DPanel.prototype, k));
    }
}
