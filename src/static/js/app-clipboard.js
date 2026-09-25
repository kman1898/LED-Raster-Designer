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

// A COPY of a screen never carries its feeds (owner ruling, 2026-09-23:
// "they can't carry over because then they would be duplicates on the same
// multi or processor"). These six per-multi stores name the run from a
// distro to the screen - which box (powerSocaDistro), which slot on it
// (powerSocaNumber, the shared-box key; a number means nothing off a
// distro), which legs and breaker position on that box (powerSocaPhasePos /
// powerSocaPhaseOffset, the phase balance of THAT distro's load), what the
// multi is called in the show (powerSocaNames - rung 2 of the name ladder,
// above "distro name + number") and how long its home run is
// (powerSocaLengths). A copy is fed by a fresh drop, so it starts with none
// of them. The screen's OWN plan carries: the circuit boundaries its multis
// split at (powerSocaSplits), the splitter groups (powerSplitters), the
// keying stamp (powerSocaKeying - without it the copy's stores would be
// rekeyed a second time) and the bracket toggle, the way the voltage, the
// breakout, the colours and the drawn runs do.
//
// The data side has no twin on the layer: card ports are pins in
// project.port_assignments keyed by layer id, and a copy has a new id
// nothing has pinned yet. Read by _screenCopyPayload (Duplicate / Paste)
// and duplicateGroup (app-screen-groups.js); the server's own clones
// (duplicate canvas, duplicate to canvas) drop the same list in
// app.strip_copied_feeds.
export const SCREEN_FEED_KEYS = [
    'powerSocaDistro', 'powerSocaNumber', 'powerSocaPhasePos',
    'powerSocaPhaseOffset', 'powerSocaNames', 'powerSocaLengths',
];

export function stripScreenFeeds(layer) {
    if (!layer || (layer.type || 'screen') !== 'screen') return layer;
    SCREEN_FEED_KEYS.forEach(k => { delete layer[k]; });
    return layer;
}

function _carryImageShadow(layer) {
    const out = {};
    IMAGE_SHADOW_KEYS.forEach(k => {
        if (layer && layer[k] !== undefined) out[k] = layer[k];
    });
    return out;
}

