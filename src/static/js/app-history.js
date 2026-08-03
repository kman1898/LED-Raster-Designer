// app-history: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _History {
    // ===== HISTORY SYSTEM =====
    resetHistory(initialAction = 'Initial State') {
        this.history = [];
        this.historyIndex = -1;
        this.saveState(initialAction);
        sendClientLog('history_reset', { action: initialAction });
    }
    
    saveState(action) {
        // v0.10.7.2: history isn't allocated until resetHistory() runs, which is
        // after setupEventListeners(). Guard against any save that fires before
        // then (e.g. a debounced picker commit flushing during setup) rather than
        // throwing on this.history.length and aborting the caller mid-setup.
        if (!Array.isArray(this.history)) return;
        // v0.10.5: a debounced snapshot still waiting to fire must land BEFORE
        // this one, or history ends up out of order (and the pending timer
        // would later snapshot a state that already includes this action).
        this._flushPendingSaveState();

        // Save current project state
        const state = {
            action: action,
            project: JSON.parse(JSON.stringify(this.project)),
            timestamp: Date.now()
        };

        
        // Remove any future states if we're not at the end
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }
        
        // Add new state
        this.history.push(state);
        
        // Limit history size
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        } else {
            this.historyIndex++;
        }
        sendClientLog('save_state', {
            action,
            historyIndex: this.historyIndex,
            historyLength: this.history.length,
            layers: this.project.layers ? this.project.layers.length : 0,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : [],
            currentLayerId: this.currentLayer ? this.currentLayer.id : null
        });

    }

    /**
     * Coalesce a continuous stream of edits (dragging a slider, typing in a
     * text field) into ONE undo step.
     *
     * `key` identifies what is being edited. When it changes, the pending
     * snapshot is flushed first so switching controls always starts a new undo
     * step instead of folding both edits together. Discrete, committed edits
     * should call saveState() directly rather than coming through here.
     */
    debouncedSaveState(action, delay = 500, key = null) {
        const k = key || action;
        if (this._saveStateTimer && this._pendingSaveKey !== k) {
            this._flushPendingSaveState();
        }
        this._pendingSaveAction = action;
        this._pendingSaveKey = k;
        if (this._saveStateTimer) clearTimeout(this._saveStateTimer);
        this._saveStateTimer = setTimeout(() => {
            this._saveStateTimer = null;
            const pending = this._pendingSaveAction || action;
            this._pendingSaveAction = null;
            this._pendingSaveKey = null;
            this.saveState(pending);
        }, delay);
    }

    /**
     * Commit a pending debounced snapshot immediately. Clearing the timer
     * first keeps saveState()'s own flush call from recursing.
     */
    _flushPendingSaveState() {
        if (!this._saveStateTimer) return;
        clearTimeout(this._saveStateTimer);
        this._saveStateTimer = null;
        const pending = this._pendingSaveAction;
        this._pendingSaveAction = null;
        this._pendingSaveKey = null;
        if (pending) this.saveState(pending);
    }

    undo() {
        // Land any in-flight debounced snapshot first, so Ctrl+Z steps back
        // over the edit the user just made instead of skipping past it (and
        // so the timer can't overwrite the restored state a moment later).
        this._flushPendingSaveState();

        if (this.historyIndex > 0) {
            this.historyIndex--;
            const state = this.history[this.historyIndex];
            
            
            this.project = JSON.parse(JSON.stringify(state.project));
            this.dedupeProjectLayers('undo_restore');
            sendClientLog('undo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            // Update current layer reference
            if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || null;
            }
            this.updateCustomFlowUI();
            // v0.10.7.2: updateUI() re-renders the canvas but does NOT reload the
            // Screen Info fields or the toolbar Raster inputs, so without this an
            // undo/redo reverts the geometry while the sidebar keeps showing the
            // pre-undo numbers (panel size / columns / rows / raster) - the value
            // and the actual size disagree. Refresh them from the restored state,
            // exactly as deleteCurrentLayer already does for the same reason.
            if (typeof this.loadLayerToInputs === 'function') {
                try { this.loadLayerToInputs(); } catch (_) {}
            }
            if (typeof this.syncRasterFromProject === 'function') {
                try { this.syncRasterFromProject(); } catch (_) {}
            }
            
            // Sync the restored state to the backend
            fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.project)
            })
            .then(response => {
                return response.json();
            })
            .then(() => {
                this.updateUI();
            })
            .catch(error => {
                console.error('Undo backend sync failed:', error);
            });
        } else {
        }
    }
    
    redo() {
        this._flushPendingSaveState();

        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            const state = this.history[this.historyIndex];
            
            
            this.project = JSON.parse(JSON.stringify(state.project));
            this.dedupeProjectLayers('redo_restore');
            sendClientLog('redo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            // Update current layer reference
            if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || null;
            }
            this.updateCustomFlowUI();
            // v0.10.7.2: updateUI() re-renders the canvas but does NOT reload the
            // Screen Info fields or the toolbar Raster inputs, so without this an
            // undo/redo reverts the geometry while the sidebar keeps showing the
            // pre-undo numbers (panel size / columns / rows / raster) - the value
            // and the actual size disagree. Refresh them from the restored state,
            // exactly as deleteCurrentLayer already does for the same reason.
            if (typeof this.loadLayerToInputs === 'function') {
                try { this.loadLayerToInputs(); } catch (_) {}
            }
            if (typeof this.syncRasterFromProject === 'function') {
                try { this.syncRasterFromProject(); } catch (_) {}
            }
            
            // Sync the restored state to the backend
            fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.project)
            })
            .then(response => {
                return response.json();
            })
            .then(() => {
                this.updateUI();
            })
            .catch(error => {
                console.error('Redo backend sync failed:', error);
            });
        } else {
        }
    }
    
    // ===== DELETE LAYER =====
    
    deleteCurrentLayer() {
        
        if (!this.currentLayer || this.deletionInProgress) {
            return;
        }
        
        // Collect all selected layer IDs to delete
        const idsToDelete = this.selectedLayerIds && this.selectedLayerIds.size > 1
            ? [...this.selectedLayerIds]
            : [this.currentLayer.id];
        
        // Don't delete if it would remove ALL layers
        if (idsToDelete.length >= this.project.layers.length) {
            // Keep at least one layer
            if (this.project.layers.length <= 1) return;
            idsToDelete.pop(); // Remove last one from delete list to keep it
        }
        
        this.deletionInProgress = true;
        // The 'Delete Layer' snapshot is taken AFTER the deletes land, at the
        // bottom of deleteNext(), not here. Taken here it held the project
        // WITH the screen still in it, so redo restored the screen instead of
        // removing it: Delete -> Ctrl+Z -> Ctrl+Shift+Z left the screen on
        // screen with no way to get the delete back except doing it again.
        // Snapshotting after the mutation is what every other action in the
        // app does, and it leaves the undo side untouched - one Ctrl+Z still
        // lands on the previous entry, which still holds the edit made before
        // the delete.

        // Find index of current layer for post-delete selection
        const currentIndex = this.project.layers.findIndex(l => l.id === this.currentLayer.id);
        this.currentLayer = null;
        
        // Delete all selected layers sequentially
        const deleteNext = (ids) => {
            if (ids.length === 0) {
                // All deletes done - refresh project
                fetch('/api/project')
                    .then(res => res.json())
                    .then(project => {
                        this.project = project;
                        this.dedupeProjectLayers('delete_layer');
                        
                        if (this.project.layers.length > 0) {
                            const newIndex = Math.min(currentIndex, this.project.layers.length - 1);
                            this.currentLayer = this.project.layers[newIndex];
                            this.selectedLayerIds = new Set([this.currentLayer.id]);
                            this.lastSelectedLayerId = this.currentLayer.id;
                            this.selectionAnchorLayerId = this.currentLayer.id;
                        } else {
                            this.currentLayer = null;
                            this.selectedLayerIds = new Set();
                            this.lastSelectedLayerId = null;
                            this.selectionAnchorLayerId = null;
                        }

                        // v0.8.7.6: refresh the layer-property inputs from
                        // the newly-promoted currentLayer. Without this the
                        // sidebar keeps showing the DELETED layer's
                        // cabinet_width / cabinet_height / columns / rows /
                        // etc., and the next "Update Properties" round-trip
                        // reads those stale values out of the inputs and
                        // writes them onto the surviving layer, clobbering
                        // its actual panel dimensions while the on-canvas
                        // panels stay sized correctly (because the panel
                        // geometry is already baked into layer.panels).
                        // Repro that exposed this: add a VN-8.3 preset
                        // screen (cabinet 60x120), delete the default
                        // Brompton screen (cabinet 192x384), edit the
                        // surviving screen's column count → its cabinet
                        // silently flipped to 192x384.
                        if (this.currentLayer && typeof this.loadLayerToInputs === 'function') {
                            try { this.loadLayerToInputs(); } catch (_) {}
                        }
                        // Post-mutation snapshot: this entry is the project
                        // WITHOUT the deleted screen, so redo re-applies the
                        // delete. See the note where deletionInProgress is
                        // set.
                        this.saveState('Delete Layer');
                        this.updateUI();
                    })
                    .finally(() => {
                        this.deletionInProgress = false;
                    });
                return;
            }
            
            const id = ids.shift();
            sendClientLog('delete_layer', { id: id, name: (this.project.layers.find(l => l.id === id) || {}).name });
            
            fetch(`/api/layer/${id}`, { method: 'DELETE' })
                .then(res => res.json())
                .then(project => {
                    this.project = project;
                    deleteNext(ids);
                })
                .catch(error => {
                    console.error('DELETE failed:', error);
                    deleteNext(ids); // Continue with remaining deletes
                });
        };
        
        deleteNext([...idsToDelete]);
    }
    
    // ===== CROSS-MEMBER MANUAL PATHS: WHAT A COPY IS ALLOWED TO CARRY =====
    //
    // v0.10.9 (step 6): an entry in customPortPaths / powerCustomPaths is
    // normally {row, col} - a panel in the layer that OWNS the path, which is
    // how 100% of projects written before this step look. A path hand-drawn
    // across a group's members stores {row, col, layerId} for the panels that
    // live in a PEER member.
    //
    // A layer id only means something inside the project that minted it, so
    // every copy operation has to answer one question per entry: does the
    // layer this entry names come along with the copy?
    //
    //   it does     -> rewrite the entry to point at ITS copy (via idMap), so
    //                  a user who duplicates a wall gets their wiring with it
    //   it does not -> DROP the entry
    //
    // Dropping rather than keeping, because an id that survives into a context
    // where it means something ELSE is the worst outcome on the table: the
    // wiring silently re-attaches to an unrelated screen and nothing errors.
    // A path missing a panel is visible the moment the user looks at it; a
    // path wired to the wrong wall is not.
    //
    // An entry naming the SOURCE OWNER itself becomes a plain {row, col}. The
    // writer normalises that away (see makePathEntry), but a hand-edited file
    // can still hold one, and "this layer" stays true after a copy whatever id
    // the copy ends up with - which is also why this works for duplicate/paste,
    // where the new id does not exist until the server answers.
    //
    // A path that loses SOME entries keeps the rest: it is a route the user
    // drew, and the part still inside the copy is still their route. A path
    // that loses ALL of them is removed key and all - an empty path is not a
    // path, and a leftover `{"3": []}` would advertise port 3 as hand-routed
    // with nothing drawn.
    //
    // `idMap` is a Map (or plain object) of source layer id -> copy layer id,
    // or null/omitted when nothing but the owner is being copied.
    copyPathsForNewOwner(paths, sourceOwnerId, idMap) {
        const out = {};
        if (!paths || typeof paths !== 'object') return out;
        const mapId = (oldId) => {
            if (!idMap) return undefined;
            return (idMap instanceof Map) ? idMap.get(oldId) : idMap[oldId];
        };
        const newOwnerId = (sourceOwnerId != null) ? mapId(sourceOwnerId) : undefined;
        Object.keys(paths).forEach(key => {
            const path = paths[key];
            if (!Array.isArray(path)) {
                // Not a path at all (older or hand-edited payload). Carry it
                // verbatim rather than inventing a shape for it - this branch
                // is the pre-step-6 deep copy, unchanged.
                out[key] = JSON.parse(JSON.stringify(path));
                return;
            }
            const kept = [];
            path.forEach(entry => {
                if (!entry || typeof entry !== 'object') {
                    // Nothing to validate - carry it as the old deep copy did.
                    kept.push(entry);
                    return;
                }
                if (entry.layerId === undefined || entry.layerId === null) {
                    kept.push({ ...entry });   // "this layer" - always travels
                    return;
                }
                if (entry.layerId === sourceOwnerId) {
                    const normalised = { ...entry };
                    delete normalised.layerId;
                    kept.push(normalised);
                    return;
                }
                const remapped = mapId(entry.layerId);
                if (remapped === undefined || remapped === null) return;  // dropped
                if (newOwnerId !== undefined && remapped === newOwnerId) {
                    const normalised = { ...entry };
                    delete normalised.layerId;
                    kept.push(normalised);
                    return;
                }
                kept.push({ ...entry, layerId: remapped });
            });
            if (kept.length > 0) out[key] = kept;
        });
        return out;
    }

    // The whole-wall shape of the same rule: N layers copied TOGETHER, so a
    // path reaching a peer inside the copied set is rewritten to that peer's
    // copy and the wiring survives intact. Anything reaching outside the set
    // is dropped by copyPathsForNewOwner above.
    //
    // `pairs` is [{ source, clone }, ...]. Callers that copy a whole group
    // hand over every member and its clone at once, which is the only moment
    // the source -> copy mapping exists.
    remapCopiedLayerPaths(pairs) {
        const list = (pairs || []).filter(p => p && p.source && p.clone);
        if (list.length === 0) return 0;
        const idMap = new Map(list.map(p => [p.source.id, p.clone.id]));
        list.forEach(({ source, clone }) => {
            clone.customPortPaths = this.copyPathsForNewOwner(
                source.customPortPaths, source.id, idMap);
            clone.powerCustomPaths = this.copyPathsForNewOwner(
                source.powerCustomPaths, source.id, idMap);
        });
        return list.length;
    }

    // ===== DUPLICATE LAYER =====

    duplicateLayer(layer) {
        // Smart name incrementing
        const getNextName = (baseName) => {
            // Check if name ends with a number
            const match = baseName.match(/^(.*?)(\d+)$/);
            
            if (match) {
                // Name ends with number (e.g., "Screen1" or "Nvidia12")
                const base = match[1];
                const num = parseInt(match[2]);
                return `${base}${num + 1}`;
            } else {
                // Name doesn't end with number (e.g., "Nvidia")
                return `${baseName} 1`;
            }
        };

        // v0.8.6.3: helper to carry Show Look state across duplicate/paste
        // so a layer dragged in Show Look (showOffset / show_canvas_id) is
        // copied with its Show Look position intact, not snapped back to
        // mirror Pixel Map.
        //
        // v0.10.9: `group_id` is deliberately absent from this helper and
        // from duplicateData / clientProps below. Duplicating a screen makes
        // a new screen; enrolling it in the source's group would change that
        // group's totals, port numbering and export the moment the user hits
        // Duplicate, without them asking. The server's create_layer defaults
        // group_id to null, so omitting it here is the whole mechanism.
        const _carryShow = (l, dx, dy) => {
            const out = {};
            if (l.showOffsetX != null) out.showOffsetX = (Number(l.showOffsetX) || 0) + (dx || 0);
            if (l.showOffsetY != null) out.showOffsetY = (Number(l.showOffsetY) || 0) + (dy || 0);
            if (l.show_canvas_id) out.show_canvas_id = l.show_canvas_id;
            return out;
        };

        if ((layer.type || 'screen') === 'image') {
            const duplicateData = {
                name: getNextName(layer.name),
                imageData: layer.imageData,
                imageWidth: layer.imageWidth,
                imageHeight: layer.imageHeight,
                imageScale: layer.imageScale || 1.0,
                offset_x: layer.offset_x + 50,
                offset_y: layer.offset_y + 50,
                ..._carryShow(layer, 50, 50),
            };
            fetch('/api/layer/add-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(duplicateData)
            })
            .then(res => res.json())
            .then(newLayer => {
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Duplicate Image Layer');
            });
            return;
        }

        if ((layer.type || 'screen') === 'text') {
            const duplicateData = {
                name: getNextName(layer.name),
                offset_x: (layer.offset_x || 0) + 50,
                offset_y: (layer.offset_y || 0) + 50,
                textContent: layer.textContent || '',
                textContentPixelMap: layer.textContentPixelMap || '',
                textContentCabinetId: layer.textContentCabinetId || '',
                textContentShowLook: layer.textContentShowLook || '',
                textContentDataFlow: layer.textContentDataFlow || '',
                textContentPower: layer.textContentPower || '',
                textContentOverridePixelMap: !!layer.textContentOverridePixelMap,
                textContentOverrideCabinetId: !!layer.textContentOverrideCabinetId,
                textContentOverrideShowLook: !!layer.textContentOverrideShowLook,
                textContentOverrideDataFlow: !!layer.textContentOverrideDataFlow,
                textContentOverridePower: !!layer.textContentOverridePower,
                textWidth: layer.textWidth || 400,
                textHeight: layer.textHeight || 100,
                fontSize: layer.fontSize || 24,
                fontFamily: layer.fontFamily || 'Arial',
                fontColor: layer.fontColor || '#ffffff',
                bgColor: layer.bgColor || '#000000',
                bgOpacity: layer.bgOpacity != null ? layer.bgOpacity : 0.7,
                textAlign: layer.textAlign || 'left',
                textPadding: layer.textPadding || 12,
                showBorder: layer.showBorder !== false,
                borderColor: layer.borderColor || '#555555',
                showOnPixelMap: layer.showOnPixelMap !== false,
                showOnCabinetId: layer.showOnCabinetId !== false,
                showOnShowLook: layer.showOnShowLook !== false,
                showOnDataFlow: layer.showOnDataFlow !== false,
                showOnPower: layer.showOnPower !== false,
                showRasterSize: !!layer.showRasterSize,
                showProjectName: !!layer.showProjectName,
                showDate: !!layer.showDate,
                showPrimaryPorts: !!layer.showPrimaryPorts,
                showBackupPorts: !!layer.showBackupPorts,
                showCircuits: !!layer.showCircuits,
                showSinglePhase: !!layer.showSinglePhase,
                showThreePhase: !!layer.showThreePhase,
                fontBold: !!layer.fontBold,
                fontItalic: !!layer.fontItalic,
                fontUnderline: !!layer.fontUnderline,
                ..._carryShow(layer, 50, 50),
            };
            fetch('/api/layer/add-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(duplicateData)
            })
            .then(res => res.json())
            .then(newLayer => {
                // Copy text properties to new layer
                Object.assign(newLayer, duplicateData);
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Duplicate Text Layer');
            });
            return;
        }

        // Collect hidden panel positions (row, col) to apply to new layer.
        // Backwards-compat: older server builds only knew about hiddenPanels.
        const hiddenPanels = layer.panels
            .filter(p => p.hidden)
            .map(p => ({ row: p.row, col: p.col }));
        // v0.8.0 fix: half-tile state was being lost on duplicate. Build a
        // full per-panel state list (halfTile + hidden + blank) so the
        // server can rebuild the duplicate's geometry to match the source.
        const panelStates = layer.panels
            .filter(p => p.hidden || p.blank || (p.halfTile && p.halfTile !== 'none'))
            .map(p => ({
                row: p.row,
                col: p.col,
                halfTile: p.halfTile || 'none',
                hidden: !!p.hidden,
                blank: !!p.blank,
            }));

        // v0.10.9 (step 6): Duplicate makes a NEW, UNGROUPED screen - that is
        // the same decision the group_id note above documents. Nothing but this
        // layer is being copied, so no peer named by a cross-member path entry
        // has a counterpart here and every such entry drops (idMap = null).
        // Keeping them would leave the copy's wiring pointing at the ORIGINAL
        // wall's cabinets while the copy is not even in that wall's group.
        // Plain {row, col} paths - every pre-step-6 project - come through
        // copyPathsForNewOwner untouched.
        const dupPowerCustomPaths = this.copyPathsForNewOwner(
            layer.powerCustomPaths, layer.id, null);
        const dupCustomPortPaths = this.copyPathsForNewOwner(
            layer.customPortPaths, layer.id, null);

        const duplicateData = {
            name: getNextName(layer.name),
            columns: layer.columns,
            rows: layer.rows,
            cabinet_width: layer.cabinet_width,
            cabinet_height: layer.cabinet_height,
            offset_x: layer.offset_x + 50, // Offset by 50px
            offset_y: layer.offset_y + 50,
            color1: layer.color1,
            color2: layer.color2,
            panel_width_mm: layer.panel_width_mm,
            panel_height_mm: layer.panel_height_mm,
            panel_weight: layer.panel_weight,
            weight_unit: layer.weight_unit,
            halfFirstColumn: !!layer.halfFirstColumn,
            halfLastColumn: !!layer.halfLastColumn,
            halfFirstRow: !!layer.halfFirstRow,
            halfLastRow: !!layer.halfLastRow,
            show_numbers: layer.show_numbers,
            number_size: layer.number_size,
            show_panel_borders: layer.show_panel_borders,
            panel_border_width: layer.panel_border_width,
            show_circle_with_x: layer.show_circle_with_x,
            border_color: layer.border_color,
            border_width: layer.border_width,
            cabinetIdStyle: layer.cabinetIdStyle,
            cabinetIdPosition: layer.cabinetIdPosition,
            cabinetIdColor: layer.cabinetIdColor,
            showLabelName: layer.showLabelName,
            showLabelNameCabinet: layer.showLabelNameCabinet,
            showLabelNameDataFlow: layer.showLabelNameDataFlow,
            showLabelNamePower: layer.showLabelNamePower,
            showLabelSizePx: layer.showLabelSizePx,
            showLabelSizeM: layer.showLabelSizeM,
            showLabelSizeFt: layer.showLabelSizeFt,
            showLabelWeight: layer.showLabelWeight,
            showLabelInfo: layer.showLabelInfo,
            labelsColor: layer.labelsColor,
            labelsFontSize: layer.labelsFontSize,
            infoLabelSize: layer.infoLabelSize,
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showOffsetTL: layer.showOffsetTL,
            showOffsetTR: layer.showOffsetTR,
            showOffsetBL: layer.showOffsetBL,
            showOffsetBR: layer.showOffsetBR,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerAmperage: layer.powerAmperage,
            powerAmperageCustom: layer.powerAmperageCustom,
            panelWatts: layer.panelWatts,
            powerMaximize: !!layer.powerMaximize,
            powerOrganized: !!layer.powerOrganized,
            powerCustomPath: !!layer.powerCustomPath,
            powerFlowPattern: layer.powerFlowPattern,
            powerLineWidth: layer.powerLineWidth,
            powerLineColor: layer.powerLineColor,
            powerArrowColor: layer.powerArrowColor,
            powerRandomColors: !!layer.powerRandomColors,
            powerColorCodedView: !!layer.powerColorCodedView,
            powerCircuitColors: JSON.parse(JSON.stringify(layer.powerCircuitColors || {})),
            powerLabelSize: layer.powerLabelSize,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(layer.powerLabelOverrides || {})),
            powerCustomPaths: dupPowerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            hiddenPanels: hiddenPanels,  // Pass hidden panel info (legacy)
            panelStates: panelStates,    // Half-tile + hidden + blank (v0.8.0)
        };
        
        // Store client-side properties to copy after layer is created
        const clientProps = {
            arrowLineWidth: layer.arrowLineWidth,
            arrowColor: layer.arrowColor,
            dataFlowColor: layer.dataFlowColor,
            dataFlowLabelSize: layer.dataFlowLabelSize,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            flowPattern: layer.flowPattern,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate,
            processorType: layer.processorType,
            lowLatency: layer.lowLatency,
            portMappingMode: layer.portMappingMode,
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
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
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
            powerCircuitColors: JSON.parse(JSON.stringify(layer.powerCircuitColors || {})),
            powerLabelSize: layer.powerLabelSize,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(layer.powerLabelOverrides || {})),
            powerCustomPaths: dupPowerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showDataFlowPortInfo: !!layer.showDataFlowPortInfo,
            showDataFlowPortLoad: !!layer.showDataFlowPortLoad,
            weight_unit: layer.weight_unit,
            panel_weight: layer.panel_weight,
            infoLabelSize: layer.infoLabelSize,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: JSON.parse(JSON.stringify(layer.portLabelOverridesPrimary || {})),
            portLabelOverridesReturn: JSON.parse(JSON.stringify(layer.portLabelOverridesReturn || {})),
            customPortPaths: dupCustomPortPaths,
            customPortIndex: layer.customPortIndex,
            randomDataColors: !!layer.randomDataColors,
            arrowSize: layer.arrowSize,
            ..._carryShow(layer, 50, 50),
        };

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(duplicateData)
        })
        .then(res => res.json())
        .then(newLayer => {
            // Copy client-side properties to new layer
            Object.assign(newLayer, clientProps);
            
            sendClientLog('duplicate_layer', {
                sourceId: layer.id, sourceName: layer.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });
            
            this.upsertProjectLayer(newLayer);
            this.selectLayer(newLayer);
            this.updateUI();
            
            // Save client-side properties
            this.saveClientSideProperties();
            
            // Save state AFTER duplicate completes
            this.saveState('Duplicate Layer');
        });
    }
    
    // ===== COPY/PASTE =====
    
    copyLayer() {
        if (!this.currentLayer) return;
        
        this.clipboard = JSON.parse(JSON.stringify(this.currentLayer));
        sendClientLog('copy_layer', {
            id: this.currentLayer.id,
            name: this.currentLayer.name,
            type: this.currentLayer.type || 'screen'
        });
    }
    
    pasteLayer() {
        if (!this.clipboard) return;

        // Smart name incrementing (same logic as duplicate)
        const getNextName = (baseName) => {
            const match = baseName.match(/^(.*?)(\d+)$/);
            if (match) {
                const base = match[1];
                const num = parseInt(match[2]);
                return `${base}${num + 1}`;
            } else {
                return `${baseName} 1`;
            }
        };

        // v0.8.6.3: same Show Look carry-over as duplicateLayer.
        const _carryShow = (l, dx, dy) => {
            const out = {};
            if (l.showOffsetX != null) out.showOffsetX = (Number(l.showOffsetX) || 0) + (dx || 0);
            if (l.showOffsetY != null) out.showOffsetY = (Number(l.showOffsetY) || 0) + (dy || 0);
            if (l.show_canvas_id) out.show_canvas_id = l.show_canvas_id;
            return out;
        };

        if ((this.clipboard.type || 'screen') === 'image') {
            const pasteData = {
                name: getNextName(this.clipboard.name),
                imageData: this.clipboard.imageData,
                imageWidth: this.clipboard.imageWidth,
                imageHeight: this.clipboard.imageHeight,
                imageScale: this.clipboard.imageScale || 1.0,
                offset_x: (this.clipboard.offset_x || 0) + 50,
                offset_y: (this.clipboard.offset_y || 0) + 50,
                ..._carryShow(this.clipboard, 50, 50),
            };
            fetch('/api/layer/add-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pasteData)
            })
            .then(res => res.json())
            .then(newLayer => {
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Paste Image Layer');
            });
            return;
        }

        if ((this.clipboard.type || 'screen') === 'text') {
            const pasteData = {
                name: getNextName(this.clipboard.name),
                offset_x: (this.clipboard.offset_x || 0) + 50,
                offset_y: (this.clipboard.offset_y || 0) + 50,
                textContent: this.clipboard.textContent || '',
                textContentPixelMap: this.clipboard.textContentPixelMap || '',
                textContentCabinetId: this.clipboard.textContentCabinetId || '',
                textContentShowLook: this.clipboard.textContentShowLook || '',
                textContentDataFlow: this.clipboard.textContentDataFlow || '',
                textContentPower: this.clipboard.textContentPower || '',
                textContentOverridePixelMap: !!this.clipboard.textContentOverridePixelMap,
                textContentOverrideCabinetId: !!this.clipboard.textContentOverrideCabinetId,
                textContentOverrideShowLook: !!this.clipboard.textContentOverrideShowLook,
                textContentOverrideDataFlow: !!this.clipboard.textContentOverrideDataFlow,
                textContentOverridePower: !!this.clipboard.textContentOverridePower,
                textWidth: this.clipboard.textWidth || 400,
                textHeight: this.clipboard.textHeight || 100,
                fontSize: this.clipboard.fontSize || 24,
                fontFamily: this.clipboard.fontFamily || 'Arial',
                fontColor: this.clipboard.fontColor || '#ffffff',
                bgColor: this.clipboard.bgColor || '#000000',
                bgOpacity: this.clipboard.bgOpacity != null ? this.clipboard.bgOpacity : 0.7,
                textAlign: this.clipboard.textAlign || 'left',
                textPadding: this.clipboard.textPadding || 12,
                showBorder: this.clipboard.showBorder !== false,
                borderColor: this.clipboard.borderColor || '#555555',
                showOnPixelMap: this.clipboard.showOnPixelMap !== false,
                showOnCabinetId: this.clipboard.showOnCabinetId !== false,
                showOnShowLook: this.clipboard.showOnShowLook !== false,
                showOnDataFlow: this.clipboard.showOnDataFlow !== false,
                showOnPower: this.clipboard.showOnPower !== false,
                showRasterSize: !!this.clipboard.showRasterSize,
                showProjectName: !!this.clipboard.showProjectName,
                showDate: !!this.clipboard.showDate,
                showPrimaryPorts: !!this.clipboard.showPrimaryPorts,
                showBackupPorts: !!this.clipboard.showBackupPorts,
                showCircuits: !!this.clipboard.showCircuits,
                showSinglePhase: !!this.clipboard.showSinglePhase,
                showThreePhase: !!this.clipboard.showThreePhase,
                fontBold: !!this.clipboard.fontBold,
                fontItalic: !!this.clipboard.fontItalic,
                fontUnderline: !!this.clipboard.fontUnderline,
                ..._carryShow(this.clipboard, 50, 50),
            };
            fetch('/api/layer/add-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pasteData)
            })
            .then(res => res.json())
            .then(newLayer => {
                Object.assign(newLayer, pasteData);
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Paste Text Layer');
            });
            return;
        }

        // v0.10.9 (step 6): paste is the same drop as duplicate, for a harder
        // reason. The clipboard outlives the project it was filled from - copy
        // a screen, open another file, paste - and layer ids are per project
        // and reused freely across them. A cross-member entry pasted into a
        // different project would name whatever screen happens to hold that id
        // there, so the pasted wall's port would quietly claim cabinets on an
        // unrelated screen with nothing to show the user it had happened.
        //
        // We cannot tell the two cases apart from here (the clipboard is a
        // plain deep copy, with no record of which project it came from), so
        // paste takes the conservative branch every time: only the peers being
        // pasted WITH it could be remapped, and paste copies exactly one layer,
        // so nothing is. Plain {row, col} paths paste unchanged.
        const pastePowerCustomPaths = this.copyPathsForNewOwner(
            this.clipboard.powerCustomPaths, this.clipboard.id, null);
        const pasteCustomPortPaths = this.copyPathsForNewOwner(
            this.clipboard.customPortPaths, this.clipboard.id, null);

        const pasteData = {
            name: getNextName(this.clipboard.name),
            columns: this.clipboard.columns,
            rows: this.clipboard.rows,
            cabinet_width: this.clipboard.cabinet_width,
            cabinet_height: this.clipboard.cabinet_height,
            offset_x: this.clipboard.offset_x + 50,
            offset_y: this.clipboard.offset_y + 50,
            color1: this.clipboard.color1,
            color2: this.clipboard.color2,
            panel_width_mm: this.clipboard.panel_width_mm,
            panel_height_mm: this.clipboard.panel_height_mm,
            panel_weight: this.clipboard.panel_weight,
            weight_unit: this.clipboard.weight_unit,
            halfFirstColumn: !!this.clipboard.halfFirstColumn,
            halfLastColumn: !!this.clipboard.halfLastColumn,
            halfFirstRow: !!this.clipboard.halfFirstRow,
            halfLastRow: !!this.clipboard.halfLastRow,
            show_numbers: this.clipboard.show_numbers,
            number_size: this.clipboard.number_size,
            show_panel_borders: this.clipboard.show_panel_borders,
            panel_border_width: this.clipboard.panel_border_width,
            show_circle_with_x: this.clipboard.show_circle_with_x,
            border_color: this.clipboard.border_color,
            cabinetIdStyle: this.clipboard.cabinetIdStyle,
            cabinetIdPosition: this.clipboard.cabinetIdPosition,
            cabinetIdColor: this.clipboard.cabinetIdColor,
            showLabelName: this.clipboard.showLabelName,
            showLabelNameCabinet: this.clipboard.showLabelNameCabinet,
            showLabelNameDataFlow: this.clipboard.showLabelNameDataFlow,
            showLabelNamePower: this.clipboard.showLabelNamePower,
            showLabelSizePx: this.clipboard.showLabelSizePx,
            showLabelSizeM: this.clipboard.showLabelSizeM,
            showLabelSizeFt: this.clipboard.showLabelSizeFt,
            showLabelWeight: this.clipboard.showLabelWeight,
            showLabelInfo: this.clipboard.showLabelInfo,
            labelsColor: this.clipboard.labelsColor,
            labelsFontSize: this.clipboard.labelsFontSize,
            infoLabelSize: this.clipboard.infoLabelSize,
            showPowerCircuitInfo: !!this.clipboard.showPowerCircuitInfo,
            showOffsetTL: this.clipboard.showOffsetTL,
            showOffsetTR: this.clipboard.showOffsetTR,
            showOffsetBL: this.clipboard.showOffsetBL,
            showOffsetBR: this.clipboard.showOffsetBR,
            powerVoltage: this.clipboard.powerVoltage,
            powerVoltageCustom: this.clipboard.powerVoltageCustom,
            powerAmperage: this.clipboard.powerAmperage,
            powerAmperageCustom: this.clipboard.powerAmperageCustom,
            panelWatts: this.clipboard.panelWatts,
            powerMaximize: !!this.clipboard.powerMaximize,
            powerOrganized: !!this.clipboard.powerOrganized,
            powerCustomPath: !!this.clipboard.powerCustomPath,
            powerFlowPattern: this.clipboard.powerFlowPattern,
            powerLineWidth: this.clipboard.powerLineWidth,
            powerLineColor: this.clipboard.powerLineColor,
            powerArrowColor: this.clipboard.powerArrowColor,
            powerRandomColors: !!this.clipboard.powerRandomColors,
            powerColorCodedView: !!this.clipboard.powerColorCodedView,
            powerCircuitColors: JSON.parse(JSON.stringify(this.clipboard.powerCircuitColors || {})),
            powerLabelSize: this.clipboard.powerLabelSize,
            powerLabelBgColor: this.clipboard.powerLabelBgColor,
            powerLabelTextColor: this.clipboard.powerLabelTextColor,
            powerLabelTemplate: this.clipboard.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(this.clipboard.powerLabelOverrides || {})),
            powerCustomPaths: pastePowerCustomPaths,
            powerCustomIndex: this.clipboard.powerCustomIndex,
            showDataFlowPortInfo: !!this.clipboard.showDataFlowPortInfo,
            showDataFlowPortLoad: !!this.clipboard.showDataFlowPortLoad,
            portLabelTemplatePrimary: this.clipboard.portLabelTemplatePrimary,
            portLabelTemplateReturn: this.clipboard.portLabelTemplateReturn,
            portLabelOverridesPrimary: JSON.parse(JSON.stringify(this.clipboard.portLabelOverridesPrimary || {})),
            portLabelOverridesReturn: JSON.parse(JSON.stringify(this.clipboard.portLabelOverridesReturn || {})),
            customPortPaths: pasteCustomPortPaths,
            customPortIndex: this.clipboard.customPortIndex,
            randomDataColors: !!this.clipboard.randomDataColors,
            arrowSize: this.clipboard.arrowSize,
            ..._carryShow(this.clipboard, 50, 50),
        };
        const pasteClientProps = {
            border_color_pixel: this.clipboard.border_color_pixel,
            border_color_cabinet: this.clipboard.border_color_cabinet,
            border_color_data: this.clipboard.border_color_data,
            border_color_power: this.clipboard.border_color_power,
            primaryTextColor: this.clipboard.primaryTextColor,
            backupTextColor: this.clipboard.backupTextColor,
            powerLabelBgColor: this.clipboard.powerLabelBgColor,
            powerLabelTextColor: this.clipboard.powerLabelTextColor
        };
        
        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pasteData)
        })
        .then(res => res.json())
        .then(newLayer => {
            Object.assign(newLayer, pasteClientProps);
            sendClientLog('paste_layer', {
                sourceId: this.clipboard.id, sourceName: this.clipboard.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });
            this.upsertProjectLayer(newLayer);
            this.selectLayer(newLayer);
            this.updateUI();
            
            // Save state AFTER paste completes
            this.saveState('Paste Layer');
        });
    }
    
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 255, g: 0, b: 0 };
    }

    // Evaluate a simple arithmetic expression using + - * / and parentheses.
    // Returns a finite number, or null if the input is empty/invalid. Used by
    // the Watts per Panel field (and anywhere else we want a "spreadsheet-y"
    // numeric input) so users can type e.g. "200+50" or "1000/3" directly.
    evaluateNumericExpression(raw) {
        if (raw == null) return null;
        const s = String(raw).trim();
        if (s === '') return null;
        // Allow only digits, . , whitespace, and the four operators + - * / plus parentheses
        const cleaned = s.replace(/,/g, '').replace(/\s+/g, '');
        if (!/^[-+*/().\d]+$/.test(cleaned)) return null;
        // Reject dangerous patterns (consecutive operators other than a leading unary minus in a sub-expr)
        if (/[*/]{2,}|\+{2,}|-{3,}|[-+*/]$|^[*/]/.test(cleaned)) return null;
        try {
            // Function constructor with no scope access, still safer than eval(),
            // and the regex above guarantees only arithmetic characters are present.
            // eslint-disable-next-line no-new-func
            const result = Function('"use strict"; return (' + cleaned + ');')();
            if (typeof result !== 'number' || !isFinite(result)) return null;
            return result;
        } catch (e) {
            return null;
        }
    }

    // Format an evaluated number for display in the input: drop trailing zeros
    // but keep reasonable precision for fractional results (e.g. 1000/3).
    _formatEvaluatedNumber(n) {
        if (!isFinite(n)) return '0';
        if (Number.isInteger(n)) return String(n);
        // Up to 4 decimal places, trim trailing zeros
        return parseFloat(n.toFixed(4)).toString();
    }
    
    rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
}

for (const k of Object.getOwnPropertyNames(_History.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_History.prototype, k));
    }
}
