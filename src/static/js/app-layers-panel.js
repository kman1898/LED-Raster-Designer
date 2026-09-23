// app-layers-panel: the sidebar layer list for LEDRasterApp - renderLayers
// builds one row per screen (swatch, name edit, visibility, lock, drag
// handle) and then hands the flat list to the canvas and group regroupers.
import { LEDRasterApp } from './app-core.js';

class _LayersPanel {

    renderLayers() {
        
        const container = document.getElementById('layers-list');
        container.innerHTML = '';
        
        if (!this.project || !this.project.layers) {
            console.error('RENDER LAYERS ERROR: No project or no layers array!');
            return;
        }
        
        // Debug: Log all layer IDs to check for duplicates
        const layerIds = this.project.layers.map(l => l.id);
        const uniqueIds = [...new Set(layerIds)];
        if (layerIds.length !== uniqueIds.length) {
            console.error('RENDER LAYERS: DUPLICATE IDs DETECTED!', layerIds);
        }
        
        console.log('RENDER LAYERS: currentLayer.id =', this.currentLayer?.id, 'all ids =', layerIds);
        
        // Reverse the layers array for display - standard (newest on top)
        const reversedLayers = [...this.project.layers].reverse();
        this.layerListOrder = reversedLayers.map(l => l.id);
        
        reversedLayers.forEach(layer => {
            const layerDiv = document.createElement('div');
            layerDiv.className = 'layer-item';
            layerDiv.dataset.layerId = layer.id;
            layerDiv.draggable = true;
            if (this.selectedLayerIds && this.selectedLayerIds.has(layer.id)) {
                layerDiv.classList.add('active');
            }
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                layerDiv.classList.add('primary');
            }
            // v0.8.7.7.1: visually distinguish hidden layers in the sidebar.
            if (layer.visible === false) {
                layerDiv.classList.add('hidden');
            }
            
            const layerType = layer.type || 'screen';
            const isImage = layerType === 'image';
            const isText = layerType === 'text';
            const activePanels = (isImage || isText) ? 0 : layer.panels.filter(p => !p.blank && !p.hidden).length;

            let infoText;
            if (isText) {
                const preview = (layer.textContent || '').substring(0, 30);
                infoText = `Text • ${layer.fontSize || 24}px${preview ? ' • ' + preview : ''}`;
            } else if (isImage) {
                infoText = `${layer.imageWidth || 0}×${layer.imageHeight || 0}px • ${Math.round((layer.imageScale || 1) * 100)}%`;
            } else {
                infoText = `${layer.columns}x${layer.rows} (${activePanels} panels) • ${layer.cabinet_width}×${layer.cabinet_height}px`;
            }
            const lockBadge = layer.locked ? '<span title="Locked" style="margin-left: 6px; color:#bbb;">🔒</span>' : '';
            // Change cabinet… (2026-09-16), the button left of the eye on a
            // screen row: a cabinet outline, the same .layer-btn size and
            // hover as the eye. An image or text row has no cabinet and no
            // button. It opens the preset picker in replace mode over THIS
            // row's screen (app-presets.js openChangeCabinet); the
            // right-click menu is the way to change several at once.
            const cabinetBtn = (isImage || isText) ? '' : `
                        <button class="layer-btn layer-cabinet-btn" data-layer-id="${layer.id}" title="Change cabinet…"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" style="display:block;"><rect x="1.5" y="1.5" width="11" height="11" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M7 1.5v11M1.5 7h11" fill="none" stroke="currentColor" stroke-width="1.4"/></svg></button>`;
            // v0.8 Slice 2.5: per-layer ▲▼ arrows replace the global Up/Down
            // buttons. Disabled state (top/bottom of the layer's canvas group)
            // is computed in updateLayerOrderControls() after the regroup pass
            // so we know the within-canvas ordering.
            layerDiv.innerHTML = `
                <div class="layer-header">
                    <div style="display:flex; align-items:center; gap:4px; flex:1; min-width:0;">
                        <input type="text" class="layer-name-input" data-layer-id="${layer.id}" value="${layer.name}" style="background: transparent; border: 1px solid transparent; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; flex:1; min-width:0;">
                        ${lockBadge}
                    </div>
                    <div class="layer-controls">
                        <div class="layer-arrows">
                            <button class="layer-btn layer-move-up" data-layer-id="${layer.id}" title="Move up within canvas">▲</button>
                            <button class="layer-btn layer-move-down" data-layer-id="${layer.id}" title="Move down within canvas">▼</button>
                        </div>
${cabinetBtn}
                        <button class="layer-btn layer-visibility-btn ${layer.visible === false ? 'is-hidden' : ''}" onclick="app.toggleLayerVisibility(${layer.id})" title="${layer.visible === false ? 'Hidden, click to show' : 'Visible, click to hide'}">
                            ${layer.visible === false ? '🚫' : '👁'}
                        </button>
                    </div>
                </div>
                <div class="layer-info">
                    ${layer.visible === false ? '<span class="layer-hidden-badge">HIDDEN</span> ' : ''}${infoText}
                </div>
            `;
            
            // Per-layer reorder arrows (Slice 2.5).
            const upArrow = layerDiv.querySelector('.layer-move-up');
            const downArrow = layerDiv.querySelector('.layer-move-down');
            if (upArrow) {
                upArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (upArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, -1);
                });
            }
            if (downArrow) {
                downArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (downArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, 1);
                });
            }

            // Change cabinet… on this row's screen alone. The click stops
            // here: the row's own click handler below reads e.target's
            // class, and a click landing on the glyph inside the button
            // would otherwise select the row as well.
            const cabinetButton = layerDiv.querySelector('.layer-cabinet-btn');
            if (cabinetButton) {
                cabinetButton.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.openChangeCabinet([layer]);
                });
            }

            // Single click to select. The name field fills the row header,
            // so a click on it is the click most people make on a row: it
            // selects like the rest of the row (plain, Cmd/Ctrl to add,
            // Shift to range). Two exclusions, both about the rename
            // (2026-09-23):
            //   - a name being EDITED: a double-click has put it in edit
            //     mode (readOnly off, below) and a click inside it places
            //     the caret; re-selecting would rebuild the list and drop
            //     the edit;
            //   - the SECOND click of a double-click on a name (e.detail
            //     2): the first click selected the row and rebuilt the
            //     list, and the dblclick is dispatched to the field that
            //     took this second click - rebuild again here and it goes
            //     to a detached node, so the rename never opens.
            layerDiv.addEventListener('click', (e) => {
                const onName = e.target.classList.contains('layer-name-input');
                if (onName && (!e.target.readOnly || e.detail >= 2)) return;
                if (!e.target.classList.contains('layer-btn')) {
                    const isToggle = e.metaKey || e.ctrlKey;
                    const isRange = e.shiftKey;
                    if (isRange) {
                        this.selectLayerRange(layer);
                    } else if (isToggle) {
                        this.toggleLayerSelection(layer);
                    } else {
                        this.selectLayer(layer);
                    }
                }
            });

            // Right-click context menu on layer list. A row already in the
            // selection keeps the selection (the canvas's rule, so "Put on
            // beach" over one of three selected rows means all three); a
            // row outside it becomes the selection first.
            layerDiv.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isToggle = e.metaKey || e.ctrlKey;
                const inSelection = !!(this.selectedLayerIds
                    && this.selectedLayerIds.size > 0
                    && this.selectedLayerIds.has(layer.id));
                if (isToggle) {
                    this.toggleLayerSelection(layer);
                } else if (!inSelection) {
                    this.selectLayer(layer);
                }
                this.showContextMenu(e.clientX, e.clientY);
            });

            const handleDragStart = (e) => {
                e.dataTransfer.setData('text/plain', String(layer.id));
                e.dataTransfer.effectAllowed = 'move';
                this.dragLayerId = layer.id;
            };
            layerDiv.addEventListener('dragstart', handleDragStart);
            const headerEl = layerDiv.querySelector('.layer-header');
            const infoEl = layerDiv.querySelector('.layer-info');
            if (headerEl) {
                headerEl.draggable = true;
                headerEl.addEventListener('dragstart', handleDragStart);
            }
            if (infoEl) {
                infoEl.draggable = true;
                infoEl.addEventListener('dragstart', handleDragStart);
            }
            layerDiv.addEventListener('dragover', (e) => {
                e.preventDefault();
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const position = e.clientY < midpoint ? 'top' : 'bottom';
                layerDiv.classList.toggle('drag-over-top', position === 'top');
                layerDiv.classList.toggle('drag-over-bottom', position === 'bottom');
                layerDiv.classList.add('drag-over');
                this.dragOverPosition = position;
            });
            layerDiv.addEventListener('dragleave', () => {
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
            });
            layerDiv.addEventListener('drop', (e) => {
                e.preventDefault();
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
                const draggedId = this.dragLayerId || parseInt(e.dataTransfer.getData('text/plain'), 10);
                const targetId = layer.id;
                if (!draggedId || draggedId === targetId) return;
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const insertAfter = e.clientY >= midpoint;
                this.reorderLayersByDrag(draggedId, targetId, insertAfter);
            });
            
            // Handle name input: single-click selects layer (the row's click
            // handler above, since a read-only name is part of the row),
            // double-click edits name. The first click of the double-click
            // selects and rebuilds the list, the second is left alone, and
            // the dblclick lands on the rebuilt field for this same screen
            // and opens the edit.
            const nameInput = layerDiv.querySelector('.layer-name-input');
            nameInput.readOnly = true;
            nameInput.draggable = true;
            nameInput.style.cursor = 'default';
            nameInput.addEventListener('dragstart', handleDragStart);

            const enterEditMode = () => {
                nameInput.readOnly = false;
                nameInput.draggable = false;
                nameInput.style.cursor = 'text';
                // v0.11.0: class, not inline - theme.css styles .layer-name-input
                // with !important, so an inline border/background never painted.
                nameInput.classList.add('editing');
                nameInput.focus();
                nameInput.select();
            };

            const exitEditMode = () => {
                nameInput.readOnly = true;
                nameInput.draggable = true;
                nameInput.style.cursor = 'default';
                nameInput.classList.remove('editing');
                const newName = nameInput.value.trim() || layer.name;
                if (newName !== layer.name) {
                    layer.name = newName;
                    // _putLayer: a rename is a hand on the screen (the
                    // `edited` marker rides the PUT).
                    this._putLayer(layer.id, { name: newName });
                    // Record the rename so it's undoable on its own; without
                    // this the local name change rode along on the next action
                    // and a later undo restored a stale name (client/server
                    // desync). The renameLayer() path already does this.
                    this.saveState('Rename Layer');
                }
            };

            nameInput.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                enterEditMode();
            });
            nameInput.addEventListener('blur', exitEditMode);
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    nameInput.blur();
                } else if (e.key === 'Escape' && !nameInput.readOnly) {
                    // Drop the typing and end the edit, as the canvas name
                    // field does (app-canvas-ui.js).
                    nameInput.value = layer.name;
                    nameInput.blur();
                }
                if (!nameInput.readOnly) e.stopPropagation();
            });
            
            container.appendChild(layerDiv);
        });

        // v0.8 Slice 2: regroup the flat layer list by canvas. The existing
        // layer items above are preserved as-is, we just lift them into
        // per-canvas group containers and add canvas headers + per-canvas
        // "+ Add Screen" buttons + cross-canvas drag/drop.
        this.regroupLayersByCanvas(container);

        // v0.11.0: then nest each screen group's member rows under a group
        // header, INSIDE the canvas group they already sit in. Runs after the
        // canvas pass because it lifts the rows that pass has just placed.
        this.regroupLayersByGroup(container);

        this.updateLayerOrderControls();
        // Beaches (2026-09-08): the BEACHES line under the canvases follows
        // every list rebuild - load, undo, a beach route's adoption.
        if (typeof this.renderBeaches === 'function') this.renderBeaches();
    }

    // -------------------------------------------------------------------
    // Multi-canvas (v0.8 Slice 2), sidebar canvas grouping.
    //
    // Slice 2 keeps workspace rendering unchanged; the sidebar restructure
    // is the entire visible deliverable. Each canvas gets a header row
    // (color swatch / name / 👁 / ⋮ / drag handle), its layers underneath
    // (filtered by layer.canvas_id), and a per-canvas "+ Add Screen"
    // button. A canvas drag handle reorders canvases. Layers can be
    // dragged onto another group's header to move them cross-canvas
    // (Cmd/Alt = duplicate).
    // -------------------------------------------------------------------
}

for (const k of Object.getOwnPropertyNames(_LayersPanel.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_LayersPanel.prototype, k));
    }
}
