// app-rigging: the Header/Footer tab's left column. A Header | Footer choice
// (which side of the selected screens carries bars), an Auto | Custom
// choice, a row of bar sizes (1-4 panels wide, single to quad; 3 and up sit
// behind a + button), and in Auto an Auto button that fits bars of the lit
// sizes across every selected screen's width; in Custom one size is picked
// and the person clicks or drags in the bar strip outside the wall on the
// canvas (canvas-input.js) to lay bars of it. The sizes and the bars ride on each
// screen; the bars draw in this view (canvas-rigging.js), and
// riggingPullRows hands them to the pull list (app-pull-list.js).
//
// ONE SIDE PER SCREEN (owner, 2026-11-08: "it can only be one or the
// other"): a screen has header bars OR footer bars. The Header | Footer
// buttons set the selected screens' side; switching moves the bars over
// unchanged, one undo step. A show saved with both on one screen opens
// unchanged: the tab's warning box lists the screen with Keep Header and
// Keep Footer, and until one is pressed everything shows what is stored.
//
// STORED SHAPE: riggingBars (header) / riggingFooterBars (footer) are the
// bar sizes left to right, as always. A row that does not run end to end
// from the wall's left edge (a gap in a custom row, or the second screen of
// a row that crosses a group's seam) also stores riggingBarStarts /
// riggingFooterBarStarts: the panel each bar starts on. Null otherwise, so
// an older show reads exactly as it did (RiggingMath.placedOf).
// riggingSide remembers the side of a screen with no bars yet, and
// riggingCustom marks a row laid by hand (gaps allowed).
//
// GROUPS CROSS (owner, 2026-11-08: "they need to cross"): the members of a
// group that stand edge to edge in Show Look, the same panel width and
// their bar edges lined up, form ONE row (riggingRow). Auto fits across the
// whole row, a bar may straddle the seam, Custom works across it. Each bar
// is STORED ON THE MEMBER IT STARTS ON (that member's own panels; a
// straddling bar runs past its edge), so it is counted once wherever bars
// are counted per screen (the totals, the pull list, the binder tables),
// undo and the lock keep working screen by screen, and an old group whose
// members already have bars reads as one row with nothing changed.
//
// A LOCKED SCREEN STAYS UNCHANGED: the buttons go through _writableLayers
// (or refuse a whole row, which cannot change half way), which names the
// locked screens on every press; the colors, which stream while the picker
// is dragged, go through the applyToSelectedLayers hold.
//
// BARS THAT NO LONGER FIT (owner, 2026-11-06: "the bars no longer fit and
// offer Auto again, rather than changing them silently"): an Auto row still
// has to cover its wall edge to edge; a custom row may have gaps, and only a
// bar past the wall's edge (or two on one panel) is wrong. Nothing here
// touches such a row until the person says. riggingMisfits finds them; the
// tab's warning box names them and offers Auto, a toast says so the moment
// the edit lands (riggingFitCheck), the canvas draws them at their true
// width (canvas-rigging.js), and the pull rows, the binder and every export
// say so too.
//
// A ROW SPLITS AT A CORNER (owner, 2026-11-09): a screen's corners (the
// Corners under the Curve, app-corners.js, every one 90 degrees) each
// take a corner piece over the panels touching the corner (rigging-math.js
// cornerPieces): the folded panel of a corner down a panel's middle, the
// "Header Bar - Corner (1 panel)", or one panel either side of a corner
// on a seam, the "Header Bar - Corner (2 panel)"; two different parts,
// each its own line wherever bars are counted (owner, 2026-11-10).
// Regular bars fill each side; none crosses a corner. Auto lays every corner's piece and fits each side on its own; Clear
// takes them off with the bars. In Custom, a click or drag over a
// corner's panels lays its piece, a bar that would run onto a corner
// stops at it (or is refused, said, when it no longer fits there), and a
// picked piece comes off with Delete. A piece is kept on its corner
// (`bar`), so it is counted once, on its screen, everywhere bars are: the
// tab's totals, the pull list and the binder's Header/Footer and pull
// sheets. A screen turned a quarter (its bars run along its folds) takes
// no pieces. A curved screen's Curve lays its bars on each side up to its
// corners, and the pieces with them, each side curved as its own wall
// (app-curve.js).
import { LEDRasterApp } from './app-core.js';
import { setupColorPickerWithHex } from './helpers.js';
import { s3dCleanCorners, s3dCornersOn } from './app-stage3d.js';

// Bars come single, double, triple and quad, 1 to 4 panels wide.
const RIGGING_SIZES = [1, 2, 3, 4];
const DEFAULT_SIZES = [1, 2];
const DEFAULT_CUSTOM_SIZE = 2;
const DEFAULT_BAR_COLOR = '#000000';
const DEFAULT_TEXT_COLOR = '#FFFFFF';
// The layer fields each row of bars lives in.
const BAR_FIELD = { header: 'riggingBars', footer: 'riggingFooterBars' };
const START_FIELD = { header: 'riggingBarStarts', footer: 'riggingFooterBarStarts' };
const KIND_WORD = { header: 'Header', footer: 'Footer' };
const KINDS = ['header', 'footer'];

