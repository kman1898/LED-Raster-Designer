// app-power: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';

class _Power {

    // While ONE overridden run is open for redrawing, the editable runs ARE
    // the layer's overrides, so the step walks that list (clamped at its
    // ends) instead of the open number line - stepping onto a port the user
    // never took over would make the next click take it over silently.
    _steppedCustomIndex(layer, kind, delta) {
        const current = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        if (!this._isOverrideEditing(layer, kind)) {
            return Math.max(1, current + delta);
        }
        const nums = this.getOverrideNums(layer, kind);
        const at = nums.indexOf(current);
        const next = at === -1 ? 0
            : Math.max(0, Math.min(nums.length - 1, at + delta));
        return nums[next];
    }

    // A step button (Next / Prev, data and power) is a MOUSE control. A
    // button keeps keyboard focus after a click, and a focused button
    // re-fires on Enter and Space - so "click Next, press Enter" stepped
    // twice and the circuit numbers skipped one, which is how a brand-new
    // show ended up drawn 1-4, 6-23 (user, 2026-09-03). Tab from the
    // focused button used to step too; the document handler in canvas.js
    // now leaves Tab to a focused control. The keyboard's way to step is
    // Tab / Shift+Tab and [ / ] on the canvas, unchanged - the buttons
    // themselves just stop answering keys.
    _armStepButton(btn) {
        if (!btn) return;
        const swallow = (e) => {
            if (e.code === 'Enter' || e.code === 'NumpadEnter' || e.code === 'Space') {
                e.preventDefault();
            }
        };
        btn.addEventListener('keydown', swallow);
        btn.addEventListener('keyup', swallow);
    }

    stepCustomPort(delta) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        const view = window.canvasRenderer.viewMode;
        if (view === 'data-flow' && this.isCustomFlowEditing(this.currentLayer)) {
            this.ensureCustomFlowState(this.currentLayer);
            this.currentLayer.customPortIndex =
                this._steppedCustomIndex(this.currentLayer, 'data', delta);
            if (this._overrideEditing && this._overrideEditing.kind === 'data'
                    && this._overrideEditing.layerId === this.currentLayer.id) {
                this._overrideEditing.num = this.currentLayer.customPortIndex;
            }
            this.saveState('Custom Port Change');
            this.saveClientSideProperties();
            // v0.8.2: PUT to server (keyboard shortcut path needs the same
            // server sync as the on-screen Next/Prev buttons).
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        } else if (view === 'power' && this.isCustomPowerEditing(this.currentLayer)) {
            this.ensureCustomPowerState(this.currentLayer);
            this.currentLayer.powerCustomIndex =
                this._steppedCustomIndex(this.currentLayer, 'power', delta);
            if (this._overrideEditing && this._overrideEditing.kind === 'power'
                    && this._overrideEditing.layerId === this.currentLayer.id) {
                this._overrideEditing.num = this.currentLayer.powerCustomIndex;
            }
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
        // Same again for the group's "Route <name> as one screen" row: it has
        // to HIDE when the selection moves to an ungrouped screen, an image
        // layer or nothing at all, so it runs ahead of the early returns too.
        if (typeof this.updateGroupRouteControl === 'function') {
            this.updateGroupRouteControl();
        }

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
            // v0.12: cabinets and NO ports is an error only when nothing is
            // feeding them. A member of a group that routes as one screen is
            // fed by the member that owns the walk, and a member every one of
            // whose cabinets sits on a peer's hand-drawn cable is fed by that
            // cable - in both cases zero is the honest figure and the wall's
            // real port count is on the group row in the Screens list. Without
            // this every peer of a crossing group reads a red ERROR while the
            // wall beside it is correctly routed.
            const servedByPeer = typeof this.isServedByPeerRouting === 'function'
                && this.isServedByPeerRouting(this.currentLayer, 'data');
            if ((this.currentLayer._capacityError || noCapacity
                    || (portsRequired === 0 && panelsPerPort > 0
                        && panelCountForStatus > 0 && !servedByPeer))) {
                portsRequiredEl.textContent = 'ERROR';
                portsRequiredEl.style.color = '#ff0000';
            } else if (panelCountForStatus === 0 || servedByPeer) {
                portsRequiredEl.textContent = '0';
                portsRequiredEl.style.color = 'var(--ps-dim, #c0c0c0)';
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
        // The cap under the custom controls reads the same figures.
        this._syncCustomFillReadout('data');
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
        // The engine's own numbers ride with the rows (per-run overrides gap
        // the sequence); a stale keys array against fresh rows would label a
        // circuit with its neighbour's number.
        layer._powerCircuitNumKeys = powerAssignments.nums || null;

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString() : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        if (amps1El) amps1El.textContent = totalAmps1 ? totalAmps1.toFixed(2) + ' A' : '0';
        if (amps3El) amps3El.textContent = totalAmps3 ? totalAmps3.toFixed(2) + ' A' : '0';
        // The cap under the custom controls reads the same figures.
        this._syncCustomFillReadout('power');
        // Deferred, not called inline: this runs synchronously inside the
        // change handlers of the static Power fields (panel watts, voltage,
        // amperage). The knob syncs are cheap, but refreshDistroPanel is a
        // whole dock render (its wipe included), and this same path runs
        // from controls whose Tab is still mid-flight - an inline wipe
        // destroys the field Tab is about to land in. See
        // _rebuildAfterGesture.
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
            // `nums` exists only when per-run overrides are in play: the auto
            // circuits skip the overridden numbers and the overridden ones
            // keep theirs, so i + 1 stops being the truth there.
            const c = { num: res.nums ? res.nums[i] : i + 1, panels };
            // v0.12: an AUTOMATIC circuit can now cross into a group peer too,
            // so it carries the same index-aligned `layers` a hand-drawn
            // crossing circuit has carried since v0.11.0 - getSocaPlan charges
            // each cabinet at its own member's wattage off this. Absent for
            // every non-crossing plan, exactly as before.
            if (res.layers && res.layers[i]) c.layers = res.layers[i];
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

    // ---- multi splits --------------------------------------------------------
    //
    // How a screen's circuits group into multis used to be pure arithmetic -
    // floor(ordinal / 6) - which is exactly why the reference show could not
    // land "the 2 remaining circuits" on another box without hand-typed
    // labels: the remainder was welded to its 6-block. A SPLIT breaks one
    // multi at a user-chosen circuit boundary, and each resulting part is a
    // multi in its own right - its own tile, its own (distro, number), so a
    // 2-circuit tail can pin onto another box's free tails through the
    // ordinary shared-soca gesture.
    //
    // The store is `layer.powerSocaSplits`: an array of 1-based circuit
    // ordinals (position in the plan's circuit order, splitter merges
    // already applied) after which a multi ends early. Boundaries compose
    // with the fixed 6-grid rather than re-wrapping it: 14 circuits with a
    // break after 2 read [1-2][3-6][7-12][13-14], so every multi AFTER the
    // split keeps the span it always had and only the indexes step. No
    // stored splits = the exact floor(/6) segmentation, byte for byte.

    // Normalized read: distinct interior ordinals, ascending. Points at or
    // past the end of the plan (the wall shrank) are ignored, not deleted -
    // the same degrade-on-read rule the tail stores follow.
    _socaSplitPoints(layer, count) {
        const raw = (layer && layer.powerSocaSplits) || [];
        if (!Array.isArray(raw)) return [];
        return [...new Set(raw.map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1
                && (count == null || n < count)))]
            .sort((a, b) => a - b);
    }

    // The plan's multis as contiguous ordinal runs: [{index, start, end,
    // userEnd}], 1-based inclusive. Boundaries are the fixed box grid (six
    // for a soca, three for an L21-30 - socaBoxSize) plus every stored
    // split point; `userEnd` marks a part whose END is a stored point -
    // the boundary the "Merge back into …" gesture removes.
    _socaSegments(layer, count) {
        const n = Math.max(0, Number(count) || 0);
        if (!n) return [];
        const size = this.socaBoxSize(layer);
        const stored = new Set(this._socaSplitPoints(layer, n));
        const segs = [];
        let start = 1;
        for (let i = 1; i <= n; i++) {
            if (i === n || i % size === 0 || stored.has(i)) {
                segs.push({ index: segs.length + 1, start, end: i,
                            userEnd: stored.has(i) });
                start = i + 1;
            }
        }
        return segs;
    }

    // ordinal (1-based) -> soca index, flat for the per-circuit walks.
    _socaIndexByOrdinal(segs) {
        const idx = [];
        segs.forEach(s => {
            for (let i = s.start; i <= s.end; i++) idx[i] = s.index;
        });
        return idx;
    }

    // How many multis `count` circuits make on this screen - the split-aware
    // replacement for ceil(count / 6), shared with the canvas info line.
    socaCountFor(layer, count) {
        return this._socaSegments(layer, count).length;
    }

    // Insert (delta +1) or remove (delta -1) one multi's slot at `at` in
    // every per-multi store, the way an array splice would: a split gives
    // the new second part a clean slate and every later multi keeps its
    // name, distro, number, length and tails under its stepped index.
    // Removal drops slot `at`'s own entries with it.
    _spliceSocaStores(layer, at, delta) {
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const map = layer[field];
            if (!map || typeof map !== 'object') continue;
            const next = {};
            for (const key of Object.keys(map)) {
                const n = parseInt(key, 10);
                // Not a multi index, so not ours to move - carried across,
                // same rule as migrateSocaKeying.
                if (!Number.isFinite(n)) { next[key] = map[key]; continue; }
                if (delta > 0) next[n >= at ? n + 1 : n] = map[key];
                else if (n === at) continue;
                else next[n > at ? n - 1 : n] = map[key];
            }
            layer[field] = next;
        }
    }

