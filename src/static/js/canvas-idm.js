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
// How far apart (RGB distance) a mark and the field must be for the mark to
// keep its own colour on the wall.
const IDM_MARK_MIN_DISTANCE = 110;

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
    // (app.sanitize_idm_field; white with shaded borders when missing).
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
    //   lines  a 1 px line at every module edge in the contrasting colour at
    //          half strength, the cabinet's outer ring at full strength.
    //   ticks  short L ticks in each module's corners (length scaled to the
    //          module), longer and 2 px thick at each cabinet's corners.
    //   none   the field alone.
    // The contrasting colour is black on a light field, white on a dark one.
    idmFieldSpec() {
        const app = window.app;
        const raw = (app && app.project && app.project.idmField && typeof app.project.idmField === 'object')
            ? app.project.idmField : {};
        const hex = this._idmHexOrNull(raw.color) || IDM_FIELD_DEFAULT_COLOR;
        const border = IDM_FIELD_BORDERS.includes(raw.border) ? raw.border : 'shade';
        return { color: hex, border, rgb: this._idmRgb(hex) };
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
        const dark = Math.max(rgb[0], rgb[1], rgb[2]) < 40;
        const lift = (k) => rgb.map(v => Math.min(255, v + k));
        const dim = (f) => rgb.map(v => Math.round(v * f));
        return dark
            ? { alt: lift(26), ring: lift(52) }
            : { alt: dim(IDM_SHADE_ALT), ring: dim(IDM_SHADE_RING) };
    },

    // The colour a mark is DRAWN in: its own, unless that is too close to
    // the field to see (a red mark on a red field) - then the contrasting
    // colour. The stored colour never changes.
    idmMarkInk(color, fieldRgb) {
        const own = this._idmHexOrNull(color) || '#ff1a1a';
        if (this._idmDistance(this._idmRgb(own), fieldRgb) >= IDM_MARK_MIN_DISTANCE) return own;
        return this._idmCss(this.idmContrastRgb(fieldRgb));
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
            const lv = this.idmShadeLevels(F);
            ctx.fillStyle = this._idmCss(lv.alt);
            const gx0 = (panel.col || 0) * counts.x, gy0 = (panel.row || 0) * counts.y;
            for (const c of cells) {
                if ((gx0 + c.mx + gy0 + c.my) % 2 === 1) ctx.fillRect(c.x, c.y, c.w, c.h);
            }
            ctx.fillStyle = this._idmCss(lv.ring);
            this._idmRing(ctx, panel.x, panel.y, panel.width, panel.height, 1);
        } else if (field.border === 'lines') {
            const C = this.idmContrastRgb(F);
            ctx.fillStyle = this._idmCss(F.map((v, i) => Math.round((v + C[i]) / 2)));
            const xs = new Set(), ys = new Set();
            for (const c of cells) {
                if (c.x > panel.x + 1e-6) xs.add(c.x);
                if (c.y > panel.y + 1e-6) ys.add(c.y);
            }
            xs.forEach(x => ctx.fillRect(x, panel.y, 1, panel.height));
            ys.forEach(y => ctx.fillRect(panel.x, y, panel.width, 1));
            ctx.fillStyle = this._idmCss(C);
            this._idmRing(ctx, panel.x, panel.y, panel.width, panel.height, 1);
        } else if (field.border === 'ticks') {
            const C = this.idmContrastRgb(F);
            ctx.fillStyle = this._idmCss(C);
            for (const c of cells) {
                const len = Math.max(2, Math.min(16, Math.round(Math.min(c.w, c.h) * 0.15)));
                this._idmTicks(ctx, c.x, c.y, c.w, c.h, len, 1);
            }
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
