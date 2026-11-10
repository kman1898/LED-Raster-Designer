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
//                             15 degrees. The whole drag is ONE undo step.
//   click without dragging    puts the caret in it to type (Math OK, and a
//                             length with its own unit, 12' 6" or 3.5m)
//   Enter                     commits and lets go ("Enter ends the edit")
//   Esc                       puts the figure back and lets go
//   Up / Down                 nudge 1 in, 1 cm or 1 degree (Shift a tenth,
//                             Ctrl / Cmd a snap step); the run of nudges is
//                             one undo step, saved when the field lets go
//   the wheel                 does nothing (too easy to do by accident)
//   right-click a rotation    +90, -90 and Reset
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
    DEG, round, wrap180, s3dCornersOn, s3dCornerSeams, s3dCurveOn, s3dStoredFrom,
} from './app-stage3d.js';
import { cornerSpotLabel } from './app-corners.js';

const LENGTH_KEYS = ['x', 'y', 'z'];
const ANGLE_KEYS = ['pitch', 'yaw', 'roll'];
const KEYS = LENGTH_KEYS.concat(ANGLE_KEYS);
const DRAG_PX = 3;               // a press that travels this far is a drag
// A drag's step per page pixel, and the snap and nudge steps, in mm or
// degrees: feet move an inch a pixel, meters a centimeter.
const PX_STEP = { ft: 25.4, m: 10, deg: 0.5 };
const SNAP = { ft: 25.4, m: 10, deg: 15 };
const NUDGE = { ft: 25.4, m: 10, deg: 1 };
const FINE = 0.1;

