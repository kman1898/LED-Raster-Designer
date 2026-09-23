// app-clipboard: duplicate, copy and paste for LEDRasterApp - the
// clipboard model, the smart-increment naming a copy gets, and the
// cross-member path rewriting (copyPathsForNewOwner /
// remapCopiedLayerPaths) that decides what wiring a copy is allowed to
// carry. Undo / redo and delete stay in app-history.js.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// Carry an image layer's Drop Shadow and Opacity onto its duplicate / paste.
// /api/layer/add-image only stores what it is sent, so a field left out here
// gives the copy a shadow in the browser and none on the server - right until
// the next reload, the way the gradient block used to be lost.
const IMAGE_SHADOW_KEYS = [
    'imageShadowEnabled', 'imageShadowColor', 'imageShadowOpacity',
    'imageShadowAngle', 'imageShadowDistance', 'imageShadowSpread',
    'imageShadowSize',
    'imageOpacity',
];

function _carryImageShadow(layer) {
    const out = {};
    IMAGE_SHADOW_KEYS.forEach(k => {
        if (layer && layer[k] !== undefined) out[k] = layer[k];
    });
    return out;
}

class _Clipboard {
    // ===== CROSS-MEMBER MANUAL PATHS: WHAT A COPY IS ALLOWED TO CARRY =====
    //
    // v0.11.0 (step 6): an entry in customPortPaths / powerCustomPaths is
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
            // Per-run overrides ride with their paths; plain number arrays,
            // nothing in them names a peer.
            clone.customPortOverrides = (source.customPortOverrides || []).slice();
            clone.powerCustomOverrides = (source.powerCustomOverrides || []).slice();
        });
        return list.length;
    }

    // ===== DUPLICATE LAYER =====

    duplicateLayer(layer) {
        // A GROUP IS ONE SCREEN, so Duplicate aimed at a whole selected wall
        // copies the WALL - every member, into one new group - through the
        // same duplicateGroup the group ⋮ menu uses. Every path that
        // duplicates arrives here (Cmd/Ctrl+J in canvas.js, the canvas
        // context menu and the menu bar via handleMenuAction('duplicate')),
        // and each of them hands over currentLayer alone; that is why a
        // three-screen wall used to come back as one loose screen.
        //
        // Aimed at ONE member picked out of the wall it still makes a single
        // ungrouped screen, cross-member path steps and all dropped - see
        // selectedWholeGroupFor (app-screen-groups.js) for which gesture is
        // which, and test_cross_layer_paths_lifecycle.py for that ruling.
        const wall = (typeof this.selectedWholeGroupFor === 'function')
            ? this.selectedWholeGroupFor(layer) : null;
        if (wall) return this.duplicateGroup(wall.id);

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
        // v0.11.0: `group_id` is deliberately absent from this helper and
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
                ..._carryImageShadow(layer),
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

        // v0.11.0 (step 6): Duplicate makes a NEW, UNGROUPED screen - that is
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
            showPowerNferTags: layer.showPowerNferTags !== false,
            showPowerCableTags: layer.showPowerCableTags === true,
            showDataCableTags: layer.showDataCableTags === true,
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
            powerCircuitCables: JSON.parse(JSON.stringify(layer.powerCircuitCables || {})),
            powerCustomPaths: dupPowerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            // Per-run overrides travel with their paths. Plain number
            // arrays - nothing in them names a peer, so no idMap pass.
            powerCustomOverrides: (layer.powerCustomOverrides || []).slice(),
            // v0.11.0: the appearance block was listed ONLY in clientProps
            // below, which is applied to the response in the browser and never
            // sent. The copy therefore looked right and the server held a
            // screen with no gradient at all, so duplicating a screen and
            // reloading lost the copy's gradient - the same symptom as editing
            // one and reloading, reached by a different door.
            gradientEnabled: layer.gradientEnabled,
            gradientType: layer.gradientType,
            gradientScope: layer.gradientScope,
            gradientPanelAlternate: layer.gradientPanelAlternate,
            gradientRadialCenterX: layer.gradientRadialCenterX,
            gradientRadialCenterY: layer.gradientRadialCenterY,
            gradientRadialRadius: layer.gradientRadialRadius,
            gradientAngle: layer.gradientAngle,
            gradientOpacity: layer.gradientOpacity,
            gradientBlend: layer.gradientBlend,
            gradientStops: Array.isArray(layer.gradientStops)
                ? layer.gradientStops.map(s => ({ pos: s.pos, color: s.color }))
                : undefined,
            panelColorMode: layer.panelColorMode,
            panelColors: Array.isArray(layer.panelColors)
                ? layer.panelColors.slice() : undefined,
            transparentFill: layer.transparentFill,
            screenNameOffsetXPixelMap: layer.screenNameOffsetXPixelMap,
            screenNameOffsetYPixelMap: layer.screenNameOffsetYPixelMap,
            screenNameOffsetXShowLook: layer.screenNameOffsetXShowLook,
            screenNameOffsetYShowLook: layer.screenNameOffsetYShowLook,
            // The Data tab's colours were in clientProps only, so the copy
            // looked right and the server held the shipped colours - the
            // gradient bug one door over. Sent so the server's copy matches
            // (the add route's allow-list carries every one of them,
            // dataFlowColor included - routes_layers add_layer).
            arrowColor: layer.arrowColor,
            dataFlowColor: layer.dataFlowColor,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            // The four per-view cabinet borders were in clientProps only
            // too (until 2026-09-22), so the copy's server record held the
            // one border_color for every view - gone on reload.
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            // The breakout rides with the voltage: without it a 208 V
            // powerCON screen's copy read True1 (the voltage's default).
            powerBreakoutType: layer.powerBreakoutType,
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
            // v0.11.0: copies, not the source arrays. This object is
            // Object.assign'd onto the new layer AFTER duplicateData's
            // .map()/.slice() copies have already gone to the server, so
            // passing references here handed the duplicate the ORIGINAL's
            // arrays and quietly undid that copy. Nothing mutates either array
            // in place today - every writer assigns a fresh one - so this was
            // luck rather than design, and it is one in-place edit away from
            // the two screens sharing a gradient.
            gradientStops: Array.isArray(layer.gradientStops)
                ? layer.gradientStops.map(s => ({ pos: s.pos, color: s.color }))
                : layer.gradientStops,
            panelColorMode: layer.panelColorMode,
            panelColors: Array.isArray(layer.panelColors)
                ? layer.panelColors.slice() : layer.panelColors,
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerBreakoutType: layer.powerBreakoutType,
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
            powerCircuitCables: JSON.parse(JSON.stringify(layer.powerCircuitCables || {})),
            powerCustomPaths: dupPowerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            powerCustomOverrides: (layer.powerCustomOverrides || []).slice(),
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showPowerNferTags: layer.showPowerNferTags !== false,
            showPowerCableTags: layer.showPowerCableTags === true,
            showDataCableTags: layer.showDataCableTags === true,
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
            // Per-run overrides travel with their paths. Plain number
            // arrays - nothing in them names a peer, so no idMap pass.
            customPortOverrides: (layer.customPortOverrides || []).slice(),
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
            // The copy's breakout must be one its voltage allows (the
            // source's is, so this is a safety net); a rewrite is pushed
            // so the server's copy matches.
            if (typeof this.normalizePowerBreakout === 'function'
                    && this.normalizePowerBreakout(newLayer)) {
                this.updateLayers([newLayer]);
            }
            
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
                ..._carryImageShadow(this.clipboard),
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

        // v0.11.0 (step 6): paste is the same drop as duplicate, for a harder
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
            showPowerNferTags: this.clipboard.showPowerNferTags !== false,
            showPowerCableTags: this.clipboard.showPowerCableTags === true,
            showDataCableTags: this.clipboard.showDataCableTags === true,
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
            powerCircuitCables: JSON.parse(JSON.stringify(this.clipboard.powerCircuitCables || {})),
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
            // The Data tab's colours: the same set duplicate carries
            // (clientProps there). Until 2026-09-22 paste sent none of them
            // and pasteClientProps stamped only the two text colours, so a
            // pasted screen came out with the shipped line, arrow and port
            // colours whatever the source had - immediately, and on the
            // server. Sent here too so the server's copy matches; the add
            // route lists all but dataFlowColor today.
            arrowColor: this.clipboard.arrowColor,
            dataFlowColor: this.clipboard.dataFlowColor,
            primaryColor: this.clipboard.primaryColor,
            primaryTextColor: this.clipboard.primaryTextColor,
            backupColor: this.clipboard.backupColor,
            backupTextColor: this.clipboard.backupTextColor,
            // The four per-view cabinet borders: pasteClientProps stamped
            // them in the browser and nothing sent them (until 2026-09-22),
            // so a paste across canvases came back from the server with
            // one border for every view on reload.
            border_color_pixel: this.clipboard.border_color_pixel,
            border_color_cabinet: this.clipboard.border_color_cabinet,
            border_color_data: this.clipboard.border_color_data,
            border_color_power: this.clipboard.border_color_power,
            // The breakout rides with the voltage, as duplicate carries it.
            powerBreakoutType: this.clipboard.powerBreakoutType,
            // v0.11.0: paste never carried the appearance block at all -
            // not in this payload and not in pasteClientProps below, which is
            // eight colours and nothing else. So a pasted screen lost its
            // gradient, palette and Transparent Fill immediately on screen,
            // not merely after a reload. Copy/Paste and Duplicate are the same
            // intent; they now produce the same screen.
            gradientEnabled: this.clipboard.gradientEnabled,
            gradientType: this.clipboard.gradientType,
            gradientScope: this.clipboard.gradientScope,
            gradientPanelAlternate: this.clipboard.gradientPanelAlternate,
            gradientRadialCenterX: this.clipboard.gradientRadialCenterX,
            gradientRadialCenterY: this.clipboard.gradientRadialCenterY,
            gradientRadialRadius: this.clipboard.gradientRadialRadius,
            gradientAngle: this.clipboard.gradientAngle,
            gradientOpacity: this.clipboard.gradientOpacity,
            gradientBlend: this.clipboard.gradientBlend,
            gradientStops: Array.isArray(this.clipboard.gradientStops)
                ? this.clipboard.gradientStops.map(s => ({ pos: s.pos, color: s.color }))
                : undefined,
            panelColorMode: this.clipboard.panelColorMode,
            panelColors: Array.isArray(this.clipboard.panelColors)
                ? this.clipboard.panelColors.slice() : undefined,
            transparentFill: this.clipboard.transparentFill,
            screenNameOffsetXPixelMap: this.clipboard.screenNameOffsetXPixelMap,
            screenNameOffsetYPixelMap: this.clipboard.screenNameOffsetYPixelMap,
            screenNameOffsetXShowLook: this.clipboard.screenNameOffsetXShowLook,
            screenNameOffsetYShowLook: this.clipboard.screenNameOffsetYShowLook,
            ..._carryShow(this.clipboard, 50, 50),
        };
        const pasteClientProps = {
            border_color_pixel: this.clipboard.border_color_pixel,
            border_color_cabinet: this.clipboard.border_color_cabinet,
            border_color_data: this.clipboard.border_color_data,
            border_color_power: this.clipboard.border_color_power,
            // The same six Data colours duplicate's clientProps stamps.
            arrowColor: this.clipboard.arrowColor,
            dataFlowColor: this.clipboard.dataFlowColor,
            primaryColor: this.clipboard.primaryColor,
            primaryTextColor: this.clipboard.primaryTextColor,
            backupColor: this.clipboard.backupColor,
            backupTextColor: this.clipboard.backupTextColor,
            powerLabelBgColor: this.clipboard.powerLabelBgColor,
            powerLabelTextColor: this.clipboard.powerLabelTextColor,
            powerBreakoutType: this.clipboard.powerBreakoutType
        };
        
        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pasteData)
        })
        .then(res => res.json())
        .then(newLayer => {
            Object.assign(newLayer, pasteClientProps);
            // Same safety net as duplicate: the pasted breakout must be one
            // the voltage allows; a rewrite is pushed so the server matches.
            if (typeof this.normalizePowerBreakout === 'function'
                    && this.normalizePowerBreakout(newLayer)) {
                this.updateLayers([newLayer]);
            }
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
}

for (const k of Object.getOwnPropertyNames(_Clipboard.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Clipboard.prototype, k));
    }
}
