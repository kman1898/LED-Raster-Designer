// app-power: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// Float sums of derated watts land a hair over an exact multiple; a circuit
// that is precisely full is full, not over. See customRunCapacity.
const CUSTOM_RUN_EPS = 1e-6;

class _Power {

    // The soca / splitter / distro panels build their markup as strings and
    // drop it in with innerHTML, interpolating user text - screen names,
    // soca names, distro names. Every one of those sites calls _esc. It has
    // to exist: without it a screen named "Main & FOH" renders wrong, and a
    // name containing a tag injects live DOM into the sidebar.
    // _escapeAttr (app-canvas-ui.js) is this app's one escaping helper;
    // _esc is the name the panel builders ask for, so point it there rather
    // than growing a second, drifting implementation.
    _esc(s) {
        return this._escapeAttr(s);
    }

    showContextMenu(x, y) {
        const menu = document.getElementById('context-menu');
        if (!menu) return;
        // The SURFACE under the cursor is decided before any item is: the
        // hardware dock is hardware, not layers, so a chip right-clicked
        // there gets that chip's own action and nothing else - "Delete
        // Layer" next to "Clear port 3" reads as an offer to delete the
        // chip. And a tray spot with no chip under it has no actions at
        // all, so no menu opens: an empty menu teaches nothing.
        const under = document.elementFromPoint(x, y);
        const inDock = !!(under && under.closest
            && under.closest('#hardware-dock'));
        // Assignment clears: armed only when the right-click landed on a
        // drawn port run, a power circuit, or a dock chip (app-dock.js
        // _prepareClearMenu). The label and the title are written at open
        // time because they name the thing under the cursor; an impossible
        // clear stays on the menu, disabled, with the reason as its title.
        const clear = (typeof this._prepareClearMenu === 'function')
            ? this._prepareClearMenu(x, y) : null;
        this._clearMenuAction = clear;
        // The way back from a drop-implied split, offered only where a
        // stored boundary exists (app-dock.js _prepareMergeMenu): unlike the
        // clear there is no disabled state, because "nothing to merge" is
        // the ordinary condition of most multis, not a refused gesture.
        const merge = (typeof this._prepareMergeMenu === 'function')
            ? this._prepareMergeMenu(x, y) : null;
        this._mergeMenuAction = merge;
        // Circuit sharing (the retired Splitters panel's manual lever):
        // armed only on a power circuit run or chip, and only while the
        // screen's splitters are on or its circuits are drawn custom
        // (app-dock.js _prepareShareMenus). Absent everywhere else.
        const sharing = (typeof this._prepareShareMenus === 'function')
            ? this._prepareShareMenus(x, y) : { share: null, unshare: null };
        this._shareMenuAction = sharing.share;
        this._unshareMenuAction = sharing.unshare;
        // The batch verb (2026-08-30, "B and then right click"): with a
        // sweep selection armed the menu deals it as Nfers; with none, the
        // same entries act on the whole screen under the cursor. Canvas
        // power view only - a dock chip is hardware, not a run.
        const batch = (typeof this._prepareBatchMenu === 'function')
            ? this._prepareBatchMenu(x, y) : null;
        this._batchMenuActions = batch;
        // Per-run override: armed only on a drawn run in Data Flow / Power,
        // and never on the dock (a chip is hardware, not a run). "Back to
        // auto" appears only where an override exists to drop - the same
        // only-what-applies rule the clears follow.
        const ovr = (!inDock && typeof this._prepareOverrideMenu === 'function')
            ? this._prepareOverrideMenu(x, y) : null;
        this._overrideMenuActions = ovr;
        // Distro outputs, the click path (2026-08-31): on a screen in the
        // power view - its cabinets, or its circuit chips in the tray -
        // "Add <type> from…" opens a submenu of every distro, the ones
        // offering the screen's connector with their load, the rest greyed
        // with the reason (app-dock.js _prepareOutputsMenu).
        const outs = (typeof this._prepareOutputsMenu === 'function')
            ? this._prepareOutputsMenu(x, y) : null;
        this._outputsMenuActions = outs;
        // Data snakes (2026-09-06, "B to form it"): on a lit port chip
        // the sweep gathered, on a snake's tag, or on a chip riding a
        // snake - "Snake these N", "Set home run…", "Loosen", "Rename"
        // (app-dock.js _prepareSnakeMenu). Tray only; absent elsewhere.
        const snake = (typeof this._prepareSnakeMenu === 'function')
            ? this._prepareSnakeMenu(x, y) : null;
        this._snakeMenuActions = snake;
        // "Export this screen..." (app-binder.js): the screen under the
        // cursor on the canvas, else the selected screen; never on the dock.
        this._binderMenuLayer = (!inDock && typeof this._prepareBinderMenu === 'function')
            ? this._prepareBinderMenu(x, y) : null;
        if (inDock && !clear && !merge && !sharing.share
                && !sharing.unshare && !outs && !snake) {
            this.hideContextMenu();
            return;
        }
        // The layer/canvas items belong to the canvas surface only. On the
        // dock they all leave, whatever their group logic below would say.
        menu.querySelectorAll(
            '.menu-option:not(.hw-clear-only):not(.hw-merge-only)'
            + ':not(.hw-share-only):not(.hw-unshare-only)'
            + ':not(.hw-batch-only):not(.hw-out-only):not(.hw-snake-only), '
            + '.menu-divider:not(.hw-clear-only):not(.hw-batch-only)'
            + ':not(.hw-out-only):not(.hw-snake-only)')
            .forEach(el => {
                el.style.display = inDock ? 'none' : '';
            });
        if (!inDock) {
            // Show/hide pixel-map-only menu group based on view + selection.
            const inPixelMap = window.canvasRenderer && window.canvasRenderer.viewMode === 'pixel-map';
            const haveSelection = this.pixelMapSelection && this.pixelMapSelection.size > 0;
            const showPixelMapItems = inPixelMap && haveSelection;
            menu.querySelectorAll('.pixel-map-only').forEach(el => {
                el.style.display = showPixelMapItems ? '' : 'none';
            });
            // Centering only applies where screens can actually be
            // positioned: Pixel Map (processor offset) and Show Look (show
            // offset). Data and Power mirror the Show Look position, so
            // they're read-only there.
            const canCenter = window.canvasRenderer
                && ['pixel-map', 'show-look'].includes(window.canvasRenderer.viewMode)
                && this.getSelectedLayers().some(l => !l.locked);
            menu.querySelectorAll('.movable-view-only').forEach(el => {
                el.style.display = canCenter ? '' : 'none';
            });
            menu.querySelectorAll('.screen-export-only').forEach(el => {
                el.style.display = this._binderMenuLayer ? '' : 'none';
            });
            // v0.11.0: screen-group actions. Grouping needs 2+ screen
            // layers selected, so with fewer the item is simply not offered
            // (a group of one is not a group). Ungroup / Remove only mean
            // anything once the selection is already in a group.
            const canGroup = this.canGroupSelection();
            const inGroup = this.getSelectedGroupIds().length > 0;
            menu.querySelectorAll('.group-create-only').forEach(el => {
                el.style.display = canGroup ? '' : 'none';
            });
            menu.querySelectorAll('.group-member-only').forEach(el => {
                el.style.display = inGroup ? '' : 'none';
            });
            menu.querySelectorAll('.group-any-only').forEach(el => {
                el.style.display = (canGroup || inGroup) ? '' : 'none';
            });
            // Move to Canvas needs a layer to move and somewhere to move it
            // to. Offering it with one canvas would open a picker with
            // nothing in it.
            const canvases = (this.project && this.project.canvases) || [];
            const canMove = canvases.length > 1
                && this.getSelectedLayers().some(l => !l.locked);
            menu.querySelectorAll('.move-canvas-only').forEach(el => {
                el.style.display = canMove ? '' : 'none';
            });
        }
        menu.querySelectorAll('.hw-clear-only').forEach(el => {
            el.style.display = clear ? '' : 'none';
        });
        // The clear's divider separates it from the layer items; alone on a
        // dock menu there is nothing above it to separate from.
        const clearDivider = menu.querySelector('.menu-divider.hw-clear-only');
        if (clearDivider && inDock) clearDivider.style.display = 'none';
        const clearItem = menu.querySelector('[data-action="hw-clear"]');
        if (clearItem && clear) {
            clearItem.textContent = clear.label;
            clearItem.title = clear.title || '';
            clearItem.classList.toggle('menu-disabled', !!clear.disabled);
        }
        menu.querySelectorAll('.hw-merge-only').forEach(el => {
            el.style.display = merge ? '' : 'none';
        });
        const mergeItem = menu.querySelector('[data-action="hw-merge"]');
        if (mergeItem && merge) {
            mergeItem.textContent = merge.label;
            mergeItem.title = merge.title || '';
        }
        // The batch entries: up to three sizes plus the un-share, written
        // at open time like the clear - each slot names its own deal, and
        // a gated screen's entries stay on the menu disabled with the
        // reason as the title (discoverability without rule-breaking).
        menu.querySelectorAll('.hw-batch-only').forEach(el => {
            el.style.display = 'none';
        });
        const batchEntries = (batch && batch.entries) || [];
        batchEntries.slice(0, 3).forEach((en, i) => {
            const item = menu.querySelector(`[data-action="hw-batch-n${i}"]`);
            if (!item) return;
            item.style.display = '';
            item.textContent = en.label;
            item.title = en.title || '';
            item.classList.toggle('menu-disabled', !!en.disabled);
        });
        const bun = menu.querySelector('[data-action="hw-batch-unshare"]');
        if (bun && batch && batch.unshare) {
            bun.style.display = '';
            bun.textContent = batch.unshare.label;
            bun.title = batch.unshare.title || '';
            bun.classList.remove('menu-disabled');
        }
        const bdiv = menu.querySelector('.menu-divider.hw-batch-only');
        if (bdiv && (batchEntries.length || (batch && batch.unshare))) {
            bdiv.style.display = '';
        }
        // The snake entries: up to four slots written at open time like
        // the batch's; a shortcut hint (Alt+Enter) rides the first where
        // the entry carries one.
        menu.querySelectorAll('.hw-snake-only').forEach(el => {
            el.style.display = 'none';
        });
        const snakeEntries = (snake && snake.entries) || [];
        snakeEntries.slice(0, 4).forEach((en, i) => {
            const item = menu.querySelector(`[data-action="hw-snake-n${i}"]`);
            if (!item) return;
            item.style.display = '';
            item.textContent = en.shortcut
                ? `${en.label} (${en.shortcut})` : en.label;
            item.title = en.title || '';
            item.classList.toggle('menu-disabled', !!en.disabled);
        });
        const sdiv = menu.querySelector('.menu-divider.hw-snake-only');
        if (sdiv && snakeEntries.length && (clear || merge)) {
            sdiv.style.display = '';
        }
        // The outputs submenu: parent label names the screen's connector,
        // one entry per distro written at open time like every hw item.
        menu.querySelectorAll('.hw-out-only').forEach(el => {
            el.style.display = outs ? '' : 'none';
        });
        if (outs) {
            const lbl = menu.querySelector('#hw-outputs-label');
            if (lbl) lbl.textContent = outs.label;
            const sub = menu.querySelector('#hw-outputs-submenu');
            if (sub) {
                sub.innerHTML = '';
                outs.entries.forEach((en, i) => {
                    const item = document.createElement('div');
                    item.className = 'menu-option'
                        + (en.disabled ? ' menu-disabled' : '');
                    item.dataset.action = `hw-out-${i}`;
                    item.textContent = en.label;
                    item.title = en.title || '';
                    sub.appendChild(item);
                });
            }
        }
        [['hw-share-only', 'hw-share', sharing.share],
         ['hw-unshare-only', 'hw-unshare', sharing.unshare],
         ['ovr-redraw-only', 'ovr-redraw', ovr && ovr.redraw],
         ['ovr-auto-only', 'ovr-auto', ovr && ovr.backToAuto],
        ].forEach(([cls, action, armed]) => {
            menu.querySelectorAll(`.${cls}`).forEach(el => {
                el.style.display = armed ? '' : 'none';
            });
            const item = menu.querySelector(`[data-action="${action}"]`);
            if (item && armed) {
                item.textContent = armed.label;
                item.title = armed.title || '';
            }
        });

        menu.style.visibility = 'hidden';
        menu.style.display = 'block';
        const menuRect = menu.getBoundingClientRect();
        const margin = 8;
        const maxX = window.innerWidth - menuRect.width - margin;
        const maxY = window.innerHeight - menuRect.height - margin;
        const clampedX = Math.max(margin, Math.min(x, maxX));
        const clampedY = Math.max(margin, Math.min(y, maxY));
        menu.style.left = `${clampedX}px`;
        menu.style.top = `${clampedY}px`;
        menu.style.visibility = 'visible';
    }

    hideContextMenu() {
        const menu = document.getElementById('context-menu');
        if (menu) menu.style.display = 'none';
    }