    // Re-key every per-multi store from the OLD segmentation to a NEW set
    // of split points, in one move - the general form of the splice above
    // for gestures that change several boundaries at once (a clear that
    // forgets the cuts at its edges, a drop that absorbs the one-circuit
    // leftovers in its span). Each old multi is followed by its START
    // ordinal: whichever new segment holds that circuit inherits the
    // stores under the new index. When two old multis land in one new
    // segment the FIRST claimant wins, per store: the earlier multi's
    // entry stands, the later's drops, and a field the earlier never set
    // takes the later's - so nothing on file is lost that need not be.
    // The callers arrange that little collides anyway: a cleared multi
    // was wiped first, an absorbed leftover is unassigned. A multi whose
    // SPAN changed (it grew or was cut) sheds its stored tail set and
    // breaker offset the way the split and un-split always did - the
    // arrangement covered circuits the multi no longer has, or too few
    // for the ones it has now - while name, distro, number and length
    // are identity and carry. Writes `layer.powerSocaSplits` (normalized)
    // and drops the naming cache. Returns Map(oldIndex -> { index:
    // newIndex, same: span unchanged }).
    _resegmentSocaStores(layer, newSplitPoints) {
        if (!layer) return new Map();
        const count = this.screenCircuits(layer).length;
        const oldSegs = this._socaSegments(layer, count);
        layer.powerSocaSplits = this._socaSplitPoints(
            { powerSocaSplits: newSplitPoints }, count);
        const newSegs = this._socaSegments(layer, count);
        const newIdxOf = this._socaIndexByOrdinal(newSegs);
        const map = new Map();
        for (const s of oldSegs) {
            const ni = newIdxOf[s.start];
            if (!ni) continue;
            const t = newSegs[ni - 1];
            map.set(s.index, { index: ni,
                               same: t.start === s.start && t.end === s.end });
        }
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const store = layer[field];
            if (!store || typeof store !== 'object') continue;
            const next = {};
            const keys = Object.keys(store).sort((a, b) =>
                (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));
            for (const key of keys) {
                const n = parseInt(key, 10);
                // Not a multi index, so not ours to move - carried across,
                // same rule as _spliceSocaStores.
                if (!Number.isFinite(n)) { next[key] = store[key]; continue; }
                const m = map.get(n);
                if (!m) continue;
                if (!m.same && (field === 'powerSocaPhasePos'
                                || field === 'powerSocaPhaseOffset')) continue;
                if (next[m.index] !== undefined) continue;
                next[m.index] = store[key];
            }
            layer[field] = next;
        }
        this._circuitTailCache = null;
        return map;
    }

    // The split MUTATION on its own, no history entry: validation, the
    // incumbent stamp, the store splice. splitSocaAfter wraps it with the
    // one-entry snapshot; the dock's drop-implied split composes it with
    // the assignment that motivated it so the whole gesture is ONE entry.
    // Returns the stamped layers (the incumbents can live on other screens)
    // or null when the cut is not a legal boundary.
    _splitSocaApply(layer, socaIndex, afterLeg) {
        if (!layer) return null;
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const seg = segs.find(s => s.index === Number(socaIndex));
        const cut = parseInt(afterLeg, 10);
        if (!seg || !Number.isFinite(cut) || cut < 1
                || cut >= seg.end - seg.start + 1) return null;
        const boundary = seg.start + cut - 1;
        const points = this._socaSplitPoints(layer, count);
        if (points.includes(boundary)) return null;
        // The first part keeps the pin but sheds circuits, so it re-deals
        // its tails on the box - and if that box is shared, the OTHER
        // members' rendered tails must be held first or the re-deal could
        // slide them (stamped before any store moves, while the naming
        // cache still shows the pre-split wall).
        const stamped = this._materializeSocaBox(
            (layer.powerSocaDistro || {})[socaIndex],
            (layer.powerSocaNumber || {})[socaIndex], layer, socaIndex);
        layer.powerSocaSplits = [...points, boundary].sort((a, b) => a - b);
        this._spliceSocaStores(layer, Number(socaIndex) + 1, +1);
        delete (layer.powerSocaPhasePos || {})[socaIndex];
        delete (layer.powerSocaPhaseOffset || {})[socaIndex];
        // The segmentation just changed, so every read from here on must
        // see the post-split wall - a caller composing further mutations
        // (the drop gesture's second cut, the target-box stamp) included.
        this._circuitTailCache = null;
        return stamped;
    }

    // Break multi `socaIndex` after its `afterLeg`-th circuit (1..legs-1).
    // The first part keeps the multi's identity - name, distro, number,
    // length - and the second starts unassigned; its stored tail set is
    // dropped because the arrangement covered circuits the part no longer
    // has. Contiguous only: a boundary, never a reshuffle.
    splitSocaAfter(layer, socaIndex, afterLeg) {
        const stamped = this._splitSocaApply(layer, socaIndex, afterLeg);
        if (!stamped) return false;
        this.updateLayers([...new Set([layer, ...stamped])], true,
                          'Split Multi');
        return true;
    }

    // ---- a multi dropped on a circuit takes the box's FIRST circuits ------
    //
    // User (2026-09-04): "if i add circuits the numbering is all wrong and
    // when i try and say drag multi 2 onto 6 ports it only lets me do 1
    // because of the incorrect numbering. we need to audit this so it
    // allows me to do up to 6 if i am doing multi/soca. so even if i have
    // 1 circuit taken on multi 1 then i have 5 circuits left and i should
    // only be able to add 5 more to that multi."
    //
    // The wall he was looking at: circuit-pip drops (_dockDropTail) cut
    // before and after their circuit by design, so a run of them leaves a
    // trail of one-circuit multis - S2[7] S3[8] ... - and a slot dropped on
    // circuit 7 used to assign exactly the multi under the cursor: one
    // circuit onto a box with six free. The first take rule reached from
    // the hovered circuit FORWARD to the grid line - hover 6 of a six and
    // one circuit lit, hover 1 and all six did - which read backwards on
    // the wall. User (2026-09-05): "data and power when dragged onto a
    // screen in bulk starts say s1-6 and then as you drag towards 1-1 it
    // fills all 6 circuits. i need it to start at 1-1 instead and increase
    // to 1-6 instead. it is backwards for how it should work." Asked what
    // to anchor to: "So typically you would start with multi 1 so start
    // at the 1st circuit regardless of naming. should just be in order."
    //
    // ONE rule, anchored at the START of the box cell, for the plain
    // whole-multi drop and the mid-multi drop alike (the old "from this
    // circuit on" split-drop is gone - a drop on a later circuit now
    // means "the first N"):
    //
    //   The hovered circuit `o` sits in one cell of the fixed box grid
    //   (_socaSegments always cuts at multiples of socaBoxSize, so a multi
    //   never crosses a grid line and neither does the span). The span
    //   runs from the cell's first circuit TO `o`, in order: hover the
    //   cell's 1st and that circuit alone lights, its 4th and the first
    //   four light, its 6th and all six. Circuits at the head of the cell
    //   that already sit on a DIFFERENT box are somebody's feed and are
    //   never pulled off it by a drop aimed elsewhere: they are skipped,
    //   so the span begins at the first circuit after the last of them
    //   and runs to `o`. Hovering a circuit that itself sits on another
    //   box refuses - nothing lights, the drop says so. "Another box" is
    //   an assignment that is not the target (distroId, number): a pin on
    //   any other number, or any number on another distro. A multi already
    //   on the target box is re-taken (it stays; the span grows around
    //   it), and a same-distro AUTO number holds nothing - it re-deals -
    //   so it is absorbed like an unassigned leftover.
    //
    //   Capacity: min(span, free). `free` is what the box can still hold,
    //   computed the way the join always did - the smallest box size among
    //   the box's members, minus the legs its PINNED incumbents hold (an
    //   auto at that number re-deals and defends nothing); a pinned member
    //   of this screen that overlaps the span counts only the legs that
    //   STAY outside it (the multi re-dropped onto its own box counts at
    //   what stays). Short of the span, the FIRST `free` circuits land
    //   ("took N of M") and the rest stay as their own unassigned multi;
    //   a full box refuses outright and moves nothing. The unassigned
    //   one-circuit leftovers inside the span are absorbed; the remainder
    //   of the cell beyond the span stays as its own multi, keeping the
    //   assignment it had.
    //
    // The store moves are a resegmentation: every stored point strictly
    // inside the taken span removed, a boundary at the span's end where it
    // stops short of the grid line, then _resegmentSocaStores re-keys what
    // survives; the one taken segment gets (distroId, number) with the
    // incumbents' tails frozen first, as every join freezes them, and a
    // remainder cut off a multi that was on a box keeps that box and the
    // tails it was rendering, so nobody moves. ONE history entry for the
    // whole gesture.

    // The resolution on its own, no mutation - the preview lights exactly
    // these circuits and the release takes exactly these circuits, so the
    // two can never disagree. `ordinal` is 1-based in the plan's circuit
    // order. Returns { ok, free, remaining, take, nums, spanStart, spanEnd,
    // ... } - or { ok: false, why: 'other-box' | 'full', free, remaining }
    // for a refusal.
    _socaTakePlan(layer, ordinal, distroId, number) {
        const none = { ok: false, free: 0, remaining: 0, take: 0, nums: [] };
        if (!layer || !distroId) return none;
        const circuits = this.screenCircuits(layer);
        const count = circuits.length;
        const o = parseInt(ordinal, 10);
        if (!Number.isFinite(o) || o < 1 || o > count) return none;
        const segs = this._socaSegments(layer, count);
        const seg = segs.find(s => s.start <= o && o <= s.end);
        if (!seg) return none;
        const size = this.socaBoxSize(layer);
        const n = parseInt(number, 10);
        const assign = layer.powerSocaDistro || {};
        const pins = layer.powerSocaNumber || {};
        const members = this._distroMultiNumbers(distroId).get(n) || [];
        const onTarget = new Set(members
            .filter(m => m.layerId === layer.id).map(m => m.soca));
        // On another box: assigned, and not this box - a pin on another
        // number, or any number on another distro. A same-distro auto at
        // some other number is not holding anything.
        const onOther = s => !!assign[s.index] && !onTarget.has(s.index)
            && (assign[s.index] !== distroId
                || Number.isFinite(parseInt(pins[s.index], 10)));
        if (onOther(seg)) {
            return { ok: false, why: 'other-box', free: 0, remaining: 0,
                     take: 0, nums: [], seg, ordinal: o };
        }
        const cellStart = Math.floor((o - 1) / size) * size + 1;
        const cellEnd = Math.min(count, cellStart + size - 1);
        // The anchor: the cell's first circuit, stepped past every circuit
        // before `o` that is on another box.
        let start = cellStart;
        for (const s of segs) {
            if (s.end < cellStart || s.start > o) continue;
            if (onOther(s)) start = Math.max(start, s.end + 1);
        }
        const remaining = o - start + 1;
        let held = 0;
        // The target box's fan is as big as the SMALLEST breakout claiming
        // it - a 3-tail L21-30 box has three tails whoever else lands on
        // it, and pretending to six would deal tails that do not exist.
        let cap = size;
        for (const m of members) {
            const ml = ((this.project && this.project.layers) || [])
                .find(l => l.id === m.layerId);
            if (ml) cap = Math.min(cap, this.socaBoxSize(ml));
            if (!m.pinned) continue;
            const ms = m.layerId === layer.id
                ? segs.find(s => s.index === m.soca) : null;
            // A pinned member of this screen inside the span is re-taken:
            // only the legs that stay outside the span are held.
            held += (ms && ms.start <= o && ms.end >= start)
                ? Math.max(0, start - ms.start) + Math.max(0, ms.end - o)
                : m.legs;
        }
        const free = Math.max(0, cap - held);
        if (!free) {
            return { ok: false, why: 'full', free, remaining, take: 0,
                     nums: [], seg, ordinal: o, spanStart: start };
        }
        const take = Math.min(remaining, free);
        return {
            ok: true, free, remaining, take, seg, number: n, ordinal: o,
            spanStart: start, spanEnd: start + take - 1, gridEnd: cellEnd,
            nums: circuits.slice(start - 1, start - 1 + take).map(c => c.num),
        };
    }

    // The mutation: resegment, re-key, stamp, assign - ONE history entry
    // under `action`. Returns { ok, took, tailLen, free } (`tailLen` is
    // the span the drop reached for, so a caller can say "took N of M")
    // or { ok: false, why, free, tailLen } for the refusal, with nothing
    // moved.
    takeSocaOnto(layer, ordinal, distroId, number, action) {
        const plan = this._socaTakePlan(layer, ordinal, distroId, number);
        if (!plan.ok) return { ok: false, why: plan.why, free: plan.free,
                               tailLen: plan.remaining };
        const count = this.screenCircuits(layer).length;
        const size = this.socaBoxSize(layer);
        const segs = this._socaSegments(layer, count);
        const start = plan.spanStart;
        const end = plan.spanEnd;
        const touched = new Set([layer]);
        // The multi the span's end cuts through, when it runs past it: its
        // remainder keeps the box it was on (2026-09-05 rule: "the
        // remainder ... keeps whatever assignment it had") and the tails
        // it was rendering for those circuits, so a re-drop onto the same
        // box never reshuffles the cabled fan; the other members of that
        // box hold their rendered tails first, as every split does. Read
        // while the naming cache still shows the pre-drop wall.
        const cut = segs.find(s => s.start <= end && s.end > end);
        const assign = layer.powerSocaDistro || {};
        let carry = null;
        if (cut && assign[cut.index]) {
            const rec = this._powerNaming(layer).socas.get(cut.index);
            const pinNum = parseInt((layer.powerSocaNumber || {})[cut.index], 10);
            const L = cut.end - cut.start + 1;
            const shown = rec && rec.positions;
            const pos = (Array.isArray(shown) && shown.length === L
                && shown.every(p => Number.isInteger(p) && p >= 1 && p <= size)
                && new Set(shown).size === L)
                ? shown.slice(end + 1 - cut.start) : null;
            carry = { distro: assign[cut.index],
                      number: Number.isFinite(pinNum) ? pinNum : null,
                      name: (layer.powerSocaNames || {})[cut.index], pos };
            if (carry.number != null) {
                this._materializeSocaBox(carry.distro, carry.number, layer,
                                         cut.index)
                    .forEach(l => touched.add(l));
            }
        }
        const points = this._socaSplitPoints(layer, count)
            .filter(p => p < start - 1 || p > end);
        if (start > 1 && (start - 1) % size !== 0) points.push(start - 1);
        if (end < count && end % size !== 0) points.push(end);
        this._resegmentSocaStores(layer, points);
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, count));
        const idx = idxOf[start];
        if (carry) {
            const remIdx = idxOf[end + 1];
            const put = (field, v) => {
                (layer[field] || (layer[field] = {}))[remIdx] = v;
            };
            put('powerSocaDistro', carry.distro);
            if (carry.number != null) put('powerSocaNumber', carry.number);
            if (carry.name !== undefined) put('powerSocaNames', carry.name);
            if (carry.pos) put('powerSocaPhasePos', carry.pos);
            this._circuitTailCache = null;
        }
        // Landing on an occupied box is the JOIN: the incumbents' rendered
        // tails freeze first so the taken part deals into what is
        // genuinely free - the same stamp the panel's number pick made.
        this._materializeSocaBox(distroId, plan.number, layer, idx)
            .forEach(l => touched.add(l));
        (layer.powerSocaDistro || (layer.powerSocaDistro = {}))[idx]
            = distroId;
        (layer.powerSocaNumber || (layer.powerSocaNumber = {}))[idx]
            = plan.number;
        this._circuitTailCache = null;
        this.updateLayers([...touched], true, action || 'Assign Multi Distro');
        return { ok: true, took: plan.take, tailLen: plan.remaining,
                 free: plan.free };
    }

    // The drop-implied cut spelled as it always was - multi `socaIndex`,
    // its `afterLeg`-th circuit, box (distroId, number) - now a thin
    // wrapper over takeSocaOnto with the anchored meaning (2026-09-05):
    // the drop lands on the multi's circuit `afterLeg + 1`, so the box
    // takes the cell's FIRST circuits up to that one, and the take rule
    // decides how many of them the box has room for. Kept under its own
    // history name for the callers that ask for a split by name; the
    // dock's drop records the assignment.
    splitSocaOnto(layer, socaIndex, afterLeg, distroId, number) {
        if (!layer || !distroId) return { ok: false, free: 0, tailLen: 0 };
        const count = this.screenCircuits(layer).length;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === Number(socaIndex));
        const cut = parseInt(afterLeg, 10);
        if (!seg || !Number.isFinite(cut) || cut < 1
                || cut >= seg.end - seg.start + 1) {
            return { ok: false, free: 0, tailLen: 0 };
        }
        return this.takeSocaOnto(layer, seg.start + cut, distroId, number,
                                 'Split Multi');
    }

    // Remove the stored boundary at the end of part `socaIndex`: the part
    // and its successor fall back into one natural block. The successor's
    // stores go with its identity; the surviving multi keeps the first
    // part's. Always safe - segmentation re-runs on the 6-grid, so a 6+2
    // that came from a split simply becomes a natural 6+2.
    unsplitSocaAfter(layer, socaIndex) {
        if (!layer) return false;
        const count = this.screenCircuits(layer).length;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === Number(socaIndex));
        if (!seg || !seg.userEnd) return false;
        // The welded multi keeps the first part's pin with MORE circuits,
        // so it re-deals on its box exactly like a split part does - the
        // other members of a shared box hold their rendered tails first.
        const stamped = this._materializeSocaBox(
            (layer.powerSocaDistro || {})[socaIndex],
            (layer.powerSocaNumber || {})[socaIndex], layer, socaIndex);
        layer.powerSocaSplits = this._socaSplitPoints(layer, count)
            .filter(p => p !== seg.end);
        this._spliceSocaStores(layer, Number(socaIndex) + 1, -1);
        delete (layer.powerSocaPhasePos || {})[socaIndex];
        delete (layer.powerSocaPhaseOffset || {})[socaIndex];
        this._circuitTailCache = null;
        this.updateLayers([...new Set([layer, ...stamped])], true,
                          'Un-split Multi');
        return true;
    }

    // ---- one circuit off its box, the rest of the multi staying put -----
    //
    // User (2026-09-05): "lets say i pair 6 circuits on power but i want
    // to delete the 6th circuit from the distro we have no way of doing
    // that. can only clear the whole multi."
    //
    // The circuit chip's clear (and its drag back onto the tray) takes
    // THAT circuit off the box and nothing else. The circuit becomes its
    // own unassigned one-circuit multi - a cut before it where it is not
    // already a segment start, a cut after it where it is not the multi's
    // last - and the rest of the multi stays exactly as the wall showed
    // it: the HEAD part (the circuits before it) keeps the multi's
    // identity - typed name, home-run length, distro, number - and holds
    // the tails it was rendering; a TAIL part (the circuits after it, when
    // the circuit was in the middle) stays on the SAME box, (distroId,
    // number), holding the tails IT was rendering, so SR1-1 SR1-2 SR1-4
    // SR1-5 SR1-6 keep reading exactly that with tail 3 free on the box
    // and nobody moves or renumbers - and a typed multi name rides the
    // tail part too, because the labels derive from it (STAGE LEFT-4
    // must not turn into SR1-4: same name on the same number IS the
    // shared-box shape). The home-run length stays with the head alone:
    // one cable, counted once. When the circuit was the multi's FIRST the
    // identity goes to the part after it - the multi is the circuits
    // that stay, whichever end came off. The other members of a
    // shared box hold their rendered tails first, as every join and split
    // freezes them. The multi's shown number becomes its pin where it was
    // auto - a head and a tail part on one box need the pin to be one box
    // (what was showing becomes held, the tail rule applied to the
    // number).
    //
    // No history entry and none of the circuit's own paperwork here: the
    // dock's _clearCircuitChip wraps this with the wipe of the removed
    // circuit's programming (label override, manual splitter entries) and
    // the one 'Clear Circuit' entry, so a single undo puts back the cuts,
    // the stores and the positions together. Returns { touched,
    // removedIdx } or null when the circuit is not in that multi.
    //
    // The store moves ride _resegmentSocaStores, which follows a multi by
    // its START circuit - the removed circuit itself when it was the
    // first - so this multi's own entries are lifted out before the
    // re-key and put back by hand on the part that keeps the identity;
    // every OTHER multi on the screen keeps its stores under its stepped
    // index the ordinary way. A one-circuit multi has no rest to keep:
    // the dock clears it by the multi-scope rule it always ran.
    _socaReleaseCircuit(layer, socaIndex, circuitNum) {
        if (!layer) return null;
        const idx = Number(socaIndex);
        const rec = this._powerNaming(layer).socas.get(idx);
        const at = rec ? rec.circuits.indexOf(circuitNum) : -1;
        if (!rec || at < 0 || rec.circuits.length < 2) return null;
        const circuits = this.screenCircuits(layer);
        const count = circuits.length;
        const o = circuits.findIndex(c => c.num === circuitNum) + 1;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === idx);
        if (!seg || o < seg.start || o > seg.end) return null;
        const L = rec.circuits.length;
        // The tails the wall was showing, held only when they are a fan
        // arrangement worth holding - the _materializeSocaBox test.
        const cap = this.socaBoxSize(layer);
        const shown = rec.positions;
        const pos = (Array.isArray(shown) && shown.length === L
            && shown.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
            && new Set(shown).size === L) ? shown.slice() : null;
        const n = parseInt(rec.number, 10);
        const onBox = !!rec.distroId && Number.isFinite(n) && n >= 1;
        const touched = new Set([layer]);
        if (onBox) {
            this._materializeSocaBox(rec.distroId, n, layer, idx)
                .forEach(l => touched.add(l));
        }
        const points = this._socaSplitPoints(layer, count);
        if (o > seg.start) points.push(o - 1);
        if (o < seg.end) points.push(o);
        const fields = ['powerSocaDistro', 'powerSocaLengths',
                        'powerSocaPhasePos', 'powerSocaPhaseOffset',
                        'powerSocaNames', 'powerSocaNumber'];
        const carried = {};
        for (const field of fields) {
            const store = layer[field];
            if (!store || store[idx] === undefined) continue;
            carried[field] = store[idx];
            delete store[idx];
        }
        this._resegmentSocaStores(layer, points);
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, count));
        const headIdx = o > seg.start ? idxOf[seg.start] : null;
        const tailIdx = o < seg.end ? idxOf[o + 1] : null;
        const keepIdx = headIdx != null ? headIdx : tailIdx;
        const put = (field, i, v) => {
            (layer[field] || (layer[field] = {}))[i] = v;
        };
        // Identity onto the part that keeps it. The stored tail set and
        // the legacy breaker offset are not carried: the arrangement
        // covered circuits the part no longer has (the split rule) - the
        // shown tails go back on below, part by part.
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaNames', 'powerSocaNumber']) {
            if (carried[field] === undefined) continue;
            put(field, keepIdx, carried[field]);
        }
        if (onBox) {
            put('powerSocaDistro', keepIdx, rec.distroId);
            put('powerSocaNumber', keepIdx, n);
            if (headIdx != null && tailIdx != null) {
                put('powerSocaDistro', tailIdx, rec.distroId);
                put('powerSocaNumber', tailIdx, n);
                if (carried.powerSocaNames !== undefined) {
                    put('powerSocaNames', tailIdx, carried.powerSocaNames);
                }
            }
        }
        if (pos) {
            if (headIdx != null) {
                put('powerSocaPhasePos', headIdx, pos.slice(0, at));
            }
            if (tailIdx != null) {
                put('powerSocaPhasePos', tailIdx, pos.slice(at + 1));
            }
        }
        this._circuitTailCache = null;
        return { touched: [...touched], removedIdx: idxOf[o] };
    }

    getSocaPlan(layer) {
        if (!layer) return [];
        const circuits = this.screenCircuits(layer);   // [{num, panels}] in circuit order
        if (!circuits.length) return [];
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        // `soca` is the multi's STABLE INDEX within this screen, which is what
        // the per-multi stores are keyed by; `number` and `name` come off the
        // show-wide naming index, where numbering runs per distro. The two
        // were the same thing while a multi's number came from the screen's
        // own template - see _powerNaming for why they cannot be.
        const nm = this._powerNaming(layer);
        const socas = new Map();
        // Which multi each circuit belongs to comes from the split-aware
        // segmentation, not floor(/6) - identical while no split is stored.
        const segs = this._socaSegments(layer, circuits.length);
        const idxOf = this._socaIndexByOrdinal(segs);
        circuits.forEach((c, ci) => {
            const n = idxOf[ci + 1];
            const leg = ci + 2 - segs[n - 1].start;
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
            const info = nm.socas.get(n);
            const s = socas.get(n) || {
                soca: n,
                number: info ? info.number : n,
                name: (info && info.name)
                    || this._deriveMultiName(nm.tpl.prefix || 'S',
                                             (nm.tpl.start || 1) + n - 1, nm.tpl),
                distroId: (info && info.distroId) || null,
                legs: [], watts: 0, x1: Infinity, x2: -Infinity
            };
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
    //
    // `boxSize` is how many circuits ONE physical box of this breakout
    // holds - the fan the tails hang off. A soca is six; the L21-30
    // breakout is a 3-circuit box (one 208V circuit per leg pair off a
    // 30A/leg L21-30 feed, user-specified), so its `feedLegA` carries the
    // feed's per-leg rating for the dock's over check. Everything that
    // segments circuits into boxes, deals tails or maps tails onto legs
    // reads the size through socaBoxSize below, never the literal 6.
    getPowerBreakoutTypes() {
        return [
            { id: 'soca-true1', name: 'Multi → True1', connector: 'True1', boxSize: 6, breakoutItem: 'Multi breakouts → True1' },
            { id: 'soca-powercon', name: 'Multi → powerCON', connector: 'powerCON', boxSize: 6, breakoutItem: 'Multi breakouts → powerCON' },
            { id: 'soca-edison', name: 'Multi → Edison (110V)', connector: 'Edison', boxSize: 6, breakoutItem: 'Multi breakouts → Edison', tailItem: 'Edison → panels' },
            { id: 'soca-l620', name: 'Multi → L6-20', connector: 'L6-20', boxSize: 6, breakoutItem: 'Multi breakouts → L6-20', tailItem: 'L6-20 → panels' },
            // The L21-30 breakout (user ruling, 2026-08-28): fed by an
            // L21-30 at 30 A per leg, splitting to 3 x 208V circuits on
            // True1 or powerCON - a leg-PAIR circuit per tail, never a
            // 6-circuit soca. It hangs on a distro number like a multi
            // does, with 3 tails.
            { id: 'l2130-true1', name: 'L21-30 (3 × 208V) → True1', connector: 'True1', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → True1' },
            { id: 'l2130-powercon', name: 'L21-30 (3 × 208V) → powerCON', connector: 'powerCON', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → powerCON' }
        ];
    }

    getPowerBreakout(layer) {
        const types = this.getPowerBreakoutTypes();
        const stored = types.find(t => t.id === (layer && layer.powerBreakoutType));
        if (stored) return stored;
        // No stored choice: a 110V screen defaults to its only legal
        // breakout (user ruling: a 110V screen can only have 110V Edison
        // on it). A stored choice is somebody's paperwork and stands as
        // written, whatever the voltage says now.
        const v = parseFloat(layer && layer.powerVoltage) || 0;
        if (v > 0 && v <= 120) {
            return types.find(t => t.id === 'soca-edison') || types[0];
        }
        return types[0];
    }

    // How many circuits one physical box on THIS screen holds. The one
    // authority for the box shape - segmentation, tail clamps, the balance
    // search, the leg maps and the dock's chip grid all read it, so a
    // 3-tail L21-30 box can never render six chips or deal a tail 4.
    socaBoxSize(layer) {
        const n = Number(this.getPowerBreakout(layer).boxSize);
        return Number.isFinite(n) && n >= 1 ? n : 6;
    }

    // Which breakouts a screen's voltage can legally run (user ruling: a
    // screen set to 110V can only have 110V Edison on it, and the L21-30
    // box is documented as 3 x 208V - nothing else is restricted, and no
    // rule is extrapolated to voltages the ruling does not cover). The
    // select disables what is ineligible; a STORED incompatible choice is
    // somebody's paperwork and keeps displaying, the same doctrine the
    // mismatched phasing scheme follows.
    _breakoutEligible(type, voltage) {
        const v = parseFloat(voltage) || 0;
        if (v > 0 && v <= 120) return type.id === 'soca-edison';
        if (String(type.id).startsWith('l2130-')) return v === 208;
        return true;
    }

    setPowerBreakout(layer, id) {
        if (!layer) return;
        layer.powerBreakoutType = id;
        this.updateLayers([layer], true, 'Change Power Breakout');
    }

    // ---- distro outputs -----------------------------------------------------
    //
    // The connector TYPES a distro can hand a screen (user ruling,
    // 2026-08-31: types only, no counts - the rating already bounds the
    // service and the LEGS line already says where it is). Each type names
    // the screen breakouts it can feed, and that table IS the matching
    // rule: a Multi 208 lands on a Multi -> True1 / powerCON screen, a Multi
    // 120 on an Edison screen, an L21-30 on an L21-30 box. Nothing is
    // extrapolated past the table - a breakout no type names (L6-20) is a
    // mismatch like any other, refused with the fix said out loud, never
    // silently re-typed. `faces` are the breakout connectors the popover
    // row shows beside the type; `badge` is the bracket's text sub-pill.
    //
    // Each type also carries the BOX SHAPE its breakouts share - `boxSize`
    // (six circuits on a soca, three on an L21-30) and `feedLegA` (the
    // L21-30 feed's per-leg rating) - read off the breakout table above,
    // never restated, so a box typed by its chip and a box typed by its
    // occupants' breakout answer to the one authority (2026-09-05, the
    // type moved onto the box: "when a new Multi/group of circuits is
    // where the port type should be moved to").
    getDistroOutputTypes() {
        const bts = this.getPowerBreakoutTypes();
        const shape = (ids) => {
            const m = bts.filter(b => ids.includes(b.id));
            return {
                boxSize: m.length
                    ? Math.min(...m.map(b => Number(b.boxSize) || 6)) : 6,
                feedLegA: Math.max(0, ...m.map(b => Number(b.feedLegA) || 0)),
            };
        };
        return [
            { id: 'soca208', name: 'Multi 208', sub: 'True1 / powerCON',
              glyph: 'soca', faces: ['true1', 'powercon'],
              breakouts: ['soca-true1', 'soca-powercon'], badge: 'MULTI 208' },
            { id: 'soca120', name: 'Multi 120', sub: 'Edison',
              glyph: 'soca', faces: ['edison'],
              breakouts: ['soca-edison'], badge: 'MULTI 120' },
            { id: 'l2130', name: 'L21-30', sub: '3 × 208V',
              glyph: 'l2130', faces: ['true1', 'powercon'],
              breakouts: ['l2130-true1', 'l2130-powercon'], badge: 'L21-30' },
        ].map(t => Object.assign(t, shape(t.breakouts)));
    }

    // What one distro offers, as type records, in catalog order. No
    // `outputs` key - every file from before the key existed, and a
    // freshly added distro - reads as "offers everything", so nothing an
    // older show could drag stops dragging. An explicit list, the empty
    // one included, is somebody's paperwork and stands as written.
    distroOutputs(d) {
        const types = this.getDistroOutputTypes();
        if (!d || !Array.isArray(d.outputs)) return types;
        return types.filter(t => d.outputs.includes(t.id));
    }

    distroOffers(d, typeId) {
        return this.distroOutputs(d).some(t => t.id === typeId);
    }

    // ---- box types: the connector a MULTI BOX is -------------------------
    //
    // The type lives on the box as well as on the distro's OUTPUTS row
    // (user, 2026-09-05: "the soca, l21 and what not is a bit silly on the
    // distro. when a new Multi/group of circuits is where the port type
    // should be moved to you know?" - and, asked where it gets picked,
    // "Type chip on the spare box ... or both places rather"). Stored as
    // `distro.boxTypes = { [number]: typeId }`; the server round-trips a
    // distro as an opaque record (routes_project.py merges the payload
    // wholesale), so no allow-list to extend.
    //
    // THE CONTRACT - distroBoxType(d, number, members?) resolves ONE type
    // for a box, in this order, and says which rung it came from:
    //   1. stored     - boxTypes[number] names a catalog type
    //   2. members    - an occupied box reads the type its members'
    //                   breakout implies, the smallest-fan member deciding
    //                   when they disagree (_resolveSharedSocas' rule), so
    //                   every file from before boxTypes existed reads right
    //   3. neighbour  - a box with nothing on it follows the distro's
    //                   other boxes: the nearest lower-numbered box that
    //                   resolves by rung 1 or 2 (else the nearest higher),
    //                   so a spare on an Edison distro is Edison and never
    //                   needs retyping show after show
    //   4. offered    - the first type the distro offers
    //   5. default    - Multi 208, when the distro offers nothing yet
    // Returns { type, source, implied, clash }: `implied` is rung 2's
    // reading whenever the box is occupied (null when no member's breakout
    // is named by the table), and `clash` is true when a STORED type
    // contradicts it - the stored type still stands (it is somebody's
    // paperwork, never silently overridden) and the dock warns.
    // `members` is _distroMultiNumbers' record for the number; passed in
    // by callers that already hold it, looked up otherwise.
    distroBoxType(d, number, members) {
        const types = this.getDistroOutputTypes();
        const n = parseInt(number, 10);
        const list = Array.isArray(members) ? members
            : (d ? (this._distroMultiNumbers(d.id).get(n) || []) : []);
        let implied = null;
        for (const m of list) {
            const l = ((this.project && this.project.layers) || [])
                .find(x => x.id === m.layerId);
            const t = l ? this.outputTypeForBreakout(this.getPowerBreakout(l))
                : null;
            if (t && (!implied || t.boxSize < implied.boxSize)) implied = t;
        }
        const stored = this.distroStoredBoxType(d, n);
        if (stored) {
            return { type: stored, source: 'stored', implied,
                     clash: !!(implied && implied.id !== stored.id) };
        }
        if (implied) {
            return { type: implied, source: 'members', implied, clash: false };
        }
        const neighbour = this._distroNeighbourBoxType(d, n);
        if (neighbour) {
            return { type: neighbour, source: 'neighbour', implied: null,
                     clash: false };
        }
        // Rungs 4 and 5 read the Multi type PREFERENCE (Distros & multis
        // tab): a distro with an explicit OUTPUTS list offers the
        // preferred type if it is on the list, else its first; a distro
        // offering everything (no list - a fresh one) reads the
        // preference outright. Nothing stored is touched - a box stamped
        // by a drop or typed by its chip has already settled on rung 1.
        const preferred = this._preferredBoxType();
        if (d && Array.isArray(d.outputs)) {
            const offered = this.distroOutputs(d);
            if (offered.length) {
                const pick = offered.find(t => t.id === preferred.id) || offered[0];
                return { type: pick, source: 'offered', implied: null,
                         clash: false };
            }
        }
        return { type: preferred, source: 'default', implied: null,
                 clash: false };
    }

    // The type a box reads when nothing on its distro says otherwise: the
    // Multi type preference, Multi 208 when it names nothing the catalog
    // has.
    _preferredBoxType() {
        const types = this.getDistroOutputTypes();
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return types.find(t => t.id === prefs.multiType) || types[0];
    }

    // Rung 3: what the distro's OTHER boxes are. Only boxes that settle by
    // rung 1 or 2 (a stored type, or members whose breakout names one)
    // count - a memberless untyped box has nothing to say and asking it
    // would ask this question again. The nearest lower number wins (the
    // box before this one), else the nearest higher; null when the distro
    // has no settled box at all.
    _distroNeighbourBoxType(d, number) {
        if (!d) return null;
        const n = parseInt(number, 10);
        const numbers = new Set();
        for (const k of Object.keys(d.boxTypes || {})) numbers.add(parseInt(k, 10));
        for (const k of this._distroMultiNumbers(d.id).keys()) numbers.add(k);
        const settled = [...numbers]
            .filter(k => Number.isFinite(k) && k !== n)
            .map(k => {
                const stored = this.distroStoredBoxType(d, k);
                if (stored) return { k, type: stored };
                const r = this.distroBoxType(d, k);
                return r.source === 'members' ? { k, type: r.type } : null;
            })
            .filter(Boolean);
        if (!settled.length) return null;
        const lower = settled.filter(s => s.k < n).sort((a, b) => b.k - a.k);
        if (lower.length) return lower[0].type;
        return settled.sort((a, b) => a.k - b.k)[0].type;
    }

    // Rung 1 alone: the stored type of box `number`, or null. Reads no
    // member and touches no naming cache, so it is safe from inside the
    // cache's own build.
    distroStoredBoxType(d, number) {
        const map = d && d.boxTypes;
        if (!map || typeof map !== 'object') return null;
        const id = map[parseInt(number, 10)];
        return this.getDistroOutputTypes().find(t => t.id === id) || null;
    }

    // The chip's pick: ONE 'Set Multi Type' entry. A null type forgets the
    // box's stored type (it falls back down the rungs).
    setDistroBoxType(distroId, number, typeId) {
        const d = this.getDistros().find(x => x.id === distroId);
        if (!d) return null;
        const map = Object.assign({}, d.boxTypes || {});
        map[parseInt(number, 10)] = typeId || null;
        return this.updateDistro(distroId, { boxTypes: map }, 'Set Multi Type');
    }

    // The drop's stamp: a plug drop, or a typed spare box's drop, records
    // the type of the box it makes WITHOUT an entry of its own - it runs
    // before the assignment's own saveState, so the gesture stays one
    // undo step and one Ctrl+Z forgets the type with the assignment.
    _stampBoxType(distroId, number, typeId) {
        const d = this.getDistros().find(x => x.id === distroId);
        const n = parseInt(number, 10);
        if (!d || !Number.isFinite(n) || n < 1) return;
        if (!this.getDistroOutputTypes().some(t => t.id === typeId)) return;
        if (!d.boxTypes || typeof d.boxTypes !== 'object') d.boxTypes = {};
        if (d.boxTypes[n] === typeId) return;
        d.boxTypes[n] = typeId;
        this._persistDistros();
    }

    // The output type a screen's (effective) breakout takes, or null for a
    // breakout the table does not name.
    outputTypeForBreakout(bt) {
        const id = bt && bt.id;
        return this.getDistroOutputTypes()
            .find(t => t.breakouts.includes(id)) || null;
    }

    // ---- per-circuit cables: the 10' True1 on circuit 1 ------------------
    //
    // "we need to be able to add cables to each circuit on the distro
    // besides just soca length or l620 length etc. like say circuit 1
    // needs a 10ft true 1 and circuit 2 needs 6ft and 3/4 need nothing and
    // 5 needs 6ft and 6 needs a 10 ft. since we are going to have those
    // pdf docs we need to be able to have that info if i want to add it."
    // (user, 2026-09-06). For ONE circuit of ONE screen an optional cable
    // is a length in feet plus a connector, stored per screen and keyed
    // by circuit number the way powerLabelOverrides is:
    //     layer.powerCircuitCables = { [circuitNum]: { ft, connector } }
    // `connector` null means "follows the box" - the connector the
    // circuit's box breaks out to (True1 on a Soca 208 feeding a True1
    // screen, Edison on a Soca 120, the L21-30 breakout's own tail
    // connector) - so most of the time only a length gets typed. No entry
    // means no cable. A cleared circuit, multi or distro forgets its
    // cables with its label overrides: cables are programming.

    // The connectors a cable can be typed as - the breakout table's own
    // connector names, once each, in table order. Ids are the plug chips'
    // face ids (true1 / powercon / edison / l620), so the select's value
    // and the OUTPUTS row's faces name the same thing.
    getPowerCableConnectors() {
        const seen = new Set();
        const out = [];
        this.getPowerBreakoutTypes().forEach(bt => {
            const id = this._cableConnectorId(bt.connector);
            if (!id || seen.has(id)) return;
            seen.add(id);
            out.push({ id, name: bt.connector });
        });
        return out;
    }

    _cableConnectorId(name) {
        return String(name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    cableConnectorName(id) {
        const hit = this.getPowerCableConnectors().find(c => c.id === id);
        return hit ? hit.name : null;
    }

    // The connector a box's tails break out to: the box's resolved type
    // (distroBoxType - stored, members, neighbour, offered) names the
    // breakouts it feeds, and the holder screen's own breakout picks among
    // them (a Soca 208 feeds True1 OR powerCON; the screen says which);
    // a box nobody holds, or a screen whose breakout the box does not
    // name, reads the type's first breakout. Off any distro the screen's
    // own breakout is the whole answer. Returns a connector id.
    boxTailConnector(d, number, layer) {
        const bts = this.getPowerBreakoutTypes();
        const own = layer ? this.getPowerBreakout(layer) : null;
        if (!d) {
            return this._cableConnectorId((own || bts[0]).connector);
        }
        const type = this.distroBoxType(d, number).type;
        const ids = (type && type.breakouts) || [];
        const pick = (own && ids.includes(own.id))
            ? own
            : bts.find(b => ids.includes(b.id)) || own || bts[0];
        return this._cableConnectorId(pick.connector);
    }

    // Where one circuit of a screen sits: its multi's stable index, the
    // distro record (null off any distro) and the box number - read off
    // the naming index, the one authority for which box a circuit is on.
    _circuitBox(layer, circuitNum) {
        const nm = this._powerNaming(layer);
        const slot = nm.slots.get(parseInt(circuitNum, 10));
        if (!slot) return { idx: null, d: null, number: null };
        const idx = slot.multi;
        const distroId = (layer.powerSocaDistro || {})[idx] || null;
        const d = distroId
            ? this.getDistros().find(x => x.id === distroId) || null : null;
        return { idx, d, number: slot.number };
    }

    // The stored cable on one circuit, resolved for printing: null when
    // the circuit has none, else { ft, connector (the stored id or null),
    // id (the id in force), name, text } - text is what the chip corner,
    // the canvas tag and the paperwork all print ("10' True1").
    powerCircuitCable(layer, circuitNum) {
        const store = layer && layer.powerCircuitCables;
        const rec = store && store[circuitNum];
        const ft = rec ? Number(rec.ft) : NaN;
        if (!rec || !Number.isFinite(ft) || ft <= 0) return null;
        let id = rec.connector && this.cableConnectorName(rec.connector)
            ? rec.connector : null;
        if (!id) {
            const box = this._circuitBox(layer, circuitNum);
            id = this.boxTailConnector(box.d, box.number, layer);
        }
        const name = this.cableConnectorName(id) || '';
        return {
            ft, connector: rec.connector || null, id, name,
            text: this.cableText(ft, name),
        };
    }

    cableText(ft, name) {
        const n = Number(ft);
        const len = Number.isInteger(n) ? String(n) : String(+n.toFixed(1));
        return `${len}'${name ? ` ${name}` : ''}`;
    }

    // Write one circuit's cable. `cable` is { ft, connector } - a blank or
    // zero length forgets the entry (no cable), a null connector follows
    // the box. `record` false is the sheet's quick-fill, which issues ONE
    // updateLayers over every layer it touched itself, so a fill is one
    // undo step the way a length commit is.
    // The length the box sheet's quick fill writes on every circuit: the
    // Power cable preference (10' as shipped). Read where the cables are
    // made; a cable already typed is never rewritten by it.
    defaultPowerCableFt() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const n = Number(prefs.powerCableFt);
        return Number.isFinite(n) && n > 0 ? n : 10;
    }

    setCircuitCable(layer, circuitNum, cable, record = true) {
        if (!layer) return false;
        const store = layer.powerCircuitCables
            || (layer.powerCircuitCables = {});
        const ft = cable ? Number(cable.ft) : NaN;
        const before = JSON.stringify(store[circuitNum] || null);
        if (!Number.isFinite(ft) || ft <= 0) {
            delete store[circuitNum];
        } else {
            const connector = cable.connector
                && this.cableConnectorName(cable.connector)
                ? cable.connector : null;
            store[circuitNum] = { ft, connector };
        }
        const changed = JSON.stringify(store[circuitNum] || null) !== before;
        if (record && changed) {
            this.updateLayers([layer], true, 'Set Circuit Cable');
        }
        return changed;
    }

    // How a refusal names the screen's breakout - "set to L21-30", "set to
    // Edison (110V)" - the connector the box is set to, said the way the
    // crew says it.
    _breakoutShortName(bt) {
        if (!bt) return 'an unknown breakout';
        if (String(bt.id).startsWith('l2130-')) return 'L21-30';
        if (bt.id === 'soca-edison') return 'Edison (110V)';
        return bt.name;
    }

    // The five connector FACES - what a hand sees reaching for the box:
    // soca (19-pin round multi), True1 (keyed round, three contacts),
    // powerCON (round with the locking tab), Edison (two slots, ground
    // below), L21-30 (twist-lock, five curved slots). One <symbol> sprite
    // on the body; every chip, popover row and drag pill references a face
    // through plugGlyph, so the same five faces show everywhere.
    _ensurePlugGlyphs() {
        if (document.getElementById('hw-plug-glyphs')) return;
        const host = document.createElement('div');
        host.innerHTML = '<svg id="hw-plug-glyphs" width="0" height="0" '
            + 'style="position:absolute" aria-hidden="true"><defs>'
            + '<symbol id="hw-g-soca" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/>'
            + '<circle class="pin" cx="12" cy="12" r="1"/><g class="pin">'
            + '<circle cx="12" cy="8" r=".9"/><circle cx="15.5" cy="10" r=".9"/>'
            + '<circle cx="15.5" cy="14" r=".9"/><circle cx="12" cy="16" r=".9"/>'
            + '<circle cx="8.5" cy="14" r=".9"/><circle cx="8.5" cy="10" r=".9"/>'
            + '<circle cx="12" cy="4.6" r=".8"/><circle cx="15.7" cy="5.6" r=".8"/>'
            + '<circle cx="18.4" cy="8.3" r=".8"/><circle cx="19.4" cy="12" r=".8"/>'
            + '<circle cx="18.4" cy="15.7" r=".8"/><circle cx="15.7" cy="18.4" r=".8"/>'
            + '<circle cx="12" cy="19.4" r=".8"/><circle cx="8.3" cy="18.4" r=".8"/>'
            + '<circle cx="5.6" cy="15.7" r=".8"/><circle cx="4.6" cy="12" r=".8"/>'
            + '<circle cx="5.6" cy="8.3" r=".8"/><circle cx="8.3" cy="5.6" r=".8"/>'
            + '</g></symbol>'
            + '<symbol id="hw-g-true1" viewBox="0 0 24 24">'
            + '<path d="M7 3.6 H17 A10 10 0 1 1 7 3.6 Z"/>'
            + '<rect class="pin" x="10.6" y="3" width="2.8" height="2.2" rx=".4"/>'
            + '<rect class="pin" x="7.2" y="10" width="2.2" height="5" rx=".6"/>'
            + '<rect class="pin" x="14.6" y="10" width="2.2" height="5" rx=".6"/>'
            + '<rect class="pin" x="10.9" y="14.8" width="2.2" height="4" rx=".6"/>'
            + '</symbol>'
            + '<symbol id="hw-g-powercon" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="9.8"/><path d="M17.6 4.4 l2.6 -2.2"/>'
            + '<rect class="pin" x="11" y="5.2" width="2" height="4.6" rx=".5"/>'
            + '<rect class="pin" x="6.2" y="13.2" width="2" height="4.6" rx=".5" '
            + 'transform="rotate(30 7.2 15.5)"/>'
            + '<rect class="pin" x="15.8" y="13.2" width="2" height="4.6" rx=".5" '
            + 'transform="rotate(-30 16.8 15.5)"/>'
            + '</symbol>'
            + '<symbol id="hw-g-edison" viewBox="0 0 24 24">'
            + '<rect x="3" y="3" width="18" height="18" rx="4"/>'
            + '<rect class="pin" x="7" y="7" width="2.2" height="6" rx=".5"/>'
            + '<rect class="pin" x="14.8" y="7.8" width="2.2" height="5.2" rx=".5"/>'
            + '<path class="pin" d="M10.2 17.8 v-2 a1.8 1.8 0 0 1 3.6 0 v2 z"/>'
            + '</symbol>'
            + '<symbol id="hw-g-l2130" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/><circle cx="12" cy="12" r="1.2"/>'
            + '<g stroke-width="2.4" stroke-linecap="round" fill="none">'
            + '<path d="M11 5.4 a6.8 6.8 0 0 1 2.2 0"/>'
            + '<path d="M17.7 9.3 a6.8 6.8 0 0 1 .8 2.2"/>'
            + '<path d="M16.9 16.6 a6.8 6.8 0 0 1 -1.7 1.5"/>'
            + '<path d="M8.8 18.1 a6.8 6.8 0 0 1 -1.7 -1.5"/>'
            + '<path d="M5.5 11.5 a6.8 6.8 0 0 1 .8 -2.2"/>'
            + '</g></symbol>'
            + '</defs></svg>';
        document.body.appendChild(host.firstChild);
    }

    plugGlyph(id, cls) {
        this._ensurePlugGlyphs();
        const ns = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('class', 'hw-plug-g' + (cls ? ` ${cls}` : ''));
        const use = document.createElementNS(ns, 'use');
        use.setAttribute('href', `#hw-g-${id}`);
        svg.appendChild(use);
        return svg;
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
        // One feeds entry per PHYSICAL box: two multis pinned to the same
        // (distro, number) are one soca serving two screens, so the second
        // member folds into the first's row - watts summed, legs combined,
        // both screens named. Counting each member as its own soca is
        // exactly the phantom-multi arithmetic the pin exists to kill. The
        // WATTS still add per member (the load is real twice over); only
        // the enumeration merges.
        const boxRows = new Map();      // share key -> the one feeds row
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const plan = this.getSocaPlan(layer);
            if (!plan.length) continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of plan) {
                const b = buckets.get(assign[s.soca]) || unassigned;
                const share = this.getSocaShare(layer, s.soca);
                const row = share && boxRows.get(share.key);
                if (row) {
                    row.layer += ' + ' + layer.name;
                    row.watts += s.watts;
                    row.legs += s.legs.length;
                } else {
                    const fresh = { layer: layer.name, layerId: layer.id, soca: s.soca, name: s.name, watts: s.watts, legs: s.legs.length };
                    if (share) { fresh.shared = true; boxRows.set(share.key, fresh); }
                    b.socas.push(fresh);
                }
                b.watts += s.watts;
                // spread this multi's circuits across the phase legs
                const d = b.distro;
                if (d && d.phase === 3) {
                    // Per CIRCUIT, not per distro: coupling follows the
                    // circuit's own voltage (_circuitSchemeFor), so a 110V
                    // multi rides one leg per circuit while a 208V multi on
                    // the same service keeps its leg pairs - the mixed case
                    // sums correctly because both land in one phasor store.
                    const scheme = this._circuitSchemeFor(d, circuitV);
                    if (b.scheme && b.scheme.lineToLine !== scheme.lineToLine) {
                        b.schemeMixed = true;
                    }
                    b.scheme = scheme;
                    const vln = d.voltage / Math.sqrt(3);
                    const boxSize = this.socaBoxSize(layer);
                    const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                    for (let li = 0; li < s.legs.length; li++) {
                        const leg = s.legs[li];
                        const legs = this._circuitLegs(pos[li], scheme.id, 0, boxSize);
                        if (legs.length === 1) {
                            // Line-to-neutral: full current on ONE leg, in
                            // phase with that leg's L-N voltage. Amps are
                            // I = P / V_screen (the circuit's own voltage -
                            // a 110V circuit draws its watts at 110, user
                            // ruling); the service L-N figure only stands
                            // in when the screen carries no voltage.
                            b.legWatts[legs[0]] += leg.watts;
                            this._addLegPhasor(b.legPhasor, legs[0],
                                leg.watts / (circuitV > 0 ? circuitV : vln), 0);
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
                // True when this service carries BOTH couplings at once -
                // 110V single-leg circuits beside 208V leg pairs. The
                // scheme fields above then name only the last one summed,
                // so a surface printing the scheme can say "mixed" instead.
                legs.schemeMixed = !!b.schemeMixed;
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

    // Per-leg amps in ONE physical box's feed - the same phasor walk
    // getDistroLoads runs for a service, scoped to the box. `members` is
    // [{layer, s}] with `s` the member's soca-plan record; a shared box
    // hands every member in, so both screens' circuits sum into one feed.
    // This is what the L21-30's 30 A/leg feed check reads: the box's three
    // 208V circuits sit +-30 deg off their legs, so a full box at circuit
    // current I loads each feed leg at I x sqrt(3), never 2 x I.
    boxFeedLegAmps(distro, members) {
        const phasor = { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 },
                         Z: { re: 0, im: 0 } };
        if (!distro) return { X: 0, Y: 0, Z: 0 };
        const vln = (Number(distro.voltage) || 0) / Math.sqrt(3);
        for (const m of (members || [])) {
            if (!m || !m.layer || !m.s) continue;
            const circuitV = parseFloat(m.layer.powerVoltage) || 0;
            const scheme = this._circuitSchemeFor(distro, circuitV);
            const boxSize = this.socaBoxSize(m.layer);
            const pos = this.socaCircuitPositions(
                m.layer, m.s.soca, m.s.legs.length);
            for (let li = 0; li < m.s.legs.length; li++) {
                const leg = m.s.legs[li];
                const legs = this._circuitLegs(pos[li], scheme.id, 0, boxSize);
                if (legs.length === 1) {
                    this._addLegPhasor(phasor, legs[0],
                        leg.watts / (circuitV > 0 ? circuitV : vln), 0);
                } else {
                    const [first, second] = this._cyclicPair(legs[0], legs[1]);
                    const amps = leg.watts / (Number(distro.voltage) || 1);
                    this._addLegPhasor(phasor, first, amps, 30);
                    this._addLegPhasor(phasor, second, amps, -30);
                }
            }
        }
        const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
        return { X: mag(phasor.X), Y: mag(phasor.Y), Z: mag(phasor.Z) };
    }

    // Keyed by the multi's stable index, like every other per-multi store, so
    // a home run stays with its multi when the distro renumbers it.
    // `record` mirrors setSocaName's: false for the dock's shared-box
    // write-through, which issues one updateLayers over every member itself.
    setSocaLength(layer, socaIndex, length, record = true) {
        if (!layer) return;
        const store = layer.powerSocaLengths || (layer.powerSocaLengths = {});
        const v = String(length || '').trim();
        if (v) store[socaIndex] = v; else delete store[socaIndex];
        if (record) {
            this.updateLayers([layer], true, 'Set Multi Home Run');
        }
    }

    // The distro list died with the Power sidebar: the dock's distro
    // sections are the one surface now - name inline on the header, the
    // load bar and LEGS line beside it, the electrical setup behind the
    // gear (whose content _buildDistroGearContent below builds). So a
    // distro refresh IS a dock render, kept under its old name because
    // every "the loads moved" path already calls it.
    refreshDistroPanel() {
        if (typeof this.renderHardwareDock === 'function') {
            this.renderHardwareDock();
        }
    }

    // The phasing entries one distro's gear select offers: only the
    // orderings of the coupling the voltage derivation picked - read off
    // distroPhasingState's own comparison (powerPhasingFor), never a second
    // one that could disagree with the leg maths. An explicit scheme whose
    // coupling the voltage no longer permits (picked first, voltage changed
    // after) is somebody's paperwork: it stays offered with the mismatch
    // said out loud, never silently dropped or swapped.
    _distroPhasingOptions(ph) {
        const offered = this.powerPhasingSchemes()
            .filter(sc => sc.lineToLine === ph.derived.lineToLine);
        if (ph.explicit && !offered.some(sc => sc.id === ph.scheme.id)) {
            offered.push({ ...ph.scheme,
                name: `${ph.scheme.name} — does not match the `
                    + `${Math.round(ph.circuitVoltage)} V circuits `
                    + `(${ph.derived.coupling.toLowerCase()})` });
        }
        return offered;
    }

    // The distro's gear popover: the electrical setup the retired sidebar
    // rows carried - rating, voltage, phase, phasing (with its derive entry
    // and help), location, remove. Same data-lrd-field keys, same patch
    // path (updateDistro + _restateNaming), same phasing doctrine: the
    // voltage DECIDES the coupling, so only the ordering axis is offered.
    _buildDistroGearContent(d) {
        const wrap = document.createElement('div');
        const heading = document.createElement('div');
        heading.className = 'hw-pop-heading';
        heading.textContent = d.name || 'distro';
        wrap.appendChild(heading);

        const patch = (p) => {
            this.updateDistro(d.id, p);
            this._restateNaming();
        };
        const cap = (text) => {
            const c = document.createElement('label');
            c.style.fontSize = '10px';
            c.style.color = 'var(--ps-dim, #c0c0c0)';
            c.style.textTransform = 'uppercase';
            c.textContent = text;
            return c;
        };

        const row1 = document.createElement('div');
        row1.style.display = 'flex';
        row1.style.flexWrap = 'wrap';
        row1.style.gap = '6px';
        row1.style.alignItems = 'center';
        row1.appendChild(cap('Rating'));
        const rate = document.createElement('input');
        rate.type = 'number';
        rate.min = '1';
        rate.value = d.ratingA;
        rate.style.width = '56px';
        rate.dataset.lrdField = `distro-rating-${d.id}`;
        rate.title = 'Service rating in amps.';
        rate.addEventListener('change', () => patch({ ratingA: rate.value }));
        row1.appendChild(rate);
        row1.appendChild(cap('Voltage'));
        const volt = document.createElement('select');
        volt.className = 'info-select';
        volt.dataset.lrdField = `distro-voltage-${d.id}`;
        [110, 120, 208, 220, 230, 240, 400, 415].forEach(v => {
            const opt = document.createElement('option');
            opt.value = String(v);
            opt.textContent = `${v}V`;
            if (Number(d.voltage) === v) opt.selected = true;
            volt.appendChild(opt);
        });
        volt.addEventListener('change', () => patch({ voltage: volt.value }));
        row1.appendChild(volt);
        const phase = document.createElement('select');
        phase.className = 'info-select';
        phase.dataset.lrdField = `distro-phase-${d.id}`;
        [[1, '1φ'], [3, '3φ']].forEach(([v, text]) => {
            const opt = document.createElement('option');
            opt.value = String(v);
            opt.textContent = text;
            if (Number(d.phase) === v) opt.selected = true;
            phase.appendChild(opt);
        });
        phase.addEventListener('change', () => patch({ phase: phase.value }));
        row1.appendChild(phase);
        wrap.appendChild(row1);

        if (Number(d.phase) === 3) {
            const ph = this.distroPhasingState(d);
            const row2 = document.createElement('div');
            row2.style.display = 'flex';
            row2.style.gap = '6px';
            row2.style.alignItems = 'center';
            row2.style.marginTop = '6px';
            row2.title = 'Phasing. How a multi\'s 6 circuits land on the '
                + 'phase legs - a property of the distro\'s bus and breaker '
                + 'arrangement, read off the distro. Not the connector\'s '
                + 'E1.80 pinout type. Each name gives the coupling, then '
                + 'the dealing order.';
            row2.appendChild(cap('Phasing'));
            const sel = document.createElement('select');
            sel.className = 'info-select';
            sel.style.flex = '1 1 0';
            sel.style.minWidth = '0';
            sel.dataset.lrdField = `distro-phasing-${d.id}`;
            // Two KINDS of entry, grouped as two: the first is an
            // instruction to the app ("follow the voltage"), the rest
            // describe how a distro is wired. Deriving is a state, not the
            // absence of one - the empty value clears distro.phasing and
            // hands the choice back to the voltage. The resolved volts ride
            // on the GROUP, off this distro's own service: they are not a
            // property of any scheme (line-to-neutral is 120V on a 208V
            // service, 230V on a 400V one).
            const derive = document.createElement('optgroup');
            derive.label = 'Let the voltage decide';
            const followOpt = document.createElement('option');
            followOpt.value = '';
            followOpt.textContent =
                `Follow the circuit voltage — ${ph.derived.name}`;
            if (!ph.explicit) followOpt.selected = true;
            derive.appendChild(followOpt);
            sel.appendChild(derive);
            const wired = document.createElement('optgroup');
            wired.label = 'Read it off the distro · '
                + `${Math.round(d.voltage / Math.sqrt(3))} V line-to-neutral, `
                + `${Math.round(d.voltage)} V line-to-line`;
            this._distroPhasingOptions(ph).forEach(sc => {
                const opt = document.createElement('option');
                opt.value = sc.id;
                opt.textContent = sc.name;
                if (ph.explicit && ph.scheme.id === sc.id) opt.selected = true;
                wired.appendChild(opt);
            });
            sel.appendChild(wired);
            sel.addEventListener('change', () => patch({ phasing: sel.value }));
            row2.appendChild(sel);
            const help = document.createElement('button');
            help.textContent = '?';
            help.title = 'What do these mean?';
            help.dataset.lrdField = `distro-phasing-help-${d.id}`;
            help.addEventListener('click', () => this.showPhasingHelp());
            row2.appendChild(help);
            wrap.appendChild(row2);
        }

        const row3 = document.createElement('div');
        row3.style.display = 'flex';
        row3.style.gap = '6px';
        row3.style.alignItems = 'center';
        row3.style.marginTop = '6px';
        // The beach this distro sits on (2026-09-08, "Replace it with the
        // picker"): one of the project's beaches, or a new one made right
        // here - app-beaches.js builds the same picker the box's gear and
        // Screen Info use. Every power row the distro produces is pulled
        // there. One 'Set Distro Beach' entry; the blank entry clears.
        row3.appendChild(cap('Beach'));
        const beachSelect = document.createElement('select');
        beachSelect.style.flex = '1';
        beachSelect.style.minWidth = '0';
        beachSelect.dataset.lrdField = `distro-beach-${d.id}`;
        beachSelect.title = 'The beach this distro sits on - the dimmer beach, '
            + 'stage left world, FOH. Its multis, breakouts and circuit cables '
            + 'are pulled there.';
        this.fillBeachPicker(beachSelect, d.beachId);
        this.wireBeachPicker(beachSelect, (beachId) => {
            this.updateDistro(d.id, { beachId }, 'Set Distro Beach');
            this._restateNaming();
            if (typeof this.renderBeaches === 'function') this.renderBeaches();
        });
        row3.appendChild(beachSelect);
        wrap.appendChild(row3);

        // OUTPUTS (2026-08-31): the connector types this distro can hand a
        // screen - types only, no counts. One tick row per type: face,
        // plain name, what it breaks out to. Every row is sized to stay
        // inside the popover's own box (the resize suite pins it): names
        // never wrap, the breakout text ellipsizes before it can push
        // past the edge.
        const outs = document.createElement('div');
        outs.className = 'hw-pop-outs';
        const outsCap = document.createElement('div');
        outsCap.className = 'hw-pop-outs-cap';
        outsCap.appendChild(cap('Outputs'));
        const outsSub = document.createElement('small');
        outsSub.textContent = 'what this distro can hand a screen';
        outsCap.appendChild(outsSub);
        outs.appendChild(outsCap);
        const offered = new Set(this.distroOutputs(d).map(t => t.id));
        this.getDistroOutputTypes().forEach(t => {
            const row = document.createElement('label');
            row.className = 'hw-pop-out'
                + (offered.has(t.id) ? '' : ' hw-pop-out-off');
            row.title = `${t.name} → ${t.sub}. Ticked, the tray shows a `
                + `${t.name} chip under this distro's LEGS line to drag `
                + 'onto a screen; unticked, it never does.';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = offered.has(t.id);
            cb.dataset.lrdField = `distro-out-${t.id}-${d.id}`;
            cb.addEventListener('change', () => {
                const live = this.getDistros().find(x => x.id === d.id) || d;
                const now = new Set(this.distroOutputs(live).map(x => x.id));
                if (cb.checked) now.add(t.id); else now.delete(t.id);
                patch({ outputs: this.getDistroOutputTypes()
                    .map(x => x.id).filter(id => now.has(id)) });
            });
            row.appendChild(cb);
            row.appendChild(this.plugGlyph(t.glyph));
            const name = document.createElement('b');
            name.textContent = t.name;
            row.appendChild(name);
            const sub = document.createElement('small');
            sub.className = 'hw-pop-out-sub';
            t.faces.forEach(f => sub.appendChild(this.plugGlyph(f)));
            sub.appendChild(document.createTextNode(t.sub));
            row.appendChild(sub);
            outs.appendChild(row);
        });
        const hint = document.createElement('div');
        hint.className = 'hw-pop-outs-hint';
        hint.textContent = 'Unticked types never show as chips. A distro '
            + 'with nothing ticked still drags whole onto a screen, as it '
            + 'always has.';
        outs.appendChild(hint);
        wrap.appendChild(outs);

        const remove = document.createElement('button');
        remove.className = 'btn hw-pop-remove';
        remove.textContent = 'Remove distro';
        remove.title = 'Remove this power source. Multis assigned to it '
            + 'come free; undo puts it back.';
        remove.dataset.lrdField = `distro-del-${d.id}`;
        remove.addEventListener('click', () => {
            if (typeof this._hwPopoverClose === 'function') {
                this._hwPopoverClose();
            }
            this.removeDistro(d.id);
            // The distro is gone and its id never comes back, so its fold
            // keys go with it - the dock section's, and the per-number
            // multi keys under it (a prefix sweep catches however many the
            // tray ever drew).
            try {
                localStorage.removeItem(
                    `ledRasterPanelCollapsed_hwdock-distro-${d.id}`);
                const prefix =
                    `ledRasterPanelCollapsed_hwdock-multi-${d.id}-`;
                Object.keys(localStorage)
                    .filter(k => k.startsWith(prefix))
                    .forEach(k => localStorage.removeItem(k));
            } catch (_) { /* blocked storage never held the key */ }
            this._restateNaming();
        });
        wrap.appendChild(remove);
        return wrap;
    }


    // Every surface a name reaches, restated together.
    //
    // Renaming a distro or a multi, or landing a multi on a distro, renumbers
    // or renames circuits across the WHOLE show. Redrawing the panel that was
    // clicked and leaving the wall behind would put two different answers on
    // screen at once, so the prepared index is dropped and everything that
    // reads it is rebuilt from one place.
    //
    // The wall redraws immediately; the PANELS wait a macrotask. Every caller
    // here fires from a field's own `change` handler, which runs mid-Tab, and
    // a synchronous wipe destroys the field the gesture is landing in - see
    // _rebuildAfterGesture.
    _restateNaming() {
        this._circuitTailCache = null;
        if (window.canvasRenderer) window.canvasRenderer.render();
        this._rebuildAfterGesture(() => {
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            // The dock is where the naming shows now - headers, chips,
            // strip - so ONE render covers what four panel wipes did
            // (refreshDistroPanel is this same render under its old name).
            this.renderHardwareDock && this.renderHardwareDock();
        });
    }

    // Why this screen's plan is empty, when a POWER ERROR is why - the
    // sentence, minus its lead-in, so the soca host ("No circuits — ...")
    // and the label editor ("No circuits to edit — ...") share one story.
    //
    // Live repro: a 13-wide screen of 200W panels at 110V/15A in organized
    // row mode cannot fit a row on a circuit, so the plan is empty - and the
    // soca panel rendered NOTHING, which read as the soca feature being
    // broken. The explanation lived only in the left sidebar and the red
    // wall tint. Every other empty state stays blank: a non-screen layer, a
    // screen with nothing visible on it, a group member counted on its
    // owner, and a custom-routed screen (whose drawn paths supersede the
    // auto error - the same rule updatePowerCapacityDisplay applies to
    // _powerError) have no error to explain.
    _socaPlanEmptyReason(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        if (this.usesCustomCircuits(layer)) return null;
        const err = this.calculatePowerAssignments(layer).error;
        if (!err) return null;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const fmt = (w) => `${Math.round(w).toLocaleString()} W`;
        const circuit = `a circuit at ${voltage} V / ${amperage} A carries ${fmt(voltage * amperage)}`;
        if (err.unitType) {
            const across = err.unitType === 'row' ? 'column' : 'row';
            return `a full ${err.unitType} is ${fmt(err.unitLoad || 0)} and ${circuit}. `
                + `Fix in Power Settings: higher voltage or amperage, a ${across} pattern, or a custom path `
                + `(select a narrower block and apply a pattern — circuits cut at capacity).`;
        }
        // PANEL WATTS EXCEED CIRCUIT CAPACITY: one cabinet alone is over,
        // so no pattern can help.
        return `one panel is ${fmt(parseFloat(layer.panelWatts) || 0)} and ${circuit}. `
            + `Fix in Power Settings: higher voltage or amperage.`;
    }

    // The soca tiles died with the Power sidebar - a multi's name and
    // home-run length edit inline on its dock multi header, and the
    // empty-plan story tells on the dock's strip - so what is left under
    // this name is syncing the per-screen knobs that moved into the left
    // sidebar's Power Settings: the breakout type and the map brackets.
    // Static controls, synced in place (never wiped), so there is no focus
    // to preserve; a control someone is standing in is left alone.
    refreshSocaRuns() {
        const sel = document.getElementById('power-breakout-type');
        const brk = document.getElementById('show-soca-brackets');
        if (!sel && !brk) return;
        this._wireScreenPowerKnobs();
        const layer = this.currentLayer;
        const screen = layer && (layer.type || 'screen') === 'screen';
        if (sel) {
            if (!sel.options.length) {
                this.getPowerBreakoutTypes().forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.name;
                    sel.appendChild(opt);
                });
            }
            // Eligibility follows the screen's voltage (user ruling: a
            // 110V screen can only have 110V Edison on it; the L21-30 box
            // is 3 x 208V). Disabled, not removed: the list stays stable
            // and a stored incompatible choice keeps displaying - the
            // mismatched-phasing doctrine, applied to breakouts.
            if (screen) {
                const v = layer.powerVoltage;
                const types = this.getPowerBreakoutTypes();
                Array.from(sel.options).forEach(opt => {
                    const t = types.find(x => x.id === opt.value);
                    const ok = !t || this._breakoutEligible(t, v);
                    // Only a STORED choice earns the exemption - it keeps
                    // displaying and re-selecting; an unset screen has no
                    // paperwork to defend.
                    opt.disabled = !ok && opt.value !== layer.powerBreakoutType;
                    opt.title = ok ? '' : `Not available at ${v} V.`;
                });
            }
            if (screen && sel !== document.activeElement) {
                sel.value = this.getPowerBreakout(layer).id;
            }
        }
        if (brk && brk !== document.activeElement) {
            // OFF unless explicitly ticked (=== true, matching the canvas
            // gate): brackets started life on by default and the user asked
            // for them unselected. A field never touched now means off, on
            // old projects too.
            brk.checked = !!(screen && layer.showSocaBrackets === true);
        }
    }

    // The static knobs' change handlers, wired ONCE - the controls live in
    // index.html now and are never rebuilt. Multi-select doctrine
    // unchanged: a per-screen scalar edit applies to EVERY selected screen
    // (_socaPanelTargets), under the same history actions the old panel
    // rows earned.
    _wireScreenPowerKnobs() {
        if (this._screenPowerKnobsWired) return;
        this._screenPowerKnobsWired = true;
        const sel = document.getElementById('power-breakout-type');
        if (sel) sel.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.powerBreakoutType = sel.value; });
            this.updateLayers(list, true, 'Change Power Breakout');
        });
        const brk = document.getElementById('show-soca-brackets');
        if (brk) brk.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => { l.showSocaBrackets = brk.checked; });
            this.updateLayers(list, true, 'Toggle Soca Brackets');
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        const en = document.getElementById('power-splitters-enabled');
        const mw = document.getElementById('power-splitters-maxways');
        const mwc = document.getElementById('power-splitters-maxways-custom');
        const writeAll = (patch) => {
            const layer = this.currentLayer;
            if (!layer) return;
            const list = this._socaPanelTargets(layer);
            list.forEach(l => {
                const cur = this.getPowerSplitters(l);
                l.powerSplitters = { ...cur, ...patch, manual: cur.manual };
            });
            this.updateLayers(list, true, 'Change Splitter Packing');
            this._rebuildAfterGesture(() => {
                this.refreshSplitterPanel();
                this.refreshSocaRuns();
                this.refreshDistroPanel();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        };
        if (en) en.addEventListener('change',
                                    () => writeAll({ enabled: en.checked }));
        if (mw) mw.addEventListener('change', () => {
            if (mw.value === 'custom') {
                // seed a non-stock value so the custom box appears, filled
                writeAll({ maxWays: 5 });
                return;
            }
            writeAll({ maxWays: parseInt(mw.value, 10) || 3 });
        });
        if (mwc) mwc.addEventListener('change', () => {
            writeAll({ maxWays: Math.max(2, parseInt(mwc.value, 10) || 2) });
        });
    }

    // The Splitters panel rows died with the sidebar - manual merge and
    // split are the right-click Share / Un-share on the circuit itself
    // (app-dock.js _prepareShareMenus) - so what is left under this name is
    // syncing the packing knobs that moved into Power Settings: the enable
    // checkbox, and the size row that follows it. "Present only while
    // sharing is on" (the old panel's rule) is worn as visibility on the
    // static row.
    refreshSplitterPanel() {
        const en = document.getElementById('power-splitters-enabled');
        if (!en) return;
        this._wireScreenPowerKnobs();
        const layer = this.currentLayer;
        const screen = layer && (layer.type || 'screen') === 'screen';
        const sp = screen ? this.getPowerSplitters(layer)
            : { enabled: false, maxWays: 3 };
        if (en !== document.activeElement) {
            en.checked = !!(screen && sp.enabled);
        }
        const row = document.getElementById('power-splitters-maxways-row');
        if (row) row.style.display = (screen && sp.enabled) ? 'flex' : 'none';
        const mw = document.getElementById('power-splitters-maxways');
        const mwc = document.getElementById('power-splitters-maxways-custom');
        const stock = [2, 3, 4].includes(sp.maxWays);
        if (mw && mw !== document.activeElement) {
            mw.value = stock ? String(sp.maxWays) : 'custom';
        }
        if (mwc) {
            mwc.style.display = stock ? 'none' : '';
            if (mwc !== document.activeElement && !stock) {
                mwc.value = String(sp.maxWays);
            }
        }
    }

    // Merge the selected circuits into one manual group.
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
    // `action` (optional) names the history entry - the batch verb's
    // "Un-share all" passes its own so the step reads as what it was.
    splitSplitterCircuits(layer, circuitNums, action) {
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
        }, action);
    }

    // ---- the batch verb: "3fer them" ---------------------------------------
    //
    // 2026-08-30, tester + user ruling ("lets go for B and then right
    // click"): sweep a contiguous stretch of runs, right-click, and the
    // menu offers "2fer them / 3fer them / 4fer them" with the group math
    // spelled out. The verb PARTITIONS - consecutive adjacent groups dealt
    // left to right along the wall - so 18 circuits under "3fer them"
    // become six separate 3fers, never one mega-gang. Adjacency is the
    // splitter doctrine (never skip a run); over-capacity groups are
    // honored and flag OVER like every manual merge.

    // Group sizes for `count` runs dealt as Nfers. The REMAINDER RE-DEALS
    // so nothing is orphaned (user-vetoable choice, mock option (i)):
    // a remainder of 2+ becomes its own smaller fer (8 @ 3fer -> 3,3,2);
    // a remainder of 1 borrows from the last full group and goes out as
    // two 2fers (16 @ 3fer -> 3,3,3,3,2,2). Only "2fer them" over an odd
    // count leaves a single plain run - there is no smaller fer to deal.
    batchNferGroups(count, n) {
        const L = Math.max(0, Number(count) || 0);
        const size = Math.max(2, Number(n) || 2);
        let full = Math.floor(L / size);
        const rem = L % size;
        let tail = [];
        if (rem === 1 && size > 2 && full >= 1) {
            // borrow the last full group and re-deal its n+1 runs as two
            // smaller fers, biggest first: 3fer -> 2+2, 4fer -> 3+2
            full -= 1;
            const m = size + 1;
            tail = [Math.ceil(m / 2), Math.floor(m / 2)];
        } else if (rem >= 2) {
            tail = [rem];
        } else if (rem === 1) {
            tail = [1];
        }
        return Array.from({ length: full }, () => size).concat(tail);
    }

    // "6 × 3fer", "4 × 4fer + 2fer", "3 × 2fer + 1 plain" - the group math
    // the menu entry carries, so the deal is read before it is taken.
    batchNferLabel(count, n) {
        const sizes = this.batchNferGroups(count, n);
        const tally = new Map();
        sizes.forEach(s => tally.set(s, (tally.get(s) || 0) + 1));
        return [...tally.entries()].sort((a, b) => b[0] - a[0])
            .map(([sz, k]) => sz === 1
                ? `${k} plain`
                : (k === 1 ? `1 × ${sz}fer` : `${k} × ${sz}fer`))
            .join(' + ');
    }

    // Deal the chosen circuits' RUNS into Nfer groups, one manual-store
    // write, ONE history entry (`action`). Operates at the run level so an
    // existing gang inside the batch re-deals with everything else. A solo
    // remainder on an auto screen is split-PINNED so re-packing cannot
    // quietly gang what the deal left plain (custom circuits need no pin -
    // they never auto-pack). Same id-space rules as every manual edit:
    // _writeSplitterManual stamps the space the screen currently reads.
    batchShareCircuits(layer, circuitNums, n, action) {
        if (!layer || !Array.isArray(circuitNums)) return false;
        const size = Math.max(2, Number(n) || 0);
        const chosen = new Set(circuitNums);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        if (runIds.length < 2) return false;
        const sizes = this.batchNferGroups(runIds.length, size);
        const custom = this.usesCustomCircuits(layer);
        this._writeSplitterManual(layer, (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(x => !hit.has(x)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(x => !hit.has(x));
            let off = 0;
            sizes.forEach(sz => {
                const g = runIds.slice(off, off + sz);
                off += sz;
                if (g.length >= 2) {
                    manual.merge.push([...g].sort((a, b) => a - b));
                } else if (!custom) {
                    manual.split.push(...g);
                }
            });
            manual.split = [...new Set(manual.split)].sort((a, b) => a - b);
        }, action);
        return true;
    }

    // ---- what a CLEAR forgets ------------------------------------------------
    //
    // User ruling (2026-08-30): "when i clear a circuit, soca or a distro
    // or sending card i dont want it to remember how i had it programmed
    // before with balancing etc". A clear used to drop only the assignment
    // and leave the paperwork - the stored tail set above all - so
    // re-assigning resurrected the old balance layout. Now the clear wipes
    // the cleared thing's stored programming too, and the caller folds
    // every wipe into ONE history entry so a single undo restores all of
    // it. The split boundaries at the cleared multi's edges go too, and
    // so does every cut left between multis nobody is feeding (user
    // ruling, 2026-09-04, extending the above: a wall of one-circuit
    // multis left by circuit-pip drops read S1[1-6] S2[7] S3[8] ... after
    // a clear - "the numbering is all wrong") - see _socaClearSplitPoints.

    // The split points that survive clearing `indices` on this layer.
    // Two rules, one home:
    //
    // 1. The cleared multis' own edges. The boundary that ends each
    //    cleared multi and the one that ends the multi before it are
    //    forgotten, so the cleared circuits fall back onto the natural box
    //    grid (_socaSegments cuts at every multiple of socaBoxSize
    //    whatever is stored). A run of cleared multis inside one grid
    //    cell is treated as one: its interior cuts always go; the cut to
    //    a KEPT neighbour goes when the run has a kept neighbour on ONE
    //    side only (the run welds onto it - the neighbour keeps its
    //    identity and re-deals its tails, the un-split rule), and both
    //    cuts stay when kept multis flank the run on both sides -
    //    forgetting either would weld two multis that were not cleared
    //    into one and lose the second's distro, number and name, which
    //    the ruling never asked for. Grid lines are never stored, so a
    //    neighbour across one is not a neighbour here.
    //
    // 2. The leftovers. Every remaining stored cut that sits between two
    //    multis which are BOTH unassigned (no distro) once the clear has
    //    run goes too, welding them back onto the natural grid. On the
    //    user's own show (2026-09-04) a run of circuit-pip drops had left
    //    twelve one-circuit multis S2..S13 behind S1, already unassigned,
    //    so rule 1 alone cleared S1 and left the wall reading S1[1-6]
    //    S2[7] S3[8] ... - "if i add circuits the numbering is all wrong",
    //    and "we need to audit this so it allows me to do up to 6 if i am
    //    doing multi/soca". An unassigned cut is programming nobody is
    //    using, and a clear must not remember how the wall was programmed
    //    (the 2026-08-30 ruling above). A cut with an ASSIGNED multi on
    //    either side stays: that multi keeps its identity, its number and
    //    its circuits under its new index (_resegmentSocaStores), so a
    //    flanked run of leftovers between two fed multis keeps both cuts
    //    - rule 1's flanked case is the same test with the cleared run
    //    counted as unassigned.
    //
    // Pure: reads the stores as the caller left them (the wipe ran first,
    // so a cleared multi's distro is already gone; `indices` covers it
    // regardless) and returns the surviving points - the caller re-keys
    // with _resegmentSocaStores, so the whole clear is still ONE history
    // entry and one undo puts every cut back.
    _socaClearSplitPoints(layer, indices) {
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const stored = new Set(this._socaSplitPoints(layer, count));
        const size = this.socaBoxSize(layer);
        const cleared = new Set((indices || []).map(Number));
        const gone = new Set();
        for (let i = 0; i < segs.length; i++) {
            if (!cleared.has(segs[i].index)) continue;
            let j = i;
            while (j + 1 < segs.length && cleared.has(segs[j + 1].index)
                    && segs[j].end % size !== 0) j++;
            for (let k = i; k < j; k++) gone.add(segs[k].end);
            const before = segs[i].start - 1;
            const after = segs[j].end;
            const keptBefore = before >= 1 && before % size !== 0
                && stored.has(before);
            const keptAfter = after < count && after % size !== 0
                && stored.has(after);
            if (!(keptBefore && keptAfter)) {
                if (keptBefore) gone.add(before);
                if (keptAfter) gone.add(after);
            }
            i = j;
        }
        const assign = layer.powerSocaDistro || {};
        const fed = s => !cleared.has(s.index) && !!assign[s.index];
        for (let i = 0; i + 1 < segs.length; i++) {
            const p = segs[i].end;
            if (!stored.has(p) || gone.has(p)) continue;
            if (!fed(segs[i]) && !fed(segs[i + 1])) gone.add(p);
        }
        return [...stored].filter(p => !gone.has(p));
    }

    // One multi's circuits and their splitter run ids, read BEFORE any
    // store moves - the naming pass and the run ids describe the pre-clear
    // wall, and a wipe that changed the splitter store first would read a
    // renumbered plan.
    _socaClearTargets(layer, socaIndex) {
        const rec = this._powerNaming(layer).socas.get(Number(socaIndex));
        const circuits = rec ? rec.circuits.slice() : [];
        const runIds = [];
        if (circuits.length) {
            const inMulti = new Set(circuits);
            this.screenCircuits(layer).forEach(c => {
                if (!inMulti.has(c.num)) return;
                (c.runIds || [c.num]).forEach(id => runIds.push(id));
            });
        }
        return { circuits, runIds };
    }

    // Wipe one multi's stored programming: the (distro, number) assignment,
    // the stored tail set and legacy breaker offset, the typed name and
    // home-run length, its circuits' label overrides, and the manual
    // share/split entries covering its circuits. No history entry here -
    // the clear gestures compose members into one entry themselves. The
    // store objects are always left behind, never the properties deleted
    // whole (an absent key is missing from the update payload and the
    // server keeps whatever it had, so "cleared" would silently not clear).
    _wipeSocaProgramming(layer, socaIndex, targets) {
        const idx = Number(socaIndex);
        for (const field of ['powerSocaNumber', 'powerSocaDistro',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaLengths']) {
            if (layer[field]) delete layer[field][idx];
        }
        const t = targets || this._socaClearTargets(layer, socaIndex);
        if (layer.powerLabelOverrides) {
            t.circuits.forEach(num => {
                delete layer.powerLabelOverrides[num];
            });
        }
        // A circuit's cable is programming the same way its label override
        // is (2026-09-06): the cleared circuits forget theirs.
        if (layer.powerCircuitCables) {
            t.circuits.forEach(num => {
                delete layer.powerCircuitCables[num];
            });
        }
        this._wipeSplitterManualFor(layer, t.runIds);
    }

    // Drop the manual share (merge) groups and split pins covering the
    // given run ids, so a cleared scope re-packs naturally instead of
    // keeping hand-ganged circuits nobody is feeding any more. Unrecorded
    // by design - the clear's one entry carries it. Only the groups
    // authored in the id space the layer currently reads are touched; a
    // dormant foreign-space store is not this gesture's paperwork.
    _wipeSplitterManualFor(layer, runIds) {
        if (!runIds || !runIds.length) return false;
        const raw = layer && layer.powerSplitters;
        if (!raw || !raw.manual) return false;
        const space = this._splitterManualSpace(layer);
        if (space && space !== this._splitterIdSpace(layer)) return false;
        const cur = this.getPowerSplitters(layer);
        const hit = new Set(runIds);
        const merge = cur.manual.merge
            .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(n)) : []))
            .filter(g => g.length >= 2);
        const split = cur.manual.split.filter(n => !hit.has(n));
        if (JSON.stringify(merge) === JSON.stringify(cur.manual.merge)
                && split.length === cur.manual.split.length) {
            return false;
        }
        layer.powerSplitters = { ...cur, manual: {
            merge, split,
            space: cur.manual.space || this._splitterIdSpace(layer),
        } };
        return true;
    }

    // `action` names the history entry; the default keeps every existing
    // caller's entry byte-identical. The batch verb passes its own name
    // ('3fer Selection') so one commit is one legible undo step.
    _writeSplitterManual(layer, fn, action) {
        const cur = this.getPowerSplitters(layer);
        // An edit is made in the CURRENT id space. Groups stored from the
        // other space cannot be edited alongside it - one store, one space -
        // so the edit starts clean and the write stamps the space it was
        // authored in. Reads never get here, so merely flipping a screen
        // between custom and auto keeps the other space's groups dormant.
        const space = this._splitterIdSpace(layer);
        const foreign = this._splitterManualSpace(layer) !== space;
        const manual = {
            merge: foreign ? []
                : cur.manual.merge.map(g => (Array.isArray(g) ? g.slice() : [])),
            split: foreign ? [] : cur.manual.split.slice(),
        };
        fn(manual);
        manual.space = space;
        layer.powerSplitters = { ...cur, manual };
        this.updateLayers([layer], true, action || 'Edit Splitter Groups');
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
    // auto modes; the drawn circuit number for custom screens. Those are two
    // DIFFERENT id spaces sharing one store, so `manual.space` records which
    // one a group was authored in ('auto' | 'custom') and the groups go
    // dormant - not deleted - while the screen reads the other space. The
    // reference show proved why: a tower's 3fer merges, drawn over its 12
    // per-row custom circuits, rode along after the screen went back to an
    // auto pattern and silently re-ganged auto run ordinals 7-9 into an
    // over-capacity 3fer the user never asked for.

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
                space: (manual.space === 'auto' || manual.space === 'custom')
                    ? manual.space : null,
            },
        };
    }

    // The id space the layer's circuits read RIGHT NOW: drawn circuit
    // numbers for a screen routing custom, pre-packing run ordinals for
    // every auto pattern.
    _splitterIdSpace(layer) {
        return this.usesCustomCircuits(layer) ? 'custom' : 'auto';
    }

    // The id space the STORED manual groups belong to. Stamped on every
    // manual edit; a legacy file carries no stamp, so the space is inferred
    // from the only evidence the file holds: a screen routing custom read
    // its groups against the drawn numbers (unchanged), a pure auto screen
    // against its run ordinals (unchanged) - but an auto screen still
    // carrying DORMANT drawn circuits (non-empty custom power paths outside
    // its override numbers, kept from a retired custom routing) authored its
    // groups against those drawn numbers, so the groups stay dormant with
    // the paths instead of being misapplied to run ordinals that merely
    // share the digits.
    _splitterManualSpace(layer) {
        const stamped = this.getPowerSplitters(layer).manual.space;
        if (stamped) return stamped;
        if (this.usesCustomCircuits(layer)) return 'custom';
        const overridden = new Set(this.getOverrideNums(layer, 'power'));
        const paths = (layer && layer.powerCustomPaths) || {};
        const dormantDrawn = Object.keys(paths).some(n =>
            (paths[n] || []).length > 0 && !overridden.has(parseInt(n, 10)));
        return dormantDrawn ? 'custom' : 'auto';
    }

    // Validated-on-read manual groups against the run ids that currently
    // exist. Ids that no longer resolve are silently dropped; a group left
    // with fewer than two members dissolves; a run can sit in only one group
    // (first wins), and a run inside a group cannot also be split-pinned.
    // Groups authored in the OTHER id space (see the run-id doctrine above)
    // are dormant here: an id is a number, not a circuit, and only its own
    // space can say which circuit it named.
    appliedSplitterGroups(layer, validIds) {
        if (this._splitterManualSpace(layer) !== this._splitterIdSpace(layer)) {
            return { merge: [], split: [] };
        }
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

        // v0.12: a screen group whose members are the same panel AND the same
        // wattage packs its circuits as ONE BIGGER SCREEN - see getAutoRoutePlan
        // (app-screen-info.js). Null for every ungrouped screen and for a group
        // that matches on resolution but not on watts, and then every line below
        // is the line it always was.
        const plan = (typeof this.getAutoRoutePlan === 'function')
            ? this.getAutoRoutePlan(layer, 'power') : null;
        if (plan && !plan.isOwner) {
            // The wall's circuits are the first member's and are counted there.
            // Same only-honest-zero rule a member fed by a peer's hand-drawn
            // circuit already follows. The member's own OVERRIDDEN circuits are
            // the one exception: a redrawn circuit lives in its own layer's
            // numbering space, so it is reported here, by the layer that owns
            // it, and nowhere else.
            return this._mergeOverrideCircuits(layer, { circuits: [], error: null });
        }

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

        // The wall's grid and the screen each cabinet sits on. Without a plan
        // these are the layer's own, so nothing below can tell the difference.
        const gridRows = plan ? plan.rows : layer.rows;
        const gridCols = plan ? plan.columns : layer.columns;
        const rowOfPanel = plan ? (p => plan.rowOf.get(p)) : (p => p.row);
        const colOfPanel = plan ? (p => plan.colOf.get(p)) : (p => p.col);
        const panelOwners = new Map();
        if (plan) plan.ordered.forEach(c => panelOwners.set(c.panel, c.layer));
        const layerOfPanel = plan ? (p => panelOwners.get(p) || layer) : (() => layer);

        // The load factor is a HALF-TILE derate, so it is read against the
        // cabinet's own screen; the wattage is the group's, which the gate has
        // already proved every member agrees on.
        const loadOf = (panel) => panelWatts * this.getPanelLoadFactor(layerOfPanel(panel), panel);
        // Per-run overrides: a cabinet on a hand-drawn override anywhere in
        // the path scope is already fed, so the automatic walk lays over
        // everything else. Empty for every project without overrides, and
        // then the filters below keep every list byte-identical.
        const claimed = (typeof this._overrideClaims === 'function')
            ? this._overrideClaims(layer, 'power') : new Set();
        const unclaimed = (panels) => (claimed.size === 0
            ? panels : panels.filter(p => !claimed.has(p)));
        const visibleOrdered = unclaimed(plan
            ? plan.ordered.filter(c => !c.panel.hidden).map(c => c.panel)
            : this.getOrderedPanelsByPattern(layer, pattern, false));
        if (visibleOrdered.length === 0) {
            return this._mergeOverrideCircuits(layer, { circuits: [], error: null });
        }

        if (panelWatts > wattsPerCircuit) {
            return { circuits: [], error: { message: 'PANEL WATTS EXCEED CIRCUIT CAPACITY' } };
        }

        // `layers`, index-aligned with `circuits` the way screenCircuits has
        // written it for hand-drawn cross-member paths since v0.11.0, so the
        // soca planner charges every cabinet at its OWN member's wattage and the
        // power tinting can key a peer's cabinet by (layer, row, col). Under the
        // crossing gate the members all share panelWatts, so the plan's figure
        // comes out right either way - it is set anyway, because a total that is
        // only ACCIDENTALLY correct is a total nobody can trust the next time
        // the gate moves. The key is added only when the route actually crosses,
        // so an ungrouped screen's return shape does not move at all.
        const withOwners = (result) => {
            if (!plan) return result;
            result.layers = (result.circuits || [])
                .map(panels => (panels || []).map(p => layerOfPanel(p)));
            return result;
        };

        const circuits = [];
        if (organized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(gridRows).keys()].map(i => (startsTop ? i : (gridRows - 1 - i)))
                : [...Array(gridCols).keys()].map(i => (startsLeft ? i : (gridCols - 1 - i)));

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
                    const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                    if (unitPanels.length === 0) continue;
                    const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                    if (unitLoad > wattsPerCircuit) {
                        return {
                            circuits: [],
                            error: {
                                message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                                unitType: isHorizontalFirst ? 'row' : 'column',
                                unitCount: isHorizontalFirst ? gridCols : gridRows,
                                // the offending unit's own watts, so the empty
                                // soca panel can say WHY with real figures
                                unitLoad
                            }
                        };
                    }
                    runs.push({
                        panels: unclaimed(this.getOrganizedPanelsForUnits(
                            layer, pattern, isHorizontalFirst, [idx], false, plan)),
                        load: unitLoad,
                    });
                }
                const manual = this.appliedSplitterGroups(
                    layer, runs.map((_, i) => i + 1));
                const packed = this._packPowerRuns(
                    runs, wattsPerCircuit, splitters.maxWays, manual);
                return this._mergeOverrideCircuits(layer, withOwners({
                    circuits: packed.circuits, runs: packed.runs,
                    runIds: packed.runIds, error: null }));
            }

            let current = { unitIndices: [], load: 0 };

            for (const idx of unitIndices) {
                const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                if (unitPanels.length === 0) continue;
                const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                if (unitLoad > wattsPerCircuit) {
                    return {
                        circuits: [],
                        error: {
                            message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                            unitType: isHorizontalFirst ? 'row' : 'column',
                            unitCount: isHorizontalFirst ? gridCols : gridRows,
                            // the offending unit's own watts, so the empty
                            // soca panel can say WHY with real figures
                            unitLoad
                        }
                    };
                }
                if (current.load > 0 && current.load + unitLoad > wattsPerCircuit) {
                    circuits.push(unclaimed(
                        this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false, plan)
                    ));
                    current = { unitIndices: [], load: 0 };
                }
                current.unitIndices.push(idx);
                current.load += unitLoad;
            }
            if ((current.unitIndices || []).length > 0) {
                circuits.push(unclaimed(
                    this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false, plan)
                ));
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

        return this._mergeOverrideCircuits(layer, withOwners({ circuits, error: null }));
    }

    // Fold this layer's overridden circuits into an automatic result: the
    // auto rows take numbers 1, 2, 3... SKIPPING every overridden number, the
    // override rows come in under the numbers the user took over, and the
    // whole set is handed back in ascending circuit order. `nums` appears on
    // the result ONLY when overrides are in play, so every other project's
    // return shape does not move by a key. On an error the automatic story is
    // the story - same as the ports side - and the result passes through.
    _mergeOverrideCircuits(layer, result) {
        if (result.error) return result;
        const reserved = (typeof this.getOverrideNums === 'function'
            && !this.isCustomPower(layer))
            ? this.getOverrideNums(layer, 'power') : [];
        if (reserved.length === 0) return result;
        const overrides = this._ownOverrideRuns(layer, 'power');
        const rows = [];
        let next = 1;
        (result.circuits || []).forEach((panels, i) => {
            while (reserved.includes(next)) next++;
            rows.push({
                num: next++,
                panels,
                layers: result.layers ? result.layers[i] : null,
                runs: result.runs ? result.runs[i] : null,
                runIds: result.runIds ? result.runIds[i] : null,
            });
        });
        const crossing = overrides.some(o => o.hits.some(h => h.layer.id !== layer.id));
        overrides.forEach(o => {
            rows.push({
                num: o.num,
                panels: o.hits.map(h => h.panel),
                layers: (result.layers || crossing)
                    ? o.hits.map(h => h.layer) : null,
                runs: result.runs ? [o.hits.length] : null,
                runIds: null,
            });
        });
        rows.sort((a, b) => a.num - b.num);
        const out = { circuits: rows.map(r => r.panels), error: null, nums: rows.map(r => r.num) };
        if (result.layers || crossing) {
            // Owner rows for the auto circuits that never had any: every
            // cabinet is this layer's own. _powerOwnerIdRows nulls those rows
            // back out downstream, so the tinting fast path stays untouched.
            out.layers = rows.map(r => r.layers || (r.panels || []).map(() => layer));
        }
        if (result.runs) {
            out.runs = rows.map(r => r.runs);
            out.runIds = rows.map(r => r.runIds);
        }
        return out;
    }

}

for (const k of Object.getOwnPropertyNames(_Power.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Power.prototype, k));
    }
}
