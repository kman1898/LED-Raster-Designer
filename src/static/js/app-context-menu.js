// app-context-menu: the canvas right-click menu for LEDRasterApp - building
// and showing it, hiding it, and the Center on Canvas verbs it offers. It
// also owns _esc, the escaping alias every sidebar panel builder passes
// user text through before interpolating it into innerHTML.
import { LEDRasterApp } from './app-core.js';

class _ContextMenu {

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
        // snake - "Snake these N", "Set home run…", "Unsnake", "Rename"
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
}

for (const k of Object.getOwnPropertyNames(_ContextMenu.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ContextMenu.prototype, k));
    }
}
