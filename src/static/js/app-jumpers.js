// app-jumpers: the cable between two cabinets of one run - how every link
// of a data run or a power run is classified, how long its jumper is, and
// the per-screen lengths the short ones take. Read by the pull list
// (app-pull-list: the rows every paper prints), by the maps (canvas-data /
// canvas-power: the tag on a long jump) and by the Data and Power sidebars
// (the Jumpers row). Owner rulings, 2026-09-25, from a show of vertical-flow
// walls of 500 x 1000 mm cabinets where every row change was counted as a 6'
// jumper while the real links are about a foot:
//
//   * each link between two consecutive cabinets of a run is ONE of:
//       VERTICAL   - the next cabinet directly above / below: same screen,
//                    same column, row +-1. A jumper at the screen's own
//                    vertical length (dataJumpV / powerJumpV);
//       HORIZONTAL - the next cabinet directly beside: same screen, same
//                    row, column +-1. A jumper at the screen's horizontal
//                    length (dataJumpH / powerJumpH);
//       - across a GROUP SEAM (the next cabinet on another member) the same
//         two by where the cabinets sit, not by row / column (each member
//         has its own grid): cabinets that TOUCH edge to edge in the
//         measuring frame below - a shared edge longer than the tolerance,
//         a gap no wider than JUMPER_TOUCH_MM (5 mm, so rounding in the
//         positions never splits a real seam) - are beside (HORIZONTAL) or
//         above / below (VERTICAL), at the SOURCE cabinet's screen's
//         length. Two grouped screens side by side are one wall: a run
//         crossing their seam is a short link like any other ("next
//         cabinet directly above/below = vertical, directly beside =
//         horizontal, anything else = long", 2026-09-25);
//       LONG       - anything else: not touching (a jump back across the
//                    wall, a skip over a hidden cabinet, a hop to a member
//                    that sits apart, a corner-to-corner step). Measured
//                    "center to each panel"
//                    along the panels: |dx| + |dy| between the two
//                    cabinets' centers in real-world units, plus 1 ft of
//                    slack, rounded UP to the next stock length 3, 6, 10,
//                    15, 25 ft. Past 25 ft it rounds up to the next 5 ft
//                    (26 -> 30, 31 -> 35): nobody stocks a 25-plus jumper
//                    in a fixed ladder, so the step is 5 ft from there.
//   * the short lengths are PER SCREEN ("each screen is different"): four
//     layer fields, feet, a number or null. null (a blank field) counts NO
//     cable for that direction - panels that link themselves. A long jump
//     is always counted: it is a cable whatever the panels do.
//   * a NEW screen takes them from Preferences > Sheet & cables: the
//     existing dataJumpLength / powerJumpLength are the VERTICAL defaults,
//     dataJumpLengthH / powerJumpLengthH the horizontal ones - and a
//     preference record with no horizontal key reads the vertical figure, so
//     the shipped default is horizontal = vertical = 6' (predictable: a
//     screen counts every link the same until somebody says otherwise).
//     A file saved before the fields existed reads them as the preferences'
//     values at load; nothing is written back until an edit.
//
// THE MEASURING FRAME. A cabinet's center is its drawn rect's center (the
// panel's x / y / width / height, which already carry half tiles: a half
// column is half as wide, so the center of the next cabinet is where it
// really is), taken into the Show Look frame (showOffsetX / showOffsetY - the
// real-world stage layout; the processor offset where a screen never moved)
// and turned into millimetres by the screen's own pitch: panel_width_mm per
// cabinet_width pixels across, panel_height_mm per cabinet_height pixels
// down. Within one screen that is exact. Between two members of a group the
// pixel distance (and, for the seam test, the gap between the two cabinets'
// facing edges) is read in the same Show Look frame and each axis is scaled
// by the MEAN of the two members' pitches - exact when the members share a
// cabinet (the usual wall), an honest approximation when they do not, since
// the canvas draws both at their pixel sizes. Rotation is not applied: a
// 90-degree turn swaps dx and dy, which leaves |dx| + |dy| as it was.
import { LEDRasterApp } from './app-core.js';

