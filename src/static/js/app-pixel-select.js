// app-pixel-select: cabinet selection for LEDRasterApp - the custom-flow
// and custom-power edit modes (enter, leave, selection sets, marquee) and
// the Pixel Map bulk-select with its half-tile / blank bulk verbs.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _PixelSelect {

    isCustomFlow(layer) {
        return !!layer && layer.flowPattern === 'custom';
    }

    // Is the path-EDITING machinery live for this layer right now? True in
    // whole-screen custom mode, exactly as every gate read before, and ALSO
    // while ONE overridden port is open for redrawing (see the per-run
    // override section below). Every editing gate - the click, the marquee,
    // the arrow keys, the pattern-on-selection - reads THIS; every gate about
    // what the map IS (rendering, counting, the group crossing) keeps reading
    // isCustomFlow, because a screen with one redrawn port is still an
    // automatic screen.
    isCustomFlowEditing(layer) {
        return this.isCustomFlow(layer) || this._isOverrideEditing(layer, 'data');
    }

    isCustomPowerEditing(layer) {
        return this.isCustomPower(layer) || this._isOverrideEditing(layer, 'power');
    }

    ensureCustomFlowState(layer) {
        if (!layer) return;
        if (!layer.customPortPaths) layer.customPortPaths = {};
        if (!layer.customPortIndex) layer.customPortIndex = 1;
    }

    toggleCustomFlowMode(enabled) {
        if (!this.currentLayer) return;
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.flowPattern && layer.flowPattern !== 'custom') {
                    layer.lastFlowPattern = layer.flowPattern;
                }
                layer.flowPattern = 'custom';
                this.ensureCustomFlowState(layer);
            } else {
                layer.flowPattern = layer.lastFlowPattern || 'tl-h';
            }
        });
        if (!enabled) {
            this.customSelectMode = false;
            this.customSelection.clear();
        }
        this.saveState('Custom Mode Toggle');
        this.saveClientSideProperties();
        // Recompute port count BEFORE the server roundtrip so the layer's
        // _portsRequired is fresh when preservedProps captures it.
        this.updatePortCapacityDisplay();
        this.updateLayers(this.getSelectedLayers());
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    updateCustomFlowUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('custom-flow-controls');
            if (container) container.style.display = 'none';
            return;
        }
        // The editing predicate, not the pattern: while one overridden port is
        // open for redrawing the same controls (active port, clear, patterns)
        // are the tools of THAT edit, so the panel shows without the screen
        // ever leaving its automatic pattern.
        const isCustom = this.currentLayer && this.isCustomFlowEditing(this.currentLayer);
        const container = document.getElementById('custom-flow-controls');
        const portInput = document.getElementById('custom-active-port-input');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.customPortIndex || 1}`;
        }
        // Only while the DATA view is the one on screen. There is one canvas
        // cursor and both this and updateCustomPowerUI were writing it from
        // their own pattern with no view test, so whichever ran last won -
        // and loadLayerToInputs runs the power one second. A screen with
        // custom data flow and automatic power (the normal state for a
        // grouped screen, since the flow pattern is shared across members but
        // power need not be) lost its crosshair in Data Flow the moment the
        // layer was re-selected, while custom drawing was still active.
        if (window.canvasRenderer && window.canvasRenderer.viewMode === 'data-flow') {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
        this._syncCustomFillReadout('data');
    }

    isCustomPower(layer) {
        return !!layer && layer.powerFlowPattern === 'custom';
    }

    ensureCustomPowerState(layer) {
        if (!layer) return;
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (!layer.powerCustomIndex) layer.powerCustomIndex = 1;
    }

    toggleCustomPowerMode(enabled) {
        if (!this.currentLayer) return;
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.powerFlowPattern && layer.powerFlowPattern !== 'custom') {
                    layer.lastPowerFlowPattern = layer.powerFlowPattern;
                }
                layer.powerFlowPattern = 'custom';
                layer.powerCustomPath = true;
                this.ensureCustomPowerState(layer);
            } else {
                layer.powerFlowPattern = layer.lastPowerFlowPattern || 'tl-h';
                layer.powerCustomPath = false;
            }
        });
        if (!enabled) {
            this.powerCustomSelection.clear();
        }
        this.saveState('Power Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updateLayers(this.getSelectedLayers());
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    updateCustomPowerUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('power-custom-controls');
            if (container) container.style.display = 'none';
            return;
        }
        // Editing predicate, not the pattern - same reason as the data twin.
        const isCustom = this.currentLayer && this.isCustomPowerEditing(this.currentLayer);
        const container = document.getElementById('power-custom-controls');
        const portInput = document.getElementById('power-custom-active');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.powerCustomIndex || 1}`;
        }
        // Power view only - see the note on the same line in
        // updateCustomFlowUI. Unguarded, this one always won.
        if (window.canvasRenderer && window.canvasRenderer.viewMode === 'power') {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
        this._syncCustomFillReadout('power');
    }

    getPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    getPanelByRowCol(layer, row, col) {
        if (!layer || !layer.panels) return null;
        return layer.panels.find(p => p.row === row && p.col === col) || null;
    }

    // v0.11.0: customSelection is keyed by getScopedPanelKey, not getPanelKey -
    // see _selectPathPanelsInRect for why. `panelLayer` names the screen the
    // cabinet came from when it is not currentLayer; leaving it out resolves
    // it, so every existing single-screen caller is unchanged.
    togglePanelSelection(panel, panelLayer = null) {
        if (!panel) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer) || owner;
        if (!source) return;
        const key = this.getScopedPanelKey(source.id, panel);
        if (this.customSelection.has(key)) {
            this.customSelection.delete(key);
        } else {
            this.customSelection.add(key);
        }
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    clearCustomSelection() {
        this.customSelection.clear();
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    // The power-side twin. canvas.js used to clear powerCustomSelection inline
    // and separately remember to refresh the UI and re-render; the data side
    // has had this helper all along.
    clearPowerCustomSelection() {
        this.powerCustomSelection.clear();
        this.updateCustomPowerUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    /**
     * Marquee-select the cabinets under `rect` for a manual path owned by
     * `ownerLayer`, filling `selection` with SCOPED keys.
     *
     * v0.11.0: the marquee now sweeps every member of the owner's group, the
     * same reachability rule click-to-add uses. Before this it walked one
     * layer, which is why dragging a box across a mixed-cabinet wall picked up
     * only half of it.
     *
     * The Set has to be keyed by getScopedPanelKey and not getPanelKey:
     * member A's R0C0 and member B's R0C0 are two different cabinets, and under
     * the bare `${row},${col}` they are ONE entry - so a cross-member marquee
     * could only ever have committed the owner's own cabinets under the peer's
     * row and column. Silently wrong, not partly working. getPanelKey itself is
     * untouched, because pixelMapSelection still uses it (one screen, no
     * groups) and its overlay still parses it back with split(',').
     *
     * Each member converts the WORLD rect into its OWN frame:
     * _getLayerWorkspaceOffset is per-layer (canvas workspace + that layer's
     * Show Look delta), and rotation is undone per member the way
     * selectPixelMapPanelsInRect and canvas.js getPanelAt do it. Note the
     * members of one canvas already share an origin - _build_panels lays each
     * member's columns out from its own offset_x - so there is no second offset
     * to apply on top of that, and applying one would drag the peer's hit-test
     * off the wall.
     */
    _selectPathPanelsInRect(ownerLayer, rect, selection) {
        selection.clear();
        if (!ownerLayer || !rect) return;
        const _r = window.canvasRenderer;
        // Selection scope, not path scope: a marquee must not sweep up a
        // member the user cannot see or click. See getSelectionScopeLayers.
        this.getSelectionScopeLayers(ownerLayer).forEach(member => {
            if (!member || !Array.isArray(member.panels)) return;
            const off = this._getLayerWorkspaceOffset(member);
            let x1 = Math.min(rect.x1, rect.x2) - off.wx;
            let x2 = Math.max(rect.x1, rect.x2) - off.wx;
            let y1 = Math.min(rect.y1, rect.y2) - off.wy;
            let y2 = Math.max(rect.y1, rect.y2) - off.wy;
            // Rotation is 90/180/270 only, so the unrotated rect is still
            // axis-aligned and the corners bound it exactly.
            if (_r && typeof _r._unrotatePointForLayer === 'function') {
                const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                    .map(([x, y]) => _r._unrotatePointForLayer(x, y, member));
                x1 = Math.min(...corners.map(c => c.x)); x2 = Math.max(...corners.map(c => c.x));
                y1 = Math.min(...corners.map(c => c.y)); y2 = Math.max(...corners.map(c => c.y));
            }
            member.panels.forEach(panel => {
                if (panel.hidden) return;
                const intersects = panel.x <= x2 && (panel.x + panel.width) >= x1 &&
                    panel.y <= y2 && (panel.y + panel.height) >= y1;
                if (intersects) selection.add(this.getScopedPanelKey(member.id, panel));
            });
        });
    }

    // `layer` is the path's OWNER - the screen whose port is being drawn - and
    // its group decides how far the marquee reaches. The signature is
    // unchanged, so canvas.js still passes currentLayer.
    selectPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomFlowEditing(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.customSelection);
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    // ---------- Pixel Map bulk-select (panel selection on the Pixel Map tab) ----------

    selectPixelMapPanelsInRect(layer, rect) {
        if (!layer || !rect) return;
        this.pixelMapSelection.clear();
        // rect is in workspace coords; panel coords are canvas-relative,
        // shift by the layer's parent canvas's workspace offset before
        // comparing. (No-op for single-canvas projects.)
        const off = this._getLayerWorkspaceOffset(layer);
        let x1 = Math.min(rect.x1, rect.x2) - off.wx;
        let x2 = Math.max(rect.x1, rect.x2) - off.wx;
        let y1 = Math.min(rect.y1, rect.y2) - off.wy;
        let y2 = Math.max(rect.y1, rect.y2) - off.wy;
        // v0.9.3: if the screen is rotated, map the marquee back into the screen's
        // unrotated panel space (rotation is 90/180/270, so it stays axis-aligned).
        const _r = window.canvasRenderer;
        if (_r && _r._unrotatePointForLayer) {
            const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                .map(([x, y]) => _r._unrotatePointForLayer(x, y, layer));
            x1 = Math.min(...corners.map(c => c.x)); x2 = Math.max(...corners.map(c => c.x));
            y1 = Math.min(...corners.map(c => c.y)); y2 = Math.max(...corners.map(c => c.y));
        }
        const minX = x1, maxX = x2, minY = y1, maxY = y2;
        // Include hidden ("blank") panels so they can be selected for bulk
        // restore via the sidebar / Alt+click action.
        (layer.panels || []).forEach(panel => {
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.pixelMapSelection.add(this.getPanelKey(panel));
        });
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    togglePixelMapPanelSelection(panel) {
        if (!panel) return;
        const key = this.getPanelKey(panel);
        if (this.pixelMapSelection.has(key)) {
            this.pixelMapSelection.delete(key);
        } else {
            this.pixelMapSelection.add(key);
        }
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    clearPixelMapSelection() {
        if (!this.pixelMapSelection || this.pixelMapSelection.size === 0) return;
        this.pixelMapSelection.clear();
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    getPixelMapSelectedPanels() {
        if (!this.currentLayer || !this.currentLayer.panels) return [];
        return this.currentLayer.panels.filter(p => this.pixelMapSelection.has(this.getPanelKey(p)));
    }

    /**
     * Auto-detect half-tile direction for a panel based on its visible neighbors:
     *  - top/bottom edge (no neighbor above or below): 'height'
     *  - left/right edge (no neighbor left or right): 'width'
     *  - corner (two missing): default 'height' (top/bottom is the common case)
     *  - interior (all four neighbors visible): 'height' (rare; user can force-W via UI)
     */
    autoDetectHalfDirection(layer, panel) {
        if (!layer || !panel) return 'height';
        const get = (r, c) => (layer.panels || []).find(p => p.row === r && p.col === c);
        const neighborVisible = (r, c) => {
            const n = get(r, c);
            return !!(n && !n.hidden);
        };
        const hasAbove = neighborVisible(panel.row - 1, panel.col);
        const hasBelow = neighborVisible(panel.row + 1, panel.col);
        const hasLeft = neighborVisible(panel.row, panel.col - 1);
        const hasRight = neighborVisible(panel.row, panel.col + 1);
        const verticalEdge = !hasAbove || !hasBelow;
        const horizontalEdge = !hasLeft || !hasRight;
        if (verticalEdge && !horizontalEdge) return 'height';
        if (horizontalEdge && !verticalEdge) return 'width';
        // Corner or interior, default to 'height' (top/bottom edges are the common case).
        return 'height';
    }

    async setPanelsHalfTileBulk(panels, halfTile) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        // For 'auto', vote across the selection: pick the direction the
        // majority of panels would auto-detect to, then apply that uniformly.
        // Avoids a row of selected panels splitting into different directions
        // when one happens to be an interior panel.
        let resolved = halfTile;
        if (halfTile === 'auto') {
            let widthVotes = 0;
            let heightVotes = 0;
            panels.forEach(p => {
                const d = this.autoDetectHalfDirection(this.currentLayer, p);
                if (d === 'width') widthVotes++;
                else heightVotes++;
            });
            // Tie goes to 'height' (top/bottom is the more common case).
            resolved = widthVotes > heightVotes ? 'width' : 'height';
        }
        const body = {
            panels: panels.map(p => ({
                id: p.id,
                halfTile: resolved,
            })),
        };
        // Apply locally so the canvas updates immediately while the POST is in
        // flight; the flags alone are enough to redraw at the old geometry.
        panels.forEach(p => { p.halfTile = resolved; });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // v0.10.8: the snapshot must wait for the server's rebuilt layer.
        // Setting halfTile resizes every panel, and that rebuild only happens
        // server-side, so a saveState() taken here would pair the new flags
        // with full-size geometry. Undo restored that mismatch and PUT it back
        // to /api/project, which does no rebuild — making the corruption
        // permanent. Merge the response first, snapshot second.
        let applied = false;
        try {
            const res = await fetch(`/api/layer/${layerId}/panels/set_half_tile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data && data.layer) {
                applied = this.applyServerLayer(data.layer, 'bulk_set_half_tile');
                if (window.canvasRenderer) window.canvasRenderer.render();
            }
        } catch (err) {
            console.error('setPanelsHalfTileBulk failed', err);
        }
        // No rebuilt layer means no trustworthy snapshot to take. Skip the
        // history entry rather than record the stale-geometry one; the socket
        // `layer_updated` event still reconciles the live state.
        if (applied) this.saveState('Bulk Set Half-tile');
        sendClientLog && sendClientLog('bulk_set_half_tile', {
            layer_id: layerId,
            count: panels.length,
            mode: halfTile,
        });
    }

    /**
     * Bulk hide/show panels, what the UI calls "Set Blank" (matching the
     * Alt+click behaviour, which toggles the per-panel `hidden` flag so the
     * cabinet disappears from the wall layout).
     */
    async setPanelsBlankBulk(panels, blank) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        const targetHidden = !!blank;
        const toChange = panels.filter(p => !!p.hidden !== targetHidden);
        if (toChange.length === 0) return;
        // Apply locally so the canvas updates immediately while the server PUT is in flight.
        toChange.forEach(p => { p.hidden = targetHidden; });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // v0.10.8.1: same contract as setPanelsHalfTileBulk above. Hiding a
        // panel re-anchors any neighbouring half-tile, and that rebuild only
        // happens server-side, so a saveState() taken here would snapshot the
        // old geometry. Merge the response first, snapshot second.
        let applied = false;
        try {
            const res = await fetch(`/api/layer/${layerId}/panels/set_hidden`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ panels: toChange.map(p => ({ id: p.id, hidden: targetHidden })) }),
            });
            const data = await res.json();
            if (data && data.layer) {
                applied = this.applyServerLayer(data.layer, 'bulk_set_blank');
                if (window.canvasRenderer) window.canvasRenderer.render();
            }
        } catch (err) {
            console.error('setPanelsBlankBulk failed', err);
        }
        // No rebuilt layer means no trustworthy snapshot to take. Skip the
        // history entry rather than record the stale-geometry one; the socket
        // `layer_updated` event still reconciles the live state.
        if (applied) this.saveState('Bulk Set Blank');
        sendClientLog && sendClientLog('bulk_set_blank', {
            layer_id: layerId,
            count: toChange.length,
            hidden: targetHidden,
        });
    }

    /**
     * Update the sidebar bulk-action panel based on current selection.
     * Shows count + action buttons when at least one panel is selected,
     * hides when empty.
     */
    updatePixelMapBulkActionUI() {
        const panel = document.getElementById('pixel-map-bulk-actions');
        if (!panel) return;
        const count = this.pixelMapSelection ? this.pixelMapSelection.size : 0;
        const countEl = document.getElementById('pixel-map-bulk-count');
        // Wrap label too so we can fix pluralization without rebuilding markup.
        const labelEl = document.getElementById('pixel-map-bulk-label');
        if (count > 0) {
            panel.style.display = 'block';
            if (countEl) countEl.textContent = count.toLocaleString();
            if (labelEl) labelEl.textContent = count === 1 ? 'panel' : 'panels';
        } else {
            panel.style.display = 'none';
        }
    }

    // Power's half of the marquee. Same scoping rule, same owner semantics -
    // see _selectPathPanelsInRect.
    selectPowerPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomPowerEditing(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.powerCustomSelection);
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }
}

for (const k of Object.getOwnPropertyNames(_PixelSelect.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PixelSelect.prototype, k));
    }
}
