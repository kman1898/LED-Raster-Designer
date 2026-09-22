// v0.8.8.x: build a canvas-text font shorthand using the project-wide font
// (preferences.font, defaults to Arial). Use this in place of hardcoded
// 'Arial' literals so the user's chosen font drives every on-canvas label.
function projectFontFamily() {
    return (window.app && typeof window.app.getProjectFont === 'function')
        ? window.app.getProjectFont() : 'Arial';
}

// The cable tags' two families (2026-09-06): power's gold on near-black
// (.cl .tag of cables-mock.html) and the data side's blue on dark (.snake
// .tag of snake-mock.html). One drawer, drawCableTag, takes either.
const POWER_CABLE_TAG_COLORS = { fill: '#1c1c1c', rim: '#c8a04a', ink: '#f0d48a' };
// The gang (2fer / 3fer) tag on the wall: the tray's gang chip, drawn -
// dark pill, white text, grey rim - so it never reads as a label disc.
const NFER_TAG_COLORS = { fill: '#2e2e2e', ink: '#ffffff', rim: '#9aa4b2' };
const DATA_CABLE_TAG_COLORS = { fill: '#10202c', rim: '#8fd0ff', ink: '#cfeaff' };

// The PRINTER palette (binder-mock.html, the "Printer" page): every colour
// the power and data passes pick goes through it when printerMode is on -
// cabinets in two greys, every run black and told apart by a dash pattern
// per circuit / port (eleven, cycled), label discs white with black text
// and a black rim, tags white with a black rim, brackets black. ONE flag,
// read where a colour is chosen; there is no second drawer.
const PRINTER_INK = '#111111';
const PRINTER_GREYS = ['#d6d6d6', '#e9e9e9'];
const PRINTER_BORDER = '#999999';
const PRINTER_TAG_COLORS = { fill: '#ffffff', rim: '#111111', ink: '#111111' };
// Dash patterns in units of the run's line width; [] is solid.
// The stages a view is drawn in, named the way a Photoshop user reads them,
// top to bottom of the layer stack. The PSD "Elements" export renders each
// one alone (CanvasRenderer.renderStages) and files it as its own layer.
//   Panels        the cabinet fills: checkerboard, palette, gradient, circuit tint
//   Borders       the cabinet borders and the dashed ghost of a hidden cabinet
//   Test pattern  the circle with an X
//   Cabinet IDs   the cabinet numbers (Cabinet ID view)
//   Data          the port runs, arrows and port labels (Data view)
//   Power         the circuits, circuit labels, 2fer brackets and cable tags
//   Screen name   the name plate, sizes, info bar and corner offsets
//   Image         the image layers
//   Text          the text layers
//   Canvas outline the canvas's dashed outline (drawn only when asked for)
//   Background    the solid backdrop (only when the export is not transparent)
const RENDER_STAGES = ['Screen name', 'Power', 'Data', 'Cabinet IDs', 'Test pattern',
    'Borders', 'Panels', 'Image', 'Text', 'Canvas outline', 'Background'];