// The stock ladder a long jumper rounds up to, and the slack added first.
const JUMPER_STOCK_FT = [3, 6, 10, 15, 25];
const JUMPER_SLACK_FT = 1;
// Two cabinets on different members TOUCH when the gap between their facing
// edges is at most this many mm (either way - a hair of overlap is a seam
// too) and the edges they share are longer than it.
const JUMPER_TOUCH_MM = 5;
const MM_PER_FT = 304.8;
// The layer fields, per side: [vertical, horizontal].
const JUMPER_FIELDS = {
    data: ['dataJumpV', 'dataJumpH'],
    power: ['powerJumpV', 'powerJumpH'],
};
// The preference keys behind them, the same order.
const JUMPER_PREF_KEYS = {
    data: ['dataJumpLength', 'dataJumpLengthH'],
    power: ['powerJumpLength', 'powerJumpLengthH'],
};
const JUMPER_SHIPPED_FT = 6;

class _Jumpers {

    // ---- lengths ----------------------------------------------------------

    // A jumper length as the fields store it: a positive number of feet, or
    // null (blank, zero, negative or not a number: no cable).
    jumperLengthValue(v) {
        if (v === null || v === undefined) return null;
        if (typeof v === 'string' && v.trim() === '') return null;
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    // A long jump's raw length (feet, slack already in) rounded up to the
    // stock ladder; past its top, up to the next 5 ft.
    jumperStockLength(ft) {
        // A hair of tolerance so a figure that is a stock length on paper
        // (5 ft of panels + 1 = 6) is not pushed a rung by float dust.
        const x = Math.round((Number(ft) || 0) * 1e6) / 1e6;
        for (const s of JUMPER_STOCK_FT) if (x <= s) return s;
        return Math.ceil(x / 5) * 5;
    }

    // The four defaults a NEW screen takes: the preferences (getPreferences
    // already reads a record's vertical figure for a horizontal it never
    // held). A blank preference (null) is kept - new screens then count no
    // cable there.
    jumperDefaults() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const has = (k) => prefs[k] !== undefined;
        const out = {};
        for (const side of Object.keys(JUMPER_FIELDS)) {
            const [vKey, hKey] = JUMPER_PREF_KEYS[side];
            const v = has(vKey) ? this.jumperLengthValue(prefs[vKey]) : JUMPER_SHIPPED_FT;
            const h = has(hKey) ? this.jumperLengthValue(prefs[hKey]) : v;
            out[JUMPER_FIELDS[side][0]] = v;
            out[JUMPER_FIELDS[side][1]] = h;
        }
        return out;
    }

    // A screen's own lengths, { data: { v, h }, power: { v, h } }: its stored
    // field where it has one (null included - a blank is a decision), else
    // the preference (a file saved before the fields existed).
    screenJumperLengths(layer) {
        const defaults = this.jumperDefaults();
        const out = {};
        for (const side of Object.keys(JUMPER_FIELDS)) {
            const [vf, hf] = JUMPER_FIELDS[side];
            const read = (f) => (layer && layer[f] !== undefined)
                ? this.jumperLengthValue(layer[f]) : defaults[f];
            out[side] = { v: read(vf), h: read(hf) };
        }
        return out;
    }

    // Stamp the preferences onto a screen that lacks the fields (a new
    // screen with `force`, or an old file's screen at load). In memory only
    // - nothing is written to the server here.
    applyJumperDefaults(layer, force = false) {
        if (!layer || (layer.type || 'screen') !== 'screen') return;
        const d = this.jumperDefaults();
        for (const f of Object.keys(d)) {
            if (force || layer[f] === undefined) layer[f] = d[f];
        }
    }

    // ---- the link rule ----------------------------------------------------

    // A cabinet's center in the Show Look frame, in pixels, and the screen's
    // pitch (mm per pixel) on each axis - see THE MEASURING FRAME above.
    _jumperCenter(panel, layer) {
        const l = layer || {};
        const w = Number(panel.width) || 0;
        const h = Number(panel.height) || 0;
        const cw = Number(l.cabinet_width) || w || 1;
        const ch = Number(l.cabinet_height) || h || 1;
        const procX = Number(l.offset_x) || 0;
        const procY = Number(l.offset_y) || 0;
        const showX = l.showOffsetX != null ? Number(l.showOffsetX) || 0 : procX;
        const showY = l.showOffsetY != null ? Number(l.showOffsetY) || 0 : procY;
        return {
            x: (Number(panel.x) || 0) - procX + showX + w / 2,
            y: (Number(panel.y) || 0) - procY + showY + h / 2,
            w, h,
            mmx: (Number(l.panel_width_mm) || 500) / cw,
            mmy: (Number(l.panel_height_mm) || 500) / ch,
        };
    }

