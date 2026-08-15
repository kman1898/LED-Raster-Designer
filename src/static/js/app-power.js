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
        // v0.11.0: screen-group actions. Grouping needs 2+ screen layers
        // selected, so with fewer the item is simply not offered (a group of
        // one is not a group). Ungroup / Remove only mean anything once the
        // selection is already in a group.
        const canGroup = this.canGroupSelection();
        const inGroup = this.getSelectedGroupIds().length > 0;
        menu.querySelectorAll('.group-create-only').forEach(el => {
            el.style.display = canGroup ? '' : 'none';
        });
        menu.querySelectorAll('.group-member-only').forEach(el => {
            el.style.display = inGroup ? '' : 'none';
        });
        menu.querySelectorAll('.group-any-only').forEach(el => {
            el.style.display = (canGroup || inGroup) ? '' : 'none';
        });
        // Move to Canvas needs a layer to move and somewhere to move it to.
        // Offering it with one canvas would open a picker with nothing in it.
        const canvases = (this.project && this.project.canvases) || [];
        const canMove = canvases.length > 1
            && this.getSelectedLayers().some(l => !l.locked);
        menu.querySelectorAll('.move-canvas-only').forEach(el => {
            el.style.display = canMove ? '' : 'none';
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
    
    // v0.11.0: Enable + highlight the Organized / Max Capacity buttons from the
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

        // v0.11.0: the theme styles .mapping-mode-btn / .mapping-mode-btn.active
        // with !important, so the .active class is the ONLY thing that can move
        // the highlight. Inline background/color writes here were dead.
        mappingOrgBtn.classList.toggle('active', isOrganized);
        mappingMaxBtn.classList.toggle('active', !isOrganized);
    }

    // Update the port capacity display in the UI
    updatePortCapacityDisplay() {
        // v0.11.0: run the button pass FIRST. It used to sit at the end of this
        // function, behind the early returns below (no current layer / image
        // layer), so the buttons could latch into a stale state.
        this.updatePortMappingButtons();
        // v0.11.0: same reasoning - the Low Latency control and its note must
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
            // v0.11.0: a healthy figure renders in the ordinary text colour on
            // .value-normal, so it cannot be mistaken for a fault; the warning
            // colour is the only inline override and the only colour here.
            if (portCapacity > 0) {
                capacityEl.textContent = portCapacity.toLocaleString();
                capacityEl.classList.add('value-normal');
                capacityEl.style.color = '';
                capacityEl.title = '';
            } else {
                capacityEl.textContent = 'N/A';
                capacityEl.classList.remove('value-normal');
                capacityEl.style.color = '#ff6600';
                // v0.11.0 audit: say WHY there is no figure when the reason is
                // knowable. A frame rate the manufacturer does not publish for
                // this processor used to be answered with the nearest row's
                // capacity - on Armor, 240 Hz got the 120 Hz figure, double the
                // truth - and nothing is extrapolated to replace it, so the
                // readout has to name the fix rather than just go blank.
                const rates = (typeof this.getSupportedFrameRates === 'function')
                    ? this.getSupportedFrameRates(processorType, bitDepth) : [];
                capacityEl.title = (rates.length > 0 && frameRate > rates[rates.length - 1])
                    ? `${processorType} publishes no ${frameRate} Hz figure at `
                      + `${bitDepth}-bit. Published frame rates: `
                      + `${rates.join(', ')} Hz.`
                    : '';
            }
        }

        const panelPixels = this.getFullPanelPixels(this.currentLayer);
        const panelsPerPort = (portCapacity > 0 && panelPixels > 0) ? Math.floor(portCapacity / panelPixels) : 0;
        
        const panelsPerPortEl = document.getElementById('panels-per-port');
        if (panelsPerPortEl) {
            if (panelsPerPort < 1) {
                panelsPerPortEl.textContent = 'ERROR';
                panelsPerPortEl.classList.remove('value-normal');
                panelsPerPortEl.style.color = '#ff0000';
            } else {
                panelsPerPortEl.textContent = panelsPerPort.toLocaleString();
                panelsPerPortEl.classList.add('value-normal');
                panelsPerPortEl.style.color = '';
            }
        }
        
        // Calculate total ports required from assignments
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const visiblePanels = this.currentLayer.panels ? this.currentLayer.panels.filter(p => !p.hidden).length : 0;
        const panelCountForStatus = usesRectangle && this.currentLayer.panels ? this.currentLayer.panels.length : visiblePanels;
        const assignments = this.calculatePortAssignments(this.currentLayer);
        // v0.11.0: calculatePortAssignments is the only thing that knows where
        // each Low Latency port sits, so it hands back the derate for the note.
        this.setLowLatencyDerateNote(this.currentLayer._lowLatencyDerate);
        // v0.11.0 step 6: one group-aware implementation, shared with the
        // group roll-up and the canvas label, so a port that spans two members
        // cannot read as two different numbers in three places. `assignments`
        // is handed straight through - it was just computed above for the
        // derate note, and re-walking it would be pure waste.
        const portsRequired = this.getLayerPortsRequired(this.currentLayer, assignments);
        this.currentLayer._portsRequired = portsRequired;
        // debug toggle removed
        const portsRequiredEl = document.getElementById('ports-required');
        if (portsRequiredEl) {
            // v0.11.0 audit: no capacity at all is an ERROR here too. Without
            // this, a screen whose processor publishes no figure for its frame
            // rate showed "N/A" pixels/port, "ERROR" panels/port and then a
            // calm green 0 next to Ports Required - and 0 ports reads as "none
            // needed", which is the one thing it does not mean.
            const noCapacity = !(portCapacity > 0) && panelCountForStatus > 0;
            if ((this.currentLayer._capacityError || noCapacity
                    || (portsRequired === 0 && panelsPerPort > 0 && panelCountForStatus > 0))) {
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
        // v0.11.0 audit fix: `!p.blank` as well as `!p.hidden`. This filter used
        // to drop hidden cabinets only, so a 2 x 2 screen with one cabinet
        // blanked read 800 W here and 600 W in the group roll-up and the
        // project totals - GROUPING A SCREEN CHANGED ITS WATTAGE. A blank is a
        // hole in the wall: no cabinet hangs there, it has no weight and it
        // draws nothing. Matches getGroupTotals, getPowerCounts and the canvas
        // weight label.
        const activePanels = layer.panels ? layer.panels.filter(p => !p.blank && !p.hidden) : [];
        const equivalentPanels = activePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
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

    // The label this port takes off the processor, or null when it takes none
    // - which is every port of every project that defines no processor.
    //
    // Split out from getPortLabelText only so the label editor can ask the
    // same question without re-deriving it: it needs to know not just what the
    // label is but where it came from, because a box the user can type in that
    // no longer changes the drawing is a trap.
    getProcessorPortLabel(layer, portNum) {
        const onProcessor = this._processorPortLabels
            && this._processorPortLabels[String(layer && layer.id)];
        return (onProcessor && onProcessor[portNum]) || null;
    }

    // The one place a port's label is decided. The canvas, both label editors
    // and every export come through here, so a rule added here reaches all of
    // them at once - and a second path added anywhere else would print one
    // thing on screen and another on the PDF.
    getPortLabelText(layer, portNum, type) {
        // THE PROCESSOR NAMES ITS OWN PORTS, AND IT WINS OUTRIGHT.
        //
        // A port that is assigned to a sending-card port takes that port's
        // label - the name on the card or the box a tech is standing in front
        // of - and no per-layer override applies to it. That is the point of
        // the Processors panel: the wall labels itself off the machine driving
        // it instead of off a template typed into every screen. The way to
        // change an assigned port's label is to rename the port, or the card,
        // in the Processors panel; both ends of the run take that name.
        //
        // BOTH ENDS, NOT THE SAME TEXT. A redundant loop leaves the socket and
        // comes back to it, so the two ends print at opposite corners of the
        // wall and the drawing is the only thing saying which is which. Two
        // labels reading SR-1 make a backup run impossible to trace, which is
        // the one job the return label has. It is the primary with an R after
        // it - SR-1 out, SR-1R back - so the socket is still named once and the
        // return is still the return, which is what P1 / R1 said before a
        // processor was naming anything.
        //
        // _processorPortLabels is a flat layerId -> portNum -> label lookup,
        // rebuilt only when the assignment changes (see _indexAssignmentLabels
        // in app-port-assignment.js). This runs for every port of every screen
        // on every frame, so it must never resolve anything itself.
        const assigned = this.getProcessorPortLabel(layer, portNum);
        if (assigned) return type === 'return' ? `${assigned}R` : assigned;

        // No processor in the project, or a port that is not on one: exactly
        // what every project did before processors existed, override included.
        // This is the fallback that keeps drawings already issued printing the
        // labels they were issued with.
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

    // Keep the caret where the user put it across an editor rebuild.
    //
    // Editing a label and pressing Tab fires the input's `change` handler,
    // which PUTs to the server. The browser moves focus to the NEXT input
    // immediately; the rebuild (`list.innerHTML = ''`) only happens a
    // round-trip later, when the response - or the socket `layer_updated`
    // echo - lands. By then the field the user is typing in is the one the
    // rebuild destroys, so focus falls to <body> and the next keystroke goes
    // nowhere. Pressing Tab again appears to work only because an unedited
    // field fires no `change` and nothing rebuilds.
    //
    // Capture the focused field's stable key plus its caret, then restore in
    // a microtask: that runs after the synchronous rebuild whichever return
    // path the builder takes, and does not care which of the two triggers
    // fired.
    _preserveEditorFocus() {
        const active = document.activeElement;
        const key = active && active.dataset ? active.dataset.lrdField : null;
        if (!key) return;
        let start = null;
        let end = null;
        try {
            start = active.selectionStart;
            end = active.selectionEnd;
        } catch (_) {
            // Not every input type exposes a selection (number, color, ...).
            start = null;
            end = null;
        }
        Promise.resolve().then(() => {
            const el = document.querySelector(`[data-lrd-field="${key}"]`);
            // Gone - the port/circuit count shrank out from under it. Leave
            // focus alone rather than throwing.
            if (!el || el === document.activeElement) return;
            try {
                el.focus();
            } catch (_) {
                return;
            }
            if (start === null || typeof el.setSelectionRange !== 'function') return;
            try {
                el.setSelectionRange(start, end);
            } catch (_) { /* selection unsupported on this element */ }
        });
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
        this._preserveEditorFocus();
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
            // Tab out of a port's Return field lands on the NEXT row's
            // checkbox, so it needs a stable key too or the rebuild drops it.
            cb.dataset.lrdField = `port-check-${portNum}`;
            cb.title = `Port ${portNum}`;
            cb.style.margin = '0';

            const numLabel = document.createElement('div');
            numLabel.style.fontSize = '13px';
            numLabel.style.fontWeight = '700';
            numLabel.style.color = '#ccc';
            numLabel.style.textAlign = 'center';
            numLabel.style.fontFamily = 'monospace';
            numLabel.textContent = String(portNum);

            // An assigned port takes its name off the processor and nothing
            // typed here reaches it. Say so on the row rather than leaving two
            // boxes that accept text and change nothing on the drawing - the
            // place to rename an assigned port is its row in the Processors
            // panel. The boxes stay editable because what is in them is still
            // the fallback the moment the processor stops naming the port.
            const fromProcessor = this.getProcessorPortLabel(this.currentLayer, portNum);
            const ownedNote = fromProcessor
                ? `Port ${portNum} is on the processor, which names it `
                  + `${fromProcessor} and its return ${fromProcessor}R. Rename `
                  + `it in the Processors panel. What you type here is kept, `
                  + `and draws again only if this port stops being assigned.`
                : '';
            if (fromProcessor) {
                numLabel.style.color = '#c8a04a';
                numLabel.title = ownedNote;
            }

            const primaryInput = document.createElement('input');
            primaryInput.type = 'text';
            // Stable identity across rebuilds, so focus + caret can be
            // restored into the same field after list.innerHTML = ''.
            primaryInput.dataset.lrdField = `port-primary-${portNum}`;
            if (ownedNote) primaryInput.title = ownedNote;
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
            returnInput.dataset.lrdField = `port-return-${portNum}`;
            if (ownedNote) returnInput.title = ownedNote;
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

        // v0.11.0 step 6: same single implementation the ports readout now
        // uses - a circuit drawn across two members is one circuit, and the
        // editor must offer exactly that many label rows.
        const circuitsRequired = this.getLayerCircuitsRequired(this.currentLayer);

        this._preserveEditorFocus();
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
            // Tab out of a circuit's label field lands here, on the next
            // row's checkbox - the first thing the rebuild destroys.
            cb.dataset.lrdField = `power-check-${circuitNum}`;
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
            input.dataset.lrdField = `power-label-${circuitNum}`;
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
        this._preserveEditorFocus();
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
            cb.dataset.lrdField = `power-circuit-color-${letter}`;

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
        // Only while the DATA view is the one on screen. There is one canvas
        // cursor and both this and updateCustomPowerUI were writing it from
        // their own pattern with no view test, so whichever ran last won -
        // and loadLayerToInputs runs the power one second. A screen with
        // custom data flow and automatic power (the normal state for a
        // grouped screen, since the flow pattern is shared across members but
        // power need not be) lost its crosshair in Data Flow the moment the
        // layer was re-selected, while custom drawing was still active.
        if (window.canvasRenderer && window.canvasRenderer.viewMode === 'data-flow') {
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
        // Power view only - see the note on the same line in
        // updateCustomFlowUI. Unguarded, this one always won.
        if (window.canvasRenderer && window.canvasRenderer.viewMode === 'power') {
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

    // v0.11.0: customSelection is keyed by getScopedPanelKey, not getPanelKey -
    // see _selectPathPanelsInRect for why. `panelLayer` names the screen the
    // cabinet came from when it is not currentLayer; leaving it out resolves
    // it, so every existing single-screen caller is unchanged.
    togglePanelSelection(panel, panelLayer = null) {
        if (!panel) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer) || owner;
        if (!source) return;
        const key = this.getScopedPanelKey(source.id, panel);
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

    // The power-side twin. canvas.js used to clear powerCustomSelection inline
    // and separately remember to refresh the UI and re-render; the data side
    // has had this helper all along.
    clearPowerCustomSelection() {
        this.powerCustomSelection.clear();
        this.updateCustomPowerUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    /**
     * Marquee-select the cabinets under `rect` for a manual path owned by
     * `ownerLayer`, filling `selection` with SCOPED keys.
     *
     * v0.11.0: the marquee now sweeps every member of the owner's group, the
     * same reachability rule click-to-add uses. Before this it walked one
     * layer, which is why dragging a box across a mixed-cabinet wall picked up
     * only half of it.
     *
     * The Set has to be keyed by getScopedPanelKey and not getPanelKey:
     * member A's R0C0 and member B's R0C0 are two different cabinets, and under
     * the bare `${row},${col}` they are ONE entry - so a cross-member marquee
     * could only ever have committed the owner's own cabinets under the peer's
     * row and column. Silently wrong, not partly working. getPanelKey itself is
     * untouched, because pixelMapSelection still uses it (one screen, no
     * groups) and its overlay still parses it back with split(',').
     *
     * Each member converts the WORLD rect into its OWN frame:
     * _getLayerWorkspaceOffset is per-layer (canvas workspace + that layer's
     * Show Look delta), and rotation is undone per member the way
     * selectPixelMapPanelsInRect and canvas.js getPanelAt do it. Note the
     * members of one canvas already share an origin - _build_panels lays each
     * member's columns out from its own offset_x - so there is no second offset
     * to apply on top of that, and applying one would drag the peer's hit-test
     * off the wall.
     */
    _selectPathPanelsInRect(ownerLayer, rect, selection) {
        selection.clear();
        if (!ownerLayer || !rect) return;
        const _r = window.canvasRenderer;
        // Selection scope, not path scope: a marquee must not sweep up a
        // member the user cannot see or click. See getSelectionScopeLayers.
        this.getSelectionScopeLayers(ownerLayer).forEach(member => {
            if (!member || !Array.isArray(member.panels)) return;
            const off = this._getLayerWorkspaceOffset(member);
            let x1 = Math.min(rect.x1, rect.x2) - off.wx;
            let x2 = Math.max(rect.x1, rect.x2) - off.wx;
            let y1 = Math.min(rect.y1, rect.y2) - off.wy;
            let y2 = Math.max(rect.y1, rect.y2) - off.wy;
            // Rotation is 90/180/270 only, so the unrotated rect is still
            // axis-aligned and the corners bound it exactly.
            if (_r && typeof _r._unrotatePointForLayer === 'function') {
                const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                    .map(([x, y]) => _r._unrotatePointForLayer(x, y, member));
                x1 = Math.min(...corners.map(c => c.x)); x2 = Math.max(...corners.map(c => c.x));
                y1 = Math.min(...corners.map(c => c.y)); y2 = Math.max(...corners.map(c => c.y));
            }
            member.panels.forEach(panel => {
                if (panel.hidden) return;
                const intersects = panel.x <= x2 && (panel.x + panel.width) >= x1 &&
                    panel.y <= y2 && (panel.y + panel.height) >= y1;
                if (intersects) selection.add(this.getScopedPanelKey(member.id, panel));
            });
        });
    }

    // `layer` is the path's OWNER - the screen whose port is being drawn - and
    // its group decides how far the marquee reaches. The signature is
    // unchanged, so canvas.js still passes currentLayer.
    selectPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomFlow(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.customSelection);
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

    // Power's half of the marquee. Same scoping rule, same owner semantics -
    // see _selectPathPanelsInRect.
    selectPowerPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomPower(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.powerCustomSelection);
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    // ── Cross-member manual paths (v0.11.0, step 6) ──────────────────────
    //
    // A group IS ONE WALL, so a hand-drawn port path or power circuit has to
    // be allowed to run off one member and onto the next. The path itself
    // never moves: it stays on the layer that OWNS the port or circuit -
    // a port is a physical output on ONE processor - and only the individual
    // step learns where the cable landed.
    //
    //     {row, col}            a panel in the OWNING layer. Unchanged, and
    //                           the shape 100% of existing projects have.
    //     {row, col, layerId}   a panel in a PEER member of the same group.
    //
    // Why a key on the STEP rather than a new key on the layer: the server's
    // add / update allow-lists silently DROP layer keys they do not know,
    // which has already cost this codebase two features (processorType,
    // lowLatency). A step lives inside customPortPaths, which is already
    // allow-listed, so it rides in for free.
    //
    // Why (layerId, row, col) rather than panel.id: _build_panels regenerates
    // panel ids on every geometry rebuild, so an id is worthless the moment
    // anyone changes a column count. (row, col) is the only durable address.
    //
    // Every helper below returns the ungrouped answer for an ungrouped layer,
    // and a path with no layerId anywhere reads exactly as it did before, so a
    // project without groups takes precisely the code path it took before.

    // The canvas a manual path treats a layer as living on. Paths are only
    // ever drawn in Data Flow and Power, which are both Show Look views, so
    // the show override is the right answer REGARDLESS of which tab is open.
    // Deliberately NOT canvasRenderer._effectiveLayerCanvasId, which flips
    // with viewMode: reachability that changed the moment the user clicked the
    // Pixel Map tab would mean the same stored step resolving on one tab and
    // reading as dangling on another.
    _pathCanvasIdOf(layer) {
        if (!layer) return null;
        return layer.show_canvas_id || layer.canvas_id || null;
    }

    // Every layer a path owned by `layer` may legally touch. The owner is
    // always first, so callers that want "the owner, then its peers" get a
    // stable order without re-sorting.
    getPathScopeLayers(layer) {
        if (!layer) return [];
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return [layer];
        const cid = this._pathCanvasIdOf(layer);
        const scope = [layer];
        (this.getGroupMembers(group) || []).forEach(m => {
            if (!m || m.id === layer.id) return;
            if ((m.type || 'screen') !== 'screen') return;
            // The same rule canvas.js _groupDrawnMembers applies: a member
            // sitting on another canvas is a different workspace entirely, so
            // a cable drawn onto it would be drawn at a position that means
            // nothing. Hidden members are NOT excluded here (where
            // _groupDrawnMembers does exclude them) - hiding a screen must not
            // quietly invalidate paths the user already drew onto it, because
            // unhiding has to bring them straight back.
            if (this._pathCanvasIdOf(m) !== cid) return;
            scope.push(m);
        });
        return scope;
    }

    // The layers a SELECTION owned by `layer` may touch: the path scope, less
    // the members the user cannot see.
    //
    // getPathScopeLayers deliberately keeps hidden members, because a path
    // already drawn onto a screen must survive that screen being hidden and
    // come straight back when it is unhidden. That is right for RESOLVING a
    // path and wrong for BUILDING one: a hidden member is not drawn
    // (canvas.js _groupDrawnMembers filters visible !== false) and cannot be
    // clicked (getPanelAt skips it), so a marquee, an arrow handoff or an
    // Apply Pattern that reached it wired cabinets nobody could see - 12 of
    // them, on a screen that is not on the canvas, into the visible screen's
    // port 1.
    //
    // The OWNER is never filtered out. It is the layer the user is working on
    // and the port belongs to it; dropping it would make a hidden current
    // layer un-drawable rather than merely un-reachable, and it keeps an
    // ungrouped screen byte-identical to before.
    //
    // `visible === false`, not `!visible`: a layer with no visible key is
    // visible everywhere else in this app (the server reads
    // layer.get('visible', True)).
    getSelectionScopeLayers(layer) {
        if (!layer) return [];
        return this.getPathScopeLayers(layer)
            .filter(l => l && (l.id === layer.id || l.visible !== false));
    }

    canPathReachLayer(ownerLayer, targetLayer) {
        if (!ownerLayer || !targetLayer) return false;
        if (ownerLayer.id === targetLayer.id) return true;
        return this.getPathScopeLayers(ownerLayer).some(l => l && l.id === targetLayer.id);
    }

    // The layer id a step names, resolving the plain form to the owner. Kept
    // separate from resolvePathEntryLayer because the conflict scan wants the
    // id without paying for a lookup and a legality check per step.
    getPathEntryLayerId(ownerLayer, entry) {
        const lid = entry ? entry.layerId : undefined;
        if (lid === undefined || lid === null) return ownerLayer ? ownerLayer.id : null;
        return lid;
    }

    resolvePathEntryLayer(ownerLayer, entry) {
        if (!ownerLayer || !entry) return null;
        const lid = entry.layerId;
        if (lid === undefined || lid === null || lid === ownerLayer.id) return ownerLayer;
        const target = ((this.project && this.project.layers) || [])
            .find(l => l && l.id === lid) || null;
        if (!target) return null;
        // A pointer at a layer that exists but is no longer a reachable peer
        // (ungrouped, regrouped, or dragged onto another canvas) is dead, not
        // drawable. The server prunes it on the next round-trip; until then
        // reading it as null keeps the renderer from drawing a cable onto an
        // unrelated screen.
        return this.canPathReachLayer(ownerLayer, target) ? target : null;
    }

    resolvePathEntry(ownerLayer, entry) {
        const layer = this.resolvePathEntryLayer(ownerLayer, entry);
        if (!layer || !entry) return null;
        const panel = this.getPanelByRowCol(layer, entry.row, entry.col);
        if (!panel) return null;
        return { layer, panel };
    }

    // Hidden panels are dropped HERE rather than by each caller, matching the
    // read-time `.filter(p => p && !p.hidden)` every path consumer already ran
    // before a step could name a peer.
    getResolvedPathPanels(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return [];
        const out = [];
        path.forEach(entry => {
            const resolved = this.resolvePathEntry(ownerLayer, entry);
            if (resolved && !resolved.panel.hidden) out.push(resolved);
        });
        return out;
    }

    // layerId is written ONLY when it differs from the owner, so a path that
    // never leaves its own screen is byte-for-byte the shape it has always
    // been. (The server's prune pass normalises a self-pointer the same way,
    // so the two sides can never drift into writing different files.)
    makePathEntry(ownerLayer, panelLayer, panel) {
        if (!panel) return null;
        const entry = { row: panel.row, col: panel.col };
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            entry.layerId = panelLayer.id;
        }
        return entry;
    }

    // The address of ONE cabinet on the wall. Path ownership, path dedupe and
    // (since v0.11.0's marquee) customSelection / powerCustomSelection are all
    // keyed on this, because inside a group `${row},${col}` names two cabinets
    // at once and every one of those jobs has to tell them apart.
    //
    // getPanelKey stays `${row},${col}` regardless: pixelMapSelection still
    // uses it - one screen, nothing grouped about it - and its overlay parses
    // the key back with `key.split(',').map(parseInt)`, which a layer id in
    // front would turn into the WRONG panel silently, with no error anywhere.
    getScopedPanelKey(layerId, panel) {
        return `${layerId}:${panel.row},${panel.col}`;
    }

    pathCrossesMembers(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return false;
        return path.some(e => e && e.layerId !== undefined && e.layerId !== null
            && e.layerId !== ownerLayer.id);
    }

    // Which layer does this panel object belong to, as far as a path owned by
    // `ownerLayer` is concerned? Null when the panel is not reachable at all.
    // Identity first - the click handler and the arrow keys both hand us the
    // panel straight out of a layer's own array - and the (row, col) fallback
    // is what keeps a caller that rebuilt the panel behaving exactly as before.
    _resolvePathPanelLayer(ownerLayer, panel, explicitLayer) {
        if (!ownerLayer || !panel) return null;
        if (explicitLayer) {
            return this.canPathReachLayer(ownerLayer, explicitLayer) ? explicitLayer : null;
        }
        const scope = this.getPathScopeLayers(ownerLayer);
        const byIdentity = scope.find(l => l && Array.isArray(l.panels)
            && l.panels.includes(panel));
        if (byIdentity) return byIdentity;
        return this.getPanelByRowCol(ownerLayer, panel.row, panel.col) ? ownerLayer : null;
    }

    _pathLayerName(layer) {
        if (!layer) return 'another screen';
        return layer.name || `Screen ${layer.id}`;
    }

    // "port 2", or "port 2 on North Lower" when the conflict lives on a peer.
    // R3C4 alone stops meaning anything the moment two grids are in play, so
    // a toast that names only the number sends the user hunting.
    _describePathConflict(conflict, kind) {
        if (!conflict) return '';
        const base = `${kind} ${conflict.number}`;
        return conflict.foreign ? `${base} on ${this._pathLayerName(conflict.layer)}` : base;
    }

    _describePathPanel(ownerLayer, panelLayer, panel) {
        const base = `R${panel.row + 1}C${panel.col + 1}`;
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            return `${base} on ${this._pathLayerName(panelLayer)}`;
        }
        return base;
    }

    /**
     * Which port / circuit (if any) already owns this cabinet, anywhere in the
     * owner's path scope. Returns {number, layer, layerId, foreign} or null.
     *
     * `foreign` is the whole reason this returns an object rather than the
     * bare number it used to: with a group in play the answer may live on a
     * different screen, and the caller has to be able to say which.
     */
    _findPathOwner(ownerLayer, panel, excludeNum, panelLayer, pathsKey) {
        if (!ownerLayer || !panel) return null;
        const source = panelLayer || ownerLayer;
        const key = this.getScopedPanelKey(source.id, panel);
        for (const scope of this.getPathScopeLayers(ownerLayer)) {
            const paths = scope && scope[pathsKey];
            if (!paths) continue;
            for (const numStr of Object.keys(paths)) {
                // Number("0") is 0, which is falsy - the old `Number(s) || s`
                // handed back the STRING "0" and then failed to match a
                // numeric exclude. Ports and circuits are 1-based so it never
                // bit anyone, but a quirk that only works because a value is
                // impossible is a trap for whoever changes that.
                const parsed = Number(numStr);
                const num = Number.isFinite(parsed) ? parsed : numStr;
                // Only the port being drawn RIGHT NOW is exempt, and only on
                // its own layer: port 1 of member A and port 1 of member B are
                // two different physical outputs (getGroupTotals sums each
                // member's own requirement), so a cabinet already claimed by
                // the peer's port 1 genuinely is taken.
                if (scope.id === ownerLayer.id && num === excludeNum) continue;
                const path = paths[numStr] || [];
                const hit = path.some(e => e && this.getScopedPanelKey(
                    this.getPathEntryLayerId(scope, e), e) === key);
                if (hit) {
                    return {
                        number: num,
                        layer: scope,
                        layerId: scope.id,
                        foreign: scope.id !== ownerLayer.id,
                    };
                }
            }
        }
        return null;
    }

    /**
     * The OTHER port (if any) that already owns this panel. Scans every layer
     * in the owner's path scope, not just the owner's own paths, so a cabinet
     * claimed by a port drawn from member A is seen as taken while drawing
     * from member B.
     */
    _findPanelOwnerPort(layer, panel, excludePortNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludePortNum, panelLayer, 'customPortPaths');
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludeCircuitNum, panelLayer, 'powerCustomPaths');
    }

    /**
     * The layers a path edit has to PUT. updateLayers only sends what it is
     * handed (plus peers a shared-field edit left pending), and clicking a
     * peer member's cabinet writes onto currentLayer - which is not guaranteed
     * to be in the selection, since a marquee or a click on the peer alone can
     * leave it out. The owner is therefore added explicitly. Nothing else
     * changed, so nothing else is sent.
     */
    _pathPersistLayers(ownerLayer) {
        const layers = this.getSelectedLayers() || [];
        if (ownerLayer && !layers.some(l => l && l.id === ownerLayer.id)) {
            return layers.concat([ownerLayer]);
        }
        return layers;
    }

    /**
     * Append a cabinet to the active port's path. `panelLayer` names the
     * screen the cabinet came from when it is not currentLayer; leaving it out
     * resolves it, so every existing single-screen caller is unchanged.
     *
     * The PORT stays on currentLayer even when the user clicked a peer's
     * cabinet - a port is one physical output on one processor, and only the
     * step records which screen the cable ran onto.
     */
    addPanelToCustomPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomFlowState(owner);
        const portNum = owner.customPortIndex || 1;
        if (!owner.customPortPaths[portNum]) owner.customPortPaths[portNum] = [];
        // Scoped key, not getPanelKey: R0C0 of the owner and R0C0 of a peer
        // are two different cabinets, and a bare `${row},${col}` compare would
        // refuse to add the second one.
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.customPortPaths[portNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        // Reject if the panel already belongs to a different port, user
        // must clear the existing assignment first. Avoids silent
        // double-mapping that the user has to undo manually.
        const conflict = this._findPanelOwnerPort(owner, panel, portNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'port');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        owner.customPortPaths[portNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel port assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.customDebug) {
            console.log('[CustomFlow] Add panel', {
                portNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
    }

    addPanelToCustomPowerPath(panel, panelLayer = null) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size > 0) return;
        const owner = this.currentLayer;
        const source = this._resolvePathPanelLayer(owner, panel, panelLayer);
        if (!source) return;
        this.ensureCustomPowerState(owner);
        const circuitNum = owner.powerCustomIndex || 1;
        if (!owner.powerCustomPaths[circuitNum]) owner.powerCustomPaths[circuitNum] = [];
        const key = this.getScopedPanelKey(source.id, panel);
        const exists = owner.powerCustomPaths[circuitNum].some(e => e
            && this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e) === key);
        if (exists) return;
        const conflict = this._findPanelOwnerCircuit(owner, panel, circuitNum, source);
        if (conflict) {
            if (typeof this._toast === 'function') {
                const where = this._describePathConflict(conflict, 'circuit');
                this._toast(`Panel ${this._describePathPanel(owner, source, panel)} is already wired to ${where}. Clear it from ${where} first.`, true);
            }
            return;
        }
        owner.powerCustomPaths[circuitNum].push(this.makePathEntry(owner, source, panel));
        this.saveState('Power Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel circuit assignments persist.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.powerCustomDebug) {
            console.log('[CustomPower] Add panel', {
                circuitNum, row: panel.row, col: panel.col,
                layerId: source.id !== owner.id ? source.id : undefined,
            });
        }
        window.canvasRenderer.render();
    }

    /**
     * Where an arrow key takes the path from its current end.
     *
     * Returns `false` when there is nothing drawn yet (the key is NOT ours,
     * the caller lets it fall through), `null` when there is nowhere to go
     * (the key is swallowed, exactly as before), or {layer, panel}.
     */
    // Is the view this path is drawn in mirrored left-to-right?
    //
    // Rear perspective draws the canvas through ctx.scale(-1, 1), so world +X
    // appears on the viewer's LEFT. Anything that turns a user's intent into a
    // world-space direction has to account for that - the screen-name drag
    // already does (canvas.js, `_visualDx`).
    _pathViewIsMirrored(layer) {
        const cr = window.canvasRenderer;
        if (!cr || !layer || typeof cr._effectiveLayerCanvasId !== 'function') return false;
        if (typeof cr._isCanvasMirrored !== 'function') return false;
        const canvases = (this.project && this.project.canvases) || [];
        if (!Array.isArray(canvases)) return false;
        const cid = cr._effectiveLayerCanvasId(layer);
        const canvas = canvases.find(c => c && c.id === cid);
        return !!(canvas && cr._isCanvasMirrored(canvas));
    }

    _stepPathFromLastEntry(ownerLayer, path, dir) {
        if (!Array.isArray(path) || path.length === 0) return false;
        const last = this.resolvePathEntry(ownerLayer, path[path.length - 1]);
        if (!last) return null;
        const drow = dir === 'ArrowUp' ? -1 : (dir === 'ArrowDown' ? 1 : 0);
        let dcol = dir === 'ArrowLeft' ? -1 : (dir === 'ArrowRight' ? 1 : 0);
        // Issue #111: in Rear view the arrows walked the cable backwards -
        // Right went left and Left went right. The keys were never wrong; the
        // CANVAS is mirrored and the step was computed in unmirrored world
        // space. Flip the horizontal component so the cable follows the arrow
        // the user actually pressed. Vertical is unaffected: the mirror is
        // left-to-right only.
        //
        // Applied HERE rather than in handleCustomArrowKey so the cross-member
        // handoff below inherits it too - stepping off the right-hand edge in
        // Rear view has to look for the neighbour on the viewer's right.
        if (dcol !== 0 && this._pathViewIsMirrored(last.layer)) dcol = -dcol;
        // Step inside the END STEP'S OWN grid first. row/col are per-layer
        // indices, and this branch is byte-for-byte what the key did before.
        const within = this.getPanelByRowCol(
            last.layer, last.panel.row + drow, last.panel.col + dcol);
        if (within) return within.hidden ? null : { layer: last.layer, panel: within };
        // Grid edge. Before v0.11.0 the key was swallowed here with no feedback
        // at all, which inside a group is simply wrong: the wall continues, it
        // just continues on a different layer. Hand off GEOMETRICALLY, because
        // a member built from a different cabinet size has a completely
        // different index space - "row + 1" means nothing across the boundary
        // and only world coordinates do.
        return this._panelAcrossPathBoundary(ownerLayer, last, drow, dcol);
    }

    _panelAcrossPathBoundary(ownerLayer, from, drow, dcol) {
        if (!window.canvasRenderer || !from) return null;
        // An arrow key hands the cable to the cabinet the user can see next
        // door, so a hidden member is not a candidate - the same rule the
        // marquee and click-to-add follow. The hidden member's cabinets are
        // still where they were, so this walks PAST it exactly as it walks
        // past a gap: nothing is added and the key is swallowed.
        const peers = this.getSelectionScopeLayers(ownerLayer)
            .filter(l => l && l.id !== from.layer.id);
        if (peers.length === 0) return null;
        const p = from.panel;
        // Probe a hair PAST the edge we just walked off, centred on the other
        // axis. Aiming at "where the next cell would have been" instead would
        // land exactly on a shared cabinet boundary whenever the neighbouring
        // member's cabinets are a different size, and the hit-test is
        // inclusive at both edges - so it would be a coin flip which of the
        // peer's two cabinets answered.
        const eps = 1;
        const lx = p.x + (dcol > 0 ? p.width + eps : (dcol < 0 ? -eps : p.width / 2));
        const ly = p.y + (drow > 0 ? p.height + eps : (drow < 0 ? -eps : p.height / 2));
        const world = this._pathPointToWorld(from.layer, lx, ly);
        if (!world) return null;
        for (const peer of peers) {
            const local = this._pathPointFromWorld(peer, world.x, world.y);
            if (!local) continue;
            const hit = (peer.panels || []).find(q => local.x >= q.x
                && local.x <= q.x + q.width
                && local.y >= q.y && local.y <= q.y + q.height);
            if (hit) return hit.hidden ? null : { layer: peer, panel: hit };
        }
        return null;
    }

    // Layer space -> world, the exact inverse of canvas.js getPanelAt. The
    // offsets belong to the renderer, so they are CALLED here rather than
    // re-derived: a rotated or cross-canvas member would silently drift the
    // day one of them changed there and not here.
    _pathPointToWorld(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (!cr) return null;
        const r = this._rotatePathPoint(layer, lx, ly);
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return { x: r.x + dx + wx, y: r.y + dy + wy };
    }

    _pathPointFromWorld(layer, worldX, worldY) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr._unrotatePointForLayer !== 'function') return null;
        const { dx, dy } = cr.getLayerRenderOffset(layer);
        const { wx, wy } = cr._layerCanvasOffset(layer);
        return cr._unrotatePointForLayer(worldX - dx - wx, worldY - dy - wy, layer);
    }

    // Forward rotation. canvas.js ships the inverse (_unrotatePointForLayer)
    // and the pivot geometry (_layerRotationGeom) but not yet this direction;
    // the moment it grows a _rotatePointForLayer this picks it up instead, so
    // the two can never end up disagreeing about where a rotated screen's
    // cabinet actually sits.
    _rotatePathPoint(layer, lx, ly) {
        const cr = window.canvasRenderer;
        if (cr && typeof cr._rotatePointForLayer === 'function') {
            return cr._rotatePointForLayer(lx, ly, layer);
        }
        const g = (cr && typeof cr._layerRotationGeom === 'function')
            ? cr._layerRotationGeom(layer) : null;
        if (!g || (g.deg !== 90 && g.deg !== 180 && g.deg !== 270)) return { x: lx, y: ly };
        const rad = g.deg * Math.PI / 180;
        const cos = Math.cos(rad), sin = Math.sin(rad);
        const dx = lx - g.cx, dy = ly - g.cy;
        return { x: g.cx + (dx * cos - dy * sin), y: g.cy + (dx * sin + dy * cos) };
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
            const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
            if (next === false) return false;
            if (next) this.addPanelToCustomPowerPath(next.panel, next.layer);
            return true;
        }
        if (!this.isCustomFlow(this.currentLayer)) return false;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = this.currentLayer.customPortPaths[portNum] || [];
        const next = this._stepPathFromLastEntry(this.currentLayer, path, dir);
        if (next === false) return false;
        if (next) this.addPanelToCustomPath(next.panel, next.layer);
        return true;
    }

    // The wall lattice a pattern is ordered on. ONE implementation, and it is
    // the renderer's getPositionLattice - the same one the cabinet ID numbers
    // are assigned with (canvas.js _groupNumberingPlan). Two copies would
    // eventually disagree, and a serpentine that snakes the wall in a different
    // order than the IDs read is worse than no serpentine at all. It lives on
    // the renderer because the ranking needs getLayerRenderOffset.
    //
    // Null only when the renderer is missing entirely, and _orderPicksForPattern
    // then falls back to the panels' own row/col - the ordering this had before
    // v0.11.0. A degradation, deliberately, rather than a second lattice.
    _pathLattice(ownerLayer) {
        const cr = window.canvasRenderer;
        if (!cr || typeof cr.getPositionLattice !== 'function') return null;
        return cr.getPositionLattice(this.getPathScopeLayers(ownerLayer));
    }

    /**
     * The cabinets a scoped selection Set actually names, as {layer, panel}.
     *
     * Walked in path-scope order (owner first, then peers in group order) and
     * then in each member's own panel order, so an ungrouped screen yields the
     * exact list - and the exact order - the old `currentLayer.panels.filter()`
     * did. Hidden cabinets are dropped here, matching that filter.
     */
    _selectedPathPanels(ownerLayer, selection) {
        const out = [];
        if (!ownerLayer || !selection || selection.size === 0) return out;
        // Selection scope again, so a key that was already in the Set when its
        // screen was hidden cannot be committed by a later Apply Pattern. The
        // marquee is filtered at source; this is the same rule applied at the
        // moment of writing, which is the one that reaches the wall.
        this.getSelectionScopeLayers(ownerLayer).forEach(member => {
            if (!member || !Array.isArray(member.panels)) return;
            member.panels.forEach(panel => {
                if (panel.hidden) return;
                if (selection.has(this.getScopedPanelKey(member.id, panel))) {
                    out.push({ layer: member, panel });
                }
            });
        });
        return out;
    }

    /**
     * Put a cross-member selection into pattern order.
     *
     * The picks are placed on the WALL LATTICE (canvas.js getPositionLattice:
     * every member's column and row slots pooled and ranked by where they
     * physically sit), the lattice is compacted to just the rows and columns
     * the selection actually touches - exactly what the old uniqueRows /
     * uniqueCols pass did, only over positions rather than indices - and
     * getPatternOrderForGrid walks it. A serpentine therefore alternates
     * direction per LATTICE row and snakes across the whole wall instead of
     * per member.
     *
     * WHY position and not row/col indices. A 1m member's row 1 and a 0.5m
     * member's row 1 are different physical heights, so a pattern ordered by
     * the panels' own indices - which is what this did - zig-zags through an
     * order that exists nowhere on site. A cabinet spanning two lattice rows
     * ranks by its own top-left, exactly as step 5 numbers it.
     *
     * For a single ungrouped screen the lattice ranks that screen's own columns
     * by x and rows by y, which for any grid _build_panels produces is the
     * column and row index itself. The compacted grid is therefore identical
     * to the one this built before, and so is the order.
     *
     * The bucket is for genuinely OVERLAPPING members - two cabinets whose
     * top-left corners coincide land in one lattice cell. A plain grid write
     * would drop one of them from the path with no error; keeping the cell's
     * later arrivals and emitting them right behind the representative means a
     * selected cabinet can never silently vanish.
     */
    _orderPicksForPattern(ownerLayer, pattern, picks) {
        if (!picks || picks.length === 0) return [];
        const lattice = this._pathLattice(ownerLayer);
        const cells = picks.map(pick => ({
            pick,
            row: lattice ? lattice.rowOf(pick.layer, pick.panel) : pick.panel.row,
            col: lattice ? lattice.colOf(pick.layer, pick.panel) : pick.panel.col,
        }));

        const uniqueRows = [...new Set(cells.map(c => c.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(cells.map(c => c.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const grid = Array.from({ length: uniqueRows.length },
            () => Array(uniqueCols.length).fill(null));
        const bucket = new Map();   // representative pick -> every pick in its cell
        cells.forEach(c => {
            const r = rowIndex.get(c.row);
            const k = colIndex.get(c.col);
            const held = grid[r][k];
            if (held === null) {
                grid[r][k] = c.pick;
                bucket.set(c.pick, [c.pick]);
            } else {
                bucket.get(held).push(c.pick);
            }
        });

        const ordered = this.getPatternOrderForGrid(pattern, grid);
        const out = [];
        ordered.forEach(pick => {
            const group = bucket.get(pick);
            if (group) out.push(...group);
            else out.push(pick);
        });
        return out;
    }

    applyPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size === 0) return;

        // The PORT stays on currentLayer even when the selection spans peers -
        // a port is one physical output on one processor. Only the individual
        // step records which screen the cable ran onto.
        const owner = this.currentLayer;
        this.ensureCustomFlowState(owner);
        const picks = this._selectedPathPanels(owner, this.customSelection);
        if (picks.length === 0) return;

        const ordered = this._orderPicksForPattern(owner, pattern, picks);
        if (ordered.length === 0) return;

        const portNum = owner.customPortIndex || 1;
        // Reject the entire pattern apply if any selected panel already
        // belongs to a different port. Prevents silent double-mapping.
        const conflicts = [];
        for (const pick of ordered) {
            // The claim may live on a peer now, which is why the sample below
            // names both the cabinet's screen and the conflicting port's.
            const claim = this._findPanelOwnerPort(owner, pick.panel, portNum, pick.layer);
            if (claim) conflicts.push({ pick, owner: claim });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `${this._describePathPanel(owner, c.pick.layer, c.pick.panel)}→${this._describePathConflict(c.owner, 'port')}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ports, ${sample}${more}.`, true);
            }
            return;
        }
        // makePathEntry omits layerId for the owner's own cabinets, so a path
        // that never leaves its screen is byte-for-byte the shape it has always
        // been written in.
        owner.customPortPaths[portNum] = ordered
            .map(pick => this.makePathEntry(owner, pick.layer, pick.panel));
        this.saveState('Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        // v0.11.0: the OWNER is added explicitly - a marquee that ended on a
        // peer can leave currentLayer out of the layer selection entirely.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomFlow] Apply pattern', {
                pattern,
                portNum,
                count: ordered.length,
                first: first ? { row: first.panel.row, col: first.panel.col, layerId: first.layer.id } : null,
                last: last ? { row: last.panel.row, col: last.panel.col, layerId: last.layer.id } : null
            });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
    }

    applyPowerPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size === 0) return;

        // Same ownership rule as applyPatternToSelection: the CIRCUIT belongs
        // to currentLayer, only the step learns which screen it landed on.
        const owner = this.currentLayer;
        this.ensureCustomPowerState(owner);
        const picks = this._selectedPathPanels(owner, this.powerCustomSelection);
        if (picks.length === 0) return;

        const ordered = this._orderPicksForPattern(owner, pattern, picks);
        if (ordered.length === 0) return;

        const circuitNum = owner.powerCustomIndex || 1;
        // Reject if any selected panel already belongs to a different
        // circuit, same policy as data-flow custom pattern apply.
        const conflicts = [];
        for (const pick of ordered) {
            const claim = this._findPanelOwnerCircuit(owner, pick.panel, circuitNum, pick.layer);
            if (claim) conflicts.push({ pick, owner: claim });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `${this._describePathPanel(owner, c.pick.layer, c.pick.panel)}→${this._describePathConflict(c.owner, 'circuit')}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other circuits, ${sample}${more}.`, true);
            }
            return;
        }
        owner.powerCustomPaths[circuitNum] = ordered
            .map(pick => this.makePathEntry(owner, pick.layer, pick.panel));
        this.saveState('Power Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        this.updateLayers(this._pathPersistLayers(owner));
        if (this.powerCustomDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomPower] Apply pattern', {
                pattern,
                circuitNum,
                count: ordered.length,
                first: first ? { row: first.panel.row, col: first.panel.col, layerId: first.layer.id } : null,
                last: last ? { row: last.panel.row, col: last.panel.col, layerId: last.layer.id } : null
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

        // v0.11.0: then nest each screen group's member rows under a group
        // header, INSIDE the canvas group they already sit in. Runs after the
        // canvas pass because it lifts the rows that pass has just placed.
        this.regroupLayersByGroup(container);

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
