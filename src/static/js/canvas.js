class CanvasRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.zoom = 1.0;
        this.panX = 100;
        this.panY = 100;
        this.isDragging = false;
        this.isDraggingLayer = false;
        this.isDraggingScreenName = false;
        this.screenNameDragHistorySaved = false;
        this.isSelectingPanels = false;
        this.isSelectingLayers = false;
        this.selectionRect = null;
        this.layerSelectionRect = null;
        this.magneticSnap = true; // Magnetic snapping enabled by default
        this.spacePressed = false;
        this.rasterWidth = 1920;
        this.rasterHeight = 1080;
        this.showGrid = true;
        this.viewMode = 'pixel-map'; // Default view mode
        this.exportMode = false; // When true, hides grid and raster boundary for clean export
        
        // Label display settings
        this.showLabelName = true;
        this.showLabelSizePx = false;
        this.showLabelSizeM = false;
        this.showLabelSizeFt = false;
        this.showLabelInfo = false;
        this.labelsColor = '#ffffff';
        this.labelsFontSize = 30;
        
        // Offset display settings
        this.showOffsetTL = false;
        this.showOffsetTR = false;
        this.showOffsetBL = false;
        this.showOffsetBR = false;
        
        this.setupCanvas();
        this.setupEventListeners();
    }
    
    setupCanvas() {
        const wrapper = this.canvas.parentElement;
        this.canvas.width = wrapper.clientWidth;
        this.canvas.height = wrapper.clientHeight;
        this.render();
    }
    
    setupEventListeners() {
        this.canvas.addEventListener('mousedown', this.handleMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.handleMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.handleMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.handleWheel.bind(this));
        this.canvas.addEventListener('contextmenu', this.handleContextMenu.bind(this));
        document.addEventListener('keydown', this.handleKeyDown.bind(this));
        document.addEventListener('keyup', this.handleKeyUp.bind(this));
        window.addEventListener('mouseup', () => {
            const hadLayerRect = !!this.layerSelectionRect;
            const hadPanelRect = !!this.selectionRect;
            if (!this.isSelectingLayers && !this.isSelectingPanels && !hadLayerRect && !hadPanelRect) return;
            // Clear stuck selection box if mouseup happens off-canvas or flags get out of sync
            if (this.isSelectingLayers || hadLayerRect) {
                this.isSelectingLayers = false;
                this.layerSelectionRect = null;
            }
            if (this.isSelectingPanels || hadPanelRect) {
                this.isSelectingPanels = false;
                this.selectionRect = null;
            }
            if (typeof sendClientLog === 'function') {
                sendClientLog('selection_cleared_off_canvas', {
                    viewMode: this.viewMode,
                    hadLayerRect,
                    hadPanelRect
                });
            }
            this.render();
        });
        window.addEventListener('resize', () => this.setupCanvas());
    }

    snap(value) {
        return this.exportMode ? Math.round(value) : value;
    }

    snapRect(x, y, width, height) {
        if (!this.exportMode) {
            return { x, y, width, height };
        }
        return {
            x: Math.round(x),
            y: Math.round(y),
            width: Math.round(width),
            height: Math.round(height)
        };
    }

    getLayerBounds(layer) {
        if (layer && (layer.type || 'screen') === 'image') {
            const scale = Number(layer.imageScale) || 1;
            const width = (Number(layer.imageWidth) || 0) * scale;
            const height = (Number(layer.imageHeight) || 0) * scale;
            return {
                x: Number(layer.offset_x) || 0,
                y: Number(layer.offset_y) || 0,
                width,
                height
            };
        }
        if (layer && Array.isArray(layer.panels) && layer.panels.length > 0) {
            let minX = Infinity;
            let minY = Infinity;
            let maxX = -Infinity;
            let maxY = -Infinity;
            layer.panels.forEach(panel => {
                const x1 = Number(panel.x) || 0;
                const y1 = Number(panel.y) || 0;
                const x2 = x1 + (Number(panel.width) || 0);
                const y2 = y1 + (Number(panel.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return {
                x: minX,
                y: minY,
                width: maxX - minX,
                height: maxY - minY
            };
        }
        const width = (Number(layer.columns) || 0) * (Number(layer.cabinet_width) || 0);
        const height = (Number(layer.rows) || 0) * (Number(layer.cabinet_height) || 0);
        return {
            x: Number(layer.offset_x) || 0,
            y: Number(layer.offset_y) || 0,
            width,
            height
        };
    }
    
    handleMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldX = (mouseX - this.panX) / this.zoom;
        const worldY = (mouseY - this.panY) / this.zoom;
        
        if (e.button === 0 && this.spacePressed) {
            this.isDragging = true;
            this.dragStartX = mouseX;
            this.dragStartY = mouseY;
            this.canvas.style.cursor = 'grabbing';
            return;
        }
        
        if (e.button === 0 && e.shiftKey) {
            // Let shift+drag behavior handle screen name move
            if (window.app && window.app.currentLayer) {
                if (this.viewMode !== 'pixel-map') {
                    this.isDraggingScreenName = true;
                    this.dragScreenNameStartX = worldX;
                    this.dragScreenNameStartY = worldY;
                    
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
                    
                    this.screenNameStartOffset = { x: currentOffsetX, y: currentOffsetY };
                    return;
                }
            }
        }

        if (e.button === 0 && window.app && window.app.currentLayer && this.viewMode === 'data-flow') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlow(layer)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }
        if (e.button === 0 && window.app && window.app.currentLayer && this.viewMode === 'power') {
            const layer = window.app.currentLayer;
            if (window.app.isCustomPower(layer)) {
                this.isSelectingPanels = true;
                this.selectionRect = { x1: worldX, y1: worldY, x2: worldX, y2: worldY };
                if (typeof sendClientLog === 'function') {
                    sendClientLog('panel_selection_start', { viewMode: this.viewMode, layerId: layer.id });
                }
                return;
            }
        }

        if (e.button === 0 && !this.spacePressed && !e.shiftKey && !e.altKey) {
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
                // On pixel-map: drag entire layer
                // On other modes: drag screen name label only
                if (this.viewMode === 'pixel-map') {
                    const selected = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                    const uniqueSelected = [];
                    const seenIds = new Set();
                    selected.forEach(layer => {
                        if (!layer || seenIds.has(layer.id)) return;
                        seenIds.add(layer.id);
                        uniqueSelected.push(layer);
                    });
                    const movable = uniqueSelected.filter(layer => !layer.locked);
                    if (movable.length === 0) {
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_drag_blocked_locked', { viewMode: this.viewMode });
                        }
                        return;
                    }
                    this.isDraggingLayer = true;
                    this.dragLayerStartX = worldX;
                    this.dragLayerStartY = worldY;
                    this.layerStartOffset = {
                        x: window.app.currentLayer.offset_x,
                        y: window.app.currentLayer.offset_y
                    };
                    this.dragLayerOffsets = movable.map(layer => ({
                        id: layer.id,
                        startX: layer.offset_x,
                        startY: layer.offset_y,
                        panelStarts: (layer.panels || []).map(panel => ({
                            id: panel.id,
                            x: panel.x,
                            y: panel.y
                        }))
                    }));
                    if (typeof sendClientLog === 'function') {
                        sendClientLog('layer_drag_start', { viewMode: this.viewMode, layerIds: movable.map(l => l.id) });
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
        } else if (e.button === 0 && e.altKey) {
            // Alt+click to hide panels only on pixel-map
            if (this.viewMode === 'pixel-map') {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel && window.app) {
                    window.app.togglePanelHidden(clickedPanel.layerId, clickedPanel.panel.id);
                }
            }
        } else if (e.button === 0 && this.viewMode === 'data-flow' && window.app) {
            const layer = this.getLayerAt(worldX, worldY);
            if (layer) {
                window.app.selectLayer(layer);
            } else {
                const clickedPanel = this.getPanelAt(worldX, worldY);
                if (clickedPanel) {
                    const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                    if (panelLayer) {
                        window.app.selectLayer(panelLayer);
                    }
                }
            }
        } else if (e.button === 0) {
            if (window.app) {
                const layer = this.getLayerAt(worldX, worldY);
                if (layer) {
                    window.app.selectLayer(layer);
                } else {
                    const clickedPanel = this.getPanelAt(worldX, worldY);
                    if (clickedPanel) {
                        const panelLayer = window.app.project.layers.find(l => l.id === clickedPanel.layerId);
                        if (panelLayer) {
                            window.app.selectLayer(panelLayer);
                        }
                    }
                }
            }
        }
    }
    
    handleMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const worldX = (mouseX - this.panX) / this.zoom;
        const worldY = (mouseY - this.panY) / this.zoom;

        if (this.isSelectingPanels && this.selectionRect) {
            this.selectionRect.x2 = worldX;
            this.selectionRect.y2 = worldY;
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                window.app.selectPanelsInRect(window.app.currentLayer, this.selectionRect);
            } else if (window.app && window.app.currentLayer && this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer)) {
                window.app.selectPowerPanelsInRect(window.app.currentLayer, this.selectionRect);
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
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    layer.offset_x = nextX;
                    layer.offset_y = nextY;
                    const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                    layer.panels.forEach(panel => {
                        const start = startMap.get(panel.id);
                        if (!start) return;
                        panel.x = start.x + snapDx;
                        panel.y = start.y + snapDy;
                    });
                });
                
                this.render();
            }
        } else if (this.isDraggingScreenName) {
            // Screen name dragging with snap positions - tab-specific
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                const bounds = this.getLayerBounds(layer);
                const layerWidth = bounds.width;
                const layerHeight = bounds.height;
                
                // Calculate raw offset from drag
                const dx = worldX - this.dragScreenNameStartX;
                const dy = worldY - this.dragScreenNameStartY;
                
                let newOffsetX = this.screenNameStartOffset.x + dx;
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
                if (this.viewMode === 'cabinet-id') {
                    layer.screenNameOffsetXCabinet = newOffsetX;
                    layer.screenNameOffsetYCabinet = newOffsetY;
                } else if (this.viewMode === 'data-flow') {
                    layer.screenNameOffsetXDataFlow = newOffsetX;
                    layer.screenNameOffsetYDataFlow = newOffsetY;
                } else if (this.viewMode === 'power') {
                    layer.screenNameOffsetXPower = newOffsetX;
                    layer.screenNameOffsetYPower = newOffsetY;
                }
                
                this.render();
            }
        }
        
        if (this.spacePressed && !this.isDragging) {
            this.canvas.style.cursor = 'grab';
        } else if (!this.isDragging && !this.isDraggingLayer && !this.isDraggingScreenName) {
            this.canvas.style.cursor = 'default';
        }
    }
    
    handleMouseUp(e) {
        if (this.isSelectingPanels) {
            this.isSelectingPanels = false;
            if (this.selectionRect && window.app && window.app.currentLayer) {
                const w = Math.abs(this.selectionRect.x2 - this.selectionRect.x1);
                const h = Math.abs(this.selectionRect.y2 - this.selectionRect.y1);
                if (w < 0.5 && h < 0.5) {
                    if (this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                        window.app.powerCustomSelection.clear();
                        window.app.updateCustomPowerUI();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    if (this.viewMode === 'data-flow' && window.app.isCustomFlow(window.app.currentLayer) && window.app.customSelection.size > 0) {
                        window.app.clearCustomSelection();
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                    const clickedPanel = this.getPanelAt(this.selectionRect.x1, this.selectionRect.y1);
                    if (clickedPanel) {
                        const isPower = this.viewMode === 'power';
                        if (isPower && window.app.isCustomPower(window.app.currentLayer) && clickedPanel.layerId === window.app.currentLayer.id) {
                            if (window.app.powerCustomSelection.size > 0) {
                                window.app.powerCustomSelection.clear();
                                window.app.updateCustomPowerUI();
                            } else {
                                window.app.addPanelToCustomPowerPath(clickedPanel.panel);
                            }
                        } else if (!isPower && window.app.isCustomFlow(window.app.currentLayer) && clickedPanel.layerId === window.app.currentLayer.id) {
                            if (window.app.customSelection.size > 0) {
                                window.app.clearCustomSelection();
                            } else {
                                window.app.addPanelToCustomPath(clickedPanel.panel);
                            }
                        } else if (!window.app.isCustomFlow(window.app.currentLayer) && !window.app.isCustomPower(window.app.currentLayer)) {
                            window.app.togglePanelSelection(clickedPanel.panel);
                        }
                    } else {
                        if (this.viewMode === 'power' && window.app.isCustomPower(window.app.currentLayer) && window.app.powerCustomSelection.size > 0) {
                            window.app.powerCustomSelection.clear();
                            window.app.updateCustomPowerUI();
                        }
                        if (this.viewMode === 'data-flow' && window.app.isCustomFlow(window.app.currentLayer) && window.app.customSelection.size > 0) {
                            window.app.clearCustomSelection();
                        }
                        this.selectionRect = null;
                        this.render();
                        return;
                    }
                } else {
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
                            window.app.toggleLayerSelection(layer);
                        } else {
                            window.app.selectLayer(layer);
                        }
                        if (typeof sendClientLog === 'function') {
                            sendClientLog('layer_select_click', { viewMode: this.viewMode, layerId: layer.id, toggle: isToggle });
                        }
                    }
                } else {
                    window.app.selectLayersInRect(this.layerSelectionRect, isToggle);
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
            
            if (window.app && window.app.currentLayer) {
                const dx = Math.round(((e.clientX - this.canvas.getBoundingClientRect().left) - this.panX) / this.zoom - this.dragLayerStartX);
                const dy = Math.round(((e.clientY - this.canvas.getBoundingClientRect().top) - this.panY) / this.zoom - this.dragLayerStartY);
                
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
                movable.forEach(item => {
                    const layer = window.app.project.layers.find(l => l.id === item.id);
                    if (!layer || layer.locked) return;
                    const nextX = item.startX + snapDx;
                    const nextY = item.startY + snapDy;
                    layer.offset_x = nextX;
                    layer.offset_y = nextY;
                    const startMap = new Map((item.panelStarts || []).map(p => [p.id, p]));
                    layer.panels.forEach(panel => {
                        const start = startMap.get(panel.id);
                        if (!start) return;
                        panel.x = start.x + snapDx;
                        panel.y = start.y + snapDy;
                    });
                });
                
                // Update Screen Info inputs to reflect current positions (respects mixed values)
                if (window.app.loadLayerToInputs) {
                    window.app.loadLayerToInputs();
                } else {
                    document.getElementById('offset-x').value = window.app.currentLayer.offset_x;
                    document.getElementById('offset-y').value = window.app.currentLayer.offset_y;
                }
                
                const toUpdate = window.app.getSelectedLayers ? window.app.getSelectedLayers() : [window.app.currentLayer];
                window.app.updateLayers(toUpdate, true, 'Move Layers');
            }
        } else if (this.isDraggingScreenName) {
            this.isDraggingScreenName = false;
            // Persist and snapshot ONLY if the label actually moved
            if (window.app && window.app.currentLayer) {
                const layer = window.app.currentLayer;
                let currentOffsetX = 0;
                let currentOffsetY = 0;

                if (this.viewMode === 'cabinet-id') {
                    currentOffsetX = layer.screenNameOffsetXCabinet || 0;
                    currentOffsetY = layer.screenNameOffsetYCabinet || 0;
                } else if (this.viewMode === 'data-flow') {
                    currentOffsetX = layer.screenNameOffsetXDataFlow || 0;
                    currentOffsetY = layer.screenNameOffsetYDataFlow || 0;
                } else if (this.viewMode === 'power') {
                    currentOffsetX = layer.screenNameOffsetXPower || 0;
                    currentOffsetY = layer.screenNameOffsetYPower || 0;
                }

                const moved = currentOffsetX !== this.screenNameStartOffset.x || currentOffsetY !== this.screenNameStartOffset.y;
                if (moved && typeof window.app.saveState === 'function') {
                    window.app.saveState('Move Screen Name');
                }
                window.app.saveClientSideProperties();
            }
            this.render();
        }
    }
    
    handleWheel(e) {
        e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        // Further reduced sensitivity: 1.025 instead of 1.05 (50% less again)
        const zoomFactor = e.deltaY < 0 ? 1.025 : 0.975;
        const newZoom = Math.max(0.01, Math.min(500.0, this.zoom * zoomFactor));  // Max 50000% for pixel-level zoom
        const worldX = (mouseX - this.panX) / this.zoom;
        const worldY = (mouseY - this.panY) / this.zoom;
        this.zoom = newZoom;
        this.panX = mouseX - worldX * this.zoom;
        this.panY = mouseY - worldY * this.zoom;
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    handleContextMenu(e) {
        e.preventDefault();
        e.stopPropagation();
        if (window.app) {
            window.app.showContextMenu(e.clientX, e.clientY);
        }
    }
    
    handleKeyDown(e) {
        // Check if user is typing in an input or textarea
        const isTyping = document.activeElement.tagName === 'INPUT' || 
                        document.activeElement.tagName === 'TEXTAREA' ||
                        document.activeElement.isContentEditable;

        if (!isTyping && window.app && window.app.handleCustomArrowKey(e)) {
            e.preventDefault();
            return;
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
            if (window.app) window.app.undo();
        }
        
        // Cmd/Ctrl+Shift+Z - Redo (works everywhere)
        if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ' && e.shiftKey) {
            if (e.repeat) return;
            e.preventDefault();
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
        
        // Cmd/Ctrl+J - Duplicate (Photoshop standard)
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

        // Shift+N - Next port (custom flow)
        if (e.shiftKey && !e.metaKey && !e.ctrlKey && e.code === 'KeyN' && !isTyping) {
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomFlowState(layer);
                window.app.saveState('Custom Port Change');
                layer.customPortIndex = (layer.customPortIndex || 1) + 1;
                window.app.updateCustomFlowUI();
                window.app.updatePortLabelEditor();
                this.render();
            } else if (window.app && window.app.currentLayer && window.app.isCustomPower(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomPowerState(layer);
                window.app.saveState('Power Custom Circuit Change');
                layer.powerCustomIndex = (layer.powerCustomIndex || 1) + 1;
                window.app.updateCustomPowerUI();
                this.render();
            }
        }

        // Shift+B - Previous port (custom flow)
        if (e.shiftKey && !e.metaKey && !e.ctrlKey && e.code === 'KeyB' && !isTyping) {
            if (window.app && window.app.currentLayer && window.app.isCustomFlow(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomFlowState(layer);
                window.app.saveState('Custom Port Change');
                layer.customPortIndex = Math.max(1, (layer.customPortIndex || 1) - 1);
                window.app.updateCustomFlowUI();
                window.app.updatePortLabelEditor();
                this.render();
            } else if (window.app && window.app.currentLayer && window.app.isCustomPower(window.app.currentLayer)) {
                e.preventDefault();
                const layer = window.app.currentLayer;
                window.app.ensureCustomPowerState(layer);
                window.app.saveState('Power Custom Circuit Change');
                layer.powerCustomIndex = Math.max(1, (layer.powerCustomIndex || 1) - 1);
                window.app.updateCustomPowerUI();
                this.render();
            }
        }

        // Custom flow port shortcuts: [ prev, ] next
        if (!isTyping && this.viewMode === 'data-flow' && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            if (window.app.isCustomFlow(layer)) {
                if (e.code === 'BracketLeft') {
                    e.preventDefault();
                    window.app.ensureCustomFlowState(layer);
                    window.app.saveState('Custom Port Change');
                    layer.customPortIndex = Math.max(1, (layer.customPortIndex || 1) - 1);
                    window.app.updateCustomFlowUI();
                    window.app.updatePortLabelEditor();
                    this.render();
                } else if (e.code === 'BracketRight') {
                    e.preventDefault();
                    window.app.ensureCustomFlowState(layer);
                    window.app.saveState('Custom Port Change');
                    layer.customPortIndex = (layer.customPortIndex || 1) + 1;
                    window.app.updateCustomFlowUI();
                    window.app.updatePortLabelEditor();
                    this.render();
                }
            }
        }
        if (!isTyping && this.viewMode === 'power' && window.app && window.app.currentLayer) {
            const layer = window.app.currentLayer;
            if (window.app.isCustomPower(layer)) {
                if (e.code === 'BracketLeft') {
                    e.preventDefault();
                    window.app.ensureCustomPowerState(layer);
                    window.app.saveState('Power Custom Circuit Change');
                    layer.powerCustomIndex = Math.max(1, (layer.powerCustomIndex || 1) - 1);
                    window.app.updateCustomPowerUI();
                    this.render();
                } else if (e.code === 'BracketRight') {
                    e.preventDefault();
                    window.app.ensureCustomPowerState(layer);
                    window.app.saveState('Power Custom Circuit Change');
                    layer.powerCustomIndex = (layer.powerCustomIndex || 1) + 1;
                    window.app.updateCustomPowerUI();
                    this.render();
                }
            }
        }

        // Cmd/Ctrl+0 - Fit to view (Photoshop standard)
        if ((e.metaKey || e.ctrlKey) && e.code === 'Digit0' && !isTyping) {
            e.preventDefault();
            this.fitToView();
        }

        // Cmd/Ctrl+1 - Actual size 1:1 (Photoshop standard)
        if ((e.metaKey || e.ctrlKey) && e.code === 'Digit1' && !isTyping) {
            e.preventDefault();
            this.zoomActual();
        }

        // Cmd/Ctrl+Shift+' - Toggle snap (Photoshop standard: Snap to Grid)
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Quote' && !isTyping) {
            e.preventDefault();
            this.magneticSnap = !this.magneticSnap;
            const snapCheckbox = document.getElementById('magnetic-snap');
            if (snapCheckbox) snapCheckbox.checked = this.magneticSnap;
        }
    }

    handleKeyUp(e) {
        if (e.code === 'Space') {
            this.spacePressed = false;
            if (!this.isDragging) this.canvas.style.cursor = 'default';
        }
    }
    
    getPanelAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            if ((layer.type || 'screen') === 'image') continue;
            for (const panel of layer.panels) {
                // Don't skip hidden panels - they need to be clickable to toggle back
                if (worldX >= panel.x && worldX <= panel.x + panel.width &&
                    worldY >= panel.y && worldY <= panel.y + panel.height) {
                    return { panel, layerId: layer.id };
                }
            }
        }
        return null;
    }

    getLayerAt(worldX, worldY) {
        if (!window.app || !window.app.project) return null;
        for (let i = window.app.project.layers.length - 1; i >= 0; i--) {
            const layer = window.app.project.layers[i];
            if (!layer.visible) continue;
            const bounds = this.getLayerBounds(layer);
            if (worldX >= bounds.x && worldX <= bounds.x + bounds.width &&
                worldY >= bounds.y && worldY <= bounds.y + bounds.height) {
                return layer;
            }
        }
        return null;
    }

    renderImageLayer(layer) {
        if (!layer || !layer.imageData) return;
        if (!layer._imageObj || layer._imageObj.src !== layer.imageData) {
            const img = new Image();
            img.onload = () => {
                if (layer._imageObj !== img) return;
                this.render();
            };
            img.src = layer.imageData;
            layer._imageObj = img;
        }
        const img = layer._imageObj;
        if (!img || !img.complete) return;
        const scale = Number(layer.imageScale) || 1;
        const w = (Number(layer.imageWidth) || img.width) * scale;
        const h = (Number(layer.imageHeight) || img.height) * scale;
        const x = Number(layer.offset_x) || 0;
        const y = Number(layer.offset_y) || 0;
        const prevSmoothing = this.ctx.imageSmoothingEnabled;
        this.ctx.imageSmoothingEnabled = true;
        this.ctx.drawImage(img, x, y, w, h);
        this.ctx.imageSmoothingEnabled = prevSmoothing;
    }
    
    render() {
        if (this.layerSelectionRect && !this.isSelectingLayers && !this.isSelectingPanels && !this.isDraggingLayer) {
            this.layerSelectionRect = null;
        }
        // In export mode, use black background; otherwise use dark gray
        this.ctx.fillStyle = this.exportMode ? '#000000' : '#0a0a0a';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Skip grid in export mode
        if (this.showGrid && !this.exportMode) {
            this.ctx.strokeStyle = '#1a1a1a';
            this.ctx.lineWidth = 1;
            const gridSpacing = 50 * this.zoom;
            const offsetX = this.panX % gridSpacing;
            const offsetY = this.panY % gridSpacing;
            for (let x = offsetX; x < this.canvas.width; x += gridSpacing) {
                this.ctx.beginPath();
                this.ctx.moveTo(x, 0);
                this.ctx.lineTo(x, this.canvas.height);
                this.ctx.stroke();
            }
            for (let y = offsetY; y < this.canvas.height; y += gridSpacing) {
                this.ctx.beginPath();
                this.ctx.moveTo(0, y);
                this.ctx.lineTo(this.canvas.width, y);
                this.ctx.stroke();
            }
        }
        
        this.ctx.save();
        // Round pan values to prevent sub-pixel anti-aliasing seams between panels
        this.ctx.setTransform(this.zoom, 0, 0, this.zoom, Math.round(this.panX), Math.round(this.panY));
        
        // Disable image smoothing to prevent anti-aliasing artifacts (seams between panels)
        this.ctx.imageSmoothingEnabled = false;
        
        // Raster boundary - skip in export mode
        if (!this.exportMode) {
            this.ctx.strokeStyle = '#ff0000';
            // Scale inversely with zoom so it's always visible (min 3px on screen)
            this.ctx.lineWidth = Math.max(3, 5 / this.zoom);
            this.ctx.setLineDash([10, 5]);
            this.ctx.strokeRect(0, 0, this.rasterWidth, this.rasterHeight);
            this.ctx.setLineDash([]);
        }
        
        if (window.app && window.app.project && window.app.project.layers) {
            // First pass: render all panels and mode-specific content (except labels)
            window.app.project.layers.forEach(layer => {
                if (layer.visible) {
                    if (this.viewMode === 'power') {
                        this.preparePowerLayerRenderData(layer);
                    }
                    if ((layer.type || 'screen') === 'image') {
                        this.renderImageLayer(layer);
                        return;
                    }
                    // Note: We don't fill the layer background anymore
                    // Each panel fills its own area, and hidden panels show as outlines
                    // This allows hidden panels to be transparent instead of black
                    
                    layer.panels.forEach(panel => {
                        if (panel.x >= this.rasterWidth || panel.y >= this.rasterHeight) return;
                        
                        // Render all panels - visible and hidden (hidden as ghost outlines)
                        this.renderPanel(panel, layer);
                    });
                    
                    // Render Circle with X test pattern
                    if (layer.show_circle_with_x && this.viewMode === 'pixel-map' && (layer.type || 'screen') !== 'image') {
                        this.renderCircleWithX(layer);
                    }
                    
                    // Render offsets (pixel-map only)
                    this.renderLayerOffsets(layer);
                    
                    // Render Cabinet ID numbers in world space (scales with zoom)
                    if (this.viewMode === 'cabinet-id') {
                        this.renderCabinetIDNumbers(layer);
                    }
                    
                    // Render Data Flow arrows (serpentine path with P1/R1 labels)
                    if (this.viewMode === 'data-flow') {
                        this.renderDataFlowArrows(layer);
                    }
                    if (this.viewMode === 'power') {
                        this.renderPowerArrows(layer);
                    }
                }
            });
            
            if (!this.exportMode && this.viewMode === 'data-flow') {
                this.renderCustomSelectionOverlay();
                this.renderCustomActivePortBadge();
            }
            if (!this.exportMode && this.viewMode === 'power') {
                this.renderPowerSelectionOverlay();
                this.renderPowerActiveCircuitBadge();
            }
            
            // Second pass: render all labels ON TOP of panels, clipped to layer bounds
            const visibleLayers = window.app.project.layers.filter(l => l.visible);

            visibleLayers.forEach((layer) => {
                this.renderLayerLabels(layer);
            });
            
            // Third pass: render capacity error overlays ON TOP of labels (Data Flow mode only)
            if (this.viewMode === 'data-flow') {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        this.renderCapacityErrorOverlay(layer);
                    }
                });
            }
            if (this.viewMode === 'power') {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        this.renderPowerErrorOverlay(layer);
                    }
                });
            }
            
            // Draw bounding boxes around selected layers (skip during export)
            if (!this.exportMode && window.app && window.app.selectedLayerIds && window.app.selectedLayerIds.size > 0) {
                const selectedIds = window.app.selectedLayerIds;
                window.app.project.layers.forEach(layer => {
                    if (!layer.visible) return;
                    if (!selectedIds.has(layer.id)) return;
                    const bounds = this.getLayerBounds(layer);
                    const layerWidth = bounds.width;
                    const layerHeight = bounds.height;
                    this.ctx.strokeStyle = (window.app.currentLayer && window.app.currentLayer.id === layer.id) ? '#00ccff' : '#4A90E2';
                    this.ctx.lineWidth = 2 / this.zoom;
                    this.ctx.setLineDash([8 / this.zoom, 4 / this.zoom]);
                    this.ctx.strokeRect(bounds.x, bounds.y, layerWidth, layerHeight);
                    this.ctx.setLineDash([]);
                });
            }

            // Draw bounding box around selected layer ONLY during Shift+Drag (skip during export)
            if (!this.exportMode && this.isDraggingLayer && window.app && window.app.currentLayer) {
                const selectedLayer = window.app.currentLayer;
                if (selectedLayer.visible) {
                    const bounds = this.getLayerBounds(selectedLayer);
                    const layerWidth = bounds.width;
                    const layerHeight = bounds.height;
                    
                    this.ctx.strokeStyle = '#4A90E2';  // Blue highlight color
                    this.ctx.lineWidth = 3 / this.zoom;  // Scale with zoom
                    this.ctx.setLineDash([10 / this.zoom, 5 / this.zoom]);
                    this.ctx.strokeRect(
                        bounds.x,
                        bounds.y,
                        layerWidth,
                        layerHeight
                    );
                    this.ctx.setLineDash([]);
                }
            }

            // Draw selection rectangle + highlight for layer multi-select (skip during export)
            if (!this.exportMode && this.isSelectingLayers && this.layerSelectionRect) {
                const minX = Math.min(this.layerSelectionRect.x1, this.layerSelectionRect.x2);
                const maxX = Math.max(this.layerSelectionRect.x1, this.layerSelectionRect.x2);
                const minY = Math.min(this.layerSelectionRect.y1, this.layerSelectionRect.y2);
                const maxY = Math.max(this.layerSelectionRect.y1, this.layerSelectionRect.y2);

                this.ctx.save();
                // Darken selected layers while dragging
                if (window.app && window.app.project) {
                    window.app.project.layers.forEach(layer => {
                        if (!layer.visible) return;
                        const bounds = this.getLayerBounds(layer);
                        const layerWidth = bounds.width;
                        const layerHeight = bounds.height;
                        const x1 = bounds.x;
                        const y1 = bounds.y;
                        const x2 = x1 + layerWidth;
                        const y2 = y1 + layerHeight;
                        const intersects = x1 <= maxX && x2 >= minX && y1 <= maxY && y2 >= minY;
                        if (intersects) {
                            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
                            this.ctx.fillRect(x1, y1, layerWidth, layerHeight);
                        }
                    });
                }

                this.ctx.strokeStyle = '#4A90E2';
                this.ctx.lineWidth = 2 / this.zoom;
                this.ctx.setLineDash([6 / this.zoom, 4 / this.zoom]);
                this.ctx.strokeRect(minX, minY, maxX - minX, maxY - minY);
                this.ctx.setLineDash([]);
                this.ctx.restore();
            }
            
            // Final pass: render pixel grid ON TOP of everything (all view modes, 1000%+ zoom)
            if (this.zoom >= 10) {
                window.app.project.layers.forEach(layer => {
                    if (layer.visible) {
                        this.renderPixelGrid(layer);
                    }
                });
            }
        }
        
        this.ctx.restore();
    }
    
    renderCircleWithX(layer) {
        // Calculate layer dimensions
        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        
        // Circle radius is about 40% of the smaller dimension (based on Pixel Perfect Pro reference)
        const radius = Math.min(layerWidth, layerHeight) * 0.40;
        
        // Save context and clip to raster bounds
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        
        this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'pixel-map');
        this.ctx.lineWidth = 2;
        
        // Draw perfect circle
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        this.ctx.stroke();
        
        // Draw X from corner to corner of entire layer
        this.ctx.beginPath();
        // Top-left to bottom-right
        this.ctx.moveTo(bounds.x, bounds.y);
        this.ctx.lineTo(bounds.x + layerWidth, bounds.y + layerHeight);
        // Top-right to bottom-left
        this.ctx.moveTo(bounds.x + layerWidth, bounds.y);
        this.ctx.lineTo(bounds.x, bounds.y + layerHeight);
        this.ctx.stroke();
        
        // Restore context (remove clipping)
        this.ctx.restore();
    }
    
    zoomIn() {
        this.zoom = Math.min(500.0, this.zoom * 1.2);  // Max 50000% for pixel-level zoom
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    zoomOut() {
        this.zoom = Math.max(0.01, this.zoom / 1.2);
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    setZoom(zoomLevel) {
        this.zoom = Math.max(0.01, Math.min(500.0, zoomLevel));
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    fitToView() {
        const zoomX = (this.canvas.width * 0.9) / this.rasterWidth;
        const zoomY = (this.canvas.height * 0.9) / this.rasterHeight;
        this.zoom = Math.min(zoomX, zoomY);
        this.panX = (this.canvas.width - this.rasterWidth * this.zoom) / 2;
        this.panY = (this.canvas.height - this.rasterHeight * this.zoom) / 2;
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    zoomActual() {
        if (!window.app || !window.app.currentLayer) {
            this.zoom = 1.0;
            this.panX = 100;
            this.panY = 100;
        } else {
            const layer = window.app.currentLayer;
            const bounds = this.getLayerBounds(layer);
            const layerWidth = bounds.width;
            const layerHeight = bounds.height;
            const zoomX = (this.canvas.width * 0.9) / layerWidth;
            const zoomY = (this.canvas.height * 0.9) / layerHeight;
            this.zoom = Math.min(zoomX, zoomY);
            const layerCenterX = bounds.x + layerWidth / 2;
            const layerCenterY = bounds.y + layerHeight / 2;
            this.panX = this.canvas.width / 2 - layerCenterX * this.zoom;
            this.panY = this.canvas.height / 2 - layerCenterY * this.zoom;
        }
        document.getElementById('zoom-level').value = `${Math.round(this.zoom * 100)}%`;
        this.render();
    }
    
    calculateMagneticSnap(offsetX, offsetY, currentLayer) {
        const snapDistance = 20; // Snap within 20 pixels - feels natural
        let snappedX = offsetX;
        let snappedY = offsetY;
        
        const currentBounds = this.getLayerBounds(currentLayer);
        const layerWidth = currentBounds.width;
        const layerHeight = currentBounds.height;
        
        const currentLeft = offsetX;
        const currentRight = offsetX + layerWidth;
        const currentTop = offsetY;
        const currentBottom = offsetY + layerHeight;
        
        
        // Snap to raster boundaries - HARD EDGES ONLY
        // Left edge to 0
        if (Math.abs(currentLeft - 0) <= snapDistance) {
            snappedX = 0;
        }
        // Right edge to raster width
        if (Math.abs(currentRight - this.rasterWidth) <= snapDistance) {
            snappedX = this.rasterWidth - layerWidth;
        }
        // Top edge to 0
        if (Math.abs(currentTop - 0) <= snapDistance) {
            snappedY = 0;
        }
        // Bottom edge to raster height
        if (Math.abs(currentBottom - this.rasterHeight) <= snapDistance) {
            snappedY = this.rasterHeight - layerHeight;
        }
        
        // Snap to other layers - HARD EDGES ONLY
        if (window.app && window.app.project) {
            window.app.project.layers.forEach(layer => {
                if (layer.id === currentLayer.id || !layer.visible) return;
                
                const otherBounds = this.getLayerBounds(layer);
                const otherLeft = otherBounds.x;
                const otherRight = otherBounds.x + otherBounds.width;
                const otherTop = otherBounds.y;
                const otherBottom = otherBounds.y + otherBounds.height;
                
                // Snap any edge of current layer to any edge of other layer
                // Left edge snaps
                if (Math.abs(currentLeft - otherLeft) <= snapDistance) snappedX = otherLeft;
                if (Math.abs(currentLeft - otherRight) <= snapDistance) snappedX = otherRight;
                
                // Right edge snaps
                if (Math.abs(currentRight - otherLeft) <= snapDistance) snappedX = otherLeft - layerWidth;
                if (Math.abs(currentRight - otherRight) <= snapDistance) snappedX = otherRight - layerWidth;
                
                // Top edge snaps
                if (Math.abs(currentTop - otherTop) <= snapDistance) snappedY = otherTop;
                if (Math.abs(currentTop - otherBottom) <= snapDistance) snappedY = otherBottom;
                
                // Bottom edge snaps
                if (Math.abs(currentBottom - otherTop) <= snapDistance) snappedY = otherTop - layerHeight;
                if (Math.abs(currentBottom - otherBottom) <= snapDistance) snappedY = otherBottom - layerHeight;
            });
        }
        
        return { x: Math.round(snappedX), y: Math.round(snappedY) };
    }
    
    setViewMode(mode) {
        this.viewMode = mode;
        this.render();
    }

    getLayerBorderColor(layer, mode = this.viewMode) {
        if (!layer) return '#ffffff';
        if (mode === 'cabinet-id') return layer.border_color_cabinet || layer.border_color || '#ffffff';
        if (mode === 'data-flow') return layer.border_color_data || layer.border_color || '#ffffff';
        if (mode === 'power') return layer.border_color_power || layer.border_color || '#ffffff';
        return layer.border_color_pixel || layer.border_color || '#ffffff';
    }
    
    renderPanel(panel, layer) {
        const clipX = Math.max(0, panel.x);
        const clipY = Math.max(0, panel.y);
        const clipWidth = Math.min(panel.width, this.rasterWidth - panel.x);
        const clipHeight = Math.min(panel.height, this.rasterHeight - panel.y);
        
        if (clipWidth <= 0 || clipHeight <= 0) return;
        
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(clipX, clipY, clipWidth, clipHeight);
        this.ctx.clip();
        
        // Render based on view mode
        switch (this.viewMode) {
            case 'pixel-map':
                this.renderPixelMap(panel, layer);
                break;
            case 'cabinet-id':
                this.renderCabinetID(panel, layer);
                break;
            case 'data-flow':
                this.renderDataFlow(panel, layer);
                break;
            case 'power':
                this.renderPower(panel, layer);
                break;
        }
        
        this.ctx.restore();
    }
    
    renderPixelMap(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom like text
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'; // Semi-transparent white
            this.ctx.lineWidth = 1; // Thinner line for ghost, scales with zoom
            this.ctx.setLineDash([5, 5]); // Dashed line, scales with zoom
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]); // Reset dash
            return; // Don't fill, just outline
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        // Where two panels meet, you get 2+2 = 4 pixels total
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'pixel-map');
            this.ctx.lineWidth = 2;  // 2 LED pixels wide
            // Inset by half the line width so the full 2px is inside the panel
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
    }
    
    renderPixelGrid(layer) {
        // Render pixel grid over the ENTIRE layer (on top of everything)
        // This shows the actual LED pixel boundaries (1 world unit = 1 LED pixel)
        
        const bounds = this.getLayerBounds(layer);
        const layerLeft = bounds.x;
        const layerTop = bounds.y;
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const layerRight = layerLeft + layerWidth;
        const layerBottom = layerTop + layerHeight;
        
        // Clip to raster bounds
        const clipX = Math.max(0, layerLeft);
        const clipY = Math.max(0, layerTop);
        const clipRight = Math.min(layerRight, this.rasterWidth);
        const clipBottom = Math.min(layerBottom, this.rasterHeight);
        
        if (clipRight <= clipX || clipBottom <= clipY) return;
        
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(clipX, clipY, clipRight - clipX, clipBottom - clipY);
        this.ctx.clip();
        
        // Only draw grid if pixels are large enough to see (at least 3 screen pixels per LED pixel)
        const screenPixelSize = this.zoom;  // 1 world unit = 1 LED pixel
        if (screenPixelSize < 3) {
            this.ctx.restore();
            return;
        }
        
        // Calculate visible range to optimize rendering
        const visibleLeft = (0 - this.panX) / this.zoom;
        const visibleTop = (0 - this.panY) / this.zoom;
        const visibleRight = (this.canvas.width - this.panX) / this.zoom;
        const visibleBottom = (this.canvas.height - this.panY) / this.zoom;
        
        // Grid line style - darker gray, more pronounced
        this.ctx.strokeStyle = 'rgba(80, 80, 80, 0.55)';
        this.ctx.lineWidth = 1 / this.zoom;  // 1 screen pixel wide
        
        // Draw vertical lines (every 1 world unit = 1 LED pixel)
        this.ctx.beginPath();
        const startCol = Math.max(0, Math.floor(visibleLeft - layerLeft));
        const endCol = Math.min(layerWidth, Math.ceil(visibleRight - layerLeft));
        
        for (let col = startCol; col <= endCol; col++) {
            const x = layerLeft + col;
            if (x >= clipX && x <= clipRight) {
                this.ctx.moveTo(x, clipY);
                this.ctx.lineTo(x, clipBottom);
            }
        }
        
        // Draw horizontal lines
        const startRow = Math.max(0, Math.floor(visibleTop - layerTop));
        const endRow = Math.min(layerHeight, Math.ceil(visibleBottom - layerTop));
        
        for (let row = startRow; row <= endRow; row++) {
            const y = layerTop + row;
            if (y >= clipY && y <= clipBottom) {
                this.ctx.moveTo(clipX, y);
                this.ctx.lineTo(clipRight, y);
            }
        }
        
        this.ctx.stroke();
        this.ctx.restore();
    }
    
    renderCabinetID(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'cabinet-id');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
        
        // Cabinet ID numbers rendered separately in screen space - see renderCabinetIDNumbers()
    }
    
    renderDataFlow(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }
        
        // Use normal checkerboard colors (removed blank mode)
        const color = panel.is_color1 ? layer.color1 : layer.color2;
        this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
        
        // Panel borders - 2 pixels wide per panel, drawn INSIDE the panel
        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'data-flow');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
        
        // Data flow arrows are rendered as a separate pass in renderDataFlowArrows
    }
    
    // Render capacity error overlay ON TOP of everything (including labels)
    // This renders WITHOUT clipping so it's visible even outside raster bounds
    renderCapacityErrorOverlay(layer) {
        if (!layer._capacityError) return;
        
        const err = layer._capacityError;
        const bounds = this.getLayerBounds(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        
        // Red semi-transparent overlay on the layer itself
        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);
        
        // Measure text to size box appropriately
        this.ctx.font = 'bold 48px Arial';
        const titleText = `CANNOT FIT COMPLETE ${err.unitType.toUpperCase()}`;
        const titleWidth = this.ctx.measureText(titleText).width;
        
        this.ctx.font = '28px Arial';
        const detailText = `Need ${err.unitCount} panels, port only fits ${err.panelsPerPort}`;
        const detailWidth = this.ctx.measureText(detailText).width;
        
        this.ctx.font = '24px Arial';
        const infoText = `Port: ${err.portCapacity.toLocaleString()} px | Panel: ${err.panelPixels.toLocaleString()} px`;
        const infoWidth = this.ctx.measureText(infoText).width;
        
        // Size box to fit text with padding
        const textBoxWidth = Math.max(titleWidth, detailWidth, infoWidth) + 40;
        const textBoxHeight = 130;
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Red border around text box
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        
        // Error text
        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = 'bold 48px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        this.ctx.fillText(titleText, layerCenterX, layerCenterY - 35);
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = '28px Arial';
        this.ctx.fillText(detailText, layerCenterX, layerCenterY + 10);
        this.ctx.font = '24px Arial';
        this.ctx.fillStyle = '#AAAAAA';
        this.ctx.fillText(infoText, layerCenterX, layerCenterY + 45);
    }
    
    renderDataFlowArrows(layer) {
        // Get the flow pattern (default: top-right, vertical-first)
        const pattern = layer.flowPattern || 'tl-h';
        const baseLineWidth = layer.arrowLineWidth || 4;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.dataFlowLabelSize || 30;
        const primaryColor = layer.primaryColor || '#00FF00';
        const primaryTextColor = layer.primaryTextColor || '#000000';
        const backupColor = layer.backupColor || '#FF0000';
        const backupTextColor = layer.backupTextColor || '#FFFFFF';
        const lineColor = layer.dataFlowColor || '#FFFFFF';
        const arrowColor = layer.arrowColor || '#0042AA';
        const useRandomColors = layer.randomDataColors || false;
        const isCustomFlow = pattern === 'custom';
        if (isCustomFlow) {
            // Clear any capacity error when in custom mode
            layer._capacityError = null;
        }
        // Calculate circle radius based on label size
        const circleRadius = labelSize * 1.2;
        
        // Random color palette for multi-port support
        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];
        
        // Get visible (non-hidden) panels
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;
        
        // Save context
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';
        
        const drawPort = (portPanels, portNum) => {
            if (portPanels.length === 0) return;
            
            const currentLineColor = useRandomColors ? randomColors[(portNum - 1) % randomColors.length] : lineColor;
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;
            
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                
                this.ctx.beginPath();
                this.ctx.moveTo(cx, cy);
                this.ctx.lineTo(nx, ny);
                this.ctx.stroke();
            }
            
            this.ctx.fillStyle = arrowColor;
            for (let i = 0; i < portPanels.length - 1; i++) {
                const current = portPanels[i];
                const next = portPanels[i + 1];
                
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                
                const midX = this.snap((cx + nx) / 2);
                const midY = this.snap((cy + ny) / 2);
                const angle = Math.atan2(ny - cy, nx - cx);
                const arrowLen = lineWidth * 3;
                
                this.ctx.beginPath();
                this.ctx.moveTo(
                    midX + arrowLen * Math.cos(angle),
                    midY + arrowLen * Math.sin(angle)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle - Math.PI / 5),
                    midY - arrowLen * Math.sin(angle - Math.PI / 5)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle + Math.PI / 5),
                    midY - arrowLen * Math.sin(angle + Math.PI / 5)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }
            
            const firstPanel = portPanels[0];
            let px = this.snap(firstPanel.x + firstPanel.width / 2);
            let py = this.snap(firstPanel.y + firstPanel.height / 2);
            const lastPanel = portPanels[portPanels.length - 1];
            let rx = this.snap(lastPanel.x + lastPanel.width / 2);
            let ry = this.snap(lastPanel.y + lastPanel.height / 2);
            const primaryLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'primary') : `P${portNum}`;
            const returnLabel = window.app ? window.app.getPortLabelText(layer, portNum, 'return') : `R${portNum}`;
            
            // If the port has only one panel, draw backup first so primary is on top.
            if (portPanels.length === 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, circleRadius, 0, Math.PI * 2);
                this.ctx.fill();
                this.ctx.fillStyle = backupTextColor;
                this.ctx.font = `bold ${labelSize}px Arial`;
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                this.ctx.fillText(returnLabel, rx, ry);
            }
            
            this.ctx.fillStyle = primaryColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, circleRadius, 0, Math.PI * 2);
            this.ctx.fill();
            
            this.ctx.fillStyle = primaryTextColor;
            this.ctx.font = `bold ${labelSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(primaryLabel, px, py);
            
            if (portPanels.length > 1) {
                this.ctx.fillStyle = backupColor;
                this.ctx.beginPath();
                this.ctx.arc(rx, ry, circleRadius, 0, Math.PI * 2);
                this.ctx.fill();
                
                this.ctx.fillStyle = backupTextColor;
                this.ctx.fillText(returnLabel, rx, ry);
            }
        };

        // Custom flow mode: use user-defined paths
        if (isCustomFlow && layer.customPortPaths) {
            const portNums = Object.keys(layer.customPortPaths)
                .map(n => parseInt(n, 10))
                .sort((a, b) => a - b);
            
            portNums.forEach(portNum => {
                const path = layer.customPortPaths[portNum] || [];
                const portPanels = path.map(p => {
                    const panel = layer.panels.find(panel => panel.row === p.row && panel.col === p.col);
                    return panel && !panel.hidden ? panel : null;
                }).filter(Boolean);
                drawPort(portPanels, portNum);
            });
            
            this.ctx.restore();
            return;
        }

        const assignments = window.app ? window.app.calculatePortAssignments(layer) : [];
        if (layer._capacityError) {
            this.ctx.restore();
            return;
        }

        const ports = new Map();
        assignments.forEach(item => {
            if (!item || !item.panel || item.panel.hidden) return;
            if (!ports.has(item.port)) ports.set(item.port, []);
            ports.get(item.port).push(item.panel);
        });

        [...ports.keys()].sort((a, b) => a - b).forEach(portNum => {
            drawPort(ports.get(portNum) || [], portNum);
        });
        
        this.ctx.restore();
    }

    getPowerCircuitPalette() {
        return ['#FF0000', '#FF8C00', '#FFE600', '#00CC00', '#1E4CFF', '#8A2BE2'];
    }

    getPowerCircuitColor(layer, circuitNum) {
        if (window.app && typeof window.app.getPowerCircuitColor === 'function') {
            return window.app.getPowerCircuitColor(layer, circuitNum);
        }
        const palette = this.getPowerCircuitPalette();
        return palette[(Math.max(1, circuitNum) - 1) % palette.length];
    }

    getPowerCircuitLetter(circuitNum) {
        let n = Math.max(1, parseInt(circuitNum, 10) || 1);
        let out = '';
        while (n > 0) {
            n -= 1;
            out = String.fromCharCode(65 + (n % 26)) + out;
            n = Math.floor(n / 26);
        }
        return out;
    }

    getPowerLabelTextColor(hexColor) {
        const normalized = String(hexColor || '').replace('#', '');
        if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return '#000000';
        const r = parseInt(normalized.slice(0, 2), 16);
        const g = parseInt(normalized.slice(2, 4), 16);
        const b = parseInt(normalized.slice(4, 6), 16);
        const luminance = (0.299 * r) + (0.587 * g) + (0.114 * b);
        return luminance > 150 ? '#000000' : '#FFFFFF';
    }

    getPowerPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    preparePowerLayerRenderData(layer) {
        if (!window.app) return;
        const isCustom = (layer.powerFlowPattern || 'tl-h') === 'custom';
        let error = null;
        let circuits = [];

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            circuits = circuitNums.map(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                return path
                    .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                    .filter(p => p && !p.hidden);
            });
        } else {
            const assignments = window.app.calculatePowerAssignments(layer);
            error = assignments.error;
            circuits = assignments.circuits || [];
        }

        layer._powerError = error;
        layer._powerCircuits = circuits;

        const panelCircuitMap = new Map();
        const panelIndexMap = new Map();
        if (!error) {
            circuits.forEach((circuitPanels, idx) => {
                const circuitNum = idx + 1;
                (circuitPanels || []).forEach((panel, panelIdx) => {
                    const key = this.getPowerPanelKey(panel);
                    panelCircuitMap.set(key, circuitNum);
                    panelIndexMap.set(key, panelIdx + 1);
                });
            });
        }
        layer._powerPanelCircuitMap = panelCircuitMap;
        layer._powerPanelIndexMap = panelIndexMap;
    }

    renderPowerArrows(layer) {
        const pattern = layer.powerFlowPattern || 'tl-h';
        const baseLineWidth = layer.powerLineWidth || 8;
        const lineWidth = this.exportMode ? Math.max(1, Math.round(baseLineWidth)) : baseLineWidth;
        const labelSize = layer.powerLabelSize || 14;
        const powerLabelBgColor = layer.powerLabelBgColor || '#D95000';
        const powerLabelTextColor = layer.powerLabelTextColor || '#000000';
        const lineColor = layer.powerLineColor || '#FF0000';
        const arrowColor = layer.powerArrowColor || '#0042AA';
        const useRandomColors = layer.powerRandomColors || false;
        const useColorCodedView = !!layer.powerColorCodedView;
        const isCustom = pattern === 'custom';
        if (isCustom) {
            layer._powerError = null;
        }
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        const randomColors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ];

        const drawCircuitLabel = (panelStart, panelNext, circuitNum) => {
            const label = window.app ? window.app.getPowerCircuitLabel(layer, circuitNum) : `S1-${circuitNum}`;
            const px = this.snap(panelStart.x + panelStart.width / 2);
            const py = this.snap(panelStart.y + panelStart.height / 2);
            this.ctx.font = `bold ${labelSize}px Arial`;
            const textWidth = this.ctx.measureText(label).width;
            const padding = Math.max(6, labelSize * 0.25);
            const circleRadius = Math.max(labelSize * 0.7, lineWidth * 1.4, textWidth / 2 + padding);

            this.ctx.fillStyle = powerLabelBgColor;
            this.ctx.beginPath();
            this.ctx.arc(px, py, circleRadius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.fillStyle = powerLabelTextColor;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(label, px, py);
        };

        if (useColorCodedView) {
            if (!Array.isArray(layer._powerCircuits) && window.app) {
                const assignments = window.app.calculatePowerAssignments(layer);
                layer._powerError = assignments.error;
                layer._powerCircuits = assignments.circuits || [];
            }
            if (layer._powerError || !Array.isArray(layer._powerCircuits)) {
                this.ctx.restore();
                return;
            }
            layer._powerCircuits.forEach((circuitPanels, idx) => {
                if (!circuitPanels || circuitPanels.length === 0) return;
                drawCircuitLabel(circuitPanels[0], circuitPanels[1], idx + 1);
            });
            this.ctx.restore();
            return;
        }

        const drawCircuit = (circuitPanels, circuitNum) => {
            if (circuitPanels.length === 0) return;
            const currentLineColor = useRandomColors ? randomColors[(circuitNum - 1) % randomColors.length] : lineColor;
            this.ctx.strokeStyle = currentLineColor;
            this.ctx.lineWidth = lineWidth;

            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                this.ctx.beginPath();
                this.ctx.moveTo(cx, cy);
                this.ctx.lineTo(nx, ny);
                this.ctx.stroke();
            }

            this.ctx.fillStyle = arrowColor;
            for (let i = 0; i < circuitPanels.length - 1; i++) {
                const current = circuitPanels[i];
                const next = circuitPanels[i + 1];
                const cx = this.snap(current.x + current.width / 2);
                const cy = this.snap(current.y + current.height / 2);
                const nx = this.snap(next.x + next.width / 2);
                const ny = this.snap(next.y + next.height / 2);
                const midX = this.snap((cx + nx) / 2);
                const midY = this.snap((cy + ny) / 2);
                const angle = Math.atan2(ny - cy, nx - cx);
                const arrowLen = lineWidth * 3;
                this.ctx.beginPath();
                this.ctx.moveTo(
                    midX + arrowLen * Math.cos(angle),
                    midY + arrowLen * Math.sin(angle)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle - Math.PI / 5),
                    midY - arrowLen * Math.sin(angle - Math.PI / 5)
                );
                this.ctx.lineTo(
                    midX - arrowLen * Math.cos(angle + Math.PI / 5),
                    midY - arrowLen * Math.sin(angle + Math.PI / 5)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }

            drawCircuitLabel(circuitPanels[0], circuitPanels[1], circuitNum);
        };

        if (isCustom && layer.powerCustomPaths) {
            const circuitNums = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b);
            circuitNums.forEach(circuitNum => {
                const path = layer.powerCustomPaths[circuitNum] || [];
                const panels = path
                    .map(pos => window.app.getPanelByRowCol(layer, pos.row, pos.col))
                    .filter(p => p && !p.hidden);
                drawCircuit(panels, circuitNum);
            });
            this.ctx.restore();
            return;
        }

        if (!Array.isArray(layer._powerCircuits) && window.app) {
            const assignments = window.app.calculatePowerAssignments(layer);
            layer._powerError = assignments.error;
            layer._powerCircuits = assignments.circuits || [];
        }
        if (layer._powerError) {
            this.ctx.restore();
            return;
        }

        layer._powerCircuits.forEach((circuitPanels, idx) => {
            if (!circuitPanels || circuitPanels.length === 0) return;
            drawCircuit(circuitPanels, idx + 1);
        });

        this.ctx.restore();
    }

    renderPowerErrorOverlay(layer) {
        if (!layer._powerError) return;
        const err = layer._powerError;
        const bounds = this.getLayerBounds(layer);
        const layerCenterX = bounds.x + (bounds.width / 2);
        const layerCenterY = bounds.y + (bounds.height / 2);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;

        this.ctx.fillStyle = 'rgba(255, 0, 0, 0.5)';
        this.ctx.fillRect(bounds.x, bounds.y, layerWidth, layerHeight);

        const titleText = err.message || 'POWER ERROR';
        this.ctx.font = 'bold 42px Arial';
        const titleWidth = this.ctx.measureText(titleText).width;
        const textBoxWidth = titleWidth + 40;
        const textBoxHeight = 90;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );
        this.ctx.strokeStyle = '#FF0000';
        this.ctx.lineWidth = 3;
        this.ctx.strokeRect(
            layerCenterX - textBoxWidth / 2,
            layerCenterY - textBoxHeight / 2,
            textBoxWidth,
            textBoxHeight
        );

        this.ctx.fillStyle = '#FF4444';
        this.ctx.font = 'bold 42px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(titleText, layerCenterX, layerCenterY);
    }
    
    // Get panel flow order for a specific range of rows (for horizontal-first patterns)
    getPanelFlowOrderForRows(layer, pattern, startRow, endRow) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const cols = layer.columns;
        
        // Parse pattern
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        
        const orderedPanels = [];
        const numRows = endRow - startRow + 1;
        
        // Horizontal-first serpentine within this rectangle
        for (let r = 0; r < numRows; r++) {
            const actualRow = startsTop ? (startRow + r) : (endRow - r);
            
            // Determine direction for this row (serpentine)
            let leftToRight;
            if (startsLeft) {
                leftToRight = (r % 2 === 0);
            } else {
                leftToRight = (r % 2 !== 0);
            }
            
            if (leftToRight) {
                for (let c = 0; c < cols; c++) {
                    const panel = panelMap.get(`${actualRow},${c}`);
                    if (panel) orderedPanels.push(panel);
                }
            } else {
                for (let c = cols - 1; c >= 0; c--) {
                    const panel = panelMap.get(`${actualRow},${c}`);
                    if (panel) orderedPanels.push(panel);
                }
            }
        }
        
        return orderedPanels;
    }
    
    // Get panel flow order for a specific range of columns (for vertical-first patterns)
    getPanelFlowOrderForCols(layer, pattern, startCol, endCol) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const rows = layer.rows;
        
        // Parse pattern
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        
        const orderedPanels = [];
        const numCols = endCol - startCol + 1;
        
        // Vertical-first serpentine within this rectangle
        for (let c = 0; c < numCols; c++) {
            const actualCol = startsLeft ? (startCol + c) : (endCol - c);
            
            // Determine direction for this column (serpentine)
            let topToBottom;
            if (startsTop) {
                topToBottom = (c % 2 === 0);
            } else {
                topToBottom = (c % 2 !== 0);
            }
            
            if (topToBottom) {
                for (let r = 0; r < rows; r++) {
                    const panel = panelMap.get(`${r},${actualCol}`);
                    if (panel) orderedPanels.push(panel);
                }
            } else {
                for (let r = rows - 1; r >= 0; r--) {
                    const panel = panelMap.get(`${r},${actualCol}`);
                    if (panel) orderedPanels.push(panel);
                }
            }
        }
        
        return orderedPanels;
    }
    
    getPanelFlowOrder(layer, pattern) {
        const visiblePanels = layer.panels.filter(p => !p.hidden);
        if (visiblePanels.length === 0) return [];
        const panelMap = new Map();
        visiblePanels.forEach(panel => panelMap.set(`${panel.row},${panel.col}`, panel));
        const cols = layer.columns;
        const rows = layer.rows;
        
        // Parse pattern
        const [startCorner, direction] = pattern.split('-');
        
        // Build ordered list based on pattern
        const ordered = [];
        
        // Determine starting position and iteration directions
        let startRow, startCol, rowDir, colDir, isVerticalFirst;
        
        switch (startCorner) {
            case 'tl': // top-left
                startRow = 0; startCol = 0;
                rowDir = 1; colDir = 1;
                break;
            case 'tr': // top-right
                startRow = 0; startCol = cols - 1;
                rowDir = 1; colDir = -1;
                break;
            case 'bl': // bottom-left
                startRow = rows - 1; startCol = 0;
                rowDir = -1; colDir = 1;
                break;
            case 'br': // bottom-right
                startRow = rows - 1; startCol = cols - 1;
                rowDir = -1; colDir = -1;
                break;
            default:
                startRow = 0; startCol = cols - 1;
                rowDir = 1; colDir = -1;
        }
        
        isVerticalFirst = (direction === 'v');
        
        if (isVerticalFirst) {
            // Vertical-first: traverse columns, serpentine within each column
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const shouldReverse = colOffset % 2 === 1;
                
                if (shouldReverse) {
                    // Reverse direction for serpentine
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                }
            }
        } else {
            // Horizontal-first: traverse rows, serpentine within each row
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const shouldReverse = rowOffset % 2 === 1;
                
                if (shouldReverse) {
                    // Reverse direction for serpentine
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel) ordered.push(panel);
                    }
                }
            }
        }
        
        return ordered;
    }
    
    renderPower(panel, layer) {
        // If panel is hidden, render as ghost outline only - scales with zoom
        if (panel.hidden) {
            this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(panel.x, panel.y, panel.width, panel.height);
            this.ctx.setLineDash([]);
            return;
        }

        let fillHex = null;
        let panelCircuitNum = null;
        if (layer.powerColorCodedView && !layer._powerError && layer._powerPanelCircuitMap instanceof Map) {
            const key = this.getPowerPanelKey(panel);
            panelCircuitNum = layer._powerPanelCircuitMap.get(key);
            if (panelCircuitNum) {
                fillHex = this.getPowerCircuitColor(layer, panelCircuitNum);
            }
        }

        if (fillHex) {
            this.ctx.fillStyle = fillHex;
        } else {
            const color = panel.is_color1 ? layer.color1 : layer.color2;
            this.ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
        }
        this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);

        if (layer.show_panel_borders) {
            this.ctx.strokeStyle = this.getLayerBorderColor(layer, 'power');
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2);
        }
    }
    
    renderCabinetIDNumbers(layer) {
        if (!layer.show_numbers) return;
        
        // Save context and clip to raster bounds
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        
        const numberSize = layer.number_size || 24;
        const cabinetIdStyle = layer.cabinetIdStyle || 'column-row';
        const cabinetIdPosition = layer.cabinetIdPosition || 'center';
        const cabinetIdColor = layer.cabinetIdColor || '#ffffff';
        
        this.ctx.fillStyle = cabinetIdColor;
        this.ctx.font = `bold ${numberSize}px Arial`;
        
        // Position-based settings
        if (cabinetIdPosition === 'center') {
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
        } else {
            // top-left
            this.ctx.textAlign = 'left';
            this.ctx.textBaseline = 'top';
        }
        
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            if (panel.x >= this.rasterWidth || panel.y >= this.rasterHeight) return;
            
            // Calculate label based on style
            let label = '';
            const col = panel.col;  // 0-indexed
            const row = panel.row;  // 0-indexed
            
            switch (cabinetIdStyle) {
                case 'column-row':
                    // A1, B1, C1... (column letter + row number)
                    // Reads top-to-bottom by columns
                    label = this.getColumnLetter(col) + (row + 1);
                    break;
                    
                case 'row-column':
                    // A1, A2, A3... (row letter + column number)
                    // Reads left-to-right by rows
                    label = this.getColumnLetter(row) + (col + 1);
                    break;
                    
                case 'row-col':
                    // 1,1  1,2  1,3... (row number, column number)
                    // Reads left-to-right with comma notation
                    label = `${row + 1},${col + 1}`;
                    break;
                    
                default:
                    label = panel.number; // Fallback to sequential
            }
            
            // Calculate position
            let textX, textY;
            if (cabinetIdPosition === 'center') {
                textX = panel.x + panel.width / 2;
                textY = panel.y + panel.height / 2;
            } else {
                // top-left with small padding
                textX = panel.x + 5;
                textY = panel.y + 5;
            }
            
            this.ctx.fillText(label, this.snap(textX), this.snap(textY));
        });
        
        this.ctx.restore();
    }
    
    // Helper function to convert number to letter (0=A, 1=B, ... 25=Z, 26=AA, etc.)
    getColumnLetter(num) {
        let letter = '';
        while (num >= 0) {
            letter = String.fromCharCode(65 + (num % 26)) + letter;
            num = Math.floor(num / 26) - 1;
        }
        return letter;
    }
    
    renderLayerLabels(layer) {
        if ((layer.type || 'screen') === 'image') {
            return;
        }
        // Note: Clipping for layer occlusion is handled in the render() second pass
        // We only clip to raster bounds here, which intersects with the occlusion clip
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        
        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        const centerX = bounds.x + layerWidth / 2;
        const centerY = bounds.y + layerHeight / 2;
        const bottomY = bounds.y + layerHeight;
        
        // Calculate physical dimensions
        const widthMM = (layer.panel_width_mm || 500) * (layerWidth / (layer.cabinet_width || 1));
        const heightMM = (layer.panel_height_mm || 500) * (layerHeight / (layer.cabinet_height || 1));
        const widthM = widthMM / 1000;
        const heightM = heightMM / 1000;
        const widthFt = widthM * 3.28084;
        const heightFt = heightM * 3.28084;
        
        const activePanels = layer.panels.filter(p => !p.blank && !p.hidden).length;
        const equivalentPanels = layer.panels
            .filter(p => !p.blank && !p.hidden)
            .reduce((sum, p) => {
                if (window.app && typeof window.app.getPanelLoadFactor === 'function') {
                    return sum + window.app.getPanelLoadFactor(layer, p);
                }
                return sum + 1;
            }, 0);
        const panelWeightValue = layer.panel_weight || 20;
        const panelWeightUnit = layer.weight_unit || 'kg';
        const panelWeightKg = panelWeightUnit === 'lb' ? (panelWeightValue / 2.20462) : panelWeightValue;
        const totalWeightKg = equivalentPanels * panelWeightKg;
        const totalWeightLb = totalWeightKg * 2.20462;
        
        // Build labels - Screen Name is separate with white background
        // Per-tab showLabelName: each view mode has its own property, falling back to global → true
        let showLabelName;
        if (this.viewMode === 'cabinet-id') {
            showLabelName = layer.showLabelNameCabinet !== undefined ? layer.showLabelNameCabinet
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else if (this.viewMode === 'data-flow') {
            showLabelName = layer.showLabelNameDataFlow !== undefined ? layer.showLabelNameDataFlow
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else if (this.viewMode === 'power') {
            showLabelName = layer.showLabelNamePower !== undefined ? layer.showLabelNamePower
                : (layer.showLabelName !== undefined ? layer.showLabelName : true);
        } else {
            showLabelName = layer.showLabelName !== undefined ? layer.showLabelName : true;
        }
        const screenName = showLabelName ? layer.name : null;
        
        // Other center labels (regular style)
        const centerLines = [];
        
        // Other labels only in pixel-map mode
        if (this.viewMode === 'pixel-map') {
            if (layer.showLabelSizePx) {
                centerLines.push(`W ${layerWidth} X H ${layerHeight}`);
            }
            if (layer.showLabelSizeM) {
                centerLines.push(`W ${widthM.toFixed(2)}(m) X H ${heightM.toFixed(2)}(m)`);
            }
            if (layer.showLabelSizeFt) {
                const useFractional = layer.useFractionalInches || false;
                
                if (useFractional) {
                    // FRACTIONAL MODE: e.g., 2' 2 7/8"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    const widthInWhole = Math.floor(widthInchesDecimal);
                    const widthInRemainder = widthInchesDecimal - widthInWhole;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    const heightInWhole = Math.floor(heightInchesDecimal);
                    const heightInRemainder = heightInchesDecimal - heightInWhole;
                    
                    // Convert decimal to fraction (1/16ths precision)
                    const toFraction = (decimal) => {
                        if (decimal < 0.03125) return ''; // Less than 1/16
                        const sixteenths = Math.round(decimal * 16);
                        // Simplify common fractions
                        if (sixteenths === 16) return '1'; // Whole inch
                        if (sixteenths === 8) return ' 1/2';
                        if (sixteenths === 4) return ' 1/4';
                        if (sixteenths === 12) return ' 3/4';
                        if (sixteenths === 2) return ' 1/8';
                        if (sixteenths === 6) return ' 3/8';
                        if (sixteenths === 10) return ' 5/8';
                        if (sixteenths === 14) return ' 7/8';
                        return ` ${sixteenths}/16`;
                    };
                    
                    const widthFrac = toFraction(widthInRemainder);
                    const heightFrac = toFraction(heightInRemainder);
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInWhole}${widthFrac}" X H ${heightFtTotal}' ${heightInWhole}${heightFrac}"`);
                } else {
                    // DECIMAL MODE: e.g., 2' 2.5"
                    const widthFtTotal = Math.floor(widthFt);
                    const widthInchesDecimal = (widthFt - widthFtTotal) * 12;
                    
                    const heightFtTotal = Math.floor(heightFt);
                    const heightInchesDecimal = (heightFt - heightFtTotal) * 12;
                    
                    centerLines.push(`W ${widthFtTotal}' ${widthInchesDecimal.toFixed(1)}" X H ${heightFtTotal}' ${heightInchesDecimal.toFixed(1)}"`);
                }
            }
            if (layer.showLabelWeight) {
                centerLines.push(`Weight ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
            }
        } else if (this.viewMode === 'data-flow') {
            if (layer.showDataFlowPortInfo) {
                let portsRequired = layer._portsRequired || 0;
                // Fallback: recalculate if not yet computed (e.g. right after file load)
                if (portsRequired <= 0 && window.app && typeof window.app.calculatePortAssignments === 'function') {
                    const assignments = window.app.calculatePortAssignments(layer);
                    if (Array.isArray(assignments)) {
                        portsRequired = assignments.reduce((max, a) => Math.max(max, a.port || 0), 0);
                    }
                    if (portsRequired <= 0 && layer._autoPortsRequired) {
                        portsRequired = layer._autoPortsRequired;
                    }
                }
                if (portsRequired > 0) {
                    const mains = portsRequired;
                    const backups = portsRequired;
                    centerLines.push(`${mains} Mains, ${backups} Backups | ${mains + backups} Ports`);
                }
            }
        } else if (this.viewMode === 'power') {
            if (layer.showPowerCircuitInfo) {
                let circuits = Number(layer._powerCircuitsRequired) || 0;
                if (circuits <= 0 && Array.isArray(layer._powerCircuits)) {
                    circuits = layer._powerCircuits.filter(c => Array.isArray(c) && c.length > 0).length;
                }
                if (circuits <= 0 && window.app && typeof window.app.calculatePowerAssignments === 'function') {
                    const assignments = window.app.calculatePowerAssignments(layer);
                    if (!assignments.error && Array.isArray(assignments.circuits)) {
                        circuits = assignments.circuits.filter(c => Array.isArray(c) && c.length > 0).length;
                    }
                }
                const voltage = parseFloat(layer.powerVoltage) || 0;
                const panelWatts = parseFloat(layer.panelWatts) || 0;
                const equivalentPanels = Array.isArray(layer.panels)
                    ? layer.panels
                        .filter(p => !p.hidden)
                        .reduce((sum, p) => {
                            if (window.app && typeof window.app.getPanelLoadFactor === 'function') {
                                return sum + window.app.getPanelLoadFactor(layer, p);
                            }
                            return sum + 1;
                        }, 0)
                    : 0;
                const totalWatts = panelWatts * equivalentPanels;
                const amps1 = voltage > 0 ? (totalWatts / voltage) : (Number(layer._powerTotalAmps1) || 0);
                const amps3 = voltage > 0 ? (totalWatts / (voltage * 1.73)) : (Number(layer._powerTotalAmps3) || 0);
                const multis = circuits > 0 ? Math.ceil(circuits / 6) : 0;
                centerLines.push(`${multis} Multi, ${circuits} Circuits | ${amps1.toFixed(2)}A 1φ / ${amps3.toFixed(2)}A 3φ`);
            }
        }
        
        // Build Info label text (separate, at bottom) - only in pixel-map mode
        // Single row format for compact display
        const infoLines = [];
        if (this.viewMode === 'pixel-map' && layer.showLabelInfo) {
            // Calculate aspect ratio
            const aspectRatio = layerWidth / layerHeight;
            const aspectRatioStr = `${aspectRatio.toFixed(2)}`;
            
            infoLines.push(`${layer.columns} Columns X ${layer.rows} Rows • ${activePanels} Cabinets Total / Resolution: ${layerWidth} X ${layerHeight} • Aspect Ratio: ${aspectRatioStr} • Weight: ${totalWeightKg.toFixed(1)} kg / ${totalWeightLb.toFixed(1)} lb`);
        }
        
        // Use absolute pixel sizes - no scaling with zoom
        let fontSize = layer.labelsFontSize || 30;
        const lineHeight = fontSize + 4;
        const padding = 6;
        
        // Info label uses independent slider value
        const infoFontSize = layer.infoLabelSize || 14;
        const infoLineHeight = infoFontSize + 4;
        
        // Screen name uses tab-specific size and position settings
        let screenNameSize = fontSize; // Default for pixel-map
        let screenNameOffsetX = 0;
        let screenNameOffsetY = 0;
        
        if (this.viewMode === 'cabinet-id') {
            screenNameSize = layer.screenNameSizeCabinet || 14;
            screenNameOffsetX = layer.screenNameOffsetXCabinet || 0;
            screenNameOffsetY = layer.screenNameOffsetYCabinet || 0;
        } else if (this.viewMode === 'data-flow') {
            screenNameSize = layer.screenNameSizeDataFlow || 14;
            screenNameOffsetX = layer.screenNameOffsetXDataFlow || 0;
            screenNameOffsetY = layer.screenNameOffsetYDataFlow || 0;
            fontSize = screenNameSize;
        } else if (this.viewMode === 'power') {
            screenNameSize = layer.screenNameSizePower || 14;
            screenNameOffsetX = layer.screenNameOffsetXPower || 0;
            screenNameOffsetY = layer.screenNameOffsetYPower || 0;
            fontSize = screenNameSize;
        }
        
        const screenNameLineHeight = screenNameSize + 4;
        
        this.ctx.font = `bold ${fontSize}px Arial`;
        
        // Calculate total height of ALL center labels (screen name + other labels)
        let totalCenterHeight = 0;
        let screenNameHeight = 0;
        
        if (screenName) {
            screenNameHeight = screenNameLineHeight + padding * 2;
            totalCenterHeight += screenNameHeight;
            if (centerLines.length > 0) {
                totalCenterHeight += 5; // Gap between screen name and other labels
            }
        }
        
        if (centerLines.length > 0 && this.viewMode === 'pixel-map') {
            totalCenterHeight += centerLines.length * lineHeight + padding * 2;
        }
        
        // Start Y position so that ALL labels are centered vertically
        let currentY = centerY - totalCenterHeight / 2;
        

        
        // Render Screen Name with WHITE background and BLACK text
        let infoAnchorY = null;
        if (screenName) {
            // For non-pixel-map modes, use tab-specific offset position
            let screenNameX = centerX;
            let screenNameY = centerY;
            
            if (this.viewMode !== 'pixel-map') {
                // Apply tab-specific screen name offset (relative to center)
                screenNameX = centerX + screenNameOffsetX;
                screenNameY = centerY + screenNameOffsetY;
                
                // If offset pushes label outside layer bounds, reset to center
                if (screenNameX < bounds.x || screenNameX > bounds.x + layerWidth) {
                    screenNameX = centerX;
                }
                if (screenNameY < bounds.y || screenNameY > bounds.y + layerHeight) {
                    screenNameY = centerY;
                }
            } else {
                // Pixel map mode - keep original center position
                screenNameY = currentY + screenNameHeight / 2;
            }
            
            this.ctx.font = `bold ${screenNameSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            
            const metrics = this.ctx.measureText(screenName);
            const nameWidth = metrics.width + padding * 2;
            const nameHeight = screenNameLineHeight + padding * 2;
            
            const nameX = screenNameX - nameWidth / 2;
            const nameY = screenNameY - nameHeight / 2;
            
            // Clip to layer bounds so labels don't overflow the screen edge
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw WHITE background
            this.ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
            const snappedNameRect = this.snapRect(nameX, nameY, nameWidth, nameHeight);
            this.ctx.fillRect(snappedNameRect.x, snappedNameRect.y, snappedNameRect.width, snappedNameRect.height);

            // Draw BLACK text
            this.ctx.fillStyle = '#000000';
            this.ctx.fillText(screenName, this.snap(screenNameX), this.snap(screenNameY));

            this.ctx.restore();
            
            // Reset font for other labels
            this.ctx.font = `bold ${fontSize}px Arial`;
            if (this.viewMode === 'pixel-map') {
                currentY += screenNameHeight;
                if (centerLines.length > 0) {
                    currentY += 5; // Gap before other labels
                }
            } else {
                infoAnchorY = nameY + nameHeight + 5;
            }
        }
        
        // Render other center labels with dark background (regular style)
        if (centerLines.length > 0) {
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            
            // Measure text for background
            let maxWidth = 0;
            centerLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });
            
            const bgWidth = maxWidth + padding * 2;
            const bgHeight = centerLines.length * lineHeight + padding * 2;
            const bgX = centerX - bgWidth / 2;
            const bgY = this.viewMode === 'pixel-map' ? currentY : (infoAnchorY ?? currentY);
            
            // Clip to layer bounds so labels don't bleed through higher layers
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(bounds.x, bounds.y, layerWidth, layerHeight);
            this.ctx.clip();

            // Draw dark background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedBgRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedBgRect.x, snappedBgRect.y, snappedBgRect.width, snappedBgRect.height);

            // Draw white text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            let yPos = bgY + padding + lineHeight / 2;
            centerLines.forEach(line => {
                this.ctx.fillText(line, this.snap(centerX), this.snap(yPos));
                yPos += lineHeight;
            });

            this.ctx.restore();
        }
        
        // Render Info label at bottom with background (fixed 14px screen size)
        if (infoLines.length > 0) {
            // Use world coordinates directly (transform is already applied)
            this.ctx.font = `${infoFontSize}px Arial`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';
            
            // Measure text for background
            let maxWidth = 0;
            infoLines.forEach(line => {
                const metrics = this.ctx.measureText(line);
                maxWidth = Math.max(maxWidth, metrics.width);
            });
            
            const bgWidth = maxWidth + padding * 2;
            const bgHeight = infoLines.length * infoLineHeight + padding * 2;
            const bgX = centerX - bgWidth / 2;
            const bgY = bottomY - bgHeight - padding;
            
            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedInfoRect = this.snapRect(bgX, bgY, bgWidth, bgHeight);
            this.ctx.fillRect(snappedInfoRect.x, snappedInfoRect.y, snappedInfoRect.width, snappedInfoRect.height);

            // Draw text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            let yPos = bgY + padding + infoLineHeight;
            infoLines.forEach(line => {
                this.ctx.fillText(line, this.snap(centerX), this.snap(yPos));
                yPos += infoLineHeight;
            });
        }
        
        // Restore context (remove clipping)
        this.ctx.restore();
    }
    
    renderLayerOffsets(layer) {
        // Only render offsets in pixel-map mode
        if (this.viewMode !== 'pixel-map') {
            return;
        }
        
        if (!layer.showOffsetTL && !layer.showOffsetTR && !layer.showOffsetBL && !layer.showOffsetBR) {
            return;
        }
        
        // Save context and clip to raster bounds
        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();
        
        const bounds = this.getLayerBounds(layer);
        const layerWidth = bounds.width;
        const layerHeight = bounds.height;
        
        // Calculate actual corner positions
        // Since pixels are zero-indexed:
        // - Top-left starts at offset_x, offset_y (e.g., 0, 0)
        // - Top-right is at offset_x + width - 1 (e.g., 0 + 1024 - 1 = 1023)
        // - Bottom-left is at offset_y + height - 1 (e.g., 0 + 640 - 1 = 639)
        // - Bottom-right is at both -1 (e.g., 1023, 639)
        const tlX = bounds.x;
        const tlY = bounds.y;
        const trX = bounds.x + layerWidth - 1;  // Account for zero-indexing
        const trY = bounds.y;
        const blX = bounds.x;
        const blY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        const brX = bounds.x + layerWidth - 1;   // Account for zero-indexing
        const brY = bounds.y + layerHeight - 1;  // Account for zero-indexing
        
        const corners = [
            { x: tlX, y: tlY, text: `X ${tlX}, Y ${tlY}`, show: layer.showOffsetTL, align: 'left', baseline: 'top', offsetX: 5, offsetY: 5 },
            { x: trX, y: trY, text: `X ${trX}, Y ${trY}`, show: layer.showOffsetTR, align: 'right', baseline: 'top', offsetX: -5, offsetY: 5 },
            { x: blX, y: blY, text: `X ${blX}, Y ${blY}`, show: layer.showOffsetBL, align: 'left', baseline: 'bottom', offsetX: 5, offsetY: -5 },
            { x: brX, y: brY, text: `X ${brX}, Y ${brY}`, show: layer.showOffsetBR, align: 'right', baseline: 'bottom', offsetX: -5, offsetY: -5 }
        ];
        
        // Use absolute pixel sizes - no scaling with zoom
        const fontSize = layer.labelsFontSize || 30;
        const padding = 4;
        
        this.ctx.font = `${fontSize}px Arial`;
        
        corners.forEach(corner => {
            if (!corner.show) return;
            
            // Skip if corner is outside raster bounds
            if (corner.x < 0 || corner.x >= this.rasterWidth || corner.y < 0 || corner.y >= this.rasterHeight) {
                return;
            }
            
            // Use world coordinates directly (transform is already applied)
            const worldX = corner.x + corner.offsetX;
            const worldY = corner.y + corner.offsetY;
            
            // Measure text for background
            const metrics = this.ctx.measureText(corner.text);
            const textWidth = metrics.width;
            const textHeight = fontSize;
            
            let bgX, bgY;
            if (corner.align === 'left') {
                bgX = worldX;
            } else {
                bgX = worldX - textWidth - padding * 2;
            }
            
            if (corner.baseline === 'top') {
                bgY = worldY;
            } else {
                bgY = worldY - textHeight - padding * 2;
            }
            
            // Draw background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const snappedCornerRect = this.snapRect(bgX, bgY, textWidth + padding * 2, textHeight + padding * 2);
            this.ctx.fillRect(snappedCornerRect.x, snappedCornerRect.y, snappedCornerRect.width, snappedCornerRect.height);
            
            // Draw text
            this.ctx.fillStyle = layer.labelsColor || '#ffffff';
            this.ctx.textAlign = corner.align;
            this.ctx.textBaseline = corner.baseline;
            
            const textX = corner.align === 'left' ? worldX + padding : worldX - padding;
            const textY = corner.baseline === 'top' ? worldY + padding : worldY - padding;
            
            this.ctx.fillText(corner.text, this.snap(textX), this.snap(textY));
        });
        
        this.ctx.restore();
    }

    renderCustomSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlow(layer)) return;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();

        const selection = window.app.customSelection || new Set();
        if (selection.size > 0) {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            selection.forEach(key => {
                const [row, col] = key.split(',').map(n => parseInt(n, 10));
                const panel = window.app.getPanelByRowCol(layer, row, col);
                if (!panel) return;
                this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            });
        }

        // No selection rectangle preview (per UX request)

        this.ctx.restore();
    }

    renderPowerSelectionOverlay() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPower(layer)) return;

        this.ctx.save();
        this.ctx.beginPath();
        this.ctx.rect(0, 0, this.rasterWidth, this.rasterHeight);
        this.ctx.clip();

        const selection = window.app.powerCustomSelection || new Set();
        if (selection.size > 0) {
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            selection.forEach(key => {
                const [row, col] = key.split(',').map(n => parseInt(n, 10));
                const panel = window.app.getPanelByRowCol(layer, row, col);
                if (!panel) return;
                this.ctx.fillRect(panel.x, panel.y, panel.width, panel.height);
            });
        }

        this.ctx.restore();
    }

    renderCustomActivePortBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomFlow(layer)) return;
        const portNum = layer.customPortIndex || 1;
        const label = window.app.getPortLabelText(layer, portNum, 'primary');

        this.ctx.save();
        // Draw in screen space (top-left of canvas)
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);

        const x = 20;
        const y = 20;
        const fontSize = 72;
        this.ctx.font = `bold ${fontSize}px Arial`;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        const padding = 12;
        const metrics = this.ctx.measureText(label);
        const boxW = metrics.width + padding * 2;
        const boxH = fontSize + padding * 2;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
        this.ctx.fillRect(x, y, boxW, boxH);

        this.ctx.fillStyle = 'rgba(0, 255, 0, 0.9)';
        this.ctx.fillText(label, x + padding, y + padding);
        this.ctx.restore();
    }

    renderPowerActiveCircuitBadge() {
        if (!window.app || !window.app.currentLayer) return;
        const layer = window.app.currentLayer;
        if (!window.app.isCustomPower(layer)) return;
        const circuitNum = layer.powerCustomIndex || 1;
        const label = window.app.getPowerCircuitLabel(layer, circuitNum);

        this.ctx.save();
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);

        const x = 20;
        const y = 20;
        const fontSize = 72;
        this.ctx.font = `bold ${fontSize}px Arial`;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        const padding = 12;
        const metrics = this.ctx.measureText(label);
        const boxW = metrics.width + padding * 2;
        const boxH = fontSize + padding * 2;

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
        this.ctx.fillRect(x, y, boxW, boxH);

        this.ctx.fillStyle = 'rgba(0, 255, 102, 0.9)';
        this.ctx.fillText(label, x + padding, y + padding);
        this.ctx.restore();
    }
}

window.CanvasRenderer = CanvasRenderer;
