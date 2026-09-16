// app-selection: the multi-select model for LEDRasterApp - which layers
// are selected (getSelectedLayers, setSelectedLayersByIds,
// toggleLayerSelection, selectLayerRange), applying an edit to all of
// them (applyToSelectedLayers), and the project-layer list hygiene the
// selection depends on (upsertProjectLayer, dedupeProjectLayers).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Selection {
    getSelectedLayers() {
        if (!this.project || !this.project.layers) return [];
        this.dedupeProjectLayers('get_selected_layers');
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            return this.currentLayer ? [this.currentLayer] : [];
        }
        return this.project.layers.filter(l => this.selectedLayerIds.has(l.id));
    }

    upsertProjectLayer(layer) {
        if (!this.project || !this.project.layers || !layer) return;
        const index = this.project.layers.findIndex(l => l.id === layer.id);
        if (index >= 0) {
            this.project.layers[index] = layer;
        } else {
            this.project.layers.push(layer);
        }
    }

    dedupeProjectLayers(reason = 'unknown') {
        if (!this.project || !Array.isArray(this.project.layers)) return;
        const seen = new Set();
        const deduped = [];
        const dropped = [];
        this.project.layers.forEach(layer => {
            if (!layer || layer.id === undefined || layer.id === null) return;
            if (seen.has(layer.id)) {
                dropped.push(layer.id);
                return;
            }
            seen.add(layer.id);
            deduped.push(layer);
        });
        if (dropped.length > 0) {
            this.project.layers = deduped;
            this.selectedLayerIds = new Set([...this.selectedLayerIds].filter(id => seen.has(id)));
            if (this.currentLayer && !seen.has(this.currentLayer.id)) {
                this.currentLayer = this.project.layers.length > 0 ? this.project.layers[0] : null;
            } else if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || this.currentLayer;
            }
            if (typeof sendClientLog === 'function') {
                sendClientLog('project_layers_deduped', { reason, droppedIds: dropped });
            }
        }
    }

    applyToSelectedLayers(fn) {
        const layers = this.getSelectedLayers();
        // v0.11.0: a screen group is ONE screen, so an edit to a member is an
        // edit to the wall. Rather than teach ~70 control handlers about
        // groups, snapshot the shareable fields here, let `fn` do its existing
        // work, then copy across only what actually changed (see
        // GROUP_SHARED_LAYER_FIELDS in app-screen-groups.js). Diffing is what
        // keeps an unrelated edit from silently repainting a peer.
        const snapshot = this._snapshotSharedFields
            ? this._snapshotSharedFields(layers) : null;
        layers.forEach(fn);
        if (snapshot && this._propagateChangedSharedFields) {
            this._propagateChangedSharedFields(layers, snapshot);
        }
    }

    setSelectedLayersByIds(ids, primaryId = null) {
        this.selectedLayerIds = new Set(ids);
        if (primaryId && this.selectedLayerIds.has(primaryId)) {
            this.currentLayer = this.project.layers.find(l => l.id === primaryId) || this.currentLayer;
        } else if (this.selectedLayerIds.size > 0) {
            const firstId = this.selectedLayerIds.values().next().value;
            this.currentLayer = this.project.layers.find(l => l.id === firstId) || this.currentLayer;
        } else {
            this.currentLayer = null;
        }
        if (this.currentLayer) {
            this.lastSelectedLayerId = this.currentLayer.id;
            this.selectionAnchorLayerId = this.currentLayer.id;
        }
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    toggleLayerSelection(layer) {
        if (!layer) return;
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            this.selectedLayerIds = new Set([layer.id]);
            this.currentLayer = layer;
        } else if (this.selectedLayerIds.has(layer.id)) {
            this.selectedLayerIds.delete(layer.id);
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                const nextId = this.selectedLayerIds.values().next().value;
                this.currentLayer = nextId ? this.project.layers.find(l => l.id === nextId) : null;
            }
        } else {
            this.selectedLayerIds.add(layer.id);
            this.currentLayer = layer;
        }
        this.lastSelectedLayerId = layer.id;
        if (!this.selectionAnchorLayerId) {
            this.selectionAnchorLayerId = layer.id;
        }
        // Slice 4 + Slice 13: auto-activate this layer's canvas, but PRESERVE
        // any existing cross-canvas multi-selection. Without this flag,
        // setActiveCanvas would drop selected layers in other canvases - which
        // breaks the "select layers across canvases and bulk-edit them" flow
        // (e.g. shift-click SR in c1, then DJ in c2, then change panel size on
        // both at once).
        this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    selectLayerRange(layer) {
        if (!layer || !this.project || !this.project.layers) return;
        const order = this.layerListOrder || [...this.project.layers].reverse().map(l => l.id);
        const anchorId = this.selectionAnchorLayerId || (this.currentLayer ? this.currentLayer.id : layer.id);
        const startIndex = order.indexOf(anchorId);
        const endIndex = order.indexOf(layer.id);
        if (startIndex === -1 || endIndex === -1) {
            this.selectLayer(layer);
            return;
        }
        const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
        const rangeIds = order.slice(from, to + 1);
        this.selectedLayerIds = new Set(rangeIds);
        this.currentLayer = layer;
        this.lastSelectedLayerId = layer.id;
        // Slice 4 + Slice 13: same preserveSelection trick as
        // toggleLayerSelection so a shift-click range selection that crosses
        // canvas boundaries doesn't get its other-canvas members culled
        // when the active canvas auto-switches.
        this._activateCanvasForLayer(layer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    // Cmd/Ctrl+A (app-menubar's handleMenuShortcut). Selects everything in
    // the current view: on Pixel Map with a cabinet selection already open,
    // every cabinet of that screen (selectAllPixelMapPanels); otherwise
    // every visible layer on the ACTIVE canvas - the same set a marquee
    // over the whole canvas would build, so the Screens panel rows follow
    // through setSelectedLayersByIds. Layers on other canvases are left
    // alone, so "all" means the canvas the person is working in. Returns
    // what it selected ('cabinets', 'layers' or 'none') for the caller's
    // log line.
    //
    // Before this existed Ctrl+A fell through to the browser, which
    // selected every label in the app as TEXT; the next drag on the canvas
    // then dragged that text selection instead of marquee-selecting
    // (Windows/Firefox report, 2026-09-16). The keydown is preventDefault'd
    // by the dispatcher, and #app is user-select: none besides.
    selectAllInView() {
        if (!this.project || !this.project.layers) return 'none';
        const renderer = window.canvasRenderer;
        const viewMode = renderer ? renderer.viewMode : 'pixel-map';
        if (viewMode === 'pixel-map' && this.currentLayer
                && this.pixelMapSelection && this.pixelMapSelection.size > 0
                && typeof this.selectAllPixelMapPanels === 'function') {
            this.selectAllPixelMapPanels();
            return 'cabinets';
        }
        const activeId = this.project.active_canvas_id || null;
        const canvasOf = (layer) => (renderer && renderer._effectiveLayerCanvasId)
            ? renderer._effectiveLayerCanvasId(layer)
            : (layer.canvas_id || null);
        const ids = this.project.layers
            .filter(l => l.visible !== false)
            .filter(l => !activeId || canvasOf(l) === activeId)
            .map(l => l.id);
        if (ids.length === 0) return 'none';
        const primaryId = (this.currentLayer && ids.includes(this.currentLayer.id))
            ? this.currentLayer.id : ids[ids.length - 1];
        this.setSelectedLayersByIds(ids, primaryId);
        return 'layers';
    }
}

for (const k of Object.getOwnPropertyNames(_Selection.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Selection.prototype, k));
    }
}
