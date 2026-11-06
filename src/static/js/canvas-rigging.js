// canvas.js mixin: The header/footer pass: the bars drawn above (header) and below (footer) a wall in the Header/Footer view.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    // The bar under a point on the canvas (canvas pixels), or null. The hit
    // carries its screen, its row ('header' or 'footer') and its index.
    riggingBarAt(mouseX, mouseY) {
        const hits = this._riggingHits || [];
        // A zoomed-out bar can be a few pixels tall: the grab area is never
        // thinner than this, centred on the bar.
        const MIN_GRAB = 18;
        for (let i = hits.length - 1; i >= 0; i--) {
            const h = hits[i];
            const pad = Math.max(0, (MIN_GRAB - (h.y1 - h.y0)) / 2);
            if (mouseX >= h.x0 && mouseX <= h.x1 && mouseY >= h.y0 - pad && mouseY <= h.y1 + pad) return h;
        }
        return null;
    },

    // The edge between two bars under a point, or null: within a few
    // pixels of the line they share, and the same grab height as a bar.
    // Checked before the bars, so the edge wins over the bar it borders.
    riggingEdgeAt(mouseX, mouseY) {
        const EDGE_GRAB = 6;
        const MIN_GRAB = 18;
        const edges = this._riggingEdges || [];
        for (let i = edges.length - 1; i >= 0; i--) {
            const e = edges[i];
            const pad = Math.max(0, (MIN_GRAB - (e.y1 - e.y0)) / 2);
            if (Math.abs(mouseX - e.x) <= EDGE_GRAB && mouseY >= e.y0 - pad && mouseY <= e.y1 + pad) return e;
        }
        return null;
    },

    // The header row above the wall and the footer row below it.
    // layer.riggingBars / layer.riggingFooterBars are the bar sizes in
    // panels, left to right ([6, 2] is a 6-wide bar then a 2-wide bar); each
    // is empty until the user presses Auto, and nothing draws for an empty
    // row. Called inside the layer's show-position translate, so the
    // footprint from getLayerFootprintInActiveView is where the wall sits.
    renderRiggingBars(layer) {
        const header = Array.isArray(layer.riggingBars) ? layer.riggingBars : [];
        const footer = Array.isArray(layer.riggingFooterBars) ? layer.riggingFooterBars : [];
        if (!header.length && !footer.length) return;

        const box = this.getLayerFootprintInActiveView(layer);
        const baseH = Math.max(36, Math.min(96, box.height * 0.18));
        const ctx = this.ctx;
        // The screen's own colors (black bar, white text unless changed). A
        // printed page (the binder's printer palette) is always a white bar
        // with black text, so it costs no ink and stays readable.
        const hex = /^#[0-9a-f]{6}$/i;
        let fill = hex.test(layer.riggingColor || '') ? layer.riggingColor : '#000000';
        let textColor = hex.test(layer.riggingTextColor || '') ? layer.riggingTextColor : '#ffffff';
        if (this.printerMode) { fill = '#ffffff'; textColor = PRINTER_INK; }
        const style = { fill, textColor };

        ctx.save();
        // The binder's sheet leaves a fixed strip above and below the wall
        // (in sheet units); it sets riggingTopRoom / riggingBottomRoom to
        // those strips in canvas units so the bars fit whatever the zoom.
        const fit = (room) => {
            let gap = 6;
            let h = baseH;
            if (Number.isFinite(room)) {
                gap = Math.min(gap, room * 0.1);
                h = Math.min(h, Math.max(8, room - gap));
            }
            return { gap, h };
        };
        // A picture of the raster (PNG export) ends at the raster's edges: a
        // wall too near one takes its bars over its own edge row instead of
        // losing them off the image.
        const clipToRaster = this.exportMode && !this.ignoreRasterBounds;
        if (header.length) {
            const { gap, h } = fit(this.riggingTopRoom);
            let top = box.y - gap - h;
            if (clipToRaster && top < 0) top = 0;
            this._drawRiggingRow(layer, 'header', header, box, top, h, style);
        }
        if (footer.length) {
            const { gap, h } = fit(this.riggingBottomRoom);
            let top = box.y + box.height + gap;
            if (clipToRaster && Number.isFinite(this.rasterHeight) && top + h > this.rasterHeight) {
                top = Math.max(0, this.rasterHeight - h);
            }
            this._drawRiggingRow(layer, 'footer', footer, box, top, h, style);
        }
        ctx.restore();
    },

    // One row of bars across the wall's width, and the mouse's view of it.
    _drawRiggingRow(layer, row, bars, box, top, barH, style) {
        const total = bars.reduce((a, b) => a + b, 0);
        if (total <= 0) return;
        const ctx = this.ctx;
        const unit = box.width / total;
        // Where each bar and edge sits on the screen (canvas pixels), for
        // the mouse: read through the current transform, so the layer's
        // workspace offset and a mirrored canvas are already in it. A
        // picture being exported has no mouse and records nothing.
        const m = ctx.getTransform();
        const hits = (!this.exportMode && this._riggingHits) || null;
        const edges = (!this.exportMode && this._riggingEdges) || null;
        // The bars lit while the mouse has hold of something: the bar being
        // moved, or the two either side of the edge being dragged.
        const lit = new Set();
        const d = this._riggingDrag;
        if (d && d.layerId === layer.id && d.row === row) {
            if (d.kind === 'edge') { lit.add(d.boundary); lit.add(d.boundary + 1); }
            else lit.add(Number.isInteger(d.current) ? d.current : d.index);
        }
        let x = box.x;
        let index = 0;
        for (const span of bars) {
            const w = span * unit;
            ctx.fillStyle = style.fill;
            ctx.fillRect(x, top, w, barH);
            ctx.strokeStyle = lit.has(index) ? '#4A90E2' : style.textColor;
            ctx.lineWidth = lit.has(index) ? 4 : 2;
            ctx.strokeRect(x, top, w, barH);
            const unitPx = Math.abs(m.a * unit);
            const dir = m.a < 0 ? -1 : 1;
            if (hits) {
                const sx0 = m.a * x + m.e, sx1 = m.a * (x + w) + m.e;
                hits.push({ layerId: layer.id, row, index, span,
                            x0: Math.min(sx0, sx1), x1: Math.max(sx0, sx1),
                            y0: m.d * top + m.f, y1: m.d * (top + barH) + m.f,
                            // screen pixels per panel, and which way the wall runs
                            unitPx, dir });
            }
            // The edge this bar shares with the next one (not the wall's own
            // two ends, which have no neighbour to give or take a panel).
            if (edges && index < bars.length - 1) {
                edges.push({ layerId: layer.id, row, boundary: index, x: m.a * (x + w) + m.e,
                             y0: m.d * top + m.f, y1: m.d * (top + barH) + m.f, unitPx, dir });
            }
            index++;

            const fontPx = Math.max(10, Math.min(barH * 0.6, w * 0.5));
            ctx.fillStyle = style.textColor;
            ctx.font = `bold ${fontPx}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(span), x + w / 2, top + barH / 2);
            x += w;
        }
    },
});
