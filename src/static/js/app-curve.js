// app-curve: the Header/Footer tab's Curve. A Curve checkbox on the
// selected screens; ticked, a compact form (the curve as a % of a full
// circle or degrees of sweep, concave or convex, Simplest / Even /
// Tightest, how close is close enough, the angles the locks have, and
// where the build starts) and the result: a build sheet strip of the bars
// with the angle at every join between them, a small plan of the wall
// from above against the drawn arc, and the readouts.
//
// The math is the curve calculator's own (curve-math.js). The bar sizes
// are the tab's lit sizes (the stock on the truck), in panel widths; the
// panel width is the screen's own.
//
// CURVE ON MEANS THE CALCULATOR OWNS THAT SCREEN'S BARS AND JOINT ANGLES:
// it lays the screen's bars on its side (header or footer), the tab's
// real bars, so the totals, the pull list and the binder count them, and
// writes the angle at every joint between columns into the screen's 3D
// placement (stage3d.jointsCol, concave positive, flat joints written as
// 0 so the screen-wide column figure never leaks in). Every change is one
// undo step. While Curve is on, Custom does not lay bars on that screen
// and Auto lays the curve again. Turned off, the joints go back to the
// screen-wide figure and the bars stay where they are.
//
// Stored on the layer as riggingCurve (curve-math.js cleanCurve holds its
// shape); a show without it has every screen off, unchanged.
//
// What is left out, on purpose, to keep the tab compact: the table of
// every way to build it (Simplest, Even and Tightest are the three that
// matter, one click each) and the reference table of every joint at one
// angle. The datum is the center or either end, not a dragged point.
import { LEDRasterApp } from './app-core.js';
import { s3dSanitize } from './app-stage3d.js';
import {
    cleanCurve, convertCurveEntry, formatAngle, formatLength, formatSmall, parseAngles,
    screenCurve,
} from './curve-math.js';

const CACHE_MAX = 40;
const NS = 'http://www.w3.org/2000/svg';

