// app-client-props: the localStorage side of LEDRasterApp's per-layer
// state - the client-side properties that ride alongside the server's
// project (loadClientSideProperties / saveClientSideProperties) and the
// raster size the toolbar shows (saveRasterSize / syncRasterFromProject /
// loadRasterSize).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ClientProps {
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
                        if (layerProps.lowLatency !== undefined) layer.lowLatency = layerProps.lowLatency;
                        if (layerProps.portMappingMode !== undefined) layer.portMappingMode = layerProps.portMappingMode;
                        if (layerProps.portLabelTemplatePrimary !== undefined) layer.portLabelTemplatePrimary = layerProps.portLabelTemplatePrimary;
                        if (layerProps.portLabelTemplateReturn !== undefined) layer.portLabelTemplateReturn = layerProps.portLabelTemplateReturn;
                        if (layerProps.portLabelOverridesPrimary !== undefined) layer.portLabelOverridesPrimary = layerProps.portLabelOverridesPrimary;
                        if (layerProps.portLabelOverridesReturn !== undefined) layer.portLabelOverridesReturn = layerProps.portLabelOverridesReturn;
                        if (layerProps.customPortPaths !== undefined) layer.customPortPaths = layerProps.customPortPaths;
                        if (layerProps.customPortIndex !== undefined) layer.customPortIndex = layerProps.customPortIndex;
                        if (layerProps.customPortOverrides !== undefined) layer.customPortOverrides = layerProps.customPortOverrides;
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
                        if (layerProps.powerCircuitCables !== undefined) layer.powerCircuitCables = layerProps.powerCircuitCables;
                        if (layerProps.powerCustomPaths !== undefined) layer.powerCustomPaths = layerProps.powerCustomPaths;
                        if (layerProps.powerCustomIndex !== undefined) layer.powerCustomIndex = layerProps.powerCustomIndex;
                        if (layerProps.powerCustomOverrides !== undefined) layer.powerCustomOverrides = layerProps.powerCustomOverrides;
                        if (layerProps.powerSplitters !== undefined) layer.powerSplitters = layerProps.powerSplitters;
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
                        if (layerProps.showDataFlowPortLoad !== undefined) layer.showDataFlowPortLoad = layerProps.showDataFlowPortLoad;
                        if (layerProps.showPowerCircuitInfo !== undefined) layer.showPowerCircuitInfo = layerProps.showPowerCircuitInfo;
                        if (layerProps.showPowerNferTags !== undefined) layer.showPowerNferTags = layerProps.showPowerNferTags;
                        if (layerProps.showPowerCableTags !== undefined) layer.showPowerCableTags = layerProps.showPowerCableTags;
                        if (layerProps.showDataCableTags !== undefined) layer.showDataCableTags = layerProps.showDataCableTags;
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
            // v0.11.0: sets lowLatency itself when it fires, so it has to run
            // before the default below or the migrated flag gets stamped out.
            this.migrateLowLatencyProcessor(layer);
            if (layer.lowLatency === undefined) layer.lowLatency = !!prefs.lowLatency;
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
            if (layer.customPortOverrides === undefined) layer.customPortOverrides = [];
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
            // Per-circuit cables ({circuit: {ft, connector}}) - the
            // paperwork's 10' True1 on circuit 1 (2026-09-06).
            if (layer.powerCircuitCables === undefined) layer.powerCircuitCables = {};
            if (layer.powerSocaNames === undefined) layer.powerSocaNames = {};
            // Reads the template it just defaulted above, so it has to run
            // after it: the shift it applies is the template's own start
            // digit. Stamps the layer, so it is a no-op on every load after
            // the first (see migrateSocaKeying).
            this.migrateSocaKeying(layer);
                if (layer.powerCustomPaths === undefined) layer.powerCustomPaths = {};
            if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
            if (layer.powerCustomOverrides === undefined) layer.powerCustomOverrides = [];
            // Power splitters (circuit sharing): off by default, 3fer max
            // (2fer/3fer out of the box), no manual overrides. See
            // getPowerSplitters for the normalized read.
            if (layer.powerSplitters === undefined) {
                layer.powerSplitters = {
                    enabled: false, maxWays: 3,
                    manual: { merge: [], split: [] },
                };
            }
            if (layer.halfFirstColumn === undefined) layer.halfFirstColumn = false;
            if (layer.halfLastColumn === undefined) layer.halfLastColumn = false;
            if (layer.halfFirstRow === undefined) layer.halfFirstRow = false;
            if (layer.halfLastRow === undefined) layer.halfLastRow = false;
            if (layer.weight_unit === undefined) layer.weight_unit = prefs.weightUnit || 'kg';
            if (layer.panel_weight === undefined) layer.panel_weight = prefs.panelWeight || 20;
            if (layer.infoLabelSize === undefined) layer.infoLabelSize = 14;
            if (layer.showDataFlowPortInfo === undefined) layer.showDataFlowPortInfo = false;
            // v0.11.0: port load % defaults OFF - an existing project must open
            // and export exactly as it did before.
            if (layer.showDataFlowPortLoad === undefined) layer.showDataFlowPortLoad = false;
            if (layer.showPowerCircuitInfo === undefined) layer.showPowerCircuitInfo = false;
            // The 2fer / 3fer tag on a shared circuit's bracket defaults ON;
            // the switch exists because "i need a way to disable the
            // twofer/3fer text on the screen if i dont want it there"
            // (2026-09-06). A project saved before the switch keeps its tags.
            if (layer.showPowerNferTags === undefined) layer.showPowerNferTags = true;
            // The cable tag beside a circuit's label defaults OFF: it is
            // ink for the docs - "i like having D as an option when doing
            // the docs per screen" (2026-09-06) - not for the wall.
            if (layer.showPowerCableTags === undefined) layer.showPowerCableTags = false;
            // Its data twin - a port's snake name or own cable beside its
            // label - defaults OFF for the same reason ("the same option
            // for data homeruns", 2026-09-06).
            if (layer.showDataCableTags === undefined) layer.showDataCableTags = false;
            // Show Look position, default to processor offset for older
            // projects so they open looking identical to before.
            if (layer.showOffsetX === undefined || layer.showOffsetX === null) {
                layer.showOffsetX = layer.offset_x || 0;
            }
            if (layer.showOffsetY === undefined || layer.showOffsetY === null) {
                layer.showOffsetY = layer.offset_y || 0;
            }
            // v0.11.0 (step 6): last in the pass, once customPortPaths /
            // powerCustomPaths are guaranteed to exist. It validates against
            // group membership, which arrives with the server payload rather
            // than from the defaults above, so position inside this loop is
            // safe. The paths it is checking were restored from localStorage
            // keyed by layer id - exactly where a stale peer reference from a
            // different project gets in.
            this.sanitizeCrossLayerPaths(layer);
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
            layer.lowLatency = !!prefs.lowLatency;
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
                lowLatency: layer.lowLatency,
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
                powerCustomOverrides: layer.powerCustomOverrides,
                powerSplitters: layer.powerSplitters,
                border_color_pixel: layer.border_color_pixel,
                border_color_cabinet: layer.border_color_cabinet,
                border_color_data: layer.border_color_data,
                border_color_power: layer.border_color_power,
                weight_unit: layer.weight_unit,
                panel_weight: layer.panel_weight,
                infoLabelSize: layer.infoLabelSize,
                showDataFlowPortInfo: layer.showDataFlowPortInfo,
                showDataFlowPortLoad: layer.showDataFlowPortLoad,
                showPowerCircuitInfo: layer.showPowerCircuitInfo,
                showPowerNferTags: layer.showPowerNferTags,
                showPowerCableTags: layer.showPowerCableTags,
                showDataCableTags: layer.showDataCableTags,
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
}

for (const k of Object.getOwnPropertyNames(_ClientProps.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ClientProps.prototype, k));
    }
}
