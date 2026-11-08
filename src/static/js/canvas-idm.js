// canvas.js mixin: the IDM Locator view - every screen in one solid field
// colour with its module and cabinet borders, the modules marked bad, the
// live highlight, and the hit test that finds the module under the pointer.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
//
// The view stands the cabinets where the Pixel Map does (render() runs the
// Pixel Map pass with _idmPass set; canvas.js) - the processor raster
// Output to Display puts on the wall - but draws the field in place of the
// Pixel Map's pattern, labels and test pattern. Each screen's block is
// `layer.idm` (app.sanitize_idm on the server holds the shape;
// app-idm-locator.js edits it):
//   {modulesX, modulesY, marks: {"col,row,mx,my": {style, color}}}
// A module is the cabinet's pixels / modules, the remainder spread so no
// module is a fractional pixel: edges at floor(k * px / n). A half cabinet
// keeps the modules that fall inside it, the full cabinet laid from the side
// that meets the wall (the cut is on the free edge). A blanked cabinet has
// none. The geometry here is the server's idm_module_cells line for line.
const IDM_MAX_MODULES = 64;
const IDM_FIELD_DEFAULT_COLOR = '#ffffff';
const IDM_FIELD_BORDERS = ['shade', 'lines', 'ticks', 'none'];
// The shade style: alternate modules at 85% of the field, the cabinet's
// outer pixel ring at 65%.
const IDM_SHADE_ALT = 0.85;
const IDM_SHADE_RING = 0.65;
// Lines, ticks and Module ID numbers: the field's hue at these shares - 50%
// for cabinet edges and the numbers, 70% for module edges. A field whose
// brightest channel is under IDM_DARK_MAX counts as black (lit greys then).
const IDM_INK_CABINET = 0.5;
const IDM_INK_MODULE = 0.7;
const IDM_DARK_MAX = 40;
// How far apart (RGB distance) a mark and the field must be for the mark to
// keep its own colour on the wall.
const IDM_MARK_MIN_DISTANCE = 110;
// Module ID labels: the type's size as a share of a full module's smaller
// side (centred, and the smaller corner label), the corner label's stand-off
// from the module's edge, and the least size in bitmap pixels a label is
// drawn at - below it no module on that screen is numbered (a smear reads
// as nothing and would run into its neighbours).
const IDM_MODULE_ID_CENTRE = 0.5;
const IDM_MODULE_ID_CORNER = 0.3;
const IDM_MODULE_ID_INSET = 0.1;
const IDM_MODULE_ID_FLOOR_PX = 8;

