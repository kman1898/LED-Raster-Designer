// app-menubar: the top menu bar - setupMenuBar wires the dropdowns,
// handleMenuAction dispatches every menu item, and the Move-to-Canvas,
// Shortcuts and About surfaces open from here. Moved verbatim out of
// app-export-io.js and attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _MenuBar {
    setupMenuBar() {
        const menuItems = document.querySelectorAll('#menu-bar .menu-item');
        const menus = document.querySelectorAll('.menu-dropdown');
        const hideMenus = () => {
            menus.forEach(menu => menu.style.display = 'none');
            menuItems.forEach(item => item.classList.remove('active'));
        };

        this.updateShortcutLabels();

        menuItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const menuId = `menu-${item.dataset.menu}`;
                const menu = document.getElementById(menuId);
                if (!menu) return;
                const rect = item.getBoundingClientRect();
                const isVisible = menu.style.display === 'block';
                hideMenus();
                if (!isVisible) {
                    menu.style.display = 'block';
                    menu.style.left = `${rect.left}px`;
                    menu.style.top = `${rect.bottom + 4}px`;
                    item.classList.add('active');
                }
            });
        });

        document.addEventListener('click', () => {
            hideMenus();
            this.hideContextMenu();
        });
        window.addEventListener('resize', () => {
            hideMenus();
            this.hideContextMenu();
        });

        const handleMenuClick = (e) => {
            const target = e.target.closest('.menu-option');
            if (!target) return;
            // Don't close menu when hovering over submenu parent
            if (target.classList.contains('menu-has-submenu')) return;
            // A disabled item is a sentence, not a control: it stays put so
            // its title (the reason) can be read, and clicking it neither
            // acts nor closes the menu - native menu behaviour.
            if (target.classList.contains('menu-disabled')) return;
            const action = target.dataset.action;
            if (!action) return;
            hideMenus();
            this.handleMenuAction(action);
        };
        document.querySelectorAll('.menu-dropdown').forEach(menu => {
            menu.addEventListener('click', handleMenuClick);
        });

        const contextMenu = document.getElementById('context-menu');
        if (contextMenu) {
            contextMenu.addEventListener('click', handleMenuClick);
        }

        if (!this.globalContextMenuBound) {
            const appRoot = document.getElementById('app') || document.body;
            appRoot.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e.clientX, e.clientY);
            });
            this.globalContextMenuBound = true;
        }

        // Populate recent files submenu
        this.updateRecentFilesMenu();
    }

    // ONE platform read for every printed accelerator - the menu labels
    // and the Keyboard Shortcuts modal both say Cmd on a Mac and Ctrl
    // elsewhere, and they must never disagree.
    _isMacPlatform() {
        return /Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac/.test(navigator.userAgent);
    }

    updateShortcutLabels() {
        const isMac = this._isMacPlatform();
        document.querySelectorAll('.menu-option[data-label]').forEach(option => {
            // Skip options with submenus, they manage their own content
            if (option.classList.contains('menu-has-submenu')) return;
            const label = option.getAttribute('data-label') || '';
            const shortcut = isMac ? option.getAttribute('data-shortcut-mac') : option.getAttribute('data-shortcut-win');
            if (shortcut) {
                option.textContent = `${label} (${shortcut})`;
            } else {
                option.textContent = label;
            }
        });
    }

    // Move the selected layers to another canvas from the right-click menu.
    //
    // The canvas list is built when the menu opens rather than declared in the
    // template: canvases are added, renamed and deleted at runtime, so a static
    // list would go stale. Follows the same popup shape as the per-canvas
    // "+ Add" chooser so the two feel like the same control.
    //
    // Layers keep their position when they move (routes_layers.move_layer_to_
    // canvas) - canvases share a coordinate space, so a screen lands where it
    // already was rather than jumping to the corner.
    openMoveToCanvasMenu() {
        const layers = this.getSelectedLayers().filter(l => !l.locked);
        if (layers.length === 0) return;
        const canvases = (this.project && this.project.canvases) || [];
        // Where the selection already lives. With a mixed selection every
        // canvas is a real destination for something, so nothing is excluded.
        const originIds = new Set(layers.map(l => l.canvas_id));
        const targets = canvases.filter(c => !(originIds.size === 1 && originIds.has(c.id)));
        if (targets.length === 0) return;

        document.querySelectorAll('.canvas-add-popup, .canvas-menu-popup, .canvas-color-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup canvas-add-popup';
        menu.innerHTML = targets
            .map(c => `<button data-canvas-id="${c.id}">${c.name}</button>`)
            .join('');
        document.body.appendChild(menu);

        const cm = document.getElementById('context-menu');
        const r = cm ? cm.getBoundingClientRect() : { left: 100, top: 100, width: 0 };
        menu.style.position = 'fixed';
        menu.style.left = `${Math.min(r.left + Math.max(r.width, 40), window.innerWidth - 180)}px`;
        menu.style.top = `${Math.max(8, Math.min(r.top, window.innerHeight - 40 - targets.length * 28))}px`;
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
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const canvasId = btn.dataset.canvasId;
                close();
                // ONE BATCH, not a layer at a time, because a group is one
                // wall. /api/layer/<id>/canvas can only ever see ONE layer,
                // so it has to assume the rest of the wall is staying where
                // it is: it takes the member out of its group on the way
                // across (_detach_from_cross_canvas_group), and what is left
                // of a group of one is dissolved. Run over three members
                // that delivered three loose screens on the target canvas.
                // moveLayersCrossCanvas is the same gesture the cross-canvas
                // DRAG already goes through: it still PUTs sequentially (the
                // server answers with the whole project, so overlapping calls
                // would race and the last response would undo the others),
                // but it snapshots the whole walls inside the batch first and
                // puts them back together once every PUT has landed. Layers
                // already sitting on the destination are handed over too - in
                // a mixed selection they can be members of a wall the rest of
                // the batch is bringing, and the batch has to see all of it
                // to recognize a whole wall; the PUT is a no-op move for them.
                await this.moveLayersCrossCanvas(layers.map(l => l.id), canvasId, 'move');
                sendClientLog('move_to_canvas', { count: layers.length, canvasId });
            });
        });
    }

    handleMenuAction(action) {
        switch (action) {
            case 'new':
                this.createNewProject();
                break;
            case 'open':
                this.loadProjectFromFile();
                break;
            case 'save':
                this.saveProjectToFile();
                break;
            case 'export-png':
                this.openExportModal('png');
                break;
            case 'export-psd':
                this.openExportModal('psd');
                break;
            case 'pull-sheet':
                // The in-app editor over the pull list (app-pull-sheet-editor.js).
                this.openPullSheetEditor();
                break;
            case 'export-pull-sheet':
                this.openExportModal('pull-sheet');
                break;
            case 'export-binder':
                this.openExportModal('binder');
                break;
            // The canvas's right-click on a screen (app-binder.js): the same
            // dialog, preset to that screen's pages alone.
            case 'export-screen-binder':
                this.openScreenBinderExport(this._binderMenuLayer || this.currentLayer);
                break;
            case 'preferences':
                this.openPreferencesModal();
                break;
            case 'undo':
                this.undo();
                break;
            case 'redo':
                this.redo();
                break;
            case 'copy':
                this.copyLayer();
                break;
            case 'paste':
                this.pasteLayer();
                break;
            case 'duplicate':
                if (this.currentLayer) this.duplicateLayer(this.currentLayer);
                break;
            case 'delete':
                if (this.currentLayer) this.deleteLayer(this.currentLayer.id);
                break;
            // v0.11.0: screen groups. showContextMenu() hides these when the
            // selection cannot take them, and each action re-checks, so a
            // keyboard-driven call can't make a group of one either.
            case 'group-screens':
                this.groupSelectedLayers();
                break;
            case 'ungroup-screens':
                this.ungroupSelectedLayers();
                break;
            case 'remove-from-group':
                this.removeSelectedFromGroup();
                break;
            case 'center-x':
                this.centerLayersOnCanvas('x');
                break;
            case 'center-y':
                this.centerLayersOnCanvas('y');
                break;
            case 'center-both':
                this.centerLayersOnCanvas('both');
                break;
            case 'move-to-canvas':
                this.openMoveToCanvasMenu();
                break;
            case 'next-port':
                this.stepCustomPort(1);
                break;
            case 'prev-port':
                this.stepCustomPort(-1);
                break;
            // The assignment clear armed for this opening of the menu
            // (showContextMenu stored it). Re-checked here rather than
            // trusted: the disabled guard in handleMenuClick already blocks
            // the click, but a keyboard-driven call must not clear either.
            case 'hw-clear':
                if (this._clearMenuAction && !this._clearMenuAction.disabled
                        && typeof this._clearMenuAction.run === 'function') {
                    this._clearMenuAction.run();
                }
                break;
            // The merge-back armed for this opening of the menu, same
            // doctrine as the clear above: stored at open time, re-checked
            // here so a keyboard-driven call cannot merge what the cursor
            // never named.
            case 'hw-merge':
                if (this._mergeMenuAction
                        && typeof this._mergeMenuAction.run === 'function') {
                    this._mergeMenuAction.run();
                }
                break;
            // Circuit sharing, same doctrine: armed at open time on the
            // circuit the cursor named, re-checked here.
            case 'hw-share':
                if (this._shareMenuAction
                        && typeof this._shareMenuAction.run === 'function') {
                    this._shareMenuAction.run();
                }
                break;
            case 'hw-unshare':
                if (this._unshareMenuAction
                        && typeof this._unshareMenuAction.run === 'function') {
                    this._unshareMenuAction.run();
                }
                break;
            // The batch verb's entries, armed at open time on the sweep
            // selection (or the whole screen) the cursor named - re-checked
            // here like every hw item, disabled included: a gated entry
            // stays on the menu to be read, never to run.
            case 'hw-batch-n0':
            case 'hw-batch-n1':
            case 'hw-batch-n2': {
                const i = parseInt(action.slice(-1), 10);
                const en = this._batchMenuActions
                    && this._batchMenuActions.entries
                    && this._batchMenuActions.entries[i];
                if (en && !en.disabled && typeof en.run === 'function') {
                    en.run();
                }
                break;
            }
            case 'hw-batch-unshare':
                if (this._batchMenuActions && this._batchMenuActions.unshare
                        && typeof this._batchMenuActions.unshare.run === 'function') {
                    this._batchMenuActions.unshare.run();
                }
                break;
            // The data snake entries (2026-09-06), armed at open time on
            // the lit chips, a snake's tag or a snaked chip - re-checked
            // here like every hw item.
            case 'hw-snake-n0':
            case 'hw-snake-n1':
            case 'hw-snake-n2':
            case 'hw-snake-n3': {
                const i = parseInt(action.slice(-1), 10);
                const en = this._snakeMenuActions
                    && this._snakeMenuActions.entries
                    && this._snakeMenuActions.entries[i];
                if (en && !en.disabled && typeof en.run === 'function') {
                    en.run();
                }
                break;
            }
            // Per-run override, same doctrine as the clears above: armed at
            // open time on the run the cursor named, re-checked here.
            case 'ovr-redraw':
                if (this._overrideMenuActions && this._overrideMenuActions.redraw
                        && typeof this._overrideMenuActions.redraw.run === 'function') {
                    this._overrideMenuActions.redraw.run();
                }
                break;
            case 'ovr-auto':
                if (this._overrideMenuActions && this._overrideMenuActions.backToAuto
                        && typeof this._overrideMenuActions.backToAuto.run === 'function') {
                    this._overrideMenuActions.backToAuto.run();
                }
                break;
            case 'bulk-set-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), true);
                break;
            case 'bulk-unset-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), false);
                break;
            case 'bulk-set-half-auto':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'auto');
                break;
            case 'bulk-set-half-width':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'width');
                break;
            case 'bulk-set-half-height':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'height');
                break;
            case 'bulk-clear-half':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'none');
                break;
            case 'fit':
                if (window.canvasRenderer) window.canvasRenderer.fitToView();
                break;
            case 'actual-size':
                if (window.canvasRenderer) {
                    window.canvasRenderer.zoom = 1;
                    window.canvasRenderer.panX = 0;
                    window.canvasRenderer.panY = 0;
                    window.canvasRenderer.render();
                }
                break;
            case 'toggle-snap':
                if (window.canvasRenderer) {
                    window.canvasRenderer.magneticSnap = !window.canvasRenderer.magneticSnap;
                    const snapCb = document.getElementById('magnetic-snap');
                    if (snapCb) snapCb.checked = window.canvasRenderer.magneticSnap;
                }
                break;
            case 'quick-start':
                if (window.QuickStart) window.QuickStart.start();
                break;
            case 'whats-new-tour':
                if (window.QuickStart) window.QuickStart.startWhatsNew();
                break;
            case 'advanced-guide':
                if (window.QuickStart) window.QuickStart.startAdvanced();
                break;
            case 'whats-new':
                if (window.WhatsNew) window.WhatsNew.open();
                break;
            case 'keyboard-shortcuts':
                this.openShortcutsModal();
                break;
            case 'show-logs':
                this.openLogsModal();
                break;
            case 'about':
                this.openAboutModal();
                break;
            default:
                if (action && action.startsWith('recent-file-')) {
                    const idx = parseInt(action.replace('recent-file-', ''), 10);
                    this.loadRecentFile(idx);
                }
                // The outputs submenu's entries, armed at open time on the
                // screen the cursor named (showContextMenu stored them),
                // re-checked here like every hw item - a disabled entry is
                // a sentence, never a control.
                if (action && action.startsWith('hw-out-')) {
                    const i = parseInt(action.replace('hw-out-', ''), 10);
                    const en = this._outputsMenuActions
                        && this._outputsMenuActions.entries
                        && this._outputsMenuActions.entries[i];
                    if (en && !en.disabled && typeof en.run === 'function') {
                        en.run();
                    }
                }
                // "Put on beach" submenu (app-beaches.js): beach-new makes
                // one and puts the selection on it; beach-<n> is the n-th
                // beach armed at open time. 'beach-menu' itself is the
                // submenu's parent and never reaches here.
                if (action === 'beach-new') {
                    const nb = this._beachMenuActions
                        && this._beachMenuActions.newBeach;
                    if (nb && typeof nb.run === 'function') nb.run();
                } else if (action && /^beach-\d+$/.test(action)) {
                    const i = parseInt(action.replace('beach-', ''), 10);
                    const en = this._beachMenuActions
                        && this._beachMenuActions.entries
                        && this._beachMenuActions.entries[i];
                    if (en && typeof en.run === 'function') en.run();
                }
                break;
        }
    }

    openShortcutsModal() {
        var modal = document.getElementById('shortcuts-modal');
        if (!modal) return;
        // The modifier reads the way the menus print it (updateShortcutLabels):
        // every [data-sc-mod] span in the modal is Cmd on a Mac, Ctrl elsewhere.
        var mod = this._isMacPlatform() ? 'Cmd' : 'Ctrl';
        modal.querySelectorAll('[data-sc-mod]').forEach(function(el) {
            el.textContent = mod;
        });
        modal.style.display = 'block';
        var closeBtn = document.getElementById('shortcuts-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }

    openAboutModal() {
        var modal = document.getElementById('about-modal');
        if (!modal) return;
        var versionEl = document.getElementById('about-version');
        if (versionEl) {
            fetch('/api/version')
                .then(function(r) { return r.json(); })
                .then(function(d) { versionEl.textContent = 'v' + (d.version || ''); })
                .catch(function() { versionEl.textContent = ''; });
        }
        modal.style.display = 'block';
        var closeBtn = document.getElementById('about-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }
}

for (const k of Object.getOwnPropertyNames(_MenuBar.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_MenuBar.prototype, k));
    }
}
