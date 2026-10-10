// canvas.js mixin: the IDM Locator view - every cabinet's module grid and the
// modules marked bad, drawn over the Pixel Map, and the hit test that finds
// the module under the pointer.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
//
// The view draws exactly what the Pixel Map draws (render() runs the Pixel
// Map pass with _idmPass set; canvas.js), so the cabinets stand where the
// processor raster has them and Output to Display can put the picture on
// the wall. Each screen's block is `layer.idm` (app.sanitize_idm on the
// server holds the shape; app-idm-locator.js edits it):
//   {modulesX, modulesY, marks: {"col,row,mx,my": {style, color}}}
// A module is the cabinet's pixels / modules, the remainder spread so no
// module is a fractional pixel: edges at floor(k * px / n). A half cabinet
// keeps the modules that fall inside it, the full cabinet laid from the side
// that meets the wall (the cut is on the free edge). A blanked cabinet has
// none. The geometry here is the server's idm_module_cells line for line.
const IDM_MAX_MODULES = 64;

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

    // Drawn inside the screen's own frame (its offset and Pixel Map rotation
    // applied by render()), after the Pixel Map pass of that screen: the
    // marks, then the module lines, then the cabinet edges. Line widths are
    // one LED pixel on the output (export mode) and one screen pixel or
    // more in the designer, whatever the zoom.
    renderIdmLayer(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen' || !Array.isArray(layer.panels)) return;
        const ctx = this.ctx;
        const marks = (layer.idm && layer.idm.marks && typeof layer.idm.marks === 'object')
            ? layer.idm.marks : {};
        const unit = this.exportMode ? 1 : Math.max(1, 1 / (this.zoom || 1));
        const half = this.exportMode ? 0.5 : 0;
        const flash = (!this.exportMode && window.app && typeof window.app._idmFlashFor === 'function')
            ? window.app._idmFlashFor(layer) : null;
        ctx.save();
        this._clipToActiveRaster();
        for (const { panel, cells } of this.idmLayerCells(layer)) {
            if (!cells.length) continue;
            ctx.save();
            ctx.beginPath();
            ctx.rect(panel.x, panel.y, panel.width, panel.height);
            ctx.clip();
            // The marks.
            for (const c of cells) {
                const m = marks[this.idmCellKey(panel, c)];
                if (!m) continue;
                const colour = m.color || '#ff1a1a';
                if (m.style === 'x') {
                    ctx.save();
                    ctx.beginPath();
                    ctx.rect(c.x, c.y, c.w, c.h);
                    ctx.clip();
                    ctx.strokeStyle = colour;
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
                    ctx.fillStyle = colour;
                    ctx.fillRect(c.x, c.y, c.w, c.h);
                }
            }
            // The lines between modules: a dark band with a light core, so
            // they read on a light cabinet colour and on a dark one.
            const xs = new Set(), ys = new Set();
            for (const c of cells) {
                if (c.x > panel.x + 1e-6) xs.add(c.x);
                if (c.y > panel.y + 1e-6) ys.add(c.y);
            }
            if (xs.size || ys.size) {
                const path = () => {
                    ctx.beginPath();
                    xs.forEach(x => { ctx.moveTo(x - half, panel.y); ctx.lineTo(x - half, panel.y + panel.height); });
                    ys.forEach(y => { ctx.moveTo(panel.x, y - half); ctx.lineTo(panel.x + panel.width, y - half); });
                };
                path();
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.55)';
                ctx.lineWidth = 3 * unit;
                ctx.stroke();
                path();
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
                ctx.lineWidth = unit;
                ctx.stroke();
            }
            // The cabinet's own edge, stronger, inside the cabinet.
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.lineWidth = 2 * unit;
            ctx.strokeRect(panel.x + unit, panel.y + unit,
                           Math.max(0, panel.width - 2 * unit), Math.max(0, panel.height - 2 * unit));
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
            ctx.restore();
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
