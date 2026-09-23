// LEDRasterApp core: constructor, socket wiring, and primary UI setup.
// Feature areas live in the app-*.js modules, which extend the prototype.
import { evaluateMathExpression, sendClientLog, setupColorPickerWithHex } from './helpers.js';

export class LEDRasterApp {
    constructor() {
        this.project = null;
        this.socket = null;
        this.currentLayer = null;
        this.selectedLayerIds = new Set();
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        this.customSelectMode = false;
        // Manual data-flow / power selections. v0.11.0: Sets of SCOPED keys,
        // `${layerId}:${row},${col}` (app-power.js getScopedPanelKey), because
        // a marquee over a screen group has to be able to name member A's R0C0
        // and member B's R0C0 as two different cabinets. Under the unscoped
        // `${row},${col}` they were ONE entry, which is why a cross-member
        // selection could only ever have committed the owner's cabinets under
        // the peer's row and column. Anything reading these back must resolve
        // the layer id first - see canvas.js renderCustomSelectionOverlay.
        this.customSelection = new Set();
        this.customDebug = false;
        this.powerCustomSelection = new Set();
        this.powerCustomDebug = false;
        // Pixel Map bulk-select: drag-select panels of the current layer to
        // bulk-toggle blank or half-tile state. Set of "row,col" strings -
        // deliberately still UNSCOPED (getPanelKey). This is a single-screen
        // feature, nothing about it is grouped, and its overlay parses the key
        // back with split(','), which a layer id in front would silently break.
        this.pixelMapSelection = new Set();
        
        // Undo/Redo system
        this.history = [];
        this.historyIndex = -1;
        this.maxHistory = 50;
        this._saveStateTimer = null;
        this._pendingSaveAction = null;
        
        // Clipboard for copy/paste
        this.clipboard = null;
        
        // Prevent double-delete
        this.deletionInProgress = false;

        // Track whether the initial loadProject() has completed.
        // When true, socket project_data events are reconnects (skip preference enforcement).
        // When false, it's a cold start (allow preferences to apply).
        this._initialLoadComplete = false;

        this.init();
    }
    
    init() {
        window.canvasRenderer = new CanvasRenderer('main-canvas');

        // Restore collapsed sidebar state before anything paints so there's
        // no flash of the open panel.
        this.initSidebarToggles();
        // Same doctrine one level down: per-section collapse, restored
        // before first paint.
        this.initSectionCollapse();
        // The Signal and Power panels' markup ships hidden, which is right for
        // the pixel-map view the app opens on. Reconcile anyway so neither can
        // be left behind if the renderer ever boots on another view.
        this.updateViewSidebars(window.canvasRenderer.viewMode);

        // Check server session FIRST - if server restarted, clear localStorage
        this.checkServerSession().then(() => {
            // Never let a socket/transport failure block the rest of boot. If
            // io() is missing or throws, the app must still load the project and
            // wire up interactions (it just won't get live push updates).
            try {
                this.connectWebSocket();
            } catch (e) {
                console.error('WebSocket init failed; continuing without live updates:', e);
            }
            this.loadProject();
            this.setupEventListeners();
            // The Processors panel is project state, not layer state, so it
            // loads its own catalog and its own tree rather than waiting on a
            // selection. A project with no processors leaves it empty and
            // touches nothing else.
            this.initProcessorPanel();
            this.initPortAssignmentPanel();
            // The hardware dock draws the same processor and distro state
            // the panels do, so it initialises alongside them.
            this.initHardwareDock();
            sendClientLog('app_init', { ua: navigator.userAgent });
            // Background-check upstream panel catalog after the rest of boot
            // settles so we don't slow first paint. Failure is silent.
            setTimeout(() => this.checkPanelCatalogUpdate(), 1500);
        });
    }

    /**
     * Wire the sidebar collapse toggles. Each panel is independent and its
     * collapsed state persists in localStorage so the panel stays
     * the way the user left it across reloads. The toggle button is
     * positioned dynamically against the sidebar's actual geometry (via
     * getBoundingClientRect), so it always sits flush with the sidebar's
     * inner edge regardless of monitor size, sidebar width, or window
     * resize. ResizeObserver keeps it pinned in place if the sidebar's
     * dimensions ever change at runtime.
     *
     * `edge` is which side of the app the panel docks to, and it is NOT the
     * same thing as `key`: the Signal and Power panels are middle columns that
     * dock left like the left sidebar, so their toggles hug their right-hand
     * edges the same way, but their storage keys have to stay their own.
     * The hardware dock is the horizontal member of the family - it docks to
     * the BOTTOM of the canvas column, so its chevrons point down/up and its
     * toggle hugs its top edge, the sidebars' rule turned on its side.
     */
    initSidebarToggles() {
        const sides = [
            // The Signal and Power middle rows retired with their sidebars:
            // the hardware dock is the one view-scoped member left.
            { key: 'left', edge: 'left', label: 'left', sidebarId: 'left-sidebar', toggleId: 'left-sidebar-toggle', expandSym: '›', collapseSym: '‹' },
            { key: 'right', edge: 'right', label: 'right', sidebarId: 'right-sidebar', toggleId: 'right-sidebar-toggle', expandSym: '‹', collapseSym: '›' },
            { key: 'dock', edge: 'bottom', label: 'hardware', sidebarId: 'hardware-dock', toggleId: 'hardware-dock-toggle', expandSym: '▴', collapseSym: '▾' },
        ];
        // Kept so a panel entering or leaving layout (see
        // updateViewSidebars) can re-pin every toggle at once.
        this._sidebarPositioners = [];
        sides.forEach(({ key, edge, label, sidebarId, toggleId, expandSym, collapseSym }) => {
            const sidebar = document.getElementById(sidebarId);
            const btn = document.getElementById(toggleId);
            if (!sidebar || !btn) return;
            const storageKey = `ledRasterSidebarCollapsed_${key}`;
            const positionToggle = () => {
                const rect = sidebar.getBoundingClientRect();
                if (edge === 'left') {
                    btn.style.left = `${Math.round(rect.right)}px`;
                    btn.style.right = '';
                } else if (edge === 'right') {
                    btn.style.right = `${Math.round(window.innerWidth - rect.left)}px`;
                    btn.style.left = '';
                } else {
                    // Bottom-docked: the toggle hangs above the tray's top
                    // edge, centred on it - "hug the inner edge" turned on
                    // its side. The CSS translate(-50%, -100%) makes these
                    // coordinates the tab's centre and bottom.
                    btn.style.left = `${Math.round(rect.left + rect.width / 2)}px`;
                    btn.style.top = `${Math.round(rect.top)}px`;
                    btn.style.right = '';
                }
            };
            const apply = (collapsed) => {
                sidebar.classList.toggle('collapsed', collapsed);
                document.body.classList.toggle(`${key}-sidebar-collapsed`, collapsed);
                btn.textContent = collapsed ? expandSym : collapseSym;
                btn.title = collapsed
                    ? `Expand ${label} panel`
                    : `Collapse ${label} panel`;
                this.settleLayout();
            };
            const saved = localStorage.getItem(storageKey) === '1';
            apply(saved);
            btn.addEventListener('click', () => {
                const nowCollapsed = !sidebar.classList.contains('collapsed');
                localStorage.setItem(storageKey, nowCollapsed ? '1' : '0');
                apply(nowCollapsed);
                if (typeof sendClientLog === 'function') {
                    sendClientLog('sidebar_toggle', { side: key, collapsed: nowCollapsed });
                }
            });
            // Keep the toggle pinned to the sidebar edge whenever the
            // sidebar resizes (window resize, scrollbar appearance, etc.).
            if (typeof ResizeObserver === 'function') {
                new ResizeObserver(positionToggle).observe(sidebar);
            }
            window.addEventListener('resize', positionToggle);
            this._sidebarPositioners.push(positionToggle);
        });
    }

    /**
     * Collapsible sections, one mechanism for every titled block.
     *
     * Every section title bar carried a ▾ glyph (theme.css ::after) that did
     * nothing. It is now the collapse affordance, with one behaviour
     * everywhere it appears (user spec, fixed):
     *
     *   - a single click on the ARROW collapses/expands the section
     *   - a DOUBLE-click anywhere on the header does the same; a single
     *     click on the header does nothing, so stray clicks are harmless
     *   - state persists per section (ledRasterPanelCollapsed_<id>) and is
     *     independent of the sidebar-level collapse above
     *
     * Two header shapes come through here: the static .panel-header bars
     * (arrow at the right, where the decorative glyph sat) and the generated
     * block headings inside the Power panel (.lrd-sec-head, arrow leading
     * the title the way the screen-group rows lead with theirs). Both hide
     * their body with a class - never detach it - so getElementById lookups
     * and live references into a collapsed section keep working, and the
     * hosts that rebuild with innerHTML re-wire themselves by calling
     * _wireSectionCollapse(host) after every render.
     *
     * A focus restore into a collapsed section auto-expands it
     * (_expandSectionsFor, called from _preserveEditorFocus): a field the
     * app is putting the user's caret back into must not be display:none.
     */
    initSectionCollapse() {
        this._wireSectionCollapse(document);
    }