    // The distance "center to each panel" along the panels between two
    // cabinets, in feet (no slack).
    jumperDistanceFt(a, la, b, lb) {
        const ca = this._jumperCenter(a, la);
        const cb = this._jumperCenter(b, lb || la);
        const mmx = la === lb ? ca.mmx : (ca.mmx + cb.mmx) / 2;
        const mmy = la === lb ? ca.mmy : (ca.mmy + cb.mmy) / 2;
        const mm = Math.abs(cb.x - ca.x) * mmx + Math.abs(cb.y - ca.y) * mmy;
        return mm / MM_PER_FT;
    }

    // How two cabinets on DIFFERENT members meet, in the measuring frame:
    // 'horizontal' (side by side, sharing a vertical edge), 'vertical' (one
    // above the other, sharing a horizontal edge) or null (apart, or only
    // corners meeting). Pixels in the Show Look frame, each axis turned to
    // mm by the mean of the two pitches - the frame jumperDistanceFt reads.
    jumperSeam(a, la, b, lb) {
        const ca = this._jumperCenter(a, la);
        const cb = this._jumperCenter(b, lb);
        const mmx = (ca.mmx + cb.mmx) / 2;
        const mmy = (ca.mmy + cb.mmy) / 2;
        const span = (c, axis) => axis === 'x'
            ? [c.x - c.w / 2, c.x + c.w / 2] : [c.y - c.h / 2, c.y + c.h / 2];
        // gap between the facing edges (negative: they overlap), and the
        // length both share along the other axis - in mm
        const gap = (axis, mm) => {
            const [a1, a2] = span(ca, axis), [b1, b2] = span(cb, axis);
            return Math.max(b1 - a2, a1 - b2) * mm;
        };
        const shared = (axis, mm) => {
            const [a1, a2] = span(ca, axis), [b1, b2] = span(cb, axis);
            return (Math.min(a2, b2) - Math.max(a1, b1)) * mm;
        };
        const tol = JUMPER_TOUCH_MM;
        const gx = gap('x', mmx), gy = gap('y', mmy);
        const sx = shared('x', mmx), sy = shared('y', mmy);
        if (Math.abs(gx) <= tol && sy > tol) return 'horizontal';
        if (Math.abs(gy) <= tol && sx > tol) return 'vertical';
        return null;
    }

    // One link, cabinet `a` (on screen `la`) to cabinet `b` (on `lb`), on the
    // data or power side: { kind: 'vertical' | 'horizontal' | 'long', ft }
    // where ft is the jumper's length in feet, or null for a short link the
    // screen counts no cable on.
    jumperLink(a, la, b, lb, side = 'data') {
        const same = (la || null) === (lb || null);
        if (same && a && b) {
            const dr = Math.abs((a.row | 0) - (b.row | 0));
            const dc = Math.abs((a.col | 0) - (b.col | 0));
            if ((dr === 1 && dc === 0) || (dr === 0 && dc === 1)) {
                const lengths = this.screenJumperLengths(la)[side] || { v: null, h: null };
                return dr === 1
                    ? { kind: 'vertical', ft: lengths.v }
                    : { kind: 'horizontal', ft: lengths.h };
            }
        } else if (a && b) {
            // a group seam: short when the two cabinets touch, at the
            // SOURCE cabinet's screen's length
            const seam = this.jumperSeam(a, la, b, lb);
            if (seam) {
                const lengths = this.screenJumperLengths(la)[side] || { v: null, h: null };
                return seam === 'vertical'
                    ? { kind: 'vertical', ft: lengths.v }
                    : { kind: 'horizontal', ft: lengths.h };
            }
        }
        const raw = this.jumperDistanceFt(a, la, b, lb) + JUMPER_SLACK_FT;
        return { kind: 'long', ft: this.jumperStockLength(raw), rawFt: raw };
    }

    // Every link of one run, in order: [{ a, b, la, lb, kind, ft }]. `layers`
    // is index-aligned with `panels` (a crossing run's own member per
    // cabinet); absent, every cabinet is on `owner`.
    jumperLinksOfRun(panels, layers, owner, side = 'data') {
        const out = [];
        for (let i = 1; i < (panels || []).length; i++) {
            const a = panels[i - 1], b = panels[i];
            if (!a || !b) continue;
            const la = (layers && layers[i - 1]) || owner;
            const lb = (layers && layers[i]) || owner;
            out.push({ a, b, la, lb, ...this.jumperLink(a, la, b, lb, side) });
        }
        return out;
    }