// v0.8.6.3: carry Show Look state across duplicate / paste, so a layer
// dragged in Show Look (showOffset / show_canvas_id) is copied with its Show
// Look position intact, nudged with the copy, not snapped back to mirror
// Pixel Map. Read by _screenCopyPayload and by the image and text copies.
//
// v0.11.0: `group_id` is deliberately absent here and from
// _screenCopyPayload. Duplicating a screen makes a new screen; enrolling it
// in the source's group would change that group's totals, port numbering and
// export the moment the user hits Duplicate, without them asking. The
// server's create_layer defaults group_id to null, so omitting it is the
// whole mechanism.
function _carryShow(l, dx, dy) {
    const out = {};
    if (l.showOffsetX != null) out.showOffsetX = (Number(l.showOffsetX) || 0) + (dx || 0);
    if (l.showOffsetY != null) out.showOffsetY = (Number(l.showOffsetY) || 0) + (dy || 0);
    if (l.show_canvas_id) out.show_canvas_id = l.show_canvas_id;
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

    // ===== WHAT A COPY OF A SCREEN CARRIES =====
    //
    // ONE list, read by Duplicate and Paste both (2026-09-23). Each of them
    // used to build its own server body and its own client-props blob by
    // hand - four lists for one intent - and every field added to one list
    // and not the others was the same bug wearing a new face: the gradient
    // (v0.11.0), the Data colours and per-view borders (2026-09-22), and
    // then the processing settings, which Duplicate stamped and Paste never
    // did, so a pasted COEX screen came back on the default processor with
    // its port mapping gone - under a comment saying the two "now produce
    // the same screen".
    //
    // `body` goes to POST /api/layer/add; `clientProps` is stamped onto the
    // response. They carry the SAME keys. The add route stores the keys its
    // allow-list names and ignores the rest - processorType, bitDepth,
    // frameRate, lowLatency, portMappingMode, flowPattern, rotation,
    // arrowLineWidth, dataFlowLabelSize, the per-view name sizes and
    // offsets (routes_layers add_layer) - and the PUT both callers push
    // right after the add stores those, the way addLayer (app-core) pushes
    // a new screen's client-side defaults. Until that push a Duplicate's
    // server copy had no processorType at all before the next hand on it.
    // The body also carries the panel geometry (hiddenPanels / panelStates)
    // the server rebuilds the copy from; clientProps leaves undefined
    // values out, so a key the source never had cannot overwrite a default
    // the server has just set.
    //
    // NOT here, on purpose: id; group_id (a copy is a new, ungrouped screen
    // - see duplicateLayer); canvas_id (the add route places the copy on
    // the active canvas); the feeds (SCREEN_FEED_KEYS - a copy claims no
    // multi on any distro); every `_`-prefixed runtime cache. The name and
    // the offsets are the caller's - both use the same smart increment and
    // the same +50 nudge, handed in here. Cross-member path entries are
    // dropped (copyPathsForNewOwner with idMap = null): nothing but this
    // layer is being copied, so no peer has a counterpart - see the two
    // callers for why each of them lands on that answer.
    _screenCopyPayload(layer, name, dx, dy) {
        const deep = (v) => JSON.parse(JSON.stringify(v || {}));
        const props = {
            columns: layer.columns,
            rows: layer.rows,
            cabinet_width: layer.cabinet_width,
            cabinet_height: layer.cabinet_height,
            rotation: layer.rotation,
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
            // The four per-view cabinet borders (2026-09-22): stamped in the
            // browser and never sent, so a paste across canvases came back
            // from the server with one border for every view on reload.
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
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
            showOffsetTL: layer.showOffsetTL,
            showOffsetTR: layer.showOffsetTR,
            showOffsetBL: layer.showOffsetBL,
            showOffsetBR: layer.showOffsetBR,
            // Screen name sizes and per-view positions.
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
            // Appearance (v0.11.0): the gradient, palette and Transparent
            // Fill. Copies of the arrays, never the source's - a reference
            // handed to the copy is one in-place edit away from two screens
            // sharing one gradient.
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
            // Processing: the processor, its bit depth, frame rate and Low
            // Latency, and the port mapping mode. The add route lists none
            // of them; the PUT after the add is what stores them.
            processorType: layer.processorType,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate,
            lowLatency: layer.lowLatency,
            portMappingMode: layer.portMappingMode,
            // Data tab: pattern, lines, labels and the six colours.
            flowPattern: layer.flowPattern,
            arrowLineWidth: layer.arrowLineWidth,
            arrowSize: layer.arrowSize,
            arrowColor: layer.arrowColor,
            dataFlowColor: layer.dataFlowColor,
            dataFlowLabelSize: layer.dataFlowLabelSize,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            randomDataColors: !!layer.randomDataColors,
            showDataFlowPortInfo: !!layer.showDataFlowPortInfo,
            showDataFlowPortLoad: !!layer.showDataFlowPortLoad,
            showDataCableTags: layer.showDataCableTags === true,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: deep(layer.portLabelOverridesPrimary),
            portLabelOverridesReturn: deep(layer.portLabelOverridesReturn),
            customPortPaths: this.copyPathsForNewOwner(layer.customPortPaths, layer.id, null),
            customPortIndex: layer.customPortIndex,
            // Per-run overrides travel with their paths. Plain number
            // arrays - nothing in them names a peer, so no idMap pass.
            customPortOverrides: (layer.customPortOverrides || []).slice(),
            // Power tab: the voltage, the breakout that rides with it
            // (without it a 208 V powerCON screen's copy read True1), the
            // circuits, their colours, labels, cables and hand-drawn runs.
            // NOT the feeds - see SCREEN_FEED_KEYS at the top of this file.
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerBreakoutType: layer.powerBreakoutType,
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
            powerCircuitColors: deep(layer.powerCircuitColors),
            powerLabelSize: layer.powerLabelSize,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: deep(layer.powerLabelOverrides),
            powerCircuitCables: deep(layer.powerCircuitCables),
            // The screen's own jumper lengths (2026-09-25): its cabinets,
            // not a claim on any box, so the copy keeps them.
            dataJumpV: layer.dataJumpV,
            dataJumpH: layer.dataJumpH,
            powerJumpV: layer.powerJumpV,
            powerJumpH: layer.powerJumpH,
            powerCustomPaths: this.copyPathsForNewOwner(layer.powerCustomPaths, layer.id, null),
            powerCustomIndex: layer.powerCustomIndex,
            powerCustomOverrides: (layer.powerCustomOverrides || []).slice(),
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showPowerNferTags: layer.showPowerNferTags !== false,
            showPowerCableTags: layer.showPowerCableTags === true,
            // The screen's own multi plan (2026-09-23): where its multis
            // split, how its circuits share splitters, the keying stamp
            // and the bracket toggle. Geometry of the copy's own circuits,
            // not a claim on any box - the feeds above are the claim.
            powerSocaSplits: Array.isArray(layer.powerSocaSplits)
                ? layer.powerSocaSplits.slice() : undefined,
            powerSplitters: layer.powerSplitters !== undefined
                ? deep(layer.powerSplitters) : undefined,
            powerSocaKeying: layer.powerSocaKeying,
            showSocaBrackets: layer.showSocaBrackets,
            // Show Look position and canvas, nudged with the copy
            // (v0.8.6.3) so a layer dragged in Show Look is copied where it
            // sits there, not snapped back to mirror Pixel Map.
            ..._carryShow(layer, dx, dy),
        };

        // Panel geometry. Older server builds only knew hiddenPanels; the
        // full per-panel state list (halfTile + hidden + blank, v0.8.0) is
        // what the server rebuilds the copy's geometry from.
        const panels = Array.isArray(layer.panels) ? layer.panels : [];
        const hiddenPanels = panels
            .filter(p => p.hidden)
            .map(p => ({ row: p.row, col: p.col }));
        const panelStates = panels
            .filter(p => p.hidden || p.blank || (p.halfTile && p.halfTile !== 'none'))
            .map(p => ({
                row: p.row,
                col: p.col,
                halfTile: p.halfTile || 'none',
                hidden: !!p.hidden,
                blank: !!p.blank,
            }));

        const clientProps = {};
        Object.keys(props).forEach(k => {
            if (props[k] !== undefined) clientProps[k] = props[k];
        });
        const body = {
            name,
            offset_x: (Number(layer.offset_x) || 0) + dx,
            offset_y: (Number(layer.offset_y) || 0) + dy,
            ...props,
            hiddenPanels,
            panelStates,
        };
        // The list above names no feed key; this keeps it that way should
        // one ever be added, since the add route stores every one it is
        // sent (full-layer POSTs need it to).
        stripScreenFeeds(body);
        stripScreenFeeds(clientProps);
        return { body, clientProps };
    }

    // The steps after POST /api/layer/add answers, the same for Duplicate
    // and Paste: stamp what the add route did not store, make sure the
    // breakout is one the voltage allows (the source's is, so a safety
    // net), put the copy in the project and select it, then PUSH it - the
    // PUT is what stores the processing settings and the rest of the keys
    // the add route ignores (see _screenCopyPayload), and the normalized
    // breakout with them. History is saved by the caller, after this, so
    // the snapshot holds the whole copy.
    _adoptScreenCopy(newLayer, clientProps) {
        Object.assign(newLayer, clientProps);
        if (typeof this.normalizePowerBreakout === 'function') {
            this.normalizePowerBreakout(newLayer);
        }
        this.upsertProjectLayer(newLayer);
        this.selectLayer(newLayer);
        this.updateLayers([newLayer]);
        this.updateUI();
        this.saveClientSideProperties();
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

        // v0.11.0 (step 6): Duplicate makes a NEW, UNGROUPED screen - that is
        // the same decision the group_id note on _carryShow documents. Nothing but this
        // layer is being copied, so no peer named by a cross-member path entry
        // has a counterpart here and every such entry drops (idMap = null in
        // _screenCopyPayload). Keeping them would leave the copy's wiring
        // pointing at the ORIGINAL wall's cabinets while the copy is not even
        // in that wall's group. Plain {row, col} paths - every pre-step-6
        // project - come through copyPathsForNewOwner untouched.
        const { body, clientProps } = this._screenCopyPayload(
            layer, getNextName(layer.name), 50, 50);

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(res => res.json())
        .then(newLayer => {
            this._adoptScreenCopy(newLayer, clientProps);

            sendClientLog('duplicate_layer', {
                sourceId: layer.id, sourceName: layer.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });

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
        // so nothing is (idMap = null in _screenCopyPayload). Plain {row, col}
        // paths paste unchanged.
        //
        // Copy/Paste and Duplicate are the same intent, and since 2026-09-23
        // they read the same list, so they produce the same screen - on the
        // client and on the server. Paste used to keep its own two lists and
        // lost, in turn, the gradient, the Data colours, the per-view borders
        // and the processing settings that Duplicate carried.
        const { body, clientProps } = this._screenCopyPayload(
            this.clipboard, getNextName(this.clipboard.name), 50, 50);

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(res => res.json())
        .then(newLayer => {
            this._adoptScreenCopy(newLayer, clientProps);
            sendClientLog('paste_layer', {
                sourceId: this.clipboard.id, sourceName: this.clipboard.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });

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
