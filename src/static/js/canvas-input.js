// canvas.js mixin: Pointer, wheel and keyboard gestures on the canvas, and the hit-testing they lean on.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    handleMouseDown(e) {
        // Last known cursor position, for the focus-loss finalizer
        // (_releaseTransientInput) which has no event to read it from.
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldY = (mouseY - this.panY) / this.zoom;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom, worldY);

        // A plain left press anywhere drops the sweep selection - the same
        // click-away every selection obeys. A RIGHT press keeps it: the
        // selection exists exactly so the right-click can deal it.
        if (e.button === 0 && !e.altKey && window.app
                && window.app._sweepSelection) {
            window.app._sweepSelection = null;
            this.render();
        }

        // v0.8.7.7: plain-click directly on a screen-name label starts a
        // screen-name drag (no modifier needed). This is the universal
        // "grab the label" gesture across every tab, Pixel Map, Cabinet
        // ID, Data Flow, Power. The label rect is cached on the layer by
        // renderLayerLabels at draw time so this hit-test stays in sync
        // with what's drawn. Only checks the active currentLayer's label
        //, clicking some other layer's label still needs Shift / etc.
        if (e.button === 0 && !this.spacePressed && !e.altKey && !e.shiftKey
                && !e.metaKey && !e.ctrlKey
                && window.app && window.app.currentLayer
                && (window.app.currentLayer.type || 'screen') === 'screen'
                // v0.8.7.7.1: don't fire on a hidden layer even if the
                // hit-rect cache is stale from before the visibility
                // toggle. toggleLayerVisibility now clears the cache too,
                // but this guard makes the rule explicit.
                && window.app.currentLayer.visible !== false) {
            const _r = window.app.currentLayer._screenNameHitRect;
            if (_r && _r.viewMode === this.viewMode
                    && worldX >= _r.x1 && worldX <= _r.x2
                    && worldY >= _r.y1 && worldY <= _r.y2) {
                this.isDraggingScreenName = true;
                this.dragScreenNameStartX = worldX;
                this.dragScreenNameStartY = worldY;
                let currentOffsetX = 0;
                let currentOffsetY = 0;
                const layer = window.app.currentLayer;
                if (this.viewMode === 'pixel-map') {
                    currentOffsetX = layer.screenNameOffsetXPixelMap || 0;
                    currentOffsetY = layer.screenNameOffsetYPixelMap || 0;
                } else if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                } else if (this.viewMode === 'show-look') {
                    currentOffsetX = layer.screenNameOffsetXShowLook || 0;
                    currentOffsetY = layer.screenNameOffsetYShowLook || 0;
                }
                this.screenNameStartOffset = { x: currentOffsetX, y: currentOffsetY };
                this.canvas.style.cursor = 'move';
                return;
            }
        }

        // The 'both' name display adds a second grabbable label: the group's
        // headline. Checked AFTER the member-name rect above so the more
        // specific label wins where the two overlap. The rect is cached on
        // the group's cfg member (resolved through the plan, so any selected
        // member can grab it); the offsets ride the group object itself.
        if (e.button === 0 && !this.spacePressed && !e.altKey && !e.shiftKey
                && !e.metaKey && !e.ctrlKey
                && window.app && window.app.currentLayer
                && (window.app.currentLayer.type || 'screen') === 'screen'
                && window.app.currentLayer.visible !== false
                && this._groupNameMode() === 'both') {
            const _plan = this._groupLabelPlan(window.app.currentLayer);
            const _gr = _plan && _plan.cfg._groupNameHitRect;
            if (_gr && _gr.viewMode === this.viewMode
                    && worldX >= _gr.x1 && worldX <= _gr.x2
                    && worldY >= _gr.y1 && worldY <= _gr.y2) {
                this.isDraggingGroupName = true;
                this._dragGroupNameGroup = _plan.group;
                this.dragScreenNameStartX = worldX;
                this.dragScreenNameStartY = worldY;
                const _f = this._screenNameOffsetFields();
                this.screenNameStartOffset = {
                    x: _plan.group[_f.x] || 0,
                    y: _plan.group[_f.y] || 0,
                };
                this.canvas.style.cursor = 'move';
                return;
            }
        }

        // Slice 5: dragging a canvas's dashed outline edge repositions
        // the canvas in the workspace. Must be checked BEFORE the Slice 4
        // panel/canvas-activate block so edge-drag wins over body-click
        // activation. Skipped for pan (space), shift, and alt, those are
        // existing drag/paint behaviors. Inside the canvas body still
        // falls through to Slice 4.
        // v0.8.3: canvas-edge drag is only meaningful on the layout-driving
        // tabs (Pixel Map = processor layout, Show Look = stage layout).
        // On Cabinet ID / Data / Power the canvas position is derived from
        // those two and grabbing the dashed outline there was confusing.
        const canvasDragAllowed = (this.viewMode === 'pixel-map' || this.viewMode === 'show-look');
        if (canvasDragAllowed && e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            const edgeCanvas = this._canvasEdgeAtPoint(worldX, worldY);
            if (edgeCanvas) {
                this.isDraggingCanvas = true;
                this.draggingCanvasId = edgeCanvas.id;
                this.canvasDragStartX = worldX;
                this.canvasDragStartY = worldY;
                // v0.8.5.3: drag uses the active view's workspace position
                // (Show Look has its own show_workspace_x/y).
                {
                    const _ws = this._canvasWorkspace(edgeCanvas);
                    this.canvasDragStartWX = _ws.wx;
                    this.canvasDragStartWY = _ws.wy;
                }
                // saveState moved to canvas-drag END (in updateCanvas .then())
                // so the snapshot is the POST-drag workspace position. Pre-drag
                // saveState was off-by-one and made undo skip past the drag.
                // Activate the dragged canvas so the sidebar reflects it.
                if (window.app && window.app.project
                    && window.app.project.active_canvas_id !== edgeCanvas.id
                    && typeof window.app.setActiveCanvas === 'function') {
                    window.app.setActiveCanvas(edgeCanvas.id);
                }
                this.canvas.style.cursor = 'grabbing';
                if (typeof sendClientLog === 'function') {
                    sendClientLog('canvas_drag_start', { canvasId: edgeCanvas.id });
                }
                return;
            }
        }

        // Slice 4 (+ multi-canvas hit-test fix): every left click in the
        // workspace either:
        //   (a) hits a panel in some canvas's layer → activate that canvas
        //       and make that layer the currentLayer so the existing
        //       panel-select / layer-action paths can run against it
        //       without the user having to click the layer in the sidebar
        //       first;
        //   (b) hits empty area inside a canvas's rect → activate that
        //       canvas;
        //   (c) hits empty area outside any canvas → no canvas change.
        // Skipped for pan (space) and shift/alt modifiers (existing drag
        // behaviors). Additive, the rest of mouse-down still runs.
        // Also skipped for Cmd/Ctrl: that is the selection-TOGGLE gesture,
        // resolved on mouse-up. Running the plain-click activate/promote here
        // would replace the multi-selection with the clicked layer before the
        // toggle ever read it (selectLayer resets selectedLayerIds), and
        // setActiveCanvas without preserveSelection would cull anything
        // selected on another canvas. The toggle path activates the right
        // canvas itself, with preserveSelection.
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey
                && !e.metaKey && !e.ctrlKey) {
            const hitPanel = this.getPanelAt(worldX, worldY);
            if (hitPanel) {
                // Panel hit: switch to its layer's canvas if needed, and
                // promote its layer to currentLayer if needed. Both gates
                // are no-ops when already in scope, so single-canvas /
                // current-layer flows are unchanged.
                const layer = window.app && window.app.project
                    && window.app.project.layers.find(l => l.id === hitPanel.layerId);
                if (layer) {
                    if (layer.canvas_id
                        && window.app.project.active_canvas_id !== layer.canvas_id
                        && typeof window.app.setActiveCanvas === 'function') {
                        window.app.setActiveCanvas(layer.canvas_id);
                    }
                    if ((!window.app.currentLayer || window.app.currentLayer.id !== layer.id)
                        && !this._isCustomPathGesture(layer)
                        && typeof window.app.selectLayer === 'function') {
                        // selectLayer takes the layer OBJECT, not the id
                        // (the !layer.id guard rejects raw integers).
                        this._selectLayerFromCanvas(layer);
                    }
                }
            } else {
                const hitCanvas = this._canvasAtPoint(worldX, worldY);
                if (hitCanvas && hitCanvas.id
                    && window.app
                    && window.app.project
                    && hitCanvas.id !== window.app.project.active_canvas_id
                    && typeof window.app.setActiveCanvas === 'function') {
                    window.app.setActiveCanvas(hitCanvas.id);
                }
            }
        }

        if (e.button === 0 && this.spacePressed) {
            this.isDragging = true;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.canvas.style.cursor = 'grabbing';
            return;
        }
        
        if (e.button === 0 && e.shiftKey) {
            // Let shift+drag behavior handle screen name move on cabinet-id /
            // data-flow / power. On pixel-map and show-look, fall through so
            // shift+drag moves the entire layer (writing to offset_x/y or
            // showOffsetX/Y respectively).
            // v0.8.3: text and image layers don't have per-tab screen-name
            // labels, so shift+drag on them always moves the whole layer
            // regardless of view mode.
            if (window.app && window.app.currentLayer) {
                const layerType = window.app.currentLayer.type || 'screen';
                const isScreenLayer = layerType === 'screen';
                if (isScreenLayer && this.viewMode !== 'pixel-map' && this.viewMode !== 'show-look') {
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;

                    let currentOffsetX = 0;
                    let currentOffsetY = 0;

                    if (this.viewMode === 'pixel-map') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPixelMap || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPixelMap || 0;
                    } else if (this.viewMode === 'cabinet-id') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXCabinet || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYCabinet || 0;
                    } else if (this.viewMode === 'data-flow') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXDataFlow || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYDataFlow || 0;
                    } else if (this.viewMode === 'power') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPower || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPower || 0;
                    }

                    this.screenNameStartOffset = { x: currentOffsetX, y: currentOffsetY };
                    return;
                }
            }
        }

        // Custom data / power: arm the PATH marquee only when the press lands
        // on a cabinet this gesture can actually draw on.
        //
        // These two branches used to arm anywhere on the canvas and then
        // `return`, with no position test at all - so for every plain press
        // while custom mode was on, the layer marquee further down was
        // unreachable. You could not rubber-band several screens without
        // leaving custom mode first. Pixel Map has always done this properly
        // (hit-test, otherwise fall through); this brings custom mode in line.
        // `!e.altKey`: Alt+press is the override gesture (take the run under
        // the cursor over), never a path marquee - see the alt branch below.
        if (e.button === 0 && !e.altKey && window.app && window.app.currentLayer && this.viewMode === 'data-flow') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlowEditing(layer) && this._customDrawStartsInScope(worldX, worldY)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }
        if (e.button === 0 && !e.altKey && window.app && window.app.currentLayer && this.viewMode === 'power') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomPowerEditing(layer) && this._customDrawStartsInScope(worldX, worldY)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }

        // Pixel Map: drag-select panels of the current layer for bulk
        // Set-Blank / Set-Half-tile actions. Falls through to layer selection
        // when the drag starts in empty space (so layer multi-select still works).
        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey
                && this.viewMode === 'pixel-map'
                && window.app && window.app.currentLayer) {
            const startPanel = this.getPanelAt(worldX, worldY);
            // Allow drag-start on hidden ("blank") panels too, selecting them
            // is the only way to bulk-restore via the sidebar buttons.
            const onCurrentLayer = startPanel
                && startPanel.layerId === window.app.currentLayer.id;
            // Don't capture the click for panel-select if there's a HIGHER-Z
            // layer (image / text / another screen later in project.layers)
            // sitting on top of the current layer at this point, the user is
            // clicking the visible top layer, not the panel buried beneath it.
            // Bug: with a text layer over a selected screen, clicks on text
            // were grabbed by the screen's panel-select instead of selecting
            // the text layer.
            const topLayer = this.getLayerAt(worldX, worldY);
            const topIsHigher = topLayer && window.app.project
                && window.app.project.layers.indexOf(topLayer)
                    > window.app.project.layers.indexOf(window.app.currentLayer);
            if (onCurrentLayer && !topIsHigher) {
                this.isSelectingPixelMapPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: window.app.currentLayer.id });
                }
                return;
            }
        }

        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
            // Falling through to layer-select means the user clicked outside any
            // panel in pixel-map (or in another view). Drop any stale pixel-map
            // panel selection so it doesn't sit around, fresh layer-drag should
            // start without panel-state lingering.
            if (this.viewMode === 'pixel-map' && window.app && window.app.pixelMapSelection
                    && window.app.pixelMapSelection.size > 0) {
                window.app.clearPixelMapSelection();
            }
            // Same for custom data / power: reaching here means the press
            // landed outside every screen this path can draw on, so the panels
            // highlighted for the port or circuit are no longer the subject of
            // what the user is doing. Leaving them lit made the next click
            // inside the screen extend a selection the user thought they had
            // dropped when they clicked away.
            if (this.viewMode === 'data-flow' && window.app
                    && window.app.customSelection && window.app.customSelection.size > 0) {
                window.app.clearCustomSelection();
            }
            if (this.viewMode === 'power' && window.app
                    && window.app.powerCustomSelection && window.app.powerCustomSelection.size > 0) {
                window.app.clearPowerCustomSelection();
            }
            this.isSelectingLayers = true;
            this.layerSelectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
            if (typeof sendClientLog === 'function') {
                sendClientLog('layer_selection_start', { viewMode: this.viewMode });
            }
            return;
        }
        
        if (e.button === 1 || (e.button === 0 && this.spacePressed)) {
            this.isDragging = true;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.canvas.style.cursor = 'grabbing';
        } else if (e.button === 0 && e.shiftKey && !e.altKey) {
            if (window.app && window.app.currentLayer) {
                // On pixel-map / show-look: drag entire layer.
                //   - pixel-map writes to offset_x/y (the processor position)
                //   - show-look writes to showOffsetX/Y (the show position)
                // On data-flow / power / cabinet-id: drag screen name label only.
                // v0.8.3: text and image layers always do whole-layer move on
                // any tab (they don't have per-tab screen-name labels).
                const layerType = window.app.currentLayer.type || 'screen';
                const isScreenLayer = layerType === 'screen';
                const wholeLayerMove = !isScreenLayer
                    || this.viewMode === 'pixel-map'
                    || this.viewMode === 'show-look';
                if (wholeLayerMove) {
                    const selected = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    const uniqueSelected = [];
                    const seenIds = new Set();
                    selected.forEach(layer => {
                        if (!layer || seenIds.has(layer.id)) return;
                        seenIds.add(layer.id);
                        uniqueSelected.push(layer);
                    });
                    // v0.11.0: a group moves as one screen, so any selected
                    // member pulls in its peers (and puts them in the app's
                    // selection, so mouseup persists every layer that moved).
                    // Relative offsets are preserved for free: the drag applies
                    // ONE delta to every entry in dragLayerOffsets below.
                    this._addGroupPeersToDrag(uniqueSelected);
                    const movable = uniqueSelected.filter(layer => !layer.locked);
                    if (movable.length === 0) {
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_drag_blocked_locked', { viewMode: this.viewMode });
                        }
                        return;
                    }
                    this.isDraggingLayer = true;
                    this.dragLayerMode = (this.viewMode === 'show-look') ? 'show' : 'processor';
                    // saveState moved to drag-END so the snapshot captures the
                    // POST-drag project state. Undo decrements then restores
                    // the previous post-state, which matches the user's
                    // expectation of "one Cmd+Z reverts one drag." Pre-drag
                    // saveState was off-by-one and made undo skip past the
                    // most recent action.
                    this.dragLayerStartX = worldX;
                    this.dragLayerStartY = worldY;
                    const useShow = this.dragLayerMode === 'show';
                    const startX = useShow
                        ? (window.app.currentLayer.showOffsetX ?? window.app.currentLayer.offset_x ?? 0)
                        : (window.app.currentLayer.offset_x ?? 0);
                    const startY = useShow
                        ? (window.app.currentLayer.showOffsetY ?? window.app.currentLayer.offset_y ?? 0)
                        : (window.app.currentLayer.offset_y ?? 0);
                    this.layerStartOffset = { x: startX, y: startY };
                    this.dragLayerOffsets = movable.map(layer => ({
                        id: layer.id,
                        startX: useShow
                            ? (layer.showOffsetX ?? layer.offset_x ?? 0)
                            : (layer.offset_x ?? 0),
                        startY: useShow
                            ? (layer.showOffsetY ?? layer.offset_y ?? 0)
                            : (layer.offset_y ?? 0),
                        // Capture whether this layer's show position was
                        // linked to its processor position at drag-start
                        // (i.e. equal). If so, dragging in pixel-map should
                        // also update showOffset so Show Look / Data / Power
                        // track the new position. Once they diverge (because
                        // the user moved the layer in Show Look), pixel-map
                        // drags stop touching showOffset.
                        showLinkedX: !useShow && (Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0)),
                        showLinkedY: !useShow && (Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0)),
                        // Only the processor-position drag mutates panel.x/y
                        // (panels live in processor coords). Show-position
                        // drag is rendered via ctx.translate so panels stay
                        // put.
                        panelStarts: useShow ? null : (layer.panels || []).map(panel => ({
                            id: panel.id,
                            x: panel.x,
                            y: panel.y
                        }))
                    }));
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('layer_drag_start', {
                            viewMode: this.viewMode,
                            mode: this.dragLayerMode,
                            layerIds: movable.map(l => l.id),
                        });
                    }
                } else {
                    // Dragging screen name on cabinet-id, data-flow, power modes
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;
                    
                    // Get tab-specific screen name offset
                    let currentOffsetX = 0;
                    let currentOffsetY = 0;
                    
                    if (this.viewMode === 'cabinet-id') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXCabinet || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYCabinet || 0;
                    } else if (this.viewMode === 'data-flow') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXDataFlow || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYDataFlow || 0;
                    } else if (this.viewMode === 'power') {
                        currentOffsetX = window.app.currentLayer.screenNameOffsetXPower || 0;
                        currentOffsetY = window.app.currentLayer.screenNameOffsetYPower || 0;
                    }
                    
                    this.screenNameStartOffset = {
                        x: currentOffsetX,
                        y: currentOffsetY
                    };
                }
            }
        } else if (e.button === 0 && e.altKey && e.shiftKey) {
            // Alt+Shift+click toggles per-panel half-tile (auto direction).
            // When a multi-selection is active, apply to the entire selection
            // instead of just the clicked panel.
            if (this.viewMode === 'pixel-map') {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel && window.app && window.app.currentLayer
                        && clickedPanel.layerId === window.app.currentLayer.id
                        && !clickedPanel.panel.hidden) {
                    e.preventDefault();
                    const p = clickedPanel.panel;
                    const selected = window.app.getPixelMapSelectedPanels
                        ? window.app.getPixelMapSelectedPanels()
                        : [];
                    const targets = selected.length > 0 ? selected : [p];
                    // Toggle: if any target panel currently has a halfTile, clear all;
                    // otherwise auto-detect per panel and apply.
                    const anyOn = targets.some(t => t.halfTile && t.halfTile !== 'none');
                    const targetMode = anyOn ? 'none' : 'auto';
                    window.app.setPanelsHalfTileBulk(targets, targetMode);
                }
            }
        } else if (e.button === 0 && e.altKey) {
            // POWER: Alt+press ARMS two gestures and the dock drag engine's
            // 4px threshold discriminates (2026-08-30, "B and then right
            // click"): drag past it and the press is a SWEEP - a contiguous
            // run selection collecting under the cursor for the right-click
            // batch menu; release inside it and the press is the takeover
            // click it always was. Selection is session view state - never
            // a history entry (leading-underscore key, so snapshots skip it
            // by the _snapshotReplacer convention).
            if (this.viewMode === 'power') {
                e.preventDefault();
                const run = window.app
                    && typeof window.app.runAtPoint === 'function'
                    ? window.app.runAtPoint(worldX, worldY) : null;
                this._sweepPending = {
                    sx: e.clientX, sy: e.clientY, worldX, worldY,
                    active: false,
                    anchor: (run && run.kind === 'power')
                        ? { ownerId: run.layer.id, num: run.num } : null,
                };
                return;
            }
            // Data: Alt+click takes the run under the cursor over for
            // hand-redrawing (or reopens one already taken). The highlight
            // the held Alt paints (see handleMouseMove) is the affordance;
            // the click is the commitment.
            if (this.viewMode === 'data-flow') {
                if (window.app && typeof window.app.handleOverrideClick === 'function') {
                    e.preventDefault();
                    window.app.handleOverrideClick(worldX, worldY);
                }
                return;
            }
            // Alt+click/drag toggles "blank" (hidden) on the panel.
            // When a multi-selection is active, apply to the entire selection
            // in one shot (no drag-painting in that mode, the selection is
            // already explicit).
            if (this.viewMode === 'pixel-map') {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel && window.app) {
                    e.preventDefault();
                    const selected = (window.app.getPixelMapSelectedPanels
                        ? window.app.getPixelMapSelectedPanels()
                        : []);
                    if (selected.length > 0) {
                        // Toggle direction: if any selected panel is currently
                        // visible, hide all; otherwise show all.
                        const anyVisible = selected.some(p => !p.hidden);
                        window.app.setPanelsBlankBulk(selected, anyVisible);
                        return;
                    }
                    this.isAltPainting = true;
                    this.altPaintLayerId = clickedPanel.layerId;
                    this.altPaintMode = clickedPanel.panel.hidden ? 'show' : 'hide';
                    this.altPaintedPanelIds = new Set();
                    clickedPanel.panel.hidden = (this.altPaintMode === 'hide');
                    this.altPaintedPanelIds.add(clickedPanel.panel.id);
                    this.render();
                }
            }
        } else if (e.button === 0 && this.viewMode === 'data-flow' && window.app) {
            const layer = this.getLayerAt(worldX, worldY);
            if (layer) {
                this._selectLayerFromCanvas(layer);
            } else {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel) {
                    const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                    if (panelLayer) {
                        this._selectLayerFromCanvas(panelLayer);
                    }
                }
            }
        } else if (e.button === 0) {
            if (window.app) {
                const layer = this.getLayerAt(worldX, worldY);
                if (layer) {
                    this._selectLayerFromCanvas(layer);
                } else {
                    const clickedPanel = this.getPanelAt(worldX, worldY);
                    if (clickedPanel) {
                        const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        if (panelLayer) {
                            this._selectLayerFromCanvas(panelLayer);
                        }
                    }
                }
            }
        }
    },
    
    handleMouseMove(e) {
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldY = (mouseY - this.panY) / this.zoom;
        const worldX = this._unmirrorWorldX((mouseX - this.panX) / this.zoom, worldY);

        // Slice 5: live canvas-drag, update workspace_x/y on every move,
        // but only PUT to the server on mouseup (avoid flooding).
        if (this.isDraggingCanvas && this.draggingCanvasId) {
            if (window.app && window.app.project) {
                const c = window.app.project.canvases.find(c => c.id === this.draggingCanvasId);
                if (c) {
                    const dx = worldX - this.canvasDragStartX;
                    const dy = worldY - this.canvasDragStartY;
                    let nextX = this.canvasDragStartWX + dx;
                    let nextY = this.canvasDragStartWY + dy;
                    // v0.8 Slice 9: snap dragged canvas edges to neighbor
                    // canvas edges (left↔right, right↔left, top↔bottom,
                    // bottom↔top, plus aligned-edge snap). Honors the global
                    // magnetic-snap toggle so users can disable it.
                    if (this.magneticSnap) {
                        const snapped = this._snapCanvasToNeighbors(c, nextX, nextY);
                        nextX = snapped.x;
                        nextY = snapped.y;
                    }
                    // v0.8.5.3: Show Look canvas drag writes show_workspace
                    // so Pixel Map's workspace stays put.
                    if (this.isShowLookView()) {
                        c.show_workspace_x = nextX;
                        c.show_workspace_y = nextY;
                    } else {
                        c.workspace_x = nextX;
                        c.workspace_y = nextY;
                    }
                    this.render();
                }
            }
            return;
        }

        if (this.isAltPainting) {
            const clickedPanel = this.getPanelAt(worldX, worldY);
            if (clickedPanel && clickedPanel.layerId === this.altPaintLayerId && !this.altPaintedPanelIds.has(clickedPanel.panel.id)) {
                clickedPanel.panel.hidden = (this.altPaintMode === 'hide');
                this.altPaintedPanelIds.add(clickedPanel.panel.id);
                this.render();
            }
            return;
        }

        // An armed Alt+press in Power: inside the 4px threshold it is still
        // a click-to-be; past it, the press becomes the SWEEP and collects
        // the contiguous run range between the anchor and the cursor.
        if (this._sweepPending) {
            const p = this._sweepPending;
            if (!p.active) {
                if (Math.hypot(e.clientX - p.sx, e.clientY - p.sy) <= 4) {
                    return;
                }
                if (!p.anchor) { this._sweepPending = null; return; }
                p.active = true;
                // the sweep owns the gesture now - the takeover's held-Alt
                // hover highlight would fight the selection underlay
                if (window.app
                        && typeof window.app.updateOverrideHover === 'function') {
                    window.app.updateOverrideHover(false, 0, 0);
                }
            }
            this._sweepExtend(worldX, worldY, e.clientX, e.clientY);
            return;
        }

        if (this.isSelectingPanels && this.selectionRect) {
            this.selectionRect.x2 = worldX;
            this.selectionRect.y2 = worldY;
            // currentLayer is the OWNER of the port/circuit being drawn, not a
            // limit on what the rect may cover: since v0.11.0 these two walk
            // every member the owner's path can legally reach, so a live drag
            // lights up cabinets on the next screen of the wall as it crosses
            // onto it (see the mouse-up twin below).
            // BOTH branches test viewMode. The data branch used to test only
            // isCustomFlow, so in POWER view a screen that was also on a custom
            // DATA pattern took the first branch and filled the data selection
            // instead - and since the power overlay reads the power set, the
            // drag looked like it was doing nothing until mouse-up (which has
            // always gated on viewMode) finally filled the right one. A screen
            // in a group is always in that state, because the flow pattern is
            // shared across members.
            if (window.app && window.app.currentLayer && this.viewMode === 'data-flow'
                && window.app.isCustomFlowEditing(window.app.currentLayer)) {
                window.app.selectPanelsInRect(window.app.currentLayer, this.selectionRect);
            } else if (window.app && window.app.currentLayer && this.viewMode === 'power' && window.app.isCustomPowerEditing(window.app.currentLayer)) {
                window.app.selectPowerPanelsInRect(window.app.currentLayer, this.selectionRect);
            }
            this.render();
            return;
        }

        if (this.isSelectingPixelMapPanels && this.selectionRect) {
            this.selectionRect.x2 = worldX;
            this.selectionRect.y2 = worldY;
            if (window.app && window.app.currentLayer) {
                window.app.selectPixelMapPanelsInRect(window.app.currentLayer, this.selectionRect);
            }
            this.render();
            return;
        }

        if (this.isSelectingLayers && this.layerSelectionRect) {
            this.layerSelectionRect.x2 = worldX;
            this.layerSelectionRect.y2 = worldY;
            this.render();
            return;
        }
        
        document.getElementById('cursor-position').textContent = `X: ${Math.round(worldX)}, Y: ${Math.round(worldY)}`;

        // Held Alt over a wired view: light the run under the cursor, the way
        // a dock drag lights the run it is about to land on. The update is a
        // no-op (no render) unless the lit run actually changes.
        if ((this.viewMode === 'data-flow' || this.viewMode === 'power')
                && window.app && typeof window.app.updateOverrideHover === 'function') {
            window.app.updateOverrideHover(!!e.altKey, worldX, worldY);
        }

        if (this.isDragging) {
            const dx = mouseX - this.dragStartX;
            const dy = mouseY - this.dragStartY;
            this.panX += dx;
            this.panY += dy;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.render();
        } else if (this.isDraggingLayer) {
            const dx = Math.round(worldX - this.dragLayerStartX);
            const dy = Math.round(worldY - this.dragLayerStartY);
            
            if (window.app && window.app.currentLayer) {
                let snapDx = dx;
                let snapDy = dy;
                let newOffsetX = this.layerStartOffset.x + dx;
                let newOffsetY = this.layerStartOffset.y + dy;
                
                // Magnetic snapping (only if enabled) based on current layer
                if (this.magneticSnap) {
                    const snapResult = this.calculateMagneticSnap(newOffsetX, newOffsetY, window.app.currentLayer);
                    snapDx = snapResult.x - this.layerStartOffset.x;
                    snapDy = snapResult.y - this.layerStartOffset.y;
                }
                
                const selected = this.dragLayerOffsets && this.dragLayerOffsets.length > 0
                    ? this.dragLayerOffsets
                    : [{ id: window.app.currentLayer.id, startX: this.layerStartOffset.x, startY: this.layerStartOffset.y }];
                const movable = selected.filter(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    return layer && !layer.locked;
                });
                if (movable.length === 0) {
                    return;
                }
                const showMode = this.dragLayerMode === 'show';
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    if (showMode) {
                        // Show Look drag, only the show position changes;
                        // panels stay at their processor coords.
                        layer.showOffsetX = nextX;
                        layer.showOffsetY = nextY;
                    } else {
                        layer.offset_x = nextX;
                        layer.offset_y = nextY;
                        // While show position was linked to processor position,
                        // keep them in sync so Show Look / Data / Power follow
                        // the pixel-map move.
                        if (item.showLinkedX) layer.showOffsetX = nextX;
                        if (item.showLinkedY) layer.showOffsetY = nextY;
                        const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                        layer.panels.forEach(panel => {
                            const start = startMap.get(panel.id);
                            if (!start) return;
                            panel.x = start.x + snapDx;
                            panel.y = start.y + snapDy;
                        });
                    }
                });

                // Track cross-canvas drop target for visual hint. Match the
                // mouseUp drop logic: hit-test the **mouse cursor**, not the
                // layer center (so wide layers feel responsive).
                const _primary = window.app.currentLayer;
                if (_primary) {
                    const _tgt = this._canvasAtPoint(worldX, worldY);
                    // v0.8.5: in Show Look / Data / Power the cross-canvas
                    // hint compares against the layer's effective show
                    // canvas, matching where it renders.
                    const _primaryCid = this._effectiveLayerCanvasId(_primary);
                    this._crossCanvasDropTarget = (_tgt && _tgt.id !== _primaryCid) ? _tgt : null;
                } else {
                    this._crossCanvasDropTarget = null;
                }

                this.render();
            }
        } else if (this.isDraggingScreenName) {
            // Screen name dragging with snap positions - tab-specific
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                // Screen-name drag, bounds in the active view for snap calc.
                const bounds = this.getLayerBoundsInActiveView(layer);
                const layerWidth = bounds.width;
                const layerHeight = bounds.height;
                
                // Calculate raw offset from drag
                const dx = worldX - this.dragScreenNameStartX;
                const dy = worldY - this.dragScreenNameStartY;

                // v0.8.7.2: screen-name offsets are stored in *visual* (viewer)
                // space so toggling Front<->Back keeps the label visually in
                // place instead of mirror-jumping across the screen. When the
                // active layer's canvas is mirrored, the mouse delta in world
                // (un-mirrored) space points the opposite direction from what
                // the user sees, so negate X here to keep "drag right = +X
                // visually" regardless of perspective.
                const _mirrorActive = (() => {
                    const layer = window.app && window.app.currentLayer;
                    if (!layer || typeof this._effectiveLayerCanvasId !== 'function') return false;
                    const cid = this._effectiveLayerCanvasId(layer);
                    const arr = window.app.project && window.app.project.canvases;
                    if (!Array.isArray(arr)) return false;
                    const c = arr.find(c => c && c.id === cid);
                    return !!(c && this._isCanvasMirrored && this._isCanvasMirrored(c));
                })();
                const _visualDx = _mirrorActive ? -dx : dx;

                let newOffsetX = this.screenNameStartOffset.x + _visualDx;
                let newOffsetY = this.screenNameStartOffset.y + dy;
                
                // Only snap if magnetic snap is enabled
                if (this.magneticSnap) {
                    // Snap positions relative to layer center (0,0 = center)
                    // Left: -layerWidth/2, Center: 0, Right: layerWidth/2
                    // Top: -layerHeight/2, Middle: 0, Bottom: layerHeight/2
                    const snapThreshold = 20;
                    const snapPositionsX = [-layerWidth/2, 0, layerWidth/2];
                    const snapPositionsY = [-layerHeight/2, 0, layerHeight/2];
                    
                    // Snap X
                    for (const snapX of snapPositionsX) {
                        if (Math.abs(newOffsetX - snapX) < snapThreshold) {
                            newOffsetX = snapX;
                            break;
                        }
                    }
                    
                    // Snap Y
                    for (const snapY of snapPositionsY) {
                        if (Math.abs(newOffsetY - snapY) < snapThreshold) {
                            newOffsetY = snapY;
                            break;
                        }
                    }
                }
                
                // Store in tab-specific properties
                if (this.viewMode === 'pixel-map') {
                    layer.screenNameOffsetXPixelMap = newOffsetX;
                    layer.screenNameOffsetYPixelMap = newOffsetY;
                } else if (this.viewMode === 'cabinet-id') {
                    layer.screenNameOffsetXCabinet = newOffsetX;
                    layer.screenNameOffsetYCabinet = newOffsetY;
                } else if (this.viewMode === 'data-flow') {
                    layer.screenNameOffsetXDataFlow = newOffsetX;
                    layer.screenNameOffsetYDataFlow = newOffsetY;
                } else if (this.viewMode === 'power') {
                    layer.screenNameOffsetXPower = newOffsetX;
                    layer.screenNameOffsetYPower = newOffsetY;
                } else if (this.viewMode === 'show-look') {
                    layer.screenNameOffsetXShowLook = newOffsetX;
                    layer.screenNameOffsetYShowLook = newOffsetY;
                }

                this.render();
            }
        } else if (this.isDraggingGroupName) {
            // The 'both' display's group headline drag: same visual-space
            // delta, mirror compensation and magnetic-snap treatment as a
            // screen name's, measured against the group's union bounds and
            // stored on the group object under the per-view field names.
            const group = this._dragGroupNameGroup;
            const layer = window.app && window.app.currentLayer;
            if (group && layer) {
                const plan = this._groupLabelPlan(layer);
                const bounds = plan
                    ? this._groupUnionBounds(plan.members, plan.host)
                    : this.getLayerBoundsInActiveView(layer);

                const dx = worldX - this.dragScreenNameStartX;
                const dy = worldY - this.dragScreenNameStartY;
                const _mirrorActive = (() => {
                    if (typeof this._effectiveLayerCanvasId !== 'function') return false;
                    const cid = this._effectiveLayerCanvasId(layer);
                    const arr = window.app.project && window.app.project.canvases;
                    if (!Array.isArray(arr)) return false;
                    const c = arr.find(c => c && c.id === cid);
                    return !!(c && this._isCanvasMirrored && this._isCanvasMirrored(c));
                })();
                const _visualDx = _mirrorActive ? -dx : dx;

                let newOffsetX = this.screenNameStartOffset.x + _visualDx;
                let newOffsetY = this.screenNameStartOffset.y + dy;

                if (this.magneticSnap) {
                    const snapThreshold = 20;
                    const snapPositionsX = [-bounds.width / 2, 0, bounds.width / 2];
                    const snapPositionsY = [-bounds.height / 2, 0, bounds.height / 2];
                    for (const snapX of snapPositionsX) {
                        if (Math.abs(newOffsetX - snapX) < snapThreshold) {
                            newOffsetX = snapX;
                            break;
                        }
                    }
                    for (const snapY of snapPositionsY) {
                        if (Math.abs(newOffsetY - snapY) < snapThreshold) {
                            newOffsetY = snapY;
                            break;
                        }
                    }
                }

                const f = this._screenNameOffsetFields();
                group[f.x] = newOffsetX;
                group[f.y] = newOffsetY;

                this.render();
            }
        }

        if (this.spacePressed && !this.isDragging) {
            this.canvas.style.cursor = 'grab';
        } else if (!this.isDragging && !this.isDraggingLayer && !this.isDraggingScreenName && !this.isDraggingGroupName && !this.isDraggingCanvas) {
            // Slice 5: hovering a canvas's outline edge → show 'move' so
            // the user knows they can grab it. Skip when a modifier is
            // held (other actions own those gestures).
            if (!e.shiftKey && !e.altKey && !this.isSelectingPanels && !this.isSelectingLayers
                && this._canvasEdgeAtPoint(worldX, worldY)) {
                this.canvas.style.cursor = 'move';
            } else {
                this.canvas.style.cursor = 'default';
            }
        }
    },
    
    handleMouseUp(e) {
        // The armed Alt+press resolves here: a release inside the 4px
        // threshold is the takeover click deferred at mousedown; a release
        // after sweeping keeps the selection lit for the right-click menu
        // (the pill leaves with the cursor's gesture, the selection stays).
        if (this._sweepPending) {
            const p = this._sweepPending;
            this._sweepPending = null;
            this._removeSweepHud();
            if (!p.active && window.app
                    && typeof window.app.handleOverrideClick === 'function') {
                window.app.handleOverrideClick(p.worldX, p.worldY);
            }
            return;
        }

        // Slice 5: commit canvas-drag drop. Live updates already happened
        // during mousemove; here we round to integer (avoid sub-pixel
        // drift), persist with a single PUT, and run an overlap check.
        if (this.isDraggingCanvas) {
            this.isDraggingCanvas = false;
            const id = this.draggingCanvasId;
            this.draggingCanvasId = null;
            this.canvas.style.cursor = 'default';
            if (window.app && window.app.project) {
                const c = window.app.project.canvases.find(c => c.id === id);
                if (c) {
                    // v0.8.5.3: persist to the right field per view.
                    const isShow = this.isShowLookView();
                    const _ws = this._canvasWorkspace(c);
                    const wx = Math.round(_ws.wx);
                    const wy = Math.round(_ws.wy);
                    if (isShow) {
                        c.show_workspace_x = wx;
                        c.show_workspace_y = wy;
                    } else {
                        c.workspace_x = wx;
                        c.workspace_y = wy;
                    }
                    if (typeof window.app.updateCanvas === 'function') {
                        // updateCanvas now snapshots POST-mutation state in
                        // its server-response .then() so a single Cmd+Z reverts
                        // exactly this drag. No skipSaveState needed.
                        const patch = isShow
                            ? { show_workspace_x: wx, show_workspace_y: wy }
                            : { workspace_x: wx, workspace_y: wy };
                        window.app.updateCanvas(id, patch);
                    }
                    if (typeof window.app._checkCanvasOverlapAndToast === 'function') {
                        window.app._checkCanvasOverlapAndToast(id);
                    }
                }
            }
            this.render();
            if (typeof sendClientLog === 'function') {
                sendClientLog('canvas_drag_end', { canvasId: id });
            }
            return;
        }

        if (this.isAltPainting) {
            this.isAltPainting = false;
            if (window.app && this.altPaintedPanelIds && this.altPaintedPanelIds.size > 0) {
                const layer = window.app.project.layers.find(l => l.id === this.altPaintLayerId);
                if (layer) {
                    // Undo audit: same contract as setPanelsBlankBulk (the
                    // sidebar twin of this gesture). Hiding a panel re-anchors
                    // neighbouring half-tiles and that rebuild only happens
                    // server-side, so the snapshot must wait for the rebuilt
                    // layer - taken here it paired the new flags with the old
                    // geometry, and it recorded even when the POST failed.
                    // Merge the response first, snapshot second.
                    const newHidden = this.altPaintMode === 'hide';
                    const panels = [...this.altPaintedPanelIds].map(id => ({ id, hidden: newHidden }));
                    fetch(`/api/layer/${this.altPaintLayerId}/panels/set_hidden`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ panels })
                    })
                        .then(res => res.json())
                        .then(data => {
                            if (data && data.layer && window.app) {
                                const applied = window.app.applyServerLayer(
                                    data.layer, 'alt_paint_set_hidden');
                                this.render();
                                if (applied) window.app.saveState('Toggle Panel Visibility');
                            }
                        })
                        .catch(err => console.error('Alt-paint set_hidden failed', err));
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('bulk_toggle_panels', {
                            layerId: this.altPaintLayerId,
                            mode: this.altPaintMode,
                            count: this.altPaintedPanelIds.size
                        });
                    }
                }
            }
            this.altPaintLayerId = null;
            this.altPaintMode = null;
            this.altPaintedPanelIds = null;
            this.render();
            return;
        }

        if (this.isSelectingPanels) {
            this.isSelectingPanels = false;
            if (this.selectionRect && window.app && window.app.currentLayer) {
                const w = Math.abs(this.selectionRect.x2 - this.selectionRect.x1);
                const h = Math.abs(this.selectionRect.y2 - this.selectionRect.y1);
                if (w < 0.5 && h < 0.5) {
                    if (this.viewMode === 'power' && window.app.isCustomPowerEditing(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                        window.app.powerCustomSelection.clear();
                        window.app.updateCustomPowerUI();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    if (this.viewMode === 'data-flow' && window.app.isCustomFlowEditing(window.app.currentLayer) && window.app.customSelection.size > 0) {
                        window.app.clearCustomSelection();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    const clickedPanel = this.getPanelAt(this.selectionRect.x1, this.selectionRect.y1);
                    if (clickedPanel) {
                        const isPower = this.viewMode === 'power';
                        // v0.11.0 screen groups: the gate used to be a straight
                        // `clickedPanel.layerId === currentLayer.id`, which made
                        // a hand-drawn path physically unable to leave its own
                        // layer. A group is ONE wall, so the path has to be able
                        // to run onto the next member. getPanelAt already
                        // searched every visible layer top-down and told us
                        // which one it hit, applying that layer's own Show Look
                        // offset, canvas translate and rotation, so there is no
                        // geometry to redo here - only the question of whether
                        // the port may legally reach that layer, which
                        // canPathReachLayer answers (same group, same effective
                        // canvas). Without the helper it reduces to the old
                        // identity test, so nothing changes before app-power.js
                        // lands it.
                        const clickedLayer = window.app.project.layers.find(
                            l => l.id === clickedPanel.layerId) || null;
                        const reachable = (typeof window.app.canPathReachLayer === 'function')
                            ? !!(clickedLayer && window.app.canPathReachLayer(
                                window.app.currentLayer, clickedLayer))
                            : clickedPanel.layerId === window.app.currentLayer.id;
                        if (isPower && window.app.isCustomPowerEditing(window.app.currentLayer) && reachable) {
                            if (window.app.powerCustomSelection.size > 0) {
                                window.app.powerCustomSelection.clear();
                                window.app.updateCustomPowerUI();
                            } else {
                                // The clicked panel's OWN layer goes with it so
                                // makePathEntry can stamp the right layerId;
                                // it is omitted again when that layer is the
                                // owner, which is every pre-group project.
                                window.app.addPanelToCustomPowerPath(clickedPanel.panel, clickedLayer);
                            }
                        } else if (!isPower && window.app.isCustomFlowEditing(window.app.currentLayer) && reachable) {
                            if (window.app.customSelection.size > 0) {
                                window.app.clearCustomSelection();
                            } else {
                                window.app.addPanelToCustomPath(clickedPanel.panel, clickedLayer);
                            }
                        } else if (!window.app.isCustomFlowEditing(window.app.currentLayer) && !window.app.isCustomPowerEditing(window.app.currentLayer)) {
                            window.app.togglePanelSelection(clickedPanel.panel);
                        }
                    } else {
                        if (this.viewMode === 'power' && window.app.isCustomPowerEditing(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                            window.app.powerCustomSelection.clear();
                            window.app.updateCustomPowerUI();
                        }
                        if (this.viewMode === 'data-flow' && window.app.isCustomFlowEditing(window.app.currentLayer) && window.app.customSelection.size > 0) {
                            window.app.clearCustomSelection();
                        }
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                } else {
                    // v0.11.0 screen groups: the marquee crosses members too.
                    //
                    // It could not before, and the reason was real:
                    // customSelection / powerCustomSelection were keyed by the
                    // UNSCOPED getPanelKey, `${row},${col}`, so member A's R0C0
                    // and member B's R0C0 were the SAME entry in the Set and a
                    // marquee spanning two members could only ever commit the
                    // OWNER's cabinets under the peer's row and column - a
                    // silently wrong path, not a partly-working one. Those two
                    // Sets are now keyed by getScopedPanelKey,
                    // `${layerId}:${row},${col}`, which is what makes a
                    // cross-member selection expressible at all.
                    // (pixelMapSelection stays unscoped - it is a single-screen
                    // feature and its overlay still parses the plain key.)
                    //
                    // currentLayer stays the OWNER of the port/circuit being
                    // drawn even when the rect covers a peer; selectPanelsInRect
                    // hit-tests every layer the owner's path may legally reach.
                    if (this.viewMode === 'power') {
                        window.app.selectPowerPanelsInRect(window.app.currentLayer, this.selectionRect);
                    } else {
                        window.app.selectPanelsInRect(window.app.currentLayer, this.selectionRect);
                    }
                }
            }
            this.selectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('panel_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }

        if (this.isSelectingPixelMapPanels) {
            this.isSelectingPixelMapPanels = false;
            if (this.selectionRect && window.app && window.app.currentLayer) {
                const w = Math.abs(this.selectionRect.x2 - this.selectionRect.x1);
                const h = Math.abs(this.selectionRect.y2 - this.selectionRect.y1);
                if (w < 0.5 && h < 0.5) {
                    // Click without drag.
                    //  - Plain click on a panel: replace the selection with just that panel
                    //    (resets multi-select instead of confusingly toggling one panel out).
                    //  - Cmd/Ctrl+click: additive, toggle that panel in/out of the selection.
                    //  - Plain click on empty space: clear the selection.
                    const clickedPanel = this.getPanelAt(this.selectionRect.x1, this.selectionRect.y1);
                    const additive = e.metaKey || e.ctrlKey;
                    // Allow click-select on hidden panels so they can be
                    // bulk-restored via the sidebar.
                    if (clickedPanel && clickedPanel.layerId === window.app.currentLayer.id) {
                        if (additive) {
                            window.app.togglePixelMapPanelSelection(clickedPanel.panel);
                        } else {
                            window.app.pixelMapSelection.clear();
                            window.app.pixelMapSelection.add(window.app.getPanelKey(clickedPanel.panel));
                            window.app.updatePixelMapBulkActionUI();
                            this.render();
                        }
                    } else if (!additive) {
                        window.app.clearPixelMapSelection();
                    }
                } else {
                    window.app.selectPixelMapPanelsInRect(window.app.currentLayer, this.selectionRect);
                }
            }
            this.selectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('panel_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }
        if (this.isSelectingLayers) {
            this.isSelectingLayers = false;
            if (this.layerSelectionRect && window.app) {
                const w = Math.abs(this.layerSelectionRect.x2 - this.layerSelectionRect.x1);
                const h = Math.abs(this.layerSelectionRect.y2 - this.layerSelectionRect.y1);
                const isToggle = e.metaKey || e.ctrlKey;
                if (w < 0.5 && h < 0.5) {
                    let layer = this.getLayerAt(this.layerSelectionRect.x1, this.layerSelectionRect.y1);
                    if (!layer) {
                        const clickedPanel = this.getPanelAt(this.layerSelectionRect.x1, this.layerSelectionRect.y1);
                        if (clickedPanel) {
                            layer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        }
                    }
                    if (layer) {
                        if (isToggle) {
                            this._toggleLayerSelectionFromCanvas(layer);
                        } else {
                            this._selectLayerFromCanvas(layer);
                        }
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_select_click', { viewMode: this.viewMode, layerId: layer.id, toggle: isToggle });
                        }
                    }
                } else {
                    window.app.selectLayersInRect(this.layerSelectionRect, isToggle);
                    // v0.11.0: a marquee that catches one member of a group
                    // catches the group. Skipped for the toggle (Cmd/Ctrl)
                    // marquee, where re-adding what the user just toggled OUT
                    // would fight the gesture.
                    if (!isToggle && this._extendSelectionToGroups()
                            && typeof window.app.renderLayers === 'function') {
                        window.app.renderLayers();
                    }
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('layer_selection_box', { viewMode: this.viewMode, toggle: isToggle });
                    }
                }
            }
            this.layerSelectionRect = null;
            if (typeof sendClientLog === 'function') {
                sendClientLog('layer_selection_end', { viewMode: this.viewMode });
            }
            this.render();
            return;
        }
        if (this.layerSelectionRect) {
            this.layerSelectionRect = null;
            this.render();
        }
        if (this.isDragging) {
            this.isDragging = false;
            this.canvas.style.cursor = this.spacePressed ? 'grab' : 'default';
        } else if (this.isDraggingLayer) {
            this.isDraggingLayer = false;
            this._crossCanvasDropTarget = null;

            if (window.app && window.app.currentLayer) {
                const _dropWY = ((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom;
                const dx = Math.round(this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom, _dropWY) - this.dragLayerStartX);
                const dy = Math.round(_dropWY - this.dragLayerStartY);
                
                let snapDx = dx;
                let snapDy = dy;
                let newOffsetX = this.layerStartOffset.x + dx;
                let newOffsetY = this.layerStartOffset.y + dy;
                
                // Apply magnetic snapping to final position (only if enabled)
                if (this.magneticSnap) {
                    const snapResult = this.calculateMagneticSnap(newOffsetX, newOffsetY, window.app.currentLayer);
                    snapDx = snapResult.x - this.layerStartOffset.x;
                    snapDy = snapResult.y - this.layerStartOffset.y;
                }
                
                const selected = this.dragLayerOffsets && this.dragLayerOffsets.length > 0
                    ? this.dragLayerOffsets
                    : [{ id: window.app.currentLayer.id, startX: this.layerStartOffset.x, startY: this.layerStartOffset.y }];
                
                const movable = selected.filter(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    return layer && !layer.locked;
                });
                const showMode = this.dragLayerMode === 'show';
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    if (showMode) {
                        layer.showOffsetX = nextX;
                        layer.showOffsetY = nextY;
                    } else {
                        layer.offset_x = nextX;
                        layer.offset_y = nextY;
                        const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                        layer.panels.forEach(panel => {
                            const start = startMap.get(panel.id);
                            if (!start) return;
                            panel.x = start.x + snapDx;
                            panel.y = start.y + snapDy;
                        });
                    }
                });

                // Update Screen Info inputs to reflect current positions (respects mixed values)
                if (window.app.loadLayerToInputs) {
                    window.app.loadLayerToInputs();
                } else {
                    document.getElementById('offset-x').value = window.app.currentLayer.offset_x;
                    document.getElementById('offset-y').value = window.app.currentLayer.offset_y;
                }

                // Slice 7 + multi-select fix: cross-canvas drop check. The
                // hit-test uses the **mouse cursor position** at drop time,
                // not the layer's geometric center, for a wide layer
                // dragged onto a smaller canvas, the cursor lands inside
                // the target rect long before the layer's center does, and
                // the user expects "drop where I'm pointing". (Earlier
                // implementation used layer center and felt unresponsive
                // on big layers.) Layers in OTHER canvases keep their
                // normal within-canvas offset change.
                const primary = window.app.currentLayer;
                // v0.8.5: Pixel Map and Show Look maintain INDEPENDENT canvas
                // membership. The Show Look canvas (used for show-look /
                // data / power rendering) is the layer's `show_canvas_id`,
                // falling back to `canvas_id` when null (the default).
                // Pixel Map / Cabinet ID always use `canvas_id`.
                const isShowMode = (this.dragLayerMode === 'show');
                const primaryCanvasId = isShowMode
                    ? (primary.show_canvas_id || primary.canvas_id)
                    : primary.canvas_id;
                const primaryCanvas = window.app.project && Array.isArray(window.app.project.canvases)
                    ? window.app.project.canvases.find(c => c && c.id === primaryCanvasId)
                    : null;
                let crossCanvasHandled = false;
                if (primaryCanvas) {
                    // Mouse cursor world coords at drop (already computed
                    // above for the offset delta).
                    const cursorWY = ((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom;
                    const cursorWX = this._unmirrorWorldX(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom, cursorWY);
                    const targetCanvas = this._canvasAtPoint(cursorWX, cursorWY);
                    if (targetCanvas && targetCanvas.id !== primaryCanvasId) {
                        const mode = (e.metaKey || e.altKey) ? 'duplicate' : 'move';
                        // v0.8.6.3: in Show Look, include ALL unlocked
                        // selected layers in the multi-canvas drop,
                        // regardless of source canvas. Layers coming from
                        // different source canvases each get their own
                        // showOffset compensation based on their own source
                        // canvas's show_workspace (computed below).
                        // Pixel Map drag still requires same-source-canvas
                        // because Pixel Map reparent rewrites offset_x/y
                        // relative to the new canvas's origin and the bulk
                        // reparent endpoint expects a single source.
                        const peerCanvasId = (l) => isShowMode
                            ? (l.show_canvas_id || l.canvas_id)
                            : l.canvas_id;
                        const movedIds = [primary.id];
                        if (window.app.selectedLayerIds && window.app.selectedLayerIds.size > 1) {
                            window.app.selectedLayerIds.forEach(id => {
                                if (id === primary.id) return;
                                const l = window.app.project.layers.find(x => x.id === id);
                                if (!l || l.locked) return;
                                if (peerCanvasId(l) === targetCanvas.id) return; // already there
                                if (isShowMode) {
                                    movedIds.push(id);
                                } else if (peerCanvasId(l) === primaryCanvasId) {
                                    movedIds.push(id);
                                }
                            });
                        }
                        if (isShowMode) {
                            // Show Look drag: persist the freshly-dragged
                            // showOffsetX/Y first (no saveState on this PUT
                            //, the moveLayerShowCanvas .then() will snapshot
                            // post-everything state), then PUT show_canvas_id
                            // so canvas_id, offset_x/y, panels stay put.
                            // Duplicate is not supported here (mode is
                            // forced to 'move') since show-canvas reassign
                            // isn't a clone op.
                            //
                            // v0.8.5 fix: showOffsetX/Y are stored CANVAS-
                            // RELATIVE (renderer adds canvas.workspace_x/y to
                            // them). When we swap the layer's effective show
                            // canvas, we MUST compensate the offsets by
                            // (oldCanvas.workspace - newCanvas.workspace) or
                            // the layer visually JUMPS to a wrong spot
                            // because (newCanvas.workspace + sameOffset) !=
                            // (oldCanvas.workspace + sameOffset). Without
                            // this, dragging a c2 screen into c1's area
                            // looked like the layer was still in c2's space
                            // (or even way off-screen).
                            // v0.8.5.3: compensation must use the SHOW-LOOK
                            // workspace of each canvas (the one the layer is
                            // actually rendered against in this view).
                            // v0.8.6.3: each moved layer might come from a
                            // different source canvas (when the user has a
                            // multi-canvas selection), so compute per-layer
                            // compensation rather than reusing the primary's
                            // source delta for everyone.
                            const _ws2 = this._canvasWorkspace(targetCanvas);
                            const _canvasById = {};
                            (window.app.project.canvases || []).forEach(c => {
                                if (c && c.id) _canvasById[c.id] = c;
                            });
                            movedIds.forEach(id => {
                                const l = window.app.project.layers.find(x => x.id === id);
                                if (!l) return;
                                const srcCid = peerCanvasId(l);
                                const srcCanvas = _canvasById[srcCid];
                                if (!srcCanvas) return;
                                const _ws1 = this._canvasWorkspace(srcCanvas);
                                l.showOffsetX = (Number(l.showOffsetX) || 0) + (_ws1.wx - _ws2.wx);
                                l.showOffsetY = (Number(l.showOffsetY) || 0) + (_ws1.wy - _ws2.wy);
                            });
                            const toUpdate = window.app.getSelectedLayers
                                ? window.app.getSelectedLayers()
                                : [window.app.currentLayer];
                            window.app.updateLayers(toUpdate, false);
                            if (movedIds.length > 1 && typeof window.app.moveLayersShowCanvas === 'function') {
                                window.app.moveLayersShowCanvas(movedIds, targetCanvas.id);
                            } else if (typeof window.app.moveLayerShowCanvas === 'function') {
                                window.app.moveLayerShowCanvas(primary.id, targetCanvas.id);
                            }
                            crossCanvasHandled = true;
                        } else {
                            // Pixel Map drag: full processor reparent
                            // (resets offset_x/y, rebuilds panel geometry
                            // at the new canvas's origin).
                            if (movedIds.length > 1 && typeof window.app.moveLayersCrossCanvas === 'function') {
                                window.app.moveLayersCrossCanvas(movedIds, targetCanvas.id, mode);
                                crossCanvasHandled = true;
                            } else if (typeof window.app.moveLayerCrossCanvas === 'function') {
                                window.app.moveLayerCrossCanvas(primary.id, targetCanvas.id, mode);
                                crossCanvasHandled = true;
                            }
                        }
                    }
                }

                if (!crossCanvasHandled) {
                    // Snapshot POST-drag state so one Cmd+Z reverts this drag.
                    if (typeof window.app.saveState === 'function') {
                        window.app.saveState(this.dragLayerMode === 'show' ? 'Move Layers (Show Look)' : 'Move Layers');
                    }
                    const toUpdate = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    window.app.updateLayers(toUpdate, false);
                }
                this.dragLayerMode = null;
            }
        } else if (this.isDraggingScreenName) {
            this.isDraggingScreenName = false;
            // Persist and snapshot ONLY if the label actually moved
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                let currentOffsetX = 0;
                let currentOffsetY = 0;

                if (this.viewMode === 'pixel-map') {
                    currentOffsetX = layer.screenNameOffsetXPixelMap || 0;
                    currentOffsetY = layer.screenNameOffsetYPixelMap || 0;
                } else if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                } else if (this.viewMode === 'show-look') {
                    currentOffsetX = layer.screenNameOffsetXShowLook || 0;
                    currentOffsetY = layer.screenNameOffsetYShowLook || 0;
                }

                const moved = currentOffsetX !== this.screenNameStartOffset.x || currentOffsetY !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Screen Name');
                    // Undo audit: the group-headline drag below persists to
                    // the server; this drag only wrote localStorage, so the
                    // moved label lived on the client until some unrelated
                    // updateLayers carried it up. The offsets are on the
                    // layer-PUT allow-list; send them the same way.
                    if (typeof window.app.updateLayers === 'function') {
                        window.app.updateLayers([layer], false);
                    }
                }
                window.app.saveClientSideProperties();
            }
            this.render();
        } else if (this.isDraggingGroupName) {
            this.isDraggingGroupName = false;
            const group = this._dragGroupNameGroup;
            this._dragGroupNameGroup = null;
            // Persist and snapshot ONLY if the headline actually moved. The
            // offsets live on the group, which rides the project itself, so
            // persistence is a project save rather than a layer PUT.
            if (group && window.app) {
                const f = this._screenNameOffsetFields();
                const moved = (group[f.x] || 0) !== this.screenNameStartOffset.x
                    || (group[f.y] || 0) !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Group Name');
                }
                if (typeof window.app.saveProject === 'function') {
                    window.app.saveProject();
                }
            }
            this.render();
        }
    },
    
    handleWheel(e) {
        e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // If horizontal scroll dominates (trackpad swipe), pan instead of zoom
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 1) {
            this.panX -= e.deltaX;
            this.panY -= e.deltaY;
            this.render();
            return;
        }

        // Ignore tiny deltaY to avoid accidental zoom during horizontal swipes
        if (Math.abs(e.deltaY) < 1) return;

        // Further reduced sensitivity: 1.025 instead of 1.05 (50% less again)
        const zoomFactor = e.deltaY < 0 ? 1.025 : 0.975;
        const newZoom = Math.max(0.01, Math.min(500.0, this.zoom * zoomFactor));  // Max 50000% for pixel-level zoom
        const worldX = (mouseX - this.panX) / this.zoom;
        const worldY = (mouseY - this.panY) / this.zoom;
        this.zoom = newZoom;
        this.panX = mouseX - worldX * this.zoom;
        this.panY = mouseY - worldY * this.zoom;
        document.getElementById('zoom-level').value = `${this._zoomToPercent(this.zoom)}%`;
        this.render();
    },

    handleContextMenu(e) {
        e.preventDefault();
        e.stopPropagation();
        if (!window.app) return;
        // In Pixel Map view: if right-click lands on a panel of currentLayer
        // and the panel is not already in the selection, treat it as a
        // single-panel selection so the menu actions target it.
        // In the views where screens can be moved, right-clicking a screen that
        // isn't part of the current selection targets that screen, so "Center
        // on Canvas" acts on what the user actually pointed at.
        if (['pixel-map', 'show-look'].includes(this.viewMode)) {
            const rect = this.canvas.getBoundingClientRect();
            const worldY = ((e.clientY - rect.top) - this.panY) / this.zoom;
            const worldX = this._unmirrorWorldX(((e.clientX - rect.left) - this.panX) / this.zoom, worldY);
            const hit = this.getLayerAt(worldX, worldY);
            // selectedLayerIds is a Set — use .has(), not Array.includes()
            // (which threw a TypeError here and aborted the handler).
            const selectedIds = window.app.selectedLayerIds;
            const alreadySelected = selectedIds
                && (typeof selectedIds.has === 'function'
                    ? selectedIds.has(hit && hit.id)
                    : Array.from(selectedIds).includes(hit && hit.id));
            if (hit && !alreadySelected) {
                this._selectLayerFromCanvas(hit);
            }
        }
        if (this.viewMode === 'pixel-map' && window.app.currentLayer) {
            const rect = this.canvas.getBoundingClientRect();
            const worldY = ((e.clientY - rect.top) - this.panY) / this.zoom;
            const worldX = this._unmirrorWorldX(((e.clientX - rect.left) - this.panX) / this.zoom, worldY);
            const clicked = this.getPanelAt(worldX, worldY);
            // Right-click works on hidden panels too, the menu shows
            // "Restore From Blank" so they can be brought back.
            if (clicked && clicked.layerId === window.app.currentLayer.id) {
                const key = window.app.getPanelKey(clicked.panel);
                if (!window.app.pixelMapSelection.has(key)) {
                    window.app.pixelMapSelection.clear();
                    window.app.pixelMapSelection.add(key);
                    window.app.updatePixelMapBulkActionUI();
                    this.render();
                }
            }
        }
        window.app.showContextMenu(e.clientX, e.clientY);
    },
    
    handleKeyDown(e) {
        // Check if user is typing in an input or textarea
        const isTyping = document.activeElement.tagName === 'INPUT' || 
                        document.activeElement.tagName === 'TEXTAREA' ||
                        document.activeElement.isContentEditable;

        if (!isTyping && window.app && window.app.handleCustomArrowKey(e)) {
            e.preventDefault();
            return;
        }

        // Esc closes an open per-run override edit (the override and its path
        // stay - only the editing session ends). Checked ahead of everything
        // else so a stray Esc cannot fall through to some other consumer while
        // an edit is open.
        if (e.code === 'Escape' && !isTyping && window.app && window.app._overrideEditing) {
            e.preventDefault();
            window.app.endOverrideEdit();
            return;
        }

        // Esc drops the sweep selection (and any half-armed sweep) - the
        // same escape every transient selection answers to.
        if (e.code === 'Escape' && !isTyping && window.app
                && (window.app._sweepSelection || this._sweepPending)) {
            e.preventDefault();
            window.app._sweepSelection = null;
            this._sweepPending = null;
            this._removeSweepHud();
            this.render();
            return;
        }

        // Holding Alt lights the run under the cursor for the override
        // gesture; recompute at the last known cursor position so the
        // highlight appears without waiting for the mouse to move.
        // preventDefault keeps the key from focusing the browser menu bar.
        if (e.key === 'Alt' && !isTyping
                && (this.viewMode === 'data-flow' || this.viewMode === 'power')) {
            e.preventDefault();
            this._overrideHoverFromClient(true);
        }

        // Space - only prevent default and pan if NOT typing
        if (e.code === 'Space' && !isTyping) {
            e.preventDefault();
            this.spacePressed = true;
            if (!this.isDragging) this.canvas.style.cursor = 'grab';
        }
        
        // Delete key - only delete layer if NOT typing
        if ((e.code === 'Delete' || e.code === 'Backspace') && !isTyping) {
            if (window.app && window.app.currentLayer) {
                e.preventDefault();
                window.app.deleteCurrentLayer();
            }
        }
        
        // Cmd/Ctrl+Z - Undo (works everywhere)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && !e.shiftKey) {
            if (e.repeat) return;
            e.preventDefault();
            // Undo audit: an undo fired mid-gesture was silently reverted -
            // the next mousemove re-derived positions from offsets captured
            // at mousedown against the pre-undo project, and the eventual
            // mouseup's snapshot truncated the redo stack. Commit whatever is
            // held through the normal finalizer first, so Ctrl+Z steps back
            // over the gesture the user was making - the same rule the
            // debounced-save flush inside undo() applies to typed edits.
            this._releaseTransientInput();
            if (window.app) window.app.undo();
        }

        // Cmd/Ctrl+Shift+Z - Redo (works everywhere)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && e.shiftKey) {
            if (e.repeat) return;
            e.preventDefault();
            // Same mid-gesture commit as undo above.
            this._releaseTransientInput();
            if (window.app) window.app.redo();
        }
        
        // Cmd/Ctrl+C - Copy (only if NOT typing in a text field)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyC' && !isTyping) {
            e.preventDefault();
            if (window.app) window.app.copyLayer();
        }
        
        // Cmd/Ctrl+V - Paste (only if NOT typing in a text field)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyV' && !isTyping) {
            e.preventDefault();
            if (window.app) window.app.pasteLayer();
        }
        
        // Cmd/Ctrl+J - Duplicate (standard)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyJ' && !isTyping) {
            e.preventDefault();
            if (window.app && window.app.currentLayer) {
                window.app.duplicateLayer(window.app.currentLayer);
            }
        }

        // Cmd/Ctrl+, - Preferences
        if ((e.metaKey || e.ctrlKey) && e.code === 'Comma' && !isTyping) {
            e.preventDefault();
            if (window.app) {
                window.app.openPreferencesModal();
            }
        }

        // Tab / Shift+Tab - next / previous custom PORT in Data Flow, custom
        // CIRCUIT in Power.
        //
        // These two used to inline their own copy of the step, testing
        // isCustomFlow FIRST with no view check - and isCustomFlow is a pure
        // layer-state predicate (flowPattern === 'custom'), not a view test.
        // So on a screen that had BOTH a custom data pattern and custom power
        // - which every screen in a group has, because the flow pattern is
        // shared across members - Tab in POWER view took the data branch and
        // silently advanced the DATA port. The circuit never moved, so the key
        // looked dead. Data flow worked, which is exactly why it went unseen:
        // there the first branch IS the right one. Same defect the drag-select
        // handler above carries a comment about; this copy was missed.
        //
        // Routed through stepCustomPort now, so there is ONE implementation
        // shared with the on-screen Next/Prev buttons. It checks the VIEW as
        // well as the pattern, and it PUTs the new index to the server -
        // which this handler also never did, so a Tab'd index was lost on the
        // next reload even when it moved the right one.
        //
        // A focused BUTTON owns Tab too. The Next/Prev buttons keep keyboard
        // focus after a mouse click, and this document-level handler used
        // to step AGAIN on the Tab that followed - so "click Next, press
        // Tab" skipped a circuit number, which is how a brand-new show
        // ended up drawn 1-4, 6-23 (user, 2026-09-03). Tab from a focused
        // control moves focus, as the browser intends; the shortcut is for
        // the canvas. (Not folded into isTyping: the arrow keys must keep
        // drawing after a Next click.)
        const onControl = document.activeElement
            && document.activeElement.tagName === 'BUTTON';
        if (e.code === 'Tab' && !e.metaKey && !e.ctrlKey && !isTyping
                && !onControl && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            const handled =
                (this.viewMode === 'data-flow' && window.app.isCustomFlowEditing(layer))
                || (this.viewMode === 'power' && window.app.isCustomPowerEditing(layer));
            if (handled) {
                e.preventDefault();
                window.app.stepCustomPort(e.shiftKey ? -1 : 1);
            }
        }

        // [ prev / ] next - the same step as Tab, and now the same one call.
        //
        // These two blocks were correctly view-guarded, so they never stepped
        // the wrong thing. They did mutate the index inline without either
        // updateLayers() or saveClientSideProperties(), and customPortIndex /
        // powerCustomIndex are persisted fields - so stepping to port 7 with
        // "]" and reloading, or letting any other edit PUT first, snapped the
        // index back to whatever a button had last written. stepCustomPort
        // does the step, the save, the localStorage write and the PUT.
        if (!isTyping && (e.code === 'BracketLeft' || e.code === 'BracketRight')
                && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            const handled =
                (this.viewMode === 'data-flow' && window.app.isCustomFlowEditing(layer))
                || (this.viewMode === 'power' && window.app.isCustomPowerEditing(layer));
            if (handled) {
                e.preventDefault();
                window.app.stepCustomPort(e.code === 'BracketLeft' ? -1 : 1);
            }
        }

        // Cmd/Ctrl+Shift+1 - Fit to view
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Digit1' && !isTyping) {
            e.preventDefault();
            this.fitToView();
        }

        // Cmd/Ctrl+Shift+2 - Zoom to selection (actual size 1:1)
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Digit2' && !isTyping) {
            e.preventDefault();
            this.zoomActual();
        }

        // Cmd/Ctrl+Shift+' - Toggle snap (standard: Snap to Grid)
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Quote' && !isTyping) {
            e.preventDefault();
            this.magneticSnap = !this.magneticSnap;
            const snapCheckbox = document.getElementById('magnetic-snap');
            if (snapCheckbox) snapCheckbox.checked = this.magneticSnap;
        }
    },

    handleKeyUp(e) {
        if (e.code === 'Space') {
            this.spacePressed = false;
            if (!this.isDragging) this.canvas.style.cursor = 'default';
        }
        if (e.key === 'Alt') {
            this._overrideHoverFromClient(false);
        }
    },

    // The run-under-cursor highlight, recomputed from the last known mouse
    // position - for the moment Alt goes down or up without the mouse moving.
    // Same client-to-world walk handleMouseMove makes, mirror included.
    _overrideHoverFromClient(active) {
        if (!window.app || typeof window.app.updateOverrideHover !== 'function') return;
        if (this.viewMode !== 'data-flow' && this.viewMode !== 'power') {
            window.app.updateOverrideHover(false, 0, 0);
            return;
        }
        const rect = this.canvas.getBoundingClientRect();
        const worldY = (((this._lastClientY || 0) - rect.top) - this.panY) / this.zoom;
        const worldX = this._unmirrorWorldX(
            (((this._lastClientX || 0) - rect.left) - this.panX) / this.zoom, worldY);
        window.app.updateOverrideHover(active, worldX, worldY);
    },

    // Focus loss eats the release events that end whatever is held right
    // now: cmd-tab with space down delivers the keyup to the other app, and
    // a mouse button let go over another window is never reported here
    // either. Without this, spacePressed (and any armed drag) stayed
    // latched until the user rediscovered the magic unstick tap. Called on
    // window blur and on tab-hide. Held-key state is dropped outright;
    // an in-flight drag is pushed through the normal mouseup finalizer at
    // the last known cursor position, because layer/canvas drags mutate
    // offsets live during mousemove and just clearing the flag would strand
    // those moves unpersisted with no undo snapshot.
    _releaseTransientInput() {
        this.spacePressed = false;
        // The Alt keyup goes with the focus too, so the run highlight would
        // otherwise stay lit until the next mouse move.
        if (window.app && window.app._overrideHover
                && typeof window.app.updateOverrideHover === 'function') {
            window.app.updateOverrideHover(false, 0, 0);
        }
        const armed = this.isDragging || this.isDraggingLayer
            || this.isDraggingScreenName || this.isDraggingGroupName
            || this.isDraggingCanvas || this.isAltPainting
            || this.isSelectingPanels || this.isSelectingPixelMapPanels
            || this.isSelectingLayers
            || this.selectionRect || this.layerSelectionRect;
        if (armed) {
            this.handleMouseUp({
                button: 0,
                clientX: this._lastClientX || 0,
                clientY: this._lastClientY || 0,
                shiftKey: false,
                altKey: false,
                metaKey: false,
                ctrlKey: false
            });
        }
        this.canvas.style.cursor = 'default';
    },

    getPanelAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            if ((layer.type || 'screen') === 'image') continue;
            // Convert world coords back into the layer's processor space so we
            // can hit-test against panel.x/y (which are stored at processor
            // position; show-look renders with a translate AND, for v0.8
            // multi-canvas, the per-layer render is wrapped in the parent
            // canvas's workspace translate). Subtract both.
            const { dx, dy } = this.getLayerRenderOffset(layer);
            const { wx, wy } = this._layerCanvasOffset(layer);
            // v0.9.3: undo the screen's rotation (Pixel Map / Cabinet ID) so the
            // click maps back to the unrotated panel grid before hit-testing.
            const up = this._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
            const lx = up.x;
            const ly = up.y;
            for (const panel of layer.panels) {
                // Don't skip hidden panels - they need to be clickable to toggle back
                if (lx >= panel.x && lx <= panel.x + panel.width &&
                    ly >= panel.y && ly <= panel.y + panel.height) {
                    return { panel, layerId: layer.id };
                }
            }
        }
        return null;
    },

    getLayerAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            // Hit-test against the layer's bounds in the *active view*, since
            // worldX/worldY are in the view's coord space (Show Look / Data /
            // Power render at the show position). v0.8: bounds returned by
            // getLayerBoundsInActiveView are in the canvas's local coord
            // space; shift by the canvas's workspace_x/y so the comparison
            // against worldX/worldY (which are in workspace coords) is right
            // for canvases beyond the first.
            const bounds = this.getLayerFootprintInActiveView(layer);
            const { wx, wy } = this._layerCanvasOffset(layer);
            const bx = bounds.x + wx;
            const by = bounds.y + wy;
            if (worldX >= bx && worldX <= bx + bounds.width &&
                worldY >= by && worldY <= by + bounds.height) {
                return layer;
            }
        }
        return null;
    },
});
