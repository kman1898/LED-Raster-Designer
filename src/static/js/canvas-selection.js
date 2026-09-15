// canvas.js mixin: Selection overlays (custom / power / pixel-map), the active-port and circuit badges, and the custom-run readout.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    // One key out of customSelection / powerCustomSelection, resolved to the
    // cabinet it actually names.
    //
    // v0.11.0: those two Sets are keyed by getScopedPanelKey -
    // `${layerId}:${row},${col}` - because a marquee across a screen group has
    // to be able to hold member A's R0C0 AND member B's R0C0, and the unscoped
    // `${row},${col}` key cannot tell them apart. The old parser here was
    // `key.split(',').map(n => parseInt(n, 10))`, and run against a scoped key
    // that yields parseInt("3:0") === 3 - a real row number, a real panel, the
    // WRONG cabinet, silently and with no error at all. So the scoped Sets are
    // read here and pixelMapSelection - still unscoped, still a single-screen
    // feature - keeps the old parser untouched.
    //
    // An unscoped key is still accepted and read as the owner's own cabinet:
    // that is what one that arrives from an older Set, or from a caller that
    // predates the scoping, means, and treating it as owner-relative is exactly
    // today's behaviour.
    _resolveSelectionKey(ownerLayer, key) {
        const app = window.app;
        if (!app || !ownerLayer || typeof key !== 'string') return null;
        const sep = key.indexOf(':');
        let layer = ownerLayer;
        let coords = key;
        if (sep >= 0) {
            coords = key.slice(sep + 1);
            const layerId = parseInt(key.slice(0, sep), 10);
            if (!Number.isNaN(layerId) && layerId !== ownerLayer.id) {
                const layers = (app.project && app.project.layers) || [];
                const found = layers.find(l => l && l.id === layerId) || null;
                // The same reachability rule click-to-add uses: a selection may
                // only reach a peer the owner's path could legally reach. A key
                // naming a deleted layer, or one that has since left the group,
                // resolves to nothing rather than to some other screen's grid.
                const reachable = found && (typeof app.canPathReachLayer === 'function'
                    ? app.canPathReachLayer(ownerLayer, found)
                    : false);
                if (!reachable) return null;
                layer = found;
            }
        }
        const [row, col] = coords.split(',').map(n => parseInt(n, 10));
        const panel = app.getPanelByRowCol(layer, row, col);
        if (!panel) return null;
        return { layer, panel };
    },

    // The drag-select highlight for the two CUSTOM selections, which since
    // v0.11.0 can span the members of a screen group.
    //
    // This overlay runs AFTER the per-canvas render loop has popped its
    // workspace translate, its perspective mirror, every per-layer Show Look
    // offset and every per-layer rotation, so all of that has to be re-applied
    // here - without it (v0.8.7.2.1) the fills landed at workspace (0, 0) in raw
    // processor coords and the user saw no highlight at all while dragging.
    //
    // ONE convention for owner and peer. A per-layer transform can only carry
    // ONE member's Show Look offset and ONE member's rotation, and two members of
    // a wall can disagree on both, so every cabinet - the owner's included -
    // draws in the cross-member frame: the workspace translate and the canvas
    // mirror once, with each cabinet's own rotation and render offset baked into
    // its rect by _crossMemberPanelShim.
    //
    // Before v0.11.0 the owner's half went through _withOverlayLayerTransform,
    // which applied the translate, the mirror and the Show Look offset but NOT
    // the rotation. On a rotated wall that put the owner's highlight a cabinet
    // away from the cabinet it meant while the peer's landed correctly - mid
    // drag-select, half the highlighted cabinets were the ones being pointed at
    // and half were not, and the operator wired the wrong cabinet to the port.
    //
    // Owner first, then peers, so the drawn order is unchanged; for an
    // unrotated screen with no show offset the shim is the identity and the
    // fills are the same rects at the same world coords as before.
    _renderScopedSelectionOverlay(layer, selection) {
        const own = [];
        const peers = [];
        selection.forEach(key => {
            const hit = this._resolveSelectionKey(layer, key);
            if (!hit) return;
            if (hit.layer.id === layer.id) { own.push(hit); return; }
            // v0.11.0: the same rule the crossing cable follows - a member this
            // view does not draw has no cabinets on screen, so there is nothing
            // there to highlight. The key can still legitimately be in the Set:
            // a path scope deliberately keeps hidden members so wiring already
            // drawn onto one survives a hide. Only the OWNER is exempt, because
            // it is the screen the user has open and is drawing on.
            if (hit.layer.visible === false) return;
            peers.push(hit);
        });
        if (own.length === 0 && peers.length === 0) return;

        // One draw frame per MEMBER, not per cabinet: a drag-select can hold
        // thousands of keys and building a frame is O(panels).
        const frames = new Map();
        const frameFor = m => {
            let f = frames.get(m.id);
            if (!f) { f = this._layerDrawFrame(m); frames.set(m.id, f); }
            return f;
        };

        this._withCrossMemberCanvasTransform(layer, () => {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            const fill = hit => {
                const rect = this._drawnPanelRect(frameFor(hit.layer), hit.panel);
                this.ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
            };
            own.forEach(fill);
            peers.forEach(fill);
        });
    },

    renderCustomSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlowEditing(layer)) return;

        const selection = window.app.customSelection || new Set();
        if (selection.size === 0) return;

        this._renderScopedSelectionOverlay(layer, selection);
    },

    renderPowerSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPowerEditing(layer)) return;

        const selection = window.app.powerCustomSelection || new Set();
        if (selection.size === 0) return;

        this._renderScopedSelectionOverlay(layer, selection);
    },

    /**
     * v0.8.7.2.1: shared helper for post-render overlays that need to draw
     * in the same coord frame as the layer they're badging (selection
     * overlays, active port/circuit badges, etc.). Applies the layer's
     * canvas workspace translate, the canvas's Front/Back mirror around
     * its right edge, and the per-layer Show Look offset, exactly the
     * stack the main render loop wraps a layer in.
     *
     * CAUTION (v0.11.0): it does NOT apply the layer's rotation, so anything
     * drawn through it at raw panel coords lands on a rotated screen's
     * UNROTATED grid. Use _withCrossMemberCanvasTransform plus
     * _drawnPanelRect / _crossMemberPanelShim for anything that has to sit on a
     * specific cabinet - that is why the drag-select highlight moved off this.
     * Kept for overlays that only need the layer's frame and draw nothing
     * cabinet-specific.
     */
    _withOverlayLayerTransform(layer, fn) {
        const wsOff = (typeof this._layerCanvasOffset === 'function')
            ? this._layerCanvasOffset(layer) : { wx: 0, wy: 0 };
        const cid = (typeof this._effectiveLayerCanvasId === 'function')
            ? this._effectiveLayerCanvasId(layer) : null;
        const arr = (window.app && window.app.project && window.app.project.canvases) || [];
        const c = Array.isArray(arr) ? arr.find(x => x && x.id === cid) : null;
        const mirrorActive = !!(c && this._isCanvasMirrored && this._isCanvasMirrored(c));
        const { dx, dy } = (typeof this.getLayerRenderOffset === 'function')
            ? this.getLayerRenderOffset(layer) : { dx: 0, dy: 0 };

        this.ctx.save();
        if (wsOff.wx || wsOff.wy) this.ctx.translate(wsOff.wx, wsOff.wy);
        if (mirrorActive) {
            const crw = (this.isShowLookView() && c.show_raster_width) || c.raster_width || 0;
            this.ctx.translate(crw, 0);
            this.ctx.scale(-1, 1);
        }
        if (dx || dy) this.ctx.translate(dx, dy);
        try { fn(); } finally { this.ctx.restore(); }
    },

    // DELIBERATELY UNSCOPED, unlike the two custom-selection overlays above.
    // pixelMapSelection is bulk hide / blank / half-tile WITHIN one screen -
    // nothing about it is grouped, it never leaves currentLayer, and it keeps
    // the plain `${row},${col}` getPanelKey. Do not "tidy" this into
    // _renderScopedSelectionOverlay: the scoped resolver would still read these
    // keys correctly, but pointing a second feature at the group machinery buys
    // nothing and would make a single-screen action start caring about peers.
    renderPixelMapSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const selection = window.app.pixelMapSelection;
        if (!selection || selection.size === 0) return;
        const layer = window.app.currentLayer;
        // v0.8 multi-canvas: panels are drawn at canvas-relative coords; the
        // workspace position of the layer's parent canvas needs to be applied
        // so the overlay lands ON the layer the user is editing instead of
        // at workspace (0,0) where it visually overlapped Canvas 1's panels.
        const wsOff = (typeof window.app._getLayerWorkspaceOffset === 'function')
            ? window.app._getLayerWorkspaceOffset(layer) : { wx: 0, wy: 0 };
        this.ctx.save();
        if (wsOff.wx || wsOff.wy) this.ctx.translate(wsOff.wx, wsOff.wy);
        // v0.9.3: rotate the highlight with the screen so it lands on the same
        // panels the (rotated) render shows.
        const _rot = this._beginLayerRotation(layer);
        this.ctx.lineWidth = 2 / this.zoom;
        selection.forEach(key => {
            const [row, col] = key.split(',').map(n => parseInt(n, 10));
            const panel = window.app.getPanelByRowCol(layer, row, col);
            if (!panel) return;
            // Hidden ("blank") panels render as just a faint dashed outline,
            // so the normal 0.35-alpha selection tint barely shows against the
            // dark background. Use a stronger fill on hidden panels so the
            // user can clearly see which blank cells are part of the selection.
            if (panel.hidden) {
                this.ctx.fillStyle = 'rgba(74, 144, 226, 0.55)';
            } else {
                this.ctx.fillStyle = 'rgba(74, 144, 226, 0.35)';
            }
            this.ctx.strokeStyle = 'rgba(74, 144, 226, 1.0)';
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
        });
        if (_rot) this.ctx.restore();
        this.ctx.restore();
    },

    renderPixelMapSelectionBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const selection = window.app.pixelMapSelection;
        if (!selection || selection.size === 0) return;
        const count = selection.size;
        const label = `${count.toLocaleString()} panel${count === 1 ? '' : 's'} selected`;

        // Draw in screen-space (above the world transform) so size doesn't depend on zoom.
        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        const padX = 14;
        const padY = 8;
        const fontPx = 13;
        this.ctx.font = `600 ${fontPx}px -apple-system, "Segoe UI", sans-serif`;
        const textWidth = this.ctx.measureText(label).width;
        const boxW = textWidth + padX * 2;
        const boxH = fontPx + padY * 2;
        const x = 20;
        const y = 20;
        this.ctx.fillStyle = 'rgba(74, 144, 226, 0.95)';
        this.ctx.beginPath();
        if (this.ctx.roundRect) this.ctx.roundRect(x, y, boxW, boxH, 6);
        else this.ctx.rect(x, y, boxW, boxH);
        this.ctx.fill();
        this.ctx.fillStyle = '#fff';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(label, x + padX, y + boxH / 2);
        this.ctx.restore();
    },

    /**
     * Wiring perspective badge, "BACK VIEW" in screen-space corner when
     * Data Flow / Power are rendering in back perspective. Shown in both
     * interactive view and export so the printed map is unambiguous.
     * Front view shows nothing (clutter-free default; Front is implied).
     */
    renderPerspectiveBadge() {
        if (this.viewMode !== 'data-flow' && this.viewMode !== 'power') return;
        if (!this.isMirroredView()) return;
        const label = 'BACK';
        const arr = (window.app && window.app.project && Array.isArray(window.app.project.canvases))
            ? window.app.project.canvases : [];
        // v0.8.6: per-canvas badge so a mixed-perspective workspace makes
        // it obvious which canvas is flipped. Legacy single-canvas
        // projects fall back to the original viewport-corner badge.
        if (arr.length === 0) {
            this._drawBackBadgeAt(label, this.canvas.width - 20, 20, 'right', this.canvas.width);
            return;
        }
        const useShow = this.isShowLookView();
        arr.forEach(c => {
            if (!c || c.visible === false) return;
            if (!this._isCanvasMirrored(c)) return;
            const ws = this._canvasWorkspace(c);
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            // World top-right of canvas → screen coords (account for pan/zoom).
            const screenX = (ws.wx + w) * this.zoom + this.panX;
            const screenY = ws.wy * this.zoom + this.panY;
            // v0.8.7.1: badge scales with the canvas's on-screen size so it
            // doesn't dominate small/zoomed-out canvases. Pass the canvas's
            // screen-pixel width to _drawBackBadgeAt; it picks a font/pad
            // proportional to that (clamped to min/max so it stays
            // readable at extreme zooms).
            const canvasScreenW = w * this.zoom;
            // v0.8.7.2: skip the badge when the canvas is so small on
            // screen that the badge would dominate it. The dashed canvas
            // outline + flipped content already telegraph back-view at
            // any zoom; the badge is just a confirmation tag for normal
            // zoom levels.
            if (canvasScreenW < 110) return;
            // Anchor to canvas corner with a small inset; clamp so badge
            // stays visible if the canvas top-right is offscreen.
            const x = Math.max(20, Math.min(this.canvas.width - 20, screenX - 4));
            const y = Math.max(8, Math.min(this.canvas.height - 24, screenY + 4));
            this._drawBackBadgeAt(label, x, y, 'right', canvasScreenW);
        });
    },

    _drawBackBadgeAt(label, anchorX, anchorY, align, canvasScreenW) {
        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        // v0.8.7.2: badge size is purely proportional to canvas screen
        // width, no minimum clamp, since at extreme zoom-out the canvas
        // itself shrinks faster than the badge would. Caller skips the
        // badge entirely when canvasScreenW falls below the
        // "too small to label" threshold.
        const targetW = Math.min(110, (canvasScreenW || 600) * 0.10);
        const fontPx = Math.max(9, Math.min(13, Math.round(targetW / 5.2)));
        const padX = Math.max(4, Math.round(fontPx * 0.6));
        const padY = Math.max(2, Math.round(fontPx * 0.35));
        this.ctx.font = `700 ${fontPx}px -apple-system, "Segoe UI", sans-serif`;
        const textWidth = this.ctx.measureText(label).width;
        const boxW = textWidth + padX * 2;
        const boxH = fontPx + padY * 2;
        const x = align === 'right' ? (anchorX - boxW) : anchorX;
        const y = anchorY;
        this.ctx.fillStyle = 'rgba(217, 80, 0, 0.95)';
        this.ctx.beginPath();
        const radius = Math.max(3, Math.round(fontPx * 0.4));
        if (this.ctx.roundRect) this.ctx.roundRect(x, y, boxW, boxH, radius);
        else this.ctx.rect(x, y, boxW, boxH);
        this.ctx.fill();
        this.ctx.fillStyle = '#fff';
        this.ctx.textBaseline = 'middle';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(label, x + padX, y + boxH / 2);
        this.ctx.restore();
    },

    renderCustomActivePortBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlowEditing(layer)) return;
        const portNum = layer.customPortIndex || 1;
        const label = window.app.getPortLabelText(layer, portNum, 'primary');
        const committedCount = this._getCustomPortPanelCount(layer, portNum);
        const selectedCount = (window.app.customSelection && window.app.customSelection.size) || 0;
        const fill = (typeof window.app.customRunFill === 'function')
            ? window.app.customRunFill(layer, 'data', portNum) : null;
        this._drawActiveBadge(label, committedCount, selectedCount, 'rgba(0, 255, 0, 0.9)',
            fill, 'port');
    },

    renderPowerActiveCircuitBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPowerEditing(layer)) return;
        const circuitNum = layer.powerCustomIndex || 1;
        const label = window.app.getPowerCircuitLabel(layer, circuitNum);
        const committedCount = this._getCustomPowerCircuitPanelCount(layer, circuitNum);
        const selectedCount = (window.app.powerCustomSelection && window.app.powerCustomSelection.size) || 0;
        const fill = (typeof window.app.customRunFill === 'function')
            ? window.app.customRunFill(layer, 'power', circuitNum) : null;
        this._drawActiveBadge(label, committedCount, selectedCount, 'rgba(0, 255, 102, 0.9)',
            fill, 'circuit');
    },

    // "N on port" / "N on circuit". v0.11.0: counted through the shared path
    // resolver so a step that landed on a group peer counts too - the badge is
    // telling the user how many cabinets they have wired to the port they are
    // drawing, and a cabinet on the next member is still wired to it. Both
    // resolvers drop steps whose cabinet no longer exists or is hidden, which
    // is what the hand-rolled reduce did.
    _getCustomPortPanelCount(layer, portNum) {
        const path = (layer.customPortPaths && layer.customPortPaths[portNum]) || [];
        if (!Array.isArray(path)) return 0;
        if (!window.app || typeof window.app.getPanelByRowCol !== 'function') return path.length;
        return this._resolvePathPanels(layer, path).length;
    },

    _getCustomPowerCircuitPanelCount(layer, circuitNum) {
        const path = (layer.powerCustomPaths && layer.powerCustomPaths[circuitNum]) || [];
        if (!Array.isArray(path)) return 0;
        if (!window.app || typeof window.app.getPanelByRowCol !== 'function') return path.length;
        return this._resolvePathPanels(layer, path).length;
    },

    // The active-port / active-circuit READOUT while a custom flow is being
    // built. It used to be painted at 72px in the canvas's top-left, over
    // whatever cabinets sat there ("when i am in custom mode on data and
    // power this is in my way very often" - the user, 2026-09-05); it now
    // lives in the canvas strip above the canvas (#custom-run-readout, next
    // to Fit / 1:1) and nothing is drawn on the wall. The name and the
    // signature are kept: the two view-specific callers and the tests know
    // this method, and the text it settles on is still the one authority.
    //  - `committed` = panels already assigned to this port/circuit
    //  - `selected`  = panels currently highlighted by a drag-select but
    //    not yet applied. Shown in yellow only when > 0 so the user can
    //    distinguish "locked in" vs "pending" at a glance.
    //  - `fill`      = app.customRunFill for the run: when a cap is known the
    //    committed pill reads "9/14 on circuit" against it (whole-cabinet
    //    equivalents, so a half-tile shows as a fraction) and "14/14 on
    //    circuit · full" in the warning colour once another whole cabinet
    //    would not fit. No cap known, and the pill counts as it always has.
    // The text shown is kept on `_lastActiveBadge` so it can be read back
    // without scraping the DOM. `labelColor` is the view's green; the strip
    // keys its label colour off `noun` (port = data, circuit = power).
    _drawActiveBadge(label, committed, selected, labelColor, fill = null, noun = 'port') {
        const capped = !!(fill && fill.known);
        const isFull = capped && !!fill.full;
        const usedText = capped && window.app && typeof window.app._formatRunUsed === 'function'
            ? window.app._formatRunUsed(fill.used) : `${committed}`;
        const committedText = capped
            ? `${usedText}/${fill.count} on ${noun}${isFull ? ' · full' : ''}`
            : `${committed} on ${noun}`;
        this._lastActiveBadge = { label, pill: committedText, full: isFull, selected };
        this._activeBadgeShown = true;
        this._syncCustomRunReadout({
            label, pill: committedText, full: isFull, selected,
            committed, kind: noun === 'circuit' ? 'power' : 'data',
        });
    },

    // Writes the readout into the strip, or hides it. Called with a state by
    // _drawActiveBadge and with null from render()'s post-pass whenever the
    // frame drew no badge - so leaving custom mode, switching view, changing
    // layer or undoing all clear it on the very next frame, with no second
    // computation of the label or the count anywhere.
    _syncCustomRunReadout(state) {
        const el = document.getElementById('custom-run-readout');
        if (!el) return;
        if (!state) {
            if (!el.hidden) el.hidden = true;
            return;
        }
        const labelEl = el.querySelector('.cr-label');
        const pillEl = el.querySelector('.cr-pill');
        const selEl = el.querySelector('.cr-selected');
        if (labelEl && labelEl.textContent !== state.label) labelEl.textContent = state.label;
        if (pillEl && pillEl.textContent !== state.pill) pillEl.textContent = state.pill;
        el.classList.toggle('cr-full', !!state.full);
        el.classList.toggle('cr-empty', !state.full && !(state.committed > 0));
        el.classList.toggle('cr-power', state.kind === 'power');
        el.classList.toggle('cr-data', state.kind !== 'power');
        if (selEl) {
            const show = state.selected > 0;
            const text = show ? `+${state.selected} selected` : '';
            if (selEl.textContent !== text) selEl.textContent = text;
            if (selEl.hidden === show) selEl.hidden = !show;
        }
        if (el.hidden) el.hidden = false;
    },
});