const plain = (placed) => (placed || []).map(b => ({ start: b.start, size: b.size }));
const listWords = (names) => (names.length <= 1 ? (names[0] || '')
    : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

class _Rigging {
    _wireRigging() {
        const picker = document.getElementById('rigging-size-picker');
        const auto = document.getElementById('rigging-auto-btn');
        const clear = document.getElementById('rigging-clear-btn');
        if (!picker || !auto || !clear) return;

        document.querySelectorAll('#rigging-mode-picker .rigging-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setRiggingSide(btn.dataset.mode === 'footer' ? 'footer' : 'header'));
        });
        document.querySelectorAll('#rigging-tool-picker .rigging-tool-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setRiggingTool(btn.dataset.tool === 'custom' ? 'custom' : 'auto'));
        });
        picker.querySelectorAll('.rigging-size-btn[data-size]').forEach(btn => {
            btn.addEventListener('click', () => this.toggleRiggingSize(parseInt(btn.dataset.size, 10)));
        });
        // 3 and up stay behind the + until it is pressed.
        const more = document.getElementById('rigging-size-more');
        if (more) more.addEventListener('click', () => {
            this._riggingMoreOpen = !this._riggingMoreOpen;
            this.refreshRiggingPanel();
        });
        const selectAll = document.getElementById('rigging-select-all-btn');
        if (selectAll) selectAll.addEventListener('click', () => this.selectAllRiggingScreens());
        auto.addEventListener('click', () => this.applyAutoRigging());
        clear.addEventListener('click', () => this.clearRiggingBars());
        const fitAuto = document.getElementById('rigging-fit-auto');
        if (fitAuto) fitAuto.addEventListener('click', () => this.fitMisfitRigging());
        // Keep Header / Keep Footer, one pair per screen that has both.
        const both = document.getElementById('rigging-both-list');
        if (both) both.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-keep]') : null;
            if (btn) this.keepRiggingSide(Number(btn.dataset.layerId), btn.dataset.keep);
        });

        // Bar color: live while dragging, saved (and undoable) on release.
        // One color pair per screen, for its header and footer bars alike.
        setupColorPickerWithHex('rigging-color', 'rigging-color-hex', (val, isFinal) => {
            this._setRiggingColor('riggingColor', val, isFinal, 'Bar Color');
        });
        setupColorPickerWithHex('rigging-text-color', 'rigging-text-color-hex', (val, isFinal) => {
            this._setRiggingColor('riggingTextColor', val, isFinal, 'Bar Text Color');
        });
        // The Curve's checkbox and form (app-curve.js).
        if (typeof this._wireRiggingCurve === 'function') this._wireRiggingCurve();
        // The Corners under it (app-corners.js).
        if (typeof this._wireRiggingCorners === 'function') this._wireRiggingCorners();
    }

    _setRiggingColor(field, val, isFinal, action) {
        if (this._riggingScreens().length === 0) return;
        this.applyToSelectedLayers(l => {
            if ((l.type || 'screen') === 'screen') l[field] = val;
        });
        if (isFinal) {
            const screens = this._riggingScreens().filter(l => !this._layerLocked(l));
            if (screens.length) this.updateLayers(screens, true, action);
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    _riggingScreens() {
        return this.getSelectedLayers().filter(l => (l.type || 'screen') === 'screen');
    }

    _riggingPrimary(screens = this._riggingScreens()) {
        return this.currentLayer && screens.includes(this.currentLayer) ? this.currentLayer : screens[0];
    }

    // The screens and every other member of their groups: a group's side and
    // its rows of bars are the group's.
    _riggingWithGroups(screens) {
        const out = [];
        const seen = new Set();
        const add = (l) => { if (l && !seen.has(l.id) && (l.type || 'screen') === 'screen') { seen.add(l.id); out.push(l); } };
        for (const l of screens || []) {
            add(l);
            if (typeof this.groupMembersOf === 'function') this.groupMembersOf(l).forEach(add);
        }
        return out;
    }

    // ---- what is stored -------------------------------------------------

    // The bars of one row on a screen, as sizes (always an array).
    riggingBarsOf(layer, kind) {
        const bars = layer && layer[BAR_FIELD[kind === 'footer' ? 'footer' : 'header']];
        return Array.isArray(bars) ? bars : [];
    }

    // The bars of one row on a screen as { start, size } in its own panels.
    riggingPlaced(layer, kind) {
        const k = kind === 'footer' ? 'footer' : 'header';
        return layer ? RiggingMath.placedOf(layer[BAR_FIELD[k]], layer[START_FIELD[k]]) : [];
    }

    // ---- corner pieces (rigging-math.js cornerPieces) ------------------

    // Can a screen's corners split its row? Not when the screen is turned
    // a quarter (its bars run along its folds).
    _riggingCornersApply(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return false;
        const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
        if (deg === 90 || deg === 270) return false;
        return true;
    }

    // Every corner of a screen with the panels its piece covers,
    // in the screen's own bar panels (left to right as it stands):
    // [{ at, start, size, bar }], `bar` where the piece is laid.
    riggingCornerSpots(layer) {
        if (!this._riggingCornersApply(layer)) return [];
        const cols = Number(layer.columns) || 0;
        const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
        return RiggingMath.cornerPieces(s3dCornersOn(layer, cols), cols, deg === 180);
    }

    // The corner pieces laid on a screen.
    riggingCornerPiecesOf(layer) {
        return this.riggingCornerSpots(layer).filter(s => s.bar);
    }

    // Lay (on) or take off the pieces of the corners at `ats` on a screen.
    _riggingSetCornerBars(layer, ats, on) {
        const want = new Set(ats);
        const list = s3dCleanCorners(layer && layer.riggingCorners);
        let changed = false;
        const next = list.map(c => {
            if (!want.has(c.at) || (c.bar === true) === on) return c;
            changed = true;
            const out = { at: c.at, angle: c.angle, side: c.side };
            if (on) out.bar = true;
            return out;
        });
        if (changed) layer.riggingCorners = next;
        return changed;
    }

    _riggingWrite(layer, kind, placed) {
        const { bars, starts } = RiggingMath.storeOf(placed);
        layer[BAR_FIELD[kind]] = bars;
        layer[START_FIELD[kind]] = starts;
        layer.riggingSide = kind;
    }

    // The side a screen carries bars on: 'header', 'footer', or 'both' for
    // a show saved before a screen could have only one. A screen with no
    // bars is on the side it was last set to, the header by default.
    riggingSideOf(layer) {
        if (!layer) return 'header';
        const h = this.riggingBarsOf(layer, 'header').length > 0;
        const f = this.riggingBarsOf(layer, 'footer').length > 0;
        if (h && f) return 'both';
        if (h) return 'header';
        if (f) return 'footer';
        return layer.riggingSide === 'footer' ? 'footer' : 'header';
    }

    // The sides a screen's rows are on: one, or two on an old show's 'both'.
    _riggingKindsOf(layer) {
        const side = this.riggingSideOf(layer);
        return side === 'both' ? KINDS : [side];
    }

    // The sizes the Auto picker shows: the current screen's. A screen nobody
    // has picked for starts on 1 and 2; a screen whose picks were all
    // switched off keeps its empty list. A size past a quad, lit before the
    // picker stopped at 4, is left out, so Auto never fits a bar nobody
    // stocks.
    _riggingSizesOf(layer) {
        if (!layer) return [];
        return Array.isArray(layer.riggingSizes)
            ? layer.riggingSizes.filter(s => RIGGING_SIZES.includes(s)) : [...DEFAULT_SIZES];
    }

    // Auto (fit the lit sizes) or Custom (click or drag one size in the
    // bar strip). SAVED WITH THE SHOW, ONE CHOICE FOR THE WHOLE SHOW
    // (project.riggingTool; owner, 2026-11-08: the choice is saved). It is
    // a way of working, not a property of a wall: in Custom every wall's
    // bar strip lays bars, whichever screen is selected, so a per-screen
    // choice would change under the person as they clicked from wall to
    // wall. View state like the IDM Locator's field: never an undo step,
    // and undo, redo and a reload keep it. A show without it opens on Auto.
    _riggingToolNow() {
        return this.project && this.project.riggingTool === 'custom' ? 'custom' : 'auto';
    }

    riggingCustomSize() {
        return RIGGING_SIZES.includes(this._riggingCustomSize) ? this._riggingCustomSize : DEFAULT_CUSTOM_SIZE;
    }

    // ---- rows of bars, across a group's seams ---------------------------

    // Where a screen stands in Show Look, in workspace pixels, turned the
    // way it stands: { id, x, y, w, h, panels }.
    _riggingRect(layer) {
        const r = window.canvasRenderer;
        const b = (r && typeof r.getLayerBounds === 'function') ? r.getLayerBounds(layer) : {
            x: Number(layer.offset_x) || 0, y: Number(layer.offset_y) || 0,
            width: (Number(layer.columns) || 0) * (Number(layer.cabinet_width) || 0),
            height: (Number(layer.rows) || 0) * (Number(layer.cabinet_height) || 0),
        };
        const procX = Number(layer.offset_x) || 0;
        const procY = Number(layer.offset_y) || 0;
        const showX = layer.showOffsetX != null ? Number(layer.showOffsetX) : procX;
        const showY = layer.showOffsetY != null ? Number(layer.showOffsetY) : procY;
        let x = b.x + showX - procX, y = b.y + showY - procY, w = b.width, h = b.height;
        const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
        if (deg === 90 || deg === 270) {
            const cx = x + w / 2, cy = y + h / 2;
            [w, h] = [h, w];
            x = cx - w / 2; y = cy - h / 2;
        }
        const cid = layer.show_canvas_id || layer.canvas_id || null;
        const c = cid ? ((this.project && this.project.canvases) || []).find(cv => cv && cv.id === cid) : null;
        const wx = c ? (c.show_workspace_x == null ? (c.workspace_x || 0) : (c.show_workspace_x || 0)) : 0;
        const wy = c ? (c.show_workspace_y == null ? (c.workspace_y || 0) : (c.show_workspace_y || 0)) : 0;
        return { id: layer.id, x: x + wx, y: y + wy, w, h, panels: this.riggingWallPanels(layer) };
    }

    // The run of screens `layer` shares a row with on one side: itself
    // alone, or the members of its group that stand edge to edge with it
    // (RiggingMath.runsOf). { layers, ids, offsets, panels, width }.
    _riggingRunOf(layer, kind) {
        const n = this.riggingWallPanels(layer);
        const alone = { layers: [layer], ids: [layer.id], offsets: [0], panels: [n], width: n };
        if (!this._riggingKindsOf(layer).includes(kind)) return alone;
        const members = typeof this.groupMembersOf === 'function' ? this.groupMembersOf(layer) : [];
        if (members.length < 2) return alone;
        const peers = members.filter(m => m === layer || this._riggingKindsOf(m).includes(kind));
        if (peers.length < 2) return alone;
        const run = RiggingMath.runsOf(peers.map(m => this._riggingRect(m)), kind)
            .find(u => u.ids.includes(layer.id));
        if (!run || run.ids.length < 2) return alone;
        const byId = new Map(peers.map(m => [m.id, m]));
        return { ...run, layers: run.ids.map(id => byId.get(id)) };
    }

    // One row of bars: the screens it runs across, every bar on it in the
    // row's own panels (with the screen it is stored on), and what is
    // wrong with it, if anything.
    // { key, kind, layers, ids, offsets, panels, width, placed, custom, problem }
    riggingRow(layer, kind) {
        const k = kind === 'footer' ? 'footer' : 'header';
        const run = this._riggingRunOf(layer, k);
        const placed = [];
        run.layers.forEach((m, i) => {
            this.riggingPlaced(m, k).forEach((b, j) => placed.push({
                start: run.offsets[i] + b.start, size: b.size, owner: m, ownerIndex: j,
            }));
        });
        placed.sort((a, b) => a.start - b.start || run.layers.indexOf(a.owner) - run.layers.indexOf(b.owner));
        placed.forEach((b, i) => { b.runIndex = i; });
        const custom = run.layers.some(m => m.riggingCustom === true);
        const spans = run.offsets.map((o, i) => [o, run.panels[i]]);
        // Every corner along the row, in the row's panels (`spots`), and
        // the pieces laid on them (`pieces`): only on a screen whose own
        // side this row is.
        const spots = [];
        run.layers.forEach((m, i) => {
            if (!this._riggingKindsOf(m).includes(k)) return;
            this.riggingCornerSpots(m).forEach(sp => spots.push({ ...sp, start: run.offsets[i] + sp.start, owner: m }));
        });
        spots.sort((a, b) => a.start - b.start);
        const pieces = spots.filter(sp => sp.bar);
        return {
            key: `${k}:${run.ids.join(',')}`, kind: k, layers: run.layers, ids: run.ids,
            offsets: run.offsets, panels: run.panels, width: run.width, placed, custom, spots, pieces,
            problem: RiggingMath.rowProblem(placed, run.width, spans, custom, pieces),
        };
    }

    // The rows a screen is on, one per side it carries.
    riggingRowsOf(layer) {
        return this._riggingKindsOf(layer).map(kind => this.riggingRow(layer, kind));
    }

    // A row's bars written back to its screens, each on the screen it starts on.
    _riggingWriteRow(row, placed) {
        const parts = RiggingMath.distribute(row, placed);
        row.layers.forEach((m, i) => this._riggingWrite(m, row.kind, parts[i]));
    }

    // A row's name: its screen, or its group when it runs across members.
    _riggingRowName(row) {
        if (row.layers.length > 1) {
            const g = typeof this.getGroupOfLayer === 'function' ? this.getGroupOfLayer(row.layers[0]) : null;
            if (g && g.name) return g.name;
            return listWords(row.layers.map(l => l.name || `Screen ${l.id}`));
        }
        return row.layers[0].name || `Screen ${row.layers[0].id}`;
    }

    // ---- the panel's buttons --------------------------------------------

    toggleRiggingSize(size) {
        if (!RIGGING_SIZES.includes(size)) return;
        // Custom: the one size the next click or drag lays.
        if (this._riggingToolNow() === 'custom') {
            this._riggingCustomSize = size;
            this.refreshRiggingPanel();
            if (window.canvasRenderer) window.canvasRenderer.render();
            return;
        }
        const selected = this._riggingScreens();
        if (selected.length === 0) return;
        const next = new Set(this._riggingSizesOf(this._riggingPrimary(selected)));
        if (next.has(size)) next.delete(size); else next.add(size);
        const sizes = [...next].sort((a, b) => a - b);
        const screens = this._writableLayers(selected);
        if (screens.length) {
            screens.forEach(l => { l.riggingSizes = [...sizes]; });
            // The lit sizes are a curved screen's stock: its curve is laid
            // again from them in the background, and the sizes land with it
            // as one undo step (app-curve.js).
            const later = typeof this.riggingCurveRelayLater === 'function'
                && this.riggingCurveRelayLater(screens, 'Bar Sizes', screens);
            if (!later) this.updateLayers(screens, true, 'Bar Sizes');
        }
        this.refreshRiggingPanel();
    }

    setRiggingTool(tool) {
        const next = tool === 'custom' ? 'custom' : 'auto';
        this._riggingGhost = null;
        if (this.project && this._riggingToolNow() !== next) {
            // Onto the project and every history entry, so no undo or redo
            // brings the other choice back and the next snapshot does not
            // count it as an edit; then to the server, which saves it with
            // the show.
            this.project.riggingTool = next;
            (Array.isArray(this.history) ? this.history : []).forEach(entry => {
                if (entry && entry.project && typeof entry.project === 'object') entry.project.riggingTool = next;
            });
            fetch('/api/project/rigging-tool', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tool: next }),
            }).catch(() => {});
        }
        if (next === 'custom' && !RIGGING_SIZES.includes(this._riggingCustomSize)) {
            // Start on a size the person already lit, the largest.
            const lit = this._riggingSizesOf(this._riggingPrimary());
            this._riggingCustomSize = lit.length ? lit[lit.length - 1] : DEFAULT_CUSTOM_SIZE;
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Header or Footer for the selected screens (and the rest of their
    // groups): each screen's bars move to that side unchanged. A screen
    // with both, from an older show, waits for Keep Header or Keep Footer.
    // One undo step.
    setRiggingSide(side) {
        const kind = side === 'footer' ? 'footer' : 'header';
        this._riggingMode = kind;
        const selected = this._riggingScreens();
        if (selected.length === 0) { this.refreshRiggingPanel(); return; }
        const all = this._riggingWithGroups(selected);
        const both = all.filter(l => this.riggingSideOf(l) === 'both');
        const want = all.filter(l => !['both', kind].includes(this.riggingSideOf(l)));
        if (both.length) this._riggingSayBoth(both);
        const screens = this._writableLayers(want);
        if (screens.length) {
            let moved = false;
            screens.forEach(l => {
                const from = this.riggingSideOf(l);
                const placed = this.riggingPlaced(l, from);
                if (placed.length) moved = true;
                this._riggingWrite(l, from, []);
                this._riggingWrite(l, kind, placed);
            });
            this.updateLayers(screens, true, moved ? `Bars to ${KIND_WORD[kind]}` : `${KIND_WORD[kind]} Side`);
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    _riggingSayBoth(layers) {
        const names = listWords(layers.map(l => l.name || `Screen ${l.id}`));
        const one = layers.length === 1;
        this._toast(`${names} ${one ? 'has' : 'have'} a header and a footer. Pick the side to keep in the box on the left first.`, true, 6000);
    }

    // Keep Header / Keep Footer on a screen an older show left with both:
    // the other row goes. One undo step.
    keepRiggingSide(layerId, side) {
        const kind = side === 'footer' ? 'footer' : 'header';
        const layer = ((this.project && this.project.layers) || []).find(l => l.id === layerId);
        if (!layer || this.riggingSideOf(layer) !== 'both') return;
        if (this._lockedRefused([layer])) return;
        this._riggingWrite(layer, kind === 'header' ? 'footer' : 'header', []);
        layer.riggingSide = kind;
        this.updateLayers([layer], true, `Keep ${KIND_WORD[kind]}`);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Every screen in the show, on every canvas, selected - so one Auto or
    // Clear acts on all of them. (Cmd/Ctrl+A stops at the active canvas.)
    selectAllRiggingScreens() {
        const ids = this._riggingScreensInShow().map(l => l.id);
        if (ids.length === 0) return;
        const primaryId = this.currentLayer && ids.includes(this.currentLayer.id)
            ? this.currentLayer.id : ids[ids.length - 1];
        this.setSelectedLayersByIds(ids, primaryId);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The rows `screens` are on, each once, on each screen's side. A screen
    // with both sides is left out (it waits for Keep Header / Keep Footer)
    // and named. { rows, locked }: a row with a locked screen on it cannot
    // change half way, so it is held whole and its locked screens named.
    _riggingRowsToChange(screens) {
        const all = this._riggingWithGroups(screens);
        const both = all.filter(l => this.riggingSideOf(l) === 'both');
        if (both.length) this._riggingSayBoth(both);
        const rows = [];
        const seen = new Set();
        for (const l of all) {
            if (this.riggingSideOf(l) === 'both') continue;
            const row = this.riggingRow(l, this.riggingSideOf(l));
            if (seen.has(row.key)) continue;
            seen.add(row.key);
            rows.push(row);
        }
        const locked = [];
        const open = rows.filter(row => {
            const held = row.layers.filter(m => this._layerLocked(m));
            held.forEach(m => { if (!locked.includes(m)) locked.push(m); });
            return held.length === 0;
        });
        if (locked.length) this._showLockedError(locked);
        return open;
    }

    // Bars of the lit sizes, end to end across the row: every corner
    // along it takes its piece and each side between them is fitted on
    // its own (RiggingMath.fitAround), so no bar crosses a corner. A row
    // without corners fits exactly as it always did.
    _riggingFitRow(row, sizes) {
        const placed = RiggingMath.fitAround(row.width, sizes, row.spots || []);
        if (!placed) return false;
        this._riggingWriteRow(row, placed);
        row.layers.forEach(m => {
            m.riggingCustom = false;
            const ats = (row.spots || []).filter(sp => sp.owner === m).map(sp => sp.at);
            if (ats.length) this._riggingSetCornerBars(m, ats, true);
        });
        return true;
    }

    applyAutoRigging() {
        const selected = this._riggingScreens();
        if (selected.length === 0) return;
        const misses = [];
        // The sizes lit in the panel are the ones Auto uses, for every
        // selected screen - not each screen's own last pick.
        const sizes = this._riggingSizesOf(this._riggingPrimary(selected));
        const rows = this._riggingRowsToChange(selected);
        if (rows.length === 0) { this.refreshRiggingPanel(); return; }
        const changed = [];
        const curved = [];
        rows.forEach(row => {
            row.layers.forEach(m => { m.riggingSizes = [...sizes]; if (!changed.includes(m)) changed.push(m); });
            // A curved screen's Auto lays its curve again (app-curve.js).
            if (row.layers.length === 1 && typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(row.layers[0])) {
                curved.push(row.layers[0]);
                return;
            }
            // Across the wall as it stands (a wall turned a quarter is its
            // rows wide), and across every member of a group in line with it.
            if (!this._riggingFitRow(row, sizes)) misses.push(this._riggingRowName(row));
        });
        const kinds = new Set(rows.map(r => r.kind));
        const action = kinds.size === 1 ? `Auto ${KIND_WORD[rows[0].kind]} Bars` : 'Auto Bars';
        // With a curved screen among them, everything lands as one step
        // once its curve is worked out (app-curve.js).
        if (curved.length && this.riggingCurveRelayLater(curved, action, changed, { misses })) {
            this.refreshRiggingPanel();
            return;
        }
        this.updateLayers(changed, true, action);
        this.refreshRiggingPanel(misses);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The warning box's Auto: every row that no longer fits, fitted again
    // with its first screen's own lit sizes, whatever is selected. One undo
    // step.
    fitMisfitRigging() {
        const misfits = this.riggingShownMisfits();
        if (misfits.length === 0) return;
        const misses = [];
        const changed = [];
        const locked = [];
        const curved = [];
        misfits.forEach(m => {
            const row = this.riggingRow(m.layers[0], m.kind);
            const held = row.layers.filter(l => this._layerLocked(l));
            if (held.length) { held.forEach(l => { if (!locked.includes(l)) locked.push(l); }); return; }
            if (row.layers.length === 1 && typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(row.layers[0])) {
                curved.push(row.layers[0]);
                return;
            }
            if (!this._riggingFitRow(row, this._riggingSizesOf(row.layers[0]))) {
                misses.push(this._riggingRowName(row));
                return;
            }
            row.layers.forEach(l => { if (!changed.includes(l)) changed.push(l); });
        });
        if (locked.length) this._showLockedError(locked);
        if (curved.length && this.riggingCurveRelayLater(curved, 'Auto Bars', changed, { misses })) {
            this.refreshRiggingPanel();
            return;
        }
        if (changed.length) this.updateLayers(changed, true, 'Auto Bars');
        this.refreshRiggingPanel(misses);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Clear: every bar on the selected screens (and the rest of their
    // groups), whichever side.
    clearRiggingBars() {
        const withBars = this._riggingWithGroups(this._riggingScreens())
            .filter(l => KINDS.some(k => this.riggingBarsOf(l, k).length) || this.riggingCornerPiecesOf(l).length);
        if (withBars.length === 0) return;
        const screens = this._writableLayers(withBars);
        if (screens.length === 0) return;
        const kinds = new Set();
        screens.forEach(l => {
            const side = this.riggingSideOf(l);
            KINDS.forEach(k => {
                if (this.riggingBarsOf(l, k).length) kinds.add(k);
                this._riggingWrite(l, k, []);
            });
            l.riggingSide = side === 'footer' ? 'footer' : 'header';
            l.riggingCustom = false;
            // The corner pieces come off with the bars.
            const laid = s3dCleanCorners(l.riggingCorners).filter(c => c.bar).map(c => c.at);
            if (laid.length) {
                this._riggingSetCornerBars(l, laid, false);
                kinds.add(side === 'footer' ? 'footer' : 'header');
            }
            // A curve with its bars taken off is a curve no more: Clear
            // turns it off and the joints go back to flat (app-curve.js).
            if (typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(l)) {
                l.riggingCurve = { ...this.riggingCurveOf(l), on: false };
                this._curveUnlay(l);
            }
        });
        const word = kinds.size === 1 ? `${KIND_WORD[[...kinds][0]]} ` : '';
        this.updateLayers(screens, true, `Clear ${word}Bars`);
        this._riggingPicked = null;
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // ---- the canvas gestures (canvas-input.js) ----------------------------
    //
    // Every gesture works on a ROW: it starts with riggingBeginDrag (the
    // row's lock is checked and its fields kept), writes the row live as
    // the mouse moves, and ends with riggingEndDrag, which saves the row as
    // one undo step or puts it back exactly as it was.

    _riggingFieldsOf(layers) {
        return layers.map(l => ({
            l, side: l.riggingSide, custom: l.riggingCustom, corners: l.riggingCorners,
            f: KINDS.map(k => [l[BAR_FIELD[k]], l[START_FIELD[k]]]),
        }));
    }

    riggingBeginDrag(layer, kind) {
        if (!layer) return null;
        const row = this.riggingRow(layer, kind);
        const locked = row.layers.filter(l => this._layerLocked(l));
        if (locked.length) { this._showLockedError(locked); return null; }
        // A curved screen's bars are the Curve's (app-curve.js).
        if (typeof this.riggingCurveRefusesHand === 'function' && this.riggingCurveRefusesHand(row.layers)) return null;
        // Pressing on one member presses on its group: the side and the
        // rows are the group's.
        const ids = this._riggingWithGroups([layer]).map(l => l.id);
        if (!ids.every(id => this.selectedLayerIds && this.selectedLayerIds.has(id))) {
            this.setSelectedLayersByIds(ids, layer.id);
        }
        const original = plain(row.placed);
        return { layerId: layer.id, row: row.kind, rowObj: row, original, placed: original,
                 kept: this._riggingFieldsOf(row.layers), cornersWere: this._riggingCornerSig(row.layers) };
    }

    // Custom: a press on the panel `localPanel` of `layer` along its bar
    // edge. Lays one bar of the picked size there at once (the drag that
    // follows stretches it into a row of them).
    riggingBeginPlace(layer, kind, localPanel) {
        if (kind === 'both') { this._riggingSayBoth([layer]); return null; }
        const d = this.riggingBeginDrag(layer, kind);
        if (!d) return null;
        const row = d.rowObj;
        d.kind = 'place';
        d.size = this.riggingCustomSize();
        d.from = row.offsets[row.layers.indexOf(layer)] + localPanel;
        row.layers.forEach(l => { l.riggingCustom = true; });
        this.riggingPreviewPlace(d, d.from);
        return d;
    }

    // The laid corner pieces of `layers`, for telling a gesture changed them.
    _riggingCornerSig(layers) {
        return JSON.stringify((layers || []).map(l => s3dCleanCorners(l.riggingCorners).filter(c => c.bar).map(c => c.at)));
    }

    // What a Custom click or drag from row panel `from` to `to` lays:
    // bars of `size` on each side of any corner, and the pieces of the
    // corners it covers (RiggingMath.layAround). { adds, spots }.
    riggingCustomLay(row, from, to, size) {
        const spots = row.spots || [];
        const lay = RiggingMath.layAround(from, to, size, row.width, spots);
        return { adds: lay.adds, spots: lay.corners.map(i => spots[i]) };
    }

    riggingPreviewPlace(d, runPanel) {
        const row = d.rowObj;
        const lay = this.riggingCustomLay(row, d.from, runPanel, d.size);
        d.adds = lay.adds;
        d.refused = !lay.adds.length && !lay.spots.length;
        d.cornerAdds = lay.spots.map(sp => sp.at);
        // A bar on a corner's panels makes way for the corner's piece.
        const pieces = lay.spots;
        const kept = pieces.length
            ? d.original.filter(b => !pieces.some(p => b.start < p.start + p.size && p.start < b.start + b.size))
            : d.original;
        d.placed = RiggingMath.placeBars(kept, d.adds);
        // The corners as the press found them, then the pieces this lays.
        d.kept.forEach(({ l, corners }) => {
            if (corners === undefined) delete l.riggingCorners;
            else l.riggingCorners = corners;
        });
        row.layers.forEach(m => {
            const ats = pieces.filter(p => p.owner === m).map(p => p.at);
            if (ats.length) this._riggingSetCornerBars(m, ats, true);
        });
        this._riggingWriteRow(row, d.placed);
    }

    riggingPreviewEdge(d, panels) {
        d.placed = RiggingMath.resizeEdgeAt(d.original, d.boundary, panels);
        this._riggingWriteRow(d.rowObj, d.placed);
    }

    riggingPreviewMove(d, panels) {
        const moved = RiggingMath.moveInBlock(d.original, d.index, panels);
        d.placed = moved.placed;
        d.current = moved.index;
        this._riggingWriteRow(d.rowObj, d.placed);
    }

    _riggingPutBack(kept) {
        kept.forEach(({ l, side, custom, corners, f }) => {
            KINDS.forEach((k, i) => { l[BAR_FIELD[k]] = f[i][0]; l[START_FIELD[k]] = f[i][1]; });
            l.riggingSide = side;
            l.riggingCustom = custom;
            if (corners === undefined) delete l.riggingCorners;
            else l.riggingCorners = corners;
        });
    }

    // The gesture let go: saved as one undo step when it changed the row
    // (and `keep`), put back exactly as it was otherwise.
    riggingEndDrag(d, keep = true) {
        const cornersMoved = d.cornersWere !== undefined && this._riggingCornerSig(d.rowObj.layers) !== d.cornersWere;
        const changed = JSON.stringify(plain(d.placed)) !== JSON.stringify(d.original) || cornersMoved;
        const word = KIND_WORD[d.row];
        // A click whose bar fits nowhere on its side of a corner says so.
        if (keep && !changed && d.kind === 'place' && d.refused) {
            this._toast(`A ${RiggingMath.sizeWord(d.size).toLowerCase()} does not fit between this corner and the next corner or edge. Pick a smaller size.`, true, 5000);
        }
        if (keep && changed) {
            const n = (d.adds || []).length + (cornersMoved ? 1 : 0);
            const action = d.kind === 'place' ? `Add ${word} Bar${n > 1 ? 's' : ''}`
                : d.kind === 'edge' ? `Resize ${word} Bar` : `Move ${word} Bar`;
            this.updateLayers(d.rowObj.layers, true, action);
        } else {
            this._riggingPutBack(d.kept);
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
        return keep && changed;
    }

    // A click on a bar picks it: drawn lit, and Delete (or the right-click
    // menu's Remove Bar) takes it off.
    pickRiggingBar(hit) {
        this._riggingPicked = hit ? { layerId: hit.layerId, kind: hit.row === 'footer' ? 'footer' : 'header',
                                      start: hit.start, corner: hit.corner == null ? null : hit.corner } : null;
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Delete or Backspace on this tab (canvas-input.js; Matt, 2026-11-08):
    // the picked bar goes; with none picked, the selected screens' bars go,
    // as Clear takes them (both rows on an older show's screen with both),
    // one undo step, a locked screen named and left as it is. Never a
    // screen.
    riggingDeleteKey() {
        if (this._riggingPicked) return this.removePickedRiggingBar();
        this.clearRiggingBars();
        return true;
    }

    removePickedRiggingBar() {
        const p = this._riggingPicked;
        this._riggingPicked = null;
        const layer = p && ((this.project && this.project.layers) || []).find(l => l.id === p.layerId);
        if (!layer) return false;
        const row = this.riggingRow(layer, p.kind);
        const locked = row.layers.filter(l => this._layerLocked(l));
        if (locked.length) { this._showLockedError(locked); return false; }
        if (typeof this.riggingCurveRefusesHand === 'function' && this.riggingCurveRefusesHand(row.layers)) return false;
        if (p.corner != null) {
            // A corner piece: off its corner, its panels left open.
            if (!this._riggingSetCornerBars(layer, [p.corner], false)) return false;
            row.layers.forEach(l => { l.riggingCustom = true; });
            this.updateLayers(row.layers, true, `Remove ${KIND_WORD[row.kind]} Bar`);
            this.refreshRiggingPanel();
            if (window.canvasRenderer) window.canvasRenderer.render();
            return true;
        }
        const at = row.offsets[row.layers.indexOf(layer)] + p.start;
        const rest = row.placed.filter(b => !(b.owner === layer && b.start === at));
        if (rest.length === row.placed.length) return false;
        this._riggingWriteRow(row, plain(rest));
        // A row with a bar taken out has a gap: it is a custom row now.
        row.layers.forEach(l => { l.riggingCustom = true; });
        this.updateLayers(row.layers, true, `Remove ${KIND_WORD[row.kind]} Bar`);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // Right-click on a bar in this view: "Remove Bar" (app-context-menu.js).
    _prepareRiggingBarMenu(x, y) {
        const r = window.canvasRenderer;
        if (!r || r.viewMode !== 'rigging' || !r.canvas || typeof r.riggingBarAt !== 'function') return null;
        if (document.elementFromPoint(x, y) !== r.canvas) return null;
        const rect = r.canvas.getBoundingClientRect();
        const hit = r.riggingBarAt(x - rect.left, y - rect.top);
        if (!hit) return null;
        this.pickRiggingBar(hit);
        return { label: 'Remove Bar', title: hit.corner != null ? 'Take this corner bar off'
            : `Take this ${RiggingMath.sizeWord(hit.span).toLowerCase()} bar off` };
    }

    // ---- the panel --------------------------------------------------------

    // Redraws the panel from the current screen. `misses` names rows the
    // last Auto could not fit with the lit sizes.
    refreshRiggingPanel(misses) {
        const picker = document.getElementById('rigging-size-picker');
        if (!picker) return;
        this.refreshRiggingTotals();
        const screens = this._riggingScreens();
        const primary = this._riggingPrimary(screens);
        const side = primary ? this.riggingSideOf(primary) : (this._riggingMode === 'footer' ? 'footer' : 'header');
        const tool = this._riggingToolNow();
        const sizes = this._riggingSizesOf(primary);
        const lit = tool === 'custom' ? [this.riggingCustomSize()] : sizes;

        document.querySelectorAll('#rigging-mode-picker .rigging-mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === side);
        });
        document.querySelectorAll('#rigging-tool-picker .rigging-tool-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tool === tool);
        });
        picker.querySelectorAll('.rigging-size-btn[data-size]').forEach(btn => {
            btn.classList.toggle('active', lit.includes(parseInt(btn.dataset.size, 10)));
        });
        const sizeLabel = document.getElementById('rigging-size-label');
        if (sizeLabel) sizeLabel.textContent = tool === 'custom' ? 'Size to lay' : 'Sizes Auto uses';
        // 3 and 4 show once the + is open, or at once when one of them is lit
        // (a lit size is never hidden).
        const extra = document.getElementById('rigging-size-extra');
        const more = document.getElementById('rigging-size-more');
        const open = !!this._riggingMoreOpen || lit.some(s => s >= 3);
        if (extra) extra.style.display = open ? 'flex' : 'none';
        if (more) {
            more.textContent = open ? '−' : '+';
            more.classList.toggle('active', open);
            more.setAttribute('aria-expanded', open ? 'true' : 'false');
        }

        const colorEl = document.getElementById('rigging-color');
        const colorHex = document.getElementById('rigging-color-hex');
        const color = (primary && primary.riggingColor) || DEFAULT_BAR_COLOR;
        if (colorEl) colorEl.value = color.toLowerCase();
        if (colorHex) colorHex.value = color.toUpperCase();
        const textEl = document.getElementById('rigging-text-color');
        const textHex = document.getElementById('rigging-text-color-hex');
        const textColor = (primary && primary.riggingTextColor) || DEFAULT_TEXT_COLOR;
        if (textEl) textEl.value = textColor.toLowerCase();
        if (textHex) textHex.value = textColor.toUpperCase();

        const auto = document.getElementById('rigging-auto-btn');
        const clear = document.getElementById('rigging-clear-btn');
        const hint = document.getElementById('rigging-custom-hint');
        if (auto) {
            auto.disabled = screens.length === 0 || sizes.length === 0;
            auto.style.display = tool === 'custom' ? 'none' : '';
        }
        if (hint) {
            hint.style.display = tool === 'custom' ? '' : 'none';
            const where = side === 'footer' ? 'below' : 'above';
            hint.textContent = `Click in the bar strip ${where} a wall to drop a ${RiggingMath.sizeWord(this.riggingCustomSize()).toLowerCase()}, or drag along it to lay a row. Click a bar and press Delete to take it off.`;
        }
        if (clear) clear.disabled = !this._riggingWithGroups(screens).some(l => KINDS.some(k => this.riggingBarsOf(l, k).length)
            || this.riggingCornerPiecesOf(l).length);
        if (typeof this.refreshRiggingCurve === 'function') this.refreshRiggingCurve();
        if (typeof this.refreshRiggingCorners === 'function') this.refreshRiggingCorners();

        const status = document.getElementById('rigging-status');
        if (!status) return;
        // Blank unless the last Auto could not make a row's width: the
        // panel shows the totals and nothing else.
        status.textContent = misses && misses.length
            ? `No exact fit with these sizes: ${misses.join(', ')}` : '';
    }

    // Every screen in the show, for Select All Screens.
    _riggingScreensInShow() {
        const layers = (this.project && this.project.layers) || [];
        return layers.filter(l => (l.type || 'screen') === 'screen');
    }

    // The wall's real width in panels: what an Auto row has to cover.
    riggingWallPanels(layer) {
        return layer ? RiggingMath.wallPanels(layer.columns, layer.rows, layer.rotation) : 0;
    }

    // ---- bars that no longer fit -----------------------------------------

    _riggingMisfitOf(row) {
        const p = row.problem;
        const first = (row.placed[0] && row.placed[0].owner) || row.layers[0];
        return { layer: first, layers: row.layers, key: row.key, kind: row.kind, word: KIND_WORD[row.kind],
                 have: p.have, wall: p.wall, past: p.past, problem: p, name: this._riggingRowName(row) };
    }

    // The rows a screen is on that no longer fit:
    // [{ layer, layers, key, kind, word, have, wall, past, problem, name }].
    riggingMisfits(layer) {
        return this.riggingRowsOf(layer).filter(r => r.problem).map(r => this._riggingMisfitOf(r));
    }

    // The same across the show, each row once: the screens the pull list
    // counts, so a hidden screen, which does not count, does not warn.
    riggingShownMisfits() {
        const seen = new Set();
        const out = [];
        for (const l of this._pullScreens()) {
            for (const m of this.riggingMisfits(l)) {
                if (seen.has(m.key)) continue;
                seen.add(m.key);
                out.push(m);
            }
        }
        return out;
    }

    // "Main Wall: header bars cover 12 panels, the wall is 16."
    riggingMisfitLine(m, named = true) {
        const p = m.problem || { have: m.have, wall: m.wall };
        let said;
        if (p.corner) {
            said = `${m.word} bars cross a corner, where the corner bar goes.`;
        } else if (p.custom) {
            said = p.past ? `${m.word} bars run ${p.past} panel${p.past === 1 ? '' : 's'} past the wall's edge.`
                : `${m.word} bars overlap.`;
        } else if (p.have !== p.wall) {
            said = `${m.word} bars cover ${p.have} panels, the wall is ${p.wall}.`;
        } else {
            said = p.overlap ? `${m.word} bars overlap.` : `${m.word} bars leave a gap.`;
        }
        const name = m.name || (m.layer && m.layer.name) || '';
        return named ? `${name}: ${said.charAt(0).toLowerCase()}${said.slice(1)}` : said;
    }

    // One message for the toast and the exports, '' when every row fits.
    riggingFitWarning(misfits = this.riggingShownMisfits()) {
        if (!misfits.length) return '';
        const lines = misfits.slice(0, 4).map(m => this.riggingMisfitLine(m));
        if (misfits.length > 4) lines.push(`And ${misfits.length - 4} more.`);
        return `Header/Footer bars no longer fit. ${lines.join(' ')} Press Auto on the Header/Footer tab to fit them.`;
    }

    // After a commit (updateLayers): says so once when the edit left a row
    // of bars that no longer fits on a screen it touched, and redraws the
    // tab's box. A row that was already wrong says nothing new.
    riggingFitCheck(layers) {
        const misfits = this.riggingShownMisfits();
        const key = (m) => `${m.key}:${m.have}:${m.wall}:${m.past}`;
        const said = this._riggingFitSaid || new Set();
        const touched = new Set((layers || []).map(l => l.id));
        const fresh = misfits.filter(m => m.layers.some(l => touched.has(l.id)) && !said.has(key(m)));
        this._riggingFitSaid = new Set(misfits.map(key));
        if (fresh.length && typeof this._toast === 'function') {
            this._toast(this.riggingFitWarning(fresh), true, 8000);
        }
        this.refreshRiggingTotals();
    }

    // The screens on show an older file left with a header AND a footer.
    riggingBothScreens() {
        return this._pullScreens().filter(l => this.riggingSideOf(l) === 'both');
    }

    // The tab's warning box: the rows that no longer fit, with Auto for
    // them, and the screens with both a header and a footer, with Keep
    // Header and Keep Footer for each.
    _refreshRiggingFitBox() {
        const box = document.getElementById('rigging-fit-warning');
        const text = document.getElementById('rigging-fit-text');
        if (!box || !text) return;
        const misfits = this.riggingShownMisfits();
        const both = this.riggingBothScreens();
        box.style.display = misfits.length || both.length ? '' : 'none';
        const fitPart = document.getElementById('rigging-fit-section');
        if (fitPart) fitPart.style.display = misfits.length ? '' : 'none';
        const lines = misfits.slice(0, 6).map(m => this.riggingMisfitLine(m));
        if (misfits.length > 6) lines.push(`And ${misfits.length - 6} more.`);
        text.textContent = lines.join('\n');
        const bothPart = document.getElementById('rigging-both-section');
        const list = document.getElementById('rigging-both-list');
        if (bothPart) bothPart.style.display = both.length ? '' : 'none';
        if (list) {
            const sig = JSON.stringify(both.map(l => [l.id, l.name]));
            if (list.dataset.sig !== sig) {
                list.dataset.sig = sig;
                list.innerHTML = '';
                both.forEach(l => {
                    // One line per screen at any sidebar width: the name,
                    // then the two sides to keep, one word each (the box
                    // already says "Pick the side to keep").
                    const rowEl = document.createElement('div');
                    rowEl.className = 'rigging-both-row';
                    rowEl.style.cssText = 'margin-top: 6px;';
                    const name = document.createElement('div');
                    name.textContent = l.name || `Screen ${l.id}`;
                    name.style.cssText = 'margin-bottom: 3px; color: #ddd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
                    const btns = document.createElement('div');
                    btns.style.cssText = 'display: flex; gap: 4px;';
                    for (const k of KINDS) {
                        const b = document.createElement('button');
                        b.type = 'button';
                        b.className = 'btn btn-secondary';
                        // The theme's button padding and size win over a
                        // plain inline style; these two must not, or the
                        // word does not fit the narrowest sidebar.
                        b.style.cssText = 'flex: 1 1 0; min-width: 0; white-space: nowrap; overflow: hidden;';
                        b.style.setProperty('padding', '3px 2px', 'important');
                        b.style.setProperty('font-size', '11px', 'important');
                        b.dataset.layerId = String(l.id);
                        b.dataset.keep = k;
                        b.textContent = KIND_WORD[k];
                        b.setAttribute('data-tooltip', `Keep ${KIND_WORD[k]}, keep this screen's ${k} bars and take its ${k === 'header' ? 'footer' : 'header'} bars off. A screen has bars on one side.`);
                        btns.appendChild(b);
                    }
                    rowEl.append(name, btns);
                    list.appendChild(rowEl);
                });
            }
        }
    }

    refreshRiggingTotals() {
        this._refreshRiggingFitBox();
        // The pull list's screens: hidden doesn't count (owner, 2026-11-06),
        // so the box and the pull list can never disagree. A bar across a
        // group's seam is stored on one member, so it is counted once.
        const screens = this._pullScreens();
        const fill = (kind, countId, listId) => {
            const count = document.getElementById(countId);
            const list = document.getElementById(listId);
            if (!count || !list) return;
            const { total, bySize } = RiggingMath.tally(screens.map(l => this.riggingBarsOf(l, kind)));
            const corners = this.riggingCornersBySize(screens, kind);
            const pieces = Object.values(corners).reduce((t, n) => t + n, 0);
            count.textContent = String(total + pieces);
            const lines = Object.keys(bySize).map(Number).sort((a, b) => b - a)
                .map(size => `${RiggingMath.sizeWord(size)}: ${bySize[size]}`);
            // each corner part its own line, 1 panel before 2
            Object.keys(corners).map(Number).sort((a, b) => a - b)
                .forEach(size => lines.push(`${RiggingMath.cornerWord(size)}: ${corners[size]}`));
            list.textContent = lines.join('\n');
        };
        fill('header', 'rigging-total-count', 'rigging-total-breakdown');
        fill('footer', 'rigging-footer-total-count', 'rigging-footer-total-breakdown');
    }

    // How many corner pieces `layers` carry on their `kind` side, each
    // counted on the screen whose corner it is.
    riggingCornerCount(layers, kind) {
        return Object.values(this.riggingCornersBySize(layers, kind)).reduce((t, n) => t + n, 0);
    }

    // The same by part, the panels each covers: { 1: n, 2: n }. A 1 panel
    // and a 2 panel corner bar are different parts (owner, 2026-11-10).
    riggingCornersBySize(layers, kind) {
        const by = {};
        for (const l of layers || []) {
            if (!this._riggingKindsOf(l).includes(kind)) continue;
            for (const pc of this.riggingCornerPiecesOf(l)) by[pc.size] = (by[pc.size] || 0) + 1;
        }
        return by;
    }

    // ---- the binder's Screens sheets --------------------------------------

    // The bars a screen's own sheet shows on one side: every bar of its row
    // over this screen, its own and a neighbor's that reaches across the
    // seam, in this screen's panels; `shared` marks one that crosses a seam.
    // [{ start, size, own, shared, owner }]
    riggingSliceOf(layer, kind) {
        const row = this.riggingRow(layer, kind);
        const k = row.layers.indexOf(layer);
        const o = row.offsets[k], n = row.panels[k];
        return row.placed
            .filter(b => b.owner === layer || (b.start < o + n && b.start + b.size > o))
            .map(b => ({ start: b.start - o, size: b.size, own: b.owner === layer, owner: b.owner,
                         shared: row.layers.length > 1 && ((k > 0 && b.start < o) || (k < row.layers.length - 1 && b.start + b.size > o + n)) }))
            // its corner pieces, which never leave it
            .concat((row.pieces || []).filter(p => p.owner === layer)
                .map(p => ({ start: p.start - o, size: p.size, own: true, owner: layer, shared: false, corner: p.at })));
    }

    // The bars across a seam that touch `layer`, for its sheet's note:
    // [{ kind, size, from, to }] ("a double runs from WALL-L onto WALL-R").
    riggingSharedBarsOf(layer) {
        const out = [];
        for (const kind of this._riggingKindsOf(layer)) {
            const row = this.riggingRow(layer, kind);
            if (row.layers.length < 2) continue;
            for (const b of row.placed) {
                const end = b.start + b.size;
                const on = row.layers.filter((m, i) => b.start < row.offsets[i] + row.panels[i] && end > row.offsets[i]);
                if (on.length > 1 && on.includes(layer)) out.push({ kind, size: b.size, from: on[0], to: on[on.length - 1], owner: b.owner });
            }
        }
        return out;
    }

    // ---- copies --------------------------------------------------------------

    // The bar fields a copy of `layer` alone gets (Copy, Duplicate; Paste
    // takes the copy's: app-clipboard.js), or null when the screen's own
    // fields will do. A copy stands alone, out of the group, so of a row
    // that crosses a seam it keeps the bars over this screen, each cut at
    // its edges: the bar straddling the seam becomes the part of it over
    // this screen, a neighbor's bar reaching onto it included, so the copy
    // is covered edge to edge exactly as the screen is and nothing runs
    // past its edge (owner, 2026-11-08). Every other bar is kept as it is
    // (copies keep their bars, 2026-11-06).
    riggingCopyFields(layer) {
        const layers = (this.project && this.project.layers) || [];
        if (!layer || !layers.includes(layer) || (layer.type || 'screen') !== 'screen') return null;
        let out = null;
        for (const kind of this._riggingKindsOf(layer)) {
            const row = this.riggingRow(layer, kind);
            if (row.layers.length < 2) continue;
            const k = row.layers.indexOf(layer);
            const { bars, starts } = RiggingMath.storeOf(RiggingMath.clipTo(row.placed, row.offsets[k], row.panels[k]));
            out = out || {};
            out[BAR_FIELD[kind]] = bars;
            out[START_FIELD[kind]] = starts;
        }
        return out;
    }

    // ---- the 3D stage ---------------------------------------------------------

    // The bars that stand over a screen on the 3D stage (app-stage3d.js
    // s3dBarRows), one entry per side it carries: the bars of its row over
    // it, a shown neighbor's across a seam too, in its own panels.
    // [{ row, bars: [{ start, size }], end, fits }]; `end` when the screen
    // is the last of its row, so a bar past the row's end stands past its
    // last column.
    riggingStageSlices(layer) {
        return this.riggingRowsOf(layer).map(row => {
            const k = row.layers.indexOf(layer);
            const o = row.offsets[k], n = row.panels[k];
            const end = k === row.layers.length - 1;
            const bars = row.placed
                .filter(b => (b.owner === layer || b.owner.visible !== false)
                    && ((b.start < o + n && b.start + b.size > o) || (end && b.start >= o + n)))
                .map(b => ({ start: b.start - o, size: b.size }))
                // its corner pieces, folded with the panels (s3dBarRows)
                .concat((row.pieces || []).filter(p => p.owner === layer)
                    .map(p => ({ start: p.start - o, size: p.size, corner: true })))
                .sort((a, b) => a.start - b.start);
            return { row: row.kind, bars, end, fits: !row.problem };
        }).filter(s => s.bars.length);
    }

    // ---- the pull list ------------------------------------------------------

    // One pull-list row per bar size and row (header or footer) on a screen:
    // the screen's own line in its position, merged into the show totals
    // like any other gear. `side: 'rigging'` keeps it off the Power and Data
    // cable lists (the binder's pull sheet prints it under its own Header
    // bars and Footer bars tables). A bar across a group's seam is listed on
    // the screen it starts on, once. A row of bars that no longer fits keeps
    // its quantities, marked on the label every table prints and with the
    // figures in the notes, so what it asks for is never taken as right.
    riggingPullRows(layer) {
        const rows = [];
        const name = (layer && layer.name) || '';
        const misfits = this.riggingMisfits(layer);
        for (const kind of KINDS) {
            const miss = misfits.find(m => m.kind === kind);
            const bySize = RiggingMath.tally([this.riggingBarsOf(layer, kind)]).bySize;
            const corners = this.riggingCornersBySize([layer], kind);
            const parts = Object.keys(bySize).map(Number).sort((a, b) => b - a)
                .map(size => [RiggingMath.barName(size, kind), bySize[size]]);
            // each corner part its own line, 1 panel before 2
            Object.keys(corners).map(Number).sort((a, b) => a - b)
                .forEach(size => parts.push([RiggingMath.cornerName(size, kind), corners[size]]));
            parts.forEach(([type, qty]) => rows.push({
                type, length: 'EA', qty,
                label: miss ? `${name} (bars no longer fit)` : name,
                notes: miss ? `${this.riggingMisfitLine(miss, false)} Press Auto on the Header/Footer tab.` : '',
                side: 'rigging',
            }));
        }
        return rows;
    }
}

for (const k of Object.getOwnPropertyNames(_Rigging.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Rigging.prototype, k));
    }
}
