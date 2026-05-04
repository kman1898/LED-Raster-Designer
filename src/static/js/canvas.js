class CanvasRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.zoom = 1.0;
        this.panX = 100;
        this.panY = 100;
        this.isDragging = false;
        this.isDraggingLayer = false;
        this.isDraggingScreenName = false;
        this.screenNameDragHistorySaved = false;
        this.isSelectingPanels = false;
        this.isSelectingLayers = false;
        this.selectionRect = null;
        this.layerSelectionRect = null;
        this.magneticSnap = true; // Magnetic snapping enabled by default
        this.spacePressed = false;
        // Slice 6: rasterWidth/Height (and pixel/show variants) are now
        // accessor properties that read from the *active canvas* (or, during
        // the per-canvas render loop, from `_activeRenderCanvas`, set by
        // render() so each canvas's panels clip against ITS own raster, not
        // the active canvas's). Backing fields below are the legacy
        // single-canvas fallback used only when the project has no canvases
        // array (extremely old / pre-Slice-1 projects).
        this._fallbackPixelRasterWidth = 1920;
        this._fallbackPixelRasterHeight = 1080;
        this._fallbackShowRasterWidth = 1920;
        this._fallbackShowRasterHeight = 1080;
        this._activeRenderCanvas = null;
        this.showGrid = true;
        this.viewMode = 'pixel-map'; // Default view mode
        this.exportMode = false; // When true, hides grid and raster boundary for clean export
        this.exportTransparentBg = false; // When true, export renders with transparent background
        
        // Label display settings
        this.showLabelName = true;
        this.showLabelSizePx = false;
        this.showLabelSizeM = false;
        this.showLabelSizeFt = false;
        this.showLabelInfo = false;
        this.labelsColor = '#ffffff';
        this.labelsFontSize = 30;
        
        // Offset display settings
        this.showOffsetTL = false;
        this.showOffsetTR = false;
        this.showOffsetBL = false;
        this.showOffsetBR = false;

        // Slice 6: install raster getters/setters that route to the active
        // canvas. Done in the constructor so every CanvasRenderer instance
        // gets them on its own object (cannot be on the prototype because
        // they shadow plain assignments).
        this._installRasterAccessors();

        this.setupCanvas();
        this.setupEventListeners();
    }

    /**
     * Slice 6 (multi-canvas v0.8): rasterWidth / rasterHeight and the
     * pixel/show variants used to be plain instance fields. They are now
     * computed from the active canvas (or the canvas currently being rendered
     * in the per-canvas loop). Reads return the right value for the current
     * view tab; writes route to the active canvas via the project model so
     * the toolbar Raster: W x H field edits the active canvas's raster.
     *
     * Fallback behaviour (no canvases array, legacy / pre-Slice-1 project):
     * read/write the _fallback* backing fields. Single-canvas behaviour is
     * preserved exactly.
     */
    _installRasterAccessors() {
        const self = this;
        const active = () => {
            const proj = (window.app && window.app.project) || null;
            if (!proj || !Array.isArray(proj.canvases) || proj.canvases.length === 0) return null;
            // Per-canvas render loop sets _activeRenderCanvas so each canvas's
            // panels clip against ITS OWN raster, not the active canvas's.
            if (self._activeRenderCanvas) return self._activeRenderCanvas;
            return proj.canvases.find(c => c.id === proj.active_canvas_id) || proj.canvases[0];
        };
        const isShow = () => self.isShowLookView();
        const def = (name, read, write) => Object.defineProperty(self, name, {
            configurable: true,
            enumerable: true,
            get: read,
            set: write,
        });
        def('pixelRasterWidth',
            () => { const c = active(); return c ? (Number(c.raster_width) || 0) : self._fallbackPixelRasterWidth; },
            (v) => { const c = active(); if (c) c.raster_width = Number(v) || 0; else self._fallbackPixelRasterWidth = Number(v) || 0; });
        def('pixelRasterHeight',
            () => { const c = active(); return c ? (Number(c.raster_height) || 0) : self._fallbackPixelRasterHeight; },
            (v) => { const c = active(); if (c) c.raster_height = Number(v) || 0; else self._fallbackPixelRasterHeight = Number(v) || 0; });
        def('showRasterWidth',
            () => { const c = active(); return c ? (Number(c.show_raster_width) || Number(c.raster_width) || 0) : self._fallbackShowRasterWidth; },
            (v) => { const c = active(); if (c) c.show_raster_width = Number(v) || 0; else self._fallbackShowRasterWidth = Number(v) || 0; });
        def('showRasterHeight',
            () => { const c = active(); return c ? (Number(c.show_raster_height) || Number(c.raster_height) || 0) : self._fallbackShowRasterHeight; },
            (v) => { const c = active(); if (c) c.show_raster_height = Number(v) || 0; else self._fallbackShowRasterHeight = Number(v) || 0; });
        def('rasterWidth',
            () => isShow() ? self.showRasterWidth : self.pixelRasterWidth,
            (v) => { if (isShow()) self.showRasterWidth = v; else self.pixelRasterWidth = v; });
        def('rasterHeight',
            () => isShow() ? self.showRasterHeight : self.pixelRasterHeight,
            (v) => { if (isShow()) self.showRasterHeight = v; else self.pixelRasterHeight = v; });
    }
    
    setupCanvas() {
        const wrapper = this.canvas.parentElement;
        this.canvas.width = wrapper.clientWidth;
        this.canvas.height = wrapper.clientHeight;
        this.render();
    }
    
    setupEventListeners() {
        this.canvas.addEventListener('mousedown', this.handleMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.handleMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.handleMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.handleWheel.bind(this));
        this.canvas.addEventListener('contextmenu', this.handleContextMenu.bind(this));
        document.addEventListener('keydown', this.handleKeyDown.bind(this));
        document.addEventListener('keyup', this.handleKeyUp.bind(this));
        window.addEventListener('mouseup', () => {
            const hadLayerRect = !!this.layerSelectionRect;
            const hadPanelRect = !!this.selectionRect;
            if (!this.isSelectingLayers && !this.isSelectingPanels && !hadLayerRect && !hadPanelRect) return;
            // Clear stuck selection box if mouseup happens off-canvas or flags get out of sync
            if (this.isSelectingLayers || hadLayerRect) {
                this.isSelectingLayers = false;
                this.layerSelectionRect = null;
            }
            if (this.isSelectingPanels || hadPanelRect) {
                this.isSelectingPanels = false;
                this.selectionRect = null;
            }
            if (typeof sendClientLog === 'function') {
                sendClientLog('selection_cleared_off_canvas', {
                    viewMode: this.viewMode,
                    hadLayerRect,
                    hadPanelRect
                });
            }
            this.render();
        });
        window.addEventListener('resize', () => this.setupCanvas());
    }

    snap(value) {
        return this.exportMode ? Math.round(value) : value;
    }

    snapRect(x, y, width, height) {
        if (!this.exportMode) {
            return { x, y, width, height };
        }
        return {
            x: Math.round(x),
            y: Math.round(y),
            width: Math.round(width),
            height: Math.round(height)
        };
    }

    /**
     * Returns true when the current view uses the Show Look position
     * (showOffsetX/Y) instead of the processor position (offset_x/y).
     * Show Look itself, plus Data Flow and Power, all render at the
     * real-world stage layout per the Show Look feature spec.
     */
    isShowLookView(mode = this.viewMode) {
        return mode === 'show-look' || mode === 'data-flow' || mode === 'power';
    }

    /**
     * True when the active view is one of the wiring views (Data Flow /
     * Power) AND the project's perspective for that view is 'back'. In that
     * case render() horizontally mirrors the canvas around the right edge
     * of the raster so techs working behind the wall see the layout from
     * their perspective. Labels are un-mirrored at draw time via _fillText
     * / _strokeText so they stay readable.
     */
    isMirroredView() {
        if (!window.app || !window.app.project) return false;
        // v0.8 Slice 8: perspective is per-canvas. Read from the active
        // canvas first; fall back to the project root for legacy projects
        // that haven't been migrated (and the synthetic canvasesToRender
        // entry built at render() for pre-Slice-1 fallbacks).
        const proj = window.app.project;
        const active = (typeof window.app._activeCanvas === 'function')
            ? window.app._activeCanvas() : null;
        if (this.viewMode === 'data-flow') {
            const v = (active && active.data_flow_perspective) || proj.data_flow_perspective;
            return v === 'back';
        }
        if (this.viewMode === 'power') {
            const v = (active && active.power_perspective) || proj.power_perspective;
            return v === 'back';
        }
        return false;
    }

    /**
     * fillText that auto-un-mirrors when the canvas is in a mirrored
     * (back-view) render so label glyphs stay right-side-up. Anchor
     * position is the same as ctx.fillText, pass the position you would
     * have used in normal rendering. Text alignment ('center' is the most
     * common in this codebase) keeps its visual centering. Edge-aligned
     * text ('left'/'right') will flip its anchor side, which is the right
     * behavior for a back view (the cabinet's left edge becomes its right
     * in the tech's view).
     */
    _fillText(text, x, y, maxWidth) {
        if (this._mirror) {
            this.ctx.save();
            this.ctx.translate(x, y);
            this.ctx.scale(-1, 1);
            if (maxWidth !== undefined) this.ctx.fillText(text, 0, 0, maxWidth);
            else this.ctx.fillText(text, 0, 0);
            this.ctx.restore();
        } else {
            if (maxWidth !== undefined) this.ctx.fillText(text, x, y, maxWidth);
            else this.ctx.fillText(text, x, y);
        }
    }

    _strokeText(text, x, y, maxWidth) {
        if (this._mirror) {
            this.ctx.save();
            this.ctx.translate(x, y);
            this.ctx.scale(-1, 1);
            if (maxWidth !== undefined) this.ctx.strokeText(text, 0, 0, maxWidth);
            else this.ctx.strokeText(text, 0, 0);
            this.ctx.restore();
        } else {
            if (maxWidth !== undefined) this.ctx.strokeText(text, x, y, maxWidth);
            else this.ctx.strokeText(text, x, y);
        }
    }

    /**
     * Build a clip path that constrains drawing to the active raster bounds
     * in *screen* space, even when the caller is currently inside a per-layer
     * ctx.translate(dx, dy). Without this, a naive `ctx.rect(0,0,rasterWidth,
     * rasterHeight); ctx.clip()` ends up clipping in local (translated)
     * coords, which means screen coords [dx, dx+rasterWidth], and lops off
     * any content drawn at low screen-x when the layer is shifted right (or
     * vice versa). All renderers that paint within the per-layer translate
     * (renderLayerLabels, renderDataFlowArrows, renderPowerArrows, etc.)
     * should use this instead of the raw raster rect.
     */
    _clipToActiveRaster() {
        const dx = this._renderDx || 0;
        const dy = this._renderDy || 0;
        this.ctx.beginPath();
        this.ctx.rect(-dx, -dy, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
    }

    /**
     * Layer bounds in the *currently active view's* coordinate space.
     * For pixel-map / cabinet-id this matches getLayerBounds (processor
     * coords). For show-look / data-flow / power it shifts by the layer's
     * showOffset - offset_x/y delta so selection rects, hit-tests, and
     * magnetic snap line up with the rendered position.
     */
    /**
     * Multi-canvas (v0.8 Slice 3): draw a single canvas's dashed outline at
     * the origin of the current ctx (caller is expected to have already
     * translated to canvas.workspace_x/y). The outline color matches
     * canvas.color; the active canvas gets a 1.5x bolder stroke. Skipped in
     * exportMode by the caller.
     *
     * Uses the canvas's own raster_width/raster_height (not the renderer's
     * project-level rasterWidth) so each canvas's rect reflects its own
     * size, even though Slice 3 keeps the source-of-truth at project root
     * for the active canvas; per-canvas raster sizes are read straight from
     * the canvas object here.
     */
    _drawCanvasOutline(canvas, isActive) {
        if (!canvas) return;
        // For Slice 3, pixel-map / cabinet-id views use raster_width/height;
        // show-look / data-flow / power use show_raster_width/height. Falls
        // back to raster_width/height if the show-raster fields are missing.
        const useShow = this.isShowLookView();
        const w = (useShow && canvas.show_raster_width) || canvas.raster_width || 0;
        const h = (useShow && canvas.show_raster_height) || canvas.raster_height || 0;
        if (w <= 0 || h <= 0) return;
        const color = canvas.color || '#ff0000';
        const isCrossDropTarget = !!(this._crossCanvasDropTarget
            && this._crossCanvasDropTarget.id === canvas.id);
        this.ctx.save();
        if (isCrossDropTarget) {
            // Slice 7 hint: brighten outline + faint fill so the user sees
            // where their shift+drag will land.
            this.ctx.fillStyle = color + '22';
            this.ctx.fillRect(0, 0, w, h);
        }
        this.ctx.strokeStyle = color;
        const baseLW = Math.max(3, 5 / this.zoom);
        this.ctx.lineWidth = isCrossDropTarget ? baseLW * 2.2
            : (isActive ? baseLW * 1.5 : baseLW);
        this.ctx.setLineDash([10, 5]);
        this.ctx.strokeRect(0, 0, w, h);
        this.ctx.setLineDash([]);
        this.ctx.restore();
    }

    /**
     * Faint background tint for the active canvas. Painted BEFORE layers
     * (so layers paint over it) so the tint is visible only in empty
     * regions of the active canvas's raster.
     */
    _drawActiveCanvasTint(canvas) {
        if (!canvas) return;
        const useShow = this.isShowLookView();
        const w = (useShow && canvas.show_raster_width) || canvas.raster_width || 0;
        const h = (useShow && canvas.show_raster_height) || canvas.raster_height || 0;
        if (w <= 0 || h <= 0) return;
        const color = canvas.color || '#ff0000';
        // ~6% alpha (0F in 8-digit hex). Caller already translated to canvas
        // origin, so fill at (0, 0).
        this.ctx.save();
        this.ctx.fillStyle = color + '0F';
        this.ctx.fillRect(0, 0, w, h);
        this.ctx.restore();
    }

    getLayerBoundsInActiveView(layer) {
        const b = this.getLayerBounds(layer);
        const { dx, dy } = this.getLayerRenderOffset(layer);
        return { x: b.x + dx, y: b.y + dy, width: b.width, height: b.height };
    }

    /**
     * Render-time translation to apply to a layer's geometry so it appears
     * at its show position in show-look / data-flow / power. Returns
     * {dx: 0, dy: 0} for pixel-map / cabinet-id (no shift).
     */
    getLayerRenderOffset(layer) {
        if (!layer || !this.isShowLookView()) return { dx: 0, dy: 0 };
        const procX = Number(layer.offset_x) || 0;
        const procY = Number(layer.offset_y) || 0;
        const showX = (layer.showOffsetX !== null && layer.showOffsetX !== undefined)
            ? Number(layer.showOffsetX) : procX;
        const showY = (layer.showOffsetY !== null && layer.showOffsetY !== undefined)
            ? Number(layer.showOffsetY) : procY;
        return { dx: showX - procX, dy: showY - procY };
    }

    getLayerBounds(layer) {
        // NOTE: returns RAW processor-coords bounds (not shifted by Show Look
        // offset). Most callers use this for things drawn INSIDE the per-layer
        // ctx.translate(dx, dy) block in render(), so adding dx here would
        // double-shift them. Callers that operate OUTSIDE the per-layer
        // translate (selection bounding box, hit-test, magnetic snap, layer
        // drag overlay) should use getLayerBoundsInActiveView(layer) instead,
        // which adds the active view's render offset.
        if (layer && (layer.type || 'screen') === 'text') {
            return {
                x: Number(layer.offset_x) || 0,
                y: Number(layer.offset_y) || 0,
                width: Number(layer.textWidth) || 400,
                height: Number(layer.textHeight) || 100
            };
        }
        if (layer && (layer.type || 'screen') === 'image') {
            const scale = Number(layer.imageScale) || 1;
            const width = (Number(layer.imageWidth) || 0) * scale;
            const height = (Number(layer.imageHeight) || 0) * scale;
            return {
                x: Number(layer.offset_x) || 0,
                y: Number(layer.offset_y) || 0,
                width,
                height
            };
        }
        if (layer && Array.isArray(layer.panels) && layer.panels.length > 0) {
            let minX = Infinity;
            let minY = Infinity;
            let maxX = -Infinity;
            let maxY = -Infinity;
            layer.panels.forEach(panel => {
                const x1 = Number(panel.x) || 0;
                const y1 = Number(panel.y) || 0;
                const x2 = x1 + (Number(panel.width) || 0);
                const y2 = y1 + (Number(panel.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return {
                x: minX,
                y: minY,
                width: maxX - minX,
                height: maxY - minY
            };
        }
        const width = (Number(layer.columns) || 0) * (Number(layer.cabinet_width) || 0);
        const height = (Number(layer.rows) || 0) * (Number(layer.cabinet_height) || 0);
        return {
            x: Number(layer.offset_x) || 0,
            y: Number(layer.offset_y) || 0,
            width,
            height
        };
    }
    
    // When the active view is mirrored (Back perspective), the canvas is
    // flipped horizontally for display only. Mouse coordinates are still in
    // un-mirrored screen space, so we have to flip them back into layer
    // coordinates before any hit-testing / drag math.
    _unmirrorWorldX(worldX) {
        if (!this.isMirroredView()) return worldX;
        // v0.8 Slice 8 fix: mirror axis is the workspace bounds, not the
        // active canvas's raster, otherwise multi-canvas workspaces flip
        // off-screen because workspace_x can be far past rasterWidth.
        const k = this._mirrorAxisX();
        return k - worldX;
    }

    /**
     * The Canvas2D translate-X used as the mirror axis when Back perspective
     * is active. We mirror around the workspace bounding box so points stay
     * in the same x-range after the flip, single-canvas projects degrade to
     * mirroring around rasterWidth (legacy behaviour) automatically because
     * their bbox.x is 0 and bbox.w == rasterWidth.
     */
    _mirrorAxisX() {
        const bb = this._workspaceBounds();
        // K such that K - x maps left edge to right edge of bbox:
        //   K - bbox.x = bbox.x + bbox.w  →  K = 2*bbox.x + bbox.w
        return 2 * (bb.x || 0) + (bb.width || this.rasterWidth);
    }

    /**
     * Slice 4: hit-test a workspace point against the visible canvases.
     * Returns the first canvas (in array order, earlier wins on overlap)
     * whose rect contains (worldX, worldY), or null. Uses the same per-mode
     * raster fields _drawCanvasOutline does, including the workspace_x/y
     * offset so the rect is in workspace coords (matching worldX/worldY).
     */
    _canvasAtPoint(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        const arr = window.app.project.canvases;
        if (!Array.isArray(arr) || arr.length === 0) return null;
        const useShow = this.isShowLookView();
        for (const c of arr) {
            if (!c || c.visible === false) continue;
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            const h = (useShow && c.show_raster_height) || c.raster_height || 0;
            if (w <= 0 || h <= 0) continue;
            const x = c.workspace_x || 0;
            const y = c.workspace_y || 0;
            if (worldX >= x && worldX <= x + w && worldY >= y && worldY <= y + h) {
                return c;
            }
        }
        return null;
    }

    /**
     * Slice 5: hit-test a workspace point against the dashed outline edges
     * of visible canvases. Returns the first canvas whose outline edge is
     * within EDGE_HIT_PX (screen pixels, converted to world units via
     * /this.zoom) of (worldX, worldY), or null.
     *
     * "Edge" = within `tol` of any of the four edges of the canvas rect,
     * but the point must also be inside the rect-with-tolerance overall
     * (so corners count). Inside the canvas body (more than `tol` away
     * from every edge) does NOT count, that's reserved for body-click
     * activate / panel selection.
     */
    _canvasEdgeAtPoint(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        const arr = window.app.project.canvases;
        if (!Array.isArray(arr) || arr.length === 0) return null;
        const EDGE_HIT_PX = 6;
        const tol = EDGE_HIT_PX / Math.max(this.zoom, 0.0001);
        const useShow = this.isShowLookView();
        for (const c of arr) {
            if (!c || c.visible === false) continue;
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            const h = (useShow && c.show_raster_height) || c.raster_height || 0;
            if (w <= 0 || h <= 0) continue;
            const x = c.workspace_x || 0;
            const y = c.workspace_y || 0;
            // Outer bounds (rect + tol on every side)
            if (worldX < x - tol || worldX > x + w + tol) continue;
            if (worldY < y - tol || worldY > y + h + tol) continue;
            // Inside any of the four edge bands?
            const nearLeft   = Math.abs(worldX - x)       <= tol;
            const nearRight  = Math.abs(worldX - (x + w)) <= tol;
            const nearTop    = Math.abs(worldY - y)       <= tol;
            const nearBottom = Math.abs(worldY - (y + h)) <= tol;
            if (nearLeft || nearRight || nearTop || nearBottom) {
                return c;
            }
        }
        return null;
    }

    handleMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom);
        const worldY = (mouseY - this.panY) / this.zoom;

        // Slice 5: dragging a canvas's dashed outline edge repositions
        // the canvas in the workspace. Must be checked BEFORE the Slice 4
        // panel/canvas-activate block so edge-drag wins over body-click
        // activation. Skipped for pan (space), shift, and alt, those are
        // existing drag/paint behaviors. Inside the canvas body still
        // falls through to Slice 4.
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            const edgeCanvas = this._canvasEdgeAtPoint(worldX, worldY);
            if (edgeCanvas) {
                this.isDraggingCanvas = true;
                this.draggingCanvasId = edgeCanvas.id;
                this.canvasDragStartX = worldX;
                this.canvasDragStartY = worldY;
                this.canvasDragStartWX = edgeCanvas.workspace_x || 0;
                this.canvasDragStartWY = edgeCanvas.workspace_y || 0;
                // saveState moved to canvas-drag END (in updateCanvas .then())
                // so the snapshot is the POST-drag workspace position. Pre-drag
                // saveState was off-by-one and made undo skip past the drag.
                // Activate the dragged canvas so the sidebar reflects it.
                if (window.app && window.app.project
                    && window.app.project.active_canvas_id !== edgeCanvas.id
                    && typeof window.app.setActiveCanvas === 'function') {
                    window.app.setActiveCanvas(edgeCanvas.id);
                }
                this.canvas.style.cursor = 'grabbing';
                if (typeof sendClientLog === 'function') {
                    sendClientLog('canvas_drag_start', { canvasId: edgeCanvas.id });
                }
                return;
            }
        }

        // Slice 4 (+ multi-canvas hit-test fix): every left click in the
        // workspace either:
        //   (a) hits a panel in some canvas's layer → activate that canvas
        //       and make that layer the currentLayer so the existing
        //       panel-select / layer-action paths can run against it
        //       without the user having to click the layer in the sidebar
        //       first;
        //   (b) hits empty area inside a canvas's rect → activate that
        //       canvas;
        //   (c) hits empty area outside any canvas → no canvas change.
        // Skipped for pan (space) and shift/alt modifiers (existing drag
        // behaviors). Additive, the rest of mouse-down still runs.
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            const hitPanel = this.getPanelAt(worldX, worldY);
            if (hitPanel) {
                // Panel hit: switch to its layer's canvas if needed, and
                // promote its layer to currentLayer if needed. Both gates
                // are no-ops when already in scope, so single-canvas /
                // current-layer flows are unchanged.
                const layer = window.app && window.app.project
                    && window.app.project.layers.find(l => l.id === hitPanel.layerId);
                if (layer) {
                    if (layer.canvas_id
                        && window.app.project.active_canvas_id !== layer.canvas_id
                        && typeof window.app.setActiveCanvas === 'function') {
                        window.app.setActiveCanvas(layer.canvas_id);
                    }
                    if ((!window.app.currentLayer || window.app.currentLayer.id !== layer.id)
                        && typeof window.app.selectLayer === 'function') {
                        // selectLayer takes the layer OBJECT, not the id
                        // (the !layer.id guard rejects raw integers).
                        window.app.selectLayer(layer);
                    }
                }
            } else {
                const hitCanvas = this._canvasAtPoint(worldX, worldY);
                if (hitCanvas && hitCanvas.id
                    && window.app
                    && window.app.project
                    && hitCanvas.id !== window.app.project.active_canvas_id
                    && typeof window.app.setActiveCanvas === 'function') {
                    window.app.setActiveCanvas(hitCanvas.id);
                }
            }
        }

        if (e.button === 0 && this.spacePressed) {
            this.isDragging = true;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.canvas.style.cursor = 'grabbing';
            return;
        }
        
        if (e.button === 0 && e.shiftKey) {
            // Let shift+drag behavior handle screen name move on cabinet-id /
            // data-flow / power. On pixel-map and show-look, fall through so
            // shift+drag moves the entire layer (writing to offset_x/y or
            // showOffsetX/Y respectively).
            if (window.app && window.app.currentLayer) {
                if (this.viewMode !== 'pixel-map' && this.viewMode !== 'show-look') {
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;
                    
                    let currentOffsetX = 0;
                    let currentOffsetY = 0;
                    
                    if (this.viewMode === 'cabinet-id') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXCabinet || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYCabinet || 0;
                    } else if (this.viewMode === 'data-flow') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXDataFlow || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYDataFlow || 0;
                    } else if (this.viewMode === 'power') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPower || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPower || 0;
                    }
                    
                    this.screenNameStartOffset = { x: currentOffsetX, y: currentOffsetY };
                    return;
                }
            }
        }

        if (e.button === 0 && window.app && window.app.currentLayer && this.viewMode === 'data-flow') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlow(layer)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }
        if (e.button === 0 && window.app && window.app.currentLayer && this.viewMode === 'power') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomPower(layer)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }

        // Pixel Map: drag-select panels of the current layer for bulk
        // Set-Blank / Set-Half-tile actions. Falls through to layer selection
        // when the drag starts in empty space (so layer multi-select still works).
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey
                && this.viewMode === 'pixel-map'
                && window.app && window.app.currentLayer) {
            const startPanel = this.getPanelAt(worldX, worldY);
            // Allow drag-start on hidden ("blank") panels too, selecting them
            // is the only way to bulk-restore via the sidebar buttons.
            const onCurrentLayer = startPanel
                && startPanel.layerId === window.app.currentLayer.id;
            // Don't capture the click for panel-select if there's a HIGHER-Z
            // layer (image / text / another screen later in project.layers)
            // sitting on top of the current layer at this point, the user is
            // clicking the visible top layer, not the panel buried beneath it.
            // Bug: with a text layer over a selected screen, clicks on text
            // were grabbed by the screen's panel-select instead of selecting
            // the text layer.
            const topLayer = this.getLayerAt(worldX, worldY);
            const topIsHigher = topLayer && window.app.project
                && window.app.project.layers.indexOf(topLayer)
                    > window.app.project.layers.indexOf(window.app.currentLayer);
            if (onCurrentLayer && !topIsHigher) {
                this.isSelectingPixelMapPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: window.app.currentLayer.id });
                }
                return;
            }
        }

        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            // Falling through to layer-select means the user clicked outside any
            // panel in pixel-map (or in another view). Drop any stale pixel-map
            // panel selection so it doesn't sit around, fresh layer-drag should
            // start without panel-state lingering.
            if (this.viewMode === 'pixel-map' && window.app && window.app.pixelMapSelection
                    && window.app.pixelMapSelection.size > 0) {
                window.app.clearPixelMapSelection();
            }
            this.isSelectingLayers = true;
            this.layerSelectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
            if (typeof sendClientLog === 'function') {
                sendClientLog('layer_selection_start', { viewMode: this.viewMode });
            }
            return;
        }
        
        if (e.button === 1 || (e.button === 0 && this.spacePressed)) {
            this.isDragging = true;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.canvas.style.cursor = 'grabbing';
        } else if (e.button === 0 && e.shiftKey && !e.altKey) {
            if (window.app && window.app.currentLayer) {
                // On pixel-map / show-look: drag entire layer.
                //   - pixel-map writes to offset_x/y (the processor position)
                //   - show-look writes to showOffsetX/Y (the show position)
                // On data-flow / power / cabinet-id: drag screen name label only.
                if (this.viewMode === 'pixel-map' || this.viewMode === 'show-look') {
                    const selected = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    const uniqueSelected = [];
                    const seenIds = new Set();
                    selected.forEach(layer => {
                        if (!layer || seenIds.has(layer.id)) return;
                        seenIds.add(layer.id);
                        uniqueSelected.push(layer);
                    });
                    const movable = uniqueSelected.filter(layer => !layer.locked);
                    if (movable.length === 0) {
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_drag_blocked_locked', { viewMode: this.viewMode });
                        }
                        return;
                    }
                    this.isDraggingLayer = true;
                    this.dragLayerMode = (this.viewMode === 'show-look') ? 'show' : 'processor';
                    // saveState moved to drag-END so the snapshot captures the
                    // POST-drag project state. Undo decrements then restores
                    // the previous post-state, which matches the user's
                    // expectation of "one Cmd+Z reverts one drag." Pre-drag
                    // saveState was off-by-one and made undo skip past the
                    // most recent action.
                    this.dragLayerStartX = worldX;
                    this.dragLayerStartY = worldY;
                    const useShow = this.dragLayerMode === 'show';
                    const startX = useShow
                        ? (window.app.currentLayer.showOffsetX ?? window.app.currentLayer.offset_x ?? 0)
                        : (window.app.currentLayer.offset_x ?? 0);
                    const startY = useShow
                        ? (window.app.currentLayer.showOffsetY ?? window.app.currentLayer.offset_y ?? 0)
                        : (window.app.currentLayer.offset_y ?? 0);
                    this.layerStartOffset = { x: startX, y: startY };
                    this.dragLayerOffsets = movable.map(layer => ({
                        id: layer.id,
                        startX: useShow
                            ? (layer.showOffsetX ?? layer.offset_x ?? 0)
                            : (layer.offset_x ?? 0),
                        startY: useShow
                            ? (layer.showOffsetY ?? layer.offset_y ?? 0)
                            : (layer.offset_y ?? 0),
                        // Capture whether this layer's show position was
                        // linked to its processor position at drag-start
                        // (i.e. equal). If so, dragging in pixel-map should
                        // also update showOffset so Show Look / Data / Power
                        // track the new position. Once they diverge (because
                        // the user moved the layer in Show Look), pixel-map
                        // drags stop touching showOffset.
                        showLinkedX: !useShow && (Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0)),
                        showLinkedY: !useShow && (Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0)),
                        // Only the processor-position drag mutates panel.x/y
                        // (panels live in processor coords). Show-position
                        // drag is rendered via ctx.translate so panels stay
                        // put.
                        panelStarts: useShow ? null : (layer.panels || []).map(panel => ({
                            id: panel.id,
                            x: panel.x,
                            y: panel.y
                        }))
                    }));
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('layer_drag_start', {
                            viewMode: this.viewMode,
                            mode: this.dragLayerMode,
                            layerIds: movable.map(l => l.id),
                        });
                    }
                } else {
                    // Dragging screen name on cabinet-id, data-flow, power modes
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;
                    
                    // Get tab-specific screen name offset
                    let currentOffsetX = 0;
                    let currentOffsetY = 0;
                    
                    if (this.viewMode === 'cabinet-id') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXCabinet || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYCabinet || 0;
                    } else if (this.viewMode === 'data-flow') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXDataFlow || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYDataFlow || 0;
                    } else if (this.viewMode === 'power') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPower || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPower || 0;
                    }
                    
                    this.screenNameStartOffset = {
                        x: currentOffsetX,
                        y: currentOffsetY
                    };
                }
            }
        } else if (e.button === 0 && e.altKey && e.shiftKey) {
            // Alt+Shift+click toggles per-panel half-tile (auto direction).
            // When a multi-selection is active, apply to the entire selection
            // instead of just the clicked panel.
            if (this.viewMode === 'pixel-map') {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel && window.app && window.app.currentLayer
                        && clickedPanel.layerId === window.app.currentLayer.id
                        && !clickedPanel.panel.hidden) {
                    e.preventDefault();
                    const p = clickedPanel.panel;
                    const selected = window.app.getPixelMapSelectedPanels
                        ? window.app.getPixelMapSelectedPanels()
                        : [];
                    const targets = selected.length > 0 ? selected : [p];
                    // Toggle: if any target panel currently has a halfTile, clear all;
                    // otherwise auto-detect per panel and apply.
                    const anyOn = targets.some(t => t.halfTile && t.halfTile !== 'none');
                    const targetMode = anyOn ? 'none' : 'auto';
                    window.app.setPanelsHalfTileBulk(targets, targetMode);
                }
            }
        } else if (e.button === 0 && e.altKey) {
            // Alt+click/drag toggles "blank" (hidden) on the panel.
            // When a multi-selection is active, apply to the entire selection
            // in one shot (no drag-painting in that mode, the selection is
            // already explicit).
            if (this.viewMode === 'pixel-map') {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel && window.app) {
                    e.preventDefault();
                    const selected = (window.app.getPixelMapSelectedPanels
                        ? window.app.getPixelMapSelectedPanels()
                        : []);
                    if (selected.length > 0) {
                        // Toggle direction: if any selected panel is currently
                        // visible, hide all; otherwise show all.
                        const anyVisible = selected.some(p => !p.hidden);
                        window.app.setPanelsBlankBulk(selected, anyVisible);
                        return;
                    }
                    this.isAltPainting = true;
                    this.altPaintLayerId = clickedPanel.layerId;
                    this.altPaintMode = clickedPanel.panel.hidden ? 'show' : 'hide';
                    this.altPaintedPanelIds = new Set();
                    clickedPanel.panel.hidden = (this.altPaintMode === 'hide');
                    this.altPaintedPanelIds.add(clickedPanel.panel.id);
                    this.render();
                }
            }
        } else if (e.button === 0 && this.viewMode === 'data-flow' && window.app) {
            const layer = this.getLayerAt(worldX, worldY);
            if (layer) {
                window.app.selectLayer(layer);
            } else {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel) {
                    const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                    if (panelLayer) {
                        window.app.selectLayer(panelLayer);
                    }
                }
            }
        } else if (e.button === 0) {
            if (window.app) {
                const layer = this.getLayerAt(worldX, worldY);
                if (layer) {
                    window.app.selectLayer(layer);
                } else {
                    const clickedPanel = this.getPanelAt(worldX, worldY);
                    if (clickedPanel) {
                        const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        if (panelLayer) {
                            window.app.selectLayer(panelLayer);
                        }
                    }
                }
            }
        }
    }
    
    handleMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom);
        const worldY = (mouseY - this.panY) / this.zoom;

        // Slice 5: live canvas-drag, update workspace_x/y on every move,
        // but only PUT to the server on mouseup (avoid flooding).
        if (this.isDraggingCanvas && this.draggingCanvasId) {
            if (window.app && window.app.project) {
                const c = window.app.project.canvases.find(c => c.id === this.draggingCanvasId);
                if (c) {
                    const dx = worldX - this.canvasDragStartX;
                    const dy = worldY - this.canvasDragStartY;
                    let nextX = this.canvasDragStartWX + dx;
                    let nextY = this.canvasDragStartWY + dy;
                    // v0.8 Slice 9: snap dragged canvas edges to neighbor
                    // canvas edges (left↔right, right↔left, top↔bottom,
                    // bottom↔top, plus aligned-edge snap). Honors the global
                    // magnetic-snap toggle so users can disable it.
                    if (this.magneticSnap) {
                        const snapped = this._snapCanvasToNeighbors(c, nextX, nextY);
                        nextX = snapped.x;
                        nextY = snapped.y;
                    }
                    c.workspace_x = nextX;
                    c.workspace_y = nextY;
                    this.render();
                }
            }
            return;
        }

        if (this.isAltPainting) {
            const clickedPanel = this.getPanelAt(worldX, worldY);
            if (clickedPanel && clickedPanel.layerId === this.altPaintLayerId && !this.altPaintedPanelIds.has(clickedPanel.panel.id)) {
                clickedPanel.panel.hidden = (this.altPaintMode === 'hide');
                this.altPaintedPanelIds.add(clickedPanel.panel.id);
                this.render();
            }
            return;
        }

        if (this.isSelectingPanels && this.selectionRect) {
            this.selectionRect.x2 = worldX;
            this.selectionRect.y2 = worldY;
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                window.app.selectPanelsInRect(window.app.currentLayer, this.selectionRect);
            } else if (window.app && window.app.currentLayer && this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer)) {
                window.app.selectPowerPanelsInRect(window.app.currentLayer, this.selectionRect);
            }
            this.render();
            return;
        }

        if (this.isSelectingPixelMapPanels && this.selectionRect) {
            this.selectionRect.x2 = worldX;
            this.selectionRect.y2 = worldY;
            if (window.app && window.app.currentLayer) {
                window.app.selectPixelMapPanelsInRect(window.app.currentLayer, this.selectionRect);
            }
            this.render();
            return;
        }

        if (this.isSelectingLayers && this.layerSelectionRect) {
            this.layerSelectionRect.x2 = worldX;
            this.layerSelectionRect.y2 = worldY;
            this.render();
            return;
        }
        
        document.getElementById('cursor-position').textContent = `X: ${Math.round(worldX)}, Y: ${Math.round(worldY)}`;
        
        if (this.isDragging) {
            const dx = mouseX - this.dragStartX;
            const dy = mouseY - this.dragStartY;
            this.panX += dx;
            this.panY += dy;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.render();
        } else if (this.isDraggingLayer) {
            const dx = Math.round(worldX - this.dragLayerStartX);
            const dy = Math.round(worldY - this.dragLayerStartY);
            
            if (window.app && window.app.currentLayer) {
                let snapDx = dx;
                let snapDy = dy;
                let newOffsetX = this.layerStartOffset.x + dx;
                let newOffsetY = this.layerStartOffset.y + dy;
                
                // Magnetic snapping (only if enabled) based on current layer
                if (this.magneticSnap) {
                    const snapResult = this.calculateMagneticSnap(newOffsetX, newOffsetY, window.app.currentLayer);
                    snapDx = snapResult.x - this.layerStartOffset.x;
                    snapDy = snapResult.y - this.layerStartOffset.y;
                }
                
                const selected = this.dragLayerOffsets && this.dragLayerOffsets.length > 0
                    ? this.dragLayerOffsets
                    : [{ id: window.app.currentLayer.id, startX: this.layerStartOffset.x, startY: this.layerStartOffset.y }];
                const movable = selected.filter(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    return layer && !layer.locked;
                });
                if (movable.length === 0) {
                    return;
                }
                const showMode = this.dragLayerMode === 'show';
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    if (showMode) {
                        // Show Look drag, only the show position changes;
                        // panels stay at their processor coords.
                        layer.showOffsetX = nextX;
                        layer.showOffsetY = nextY;
                    } else {
                        layer.offset_x = nextX;
                        layer.offset_y = nextY;
                        // While show position was linked to processor position,
                        // keep them in sync so Show Look / Data / Power follow
                        // the pixel-map move.
                        if (item.showLinkedX) layer.showOffsetX = nextX;
                        if (item.showLinkedY) layer.showOffsetY = nextY;
                        const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                        layer.panels.forEach(panel => {
                            const start = startMap.get(panel.id);
                            if (!start) return;
                            panel.x = start.x + snapDx;
                            panel.y = start.y + snapDy;
                        });
                    }
                });

                // Track cross-canvas drop target for visual hint. Match the
                // mouseUp drop logic: hit-test the **mouse cursor**, not the
                // layer center (so wide layers feel responsive).
                const _primary = window.app.currentLayer;
                if (_primary) {
                    const _tgt = this._canvasAtPoint(worldX, worldY);
                    this._crossCanvasDropTarget = (_tgt && _tgt.id !== _primary.canvas_id) ? _tgt : null;
                } else {
                    this._crossCanvasDropTarget = null;
                }

                this.render();
            }
        } else if (this.isDraggingScreenName) {
            // Screen name dragging with snap positions - tab-specific
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                // Screen-name drag, bounds in the active view for snap calc.
                const bounds = this.getLayerBoundsInActiveView(layer);
                const layerWidth = bounds.width;
                const layerHeight = bounds.height;
                
                // Calculate raw offset from drag
                const dx = worldX - this.dragScreenNameStartX;
                const dy = worldY - this.dragScreenNameStartY;
                
                let newOffsetX = this.screenNameStartOffset.x + dx;
                let newOffsetY = this.screenNameStartOffset.y + dy;
                
                // Only snap if magnetic snap is enabled
                if (this.magneticSnap) {
                    // Snap positions relative to layer center (0,0 = center)
                    // Left: -layerWidth/2, Center: 0, Right: layerWidth/2
                    // Top: -layerHeight/2, Middle: 0, Bottom: layerHeight/2
                    const snapThreshold = 20;
                    const snapPositionsX = [-layerWidth/2, 0, layerWidth/2];
                    const snapPositionsY = [-layerHeight/2, 0, layerHeight/2];
                    
                    // Snap X
                    for (const snapX of snapPositionsX) {
                        if (Math.abs(newOffsetX - snapX) < snapThreshold) {
                            newOffsetX = snapX;
                            break;
                        }
                    }
                    
                    // Snap Y
                    for (const snapY of snapPositionsY) {
                        if (Math.abs(newOffsetY - snapY) < snapThreshold) {
                            newOffsetY = snapY;
                            break;
                        }
                    }
                }
                
                // Store in tab-specific properties
                if (this.viewMode === 'cabinet-id') {
                    layer.screenNameOffsetXCabinet = newOffsetX;
                    layer.screenNameOffsetYCabinet = newOffsetY;
                } else if (this.viewMode === 'data-flow') {
                    layer.screenNameOffsetXDataFlow = newOffsetX;
                    layer.screenNameOffsetYDataFlow = newOffsetY;
                } else if (this.viewMode === 'power') {
                    layer.screenNameOffsetXPower = newOffsetX;
                    layer.screenNameOffsetYPower = newOffsetY;
                }
                
                this.render();
            }
        }
        
        if (this.spacePressed && !this.isDragging) {
            this.canvas.style.cursor = 'grab';
        } else if (!this.isDragging && !this.isDraggingLayer && !this.isDraggingScreenName && !this.isDraggingCanvas) {
            // Slice 5: hovering a canvas's outline edge → show 'move' so
            // the user knows they can grab it. Skip when a modifier is
            // held (other actions own those gestures).
            if (!e.shiftKey && !e.altKey && !this.isSelectingPanels && !this.isSelectingLayers
                && this._canvasEdgeAtPoint(worldX, worldY)) {
                this.canvas.style.cursor = 'move';
            } else {
                this.canvas.style.cursor = 'default';
            }
        }
    }
    
    handleMouseUp(e) {
        // Slice 5: commit canvas-drag drop. Live updates already happened
        // during mousemove; here we round to integer (avoid sub-pixel
        // drift), persist with a single PUT, and run an overlap check.
        if (this.isDraggingCanvas) {
            this.isDraggingCanvas = false;
            const id = this.draggingCanvasId;
            this.draggingCanvasId = null;
            this.canvas.style.cursor = 'default';
            if (window.app && window.app.project) {
                const c = window.app.project.canvases.find(c => c.id === id);
                if (c) {
                    const wx = Math.round(c.workspace_x || 0);
                    const wy = Math.round(c.workspace_y || 0);
                    c.workspace_x = wx;
                    c.workspace_y = wy;
                    if (typeof window.app.updateCanvas === 'function') {
                        // updateCanvas now snapshots POST-mutation state in
                        // its server-response .then() so a single Cmd+Z reverts
                        // exactly this drag. No skipSaveState needed.
                        window.app.updateCanvas(id, { workspace_x: wx, workspace_y: wy });
                    }
                    if (typeof window.app._checkCanvasOverlapAndToast === 'function') {
                        window.app._checkCanvasOverlapAndToast(id);
                    }
                }
            }
            this.render();
            if (typeof sendClientLog === 'function') {
                sendClientLog('canvas_drag_end', { canvasId: id });
            }
            return;
        }

        if (this.isAltPainting) {
            this.isAltPainting = false;
            if (window.app && this.altPaintedPanelIds && this.altPaintedPanelIds.size > 0) {
                const layer = window.app.project.layers.find(l => l.id === this.altPaintLayerId);
                if (layer) {
                    window.app.saveState('Toggle Panel Visibility');
                    const newHidden = this.altPaintMode === 'hide';
                    const panels = [...this.altPaintedPanelIds].map(id => ({ id, hidden: newHidden }));
                    fetch(`/api/layer/${this.altPaintLayerId}/panels/set_hidden`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ panels })
                    });
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('bulk_toggle_panels', {
                            layerId: this.altPaintLayerId,
                            mode: this.altPaintMode,
                            count: this.altPaintedPanelIds.size
                        });
                    }
                }
            }
            this.altPaintLayerId = null;
            this.altPaintMode = null;
            this.altPaintedPanelIds = null;
            this.render();
            return;
        }

        if (this.isSelectingPanels) {
            this.isSelectingPanels = false;
            if (this.selectionRect && window.app && window.app.currentLayer) {
                const w = Math.abs(this.selectionRect.x2 - this.selectionRect.x1);
                const h = Math.abs(this.selectionRect.y2 - this.selectionRect.y1);
                if (w < 0.5 && h < 0.5) {
                    if (this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                        window.app.powerCustomSelection.clear();
                        window.app.updateCustomPowerUI();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    if (this.viewMode === 'data-flow' && window.app.isCustomFlow(window.app.currentLayer) && window.app.customSelection.size > 0) {
                        window.app.clearCustomSelection();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    const clickedPanel = this.getPanelAt(this.selectionRect.x1, this.selectionRect.y1);
                    if (clickedPanel) {
                        const isPower = this.viewMode === 'power';
                        if (isPower && window.app.isCustomPower(window.app.currentLayer) && clickedPanel.layerId === window.app.currentLayer.id) {
                            if (window.app.powerCustomSelection.size > 0) {
                                window.app.powerCustomSelection.clear();
                                window.app.updateCustomPowerUI();
                            } else {
                                window.app.addPanelToCustomPowerPath(clickedPanel.panel);
                            }
                        } else if (!isPower && window.app.isCustomFlow(window.app.currentLayer) && clickedPanel.layerId === window.app.currentLayer.id) {
                            if (window.app.customSelection.size > 0) {
                                window.app.clearCustomSelection();
                            } else {
                                window.app.addPanelToCustomPath(clickedPanel.panel);
                            }
                        } else if (!window.app.isCustomFlow(window.app.currentLayer) && !window.app.isCustomPower(window.app.currentLayer)) {
                            window.app.togglePanelSelection(clickedPanel.panel);
                        }
                    } else {
                        if (this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                            window.app.powerCustomSelection.clear();
                            window.app.updateCustomPowerUI();
                        }
                        if (this.viewMode === 'data-flow' && window.app.isCustomFlow(window.app.currentLayer) && window.app.customSelection.size > 0) {
                            window.app.clearCustomSelection();
                        }
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                } else {
                    if (this.viewMode === 'power') {
                        window.app.selectPowerPanelsInRect(window.app.currentLayer, this.selectionRect);
                    } else {
                        window.app.selectPanelsInRect(window.app.currentLayer, this.selectionRect);
                    }
                }
            }
            this.selectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('panel_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }

        if (this.isSelectingPixelMapPanels) {
            this.isSelectingPixelMapPanels = false;
            if (this.selectionRect && window.app && window.app.currentLayer) {
                const w = Math.abs(this.selectionRect.x2 - this.selectionRect.x1);
                const h = Math.abs(this.selectionRect.y2 - this.selectionRect.y1);
                if (w < 0.5 && h < 0.5) {
                    // Click without drag.
                    //  - Plain click on a panel: replace the selection with just that panel
                    //    (resets multi-select instead of confusingly toggling one panel out).
                    //  - Cmd/Ctrl+click: additive, toggle that panel in/out of the selection.
                    //  - Plain click on empty space: clear the selection.
                    const clickedPanel = this.getPanelAt(this.selectionRect.x1, this.selectionRect.y1);
                    const additive = e.metaKey || e.ctrlKey;
                    // Allow click-select on hidden panels so they can be
                    // bulk-restored via the sidebar.
                    if (clickedPanel && clickedPanel.layerId === window.app.currentLayer.id) {
                        if (additive) {
                            window.app.togglePixelMapPanelSelection(clickedPanel.panel);
                        } else {
                            window.app.pixelMapSelection.clear();
                            window.app.pixelMapSelection.add(window.app.getPanelKey(clickedPanel.panel));
                            window.app.updatePixelMapBulkActionUI();
                            this.render();
                        }
                    } else if (!additive) {
                        window.app.clearPixelMapSelection();
                    }
                } else {
                    window.app.selectPixelMapPanelsInRect(window.app.currentLayer, this.selectionRect);
                }
            }
            this.selectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('panel_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }
        if (this.isSelectingLayers) {
            this.isSelectingLayers = false;
            if (this.layerSelectionRect && window.app) {
                const w = Math.abs(this.layerSelectionRect.x2 - this.layerSelectionRect.x1);
                const h = Math.abs(this.layerSelectionRect.y2 - this.layerSelectionRect.y1);
                const isToggle = e.metaKey || e.ctrlKey;
                if (w < 0.5 && h < 0.5) {
                    let layer = this.getLayerAt(this.layerSelectionRect.x1, this.layerSelectionRect.y1);
                    if (!layer) {
                        const clickedPanel = this.getPanelAt(this.layerSelectionRect.x1, this.layerSelectionRect.y1);
                        if (clickedPanel) {
                            layer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        }
                    }
                    if (layer) {
                        if (isToggle) {
                            window.app.toggleLayerSelection(layer);
                        } else {
                            window.app.selectLayer(layer);
                        }
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_select_click', { viewMode: this.viewMode, layerId: layer.id, toggle: isToggle });
                        }
                    }
                } else {
                    window.app.selectLayersInRect(this.layerSelectionRect, isToggle);
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('layer_selection_box', { viewMode: this.viewMode, toggle: isToggle });
                    }
                }
            }
            this.layerSelectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('layer_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }
        if (this.layerSelectionRect) {
            this.layerSelectionRect = null;
            this.render();
        }
        if (this.isDragging) {
            this.isDragging = false;
            this.canvas.style.cursor = this.spacePressed ? 'grab' : 'default';
        } else if (this.isDraggingLayer) {
            this.isDraggingLayer = false;
            this._crossCanvasDropTarget = null;

            if (window.app && window.app.currentLayer) {
                const dx = Math.round(this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom) - this.dragLayerStartX);
                const dy = Math.round(((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom - this.dragLayerStartY);
                
                let snapDx = dx;
                let snapDy = dy;
                let newOffsetX = this.layerStartOffset.x + dx;
                let newOffsetY = this.layerStartOffset.y + dy;
                
                // Apply magnetic snapping to final position (only if enabled)
                if (this.magneticSnap) {
                    const snapResult = this.calculateMagneticSnap(newOffsetX, newOffsetY, window.app.currentLayer);
                    snapDx = snapResult.x - this.layerStartOffset.x;
                    snapDy = snapResult.y - this.layerStartOffset.y;
                }
                
                const selected = this.dragLayerOffsets && this.dragLayerOffsets.length > 0
                    ? this.dragLayerOffsets
                    : [{ id: window.app.currentLayer.id, startX: this.layerStartOffset.x, startY: this.layerStartOffset.y }];
                
                const movable = selected.filter(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    return layer && !layer.locked;
                });
                const showMode = this.dragLayerMode === 'show';
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    if (showMode) {
                        layer.showOffsetX = nextX;
                        layer.showOffsetY = nextY;
                    } else {
                        layer.offset_x = nextX;
                        layer.offset_y = nextY;
                        const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                        layer.panels.forEach(panel => {
                            const start = startMap.get(panel.id);
                            if (!start) return;
                            panel.x = start.x + snapDx;
                            panel.y = start.y + snapDy;
                        });
                    }
                });

                // Update Screen Info inputs to reflect current positions (respects mixed values)
                if (window.app.loadLayerToInputs) {
                    window.app.loadLayerToInputs();
                } else {
                    document.getElementById('offset-x').value = window.app.currentLayer.offset_x;
                    document.getElementById('offset-y').value = window.app.currentLayer.offset_y;
                }

                // Slice 7 + multi-select fix: cross-canvas drop check. The
                // hit-test uses the **mouse cursor position** at drop time,
                // not the layer's geometric center, for a wide layer
                // dragged onto a smaller canvas, the cursor lands inside
                // the target rect long before the layer's center does, and
                // the user expects "drop where I'm pointing". (Earlier
                // implementation used layer center and felt unresponsive
                // on big layers.) Layers in OTHER canvases keep their
                // normal within-canvas offset change.
                const primary = window.app.currentLayer;
                const primaryCanvas = window.app.project && Array.isArray(window.app.project.canvases)
                    ? window.app.project.canvases.find(c => c && c.id === primary.canvas_id)
                    : null;
                let crossCanvasHandled = false;
                if (primaryCanvas) {
                    // Mouse cursor world coords at drop (already computed
                    // above for the offset delta).
                    const cursorWX = this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom);
                    const cursorWY = ((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom;
                    const targetCanvas = this._canvasAtPoint(cursorWX, cursorWY);
                    if (targetCanvas && targetCanvas.id !== primary.canvas_id) {
                        const mode = (e.metaKey || e.altKey) ? 'duplicate' : 'move';
                        // Collect all selected layer ids that share the
                        // primary's canvas (so the whole multi-selection
                        // travels together). Primary first so it stays the
                        // currentLayer in the target.
                        const movedIds = [primary.id];
                        if (window.app.selectedLayerIds && window.app.selectedLayerIds.size > 1) {
                            window.app.selectedLayerIds.forEach(id => {
                                if (id === primary.id) return;
                                const l = window.app.project.layers.find(x => x.id === id);
                                if (l && l.canvas_id === primary.canvas_id && !l.locked) {
                                    movedIds.push(id);
                                }
                            });
                        }
                        // Cross-canvas helpers now snapshot post-action state
                        // themselves (in their .then() after the server
                        // round-trip), so we don't pass skipSaveState anymore.
                        if (movedIds.length > 1 && typeof window.app.moveLayersCrossCanvas === 'function') {
                            window.app.moveLayersCrossCanvas(movedIds, targetCanvas.id, mode);
                            crossCanvasHandled = true;
                        } else if (typeof window.app.moveLayerCrossCanvas === 'function') {
                            window.app.moveLayerCrossCanvas(primary.id, targetCanvas.id, mode);
                            crossCanvasHandled = true;
                        }
                    }
                }

                if (!crossCanvasHandled) {
                    // Snapshot POST-drag state so one Cmd+Z reverts this drag.
                    if (typeof window.app.saveState === 'function') {
                        window.app.saveState(this.dragLayerMode === 'show' ? 'Move Layers (Show Look)' : 'Move Layers');
                    }
                    const toUpdate = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    window.app.updateLayers(toUpdate, false);
                }
                this.dragLayerMode = null;
            }
        } else if (this.isDraggingScreenName) {
            this.isDraggingScreenName = false;
            // Persist and snapshot ONLY if the label actually moved
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                let currentOffsetX = 0;
                let currentOffsetY = 0;

                if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                }

                const moved = currentOffsetX !== this.screenNameStartOffset.x || currentOffsetY !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Screen Name');
                }
                window.app.saveClientSideProperties();
            }
            this.render();
        }
    }
    
    handleWheel(e) {
        e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // If horizontal scroll dominates (trackpad swipe), pan instead of zoom
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 1) {
            this.panX -= e.deltaX;
            this.panY -= e.deltaY;
            this.render();
            return;
        }

        // Ignore tiny deltaY to avoid accidental zoom during horizontal swipes
        if (Math.abs(e.deltaY) < 1) return;

        // Further reduced sensitivity: 1.025 instead of 1.05 (50% less again)
        const zoomFactor = e.deltaY < 0 ? 1.025 : 0.975;
        const newZoom = Math.max(0.01, Math.min(500.0, this.zoom * zoomFactor));  // Max 50000% for pixel-level zoom
        const worldX = (mouseX - this.panX) / this.zoom;
        const worldY = (mouseY - this.panY) / this.zoom;
        this.zoom = newZoom;
        this.panX = mouseX - worldX * this.zoom;
        this.panY = mouseY - worldY * this.zoom;
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }

    handleContextMenu(e) {
        e.preventDefault();
        e.stopPropagation();
        if (!window.app) return;
        // In Pixel Map view: if right-click lands on a panel of currentLayer
        // and the panel is not already in the selection, treat it as a
        // single-panel selection so the menu actions target it.
        if (this.viewMode === 'pixel-map' && window.app.currentLayer) {
            const rect = this.canvas.getBoundingClientRect();
            const worldX = this._unmirrorWorldX(((e.clientX - rect.left) - this.panX) / this.zoom);
            const worldY = ((e.clientY - rect.top) - this.panY) / this.zoom;
            const clicked = this.getPanelAt(worldX, worldY);
            // Right-click works on hidden panels too, the menu shows
            // "Restore From Blank" so they can be brought back.
            if (clicked && clicked.layerId === window.app.currentLayer.id) {
                const key = window.app.getPanelKey(clicked.panel);
                if (!window.app.pixelMapSelection.has(key)) {
                    window.app.pixelMapSelection.clear();
                    window.app.pixelMapSelection.add(key);
                    window.app.updatePixelMapBulkActionUI();
                    this.render();
                }
            }
        }
        window.app.showContextMenu(e.clientX, e.clientY);
    }
    
    handleKeyDown(e) {
        // Check if user is typing in an input or textarea
        const isTyping = document.activeElement.tagName === 'INPUT' || 
                        document.activeElement.tagName === 'TEXTAREA' ||
                        document.activeElement.isContentEditable;

        if (!isTyping && window.app && window.app.handleCustomArrowKey(e)) {
            e.preventDefault();
            return;
        }
        
        // Space - only prevent default and pan if NOT typing
        if (e.code === 'Space' && !isTyping) {
            e.preventDefault();
            this.spacePressed = true;
            if (!this.isDragging) this.canvas.style.cursor = 'grab';
        }
        
        // Delete key - only delete layer if NOT typing
        if ((e.code === 'Delete' || e.code === 'Backspace') && !isTyping) {
            if (window.app && window.app.currentLayer) {
                e.preventDefault();
                window.app.deleteCurrentLayer();
            }
        }
        
        // Cmd/Ctrl+Z - Undo (works everywhere)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && !e.shiftKey) {
            if (e.repeat) return;
            e.preventDefault();
            if (window.app) window.app.undo();
        }
        
        // Cmd/Ctrl+Shift+Z - Redo (works everywhere)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && e.shiftKey) {
            if (e.repeat) return;
            e.preventDefault();
            if (window.app) window.app.redo();
        }
        
        // Cmd/Ctrl+C - Copy (only if NOT typing in a text field)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyC' && !isTyping) {
            e.preventDefault();
            if (window.app) window.app.copyLayer();
        }
        
        // Cmd/Ctrl+V - Paste (only if NOT typing in a text field)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyV' && !isTyping) {
            e.preventDefault();
            if (window.app) window.app.pasteLayer();
        }
        
        // Cmd/Ctrl+J - Duplicate (Photoshop standard)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyJ' && !isTyping) {
            e.preventDefault();
            if (window.app && window.app.currentLayer) {
                window.app.duplicateLayer(window.app.currentLayer);
            }
        }

        // Cmd/Ctrl+, - Preferences
        if ((e.metaKey || e.ctrlKey) && e.code === 'Comma' && !isTyping) {
            e.preventDefault();
            if (window.app) {
                window.app.openPreferencesModal();
            }
        }

        // Tab - Next port (custom flow/power, only when custom mode active)
        if (e.code === 'Tab' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !isTyping) {
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomFlowState(layer);
                window.app.saveState('Custom Port Change');
                layer.customPortIndex = (layer.customPortIndex || 1) + 1;
                window.app.updateCustomFlowUI();
                window.app.updatePortLabelEditor();
                this.render();
            } else if (window.app && window.app.currentLayer && window.app.isCustomPower(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomPowerState(layer);
                window.app.saveState('Power Custom Circuit Change');
                layer.powerCustomIndex = (layer.powerCustomIndex || 1) + 1;
                window.app.updateCustomPowerUI();
                this.render();
            }
        }

        // Shift+Tab - Previous port (custom flow/power, only when custom mode active)
        if (e.code === 'Tab' && e.shiftKey && !e.metaKey && !e.ctrlKey && !isTyping) {
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomFlowState(layer);
                window.app.saveState('Custom Port Change');
                layer.customPortIndex = Math.max(1, (layer.customPortIndex || 1) - 1);
                window.app.updateCustomFlowUI();
                window.app.updatePortLabelEditor();
                this.render();
            } else if (window.app && window.app.currentLayer && window.app.isCustomPower(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomPowerState(layer);
                window.app.saveState('Power Custom Circuit Change');
                layer.powerCustomIndex = Math.max(1, (layer.powerCustomIndex || 1) - 1);
                window.app.updateCustomPowerUI();
                this.render();
            }
        }

        // Custom flow port shortcuts: [ prev, ] next
        if (!isTyping && this.viewMode === 'data-flow' && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlow(layer)) {
                if (e.code === 'BracketLeft') {
                    e.preventDefault();
                    window.app.ensureCustomFlowState(layer);
                    window.app.saveState('Custom Port Change');
                    layer.customPortIndex = Math.max(1, (layer.customPortIndex || 1) - 1);
                    window.app.updateCustomFlowUI();
                    window.app.updatePortLabelEditor();
                    this.render();
                } else if (e.code === 'BracketRight') {
                    e.preventDefault();
                    window.app.ensureCustomFlowState(layer);
                    window.app.saveState('Custom Port Change');
                    layer.customPortIndex = (layer.customPortIndex || 1) + 1;
                    window.app.updateCustomFlowUI();
                    window.app.updatePortLabelEditor();
                    this.render();
                }
            }
        }
        if (!isTyping && this.viewMode === 'power' && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            if (window.app.isCustomPower(layer)) {
                if (e.code === 'BracketLeft') {
                    e.preventDefault();
                    window.app.ensureCustomPowerState(layer);
                    window.app.saveState('Power Custom Circuit Change');
                    layer.powerCustomIndex = Math.max(1, (layer.powerCustomIndex || 1) - 1);
                    window.app.updateCustomPowerUI();
                    this.render();
                } else if (e.code === 'BracketRight') {
                    e.preventDefault();
                    window.app.ensureCustomPowerState(layer);
                    window.app.saveState('Power Custom Circuit Change');
                    layer.powerCustomIndex = (layer.powerCustomIndex || 1) + 1;
                    window.app.updateCustomPowerUI();
                    this.render();
                }
            }
        }

        // Cmd/Ctrl+Shift+1 - Fit to view
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Digit1' && !isTyping) {
            e.preventDefault();
            this.fitToView();
        }

        // Cmd/Ctrl+Shift+2 - Zoom to selection (actual size 1:1)
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Digit2' && !isTyping) {
            e.preventDefault();
            this.zoomActual();
        }

        // Cmd/Ctrl+Shift+' - Toggle snap (Photoshop standard: Snap to Grid)
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Quote' && !isTyping) {
            e.preventDefault();
            this.magneticSnap = !this.magneticSnap;
            const snapCheckbox = document.getElementById('magnetic-snap');
            if (snapCheckbox) snapCheckbox.checked = this.magneticSnap;
        }
    }

    handleKeyUp(e) {
        if (e.code === 'Space') {
            this.spacePressed = false;
            if (!this.isDragging) this.canvas.style.cursor = 'default';
        }
    }
    
    /**
     * v0.8 multi-canvas: return the workspace translate ({wx, wy}) for the
     * canvas a layer belongs to. Layers without a canvas_id (legacy / orphan)
     * and projects with no canvases array fall back to (0, 0) so single-canvas
     * behaviour is unchanged.
     */
    _layerCanvasOffset(layer) {
        if (!layer || !window.app || !window.app.project) return { wx: 0, wy: 0 };
        const arr = window.app.project.canvases;
        if (!Array.isArray(arr) || arr.length === 0) return { wx: 0, wy: 0 };
        const cid = layer.canvas_id;
        if (!cid) return { wx: 0, wy: 0 };
        for (const c of arr) {
            if (c && c.id === cid) {
                return { wx: c.workspace_x || 0, wy: c.workspace_y || 0 };
            }
        }
        return { wx: 0, wy: 0 };
    }

    getPanelAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            if ((layer.type || 'screen') === 'image') continue;
            // Convert world coords back into the layer's processor space so we
            // can hit-test against panel.x/y (which are stored at processor
            // position; show-look renders with a translate AND, for v0.8
            // multi-canvas, the per-layer render is wrapped in the parent
            // canvas's workspace translate). Subtract both.
            const { dx, dy } = this.getLayerRenderOffset(layer);
            const { wx, wy } = this._layerCanvasOffset(layer);
            const lx = worldX - dx - wx;
            const ly = worldY - dy - wy;
            for (const panel of layer.panels) {
                // Don't skip hidden panels - they need to be clickable to toggle back
                if (lx >= panel.x && lx <= panel.x + panel.width &&
                    ly >= panel.y && ly <= panel.y + panel.height) {
                    return { panel, layerId: layer.id };
                }
            }
        }
        return null;
    }

    getLayerAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            // Hit-test against the layer's bounds in the *active view*, since
            // worldX/worldY are in the view's coord space (Show Look / Data /
            // Power render at the show position). v0.8: bounds returned by
            // getLayerBoundsInActiveView are in the canvas's local coord
            // space; shift by the canvas's workspace_x/y so the comparison
            // against worldX/worldY (which are in workspace coords) is right
            // for canvases beyond the first.
            const bounds = this.getLayerBoundsInActiveView(layer);
            const { wx, wy } = this._layerCanvasOffset(layer);
            const bx = bounds.x + wx;
            const by = bounds.y + wy;
            if (worldX >= bx && worldX <= bx + bounds.width &&
                worldY >= by && worldY <= by + bounds.height) {
                return layer;
            }
        }
        return null;
    }

    renderImageLayer(layer) {
        if (!layer || !layer.imageData) return;
        if (!layer._imageObj || layer._imageObj.src !== layer.imageData) {
            const img = new Image();
            img.onload = () => {
                if (layer._imageObj !== img) return;
                this.render();
            };
            img.src = layer.imageData;
            layer._imageObj = img;
        }
        const img = layer._imageObj;
        if (!img || !img.complete) return;
        const scale = Number(layer.imageScale) || 1;
        const w = (Number(layer.imageWidth) || img.width) * scale;
        const h = (Number(layer.imageHeight) || img.height) * scale;
        const x = Number(layer.offset_x) || 0;
        const y = Number(layer.offset_y) || 0;
        const prevSmoothing = this.ctx.imageSmoothingEnabled;
        this.ctx.imageSmoothingEnabled = true;
        this.ctx.drawImage(img, x, y, w, h);
        this.ctx.imageSmoothingEnabled = prevSmoothing;
    }
    
    renderTextLayer(layer) {
        if (!layer) return;
        // Check per-tab visibility
        const viewMode = this.viewMode || 'pixel-map';
        if (viewMode === 'pixel-map' && !layer.showOnPixelMap) return;
        if (viewMode === 'cabinet-id' && !layer.showOnCabinetId) return;
        if (viewMode === 'data-flow' && !layer.showOnDataFlow) return;
        if (viewMode === 'power' && !layer.showOnPower) return;

        const x = Number(layer.offset_x) || 0;
        const y = Number(layer.offset_y) || 0;
        const w = Number(layer.textWidth) || 400;
        const h = Number(layer.textHeight) || 100;
        const padding = Number(layer.textPadding) || 12;
        const fontSize = Number(layer.fontSize) || 24;
        const fontFamily = layer.fontFamily || 'Arial';
        const fontColor = layer.fontColor || '#ffffff';
        const bgColor = layer.bgColor || '#000000';
        const bgOpacity = layer.bgOpacity != null ? Number(layer.bgOpacity) : 0.7;
        const textAlign = layer.textAlign || 'left';

        // Background
        this.ctx.save();
        this.ctx.globalAlpha = bgOpacity;
        this.ctx.fillStyle = bgColor;
        this.ctx.fillRect(x, y, w, h);
        this.ctx.globalAlpha = 1.0;

        // Border
        if (layer.showBorder) {
            this.ctx.strokeStyle = layer.borderColor || '#555555';
            this.ctx.lineWidth = 1;
            this.ctx.strokeRect(x, y, w, h);
        }

        // Per-tab text content
        let text = '';
        if (viewMode === 'pixel-map') text = layer.textContentPixelMap || layer.textContent || '';
        else if (viewMode === 'cabinet-id') text = layer.textContentCabinetId || layer.textContent || '';
        else if (viewMode === 'data-flow') text = layer.textContentDataFlow || layer.textContent || '';
        else if (viewMode === 'power') text = layer.textContentPower || layer.textContent || '';
        else text = layer.textContent || '';

        // Append dynamic info lines
        const dynamicLines = [];
        if (layer.showRasterSize && window.canvasRenderer) {
            const rw = window.canvasRenderer.rasterWidth || 1920;
            const rh = window.canvasRenderer.rasterHeight || 1080;
            dynamicLines.push(`Raster: ${rw} × ${rh}`);
        }
        if (layer.showProjectName && window.app && window.app.project) {
            dynamicLines.push(window.app.project.name || 'Untitled Project');
        }
        if (layer.showDate) {
            dynamicLines.push(new Date().toLocaleDateString());
        }
        // v0.8 Slice 10: dynamic data/power stats now honor a per-layer
        // scope: 'canvas' (text layer's parent canvas), 'project' (all
        // canvases, original behaviour, default), or 'both' (renders one
        // line for the canvas, then one for the project total).
        const scope = layer.dynamicInfoScope || 'project';
        const wantsData = layer.showPrimaryPorts || layer.showBackupPorts;
        const wantsPower = layer.showCircuits || layer.showSinglePhase || layer.showThreePhase;
        if ((wantsData || wantsPower) && window.app) {
            // Resolve the canvas this text layer sits on. For "canvas" /
            // "both" scopes we need to pass canvas_id into the aggregators.
            const ownCanvasId = layer.canvas_id || null;
            const ownCanvas = (ownCanvasId && window.app._activeCanvas)
                ? (window.app.project && window.app.project.canvases || []).find(c => c && c.id === ownCanvasId)
                : null;
            const canvasLabel = ownCanvas ? (ownCanvas.name || 'Canvas') : 'Canvas';
            const passes = []; // [{ key: 'canvas'|'project', label: '... (X)' or '... (Total)' }]
            if (scope === 'canvas') passes.push({ key: 'canvas', suffix: ` (${canvasLabel})` });
            else if (scope === 'project') passes.push({ key: 'project', suffix: '' });
            else { // 'both'
                passes.push({ key: 'canvas', suffix: ` (${canvasLabel})` });
                passes.push({ key: 'project', suffix: ' (Total)' });
            }
            passes.forEach(pass => {
                const filter = pass.key === 'canvas' ? ownCanvasId : undefined;
                if (wantsData) {
                    const counts = window.app.getPortCounts(filter);
                    if (layer.showPrimaryPorts && counts.primary > 0) {
                        dynamicLines.push(`Primary Ports${pass.suffix}: ${counts.primary}`);
                    }
                    if (layer.showBackupPorts && counts.backup > 0) {
                        dynamicLines.push(`Backup Ports${pass.suffix}: ${counts.backup}`);
                    }
                }
                if (wantsPower) {
                    const pwr = window.app.getPowerCounts(filter);
                    if (layer.showCircuits && pwr.circuits > 0) {
                        dynamicLines.push(`Circuits${pass.suffix}: ${pwr.circuits} @ ${pwr.voltage}V`);
                    }
                    if (layer.showSinglePhase && pwr.circuits > 0) {
                        dynamicLines.push(`1-Phase${pass.suffix}: ${pwr.singlePhaseAmps.toFixed(2)}A`);
                    }
                    if (layer.showThreePhase && pwr.circuits >= 3) {
                        dynamicLines.push(`3-Phase${pass.suffix}: ${pwr.threePhaseAmps.toFixed(2)}A`);
                    }
                }
            });
        }
        if (dynamicLines.length > 0) {
            text = text ? `${text}\n${dynamicLines.join('\n')}` : dynamicLines.join('\n');
        }

        if (text) {
            // Clip text rendering to the text-layer's own box so overlong
            // content can't spill onto neighboring canvases or out of the
            // layer's raster footprint. The clip is scoped to a separate
            // save() so the background + border (already drawn above) are
            // unaffected.
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(x, y, w, h);
            this.ctx.clip();

            this.ctx.fillStyle = fontColor;
            // Build font string with bold/italic
            let fontStyle = '';
            if (layer.fontItalic) fontStyle += 'italic ';
            if (layer.fontBold) fontStyle += 'bold ';
            this.ctx.font = `${fontStyle}${fontSize}px ${fontFamily}`;
            this.ctx.textBaseline = 'top';
            this.ctx.textAlign = textAlign;

            const lines = text.split('\n');
            const lineHeight = fontSize * 1.3;
            let textX = x + padding;
            if (textAlign === 'center') textX = x + w / 2;
            else if (textAlign === 'right') textX = x + w - padding;

            lines.forEach((line, i) => {
                const ty = y + padding + i * lineHeight;
                // Cheap vertical-overflow short-circuit so we don't measure +
                // fillText for lines fully below the box (clip would suppress
                // them anyway, but skipping saves work on big text dumps).
                if (ty > y + h) return;
                this._fillText(line, textX, ty);
                if (layer.fontUnderline && line.length > 0) {
                    const metrics = this.ctx.measureText(line);
                    let ulX = textX;
                    if (textAlign === 'center') ulX = textX - metrics.width / 2;
                    else if (textAlign === 'right') ulX = textX - metrics.width;
                    const ulY = ty + fontSize + 2;
                    this.ctx.beginPath();
                    this.ctx.strokeStyle = fontColor;
                    this.ctx.lineWidth = Math.max(1, fontSize / 15);
                    this.ctx.moveTo(ulX, ulY);
                    this.ctx.lineTo(ulX + metrics.width, ulY);
                    this.ctx.stroke();
                }
            });
            this.ctx.restore();
        }

        this.ctx.restore();
    }

    render() {
        if (this.layerSelectionRect && !this.isSelectingLayers && !this.isSelectingPanels && !this.isDraggingLayer) {
            this.layerSelectionRect = null;
        }
        // In export mode with transparent bg, clear to transparent; otherwise fill
        if (this.exportMode && this.exportTransparentBg) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        } else {
            this.ctx.fillStyle = this.exportMode ? '#000000' : '#0a0a0a';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        }
        
        // Skip grid in export mode
        if (this.showGrid && !this.exportMode) {
            this.ctx.strokeStyle = '#1a1a1a';
            this.ctx.lineWidth = 1;
            const gridSpacing = 50 * this.zoom;
            const offsetX = this.panX % gridSpacing;
            const offsetY = this.panY % gridSpacing;
            for (let x = offsetX; x < this.canvas.width; x += gridSpacing) {
                this.ctx.beginPath();
                this.ctx.moveTo(x, 0);
                this.ctx.lineTo(x, this.canvas.height);
                this.ctx.stroke();
            }
            for (let y = offsetY; y < this.canvas.height; y += gridSpacing) {
                this.ctx.beginPath();
                this.ctx.moveTo(0, y);
                this.ctx.lineTo(this.canvas.width, y);
                this.ctx.stroke();
            }
        }
        
        this.ctx.save();
        // Round pan values to prevent sub-pixel anti-aliasing seams between panels
        this.ctx.setTransform(this.zoom, 0, 0, this.zoom, Math.round(this.panX), Math.round(this.panY));

        // Wiring view perspective: in 'back' view, mirror the entire
        // geometry around the right edge of the raster so techs working
        // behind the wall see things from their perspective. _fillText /
        // _strokeText un-mirror text glyphs so labels stay readable. The
        // _mirror flag drives both the canvas transform and the text
        // helpers below.
        this._mirror = this.isMirroredView();
        if (this._mirror) {
            // v0.8 Slice 8: mirror axis is the workspace bounding-box right
            // edge so multi-canvas workspaces stay on-screen when flipped.
            // Single-canvas legacy projects naturally land at this.rasterWidth
            // because their bbox is (0, 0, rasterWidth, rasterHeight).
            this.ctx.translate(this._mirrorAxisX(), 0);
            this.ctx.scale(-1, 1);
        }

        // Disable image smoothing to prevent anti-aliasing artifacts (seams between panels)
        this.ctx.imageSmoothingEnabled = false;
        
        // Multi-canvas (v0.8 Slice 3): build a lookup so per-layer post-passes
        // (selection overlays, error badges, pixel grid) can translate to
        // the layer's own canvas's workspace position. For pre-v0.8 projects
        // that haven't been migrated yet, fall back to a synthetic canvas at
        // (0, 0) so single-canvas behaviour is unchanged.
        const _canvasesArr = (window.app && window.app.project && Array.isArray(window.app.project.canvases))
            ? window.app.project.canvases
            : [];
        const _canvasById = {};
        _canvasesArr.forEach(c => { if (c && c.id) _canvasById[c.id] = c; });
        const _activeCanvasId = (window.app && window.app.project)
            ? window.app.project.active_canvas_id : null;
        // Helper: returns the workspace translate for a layer (or 0,0 for
        // legacy / orphan layers). Used by the post-pass wrappers below.
        const _layerWs = (layer) => {
            const cid = layer && layer.canvas_id;
            const c = cid ? _canvasById[cid] : null;
            return { wx: (c && c.workspace_x) || 0, wy: (c && c.workspace_y) || 0 };
        };
        // Helper: returns true if this layer's canvas is hidden (canvas-level
        // eye toggle off). Used to skip every per-layer post-pass for hidden
        // canvases, without this, hiding a canvas removed only its outline
        // while its layers continued to render at the canvas's workspace
        // offset.
        const _layerCanvasHidden = (layer) => {
            const cid = layer && layer.canvas_id;
            const c = cid ? _canvasById[cid] : null;
            return c && c.visible === false;
        };
        // Helper: wraps a per-layer drawing callback with the layer's
        // canvas-workspace translate. Skips entirely if the layer's canvas
        // is hidden. Applies translate only when wx/wy are non-zero so
        // single-canvas projects emit no extra ctx ops.
        const _withLayerWs = (layer, fn) => {
            if (_layerCanvasHidden(layer)) return;
            const { wx, wy } = _layerWs(layer);
            if (wx || wy) {
                this.ctx.save();
                this.ctx.translate(wx, wy);
                fn();
                this.ctx.restore();
            } else {
                fn();
            }
        };

        if (window.app && window.app.project && window.app.project.layers) {
            // Per-canvas loop (Slice 3): translate to each canvas's
            // workspace position, render that canvas's layers (existing
            // per-layer body, unmodified), then draw the canvas's dashed
            // outline ON TOP. Empty + hidden canvases are skipped.
            // Pre-Slice-1 projects with no `canvases` array fall back to a
            // synthetic single canvas using project root raster fields so
            // legacy single-canvas behaviour is identical to v0.7.7.4.
            const canvasesToRender = (_canvasesArr.length > 0)
                ? _canvasesArr
                : [{
                    id: null,
                    workspace_x: 0,
                    workspace_y: 0,
                    raster_width: this.rasterWidth,
                    raster_height: this.rasterHeight,
                    color: '#ff0000',
                    visible: true,
                }];
            canvasesToRender.forEach(canvas => {
                if (canvas.visible === false) return;
                const layersInCanvas = window.app.project.layers.filter(l => {
                    if (!l.visible) return false;
                    if (_canvasesArr.length === 0) return true; // legacy fallback
                    return l.canvas_id === canvas.id;
                });
                // Empty canvases (no layers) still get drawn, outline +
                // active tint, so the user can see the canvas exists and can
                // drag layers into it. Slice 7 cross-canvas drag depends on
                // this being a valid drop target. Originally Slice 3 skipped
                // empty canvases entirely, but that hid them from the
                // workspace which broke the drop-into-empty-canvas flow.
                const wx = canvas.workspace_x || 0;
                const wy = canvas.workspace_y || 0;
                const needsCanvasShift = (wx !== 0 || wy !== 0);
                if (needsCanvasShift) {
                    this.ctx.save();
                    this.ctx.translate(wx, wy);
                }
                // Slice 6: scope rasterWidth/Height (via the getter) to THIS
                // canvas during its render pass so per-panel clipping uses
                // this canvas's raster, not the active canvas's. Cleared at
                // the end of the pass.
                this._activeRenderCanvas = canvas.id ? canvas : null;
                // Active-canvas tint (BEFORE layers so layers paint over it
                // but the tint shows through in empty regions).
                if (!this.exportMode && canvas.id && canvas.id === _activeCanvasId) {
                    this._drawActiveCanvasTint(canvas);
                }
                // First pass: render all panels and mode-specific content (except labels)
                layersInCanvas.forEach(layer => {
                if (layer.visible) {
                    if (this.viewMode === 'power') {
                        this.preparePowerLayerRenderData(layer);
                    }
                    // Show Look / Data / Power render at the layer's show
                    // position rather than its processor position. We apply
                    // that as a per-layer ctx translate so all the existing
                    // panel.x/y math stays in processor coords.
                    const { dx, dy } = this.getLayerRenderOffset(layer);
                    const needsShift = dx !== 0 || dy !== 0;
                    if (needsShift) {
                        this.ctx.save();
                        this.ctx.translate(dx, dy);
                    }
                    if ((layer.type || 'screen') === 'image') {
                        this.renderImageLayer(layer);
                        if (needsShift) this.ctx.restore();
                        return;
                    }
                    if ((layer.type || 'screen') === 'text') {
                        this.renderTextLayer(layer);
                        if (needsShift) this.ctx.restore();
                        return;
                    }
                    // Note: We don't fill the layer background anymore
                    // Each panel fills its own area, and hidden panels show as outlines
                    // This allows hidden panels to be transparent instead of black

                    // Stash the per-layer render offset so renderPanel() can
                    // clip against raster bounds *in this layer's translated
                    // space*. Without this, the per-panel clip in renderPanel
                    // uses raw panel.x vs rasterWidth and silently drops
                    // panels that sit beyond rasterWidth in processor coords
                    // even when the show-offset places them inside the
                    // visible raster, caused panels to "vanish" in Show
                    // Look after a temporary raster shrink.
                    this._renderDx = dx;
                    this._renderDy = dy;
                    layer.panels.forEach(panel => {
                        // Cheap early skip for panels entirely outside the
                        // raster on the right or bottom in render space.
                        if (panel.x + dx >= this.rasterWidth || panel.y + dy >= this.rasterHeight) return;

                        // Render all panels - visible and hidden (hidden as ghost outlines)
                        this.renderPanel(panel, layer);
                    });

                    // Render Circle with X test pattern
                    if (layer.show_circle_with_x && this.viewMode === 'pixel-map' && (layer.type || 'screen') !== 'image') {
                        this.renderCircleWithX(layer);
                    }

                    // Render offsets (pixel-map only)
                    this.renderLayerOffsets(layer);

                    // Render Cabinet ID numbers in world space (scales with zoom)
                    if (this.viewMode === 'cabinet-id') {
                        this.renderCabinetIDNumbers(layer);
                    }

                    // Render Data Flow arrows (serpentine path with P1/R1 labels)
                    if (this.viewMode === 'data-flow') {
                        this.renderDataFlowArrows(layer);
                    }
                    if (this.viewMode === 'power') {
                        this.renderPowerArrows(layer);
                    }

                    // Render labels as part of each layer so upper layers naturally
                    // paint over lower layers' labels (no bleed-through)
                    this.renderLayerLabels(layer);
                    if (needsShift) this.ctx.restore();
                }
                });
                // Canvas outline drawn LAST so it sits on top of any
                // layer content that bleeds outside the raster bounds.
                if (!this.exportMode) {
                    this._drawCanvasOutline(canvas, canvas.id === _activeCanvasId);
                }
                if (needsCanvasShift) this.ctx.restore();
            });
            // Per-layer translates have been restored, clear the cached
            // render offset so any later renderers (selection overlays,
            // error badges) that happen to call _clipToActiveRaster get
            // raster bounds in real screen space, not in the last layer's
            // translated space.
            this._renderDx = 0;
            this._renderDy = 0;
            // Slice 6: clear the per-canvas raster scope so any post-pass
            // (overlays, badges, hit-testing during this render) sees the
            // active canvas's raster via the getter again.
            this._activeRenderCanvas = null;

            if (!this.exportMode && this.viewMode === 'data-flow') {
                this.renderCustomSelectionOverlay();
                this.renderCustomActivePortBadge();
            }
            if (!this.exportMode && this.viewMode === 'power') {
                this.renderPowerSelectionOverlay();
                this.renderPowerActiveCircuitBadge();
            }
            if (!this.exportMode && this.viewMode === 'pixel-map') {
                this.renderPixelMapSelectionOverlay();
                this.renderPixelMapSelectionBadge();
            }
            // Always show the perspective badge (BACK VIEW) in wiring views
            // when in back perspective. Renders in both interactive view and
            // export so the printed map is unambiguous.
            if (this.viewMode === 'data-flow' || this.viewMode === 'power') {
                this.renderPerspectiveBadge();
            }
            
            // Third pass: render capacity error overlays ON TOP of labels (Data Flow mode only)
            if (this.viewMode === 'data-flow') {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        _withLayerWs(layer, () => this.renderCapacityErrorOverlay(layer));
                    }
                });
            }
            if (this.viewMode === 'power') {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        _withLayerWs(layer, () => this.renderPowerErrorOverlay(layer));
                    }
                });
            }

            // Draw bounding boxes around selected layers (skip during export)
            // These render OUTSIDE the per-layer ctx.translate, so use the
            // active-view bounds.
            if (!this.exportMode && window.app && window.app.selectedLayerIds && window.app.selectedLayerIds.size > 0) {
                const selectedIds = window.app.selectedLayerIds;
                window.app.project.layers.forEach(layer => {
                    if (!layer.visible) return;
                    if (!selectedIds.has(layer.id)) return;
                    _withLayerWs(layer, () => {
                        const bounds = this.getLayerBoundsInActiveView(layer);
                        const layerWidth = bounds.width;
                        const layerHeight = bounds.height;
                        this.ctx.strokeStyle = (window.app.currentLayer && window.app.currentLayer.id === layer.id) ? '#00ccff' : '#4A90E2';
                        this.ctx.lineWidth = 2 / this.zoom;
                        this.ctx.setLineDash([8 / this.zoom, 4 / this.zoom]);
                        this.ctx.strokeRect(bounds.x, bounds.y, layerWidth, layerHeight);
                        this.ctx.setLineDash([]);
                    });
                });
            }

            // Draw bounding box around selected layer ONLY during Shift+Drag (skip during export)
            if (!this.exportMode && this.isDraggingLayer && window.app && window.app.currentLayer) {
                const selectedLayer = window.app.currentLayer;
                if (selectedLayer.visible) {
                    _withLayerWs(selectedLayer, () => {
                        const bounds = this.getLayerBoundsInActiveView(selectedLayer);
                        const layerWidth = bounds.width;
                        const layerHeight = bounds.height;

                        this.ctx.strokeStyle = '#4A90E2';  // Blue highlight color
                        this.ctx.lineWidth = 3 / this.zoom;  // Scale with zoom
                        this.ctx.setLineDash([10 / this.zoom, 5 / this.zoom]);
                        this.ctx.strokeRect(
                            bounds.x,
                            bounds.y,
                            layerWidth,
                            layerHeight
                        );
                        this.ctx.setLineDash([]);
                    });
                }
            }

            // Draw selection rectangle + highlight for layer multi-select (skip during export)
            if (!this.exportMode && this.isSelectingLayers && this.layerSelectionRect) {
                const minX = Math.min(this.layerSelectionRect.x1, this.layerSelectionRect.x2);
                const maxX = Math.max(this.layerSelectionRect.x1, this.layerSelectionRect.x2);
                const minY = Math.min(this.layerSelectionRect.y1, this.layerSelectionRect.y2);
                const maxY = Math.max(this.layerSelectionRect.y1, this.layerSelectionRect.y2);

                this.ctx.save();
                // Darken selected layers while dragging
                if (window.app && window.app.project) {
                    window.app.project.layers.forEach(layer => {
                        if (!layer.visible) return;
                        // Active-view bounds, selection rect is in world coords
                        // matching the rendered (possibly show-shifted) layout.
                        // For multi-canvas, shift bounds into workspace coords
                        // so the intersection test compares apples-to-apples
                        // with the selection rect (which is in workspace coords
                        //, captured from world-space mouse events).
                        const { wx, wy } = _layerWs(layer);
                        const bounds = this.getLayerBoundsInActiveView(layer);
                        const layerWidth = bounds.width;
                        const layerHeight = bounds.height;
                        const x1 = bounds.x + wx;
                        const y1 = bounds.y + wy;
                        const x2 = x1 + layerWidth;
                        const y2 = y1 + layerHeight;
                        const intersects = x1 <= maxX && x2 >= minX && y1 <= maxY && y2 >= minY;
                        if (intersects) {
                            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
                            this.ctx.fillRect(x1, y1, layerWidth, layerHeight);
                        }
                    });
                }

                this.ctx.strokeStyle = '#4A90E2';
                this.ctx.lineWidth = 2 / this.zoom;
                this.ctx.setLineDash([6 / this.zoom, 4 / this.zoom]);
                this.ctx.strokeRect(minX, minY, maxX - minX, maxY - minY);
                this.ctx.setLineDash([]);
                this.ctx.restore();
            }
            
            // Final pass: render pixel grid ON TOP of everything (all view modes, 1000%+ zoom)
            if (this.zoom >= 10) {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        _withLayerWs(layer, () => this.renderPixelGrid(layer));
                    }
                });
            }
        }
        
        this.ctx.restore();
    }
    
    renderCircleWithX(layer) {
        // Calculate layer dimensions
        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        
        // Circle radius is about 40% of the smaller dimension (based on Pixel Perfect Pro reference)
        const radius = Math.min(layerWidth, layerHeight) * 0.40;
        
        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'pixel-map');
        this.ctx.lineWidth = 2;
        
        // Draw perfect circle
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.stroke();
        
        // Draw X from corner to corner of entire layer
        this.ctx.beginPath();
        // Top-left to bottom-right
        this.ctx.moveTo(bounds.x, bounds.y);
        this.ctx.lineTo(bounds.x + layerWidth, bounds.y + layerHeight);
        // Top-right to bottom-left
        this.ctx.moveTo(bounds.x + layerWidth, bounds.y);
        this.ctx.lineTo(bounds.x, bounds.y + layerHeight);
        this.ctx.stroke();
        
        // Restore context (remove clipping)
        this.ctx.restore();
    }
    
    // The displayed zoom percentage is 1 raster-pixel-to-1-device-pixel based,
    // so "100%" truly means actual size. Internally `this.zoom` still maps
    // raster pixels to CSS pixels; on a Retina display devicePixelRatio is 2,
    // so 100% displayed == this.zoom == 0.5 (1 raster px → 0.5 CSS px → 1
    // device px). This keeps render math unchanged and only adjusts the I/O
    // boundary with the zoom-level input.
    _displayDpr() { return window.devicePixelRatio || 1; }
    _zoomToPercent(z) { return Math.round(z * this._displayDpr() * 100); }
    _percentToZoom(p) { return p / 100 / this._displayDpr(); }

    zoomIn() {
        this.zoom = Math.min(500.0, this.zoom * 1.2);  // Max 50000% for pixel-level zoom
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }

    zoomOut() {
        this.zoom = Math.max(0.01, this.zoom / 1.2);
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }

    setZoom(zoomLevel) {
        this.zoom = Math.max(0.01, Math.min(500.0, zoomLevel));
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }
    
    /**
     * Compute the workspace bounding box of all visible canvases. Returns
     * {x, y, width, height} of the union. Falls back to a synthetic box at
     * (0, 0, rasterWidth, rasterHeight) for projects with no canvases array
     * (pre-Slice-1) or when no canvases are visible.
     */
    _workspaceBounds() {
        const proj = window.app && window.app.project;
        const canvases = (proj && Array.isArray(proj.canvases)) ? proj.canvases : [];
        const visible = canvases.filter(c => c && c.visible !== false);
        if (visible.length === 0) {
            return { x: 0, y: 0, width: this.rasterWidth, height: this.rasterHeight };
        }
        const useShow = this.isShowLookView();
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        visible.forEach(c => {
            const wx = c.workspace_x || 0;
            const wy = c.workspace_y || 0;
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            const h = (useShow && c.show_raster_height) || c.raster_height || 0;
            if (wx < minX) minX = wx;
            if (wy < minY) minY = wy;
            if (wx + w > maxX) maxX = wx + w;
            if (wy + h > maxY) maxY = wy + h;
        });
        return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    }

    fitToView() {
        // Multi-canvas (v0.8 Slice 3): fit to the union bbox of all visible
        // canvases instead of just the active canvas's raster.
        const bb = this._workspaceBounds();
        const w = bb.width || this.rasterWidth;
        const h = bb.height || this.rasterHeight;
        const zoomX = (this.canvas.width * 0.9) / w;
        const zoomY = (this.canvas.height * 0.9) / h;
        this.zoom = Math.min(zoomX, zoomY);
        this.panX = (this.canvas.width - w * this.zoom) / 2 - bb.x * this.zoom;
        this.panY = (this.canvas.height - h * this.zoom) / 2 - bb.y * this.zoom;
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }

    zoomActual() {
        if (!window.app || !window.app.currentLayer) {
            // 1:1 sizing: 1 raster px == 1 device px (so on Retina, halve the
            // CSS-pixel scale).
            this.zoom = 1.0 / this._displayDpr();
            this.panX = 100;
            this.panY = 100;
        } else {
            const layer = window.app.currentLayer;
            // Zoom-to-layer in the active view, so it matches what's rendered.
            const bounds = this.getLayerBoundsInActiveView(layer);
            // bounds.x/y are canvas-relative (in the layer's parent canvas's
            // raster coords). Add the canvas's workspace_x/y so the pan
            // centers on where the layer is actually drawn in the workspace,
            // otherwise 1:1 zooms to the wrong canvas's slot.
            let wx = 0, wy = 0;
            if (window.app.project && window.app.project.canvases && layer.canvas_id) {
                const c = window.app.project.canvases.find(c => c.id === layer.canvas_id);
                if (c) { wx = c.workspace_x || 0; wy = c.workspace_y || 0; }
            }
            const layerWidth = bounds.width;
            const layerHeight = bounds.height;
            const zoomX = (this.canvas.width * 0.9) / layerWidth;
            const zoomY = (this.canvas.height * 0.9) / layerHeight;
            this.zoom = Math.min(zoomX, zoomY);
            const layerCenterX = bounds.x + wx + layerWidth / 2;
            const layerCenterY = bounds.y + wy + layerHeight / 2;
            this.panX = this.canvas.width / 2 - layerCenterX * this.zoom;
            this.panY = this.canvas.height / 2 - layerCenterY * this.zoom;
        }
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    }

    /**
     * v0.8 Slice 9: snap a dragged canvas's edges to abut (or align with)
     * neighboring canvases. Threshold scales with current zoom so the snap
     * "feels" the same physical distance regardless of zoom level, ~14
     * device px on screen.
     *
     * Returns the (possibly snapped) {x, y} workspace position. Each axis is
     * checked independently so you can snap one side without locking the
     * other.
     */
    _snapCanvasToNeighbors(dragged, proposedX, proposedY) {
        if (!window.app || !window.app.project || !Array.isArray(window.app.project.canvases)) {
            return { x: proposedX, y: proposedY };
        }
        const useShow = this.isShowLookView();
        const draggedW = (useShow && dragged.show_raster_width) || dragged.raster_width || 0;
        const draggedH = (useShow && dragged.show_raster_height) || dragged.raster_height || 0;
        if (draggedW <= 0 || draggedH <= 0) return { x: proposedX, y: proposedY };
        // Snap threshold in workspace coords (zoom-corrected so on-screen
        // feel is consistent at any zoom).
        const threshold = 14 / Math.max(this.zoom, 0.0001);
        const draggedLeft = proposedX;
        const draggedRight = proposedX + draggedW;
        const draggedTop = proposedY;
        const draggedBottom = proposedY + draggedH;
        let bestDx = null, bestDy = null;
        const consider = (delta, current) => {
            if (Math.abs(delta) > threshold) return current;
            if (current === null || Math.abs(delta) < Math.abs(current)) return delta;
            return current;
        };
        for (const other of window.app.project.canvases) {
            if (!other || other.id === dragged.id || other.visible === false) continue;
            const ox = other.workspace_x || 0;
            const oy = other.workspace_y || 0;
            const ow = (useShow && other.show_raster_width) || other.raster_width || 0;
            const oh = (useShow && other.show_raster_height) || other.raster_height || 0;
            if (ow <= 0 || oh <= 0) continue;
            const otherLeft = ox, otherRight = ox + ow;
            const otherTop = oy, otherBottom = oy + oh;
            // X-axis snap candidates: abut (left-to-right, right-to-left)
            // plus aligned edges (left↔left, right↔right, centerline).
            bestDx = consider(otherRight - draggedLeft, bestDx);   // dragged.left snaps to other.right (abut)
            bestDx = consider(otherLeft - draggedRight, bestDx);   // dragged.right snaps to other.left (abut)
            bestDx = consider(otherLeft - draggedLeft, bestDx);    // align lefts
            bestDx = consider(otherRight - draggedRight, bestDx);  // align rights
            // Y-axis snap candidates
            bestDy = consider(otherBottom - draggedTop, bestDy);   // dragged.top snaps to other.bottom (abut)
            bestDy = consider(otherTop - draggedBottom, bestDy);   // dragged.bottom snaps to other.top (abut)
            bestDy = consider(otherTop - draggedTop, bestDy);      // align tops
            bestDy = consider(otherBottom - draggedBottom, bestDy);// align bottoms
        }
        return {
            x: proposedX + (bestDx || 0),
            y: proposedY + (bestDy || 0),
        };
    }

    calculateMagneticSnap(offsetX, offsetY, currentLayer) {
        const snapDistance = 20; // Snap within 20 pixels - feels natural
        let snappedX = offsetX;
        let snappedY = offsetY;

        // Width/height are the same regardless of view; use raw bounds.
        const currentBounds = this.getLayerBounds(currentLayer);
        const layerWidth = currentBounds.width;
        const layerHeight = currentBounds.height;
        
        const currentLeft = offsetX;
        const currentRight = offsetX + layerWidth;
        const currentTop = offsetY;
        const currentBottom = offsetY + layerHeight;
        
        
        // Snap to raster boundaries - HARD EDGES ONLY
        // Left edge to 0
        if (Math.abs(currentLeft - 0) <= snapDistance) {
            snappedX = 0;
        }
        // Right edge to raster width
        if (Math.abs(currentRight - this.rasterWidth) <= snapDistance) {
            snappedX = this.rasterWidth - layerWidth;
        }
        // Top edge to 0
        if (Math.abs(currentTop - 0) <= snapDistance) {
            snappedY = 0;
        }
        // Bottom edge to raster height
        if (Math.abs(currentBottom - this.rasterHeight) <= snapDistance) {
            snappedY = this.rasterHeight - layerHeight;
        }
        
        // Snap to other layers - HARD EDGES ONLY
        // Other layers' bounds are compared against the dragged layer's
        // proposed offset (offsetX/Y), which is in the active view's
        // coords, so use active-view bounds for the comparison.
        if (window.app && window.app.project) {
            window.app.project.layers.forEach(layer => {
                if (layer.id === currentLayer.id || !layer.visible) return;

                const otherBounds = this.getLayerBoundsInActiveView(layer);
                const otherLeft = otherBounds.x;
                const otherRight = otherBounds.x + otherBounds.width;
                const otherTop = otherBounds.y;
                const otherBottom = otherBounds.y + otherBounds.height;
                
                // Snap any edge of current layer to any edge of other layer
                // Left edge snaps
                if (Math.abs(currentLeft - otherLeft) <= snapDistance) snappedX = otherLeft;
                if (Math.abs(currentLeft - otherRight) <= snapDistance) snappedX = otherRight;
                
                // Right edge snaps
                if (Math.abs(currentRight - otherLeft) <= snapDistance) snappedX = otherLeft - layerWidth;
                if (Math.abs(currentRight - otherRight) <= snapDistance) snappedX = otherRight - layerWidth;
                
                // Top edge snaps
                if (Math.abs(currentTop - otherTop) <= snapDistance) snappedY = otherTop;
                if (Math.abs(currentTop - otherBottom) <= snapDistance) snappedY = otherBottom;
                
                // Bottom edge snaps
                if (Math.abs(currentBottom - otherTop) <= snapDistance) snappedY = otherTop - layerHeight;
                if (Math.abs(currentBottom - otherBottom) <= snapDistance) snappedY = otherBottom - layerHeight;
            });
        }
        
        return { x: Math.round(snappedX), y: Math.round(snappedY) };
    }
    
    setViewMode(mode) {
        this.viewMode = mode;
        // Slice 6: rasterWidth/Height now read view-aware from the active
        // canvas via getters (pixel raster on pixel-map/cabinet-id, show
        // raster on show-look/data-flow/power), so no manual swap needed.
        // Refresh the toolbar inputs so the user sees the right numbers when
        // switching tabs.
        const rw = document.getElementById('toolbar-raster-width');
        const rh = document.getElementById('toolbar-raster-height');
        if (rw) rw.value = this.rasterWidth;
        if (rh) rh.value = this.rasterHeight;
        this.render();
    }

    getLayerBorderColor(layer, mode = this.viewMode) {
        if (!layer) return '#ffffff';
        if (mode === 'cabinet-id') return layer.border_color_cabinet || layer.border_color || '#ffffff';
        if (mode === 'data-flow') return layer.border_color_data || layer.border_color || '#ffffff';
        if (mode === 'power') return layer.border_color_power || layer.border_color || '#ffffff';
        return layer.border_color_pixel || layer.border_color || '#ffffff';
    }
    
    renderPanel(panel, layer) {
        // The outer render() loop applies ctx.translate(dx, dy) per layer for
        // Show Look / Data / Power so the panel's processor coords land at
        // their show position. The clip rect we set up here lives in that
        // *translated* space, so the raster boundary (in screen-relative
        // coords [0, rasterWidth]) maps to local coords [-dx, rasterWidth-dx].
        // Computing the clip without that shift drops panels whenever
        // panel.x >= rasterWidth in processor space, even when the show
        // offset places them inside the visible raster.
        const dx = this._renderDx || 0;
        const dy = this._renderDy || 0;
        const rasterLeft = -dx;
        const rasterTop = -dy;
        const rasterRight = this.rasterWidth - dx;
        const rasterBottom = this.rasterHeight - dy;
        const clipX = Math.max(rasterLeft, panel.x);
        const clipY = Math.max(rasterTop, panel.y);
        const clipRight = Math.min(rasterRight, panel.x + panel.width);
        const clipBottom = Math.min(rasterBottom, panel.y + panel.height);
        const clipWidth = clipRight - clipX;
        const clipHeight = clipBottom - clipY;

        if (clipWidth <= 0 || clipHeight <= 0) return;
        
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(clipX, clipY, clipWidth, clipHeight);
        this.ctx.clip();
        
        // Render based on view mode
        switch (this.viewMode) {
            case 'pixel-map':
                this.renderPixelMap(panel, layer);
                break;
            case 'cabinet-id':
                this.renderCabinetID(panel, layer);
                break;
            case 'show-look':
                // Show Look uses the same checkerboard look as Pixel Map so
                // the user can see the screen arrangement; only the layout
                // (positions) differs.
                this.renderPixelMap(panel, layer);
                break;
            case 'data-flow':
                this.renderDataFlow(panel, layer);
                break;
            case 'power':
                this.renderPower(panel, layer);
                break;
        }
        
        this.ctx.restore();
    }
    
    renderPixelMap(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom like text
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'; // Semi-transparent white
            this.ctx.lineWidth = 1; // Thinner line for ghost, scales with zoom
            this.ctx.setLineDash([5, 5]); // Dashed line, scales with zoom
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]); // Reset dash
            return; // Don't fill, just outline
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        // Where two panels meet, you get 2+2 = 4 pixels total
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'pixel-map');
            this.ctx.lineWidth = 2;  // 2 LED pixels wide
            // Inset by half the line width so the full 2px is inside the panel
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
    }
    
    renderPixelGrid(layer) {
        // Render pixel grid over the ENTIRE layer (on top of everything)
        // This shows the actual LED pixel boundaries (1 world unit = 1 LED pixel)
        
        const bounds = this.getLayerBounds(layer);
        const layerLeft = bounds.x;
        const layerTop = bounds.y;
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const layerRight = layerLeft + layerWidth;
        const layerBottom = layerTop + layerHeight;
        
        // Clip to raster bounds
        const clipX = Math.max(0, layerLeft);
        const clipY = Math.max(0, layerTop);
        const clipRight = Math.min(layerRight, this.rasterWidth);
        const clipBottom = Math.min(layerBottom, this.rasterHeight);
        
        if (clipRight <= clipX || clipBottom <= clipY) return;
        
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(clipX, clipY, clipRight - clipX, clipBottom - clipY);
        this.ctx.clip();
        
        // Only draw grid if pixels are large enough to see (at least 3 screen pixels per LED pixel)
        const screenPixelSize = this.zoom;  // 1 world unit = 1 LED pixel
        if (screenPixelSize < 3) {
            this.ctx.restore();
            return;
        }
        
        // Calculate visible range to optimize rendering
        const visibleLeft = (0 - this.panX) / this.zoom;
        const visibleTop = (0 - this.panY) / this.zoom;
        const visibleRight = (this.canvas.width - this.panX) / this.zoom;
        const visibleBottom = (this.canvas.height - this.panY) / this.zoom;
        
        // Grid line style - darker gray, more pronounced
        this.ctx.strokeStyle = 'rgba(80, 80, 80, 0.55)';
        this.ctx.lineWidth = 1 / this.zoom;  // 1 screen pixel wide
        
        // Draw vertical lines (every 1 world unit = 1 LED pixel)
        this.ctx.beginPath();
        const startCol = Math.max(0, Math.floor(visibleLeft - layerLeft));
        const endCol = Math.min(layerWidth, Math.ceil(visibleRight - layerLeft));
        
        for (let col = startCol; col <= endCol; col++) {
            const x = layerLeft + col;
            if (x >= clipX && x <= clipRight) {
                this.ctx.moveTo(x, clipY);
                this.ctx.lineTo(x, clipBottom);
            }
        }
        
        // Draw horizontal lines
        const startRow = Math.max(0, Math.floor(visibleTop - layerTop));
        const endRow = Math.min(layerHeight, Math.ceil(visibleBottom - layerTop));
        
        for (let row = startRow; row <= endRow; row++) {
            const y = layerTop + row;
            if (y >= clipY && y <= clipBottom) {
                this.ctx.moveTo(clipX, y);
                this.ctx.lineTo(clipRight, y);
            }
        }
        
        this.ctx.stroke();
        this.ctx.restore();
    }
    
    renderCabinetID(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'cabinet-id');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
        
        // Cabinet ID numbers rendered separately in screen space - see renderCabinetIDNumbers()
    }
    
    renderDataFlow(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'data-flow');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
        
        // Data flow arrows are rendered as a separate pass in renderDataFlowArrows
    }
    
    // Render capacity error overlay ON TOP of everything (including labels)
    // This renders WITHOUT clipping so it's visible even outside raster bounds.
    // Called from the third render pass (outside the per-layer ctx.translate),
    // so use show-translated bounds, getLayerBounds returns processor coords
    // which would land the badge at the layer's pixel-map position even when
    // the layer renders at its show position in Data Flow / Power.
    renderCapacityErrorOverlay(layer) {
        if (!layer._capacityError) return;

        const err = layer._capacityError;
        const bounds = this.getLayerBoundsInActiveView(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        
        // Red semi-transparent overlay on the layer itself
        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);
        
        // Measure text to size box appropriately
        this.ctx.font = 'bold 48px Arial';
        const titleText = `CANNOT FIT COMPLETE ${err.unitType.toUpperCase()}`;
        const titleWidth = this.ctx.measureText(titleText).width;
        
        this.ctx.font = '28px Arial';
        const detailText = `Need ${err.unitCount} panels, port only fits ${err.panelsPerPort}`;
        const detailWidth = this.ctx.measureText(detailText).width;
        
        this.ctx.font = '24px Arial';
        const infoText = `Port: ${err.portCapacity.toLocaleString()} px | Panel: ${err.panelPixels.toLocaleString()} px`;
        const infoWidth = this.ctx.measureText(infoText).width;
        
        // Size box to fit text with padding
        const textBoxWidth = Math.max(titleWidth, detailWidth, infoWidth) + 40;
        const textBoxHeight = 130;
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Red border around text box
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Error text
        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = 'bold 48px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        this._fillText(titleText, layerCenterX, layerCenterY - 35);
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = '28px Arial';
        this._fillText(detailText, layerCenterX, layerCenterY + 10);
        this.ctx.font = '24px Arial';
        this.ctx.fillStyle = '#AAAAAA';
        this._fillText(infoText, layerCenterX, layerCenterY + 45);
    }
    
    renderDataFlowArrows(layer) {
        // Get the flow pattern (default: top-right, vertical-first)
        const pattern = layer.flowPattern || 'tl-h';
        const baseLineWidth = layer.arrowLineWidth || 4;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.dataFlowLabelSize || 30;
        const primaryColor = layer.primaryColor || '#00FF00';
        const primaryTextColor = layer.primaryTextColor || '#000000';
        const backupColor = layer.backupColor || '#FF0000';
        const backupTextColor = layer.backupTextColor || '#FFFFFF';
        const lineColor = layer.dataFlowColor || '#FFFFFF';
        const arrowColor = layer.arrowColor || '#0042AA';
        const useRandomColors = layer.randomDataColors || false;
        const isCustomFlow = pattern === 'custom';
        if (isCustomFlow) {
            // Clear any capacity error when in custom mode
            layer._capacityError = null;
        }
        // Calculate circle radius based on label size
        const circleRadius = labelSize * 1.2;
        
        // Random color palette for multi-port support
        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];
        
        // Get visible (non-hidden) panels
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;
        
        // Save context, clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        
        const drawPort = (portPanels, portNum) => {
            if (portPanels.length === 0) return;
            
            const currentLineColor = useRandomColors ? randomColors[(portNum - 1) % randomColors.length] : lineColor;
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;
            
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                
                this.ctx.beginPath();
                this.ctx.moveTo(cx, cy);
                this.ctx.lineTo(nx, ny);
                this.ctx.stroke();
            }
            
            this.ctx.fillStyle = arrowColor;
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                
                const midX = this.snap((cx + nx) / 2);
                const midY = this.snap((cy + ny) / 2);
                const angle = Math.atan2(ny - cy, nx - cx);
                const arrowLen = lineWidth * 3;
                
                this.ctx.beginPath();
                this.ctx.moveTo(
                    midX + arrowLen * Math.cos(angle),
                    midY + arrowLen * Math.sin(angle)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle - Math.PI / 5),
                    midY - arrowLen * Math.sin(angle - Math.PI / 5)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle + Math.PI / 5),
                    midY - arrowLen * Math.sin(angle + Math.PI / 5)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }
            
            const firstPanel = portPanels[0];
            let px = this.snap(firstPanel.x + firstPanel.width / 2);
            let py = this.snap(firstPanel.y + firstPanel.height / 2);
            const lastPanel = portPanels[portPanels.length - 1];
            let rx = this.snap(lastPanel.x + lastPanel.width / 2);
            let ry = this.snap(lastPanel.y + lastPanel.height / 2);
            const primaryLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'primary') : `P${portNum}`;
            const returnLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'return') : `R${portNum}`;
            
            // If the port has only one panel, draw backup first so primary is on top.
            if (portPanels.length === 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, circleRadius, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${labelSize}px Arial`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this._fillText(returnLabel, rx, ry);
            }

            this.ctx.fillStyle = primaryColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, circleRadius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.fillStyle = primaryTextColor;
            this.ctx.font = `bold ${labelSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillText(primaryLabel, px, py);

            if (portPanels.length > 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, circleRadius, 0, Math.PI * 2);
                this.ctx.fill();

                this.ctx.fillStyle = backupTextColor;
                this._fillText(returnLabel, rx, ry);
            }
        };

        // Custom flow mode: use user-defined paths
        if (isCustomFlow && layer.customPortPaths) {
            const portNums = Object.keys(layer.customPortPaths)
                .map(n => parseInt(n, 10))
                .sort((a, b) => a - b);
            
            portNums.forEach(portNum => {
                const path = layer.customPortPaths[portNum] || [];
                const portPanels = path.map(p => {
                    const panel = layer.panels.find(panel => panel.row === p.row && panel.col === p.col);
                    return panel && !panel.hidden ? panel : null;
                }).filter(Boolean);
                drawPort(portPanels, portNum);
            });
            
            this.ctx.restore();
            return;
        }

        const assignments = window.app ? window.app.calculatePortAssignments(layer) : [];
        if (layer._capacityError) {
            this.ctx.restore();
            return;
        }

        const ports = new Map();
        assignments.forEach(item => {
            if (!item || !item.panel || item.panel.hidden) return;
            if (!ports.has(item.port)) ports.set(item.port, []);
            ports.get(item.port).push(item.panel);
        });

        [...ports.keys()].sort((a, b) => a - b).forEach(portNum => {
            drawPort(ports.get(portNum) || [], portNum);
        });
        
        this.ctx.restore();
    }

    getPowerCircuitPalette() {
        return ['#FF0000', '#FF8C00', '#FFE600', '#00CC00', '#1E4CFF', '#8A2BE2'];
    }

    getPowerCircuitColor(layer, circuitNum) {
        if (window.app && typeof window.app.getPowerCircuitColor === 'function') {
            return window.app.getPowerCircuitColor(layer, circuitNum);
        }
        const palette = this.getPowerCircuitPalette();
        return palette[(Math.max(1, circuitNum) - 1) % palette.length];
    }

    getPowerCircuitLetter(circuitNum) {
        let n = Math.max(1, parseInt(circuitNum, 10) || 1);
        let out = '';
        while (n > 0) {
            n -= 1;
            out = String.fromCharCode(65 + (n % 26)) + out;
            n = Math.floor(n / 26);
        }
        return out;
    }

    getPowerLabelTextColor(hexColor) {
        const normalized = String(hexColor || '').replace('#', '');
        if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return '#000000';
        const r = parseInt(normalized.slice(0, 2), 16);
        const g = parseInt(normalized.slice(2, 4), 16);
        const b = parseInt(normalized.slice(4, 6), 16);
        const luminance = (0.299 * r) + (0.587 * g) + (0.114 * b);
        return luminance > 150 ? '#000000' : '#FFFFFF';
    }

    getPowerPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    preparePowerLayerRenderData(layer) {
        if (!window.app) return;
        const isCustom = (layer.powerFlowPattern || 'tl-h') === 'custom';
        let error = null;
        let circuits = [];
        let circuitNumKeys = null;

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            circuitNumKeys = circuitNums;
            circuits = circuitNums.map(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                return path
                    .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                    .filter(p => p && !p.hidden);
            });
        } else {
            const assignments = window.app.calculatePowerAssignments(layer);
            error = assignments.error;
            circuits = assignments.circuits || [];
        }

        layer._powerError = error;
        layer._powerCircuits = circuits;
        layer._powerCircuitNumKeys = circuitNumKeys;

        const panelCircuitMap = new Map();
        const panelIndexMap = new Map();
        if (!error) {
            circuits.forEach((circuitPanels, idx) => {
                const circuitNum = circuitNumKeys ? circuitNumKeys[idx] : idx + 1;
                (circuitPanels || []).forEach((panel, panelIdx) => {
                    const key = this.getPowerPanelKey(panel);
                    panelCircuitMap.set(key, circuitNum);
                    panelIndexMap.set(key, panelIdx + 1);
                });
            });
        }
        layer._powerPanelCircuitMap = panelCircuitMap;
        layer._powerPanelIndexMap = panelIndexMap;
    }

    renderPowerArrows(layer) {
        const pattern = layer.powerFlowPattern || 'tl-h';
        const baseLineWidth = layer.powerLineWidth || 8;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.powerLabelSize || 14;
        const powerLabelBgColor = layer.powerLabelBgColor || '#D95000';
        const powerLabelTextColor = layer.powerLabelTextColor || '#000000';
        const lineColor = layer.powerLineColor || '#FF0000';
        const arrowColor = layer.powerArrowColor || '#0042AA';
        const useRandomColors = layer.powerRandomColors || false;
        const useColorCodedView = !!layer.powerColorCodedView;
        const isCustom = pattern === 'custom';
        if (isCustom) {
            layer._powerError = null;
        }
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;

        this.ctx.save();
        this._clipToActiveRaster();
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];

        const drawCircuitLabel = (panelStart, panelNext, circuitNum) => {
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const px = this.snap(panelStart.x + panelStart.width / 2);
            const py = this.snap(panelStart.y + panelStart.height / 2);
            this.ctx.font = `bold ${labelSize}px Arial`;
            const textWidth = this.ctx.measureText(label).width;
            const padding = Math.max(6, labelSize * 0.25);
            const circleRadius = Math.max(labelSize * 0.7, lineWidth * 1.4, textWidth / 2 + padding);

            this.ctx.fillStyle = powerLabelBgColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, circleRadius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.fillStyle = powerLabelTextColor;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillText(label, px, py);
        };

        if (useColorCodedView) {
            if (!Array.isArray(layer._powerCircuits) && window.app) {
                const assignments = window.app.calculatePowerAssignments(layer);
                layer._powerError = assignments.error;
                layer._powerCircuits = assignments.circuits || [];
            }
            if (layer._powerError || !Array.isArray(layer._powerCircuits)) {
                this.ctx.restore();
                return;
            }
            const colorViewKeys = layer._powerCircuitNumKeys;
            layer._powerCircuits.forEach((circuitPanels, idx) => {
                if (!circuitPanels || circuitPanels.length === 0) return;
                const circuitNum = colorViewKeys ? colorViewKeys[idx] : idx + 1;
                drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
            });
            this.ctx.restore();
            return;
        }

        const drawCircuit = (circuitPanels, circuitNum) => {
            if (circuitPanels.length === 0) return;
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;

            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                this.ctx.beginPath();
                this.ctx.moveTo(cx, cy);
                this.ctx.lineTo(nx, ny);
                this.ctx.stroke();
            }

            this.ctx.fillStyle = arrowColor;
            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                const midX = this.snap((cx + nx) / 2);
                const midY = this.snap((cy + ny) / 2);
                const angle = Math.atan2(ny - cy, nx - cx);
                const arrowLen = lineWidth * 3;
                this.ctx.beginPath();
                this.ctx.moveTo(
                    midX + arrowLen * Math.cos(angle),
                    midY + arrowLen * Math.sin(angle)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle - Math.PI / 5),
                    midY - arrowLen * Math.sin(angle - Math.PI / 5)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle + Math.PI / 5),
                    midY - arrowLen * Math.sin(angle + Math.PI / 5)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }

            drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
        };

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            circuitNums.forEach(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                const panels = path
                    .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                    .filter(p => p && !p.hidden);
                drawCircuit(panels, circuitNum);
            });
            this.ctx.restore();
            return;
        }

        if (!Array.isArray(layer._powerCircuits) && window.app) {
            const assignments = window.app.calculatePowerAssignments(layer);
            layer._powerError = assignments.error;
            layer._powerCircuits = assignments.circuits || [];
        }
        if (layer._powerError) {
            this.ctx.restore();
            return;
        }

        layer._powerCircuits.forEach((circuitPanels, idx) => {
            if (!circuitPanels || circuitPanels.length === 0) return;
            drawCircuit(circuitPanels, idx + 1);
        });

        this.ctx.restore();
    }

    renderPowerErrorOverlay(layer) {
        if (!layer._powerError) return;
        const err = layer._powerError;
        // Same as renderCapacityErrorOverlay: this is called from the third
        // render pass outside the per-layer translate, so we need the layer's
        // active-view bounds (show offset already baked in), using raw
        // processor bounds parks the badge at the wrong screen position when
        // the layer is moved in Show Look.
        const bounds = this.getLayerBoundsInActiveView(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;

        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);

        const titleText = err.message || 'POWER ERROR';
        this.ctx.font = 'bold 42px Arial';
        const titleWidth = this.ctx.measureText(titleText).width;
        const textBoxWidth = titleWidth + 40;
        const textBoxHeight = 90;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );

        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = 'bold 42px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this._fillText(titleText, layerCenterX, layerCenterY);
    }
    
    // Get panel flow order for a specific range of rows (for horizontal-first patterns)
    getPanelFlowOrderForRows(layer, pattern, startRow, endRow) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const cols = layer.columns;
        
        // Parse pattern
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        
        const orderedPanels = [];
        const numRows = endRow - startRow + 1;
        
        // Horizontal-first serpentine within this rectangle
        for (let r = 0; r < numRows; r++) {
            const actualRow = startsTop ? (startRow + r) : (endRow - r);
            
            // Determine direction for this row (serpentine)
            let leftToRight;
            if (startsLeft) {
                leftToRight = (r % 2 === 0);
            } else {
                leftToRight = (r % 2 !== 0);
            }
            
            if (leftToRight) {
                for (let c = 0; c < cols; c++) {
                    const panel = panelMap.get(`${actualRow},${c}`);
                    if (panel) orderedPanels.push(panel);
                }
            } else {
                for (let c = cols - 1; c >= 0; c--) {
                    const panel = panelMap.get(`${actualRow},${c}`);
                    if (panel) orderedPanels.push(panel);
                }
            }
        }
        
        return orderedPanels;
    }
    
    // Get panel flow order for a specific range of columns (for vertical-first patterns)
    getPanelFlowOrderForCols(layer, pattern, startCol, endCol) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const rows = layer.rows;
        
        // Parse pattern
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        
        const orderedPanels = [];
        const numCols = endCol - startCol + 1;
        
        // Vertical-first serpentine within this rectangle
        for (let c = 0; c < numCols; c++) {
            const actualCol = startsLeft ? (startCol + c) : (endCol - c);
            
            // Determine direction for this column (serpentine)
            let topToBottom;
            if (startsTop) {
                topToBottom = (c % 2 === 0);
            } else {
                topToBottom = (c % 2 !== 0);
            }
            
            if (topToBottom) {
                for (let r = 0; r < rows; r++) {
                    const panel = panelMap.get(`${r},${actualCol}`);
                    if (panel) orderedPanels.push(panel);
                }
            } else {
                for (let r = rows - 1; r >= 0; r--) {
                    const panel = panelMap.get(`${r},${actualCol}`);
                    if (panel) orderedPanels.push(panel);
                }
            }
        }
        
        return orderedPanels;
    }
    
    getPanelFlowOrder(layer, pattern) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const cols = layer.columns;
        const rows = layer.rows;
        
        // Parse pattern
        const [startCorner, direction] = pattern.split('-');
        
        // Build ordered list based on pattern
        const ordered = [];
        
        // Determine starting position and iteration directions
        let startRow, startCol, rowDir, colDir, isVerticalFirst;
        
        switch (startCorner) {
            case 'tl': // top-left
                startRow = 0; startCol = 0;
                rowDir = 1; colDir = 1;
                break;
            case 'tr': // top-right
                startRow = 0; startCol = cols - 1;
                rowDir = 1; colDir = -1;
                break;
            case 'bl': // bottom-left
                startRow = rows - 1; startCol = 0;
                rowDir = -1; colDir = 1;
                break;
            case 'br': // bottom-right
                startRow = rows - 1; startCol = cols - 1;
                rowDir = -1; colDir = -1;
                break;
            default:
                startRow = 0; startCol = cols - 1;
                rowDir = 1; colDir = -1;
        }
        
        isVerticalFirst = (direction === 'v');
        
        if (isVerticalFirst) {
            // Vertical-first: traverse columns, serpentine within each column
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const shouldReverse = colOffset % 2 === 1;
                
                if (shouldReverse) {
                    // Reverse direction for serpentine
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                }
            }
        } else {
            // Horizontal-first: traverse rows, serpentine within each row
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const shouldReverse = rowOffset % 2 === 1;
                
                if (shouldReverse) {
                    // Reverse direction for serpentine
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                }
            }
        }
        
        return ordered;
    }
    
    renderPower(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }

        let fillHex = null;
        let panelCircuitNum = null;
        if (layer.powerColorCodedView && !layer._powerError && layer._powerPanelCircuitMap instanceof Map) {
            const key = this.getPowerPanelKey(panel);
            panelCircuitNum = layer._powerPanelCircuitMap.get(key);
            if (panelCircuitNum) {
                fillHex = this.getPowerCircuitColor(layer, panelCircuitNum);
            }
        }

        if (fillHex) {
            this.ctx.fillStyle = fillHex;
        } else {
            const color = panel.is_color1 ? layer.color1 : layer.color2;
            this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        }
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);

        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'power');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
    }
    
    renderCabinetIDNumbers(layer) {
        if (!layer.show_numbers) return;
        
        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        const numberSize = layer.number_size || 24;
        const cabinetIdStyle = layer.cabinetIdStyle || 'column-row';
        const cabinetIdPosition = layer.cabinetIdPosition || 'center';
        const cabinetIdColor = layer.cabinetIdColor || '#ffffff';
        
        this.ctx.fillStyle = cabinetIdColor;
        this.ctx.font = `bold ${numberSize}px Arial`;
        
        // Position-based settings
        if (cabinetIdPosition === 'center') {
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
        } else {
            // top-left
            this.ctx.textAlign = 'left';
            this.ctx.textBaseline = 'top';
        }
        
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            if (panel.x >= this.rasterWidth || panel.y >= this.rasterHeight) return;
            
            // Calculate label based on style
            let label = '';
            const col = panel.col;  // 0-indexed
            const row = panel.row;  // 0-indexed
            
            switch (cabinetIdStyle) {
                case 'column-row':
                    // A1, B1, C1... (column letter + row number)
                    // Reads top-to-bottom by columns
                    label = this.getColumnLetter(col) + (row + 1);
                    break;
                    
                case 'row-column':
                    // A1, A2, A3... (row letter + column number)
                    // Reads left-to-right by rows
                    label = this.getColumnLetter(row) + (col + 1);
                    break;
                    
                case 'row-col':
                    // 1,1  1,2  1,3... (row number, column number)
                    // Reads left-to-right with comma notation
                    label = `${row + 1},${col + 1}`;
                    break;
                    
                default:
                    label = panel.number; // Fallback to sequential
            }
            
            // Calculate position
            let textX, textY;
            if (cabinetIdPosition === 'center') {
                textX = panel.x + panel.width / 2;
                textY = panel.y + panel.height / 2;
            } else {
                // top-left with small padding
                textX = panel.x + 5;
                textY = panel.y + 5;
            }
            
            this._fillText(label, this.snap(textX), this.snap(textY));
        });

        this.ctx.restore();
    }
    
    // Helper function to convert number to letter (0=A, 1=B, ... 25=Z, 26=AA, etc.)
    getColumnLetter(num) {
        let letter = '';
        while (num >= 0) {
            letter = String.fromCharCode(65 + (num % 26)) + letter;
            num = Math.floor(num / 26) - 1;
        }
        return letter;
    }
    
    renderLayerLabels(layer) {
        if ((layer.type || 'screen') === 'image') {
            return;
        }
        // Note: Clipping for layer occlusion is handled in the render() second pass
        // We only clip to raster bounds here (translate-aware), which
        // intersects with the occlusion clip
        this.ctx.save();
        this._clipToActiveRaster();

        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        const bottomY = bounds.y + layerHeight;
        
        // Calculate physical dimensions
        const widthMM = (layer.panel_width_mm || 500) * (layerWidth / (layer.cabinet_width || 1));
        const heightMM = (layer.panel_height_mm || 500) * (layerHeight / (layer.cabinet_height || 1));
        const widthM = widthMM / 1000;
        const heightM = heightMM / 1000;
        const widthFt = widthM * 3.28084;
        const heightFt = heightM * 3.28084;
        
        const activePanels = layer.panels.filter(p => !p.blank && !p.hidden).length;
        const equivalentPanels = layer.panels
            .filter(p => !p.blank && !p.hidden)
            .reduce((sum, p) => {
                if (window.app && typeof window.app.getPanelLoadFactor === 'function') {
                    return sum + window.app.getPanelLoadFactor(layer, p);
                }
                return sum + 1;
            }, 0);
        const panelWeightValue = layer.panel_weight || 20;
        const panelWeightUnit = layer.weight_unit || 'kg';
        const panelWeightKg = panelWeightUnit === 'lb' ? (panelWeightValue / 2.20462) : panelWeightValue;
        const totalWeightKg = equivalentPanels * panelWeightKg;
        const totalWeightLb = totalWeightKg * 2.20462;
        
        // Build labels - Screen Name is separate with white background
        // Per-tab showLabelName: each view mode has its own property, falling back to global → true
        let showLabelName;
        if (this.viewMode === 'cabinet-id') {
            showLabelName = layer.showLabelNameCabinet !== undefined ? layer.showLabelNameCabinet
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else if (this.viewMode === 'data-flow') {
            showLabelName = layer.showLabelNameDataFlow !== undefined ? layer.showLabelNameDataFlow
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else if (this.viewMode === 'power') {
            showLabelName = layer.showLabelNamePower !== undefined ? layer.showLabelNamePower
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else {
            showLabelName = layer.showLabelName !== undefined ? layer.showLabelName : true;
        }
        const screenName = showLabelName ? layer.name : null;
        
        // Other center labels (regular style)
        const centerLines = [];
        
        // Other labels only in pixel-map mode
        if (this.viewMode === 'pixel-map') {
            if (layer.showLabelSizePx) {
                centerLines.push(`W ${layerWidth} X H ${layerHeight}`);
            }
            if (layer.showLabelSizeM) {
                centerLines.push(`W ${widthM.toFixed(2)}(m) X H ${heightM.toFixed(2)}(m)`);
            }
            if (layer.showLabelSizeFt) {
                const useFractional = layer.useFractionalInches || false;
                
                if (useFractional) {
                    // FRACTIONAL MODE: e.g., 2' 2 7/8"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    const widthInWhole = Math.floor(widthInchesDecimal);
                    const widthInRemainder = widthInchesDecimal - widthInWhole;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    const heightInWhole = Math.floor(heightInchesDecimal);
                    const heightInRemainder = heightInchesDecimal - heightInWhole;
                    
                    // Convert decimal to fraction (1/16ths precision)
                    const toFraction = (decimal) => {
                        if (decimal < 0.03125) return ''; // Less than 1/16
                        const sixteenths = Math.round(decimal * 16);
                        // Simplify common fractions
                        if (sixteenths === 16) return '1'; // Whole inch
                        if (sixteenths === 8) return ' 1/2';
                        if (sixteenths === 4) return ' 1/4';
                        if (sixteenths === 12) return ' 3/4';
                        if (sixteenths === 2) return ' 1/8';
                        if (sixteenths === 6) return ' 3/8';
                        if (sixteenths === 10) return ' 5/8';
                        if (sixteenths === 14) return ' 7/8';
                        return ` ${sixteenths}/16`;
                    };
                    
                    const widthFrac = toFraction(widthInRemainder);
                    const heightFrac = toFraction(heightInRemainder);
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInWhole}${widthFrac}" X H ${heightFtTotal}' ${heightInWhole}${heightFrac}"`);
                } else {
                    // DECIMAL MODE: e.g., 2' 2.5"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInchesDecimal.toFixed(1)}" X H ${heightFtTotal}' ${heightInchesDecimal.toFixed(1)}"`);
                }
            }
            if (layer.showLabelWeight) {
                centerLines.push(`Weight ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
            }
        } else if (this.viewMode === 'data-flow') {
            if (layer.showDataFlowPortInfo && window.app) {
                // Always recompute from current layer state. Cached `_portsRequired`
                // is only refreshed for the currently-selected layer by
                // `updatePortCapacityDisplay`, so other layers' labels would go
                // stale until clicked. `renderDataFlowArrows` ran just above and
                // populated fresh `_autoPortsRequired` on this layer.
                let portsRequired = 0;
                const isCustom = typeof window.app.isCustomFlow === 'function'
                    ? window.app.isCustomFlow(layer)
                    : (layer.flowPattern === 'custom');
                if (isCustom && layer.customPortPaths) {
                    const customPorts = Object.keys(layer.customPortPaths)
                        .map(p => parseInt(p, 10))
                        .filter(p => (layer.customPortPaths[p] || []).length > 0);
                    portsRequired = customPorts.length > 0
                        ? Math.max(...customPorts)
                        : (layer._autoPortsRequired || layer.customPortIndex || 0);
                } else {
                    portsRequired = layer._autoPortsRequired || 0;
                    if (portsRequired <= 0 && typeof window.app.calculatePortAssignments === 'function') {
                        window.app.calculatePortAssignments(layer);
                        portsRequired = layer._autoPortsRequired || 0;
                    }
                }
                if (portsRequired > 0) {
                    const mains = portsRequired;
                    const backups = portsRequired;
                    centerLines.push(`${mains} Mains, ${backups} Backups | ${mains + backups} Ports`);
                }
            }
        } else if (this.viewMode === 'power') {
            if (layer.showPowerCircuitInfo && window.app) {
                // Always recompute from current layer state. `renderPowerArrows`
                // (or `preparePowerLayerRenderData`) ran just above and populated
                // `_powerCircuits` on this layer, so use that directly rather
                // than trusting `_powerCircuitsRequired` (only refreshed for
                // the currently-selected layer by `updatePowerStatsDisplay`).
                let circuits = Array.isArray(layer._powerCircuits)
                    ? layer._powerCircuits.filter(c => Array.isArray(c) && c.length > 0).length
                    : 0;
                if (circuits <= 0 && typeof window.app.calculatePowerAssignments === 'function') {
                    const assignments = window.app.calculatePowerAssignments(layer);
                    if (assignments && !assignments.error && Array.isArray(assignments.circuits)) {
                        circuits = assignments.circuits.filter(c => Array.isArray(c) && c.length > 0).length;
                    }
                }
                const voltage = parseFloat(layer.powerVoltage) || 0;
                const panelWatts = parseFloat(layer.panelWatts) || 0;
                const equivalentPanels = Array.isArray(layer.panels)
                    ? layer.panels
                        .filter(p => !p.hidden)
                        .reduce((sum, p) => {
                            if (typeof window.app.getPanelLoadFactor === 'function') {
                                return sum + window.app.getPanelLoadFactor(layer, p);
                            }
                            return sum + 1;
                        }, 0)
                    : 0;
                const totalWatts = panelWatts * equivalentPanels;
                const amps1 = voltage > 0 ? (totalWatts / voltage) : 0;
                const amps3 = voltage > 0 ? (totalWatts / (voltage * 1.73)) : 0;
                const multis = circuits > 0 ? Math.ceil(circuits / 6) : 0;
                centerLines.push(`${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`);
            }
        }
        
        // Build Info label text (separate, at bottom) - only in pixel-map mode
        // Single row format for compact display
        const infoLines = [];
        if (this.viewMode === 'pixel-map' && layer.showLabelInfo) {
            // Calculate aspect ratio
            const aspectRatio = layerWidth / layerHeight;
            const aspectRatioStr = `${aspectRatio.toFixed(2)}`;
            
            infoLines.push(`${layer.columns} Columns X ${layer.rows} Rows • ${activePanels} Cabinets Total / Resolution: ${layerWidth} X ${layerHeight} • Aspect Ratio: ${aspectRatioStr} • Weight: ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
        }
        
        // Use absolute pixel sizes - no scaling with zoom
        let fontSize = layer.labelsFontSize || 30;
        const lineHeight = fontSize + 4;
        const padding = 6;
        
        // Info label uses independent slider value
        const infoFontSize = layer.infoLabelSize || 14;
        const infoLineHeight = infoFontSize + 4;
        
        // Screen name uses tab-specific size and position settings
        let screenNameSize = fontSize; // Default for pixel-map
        let screenNameOffsetX = 0;
        let screenNameOffsetY = 0;
        
        if (this.viewMode === 'cabinet-id') {
            screenNameSize = layer.screenNameSizeCabinet || 14;
            screenNameOffsetX = layer.screenNameOffsetXCabinet || 0;
            screenNameOffsetY = layer.screenNameOffsetYCabinet || 0;
        } else if (this.viewMode === 'data-flow') {
            screenNameSize = layer.screenNameSizeDataFlow || 14;
            screenNameOffsetX = layer.screenNameOffsetXDataFlow || 0;
            screenNameOffsetY = layer.screenNameOffsetYDataFlow || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'power') {
            screenNameSize = layer.screenNameSizePower || 14;
            screenNameOffsetX = layer.screenNameOffsetXPower || 0;
            screenNameOffsetY = layer.screenNameOffsetYPower || 0;
            fontSize = screenNameSize;
        }
        
        const screenNameLineHeight = screenNameSize + 4;
        
        this.ctx.font = `bold ${fontSize}px Arial`;
        
        // Calculate total height of ALL center labels (screen name + other labels)
        let totalCenterHeight = 0;
        let screenNameHeight = 0;
        
        if (screenName) {
            screenNameHeight = screenNameLineHeight + padding * 2;
            totalCenterHeight += screenNameHeight;
            if (centerLines.length > 0) {
                totalCenterHeight += 5; // Gap between screen name and other labels
            }
        }
        
        if (centerLines.length > 0 && this.viewMode === 'pixel-map') {
            totalCenterHeight += centerLines.length * lineHeight + padding * 2;
        }
        
        // Start Y position so that ALL labels are centered vertically
        let currentY = centerY - totalCenterHeight / 2;
        

        
        // Render Screen Name with WHITE background and BLACK text
        let infoAnchorY = null;
        if (screenName) {
            // For non-pixel-map modes, use tab-specific offset position
            let screenNameX = centerX;
            let screenNameY = centerY;
            
            if (this.viewMode !== 'pixel-map') {
                // Apply tab-specific screen name offset (relative to center)
                screenNameX = centerX + screenNameOffsetX;
                screenNameY = centerY + screenNameOffsetY;
                
                // If offset pushes label outside layer bounds, reset to center
                if (screenNameX < bounds.x || screenNameX > bounds.x + layerWidth) {
                    screenNameX = centerX;
                }
                if (screenNameY < bounds.y || screenNameY > bounds.y + layerHeight) {
                    screenNameY = centerY;
                }
            } else {
                // Pixel map mode - keep original center position
                screenNameY = currentY + screenNameHeight / 2;
            }
            
            this.ctx.font = `bold ${screenNameSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            
            const metrics = this.ctx.measureText(screenName);
            const nameWidth = metrics.width + padding * 2;
            const nameHeight = screenNameLineHeight + padding * 2;
            
            const nameX = screenNameX - nameWidth / 2;
            const nameY = screenNameY - nameHeight / 2;
            
            // Clip to layer bounds so labels don't overflow the screen edge
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw WHITE background
            this.ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
            const snappedNameRect = this.snapRect(nameX, nameY, nameWidth, nameHeight);
            this.ctx.fillRect(snappedNameRect.x, snappedNameRect.y, snappedNameRect.width, snappedNameRect.height);

            // Draw BLACK text
            this.ctx.fillStyle = '#000000';
            this._fillText(screenName, this.snap(screenNameX), this.snap(screenNameY));

            this.ctx.restore();
            
            // Reset font for other labels
            this.ctx.font = `bold ${fontSize}px Arial`;
            if (this.viewMode === 'pixel-map') {
                currentY += screenNameHeight;
                if (centerLines.length > 0) {
                    currentY += 5; // Gap before other labels
                }
            } else {
                infoAnchorY = nameY + nameHeight + 5;
            }
        }
        
        // Render other center labels with dark background (regular style)
        if (centerLines.length > 0) {
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            
            // Measure text for background
            let maxWidth = 0;
            centerLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });
            
            const bgWidth = maxWidth + padding * 2;
            const bgHeight = centerLines.length * lineHeight + padding * 2;
            const bgX = centerX - bgWidth / 2;
            const bgY = this.viewMode === 'pixel-map' ? currentY : (infoAnchorY ?? currentY);
            
            // Clip to layer bounds so labels don't bleed through higher layers
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw dark background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedBgRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedBgRect.x, snappedBgRect.y, snappedBgRect.width, snappedBgRect.height);

            // Draw white text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            let yPos = bgY + padding + lineHeight / 2;
            centerLines.forEach(line => {
                this._fillText(line, this.snap(centerX), this.snap(yPos));
                yPos += lineHeight;
            });

            this.ctx.restore();
        }
        
        // Render Info label at bottom with background (fixed 14px screen size)
        if (infoLines.length > 0) {
            // Use world coordinates directly (transform is already applied)
            this.ctx.font = `${infoFontSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';
            
            // Measure text for background
            let maxWidth = 0;
            infoLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });
            
            const bgWidth = maxWidth + padding * 2;
            const bgHeight = infoLines.length * infoLineHeight + padding * 2;
            const bgX = centerX - bgWidth / 2;
            const bgY = bottomY - bgHeight - padding;
            
            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedInfoRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedInfoRect.x, snappedInfoRect.y, snappedInfoRect.width, snappedInfoRect.height);

            // Draw text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            let yPos = bgY + padding + infoLineHeight;
            infoLines.forEach(line => {
                this._fillText(line, this.snap(centerX), this.snap(yPos));
                yPos += infoLineHeight;
            });
        }
        
        // Restore context (remove clipping)
        this.ctx.restore();
    }
    
    renderLayerOffsets(layer) {
        // Only render offsets in pixel-map mode
        if (this.viewMode !== 'pixel-map') {
            return;
        }
        
        if (!layer.showOffsetTL && !layer.showOffsetTR && !layer.showOffsetBL && !layer.showOffsetBR) {
            return;
        }
        
        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        
        // Calculate actual corner positions
        // Since pixels are zero-indexed:
        // - Top-left starts at offset_x, offset_y (e.g., 0, 0)
        // - Top-right is at offset_x + width - 1 (e.g., 0 + 1024 - 1 = 1023)
        // - Bottom-left is at offset_y + height - 1 (e.g., 0 + 640 - 1 = 639)
        // - Bottom-right is at both -1 (e.g., 1023, 639)
        const tlX = bounds.x;
        const tlY = bounds.y;
        const trX = bounds.x + layerWidth - 1;  // Account for zero-indexing
        const trY = bounds.y;
        const blX = bounds.x;
        const blY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        const brX = bounds.x + layerWidth - 1;   // Account for zero-indexing
        const brY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        
        const corners = [
            { x: tlX, y: tlY, text: `X ${tlX}, Y ${tlY}`, show: layer.showOffsetTL, align: 'left', baseline: 'top', offsetX: 5, offsetY: 5 },
            { x: trX, y: trY, text: `X ${trX}, Y ${trY}`, show: layer.showOffsetTR, align: 'right', baseline: 'top', offsetX: -5, offsetY: 5 },
            { x: blX, y: blY, text: `X ${blX}, Y ${blY}`, show: layer.showOffsetBL, align: 'left', baseline: 'bottom', offsetX: 5, offsetY: -5 },
            { x: brX, y: brY, text: `X ${brX}, Y ${brY}`, show: layer.showOffsetBR, align: 'right', baseline: 'bottom', offsetX: -5, offsetY: -5 }
        ];
        
        // Use absolute pixel sizes - no scaling with zoom
        const fontSize = layer.labelsFontSize || 30;
        const padding = 4;
        
        this.ctx.font = `${fontSize}px Arial`;
        
        corners.forEach(corner => {
            if (!corner.show) return;
            
            // Skip if corner is outside raster bounds
            if (corner.x < 0 || corner.x >= this.rasterWidth || corner.y < 0 || corner.y >= this.rasterHeight) {
                return;
            }
            
            // Use world coordinates directly (transform is already applied)
            const worldX = corner.x + corner.offsetX;
            const worldY = corner.y + corner.offsetY;
            
            // Measure text for background
            const metrics = this.ctx.measureText(corner.text);
            const textWidth = metrics.width;
            const textHeight = fontSize;
            
            let bgX, bgY;
            if (corner.align === 'left') {
                bgX = worldX;
            } else {
                bgX = worldX - textWidth - padding * 2;
            }
            
            if (corner.baseline === 'top') {
                bgY = worldY;
            } else {
                bgY = worldY - textHeight - padding * 2;
            }
            
            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedCornerRect = this.snapRect(bgX, bgY, textWidth + padding * 2, textHeight + padding * 2);
            this.ctx.fillRect(snappedCornerRect.x, snappedCornerRect.y, snappedCornerRect.width, snappedCornerRect.height);
            
            // Draw text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            this.ctx.textAlign = corner.align;
            this.ctx.textBaseline = corner.baseline;
            
            const textX = corner.align === 'left' ? worldX + padding : worldX - padding;
            const textY = corner.baseline === 'top' ? worldY + padding : worldY - padding;

            this._fillText(corner.text, this.snap(textX), this.snap(textY));
        });
        
        this.ctx.restore();
    }

    renderCustomSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlow(layer)) return;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();

        const selection = window.app.customSelection || new Set();
        if (selection.size > 0) {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            selection.forEach(key => {
                const [row, col] = key.split(',').map(n => parseInt(n, 10));
                const panel = window.app.getPanelByRowCol(layer, row, col);
                if (!panel) return;
                this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            });
        }

        // No selection rectangle preview (per UX request)

        this.ctx.restore();
    }

    renderPowerSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPower(layer)) return;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();

        const selection = window.app.powerCustomSelection || new Set();
        if (selection.size > 0) {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            selection.forEach(key => {
                const [row, col] = key.split(',').map(n => parseInt(n, 10));
                const panel = window.app.getPanelByRowCol(layer, row, col);
                if (!panel) return;
                this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            });
        }

        this.ctx.restore();
    }

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
        this.ctx.restore();
    }

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
    }

    /**
     * Wiring perspective badge, "BACK VIEW" in screen-space corner when
     * Data Flow / Power are rendering in back perspective. Shown in both
     * interactive view and export so the printed map is unambiguous.
     * Front view shows nothing (clutter-free default; Front is implied).
     */
    renderPerspectiveBadge() {
        if (!this.isMirroredView()) return;
        const label = 'BACK VIEW';
        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        const padX = 18;
        const padY = 10;
        const fontPx = 16;
        this.ctx.font = `700 ${fontPx}px -apple-system, "Segoe UI", sans-serif`;
        const textWidth = this.ctx.measureText(label).width;
        const boxW = textWidth + padX * 2;
        const boxH = fontPx + padY * 2;
        // Top-right corner so it doesn't overlap the selection badge.
        const x = this.canvas.width - boxW - 20;
        const y = 20;
        this.ctx.fillStyle = 'rgba(217, 80, 0, 0.95)';
        this.ctx.beginPath();
        if (this.ctx.roundRect) this.ctx.roundRect(x, y, boxW, boxH, 6);
        else this.ctx.rect(x, y, boxW, boxH);
        this.ctx.fill();
        this.ctx.fillStyle = '#fff';
        this.ctx.textBaseline = 'middle';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(label, x + padX, y + boxH / 2);
        this.ctx.restore();
    }

    renderCustomActivePortBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlow(layer)) return;
        const portNum = layer.customPortIndex || 1;
        const label = window.app.getPortLabelText(layer, portNum, 'primary');
        const committedCount = this._getCustomPortPanelCount(layer, portNum);
        const selectedCount = (window.app.customSelection && window.app.customSelection.size) || 0;
        this._drawActiveBadge(label, committedCount, selectedCount, 'rgba(0, 255, 0, 0.9)');
    }

    renderPowerActiveCircuitBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPower(layer)) return;
        const circuitNum = layer.powerCustomIndex || 1;
        const label = window.app.getPowerCircuitLabel(layer, circuitNum);
        const committedCount = this._getCustomPowerCircuitPanelCount(layer, circuitNum);
        const selectedCount = (window.app.powerCustomSelection && window.app.powerCustomSelection.size) || 0;
        this._drawActiveBadge(label, committedCount, selectedCount, 'rgba(0, 255, 102, 0.9)');
    }

    _getCustomPortPanelCount(layer, portNum) {
        const path = (layer.customPortPaths && layer.customPortPaths[portNum]) || [];
        if (!Array.isArray(path)) return 0;
        // Filter to panels that still exist and are not hidden
        return path.reduce((n, pos) => {
            if (!window.app || typeof window.app.getPanelByRowCol !== 'function') return n + 1;
            const panel = window.app.getPanelByRowCol(layer, pos.row, pos.col);
            return n + (panel && !panel.hidden ? 1 : 0);
        }, 0);
    }

    _getCustomPowerCircuitPanelCount(layer, circuitNum) {
        const path = (layer.powerCustomPaths && layer.powerCustomPaths[circuitNum]) || [];
        if (!Array.isArray(path)) return 0;
        return path.reduce((n, pos) => {
            if (!window.app || typeof window.app.getPanelByRowCol !== 'function') return n + 1;
            const panel = window.app.getPanelByRowCol(layer, pos.row, pos.col);
            return n + (panel && !panel.hidden ? 1 : 0);
        }, 0);
    }

    // Shared renderer for the active-port / active-circuit badge in the
    // top-left of the canvas when a custom flow is being built.
    //  - `committed` = panels already assigned to this port/circuit
    //  - `selected`  = panels currently highlighted by a drag-select but
    //    not yet applied. Shown in yellow only when > 0 so the user can
    //    distinguish "locked in" vs "pending" at a glance.
    _drawActiveBadge(label, committed, selected, labelColor) {
        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);

        const x = 20;
        const y = 20;
        const fontSize = 72;
        const countFontSize = Math.round(fontSize * 0.5);
        const padding = 12;
        const gap = 14;
        const pillGap = 8;
        const pillPadX = 10;
        const pillPadY = 6;

        // Measure label
        this.ctx.font = `bold ${fontSize}px Arial`;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';
        const labelW = this.ctx.measureText(label).width;

        // Measure pills
        this.ctx.font = `bold ${countFontSize}px Arial`;
        const committedText = `${committed} on port`;
        const committedW = this.ctx.measureText(committedText).width;
        const committedPillW = committedW + pillPadX * 2;
        const pillH = countFontSize + pillPadY * 2;

        const showSelected = selected > 0;
        const selectedText = `+${selected} selected`;
        const selectedW = showSelected ? this.ctx.measureText(selectedText).width : 0;
        const selectedPillW = showSelected ? selectedW + pillPadX * 2 : 0;

        // Outer box dimensions
        const pillsW = committedPillW + (showSelected ? pillGap + selectedPillW : 0);
        const boxW = labelW + gap + pillsW + padding * 2;
        const boxH = fontSize + padding * 2;

        // Background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
        this.ctx.fillRect(x, y, boxW, boxH);

        // Label (big)
        this.ctx.font = `bold ${fontSize}px Arial`;
        this.ctx.fillStyle = labelColor;
        this.ctx.fillText(label, x + padding, y + padding);

        // Committed pill (white)
        const pillY = y + (boxH - pillH) / 2;
        let pillX = x + padding + labelW + gap;
        this.ctx.fillStyle = committed > 0 ? 'rgba(255, 255, 255, 0.18)' : 'rgba(255, 255, 255, 0.08)';
        this._roundRect(pillX, pillY, committedPillW, pillH, 8);
        this.ctx.fill();
        this.ctx.font = `bold ${countFontSize}px Arial`;
        this.ctx.fillStyle = committed > 0 ? '#ffffff' : 'rgba(255, 255, 255, 0.7)';
        this.ctx.fillText(committedText, pillX + pillPadX, pillY + pillPadY - 2);

        // Selected pill (yellow), only when drag-select has picked panels
        if (showSelected) {
            pillX += committedPillW + pillGap;
            this.ctx.fillStyle = 'rgba(255, 204, 0, 0.85)';
            this._roundRect(pillX, pillY, selectedPillW, pillH, 8);
            this.ctx.fill();
            this.ctx.fillStyle = '#000000';
            this.ctx.fillText(selectedText, pillX + pillPadX, pillY + pillPadY - 2);
        }

        this.ctx.restore();
    }

    _roundRect(x, y, w, h, r) {
        const radius = Math.min(r, w / 2, h / 2);
        this.ctx.beginPath();
        this.ctx.moveTo(x + radius, y);
        this.ctx.lineTo(x + w - radius, y);
        this.ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
        this.ctx.lineTo(x + w, y + h - radius);
        this.ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
        this.ctx.lineTo(x + radius, y + h);
        this.ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
        this.ctx.lineTo(x, y + radius);
        this.ctx.quadraticCurveTo(x, y, x + radius, y);
        this.ctx.closePath();
    }
}

window.CanvasRenderer = CanvasRenderer;
