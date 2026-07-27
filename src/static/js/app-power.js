// app-power: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Power {

    showContextMenu(x, y) {
        const menu = document.getElementById('context-menu');
        if (!menu) return;
        // Show/hide pixel-map-only menu group based on view + selection.
        const inPixelMap = window.canvasRenderer && window.canvasRenderer.viewMode === 'pixel-map';
        const haveSelection = this.pixelMapSelection && this.pixelMapSelection.size > 0;
        const showPixelMapItems = inPixelMap && haveSelection;
        menu.querySelectorAll('.pixel-map-only').forEach(el => {
            el.style.display = showPixelMapItems ? '' : 'none';
        });
        // Centering only applies where screens can actually be positioned:
        // Pixel Map (processor offset) and Show Look (show offset). Data and
        // Power mirror the Show Look position, so they're read-only there.
        const canCenter = window.canvasRenderer
            && ['pixel-map', 'show-look'].includes(window.canvasRenderer.viewMode)
            && this.getSelectedLayers().some(l => !l.locked);
        menu.querySelectorAll('.movable-view-only').forEach(el => {
            el.style.display = canCenter ? '' : 'none';
        });
        menu.style.visibility = 'hidden';
        menu.style.display = 'block';
        const menuRect = menu.getBoundingClientRect();
        const margin = 8;
        const maxX = window.innerWidth - menuRect.width - margin;
        const maxY = window.innerHeight - menuRect.height - margin;
        const clampedX = Math.max(margin, Math.min(x, maxX));
        const clampedY = Math.max(margin, Math.min(y, maxY));
        menu.style.left = `${clampedX}px`;
        menu.style.top = `${clampedY}px`;
        menu.style.visibility = 'visible';
    }

    hideContextMenu() {
        const menu = document.getElementById('context-menu');
        if (menu) menu.style.display = 'none';
    }

    /**
     * v0.10.4: center the selected screens on their canvas's raster, on one
     * axis or both. Pixel Map writes offset_x/offset_y against the canvas's
     * pixel raster; Show Look writes showOffsetX/showOffsetY against the show
     * raster. Data and Power mirror Show Look, so the menu hides there.
     *
     * Each screen centers on ITS OWN canvas, so a multi-select spanning two
     * canvases does the right thing per screen. Rotated screens center by
     * their visible footprint (getLayerBounds is the rotated box).
     */
    centerLayersOnCanvas(axis = 'both') {
        const cr = window.canvasRenderer;
        if (!cr || !['pixel-map', 'show-look'].includes(cr.viewMode)) return;
        const layers = (this.getSelectedLayers() || []).filter(l => l && !l.locked);
        if (layers.length === 0) return;

        const useShow = cr.viewMode === 'show-look';
        const canvases = (this.project && this.project.canvases) || [];
        const moved = [];

        layers.forEach(layer => {
            const canvasId = useShow ? (layer.show_canvas_id || layer.canvas_id) : layer.canvas_id;
            const canvas = canvases.find(c => c.id === canvasId);
            if (!canvas) return;
            const rasterW = (useShow && canvas.show_raster_width) || canvas.raster_width || 0;
            const rasterH = (useShow && canvas.show_raster_height) || canvas.raster_height || 0;
            if (rasterW <= 0 || rasterH <= 0) return;

            // getLayerBounds is the UNROTATED box, so swap for a 90/270 screen
            // to get the visible footprint. The stored offset is the unrotated
            // top-left, so subtract the footprint delta to turn a desired
            // footprint position back into an offset.
            const b = cr.getLayerBounds(layer);
            const deg = (((Number(layer.rotation) || 0) % 360) + 360) % 360;
            const swap = deg === 90 || deg === 270;
            const fpW = swap ? b.height : b.width;
            const fpH = swap ? b.width : b.height;
            const fp = cr.getLayerFootprintOffset(layer);
            const centeredX = Math.round((rasterW - fpW) / 2 - fp.dx);
            const centeredY = Math.round((rasterH - fpH) / 2 - fp.dy);

            if (useShow) {
                if (axis === 'x' || axis === 'both') layer.showOffsetX = centeredX;
                if (axis === 'y' || axis === 'both') layer.showOffsetY = centeredY;
            } else {
                // Keep Show Look following the move while the two are linked
                // (same rule the Screen Info offset fields use).
                const linkedX = Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0);
                const linkedY = Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0);
                if (axis === 'x' || axis === 'both') {
                    layer.offset_x = centeredX;
                    if (linkedX) layer.showOffsetX = centeredX;
                }
                if (axis === 'y' || axis === 'both') {
                    layer.offset_y = centeredY;
                    if (linkedY) layer.showOffsetY = centeredY;
                }
            }
            moved.push(layer);
        });

        if (moved.length === 0) return;
        const label = axis === 'x' ? 'Center on Canvas X'
            : axis === 'y' ? 'Center on Canvas Y' : 'Center on Canvas';
        this.saveState(label);
        this.updateLayers(moved);
        this.loadLayerToInputs();
        cr.render();
    }

    stepCustomPort(delta) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        const view = window.canvasRenderer.viewMode;
        if (view === 'data-flow' && this.isCustomFlow(this.currentLayer)) {
            this.ensureCustomFlowState(this.currentLayer);
            this.currentLayer.customPortIndex = Math.max(1, (this.currentLayer.customPortIndex || 1) + delta);
            this.saveState('Custom Port Change');
            this.saveClientSideProperties();
            // v0.8.2: PUT to server (keyboard shortcut path needs the same
            // server sync as the on-screen Next/Prev buttons).
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        } else if (view === 'power' && this.isCustomPower(this.currentLayer)) {
            this.ensureCustomPowerState(this.currentLayer);
            this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) + delta);
            this.saveState('Power Custom Circuit Change');
            this.saveClientSideProperties();
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomPowerUI();
            window.canvasRenderer.render();
        }
    }
    
    // v0.10.9: Enable + highlight the Organized / Max Capacity buttons from the
    // current layer's portMappingMode. Both modes are valid on every processor
    // now; NovaStar Armor honours its reserved-rectangle rule in BOTH of them,
    // which is why its usable capacity is lower than a plain pixel sum.
    updatePortMappingButtons() {
        const mappingOrgBtn = document.getElementById('mapping-organized');
        const mappingMaxBtn = document.getElementById('mapping-max-capacity');
        if (!mappingOrgBtn || !mappingMaxBtn) return;

        const layer = this.currentLayer;
        const processorType = (layer && layer.processorType) || 'novastar-armor';
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const isOrganized = ((layer && layer.portMappingMode) || 'organized') === 'organized';

        mappingOrgBtn.style.opacity = '1';
        mappingOrgBtn.style.pointerEvents = 'auto';
        mappingMaxBtn.style.opacity = '1';
        mappingMaxBtn.style.pointerEvents = 'auto';

        const rectNote = usesRectangle
            ? ' NovaStar Armor reserves a pixel rectangle enclosing every cabinet in the port, so a port holds fewer pixels than the raw limit.'
            : '';
        mappingOrgBtn.title = 'Ports fill complete rows or columns only.' + rectNote;
        mappingMaxBtn.title = 'Ports fill to max pixel capacity - may split mid-row/column.' + rectNote;

        // v0.10.9: the theme styles .mapping-mode-btn / .mapping-mode-btn.active
        // with !important, so the .active class is the ONLY thing that can move
        // the highlight. Inline background/color writes here were dead.
        mappingOrgBtn.classList.toggle('active', isOrganized);
        mappingMaxBtn.classList.toggle('active', !isOrganized);
    }

    // Update the port capacity display in the UI
    updatePortCapacityDisplay() {
        // v0.10.9: run the button pass FIRST. It used to sit at the end of this
        // function, behind the early returns below (no current layer / image
        // layer), so the buttons could latch into a stale state.
        this.updatePortMappingButtons();
        // v0.10.9: same reasoning - the Low Latency control and its note must
        // not latch on a stale processor when the early returns below fire.
        this.updateLowLatencyUI();

        if (!this.currentLayer) {
            return;
        }
        if ((this.currentLayer.type || 'screen') === 'image') {
            const capacityEl = document.getElementById('port-capacity');
            const panelsPerPortEl = document.getElementById('panels-per-port');
            const portsRequiredEl = document.getElementById('ports-required');
            if (capacityEl) capacityEl.textContent = '-';
            if (panelsPerPortEl) panelsPerPortEl.textContent = '-';
            if (portsRequiredEl) portsRequiredEl.textContent = '-';
            return;
        }
        
        const bitDepth = this.currentLayer.bitDepth || 8;
        const frameRate = this.currentLayer.frameRate || 60;
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const portCapacity = this.calculatePortCapacity(
            bitDepth, frameRate, processorType, !!this.currentLayer.lowLatency);
        
        // Update capacity display
        const capacityEl = document.getElementById('port-capacity');
        if (capacityEl) {
            // v0.10.9: healthy value rides on .value-accent (follows the themed
            // accent); only the warning colour stays an inline override.
            if (portCapacity > 0) {
                capacityEl.textContent = portCapacity.toLocaleString();
                capacityEl.classList.add('value-accent');
                capacityEl.style.color = '';
            } else {
                capacityEl.textContent = 'N/A';
                capacityEl.classList.remove('value-accent');
                capacityEl.style.color = '#ff6600';
            }
        }

        const panelPixels = this.getFullPanelPixels(this.currentLayer);
        const panelsPerPort = (portCapacity > 0 && panelPixels > 0) ? Math.floor(portCapacity / panelPixels) : 0;
        
        const panelsPerPortEl = document.getElementById('panels-per-port');
        if (panelsPerPortEl) {
            if (panelsPerPort < 1) {
                panelsPerPortEl.textContent = 'ERROR';
                panelsPerPortEl.classList.remove('value-accent');
                panelsPerPortEl.style.color = '#ff0000';
            } else {
                panelsPerPortEl.textContent = panelsPerPort.toLocaleString();
                panelsPerPortEl.classList.add('value-accent');
                panelsPerPortEl.style.color = '';
            }
        }
        
        // Calculate total ports required from assignments
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const visiblePanels = this.currentLayer.panels ? this.currentLayer.panels.filter(p => !p.hidden).length : 0;
        const panelCountForStatus = usesRectangle && this.currentLayer.panels ? this.currentLayer.panels.length : visiblePanels;
        const assignments = this.calculatePortAssignments(this.currentLayer);
        let portsRequired = this.currentLayer._autoPortsRequired || assignments.reduce((max, a) => Math.max(max, a.port || 0), 0);

        const basePortsRequired = portsRequired;
        if (this.isCustomFlow(this.currentLayer) && this.currentLayer.customPortPaths) {
            const customPorts = Object.keys(this.currentLayer.customPortPaths)
                .map(p => parseInt(p, 10))
                .filter(p => (this.currentLayer.customPortPaths[p] || []).length > 0);
            if (customPorts.length > 0) {
                portsRequired = Math.max(...customPorts);
            } else {
                portsRequired = basePortsRequired > 0 ? basePortsRequired : (this.currentLayer.customPortIndex || 1);
            }
        }
        this.currentLayer._portsRequired = portsRequired;
        // debug toggle removed
        const portsRequiredEl = document.getElementById('ports-required');
        if (portsRequiredEl) {
            if ((this.currentLayer._capacityError || (portsRequired === 0 && panelsPerPort > 0 && panelCountForStatus > 0))) {
                portsRequiredEl.textContent = 'ERROR';
                portsRequiredEl.style.color = '#ff0000';
            } else if (panelCountForStatus === 0) {
                portsRequiredEl.textContent = '0';
                portsRequiredEl.style.color = '#888';
            } else {
                portsRequiredEl.textContent = portsRequired;
                if (portsRequired <= 4) {
                    portsRequiredEl.style.color = '#00cc00';
                } else if (portsRequired <= 8) {
                    portsRequiredEl.style.color = '#ffcc00';
                } else {
                    portsRequiredEl.style.color = '#ff6600';
                }
            }
        }
        
    }

    updatePowerCapacityDisplay() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') {
            const wattsEl = document.getElementById('power-watts-per-circuit');
            const panelsEl = document.getElementById('power-panels-per-circuit');
            const circuitsEl = document.getElementById('power-circuits-required');
            const amps1El = document.getElementById('power-total-amps-1ph');
            const amps3El = document.getElementById('power-total-amps-3ph');
            if (wattsEl) wattsEl.textContent = '-';
            if (panelsEl) panelsEl.textContent = '-';
            if (circuitsEl) circuitsEl.textContent = '-';
            if (amps1El) amps1El.textContent = '-';
            if (amps3El) amps3El.textContent = '-';
            return;
        }
        const layer = this.currentLayer;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const panelsPerCircuit = panelWatts > 0 ? Math.floor(wattsPerCircuit / panelWatts) : 0;
        const visiblePanels = layer.panels ? layer.panels.filter(p => !p.hidden) : [];
        const equivalentPanels = visiblePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
        const totalWatts = panelWatts * equivalentPanels;
        const totalAmps1 = voltage > 0 ? totalWatts / voltage : 0;
        const totalAmps3 = voltage > 0 ? totalWatts / (voltage * 1.73) : 0;
        layer._powerTotalAmps1 = totalAmps1;
        layer._powerTotalAmps3 = totalAmps3;

        const wattsEl = document.getElementById('power-watts-per-circuit');
        const panelsEl = document.getElementById('power-panels-per-circuit');
        const circuitsEl = document.getElementById('power-circuits-required');
        const amps1El = document.getElementById('power-total-amps-1ph');
        const amps3El = document.getElementById('power-total-amps-3ph');

        if (wattsEl) wattsEl.textContent = wattsPerCircuit > 0 ? wattsPerCircuit.toLocaleString() : '0';
        if (panelsEl) panelsEl.textContent = panelsPerCircuit > 0 ? panelsPerCircuit.toLocaleString() : '0';
        const powerAssignments = this.calculatePowerAssignments(layer);
        const circuitsRequired = powerAssignments.circuits.length;
        layer._powerError = powerAssignments.error;
        layer._powerCircuits = powerAssignments.circuits;

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString() : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        if (amps1El) amps1El.textContent = totalAmps1 ? totalAmps1.toFixed(2) + ' A' : '0';
        if (amps3El) amps3El.textContent = totalAmps3 ? totalAmps3.toFixed(2) + ' A' : '0';
    }

    calculatePowerAssignments(layer) {
        if (!layer || (layer.type || 'screen') === 'image' || !Array.isArray(layer.panels)) return { circuits: [], error: null };

        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const pattern = layer.powerFlowPattern || 'tl-h';
        const maximize = !!layer.powerMaximize;
        const organized = !!layer.powerOrganized && !maximize;
        const isHorizontalFirst = pattern.includes('-h');
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');

        if (wattsPerCircuit <= 0 || panelWatts <= 0) {
            return { circuits: [], error: null };
        }

        const loadOf = (panel) => panelWatts * this.getPanelLoadFactor(layer, panel);
        const visibleOrdered = this.getOrderedPanelsByPattern(layer, pattern, false);
        if (visibleOrdered.length === 0) return { circuits: [], error: null };

        if (panelWatts > wattsPerCircuit) {
            return { circuits: [], error: { message: 'PANEL WATTS EXCEED CIRCUIT CAPACITY' } };
        }

        const circuits = [];
        if (organized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(layer.rows).keys()].map(i => (startsTop ? i : (layer.rows - 1 - i)))
                : [...Array(layer.columns).keys()].map(i => (startsLeft ? i : (layer.columns - 1 - i)));
            let current = { unitIndices: [], load: 0 };

            for (const idx of unitIndices) {
                const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? p.row === idx : p.col === idx));
                if (unitPanels.length === 0) continue;
                const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                if (unitLoad > wattsPerCircuit) {
                    return {
                        circuits: [],
                        error: {
                            message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                            unitType: isHorizontalFirst ? 'row' : 'column',
                            unitCount: isHorizontalFirst ? layer.columns : layer.rows
                        }
                    };
                }
                if (current.load > 0 && current.load + unitLoad > wattsPerCircuit) {
                    circuits.push(
                        this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false)
                    );
                    current = { unitIndices: [], load: 0 };
                }
                current.unitIndices.push(idx);
                current.load += unitLoad;
            }
            if ((current.unitIndices || []).length > 0) {
                circuits.push(
                    this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false)
                );
            }
        } else {
            let current = [];
            let currentLoad = 0;
            visibleOrdered.forEach(panel => {
                const load = loadOf(panel);
                if (load <= 0) return;
                if (currentLoad > 0 && currentLoad + load > wattsPerCircuit) {
                    circuits.push(current);
                    current = [];
                    currentLoad = 0;
                }
                current.push(panel);
                currentLoad += load;
            });
            if (current.length > 0) circuits.push(current);
        }

        return { circuits, error: null };
    }

    getPortLabelText(layer, portNum, type) {
        const template = type === 'return' ? (layer.portLabelTemplateReturn || 'R#') : (layer.portLabelTemplatePrimary || 'P#');
        const overrides = type === 'return' ? (layer.portLabelOverridesReturn || {}) : (layer.portLabelOverridesPrimary || {});
        if (overrides && overrides[portNum]) return overrides[portNum];
        return template.replace('#', portNum);
    }

    getPowerCircuitLabel(layer, circuitNum) {
        const template = layer.powerLabelTemplate || 'S1-#';
        const overrides = layer.powerLabelOverrides || {};
        if (overrides && overrides[circuitNum]) return overrides[circuitNum];
        // A multi/soca has 6 ports, so labels wrap every 6 circuits and the
        // soca number in the template increments. Works for any template
        // shaped like <prefix><number><separator>#, e.g. S1-#, S2-#, MULTI3-#.
        const m = String(template).match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
        if (m) {
            const prefix = m[1];
            const startMulti = parseInt(m[2], 10) || 1;
            const sep = m[3];
            const suffix = m[4];
            const n = Math.max(1, parseInt(circuitNum, 10) || 1);
            const multi = startMulti + Math.floor((n - 1) / 6);
            const circuitInMulti = ((n - 1) % 6) + 1;
            return `${prefix}${multi}${sep}${circuitInMulti}${suffix}`;
        }
        return template.replace('#', circuitNum);
    }

    getDefaultPowerCircuitColors() {
        return {
            A: '#BC382F',
            B: '#CC6B30',
            C: '#D2E94D',
            D: '#2CF82B',
            E: '#2145DC',
            F: '#7414F5'
        };
    }

    normalizeHexColor(value, fallback = '#FF0000') {
        const raw = String(value || '').trim();
        if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
        if (/^[0-9a-fA-F]{6}$/.test(raw)) return `#${raw.toUpperCase()}`;
        return fallback;
    }

    normalizePowerCircuitColors(colors) {
        const defaults = this.getDefaultPowerCircuitColors();
        const next = { ...defaults };
        if (colors && typeof colors === 'object') {
            Object.keys(defaults).forEach(letter => {
                if (colors[letter]) {
                    next[letter] = this.normalizeHexColor(colors[letter], defaults[letter]);
                }
            });
        }
        // Migrate old default green (Circuit 4) to the new default.
        if ((next.D || '').toUpperCase() === '#79FC4C') {
            next.D = defaults.D;
        }
        return next;
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

    getPowerCircuitColor(layer, circuitNum) {
        const colors = this.normalizePowerCircuitColors(layer && layer.powerCircuitColors);
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const slots = ['A', 'B', 'C', 'D', 'E', 'F'];
        const slotKey = slots[(n - 1) % slots.length];
        return colors[slotKey] || '#BC382F';
    }

    updatePortLabelEditor() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') return;
        const list = document.getElementById('port-label-list');
        if (!list) return;

        let portsRequired = this.currentLayer._portsRequired || 0;
        if (portsRequired <= 0) {
            this.updatePortCapacityDisplay();
            portsRequired = this.currentLayer._portsRequired || 0;
        }
        if (this.customDebug) {
            console.log('[PortLabels] update', {
                layerId: this.currentLayer.id,
                portsRequired,
                flowPattern: this.currentLayer.flowPattern,
                bitDepth: this.currentLayer.bitDepth,
                frameRate: this.currentLayer.frameRate,
                processorType: this.currentLayer.processorType,
                panelPixels: this.currentLayer.cabinet_width * this.currentLayer.cabinet_height,
                panels: this.currentLayer.panels ? this.currentLayer.panels.length : 0
            });
        }
        list.innerHTML = '';
        // v0.8.7.3: force the list's grid to 1fr so each row stretches
        // the full list width instead of collapsing to content width
        // (which left ~12px of dead space on the right after the
        // backup input). Also tighten the list's own padding to claw
        // back another ~8px for the inputs. Negative margins break the
        // list out of the panel-content's 12px L+R padding so the
        // inputs can extend the full sidebar interior, claws back
        // another 24px (12 on each side).
        list.style.gridTemplateColumns = '1fr';
        list.style.padding = '4px';
        list.style.marginLeft = '-12px';
        list.style.marginRight = '-12px';

        if (portsRequired <= 0) {
            const empty = document.createElement('div');
            empty.style.color = '#888';
            empty.style.fontSize = '11px';
            empty.textContent = 'No ports to edit.';
            list.appendChild(empty);
            return;
        }

        for (let portNum = 1; portNum <= portsRequired; portNum++) {
            const row = document.createElement('div');
            row.style.display = 'grid';
            // v0.8.7.3: compact "1" / "2" number column instead of the
            // full "Port N" text, saves ~40px in the narrow 260px
            // sidebar so both inputs get more width. Row stretches to
            // fill its container with no right-side gap.
            row.style.gridTemplateColumns = '18px 14px 1fr 1fr';
            row.style.gap = '4px';
            row.style.alignItems = 'center';
            row.style.width = '100%';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-port', String(portNum));
            cb.title = `Port ${portNum}`;
            cb.style.margin = '0';

            const numLabel = document.createElement('div');
            numLabel.style.fontSize = '13px';
            numLabel.style.fontWeight = '700';
            numLabel.style.color = '#ccc';
            numLabel.style.textAlign = 'center';
            numLabel.style.fontFamily = 'monospace';
            numLabel.textContent = String(portNum);

            const primaryInput = document.createElement('input');
            primaryInput.type = 'text';
            primaryInput.value = (this.currentLayer.portLabelOverridesPrimary && this.currentLayer.portLabelOverridesPrimary[portNum]) || '';
            primaryInput.placeholder = this.getPortLabelText(this.currentLayer, portNum, 'primary');
            primaryInput.style.padding = '3px 4px';
            primaryInput.style.background = '#0d0d0d';
            primaryInput.style.border = '1px solid #333';
            primaryInput.style.color = '#fff';
            primaryInput.style.borderRadius = '4px';
            primaryInput.style.fontFamily = 'monospace';
            // v0.8.7.3: fill the grid column instead of using the input's
            // default intrinsic width (was leaving wasted space to the
            // right of each input). Power editor already does this.
            primaryInput.style.width = '100%';
            primaryInput.style.minWidth = '0';
            primaryInput.style.boxSizing = 'border-box';

            primaryInput.addEventListener('change', () => {
                const val = primaryInput.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.portLabelOverridesPrimary) layer.portLabelOverridesPrimary = {};
                    if (val) {
                        layer.portLabelOverridesPrimary[portNum] = val;
                    } else {
                        delete layer.portLabelOverridesPrimary[portNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Edit Port Label');
            });

            const returnInput = document.createElement('input');
            returnInput.type = 'text';
            returnInput.value = (this.currentLayer.portLabelOverridesReturn && this.currentLayer.portLabelOverridesReturn[portNum]) || '';
            returnInput.placeholder = this.getPortLabelText(this.currentLayer, portNum, 'return');
            returnInput.style.padding = '3px 4px';
            returnInput.style.background = '#0d0d0d';
            returnInput.style.border = '1px solid #333';
            returnInput.style.color = '#fff';
            returnInput.style.borderRadius = '4px';
            returnInput.style.fontFamily = 'monospace';
            returnInput.style.width = '100%';
            returnInput.style.minWidth = '0';
            returnInput.style.boxSizing = 'border-box';

            returnInput.addEventListener('change', () => {
                const val = returnInput.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.portLabelOverridesReturn) layer.portLabelOverridesReturn = {};
                    if (val) {
                        layer.portLabelOverridesReturn[portNum] = val;
                    } else {
                        delete layer.portLabelOverridesReturn[portNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Edit Port Label');
            });

            row.appendChild(cb);
            row.appendChild(numLabel);
            row.appendChild(primaryInput);
            row.appendChild(returnInput);
            list.appendChild(row);
        }
    }

    updatePowerLabelEditor() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') return;
        const list = document.getElementById('power-label-list');
        if (!list) return;
        list.style.overflowX = 'hidden';

        let circuitsRequired = this.currentLayer._powerCircuitsRequired || 0;
        if (this.isCustomPower(this.currentLayer) && this.currentLayer.powerCustomPaths) {
            const customCircuits = Object.keys(this.currentLayer.powerCustomPaths)
                .map(c => parseInt(c, 10))
                .filter(c => (this.currentLayer.powerCustomPaths[c] || []).length > 0);
            if (customCircuits.length > 0) {
                circuitsRequired = Math.max(...customCircuits);
            } else {
                circuitsRequired = circuitsRequired > 0 ? circuitsRequired : (this.currentLayer.powerCustomIndex || 1);
            }
        }

        list.innerHTML = '';
        // v0.8.7.3: stretch each row to full list width, trim padding,
        // and extend past panel-content padding for more input room.
        list.style.gridTemplateColumns = '1fr';
        list.style.padding = '4px';
        list.style.marginLeft = '-12px';
        list.style.marginRight = '-12px';
        if (circuitsRequired <= 0) {
            const empty = document.createElement('div');
            empty.style.color = '#888';
            empty.style.fontSize = '11px';
            empty.textContent = 'No circuits to edit.';
            list.appendChild(empty);
            return;
        }

        for (let circuitNum = 1; circuitNum <= circuitsRequired; circuitNum++) {
            const row = document.createElement('div');
            row.style.display = 'grid';
            // v0.8.7.3: compact "1" / "2" number column, same as port
            // editor. Row stretches to fill its container width.
            row.style.gridTemplateColumns = '18px 18px 1fr';
            row.style.gap = '4px';
            row.style.alignItems = 'center';
            row.style.width = '100%';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit', String(circuitNum));
            cb.title = `Circuit ${circuitNum}`;
            cb.style.margin = '0';

            const numLabel = document.createElement('div');
            numLabel.style.fontSize = '13px';
            numLabel.style.fontWeight = '700';
            numLabel.style.color = '#ccc';
            numLabel.style.textAlign = 'center';
            numLabel.style.fontFamily = 'monospace';
            numLabel.textContent = String(circuitNum);

            const input = document.createElement('input');
            input.type = 'text';
            input.value = (this.currentLayer.powerLabelOverrides && this.currentLayer.powerLabelOverrides[circuitNum]) || '';
            input.placeholder = this.getPowerCircuitLabel(this.currentLayer, circuitNum);
            input.style.padding = '3px 4px';
            input.style.background = '#0d0d0d';
            input.style.border = '1px solid #333';
            input.style.color = '#fff';
            input.style.borderRadius = '4px';
            input.style.fontFamily = 'monospace';
            input.style.width = '100%';
            input.style.minWidth = '0';
            input.style.boxSizing = 'border-box';

            input.addEventListener('change', () => {
                const val = input.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
                    if (val) {
                        layer.powerLabelOverrides[circuitNum] = val;
                    } else {
                        delete layer.powerLabelOverrides[circuitNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Edit Circuit Label');
            });

            row.appendChild(cb);
            row.appendChild(numLabel);
            row.appendChild(input);
            list.appendChild(row);
        }
    }

    updatePowerCircuitColorEditor() {
        if (!this.currentLayer) return;
        const section = document.getElementById('power-circuit-color-section');
        const list = document.getElementById('power-circuit-color-list');
        if (section) {
            section.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        if (!list) return;
        list.innerHTML = '';
        const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
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
            list.appendChild(row);
        });
    }

    isCustomFlow(layer) {
        return !!layer && layer.flowPattern === 'custom';
    }

    ensureCustomFlowState(layer) {
        if (!layer) return;
        if (!layer.customPortPaths) layer.customPortPaths = {};
        if (!layer.customPortIndex) layer.customPortIndex = 1;
    }

    toggleCustomFlowMode(enabled) {
        if (!this.currentLayer) return;
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.flowPattern && layer.flowPattern !== 'custom') {
                    layer.lastFlowPattern = layer.flowPattern;
                }
                layer.flowPattern = 'custom';
                this.ensureCustomFlowState(layer);
            } else {
                layer.flowPattern = layer.lastFlowPattern || 'tl-h';
            }
        });
        if (!enabled) {
            this.customSelectMode = false;
            this.customSelection.clear();
        }
        this.saveState('Custom Mode Toggle');
        this.saveClientSideProperties();
        // Recompute port count BEFORE the server roundtrip so the layer's
        // _portsRequired is fresh when preservedProps captures it.
        this.updatePortCapacityDisplay();
        this.updateLayers(this.getSelectedLayers());
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    updateCustomFlowUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('custom-flow-controls');
            if (container) container.style.display = 'none';
            return;
        }
        const isCustom = this.currentLayer && this.currentLayer.flowPattern === 'custom';
        const container = document.getElementById('custom-flow-controls');
        const portInput = document.getElementById('custom-active-port-input');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.customPortIndex || 1}`;
        }
        if (window.canvasRenderer) {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
    }

    isCustomPower(layer) {
        return !!layer && layer.powerFlowPattern === 'custom';
    }

    ensureCustomPowerState(layer) {
        if (!layer) return;
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (!layer.powerCustomIndex) layer.powerCustomIndex = 1;
    }

    toggleCustomPowerMode(enabled) {
        if (!this.currentLayer) return;
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.powerFlowPattern && layer.powerFlowPattern !== 'custom') {
                    layer.lastPowerFlowPattern = layer.powerFlowPattern;
                }
                layer.powerFlowPattern = 'custom';
                layer.powerCustomPath = true;
                this.ensureCustomPowerState(layer);
            } else {
                layer.powerFlowPattern = layer.lastPowerFlowPattern || 'tl-h';
                layer.powerCustomPath = false;
            }
        });
        if (!enabled) {
            this.powerCustomSelection.clear();
        }
        this.saveState('Power Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updateLayers(this.getSelectedLayers());
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    updateCustomPowerUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('power-custom-controls');
            if (container) container.style.display = 'none';
            return;
        }
        const isCustom = this.currentLayer && this.currentLayer.powerFlowPattern === 'custom';
        const container = document.getElementById('power-custom-controls');
        const portInput = document.getElementById('power-custom-active');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.powerCustomIndex || 1}`;
        }
        if (window.canvasRenderer) {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
    }

    getPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    getPanelByRowCol(layer, row, col) {
        if (!layer || !layer.panels) return null;
        return layer.panels.find(p => p.row === row && p.col === col) || null;
    }

    togglePanelSelection(panel) {
        if (!panel) return;
        const key = this.getPanelKey(panel);
        if (this.customSelection.has(key)) {
            this.customSelection.delete(key);
        } else {
            this.customSelection.add(key);
        }
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    clearCustomSelection() {
        this.customSelection.clear();
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    selectPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomFlow(layer)) return;
        this.customSelection.clear();
        const off = this._getLayerWorkspaceOffset(layer);
        const minX = Math.min(rect.x1, rect.x2) - off.wx;
        const maxX = Math.max(rect.x1, rect.x2) - off.wx;
        const minY = Math.min(rect.y1, rect.y2) - off.wy;
        const maxY = Math.max(rect.y1, rect.y2) - off.wy;
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.customSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    // ---------- Pixel Map bulk-select (panel selection on the Pixel Map tab) ----------

    selectPixelMapPanelsInRect(layer, rect) {
        if (!layer || !rect) return;
        this.pixelMapSelection.clear();
        // rect is in workspace coords; panel coords are canvas-relative,
        // shift by the layer's parent canvas's workspace offset before
        // comparing. (No-op for single-canvas projects.)
        const off = this._getLayerWorkspaceOffset(layer);
        let x1 = Math.min(rect.x1, rect.x2) - off.wx;
        let x2 = Math.max(rect.x1, rect.x2) - off.wx;
        let y1 = Math.min(rect.y1, rect.y2) - off.wy;
        let y2 = Math.max(rect.y1, rect.y2) - off.wy;
        // v0.9.3: if the screen is rotated, map the marquee back into the screen's
        // unrotated panel space (rotation is 90/180/270, so it stays axis-aligned).
        const _r = window.canvasRenderer;
        if (_r && _r._unrotatePointForLayer) {
            const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                .map(([x, y]) => _r._unrotatePointForLayer(x, y, layer));
            x1 = Math.min(...corners.map(c => c.x)); x2 = Math.max(...corners.map(c => c.x));
            y1 = Math.min(...corners.map(c => c.y)); y2 = Math.max(...corners.map(c => c.y));
        }
        const minX = x1, maxX = x2, minY = y1, maxY = y2;
        // Include hidden ("blank") panels so they can be selected for bulk
        // restore via the sidebar / Alt+click action.
        (layer.panels || []).forEach(panel => {
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.pixelMapSelection.add(this.getPanelKey(panel));
        });
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    togglePixelMapPanelSelection(panel) {
        if (!panel) return;
        const key = this.getPanelKey(panel);
        if (this.pixelMapSelection.has(key)) {
            this.pixelMapSelection.delete(key);
        } else {
            this.pixelMapSelection.add(key);
        }
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    clearPixelMapSelection() {
        if (!this.pixelMapSelection || this.pixelMapSelection.size === 0) return;
        this.pixelMapSelection.clear();
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    getPixelMapSelectedPanels() {
        if (!this.currentLayer || !this.currentLayer.panels) return [];
        return this.currentLayer.panels.filter(p => this.pixelMapSelection.has(this.getPanelKey(p)));
    }

    /**
     * Auto-detect half-tile direction for a panel based on its visible neighbors:
     *  - top/bottom edge (no neighbor above or below): 'height'
     *  - left/right edge (no neighbor left or right): 'width'
     *  - corner (two missing): default 'height' (top/bottom is the common case)
     *  - interior (all four neighbors visible): 'height' (rare; user can force-W via UI)
     */
    autoDetectHalfDirection(layer, panel) {
        if (!layer || !panel) return 'height';
        const get = (r, c) => (layer.panels || []).find(p => p.row === r && p.col === c);
        const neighborVisible = (r, c) => {
            const n = get(r, c);
            return !!(n && !n.hidden);
        };
        const hasAbove = neighborVisible(panel.row - 1, panel.col);
        const hasBelow = neighborVisible(panel.row + 1, panel.col);
        const hasLeft = neighborVisible(panel.row, panel.col - 1);
        const hasRight = neighborVisible(panel.row, panel.col + 1);
        const verticalEdge = !hasAbove || !hasBelow;
        const horizontalEdge = !hasLeft || !hasRight;
        if (verticalEdge && !horizontalEdge) return 'height';
        if (horizontalEdge && !verticalEdge) return 'width';
        // Corner or interior, default to 'height' (top/bottom edges are the common case).
        return 'height';
    }

    async setPanelsHalfTileBulk(panels, halfTile) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        // For 'auto', vote across the selection: pick the direction the
        // majority of panels would auto-detect to, then apply that uniformly.
        // Avoids a row of selected panels splitting into different directions
        // when one happens to be an interior panel.
        let resolved = halfTile;
        if (halfTile === 'auto') {
            let widthVotes = 0;
            let heightVotes = 0;
            panels.forEach(p => {
                const d = this.autoDetectHalfDirection(this.currentLayer, p);
                if (d === 'width') widthVotes++;
                else heightVotes++;
            });
            // Tie goes to 'height' (top/bottom is the more common case).
            resolved = widthVotes > heightVotes ? 'width' : 'height';
        }
        const body = {
            panels: panels.map(p => ({
                id: p.id,
                halfTile: resolved,
            })),
        };
        // Apply locally so the canvas updates immediately while the POST is in
        // flight; the flags alone are enough to redraw at the old geometry.
        panels.forEach(p => { p.halfTile = resolved; });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // v0.10.8: the snapshot must wait for the server's rebuilt layer.
        // Setting halfTile resizes every panel, and that rebuild only happens
        // server-side, so a saveState() taken here would pair the new flags
        // with full-size geometry. Undo restored that mismatch and PUT it back
        // to /api/project, which does no rebuild — making the corruption
        // permanent. Merge the response first, snapshot second.
        let applied = false;
        try {
            const res = await fetch(`/api/layer/${layerId}/panels/set_half_tile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data && data.layer) {
                applied = this.applyServerLayer(data.layer, 'bulk_set_half_tile');
                if (window.canvasRenderer) window.canvasRenderer.render();
            }
        } catch (err) {
            console.error('setPanelsHalfTileBulk failed', err);
        }
        // No rebuilt layer means no trustworthy snapshot to take. Skip the
        // history entry rather than record the stale-geometry one; the socket
        // `layer_updated` event still reconciles the live state.
        if (applied) this.saveState('Bulk Set Half-tile');
        sendClientLog && sendClientLog('bulk_set_half_tile', {
            layer_id: layerId,
            count: panels.length,
            mode: halfTile,
        });
    }

    /**
     * Bulk hide/show panels, what the UI calls "Set Blank" (matching the
     * Alt+click behaviour, which toggles the per-panel `hidden` flag so the
     * cabinet disappears from the wall layout).
     */
    async setPanelsBlankBulk(panels, blank) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        const targetHidden = !!blank;
        const toChange = panels.filter(p => !!p.hidden !== targetHidden);
        if (toChange.length === 0) return;
        // Apply locally so the canvas updates immediately while the server PUT is in flight.
        toChange.forEach(p => { p.hidden = targetHidden; });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // v0.10.8.1: same contract as setPanelsHalfTileBulk above. Hiding a
        // panel re-anchors any neighbouring half-tile, and that rebuild only
        // happens server-side, so a saveState() taken here would snapshot the
        // old geometry. Merge the response first, snapshot second.
        let applied = false;
        try {
            const res = await fetch(`/api/layer/${layerId}/panels/set_hidden`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ panels: toChange.map(p => ({ id: p.id, hidden: targetHidden })) }),
            });
            const data = await res.json();
            if (data && data.layer) {
                applied = this.applyServerLayer(data.layer, 'bulk_set_blank');
                if (window.canvasRenderer) window.canvasRenderer.render();
            }
        } catch (err) {
            console.error('setPanelsBlankBulk failed', err);
        }
        // No rebuilt layer means no trustworthy snapshot to take. Skip the
        // history entry rather than record the stale-geometry one; the socket
        // `layer_updated` event still reconciles the live state.
        if (applied) this.saveState('Bulk Set Blank');
        sendClientLog && sendClientLog('bulk_set_blank', {
            layer_id: layerId,
            count: toChange.length,
            hidden: targetHidden,
        });
    }

    /**
     * Update the sidebar bulk-action panel based on current selection.
     * Shows count + action buttons when at least one panel is selected,
     * hides when empty.
     */
    updatePixelMapBulkActionUI() {
        const panel = document.getElementById('pixel-map-bulk-actions');
        if (!panel) return;
        const count = this.pixelMapSelection ? this.pixelMapSelection.size : 0;
        const countEl = document.getElementById('pixel-map-bulk-count');
        // Wrap label too so we can fix pluralization without rebuilding markup.
        const labelEl = document.getElementById('pixel-map-bulk-label');
        if (count > 0) {
            panel.style.display = 'block';
            if (countEl) countEl.textContent = count.toLocaleString();
            if (labelEl) labelEl.textContent = count === 1 ? 'panel' : 'panels';
        } else {
            panel.style.display = 'none';
        }
    }

    selectPowerPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomPower(layer)) return;
        this.powerCustomSelection.clear();
        const off = this._getLayerWorkspaceOffset(layer);
        const minX = Math.min(rect.x1, rect.x2) - off.wx;
        const maxX = Math.max(rect.x1, rect.x2) - off.wx;
        const minY = Math.min(rect.y1, rect.y2) - off.wy;
        const maxY = Math.max(rect.y1, rect.y2) - off.wy;
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.powerCustomSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    /**
     * Find the OTHER port number (if any) that already owns this panel in
     * the layer's custom data-flow paths. Returns the conflicting port's
     * number, or null if the panel is unassigned (or only assigned to the
     * caller-supplied excludePortNum, which we treat as "not a conflict").
     */
    _findPanelOwnerPort(layer, panel, excludePortNum) {
        if (!layer || !layer.customPortPaths || !panel) return null;
        const key = `${panel.row},${panel.col}`;
        for (const portNumStr of Object.keys(layer.customPortPaths)) {
            const portNum = Number(portNumStr) || portNumStr;
            if (portNum === excludePortNum) continue;
            const path = layer.customPortPaths[portNumStr] || [];
            if (path.some(p => `${p.row},${p.col}` === key)) return portNum;
        }
        return null;
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum) {
        if (!layer || !layer.powerCustomPaths || !panel) return null;
        const key = `${panel.row},${panel.col}`;
        for (const circuitNumStr of Object.keys(layer.powerCustomPaths)) {
            const circuitNum = Number(circuitNumStr) || circuitNumStr;
            if (circuitNum === excludeCircuitNum) continue;
            const path = layer.powerCustomPaths[circuitNumStr] || [];
            if (path.some(p => `${p.row},${p.col}` === key)) return circuitNum;
        }
        return null;
    }

    addPanelToCustomPath(panel) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size > 0) return;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        if (!this.currentLayer.customPortPaths[portNum]) this.currentLayer.customPortPaths[portNum] = [];
        const key = this.getPanelKey(panel);
        const exists = this.currentLayer.customPortPaths[portNum].some(p => `${p.row},${p.col}` === key);
        if (exists) return;
        // Reject if the panel already belongs to a different port, user
        // must clear the existing assignment first. Avoids silent
        // double-mapping that the user has to undo manually.
        const conflict = this._findPanelOwnerPort(this.currentLayer, panel, portNum);
        if (conflict !== null) {
            if (typeof this._toast === 'function') {
                this._toast(`Panel R${panel.row + 1}C${panel.col + 1} is already wired to port ${conflict}. Clear it from port ${conflict} first.`, true);
            }
            return;
        }
        this.currentLayer.customPortPaths[portNum].push({ row: panel.row, col: panel.col });
        this.saveState('Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel port assignments persist.
        this.updateLayers(this.getSelectedLayers());
        if (this.customDebug) {
            console.log('[CustomFlow] Add panel', { portNum, row: panel.row, col: panel.col });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
    }

    addPanelToCustomPowerPath(panel) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size > 0) return;
        this.ensureCustomPowerState(this.currentLayer);
        const circuitNum = this.currentLayer.powerCustomIndex || 1;
        if (!this.currentLayer.powerCustomPaths[circuitNum]) this.currentLayer.powerCustomPaths[circuitNum] = [];
        const key = this.getPanelKey(panel);
        const exists = this.currentLayer.powerCustomPaths[circuitNum].some(p => `${p.row},${p.col}` === key);
        if (exists) return;
        const conflict = this._findPanelOwnerCircuit(this.currentLayer, panel, circuitNum);
        if (conflict !== null) {
            if (typeof this._toast === 'function') {
                this._toast(`Panel R${panel.row + 1}C${panel.col + 1} is already wired to circuit ${conflict}. Clear it from circuit ${conflict} first.`, true);
            }
            return;
        }
        this.currentLayer.powerCustomPaths[circuitNum].push({ row: panel.row, col: panel.col });
        this.saveState('Power Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel circuit assignments persist.
        this.updateLayers(this.getSelectedLayers());
        if (this.powerCustomDebug) {
            console.log('[CustomPower] Add panel', { circuitNum, row: panel.row, col: panel.col });
        }
        window.canvasRenderer.render();
    }

    handleCustomArrowKey(e) {
        const dir = e.code;
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(dir)) return false;
        if (!this.currentLayer) return false;
        const isPower = window.canvasRenderer && window.canvasRenderer.viewMode === 'power';
        if (isPower) {
            if (!this.isCustomPower(this.currentLayer)) return false;
            this.ensureCustomPowerState(this.currentLayer);
            const circuitNum = this.currentLayer.powerCustomIndex || 1;
            const path = this.currentLayer.powerCustomPaths[circuitNum] || [];
            if (path.length === 0) return false;
            const last = path[path.length - 1];
            let nextRow = last.row;
            let nextCol = last.col;
            if (dir === 'ArrowUp') nextRow -= 1;
            if (dir === 'ArrowDown') nextRow += 1;
            if (dir === 'ArrowLeft') nextCol -= 1;
            if (dir === 'ArrowRight') nextCol += 1;
            const panel = this.getPanelByRowCol(this.currentLayer, nextRow, nextCol);
            if (!panel || panel.hidden) return true;
            this.addPanelToCustomPowerPath(panel);
            return true;
        }
        if (!this.isCustomFlow(this.currentLayer)) return false;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = this.currentLayer.customPortPaths[portNum] || [];
        if (path.length === 0) return false;
        const last = path[path.length - 1];
        let nextRow = last.row;
        let nextCol = last.col;
        if (dir === 'ArrowUp') nextRow -= 1;
        if (dir === 'ArrowDown') nextRow += 1;
        if (dir === 'ArrowLeft') nextCol -= 1;
        if (dir === 'ArrowRight') nextCol += 1;
        const panel = this.getPanelByRowCol(this.currentLayer, nextRow, nextCol);
        if (!panel || panel.hidden) return true;
        this.addPanelToCustomPath(panel);
        return true;
    }

    applyPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size === 0) return;

        this.ensureCustomFlowState(this.currentLayer);
        const selectedPanels = this.currentLayer.panels
            .filter(panel => this.customSelection.has(this.getPanelKey(panel)) && !panel.hidden);
        if (selectedPanels.length === 0) return;

        const uniqueRows = [...new Set(selectedPanels.map(p => p.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(selectedPanels.map(p => p.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const normalizedGrid = Array.from({ length: uniqueRows.length }, () => Array(uniqueCols.length).fill(null));
        selectedPanels.forEach(panel => {
            const r = rowIndex.get(panel.row);
            const c = colIndex.get(panel.col);
            normalizedGrid[r][c] = panel;
        });

        const ordered = this.getPatternOrderForGrid(pattern, normalizedGrid);
        if (ordered.length === 0) return;

        const portNum = this.currentLayer.customPortIndex || 1;
        // Reject the entire pattern apply if any selected panel already
        // belongs to a different port. Prevents silent double-mapping.
        const conflicts = [];
        for (const p of ordered) {
            const owner = this._findPanelOwnerPort(this.currentLayer, p, portNum);
            if (owner !== null) conflicts.push({ row: p.row, col: p.col, owner });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `R${c.row + 1}C${c.col + 1}→port ${c.owner}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ports, ${sample}${more}.`, true);
            }
            return;
        }
        this.currentLayer.customPortPaths[portNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        this.updateLayers(this.getSelectedLayers());
        if (this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomFlow] Apply pattern', {
                pattern,
                portNum,
                count: ordered.length,
                gridRows: normalizedGrid.length,
                gridCols: normalizedGrid[0] ? normalizedGrid[0].length : 0,
                first: first ? { row: first.row, col: first.col } : null,
                last: last ? { row: last.row, col: last.col } : null
            });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
    }

    applyPowerPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size === 0) return;

        this.ensureCustomPowerState(this.currentLayer);
        const selectedPanels = this.currentLayer.panels
            .filter(panel => this.powerCustomSelection.has(this.getPanelKey(panel)) && !panel.hidden);
        if (selectedPanels.length === 0) return;

        const uniqueRows = [...new Set(selectedPanels.map(p => p.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(selectedPanels.map(p => p.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const normalizedGrid = Array.from({ length: uniqueRows.length }, () => Array(uniqueCols.length).fill(null));
        selectedPanels.forEach(panel => {
            const r = rowIndex.get(panel.row);
            const c = colIndex.get(panel.col);
            normalizedGrid[r][c] = panel;
        });

        const ordered = this.getPatternOrderForGrid(pattern, normalizedGrid);
        if (ordered.length === 0) return;

        const circuitNum = this.currentLayer.powerCustomIndex || 1;
        // Reject if any selected panel already belongs to a different
        // circuit, same policy as data-flow custom pattern apply.
        const conflicts = [];
        for (const p of ordered) {
            const owner = this._findPanelOwnerCircuit(this.currentLayer, p, circuitNum);
            if (owner !== null) conflicts.push({ row: p.row, col: p.col, owner });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `R${c.row + 1}C${c.col + 1}→circuit ${c.owner}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other circuits, ${sample}${more}.`, true);
            }
            return;
        }
        this.currentLayer.powerCustomPaths[circuitNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Power Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        this.updateLayers(this.getSelectedLayers());
        if (this.powerCustomDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomPower] Apply pattern', {
                pattern,
                circuitNum,
                count: ordered.length,
                gridRows: normalizedGrid.length,
                gridCols: normalizedGrid[0] ? normalizedGrid[0].length : 0,
                first: first ? { row: first.row, col: first.col } : null,
                last: last ? { row: last.row, col: last.col } : null
            });
        }
        window.canvasRenderer.render();
    }

    getPatternOrderForGrid(pattern, grid) {
        const rows = grid.length;
        const cols = rows > 0 ? grid[0].length : 0;
        if (rows === 0 || cols === 0) return [];

        const [startCorner, direction] = pattern.split('-');
        let startRow, startCol, rowDir, colDir;

        switch (startCorner) {
            case 'tl':
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1; break;
            case 'tr':
                startRow = 0; startCol = cols - 1; rowDir = 1; colDir = -1; break;
            case 'bl':
                startRow = rows - 1; startCol = 0; rowDir = -1; colDir = 1; break;
            case 'br':
                startRow = rows - 1; startCol = cols - 1; rowDir = -1; colDir = -1; break;
            default:
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1;
        }

        const ordered = [];
        const isVerticalFirst = (direction === 'v');

        if (isVerticalFirst) {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const shouldReverse = colOffset % 2 === 1;
                if (shouldReverse) {
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                }
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const shouldReverse = rowOffset % 2 === 1;
                if (shouldReverse) {
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                }
            }
        }

        return ordered;
    }
    
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

            // Single click to select
            layerDiv.addEventListener('click', (e) => {
                if (!e.target.classList.contains('layer-btn') && !e.target.classList.contains('layer-name-input')) {
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

            // Right-click context menu on layer list
            layerDiv.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isToggle = e.metaKey || e.ctrlKey;
                if (isToggle) {
                    this.toggleLayerSelection(layer);
                } else {
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
            
            // Handle name input: single-click selects layer, double-click edits name
            const nameInput = layerDiv.querySelector('.layer-name-input');
            nameInput.readOnly = true;
            nameInput.draggable = true;
            nameInput.style.cursor = 'default';
            nameInput.addEventListener('dragstart', handleDragStart);

            const enterEditMode = () => {
                nameInput.readOnly = false;
                nameInput.draggable = false;
                nameInput.style.cursor = 'text';
                // v0.10.9: class, not inline - theme.css styles .layer-name-input
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
                    fetch(`/api/layer/${layer.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                    });
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

        this.updateLayerOrderControls();
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

for (const k of Object.getOwnPropertyNames(_Power.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Power.prototype, k));
    }
}