    // The runs of a screen on one side, as [{ panels, layers }]: the data
    // ports (the pull list's own reading), or each BRANCH of each circuit
    // (a 2fer's runs are separate daisies from the fan-out).
    screenJumperRuns(layer, side) {
        if (!layer) return [];
        if (side === 'data') {
            return (typeof this._pullPortRuns === 'function' ? this._pullPortRuns(layer) : [])
                .map(r => ({ panels: r.panels, layers: r.layers }));
        }
        const out = [];
        const circuits = typeof this.screenCircuits === 'function' ? this.screenCircuits(layer) : [];
        for (const c of circuits) {
            const runs = Array.isArray(c.branches) && c.branches.length ? c.branches : [c.panels];
            let off = 0;
            for (const run of runs) {
                const layers = c.layers ? c.layers.slice(off, off + run.length) : null;
                off += run.length;
                out.push({ panels: run, layers, num: c.num });
            }
        }
        return out;
    }

    // The LONG links of a screen for its map's tags: panel -> (next panel ->
    // feet). Keyed by the cabinet objects themselves, so a drawn pair looks
    // itself up (a cross-member shim through its srcPanel).
    jumperLongLinkMap(layer, side) {
        const map = new Map();
        for (const run of this.screenJumperRuns(layer, side)) {
            for (const link of this.jumperLinksOfRun(run.panels, run.layers, layer, side)) {
                if (link.kind !== 'long' || link.ft == null) continue;
                let inner = map.get(link.a);
                if (!inner) { inner = new Map(); map.set(link.a, inner); }
                inner.set(link.b, link.ft);
            }
        }
        return map;
    }

    // ---- the sidebar's Jumpers row ------------------------------------------

    // The two fields of each side, multi-select aware the way the other
    // sidebar fields are: every selected screen agreeing shows its figure
    // (blank, placeholder "none", for no cable), screens that differ show a
    // blank with "-".
    syncJumperControls(layers) {
        const list = (layers || []).filter(l => l && (l.type || 'screen') === 'screen');
        if (!list.length) return;
        const ids = { dataJumpV: 'data-jump-v', dataJumpH: 'data-jump-h',
                      powerJumpV: 'power-jump-v', powerJumpH: 'power-jump-h' };
        const read = (l) => {
            const r = this.screenJumperLengths(l);
            return { dataJumpV: r.data.v, dataJumpH: r.data.h, powerJumpV: r.power.v, powerJumpH: r.power.h };
        };
        const all = list.map(read);
        for (const [field, id] of Object.entries(ids)) {
            const el = document.getElementById(id);
            if (!el || document.activeElement === el) continue;
            const first = all[0][field];
            const mixed = all.some(r => r[field] !== first);
            el.classList.remove('invalid');
            if (mixed) { el.value = ''; el.placeholder = '-'; }
            else { el.value = first == null ? '' : String(first); el.placeholder = 'none'; }
        }
    }

    // Wired once from _wirePowerPanel. A commit writes every selected screen
    // (never its group peers: the lengths are per screen), one history entry,
    // one PUT batch; a figure every selected screen already holds commits
    // nothing. Blank is null (no cable); anything else must be a positive
    // number of feet, or the field is flagged and nothing is written.
    initJumperControls() {
        if (this._jumperControlsWired) return;
        this._jumperControlsWired = true;
        const bind = (id, field, action) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => {
                const raw = String(el.value == null ? '' : el.value).trim();
                let val = null;
                if (raw !== '') {
                    const n = typeof this.evaluateNumericExpression === 'function'
                        ? this.evaluateNumericExpression(raw) : parseFloat(raw);
                    if (!(Number.isFinite(n) && n > 0)) {
                        el.classList.add('invalid');
                        return;
                    }
                    val = n;
                }
                el.classList.remove('invalid');
                const selected = this.getSelectedLayers()
                    .filter(l => l && (l.type || 'screen') === 'screen');
                if (!selected.some(l => l[field] !== val)) return;
                selected.forEach(l => { l[field] = val; });
                this.saveClientSideProperties();
                this.updateLayers(selected, true, action);
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        };
        bind('data-jump-v', 'dataJumpV', 'Set Data Jumper Vertical');
        bind('data-jump-h', 'dataJumpH', 'Set Data Jumper Horizontal');
        bind('power-jump-v', 'powerJumpV', 'Set Power Jumper Vertical');
        bind('power-jump-h', 'powerJumpH', 'Set Power Jumper Horizontal');
    }
}

for (const k of Object.getOwnPropertyNames(_Jumpers.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Jumpers.prototype, k));
    }
}