    _wireSectionCollapse(scope) {
        scope.querySelectorAll('.panel-header, .lrd-sec-head').forEach(head => {
            if (head.dataset.lrdSecWired) return;
            const container = head.parentElement;
            if (!container) return;
            const generated = head.classList.contains('lrd-sec-head');
            const body = container.querySelector(
                generated ? ':scope > .lrd-sec-body' : ':scope > .panel-content');
            if (!body) return;   // a bar with nothing under it has nothing to fold
            // The id is what the collapsed state persists under, so it must
            // be stable across reloads and unique across sections. Generated
            // heads declare theirs (data-lrd-sec); the static panels derive
            // tab + title, which disambiguates the three "Image Layer" bars.
            let id = head.dataset.lrdSec;
            if (!id) {
                const h2 = head.querySelector('h2, h3');
                const slug = ((h2 ? h2.textContent : head.textContent) || '')
                    .trim().toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                if (!slug) return;
                const tab = container.dataset.tab || '';
                id = tab ? `${tab}--${slug}` : slug;
            }
            head.dataset.lrdSecWired = '1';
            head.classList.add('lrd-sec-click');
            container.dataset.lrdSecId = id;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'lrd-sec-arrow';
            // Out of the tab ring on purpose: the headers sit between every
            // panel's fields, and a focusable stop there would rewrite the
            // tab order the editors' focus tests pin. The arrow is a pointer
            // affordance; double-click serves the same gesture.
            btn.tabIndex = -1;
            btn.textContent = '▾';
            if (generated) {
                // Lead the title with the arrow, the way the screen-group
                // rows do. Into the title LABEL when the head is a flex row
                // (the distro heading carries buttons beside its label) so
                // the arrow wraps with the title instead of stranding on its
                // own line at the 180px clamp.
                const anchor = head.querySelector(':scope > label') || head;
                anchor.insertBefore(btn, anchor.firstChild);
            } else {
                head.appendChild(btn);
            }
            const toggle = () => this._setSectionCollapsed(
                container, !container.classList.contains('lrd-sec-collapsed'));
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggle();
            });
            head.addEventListener('dblclick', (e) => {
                // A double-click that lands on a real control is the
                // control's, not ours - the distro heading carries the
                // Balance and + Add buttons. Our own arrow still counts.
                const hit = e.target.closest && e.target.closest(
                    'button, input, select, textarea');
                if (hit && hit !== btn) return;
                toggle();
            });
            this._setSectionCollapsed(container,
                localStorage.getItem(`ledRasterPanelCollapsed_${id}`) === '1');
        });
    }

    // Whether `container`'s fold hides `el`: the fold hides exactly the
    // section's body (.lrd-sec-body / .panel-content, style.css), so an
    // element on the header or on anything the section carries outside
    // its body stays visible through the fold.
    _sectionFoldHides(container, el) {
        const body = container.querySelector(
            ':scope > .lrd-sec-body, :scope > .panel-content');
        return !!(body && body.contains(el));
    }

    _setSectionCollapsed(container, collapsed) {
        container.classList.toggle('lrd-sec-collapsed', collapsed);
        const btn = container.querySelector(
            ':scope > .panel-header .lrd-sec-arrow, '
            + ':scope > .lrd-sec-head .lrd-sec-arrow');
        if (btn) {
            btn.setAttribute('aria-expanded', String(!collapsed));
            btn.title = collapsed ? 'Expand section' : 'Collapse section';
        }
        const id = container.dataset.lrdSecId;
        if (id) {
            try {
                localStorage.setItem(`ledRasterPanelCollapsed_${id}`,
                                     collapsed ? '1' : '0');
            } catch (_) { /* storage full/blocked: state just won't persist */ }
        }
    }

    /**
     * Expand every collapsed section above `el`, persisting the expansion.
     * The focus-restore rule: a field the app is programmatically focusing
     * (after a rebuild, or from a test driving the editors) must be visible,
     * so the section it lives in opens rather than swallowing the focus.
     */
    _expandSectionsFor(el) {
        for (let n = el && el.parentElement; n; n = n.parentElement) {
            if (!n.classList) continue;
            // A field that lives inside a closed tile is the same case one
            // register down: the restore is about to focus it, so the tile
            // opens - and records the opening, or the next rebuild would
            // close the editor around the caret.
            if (n.classList.contains('lrd-tile')
                    && !n.classList.contains('lrd-tile-open')) {
                this._setTileOpen(n, true);
            }
            // Only a fold that actually HIDES the field: the fold hides the
            // section's body, and a control on its header (the dock's ≡,
            // a name box) or on a strip that rides outside the fold (a
            // distro's LEGS line, a box's cable sheet) is visible folded.
            // Unfolding for those rewrote the user's fold on every
            // rebuild that restored focus into a header control.
            if (n.classList.contains('lrd-sec-collapsed')
                    && this._sectionFoldHides(n, el)) {
                this._setSectionCollapsed(n, false);
            }
            // A backup nested in a redundant pair hides WHOLE when its main
            // folds (the pair is one thing), so a restore aiming inside the
            // backup must open the MAIN - a sibling, which the ancestor
            // walk alone would never touch.
            if (n.classList.contains('lrd-red-pair')) {
                const main = n.firstElementChild;
                if (main && main.classList
                        && main.classList.contains('lrd-sec-collapsed')
                        && !main.contains(el)) {
                    this._setSectionCollapsed(main, false);
                }
            }
            // The dock folds by the SIDEBAR machinery, not the section
            // machinery, and the port chips' editors live inside it - so a
            // restore aiming into a collapsed tray reopens it through its
            // own toggle, which is what persists the state and settles the
            // canvas around the returning height.
            if (n.id === 'hardware-dock'
                    && n.classList.contains('collapsed')) {
                const toggle =
                    document.getElementById('hardware-dock-toggle');
                if (toggle) toggle.click();
            }
        }
    }

    /**
     * Tiles: a port or a multi drawn as one dense cell of a wrapping grid,
     * with its editor folded inside it (style.css .lrd-tile). Clicking the
     * face opens the editor in place; one editor per box at a time, so
     * opening a tile closes whichever neighbour was open.
     *
     * Which tile is open lives HERE (`_openTiles`, boxId -> tileId), never
     * in the DOM: both panels that draw tiles rebuild wholesale on every
     * resolution, and the open editor has to come back by id through the
     * wipe - the same reason the fold state lives off the markup. In memory
     * only, on purpose: an editor is a gesture, not a preference, so unlike
     * the fold it does not outlive the page.
     */
    _tileOpenId(boxId) {
        return (this._openTiles || {})[boxId] || null;
    }

    _setTileOpen(tile, open, focusFace) {
        if (!tile) return;
        const boxId = tile.dataset.lrdTileBox || '';
        const id = tile.dataset.lrdTile || '';
        if (!this._openTiles) this._openTiles = {};
        if (open) {
            const prev = this._openTiles[boxId];
            if (prev && prev !== id) {
                // the box's other open tile closes as this one opens
                const el = document.querySelector(
                    `[data-lrd-tile="${prev}"]`);
                if (el) {
                    el.classList.remove('lrd-tile-open');
                    const f = el.querySelector(':scope > .lrd-tile-face');
                    if (f) f.setAttribute('aria-expanded', 'false');
                }
            }
            this._openTiles[boxId] = id;
        } else if (this._openTiles[boxId] === id) {
            delete this._openTiles[boxId];
        }
        tile.classList.toggle('lrd-tile-open', open);
        // Opening grows the tile, and in a scrolling host (the dock's body
        // caps its height) the editor can land partly outside the visible
        // area - open half-off-screen, with the face no longer clickable
        // where the eye left it. Nearest-edge scrolling keeps the opened
        // tile in view and is a no-op when it already is.
        if (open && tile.scrollIntoView) {
            tile.scrollIntoView({ block: 'nearest' });
        }
        const face = tile.querySelector(':scope > .lrd-tile-face');
        if (face) {
            face.setAttribute('aria-expanded', String(open));
            // Closing from inside the editor would otherwise drop focus into
            // a field that just went display:none - the tile is the stop the
            // gesture came from, so it is where focus goes back to.
            if (!open && focusFace) face.focus();
        }
    }

    _wireTiles(scope) {
        scope.querySelectorAll('.lrd-tile').forEach(tile => {
            if (tile.dataset.lrdTileWired) return;
            const face = tile.querySelector(':scope > .lrd-tile-face');
            if (!face) return;
            // A tile with no editor folded inside it (a FREE circuit chip -
            // there is no override to edit until a circuit holds the tail)
            // is a plain drag handle: wiring it would make its face toggle
            // an empty body open and closed.
            if (!tile.querySelector(':scope > .lrd-tile-body')) return;
            tile.dataset.lrdTileWired = '1';
            // The face is a real tab stop: the old rows were keyboard-
            // reachable through their inputs, and a tile whose fields are
            // hidden until opened would otherwise take that access away.
            // Enter/Space open it, Escape anywhere in the tile closes it.
            face.tabIndex = 0;
            face.setAttribute('role', 'button');
            face.setAttribute('aria-expanded',
                              String(tile.classList.contains('lrd-tile-open')));
            const toggle = () => this._setTileOpen(
                tile, !tile.classList.contains('lrd-tile-open'), true);
            face.addEventListener('click', toggle);
            face.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggle();
                }
            });
            tile.addEventListener('keydown', (e) => {
                if (e.key === 'Escape'
                        && tile.classList.contains('lrd-tile-open')) {
                    e.stopPropagation();
                    this._setTileOpen(tile, false, true);
                }
            });
        });
    }

    /**
     * Re-pin every sidebar toggle and re-size the canvas backing store to the
     * wrapper it now has.
     *
     * The canvas is sized in setupCanvas() from wrapper.clientWidth/Height,
     * and its only automatic trigger is the window resize listener - so a
     * panel that changed width without the window changing leaves the canvas
     * painting at its old pixel size, with a black strip where the panel used
     * to be. Cheap enough to call on every frame of a drag.
     */
    remeasureCanvas() {
        (this._sidebarPositioners || []).forEach(fn => {
            try { fn(); } catch (_) { /* a panel may not be in the DOM */ }
        });
        const renderer = window.canvasRenderer;
        if (!renderer) return;
        // setupCanvas() renders as its last step, so this is one paint.
        if (renderer.setupCanvas) renderer.setupCanvas();
        else if (renderer.render) renderer.render();
    }

    /**
     * One layout change, three re-measures. The panels' width transition runs
     * ~180ms, so measuring once measures the wrong frame - the canvas would
     * settle at whatever width it happened to have mid-animation.
     *
     * Collapse, view switching (updateViewSidebars) and the end of a
     * drag-resize (theme.js, through window.app) all land here, so there is
     * one mechanism for this rather than one per caller. A live drag suppresses
     * the transition and calls remeasureCanvas() directly instead.
     */
    settleLayout() {
        const settle = () => this.remeasureCanvas();
        requestAnimationFrame(settle);
        setTimeout(settle, 60);
        setTimeout(settle, 220);
    }

    /**
     * The hardware dock belongs to the two hardware views and nowhere else:
     * processors and ports describe how signal reaches the cabinets, distros
     * and multis how power does, and neither means anything in Pixel Map,
     * Cabinet ID or Show Look - so the tray and its toggle leave layout
     * completely everywhere else (.view-hidden is display:none, not a
     * collapse). That is the whole reason a user who only ever opens Pixel
     * Map sees nothing new. The Signal and Power middle sidebars used to be
     * two more rows of this table; they retired when the dock absorbed the
     * hardware surfaces, and the canvas got their width back.
     *
     * The table shape stays (one row per view-scoped panel, the same shape
     * as the collapse and resize tables in initSidebarToggles above and
     * theme.js's PANELS): a future view-scoped panel is a row here rather
     * than a near-copy of this function.
     *
     * Collapsed state is untouched here: collapsing the tray and then
     * leaving its views must not silently re-expand it on the way back.
     */
    updateViewSidebars(mode) {
        const panels = [
            { sidebarId: 'hardware-dock', toggleId: 'hardware-dock-toggle', modes: ['data-flow', 'power'] },
        ];
        let touched = false;
        panels.forEach(({ sidebarId, toggleId, modes }) => {
            const sidebar = document.getElementById(sidebarId);
            if (!sidebar) return;
            touched = true;
            const btn = toggleId ? document.getElementById(toggleId) : null;
            const visible = modes.includes(mode);
            sidebar.classList.toggle('view-hidden', !visible);
            if (btn) btn.classList.toggle('view-hidden', !visible);
        });
        // The dock's CONTENT is per-view too - processors in Data, distros
        // in Power - so entering either view redraws it for that view.
        if (typeof this.renderHardwareDock === 'function') {
            try { this.renderHardwareDock(); } catch (_) {}
        }
        if (!touched) return;
        // A whole flex column appearing or disappearing changes the width the
        // canvas has to fill, and moves every toggle - and the dock changes
        // the HEIGHT the canvas has to fill the same way.
        this.settleLayout();
    }

    // Check if server has restarted - if so, clear localStorage
    // Also fetch server-side preferences so all clients share the same config
    async checkServerSession() {
        try {
            const response = await fetch('/api/server-session');
            const data = await response.json();
            const savedSessionId = localStorage.getItem('ledRasterServerSession');

            if (savedSessionId !== data.session_id) {
                // Server has restarted - clear all localStorage and use defaults
                console.log('Server restarted - clearing localStorage and using defaults');
                localStorage.removeItem('ledRasterSize');
                localStorage.removeItem('ledRasterClientProps');
                localStorage.removeItem('ledRasterPropsVersion');
                localStorage.setItem('ledRasterServerSession', data.session_id);
                // Apply preferences-based raster size after reset
                this.loadRasterSize();
            } else {
                // Same server session - load from localStorage
                console.log('Same server session - loading from localStorage');
                this.loadRasterSize();
            }
        } catch (e) {
            console.error('Error checking server session:', e);
            // On error, just load from localStorage
            this.loadRasterSize();
        }

        // Fetch server-side preferences (shared across all clients)
        try {
            const prefResp = await fetch('/api/preferences');
            const serverPrefs = await prefResp.json();
            if (serverPrefs && Object.keys(serverPrefs).length > 0) {
                // Server has preferences, use them (overrides localStorage)
                this._serverPreferences = serverPrefs;
                console.log('Loaded server-side preferences:', Object.keys(serverPrefs));
            } else {
                // No server prefs yet, seed from localStorage if available
                const localPrefs = this.getLocalPreferences();
                if (Object.keys(localPrefs).length > 0) {
                    this._serverPreferences = localPrefs;
                    // Push local prefs to server so other clients pick them up
                    fetch('/api/preferences', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(localPrefs)
                    });
                    console.log('Seeded server preferences from localStorage');
                }
            }
        } catch (e) {
            console.error('Error fetching server preferences:', e);
        }
    }
    
    connectWebSocket() {
        this.socket = io();
        this.socket.on('connect', () => {
            document.getElementById('status-message').textContent = 'Connected';
            sendClientLog('socket_connect');
        });
        this.socket.on('disconnect', () => {
            document.getElementById('status-message').textContent = 'Disconnected';
            sendClientLog('socket_disconnect');
        });
        this.socket.on('project_data', (data) => {
            console.log('WEBSOCKET project_data received');
            sendClientLog('socket_project_data', { layers: data.layers ? data.layers.length : 0 });
            
            // Preserve client-side properties when server sends project data
            const savedClientProps = {};
            if (this.project && this.project.layers) {
                this.project.layers.forEach(layer => {
                    savedClientProps[layer.id] = this.extractClientSideProps(layer);
                });
            }
            
            // On reconnect, preserve the current raster size (it may have been
            // set by preferences or user action). Only apply the server's raster
            // on cold start when no preference override will follow.
            // Capture BOTH the Pixel Map raster and the Show Look raster
            // explicitly (not the view-dependent getter) so a stale connect-time
            // echo can't revert the Show Look raster while leaving Pixel Map's
            // intact, the asymmetry that left Show Look at 1080p.
            const preserveRaster = this._initialLoadComplete;
            const prevRasterW = preserveRaster ? window.canvasRenderer.pixelRasterWidth : null;
            const prevRasterH = preserveRaster ? window.canvasRenderer.pixelRasterHeight : null;
            const prevShowW = preserveRaster ? window.canvasRenderer.showRasterWidth : null;
            const prevShowH = preserveRaster ? window.canvasRenderer.showRasterHeight : null;

            this.project = data;
            this.dedupeProjectLayers('socket_project_data');
            if (data && data.raster_width && data.raster_height) {
                this.syncRasterFromProject();
                this.saveRasterSize();
            }

            // On reconnect, restore the raster size we had before the server
            // overwrote it with its default, both the Pixel Map raster and the
            // Show Look raster, so neither reverts.
            if (preserveRaster && prevRasterW && prevRasterH) {
                this.project.raster_width = prevRasterW;
                this.project.raster_height = prevRasterH;
                window.canvasRenderer.pixelRasterWidth = prevRasterW;
                window.canvasRenderer.pixelRasterHeight = prevRasterH;
                if (prevShowW && prevShowH) {
                    this.project.show_raster_width = prevShowW;
                    this.project.show_raster_height = prevShowH;
                    window.canvasRenderer.showRasterWidth = prevShowW;
                    window.canvasRenderer.showRasterHeight = prevShowH;
                }
                const rw = document.getElementById('toolbar-raster-width');
                const rh = document.getElementById('toolbar-raster-height');
                if (rw) rw.value = window.canvasRenderer.rasterWidth;
                if (rh) rh.value = window.canvasRenderer.rasterHeight;
            }

            // Restore client-side properties and layer defaults.
            // On reconnect (after sleep), skip preference enforcement, the project
            // already has the correct state from before the disconnect.
            this.loadClientSideProperties({ skipPreferences: this._initialLoadComplete });
            
            // Also restore any in-memory props we had
            if (this.project && this.project.layers) {
                this.project.layers.forEach(layer => {
                    const memProps = savedClientProps[layer.id];
                    if (memProps) {
                        // Only apply if the value was actually set (not undefined)
                        Object.keys(memProps).forEach(key => {
                            if (memProps[key] !== undefined) {
                                layer[key] = memProps[key];
                            }
                        });
                    }
                });
            }
            
            // Re-select current layer to sync currentLayer reference
            if (this.currentLayer) {
                const layerId = this.currentLayer.id;
                const updatedLayer = this.project.layers.find(l => l.id === layerId);
                if (updatedLayer) {
                    this.currentLayer = updatedLayer;
                }
            }
            
            this.updateUI();
        });
        this.socket.on('layer_updated', (layer) => {
            console.log('WEBSOCKET layer_updated received for layer:', layer.id);
            // Undo audit: while an undo/redo restore PUT is on its way to the
            // server, a layer_updated broadcast describes the PRE-restore
            // server state (typically the very edit being undone - e.g. the
            // just-committed drag's offsets). Applying it re-imposed the
            // undone edit on the restored client project; the restore PUT's
            // own adopted response is the reconciliation for this window.
            if (this._restorePutPending) {
                sendClientLog('socket_layer_updated_suppressed_during_restore',
                              { id: layer.id });
                return;
            }
            sendClientLog('socket_layer_updated', { id: layer.id });
            this.applyServerLayer(layer, 'socket_layer_updated');
            this.updateUI();
        });
        this.socket.on('preferences_updated', (prefs) => {
            console.log('WEBSOCKET preferences_updated received');
            this._serverPreferences = prefs;
        });
    }

    // Extract client-side only properties from a layer.
    //
    // v0.11.0: `group_id` does NOT belong here, for the same reason
    // `canvas_id` / `show_canvas_id` never have. This list (and its twin in
    // saveClientSideProperties / loadClientSideProperties) exists for fields
    // the SERVER does not round-trip, which are then re-applied on top of a
    // server payload and cached in localStorage keyed by layer id. group_id
    // is server-owned and whitelisted on PUT /api/layer/<id>, so it already
    // survives every round trip; adding it would let a stale membership from
    // a previous project be re-stamped onto a same-numbered layer.
    extractClientSideProps(layer) {
        return {
            dataFlowColor: layer.dataFlowColor,
            arrowColor: layer.arrowColor,
            dataFlowLabelSize: layer.dataFlowLabelSize,
            arrowLineWidth: layer.arrowLineWidth,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            randomDataColors: layer.randomDataColors,
            flowPattern: layer.flowPattern,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate,
            processorType: layer.processorType,
            lowLatency: layer.lowLatency,
            portMappingMode: layer.portMappingMode,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
            portLabelOverridesReturn: layer.portLabelOverridesReturn,
            customPortPaths: layer.customPortPaths,
            customPortIndex: layer.customPortIndex,
            customPortOverrides: layer.customPortOverrides,
            screenNameSizeCabinet: layer.screenNameSizeCabinet,
            screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
            screenNameSizePower: layer.screenNameSizePower,
            screenNameOffsetXPixelMap: layer.screenNameOffsetXPixelMap,
            screenNameOffsetYPixelMap: layer.screenNameOffsetYPixelMap,
            screenNameOffsetXCabinet: layer.screenNameOffsetXCabinet,
            screenNameOffsetYCabinet: layer.screenNameOffsetYCabinet,
            screenNameOffsetXDataFlow: layer.screenNameOffsetXDataFlow,
            screenNameOffsetYDataFlow: layer.screenNameOffsetYDataFlow,
            screenNameOffsetXPower: layer.screenNameOffsetXPower,
            screenNameOffsetYPower: layer.screenNameOffsetYPower,
            screenNameOffsetXShowLook: layer.screenNameOffsetXShowLook,
            screenNameOffsetYShowLook: layer.screenNameOffsetYShowLook,
            gradientEnabled: layer.gradientEnabled,
            transparentFill: layer.transparentFill,
            rotation: layer.rotation,
            gradientType: layer.gradientType,
            gradientScope: layer.gradientScope,
            gradientPanelAlternate: layer.gradientPanelAlternate,
            gradientRadialCenterX: layer.gradientRadialCenterX,
            gradientRadialCenterY: layer.gradientRadialCenterY,
            gradientRadialRadius: layer.gradientRadialRadius,
            gradientAngle: layer.gradientAngle,
            gradientOpacity: layer.gradientOpacity,
            gradientBlend: layer.gradientBlend,
            gradientStops: layer.gradientStops,
            panelColorMode: layer.panelColorMode,
            panelColors: layer.panelColors,
            showDataFlowPortInfo: layer.showDataFlowPortInfo,
            showDataFlowPortLoad: layer.showDataFlowPortLoad,
            showPowerCircuitInfo: layer.showPowerCircuitInfo,
            showPowerNferTags: layer.showPowerNferTags,
            showPowerCableTags: layer.showPowerCableTags,
            showDataCableTags: layer.showDataCableTags,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerAmperage: layer.powerAmperage,
            powerAmperageCustom: layer.powerAmperageCustom,
            panelWatts: layer.panelWatts,
            powerMaximize: layer.powerMaximize,
            powerOrganized: layer.powerOrganized,
            powerCustomPath: layer.powerCustomPath,
            powerFlowPattern: layer.powerFlowPattern,
            powerLineWidth: layer.powerLineWidth,
            powerLineColor: layer.powerLineColor,
            powerArrowColor: layer.powerArrowColor,
            powerRandomColors: layer.powerRandomColors,
            powerColorCodedView: layer.powerColorCodedView,
            powerCircuitColors: layer.powerCircuitColors,
            powerLabelSize: layer.powerLabelSize,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: layer.powerLabelOverrides,
            powerCircuitCables: layer.powerCircuitCables,
            powerCustomPaths: layer.powerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            powerCustomOverrides: layer.powerCustomOverrides,
            powerSplitters: layer.powerSplitters,
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            weight_unit: layer.weight_unit,
            panel_weight: layer.panel_weight,
            infoLabelSize: layer.infoLabelSize,
            // Text layer properties
            textContent: layer.textContent,
            textContentPixelMap: layer.textContentPixelMap,
            textContentCabinetId: layer.textContentCabinetId,
            textContentShowLook: layer.textContentShowLook,
            textContentDataFlow: layer.textContentDataFlow,
            textContentPower: layer.textContentPower,
            textContentOverridePixelMap: layer.textContentOverridePixelMap,
            textContentOverrideCabinetId: layer.textContentOverrideCabinetId,
            textContentOverrideShowLook: layer.textContentOverrideShowLook,
            textContentOverrideDataFlow: layer.textContentOverrideDataFlow,
            textContentOverridePower: layer.textContentOverridePower,
            textWidth: layer.textWidth,
            textHeight: layer.textHeight,
            fontSize: layer.fontSize,
            fontFamily: layer.fontFamily,
            fontColor: layer.fontColor,
            bgColor: layer.bgColor,
            bgOpacity: layer.bgOpacity,
            textAlign: layer.textAlign,
            textPadding: layer.textPadding,
            showBorder: layer.showBorder,
            borderColor: layer.borderColor,
            showOnPixelMap: layer.showOnPixelMap,
            showOnCabinetId: layer.showOnCabinetId,
            showOnShowLook: layer.showOnShowLook,
            showOnDataFlow: layer.showOnDataFlow,
            showOnPower: layer.showOnPower,
            showRasterSize: layer.showRasterSize,
            showProjectName: layer.showProjectName,
            showDate: layer.showDate,
            showPrimaryPorts: layer.showPrimaryPorts,
            showBackupPorts: layer.showBackupPorts,
            showCircuits: layer.showCircuits,
            showSinglePhase: layer.showSinglePhase,
            showThreePhase: layer.showThreePhase,
            fontBold: layer.fontBold,
            fontItalic: layer.fontItalic,
            fontUnderline: layer.fontUnderline,
            // Image layer Drop Shadow. The server does store these now, but a
            // socket echo of a layer that was PUT before the shadow edit would
            // otherwise land on top of it and un-shadow the layer for a frame.
            imageShadowEnabled: layer.imageShadowEnabled,
            imageShadowColor: layer.imageShadowColor,
            imageShadowOpacity: layer.imageShadowOpacity,
            imageShadowAngle: layer.imageShadowAngle,
            imageShadowDistance: layer.imageShadowDistance,
            imageShadowSpread: layer.imageShadowSpread,
            imageShadowSize: layer.imageShadowSize,
            // Image layer opacity: same echo race as the shadow block.
            imageOpacity: layer.imageOpacity
        };
    }

    // v0.10.8: merge a server-sent layer into this.project, preserving the
    // client-side-only props the server never round-trips. Shared by the
    // socket `layer_updated` handler and by fetch callers whose response
    // carries the rebuilt layer, so both paths merge identically. Returns
    // false when there is nothing to apply (no layer / no project yet).
    applyServerLayer(layer, reason = 'apply_server_layer') {
        if (!layer || !this.project || !this.project.layers) return false;
        const index = this.project.layers.findIndex(l => l.id === layer.id);
        if (index >= 0) {
            // Preserve client-side properties when server sends layer update
            const clientProps = this.extractClientSideProps(this.project.layers[index]);
            this.project.layers[index] = layer;

            // Restore client props
            Object.keys(clientProps).forEach(key => {
                if (clientProps[key] !== undefined) {
                    this.project.layers[index][key] = clientProps[key];
                }
            });

            if (this.currentLayer && this.currentLayer.id === layer.id) {
                this.currentLayer = this.project.layers[index];
            }
            this.dedupeProjectLayers(reason);
        } else {
            this.upsertProjectLayer(layer);
            this.dedupeProjectLayers(`${reason}_upsert`);
        }
        return true;
    }

    loadProject() {
        fetch('/api/project')
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('load_project');
                if (data && data.raster_width && data.raster_height) {
                    this.syncRasterFromProject();
                    this.saveRasterSize();
                }
                sendClientLog('load_project', { name: data.name, layers: data.layers ? data.layers.length : 0 });
                
                // Load client-side properties from localStorage
                const breakoutBefore = new Map((this.project.layers || [])
                    .map(l => [l.id, l.powerBreakoutType]));
                this.loadClientSideProperties();
                // The breakout the load pass wrote (normalizePowerBreakout
                // in the defaults sweep above) is paperwork the server has
                // to hold too, or the next project re-fetch - a delete, a
                // reconnect - hands back the screen without it. PUT exactly
                // the screens whose breakout changed, nothing else, and
                // without a history entry (nothing the user did).
                const breakoutRewrote = (this.project.layers || []).filter(
                    l => (l.type || 'screen') === 'screen'
                        && l.powerBreakoutType !== breakoutBefore.get(l.id));
                if (breakoutRewrote.length) this.updateLayers(breakoutRewrote);
                
                // Auto-select first layer BEFORE updateUI so render has correct data
                if (this.project.layers && this.project.layers.length > 0) {
                    this.selectLayer(this.project.layers[0]);
                    // Never force-apply defaults to arbitrary loaded projects.
                    // Only apply to true startup default project when criteria match.
                    this.applyPreferencesToDefaultLayerIfMatch(false);
                }
                
                // Save initial state for undo/redo
                this.resetHistory('Initial State');

                // Mark initial load complete, subsequent socket project_data
                // events are reconnects and should not re-apply preferences.
                this._initialLoadComplete = true;

                // Default to Fit view on load. Retry while layout settles: on
                // a slow first paint the canvas wrapper can still be 0-height
                // at +100ms, which computes zoom 0 and leaves the canvas blank
                // until the user manually hits Fit.
                const initialFit = (attempt = 0) => {
                    window.canvasRenderer.setupCanvas();
                    window.canvasRenderer.fitToView();
                    if (!window.canvasRenderer.zoom && attempt < 8) {
                        setTimeout(() => initialFit(attempt + 1), 250);
                    }
                };
                setTimeout(() => initialFit(), 100);
            });
    }
    
    // v0.11.0: 'brompton-ull' used to be its own processor entry holding the
    // Brompton table halved. It is now Brompton + Low Latency, which produces
    // the same numbers from one table. Old files and old presets keep the old
    // value forever, so every load path runs this. Returns true if it changed
    // the layer.
    migrateLowLatencyProcessor(layer) {
        if (!layer || layer.processorType !== 'brompton-ull') return false;
        layer.processorType = 'brompton';
        layer.lowLatency = true;
        return true;
    }

    // v0.11.0 (step 6): a cross-member path entry ({row, col, layerId}) is only
    // meaningful while the layer it names is still a reachable peer of the
    // owner. Three things restore paths without any guarantee of that:
    // localStorage client props (keyed by layer id, so a project with the same
    // ids gets another project's wiring stamped on it), File > Open, and
    // Recent Files. On top of that a group can be dissolved, or a member moved
    // to another canvas, between the save and the load.
    //
    // The server prunes the same entries inside _enforce_group_integrity on
    // every restore, so this pass does not have to be exhaustive - it exists so
    // the canvas does not draw a port reaching into an unrelated screen in the
    // window BEFORE the first sync comes back.
    //
    // Entries with no layerId - every path in every pre-step-6 project - are
    // not touched, not even rewritten, so a project with no cross-member paths
    // comes out of here byte-for-byte as it went in. Returns the number of
    // entries dropped.
    sanitizeCrossLayerPaths(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return 0;
        // A group commit is mid-flight: the client's copy is half-written and
        // the repaired project is already on its way back. Judging wiring
        // against a project in that state is exactly how the same sequence of
        // actions produced two different outcomes depending on timing.
        if (this._groupCommitDepth > 0) return 0;
        const layers = (this.project && this.project.layers) || [];
        // THE SERVER'S RULE, deliberately - _prune_cross_layer_paths in app.py:
        // a step is legal while it names a layer that exists and sits in the
        // SAME GROUP as the owner. It is not canPathReachLayer's rule, which
        // additionally requires the same canvas: that is a DRAWABILITY test
        // (the renderer must not paint a cable into another workspace) and it
        // is right for the renderer, but a destructive pass that used it
        // deleted wiring the server had kept, so whether a wall survived
        // "move a member to canvas 2, save, reopen" came down to which pass
        // ran first. The renderer still refuses to draw those steps; this one
        // no longer throws them away.
        const groupIdOf = (l) => {
            if (!l || !l.group_id) return null;
            if (typeof this.resolveGroup === 'function') {
                return this.resolveGroup(l.group_id) ? l.group_id : null;
            }
            return l.group_id;
        };
        const ownGroup = groupIdOf(layer);
        let dropped = 0;
        ['customPortPaths', 'powerCustomPaths'].forEach(key => {
            const paths = layer[key];
            if (!paths || typeof paths !== 'object') return;
            Object.keys(paths).forEach(pathKey => {
                const path = paths[pathKey];
                if (!Array.isArray(path)) return;
                const kept = path.filter(entry => {
                    if (!entry || typeof entry !== 'object') return true;
                    if (entry.layerId === undefined || entry.layerId === null) return true;
                    if (entry.layerId === layer.id) {
                        // "this layer", written the long way. Normalise it to
                        // the plain form the renderers fast-path on.
                        delete entry.layerId;
                        return true;
                    }
                    if (!ownGroup) return false;   // owner is not in a group at all
                    const target = layers.find(l => l && l.id === entry.layerId);
                    if (!target || groupIdOf(target) !== ownGroup) return false;
                    // A cross-layer step with no cell to land on is a
                    // truncated or hand-edited file; the server drops it too.
                    return entry.row !== undefined && entry.row !== null
                        && entry.col !== undefined && entry.col !== null;
                });
                if (kept.length === path.length) return;
                dropped += path.length - kept.length;
                // An emptied path loses its key: a port listed with an empty
                // path reads as hand-routed with nothing drawn.
                if (kept.length === 0) delete paths[pathKey];
                else paths[pathKey] = kept;
            });
        });
        if (dropped > 0) {
            sendClientLog('cross_layer_paths_pruned', {
                layerId: layer.id, layerName: layer.name, entries: dropped,
            });
        }
        return dropped;
    }

    // Run the pass above over every layer, and answer how many entries went.
    //
    // POST /api/project (saveProject) is a straight dict update on the server:
    // no _enforce_group_integrity, no _prune_cross_layer_paths. Whatever the
    // client sends through it BECOMES the canonical project, so a client
    // holding a step the server already pruned would put it straight back -
    // onto layers that are no longer grouped. Callers that save through that
    // route run this first: it applies the server's own rule, so it can only
    // remove what the server would have removed anyway.
    //
    // A project with no cross-member wiring - every project written before
    // v0.11.0 - comes out of here untouched, not even rewritten.
    pruneStaleCrossLayerPaths() {
        const layers = (this.project && this.project.layers) || [];
        let dropped = 0;
        layers.forEach(layer => { dropped += this.sanitizeCrossLayerPaths(layer); });
        return dropped;
    }

    createNewProject() {
        this.resetApplicationState();
        fetch('/api/project/new', {
            method: 'POST'
        })
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('new_project');
                this.syncRasterFromProject();
                sendClientLog('new_project');
                this.updateUI();

                // Auto-select first layer if available
                if (this.project.layers && this.project.layers.length > 0) {
                    this.selectLayer(this.project.layers[0]);
                    const prefs = this.getPreferences();
                    this.applyPreferencesToCurrentLayer(prefs);
                } else {
                    this.currentLayer = null;
                }

                // Reset raster dimensions to defaults. Both the Pixel Map and
                // Show Look rasters start at the preference size so a new
                // project's Show Look matches (not the server's 1080p default).
                const prefs = this.getPreferences();
                window.canvasRenderer.pixelRasterWidth = prefs.rasterWidth;
                window.canvasRenderer.pixelRasterHeight = prefs.rasterHeight;
                window.canvasRenderer.showRasterWidth = prefs.rasterWidth;
                window.canvasRenderer.showRasterHeight = prefs.rasterHeight;
                document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
                document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;

                // Undo audit: resetApplicationState() above snapshotted the
                // OLD project (it runs before the fetch), so the first Ctrl+Z
                // in the new project restored - and PUT back - the project the
                // user had just left. Reset again now that this.project IS the
                // new project, the same post-load reset File > Open and Recent
                // Files perform.
                this.resetHistory('Initial State');

                // Save the default raster size to localStorage
                // This way refresh after "New" will show defaults
                this.saveRasterSize();
                // Persist both rasters to the server so the Show Look raster
                // doesn't snap back to the default on the next project echo.
                // `keep_pristine`: this is the page's own sync, not a user
                // save - the new project stays pristine on the server, so
                // its startup screen follows Preferences until a hand
                // touches it (same marker as the load-time sync in
                // loadClientSideProperties). The build's version rides
                // along and is mirrored here so the first undo snapshot
                // carries it (see appVersion).
                this.project.app_version = this.appVersion();
                fetch('/api/project', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        raster_width: prefs.rasterWidth,
                        raster_height: prefs.rasterHeight,
                        show_raster_width: prefs.rasterWidth,
                        show_raster_height: prefs.rasterHeight,
                        app_version: this.project.app_version,
                        keep_pristine: true
                    })
                });

                // Fit to view
                setTimeout(() => {
                    window.canvasRenderer.fitToView();
                }, 100);
            });
    }

    applyPreferencesToCurrentLayer(prefs) {
        if (!this.currentLayer) return;
        this.currentLayer.columns = prefs.columns;
        this.currentLayer.rows = prefs.rows;
        this.currentLayer.cabinet_width = prefs.panelWidth;
        this.currentLayer.cabinet_height = prefs.panelHeight;
        this.currentLayer.panel_width_mm = prefs.panelWidthMM;
        this.currentLayer.panel_height_mm = prefs.panelHeightMM;
        this.currentLayer.panel_weight = prefs.panelWeight;
        this.currentLayer.weight_unit = prefs.weightUnit || 'kg';
        this.currentLayer.number_size = prefs.cabinetFontSize;
        this.currentLayer.labelsFontSize = prefs.labelFontSize;
        // The screen name on the other tabs uses the same default size as the
        // Pixel Map label font size, so the name is consistent across tabs.
        this.currentLayer.screenNameSizeCabinet = prefs.labelFontSize;
        this.currentLayer.screenNameSizeDataFlow = prefs.labelFontSize;
        this.currentLayer.screenNameSizePower = prefs.labelFontSize;
        // The tile colours the same way the new colours below are checked:
        // a stored '#FFF' expands, '' or 'abc' falls back to the shipped
        // literal (hexToRgb('#FFF') read as red; '' landed on the server).
        const tile = (value, fallback) => this.normalizeTileColor(value, fallback);
        this.currentLayer.color1 = this.hexToRgb(tile(prefs.color1, '#404680'));
        this.currentLayer.color2 = this.hexToRgb(tile(prefs.color2, '#959CB8'));
        const borderColor = tile(prefs.borderColor, '#FFFFFF');
        this.currentLayer.border_color = borderColor;
        this.currentLayer.border_color_pixel = borderColor;
        this.currentLayer.border_color_cabinet = borderColor;
        this.currentLayer.border_color_data = borderColor;
        this.currentLayer.border_color_power = borderColor;
        this.currentLayer.flowPattern = prefs.flowPattern;
        this.currentLayer.arrowLineWidth = prefs.dataLineWidth;
        this.currentLayer.dataFlowLabelSize = prefs.dataLabelSize;
        this.currentLayer.powerLineWidth = prefs.powerLineWidth;
        this.currentLayer.powerLabelSize = prefs.powerLabelSize;
        // The pristine startup screen is, in effect, a new screen: it takes
        // every colour default the Preferences dialog holds (the same set
        // initializeLayerDefaults and addLayer give a screen that is added),
        // not only the tile colours. The literal behind each is what shipped
        // before the preference existed, for a stored value that is not a
        // colour. The circuit colours are the preference's A to F.
        const color = (value, fallback) => this.normalizeHexColor(value, fallback);
        this.currentLayer.labelsColor = color(prefs.screenNameColor, '#FFFFFF');
        this.currentLayer.cabinetIdColor = color(prefs.cabinetIdColor, '#FFFFFF');
        this.currentLayer.dataFlowColor = color(prefs.dataLineColor, '#FFFFFF');
        this.currentLayer.arrowColor = color(prefs.dataArrowColor, '#0042AA');
        this.currentLayer.primaryColor = color(prefs.dataPrimaryColor, '#00FF00');
        this.currentLayer.primaryTextColor = color(prefs.dataPrimaryTextColor, '#000000');
        this.currentLayer.backupColor = color(prefs.dataBackupColor, '#FF0000');
        this.currentLayer.backupTextColor = color(prefs.dataBackupTextColor, '#FFFFFF');
        this.currentLayer.powerLineColor = color(prefs.powerLineColor, '#FF0000');
        this.currentLayer.powerArrowColor = color(prefs.powerArrowColor, '#0042AA');
        this.currentLayer.powerLabelBgColor = color(prefs.powerLabelBgColor, '#D95000');
        this.currentLayer.powerLabelTextColor = color(prefs.powerLabelTextColor, '#000000');
        const circuits = this.getPreferenceCircuitColorList(prefs);
        this.currentLayer.powerCircuitColors = {
            A: circuits[0], B: circuits[1], C: circuits[2],
            D: circuits[3], E: circuits[4], F: circuits[5]
        };
        this.currentLayer.processorType = prefs.processorType;
        this.currentLayer.lowLatency = !!prefs.lowLatency;
        this.currentLayer.bitDepth = prefs.bitDepth;
        this.currentLayer.frameRate = prefs.frameRate;
        this.currentLayer.powerVoltage = prefs.powerVoltage;
        this.currentLayer.powerVoltageCustom = prefs.powerVoltage;
        this.normalizePowerBreakout(this.currentLayer);   // the breakout follows the voltage just written (2026-09-22)
        this.currentLayer.powerAmperage = prefs.powerAmperage;
        this.currentLayer.powerAmperageCustom = prefs.powerAmperage;
        this.currentLayer.panelWatts = prefs.powerWatts;
        this.currentLayer.powerFlowPattern = prefs.powerFlowPattern || 'tl-h';
        this.loadLayerToInputs();
        // This PUT is the preference Save re-making the pristine startup
        // screen, not a hand on it: it must not end the pristine state on
        // the server (see _layerPutIsAnEdit), or the screen would stop
        // following Preferences after the next relaunch.
        this._pristinePreferencePut = true;
        try {
            this.updateLayer();
        } finally {
            this._pristinePreferencePut = false;
        }
    }

    // Does a layer PUT made right now count as the USER editing the screen?
    // The answer rides every PUT updateLayer / updateLayers makes as
    // `edited`, and the server ends the project's pristine state only on
    // a PUT that says true (routes_layers update_layer). No while the page
    // is still booting - the load pass writes back what it normalized (a
    // breakout the server lacked) before _initialLoadComplete is set, and
    // nobody has touched anything - and no for the Preferences dialog's
    // own Save re-making the startup screen (applyPreferencesToCurrentLayer
    // raises _pristinePreferencePut around its PUT). Every other PUT is a
    // hand on the screen: the sidebar's updateLayerFromInputs, a drag, the
    // push after an add (add_layer cleared the flag already).
    _layerPutIsAnEdit() {
        return this._initialLoadComplete === true && !this._pristinePreferencePut;
    }

    shouldApplyStartupPreferences() {
        if (!this.project || !this.project.layers || this.project.layers.length !== 1) return false;
        if (!this.currentLayer) return false;
        if (this.project.is_pristine !== true) return false;
        if (this.project.name !== 'Untitled Project') return false;
        // Pristine on BOTH sides. The flag above is the server's, as the
        // project was last fetched: it starts true on the project the
        // server builds (startup, New Project) and is cleared by a user
        // save or file load (POST / PUT /api/project), by adding or
        // deleting a layer, and by a layer PUT that carries `edited: true`
        // - which updateLayer / updateLayers send for every write made
        // after boot except the preference Save's own (_layerPutIsAnEdit).
        // The page's own writes carry no marker: the raster sync POST on
        // load says `keep_pristine`, and the boot pass's normalization
        // PUTs come before _initialLoadComplete. So the flag survives a
        // relaunch, and the startup screen keeps following Preferences
        // until a hand touches it. (Until 2026-09-22 the raster sync
        // cleared it on every load, so the screen followed only inside
        // the session that made it.)
        // The server never tells this copy when it clears the flag, so the
        // second guard is the client's own: a user edit lands an undo step
        // (startupScreenWasEdited), and the Save then leaves the screen
        // alone even before the next fetch.
        if (this.startupScreenWasEdited()) {
            this.project.is_pristine = false;
            return false;
        }
        return true;
    }

    // Has the user edited the startup screen since it was made? Every
    // user edit lands an undo step (updateLayerFromInputs, a drag, a
    // panel toggle: saveState), and both makers of the startup screen -
    // loadProject and createNewProject - resetHistory to the one 'Initial
    // State' entry AFTER applying the preferences; a preference Save's
    // own PUT (applyPreferencesToCurrentLayer -> updateLayer()) saves no
    // step. So a history longer than that one entry is an edit - undone
    // or not, the way the server's flag stays cleared after an undo. A
    // debounced picker commit still waiting is landed first so it counts.
    startupScreenWasEdited() {
        if (typeof this._flushPendingSaveState === 'function') this._flushPendingSaveState();
        return Array.isArray(this.history) && this.history.length > 1;
    }

    shouldUseSavedClientProps() {
        // Local client props are keyed only by layer id. Restrict use to the
        // untouched startup default project so they don't bleed into loaded files.
        if (!this.project || !this.project.layers || this.project.layers.length !== 1) return false;
        return this.project.name === 'Untitled Project';
    }

    applyPreferencesToDefaultLayerIfMatch(force = false) {
        if (!this.shouldApplyStartupPreferences()) return;
        const prefs = this.getPreferences();
        sendClientLog('apply_preferences_to_default_layer', {
            force: !!force,
            projectName: this.project.name,
            processorType: prefs.processorType,
            bitDepth: prefs.bitDepth,
            frameRate: prefs.frameRate
        });
        this.applyPreferencesToCurrentLayer(prefs);
    }
    
    updateUI() {

        const projectNameEl = document.getElementById('project-name');
        projectNameEl.value = this.project.name;
        // Refresh illegal-character warning whenever the project name changes
        // programmatically (e.g. on project load).
        projectNameEl.dispatchEvent(new Event('input'));
        // Sync the Front/Back perspective toggle buttons to the loaded
        // project's saved values.
        if (this.refreshPerspectiveButtons) this.refreshPerspectiveButtons();
        // Same for the NAMES (Screens / Group / Both) switch, so undo and
        // file open land the buttons on the project's stored choice.
        if (this.refreshNameDisplayButtons) this.refreshNameDisplayButtons();

        // Load project notes
        const notesEl = document.getElementById('project-notes');
        if (notesEl) notesEl.value = this.project.notes || '';

        this.renderLayers();
        this.loadTextLayerToInputs();
        // Slice 10: keep the Totals panels (Data Flow + Power tabs) in sync
        // with whatever just changed. Always cheap, two aggregations over
        // the visible screen layers, plus a handful of textContent writes.
        if (typeof this.refreshTotalsSidebar === 'function') {
            try { this.refreshTotalsSidebar(); } catch (_) {}
        }

        // The processor tree can change under the panel without the panel
        // asking - undo/redo and a file load both replace the whole project -
        // so re-resolve, but only when it actually differs from what was last
        // drawn. Comparing a small blob beats a fetch on every UI update, and
        // a project with no processors compares equal on the first line and
        // never touches the network at all.
        if (typeof this.refreshProcessors === 'function' && this.project) {
            const raw = JSON.stringify(this.project.processors || []);
            if (raw !== this._processorsRaw) this.refreshProcessors();
        }

        // Port assignment follows both sides: the cards it allocates onto and
        // the screens it allocates for. Guarded on there being a processor at
        // all, because working out what to compare means asking every screen
        // how many ports it needs, and getLayerPortsRequired walks the wall to
        // answer. A project with no processors has nothing to assign to, so it
        // never pays for the walk - which is also what keeps it behaving
        // exactly as it did before this panel existed.
        if (typeof this.refreshPortAssignment === 'function' && this.project
                && (this.project.processors || []).length) {
            const raw = this._assignmentKey();
            if (raw !== this._assignmentKeyRaw) this.refreshPortAssignment();
        }

        if (window.canvasRenderer) {
            if (window.canvasRenderer.viewMode === 'data-flow' && this.currentLayer) {
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateCustomFlowUI();
            } else if (window.canvasRenderer.viewMode === 'power' && this.currentLayer) {
                this.updatePowerCapacityDisplay();
                this.updatePowerLabelEditor();
                this.updateCustomPowerUI();
            }
            window.canvasRenderer.render();
        }
    }
    
    setupPixelMapBulkActions() {
        const wireBtn = (id, fn) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('click', () => {
                const panels = this.getPixelMapSelectedPanels();
                if (panels.length === 0) return;
                fn(panels);
            });
        };
        wireBtn('bulk-set-blank',       (panels) => this.setPanelsBlankBulk(panels, true));
        wireBtn('bulk-unset-blank',     (panels) => this.setPanelsBlankBulk(panels, false));
        wireBtn('bulk-set-half-auto',   (panels) => this.setPanelsHalfTileBulk(panels, 'auto'));
        wireBtn('bulk-set-half-width',  (panels) => this.setPanelsHalfTileBulk(panels, 'width'));
        wireBtn('bulk-set-half-height', (panels) => this.setPanelsHalfTileBulk(panels, 'height'));
        wireBtn('bulk-clear-half',      (panels) => this.setPanelsHalfTileBulk(panels, 'none'));

        // Esc clears the pixel-map selection. Only react when no input is focused
        // and the pixel-map view is active.
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const tag = (document.activeElement && document.activeElement.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
            if (window.canvasRenderer && window.canvasRenderer.viewMode === 'pixel-map'
                    && this.pixelMapSelection && this.pixelMapSelection.size > 0) {
                this.clearPixelMapSelection();
                e.preventDefault();
                e.stopPropagation();
            }
        }, true);
    }

    /**
     * Wire the Front / Back perspective toggles in the Data Flow and Power
     * sidebars. Each tab has its own perspective stored on the project
     * (project.data_flow_perspective, project.power_perspective). 'back'
     * horizontally mirrors the wiring view so techs working behind the wall
     * see things from their perspective; labels stay readable (un-mirrored
     * inside the canvas mirror transform during render).
     */
    setupPerspectiveToggles() {
        document.querySelectorAll('.perspective-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.getAttribute('data-target');
                const value = btn.getAttribute('data-perspective');
                if (!target || !value || !this.project) return;
                // v0.8 Slice 8: perspective is per-canvas. Write to the active
                // canvas (which routes through updateCanvas → server PUT, undo
                // entry, and a re-render via _applyProjectUpdate). Mirror
                // project-root field too so legacy code paths keep working
                // until they're all migrated to read from active canvas.
                const active = this._activeCanvas();
                const currentVal = (active && active[target]) || this.project[target] || 'front';
                if (currentVal === value) return;
                this.project[target] = value;
                if (active && typeof this.updateCanvas === 'function') {
                    this.updateCanvas(active.id, { [target]: value });
                } else {
                    this.refreshPerspectiveButtons();
                    this.saveProject();
                    // Undo audit: on a pre-multi-canvas project the history
                    // entry lived only inside updateCanvas, so this branch
                    // mutated and saved with no entry at all.
                    if (typeof this.saveState === 'function') {
                        this.saveState('Change Perspective');
                    }
                    if (window.canvasRenderer) window.canvasRenderer.render();
                }
                if (typeof sendClientLog === 'function') {
                    sendClientLog('perspective_change', {
                        target, value, canvasId: active && active.id
                    });
                }
            });
        });
        this.refreshPerspectiveButtons();
    }

    /**
     * Find the active canvas object, or null. v0.8 Slice 8 helper.
     */
    _activeCanvas() {
        if (!this.project || !Array.isArray(this.project.canvases)) return null;
        const id = this.project.active_canvas_id;
        if (!id) return this.project.canvases[0] || null;
        return this.project.canvases.find(c => c && c.id === id) || null;
    }

    /**
     * v0.8 Slice 9: ids of all canvases whose visibility is explicitly off.
     * Used by aggregate counters (data ports, power totals) to exclude
     * hidden canvases so the numbers in the sidebar match what's drawn.
     */
    _hiddenCanvasIdSet() {
        const set = new Set();
        if (!this.project || !Array.isArray(this.project.canvases)) return set;
        this.project.canvases.forEach(c => {
            if (c && c.visible === false && c.id) set.add(c.id);
        });
        return set;
    }

    /**
     * v0.8 Slice 10: paint the Totals panels on the Data Flow + Power tabs.
     * Two columns each: active canvas + project-wide. Numbers come from
     * getPortCounts/getPowerCounts which already exclude hidden canvases.
     * Cheap to call on every updateUI, the Totals panels are display:none
     * unless the user is on the relevant tab.
     */
    refreshTotalsSidebar() {
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        const fmtAmps = (a) => (a > 0) ? `${a.toFixed(2)} A` : '0';
        const fmtWatts = (w) => (w > 0) ? `${Math.round(w).toLocaleString()} W` : '0';

        // v0.8.7.7.4: list every visible canvas individually instead of a
        // single "active canvas" column. The old active-canvas readout was
        // ambiguous on Data/Power (a layer has both a processor canvas and a
        // show canvas, and the active-canvas tracker flips between them), so a
        // selection on one canvas could show another canvas's numbers. Listing
        // each canvas by name removes that guesswork. getPortCounts/
        // getPowerCounts already group by the show canvas on these tabs and
        // exclude hidden canvases.
        const hidden = this._hiddenCanvasIdSet();
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases.filter(c => c && c.id && !hidden.has(c.id))
            : [];

        // Build one block per canvas. A single-canvas project is left empty
        // (the "All Canvases" total below already covers it, no point in
        // duplicating it).
        const buildPerCanvas = (containerId, rowsFor) => {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '';
            if (canvases.length <= 1) return;
            canvases.forEach(c => {
                const block = document.createElement('div');
                block.style.cssText = 'padding: 8px; background: #111; border: 1px solid #333; border-radius: 4px; font-size: 12px; color: #ccc; margin-bottom: 8px;';
                const title = document.createElement('div');
                title.style.cssText = 'font-weight: 600; color: #fff; margin-bottom: 4px;';
                title.textContent = c.name || 'Canvas';
                block.appendChild(title);
                rowsFor(c.id).forEach(([label, value]) => {
                    const row = document.createElement('div');
                    row.textContent = `${label}: ${value}`;
                    block.appendChild(row);
                });
                container.appendChild(block);
            });
        };

        // Data Flow totals
        buildPerCanvas('data-totals-per-canvas', (cid) => {
            const d = this.getPortCounts(cid);
            return [['Primary Ports', d.primary], ['Backup Ports', d.backup]];
        });
        const dataProject = this.getPortCounts();
        setText('data-totals-project-primary', dataProject.primary);
        setText('data-totals-project-backup', dataProject.backup);

        // Power totals
        // Two walls on different supplies is a real thing, so the amps are
        // reported PER VOLTAGE rather than blended: getPowerCounts returns null
        // for the combined figures when voltages differ, and fmtAmps would
        // print a confident "0" over a wall that is actually drawing current.
        const powerRows = (p) => {
            const rows = [
                ['Watts', fmtWatts(p.totalWatts)],
                ['Circuits', p.circuits],
            ];
            if (p.voltageMismatch && Array.isArray(p.byVoltage) && p.byVoltage.length) {
                p.byVoltage.forEach(b => {
                    rows.push([`Amps (1φ) @ ${b.voltage}V`, fmtAmps(b.amps1ph)]);
                    rows.push([`Amps (3φ) @ ${b.voltage}V`, fmtAmps(b.amps3ph)]);
                });
            } else {
                rows.push(['Amps (1φ)', fmtAmps(p.singlePhaseAmps)]);
                rows.push(['Amps (3φ)', fmtAmps(p.threePhaseAmps)]);
            }
            return rows;
        };
        buildPerCanvas('power-totals-per-canvas', (cid) => powerRows(this.getPowerCounts(cid)));
        const pwrProject = this.getPowerCounts();
        setText('power-totals-project-watts', fmtWatts(pwrProject.totalWatts));
        setText('power-totals-project-circuits', pwrProject.circuits);
        // The single-figure readouts have nowhere to put two answers, so they
        // say which voltages are in play rather than printing one of them.
        if (pwrProject.voltageMismatch) {
            const volts = (pwrProject.voltages || []).filter(v => v > 0).join(' / ');
            setText('power-totals-project-1ph', `mixed: ${volts} V`);
            setText('power-totals-project-3ph', `mixed: ${volts} V`);
        } else {
            setText('power-totals-project-1ph', fmtAmps(pwrProject.singlePhaseAmps));
            setText('power-totals-project-3ph', fmtAmps(pwrProject.threePhaseAmps));
        }
    }

    /**
     * Reflect the active canvas's perspective values on the toggle buttons.
     * Falls back to the project root for pre-Slice-1 / legacy projects that
     * have no canvas list yet. Called on project load and on every active-
     * canvas switch.
     */
    refreshPerspectiveButtons() {
        if (!this.project) return;
        const active = this._activeCanvas();
        document.querySelectorAll('.perspective-btn').forEach(btn => {
            const target = btn.getAttribute('data-target');
            const value = btn.getAttribute('data-perspective');
            if (!target || !value) return;
            const current = (active && active[target]) || this.project[target] || 'front';
            btn.classList.toggle('active', current === value);
        });
    }

    /**
     * Wire the NAMES switch (Screens / Group / Both) for grouped screens.
     * One project-level setting (project.groupNameDisplay): it names a
     * drawing convention for every grouped wall, the way perspective names
     * one for a whole canvas - not any single layer's toggle. The switch is
     * mirrored beside each tab's Screen Name control (the same way the
     * Border checkbox is mirrored across tabs), every copy driving the same
     * field. 'group' is the default and the pre-switch behaviour.
     */
    setupNameDisplayToggles() {
        document.querySelectorAll('.name-display-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const value = btn.getAttribute('data-name-display');
                if (!value || !this.project) return;
                const current = this.project.groupNameDisplay || 'group';
                if (current === value) return;
                this.project.groupNameDisplay = value;
                this.refreshNameDisplayButtons();
                this.saveProject();
                this.saveState('Change Name Display');
                if (window.canvasRenderer) window.canvasRenderer.render();
                if (typeof sendClientLog === 'function') {
                    sendClientLog('name_display_change', { value });
                }
            });
        });
        this.refreshNameDisplayButtons();
    }

    refreshNameDisplayButtons() {
        if (!this.project) return;
        const current = this.project.groupNameDisplay || 'group';
        document.querySelectorAll('.name-display-btn').forEach(btn => {
            btn.classList.toggle('active',
                btn.getAttribute('data-name-display') === current);
        });
    }

    setupEventListeners() {
        this.setupPixelMapBulkActions();
        this.setupPerspectiveToggles();
        this.setupNameDisplayToggles();
        // The listener wiring lives in app-wiring.js, one _wire* method per
        // area of the page. They run in this order because the old single
        // body registered its listeners in this order.
        this._wireProjectChrome();
        this._wireViewTabs();
        this._wireLayerToolbar();
        this._wireCanvasControls();
        this._wireScreenInfo();
        this._wireLabelsAndBorders();
        this._wireDataPanel();
        this._wirePowerPanel();
        this._wireColorsAndSizes();
        this._wireToolbarRaster();
        this._wireExportAndPrefs();

        this.setupMenuBar();
        this.setupPreferences();
    }
    
    getNextScreenName() {
        let maxNum = 0;
        if (this.project && this.project.layers) {
            for (const l of this.project.layers) {
                // Match "Screen1", "Screen 1", "Screen_1", "screen 12", etc.
                const m = (l.name || '').match(/^Screen[\s_]*(\d+)$/i);
                if (m) {
                    const n = parseInt(m[1], 10);
                    if (n > maxNum) maxNum = n;
                }
            }
        }
        // Also ensure we don't collide with the total layer count
        const layerCount = this.project && this.project.layers ? this.project.layers.length : 0;
        if (layerCount > maxNum) maxNum = layerCount;
        return `Screen${maxNum + 1}`;
    }

    addLayer(presetData) {
        // Server-side props control panel generation (columns/rows/cabinet sizes/colors/etc.)
        // Client-side props (data flow, power, labels...) are applied after the layer is returned.
        const prefs = this.getPreferences();
        // A stored preference that is not a colour ('#FFF', 'abcdef', '')
        // must not reach the server verbatim; the literal is what shipped.
        // The tile colours take the same check (a 3-digit '#FFF' expands):
        // hexToRgb('#FFF') read as red, and a '' border landed as-is on
        // the server and on all four per-view borders.
        const color = (value, fallback) => this.normalizeHexColor(value, fallback);
        const tile = (value, fallback) => this.normalizeTileColor(value, fallback);
        const color1 = this.hexToRgb(tile(prefs.color1, '#404680'));
        const color2 = this.hexToRgb(tile(prefs.color2, '#959CB8'));
        const borderColor = tile(prefs.borderColor, '#FFFFFF');
        const labelsColor = color(prefs.screenNameColor, '#FFFFFF');
        const cabinetIdColor = color(prefs.cabinetIdColor, '#FFFFFF');
        // A preset's two tile colours take the same check as the rest of
        // its colours. The canvas draws a tile from an {r, g, b} object
        // (canvas-render's rgb()), which is what a layer stores and what a
        // preset saved from one carries; a hand-edited preset may hold a
        // hex string instead, and anything else ('', 'nope', [], {r: 'x'})
        // is no colour. So: a well-formed {r, g, b} lands as is, a hex
        // string (3 or 6 digits, # or not) becomes the object, and the
        // rest fall back to the preference's colour - which until
        // 2026-09-22 only '' and null did, so 'nope' reached the server
        // and drew grey.
        const tileRgb = (value, fallback) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                const ch = ['r', 'g', 'b'].map(k => Number(value[k]));
                return ch.every(n => Number.isInteger(n) && n >= 0 && n <= 255)
                    ? { r: ch[0], g: ch[1], b: ch[2] } : fallback;
            }
            const hex = tile(value, '');
            return hex ? this.hexToRgb(hex) : fallback;
        };
        let serverProps;
        if (presetData && typeof presetData === 'object') {
            serverProps = {
                columns: presetData.columns != null ? presetData.columns : prefs.columns,
                rows: presetData.rows != null ? presetData.rows : prefs.rows,
                cabinet_width: presetData.cabinet_width != null ? presetData.cabinet_width : prefs.panelWidth,
                cabinet_height: presetData.cabinet_height != null ? presetData.cabinet_height : prefs.panelHeight,
                color1: tileRgb(presetData.color1, color1),
                color2: tileRgb(presetData.color2, color2),
                border_color: tile(presetData.border_color, borderColor),
                panel_weight: presetData.panel_weight != null ? presetData.panel_weight : prefs.panelWeight,
                weight_unit: presetData.weight_unit || prefs.weightUnit,
                // The two colours the server sets on a new layer (create_layer);
                // the Look tab's "Info labels" and "Cabinet ID text" preferences.
                // A preset value that is not a colour ('nope', 'red', [], {})
                // is no colour: the preference default applies, the same
                // rule applyPresetClientProps holds for the rest.
                labelsColor: color(presetData.labelsColor, labelsColor),
                cabinetIdColor: color(presetData.cabinetIdColor, cabinetIdColor)
            };
        } else {
            serverProps = {
                columns: prefs.columns,
                rows: prefs.rows,
                cabinet_width: prefs.panelWidth,
                cabinet_height: prefs.panelHeight,
                color1: color1,
                color2: color2,
                border_color: borderColor,
                panel_weight: prefs.panelWeight,
                weight_unit: prefs.weightUnit,
                labelsColor: labelsColor,
                cabinetIdColor: cabinetIdColor
            };
        }

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: this.getNextScreenName(),
                offset_x: 0,
                offset_y: 0,
                ...serverProps
            })
        })
        .then(res => {
            // A 4xx/5xx still parses (the server answers {error}), and the
            // chain below would go on to select a layer with no id.
            if (!res.ok) throw new Error(`POST /api/layer/add answered ${res.status}`);
            return res.json();
        })
        .then(layer => {
            sendClientLog('add_layer', {
                id: layer.id, name: layer.name,
                columns: layer.columns, rows: layer.rows,
                cabinet_width: layer.cabinet_width, cabinet_height: layer.cabinet_height,
                offset_x: layer.offset_x, offset_y: layer.offset_y,
                preset: presetData ? (presetData._presetName || true) : false,
                totalLayers: this.project.layers ? this.project.layers.length + 1 : 1
            });
            // Initialize client-side defaults first (baseline)
            this.initializeLayerDefaults(layer);
            // Then overlay preset client-side props on top
            const appliedPreset = presetData && typeof presetData === 'object';
            if (appliedPreset) {
                this.applyPresetClientProps(layer, presetData);
            }
            // A NEW screen's breakout and splitter packing come from the
            // Distros & multis preferences - here, at creation, and never
            // on a screen that exists (initializeLayerDefaults runs on
            // every load, so it is not the place). A preset that carries
            // its own wins. The breakout is stored only where the
            // screen's voltage allows it (2026-09-22: a 110 V / 120 V
            // screen runs True1, powerCON or Edison; the L21-30 box is
            // 208 V only); otherwise the screen stays unset and reads
            // the voltage's own default, as it always has.
            this.applyNewScreenPowerPreferences(layer, appliedPreset ? presetData : null);
            // Then the store's own rule: a preference the voltage does not
            // allow (L21-30 at 110 V, Edison at 208 V) was skipped above and
            // left the screen with no breakout at all, and a preset carries
            // whatever it holds; both end on the eligible default (Edison
            // at or below 120 V, True1 above) - here, so the PUT below
            // stores it, rather than on the next load.
            if (typeof this.normalizePowerBreakout === 'function') {
                this.normalizePowerBreakout(layer);
            }

            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();

            // saveState AFTER the layer lands in the project (same fix as Add
            // Canvas): snapshotting before the fetch resolved captured the
            // pre-add state, so redo after undo silently lost the new screen.
            this.saveState('Add Layer');

            // Save the new defaults to localStorage
            this.saveClientSideProperties();

            // IMPORTANT: the server only knows the structural fields sent via
            // /api/layer/add (columns, cabinet dims, tile colours, the two
            // label colours); create_layer stores its own literal defaults
            // for everything else. Every client-side default that
            // initializeLayerDefaults just set - the Data and Power tab
            // colours, the circuit colours, bitDepth, frameRate, flowPattern,
            // line widths, label sizes - and any preset value on top lives
            // only on the client at this point. Any subsequent server
            // re-fetch (delete_layer, reload, file load) would clobber them
            // with the literals. Push the enriched layer back now, preset or
            // not, so server + client stay in sync. (Until 2026-09-22 only
            // the preset branch did this, so a new screen lost its
            // Preferences colours on the next reload unless it was saved.)
            this.updateLayers([layer]);
        })
        .catch(error => {
            // The POST itself failing (offline, the server gone, a 500)
            // was an unhandled rejection on the page: nothing was added,
            // and nothing said so. Log it and say so; never throw from
            // here. (updateLayers has its own catch for the push above.)
            sendClientLog('add_layer_failed', {
                preset: presetData ? (presetData._presetName || true) : false,
                error: error ? String(error.message || error) : ''
            });
            if (typeof this._toast === 'function') {
                this._toast('The screen was not added. Check the connection and try again.', true);
            }
        });
    }

    applyNewScreenPowerPreferences(layer, presetData) {
        if (!layer || (layer.type || 'screen') !== 'screen') return;
        const prefs = this.getPreferences();
        const preset = presetData || {};
        if (preset.powerBreakoutType == null && typeof this.getPowerBreakoutTypes === 'function') {
            const want = this.getPowerBreakoutTypes().find(t => t.id === prefs.breakoutType);
            if (want && (typeof this._breakoutEligible !== 'function'
                         || this._breakoutEligible(want, layer.powerVoltage))) {
                layer.powerBreakoutType = want.id;
            }
        }
        if (preset.powerSplitters == null) {
            const cur = (layer.powerSplitters && typeof layer.powerSplitters === 'object')
                ? layer.powerSplitters : { enabled: false, maxWays: 3, manual: { merge: [], split: [] } };
            layer.powerSplitters = { ...cur, enabled: !!prefs.splittersEnabled };
        }
    }

    // Properties excluded from presets (identity, runtime position, cached computations).
    // Everything else on a layer can be preserved as a preset.
    getPresetExcludedKeys() {
        return new Set([
            'id', 'name', 'visible', 'locked',
            'offset_x', 'offset_y',
            // v0.11.0: group membership is identity, not a setting. A preset
            // is a bag of hardware/appearance values reused across projects,
            // and a group id only means anything inside the one project that
            // owns it - carrying it would drop a fresh screen into a group
            // that does not exist (or worse, into an unrelated group that
            // happens to reuse the id).
            'group_id',
            'panels',  // panel array is regenerated from columns/rows on server
            '_powerError', '_powerCircuits', '_powerPanelCircuitMap', '_powerPanelIndexMap',
            // The scoped twins carry the same per-frame render data keyed by
            // layer as well as row/col, so a circuit crossing members can tint
            // both. Same lifetime as the unscoped maps above - rebuilt every
            // frame, and Maps besides, so serialising them writes `{}` into a
            // preset and leaves a dead key behind on load.
            '_powerPanelCircuitScopedMap', '_powerPanelIndexScopedMap',
            '_powerCircuitOwners',
            '_powerCircuitNumKeys', '_powerTotalAmps1', '_powerTotalAmps3',
            '_powerCircuitsRequired', '_capacityError', '_portsRequired', '_autoPortsRequired',
            '_lowLatencyDerate',
            '_imageObj', 'imageData'
        ]);
    }

    serializeLayerAsPreset(layer) {
        if (!layer) return null;
        const excluded = this.getPresetExcludedKeys();
        const out = {};
        Object.keys(layer).forEach(k => {
            if (excluded.has(k)) return;
            if (k.startsWith('_')) return;  // skip runtime caches
            out[k] = layer[k];
        });
        // Ensure common layer-default keys are always present even if the
        // source layer was loaded from an older project file that lacked them.
        // Without this, a fresh layer created from the preset would fall back
        // to `initializeLayerDefaults` values instead of the intended preset.
        const ensuredDefaults = {
            portMappingMode: 'organized',
            randomDataColors: false
        };
        Object.keys(ensuredDefaults).forEach(k => {
            if (out[k] === undefined) out[k] = ensuredDefaults[k];
        });
        // v0.11.0 (step 6): hand-drawn paths still travel with a preset - the
        // geometry that gives them meaning (columns / rows / cabinet size)
        // travels with it too - but only the entries that mean "a panel in
        // this screen". A preset is reused in OTHER projects, where a layer id
        // from this one names a different screen or nothing at all, so a
        // cross-member entry is dropped at SAVE time rather than being carried
        // out of the only project it was ever true in. Same rule as duplicate
        // and paste: nothing but the owner is being copied, so nothing that
        // names a peer can survive.
        // Only rewritten when the layer actually carried them, so a preset
        // saved from a layer without paths keeps the exact shape it had before.
        if (out.customPortPaths !== undefined) {
            out.customPortPaths = this.copyPathsForNewOwner(
                layer.customPortPaths, layer.id, null);
        }
        if (out.powerCustomPaths !== undefined) {
            out.powerCustomPaths = this.copyPathsForNewOwner(
                layer.powerCustomPaths, layer.id, null);
        }
        return out;
    }

    applyPresetClientProps(layer, presetData) {
        const excluded = this.getPresetExcludedKeys();
        // Server-side structural props already applied via /api/layer/add; skip them here.
        const serverKeys = new Set(['columns', 'rows', 'cabinet_width', 'cabinet_height',
            'color1', 'color2', 'border_color', 'panel_weight', 'weight_unit']);
        // A colour key a preset carries as anything but a hex colour - null,
        // '', 'nope', 'red', [], {} (a hand-edited file, or one saved from
        // a layer that never had the colour) - is "no colour", not a
        // colour: the default initializeLayerDefaults (or the server, for
        // the two label colours) already gave the layer stays, with the
        // shipped literal behind it should the layer somehow lack one.
        // Every preset colour goes through normalizeHexColor, so a valid
        // one lands upper case the way the layer stores it. The circuit
        // map is checked letter by letter: a letter that is not a colour
        // keeps the default in that position, and a map that is not a
        // plain object ([] included) is no map at all.
        const colorKeys = {
            labelsColor: '#FFFFFF', cabinetIdColor: '#FFFFFF',
            arrowColor: '#0042AA', dataFlowColor: '#FFFFFF',
            primaryColor: '#00FF00', primaryTextColor: '#000000',
            backupColor: '#FF0000', backupTextColor: '#FFFFFF',
            powerLineColor: '#FF0000', powerArrowColor: '#0042AA',
            powerLabelBgColor: '#D95000', powerLabelTextColor: '#000000',
            border_color_pixel: '#FFFFFF', border_color_cabinet: '#FFFFFF',
            border_color_data: '#FFFFFF', border_color_power: '#FFFFFF'
        };
        Object.keys(presetData).forEach(k => {
            if (excluded.has(k)) return;
            if (serverKeys.has(k)) return;
            if (k.startsWith('_')) return;
            if (k === 'powerCircuitColors') {
                const given = presetData[k];
                if (!given || typeof given !== 'object' || Array.isArray(given)) return;
                const current = (layer.powerCircuitColors && typeof layer.powerCircuitColors === 'object')
                    ? layer.powerCircuitColors : this.getDefaultPowerCircuitColors();
                const next = { ...current };
                ['A', 'B', 'C', 'D', 'E', 'F'].forEach(letter => {
                    next[letter] = this.normalizeHexColor(given[letter], current[letter]);
                });
                layer[k] = next;
                return;
            }
            if (Object.prototype.hasOwnProperty.call(colorKeys, k)) {
                layer[k] = this.normalizeHexColor(presetData[k],
                    this.normalizeHexColor(layer[k], colorKeys[k]));
                return;
            }
            layer[k] = presetData[k];
        });
        // v0.11.0 (step 6): the same drop on the way IN. serializeLayerAsPreset
        // strips cross-member entries at save time, but presets already sitting
        // on disk from an in-between build can still hold one, and a preset
        // file is hand-editable. Passing a null owner id and no idMap means no
        // id from the preset's project maps to anything here, so every entry
        // naming a peer is dropped and only the plain {row, col} route lands.
        if (layer.customPortPaths !== undefined) {
            layer.customPortPaths = this.copyPathsForNewOwner(
                layer.customPortPaths, null, null);
        }
        if (layer.powerCustomPaths !== undefined) {
            layer.powerCustomPaths = this.copyPathsForNewOwner(
                layer.powerCustomPaths, null, null);
        }
        // v0.11.0: presets saved before Low Latency existed can still carry
        // 'brompton-ull', so migrate here as well as on the file-load paths.
        this.migrateLowLatencyProcessor(layer);
        if (layer.lowLatency === undefined) layer.lowLatency = false;
    }

    // v0.11.0: Low Latency behaviour per processor family. Single source of
    // truth for both the capacity math (calculatePortCapacity) and the note
    // shown next to the Low Latency control.
    //
    // Provenance:
    //  - Brompton: Tessera User Manual section 4.4, the published Ultra Low
    //    Latency pixels-per-port columns (16 frame rates x 3 bit depths).
    //    Every ULL cell is the normal-mode cell halved and floored, so the
    //    factor is EXACTLY 0.5 rather than a per-cell table. ULL is an
    //    SX40/S8 feature and needs an HDMI source. The "Low Latency Mode" on
    //    T1/M2 is a different feature and costs no capacity at all.
    //  - Megapixel: "HELIOS(R) LED Processing Platform - User Guide" v26.04.0
    //    (2026-04-20). Tile LL + Processor LL do not change the Appendix K.14
    //    port capacities; the real cost is halved daisy-chain length in
    //    stacked columns.
    //  - NovaStar: low latency constrains port GEOMETRY rather than the pixel
    //    budget. Sourced from NovaStar's OWN answers to our questions, which
    //    supersede the published manuals we first worked from:
    //      * there is NO 512 px port-width limit. NovaStar: on the latest
    //        firmware the single Ethernet port loading width limit of 512 px
    //        "has been removed" on NovaPro UHD Jr, and "this limitation has
    //        also been removed" on MCTRL4K and MCTRL660 Pro; the manuals are
    //        wrong and are being revised. The cap used to be enforced here and
    //        must not come back from a manual reading.
    //      * (1 - Y / canvasHeight) applies to EVERY NovaStar product, legacy
    //        and COEX alike. NovaStar: "for any novastar product including
    //        legacy and coex, when low-latency mode is enabled, the screen
    //        connection must meet the required conditions, including top
    //        alignment and vertical cabinet formula". So ports load as
    //        vertical runs of cabinets, and a port whose topmost cabinet does
    //        not sit at canvas Y=0 keeps only that fraction of the table
    //        figure. This is why yDerate is true on all three NovaStar lines.
    //    Every NovaStar sending device is treated as low-latency compatible.
    //    Receiving cards are NOT: A5S Plus/-N, A8S/-N, A8S Pro, A10S Plus/-N,
    //    A10S Pro, MRV208-N, MRV412-N and MRV416-N support it; MRV328 and
    //    MRV336 do not. We do not model cards, so that list is UI text (the
    //    descriptor's `cards`), not math. In a correctly built layout the
    //    ports are top-aligned, Y is 0, and the derate costs nothing; it is
    //    the penalty for a port that is NOT top-aligned.
    //
    // capacity.kind:
    //   'factor'      - multiply the table lookup by capacity.factor
    //   'none'        - low latency costs no pixels per port
    //   'novastar-ll' - geometric, so the TABLE VALUE IS UNCHANGED: the lookup
    //                   is the port's TOTAL at the current bit depth and frame
    //                   rate. The per-port (1 - Y/H) derate is applied in
    //                   calculatePortAssignments, the only place that can see
    //                   where a port actually sits on the canvas.
    //
    // `cards`: receiving cards, shown as the note's tooltip. Informational -
    // the app does not model cards, so nothing in the math reads this.
    //
    // v0.11.0: `rules` is the same behaviour written out as the rules the user
    // is actually working under, listed in the Data sidebar under the
    // Pixels/Port readout whenever Low Latency is on (setLowLatencyRules in
    // app-screen-info.js). It lives HERE, next to the capacity block it
    // describes, so the wording cannot drift away from the math the way strings
    // built inside a render function would. DISPLAY ONLY - nothing in any
    // calculation reads `rules`.
    //   `text` - one rule, plain language, terse.
    //   `tip`  - optional tooltip for a rule with more detail than a line holds.
    // The three NovaStar entries repeat the same three geometric rules, exactly
    // as they already repeat `note` and `cards`; 5G carries a fourth for its
    // narrow-port penalty. test_low_latency_rules_do_not_drift_between_novastar_lines
    // pins that repetition so an edit to one line cannot silently miss another.
    lowLatencyProfiles = {
        'novastar-armor': {
            supported: true,
            capacity: { kind: 'novastar-ll', yDerate: true },
            note: 'Ports must load vertically and start at the top of the canvas; a port that starts lower loses capacity. MRV328 and MRV336 cannot do low latency.',
            cards: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.',
            rules: [
                { text: 'Ports load vertically and must start at the top of the canvas.' },
                { text: 'A port starting lower keeps only (1 - Y/H) of its pixels per port.' },
                {
                    text: 'Needs a supported receiving card. MRV328 and MRV336 cannot do low latency.',
                    tip: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.'
                }
            ]
        },
        'novastar-coex-1g': {
            supported: true,
            capacity: { kind: 'novastar-ll', yDerate: true },
            note: 'Ports must load vertically and start at the top of the canvas; a port that starts lower loses capacity. MRV328 and MRV336 cannot do low latency.',
            cards: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.',
            rules: [
                { text: 'Ports load vertically and must start at the top of the canvas.' },
                { text: 'A port starting lower keeps only (1 - Y/H) of its pixels per port.' },
                {
                    text: 'Needs a supported receiving card. MRV328 and MRV336 cannot do low latency.',
                    tip: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.'
                }
            ]
        },
        'novastar-5g': {
            supported: true,
            capacity: { kind: 'novastar-ll', yDerate: true },
            note: 'Ports must load vertically and start at the top of the canvas; a port that starts lower loses capacity. MRV328 and MRV336 cannot do low latency.',
            cards: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.',
            rules: [
                { text: 'Ports load vertically and must start at the top of the canvas.' },
                { text: 'A port starting lower keeps only (1 - Y/H) of its pixels per port.' },
                {
                    text: 'Needs a supported receiving card. MRV328 and MRV336 cannot do low latency.',
                    tip: 'Receiving cards with low latency: A5S Plus, A5S Plus-N, A8S, A8S-N, A8S Pro, A10S Plus, A10S Plus-N, A10S Pro, MRV208-N, MRV412-N, MRV416-N. MRV328 and MRV336 do NOT support low latency.'
                },
                {
                    // v0.11.0: 5G only - novastarMinLoadWidth returns 0 everywhere
                    // else, so no other entry may carry this rule. The second
                    // sentence is not padding: calculatePortAssignments reads
                    // novastarMinLoadWidth unconditionally, so the penalty is a
                    // property of the 5G port and NOT of Low Latency. Listing it
                    // here without saying so would read as a low latency cost.
                    text: 'A port narrower than 128 px loses (128 - width) x height. On 5G that applies with or without Low Latency.',
                    tip: 'NovaStar publish this under the 5G Ethernet Port Load Capacity table (XA50 Pro / CA50E receiving cards) only. Load width is the port\'s own width, not one cabinet\'s.'
                }
            ]
        },
        'brompton': {
            supported: true,
            capacity: { kind: 'factor', factor: 0.5 },
            note: 'Ultra Low Latency: SX40/S8 only. HDMI input, no SDI. Halves pixels per port.',
            rules: [
                { text: 'Pixels per port is halved.' },
                { text: 'Ultra Low Latency is an SX40/S8 feature.' },
                { text: 'HDMI input only, no SDI.' }
            ]
        },
        'megapixel-1g': {
            supported: true,
            capacity: { kind: 'none' },
            note: 'No capacity change; halves daisy-chain length in stacked columns.',
            rules: [
                { text: 'No change to pixels per port.' },
                { text: 'Halves the daisy-chain length in stacked columns.' }
            ]
        },
        'megapixel-2.5g': {
            supported: true,
            capacity: { kind: 'none' },
            note: 'No capacity change; halves daisy-chain length in stacked columns.',
            rules: [
                { text: 'No change to pixels per port.' },
                { text: 'Halves the daisy-chain length in stacked columns.' }
            ]
        }
    };

    // v0.11.0: capacity kinds whose math actually runs today. Until a kind is
    // listed, isLowLatencyCapacityPending() is true and the UI states plainly
    // that the constraint is not in the numbers yet. 'novastar-ll' joined the
    // list in pass 2, when calculatePortAssignments started applying the
    // per-port (1 - Y/H) derate.
    lowLatencyImplementedKinds = ['factor', 'none', 'novastar-ll'];

    // The frame rates the Screen Info #frame-rate dropdown offers, before the
    // processor narrows them.
    //
    // TWIN of `baseRates` inside updateFrameRateOptions() (app-export-io.js),
    // which owns that <select> and needs a currentLayer to render into. The
    // group settings dialog has no current layer and no <select> to read, so
    // the list is stated here for callers that only have a processor name.
    //
    // NOT a capacity table: no figure here feeds a calculation. It is the set
    // of rates a user may pick from; which of them a given processor actually
    // publishes is publishedFrameRates' answer, not this list's.
    frameRateChoices = [
        23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 72, 100, 120, 144, 150,
        180, 192, 200, 240, 250
    ];

    // Which of those a processor may be set to. publishedFrameRates
    // (app-export-io.js) is the authority - the rates the processor's own
    // table has a row for - and this makes the same call, in the same way, as
    // updateFrameRateOptions, so the group settings dialog and the Screen Info
    // dropdown can never offer different lists.
    // tests/test_screen_groups_integrity.py pins the two together.
    getSelectableFrameRates(processorType) {
        const published = (typeof this.publishedFrameRates === 'function')
            ? this.publishedFrameRates(processorType) : null;
        // No table at all (an unknown processor) keeps every rate rather than
        // leaving nothing to pick, same as the dropdown.
        if (!published) return this.frameRateChoices.slice();
        const allowed = this.frameRateChoices.filter(
            rate => published.has(Math.round(rate)));
        return allowed.length ? allowed : this.frameRateChoices.slice();
    }

    // Port capacity lookup tables from manufacturer specs
    // Keys are frame rates, values are pixel capacities
    portCapacityTables = {
        // NovaStar Armor (MSD/MRV) legacy 1G receiving cards
        // 8-bit uses 24x; 10/12-bit use 48x (max 120 Hz)
        'novastar-armor': {
            8:  { 24:1649306, 25:1583333, 30:1319444, 50:791667, 60:659722, 120:329861 },
            10: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931 },
            12: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931 }
        },
        // NovaStar COEX 1G (A10s/A8s Pro) receiving cards
        // 8-bit uses 24x; 10-bit uses 32x; 12-bit uses 48x
        'novastar-coex-1g': {
            8:  { 24:1649306, 25:1583333, 30:1319444, 50:791667, 60:659722, 120:329861, 144:274884, 240:164931 },
            10: { 24:1236979, 25:1187500, 30:989583,  50:593750, 60:494792, 120:247396, 144:206163, 240:123698 },
            12: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931, 144:137442, 240:82465 }
        },
        // NovaStar COEX 5G (CX40 Pro) receiving cards
        // v0.11.0: NovaStar 5G (CX40 Pro etc. with XA50 Pro / CA50E receiving
        // cards), from NovaStar's published "Ethernet Port Load Capacity" table,
        // confirmed direct with NovaStar. Their formula is
        //   8-bit:  capacity x 24 x frame rate < 5G x 0.85
        //   10-bit: capacity x 32 x frame rate < 5G x 0.88
        //   12-bit: capacity x 48 x frame rate < 5G x 0.85
        // Note the multipliers are 24/32/48, NOT bitDepth x 3. Our previous
        // figures used x36 for 12-bit, which overstated 12-bit capacity by ~17%
        // and under-counted ports. These are the published values verbatim.
        // NovaStar also state a port only reaches these figures when its load
        // width is >= 128 px; below that, capacity drops by (128 - width) x height.
        'novastar-5g': {
            8:  { 24:7378000, 25:7082800, 30:5902400, 50:3541440, 60:2951200, 120:1475600, 144:1229600, 240:737800 },
            10: { 24:5728280, 25:5499149, 30:4582624, 50:2749574, 60:2291312, 120:1145656, 144:954713,  240:572828 },
            12: { 24:3689000, 25:3541440, 30:2951200, 50:1770720, 60:1475600, 120:737800,  144:612374,  240:368900 }
        },
        'brompton': {
            8:  { 24:1312500, 25:1260000, 30:1050000, 48:656250, 50:630000, 60:525000, 72:437500, 100:315000, 120:262500, 144:218750, 150:210000, 180:175000, 192:164063, 200:157500, 240:131250, 250:126000 },
            10: { 24:1050000, 25:1008000, 30:840000,  48:525000, 50:504000, 60:420000, 72:350000, 100:252000, 120:210000, 144:175000, 150:168000, 180:140000, 192:131250, 200:126000, 240:105000, 250:100800 },
            12: { 24:875000,  25:840000,  30:700000,   48:437500, 50:420000, 60:350000, 72:291667, 100:210000, 120:175000, 144:145833, 150:140000, 180:116667, 192:109375, 200:105000, 240:87500,  250:84000 }
        },
        // v0.11.0: superseded by 'brompton' + lowLatency (migrateLowLatencyProcessor).
        // Kept so a stale value that slipped past the migration - an old preset, a
        // hand-edited file, a layer restored from localStorage - still resolves to a
        // real capacity instead of falling through to 0 / "N/A". Removed from both
        // <select> blocks so it can no longer be chosen. Do NOT halve it again:
        // these cells are already the ULL numbers.
        'brompton-ull': {
            8:  { 24:656250,  25:630000,  30:525000,  48:328125, 50:315000, 60:262500, 72:218750, 100:157500, 120:131250, 144:109375, 150:105000, 180:87500,  192:82031,  200:78750,  240:65625,  250:63000 },
            10: { 24:525000,  25:504000,  30:420000,  48:262500, 50:252000, 60:210000, 72:175000, 100:126000, 120:105000, 144:87500,  150:84000,  180:70000,  192:65625,  200:63000,  240:52500,  250:50400 },
            12: { 24:437500,  25:420000,  30:350000,  48:218750, 50:210000, 60:175000, 72:145833, 100:105000, 120:87500,  144:72917,  150:70000,  180:58333,  192:54688,  200:52500,  240:43750,  250:42000 }
        },
        // v0.11.0: Megapixel HELIOS switch-to-tile output port capacity.
        // Source: "HELIOS(R) LED Processing Platform - User Guide", v26.04.0 (2026-04-20),
        // Appendix K.14 "HELIOS & Switch - Output Port Capacity (Pixels)", p.216.
        // Megapixel publishes no 8-bit figures for HELIOS, so only 10/12 exist here.
        // Prior values came from the rounded switch spec-sheet figure (425,000 px
        // @ 12-bit/60Hz) and ran up to ~6% HIGH against K.14; do not reintroduce them.
        // 2.5G requires 2.5G-capable tiles; most tiles are 1G only.
        'megapixel-1g': {
            10: { 24:1237000, 25:1187000, 30:985000, 48:608000, 50:583000, 60:482000, 120:230000, 144:188000, 180:146000, 200:129000, 240:104000 },
            12: { 24:1031000, 25:989000,  30:821000, 48:506000, 50:485000, 60:401000, 120:192000, 144:157000, 180:122000, 200:108000, 240:87000 }
        },
        'megapixel-2.5g': {
            10: { 24:3094000, 25:2968000, 30:2464000, 48:1520000, 50:1457000, 60:1205000, 120:576000, 144:471000, 180:366000, 200:324000, 240:261000 },
            12: { 24:2578000, 25:2473000, 30:2053000, 48:1267000, 50:1214000, 60:1004000, 120:480000, 144:393000, 180:305000, 200:270000, 240:218000 }
        }
    };
}
