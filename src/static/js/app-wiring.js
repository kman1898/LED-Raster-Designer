// app-wiring: the DOM event wiring for LEDRasterApp's sidebars, toolbar
// and export modal - the body of what was one 2,000-line
// setupEventListeners in app-core.js, cut into one _wire* method per
// area of the page. Each method is a verbatim, contiguous slice of the
// old body and setupEventListeners (app-core.js) calls them in the old
// order, so every listener registers in exactly the sequence it always
// did. Nothing here is shared between blocks: every handle and closure
// a block uses is declared inside it.
import { LEDRasterApp } from './app-core.js';
import { evaluateMathExpression, sendClientLog, setupColorPickerWithHex } from './helpers.js';

class _Wiring {
    // Project name field (and its illegal-character warning), the Project
    // Notes textarea and the Notes / Help panel collapse toggles.
    _wireProjectChrome() {
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

    }

    // A pattern tile applied to a selection hands the keyboard back to the
    // canvas. Chrome keeps focus on a button after a mouse click (Safari
    // does not), and canvas-input's Tab shortcut yields to a focused
    // control - so in Chrome "select, press serpentine, press Tab" walked
    // the pattern tiles instead of stepping to the next circuit, while the
    // same gesture in Safari stepped (user, 2026-09-22: "it is tabbing the
    // serpentine not the circuits"). Only a MOUSE click drops the focus
    // (e.detail is 0 for Enter / Space on a focused tile): a keyboard user
    // who tabbed to the tile keeps their place. The Next / Prev buttons
    // keep theirs on purpose - see the 2026-09-03 ruling in canvas-input.
    //
    // The four Clear buttons take the same treatment (found by an
    // end-to-end pass, 2026-09-23): after a mouse click on Clear Circuit /
    // Clear All (power) or Clear Port / Clear All (data), Tab walked from
    // one Clear button to the next instead of stepping the run. A Clear
    // drops its focus even when it cleared nothing - the user's next
    // gesture is the same either way.
    _dropPatternTileFocus(btn, e) {
        if (!btn || !e || !e.detail) return;
        if (document.activeElement === btn && typeof btn.blur === 'function') btn.blur();
    }