const isLength = (key) => LENGTH_KEYS.includes(key);

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
            input.addEventListener('keydown', (ev) => this._s3dFieldKey(input, ev));
            input.addEventListener('change', () => this._s3dFieldFinish(input));
            input.addEventListener('blur', () => this._s3dFieldFinish(input));
            if (ANGLE_KEYS.includes(key)) {
                field.addEventListener('contextmenu', (ev) => this._s3dRotationMenu(key, ev));
            }
        });
        const on = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        on('s3d-reset-position', () => this._s3dResetPosition());
        on('s3d-reset-rotation', () => this._s3dResetRotation());
        on('s3d-curve-edit', () => this._s3dOpenCurve());
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

    _s3dFieldParse(key, text) {
        return isLength(key) ? this._s3dParseLength(text) : this._s3dParseAngle(text);
    }

    // The screen's figure as the panel shows it (X, Y and Z at the datum).
    _s3dFieldModel(layer, key) {
        return this._s3dShownOf(layer, this._s3dPlacementOf(layer))[key];
    }

    // The six figures written into their fields: the one being typed in or
    // dragged keeps its own (`force` rewrites it too).
    _s3dPanelFigures(shown, force = false) {
        const st = this._s3dState();
        for (const key of KEYS) {
            const el = document.getElementById(`s3d-${key}`);
            if (!el) continue;
            const text = this._s3dFieldText(key, shown[key]);
            if (!force && (document.activeElement === el || (st.field && st.field.key === key && st.field.moved))) continue;
            if (el.value !== text) el.value = text;
            el.dataset.text = text;
            delete el.dataset.pending;
        }
    }

    // ── press and drag ────────────────────────────────────────────────────

    _s3dFieldPress(input, field, ev) {
        if (ev.button !== 0 || document.activeElement === input) return;
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        ev.preventDefault();
        const st = this._s3dState();
        const key = input.dataset.s3dKey;
        st.field = {
            key, input, field, layerId: layer.id, pointerId: ev.pointerId,
            x0: ev.clientX, lastX: ev.clientX, moved: false, refused: false,
            start: this._s3dFieldModel(layer, key), raw: this._s3dFieldModel(layer, key), value: null,
        };
        try { field.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
    }

    _s3dFieldMove(ev) {
        const st = this._s3dState();
        const f = st.field;
        if (!f || ev.pointerId !== f.pointerId || f.refused) return;
        if (!f.moved) {
            if (Math.abs(ev.clientX - f.x0) < DRAG_PX) return;
            const layer = this._s3dFieldLayer(f);
            if (!layer || this._lockedRefused(layer)) {
                f.refused = true;
                return;
            }
            f.moved = true;
            f.lastX = f.x0;
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
        f.value = (ev.ctrlKey || ev.metaKey) ? Math.round(f.raw / SNAP[unit]) * SNAP[unit] : f.raw;
        f.input.value = this._s3dFieldText(f.key, f.value);
        this._s3dFieldPreview(this._s3dFieldLayer(f), f.key, f.value);
    }

    _s3dFieldRelease(ev, cancelled) {
        const st = this._s3dState();
        const f = st.field;
        if (!f || (ev && ev.pointerId !== undefined && ev.pointerId !== f.pointerId)) return;
        st.field = null;
        document.body.classList.remove('s3d-scrubbing');
        if (f.esc) window.removeEventListener('keydown', f.esc, true);
        try { f.field.releasePointerCapture(f.pointerId); } catch (e) { /* not held */ }
        if (f.refused) {
            this._s3dRefreshPanel(true);
            return;
        }
        if (!f.moved) {
            // A click: the caret goes in to type, the figure selected.
            if (!cancelled) {
                f.input.focus();
                f.input.select();
            }
            return;
        }
        const layer = this._s3dFieldLayer(f);
        this._s3dFieldEndPreview(cancelled || !layer);
        if (cancelled || !layer || f.value === null) {
            this._s3dRefreshPanel(true);
            return;
        }
        sendClientLog('stage3d_field_drag', { key: f.key, from: f.start, to: f.value });
        this._s3dFieldCommitValue(layer, f.key, f.value);
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

    // The screen (and its group) drawn where the figure puts them, without
    // saving anything: the stage keeps the preview until the drag ends
    // (app-stage3d.js _s3dUpdateEntry leaves a screen in st.drag alone).
    _s3dFieldPreview(layer, key, value) {
        if (!layer) return;
        const st = this._s3dState();
        const shown = { ...this._s3dShownOf(layer, this._s3dPlacementOf(layer)), [key]: value };
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
        const pending = input.dataset.pending !== undefined && input.value === input.dataset.pendingText
            ? Number(input.dataset.pending) : null;
        const typed = pending === null ? this._s3dFieldParse(key, input.value) : null;
        const base = pending !== null ? pending : (typed !== null && input.value !== input.dataset.text
            ? typed : this._s3dFieldModel(layer, key));
        let value;
        if (ev.ctrlKey || ev.metaKey) {
            value = (Math.round(base / SNAP[unit]) + dir) * SNAP[unit];
        } else {
            value = base + dir * NUDGE[unit] * (ev.shiftKey ? FINE : 1);
        }
        input.value = this._s3dFieldText(key, value);
        input.dataset.pending = String(value);
        input.dataset.pendingText = input.value;
        this._s3dFieldPreview(layer, key, value);
    }

    // The field lets go (Enter, Tab, a click elsewhere) or its text
    // changed: the figure it holds is saved, once. Unchanged text saves
    // nothing; text that is no figure puts the old one back.
    _s3dFieldFinish(input) {
        const key = input.dataset.s3dKey;
        const layer = this._s3dCurrentScreen();
        const text = String(input.value || '').trim();
        let value = null;
        if (input.dataset.pending !== undefined && input.value === input.dataset.pendingText) {
            value = Number(input.dataset.pending);
        } else if (text !== (input.dataset.text || '')) {
            value = this._s3dFieldParse(key, text);
            if (value === null) {
                delete input.dataset.pending;
                this._s3dFieldEndPreview(true);
                this._s3dRefreshPanel(true);
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
        this._s3dFieldCommitValue(layer, key, value);
    }

    // One figure saved: one undo step, the group following.
    _s3dFieldCommitValue(layer, key, value) {
        const shown = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        if (!Number.isFinite(value)) return;
        if (Math.abs((Number(shown[key]) || 0) - value) < 1e-9) {
            this._s3dRefreshPanel(true);
            return;
        }
        this._s3dCommitShown(layer, { ...shown, [key]: value }, isLength(key) ? 'Move Screen (3D)' : 'Rotate Screen (3D)');
    }

    // ── reset icons and the rotation menu ─────────────────────────────────

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

    // Right-click a rotation field: +90, -90 and Reset, each one undo step.
    _s3dRotationMenu(key, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        this._s3dCloseFieldMenu();
        const menu = document.createElement('div');
        menu.id = 's3d-field-menu';
        menu.setAttribute('role', 'menu');
        const items = [['+90', '+90°', (v) => v + 90], ['-90', '-90°', (v) => v - 90], ['reset', 'Reset', () => 0]];
        for (const [id, text, to] of items) {
            const b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('role', 'menuitem');
            b.dataset.s3dMenu = id;
            b.textContent = text;
            b.addEventListener('click', () => {
                this._s3dCloseFieldMenu();
                const live = this._s3dCurrentScreen();
                if (!live) return;
                const now = this._s3dFieldModel(live, key);
                this._s3dFieldCommitValue(live, key, wrap180(to(now)));
            });
            menu.appendChild(b);
        }
        document.body.appendChild(menu);
        const w = menu.offsetWidth, h = menu.offsetHeight;
        menu.style.left = `${Math.max(4, Math.min(ev.clientX, window.innerWidth - w - 4))}px`;
        menu.style.top = `${Math.max(4, Math.min(ev.clientY, window.innerHeight - h - 4))}px`;
        const st = this._s3dState();
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
    // reach. Columns only.
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
        return best ? best[1] : null;
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