Object.assign(CanvasRenderer.prototype, {
    // Modules across and down in one cabinet of `layer`: integers 1..64.
    idmCounts(layer) {
        const count = (v) => {
            if (typeof v === 'boolean' || v === null || v === undefined) return 1;
            const n = Number(v);
            if (!Number.isFinite(n)) return 1;
            return Math.max(1, Math.min(IDM_MAX_MODULES, Math.trunc(n)));
        };
        const idm = (layer && layer.idm && typeof layer.idm === 'object') ? layer.idm : {};
        return { x: count(idm.modulesX), y: count(idm.modulesY) };
    },

    // (row, col) -> is there a shown cabinet there. The half-cabinet anchor
    // reads its neighbours the way _build_panels does (hidden only).
    _idmVisibleLookup(layer) {
        const shown = new Set();
        ((layer && layer.panels) || []).forEach(p => {
            if (p && !p.hidden) shown.add(`${p.row || 0},${p.col || 0}`);
        });
        return (r, c) => shown.has(`${r},${c}`);
    },

    // One cabinet's modules as [{mx, my, x, y, w, h}] in the screen's own
    // (processor) pixels, clipped to the cabinet as drawn.
    idmModuleCells(layer, panel, modulesX, modulesY, visibleAt) {
        if (!layer || !panel || panel.hidden || panel.blank) return [];
        const fullW = Math.round(Number(layer.cabinet_width) || 0);
        const fullH = Math.round(Number(layer.cabinet_height) || 0);
        if (fullW <= 0 || fullH <= 0) return [];
        const px = Number(panel.x) || 0, py = Number(panel.y) || 0;
        const pw = Number(panel.width) || 0, ph = Number(panel.height) || 0;
        if (pw <= 0 || ph <= 0) return [];
        const row = panel.row || 0, col = panel.col || 0;
        const seen = visibleAt || (() => false);
        let ox = px, oy = py;
        if (panel.halfTile === 'width' && pw < fullW && !seen(row, col - 1) && seen(row, col + 1)) {
            ox = px + pw - fullW;
        }
        if (panel.halfTile === 'height' && ph < fullH && !seen(row - 1, col) && seen(row + 1, col)) {
            oy = py + ph - fullH;
        }
        const edges = (total, n) => {
            const out = [];
            for (let k = 0; k <= n; k++) out.push(Math.floor(total * k / n));
            return out;
        };
        const ex = edges(fullW, modulesX);
        const ey = edges(fullH, modulesY);
        const cells = [];
        for (let my = 0; my < modulesY; my++) {
            const y0 = Math.max(py, oy + ey[my]);
            const y1 = Math.min(py + ph, oy + ey[my + 1]);
            if (y1 - y0 <= 1e-6) continue;
            for (let mx = 0; mx < modulesX; mx++) {
                const x0 = Math.max(px, ox + ex[mx]);
                const x1 = Math.min(px + pw, ox + ex[mx + 1]);
                if (x1 - x0 <= 1e-6) continue;
                cells.push({ mx, my, x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
            }
        }
        return cells;
    },

    idmCellKey(panel, cell) {
        return `${panel.col || 0},${panel.row || 0},${cell.mx},${cell.my}`;
    },

    // A module's label, as the Module ID labels, the locator list and the
    // highlight readout all print it - one function, so the three never
    // disagree. It is the screen's Cabinet ID style (cabinetIdFormat, the
    // Cabinet ID tab's setting) applied to the cabinet's own module grid,
    // starting again in every cabinet: in A1, B1 style a 2 x 2 cabinet
    // reads A1 B1 / A2 B2, in A1, A2 style A1 A2 / B1 B2, in 1,1 style
    // 1,1 1,2 / 2,1 2,2; any other style numbers the modules 1.. row by
    // row. The position is the module's in the FULL cabinet grid, seen
    // from the front (the screen as built, before any Pixel Map rotation),
    // so a half cabinet's modules read as the same modules of a whole one.
    // Returns cell -> text.
    idmModuleLabeler(layer) {
        const style = (layer && layer.cabinetIdStyle) || 'column-row';
        const counts = this.idmCounts(layer);
        return (cell) => this.cabinetIdFormat(style, cell.my, cell.mx, cell.my * counts.x + cell.mx + 1);
    },

    // Every cabinet of `layer` with its modules: [{panel, cells}].
    idmLayerCells(layer) {
        const counts = this.idmCounts(layer);
        const seen = this._idmVisibleLookup(layer);
        return ((layer && layer.panels) || []).map(panel => ({
            panel, cells: this.idmModuleCells(layer, panel, counts.x, counts.y, seen),
        }));
    },

    // ── the field ───────────────────────────────────────────────────────
    //
    // The tab draws every screen in ONE solid colour, the crew's dead-pixel
    // and bad-module check on the real wall, with a border style that says
    // where modules and cabinets meet. The project keeps it as
    //   idmField: {color: '#rrggbb', border: 'shade' | 'lines' | 'ticks' | 'none'}
    // (app.sanitize_idm_field; white with shaded borders when missing), and
    // moduleIds: true numbers every module (_idmDrawModuleIds).
    // What is drawn here goes into the raster - the output window gets
    // exactly this - except the on-screen grid (designer only, never in an
    // export pass) and the accent outline round the live highlight.
    //
    // Borders, all one LED pixel wide on the wall:
    //   shade  every pixel stays lit. Modules alternate full colour and 85%
    //          in a checker across the whole screen (a module edge reads as
    //          a brightness step), and each cabinet's outermost pixel ring
    //          is drawn at 65% - a thin darker line no module edge has, so
    //          a cabinet edge reads as a line and a module edge as a step.
    //          On a black (or nearly black) field the levels go UP instead:
    //          very dark grey modules, a slightly lighter cabinet ring.
    //   lines  a 1 px line at every module edge at 70% of the field, the
    //          cabinet's outer ring at 50%.
    //   ticks  short L ticks in each module's corners (length scaled to the
    //          module) at 70%, longer and 2 px thick at each cabinet's
    //          corners at 50%.
    //   none   the field alone.
    // Nothing drawn into the field is ever black on Auto: an unlit pixel
    // inside a line or a number would hide a dead one, or pass for one, and
    // dead pixels are what the crew is looking for. Lines, ticks and the
    // Module ID numbers are the field's own hue, dimmer (idmInkLevels); on a
    // black (or nearly black) field they are lit greys instead.
    //
    // The Colours (one set for the show, each missing = Auto, the levels
    // above): labelColor, moduleEdgeColor, cabinetEdgeColor ('#rrggbb') and
    // shade ('#rrggbb' or a percent of the field) - a colour the crew chose
    // is drawn as chosen, black included (the panel warns about black).
    idmFieldSpec() {
        const app = window.app;
        const raw = (app && app.project && app.project.idmField && typeof app.project.idmField === 'object')
            ? app.project.idmField : {};
        const hex = this._idmHexOrNull(raw.color) || IDM_FIELD_DEFAULT_COLOR;
        const border = IDM_FIELD_BORDERS.includes(raw.border) ? raw.border : 'shade';
        return {
            color: hex, border, rgb: this._idmRgb(hex), moduleIds: raw.moduleIds === true,
            labelColor: this._idmHexOrNull(raw.labelColor),
            moduleEdgeColor: this._idmHexOrNull(raw.moduleEdgeColor),
            cabinetEdgeColor: this._idmHexOrNull(raw.cabinetEdgeColor),
            shade: this._idmShadeOrNull(raw.shade),
        };
    },

    // The shade setting held to its shape: '#rrggbb', a whole percent
    // 0..100, or null (Auto) - app.idm_shade_level's twin.
    _idmShadeOrNull(value) {
        if (typeof value === 'number') {
            if (!Number.isFinite(value) || value < 0 || value > 100) return null;
            return Math.floor(value + 0.5);
        }
        return this._idmHexOrNull(value);
    },

    // What the field's borders are drawn in, the Colours applied over the
    // Auto levels: {alt, ring} for the shade style (the alternate modules,
    // the cabinet ring), {module, cabinet} for lines and ticks.
    idmBorderInks(field) {
        const F = field.rgb;
        const shade = this.idmShadeLevels(F);
        const ink = this.idmInkLevels(F);
        const pick = (hex, auto) => (hex ? this._idmRgb(hex) : auto);
        let alt = shade.alt;
        if (typeof field.shade === 'number') alt = F.map(v => Math.round(v * field.shade / 100));
        else if (field.shade) alt = this._idmRgb(field.shade);
        return {
            alt,
            ring: pick(field.cabinetEdgeColor, shade.ring),
            module: pick(field.moduleEdgeColor, ink.module),
            cabinet: pick(field.cabinetEdgeColor, ink.cabinet),
        };
    },

    _idmHexOrNull(value) {
        if (typeof value !== 'string') return null;
        const text = value.trim();
        let m = /^#?([0-9a-fA-F]{6})$/.exec(text);
        if (m) return '#' + m[1].toLowerCase();
        m = /^#?([0-9a-fA-F]{3})$/.exec(text);
        if (m) return '#' + m[1].split('').map(c => c + c).join('').toLowerCase();
        return null;
    },

    _idmRgb(hex) {
        const h = this._idmHexOrNull(hex) || '#000000';
        return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
    },

    _idmCss(rgb) {
        return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
    },

    // Black on a light field, white on a dark one.
    idmContrastRgb(rgb) {
        const y = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
        return y > 140 ? [0, 0, 0] : [255, 255, 255];
    },

    _idmDistance(a, b) {
        return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    },

    // The shade style's two other levels: the alternate modules' and the
    // cabinet ring's. Darker than the field, or on a (nearly) black field
    // lighter, so every pixel stays lit either way.
    idmShadeLevels(rgb) {
        const dark = Math.max(rgb[0], rgb[1], rgb[2]) < IDM_DARK_MAX;
        const lift = (k) => rgb.map(v => Math.min(255, v + k));
        const dim = (f) => rgb.map(v => Math.round(v * f));
        return dark
            ? { alt: lift(26), ring: lift(52) }
            : { alt: dim(IDM_SHADE_ALT), ring: dim(IDM_SHADE_RING) };
    },

    // What lines, ticks and Module ID numbers are drawn in on a field (or a
    // colour mark) of `rgb`: the same hue at 50% (cabinet edges, numbers)
    // and 70% (module edges) - every pixel lit. On a black or nearly black
    // field, where half is still dark, lit greys: 40% for the cabinet and
    // the numbers, 20% for the modules.
    idmInkLevels(rgb) {
        if (Math.max(rgb[0], rgb[1], rgb[2]) < IDM_DARK_MAX) {
            return { cabinet: [102, 102, 102], module: [51, 51, 51] };
        }
        const dim = (f) => rgb.map(v => Math.round(v * f));
        return { cabinet: dim(IDM_INK_CABINET), module: dim(IDM_INK_MODULE) };
    },

    // The colour a mark is DRAWN in: its own, unless that is too close to
    // the field to see (a red mark on a red field) - then the contrasting
    // colour. The stored colour never changes.
    idmMarkInk(color, fieldRgb) {
        const own = this._idmHexOrNull(color) || '#ff1a1a';
        if (this._idmDistance(this._idmRgb(own), fieldRgb) >= IDM_MARK_MIN_DISTANCE) return own;
        return this._idmCss(this.idmContrastRgb(fieldRgb));
    },

    // idmMarkInk as [r, g, b].
    _idmMarkInkRgb(color, fieldRgb) {
        const own = this._idmRgb(this._idmHexOrNull(color) || '#ff1a1a');
        return this._idmDistance(own, fieldRgb) >= IDM_MARK_MIN_DISTANCE ? own : this.idmContrastRgb(fieldRgb);
    },

    // The shade style's checker: true for a module drawn at the alternate
    // level. It runs across the whole screen, cabinet after cabinet.
    _idmIsAlt(panel, cell, counts) {
        const gx0 = (panel.col || 0) * counts.x, gy0 = (panel.row || 0) * counts.y;
        return (gx0 + cell.mx + gy0 + cell.my) % 2 === 1;
    },

    // The live highlight blinks between full white and this: the field's
    // inverse, or black when the inverse is itself near white (a black or
    // near-black field), so it blinks on any field.
    idmHighlightOffRgb(fieldRgb) {
        const inv = fieldRgb.map(v => 255 - v);
        return this._idmDistance(inv, [255, 255, 255]) < IDM_MARK_MIN_DISTANCE ? [0, 0, 0] : inv;
    },

    // A ring `t` px thick inside a rectangle (fills, so it sits on whole
    // pixels).
    _idmRing(ctx, x, y, w, h, t) {
        if (w <= 0 || h <= 0) return;
        const tt = Math.min(t, w / 2, h / 2);
        ctx.fillRect(x, y, w, tt);
        ctx.fillRect(x, y + h - tt, w, tt);
        ctx.fillRect(x, y, tt, h);
        ctx.fillRect(x + w - tt, y, tt, h);
    },

    // An L in one corner of a rectangle: `sx`/`sy` say which corner (+1 the
    // left/top, -1 the right/bottom).
    _idmTick(ctx, cx, cy, sx, sy, len, t) {
        ctx.fillRect(sx > 0 ? cx : cx - len, sy > 0 ? cy : cy - t, len, t);
        ctx.fillRect(sx > 0 ? cx : cx - t, sy > 0 ? cy : cy - len, t, len);
    },

    _idmTicks(ctx, x, y, w, h, len, t) {
        const L = Math.max(1, Math.min(len, Math.floor(w / 2), Math.floor(h / 2)));
        const T = Math.max(1, Math.min(t, L));
        this._idmTick(ctx, x, y, 1, 1, L, T);
        this._idmTick(ctx, x + w, y, -1, 1, L, T);
        this._idmTick(ctx, x, y + h, 1, -1, L, T);
        this._idmTick(ctx, x + w, y + h, -1, -1, L, T);
    },

    // One cabinet's field and border style (inside the panel's clip).
    _idmDrawField(ctx, panel, cells, counts, field) {
        const F = field.rgb;
        ctx.fillStyle = this._idmCss(F);
        ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        if (field.border === 'shade') {
            const lv = this.idmBorderInks(field);
            ctx.fillStyle = this._idmCss(lv.alt);
            for (const c of cells) {
                if (this._idmIsAlt(panel, c, counts)) ctx.fillRect(c.x, c.y, c.w, c.h);
            }
            ctx.fillStyle = this._idmCss(lv.ring);
            this._idmRing(ctx, panel.x, panel.y, panel.width, panel.height, 1);
        } else if (field.border === 'lines') {
            const ink = this.idmBorderInks(field);
            ctx.fillStyle = this._idmCss(ink.module);
            const xs = new Set(), ys = new Set();
            for (const c of cells) {
                if (c.x > panel.x + 1e-6) xs.add(c.x);
                if (c.y > panel.y + 1e-6) ys.add(c.y);
            }
            xs.forEach(x => ctx.fillRect(x, panel.y, 1, panel.height));
            ys.forEach(y => ctx.fillRect(panel.x, y, panel.width, 1));
            ctx.fillStyle = this._idmCss(ink.cabinet);
            this._idmRing(ctx, panel.x, panel.y, panel.width, panel.height, 1);
        } else if (field.border === 'ticks') {
            const ink = this.idmBorderInks(field);
            ctx.fillStyle = this._idmCss(ink.module);
            for (const c of cells) {
                const len = Math.max(2, Math.min(16, Math.round(Math.min(c.w, c.h) * 0.15)));
                this._idmTicks(ctx, c.x, c.y, c.w, c.h, len, 1);
            }
            ctx.fillStyle = this._idmCss(ink.cabinet);
            const cab = Math.max(3, Math.min(32, Math.round(Math.min(panel.width, panel.height) * 0.12)));
            this._idmTicks(ctx, panel.x, panel.y, panel.width, panel.height, cab, 2);
        }
    },

    // A mark in its cell: a fill, or an X corner to corner. `inset` (0..0.5)
    // draws a fill smaller than the module (the live highlight's centre).
    _idmDrawMark(ctx, c, mark, ink, unit, inset = 0) {
        if (mark.style === 'x') {
            ctx.save();
            ctx.beginPath();
            ctx.rect(c.x, c.y, c.w, c.h);
            ctx.clip();
            ctx.strokeStyle = ink;
            ctx.lineCap = 'square';
            ctx.lineWidth = Math.max(2 * unit, Math.round(Math.min(c.w, c.h) / 10));
            ctx.beginPath();
            ctx.moveTo(c.x, c.y);
            ctx.lineTo(c.x + c.w, c.y + c.h);
            ctx.moveTo(c.x + c.w, c.y);
            ctx.lineTo(c.x, c.y + c.h);
            ctx.stroke();
            ctx.restore();
        } else {
            ctx.fillStyle = ink;
            ctx.fillRect(c.x + c.w * inset, c.y + c.h * inset, c.w * (1 - 2 * inset), c.h * (1 - 2 * inset));
        }
    },

    // ── Module ID labels ────────────────────────────────────────────────
    //
    // With idmField.moduleIds on, every module carries its label - the
    // Cabinet ID style run over the cabinet's module grid (idmModuleLabeler),
    // the locator list's and the highlight readout's own "Module A2" - in
    // the app and on the wall. Placed where the screen's Cabinet ID labels
    // are (its cabinetIdPosition: centred, or the top-left corner), in the
    // project font the Cabinet ID view uses, one size per screen scaled to
    // a full module (a share of its smaller side, pulled in until the
    // widest label of a whole cabinet fits) and floored to whole bitmap
    // pixels so the wall's type is crisp. Under IDM_MODULE_ID_FLOOR_PX on
    // the bitmap nothing is labelled; a module with no room for its label
    // at that size (a half cabinet's sliver) goes without. Never black (see
    // the field above): the field's hue at 50% (idmInkLevels), or on a
    // colour mark the mark's. Drawn in the screen's own frame, so a turned
    // screen's labels turn with it as its Cabinet IDs do; the live
    // highlight is drawn over them.

    // The labels of one screen, worked out but not drawn: {px, position,
    // sites: [{key, text, x, y, w, h, ascent, left, right, color}]} with
    // each label's ink box (x, y, w, h) in the screen's own frame. px 0
    // and no sites when the switch is off or the size is under the floor.
    // opts.scale: bitmap px per world unit (read off the ctx otherwise).
    idmModuleLabels(layer, opts = {}) {
        const out = { px: 0, position: 'center', sites: [] };
        const field = opts.field || this.idmFieldSpec();
        if (!field.moduleIds || !layer || (layer.type || 'screen') !== 'screen' || !Array.isArray(layer.panels)) return out;
        const ctx = opts.ctx || this.ctx;
        let scale = Number(opts.scale);
        if (!(scale > 0)) {
            try {
                const m = ctx.getTransform();
                scale = Math.hypot(m.a, m.b) || 1;
            } catch (_) { scale = 1; }
        }
        const counts = this.idmCounts(layer);
        const fullW = Math.round(Number(layer.cabinet_width) || 0);
        const fullH = Math.round(Number(layer.cabinet_height) || 0);
        const modW = Math.floor(fullW / counts.x), modH = Math.floor(fullH / counts.y);
        const side = Math.min(modW, modH);
        if (!(side > 0)) return out;
        const centred = layer.cabinetIdPosition !== 'top-left';
        out.position = centred ? 'center' : 'top-left';
        const inset = centred ? 0 : Math.max(3, Math.round(IDM_MODULE_ID_INSET * side));
        const groups = this.idmLayerCells(layer);
        if (!groups.some(g => g.cells.length)) return out;
        const labelOf = this.idmModuleLabeler(layer);
        const family = projectFontFamily();
        const marks = (layer.idm && layer.idm.marks && typeof layer.idm.marks === 'object') ? layer.idm.marks : {};
        // The Colours' label colour, when chosen, everywhere (marks too);
        // Auto is the field's hue at 50%, on a colour mark the mark's.
        const chosen = field.labelColor ? this._idmRgb(field.labelColor) : null;
        const fieldInk = chosen || this.idmInkLevels(field.rgb).cabinet;
        ctx.save();
        try {
            // Type scales with its size, so one measurement at a reference
            // size gives every size: the widest label of a whole cabinet and
            // the labels' height, per px.
            const metrics = this._idmLabelMetrics(ctx, family, layer, counts, labelOf);
            const perW = metrics.w, perA = metrics.a, perD = metrics.d;
            const roomW = centred ? modW * 0.8 : modW - 2 * inset;
            const roomH = centred ? modH * 0.8 : modH - 2 * inset;
            let px = side * (centred ? IDM_MODULE_ID_CENTRE : IDM_MODULE_ID_CORNER);
            if (perW > 0) px = Math.min(px, roomW / perW);
            if (perA + perD > 0) px = Math.min(px, roomH / (perA + perD));
            px = Math.floor(px * scale) / scale;
            if (!(px * scale >= IDM_MODULE_ID_FLOOR_PX)) return out;
            out.px = px;
            ctx.font = `bold ${px}px ${family}`;
            const A = perA * px, H = (perA + perD) * px;
            const seen = new Map();
            const measure = (text) => {
                let m = seen.get(text);
                if (!m) {
                    const r = ctx.measureText(text);
                    const l = Number.isFinite(r.actualBoundingBoxLeft) ? r.actualBoundingBoxLeft : 0;
                    const rt = Number.isFinite(r.actualBoundingBoxRight) ? r.actualBoundingBoxRight : r.width;
                    m = { l, r: rt, w: l + rt };
                    seen.set(text, m);
                }
                return m;
            };
            for (const { panel, cells } of groups) {
                for (const c of cells) {
                    const text = labelOf(c);
                    const m = measure(text);
                    const x = centred ? c.x + (c.w - m.w) / 2 : c.x + inset;
                    const y = centred ? c.y + (c.h - H) / 2 : c.y + inset;
                    if (x < c.x || y < c.y || x + m.w > c.x + c.w - (centred ? 0 : 1)
                        || y + H > c.y + c.h - (centred ? 0 : 1)) continue;
                    const key = this.idmCellKey(panel, c);
                    const mark = marks[key];
                    const ink = (!chosen && mark && mark.style !== 'x')
                        ? this.idmInkLevels(this._idmMarkInkRgb(mark.color, field.rgb)).cabinet : fieldInk;
                    out.sites.push({
                        key, text, x, y, w: m.w, h: H, ascent: A, left: m.l, right: m.r,
                        color: this._idmCss(ink),
                    });
                }
            }
        } finally {
            ctx.restore();
        }
        return out;
    },

    // Per px of type: the widest label a whole cabinet of `layer` carries
    // and the labels' ascent and descent. Kept for the font, style and
    // module grid it was measured for (labels are the same in every
    // cabinet), so a redraw measures nothing.
    _idmLabelMetrics(ctx, family, layer, counts, labelOf) {
        const style = layer.cabinetIdStyle || 'column-row';
        const key = `${family}|${style}|${counts.x}|${counts.y}`;
        if (this._idmLabelMetricsKey === key && this._idmLabelMetricsVal) return this._idmLabelMetricsVal;
        const REF = 100;
        ctx.font = `bold ${REF}px ${family}`;
        let w = 0;
        const chars = new Set();
        for (let my = 0; my < counts.y; my++) {
            for (let mx = 0; mx < counts.x; mx++) {
                const text = labelOf({ mx, my });
                w = Math.max(w, ctx.measureText(text).width);
                for (const ch of text) chars.add(ch);
            }
        }
        const dm = ctx.measureText([...chars].join('') || '0');
        const a = Number.isFinite(dm.actualBoundingBoxAscent) ? dm.actualBoundingBoxAscent : 0.72 * REF;
        const d = Number.isFinite(dm.actualBoundingBoxDescent) ? Math.max(0, dm.actualBoundingBoxDescent) : 0;
        this._idmLabelMetricsKey = key;
        this._idmLabelMetricsVal = { w: w / REF, a: a / REF, d: d / REF };
        return this._idmLabelMetricsVal;
    },

    _idmDrawModuleIds(ctx, layer, field) {
        const L = this.idmModuleLabels(layer, { field, ctx });
        if (!L.sites.length) return;
        ctx.save();
        ctx.font = `bold ${L.px}px ${projectFontFamily()}`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        let colour = null;
        for (const s of L.sites) {
            if (s.color !== colour) {
                colour = s.color;
                ctx.fillStyle = colour;
            }
            // The anchor puts the ink on its box, on a whole pixel on the
            // wall. A mirrored canvas has _fillText turn the type about the
            // anchor, so there the anchor is the box's other side.
            const ax = this._mirror ? s.x + s.right : s.x + s.left;
            this._fillText(s.text, this.snap(ax), this.snap(s.y + s.ascent));
        }
        ctx.restore();
    },

    // Drawn inside the screen's own frame (its offset and Pixel Map rotation
    // applied by render()), in place of the Pixel Map's cabinets: the field
    // and its borders, the marks, then - on screen only - the module grid
    // and the cabinet edges, which never reach the output. Line widths of
    // the on-screen grid are one screen pixel or more whatever the zoom.
    renderIdmLayer(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen' || !Array.isArray(layer.panels)) return;
        const ctx = this.ctx;
        const onScreen = !this.exportMode;
        const marks = (layer.idm && layer.idm.marks && typeof layer.idm.marks === 'object')
            ? layer.idm.marks : {};
        const field = this.idmFieldSpec();
        const counts = this.idmCounts(layer);
        const unit = onScreen ? Math.max(1, 1 / (this.zoom || 1)) : 1;
        const flash = (onScreen && window.app && typeof window.app._idmFlashFor === 'function')
            ? window.app._idmFlashFor(layer) : null;
        ctx.save();
        this._clipToActiveRaster();
        for (const { panel, cells } of this.idmLayerCells(layer)) {
            if (!cells.length) {
                // A blanked cabinet puts nothing on the wall; the designer
                // shows where it is, the way the Pixel Map does.
                if (onScreen && panel && (panel.hidden || panel.blank)) {
                    ctx.save();
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
                    ctx.lineWidth = unit;
                    ctx.setLineDash([5 * unit, 5 * unit]);
                    ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
                    ctx.restore();
                }
                continue;
            }
            ctx.save();
            ctx.beginPath();
            ctx.rect(panel.x, panel.y, panel.width, panel.height);
            ctx.clip();
            this._idmDrawField(ctx, panel, cells, counts, field);
            for (const c of cells) {
                const m = marks[this.idmCellKey(panel, c)];
                if (m) this._idmDrawMark(ctx, c, m, this.idmMarkInk(m.color, field.rgb), unit);
            }
            if (onScreen) {
                // The on-screen grid: a dark band with a light core, so it
                // reads on any field colour. Module lines thin, the
                // cabinet's own edge stronger.
                const xs = new Set(), ys = new Set();
                for (const c of cells) {
                    if (c.x > panel.x + 1e-6) xs.add(c.x);
                    if (c.y > panel.y + 1e-6) ys.add(c.y);
                }
                if (xs.size || ys.size) {
                    const path = () => {
                        ctx.beginPath();
                        xs.forEach(x => { ctx.moveTo(x, panel.y); ctx.lineTo(x, panel.y + panel.height); });
                        ys.forEach(y => { ctx.moveTo(panel.x, y); ctx.lineTo(panel.x + panel.width, y); });
                    };
                    path();
                    ctx.strokeStyle = 'rgba(0, 0, 0, 0.45)';
                    ctx.lineWidth = 3 * unit;
                    ctx.stroke();
                    path();
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.75)';
                    ctx.lineWidth = unit;
                    ctx.stroke();
                }
                const inset = 1.5 * unit;
                const rect = [panel.x + inset, panel.y + inset,
                    Math.max(0, panel.width - 2 * inset), Math.max(0, panel.height - 2 * inset)];
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
                ctx.lineWidth = 3 * unit;
                ctx.strokeRect(...rect);
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
                ctx.lineWidth = 1.5 * unit;
                ctx.strokeRect(...rect);
                // A module picked from the locator list blinks in the accent.
                if (flash) {
                    for (const c of cells) {
                        if (this.idmCellKey(panel, c) !== flash.key) continue;
                        ctx.strokeStyle = flash.colour;
                        ctx.lineWidth = 4 * unit;
                        ctx.strokeRect(c.x + 2 * unit, c.y + 2 * unit,
                                       Math.max(0, c.w - 4 * unit), Math.max(0, c.h - 4 * unit));
                    }
                }
            }
            ctx.restore();
        }
        // Module ID labels over the field and the marks (under the live
        // highlight, which is drawn after every screen).
        if (field.moduleIds) this._idmDrawModuleIds(ctx, layer, field);
        ctx.restore();
    },

    // ── the live highlight ──────────────────────────────────────────────

    // One module's rectangle in workspace coordinates: the screen's frame
    // (rotation, render offset) and its canvas's workspace position applied.
    // Rotations are quarter turns, so the result is still a rectangle.
    idmModuleWorldRect(layer, panel, cell) {
        const frame = this._layerDrawFrame(layer);
        const { wx, wy } = this._layerCanvasOffset(layer);
        const pts = [[cell.x, cell.y], [cell.x + cell.w, cell.y],
            [cell.x, cell.y + cell.h], [cell.x + cell.w, cell.y + cell.h]]
            .map(([px, py]) => this._drawnPoint(frame, px, py));
        const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
        const x0 = Math.min(...xs), y0 = Math.min(...ys);
        return {
            x: x0 + frame.off.dx + wx, y: y0 + frame.off.dy + wy,
            w: Math.max(...xs) - x0, h: Math.max(...ys) - y0,
        };
    },

    // Every module of every shown screen as a workspace rectangle, for the
    // arrow keys: [{layer, panel, cell, key, x, y, w, h}]. `keep(layer)`
    // narrows the screens.
    idmModuleRects(keep) {
        const app = window.app;
        const out = [];
        if (!app || !app.project || !Array.isArray(app.project.layers)) return out;
        const canvases = Array.isArray(app.project.canvases) ? app.project.canvases : [];
        for (const layer of app.project.layers) {
            if (!layer || !layer.visible || (layer.type || 'screen') !== 'screen') continue;
            const cid = this._effectiveLayerCanvasId(layer);
            const canvas = cid ? canvases.find(c => c && c.id === cid) : null;
            if (canvas && canvas.visible === false) continue;
            if (keep && !keep(layer)) continue;
            for (const { panel, cells } of this.idmLayerCells(layer)) {
                for (const cell of cells) {
                    const r = this.idmModuleWorldRect(layer, panel, cell);
                    out.push({ layer, panel, cell, key: this.idmCellKey(panel, cell), ...r });
                }
            }
        }
        return out;
    },

    // Drawn after every screen, in workspace coordinates on `ctx` (the
    // designer's, or the output's own frame - app-output-display.js lays it
    // over a frame drawn without it): the highlighted module filled white or
    // the blink's other colour, its mark in the middle so a marked module
    // still shows it, and on screen an accent outline. opts.canvasId keeps
    // it to one canvas's output; opts.exportMode says it is for the wall.
    renderIdmHighlight(ctx = this.ctx, opts = {}) {
        const app = window.app;
        const t = (app && typeof app._idmHighlightTarget === 'function') ? app._idmHighlightTarget() : null;
        if (!t || !t.layer.visible) return;
        const canvases = (app.project && Array.isArray(app.project.canvases)) ? app.project.canvases : [];
        if (canvases.length) {
            const cid = this._effectiveLayerCanvasId(t.layer);
            if (opts.canvasId !== undefined) {
                if (opts.canvasId !== cid) return;
            } else {
                const canvas = canvases.find(c => c && c.id === cid);
                if (canvas && canvas.visible === false) return;
            }
        }
        const onScreen = opts.exportMode === undefined ? !this.exportMode : !opts.exportMode;
        const field = this.idmFieldSpec();
        const r = this.idmModuleWorldRect(t.layer, t.panel, t.cell);
        const unit = onScreen ? Math.max(1, 1 / (this.zoom || 1)) : 1;
        ctx.save();
        ctx.fillStyle = this._idmCss(t.on ? [255, 255, 255] : this.idmHighlightOffRgb(field.rgb));
        ctx.fillRect(r.x, r.y, r.w, r.h);
        const marks = (t.layer.idm && t.layer.idm.marks) || {};
        const m = marks[t.key];
        if (m) this._idmDrawMark(ctx, r, m, this.idmMarkInk(m.color, field.rgb), unit, 0.25);
        if (onScreen) {
            let accent = '#e22330';
            try {
                accent = getComputedStyle(document.documentElement).getPropertyValue('--ps-accent').trim() || accent;
            } catch (_) { /* the default accent */ }
            // A dark band under the accent, so it reads on a field of the
            // accent's own colour.
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.85)';
            ctx.lineWidth = 5 * unit;
            ctx.strokeRect(r.x - 2.5 * unit, r.y - 2.5 * unit, r.w + 5 * unit, r.h + 5 * unit);
            ctx.strokeStyle = accent;
            ctx.lineWidth = 3 * unit;
            ctx.strokeRect(r.x - 2.5 * unit, r.y - 2.5 * unit, r.w + 5 * unit, r.h + 5 * unit);
        }
        ctx.restore();
    },

    // The screen, cabinet and module under a point in workspace coordinates:
    // {layer, panel, cell} for a module, {layer, panel, cell: null} for a
    // blanked cabinet, null off every screen. Topmost screen first; the
    // screen's own frame (canvas, offset, Pixel Map rotation) is undone the
    // way getPanelAt undoes it.
    idmHitAt(worldX, worldY) {
        const app = window.app;
        if (!app || !app.project || !Array.isArray(app.project.layers)) return null;
        const canvases = Array.isArray(app.project.canvases) ? app.project.canvases : [];
        for (let i = app.project.layers.length - 1; i >= 0; i--) {
            const layer = app.project.layers[i];
            if (!layer || !layer.visible || (layer.type || 'screen') !== 'screen') continue;
            const cid = this._effectiveLayerCanvasId(layer);
            const canvas = cid ? canvases.find(c => c && c.id === cid) : null;
            if (canvas && canvas.visible === false) continue;
            const { dx, dy } = this.getLayerRenderOffset(layer);
            const { wx, wy } = this._layerCanvasOffset(layer);
            const up = this._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
            const panel = (layer.panels || []).find(p => up.x >= p.x && up.x <= p.x + p.width
                && up.y >= p.y && up.y <= p.y + p.height);
            if (!panel) continue;
            const counts = this.idmCounts(layer);
            const cells = this.idmModuleCells(layer, panel, counts.x, counts.y, this._idmVisibleLookup(layer));
            const cell = cells.find(c => up.x >= c.x && up.x <= c.x + c.w
                && up.y >= c.y && up.y <= c.y + c.h) || null;
            return { layer, panel, cell };
        }
        return null;
    },
});
