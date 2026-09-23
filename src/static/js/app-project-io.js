// app-project-io: saving and loading the project as a file for
// LEDRasterApp - saveProject, saveProjectToFile, loadProjectFromFile,
// resetApplicationState, and the normalizers a loaded project passes
// through (missing layer defaults, power flow pattern, Armor port
// mapping).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ProjectIo {
    // The build this page is: what a saved project is stamped with as
    // `app_version` (the server stamps the same on every POST /api/project
    // and on a new project; a load never stamps, so a file saved before
    // the stamp existed still carries none - see app-naming
    // normalizePowerCircuitColors for what reads it). /api/version is the
    // authority (VERSION.txt on the local server, the About dialog's
    // source); it is fetched once, and until it answers the baked page
    // title stands in - the same fallback whatsnew.js uses. Synchronous,
    // so a save never waits on the network for its stamp.
    appVersion() {
        if (this._appVersion) return this._appVersion;
        if (!this._appVersionFetch) {
            this._appVersionFetch = fetch('/api/version')
                .then(r => r.json())
                .then(d => { if (d && d.version) this._appVersion = String(d.version); })
                .catch(() => {});
        }
        const m = /v(\d+\.\d+\.\d+)/.exec(document.title || '');
        return m ? m[1] : '';
    }

    // The project as the file on disk holds it: this build's version
    // stamped on, then pretty-printed. saveProjectToFile writes exactly
    // this, so a round trip through File > Open reads the stamp back.
    serializeProjectForFile(project = this.project) {
        project.app_version = this.appVersion();
        return JSON.stringify(project, null, 2);
    }

    saveProject() {
        this.project.app_version = this.appVersion();
        fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.project)
        })
        .then(() => {
            document.getElementById('status-message').textContent = 'Project saved';
            setTimeout(() => {
                document.getElementById('status-message').textContent = 'Ready';
            }, 2000);
        });
    }
    
    async saveProjectToFile() {
        // Ensure raster size in project reflects current toolbar/canvas values
        if (window.canvasRenderer && this.project) {
            this.project.raster_width = window.canvasRenderer.rasterWidth;
            this.project.raster_height = window.canvasRenderer.rasterHeight;
        }
        sendClientLog('save_project_file_capabilities', {
            hasSaveFilePicker: this.supportsFilePickerAPIs()
        });
        if (!this.supportsFilePickerAPIs() && !this._warnedNoFilePicker) {
            this._warnedNoFilePicker = true;
            sendClientLog('save_picker_apis_unavailable_warning', {});
        }
        // Pass a lazy blob factory so JSON.stringify (slow on large multi-canvas
        // projects, ~1MB) runs AFTER showSaveFilePicker resolves. This keeps
        // Chrome's user-activation token fresh for createWritable; otherwise
        // Chrome rejects the write with NotAllowedError and leaves a 0-byte file.
        const project = this.project;
        await this.saveBlobWithPicker(
            () => {
                const projectData = this.serializeProjectForFile(project);
                return new Blob([projectData], { type: 'application/json' });
            },
            `${this.project.name}.json`,
            'application/json'
        );

        this.addToRecentFiles(this.project);
        document.getElementById('status-message').textContent = 'Project saved to file';
        setTimeout(() => {
            document.getElementById('status-message').textContent = 'Ready';
        }, 2000);
    }
    
    loadProjectFromFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.style.display = 'none';
        document.body.appendChild(input);
        sendClientLog('open_file_dialog_requested');
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const projectData = JSON.parse(event.target.result);
                        sendClientLog('load_project_file_start', { name: projectData.name || 'Unnamed', layers: projectData.layers ? projectData.layers.length : 0 });
                        // Clean-slate reset so stale sidebar values can't leak into new project
                        this.resetApplicationState();
                        this.project = projectData;
                        if (this.project.layers) {
                            this.project.layers.forEach(layer => {
                                this.applyMissingLayerDefaults(layer);
                                this.normalizeLoadedPowerFlowPattern(layer);
                            });
                        }
                        // The migrations above have run against the file's
                        // own stamp; from here the project is this build's.
                        // Stamped BEFORE the PUT below, because a load never
                        // stamps on the server, and an unstamped server copy
                        // re-ran the old-green migration on every page reload
                        // - repainting a set chosen since (2026-09-23).
                        this.project.app_version = this.appVersion();
                        // v0.11.0: fix up Armor layers that carry a Max Capacity
                        // flag they were never actually drawn with. Runs before
                        // the PUT so the server (and the first undo snapshot)
                        // get the corrected mode.
                        this.normalizeArmorPortMapping(this.project);

                        // v0.8.7.2.1: ONLY trust root-level raster fields for
                        // legacy (pre-v0.8, no canvases array) files. Multi-
                        // canvas files keep the source-of-truth on each canvas
                        // object, and writing the root value into
                        // canvasRenderer.rasterWidth would clobber the active
                        // canvas's per-canvas raster (the setter routes to
                        // either raster_width or show_raster_width depending
                        // on the current tab). Bug repro: the file's root
                        // raster_width was a mirror of the active canvas's
                        // *show* raster (because the user last saved on Show
                        // Look), so opening the file overwrote the active
                        // canvas's pixel-map raster with its show raster
                        // value. syncRasterFromProject below reads from each
                        // canvas directly so multi-canvas projects are
                        // unaffected by skipping this block.
                        const _hasCanvases = Array.isArray(projectData.canvases)
                            && projectData.canvases.length > 0;
                        if (!_hasCanvases && projectData.raster_width && projectData.raster_height) {
                            window.canvasRenderer.rasterWidth = projectData.raster_width;
                            window.canvasRenderer.rasterHeight = projectData.raster_height;
                            document.getElementById('toolbar-raster-width').value = projectData.raster_width;
                            document.getElementById('toolbar-raster-height').value = projectData.raster_height;
                            this.saveRasterSize();
                        }

                        // Show locally right away (even if server sync fails)
                        this.updateUI();
                        if (this.project.layers && this.project.layers.length > 0) {
                            this.selectLayer(this.project.layers[0]);
                        }
                        this.saveClientSideProperties();
                        window.canvasRenderer.fitToView();

                        fetch('/api/project', {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.project)
                        })
                            .then(res => res.json())
                            .then(data => {
                                if (!data || !Array.isArray(data.layers)) {
                                    throw new Error('Invalid project data returned from server');
                                }
                                this.project = data;
                                this.dedupeProjectLayers('load_project_file');
                                if (this.project.layers) {
                                    this.project.layers.forEach(layer => {
                                        this.applyMissingLayerDefaults(layer);
                                        this.normalizeLoadedPowerFlowPattern(layer);
                                    });
                                }
                                // v0.11.0: no-op when the pre-PUT pass already
                                // fixed them; kept so the object that feeds
                                // resetHistory() below is always normalized.
                                this.normalizeArmorPortMapping(this.project);
                                // Sync the canvas's pixel/show raster backing fields from the
                                // loaded project so Show Look picks up the file's values
                                // (and falls back to the pixel raster when show wasn't saved).
                                this.syncRasterFromProject();
                                this.updateUI();
                                if (this.project.layers && this.project.layers.length > 0) {
                                    this.selectLayer(this.project.layers[0]);
                                }
                                this.saveClientSideProperties();
                                window.canvasRenderer.fitToView();
                                // Push all layers to server so client-side properties
                                // (showDataFlowPortInfo, showPowerCircuitInfo, computed power/capacity)
                                // are synced for every layer, not just the selected one.
                                this.updateLayers(this.project.layers, false, 'File Load Sync');
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                                this.addToRecentFiles(this.project);
                                sendClientLog('load_project_file_success', { name: this.project.name, layers: this.project.layers ? this.project.layers.length : 0 });
                                // Slice 12: server flagged this file as
                                // freshly migrated from v0.7. Show a one-time
                                // toast and strip the transient flag so it
                                // never ends up in the saved JSON. The toast
                                // is suppressed automatically on subsequent
                                // loads because the saved file now carries
                                // format_version: "0.8".
                                if (data && data._migration_notice) {
                                    delete this.project._migration_notice;
                                    sendClientLog('migration_notice_shown', {
                                        name: this.project.name,
                                        layers: this.project.layers ? this.project.layers.length : 0
                                    });
                                    if (typeof this._toast === 'function') {
                                        this._toast(
                                            'Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file.',
                                            false,
                                            10000
                                        );
                                    }
                                }
                            })
                            .catch((err) => {
                                sendClientLog('load_project_file_error', { message: err.message });
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded (server sync failed)';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                            });
                    } catch (error) {
                        sendClientLog('load_project_file_error', { message: error.message });
                        alert('Error loading project file: ' + error.message);
                    }
                };
                reader.readAsText(file);
            } else {
                sendClientLog('open_file_dialog_cancelled');
            }
            if (input.parentNode) input.parentNode.removeChild(input);
        };
        input.click();
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

    applyMissingLayerDefaults(layer) {
        if (layer.locked === undefined) layer.locked = false;
        // v0.11.0: File > Open and Recent Files come through here, not through
        // loadClientSideProperties, so the brompton-ull migration has to run on
        // this path too or an old file would keep a processor that is no longer
        // offered. Runs before the default below: it sets lowLatency itself.
        this.migrateLowLatencyProcessor(layer);
        if (layer.lowLatency === undefined) layer.lowLatency = false;
        if (layer.powerVoltage === undefined) this.setScreenVoltage(layer, 110);
        if (layer.powerVoltageCustom === undefined) layer.powerVoltageCustom = layer.powerVoltage;
        if (layer.powerAmperage === undefined) layer.powerAmperage = 15;
        if (layer.powerAmperageCustom === undefined) layer.powerAmperageCustom = layer.powerAmperage;
        if (layer.panelWatts === undefined) layer.panelWatts = 200;
        if (layer.powerMaximize === undefined) layer.powerMaximize = false;
        if (layer.powerOrganized === undefined) layer.powerOrganized = true;
        if (layer.powerCustomPath === undefined) layer.powerCustomPath = false;
        if (!layer.powerFlowPattern) layer.powerFlowPattern = layer.flowPattern || 'tl-h';
        if (layer.powerLineWidth === undefined) layer.powerLineWidth = 8;
        if (!layer.powerLineColor) layer.powerLineColor = '#FF0000';
        if (!layer.powerArrowColor) layer.powerArrowColor = '#0042AA';
        if (layer.powerRandomColors === undefined) layer.powerRandomColors = false;
        if (layer.powerColorCodedView === undefined) layer.powerColorCodedView = false;
        layer.powerCircuitColors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
        this.normalizePowerBreakout(layer);   // a screen always carries an eligible breakout (2026-09-22)
        if (layer.powerLabelSize === undefined) layer.powerLabelSize = 14;
        if (!layer.powerLabelBgColor) layer.powerLabelBgColor = '#D95000';
        if (!layer.powerLabelTextColor) layer.powerLabelTextColor = '#000000';
        if (!layer.powerLabelTemplate) layer.powerLabelTemplate = 'S1-#';
        if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
        if (!layer.primaryTextColor) layer.primaryTextColor = '#000000';
        if (!layer.backupTextColor) layer.backupTextColor = '#FFFFFF';
        if (!layer.border_color_pixel) layer.border_color_pixel = layer.border_color || '#ffffff';
        if (!layer.border_color_cabinet) layer.border_color_cabinet = layer.border_color || '#ffffff';
        if (!layer.border_color_data) layer.border_color_data = layer.border_color || '#ffffff';
        if (!layer.border_color_power) layer.border_color_power = layer.border_color || '#ffffff';
        // v0.11.0 (step 6): cross-member path entries are NOT transient, so
        // they are deliberately not in the delete list below - they are the
        // user's hand-drawn wiring and a file is where it lives. What a file
        // cannot be trusted about is whether the peer an entry names is still
        // a reachable member of the owner's group, so the entries are
        // VALIDATED here instead of dropped. Every file path runs through
        // applyMissingLayerDefaults (File > Open and Recent Files both), and
        // this.project is already the loaded project by the time the caller
        // loops over its layers, so group membership is visible from here.
        this.sanitizeCrossLayerPaths(layer);
        // Computed/transient fields should never be trusted from file payload
        delete layer._powerError;
        delete layer._powerCircuits;
        // Per-frame render maps for cross-member circuits. A saved file can
        // carry them as `{}` (a Map does not survive JSON), and a stale empty
        // map reads as "this cabinet belongs to no circuit" until the next
        // render rebuilds it.
        delete layer._powerPanelCircuitScopedMap;
        delete layer._powerPanelIndexScopedMap;
        delete layer._powerCircuitOwners;
        delete layer._powerTotalAmps1;
        delete layer._powerTotalAmps3;
        delete layer._powerCircuitsRequired;
        delete layer._capacityError;
        delete layer._autoPortsRequired;
        delete layer._portsRequired;
        delete layer._lowLatencyDerate;
    }

    normalizeLoadedPowerFlowPattern(layer) {
        if (!layer || !Array.isArray(layer.panels) || layer.panels.length === 0) return;
        if (!layer.flowPattern || !layer.powerFlowPattern) return;
        if (layer.powerFlowPattern === 'custom') return;
        if (layer.powerFlowPattern === layer.flowPattern) return;

        const originalPattern = layer.powerFlowPattern;
        const current = this.calculatePowerAssignments(layer);
        if (!current || !current.error) return;

        layer.powerFlowPattern = layer.flowPattern;
        const migrated = this.calculatePowerAssignments(layer);
        if (migrated && !migrated.error) {
            sendClientLog('loaded_power_pattern_migrated', {
                layerId: layer.id,
                from: originalPattern,
                to: layer.flowPattern
            });
            return;
        }

        layer.powerFlowPattern = originalPattern;
    }

    // v0.11.0: NovaStar Armor used to discard portMappingMode entirely -
    // calculatePortAssignments forced Organized on it no matter what the layer
    // said. Projects saved in that window can carry 'max-capacity' on an Armor
    // screen while having been drawn (and printed) as Organized the whole time.
    // Now that Armor honours both modes, opening such a file would silently
    // redraw an already-issued map, so pin those layers back to the mode they
    // really rendered with. LOAD PATHS ONLY: switching a layer to Armor by hand
    // is a deliberate choice, and undo/redo must never re-apply this.
    // Returns the number of layers changed.
    normalizeArmorPortMapping(project) {
        if (!project || !Array.isArray(project.layers)) return 0;
        let changed = 0;
        project.layers.forEach(layer => {
            if (!layer || (layer.type || 'screen') !== 'screen') return;
            // A missing processorType renders as Armor (calculatePortAssignments
            // defaults to it), so those layers were drawn Organized too and get
            // the same treatment.
            if ((layer.processorType || 'novastar-armor') !== 'novastar-armor') return;
            if (layer.portMappingMode !== 'max-capacity') return;
            layer.portMappingMode = 'organized';
            changed++;
        });
        if (changed > 0) {
            sendClientLog('armor_port_mapping_normalized', { layers: changed });
        }
        return changed;
    }
}

for (const k of Object.getOwnPropertyNames(_ProjectIo.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ProjectIo.prototype, k));
    }
}
