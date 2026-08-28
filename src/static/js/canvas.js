// v0.8.8.x: build a canvas-text font shorthand using the project-wide font
// (preferences.font, defaults to Arial). Use this in place of hardcoded
// 'Arial' literals so the user's chosen font drives every on-canvas label.
function projectFontFamily() {
    return (window.app && typeof window.app.getProjectFont === 'function')
        ? window.app.getProjectFont() : 'Arial';
}

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
        // The 'both' name display's group headline drag (see _groupNameMode).
        this.isDraggingGroupName = false;
        this._dragGroupNameGroup = null;
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
        // mouseup listens on the WINDOW, not the canvas. A drag that starts
        // on the canvas routinely ends over the sidebar, a toolbar, or
        // outside the browser window entirely; a canvas-scoped listener
        // never heard that release, so whichever flag the mousedown had
        // armed (space/middle pan, shift layer drag, shift screen-name
        // drag, alt paint, canvas drag, the marquees) stayed latched, and
        // the next time the cursor crossed the raster mousemove resumed the
        // drag with no button held. Every branch of handleMouseUp is gated
        // on state only a canvas mousedown can set, so hearing every
        // release in the document is safe: with nothing in flight it falls
        // straight through. This also retires the old window-level
        // "clear stuck selection box" fallback, which knew how to CANCEL
        // the two marquee flags but nothing else - the full finalizer now
        // runs for off-canvas releases, so a marquee released past the
        // edge commits exactly like one released on the canvas.
        window.addEventListener('mouseup', this.handleMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.handleWheel.bind(this));
        this.canvas.addEventListener('contextmenu', this.handleContextMenu.bind(this));
        document.addEventListener('keydown', this.handleKeyDown.bind(this));
        document.addEventListener('keyup', this.handleKeyUp.bind(this));
        // Focus loss (cmd-tab, window switch, tab hide) delivers the
        // matching keyup/mouseup to some OTHER app, never to us - see
        // _releaseTransientInput.
        window.addEventListener('blur', () => this._releaseTransientInput());
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) this._releaseTransientInput();
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
        // v0.8.6: perspective is fully per-canvas. The legacy global-mirror
        // path is gone (each canvas applies its own mirror inside the render
        // loop). This now answers "is ANY visible canvas mirrored in the
        // current view", used to gate the BACK VIEW badge layer and to
        // short-circuit hit-test unmirror when nothing is mirrored.
        if (this.viewMode !== 'data-flow' && this.viewMode !== 'power') return false;
        if (!window.app || !window.app.project) return false;
        const proj = window.app.project;
        const arr = Array.isArray(proj.canvases) ? proj.canvases : [];
        if (arr.length === 0) {
            // Pre-Slice-1 legacy projects: read project-root field.
            const key = this.viewMode === 'data-flow' ? 'data_flow_perspective' : 'power_perspective';
            return proj[key] === 'back';
        }
        return arr.some(c => c && c.visible !== false && this._isCanvasMirrored(c));
    }

    /**
     * v0.8.6: per-canvas perspective check. Each canvas can independently
     * be in Front or Back view. Used by the per-canvas mirror transform
     * applied during render and by hit-testing.
     */
    _isCanvasMirrored(canvas) {
        if (!canvas) return false;
        if (this.viewMode === 'data-flow') return canvas.data_flow_perspective === 'back';
        if (this.viewMode === 'power') return canvas.power_perspective === 'back';
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
        // v0.9.3: on Data/Power a rotated screen keeps its text upright by
        // counter-rotating each label about its anchor.
        const upright = this._keepTextUpright && this._activeRotationRad;
        if (this._mirror || upright) {
            this.ctx.save();
            this.ctx.translate(x, y);
            if (upright) this.ctx.rotate(-this._activeRotationRad);
            if (this._mirror) this.ctx.scale(-1, 1);
            if (maxWidth !== undefined) this.ctx.fillText(text, 0, 0, maxWidth);
            else this.ctx.fillText(text, 0, 0);
            this.ctx.restore();
        } else {
            if (maxWidth !== undefined) this.ctx.fillText(text, x, y, maxWidth);
            else this.ctx.fillText(text, x, y);
        }
    }

    _strokeText(text, x, y, maxWidth) {
        const upright = this._keepTextUpright && this._activeRotationRad;
        if (this._mirror || upright) {
            this.ctx.save();
            this.ctx.translate(x, y);
            if (upright) this.ctx.rotate(-this._activeRotationRad);
            if (this._mirror) this.ctx.scale(-1, 1);
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
        // v0.9.3: while a screen is rotated (Pixel Map / Cabinet ID) the raster
        // rect would be repositioned in the rotated space and would trim the
        // rotated content; skip it (the export canvas edge still bounds output).
        if (this._layerRotating) return;
        const dx = this._renderDx || 0;
        const dy = this._renderDy || 0;
        this.ctx.beginPath();
        this.ctx.rect(-dx, -dy, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
    }

    // v0.9.3: the screen's rotation for the CURRENT view, 0/90/180/270, only in
    // Pixel Map / Cabinet ID (other views never rotate).
    _layerRotationDeg(layer) {
        // v0.9.3: rotation applies to every screen view (Pixel Map, Cabinet ID,
        // Show Look, Data, Power). On Data/Power the panels/arrows rotate but the
        // text labels are kept upright, see _fillText / _keepTextUpright.
        return ((((Number(layer && layer.rotation) || 0) % 360) + 360) % 360);
    }

    // v0.9.3: rotation geometry for a screen. Rotates AROUND THE SCREEN CENTER
    // (rotate "in place"), then clamps the rotated footprint back inside the
    // raster so it never renders off-canvas. `bounds` lets callers pass the
    // active-view bounds; defaults to processor bounds. Every rotation consumer
    // (render transform, footprint bounds, hit-test) goes through this so they
    // always agree.
    _layerRotationGeom(layer, bounds) {
        const deg = this._layerRotationDeg(layer);
        const b = bounds || this.getLayerBounds(layer);
        const w = b.width, h = b.height;
        const cx = b.x + w / 2, cy = b.y + h / 2;        // pivot = screen center
        const swap = (deg === 90 || deg === 270);
        const fw = swap ? h : w;                          // footprint dims
        const fh = swap ? w : h;
        // Rotate in place, the footprint may extend off-canvas; off-canvas
        // content is clipped at render time, never repositioned.
        return { deg, cx, cy, fw, fh, x: cx - fw / 2, y: cy - fh / 2 };
    }

    // Apply the screen's rotation (Pixel Map / Cabinet ID): rotate in place
    // about the screen center.
    // Returns true if a rotation was applied, the caller MUST ctx.restore().
    _beginLayerRotation(layer) {
        const g = this._layerRotationGeom(layer);
        if (g.deg !== 90 && g.deg !== 180 && g.deg !== 270) return false;
        this.ctx.save();
        this.ctx.translate(g.cx, g.cy);
        this.ctx.rotate(g.deg * Math.PI / 180);
        this.ctx.translate(-g.cx, -g.cy);
        return true;
    }

    // Axis-aligned footprint of a (possibly rotated) screen after the in-raster
    // clamp; width/height swap for 90/270. Equals the bounds when unrotated.
    getLayerFootprintBounds(layer) {
        const g = this._layerRotationGeom(layer);
        return { x: g.x, y: g.y, width: g.fw, height: g.fh };
    }

    getLayerFootprintInActiveView(layer) {
        const g = this._layerRotationGeom(layer, this.getLayerBoundsInActiveView(layer));
        return { x: g.x, y: g.y, width: g.fw, height: g.fh };
    }

    // v0.9.3: how far the rotated footprint's top-left sits from the screen's
    // stored offset (0 unless rotated 90/270). Screen Info shows offset + this so
    // the displayed X,Y matches the rotated screen's actual top-left; edits are
    // converted back. Uses layer.rotation directly (not the current view).
    getLayerFootprintOffset(layer) {
        const deg = (((Number(layer && layer.rotation) || 0) % 360) + 360) % 360;
        if (deg !== 90 && deg !== 270) return { dx: 0, dy: 0 };
        const b = this.getLayerBounds(layer);
        return { dx: (b.width - b.height) / 2, dy: (b.height - b.width) / 2 };
    }

    // Map a point from rotated display space back to the screen's unrotated
    // content space, for panel hit-testing under rotation. Identity if unrotated.
    _unrotatePointForLayer(px, py, layer) {
        const g = this._layerRotationGeom(layer);
        if (g.deg !== 90 && g.deg !== 180 && g.deg !== 270) return { x: px, y: py };
        // inverse of the in-place center rotation
        const dx = px - g.cx;
        const dy = py - g.cy;
        const rad = -g.deg * Math.PI / 180;
        const cos = Math.cos(rad), sin = Math.sin(rad);
        return { x: g.cx + (dx * cos - dy * sin), y: g.cy + (dx * sin + dy * cos) };
    }

    // v0.11.0: the forward direction of _unrotatePointForLayer - a point in the
    // screen's own unrotated content space, mapped to where the rotated render
    // actually puts it. The per-layer render pass never needs this (it rotates
    // the whole ctx and keeps drawing in unrotated coords), but the cross-member
    // path overlay does: it draws OUTSIDE any one member's transform, so it has
    // to bake each member's own rotation into the points it hands the renderer.
    // Identity if unrotated, so an unrotated project pays nothing for it.
    _rotatePointForLayer(px, py, layer) {
        return this._drawnPoint(this._layerDrawFrame(layer), px, py);
    }

    // ── THE ONE MAPPING: a member's own grid -> where that member DRAWS ──────
    //
    // v0.11.0: rotation used to be applied at draw time only - the per-layer
    // render pass rotates the whole ctx and keeps drawing in unrotated coords -
    // so anything that RANKED or BOUNDED a member (the wall lattice, the group's
    // union bounds, the drag-select highlight) silently worked in unrotated
    // space and was then drawn inside somebody's rotation transform. On a
    // rotated member that puts the answer a cabinet - or a whole wall - away
    // from the thing it names.
    //
    // `_layerDrawFrame` is that member's draw frame computed ONCE (its rotation
    // pivot and its Show Look render offset); `_drawnPanelRect` maps one cabinet
    // through it. Every consumer goes through this pair so they cannot drift,
    // and it is a strict identity for an unrotated screen with no show offset -
    // which is why an ungrouped, unrotated project pays nothing and changes by
    // nothing.
    //
    // Computing the frame once matters: _layerRotationGeom calls getLayerBounds,
    // which is O(panels), so a per-panel call would make any whole-screen sweep
    // quadratic.
    _layerDrawFrame(layer) {
        const g = this._layerRotationGeom(layer);
        const rot = (g.deg === 90 || g.deg === 180 || g.deg === 270);
        const rad = g.deg * Math.PI / 180;
        return {
            deg: g.deg,
            rot,
            swap: (g.deg === 90 || g.deg === 270),
            cx: g.cx,
            cy: g.cy,
            // Kept exact (not Math.cos of a right angle) when there is no
            // rotation, so the unrotated path is bit-for-bit the identity.
            cos: rot ? Math.cos(rad) : 1,
            sin: rot ? Math.sin(rad) : 0,
            off: this.getLayerRenderOffset(layer),
        };
    }

    // A point in the member's own unrotated content space, rotated the way the
    // render pass rotates it. Does NOT add the render offset - callers that draw
    // inside the per-layer translate must not have it added twice.
    _drawnPoint(frame, px, py) {
        if (!frame.rot) return { x: px, y: py };
        const dx = px - frame.cx;
        const dy = py - frame.cy;
        return {
            x: frame.cx + (dx * frame.cos - dy * frame.sin),
            y: frame.cy + (dx * frame.sin + dy * frame.cos),
        };
    }

    // One cabinet as the {x, y, width, height} rect it is actually DRAWN at,
    // including that member's own rotation and its own Show Look offset.
    //
    // Under a 90/270 rotation the cabinet's footprint swaps width and height;
    // the rect is rebuilt around the ROTATED CENTRE so `x + width / 2` - the
    // thing the arrow code and the lattice both ask for - still names the middle
    // of the cabinet as drawn.
    _drawnPanelRect(frame, panel) {
        const pw = Number(panel.width) || 0;
        const ph = Number(panel.height) || 0;
        const w = frame.swap ? ph : pw;
        const h = frame.swap ? pw : ph;
        const c = this._drawnPoint(frame,
            (Number(panel.x) || 0) + pw / 2,
            (Number(panel.y) || 0) + ph / 2);
        return {
            x: c.x + frame.off.dx - w / 2,
            y: c.y + frame.off.dy - h / 2,
            width: w,
            height: h,
            hidden: false,
            row: panel.row,
            col: panel.col,
        };
    }

    // Which of a member's grid axes runs along the DRAWN x axis, and which along
    // the drawn y. A 90/270 turn trades them: that member's rows become the
    // wall's columns. Used to group cabinets into drawn columns/rows before
    // their positions are ranked, so a half-tile still shares its slot with the
    // full cabinets beside it.
    _drawnColKey(frame, panel) { return frame.swap ? panel.row : panel.col; }
    _drawnRowKey(frame, panel) { return frame.swap ? panel.col : panel.row; }

    // Undo a layer's own rotation for the duration of `fn`, WITHOUT its own
    // save/restore - the caller's surrounding ctx.save() pops it. Returns true
    // if anything was applied.
    //
    // The render loop wraps each member's pass in _beginLayerRotation, which
    // turns the ctx about THAT member's centre. Anything measured in the WALL's
    // frame (a group's union bounds) must not be turned about one member's
    // centre, so it cancels the rotation first and draws in the same space it
    // measured in.
    _unrotateLayerInPlace(layer) {
        if (!this._layerRotating) return false;
        const g = this._layerRotationGeom(layer);
        if (g.deg !== 90 && g.deg !== 180 && g.deg !== 270) return false;
        this.ctx.translate(g.cx, g.cy);
        this.ctx.rotate(-g.deg * Math.PI / 180);
        this.ctx.translate(-g.cx, -g.cy);
        return true;
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
    
    // When the canvas under the cursor is in Back perspective, its content
    // is flipped horizontally for display only. Mouse coordinates are still
    // in un-mirrored screen space, so we have to flip them back into layer
    // coordinates before any hit-testing / drag math. v0.8.6: per-canvas
    //, find the canvas under the cursor and mirror around its own right
    // edge. Points outside any canvas (or over an unmirrored canvas) pass
    // through unchanged.
    _unmirrorWorldX(worldX, worldY) {
        if (!this.isMirroredView()) return worldX;
        // Legacy single-canvas projects: keep the old workspace-bbox mirror.
        const arr = (window.app && window.app.project && window.app.project.canvases) || [];
        if (!Array.isArray(arr) || arr.length === 0) {
            const k = this._mirrorAxisX();
            return k - worldX;
        }
        if (worldY == null) {
            // Caller didn't pass worldY (legacy callsite). Fall back to the
            // active canvas, since most interactions happen in it.
            const active = (window.app && typeof window.app._activeCanvas === 'function')
                ? window.app._activeCanvas() : null;
            if (active && this._isCanvasMirrored(active)) {
                const ws = this._canvasWorkspace(active);
                const useShow = this.isShowLookView();
                const w = (useShow && active.show_raster_width) || active.raster_width || 0;
                return 2 * ws.wx + w - worldX;
            }
            return worldX;
        }
        const c = this._canvasAtPoint(worldX, worldY);
        if (!c || !this._isCanvasMirrored(c)) return worldX;
        const ws = this._canvasWorkspace(c);
        const useShow = this.isShowLookView();
        const w = (useShow && c.show_raster_width) || c.raster_width || 0;
        return 2 * ws.wx + w - worldX;
    }

    /**
     * Legacy mirror axis for pre-Slice-1 single-canvas projects only.
     * Multi-canvas projects (v0.8+) mirror per-canvas around each canvas's
     * own right edge, see _unmirrorWorldX and the per-canvas mirror block
     * inside the render loop.
     */
    _mirrorAxisX() {
        const bb = this._workspaceBounds();
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
            // v0.8.5.3: Show Look uses its own workspace position when set.
            const ws = this._canvasWorkspace(c);
            const x = ws.wx;
            const y = ws.wy;
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
            // v0.8.5.3: Show Look uses its own workspace position when set.
            const ws = this._canvasWorkspace(c);
            const x = ws.wx;
            const y = ws.wy;
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
        // Last known cursor position, for the focus-loss finalizer
        // (_releaseTransientInput) which has no event to read it from.
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldY = (mouseY - this.panY) / this.zoom;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom, worldY);

        // v0.8.7.7: plain-click directly on a screen-name label starts a
        // screen-name drag (no modifier needed). This is the universal
        // "grab the label" gesture across every tab, Pixel Map, Cabinet
        // ID, Data Flow, Power. The label rect is cached on the layer by
        // renderLayerLabels at draw time so this hit-test stays in sync
        // with what's drawn. Only checks the active currentLayer's label
        //, clicking some other layer's label still needs Shift / etc.
        if (e.button === 0 && !this.spacePressed && !e.altKey && !e.shiftKey
                && !e.metaKey && !e.ctrlKey
                && window.app && window.app.currentLayer
                && (window.app.currentLayer.type || 'screen') === 'screen'
                // v0.8.7.7.1: don't fire on a hidden layer even if the
                // hit-rect cache is stale from before the visibility
                // toggle. toggleLayerVisibility now clears the cache too,
                // but this guard makes the rule explicit.
                && window.app.currentLayer.visible !== false) {
            const _r = window.app.currentLayer._screenNameHitRect;
            if (_r && _r.viewMode === this.viewMode
                    && worldX >= _r.x1 && worldX <= _r.x2
                    && worldY >= _r.y1 && worldY <= _r.y2) {
                this.isDraggingScreenName = true;
                this.dragScreenNameStartX = worldX;
                this.dragScreenNameStartY = worldY;
                let currentOffsetX = 0;
                let currentOffsetY = 0;
                const layer = window.app.currentLayer;
                if (this.viewMode === 'pixel-map') {
                    currentOffsetX = layer.screenNameOffsetXPixelMap || 0;
                    currentOffsetY = layer.screenNameOffsetYPixelMap || 0;
                } else if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                } else if (this.viewMode === 'show-look') {
                    currentOffsetX = layer.screenNameOffsetXShowLook || 0;
                    currentOffsetY = layer.screenNameOffsetYShowLook || 0;
                }
                this.screenNameStartOffset = { x: currentOffsetX, y: currentOffsetY };
                this.canvas.style.cursor = 'move';
                return;
            }
        }

        // The 'both' name display adds a second grabbable label: the group's
        // headline. Checked AFTER the member-name rect above so the more
        // specific label wins where the two overlap. The rect is cached on
        // the group's cfg member (resolved through the plan, so any selected
        // member can grab it); the offsets ride the group object itself.
        if (e.button === 0 && !this.spacePressed && !e.altKey && !e.shiftKey
                && !e.metaKey && !e.ctrlKey
                && window.app && window.app.currentLayer
                && (window.app.currentLayer.type || 'screen') === 'screen'
                && window.app.currentLayer.visible !== false
                && this._groupNameMode() === 'both') {
            const _plan = this._groupLabelPlan(window.app.currentLayer);
            const _gr = _plan && _plan.cfg._groupNameHitRect;
            if (_gr && _gr.viewMode === this.viewMode
                    && worldX >= _gr.x1 && worldX <= _gr.x2
                    && worldY >= _gr.y1 && worldY <= _gr.y2) {
                this.isDraggingGroupName = true;
                this._dragGroupNameGroup = _plan.group;
                this.dragScreenNameStartX = worldX;
                this.dragScreenNameStartY = worldY;
                const _f = this._screenNameOffsetFields();
                this.screenNameStartOffset = {
                    x: _plan.group[_f.x] || 0,
                    y: _plan.group[_f.y] || 0,
                };
                this.canvas.style.cursor = 'move';
                return;
            }
        }

        // Slice 5: dragging a canvas's dashed outline edge repositions
        // the canvas in the workspace. Must be checked BEFORE the Slice 4
        // panel/canvas-activate block so edge-drag wins over body-click
        // activation. Skipped for pan (space), shift, and alt, those are
        // existing drag/paint behaviors. Inside the canvas body still
        // falls through to Slice 4.
        // v0.8.3: canvas-edge drag is only meaningful on the layout-driving
        // tabs (Pixel Map = processor layout, Show Look = stage layout).
        // On Cabinet ID / Data / Power the canvas position is derived from
        // those two and grabbing the dashed outline there was confusing.
        const canvasDragAllowed = (this.viewMode === 'pixel-map' || this.viewMode === 'show-look');
        if (canvasDragAllowed && e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            const edgeCanvas = this._canvasEdgeAtPoint(worldX, worldY);
            if (edgeCanvas) {
                this.isDraggingCanvas = true;
                this.draggingCanvasId = edgeCanvas.id;
                this.canvasDragStartX = worldX;
                this.canvasDragStartY = worldY;
                // v0.8.5.3: drag uses the active view's workspace position
                // (Show Look has its own show_workspace_x/y).
                {
                    const _ws = this._canvasWorkspace(edgeCanvas);
                    this.canvasDragStartWX = _ws.wx;
                    this.canvasDragStartWY = _ws.wy;
                }
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
        // Also skipped for Cmd/Ctrl: that is the selection-TOGGLE gesture,
        // resolved on mouse-up. Running the plain-click activate/promote here
        // would replace the multi-selection with the clicked layer before the
        // toggle ever read it (selectLayer resets selectedLayerIds), and
        // setActiveCanvas without preserveSelection would cull anything
        // selected on another canvas. The toggle path activates the right
        // canvas itself, with preserveSelection.
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey
                && !e.metaKey && !e.ctrlKey) {
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
                        && !this._isCustomPathGesture(layer)
                        && typeof window.app.selectLayer === 'function') {
                        // selectLayer takes the layer OBJECT, not the id
                        // (the !layer.id guard rejects raw integers).
                        this._selectLayerFromCanvas(layer);
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
            // v0.8.3: text and image layers don't have per-tab screen-name
            // labels, so shift+drag on them always moves the whole layer
            // regardless of view mode.
            if (window.app && window.app.currentLayer) {
                const layerType = window.app.currentLayer.type || 'screen';
                const isScreenLayer = layerType === 'screen';
                if (isScreenLayer && this.viewMode !== 'pixel-map' && this.viewMode !== 'show-look') {
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;

                    let currentOffsetX = 0;
                    let currentOffsetY = 0;

                    if (this.viewMode === 'pixel-map') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPixelMap || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPixelMap || 0;
                    } else if (this.viewMode === 'cabinet-id') {
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

        // Custom data / power: arm the PATH marquee only when the press lands
        // on a cabinet this gesture can actually draw on.
        //
        // These two branches used to arm anywhere on the canvas and then
        // `return`, with no position test at all - so for every plain press
        // while custom mode was on, the layer marquee further down was
        // unreachable. You could not rubber-band several screens without
        // leaving custom mode first. Pixel Map has always done this properly
        // (hit-test, otherwise fall through); this brings custom mode in line.
        if (e.button === 0 && window.app && window.app.currentLayer && this.viewMode === 'data-flow') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlow(layer) && this._customDrawStartsInScope(worldX, worldY)) {
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
            if (window.app.isCustomPower(layer) && this._customDrawStartsInScope(worldX, worldY)) {
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
            // Same for custom data / power: reaching here means the press
            // landed outside every screen this path can draw on, so the panels
            // highlighted for the port or circuit are no longer the subject of
            // what the user is doing. Leaving them lit made the next click
            // inside the screen extend a selection the user thought they had
            // dropped when they clicked away.
            if (this.viewMode === 'data-flow' && window.app
                    && window.app.customSelection && window.app.customSelection.size > 0) {
                window.app.clearCustomSelection();
            }
            if (this.viewMode === 'power' && window.app
                    && window.app.powerCustomSelection && window.app.powerCustomSelection.size > 0) {
                window.app.clearPowerCustomSelection();
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
                // v0.8.3: text and image layers always do whole-layer move on
                // any tab (they don't have per-tab screen-name labels).
                const layerType = window.app.currentLayer.type || 'screen';
                const isScreenLayer = layerType === 'screen';
                const wholeLayerMove = !isScreenLayer
                    || this.viewMode === 'pixel-map'
                    || this.viewMode === 'show-look';
                if (wholeLayerMove) {
                    const selected = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    const uniqueSelected = [];
                    const seenIds = new Set();
                    selected.forEach(layer => {
                        if (!layer || seenIds.has(layer.id)) return;
                        seenIds.add(layer.id);
                        uniqueSelected.push(layer);
                    });
                    // v0.11.0: a group moves as one screen, so any selected
                    // member pulls in its peers (and puts them in the app's
                    // selection, so mouseup persists every layer that moved).
                    // Relative offsets are preserved for free: the drag applies
                    // ONE delta to every entry in dragLayerOffsets below.
                    this._addGroupPeersToDrag(uniqueSelected);
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
                this._selectLayerFromCanvas(layer);
            } else {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel) {
                    const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                    if (panelLayer) {
                        this._selectLayerFromCanvas(panelLayer);
                    }
                }
            }
        } else if (e.button === 0) {
            if (window.app) {
                const layer = this.getLayerAt(worldX, worldY);
                if (layer) {
                    this._selectLayerFromCanvas(layer);
                } else {
                    const clickedPanel = this.getPanelAt(worldX, worldY);
                    if (clickedPanel) {
                        const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        if (panelLayer) {
                            this._selectLayerFromCanvas(panelLayer);
                        }
                    }
                }
            }
        }
    }
    
    handleMouseMove(e) {
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldY = (mouseY - this.panY) / this.zoom;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom, worldY);

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
                    // v0.8.5.3: Show Look canvas drag writes show_workspace
                    // so Pixel Map's workspace stays put.
                    if (this.isShowLookView()) {
                        c.show_workspace_x = nextX;
                        c.show_workspace_y = nextY;
                    } else {
                        c.workspace_x = nextX;
                        c.workspace_y = nextY;
                    }
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
            // currentLayer is the OWNER of the port/circuit being drawn, not a
            // limit on what the rect may cover: since v0.11.0 these two walk
            // every member the owner's path can legally reach, so a live drag
            // lights up cabinets on the next screen of the wall as it crosses
            // onto it (see the mouse-up twin below).
            // BOTH branches test viewMode. The data branch used to test only
            // isCustomFlow, so in POWER view a screen that was also on a custom
            // DATA pattern took the first branch and filled the data selection
            // instead - and since the power overlay reads the power set, the
            // drag looked like it was doing nothing until mouse-up (which has
            // always gated on viewMode) finally filled the right one. A screen
            // in a group is always in that state, because the flow pattern is
            // shared across members.
            if (window.app && window.app.currentLayer && this.viewMode === 'data-flow'
                && window.app.isCustomFlow(window.app.currentLayer)) {
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
                    // v0.8.5: in Show Look / Data / Power the cross-canvas
                    // hint compares against the layer's effective show
                    // canvas, matching where it renders.
                    const _primaryCid = this._effectiveLayerCanvasId(_primary);
                    this._crossCanvasDropTarget = (_tgt && _tgt.id !== _primaryCid) ? _tgt : null;
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

                // v0.8.7.2: screen-name offsets are stored in *visual* (viewer)
                // space so toggling Front<->Back keeps the label visually in
                // place instead of mirror-jumping across the screen. When the
                // active layer's canvas is mirrored, the mouse delta in world
                // (un-mirrored) space points the opposite direction from what
                // the user sees, so negate X here to keep "drag right = +X
                // visually" regardless of perspective.
                const _mirrorActive = (() => {
                    const layer = window.app && window.app.currentLayer;
                    if (!layer || typeof this._effectiveLayerCanvasId !== 'function') return false;
                    const cid = this._effectiveLayerCanvasId(layer);
                    const arr = window.app.project && window.app.project.canvases;
                    if (!Array.isArray(arr)) return false;
                    const c = arr.find(c => c && c.id === cid);
                    return !!(c && this._isCanvasMirrored && this._isCanvasMirrored(c));
                })();
                const _visualDx = _mirrorActive ? -dx : dx;

                let newOffsetX = this.screenNameStartOffset.x + _visualDx;
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
                if (this.viewMode === 'pixel-map') {
                    layer.screenNameOffsetXPixelMap = newOffsetX;
                    layer.screenNameOffsetYPixelMap = newOffsetY;
                } else if (this.viewMode === 'cabinet-id') {
                    layer.screenNameOffsetXCabinet = newOffsetX;
                    layer.screenNameOffsetYCabinet = newOffsetY;
                } else if (this.viewMode === 'data-flow') {
                    layer.screenNameOffsetXDataFlow = newOffsetX;
                    layer.screenNameOffsetYDataFlow = newOffsetY;
                } else if (this.viewMode === 'power') {
                    layer.screenNameOffsetXPower = newOffsetX;
                    layer.screenNameOffsetYPower = newOffsetY;
                } else if (this.viewMode === 'show-look') {
                    layer.screenNameOffsetXShowLook = newOffsetX;
                    layer.screenNameOffsetYShowLook = newOffsetY;
                }

                this.render();
            }
        } else if (this.isDraggingGroupName) {
            // The 'both' display's group headline drag: same visual-space
            // delta, mirror compensation and magnetic-snap treatment as a
            // screen name's, measured against the group's union bounds and
            // stored on the group object under the per-view field names.
            const group = this._dragGroupNameGroup;
            const layer = window.app && window.app.currentLayer;
            if (group && layer) {
                const plan = this._groupLabelPlan(layer);
                const bounds = plan
                    ? this._groupUnionBounds(plan.members, plan.host)
                    : this.getLayerBoundsInActiveView(layer);

                const dx = worldX - this.dragScreenNameStartX;
                const dy = worldY - this.dragScreenNameStartY;
                const _mirrorActive = (() => {
                    if (typeof this._effectiveLayerCanvasId !== 'function') return false;
                    const cid = this._effectiveLayerCanvasId(layer);
                    const arr = window.app.project && window.app.project.canvases;
                    if (!Array.isArray(arr)) return false;
                    const c = arr.find(c => c && c.id === cid);
                    return !!(c && this._isCanvasMirrored && this._isCanvasMirrored(c));
                })();
                const _visualDx = _mirrorActive ? -dx : dx;

                let newOffsetX = this.screenNameStartOffset.x + _visualDx;
                let newOffsetY = this.screenNameStartOffset.y + dy;

                if (this.magneticSnap) {
                    const snapThreshold = 20;
                    const snapPositionsX = [-bounds.width / 2, 0, bounds.width / 2];
                    const snapPositionsY = [-bounds.height / 2, 0, bounds.height / 2];
                    for (const snapX of snapPositionsX) {
                        if (Math.abs(newOffsetX - snapX) < snapThreshold) {
                            newOffsetX = snapX;
                            break;
                        }
                    }
                    for (const snapY of snapPositionsY) {
                        if (Math.abs(newOffsetY - snapY) < snapThreshold) {
                            newOffsetY = snapY;
                            break;
                        }
                    }
                }

                const f = this._screenNameOffsetFields();
                group[f.x] = newOffsetX;
                group[f.y] = newOffsetY;

                this.render();
            }
        }

        if (this.spacePressed && !this.isDragging) {
            this.canvas.style.cursor = 'grab';
        } else if (!this.isDragging && !this.isDraggingLayer && !this.isDraggingScreenName && !this.isDraggingGroupName && !this.isDraggingCanvas) {
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
                    // v0.8.5.3: persist to the right field per view.
                    const isShow = this.isShowLookView();
                    const _ws = this._canvasWorkspace(c);
                    const wx = Math.round(_ws.wx);
                    const wy = Math.round(_ws.wy);
                    if (isShow) {
                        c.show_workspace_x = wx;
                        c.show_workspace_y = wy;
                    } else {
                        c.workspace_x = wx;
                        c.workspace_y = wy;
                    }
                    if (typeof window.app.updateCanvas === 'function') {
                        // updateCanvas now snapshots POST-mutation state in
                        // its server-response .then() so a single Cmd+Z reverts
                        // exactly this drag. No skipSaveState needed.
                        const patch = isShow
                            ? { show_workspace_x: wx, show_workspace_y: wy }
                            : { workspace_x: wx, workspace_y: wy };
                        window.app.updateCanvas(id, patch);
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
                        // v0.11.0 screen groups: the gate used to be a straight
                        // `clickedPanel.layerId === currentLayer.id`, which made
                        // a hand-drawn path physically unable to leave its own
                        // layer. A group is ONE wall, so the path has to be able
                        // to run onto the next member. getPanelAt already
                        // searched every visible layer top-down and told us
                        // which one it hit, applying that layer's own Show Look
                        // offset, canvas translate and rotation, so there is no
                        // geometry to redo here - only the question of whether
                        // the port may legally reach that layer, which
                        // canPathReachLayer answers (same group, same effective
                        // canvas). Without the helper it reduces to the old
                        // identity test, so nothing changes before app-power.js
                        // lands it.
                        const clickedLayer = window.app.project.layers.find(
                            l => l.id === clickedPanel.layerId) || null;
                        const reachable = (typeof window.app.canPathReachLayer === 'function')
                            ? !!(clickedLayer && window.app.canPathReachLayer(
                                window.app.currentLayer, clickedLayer))
                            : clickedPanel.layerId === window.app.currentLayer.id;
                        if (isPower && window.app.isCustomPower(window.app.currentLayer) && reachable) {
                            if (window.app.powerCustomSelection.size > 0) {
                                window.app.powerCustomSelection.clear();
                                window.app.updateCustomPowerUI();
                            } else {
                                // The clicked panel's OWN layer goes with it so
                                // makePathEntry can stamp the right layerId;
                                // it is omitted again when that layer is the
                                // owner, which is every pre-group project.
                                window.app.addPanelToCustomPowerPath(clickedPanel.panel, clickedLayer);
                            }
                        } else if (!isPower && window.app.isCustomFlow(window.app.currentLayer) && reachable) {
                            if (window.app.customSelection.size > 0) {
                                window.app.clearCustomSelection();
                            } else {
                                window.app.addPanelToCustomPath(clickedPanel.panel, clickedLayer);
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
                    // v0.11.0 screen groups: the marquee crosses members too.
                    //
                    // It could not before, and the reason was real:
                    // customSelection / powerCustomSelection were keyed by the
                    // UNSCOPED getPanelKey, `${row},${col}`, so member A's R0C0
                    // and member B's R0C0 were the SAME entry in the Set and a
                    // marquee spanning two members could only ever commit the
                    // OWNER's cabinets under the peer's row and column - a
                    // silently wrong path, not a partly-working one. Those two
                    // Sets are now keyed by getScopedPanelKey,
                    // `${layerId}:${row},${col}`, which is what makes a
                    // cross-member selection expressible at all.
                    // (pixelMapSelection stays unscoped - it is a single-screen
                    // feature and its overlay still parses the plain key.)
                    //
                    // currentLayer stays the OWNER of the port/circuit being
                    // drawn even when the rect covers a peer; selectPanelsInRect
                    // hit-tests every layer the owner's path may legally reach.
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
                            this._toggleLayerSelectionFromCanvas(layer);
                        } else {
                            this._selectLayerFromCanvas(layer);
                        }
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_select_click', { viewMode: this.viewMode, layerId: layer.id, toggle: isToggle });
                        }
                    }
                } else {
                    window.app.selectLayersInRect(this.layerSelectionRect, isToggle);
                    // v0.11.0: a marquee that catches one member of a group
                    // catches the group. Skipped for the toggle (Cmd/Ctrl)
                    // marquee, where re-adding what the user just toggled OUT
                    // would fight the gesture.
                    if (!isToggle && this._extendSelectionToGroups()
                            && typeof window.app.renderLayers === 'function') {
                        window.app.renderLayers();
                    }
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
                const _dropWY = ((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom;
                const dx = Math.round(this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom, _dropWY) - this.dragLayerStartX);
                const dy = Math.round(_dropWY - this.dragLayerStartY);
                
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
                // v0.8.5: Pixel Map and Show Look maintain INDEPENDENT canvas
                // membership. The Show Look canvas (used for show-look /
                // data / power rendering) is the layer's `show_canvas_id`,
                // falling back to `canvas_id` when null (the default).
                // Pixel Map / Cabinet ID always use `canvas_id`.
                const isShowMode = (this.dragLayerMode === 'show');
                const primaryCanvasId = isShowMode
                    ? (primary.show_canvas_id || primary.canvas_id)
                    : primary.canvas_id;
                const primaryCanvas = window.app.project && Array.isArray(window.app.project.canvases)
                    ? window.app.project.canvases.find(c => c && c.id === primaryCanvasId)
                    : null;
                let crossCanvasHandled = false;
                if (primaryCanvas) {
                    // Mouse cursor world coords at drop (already computed
                    // above for the offset delta).
                    const cursorWY = ((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom;
                    const cursorWX = this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom, cursorWY);
                    const targetCanvas = this._canvasAtPoint(cursorWX, cursorWY);
                    if (targetCanvas && targetCanvas.id !== primaryCanvasId) {
                        const mode = (e.metaKey || e.altKey) ? 'duplicate' : 'move';
                        // v0.8.6.3: in Show Look, include ALL unlocked
                        // selected layers in the multi-canvas drop,
                        // regardless of source canvas. Layers coming from
                        // different source canvases each get their own
                        // showOffset compensation based on their own source
                        // canvas's show_workspace (computed below).
                        // Pixel Map drag still requires same-source-canvas
                        // because Pixel Map reparent rewrites offset_x/y
                        // relative to the new canvas's origin and the bulk
                        // reparent endpoint expects a single source.
                        const peerCanvasId = (l) => isShowMode
                            ? (l.show_canvas_id || l.canvas_id)
                            : l.canvas_id;
                        const movedIds = [primary.id];
                        if (window.app.selectedLayerIds && window.app.selectedLayerIds.size > 1) {
                            window.app.selectedLayerIds.forEach(id => {
                                if (id === primary.id) return;
                                const l = window.app.project.layers.find(x => x.id === id);
                                if (!l || l.locked) return;
                                if (peerCanvasId(l) === targetCanvas.id) return; // already there
                                if (isShowMode) {
                                    movedIds.push(id);
                                } else if (peerCanvasId(l) === primaryCanvasId) {
                                    movedIds.push(id);
                                }
                            });
                        }
                        if (isShowMode) {
                            // Show Look drag: persist the freshly-dragged
                            // showOffsetX/Y first (no saveState on this PUT
                            //, the moveLayerShowCanvas .then() will snapshot
                            // post-everything state), then PUT show_canvas_id
                            // so canvas_id, offset_x/y, panels stay put.
                            // Duplicate is not supported here (mode is
                            // forced to 'move') since show-canvas reassign
                            // isn't a clone op.
                            //
                            // v0.8.5 fix: showOffsetX/Y are stored CANVAS-
                            // RELATIVE (renderer adds canvas.workspace_x/y to
                            // them). When we swap the layer's effective show
                            // canvas, we MUST compensate the offsets by
                            // (oldCanvas.workspace - newCanvas.workspace) or
                            // the layer visually JUMPS to a wrong spot
                            // because (newCanvas.workspace + sameOffset) !=
                            // (oldCanvas.workspace + sameOffset). Without
                            // this, dragging a c2 screen into c1's area
                            // looked like the layer was still in c2's space
                            // (or even way off-screen).
                            // v0.8.5.3: compensation must use the SHOW-LOOK
                            // workspace of each canvas (the one the layer is
                            // actually rendered against in this view).
                            // v0.8.6.3: each moved layer might come from a
                            // different source canvas (when the user has a
                            // multi-canvas selection), so compute per-layer
                            // compensation rather than reusing the primary's
                            // source delta for everyone.
                            const _ws2 = this._canvasWorkspace(targetCanvas);
                            const _canvasById = {};
                            (window.app.project.canvases || []).forEach(c => {
                                if (c && c.id) _canvasById[c.id] = c;
                            });
                            movedIds.forEach(id => {
                                const l = window.app.project.layers.find(x => x.id === id);
                                if (!l) return;
                                const srcCid = peerCanvasId(l);
                                const srcCanvas = _canvasById[srcCid];
                                if (!srcCanvas) return;
                                const _ws1 = this._canvasWorkspace(srcCanvas);
                                l.showOffsetX = (Number(l.showOffsetX) || 0) + (_ws1.wx - _ws2.wx);
                                l.showOffsetY = (Number(l.showOffsetY) || 0) + (_ws1.wy - _ws2.wy);
                            });
                            const toUpdate = window.app.getSelectedLayers
                                ? window.app.getSelectedLayers()
                                : [window.app.currentLayer];
                            window.app.updateLayers(toUpdate, false);
                            if (movedIds.length > 1 && typeof window.app.moveLayersShowCanvas === 'function') {
                                window.app.moveLayersShowCanvas(movedIds, targetCanvas.id);
                            } else if (typeof window.app.moveLayerShowCanvas === 'function') {
                                window.app.moveLayerShowCanvas(primary.id, targetCanvas.id);
                            }
                            crossCanvasHandled = true;
                        } else {
                            // Pixel Map drag: full processor reparent
                            // (resets offset_x/y, rebuilds panel geometry
                            // at the new canvas's origin).
                            if (movedIds.length > 1 && typeof window.app.moveLayersCrossCanvas === 'function') {
                                window.app.moveLayersCrossCanvas(movedIds, targetCanvas.id, mode);
                                crossCanvasHandled = true;
                            } else if (typeof window.app.moveLayerCrossCanvas === 'function') {
                                window.app.moveLayerCrossCanvas(primary.id, targetCanvas.id, mode);
                                crossCanvasHandled = true;
                            }
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

                if (this.viewMode === 'pixel-map') {
                    currentOffsetX = layer.screenNameOffsetXPixelMap || 0;
                    currentOffsetY = layer.screenNameOffsetYPixelMap || 0;
                } else if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                } else if (this.viewMode === 'show-look') {
                    currentOffsetX = layer.screenNameOffsetXShowLook || 0;
                    currentOffsetY = layer.screenNameOffsetYShowLook || 0;
                }

                const moved = currentOffsetX !== this.screenNameStartOffset.x || currentOffsetY !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Screen Name');
                }
                window.app.saveClientSideProperties();
            }
            this.render();
        } else if (this.isDraggingGroupName) {
            this.isDraggingGroupName = false;
            const group = this._dragGroupNameGroup;
            this._dragGroupNameGroup = null;
            // Persist and snapshot ONLY if the headline actually moved. The
            // offsets live on the group, which rides the project itself, so
            // persistence is a project save rather than a layer PUT.
            if (group && window.app) {
                const f = this._screenNameOffsetFields();
                const moved = (group[f.x] || 0) !== this.screenNameStartOffset.x
                    || (group[f.y] || 0) !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Group Name');
                }
                if (typeof window.app.saveProject === 'function') {
                    window.app.saveProject();
                }
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
        // In the views where screens can be moved, right-clicking a screen that
        // isn't part of the current selection targets that screen, so "Center
        // on Canvas" acts on what the user actually pointed at.
        if (['pixel-map', 'show-look'].includes(this.viewMode)) {
            const rect = this.canvas.getBoundingClientRect();
            const worldY = ((e.clientY - rect.top) - this.panY) / this.zoom;
            const worldX = this._unmirrorWorldX(((e.clientX - rect.left) - this.panX) / this.zoom, worldY);
            const hit = this.getLayerAt(worldX, worldY);
            // selectedLayerIds is a Set — use .has(), not Array.includes()
            // (which threw a TypeError here and aborted the handler).
            const selectedIds = window.app.selectedLayerIds;
            const alreadySelected = selectedIds
                && (typeof selectedIds.has === 'function'
                    ? selectedIds.has(hit && hit.id)
                    : Array.from(selectedIds).includes(hit && hit.id));
            if (hit && !alreadySelected) {
                this._selectLayerFromCanvas(hit);
            }
        }
        if (this.viewMode === 'pixel-map' && window.app.currentLayer) {
            const rect = this.canvas.getBoundingClientRect();
            const worldY = ((e.clientY - rect.top) - this.panY) / this.zoom;
            const worldX = this._unmirrorWorldX(((e.clientX - rect.left) - this.panX) / this.zoom, worldY);
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
        
        // Cmd/Ctrl+J - Duplicate (standard)
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

        // Tab / Shift+Tab - next / previous custom PORT in Data Flow, custom
        // CIRCUIT in Power.
        //
        // These two used to inline their own copy of the step, testing
        // isCustomFlow FIRST with no view check - and isCustomFlow is a pure
        // layer-state predicate (flowPattern === 'custom'), not a view test.
        // So on a screen that had BOTH a custom data pattern and custom power
        // - which every screen in a group has, because the flow pattern is
        // shared across members - Tab in POWER view took the data branch and
        // silently advanced the DATA port. The circuit never moved, so the key
        // looked dead. Data flow worked, which is exactly why it went unseen:
        // there the first branch IS the right one. Same defect the drag-select
        // handler above carries a comment about; this copy was missed.
        //
        // Routed through stepCustomPort now, so there is ONE implementation
        // shared with the on-screen Next/Prev buttons. It checks the VIEW as
        // well as the pattern, and it PUTs the new index to the server -
        // which this handler also never did, so a Tab'd index was lost on the
        // next reload even when it moved the right one.
        if (e.code === 'Tab' && !e.metaKey && !e.ctrlKey && !isTyping
                && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            const handled =
                (this.viewMode === 'data-flow' && window.app.isCustomFlow(layer))
                || (this.viewMode === 'power' && window.app.isCustomPower(layer));
            if (handled) {
                e.preventDefault();
                window.app.stepCustomPort(e.shiftKey ? -1 : 1);
            }
        }

        // [ prev / ] next - the same step as Tab, and now the same one call.
        //
        // These two blocks were correctly view-guarded, so they never stepped
        // the wrong thing. They did mutate the index inline without either
        // updateLayers() or saveClientSideProperties(), and customPortIndex /
        // powerCustomIndex are persisted fields - so stepping to port 7 with
        // "]" and reloading, or letting any other edit PUT first, snapped the
        // index back to whatever a button had last written. stepCustomPort
        // does the step, the save, the localStorage write and the PUT.
        if (!isTyping && (e.code === 'BracketLeft' || e.code === 'BracketRight')
                && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            const handled =
                (this.viewMode === 'data-flow' && window.app.isCustomFlow(layer))
                || (this.viewMode === 'power' && window.app.isCustomPower(layer));
            if (handled) {
                e.preventDefault();
                window.app.stepCustomPort(e.code === 'BracketLeft' ? -1 : 1);
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

        // Cmd/Ctrl+Shift+' - Toggle snap (standard: Snap to Grid)
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

    // Focus loss eats the release events that end whatever is held right
    // now: cmd-tab with space down delivers the keyup to the other app, and
    // a mouse button let go over another window is never reported here
    // either. Without this, spacePressed (and any armed drag) stayed
    // latched until the user rediscovered the magic unstick tap. Called on
    // window blur and on tab-hide. Held-key state is dropped outright;
    // an in-flight drag is pushed through the normal mouseup finalizer at
    // the last known cursor position, because layer/canvas drags mutate
    // offsets live during mousemove and just clearing the flag would strand
    // those moves unpersisted with no undo snapshot.
    _releaseTransientInput() {
        this.spacePressed = false;
        const armed = this.isDragging || this.isDraggingLayer
            || this.isDraggingScreenName || this.isDraggingGroupName
            || this.isDraggingCanvas || this.isAltPainting
            || this.isSelectingPanels || this.isSelectingPixelMapPanels
            || this.isSelectingLayers
            || this.selectionRect || this.layerSelectionRect;
        if (armed) {
            this.handleMouseUp({
                button: 0,
                clientX: this._lastClientX || 0,
                clientY: this._lastClientY || 0,
                shiftKey: false,
                altKey: false,
                metaKey: false,
                ctrlKey: false
            });
        }
        this.canvas.style.cursor = 'default';
    }
    
    /**
     * v0.8 multi-canvas: return the workspace translate ({wx, wy}) for the
     * canvas a layer belongs to. Layers without a canvas_id (legacy / orphan)
     * and projects with no canvases array fall back to (0, 0) so single-canvas
     * behaviour is unchanged.
     */
    /**
     * v0.8.5.3: which workspace position does this canvas use in the active
     * view? Show Look (and Data + Power, which render at the show layout)
     * use `show_workspace_x/y` when set; otherwise mirror `workspace_x/y`.
     * Pixel Map / Cabinet ID always use `workspace_x/y`. Returns {wx, wy}.
     */
    _canvasWorkspace(canvas) {
        if (!canvas) return { wx: 0, wy: 0 };
        if (this.isShowLookView()) {
            const swx = canvas.show_workspace_x;
            const swy = canvas.show_workspace_y;
            return {
                wx: (swx == null ? (canvas.workspace_x || 0) : (swx || 0)),
                wy: (swy == null ? (canvas.workspace_y || 0) : (swy || 0)),
            };
        }
        return { wx: canvas.workspace_x || 0, wy: canvas.workspace_y || 0 };
    }

    /**
     * v0.8.5: which canvas does this layer "live in" for the active view?
     * Pixel Map / Cabinet ID always use the processor canvas (canvas_id).
     * Show Look / Data / Power use the layer's `show_canvas_id` override
     * (set by Show Look cross-canvas drops); when null/missing, falls back
     * to canvas_id so the layer mirrors its Pixel Map canvas.
     */
    _effectiveLayerCanvasId(layer) {
        if (!layer) return null;
        if (this.isShowLookView() && layer.show_canvas_id) {
            return layer.show_canvas_id;
        }
        return layer.canvas_id || null;
    }

    _layerCanvasOffset(layer) {
        if (!layer || !window.app || !window.app.project) return { wx: 0, wy: 0 };
        const arr = window.app.project.canvases;
        if (!Array.isArray(arr) || arr.length === 0) return { wx: 0, wy: 0 };
        const cid = this._effectiveLayerCanvasId(layer);
        if (!cid) return { wx: 0, wy: 0 };
        for (const c of arr) {
            if (c && c.id === cid) {
                // v0.8.5.3: Show Look uses its own canvas workspace position.
                return this._canvasWorkspace(c);
            }
        }
        return { wx: 0, wy: 0 };
    }

    // ── Screen groups (v0.11.0): the canvas half ──────────────────────────
    //
    // Step 2 built the roll-up (app-screen-info.js getGroupTotals). A group is
    // ONE screen that had to be built from more than one layer, because the
    // per-layer grid is uniform: a wall of 1m JP5 cabinets AND 0.5m standard
    // cabinets is two layers no matter how it reads on site. The geometry has
    // always been right; what was wrong is that it DREW, SELECTED and MOVED as
    // two screens. So: one label over the group's bounding box, clicking any
    // member selects them all, and dragging any member moves the whole group
    // in one undo step. Members still draw their own cabinets - only the label
    // consolidates.
    //
    // Every helper here returns null / [] / false for an ungrouped layer, so a
    // project without groups takes exactly the paths it took before.

    _groupForLayer(layer) {
        if (!layer || !layer.group_id) return null;
        if (!window.app || typeof window.app.resolveGroup !== 'function') return null;
        return window.app.resolveGroup(layer.group_id);
    }

    // The members of `layer`'s group that this view actually draws: screens,
    // not hidden, and on the same effective canvas as `layer` (a group split
    // across canvases would otherwise union bounds across two workspaces).
    // Returned in the group's own order, which is the order the user built it.
    _groupDrawnMembers(layer) {
        const g = this._groupForLayer(layer);
        if (!g || !window.app || typeof window.app.getGroupMembers !== 'function') return [];
        const cid = this._effectiveLayerCanvasId(layer);
        return window.app.getGroupMembers(g).filter(m => m
            && (m.type || 'screen') === 'screen'
            && m.visible !== false
            && this._effectiveLayerCanvasId(m) === cid);
    }

    // Which name a grouped wall carries on the canvas. 'group' (the default,
    // and the v0.11.0 behaviour): ONE name - the group's - over the whole
    // wall. 'screens': every member keeps its own name, the way the wall
    // read before it was grouped. 'both': the group's name headlines the
    // wall AND every member keeps its own. Project-level, because it names
    // a drawing convention for every grouped wall - not one layer's toggle -
    // and the exports simply bake whatever the canvas draws.
    _groupNameMode() {
        const m = window.app && window.app.project
            && window.app.project.groupNameDisplay;
        return (m === 'screens' || m === 'both') ? m : 'group';
    }

    // The per-view screen-name offset field pair for the CURRENT view. One
    // authority for the mapping the drag handlers and the group-name drag
    // both need; the field names are the same whether they sit on a layer
    // (a screen's own name) or on a group (the group's headline).
    _screenNameOffsetFields() {
        switch (this.viewMode) {
            case 'cabinet-id': return { x: 'screenNameOffsetXCabinet', y: 'screenNameOffsetYCabinet' };
            case 'data-flow': return { x: 'screenNameOffsetXDataFlow', y: 'screenNameOffsetYDataFlow' };
            case 'power': return { x: 'screenNameOffsetXPower', y: 'screenNameOffsetYPower' };
            case 'show-look': return { x: 'screenNameOffsetXShowLook', y: 'screenNameOffsetYShowLook' };
            default: return { x: 'screenNameOffsetXPixelMap', y: 'screenNameOffsetYPixelMap' };
        }
    }

    // Who draws the group's single label, and whose label settings it uses.
    // Null unless `layer` is in a group with at least two drawn members - a
    // group of one has nothing to consolidate and keeps its own label.
    //   cfg   the group's FIRST member. Members can disagree on the label
    //         toggles, sizes and colours; the first member wins, the same way
    //         the group's name replaces the members' names.
    //   host  the LAST member in render order. The label is drawn in that
    //         member's pass so it lands on top of every member's cabinets.
    //         Hosted on the first member, the bottom info bar - which sits
    //         over the LAST member of a stacked wall - would be painted over
    //         by that member's panels a moment later.
    _groupLabelPlan(layer) {
        const members = this._groupDrawnMembers(layer);
        if (members.length < 2) return null;
        const order = (window.app.project && window.app.project.layers) || [];
        const drawn = members.slice().sort((a, b) => order.indexOf(a) - order.indexOf(b));
        return {
            group: this._groupForLayer(layer),
            members,
            cfg: members[0],
            host: drawn[drawn.length - 1],
        };
    }

    // THE WALL'S OWN RECTANGLE - the union of where its members are DRAWN,
    // expressed in the space the HOST layer draws in: renderCircleWithX and
    // renderLayerLabels both run inside the host's per-layer ctx.translate, so
    // each member's footprint is brought back by the host's own render offset.
    //
    // v0.11.0: the footprint, not the bounds. A member carrying a screen
    // rotation is drawn turned about its own centre, so its unrotated bounds
    // name a rectangle that is nowhere on the wall - and a 90/270 turn changes
    // the wall's width and height, which is what sizes the circle-and-X.
    // getLayerFootprintInActiveView is exactly "where this member draws", and
    // equals the bounds for an unrotated member, so an unrotated group is
    // unchanged.
    //
    // The two callers must therefore also DRAW in this frame: both cancel the
    // host's rotation (_unrotateLayerInPlace) before using these bounds. Measure
    // the wall, then rotate it about one member's centre, and the wall's own
    // centre lands off the wall.
    _groupUnionBounds(members, host) {
        const off = this.getLayerRenderOffset(host);
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        members.forEach(m => {
            const b = this.getLayerFootprintInActiveView(m);
            x1 = Math.min(x1, b.x - off.dx);
            y1 = Math.min(y1, b.y - off.dy);
            x2 = Math.max(x2, b.x + b.width - off.dx);
            y2 = Math.max(y2, b.y + b.height - off.dy);
        });
        if (!isFinite(x1)) return this.getLayerBounds(host);
        return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
    }

    // Where the 'both' name display's group headline will land, in `member`'s
    // own drawing frame - the box a member's name must keep clear of. The
    // member passes draw BEFORE the host draws the headline, so the box is
    // predicted with a lean restatement of renderLayerLabels' name layout
    // rather than read back from a previous frame (a stale read would come
    // apart in exports, which render each view exactly once). Null when the
    // headline is not drawn at all on this tab.
    _bothModeGroupNameBox(plan, member) {
        const cfg = plan.cfg;
        const group = plan.group || {};
        // Per-tab name visibility, the same fallback chain the label uses.
        let shown;
        if (this.viewMode === 'cabinet-id') {
            shown = cfg.showLabelNameCabinet !== undefined ? cfg.showLabelNameCabinet
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'data-flow') {
            shown = cfg.showLabelNameDataFlow !== undefined ? cfg.showLabelNameDataFlow
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'power') {
            shown = cfg.showLabelNamePower !== undefined ? cfg.showLabelNamePower
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else {
            shown = cfg.showLabelName !== undefined ? cfg.showLabelName : true;
        }
        if (!shown) return null;
        const name = group.name || cfg.name || '';
        if (!name) return null;

        const bounds = this._groupUnionBounds(plan.members, member);
        const padding = 6;
        const fontSize = cfg.labelsFontSize || 30;
        let nameSize = fontSize;
        if (this.viewMode === 'cabinet-id') nameSize = cfg.screenNameSizeCabinet || 14;
        else if (this.viewMode === 'data-flow') nameSize = cfg.screenNameSizeDataFlow || 14;
        else if (this.viewMode === 'power') nameSize = cfg.screenNameSizePower || 14;
        const nameHeight = (nameSize + 4) + padding * 2;

        const prevFont = this.ctx.font;
        this.ctx.font = `bold ${nameSize}px ${projectFontFamily()}`;
        const nameWidth = this.ctx.measureText(name).width + padding * 2;
        this.ctx.font = prevFont;

        const f = this._screenNameOffsetFields();
        const offX = this._mirror ? -(group[f.x] || 0) : (group[f.x] || 0);
        const offY = group[f.y] || 0;
        const centerX = bounds.x + bounds.width / 2;
        const centerY = bounds.y + bounds.height / 2;

        // The dodge must clear the headline's WHOLE centre stack - the name
        // plus whatever rides under it (the size/weight lines on Pixel Map,
        // the port/circuit line on Data and Power) - or a member name pushed
        // past the name box just lands behind the next line down.
        let stackBelow = 0;   // stack height below the name box's own bottom
        if (this.viewMode === 'pixel-map') {
            let lines = 0;
            if (cfg.showLabelSizePx) lines++;
            if (cfg.showLabelSizeM) lines++;
            if (cfg.showLabelSizeFt) lines++;
            if (cfg.showLabelWeight) lines++;
            if (lines > 0) stackBelow = 5 + lines * (fontSize + 4) + padding * 2;
        } else if (this.viewMode === 'data-flow' && cfg.showDataFlowPortInfo) {
            stackBelow = 5 + (nameSize + 4) + padding * 2;
        } else if (this.viewMode === 'power' && cfg.showPowerCircuitInfo) {
            stackBelow = 5 + (nameSize + 4) + padding * 2;
        }
        // Pixel Map centres name + lines as one stack, so the name box sits
        // above centre by half the lines' height. Every other tab centres
        // the name itself and hangs the info line beneath it.
        let boxCenterY = centerY;
        if (this.viewMode === 'pixel-map') {
            boxCenterY = centerY - (nameHeight + stackBelow) / 2 + nameHeight / 2;
        }

        // The same edge clamp the real draw applies, against the union.
        const _clamp = (v, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.min(Math.max(v, lo), hi));
        const cx = _clamp(centerX + offX, bounds.x + nameWidth / 2, bounds.x + bounds.width - nameWidth / 2);
        const cy = _clamp(boxCenterY + offY, bounds.y + nameHeight / 2, bounds.y + bounds.height - nameHeight / 2);
        return {
            x1: cx - nameWidth / 2, y1: cy - nameHeight / 2,
            x2: cx + nameWidth / 2, y2: cy + nameHeight / 2 + stackBelow,
        };
    }

    // Pull every selected layer's group peers into the selection. This extends
    // the existing multi-select Set - the same one the marquee fills - rather
    // than adding a second selection path, so the sidebar, the selection
    // bounding boxes and the layer drag all keep reading one source of truth.
    // Returns true when it actually added something.
    _extendSelectionToGroups() {
        if (!window.app || !window.app.selectedLayerIds) return false;
        const layers = (window.app.project && window.app.project.layers) || [];
        const selected = layers.filter(l => window.app.selectedLayerIds.has(l.id));
        let added = false;
        selected.forEach(l => {
            const g = this._groupForLayer(l);
            if (!g || typeof window.app.getGroupMembers !== 'function') return;
            window.app.getGroupMembers(g).forEach(m => {
                if (!m || m.visible === false) return;
                if (window.app.selectedLayerIds.has(m.id)) return;
                window.app.selectedLayerIds.add(m.id);
                added = true;
            });
        });
        return added;
    }

    // Click-select from the canvas: selects the layer exactly as before, then
    // widens to its group so a grouped wall selects - and therefore drags - as
    // the one screen it is.
    _selectLayerFromCanvas(layer) {
        if (!window.app || !layer || typeof window.app.selectLayer !== 'function') return;
        window.app.selectLayer(layer);
        if (!this._extendSelectionToGroups()) return;
        // selectLayer already refreshed for the single-layer selection; repeat
        // the cheap parts so the sidebar and the selection boxes show the peers.
        if (typeof window.app.renderLayers === 'function') window.app.renderLayers();
        this.render();
    }

    // Cmd/Ctrl+click from the canvas: toggle the clicked layer in/out of the
    // multi-selection (the same selectedLayerIds Set the sidebar's Ctrl-click
    // uses, so bulk edits / group actions / totals downstream see one model).
    // The toggle UNIT is whatever a plain click would select: the whole group
    // when the clicked layer is a grouped member, the single layer otherwise.
    // So toggling an unselected member brings its whole group in, and toggling
    // a selected member takes the whole group out. Ungrouped layers delegate
    // to the app's own toggleLayerSelection so canvas and sidebar stay one
    // behaviour. Selection is view state - no saveState anywhere on this path.
    _toggleLayerSelectionFromCanvas(layer) {
        const app = window.app;
        if (!app || !layer) return;
        let unit = null;
        const g = this._groupForLayer(layer);
        if (g && typeof app.getGroupMembers === 'function') {
            const members = app.getGroupMembers(g)
                .filter(m => m && m.visible !== false);
            if (members.length > 1 && members.some(m => m.id === layer.id)) {
                unit = members;
            }
        }
        if (!unit) {
            if (typeof app.toggleLayerSelection === 'function') {
                app.toggleLayerSelection(layer);
            }
            return;
        }
        if (!app.selectedLayerIds) app.selectedLayerIds = new Set();
        const sel = app.selectedLayerIds;
        if (sel.has(layer.id)) {
            // Toggling a selected member OUT removes its whole group.
            unit.forEach(m => sel.delete(m.id));
            if (app.currentLayer && !sel.has(app.currentLayer.id)) {
                const nextId = sel.values().next().value;
                app.currentLayer = nextId
                    ? (app.project.layers.find(l => l.id === nextId) || null)
                    : null;
                app.lastSelectedLayerId = app.currentLayer ? app.currentLayer.id : null;
            }
        } else {
            unit.forEach(m => sel.add(m.id));
            app.currentLayer = layer;
            app.lastSelectedLayerId = layer.id;
            if (!app.selectionAnchorLayerId) app.selectionAnchorLayerId = layer.id;
            // Same preserveSelection contract as toggleLayerSelection, so a
            // cross-canvas multi-selection survives the canvas activation.
            if (typeof app._activateCanvasForLayer === 'function') {
                app._activateCanvasForLayer(layer, { preserveSelection: true });
            }
        }
        if (typeof app.renderLayers === 'function') app.renderLayers();
        if (typeof app.loadLayerToInputs === 'function') app.loadLayerToInputs();
        this.render();
    }

    // Add the group peers of everything in `layers` (in place), and to the
    // app's selection, so a drag started on one member moves the whole group
    // AND mouseup's updateLayers persists every layer the drag actually moved.
    _addGroupPeersToDrag(layers) {
        if (!window.app || !Array.isArray(layers)) return layers;
        const seen = new Set(layers.map(l => l && l.id));
        layers.slice().forEach(l => {
            const g = this._groupForLayer(l);
            if (!g || typeof window.app.getGroupMembers !== 'function') return;
            window.app.getGroupMembers(g).forEach(m => {
                if (!m || seen.has(m.id) || m.visible === false) return;
                if ((m.type || 'screen') !== 'screen') return;
                seen.add(m.id);
                layers.push(m);
                if (window.app.selectedLayerIds) window.app.selectedLayerIds.add(m.id);
            });
        });
        return layers;
    }

    // ── Screen groups (v0.11.0): paths that cross from member to member ───
    //
    // To the user a group IS one wall, so a hand-drawn port or circuit has to
    // be allowed to run off one member and onto the next. The path still
    // BELONGS to the layer that owns the port/circuit; only the individual
    // step learns where it landed, as `{row, col, layerId}`. app-power.js owns
    // the resolution helpers (resolvePathEntry, getResolvedPathPanels,
    // pathCrossesMembers, ...); everything here CALLS them and degrades to
    // plain single-layer behaviour when they are absent, so the renderer never
    // depends on load order.
    //
    // WHY A SEPARATE PASS. renderDataFlowArrows / renderPowerArrows run INSIDE
    // one layer's ctx transform: the canvas workspace translate, the canvas
    // mirror, that layer's Show Look offset and that layer's rotation. Two
    // members with different showOffsetX/Y or different rotation cannot both be
    // correct under one of those, and drawing the line during the OWNER's pass
    // would also let a peer drawn later paint its cabinets over it. So a
    // crossing path is skipped in the per-layer pass, its owner is queued, and
    // after the whole canvas loop has finished we re-enter the same renderers
    // with `_crossMemberPass` set - reusing every line of the drawing code
    // rather than growing a second copy of it that can drift.
    //
    // A path with NO cross-layer entry never reaches any of this: it takes the
    // per-layer branch it always took, expression for expression. That is the
    // whole point - the overwhelming majority of projects have no groups at
    // all, and none of them may change by a pixel.

    // Is a press on `hitLayer` a DRAWING gesture aimed at the current layer,
    // rather than a request to switch to that screen?
    //
    // It is exactly when the user is hand-drawing a port or a circuit and the
    // press landed on a peer member of the owner's group. Without this, the
    // generic "click a panel, that panel's layer becomes currentLayer" step in
    // handleMouseDown fires FIRST and quietly moves the ownership of the path
    // being drawn onto the peer: the click-to-add gate step 6 relaxed with
    // canPathReachLayer would then never see a peer at all (currentLayer would
    // already BE that peer), and a marquee started over the next screen of the
    // wall would fill the peer's port instead of the one the user has open.
    //
    // Only the currentLayer promotion is suppressed - the canvas activation
    // above it still runs, and everything outside custom mode is untouched, so
    // clicking a peer to select it works exactly as before whenever the user is
    // not mid-draw.
    _isCustomPathGesture(hitLayer) {
        const app = window.app;
        if (!app || !hitLayer) return false;
        const owner = app.currentLayer;
        if (!owner || owner.id === hitLayer.id) return false;
        const drawing = (this.viewMode === 'data-flow' && app.isCustomFlow && app.isCustomFlow(owner))
            || (this.viewMode === 'power' && app.isCustomPower && app.isCustomPower(owner));
        if (!drawing) return false;
        if (typeof app.canPathReachLayer !== 'function') return false;
        return !!app.canPathReachLayer(owner, hitLayer);
    }

    // Does a press at this point belong to the custom path being drawn?
    //
    // True only inside a screen the gesture can actually draw on: the screen
    // whose port/circuit is open, or a group peer the path can reach. Anywhere
    // else - empty canvas, an unrelated screen, an image on top - the press is
    // an ordinary layer-level press and mousedown must fall through to the
    // layer marquee below.
    //
    // getLayerAt is the bounds test, and it is the topmost layer at that point,
    // so a text or image layer sitting over the screen takes the press rather
    // than the marquee underneath it - the same occlusion rule Pixel Map's
    // panel drag already follows.
    _customDrawStartsInScope(worldX, worldY) {
        const app = window.app;
        if (!app || !app.currentLayer) return false;
        const hitLayer = this.getLayerAt(worldX, worldY);
        if (!hitLayer) return false;                       // empty canvas
        if (hitLayer.id === app.currentLayer.id) return true;
        return this._isCustomPathGesture(hitLayer);        // reachable peer
    }

    // Is this path one of the crossing ones? False whenever app-power.js has
    // not defined the helper, which is also the honest answer for a project
    // that has never had a group.
    _pathCrossesMembers(ownerLayer, path) {
        const app = window.app;
        if (!app || typeof app.pathCrossesMembers !== 'function') return false;
        return !!app.pathCrossesMembers(ownerLayer, path);
    }

    // A path resolved to {layer, panel} pairs, hidden cabinets dropped, in path
    // order. Falls back to owner-only resolution so this is safe before
    // app-power.js grows getResolvedPathPanels.
    _resolvePathPanels(ownerLayer, path) {
        const app = window.app;
        if (!app || !Array.isArray(path)) return [];
        if (typeof app.getResolvedPathPanels === 'function') {
            return app.getResolvedPathPanels(ownerLayer, path) || [];
        }
        return path
            .map(pos => {
                const panel = app.getPanelByRowCol(ownerLayer, pos && pos.row, pos && pos.col);
                return panel && !panel.hidden ? { layer: ownerLayer, panel } : null;
            })
            .filter(Boolean);
    }

    // One resolved cabinet as the geometry the arrow renderers actually read:
    // an {x, y, width, height} rect in the frame the cross-member overlay draws
    // in. That frame is the canvas workspace AFTER the mirror, so it carries
    // the entry layer's OWN rotation and its OWN Show Look offset - the two
    // things that differ between members - and nothing else. The workspace
    // translate and the mirror are identical for every member (a group member
    // on another effective canvas is not reachable at all, see
    // _groupDrawnMembers), so the caller applies those once as a ctx transform.
    //
    // Under a 90/270 rotation the cabinet's footprint swaps width and height;
    // the rect is rebuilt around the ROTATED CENTRE so `x + width / 2` - the
    // only thing the arrow code ever asks for - still names the middle of the
    // cabinet as drawn.
    //
    // v0.11.0: this is _drawnPanelRect with the member's frame computed on the
    // spot. It stays as a named entry point because it reads at the call sites
    // as "put this peer's cabinet where it is drawn", and because the audit
    // helpers and tests address it by name; a caller mapping MANY cabinets of
    // one member should hoist _layerDrawFrame itself rather than pay for it per
    // cabinet.
    _crossMemberPanelShim(entryLayer, panel) {
        return this._drawnPanelRect(this._layerDrawFrame(entryLayer), panel);
    }

    // v0.11.0: a cabinet on a member this view does not draw is not on the
    // drawing, so no cable may be drawn onto it. getResolvedPathPanels
    // deliberately KEEPS entries pointing at a hidden member (app-power.js) so
    // that hiding a member and showing it again does not destroy wiring already
    // drawn onto it - that is the model's job. The DRAWING side has the opposite
    // duty: a printed map must not carry a data cable running off the wall onto
    // blank paper. So the line stops at the last cabinet that is actually drawn,
    // which is the same way the circle-and-X shrinks to what is lit.
    _crossMemberDrawPanels(ownerLayer, path) {
        return this._resolvePathPanels(ownerLayer, path)
            .filter(hit => hit && hit.layer && hit.layer.visible !== false)
            .map(hit => this._crossMemberPanelShim(hit.layer, hit.panel));
    }

    // The cabinets a crossing port is SCORED on, which is a different frame
    // from the one it is drawn in.
    //
    // Port load and capacity are processor facts: the NovaStar Armor rectangle
    // constraint is about the pixel rectangle the processor has to push, and
    // the NovaStar low-latency (1 - Y/H) derate measures Y down the processor
    // canvas. panel.x/panel.y are ALREADY canvas-relative - _build_panels lays
    // each column out from layer.offset_x (app.py) - so two members of the same
    // processor canvas already share one frame and their raw coords union
    // correctly with no conversion at all. Adding the Show Look offset here,
    // which is what the DRAWING frame carries, would silently move a port's Y
    // and hand the low-latency derate a number about where the screen was
    // dragged for the show file rather than where the processor sees it.
    //
    // The one case that genuinely cannot be scored: Show Look can move a member
    // onto a different canvas (show_canvas_id), so two members can share an
    // EFFECTIVE canvas - which is all a cross-member path requires - while
    // their panels are laid out against different processor rasters. There is
    // no honest union across two rasters and no honest H for the derate, so
    // this returns null and the caller draws no badge rather than a number
    // nobody can act on.
    _crossMemberLoadPanels(ownerLayer, path) {
        const hits = this._resolvePathPanels(ownerLayer, path);
        if (hits.length === 0) return [];
        const rasterId = ownerLayer && ownerLayer.canvas_id;
        for (const hit of hits) {
            if (hit.layer && hit.layer.canvas_id !== rasterId) return null;
        }
        return hits.map(hit => hit.panel);
    }

    // Union of the drawn members' footprints in the overlay frame, so the port
    // and circuit labels are nudged inside THE WALL rather than inside whichever
    // member happens to own the port. getLayerFootprintInActiveView is already
    // exactly this frame: bounds + that member's render offset, rotated.
    _crossMemberBounds(ownerLayer) {
        const members = this._groupDrawnMembers(ownerLayer);
        if (members.length === 0) return this.getLayerBoundsInActiveView(ownerLayer);
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        members.forEach(m => {
            const b = this.getLayerFootprintInActiveView(m);
            x1 = Math.min(x1, b.x);
            y1 = Math.min(y1, b.y);
            x2 = Math.max(x2, b.x + b.width);
            y2 = Math.max(y2, b.y + b.height);
        });
        if (!isFinite(x1)) return this.getLayerBoundsInActiveView(ownerLayer);
        return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
    }

    // The one decision every custom-path branch asks: is this path mine to draw?
    // In the ordinary per-layer pass a crossing path is skipped and its owner
    // remembered; in the overlay pass only crossing paths draw. Returns true
    // when the caller should skip.
    _deferCrossMemberPath(ownerLayer, path) {
        return this._deferCrossMember(ownerLayer, this._pathCrossesMembers(ownerLayer, path));
    }

    // The same decision for a run whose crossing is already known - an
    // AUTOMATIC port or circuit, where the answer comes from the assignment's
    // own layer ids rather than from a stored path. Split out so the two kinds
    // of crossing run cannot drift into two queueing rules.
    _deferCrossMember(ownerLayer, crosses) {
        if (this._crossMemberPass) return !crosses;
        if (crosses) {
            if (!this._crossMemberOwners) this._crossMemberOwners = [];
            if (!this._crossMemberOwners.includes(ownerLayer)) {
                this._crossMemberOwners.push(ownerLayer);
            }
            return true;
        }
        return false;
    }

    // An automatic assignment list resolved to {layer, panel} pairs, the same
    // shape _resolvePathPanels hands the hand-drawn side, with cabinets on a
    // member this view does not draw dropped: a printed map must not carry a
    // cable running off the wall onto blank paper.
    _autoCrossMemberHits(ownerLayer, items) {
        const app = window.app;
        const scope = (app && typeof app.getPathScopeLayers === 'function')
            ? app.getPathScopeLayers(ownerLayer) : [ownerLayer];
        const byId = new Map(scope.map(l => [l.id, l]));
        return (items || [])
            .map(item => {
                const l = (item.layerId === undefined || item.layerId === null)
                    ? ownerLayer : byId.get(item.layerId);
                return (l && l.visible !== false) ? { layer: l, panel: item.panel } : null;
            })
            .filter(Boolean);
    }

    // The overlay frame: the canvas workspace translate and the canvas mirror,
    // and deliberately NOT the per-layer Show Look offset or rotation - those
    // are per member and are already baked into the points. `_mirror` is raised
    // for the duration for the same reason the main loop raises it, so port and
    // circuit labels come out readable on a Back-perspective canvas instead of
    // written backwards.
    _withCrossMemberCanvasTransform(ownerLayer, fn) {
        const wsOff = this._layerCanvasOffset(ownerLayer);
        const cid = this._effectiveLayerCanvasId(ownerLayer);
        const arr = (window.app && window.app.project && window.app.project.canvases) || [];
        const c = Array.isArray(arr) ? arr.find(x => x && x.id === cid) : null;
        const mirrorActive = !!(c && this._isCanvasMirrored(c));
        const prevMirror = this._mirror;
        this.ctx.save();
        if (wsOff.wx || wsOff.wy) this.ctx.translate(wsOff.wx, wsOff.wy);
        if (mirrorActive) {
            const crw = (this.isShowLookView() && c.show_raster_width) || c.raster_width || 0;
            this.ctx.translate(crw, 0);
            this.ctx.scale(-1, 1);
            this._mirror = true;
        }
        try {
            fn();
        } finally {
            this._mirror = prevMirror;
            this.ctx.restore();
        }
    }

    // The post-loop pass. Runs once per owner that queued a crossing path, in
    // the order the layers were drawn, so a crossing line lands on top of every
    // member's cabinets - which is what "one wall" has to look like.
    //
    // `_activeRenderCanvas` is restored to the owner's own canvas for the
    // duration: the loop cleared it, and without it _clipToActiveRaster would
    // clip a group living on a background canvas against the ACTIVE canvas's
    // raster and quietly trim the line.
    _renderCrossMemberPaths(kind) {
        const owners = this._crossMemberOwners;
        if (!Array.isArray(owners) || owners.length === 0) return;
        const canvases = (window.app && window.app.project && window.app.project.canvases) || [];
        this._crossMemberOwners = [];
        this._crossMemberPass = true;
        try {
            owners.forEach(layer => {
                if (!layer || !layer.visible) return;
                const cid = this._effectiveLayerCanvasId(layer);
                const canvas = Array.isArray(canvases) ? canvases.find(c => c && c.id === cid) : null;
                const prevCanvas = this._activeRenderCanvas;
                this._activeRenderCanvas = canvas || null;
                try {
                    this._withCrossMemberCanvasTransform(layer, () => {
                        if (kind === 'power') this.renderPowerArrows(layer);
                        else this.renderDataFlowArrows(layer);
                    });
                } finally {
                    this._activeRenderCanvas = prevCanvas;
                }
            });
        } finally {
            this._crossMemberPass = false;
            // Re-entering the renderers re-queued nothing legitimate (the
            // overlay pass never defers), but clear it so a helper that threw
            // mid-pass cannot leave an owner queued for the NEXT frame.
            this._crossMemberOwners = [];
        }
    }

    // The circuit tinting a cabinet in the color-coded power view, and the
    // layer that OWNS that circuit (its palette and its label are the owner's).
    //
    // The fast path is the layer's own unscoped map, byte for byte the lookup
    // this has always done. Only if that misses, and only for a grouped layer,
    // do we ask the peers: a circuit owned by member A can legally contain a
    // cabinet of member B, and B's own map knows nothing about it. Peer maps
    // are keyed by getScopedPanelKey - `${layerId}:${row},${col}` - because the
    // unscoped key cannot tell A's R0C0 from B's R0C0, and putting a peer's
    // cabinet into an unscoped map would tint the owner's OWN cabinet at that
    // row and column instead. (getPowerPanelKey itself stays `${row},${col}`,
    // one map per layer keyed by that layer's own grid; the SCOPED twin lives
    // beside it rather than replacing it, so every existing per-layer lookup is
    // untouched. The two custom-selection overlays did move to scoped keys in
    // v0.11.0 - see _resolveSelectionKey - but pixelMapSelection still parses
    // `key.split(',').map(parseInt)`, where `parseInt("3:0")` is 3 and a scoped
    // key would silently address the wrong panel with no error at all.)
    _powerCircuitForPanel(layer, panel) {
        if (layer._powerPanelCircuitMap instanceof Map) {
            const n = layer._powerPanelCircuitMap.get(this.getPowerPanelKey(panel));
            if (n) return { owner: layer, circuitNum: n };
        }
        if (!layer.group_id) return null;
        const app = window.app;
        if (!app || typeof app.getScopedPanelKey !== 'function') return null;
        const key = app.getScopedPanelKey(layer.id, panel);
        const members = this._groupDrawnMembers(layer);
        for (const peer of members) {
            if (!peer || peer === layer || peer.id === layer.id) continue;
            // The peer may not have had its render pass yet - preparation runs
            // at the top of each layer's pass - so build its maps on demand.
            // The function is a pure derivation of the layer's own state, so
            // its own pass will simply produce the same maps again. Keyed on
            // the frame counter rather than "does a map exist", because a map
            // left over from the previous frame is exactly the stale tint this
            // is here to avoid; the check also keeps this to once per peer per
            // frame instead of once per cabinet.
            const prepared = this._powerPrepFrame
                && this._powerPrepFrame.get(peer) === (this._renderSeq || 0);
            if (!prepared) this.preparePowerLayerRenderData(peer);
            const scoped = peer._powerPanelCircuitScopedMap;
            if (!(scoped instanceof Map)) continue;
            if (peer._powerError) continue;
            const n = scoped.get(key);
            if (n) return { owner: peer, circuitNum: n };
        }
        return null;
    }

    // The hardware dock's live drop highlight, drawn UNDER a run's own lines
    // from inside the pass that draws them - so it inherits every transform
    // the run itself gets (canvas workspace, mirror, rotation, cross-member
    // shims) instead of re-deriving them and disagreeing on the wall that
    // matters. `num` is the port number in Data view and the circuit number
    // in Power view; a screen-wide target lights every run of the screen.
    //
    // The preview must light the drop's WHOLE reach before release: a multi
    // slot takes every circuit of the multi (or the split-off tail), a
    // distro takes every unassigned multi - lighting only the hovered run
    // made those drops look like one circuit. `t.nums` is that reach where
    // the hit test computed one; without it the target stays what it says
    // (one run, or the whole screen).
    _dockRunUnderlay(panels, layer, num) {
        const t = window.app && window.app._dockDropTarget;
        if (!t || t.layerId !== layer.id) return;
        if (t.kind !== 'run' && t.kind !== 'screen') return;
        const nums = Array.isArray(t.nums) ? t.nums : null;
        if (t.kind === 'run'
                && !(nums ? nums.includes(num) : t.num === num)) return;
        if (t.kind === 'screen' && nums && !nums.includes(num)) return;
        if (!panels || !panels.length) return;
        this.ctx.save();
        this.ctx.strokeStyle = 'rgba(120, 180, 255, 0.55)';
        this.ctx.lineWidth = Math.max(10, 14 / Math.max(this.zoom, 0.01));
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        this.ctx.beginPath();
        panels.forEach((p, i) => {
            const x = p.x + p.width / 2;
            const y = p.y + p.height / 2;
            if (i === 0) this.ctx.moveTo(x, y);
            else this.ctx.lineTo(x, y);
        });
        if (panels.length === 1) {
            // a one-panel run has no line to widen; ring the panel instead
            const p = panels[0];
            this.ctx.arc(p.x + p.width / 2, p.y + p.height / 2,
                         Math.min(p.width, p.height) * 0.4, 0, Math.PI * 2);
        }
        this.ctx.stroke();
        this.ctx.restore();
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
            // v0.9.3: undo the screen's rotation (Pixel Map / Cabinet ID) so the
            // click maps back to the unrotated panel grid before hit-testing.
            const up = this._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
            const lx = up.x;
            const ly = up.y;
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
            const bounds = this.getLayerFootprintInActiveView(layer);
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
        const shadow = this._imageDropShadowParams(layer);
        if (shadow) this._drawImageDropShadow(img, x, y, w, h, shadow);
        this.ctx.drawImage(img, x, y, w, h);
        this.ctx.imageSmoothingEnabled = prevSmoothing;
    }

    // Read + clamp the per-layer Drop Shadow settings. Returns null when the
    // layer has no shadow, so every project made before this existed renders
    // byte for byte the way it always did.
    _imageDropShadowParams(layer) {
        if (!layer || !layer.imageShadowEnabled) return null;
        const num = (v, dflt, lo, hi) => {
            if (v === null || v === undefined || v === '') return dflt;
            const n = Number(v);
            if (!Number.isFinite(n)) return dflt;
            return Math.max(lo, Math.min(hi, n));
        };
        const size = num(layer.imageShadowSize, 10, 0, 250);
        const distance = num(layer.imageShadowDistance, 10, 0, 250);
        // Nothing to draw: no blur, no dilation and no offset means the
        // shadow would sit exactly under the image and never show.
        if (size <= 0 && distance <= 0) return null;
        const color = /^#[0-9a-fA-F]{6}$/.test(String(layer.imageShadowColor || ''))
            ? String(layer.imageShadowColor) : '#000000';
        return {
            color,
            opacity: num(layer.imageShadowOpacity, 75, 0, 100) / 100,
            angle: num(layer.imageShadowAngle, 120, 0, 360),
            distance,
            spread: num(layer.imageShadowSpread, 0, 0, 100) / 100,
            size,
        };
    }

    // Photoshop's Drop Shadow for an image layer, baked into the frame so the
    // PNG/PDF export gets it too (the export runs this same renderer).
    //
    // Deliberately NOT ctx.shadowBlur/shadowOffsetX/shadowColor: those have no
    // Spread at all, and their offset and blur are in DEVICE pixels - the
    // current transform does not touch them - so the shadow would keep its
    // screen size at every zoom and come out the wrong size in every export.
    // They also leak into every later draw unless each path is wrapped in
    // save()/restore(). Everything below is measured in WORLD units and only
    // rasterised at the transform's own scale, so it tracks zoom and export
    // resolution the way the image itself does.
    _drawImageDropShadow(img, x, y, w, h, p) {
        const ctx = this.ctx;
        if (!(w > 0) || !(h > 0)) return;
        // Device pixels per world unit. A mirrored canvas flips the sign of
        // `a`; hypot keeps the magnitude, and the mirror then applies to the
        // composited shadow exactly as it applies to the image.
        let k = 1;
        if (typeof ctx.getTransform === 'function') {
            const t = ctx.getTransform();
            k = Math.hypot(t.a, t.b);
        } else {
            k = this.zoom || 1;
        }
        if (!Number.isFinite(k) || k <= 0) k = 1;

        // Spread is the fraction of Size that is solid before the falloff
        // starts. The two halves share one budget, so the shadow reaches
        // `size` past the silhouette at any spread; +2 covers the blur's tail.
        const solid = p.spread * p.size;
        const soft = p.size - solid;
        const pad = p.size + 2;

        // A deep zoom can ask for a scratch bigger than the browser will
        // allocate. Drop the raster density rather than the shadow.
        const MAX_DIM = 4096;
        const fitW = (w + pad * 2) * k;
        const fitH = (h + pad * 2) * k;
        if (fitW > MAX_DIM || fitH > MAX_DIM) {
            k = k * Math.min(MAX_DIM / fitW, MAX_DIM / fitH);
        }
        const cw = Math.max(1, Math.ceil((w + pad * 2) * k));
        const chh = Math.max(1, Math.ceil((h + pad * 2) * k));

        // The raster only depends on the silhouette, its size on screen, and
        // the two shape settings - Distance, Angle and Opacity are applied
        // when it is composited, further down. So a PAN, which changes neither
        // the scale nor the settings, can reuse the last one.
        //
        // That matters: the dilation below is a getImageData plus two sweeps
        // over every pixel of the scratch, and the scratch grows with zoom to
        // the 4096 cap. Rebuilding it per frame turned a pan into single-digit
        // fps as soon as Spread was above zero. Cached on the image object, so
        // it is bounded by the number of image layers and freed with them.
        const cacheKey = `${cw}x${chh}|${p.spread}|${p.size}|${p.color}`;
        const cached = img._lrdShadowRaster;
        if (cached && cached.key === cacheKey) {
            this._compositeImageShadow(cached.canvas, x, y, w, h, pad, p);
            return;
        }

        let src = this._imageShadowScratch(0, cw, chh);

        // 1. The alpha silhouette, already tinted: draw the image, then paint
        //    the shadow colour through its own alpha with source-in.
        src.ctx.imageSmoothingEnabled = true;
        src.ctx.drawImage(img, pad * k, pad * k, w * k, h * k);
        src.ctx.globalCompositeOperation = 'source-in';
        src.ctx.fillStyle = p.color;
        src.ctx.fillRect(0, 0, cw, chh);
        src.ctx.globalCompositeOperation = 'source-over';

        const hasFilter = ('filter' in src.ctx);
        const solidPx = solid * k;
        const softPx = soft * k;

        // 2a. Spread = dilate the silhouette by `solid` world units, done as a
        //     distance transform plus a threshold (see _dilateAlpha). Two
        //     cheaper-looking options were tried and rejected:
        //
        //     - Stamping the silhouette around a ring of offsets only covers
        //       translates AT the radius, and the union of a shape with its
        //       ring copies is not its union with the whole disc: a thin
        //       stroke comes out striped at the half-radius.
        //     - Blur-then-threshold looks exact on paper (an ideal Gaussian
        //       crosses 15.87% one sigma out) but is not: the browser's blur
        //       is an approximation that Skia downsamples for large sigma, so
        //       the same threshold moved the edge 33px instead of 40 at
        //       sigma 40 - and the error grows as the shape gets small
        //       relative to the spread.
        //
        //     The distance transform has neither problem and is the same at
        //     every zoom, which the Spread test pins to the pixel.
        if (solidPx >= 0.5) {
            try {
                const id = src.ctx.getImageData(0, 0, cw, chh);
                this._dilateAlpha(id, cw, chh, solidPx, this._hexToRgbTriple(p.color));
                src.ctx.putImageData(id, 0, 0);
            } catch (e) {
                // A tainted canvas (an image served cross-origin) blocks the
                // read. Fall through with the undilated silhouette: a
                // narrower shadow beats no shadow and beats a thrown frame.
            }
        }

        // 2b. The remaining falloff. sigma = soft/2 so the visible edge dies
        //     out about `soft` world units from the silhouette, the same way a
        //     CSS box-shadow blur radius reads.
        if (softPx >= 0.5 && hasFilter) {
            const dst = this._imageShadowScratch(1, cw, chh);
            dst.ctx.filter = `blur(${softPx / 2}px)`;
            dst.ctx.drawImage(src.canvas, 0, 0);
            dst.ctx.filter = 'none';
            src = dst;
        }

        // 3. Keep the finished raster on the image, then composite it.
        const keep = document.createElement('canvas');
        keep.width = cw;
        keep.height = chh;
        keep.getContext('2d').drawImage(src.canvas, 0, 0);
        img._lrdShadowRaster = { key: cacheKey, canvas: keep };
        this._compositeImageShadow(keep, x, y, w, h, pad, p);
    }

    // Distance, Angle and Opacity are applied HERE rather than baked into the
    // raster, so dragging any of the three reuses the cached one.
    //
    // Photoshop's angle points at the LIGHT, counter-clockwise from east in a
    // y-up frame; the shadow falls the other way and canvas y grows downward,
    // so the default 120 deg (light upper-left) throws the shadow down-right.
    _compositeImageShadow(raster, x, y, w, h, pad, p) {
        const ctx = this.ctx;
        const rad = p.angle * Math.PI / 180;
        const offX = -p.distance * Math.cos(rad);
        const offY = p.distance * Math.sin(rad);
        ctx.save();
        ctx.globalAlpha = ctx.globalAlpha * p.opacity;
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(raster,
            x - pad + offX, y - pad + offY,
            w + pad * 2, h + pad * 2);
        ctx.restore();
    }

    // Grow an alpha mask outward by `radius` device pixels, in place, and
    // repaint it in `rgb`. This is the Spread half of the drop shadow.
    //
    // A 3-4 chamfer distance transform: two sweeps (down-right, then up-left)
    // build the distance from every transparent pixel to the nearest solid
    // one, in thirds of a pixel, and everything within `radius` becomes
    // solid. The 3/4 step weights approximate Euclidean distance to about 2%,
    // which is well under a pixel at any Spread the UI allows, and unlike a
    // blur it does not care how large the shape is or how the browser
    // implements filters - the edge lands exactly where Spread says.
    _dilateAlpha(imageData, w, h, radius, rgb) {
        const d = imageData.data;
        const n = w * h;
        const INF = 0x3fffffff;
        const dt = new Int32Array(n);
        for (let i = 0, p = 3; i < n; i++, p += 4) {
            dt[i] = d[p] >= 128 ? 0 : INF;
        }
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const i = y * w + x;
                let v = dt[i];
                if (v === 0) continue;
                if (x > 0 && dt[i - 1] + 3 < v) v = dt[i - 1] + 3;
                if (y > 0) {
                    if (dt[i - w] + 3 < v) v = dt[i - w] + 3;
                    if (x > 0 && dt[i - w - 1] + 4 < v) v = dt[i - w - 1] + 4;
                    if (x < w - 1 && dt[i - w + 1] + 4 < v) v = dt[i - w + 1] + 4;
                }
                dt[i] = v;
            }
        }
        for (let y = h - 1; y >= 0; y--) {
            for (let x = w - 1; x >= 0; x--) {
                const i = y * w + x;
                let v = dt[i];
                if (v === 0) continue;
                if (x < w - 1 && dt[i + 1] + 3 < v) v = dt[i + 1] + 3;
                if (y < h - 1) {
                    if (dt[i + w] + 3 < v) v = dt[i + w] + 3;
                    if (x < w - 1 && dt[i + w + 1] + 4 < v) v = dt[i + w + 1] + 4;
                    if (x > 0 && dt[i + w - 1] + 4 < v) v = dt[i + w - 1] + 4;
                }
                dt[i] = v;
            }
        }
        const cut = radius * 3;
        for (let i = 0, p = 0; i < n; i++, p += 4) {
            d[p] = rgb[0];
            d[p + 1] = rgb[1];
            d[p + 2] = rgb[2];
            d[p + 3] = dt[i] <= cut ? 255 : 0;
        }
    }

    // Two reusable scratch canvases for the shadow pass. Allocating a fresh
    // pair per layer per frame churned enough memory to stutter a pan.
    _imageShadowScratch(index, w, h) {
        if (!this._imgShadowScratch) this._imgShadowScratch = [];
        let s = this._imgShadowScratch[index];
        if (!s) {
            const canvas = document.createElement('canvas');
            s = { canvas, ctx: canvas.getContext('2d', { willReadFrequently: true }) };
            this._imgShadowScratch[index] = s;
        }
        // Assigning width/height also clears the canvas; only clear by hand
        // when the size is already right.
        if (s.canvas.width !== w || s.canvas.height !== h) {
            s.canvas.width = w;
            s.canvas.height = h;
        } else {
            s.ctx.clearRect(0, 0, w, h);
        }
        s.ctx.globalCompositeOperation = 'source-over';
        s.ctx.globalAlpha = 1;
        if ('filter' in s.ctx) s.ctx.filter = 'none';
        return s;
    }

    _hexToRgbTriple(hex) {
        const m = /^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(String(hex || ''));
        if (!m) return [0, 0, 0];
        return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
    }

    renderTextLayer(layer) {
        if (!layer) return;
        // Check per-tab visibility
        const viewMode = this.viewMode || 'pixel-map';
        if (viewMode === 'pixel-map' && !layer.showOnPixelMap) return;
        if (viewMode === 'cabinet-id' && !layer.showOnCabinetId) return;
        if (viewMode === 'data-flow' && !layer.showOnDataFlow) return;
        if (viewMode === 'power' && !layer.showOnPower) return;
        // v0.8.3: Show Look is its own tab and needs an independent gate.
        // Default true so existing projects don't suddenly hide text on it.
        if (viewMode === 'show-look' && layer.showOnShowLook === false) return;

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

        // Per-tab text content. Fallback chain:
        //   1. This tab's own textContent<Tab> (explicit per-tab override)
        //   2. The global textContent (legacy default)
        //   3. ANY other per-tab field that's non-empty (so typing into one
        //      tab carries over to the others until the user explicitly
        //      sets a different value per tab). Without this third step,
        //      typing only in Pixel Map left Cabinet ID / Data Flow / Power
        //      / Show Look rendering blank.
        // v0.8.3: shared `textContent` is the default for every tab. Each
        // tab also has an override flag (`textContentOverride<Tab>`); when
        // on, that tab uses its own `textContent<Tab>` field instead of the
        // shared one. Legacy projects (pre-v0.8.3) may have content only in
        // the per-tab fields with `textContent` empty: fall back to whichever
        // per-tab field is non-empty so nothing visually disappears.
        const tabKey = (viewMode === 'pixel-map')  ? 'textContentPixelMap'
                     : (viewMode === 'cabinet-id') ? 'textContentCabinetId'
                     : (viewMode === 'show-look')  ? 'textContentShowLook'
                     : (viewMode === 'data-flow')  ? 'textContentDataFlow'
                     : (viewMode === 'power')      ? 'textContentPower'
                     : null;
        const overrideKey = (viewMode === 'pixel-map')  ? 'textContentOverridePixelMap'
                          : (viewMode === 'cabinet-id') ? 'textContentOverrideCabinetId'
                          : (viewMode === 'show-look')  ? 'textContentOverrideShowLook'
                          : (viewMode === 'data-flow')  ? 'textContentOverrideDataFlow'
                          : (viewMode === 'power')      ? 'textContentOverridePower'
                          : null;
        let text = '';
        if (overrideKey && layer[overrideKey]) {
            text = (tabKey ? layer[tabKey] : '') || '';
        } else {
            text = layer.textContent || '';
        }
        if (!text) {
            const fallbackKeys = ['textContentPixelMap', 'textContentCabinetId',
                                  'textContentShowLook', 'textContentDataFlow',
                                  'textContentPower'];
            for (const k of fallbackKeys) {
                if (layer[k]) { text = layer[k]; break; }
            }
        }

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
                    // A project may legitimately span voltages - two walls on
                    // different supplies. getPowerCounts refuses to blend them
                    // (the combined amps come back NULL, because 800 W at 110 V
                    // plus 800 W at 208 V is not 1600 W at either), so print a
                    // line PER VOLTAGE instead of one figure belonging to
                    // neither wall. Calling .toFixed on the null combined value
                    // used to take the whole renderer down.
                    const perVoltage = pwr.voltageMismatch && Array.isArray(pwr.byVoltage)
                        ? pwr.byVoltage.filter(b => b && b.circuits > 0)
                        : null;
                    if (perVoltage && perVoltage.length > 0) {
                        perVoltage.forEach(b => {
                            if (layer.showCircuits) {
                                dynamicLines.push(`Circuits${pass.suffix} @ ${b.voltage}V: ${b.circuits}`);
                            }
                            if (layer.showSinglePhase) {
                                dynamicLines.push(`1-Phase${pass.suffix} @ ${b.voltage}V: ${b.amps1ph.toFixed(2)}A`);
                            }
                            if (layer.showThreePhase && b.circuits >= 3) {
                                dynamicLines.push(`3-Phase${pass.suffix} @ ${b.voltage}V: ${b.amps3ph.toFixed(2)}A`);
                            }
                        });
                    } else {
                        if (layer.showCircuits && pwr.circuits > 0) {
                            dynamicLines.push(`Circuits${pass.suffix}: ${pwr.circuits} @ ${pwr.voltage}V`);
                        }
                        if (layer.showSinglePhase && pwr.circuits > 0 && pwr.singlePhaseAmps != null) {
                            dynamicLines.push(`1-Phase${pass.suffix}: ${pwr.singlePhaseAmps.toFixed(2)}A`);
                        }
                        if (layer.showThreePhase && pwr.circuits >= 3 && pwr.threePhaseAmps != null) {
                            dynamicLines.push(`3-Phase${pass.suffix}: ${pwr.threePhaseAmps.toFixed(2)}A`);
                        }
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
        // v0.8.7.8: bump a per-render token so screen-fill gradients are built
        // at most once per layer per frame (cached on the layer keyed by this).
        this._renderPass = (this._renderPass || 0) + 1;
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

        // v0.8.6: Wiring-view perspective is per-canvas. Each canvas
        // independently applies its own mirror transform inside the
        // per-canvas render loop below (around its own right edge), so c1
        // can show Front while c2 shows Back simultaneously. The legacy
        // global-mirror block here used to flip the entire workspace
        // around the bbox right edge, which forced every canvas into the
        // same perspective. _fillText / _strokeText still key off
        // this._mirror, that flag is now toggled on/off per canvas as the
        // loop enters/exits each canvas's draw scope.
        this._mirror = false;
        // v0.11.0: the per-layer passes below queue any manual path that
        // crosses into a group peer; _renderCrossMemberPaths drains the queue
        // once every layer has been drawn. Cleared here so a frame that threw
        // part way through cannot carry an owner into the next one.
        this._crossMemberOwners = [];
        this._crossMemberPass = false;
        // v0.11.0: frame counter, so _powerCircuitForPanel can tell a peer's
        // circuit maps it built itself THIS frame from ones left over from the
        // last one. Without it a peer drawn after its owner would keep tinting
        // from a stale map for one frame after every edit.
        this._renderSeq = (this._renderSeq || 0) + 1;
        // Legacy single-canvas projects (no canvases array) keep the old
        // global mirror so v0.7 fallbacks render correctly.
        const _legacyNoCanvases = !window.app || !window.app.project
            || !Array.isArray(window.app.project.canvases)
            || window.app.project.canvases.length === 0;
        if (_legacyNoCanvases && this.isMirroredView()) {
            this._mirror = true;
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
            const cid = this._effectiveLayerCanvasId(layer);
            const c = cid ? _canvasById[cid] : null;
            // v0.8.5.3: pick the right workspace position per view.
            return this._canvasWorkspace(c);
        };
        // Helper: returns true if this layer's canvas is hidden (canvas-level
        // eye toggle off). Used to skip every per-layer post-pass for hidden
        // canvases, without this, hiding a canvas removed only its outline
        // while its layers continued to render at the canvas's workspace
        // offset.
        const _layerCanvasHidden = (layer) => {
            const cid = this._effectiveLayerCanvasId(layer);
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
            // v0.8.6: post-passes (capacity error overlay, selection
            // bounds) run AFTER the per-canvas render loop popped its
            // mirror, so re-apply the layer's canvas mirror here too -
            // otherwise overlays render in un-mirrored space and float
            // detached from the layer they're badging.
            const _cid = this._effectiveLayerCanvasId(layer);
            const _c = _cid ? _canvasById[_cid] : null;
            const _layerMirror = _c && this._isCanvasMirrored(_c);
            if (wx || wy || _layerMirror) {
                this.ctx.save();
                if (wx || wy) this.ctx.translate(wx, wy);
                if (_layerMirror) {
                    const _crw = (this.isShowLookView() && _c.show_raster_width)
                        || _c.raster_width || 0;
                    this.ctx.translate(_crw, 0);
                    this.ctx.scale(-1, 1);
                    this._mirror = true;
                }
                fn();
                if (_layerMirror) this._mirror = false;
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
                    // v0.8.5: in Show Look / Data / Power, group by the
                    // layer's effective show canvas (show_canvas_id ||
                    // canvas_id). Pixel Map / Cabinet ID still group by
                    // canvas_id, the helper handles the view-mode pick.
                    return this._effectiveLayerCanvasId(l) === canvas.id;
                });
                // Empty canvases (no layers) still get drawn, outline +
                // active tint, so the user can see the canvas exists and can
                // drag layers into it. Slice 7 cross-canvas drag depends on
                // this being a valid drop target. Originally Slice 3 skipped
                // empty canvases entirely, but that hid them from the
                // workspace which broke the drop-into-empty-canvas flow.
                // v0.8.5.3: in Show Look use the canvas's show workspace pos.
                const _ws = this._canvasWorkspace(canvas);
                const wx = _ws.wx;
                const wy = _ws.wy;
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
                // v0.8.6: per-canvas mirror. Each canvas applies its own
                // Front/Back transform around its own right edge so other
                // canvases are unaffected. _mirror flag drives label
                // un-mirroring inside _fillText / _strokeText for the
                // duration of this canvas's layer pass.
                const _canvasMirror = this._isCanvasMirrored(canvas);
                if (_canvasMirror) {
                    this.ctx.save();
                    const _crw = (this.isShowLookView() && canvas.show_raster_width)
                        || canvas.raster_width || 0;
                    this.ctx.translate(_crw, 0);
                    this.ctx.scale(-1, 1);
                    this._mirror = true;
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

                    // v0.9.3: screen rotation (Pixel Map / Cabinet ID only). Rotate
                    // the cabinets and all labels around the screen's center. The
                    // corner X,Y readouts stay upright, drawn after the restore.
                    const _rotDeg = this._layerRotationDeg(layer);
                    const _rotating = (_rotDeg === 90 || _rotDeg === 180 || _rotDeg === 270);
                    if (_rotating) {
                        // Clip to the raster in UNROTATED (screen) space first, so any
                        // rotated content that falls off-canvas simply isn't drawn -
                        // the same clip rule unrotated screens have always had.
                        this.ctx.save();
                        this.ctx.beginPath();
                        this.ctx.rect(-dx, -dy, this.rasterWidth, this.rasterHeight);
                        this.ctx.clip();
                        this._layerRotating = true;
                        // Angle used to keep specific labels upright (Data/Power
                        // technical labels only), see _fillText / _keepTextUpright.
                        this._activeRotationRad = _rotDeg * Math.PI / 180;
                        this._beginLayerRotation(layer);   // rotate in place (own save)
                    }

                    layer.panels.forEach(panel => {
                        // Cheap early skip for panels entirely outside the raster.
                        // Skip this optimization while rotating, a rotated panel
                        // may land inside the view even if its unrotated pos is out.
                        if (!_rotating && (panel.x + dx >= this.rasterWidth || panel.y + dy >= this.rasterHeight)) return;

                        // Render all panels - visible and hidden (hidden as ghost outlines)
                        this.renderPanel(panel, layer);
                    });

                    // Render Circle with X test pattern. Every condition lives
                    // inside, because a group draws ONE pattern across its
                    // members and the decision about which member draws it
                    // cannot be made from this layer alone.
                    this.renderCircleWithX(layer);

                    // Render Cabinet ID numbers in world space (scales with zoom)
                    if (this.viewMode === 'cabinet-id') {
                        this.renderCabinetIDNumbers(layer);
                    }

                    // Data/Power flow arrows rotate with the panels, but their
                    // technical labels (P1/R1, port/circuit info) stay upright.
                    if (this.viewMode === 'data-flow') {
                        this._keepTextUpright = _rotating;
                        this.renderDataFlowArrows(layer);
                        this._keepTextUpright = false;
                    }
                    if (this.viewMode === 'power') {
                        this._keepTextUpright = _rotating;
                        this.renderPowerArrows(layer);
                        // Brackets draw only when explicitly ticked (=== true,
                        // matching the soca panel's checkbox): the user asked
                        // for them off by default.
                        if (layer.showSocaBrackets === true) this.renderSocaBrackets(layer);
                        this._keepTextUpright = false;
                    }

                    // Render labels as part of each layer so upper layers naturally
                    // paint over lower layers' labels (no bleed-through). The screen
                    // name rotates with the screen (keepTextUpright is off here).
                    this.renderLayerLabels(layer);

                    // v0.9.3: end the rotation before the corner readouts so the
                    // X,Y coordinates stay upright and unrotated.
                    if (_rotating) {
                        this.ctx.restore();          // pop the rotation transform
                        this._layerRotating = false;
                        this._keepTextUpright = false;
                        this._activeRotationRad = 0;
                        this.ctx.restore();          // pop the raster clip
                    }

                    // Render offsets / corner X,Y readouts (pixel-map only), upright
                    this.renderLayerOffsets(layer);

                    if (needsShift) this.ctx.restore();
                }
                });
                // v0.8.6: pop per-canvas mirror so the outline draws in
                // un-mirrored space (and so the next canvas's mirror
                // decision is independent).
                if (_canvasMirror) {
                    this.ctx.restore();
                    this._mirror = false;
                }
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

            // v0.11.0 screen groups: the manual paths that cross from one member
            // to the next, drawn now that every member's cabinets are down.
            // Deliberately NOT gated on exportMode - a wall wired across two
            // members has to appear on the printed map too, and drawing it here
            // is also the only way it survives being covered by a peer that
            // renders after its owner.
            if (this.viewMode === 'data-flow' || this.viewMode === 'power') {
                this._renderCrossMemberPaths(this.viewMode === 'power' ? 'power' : 'data');
            }

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
                        const bounds = this.getLayerFootprintInActiveView(layer);
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
                        const bounds = this.getLayerFootprintInActiveView(selectedLayer);
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

            // The landing pulse (pulseLayer): a transient outline that grows
            // and fades over the pulsed layer for ~1.2s, so "center on this
            // screen" ends with the eye on the right wall. Pure view state -
            // it self-clears by time, never touches the project, and skips
            // exports entirely. The animation rides ONE queued frame at a
            // time rather than a timer: render() is called from everywhere,
            // and a second scheduler would double-draw.
            if (!this.exportMode && this._pulse) {
                const now = performance.now();
                if (now >= this._pulse.until) {
                    this._pulse = null;
                } else {
                    const layer = window.app.project.layers.find(
                        l => String(l.id) === String(this._pulse.layerId));
                    if (layer && layer.visible) {
                        _withLayerWs(layer, () => {
                            const b = this.getLayerFootprintInActiveView(layer);
                            // 0 at the click, 1 at the fade's end.
                            const t = 1 - (this._pulse.until - now)
                                / this._pulse.span;
                            const grow = (4 + 16 * t) / this.zoom;
                            this.ctx.save();
                            this.ctx.strokeStyle =
                                `rgba(255, 85, 85, ${0.85 * (1 - t)})`;
                            this.ctx.lineWidth = 3 / this.zoom;
                            this.ctx.strokeRect(b.x - grow, b.y - grow,
                                                b.width + grow * 2,
                                                b.height + grow * 2);
                            this.ctx.restore();
                        });
                    }
                    if (!this._pulseFrame) {
                        this._pulseFrame = requestAnimationFrame(() => {
                            this._pulseFrame = null;
                            this.render();
                        });
                    }
                }
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
    
    // The circle-and-X is a test pattern for THE WALL - you look at it to see
    // the wall is whole and square. A group is one wall, so it gets ONE
    // pattern spanning its members, not a circle per screen: two half-metre
    // sections beside a one-metre section would otherwise show three separate
    // circles on a wall that is meant to read as one.
    //
    // Drawn in the HOST's pass (the last member in render order) so it lands
    // on top of every member's cabinets, and sized from the union of their
    // bounds - the same host/union pair renderLayerLabels already uses for the
    // group's single name label, expressed in the host's own draw space.
    //
    // An ungrouped screen, or a group with only one drawn member, takes the
    // untouched original path.
    renderCircleWithX(layer) {
        if (this.viewMode !== 'pixel-map' || (layer.type || 'screen') === 'image') return;
        const plan = this._groupLabelPlan(layer);
        // show_circle_with_x is a shared group field, but read it off the same
        // member that supplies the label config so the group has ONE answer
        // even in a project saved before that field was shared.
        const cfg = plan ? plan.cfg : layer;
        if (!cfg.show_circle_with_x) return;
        // Peers bow out; only the host draws, exactly once for the group.
        if (plan && layer !== plan.host) return;

        const bounds = plan
            ? this._groupUnionBounds(plan.members, plan.host)
            : this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;

        // Circle radius is about 40% of the smaller dimension (based on professional LED software reference)
        const radius = Math.min(layerWidth, layerHeight) * 0.40;

        // Save context and clip to active raster bounds (translate-aware)
        this.ctx.save();
        this._clipToActiveRaster();

        // v0.11.0: the group's pattern is measured across the whole wall
        // (_groupUnionBounds), so it must not be turned about the HOST member's
        // centre - the render loop is inside _beginLayerRotation(host) here.
        // Cancel that for the pattern only; the ctx.save above pops it. A lone
        // screen keeps rotating with its own pattern, as it always has.
        if (plan) this._unrotateLayerInPlace(layer);

        this.ctx.strokeStyle = this.getLayerBorderColor(cfg, 'pixel-map');
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
            // v0.8.5.3: workspace bbox uses the active view's canvas position.
            const ws = this._canvasWorkspace(c);
            const wx = ws.wx;
            const wy = ws.wy;
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

    /**
     * Arm the landing pulse on a layer for ~1.2s and kick a frame; the
     * render pass draws (and eventually clears) it. View state only - the
     * caller centering the canvas (app-dock.js centerCanvasOnLayer) has
     * already moved the pan, and neither half earns an undo entry.
     */
    pulseLayer(layerId) {
        const span = 1200;
        this._pulse = { layerId, span, until: performance.now() + span };
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
            // v0.8.5: zoom-to-layer in Show Look / Data / Power must use
            // the layer's effective show canvas (show_canvas_id), since the
            // layer renders at THAT canvas's workspace position there.
            const zoomCanvasId = this._effectiveLayerCanvasId(layer);
            if (window.app.project && window.app.project.canvases && zoomCanvasId) {
                const c = window.app.project.canvases.find(c => c.id === zoomCanvasId);
                if (c) {
                    // v0.8.5.3: pick the right workspace position per view.
                    const ws = this._canvasWorkspace(c);
                    wx = ws.wx; wy = ws.wy;
                }
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
            // v0.8.5.3: snap-to-neighbor in Show Look uses each canvas's
            // show workspace position (falls back to workspace_x/y when
            // null). Without this, snapping in Show Look targeted Pixel
            // Map positions and the just-dropped canvas could trigger a
            // false "overlap" toast against a neighbor's stale pixel-map
            // bounds that no longer reflects its show position.
            const _ws = this._canvasWorkspace(other);
            const ox = _ws.wx;
            const oy = _ws.wy;
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
        // Zoom-consistent snap zone (~14 screen px, same feel as the canvas
        // snap), capped at 60 raster px so a zoomed-out view can't grab the
        // screen from a whole cabinet-width away.
        const snapDistance = Math.min(14 / (this.zoom || 1), 60);

        // v0.9.3: snap by the rotated FOOTPRINT. It's centered on the screen, so
        // its top-left sits at offset + fpD (fpD = 0 when unrotated). We snap the
        // footprint edges, then convert the result back to the layer offset.
        const b = this.getLayerBounds(currentLayer);
        const swap = this._layerRotationDeg(currentLayer) === 90 || this._layerRotationDeg(currentLayer) === 270;
        const layerWidth = swap ? b.height : b.width;
        const layerHeight = swap ? b.width : b.height;
        const fpDx = (b.width - layerWidth) / 2;
        const fpDy = (b.height - layerHeight) / 2;

        const currentLeft = offsetX + fpDx;
        const currentRight = currentLeft + layerWidth;
        const currentTop = offsetY + fpDy;
        const currentBottom = currentTop + layerHeight;

        // v0.11.0: a screen group snaps as ONE object. The edges offered to the
        // snap are the UNION of the group's footprints (so the wall's left edge
        // is its left-most member's), and the peers are dropped as snap TARGETS
        // - they travel with the drag, so snapping to one would only ever pin
        // the group to itself. Every member takes the same delta during a drag,
        // so a peer's proposed edges are its current edges shifted by whatever
        // the primary is proposing.
        const peerIds = new Set();
        let groupLeft = currentLeft;
        let groupRight = currentRight;
        let groupTop = currentTop;
        let groupBottom = currentBottom;
        const groupMembers = this._groupDrawnMembers(currentLayer);
        if (groupMembers.length > 1) {
            const selfNow = this.getLayerFootprintInActiveView(currentLayer);
            groupMembers.forEach(m => {
                peerIds.add(m.id);
                if (m.id === currentLayer.id) return;
                const mb = this.getLayerFootprintInActiveView(m);
                const relX = mb.x - selfNow.x;
                const relY = mb.y - selfNow.y;
                groupLeft = Math.min(groupLeft, currentLeft + relX);
                groupRight = Math.max(groupRight, currentLeft + relX + mb.width);
                groupTop = Math.min(groupTop, currentTop + relY);
                groupBottom = Math.max(groupBottom, currentTop + relY + mb.height);
            });
        }

        // v0.10.1: the NEAREST candidate wins on each axis. The old code let
        // whichever candidate was checked last overwrite the rest, so dragging
        // toward the raster's left edge could land at a far layer's edge
        // instead (e.g. -40 rather than 0). Raster edges are seeded first so
        // they win exact ties (strict < keeps the earlier candidate).
        let bestX = null;
        let bestY = null;
        const considerX = (edgePos, target, resultOffset) => {
            const dist = Math.abs(edgePos - target);
            if (dist <= snapDistance && (!bestX || dist < bestX.dist)) bestX = { value: resultOffset, dist };
        };
        const considerY = (edgePos, target, resultOffset) => {
            const dist = Math.abs(edgePos - target);
            if (dist <= snapDistance && (!bestY || dist < bestY.dist)) bestY = { value: resultOffset, dist };
        };

        // Snap to raster boundaries, HARD EDGES ONLY.
        // v0.11.0: every candidate below is now written as "the offset that
        // puts THIS edge on THAT target" - offsetX + (target - edge). For an
        // ungrouped layer the group edges ARE the layer's edges, so each of
        // these still evaluates to exactly what it did before.
        considerX(groupLeft, 0, offsetX + (0 - groupLeft));
        considerX(groupRight, this.rasterWidth, offsetX + (this.rasterWidth - groupRight));
        considerY(groupTop, 0, offsetY + (0 - groupTop));
        considerY(groupBottom, this.rasterHeight, offsetY + (this.rasterHeight - groupBottom));

        // Snap to other layers' footprints, HARD EDGES ONLY.
        // v0.10.1: only layers that are neighbors on the perpendicular axis
        // (ranges overlap, or nearly touch within the snap zone) attract a
        // snap. A screen far above shouldn't grab a screen dragged along the
        // raster's bottom just because their widths line up.
        if (window.app && window.app.project) {
            window.app.project.layers.forEach(layer => {
                if (layer.id === currentLayer.id || !layer.visible) return;
                if (peerIds.has(layer.id)) return;   // travels with the drag

                const otherBounds = this.getLayerFootprintInActiveView(layer);
                const otherLeft = otherBounds.x;
                const otherRight = otherBounds.x + otherBounds.width;
                const otherTop = otherBounds.y;
                const otherBottom = otherBounds.y + otherBounds.height;

                const nearVertically = groupTop <= otherBottom + snapDistance &&
                    groupBottom >= otherTop - snapDistance;
                const nearHorizontally = groupLeft <= otherRight + snapDistance &&
                    groupRight >= otherLeft - snapDistance;

                if (nearVertically) {
                    // Left edge snaps
                    considerX(groupLeft, otherLeft, offsetX + (otherLeft - groupLeft));
                    considerX(groupLeft, otherRight, offsetX + (otherRight - groupLeft));
                    // Right edge snaps
                    considerX(groupRight, otherLeft, offsetX + (otherLeft - groupRight));
                    considerX(groupRight, otherRight, offsetX + (otherRight - groupRight));
                }
                if (nearHorizontally) {
                    // Top edge snaps
                    considerY(groupTop, otherTop, offsetY + (otherTop - groupTop));
                    considerY(groupTop, otherBottom, offsetY + (otherBottom - groupTop));
                    // Bottom edge snaps
                    considerY(groupBottom, otherTop, offsetY + (otherTop - groupBottom));
                    considerY(groupBottom, otherBottom, offsetY + (otherBottom - groupBottom));
                }
            });
        }

        return {
            x: Math.round(bestX ? bestX.value : offsetX),
            y: Math.round(bestY ? bestY.value : offsetY)
        };
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
        // v0.9.3: while the layer is rotated, skip the raster clip (its rect would
        // be wrong in rotated space); the panel still draws inside its own bounds.
        if (this._layerRotating) {
            this.ctx.save();
        } else {
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
        }

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
    
    // v0.8.7.8: build a CanvasGradient spanning the layer's bounding box in
    // the current ctx coordinate space. Because canvas gradients live in user
    // space, the SAME gradient used as the fill for each panel rect renders as
    // one continuous gradient across the whole screen (and naturally skips
    // blank/half/hidden panels, which never fill).
    // v0.8.7.8: base cabinet fill. Default is the legacy 2-color checkerboard
    // (color1/color2 via panel.is_color1). When panelColorMode selects a
    // palette distribution and panelColors has entries, each cabinet samples a
    // color from the palette by its grid position.
    _panelBaseFill(panel, layer) {
        const mode = layer.panelColorMode || 'checker';
        const pal = Array.isArray(layer.panelColors) ? layer.panelColors : [];
        if (mode !== 'checker' && pal.length >= 1) {
            const cols = Math.max(1, Number(layer.columns) || 1);
            const r = Number(panel.row) || 0;
            const c = Number(panel.col) || 0;
            let idx;
            switch (mode) {
                case 'diagonal': idx = (r + c) % pal.length; break;        // ORACLE wave
                case 'cycle': idx = (r * cols + c) % pal.length; break;
                case 'row': idx = r % pal.length; break;
                case 'column': idx = c % pal.length; break;
                default: idx = 0;
            }
            return pal[((idx % pal.length) + pal.length) % pal.length] || '#000000';
        }
        // v0.11.0: a layer with no color1/color2 used to throw here, and because
        // this runs per panel it took the WHOLE render down - one malformed
        // layer blanked the canvas rather than just itself. create_layer always
        // sets both, but a hand-built or hand-edited layer need not, and that
        // was reliably breaking 31 browser tests. Fall back to the other colour,
        // then to a neutral grey, rather than letting a missing field crash.
        const rgb = (c) => (c && Number.isFinite(Number(c.r)) && Number.isFinite(Number(c.g))
            && Number.isFinite(Number(c.b))) ? c : null;
        const color = rgb(panel.is_color1 ? layer.color1 : layer.color2)
            || rgb(panel.is_color1 ? layer.color2 : layer.color1)
            || { r: 128, g: 128, b: 128 };
        return `rgb(${color.r}, ${color.g}, ${color.b})`;
    }

    _buildGradientForRect(layer, x, y, w, h, invert) {
        const ctx = this.ctx;
        let stops = Array.isArray(layer.gradientStops) ? layer.gradientStops.slice() : [];
        if (stops.length < 2) {
            stops = [{ pos: 0, color: '#000000' }, { pos: 1, color: '#ffffff' }];
        }
        // invert = mirror the gradient (pos → 1-pos); used to flip alternating
        // cabinets in per-panel mode so adjacent panels mirror each other.
        if (invert) stops = stops.map(s => ({ pos: 1 - (Number(s.pos) || 0), color: s.color }));
        stops.sort((a, b) => (Number(a.pos) || 0) - (Number(b.pos) || 0));
        let grad;
        if ((layer.gradientType || 'linear') === 'radial') {
            // Center is a fraction of the rect (0.5 = middle); radius is a
            // multiplier of the rect's base radius (max(w,h)/2).
            const fx = (layer.gradientRadialCenterX != null) ? layer.gradientRadialCenterX : 0.5;
            const fy = (layer.gradientRadialCenterY != null) ? layer.gradientRadialCenterY : 0.5;
            const rs = (layer.gradientRadialRadius != null) ? layer.gradientRadialRadius : 1;
            const cx = x + w * fx;
            const cy = y + h * fy;
            const r = Math.max(1, (Math.max(w, h) / 2) * rs);
            grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        } else {
            // angle: 0 = left→right, 90 = top→bottom (canvas +y is down).
            const angle = ((Number(layer.gradientAngle) || 0) * Math.PI) / 180;
            const dx = Math.cos(angle);
            const dy = Math.sin(angle);
            const cx = x + w / 2;
            const cy = y + h / 2;
            // Project the box half-extent onto the gradient direction so the
            // 0 and 1 stops land on the bounding edges along that angle.
            const half = (Math.abs(dx) * w + Math.abs(dy) * h) / 2 || 1;
            grad = ctx.createLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half);
        }
        stops.forEach(s => {
            const p = Math.min(1, Math.max(0, Number(s.pos) || 0));
            try { grad.addColorStop(p, s.color || '#000000'); } catch (_) {}
        });
        return grad;
    }

    // Memoized per-layer-per-render gradient spanning the whole screen. Safe to
    // call once per panel. (Per-panel spread builds its own gradient per rect.)
    _screenGradientFor(layer) {
        if (layer._gradPass !== this._renderPass) {
            const b = this.getLayerBounds(layer);
            layer._gradObj = this._buildGradientForRect(layer, b.x, b.y, b.width, b.height);
            layer._gradPass = this._renderPass;
        }
        return layer._gradObj;
    }

    // Map a friendly gradient blend name to a canvas globalCompositeOperation.
    _gradientCompositeOp(name) {
        if (!name || name === 'normal') return 'source-over';
        // The remaining names match canvas composite operations 1:1.
        return name;
    }

    // Composite the gradient over a single panel rect (called after the
    // checkerboard fill, before borders). No-op unless the layer opts in.
    // gradientScope 'screen' = one continuous gradient across the whole screen;
    // 'panel' = the gradient is mapped to each cabinet individually.
    _applyGradientOverlay(panel, layer) {
        if (!layer || !layer.gradientEnabled) return;
        let grad;
        if (layer.gradientScope === 'panel') {
            // Mirror the gradient on alternating COLUMNS (a whole column shares
            // one orientation; every other column flips), the SUPERTASK wave.
            const invert = !!layer.gradientPanelAlternate
                && ((Number(panel.col) || 0) % 2 === 1);
            grad = this._buildGradientForRect(layer, panel.x, panel.y, panel.width, panel.height, invert);
        } else {
            grad = this._screenGradientFor(layer);
        }
        if (!grad) return;
        this.ctx.save();
        this.ctx.globalAlpha = (layer.gradientOpacity != null) ? layer.gradientOpacity : 0.6;
        this.ctx.globalCompositeOperation = this._gradientCompositeOp(layer.gradientBlend);
        this.ctx.fillStyle = grad;
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
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
        
        // Base cabinet fill: 2-color checkerboard or multi-color palette.
        // transparentFill = render cabinets see-through (no fill / no gradient);
        // borders and labels still draw on top.
        if (!layer.transparentFill) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            // v0.8.7.8: gradient overlay on top of the checkerboard, below borders.
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width in LED pixels, drawn INSIDE the
        // panel. Where two panels meet, you get 2× the width total.
        if (layer.show_panel_borders) {
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'pixel-map');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
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
        
        // Base cabinet fill: 2-color checkerboard or multi-color palette.
        // transparentFill = render cabinets see-through (no fill / no gradient).
        if (!layer.transparentFill) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            // v0.8.7.8: gradient overlay on top of the checkerboard, below borders.
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width, drawn INSIDE the panel.
        if (layer.show_panel_borders) {
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'cabinet-id');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
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
        
        // Base cabinet fill: checkerboard / palette, same as Pixel Map, with
        // the gradient overlay on top (below borders and flow arrows). These
        // used to hard-code the plain checkerboard, so gradients, palette
        // modes, and Transparent (no fill) were all ignored on the Data view.
        if (!layer.transparentFill) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width, drawn INSIDE the panel.
        if (layer.show_panel_borders) {
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'data-flow');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
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
        this.ctx.font = `bold 48px ${projectFontFamily()}`;
        const titleText = `CANNOT FIT COMPLETE ${err.unitType.toUpperCase()}`;
        const titleWidth = this.ctx.measureText(titleText).width;
        
        this.ctx.font = `28px ${projectFontFamily()}`;
        const detailText = `Need ${err.unitCount} panels, port only fits ${err.panelsPerPort}`;
        const detailWidth = this.ctx.measureText(detailText).width;
        
        this.ctx.font = `24px ${projectFontFamily()}`;
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
        this.ctx.font = `bold 48px ${projectFontFamily()}`;
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        this._fillText(titleText, layerCenterX, layerCenterY - 35);
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = `28px ${projectFontFamily()}`;
        this._fillText(detailText, layerCenterX, layerCenterY + 10);
        this.ctx.font = `24px ${projectFontFamily()}`;
        this.ctx.fillStyle = '#AAAAAA';
        this._fillText(infoText, layerCenterX, layerCenterY + 45);
    }

    // v0.11.0: pixel load of ONE port, in the same terms calculatePortAssignments
    // charged it. The accounting differs per processor and both forms live here
    // so the custom-path branch (which never goes through calculatePortAssignments)
    // is scored the same way the automatic map is:
    //   - rectangle-constraint processors (NovaStar Armor) pay for the pixel
    //     RECTANGLE that encloses every visible cabinet in the port, holes and
    //     all - the same rect calcBoundingRectLoad builds;
    //   - everything else pays the sum of the cabinets' pixel areas, which for
    //     these processors is exactly the running `load` the port map used
    //     (hidden cabinets never reach the traversal there, getOrderedPanelsByPattern
    //     drops them unless the processor is a rectangle one).
    //
    // v0.11.0 screen groups: the rectangle branch unions raw p.x / p.y across
    // the port's cabinets, and for a port that runs onto a group peer that is
    // still the right thing - panel coords are laid out from layer.offset_x by
    // _build_panels, so they are CANVAS-relative, and two members of the same
    // processor canvas already share one frame. Converting to show-look world
    // coords first would be actively wrong: it would fold in each member's
    // Show Look offset, which is where the screen was dragged for the show
    // file, not where the processor sees the pixels. The frame is enforced by
    // the caller (_crossMemberLoadPanels refuses a port whose cabinets straddle
    // two processor rasters, which Show Look's show_canvas_id can produce).
    getPortPixelLoad(layer, portPanels) {
        const app = window.app;
        if (!app || !layer || !Array.isArray(portPanels)) return 0;
        const visible = portPanels.filter(p => p && !p.hidden);
        if (visible.length === 0) return 0;

        const usesRectangle = typeof app.usesRectangleConstraint === 'function'
            && app.usesRectangleConstraint(layer.processorType || 'novastar-armor');
        if (!usesRectangle) {
            return visible.reduce((sum, p) => sum + app.getPanelPixelArea(p), 0);
        }

        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        visible.forEach(p => {
            const x1 = Number(p.x) || 0;
            const y1 = Number(p.y) || 0;
            const x2 = x1 + (Number(p.width) || 0);
            const y2 = y1 + (Number(p.height) || 0);
            if (x1 < minX) minX = x1;
            if (y1 < minY) minY = y1;
            if (x2 > maxX) maxX = x2;
            if (y2 > maxY) maxY = y2;
        });
        return (maxX - minX) * (maxY - minY);
    }

    // v0.11.0: capacity of ONE port, so a percentage is always measured against
    // the capacity THAT port actually has. The base figure is the app's own
    // table lookup (never re-derived here); on NovaStar Low Latency the
    // (1 - Y/H) derate is then applied from the port's OWN topmost cabinet,
    // exactly as calculatePortAssignments does, so a port that starts low on
    // the canvas is scored against its reduced figure and not the table value.
    // layer._lowLatencyDerate is the sidebar note's layer-wide summary, so it
    // is only a fallback here - it carries the worst case, not this port's.
    //
    // v0.11.0: the NovaStar 5G narrow-port penalty is then subtracted, from
    // this port's OWN bounding box, in the same order calculatePortAssignments
    // uses (table value -> Y-derate -> penalty). Without it a penalised 5G port
    // would be scored as a percentage of a capacity it does not have.
    //
    // v0.11.0 screen groups: `layer` is always the port's OWNER, even when the
    // port runs onto a group peer, and every figure below is read from it. That
    // is not laziness about which member to ask - the port is physically on the
    // owner's processor, so the owner's bit depth, frame rate, processor type
    // and low-latency flag are the ones that decide what it can carry. It also
    // matters that they are not blended: GROUP_SHARED_SETTINGS validates
    // processorType, bitDepth and frameRate at group creation, but lowLatency
    // and portMappingMode are only propagated on EDIT, so a group built before
    // that can hold members that disagree. Mixing them would produce a capacity
    // no member actually has.
    //
    // The 5G narrow-port penalty and the (1 - Y/H) derate both stay meaningful
    // across members because they measure the port's own bounding box against
    // the processor canvas, and same-canvas members' panel coords already share
    // that frame - see _crossMemberLoadPanels, which also refuses to hand this
    // function a port whose cabinets straddle two processor rasters.
    getPortCapacityForPanels(layer, portPanels) {
        const app = window.app;
        if (!app || !layer || typeof app.calculatePortCapacity !== 'function') return 0;
        const processorType = layer.processorType || 'novastar-armor';
        const base = app.calculatePortCapacity(
            layer.bitDepth || 8,
            layer.frameRate || 60,
            processorType,
            !!layer.lowLatency
        );
        if (!(base > 0)) return 0;

        const visible = (portPanels || []).filter(p => p && !p.hidden);
        // The app's own function does the arithmetic and owns the scope guard;
        // this only measures the port. A no-op on every processor but 5G.
        const withWidthPenalty = (capacity) => {
            if (visible.length === 0) return capacity;
            if (typeof app.minLoadWidthPortCapacity !== 'function') return capacity;
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            visible.forEach(p => {
                const x1 = Number(p.x) || 0;
                const y1 = Number(p.y) || 0;
                const x2 = x1 + (Number(p.width) || 0);
                const y2 = y1 + (Number(p.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return app.minLoadWidthPortCapacity(
                capacity, processorType, maxX - minX, maxY - minY);
        };

        const geometry = typeof app.getLowLatencyGeometry === 'function'
            ? app.getLowLatencyGeometry(layer)
            : null;
        if (!geometry || !geometry.yDerate) return withWidthPenalty(base);

        const canvasHeight = typeof app.getLayerCanvasHeight === 'function'
            ? app.getLayerCanvasHeight(layer)
            : 0;
        if (!(canvasHeight > 0) || typeof app.lowLatencyPortCapacity !== 'function') {
            // No honest H: derate nothing rather than guess, which is what the
            // port map itself does. The recorded derate, when present, carries
            // the same underated figure.
            const derate = layer._lowLatencyDerate;
            return withWidthPenalty(
                (derate && derate.portCapacity > 0) ? derate.portCapacity : base);
        }

        if (visible.length === 0) return base;
        const minY = Math.min(...visible.map(p => Number(p.y) || 0));
        return withWidthPenalty(app.lowLatencyPortCapacity(base, minY, canvasHeight));
    }

    // v0.11.0: how full one port is, as a percentage of ITS capacity. Returns
    // null when there is no capacity figure to measure against (unknown
    // processor, image layer), so callers draw nothing rather than "NaN%".
    //
    // 100% IS A GOOD PORT. A port filled exactly to capacity is legal and
    // reads 100 in the ordinary colour; only one that exceeds capacity is a
    // fault. This used to treat load == capacity as over, which drew a red
    // badge on a port that fits.
    //
    // The digits and the colour still always agree, which is the property
    // worth keeping: a port that fits can never print more than 100, and one
    // that does not can never print less than 101. Without those clamps a
    // 100.4% port would round to a passing-looking "100" while glowing red,
    // and a 99.6% port would print 100 with no way to tell it apart from a
    // port that is genuinely full.
    getPortLoadStats(layer, portPanels) {
        const capacity = this.getPortCapacityForPanels(layer, portPanels);
        if (!(capacity > 0)) return null;
        const load = this.getPortPixelLoad(layer, portPanels);
        const percent = (load / capacity) * 100;
        const over = load > capacity;
        const shown = over
            ? Math.max(101, Math.round(percent))
            : Math.min(100, Math.round(percent));
        return {
            load,
            capacity,
            percent,
            shown,
            // Binary: a port either fits or it does not. There used to be an
            // amber 90%+ "warn" band, which made sense while 100% was a fault
            // and you wanted warning before it. Now that a port filled exactly
            // to capacity is legal, amber marked good ports as suspect - and a
            // drawing where every healthy port is plain means any colour on it
            // is a real problem.
            state: over ? 'over' : 'ok'
        };
    }

    // v0.11.0: the load badge that sits under a port's primary marker. Healthy
    // reads in the ordinary label colour - the owner reported coloured healthy
    // readouts being taken for faults - and only the warning (#ff6600) and
    // over-capacity (#ff0000) states get a colour, the same two the Port
    // Capacity panel uses. Drawn on the house dark plate so it stays legible
    // over any cabinet colour, and sized from the layer's own data-flow label
    // size so it tracks the slider like the P/R markers do.
    drawPortLoadBadge(layer, portPanels, centerX, centerY, markerRadius, labelSize, bounds) {
        const stats = this.getPortLoadStats(layer, portPanels);
        if (!stats) return;

        const fontSize = Math.max(8, Math.round(labelSize * 0.55));
        const text = `${stats.shown}%`;
        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        const padX = Math.max(3, Math.round(fontSize * 0.35));
        const padY = Math.max(2, Math.round(fontSize * 0.2));
        const plateWidth = this.ctx.measureText(text).width + padX * 2;
        const plateHeight = fontSize + padY * 2;

        // Under the marker by default; above it when the marker sits so low in
        // the screen that the badge would hang off the bottom edge.
        const gap = Math.max(2, Math.round(fontSize * 0.25));
        let cy = centerY + markerRadius + gap + plateHeight / 2;
        if (bounds && cy + plateHeight / 2 > bounds.bottom) {
            cy = centerY - markerRadius - gap - plateHeight / 2;
        }
        let cx = centerX;
        if (bounds) {
            if (cx - plateWidth / 2 < bounds.left) cx = bounds.left + plateWidth / 2;
            if (cx + plateWidth / 2 > bounds.right) cx = bounds.right - plateWidth / 2;
        }
        cx = this.snap(cx);
        cy = this.snap(cy);

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        const plate = this.snapRect(cx - plateWidth / 2, cy - plateHeight / 2, plateWidth, plateHeight);
        this.ctx.fillRect(plate.x, plate.y, plate.width, plate.height);

        if (stats.state === 'over') {
            this.ctx.fillStyle = '#ff0000';
        } else {
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
        }
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this._fillText(text, cx, cy);
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
        // v0.11.0: per-port load percentage, off by default so no existing
        // export changes. Drawn beside the port marker by drawPortLoadBadge.
        const showPortLoad = !!layer.showDataFlowPortLoad;
        const isCustomFlow = pattern === 'custom';
        if (isCustomFlow) {
            // Clear any capacity error when in custom mode
            layer._capacityError = null;
        }
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

        // v0.8.7.4: layer bounds in panel-local coords, used to shift
        // port labels inward when they'd overflow the screen edge.
        // v0.11.0: in the cross-member overlay pass the "screen" a label must
        // stay inside is the whole wall, not the member that owns the port, and
        // the frame is the overlay's rather than this layer's.
        const layerBoundsForPort = this._crossMemberPass
            ? this._crossMemberBounds(layer)
            : this.getLayerBounds(layer);
        const layerLeft = layerBoundsForPort.x;
        const layerTop = layerBoundsForPort.y;
        const layerRight = layerBoundsForPort.x + layerBoundsForPort.width;
        const layerBottom = layerBoundsForPort.y + layerBoundsForPort.height;

        // `loadPanels` splits the cabinets a port is DRAWN from off the ones it
        // is SCORED on. They are the same objects for every ordinary port and
        // the argument is simply omitted; a crossing port is drawn from
        // overlay-frame shims but scored on the real cabinets, in processor
        // coords, because load and capacity are processor facts. null means the
        // port cannot be scored honestly at all (see _crossMemberLoadPanels).
        const drawPort = (portPanels, portNum, loadPanels) => {
            if (portPanels.length === 0) return;
            const scoredPanels = (loadPanels === undefined) ? portPanels : loadPanels;

            // dock drag: the run under the cursor lights up before its lines
            this._dockRunUnderlay(portPanels, layer, portNum);

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
            const lastPanel = portPanels[portPanels.length - 1];
            const primaryLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'primary') : `P${portNum}`;
            const returnLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'return') : `R${portNum}`;

            // v0.8.7.4: render at user's labelSize directly. Circle grows
            // to fit text width so the label is never clipped. If the
            // label would overflow the screen edge, shift the CENTER
            // inward so it stays fully inside the screen.
            const sizeLabel = (label) => {
                this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
                const textWidth = this.ctx.measureText(label).width;
                const padding = Math.max(4, labelSize * 0.2);
                const radius = Math.max(labelSize * 1.2, textWidth / 2 + padding);
                return { size: labelSize, radius };
            };
            const primaryFit = sizeLabel(primaryLabel);
            const returnFit = sizeLabel(returnLabel);

            const shiftIntoBounds = (px, py, radius) => {
                if (px - radius < layerLeft) px = layerLeft + radius;
                if (px + radius > layerRight) px = layerRight - radius;
                if (py - radius < layerTop) py = layerTop + radius;
                if (py + radius > layerBottom) py = layerBottom - radius;
                return { px: this.snap(px), py: this.snap(py) };
            };

            const primaryPos = shiftIntoBounds(
                firstPanel.x + firstPanel.width / 2,
                firstPanel.y + firstPanel.height / 2,
                primaryFit.radius
            );
            const returnPos = shiftIntoBounds(
                lastPanel.x + lastPanel.width / 2,
                lastPanel.y + lastPanel.height / 2,
                returnFit.radius
            );
            const px = primaryPos.px, py = primaryPos.py;
            const rx = returnPos.px, ry = returnPos.py;

            // If the port has only one panel, draw backup first so primary is on top.
            if (portPanels.length === 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, returnFit.radius, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${returnFit.size}px ${projectFontFamily()}`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this._fillText(returnLabel, rx, ry);
            }

            this.ctx.fillStyle = primaryColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, primaryFit.radius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.fillStyle = primaryTextColor;
            this.ctx.font = `bold ${primaryFit.size}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillText(primaryLabel, px, py);

            if (portPanels.length > 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, returnFit.radius, 0, Math.PI * 2);
                this.ctx.fill();

                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${returnFit.size}px ${projectFontFamily()}`;
                this._fillText(returnLabel, rx, ry);
            }

            // v0.11.0: how close this port is to its limit, under the primary
            // marker so it reads with the port it belongs to and never covers
            // the port number itself. Runs for the hand-drawn custom paths too,
            // which is the case the percentage was asked for.
            if (showPortLoad && scoredPanels) {
                this.drawPortLoadBadge(layer, scoredPanels, px, py, primaryFit.radius, labelSize, {
                    left: layerLeft, right: layerRight, top: layerTop, bottom: layerBottom
                });
            }
        };

        // Custom flow mode: use user-defined paths
        if (isCustomFlow && layer.customPortPaths) {
            const portNums = Object.keys(layer.customPortPaths)
                .map(n => parseInt(n, 10))
                .sort((a, b) => a - b);

            portNums.forEach(portNum => {
                const path = layer.customPortPaths[portNum] || [];
                // v0.11.0: a path that stays on this layer is resolved and drawn
                // exactly as it always was; a path that reaches into a peer is
                // skipped here and drawn by the post-loop overlay pass, which
                // re-enters this function with _crossMemberPass raised and
                // takes the other side of both branches below.
                if (this._deferCrossMemberPath(layer, path)) return;
                if (this._crossMemberPass) {
                    drawPort(this._crossMemberDrawPanels(layer, path), portNum,
                        this._crossMemberLoadPanels(layer, path));
                    return;
                }
                const portPanels = path.map(p => {
                    const panel = layer.panels.find(panel => panel.row === p.row && panel.col === p.col);
                    return panel && !panel.hidden ? panel : null;
                }).filter(Boolean);
                drawPort(portPanels, portNum);
            });

            this.ctx.restore();
            return;
        }

        // v0.12: automatic assignment CAN leave its layer now - a screen group
        // whose members are the same panel routes as one bigger screen (see
        // getAutoRoutePlan). A port that stays home is drawn here exactly as it
        // always was; one that reaches a peer is deferred to the same overlay
        // pass the hand-drawn crossing paths use, because an arrow drawn inside
        // this layer's transform lands in the wrong place on a member carrying a
        // different rotation or Show Look offset, and a member drawn later would
        // paint over it. A layer the plan makes a PEER gets an empty assignment
        // list back and draws nothing at all.
        const assignments = window.app ? window.app.calculatePortAssignments(layer) : [];
        if (layer._capacityError) {
            this.ctx.restore();
            return;
        }

        const ports = new Map();
        assignments.forEach(item => {
            if (!item || !item.panel || item.panel.hidden) return;
            if (!ports.has(item.port)) ports.set(item.port, []);
            ports.get(item.port).push(item);
        });

        [...ports.keys()].sort((a, b) => a - b).forEach(portNum => {
            const items = ports.get(portNum) || [];
            const crosses = items.some(i =>
                i.layerId !== undefined && i.layerId !== null && i.layerId !== layer.id);
            if (this._deferCrossMember(layer, crosses)) return;
            if (crosses) {
                const hits = this._autoCrossMemberHits(layer, items);
                // Drawn through each cabinet's own member's frame; SCORED on the
                // raw panels, which are already canvas-relative and share one
                // processor raster across the group (_crossMemberLoadPanels
                // carries the same distinction for the hand-drawn side).
                drawPort(hits.map(h => this._crossMemberPanelShim(h.layer, h.panel)),
                    portNum, hits.map(h => h.panel));
                return;
            }
            drawPort(items.map(i => i.panel), portNum);
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

    // _powerCircuitOwners rows as LAYER IDS - one row per circuit, null for a
    // circuit that never leaves `layer`, and null overall when nothing crosses.
    //
    // IDS, NOT LAYER OBJECTS. These rows are cached on the layer, and the
    // layer lives inside app.project - a row holding the layer itself (which
    // every stay-home cabinet of a grouped plan does) makes the project
    // CIRCULAR, and the first JSON.stringify of it throws instead of saving.
    // That is not a corner case: saveState deep-copies the project on every
    // edit, updateLayers PUTs each layer, and the group commit PUTs the whole
    // project - so one power render of a grouped wall silently broke undo and
    // persistence everywhere. The automatic DATA crossing already ships plain
    // layerIds on its items (_autoCrossMemberHits) for exactly this reason.
    //
    // Accepts rows of layers or of ids, so both the custom builder (which can
    // hand ids straight through) and calculatePowerAssignments' object rows
    // funnel through one conversion.
    _powerOwnerIdRows(layer, ownerRows) {
        if (!Array.isArray(ownerRows)) return null;
        let crossesAnywhere = false;
        const rows = ownerRows.map(row => {
            if (!Array.isArray(row)) return null;
            const ids = row.map(o => (o == null) ? null
                : (o.id !== undefined ? o.id : o));
            // An all-home row reads as "does not cross", the same shape the
            // hand-drawn side has always used, so the crossing tests downstream
            // stay a plain truthiness check.
            if (ids.every(id => id == null || id === layer.id)) return null;
            crossesAnywhere = true;
            return ids;
        });
        return crossesAnywhere ? rows : null;
    }

    preparePowerLayerRenderData(layer) {
        if (!window.app) return;
        const isCustom = (layer.powerFlowPattern || 'tl-h') === 'custom';
        let error = null;
        let circuits = [];
        let circuitNumKeys = null;

        // v0.11.0: which LAYER each cabinet of each circuit came from, parallel
        // to `circuits`. Every entry is this layer for an automatic map and for
        // any custom circuit that stays home; only a circuit reaching into a
        // group peer differs, and only that case needs the scoped keys below.
        let circuitOwners = null;

        // Per-circuit branch panel counts (splitter circuits only) - null
        // when nothing on this screen shares a circuit.
        let circuitRuns = null;

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            const entries = circuitNums.map(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                if (!this._pathCrossesMembers(layer, path)) {
                    return { num: circuitNum, owners: null,   // all this layer's own cabinets
                        panels: path
                            .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                            .filter(p => p && !p.hidden) };
                }
                // Ids, not the layers themselves - see _powerOwnerIdRows.
                const hits = this._resolvePathPanels(layer, path);
                return { num: circuitNum, owners: hits.map(h => h.layer.id),
                    panels: hits.map(h => h.panel) };
            });
            // Manual splitter merges collapse drawn circuits into ONE shared
            // circuit keyed (and labelled) by the first member's number, so
            // every tile of the group tints and reads as the one circuit.
            const groups = (window.app && typeof window.app.appliedSplitterGroups === 'function')
                ? window.app.appliedSplitterGroups(layer, circuitNums).merge : [];
            let merged = entries;
            if (groups.length) {
                const inG = new Map();
                groups.forEach(g => g.forEach(n => inG.set(n, g)));
                const byNum = new Map(entries.map(e => [e.num, e]));
                const done = new Set();
                merged = [];
                circuitRuns = [];
                for (const e of entries) {
                    if (done.has(e.num)) continue;
                    const g = inG.get(e.num);
                    if (!g) {
                        merged.push(e);
                        circuitRuns.push([e.panels.length]);
                        continue;
                    }
                    const ms = g.filter(n => byNum.has(n)).map(n => byNum.get(n));
                    ms.forEach(m => done.add(m.num));
                    merged.push({
                        num: ms[0].num,
                        owners: ms.some(m => m.owners)
                            ? ms.flatMap(m => m.owners || m.panels.map(() => layer.id))
                            : null,
                        panels: ms.flatMap(m => m.panels),
                    });
                    circuitRuns.push(ms.map(m => m.panels.length));
                }
            }
            circuitNumKeys = merged.map(e => e.num);
            circuitOwners = merged.map(e => e.owners);
            circuits = merged.map(e => e.panels);
        } else {
            const assignments = window.app.calculatePowerAssignments(layer);
            error = assignments.error;
            circuits = assignments.circuits || [];
            circuitRuns = assignments.runs || null;
            // v0.12: an automatic circuit that crosses into a group peer names
            // the screen each cabinet is on. Null for every non-crossing plan,
            // which keeps the unscoped `${row},${col}` map below - and therefore
            // the colour-coded tinting of every ungrouped screen - exactly as it
            // was. Without it a crossing circuit tints the OWNER's R3C4 instead
            // of the peer's, because that key cannot tell the two apart.
            circuitOwners = this._powerOwnerIdRows(layer, assignments.layers);
        }

        layer._powerError = error;
        layer._powerCircuits = circuits;
        layer._powerCircuitRuns = circuitRuns;
        layer._powerCircuitNumKeys = circuitNumKeys;
        layer._powerCircuitOwners = circuitOwners;

        const panelCircuitMap = new Map();
        const panelIndexMap = new Map();
        // v0.11.0: the same two maps keyed by `${layerId}:${row},${col}` so a
        // circuit that reaches into a group peer can still tint the cabinets it
        // claimed over there. It has to be a SECOND map rather than a change of
        // key: the unscoped one is read by renderPower for this layer's own
        // cabinets and cannot tell member A's R0C0 from member B's, so filing a
        // peer's cabinet in it would paint the owner's own R0C0 instead.
        const panelCircuitScopedMap = new Map();
        const panelIndexScopedMap = new Map();
        if (!error) {
            circuits.forEach((circuitPanels, idx) => {
                const circuitNum = circuitNumKeys ? circuitNumKeys[idx] : idx + 1;
                const owners = circuitOwners ? circuitOwners[idx] : null;
                (circuitPanels || []).forEach((panel, panelIdx) => {
                    const ownerId = (owners && owners[panelIdx] != null)
                        ? owners[panelIdx] : layer.id;
                    if (ownerId === layer.id) {
                        const key = this.getPowerPanelKey(panel);
                        panelCircuitMap.set(key, circuitNum);
                        panelIndexMap.set(key, panelIdx + 1);
                    }
                    if (window.app && typeof window.app.getScopedPanelKey === 'function') {
                        const scopedKey = window.app.getScopedPanelKey(ownerId, panel);
                        panelCircuitScopedMap.set(scopedKey, circuitNum);
                        panelIndexScopedMap.set(scopedKey, panelIdx + 1);
                    }
                });
            });
        }
        layer._powerPanelCircuitMap = panelCircuitMap;
        layer._powerPanelIndexMap = panelIndexMap;
        layer._powerPanelCircuitScopedMap = panelCircuitScopedMap;
        layer._powerPanelIndexScopedMap = panelIndexScopedMap;
        // Which frame these maps belong to. Kept off the layer object (a
        // WeakMap on the renderer) so it is not one more transient key the
        // preset, file-load and history code has to remember to strip.
        if (!this._powerPrepFrame) this._powerPrepFrame = new WeakMap();
        this._powerPrepFrame.set(layer, this._renderSeq || 0);
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

        // v0.8.7.4: layer bounds in panel-local coords, used to shift
        // labels inward when they'd overflow the screen edge.
        // v0.11.0: the cross-member overlay pass keeps its labels inside the
        // whole wall instead, in the overlay's frame - see renderDataFlowArrows.
        const layerBounds = this._crossMemberPass
            ? this._crossMemberBounds(layer)
            : this.getLayerBounds(layer);
        const layerLeft = layerBounds.x;
        const layerTop = layerBounds.y;
        const layerRight = layerBounds.x + layerBounds.width;
        const layerBottom = layerBounds.y + layerBounds.height;

        // v0.8.7.4: render at the user's labelSize directly (no
        // fit-to-panel cap, that was overriding the size slider).
        // Circle grows to fit text width so labels never get clipped.
        // If the label would overflow the screen edge, shift the
        // CENTER inward so the label stays fully inside the screen
        // bounds. Long labels overflow into neighboring panels but
        // never beyond the screen.
        // v0.12.0: placement split from drawing so the splitter fan-out can
        // place ONE bubble centered over its run heads (see
        // drawCircuitBranches); the single-run path is unchanged.
        const labelRadius = (label) => {
            this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
            const textWidth = this.ctx.measureText(label).width;
            const padding = Math.max(6, labelSize * 0.25);
            return Math.max(labelSize * 0.7, lineWidth * 1.4, textWidth / 2 + padding);
        };
        const clampLabelCenter = (px, py, circleRadius) => {
            // Shift to keep circle fully within screen bounds.
            if (px - circleRadius < layerLeft) px = layerLeft + circleRadius;
            if (px + circleRadius > layerRight) px = layerRight - circleRadius;
            if (py - circleRadius < layerTop) py = layerTop + circleRadius;
            if (py + circleRadius > layerBottom) py = layerBottom - circleRadius;
            return { px: this.snap(px), py: this.snap(py) };
        };
        const drawLabelBubble = (label, px, py, circleRadius) => {
            this.ctx.fillStyle = powerLabelBgColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, circleRadius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.fillStyle = powerLabelTextColor;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this._fillText(label, px, py);
        };
        const drawCircuitLabel = (panelStart, panelNext, circuitNum) => {
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const circleRadius = labelRadius(label);
            const { px, py } = clampLabelCenter(
                panelStart.x + panelStart.width / 2,
                panelStart.y + panelStart.height / 2, circleRadius);
            drawLabelBubble(label, px, py, circleRadius);
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
            // v0.11.0: `circuits` can now hold a peer's cabinets, and the label
            // is parked on the circuit's FIRST cabinet - which may be one of
            // them. Its raw x/y mean nothing inside this layer's transform, so
            // a crossing circuit's label is deferred to the overlay pass with
            // the lines, and there it is rebuilt from overlay-frame shims.
            const colorViewOwners = layer._powerCircuitOwners;
            layer._powerCircuits.forEach((circuitPanels, idx) => {
                if (!circuitPanels || circuitPanels.length === 0) return;
                const circuitNum = colorViewKeys ? colorViewKeys[idx] : idx + 1;
                const path = (isCustom && layer.powerCustomPaths)
                    ? (layer.powerCustomPaths[circuitNum] || []) : [];
                const crosses = !!(colorViewOwners && colorViewOwners[idx]);
                if (this._crossMemberPass) {
                    if (!crosses) return;
                    const shims = this._crossMemberDrawPanels(layer, path);
                    if (shims.length === 0) return;
                    drawCircuitLabel(shims[0], shims[1], circuitNum);
                    return;
                }
                if (crosses) {
                    this._deferCrossMemberPath(layer, path);
                    return;
                }
                // dock drag: colour-coded view draws no daisy, so the
                // underlay is the whole of the run highlight here
                this._dockRunUnderlay(circuitPanels, layer, circuitNum);
                drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
            });
            this.ctx.restore();
            return;
        }

        // The daisy polyline + direction arrows for ONE run of panels -
        // shared by the whole-circuit path and the per-branch splitter path.
        const drawDaisyLines = (circuitPanels, currentLineColor) => {
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
        };

        const drawCircuit = (circuitPanels, circuitNum) => {
            if (circuitPanels.length === 0) return;
            // dock drag: the circuit under the cursor lights up first
            this._dockRunUnderlay(circuitPanels, layer, circuitNum);
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            drawDaisyLines(circuitPanels, currentLineColor);
            drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
        };

        // A splitter circuit: each branch is its own short daisy, and the
        // ONE circuit label sits at the FAN-OUT - centered across the span
        // of the run-head panels (between the two heads of a 2fer, over the
        // middle of a 3fer) - with the dashed stubs radiating from the
        // bubble to every run head. v0.12.0: it used to sit on run 1's first
        // panel with the stubs crossing to the other heads, which read as
        // clutter on a real wall; a single-branch circuit keeps the plain
        // first-panel label.
        const drawCircuitBranches = (branches, circuitNum) => {
            const live = (branches || []).filter(b => b && b.length > 0);
            if (!live.length) return;
            // dock drag: every branch of the circuit lights together
            live.forEach(b => this._dockRunUnderlay(b, layer, circuitNum));
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            live.forEach(b => drawDaisyLines(b, currentLineColor));
            if (live.length === 1) {
                drawCircuitLabel(live[0][0], live[0][1], circuitNum);
                return;
            }
            const heads = live.map(b => b[0]);
            const hx = heads.map(h => h.x + h.width / 2);
            const hy = heads.map(h => h.y + h.height / 2);
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const circleRadius = labelRadius(label);
            const { px, py } = clampLabelCenter(
                (Math.min(...hx) + Math.max(...hx)) / 2,
                (Math.min(...hy) + Math.max(...hy)) / 2, circleRadius);
            this.ctx.save();
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = Math.max(1, lineWidth * 0.6);
            this.ctx.setLineDash([lineWidth * 1.5, lineWidth]);
            for (const h of heads) {
                this.ctx.beginPath();
                this.ctx.moveTo(px, py);
                this.ctx.lineTo(this.snap(h.x + h.width / 2), this.snap(h.y + h.height / 2));
                this.ctx.stroke();
            }
            this.ctx.restore();
            drawLabelBubble(label, px, py, circleRadius);
        };

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            // Manual splitter merges: the group's member paths draw as the
            // BRANCHES of one shared circuit - one label (the first member's
            // number), dashed stubs to the other runs. A group touching a
            // cross-member path keeps the per-path drawing (the overlay pass
            // machinery owns those), so nothing is wired twice.
            const groups = (window.app && typeof window.app.appliedSplitterGroups === 'function')
                ? window.app.appliedSplitterGroups(layer, circuitNums).merge : [];
            const inG = new Map();
            groups.forEach(g => g.forEach(n => inG.set(n, g)));
            const homePanelsOf = (circuitNum) => (layer.powerCustomPaths[circuitNum] || [])
                .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                .filter(p => p && !p.hidden);
            const done = new Set();
            circuitNums.forEach(circuitNum => {
                if (done.has(circuitNum)) return;
                const g = inG.get(circuitNum);
                if (g && !this._crossMemberPass) {
                    const members = g.filter(n => circuitNums.includes(n));
                    const crosses = members.some(n =>
                        this._pathCrossesMembers(layer, layer.powerCustomPaths[n] || []));
                    if (!crosses) {
                        members.forEach(n => done.add(n));
                        drawCircuitBranches(members.map(homePanelsOf), members[0]);
                        return;
                    }
                }
                const path = layer.powerCustomPaths[circuitNum] || [];
                // v0.11.0: same split as the data-flow custom branch, and it has
                // to stay in step with preparePowerLayerRenderData above - the
                // two read the same paths and a divergence would show up as a
                // circuit that is tinted but not wired, or wired twice.
                if (this._deferCrossMemberPath(layer, path)) return;
                if (this._crossMemberPass) {
                    drawCircuit(this._crossMemberDrawPanels(layer, path), circuitNum);
                    return;
                }
                drawCircuit(homePanelsOf(circuitNum), circuitNum);
            });
            this.ctx.restore();
            return;
        }

        // v0.12: an automatic circuit CAN leave its layer - same change as the
        // one in renderDataFlowArrows above, and the same reason for the overlay
        // pass. A circuit that stays home draws here exactly as it did.
        if (!Array.isArray(layer._powerCircuits) && window.app) {
            const assignments = window.app.calculatePowerAssignments(layer);
            layer._powerError = assignments.error;
            layer._powerCircuits = assignments.circuits || [];
            layer._powerCircuitRuns = assignments.runs || null;
            layer._powerCircuitOwners = this._powerOwnerIdRows(layer, assignments.layers);
        }
        if (layer._powerError) {
            this.ctx.restore();
            return;
        }

        // The cached owner rows hold ids (_powerOwnerIdRows); resolve them
        // through the same scope authority the ids were minted from.
        const ownerById = (window.app && typeof window.app.getPathScopeLayers === 'function')
            ? new Map(window.app.getPathScopeLayers(layer).map(l => [l.id, l]))
            : null;
        layer._powerCircuits.forEach((circuitPanels, idx) => {
            if (!circuitPanels || circuitPanels.length === 0) return;
            const owners = layer._powerCircuitOwners && layer._powerCircuitOwners[idx];
            const crosses = Array.isArray(owners)
                && owners.some(id => id != null && id !== layer.id);
            if (this._deferCrossMember(layer, crosses)) return;
            // A crossing circuit is drawn through each cabinet's own member's
            // frame; a cabinet on a member this view does not draw is left off
            // the line rather than run onto blank paper.
            const ownerOf = (i) => (owners && owners[i] != null && ownerById
                && ownerById.get(owners[i])) || layer;
            const drawPanels = crosses
                ? circuitPanels
                    .map((p, i) => ((ownerOf(i).visible !== false)
                        ? this._crossMemberPanelShim(ownerOf(i), p) : null))
                    .filter(Boolean)
                : circuitPanels;
            // Splitter circuit: break the daisy at run boundaries and fan
            // dashed stubs out from the feed - one label either way. The run
            // counts index the same list either way, so a crossing splitter
            // circuit keeps its branches instead of collapsing into one daisy.
            const counts = layer._powerCircuitRuns && layer._powerCircuitRuns[idx];
            if (counts && counts.length > 1) {
                let off = 0;
                drawCircuitBranches(
                    counts.map(n => drawPanels.slice(off, off += n)), idx + 1);
                return;
            }
            drawCircuit(drawPanels, idx + 1);
        });

        this.ctx.restore();
    }

    // Soca/multi brackets above the wall on the power map: one bracket per
    // multi spanning the columns its 6 legs feed, labeled with the multi
    // name and home-run length (Binder convention). Brackets stack upward
    // when their spans overlap (row-major circuits usually span full width).
    renderSocaBrackets(layer) {
        if (!window.app || typeof window.app.getSocaPlan !== 'function') return;
        if ((layer.type || 'screen') !== 'screen') return;
        const plan = window.app.getSocaPlan(layer);
        if (!plan.length) return;
        const bounds = this.getLayerBounds(layer);
        const top = bounds.y;
        const labelSize = Math.max(11, (layer.powerLabelSize || 14) * 0.9);
        const legFont = Math.max(8, labelSize * 0.62);
        const rowH = labelSize + 14;
        // clear space under the bracket line for the leg ticks + L labels
        const baseGap = 12 + legFont * 1.9;
        // assign stacking rows: first bracket whose x-span is free on a row
        const rows = [];   // per row: list of [x1, x2]
        const placed = plan.map(s => {
            if (!Number.isFinite(s.x1) || !Number.isFinite(s.x2)) return null;
            let r = 0;
            for (; ; r++) {
                const row = rows[r] || (rows[r] = []);
                if (row.every(([a, b]) => s.x2 + 12 < a || s.x1 - 12 > b)) { row.push([s.x1, s.x2]); break; }
            }
            return { s, r };
        }).filter(Boolean);

        this.ctx.save();
        this.ctx.lineWidth = Math.max(1.5, labelSize * 0.12);
        this.ctx.strokeStyle = layer.powerLabelBgColor || '#D95000';
        this.ctx.fillStyle = layer.powerLabelBgColor || '#D95000';
        this.ctx.font = `bold ${labelSize}px ${projectFontFamily()}`;
        for (const { s, r } of placed) {
            const y = top - baseGap - r * rowH;
            const tick = labelSize * 0.45;
            this.ctx.beginPath();
            this.ctx.moveTo(s.x1, y + tick);
            this.ctx.lineTo(s.x1, y);
            this.ctx.lineTo(s.x2, y);
            this.ctx.lineTo(s.x2, y + tick);
            this.ctx.stroke();
            // Leg ticks: drop a short mark from the bracket to the columns
            // each leg feeds, labeled L1..L6 (Binder power-diagram detail).
            // Only meaningful when the legs sit on DISTINCT column groups -
            // row-based circuits all span the same columns, so their ticks
            // would pile up on one x; skip them rather than draw a smear.
            const legs = (s.legs || [])
                .filter(l => Number.isFinite(l.x1) && Number.isFinite(l.x2))
                .map(l => ({ ...l, cx: (l.x1 + l.x2) / 2 }))
                .sort((a, b) => a.cx - b.cx);
            const minGap = legFont * 2.2;
            const distinct = legs.length > 1 &&
                legs.every((l, i) => i === 0 || (l.cx - legs[i - 1].cx) >= minGap);
            if (distinct) {
                this.ctx.save();
                this.ctx.lineWidth = Math.max(1, labelSize * 0.07);
                this.ctx.font = `600 ${legFont}px ${projectFontFamily()}`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'top';
                for (const l of legs) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(l.cx, y);
                    this.ctx.lineTo(l.cx, y + tick * 1.5);
                    this.ctx.stroke();
                    this._fillText('L' + l.leg, l.cx, y + tick * 1.6);
                }
                this.ctx.restore();
            }
            // Home-run lengths are paperwork: they print on exported maps
            // (like the Binder's power diagram) but stay off the working view.
            const label = s.name
                + (this.exportMode && s.length ? ` · ${s.length}` : '')
                + ` · ${s.amps.toFixed(1)}A`;
            const cx = (s.x1 + s.x2) / 2;
            const tw = this.ctx.measureText(label).width;
            // knock out a gap in the bracket line behind the label
            this.ctx.save();
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.globalCompositeOperation = 'source-over';
            const padX = labelSize * 0.4;
            this.ctx.fillStyle = layer.powerLabelBgColor || '#D95000';
            this.ctx.beginPath();
            const pillH = labelSize + 6;
            if (this.ctx.roundRect) this.ctx.roundRect(cx - tw / 2 - padX, y - pillH / 2, tw + padX * 2, pillH, pillH / 2);
            else this.ctx.rect(cx - tw / 2 - padX, y - pillH / 2, tw + padX * 2, pillH);
            this.ctx.fill();
            this.ctx.fillStyle = layer.powerLabelTextColor || '#000000';
            this._fillText(label, cx, y);
            this.ctx.restore();
        }
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
        this.ctx.font = `bold 42px ${projectFontFamily()}`;
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
        this.ctx.font = `bold 42px ${projectFontFamily()}`;
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
        if (layer.powerColorCodedView && !layer._powerError) {
            // v0.11.0: the circuit tinting this cabinet is usually one of this
            // layer's own, but a group peer's circuit can have claimed it - and
            // then the COLOUR is the peer's, because the palette and the circuit
            // number both belong to the layer that owns the circuit. Without
            // this a cross-member circuit tinted only the half of itself that
            // happened to sit on the layer being drawn.
            const hit = this._powerCircuitForPanel(layer, panel);
            if (hit && hit.circuitNum) {
                fillHex = this.getPowerCircuitColor(hit.owner, hit.circuitNum);
            }
        }

        if (fillHex) {
            // Circuit color-coded view: keep the flat circuit color readable
            // (no gradient on top).
            this.ctx.fillStyle = fillHex;
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        } else if (!layer.transparentFill) {
            // Base cabinet fill: checkerboard / palette, same as Pixel Map,
            // with the gradient overlay on top (below borders and circuit
            // lines). These used to hard-code the plain checkerboard, so
            // gradients, palette modes, and Transparent (no fill) were all
            // ignored on the Power view. Circuit color-coding above is data,
            // not decoration, so it still paints on a transparent screen.
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            this._applyGradientOverlay(panel, layer);
        }

        if (layer.show_panel_borders) {
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'power');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
        }
    }
    
    // ── Screen groups (v0.11.0): cabinet IDs that run across the group ────
    //
    // A group is ONE screen built from more than one layer, so its cabinet IDs
    // have to read as one screen too. Per layer they are grid indices, so the
    // second member restarts at A1 / 1 and the wall carries two cabinets
    // labelled A1 - a tech reading the map cannot tell them apart.
    //
    // Both families of ID are re-derived from the cabinet's ACTUAL POSITION on
    // the wall, pooled across every member, so the label is what someone
    // standing in front of the wall counting cabinets would say and the member
    // boundaries are invisible:
    //
    //   column-row / row-column / row-col
    //       the column index is the rank of the cabinet's column among the
    //       group's distinct column positions (rows likewise) - not the
    //       member's own grid index, and not that index plus an offset:
    //       members have different cabinet sizes, so "column 3" is a different
    //       place on the wall in each of them.
    //   sequential (panel.number)
    //       reading order over the whole wall, top-to-bottom then
    //       left-to-right, rather than member after member.
    //
    // The position ranked is the cabinet's SLOT origin (the smallest x in its
    // member's column, the smallest y in its member's row), not its own x/y,
    // because a half-tile is anchored inside its slot (_build_panels) and
    // would otherwise rank as a column of its own.
    //
    // The cost of ranking positions: with mixed cabinet sizes the distinct
    // positions do not line up between members. A 128 px member contributes
    // x = 0, 128, 256... and a 64 px member 0, 64, 128..., so the pooled
    // letters advance at every cabinet edge on the wall and the big member's
    // own letters skip (A, C, E...). That is the honest reading - the letters
    // count places on the wall, which is what the person counting counts.
    //
    // Two cabinets can share a column AND a row rank only when they share a
    // slot origin, i.e. when members physically overlap. Uniqueness is a hard
    // requirement, so the plan CHECKS it rather than trusting the geometry: a
    // grid style that cannot label this group uniquely is dropped for the
    // whole group in favour of the wall's sequential numbers (one consistent
    // map, every cabinet distinct) rather than drawing two A1s or inventing a
    // sub-number.
    //
    // Hidden and blank cabinets keep today's treatment exactly: both consume a
    // number (panel.number counts every grid cell), blank ones are labelled,
    // hidden ones are not - so hidden cabinets are ranked too, and their
    // columns and rows still take their place.
    //
    // v0.11.0: positions are ranked where the cabinets DRAW, so a member
    // carrying a screen rotation is numbered in the order the eye follows it
    // across the wall rather than by where its unrotated grid would have sat.
    // See getPositionLattice.
    _groupNumberingMembers(layer) {
        const g = this._groupForLayer(layer);
        if (!g || !window.app || typeof window.app.getGroupMembers !== 'function') return [];
        const cid = this._effectiveLayerCanvasId(layer);
        // Deliberately NOT filtered on `visible`, unlike _groupDrawnMembers:
        // hiding one member must not renumber another member's cabinets. Same
        // canvas only - a position from another canvas's workspace cannot be
        // ranked against these.
        return window.app.getGroupMembers(g).filter(m => m
            && (m.type || 'screen') === 'screen'
            && Array.isArray(m.panels)
            && this._effectiveLayerCanvasId(m) === cid);
    }

    // THE WALL LATTICE - a set of members' separate grids collapsed into one
    // ordered set of column and row POSITIONS. This is the rank-position
    // mapping step 5 built for continuous cabinet numbering, extracted so it
    // has exactly ONE implementation.
    //
    // Two members of one wall do not share a grid: a 1m cabinet's row 1 and a
    // 0.5m cabinet's row 1 are different physical heights, so anything that has
    // to run ACROSS the wall - the cabinet IDs, and now a pattern applied to a
    // selection that starts on one member and finishes on the next - is
    // meaningless if it is ordered by the panels' own row/col indices. It has
    // to be ordered by WHERE EACH CABINET SITS. Every distinct column x and row
    // y any member occupies is pooled and ranked, and each cabinet then reports
    // the rank of its own slot; a cabinet spanning two lattice rows ranks by
    // its own top-left, exactly as step 5 numbers it.
    //
    // WHO CALLS IT. _groupNumberingPlan below (the cabinet IDs) and
    // app-power.js's cross-member flow patterns, through
    // `window.canvasRenderer.getPositionLattice(...)`. It lives on the renderer
    // because the ranking needs getLayerRenderOffset - two members can carry
    // different Show Look offsets, and Data Flow / Power draw at the SHOW
    // position. The canvas workspace translate is shared by every member of a
    // path scope, so it cancels out of a ranking and is deliberately left out.
    // Two copies of this would eventually disagree, and a serpentine that
    // zig-zags the wall in a different order than the IDs read is worse than no
    // serpentine at all.
    //
    //   members                    the ranked members, in the order given
    //   indexOfLayer(layerOrId)    that member's index, or -1
    //   colOfMember(index, panel)  rank by member index, when the caller
    //   rowOfMember(index, panel)  already knows it
    //   colOf(layerOrId, panel)    the cabinet's lattice column rank
    //   rowOf(layerOrId, panel)    the cabinet's lattice row rank
    //   compare(a, b)              reading order over {layer, panel} pairs
    //
    // colOf/rowOf take the panel's OWN layer, because the same {row, col} means
    // a different place on the wall in each member - that is the entire point.
    // The panel's own index is the fallback for a panel whose layer is not in
    // the list, so a caller handing over something outside the scope degrades
    // to today's behaviour rather than throwing mid-render or returning NaN.
    //
    // A single-member list is meaningful and ranks that one screen's own slots:
    // for a uniform grid the ranks then equal the panels' own indices, which is
    // why an ungrouped screen can go through the same code and come out with
    // the order it has always had.
    //
    // ROTATION. Positions are ranked where each cabinet is DRAWN, through that
    // member's own draw frame (_layerDrawFrame / _drawnPanelRect) - the same
    // mapping the marquee, the arrow handoff and the selection highlight use. A
    // wall with one member turned 90 therefore numbers, and serpentines, in the
    // order somebody walking the wall reads it. Ranking in unrotated space (what
    // this did before v0.11.0) produced an order that existed nowhere on site.
    getPositionLattice(members) {
        const list = (members || []).filter(m => m && Array.isArray(m.panels));

        // Slot origins per member, in the space this view DRAWS in: each
        // cabinet's rect through that member's own draw frame, which carries its
        // rotation and its Show Look offset. The render offset is 0 on Cabinet
        // ID today; it matters in the views that DO shift layers (Data Flow /
        // Power carry Show Look offsets), which is where the flow patterns read
        // this from.
        //
        // v0.11.0: a 90/270 turn trades a member's axes - its rows run along the
        // wall's x - so the cabinets are grouped into drawn columns and rows by
        // _drawnColKey / _drawnRowKey before their positions are pooled. Without
        // it a rotated member ranks where its grid sits rather than where it
        // draws, and a serpentine enters it at a corner that is nowhere on site.
        // The frame is hoisted per member: it is O(panels) to build.
        const key = v => Math.round(v * 100);   // pixel coords; kills float noise
        const slots = list.map(m => {
            const frame = this._layerDrawFrame(m);
            const cols = new Map();
            const rows = new Map();
            (m.panels || []).forEach(p => {
                const r = this._drawnPanelRect(frame, p);
                const ck = this._drawnColKey(frame, p);
                const rk = this._drawnRowKey(frame, p);
                const cx = cols.get(ck);
                if (cx === undefined || r.x < cx) cols.set(ck, r.x);
                const ry = rows.get(rk);
                if (ry === undefined || r.y < ry) rows.set(rk, r.y);
            });
            return { cols, rows, frame };
        });

        // Every distinct column position on the wall, in order, then rows.
        // Pooled across all N members, not just a pair.
        const rankPositions = maps => {
            const seen = new Set();
            const values = [];
            maps.forEach(map => map.forEach(v => {
                if (seen.has(key(v))) return;
                seen.add(key(v));
                values.push(v);
            }));
            values.sort((a, b) => a - b);
            const ranks = new Map();
            values.forEach((v, i) => ranks.set(key(v), i));
            return ranks;
        };
        const colRanks = rankPositions(slots.map(s => s.cols));
        const rowRanks = rankPositions(slots.map(s => s.rows));

        // The panel's own index is the fallback for a panel that is not in the
        // member we were handed - what a caller outside the scope wants, and
        // what keeps a stale one from getting NaN.
        const colOfMember = (mi, panel) => {
            const s = slots[mi];
            const x = (s && panel) ? s.cols.get(this._drawnColKey(s.frame, panel)) : undefined;
            const r = (x === undefined) ? undefined : colRanks.get(key(x));
            return (r === undefined) ? (panel ? panel.col : 0) : r;
        };
        const rowOfMember = (mi, panel) => {
            const s = slots[mi];
            const y = (s && panel) ? s.rows.get(this._drawnRowKey(s.frame, panel)) : undefined;
            const r = (y === undefined) ? undefined : rowRanks.get(key(y));
            return (r === undefined) ? (panel ? panel.row : 0) : r;
        };

        // Layer -> member index, by id so a caller holding a stale object
        // reference (or just an id) still lands on the right member.
        const byId = new Map();
        list.forEach((m, i) => byId.set(m.id, i));
        const indexOfLayer = target => {
            if (target === null || target === undefined) return -1;
            const id = (typeof target === 'object') ? target.id : target;
            const i = byId.get(id);
            return (i === undefined) ? -1 : i;
        };

        const colOf = (panelLayer, panel) => colOfMember(indexOfLayer(panelLayer), panel);
        const rowOf = (panelLayer, panel) => rowOfMember(indexOfLayer(panelLayer), panel);

        return {
            members: list,
            indexOfLayer,
            colOfMember,
            rowOfMember,
            colOf,
            rowOf,
            // Reading order over the whole wall. Row rank then column rank IS
            // ranking by slot position; the member index and then the member's
            // own grid position break any remaining tie, so the order is stable
            // and follows the order the members were given in. This is the
            // comparator the cabinet numbers below are assigned with, because
            // it is literally the same one.
            compare: (a, b) => {
                const ra = rowOf(a.layer, a.panel);
                const rb = rowOf(b.layer, b.panel);
                const ca = colOf(a.layer, a.panel);
                const cb = colOf(b.layer, b.panel);
                return (ra - rb) || (ca - cb)
                    || (indexOfLayer(a.layer) - indexOfLayer(b.layer))
                    || (a.panel.row - b.panel.row) || (a.panel.col - b.panel.col);
            },
        };
    }

    // The lattice for `layer`'s GROUP: the members this canvas ranks together,
    // in the group's own order. Null when `layer` is not in a group of two or
    // more here, which is what keeps every single-screen caller - the cabinet
    // numbering below included - on the path it always took.
    getGroupLattice(layer) {
        const members = this._groupNumberingMembers(layer);
        if (members.length < 2) return null;
        return this.getPositionLattice(members);
    }

    // The numbering `layer` should draw with, or null when it is not in a
    // group of two or more here - and then renderCabinetIDNumbers takes
    // exactly the path it always took.
    _groupNumberingPlan(layer) {
        const lattice = this.getGroupLattice(layer);
        if (!lattice) return null;
        const members = lattice.members;
        const mine = members.findIndex(m => m.id === layer.id);
        if (mine < 0) return null;

        // Sequential = reading order over the whole wall, which is exactly the
        // lattice's own comparator.
        const cells = [];
        members.forEach((m, mi) => (m.panels || []).forEach(p => cells.push({
            mi, panel: p, layer: m,
            col: lattice.colOf(m, p), row: lattice.rowOf(m, p),
        })));
        cells.sort(lattice.compare);
        const numbers = new Map();
        cells.forEach((c, i) => numbers.set(`${c.mi}:${c.panel.row},${c.panel.col}`, i + 1));

        // Can a grid style label this group uniquely? Only the cabinets that
        // actually draw a label are checked - a hidden cabinet draws none, so
        // it cannot collide with anything.
        const gridSeen = new Set();
        let gridUnique = true;
        cells.forEach(c => {
            if (!gridUnique || c.panel.hidden) return;
            const k = `${c.col},${c.row}`;
            if (gridSeen.has(k)) gridUnique = false;
            else gridSeen.add(k);
        });

        return {
            gridUnique,
            // One style for the whole wall, the FIRST member's, the same rule
            // _groupLabelPlan uses for the label config. Screen Info already
            // propagates cabinetIdStyle across a group, so this only bites on
            // members that disagreed before they were grouped - and there it
            // matters, because one member drawing A1 as column-row while
            // another draws A1 as row-column is a duplicate ID again.
            style: members[0].cabinetIdStyle || 'column-row',
            colOf: panel => lattice.colOf(layer, panel),
            rowOf: panel => lattice.rowOf(layer, panel),
            numberOf: panel => numbers.get(`${mine}:${panel.row},${panel.col}`) || panel.number,
        };
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

        // v0.11.0: in a screen group the IDs run across the whole wall - see
        // _groupNumberingPlan. Null for an ungrouped layer, and every line
        // below then reads exactly as it always did.
        const plan = this._groupNumberingPlan(layer);
        // A grid style that cannot label this group uniquely is dropped for
        // the whole group in favour of the wall's sequential numbers -
        // 'sequential' is not a stored style, it is the name of the switch's
        // default arm below.
        const idStyle = plan
            ? (plan.gridUnique ? plan.style : 'sequential')
            : cabinetIdStyle;

        this.ctx.fillStyle = cabinetIdColor;
        this.ctx.font = `bold ${numberSize}px ${projectFontFamily()}`;
        
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
            const col = plan ? plan.colOf(panel) : panel.col;  // 0-indexed
            const row = plan ? plan.rowOf(panel) : panel.row;  // 0-indexed

            switch (idStyle) {
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
                    // Fallback to sequential - the wall's reading order in a
                    // group, the layer's own panel numbers on their own.
                    label = plan ? plan.numberOf(panel) : panel.number;
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
    
    renderLayerLabels(layer, groupLabelPass = false) {
        // v0.11.0: screen groups draw ONE label for the whole group. The host
        // member draws it (see _groupLabelPlan) and every peer bows out right
        // here - peers keep drawing their own cabinets, only the label
        // consolidates. `plan` is null for an ungrouped layer, so everything
        // below is unchanged for a project without groups.
        const plan = this._groupLabelPlan(layer);
        // The NAMES switch (_groupNameMode). In 'screens' and 'both' every
        // member draws its own name again - exactly the ungrouped path - so
        // the group's consolidated label moves to a separate pass, hosted by
        // the same last member as always: with the group's name in 'both',
        // with no name line at all in 'screens'. The combined figures
        // consolidate either way; only the NAME element changes hands.
        const nameMode = plan ? this._groupNameMode() : 'group';
        const memberNamePass = !!plan && nameMode !== 'group' && !groupLabelPass;
        if (memberNamePass && plan.host.id === layer.id) {
            this.renderLayerLabels(layer, true);
        }
        // gplan: the plan the rest of this function acts on. Null during a
        // member's own-name pass, so every line below reads exactly as it
        // does for an ungrouped layer.
        const gplan = memberNamePass ? null : plan;
        if (gplan && gplan.host.id !== layer.id) {
            if (layer._screenNameHitRect) layer._screenNameHitRect = null;
            return;
        }
        // Where the label's settings come from: the layer itself, or the
        // group's first member. This is also the layer that caches the hit
        // rect and stores the screen-name drag offset, so the one label has
        // exactly one owner no matter which member happens to draw it.
        const cfg = gplan ? gplan.cfg : layer;

        // v0.8.7.7: clear any stale screen-name hit rect from a previous
        // render; the if-block below resets it when the label is actually
        // drawn, but layers with showLabelName off (or tab-specific
        // toggles like showLabelNameCabinet) need a clean slate so a
        // mousedown doesn't catch the ghost.
        // The group label pass must NOT touch it: in 'screens'/'both' the
        // rect on cfg belongs to the first member's OWN name, drawn in that
        // member's earlier pass this same frame.
        if (!groupLabelPass) {
            if (layer && layer._screenNameHitRect) layer._screenNameHitRect = null;
            if (cfg._screenNameHitRect) cfg._screenNameHitRect = null;
        }
        // Same hygiene for the group headline's rect ('both'): cleared on
        // every group-label pass and re-set only when the headline is drawn,
        // so switching away from 'both' leaves no ghost to grab.
        if (gplan && cfg._groupNameHitRect) cfg._groupNameHitRect = null;
        if ((layer.type || 'screen') === 'image') {
            return;
        }
        // Note: Clipping for layer occlusion is handled in the render() second pass
        // We only clip to raster bounds here (translate-aware), which
        // intersects with the occlusion clip
        this.ctx.save();
        this._clipToActiveRaster();

        // v0.11.0: a group's label belongs to THE WALL, and _groupUnionBounds
        // measures the wall. The render loop has the ctx turned about the host
        // member's own centre, so cancel that before the label is positioned -
        // otherwise the wall's centre is thrown wherever one member's rotation
        // sends it. The ctx.save above pops it; an ungrouped screen's name still
        // rotates with its screen.
        if (gplan) this._unrotateLayerInPlace(layer);

        // v0.11.0: a group's label is positioned against the union of its
        // members' drawn footprints - the real shape of the wall - not one
        // member's.
        const bounds = gplan ? this._groupUnionBounds(gplan.members, layer) : this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        const bottomY = bounds.y + layerHeight;

        // v0.11.0: and its figures are the COMBINED figures, straight from the
        // step-2 roll-up. No calculation is repeated here.
        // The canvas being drawn is passed through: a group is labelled once
        // per canvas, and its figures must describe the members ON that canvas
        // rather than every member wherever it sits. Without it the label under
        // a two-section wall could carry the weight of a third section drawn
        // somewhere else entirely.
        const groupTotals = (gplan && window.app && typeof window.app.getGroupTotals === 'function')
            ? window.app.getGroupTotals(gplan.group, this._effectiveLayerCanvasId(layer))
            : null;

        // Calculate physical dimensions. For a group the pixel span is the
        // whole wall's but the mm-per-pixel conversion is the FIRST member's
        // pitch - mixed-pitch members have no single answer, and the first
        // member is the one every other label setting comes from.
        const widthMM = (cfg.panel_width_mm || 500) * (layerWidth / (cfg.cabinet_width || 1));
        const heightMM = (cfg.panel_height_mm || 500) * (layerHeight / (cfg.cabinet_height || 1));
        const widthM = widthMM / 1000;
        const heightM = heightMM / 1000;
        const widthFt = widthM * 3.28084;
        const heightFt = heightM * 3.28084;
        
        const ownActivePanels = layer.panels.filter(p => !p.blank && !p.hidden);
        const activePanels = groupTotals ? groupTotals.cabinets : ownActivePanels.length;
        const equivalentPanels = groupTotals ? groupTotals.equivalentPanels : ownActivePanels
            .reduce((sum, p) => {
                if (window.app && typeof window.app.getPanelLoadFactor === 'function') {
                    return sum + window.app.getPanelLoadFactor(layer, p);
                }
                return sum + 1;
            }, 0);
        const panelWeightValue = layer.panel_weight || 20;
        const panelWeightUnit = layer.weight_unit || 'kg';
        const panelWeightKg = panelWeightUnit === 'lb' ? (panelWeightValue / 2.20462) : panelWeightValue;
        // The roll-up already weighs each member against its OWN cabinet, so a
        // group's weight can never be one member's per-cabinet figure applied
        // to everybody's cabinets.
        const totalWeightKg = groupTotals ? groupTotals.weightKg : equivalentPanels * panelWeightKg;
        const totalWeightLb = groupTotals ? groupTotals.weightLb : totalWeightKg * 2.20462;

        // Build labels - Screen Name is separate with white background
        // Per-tab showLabelName: each view mode has its own property, falling back to global → true
        let showLabelName;
        if (this.viewMode === 'cabinet-id') {
            showLabelName = cfg.showLabelNameCabinet !== undefined ? cfg.showLabelNameCabinet
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'data-flow') {
            showLabelName = cfg.showLabelNameDataFlow !== undefined ? cfg.showLabelNameDataFlow
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else if (this.viewMode === 'power') {
            showLabelName = cfg.showLabelNamePower !== undefined ? cfg.showLabelNamePower
                : (cfg.showLabelName !== undefined ? cfg.showLabelName : true);
        } else {
            showLabelName = cfg.showLabelName !== undefined ? cfg.showLabelName : true;
        }
        // v0.11.0: the group's name, not the host member's - the wall has one
        // name on site and now one on the drawing.
        // Under the NAMES switch the group label carries its name line only
        // when the group's name is wanted: always in 'group', in 'both' as
        // the wall's headline, never in 'screens' (the members carry their
        // own, in their own passes).
        let screenName = showLabelName
            ? (groupTotals ? (groupTotals.name || cfg.name) : layer.name)
            : null;
        if (groupLabelPass && nameMode === 'screens') screenName = null;

        // Other center labels (regular style)
        const centerLines = [];

        // Other labels only in pixel-map mode.
        // A member's own-name pass draws the NAME and nothing else - the
        // sizes, weight, port and circuit figures stay consolidated on the
        // group's single label, exactly where they are in 'group' display.
        if (memberNamePass) {
            // no center lines
        } else if (this.viewMode === 'pixel-map') {
            if (cfg.showLabelSizePx) {
                centerLines.push(`W ${layerWidth} X H ${layerHeight}`);
            }
            if (cfg.showLabelSizeM) {
                centerLines.push(`W ${widthM.toFixed(2)}(m) X H ${heightM.toFixed(2)}(m)`);
            }
            if (cfg.showLabelSizeFt) {
                const useFractional = cfg.useFractionalInches || false;
                
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
            if (cfg.showLabelWeight) {
                centerLines.push(`Weight ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
            }
        } else if (this.viewMode === 'data-flow') {
            if (cfg.showDataFlowPortInfo && groupTotals) {
                // A group's ports come straight out of the roll-up, which adds
                // up whatever each member reports. v0.12: on a group whose
                // members are the same panel that is ONE combined walk's figure,
                // carried by the first member with every other member reporting
                // zero - so this label reads the wall's real port count and not
                // the sum of what its sections would have needed apart. On every
                // other group it is still the members' own requirements summed.
                const mains = groupTotals.portsPrimary;
                const backups = groupTotals.portsBackup;
                if (mains > 0) {
                    centerLines.push(`${mains} Mains, ${backups} Backups | ${mains + backups} Ports`);
                }
            } else if (cfg.showDataFlowPortInfo && window.app) {
                // Always recompute from current layer state. Cached `_portsRequired`
                // is only refreshed for the currently-selected layer by
                // `updatePortCapacityDisplay`, so other layers' labels would go
                // stale until clicked. `renderDataFlowArrows` ran just above and
                // populated fresh `_autoPortsRequired` on this layer.
                // Both sides converged on the same lesson: ONE authority for
                // "how many ports does this screen need". Upstream's
                // getLayerPortsRequired is the group-aware one (a member fully
                // served by a peer's crossing path needs zero of its own), so
                // it is the one the canvas asks; the rack-side screenPortCount
                // is being reconciled onto it rather than kept as a rival.
                let portsRequired = typeof window.app.getLayerPortsRequired === 'function'
                    ? (window.app.getLayerPortsRequired(layer) || 0) : 0;
                if (portsRequired > 0) {
                    const mains = portsRequired;
                    const backups = portsRequired;
                    centerLines.push(`${mains} Mains, ${backups} Backups | ${mains + backups} Ports`);
                }
            }
        } else if (this.viewMode === 'power') {
            if (cfg.showPowerCircuitInfo && groupTotals) {
                // Circuits come through the roll-up the same way ports do, and
                // on a crossing group that is one combined walk's figure for the
                // same reason. Amps do NOT:
                // 200 A at 110 V and 200 A at 208 V are not the same load, so
                // when the members disagree on voltage the roll-up hands back
                // null and the label says so instead of printing a blended
                // figure nobody can act on.
                const circuits = groupTotals.circuits;
                // Split-aware and box-size-aware, per member: socaCountFor
                // reads each screen's own split points and breakout box
                // size (three tails on an L21-30, six on a soca), so the
                // group line agrees with the dock. A peer-served member
                // reports zero circuits and therefore zero boxes.
                let multis = 0;
                if (circuits > 0 && window.app
                        && typeof window.app.socaCountFor === 'function'
                        && typeof window.app.screenCircuitCount === 'function'
                        && typeof window.app.getGroupMembers === 'function') {
                    (window.app.getGroupMembers(gplan.group) || []).forEach(m => {
                        if (!m || (m.type || 'screen') !== 'screen') return;
                        multis += window.app.socaCountFor(
                            m, window.app.screenCircuitCount(m));
                    });
                } else if (circuits > 0) {
                    multis = Math.ceil(circuits / 6);
                }
                if (groupTotals.voltageMismatch) {
                    const volts = groupTotals.voltages.filter(v => v > 0).join(' / ');
                    centerLines.push(`${multis} Multi, ${circuits} Circuits | Mixed voltage: ${volts} V`);
                } else {
                    const amps1 = groupTotals.amps1ph || 0;
                    const amps3 = groupTotals.amps3ph || 0;
                    centerLines.push(`${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`);
                }
            } else if (cfg.showPowerCircuitInfo && window.app) {
                // Ungrouped: recompute from current layer state rather than
                // trusting `_powerCircuitsRequired` (only refreshed for the
                // currently-selected layer). `screenCircuitCount` is the shared
                // authority, so the badge, the Power tab, the soca plan and the
                // report all say the same number on a custom-routed screen.
                let circuits = typeof window.app.screenCircuitCount === 'function'
                    ? window.app.screenCircuitCount(layer)
                    : 0;
                if (circuits <= 0 && Array.isArray(layer._powerCircuits)) {
                    circuits = layer._powerCircuits.filter(c => Array.isArray(c) && c.length > 0).length;
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
                // Split-aware: a multi broken at a chosen boundary is two
                // multis, and this line must agree with the soca panel.
                const multis = circuits > 0
                    ? (typeof window.app.socaCountFor === 'function'
                        ? window.app.socaCountFor(layer, circuits)
                        : Math.ceil(circuits / 6))
                    : 0;
                centerLines.push(`${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`);
            }
        }
        
        // Build Info label clauses (separate bar, at bottom) - only in pixel-map
        // mode. v0.10.7: emit discrete clauses instead of one long string so the
        // draw step can pack them into as many lines as the screen width allows,
        // keeping the whole info bar bound inside the layer instead of spilling
        // past both edges on a narrow screen.
        const infoParts = [];
        if (!memberNamePass && this.viewMode === 'pixel-map' && cfg.showLabelInfo) {
            const aspectRatio = layerWidth / layerHeight;
            const aspectRatioStr = `${aspectRatio.toFixed(2)}`;
            // v0.11.0: a group has no single Columns X Rows - that is the whole
            // reason it is more than one layer - so it reports how many screens
            // it is built from instead of quoting one member's grid.
            if (groupTotals) {
                infoParts.push(`${groupTotals.memberCount} Screens`);
            } else {
                infoParts.push(`${layer.columns} Columns X ${layer.rows} Rows`);
            }
            infoParts.push(`${activePanels} Cabinets Total`);
            infoParts.push(`Resolution: ${layerWidth} X ${layerHeight}`);
            infoParts.push(`Aspect Ratio: ${aspectRatioStr}`);
            infoParts.push(`Weight: ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
        }
        
        // Use absolute pixel sizes - no scaling with zoom
        let fontSize = cfg.labelsFontSize || 30;
        const lineHeight = fontSize + 4;
        const padding = 6;

        // Info label uses independent slider value
        const infoFontSize = cfg.infoLabelSize || 14;
        const infoLineHeight = infoFontSize + 4;
        
        // Screen name uses tab-specific size and position settings.
        // Where the name's drag offset lives: the cfg layer, except for the
        // group headline in 'both' - there the first member's fields already
        // position the first member's OWN name, and one stored offset cannot
        // place two labels, so the headline's offsets ride the group object
        // under the same field names.
        const nameCfg = (groupLabelPass && nameMode === 'both') ? gplan.group : cfg;
        let screenNameSize = fontSize; // Default for pixel-map
        let screenNameOffsetX = 0;
        let screenNameOffsetY = 0;

        if (this.viewMode === 'pixel-map') {
            // v0.8.7.7: Pixel Map screen-name size stays tied to the
            // legacy labelsFontSize slider (the default for pixel-map),
            // but the X/Y offset is now read from per-view fields so the
            // user can Shift+Alt+drag the name out of the center stack.
            screenNameOffsetX = nameCfg.screenNameOffsetXPixelMap || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYPixelMap || 0;
        } else if (this.viewMode === 'cabinet-id') {
            screenNameSize = cfg.screenNameSizeCabinet || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXCabinet || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYCabinet || 0;
        } else if (this.viewMode === 'data-flow') {
            screenNameSize = cfg.screenNameSizeDataFlow || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXDataFlow || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYDataFlow || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'power') {
            screenNameSize = cfg.screenNameSizePower || 14;
            screenNameOffsetX = nameCfg.screenNameOffsetXPower || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYPower || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'show-look') {
            // v0.8.7.7.3: Show Look gets its own grabbable screen-name offset
            // so the label can be repositioned (and edge-clamped) here too.
            screenNameOffsetX = nameCfg.screenNameOffsetXShowLook || 0;
            screenNameOffsetY = nameCfg.screenNameOffsetYShowLook || 0;
        }

        const screenNameLineHeight = screenNameSize + 4;
        
        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        
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
        // v0.8.7.7.2: the offset actually *applied* to the screen name after
        // the out-of-bounds clamp below. The center/info label group must use
        // this same value (not the raw stored offset) so it never diverges
        // from the name, otherwise a name that snapped back to center leaves
        // the size/info bar flung off-bounds where it gets clipped away.
        let _appliedNameOffsetX = 0;
        let _appliedNameOffsetY = 0;
        if (screenName) {
            // Set the name font up-front so we can measure the label box and
            // clamp it fully inside the layer before drawing.
            this.ctx.font = `bold ${screenNameSize}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';

            const metrics = this.ctx.measureText(screenName);
            const nameWidth = metrics.width + padding * 2;
            const nameHeight = screenNameLineHeight + padding * 2;

            // Baseline (un-offset) anchor for this view mode. Pixel Map stacks
            // the name above the size/info lines; the other tabs center it.
            const baseX = centerX;
            const baseY = (this.viewMode === 'pixel-map')
                ? (currentY + screenNameHeight / 2)
                : centerY;

            // Desired position = baseline + the user's drag offset. Offsets are
            // stored in *visual* space; on a mirrored (Back-view) canvas the
            // wrapping scale(-1,1) would flip X, so negate offsetX to undo it.
            const _visualOffsetX = this._mirror ? -screenNameOffsetX : screenNameOffsetX;
            let screenNameX = baseX + _visualOffsetX;
            let screenNameY = baseY + screenNameOffsetY;

            // v0.8.7.7.3: clamp the label box to the layer's edges on EVERY tab
            // (Pixel Map, Cabinet ID, Data, Power) instead of snapping back to
            // center when the drag overshoots. Pinning to the edge lets a name
            // sit at the top of a panel (above an overlapping window layer)
            // while keeping the whole label group on-screen. The applied
            // (post-clamp) delta drives the size/info bar so the group never
            // diverges. If the box is larger than the layer, fall back to
            // centering on that axis.
            const _clamp = (v, lo, hi) => (lo > hi ? (lo + hi) / 2 : Math.min(Math.max(v, lo), hi));
            screenNameX = _clamp(screenNameX, bounds.x + nameWidth / 2, bounds.x + layerWidth - nameWidth / 2);
            screenNameY = _clamp(screenNameY, bounds.y + nameHeight / 2, bounds.y + layerHeight - nameHeight / 2);

            _appliedNameOffsetX = screenNameX - baseX;
            _appliedNameOffsetY = screenNameY - baseY;

            // The 'both' display keeps the group's headline AND the member
            // names on the wall at once, and they must never sit on top of
            // each other - the wall's main section centres exactly where the
            // headline does. Resolved the way the label stack already
            // resolves its own collisions: the headline keeps its place and
            // the member name steps BELOW it, with the stack's own 5px gap.
            // Applied after the offset bookkeeping above so the step is a
            // draw-time dodge, never healed into the stored offsets; skipped
            // while this very name is being dragged so it tracks the cursor
            // out from under the headline.
            if (memberNamePass && nameMode === 'both'
                    && !(this.isDraggingScreenName && window.app && window.app.currentLayer
                        && window.app.currentLayer.id === layer.id)) {
                const gBox = this._bothModeGroupNameBox(plan, layer);
                if (gBox
                        && screenNameX + nameWidth / 2 > gBox.x1
                        && screenNameX - nameWidth / 2 < gBox.x2
                        && screenNameY + nameHeight / 2 > gBox.y1
                        && screenNameY - nameHeight / 2 < gBox.y2) {
                    screenNameY = _clamp(gBox.y2 + 5 + nameHeight / 2,
                        bounds.y + nameHeight / 2,
                        bounds.y + layerHeight - nameHeight / 2);
                }
            }

            const nameX = screenNameX - nameWidth / 2;
            const nameY = screenNameY - nameHeight / 2;

            // v0.8.7.7: cache the label rect in workspace (un-mirrored)
            // coords so a plain mousedown can hit-test it and start a
            // screen-name drag without needing a Shift modifier. Includes
            // the layer's canvas workspace offset and the per-layer Show
            // Look translate (this._renderDx / this._renderDy) so the
            // rect lines up with where the label is actually drawn on
            // screen across multi-canvas / Show Look views.
            if (!this.exportMode) {
                const _wsOff = (typeof this._layerCanvasOffset === 'function')
                    ? this._layerCanvasOffset(layer) : { wx: 0, wy: 0 };
                const _ldx = (typeof this._renderDx === 'number') ? this._renderDx : 0;
                const _ldy = (typeof this._renderDy === 'number') ? this._renderDy : 0;
                // v0.11.0: cached on `cfg`, so a group's single label has a
                // single owner for the plain-click drag hit-test. The 'both'
                // headline gets its own key on the same owner: the ordinary
                // key belongs to that member's own name in that display.
                const _nameRect = {
                    x1: _wsOff.wx + _ldx + nameX,
                    y1: _wsOff.wy + _ldy + nameY,
                    x2: _wsOff.wx + _ldx + nameX + nameWidth,
                    y2: _wsOff.wy + _ldy + nameY + nameHeight,
                    viewMode: this.viewMode,
                };
                if (groupLabelPass) cfg._groupNameHitRect = _nameRect;
                else cfg._screenNameHitRect = _nameRect;
            }

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
            this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
            if (this.viewMode === 'pixel-map') {
                currentY += screenNameHeight;
                if (centerLines.length > 0) {
                    currentY += 5; // Gap before other labels
                }
            } else {
                infoAnchorY = nameY + nameHeight + 5;
            }
        }

        // v0.8.7.7: when the user has dragged the screen-name label off
        // its default center position, the other identification labels
        // (port/circuit stats above, "Columns × Rows • Cabinets..." info
        // bar at the bottom) shift by the same offset so the whole label
        // group moves as one unit. Falls back to 0/0 when the layer has
        // no offset for the current view OR no screen name is shown.
        // v0.8.7.7.3: the size/info labels follow the name's *applied*
        // (post-clamp) offset on every tab, so the whole label group always
        // moves as a single unit and can never be clipped off-bounds on its
        // own. _appliedNameOffset is already in visual space (it accounts for
        // Back-view mirroring), so no extra mirror compensation is needed.
        let _labelGroupOffsetX = 0;
        let _labelGroupOffsetY = 0;
        if (screenName) {
            _labelGroupOffsetX = _appliedNameOffsetX;
            _labelGroupOffsetY = _appliedNameOffsetY;

            // v0.8.7.7.3: HEAL a runaway stored offset back to the clamped
            // value. The older snap-to-center clamp let the *stored* offset
            // balloon far past the layer (e.g. a name dragged behind a
            // now-hidden window could reach -1200 on an 840px screen) while
            // the label visually stayed put. That corrupt value persisted in
            // saved files and made the label feel unmovable on the next drag.
            // Writing the post-clamp value back here self-corrects those
            // offsets on the very next render, including right after a file
            // load, so re-dragging always starts from where the label
            // actually sits. Skipped while THIS layer's name is being dragged
            // (so we don't fight the live gesture) and in export.
            const _isDraggingThisName = groupLabelPass
                ? this.isDraggingGroupName
                : (this.isDraggingScreenName
                    && window.app && window.app.currentLayer
                    && window.app.currentLayer.id === cfg.id);
            if (!this.exportMode && !_isDraggingThisName) {
                // Stored offsets are in logical space; _appliedNameOffsetX is
                // in visual space (mirror already applied), so convert X back.
                // Healed onto whichever object the offsets were read from -
                // the layer, or the group for the 'both' headline.
                const _healX = this._mirror ? -_appliedNameOffsetX : _appliedNameOffsetX;
                const _healY = _appliedNameOffsetY;
                const _heal = (fx, fy) => {
                    if (Math.abs((nameCfg[fx] || 0) - _healX) > 0.5) nameCfg[fx] = _healX;
                    if (Math.abs((nameCfg[fy] || 0) - _healY) > 0.5) nameCfg[fy] = _healY;
                };
                if (this.viewMode === 'pixel-map') _heal('screenNameOffsetXPixelMap', 'screenNameOffsetYPixelMap');
                else if (this.viewMode === 'cabinet-id') _heal('screenNameOffsetXCabinet', 'screenNameOffsetYCabinet');
                else if (this.viewMode === 'data-flow') _heal('screenNameOffsetXDataFlow', 'screenNameOffsetYDataFlow');
                else if (this.viewMode === 'power') _heal('screenNameOffsetXPower', 'screenNameOffsetYPower');
                else if (this.viewMode === 'show-look') _heal('screenNameOffsetXShowLook', 'screenNameOffsetYShowLook');
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
            // v0.8.7.7: shift the center-info group horizontally by the
            // same offset the screen-name moved (Y is already tracked
            // via infoAnchorY for non-pixel-map, and via _labelGroupOffsetY
            // applied below for pixel-map).
            const bgX = (centerX + _labelGroupOffsetX) - bgWidth / 2;
            const bgY = (this.viewMode === 'pixel-map'
                ? currentY + _labelGroupOffsetY
                : (infoAnchorY ?? currentY));

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
            this.ctx.fillStyle = cfg.labelsColor || '#ffffff';
            let yPos = bgY + padding + lineHeight / 2;
            centerLines.forEach(line => {
                this._fillText(line, this.snap(centerX + _labelGroupOffsetX), this.snap(yPos));
                yPos += lineHeight;
            });

            this.ctx.restore();
        }
        
        // Render Info label at bottom with background.
        if (infoParts.length > 0) {
            // Use world coordinates directly (transform is already applied)
            this.ctx.font = `${infoFontSize}px ${projectFontFamily()}`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';

            // v0.10.7: greedily pack the clauses into lines that stay within the
            // layer's inner width, joined by " • ", so the info bar wraps and
            // stacks upward from the bottom edge instead of overflowing the
            // sides of a narrow screen. Wide screens still collapse to one line.
            const sep = ' • ';
            const maxLineWidth = Math.max(layerWidth - padding * 2, infoFontSize * 4);
            const infoLines = [];
            let currentLine = '';
            infoParts.forEach(part => {
                const candidate = currentLine ? currentLine + sep + part : part;
                if (currentLine && this.ctx.measureText(candidate).width > maxLineWidth) {
                    infoLines.push(currentLine);
                    currentLine = part;
                } else {
                    currentLine = candidate;
                }
            });
            if (currentLine) infoLines.push(currentLine);

            // Measure text for background
            let maxWidth = 0;
            infoLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });

            const bgWidth = maxWidth + padding * 2;
            const bgHeight = infoLines.length * infoLineHeight + padding * 2;
            // v0.8.7.7: bottom-anchored info bar follows the screen-name
            // offset so the whole label group moves together when the
            // user drags.
            const bgX = (centerX + _labelGroupOffsetX) - bgWidth / 2;
            const bgY = (bottomY + _labelGroupOffsetY) - bgHeight - padding;

            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedInfoRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedInfoRect.x, snappedInfoRect.y, snappedInfoRect.width, snappedInfoRect.height);

            // Draw text
            this.ctx.fillStyle = cfg.labelsColor || '#ffffff';
            let yPos = bgY + padding + infoLineHeight;
            infoLines.forEach(line => {
                this._fillText(line, this.snap(centerX + _labelGroupOffsetX), this.snap(yPos));
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

        // v0.9.3: use the rotated footprint so the corner X,Y readouts sit at the
        // rotated screen's corners and report that orientation's coordinates.
        const bounds = this.getLayerFootprintBounds(layer);
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
        
        this.ctx.font = `${fontSize}px ${projectFontFamily()}`;
        
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
    }

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
    }

    renderCustomSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlow(layer)) return;

        const selection = window.app.customSelection || new Set();
        if (selection.size === 0) return;

        this._renderScopedSelectionOverlay(layer, selection);
    }

    renderPowerSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPower(layer)) return;

        const selection = window.app.powerCustomSelection || new Set();
        if (selection.size === 0) return;

        this._renderScopedSelectionOverlay(layer, selection);
    }

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
    }

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
    }

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
    }

    _getCustomPowerCircuitPanelCount(layer, circuitNum) {
        const path = (layer.powerCustomPaths && layer.powerCustomPaths[circuitNum]) || [];
        if (!Array.isArray(path)) return 0;
        if (!window.app || typeof window.app.getPanelByRowCol !== 'function') return path.length;
        return this._resolvePathPanels(layer, path).length;
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
        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';
        const labelW = this.ctx.measureText(label).width;

        // Measure pills
        this.ctx.font = `bold ${countFontSize}px ${projectFontFamily()}`;
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
        this.ctx.font = `bold ${fontSize}px ${projectFontFamily()}`;
        this.ctx.fillStyle = labelColor;
        this.ctx.fillText(label, x + padding, y + padding);

        // Committed pill (white)
        const pillY = y + (boxH - pillH) / 2;
        let pillX = x + padding + labelW + gap;
        this.ctx.fillStyle = committed > 0 ? 'rgba(255, 255, 255, 0.18)' : 'rgba(255, 255, 255, 0.08)';
        this._roundRect(pillX, pillY, committedPillW, pillH, 8);
        this.ctx.fill();
        this.ctx.font = `bold ${countFontSize}px ${projectFontFamily()}`;
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
