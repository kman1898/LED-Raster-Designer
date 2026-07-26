// app-canvas-ui: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _CanvasUi {
    regroupLayersByCanvas(container) {
        const project = this.project;
        if (!project || !Array.isArray(project.canvases) || project.canvases.length === 0) return;
        const activeId = project.active_canvas_id;

        // Snapshot the existing rendered layer items, keyed by id, then clear.
        const layerNodes = new Map();
        container.querySelectorAll('.layer-item').forEach(el => {
            const lid = parseInt(el.dataset.layerId, 10);
            if (Number.isFinite(lid)) layerNodes.set(lid, el);
        });
        container.innerHTML = '';

        // v0.8.6.1: pick the layer's view-effective canvas so the sidebar
        // grouping matches what the canvas is rendering. Show Look / Data /
        // Power group by `show_canvas_id || canvas_id`; Pixel Map / Cabinet
        // ID group by `canvas_id`.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const layerCanvasId = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;

        // Sidebar shows canvases in array order, with each canvas's
        // (reverse-ordered) layers underneath, matches the existing
        // newest-on-top convention.
        project.canvases.forEach(canvas => {
            const group = this.buildCanvasGroupEl(canvas, activeId === canvas.id);
            container.appendChild(group);
            const body = group.querySelector('.canvas-group-body');

            // Append matching layer nodes in reverse render order
            // (standard, newest on top).
            const reversed = [...project.layers].reverse();
            reversed.forEach(layer => {
                if (layerCanvasId(layer) !== canvas.id) return;
                const node = layerNodes.get(layer.id);
                if (node) body.appendChild(node);
            });
        });
    }

    buildCanvasGroupEl(canvas, isActive) {
        const wrap = document.createElement('div');
        wrap.className = 'canvas-group' + (isActive ? ' active' : '');
        if (canvas.visible === false) wrap.classList.add('hidden');
        wrap.dataset.canvasId = canvas.id;
        wrap.style.setProperty('--canvas-color', canvas.color || '#4A90E2');

        wrap.innerHTML = `
            <div class="canvas-group-header" draggable="true" title="Click to activate · Drag to reorder">
                <span class="canvas-drag-handle" title="Drag to reorder">⋮⋮</span>
                <span class="canvas-color-swatch" style="background:${canvas.color || '#4A90E2'};"></span>
                <input class="canvas-name-input" type="text" value="${this._escapeAttr(canvas.name || 'Canvas')}" readonly>
                <button class="canvas-vis-btn" title="Toggle canvas visibility">${canvas.visible === false ? '👁‍🗨' : '👁'}</button>
                <button class="canvas-menu-btn" title="Canvas actions">⋮</button>
            </div>
            <div class="canvas-group-body"></div>
            <div class="canvas-group-footer">
                <button class="btn btn-secondary canvas-add-btn" title="Add a layer to this canvas">+ Add</button>
            </div>
        `;
        this._wireCanvasGroupEl(wrap, canvas);
        return wrap;
    }

    _escapeAttr(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    _wireCanvasGroupEl(wrap, canvas) {
        const header = wrap.querySelector('.canvas-group-header');
        const nameInput = wrap.querySelector('.canvas-name-input');
        const visBtn = wrap.querySelector('.canvas-vis-btn');
        const menuBtn = wrap.querySelector('.canvas-menu-btn');
        const addBtn = wrap.querySelector('.canvas-add-btn');

        // Click header anywhere except on inputs/buttons => activate canvas.
        header.addEventListener('click', (e) => {
            if (e.target.closest('button') || e.target.closest('input')) return;
            this.setActiveCanvas(canvas.id);
        });

        // Double-click name to rename inline.
        nameInput.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            nameInput.readOnly = false;
            nameInput.focus();
            nameInput.select();
        });
        const commitName = () => {
            nameInput.readOnly = true;
            const newName = nameInput.value.trim();
            if (newName && newName !== canvas.name) {
                this.updateCanvas(canvas.id, { name: newName });
            } else {
                nameInput.value = canvas.name || '';
            }
        };
        nameInput.addEventListener('blur', commitName);
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
            else if (e.key === 'Escape') { nameInput.value = canvas.name || ''; nameInput.blur(); }
            if (!nameInput.readOnly) e.stopPropagation();
        });

        visBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.updateCanvas(canvas.id, { visible: canvas.visible === false });
        });

        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openCanvasMenu(canvas, menuBtn);
        });

        addBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openCanvasAddMenu(canvas, addBtn);
        });

        // -- Drag & drop --
        // Drag canvas header => reorder canvases.
        header.addEventListener('dragstart', (e) => {
            // If the drag originated from the name input (when readonly was true
            // and user grabbed the field), still treat as canvas reorder.
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('application/x-canvas-id', canvas.id);
            e.dataTransfer.setData('text/plain', `canvas:${canvas.id}`);
            this._dragCanvasId = canvas.id;
            wrap.classList.add('dragging');
        });
        header.addEventListener('dragend', () => {
            wrap.classList.remove('dragging');
            this._dragCanvasId = null;
        });

        // Drop target: canvas header accepts canvas-reorder OR layer drop.
        wrap.addEventListener('dragover', (e) => {
            // Layer being dragged onto this canvas => indicate cross-canvas drop.
            const isCanvas = !!this._dragCanvasId;
            const isLayer = this.dragLayerId != null && !isCanvas;
            if (!isCanvas && !isLayer) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = (isLayer && (e.metaKey || e.altKey)) ? 'copy' : 'move';
            wrap.classList.add('drag-target');
        });
        wrap.addEventListener('dragleave', (e) => {
            // Only clear the highlight when leaving the wrap entirely.
            if (!wrap.contains(e.relatedTarget)) wrap.classList.remove('drag-target');
        });
        wrap.addEventListener('drop', (e) => {
            wrap.classList.remove('drag-target');
            // Canvas reorder?
            const draggedCanvasId = this._dragCanvasId
                || e.dataTransfer.getData('application/x-canvas-id');
            if (draggedCanvasId && draggedCanvasId !== canvas.id) {
                e.preventDefault();
                this.reorderCanvasBeforeTarget(draggedCanvasId, canvas.id);
                return;
            }
            // Cross-canvas layer drop?
            // Only handle when the drop landed on the canvas header / footer
            // (not on an existing layer-item inside this canvas), otherwise
            // we would double-fire alongside the within-list reorder handler.
            if (this.dragLayerId != null) {
                const onLayerItem = e.target.closest && e.target.closest('.layer-item');
                if (onLayerItem) return;
                const draggedLayer = (this.project.layers || []).find(l => l.id === this.dragLayerId);
                if (!draggedLayer) return;
                // v0.8.6.1: in Show Look / Data / Power, dropping onto a
                // canvas group rewrites show_canvas_id (Show Look layer
                // membership) so Pixel Map's canvas_id stays untouched.
                // Pixel Map / Cabinet ID drops still rewrite canvas_id.
                const _isShowView = !!(window.canvasRenderer
                    && window.canvasRenderer.isShowLookView
                    && window.canvasRenderer.isShowLookView());
                const effCid = _isShowView
                    ? (draggedLayer.show_canvas_id || draggedLayer.canvas_id)
                    : draggedLayer.canvas_id;
                if (effCid !== canvas.id) {
                    e.preventDefault();
                    if (_isShowView) {
                        if (typeof this.moveLayerShowCanvas === 'function') {
                            this.moveLayerShowCanvas(draggedLayer.id, canvas.id);
                        }
                    } else {
                        const mode = (e.metaKey || e.altKey) ? 'duplicate' : 'move';
                        this.moveLayerToCanvas(draggedLayer.id, canvas.id, mode);
                    }
                }
            }
        });
    }

    // -------------------------------------------------------------------
    // Canvas API helpers (Slice 2). All call backend endpoints introduced
    // in /api/canvas* and update this.project from the response.
    // -------------------------------------------------------------------

    _applyProjectUpdate(data) {
        if (!data) return;
        // Preserve client-side properties that may be on existing layers
        // before we overwrite the project reference.
        const savedClientProps = {};
        if (this.project && this.project.layers) {
            this.project.layers.forEach(l => {
                savedClientProps[l.id] = this.extractClientSideProps
                    ? this.extractClientSideProps(l) : null;
            });
        }
        this.project = data;
        // v0.8.7.2.1: actually re-apply the in-memory client-side props
        // collected above. The previous code referenced a non-existent
        // `applyClientSideProperties` method, so the if-branch was always
        // false and client-side fields (screen-name offsets, label sizes,
        // power voltage, custom port paths, etc.) silently reverted to
        // whatever the server response carried. Repro: drag a screen-name
        // label, toggle Front<->Back perspective, label snaps back to its
        // pre-drag position because the perspective PUT response wipes the
        // layer object and nothing restores the just-dragged offset.
        if (data.layers && Object.keys(savedClientProps).length > 0) {
            data.layers.forEach(layer => {
                const props = savedClientProps[layer.id];
                if (!props) return;
                Object.keys(props).forEach(key => {
                    if (props[key] !== undefined) layer[key] = props[key];
                });
            });
        }
        // Also re-run the localStorage restore for the "Untitled Project"
        // boot path (shouldUseSavedClientProps gate handles the rest).
        try { this.loadClientSideProperties && this.loadClientSideProperties({ skipPreferences: true }); } catch (_) {}
        // If the active canvas's properties changed, sync raster size for
        // the workspace toolbar (Slice 4 will deepen this, Slice 2 just
        // keeps the sidebar consistent).
        if (data.raster_width && data.raster_height && this.syncRasterFromProject) {
            try { this.syncRasterFromProject(); } catch (_) {}
        }
        this.renderLayers();
        // Rebind currentLayer to the fresh object in the new project payload
        // (same id, new reference) and refresh the settings panel inputs so
        // post-mutation values (offset_x snapped to 0,0 after a cross-canvas
        // move, raster size after a resize, etc.) propagate without forcing
        // the user to deselect+reselect to see the change.
        if (this.currentLayer && data.layers) {
            const refreshed = data.layers.find(l => l.id === this.currentLayer.id);
            if (refreshed) {
                this.currentLayer = refreshed;
                if (typeof this.loadLayerToInputs === 'function') {
                    try { this.loadLayerToInputs(); } catch (_) {}
                }
            }
        }
        // Slice 8: re-sync perspective toggles after any canvas mutation
        // (perspective edited on a sibling canvas, active canvas swapped on
        // server, etc.).
        if (typeof this.refreshPerspectiveButtons === 'function') {
            try { this.refreshPerspectiveButtons(); } catch (_) {}
        }
        // Re-render the workspace canvas. The previous `if (this.render)`
        // check was always false (app has no .render method), so the
        // workspace pixels never refreshed after a canvas CRUD response,
        // most visibly: toggling a canvas's visibility updated state but
        // never repainted the workspace, so the canvas appeared not to hide.
        if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
            try { window.canvasRenderer.render(); } catch (_) {}
        }
    }

    addCanvas() {
        // Seed new canvases from the user's preferred default canvas size so
        // every "+ Add Canvas" click matches the same baseline as a brand-new
        // project, not whatever the currently active canvas happens to be.
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : null;
        const body = {};
        if (prefs && Number.isFinite(prefs.rasterWidth) && prefs.rasterWidth > 0) {
            body.raster_width = prefs.rasterWidth;
            body.show_raster_width = prefs.rasterWidth;
        }
        if (prefs && Number.isFinite(prefs.rasterHeight) && prefs.rasterHeight > 0) {
            body.raster_height = prefs.rasterHeight;
            body.show_raster_height = prefs.rasterHeight;
        }
        return fetch('/api/canvas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            // saveState AFTER mutation so the snapshot captures the new canvas.
            // One Cmd+Z then reverts exactly this Add.
            if (typeof this.saveState === 'function') this.saveState('Add Canvas');
        });
    }

    // Canvas mutation routed through one helper so every mutating call
    // gets one (and only one) post-mutation undo entry.
    updateCanvas(canvasId, patch, { skipHistory = false } = {}) {
        // Pick the most informative undo label from the patch keys.
        const keys = patch ? Object.keys(patch) : [];
        let label = 'Update Canvas';
        if (keys.includes('name')) label = 'Rename Canvas';
        else if (keys.includes('color')) label = 'Change Canvas Color';
        else if (keys.includes('visible')) label = 'Toggle Canvas Visibility';
        else if (keys.includes('workspace_x') || keys.includes('workspace_y')) label = 'Move Canvas';
        else if (keys.includes('raster_width') || keys.includes('raster_height')
            || keys.includes('show_raster_width') || keys.includes('show_raster_height')) label = 'Resize Canvas';
        else if (keys.includes('data_flow_perspective') || keys.includes('power_perspective')) label = 'Change Perspective';
        return fetch(`/api/canvas/${canvasId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch || {})
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            // skipHistory lets a continuous edit (e.g. dragging the native
            // canvas color picker) persist every frame while a single coalesced
            // snapshot is recorded by the caller once the drag settles.
            if (!skipHistory && typeof this.saveState === 'function') this.saveState(label);
        });
    }

    /**
     * Slice 7: reassign a layer to a different canvas via the existing
     * Slice-2 endpoint. ``mode`` is "move" or "duplicate".
     * - "move": same layer id, offsets reset to 0,0; selection follows.
     * - "duplicate": new layer id appended in target canvas; original
     *   stays put and remains selected.
     */
    /**
     * v0.8.5: Reassign a layer's Show Look canvas membership. Used by
     * cross-canvas drops on the Show Look / Data / Power tabs. Does not
     * touch canvas_id, offset_x/y, or panel geometry, so the layer's
     * Pixel Map / Cabinet ID position and processor membership stay
     * exactly where they were. Pass null to clear the override and let
     * Show Look fall back to mirroring canvas_id.
     */
    moveLayerShowCanvas(layerId, targetCanvasId) {
        return fetch(`/api/layer/${layerId}/show_canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show_canvas_id: targetCanvasId })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.renderLayers === 'function') this.renderLayers();
            if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                window.canvasRenderer.render();
            }
            if (typeof this.saveState === 'function') {
                this.saveState('Move Layer (Show Look) to Canvas');
            }
            return data;
        });
    }

    /**
     * v0.8.5: Multi-layer Show Look canvas reassign (mirrors moveLayersCrossCanvas).
     */
    async moveLayersShowCanvas(layerIds, targetCanvasId) {
        if (!Array.isArray(layerIds) || layerIds.length === 0) return;
        let lastData = null;
        for (const id of layerIds) {
            const r = await fetch(`/api/layer/${id}/show_canvas`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ show_canvas_id: targetCanvasId })
            });
            lastData = await r.json();
        }
        if (lastData) {
            this._applyProjectUpdate(lastData);
            if (typeof this.renderLayers === 'function') this.renderLayers();
            if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                window.canvasRenderer.render();
            }
            if (typeof this.saveState === 'function') {
                this.saveState(`Move ${layerIds.length} Layers (Show Look) to Canvas`);
            }
        }
        return lastData;
    }

    moveLayerCrossCanvas(layerId, targetCanvasId, mode) {
        const wantMove = (mode !== 'duplicate');
        return fetch(`/api/layer/${layerId}/canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_id: targetCanvasId, mode: wantMove ? 'move' : 'duplicate' })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            // After move: the same layer id now lives in the target canvas;
            // make sure it stays the current layer so the sidebar follows.
            if (wantMove && this.project && Array.isArray(this.project.layers)) {
                const moved = this.project.layers.find(l => l.id === layerId);
                if (moved) {
                    this.currentLayer = moved;
                    if (this.project) this.project.active_canvas_id = targetCanvasId;
                    if (typeof this.renderLayers === 'function') this.renderLayers();
                    if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                        window.canvasRenderer.render();
                    }
                }
            }
            // saveState AFTER server applies the cross-canvas move so the
            // snapshot includes the canvas_id swap + the snap-to-(0,0) offset
            // reset. Single Cmd+Z reverts the whole operation.
            if (typeof this.saveState === 'function') {
                this.saveState(wantMove ? 'Move Layer to Canvas' : 'Duplicate Layer to Canvas');
            }
            // For duplicate: leave selection on the original (default behavior).
            return data;
        });
    }

    /**
     * Multi-select cross-canvas drag: PUT each selected layer's canvas
     * sequentially (avoids server race), then sync state so all moved
     * layers stay selected and the active canvas follows. Mode applies
     * to ALL layers in the batch (move OR duplicate, not mixed).
     */
    async moveLayersCrossCanvas(layerIds, targetCanvasId, mode) {
        const wantMove = (mode !== 'duplicate');
        if (!Array.isArray(layerIds) || layerIds.length === 0) return;
        let lastData = null;
        for (const id of layerIds) {
            const r = await fetch(`/api/layer/${id}/canvas`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ canvas_id: targetCanvasId, mode: wantMove ? 'move' : 'duplicate' })
            });
            lastData = await r.json();
        }
        if (lastData) {
            this._applyProjectUpdate(lastData);
            if (wantMove && this.project && Array.isArray(this.project.layers)) {
                // Re-select all moved layers (same ids); set active canvas
                // to target so the sidebar reflects the destination.
                this.project.active_canvas_id = targetCanvasId;
                this.selectedLayerIds = new Set(layerIds);
                const primary = this.project.layers.find(l => l.id === layerIds[0]);
                if (primary) this.currentLayer = primary;
                if (typeof this.renderLayers === 'function') this.renderLayers();
                if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                    window.canvasRenderer.render();
                }
            }
            // saveState AFTER all PUTs settle so one Cmd+Z reverts the whole
            // multi-layer cross-canvas move/duplicate.
            if (typeof this.saveState === 'function') {
                this.saveState(wantMove
                    ? `Move ${layerIds.length} Layers to Canvas`
                    : `Duplicate ${layerIds.length} Layers to Canvas`);
            }
        }
        return lastData;
    }

    /**
     * Slice 5: after a canvas-drag drop, warn (non-blocking) if the
     * dragged canvas's workspace bounds intersect any other visible
     * canvas's bounds. Does NOT auto-snap or reject, just toasts.
     * Bounds use the active view's raster (pixel-map vs show-look),
     * matching what the user sees in `_drawCanvasOutline`.
     */
    _checkCanvasOverlapAndToast(canvasId) {
        if (!this.project || !Array.isArray(this.project.canvases)) return;
        const useShow = !!(window.canvasRenderer && typeof window.canvasRenderer.isShowLookView === 'function'
            && window.canvasRenderer.isShowLookView());
        const bounds = (c) => {
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            const h = (useShow && c.show_raster_height) || c.raster_height || 0;
            // v0.8.5.3: in Show Look use the canvas's show workspace
            // position (falls back to workspace_x/y when null). The check
            // was reading workspace_x/y in both views, which gave false
            // overlap toasts when only the show position had moved.
            let x, y;
            if (useShow) {
                x = (c.show_workspace_x == null ? (c.workspace_x || 0) : (c.show_workspace_x || 0));
                y = (c.show_workspace_y == null ? (c.workspace_y || 0) : (c.show_workspace_y || 0));
            } else {
                x = c.workspace_x || 0;
                y = c.workspace_y || 0;
            }
            return { x, y, w, h };
        };
        const dragged = this.project.canvases.find(c => c && c.id === canvasId);
        if (!dragged || dragged.visible === false) return;
        const a = bounds(dragged);
        if (a.w <= 0 || a.h <= 0) return;
        const intersects = (a, b) =>
            a.x < b.x + b.w && a.x + a.w > b.x &&
            a.y < b.y + b.h && a.y + a.h > b.y;
        for (const other of this.project.canvases) {
            if (!other || other.id === canvasId || other.visible === false) continue;
            const b = bounds(other);
            if (b.w <= 0 || b.h <= 0) continue;
            if (intersects(a, b)) {
                this._toast('Canvases overlapping, visual rendering may be confusing.', true);
                return;
            }
        }
    }

    deleteCanvas(canvasId) {
        return fetch(`/api/canvas/${canvasId}`, { method: 'DELETE' })
            .then(r => r.json().then(body => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (!ok) {
                    this._toast(body && body.error ? body.error : 'Cannot delete canvas', true);
                    return;
                }
                this._applyProjectUpdate(body);
                if (typeof this.saveState === 'function') this.saveState('Delete Canvas');
            });
    }

    duplicateCanvas(canvasId) {
        return fetch(`/api/canvas/${canvasId}/duplicate`, { method: 'POST' })
            .then(r => r.json()).then(data => {
                this._applyProjectUpdate(data);
                if (typeof this.saveState === 'function') this.saveState('Duplicate Canvas');
            });
    }

    setActiveCanvas(canvasId, opts = {}) {
        // Optimistic UI update so the highlight feels instant; backend
        // confirms.
        if (!this.project) return Promise.resolve();
        if (this.project.active_canvas_id === canvasId && !opts.force) {
            // No-op: already active. Skip the network round-trip and
            // re-render to avoid spamming PUTs from layer-selection paths.
            return Promise.resolve();
        }
        this.project.active_canvas_id = canvasId;
        // Slice 5: active canvas constrains selection. Drop any selected
        // layer ids that don't belong to the new active canvas, and clear
        // currentLayer if it's now in a different canvas. Layers without a
        // canvas_id (legacy / orphan) are kept on the safe side. This keeps
        // the user's mental model consistent ("the active canvas is what
        // I'm working in") and prevents stale highlights on the inactive
        // canvas after a click.
        // Slice 13 escape hatch: callers performing an explicit cross-canvas
        // multi-select (shift-click toggle / shift-click range) pass
        // preserveSelection:true to keep their full selection alive, so the
        // user can bulk-edit screens across canvases at once.
        // v0.8.6.3: in show views, prune by show_canvas_id || canvas_id so
        // a layer reassigned to a different Show Look canvas is kept when
        // its Show Look home becomes active (and dropped when something
        // else does), matching what's drawn and grouped in the sidebar.
        const _isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const _effCid = (l) => (_isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        if (!opts.preserveSelection
                && Array.isArray(this.project.layers)
                && this.selectedLayerIds && this.selectedLayerIds.size > 0) {
            const layerById = {};
            for (const l of this.project.layers) layerById[l.id] = l;
            const filtered = new Set();
            for (const id of this.selectedLayerIds) {
                const l = layerById[id];
                if (!l) continue;
                const cid = _effCid(l);
                if (!cid || cid === canvasId) filtered.add(id);
            }
            this.selectedLayerIds = filtered;
        }
        if (!opts.preserveSelection
                && this.currentLayer && _effCid(this.currentLayer)
                && _effCid(this.currentLayer) !== canvasId) {
            // Promote the most-recently-selected layer in the new active
            // canvas (if any) to currentLayer, otherwise null.
            let next = null;
            if (this.selectedLayerIds && this.selectedLayerIds.size > 0
                && Array.isArray(this.project.layers)) {
                const lastId = this.lastSelectedLayerId;
                if (lastId && this.selectedLayerIds.has(lastId)) {
                    next = this.project.layers.find(l => l.id === lastId) || null;
                }
                if (!next) {
                    const firstId = this.selectedLayerIds.values().next().value;
                    next = this.project.layers.find(l => l.id === firstId) || null;
                }
            }
            this.currentLayer = next;
            if (!next) this.lastSelectedLayerId = null;
        }
        // Slice 6: toolbar raster reflects the active canvas's raster.
        // syncRasterFromProject reads straight from the active canvas now,
        // so no project-root mirror needed.
        try { this.syncRasterFromProject(); } catch (_) {}
        // Slice 8: per-canvas perspective, sync the Front/Back toggle state
        // when the active canvas changes so the sidebar reflects the canvas
        // the user is now editing.
        if (typeof this.refreshPerspectiveButtons === 'function') {
            try { this.refreshPerspectiveButtons(); } catch (_) {}
        }
        if (!opts.silent) {
            this.renderLayers();
            if (window.canvasRenderer) window.canvasRenderer.render();
        }
        return fetch(`/api/canvas/${canvasId}/active`, { method: 'PUT' })
            .then(r => r.json()).then(data => {
                // v0.8.7: previously did `this.project = data` here, which
                // wiped client-side-only properties (screenNameOffsetX/Y
                // per view, etc.) every time the user activated a different
                // canvas, visible as the screen-name label snapping back
                // to its previous spot the moment you clicked away after
                // dragging it. The PUT only changes active_canvas_id; just
                // sync that one field instead of clobbering the whole
                // project. _applyProjectUpdate-style merges aren't needed
                // because we already optimistically updated this.project
                // before the fetch.
                if (data && data.active_canvas_id) {
                    this.project.active_canvas_id = data.active_canvas_id;
                }
            });
    }

    /**
     * Slice 6: deprecated, kept as a no-op so any lingering callers don't
     * crash during the deprecation window. The renderer reads straight from
     * the active canvas via accessors now, so there is no project-root copy
     * to keep in sync.
     */
    _syncRootRasterFromActiveCanvas() {
        // intentionally empty, see syncRasterFromProject().
    }

    /**
     * Slice 4: when a layer becomes the user-selected layer, also activate
     * its canvas (if different). Idempotent, setActiveCanvas short-circuits
     * when already active, so we won't spam PUTs from re-selecting the same
     * layer or selecting siblings inside the already-active canvas.
     */
    _activateCanvasForLayer(layer, opts) {
        if (!layer) return;
        if (!this.project) return;
        // v0.8.6.3: in show views, activate the layer's Show Look canvas
        // (show_canvas_id || canvas_id) so clicking a Show-Look-reassigned
        // layer activates the canvas it actually lives in on screen.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const targetCid = (isShowView && layer.show_canvas_id)
            ? layer.show_canvas_id
            : layer.canvas_id;
        if (!targetCid) return;
        if (targetCid === this.project.active_canvas_id) return;
        this.setActiveCanvas(targetCid, opts);
    }

    reorderCanvasBeforeTarget(draggedId, targetId) {
        if (!this.project || !this.project.canvases) return;
        const ids = this.project.canvases.map(c => c.id);
        const from = ids.indexOf(draggedId);
        const to = ids.indexOf(targetId);
        if (from < 0 || to < 0 || from === to) return;
        ids.splice(from, 1);
        ids.splice(ids.indexOf(targetId), 0, draggedId);
        return fetch('/api/canvas/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_ids: ids })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.saveState === 'function') this.saveState('Reorder Canvases');
        });
    }

    moveLayerToCanvas(layerId, canvasId, mode = 'move') {
        return fetch(`/api/layer/${layerId}/canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_id: canvasId, mode })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.saveState === 'function') {
                this.saveState(mode === 'duplicate' ? 'Duplicate Layer to Canvas' : 'Move Layer to Canvas');
            }
        });
    }

    // v0.8 Slice 2.5: per-canvas "+ Add" chooser (Screen / Image / Text).
    // Routes to the existing add flows after activating the target canvas
    // so the new layer always lands in the canvas whose "+ Add" was clicked
    // (mirrors the Slice 2 add-screen pattern, server uses active_canvas_id
    // when assigning new layers).
    openCanvasAddMenu(canvas, anchor) {
        document.querySelectorAll('.canvas-add-popup, .canvas-menu-popup, .canvas-color-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup canvas-add-popup';
        menu.innerHTML = `
            <button data-action="screen">Screen…</button>
            <button data-action="image">Image / Logo…</button>
            <button data-action="text">Text</button>
        `;
        document.body.appendChild(menu);
        const r = anchor.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = `${r.bottom + 4}px`;
        menu.style.left = `${Math.max(8, r.left)}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const act = btn.dataset.action;
                close();
                this._handleCanvasAddAction(canvas, act);
            });
        });
    }

    _handleCanvasAddAction(canvas, action) {
        // Activate the target canvas so the existing add flows (which look
        // at active_canvas_id server-side) place the layer correctly.
        const after = () => {
            if (action === 'screen') {
                this.openPresetPicker();
            } else if (action === 'image') {
                this.imageFileAction = 'add';
                const input = document.getElementById('add-image-input');
                if (input) input.click();
            } else if (action === 'text') {
                this.addTextLayer();
            }
        };
        Promise.resolve(this.setActiveCanvas(canvas.id, { silent: true })).then(after);
    }

    openCanvasMenu(canvas, anchor) {
        // Close any pre-existing menu.
        document.querySelectorAll('.canvas-menu-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup';
        menu.innerHTML = `
            <button data-action="rename">Rename</button>
            <button data-action="duplicate">Duplicate</button>
            <button data-action="color">Change Color…</button>
            <button data-action="delete" class="danger">Delete</button>
        `;
        document.body.appendChild(menu);
        const r = anchor.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = `${r.bottom + 4}px`;
        menu.style.left = `${Math.max(8, r.right - 160)}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        // Defer to avoid catching the click that opened us.
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const act = btn.dataset.action;
                close();
                this._handleCanvasMenuAction(canvas, act);
            });
        });
    }

    _handleCanvasMenuAction(canvas, action) {
        if (action === 'rename') {
            const input = document.querySelector(`.canvas-group[data-canvas-id="${canvas.id}"] .canvas-name-input`);
            if (input) {
                input.readOnly = false;
                input.focus();
                input.select();
            }
        } else if (action === 'duplicate') {
            this.duplicateCanvas(canvas.id);
        } else if (action === 'color') {
            this.openCanvasColorPicker(canvas);
        } else if (action === 'delete') {
            const layerCount = (this.project.layers || []).filter(l => l.canvas_id === canvas.id).length;
            const msg = layerCount > 0
                ? `Delete canvas '${canvas.name}' and its ${layerCount} layer${layerCount === 1 ? '' : 's'}? This cannot be undone.`
                : `Delete canvas '${canvas.name}'?`;
            if (window.confirm(msg)) this.deleteCanvas(canvas.id);
        }
    }

    openCanvasColorPicker(canvas) {
        // Clean up any stray popup from the previous implementation.
        document.querySelectorAll('.canvas-color-popup').forEach(el => el.remove());

        // Hidden color input the picker commits to; its change updates the canvas.
        let proxy = document.getElementById('canvas-color-proxy');
        if (!proxy) {
            proxy = document.createElement('input');
            proxy.type = 'color';
            proxy.id = 'canvas-color-proxy';
            proxy.style.cssText = 'position:fixed;width:1px;height:1px;opacity:0;border:0;padding:0;z-index:12000;';
            document.body.appendChild(proxy);
        }
        // Anchor it near the canvas's menu button so the native picker pops up there.
        const anchor = document.querySelector(`.canvas-group[data-canvas-id="${canvas.id}"] .canvas-menu-btn`);
        if (anchor) {
            const r = anchor.getBoundingClientRect();
            proxy.style.left = `${Math.round(r.left)}px`;
            proxy.style.top = `${Math.round(r.bottom)}px`;
        }
        proxy.value = canvas.color || '#4A90E2';
        // Split preview from commit like every other color control: dragging
        // the picker only repaints locally, and the single server PUT + undo
        // step happens once on change. Bound to both events it used to fire a
        // full PUT + saveState per drag frame — dozens of history entries for
        // one color pick.
        proxy.oninput = (e) => {
            canvas.color = (e.target.value || '').toLowerCase();
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        proxy.onchange = (e) => {
            // Native <input type=color> fires 'change' continuously while the
            // macOS system picker is dragged. Persist each frame WITHOUT its own
            // undo entry, then coalesce a single snapshot once the drag settles.
            this.updateCanvas(canvas.id, { color: (e.target.value || '').toLowerCase() }, { skipHistory: true })
                .then(() => this.debouncedSaveState('Change Canvas Color', 400, 'canvas-color'));
        };

        // Same rule as every other color control: custom wheel on PC, native OS
        // picker on macOS. Either way it opens directly on "Change Color".
        const useCustom = window.LRDColorPicker && window.LRDColorPicker.isEnabled();
        if (useCustom && window.LRDColorWindow && typeof window.LRDColorWindow.open === 'function') {
            window.LRDColorWindow.open(proxy, proxy.value);
        } else {
            proxy.click(); // native OS color picker (macOS wheel)
        }
    }

    updateLayerOrderControls() {
        // v0.8 Slice 2.5: per-layer ▲▼ arrows. Disable the up arrow on the
        // top-most layer of each canvas group, the down arrow on the
        // bottom-most. Display order in the sidebar is reverse of the layer
        // array (newest on top), so within a canvas the FIRST displayed
        // layer is the LAST one in the array, the up arrow on that one is
        // disabled, etc.
        if (!this.project || !this.project.canvases) return;
        // v0.8.6.3: group by view-effective canvas (show_canvas_id ||
        // canvas_id in show views) so the ▲▼ arrow enable/disable matches
        // the sidebar group the layer is currently shown in.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const effCid = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        // Group layer ids by canvas, in display order (reverse-array).
        const reversed = [...(this.project.layers || [])].reverse();
        const byCanvas = new Map();
        reversed.forEach(l => {
            const cid = effCid(l);
            if (!byCanvas.has(cid)) byCanvas.set(cid, []);
            byCanvas.get(cid).push(l.id);
        });
        document.querySelectorAll('#layers-list .layer-item').forEach(el => {
            const lid = parseInt(el.dataset.layerId, 10);
            const layer = (this.project.layers || []).find(l => l.id === lid);
            if (!layer) return;
            const ids = byCanvas.get(effCid(layer)) || [];
            const idx = ids.indexOf(lid);
            const up = el.querySelector('.layer-move-up');
            const down = el.querySelector('.layer-move-down');
            if (up) up.disabled = idx <= 0;
            if (down) down.disabled = idx < 0 || idx >= ids.length - 1;
        });
    }

    moveLayerById(layerId, delta) {
        // Kept for backward compatibility (keyboard shortcuts may call this).
        // Delegates to within-canvas reorder so cross-canvas hops never
        // happen via arrow-key reorder either.
        this.moveLayerWithinCanvas(layerId, delta);
    }

    // v0.8 Slice 2.5: reorder a layer up/down by one slot, but only within
    // its own canvas group. Display order is reverse of array order, so
    // delta=-1 (visual up) corresponds to a HIGHER array index swap.
    moveLayerWithinCanvas(layerId, delta) {
        if (!this.project || !this.project.layers) return;
        const layer = this.project.layers.find(l => l.id === layerId);
        if (!layer) return;
        // v0.8.6.3: route through view-effective canvas so reorder
        // operates on the same group the sidebar shows in show views.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const effCid = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        const ownCid = effCid(layer);
        // Build the within-canvas display-order id list.
        const reversed = [...this.project.layers].reverse();
        const sameCanvasIds = reversed.filter(l => effCid(l) === ownCid).map(l => l.id);
        const localIdx = sameCanvasIds.indexOf(layerId);
        const nextLocal = localIdx + delta;
        if (localIdx < 0 || nextLocal < 0 || nextLocal >= sameCanvasIds.length) return;
        const swapWithId = sameCanvasIds[nextLocal];
        // Build the full display-order id list and swap just those two.
        const displayIds = reversed.map(l => l.id);
        const a = displayIds.indexOf(layerId);
        const b = displayIds.indexOf(swapWithId);
        if (a < 0 || b < 0) return;
        [displayIds[a], displayIds[b]] = [displayIds[b], displayIds[a]];
        this.applyDisplayOrder(displayIds, 'Reorder Layers');
    }

    reorderLayersByDrag(draggedId, targetId, insertAfter = false) {
        const displayIds = [...document.querySelectorAll('#layers-list .layer-item')].map(el => parseInt(el.dataset.layerId, 10));
        const from = displayIds.indexOf(draggedId);
        const to = displayIds.indexOf(targetId);
        if (from < 0 || to < 0) return;
        const [moved] = displayIds.splice(from, 1);
        let insertIndex = to;
        if (insertAfter && to >= 0) {
            insertIndex = to + 1;
        }
        if (from < to && insertAfter) {
            insertIndex -= 1;
        }
        displayIds.splice(insertIndex, 0, moved);
        this.applyDisplayOrder(displayIds, 'Reorder Layers');
    }

    applyDisplayOrder(displayIds, historyAction) {
        if (!this.project || !this.project.layers) return;
        const layerMap = new Map(this.project.layers.map(l => [l.id, l]));
        const newDisplay = displayIds.map(id => layerMap.get(id)).filter(Boolean);
        const newOrder = [...newDisplay].reverse();
        sendClientLog('reorder_layers', {
            action: historyAction,
            newOrder: newOrder.map(l => ({ id: l.id, name: l.name }))
        });
        // v0.10.5: snapshot AFTER the reorder. Taken before, the entry held
        // the pre-reorder order, so Undo-then-Redo silently lost the reorder
        // (same bug class as the v0.10.0 "Add Layer" fix).
        this.project.layers = newOrder;
        this.saveState(historyAction);
        this.updateUI();
        this.saveProject();
    }
    
    /**
     * Slice 6: write a toolbar Raster: W x H change to the active canvas via
     * PUT /api/canvas/<id>. Source-of-truth lives on the canvas object, no
     * project-root mirror. `axis` is 'width' or 'height'; `value` is the new
     * dimension; `isShow` selects show_raster_* vs raster_*.
     *
     * v0.8.5.2 made the two rasters fully independent, so a Pixel Map edit
     * never touched Show Look. That left a screen sized before Show Look was
     * ever opened stuck at the old raster: set 4K, change to 8K, switch to
     * Show Look, still 4K, with no hint why.
     *
     * v0.10.5.1 restores the v0.7.6.1 link using the same rule the per-layer
     * show offsets already use: Show Look FOLLOWS Pixel Map while the two
     * still match, and stops the moment the user sets a different Show Look
     * raster. Independence is preserved once it actually means something;
     * until then the two track. The link is one-way, editing the Show Look
     * raster never rewrites the Pixel Map raster.
     */
    _writeToolbarRasterToActiveCanvas(axis, value, isShow) {
        if (!this.project || !Array.isArray(this.project.canvases)) return;
        const canvasId = this.project.active_canvas_id;
        const c = this.project.canvases.find(x => x.id === canvasId);
        if (!c) return;
        const patch = {};
        if (isShow) {
            if (axis === 'width')  patch.show_raster_width  = value;
            if (axis === 'height') patch.show_raster_height = value;
        } else {
            const key = axis === 'width' ? 'raster_width' : 'raster_height';
            const showKey = axis === 'width' ? 'show_raster_width' : 'show_raster_height';
            const pixelBefore = Number(c[key]) || 0;
            const showBefore = Number(c[showKey]) || 0;
            // Linked while equal, or while Show Look has no size of its own yet.
            const linked = showBefore === 0 || showBefore === pixelBefore;
            patch[key] = value;
            if (linked) patch[showKey] = value;
        }
        // Optimistic local update so the renderer (which reads from the
        // canvas object via getters) repaints immediately, before the PUT
        // round-trip. The server response will overwrite this with the
        // canonical state.
        Object.assign(c, patch);
        this.saveRasterSize();
        if (typeof sendClientLog === 'function') {
            sendClientLog('raster_change', {
                axis, value, isShow,
                view: window.canvasRenderer && window.canvasRenderer.viewMode,
                canvas_id: canvasId,
            });
        }
        if (typeof this.updateCanvas === 'function') {
            this.updateCanvas(canvasId, patch);
        }
    }

    saveProject() {
        fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.project)
        })
        .then(() => {
            document.getElementById('status-message').textContent = 'Project saved';
            setTimeout(() => {
                document.getElementById('status-message').textContent = 'Ready';
            }, 2000);
        });
    }
    
    async saveProjectToFile() {
        // Ensure raster size in project reflects current toolbar/canvas values
        if (window.canvasRenderer && this.project) {
            this.project.raster_width = window.canvasRenderer.rasterWidth;
            this.project.raster_height = window.canvasRenderer.rasterHeight;
        }
        sendClientLog('save_project_file_capabilities', {
            hasSaveFilePicker: this.supportsFilePickerAPIs()
        });
        if (!this.supportsFilePickerAPIs() && !this._warnedNoFilePicker) {
            this._warnedNoFilePicker = true;
            sendClientLog('save_picker_apis_unavailable_warning', {});
        }
        // Pass a lazy blob factory so JSON.stringify (slow on large multi-canvas
        // projects, ~1MB) runs AFTER showSaveFilePicker resolves. This keeps
        // Chrome's user-activation token fresh for createWritable; otherwise
        // Chrome rejects the write with NotAllowedError and leaves a 0-byte file.
        const project = this.project;
        await this.saveBlobWithPicker(
            () => {
                const projectData = JSON.stringify(project, null, 2);
                return new Blob([projectData], { type: 'application/json' });
            },
            `${this.project.name}.json`,
            'application/json'
        );

        this.addToRecentFiles(this.project);
        document.getElementById('status-message').textContent = 'Project saved to file';
        setTimeout(() => {
            document.getElementById('status-message').textContent = 'Ready';
        }, 2000);
    }
    
    loadProjectFromFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.style.display = 'none';
        document.body.appendChild(input);
        sendClientLog('open_file_dialog_requested');
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const projectData = JSON.parse(event.target.result);
                        sendClientLog('load_project_file_start', { name: projectData.name || 'Unnamed', layers: projectData.layers ? projectData.layers.length : 0 });
                        // Clean-slate reset so stale sidebar values can't leak into new project
                        this.resetApplicationState();
                        this.project = projectData;
                        if (this.project.layers) {
                            this.project.layers.forEach(layer => {
                                this.applyMissingLayerDefaults(layer);
                                this.normalizeLoadedPowerFlowPattern(layer);
                            });
                        }
                        // v0.10.9: fix up Armor layers that carry a Max Capacity
                        // flag they were never actually drawn with. Runs before
                        // the PUT so the server (and the first undo snapshot)
                        // get the corrected mode.
                        this.normalizeArmorPortMapping(this.project);

                        // v0.8.7.2.1: ONLY trust root-level raster fields for
                        // legacy (pre-v0.8, no canvases array) files. Multi-
                        // canvas files keep the source-of-truth on each canvas
                        // object, and writing the root value into
                        // canvasRenderer.rasterWidth would clobber the active
                        // canvas's per-canvas raster (the setter routes to
                        // either raster_width or show_raster_width depending
                        // on the current tab). Bug repro: the file's root
                        // raster_width was a mirror of the active canvas's
                        // *show* raster (because the user last saved on Show
                        // Look), so opening the file overwrote the active
                        // canvas's pixel-map raster with its show raster
                        // value. syncRasterFromProject below reads from each
                        // canvas directly so multi-canvas projects are
                        // unaffected by skipping this block.
                        const _hasCanvases = Array.isArray(projectData.canvases)
                            && projectData.canvases.length > 0;
                        if (!_hasCanvases && projectData.raster_width && projectData.raster_height) {
                            window.canvasRenderer.rasterWidth = projectData.raster_width;
                            window.canvasRenderer.rasterHeight = projectData.raster_height;
                            document.getElementById('toolbar-raster-width').value = projectData.raster_width;
                            document.getElementById('toolbar-raster-height').value = projectData.raster_height;
                            this.saveRasterSize();
                        }

                        // Show locally right away (even if server sync fails)
                        this.updateUI();
                        if (this.project.layers && this.project.layers.length > 0) {
                            this.selectLayer(this.project.layers[0]);
                        }
                        this.saveClientSideProperties();
                        window.canvasRenderer.fitToView();

                        fetch('/api/project', {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.project)
                        })
                            .then(res => res.json())
                            .then(data => {
                                if (!data || !Array.isArray(data.layers)) {
                                    throw new Error('Invalid project data returned from server');
                                }
                                this.project = data;
                                this.dedupeProjectLayers('load_project_file');
                                if (this.project.layers) {
                                    this.project.layers.forEach(layer => {
                                        this.applyMissingLayerDefaults(layer);
                                        this.normalizeLoadedPowerFlowPattern(layer);
                                    });
                                }
                                // v0.10.9: no-op when the pre-PUT pass already
                                // fixed them; kept so the object that feeds
                                // resetHistory() below is always normalized.
                                this.normalizeArmorPortMapping(this.project);
                                // Sync the canvas's pixel/show raster backing fields from the
                                // loaded project so Show Look picks up the file's values
                                // (and falls back to the pixel raster when show wasn't saved).
                                this.syncRasterFromProject();
                                this.updateUI();
                                if (this.project.layers && this.project.layers.length > 0) {
                                    this.selectLayer(this.project.layers[0]);
                                }
                                this.saveClientSideProperties();
                                window.canvasRenderer.fitToView();
                                // Push all layers to server so client-side properties
                                // (showDataFlowPortInfo, showPowerCircuitInfo, computed power/capacity)
                                // are synced for every layer, not just the selected one.
                                this.updateLayers(this.project.layers, false, 'File Load Sync');
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                                this.addToRecentFiles(this.project);
                                sendClientLog('load_project_file_success', { name: this.project.name, layers: this.project.layers ? this.project.layers.length : 0 });
                                // Slice 12: server flagged this file as
                                // freshly migrated from v0.7. Show a one-time
                                // toast and strip the transient flag so it
                                // never ends up in the saved JSON. The toast
                                // is suppressed automatically on subsequent
                                // loads because the saved file now carries
                                // format_version: "0.8".
                                if (data && data._migration_notice) {
                                    delete this.project._migration_notice;
                                    sendClientLog('migration_notice_shown', {
                                        name: this.project.name,
                                        layers: this.project.layers ? this.project.layers.length : 0
                                    });
                                    if (typeof this._toast === 'function') {
                                        this._toast(
                                            'Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file.',
                                            false,
                                            10000
                                        );
                                    }
                                }
                            })
                            .catch((err) => {
                                sendClientLog('load_project_file_error', { message: err.message });
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded (server sync failed)';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                            });
                    } catch (error) {
                        sendClientLog('load_project_file_error', { message: error.message });
                        alert('Error loading project file: ' + error.message);
                    }
                };
                reader.readAsText(file);
            } else {
                sendClientLog('open_file_dialog_cancelled');
            }
            if (input.parentNode) input.parentNode.removeChild(input);
        };
        input.click();
    }

    resetApplicationState() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        localStorage.removeItem('ledRasterClientProps');
        this.resetHistory('Initial State');
    }

    applyMissingLayerDefaults(layer) {
        if (layer.locked === undefined) layer.locked = false;
        if (layer.powerVoltage === undefined) layer.powerVoltage = 110;
        if (layer.powerVoltageCustom === undefined) layer.powerVoltageCustom = layer.powerVoltage;
        if (layer.powerAmperage === undefined) layer.powerAmperage = 15;
        if (layer.powerAmperageCustom === undefined) layer.powerAmperageCustom = layer.powerAmperage;
        if (layer.panelWatts === undefined) layer.panelWatts = 200;
        if (layer.powerMaximize === undefined) layer.powerMaximize = false;
        if (layer.powerOrganized === undefined) layer.powerOrganized = true;
        if (layer.powerCustomPath === undefined) layer.powerCustomPath = false;
        if (!layer.powerFlowPattern) layer.powerFlowPattern = layer.flowPattern || 'tl-h';
        if (layer.powerLineWidth === undefined) layer.powerLineWidth = 8;
        if (!layer.powerLineColor) layer.powerLineColor = '#FF0000';
        if (!layer.powerArrowColor) layer.powerArrowColor = '#0042AA';
        if (layer.powerRandomColors === undefined) layer.powerRandomColors = false;
        if (layer.powerColorCodedView === undefined) layer.powerColorCodedView = false;
        layer.powerCircuitColors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
        if (layer.powerLabelSize === undefined) layer.powerLabelSize = 14;
        if (!layer.powerLabelBgColor) layer.powerLabelBgColor = '#D95000';
        if (!layer.powerLabelTextColor) layer.powerLabelTextColor = '#000000';
        if (!layer.powerLabelTemplate) layer.powerLabelTemplate = 'S1-#';
        if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
        if (!layer.primaryTextColor) layer.primaryTextColor = '#000000';
        if (!layer.backupTextColor) layer.backupTextColor = '#FFFFFF';
        if (!layer.border_color_pixel) layer.border_color_pixel = layer.border_color || '#ffffff';
        if (!layer.border_color_cabinet) layer.border_color_cabinet = layer.border_color || '#ffffff';
        if (!layer.border_color_data) layer.border_color_data = layer.border_color || '#ffffff';
        if (!layer.border_color_power) layer.border_color_power = layer.border_color || '#ffffff';
        // Computed/transient fields should never be trusted from file payload
        delete layer._powerError;
        delete layer._powerCircuits;
        delete layer._powerTotalAmps1;
        delete layer._powerTotalAmps3;
        delete layer._powerCircuitsRequired;
        delete layer._capacityError;
        delete layer._autoPortsRequired;
        delete layer._portsRequired;
    }

    normalizeLoadedPowerFlowPattern(layer) {
        if (!layer || !Array.isArray(layer.panels) || layer.panels.length === 0) return;
        if (!layer.flowPattern || !layer.powerFlowPattern) return;
        if (layer.powerFlowPattern === 'custom') return;
        if (layer.powerFlowPattern === layer.flowPattern) return;

        const originalPattern = layer.powerFlowPattern;
        const current = this.calculatePowerAssignments(layer);
        if (!current || !current.error) return;

        layer.powerFlowPattern = layer.flowPattern;
        const migrated = this.calculatePowerAssignments(layer);
        if (migrated && !migrated.error) {
            sendClientLog('loaded_power_pattern_migrated', {
                layerId: layer.id,
                from: originalPattern,
                to: layer.flowPattern
            });
            return;
        }

        layer.powerFlowPattern = originalPattern;
    }

    // v0.10.9: NovaStar Armor used to discard portMappingMode entirely -
    // calculatePortAssignments forced Organized on it no matter what the layer
    // said. Projects saved in that window can carry 'max-capacity' on an Armor
    // screen while having been drawn (and printed) as Organized the whole time.
    // Now that Armor honours both modes, opening such a file would silently
    // redraw an already-issued map, so pin those layers back to the mode they
    // really rendered with. LOAD PATHS ONLY: switching a layer to Armor by hand
    // is a deliberate choice, and undo/redo must never re-apply this.
    // Returns the number of layers changed.
    normalizeArmorPortMapping(project) {
        if (!project || !Array.isArray(project.layers)) return 0;
        let changed = 0;
        project.layers.forEach(layer => {
            if (!layer || (layer.type || 'screen') !== 'screen') return;
            // A missing processorType renders as Armor (calculatePortAssignments
            // defaults to it), so those layers were drawn Organized too and get
            // the same treatment.
            if ((layer.processorType || 'novastar-armor') !== 'novastar-armor') return;
            if (layer.portMappingMode !== 'max-capacity') return;
            layer.portMappingMode = 'organized';
            changed++;
        });
        if (changed > 0) {
            sendClientLog('armor_port_mapping_normalized', { layers: changed });
        }
        return changed;
    }

    renameLayer(layer, nameElement) {
        const currentName = layer.name;
        let renameFinished = false;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentName;
        input.className = 'layer-name-input';
        input.style.cssText = 'background: #1a1a1a; border: 1px solid #4A90E2; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; width: 100%;';
        
        nameElement.textContent = '';
        nameElement.appendChild(input);
        input.focus();
        input.select();
        
        const finishRename = () => {
            if (renameFinished) return;
            renameFinished = true;
            const newName = input.value.trim() || currentName;
            layer.name = newName;

            if (newName !== currentName) {
                this.saveState('Rename Layer');
                if (typeof sendClientLog === 'function') {
                    sendClientLog('rename_layer', { id: layer.id, from: currentName, to: newName });
                }
            }
            
            fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            })
            .then(() => {
                this.renderLayers();
            });
        };
        
        input.addEventListener('blur', finishRename);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                finishRename();
            } else if (e.key === 'Escape') {
                layer.name = currentName;
                this.renderLayers();
            }
        });
    }
    
}

for (const k of Object.getOwnPropertyNames(_CanvasUi.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CanvasUi.prototype, k));
    }
}