    // The five view tabs: switch the renderer, swap the sidebar panels,
    // and refresh whichever panel the new view owns.
    _wireViewTabs() {
        // View tabs - the top strip's only. The Preferences dialog's tab
        // strip reuses the .view-tab class (data-key, no data-mode) and has
        // its own handler (app-preferences showPreferencesTab); binding it
        // here called setViewMode(undefined), which hid the hardware dock
        // and every sidebar panel until a top view button was clicked.
        const viewTabs = () => document.querySelectorAll('#view-tabs .view-tab[data-mode]');
        viewTabs().forEach(tab => {
            tab.addEventListener('click', () => {
                const mode = tab.getAttribute('data-mode');
                // The patch bay opens over the workspace from Data Settings;
                // switching to any view closes it and shows that view.
                if (this.closePatchBay) this.closePatchBay();
                viewTabs().forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Show/hide appropriate sidebar panels
                document.querySelectorAll('.tab-panel').forEach(panel => {
                    if (panel.getAttribute('data-tab') === mode) {
                        panel.style.display = 'block';
                    } else {
                        panel.style.display = 'none';
                    }
                });
                
                window.canvasRenderer.setViewMode(mode);
                // The Signal and Power panels each belong to one view, so they
                // join or leave layout with the tab, not with the selection.
                this.updateViewSidebars(mode);
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

    }

    // + Canvas, Save Preset (and the preset modals), the image file input
    // and Replace Image, the text-layer controls, and Lock Selected.
    _wireLayerToolbar() {
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
        
    }

    // Zoom in / out / fit / actual, the typed zoom percentage, and the
    // magnetic-snap checkbox.
    _wireCanvasControls() {
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
        
    }

    // Screen Info: the numeric geometry inputs, the Show Look resets,
    // Image Scale, Drop Shadow, Show Numbers and the weight unit.
    _wireScreenInfo() {
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
                        // Undo audit: skipHistory, or every touched canvas's
                        // PUT recorded its own async entry on top of the one
                        // below - one click cost 2..N+1 Ctrl+Z presses.
                        this.updateCanvas(cid, patch, { skipHistory: true });
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
                        // Undo audit: same skipHistory as the single reset
                        // above - one click, one entry.
                        this.updateCanvas(c.id, patch, { skipHistory: true });
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

        // Opacity (image layers). Same shape as Image Scale: the slider's
        // `input` mutates the layer and re-renders as it moves, `change`
        // pushes to the server and records ONE history entry, debounced.
        const imageOpacityRange = document.getElementById('image-opacity-range');
        const imageOpacityValue = document.getElementById('image-opacity-value');
        if (imageOpacityRange) {
            const readOpacity = () => {
                const n = Math.round(parseFloat(imageOpacityRange.value));
                if (Number.isNaN(n)) return 100;
                return Math.max(0, Math.min(100, n));
            };
            const imageTargets = () => (this.getSelectedLayers ? this.getSelectedLayers() : [])
                .filter(l => (l.type || 'screen') === 'image');
            const applyLiveOpacity = () => {
                const pct = readOpacity();
                if (imageOpacityValue) imageOpacityValue.textContent = `${pct}%`;
                const targets = imageTargets();
                if (targets.length === 0) return;
                targets.forEach(l => { l.imageOpacity = pct; });
                window.canvasRenderer.render();
            };
            imageOpacityRange.addEventListener('input', applyLiveOpacity);
            imageOpacityRange.addEventListener('change', () => {
                applyLiveOpacity();
                const targets = imageTargets();
                if (targets.length === 0) return;
                this.updateLayers(targets);
                this.debouncedSaveState('Change Image Opacity');
            });
        }

        // Drop Shadow (image layers). Same shape as the Image Scale wiring
        // above: mutate the layer, re-render live, then push to the server and
        // record one history entry on commit.
        const applyImageShadow = (mutate, label, isFinal) => {
            const targets = (this.getSelectedLayers ? this.getSelectedLayers() : [])
                .filter(l => (l.type || 'screen') === 'image');
            if (targets.length === 0) return;
            targets.forEach(mutate);
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(targets);
                this.debouncedSaveState(label);
            }
        };
        const shadowEnabledCheck = document.getElementById('image-shadow-enabled');
        if (shadowEnabledCheck) {
            shadowEnabledCheck.addEventListener('change', () => {
                const on = shadowEnabledCheck.checked;
                applyImageShadow(l => {
                    l.imageShadowEnabled = on;
                    // First time on, stamp Photoshop's own defaults so the
                    // user sees a shadow immediately instead of nothing.
                    if (on) {
                        if (l.imageShadowColor == null) l.imageShadowColor = '#000000';
                        if (l.imageShadowOpacity == null) l.imageShadowOpacity = 75;
                        if (l.imageShadowAngle == null) l.imageShadowAngle = 120;
                        if (l.imageShadowDistance == null) l.imageShadowDistance = 10;
                        if (l.imageShadowSpread == null) l.imageShadowSpread = 0;
                        if (l.imageShadowSize == null) l.imageShadowSize = 10;
                    }
                }, 'Drop Shadow', true);
                this.loadLayerToInputs();
            });
        }
        setupColorPickerWithHex('image-shadow-color', 'image-shadow-color-hex', (val, isFinal) => {
            applyImageShadow(l => { l.imageShadowColor = val; }, 'Shadow Color', isFinal);
        });
        [
            ['image-shadow-opacity', 'imageShadowOpacity', 0, 100, 75, 'Shadow Opacity'],
            ['image-shadow-angle', 'imageShadowAngle', 0, 360, 120, 'Shadow Angle'],
            ['image-shadow-distance', 'imageShadowDistance', 0, 250, 10, 'Shadow Distance'],
            ['image-shadow-spread', 'imageShadowSpread', 0, 100, 0, 'Shadow Spread'],
            ['image-shadow-size', 'imageShadowSize', 0, 250, 10, 'Shadow Size'],
        ].forEach(([id, key, lo, hi, dflt, label]) => {
            const el = document.getElementById(id);
            if (!el) return;
            const read = () => {
                const n = parseFloat(el.value);
                if (Number.isNaN(n)) return dflt;
                return Math.max(lo, Math.min(hi, n));
            };
            el.addEventListener('input', () => {
                applyImageShadow(l => { l[key] = read(); }, label, false);
            });
            el.addEventListener('change', () => {
                const v = read();
                el.value = String(v);
                applyImageShadow(l => { l[key] = v; }, label, true);
            });
        });


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
        
    }

    // Cabinet ID style / position / colour, the per-tab border colours,
    // border width and visibility (mirrored across the four tabs), the
    // label / offset checkboxes, info label size and per-tab screen names.
    _wireLabelsAndBorders() {
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
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Cabinet ID Color', 400, 'cabinet-id-color');
            }
            window.canvasRenderer.render();
        });
        
        // Border settings (Pixel Map tab)
        //
        // #show-panel-borders is NOT wired here. It is one of the four
        // cross-tab border-visibility checkboxes wired further down (search
        // "Sync border visibility checkboxes across tabs"), and that handler
        // already mirrors the state to the other three tabs AND calls
        // updateLayerFromInputs(). A second listener here called
        // updateLayerFromInputs() as well, so one click pushed two identical
        // snapshots and the first Ctrl+Z appeared to do nothing.
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
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Border Color', 400, 'border-color');
            }
        });
        
        // Labels color with hex sync
        setupColorPickerWithHex('labels-color', 'labels-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => { layer.labelsColor = val; });
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Label Color', 400, 'labels-color');
            }
        });
        
        // Tab-specific border controls - Cabinet ID
        setupColorPickerWithHex('border-color-cabinet', 'border-color-cabinet-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_cabinet = val;
            });
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Border Color', 400, 'border-color-cabinet');
            }
        });
        
        // Tab-specific border controls - Data Flow
        setupColorPickerWithHex('border-color-data', 'border-color-data-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_data = val;
            });
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Border Color', 400, 'border-color-data');
            }
        });
        
        // Tab-specific border controls - Power
        setupColorPickerWithHex('border-color-power', 'border-color-power-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_power = val;
            });
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Border Color', 400, 'border-color-power');
            }
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

    }

    // Data Settings: processor / bit depth / frame rate / low latency,
    // route-group-as-one, port mapping mode, the flow-pattern tiles (data
    // AND power - the power tiles register here, in the original order),
    // arrow width / size, port label templates, custom flow editing and
    // random data colours.
    _wireDataPanel() {
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

        // v0.11.0: Low Latency mirrors the Processor Type handler above - same
        // capacity + port-label refresh, and a single updateLayers(..., true)
        // so the toggle records exactly ONE undo step.
        const lowLatencyCheckbox = document.getElementById('low-latency');
        if (lowLatencyCheckbox) {
            lowLatencyCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.lowLatency = lowLatencyCheckbox.checked;
                });
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Low Latency');
                window.canvasRenderer.render();
            });
        }

        // "Route <group> as one screen" (Data Settings). Unlike its
        // neighbours this writes the GROUP, not the selected layers, so it
        // goes through the group commit funnel - one history entry labelled
        // 'Toggle Group Data Routing', and the commit's own renderLayers /
        // loadLayerToInputs pass re-syncs the row. The row is only visible
        // while the shown screen belongs to a group (updateGroupRouteControl),
        // so the guard here is belt and braces.
        const routeGroupAsOneBox = document.getElementById('route-group-as-one');
        if (routeGroupAsOneBox) {
            routeGroupAsOneBox.addEventListener('change', () => {
                const group = this.currentLayer
                    ? this.getGroupOfLayer(this.currentLayer) : null;
                if (!group) return;
                this.toggleGroupRouteDataAsOne(group.id);
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
            
            // v0.11.0: highlight via the .active CLASS, not inline styles. The
            // theme's .mapping-mode-btn rules are !important, so inline
            // background/color writes were painted over and the highlight
            // never moved off Organized.
            if (mappingOrganizedBtn && mappingMaxCapBtn) {
                mappingOrganizedBtn.classList.toggle('active', mode === 'organized');
                mappingMaxCapBtn.classList.toggle('active', mode !== 'organized');
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
            btn.addEventListener('click', (e) => {
                const pattern = btn.getAttribute('data-pattern');
                // Editing predicate: with an overridden port open and a
                // selection made, the tile applies the pattern to the
                // selection exactly as it does in whole-screen custom -
                // falling through here would silently change the SCREEN's
                // flow pattern mid-edit.
                if (this.currentLayer && this.isCustomFlowEditing(this.currentLayer) && this.customSelection.size > 0) {
                    this.applyPatternToSelection(pattern);
                    this._dropPatternTileFocus(btn, e);
                    return;
                }
                
                // Remove active class from all buttons. v0.11.0: scope this to the
                // Data grid - the Power tiles carry BOTH classes, so an unscoped
                // selector cleared their highlight too (matching the listener
                // registration above and the Power grid's own handler).
                document.querySelectorAll('.flow-pattern-btn:not(.power-flow-pattern-btn)').forEach(b => b.classList.remove('active'));
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
            btn.addEventListener('click', (e) => {
                const pattern = btn.getAttribute('data-pattern');
                // Editing predicate - same reason as the data tiles above.
                if (this.currentLayer && this.isCustomPowerEditing(this.currentLayer) && this.powerCustomSelection.size > 0) {
                    this.applyPowerPatternToSelection(pattern);
                    this._dropPatternTileFocus(btn, e);
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

        // The per-port list died with the Signal panel, and its checkboxes
        // were the only selection there was - so Apply Style restyles the
        // WHOLE run now: every port the shown screen needs, in order. One
        // port is renamed on its chip in the hardware dock instead.
        const getSelectedPortNumbers = () => {
            const layer = this.currentLayer;
            if (!layer || (layer.type || 'screen') !== 'screen') return [];
            const count = layer._portsRequired
                || (typeof this.getLayerPortsRequired === 'function'
                    ? this.getLayerPortsRequired(layer) : 0) || 0;
            return Array.from({ length: count }, (_, i) => i + 1);
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
        // Routed through stepCustomPort so there is ONE stepping rule shared
        // with Tab and the brackets: it saves, PUTs (v0.8.2 - without that,
        // local mutations accumulate only on the client until some other PUT
        // contradicts them), and while an overridden port is open for
        // redrawing it walks the layer's override list instead of the open
        // number line.
        // Mouse controls that must not answer Enter/Space - see
        // _armStepButton (app-power.js) for the skipped-number trap.
        this._armStepButton(customPrevPortBtn);
        this._armStepButton(customNextPortBtn);
        if (customPrevPortBtn) {
            customPrevPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.stepCustomPort(-1);
            });
        }
        if (customNextPortBtn) {
            customNextPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.stepCustomPort(1);
            });
        }
        if (customClearPortBtn) {
            customClearPortBtn.addEventListener('click', (e) => {
                // Mouse click: hand the keyboard back to the canvas so the
                // Tab that follows steps the port - see _dropPatternTileFocus.
                this._dropPatternTileFocus(customClearPortBtn, e);
                if (!this.currentLayer) return;
                // No ensure* here: it wrote `{}` and 1 onto a screen with
                // nothing, and a Clear that clears nothing must change
                // nothing - no undo step, no PUT (touched is empty).
                const portNum = this.currentLayer.customPortIndex || 1;
                // This screen's port, and - whole - any peer's port of the
                // same number that lands here - see clearCustomRun.
                const { touched, skipped } = this.clearCustomRun(this.currentLayer, 'data', portNum);
                if (touched.length) {
                    this.saveState('Custom Clear Port');
                    this.saveClientSideProperties();
                    this.updateLayers(this._persistWith(touched));
                }
                this._toastLockedSkipped(skipped, 'data');
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearAllBtn) {
            customClearAllBtn.addEventListener('click', (e) => {
                this._dropPatternTileFocus(customClearAllBtn, e);
                if (!this.currentLayer) return;
                // The per-run overrides go with their paths: a reserved number
                // whose path was just wiped would leave an invisible gap in
                // the automatic numbering with nothing on the wall to show
                // for it. Clear All means back to auto, all of it - and on a
                // grouped screen, all of the wall (clearAllCustomRuns).
                const { touched, skipped } = this.clearAllCustomRuns(this.currentLayer, 'data');
                this.customSelection.clear();
                if (touched.length) {
                    this.saveState('Custom Clear All');
                    this.saveClientSideProperties();
                    this.updateLayers(this._persistWith(touched));
                }
                this._toastLockedSkipped(skipped, 'data');
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
                // With an overridden port open, the editable ports ARE the
                // layer's overrides - typing a number outside that list would
                // aim the next click at a port the user never took over.
                if (this._isOverrideEditing(this.currentLayer, 'data')
                        && !this.getOverrideNums(this.currentLayer, 'data').includes(nextVal)) {
                    customActivePortInput.value = `${this.currentLayer.customPortIndex || 1}`;
                    return;
                }
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.customPortIndex = nextVal;
                    if (this._overrideEditing && this._overrideEditing.kind === 'data'
                            && this._overrideEditing.layerId === this.currentLayer.id) {
                        this._overrideEditing.num = nextVal;
                    }
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

    }

    // Power Settings: voltage / amperage / watts, line and label sizes,
    // maximize / organized, random and colour-coded circuits, the port /
    // circuit / cable tag switches, power label templates and custom
    // power editing.
    _wirePowerPanel() {
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
        const showDataFlowPortInfoEl = document.getElementById('show-data-flow-port-info');
        const showDataFlowPortLoadEl = document.getElementById('show-data-flow-port-load');
        const showPowerCircuitInfoEl = document.getElementById('show-power-circuit-info');
        const showPowerNferTagsEl = document.getElementById('show-power-nfer-tags');
        const showPowerCableTagsEl = document.getElementById('show-power-cable-tags');
        const showDataCableTagsEl = document.getElementById('show-data-cable-tags');

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

        // There used to be a second copy of the circuit-colour row builder
        // here, identical to updatePowerCircuitColorEditor() except that its
        // rows carried no data-lrd-field and it did not preserve focus. Both
        // wrote the same container, so whichever ran last won - and this one
        // ran on the colour-coded-view toggle, which quietly undid the keys
        // the other one had just set. One builder now, in app-power.js beside
        // the other two editors.
        const updatePowerCircuitColorSection = () => {
            if (powerCircuitColorSection) {
                powerCircuitColorSection.style.display = (this.currentLayer && this.currentLayer.powerColorCodedView) ? 'block' : 'none';
            }
            this.updatePowerCircuitColorEditor();
        };

        if (powerVoltageSelect && powerVoltageCustomInput) {
            // One 'Change Power Voltage' entry per REAL change. A figure
            // equal to what every selected screen already holds commits
            // nothing - no rewrite, no PUT, no history entry. The
            // breakout rides along: a stored choice the new voltage
            // cannot run is rewritten by normalizePowerBreakout in the
            // same step (L21-30 at 208 -> 110 becomes Edison).
            const commitVoltage = (val, custom) => {
                const selected = this.getSelectedLayers();
                const changed = selected.some(
                    l => (parseFloat(l.powerVoltage) || 0) !== val);
                if (!changed) return;
                this.applyToSelectedLayers(layer => {
                    // setScreenVoltage writes the figure and normalizes
                    // the breakout in one step.
                    this.setScreenVoltage(layer, val);
                    if (custom) layer.powerVoltageCustom = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Voltage');
                window.canvasRenderer.render();
            };
            powerVoltageSelect.addEventListener('change', () => {
                updatePowerVoltageUI();
                if (powerVoltageSelect.value === 'custom') {
                    // Picking "Custom" commits NOTHING: the box used to
                    // hold its stock 110 and was committed on the pick,
                    // so a 208V L21-30 screen was written 110V + Edison
                    // before the user had typed a figure. The box is
                    // seeded with the screen's CURRENT voltage - so a
                    // commit of the seed is the no-op above - and the
                    // typed figure's own change event is the commit.
                    const cur = parseFloat(this.currentLayer
                        && this.currentLayer.powerVoltage) || 0;
                    if (cur > 0) powerVoltageCustomInput.value = cur;
                    powerVoltageCustomInput.focus();
                    if (typeof powerVoltageCustomInput.select === 'function') {
                        powerVoltageCustomInput.select();
                    }
                    return;
                }
                commitVoltage(parseFloat(powerVoltageSelect.value) || 0, false);
            });
            powerVoltageCustomInput.addEventListener('change', () => {
                // A custom voltage is whole volts, 1 or more, up to the
                // box's max (1000, index.html). An emptied box, 0, a
                // negative figure, a fraction (0.5, 1e-9), text or 100000
                // is not a screen voltage: the figure in force goes back
                // in the box and nothing is committed.
                const raw = String(powerVoltageCustomInput.value || '').trim();
                const val = raw === '' ? NaN : Number(raw);
                const max = parseFloat(powerVoltageCustomInput.getAttribute('max')) || Infinity;
                if (!Number.isInteger(val) || val < 1 || val > max) {
                    const cur = parseFloat(this.currentLayer
                        && this.currentLayer.powerVoltage) || 0;
                    if (cur > 0) powerVoltageCustomInput.value = cur;
                    return;
                }
                commitVoltage(val, true);
                // The box shows the figure that was COMMITTED, not the
                // text that was typed: "120.0" commits 120 and used to
                // sit in the box as "120.0" until the sidebar redrew.
                powerVoltageCustomInput.value = val;
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
                // v0.11.0: class, not an inline outline - Enter fires `change`
                // while the field still has focus and theme.css forces
                // `input:focus { outline:none !important }`, so the cue never showed.
                powerPanelWattsInput.classList.toggle('invalid', parsed === null);
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
        if (showDataFlowPortLoadEl) {
            showDataFlowPortLoadEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showDataFlowPortLoad = showDataFlowPortLoadEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Port Load Labels');
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
        // Same shape as Show Circuit Info: one tick writes every selected
        // screen, one history step. It hides only the tag text - the
        // bracket stays, since the user wanted the TEXT gone, not the
        // share ("disable the twofer/3fer text", 2026-09-06).
        if (showPowerNferTagsEl) {
            showPowerNferTagsEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showPowerNferTags = showPowerNferTagsEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle 2fer / 3fer Tags');
                window.canvasRenderer.render();
            });
        }
        // The cable tag switch, same shape: every selected screen, one
        // history step. Default off - the tag is for "the docs per
        // screen" (2026-09-06), so it is turned on for the export.
        if (showPowerCableTagsEl) {
            showPowerCableTagsEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showPowerCableTags = showPowerCableTagsEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Cable Tags');
                window.canvasRenderer.render();
            });
        }
        // The data side's switch, the same shape: a port's snake name or
        // its own cable beside its label, off by default ("the same option
        // for data homeruns", 2026-09-06).
        if (showDataCableTagsEl) {
            showDataCableTagsEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showDataCableTags = showDataCableTagsEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers(), true, 'Toggle Data Cable Tags');
                window.canvasRenderer.render();
            });
        }

        // Same rule as the ports side: the per-circuit list died with the
        // Power sidebar, so Apply Style restyles every circuit the shown
        // screen has. One circuit is renamed on its chip in the dock.
        const getSelectedPowerCircuits = () => {
            const layer = this.currentLayer;
            if (!layer || (layer.type || 'screen') !== 'screen') return [];
            const count = (typeof this.getLayerCircuitsRequired === 'function'
                ? this.getLayerCircuitsRequired(layer) : 0) || 0;
            return Array.from({ length: count }, (_, i) => i + 1);
        };

        if (powerLabelTemplateInput) {
            powerLabelTemplateInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLabelTemplate = powerLabelTemplateInput.value || 'S1-#';
                });
                this.saveClientSideProperties();
                // The template is the bottom rung of the naming ladder, so it
                // renames every multi still on it - and the multis are what
                // name the circuits. Restating drops the prepared index first;
                // rendering the wall off a stale one is how this last showed
                // up as labels that were a frame behind.
                this._restateNaming();
                this.updateLayers(this.getSelectedLayers(), true, 'Change Power Label Template');
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
        // Routed through stepCustomPort - see the matching comment on the
        // data-flow Prev/Next above. It carries the v0.8.2 PUT (without it a
        // Mode Toggle would PUT a single-circuit collapsed view of
        // layer.powerCustomPaths) and the override-list pinning.
        this._armStepButton(powerCustomPrev);
        this._armStepButton(powerCustomNext);
        if (powerCustomPrev) {
            powerCustomPrev.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.stepCustomPort(-1);
            });
        }
        if (powerCustomNext) {
            powerCustomNext.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.stepCustomPort(1);
            });
        }
        if (powerCustomClearCircuit) {
            powerCustomClearCircuit.addEventListener('click', (e) => {
                // Mouse click drops focus - see the data Clear Port.
                this._dropPatternTileFocus(powerCustomClearCircuit, e);
                if (!this.currentLayer) return;
                // No ensure* here - see the data Clear Port.
                const circuitNum = this.currentLayer.powerCustomIndex || 1;
                // This screen's circuit, and - whole - any peer's circuit of
                // the same number that lands here - see clearCustomRun.
                const { touched, skipped } = this.clearCustomRun(this.currentLayer, 'power', circuitNum);
                if (touched.length) {
                    this.saveState('Power Custom Clear Circuit');
                    this.saveClientSideProperties();
                    this.updateLayers(this._persistWith(touched));
                }
                this._toastLockedSkipped(skipped, 'power');
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearAll) {
            powerCustomClearAll.addEventListener('click', (e) => {
                this._dropPatternTileFocus(powerCustomClearAll, e);
                if (!this.currentLayer) return;
                // Overrides go with their paths - see the data Clear All. On a
                // grouped screen the whole wall clears (clearAllCustomRuns).
                const { touched, skipped } = this.clearAllCustomRuns(this.currentLayer, 'power');
                this.powerCustomSelection.clear();
                if (touched.length) {
                    this.saveState('Power Custom Clear All');
                    this.saveClientSideProperties();
                    this.updateLayers(this._persistWith(touched));
                }
                this._toastLockedSkipped(skipped, 'power');
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
                // Pinned to the override list while one is open - see the
                // data-flow input above.
                if (this._isOverrideEditing(this.currentLayer, 'power')
                        && !this.getOverrideNums(this.currentLayer, 'power').includes(nextVal)) {
                    powerCustomActive.value = `${this.currentLayer.powerCustomIndex || 1}`;
                    return;
                }
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.powerCustomIndex = nextVal;
                    if (this._overrideEditing && this._overrideEditing.kind === 'power'
                            && this._overrideEditing.layerId === this.currentLayer.id) {
                        this._overrideEditing.num = nextVal;
                    }
                    this.saveState('Power Custom Circuit Change');
                    this.saveClientSideProperties();
                    this.updateLayers(this.getSelectedLayers());
                    this.updateCustomPowerUI();
                    window.canvasRenderer.render();
                }
            });
        }
        // power custom debug removed
        
    }

    // The colour pickers (data flow, arrows, ports, power lines / labels,
    // fill colours), label and screen-name sizes, transparent fill,
    // rotation, the beach picker and the gradient / palette editors.
    _wireColorsAndSizes() {
        // Data Flow Color
        setupColorPickerWithHex('data-flow-color', 'data-flow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.dataFlowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Data Flow Color', 400, 'data-flow-color');
            }
            window.canvasRenderer.render();
        });
        
        // Arrow Color
        setupColorPickerWithHex('arrow-color', 'arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.arrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Arrow Color', 400, 'arrow-color');
            }
            window.canvasRenderer.render();
        });
        
        // Primary Color
        setupColorPickerWithHex('primary-color', 'primary-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Primary Port Color', 400, 'primary-color');
            }
            window.canvasRenderer.render();
        });

        // Primary Label Text Color
        setupColorPickerWithHex('primary-text-color', 'primary-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Primary Text Color', 400, 'primary-text-color');
            }
            window.canvasRenderer.render();
        });
        
        // Backup/Redundant Color
        setupColorPickerWithHex('backup-color', 'backup-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Backup Port Color', 400, 'backup-color');
            }
            window.canvasRenderer.render();
        });

        // Backup/Redundant Label Text Color
        setupColorPickerWithHex('backup-text-color', 'backup-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Backup Text Color', 400, 'backup-text-color');
            }
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-line-color', 'power-line-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLineColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Power Line Color', 400, 'power-line-color');
            }
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-arrow-color', 'power-arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerArrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Power Arrow Color', 400, 'power-arrow-color');
            }
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-bg-color', 'power-label-bg-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelBgColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Power Label Background', 400, 'power-label-bg-color');
            }
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-text-color', 'power-label-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Power Label Text Color', 400, 'power-label-text-color');
            }
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
        //
        // #labels-color is NOT wired here. setupColorPickerWithHex already
        // owns it (search "Labels color with hex sync"), the way it owns every
        // other colour picker in the sidebar: write the value, render, and on
        // a COMMIT record one debounced undo step. A plain change listener
        // here called updateLayerFromInputs() -> saveState() as well, and
        // saveState() flushes the pending debounce first - so one colour
        // commit landed two snapshots that BOTH already held the new colour,
        // and the first Ctrl+Z did nothing.
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
            // Native <input type=color> fires 'change' continuously while the
            // system picker is dragged, so record ONE coalesced undo step per
            // drag (debounced) instead of one per frame - the latter buries the
            // real history under dozens of 1-value colour steps.
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Fill Color', 400, 'color1-picker');
            }
        });
        setupColorPickerWithHex('color2-picker', 'color2-hex', (val, isFinal) => {
            const rgb = this.hexToRgb(val);
            this.applyToSelectedLayers(layer => {
                layer.color2 = rgb;
            });
            window.canvasRenderer.render();
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Change Fill Color', 400, 'color2-picker');
            }
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

        // Beaches (2026-09-08): the Screen Info picker - pick one of the
        // project's beaches or make one; one 'Set Beach' entry either way.
        if (typeof this.setupBeachPicker === 'function') this.setupBeachPicker();

        // v0.8.7.8: gradient overlay editor (standard multi-stop).
        this.setupGradientEditor();
        // v0.8.7.8: multi-color cabinet palette editor.
        this.setupPaletteEditor();
        
    }

    // The toolbar Raster: W x H fields, written to the active canvas.
    _wireToolbarRaster() {
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
        
    }

    // New / Open / Save / Preferences / Export buttons and the whole
    // export modal: option preview, format-specific rows, confirm, and
    // the backdrop close.
    _wireExportAndPrefs() {
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
            // The PSD layers row (one per screen / elements) shows with it.
            const psdLayersRow = document.getElementById('export-psd-layers-row');
            if (psdLayersRow) psdLayersRow.style.display = (formatEl.value === 'psd') ? '' : 'none';
        };
        const _formatEl = document.getElementById('export-format');
        if (_formatEl) {
            _formatEl.addEventListener('change', _toggleScaleRow);
            _toggleScaleRow();
            // The pull-sheet format swaps the picture sections for its own
            // (jumper names, engineer, rev) - app-pull-list.js.
            if (typeof this.syncPullSheetControls === 'function') {
                _formatEl.addEventListener('change', () => this.syncPullSheetControls());
            }
        }
        if (typeof this.initPullSheetControls === 'function') this.initPullSheetControls();
        // The pull-sheet editor modal (File > Pull Sheet…, and the dialog's
        // "Edit rows…") - app-pull-sheet-editor.js.
        if (typeof this.initPullSheetEditor === 'function') this.initPullSheetEditor();
        // The binder's own section (scope, palette, maps, pages) - app-binder.js.
        if (typeof this.initBinderControls === 'function') this.initBinderControls();
        
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
            
            // Pull sheet: no rendered views - the list is built from the
            // project and the workbook comes back from the server. Saved
            // through the same picker path the PDF uses.
            if (format === 'pull-sheet') {
                document.getElementById('export-modal').style.display = 'none';
                document.getElementById('status-message').textContent = 'Exporting pull sheet...';
                try {
                    await this.exportPullSheet(projectName);
                    document.getElementById('status-message').textContent = 'Export complete!';
                    setTimeout(() => { document.getElementById('status-message').textContent = 'Ready'; }, 3000);
                } catch (error) {
                    console.error('Pull sheet export error:', error);
                    document.getElementById('status-message').textContent = 'Export failed!';
                    sendClientLog('export_failed', { message: error.message, format: 'pull-sheet' });
                    if (typeof this._toast === 'function') this._toast(error.message, true, 6000);
                }
                return;
            }

            // Binder: pages laid out on the client from the pull list and the
            // renderer's own maps, bound into one PDF (app-binder.js). Saved
            // through the same picker path every export takes.
            if (format === 'binder') {
                document.getElementById('export-modal').style.display = 'none';
                document.getElementById('status-message').textContent = 'Exporting binder...';
                try {
                    await this.exportBinder(projectName);
                    document.getElementById('status-message').textContent = 'Export complete!';
                    setTimeout(() => { document.getElementById('status-message').textContent = 'Ready'; }, 3000);
                } catch (error) {
                    console.error('Binder export error:', error);
                    document.getElementById('status-message').textContent = 'Export failed!';
                    sendClientLog('export_failed', { message: error.message, format: 'binder' });
                    if (typeof this._toast === 'function') this._toast(error.message, true, 6000);
                }
                return;
            }

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

    }
}

for (const k of Object.getOwnPropertyNames(_Wiring.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Wiring.prototype, k));
    }
}
