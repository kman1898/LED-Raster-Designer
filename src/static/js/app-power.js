// app-power: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Power {

    // The soca / splitter / distro panels build their markup as strings and
    // drop it in with innerHTML, interpolating user text - screen names,
    // soca names, distro names. Every one of those sites calls _esc. It has
    // to exist: without it a screen named "Main & FOH" renders wrong, and a
    // name containing a tag injects live DOM into the sidebar.
    // _escapeAttr (app-canvas-ui.js) is this app's one escaping helper;
    // _esc is the name the panel builders ask for, so point it there rather
    // than growing a second, drifting implementation.
    _esc(s) {
        return this._escapeAttr(s);
    }

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
        // count via the shared authority so a custom-routed screen reports the
        // circuits actually drawn, not what auto routing would have produced
        const circuitsRequired = this.screenCircuitCount(layer);
        // custom routing supersedes the auto assignment, so don't carry its
        // error forward (the canvas already clears it for custom patterns)
        layer._powerError = this.usesCustomCircuits(layer) ? null : powerAssignments.error;
        layer._powerCircuits = powerAssignments.circuits;

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString() : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        if (amps1El) amps1El.textContent = totalAmps1 ? totalAmps1.toFixed(2) + ' A' : '0';
        if (amps3El) amps3El.textContent = totalAmps3 ? totalAmps3.toFixed(2) + ' A' : '0';
        // Deferred, not called inline: this runs synchronously inside the
        // change handlers of the static Power fields (panel watts, voltage,
        // amperage), and it wipes all three hosts.
        //
        // Those hosts moved to the Power panel (#power-sidebar), so Tab out of
        // Watts per Panel now lands on the Flow Pattern buttons that follow it
        // in the left sidebar rather than inside the soca host. The deferral
        // still earns its place: the three hosts are siblings there and tab
        // into one another, and this same path runs from their own controls,
        // so an inline wipe still destroys the field Tab is about to land in.
        // See _rebuildAfterGesture.
        this._rebuildAfterGesture(() => {
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.refreshDistroPanel();
        });
    }

    // ---- Soca plan (Phase B) -------------------------------------------------

    // True when the screen's circuits come from paths the user drew rather
    // than from auto routing - i.e. when the auto assignment (and any error
    // it reports) has been superseded.
    usesCustomCircuits(layer) {
        if (!layer || !this.isCustomPower(layer) || !layer.powerCustomPaths) return false;
        return Object.keys(layer.powerCustomPaths)
            .some(n => (layer.powerCustomPaths[n] || []).length > 0);
    }

    // The one authority for "what circuits does this screen have": drawn
    // custom paths when the screen routes custom, else the auto assignment.
    // Everything that counts, labels or orders circuits reads this - the
    // report used to count calculatePowerAssignments() directly, which
    // ignored custom routing and disagreed with the soca plan beside it.
    screenCircuits(layer) {
        if (!layer) return [];
        if (this.isCustomPower(layer) && layer.powerCustomPaths) {
            const drawn = Object.keys(layer.powerCustomPaths)
                .map(n => parseInt(n, 10))
                .filter(n => Number.isFinite(n) && (layer.powerCustomPaths[n] || []).length > 0)
                .sort((a, b) => a - b)
                .map(n => {
                    // Resolve every step through the cross-member seam. The
                    // old getPanelByRowCol(layer, ...) landed a step that
                    // names a PEER ({row, col, layerId}) on the OWNER's
                    // cabinet at that address - a different physical cabinet,
                    // or null - silently corrupting soca leg watts, distro
                    // roll-ups, breaker labels and the label PDFs built from
                    // them. A panel resolved from a peer carries real
                    // x/y/width/height, so everything downstream keeps
                    // working; `layers` rides alongside, index-aligned with
                    // `panels`, so getSocaPlan can charge each cabinet at its
                    // OWN member's wattage. Same-layer steps resolve exactly
                    // as before (getResolvedPathPanels drops hidden panels
                    // the way the old .filter(p => p && !p.hidden) did).
                    const resolved = this.getResolvedPathPanels(
                        layer, layer.powerCustomPaths[n] || []);
                    return {
                        num: n,
                        panels: resolved.map(r => r.panel),
                        layers: resolved.map(r => r.layer),
                    };
                });
            // set to custom but nothing routed yet: fall back to the auto
            // requirement the way the ports side does, so an unrouted screen
            // still shows the distro it needs instead of reporting zero -
            // UNLESS every feedable cabinet here is already on a peer's
            // crossing circuit. That is the only honest empty plan: the
            // member's power arrives on the owner's circuits (where the
            // resolved entries above count these cabinets), so an auto
            // fallback would fabricate a plan for cables that do not exist
            // and double-count the load in every distro roll-up. Mirrors
            // getLayerCircuitsRequired's only-honest-zero rule.
            // (Evaluated BEFORE splitter merge grouping: whether a member is
            // peer-served is a fact about the drawn paths, not the merges.)
            if (drawn.length) return this._applySplitterMerges(layer, drawn);
            if (typeof this._layerFullyServedByPeerPath === 'function'
                && this._layerFullyServedByPeerPath(layer, 'powerCustomPaths')) {
                return [];
            }
        }
        const res = this.calculatePowerAssignments(layer);
        return (res.circuits || []).map((panels, i) => {
            const c = { num: i + 1, panels };
            // Splitter packing (organized + enabled): the engine hands back
            // per-branch panel counts index-aligned with `circuits`. Carry
            // them as per-branch panel arrays so the renderers can break the
            // daisy at run boundaries; `panels` stays the concatenation, so
            // every index-aligned consumer is untouched.
            if (res.runs && res.runs[i]) {
                let off = 0;
                c.branches = res.runs[i].map(n => panels.slice(off, off += n));
                c.runIds = res.runIds ? res.runIds[i] : null;
            }
            return c;
        });
    }

    // Manual splitter merges over DRAWN custom circuits: each merge group
    // collapses into ONE circuit numbered and labelled by its first member
    // (traversal order = ascending drawn number), with the member paths kept
    // as `branches`. Custom paths are NEVER auto-packed - the numbering is
    // user intent - so manual merge is the only lever here. No merges = the
    // exact input array, byte-identical to the pre-splitter path.
    _applySplitterMerges(layer, drawn) {
        const groups = this.appliedSplitterGroups(
            layer, drawn.map(c => c.num)).merge;
        if (!groups.length) return drawn;
        const byNum = new Map(drawn.map(c => [c.num, c]));
        const inGroup = new Map();
        groups.forEach(g => g.forEach(n => inGroup.set(n, g)));
        const out = [];
        const done = new Set();
        for (const c of drawn) {
            if (done.has(c.num)) continue;
            const g = inGroup.get(c.num);
            if (!g) { out.push(c); continue; }
            const members = g.filter(n => byNum.has(n)).map(n => byNum.get(n));
            members.forEach(m => done.add(m.num));
            out.push({
                num: members[0].num,
                panels: members.flatMap(m => m.panels),
                layers: members.flatMap(m => m.layers || m.panels.map(() => layer)),
                branches: members.map(m => m.panels),
                runIds: members.map(m => m.num),
            });
        }
        return out;
    }

    // The COUNT comes from the group-aware authority (app-screen-info.js) so
    // it agrees with the sidebar and the group roll-up: a peer-served member
    // reports 0, and drawn custom circuits report the highest circuit number
    // drawn - the same convention the ports side uses. screenCircuits above
    // keeps the [{num, panels}] plan shape for the soca planner, which
    // legitimately operates on the drawn paths. autoCircuits is recomputed
    // here rather than read from the cached _powerCircuitsRequired, which is
    // only refreshed for the currently-selected layer.
    screenCircuitCount(layer) {
        if (!layer) return 0;
        const auto = (this.calculatePowerAssignments(layer).circuits || []).length;
        return this.getLayerCircuitsRequired(layer, auto) || 0;
    }

    getSocaPlan(layer) {
        if (!layer) return [];
        const circuits = this.screenCircuits(layer);   // [{num, panels}] in circuit order
        if (!circuits.length) return [];
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const m = String(layer.powerLabelTemplate || 'S1-#').match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
        const startMulti = m ? parseInt(m[2], 10) || 1 : 1;
        const prefix = m ? (m[1] || 'S') : 'S';
        const socas = new Map();
        circuits.forEach((c, ci) => {
            const n = startMulti + Math.floor(ci / 6);
            const leg = (ci % 6) + 1;
            // A cross-member circuit carries cabinets from a PEER layer, and
            // those cabinets draw the peer's wattage, not the owner's -
            // screenCircuits hands back `layers` index-aligned with `panels`
            // for exactly this. Same-layer panels (and every auto plan, which
            // carries no `layers`) keep the owner's figure, byte-identical to
            // before. Voltage stays the OWNER's: the circuit is the owner's
            // cable on the owner's distro, whatever it feeds.
            const srcLayers = c.layers || [];
            const watts = c.panels.reduce((s, p, pi) => {
                const src = srcLayers[pi];
                const w = (src && src !== layer)
                    ? (parseFloat(src.panelWatts) || 0) : panelWatts;
                return s + w * this.getPanelLoadFactor(src || layer, p);
            }, 0);
            const s = socas.get(n) || { soca: n, name: prefix + n, legs: [], watts: 0, x1: Infinity, x2: -Infinity };
            // per-leg x extent so the power map can tick each leg to the
            // columns it feeds (Binder convention)
            let lx1 = Infinity, lx2 = -Infinity;
            c.panels.forEach(p => {
                const px = Number(p.x) || 0;
                lx1 = Math.min(lx1, px);
                lx2 = Math.max(lx2, px + (Number(p.width) || 0));
            });
            s.legs.push({
                leg, circuit: c.num,
                label: this.getPowerCircuitLabel(layer, c.num),
                tiles: c.panels.length, watts,
                amps: voltage ? watts / voltage : 0,
                x1: Number.isFinite(lx1) ? lx1 : null,
                x2: Number.isFinite(lx2) ? lx2 : null
            });
            s.watts += watts;
            c.panels.forEach(p => {
                const px = Number(p.x) || 0;
                s.x1 = Math.min(s.x1, px);
                s.x2 = Math.max(s.x2, px + (Number(p.width) || 0));
            });
            socas.set(n, s);
        });
        const plans = [...socas.values()];
        // v0.12.0: `leg` reports the PHYSICAL TAIL of the 6-way fan each
        // circuit lands on - identical to the sequence index until phase
        // balancing or a breaker offset moves the soca's circuits to other
        // tails, at which point the report table, breaker stickers,
        // schematic feed bubbles and bracket ticks all follow the true
        // tails. Order stays circuit order and the tails come back
        // ASCENDING (wall-order rule via socaCircuitPositions), so the wall
        // always reads in order with gaps where a tail is skipped;
        // amps/watts are untouched - balancing only renumbers.
        plans.forEach(s => {
            const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
            s.legs.forEach((l, i) => { l.leg = pos[i]; });
        });
        return plans.map(s => ({
            ...s,
            amps: voltage ? s.watts / voltage : 0,
            length: (layer.powerSocaLengths || {})[s.soca] || null
        }));
    }

    // Breakout chain from the Soca/multi to the panels. Socas break out to
    // True1 or powerCON by default (panels take those directly - that's why
    // a multi is 6 channels); Edison is the 110V alternative, and L6-20
    // breakouts add L6-20 -> panel tails per circuit.
    // `connector` is the bare connector name for labeling - the sticker goes
    // on the tail, and the tail is a True1, not a "Soca → True1".
    getPowerBreakoutTypes() {
        return [
            { id: 'soca-true1', name: 'Multi → True1', connector: 'True1', breakoutItem: 'Multi breakouts → True1' },
            { id: 'soca-powercon', name: 'Multi → powerCON', connector: 'powerCON', breakoutItem: 'Multi breakouts → powerCON' },
            { id: 'soca-edison', name: 'Multi → Edison (110V)', connector: 'Edison', breakoutItem: 'Multi breakouts → Edison', tailItem: 'Edison → panel tails' },
            { id: 'soca-l620', name: 'Multi → L6-20', connector: 'L6-20', breakoutItem: 'Multi breakouts → L6-20', tailItem: 'L6-20 → panel tails' }
        ];
    }

    getPowerBreakout(layer) {
        const types = this.getPowerBreakoutTypes();
        return types.find(t => t.id === (layer && layer.powerBreakoutType)) || types[0];
    }

    setPowerBreakout(layer, id) {
        if (!layer) return;
        layer.powerBreakoutType = id;
        this.updateLayers([layer]);
    }

    // ---- distros / circuit groups -------------------------------------------

    // A distro is a project-level power source with its own rating, voltage
    // and phase. Socas (multis) are assigned to one, so load rolls up
    // circuits -> soca -> distro across every screen it feeds. Load is summed
    // as WATTS (the invariant) and only converted to amps at the distro's own
    // voltage/phase - 3-phase per I = P / (V x 1.73).
    getDistros() {
        if (!this.project) return [];
        if (!this.project.distros) this.project.distros = [];
        return this.project.distros;
    }

    // Serialized: two rapid fire-and-forget project POSTs can complete out of
    // order, and the server merges whatever lands last - so an older payload
    // could drop a just-added distro. Chain them instead (same reason the
    // rack allocation pushes are queued).
    _persistDistros() {
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ distros: this.getDistros() })
        }).catch(() => {});
        this._distroPushQueue = (this._distroPushQueue || Promise.resolve()).then(send);
        return this._distroPushQueue;
    }

    addDistro(opts = {}) {
        const list = this.getDistros();
        const n = list.reduce((m, d) => Math.max(m, Number(String(d.id).replace('d', '')) || 0), 0) + 1;
        const d = {
            id: 'd' + n,
            name: opts.name || `DISTRO ${n}`,
            ratingA: Number(opts.ratingA) || 400,
            voltage: Number(opts.voltage) || 208,
            phase: Number(opts.phase) === 1 ? 1 : 3
        };
        list.push(d);
        this._persistDistros();
        return d;
    }

    updateDistro(id, patch = {}) {
        const d = this.getDistros().find(x => x.id === id);
        if (!d) return null;
        if (patch.name !== undefined) d.name = String(patch.name).trim() || d.name;
        if (patch.ratingA !== undefined) d.ratingA = Number(patch.ratingA) || d.ratingA;
        if (patch.voltage !== undefined) d.voltage = Number(patch.voltage) || d.voltage;
        if (patch.phase !== undefined) d.phase = Number(patch.phase) === 1 ? 1 : 3;
        if (patch.phasing !== undefined) d.phasing = patch.phasing || null;
        // Where the box physically sits - the dimmer beach, stage left
        // world. Prints on every power label that names this distro.
        if (patch.location !== undefined) d.location = String(patch.location).trim() || null;
        this._persistDistros();
        return d;
    }

    removeDistro(id) {
        const list = this.getDistros();
        const i = list.findIndex(x => x.id === id);
        if (i === -1) return false;
        list.splice(i, 1);
        // orphaned soca assignments fall back to unassigned
        const touched = [];
        for (const layer of this.project.layers || []) {
            const map = layer.powerSocaDistro;
            if (!map) continue;
            let changed = false;
            for (const k of Object.keys(map)) if (map[k] === id) { delete map[k]; changed = true; }
            if (changed) touched.push(layer);
        }
        if (touched.length) this.updateLayers(touched);
        this._persistDistros();
        return true;
    }

    setSocaDistro(layer, socaNum, distroId) {
        if (!layer) return;
        const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
        if (distroId) map[socaNum] = distroId; else delete map[socaNum];
        this.updateLayers([layer]);
    }

    // Every PARTLY-FILLED multi in the show that lands on a 3-phase distro,
    // with the tail set it currently occupies. The unit of balancing is the
    // multi, so this is what the balancer searches over. Full multis are
    // excluded: under the wall-order rule the only lever is WHICH tails a
    // multi uses, and a 6-circuit multi uses all six - there is nothing to
    // choose.
    _balanceTargets() {
        const out = [];
        const distros = this.getDistros();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of this.getSocaPlan(layer)) {
                const d = distros.find(x => x.id === assign[s.soca]);
                if (!d || d.phase !== 3) continue;
                if (s.legs.length >= 6) continue;
                out.push({
                    layer, soca: s.soca, name: s.name, distroId: d.id,
                    legs: s.legs.length,
                    positions: this.socaCircuitPositions(layer, s.soca, s.legs.length),
                    amps: s.legs.map(l => l.amps),
                    // The circuits' CURRENT labels through the one authority,
                    // captured before the search mutates the store - the
                    // balance dialog names each moved circuit by the bubble
                    // on the canvas, never by a re-derived ordinal.
                    labels: s.legs.map(l => l.label),
                    scheme: this.powerPhasingFor(d, circuitV).id
                });
            }
        }
        return out;
    }

    // Worst imbalance across every 3-phase distro, which is what we minimise.
    _worstImbalance() {
        return this.getDistroLoads()
            .filter(b => b.id && b.legs)
            .reduce((m, b) => Math.max(m, b.imbalancePct), 0);
    }

    // Search WHICH tails of the fan each partly-filled multi uses.
    //
    // Wall-order rule: circuits always map to the chosen tails ascending in
    // wall order, so the search space is tail SUBSETS (C(6,L) per multi -
    // at most 20), never permutations. They still multiply across multis, so
    // this is greedy local search: repeatedly try every single-tail change
    // (swap one used tail for a free one, re-sort), keep improvements, stop
    // when nothing helps. Deterministic. Where circuit loads are equal this
    // finds exactly what the old permutation search found - the phase math
    // only sees the subset; where they differ, wall order deliberately wins
    // over the last few percent of imbalance.
    //
    // Nothing is persisted; the project is restored before returning.
    suggestPhaseBalance() {
        const targets = this._balanceTargets();
        const before = this._worstImbalance();
        if (!targets.length) return { before, after: before, targets: [], moves: [], searched: 0 };

        const original = targets.map(t => t.positions.slice());
        const current = targets.map(t => t.positions.slice());
        const write = () => targets.forEach((t, i) => {
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            store[t.soca] = current[i].slice();
        });
        let searched = 0;
        const score = () => { write(); searched += 1; return this._worstImbalance(); };

        let best = score();
        for (let pass = 0; pass < 40; pass++) {
            let moved = false;
            for (let t = 0; t < targets.length; t++) {
                const L = current[t].length;
                for (let i = 0; i < L; i++) {
                    // trade the tail at slot i for one nothing is using;
                    // re-sort so the array stays ascending wall order
                    for (let p = 1; p <= 6; p++) {
                        if (current[t].includes(p)) continue;
                        const was = current[t].slice();
                        current[t][i] = p;
                        current[t].sort((x, y) => x - y);
                        const sc = score();
                        if (sc < best - 0.01) { best = sc; moved = true; }
                        else current[t] = was;
                    }
                }
            }
            if (!moved) break;
        }
        const winner = current.map(a => a.slice());

        // put the project back exactly as it was; the label tail-slot cache
        // may have been built against a candidate arrangement mid-search
        // (getSocaPlan labels every leg), so drop it with the candidates
        targets.forEach((t, i) => {
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            if (original[i].every((p, k) => p === k + 1)) delete store[t.soca];
            else store[t.soca] = original[i].slice();
        });
        this._circuitTailCache = null;

        return {
            before, after: best, searched,
            targets: targets.map(t => `${t.name} (${t.layer.name}, ${t.legs} circuits)`),
            moves: targets.map((t, i) => ({
                layerId: t.layer.id, layerName: t.layer.name, soca: t.soca,
                name: t.name, legs: t.legs,
                from: original[i], to: winner[i],
                amps: t.amps, labels: t.labels
            })).filter(m => m.from.some((p, k) => p !== m.to[k]))
        };
    }

    applyPhaseBalance(moves) {
        const touched = new Set();
        for (const m of moves || []) {
            const layer = (this.project.layers || []).find(l => l.id === m.layerId);
            if (!layer) continue;
            const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
            if (m.to.every((p, k) => p === k + 1)) delete store[m.soca];
            else store[m.soca] = m.to.slice();
            touched.add(layer);
        }
        this._circuitTailCache = null;
        if (touched.size) this.updateLayers([...touched]);
        return touched.size;
    }

    // Show what the balancer found and let the user accept or decline it.
    // Advisory by design: this moves a multi to a different set of breakers
    // on paper, and somebody still has to plug it in that way.
    showBalanceDialog() {
        const r = this.suggestPhaseBalance();
        const ID = 'balance-modal';
        document.getElementById(ID)?.remove();
        const esc = (s) => this._esc ? this._esc(s) : s;
        const gain = r.before - r.after;
        const body = !r.targets.length
            ? `<p style="margin:0; color:#a6b0bb;">Every multi on a three-phase distro is full, so the legs are already
               as even as the pattern allows. Imbalance comes from partly-filled
               multis — there are none here.</p>`
            : !r.moves.length
            ? `<p style="margin:0; color:#a6b0bb;">Checked ${r.searched} arrangement${r.searched === 1 ? '' : 's'} of
               ${r.targets.length} partly-filled multi${r.targets.length === 1 ? '' : 's'} and could not beat the current
               ${r.before.toFixed(1)}% imbalance. Landing them elsewhere will not help;
               filling the short multis or moving circuits between them would.</p>`
            : `<div style="display:flex; align-items:baseline; gap:10px; margin-bottom:14px;">
                 <span style="font-size:22px; color:#e05050;">${r.before.toFixed(1)}%</span>
                 <span style="color:#7d8894;">→</span>
                 <span style="font-size:22px; color:#5fa85f;">${r.after.toFixed(1)}%</span>
                 <span style="color:#8fa0b2; font-size:11px;">worst-leg imbalance · ${gain.toFixed(1)} points better</span>
               </div>
               <div style="font-size:11px; color:#8a949f; margin-bottom:6px;">Plug these circuits into different tails of the same
               fan — no rewiring, no re-patching:</div>
               ${r.moves.map(m => `
                 <div style="margin-bottom:10px;">
                   <div style="color:#e8eef5; margin-bottom:3px;">${esc(m.name)}
                     <span style="color:#7d8894; font-weight:400;">· ${esc(m.layerName)}</span></div>
                   <table style="width:100%; border-collapse:collapse; font-size:11px;">
                     ${m.to.map((p, k) => p === m.from[k] ? '' : `<tr>
                       <td style="padding:2px 8px; color:#a6b0bb; width:40%;">${esc((m.labels || [])[k] || `circuit ${k + 1}`)}
                         <span style="color:#6d7681;">(${m.amps[k].toFixed(1)} A)</span></td>
                       <td style="padding:2px 8px; color:#a6b0bb;">tail ${m.from[k]} → <strong style="color:#e8eef5;">tail ${p}</strong></td>
                     </tr>`).join('')}
                   </table>
                 </div>`).join('')}
               <div style="margin-top:12px; font-size:11px; color:#7d8894;">Balancing picks WHICH tails of the fan a partly-filled
               multi uses — skipping a different tail lands the remainder on
               different legs. Circuits keep wall order on the chosen tails,
               so the labels still read in order across the wall.
               Evaluated ${r.searched} arrangements.</div>`;

        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:540px; max-width:94vw; margin:80px auto; border:1px solid #3a3a3a; overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">BALANCE PHASE LEGS</h2>
    <button class="btn btn-secondary balance-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; font-size:12px; line-height:1.55;">${body}</div>
  <div style="display:flex; gap:8px; justify-content:flex-end; padding:0 20px 16px;">
    <button class="btn btn-secondary balance-reset" title="Put every multi back on its natural breaker position">Reset offsets</button>
    <button class="btn btn-secondary balance-close">${r.moves.length ? 'Leave it' : 'Close'}</button>
    ${r.moves.length ? '<button class="btn balance-apply">Apply</button>' : ''}
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelectorAll('.balance-close').forEach(b =>
            b.addEventListener('click', () => el.remove()));
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
        // Balancing renumbers labels (true tails), so refresh EVERY pane
        // that prints them - splitter rows and the label editor included,
        // plus the canvas bubbles - not just the load roll-ups. The server
        // echo would repaint them a round-trip later anyway; doing it here
        // means the left pane and the map agree the moment the dialog
        // closes (same refresh set as _writeSplitterManual).
        const refreshAll = () => {
            this.refreshDistroPanel();
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const resetBtn = el.querySelector('.balance-reset');
        if (resetBtn) resetBtn.addEventListener('click', () => {
            this.clearPhaseBalance();
            el.remove();
            refreshAll();
        });
        const applyBtn = el.querySelector('.balance-apply');
        if (applyBtn) applyBtn.addEventListener('click', () => {
            this.applyPhaseBalance(r.moves);
            el.remove();
            refreshAll();
        });
    }

    // Plain-language explanation of what the three phasing schemes mean and
    // why the choice changes the leg loads. Built on demand rather than
    // living in index.html so the copy sits next to the math it describes.
    showPhasingHelp() {
        const ID = 'phasing-help-modal';
        document.getElementById(ID)?.remove();
        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:660px; max-width:94vw; margin:60px auto; border:1px solid #3a3a3a; display:flex; flex-direction:column; max-height:calc(100vh - 120px); overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">HOW MULTIS LAND ON THE PHASE LEGS</h2>
    <button class="btn btn-secondary phasing-help-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; overflow-y:auto; font-size:12px; color:#c3ccd6; line-height:1.6;">

    <p style="margin:0 0 14px;"><strong style="color:#e8eef5;">A distro fed from camlock is three-phase. Every circuit
    coming off the breakout is single-phase</strong> — whether it is 120V (one
    hot and a neutral) or 208V (two hots, no neutral). Three-phase never
    reaches a panel. The legs only decide <em>which</em> hots each circuit
    sits across, and therefore how the load spreads over the service.</p>

    <div style="background:#3a2626; border-left:3px solid #b34a3a; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px; color:#e0c0ba;">
      <strong style="color:#f5cdc4;">There is no North American standard for this.</strong>
      ANSI E1.80, USITT RP-1 and NEC 520.68 all cover the <em>pinout</em> —
      which pin carries which circuit's conductors — and none of them assigns
      a circuit to a leg. No major distro manufacturer publishes a universal
      mapping. Motion Laboratories' own maintenance manual says to "verify
      the pinout of each output, including that the correct phase is on the
      correct pin per the pinout. (The pinout is marked on the panel near the
      output devices.)" <strong style="color:#f5cdc4;">Read the unit.</strong>
    </div>

    <p style="margin:0 0 14px; color:#a6b0bb;">What every source does agree on is the
    <em>balance goal</em>: two circuits per leg on 120V, two circuits per
    leg-pair on 208V. Only the order varies — and the order is exactly what
    decides where a partly-filled multi dumps its remainder. Each pattern
    below is documented on a real distro or rack, none is a default.</p>

    <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
      <tr style="border-bottom:1px solid #3a3a3a;">
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Pattern</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Circuits 1–6</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Where it is documented</th>
      </tr>
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">120V rotating<br><span style="color:#7d8894; font-size:11px;">one leg each</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px; white-space:nowrap;">X Y Z<br>X Y Z</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">Published phasing sheet for a 36-way 120V house distro.</td>
      </tr>
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">120V paired<br><span style="color:#7d8894; font-size:11px;">two circuits per leg</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px; white-space:nowrap;">X X<br>Y Y<br>Z Z</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">What several practitioners report as usual.</td>
      </tr>
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">208V paired<br><span style="color:#7d8894; font-size:11px;">XY ZX YZ</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px; white-space:nowrap;">XY XY<br>ZX ZX<br>YZ YZ</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">Two independent rental houses publish this exact map. The best-attested 208V pattern.</td>
      </tr>
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">208V paired<br><span style="color:#7d8894; font-size:11px;">XY YZ ZX</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px; white-space:nowrap;">XY XY<br>YZ YZ<br>ZX ZX</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">Same grouping, different pair order — Strand LightRack module pinout.</td>
      </tr>
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">208V rotating<br><span style="color:#7d8894; font-size:11px;">pair rotates each circuit</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px; white-space:nowrap;">XY XZ YZ<br>XY XZ YZ</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">Reported as a competing family. Spreads a partly-filled multi best.</td>
      </tr>
    </table>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0;">
      <div style="color:#e8eef5; margin-bottom:5px;">Why your legs are uneven</div>
      <div style="color:#a6b0bb;">Imbalance almost always comes from <strong>partly-filled
      multis</strong>, not from the screens. A full 6-circuit multi balances
      itself under any scheme. A multi that stops at 4 or 5 circuits dumps its
      remainder onto whichever legs come first in the pattern — with paired
      legs that is always X. Fill the multi, move a circuit to another multi,
      or use the rotating pattern if the distro is wired that way.</div>
    </div>

    <div style="margin-top:14px; color:#7d8894; font-size:11px;">
      Per-leg current is a phasor sum, not a straight addition: a 208V circuit
      is one load drawing the <em>same</em> current in both its legs, sitting
      ±30° off each leg's line-to-neutral reference. Imbalance is NEMA-style —
      the largest deviation from the average of the three legs.
    </div>
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelector('.phasing-help-close').addEventListener('click', () => el.remove());
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
    }

    // How a distro lands a multi's 6 circuits on its phase legs.
    //
    // This is a property of the DISTRO's internal bus and breaker
    // arrangement. It is NOT the connector pinout: ANSI E1.80-2024 defines
    // 120V Type U and 208V Types C/D/E, but those describe which PIN carries
    // which circuit's conductors - the standard's own table key is only
    // "L = Ungrounded Circuit Conductor" and it never assigns a circuit to
    // L1, L2 or L3. Two distros with identical E1.80 pinouts can still land
    // their circuits on different legs. Read the distro, not the connector.
    //
    // Every pattern below is documented on a real North American distro or
    // rack. There is no national standard for phase rotation - a search of
    // E1.80, USITT RP-1, NEC 520.68, and the published material from every
    // major distro manufacturer turned up nothing that assigns a circuit to
    // a leg. Motion Laboratories' own maintenance manual says to "verify the
    // pinout of each output, including that the correct phase is on the
    // correct pin per the pinout. (The pinout is marked on the panel near the
    // output devices.)" That is the industry position: read the unit.
    //
    // What IS consistent across every source is the balance goal - two
    // circuits per leg on 120V, two circuits per leg-PAIR on 208V. Only the
    // order varies, and the order is what changes a partly-filled multi.
    powerPhasingSchemes() {
        return [
            { id: 'rotating-ln', name: '120V — rotating (X Y Z X Y Z)', lineToLine: false,
              pattern: 'X Y Z X Y Z',
              note: '1>X 2>Y 3>Z 4>X 5>Y 6>Z — one published house distro sheet; no practitioner source corroborates it, so confirm before relying on it' },
            { id: 'paired-ln', name: '120V — paired (X X Y Y Z Z)', lineToLine: false,
              pattern: 'X X Y Y Z Z',
              note: '1,2>X  3,4>Y  5,6>Z — the arrangement practitioners most often describe' },
            { id: 'paired-ll', name: '208V — paired, XY ZX YZ', lineToLine: true,
              pattern: 'XY ZX YZ',
              note: '1,2>XY  3,4>ZX  5,6>YZ — two independent house pinouts publish this' },
            { id: 'paired-ll-alt', name: '208V — paired, XY YZ ZX', lineToLine: true,
              pattern: 'XY YZ ZX',
              note: '1,2>XY  3,4>YZ  5,6>ZX — same grouping, other pair order (Strand LightRack)' },
            { id: 'rotating-ll', name: '208V — rotating (XY XZ YZ)', lineToLine: true,
              pattern: 'XY XZ YZ',
              note: '1,4>XY  2,5>XZ  3,6>YZ — spreads a partly-filled multi better' }
        ];
    }

    // Default scheme for a distro: line-to-line when the circuit voltage
    // matches the service voltage (208V circuits on a 208V wye), otherwise
    // line-to-neutral.
    powerPhasingFor(distro, circuitVoltage) {
        const schemes = this.powerPhasingSchemes();
        const explicit = distro && distro.phasing && schemes.find(s => s.id === distro.phasing);
        if (explicit) return explicit;
        const ll = distro && circuitVoltage > 0 && Math.abs(circuitVoltage - distro.voltage) < 1;
        return schemes.find(s => s.id === (ll ? 'paired-ll' : 'rotating-ln'));
    }

    // The circuit voltage this distro actually sees: whatever the screens
    // feeding it run at, walked in the SAME order getDistroLoads walks them so
    // the select and the leg maths can never name two different schemes.
    //
    // A distro with nothing assigned yet has no evidence to read, so it is
    // taken at its word - a service whose circuits sit at the service voltage,
    // which is what choosing 208V means. It is a default like any other here
    // and the moment a multi lands on the distro the real circuit voltage
    // replaces it.
    distroCircuitVoltage(distro) {
        if (!distro || !this.project) return 0;
        let seen = null;
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            if (!plan.some(s => assign[s.soca] === distro.id)) continue;
            seen = parseFloat(layer.powerVoltage) || 0;
        }
        return seen === null ? (Number(distro.voltage) || 0) : seen;
    }

    // What the phasing control has to say out loud: the scheme in force, and
    // whether it is DERIVED from the voltage or was picked by hand.
    //
    // Two distros can run the same scheme, one because somebody read the box
    // and one because nobody has - and only the first survives a voltage
    // change. Without this distinction on screen "a manual choice overrides
    // the default" is a rule the user cannot see operating.
    distroPhasingState(distro) {
        const schemes = this.powerPhasingSchemes();
        const chosen = distro && distro.phasing
            && schemes.find(s => s.id === distro.phasing);
        const circuitV = this.distroCircuitVoltage(distro);
        // Ask for the derived answer explicitly rather than reading it off
        // powerPhasingFor(distro, ...), which would hand back the explicit
        // choice and hide what the voltage would have chosen.
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, phasing: null }, circuitV);
        return {
            explicit: !!chosen,
            derived,
            circuitVoltage: circuitV,
            scheme: chosen || derived
        };
    }

    // Order a leg pair cyclically (X>Y>Z>X). The first leg of the cyclic pair
    // carries the line-to-line current at +30 deg relative to its own
    // line-to-neutral voltage, the second at -30 deg.
    _cyclicPair(a, b) {
        const C = ['X', 'Y', 'Z'];
        const ia = C.indexOf(a), ib = C.indexOf(b);
        return ib === (ia + 1) % 3 ? [a, b] : [b, a];
    }

    _addLegPhasor(store, leg, amps, degrees) {
        const r = degrees * Math.PI / 180;
        store[leg].re += amps * Math.cos(r);
        store[leg].im += amps * Math.sin(r);
    }

    // `offset` slides the used circuits along the multi's own six positions:
    // a multi with 4 circuits in use can occupy positions 1-4, 2-5 or 3-6.
    // The load does not move to another multi - it is the same 6-way fan,
    // just landed on different legs of it.
    //
    // The offset MUST be bounded by socaPhaseOffsetMax so the last circuit
    // stays within position 6. The modulo below is only a guard; if it ever
    // actually wraps, the offset was invalid and the answer is nonsense -
    // a 5-circuit multi at offset 3 would want positions 4..8, and wrapping
    // 7 and 8 back to 1 and 2 silently invents a plan nobody can patch.
    _circuitLegs(legIndex, schemeId, offset = 0) {
        const i = ((legIndex - 1 + (Number(offset) || 0)) % 6 + 6) % 6;
        if (schemeId === 'paired-ll') return [['X','Y'], ['X','Y'], ['Z','X'], ['Z','X'], ['Y','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ll-alt') return [['X','Y'], ['X','Y'], ['Y','Z'], ['Y','Z'], ['Z','X'], ['Z','X']][i];
        if (schemeId === 'rotating-ll') return [['X','Y'], ['X','Z'], ['Y','Z'], ['X','Y'], ['X','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ln') return [['X'], ['X'], ['Y'], ['Y'], ['Z'], ['Z']][i];
        return [['X', 'Y', 'Z'][i % 3]];
    }

    // How far a multi's used circuits can slide as a BLOCK before the last
    // one runs off the end of the 6-way fan. Kept for the legacy block model;
    // socaCircuitPositions supersedes it.
    socaPhaseOffsetMax(legsUsed) {
        return Math.max(0, 6 - (Number(legsUsed) || 6));
    }

    // Which position on the multi's 6-way fan each used circuit occupies.
    //
    // WALL-ORDER RULE (user decision, fixed): balancing - or anything else -
    // only ever chooses WHICH tails of the fan are in use (the SET). The
    // assignment of circuits to the chosen tails is always wall order ->
    // ascending tail number, so a wall using tails {1,2,3,5,6} reads
    // S1-1, S1-2, S1-3, S1-5, S1-6 left to right, never a permutation.
    // Stored arrays are therefore sorted ascending ON READ: projects that
    // still carry a permutation from the old balancer ([6,2,5,1,3]) or a
    // rotation ([5,6,1,2,3]) display wall-ordered immediately, keeping the
    // same occupied tails, without a re-balance.
    //
    // Returns a position (1-6) per used circuit, ascending in circuit
    // (wall) order. Falls back to the legacy block offset - which selects
    // the occupied tails off+1..off+L, already ascending - then to the
    // natural 1..L.
    socaCircuitPositions(layer, socaNum, legsUsed) {
        const L = Math.max(0, Math.min(6, Number(legsUsed) || 0));
        const saved = ((layer && layer.powerSocaPhasePos) || {})[socaNum];
        if (Array.isArray(saved) && saved.length === L
            && saved.every(p => Number.isInteger(p) && p >= 1 && p <= 6)
            && new Set(saved).size === L) {
            return saved.slice().sort((a, b) => a - b);
        }
        const off = this.socaPhaseOffset(layer, socaNum, L);
        return Array.from({ length: L }, (_, i) => i + 1 + off);
    }

    // Positions must be a set of distinct 1-6 values, one per used circuit -
    // two circuits cannot share a tail. Only the SET matters (wall-order
    // rule): stored sorted ascending, and a permutation of 1..L is the
    // natural arrangement.
    setSocaCircuitPositions(layer, socaNum, positions, legsUsed) {
        if (!layer) return false;
        const L = Math.max(0, Math.min(6, Number(legsUsed) || 0));
        const ok = Array.isArray(positions) && positions.length === L
            && positions.every(p => Number.isInteger(p) && p >= 1 && p <= 6)
            && new Set(positions).size === L;
        if (!ok) return false;
        const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
        const sorted = positions.slice().sort((a, b) => a - b);
        const natural = sorted.every((p, i) => p === i + 1);
        if (natural) delete store[socaNum]; else store[socaNum] = sorted;
        this._circuitTailCache = null;
        this.updateLayers([layer]);
        return true;
    }

    // Which position within the multi the first used circuit sits on (0-based).
    // Clamped on read as well as on write, so a stored value that is no longer
    // valid - the screen shed a circuit since it was set - degrades to the
    // nearest legal position instead of wrapping off the end.
    socaPhaseOffset(layer, socaNum, legsUsed) {
        const map = (layer && layer.powerSocaPhaseOffset) || {};
        const raw = Math.max(0, Number(map[socaNum]) || 0);
        return Math.min(raw, this.socaPhaseOffsetMax(legsUsed));
    }

    setSocaPhaseOffset(layer, socaNum, offset, legsUsed) {
        if (!layer) return;
        // Always leave an object behind, never delete the property itself:
        // an absent key is simply missing from the update payload and the
        // server keeps whatever it had, so "clear this" would silently not
        // clear. An empty object overwrites.
        const map = layer.powerSocaPhaseOffset || (layer.powerSocaPhaseOffset = {});
        const v = Math.min(Math.max(0, Number(offset) || 0),
                           this.socaPhaseOffsetMax(legsUsed));
        if (v) map[socaNum] = v; else delete map[socaNum];
        this._circuitTailCache = null;
        this.updateLayers([layer]);
    }

    // Drop every multi back to its natural breaker position.
    clearPhaseBalance() {
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        screens.forEach(l => { l.powerSocaPhaseOffset = {}; l.powerSocaPhasePos = {}; });
        this._circuitTailCache = null;
        if (screens.length) this.updateLayers(screens);
        return screens.length;
    }

    // Rollup per distro across every screen, plus an 'unassigned' bucket so
    // no load is silently dropped. Three-phase distros also get per-leg
    // (X/Y/Z) loads so you can see whether the service is loaded evenly.
    getDistroLoads() {
        const distros = this.getDistros();
        const mk = (d) => ({
            distro: d, socas: [], watts: 0,
            legWatts: { X: 0, Y: 0, Z: 0 },
            legPhasor: { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 }, Z: { re: 0, im: 0 } },
            pairWatts: {}
        });
        const buckets = new Map(distros.map(d => [d.id, mk(d)]));
        const unassigned = mk(null);
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const plan = this.getSocaPlan(layer);
            if (!plan.length) continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of plan) {
                const b = buckets.get(assign[s.soca]) || unassigned;
                b.socas.push({ layer: layer.name, layerId: layer.id, soca: s.soca, name: s.name, watts: s.watts, legs: s.legs.length });
                b.watts += s.watts;
                // spread this multi's circuits across the phase legs
                const d = b.distro;
                if (d && d.phase === 3) {
                    const scheme = this.powerPhasingFor(d, circuitV);
                    b.scheme = scheme;
                    const vln = d.voltage / Math.sqrt(3);
                    const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                    for (let li = 0; li < s.legs.length; li++) {
                        const leg = s.legs[li];
                        const legs = this._circuitLegs(pos[li], scheme.id);
                        if (legs.length === 1) {
                            // line-to-neutral: full current on one leg, in
                            // phase with that leg's L-N voltage
                            b.legWatts[legs[0]] += leg.watts;
                            this._addLegPhasor(b.legPhasor, legs[0], leg.watts / vln, 0);
                        } else {
                            // Line-to-line: the SAME current flows in both
                            // legs (it is one series load) - it is NOT halved.
                            // Referred to each leg's own L-N reference it sits
                            // at +30 deg on the first leg of the cyclic pair
                            // and -30 deg on the second.
                            const [first, second] = this._cyclicPair(legs[0], legs[1]);
                            const amps = leg.watts / d.voltage;
                            this._addLegPhasor(b.legPhasor, first, amps, 30);
                            this._addLegPhasor(b.legPhasor, second, amps, -30);
                            // VA column keeps the panel-schedule convention:
                            // half the VA booked against each leg
                            b.legWatts[first] += leg.watts / 2;
                            b.legWatts[second] += leg.watts / 2;
                            const key = [first, second].join('');
                            b.pairWatts[key] = (b.pairWatts[key] || 0) + leg.watts;
                        }
                    }
                }
            }
        }
        const shape = (b) => {
            const d = b.distro;
            const v = d ? d.voltage : 0;
            const amps = v > 0 ? (d.phase === 3 ? b.watts / (v * 1.73) : b.watts / v) : 0;
            const rating = d ? d.ratingA : 0;
            // Per-leg amps are line-to-NEUTRAL: on a 208V wye that is 120V,
            // which is what each leg actually sees.
            let legs = null, imbalancePct = 0;
            if (d && d.phase === 3) {
                // Per-leg current is the PHASOR magnitude, not watts/voltage:
                // line-to-line loads sit +-30 deg off their legs' L-N
                // reference, so scalar addition would misreport by 13-15%.
                const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
                const w = b.legWatts, ph = b.legPhasor;
                const one = (k) => {
                    const a = mag(ph[k]);
                    return { watts: w[k], amps: a, pct: rating > 0 ? (a / rating) * 100 : 0 };
                };
                legs = { X: one('X'), Y: one('Y'), Z: one('Z') };
                // NEMA-style: max deviation from the AVERAGE (not max-min
                // spread, which reads roughly double and is not what a
                // genset spec or an electrician means by "% imbalance").
                const amps = [legs.X.amps, legs.Y.amps, legs.Z.amps];
                const avg = (amps[0] + amps[1] + amps[2]) / 3;
                imbalancePct = avg > 0
                    ? (Math.max(...amps.map(x => Math.abs(x - avg))) / avg) * 100 : 0;
                legs.lineToNeutralV = v / Math.sqrt(3);
                legs.avgAmps = avg;
                legs.spreadAmps = Math.max(...amps) - Math.min(...amps);
                legs.over = rating > 0 && Math.max(...amps) > rating;
                legs.scheme = b.scheme ? b.scheme.name : null;
                legs.schemeId = b.scheme ? b.scheme.id : null;
                legs.pairWatts = b.pairWatts;
            }
            return {
                id: d ? d.id : null,
                name: d ? d.name : 'Unassigned',
                location: (d && d.location) || null,
                ratingA: rating, voltage: v, phase: d ? d.phase : null,
                watts: b.watts, amps,
                pct: rating > 0 ? (amps / rating) * 100 : 0,
                over: rating > 0 && amps > rating,
                legs, imbalancePct,
                socas: b.socas
            };
        };
        const out = distros.map(d => shape(buckets.get(d.id)));
        if (unassigned.socas.length) out.push(shape(unassigned));
        return out;
    }

    setSocaLength(layer, socaNum, length) {
        if (!layer) return;
        const store = layer.powerSocaLengths || (layer.powerSocaLengths = {});
        const v = String(length || '').trim();
        if (v) store[socaNum] = v; else delete store[socaNum];
        this.updateLayers([layer]);
    }

    // Project-level distro list with a live load bar per source. Shown in the
    // Power panel because that's where power planning lives, but the numbers
    // roll up across EVERY screen, not just the selected one.
    //
    // Unlike refreshSocaRuns and refreshSplitterPanel it never blanks itself:
    // there is no layer it is wrong for. What keeps it off the other tabs is
    // its host's ancestry - the Power panel leaves layout outside Power view
    // (updateViewSidebars) and the tab-panel around the hosts hides with the
    // tab. Give the host a parent that lives in every view and this list
    // renders in every view.
    refreshDistroPanel() {
        const host = document.getElementById('power-distros');
        if (!host) return;
        // The distro rows are editors too, and this wipe runs on every stats
        // refresh - keyed fields plus the capture keep the user's focus and
        // caret across it (see _preserveEditorFocus). The buttons carry keys
        // as well: Tab out of a row's name field lands on its ✕ button, and
        // an unkeyed stop is one the restore cannot bring back - the same
        // reason the label editors keyed their row checkboxes.
        this._preserveEditorFocus();
        const esc = (s) => this._esc ? this._esc(s) : s;
        const loads = this.getDistroLoads();
        host.innerHTML = `
            <!-- Wraps: the Power panel drags down to 180px, and the heading
                 with both buttons has never fitted one line at any width the
                 panel offers - the sidebar's overflow-x:hidden was simply
                 cutting + Add off, and squeezing its label onto two lines at
                 the 260px default. The buttons travel as one group so they
                 drop below the heading together and stay right-aligned, and
                 the group wraps in turn once even it runs out of room. The
                 heading takes the slack instead of a spacer span, so a wrapped
                 line has nothing stretched across it. -->
            <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:6px;">
                <label style="font-weight:600; flex:1 1 auto;" data-tooltip="Power distros, Project-level power sources. Assign each multi to one and the load rolls up here across every screen.">Power Distros</label>
                <div style="display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; margin-left:auto;">
                    <button id="power-distro-balance" data-lrd-field="power-distro-balance" class="btn btn-secondary" style="padding:2px 10px; white-space:nowrap;" data-tooltip="Balance legs, Searches which set of six breakers each partly-filled multi should land on. A full multi balances itself, so only short ones move. Nothing changes until you accept it.">Balance</button>
                    <button id="power-distro-add" data-lrd-field="power-distro-add" class="btn btn-secondary" style="padding:2px 10px; white-space:nowrap;">+ Add</button>
                </div>
            </div>
            ${loads.length ? loads.map(d => {
                const pct = Math.min(100, Math.round(d.pct));
                const feeds = d.socas.length
                    ? d.socas.map(s => `${esc(s.name)} (${esc(s.layer)})`).join(', ')
                    : 'nothing assigned';
                // Read off the distro itself, not the rollup: the rollup only
                // learns a scheme from a multi that landed on it, so an empty
                // distro used to fall through to whichever option happened to
                // be first in the list.
                const raw = d.id ? this.getDistros().find(x => x.id === d.id) : null;
                const ph = raw && raw.phase === 3 ? this.distroPhasingState(raw) : null;
                return `<div class="power-distro-row" data-id="${d.id || ''}" style="margin-bottom:12px;">
                    ${d.id ? `
                    <div style="display:flex; gap:5px; align-items:center; margin-bottom:4px;">
                        <input type="text" class="distro-name" data-lrd-field="distro-name-${d.id}" value="${esc(d.name).replace(/"/g, '&quot;')}" style="flex:1; min-width:60px;" data-tooltip="Name this power source.">
                        <button class="btn btn-secondary distro-del" data-lrd-field="distro-del-${d.id}" style="padding:1px 7px; flex:none;">✕</button>
                    </div>
                    <!-- Same wrap, same reason as the heading above. Voltage
                         and phase travel as one group so they drop to the
                         second line together rather than one at a time, and
                         the group's flex-basis is short enough that the whole
                         row still fits on one line at the 260px default. -->
                    <div style="display:flex; flex-wrap:wrap; gap:5px; align-items:center; margin-bottom:4px;">
                        <input type="number" class="distro-rating" data-lrd-field="distro-rating-${d.id}" value="${d.ratingA}" min="1" style="width:56px;" data-tooltip="Rating, Service rating in amps.">
                        <span style="font-size:10px; color:#777;">A</span>
                        <div style="display:flex; gap:5px; align-items:center; flex:1 1 110px; min-width:0;">
                            <select class="distro-voltage info-select" data-lrd-field="distro-voltage-${d.id}" style="width:70px; min-width:0;">
                                ${[110, 120, 208, 220, 230, 240, 400, 415].map(v => `<option value="${v}" ${d.voltage === v ? 'selected' : ''}>${v}V</option>`).join('')}
                            </select>
                            <select class="distro-phase info-select" data-lrd-field="distro-phase-${d.id}" style="width:56px; min-width:0;">
                                <option value="1" ${d.phase === 1 ? 'selected' : ''}>1φ</option>
                                <option value="3" ${d.phase === 3 ? 'selected' : ''}>3φ</option>
                            </select>
                        </div>
                    </div>
                    <div style="display:flex; gap:5px; align-items:center; margin-bottom:4px;">
                        <input type="text" class="distro-location" data-lrd-field="distro-location-${d.id}" value="${esc(d.location || '').replace(/"/g, '&quot;')}" placeholder="beach / location" style="flex:1; min-width:60px;" data-tooltip="Location, Where this distro physically sits - the beach, stage left world, FOH. Prints on every power label that names it, so a runner can find the other end.">
                    </div>
                    ${d.phase === 3 && ph ? `<div class="info-row" style="margin-bottom:4px;" data-tooltip="Phasing, How a multi's 6 circuits land on the phase legs. A property of the distro's bus and breaker arrangement - read it off the distro. Not the same as the connector's E1.80 pinout type.">
                        <label style="font-weight:400; font-size:10px;">Phasing</label>
                        <!-- The select and its help button share a line of
                             their own beneath the caption: the row was written
                             as a flex row but never given display:flex, so the
                             select sized itself to its longest option and hung
                             off the panel at every width below its own. -->
                        <div style="display:flex; align-items:center; gap:6px;">
                            <select class="distro-phasing info-select" data-lrd-field="distro-phasing-${d.id}" style="flex:1 1 0; min-width:0;">
                                <!-- Deriving is a state, not the absence of
                                     one: an empty value clears distro.phasing
                                     and hands the choice back to the voltage.
                                     Named by legs rather than by volts -
                                     line-to-neutral is 120V on a 208V service
                                     and 230V on a 400V one. -->
                                <option value="" ${ph.explicit ? '' : 'selected'}>Match voltage — ${ph.derived.lineToLine ? 'line-to-line' : 'line-to-neutral'} (${ph.derived.pattern})</option>
                                ${this.powerPhasingSchemes().map(sc => `<option value="${sc.id}" ${ph.explicit && ph.scheme.id === sc.id ? 'selected' : ''}>${sc.name}</option>`).join('')}
                            </select>
                            <button class="distro-phasing-help" data-lrd-field="distro-phasing-help-${d.id}" title="What do these mean?">?</button>
                        </div>
                    </div>` : ''}` : `<div style="font-size:12px; font-weight:600; color:#d8a13c; margin-bottom:3px;">${esc(d.name)}</div>`}
                    <div class="rack-bar"><div class="rack-bar-fill${d.over ? ' over' : ''}" style="width:${pct}%"></div></div>
                    <div style="font-size:10px; color:${d.over ? '#e05050' : d.id ? '#8fa0b2' : '#d8a13c'}; margin-top:2px;">
                        ${d.id
                            ? `${d.amps.toFixed(1)} A / ${d.ratingA} A (${Math.round(d.pct)}%)${d.over ? ' — OVER' : ''} · ${Math.round(d.watts).toLocaleString()} W · ${d.phase}φ`
                            : `${Math.round(d.watts).toLocaleString()} W with no distro — assign to see amps`}
                    </div>
                    ${d.legs ? `<div style="margin-top:4px;">
                        <!-- Wraps for the same reason the rows above do: at
                             180px the imbalance figure is the one that no
                             longer fits, and it drops below the three legs
                             rather than off the panel. -->
                        <div style="display:flex; flex-wrap:wrap; gap:4px; align-items:center; font-size:10px; color:${d.imbalancePct > 20 ? '#e05050' : d.imbalancePct > 10 ? '#d8a13c' : '#8fa0b2'};"
                             data-tooltip="Leg loading, Per-leg current is a phasor sum - line-to-line circuits sit 30 degrees off each leg's line-to-neutral reference, so they are not simply added. Imbalance is NEMA-style: max deviation from the average.">
                            <span style="letter-spacing:0.5px;">LEGS</span>
                            ${['X', 'Y', 'Z'].map(k => `<span style="flex:1; text-align:center;">${k} ${d.legs[k].amps.toFixed(0)}A</span>`).join('')}
                            <span>${d.imbalancePct > 1 ? `±${Math.round(d.imbalancePct)}%` : 'even'}</span>
                        </div>
                        <div style="display:flex; gap:3px; margin-top:2px;">
                            ${['X', 'Y', 'Z'].map(k => `<div class="rack-bar" style="flex:1;"><div class="rack-bar-fill${d.legs[k].pct > 100 ? ' over' : ''}" style="width:${Math.min(100, Math.round(d.legs[k].pct))}%"></div></div>`).join('')}
                        </div>
                    </div>` : ''}
                    <div style="font-size:10px; color:#6d7987; margin-top:3px;">${feeds}</div>
                </div>`;
            }).join('') : '<div style="font-size:11px; color:#777; padding:4px 0;">No distros yet — add one, then assign multis to it.</div>'}`;

        const add = host.querySelector('#power-distro-add');
        if (add) add.addEventListener('click', () => {
            this.addDistro();
            this.refreshDistroPanel();
            this.refreshSocaRuns();
        });
        const bal = host.querySelector('#power-distro-balance');
        if (bal) bal.addEventListener('click', () => this.showBalanceDialog());
        host.querySelectorAll('.power-distro-row').forEach(row => {
            const id = row.dataset.id;
            if (!id) return;
            // The restate is deferred, not inline: patch() fires from the
            // rows' own change handlers, mid-Tab, and an inline wipe would
            // destroy the field Tab is moving into (see _rebuildAfterGesture).
            const patch = (p) => {
                this.updateDistro(id, p);
                this._rebuildAfterGesture(() => { this.refreshDistroPanel(); this.refreshSocaRuns(); });
            };
            const nameEl = row.querySelector('.distro-name');
            if (nameEl) nameEl.addEventListener('change', () => patch({ name: nameEl.value }));
            const rate = row.querySelector('.distro-rating');
            if (rate) rate.addEventListener('change', () => patch({ ratingA: rate.value }));
            const volt = row.querySelector('.distro-voltage');
            if (volt) volt.addEventListener('change', () => patch({ voltage: volt.value }));
            const ph = row.querySelector('.distro-phase');
            if (ph) ph.addEventListener('change', () => patch({ phase: ph.value }));
            const phg = row.querySelector('.distro-phasing');
            if (phg) phg.addEventListener('change', () => patch({ phasing: phg.value }));
            const loc = row.querySelector('.distro-location');
            if (loc) loc.addEventListener('change', () => patch({ location: loc.value }));
            const phHelp = row.querySelector('.distro-phasing-help');
            if (phHelp) phHelp.addEventListener('click', () => this.showPhasingHelp());
            const del = row.querySelector('.distro-del');
            if (del) del.addEventListener('click', () => {
                this.removeDistro(id);
                this.refreshDistroPanel();
                this.refreshSocaRuns();
            });
        });
    }

    refreshSocaRuns() {
        const host = document.getElementById('power-soca-runs');
        if (!host) return;
        // Same wipe, same cure as the label editors: the round-trip after a
        // soca-length edit lands here and rewrites the host the user is
        // standing in. Every field below carries a data-lrd-field key so the
        // capture can put focus and caret back after the innerHTML wipe.
        this._preserveEditorFocus();
        const layer = this.currentLayer;
        if (!layer || (layer.type || 'screen') === 'image') { host.innerHTML = ''; return; }
        const plan = this.getSocaPlan(layer);
        if (!plan.length) { host.innerHTML = ''; return; }
        const breakout = this.getPowerBreakout(layer);
        host.innerHTML = `
            <label style="font-weight: 600; margin-bottom: 6px; display: block;" data-tooltip="Soca / multi home runs, Each Soca (multi) feeds up to 6 circuits. Set the home-run cable length per multi - it flows into the gear checklist and report.">Soca / Multi Home Runs</label>
            <div class="info-row" style="align-items:center;" data-tooltip="Breakout, How the multi terminates: True1 or powerCON breakouts feed panels directly (the 6-channel default), Edison is the 110V option, L6-20 adds L6-20-to-panel tails per circuit. Drives the gear checklist.">
                <label style="font-weight:400;">Breakout</label>
                <select id="power-breakout-type" data-lrd-field="power-breakout-type" class="info-select" style="width: 150px;">
                    ${this.getPowerBreakoutTypes().map(t => `<option value="${t.id}" ${breakout.id === t.id ? 'selected' : ''}>${t.name}</option>`).join('')}
                </select>
            </div>
            ${plan.map(s => {
                const assigned = (layer.powerSocaDistro || {})[s.soca] || '';
                return `
                <div class="info-row" style="align-items:center;">
                    <label style="font-weight:400;">${this._esc ? this._esc(s.name) : s.name} · ${s.legs.length} leg${s.legs.length === 1 ? '' : 's'} · ${s.amps.toFixed(1)} A</label>
                    <select class="power-soca-distro info-select" data-soca="${s.soca}" data-lrd-field="power-soca-distro-${s.soca}" style="width:96px;" data-tooltip="Distro, Which power source this multi lands on. Load rolls up per distro across every screen.">
                        <option value="">— distro —</option>
                        ${this.getDistros().map(d => `<option value="${d.id}" ${assigned === d.id ? 'selected' : ''}>${this._esc ? this._esc(d.name) : d.name}</option>`).join('')}
                    </select>
                    <input type="text" class="power-soca-length" data-soca="${s.soca}" data-lrd-field="power-soca-length-${s.soca}" value="${(s.length || '').replace(/"/g, '&quot;')}" placeholder="e.g. 100ft" style="width: 74px;">
                </div>`; }).join('')}
            <div class="info-row checkbox-row" data-tooltip="Soca Brackets, Draw a bracket over each multi's span on the power map with its name and home-run length.">
                <input type="checkbox" id="show-soca-brackets" data-lrd-field="show-soca-brackets" ${layer.showSocaBrackets !== false ? 'checked' : ''}>
                <label for="show-soca-brackets">Soca Brackets on Map</label>
            </div>`;
        host.querySelectorAll('.power-soca-length').forEach(inp => {
            inp.addEventListener('change', () => {
                this.setSocaLength(layer, Number(inp.dataset.soca), inp.value);
            });
        });
        host.querySelectorAll('.power-soca-distro').forEach(sel => {
            sel.addEventListener('change', () => {
                this.setSocaDistro(layer, Number(sel.dataset.soca), sel.value || null);
                // The distro panel is still the next host after this one -
                // soca, splitters, distros kept their order when they moved
                // into the Power panel - so tabbing on from a soca row walks
                // into the very thing this would wipe. Defer past the gesture
                // (see _rebuildAfterGesture).
                this._rebuildAfterGesture(() => this.refreshDistroPanel());
            });
        });
        const sel = host.querySelector('#power-breakout-type');
        if (sel) sel.addEventListener('change', () => {
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.powerBreakoutType = sel.value; });
            this.updateLayers(list);
        });
        const brk = host.querySelector('#show-soca-brackets');
        if (brk) brk.addEventListener('change', () => {
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.showSocaBrackets = brk.checked; });
            this.updateLayers(list);
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
    }

    // The Splitters block beside the soca panel: the per-screen packing
    // toggle and splitter size, plus one row per circuit for the manual
    // merge/split override. Rendered like refreshSocaRuns (same focus
    // doctrine, same _rebuildAfterGesture flow), with ids/classes DISTINCT
    // from the soca panel's.
    refreshSplitterPanel() {
        const host = document.getElementById('power-splitters');
        if (!host) return;
        this._preserveEditorFocus();
        const layer = this.currentLayer;
        if (!layer || (layer.type || 'screen') !== 'screen') { host.innerHTML = ''; return; }
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        // Rows appear when the manual lever means something: packed auto
        // circuits, or drawn custom circuits (merge-only - drawn numbering
        // is user intent and is never auto-packed).
        const circuits = (sp.enabled || custom) ? this.screenCircuits(layer) : [];
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const esc = (s) => this._esc ? this._esc(s) : s;
        const stockWays = [2, 3, 4];
        const isStock = stockWays.includes(sp.maxWays);
        const rowHtml = circuits.map(c => {
            const branches = (c.branches && c.branches.length) ? c.branches : [c.panels];
            const srcLayers = c.layers || [];
            const watts = c.panels.reduce((s, p, pi) => {
                const src = srcLayers[pi];
                const w = (src && src !== layer)
                    ? (parseFloat(src.panelWatts) || 0)
                    : (parseFloat(layer.panelWatts) || 0);
                return s + w * this.getPanelLoadFactor(src || layer, p);
            }, 0);
            const amps = voltage ? watts / voltage : 0;
            const over = amperage > 0 && amps > amperage;
            const comp = branches.map(b => b.length).join('+');
            const label = this.getPowerCircuitLabel(layer, c.num);
            return `
                <div class="info-row splitter-circuit-row" style="align-items:center; gap:6px;">
                    <input type="checkbox" class="splitter-circuit-pick" data-circuit="${c.num}" data-lrd-field="splitter-circuit-pick-${c.num}">
                    <label style="font-weight:400; flex:1;">${esc(label)} · ${branches.length > 1 ? `${branches.length} runs (${comp} tiles) via ${branches.length}fer` : `${c.panels.length} tiles`} · ${amps.toFixed(1)} A${over ? ' <span style="color:#c0392b; font-weight:600;">OVER</span>' : ''}</label>
                </div>`;
        }).join('');
        host.innerHTML = `
            <label style="font-weight: 600; margin-bottom: 6px; display: block;" data-tooltip="Power splitters, Share one circuit between adjacent short power runs through a 2fer/3fer/4fer Y-cable. Organized modes pack whole rows or columns as separate runs on a shared feed; Maximize already fills each circuit to capacity, so packing changes nothing there.">Splitters</label>
            <div class="info-row checkbox-row" data-tooltip="Circuit sharing, Gang consecutive row/column runs onto one shared circuit through a splitter, up to the splitter size and the circuit capacity. Only adjacent runs share - a run is never skipped to pair two non-neighbours.">
                <input type="checkbox" id="power-splitters-enabled" data-lrd-field="power-splitters-enabled" ${sp.enabled ? 'checked' : ''}>
                <label for="power-splitters-enabled">Share circuits via splitters</label>
            </div>
            <div class="info-row" style="align-items:center;" data-tooltip="Splitter size, The largest Y-cable the packer may use. It always uses the smallest that fits: none, then 2fer, then 3fer.">
                <label style="font-weight:400;">Max splitter</label>
                <select id="power-splitters-maxways" data-lrd-field="power-splitters-maxways" class="info-select" style="width: 96px;">
                    ${stockWays.map(w => `<option value="${w}" ${isStock && sp.maxWays === w ? 'selected' : ''}>${w}fer</option>`).join('')}
                    <option value="custom" ${isStock ? '' : 'selected'}>Custom…</option>
                </select>
                ${isStock ? '' : `<input type="number" id="power-splitters-maxways-custom" data-lrd-field="power-splitters-maxways-custom" min="2" step="1" value="${sp.maxWays}" style="width: 56px;">`}
            </div>
            ${circuits.length ? `
            <div id="power-splitter-rows">${rowHtml}</div>
            <div class="info-row" style="gap:8px;">
                <button id="power-splitters-merge" data-lrd-field="power-splitters-merge" class="btn btn-secondary" style="padding:2px 10px;" data-tooltip="Merge selected, Gang the checked circuits onto ONE shared circuit through a splitter. Honored even over capacity - the row flags OVER.">Merge selected</button>
                <button id="power-splitters-split" data-lrd-field="power-splitters-split" class="btn btn-secondary" style="padding:2px 10px;" data-tooltip="Split, Un-merge the checked circuits and pin their runs out of auto packing.">Split</button>
            </div>` : ''}`;
        // Multi-select doctrine: the enabled/maxWays edits apply to EVERY
        // selected screen (same helper as the soca panel's scalar settings);
        // manual merge/split rows are inherently per-screen.
        const writeAll = (patch) => {
            const list = this._socaPanelTargets(layer);
            list.forEach(l => {
                const cur = this.getPowerSplitters(l);
                l.powerSplitters = { ...cur, ...patch,
                    manual: cur.manual };
            });
            this.updateLayers(list);
            this._rebuildAfterGesture(() => {
                this.refreshSplitterPanel();
                this.refreshSocaRuns();
                this.refreshDistroPanel();
                this.updatePowerLabelEditor && this.updatePowerLabelEditor();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        };
        const en = host.querySelector('#power-splitters-enabled');
        if (en) en.addEventListener('change', () => writeAll({ enabled: en.checked }));
        const mw = host.querySelector('#power-splitters-maxways');
        if (mw) mw.addEventListener('change', () => {
            if (mw.value === 'custom') {
                // seed the custom input with a non-stock value so it renders
                writeAll({ maxWays: 5 });
                return;
            }
            writeAll({ maxWays: parseInt(mw.value, 10) || 3 });
        });
        const mwc = host.querySelector('#power-splitters-maxways-custom');
        if (mwc) mwc.addEventListener('change', () => {
            writeAll({ maxWays: Math.max(2, parseInt(mwc.value, 10) || 2) });
        });
        const picked = () => [...host.querySelectorAll('.splitter-circuit-pick:checked')]
            .map(el => parseInt(el.dataset.circuit, 10))
            .filter(n => Number.isFinite(n));
        const mergeBtn = host.querySelector('#power-splitters-merge');
        if (mergeBtn) mergeBtn.addEventListener('click', () => {
            this.mergeSplitterCircuits(layer, picked());
        });
        const splitBtn = host.querySelector('#power-splitters-split');
        if (splitBtn) splitBtn.addEventListener('click', () => {
            this.splitSplitterCircuits(layer, picked());
        });
    }

    // Merge the selected circuits into one manual group. The group is stored
    // as RUN ids: for auto screens the run ordinals the selected circuits
    // currently carry, for custom screens the drawn circuit numbers. Members
    // leave any previous group and lose their split pins.
    mergeSplitterCircuits(layer, circuitNums) {
        if (!layer || !Array.isArray(circuitNums) || circuitNums.length < 2) return;
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (runIds.length < 2) return;
        this._writeSplitterManual(layer, (manual) => {
            const inNew = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !inNew.has(n)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(n => !inNew.has(n));
            manual.merge.push([...runIds].sort((a, b) => a - b));
        });
    }

    // Un-merge the selected circuits. Auto runs are additionally PINNED out
    // of packing (one circuit per run) - the pin is what defeats a re-pack;
    // custom circuits just fall back to their drawn numbering.
    splitSplitterCircuits(layer, circuitNums) {
        if (!layer || !Array.isArray(circuitNums) || !circuitNums.length) return;
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (!runIds.length) return;
        const custom = this.usesCustomCircuits(layer);
        this._writeSplitterManual(layer, (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(n)) : []))
                .filter(g => g.length >= 2);
            if (!custom) {
                manual.split = [...new Set([...manual.split, ...runIds])]
                    .sort((a, b) => a - b);
            }
        });
    }

    _writeSplitterManual(layer, fn) {
        const cur = this.getPowerSplitters(layer);
        const manual = {
            merge: cur.manual.merge.map(g => (Array.isArray(g) ? g.slice() : [])),
            split: cur.manual.split.slice(),
        };
        fn(manual);
        layer.powerSplitters = { ...cur, manual };
        this.updateLayers([layer]);
        this._rebuildAfterGesture(() => {
            this.refreshSplitterPanel();
            this.refreshSocaRuns();
            this.refreshDistroPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
    }

    // Multi-select doctrine: a panel edit applies to EVERY selected screen,
    // not just the one the panel happens to show. Per-screen scalar settings
    // (brackets toggle, breakout type) go through here; per-multi fields
    // (lengths, distro assignments) stay with their own screen's soca plan.
    _socaPanelTargets(layer) {
        const sel = this.getSelectedLayers().filter(l => (l.type || 'screen') === 'screen');
        return sel.some(l => l.id === layer.id) ? sel : [layer, ...sel];
    }

    // ---- Power splitters (circuit sharing via 2fer/3fer/4fer Y-cables) ------
    //
    // Real rigs gang multiple SHORT adjacent power runs onto ONE circuit
    // through a splitter: a wall cabled top-down in 5-tall columns with a
    // 15-tile circuit capacity feeds three adjacent columns from one feed
    // labelled S1-1, through a 3fer. The model rides on the layer:
    //   layer.powerSplitters = {
    //     enabled: false,          // AUTO packing (organized modes only)
    //     maxWays: 3,              // 2fer/3fer out of the box; any int >= 2
    //     manual: {
    //       merge: [[runId, ...], ...],   // hand-ganged runs, one group = one circuit
    //       split: [runId, ...],          // runs pinned OUT of auto packing
    //     },
    //   }
    // Run ids: the pre-packing run ordinal (1-based, traversal order) for
    // auto modes; the drawn circuit number for custom screens.

    // Normalized read - the raw field may be absent or partial.
    getPowerSplitters(layer) {
        const raw = (layer && layer.powerSplitters) || {};
        const mw = parseInt(raw.maxWays, 10);
        const manual = raw.manual || {};
        return {
            enabled: !!raw.enabled,
            maxWays: Number.isFinite(mw) && mw >= 2 ? mw : 3,
            manual: {
                merge: Array.isArray(manual.merge) ? manual.merge : [],
                split: Array.isArray(manual.split) ? manual.split : [],
            },
        };
    }

    // Validated-on-read manual groups against the run ids that currently
    // exist. Ids that no longer resolve are silently dropped; a group left
    // with fewer than two members dissolves; a run can sit in only one group
    // (first wins), and a run inside a group cannot also be split-pinned.
    appliedSplitterGroups(layer, validIds) {
        const sp = this.getPowerSplitters(layer);
        const valid = new Set((validIds || []).map(n => parseInt(n, 10)));
        const used = new Set();
        const merge = [];
        for (const g of sp.manual.merge) {
            if (!Array.isArray(g)) continue;
            const ids = [...new Set(g.map(n => parseInt(n, 10)))]
                .filter(n => valid.has(n) && !used.has(n))
                .sort((a, b) => a - b);
            if (ids.length < 2) continue;
            ids.forEach(n => used.add(n));
            merge.push(ids);
        }
        const split = [...new Set(sp.manual.split.map(n => parseInt(n, 10)))]
            .filter(n => valid.has(n) && !used.has(n))
            .sort((a, b) => a - b);
        return { merge, split };
    }

    // Pack runs into circuits. Greedy over CONSECUTIVE runs only - never
    // skip a run to gang two non-neighbours: a circuit keeps taking the next
    // run while the summed load fits wattsPerCircuit and the branch count
    // stays within maxWays (the packer thereby uses the smallest splitter
    // that fits: none, then 2fer, then 3fer). A run that does not fit closes
    // the circuit and starts the next. Manual overrides ride the same walk:
    // a merge group is emitted whole as one circuit when its first member is
    // reached (honored even over capacity - the soca `over` convention flags
    // it); a split-pinned run is its own circuit and a boundary.
    // Returns { circuits, runs, runIds } index-aligned: circuits[i] is the
    // concatenated panels, runs[i] the per-branch panel counts, runIds[i]
    // the run ordinals ganged into that circuit.
    _packPowerRuns(runs, wattsPerCircuit, maxWays, manual) {
        const N = runs.length;
        const groupOf = new Map();
        ((manual && manual.merge) || []).forEach(g =>
            g.forEach(id => groupOf.set(id, g)));
        const splitSet = new Set((manual && manual.split) || []);
        const consumed = new Set();
        const circuits = [], counts = [], runIds = [];
        for (let i = 0; i < N; i++) {
            const id = i + 1;
            if (consumed.has(id)) continue;
            let members;
            const g = groupOf.get(id);
            if (g) {
                members = g.filter(n => !consumed.has(n));
            } else if (splitSet.has(id)) {
                members = [id];
            } else {
                members = [id];
                let load = runs[i].load;
                for (let j = i + 1; j < N; j++) {
                    const nid = j + 1;
                    if (members.length >= maxWays) break;
                    if (groupOf.has(nid) || splitSet.has(nid)) break;
                    if (load + runs[j].load > wattsPerCircuit) break;
                    members.push(nid);
                    load += runs[j].load;
                }
            }
            members.forEach(n => consumed.add(n));
            circuits.push(members.flatMap(n => runs[n - 1].panels));
            counts.push(members.map(n => runs[n - 1].panels.length));
            runIds.push(members.slice());
        }
        return { circuits, runs: counts, runIds };
    }

    // The drawn path steps a (possibly merged) custom circuit covers - the
    // label sheets stamp every tile of a shared circuit with the ONE label,
    // so the sticker run for merged circuit `num` concatenates every member
    // path, not just the primary's.
    _splitterMergedPathFor(layer, num) {
        const paths = (layer && layer.powerCustomPaths) || {};
        const own = paths[num] || [];
        const drawnNums = Object.keys(paths)
            .map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && (paths[n] || []).length > 0);
        const groups = this.appliedSplitterGroups(layer, drawnNums).merge;
        const g = groups.find(x => x[0] === parseInt(num, 10));
        if (!g) return own;
        return g.flatMap(n => paths[n] || []);
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

            // Splitter packing: one RUN per unit (row/column) - each branch
            // is its own short daisy fed at its head, the physical truth of
            // a wall cabled top-down - then _packPowerRuns gangs consecutive
            // runs onto shared circuits within maxWays and capacity. The
            // single-unit-too-big error is unchanged. Off by default; the
            // default path below is byte-identical to the pre-splitter code.
            const splitters = this.getPowerSplitters(layer);
            if (splitters.enabled) {
                const runs = [];
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
                    runs.push({
                        panels: this.getOrganizedPanelsForUnits(
                            layer, pattern, isHorizontalFirst, [idx], false),
                        load: unitLoad,
                    });
                }
                const manual = this.appliedSplitterGroups(
                    layer, runs.map((_, i) => i + 1));
                const packed = this._packPowerRuns(
                    runs, wattsPerCircuit, splitters.maxWays, manual);
                return { circuits: packed.circuits, runs: packed.runs,
                         runIds: packed.runIds, error: null };
            }

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

    // Which multi and which PHYSICAL TAIL of its 6-way fan a circuit lands
    // on, resolved through the soca plan (screenCircuits order) and the
    // per-circuit fan positions (phase balancing / breaker offset).
    //
    // `moved` is per-soca: true only when that soca's circuits sit on
    // non-natural positions. The label authority below uses the slot ONLY
    // then, so screens nobody balanced keep their labels byte-identical -
    // including custom-drawn screens with gaps in the numbering, where the
    // drawn number is user intent.
    //
    // Cached for the current render burst: one screenCircuits walk per layer,
    // cleared on the next microtask, so a canvas full of labels does not
    // rebuild the plan per bubble.
    _circuitTailSlot(layer, circuitNum) {
        if (!layer || typeof this.screenCircuits !== 'function') return null;
        if (!this._circuitTailCache) {
            this._circuitTailCache = new Map();
            Promise.resolve().then(() => { this._circuitTailCache = null; });
        }
        let slots = this._circuitTailCache.get(layer);
        if (!slots) {
            slots = new Map();
            const tm = String(layer.powerLabelTemplate || 'S1-#')
                .match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
            const startMulti = tm ? parseInt(tm[2], 10) || 1 : 1;
            const circuits = this.screenCircuits(layer) || [];
            const perSoca = new Map();   // soca -> [circuit num] in plan order
            circuits.forEach((c, ci) => {
                const soca = startMulti + Math.floor(ci / 6);
                const arr = perSoca.get(soca) || [];
                arr.push(c.num);
                perSoca.set(soca, arr);
            });
            for (const [soca, nums] of perSoca) {
                const pos = this.socaCircuitPositions(layer, soca, nums.length);
                const moved = !pos.every((p, i) => p === i + 1);
                nums.forEach((num, i) =>
                    slots.set(num, { multi: soca, tail: pos[i], moved }));
            }
            this._circuitTailCache.set(layer, slots);
        }
        return slots.get(parseInt(circuitNum, 10)) || null;
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
            // v0.12.0: once phase balancing (or a breaker offset) lands this
            // soca's circuits on other tails of the fan, the AUTO label names
            // the TRUE PHYSICAL TAIL - S1-6 for tail 6, gaps allowed. The
            // tail range is the soca HARDWARE's 6 legs, never the used-leg
            // count. Explicit overrides above stay the user's text verbatim;
            // screens on natural positions keep the arithmetic below
            // byte-identical (the drawn number is user intent).
            const slot = this._circuitTailSlot(layer, n);
            if (slot && slot.moved) return `${prefix}${slot.multi}${sep}${slot.tail}${suffix}`;
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

    // The synchronous sibling of the round-trip delay _preserveEditorFocus()
    // was written for.
    //
    // The label editors above only rebuild when the PUT response (or socket
    // echo) lands, so by the time their wipe runs the Tab gesture is over and
    // document.activeElement IS the field the user landed in - the helper can
    // see it and put it back. Several editors in this suite (the Port List
    // name cells, the patch rail, the distro panel, the soca runs) restate
    // their DOM synchronously inside the field's own `change` handler
    // instead. That runs MID-gesture: the browser has already chosen the next
    // tab stop but not focused it yet, so the wipe destroys a target no
    // capture can know about and focus falls to <body>.
    //
    // So those sites push the restate one macrotask out. The gesture then
    // completes onto the real element, and the rebuild that follows goes
    // through _preserveEditorFocus() exactly like every round-trip rebuild
    // does. Model writes and undo snapshots stay in the handler - only the
    // DOM restatement moves.
    _rebuildAfterGesture(fn) {
        setTimeout(fn, 0);
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

            // v0.12.0: once balancing (or a breaker offset) moves this
            // multi's circuits onto other tails of the fan, the number
            // column shows the PHYSICAL TAIL - the same digit the canvas
            // bubble and breaker sticker carry - through the same slot the
            // label authority reads. A balanced wall on tails {1,2,3,5,6}
            // lists 1, 2, 3, 5, 6 down the editor, never 1..5. Screens on
            // natural positions keep today's sequential column
            // byte-identical (`moved` gates exactly like the labels).
            const slot = this._circuitTailSlot(this.currentLayer, circuitNum);
            const moved = !!(slot && slot.moved);

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit', String(circuitNum));
            // Tab out of a circuit's label field lands here, on the next
            // row's checkbox - the first thing the rebuild destroys.
            cb.dataset.lrdField = `power-check-${circuitNum}`;
            cb.title = moved
                ? this.getPowerCircuitLabel(this.currentLayer, circuitNum)
                : `Circuit ${circuitNum}`;
            cb.style.margin = '0';

            const numLabel = document.createElement('div');
            numLabel.style.fontSize = '13px';
            numLabel.style.fontWeight = '700';
            numLabel.style.color = '#ccc';
            numLabel.style.textAlign = 'center';
            numLabel.style.fontFamily = 'monospace';
            numLabel.textContent = String(moved ? slot.tail : circuitNum);

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