const PRINTER_DASHES = [
    [], [3, 2], [1.2, 1.5], [5, 2, 1, 2], [2, 1], [6, 2],
    [1, 1], [4, 1, 1, 1], [3, 3], [2, 3], [5, 1],
];

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
        // The LABEL REGISTRY (2026-09-09). A screen map reaches a binder
        // sheet as ONE BITMAP: its band pills, its own L ruler, its label
        // discs, its cable tags and its gang tags are pixels inside that
        // image, not ops in the binder's display list, so no audit of the
        // sheet's ops can see the map writing on top of itself. Set this
        // to [] for ONE render (the same one-flag-for-one-render shape
        // hideScreenNames and printerMode use) and every piece of
        // lettering, every pill and the wall's own edges land in it as
        // { kind, text, x, y, w, h } in the bitmap's own pixels; leave it
        // null and the whole registry costs one null test per label.
        this.labelProbe = null;
        this._labelProbeRadii = null;
        this.showGrid = true;
        this.viewMode = 'pixel-map'; // Default view mode
        this.exportMode = false; // When true, hides grid and raster boundary for clean export
        // Binder pages (app-binder.js) name the screen in the page header
        // and want no name plate over the runs: they set this for the one
        // render and clear it after. The ordinary export leaves it false.
        this.hideScreenNames = false;
        // The binder's printer page: greys, black runs with a dash per
        // circuit, white discs - see PRINTER_* above and _ink / _runDash.
        this.printerMode = false;
        this.exportTransparentBg = false; // When true, export renders with transparent background
        // The PSD "Elements" export renders a view once per stage - the
        // cabinet fills, the borders, the arrows, the labels - each on its
        // own transparent canvas, and files each as its own layer. null (the
        // only value outside that export) paints everything, exactly as it
        // always has. A Set of stage names paints those stages ONLY; nothing
        // else about the render changes. The names are the layer names a
        // Photoshop user reads, see RENDER_STAGES.
        this.renderStages = null;

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
    // The printer palette's answers. `_ink` is the colour a run, an arrow, a
    // bracket or a rim takes: black on the printer page, the given colour
    // otherwise. `_runDash` is the dash pattern the Nth circuit / port
    // draws with on the printer page (scaled to the line width so a thin
    // run and a thick one read alike), and [] - solid - everywhere else.
    _ink(colour) {
        return this.printerMode ? PRINTER_INK : colour;
    }

    _runDash(num, lineWidth) {
        if (!this.printerMode) return [];
        const n = Math.max(1, parseInt(num, 10) || 1);
        const unit = Math.max(1, Number(lineWidth) || 1);
        return PRINTER_DASHES[(n - 1) % PRINTER_DASHES.length].map(v => v * unit);
    }

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

    // ---- the label registry -------------------------------------------
    //
    // Start collecting for ONE render, then read what the map wrote.
    // `startLabelProbe()` / `endLabelProbe()` bracket a render the way
    // hideScreenNames brackets a binder map; nothing else in the renderer
    // changes, so what the registry reports IS what the bitmap got.
    startLabelProbe() {
        this.labelProbe = [];
        this._labelProbeRadii = new WeakMap();
        return this.labelProbe;
    }

    endLabelProbe() {
        const out = this.labelProbe || [];
        this.labelProbe = null;
        this._labelProbeRadii = null;
        return out;
    }

    /**
     * Note one box the map drew, in the BITMAP's pixels. The renderer
     * paints in world units under a zoom/pan transform and, inside a
     * layer, under that layer's own translate (and a mirror on a Back
     * view), so the box is carried through ctx.getTransform() rather than
     * multiplied by this.zoom - a Back view's boxes would otherwise land
     * on the wrong side of the wall from the ink they describe. The
     * corners are transformed and the axis-aligned hull kept, which is
     * the box a rotated screen's label really covers.
     * A no-op, and no allocation at all, when the probe is off.
     */
    _noteLabelBox(kind, text, x, y, w, h, extra) {
        const probe = this.labelProbe;
        if (!probe) return;
        if (!Number.isFinite(x) || !Number.isFinite(y)
                || !Number.isFinite(w) || !Number.isFinite(h)) return;
        let m = null;
        try { m = this.ctx.getTransform(); } catch (e) { m = null; }
        const at = (px, py) => (m
            ? { x: m.a * px + m.c * py + m.e, y: m.b * px + m.d * py + m.f }
            : { x: px, y: py });
        const pts = [at(x, y), at(x + w, y), at(x, y + h), at(x + w, y + h)];
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        for (const p of pts) {
            x1 = Math.min(x1, p.x); x2 = Math.max(x2, p.x);
            y1 = Math.min(y1, p.y); y2 = Math.max(y2, p.y);
        }
        // `extra`: fields the caller adds beside the box - a cabinet id's
        // font size, so a test can hold a screen to one size.
        probe.push(Object.assign({ kind, text: (text === undefined || text === null) ? '' : String(text),
                                   x: x1, y: y1, w: x2 - x1, h: y2 - y1 }, extra || null));
    }

    /**
     * The wall's own edges, as the four lines the cabinets' outline draws
     * (zero thickness on the axis they run along). A pill or a tag that
     * STRADDLES one of these is a label sitting on the wall's boundary
     * rather than clear of it - the 2fer pills' fault, 2026-09-09.
     */
    _noteWallEdges(layer) {
        if (!this.labelProbe) return;
        if ((layer.type || 'screen') !== 'screen') return;
        const b = this.getLayerBounds(layer);
        if (!b || !(b.width > 0) || !(b.height > 0)) return;
        this._noteLabelBox('wallEdge', 'top', b.x, b.y, b.width, 0);
        this._noteLabelBox('wallEdge', 'bottom', b.x, b.y + b.height, b.width, 0);
        this._noteLabelBox('wallEdge', 'left', b.x, b.y, 0, b.height);
        this._noteLabelBox('wallEdge', 'right', b.x + b.width, b.y, 0, b.height);
    }

    // Leading for a label stacked inside a circular marker. Kept as one
    // definition because _layoutCircleLabel sizes the circle from it and
    // _fillWrappedLabel places the lines with it - if the two disagreed a
    // wrapped label would poke out of its circle. Same fontPx + 4 leading
    // the screen-label info block uses.
    _circleLabelLineHeight(fontPx) {
        return fontPx + 4;
    }

    /**
     * Lay a port/circuit label out for its circular marker. The marker
     * grows to fit its text (labels are never clipped), so a renamed port
     * like "SR A1" used to inflate the circle until it swallowed the
     * neighboring cabinets. A label with spaces may instead stack at the
     * spaces ("SR" over "A1"), keeping the text at the user's label size
     * AND the circle near its natural size. Rules:
     *   - break at whitespace when the label has any; a label with none
     *     may break at a hyphen instead, the hyphen staying at the end of
     *     the upper line the way a hyphenated word breaks ("SR3-" over
     *     "12"), or where a run of letters meets the digit after it
     *     ("SR" over "3-5") - "also SR3-5 can be stacked like data if it
     *     fits better" and, on how: "what about / SR / 3-5" (2026-09-07).
     *     Spaces win when present, so "SR A-1" still breaks only at its
     *     space. A label with none of these keeps the old grow-to-fit
     *     behaviour unchanged;
     *   - a label that fits the natural radius on one line never wraps;
     *   - among the candidate splits the smallest circle wins, and only
     *     beats the single line by a clear margin, so line count balances
     *     itself (a tall narrow stack needs a bigger circle than a
     *     slightly wider pair, and loses).
     * The caller must have ctx.font set to the label font already (widths
     * are measured with it). `minRadius` is the site's natural radius and
     * `padding` its text padding, so the no-wrap result reproduces the
     * site's old max(minRadius, textWidth/2 + padding) exactly.
     * Returns { lines, radius }; draw the lines via _fillWrappedLabel.
     */
    _layoutCircleLabel(label, fontPx, minRadius, padding) {
        const text = String(label);
        const widthOf = (s) => this.ctx.measureText(s).width;
        // The registry rides the pair the way app-binder-wiring.js's own
        // probe does: the SAME `lines` array travels from here to
        // _fillWrappedLabel, so noting the radius against it there reports
        // every disc's real centre and size without a word of the
        // placement being guessed. Free when the probe is off.
        const keep = (out) => {
            if (this._labelProbeRadii) {
                // the label as the CALLER wrote it: the wrap's own spaces
                // are the split's, not the name's
                this._labelProbeRadii.set(out.lines, { r: out.radius, text });
            }
            return out;
        };
        const oneLine = {
            lines: [text],
            radius: Math.max(minRadius, widthOf(text) / 2 + padding)
        };
        // Fits already, or nowhere legal to break: keep the single line.
        // The break units are the whitespace-separated tokens, rejoined
        // with a space; with no whitespace to break at, the pieces cut at
        // the hyphens and letter-digit seams, rejoined with nothing (a
        // piece keeps its own hyphen, so the joined lines are the label
        // exactly).
        const tokens = text.trim().split(/\s+/).filter(t => t.length > 0);
        const spaced = tokens.length >= 2;
        const units = spaced ? tokens : this._unspacedUnits(text.trim());
        const joiner = spaced ? ' ' : '';
        if (units.length < 2 || oneLine.radius <= minRadius) return keep(oneLine);

        const lineHeight = this._circleLabelLineHeight(fontPx);
        // Smallest circle containing every line's text box: each line is a
        // fontPx-tall box centered on its slot, and the box corner farthest
        // from the circle center is what the radius must reach.
        const radiusOfLines = (lines) => {
            const n = lines.length;
            let r = 0;
            for (let i = 0; i < n; i++) {
                const halfW = widthOf(lines[i]) / 2;
                const yEdge = Math.abs(i - (n - 1) / 2) * lineHeight + fontPx / 2;
                r = Math.max(r, Math.hypot(halfW, yEdge));
            }
            return Math.max(minRadius, r + padding);
        };
        // The whole label's width sets the split's target, not the joined
        // tokens' - the two differ on a label with doubled spaces, and the
        // no-wrap result must reproduce the old layout exactly.
        const totalWidth = widthOf(text);
        let best = oneLine;
        // 4 stacked lines is already a tall circle; more never reads well
        // and the radius math would reject it anyway.
        for (let n = 2; n <= Math.min(units.length, 4); n++) {
            const lines = this._balancedSplit(units, n, widthOf, totalWidth, joiner);
            const r = radiusOfLines(lines);
            // Strictly-better only (half-px margin): ties keep fewer lines,
            // and a wrap that doesn't shrink the circle isn't worth reading
            // the label in pieces.
            if (r < best.radius - 0.5) best = { lines, radius: r };
        }
        return keep(best);
    }

    /**
     * Greedy width-balanced split of `tokens` into `n` lines, breaking
     * only between tokens: each line takes tokens until adding the next
     * would carry it past an equal share of the whole width, and the last
     * line takes whatever is left. Optimal-enough for the handful of
     * tokens a port name or a cable tag has, without enumerating every
     * partition of a pathological label. ONE implementation for the
     * port/circuit label (_layoutCircleLabel) and the cable tag
     * (cableTagLayout), so the two wrap the same way. `widthOf` measures
     * a string in the caller's font (ctx.font must already be set);
     * `totalWidth` is the unsplit text's width when the caller has it
     * (a label with doubled spaces measures wider than its joined tokens).
     * `joiner` is what sits between two tokens on one line: a space
     * (the default) for word tokens, nothing for the hyphen pieces of an
     * unspaced label, which carry their own hyphen.
     */
    _balancedSplit(tokens, n, widthOf, totalWidth, joiner) {
        if (joiner === undefined) joiner = ' ';
        const total = totalWidth !== undefined ? totalWidth
            : widthOf(tokens.join(joiner));
        const target = total / n;
        const lines = [];
        let cur = tokens[0];
        for (let i = 1; i < tokens.length; i++) {
            const joined = cur + joiner + tokens[i];
            if (lines.length < n - 1 && widthOf(joined) > target) {
                lines.push(cur);
                cur = tokens[i];
            } else {
                cur = joined;
            }
        }
        lines.push(cur);
        return lines;
    }

    /**
     * The pieces an unspaced label may break between, cut at two kinds
     * of seam:
     *   - after a hyphen that sits between two non-empty parts; the
     *     hyphen stays on the piece before it, the way a hyphenated word
     *     breaks. A leading or trailing hyphen, or one of a doubled pair,
     *     is part of the name, not a seam: "-5", "SR-" and "A--B" stay
     *     whole there;
     *   - between a letter and the digit right after it ("SR" | "3"), so
     *     a side-and-number label can stack as its side over its number:
     *     "what about / SR / 3-5" (2026-09-07). A digit followed by a
     *     letter is NOT a seam ("3A" stays whole - the user rules only
     *     on the letters-then-number shape), and nothing cuts inside a
     *     run of one class.
     * So "SR3-5" gives ["SR", "3-", "5"], "S1-12-3" gives ["S", "1-",
     * "12-", "3"] and "A3B4" gives ["A", "3B", "4"]; the balanced split
     * then picks which seams actually break. Joining the pieces with
     * nothing reproduces the label exactly.
     */
    _unspacedUnits(text) {
        const isLetter = (c) => /[A-Za-z]/.test(c);
        const isDigit = (c) => /[0-9]/.test(c);
        const units = [];
        let start = 0;
        for (let i = 1; i < text.length; i++) {
            const prev = text[i - 1];
            const cur = text[i];
            // The hyphen at i-1 ends a piece when the characters either
            // side of it are both present and neither is another hyphen.
            const afterHyphen = prev === '-' && i >= 2
                && text[i - 2] !== '-' && cur !== '-';
            const letterToDigit = isLetter(prev) && isDigit(cur);
            if (afterHyphen || letterToDigit) {
                units.push(text.slice(start, i));
                start = i;
            }
        }
        units.push(text.slice(start));
        return units;
    }

    /**
     * Draw the lines from _layoutCircleLabel centered on (x, y). One line
     * delegates to _fillText so an unwrapped label renders exactly as it
     * always has. A stack applies the mirror/upright un-transform ONCE for
     * the whole block: per-line _fillText would counter-rotate each line
     * about its own anchor and stagger the stack diagonally on a rotated
     * screen, while the block belongs upright around the circle center.
     * The leading defaults to the circle label's; the cable tag passes
     * its own (its lines are left-aligned at x, through ctx.textAlign).
     */
    _fillWrappedLabel(lines, x, y, fontPx, lineHeight) {
        // A disc: lines _layoutCircleLabel sized, drawn at their circle's
        // centre. The cable tag's lines come from cableTagLayout instead
        // and are noted by drawCableTag with the pill they land in.
        if (this._labelProbeRadii && this._labelProbeRadii.has(lines)) {
            const k = this._labelProbeRadii.get(lines);
            this._noteLabelBox('disc', k.text, x - k.r, y - k.r, k.r * 2, k.r * 2);
        }
        if (lines.length === 1) {
            this._fillText(lines[0], x, y);
            return;
        }
        if (lineHeight === undefined) {
            lineHeight = this._circleLabelLineHeight(fontPx);
        }
        const n = lines.length;
        const upright = this._keepTextUpright && this._activeRotationRad;
        if (this._mirror || upright) {
            this.ctx.save();
            this.ctx.translate(x, y);
            if (upright) this.ctx.rotate(-this._activeRotationRad);
            if (this._mirror) this.ctx.scale(-1, 1);
            for (let i = 0; i < n; i++) {
                this.ctx.fillText(lines[i], 0, (i - (n - 1) / 2) * lineHeight);
            }
            this.ctx.restore();
        } else {
            for (let i = 0; i < n; i++) {
                this.ctx.fillText(lines[i], x, y + (i - (n - 1) / 2) * lineHeight);
            }
        }
    }

    // Does this render paint the named stage? Always yes outside the PSD
    // Elements export (renderStages null); inside it, only the stages named.
    _stageOn(name) {
        return !this.renderStages || this.renderStages.has(name);
    }

    // The SVG export's group for what draws next (app-export-svg.js): the
    // recording context the export paints through takes the name and files
    // every op after it under it - `layer` names the screen the element
    // belongs to (an image or text layer files under Images / Text). A
    // real context has no __lrdGroup, so outside that export this is a no-op.
    _svgGroup(name, layer) {
        const ctx = this.ctx;
        if (ctx && typeof ctx.__lrdGroup === 'function') ctx.__lrdGroup(name, layer || null);
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
        // The EDITING predicate, not the pattern: an overridden port open for
        // redrawing draws with exactly the gestures whole-screen custom does.
        const drawing = (this.viewMode === 'data-flow' && app.isCustomFlowEditing && app.isCustomFlowEditing(owner))
            || (this.viewMode === 'power' && app.isCustomPowerEditing && app.isCustomPowerEditing(owner));
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
                        this._svgGroup(kind === 'power' ? 'Power' : 'Data', layer);
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
        if (!this._runUnderlayLit(layer, num)) return;
        if (!panels || !panels.length) return;
        this.ctx.save();
        this.ctx.strokeStyle = this._accentUnderlayColor();
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

    // The underlay's colour is the app's accent - the same "target of the
    // gesture" the dock's drop outline and the selected tiles wear - read
    // from the theme's variable at paint time so it follows the accent
    // picker. Translucent so it stays an underlay, not a line; the old
    // fixed blue remains the fallback for a themeless page.
    _accentUnderlayColor() {
        try {
            const hex = getComputedStyle(document.documentElement)
                .getPropertyValue('--ps-accent-hi').trim();
            const m = /^#?([0-9a-f]{6})$/i.exec(hex);
            if (m) {
                const v = parseInt(m[1], 16);
                return `rgba(${(v >> 16) & 255}, ${(v >> 8) & 255}, `
                    + `${v & 255}, 0.55)`;
            }
        } catch (e) { /* fall through to the fixed colour */ }
        return 'rgba(120, 180, 255, 0.55)';
    }

    // Should this run's underlay light up? Two askers share the one paint:
    // the dock drag's drop target, exactly as before, and the held-Alt
    // override hover (app.updateOverrideHover), which names one run in one
    // view - the same highlight for both because they mean the same thing,
    // "this is the run the gesture lands on".
    // Extend the sweep to the run under the cursor: the selection is the
    // CONTIGUOUS range of the owner's plan between the anchor run and the
    // hovered run - adjacency by construction, the reason the gesture needs
    // no refusal. A cursor over another screen (or over nothing) keeps the
    // last range; the sweep never jumps walls.
    _sweepExtend(worldX, worldY, clientX, clientY) {
        const p = this._sweepPending;
        const app = window.app;
        if (!p || !p.anchor || !app) return;
        const owner = (app.project.layers || [])
            .find(l => l.id === p.anchor.ownerId);
        if (!owner) return;
        const circuits = app.screenCircuits(owner);
        const ai = circuits.findIndex(c => c.num === p.anchor.num);
        if (ai < 0) return;
        let ci = ai;
        const run = typeof app.runAtPoint === 'function'
            ? app.runAtPoint(worldX, worldY) : null;
        if (run && run.kind === 'power' && run.layer.id === owner.id) {
            const k = circuits.findIndex(c => c.num === run.num);
            if (k >= 0) ci = k;
        }
        const lo = Math.min(ai, ci);
        const hi = Math.max(ai, ci);
        const nums = circuits.slice(lo, hi + 1).map(c => c.num);
        const prev = app._sweepSelection;
        const same = prev && prev.layerId === owner.id
            && Array.isArray(prev.nums) && prev.nums.length === nums.length
            && prev.nums.every((n, i) => n === nums[i]);
        app._sweepSelection = { layerId: owner.id, nums };
        this._sweepHud(clientX, clientY, owner, nums);
        if (!same) this.render();
    }

    // The counter pill riding the cursor mid-sweep: "3 circuits · 24.5 A".
    // Plain facts only - the OVER story belongs to the menu's deal and the
    // committed brackets, where a GROUP has a load to answer for.
    _sweepHud(clientX, clientY, owner, nums) {
        let hud = document.getElementById('power-sweep-hud');
        if (!hud) {
            hud = document.createElement('div');
            hud.id = 'power-sweep-hud';
            hud.style.cssText = 'position:fixed; z-index:10000;'
                + 'pointer-events:none; font-size:11px; padding:2px 9px;'
                + 'border-radius:10px; background:#2e2e2e;'
                + 'border:1px solid #666; color:#eee;'
                + 'box-shadow:0 3px 10px rgba(0,0,0,.5); white-space:nowrap;';
            document.body.appendChild(hud);
        }
        const app = window.app;
        const byNum = new Map();
        if (app && typeof app.getSocaPlan === 'function') {
            (app.getSocaPlan(owner) || []).forEach(s =>
                (s.legs || []).forEach(l => byNum.set(l.circuit, l.amps)));
        }
        const amps = nums.reduce((t, n) => t + (byNum.get(n) || 0), 0);
        hud.textContent = `${nums.length} circuit${nums.length === 1 ? '' : 's'}`
            + ` · ${amps.toFixed(1)} A`;
        hud.style.left = (clientX + 14) + 'px';
        hud.style.top = (clientY - 26) + 'px';
    }

    _removeSweepHud() {
        const hud = document.getElementById('power-sweep-hud');
        if (hud) hud.remove();
    }

    _runUnderlayLit(layer, num) {
        // The sweep selection wears the same underlay the dock drop and the
        // held-Alt hover wear - one grammar for "this run is the gesture's
        // target", drawn from inside the run's own pass so every transform
        // rides along.
        const sw = window.app && window.app._sweepSelection;
        if (sw && this.viewMode === 'power' && sw.layerId === layer.id
                && Array.isArray(sw.nums) && sw.nums.includes(num)) {
            return true;
        }
        const hov = window.app && window.app._overrideHover;
        if (hov && hov.layerId === layer.id && hov.num === num
                && ((hov.kind === 'power') === (this.viewMode === 'power'))) {
            return true;
        }
        const t = window.app && window.app._dockDropTarget;
        if (!t || t.layerId !== layer.id) return false;
        if (t.kind !== 'run' && t.kind !== 'screen') return false;
        const nums = Array.isArray(t.nums) ? t.nums : null;
        if (t.kind === 'run'
                && !(nums ? nums.includes(num) : t.num === num)) return false;
        if (t.kind === 'screen' && nums && !nums.includes(num)) return false;
        return true;
    }

    render() {
        // v0.8.7.8: bump a per-render token so screen-fill gradients are built
        // at most once per layer per frame (cached on the layer keyed by this).
        this._renderPass = (this._renderPass || 0) + 1;
        if (this.layerSelectionRect && !this.isSelectingLayers && !this.isSelectingPanels && !this.isDraggingLayer) {
            this.layerSelectionRect = null;
        }
        this._svgGroup('Background');
        // In export mode with transparent bg, clear to transparent; otherwise fill
        if ((this.exportMode && this.exportTransparentBg) || !this._stageOn('Background')) {
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
                        this._svgGroup('Images', layer);
                        if (this._stageOn('Image')) this.renderImageLayer(layer);
                        if (needsShift) this.ctx.restore();
                        return;
                    }
                    if ((layer.type || 'screen') === 'text') {
                        this._svgGroup('Text', layer);
                        if (this._stageOn('Text')) this.renderTextLayer(layer);
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
                        // may land inside the view even if its unrotated pos is out
                        // - and skip it for a drawing the raster does not bound,
                        // see ignoreRasterBounds in renderPanel.
                        if (!_rotating && !this.ignoreRasterBounds
                            && (panel.x + dx >= this.rasterWidth
                                || panel.y + dy >= this.rasterHeight)) return;

                        // Render all panels - visible and hidden (hidden as ghost outlines)
                        this.renderPanel(panel, layer);
                    });

                    // The wall's own edges, for the label registry: noted
                    // in the very frame the cabinets were drawn in.
                    if (this.labelProbe) this._noteWallEdges(layer);

                    // Render Circle with X test pattern. Every condition lives
                    // inside, because a group draws ONE pattern across its
                    // members and the decision about which member draws it
                    // cannot be made from this layer alone.
                    this._svgGroup('Test pattern', layer);
                    if (this._stageOn('Test pattern')) this.renderCircleWithX(layer);

                    // Render Cabinet ID numbers in world space (scales with zoom)
                    if (this.viewMode === 'cabinet-id' && this._stageOn('Cabinet IDs')) {
                        this._svgGroup('Cabinet IDs', layer);
                        this.renderCabinetIDNumbers(layer);
                    }

                    // Data/Power flow arrows rotate with the panels, but their
                    // technical labels (P1/R1, port/circuit info) stay upright.
                    if (this.viewMode === 'data-flow' && this._stageOn('Data')) {
                        this._svgGroup('Data', layer);
                        this._keepTextUpright = _rotating;
                        this.renderDataFlowArrows(layer);
                        this._keepTextUpright = false;
                    }
                    if (this.viewMode === 'power' && this._stageOn('Power')) {
                        this._svgGroup('Power', layer);
                        this._keepTextUpright = _rotating;
                        this.renderPowerArrows(layer);
                        // A ganged circuit says so on the wall: the Nfer
                        // bracket under its runs' feet (2026-08-30). Always
                        // on - a share that barely reads is the problem it
                        // exists to fix - and in exports too: it lives
                        // BELOW the screen, the soca brackets above, so
                        // the two never fight.
                        this.renderNferBrackets(layer);
                        // Brackets draw only when explicitly ticked (=== true,
                        // matching the soca panel's checkbox): the user asked
                        // for them off by default.
                        if (layer.showSocaBrackets === true) this.renderSocaBrackets(layer);
                        // A plug drag over this screen previews its box as
                        // a dashed bracket even with brackets off: gesture
                        // feedback, not paperwork, so it needs no tick -
                        // and with no drag on, an unticked screen draws no
                        // bracket at all (the multiselect suite pins it).
                        else if (this._pendingPlugFor(layer)) this.renderSocaBrackets(layer, true);
                        this._keepTextUpright = false;
                    }

                    // Render labels as part of each layer so upper layers naturally
                    // paint over lower layers' labels (no bleed-through). The screen
                    // name rotates with the screen (keepTextUpright is off here).
                    this._svgGroup('Screen name', layer);
                    if (this._stageOn('Screen name')) this.renderLayerLabels(layer);

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
                    this._svgGroup('Screen name', layer);
                    if (this._stageOn('Screen name')) this.renderLayerOffsets(layer);

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
                // Never part of a picture export - unless the Elements
                // export asks for it by name, as its own layer to keep or bin.
                if (this.renderStages
                        ? this.renderStages.has('Canvas outline')
                        : !this.exportMode) {
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
            if ((this.viewMode === 'data-flow' && this._stageOn('Data'))
                    || (this.viewMode === 'power' && this._stageOn('Power'))) {
                this._renderCrossMemberPaths(this.viewMode === 'power' ? 'power' : 'data');
            }

            // The custom-run readout in the canvas strip follows this frame:
            // whichever view is up, if no badge call fired (not custom mode,
            // another view, no layer) the readout hides. An export render
            // never touches it - the strip is not on paper and the next
            // interactive frame is the one that decides.
            if (!this.exportMode) this._activeBadgeShown = false;
            if (!this.exportMode && this.viewMode === 'data-flow') {
                this.renderCustomSelectionOverlay();
                this.renderCustomActivePortBadge();
            }
            if (!this.exportMode && this.viewMode === 'power') {
                this.renderPowerSelectionOverlay();
                this.renderPowerActiveCircuitBadge();
            }
            if (!this.exportMode && !this._activeBadgeShown) this._syncCustomRunReadout(null);
            if (!this.exportMode && this.viewMode === 'pixel-map') {
                this.renderPixelMapSelectionOverlay();
                this.renderPixelMapSelectionBadge();
            }
            // Always show the perspective badge (BACK VIEW) in wiring views
            // when in back perspective. Renders in both interactive view and
            // export so the printed map is unambiguous.
            // The badge and the error overlays belong to the wiring they
            // annotate: the Data stage on the Data view, Power on Power.
            const _wiringStageOn = this.viewMode === 'data-flow' ? this._stageOn('Data')
                : this.viewMode === 'power' ? this._stageOn('Power') : true;
            if ((this.viewMode === 'data-flow' || this.viewMode === 'power') && _wiringStageOn) {
                this._svgGroup('Back view');
                this.renderPerspectiveBadge();
            }

            // Third pass: render capacity error overlays ON TOP of labels (Data Flow mode only)
            if (this.viewMode === 'data-flow' && _wiringStageOn) {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        this._svgGroup('Data', layer);
                        _withLayerWs(layer, () => this.renderCapacityErrorOverlay(layer));
                    }
                });
            }
            if (this.viewMode === 'power' && _wiringStageOn) {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        this._svgGroup('Power', layer);
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
        // An open override edit is a gesture of the view it began in; a tab
        // switch closes it (the override itself stays). The hover highlight
        // goes with it.
        if (window.app && window.app._overrideEditing
                && typeof window.app.endOverrideEdit === 'function') {
            window.app.endOverrideEdit();
        }
        if (window.app && window.app._overrideHover
                && typeof window.app.updateOverrideHover === 'function') {
            window.app.updateOverrideHover(false, 0, 0);
        }
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
        if (this.printerMode) return PRINTER_BORDER;
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
        //
        // `ignoreRasterBounds` skips it for the same reason from the other
        // direction: the binder draws ONE screen on its own sheet, where the
        // processor's raster is not what bounds the drawing. Clipping to it
        // there silently cut the wall - a screen standing 1900 units down the
        // canvas printed no cabinets at all on its sheet while its outline,
        // its rulers and its labels drew, and one at 800 lost every row past
        // the raster's height (2026-09-11). A Pixel Map export still clips,
        // because there a panel outside the raster really is outside the
        // picture.
        if (this._layerRotating || this.ignoreRasterBounds) {
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
        this._svgGroup('Panels', layer);
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
        if (this.printerMode) {
            return PRINTER_GREYS[((Number(panel.row) || 0) + (Number(panel.col) || 0)) % 2];
        }
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
            if (!this._stageOn('Borders')) return;
            this._svgGroup('Borders', layer);
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
        if (!layer.transparentFill && this._stageOn('Panels')) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            // v0.8.7.8: gradient overlay on top of the checkerboard, below borders.
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width in LED pixels, drawn INSIDE the
        // panel. Where two panels meet, you get 2× the width total.
        if (layer.show_panel_borders && this._stageOn('Borders')) {
            this._svgGroup('Borders', layer);
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
            if (!this._stageOn('Borders')) return;
            this._svgGroup('Borders', layer);
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }
        
        // Base cabinet fill: 2-color checkerboard or multi-color palette.
        // transparentFill = render cabinets see-through (no fill / no gradient).
        if (!layer.transparentFill && this._stageOn('Panels')) {
            this.ctx.fillStyle = this._panelBaseFill(panel, layer);
            this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            // v0.8.7.8: gradient overlay on top of the checkerboard, below borders.
            this._applyGradientOverlay(panel, layer);
        }

        // Panel borders, per-layer width, drawn INSIDE the panel.
        if (layer.show_panel_borders && this._stageOn('Borders')) {
            this._svgGroup('Borders', layer);
            const bw = Math.max(1, Number(layer.panel_border_width) || 2);
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'cabinet-id');
            this.ctx.lineWidth = bw;
            const inset = bw / 2;
            this.ctx.strokeRect(panel.x + inset, panel.y + inset, panel.width - bw, panel.height - bw);
        }

        // Cabinet ID numbers rendered separately in screen space - see renderCabinetIDNumbers()
    }
}

// The PSD Elements export (app-export-io.js) renders these one at a time.
CanvasRenderer.RENDER_STAGES = RENDER_STAGES;

window.CanvasRenderer = CanvasRenderer;