    /**
     * v0.10.4: center the selected screens on their canvas's raster, on one
     * axis or both. Pixel Map writes offset_x/offset_y against the canvas's
     * pixel raster; Show Look writes showOffsetX/showOffsetY against the show
     * raster. Data and Power mirror Show Look, so the menu hides there.
     *
     * Each screen centers on ITS OWN canvas, so a multi-select spanning two
     * canvases does the right thing per screen. Rotated screens center by
     * their visible footprint (getLayerBounds is the rotated box).
     */
    centerLayersOnCanvas(axis = 'both') {
        const cr = window.canvasRenderer;
        if (!cr || !['pixel-map', 'show-look'].includes(cr.viewMode)) return;
        const layers = (this.getSelectedLayers() || []).filter(l => l && !l.locked);
        if (layers.length === 0) return;

        const useShow = cr.viewMode === 'show-look';
        const canvases = (this.project && this.project.canvases) || [];
        const moved = [];

        layers.forEach(layer => {
            const canvasId = useShow ? (layer.show_canvas_id || layer.canvas_id) : layer.canvas_id;
            const canvas = canvases.find(c => c.id === canvasId);
            if (!canvas) return;
            const rasterW = (useShow && canvas.show_raster_width) || canvas.raster_width || 0;
            const rasterH = (useShow && canvas.show_raster_height) || canvas.raster_height || 0;
            if (rasterW <= 0 || rasterH <= 0) return;

            // getLayerBounds is the UNROTATED box, so swap for a 90/270 screen
            // to get the visible footprint. The stored offset is the unrotated
            // top-left, so subtract the footprint delta to turn a desired
            // footprint position back into an offset.
            const b = cr.getLayerBounds(layer);
            const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
            const swap = deg === 90 || deg === 270;
            const fpW = swap ? b.height : b.width;
            const fpH = swap ? b.width : b.height;
            const fp = cr.getLayerFootprintOffset(layer);
            const centeredX = Math.round((rasterW - fpW) / 2 - fp.dx);
            const centeredY = Math.round((rasterH - fpH) / 2 - fp.dy);

            if (useShow) {
                if (axis === 'x' || axis === 'both') layer.showOffsetX = centeredX;
                if (axis === 'y' || axis === 'both') layer.showOffsetY = centeredY;
            } else {
                // Keep Show Look following the move while the two are linked
                // (same rule the Screen Info offset fields use).
                const linkedX = Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0);
                const linkedY = Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0);
                if (axis === 'x' || axis === 'both') {
                    layer.offset_x = centeredX;
                    if (linkedX) layer.showOffsetX = centeredX;
                }
                if (axis === 'y' || axis === 'both') {
                    layer.offset_y = centeredY;
                    if (linkedY) layer.showOffsetY = centeredY;
                }
            }
            moved.push(layer);
        });

        if (moved.length === 0) return;
        const label = axis === 'x' ? 'Center on Canvas X'
            : axis === 'y' ? 'Center on Canvas Y' : 'Center on Canvas';
        this.saveState(label);
        this.updateLayers(moved);
        this.loadLayerToInputs();
        cr.render();
    }

    // While ONE overridden run is open for redrawing, the editable runs ARE
    // the layer's overrides, so the step walks that list (clamped at its
    // ends) instead of the open number line - stepping onto a port the user
    // never took over would make the next click take it over silently.
    _steppedCustomIndex(layer, kind, delta) {
        const current = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        if (!this._isOverrideEditing(layer, kind)) {
            return Math.max(1, current + delta);
        }
        const nums = this.getOverrideNums(layer, kind);
        const at = nums.indexOf(current);
        const next = at === -1 ? 0
            : Math.max(0, Math.min(nums.length - 1, at + delta));
        return nums[next];
    }

    // A step button (Next / Prev, data and power) is a MOUSE control. A
    // button keeps keyboard focus after a click, and a focused button
    // re-fires on Enter and Space - so "click Next, press Enter" stepped
    // twice and the circuit numbers skipped one, which is how a brand-new
    // show ended up drawn 1-4, 6-23 (user, 2026-09-03). Tab from the
    // focused button used to step too; the document handler in canvas.js
    // now leaves Tab to a focused control. The keyboard's way to step is
    // Tab / Shift+Tab and [ / ] on the canvas, unchanged - the buttons
    // themselves just stop answering keys.
    _armStepButton(btn) {
        if (!btn) return;
        const swallow = (e) => {
            if (e.code === 'Enter' || e.code === 'NumpadEnter' || e.code === 'Space') {
                e.preventDefault();
            }
        };
        btn.addEventListener('keydown', swallow);
        btn.addEventListener('keyup', swallow);
    }

    stepCustomPort(delta) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        const view = window.canvasRenderer.viewMode;
        if (view === 'data-flow' && this.isCustomFlowEditing(this.currentLayer)) {
            this.ensureCustomFlowState(this.currentLayer);
            this.currentLayer.customPortIndex =
                this._steppedCustomIndex(this.currentLayer, 'data', delta);
            if (this._overrideEditing && this._overrideEditing.kind === 'data'
                    && this._overrideEditing.layerId === this.currentLayer.id) {
                this._overrideEditing.num = this.currentLayer.customPortIndex;
            }
            this.saveState('Custom Port Change');
            this.saveClientSideProperties();
            // v0.8.2: PUT to server (keyboard shortcut path needs the same
            // server sync as the on-screen Next/Prev buttons).
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        } else if (view === 'power' && this.isCustomPowerEditing(this.currentLayer)) {
            this.ensureCustomPowerState(this.currentLayer);
            this.currentLayer.powerCustomIndex =
                this._steppedCustomIndex(this.currentLayer, 'power', delta);
            if (this._overrideEditing && this._overrideEditing.kind === 'power'
                    && this._overrideEditing.layerId === this.currentLayer.id) {
                this._overrideEditing.num = this.currentLayer.powerCustomIndex;
            }
            this.saveState('Power Custom Circuit Change');
            this.saveClientSideProperties();
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomPowerUI();
            window.canvasRenderer.render();
        }
    }
    
    // v0.11.0: Enable + highlight the Organized / Max Capacity buttons from the
    // current layer's portMappingMode. Both modes are valid on every processor
    // now; NovaStar Armor honours its reserved-rectangle rule in BOTH of them,
    // which is why its usable capacity is lower than a plain pixel sum.
    updatePortMappingButtons() {
        const mappingOrgBtn = document.getElementById('mapping-organized');
        const mappingMaxBtn = document.getElementById('mapping-max-capacity');
        if (!mappingOrgBtn || !mappingMaxBtn) return;

        const layer = this.currentLayer;
        const processorType = (layer && layer.processorType) || 'novastar-armor';
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const isOrganized = ((layer && layer.portMappingMode) || 'organized') === 'organized';

        mappingOrgBtn.style.opacity = '1';
        mappingOrgBtn.style.pointerEvents = 'auto';
        mappingMaxBtn.style.opacity = '1';
        mappingMaxBtn.style.pointerEvents = 'auto';

        const rectNote = usesRectangle
            ? ' NovaStar Armor reserves a pixel rectangle enclosing every cabinet in the port, so a port holds fewer pixels than the raw limit.'
            : '';
        mappingOrgBtn.title = 'Ports fill complete rows or columns only.' + rectNote;
        mappingMaxBtn.title = 'Ports fill to max pixel capacity - may split mid-row/column.' + rectNote;

        // v0.11.0: the theme styles .mapping-mode-btn / .mapping-mode-btn.active
        // with !important, so the .active class is the ONLY thing that can move
        // the highlight. Inline background/color writes here were dead.
        mappingOrgBtn.classList.toggle('active', isOrganized);
        mappingMaxBtn.classList.toggle('active', !isOrganized);
    }

    // Update the port capacity display in the UI
    updatePortCapacityDisplay() {
        // v0.11.0: run the button pass FIRST. It used to sit at the end of this
        // function, behind the early returns below (no current layer / image
        // layer), so the buttons could latch into a stale state.
        this.updatePortMappingButtons();
        // v0.11.0: same reasoning - the Low Latency control and its note must
        // not latch on a stale processor when the early returns below fire.
        this.updateLowLatencyUI();
        // Same again for the group's "Route <name> as one screen" row: it has
        // to HIDE when the selection moves to an ungrouped screen, an image
        // layer or nothing at all, so it runs ahead of the early returns too.
        if (typeof this.updateGroupRouteControl === 'function') {
            this.updateGroupRouteControl();
        }

        if (!this.currentLayer) {
            return;
        }
        if ((this.currentLayer.type || 'screen') === 'image') {
            const capacityEl = document.getElementById('port-capacity');
            const panelsPerPortEl = document.getElementById('panels-per-port');
            const portsRequiredEl = document.getElementById('ports-required');
            if (capacityEl) capacityEl.textContent = '-';
            if (panelsPerPortEl) panelsPerPortEl.textContent = '-';
            if (portsRequiredEl) portsRequiredEl.textContent = '-';
            return;
        }
        
        const bitDepth = this.currentLayer.bitDepth || 8;
        const frameRate = this.currentLayer.frameRate || 60;
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const portCapacity = this.calculatePortCapacity(
            bitDepth, frameRate, processorType, !!this.currentLayer.lowLatency);
        
        // Update capacity display
        const capacityEl = document.getElementById('port-capacity');
        if (capacityEl) {
            // v0.11.0: a healthy figure renders in the ordinary text colour on
            // .value-normal, so it cannot be mistaken for a fault; the warning
            // colour is the only inline override and the only colour here.
            if (portCapacity > 0) {
                capacityEl.textContent = portCapacity.toLocaleString();
                capacityEl.classList.add('value-normal');
                capacityEl.style.color = '';
                capacityEl.title = '';
            } else {
                capacityEl.textContent = 'N/A';
                capacityEl.classList.remove('value-normal');
                capacityEl.style.color = '#ff6600';
                // v0.11.0 audit: say WHY there is no figure when the reason is
                // knowable. A frame rate the manufacturer does not publish for
                // this processor used to be answered with the nearest row's
                // capacity - on Armor, 240 Hz got the 120 Hz figure, double the
                // truth - and nothing is extrapolated to replace it, so the
                // readout has to name the fix rather than just go blank.
                const rates = (typeof this.getSupportedFrameRates === 'function')
                    ? this.getSupportedFrameRates(processorType, bitDepth) : [];
                capacityEl.title = (rates.length > 0 && frameRate > rates[rates.length - 1])
                    ? `${processorType} publishes no ${frameRate} Hz figure at `
                      + `${bitDepth}-bit. Published frame rates: `
                      + `${rates.join(', ')} Hz.`
                    : '';
            }
        }

        const panelPixels = this.getFullPanelPixels(this.currentLayer);
        const panelsPerPort = (portCapacity > 0 && panelPixels > 0) ? Math.floor(portCapacity / panelPixels) : 0;
        
        const panelsPerPortEl = document.getElementById('panels-per-port');
        if (panelsPerPortEl) {
            if (panelsPerPort < 1) {
                panelsPerPortEl.textContent = 'ERROR';
                panelsPerPortEl.classList.remove('value-normal');
                panelsPerPortEl.style.color = '#ff0000';
            } else {
                panelsPerPortEl.textContent = panelsPerPort.toLocaleString();
                panelsPerPortEl.classList.add('value-normal');
                panelsPerPortEl.style.color = '';
            }
        }
        
        // Calculate total ports required from assignments
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const visiblePanels = this.currentLayer.panels ? this.currentLayer.panels.filter(p => !p.hidden).length : 0;
        const panelCountForStatus = usesRectangle && this.currentLayer.panels ? this.currentLayer.panels.length : visiblePanels;
        const assignments = this.calculatePortAssignments(this.currentLayer);
        // v0.11.0: calculatePortAssignments is the only thing that knows where
        // each Low Latency port sits, so it hands back the derate for the note.
        this.setLowLatencyDerateNote(this.currentLayer._lowLatencyDerate);
        // v0.11.0 step 6: one group-aware implementation, shared with the
        // group roll-up and the canvas label, so a port that spans two members
        // cannot read as two different numbers in three places. `assignments`
        // is handed straight through - it was just computed above for the
        // derate note, and re-walking it would be pure waste.
        const portsRequired = this.getLayerPortsRequired(this.currentLayer, assignments);
        this.currentLayer._portsRequired = portsRequired;
        // debug toggle removed
        const portsRequiredEl = document.getElementById('ports-required');
        if (portsRequiredEl) {
            // v0.11.0 audit: no capacity at all is an ERROR here too. Without
            // this, a screen whose processor publishes no figure for its frame
            // rate showed "N/A" pixels/port, "ERROR" panels/port and then a
            // calm green 0 next to Ports Required - and 0 ports reads as "none
            // needed", which is the one thing it does not mean.
            const noCapacity = !(portCapacity > 0) && panelCountForStatus > 0;
            // v0.12: cabinets and NO ports is an error only when nothing is
            // feeding them. A member of a group that routes as one screen is
            // fed by the member that owns the walk, and a member every one of
            // whose cabinets sits on a peer's hand-drawn cable is fed by that
            // cable - in both cases zero is the honest figure and the wall's
            // real port count is on the group row in the Screens list. Without
            // this every peer of a crossing group reads a red ERROR while the
            // wall beside it is correctly routed.
            const servedByPeer = typeof this.isServedByPeerRouting === 'function'
                && this.isServedByPeerRouting(this.currentLayer, 'data');
            if ((this.currentLayer._capacityError || noCapacity
                    || (portsRequired === 0 && panelsPerPort > 0
                        && panelCountForStatus > 0 && !servedByPeer))) {
                portsRequiredEl.textContent = 'ERROR';
                portsRequiredEl.style.color = '#ff0000';
            } else if (panelCountForStatus === 0 || servedByPeer) {
                portsRequiredEl.textContent = '0';
                portsRequiredEl.style.color = 'var(--ps-dim, #c0c0c0)';
            } else {
                portsRequiredEl.textContent = portsRequired;
                if (portsRequired <= 4) {
                    portsRequiredEl.style.color = '#00cc00';
                } else if (portsRequired <= 8) {
                    portsRequiredEl.style.color = '#ffcc00';
                } else {
                    portsRequiredEl.style.color = '#ff6600';
                }
            }
        }
        // The cap under the custom controls reads the same figures.
        this._syncCustomFillReadout('data');
    }

    updatePowerCapacityDisplay() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') {
            const wattsEl = document.getElementById('power-watts-per-circuit');
            const panelsEl = document.getElementById('power-panels-per-circuit');
            const circuitsEl = document.getElementById('power-circuits-required');
            const amps1El = document.getElementById('power-total-amps-1ph');
            const amps3El = document.getElementById('power-total-amps-3ph');
            if (wattsEl) wattsEl.textContent = '-';
            if (panelsEl) panelsEl.textContent = '-';
            if (circuitsEl) circuitsEl.textContent = '-';
            if (amps1El) amps1El.textContent = '-';
            if (amps3El) amps3El.textContent = '-';
            return;
        }
        const layer = this.currentLayer;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const panelsPerCircuit = panelWatts > 0 ? Math.floor(wattsPerCircuit / panelWatts) : 0;
        // v0.11.0 audit fix: `!p.blank` as well as `!p.hidden`. This filter used
        // to drop hidden cabinets only, so a 2 x 2 screen with one cabinet
        // blanked read 800 W here and 600 W in the group roll-up and the
        // project totals - GROUPING A SCREEN CHANGED ITS WATTAGE. A blank is a
        // hole in the wall: no cabinet hangs there, it has no weight and it
        // draws nothing. Matches getGroupTotals, getPowerCounts and the canvas
        // weight label.
        const activePanels = layer.panels ? layer.panels.filter(p => !p.blank && !p.hidden) : [];
        const equivalentPanels = activePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
        const totalWatts = panelWatts * equivalentPanels;
        const totalAmps1 = voltage > 0 ? totalWatts / voltage : 0;
        const totalAmps3 = voltage > 0 ? totalWatts / (voltage * 1.73) : 0;
        layer._powerTotalAmps1 = totalAmps1;
        layer._powerTotalAmps3 = totalAmps3;

        const wattsEl = document.getElementById('power-watts-per-circuit');
        const panelsEl = document.getElementById('power-panels-per-circuit');
        const circuitsEl = document.getElementById('power-circuits-required');
        const amps1El = document.getElementById('power-total-amps-1ph');
        const amps3El = document.getElementById('power-total-amps-3ph');

        if (wattsEl) wattsEl.textContent = wattsPerCircuit > 0 ? wattsPerCircuit.toLocaleString() : '0';
        if (panelsEl) panelsEl.textContent = panelsPerCircuit > 0 ? panelsPerCircuit.toLocaleString() : '0';
        const powerAssignments = this.calculatePowerAssignments(layer);
        // count via the shared authority so a custom-routed screen reports the
        // circuits actually drawn, not what auto routing would have produced
        const circuitsRequired = this.screenCircuitCount(layer);
        // custom routing supersedes the auto assignment, so don't carry its
        // error forward (the canvas already clears it for custom patterns)
        layer._powerError = this.usesCustomCircuits(layer) ? null : powerAssignments.error;
        layer._powerCircuits = powerAssignments.circuits;
        // The engine's own numbers ride with the rows (per-run overrides gap
        // the sequence); a stale keys array against fresh rows would label a
        // circuit with its neighbour's number.
        layer._powerCircuitNumKeys = powerAssignments.nums || null;

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString() : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        if (amps1El) amps1El.textContent = totalAmps1 ? totalAmps1.toFixed(2) + ' A' : '0';
        if (amps3El) amps3El.textContent = totalAmps3 ? totalAmps3.toFixed(2) + ' A' : '0';
        // The cap under the custom controls reads the same figures.
        this._syncCustomFillReadout('power');
        // Deferred, not called inline: this runs synchronously inside the
        // change handlers of the static Power fields (panel watts, voltage,
        // amperage). The knob syncs are cheap, but refreshDistroPanel is a
        // whole dock render (its wipe included), and this same path runs
        // from controls whose Tab is still mid-flight - an inline wipe
        // destroys the field Tab is about to land in. See
        // _rebuildAfterGesture.
        this._rebuildAfterGesture(() => {
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.refreshDistroPanel();
        });
    }

    // ---- Soca plan (Phase B) -------------------------------------------------

    // True when the screen's circuits come from paths the user drew rather
    // than from auto routing - i.e. when the auto assignment (and any error
    // it reports) has been superseded.
    usesCustomCircuits(layer) {
        if (!layer || !this.isCustomPower(layer) || !layer.powerCustomPaths) return false;
        return Object.keys(layer.powerCustomPaths)
            .some(n => (layer.powerCustomPaths[n] || []).length > 0);
    }

    // The one authority for "what circuits does this screen have": drawn
    // custom paths when the screen routes custom, else the auto assignment.
    // Everything that counts, labels or orders circuits reads this - the
    // report used to count calculatePowerAssignments() directly, which
    // ignored custom routing and disagreed with the soca plan beside it.
    screenCircuits(layer) {
        if (!layer) return [];
        if (this.isCustomPower(layer) && layer.powerCustomPaths) {
            const drawn = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => Number.isFinite(n) && (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b)
                .map(n => {
                    // Resolve every step through the cross-member seam. The
                    // old getPanelByRowCol(layer, ...) landed a step that
                    // names a PEER ({row, col, layerId}) on the OWNER's
                    // cabinet at that address - a different physical cabinet,
                    // or null - silently corrupting soca leg watts, distro
                    // roll-ups, breaker labels and the label PDFs built from
                    // them. A panel resolved from a peer carries real
                    // x/y/width/height, so everything downstream keeps
                    // working; `layers` rides alongside, index-aligned with
                    // `panels`, so getSocaPlan can charge each cabinet at its
                    // OWN member's wattage. Same-layer steps resolve exactly
                    // as before (getResolvedPathPanels drops hidden panels
                    // the way the old .filter(p => p && !p.hidden) did).
                    const resolved = this.getResolvedPathPanels(
                        layer, layer.powerCustomPaths[n] || []);
                    return {
                        num: n,
                        panels: resolved.map(r => r.panel),
                        layers: resolved.map(r => r.layer),
                    };
                });
            // set to custom but nothing routed yet: fall back to the auto
            // requirement the way the ports side does, so an unrouted screen
            // still shows the distro it needs instead of reporting zero -
            // UNLESS every feedable cabinet here is already on a peer's
            // crossing circuit. That is the only honest empty plan: the
            // member's power arrives on the owner's circuits (where the
            // resolved entries above count these cabinets), so an auto
            // fallback would fabricate a plan for cables that do not exist
            // and double-count the load in every distro roll-up. Mirrors
            // getLayerCircuitsRequired's only-honest-zero rule.
            // (Evaluated BEFORE splitter merge grouping: whether a member is
            // peer-served is a fact about the drawn paths, not the merges.)
            if (drawn.length) return this._applySplitterMerges(layer, drawn);
            if (typeof this._layerFullyServedByPeerPath === 'function'
                && this._layerFullyServedByPeerPath(layer, 'powerCustomPaths')) {
                return [];
            }
        }
        const res = this.calculatePowerAssignments(layer);
        return (res.circuits || []).map((panels, i) => {
            // `nums` exists only when per-run overrides are in play: the auto
            // circuits skip the overridden numbers and the overridden ones
            // keep theirs, so i + 1 stops being the truth there.
            const c = { num: res.nums ? res.nums[i] : i + 1, panels };
            // v0.12: an AUTOMATIC circuit can now cross into a group peer too,
            // so it carries the same index-aligned `layers` a hand-drawn
            // crossing circuit has carried since v0.11.0 - getSocaPlan charges
            // each cabinet at its own member's wattage off this. Absent for
            // every non-crossing plan, exactly as before.
            if (res.layers && res.layers[i]) c.layers = res.layers[i];
            // Splitter packing (organized + enabled): the engine hands back
            // per-branch panel counts index-aligned with `circuits`. Carry
            // them as per-branch panel arrays so the renderers can break the
            // daisy at run boundaries; `panels` stays the concatenation, so
            // every index-aligned consumer is untouched.
            if (res.runs && res.runs[i]) {
                let off = 0;
                c.branches = res.runs[i].map(n => panels.slice(off, off += n));
                c.runIds = res.runIds ? res.runIds[i] : null;
            }
            return c;
        });
    }

    // Manual splitter merges over DRAWN custom circuits: each merge group
    // collapses into ONE circuit numbered and labelled by its first member
    // (traversal order = ascending drawn number), with the member paths kept
    // as `branches`. Custom paths are NEVER auto-packed - the numbering is
    // user intent - so manual merge is the only lever here. No merges = the
    // exact input array, byte-identical to the pre-splitter path.
    _applySplitterMerges(layer, drawn) {
        const groups = this.appliedSplitterGroups(
            layer, drawn.map(c => c.num)).merge;
        if (!groups.length) return drawn;
        const byNum = new Map(drawn.map(c => [c.num, c]));
        const inGroup = new Map();
        groups.forEach(g => g.forEach(n => inGroup.set(n, g)));
        const out = [];
        const done = new Set();
        for (const c of drawn) {
            if (done.has(c.num)) continue;
            const g = inGroup.get(c.num);
            if (!g) { out.push(c); continue; }
            const members = g.filter(n => byNum.has(n)).map(n => byNum.get(n));
            members.forEach(m => done.add(m.num));
            out.push({
                num: members[0].num,
                panels: members.flatMap(m => m.panels),
                layers: members.flatMap(m => m.layers || m.panels.map(() => layer)),
                branches: members.map(m => m.panels),
                runIds: members.map(m => m.num),
            });
        }
        return out;
    }

    // The COUNT comes from the group-aware authority (app-screen-info.js) so
    // it agrees with the sidebar and the group roll-up: a peer-served member
    // reports 0, and drawn custom circuits report the highest circuit number
    // drawn - the same convention the ports side uses. screenCircuits above
    // keeps the [{num, panels}] plan shape for the soca planner, which
    // legitimately operates on the drawn paths. autoCircuits is recomputed
    // here rather than read from the cached _powerCircuitsRequired, which is
    // only refreshed for the currently-selected layer.
    screenCircuitCount(layer) {
        if (!layer) return 0;
        const auto = (this.calculatePowerAssignments(layer).circuits || []).length;
        return this.getLayerCircuitsRequired(layer, auto) || 0;
    }

    // ---- multi splits --------------------------------------------------------
    //
    // How a screen's circuits group into multis used to be pure arithmetic -
    // floor(ordinal / 6) - which is exactly why the reference show could not
    // land "the 2 remaining circuits" on another box without hand-typed
    // labels: the remainder was welded to its 6-block. A SPLIT breaks one
    // multi at a user-chosen circuit boundary, and each resulting part is a
    // multi in its own right - its own tile, its own (distro, number), so a
    // 2-circuit tail can pin onto another box's free tails through the
    // ordinary shared-soca gesture.
    //
    // The store is `layer.powerSocaSplits`: an array of 1-based circuit
    // ordinals (position in the plan's circuit order, splitter merges
    // already applied) after which a multi ends early. Boundaries compose
    // with the fixed 6-grid rather than re-wrapping it: 14 circuits with a
    // break after 2 read [1-2][3-6][7-12][13-14], so every multi AFTER the
    // split keeps the span it always had and only the indexes step. No
    // stored splits = the exact floor(/6) segmentation, byte for byte.

    // Normalized read: distinct interior ordinals, ascending. Points at or
    // past the end of the plan (the wall shrank) are ignored, not deleted -
    // the same degrade-on-read rule the tail stores follow.
    _socaSplitPoints(layer, count) {
        const raw = (layer && layer.powerSocaSplits) || [];
        if (!Array.isArray(raw)) return [];
        return [...new Set(raw.map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1
                && (count == null || n < count)))]
            .sort((a, b) => a - b);
    }

    // The plan's multis as contiguous ordinal runs: [{index, start, end,
    // userEnd}], 1-based inclusive. Boundaries are the fixed box grid (six
    // for a soca, three for an L21-30 - socaBoxSize) plus every stored
    // split point; `userEnd` marks a part whose END is a stored point -
    // the boundary the "Merge back into …" gesture removes.
    _socaSegments(layer, count) {
        const n = Math.max(0, Number(count) || 0);
        if (!n) return [];
        const size = this.socaBoxSize(layer);
        const stored = new Set(this._socaSplitPoints(layer, n));
        const segs = [];
        let start = 1;
        for (let i = 1; i <= n; i++) {
            if (i === n || i % size === 0 || stored.has(i)) {
                segs.push({ index: segs.length + 1, start, end: i,
                            userEnd: stored.has(i) });
                start = i + 1;
            }
        }
        return segs;
    }

    // ordinal (1-based) -> soca index, flat for the per-circuit walks.
    _socaIndexByOrdinal(segs) {
        const idx = [];
        segs.forEach(s => {
            for (let i = s.start; i <= s.end; i++) idx[i] = s.index;
        });
        return idx;
    }

    // How many multis `count` circuits make on this screen - the split-aware
    // replacement for ceil(count / 6), shared with the canvas info line.
    socaCountFor(layer, count) {
        return this._socaSegments(layer, count).length;
    }

    // Insert (delta +1) or remove (delta -1) one multi's slot at `at` in
    // every per-multi store, the way an array splice would: a split gives
    // the new second part a clean slate and every later multi keeps its
    // name, distro, number, length and tails under its stepped index.
    // Removal drops slot `at`'s own entries with it.
    _spliceSocaStores(layer, at, delta) {
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const map = layer[field];
            if (!map || typeof map !== 'object') continue;
            const next = {};
            for (const key of Object.keys(map)) {
                const n = parseInt(key, 10);
                // Not a multi index, so not ours to move - carried across,
                // same rule as migrateSocaKeying.
                if (!Number.isFinite(n)) { next[key] = map[key]; continue; }
                if (delta > 0) next[n >= at ? n + 1 : n] = map[key];
                else if (n === at) continue;
                else next[n > at ? n - 1 : n] = map[key];
            }
            layer[field] = next;
        }
    }

    // Re-key every per-multi store from the OLD segmentation to a NEW set
    // of split points, in one move - the general form of the splice above
    // for gestures that change several boundaries at once (a clear that
    // forgets the cuts at its edges, a drop that absorbs the one-circuit
    // leftovers in its span). Each old multi is followed by its START
    // ordinal: whichever new segment holds that circuit inherits the
    // stores under the new index. When two old multis land in one new
    // segment the FIRST claimant wins, per store: the earlier multi's
    // entry stands, the later's drops, and a field the earlier never set
    // takes the later's - so nothing on file is lost that need not be.
    // The callers arrange that little collides anyway: a cleared multi
    // was wiped first, an absorbed leftover is unassigned. A multi whose
    // SPAN changed (it grew or was cut) sheds its stored tail set and
    // breaker offset the way the split and un-split always did - the
    // arrangement covered circuits the multi no longer has, or too few
    // for the ones it has now - while name, distro, number and length
    // are identity and carry. Writes `layer.powerSocaSplits` (normalized)
    // and drops the naming cache. Returns Map(oldIndex -> { index:
    // newIndex, same: span unchanged }).
    _resegmentSocaStores(layer, newSplitPoints) {
        if (!layer) return new Map();
        const count = this.screenCircuits(layer).length;
        const oldSegs = this._socaSegments(layer, count);
        layer.powerSocaSplits = this._socaSplitPoints(
            { powerSocaSplits: newSplitPoints }, count);
        const newSegs = this._socaSegments(layer, count);
        const newIdxOf = this._socaIndexByOrdinal(newSegs);
        const map = new Map();
        for (const s of oldSegs) {
            const ni = newIdxOf[s.start];
            if (!ni) continue;
            const t = newSegs[ni - 1];
            map.set(s.index, { index: ni,
                               same: t.start === s.start && t.end === s.end });
        }
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const store = layer[field];
            if (!store || typeof store !== 'object') continue;
            const next = {};
            const keys = Object.keys(store).sort((a, b) =>
                (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));
            for (const key of keys) {
                const n = parseInt(key, 10);
                // Not a multi index, so not ours to move - carried across,
                // same rule as _spliceSocaStores.
                if (!Number.isFinite(n)) { next[key] = store[key]; continue; }
                const m = map.get(n);
                if (!m) continue;
                if (!m.same && (field === 'powerSocaPhasePos'
                                || field === 'powerSocaPhaseOffset')) continue;
                if (next[m.index] !== undefined) continue;
                next[m.index] = store[key];
            }
            layer[field] = next;
        }
        this._circuitTailCache = null;
        return map;
    }

    // The split MUTATION on its own, no history entry: validation, the
    // incumbent stamp, the store splice. splitSocaAfter wraps it with the
    // one-entry snapshot; the dock's drop-implied split composes it with
    // the assignment that motivated it so the whole gesture is ONE entry.
    // Returns the stamped layers (the incumbents can live on other screens)
    // or null when the cut is not a legal boundary.
    _splitSocaApply(layer, socaIndex, afterLeg) {
        if (!layer) return null;
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const seg = segs.find(s => s.index === Number(socaIndex));
        const cut = parseInt(afterLeg, 10);
        if (!seg || !Number.isFinite(cut) || cut < 1
                || cut >= seg.end - seg.start + 1) return null;
        const boundary = seg.start + cut - 1;
        const points = this._socaSplitPoints(layer, count);
        if (points.includes(boundary)) return null;
        // The first part keeps the pin but sheds circuits, so it re-deals
        // its tails on the box - and if that box is shared, the OTHER
        // members' rendered tails must be held first or the re-deal could
        // slide them (stamped before any store moves, while the naming
        // cache still shows the pre-split wall).
        const stamped = this._materializeSocaBox(
            (layer.powerSocaDistro || {})[socaIndex],
            (layer.powerSocaNumber || {})[socaIndex], layer, socaIndex);
        layer.powerSocaSplits = [...points, boundary].sort((a, b) => a - b);
        this._spliceSocaStores(layer, Number(socaIndex) + 1, +1);
        delete (layer.powerSocaPhasePos || {})[socaIndex];
        delete (layer.powerSocaPhaseOffset || {})[socaIndex];
        // The segmentation just changed, so every read from here on must
        // see the post-split wall - a caller composing further mutations
        // (the drop gesture's second cut, the target-box stamp) included.
        this._circuitTailCache = null;
        return stamped;
    }

    // Break multi `socaIndex` after its `afterLeg`-th circuit (1..legs-1).
    // The first part keeps the multi's identity - name, distro, number,
    // length - and the second starts unassigned; its stored tail set is
    // dropped because the arrangement covered circuits the part no longer
    // has. Contiguous only: a boundary, never a reshuffle.
    splitSocaAfter(layer, socaIndex, afterLeg) {
        const stamped = this._splitSocaApply(layer, socaIndex, afterLeg);
        if (!stamped) return false;
        this.updateLayers([...new Set([layer, ...stamped])], true,
                          'Split Multi');
        return true;
    }

    // ---- a multi dropped on a circuit takes the box's FIRST circuits ------
    //
    // User (2026-09-04): "if i add circuits the numbering is all wrong and
    // when i try and say drag multi 2 onto 6 ports it only lets me do 1
    // because of the incorrect numbering. we need to audit this so it
    // allows me to do up to 6 if i am doing multi/soca. so even if i have
    // 1 circuit taken on multi 1 then i have 5 circuits left and i should
    // only be able to add 5 more to that multi."
    //
    // The wall he was looking at: circuit-pip drops (_dockDropTail) cut
    // before and after their circuit by design, so a run of them leaves a
    // trail of one-circuit multis - S2[7] S3[8] ... - and a slot dropped on
    // circuit 7 used to assign exactly the multi under the cursor: one
    // circuit onto a box with six free. The first take rule reached from
    // the hovered circuit FORWARD to the grid line - hover 6 of a six and
    // one circuit lit, hover 1 and all six did - which read backwards on
    // the wall. User (2026-09-05): "data and power when dragged onto a
    // screen in bulk starts say s1-6 and then as you drag towards 1-1 it
    // fills all 6 circuits. i need it to start at 1-1 instead and increase
    // to 1-6 instead. it is backwards for how it should work." Asked what
    // to anchor to: "So typically you would start with multi 1 so start
    // at the 1st circuit regardless of naming. should just be in order."
    //
    // ONE rule, anchored at the START of the box cell, for the plain
    // whole-multi drop and the mid-multi drop alike (the old "from this
    // circuit on" split-drop is gone - a drop on a later circuit now
    // means "the first N"):
    //
    //   The hovered circuit `o` sits in one cell of the fixed box grid
    //   (_socaSegments always cuts at multiples of socaBoxSize, so a multi
    //   never crosses a grid line and neither does the span). The span
    //   runs from the cell's first circuit TO `o`, in order: hover the
    //   cell's 1st and that circuit alone lights, its 4th and the first
    //   four light, its 6th and all six. Circuits at the head of the cell
    //   that already sit on a DIFFERENT box are somebody's feed and are
    //   never pulled off it by a drop aimed elsewhere: they are skipped,
    //   so the span begins at the first circuit after the last of them
    //   and runs to `o`. Hovering a circuit that itself sits on another
    //   box refuses - nothing lights, the drop says so. "Another box" is
    //   an assignment that is not the target (distroId, number): a pin on
    //   any other number, or any number on another distro. A multi already
    //   on the target box is re-taken (it stays; the span grows around
    //   it), and a same-distro AUTO number holds nothing - it re-deals -
    //   so it is absorbed like an unassigned leftover.
    //
    //   Capacity: min(span, free). `free` is what the box can still hold,
    //   computed the way the join always did - the smallest box size among
    //   the box's members, minus the legs its PINNED incumbents hold (an
    //   auto at that number re-deals and defends nothing); a pinned member
    //   of this screen that overlaps the span counts only the legs that
    //   STAY outside it (the multi re-dropped onto its own box counts at
    //   what stays). Short of the span, the FIRST `free` circuits land
    //   ("took N of M") and the rest stay as their own unassigned multi;
    //   a full box refuses outright and moves nothing. The unassigned
    //   one-circuit leftovers inside the span are absorbed; the remainder
    //   of the cell beyond the span stays as its own multi, keeping the
    //   assignment it had.
    //
    // The store moves are a resegmentation: every stored point strictly
    // inside the taken span removed, a boundary at the span's end where it
    // stops short of the grid line, then _resegmentSocaStores re-keys what
    // survives; the one taken segment gets (distroId, number) with the
    // incumbents' tails frozen first, as every join freezes them, and a
    // remainder cut off a multi that was on a box keeps that box and the
    // tails it was rendering, so nobody moves. ONE history entry for the
    // whole gesture.

    // The resolution on its own, no mutation - the preview lights exactly
    // these circuits and the release takes exactly these circuits, so the
    // two can never disagree. `ordinal` is 1-based in the plan's circuit
    // order. Returns { ok, free, remaining, take, nums, spanStart, spanEnd,
    // ... } - or { ok: false, why: 'other-box' | 'full', free, remaining }
    // for a refusal.
    _socaTakePlan(layer, ordinal, distroId, number) {
        const none = { ok: false, free: 0, remaining: 0, take: 0, nums: [] };
        if (!layer || !distroId) return none;
        const circuits = this.screenCircuits(layer);
        const count = circuits.length;
        const o = parseInt(ordinal, 10);
        if (!Number.isFinite(o) || o < 1 || o > count) return none;
        const segs = this._socaSegments(layer, count);
        const seg = segs.find(s => s.start <= o && o <= s.end);
        if (!seg) return none;
        const size = this.socaBoxSize(layer);
        const n = parseInt(number, 10);
        const assign = layer.powerSocaDistro || {};
        const pins = layer.powerSocaNumber || {};
        const members = this._distroMultiNumbers(distroId).get(n) || [];
        const onTarget = new Set(members
            .filter(m => m.layerId === layer.id).map(m => m.soca));
        // On another box: assigned, and not this box - a pin on another
        // number, or any number on another distro. A same-distro auto at
        // some other number is not holding anything.
        const onOther = s => !!assign[s.index] && !onTarget.has(s.index)
            && (assign[s.index] !== distroId
                || Number.isFinite(parseInt(pins[s.index], 10)));
        if (onOther(seg)) {
            return { ok: false, why: 'other-box', free: 0, remaining: 0,
                     take: 0, nums: [], seg, ordinal: o };
        }
        const cellStart = Math.floor((o - 1) / size) * size + 1;
        const cellEnd = Math.min(count, cellStart + size - 1);
        // The anchor: the cell's first circuit, stepped past every circuit
        // before `o` that is on another box.
        let start = cellStart;
        for (const s of segs) {
            if (s.end < cellStart || s.start > o) continue;
            if (onOther(s)) start = Math.max(start, s.end + 1);
        }
        const remaining = o - start + 1;
        let held = 0;
        // The target box's fan is as big as the SMALLEST breakout claiming
        // it - a 3-tail L21-30 box has three tails whoever else lands on
        // it, and pretending to six would deal tails that do not exist.
        let cap = size;
        for (const m of members) {
            const ml = ((this.project && this.project.layers) || [])
                .find(l => l.id === m.layerId);
            if (ml) cap = Math.min(cap, this.socaBoxSize(ml));
            if (!m.pinned) continue;
            const ms = m.layerId === layer.id
                ? segs.find(s => s.index === m.soca) : null;
            // A pinned member of this screen inside the span is re-taken:
            // only the legs that stay outside the span are held.
            held += (ms && ms.start <= o && ms.end >= start)
                ? Math.max(0, start - ms.start) + Math.max(0, ms.end - o)
                : m.legs;
        }
        const free = Math.max(0, cap - held);
        if (!free) {
            return { ok: false, why: 'full', free, remaining, take: 0,
                     nums: [], seg, ordinal: o, spanStart: start };
        }
        const take = Math.min(remaining, free);
        return {
            ok: true, free, remaining, take, seg, number: n, ordinal: o,
            spanStart: start, spanEnd: start + take - 1, gridEnd: cellEnd,
            nums: circuits.slice(start - 1, start - 1 + take).map(c => c.num),
        };
    }

    // The mutation: resegment, re-key, stamp, assign - ONE history entry
    // under `action`. Returns { ok, took, tailLen, free } (`tailLen` is
    // the span the drop reached for, so a caller can say "took N of M")
    // or { ok: false, why, free, tailLen } for the refusal, with nothing
    // moved.
    takeSocaOnto(layer, ordinal, distroId, number, action) {
        const plan = this._socaTakePlan(layer, ordinal, distroId, number);
        if (!plan.ok) return { ok: false, why: plan.why, free: plan.free,
                               tailLen: plan.remaining };
        const count = this.screenCircuits(layer).length;
        const size = this.socaBoxSize(layer);
        const segs = this._socaSegments(layer, count);
        const start = plan.spanStart;
        const end = plan.spanEnd;
        const touched = new Set([layer]);
        // The multi the span's end cuts through, when it runs past it: its
        // remainder keeps the box it was on (2026-09-05 rule: "the
        // remainder ... keeps whatever assignment it had") and the tails
        // it was rendering for those circuits, so a re-drop onto the same
        // box never reshuffles the cabled fan; the other members of that
        // box hold their rendered tails first, as every split does. Read
        // while the naming cache still shows the pre-drop wall.
        const cut = segs.find(s => s.start <= end && s.end > end);
        const assign = layer.powerSocaDistro || {};
        let carry = null;
        if (cut && assign[cut.index]) {
            const rec = this._powerNaming(layer).socas.get(cut.index);
            const pinNum = parseInt((layer.powerSocaNumber || {})[cut.index], 10);
            const L = cut.end - cut.start + 1;
            const shown = rec && rec.positions;
            const pos = (Array.isArray(shown) && shown.length === L
                && shown.every(p => Number.isInteger(p) && p >= 1 && p <= size)
                && new Set(shown).size === L)
                ? shown.slice(end + 1 - cut.start) : null;
            carry = { distro: assign[cut.index],
                      number: Number.isFinite(pinNum) ? pinNum : null,
                      name: (layer.powerSocaNames || {})[cut.index], pos };
            if (carry.number != null) {
                this._materializeSocaBox(carry.distro, carry.number, layer,
                                         cut.index)
                    .forEach(l => touched.add(l));
            }
        }
        const points = this._socaSplitPoints(layer, count)
            .filter(p => p < start - 1 || p > end);
        if (start > 1 && (start - 1) % size !== 0) points.push(start - 1);
        if (end < count && end % size !== 0) points.push(end);
        this._resegmentSocaStores(layer, points);
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, count));
        const idx = idxOf[start];
        if (carry) {
            const remIdx = idxOf[end + 1];
            const put = (field, v) => {
                (layer[field] || (layer[field] = {}))[remIdx] = v;
            };
            put('powerSocaDistro', carry.distro);
            if (carry.number != null) put('powerSocaNumber', carry.number);
            if (carry.name !== undefined) put('powerSocaNames', carry.name);
            if (carry.pos) put('powerSocaPhasePos', carry.pos);
            this._circuitTailCache = null;
        }
        // Landing on an occupied box is the JOIN: the incumbents' rendered
        // tails freeze first so the taken part deals into what is
        // genuinely free - the same stamp the panel's number pick made.
        this._materializeSocaBox(distroId, plan.number, layer, idx)
            .forEach(l => touched.add(l));
        (layer.powerSocaDistro || (layer.powerSocaDistro = {}))[idx]
            = distroId;
        (layer.powerSocaNumber || (layer.powerSocaNumber = {}))[idx]
            = plan.number;
        this._circuitTailCache = null;
        this.updateLayers([...touched], true, action || 'Assign Multi Distro');
        return { ok: true, took: plan.take, tailLen: plan.remaining,
                 free: plan.free };
    }

    // The drop-implied cut spelled as it always was - multi `socaIndex`,
    // its `afterLeg`-th circuit, box (distroId, number) - now a thin
    // wrapper over takeSocaOnto with the anchored meaning (2026-09-05):
    // the drop lands on the multi's circuit `afterLeg + 1`, so the box
    // takes the cell's FIRST circuits up to that one, and the take rule
    // decides how many of them the box has room for. Kept under its own
    // history name for the callers that ask for a split by name; the
    // dock's drop records the assignment.
    splitSocaOnto(layer, socaIndex, afterLeg, distroId, number) {
        if (!layer || !distroId) return { ok: false, free: 0, tailLen: 0 };
        const count = this.screenCircuits(layer).length;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === Number(socaIndex));
        const cut = parseInt(afterLeg, 10);
        if (!seg || !Number.isFinite(cut) || cut < 1
                || cut >= seg.end - seg.start + 1) {
            return { ok: false, free: 0, tailLen: 0 };
        }
        return this.takeSocaOnto(layer, seg.start + cut, distroId, number,
                                 'Split Multi');
    }

    // Remove the stored boundary at the end of part `socaIndex`: the part
    // and its successor fall back into one natural block. The successor's
    // stores go with its identity; the surviving multi keeps the first
    // part's. Always safe - segmentation re-runs on the 6-grid, so a 6+2
    // that came from a split simply becomes a natural 6+2.
    unsplitSocaAfter(layer, socaIndex) {
        if (!layer) return false;
        const count = this.screenCircuits(layer).length;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === Number(socaIndex));
        if (!seg || !seg.userEnd) return false;
        // The welded multi keeps the first part's pin with MORE circuits,
        // so it re-deals on its box exactly like a split part does - the
        // other members of a shared box hold their rendered tails first.
        const stamped = this._materializeSocaBox(
            (layer.powerSocaDistro || {})[socaIndex],
            (layer.powerSocaNumber || {})[socaIndex], layer, socaIndex);
        layer.powerSocaSplits = this._socaSplitPoints(layer, count)
            .filter(p => p !== seg.end);
        this._spliceSocaStores(layer, Number(socaIndex) + 1, -1);
        delete (layer.powerSocaPhasePos || {})[socaIndex];
        delete (layer.powerSocaPhaseOffset || {})[socaIndex];
        this._circuitTailCache = null;
        this.updateLayers([...new Set([layer, ...stamped])], true,
                          'Un-split Multi');
        return true;
    }

    // ---- one circuit off its box, the rest of the multi staying put -----
    //
    // User (2026-09-05): "lets say i pair 6 circuits on power but i want
    // to delete the 6th circuit from the distro we have no way of doing
    // that. can only clear the whole multi."
    //
    // The circuit chip's clear (and its drag back onto the tray) takes
    // THAT circuit off the box and nothing else. The circuit becomes its
    // own unassigned one-circuit multi - a cut before it where it is not
    // already a segment start, a cut after it where it is not the multi's
    // last - and the rest of the multi stays exactly as the wall showed
    // it: the HEAD part (the circuits before it) keeps the multi's
    // identity - typed name, home-run length, distro, number - and holds
    // the tails it was rendering; a TAIL part (the circuits after it, when
    // the circuit was in the middle) stays on the SAME box, (distroId,
    // number), holding the tails IT was rendering, so SR1-1 SR1-2 SR1-4
    // SR1-5 SR1-6 keep reading exactly that with tail 3 free on the box
    // and nobody moves or renumbers - and a typed multi name rides the
    // tail part too, because the labels derive from it (STAGE LEFT-4
    // must not turn into SR1-4: same name on the same number IS the
    // shared-box shape). The home-run length stays with the head alone:
    // one cable, counted once. When the circuit was the multi's FIRST the
    // identity goes to the part after it - the multi is the circuits
    // that stay, whichever end came off. The other members of a
    // shared box hold their rendered tails first, as every join and split
    // freezes them. The multi's shown number becomes its pin where it was
    // auto - a head and a tail part on one box need the pin to be one box
    // (what was showing becomes held, the tail rule applied to the
    // number).
    //
    // No history entry and none of the circuit's own paperwork here: the
    // dock's _clearCircuitChip wraps this with the wipe of the removed
    // circuit's programming (label override, manual splitter entries) and
    // the one 'Clear Circuit' entry, so a single undo puts back the cuts,
    // the stores and the positions together. Returns { touched,
    // removedIdx } or null when the circuit is not in that multi.
    //
    // The store moves ride _resegmentSocaStores, which follows a multi by
    // its START circuit - the removed circuit itself when it was the
    // first - so this multi's own entries are lifted out before the
    // re-key and put back by hand on the part that keeps the identity;
    // every OTHER multi on the screen keeps its stores under its stepped
    // index the ordinary way. A one-circuit multi has no rest to keep:
    // the dock clears it by the multi-scope rule it always ran.
    _socaReleaseCircuit(layer, socaIndex, circuitNum) {
        if (!layer) return null;
        const idx = Number(socaIndex);
        const rec = this._powerNaming(layer).socas.get(idx);
        const at = rec ? rec.circuits.indexOf(circuitNum) : -1;
        if (!rec || at < 0 || rec.circuits.length < 2) return null;
        const circuits = this.screenCircuits(layer);
        const count = circuits.length;
        const o = circuits.findIndex(c => c.num === circuitNum) + 1;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === idx);
        if (!seg || o < seg.start || o > seg.end) return null;
        const L = rec.circuits.length;
        // The tails the wall was showing, held only when they are a fan
        // arrangement worth holding - the _materializeSocaBox test.
        const cap = this.socaBoxSize(layer);
        const shown = rec.positions;
        const pos = (Array.isArray(shown) && shown.length === L
            && shown.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
            && new Set(shown).size === L) ? shown.slice() : null;
        const n = parseInt(rec.number, 10);
        const onBox = !!rec.distroId && Number.isFinite(n) && n >= 1;
        const touched = new Set([layer]);
        if (onBox) {
            this._materializeSocaBox(rec.distroId, n, layer, idx)
                .forEach(l => touched.add(l));
        }
        const points = this._socaSplitPoints(layer, count);
        if (o > seg.start) points.push(o - 1);
        if (o < seg.end) points.push(o);
        const fields = ['powerSocaDistro', 'powerSocaLengths',
                        'powerSocaPhasePos', 'powerSocaPhaseOffset',
                        'powerSocaNames', 'powerSocaNumber'];
        const carried = {};
        for (const field of fields) {
            const store = layer[field];
            if (!store || store[idx] === undefined) continue;
            carried[field] = store[idx];
            delete store[idx];
        }
        this._resegmentSocaStores(layer, points);
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, count));
        const headIdx = o > seg.start ? idxOf[seg.start] : null;
        const tailIdx = o < seg.end ? idxOf[o + 1] : null;
        const keepIdx = headIdx != null ? headIdx : tailIdx;
        const put = (field, i, v) => {
            (layer[field] || (layer[field] = {}))[i] = v;
        };
        // Identity onto the part that keeps it. The stored tail set and
        // the legacy breaker offset are not carried: the arrangement
        // covered circuits the part no longer has (the split rule) - the
        // shown tails go back on below, part by part.
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaNames', 'powerSocaNumber']) {
            if (carried[field] === undefined) continue;
            put(field, keepIdx, carried[field]);
        }
        if (onBox) {
            put('powerSocaDistro', keepIdx, rec.distroId);
            put('powerSocaNumber', keepIdx, n);
            if (headIdx != null && tailIdx != null) {
                put('powerSocaDistro', tailIdx, rec.distroId);
                put('powerSocaNumber', tailIdx, n);
                if (carried.powerSocaNames !== undefined) {
                    put('powerSocaNames', tailIdx, carried.powerSocaNames);
                }
            }
        }
        if (pos) {
            if (headIdx != null) {
                put('powerSocaPhasePos', headIdx, pos.slice(0, at));
            }
            if (tailIdx != null) {
                put('powerSocaPhasePos', tailIdx, pos.slice(at + 1));
            }
        }
        this._circuitTailCache = null;
        return { touched: [...touched], removedIdx: idxOf[o] };
    }

    getSocaPlan(layer) {
        if (!layer) return [];
        const circuits = this.screenCircuits(layer);   // [{num, panels}] in circuit order
        if (!circuits.length) return [];
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        // `soca` is the multi's STABLE INDEX within this screen, which is what
        // the per-multi stores are keyed by; `number` and `name` come off the
        // show-wide naming index, where numbering runs per distro. The two
        // were the same thing while a multi's number came from the screen's
        // own template - see _powerNaming for why they cannot be.
        const nm = this._powerNaming(layer);
        const socas = new Map();
        // Which multi each circuit belongs to comes from the split-aware
        // segmentation, not floor(/6) - identical while no split is stored.
        const segs = this._socaSegments(layer, circuits.length);
        const idxOf = this._socaIndexByOrdinal(segs);
        circuits.forEach((c, ci) => {
            const n = idxOf[ci + 1];
            const leg = ci + 2 - segs[n - 1].start;
            // A cross-member circuit carries cabinets from a PEER layer, and
            // those cabinets draw the peer's wattage, not the owner's -
            // screenCircuits hands back `layers` index-aligned with `panels`
            // for exactly this. Same-layer panels (and every auto plan, which
            // carries no `layers`) keep the owner's figure, byte-identical to
            // before. Voltage stays the OWNER's: the circuit is the owner's
            // cable on the owner's distro, whatever it feeds.
            const srcLayers = c.layers || [];
            const watts = c.panels.reduce((s, p, pi) => {
                const src = srcLayers[pi];
                const w = (src && src !== layer)
                    ? (parseFloat(src.panelWatts) || 0) : panelWatts;
                return s + w * this.getPanelLoadFactor(src || layer, p);
            }, 0);
            const info = nm.socas.get(n);
            const s = socas.get(n) || {
                soca: n,
                number: info ? info.number : n,
                name: (info && info.name)
                    || this._deriveMultiName(nm.tpl.prefix || 'S',
                                             (nm.tpl.start || 1) + n - 1, nm.tpl),
                distroId: (info && info.distroId) || null,
                legs: [], watts: 0, x1: Infinity, x2: -Infinity
            };
            // per-leg x extent so the power map can tick each leg to the
            // columns it feeds (Binder convention)
            let lx1 = Infinity, lx2 = -Infinity;
            c.panels.forEach(p => {
                const px = Number(p.x) || 0;
                lx1 = Math.min(lx1, px);
                lx2 = Math.max(lx2, px + (Number(p.width) || 0));
            });
            s.legs.push({
                leg, circuit: c.num,
                label: this.getPowerCircuitLabel(layer, c.num),
                tiles: c.panels.length, watts,
                amps: voltage ? watts / voltage : 0,
                x1: Number.isFinite(lx1) ? lx1 : null,
                x2: Number.isFinite(lx2) ? lx2 : null
            });
            s.watts += watts;
            c.panels.forEach(p => {
                const px = Number(p.x) || 0;
                s.x1 = Math.min(s.x1, px);
                s.x2 = Math.max(s.x2, px + (Number(p.width) || 0));
            });
            socas.set(n, s);
        });
        const plans = [...socas.values()];
        // v0.12.0: `leg` reports the PHYSICAL TAIL of the 6-way fan each
        // circuit lands on - identical to the sequence index until phase
        // balancing or a breaker offset moves the soca's circuits to other
        // tails, at which point the report table, breaker stickers,
        // schematic feed bubbles and bracket ticks all follow the true
        // tails. Order stays circuit order and the tails come back
        // ASCENDING (wall-order rule via socaCircuitPositions), so the wall
        // always reads in order with gaps where a tail is skipped;
        // amps/watts are untouched - balancing only renumbers.
        plans.forEach(s => {
            const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
            s.legs.forEach((l, i) => { l.leg = pos[i]; });
        });
        return plans.map(s => ({
            ...s,
            amps: voltage ? s.watts / voltage : 0,
            length: (layer.powerSocaLengths || {})[s.soca] || null
        }));
    }

    // Breakout chain from the Soca/multi to the panels. Socas break out to
    // True1 or powerCON by default (panels take those directly - that's why
    // a multi is 6 channels); Edison is the 110V alternative, and L6-20
    // breakouts add L6-20 -> panel tails per circuit.
    // `connector` is the bare connector name for labeling - the sticker goes
    // on the tail, and the tail is a True1, not a "Soca → True1".
    //
    // `boxSize` is how many circuits ONE physical box of this breakout
    // holds - the fan the tails hang off. A soca is six; the L21-30
    // breakout is a 3-circuit box (one 208V circuit per leg pair off a
    // 30A/leg L21-30 feed, user-specified), so its `feedLegA` carries the
    // feed's per-leg rating for the dock's over check. Everything that
    // segments circuits into boxes, deals tails or maps tails onto legs
    // reads the size through socaBoxSize below, never the literal 6.
    getPowerBreakoutTypes() {
        return [
            { id: 'soca-true1', name: 'Multi → True1', connector: 'True1', boxSize: 6, breakoutItem: 'Multi breakouts → True1' },
            { id: 'soca-powercon', name: 'Multi → powerCON', connector: 'powerCON', boxSize: 6, breakoutItem: 'Multi breakouts → powerCON' },
            { id: 'soca-edison', name: 'Multi → Edison (110V)', connector: 'Edison', boxSize: 6, breakoutItem: 'Multi breakouts → Edison', tailItem: 'Edison → panels' },
            { id: 'soca-l620', name: 'Multi → L6-20', connector: 'L6-20', boxSize: 6, breakoutItem: 'Multi breakouts → L6-20', tailItem: 'L6-20 → panels' },
            // The L21-30 breakout (user ruling, 2026-08-28): fed by an
            // L21-30 at 30 A per leg, splitting to 3 x 208V circuits on
            // True1 or powerCON - a leg-PAIR circuit per tail, never a
            // 6-circuit soca. It hangs on a distro number like a multi
            // does, with 3 tails.
            { id: 'l2130-true1', name: 'L21-30 (3 × 208V) → True1', connector: 'True1', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → True1' },
            { id: 'l2130-powercon', name: 'L21-30 (3 × 208V) → powerCON', connector: 'powerCON', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → powerCON' }
        ];
    }

    getPowerBreakout(layer) {
        const types = this.getPowerBreakoutTypes();
        const stored = types.find(t => t.id === (layer && layer.powerBreakoutType));
        if (stored) return stored;
        // No stored choice: a 110V screen defaults to its only legal
        // breakout (user ruling: a 110V screen can only have 110V Edison
        // on it). A stored choice is somebody's paperwork and stands as
        // written, whatever the voltage says now.
        const v = parseFloat(layer && layer.powerVoltage) || 0;
        if (v > 0 && v <= 120) {
            return types.find(t => t.id === 'soca-edison') || types[0];
        }
        return types[0];
    }

    // How many circuits one physical box on THIS screen holds. The one
    // authority for the box shape - segmentation, tail clamps, the balance
    // search, the leg maps and the dock's chip grid all read it, so a
    // 3-tail L21-30 box can never render six chips or deal a tail 4.
    socaBoxSize(layer) {
        const n = Number(this.getPowerBreakout(layer).boxSize);
        return Number.isFinite(n) && n >= 1 ? n : 6;
    }

    // Which breakouts a screen's voltage can legally run (user ruling: a
    // screen set to 110V can only have 110V Edison on it, and the L21-30
    // box is documented as 3 x 208V - nothing else is restricted, and no
    // rule is extrapolated to voltages the ruling does not cover). The
    // select disables what is ineligible; a STORED incompatible choice is
    // somebody's paperwork and keeps displaying, the same doctrine the
    // mismatched phasing scheme follows.
    _breakoutEligible(type, voltage) {
        const v = parseFloat(voltage) || 0;
        if (v > 0 && v <= 120) return type.id === 'soca-edison';
        if (String(type.id).startsWith('l2130-')) return v === 208;
        return true;
    }

    setPowerBreakout(layer, id) {
        if (!layer) return;
        layer.powerBreakoutType = id;
        this.updateLayers([layer], true, 'Change Power Breakout');
    }

    // ---- distro outputs -----------------------------------------------------
    //
    // The connector TYPES a distro can hand a screen (user ruling,
    // 2026-08-31: types only, no counts - the rating already bounds the
    // service and the LEGS line already says where it is). Each type names
    // the screen breakouts it can feed, and that table IS the matching
    // rule: a Soca 208 lands on a Multi -> True1 / powerCON screen, a Soca
    // 120 on an Edison screen, an L21-30 on an L21-30 box. Nothing is
    // extrapolated past the table - a breakout no type names (L6-20) is a
    // mismatch like any other, refused with the fix said out loud, never
    // silently re-typed. `faces` are the breakout connectors the popover
    // row shows beside the type; `badge` is the bracket's text sub-pill.
    //
    // Each type also carries the BOX SHAPE its breakouts share - `boxSize`
    // (six circuits on a soca, three on an L21-30) and `feedLegA` (the
    // L21-30 feed's per-leg rating) - read off the breakout table above,
    // never restated, so a box typed by its chip and a box typed by its
    // occupants' breakout answer to the one authority (2026-09-05, the
    // type moved onto the box: "when a new Multi/group of circuits is
    // where the port type should be moved to").
    getDistroOutputTypes() {
        const bts = this.getPowerBreakoutTypes();
        const shape = (ids) => {
            const m = bts.filter(b => ids.includes(b.id));
            return {
                boxSize: m.length
                    ? Math.min(...m.map(b => Number(b.boxSize) || 6)) : 6,
                feedLegA: Math.max(0, ...m.map(b => Number(b.feedLegA) || 0)),
            };
        };
        return [
            { id: 'soca208', name: 'Soca 208', sub: 'True1 / powerCON',
              glyph: 'soca', faces: ['true1', 'powercon'],
              breakouts: ['soca-true1', 'soca-powercon'], badge: 'SOCA 208' },
            { id: 'soca120', name: 'Soca 120', sub: 'Edison',
              glyph: 'soca', faces: ['edison'],
              breakouts: ['soca-edison'], badge: 'SOCA 120' },
            { id: 'l2130', name: 'L21-30', sub: '3 × 208V',
              glyph: 'l2130', faces: ['true1', 'powercon'],
              breakouts: ['l2130-true1', 'l2130-powercon'], badge: 'L21-30' },
        ].map(t => Object.assign(t, shape(t.breakouts)));
    }

    // What one distro offers, as type records, in catalog order. No
    // `outputs` key - every file from before the key existed, and a
    // freshly added distro - reads as "offers everything", so nothing an
    // older show could drag stops dragging. An explicit list, the empty
    // one included, is somebody's paperwork and stands as written.
    distroOutputs(d) {
        const types = this.getDistroOutputTypes();
        if (!d || !Array.isArray(d.outputs)) return types;
        return types.filter(t => d.outputs.includes(t.id));
    }

    distroOffers(d, typeId) {
        return this.distroOutputs(d).some(t => t.id === typeId);
    }

    // ---- box types: the connector a MULTI BOX is -------------------------
    //
    // The type lives on the box as well as on the distro's OUTPUTS row
    // (user, 2026-09-05: "the soca, l21 and what not is a bit silly on the
    // distro. when a new Multi/group of circuits is where the port type
    // should be moved to you know?" - and, asked where it gets picked,
    // "Type chip on the spare box ... or both places rather"). Stored as
    // `distro.boxTypes = { [number]: typeId }`; the server round-trips a
    // distro as an opaque record (routes_project.py merges the payload
    // wholesale), so no allow-list to extend.
    //
    // THE CONTRACT - distroBoxType(d, number, members?) resolves ONE type
    // for a box, in this order, and says which rung it came from:
    //   1. stored     - boxTypes[number] names a catalog type
    //   2. members    - an occupied box reads the type its members'
    //                   breakout implies, the smallest-fan member deciding
    //                   when they disagree (_resolveSharedSocas' rule), so
    //                   every file from before boxTypes existed reads right
    //   3. neighbour  - a box with nothing on it follows the distro's
    //                   other boxes: the nearest lower-numbered box that
    //                   resolves by rung 1 or 2 (else the nearest higher),
    //                   so a spare on an Edison distro is Edison and never
    //                   needs retyping show after show
    //   4. offered    - the first type the distro offers
    //   5. default    - Soca 208, when the distro offers nothing yet
    // Returns { type, source, implied, clash }: `implied` is rung 2's
    // reading whenever the box is occupied (null when no member's breakout
    // is named by the table), and `clash` is true when a STORED type
    // contradicts it - the stored type still stands (it is somebody's
    // paperwork, never silently overridden) and the dock warns.
    // `members` is _distroMultiNumbers' record for the number; passed in
    // by callers that already hold it, looked up otherwise.
    distroBoxType(d, number, members) {
        const types = this.getDistroOutputTypes();
        const n = parseInt(number, 10);
        const list = Array.isArray(members) ? members
            : (d ? (this._distroMultiNumbers(d.id).get(n) || []) : []);
        let implied = null;
        for (const m of list) {
            const l = ((this.project && this.project.layers) || [])
                .find(x => x.id === m.layerId);
            const t = l ? this.outputTypeForBreakout(this.getPowerBreakout(l))
                : null;
            if (t && (!implied || t.boxSize < implied.boxSize)) implied = t;
        }
        const stored = this.distroStoredBoxType(d, n);
        if (stored) {
            return { type: stored, source: 'stored', implied,
                     clash: !!(implied && implied.id !== stored.id) };
        }
        if (implied) {
            return { type: implied, source: 'members', implied, clash: false };
        }
        const neighbour = this._distroNeighbourBoxType(d, n);
        if (neighbour) {
            return { type: neighbour, source: 'neighbour', implied: null,
                     clash: false };
        }
        const offered = this.distroOutputs(d);
        if (offered.length) {
            return { type: offered[0], source: 'offered', implied: null,
                     clash: false };
        }
        return { type: types[0], source: 'default', implied: null,
                 clash: false };
    }

    // Rung 3: what the distro's OTHER boxes are. Only boxes that settle by
    // rung 1 or 2 (a stored type, or members whose breakout names one)
    // count - a memberless untyped box has nothing to say and asking it
    // would ask this question again. The nearest lower number wins (the
    // box before this one), else the nearest higher; null when the distro
    // has no settled box at all.
    _distroNeighbourBoxType(d, number) {
        if (!d) return null;
        const n = parseInt(number, 10);
        const numbers = new Set();
        for (const k of Object.keys(d.boxTypes || {})) numbers.add(parseInt(k, 10));
        for (const k of this._distroMultiNumbers(d.id).keys()) numbers.add(k);
        const settled = [...numbers]
            .filter(k => Number.isFinite(k) && k !== n)
            .map(k => {
                const stored = this.distroStoredBoxType(d, k);
                if (stored) return { k, type: stored };
                const r = this.distroBoxType(d, k);
                return r.source === 'members' ? { k, type: r.type } : null;
            })
            .filter(Boolean);
        if (!settled.length) return null;
        const lower = settled.filter(s => s.k < n).sort((a, b) => b.k - a.k);
        if (lower.length) return lower[0].type;
        return settled.sort((a, b) => a.k - b.k)[0].type;
    }

    // Rung 1 alone: the stored type of box `number`, or null. Reads no
    // member and touches no naming cache, so it is safe from inside the
    // cache's own build.
    distroStoredBoxType(d, number) {
        const map = d && d.boxTypes;
        if (!map || typeof map !== 'object') return null;
        const id = map[parseInt(number, 10)];
        return this.getDistroOutputTypes().find(t => t.id === id) || null;
    }

    // The chip's pick: ONE 'Set Multi Type' entry. A null type forgets the
    // box's stored type (it falls back down the rungs).
    setDistroBoxType(distroId, number, typeId) {
        const d = this.getDistros().find(x => x.id === distroId);
        if (!d) return null;
        const map = Object.assign({}, d.boxTypes || {});
        map[parseInt(number, 10)] = typeId || null;
        return this.updateDistro(distroId, { boxTypes: map }, 'Set Multi Type');
    }

    // The drop's stamp: a plug drop, or a typed spare box's drop, records
    // the type of the box it makes WITHOUT an entry of its own - it runs
    // before the assignment's own saveState, so the gesture stays one
    // undo step and one Ctrl+Z forgets the type with the assignment.
    _stampBoxType(distroId, number, typeId) {
        const d = this.getDistros().find(x => x.id === distroId);
        const n = parseInt(number, 10);
        if (!d || !Number.isFinite(n) || n < 1) return;
        if (!this.getDistroOutputTypes().some(t => t.id === typeId)) return;
        if (!d.boxTypes || typeof d.boxTypes !== 'object') d.boxTypes = {};
        if (d.boxTypes[n] === typeId) return;
        d.boxTypes[n] = typeId;
        this._persistDistros();
    }

    // The output type a screen's (effective) breakout takes, or null for a
    // breakout the table does not name.
    outputTypeForBreakout(bt) {
        const id = bt && bt.id;
        return this.getDistroOutputTypes()
            .find(t => t.breakouts.includes(id)) || null;
    }

    // ---- per-circuit cables: the 10' True1 on circuit 1 ------------------
    //
    // "we need to be able to add cables to each circuit on the distro
    // besides just soca length or l620 length etc. like say circuit 1
    // needs a 10ft true 1 and circuit 2 needs 6ft and 3/4 need nothing and
    // 5 needs 6ft and 6 needs a 10 ft. since we are going to have those
    // pdf docs we need to be able to have that info if i want to add it."
    // (user, 2026-09-06). For ONE circuit of ONE screen an optional cable
    // is a length in feet plus a connector, stored per screen and keyed
    // by circuit number the way powerLabelOverrides is:
    //     layer.powerCircuitCables = { [circuitNum]: { ft, connector } }
    // `connector` null means "follows the box" - the connector the
    // circuit's box breaks out to (True1 on a Soca 208 feeding a True1
    // screen, Edison on a Soca 120, the L21-30 breakout's own tail
    // connector) - so most of the time only a length gets typed. No entry
    // means no cable. A cleared circuit, multi or distro forgets its
    // cables with its label overrides: cables are programming.

    // The connectors a cable can be typed as - the breakout table's own
    // connector names, once each, in table order. Ids are the plug chips'
    // face ids (true1 / powercon / edison / l620), so the select's value
    // and the OUTPUTS row's faces name the same thing.
    getPowerCableConnectors() {
        const seen = new Set();
        const out = [];
        this.getPowerBreakoutTypes().forEach(bt => {
            const id = this._cableConnectorId(bt.connector);
            if (!id || seen.has(id)) return;
            seen.add(id);
            out.push({ id, name: bt.connector });
        });
        return out;
    }

    _cableConnectorId(name) {
        return String(name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    cableConnectorName(id) {
        const hit = this.getPowerCableConnectors().find(c => c.id === id);
        return hit ? hit.name : null;
    }

    // The connector a box's tails break out to: the box's resolved type
    // (distroBoxType - stored, members, neighbour, offered) names the
    // breakouts it feeds, and the holder screen's own breakout picks among
    // them (a Soca 208 feeds True1 OR powerCON; the screen says which);
    // a box nobody holds, or a screen whose breakout the box does not
    // name, reads the type's first breakout. Off any distro the screen's
    // own breakout is the whole answer. Returns a connector id.
    boxTailConnector(d, number, layer) {
        const bts = this.getPowerBreakoutTypes();
        const own = layer ? this.getPowerBreakout(layer) : null;
        if (!d) {
            return this._cableConnectorId((own || bts[0]).connector);
        }
        const type = this.distroBoxType(d, number).type;
        const ids = (type && type.breakouts) || [];
        const pick = (own && ids.includes(own.id))
            ? own
            : bts.find(b => ids.includes(b.id)) || own || bts[0];
        return this._cableConnectorId(pick.connector);
    }

    // Where one circuit of a screen sits: its multi's stable index, the
    // distro record (null off any distro) and the box number - read off
    // the naming index, the one authority for which box a circuit is on.
    _circuitBox(layer, circuitNum) {
        const nm = this._powerNaming(layer);
        const slot = nm.slots.get(parseInt(circuitNum, 10));
        if (!slot) return { idx: null, d: null, number: null };
        const idx = slot.multi;
        const distroId = (layer.powerSocaDistro || {})[idx] || null;
        const d = distroId
            ? this.getDistros().find(x => x.id === distroId) || null : null;
        return { idx, d, number: slot.number };
    }

    // The stored cable on one circuit, resolved for printing: null when
    // the circuit has none, else { ft, connector (the stored id or null),
    // id (the id in force), name, text } - text is what the chip corner,
    // the canvas tag and the paperwork all print ("10' True1").
    powerCircuitCable(layer, circuitNum) {
        const store = layer && layer.powerCircuitCables;
        const rec = store && store[circuitNum];
        const ft = rec ? Number(rec.ft) : NaN;
        if (!rec || !Number.isFinite(ft) || ft <= 0) return null;
        let id = rec.connector && this.cableConnectorName(rec.connector)
            ? rec.connector : null;
        if (!id) {
            const box = this._circuitBox(layer, circuitNum);
            id = this.boxTailConnector(box.d, box.number, layer);
        }
        const name = this.cableConnectorName(id) || '';
        return {
            ft, connector: rec.connector || null, id, name,
            text: this.cableText(ft, name),
        };
    }

    cableText(ft, name) {
        const n = Number(ft);
        const len = Number.isInteger(n) ? String(n) : String(+n.toFixed(1));
        return `${len}'${name ? ` ${name}` : ''}`;
    }

    // Write one circuit's cable. `cable` is { ft, connector } - a blank or
    // zero length forgets the entry (no cable), a null connector follows
    // the box. `record` false is the sheet's quick-fill, which issues ONE
    // updateLayers over every layer it touched itself, so a fill is one
    // undo step the way a length commit is.
    setCircuitCable(layer, circuitNum, cable, record = true) {
        if (!layer) return false;
        const store = layer.powerCircuitCables
            || (layer.powerCircuitCables = {});
        const ft = cable ? Number(cable.ft) : NaN;
        const before = JSON.stringify(store[circuitNum] || null);
        if (!Number.isFinite(ft) || ft <= 0) {
            delete store[circuitNum];
        } else {
            const connector = cable.connector
                && this.cableConnectorName(cable.connector)
                ? cable.connector : null;
            store[circuitNum] = { ft, connector };
        }
        const changed = JSON.stringify(store[circuitNum] || null) !== before;
        if (record && changed) {
            this.updateLayers([layer], true, 'Set Circuit Cable');
        }
        return changed;
    }

    // How a refusal names the screen's breakout - "set to L21-30", "set to
    // Edison (110V)" - the connector the box is set to, said the way the
    // crew says it.
    _breakoutShortName(bt) {
        if (!bt) return 'an unknown breakout';
        if (String(bt.id).startsWith('l2130-')) return 'L21-30';
        if (bt.id === 'soca-edison') return 'Edison (110V)';
        return bt.name;
    }

    // The five connector FACES - what a hand sees reaching for the box:
    // soca (19-pin round multi), True1 (keyed round, three contacts),
    // powerCON (round with the locking tab), Edison (two slots, ground
    // below), L21-30 (twist-lock, five curved slots). One <symbol> sprite
    // on the body; every chip, popover row and drag pill references a face
    // through plugGlyph, so the same five faces show everywhere.
    _ensurePlugGlyphs() {
        if (document.getElementById('hw-plug-glyphs')) return;
        const host = document.createElement('div');
        host.innerHTML = '<svg id="hw-plug-glyphs" width="0" height="0" '
            + 'style="position:absolute" aria-hidden="true"><defs>'
            + '<symbol id="hw-g-soca" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/>'
            + '<circle class="pin" cx="12" cy="12" r="1"/><g class="pin">'
            + '<circle cx="12" cy="8" r=".9"/><circle cx="15.5" cy="10" r=".9"/>'
            + '<circle cx="15.5" cy="14" r=".9"/><circle cx="12" cy="16" r=".9"/>'
            + '<circle cx="8.5" cy="14" r=".9"/><circle cx="8.5" cy="10" r=".9"/>'
            + '<circle cx="12" cy="4.6" r=".8"/><circle cx="15.7" cy="5.6" r=".8"/>'
            + '<circle cx="18.4" cy="8.3" r=".8"/><circle cx="19.4" cy="12" r=".8"/>'
            + '<circle cx="18.4" cy="15.7" r=".8"/><circle cx="15.7" cy="18.4" r=".8"/>'
            + '<circle cx="12" cy="19.4" r=".8"/><circle cx="8.3" cy="18.4" r=".8"/>'
            + '<circle cx="5.6" cy="15.7" r=".8"/><circle cx="4.6" cy="12" r=".8"/>'
            + '<circle cx="5.6" cy="8.3" r=".8"/><circle cx="8.3" cy="5.6" r=".8"/>'
            + '</g></symbol>'
            + '<symbol id="hw-g-true1" viewBox="0 0 24 24">'
            + '<path d="M7 3.6 H17 A10 10 0 1 1 7 3.6 Z"/>'
            + '<rect class="pin" x="10.6" y="3" width="2.8" height="2.2" rx=".4"/>'
            + '<rect class="pin" x="7.2" y="10" width="2.2" height="5" rx=".6"/>'
            + '<rect class="pin" x="14.6" y="10" width="2.2" height="5" rx=".6"/>'
            + '<rect class="pin" x="10.9" y="14.8" width="2.2" height="4" rx=".6"/>'
            + '</symbol>'
            + '<symbol id="hw-g-powercon" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="9.8"/><path d="M17.6 4.4 l2.6 -2.2"/>'
            + '<rect class="pin" x="11" y="5.2" width="2" height="4.6" rx=".5"/>'
            + '<rect class="pin" x="6.2" y="13.2" width="2" height="4.6" rx=".5" '
            + 'transform="rotate(30 7.2 15.5)"/>'
            + '<rect class="pin" x="15.8" y="13.2" width="2" height="4.6" rx=".5" '
            + 'transform="rotate(-30 16.8 15.5)"/>'
            + '</symbol>'
            + '<symbol id="hw-g-edison" viewBox="0 0 24 24">'
            + '<rect x="3" y="3" width="18" height="18" rx="4"/>'
            + '<rect class="pin" x="7" y="7" width="2.2" height="6" rx=".5"/>'
            + '<rect class="pin" x="14.8" y="7.8" width="2.2" height="5.2" rx=".5"/>'
            + '<path class="pin" d="M10.2 17.8 v-2 a1.8 1.8 0 0 1 3.6 0 v2 z"/>'
            + '</symbol>'
            + '<symbol id="hw-g-l2130" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/><circle cx="12" cy="12" r="1.2"/>'
            + '<g stroke-width="2.4" stroke-linecap="round" fill="none">'
            + '<path d="M11 5.4 a6.8 6.8 0 0 1 2.2 0"/>'
            + '<path d="M17.7 9.3 a6.8 6.8 0 0 1 .8 2.2"/>'
            + '<path d="M16.9 16.6 a6.8 6.8 0 0 1 -1.7 1.5"/>'
            + '<path d="M8.8 18.1 a6.8 6.8 0 0 1 -1.7 -1.5"/>'
            + '<path d="M5.5 11.5 a6.8 6.8 0 0 1 .8 -2.2"/>'
            + '</g></symbol>'
            + '</defs></svg>';
        document.body.appendChild(host.firstChild);
    }

    plugGlyph(id, cls) {
        this._ensurePlugGlyphs();
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('class', 'hw-plug-g' + (cls ? ` ${cls}` : ''));
        const use = document.createElementNS(ns, 'use');
        use.setAttribute('href', `#hw-g-${id}`);
        svg.appendChild(use);
        return svg;
    }

    // ---- distros / circuit groups -------------------------------------------

    // A distro is a project-level power source with its own rating, voltage
    // and phase. Socas (multis) are assigned to one, so load rolls up
    // circuits -> soca -> distro across every screen it feeds. Load is summed
    // as WATTS (the invariant) and only converted to amps at the distro's own
    // voltage/phase - 3-phase per I = P / (V x 1.73).
    getDistros() {
        if (!this.project) return [];
        if (!this.project.distros) this.project.distros = [];
        return this.project.distros;
    }

    // Serialized: two rapid fire-and-forget project POSTs can complete out of
    // order, and the server merges whatever lands last - so an older payload
    // could drop a just-added distro. Chain them instead (same reason the
    // rack allocation pushes are queued).
    _persistDistros() {
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ distros: this.getDistros() })
        }).catch(() => {});
        this._distroPushQueue = (this._distroPushQueue || Promise.resolve()).then(send);
        return this._distroPushQueue;
    }

    addDistro(opts = {}) {
        const list = this.getDistros();
        const n = list.reduce((m, d) => Math.max(m, Number(String(d.id).replace('d', '')) || 0), 0) + 1;
        const d = {
            id: 'd' + n,
            name: opts.name || `DISTRO ${n}`,
            ratingA: Number(opts.ratingA) || 400,
            voltage: Number(opts.voltage) || 208,
            phase: Number(opts.phase) === 1 ? 1 : 3
        };
        list.push(d);
        // Adding a distro adds a bucket the numbering runs over, and its name
        // is what the multis landing on it will be called.
        this._circuitTailCache = null;
        // Distros live on the PROJECT, and the history snapshot is the whole
        // project - so the same saveState every layer edit takes covers them,
        // and undo's project PUT restores them (restore_project replaces
        // current_project wholesale). Post-mutation, like every other action.
        this.saveState('Add Distro');
        this._persistDistros();
        return d;
    }

    updateDistro(id, patch = {}, action = 'Edit Distro') {
        const d = this.getDistros().find(x => x.id === id);
        if (!d) return null;
        if (patch.name !== undefined) d.name = String(patch.name).trim() || d.name;
        if (patch.ratingA !== undefined) d.ratingA = Number(patch.ratingA) || d.ratingA;
        if (patch.voltage !== undefined) d.voltage = Number(patch.voltage) || d.voltage;
        if (patch.phase !== undefined) d.phase = Number(patch.phase) === 1 ? 1 : 3;
        if (patch.phasing !== undefined) d.phasing = patch.phasing || null;
        // Where the box physically sits - the dimmer beach, stage left
        // world. Prints on every power label that names this distro.
        if (patch.location !== undefined) d.location = String(patch.location).trim() || null;
        // The connector types it offers (the ⚙ OUTPUTS checklist). Stored
        // in catalog order, unknown ids dropped; null forgets the key,
        // which reads as "offers everything" again (distroOutputs).
        if (patch.outputs !== undefined) {
            if (Array.isArray(patch.outputs)) {
                const want = patch.outputs.map(String);
                d.outputs = this.getDistroOutputTypes()
                    .map(t => t.id).filter(id => want.includes(id));
            } else {
                delete d.outputs;
            }
        }
        // The type each numbered box IS (distroBoxType). Stored as a clean
        // { number: typeId } map - non-numbers and unknown ids dropped, a
        // null entry forgetting that box's type; an emptied map forgets
        // the key, so a file never carries `boxTypes: {}`.
        if (patch.boxTypes !== undefined) {
            const src = patch.boxTypes;
            const known = new Set(this.getDistroOutputTypes().map(t => t.id));
            const clean = {};
            if (src && typeof src === 'object') {
                Object.keys(src).forEach(k => {
                    const n = parseInt(k, 10);
                    if (Number.isFinite(n) && n >= 1 && known.has(src[k])) {
                        clean[n] = src[k];
                    }
                });
            }
            if (Object.keys(clean).length) d.boxTypes = clean;
            else delete d.boxTypes;
        }
        // The NAME is a label input: every multi following this distro is
        // renamed by it, and so is every circuit hanging off those multis.
        // (Location is not - it is descriptive and names nothing.)
        this._circuitTailCache = null;
        // One entry per committed field (these fire on change, not per
        // keystroke), same as the other discrete label edits - under the
        // caller's name where the field has one of its own (the box type
        // chip's 'Set Multi Type').
        this.saveState(action || 'Edit Distro');
        this._persistDistros();
        return d;
    }

    removeDistro(id) {
        const list = this.getDistros();
        const i = list.findIndex(x => x.id === id);
        if (i === -1) return false;
        list.splice(i, 1);
        // orphaned soca assignments fall back to unassigned
        const touched = [];
        for (const layer of this.project.layers || []) {
            const map = layer.powerSocaDistro;
            if (!map) continue;
            let changed = false;
            for (const k of Object.keys(map)) if (map[k] === id) { delete map[k]; changed = true; }
            if (changed) touched.push(layer);
        }
        if (touched.length) this.updateLayers(touched);
        // The orphaned multis fall back into the unassigned bucket, which
        // renumbers it and everything after it.
        this._circuitTailCache = null;
        // ONE entry for the removal AND the orphaning it caused, taken after
        // both so a single Ctrl+Z brings the distro back with its multis
        // still assigned to it - not a distro with its feeds cut loose.
        this.saveState('Remove Distro');
        this._persistDistros();
        return true;
    }

    // `socaIndex` is the multi's stable index within its screen, never its
    // displayed number - the number is what this call CHANGES, since it comes
    // out of the distro's own sequence.
    // `record` (default true) is for composite gestures only: a dock drop
    // that drives this setter alongside others passes false and issues ONE
    // updateLayers(..., true, action) itself over every returned layer, so
    // the whole drop is one undo entry. Returns the touched layers either way.
    setSocaDistro(layer, socaIndex, distroId, record = true) {
        if (!layer) return [];
        const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
        // A multi that carries its pin onto another distro can land on an
        // occupied box there - the same join as pinning, spelled as an
        // assignment - so the incumbents on the target box hold their
        // rendered tails the same way.
        const pin = parseInt((layer.powerSocaNumber || {})[socaIndex], 10);
        const stamped = (distroId && Number.isFinite(pin) && pin >= 1)
            ? this._materializeSocaBox(distroId, pin, layer, socaIndex)
            : [];
        if (distroId) map[socaIndex] = distroId; else delete map[socaIndex];
        // Assignment renumbers both buckets it touches, so every label on the
        // show can move. Stale labels for a frame is a bug this has already
        // been bitten by once.
        this._circuitTailCache = null;
        const touched = [...new Set([layer, ...stamped])];
        if (record) {
            this.updateLayers(touched, true, 'Assign Multi Distro');
        }
        return touched;
    }

    // Pin a multi to a NUMBER under its distro - the "which output of the
    // box am I plugged into" choice. Auto (no entry) numbers exactly as
    // always: per distro, layer order, dealing around every pinned slot.
    //
    // The pin is also how one PHYSICAL soca serves two screens: two multis
    // pinned to the same (distro, number) ARE one box, and the second
    // screen's circuits land on the box's next free tails - the shape the
    // user used to build by hand-typing powerLabelOverrides (C2-3-4..6)
    // onto a twin multi that the rollup then counted twice. There is no
    // separate link to manage: picking the number joins, re-picking (or
    // Auto, or another distro) separates.
    // `record` mirrors setSocaDistro's: false lets a composite dock gesture
    // fold this write into its own single history entry.
    setSocaNumber(layer, socaIndex, number, record = true) {
        if (!layer) return [];
        // Always leave an object behind, never delete the property: an
        // absent key is missing from the update payload and the server
        // keeps whatever it had, so "back to Auto" would silently not clear.
        const store = layer.powerSocaNumber || (layer.powerSocaNumber = {});
        const n = parseInt(number, 10);
        // Landing on an occupied box is the JOIN, and the incumbents keep
        // the tails they were rendering: stamp them before the pin so the
        // joiner deals into what is genuinely free. Un-pinning (Auto) is
        // the leave - nobody's tails move, so there is nothing to stamp.
        const stamped = (Number.isFinite(n) && n >= 1)
            ? this._materializeSocaBox(
                (layer.powerSocaDistro || {})[socaIndex], n, layer, socaIndex)
            : [];
        if (Number.isFinite(n) && n >= 1) store[socaIndex] = n;
        else delete store[socaIndex];
        // A pin renumbers the whole distro bucket (autos deal around it) and
        // can merge or split a shared box, so every label can move.
        this._circuitTailCache = null;
        const touched = [...new Set([layer, ...stamped])];
        if (record) {
            this.updateLayers(touched, true, 'Set Multi Number');
        }
        return touched;
    }

    // The shared-box record for one multi, or null when it shares with
    // nobody. Non-null only for a PINNED multi whose (distro, number) is
    // claimed by at least one other multi - see _resolveSharedSocas for the
    // fields. This is what the soca tiles, the rollup and the balancer read,
    // so "is this one box or two" has exactly one answer.
    getSocaShare(layer, socaIndex) {
        if (!layer) return null;
        const idx = Number(socaIndex);
        if (!((layer.powerSocaDistro || {})[idx])) return null;
        const n = parseInt((layer.powerSocaNumber || {})[idx], 10);
        if (!Number.isFinite(n) || n < 1) return null;
        const rec = this._powerNaming(layer).socas.get(idx);
        return (rec && rec.share) || null;
    }

    // What was SHOWING becomes HELD - the pin philosophy applied to tails.
    // Called by every gesture that lands a multi on box (distroId, number)
    // - a pin, a re-assignment carrying a pin, a split or un-split of a
    // member - BEFORE the gesture mutates anything, while "current tails"
    // still means what the wall shows today. Each multi already on the box
    // (the incumbents) gets its rendered tails stamped into its own
    // powerSocaPhasePos, so the joiner deals into the tails that are
    // actually free and never renumbers a wall someone may have already
    // cabled. A member that already holds a stored set is already law and
    // is left alone; a rendering the fan cannot hold (an overflowed box)
    // is not an arrangement worth freezing. Returns the layers stamped so
    // the caller's updateLayers carries them - the incumbents can live on
    // other screens than the joiner.
    _materializeSocaBox(distroId, number, exceptLayer, exceptSoca) {
        const touched = [];
        const n = parseInt(number, 10);
        if (!distroId || !Number.isFinite(n) || n < 1) return touched;
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                // Only a PIN holds a slot against the joiner: an auto at
                // this number re-deals around the new pin and keeps its
                // own box, so it has nothing to defend.
                if (!rec.pinned) continue;
                if (rec.distroId !== distroId || rec.number !== n) continue;
                if (l === exceptLayer && rec.index === Number(exceptSoca)) continue;
                const store = l.powerSocaPhasePos || (l.powerSocaPhasePos = {});
                if (Array.isArray(store[rec.index])) continue;
                const L = rec.circuits.length;
                const pos = rec.positions;
                const cap = this.socaBoxSize(l);
                if (!Array.isArray(pos) || pos.length !== L) continue;
                if (!pos.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
                    || new Set(pos).size !== L) continue;
                store[rec.index] = pos.slice();
                touched.push(l);
            }
        }
        return touched;
    }

    // Every multi number in use on one distro, show-wide:
    // number -> [{layerId, layerName, soca, legs, pinned}]. The number
    // select prints this so a tech picking a slot can see who is already on
    // it - picking an occupied number is the combine gesture, and it should
    // read that way before the click, not after.
    _distroMultiNumbers(distroId) {
        const out = new Map();
        if (!distroId) return out;
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                if (rec.distroId !== distroId) continue;
                const arr = out.get(rec.number) || [];
                arr.push({ layerId: l.id, layerName: l.name, soca: rec.index,
                           legs: rec.circuits.length, pinned: !!rec.pinned });
                out.set(rec.number, arr);
            }
        }
        return out;
    }

    // Other multis on this multi's distro that DISPLAY the same name while
    // sitting on a DIFFERENT number. Same name on the same number IS the
    // shared-box gesture; the same name across two numbers is two labels
    // claiming one box on paper while the patch says two boxes - never
    // intentional now that sharing is a pin. Flagged on the tiles, never
    // blocked: the fix is either pinning both to one number (one box) or
    // renaming one (two boxes), and that is the user's call.
    _socaNameCollisions(layer, socaIndex) {
        if (!layer) return [];
        const rec = this._powerNaming(layer).socas.get(Number(socaIndex));
        if (!rec || !rec.distroId || !rec.name) return [];
        const out = [];
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const other of this._powerNaming(l).socas.values()) {
                if (l.id === layer.id && other.index === rec.index) continue;
                if (other.distroId !== rec.distroId) continue;
                if (other.number === rec.number) continue;
                if (String(other.name) !== String(rec.name)) continue;
                out.push({ layerName: l.name, number: other.number });
            }
        }
        return out;
    }

    // "4-6" for [4,5,6], "1-3, 5" for [1,2,3,5] - the way a tail set is
    // said out loud on a tile face.
    _fmtTails(tails) {
        const t = (tails || []).slice().sort((a, b) => a - b);
        if (!t.length) return '';
        const runs = [[t[0], t[0]]];
        for (let i = 1; i < t.length; i++) {
            if (t[i] === runs[runs.length - 1][1] + 1) runs[runs.length - 1][1] = t[i];
            else runs.push([t[i], t[i]]);
        }
        return runs.map(([a, b]) => a === b ? `${a}` : `${a}-${b}`).join(', ');
    }

    // A multi named by hand. Per-MULTI, so unlike the bracket toggle and the
    // breakout type it never sweeps the selection (_socaPanelTargets): a name
    // belongs to one multi on one screen. Blank hands it back to the distro.
    // `record` mirrors setSocaDistro's: false lets a composite gesture (the
    // dock's one-field-per-box header writing through to every member of a
    // shared box) fold this write into its own single history entry.
    setSocaName(layer, socaIndex, name, record = true) {
        if (!layer) return;
        // Always leave an object behind, never delete the property: an absent
        // key is simply missing from the update payload and the server keeps
        // whatever it had, so "clear this" would silently not clear.
        const store = layer.powerSocaNames || (layer.powerSocaNames = {});
        const v = String(name || '').trim();
        if (v) store[socaIndex] = v; else delete store[socaIndex];
        this._circuitTailCache = null;
        if (record) {
            this.updateLayers([layer], true, 'Rename Multi');
        }
    }

    // Every PARTLY-FILLED multi that lands on a 3-phase distro, with the
    // tail set it currently occupies. The unit of balancing is the multi,
    // so this is what the balancer searches over. Full multis are excluded:
    // under the wall-order rule the only lever is WHICH tails a multi uses,
    // and a 6-circuit multi uses all six - there is nothing to choose.
    //
    // `distroId` scopes the walk to one distro. Balancing is per distro now
    // (each Balance button lives on its distro's row): legs never interact
    // across services, so a show-wide pass was only ever N independent
    // problems solved at once - and it moved multis on distros the user was
    // not looking at. No argument keeps the show-wide walk for the callers
    // that genuinely want every distro (clearPhaseBalance's preview, tests).
    _balanceTargets(distroId) {
        const out = [];
        const distros = this.getDistros();
        const seenBoxes = new Set();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of this.getSocaPlan(layer)) {
                const d = distros.find(x => x.id === assign[s.soca]);
                if (!d || d.phase !== 3) continue;
                if (distroId && d.id !== distroId) continue;
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    // A shared box is ONE multi to the balancer: its
                    // used-tail set spans every member, and moving tails
                    // re-deals the whole box - member order (layer order),
                    // ascending within each member, the same rule
                    // _resolveSharedSocas states. Emitted once, at the
                    // first member; a box already in clash or overflow has
                    // no legal arrangement to search, so it is left alone
                    // until the clash is resolved.
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    if (share.clash || share.overflow) continue;
                    const total = share.members.reduce((t, m) => t + m.legs, 0);
                    const members = share.members.map(m => {
                        const ml = (this.project.layers || [])
                            .find(l => l.id === m.layerId);
                        return ml ? { layer: ml, soca: m.soca, legs: m.legs,
                                      tails: m.tails.slice() } : null;
                    }).filter(Boolean);
                    if (members.length !== share.members.length) continue;
                    // Full is full against the BOX's fan - the smallest
                    // member breakout's size, the same capacity the shared
                    // deal answers to. Six for socas, three for an L21-30.
                    const boxSize = Math.min(...members
                        .map(m => this.socaBoxSize(m.layer)));
                    if (total >= boxSize) continue;
                    // per-circuit amps and labels, member order - index k of
                    // from/to below is the k-th circuit of this walk
                    const legsDetail = members.flatMap(m =>
                        (this.getSocaPlan(m.layer)
                            .find(x => x.soca === m.soca) || { legs: [] }).legs);
                    members.forEach(m => {
                        const saved = (m.layer.powerSocaPhasePos || {})[m.soca];
                        m.hadStore = Array.isArray(saved);
                        m.savedStore = m.hadStore ? saved.slice() : null;
                    });
                    out.push({
                        layer, soca: s.soca, name: s.name, distroId: d.id,
                        legs: total, members, boxSize,
                        layerName: members.map(m => m.layer.name).join(' + '),
                        positions: members.flatMap(m => m.tails)
                            .sort((a, b) => a - b),
                        fromFlat: members.flatMap(m => m.tails),
                        amps: legsDetail.map(l => l.amps),
                        labels: legsDetail.map(l => l.label),
                        scheme: this._circuitSchemeFor(d, circuitV).id
                    });
                    continue;
                }
                if (s.legs.length >= this.socaBoxSize(layer)) continue;
                out.push({
                    layer, soca: s.soca, name: s.name, distroId: d.id,
                    legs: s.legs.length,
                    boxSize: this.socaBoxSize(layer),
                    positions: this.socaCircuitPositions(layer, s.soca, s.legs.length),
                    amps: s.legs.map(l => l.amps),
                    // The circuits' CURRENT labels through the one authority,
                    // captured before the search mutates the store - the
                    // balance dialog names each moved circuit by the bubble
                    // on the canvas, never by a re-derived ordinal.
                    labels: s.legs.map(l => l.label),
                    scheme: this._circuitSchemeFor(d, circuitV).id
                });
            }
        }
        return out;
    }

    // Why nothing on this distro is movable, said in the balancer's own
    // terms. The reference show pressed Balance and read silence: the DJ
    // booths' three multis were assigned to C2 but the grouped wall's auto
    // plan errors out, so the multis do not EXIST - and the dialog computed
    // to a no-op without saying why. Every reason a multi is passed over is
    // collected here so the no-targets dialog can state them instead:
    //   full     6-circuit multis (and full shared boxes) - nothing to choose
    //   clashed  shared boxes left alone until their tail clash/overflow is
    //            resolved
    //   phantom  screens whose powerSocaDistro names this distro for a multi
    //            the current circuit plan does not produce - an empty plan
    //            (power error, peer-served member) or one that shrank
    _balanceBlockers(distroId) {
        const out = { full: [], clashed: [], phantom: [] };
        if (!distroId) return out;
        const seenBoxes = new Set();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            for (const s of plan) {
                if (assign[s.soca] !== distroId) continue;
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    // deduped: a box whose members are two multis of ONE
                    // screen should not name the screen twice
                    const names = [...new Set(share.members
                        .map(m => m.layerName))].join(' + ');
                    if (share.clash || share.overflow) {
                        out.clashed.push({ name: s.name, layers: names,
                            overflow: !!share.overflow });
                    } else if (share.members.reduce((t, m) => t + m.legs, 0)
                            >= this.socaBoxSize(layer)) {
                        out.full.push({ name: s.name, layers: names });
                    }
                    continue;
                }
                if (s.legs.length >= this.socaBoxSize(layer)) {
                    out.full.push({ name: s.name, layers: layer.name });
                }
            }
            // Assignments pointing past the plan: the multi the user set up
            // is not in the drawing any more. Say so - this is exactly the
            // state that reads as "balancing won't calculate".
            const have = new Set(plan.map(s => s.soca));
            const missing = Object.keys(assign)
                .filter(k => assign[k] === distroId
                    && !have.has(parseInt(k, 10)));
            if (missing.length) {
                out.phantom.push({
                    layers: layer.name, count: missing.length,
                    reason: plan.length
                        ? 'the circuit plan no longer reaches that multi'
                        : (this._socaPlanEmptyReason(layer)
                            || 'the screen routes no circuits'),
                });
            }
        }
        return out;
    }

    // Deal a shared box's chosen tail SET across its members: ascending
    // tails to members in member order, each member's slice ascending - the
    // box-wide statement of the wall-order rule.
    _dealBoxTails(members, tailSet) {
        const sorted = tailSet.slice().sort((a, b) => a - b);
        let off = 0;
        for (const m of members) {
            const store = m.layer.powerSocaPhasePos
                || (m.layer.powerSocaPhasePos = {});
            store[m.soca] = sorted.slice(off, off + m.legs);
            off += m.legs;
        }
    }

    // Worst imbalance, which is what we minimise - across every 3-phase
    // distro show-wide, or over the one distro a scoped balance is working.
    _worstImbalance(distroId) {
        return this.getDistroLoads()
            .filter(b => b.id && b.legs && (!distroId || b.id === distroId))
            .reduce((m, b) => Math.max(m, b.imbalancePct), 0);
    }

    // Search WHICH tails of the fan each partly-filled multi uses.
    //
    // Wall-order rule: circuits always map to the chosen tails ascending in
    // wall order, so the search space is tail SUBSETS (C(6,L) per multi -
    // at most 20), never permutations. They still multiply across multis, so
    // this is greedy local search: repeatedly try every single-tail change
    // (swap one used tail for a free one, re-sort), keep improvements, stop
    // when nothing helps. Deterministic. Where circuit loads are equal this
    // finds exactly what the old permutation search found - the phase math
    // only sees the subset; where they differ, wall order deliberately wins
    // over the last few percent of imbalance.
    //
    // Nothing is persisted; the project is restored before returning.
    //
    // `distroId` scopes both the targets and the figure being minimised to
    // one distro - the per-distro Balance button's path. Unscoped remains
    // the show-wide search it always was.
    suggestPhaseBalance(distroId) {
        const targets = this._balanceTargets(distroId);
        const before = this._worstImbalance(distroId);
        if (!targets.length) return { before, after: before, targets: [], moves: [], searched: 0 };

        // For a shared box `positions` is the combined tail SET (ascending)
        // and `fromFlat` the member-order walk of the same tails - the
        // search moves the set, the moves report per circuit.
        const original = targets.map(t => (t.fromFlat || t.positions).slice());
        const current = targets.map(t => t.positions.slice());
        const write = () => targets.forEach((t, i) => {
            if (t.members) { this._dealBoxTails(t.members, current[i]); return; }
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            store[t.soca] = current[i].slice();
        });
        let searched = 0;
        const score = () => { write(); searched += 1; return this._worstImbalance(distroId); };

        let best = score();
        for (let pass = 0; pass < 40; pass++) {
            let moved = false;
            for (let t = 0; t < targets.length; t++) {
                const L = current[t].length;
                for (let i = 0; i < L; i++) {
                    // trade the tail at slot i for one nothing is using;
                    // re-sort so the array stays ascending wall order.
                    // The fan is the target's OWN box - six tails on a
                    // soca, three on an L21-30.
                    for (let p = 1; p <= (targets[t].boxSize || 6); p++) {
                        if (current[t].includes(p)) continue;
                        const was = current[t].slice();
                        current[t][i] = p;
                        current[t].sort((x, y) => x - y);
                        const sc = score();
                        if (sc < best - 0.01) { best = sc; moved = true; }
                        else current[t] = was;
                    }
                }
            }
            if (!moved) break;
        }
        const winner = current.map(a => a.slice());

        // put the project back exactly as it was; the label tail-slot cache
        // may have been built against a candidate arrangement mid-search
        // (getSocaPlan labels every leg), so drop it with the candidates
        targets.forEach((t, i) => {
            if (t.members) {
                // members whose default was DEALT (no store) go back to
                // having no store - writing the dealt tails would freeze an
                // arrangement nobody chose
                t.members.forEach(m => {
                    const store = m.layer.powerSocaPhasePos
                        || (m.layer.powerSocaPhasePos = {});
                    if (m.hadStore) store[m.soca] = m.savedStore.slice();
                    else delete store[m.soca];
                });
                return;
            }
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            if (original[i].every((p, k) => p === k + 1)) delete store[t.soca];
            else store[t.soca] = original[i].slice();
        });
        this._circuitTailCache = null;

        return {
            before, after: best, searched,
            targets: targets.map(t => `${t.name} (${t.layerName || t.layer.name}, ${t.legs} circuits)`),
            moves: targets.map((t, i) => ({
                layerId: t.layer.id, layerName: t.layerName || t.layer.name,
                soca: t.soca,
                name: t.name, legs: t.legs,
                members: t.members ? t.members.map(m => ({
                    layerId: m.layer.id, soca: m.soca, legs: m.legs })) : null,
                from: original[i], to: winner[i],
                amps: t.amps, labels: t.labels
            })).filter(m => m.from.some((p, k) => p !== m.to[k]))
        };
    }

    applyPhaseBalance(moves) {
        const touched = new Set();
        for (const m of moves || []) {
            // A shared box's move re-deals the whole set: ascending tails to
            // members in member order, each member's slice stored on its own
            // layer - the same deal write() ran during the search.
            if (m.members && m.members.length) {
                const sorted = m.to.slice().sort((a, b) => a - b);
                let off = 0;
                for (const mem of m.members) {
                    const layer = (this.project.layers || [])
                        .find(l => l.id === mem.layerId);
                    if (!layer) { off += mem.legs; continue; }
                    const store = layer.powerSocaPhasePos
                        || (layer.powerSocaPhasePos = {});
                    store[mem.soca] = sorted.slice(off, off + mem.legs);
                    off += mem.legs;
                    touched.add(layer);
                }
                continue;
            }
            const layer = (this.project.layers || []).find(l => l.id === m.layerId);
            if (!layer) continue;
            const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
            if (m.to.every((p, k) => p === k + 1)) delete store[m.soca];
            else store[m.soca] = m.to.slice();
            touched.add(layer);
        }
        this._circuitTailCache = null;
        if (touched.size) this.updateLayers([...touched], true, 'Balance Phase Legs');
        return touched.size;
    }

    // Show what the balancer found and let the user accept or decline it.
    // Advisory by design: this moves a multi to a different set of breakers
    // on paper, and somebody still has to plug it in that way.
    //
    // Scoped to one distro when `distroId` is given - the per-distro
    // Balance button's dialog reports that distro's before/after and moves
    // only its multis. With nothing movable it STATES why (full multis,
    // clashed boxes, assignments the plan no longer produces) rather than
    // computing silently to a no-op: the reference show read that silence
    // as "balancing won't calculate".
    showBalanceDialog(distroId) {
        const r = this.suggestPhaseBalance(distroId);
        const ID = 'balance-modal';
        document.getElementById(ID)?.remove();
        const esc = (s) => this._esc ? this._esc(s) : s;
        const gain = r.before - r.after;
        const distro = distroId
            ? this.getDistros().find(d => d.id === distroId) : null;
        let noTargets = `<p style="margin:0; color:#a6b0bb;">Every multi on a three-phase distro is full, so the legs are already
               as even as the pattern allows. Imbalance comes from partly-filled
               multis — there are none here.</p>`;
        if (distroId) {
            const b = this._balanceBlockers(distroId);
            const lines = [];
            if (b.full.length) lines.push(
                `${b.full.map(f => esc(f.name)).join(', ')} ${b.full.length === 1 ? 'is' : 'are'} full — a full box balances itself, there is nothing to choose.`);
            b.clashed.forEach(c => lines.push(
                `${esc(c.name)} (${esc(c.layers)}) is a shared box ${c.overflow
                    ? 'with more circuits than the six it holds'
                    : 'with a circuit claimed twice'} — resolve the clash first.`));
            b.phantom.forEach(p => lines.push(
                `${esc(p.layers)} assigns ${p.count === 1 ? 'a multi' : p.count + ' multis'} to this distro but ${esc(p.reason)}`));
            noTargets = `<p style="margin:0 0 6px; color:#a6b0bb;">Nothing on this distro can move${lines.length ? ':' : ' — no partly-filled multi lands on it.'}</p>`
                + lines.map(l => `<div style="color:#a6b0bb; margin:0 0 4px; padding-left:10px;">· ${l}</div>`).join('');
        }
        const body = !r.targets.length
            ? noTargets
            : !r.moves.length
            ? `<p style="margin:0; color:#a6b0bb;">Checked ${r.searched} arrangement${r.searched === 1 ? '' : 's'} of
               ${r.targets.length} partly-filled multi${r.targets.length === 1 ? '' : 's'} and could not beat the current
               ${r.before.toFixed(1)}% imbalance. Landing them elsewhere will not help;
               filling the short multis or moving circuits between them would.</p>`
            : `<div style="display:flex; align-items:baseline; gap:10px; margin-bottom:14px;">
                 <span style="font-size:22px; color:#e05050;">${r.before.toFixed(1)}%</span>
                 <span style="color:#7d8894;">→</span>
                 <span style="font-size:22px; color:#5fa85f;">${r.after.toFixed(1)}%</span>
                 <span style="color:#8fa0b2; font-size:11px;">worst-leg imbalance · ${gain.toFixed(1)} points better</span>
               </div>
               <div style="font-size:11px; color:#8a949f; margin-bottom:6px;">Re-plug these circuits along the same
               fan — no rewiring, no re-patching:</div>
               ${r.moves.map(m => `
                 <div style="margin-bottom:10px;">
                   <div style="color:#e8eef5; margin-bottom:3px;">${esc(m.name)}
                     <span style="color:#7d8894; font-weight:400;">· ${esc(m.layerName)}</span></div>
                   <table style="width:100%; border-collapse:collapse; font-size:11px;">
                     ${m.to.map((p, k) => p === m.from[k] ? '' : `<tr>
                       <td style="padding:2px 8px; color:#a6b0bb; width:40%;">${esc((m.labels || [])[k] || `circuit ${k + 1}`)}
                         <span style="color:#6d7681;">(${m.amps[k].toFixed(1)} A)</span></td>
                       <td style="padding:2px 8px; color:#a6b0bb;">socket ${m.from[k]} → <strong style="color:#e8eef5;">socket ${p}</strong></td>
                     </tr>`).join('')}
                   </table>
                 </div>`).join('')}
               <div style="margin-top:12px; font-size:11px; color:#7d8894;">Balancing picks WHICH sockets of the fan a partly-filled
               multi uses — skipping one lands the remainder on different
               legs. Circuits keep wall order across the chosen sockets,
               so the labels still read in order across the wall.
               Evaluated ${r.searched} arrangements.</div>`;

        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:540px; max-width:94vw; margin:80px auto; border:1px solid #3a3a3a; overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">BALANCE PHASE LEGS${distro ? ` — ${esc(distro.name).toUpperCase()}` : ''}</h2>
    <button class="btn btn-secondary balance-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; font-size:12px; line-height:1.55;">${body}</div>
  <div style="display:flex; gap:8px; justify-content:flex-end; padding:0 20px 16px;">
    <button class="btn btn-secondary balance-reset" title="Put every multi back on its natural breaker position">Reset offsets</button>
    <button class="btn btn-secondary balance-close">${r.moves.length ? 'Leave it' : 'Close'}</button>
    ${r.moves.length ? '<button class="btn balance-apply">Apply</button>' : ''}
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelectorAll('.balance-close').forEach(b =>
            b.addEventListener('click', () => el.remove()));
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
        // Balancing renumbers labels (true tails), so refresh EVERY pane
        // that prints them - splitter rows and the label editor included,
        // plus the canvas bubbles - not just the load roll-ups. The server
        // echo would repaint them a round-trip later anyway; doing it here
        // means the left pane and the map agree the moment the dialog
        // closes (same refresh set as _writeSplitterManual).
        const refreshAll = () => {
            this.refreshDistroPanel();
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const resetBtn = el.querySelector('.balance-reset');
        if (resetBtn) resetBtn.addEventListener('click', () => {
            // A scoped dialog resets only its own distro's multis - the
            // other services' arrangements are not this button's to drop.
            this.clearPhaseBalance(distroId);
            el.remove();
            refreshAll();
        });
        const applyBtn = el.querySelector('.balance-apply');
        if (applyBtn) applyBtn.addEventListener('click', () => {
            this.applyPhaseBalance(r.moves);
            el.remove();
            refreshAll();
        });
    }

    // Plain-language explanation of what the phasing schemes mean and why the
    // choice changes the leg loads. Built on demand rather than living in
    // index.html so the copy sits next to the math it describes.
    //
    // The scheme table is GENERATED from powerPhasingSchemes and the leg map
    // itself: names come from the same records the select prints, and the
    // circuit row is read out of _circuitLegs. A user asked what the
    // difference between "line-to-line" and "paired" was because the same
    // scheme was named one way here and another way there; nothing here
    // restates a name or a mapping in prose, so they cannot drift apart again.
    showPhasingHelp() {
        const ID = 'phasing-help-modal';
        document.getElementById(ID)?.remove();
        const schemes = this.powerPhasingSchemes();
        const byId = (id) => schemes.find(s => s.id === id);
        // the six positions of the fan, straight out of the leg map
        const spread = (id) => [1, 2, 3, 4, 5, 6]
            .map(i => this._circuitLegs(i, id).join('')).join(' ');
        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:660px; max-width:94vw; margin:60px auto; border:1px solid #3a3a3a; display:flex; flex-direction:column; max-height:calc(100vh - 120px); overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">HOW MULTIS LAND ON THE PHASE LEGS</h2>
    <button class="btn btn-secondary phasing-help-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; overflow-y:auto; font-size:12px; color:#c3ccd6; line-height:1.6;">

    <p style="margin:0 0 14px;"><strong style="color:#e8eef5;">A distro fed from camlock is three-phase. Every circuit
    coming off the breakout is single-phase</strong> — whether it sits on one
    hot and a neutral, or across two hots with no neutral. Three-phase never
    reaches a panel. The legs only decide <em>which</em> hots each circuit
    sits across, and therefore how the load spreads over the service.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px;">
      <div style="color:#e8eef5; margin-bottom:5px;">Two things vary, and they are independent</div>
      <div style="color:#a6b0bb; margin-bottom:8px;">Every scheme is named for both, coupling first, order second — so
      <em>${byId('paired-ll').name}</em> and <em>${byId('rotating-ll').name}</em>
      are the same coupling dealt differently, not two answers to one question.</div>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Coupling</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Line-to-neutral</strong> is one hot and
          a neutral (X). <strong style="color:#c3ccd6;">Line-to-line</strong> is two hots and no neutral (XY). This is the
          electrical relationship, and it follows the circuit voltage: line-to-neutral
          runs at the service divided by √3 — 120 V off a 208 V service, 230 V off a
          400 V one.</td>
        </tr>
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Order</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Rotating</strong> advances on every
          circuit (X Y Z X Y Z). <strong style="color:#c3ccd6;">Paired</strong> puts two consecutive circuits on the same
          assignment before advancing (X X Y Y Z Z). This is how the distro is wired
          internally, which is why it is a setting here and not something the voltage
          can answer.</td>
        </tr>
      </table>
    </div>

    <div style="background:#3a2626; border-left:3px solid #b34a3a; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px; color:#e0c0ba;">
      <strong style="color:#f5cdc4;">No standard assigns a circuit to a leg.</strong>
      ANSI E1.80, USITT RP-1 and NEC 520.68 all cover the <em>pinout</em> —
      which pin carries which circuit's conductors — and none of them assigns
      a circuit to a leg. No major distro manufacturer publishes a universal
      mapping. Motion Laboratories' own maintenance manual says to "verify
      the pinout of each output, including that the correct phase is on the
      correct pin per the pinout. (The pinout is marked on the panel near the
      output devices.)" <strong style="color:#f5cdc4;">Read the unit.</strong>
    </div>

    <p style="margin:0 0 14px; color:#a6b0bb;">What every source does agree on is the
    <em>balance goal</em>: two circuits per leg line-to-neutral, two circuits
    per leg-pair line-to-line. Only the order varies — and the order is exactly
    what decides where a partly-filled multi dumps its remainder. Each pattern
    below is documented on a real distro or rack, none is a default.</p>

    <table class="phasing-scheme-table" style="width:100%; border-collapse:collapse; margin-bottom:10px;">
      <tr style="border-bottom:1px solid #3a3a3a;">
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Scheme</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Circuits 1–6</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Where it is documented</th>
      </tr>
      ${schemes.map(sc => `
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">${sc.name}<br><span style="color:#7d8894; font-size:11px;">${sc.lineToLine ? 'two hots, no neutral' : 'one hot and a neutral'}</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px;">${spread(sc.id)}</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">${sc.where}</td>
      </tr>`).join('')}
    </table>

    <p style="margin:0 0 16px; color:#a6b0bb;">The two paired line-to-line schemes differ
    only in the order the pairs come round: <em>${byId('paired-ll-alt').pattern}</em>
    follows the cyclic order X → Y → Z → X, the way AB → BC → CA does, and
    <em>${byId('paired-ll').pattern}</em> does not. That is the ordering fact,
    not a ranking — neither is a default, and the only way to know which one a
    box uses is to read it.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0;">
      <div style="color:#e8eef5; margin-bottom:5px;">Why your legs are uneven</div>
      <div style="color:#a6b0bb;">Imbalance almost always comes from <strong>partly-filled
      multis</strong>, not from the screens. A full 6-circuit multi balances
      itself under any scheme. A multi that stops at 4 or 5 circuits dumps its
      remainder onto whichever legs come first in the pattern — with paired
      legs that is always X. Fill the multi, move a circuit to another multi,
      or use the rotating pattern if the distro is wired that way.</div>
    </div>

    <div style="margin-top:14px; color:#7d8894; font-size:11px;">
      Per-leg current is a phasor sum, not a straight addition: a line-to-line
      circuit is one load drawing the <em>same</em> current in both its legs, sitting
      ±30° off each leg's line-to-neutral reference. Imbalance is NEMA-style —
      the largest deviation from the average of the three legs.
    </div>
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelector('.phasing-help-close').addEventListener('click', () => el.remove());
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
    }

    // How a distro lands a multi's 6 circuits on its phase legs.
    //
    // This is a property of the DISTRO's internal bus and breaker
    // arrangement. It is NOT the connector pinout: ANSI E1.80-2024 defines
    // 120V Type U and 208V Types C/D/E, but those describe which PIN carries
    // which circuit's conductors - the standard's own table key is only
    // "L = Ungrounded Circuit Conductor" and it never assigns a circuit to
    // L1, L2 or L3. Two distros with identical E1.80 pinouts can still land
    // their circuits on different legs. Read the distro, not the connector.
    //
    // Every pattern below is documented on a real North American distro or
    // rack. There is no national standard for phase rotation - a search of
    // E1.80, USITT RP-1, NEC 520.68, and the published material from every
    // major distro manufacturer turned up nothing that assigns a circuit to
    // a leg. Motion Laboratories' own maintenance manual says to "verify the
    // pinout of each output, including that the correct phase is on the
    // correct pin per the pinout. (The pinout is marked on the panel near the
    // output devices.)" That is the industry position: read the unit.
    //
    // What IS consistent across every source is the balance goal - two
    // circuits per leg line-to-neutral, two circuits per leg-PAIR
    // line-to-line. Only the order varies, and the order is what changes a
    // partly-filled multi.
    //
    // NAMING. A scheme varies along TWO independent axes and the name gives
    // both, coupling first, order second:
    //   coupling  line-to-neutral (one leg, X) or line-to-line (two, XY)
    //   order     rotating (advance every circuit) or paired (two circuits
    //             on one assignment, then advance)
    // Naming only one axis made two orthogonal things look like alternatives
    // - the same scheme read as "paired" in the list and "line-to-line" on
    // the derived entry, and a user asked what the difference was. `name` is
    // therefore COMPUTED from the axes so no caller can spell it its own way.
    //
    // The volts are deliberately not in the name: line-to-neutral is 120V on
    // a 208V service and 230V on a 400V one, so the figure belongs to the
    // SERVICE, not the scheme. It is derived as V / sqrt(3) where it helps.
    powerPhasingSchemes() {
        const named = (s) => ({
            ...s,
            coupling: s.lineToLine ? 'Line-to-line' : 'Line-to-neutral',
            name: `${s.lineToLine ? 'Line-to-line' : 'Line-to-neutral'}, ${s.order} (${s.pattern})`,
        });
        return [
            { id: 'rotating-ln', lineToLine: false, order: 'rotating',
              pattern: 'X Y Z X Y Z',
              where: 'Published phasing sheet for a 36-way house distro. No practitioner source corroborates it, so confirm before relying on it.' },
            { id: 'paired-ln', lineToLine: false, order: 'paired',
              pattern: 'X X Y Y Z Z',
              where: 'What several practitioners report as usual.' },
            { id: 'paired-ll', lineToLine: true, order: 'paired',
              pattern: 'XY ZX YZ',
              where: 'Two independent rental houses publish this exact map.' },
            { id: 'paired-ll-alt', lineToLine: true, order: 'paired',
              pattern: 'XY YZ ZX',
              where: 'Same grouping, other pair order — published as the Strand LightRack module pinout.' },
            { id: 'rotating-ll', lineToLine: true, order: 'rotating',
              pattern: 'XY XZ YZ',
              where: 'Reported as a competing family. Spreads a partly-filled multi best.' }
        ].map(named);
    }

    // Default scheme for a distro: line-to-line when the circuit voltage
    // matches the service voltage (208V circuits on a 208V wye), otherwise
    // line-to-neutral.
    powerPhasingFor(distro, circuitVoltage) {
        const schemes = this.powerPhasingSchemes();
        const explicit = distro && distro.phasing && schemes.find(s => s.id === distro.phasing);
        if (explicit) return explicit;
        const ll = distro && circuitVoltage > 0 && Math.abs(circuitVoltage - distro.voltage) < 1;
        return schemes.find(s => s.id === (ll ? 'paired-ll' : 'rotating-ln'));
    }

    // The circuit voltage this distro actually sees: whatever the screens
    // feeding it run at, walked in the SAME order getDistroLoads walks them so
    // the select and the leg maths can never name two different schemes.
    //
    // A distro with nothing assigned yet has no evidence to read, so it is
    // taken at its word - a service whose circuits sit at the service voltage,
    // which is what choosing 208V means. It is a default like any other here
    // and the moment a multi lands on the distro the real circuit voltage
    // replaces it.
    distroCircuitVoltage(distro) {
        if (!distro || !this.project) return 0;
        let seen = null;
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            if (!plan.some(s => assign[s.soca] === distro.id)) continue;
            seen = parseFloat(layer.powerVoltage) || 0;
        }
        return seen === null ? (Number(distro.voltage) || 0) : seen;
    }

    // What the phasing control has to say out loud: the scheme in force, and
    // whether it is DERIVED from the voltage or was picked by hand.
    //
    // Two distros can run the same scheme, one because somebody read the box
    // and one because nobody has - and only the first survives a voltage
    // change. Without this distinction on screen "a manual choice overrides
    // the default" is a rule the user cannot see operating.
    distroPhasingState(distro) {
        const schemes = this.powerPhasingSchemes();
        const chosen = distro && distro.phasing
            && schemes.find(s => s.id === distro.phasing);
        const circuitV = this.distroCircuitVoltage(distro);
        // Ask for the derived answer explicitly rather than reading it off
        // powerPhasingFor(distro, ...), which would hand back the explicit
        // choice and hide what the voltage would have chosen.
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, phasing: null }, circuitV);
        return {
            explicit: !!chosen,
            derived,
            circuitVoltage: circuitV,
            scheme: chosen || derived
        };
    }

    // Order a leg pair cyclically (X>Y>Z>X). The first leg of the cyclic pair
    // carries the line-to-line current at +30 deg relative to its own
    // line-to-neutral voltage, the second at -30 deg.
    _cyclicPair(a, b) {
        const C = ['X', 'Y', 'Z'];
        const ia = C.indexOf(a), ib = C.indexOf(b);
        return ib === (ia + 1) % 3 ? [a, b] : [b, a];
    }

    _addLegPhasor(store, leg, amps, degrees) {
        const r = degrees * Math.PI / 180;
        store[leg].re += amps * Math.cos(r);
        store[leg].im += amps * Math.sin(r);
    }

    // `offset` slides the used circuits along the multi's own six positions:
    // a multi with 4 circuits in use can occupy positions 1-4, 2-5 or 3-6.
    // The load does not move to another multi - it is the same 6-way fan,
    // just landed on different legs of it.
    //
    // The offset MUST be bounded by socaPhaseOffsetMax so the last circuit
    // stays within position 6. The modulo below is only a guard; if it ever
    // actually wraps, the offset was invalid and the answer is nonsense -
    // a 5-circuit multi at offset 3 would want positions 4..8, and wrapping
    // 7 and 8 back to 1 and 2 silently invents a plan nobody can patch.
    //
    // `boxSize` is the fan the positions index into. A 3-tail L21-30 box
    // has no order axis to choose - one circuit per assignment - so its
    // line-to-line map is the fixed cyclic pair walk (XY YZ ZX, the box's
    // own internal wiring) whatever paired/rotating scheme the distro
    // runs its socas on, and its line-to-neutral map is one leg per tail.
    _circuitLegs(legIndex, schemeId, offset = 0, boxSize = 6) {
        const size = Number(boxSize) === 3 ? 3 : 6;
        const i = ((legIndex - 1 + (Number(offset) || 0)) % size + size) % size;
        if (size === 3) {
            const ln = schemeId === 'paired-ln' || schemeId === 'rotating-ln';
            if (ln) return [['X'], ['Y'], ['Z']][i];
            return [['X','Y'], ['Y','Z'], ['Z','X']][i];
        }
        if (schemeId === 'paired-ll') return [['X','Y'], ['X','Y'], ['Z','X'], ['Z','X'], ['Y','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ll-alt') return [['X','Y'], ['X','Y'], ['Y','Z'], ['Y','Z'], ['Z','X'], ['Z','X']][i];
        if (schemeId === 'rotating-ll') return [['X','Y'], ['X','Z'], ['Y','Z'], ['X','Y'], ['X','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ln') return [['X'], ['X'], ['Y'], ['Y'], ['Z'], ['Z']][i];
        return [['X', 'Y', 'Z'][i % 3]];
    }

    // How far a multi's used circuits can slide as a BLOCK before the last
    // one runs off the end of the fan. Kept for the legacy block model;
    // socaCircuitPositions supersedes it.
    socaPhaseOffsetMax(legsUsed, boxSize = 6) {
        return Math.max(0, (Number(boxSize) || 6) - (Number(legsUsed) || 6));
    }

    // Which position on the multi's 6-way fan each used circuit occupies.
    //
    // WALL-ORDER RULE (user decision, fixed): balancing - or anything else -
    // only ever chooses WHICH tails of the fan are in use (the SET). The
    // assignment of circuits to the chosen tails is always wall order ->
    // ascending tail number, so a wall using tails {1,2,3,5,6} reads
    // S1-1, S1-2, S1-3, S1-5, S1-6 left to right, never a permutation.
    // Stored arrays are therefore sorted ascending ON READ: projects that
    // still carry a permutation from the old balancer ([6,2,5,1,3]) or a
    // rotation ([5,6,1,2,3]) display wall-ordered immediately, keeping the
    // same occupied tails, without a re-balance.
    //
    // Returns a position (1-6) per used circuit, ascending in circuit
    // (wall) order. Falls back to the legacy block offset - which selects
    // the occupied tails off+1..off+L, already ascending - then to the
    // natural 1..L.
    socaCircuitPositions(layer, socaNum, legsUsed) {
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const saved = ((layer && layer.powerSocaPhasePos) || {})[socaNum];
        if (Array.isArray(saved) && saved.length === L
            && saved.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(saved).size === L) {
            return saved.slice().sort((a, b) => a - b);
        }
        // A multi PINNED to a number can be sharing one physical box with a
        // multi on another screen, and then its unstored default is not the
        // natural 1..L - it is the box's NEXT FREE tails, dealt in
        // _resolveSharedSocas with every member on the table. Read the dealt
        // answer rather than re-deriving it here; a pin the naming pass has
        // not resolved (mid-build, an orphan screen) falls through to the
        // legacy default below.
        if (layer && (layer.powerSocaDistro || {})[socaNum]) {
            const pin = parseInt((layer.powerSocaNumber || {})[socaNum], 10);
            if (Number.isFinite(pin) && pin >= 1) {
                const rec = this._powerNaming(layer).socas.get(Number(socaNum));
                if (rec && Array.isArray(rec.positions)
                        && rec.positions.length === (Number(legsUsed) || 0)) {
                    return rec.positions.slice();
                }
            }
        }
        const off = this.socaPhaseOffset(layer, socaNum, L);
        return Array.from({ length: L }, (_, i) => i + 1 + off);
    }

    // The scheme ONE CIRCUIT actually lands with: coupling is physics -
    // a 110V Edison circuit needs a hot and a neutral, a 208V circuit two
    // hots - so the circuit's own voltage decides line-to-neutral vs
    // line-to-line, and only the dealing ORDER is the distro's wiring to
    // declare. An explicit distro scheme therefore applies to a circuit
    // only when its coupling matches what that circuit's voltage derives;
    // otherwise the voltage's own derived default takes over for that
    // circuit alone. This is what lets a 110V multi and a 208V multi share
    // one distro without the explicit choice pairing up Edison circuits:
    // the 110V circuits ride one leg each, the 208V circuits their pairs
    // (user ruling, 2026-08-28). The gear select still shows a mismatched
    // explicit choice and says so - paperwork is displayed, never obeyed
    // into an impossible hookup.
    _circuitSchemeFor(distro, circuitVoltage) {
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, phasing: null },
            circuitVoltage);
        const chosen = this.powerPhasingFor(distro, circuitVoltage);
        return chosen.lineToLine === derived.lineToLine ? chosen : derived;
    }

    // Positions must be a set of distinct 1-6 values, one per used circuit -
    // two circuits cannot share a tail. Only the SET matters (wall-order
    // rule): stored sorted ascending, and a permutation of 1..L is the
    // natural arrangement - but only on a multi that owns its whole box.
    // On a SHARED box tails 1..L are one specific claim among six, not a
    // default: dropping the store there hands the member back to the deal,
    // and the deal answers by layer order - which is exactly how "put me
    // back on 1-4" once evaporated and let the joiner keep tail 1.
    setSocaCircuitPositions(layer, socaNum, positions, legsUsed) {
        if (!layer) return false;
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const ok = Array.isArray(positions) && positions.length === L
            && positions.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(positions).size === L;
        if (!ok) return false;
        const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
        const sorted = positions.slice().sort((a, b) => a - b);
        const natural = sorted.every((p, i) => p === i + 1);
        if (natural && !this.getSocaShare(layer, socaNum)) {
            delete store[socaNum];
        } else {
            store[socaNum] = sorted;
        }
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Move Circuits');
        return true;
    }

    // Which position within the multi the first used circuit sits on (0-based).
    // Clamped on read as well as on write, so a stored value that is no longer
    // valid - the screen shed a circuit since it was set - degrades to the
    // nearest legal position instead of wrapping off the end.
    socaPhaseOffset(layer, socaNum, legsUsed) {
        const map = (layer && layer.powerSocaPhaseOffset) || {};
        const raw = Math.max(0, Number(map[socaNum]) || 0);
        return Math.min(raw,
            this.socaPhaseOffsetMax(legsUsed, this.socaBoxSize(layer)));
    }

    setSocaPhaseOffset(layer, socaNum, offset, legsUsed) {
        if (!layer) return;
        // Always leave an object behind, never delete the property itself:
        // an absent key is simply missing from the update payload and the
        // server keeps whatever it had, so "clear this" would silently not
        // clear. An empty object overwrites.
        const map = layer.powerSocaPhaseOffset || (layer.powerSocaPhaseOffset = {});
        const v = Math.min(Math.max(0, Number(offset) || 0),
                           this.socaPhaseOffsetMax(legsUsed,
                               this.socaBoxSize(layer)));
        if (v) map[socaNum] = v; else delete map[socaNum];
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Set Breaker Offset');
    }

    // Drop every multi back to its natural breaker position - show-wide, or
    // only the multis assigned to one distro when `distroId` is given (the
    // scoped balance dialog's reset).
    clearPhaseBalance(distroId) {
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        if (!distroId) {
            screens.forEach(l => { l.powerSocaPhaseOffset = {}; l.powerSocaPhasePos = {}; });
        } else {
            screens.forEach(l => {
                const assign = l.powerSocaDistro || {};
                for (const store of [l.powerSocaPhaseOffset, l.powerSocaPhasePos]) {
                    if (!store) continue;
                    for (const k of Object.keys(store)) {
                        if (assign[k] === distroId) delete store[k];
                    }
                }
            });
        }
        this._circuitTailCache = null;
        if (screens.length) this.updateLayers(screens, true, 'Reset Phase Offsets');
        return screens.length;
    }

    // Rollup per distro across every screen, plus an 'unassigned' bucket so
    // no load is silently dropped. Three-phase distros also get per-leg
    // (X/Y/Z) loads so you can see whether the service is loaded evenly.
    getDistroLoads() {
        const distros = this.getDistros();
        const mk = (d) => ({
            distro: d, socas: [], watts: 0,
            legWatts: { X: 0, Y: 0, Z: 0 },
            legPhasor: { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 }, Z: { re: 0, im: 0 } },
            pairWatts: {}
        });
        const buckets = new Map(distros.map(d => [d.id, mk(d)]));
        const unassigned = mk(null);
        // One feeds entry per PHYSICAL box: two multis pinned to the same
        // (distro, number) are one soca serving two screens, so the second
        // member folds into the first's row - watts summed, legs combined,
        // both screens named. Counting each member as its own soca is
        // exactly the phantom-multi arithmetic the pin exists to kill. The
        // WATTS still add per member (the load is real twice over); only
        // the enumeration merges.
        const boxRows = new Map();      // share key -> the one feeds row
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const plan = this.getSocaPlan(layer);
            if (!plan.length) continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of plan) {
                const b = buckets.get(assign[s.soca]) || unassigned;
                const share = this.getSocaShare(layer, s.soca);
                const row = share && boxRows.get(share.key);
                if (row) {
                    row.layer += ' + ' + layer.name;
                    row.watts += s.watts;
                    row.legs += s.legs.length;
                } else {
                    const fresh = { layer: layer.name, layerId: layer.id, soca: s.soca, name: s.name, watts: s.watts, legs: s.legs.length };
                    if (share) { fresh.shared = true; boxRows.set(share.key, fresh); }
                    b.socas.push(fresh);
                }
                b.watts += s.watts;
                // spread this multi's circuits across the phase legs
                const d = b.distro;
                if (d && d.phase === 3) {
                    // Per CIRCUIT, not per distro: coupling follows the
                    // circuit's own voltage (_circuitSchemeFor), so a 110V
                    // multi rides one leg per circuit while a 208V multi on
                    // the same service keeps its leg pairs - the mixed case
                    // sums correctly because both land in one phasor store.
                    const scheme = this._circuitSchemeFor(d, circuitV);
                    if (b.scheme && b.scheme.lineToLine !== scheme.lineToLine) {
                        b.schemeMixed = true;
                    }
                    b.scheme = scheme;
                    const vln = d.voltage / Math.sqrt(3);
                    const boxSize = this.socaBoxSize(layer);
                    const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                    for (let li = 0; li < s.legs.length; li++) {
                        const leg = s.legs[li];
                        const legs = this._circuitLegs(pos[li], scheme.id, 0, boxSize);
                        if (legs.length === 1) {
                            // Line-to-neutral: full current on ONE leg, in
                            // phase with that leg's L-N voltage. Amps are
                            // I = P / V_screen (the circuit's own voltage -
                            // a 110V circuit draws its watts at 110, user
                            // ruling); the service L-N figure only stands
                            // in when the screen carries no voltage.
                            b.legWatts[legs[0]] += leg.watts;
                            this._addLegPhasor(b.legPhasor, legs[0],
                                leg.watts / (circuitV > 0 ? circuitV : vln), 0);
                        } else {
                            // Line-to-line: the SAME current flows in both
                            // legs (it is one series load) - it is NOT halved.
                            // Referred to each leg's own L-N reference it sits
                            // at +30 deg on the first leg of the cyclic pair
                            // and -30 deg on the second.
                            const [first, second] = this._cyclicPair(legs[0], legs[1]);
                            const amps = leg.watts / d.voltage;
                            this._addLegPhasor(b.legPhasor, first, amps, 30);
                            this._addLegPhasor(b.legPhasor, second, amps, -30);
                            // VA column keeps the panel-schedule convention:
                            // half the VA booked against each leg
                            b.legWatts[first] += leg.watts / 2;
                            b.legWatts[second] += leg.watts / 2;
                            const key = [first, second].join('');
                            b.pairWatts[key] = (b.pairWatts[key] || 0) + leg.watts;
                        }
                    }
                }
            }
        }
        const shape = (b) => {
            const d = b.distro;
            const v = d ? d.voltage : 0;
            const amps = v > 0 ? (d.phase === 3 ? b.watts / (v * 1.73) : b.watts / v) : 0;
            const rating = d ? d.ratingA : 0;
            // Per-leg amps are line-to-NEUTRAL: on a 208V wye that is 120V,
            // which is what each leg actually sees.
            let legs = null, imbalancePct = 0;
            if (d && d.phase === 3) {
                // Per-leg current is the PHASOR magnitude, not watts/voltage:
                // line-to-line loads sit +-30 deg off their legs' L-N
                // reference, so scalar addition would misreport by 13-15%.
                const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
                const w = b.legWatts, ph = b.legPhasor;
                const one = (k) => {
                    const a = mag(ph[k]);
                    return { watts: w[k], amps: a, pct: rating > 0 ? (a / rating) * 100 : 0 };
                };
                legs = { X: one('X'), Y: one('Y'), Z: one('Z') };
                // NEMA-style: max deviation from the AVERAGE (not max-min
                // spread, which reads roughly double and is not what a
                // genset spec or an electrician means by "% imbalance").
                const amps = [legs.X.amps, legs.Y.amps, legs.Z.amps];
                const avg = (amps[0] + amps[1] + amps[2]) / 3;
                imbalancePct = avg > 0
                    ? (Math.max(...amps.map(x => Math.abs(x - avg))) / avg) * 100 : 0;
                legs.lineToNeutralV = v / Math.sqrt(3);
                legs.avgAmps = avg;
                legs.spreadAmps = Math.max(...amps) - Math.min(...amps);
                legs.over = rating > 0 && Math.max(...amps) > rating;
                legs.scheme = b.scheme ? b.scheme.name : null;
                legs.schemeId = b.scheme ? b.scheme.id : null;
                // True when this service carries BOTH couplings at once -
                // 110V single-leg circuits beside 208V leg pairs. The
                // scheme fields above then name only the last one summed,
                // so a surface printing the scheme can say "mixed" instead.
                legs.schemeMixed = !!b.schemeMixed;
                legs.pairWatts = b.pairWatts;
            }
            return {
                id: d ? d.id : null,
                name: d ? d.name : 'Unassigned',
                location: (d && d.location) || null,
                ratingA: rating, voltage: v, phase: d ? d.phase : null,
                watts: b.watts, amps,
                pct: rating > 0 ? (amps / rating) * 100 : 0,
                over: rating > 0 && amps > rating,
                legs, imbalancePct,
                socas: b.socas
            };
        };
        const out = distros.map(d => shape(buckets.get(d.id)));
        if (unassigned.socas.length) out.push(shape(unassigned));
        return out;
    }

    // Per-leg amps in ONE physical box's feed - the same phasor walk
    // getDistroLoads runs for a service, scoped to the box. `members` is
    // [{layer, s}] with `s` the member's soca-plan record; a shared box
    // hands every member in, so both screens' circuits sum into one feed.
    // This is what the L21-30's 30 A/leg feed check reads: the box's three
    // 208V circuits sit +-30 deg off their legs, so a full box at circuit
    // current I loads each feed leg at I x sqrt(3), never 2 x I.
    boxFeedLegAmps(distro, members) {
        const phasor = { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 },
                         Z: { re: 0, im: 0 } };
        if (!distro) return { X: 0, Y: 0, Z: 0 };
        const vln = (Number(distro.voltage) || 0) / Math.sqrt(3);
        for (const m of (members || [])) {
            if (!m || !m.layer || !m.s) continue;
            const circuitV = parseFloat(m.layer.powerVoltage) || 0;
            const scheme = this._circuitSchemeFor(distro, circuitV);
            const boxSize = this.socaBoxSize(m.layer);
            const pos = this.socaCircuitPositions(
                m.layer, m.s.soca, m.s.legs.length);
            for (let li = 0; li < m.s.legs.length; li++) {
                const leg = m.s.legs[li];
                const legs = this._circuitLegs(pos[li], scheme.id, 0, boxSize);
                if (legs.length === 1) {
                    this._addLegPhasor(phasor, legs[0],
                        leg.watts / (circuitV > 0 ? circuitV : vln), 0);
                } else {
                    const [first, second] = this._cyclicPair(legs[0], legs[1]);
                    const amps = leg.watts / (Number(distro.voltage) || 1);
                    this._addLegPhasor(phasor, first, amps, 30);
                    this._addLegPhasor(phasor, second, amps, -30);
                }
            }
        }
        const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
        return { X: mag(phasor.X), Y: mag(phasor.Y), Z: mag(phasor.Z) };
    }

    // Keyed by the multi's stable index, like every other per-multi store, so
    // a home run stays with its multi when the distro renumbers it.
    // `record` mirrors setSocaName's: false for the dock's shared-box
    // write-through, which issues one updateLayers over every member itself.
    setSocaLength(layer, socaIndex, length, record = true) {
        if (!layer) return;
        const store = layer.powerSocaLengths || (layer.powerSocaLengths = {});
        const v = String(length || '').trim();
        if (v) store[socaIndex] = v; else delete store[socaIndex];
        if (record) {
            this.updateLayers([layer], true, 'Set Multi Home Run');
        }
    }

    // The distro list died with the Power sidebar: the dock's distro
    // sections are the one surface now - name inline on the header, the
    // load bar and LEGS line beside it, the electrical setup behind the
    // gear (whose content _buildDistroGearContent below builds). So a
    // distro refresh IS a dock render, kept under its old name because
    // every "the loads moved" path already calls it.
    refreshDistroPanel() {
        if (typeof this.renderHardwareDock === 'function') {
            this.renderHardwareDock();
        }
    }

    // The phasing entries one distro's gear select offers: only the
    // orderings of the coupling the voltage derivation picked - read off
    // distroPhasingState's own comparison (powerPhasingFor), never a second
    // one that could disagree with the leg maths. An explicit scheme whose
    // coupling the voltage no longer permits (picked first, voltage changed
    // after) is somebody's paperwork: it stays offered with the mismatch
    // said out loud, never silently dropped or swapped.
    _distroPhasingOptions(ph) {
        const offered = this.powerPhasingSchemes()
            .filter(sc => sc.lineToLine === ph.derived.lineToLine);
        if (ph.explicit && !offered.some(sc => sc.id === ph.scheme.id)) {
            offered.push({ ...ph.scheme,
                name: `${ph.scheme.name} — does not match the `
                    + `${Math.round(ph.circuitVoltage)} V circuits `
                    + `(${ph.derived.coupling.toLowerCase()})` });
        }
        return offered;
    }

    // The distro's gear popover: the electrical setup the retired sidebar
    // rows carried - rating, voltage, phase, phasing (with its derive entry
    // and help), location, remove. Same data-lrd-field keys, same patch
    // path (updateDistro + _restateNaming), same phasing doctrine: the
    // voltage DECIDES the coupling, so only the ordering axis is offered.
    _buildDistroGearContent(d) {
        const wrap = document.createElement('div');
        const heading = document.createElement('div');
        heading.className = 'hw-pop-heading';
        heading.textContent = d.name || 'distro';
        wrap.appendChild(heading);

        const patch = (p) => {
            this.updateDistro(d.id, p);
            this._restateNaming();
        };
        const cap = (text) => {
            const c = document.createElement('label');
            c.style.fontSize = '10px';
            c.style.color = 'var(--ps-dim, #c0c0c0)';
            c.style.textTransform = 'uppercase';
            c.textContent = text;
            return c;
        };

        const row1 = document.createElement('div');
        row1.style.display = 'flex';
        row1.style.flexWrap = 'wrap';
        row1.style.gap = '6px';
        row1.style.alignItems = 'center';
        row1.appendChild(cap('Rating'));
        const rate = document.createElement('input');
        rate.type = 'number';
        rate.min = '1';
        rate.value = d.ratingA;
        rate.style.width = '56px';
        rate.dataset.lrdField = `distro-rating-${d.id}`;
        rate.title = 'Service rating in amps.';
        rate.addEventListener('change', () => patch({ ratingA: rate.value }));
        row1.appendChild(rate);
        row1.appendChild(cap('Voltage'));
        const volt = document.createElement('select');
        volt.className = 'info-select';
        volt.dataset.lrdField = `distro-voltage-${d.id}`;
        [110, 120, 208, 220, 230, 240, 400, 415].forEach(v => {
            const opt = document.createElement('option');
            opt.value = String(v);
            opt.textContent = `${v}V`;
            if (Number(d.voltage) === v) opt.selected = true;
            volt.appendChild(opt);
        });
        volt.addEventListener('change', () => patch({ voltage: volt.value }));
        row1.appendChild(volt);
        const phase = document.createElement('select');
        phase.className = 'info-select';
        phase.dataset.lrdField = `distro-phase-${d.id}`;
        [[1, '1φ'], [3, '3φ']].forEach(([v, text]) => {
            const opt = document.createElement('option');
            opt.value = String(v);
            opt.textContent = text;
            if (Number(d.phase) === v) opt.selected = true;
            phase.appendChild(opt);
        });
        phase.addEventListener('change', () => patch({ phase: phase.value }));
        row1.appendChild(phase);
        wrap.appendChild(row1);

        if (Number(d.phase) === 3) {
            const ph = this.distroPhasingState(d);
            const row2 = document.createElement('div');
            row2.style.display = 'flex';
            row2.style.gap = '6px';
            row2.style.alignItems = 'center';
            row2.style.marginTop = '6px';
            row2.title = 'Phasing. How a multi\'s 6 circuits land on the '
                + 'phase legs - a property of the distro\'s bus and breaker '
                + 'arrangement, read off the distro. Not the connector\'s '
                + 'E1.80 pinout type. Each name gives the coupling, then '
                + 'the dealing order.';
            row2.appendChild(cap('Phasing'));
            const sel = document.createElement('select');
            sel.className = 'info-select';
            sel.style.flex = '1 1 0';
            sel.style.minWidth = '0';
            sel.dataset.lrdField = `distro-phasing-${d.id}`;
            // Two KINDS of entry, grouped as two: the first is an
            // instruction to the app ("follow the voltage"), the rest
            // describe how a distro is wired. Deriving is a state, not the
            // absence of one - the empty value clears distro.phasing and
            // hands the choice back to the voltage. The resolved volts ride
            // on the GROUP, off this distro's own service: they are not a
            // property of any scheme (line-to-neutral is 120V on a 208V
            // service, 230V on a 400V one).
            const derive = document.createElement('optgroup');
            derive.label = 'Let the voltage decide';
            const followOpt = document.createElement('option');
            followOpt.value = '';
            followOpt.textContent =
                `Follow the circuit voltage — ${ph.derived.name}`;
            if (!ph.explicit) followOpt.selected = true;
            derive.appendChild(followOpt);
            sel.appendChild(derive);
            const wired = document.createElement('optgroup');
            wired.label = 'Read it off the distro · '
                + `${Math.round(d.voltage / Math.sqrt(3))} V line-to-neutral, `
                + `${Math.round(d.voltage)} V line-to-line`;
            this._distroPhasingOptions(ph).forEach(sc => {
                const opt = document.createElement('option');
                opt.value = sc.id;
                opt.textContent = sc.name;
                if (ph.explicit && ph.scheme.id === sc.id) opt.selected = true;
                wired.appendChild(opt);
            });
            sel.appendChild(wired);
            sel.addEventListener('change', () => patch({ phasing: sel.value }));
            row2.appendChild(sel);
            const help = document.createElement('button');
            help.textContent = '?';
            help.title = 'What do these mean?';
            help.dataset.lrdField = `distro-phasing-help-${d.id}`;
            help.addEventListener('click', () => this.showPhasingHelp());
            row2.appendChild(help);
            wrap.appendChild(row2);
        }

        const row3 = document.createElement('div');
        row3.style.display = 'flex';
        row3.style.gap = '6px';
        row3.style.alignItems = 'center';
        row3.style.marginTop = '6px';
        row3.appendChild(cap('Location'));
        const loc = document.createElement('input');
        loc.type = 'text';
        loc.value = d.location || '';
        loc.placeholder = 'beach / location';
        loc.style.flex = '1';
        loc.style.minWidth = '0';
        loc.dataset.lrdField = `distro-location-${d.id}`;
        loc.title = 'Where this distro physically sits - the beach, stage '
            + 'left world, FOH. Prints on every power label that names it, '
            + 'so a runner can find the other end.';
        loc.addEventListener('change', () => patch({ location: loc.value }));
        row3.appendChild(loc);
        wrap.appendChild(row3);

        // OUTPUTS (2026-08-31): the connector types this distro can hand a
        // screen - types only, no counts. One tick row per type: face,
        // plain name, what it breaks out to. Every row is sized to stay
        // inside the popover's own box (the resize suite pins it): names
        // never wrap, the breakout text ellipsizes before it can push
        // past the edge.
        const outs = document.createElement('div');
        outs.className = 'hw-pop-outs';
        const outsCap = document.createElement('div');
        outsCap.className = 'hw-pop-outs-cap';
        outsCap.appendChild(cap('Outputs'));
        const outsSub = document.createElement('small');
        outsSub.textContent = 'what this distro can hand a screen';
        outsCap.appendChild(outsSub);
        outs.appendChild(outsCap);
        const offered = new Set(this.distroOutputs(d).map(t => t.id));
        this.getDistroOutputTypes().forEach(t => {
            const row = document.createElement('label');
            row.className = 'hw-pop-out'
                + (offered.has(t.id) ? '' : ' hw-pop-out-off');
            row.title = `${t.name} → ${t.sub}. Ticked, the tray shows a `
                + `${t.name} chip under this distro's LEGS line to drag `
                + 'onto a screen; unticked, it never does.';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = offered.has(t.id);
            cb.dataset.lrdField = `distro-out-${t.id}-${d.id}`;
            cb.addEventListener('change', () => {
                const live = this.getDistros().find(x => x.id === d.id) || d;
                const now = new Set(this.distroOutputs(live).map(x => x.id));
                if (cb.checked) now.add(t.id); else now.delete(t.id);
                patch({ outputs: this.getDistroOutputTypes()
                    .map(x => x.id).filter(id => now.has(id)) });
            });
            row.appendChild(cb);
            row.appendChild(this.plugGlyph(t.glyph));
            const name = document.createElement('b');
            name.textContent = t.name;
            row.appendChild(name);
            const sub = document.createElement('small');
            sub.className = 'hw-pop-out-sub';
            t.faces.forEach(f => sub.appendChild(this.plugGlyph(f)));
            sub.appendChild(document.createTextNode(t.sub));
            row.appendChild(sub);
            outs.appendChild(row);
        });
        const hint = document.createElement('div');
        hint.className = 'hw-pop-outs-hint';
        hint.textContent = 'Unticked types never show as chips. A distro '
            + 'with nothing ticked still drags whole onto a screen, as it '
            + 'always has.';
        outs.appendChild(hint);
        wrap.appendChild(outs);

        const remove = document.createElement('button');
        remove.className = 'btn hw-pop-remove';
        remove.textContent = 'Remove distro';
        remove.title = 'Remove this power source. Multis assigned to it '
            + 'come free; undo puts it back.';
        remove.dataset.lrdField = `distro-del-${d.id}`;
        remove.addEventListener('click', () => {
            if (typeof this._hwPopoverClose === 'function') {
                this._hwPopoverClose();
            }
            this.removeDistro(d.id);
            // The distro is gone and its id never comes back, so its fold
            // keys go with it - the dock section's, and the per-number
            // multi keys under it (a prefix sweep catches however many the
            // tray ever drew).
            try {
                localStorage.removeItem(
                    `ledRasterPanelCollapsed_hwdock-distro-${d.id}`);
                const prefix =
                    `ledRasterPanelCollapsed_hwdock-multi-${d.id}-`;
                Object.keys(localStorage)
                    .filter(k => k.startsWith(prefix))
                    .forEach(k => localStorage.removeItem(k));
            } catch (_) { /* blocked storage never held the key */ }
            this._restateNaming();
        });
        wrap.appendChild(remove);
        return wrap;
    }


    // Every surface a name reaches, restated together.
    //
    // Renaming a distro or a multi, or landing a multi on a distro, renumbers
    // or renames circuits across the WHOLE show. Redrawing the panel that was
    // clicked and leaving the wall behind would put two different answers on
    // screen at once, so the prepared index is dropped and everything that
    // reads it is rebuilt from one place.
    //
    // The wall redraws immediately; the PANELS wait a macrotask. Every caller
    // here fires from a field's own `change` handler, which runs mid-Tab, and
    // a synchronous wipe destroys the field the gesture is landing in - see
    // _rebuildAfterGesture.
    _restateNaming() {
        this._circuitTailCache = null;
        if (window.canvasRenderer) window.canvasRenderer.render();
        this._rebuildAfterGesture(() => {
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            // The dock is where the naming shows now - headers, chips,
            // strip - so ONE render covers what four panel wipes did
            // (refreshDistroPanel is this same render under its old name).
            this.renderHardwareDock && this.renderHardwareDock();
        });
    }

    // Why this screen's plan is empty, when a POWER ERROR is why - the
    // sentence, minus its lead-in, so the soca host ("No circuits — ...")
    // and the label editor ("No circuits to edit — ...") share one story.
    //
    // Live repro: a 13-wide screen of 200W panels at 110V/15A in organized
    // row mode cannot fit a row on a circuit, so the plan is empty - and the
    // soca panel rendered NOTHING, which read as the soca feature being
    // broken. The explanation lived only in the left sidebar and the red
    // wall tint. Every other empty state stays blank: a non-screen layer, a
    // screen with nothing visible on it, a group member counted on its
    // owner, and a custom-routed screen (whose drawn paths supersede the
    // auto error - the same rule updatePowerCapacityDisplay applies to
    // _powerError) have no error to explain.
    _socaPlanEmptyReason(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        if (this.usesCustomCircuits(layer)) return null;
        const err = this.calculatePowerAssignments(layer).error;
        if (!err) return null;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const fmt = (w) => `${Math.round(w).toLocaleString()} W`;
        const circuit = `a circuit at ${voltage} V / ${amperage} A carries ${fmt(voltage * amperage)}`;
        if (err.unitType) {
            const across = err.unitType === 'row' ? 'column' : 'row';
            return `a full ${err.unitType} is ${fmt(err.unitLoad || 0)} and ${circuit}. `
                + `Fix in Power Settings: higher voltage or amperage, a ${across} pattern, or a custom path `
                + `(select a narrower block and apply a pattern — circuits cut at capacity).`;
        }
        // PANEL WATTS EXCEED CIRCUIT CAPACITY: one cabinet alone is over,
        // so no pattern can help.
        return `one panel is ${fmt(parseFloat(layer.panelWatts) || 0)} and ${circuit}. `
            + `Fix in Power Settings: higher voltage or amperage.`;
    }

    // The soca tiles died with the Power sidebar - a multi's name and
    // home-run length edit inline on its dock multi header, and the
    // empty-plan story tells on the dock's strip - so what is left under
    // this name is syncing the per-screen knobs that moved into the left
    // sidebar's Power Settings: the breakout type and the map brackets.
    // Static controls, synced in place (never wiped), so there is no focus
    // to preserve; a control someone is standing in is left alone.
    refreshSocaRuns() {
        const sel = document.getElementById('power-breakout-type');
        const brk = document.getElementById('show-soca-brackets');
        if (!sel && !brk) return;
        this._wireScreenPowerKnobs();
        const layer = this.currentLayer;
        const screen = layer && (layer.type || 'screen') === 'screen';
        if (sel) {
            if (!sel.options.length) {
                this.getPowerBreakoutTypes().forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.name;
                    sel.appendChild(opt);
                });
            }
            // Eligibility follows the screen's voltage (user ruling: a
            // 110V screen can only have 110V Edison on it; the L21-30 box
            // is 3 x 208V). Disabled, not removed: the list stays stable
            // and a stored incompatible choice keeps displaying - the
            // mismatched-phasing doctrine, applied to breakouts.
            if (screen) {
                const v = layer.powerVoltage;
                const types = this.getPowerBreakoutTypes();
                Array.from(sel.options).forEach(opt => {
                    const t = types.find(x => x.id === opt.value);
                    const ok = !t || this._breakoutEligible(t, v);
                    // Only a STORED choice earns the exemption - it keeps
                    // displaying and re-selecting; an unset screen has no
                    // paperwork to defend.
                    opt.disabled = !ok && opt.value !== layer.powerBreakoutType;
                    opt.title = ok ? '' : `Not available at ${v} V.`;
                });
            }
            if (screen && sel !== document.activeElement) {
                sel.value = this.getPowerBreakout(layer).id;
            }
        }
        if (brk && brk !== document.activeElement) {
            // OFF unless explicitly ticked (=== true, matching the canvas
            // gate): brackets started life on by default and the user asked
            // for them unselected. A field never touched now means off, on
            // old projects too.
            brk.checked = !!(screen && layer.showSocaBrackets === true);
        }
    }

    // The static knobs' change handlers, wired ONCE - the controls live in
    // index.html now and are never rebuilt. Multi-select doctrine
    // unchanged: a per-screen scalar edit applies to EVERY selected screen
    // (_socaPanelTargets), under the same history actions the old panel
    // rows earned.
    _wireScreenPowerKnobs() {
        if (this._screenPowerKnobsWired) return;
        this._screenPowerKnobsWired = true;
        const sel = document.getElementById('power-breakout-type');
        if (sel) sel.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.powerBreakoutType = sel.value; });
            this.updateLayers(list, true, 'Change Power Breakout');
        });
        const brk = document.getElementById('show-soca-brackets');
        if (brk) brk.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.showSocaBrackets = brk.checked; });
            this.updateLayers(list, true, 'Toggle Soca Brackets');
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        const en = document.getElementById('power-splitters-enabled');
        const mw = document.getElementById('power-splitters-maxways');
        const mwc = document.getElementById('power-splitters-maxways-custom');
        const writeAll = (patch) => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => {
                const cur = this.getPowerSplitters(l);
                l.powerSplitters = { ...cur, ...patch, manual: cur.manual };
            });
            this.updateLayers(list, true, 'Change Splitter Packing');
            this._rebuildAfterGesture(() => {
                this.refreshSplitterPanel();
                this.refreshSocaRuns();
                this.refreshDistroPanel();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        };
        if (en) en.addEventListener('change',
                                    () => writeAll({ enabled: en.checked }));
        if (mw) mw.addEventListener('change', () => {
            if (mw.value === 'custom') {
                // seed a non-stock value so the custom box appears, filled
                writeAll({ maxWays: 5 });
                return;
            }
            writeAll({ maxWays: parseInt(mw.value, 10) || 3 });
        });
        if (mwc) mwc.addEventListener('change', () => {
            writeAll({ maxWays: Math.max(2, parseInt(mwc.value, 10) || 2) });
        });
    }

    // The Splitters panel rows died with the sidebar - manual merge and
    // split are the right-click Share / Un-share on the circuit itself
    // (app-dock.js _prepareShareMenus) - so what is left under this name is
    // syncing the packing knobs that moved into Power Settings: the enable
    // checkbox, and the size row that follows it. "Present only while
    // sharing is on" (the old panel's rule) is worn as visibility on the
    // static row.
    refreshSplitterPanel() {
        const en = document.getElementById('power-splitters-enabled');
        if (!en) return;
        this._wireScreenPowerKnobs();
        const layer = this.currentLayer;
        const screen = layer && (layer.type || 'screen') === 'screen';
        const sp = screen ? this.getPowerSplitters(layer)
            : { enabled: false, maxWays: 3 };
        if (en !== document.activeElement) {
            en.checked = !!(screen && sp.enabled);
        }
        const row = document.getElementById('power-splitters-maxways-row');
        if (row) row.style.display = (screen && sp.enabled) ? 'flex' : 'none';
        const mw = document.getElementById('power-splitters-maxways');
        const mwc = document.getElementById('power-splitters-maxways-custom');
        const stock = [2, 3, 4].includes(sp.maxWays);
        if (mw && mw !== document.activeElement) {
            mw.value = stock ? String(sp.maxWays) : 'custom';
        }
        if (mwc) {
            mwc.style.display = stock ? 'none' : '';
            if (mwc !== document.activeElement && !stock) {
                mwc.value = String(sp.maxWays);
            }
        }
    }

    // Merge the selected circuits into one manual group.
    // Merge the selected circuits into one manual group. The group is stored
    // as RUN ids: for auto screens the run ordinals the selected circuits
    // currently carry, for custom screens the drawn circuit numbers. Members
    // leave any previous group and lose their split pins.
    mergeSplitterCircuits(layer, circuitNums) {
        if (!layer || !Array.isArray(circuitNums) || circuitNums.length < 2) return;
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (runIds.length < 2) return;
        this._writeSplitterManual(layer, (manual) => {
            const inNew = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !inNew.has(n)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(n => !inNew.has(n));
            manual.merge.push([...runIds].sort((a, b) => a - b));
        });
    }

    // Un-merge the selected circuits. Auto runs are additionally PINNED out
    // of packing (one circuit per run) - the pin is what defeats a re-pack;
    // custom circuits just fall back to their drawn numbering.
    // `action` (optional) names the history entry - the batch verb's
    // "Un-share all" passes its own so the step reads as what it was.
    splitSplitterCircuits(layer, circuitNums, action) {
        if (!layer || !Array.isArray(circuitNums) || !circuitNums.length) return;
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (!runIds.length) return;
        const custom = this.usesCustomCircuits(layer);
        this._writeSplitterManual(layer, (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(n)) : []))
                .filter(g => g.length >= 2);
            if (!custom) {
                manual.split = [...new Set([...manual.split, ...runIds])]
                    .sort((a, b) => a - b);
            }
        }, action);
    }

    // ---- the batch verb: "3fer them" ---------------------------------------
    //
    // 2026-08-30, tester + user ruling ("lets go for B and then right
    // click"): sweep a contiguous stretch of runs, right-click, and the
    // menu offers "2fer them / 3fer them / 4fer them" with the group math
    // spelled out. The verb PARTITIONS - consecutive adjacent groups dealt
    // left to right along the wall - so 18 circuits under "3fer them"
    // become six separate 3fers, never one mega-gang. Adjacency is the
    // splitter doctrine (never skip a run); over-capacity groups are
    // honored and flag OVER like every manual merge.

    // Group sizes for `count` runs dealt as Nfers. The REMAINDER RE-DEALS
    // so nothing is orphaned (user-vetoable choice, mock option (i)):
    // a remainder of 2+ becomes its own smaller fer (8 @ 3fer -> 3,3,2);
    // a remainder of 1 borrows from the last full group and goes out as
    // two 2fers (16 @ 3fer -> 3,3,3,3,2,2). Only "2fer them" over an odd
    // count leaves a single plain run - there is no smaller fer to deal.
    batchNferGroups(count, n) {
        const L = Math.max(0, Number(count) || 0);
        const size = Math.max(2, Number(n) || 2);
        let full = Math.floor(L / size);
        const rem = L % size;
        let tail = [];
        if (rem === 1 && size > 2 && full >= 1) {
            // borrow the last full group and re-deal its n+1 runs as two
            // smaller fers, biggest first: 3fer -> 2+2, 4fer -> 3+2
            full -= 1;
            const m = size + 1;
            tail = [Math.ceil(m / 2), Math.floor(m / 2)];
        } else if (rem >= 2) {
            tail = [rem];
        } else if (rem === 1) {
            tail = [1];
        }
        return Array.from({ length: full }, () => size).concat(tail);
    }

    // "6 × 3fer", "4 × 4fer + 2fer", "3 × 2fer + 1 plain" - the group math
    // the menu entry carries, so the deal is read before it is taken.
    batchNferLabel(count, n) {
        const sizes = this.batchNferGroups(count, n);
        const tally = new Map();
        sizes.forEach(s => tally.set(s, (tally.get(s) || 0) + 1));
        return [...tally.entries()].sort((a, b) => b[0] - a[0])
            .map(([sz, k]) => sz === 1
                ? `${k} plain`
                : (k === 1 ? `1 × ${sz}fer` : `${k} × ${sz}fer`))
            .join(' + ');
    }

    // Deal the chosen circuits' RUNS into Nfer groups, one manual-store
    // write, ONE history entry (`action`). Operates at the run level so an
    // existing gang inside the batch re-deals with everything else. A solo
    // remainder on an auto screen is split-PINNED so re-packing cannot
    // quietly gang what the deal left plain (custom circuits need no pin -
    // they never auto-pack). Same id-space rules as every manual edit:
    // _writeSplitterManual stamps the space the screen currently reads.
    batchShareCircuits(layer, circuitNums, n, action) {
        if (!layer || !Array.isArray(circuitNums)) return false;
        const size = Math.max(2, Number(n) || 0);
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (runIds.length < 2) return false;
        const sizes = this.batchNferGroups(runIds.length, size);
        const custom = this.usesCustomCircuits(layer);
        this._writeSplitterManual(layer, (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(x => !hit.has(x)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(x => !hit.has(x));
            let off = 0;
            sizes.forEach(sz => {
                const g = runIds.slice(off, off + sz);
                off += sz;
                if (g.length >= 2) {
                    manual.merge.push([...g].sort((a, b) => a - b));
                } else if (!custom) {
                    manual.split.push(...g);
                }
            });
            manual.split = [...new Set(manual.split)].sort((a, b) => a - b);
        }, action);
        return true;
    }

    // ---- what a CLEAR forgets ------------------------------------------------
    //
    // User ruling (2026-08-30): "when i clear a circuit, soca or a distro
    // or sending card i dont want it to remember how i had it programmed
    // before with balancing etc". A clear used to drop only the assignment
    // and leave the paperwork - the stored tail set above all - so
    // re-assigning resurrected the old balance layout. Now the clear wipes
    // the cleared thing's stored programming too, and the caller folds
    // every wipe into ONE history entry so a single undo restores all of
    // it. The split boundaries at the cleared multi's edges go too, and
    // so does every cut left between multis nobody is feeding (user
    // ruling, 2026-09-04, extending the above: a wall of one-circuit
    // multis left by circuit-pip drops read S1[1-6] S2[7] S3[8] ... after
    // a clear - "the numbering is all wrong") - see _socaClearSplitPoints.

    // The split points that survive clearing `indices` on this layer.
    // Two rules, one home:
    //
    // 1. The cleared multis' own edges. The boundary that ends each
    //    cleared multi and the one that ends the multi before it are
    //    forgotten, so the cleared circuits fall back onto the natural box
    //    grid (_socaSegments cuts at every multiple of socaBoxSize
    //    whatever is stored). A run of cleared multis inside one grid
    //    cell is treated as one: its interior cuts always go; the cut to
    //    a KEPT neighbour goes when the run has a kept neighbour on ONE
    //    side only (the run welds onto it - the neighbour keeps its
    //    identity and re-deals its tails, the un-split rule), and both
    //    cuts stay when kept multis flank the run on both sides -
    //    forgetting either would weld two multis that were not cleared
    //    into one and lose the second's distro, number and name, which
    //    the ruling never asked for. Grid lines are never stored, so a
    //    neighbour across one is not a neighbour here.
    //
    // 2. The leftovers. Every remaining stored cut that sits between two
    //    multis which are BOTH unassigned (no distro) once the clear has
    //    run goes too, welding them back onto the natural grid. On the
    //    user's own show (2026-09-04) a run of circuit-pip drops had left
    //    twelve one-circuit multis S2..S13 behind S1, already unassigned,
    //    so rule 1 alone cleared S1 and left the wall reading S1[1-6]
    //    S2[7] S3[8] ... - "if i add circuits the numbering is all wrong",
    //    and "we need to audit this so it allows me to do up to 6 if i am
    //    doing multi/soca". An unassigned cut is programming nobody is
    //    using, and a clear must not remember how the wall was programmed
    //    (the 2026-08-30 ruling above). A cut with an ASSIGNED multi on
    //    either side stays: that multi keeps its identity, its number and
    //    its circuits under its new index (_resegmentSocaStores), so a
    //    flanked run of leftovers between two fed multis keeps both cuts
    //    - rule 1's flanked case is the same test with the cleared run
    //    counted as unassigned.
    //
    // Pure: reads the stores as the caller left them (the wipe ran first,
    // so a cleared multi's distro is already gone; `indices` covers it
    // regardless) and returns the surviving points - the caller re-keys
    // with _resegmentSocaStores, so the whole clear is still ONE history
    // entry and one undo puts every cut back.
    _socaClearSplitPoints(layer, indices) {
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const stored = new Set(this._socaSplitPoints(layer, count));
        const size = this.socaBoxSize(layer);
        const cleared = new Set((indices || []).map(Number));
        const gone = new Set();
        for (let i = 0; i < segs.length; i++) {
            if (!cleared.has(segs[i].index)) continue;
            let j = i;
            while (j + 1 < segs.length && cleared.has(segs[j + 1].index)
                    && segs[j].end % size !== 0) j++;
            for (let k = i; k < j; k++) gone.add(segs[k].end);
            const before = segs[i].start - 1;
            const after = segs[j].end;
            const keptBefore = before >= 1 && before % size !== 0
                && stored.has(before);
            const keptAfter = after < count && after % size !== 0
                && stored.has(after);
            if (!(keptBefore && keptAfter)) {
                if (keptBefore) gone.add(before);
                if (keptAfter) gone.add(after);
            }
            i = j;
        }
        const assign = layer.powerSocaDistro || {};
        const fed = s => !cleared.has(s.index) && !!assign[s.index];
        for (let i = 0; i + 1 < segs.length; i++) {
            const p = segs[i].end;
            if (!stored.has(p) || gone.has(p)) continue;
            if (!fed(segs[i]) && !fed(segs[i + 1])) gone.add(p);
        }
        return [...stored].filter(p => !gone.has(p));
    }

    // One multi's circuits and their splitter run ids, read BEFORE any
    // store moves - the naming pass and the run ids describe the pre-clear
    // wall, and a wipe that changed the splitter store first would read a
    // renumbered plan.
    _socaClearTargets(layer, socaIndex) {
        const rec = this._powerNaming(layer).socas.get(Number(socaIndex));
        const circuits = rec ? rec.circuits.slice() : [];
        const runIds = [];
        if (circuits.length) {
            const inMulti = new Set(circuits);
            this.screenCircuits(layer).forEach(c => {
                if (!inMulti.has(c.num)) return;
                (c.runIds || [c.num]).forEach(id => runIds.push(id));
            });
        }
        return { circuits, runIds };
    }

    // Wipe one multi's stored programming: the (distro, number) assignment,
    // the stored tail set and legacy breaker offset, the typed name and
    // home-run length, its circuits' label overrides, and the manual
    // share/split entries covering its circuits. No history entry here -
    // the clear gestures compose members into one entry themselves. The
    // store objects are always left behind, never the properties deleted
    // whole (an absent key is missing from the update payload and the
    // server keeps whatever it had, so "cleared" would silently not clear).
    _wipeSocaProgramming(layer, socaIndex, targets) {
        const idx = Number(socaIndex);
        for (const field of ['powerSocaNumber', 'powerSocaDistro',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaLengths']) {
            if (layer[field]) delete layer[field][idx];
        }
        const t = targets || this._socaClearTargets(layer, socaIndex);
        if (layer.powerLabelOverrides) {
            t.circuits.forEach(num => {
                delete layer.powerLabelOverrides[num];
            });
        }
        // A circuit's cable is programming the same way its label override
        // is (2026-09-06): the cleared circuits forget theirs.
        if (layer.powerCircuitCables) {
            t.circuits.forEach(num => {
                delete layer.powerCircuitCables[num];
            });
        }
        this._wipeSplitterManualFor(layer, t.runIds);
    }

    // Drop the manual share (merge) groups and split pins covering the
    // given run ids, so a cleared scope re-packs naturally instead of
    // keeping hand-ganged circuits nobody is feeding any more. Unrecorded
    // by design - the clear's one entry carries it. Only the groups
    // authored in the id space the layer currently reads are touched; a
    // dormant foreign-space store is not this gesture's paperwork.
    _wipeSplitterManualFor(layer, runIds) {
        if (!runIds || !runIds.length) return false;
        const raw = layer && layer.powerSplitters;
        if (!raw || !raw.manual) return false;
        const space = this._splitterManualSpace(layer);
        if (space && space !== this._splitterIdSpace(layer)) return false;
        const cur = this.getPowerSplitters(layer);
        const hit = new Set(runIds);
        const merge = cur.manual.merge
            .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(n)) : []))
            .filter(g => g.length >= 2);
        const split = cur.manual.split.filter(n => !hit.has(n));
        if (JSON.stringify(merge) === JSON.stringify(cur.manual.merge)
                && split.length === cur.manual.split.length) {
            return false;
        }
        layer.powerSplitters = { ...cur, manual: {
            merge, split,
            space: cur.manual.space || this._splitterIdSpace(layer),
        } };
        return true;
    }

    // `action` names the history entry; the default keeps every existing
    // caller's entry byte-identical. The batch verb passes its own name
    // ('3fer Selection') so one commit is one legible undo step.
    _writeSplitterManual(layer, fn, action) {
        const cur = this.getPowerSplitters(layer);
        // An edit is made in the CURRENT id space. Groups stored from the
        // other space cannot be edited alongside it - one store, one space -
        // so the edit starts clean and the write stamps the space it was
        // authored in. Reads never get here, so merely flipping a screen
        // between custom and auto keeps the other space's groups dormant.
        const space = this._splitterIdSpace(layer);
        const foreign = this._splitterManualSpace(layer) !== space;
        const manual = {
            merge: foreign ? []
                : cur.manual.merge.map(g => (Array.isArray(g) ? g.slice() : [])),
            split: foreign ? [] : cur.manual.split.slice(),
        };
        fn(manual);
        manual.space = space;
        layer.powerSplitters = { ...cur, manual };
        this.updateLayers([layer], true, action || 'Edit Splitter Groups');
        this._rebuildAfterGesture(() => {
            this.refreshSplitterPanel();
            this.refreshSocaRuns();
            this.refreshDistroPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
    }

    // Multi-select doctrine: a panel edit applies to EVERY selected screen,
    // not just the one the panel happens to show. Per-screen scalar settings
    // (brackets toggle, breakout type) go through here; per-multi fields
    // (lengths, distro assignments) stay with their own screen's soca plan.
    _socaPanelTargets(layer) {
        const sel = this.getSelectedLayers().filter(l => (l.type || 'screen') === 'screen');
        return sel.some(l => l.id === layer.id) ? sel : [layer, ...sel];
    }

    // ---- Power splitters (circuit sharing via 2fer/3fer/4fer Y-cables) ------
    //
    // Real rigs gang multiple SHORT adjacent power runs onto ONE circuit
    // through a splitter: a wall cabled top-down in 5-tall columns with a
    // 15-tile circuit capacity feeds three adjacent columns from one feed
    // labelled S1-1, through a 3fer. The model rides on the layer:
    //   layer.powerSplitters = {
    //     enabled: false,          // AUTO packing (organized modes only)
    //     maxWays: 3,              // 2fer/3fer out of the box; any int >= 2
    //     manual: {
    //       merge: [[runId, ...], ...],   // hand-ganged runs, one group = one circuit
    //       split: [runId, ...],          // runs pinned OUT of auto packing
    //     },
    //   }
    // Run ids: the pre-packing run ordinal (1-based, traversal order) for
    // auto modes; the drawn circuit number for custom screens. Those are two
    // DIFFERENT id spaces sharing one store, so `manual.space` records which
    // one a group was authored in ('auto' | 'custom') and the groups go
    // dormant - not deleted - while the screen reads the other space. The
    // reference show proved why: a tower's 3fer merges, drawn over its 12
    // per-row custom circuits, rode along after the screen went back to an
    // auto pattern and silently re-ganged auto run ordinals 7-9 into an
    // over-capacity 3fer the user never asked for.

    // Normalized read - the raw field may be absent or partial.
    getPowerSplitters(layer) {
        const raw = (layer && layer.powerSplitters) || {};
        const mw = parseInt(raw.maxWays, 10);
        const manual = raw.manual || {};
        return {
            enabled: !!raw.enabled,
            maxWays: Number.isFinite(mw) && mw >= 2 ? mw : 3,
            manual: {
                merge: Array.isArray(manual.merge) ? manual.merge : [],
                split: Array.isArray(manual.split) ? manual.split : [],
                space: (manual.space === 'auto' || manual.space === 'custom')
                    ? manual.space : null,
            },
        };
    }

    // The id space the layer's circuits read RIGHT NOW: drawn circuit
    // numbers for a screen routing custom, pre-packing run ordinals for
    // every auto pattern.
    _splitterIdSpace(layer) {
        return this.usesCustomCircuits(layer) ? 'custom' : 'auto';
    }

    // The id space the STORED manual groups belong to. Stamped on every
    // manual edit; a legacy file carries no stamp, so the space is inferred
    // from the only evidence the file holds: a screen routing custom read
    // its groups against the drawn numbers (unchanged), a pure auto screen
    // against its run ordinals (unchanged) - but an auto screen still
    // carrying DORMANT drawn circuits (non-empty custom power paths outside
    // its override numbers, kept from a retired custom routing) authored its
    // groups against those drawn numbers, so the groups stay dormant with
    // the paths instead of being misapplied to run ordinals that merely
    // share the digits.
    _splitterManualSpace(layer) {
        const stamped = this.getPowerSplitters(layer).manual.space;
        if (stamped) return stamped;
        if (this.usesCustomCircuits(layer)) return 'custom';
        const overridden = new Set(this.getOverrideNums(layer, 'power'));
        const paths = (layer && layer.powerCustomPaths) || {};
        const dormantDrawn = Object.keys(paths).some(n =>
            (paths[n] || []).length > 0 && !overridden.has(parseInt(n, 10)));
        return dormantDrawn ? 'custom' : 'auto';
    }

    // Validated-on-read manual groups against the run ids that currently
    // exist. Ids that no longer resolve are silently dropped; a group left
    // with fewer than two members dissolves; a run can sit in only one group
    // (first wins), and a run inside a group cannot also be split-pinned.
    // Groups authored in the OTHER id space (see the run-id doctrine above)
    // are dormant here: an id is a number, not a circuit, and only its own
    // space can say which circuit it named.
    appliedSplitterGroups(layer, validIds) {
        if (this._splitterManualSpace(layer) !== this._splitterIdSpace(layer)) {
            return { merge: [], split: [] };
        }
        const sp = this.getPowerSplitters(layer);
        const valid = new Set((validIds || []).map(n => parseInt(n, 10)));
        const used = new Set();
        const merge = [];
        for (const g of sp.manual.merge) {
            if (!Array.isArray(g)) continue;
            const ids = [...new Set(g.map(n => parseInt(n, 10)))]
                .filter(n => valid.has(n) && !used.has(n))
                .sort((a, b) => a - b);
            if (ids.length < 2) continue;
            ids.forEach(n => used.add(n));
            merge.push(ids);
        }
        const split = [...new Set(sp.manual.split.map(n => parseInt(n, 10)))]
            .filter(n => valid.has(n) && !used.has(n))
            .sort((a, b) => a - b);
        return { merge, split };
    }

    // Pack runs into circuits. Greedy over CONSECUTIVE runs only - never
    // skip a run to gang two non-neighbours: a circuit keeps taking the next
    // run while the summed load fits wattsPerCircuit and the branch count
    // stays within maxWays (the packer thereby uses the smallest splitter
    // that fits: none, then 2fer, then 3fer). A run that does not fit closes
    // the circuit and starts the next. Manual overrides ride the same walk:
    // a merge group is emitted whole as one circuit when its first member is
    // reached (honored even over capacity - the soca `over` convention flags
    // it); a split-pinned run is its own circuit and a boundary.
    // Returns { circuits, runs, runIds } index-aligned: circuits[i] is the
    // concatenated panels, runs[i] the per-branch panel counts, runIds[i]
    // the run ordinals ganged into that circuit.
    _packPowerRuns(runs, wattsPerCircuit, maxWays, manual) {
        const N = runs.length;
        const groupOf = new Map();
        ((manual && manual.merge) || []).forEach(g =>
            g.forEach(id => groupOf.set(id, g)));
        const splitSet = new Set((manual && manual.split) || []);
        const consumed = new Set();
        const circuits = [], counts = [], runIds = [];
        for (let i = 0; i < N; i++) {
            const id = i + 1;
            if (consumed.has(id)) continue;
            let members;
            const g = groupOf.get(id);
            if (g) {
                members = g.filter(n => !consumed.has(n));
            } else if (splitSet.has(id)) {
                members = [id];
            } else {
                members = [id];
                let load = runs[i].load;
                for (let j = i + 1; j < N; j++) {
                    const nid = j + 1;
                    if (members.length >= maxWays) break;
                    if (groupOf.has(nid) || splitSet.has(nid)) break;
                    if (load + runs[j].load > wattsPerCircuit) break;
                    members.push(nid);
                    load += runs[j].load;
                }
            }
            members.forEach(n => consumed.add(n));
            circuits.push(members.flatMap(n => runs[n - 1].panels));
            counts.push(members.map(n => runs[n - 1].panels.length));
            runIds.push(members.slice());
        }
        return { circuits, runs: counts, runIds };
    }

    // The drawn path steps a (possibly merged) custom circuit covers - the
    // label sheets stamp every tile of a shared circuit with the ONE label,
    // so the sticker run for merged circuit `num` concatenates every member
    // path, not just the primary's.
    _splitterMergedPathFor(layer, num) {
        const paths = (layer && layer.powerCustomPaths) || {};
        const own = paths[num] || [];
        const drawnNums = Object.keys(paths)
            .map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && (paths[n] || []).length > 0);
        const groups = this.appliedSplitterGroups(layer, drawnNums).merge;
        const g = groups.find(x => x[0] === parseInt(num, 10));
        if (!g) return own;
        return g.flatMap(n => paths[n] || []);
    }

    calculatePowerAssignments(layer) {
        if (!layer || (layer.type || 'screen') === 'image' || !Array.isArray(layer.panels)) return { circuits: [], error: null };

        // v0.12: a screen group whose members are the same panel AND the same
        // wattage packs its circuits as ONE BIGGER SCREEN - see getAutoRoutePlan
        // (app-screen-info.js). Null for every ungrouped screen and for a group
        // that matches on resolution but not on watts, and then every line below
        // is the line it always was.
        const plan = (typeof this.getAutoRoutePlan === 'function')
            ? this.getAutoRoutePlan(layer, 'power') : null;
        if (plan && !plan.isOwner) {
            // The wall's circuits are the first member's and are counted there.
            // Same only-honest-zero rule a member fed by a peer's hand-drawn
            // circuit already follows. The member's own OVERRIDDEN circuits are
            // the one exception: a redrawn circuit lives in its own layer's
            // numbering space, so it is reported here, by the layer that owns
            // it, and nowhere else.
            return this._mergeOverrideCircuits(layer, { circuits: [], error: null });
        }

        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const pattern = layer.powerFlowPattern || 'tl-h';
        const maximize = !!layer.powerMaximize;
        const organized = !!layer.powerOrganized && !maximize;
        const isHorizontalFirst = pattern.includes('-h');
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');

        if (wattsPerCircuit <= 0 || panelWatts <= 0) {
            return { circuits: [], error: null };
        }

        // The wall's grid and the screen each cabinet sits on. Without a plan
        // these are the layer's own, so nothing below can tell the difference.
        const gridRows = plan ? plan.rows : layer.rows;
        const gridCols = plan ? plan.columns : layer.columns;
        const rowOfPanel = plan ? (p => plan.rowOf.get(p)) : (p => p.row);
        const colOfPanel = plan ? (p => plan.colOf.get(p)) : (p => p.col);
        const panelOwners = new Map();
        if (plan) plan.ordered.forEach(c => panelOwners.set(c.panel, c.layer));
        const layerOfPanel = plan ? (p => panelOwners.get(p) || layer) : (() => layer);

        // The load factor is a HALF-TILE derate, so it is read against the
        // cabinet's own screen; the wattage is the group's, which the gate has
        // already proved every member agrees on.
        const loadOf = (panel) => panelWatts * this.getPanelLoadFactor(layerOfPanel(panel), panel);
        // Per-run overrides: a cabinet on a hand-drawn override anywhere in
        // the path scope is already fed, so the automatic walk lays over
        // everything else. Empty for every project without overrides, and
        // then the filters below keep every list byte-identical.
        const claimed = (typeof this._overrideClaims === 'function')
            ? this._overrideClaims(layer, 'power') : new Set();
        const unclaimed = (panels) => (claimed.size === 0
            ? panels : panels.filter(p => !claimed.has(p)));
        const visibleOrdered = unclaimed(plan
            ? plan.ordered.filter(c => !c.panel.hidden).map(c => c.panel)
            : this.getOrderedPanelsByPattern(layer, pattern, false));
        if (visibleOrdered.length === 0) {
            return this._mergeOverrideCircuits(layer, { circuits: [], error: null });
        }

        if (panelWatts > wattsPerCircuit) {
            return { circuits: [], error: { message: 'PANEL WATTS EXCEED CIRCUIT CAPACITY' } };
        }

        // `layers`, index-aligned with `circuits` the way screenCircuits has
        // written it for hand-drawn cross-member paths since v0.11.0, so the
        // soca planner charges every cabinet at its OWN member's wattage and the
        // power tinting can key a peer's cabinet by (layer, row, col). Under the
        // crossing gate the members all share panelWatts, so the plan's figure
        // comes out right either way - it is set anyway, because a total that is
        // only ACCIDENTALLY correct is a total nobody can trust the next time
        // the gate moves. The key is added only when the route actually crosses,
        // so an ungrouped screen's return shape does not move at all.
        const withOwners = (result) => {
            if (!plan) return result;
            result.layers = (result.circuits || [])
                .map(panels => (panels || []).map(p => layerOfPanel(p)));
            return result;
        };

        const circuits = [];
        if (organized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(gridRows).keys()].map(i => (startsTop ? i : (gridRows - 1 - i)))
                : [...Array(gridCols).keys()].map(i => (startsLeft ? i : (gridCols - 1 - i)));

            // Splitter packing: one RUN per unit (row/column) - each branch
            // is its own short daisy fed at its head, the physical truth of
            // a wall cabled top-down - then _packPowerRuns gangs consecutive
            // runs onto shared circuits within maxWays and capacity. The
            // single-unit-too-big error is unchanged. Off by default; the
            // default path below is byte-identical to the pre-splitter code.
            const splitters = this.getPowerSplitters(layer);
            if (splitters.enabled) {
                const runs = [];
                for (const idx of unitIndices) {
                    const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                    if (unitPanels.length === 0) continue;
                    const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                    if (unitLoad > wattsPerCircuit) {
                        return {
                            circuits: [],
                            error: {
                                message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                                unitType: isHorizontalFirst ? 'row' : 'column',
                                unitCount: isHorizontalFirst ? gridCols : gridRows,
                                // the offending unit's own watts, so the empty
                                // soca panel can say WHY with real figures
                                unitLoad
                            }
                        };
                    }
                    runs.push({
                        panels: unclaimed(this.getOrganizedPanelsForUnits(
                            layer, pattern, isHorizontalFirst, [idx], false, plan)),
                        load: unitLoad,
                    });
                }
                const manual = this.appliedSplitterGroups(
                    layer, runs.map((_, i) => i + 1));
                const packed = this._packPowerRuns(
                    runs, wattsPerCircuit, splitters.maxWays, manual);
                return this._mergeOverrideCircuits(layer, withOwners({
                    circuits: packed.circuits, runs: packed.runs,
                    runIds: packed.runIds, error: null }));
            }

            let current = { unitIndices: [], load: 0 };

            for (const idx of unitIndices) {
                const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                if (unitPanels.length === 0) continue;
                const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                if (unitLoad > wattsPerCircuit) {
                    return {
                        circuits: [],
                        error: {
                            message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                            unitType: isHorizontalFirst ? 'row' : 'column',
                            unitCount: isHorizontalFirst ? gridCols : gridRows,
                            // the offending unit's own watts, so the empty
                            // soca panel can say WHY with real figures
                            unitLoad
                        }
                    };
                }
                if (current.load > 0 && current.load + unitLoad > wattsPerCircuit) {
                    circuits.push(unclaimed(
                        this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false, plan)
                    ));
                    current = { unitIndices: [], load: 0 };
                }
                current.unitIndices.push(idx);
                current.load += unitLoad;
            }
            if ((current.unitIndices || []).length > 0) {
                circuits.push(unclaimed(
                    this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false, plan)
                ));
            }
        } else {
            let current = [];
            let currentLoad = 0;
            visibleOrdered.forEach(panel => {
                const load = loadOf(panel);
                if (load <= 0) return;
                if (currentLoad > 0 && currentLoad + load > wattsPerCircuit) {
                    circuits.push(current);
                    current = [];
                    currentLoad = 0;
                }
                current.push(panel);
                currentLoad += load;
            });
            if (current.length > 0) circuits.push(current);
        }

        return this._mergeOverrideCircuits(layer, withOwners({ circuits, error: null }));
    }

    // Fold this layer's overridden circuits into an automatic result: the
    // auto rows take numbers 1, 2, 3... SKIPPING every overridden number, the
    // override rows come in under the numbers the user took over, and the
    // whole set is handed back in ascending circuit order. `nums` appears on
    // the result ONLY when overrides are in play, so every other project's
    // return shape does not move by a key. On an error the automatic story is
    // the story - same as the ports side - and the result passes through.
    _mergeOverrideCircuits(layer, result) {
        if (result.error) return result;
        const reserved = (typeof this.getOverrideNums === 'function'
            && !this.isCustomPower(layer))
            ? this.getOverrideNums(layer, 'power') : [];
        if (reserved.length === 0) return result;
        const overrides = this._ownOverrideRuns(layer, 'power');
        const rows = [];
        let next = 1;
        (result.circuits || []).forEach((panels, i) => {
            while (reserved.includes(next)) next++;
            rows.push({
                num: next++,
                panels,
                layers: result.layers ? result.layers[i] : null,
                runs: result.runs ? result.runs[i] : null,
                runIds: result.runIds ? result.runIds[i] : null,
            });
        });
        const crossing = overrides.some(o => o.hits.some(h => h.layer.id !== layer.id));
        overrides.forEach(o => {
            rows.push({
                num: o.num,
                panels: o.hits.map(h => h.panel),
                layers: (result.layers || crossing)
                    ? o.hits.map(h => h.layer) : null,
                runs: result.runs ? [o.hits.length] : null,
                runIds: null,
            });
        });
        rows.sort((a, b) => a.num - b.num);
        const out = { circuits: rows.map(r => r.panels), error: null, nums: rows.map(r => r.num) };
        if (result.layers || crossing) {
            // Owner rows for the auto circuits that never had any: every
            // cabinet is this layer's own. _powerOwnerIdRows nulls those rows
            // back out downstream, so the tinting fast path stays untouched.
            out.layers = rows.map(r => r.layers || (r.panels || []).map(() => layer));
        }
        if (result.runs) {
            out.runs = rows.map(r => r.runs);
            out.runIds = rows.map(r => r.runIds);
        }
        return out;
    }

    // The label this port takes off the processor, or null when it takes none
    // - which is every port of every project that defines no processor.
    //
    // Split out from getPortLabelText only so the label editor can ask the
    // same question without re-deriving it: it needs to know not just what the
    // label is but where it came from, because a box the user can type in that
    // no longer changes the drawing is a trap.
    getProcessorPortLabel(layer, portNum) {
        const onProcessor = this._processorPortLabels
            && this._processorPortLabels[String(layer && layer.id)];
        return (onProcessor && onProcessor[portNum]) || null;
    }

    // The same question for the RETURN end of the same socket. A separate
    // lookup rather than a suffix rule here, because the return label is now
    // resolved where the primary is (resolve_card): a name typed on the
    // return end wins, and only an untyped one derives from the primary
    // (deriveReturnLabel). Same per-frame budget as the primary: two object
    // lookups, nothing resolved.
    getProcessorPortReturnLabel(layer, portNum) {
        const onProcessor = this._processorPortReturnLabels
            && this._processorPortReturnLabels[String(layer && layer.id)];
        return (onProcessor && onProcessor[portNum]) || null;
    }

    // The return end's name when nobody typed one: the primary with its
    // leading P turned into an R, else the primary with an R after it.
    //
    // P is primary and R is redundant - that is what the screen's own
    // templates say (P# out, R# back), and a card named P1 has to read the
    // same way: P1-1 out, R1-1 back, never P1-1R. Case follows the name
    // (p1-1 back as r1-1). The P is a prefix only when what follows it is
    // not a letter - a digit (P1-1), a separator (P-1), or nothing (P); a P
    // that begins a word (PORT-3, PANEL-2, Px) is the first letter of a
    // name and there is nothing to swap. Those, and every primary with no
    // P at all - SR-1, HOUSE-LEFT - keep the R after them, so a drawing
    // already issued with SR-1R prints SR-1R again.
    //
    // The server states this rule in derive_return_label (processor_catalog)
    // and every resolved port arrives with its return already derived; this
    // copy exists for the Processors panel's placeholders, which advertise
    // the rule before a port has a label, and as the frame loop's fallback
    // for an index with no return entry. A test holds the two byte-for-byte.
    deriveReturnLabel(primary) {
        if (!primary) return null;
        const first = primary.charAt(0);
        // ASCII letters only, spelt the same way the server spells it, so
        // the two copies cannot disagree over what counts as a letter.
        const word = /^[A-Za-z]/.test(primary.slice(1, 2));
        if (!word) {
            if (first === 'P') return `R${primary.slice(1)}`;
            if (first === 'p') return `r${primary.slice(1)}`;
        }
        return `${primary}R`;
    }

    // The one place a port's label is decided. The canvas, both label editors
    // and every export come through here, so a rule added here reaches all of
    // them at once - and a second path added anywhere else would print one
    // thing on screen and another on the PDF.
    getPortLabelText(layer, portNum, type) {
        // THE PROCESSOR NAMES ITS OWN PORTS, AND IT WINS OUTRIGHT.
        //
        // A port that is assigned to a sending-card port takes that port's
        // label - the name on the card or the box a tech is standing in front
        // of - and no per-layer override applies to it. That is the point of
        // the Processors panel: the wall labels itself off the machine driving
        // it instead of off a template typed into every screen. The way to
        // change an assigned port's label is to rename the port, or the card,
        // in the Processors panel; both ends of the run take that name.
        //
        // BOTH ENDS, NOT THE SAME TEXT. A redundant loop leaves the socket and
        // comes back to it, so the two ends print at opposite corners of the
        // wall and the drawing is the only thing saying which is which. Two
        // labels reading SR-1 make a backup run impossible to trace, which is
        // the one job the return label has. The return end is nameable in the
        // Processors panel the same way the primary is - the house's backup
        // loom is often labelled off its own series, BU-1 back for SR-1 out -
        // and a typed name arrives here through the return index. With none
        // typed the return is derived from the primary (deriveReturnLabel):
        // P1-1 out, R1-1 back - which is what P1 / R1 said before a
        // processor was naming anything - and SR-1 out, SR-1R back where
        // there is no P to swap.
        //
        // _processorPortLabels and _processorPortReturnLabels are flat
        // layerId -> portNum -> label lookups, rebuilt only when the
        // assignment changes (see _indexAssignmentLabels in
        // app-port-assignment.js). This runs for every port of every screen
        // on every frame, so it must never resolve anything itself.
        const assigned = this.getProcessorPortLabel(layer, portNum);
        if (type === 'return') {
            const assignedReturn = this.getProcessorPortReturnLabel(layer, portNum);
            if (assignedReturn) return assignedReturn;
            if (assigned) return this.deriveReturnLabel(assigned);
        } else if (assigned) {
            return assigned;
        }

        // No processor in the project, or a port that is not on one: exactly
        // what every project did before processors existed, override included.
        // This is the fallback that keeps drawings already issued printing the
        // labels they were issued with.
        const template = type === 'return' ? (layer.portLabelTemplateReturn || 'R#') : (layer.portLabelTemplatePrimary || 'P#');
        const overrides = type === 'return' ? (layer.portLabelOverridesReturn || {}) : (layer.portLabelOverridesPrimary || {});
        if (overrides && overrides[portNum]) return overrides[portNum];
        return template.replace('#', portNum);
    }

    // The template broken into the parts a label is built from:
    // <prefix><number><separator>#<suffix>, e.g. S1-#, S2-#, MULTI3-#.
    // `ok` is false for a template with no multi number in it at all (C#),
    // which has no multi concept to name and falls back to the raw replace.
    _powerTemplateParts(layer) {
        const raw = String((layer && layer.powerLabelTemplate) || 'S1-#');
        const m = raw.match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
        if (!m) return { ok: false, raw, prefix: '', start: 1, sep: '-', suffix: '' };
        return {
            ok: true, raw,
            prefix: m[1], start: parseInt(m[2], 10) || 1,
            sep: m[3], suffix: m[4],
        };
    }

    // A DERIVED multi name is <base><number> - a distro named SL numbers its
    // multis SL1, SL2, and that shape reads correctly. A base that ITSELF
    // ends in a digit does not: the default distro name is DISTRO 1, and
    // glueing its multis on printed DISTRO 11, DISTRO 12 - unreadable as
    // anything but distros eleven and twelve. So a digit-ending base takes a
    // separator before the number - the same one the screen's label template
    // carries (the '-' of S1-#), so the circuit labels built on top of the
    // name stay in one register: DISTRO 1-1 yields DISTRO 1-1-1..-6.
    // Only derived names come through here. A hand-typed multi name is the
    // user's text and is never reformatted.
    _deriveMultiName(base, number, tpl) {
        const sep = /\d$/.test(base) ? ((tpl && tpl.sep) || '-') : '';
        return `${base}${sep}${number}`;
    }

    // Old projects keyed the per-multi stores - lengths, tail positions,
    // breaker offsets, distro assignments - by the number the SCREEN's own
    // template produced, so `S3-#` stored its multis under 3, 4, 5. That was
    // only safe while the number WAS the identity. It is not any more: a
    // multi's number now comes from the distro it lands on, so keying by it
    // would orphan a multi's length and its tails the moment it was assigned.
    //
    // The stable identity is (layer, socaIndex) - the 1-based ordinal of the
    // multi inside its own screen's circuit plan - exactly as a port is
    // identified by (layerId, index) on the Data tab. The shift back to it is
    // the template's own start digit minus one, which is zero for every
    // project on the default `S1-#`.
    _socaKeyShift(layer) {
        return Math.max(0, this._powerTemplateParts(layer).start - 1);
    }

    // Rekey one layer's per-multi stores onto the stable index, once.
    //
    // The stamp is what makes it once: it rides on the layer through every
    // save path, so a project that has already been rekeyed is never shifted a
    // second time - which on an `S3-#` screen would walk its keys down past 1
    // and delete them.
    migrateSocaKeying(layer) {
        if (!layer || layer.powerSocaKeying === 'index') return false;
        layer.powerSocaKeying = 'index';
        const shift = this._socaKeyShift(layer);
        if (!shift) return false;
        let changed = false;
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const map = layer[field];
            if (!map || typeof map !== 'object') continue;
            const next = {};
            for (const key of Object.keys(map)) {
                const n = parseInt(key, 10);
                // Not a multi number, so not ours to move. Carried across
                // rather than dropped: this pass rewrites the store, and
                // anything it did not understand still has to survive it.
                if (!Number.isFinite(n)) { next[key] = map[key]; continue; }
                const idx = n - shift;
                if (idx >= 1) next[idx] = map[key];
            }
            layer[field] = next;
            changed = true;
        }
        return changed;
    }

    // What a multi is CALLED, and which physical tail of its 6-way fan each
    // circuit lands on - for the whole show, prepared once.
    //
    // It is show-wide because a multi's number is: numbering runs per distro,
    // over every screen, in layer-list order BOTTOM UP - which is project
    // layer order, the same order the Data tab hands out card ports
    // (_assignmentScreens: "project layer order, untouched"). Numbering per
    // screen is what let two screens both own an S1.
    //
    // THE NAME LADDER, top wins, mirroring manual -> box -> card -> processor
    // on the Data tab:
    //   1. an explicit powerLabelOverrides entry - handled by the label
    //      authority itself, because that names one CIRCUIT, not a multi
    //   2. the multi's own name, if somebody typed one
    //   3. the distro's name plus the multi's number under it: two multis on
    //      a distro named SL are SL1 and SL2, so their circuits read SL1-1..6.
    //      A digit-ending distro name gets a separator first (_deriveMultiName):
    //      DISTRO 1's multis are DISTRO 1-1, DISTRO 1-2, never DISTRO 11
    //   4. the screen's powerLabelTemplate prefix plus the number - the
    //      fallback for a multi on no distro. Numbered PER SCREEN from the
    //      template's own number (S1-# -> S1, S2, S3 on every screen that
    //      carries it), never out of a show-wide bucket: uniqueness across
    //      screens is the distro's job, not the template's (ruling
    //      2026-09-03, "SL main starts with 7-1")
    //
    // The circuits a screen is NAMED by. For an automatic screen that is its
    // plan. For a screen in custom mode it is the circuits the user DREW
    // and nothing else - never the automatic requirement screenCircuits
    // offers an unrouted custom screen for the distro roll-ups. That
    // fallback is the right count of cables to order, but as a naming
    // source it is a phantom: on the user's 28-wide wall it is empty (a
    // full row does not fit one circuit) and on a narrower wall it is 52
    // circuits that vanish the moment the first cabinet is clicked. A label
    // read off it named the active circuit by boxes that were never going
    // to exist (user, 2026-09-03: "i dont even have a port drawn and it
    // shows S3-1 but when i draw it changes to 1-1"). An unrouted custom
    // screen has no multis, so it takes no multi numbers and shifts no
    // other screen's - its first drawn circuit opens its first box.
    _labelCircuits(layer) {
        if (!layer || typeof this.screenCircuits !== 'function') return [];
        if (this.isCustomPower(layer) && !this.usesCustomCircuits(layer)) return [];
        return this.screenCircuits(layer) || [];
    }

    // Cached by layer object for the current render burst and dropped on the
    // next microtask: getPowerCircuitLabel runs for every circuit of every
    // screen on every frame, so it must never walk the show itself.
    _powerNaming(layer) {
        if (!this._circuitTailCache) {
            this._circuitTailCache = new Map();
            Promise.resolve().then(() => { this._circuitTailCache = null; });
        }
        let entry = this._circuitTailCache.get(layer);
        if (entry) return entry;
        // A miss rebuilds the WHOLE show, not this layer: one screen's numbers
        // depend on every screen before it, so there is no such thing as
        // naming one of them on its own.
        const screens = ((this.project && this.project.layers) || [])
            .filter(l => (l.type || 'screen') === 'screen');
        // Every pinned number per distro, collected BEFORE any number is
        // issued: auto numbering deals around a pin wherever it sits in
        // layer order, the way auto port numbering deals around a pinned
        // port. The circuit plans are kept and handed down so each screen
        // is planned once per rebuild, not once per pass.
        const pins = new Map();         // distro id -> Set(pinned numbers)
        const circuitsBy = new Map();
        for (const l of screens) {
            const circuits = this._labelCircuits(l);
            circuitsBy.set(l, circuits);
            const assign = l.powerSocaDistro || {};
            const chosen = l.powerSocaNumber || {};
            const count = this._socaSegments(l, circuits.length).length;
            for (let idx = 1; idx <= count; idx++) {
                // A pin means nothing off a distro: the number is the slot on
                // a physical box, and with no box named there is no slot.
                const d = assign[idx];
                const n = parseInt(chosen[idx], 10);
                if (!d || !Number.isFinite(n) || n < 1) continue;
                const set = pins.get(d) || new Set();
                set.add(n);
                pins.set(d, set);
            }
        }
        const seq = new Map();          // distro id ('' = unassigned) -> issued
        for (const l of screens) {
            this._circuitTailCache.set(l,
                this._namingFor(l, seq, pins, circuitsBy.get(l)));
        }
        // Second pass, once every multi has its number: two multis pinned to
        // one (distro, number) are ONE physical box, and a box's tails can
        // only be dealt with every member on the table.
        this._resolveSharedSocas(screens);
        entry = this._circuitTailCache.get(layer);
        if (!entry) {
            // A screen no project holds - a preset preview, a paste in
            // flight. Number it on its own rather than leave it nameless.
            // A pin on such a screen has no show to share with, so it
            // resolves standalone: stored tails or the natural 1..L.
            entry = this._namingFor(layer, new Map(), new Map());
            for (const rec of entry.socas.values()) {
                if (!rec.pinned) continue;
                rec.positions = this.socaCircuitPositions(
                    // read the STORE only - rec.positions is still null, so
                    // the pinned branch below cannot answer yet. The
                    // breakout type rides along so the tail clamp reads the
                    // screen's own box size, not the default six.
                    { powerSocaPhasePos: layer.powerSocaPhasePos,
                      powerBreakoutType: layer.powerBreakoutType },
                    rec.index, rec.circuits.length);
                rec.moved = !rec.positions.every((p, i) => p === i + 1);
                rec.circuits.forEach((num, i) => entry.slots.set(num, {
                    multi: rec.index, number: rec.number, name: rec.name,
                    tail: rec.positions[i], moved: rec.moved,
                }));
            }
            this._circuitTailCache.set(layer, entry);
        }
        return entry;
    }

    // One screen's share of the naming index, taking its numbers from the
    // running per-distro sequence the caller carries across screens - and
    // dealing those numbers around `pins`, the show-wide set of hand-picked
    // slots per distro. A pinned multi takes exactly the number picked;
    // its tails wait for _resolveSharedSocas, which knows whether the pin
    // shares its box.
    _namingFor(layer, seq, pins, circuitsIn) {
        const tpl = this._powerTemplateParts(layer);
        const socas = new Map();        // socaIndex -> {number, name, ...}
        const slots = new Map();        // circuit num -> {multi, tail, moved}
        if (!layer || typeof this.screenCircuits !== 'function') {
            return { socas, slots, tpl };
        }
        const circuits = circuitsIn || this._labelCircuits(layer);
        const assign = layer.powerSocaDistro || {};
        const named = layer.powerSocaNames || {};
        const chosen = layer.powerSocaNumber || {};
        const distros = this.getDistros();
        const perSoca = new Map();      // socaIndex -> [circuit num], plan order
        // Same split-aware segmentation as getSocaPlan - the naming index
        // and the plan must never disagree on what a multi is.
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, circuits.length));
        circuits.forEach((c, ci) => {
            const idx = idxOf[ci + 1];
            const arr = perSoca.get(idx) || [];
            arr.push(c.num);
            perSoca.set(idx, arr);
        });
        for (const [idx, nums] of perSoca) {
            const distroId = assign[idx] || null;
            const pin = distroId ? parseInt(chosen[idx], 10) : NaN;
            const pinned = Number.isFinite(pin) && pin >= 1;
            let number;
            if (pinned) {
                number = pin;
            } else if (distroId) {
                // Next auto number ON THAT DISTRO, skipping every slot a
                // pin claimed - a pin owns its number outright, wherever
                // the pinned screen sits in layer order. With no pins this
                // is the plain per-distro sequence it has always been.
                const taken = (pins && pins.get(distroId)) || null;
                let n = seq.get(distroId) || 0;
                do { n += 1; } while (taken && taken.has(n));
                seq.set(distroId, n);
                number = n;
            } else {
                // No distro: the SCREEN'S OWN template numbers its multis,
                // from the template's number, per screen - S1-# names this
                // screen's boxes S1, S2, S3 whatever every other screen
                // prints. These multis used to take numbers out of a
                // show-wide "unassigned" bucket in layer order, so a show
                // of four S1-# screens with no distro read S1, S6, S7 and
                // S12 down its layer list (user, 2026-09-03: "look at all
                // the drawn ports they are all wrong SL main starts with
                // 7-1"). Ruling: uniqueness across screens is not the
                // template's job - a distro names its multis uniquely, a
                // template names them the way it says. This is also the
                // number the pre-index arithmetic always printed, so the
                // per-screen ordinal and the raw number agree wherever the
                // drawn set has no gap.
                number = tpl.start + idx - 1;
            }
            const hand = String(named[idx] || '').trim();
            const name = this._multiNameFor(layer, idx, number, distroId, tpl, distros);
            if (pinned) {
                // Tails deferred: whether this pin shares its (distro,
                // number) - and therefore which tails are free - is only
                // knowable once every screen is numbered. The slots are
                // stamped in _resolveSharedSocas with the rest.
                socas.set(idx, {
                    index: idx, number, name, distroId, hand: !!hand,
                    pinned: true, circuits: nums.slice(),
                    positions: null, moved: false, share: null,
                });
                continue;
            }
            const pos = this.socaCircuitPositions(layer, idx, nums.length);
            const moved = !pos.every((p, i) => p === i + 1);
            socas.set(idx, {
                index: idx, number, name, distroId, hand: !!hand,
                pinned: false, circuits: nums.slice(), positions: pos, moved,
                share: null,
            });
            nums.forEach((num, i) => slots.set(num, {
                multi: idx, number, name, tail: pos[i], moved,
            }));
        }
        return { socas, slots, tpl };
    }

    // Rungs 2-4 of the name ladder for one multi (rung 1, the per-circuit
    // override, is the label authority's): the name somebody typed on it,
    // else its distro's name plus its number under that distro, else the
    // screen's template prefix plus its number. One function so the multis
    // the plan holds and the one a circuit is about to open climb the same
    // ladder - _predictedCircuitSlot names the box a not-yet-drawn circuit
    // will land on with this, and it must print what _namingFor will print
    // once the circuit is drawn.
    _multiNameFor(layer, idx, number, distroId, tpl, distros) {
        const hand = String(((layer && layer.powerSocaNames) || {})[idx] || '').trim();
        if (hand) return hand;
        const list = distros || this.getDistros();
        const distro = distroId ? list.find(d => d.id === distroId) : null;
        const base = distro ? String(distro.name || '').trim() : '';
        if (base) return this._deriveMultiName(base, number, tpl);
        return tpl.ok ? this._deriveMultiName(tpl.prefix, number, tpl) : '';
    }

    // Deal each shared box's six tails across its members, and say out loud
    // when they do not fit.
    //
    // Member order is PROJECT LAYER ORDER (soca index within a screen) -
    // the same bottom-up walk that numbers the multis - so the earlier
    // screen owns the lower tails and the wall reads on in order across the
    // seam. Within its slice every member's circuits ascend in wall order,
    // the same rule a single screen has always followed.
    //
    // Per member: a valid stored tail set (phase balancing, a hand move, a
    // join stamping the incumbents) is the user's arrangement and is NEVER
    // rearranged - stored sets claim their tails FIRST, so an unstored
    // member deals into the tails no stored set holds, wherever either
    // member sits in layer order. Two stored sets landing on one tail is a
    // CLASH, reported on the tiles the way port assignment reports an
    // occupied socket - both print verbatim, nothing is rearranged. Layer
    // order decides tails only among the unstored members. A box asked for
    // more than 6 legs runs off the fan: the extra circuits take tails
    // 7, 8, ... and the box reports the overflow - a soca has six tails,
    // and pretending otherwise would hide the one fact a tech needs.
    _resolveSharedSocas(screens) {
        const boxes = new Map();        // 'distroId:number' -> [{layer, entry, rec}]
        for (const l of screens) {
            const entry = this._circuitTailCache.get(l);
            if (!entry) continue;
            for (const rec of entry.socas.values()) {
                if (!rec.pinned) continue;
                const key = `${rec.distroId}:${rec.number}`;
                const arr = boxes.get(key) || [];
                arr.push({ layer: l, entry, rec });
                boxes.set(key, arr);
            }
        }
        for (const [key, members] of boxes) {
            const taken = new Set();
            let clash = false, overflow = false;
            // The physical box has as many tails as the SMALLEST member
            // breakout says it does - six for socas, three for an L21-30 -
            // and every claim past that is overflow whichever member made
            // it. Members of one box virtually always agree; when they do
            // not, the smaller figure is the only honest capacity.
            const cap = Math.min(...members
                .map(m => this.socaBoxSize(m.layer)));
            // Pass 1: every stored set takes exactly its tails. Doing this
            // before ANY dealing is what makes a stored set law: an
            // unstored member earlier in layer order can no longer sit
            // down on tails a later member's paperwork already claims.
            const dealt = [];
            for (const m of members) {
                const L = m.rec.circuits.length;
                const saved = ((m.layer.powerSocaPhasePos) || {})[m.rec.index];
                const valid = Array.isArray(saved) && saved.length === L
                    && saved.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
                    && new Set(saved).size === L;
                if (!valid) { dealt.push(m); continue; }
                const pos = saved.slice().sort((a, b) => a - b);
                m.rec.clashTails = pos.filter(p => taken.has(p));
                m.rec.overTails = pos.filter(p => p > cap);
                pos.forEach(p => taken.add(p));
                m.rec.positions = pos;
            }
            // Pass 2: the unstored members take the box's free tails in
            // member (layer) order - the initial construction of a box in
            // one gesture, and the only place layer order breaks a tie.
            for (const m of dealt) {
                const L = m.rec.circuits.length;
                const pos = [];
                let t = 1;
                while (pos.length < L) {
                    if (!taken.has(t)) pos.push(t);
                    t += 1;
                }
                m.rec.clashTails = [];
                m.rec.overTails = pos.filter(p => p > cap);
                pos.forEach(p => taken.add(p));
                m.rec.positions = pos;
            }
            for (const m of members) {
                m.rec.moved = !m.rec.positions.every((p, i) => p === i + 1);
                if (m.rec.clashTails.length) clash = true;
                if (m.rec.overTails.length) overflow = true;
            }
            for (const m of members) {
                m.rec.share = members.length > 1 ? {
                    key, number: m.rec.number, distroId: m.rec.distroId,
                    clash, overflow,
                    members: members.map(x => ({
                        layerId: x.layer.id, layerName: x.layer.name,
                        soca: x.rec.index, legs: x.rec.circuits.length,
                        tails: x.rec.positions.slice(),
                        clashTails: x.rec.clashTails.slice(),
                        overTails: x.rec.overTails.slice(),
                    })),
                } : null;
                m.rec.circuits.forEach((num, i) => m.entry.slots.set(num, {
                    multi: m.rec.index, number: m.rec.number, name: m.rec.name,
                    tail: m.rec.positions[i], moved: m.rec.moved,
                }));
            }
        }
    }

    // Which multi and which PHYSICAL TAIL of its 6-way fan a circuit lands
    // on, resolved through the soca plan (screenCircuits order) and the
    // per-circuit fan positions (phase balancing / breaker offset).
    //
    // `moved` is per-soca: true only when that soca's circuits sit on
    // non-natural positions. The label editor's number column uses it to show
    // the true tail instead of the row's own ordinal.
    _circuitTailSlot(layer, circuitNum) {
        if (!layer) return null;
        return this._powerNaming(layer).slots.get(parseInt(circuitNum, 10)) || null;
    }

    // THE ONE PLACE A CIRCUIT'S LABEL IS DECIDED. The canvas bubbles, the soca
    // panel, the splitter rows, the distro feeds list, the label editor and
    // every export come through here, so a rule added here reaches all of them
    // at once - and a second path anywhere else would print one thing on
    // screen and another on the PDF.
    getPowerCircuitLabel(layer, circuitNum) {
        const overrides = layer.powerLabelOverrides || {};
        // THE USER'S TEXT, AND IT WINS OUTRIGHT. Nothing below ever rewrites
        // a label somebody typed - drawings already issued keep printing what
        // they were issued with.
        if (overrides && overrides[circuitNum]) return overrides[circuitNum];
        const nm = this._powerNaming(layer);
        const tpl = nm.tpl;
        const slot = nm.slots.get(parseInt(circuitNum, 10));
        // The multi's name, then the tail it lands on. The tail is the TRUE
        // PHYSICAL TAIL of the 6-way fan: identical to the sequence position
        // until phase balancing or a breaker offset moves the multi's circuits
        // onto other tails, at which point the wall reads S1-1, S1-2, S1-3,
        // S1-5, S1-6 - the occupied tails ascending in wall order, gaps where
        // a tail is skipped.
        if (slot && slot.name) {
            return `${slot.name}${tpl.sep}${slot.tail}${tpl.suffix}`;
        }
        // A template with no multi number in it has no multi to name.
        if (!tpl.ok) return tpl.raw.replace('#', circuitNum);
        // A circuit the plan does not hold: the number the custom badge is
        // drawing under before its first cabinet lands, an editor row past
        // the drawn circuits. It is named by WHERE IT WILL LAND - the multi
        // and the tail the index above hands it the moment it holds a
        // cabinet - and never by arithmetic on the raw number. The two used
        // to disagree the moment the drawn numbers had a gap in them (a
        // cleared circuit, a skipped number, a splitter merge): the plan
        // names a circuit by its position on the fan, so with 2 empty the
        // drawn 13 lands on ordinal 12 and reads S2-6, while floor((13-1)/6)
        // said S3-1. The badge printed the arithmetic and the bubble printed
        // the plan (user, 2026-09-03: "it would say 3-1 and do 2-6. 2-6 was
        // actually correct. then it would go to 3-2 and i'd be drawing
        // 3-1"). One authority, one answer, before and after the click.
        const p = this._predictedCircuitSlot(layer, nm, circuitNum);
        return `${p.name}${tpl.sep}${p.tail}${tpl.suffix}`;
    }

    // Where circuit `circuitNum` WOULD land if it were drawn now: the multi
    // and physical tail the naming index will give it once it holds a
    // cabinet. Its ordinal is its place among the plan's circuit numbers
    // (with no gap that is the number itself), its multi the split-aware
    // segment that ordinal falls in, and its tail the box's lowest free tail
    // dealt in wall order with the tails already occupied - so a contiguous
    // 1..12 predicts 13 as S3-1, and 1,3..12 predicts 13 as S2-6, exactly
    // what the drawn circuit reads. A multi the plan does not have yet takes
    // the next number in its bucket and the same name ladder _namingFor
    // walks (hand-typed, distro-derived, template), so the label is the
    // label the wall prints, not a guess at it.
    _predictedCircuitSlot(layer, nm, circuitNum) {
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const drawn = [...nm.slots.keys()];
        const ordinal = drawn.filter(k => k < n).length + 1;
        const segs = this._socaSegments(layer, drawn.length + 1);
        const seg = segs.find(s => ordinal >= s.start && ordinal <= s.end)
            || segs[segs.length - 1];
        const idx = seg.index;
        const at = ordinal - seg.start + 1;
        const rec = nm.socas.get(idx);
        if (rec) {
            // The box exists: the newcomer takes its lowest free tail, and
            // the box's tails are then read ascending in wall order - the
            // same rule socaCircuitPositions applies to a stored set.
            const have = (rec.positions || []).slice();
            let free = 1;
            while (have.includes(free)) free += 1;
            const tails = have.concat(free).sort((a, b) => a - b);
            return { name: rec.name, tail: tails[at - 1] || at };
        }
        // A multi the plan does not have yet, numbered the way _namingFor
        // will number it once it exists. On no distro that is the screen's
        // own template number for this multi index - per screen, so the
        // first box a screen opens is S1 whatever the rest of the show
        // prints. On a distro it is the running sequence of that distro,
        // walked in PROJECT LAYER ORDER up to and including this screen,
        // next free number, every pin on the distro skipped - not "the
        // show's last number plus one", which on a show whose FIRST screen
        // is the one being drawn named its first box after every box the
        // later screens already had. Its name comes off the same ladder the
        // drawn multis climb.
        const distroId = (layer.powerSocaDistro || {})[idx] || null;
        let number = nm.tpl.start + idx - 1;
        if (distroId) {
            const screens = ((this.project && this.project.layers) || [])
                .filter(l => (l.type || 'screen') === 'screen');
            const entryOf = (l) => (this._circuitTailCache && this._circuitTailCache.get(l))
                || (l === layer ? nm : null);
            const pinned = new Set();
            let seq = 0;
            for (const l of screens.includes(layer) ? screens : [layer]) {
                const entry = entryOf(l);
                if (!entry) continue;
                for (const r of entry.socas.values()) {
                    if (r.distroId !== distroId) continue;
                    if (r.pinned) pinned.add(r.number);
                    else if (l === layer || screens.indexOf(l) < screens.indexOf(layer)) {
                        seq = Math.max(seq, r.number);
                    }
                }
            }
            number = seq;
            do { number += 1; } while (pinned.has(number));
        }
        const name = this._multiNameFor(layer, idx, number, distroId, nm.tpl);
        const pos = this.socaCircuitPositions(layer, idx, at);
        return { name, tail: pos[at - 1] || at };
    }

    getDefaultPowerCircuitColors() {
        return {
            A: '#BC382F',
            B: '#CC6B30',
            C: '#D2E94D',
            D: '#2CF82B',
            E: '#2145DC',
            F: '#7414F5'
        };
    }

    normalizeHexColor(value, fallback = '#FF0000') {
        const raw = String(value || '').trim();
        if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
        if (/^[0-9a-fA-F]{6}$/.test(raw)) return `#${raw.toUpperCase()}`;
        return fallback;
    }

    normalizePowerCircuitColors(colors) {
        const defaults = this.getDefaultPowerCircuitColors();
        const next = { ...defaults };
        if (colors && typeof colors === 'object') {
            Object.keys(defaults).forEach(letter => {
                if (colors[letter]) {
                    next[letter] = this.normalizeHexColor(colors[letter], defaults[letter]);
                }
            });
        }
        // Migrate old default green (Circuit 4) to the new default.
        if ((next.D || '').toUpperCase() === '#79FC4C') {
            next.D = defaults.D;
        }
        return next;
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

    getPowerCircuitColor(layer, circuitNum) {
        const colors = this.normalizePowerCircuitColors(layer && layer.powerCircuitColors);
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const slots = ['A', 'B', 'C', 'D', 'E', 'F'];
        const slotKey = slots[(n - 1) % slots.length];
        return colors[slotKey] || '#BC382F';
    }

    // Keep the caret where the user put it across an editor rebuild.
    //
    // Editing a label and pressing Tab fires the input's `change` handler,
    // which PUTs to the server. The browser moves focus to the NEXT input
    // immediately; the rebuild (`list.innerHTML = ''`) only happens a
    // round-trip later, when the response - or the socket `layer_updated`
    // echo - lands. By then the field the user is typing in is the one the
    // rebuild destroys, so focus falls to <body> and the next keystroke goes
    // nowhere. Pressing Tab again appears to work only because an unedited
    // field fires no `change` and nothing rebuilds.
    //
    // Capture the focused field's stable key plus its caret, then restore in
    // a microtask: that runs after the synchronous rebuild whichever return
    // path the builder takes, and does not care which of the two triggers
    // fired.
    _preserveEditorFocus() {
        const active = document.activeElement;
        const key = active && active.dataset ? active.dataset.lrdField : null;
        if (!key) return;
        let start = null;
        let end = null;
        try {
            start = active.selectionStart;
            end = active.selectionEnd;
        } catch (_) {
            // Not every input type exposes a selection (number, color, ...).
            start = null;
            end = null;
        }
        Promise.resolve().then(() => {
            const el = document.querySelector(`[data-lrd-field="${key}"]`);
            // Gone - the port/circuit count shrank out from under it. Leave
            // focus alone rather than throwing.
            if (!el || el === document.activeElement) return;
            // A collapsed section swallows focus() silently (the field is
            // display:none), so the restore opens the section first - the
            // stated rule for any programmatic focus into a folded section.
            if (typeof this._expandSectionsFor === 'function') {
                this._expandSectionsFor(el);
            }
            try {
                el.focus();
            } catch (_) {
                return;
            }
            if (start === null || typeof el.setSelectionRange !== 'function') return;
            try {
                el.setSelectionRange(start, end);
            } catch (_) { /* selection unsupported on this element */ }
        });
    }

    // The synchronous sibling of the round-trip delay _preserveEditorFocus()
    // was written for.
    //
    // The label editors above only rebuild when the PUT response (or socket
    // echo) lands, so by the time their wipe runs the Tab gesture is over and
    // document.activeElement IS the field the user landed in - the helper can
    // see it and put it back. Several editors in this suite (the Port List
    // name cells, the patch rail, the distro panel, the soca runs) restate
    // their DOM synchronously inside the field's own `change` handler
    // instead. That runs MID-gesture: the browser has already chosen the next
    // tab stop but not focused it yet, so the wipe destroys a target no
    // capture can know about and focus falls to <body>.
    //
    // So those sites push the restate one macrotask out. The gesture then
    // completes onto the real element, and the rebuild that follows goes
    // through _preserveEditorFocus() exactly like every round-trip rebuild
    // does. Model writes and undo snapshots stay in the handler - only the
    // DOM restatement moves.
    _rebuildAfterGesture(fn) {
        setTimeout(fn, 0);
    }

    // The per-port override editor died with the Signal sidebar. The
    // overrides themselves are untouched: the Fallback Labels block in
    // Data Settings bulk-applies and clears them, an assigned port renames
    // on its dock chip, and the canvas keeps drawing every stored
    // override. Kept as a no-op because every "labels may have moved" path
    // calls it.
    updatePortLabelEditor() {
    }


    // Same story on the power side: the per-circuit override edits on its
    // circuit chip in the dock (which every naming path already redraws),
    // and the Circuit Labels block in Power Settings bulk-applies and
    // clears. Kept as a no-op for its callers.
    updatePowerLabelEditor() {
    }


    updatePowerCircuitColorEditor() {
        if (!this.currentLayer) return;
        const section = document.getElementById('power-circuit-color-section');
        const list = document.getElementById('power-circuit-color-list');
        if (section) {
            section.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        if (!list) return;
        this._preserveEditorFocus();
        list.innerHTML = '';
        const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
        Object.keys(colors).forEach((letter, index) => {
            const row = document.createElement('div');
            row.style.display = 'grid';
            row.style.gridTemplateColumns = '20px 26px 1fr';
            row.style.gap = '6px';
            row.style.alignItems = 'center';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit-letter', letter);
            cb.dataset.lrdField = `power-circuit-color-${letter}`;

            const swatch = document.createElement('div');
            swatch.style.width = '20px';
            swatch.style.height = '20px';
            swatch.style.borderRadius = '4px';
            swatch.style.border = '1px solid #333';
            swatch.style.background = colors[letter];

            const text = document.createElement('div');
            text.style.fontSize = '12px';
            text.style.color = '#ccc';
            text.textContent = `Circuit ${index + 1}`;

            row.appendChild(cb);
            row.appendChild(swatch);
            row.appendChild(text);
            list.appendChild(row);
        });
    }

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

    // ── Cross-member manual paths (v0.11.0, step 6) ──────────────────────
    //
    // A group IS ONE WALL, so a hand-drawn port path or power circuit has to
    // be allowed to run off one member and onto the next. The path itself
    // never moves: it stays on the layer that OWNS the port or circuit -
    // a port is a physical output on ONE processor - and only the individual
    // step learns where the cable landed.
    //
    //     {row, col}            a panel in the OWNING layer. Unchanged, and
    //                           the shape 100% of existing projects have.
    //     {row, col, layerId}   a panel in a PEER member of the same group.
    //
    // Why a key on the STEP rather than a new key on the layer: the server's
    // add / update allow-lists silently DROP layer keys they do not know,
    // which has already cost this codebase two features (processorType,
    // lowLatency). A step lives inside customPortPaths, which is already
    // allow-listed, so it rides in for free.
    //
    // Why (layerId, row, col) rather than panel.id: _build_panels regenerates
    // panel ids on every geometry rebuild, so an id is worthless the moment
    // anyone changes a column count. (row, col) is the only durable address.
    //
    // Every helper below returns the ungrouped answer for an ungrouped layer,
    // and a path with no layerId anywhere reads exactly as it did before, so a
    // project without groups takes precisely the code path it took before.

    // The canvas a manual path treats a layer as living on. Paths are only
    // ever drawn in Data Flow and Power, which are both Show Look views, so
    // the show override is the right answer REGARDLESS of which tab is open.
    // Deliberately NOT canvasRenderer._effectiveLayerCanvasId, which flips
    // with viewMode: reachability that changed the moment the user clicked the
    // Pixel Map tab would mean the same stored step resolving on one tab and
    // reading as dangling on another.
    _pathCanvasIdOf(layer) {
        if (!layer) return null;
        return layer.show_canvas_id || layer.canvas_id || null;
    }

    // Every layer a path owned by `layer` may legally touch. The owner is
    // always first, so callers that want "the owner, then its peers" get a
    // stable order without re-sorting.
    getPathScopeLayers(layer) {
        if (!layer) return [];
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return [layer];
        const cid = this._pathCanvasIdOf(layer);
        const scope = [layer];
        (this.getGroupMembers(group) || []).forEach(m => {
            if (!m || m.id === layer.id) return;
            if ((m.type || 'screen') !== 'screen') return;
            // The same rule canvas.js _groupDrawnMembers applies: a member
            // sitting on another canvas is a different workspace entirely, so
            // a cable drawn onto it would be drawn at a position that means
            // nothing. Hidden members are NOT excluded here (where
            // _groupDrawnMembers does exclude them) - hiding a screen must not
            // quietly invalidate paths the user already drew onto it, because
            // unhiding has to bring them straight back.
            if (this._pathCanvasIdOf(m) !== cid) return;
            scope.push(m);
        });
        return scope;
    }

    // The layers a SELECTION owned by `layer` may touch: the path scope, less
    // the members the user cannot see.
    //
    // getPathScopeLayers deliberately keeps hidden members, because a path
    // already drawn onto a screen must survive that screen being hidden and
    // come straight back when it is unhidden. That is right for RESOLVING a
    // path and wrong for BUILDING one: a hidden member is not drawn
    // (canvas.js _groupDrawnMembers filters visible !== false) and cannot be
    // clicked (getPanelAt skips it), so a marquee, an arrow handoff or an
    // Apply Pattern that reached it wired cabinets nobody could see - 12 of
    // them, on a screen that is not on the canvas, into the visible screen's
    // port 1.
    //
    // The OWNER is never filtered out. It is the layer the user is working on
    // and the port belongs to it; dropping it would make a hidden current
    // layer un-drawable rather than merely un-reachable, and it keeps an
    // ungrouped screen byte-identical to before.
    //
    // `visible === false`, not `!visible`: a layer with no visible key is
    // visible everywhere else in this app (the server reads
    // layer.get('visible', True)).
    getSelectionScopeLayers(layer) {
        if (!layer) return [];
        return this.getPathScopeLayers(layer)
            .filter(l => l && (l.id === layer.id || l.visible !== false));
    }

    canPathReachLayer(ownerLayer, targetLayer) {
        if (!ownerLayer || !targetLayer) return false;
        if (ownerLayer.id === targetLayer.id) return true;
        return this.getPathScopeLayers(ownerLayer).some(l => l && l.id === targetLayer.id);
    }

    // The layer id a step names, resolving the plain form to the owner. Kept
    // separate from resolvePathEntryLayer because the conflict scan wants the
    // id without paying for a lookup and a legality check per step.
    getPathEntryLayerId(ownerLayer, entry) {
        const lid = entry ? entry.layerId : undefined;
        if (lid === undefined || lid === null) return ownerLayer ? ownerLayer.id : null;
        return lid;
    }

    resolvePathEntryLayer(ownerLayer, entry) {
        if (!ownerLayer || !entry) return null;
        const lid = entry.layerId;
        if (lid === undefined || lid === null || lid === ownerLayer.id) return ownerLayer;
        const target = ((this.project && this.project.layers) || [])
            .find(l => l && l.id === lid) || null;
        if (!target) return null;
        // A pointer at a layer that exists but is no longer a reachable peer
        // (ungrouped, regrouped, or dragged onto another canvas) is dead, not
        // drawable. The server prunes it on the next round-trip; until then
        // reading it as null keeps the renderer from drawing a cable onto an
        // unrelated screen.
        return this.canPathReachLayer(ownerLayer, target) ? target : null;
    }

    resolvePathEntry(ownerLayer, entry) {
        const layer = this.resolvePathEntryLayer(ownerLayer, entry);
        if (!layer || !entry) return null;
        const panel = this.getPanelByRowCol(layer, entry.row, entry.col);
        if (!panel) return null;
        return { layer, panel };
    }

    // Hidden panels are dropped HERE rather than by each caller, matching the
    // read-time `.filter(p => p && !p.hidden)` every path consumer already ran
    // before a step could name a peer.
    getResolvedPathPanels(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return [];
        const out = [];
        path.forEach(entry => {
            const resolved = this.resolvePathEntry(ownerLayer, entry);
            if (resolved && !resolved.panel.hidden) out.push(resolved);
        });
        return out;
    }

    // layerId is written ONLY when it differs from the owner, so a path that
    // never leaves its own screen is byte-for-byte the shape it has always
    // been. (The server's prune pass normalises a self-pointer the same way,
    // so the two sides can never drift into writing different files.)
    makePathEntry(ownerLayer, panelLayer, panel) {
        if (!panel) return null;
        const entry = { row: panel.row, col: panel.col };
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            entry.layerId = panelLayer.id;
        }
        return entry;
    }

    // The address of ONE cabinet on the wall. Path ownership, path dedupe and
    // (since v0.11.0's marquee) customSelection / powerCustomSelection are all
    // keyed on this, because inside a group `${row},${col}` names two cabinets
    // at once and every one of those jobs has to tell them apart.
    //
    // getPanelKey stays `${row},${col}` regardless: pixelMapSelection still
    // uses it - one screen, nothing grouped about it - and its overlay parses
    // the key back with `key.split(',').map(parseInt)`, which a layer id in
    // front would turn into the WRONG panel silently, with no error anywhere.
    getScopedPanelKey(layerId, panel) {
        return `${layerId}:${panel.row},${panel.col}`;
    }

    pathCrossesMembers(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return false;
        return path.some(e => e && e.layerId !== undefined && e.layerId !== null
            && e.layerId !== ownerLayer.id);
    }

    // Which layer does this panel object belong to, as far as a path owned by
    // `ownerLayer` is concerned? Null when the panel is not reachable at all.
    // Identity first - the click handler and the arrow keys both hand us the
    // panel straight out of a layer's own array - and the (row, col) fallback
    // is what keeps a caller that rebuilt the panel behaving exactly as before.
    _resolvePathPanelLayer(ownerLayer, panel, explicitLayer) {
        if (!ownerLayer || !panel) return null;
        if (explicitLayer) {
            return this.canPathReachLayer(ownerLayer, explicitLayer) ? explicitLayer : null;
        }
        const scope = this.getPathScopeLayers(ownerLayer);
        const byIdentity = scope.find(l => l && Array.isArray(l.panels)
            && l.panels.includes(panel));
        if (byIdentity) return byIdentity;
        return this.getPanelByRowCol(ownerLayer, panel.row, panel.col) ? ownerLayer : null;
    }

    _pathLayerName(layer) {
        if (!layer) return 'another screen';
        return layer.name || `Screen ${layer.id}`;
    }

    // "port 2", or "port 2 on North Lower" when the conflict lives on a peer.
    // R3C4 alone stops meaning anything the moment two grids are in play, so
    // a toast that names only the number sends the user hunting.
    _describePathConflict(conflict, kind) {
        if (!conflict) return '';
        const base = `${kind} ${conflict.number}`;
        return conflict.foreign ? `${base} on ${this._pathLayerName(conflict.layer)}` : base;
    }

    _describePathPanel(ownerLayer, panelLayer, panel) {
        const base = `R${panel.row + 1}C${panel.col + 1}`;
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            return `${base} on ${this._pathLayerName(panelLayer)}`;
        }
        return base;
    }

    /**
     * Which port / circuit (if any) already owns this cabinet, anywhere in the
     * owner's path scope. Returns {number, layer, layerId, foreign} or null.
     *
     * `foreign` is the whole reason this returns an object rather than the
     * bare number it used to: with a group in play the answer may live on a
     * different screen, and the caller has to be able to say which.
     */
    _findPathOwner(ownerLayer, panel, excludeNum, panelLayer, pathsKey) {
        if (!ownerLayer || !panel) return null;
        const source = panelLayer || ownerLayer;
        const key = this.getScopedPanelKey(source.id, panel);
        for (const scope of this.getPathScopeLayers(ownerLayer)) {
            const paths = scope && scope[pathsKey];
            if (!paths) continue;
            for (const numStr of Object.keys(paths)) {
                // Number("0") is 0, which is falsy - the old `Number(s) || s`
                // handed back the STRING "0" and then failed to match a
                // numeric exclude. Ports and circuits are 1-based so it never
                // bit anyone, but a quirk that only works because a value is
                // impossible is a trap for whoever changes that.
                const parsed = Number(numStr);
                const num = Number.isFinite(parsed) ? parsed : numStr;
                // Only the port being drawn RIGHT NOW is exempt, and only on
                // its own layer: port 1 of member A and port 1 of member B are
                // two different physical outputs (getGroupTotals sums each
                // member's own requirement), so a cabinet already claimed by
                // the peer's port 1 genuinely is taken.
                if (scope.id === ownerLayer.id && num === excludeNum) continue;
                const path = paths[numStr] || [];
                const hit = path.some(e => e && this.getScopedPanelKey(
                    this.getPathEntryLayerId(scope, e), e) === key);
                if (hit) {
                    return {
                        number: num,
                        layer: scope,
                        layerId: scope.id,
                        foreign: scope.id !== ownerLayer.id,
                    };
                }
            }
        }
        return null;
    }

    /**
     * The OTHER port (if any) that already owns this panel. Scans every layer
     * in the owner's path scope, not just the owner's own paths, so a cabinet
     * claimed by a port drawn from member A is seen as taken while drawing
     * from member B.
     */
    _findPanelOwnerPort(layer, panel, excludePortNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludePortNum, panelLayer, 'customPortPaths');
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludeCircuitNum, panelLayer, 'powerCustomPaths');
    }

    // ── Per-run overrides (data ports and power circuits) ─────────────────
    //
    // Custom used to be all or nothing: the WHOLE screen goes to
    // flowPattern 'custom' and every port is hand-drawn. The motivating wall
    // is the other way round - auto-cable the whole thing, then redraw the
    // ONE run that jumped somewhere a cable cannot go. So an override is a
    // single port (or circuit) number the user has taken over:
    //
    //     customPortOverrides / powerCustomOverrides   the numbers taken over,
    //                           per member and NEVER group-shared - a redrawn
    //                           port is one physical cable on one screen
    //     customPortPaths / powerCustomPaths            still where the drawn
    //                           path lives, keyed by that number - the same
    //                           dict, the same step shape ({row, col
    //                           [, layerId]}), the same editing tools
    //
    // Whole-screen custom keeps its exact semantics: isCustomFlow /
    // isCustomPower still mean the pattern, and a screen in that mode has no
    // overrides (the paths are ALL hand-drawn there). Overrides only exist
    // against an automatic pattern, where the engines lay the auto walk over
    // every cabinet an override has not claimed and skip the overridden
    // numbers - see calculatePortAssignments / calculatePowerAssignments.

    // The override numbers of one layer, validated: ints >= 1, deduped, in
    // ascending order. Tolerant of anything a stale file could hold.
    getOverrideNums(layer, kind) {
        const key = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        const arr = layer && layer[key];
        if (!Array.isArray(arr)) return [];
        const out = [];
        arr.forEach(v => {
            const n = parseInt(v, 10);
            if (Number.isFinite(n) && n >= 1 && !out.includes(n)) out.push(n);
        });
        return out.sort((a, b) => a - b);
    }

    // Overrides are meaningful only against an automatic pattern - in
    // whole-screen custom every path is hand-drawn already and the array is
    // ignored outright, so flipping to custom and back cannot double-apply.
    hasRunOverrides(layer, kind) {
        if (!layer) return false;
        if (kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer)) return false;
        return this.getOverrideNums(layer, kind).length > 0;
    }

    isRunOverridden(layer, kind, num) {
        if (!layer) return false;
        if (kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer)) return false;
        return this.getOverrideNums(layer, kind).includes(num);
    }

    // Is ONE overridden run open for redrawing right now? Session state, not
    // layer state: it must not travel through undo snapshots, saves or
    // presets. It only reads true while the layer still carries the override
    // AND the active index still points at it - undo can revert either, and
    // a click that then wrote into some other number would be corruption,
    // not editing.
    _isOverrideEditing(layer, kind) {
        const s = this._overrideEditing;
        if (!s || !layer || s.layerId !== layer.id || s.kind !== kind) return false;
        if (!this.isRunOverridden(layer, kind, s.num)) return false;
        const idx = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        return idx === s.num;
    }

    // Every cabinet claimed by an override path anywhere in this layer's path
    // scope, as the panel OBJECTS the engines walk. The scope matters: an
    // override drawn from the group's first member can run onto a peer, and
    // the peer's own walk must not feed those cabinets twice. Members in
    // whole-screen custom contribute nothing here - their paths are not
    // overrides and their screens are not on the automatic map at all.
    _overrideClaims(layer, kind) {
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const scope = (typeof this.getPathScopeLayers === 'function')
            ? this.getPathScopeLayers(layer) : [layer];
        const claimed = new Set();
        scope.forEach(member => {
            if (!member) return;
            if (kind === 'power' ? this.isCustomPower(member) : this.isCustomFlow(member)) return;
            const nums = this.getOverrideNums(member, kind);
            if (!nums.length) return;
            const paths = member[pathsKey] || {};
            nums.forEach(n => {
                this.getResolvedPathPanels(member, paths[n] || []).forEach(hit => {
                    claimed.add(hit.panel);
                });
            });
        });
        return claimed;
    }

    // This layer's own overridden runs, resolved and ready to merge into an
    // assignment: [{num, hits: [{layer, panel}...]}] in ascending number
    // order, empty paths dropped (a number with nothing drawn reserves its
    // number but is not a cable).
    _ownOverrideRuns(layer, kind) {
        if (!this.hasRunOverrides(layer, kind)) return [];
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const paths = layer[pathsKey] || {};
        return this.getOverrideNums(layer, kind)
            .map(num => ({ num, hits: this.getResolvedPathPanels(layer, paths[num] || []) }))
            .filter(o => o.hits.length > 0);
    }

    // The run under a canvas point in the CURRENT view, or null: the port in
    // Data Flow, the circuit in Power, auto or hand-drawn alike. Owner is the
    // layer whose numbering space the run lives in - for a crossing group
    // that is the member that owns the walk, not the member under the cursor.
    runAtPoint(worldX, worldY) {
        const r = window.canvasRenderer;
        if (!r || !this.project) return null;
        const view = r.viewMode;
        if (view !== 'data-flow' && view !== 'power') return null;
        const hit = r.getPanelAt(worldX, worldY);
        if (!hit) return null;
        if (view === 'data-flow') {
            // The dock's panel -> run map is THE lookup for this already;
            // cached per microtask because hover asks on every mouse move.
            if (!this._hoverDataMapCache) {
                this._hoverDataMapCache = this._dockBuildDataMap();
                Promise.resolve().then(() => { this._hoverDataMapCache = null; });
            }
            const run = this._hoverDataMapCache.get(hit.panel);
            if (!run) return null;
            const owner = (this.project.layers || []).find(l => l.id === run.ownerId);
            return owner ? { kind: 'data', layer: owner, num: run.portNum } : null;
        }
        const under = (this.project.layers || []).find(l => l.id === hit.layerId);
        if (!under) return null;
        if (!(under._powerPanelCircuitMap instanceof Map)
                && typeof r.preparePowerLayerRenderData === 'function') {
            r.preparePowerLayerRenderData(under);
        }
        const circuit = (typeof r._powerCircuitForPanel === 'function')
            ? r._powerCircuitForPanel(under, hit.panel) : null;
        return circuit
            ? { kind: 'power', layer: circuit.owner, num: circuit.circuitNum } : null;
    }

    // The held-modifier highlight: while Alt is down, the run under the
    // cursor lights up with the same underlay the dock drag paints - the
    // user's own words for the gesture ("when we hold a certain key it will
    // highlight whatever your mouse goes over"). Re-rendered only when the
    // lit run actually changes.
    updateOverrideHover(active, worldX, worldY) {
        let next = null;
        if (active) {
            const run = this.runAtPoint(worldX, worldY);
            if (run) next = { layerId: run.layer.id, num: run.num, kind: run.kind };
        }
        const prev = this._overrideHover;
        const same = (!prev && !next) || (prev && next
            && prev.layerId === next.layerId && prev.num === next.num
            && prev.kind === next.kind);
        if (same) return;
        this._overrideHover = next;
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Alt+click on a run. Three cases, none of them a mode the user has to
    // know about first:
    //   * the owner is in whole-screen custom - every run is already
    //     editable, so the click just makes that run the active one;
    //   * the run is already overridden - reopen it for editing;
    //   * an automatic run - take it over (overrideRun below).
    // Returns true when the click was consumed.
    handleOverrideClick(worldX, worldY) {
        const run = this.runAtPoint(worldX, worldY);
        if (!run) return false;
        const { kind, layer: owner, num } = run;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        if (wholeCustom) {
            this._activateRunForEdit(owner, kind, num, null);
            return true;
        }
        if (this.isRunOverridden(owner, kind, num)) {
            this.beginOverrideEdit(owner, kind, num);
            return true;
        }
        this.overrideRun(owner, kind, num);
        return true;
    }

    // Take one automatic run over: seed its path with the cabinets it carries
    // RIGHT NOW, in the order the walk feeds them - so nothing on the canvas
    // moves at the moment of entry - reserve its number, and open it for
    // editing. ONE undo step for the whole transition.
    overrideRun(owner, kind, num) {
        if (!owner || !num) return;
        const hits = this._runSeedHits(owner, kind, num);
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        if (kind === 'power') this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        owner[pathsKey][num] = hits.map(h => this.makePathEntry(owner, h.layer, h.panel));
        const nums = this.getOverrideNums(owner, kind);
        if (!nums.includes(num)) nums.push(num);
        owner[ovrKey] = nums.sort((a, b) => a - b);
        this._activateRunForEdit(owner, kind, num,
            kind === 'power' ? 'Override Circuit' : 'Override Port');
        if (typeof sendClientLog === 'function') {
            sendClientLog('override_run', {
                kind, layerId: owner.id, num, seeded: hits.length,
            });
        }
    }

    // Reopen an existing override for editing. The only model change is the
    // active index, so the undo entry is the one that change has always had.
    beginOverrideEdit(owner, kind, num) {
        if (!this.isRunOverridden(owner, kind, num)) return;
        this._activateRunForEdit(owner, kind, num, null);
    }

    // The shared tail of every entry path: select the owner, point the active
    // index at the run, raise the session editing state, persist, refresh.
    // `undoLabel` names the ONE undo step when the caller already mutated the
    // model (overrideRun); null means only the index may have moved and the
    // step is the ordinary index change - or nothing at all.
    _activateRunForEdit(owner, kind, num, undoLabel) {
        if (this.currentLayer !== owner && typeof this.selectLayer === 'function') {
            this.selectLayer(owner);
        }
        const idxKey = kind === 'power' ? 'powerCustomIndex' : 'customPortIndex';
        const idxChanged = (owner[idxKey] || 1) !== num;
        owner[idxKey] = num;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        this._overrideEditing = wholeCustom
            ? null : { layerId: owner.id, kind, num };
        const label = undoLabel || (idxChanged
            ? (kind === 'power' ? 'Power Custom Circuit Change' : 'Custom Port Change')
            : null);
        if (label) {
            this.saveState(label);
            this.saveClientSideProperties();
            this.updateLayers(this._pathPersistLayers(owner));
        }
        if (kind === 'power') {
            this.updatePowerCapacityDisplay();
            this.updateCustomPowerUI();
        } else {
            this.updatePortCapacityDisplay();
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Close the open override edit. No model change - the override and its
    // path stay exactly as drawn - so no undo entry.
    endOverrideEdit() {
        if (!this._overrideEditing) return;
        const wasPower = this._overrideEditing.kind === 'power';
        this._overrideEditing = null;
        if (wasPower) {
            if (this.powerCustomSelection) this.powerCustomSelection.clear();
            this.updateCustomPowerUI();
        } else {
            if (this.customSelection) this.customSelection.clear();
            this.updateCustomFlowUI();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Hand one overridden run back to the automatic walk: the override and
    // its drawn path go, and the engine re-flows the freed cabinets on the
    // next pass. One named undo step puts the drawing back.
    returnRunToAuto(owner, kind, num) {
        if (!owner || !this.isRunOverridden(owner, kind, num)) return;
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        owner[ovrKey] = this.getOverrideNums(owner, kind).filter(n => n !== num);
        if (owner[pathsKey]) delete owner[pathsKey][num];
        const s = this._overrideEditing;
        if (s && s.layerId === owner.id && s.kind === kind && s.num === num) {
            this._overrideEditing = null;
        }
        this.saveState(kind === 'power' ? 'Return Circuit To Auto' : 'Return Port To Auto');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        if (kind === 'power') {
            this.updatePowerCapacityDisplay();
            this.updateCustomPowerUI();
        } else {
            this.updatePortCapacityDisplay();
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        if (typeof sendClientLog === 'function') {
            sendClientLog('return_run_to_auto', { kind, layerId: owner.id, num });
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The cabinets one run carries right now, in feed order, resolved to
    // {layer, panel} so a crossing run seeds with the peer's real cabinets.
    _runSeedHits(owner, kind, num) {
        const scope = (typeof this.getPathScopeLayers === 'function')
            ? this.getPathScopeLayers(owner) : [owner];
        const byId = new Map(scope.map(l => [l.id, l]));
        const resolve = (layerId) => (layerId === undefined || layerId === null)
            ? owner : (byId.get(layerId) || owner);
        if (kind === 'data') {
            return (this.calculatePortAssignments(owner) || [])
                .filter(item => item && item.port === num && item.panel && !item.panel.hidden)
                .map(item => ({ layer: resolve(item.layerId), panel: item.panel }));
        }
        const res = this.calculatePowerAssignments(owner) || { circuits: [] };
        const circuits = res.circuits || [];
        const idx = res.nums ? res.nums.indexOf(num) : num - 1;
        if (idx < 0 || !circuits[idx]) return [];
        const owners = res.layers ? res.layers[idx] : null;
        return circuits[idx].map((panel, i) => ({
            layer: (owners && owners[i]) ? owners[i] : owner,
            panel,
        }));
    }

    // The context-menu offers for a right-click on a run: "Redraw ..." on any
    // run the gesture could take over, plus "... back to auto" only where an
    // override actually exists to drop - the house rule that a menu only
    // shows what applies. Null anywhere the cursor is not on a run, and in
    // whole-screen custom, where redrawing is the whole mode already.
    _prepareOverrideMenu(x, y) {
        const r = window.canvasRenderer;
        if (!r || !r.canvas) return null;
        if (r.viewMode !== 'data-flow' && r.viewMode !== 'power') return null;
        const rect = r.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            return null;
        }
        const worldY = ((y - rect.top) - r.panY) / r.zoom;
        const worldX = r._unmirrorWorldX(((x - rect.left) - r.panX) / r.zoom, worldY);
        const run = this.runAtPoint(worldX, worldY);
        if (!run) return null;
        const { kind, layer: owner, num } = run;
        if (kind === 'power' ? this.isCustomPower(owner) : this.isCustomFlow(owner)) {
            return null;
        }
        const noun = kind === 'power'
            ? `circuit ${this.getPowerCircuitLabel(owner, num)}`
            : `port ${this.getPortLabelText(owner, num, 'primary')}`;
        const overridden = this.isRunOverridden(owner, kind, num);
        return {
            redraw: {
                label: `Redraw ${noun}`,
                title: overridden
                    ? 'Reopen this hand-drawn run: click cabinets to extend it, '
                        + 'arrow keys to walk it, Esc when done.'
                    : 'Take this run over from automatic routing. It keeps the '
                        + 'cabinets it has now; click cabinets to redraw it, and '
                        + 'the rest of the screen re-flows around it.',
                run: () => (overridden
                    ? this.beginOverrideEdit(owner, kind, num)
                    : this.overrideRun(owner, kind, num)),
            },
            backToAuto: overridden ? {
                label: `${noun.charAt(0).toUpperCase()}${noun.slice(1)} back to auto`,
                title: 'Drop the hand-drawn run; automatic routing takes its '
                    + 'cabinets back. Undo puts the drawing back.',
                run: () => this.returnRunToAuto(owner, kind, num),
            } : null,
        };
    }

    /**
     * The layers a path edit has to PUT. updateLayers only sends what it is
     * handed (plus peers a shared-field edit left pending), and clicking a
     * peer member's cabinet writes onto currentLayer - which is not guaranteed
     * to be in the selection, since a marquee or a click on the peer alone can
     * leave it out. The owner is therefore added explicitly. Nothing else
     * changed, so nothing else is sent.
     */
    _pathPersistLayers(ownerLayer) {
        const layers = this.getSelectedLayers() || [];
        if (ownerLayer && !layers.some(l => l && l.id === ownerLayer.id)) {
            return layers.concat([ownerLayer]);
        }
        return layers;
    }

    // ── Capacity while drawing by hand ────────────────────────────────────
    //
    // The wall this was built for: 28 cabinets wide on 110 V / 15 A, so
    // automatic power refuses ("a full row is N W and a circuit carries
    // M W"). The way round it is custom mode - select a 14 x 6 block, press
    // serpentine, get circuits 1..6 at 14 apiece - which only works if the
    // pattern fill CUTS at capacity instead of pouring the whole selection
    // into the one active circuit, and if a click past the cap is refused
    // instead of quietly overloading the run. And each of those six reads
    // from the SAME side: a new run restarts the snake at the pattern's
    // start corner rather than continuing it (_chunkPicksByCapacity).
    //
    // ONE authority per side, and each is the sidebar's own readout:
    //   power  "Panels/Circuit" - watts per circuit (V x A) against each
    //          cabinet's watt-equivalent: panelWatts x getPanelLoadFactor,
    //          the half-tile derate calculatePowerAssignments' loadOf
    //          charges, at the cabinet's OWN member's wattage the way
    //          getSocaPlan charges a crossing circuit.
    //   data   "Panels/Port" - pixels per port (calculatePortCapacity, Low
    //          Latency factor included) against each cabinet's pixel area.
    // Nothing is re-derived here, so a capacity change lands in both.
    //
    // A run is FULL when one more whole cabinet would not fit; a click is
    // refused when THAT cabinet would not fit, so a half-tile can still land
    // on a run the badge calls full - the badge speaks of whole cabinets. No
    // capacity at all (no voltage or wattage set, no published pixel figure
    // for the processor) means no cap, and the run takes whatever is drawn
    // exactly as it always has.
    customRunCapacity(layer, kind) {
        const none = { known: false, limit: 0, unit: 0, count: 0, at: '', describe: '' };
        if (!layer) return none;
        if (kind === 'power') {
            const voltage = parseFloat(layer.powerVoltage) || 0;
            const amperage = parseFloat(layer.powerAmperage) || 0;
            const unit = parseFloat(layer.panelWatts) || 0;
            const limit = voltage * amperage;
            if (!(limit > 0 && unit > 0)) return none;
            const count = Math.floor(limit / unit);
            const at = `${voltage}V/${amperage}A`;
            return { known: true, limit, unit, count, at,
                describe: `${count} panels at ${at}` };
        }
        const limit = this.calculatePortCapacity(
            layer.bitDepth || 8, layer.frameRate || 60,
            layer.processorType || 'novastar-armor', !!layer.lowLatency);
        const unit = this.getFullPanelPixels(layer);
        if (!(limit > 0 && unit > 0)) return none;
        const count = Math.floor(limit / unit);
        const at = `${limit.toLocaleString()} px/port`;
        return { known: true, limit, unit, count, at,
            describe: `${count} panels at ${at}` };
    }

    // What ONE cabinet costs against the run it is being drawn onto.
    customHitLoad(kind, hitLayer, panel) {
        if (!panel) return 0;
        if (kind === 'power') {
            return (parseFloat(hitLayer && hitLayer.panelWatts) || 0)
                * this.getPanelLoadFactor(hitLayer, panel);
        }
        return this.getPanelPixelArea(panel);
    }

    // One run's fill: the load drawn so far, the cap it is drawn against, and
    // whether another whole cabinet still fits. `used` is in whole-cabinet
    // equivalents so the badge can read "9/14".
    customRunFill(owner, kind, num) {
        const cap = this.customRunCapacity(owner, kind);
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const path = (owner && owner[pathsKey] && owner[pathsKey][num]) || [];
        const load = this.getResolvedPathPanels(owner, path)
            .reduce((s, hit) => s + this.customHitLoad(kind, hit.layer, hit.panel), 0);
        const used = cap.unit > 0 ? load / cap.unit : 0;
        const eps = CUSTOM_RUN_EPS;
        return Object.assign({}, cap, {
            load, used,
            full: cap.known && (load + cap.unit > cap.limit + eps),
        });
    }

    // Does this cabinet still fit on the run?
    customRunAccepts(owner, kind, num, hitLayer, panel) {
        const fill = this.customRunFill(owner, kind, num);
        if (!fill.known) return true;
        return fill.load + this.customHitLoad(kind, hitLayer, panel)
            <= fill.limit + CUSTOM_RUN_EPS;
    }

    // "9", "13.7" - a whole count where it is one, a tenth where a half-tile
    // made it a fraction.
    _formatRunUsed(used) {
        const r = Math.round((Number(used) || 0) * 10) / 10;
        return Number.isInteger(r) ? `${r}` : r.toFixed(1);
    }

    _customRunLabel(owner, kind, num) {
        return kind === 'power'
            ? this.getPowerCircuitLabel(owner, num)
            : this.getPortLabelText(owner, num, 'primary');
    }

    // The refusal the click gets. Tab and ] are named because the run does
    // NOT advance on its own: a click that silently moved the cursor to the
    // next circuit would put the cabinet somewhere the user did not look.
    _customRunFullMessage(owner, kind, num) {
        const cap = this.customRunCapacity(owner, kind);
        const noun = kind === 'power' ? 'Circuit' : 'Port';
        return `${noun} ${this._customRunLabel(owner, kind, num)} is full — `
            + `${cap.describe}. Step to the next ${noun.toLowerCase()} (Tab / ]).`;
    }

    // The small line under the custom controls: the active run's fill against
    // the same cap the badge and the click use, so the limit is on screen
    // while the user is drawing and not only after the refusal.
    _syncCustomFillReadout(kind) {
        const el = document.getElementById(kind === 'power'
            ? 'power-custom-fill-readout' : 'custom-fill-readout');
        if (!el) return;
        const layer = this.currentLayer;
        const editing = layer && (layer.type || 'screen') === 'screen' && (kind === 'power'
            ? this.isCustomPowerEditing(layer) : this.isCustomFlowEditing(layer));
        if (!editing) {
            el.textContent = '';
            el.style.color = '';
            return;
        }
        const num = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        const fill = this.customRunFill(layer, kind, num);
        const head = `${kind === 'power' ? 'Circuit' : 'Port'} ${this._customRunLabel(layer, kind, num)}`;
        if (!fill.known) {
            const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
            const n = this.getResolvedPathPanels(layer,
                (layer[pathsKey] && layer[pathsKey][num]) || []).length;
            el.textContent = `${head}: ${n} panels — no cap (`
                + (kind === 'power'
                    ? 'set voltage, amperage and watts per panel)'
                    : 'no published port capacity for this processor)');
            el.style.color = '';
            return;
        }
        el.textContent = `${head}: ${this._formatRunUsed(fill.used)}/${fill.count} panels`
            + `${fill.full ? ' · full' : ''} (${fill.at})`;
        el.style.color = fill.full ? '#ffcc00' : '';
    }

    /**
     * Append a cabinet to the active port's path. `panelLayer` names the
     * screen the cabinet came from when it is not currentLayer; leaving it out
     * resolves it, so every existing single-screen caller is unchanged.
     *
     * The PORT stays on currentLayer even when the user clicked a peer's
     * cabinet - a port is one physical output on one processor, and only the
     * step records which screen the cable ran onto.
     */
    addPanelToCustomPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomFlowEditing(this.currentLayer)) return;
        if (this.customSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomFlowState(owner);
        const portNum = owner.customPortIndex || 1;
        if (!owner.customPortPaths[portNum]) owner.customPortPaths[portNum] = [];
        // Scoped key, not getPanelKey: R0C0 of the owner and R0C0 of a peer
        // are two different cabinets, and a bare `${row},${col}` compare would
        // refuse to add the second one.
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.customPortPaths[portNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        // Reject if the panel already belongs to a different port, user
        // must clear the existing assignment first. Avoids silent
        // double-mapping that the user has to undo manually.
        const conflict = this._findPanelOwnerPort(owner, panel, portNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'port');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        // Capacity: refused, not advanced. See customRunCapacity.
        if (!this.customRunAccepts(owner, 'data', portNum, source, panel)) {
            if (typeof this._toast === 'function') {
                this._toast(this._customRunFullMessage(owner, 'data', portNum), true);
            }
            return;
        }
        owner.customPortPaths[portNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel port assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.customDebug) {
            console.log('[CustomFlow] Add panel', {
                portNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        this.updatePortLabelEditor();
        this._syncCustomFillReadout('data');
        window.canvasRenderer.render();
    }

    addPanelToCustomPowerPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomPowerEditing(this.currentLayer)) return;
        if (this.powerCustomSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomPowerState(owner);
        const circuitNum = owner.powerCustomIndex || 1;
        if (!owner.powerCustomPaths[circuitNum]) owner.powerCustomPaths[circuitNum] = [];
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.powerCustomPaths[circuitNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        const conflict = this._findPanelOwnerCircuit(owner, panel, circuitNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'circuit');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        // Capacity: refused, not advanced. See customRunCapacity.
        if (!this.customRunAccepts(owner, 'power', circuitNum, source, panel)) {
            if (typeof this._toast === 'function') {
                this._toast(this._customRunFullMessage(owner, 'power', circuitNum), true);
            }
            return;
        }
        owner.powerCustomPaths[circuitNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Power Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel circuit assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.powerCustomDebug) {
            console.log('[CustomPower] Add panel', {
                circuitNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        this._syncCustomFillReadout('power');
        window.canvasRenderer.render();
    }

    /**
     * Where an arrow key takes the path from its current end.
     *
     * Returns `false` when there is nothing drawn yet (the key is NOT ours,
     * the caller lets it fall through), `null` when there is nowhere to go
     * (the key is swallowed, exactly as before), or {layer, panel}.
     */
    // Is the view this path is drawn in mirrored left-to-right?
    //
    // Rear perspective draws the canvas through ctx.scale(-1, 1), so world +X
    // appears on the viewer's LEFT. Anything that turns a user's intent into a
    // world-space direction has to account for that - the screen-name drag
    // already does (canvas.js, `_visualDx`).
    _pathViewIsMirrored(layer) {
        const cr = window.canvasRenderer;
        if (!cr || !layer || typeof cr._effectiveLayerCanvasId !== 'function') return false;
        if (typeof cr._isCanvasMirrored !== 'function') return false;
        const canvases = (this.project && this.project.canvases) || [];
        if (!Array.isArray(canvases)) return false;
        const cid = cr._effectiveLayerCanvasId(layer);
        const canvas = canvases.find(c => c && c.id === cid);
        return !!(canvas && cr._isCanvasMirrored(canvas));
    }

    _stepPathFromLastEntry(ownerLayer, path, dir) {
        if (!Array.isArray(path) || path.length === 0) return false;
        const last = this.resolvePathEntry(ownerLayer, path[path.length - 1]);
        if (!last) return null;
        const drow = dir === 'ArrowUp' ? -1 : (dir === 'ArrowDown' ? 1 : 0);
        let dcol = dir === 'ArrowLeft' ? -1 : (dir === 'ArrowRight' ? 1 : 0);
        // Issue #111: in Rear view the arrows walked the cable backwards -
        // Right went left and Left went right. The keys were never wrong; the
        // CANVAS is mirrored and the step was computed in unmirrored world
        // space. Flip the horizontal component so the cable follows the arrow
        // the user actually pressed. Vertical is unaffected: the mirror is
        // left-to-right only.
        //
        // Applied HERE rather than in handleCustomArrowKey so the cross-member
        // handoff below inherits it too - stepping off the right-hand edge in
        // Rear view has to look for the neighbour on the viewer's right.
        if (dcol !== 0 && this._pathViewIsMirrored(last.layer)) dcol = -dcol;
        // Step inside the END STEP'S OWN grid first. row/col are per-layer
        // indices, and this branch is byte-for-byte what the key did before.
        const within = this.getPanelByRowCol(
            last.layer, last.panel.row + drow, last.panel.col + dcol);
        if (within) return within.hidden ? null : { layer: last.layer, panel: within };
        // Grid edge. Before v0.11.0 the key was swallowed here with no feedback
        // at all, which inside a group is simply wrong: the wall continues, it
        // just continues on a different layer. Hand off GEOMETRICALLY, because
        // a member built from a different cabinet size has a completely
        // different index space - "row + 1" means nothing across the boundary
        // and only world coordinates do.
        return this._panelAcrossPathBoundary(ownerLayer, last, drow, dcol);
    }

    _panelAcrossPathBoundary(ownerLayer, from, drow, dcol) {
        if (!window.canvasRenderer || !from) return null;
        // An arrow key hands the cable to the cabinet the user can see next
        // door, so a hidden member is not a candidate - the same rule the
        // marquee and click-to-add follow. The hidden member's cabinets are
        // still where they were, so this walks PAST it exactly as it walks
        // past a gap: nothing is added and the key is swallowed.
        const peers = this.getSelectionScopeLayers(ownerLayer)
            .filter(l => l && l.id !== from.layer.id);
        if (peers.length === 0) return null;
        const p = from.panel;
        // Probe a hair PAST the edge we just walked off, centred on the other
        // axis. Aiming at "where the next cell would have been" instead would
        // land exactly on a shared cabinet boundary whenever the neighbouring
        // member's cabinets are a different size, and the hit-test is
        // inclusive at both edges - so it would be a coin flip which of the
        // peer's two cabinets answered.
        const eps = 1;
        const lx = p.x + (dcol > 0 ? p.width + eps : (dcol < 0 ? -eps : p.width / 2));
        const ly = p.y + (drow > 0 ? p.height + eps : (drow < 0 ? -eps : p.height / 2));
        const world = this._pathPointToWorld(from.layer, lx, ly);
        if (!world) return null;
        for (const peer of peers) {
            const local = this._pathPointFromWorld(peer, world.x, world.y);
            if (!local) continue;
            const hit = (peer.panels || []).find(q => local.x >= q.x
                && local.x <= q.x + q.width
                && local.y >= q.y && local.y <= q.y + q.height);
            if (hit) return hit.hidden ? null : { layer: peer, panel: hit };
        }
        return null;
    }

    // Layer space -> world, the exact inverse of canvas.js getPanelAt. The
    // offsets belong to the renderer, so they are CALLED here rather than
    // re-derived: a rotated or cross-canvas member would silently drift the
    // day one of them changed there and not here.
    _pathPointToWorld(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (!cr) return null;
        const r = this._rotatePathPoint(layer, lx, ly);
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return { x: r.x + dx + wx, y: r.y + dy + wy };
    }

    _pathPointFromWorld(layer, worldX, worldY) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr._unrotatePointForLayer !== 'function') return null;
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return cr._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
    }

    // Forward rotation. canvas.js ships the inverse (_unrotatePointForLayer)
    // and the pivot geometry (_layerRotationGeom) but not yet this direction;
    // the moment it grows a _rotatePointForLayer this picks it up instead, so
    // the two can never end up disagreeing about where a rotated screen's
    // cabinet actually sits.
    _rotatePathPoint(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (cr && typeof cr._rotatePointForLayer === 'function') {
            return cr._rotatePointForLayer(lx, ly, layer);
        }
        const g = (cr && typeof cr._layerRotationGeom === 'function')
            ? cr._layerRotationGeom(layer) : null;
        if (!g || (g.deg !== 90 && g.deg !== 180 && g.deg !== 270)) return { x: lx, y: ly };
        const rad = g.deg * Math.PI / 180;
        const cos = Math.cos(rad), sin = Math.sin(rad);
        const dx = lx - g.cx, dy = ly - g.cy;
        return { x: g.cx + (dx * cos - dy * sin), y: g.cy + (dx * sin + dy * cos) };
    }

    handleCustomArrowKey(e) {
        const dir = e.code;
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(dir)) return false;
        if (!this.currentLayer) return false;
        const isPower = window.canvasRenderer && window.canvasRenderer.viewMode === 'power';
        if (isPower) {
            if (!this.isCustomPowerEditing(this.currentLayer)) return false;
            this.ensureCustomPowerState(this.currentLayer);
            const circuitNum = this.currentLayer.powerCustomIndex || 1;
            const path = this.currentLayer.powerCustomPaths[circuitNum] || [];
            const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
            if (next === false) return false;
            if (next) this.addPanelToCustomPowerPath(next.panel, next.layer);
            return true;
        }
        if (!this.isCustomFlowEditing(this.currentLayer)) return false;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = this.currentLayer.customPortPaths[portNum] || [];
        const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
        if (next === false) return false;
        if (next) this.addPanelToCustomPath(next.panel, next.layer);
        return true;
    }

    // The wall lattice a pattern is ordered on. ONE implementation, and it is
    // the renderer's getPositionLattice - the same one the cabinet ID numbers
    // are assigned with (canvas.js _groupNumberingPlan). Two copies would
    // eventually disagree, and a serpentine that snakes the wall in a different
    // order than the IDs read is worse than no serpentine at all. It lives on
    // the renderer because the ranking needs getLayerRenderOffset.
    //
    // Null only when the renderer is missing entirely, and _orderPicksForPattern
    // then falls back to the panels' own row/col - the ordering this had before
    // v0.11.0. A degradation, deliberately, rather than a second lattice.
    _pathLattice(ownerLayer) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr.getPositionLattice !== 'function') return null;
        return cr.getPositionLattice(this.getPathScopeLayers(ownerLayer));
    }

    /**
     * The cabinets a scoped selection Set actually names, as {layer, panel}.
     *
     * Walked in path-scope order (owner first, then peers in group order) and
     * then in each member's own panel order, so an ungrouped screen yields the
     * exact list - and the exact order - the old `currentLayer.panels.filter()`
     * did. Hidden cabinets are dropped here, matching that filter.
     */
    _selectedPathPanels(ownerLayer, selection) {
        const out = [];
        if (!ownerLayer || !selection || selection.size === 0) return out;
        // Selection scope again, so a key that was already in the Set when its
        // screen was hidden cannot be committed by a later Apply Pattern. The
        // marquee is filtered at source; this is the same rule applied at the
        // moment of writing, which is the one that reaches the wall.
        this.getSelectionScopeLayers(ownerLayer).forEach(member => {
            if (!member || !Array.isArray(member.panels)) return;
            member.panels.forEach(panel => {
                if (panel.hidden) return;
                if (selection.has(this.getScopedPanelKey(member.id, panel))) {
                    out.push({ layer: member, panel });
                }
            });
        });
        return out;
    }

    /**
     * Put a cross-member selection into pattern order.
     *
     * The picks are placed on the WALL LATTICE (canvas.js getPositionLattice:
     * every member's column and row slots pooled and ranked by where they
     * physically sit), the lattice is compacted to just the rows and columns
     * the selection actually touches - exactly what the old uniqueRows /
     * uniqueCols pass did, only over positions rather than indices - and
     * getPatternOrderForGrid walks it. A serpentine therefore alternates
     * direction per LATTICE row and snakes across the whole wall instead of
     * per member.
     *
     * WHY position and not row/col indices. A 1m member's row 1 and a 0.5m
     * member's row 1 are different physical heights, so a pattern ordered by
     * the panels' own indices - which is what this did - zig-zags through an
     * order that exists nowhere on site. A cabinet spanning two lattice rows
     * ranks by its own top-left, exactly as step 5 numbers it.
     *
     * For a single ungrouped screen the lattice ranks that screen's own columns
     * by x and rows by y, which for any grid _build_panels produces is the
     * column and row index itself. The compacted grid is therefore identical
     * to the one this built before, and so is the order.
     *
     * The bucket is for genuinely OVERLAPPING members - two cabinets whose
     * top-left corners coincide land in one lattice cell. A plain grid write
     * would drop one of them from the path with no error; keeping the cell's
     * later arrivals and emitting them right behind the representative means a
     * selected cabinet can never silently vanish.
     */
    _orderPicksForPattern(ownerLayer, pattern, picks, grid = null) {
        if (!picks || picks.length === 0) return [];
        const g = grid || this._latticeGridForPicks(ownerLayer, picks);
        const ordered = this.getPatternOrderForGrid(pattern, g.grid);
        const out = [];
        ordered.forEach(pick => {
            const group = g.bucket.get(pick);
            if (group) out.push(...group);
            else out.push(pick);
        });
        return out;
    }

    // The picks laid out on the wall lattice, compacted to a dense grid: the
    // step above that getPatternOrderForGrid then walks.
    //
    // Split out of _orderPicksForPattern - not a second copy of it - because
    // automatic routing across a group's members (app-screen-info.js
    // getAutoRoutePlan) needs the same ranking AND needs to keep each cabinet's
    // compacted row and column afterwards: the Organized branch of the port and
    // circuit walks packs whole rows or columns, and on a group those are the
    // WALL's rows and columns, not one member's. Every expression here came
    // across unchanged, so the hand-drawn Apply Pattern order is untouched.
    _latticeGridForPicks(ownerLayer, picks) {
        const lattice = this._pathLattice(ownerLayer);
        const cells = (picks || []).map(pick => ({
            pick,
            row: lattice ? lattice.rowOf(pick.layer, pick.panel) : pick.panel.row,
            col: lattice ? lattice.colOf(pick.layer, pick.panel) : pick.panel.col,
        }));

        const uniqueRows = [...new Set(cells.map(c => c.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(cells.map(c => c.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const grid = Array.from({ length: uniqueRows.length },
            () => Array(uniqueCols.length).fill(null));
        const bucket = new Map();   // representative pick -> every pick in its cell
        // Panel object -> its compacted slot. Keyed by the object because
        // `${row},${col}` is exactly the address that names two cabinets at once
        // inside a group, which is the whole reason this lattice exists.
        const rowOf = new Map();
        const colOf = new Map();
        cells.forEach(c => {
            const r = rowIndex.get(c.row);
            const k = colIndex.get(c.col);
            rowOf.set(c.pick.panel, r);
            colOf.set(c.pick.panel, k);
            const held = grid[r][k];
            if (held === null) {
                grid[r][k] = c.pick;
                bucket.set(c.pick, [c.pick]);
            } else {
                bucket.get(held).push(c.pick);
            }
        });

        return {
            grid, bucket, rowOf, colOf,
            rows: uniqueRows.length, cols: uniqueCols.length,
        };
    }

    applyPatternToSelection(pattern) {
        this._applyPatternFill('data', pattern);
    }

    applyPowerPatternToSelection(pattern) {
        this._applyPatternFill('power', pattern);
    }

    // The pattern buttons on a selection, both sides through ONE walk.
    //
    // Used to write the WHOLE selection into the one active port or circuit.
    // Now it walks the selection in pattern order and fills the active run
    // up to its capacity (customRunCapacity - the sidebar's Panels/Circuit
    // and Panels/Port), then steps to the next number and keeps going until
    // the selection is consumed: a 14 x 6 block on serpentine at 14 a
    // circuit is circuits 1..6 at 14 apiece, in one gesture, every one of
    // them read from the side the first one started on.
    //
    // The numbers it fills are OVERWRITTEN - the active one always was, and
    // the ones it advances into are told on in the toast. A cabinet already
    // on a run OUTSIDE that set is a conflict and nothing is written, the
    // rule this has always had. One undo entry for the whole fill, and the
    // active index ends on the LAST number filled so the badge names what
    // was just drawn.
    //
    // With one overridden run open for redrawing, the numbers the fill may
    // step into are the layer's overrides after the open one - the same list
    // Tab walks - and a selection that needs more than those is refused
    // rather than spilled onto runs the user never took over.
    _applyPatternFill(kind, pattern) {
        const isPower = kind === 'power';
        if (!this.currentLayer || !window.canvasRenderer) return;
        // The PORT / CIRCUIT stays on currentLayer even when the selection
        // spans peers - a port is one physical output on one processor. Only
        // the individual step records which screen the cable ran onto.
        const owner = this.currentLayer;
        if (isPower ? !this.isCustomPowerEditing(owner) : !this.isCustomFlowEditing(owner)) return;
        const selection = isPower ? this.powerCustomSelection : this.customSelection;
        if (!selection || selection.size === 0) return;
        if (isPower) this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        const picks = this._selectedPathPanels(owner, selection);
        if (picks.length === 0) return;

        const lattice = this._latticeGridForPicks(owner, picks);
        const lines = this._patternLines(pattern, lattice.grid, lattice.bucket);
        if (lines.length === 0) return;

        const pathsKey = isPower ? 'powerCustomPaths' : 'customPortPaths';
        const idxKey = isPower ? 'powerCustomIndex' : 'customPortIndex';
        const noun = isPower ? 'circuit' : 'port';
        const startNum = owner[idxKey] || 1;
        const toast = (msg, isError) => {
            if (typeof this._toast === 'function') this._toast(msg, isError);
        };

        const cut = this._chunkPicksByCapacity(owner, kind, startNum, lines);
        if (cut.error) {
            toast(`Cannot apply: ${cut.error}`, true);
            return;
        }
        const chunks = cut.chunks;
        // The picks in the order they were dealt, run after run.
        const ordered = chunks.flatMap(c => c.picks);
        if (ordered.length === 0) return;
        const filled = new Set(chunks.map(c => c.num));

        // Reject the entire apply if any selected panel already belongs to a
        // run this fill will not overwrite. Prevents silent double-mapping.
        // The claim may live on a peer, which is why the sample names both
        // the cabinet's screen and the conflicting run's.
        const conflicts = [];
        for (const pick of ordered) {
            const claim = isPower
                ? this._findPanelOwnerCircuit(owner, pick.panel, startNum, pick.layer)
                : this._findPanelOwnerPort(owner, pick.panel, startNum, pick.layer);
            if (!claim) continue;
            if (!claim.foreign && filled.has(claim.number)) continue;
            conflicts.push({ pick, owner: claim });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `${this._describePathPanel(owner, c.pick.layer, c.pick.panel)}→${this._describePathConflict(c.owner, noun)}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ${noun}s, ${sample}${more}.`, true);
            return;
        }

        // Runs beyond the active one that held a drawing before this fill
        // replaced it - the toast says so.
        const replaced = chunks.map(c => c.num).filter(n => n !== startNum
            && ((owner[pathsKey][n] || []).length > 0));
        // makePathEntry omits layerId for the owner's own cabinets, so a path
        // that never leaves its screen is byte-for-byte the shape it has
        // always been written in.
        chunks.forEach(c => {
            owner[pathsKey][c.num] = c.picks
                .map(pick => this.makePathEntry(owner, pick.layer, pick.panel));
        });
        const lastNum = chunks[chunks.length - 1].num;
        owner[idxKey] = lastNum;
        if (this._overrideEditing && this._overrideEditing.kind === kind
                && this._overrideEditing.layerId === owner.id) {
            this._overrideEditing.num = lastNum;
        }
        this.saveState(isPower ? 'Power Custom Pattern Apply' : 'Custom Pattern Apply');
        this.saveClientSideProperties();
        // PUT to server so the bulk pattern assignment persists. The OWNER is
        // added explicitly - a marquee that ended on a peer can leave
        // currentLayer out of the layer selection entirely.
        this.updateLayers(this._pathPersistLayers(owner));
        if (chunks.length > 1) {
            const cap = this.customRunCapacity(owner, kind);
            let msg = `Filled ${noun}s ${this._customRunLabel(owner, kind, chunks[0].num)} to `
                + `${this._customRunLabel(owner, kind, lastNum)} from the selection`
                + ` (${cap.count} panels each at ${cap.at})`;
            if (replaced.length > 0) {
                msg += `; replaced ${noun}${replaced.length === 1 ? '' : 's'} `
                    + replaced.map(n => this._customRunLabel(owner, kind, n)).join(', ');
            }
            toast(`${msg}.`, false);
        }
        if (isPower ? this.powerCustomDebug : this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log(isPower ? '[CustomPower] Apply pattern' : '[CustomFlow] Apply pattern', {
                pattern,
                startNum,
                lastNum,
                count: ordered.length,
                runs: chunks.map(c => ({ num: c.num, count: c.picks.length })),
                first: first ? { row: first.panel.row, col: first.panel.col, layerId: first.layer.id } : null,
                last: last ? { row: last.panel.row, col: last.panel.col, layerId: last.layer.id } : null
            });
        }
        if (isPower) {
            this.updateCustomPowerUI();
        } else {
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        window.canvasRenderer.render();
    }

    // The next number a fill may step into after `num`: the open number line
    // in whole-screen custom, the layer's override list while one overridden
    // run is being redrawn (null when that list is exhausted). Mirrors
    // _steppedCustomIndex, which is what Tab does.
    _nextCustomRunNumber(owner, kind, num) {
        if (!this._isOverrideEditing(owner, kind)) return num + 1;
        const nums = this.getOverrideNums(owner, kind);
        const at = nums.indexOf(num);
        return (at >= 0 && at + 1 < nums.length) ? nums[at + 1] : null;
    }

    // Cut the pattern's lines into runs at capacity: [{num, picks, load}]
    // starting at `startNum`, each run holding as many picks as the cap
    // allows (a run always takes at least one). No cap known means one run
    // with everything.
    //
    // THE WALK. Within one run the lines snake - the first in the pattern's
    // own direction, the next back, and so on - because a run is one cable
    // daisy-chained through the block. A NEW run does not continue the
    // snake: it starts again from the pattern's start side, on whatever line
    // it begins, because its cable comes from where the first one's came
    // from. The user, 2026-09-04, on a 14-wide wall at 14 a circuit: "the
    // next row needs to restart on the same side as the serpentine started.
    // because the cables typically come from the same side." So a 14 x 6
    // block at 14 a circuit reads left to right on every row; a 12 x 2
    // block at 8 a port gives port 2 the right end of row 1 and, snaking,
    // the right end of row 2, and port 3 the rest of row 2 read from the
    // left. Where no cap is reached this is one run, and one run's snake is
    // the order getPatternOrderForGrid has always produced (two cabinets
    // sharing a lattice cell swap places on a reversed line, and nowhere
    // else).
    //
    // `error` instead when a single cabinet is over the cap on its own or
    // the override list runs out - nothing is written in either case.
    _chunkPicksByCapacity(owner, kind, startNum, lines) {
        const cap = this.customRunCapacity(owner, kind);
        const limit = cap.known ? cap.limit : Infinity;
        const eps = CUSTOM_RUN_EPS;
        const noun = kind === 'power' ? 'circuit' : 'port';
        const fmt = (v) => (kind === 'power'
            ? `${Math.round(v).toLocaleString()} W` : `${Math.round(v).toLocaleString()} px`);
        const chunks = [];
        let cur = { num: startNum, picks: [], load: 0 };
        let lineInRun = 0;
        // Close the run in hand and open the next number - or say why not.
        const closeRun = () => {
            chunks.push(cur);
            const next = this._nextCustomRunNumber(owner, kind, cur.num);
            if (next === null) {
                const taken = this.getOverrideNums(owner, kind)
                    .map(n => this._customRunLabel(owner, kind, n)).join(', ');
                return `the selection does not fit on the taken-over `
                    + `${noun}s (${taken}) at ${cap.describe}. Take over another `
                    + `run or select a narrower block.`;
            }
            cur = { num: next, picks: [], load: 0 };
            lineInRun = 0;
            return null;
        };
        for (const line of lines) {
            // What the line still has to give, kept in the pattern's own
            // direction; a reversed pass reads it from the far end.
            let cells = line.slice();
            while (cells.length > 0) {
                const reversed = lineInRun % 2 === 1;
                const seq = reversed ? cells.slice().reverse() : cells;
                let took = 0;
                for (const pick of seq) {
                    const load = this.customHitLoad(kind, pick.layer, pick.panel);
                    if (cap.known && load > limit + eps) {
                        return { error: `panel ${this._describePathPanel(owner, pick.layer, pick.panel)} `
                            + `is ${fmt(load)} and a ${noun} carries ${fmt(limit)}.` };
                    }
                    if (cur.picks.length > 0 && cur.load + load > limit + eps) break;
                    cur.picks.push(pick);
                    cur.load += load;
                    took += 1;
                }
                cells = reversed ? cells.slice(0, cells.length - took) : cells.slice(took);
                if (cells.length > 0) {
                    // Full with line to spare: this run is done, and the rest
                    // of the line opens the next one from the start side.
                    const why = closeRun();
                    if (why) return { error: why };
                }
            }
            lineInRun += 1;
        }
        chunks.push(cur);
        return { chunks };
    }

    // The compacted grid's lines - rows for a horizontal-first pattern,
    // columns for a vertical-first one - in the order the pattern visits
    // them, each line's cells in the pattern's own direction and never
    // reversed here. The serpentine's alternation belongs to whoever walks
    // the lines: getPatternOrderForGrid for one continuous snake,
    // _chunkPicksByCapacity per run. ONE home for the corner and direction
    // logic, so the two walks cannot drift apart. `bucket` expands a
    // representative pick into every pick sharing its cell.
    _patternLines(pattern, grid, bucket = null) {
        const rows = grid.length;
        const cols = rows > 0 ? grid[0].length : 0;
        if (rows === 0 || cols === 0) return [];

        const [startCorner, direction] = pattern.split('-');
        let startRow, startCol, rowDir, colDir;

        switch (startCorner) {
            case 'tl':
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1; break;
            case 'tr':
                startRow = 0; startCol = cols - 1; rowDir = 1; colDir = -1; break;
            case 'bl':
                startRow = rows - 1; startCol = 0; rowDir = -1; colDir = 1; break;
            case 'br':
                startRow = rows - 1; startCol = cols - 1; rowDir = -1; colDir = -1; break;
            default:
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1;
        }

        const expand = (pick) => (bucket && bucket.get(pick)) || [pick];
        const lines = [];
        if (direction === 'v') {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const line = [];
                for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                    if (grid[r] && grid[r][c]) line.push(...expand(grid[r][c]));
                }
                lines.push(line);
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const line = [];
                for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                    if (grid[r] && grid[r][c]) line.push(...expand(grid[r][c]));
                }
                lines.push(line);
            }
        }
        return lines;
    }

    // One continuous snake over the grid: the first line in the pattern's
    // own direction, every second line back. A line that is empty (hidden
    // cabinets, or a group's gap) still counts, so it does not reverse the
    // line after it - the rule this has always had.
    getPatternOrderForGrid(pattern, grid) {
        const ordered = [];
        this._patternLines(pattern, grid).forEach((line, i) => {
            ordered.push(...(i % 2 === 1 ? line.slice().reverse() : line));
        });
        return ordered;
    }
    
    renderLayers() {
        
        const container = document.getElementById('layers-list');
        container.innerHTML = '';
        
        if (!this.project || !this.project.layers) {
            console.error('RENDER LAYERS ERROR: No project or no layers array!');
            return;
        }
        
        // Debug: Log all layer IDs to check for duplicates
        const layerIds = this.project.layers.map(l => l.id);
        const uniqueIds = [...new Set(layerIds)];
        if (layerIds.length !== uniqueIds.length) {
            console.error('RENDER LAYERS: DUPLICATE IDs DETECTED!', layerIds);
        }
        
        console.log('RENDER LAYERS: currentLayer.id =', this.currentLayer?.id, 'all ids =', layerIds);
        
        // Reverse the layers array for display - standard (newest on top)
        const reversedLayers = [...this.project.layers].reverse();
        this.layerListOrder = reversedLayers.map(l => l.id);
        
        reversedLayers.forEach(layer => {
            const layerDiv = document.createElement('div');
            layerDiv.className = 'layer-item';
            layerDiv.dataset.layerId = layer.id;
            layerDiv.draggable = true;
            if (this.selectedLayerIds && this.selectedLayerIds.has(layer.id)) {
                layerDiv.classList.add('active');
            }
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                layerDiv.classList.add('primary');
            }
            // v0.8.7.7.1: visually distinguish hidden layers in the sidebar.
            if (layer.visible === false) {
                layerDiv.classList.add('hidden');
            }
            
            const layerType = layer.type || 'screen';
            const isImage = layerType === 'image';
            const isText = layerType === 'text';
            const activePanels = (isImage || isText) ? 0 : layer.panels.filter(p => !p.blank && !p.hidden).length;

            let infoText;
            if (isText) {
                const preview = (layer.textContent || '').substring(0, 30);
                infoText = `Text • ${layer.fontSize || 24}px${preview ? ' • ' + preview : ''}`;
            } else if (isImage) {
                infoText = `${layer.imageWidth || 0}×${layer.imageHeight || 0}px • ${Math.round((layer.imageScale || 1) * 100)}%`;
            } else {
                infoText = `${layer.columns}x${layer.rows} (${activePanels} panels) • ${layer.cabinet_width}×${layer.cabinet_height}px`;
            }
            const lockBadge = layer.locked ? '<span title="Locked" style="margin-left: 6px; color:#bbb;">🔒</span>' : '';
            // v0.8 Slice 2.5: per-layer ▲▼ arrows replace the global Up/Down
            // buttons. Disabled state (top/bottom of the layer's canvas group)
            // is computed in updateLayerOrderControls() after the regroup pass
            // so we know the within-canvas ordering.
            layerDiv.innerHTML = `
                <div class="layer-header">
                    <div style="display:flex; align-items:center; gap:4px; flex:1; min-width:0;">
                        <input type="text" class="layer-name-input" data-layer-id="${layer.id}" value="${layer.name}" style="background: transparent; border: 1px solid transparent; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; flex:1; min-width:0;">
                        ${lockBadge}
                    </div>
                    <div class="layer-controls">
                        <div class="layer-arrows">
                            <button class="layer-btn layer-move-up" data-layer-id="${layer.id}" title="Move up within canvas">▲</button>
                            <button class="layer-btn layer-move-down" data-layer-id="${layer.id}" title="Move down within canvas">▼</button>
                        </div>
                        <button class="layer-btn layer-visibility-btn ${layer.visible === false ? 'is-hidden' : ''}" onclick="app.toggleLayerVisibility(${layer.id})" title="${layer.visible === false ? 'Hidden, click to show' : 'Visible, click to hide'}">
                            ${layer.visible === false ? '🚫' : '👁'}
                        </button>
                    </div>
                </div>
                <div class="layer-info">
                    ${layer.visible === false ? '<span class="layer-hidden-badge">HIDDEN</span> ' : ''}${infoText}
                </div>
            `;
            
            // Per-layer reorder arrows (Slice 2.5).
            const upArrow = layerDiv.querySelector('.layer-move-up');
            const downArrow = layerDiv.querySelector('.layer-move-down');
            if (upArrow) {
                upArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (upArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, -1);
                });
            }
            if (downArrow) {
                downArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (downArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, 1);
                });
            }

            // Single click to select
            layerDiv.addEventListener('click', (e) => {
                if (!e.target.classList.contains('layer-btn') && !e.target.classList.contains('layer-name-input')) {
                    const isToggle = e.metaKey || e.ctrlKey;
                    const isRange = e.shiftKey;
                    if (isRange) {
                        this.selectLayerRange(layer);
                    } else if (isToggle) {
                        this.toggleLayerSelection(layer);
                    } else {
                        this.selectLayer(layer);
                    }
                }
            });

            // Right-click context menu on layer list
            layerDiv.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isToggle = e.metaKey || e.ctrlKey;
                if (isToggle) {
                    this.toggleLayerSelection(layer);
                } else {
                    this.selectLayer(layer);
                }
                this.showContextMenu(e.clientX, e.clientY);
            });

            const handleDragStart = (e) => {
                e.dataTransfer.setData('text/plain', String(layer.id));
                e.dataTransfer.effectAllowed = 'move';
                this.dragLayerId = layer.id;
            };
            layerDiv.addEventListener('dragstart', handleDragStart);
            const headerEl = layerDiv.querySelector('.layer-header');
            const infoEl = layerDiv.querySelector('.layer-info');
            if (headerEl) {
                headerEl.draggable = true;
                headerEl.addEventListener('dragstart', handleDragStart);
            }
            if (infoEl) {
                infoEl.draggable = true;
                infoEl.addEventListener('dragstart', handleDragStart);
            }
            layerDiv.addEventListener('dragover', (e) => {
                e.preventDefault();
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const position = e.clientY < midpoint ? 'top' : 'bottom';
                layerDiv.classList.toggle('drag-over-top', position === 'top');
                layerDiv.classList.toggle('drag-over-bottom', position === 'bottom');
                layerDiv.classList.add('drag-over');
                this.dragOverPosition = position;
            });
            layerDiv.addEventListener('dragleave', () => {
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
            });
            layerDiv.addEventListener('drop', (e) => {
                e.preventDefault();
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
                const draggedId = this.dragLayerId || parseInt(e.dataTransfer.getData('text/plain'), 10);
                const targetId = layer.id;
                if (!draggedId || draggedId === targetId) return;
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const insertAfter = e.clientY >= midpoint;
                this.reorderLayersByDrag(draggedId, targetId, insertAfter);
            });
            
            // Handle name input: single-click selects layer, double-click edits name
            const nameInput = layerDiv.querySelector('.layer-name-input');
            nameInput.readOnly = true;
            nameInput.draggable = true;
            nameInput.style.cursor = 'default';
            nameInput.addEventListener('dragstart', handleDragStart);

            const enterEditMode = () => {
                nameInput.readOnly = false;
                nameInput.draggable = false;
                nameInput.style.cursor = 'text';
                // v0.11.0: class, not inline - theme.css styles .layer-name-input
                // with !important, so an inline border/background never painted.
                nameInput.classList.add('editing');
                nameInput.focus();
                nameInput.select();
            };

            const exitEditMode = () => {
                nameInput.readOnly = true;
                nameInput.draggable = true;
                nameInput.style.cursor = 'default';
                nameInput.classList.remove('editing');
                const newName = nameInput.value.trim() || layer.name;
                if (newName !== layer.name) {
                    layer.name = newName;
                    fetch(`/api/layer/${layer.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                    });
                    // Record the rename so it's undoable on its own; without
                    // this the local name change rode along on the next action
                    // and a later undo restored a stale name (client/server
                    // desync). The renameLayer() path already does this.
                    this.saveState('Rename Layer');
                }
            };

            nameInput.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                enterEditMode();
            });
            nameInput.addEventListener('blur', exitEditMode);
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    nameInput.blur();
                }
                if (!nameInput.readOnly) e.stopPropagation();
            });
            
            container.appendChild(layerDiv);
        });

        // v0.8 Slice 2: regroup the flat layer list by canvas. The existing
        // layer items above are preserved as-is, we just lift them into
        // per-canvas group containers and add canvas headers + per-canvas
        // "+ Add Screen" buttons + cross-canvas drag/drop.
        this.regroupLayersByCanvas(container);

        // v0.11.0: then nest each screen group's member rows under a group
        // header, INSIDE the canvas group they already sit in. Runs after the
        // canvas pass because it lifts the rows that pass has just placed.
        this.regroupLayersByGroup(container);

        this.updateLayerOrderControls();
    }

    // -------------------------------------------------------------------
    // Multi-canvas (v0.8 Slice 2), sidebar canvas grouping.
    //
    // Slice 2 keeps workspace rendering unchanged; the sidebar restructure
    // is the entire visible deliverable. Each canvas gets a header row
    // (color swatch / name / 👁 / ⋮ / drag handle), its layers underneath
    // (filtered by layer.canvas_id), and a per-canvas "+ Add Screen"
    // button. A canvas drag handle reorders canvases. Layers can be
    // dragged onto another group's header to move them cross-canvas
    // (Cmd/Alt = duplicate).
    // -------------------------------------------------------------------
}

for (const k of Object.getOwnPropertyNames(_Power.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Power.prototype, k));
    }
}
