// canvas.js mixin: The header/footer pass: the bars drawn above (header) and below (footer) a wall in the Header/Footer view.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
// The live Header/Footer view's floor at any zoom, in screen pixels: the
// bar strip's height, the gap between it and the wall, its numbers, and how
// far past the bars a Custom press still lays them.
const RIGGING_MIN_BAR_PX = 18;
const RIGGING_MIN_GAP_PX = 4;
const RIGGING_MIN_FONT_PX = 11;
const RIGGING_ZONE_PAD = 12;

Object.assign(CanvasRenderer.prototype, {
    // Every bar, edge and strip the mouse can find is kept in its wall's
    // own frame (`f`: the inverse of the drawing transform, and `s`, screen
    // pixels per unit of that frame), so a wall whose picture is turned by
    // its Pixel Map rotation is found where its bars are drawn: along its
    // real bottom (owner, 2026-11-10). x0..y1 stay the screen box around it.
    _riggingLocal(f, mouseX, mouseY) {
        const p = f.inv.transformPoint(new DOMPoint(mouseX, mouseY));
        return { x: p.x, y: p.y };
    },

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
            const p = this._riggingLocal(h.f, mouseX, mouseY);
            const pad = Math.max(0, (MIN_GRAB / h.f.s - (h.ly1 - h.ly0)) / 2);
            if (p.x >= h.lx0 && p.x <= h.lx1 && p.y >= h.ly0 - pad && p.y <= h.ly1 + pad) return h;
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
            const p = this._riggingLocal(e.f, mouseX, mouseY);
            const pad = Math.max(0, (MIN_GRAB / e.f.s - (e.ly1 - e.ly0)) / 2);
            if (Math.abs(p.x - e.lx) <= EDGE_GRAB / e.f.s && p.y >= e.ly0 - pad && p.y <= e.ly1 + pad) return e;
        }
        return null;
    },

    // Custom: the strip where a screen's bars go under a point, with the
    // panel the point is over (the screen's own), or null. The strip runs
    // from the wall's edge out past the bars' outer edge (RIGGING_ZONE_PAD
    // on screen); the wall itself is never in it, so a press on the wall
    // selects the screen and drags as it does with Auto (owner,
    // 2026-11-08). A bar already in the strip is checked first (a press on
    // it picks or moves it), so a new bar over an old one is laid from the
    // band past the bars' outer edge or the gap at the wall. `kind` is
    // 'both' on a screen an older show left with a header and a footer.
    riggingZoneAt(mouseX, mouseY) {
        const zones = this._riggingZones || [];
        for (let i = zones.length - 1; i >= 0; i--) {
            const z = zones[i];
            const p = this._riggingLocal(z.f, mouseX, mouseY);
            if (p.x < z.lx0 || p.x > z.lx1 || p.y < z.ly0 || p.y > z.ly1) continue;
            const panel = Math.max(0, Math.min(z.panels - 1, this._riggingPanelAt(z.geo, p.x)));
            return { ...z, panel };
        }
        return null;
    },

    // The panel of a zone's ROW under a canvas point (may run onto a
    // neighbor in a group's row, or past either end: the caller clamps).
    riggingZoneRowPanel(zone, mouseX, mouseY) {
        const p = this._riggingLocal(zone.f, mouseX, mouseY == null ? 0 : mouseY);
        return zone.offset + this._riggingPanelAt(zone.geo, p.x);
    },

    // The wall's panel under x (in its own frame): the column x falls in,
    // a half column as wide as it is; off the wall, whole panels on.
    _riggingPanelAt(geo, x) {
        const rel = (x - geo.x) / geo.k;
        const { lefts, widths, total, full } = geo.cols;
        const n = widths.length;
        if (rel < 0) return Math.floor(rel / full);
        if (rel >= total) return n + Math.floor((rel - total) / full);
        for (let i = n - 1; i >= 0; i--) if (rel >= lefts[i]) return i;
        return 0;
    },

    // Where a bar stands in the wall's own frame (canvas units):
    // { x, w }. `start` is the wall's own panel (a row's panel less this
    // wall's offset in it); app-rigging riggingBarSpan says where.
    _riggingSpan(geo, start, size) {
        const [a, b] = window.app.riggingBarSpan(geo.cols, start, size);
        return { x: geo.x + a * geo.k, w: (b - a) * geo.k };
    },

    // The x of the wall's own panel edge `p` (0 its left edge), whole
    // panels off the wall.
    _riggingEdgeX(geo, p) {
        const { lefts, widths, total, full } = geo.cols;
        const n = widths.length;
        const rel = p <= 0 ? p * full : p >= n ? total + (p - n) * full : lefts[p];
        return geo.x + rel * geo.k;
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
            : row.placed.some(b => b.owner === layer) || (row.pieces || []).some(p => p.owner === layer));
        if (!interactive && !rows.some(shows)) return;

        // The wall as built, unturned: its own columns along its own bottom.
        // A Pixel Map rotation turns only the picture (owner, 2026-11-10),
        // so the bars are drawn in the wall's own frame and turned with the
        // picture about its middle: each bar stays by the cabinets it is
        // under on the wall, and the numbers stay upright.
        const raw = this.getLayerBoundsInActiveView(layer);
        const box = { x: raw.x, y: raw.y, width: raw.width, height: raw.height };
        const deg = typeof app.riggingTurn === 'function' ? app.riggingTurn(layer) : 0;
        const wall = app.riggingWallPanels(layer);
        const cols = app.riggingColumns(layer);
        // the wall's columns in this frame: a half column half as wide
        const geo = { x: box.x, cols, k: cols.total > 0 ? box.width / cols.total : 1 };
        const unit = cols.full * geo.k;            // one whole panel
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
        const upright = { keep: this._keepTextUpright, rad: this._activeRotationRad };
        if (deg) {
            const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
            ctx.translate(cx, cy);
            ctx.rotate(deg * Math.PI / 180);
            ctx.translate(-cx, -cy);
            this._keepTextUpright = true;
            this._activeRotationRad = deg * Math.PI / 180;
        }
        // The binder's sheet leaves a fixed strip above and below the wall
        // (in sheet units); it sets riggingTopRoom / riggingBottomRoom to
        // those strips in canvas units so the bars fit whatever the zoom,
        // or riggingSideRooms ({ top, right, bottom, left }), when a
        // turned picture puts the bars beside the wall.
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
        const clipToRaster = this.exportMode && !this.ignoreRasterBounds && !deg;
        const m = ctx.getTransform();
        // What the mouse reads in this wall's own frame (canvas-rigging
        // _riggingLocal): the inverse of the drawing, and screen pixels per
        // unit of it.
        const f = { inv: m.inverse(), s: Math.hypot(m.a, m.b) || 1 };
        // On this tab the bars stay readable however far out the view is
        // zoomed (owner, 2026-11-08: "bars are thin when zoomed out"): the
        // strip is never shorter than RIGGING_MIN_BAR_PX on screen, nor
        // its numbers smaller than RIGGING_MIN_FONT_PX. Only the live view:
        // the binder, an export and the 3D stage draw the real sizes.
        const perPx = 1 / f.s;     // canvas units per screen pixel
        const lift = interactive && !solo;
        style.minFont = lift ? RIGGING_MIN_FONT_PX * perPx : 10;
        style.line = lift ? perPx : 0;
        for (const row of rows) {
            // One height along a row that crosses a seam: the shortest
            // member's, so the bars line up.
            const minH = row.layers.length > 1
                ? Math.min(...row.layers.map(l => app._riggingRect(l).h)) : box.height;
            const baseH = Math.max(36, Math.min(96, minH * 0.18));
            const header = row.kind === 'header';
            const sides = this.riggingSideRooms;
            const room = sides ? sides[app.riggingPictureSide(layer, header ? 'top' : 'bottom')]
                : (header ? this.riggingTopRoom : this.riggingBottomRoom);
            let { gap, h } = fit(room, baseH);
            if (lift && !Number.isFinite(room)) {
                h = Math.max(h, RIGGING_MIN_BAR_PX * perPx);
                gap = Math.max(gap, RIGGING_MIN_GAP_PX * perPx);
            }
            let top = header ? box.y - gap - h : box.y + box.height + gap;
            if (clipToRaster && header && top < 0) top = 0;
            if (clipToRaster && !header && Number.isFinite(this.rasterHeight) && top + h > this.rasterHeight) {
                top = Math.max(0, this.rasterHeight - h);
            }
            if (interactive && this._riggingZones) {
                // The bar strip, from the wall's edge out past the bars:
                // where a Custom click or drag lays bars. Never the wall.
                const inner = header ? box.y : box.y + box.height;
                const outer = (header ? top : top + h) + (header ? -1 : 1) * RIGGING_ZONE_PAD / f.s;
                const k = row.layers.indexOf(layer);
                this._riggingZones.push({
                    layerId: layer.id, kind: side === 'both' ? 'both' : row.kind, rowKey: row.key,
                    offset: row.offsets[k], rowWidth: row.width, panels: wall, f, geo,
                    lx0: box.x, lx1: box.x + box.width, ly0: Math.min(inner, outer), ly1: Math.max(inner, outer),
                    ...this._riggingScreenBox(m, box.x, Math.min(inner, outer), box.x + box.width, Math.max(inner, outer)),
                    unitPx: unit * f.s || 1, dir: m.a < 0 ? -1 : 1,
                });
            }
            if (shows(row)) this._drawRiggingRow(layer, row, box, top, h, style, geo, solo, f);
            if (interactive) this._drawRiggingGhost(layer, row, top, h, style, geo);
        }
        this._keepTextUpright = upright.keep;
        this._activeRotationRad = upright.rad;
        ctx.restore();
    },

    // The screen box (canvas pixels) round a rectangle of the wall's own
    // frame drawn through `m`: { x0, x1, y0, y1 }.
    _riggingScreenBox(m, ax, ay, bx, by) {
        const pts = [[ax, ay], [bx, ay], [bx, by], [ax, by]].map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
        const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
        return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
    },

    // One row of bars, and the mouse's view of it. A panel of bar is a
    // panel of wall: a row that no longer fits its wall stops short of it
    // or runs past it at its true width, never stretched to look as if it
    // fits, and is marked.
    //
    // A bar is drawn at its full stock length in this wall's own frame
    // (`geo`, _riggingSpan): over a half column it hangs past the wall
    // (owner, 2026-11-10). `f` is what the mouse reads (renderRiggingBars).
    _drawRiggingRow(layer, row, box, top, barH, style, geo, solo, f) {
        const ctx = this.ctx;
        const app = window.app;
        const k = row.layers.indexOf(layer);
        const off = row.offsets[k];
        const last = row.layers.length - 1;
        const unit = geo.cols.full * geo.k;        // one whole panel
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
        const unitPx = unit * f.s;
        const dir = m.a < 0 ? -1 : 1;
        // A hit's place: in the wall's own frame for the mouse, and the box
        // round it on the screen (the guides read that).
        const place = (x, w) => ({ f, unit, lx0: x, lx1: x + w, ly0: top, ly1: top + barH,
                                    ...this._riggingScreenBox(m, x, top, x + w, top + barH) });
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
        const line = (on) => {
            ctx.strokeStyle = on ? '#4A90E2' : style.textColor;
            ctx.lineWidth = Math.max(on ? 4 : 2, (on ? 2 : 1) * (style.line || 0));
        };
        // A bar in hand, picked or being laid fills blue, so it reads at
        // any zoom; an exported picture never shows it.
        const fillOf = (on) => (on ? '#4A90E2' : style.fill);
        const label = (span, x, w) => {
            const fontPx = Math.max(style.minFont || 10, Math.min(barH * 0.6, w * 0.5));
            ctx.fillStyle = style.textColor;
            ctx.font = `bold ${fontPx}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            this._fillText(String(span), x + w / 2, top + barH / 2);
        };
        for (const b of list) {
            const { x, w } = this._riggingSpan(geo, b.start - off, b.size);
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
                hits.push({ layerId: layer.id, row: row.kind, rowKey: row.key, index: b.ownerIndex,
                            runIndex: b.runIndex, start: b.start - off, span: b.size,
                            ...place(x, w),
                            // screen pixels per panel, and which way the wall runs
                            unitPx, dir });
            }
            // The edge this bar shares with the next one, when they touch
            // (not the row's own two ends, nor a gap, which have no
            // neighbor to give or take a panel).
            const next = row.placed[b.runIndex + 1];
            if (edges && next && next.start === b.start + b.size) {
                const at = this._riggingSpan(geo, next.start - off, next.size).x;
                const sb = this._riggingScreenBox(m, at, top, at, top + barH);
                edges.push({ layerId: layer.id, row: row.kind, rowKey: row.key, boundary: b.ownerIndex,
                             runBoundary: b.runIndex, x: (sb.x0 + sb.x1) / 2, y0: sb.y0, y1: sb.y1,
                             f, unit, lx: at, ly0: top, ly1: top + barH, unitPx, dir });
            }
        }
        // Its corner pieces (app-rigging.js), each over the panels touching
        // its corner, "Corner" on it and a dashed line where it folds. A
        // click picks one (Delete takes it off); it never moves.
        for (const pc of (row.pieces || [])) {
            if (pc.owner !== layer) continue;
            const { x, w } = this._riggingSpan(geo, pc.start - off, pc.size);
            const on = !this.exportMode && ((p && p.kind === row.kind && p.layerId === layer.id && p.corner === pc.at)
                || (d && d.kind === 'place' && d.rowObj && d.rowObj.key === row.key
                    && (d.cornerAdds || []).includes(pc.at)));
            ctx.fillStyle = fillOf(on);
            ctx.fillRect(x, top, w, barH);
            line(on);
            ctx.strokeRect(x, top, w, barH);
            this._drawRiggingFold(x + w / 2, top, barH, style.textColor);
            this._riggingCornerLabel(x, w, top, barH, style);
            if (hits) {
                hits.push({ layerId: layer.id, row: row.kind, rowKey: row.key, index: -1, runIndex: -1,
                            start: pc.start - off, span: pc.size, corner: pc.at,
                            ...place(x, w), unitPx, dir });
            }
        }
        // The mark, drawn once per row, by the screen holding its last bar.
        if (row.problem && row.placed.length) {
            const end = row.placed.reduce((a, b) => (b.start + b.size >= a.start + a.size ? b : a));
            if (end.owner === layer) {
                const x0 = this._riggingEdgeX(geo, -off);
                const x1 = this._riggingEdgeX(geo, row.width - off);
                const endSpan = this._riggingSpan(geo, end.start - off, end.size);
                this._drawRiggingMisfit(x0, x1 - x0, top, barH, endSpan.x + endSpan.w, style.minFont);
            }
        }
    },

    // The fold down a corner piece: a dashed line across the bar.
    _drawRiggingFold(x, top, barH, color) {
        const ctx = this.ctx;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(1, barH * 0.04);
        ctx.setLineDash([Math.max(2, barH * 0.12), Math.max(2, barH * 0.08)]);
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, top + barH);
        ctx.stroke();
        ctx.restore();
    },

    // "Corner" on a corner piece, as big as fits.
    _riggingCornerLabel(x, w, top, barH, style, color = null) {
        const ctx = this.ctx;
        const text = 'Corner';
        let fontPx = Math.max(style.minFont || 10, barH * 0.5);
        ctx.font = `bold ${fontPx}px sans-serif`;
        // never wider than the piece
        const fit = (w * 0.85) / Math.max(1, ctx.measureText(text).width) * fontPx;
        fontPx = Math.max(4, Math.min(fontPx, fit));
        ctx.fillStyle = color || style.textColor;
        ctx.font = `bold ${fontPx}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        this._fillText(text, x + w / 2, top + barH / 2);
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
    _drawRiggingGhost(layer, row, top, barH, style, geo) {
        const g = window.app && window.app._riggingGhost;
        if (!g || g.layerId !== layer.id || g.rowKey !== row.key) return;
        const ctx = this.ctx;
        const off = row.offsets[row.layers.indexOf(layer)];
        const { x, w } = this._riggingSpan(geo, g.start - off, g.size);
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
        if (g.corner != null) {
            // a click here lays the corner's own piece
            this._riggingCornerLabel(x, w, top, barH, style, '#4A90E2');
            ctx.restore();
            return;
        }
        const fontPx = Math.max(style.minFont || 10, Math.min(barH * 0.6, w * 0.5));
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
    _drawRiggingMisfit(x0, width, top, barH, barsEnd, minFont = 10) {
        const ctx = this.ctx;
        const ink = this.printerMode ? PRINTER_INK : '#ff5a4f';
        ctx.save();
        ctx.strokeStyle = ink;
        ctx.lineWidth = 3;
        ctx.setLineDash([barH * 0.25, barH * 0.15]);
        ctx.strokeRect(x0, top, width, barH);
        ctx.setLineDash([]);
        const fontPx = Math.max(minFont, Math.min(barH * 0.4, 28));
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