const listWords = (names) => (names.length <= 1 ? (names[0] || '')
    : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

class _Curve {
    _wireRiggingCurve() {
        const box = document.getElementById('rigging-curve-on');
        if (!box || box.dataset.wired) return;
        box.dataset.wired = '1';
        box.addEventListener('change', () => this.setRiggingCurveOn(box.checked));
        const group = (sel, key) => document.querySelectorAll(sel).forEach(btn => {
            btn.addEventListener('click', () => this.setRiggingCurveField(key, btn.dataset.value));
        });
        group('#rigging-curve-entry .rigging-curve-btn', 'entry');
        group('#rigging-curve-bend .rigging-curve-btn', 'bend');
        group('#rigging-curve-goal .rigging-curve-btn', 'goal');
        group('#rigging-curve-from .rigging-curve-btn', 'from');
        const field = (id, key) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.setRiggingCurveField(key, el.value));
        };
        field('rigging-curve-value', 'value');
        field('rigging-curve-tol', 'tolerance');
        field('rigging-curve-angles', 'angles');
    }

    // ---- what is stored ---------------------------------------------------

    riggingCurveOf(layer) {
        return cleanCurve(layer && layer.riggingCurve);
    }

    riggingCurveOn(layer) {
        return !!layer && (layer.type || 'screen') === 'screen' && this.riggingCurveOf(layer).on;
    }

    // Readouts in the show's own unit: meters on a meter show, feet and
    // inches otherwise.
    _curveSystem() {
        return (typeof this.cableUnit === 'function' && this.cableUnit() === 'm') ? 'metric' : 'imperial';
    }

    // Why a screen cannot take a Curve, or '' when it can.
    _curveCannot(layer) {
        const cols = Number(layer.columns) || 0;
        if (this.riggingWallPanels(layer) !== cols) {
            return 'it is turned a quarter, so its bars run down its columns';
        }
        if (this.riggingSideOf(layer) === 'both') return 'it has a header and a footer';
        const row = this.riggingRow(layer, this.riggingSideOf(layer));
        if (row.layers.length > 1) return 'its bars run across its group, and a curve is one screen\'s';
        return '';
    }

    // The calculator's answer for a screen as it stands (curve-math.js
    // screenCurve), kept by everything it depends on.
    riggingCurveSolve(layer, settings = null) {
        const s = settings || this.riggingCurveOf(layer);
        const input = {
            panels: Number(layer.columns) || 0,
            panelWidthM: (Number(layer.panel_width_mm) || 500) / 1000,
            sizes: this._riggingSizesOf(layer),
            settings: { ...s, on: true },
            system: this._curveSystem(),
        };
        const key = JSON.stringify(input);
        if (!this._curveCache) this._curveCache = new Map();
        const hit = this._curveCache.get(key);
        if (hit) return hit;
        const out = screenCurve(input);
        if (this._curveCache.size >= CACHE_MAX) this._curveCache.delete(this._curveCache.keys().next().value);
        this._curveCache.set(key, out);
        return out;
    }

    // Lay the screen's curve: its bars on its side and the angle at every
    // column joint. False (and nothing written) when the calculator
    // refused the input; the panel shows why.
    _curveLay(layer) {
        const out = this.riggingCurveSolve(layer);
        if (out.errors.length) return false;
        const side = this.riggingSideOf(layer) === 'footer' ? 'footer' : 'header';
        let at = 0;
        this._riggingWrite(layer, side, out.bars.map(size => { const b = { start: at, size }; at += size; return b; }));
        layer.riggingCustom = false;
        const jointsCol = {};
        out.joints.forEach((a, j) => { jointsCol[String(j)] = a; });
        const prev = this._s3dPlacementOf(layer);
        layer.stage3d = s3dSanitize({ ...prev, jointsCol });
        return true;
    }

    // Curve off: the column joints go back to the screen-wide figure.
    _curveUnlay(layer) {
        const prev = layer.stage3d ? s3dSanitize(layer.stage3d) : null;
        if (prev && Object.keys(prev.jointsCol).length) layer.stage3d = { ...prev, jointsCol: {} };
    }

    // The selected screens (and none locked) that a Curve edit acts on.
    _curveTargets(onlyOn) {
        const screens = this._riggingScreens().filter(l => !onlyOn || this.riggingCurveOn(l));
        return this._writableLayers(screens);
    }

    setRiggingCurveOn(on) {
        const screens = this._curveTargets(false);
        const changed = [];
        const refused = [];
        for (const l of screens) {
            const s = this.riggingCurveOf(l);
            if (on) {
                const why = this._curveCannot(l);
                if (why) { refused.push([l, why]); continue; }
                if (s.on) continue;
                l.riggingCurve = { ...s, on: true };
                this._curveLay(l);
            } else {
                if (!s.on) continue;
                l.riggingCurve = { ...s, on: false };
                this._curveUnlay(l);
            }
            changed.push(l);
        }
        if (refused.length) {
            this._toast(refused.map(([l, why]) => `${l.name || `Screen ${l.id}`} cannot take a Curve: ${why}.`).join(' '), true, 7000);
        }
        if (changed.length) this.updateLayers(changed, true, on ? 'Curve On' : 'Curve Off');
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // One field of the form, on every selected screen with its Curve on,
    // laid again. One undo step.
    setRiggingCurveField(key, raw) {
        const screens = this._curveTargets(true);
        if (!screens.length) { this.refreshRiggingPanel(); return; }
        const primary = this._riggingPrimary(screens);
        const base = this.riggingCurveOf(primary);
        const patch = {};
        if (key === 'entry') {
            if (raw !== 'percent' && raw !== 'degrees') return;
            patch.entry = raw;
        } else if (key === 'bend') {
            if (raw !== 'concave' && raw !== 'convex') return;
            patch.bend = raw;
        } else if (key === 'goal') {
            if (!['simplest', 'even', 'tightest'].includes(raw)) return;
            patch.goal = raw;
        } else if (key === 'from') {
            if (!['center', 'left', 'right'].includes(raw)) return;
            patch.from = raw;
        } else if (key === 'value') {
            const v = Number(String(raw).replace(/[%°\s]/g, ''));
            const max = base.entry === 'degrees' ? 360 : 100;
            if (!Number.isFinite(v) || v < 0 || v > max) {
                this._toast(base.entry === 'degrees' ? 'Curve, type degrees of sweep from 0 to 360.' : 'Curve, type a % of a full circle from 0 to 100.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.value = v;
        } else if (key === 'tolerance') {
            const v = Number(String(raw).replace(/[a-z"\s]/gi, ''));
            if (!Number.isFinite(v) || v < 0) { this.refreshRiggingPanel(); return; }
            patch.toleranceMm = this._curveSystem() === 'metric' ? v : v * 25.4;
        } else if (key === 'angles') {
            const list = parseAngles(raw);
            if (!list || !list.length) {
                this._toast('Lock angles, type the angles the bars lock at, like 2.5, 5, 7.5, 10.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.angles = list;
        } else {
            return;
        }
        const changed = [];
        for (const l of screens) {
            const s = this.riggingCurveOf(l);
            const next = { ...s, ...patch };
            // Switching % and degrees says the same curve the other way:
            // the wall does not change.
            if (patch.entry && patch.entry !== s.entry) {
                next.value = Math.round(convertCurveEntry(s.value,
                    s.entry === 'degrees' ? 'sweep_deg' : 'percent_circle',
                    patch.entry === 'degrees' ? 'sweep_deg' : 'percent_circle') * 1e6) / 1e6;
            }
            if (JSON.stringify(next) === JSON.stringify(s)) continue;
            l.riggingCurve = next;
            this._curveLay(l);
            changed.push(l);
        }
        if (changed.length) this.updateLayers(changed, true, 'Curve');
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The curved screens among `layers`, laid again (the lit sizes changed,
    // or Auto was pressed): the caller's updateLayers saves them in its own
    // undo step. Returns the ones laid.
    riggingCurveRelay(layers) {
        const out = [];
        for (const l of layers || []) {
            if (!this.riggingCurveOn(l) || this._curveCannot(l)) continue;
            if (this._curveLay(l)) out.push(l);
        }
        return out;
    }

    // A Custom gesture or a Remove Bar on a curved screen: refused, said
    // in one line. True when refused.
    riggingCurveRefusesHand(layers) {
        const curved = (layers || []).filter(l => this.riggingCurveOn(l));
        if (!curved.length) return false;
        const names = listWords(curved.map(l => l.name || `Screen ${l.id}`));
        this._toast(`${names} ${curved.length === 1 ? 'has its' : 'have their'} bars laid by the Curve. Turn Curve off to lay bars by hand.`, true, 6000);
        return true;
    }

    // ---- the panel --------------------------------------------------------

    refreshRiggingCurve() {
        const block = document.getElementById('rigging-curve');
        const box = document.getElementById('rigging-curve-on');
        if (!block || !box) return;
        const screens = this._riggingScreens();
        const primary = this._riggingPrimary(screens);
        block.style.display = primary ? '' : 'none';
        if (!primary) return;
        const s = this.riggingCurveOf(primary);
        const onCount = screens.filter(l => this.riggingCurveOn(l)).length;
        box.checked = s.on;
        box.indeterminate = onCount > 0 && onCount < screens.length;
        const fields = document.getElementById('rigging-curve-fields');
        if (fields) fields.style.display = s.on ? '' : 'none';
        const note = document.getElementById('rigging-curve-note');
        if (note) {
            note.style.display = s.on ? '' : 'none';
            note.textContent = this._riggingToolNow() === 'custom'
                ? 'The Curve lays this screen\'s bars, so Custom does not. Turn Curve off to lay them by hand.'
                : 'The Curve lays this screen\'s bars from the lit sizes. Auto lays it again.';
        }
        if (!s.on) return;

        const lit = (sel, value) => document.querySelectorAll(sel).forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === value);
        });
        lit('#rigging-curve-entry .rigging-curve-btn', s.entry);
        lit('#rigging-curve-bend .rigging-curve-btn', s.bend);
        lit('#rigging-curve-goal .rigging-curve-btn', s.goal);
        lit('#rigging-curve-from .rigging-curve-btn', s.from);
        const system = this._curveSystem();
        const set = (id, value) => {
            const el = document.getElementById(id);
            if (el && document.activeElement !== el && el.value !== value) el.value = value;
        };
        set('rigging-curve-value', String(Math.round(s.value * 1000) / 1000));
        set('rigging-curve-tol', system === 'metric'
            ? String(Math.round(s.toleranceMm * 10) / 10)
            : String(Math.round(s.toleranceMm / 25.4 * 100) / 100));
        set('rigging-curve-angles', s.angles.join(', '));
        const tolUnit = document.getElementById('rigging-curve-tol-unit');
        if (tolUnit) tolUnit.textContent = system === 'metric' ? 'mm' : 'in';
        const valueUnit = document.getElementById('rigging-curve-value-unit');
        if (valueUnit) valueUnit.textContent = s.entry === 'degrees' ? 'degrees of sweep' : '% of a circle';

        const out = this.riggingCurveSolve(primary, s);
        const errorsEl = document.getElementById('rigging-curve-errors');
        const result = document.getElementById('rigging-curve-result');
        if (errorsEl) {
            errorsEl.style.display = out.errors.length ? '' : 'none';
            errorsEl.textContent = out.errors.join('\n');
        }
        if (result) result.style.display = out.errors.length ? 'none' : '';
        if (out.errors.length) return;
        this._curveDrawSheet(document.getElementById('rigging-curve-sheet'), out, s);
        this._curveDrawPlan(document.getElementById('rigging-curve-plan'), out);
        const r = out.result;
        const a = r.achieved;
        const head = document.getElementById('rigging-curve-head');
        if (head) head.textContent = this._curveHeadline(r);
        const len = (m) => formatLength(m, system);
        const rows = [
            ['Sweep', `${formatAngle(a.sweep_deg, 1)}, ${a.percent_circle.toFixed(1)}% of a circle`],
            ['Radius', Number.isFinite(a.radius_face_m) ? `${len(a.radius_face_m)} to the face` : 'straight'],
            ['Width', len(a.chord_m)],
            ['Depth', len(a.depth_m)],
            ['Off the drawing', `${formatSmall(r.max_arc_deviation_m, system)} at worst`],
        ];
        const read = document.getElementById('rigging-curve-readouts');
        if (read) {
            const sig = JSON.stringify(rows);
            if (read.dataset.sig !== sig) {
                read.dataset.sig = sig;
                read.innerHTML = '';
                rows.forEach(([k, v]) => {
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; justify-content: space-between; gap: 8px;';
                    const kEl = document.createElement('span');
                    kEl.style.color = '#aaa';
                    kEl.textContent = k;
                    const vEl = document.createElement('span');
                    vEl.textContent = v;
                    vEl.style.textAlign = 'right';
                    row.append(kEl, vEl);
                    read.appendChild(row);
                });
            }
        }
        const reason = document.getElementById('rigging-curve-reason');
        if (reason) reason.textContent = r.choice_reason;
        const warn = document.getElementById('rigging-curve-warnings');
        if (warn) {
            // The bars warning restates the build sheet strip above it.
            const shown = out.warnings.filter(w => !w.startsWith('Bars:'));
            warn.style.display = shown.length ? '' : 'none';
            warn.textContent = shown.join('\n\n');
        }
    }

    // "7.5° at 9 joints, 6 flat"
    _curveHeadline(r) {
        if (!r.angle_usage.length) return 'Every joint flat: a straight wall';
        const parts = r.angle_usage.map(u => `${formatAngle(u.angle_deg)} at ${u.count} joint${u.count === 1 ? '' : 's'}`);
        if (r.flat_joints) parts.push(`${r.flat_joints} flat`);
        return parts.join(', ');
    }

    // The build sheet strip: the bars left to right, sized to their panels
    // and marked with their size, a tag with the angle on every join that
    // bends, and the datum marked under the strip.
    _curveDrawSheet(host, out, s) {
        if (!host) return;
        const bars = out.bars;
        const joints = out.joints;
        const panels = joints.length + 1;
        const room = Math.max(120, (host.clientWidth || 200) - 2);
        const sig = JSON.stringify([bars, joints, s.from, room]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        // The strip fits the panel; past 14 px a panel it scrolls instead.
        const slots = Math.max(panels, bars.reduce((t, n) => t + n, 0));
        const W = Math.max(room, Math.round(14 * slots));
        const H = 52;
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const px = W / slots;
        const add = (tag, attrs, text) => {
            const el = document.createElementNS(NS, tag);
            Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
            if (text != null) el.textContent = text;
            svg.appendChild(el);
            return el;
        };
        const barTop = 22, barH = 16;
        let at = 0;
        bars.forEach((n, i) => {
            const x = at * px;
            add('rect', { x: x + 0.5, y: barTop, width: Math.max(1, n * px - 1), height: barH, fill: '#2a2a2a', stroke: '#888', 'stroke-width': 1, 'data-bar': i });
            add('text', { x: x + n * px / 2, y: barTop + 12, 'text-anchor': 'middle', 'font-size': 10, fill: '#ddd' }, String(n));
            at += n;
        });
        // The tags: the angle at each join that bends, over its seam, on a
        // second line where it would run into the one before.
        const ends = [-Infinity, -Infinity];
        joints.forEach((a, j) => {
            if (!a) return;
            const x = (j + 1) * px;
            const text = formatAngle(Math.abs(a));
            const half = text.length * 2.7 + 1;
            const line = x - half > ends[0] ? 0 : (x - half > ends[1] ? 1 : 0);
            ends[line] = x + half;
            add('line', { x1: x, y1: line ? 11 : barTop - 3, x2: x, y2: barTop + barH, stroke: '#e22330', 'stroke-width': 1.5 });
            add('text', { x, y: line ? 19 : 9, 'text-anchor': 'middle', 'font-size': 9, fill: '#f0f0f0', 'data-angle': j }, text);
        });
        // The datum: where the crew sets out from.
        const dx = s.from === 'left' ? 0 : s.from === 'right' ? panels * px : panels * px / 2;
        add('path', { d: `M ${dx} ${barTop + barH + 2} l -5 7 l 10 0 z`, fill: '#e22330' });
        host.appendChild(svg);
    }

    // The wall from above, drawn level, the drawn arc dashed: audience at
    // the bottom.
    _curveDrawPlan(host, out) {
        if (!host) return;
        const r = out.result;
        const face = [];
        r.placements.forEach((p, i) => { if (i === 0) face.push(p.face[0]); face.push(p.face[1]); });
        const arc = r.target_vertices;
        const sig = JSON.stringify([face.length, face[0], face[face.length - 1], r.max_arc_deviation_m, host.clientWidth]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of face.concat(arc)) {
            if (p.x < x0) x0 = p.x;
            if (p.x > x1) x1 = p.x;
            if (p.y < y0) y0 = p.y;
            if (p.y > y1) y1 = p.y;
        }
        const W = Math.max(120, (host.clientWidth || 200) - 2), pad = 4;
        const span = Math.max(1e-6, x1 - x0);
        const k = (W - 2 * pad) / span;
        const H = Math.max(14, Math.min(90, Math.round((y1 - y0) * k + 2 * pad)));
        const kk = Math.min(k, (H - 2 * pad) / Math.max(1e-6, y1 - y0));
        const ox = (W - span * kk) / 2 - x0 * kk;
        const oy = (H - (y1 - y0) * kk) / 2 - y0 * kk;
        const pts = (list) => list.map(p => `${(p.x * kk + ox).toFixed(1)},${(p.y * kk + oy).toFixed(1)}`).join(' ');
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const line = (list, attrs) => {
            const el = document.createElementNS(NS, 'polyline');
            el.setAttribute('points', pts(list));
            el.setAttribute('fill', 'none');
            Object.entries(attrs).forEach(([a, v]) => el.setAttribute(a, String(v)));
            svg.appendChild(el);
        };
        line(arc, { stroke: '#888', 'stroke-width': 1, 'stroke-dasharray': '3 3' });
        line(face, { stroke: '#e22330', 'stroke-width': 2 });
        host.appendChild(svg);
    }
}

for (const k of Object.getOwnPropertyNames(_Curve.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Curve.prototype, k));
    }
}
