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
        this.customSelection = new Set();
        this.customDebug = false;
        this.powerCustomSelection = new Set();
        this.powerCustomDebug = false;
        // Pixel Map bulk-select: drag-select panels of the current layer to
        // bulk-toggle blank or half-tile state. Set of "row,col" strings.
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
            sendClientLog('app_init', { ua: navigator.userAgent });
            // Background-check upstream panel catalog after the rest of boot
            // settles so we don't slow first paint. Failure is silent.
            setTimeout(() => this.checkPanelCatalogUpdate(), 1500);
        });
    }

    /**
     * Wire the left/right sidebar collapse toggles. Each side is independent
     * and the collapsed state persists in localStorage so the panel stays
     * the way the user left it across reloads. The toggle button is
     * positioned dynamically against the sidebar's actual geometry (via
     * getBoundingClientRect), so it always sits flush with the sidebar's
     * inner edge regardless of monitor size, sidebar width, or window
     * resize. ResizeObserver keeps it pinned in place if the sidebar's
     * dimensions ever change at runtime.
     */
    initSidebarToggles() {
        const sides = [
            { key: 'left', sidebarId: 'left-sidebar', toggleId: 'left-sidebar-toggle', expandSym: '›', collapseSym: '‹' },
            { key: 'right', sidebarId: 'right-sidebar', toggleId: 'right-sidebar-toggle', expandSym: '‹', collapseSym: '›' },
        ];
        sides.forEach(({ key, sidebarId, toggleId, expandSym, collapseSym }) => {
            const sidebar = document.getElementById(sidebarId);
            const btn = document.getElementById(toggleId);
            if (!sidebar || !btn) return;
            const storageKey = `ledRasterSidebarCollapsed_${key}`;
            const positionToggle = () => {
                const rect = sidebar.getBoundingClientRect();
                if (key === 'left') {
                    btn.style.left = `${Math.round(rect.right)}px`;
                    btn.style.right = '';
                } else {
                    btn.style.right = `${Math.round(window.innerWidth - rect.left)}px`;
                    btn.style.left = '';
                }
            };
            const resizeCanvas = () => {
                if (!window.canvasRenderer) return;
                if (window.canvasRenderer.setupCanvas) window.canvasRenderer.setupCanvas();
                window.canvasRenderer.render();
            };
            const apply = (collapsed) => {
                sidebar.classList.toggle('collapsed', collapsed);
                document.body.classList.toggle(`${key}-sidebar-collapsed`, collapsed);
                btn.textContent = collapsed ? expandSym : collapseSym;
                btn.title = collapsed
                    ? `Expand ${key} panel`
                    : `Collapse ${key} panel`;
                // The CSS width transition runs ~180ms. Reposition the
                // toggle and resize the canvas at multiple points during /
                // after the animation so the canvas always fills the
                // available wrapper width, otherwise the canvas keeps its
                // pre-collapse pixel dimensions and the user sees a black
                // strip on the side where the sidebar used to be.
                requestAnimationFrame(() => { positionToggle(); resizeCanvas(); });
                setTimeout(() => { positionToggle(); resizeCanvas(); }, 60);
                setTimeout(() => { positionToggle(); resizeCanvas(); }, 220);
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
        });
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
            sendClientLog('socket_layer_updated', { id: layer.id });
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
                this.dedupeProjectLayers('socket_layer_updated');
                this.updateUI();
            } else {
                this.upsertProjectLayer(layer);
                this.dedupeProjectLayers('socket_layer_updated_upsert');
                this.updateUI();
            }
        });
        this.socket.on('preferences_updated', (prefs) => {
            console.log('WEBSOCKET preferences_updated received');
            this._serverPreferences = prefs;
        });
    }

    // Extract client-side only properties from a layer
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
            portMappingMode: layer.portMappingMode,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
            portLabelOverridesReturn: layer.portLabelOverridesReturn,
            customPortPaths: layer.customPortPaths,
            customPortIndex: layer.customPortIndex,
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
            showPowerCircuitInfo: layer.showPowerCircuitInfo,
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
            powerCustomPaths: layer.powerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
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
            fontUnderline: layer.fontUnderline
        };
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
                this.loadClientSideProperties();
                
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
    
    // Load client-side properties from localStorage
    loadClientSideProperties({ skipPreferences = false } = {}) {
        if (!this.project || !this.project.layers) return;
        const prefs = this.getPreferences();
        
        const savedProps = localStorage.getItem('ledRasterClientProps');
        const savedVersion = localStorage.getItem('ledRasterPropsVersion');
        const currentVersion = '0.4.7'; // Increment to force reset of all localStorage settings
        
        // If version mismatch, clear old props and use fresh defaults
        if (savedVersion !== currentVersion) {
            console.log('Props version mismatch, resetting to new defaults');
            localStorage.removeItem('ledRasterClientProps');
            localStorage.removeItem('ledRasterSize'); // Also reset raster size
            localStorage.setItem('ledRasterPropsVersion', currentVersion);
            // Don't load from localStorage, just use defaults below
            window.canvasRenderer.rasterWidth = prefs.rasterWidth;
            window.canvasRenderer.rasterHeight = prefs.rasterHeight;
            document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
            document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;
            this.saveRasterSize();
        } else if (savedProps && this.shouldUseSavedClientProps()) {
            // First, apply any saved properties from localStorage
            try {
                const propsMap = JSON.parse(savedProps);
                
                this.project.layers.forEach(layer => {
                    const layerProps = propsMap[layer.id];
                    if (layerProps) {
                        // Only set properties that are actually defined in localStorage
                        if (layerProps.dataFlowColor !== undefined) layer.dataFlowColor = layerProps.dataFlowColor;
                        if (layerProps.arrowColor !== undefined) layer.arrowColor = layerProps.arrowColor;
                        if (layerProps.dataFlowLabelSize !== undefined) layer.dataFlowLabelSize = layerProps.dataFlowLabelSize;
                        if (layerProps.arrowLineWidth !== undefined) layer.arrowLineWidth = layerProps.arrowLineWidth;
                        if (layerProps.primaryColor !== undefined) layer.primaryColor = layerProps.primaryColor;
                        if (layerProps.primaryTextColor !== undefined) layer.primaryTextColor = layerProps.primaryTextColor;
                        if (layerProps.backupColor !== undefined) layer.backupColor = layerProps.backupColor;
                        if (layerProps.backupTextColor !== undefined) layer.backupTextColor = layerProps.backupTextColor;
                        if (layerProps.randomDataColors !== undefined) layer.randomDataColors = layerProps.randomDataColors;
                        if (layerProps.flowPattern !== undefined) layer.flowPattern = layerProps.flowPattern;
                        if (layerProps.bitDepth !== undefined) layer.bitDepth = layerProps.bitDepth;
                        if (layerProps.frameRate !== undefined) layer.frameRate = layerProps.frameRate;
                        if (layerProps.processorType !== undefined) layer.processorType = layerProps.processorType;
                        if (layerProps.portMappingMode !== undefined) layer.portMappingMode = layerProps.portMappingMode;
                        if (layerProps.portLabelTemplatePrimary !== undefined) layer.portLabelTemplatePrimary = layerProps.portLabelTemplatePrimary;
                        if (layerProps.portLabelTemplateReturn !== undefined) layer.portLabelTemplateReturn = layerProps.portLabelTemplateReturn;
                        if (layerProps.portLabelOverridesPrimary !== undefined) layer.portLabelOverridesPrimary = layerProps.portLabelOverridesPrimary;
                        if (layerProps.portLabelOverridesReturn !== undefined) layer.portLabelOverridesReturn = layerProps.portLabelOverridesReturn;
                        if (layerProps.customPortPaths !== undefined) layer.customPortPaths = layerProps.customPortPaths;
                        if (layerProps.customPortIndex !== undefined) layer.customPortIndex = layerProps.customPortIndex;
                        if (layerProps.powerVoltage !== undefined) layer.powerVoltage = layerProps.powerVoltage;
                        if (layerProps.powerVoltageCustom !== undefined) layer.powerVoltageCustom = layerProps.powerVoltageCustom;
                        if (layerProps.powerAmperage !== undefined) layer.powerAmperage = layerProps.powerAmperage;
                        if (layerProps.powerAmperageCustom !== undefined) layer.powerAmperageCustom = layerProps.powerAmperageCustom;
                        if (layerProps.panelWatts !== undefined) layer.panelWatts = layerProps.panelWatts;
                        if (layerProps.powerMaximize !== undefined) layer.powerMaximize = layerProps.powerMaximize;
                        if (layerProps.powerOrganized !== undefined) layer.powerOrganized = layerProps.powerOrganized;
                        if (layerProps.powerCustomPath !== undefined) layer.powerCustomPath = layerProps.powerCustomPath;
                        if (layerProps.powerFlowPattern !== undefined) layer.powerFlowPattern = layerProps.powerFlowPattern;
                        if (layerProps.powerLineWidth !== undefined) layer.powerLineWidth = layerProps.powerLineWidth;
                        if (layerProps.powerLineColor !== undefined) layer.powerLineColor = layerProps.powerLineColor;
                        if (layerProps.powerArrowColor !== undefined) layer.powerArrowColor = layerProps.powerArrowColor;
                        if (layerProps.powerRandomColors !== undefined) layer.powerRandomColors = layerProps.powerRandomColors;
                        if (layerProps.powerColorCodedView !== undefined) layer.powerColorCodedView = layerProps.powerColorCodedView;
                        if (layerProps.powerCircuitColors !== undefined) layer.powerCircuitColors = layerProps.powerCircuitColors;
                        if (layerProps.powerLabelSize !== undefined) layer.powerLabelSize = layerProps.powerLabelSize;
                        if (layerProps.powerLabelBgColor !== undefined) layer.powerLabelBgColor = layerProps.powerLabelBgColor;
                        if (layerProps.powerLabelTextColor !== undefined) layer.powerLabelTextColor = layerProps.powerLabelTextColor;
                        if (layerProps.powerLabelTemplate !== undefined) layer.powerLabelTemplate = layerProps.powerLabelTemplate;
                        if (layerProps.powerLabelOverrides !== undefined) layer.powerLabelOverrides = layerProps.powerLabelOverrides;
                        if (layerProps.powerCustomPaths !== undefined) layer.powerCustomPaths = layerProps.powerCustomPaths;
                        if (layerProps.powerCustomIndex !== undefined) layer.powerCustomIndex = layerProps.powerCustomIndex;
                        if (layerProps.border_color_pixel !== undefined) layer.border_color_pixel = layerProps.border_color_pixel;
                        if (layerProps.border_color_cabinet !== undefined) layer.border_color_cabinet = layerProps.border_color_cabinet;
                        if (layerProps.border_color_data !== undefined) layer.border_color_data = layerProps.border_color_data;
                        if (layerProps.border_color_power !== undefined) layer.border_color_power = layerProps.border_color_power;
                        if (layerProps.weight_unit !== undefined) layer.weight_unit = layerProps.weight_unit;
                        if (layerProps.panel_weight !== undefined) layer.panel_weight = layerProps.panel_weight;
                        if (layerProps.infoLabelSize !== undefined) layer.infoLabelSize = layerProps.infoLabelSize;
                        if (layerProps.screenNameSizeCabinet !== undefined) layer.screenNameSizeCabinet = layerProps.screenNameSizeCabinet;
                        if (layerProps.screenNameSizeDataFlow !== undefined) layer.screenNameSizeDataFlow = layerProps.screenNameSizeDataFlow;
                        if (layerProps.screenNameSizePower !== undefined) layer.screenNameSizePower = layerProps.screenNameSizePower;
                        if (layerProps.showDataFlowPortInfo !== undefined) layer.showDataFlowPortInfo = layerProps.showDataFlowPortInfo;
                        if (layerProps.showPowerCircuitInfo !== undefined) layer.showPowerCircuitInfo = layerProps.showPowerCircuitInfo;
                        if (layerProps.screenNameOffsetXPixelMap !== undefined) layer.screenNameOffsetXPixelMap = layerProps.screenNameOffsetXPixelMap;
                        if (layerProps.screenNameOffsetYPixelMap !== undefined) layer.screenNameOffsetYPixelMap = layerProps.screenNameOffsetYPixelMap;
                        if (layerProps.screenNameOffsetXCabinet !== undefined) layer.screenNameOffsetXCabinet = layerProps.screenNameOffsetXCabinet;
                        if (layerProps.screenNameOffsetYCabinet !== undefined) layer.screenNameOffsetYCabinet = layerProps.screenNameOffsetYCabinet;
                        if (layerProps.screenNameOffsetXDataFlow !== undefined) layer.screenNameOffsetXDataFlow = layerProps.screenNameOffsetXDataFlow;
                        if (layerProps.screenNameOffsetYDataFlow !== undefined) layer.screenNameOffsetYDataFlow = layerProps.screenNameOffsetYDataFlow;
                        if (layerProps.screenNameOffsetXPower !== undefined) layer.screenNameOffsetXPower = layerProps.screenNameOffsetXPower;
                        if (layerProps.screenNameOffsetYPower !== undefined) layer.screenNameOffsetYPower = layerProps.screenNameOffsetYPower;
                        if (layerProps.screenNameOffsetXShowLook !== undefined) layer.screenNameOffsetXShowLook = layerProps.screenNameOffsetXShowLook;
                        if (layerProps.screenNameOffsetYShowLook !== undefined) layer.screenNameOffsetYShowLook = layerProps.screenNameOffsetYShowLook;
                        if (layerProps.gradientEnabled !== undefined) layer.gradientEnabled = layerProps.gradientEnabled;
                        if (layerProps.transparentFill !== undefined) layer.transparentFill = layerProps.transparentFill;
                        if (layerProps.rotation !== undefined) layer.rotation = layerProps.rotation;
                        if (layerProps.gradientType !== undefined) layer.gradientType = layerProps.gradientType;
                        if (layerProps.gradientScope !== undefined) layer.gradientScope = layerProps.gradientScope;
                        if (layerProps.gradientPanelAlternate !== undefined) layer.gradientPanelAlternate = layerProps.gradientPanelAlternate;
                        if (layerProps.gradientRadialCenterX !== undefined) layer.gradientRadialCenterX = layerProps.gradientRadialCenterX;
                        if (layerProps.gradientRadialCenterY !== undefined) layer.gradientRadialCenterY = layerProps.gradientRadialCenterY;
                        if (layerProps.gradientRadialRadius !== undefined) layer.gradientRadialRadius = layerProps.gradientRadialRadius;
                        if (layerProps.gradientAngle !== undefined) layer.gradientAngle = layerProps.gradientAngle;
                        if (layerProps.gradientOpacity !== undefined) layer.gradientOpacity = layerProps.gradientOpacity;
                        if (layerProps.gradientBlend !== undefined) layer.gradientBlend = layerProps.gradientBlend;
                        if (Array.isArray(layerProps.gradientStops)) layer.gradientStops = layerProps.gradientStops.map(s => ({ pos: s.pos, color: s.color }));
                        if (layerProps.panelColorMode !== undefined) layer.panelColorMode = layerProps.panelColorMode;
                        if (Array.isArray(layerProps.panelColors)) layer.panelColors = layerProps.panelColors.slice();
                    }
                });
            } catch (e) {
                console.error('Error loading client-side properties:', e);
            }
        } else if (savedProps) {
            // Avoid cross-project contamination from id-based local props.
            sendClientLog('skip_saved_client_props', {
                projectName: this.project && this.project.name,
                layerCount: this.project && this.project.layers ? this.project.layers.length : 0
            });
        }
        
        // Then, initialize defaults for any properties that are still undefined
        this.project.layers.forEach(layer => {
            if (layer.arrowLineWidth === undefined) layer.arrowLineWidth = 4;
            if (layer.arrowColor === undefined) layer.arrowColor = '#0042AA';
            if (layer.dataFlowColor === undefined) layer.dataFlowColor = '#FFFFFF';
            if (layer.dataFlowLabelSize === undefined) layer.dataFlowLabelSize = prefs.dataLabelSize || 30;
            if (layer.primaryColor === undefined) layer.primaryColor = '#00FF00';
            if (layer.primaryTextColor === undefined) layer.primaryTextColor = '#000000';
            if (layer.backupColor === undefined) layer.backupColor = '#FF0000';
            if (layer.backupTextColor === undefined) layer.backupTextColor = '#FFFFFF';
            if (layer.flowPattern === undefined) layer.flowPattern = prefs.flowPattern || 'tl-h';
            if (layer.bitDepth === undefined) layer.bitDepth = prefs.bitDepth;
            if (layer.frameRate === undefined) layer.frameRate = prefs.frameRate;
            if (layer.processorType === undefined) layer.processorType = prefs.processorType;
            if (layer.processorType === 'novastar-1g') layer.processorType = 'novastar-coex-1g';
            if (layer.processorType === 'novastar-armor-1g') layer.processorType = 'novastar-armor';
            if (layer.portMappingMode === undefined) layer.portMappingMode = 'organized';
            if (layer.portLabelTemplatePrimary === undefined) layer.portLabelTemplatePrimary = 'P#';
            if (layer.portLabelTemplateReturn === undefined) layer.portLabelTemplateReturn = 'R#';
            if (typeof layer.portLabelTemplatePrimary === 'string' && layer.portLabelTemplatePrimary.includes('{n}')) {
                layer.portLabelTemplatePrimary = layer.portLabelTemplatePrimary.replace('{n}', '#');
            }
            if (typeof layer.portLabelTemplateReturn === 'string' && layer.portLabelTemplateReturn.includes('{n}')) {
                layer.portLabelTemplateReturn = layer.portLabelTemplateReturn.replace('{n}', '#');
            }
            if (layer.portLabelOverridesPrimary === undefined) layer.portLabelOverridesPrimary = {};
            if (layer.portLabelOverridesReturn === undefined) layer.portLabelOverridesReturn = {};
            if (layer.customPortPaths === undefined) layer.customPortPaths = {};
            if (layer.customPortIndex === undefined) layer.customPortIndex = 1;
            if (layer.screenNameSizeCabinet === undefined) layer.screenNameSizeCabinet = 14;
            if (layer.screenNameSizeDataFlow === undefined) layer.screenNameSizeDataFlow = 14;
            if (layer.screenNameSizePower === undefined) layer.screenNameSizePower = 14;
            if (layer.powerVoltage === undefined) layer.powerVoltage = prefs.powerVoltage;
            if (layer.powerVoltageCustom === undefined) layer.powerVoltageCustom = prefs.powerVoltage;
            if (layer.powerAmperage === undefined) layer.powerAmperage = prefs.powerAmperage;
            if (layer.powerAmperageCustom === undefined) layer.powerAmperageCustom = prefs.powerAmperage;
            if (layer.panelWatts === undefined) layer.panelWatts = prefs.powerWatts;
            if (layer.powerMaximize === undefined) layer.powerMaximize = false;
            if (layer.powerOrganized === undefined) layer.powerOrganized = true;
            if (layer.powerCustomPath === undefined) layer.powerCustomPath = false;
            if (layer.powerFlowPattern === undefined || layer.powerFlowPattern === null || layer.powerFlowPattern === '') {
                layer.powerFlowPattern = layer.flowPattern || prefs.powerFlowPattern || 'tl-h';
            }
            if (layer.powerLineWidth === undefined) layer.powerLineWidth = 8;
            if (layer.powerLineColor === undefined) layer.powerLineColor = '#FF0000';
            if (layer.powerArrowColor === undefined) layer.powerArrowColor = '#0042AA';
            if (layer.powerRandomColors === undefined) layer.powerRandomColors = false;
            if (layer.powerColorCodedView === undefined) layer.powerColorCodedView = false;
            layer.powerCircuitColors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
            if (layer.powerLabelSize === undefined) layer.powerLabelSize = prefs.powerLabelSize || 14;
            if (layer.powerLabelBgColor === undefined) layer.powerLabelBgColor = '#D95000';
            if (layer.powerLabelTextColor === undefined) layer.powerLabelTextColor = '#000000';
            if (layer.powerLabelTemplate === undefined) layer.powerLabelTemplate = 'S1-#';
            if (layer.powerLabelOverrides === undefined) layer.powerLabelOverrides = {};
                if (layer.powerCustomPaths === undefined) layer.powerCustomPaths = {};
            if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
            if (layer.halfFirstColumn === undefined) layer.halfFirstColumn = false;
            if (layer.halfLastColumn === undefined) layer.halfLastColumn = false;
            if (layer.halfFirstRow === undefined) layer.halfFirstRow = false;
            if (layer.halfLastRow === undefined) layer.halfLastRow = false;
            if (layer.weight_unit === undefined) layer.weight_unit = prefs.weightUnit || 'kg';
            if (layer.panel_weight === undefined) layer.panel_weight = prefs.panelWeight || 20;
            if (layer.infoLabelSize === undefined) layer.infoLabelSize = 14;
            if (layer.showDataFlowPortInfo === undefined) layer.showDataFlowPortInfo = false;
            if (layer.showPowerCircuitInfo === undefined) layer.showPowerCircuitInfo = false;
            // Show Look position, default to processor offset for older
            // projects so they open looking identical to before.
            if (layer.showOffsetX === undefined || layer.showOffsetX === null) {
                layer.showOffsetX = layer.offset_x || 0;
            }
            if (layer.showOffsetY === undefined || layer.showOffsetY === null) {
                layer.showOffsetY = layer.offset_y || 0;
            }
        });

        // For startup factory-default project only, enforce saved preference defaults.
        // Skip if preferences were already applied this session (e.g. socket reconnect after sleep).
        // Use server-side is_pristine flag to distinguish a true fresh default project from a
        // loaded project that happens to be named "Untitled Project".
        const startupDefaultMatch =
            !skipPreferences &&
            this.project &&
            this.project.is_pristine === true &&
            this.project.name === 'Untitled Project' &&
            this.project.layers &&
            this.project.layers.length === 1;
        if (startupDefaultMatch) {
            const layer = this.project.layers[0];
            layer.processorType = prefs.processorType;
            layer.bitDepth = prefs.bitDepth;
            layer.frameRate = prefs.frameRate;
            layer.powerVoltage = prefs.powerVoltage;
            layer.powerVoltageCustom = prefs.powerVoltage;
            layer.powerAmperage = prefs.powerAmperage;
            layer.powerAmperageCustom = prefs.powerAmperage;
            layer.panelWatts = prefs.powerWatts;
            layer.dataFlowLabelSize = prefs.dataLabelSize || 30;
            layer.powerLabelSize = prefs.powerLabelSize || 14;
            layer.primaryTextColor = layer.primaryTextColor || '#000000';
            layer.backupTextColor = layer.backupTextColor || '#FFFFFF';
            layer.powerLabelBgColor = layer.powerLabelBgColor || '#D95000';
            layer.powerLabelTextColor = layer.powerLabelTextColor || '#000000';
            layer.panel_weight = prefs.panelWeight || 20;
            layer.weight_unit = prefs.weightUnit || 'kg';
            // Apply default raster on startup so app open matches Preferences.
            // Both the Pixel Map raster AND the Show Look raster start at the
            // preference size (a new project's Show Look should match, not the
            // server's 1080p default).
            this.project.raster_width = prefs.rasterWidth;
            this.project.raster_height = prefs.rasterHeight;
            this.project.show_raster_width = prefs.rasterWidth;
            this.project.show_raster_height = prefs.rasterHeight;
            if (window.canvasRenderer) {
                window.canvasRenderer.pixelRasterWidth = prefs.rasterWidth;
                window.canvasRenderer.pixelRasterHeight = prefs.rasterHeight;
                window.canvasRenderer.showRasterWidth = prefs.rasterWidth;
                window.canvasRenderer.showRasterHeight = prefs.rasterHeight;
            }
            const rw = document.getElementById('toolbar-raster-width');
            const rh = document.getElementById('toolbar-raster-height');
            if (rw) rw.value = prefs.rasterWidth;
            if (rh) rh.value = prefs.rasterHeight;
            this.saveRasterSize();
            // Sync raster size to server so subsequent socket project_data
            // echoes return the preference values, not the server default.
            fetch('/api/project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    raster_width: prefs.rasterWidth,
                    raster_height: prefs.rasterHeight,
                    show_raster_width: prefs.rasterWidth,
                    show_raster_height: prefs.rasterHeight
                })
            });
            sendClientLog('startup_preferences_enforced', {
                processorType: layer.processorType,
                bitDepth: layer.bitDepth,
                frameRate: layer.frameRate,
                powerVoltage: layer.powerVoltage,
                powerAmperage: layer.powerAmperage,
                panelWatts: layer.panelWatts,
                rasterWidth: this.project.raster_width,
                rasterHeight: this.project.raster_height
            });
        }

        console.log('LOADED CLIENT PROPS - first layer:', {
            arrowLineWidth: this.project.layers[0]?.arrowLineWidth,
            arrowColor: this.project.layers[0]?.arrowColor,
            dataFlowLabelSize: this.project.layers[0]?.dataFlowLabelSize
        });
    }
    
    // Save client-side properties to localStorage
    saveClientSideProperties() {
        if (!this.project || !this.project.layers) return;
        
        const propsMap = {};
        
        this.project.layers.forEach(layer => {
            propsMap[layer.id] = {
                // Data Flow properties
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
                portMappingMode: layer.portMappingMode,
                portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
                portLabelTemplateReturn: layer.portLabelTemplateReturn,
                portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
                portLabelOverridesReturn: layer.portLabelOverridesReturn,
                customPortPaths: layer.customPortPaths,
                customPortIndex: layer.customPortIndex,
                screenNameSizeCabinet: layer.screenNameSizeCabinet,
                screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
                screenNameSizePower: layer.screenNameSizePower,
                
                // Tab-specific screen name positions
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
            gradientRadialCenterX: layer.gradientRadialCenterX,
            gradientRadialCenterY: layer.gradientRadialCenterY,
            gradientRadialRadius: layer.gradientRadialRadius,
            gradientPanelAlternate: layer.gradientPanelAlternate,
            gradientRadialCenterX: layer.gradientRadialCenterX,
            gradientRadialCenterY: layer.gradientRadialCenterY,
            gradientRadialRadius: layer.gradientRadialRadius,
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
            panelColorMode: layer.panelColorMode,
            panelColors: layer.panelColors,
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
                powerCustomPaths: layer.powerCustomPaths,
                powerCustomIndex: layer.powerCustomIndex,
                border_color_pixel: layer.border_color_pixel,
                border_color_cabinet: layer.border_color_cabinet,
                border_color_data: layer.border_color_data,
                border_color_power: layer.border_color_power,
                weight_unit: layer.weight_unit,
                panel_weight: layer.panel_weight,
                infoLabelSize: layer.infoLabelSize,
                showDataFlowPortInfo: layer.showDataFlowPortInfo,
                showPowerCircuitInfo: layer.showPowerCircuitInfo,
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
                fontUnderline: layer.fontUnderline
            };
        });

        localStorage.setItem('ledRasterClientProps', JSON.stringify(propsMap));
    }
    
    // Save raster size to localStorage
    saveRasterSize() {
        const rasterSize = {
            width: window.canvasRenderer.rasterWidth,
            height: window.canvasRenderer.rasterHeight
        };
        localStorage.setItem('ledRasterSize', JSON.stringify(rasterSize));
    }

    /**
     * Slice 6: refresh the toolbar Raster: W x H inputs from the active
     * canvas's raster (Pixel Map raster on pixel-map / cabinet-id, Show
     * Look raster on show-look / data / power). Also seeds any missing
     * show_raster_* on the active canvas so older projects (where show
     * raster was never set) open with show = pixel.
     *
     * Renderer fields are accessor-backed (Slice 6), they read straight
     * from the active canvas, so no per-renderer assignment is needed.
     * Legacy fallback (no canvases array): seed the renderer's _fallback*
     * backing fields from the project root so single-canvas pre-Slice-1
     * projects still display.
     */
    syncRasterFromProject() {
        if (!this.project) return;
        const r = window.canvasRenderer;
        if (!r) return;
        const canvases = Array.isArray(this.project.canvases) ? this.project.canvases : [];
        if (canvases.length > 0) {
            const c = canvases.find(x => x.id === this.project.active_canvas_id) || canvases[0];
            if (c) {
                if (!c.show_raster_width)  c.show_raster_width  = c.raster_width;
                if (!c.show_raster_height) c.show_raster_height = c.raster_height;
            }
        } else {
            // Pre-Slice-1 project, seed the renderer's fallback backing
            // fields so the legacy single-canvas getter path returns sane
            // values until the project gets migrated by the server.
            const pw = Number(this.project.raster_width) || 1920;
            const ph = Number(this.project.raster_height) || 1080;
            const sw = Number(this.project.show_raster_width) || pw;
            const sh = Number(this.project.show_raster_height) || ph;
            r._fallbackPixelRasterWidth = pw;
            r._fallbackPixelRasterHeight = ph;
            r._fallbackShowRasterWidth = sw;
            r._fallbackShowRasterHeight = sh;
        }
        const rwIn = document.getElementById('toolbar-raster-width');
        const rhIn = document.getElementById('toolbar-raster-height');
        if (rwIn) rwIn.value = r.rasterWidth;
        if (rhIn) rhIn.value = r.rasterHeight;
    }
    
    // Load raster size from localStorage (checks version first).
    //
    // Slice 6: at boot the project hasn't loaded yet, the active canvas's
    // raster is the source of truth and we must NOT clobber it with stale
    // localStorage. So we only seed the renderer's fallback backing fields
    // (used when no canvases array exists yet) and refresh the toolbar
    // inputs. Once loadProject() runs, syncRasterFromProject() takes over
    // and the toolbar reflects the active canvas.
    loadRasterSize() {
        const savedVersion = localStorage.getItem('ledRasterPropsVersion');
        const currentVersion = '0.4.7';

        const seed = (w, h) => {
            const r = window.canvasRenderer;
            if (!r) return;
            r._fallbackPixelRasterWidth = w;
            r._fallbackPixelRasterHeight = h;
            r._fallbackShowRasterWidth = w;
            r._fallbackShowRasterHeight = h;
            const wIn = document.getElementById('toolbar-raster-width');
            const hIn = document.getElementById('toolbar-raster-height');
            if (wIn) wIn.value = w;
            if (hIn) hIn.value = h;
        };

        if (savedVersion !== currentVersion) {
            console.log('Version mismatch in loadRasterSize - clearing ALL localStorage');
            localStorage.removeItem('ledRasterSize');
            localStorage.removeItem('ledRasterClientProps');
            localStorage.setItem('ledRasterPropsVersion', currentVersion);
            const prefs = this.getPreferences();
            seed(prefs.rasterWidth, prefs.rasterHeight);
            this.saveRasterSize();
            return;
        }

        const saved = localStorage.getItem('ledRasterSize');
        if (saved) {
            try {
                const size = JSON.parse(saved);
                if (size.width && size.height) seed(size.width, size.height);
            } catch (e) {
                console.error('Error loading raster size:', e);
            }
        } else {
            const prefs = this.getPreferences();
            seed(prefs.rasterWidth, prefs.rasterHeight);
            this.saveRasterSize();
        }
    }
    
    /**
     * Clean-slate reset before loading a new project or creating a new one.
     * Clears selection state, stale client props, and undo history so that
     * sidebar inputs cannot leak old values into the incoming project.
     */
    resetApplicationState() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        localStorage.removeItem('ledRasterClientProps');
        this.resetHistory('Initial State');
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

                // Save the default raster size to localStorage
                // This way refresh after "New" will show defaults
                this.saveRasterSize();
                // Persist both rasters to the server so the Show Look raster
                // doesn't snap back to the default on the next project echo.
                fetch('/api/project', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        raster_width: prefs.rasterWidth,
                        raster_height: prefs.rasterHeight,
                        show_raster_width: prefs.rasterWidth,
                        show_raster_height: prefs.rasterHeight
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
        this.currentLayer.color1 = this.hexToRgb(prefs.color1);
        this.currentLayer.color2 = this.hexToRgb(prefs.color2);
        this.currentLayer.border_color = prefs.borderColor;
        this.currentLayer.border_color_pixel = prefs.borderColor;
        this.currentLayer.border_color_cabinet = prefs.borderColor;
        this.currentLayer.border_color_data = prefs.borderColor;
        this.currentLayer.border_color_power = prefs.borderColor;
        this.currentLayer.flowPattern = prefs.flowPattern;
        this.currentLayer.arrowLineWidth = prefs.dataLineWidth;
        this.currentLayer.dataFlowLabelSize = prefs.dataLabelSize;
        this.currentLayer.powerLineWidth = prefs.powerLineWidth;
        this.currentLayer.powerLabelSize = prefs.powerLabelSize;
        this.currentLayer.primaryTextColor = this.currentLayer.primaryTextColor || '#000000';
        this.currentLayer.backupTextColor = this.currentLayer.backupTextColor || '#FFFFFF';
        this.currentLayer.powerLabelBgColor = this.currentLayer.powerLabelBgColor || '#D95000';
        this.currentLayer.powerLabelTextColor = this.currentLayer.powerLabelTextColor || '#000000';
        this.currentLayer.processorType = prefs.processorType;
        this.currentLayer.bitDepth = prefs.bitDepth;
        this.currentLayer.frameRate = prefs.frameRate;
        this.currentLayer.powerVoltage = prefs.powerVoltage;
        this.currentLayer.powerVoltageCustom = prefs.powerVoltage;
        this.currentLayer.powerAmperage = prefs.powerAmperage;
        this.currentLayer.powerAmperageCustom = prefs.powerAmperage;
        this.currentLayer.panelWatts = prefs.powerWatts;
        this.currentLayer.powerFlowPattern = prefs.powerFlowPattern || 'tl-h';
        this.loadLayerToInputs();
        this.updateLayer();
    }

    isFactoryDefaultLayer(layer) {
        if (!layer) return false;
        return (
            (layer.name || '') === 'Screen1' &&
            (Number(layer.columns) || 0) === 8 &&
            (Number(layer.rows) || 0) === 5 &&
            (Number(layer.cabinet_width) || 0) === 128 &&
            (Number(layer.cabinet_height) || 0) === 128 &&
            (Number(layer.offset_x) || 0) === 0 &&
            (Number(layer.offset_y) || 0) === 0 &&
            !layer.halfFirstColumn &&
            !layer.halfLastColumn &&
            !layer.halfFirstRow &&
            !layer.halfLastRow
        );
    }

    shouldApplyStartupPreferences() {
        if (!this.project || !this.project.layers || this.project.layers.length !== 1) return false;
        if (!this.currentLayer) return false;
        if (this.project.is_pristine !== true) return false;
        if (this.project.name !== 'Untitled Project') return false;
        return true;
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
        buildPerCanvas('power-totals-per-canvas', (cid) => {
            const p = this.getPowerCounts(cid);
            return [
                ['Watts', fmtWatts(p.totalWatts)],
                ['Circuits', p.circuits],
                ['Amps (1φ)', fmtAmps(p.singlePhaseAmps)],
                ['Amps (3φ)', fmtAmps(p.threePhaseAmps)],
            ];
        });
        const pwrProject = this.getPowerCounts();
        setText('power-totals-project-watts', fmtWatts(pwrProject.totalWatts));
        setText('power-totals-project-circuits', pwrProject.circuits);
        setText('power-totals-project-1ph', fmtAmps(pwrProject.singlePhaseAmps));
        setText('power-totals-project-3ph', fmtAmps(pwrProject.threePhaseAmps));
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

    setupEventListeners() {
        this.setupPixelMapBulkActions();
        this.setupPerspectiveToggles();
        // Project name editing
        const projectNameInput = document.getElementById('project-name');
        const projectNameWarning = document.getElementById('project-name-warning');
        const updateProjectNameWarning = () => {
            if (!projectNameWarning) return;
            const v = projectNameInput.value || '';
            const bad = v.match(/[\\/:*?"<>|]/g);
            if (bad && bad.length > 0) {
                const unique = [...new Set(bad)].join(' ');
                projectNameWarning.textContent = `Note: ${unique} will be replaced with _ in exported filenames.`;
                projectNameWarning.style.display = 'block';
            } else {
                projectNameWarning.style.display = 'none';
            }
        };
        if (projectNameInput) {
            projectNameInput.addEventListener('input', updateProjectNameWarning);
            projectNameInput.addEventListener('change', () => {
                if (this.project) {
                    this.project.name = projectNameInput.value.trim() || 'Untitled Project';
                    this.saveProject();
                    this.saveState('Rename Project');
                }
                updateProjectNameWarning();
            });
            // Run once on init in case a loaded project has illegal chars
            updateProjectNameWarning();
        }
        
        // Project Notes
        const notesTextarea = document.getElementById('project-notes');
        const notesToggle = document.getElementById('notes-toggle');
        const notesPanel = document.getElementById('notes-panel');
        if (notesTextarea) {
            notesTextarea.addEventListener('input', () => {
                if (this.project) {
                    this.project.notes = notesTextarea.value;
                    this.saveProject();
                    this.debouncedSaveState('Edit Notes', 500, 'project-notes');
                }
            });
        }
        if (notesToggle && notesPanel) {
            const NOTES_COLLAPSE_KEY = 'ledRasterPanelCollapsed_notes';
            const applyNotes = (collapsed) => {
                notesPanel.classList.toggle('collapsed', collapsed);
                notesToggle.textContent = collapsed ? '▶' : '▼';
            };
            const toggleNotes = () => {
                const collapsed = !notesPanel.classList.contains('collapsed');
                applyNotes(collapsed);
                localStorage.setItem(NOTES_COLLAPSE_KEY, collapsed ? '1' : '0');
            };
            // Restore last session's state so a refresh keeps the panel as
            // the user left it (defaults to collapsed via the HTML class).
            if (localStorage.getItem(NOTES_COLLAPSE_KEY) === '0') applyNotes(false);
            notesToggle.addEventListener('click', (e) => { e.stopPropagation(); toggleNotes(); });
            document.getElementById('notes-panel-header').addEventListener('click', toggleNotes);
        }

        // Help panel, same collapse pattern as Notes. Defaults to collapsed
        // so the layer-groups list above gets the spare space; user can
        // expand on demand via the header.
        const helpPanel = document.getElementById('help-tooltip-panel');
        const helpHeader = document.getElementById('help-tooltip-header');
        const helpToggle = document.getElementById('help-tooltip-toggle');
        if (helpPanel && helpHeader && helpToggle) {
            const HELP_COLLAPSE_KEY = 'ledRasterPanelCollapsed_help';
            const applyHelp = (collapsed) => {
                helpPanel.classList.toggle('collapsed', collapsed);
                helpToggle.textContent = collapsed ? '▶' : '▼';
            };
            const toggleHelp = () => {
                const collapsed = !helpPanel.classList.contains('collapsed');
                applyHelp(collapsed);
                localStorage.setItem(HELP_COLLAPSE_KEY, collapsed ? '1' : '0');
            };
            // Restore last session's state so a refresh keeps the panel as
            // the user left it.
            if (localStorage.getItem(HELP_COLLAPSE_KEY) === '0') applyHelp(false);
            helpToggle.addEventListener('click', (e) => { e.stopPropagation(); toggleHelp(); });
            helpHeader.addEventListener('click', toggleHelp);
        }

        // View tabs
        document.querySelectorAll('.view-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const mode = tab.getAttribute('data-mode');
                
                // Show/hide appropriate sidebar panels
                document.querySelectorAll('.tab-panel').forEach(panel => {
                    if (panel.getAttribute('data-tab') === mode) {
                        panel.style.display = 'block';
                    } else {
                        panel.style.display = 'none';
                    }
                });
                
                window.canvasRenderer.setViewMode(mode);
                // v0.8.6.1: re-render the Screens sidebar so groups reflect
                // the view-effective canvas (Show Look groups by
                // show_canvas_id; Pixel Map groups by canvas_id).
                if (typeof this.renderLayers === 'function') {
                    try { this.renderLayers(); } catch (_) {}
                }
                // Recompute the Data/Power Totals now that the view (and thus
                // the show-canvas grouping) has changed. Without this the
                // per-canvas totals keep the previous tab's grouping and
                // collapse every screen onto its processor canvas (canvas_id),
                // so canvases that only host screens via show_canvas_id read 0.
                if (typeof this.refreshTotalsSidebar === 'function') {
                    try { this.refreshTotalsSidebar(); } catch (_) {}
                }
                sendClientLog('tab_switch', {
                    tab: mode,
                    currentLayer: this.currentLayer ? { id: this.currentLayer.id, name: this.currentLayer.name } : null,
                    selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : []
                });
                this.updateLayerPanelVisibility(
                    !!this.currentLayer && (this.currentLayer.type || 'screen') === 'image',
                    !!this.currentLayer && (this.currentLayer.type || 'screen') === 'text'
                );
                this.loadLayerToInputs();
                this.loadTextLayerToInputs();
                if (mode === 'data-flow' && this.currentLayer) {
                    this.updatePortCapacityDisplay();
                    this.updatePortLabelEditor();
                    this.updateCustomFlowUI();
                    // Defer a second refresh to ensure DOM is fully painted
                    setTimeout(() => {
                        if (this.currentLayer) {
                            this.updatePortCapacityDisplay();
                            this.updatePortLabelEditor();
                        }
                    }, 50);
                } else if (mode === 'power' && this.currentLayer) {
                    this.updatePowerCapacityDisplay();
                    this.updateCustomPowerUI();
                    this.updatePowerLabelEditor();
                    setTimeout(() => {
                        if (this.currentLayer) {
                            this.updatePowerCapacityDisplay();
                            this.updatePowerLabelEditor();
                        }
                    }, 50);
                }
            });
        });

        // v0.8 Slice 2.5: the global "+ Add Screen / + Add Image / + Add Text"
        // and "▲ Up / ▼ Down" buttons were removed. Per-canvas "+ Add" chooser
        // (built in buildCanvasGroupEl) and per-layer ▲▼ arrows now own those
        // affordances. We still wire the file-input change handler because
        // the per-canvas "Image / Logo" chooser entry reuses it.
        const addCanvasBtn = document.getElementById('btn-add-canvas');
        if (addCanvasBtn) {
            addCanvasBtn.addEventListener('click', () => this.addCanvas());
        }
        const savePresetBtn = document.getElementById('btn-save-preset');
        if (savePresetBtn) {
            savePresetBtn.addEventListener('click', () => this.openPresetSaveModal());
        }
        this.setupPresetModals();
        const addImageInput = document.getElementById('add-image-input');
        if (addImageInput) {
            addImageInput.addEventListener('change', (e) => {
                this.handleImageFileSelection(e);
            });
        }
        const replaceImageBtn = document.getElementById('btn-replace-image');
        if (replaceImageBtn && addImageInput) {
            replaceImageBtn.addEventListener('click', () => {
                if (!this.currentLayer || this.currentLayer.type !== 'image') return;
                this.imageFileAction = 'replace';
                addImageInput.click();
            });
        }

        // Text layer sidebar controls
        this.setupTextLayerControls();

        const toggleLockBtn = document.getElementById('toggle-lock-selected');
        if (toggleLockBtn) {
            toggleLockBtn.addEventListener('click', () => {
                this.toggleLockOnSelected();
            });
        }
        
        document.getElementById('btn-zoom-in').addEventListener('click', () => {
            window.canvasRenderer.zoomIn();
        });
        document.getElementById('btn-zoom-out').addEventListener('click', () => {
            window.canvasRenderer.zoomOut();
        });
        document.getElementById('btn-fit').addEventListener('click', () => {
            window.canvasRenderer.fitToView();
        });
        document.getElementById('btn-zoom-actual').addEventListener('click', () => {
            window.canvasRenderer.zoomActual();
        });
        
        // Zoom level input - allow typing a percentage
        const zoomInput = document.getElementById('zoom-level');
        zoomInput.addEventListener('change', () => {
            let value = zoomInput.value.replace('%', '').trim();
            let percent = parseFloat(value);
            if (!isNaN(percent) && percent > 0) {
                // Convert displayed percent (1:1 device-pixel based) into the
                // internal raster→CSS scale used by canvasRenderer.
                const targetZoom = (typeof window.canvasRenderer._percentToZoom === 'function')
                    ? window.canvasRenderer._percentToZoom(percent)
                    : percent / 100;
                window.canvasRenderer.setZoom(targetZoom);
            }
            const displayed = (typeof window.canvasRenderer._zoomToPercent === 'function')
                ? window.canvasRenderer._zoomToPercent(window.canvasRenderer.zoom)
                : Math.round(window.canvasRenderer.zoom * 100);
            zoomInput.value = `${displayed}%`;
        });
        zoomInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                zoomInput.blur();
            }
        });
        
        // Magnetic snap toggle
        document.getElementById('magnetic-snap').addEventListener('change', (e) => {
            window.canvasRenderer.magneticSnap = e.target.checked;
        });
        
        ['offset-x', 'offset-y', 'cabinet-width', 'cabinet-height',
         'screen-columns', 'screen-rows', 'number-size', 'panel-width-mm', 'panel-height-mm', 'panel-weight-kg', 'image-scale', 'image-scale-range',
         'show-offset-x', 'show-offset-y',
         'size-by-dimensions', 'target-width', 'target-height', 'target-unit'].forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this._lastChangedInputId = id;
                        this.updateLayerFromInputs();
                        this._lastChangedInputId = null;
                    }
                });
            }
        });

        // Show Look "Reset to Pixel Map Position" button
        const showResetBtn = document.getElementById('show-look-reset');
        if (showResetBtn) {
            showResetBtn.addEventListener('click', () => {
                const layers = this.getSelectedLayers ? this.getSelectedLayers() : (this.currentLayer ? [this.currentLayer] : []);
                if (layers.length === 0) return;
                // v0.10.5: snapshot AFTER the reset (see applyDisplayOrder);
                // taken before, Undo-then-Redo lost the reset.
                layers.forEach(l => {
                    l.showOffsetX = l.offset_x;
                    l.showOffsetY = l.offset_y;
                    // v0.8.5: also clear the Show Look canvas override so
                    // the layer falls back to mirroring its Pixel Map
                    // canvas membership (canvas_id).
                    l.show_canvas_id = null;
                });
                this.updateLayers(layers, false);
                // v0.8.5.2: also re-link the Show Look raster of every
                // canvas touched by these layers back to its Pixel Map
                // raster, so a single Reset click fully restores Show Look
                // to mirror Pixel Map (position + canvas membership +
                // raster size). Pushed via the canvas PUT endpoint.
                if (this.project && Array.isArray(this.project.canvases)
                        && typeof this.updateCanvas === 'function') {
                    const canvasIds = new Set();
                    layers.forEach(l => { if (l && l.canvas_id) canvasIds.add(l.canvas_id); });
                    canvasIds.forEach(cid => {
                        const c = this.project.canvases.find(x => x && x.id === cid);
                        if (!c) return;
                        const rw = Number(c.raster_width) || 0;
                        const rh = Number(c.raster_height) || 0;
                        const sw = Number(c.show_raster_width) || 0;
                        const sh = Number(c.show_raster_height) || 0;
                        const patch = {};
                        if (rw && rw !== sw) patch.show_raster_width = rw;
                        if (rh && rh !== sh) patch.show_raster_height = rh;
                        // v0.8.5.3: also re-link show workspace position to
                        // the Pixel Map workspace position (clear override).
                        if (c.show_workspace_x != null) {
                            c.show_workspace_x = null;
                            patch.show_workspace_x = null;
                        }
                        if (c.show_workspace_y != null) {
                            c.show_workspace_y = null;
                            patch.show_workspace_y = null;
                        }
                        if (Object.keys(patch).length === 0) return;
                        Object.assign(c, patch);
                        this.updateCanvas(cid, patch);
                    });
                }
                this.saveState('Reset Show Look Position');
                this.loadLayerToInputs();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        }
        // v0.8.5.2: project-wide Show Look reset. Resets EVERY layer's
        // showOffset to its offset_x/y, clears every show_canvas_id, and
        // re-links every canvas's show_raster_* to its raster_*, one
        // click puts the entire Show Look (and Data + Power, which render
        // at the show layout) back to mirroring Pixel Map.
        const showResetAllBtn = document.getElementById('show-look-reset-all');
        if (showResetAllBtn) {
            showResetAllBtn.addEventListener('click', () => {
                if (!this.project) return;
                // v0.10.5: snapshot AFTER the reset (see applyDisplayOrder);
                // taken before, Undo-then-Redo lost the reset.
                const allLayers = (this.project.layers || []).filter(
                    l => (l.type || 'screen') === 'screen'
                );
                allLayers.forEach(l => {
                    l.showOffsetX = l.offset_x;
                    l.showOffsetY = l.offset_y;
                    l.show_canvas_id = null;
                });
                if (allLayers.length > 0) this.updateLayers(allLayers, false);
                if (Array.isArray(this.project.canvases)
                        && typeof this.updateCanvas === 'function') {
                    this.project.canvases.forEach(c => {
                        if (!c) return;
                        const rw = Number(c.raster_width) || 0;
                        const rh = Number(c.raster_height) || 0;
                        const sw = Number(c.show_raster_width) || 0;
                        const sh = Number(c.show_raster_height) || 0;
                        const patch = {};
                        if (rw && rw !== sw) patch.show_raster_width = rw;
                        if (rh && rh !== sh) patch.show_raster_height = rh;
                        // v0.8.5.3: clear the Show Look workspace override
                        // so canvases visually re-pin to their Pixel Map
                        // positions in Show Look / Data / Power.
                        if (c.show_workspace_x != null) {
                            c.show_workspace_x = null;
                            patch.show_workspace_x = null;
                        }
                        if (c.show_workspace_y != null) {
                            c.show_workspace_y = null;
                            patch.show_workspace_y = null;
                        }
                        if (Object.keys(patch).length === 0) return;
                        Object.assign(c, patch);
                        this.updateCanvas(c.id, patch);
                    });
                }
                this.saveState('Reset Entire Show Look');
                this.loadLayerToInputs();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        }
        const imageScaleInput = document.getElementById('image-scale');
        const imageScaleRange = document.getElementById('image-scale-range');
        if (imageScaleInput && imageScaleRange) {
            const applyLiveScale = (value) => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'image') return;
                const pct = Math.max(10, Math.min(500, parseFloat(value) || 100));
                this.currentLayer.imageScale = pct / 100;
                window.canvasRenderer.render();
            };
            const commitScale = () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'image') return;
                this.updateLayers([this.currentLayer]);
                this.debouncedSaveState('Image Scale');
            };
            imageScaleInput.addEventListener('input', () => {
                const val = parseFloat(imageScaleInput.value);
                if (!Number.isNaN(val)) {
                    imageScaleRange.value = String(Math.max(10, Math.min(500, val)));
                    applyLiveScale(val);
                }
            });
            imageScaleInput.addEventListener('change', () => {
                commitScale();
            });
            imageScaleRange.addEventListener('input', () => {
                imageScaleInput.value = imageScaleRange.value;
                applyLiveScale(imageScaleRange.value);
            });
            imageScaleRange.addEventListener('change', () => {
                commitScale();
            });
        }
        
        const showNumbersCheck = document.getElementById('show-numbers');
        if (showNumbersCheck) {
            showNumbersCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        const panelWeightUnitInput = document.getElementById('panel-weight-unit');
        if (panelWeightUnitInput) {
            panelWeightUnitInput.addEventListener('change', () => {
                if (!this.currentLayer) return;
                const oldUnit = this.currentLayer.weight_unit || 'kg';
                const newUnit = panelWeightUnitInput.value || 'kg';
                if (oldUnit !== newUnit) {
                    const weightInput = document.getElementById('panel-weight-kg');
                    const currentValue = parseFloat(weightInput?.value || this.currentLayer.panel_weight || 0) || 0;
                    const converted = (oldUnit === 'kg' && newUnit === 'lb')
                        ? (currentValue * 2.20462)
                        : (oldUnit === 'lb' && newUnit === 'kg')
                            ? (currentValue / 2.20462)
                            : currentValue;
                    if (weightInput) {
                        weightInput.value = converted.toFixed(2);
                    }
                }
                this.updateLayerFromInputs();
            });
        }

        // (legacy half-* checkboxes removed; per-panel halfTile editing
        // replaces them via Alt+Shift+Click and the bulk action sidebar.)
        
        // Cabinet ID style radio buttons
        const cabinetIdStyleRadios = document.querySelectorAll('input[name="cabinet-id-style"]');
        cabinetIdStyleRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.cabinetIdStyle = radio.value;
                });
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Change Cabinet ID Style');
            });
        });

        // Cabinet ID position radio buttons
        const cabinetIdPositionRadios = document.querySelectorAll('input[name="cabinet-id-position"]');
        cabinetIdPositionRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.cabinetIdPosition = radio.value;
                });
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Change Cabinet ID Position');
            });
        });
        
        // Cabinet ID color with hex sync
        setupColorPickerWithHex('cabinet-id-color', 'cabinet-id-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.cabinetIdColor = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers(), true, 'Change Cabinet ID Color');
            }
            window.canvasRenderer.render();
        });
        
        // Border settings (Pixel Map tab)
        const showPanelBordersCheck = document.getElementById('show-panel-borders');
        if (showPanelBordersCheck) {
            showPanelBordersCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        const showCircleWithXCheck = document.getElementById('show-circle-with-x');
        if (showCircleWithXCheck) {
            showCircleWithXCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        // Border color with hex sync (Pixel Map)
        setupColorPickerWithHex('border-color', 'border-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_pixel = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers(), true, 'Change Border Color');
            }
            window.canvasRenderer.render();
        });
        
        // Labels color with hex sync
        setupColorPickerWithHex('labels-color', 'labels-color-hex', (val, isFinal) => {
            if (isFinal) {
                this.updateLayerFromInputs();
            } else {
                this.applyToSelectedLayers(layer => {
                    layer.labelsColor = val;
                });
                window.canvasRenderer.render();
            }
        });
        
        // Tab-specific border controls - Cabinet ID
        setupColorPickerWithHex('border-color-cabinet', 'border-color-cabinet-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_cabinet = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers(), true, 'Change Border Color');
            }
            window.canvasRenderer.render();
        });
        
        // Tab-specific border controls - Data Flow
        setupColorPickerWithHex('border-color-data', 'border-color-data-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_data = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers(), true, 'Change Border Color');
            }
            window.canvasRenderer.render();
        });
        
        // Tab-specific border controls - Power
        setupColorPickerWithHex('border-color-power', 'border-color-power-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_power = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers(), true, 'Change Border Color');
            }
            window.canvasRenderer.render();
        });
        
        // v0.8.8.x: per-layer panel border width, in LED pixels. One value
        // per layer; mirror it across the four tab inputs so editing it on
        // any tab updates the others.
        const BORDER_WIDTH_IDS = ['panel-border-width', 'panel-border-width-cabinet',
            'panel-border-width-data', 'panel-border-width-power'];
        BORDER_WIDTH_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => {
                let v = Math.round(Number(el.value));
                if (!Number.isFinite(v) || v < 1) v = 1;
                if (v > 20) v = 20;
                BORDER_WIDTH_IDS.forEach(otherId => {
                    const o = document.getElementById(otherId);
                    if (o) o.value = v;
                });
                this.applyToSelectedLayers(layer => { layer.panel_border_width = v; });
                window.canvasRenderer.render();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Border Width');
            });
        });

        // Sync border visibility checkboxes across tabs
        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        const checked = checkbox.checked;
                        // Update all border checkboxes
                        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(otherId => {
                            const other = document.getElementById(otherId);
                            if (other) other.checked = checked;
                        });
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });
        
        // Per-layer label checkboxes
        const labelCheckboxes = ['show-label-name', 'show-label-size-px', 'show-label-size-m', 'show-label-size-ft', 'show-label-info', 'show-label-weight', 'use-fractional-inches'];
        labelCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });

        const infoLabelSizeInput = document.getElementById('info-label-size');
        const infoLabelSizeValue = document.getElementById('info-label-size-value');
        if (infoLabelSizeInput) {
            const syncValue = () => {
                if (infoLabelSizeValue) infoLabelSizeValue.textContent = `${infoLabelSizeInput.value}`;
            };
            infoLabelSizeInput.addEventListener('input', () => {
                syncValue();
                this.applyToSelectedLayers(layer => {
                    layer.infoLabelSize = parseInt(infoLabelSizeInput.value, 10) || 14;
                });
                window.canvasRenderer.render();
            });
            infoLabelSizeInput.addEventListener('change', () => {
                syncValue();
                this.applyToSelectedLayers(layer => {
                    layer.infoLabelSize = parseInt(infoLabelSizeInput.value, 10) || 14;
                });
                this.updateLayers(this.getSelectedLayers(), true, 'Change Info Label Size');
                this.saveClientSideProperties();
                window.canvasRenderer.render();
            });
            syncValue();
        }
        
        // Per-layer offset checkboxes
        const offsetCheckboxes = ['show-offset-tl', 'show-offset-tr', 'show-offset-bl', 'show-offset-br'];
        offsetCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });
        
        // Screen Name checkboxes on other tabs, each writes its own per-tab property
        const tabLabelMap = {
            'show-label-name-cabinet': 'showLabelNameCabinet',
            'show-label-name-data': 'showLabelNameDataFlow',
            'show-label-name-power': 'showLabelNamePower'
        };
        Object.entries(tabLabelMap).forEach(([id, prop]) => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.applyToSelectedLayers(layer => {
                            layer[prop] = checkbox.checked;
                        });
                        this.updateLayers(this.getSelectedLayers());
                        window.canvasRenderer.render();
                        this.saveState('Toggle Screen Name');
                    }
                });
            }
        });

        // Processor Type, Bit Depth and Frame Rate controls for port capacity
        const processorSelect = document.getElementById('processor-type');
        const bitDepthSelect = document.getElementById('bit-depth');
        const frameRateSelect = document.getElementById('frame-rate');
        
        if (processorSelect) {
            processorSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.processorType = processorSelect.value;
                });
                // Update bit depth options based on processor
                this.updateBitDepthOptions();
                this.updateFrameRateOptions();
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Processor Type');
                window.canvasRenderer.render();
            });
        }
        
        if (bitDepthSelect) {
            bitDepthSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.bitDepth = parseInt(bitDepthSelect.value);
                });
                this.updateFrameRateOptions();
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Bit Depth');
                window.canvasRenderer.render();
            });
        }
        
        if (frameRateSelect) {
            frameRateSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.frameRate = parseFloat(frameRateSelect.value);
                });
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Frame Rate');
                window.canvasRenderer.render();
            });
        }
        
        // Port Mapping mode buttons (Organized vs Max Capacity)
        const mappingOrganizedBtn = document.getElementById('mapping-organized');
        const mappingMaxCapBtn = document.getElementById('mapping-max-capacity');
        
        const setMappingMode = (mode) => {
            this.applyToSelectedLayers(layer => {
                layer.portMappingMode = mode;
            });
            
            // Update button styles
            if (mappingOrganizedBtn && mappingMaxCapBtn) {
                if (mode === 'organized') {
                    mappingOrganizedBtn.style.background = '#4A90E2';
                    mappingOrganizedBtn.style.color = '#fff';
                    mappingMaxCapBtn.style.background = '#333';
                    mappingMaxCapBtn.style.color = '#ccc';
                } else {
                    mappingMaxCapBtn.style.background = '#4A90E2';
                    mappingMaxCapBtn.style.color = '#fff';
                    mappingOrganizedBtn.style.background = '#333';
                    mappingOrganizedBtn.style.color = '#ccc';
                }
            }
            
            this.saveClientSideProperties();
            this.updatePortCapacityDisplay();
            this.updatePortLabelEditor();
            this.updateLayers(this.getSelectedLayers(), true, 'Change Port Mapping Mode');
            window.canvasRenderer.render();
        };
        
        if (mappingOrganizedBtn) {
            mappingOrganizedBtn.addEventListener('click', () => setMappingMode('organized'));
        }
        if (mappingMaxCapBtn) {
            mappingMaxCapBtn.addEventListener('click', () => setMappingMode('max-capacity'));
        }
        
        // Flow Pattern buttons
        document.querySelectorAll('.flow-pattern-btn:not(.power-flow-pattern-btn)').forEach(btn => {
            btn.addEventListener('click', () => {
                const pattern = btn.getAttribute('data-pattern');
                if (this.currentLayer && this.isCustomFlow(this.currentLayer) && this.customSelection.size > 0) {
                    this.applyPatternToSelection(pattern);
                    return;
                }
                
                // Remove active class from all buttons
                document.querySelectorAll('.flow-pattern-btn').forEach(b => b.classList.remove('active'));
                // Add active to clicked button
                btn.classList.add('active');
                
                if (this.currentLayer) {
                    this.applyToSelectedLayers(layer => {
                        layer.flowPattern = pattern;
                    });
                    this.saveClientSideProperties();
                    this.updatePortCapacityDisplay();  // Update port calculation with new pattern
                    this.updatePortLabelEditor();
                    this.updateLayers(this.getSelectedLayers(), true, 'Change Data Flow Pattern');
                    window.canvasRenderer.render();
                }
            });
        });

        // Power Flow Pattern buttons
        document.querySelectorAll('.power-flow-pattern-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const pattern = btn.getAttribute('data-pattern');
                if (this.currentLayer && this.isCustomPower(this.currentLayer) && this.powerCustomSelection.size > 0) {
                    this.applyPowerPatternToSelection(pattern);
                    return;
                }
                document.querySelectorAll('.power-flow-pattern-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (this.currentLayer) {
                    this.applyToSelectedLayers(layer => {
                        layer.powerFlowPattern = pattern;
                    });
                    this.saveClientSideProperties();
                    this.updatePowerCapacityDisplay();
                    this.updateCustomPowerUI();
                    this.updateLayers(this.getSelectedLayers(), true, 'Change Power Flow Pattern');
                    window.canvasRenderer.render();
                }
            });
        });
        
        // Data Flow controls
        const arrowLineWidthInput = document.getElementById('arrow-line-width');
        if (arrowLineWidthInput) {
            arrowLineWidthInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.arrowLineWidth = parseInt(arrowLineWidthInput.value) || 6;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Arrow Line Width');
                window.canvasRenderer.render();
            });
        }

        const portTemplatePrimaryInput = document.getElementById('port-label-template-primary');
        const portTemplateReturnInput = document.getElementById('port-label-template-return');
        const portBulkPrimaryInput = document.getElementById('port-label-bulk-primary');
        const portBulkReturnInput = document.getElementById('port-label-bulk-return');
        const portApplySelectedBtn = document.getElementById('port-label-apply-selected');
        const portClearSelectedBtn = document.getElementById('port-label-clear-selected');
        const portSelectAllBtn = document.getElementById('port-label-select-all');
        const portDeselectAllBtn = document.getElementById('port-label-deselect-all');
        const customModeToggle = document.getElementById('custom-flow-toggle');
        const customPrevPortBtn = document.getElementById('custom-prev-port');
        const customNextPortBtn = document.getElementById('custom-next-port');
        const customClearPortBtn = document.getElementById('custom-clear-port');
        const customClearAllBtn = document.getElementById('custom-clear-all');
        const customClearSelectionBtn = document.getElementById('custom-clear-selection');
        const customActivePortInput = document.getElementById('custom-active-port-input');

        if (portTemplatePrimaryInput) {
            portTemplatePrimaryInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.portLabelTemplatePrimary = portTemplatePrimaryInput.value || 'P#';
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Port Label Template');
                window.canvasRenderer.render();
            });
        }
        if (portTemplateReturnInput) {
            portTemplateReturnInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.portLabelTemplateReturn = portTemplateReturnInput.value || 'R#';
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Port Label Template');
                window.canvasRenderer.render();
            });
        }

        const getSelectedPortNumbers = () => {
            const list = document.getElementById('port-label-list');
            if (!list) return [];
            const selected = [];
            list.querySelectorAll('input[type=\"checkbox\"][data-port]').forEach(cb => {
                if (cb.checked) selected.push(parseInt(cb.getAttribute('data-port'), 10));
            });
            return selected;
        };

        const setAllPortCheckboxes = (checked) => {
            const list = document.getElementById('port-label-list');
            if (!list) return;
            list.querySelectorAll('input[type=\"checkbox\"][data-port]').forEach(cb => {
                cb.checked = checked;
            });
        };

        if (portApplySelectedBtn) {
            portApplySelectedBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedPorts = getSelectedPortNumbers();
                if (selectedPorts.length === 0) return;
                const orderedPorts = [...selectedPorts].sort((a, b) => a - b);

                const bulkPrimary = portBulkPrimaryInput ? portBulkPrimaryInput.value.trim() : '';
                const bulkReturn = portBulkReturnInput ? portBulkReturnInput.value.trim() : '';

                targetLayers.forEach(layer => {
                    if (!layer.portLabelOverridesPrimary) layer.portLabelOverridesPrimary = {};
                    if (!layer.portLabelOverridesReturn) layer.portLabelOverridesReturn = {};
                    orderedPorts.forEach((portNum, index) => {
                        const groupIndex = index + 1;
                        if (bulkPrimary) {
                            layer.portLabelOverridesPrimary[portNum] = bulkPrimary.replace('#', groupIndex);
                        }
                        if (bulkReturn) {
                            layer.portLabelOverridesReturn[portNum] = bulkReturn.replace('#', groupIndex);
                        }
                    });
                });

                this.saveClientSideProperties();
                this.updatePortLabelEditor();
                this.updateLayers(targetLayers, true, 'Apply Port Labels');
                window.canvasRenderer.render();
            });
        }

        if (portClearSelectedBtn) {
            portClearSelectedBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedPorts = getSelectedPortNumbers();
                if (selectedPorts.length === 0) return;

                targetLayers.forEach(layer => {
                    selectedPorts.forEach(portNum => {
                        if (layer.portLabelOverridesPrimary) {
                            delete layer.portLabelOverridesPrimary[portNum];
                        }
                        if (layer.portLabelOverridesReturn) {
                            delete layer.portLabelOverridesReturn[portNum];
                        }
                    });
                });

                this.saveClientSideProperties();
                this.updatePortLabelEditor();
                this.updateLayers(targetLayers, true, 'Clear Port Labels');
                window.canvasRenderer.render();
            });
        }

        if (portSelectAllBtn) {
            portSelectAllBtn.addEventListener('click', () => {
                setAllPortCheckboxes(true);
            });
        }

        if (portDeselectAllBtn) {
            portDeselectAllBtn.addEventListener('click', () => {
                setAllPortCheckboxes(false);
            });
        }

        if (customModeToggle) {
            customModeToggle.addEventListener('change', () => {
                if (!this.currentLayer) return;
                // v0.8.2 Re-entrancy guard: when the change event re-fires
                // mid-flight (browser quirk on some platforms, observed on
                // mac WKWebView clicking the toggle once produced two change
                // events 367ms apart), the second invocation immediately
                // flips the state back so the user's single click ended up
                // disabling Custom mode. Drop the second event entirely.
                if (this._customFlowToggleInFlight) return;
                this._customFlowToggleInFlight = true;
                try {
                    this.toggleCustomFlowMode(customModeToggle.checked);
                } finally {
                    setTimeout(() => { this._customFlowToggleInFlight = false; }, 600);
                }
            });
        }
        if (customPrevPortBtn) {
            customPrevPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortIndex = Math.max(1, (this.currentLayer.customPortIndex || 1) - 1);
                this.saveState('Custom Port Change');
                this.saveClientSideProperties();
                // v0.8.2: PUT to the server. Without this, all the local
                // mutations (Next/Prev/Clear/Apply) accumulate only on the
                // client; the next time something else triggers a real PUT
                // (Mode Toggle, tab switch with stale state, etc.) the
                // client's view collapses or contradicts the server's.
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customNextPortBtn) {
            customNextPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortIndex = (this.currentLayer.customPortIndex || 1) + 1;
                this.saveState('Custom Port Change');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearPortBtn) {
            customClearPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                const portNum = this.currentLayer.customPortIndex || 1;
                this.currentLayer.customPortPaths[portNum] = [];
                this.saveState('Custom Clear Port');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearAllBtn) {
            customClearAllBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortPaths = {};
                this.currentLayer.customPortIndex = 1;
                this.customSelection.clear();
                this.saveState('Custom Clear All');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearSelectionBtn) {
            customClearSelectionBtn.addEventListener('click', () => {
                this.customSelection.clear();
                this.updateCustomFlowUI();
                window.canvasRenderer.render();
            });
        }
        if (customActivePortInput) {
            customActivePortInput.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                const nextVal = parseInt(customActivePortInput.value, 10);
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.customPortIndex = nextVal;
                    this.saveState('Custom Port Change');
                    this.saveClientSideProperties();
                    this.updateLayers(this.getSelectedLayers());
                    this.updateCustomFlowUI();
                    this.updatePortLabelEditor();
                    window.canvasRenderer.render();
                }
            });
        }
        
        const arrowSizeInput = document.getElementById('arrow-size');
        if (arrowSizeInput) {
            arrowSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.arrowSize = parseInt(arrowSizeInput.value) || 12;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Arrow Size');
                window.canvasRenderer.render();
            });
        }
        
        const randomColorsCheck = document.getElementById('random-colors');
        if (randomColorsCheck) {
            randomColorsCheck.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.randomDataColors = randomColorsCheck.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Random Data Colors');
                window.canvasRenderer.render();
            });
        }

        // Power settings
        const powerVoltageSelect = document.getElementById('power-voltage-select');
        const powerVoltageCustomInput = document.getElementById('power-voltage-custom');
        const powerAmperageSelect = document.getElementById('power-amperage-select');
        const powerAmperageCustomInput = document.getElementById('power-amperage-custom');
        const powerPanelWattsInput = document.getElementById('power-panel-watts');
        const powerLineWidthInput = document.getElementById('power-line-width');
        const powerLabelSizeInput = document.getElementById('power-label-size');
        const powerMaximizeCheckbox = document.getElementById('power-maximize');
        const powerOrganizedCheckbox = document.getElementById('power-organized');
        const powerCustomToggle = document.getElementById('power-custom-toggle');
        const powerCustomPrev = document.getElementById('power-custom-prev');
        const powerCustomNext = document.getElementById('power-custom-next');
        const powerCustomClearCircuit = document.getElementById('power-custom-clear-circuit');
        const powerCustomClearAll = document.getElementById('power-custom-clear-all');
        const powerCustomClearSelection = document.getElementById('power-custom-clear-selection');
        const powerCustomActive = document.getElementById('power-custom-active');
        const powerRandomColorsCheckbox = document.getElementById('power-random-colors');
        const powerColorCodedViewCheckbox = document.getElementById('power-color-coded-view');
        const powerCircuitColorSection = document.getElementById('power-circuit-color-section');
        const powerCircuitColorList = document.getElementById('power-circuit-color-list');
        const powerCircuitColorPreset = document.getElementById('power-circuit-color-preset');
        const powerCircuitColorCustom = document.getElementById('power-circuit-color-custom');
        const powerCircuitColorCustomHex = document.getElementById('power-circuit-color-custom-hex');
        const powerCircuitColorApply = document.getElementById('power-circuit-color-apply');
        const powerCircuitColorSelectAll = document.getElementById('power-circuit-color-select-all');
        const powerCircuitColorDeselectAll = document.getElementById('power-circuit-color-deselect-all');
        const powerLabelTemplateInput = document.getElementById('power-label-template');
        const powerLabelBulkInput = document.getElementById('power-label-bulk');
        const powerLabelApplyBtn = document.getElementById('power-label-apply-selected');
        const powerLabelClearBtn = document.getElementById('power-label-clear-selected');
        const powerLabelSelectAllBtn = document.getElementById('power-label-select-all');
        const powerLabelDeselectAllBtn = document.getElementById('power-label-deselect-all');
        const showDataFlowPortInfoEl = document.getElementById('show-data-flow-port-info');
        const showPowerCircuitInfoEl = document.getElementById('show-power-circuit-info');

        const updatePowerVoltageUI = () => {
            if (!powerVoltageSelect || !powerVoltageCustomInput) return;
            if (powerVoltageSelect.value === 'custom') {
                powerVoltageCustomInput.style.display = 'inline-block';
            } else {
                powerVoltageCustomInput.style.display = 'none';
            }
        };

        const updatePowerAmperageUI = () => {
            if (!powerAmperageSelect || !powerAmperageCustomInput) return;
            if (powerAmperageSelect.value === 'custom') {
                powerAmperageCustomInput.style.display = 'inline-block';
            } else {
                powerAmperageCustomInput.style.display = 'none';
            }
        };

        const getSelectedPowerCircuitLetters = () => {
            if (!powerCircuitColorList) return [];
            const selected = [];
            powerCircuitColorList.querySelectorAll('input[type="checkbox"][data-circuit-letter]').forEach(cb => {
                if (cb.checked) selected.push(cb.getAttribute('data-circuit-letter'));
            });
            return selected;
        };

        const setPowerCircuitLetterSelection = (checked) => {
            if (!powerCircuitColorList) return;
            powerCircuitColorList.querySelectorAll('input[type="checkbox"][data-circuit-letter]').forEach(cb => {
                cb.checked = checked;
            });
        };

        const renderPowerCircuitColorRows = () => {
            if (!powerCircuitColorList || !this.currentLayer) return;
            const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
            powerCircuitColorList.innerHTML = '';
            Object.keys(colors).forEach((letter, index) => {
                const row = document.createElement('div');
                row.style.display = 'grid';
                row.style.gridTemplateColumns = '20px 26px 1fr';
                row.style.gap = '6px';
                row.style.alignItems = 'center';

                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.setAttribute('data-circuit-letter', letter);

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
                powerCircuitColorList.appendChild(row);
            });
        };

        const updatePowerCircuitColorSection = () => {
            if (powerCircuitColorSection) {
                powerCircuitColorSection.style.display = (this.currentLayer && this.currentLayer.powerColorCodedView) ? 'block' : 'none';
            }
            renderPowerCircuitColorRows();
        };

        if (powerVoltageSelect && powerVoltageCustomInput) {
            powerVoltageSelect.addEventListener('change', () => {
                updatePowerVoltageUI();
                const val = powerVoltageSelect.value === 'custom'
                    ? parseFloat(powerVoltageCustomInput.value) || 0
                    : parseFloat(powerVoltageSelect.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerVoltage = val;
                    if (powerVoltageSelect.value === 'custom') {
                        layer.powerVoltageCustom = val;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Voltage');
                window.canvasRenderer.render();
            });
            powerVoltageCustomInput.addEventListener('change', () => {
                const val = parseFloat(powerVoltageCustomInput.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerVoltage = val;
                    layer.powerVoltageCustom = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Voltage');
                window.canvasRenderer.render();
            });
        }

        if (powerAmperageSelect && powerAmperageCustomInput) {
            powerAmperageSelect.addEventListener('change', () => {
                updatePowerAmperageUI();
                const val = powerAmperageSelect.value === 'custom'
                    ? parseFloat(powerAmperageCustomInput.value) || 0
                    : parseFloat(powerAmperageSelect.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerAmperage = val;
                    if (powerAmperageSelect.value === 'custom') {
                        layer.powerAmperageCustom = val;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Amperage');
                window.canvasRenderer.render();
            });
            powerAmperageCustomInput.addEventListener('change', () => {
                const val = parseFloat(powerAmperageCustomInput.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerAmperage = val;
                    layer.powerAmperageCustom = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Amperage');
                window.canvasRenderer.render();
            });
        }

        if (powerPanelWattsInput) {
            powerPanelWattsInput.addEventListener('change', () => {
                const parsed = this.evaluateNumericExpression(powerPanelWattsInput.value);
                const val = parsed === null ? 0 : parsed;
                // Write the resolved number back so the field shows the result
                if (parsed !== null) powerPanelWattsInput.value = this._formatEvaluatedNumber(parsed);
                else powerPanelWattsInput.style.outline = '2px solid #c55';
                if (parsed !== null) powerPanelWattsInput.style.outline = '';
                this.applyToSelectedLayers(layer => {
                    layer.panelWatts = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Panel Watts');
                window.canvasRenderer.render();
            });
        }

        if (powerLineWidthInput) {
            powerLineWidthInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLineWidth = parseInt(powerLineWidthInput.value, 10) || 8;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Line Width');
                window.canvasRenderer.render();
            });
        }

        if (powerLabelSizeInput) {
            powerLabelSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLabelSize = parseInt(powerLabelSizeInput.value, 10) || 14;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Label Size');
                window.canvasRenderer.render();
            });
        }

        if (powerMaximizeCheckbox) {
            powerMaximizeCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerMaximize = powerMaximizeCheckbox.checked;
                    if (powerMaximizeCheckbox.checked) {
                        layer.powerOrganized = false;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                if (powerOrganizedCheckbox && powerMaximizeCheckbox.checked) {
                    powerOrganizedCheckbox.checked = false;
                }
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Mode');
                window.canvasRenderer.render();
            });
        }

        if (powerOrganizedCheckbox) {
            powerOrganizedCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerOrganized = powerOrganizedCheckbox.checked;
                    if (powerOrganizedCheckbox.checked) {
                        layer.powerMaximize = false;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                if (powerMaximizeCheckbox && powerOrganizedCheckbox.checked) {
                    powerMaximizeCheckbox.checked = false;
                }
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Mode');
                window.canvasRenderer.render();
            });
        }

        if (powerRandomColorsCheckbox) {
            powerRandomColorsCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerRandomColors = powerRandomColorsCheckbox.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Power Random Colors');
                window.canvasRenderer.render();
            });
        }
        if (powerColorCodedViewCheckbox) {
            powerColorCodedViewCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerColorCodedView = powerColorCodedViewCheckbox.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Power Color Coding');
                updatePowerCircuitColorSection();
                window.canvasRenderer.render();
            });
        }
        if (powerCircuitColorSelectAll) {
            powerCircuitColorSelectAll.addEventListener('click', () => setPowerCircuitLetterSelection(true));
        }
        if (powerCircuitColorDeselectAll) {
            powerCircuitColorDeselectAll.addEventListener('click', () => setPowerCircuitLetterSelection(false));
        }
        if (powerCircuitColorApply) {
            powerCircuitColorApply.addEventListener('click', () => {
                const selectedLetters = getSelectedPowerCircuitLetters();
                if (!selectedLetters.length) return;
                let colorToApply = (powerCircuitColorPreset && powerCircuitColorPreset.value !== 'custom')
                    ? powerCircuitColorPreset.value
                    : (powerCircuitColorCustomHex ? powerCircuitColorCustomHex.value : '#FF0000');
                colorToApply = this.normalizeHexColor(colorToApply, '#FF0000');
                this.applyToSelectedLayers(layer => {
                    const colors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
                    selectedLetters.forEach(letter => {
                        colors[letter] = colorToApply;
                    });
                    layer.powerCircuitColors = colors;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Circuit Colors');
                updatePowerCircuitColorSection();
                window.canvasRenderer.render();
            });
        }
        if (powerCircuitColorPreset && powerCircuitColorCustomHex) {
            powerCircuitColorPreset.addEventListener('change', () => {
                if (powerCircuitColorPreset.value !== 'custom' && powerCircuitColorCustomHex) {
                    powerCircuitColorCustomHex.value = this.normalizeHexColor(powerCircuitColorPreset.value, '#FF0000');
                    if (powerCircuitColorCustom) powerCircuitColorCustom.value = powerCircuitColorCustomHex.value;
                }
            });
        }
        setupColorPickerWithHex('power-circuit-color-custom', 'power-circuit-color-custom-hex', () => {});
        if (showDataFlowPortInfoEl) {
            showDataFlowPortInfoEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showDataFlowPortInfo = showDataFlowPortInfoEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Port Info Labels');
                window.canvasRenderer.render();
            });
        }
        if (showPowerCircuitInfoEl) {
            showPowerCircuitInfoEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showPowerCircuitInfo = showPowerCircuitInfoEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Circuit Info Labels');
                window.canvasRenderer.render();
            });
        }

        const getSelectedPowerCircuits = () => {
            const list = document.getElementById('power-label-list');
            if (!list) return [];
            const selected = [];
            list.querySelectorAll('input[type="checkbox"][data-circuit]').forEach(cb => {
                if (cb.checked) selected.push(parseInt(cb.getAttribute('data-circuit'), 10));
            });
            return selected;
        };

        const setAllPowerCheckboxes = (checked) => {
            const list = document.getElementById('power-label-list');
            if (!list) return;
            list.querySelectorAll('input[type="checkbox"][data-circuit]').forEach(cb => {
                cb.checked = checked;
            });
        };

        if (powerLabelTemplateInput) {
            powerLabelTemplateInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLabelTemplate = powerLabelTemplateInput.value || 'S1-#';
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Label Template');
                window.canvasRenderer.render();
            });
        }

        if (powerLabelApplyBtn) {
            powerLabelApplyBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedCircuits = getSelectedPowerCircuits();
                if (selectedCircuits.length === 0) return;
                const ordered = [...selectedCircuits].sort((a, b) => a - b);
                const bulk = powerLabelBulkInput ? powerLabelBulkInput.value.trim() : '';
                if (!bulk) return;
                targetLayers.forEach(layer => {
                    if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
                    ordered.forEach((circuitNum, index) => {
                        const groupIndex = index + 1;
                        layer.powerLabelOverrides[circuitNum] = bulk.replace('#', groupIndex);
                    });
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(targetLayers, true, 'Apply Power Labels');
                window.canvasRenderer.render();
            });
        }

        if (powerLabelClearBtn) {
            powerLabelClearBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedCircuits = getSelectedPowerCircuits();
                if (selectedCircuits.length === 0) return;
                targetLayers.forEach(layer => {
                    selectedCircuits.forEach(circuitNum => {
                        if (layer.powerLabelOverrides) {
                            delete layer.powerLabelOverrides[circuitNum];
                        }
                    });
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(targetLayers, true, 'Clear Power Labels');
                window.canvasRenderer.render();
            });
        }

        if (powerLabelSelectAllBtn) {
            powerLabelSelectAllBtn.addEventListener('click', () => setAllPowerCheckboxes(true));
        }
        if (powerLabelDeselectAllBtn) {
            powerLabelDeselectAllBtn.addEventListener('click', () => setAllPowerCheckboxes(false));
        }

        if (powerCustomToggle) {
            powerCustomToggle.addEventListener('change', () => {
                if (!this.currentLayer) return;
                // v0.8.2: re-entrancy guard, single click was producing two
                // change events 367ms apart, with the second flipping the
                // state back to the opposite of what the user wanted. See
                // matching guard in customModeToggle handler above.
                if (this._customPowerToggleInFlight) return;
                this._customPowerToggleInFlight = true;
                try {
                    this.toggleCustomPowerMode(powerCustomToggle.checked);
                } finally {
                    setTimeout(() => { this._customPowerToggleInFlight = false; }, 600);
                }
            });
        }
        if (powerCustomPrev) {
            powerCustomPrev.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) - 1);
                this.saveState('Power Custom Circuit Change');
                this.saveClientSideProperties();
                // v0.8.2: PUT to the server. See matching comment on the data-
                // flow Custom handlers above. Without this, every Next/Prev/
                // Clear Circuit/Clear All/Pattern Apply mutated only the
                // client; the next Mode Toggle would then PUT a single-circuit
                // collapsed view of layer.powerCustomPaths.
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomNext) {
            powerCustomNext.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomIndex = (this.currentLayer.powerCustomIndex || 1) + 1;
                this.saveState('Power Custom Circuit Change');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearCircuit) {
            powerCustomClearCircuit.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                const circuitNum = this.currentLayer.powerCustomIndex || 1;
                this.currentLayer.powerCustomPaths[circuitNum] = [];
                this.saveState('Power Custom Clear Circuit');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearAll) {
            powerCustomClearAll.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomPaths = {};
                this.currentLayer.powerCustomIndex = 1;
                this.powerCustomSelection.clear();
                this.saveState('Power Custom Clear All');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearSelection) {
            powerCustomClearSelection.addEventListener('click', () => {
                this.powerCustomSelection.clear();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomActive) {
            powerCustomActive.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                const nextVal = parseInt(powerCustomActive.value, 10);
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.powerCustomIndex = nextVal;
                    this.saveState('Power Custom Circuit Change');
                    this.saveClientSideProperties();
                    this.updateLayers(this.getSelectedLayers());
                    this.updateCustomPowerUI();
                    window.canvasRenderer.render();
                }
            });
        }
        // power custom debug removed
        
        // Data Flow Color
        setupColorPickerWithHex('data-flow-color', 'data-flow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.dataFlowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Data Flow Color');
            window.canvasRenderer.render();
        });
        
        // Arrow Color
        setupColorPickerWithHex('arrow-color', 'arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.arrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Arrow Color');
            window.canvasRenderer.render();
        });
        
        // Primary Color
        setupColorPickerWithHex('primary-color', 'primary-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Primary Port Color');
            window.canvasRenderer.render();
        });

        // Primary Label Text Color
        setupColorPickerWithHex('primary-text-color', 'primary-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Primary Text Color');
            window.canvasRenderer.render();
        });
        
        // Backup/Redundant Color
        setupColorPickerWithHex('backup-color', 'backup-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Backup Port Color');
            window.canvasRenderer.render();
        });

        // Backup/Redundant Label Text Color
        setupColorPickerWithHex('backup-text-color', 'backup-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Backup Text Color');
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-line-color', 'power-line-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLineColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Power Line Color');
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-arrow-color', 'power-arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerArrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Power Arrow Color');
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-bg-color', 'power-label-bg-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelBgColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Power Label Background');
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-text-color', 'power-label-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Power Label Text Color');
            window.canvasRenderer.render();
        });
        
        const labelSizeInput = document.getElementById('label-size');
        if (labelSizeInput) {
            labelSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.dataFlowLabelSize = parseInt(labelSizeInput.value) || 12;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Data Flow Label Size');
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Data Flow tab (uses screen-name-size id)
        const screenNameSizeInput = document.getElementById('screen-name-size');
        if (screenNameSizeInput) {
            screenNameSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizeDataFlow = parseInt(screenNameSizeInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Screen Name Size');
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Cabinet ID tab
        const screenNameSizeCabinetInput = document.getElementById('screen-name-size-cabinet');
        if (screenNameSizeCabinetInput) {
            screenNameSizeCabinetInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizeCabinet = parseInt(screenNameSizeCabinetInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Screen Name Size');
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Power tab
        const screenNameSizePowerInput = document.getElementById('screen-name-size-power');
        if (screenNameSizePowerInput) {
            screenNameSizePowerInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizePower = parseInt(screenNameSizePowerInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Screen Name Size');
                window.canvasRenderer.render();
            });
        }
        
        // Labels color and font size
        const labelsColorInput = document.getElementById('labels-color');
        if (labelsColorInput) {
            labelsColorInput.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        const labelsFontSizeInput = document.getElementById('labels-fontsize');
        if (labelsFontSizeInput) {
            labelsFontSizeInput.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        // Color pickers with hex input sync
        setupColorPickerWithHex('color1-picker', 'color1-hex', (val, isFinal) => {
            const rgb = this.hexToRgb(val);
            this.applyToSelectedLayers(layer => {
                layer.color1 = rgb;
            });
            window.canvasRenderer.render();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Fill Color');
        });
        setupColorPickerWithHex('color2-picker', 'color2-hex', (val, isFinal) => {
            const rgb = this.hexToRgb(val);
            this.applyToSelectedLayers(layer => {
                layer.color2 = rgb;
            });
            window.canvasRenderer.render();
            if (isFinal) this.updateLayers(this.getSelectedLayers(), true, 'Change Fill Color');
        });

        // Transparent (no fill) override: render cabinets see-through so only
        // borders and labels draw. Applies to Pixel Map / Show Look fills.
        const transparentFillEl = document.getElementById('transparent-fill');
        if (transparentFillEl) {
            transparentFillEl.addEventListener('change', () => {
                const checked = transparentFillEl.checked;
                this.applyToSelectedLayers(layer => { layer.transparentFill = checked; });
                window.canvasRenderer.render();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Transparent Fill');
            });
        }

        // v0.9.3: screen rotation (Pixel Map / Cabinet ID). 0/90/180/270.
        const screenRotationEl = document.getElementById('screen-rotation');
        if (screenRotationEl) {
            screenRotationEl.addEventListener('change', () => {
                const deg = parseInt(screenRotationEl.value, 10) || 0;
                this.applyToSelectedLayers(layer => { layer.rotation = deg; });
                window.canvasRenderer.render();
                this.updateLayers(this.getSelectedLayers(), true, 'Rotate Screen');
            });
        }

        // v0.8.7.8: gradient overlay editor (standard multi-stop).
        this.setupGradientEditor();
        // v0.8.7.8: multi-color cabinet palette editor.
        this.setupPaletteEditor();
        
        const rasterWidthInput = document.getElementById('toolbar-raster-width');
        const rasterHeightInput = document.getElementById('toolbar-raster-height');
        
        if (rasterWidthInput) {
            rasterWidthInput.addEventListener('change', () => {
                const width = evaluateMathExpression(rasterWidthInput.value) || 1920;
                rasterWidthInput.value = width;
                // Slice 6: the toolbar Raster: W x H field is the active
                // canvas's raster (Pixel Map raster on pixel-map / cabinet-id;
                // Show Look raster on show-look / data / power). Writes go
                // straight to the active canvas via PUT /api/canvas/<id>,
                // no project-root mirror, no _mirrorRasterToActiveCanvas hack.
                //
                // While show raster equals pixel raster ("linked"), changing
                // the pixel raster also updates the show raster, Show Look
                // tracks Pixel Map by default until the user splits them.
                const renderer = window.canvasRenderer;
                const isShow = renderer.isShowLookView();
                this._writeToolbarRasterToActiveCanvas('width', width, isShow);
                renderer.render();
            });
        }

        if (rasterHeightInput) {
            rasterHeightInput.addEventListener('change', () => {
                const height = evaluateMathExpression(rasterHeightInput.value) || 1080;
                rasterHeightInput.value = height;
                const renderer = window.canvasRenderer;
                const isShow = renderer.isShowLookView();
                this._writeToolbarRasterToActiveCanvas('height', height, isShow);
                renderer.render();
            });
        }
        
        // Note: loadRasterSize() is called in init() before setupEventListeners
        
        document.getElementById('btn-new').addEventListener('click', () => {
            if (confirm('Create a new project? Unsaved changes will be lost.')) {
                this.createNewProject();
            }
        });
        
        document.getElementById('btn-open').addEventListener('click', () => {
            this.loadProjectFromFile();
        });
        
        document.getElementById('btn-save').addEventListener('click', () => {
            this.saveProjectToFile();
        });
        
        document.getElementById('btn-preferences').addEventListener('click', () => {
            this.openPreferencesModal();
        });

        document.getElementById('btn-export').addEventListener('click', () => {
            this.openExportModal();
        });
        
        // Update preview when options change
        ['export-name', 'export-format', 'export-pixel-map', 'export-cabinet-id', 'export-show-look', 'export-data-flow', 'export-power',
         'export-suffix-pixel-map', 'export-suffix-cabinet-id', 'export-suffix-show-look', 'export-suffix-data-flow', 'export-suffix-power'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', () => {
                    this.saveExportSuffixesFromUI();
                    this.updateExportPreview();
                });
                el.addEventListener('input', () => {
                    this.saveExportSuffixesFromUI();
                    this.updateExportPreview();
                });
            }
        });

        // v0.8.7: PSD-only Resolution Scale row. Hide it for any other
        // format so the option only surfaces when it actually applies.
        const _toggleScaleRow = () => {
            const formatEl = document.getElementById('export-format');
            const scaleRow = document.getElementById('export-scale-row');
            if (!formatEl || !scaleRow) return;
            scaleRow.style.display = (formatEl.value === 'psd') ? '' : 'none';
        };
        const _formatEl = document.getElementById('export-format');
        if (_formatEl) {
            _formatEl.addEventListener('change', _toggleScaleRow);
            _toggleScaleRow();
        }
        
        document.getElementById('export-cancel').addEventListener('click', () => {
            document.getElementById('export-modal').style.display = 'none';
        });
        
        document.getElementById('export-confirm').addEventListener('click', async () => {
            const projectName = document.getElementById('export-name').value.trim() || 'Project';
            const format = document.getElementById('export-format').value;
            sendClientLog('export_capabilities', {
                hasSaveFilePicker: this.supportsFilePickerAPIs(),
                hasDirectoryPicker: this.supportsDirectoryPickerAPIs(),
                format
            });
            
            // Resolume XML export, no views needed, just geometry
            if (format === 'resolume-xml') {
                document.getElementById('export-modal').style.display = 'none';
                document.getElementById('status-message').textContent = 'Exporting Resolume XML...';
                try {
                    await this.exportResolumeXml(projectName);
                    document.getElementById('status-message').textContent = 'Export complete!';
                    setTimeout(() => { document.getElementById('status-message').textContent = 'Ready'; }, 3000);
                } catch (error) {
                    console.error('Resolume export error:', error);
                    document.getElementById('status-message').textContent = 'Export failed!';
                    sendClientLog('export_failed', { message: error.message, format: 'resolume-xml' });
                }
                return;
            }

            // Get selected views
            const views = [];
            if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
            if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
            if (document.getElementById('export-show-look') && document.getElementById('export-show-look').checked) views.push('show-look');
            if (document.getElementById('export-data-flow').checked) views.push('data-flow');
            if (document.getElementById('export-power').checked) views.push('power');

            if (views.length === 0) {
                alert('Please select at least one view to export.');
                return;
            }

            // Slice 11: collect selected canvas IDs from the dynamic
            // checklist. If the project has no canvases array (legacy /
            // pre-Slice-1 fallback), pass [null] so performExport treats it
            // as a single synthetic canvas using project-root raster dims,
            // matching v0.7 export behaviour exactly.
            const canvasIds = this.getSelectedExportCanvasIds();
            if (canvasIds.length === 0) {
                alert('Please select at least one canvas to export.');
                return;
            }

            if (!this.supportsFilePickerAPIs() && !this.supportsDirectoryPickerAPIs() && !this._warnedNoFilePickerExport) {
                this._warnedNoFilePickerExport = true;
                sendClientLog('export_picker_apis_unavailable_warning', {});
            }

            document.getElementById('export-modal').style.display = 'none';
            document.getElementById('status-message').textContent = 'Exporting...';

            try {
                await this.performExport(projectName, format, views, canvasIds);
                
                document.getElementById('status-message').textContent = 'Export complete!';
                setTimeout(() => {
                    document.getElementById('status-message').textContent = 'Ready';
                }, 3000);
            } catch (error) {
                console.error('Export error:', error);
                document.getElementById('status-message').textContent = 'Export failed!';
                sendClientLog('export_failed', { message: error.message });
            }
        });
        
        // Close export modal only when press+release both happen on backdrop
        const exportModal = document.getElementById('export-modal');
        const exportModalContent = exportModal ? exportModal.querySelector('.modal-content') : null;
        let exportBackdropDown = false;
        if (exportModal) {
            exportModal.addEventListener('mousedown', (e) => {
                exportBackdropDown = e.target === exportModal;
            });
            exportModal.addEventListener('click', (e) => {
                if (e.target === exportModal && exportBackdropDown) {
                    exportModal.style.display = 'none';
                }
                exportBackdropDown = false;
            });
        }
        if (exportModalContent) {
            exportModalContent.addEventListener('mousedown', () => {
                exportBackdropDown = false;
            });
            exportModalContent.addEventListener('click', (e) => e.stopPropagation());
        }

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
        let serverProps;
        if (presetData && typeof presetData === 'object') {
            serverProps = {
                columns: presetData.columns != null ? presetData.columns : prefs.columns,
                rows: presetData.rows != null ? presetData.rows : prefs.rows,
                cabinet_width: presetData.cabinet_width != null ? presetData.cabinet_width : prefs.panelWidth,
                cabinet_height: presetData.cabinet_height != null ? presetData.cabinet_height : prefs.panelHeight,
                color1: presetData.color1 || this.hexToRgb(prefs.color1),
                color2: presetData.color2 || this.hexToRgb(prefs.color2),
                border_color: presetData.border_color || prefs.borderColor,
                panel_weight: presetData.panel_weight != null ? presetData.panel_weight : prefs.panelWeight,
                weight_unit: presetData.weight_unit || prefs.weightUnit
            };
        } else {
            serverProps = {
                columns: prefs.columns,
                rows: prefs.rows,
                cabinet_width: prefs.panelWidth,
                cabinet_height: prefs.panelHeight,
                color1: this.hexToRgb(prefs.color1),
                color2: this.hexToRgb(prefs.color2),
                border_color: prefs.borderColor,
                panel_weight: prefs.panelWeight,
                weight_unit: prefs.weightUnit
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
        .then(res => res.json())
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

            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();

            // saveState AFTER the layer lands in the project (same fix as Add
            // Canvas): snapshotting before the fetch resolved captured the
            // pre-add state, so redo after undo silently lost the new screen.
            this.saveState('Add Layer');

            // Save the new defaults to localStorage
            this.saveClientSideProperties();

            // IMPORTANT: when a preset was applied, the server only knows the
            // structural fields sent via /api/layer/add (columns, cabinet dims,
            // colors, etc.). Preset values like bitDepth, frameRate, panelWatts,
            // powerVoltage, flowPattern, label sizes, etc. live only on the
            // client at this point. Any subsequent server re-fetch (e.g. after
            // delete_layer or file load) would clobber them. Push the enriched
            // layer back now so server + client stay in sync.
            if (appliedPreset) {
                this.updateLayers([layer]);
            }
        });
    }

    // Properties excluded from presets (identity, runtime position, cached computations).
    // Everything else on a layer can be preserved as a preset.
    getPresetExcludedKeys() {
        return new Set([
            'id', 'name', 'visible', 'locked',
            'offset_x', 'offset_y',
            'panels',  // panel array is regenerated from columns/rows on server
            '_powerError', '_powerCircuits', '_powerPanelCircuitMap', '_powerPanelIndexMap',
            '_powerCircuitNumKeys', '_powerTotalAmps1', '_powerTotalAmps3',
            '_powerCircuitsRequired', '_capacityError', '_portsRequired', '_autoPortsRequired',
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
        return out;
    }

    applyPresetClientProps(layer, presetData) {
        const excluded = this.getPresetExcludedKeys();
        // Server-side structural props already applied via /api/layer/add; skip them here.
        const serverKeys = new Set(['columns', 'rows', 'cabinet_width', 'cabinet_height',
            'color1', 'color2', 'border_color', 'panel_weight', 'weight_unit']);
        Object.keys(presetData).forEach(k => {
            if (excluded.has(k)) return;
            if (serverKeys.has(k)) return;
            if (k.startsWith('_')) return;
            layer[k] = presetData[k];
        });
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
        'novastar-5g': {
            8:  { 24:6480000, 25:6220800, 30:5184000, 50:3110400, 60:2592000, 120:1296000, 144:1080864, 240:648000 },
            10: { 24:5182500, 25:4975200, 30:4146000, 50:2487600, 60:2073000, 120:1036500, 144:864441,  240:518250 },
            12: { 24:4320000, 25:4147200, 30:3456000, 50:2073600, 60:1728000, 120:864000,  144:720576,  240:432000 }
        },
        'brompton': {
            8:  { 24:1312500, 25:1260000, 30:1050000, 48:656250, 50:630000, 60:525000, 72:437500, 100:315000, 120:262500, 144:218750, 150:210000, 180:175000, 192:164063, 200:157500, 240:131250, 250:126000 },
            10: { 24:1050000, 25:1008000, 30:840000,  48:525000, 50:504000, 60:420000, 72:350000, 100:252000, 120:210000, 144:175000, 150:168000, 180:140000, 192:131250, 200:126000, 240:105000, 250:100800 },
            12: { 24:875000,  25:840000,  30:700000,   48:437500, 50:420000, 60:350000, 72:291667, 100:210000, 120:175000, 144:145833, 150:140000, 180:116667, 192:109375, 200:105000, 240:87500,  250:84000 }
        },
        'brompton-ull': {
            8:  { 24:656250,  25:630000,  30:525000,  48:328125, 50:315000, 60:262500, 72:218750, 100:157500, 120:131250, 144:109375, 150:105000, 180:87500,  192:82031,  200:78750,  240:65625,  250:63000 },
            10: { 24:525000,  25:504000,  30:420000,  48:262500, 50:252000, 60:210000, 72:175000, 100:126000, 120:105000, 144:87500,  150:84000,  180:70000,  192:65625,  200:63000,  240:52500,  250:50400 },
            12: { 24:437500,  25:420000,  30:350000,  48:218750, 50:210000, 60:175000, 72:145833, 100:105000, 120:87500,  144:72917,  150:70000,  180:58333,  192:54688,  200:52500,  240:43750,  250:42000 }
        },
        'megapixel-1g': {
            10: { 24:1275000, 25:1225000, 30:1020000, 48:635000, 50:610000, 60:510000, 120:240000, 144:195000, 180:148000, 200:128000, 240:100000 },
            12: { 24:1062500, 25:1020000, 30:850000,  48:531000, 50:510000, 60:425000, 120:200000, 144:160000, 180:126000, 200:112000, 240:90000 }
        },
        'megapixel-2.5g': {
            10: { 24:3187500, 25:3062500, 30:2550000, 48:1587500, 50:1525000, 60:1275000, 120:600000, 144:487500, 180:370000, 200:320000, 240:250000 },
            12: { 24:2656250, 25:2550000, 30:2125000, 48:1328125, 50:1275000, 60:1062500, 120:500000, 144:400000, 180:315000, 200:280000, 240:225000 }
        }
    };
}
