// canvas.js mixin: The header/footer pass: the bars drawn above (header) and below (footer) a wall in the Header/Footer view.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    // The bar under a point on the canvas (canvas pixels), or null. The hit
    // carries its screen (the one it is stored on), its row ('header' or
    // 'footer'), its index on that screen, its index in the whole row
    // (runIndex: a row may cross a group's seam) and its start.
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

    // Custom: the strip where a screen's bars go and its edge row of panels
    // under a point, with the panel the point is over (the screen's own),
    // or null. `kind` is 'both' on a screen an older show left with a
    // header and a footer.
    riggingZoneAt(mouseX, mouseY) {
        const zones = this._riggingZones || [];
        for (let i = zones.length - 1; i >= 0; i--) {
            const z = zones[i];
            if (mouseX < Math.min(z.x0, z.x1) || mouseX > Math.max(z.x0, z.x1)) continue;
            if (mouseY < z.y0 || mouseY > z.y1) continue;
            const panel = Math.max(0, Math.min(z.panels - 1, Math.floor(z.dir * (mouseX - z.x0) / z.unitPx)));
            return { ...z, panel };
        }
        return null;
    },

    // The panel of a zone's ROW under a canvas x (may run onto a
    // neighbor in a group's row, or past either end: the caller clamps).
    riggingZoneRowPanel(zone, mouseX) {
        return zone.offset + Math.floor(zone.dir * (mouseX - zone.x0) / zone.unitPx);
    },

    // The header row above the wall and the footer row below it (only the
    // screen's own side; both on an older show that has both). Each bar is
    // drawn by the screen it is stored on (the one it starts on), at its
    // place in the row, so a bar across a group's seam runs on over the
    // neighbor. Called inside the layer's show-position translate, so the
    // footprint from getLayerFootprintInActiveView is where the wall sits.
    //
    // riggingSolo (the binder's sheet of one screen): the screen draws every
    // bar of its row over it, its neighbor's too, and the part of a bar
    // that carries on over a neighbor is drawn as a dashed outline, so the
    // crew sees it continues there.
    renderRiggingBars(layer) {
        const app = window.app;
        if (!app || typeof app.riggingRowsOf !== 'function') return;
        // Text and image layers carry no bars.
        if ((layer.type || 'screen') !== 'screen') return;
        const interactive = !this.exportMode && this.viewMode === 'rigging';
        const solo = !!this.riggingSolo;
        const side = app.riggingSideOf(layer);
        const rows = app.riggingRowsOf(layer);
        const shows = (row) => (solo ? app.riggingSliceOf(layer, row.kind).length > 0
            : row.placed.some(b => b.owner === layer));
        if (!interactive && !rows.some(shows)) return;

        const box = this.getLayerFootprintInActiveView(layer);
        const wall = RiggingMath.wallPanels(layer.columns, layer.rows, layer.rotation);
        const unit = box.width / Math.max(1, wall);
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
        const fit = (room, baseH) => {
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
        const m = ctx.getTransform();
        const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
        const wallRows = Math.max(1, Number(deg === 90 || deg === 270 ? layer.columns : layer.rows) || 1);
        const panelH = box.height / wallRows;
        for (const row of rows) {
            // One height along a row that crosses a seam: the shortest
            // member's, so the bars line up.
            const minH = row.layers.length > 1
                ? Math.min(...row.layers.map(l => app._riggingRect(l).h)) : box.height;
            const baseH = Math.max(36, Math.min(96, minH * 0.18));
            const header = row.kind === 'header';
            const { gap, h } = fit(header ? this.riggingTopRoom : this.riggingBottomRoom, baseH);
            let top = header ? box.y - gap - h : box.y + box.height + gap;
            if (clipToRaster && header && top < 0) top = 0;
            if (clipToRaster && !header && Number.isFinite(this.rasterHeight) && top + h > this.rasterHeight) {
                top = Math.max(0, this.rasterHeight - h);
            }
            if (interactive && this._riggingZones) {
                // The strip and the wall's edge row of panels: where a
                // Custom click or drag lays bars.
                const ya = header ? top : box.y + box.height - panelH;
                const yb = header ? box.y + panelH : top + h;
                const k = row.layers.indexOf(layer);
                this._riggingZones.push({
                    layerId: layer.id, kind: side === 'both' ? 'both' : row.kind, rowKey: row.key,
                    offset: row.offsets[k], rowWidth: row.width, panels: wall,
                    x0: m.a * box.x + m.e, x1: m.a * (box.x + box.width) + m.e,
                    y0: Math.min(m.d * ya + m.f, m.d * yb + m.f), y1: Math.max(m.d * ya + m.f, m.d * yb + m.f),
                    unitPx: Math.abs(m.a * unit) || 1, dir: m.a < 0 ? -1 : 1,
                });
            }
            if (shows(row)) this._drawRiggingRow(layer, row, box, top, h, style, unit, solo);
            if (interactive) this._drawRiggingGhost(layer, row, box, top, h, style, unit);
        }
        ctx.restore();
    },

    // One row of bars, and the mouse's view of it. A panel of bar is a
    // panel of wall: a row that no longer fits its wall stops short of it
    // or runs past it at its true width, never stretched to look as if it
    // fits, and is marked.
    _drawRiggingRow(layer, row, box, top, barH, style, unit, solo) {
        const ctx = this.ctx;
        const app = window.app;
        const k = row.layers.indexOf(layer);
        const off = row.offsets[k];
        const last = row.layers.length - 1;
        const rowX = box.x - off * unit;            // the row's panel 0, in this wall's frame
        const crossing = solo && row.layers.length > 1;
        const list = crossing
            ? row.placed.filter(b => b.owner === layer
                || (b.start < off + row.panels[k] && b.start + b.size > off))
            : row.placed.filter(b => b.owner === layer);
        // Where each bar and edge sits on the screen (canvas pixels), for
        // the mouse: read through the current transform, so the layer's
        // workspace offset and a mirrored canvas are already in it. A
        // picture being exported has no mouse and records nothing.
        const m = ctx.getTransform();
        const hits = (!this.exportMode && this._riggingHits) || null;
        const edges = (!this.exportMode && this._riggingEdges) || null;
        const unitPx = Math.abs(m.a * unit);
        const dir = m.a < 0 ? -1 : 1;
        // The bars lit: the one picked (Delete takes it off), the one being
        // moved, the two either side of the edge being dragged, the ones a
        // Custom click or drag is laying.
        const lit = new Set();
        const d = this._riggingDrag;
        if (d && d.rowObj && d.rowObj.key === row.key) {
            if (d.kind === 'edge') { lit.add(d.boundary); lit.add(d.boundary + 1); }
            else if (d.kind === 'move') lit.add(Number.isInteger(d.current) ? d.current : d.index);
        }
        const adds = d && d.kind === 'place' && d.rowObj && d.rowObj.key === row.key
            ? new Set((d.adds || []).map(b => b.start)) : null;
        const p = app && app._riggingPicked;
        const isLit = (b) => !this.exportMode && (lit.has(b.runIndex) || (adds && adds.has(b.start))
            || (!this.exportMode && p && p.kind === row.kind && p.layerId === b.owner.id
                && row.offsets[row.layers.indexOf(b.owner)] + p.start === b.start));
        const line = (on) => { ctx.strokeStyle = on ? '#4A90E2' : style.textColor; ctx.lineWidth = on ? 4 : 2; };
        // A bar in hand, picked or being laid fills blue, so it reads at
        // any zoom; an exported picture never shows it.
        const fillOf = (on) => (on ? '#4A90E2' : style.fill);
        const label = (span, x, w) => {
            const fontPx = Math.max(10, Math.min(barH * 0.6, w * 0.5));
            ctx.fillStyle = style.textColor;
            ctx.font = `bold ${fontPx}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            this._fillText(String(span), x + w / 2, top + barH / 2);
        };
        for (const b of list) {
            const x = rowX + b.start * unit;
            const w = b.size * unit;
            const on = isLit(b);
            if (crossing) {
                // Over this wall: the bar. Over a neighbor: a dashed outline.
                const lo = k > 0 ? Math.max(x, box.x) : x;
                const hi = k < last ? Math.min(x + w, box.x + box.width) : x + w;
                if (hi > lo) {
                    ctx.fillStyle = fillOf(on);
                    ctx.fillRect(lo, top, hi - lo, barH);
                    line(on);
                    ctx.strokeRect(lo, top, hi - lo, barH);
                }
                ctx.save();
                // On the paper around the wall, in the bar's own color (its
                // text color when the bar is too pale to show on white).
                ctx.strokeStyle = this.printerMode ? PRINTER_INK : this._riggingInkOnPaper(style);
                ctx.lineWidth = 2;
                ctx.setLineDash([Math.max(4, barH * 0.2), Math.max(3, barH * 0.12)]);
                if (lo > x) ctx.strokeRect(x, top, lo - x, barH);
                if (hi < x + w) ctx.strokeRect(Math.max(hi, x), top, x + w - Math.max(hi, x), barH);
                ctx.restore();
                if (hi > lo) label(b.size, lo, hi - lo);
            } else {
                ctx.fillStyle = fillOf(on);
                ctx.fillRect(x, top, w, barH);
                line(on);
                ctx.strokeRect(x, top, w, barH);
                label(b.size, x, w);
            }
            if (b.owner !== layer) continue;
            if (hits) {
                const sx0 = m.a * x + m.e, sx1 = m.a * (x + w) + m.e;
                hits.push({ layerId: layer.id, row: row.kind, rowKey: row.key, index: b.ownerIndex,
                            runIndex: b.runIndex, start: b.start - off, span: b.size,
                            x0: Math.min(sx0, sx1), x1: Math.max(sx0, sx1),
                            y0: m.d * top + m.f, y1: m.d * (top + barH) + m.f,
                            // screen pixels per panel, and which way the wall runs
                            unitPx, dir });
            }
            // The edge this bar shares with the next one, when they touch
            // (not the row's own two ends, nor a gap, which have no
            // neighbor to give or take a panel).
            const next = row.placed[b.runIndex + 1];
            if (edges && next && next.start === b.start + b.size) {
                edges.push({ layerId: layer.id, row: row.kind, rowKey: row.key, boundary: b.ownerIndex,
                             runBoundary: b.runIndex, x: m.a * (x + w) + m.e,
                             y0: m.d * top + m.f, y1: m.d * (top + barH) + m.f, unitPx, dir });
            }
        }
        // The mark, drawn once per row, by the screen holding its last bar.
        if (row.problem && row.placed.length) {
            const end = row.placed.reduce((a, b) => (b.start + b.size >= a.start + a.size ? b : a));
            if (end.owner === layer) {
                this._drawRiggingMisfit(rowX, row.width * unit, top, barH, rowX + (end.start + end.size) * unit);
            }
        }
    },

    // A color that shows on white paper: the bar's fill, or its text
    // color when the fill is pale.
    _riggingInkOnPaper(style) {
        const hex = String(style.fill || '#000000');
        const n = parseInt(hex.slice(1), 16);
        const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
        return lum > 0.8 ? style.textColor : hex;
    },

    // Custom: the bar a click would drop, under the mouse, before the
    // button goes down: the picked size, see-through, in a dashed blue
    // outline (app._riggingGhost, set as the mouse moves).
    _drawRiggingGhost(layer, row, box, top, barH, style, unit) {
        const g = window.app && window.app._riggingGhost;
        if (!g || g.layerId !== layer.id || g.rowKey !== row.key) return;
        const ctx = this.ctx;
        const off = row.offsets[row.layers.indexOf(layer)];
        const x = box.x + (g.start - off) * unit;
        const w = g.size * unit;
        ctx.save();
        ctx.globalAlpha = 0.45;
        ctx.fillStyle = style.fill;
        ctx.fillRect(x, top, w, barH);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#4A90E2';
        ctx.lineWidth = 3;
        ctx.setLineDash([Math.max(4, barH * 0.2), Math.max(3, barH * 0.12)]);
        ctx.strokeRect(x, top, w, barH);
        ctx.setLineDash([]);
        const fontPx = Math.max(10, Math.min(barH * 0.6, w * 0.5));
        ctx.fillStyle = '#4A90E2';
        ctx.font = `bold ${fontPx}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        this._fillText(String(g.size), x + w / 2, top + barH / 2);
        ctx.restore();
    },

    // The mark on a row that no longer fits: a dashed outline where the
    // bars should reach (x0, width: the wall, or a group's whole row), and
    // the words beside the bars' own end, inside the gap on a short row and
    // past the bars on a long one.
    _drawRiggingMisfit(x0, width, top, barH, barsEnd) {
        const ctx = this.ctx;
        const ink = this.printerMode ? PRINTER_INK : '#ff5a4f';
        ctx.save();
        ctx.strokeStyle = ink;
        ctx.lineWidth = 3;
        ctx.setLineDash([barH * 0.25, barH * 0.15]);
        ctx.strokeRect(x0, top, width, barH);
        ctx.setLineDash([]);
        const fontPx = Math.max(10, Math.min(barH * 0.4, 28));
        ctx.font = `bold ${fontPx}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = ink;
        const word = 'No longer fits';
        const half = ctx.measureText(word).width / 2;
        const gap = x0 + width - barsEnd;
        const x = gap > half * 2 ? barsEnd + gap / 2 : barsEnd + half + fontPx / 2;
        this._fillText(word, x, top + barH / 2);
        ctx.restore();
    },
});
