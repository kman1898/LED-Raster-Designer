// app-power: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The build whose US circuits first packed to 80% of the breaker: a show
// saved before it keeps its automatic 2fers and 3fers as they were
// (keepOlderShowShares).
const KEPT_SHARES_BEFORE = '1.5.4';

class _Power {

    // While ONE overridden run is open for redrawing, the editable runs ARE
    // the layer's overrides, so the step walks that list (clamped at its
    // ends) instead of the open number line - stepping onto a port the user
    // never took over would make the next click take it over silently.
    _steppedCustomIndex(layer, kind, delta) {
        const current = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        if (!this._isOverrideEditing(layer, kind)) {
            // A custom wall steps circuit by circuit, never leg by leg
            // (customCircuitRun below).
            if (kind === 'power' && this.isCustomPower(layer)) {
                // A cleared gap reads as the place of the circuit after it
                // (customCircuitShown), so Next from the gap lands on that
                // circuit, not past it.
                const shown = this.customCircuitShown(layer, current);
                const head = parseInt(this._customCircuitHead(layer, current), 10);
                const onCircuit = !this.usesCustomCircuits(layer)
                    || this.screenCircuits(layer).some(c => c.num === head);
                const target = shown + delta - (!onCircuit && delta > 0 ? 1 : 0);
                // Prev from a gap goes to the circuit before it. A gap with
                // no circuit before it (circuit 1 cleared) stays put: the
                // place-1 circuit is AFTER the gap, and stepping back must
                // never move forward.
                if (!onCircuit && delta < 0 && target < 1) return current;
                return this.customCircuitRun(layer, Math.max(1, target));
            }
            return Math.max(1, current + delta);
        }
        const nums = this.getOverrideNums(layer, kind);
        const at = nums.indexOf(current);
        const next = at === -1 ? 0
            : Math.max(0, Math.min(nums.length - 1, at + delta));
        return nums[next];
    }

    // ---- a custom circuit is read by circuit, not by drawn run ----------
    //
    // A custom 2fer or 3fer is ONE circuit whose legs each hold a drawn
    // number: a sharing fill over ten columns at 3fer draws runs 1-10 and
    // merges 1-3, 4-6 and 7-9, four circuits that print S1-1 to S1-4. The
    // owner's ruling, 2026-10-21: what you read and step is the circuit.
    // The active-circuit field shows the circuit's place on the wall (4,
    // not 10), Next / Prev / Tab step circuit by circuit, a typed number
    // is that circuit (5 is the next free one, not the middle leg of
    // S1-2), and a refusal names labels. The drawn numbers stay the
    // store's keys. With no share and no cleared gap every one of these is
    // the identity. A gap a Clear Circuit left is not a circuit, so the
    // field counts past it the way the labels do (2026-10-22).

    // The share groups of a custom screen's drawn runs, as the wall reads
    // them (appliedSplitterGroups): [[first, ...legs], ...].
    _customMergeGroups(owner) {
        if (!owner || !this.usesCustomCircuits(owner)) return [];
        const paths = owner.powerCustomPaths || {};
        const drawn = Object.keys(paths).map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && (paths[n] || []).length > 0);
        return this.appliedSplitterGroups(owner, drawn).merge;
    }

    // The circuit drawn run `num` is a leg of: its share's first run (the
    // number the circuit is labelled by), or the run itself.
    _customCircuitHead(owner, num) {
        const n = parseInt(num, 10);
        if (!owner || !Number.isFinite(n) || !this.isCustomPower(owner)) return num;
        const g = this._customMergeGroups(owner).find(ids => ids.includes(n));
        return g ? g[0] : num;
    }

    // The circuit number run `num` reads as: the circuit's place among the
    // wall's circuits (screenCircuits, a share counted once), the place its
    // label is named by. A number no circuit holds - past the last one, or
    // a gap a Clear Circuit left - reads as the place a circuit drawn there
    // would take, so the field and the label agree after a clear (the
    // owner's ruling, 2026-10-22: the drawn number counted the gap, and
    // the field read 4 over S1-3). With nothing drawn it is the number.
    customCircuitShown(owner, num) {
        const n = parseInt(num, 10) || 1;
        if (!owner || !this.usesCustomCircuits(owner)) return n;
        const head = parseInt(this._customCircuitHead(owner, n), 10) || n;
        return this.screenCircuits(owner).filter(c => c.num < head).length + 1;
    }

    // The drawn number circuit `shown` is written under: the first run of
    // the circuit in that place, or past the last circuit the next free
    // number, one after the highest drawn. The inverse of
    // customCircuitShown, so stepping and typing land on circuits and the
    // next free one, never on a cleared gap.
    customCircuitRun(owner, shown) {
        const want = Math.max(1, parseInt(shown, 10) || 1);
        if (!owner || !this.isCustomPower(owner) || !this.usesCustomCircuits(owner)) return want;
        const circuits = this.screenCircuits(owner);
        if (want <= circuits.length) return circuits[want - 1].num;
        const paths = owner.powerCustomPaths || {};
        const drawn = Object.keys(paths).map(k => parseInt(k, 10))
            .filter(k => Number.isFinite(k) && (paths[k] || []).length > 0);
        return Math.max(0, ...drawn) + 1;
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

    // A locked screen refuses a step that would MOVE its active number -
    // and only that: Prev / Shift+Tab at port 1 (or Next at the end of an
    // open override list) changes nothing, so it says nothing (the owner's
    // ruling, 2026-10-16: the error belongs to a change).
    stepCustomPort(delta) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        const view = window.canvasRenderer.viewMode;
        const layer = this.currentLayer;
        const moves = (kind) => {
            const current = kind === 'power'
                ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
            return this._steppedCustomIndex(layer, kind, delta) !== current;
        };
        if (view === 'data-flow' && this.isCustomFlowEditing(this.currentLayer)) {
            if (this._layerLocked(layer) && !moves('data')) return;
            if (this._lockedStepRefused(this.currentLayer)) return;
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
            // The active circuit of a custom group is the wall owner's
            // (powerPathOwner).
            const owner = this.powerPathOwner(layer);
            const ownerMoves = this._steppedCustomIndex(owner, 'power', delta)
                !== (owner.powerCustomIndex || 1);
            if (this._layerLocked(owner) && !ownerMoves) return;
            if (this._lockedStepRefused(owner)) return;
            this.ensureCustomPowerState(owner);
            owner.powerCustomIndex = this._steppedCustomIndex(owner, 'power', delta);
            if (this._overrideEditing && this._overrideEditing.kind === 'power'
                    && this._overrideEditing.layerId === owner.id) {
                this._overrideEditing.num = owner.powerCustomIndex;
            }
            this.saveState('Power Custom Circuit Change');
            this.saveClientSideProperties();
            this.updateLayers(this._pathPersistLayers(owner));
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
        mappingMaxBtn.title = 'Ports fill to max pixel capacity, and may split mid-row/column.' + rectNote;

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
        // ...and the mirror's read-only data map (app-mirror-screens.js):
        // the map controls dim while the shown screen is a mirror.
        if (typeof this.updateMirrorDataLock === 'function') {
            this.updateMirrorDataLock();
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
                capacityEl.textContent = portCapacity.toLocaleString('en-US');
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
                panelsPerPortEl.textContent = panelsPerPort.toLocaleString('en-US');
                panelsPerPortEl.classList.add('value-normal');
                panelsPerPortEl.style.color = '';
            }
        }
        
        // Calculate total ports required from assignments
        const usesRectangle = this.usesRectangleConstraint(processorType);
        // Data side: a legacy `blank` is no cabinet, exactly like hidden.
        const visiblePanels = this.currentLayer.panels ? this.currentLayer.panels.filter(p => !p.hidden && !p.blank).length : 0;
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

    // ---- what one circuit carries (the owner's rulings, 2026-10-22) --------
    //
    // A show load is continuous, so a US circuit is packed to 80% of its
    // breaker: a 120V / 20A circuit carries 16 A, 1,920 W. The packing % is
    // the REGION's ("It needs to be valid for the region. US is 80"):
    //   - a circuit on a US distro packs at 80% whatever its voltage, so a
    //     240 V screen on a US 120/240 distro is 80% too;
    //   - a US distro marked "100% rated breakers" packs at the breaker;
    //   - a circuit on a UK/EU distro packs at the breaker;
    //   - a screen on no distro decides by its voltage: 208 V or under (110,
    //     120, 208) is US at 80%, 220/230/240 V is at the breaker.
    // A screen on several distros packs at the lowest of them, so it fits
    // on every one. This is the ONE figure everything that asks "does it
    // fit on a circuit" reads: the automatic packer, the sidebar's
    // Watts/Circuit and Panels/Circuit, the custom caps and readouts, the
    // share and Nfer amps rule. It is the same % the distro's own breaker
    // check holds a circuit to (distroChecks), so a fully packed circuit
    // never trips that warning.
    //   { voltage, breakerA, pct, amps, watts, us, rated100, byDistro }
    // `byDistro`: a distro decided the %, not the voltage.
    circuitCapacity(layer) {
        const voltage = parseFloat(layer && layer.powerVoltage) || 0;
        const breakerA = parseFloat(layer && layer.powerAmperage) || 0;
        const rule = this._circuitPackRule(layer, voltage);
        const pct = rule.pct;
        const amps = breakerA * pct;
        return { voltage, breakerA, pct, amps, watts: voltage * amps,
                 us: rule.us, rated100: rule.us && pct >= 1, byDistro: !!rule.byDistro,
                 onDistro: !!rule.onDistro };
    }

    // The watts one circuit of `layer` carries (circuitCapacity).
    circuitCapacityWatts(layer) {
        return this.circuitCapacity(layer).watts;
    }

    // How a sentence names the circuit: "a 15 A circuit held to 12 A (80%)"
    // on a US screen, "a 16 A circuit" at the breaker.
    circuitLimitText(layer) {
        const cap = this.circuitCapacity(layer);
        const breaker = +cap.breakerA.toFixed(2);
        if (cap.pct >= 1) return `a ${breaker} A circuit`;
        return `a ${breaker} A circuit held to ${+cap.amps.toFixed(2)} A `
            + `(${Math.round(cap.pct * 100)}%)`;
    }

    // The sidebar's line beside the Amperage box: "20 A breaker · 16 A
    // usable" on an 80% circuit, "20 A breaker · 20 A usable" at 100%.
    // Empty with no breaker typed.
    circuitUsableText(layer) {
        const cap = this.circuitCapacity(layer);
        if (!(cap.breakerA > 0)) return '';
        return `${+cap.breakerA.toFixed(2)} A breaker · ${+cap.amps.toFixed(2)} A usable`;
    }

    // Why the screen's circuits pack at the % they do, in one sentence.
    circuitPctReason(layer) {
        const cap = this.circuitCapacity(layer);
        if (cap.pct < 1) {
            return 'A US circuit carries a continuous load to 80% of its breaker. '
                + 'A US distro marked "100% rated breakers" packs to the breaker.';
        }
        if (cap.us) return 'Its distro has 100% rated breakers, so it packs to the breaker.';
        if (cap.byDistro) return 'A UK/EU circuit packs to its breaker.';
        // an old distro record with no system picked has no say, so the
        // voltage decides (_circuitPackRule), as on no distro
        if (cap.onDistro) {
            return 'Its distro has no system picked, so a screen above 208 V packs to its breaker.';
        }
        return 'A screen on no distro above 208 V packs to its breaker.';
    }

    // The packing % one distro holds its circuits to: 80% on a US system,
    // the breaker when it is marked "100% rated breakers" or on a UK/EU
    // system. Null for an old record whose system is unknown: it has no
    // say, and the screen's voltage decides (distroChecks has no breaker
    // check for it either).
    _distroPackPct(d) {
        const region = d && typeof this.distroRegion === 'function' ? this.distroRegion(d) : null;
        if (region === 'us') return d.breakers100 ? 1 : 0.8;
        if (region === 'eu') return 1;
        return null;
    }

    // { pct, us } for one screen's circuits (circuitCapacity). The distros
    // its multis are on decide, every member of its group counted (a wall
    // packs as one); a screen on none decides by voltage.
    //
    // A multi the screen no longer has (the wall got lighter and its last
    // multi went) can still have an entry in powerSocaDistro: those are
    // left out. How many multis a screen has depends on the % itself, so
    // it is counted at a fixed % with this rule switched off for the count
    // (_capacityProbe), never by asking getSocaPlan: at 80%, the most
    // circuits a screen normally makes, and, only when an entry lies past
    // that, at 100% too (a wall whose rows cannot fit at 80% makes no
    // circuits there at all). An entry past both counts is stale whatever
    // the %. An entry inside them holds a multi that exists at that %, so
    // the screen packs to it and that multi is real: the answer agrees
    // with itself.
    _circuitPackRule(layer, voltage) {
        const byVoltage = voltage > 0 && voltage < 208.5;
        const fallback = { pct: byVoltage ? 0.8 : 1, us: byVoltage };
        if (this._capacityProbe) return { pct: this._capacityProbe.pct, us: byVoltage };
        if (!layer) return fallback;
        if (typeof this.getDistros !== 'function') return fallback;
        const group = (layer.group_id && typeof this.groupMembersOf === 'function')
            ? this.groupMembersOf(layer) : [];
        const screens = group.length ? group : [layer];
        const distros = this.getDistros() || [];
        // [{ screen, index, d, pct }] for every entry naming a distro that exists
        const entries = [];
        for (const s of screens) {
            const map = (s && s.powerSocaDistro) || {};
            for (const key of Object.keys(map)) {
                const id = map[key];
                const index = parseInt(key, 10);
                if (!id || !Number.isFinite(index) || index < 1) continue;
                const d = distros.find(x => x && x.id === id);
                if (!d) continue;
                const own = this._distroPackPct(d);
                entries.push({ screen: s, index, d,
                               pct: own === null ? fallback.pct : own,
                               region: own === null ? null : this.distroRegion(d) });
            }
        }
        if (!entries.length) return fallback;
        const decide = (list) => {
            if (!list.length) return fallback;
            const pct = Math.min(...list.map(e => e.pct));
            // US when any distro deciding is a US one (or, on old records,
            // the voltage said so)
            const us = list.some(e => e.region === 'us' || (e.region === null && byVoltage));
            // a distro of a known system decided it; an old record whose
            // system is unknown leaves it to the voltage (onDistro says the
            // screen is on a distro all the same, for circuitPctReason)
            return { pct, us, byDistro: list.some(e => e.region !== null), onDistro: true };
        };
        // Every entry agreeing with the voltage's %: a stale one cannot
        // change it, so nothing needs counting (the common case).
        if (entries.every(e => e.pct === fallback.pct)) {
            const d = decide(entries);
            return { pct: fallback.pct, us: d.us, byDistro: d.byDistro, onDistro: true };
        }
        const counts = new Map();
        const live = entries.filter(e => {
            if (!counts.has(e.screen)) counts.set(e.screen, this._multiCountAt(e.screen, 0.8));
            if (e.index <= counts.get(e.screen)) return true;
            return e.index <= this._multiCountAt(e.screen, 1);
        });
        return decide(live);
    }

    // How many multis `layer` has when its circuits are packed at `pct` of
    // the breaker, for _circuitPackRule's stale-entry rule. Every screen
    // the count packs reads `pct` (_capacityProbe). Memoized for the naming
    // burst (_circuitTailCache), which every edit that moves circuits drops.
    _multiCountAt(layer, pct) {
        const cache = this._circuitTailCache;
        if (cache && this._multiCountMemoFor !== cache) {
            this._multiCountMemoFor = cache;
            this._multiCountMemo = new Map();
        }
        const memo = cache ? this._multiCountMemo : null;
        const key = `${pct}`;
        const seen = memo ? memo.get(layer) : null;
        if (seen && key in seen) return seen[key];
        const outer = this._capacityProbe;
        this._capacityProbe = { pct };
        let n = 0;
        try {
            const circuits = this.screenCircuits(layer) || [];
            n = circuits.length ? this.socaCountFor(layer, circuits.length) : 0;
        } finally {
            this._capacityProbe = outer;
        }
        if (memo) memo.set(layer, Object.assign(seen || {}, { [key]: n }));
        return n;
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
            const usableEl = document.getElementById('power-amperage-usable');
            if (usableEl) { usableEl.textContent = ''; usableEl.title = ''; }
            return;
        }
        const layer = this.currentLayer;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        // 80% of the breaker on a US screen (circuitCapacity).
        const capacity = this.circuitCapacity(layer);
        const wattsPerCircuit = capacity.watts;
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
        // The balanced 3φ figure divides by the SERVICE's line-to-line
        // voltage (1.5, bug fix 3) - a 120V screen on 120/208 is
        // W / (208 x 1.73), never W / (120 x 1.73).
        const lineV = this.threePhaseLineVoltage(layer);
        const totalAmps3 = lineV > 0 ? totalWatts / (lineV * 1.73) : 0;
        layer._powerTotalAmps1 = totalAmps1;
        layer._powerTotalAmps3 = totalAmps3;

        const wattsEl = document.getElementById('power-watts-per-circuit');
        const panelsEl = document.getElementById('power-panels-per-circuit');
        const circuitsEl = document.getElementById('power-circuits-required');
        const amps1El = document.getElementById('power-total-amps-1ph');
        const amps3El = document.getElementById('power-total-amps-3ph');

        // The Amperage box is the BREAKER SIZE (the owner's rulings,
        // 2026-10-22: it keeps its Amperage label); the usable amps show beside it, so a 16 typed on a
        // US screen reads "16 A breaker · 12.8 A usable" and a double
        // derating is there to see.
        const usableEl = document.getElementById('power-amperage-usable');
        const usableText = this.circuitUsableText(layer);
        if (usableEl) {
            usableEl.textContent = usableText;
            usableEl.title = usableText ? this.circuitPctReason(layer) : '';
        }
        if (wattsEl) {
            wattsEl.textContent = wattsPerCircuit > 0 ? wattsPerCircuit.toLocaleString('en-US') : '0';
            wattsEl.title = wattsPerCircuit > 0
                ? `What one circuit carries: ${voltage} V × ${+capacity.amps.toFixed(2)} A usable `
                    + `(${Math.round(capacity.pct * 100)}% of the ${amperage} A breaker). `
                    + this.circuitPctReason(layer)
                : '';
        }
        if (panelsEl) {
            panelsEl.textContent = panelsPerCircuit > 0 ? panelsPerCircuit.toLocaleString('en-US') : '0';
            panelsEl.title = wattsPerCircuit > 0 && panelWatts > 0
                ? `How many ${panelWatts} W panels fit on one circuit: its `
                    + `${+capacity.amps.toFixed(2)} A usable of the ${amperage} A breaker, `
                    + `${wattsPerCircuit.toLocaleString('en-US')} W.`
                : '';
        }
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

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString('en-US') : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        // The screen that carries a wall's circuits reads the WALL's load
        // beside the wall's circuit count - the figure its circuits draw,
        // every member's panels counted once (getCarriedPowerLoad) - the
        // way its canvas label already does. A screen that routes alone
        // reads its own panels, exactly as before; the cached
        // _powerTotalAmps1/3 stay this screen's own either way.
        const carried = circuitsRequired > 0 ? this.getCarriedPowerLoad(layer) : null;
        const wall = carried && carried.peers.length ? carried : null;
        const shownAmps1 = wall ? wall.amps1 : totalAmps1;
        const shownAmps3 = wall ? wall.amps3 : totalAmps3;
        const wallTitle = wall
            ? `The wall's load on these circuits: ${[layer, ...wall.peers].map(l => l.name).join(' + ')}` : '';
        if (amps1El) { amps1El.textContent = shownAmps1 ? shownAmps1.toFixed(2) + ' A' : '0'; amps1El.title = wallTitle; }
        if (amps3El) { amps3El.textContent = shownAmps3 ? shownAmps3.toFixed(2) + ' A' : '0'; amps3El.title = wallTitle; }
        // The cap under the custom controls reads the same figures.
        this._syncCustomFillReadout('power');
        // A change that cuts a row, or stops cutting one, shows or hides
        // the Circuit numbers switch.
        this.syncPowerNumberOrder(layer);
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
        // The held multi numbers follow their multis the same way
        // (app-naming _rekeyMultiHolds) - they live on the distros.
        if (typeof this._rekeyMultiHolds === 'function') {
            this._rekeyMultiHolds(layer, n => (delta > 0
                ? (n >= at ? n + 1 : n)
                : (n === at ? null : (n > at ? n - 1 : n))));
        }
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
        if (typeof this._rekeyMultiHolds === 'function') {
            this._rekeyMultiHolds(layer, n => (map.has(n) ? map.get(n).index : null));
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
        // A face box (1.5) is as big as its connector. A DIRECT output is one
        // circuit: it takes the circuit it was dropped on, the way a circuit
        // chip does, not the first of the cell.
        const targetD = this.getDistros().find(x => x.id === distroId);
        const faceBox = targetD ? this.faceBox(targetD, n) : null;
        // The anchor: the cell's first circuit, stepped past every circuit
        // before `o` that is on another box.
        let start = faceBox && faceBox.size === 1 ? o : cellStart;
        for (const s of segs) {
            if (s.end < cellStart || s.start > o) continue;
            if (onOther(s)) start = Math.max(start, s.end + 1);
        }
        const remaining = o - start + 1;
        let held = 0;
        // The target box's fan is as big as the SMALLEST breakout claiming
        // it - a 3-tail L21-30 box has three tails whoever else lands on
        // it, and pretending to six would deal tails that do not exist.
        let cap = faceBox ? Math.min(size, faceBox.size) : size;
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
        // A paired connector (1.5): the same circuits on another connector.
        // A circuit can be patched to either, never both - so a box whose
        // circuits are in use through its pair takes nothing (a direct
        // output asks about its one circuit, a multi about any of its).
        if (faceBox && faceBox.paired !== undefined) {
            const busy = this._facePairedHolders(targetD, n, faceBox.size === 1 ? 1 : null);
            if (busy.length) {
                return { ok: false, why: 'paired', free: 0, remaining, take: 0,
                         nums: [], seg, ordinal: o, spanStart: start, busy };
            }
        }
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
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return { ok: false, why: 'locked', free: 0, tailLen: 0, locked: true };
        const plan = this._socaTakePlan(layer, ordinal, distroId, number);
        if (!plan.ok) return { ok: false, why: plan.why, free: plan.free,
                               tailLen: plan.remaining };
        // A locked screen the take would REPACK - one grouped with this
        // screen, whose packing % the group shares - keeps it unchanged
        // (owner, 2026-10-22): the take is tried and put back, and when it
        // moves a locked screen's % it is refused whole, the screen named.
        if (this._takeRepacksLocked(layer, plan, distroId)) {
            return { ok: false, why: 'locked', free: 0, tailLen: 0, locked: true };
        }
        const touched = this._takeSocaApply(layer, plan, distroId);
        this.updateLayers([...touched], true, action || 'Assign Multi Distro');
        return { ok: true, took: plan.take, tailLen: plan.remaining,
                 free: plan.free };
    }

    // True (the locked screens named) when the take `plan` onto `distroId`
    // would repack a locked screen (_repackRefused). A plan that cannot
    // happen moves nothing. Asked by takeSocaOnto, and by a drop before
    // anything of it is written (the box type it stamps).
    _takeRepacksLocked(layer, plan, distroId) {
        if (!layer || !plan || !plan.ok) return false;
        return this._repackRefused(() => this._takeSocaApply(layer, plan, distroId), [layer]);
    }

    // takeSocaOnto's store moves on their own, no history entry and no
    // checks: resegment, re-key, stamp, assign. Returns the touched layers
    // (a Set). Run for real by takeSocaOnto, and as the trial its repack
    // check puts back (_repackRefused).
    _takeSocaApply(layer, plan, distroId) {
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
                      name: (layer.powerSocaNames || {})[cut.index], pos,
                      // an auto multi's number stays with the remainder,
                      // which stays on the box (multi numbers do not shift)
                      shown: (rec && !rec.pinned && rec.distroId === assign[cut.index])
                          ? rec.number : null };
            if (carry.number != null) {
                this._materializeSocaBox(carry.distro, carry.number, layer,
                                         cut.index)
                    .forEach(l => touched.add(l));
            }
        }
        // A multi on no distro has no feed, so nothing typed under it is
        // this drop's: a home run or circuit cable an older file left on
        // an unfed multi in the span never rides into the new feed (owner,
        // 2026-10-17 - a new feed on the same index starts blank). Read
        // before the re-key, which would carry the stale entry across.
        const unfed = segs.filter(s => s.end >= start && s.start <= end
            && !assign[s.index]);
        if (unfed.length) {
            const circuitList = this.screenCircuits(layer);
            unfed.forEach(s => this._forgetFeedLengths(layer, s.index,
                circuitList.slice(s.start - 1, s.end).map(c => c.num)));
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
            if (carry.number == null && carry.shown != null
                    && typeof this._holdMultiNumber === 'function') {
                this._holdMultiNumber(layer, remIdx, carry.distro, carry.shown);
            }
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
        return touched;
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
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return false;
        const count = this.screenCircuits(layer).length;
        const seg = this._socaSegments(layer, count)
            .find(s => s.index === Number(socaIndex));
        if (!seg || !seg.userEnd) return false;
        // The weld can take the second part's distro off the wall (the
        // first part's identity wins): a locked screen that would repack -
        // one grouped with this screen - refuses it whole (owner,
        // 2026-10-22).
        if (this._repackRefused(() => {
            layer.powerSocaSplits = this._socaSplitPoints(layer, count)
                .filter(p => p !== seg.end);
            this._spliceSocaStores(layer, Number(socaIndex) + 1, -1);
        }, [layer])) return false;
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
    // the one 'Unplug Circuit' entry, so a single undo puts back the cuts,
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

    // The watts a set of cabinets draws on `layer`'s circuit: each cabinet
    // at its own screen's Watts per Panel (a cross-member circuit carries a
    // peer's cabinets, and `srcLayers` - index-aligned with `panels`, as
    // screenCircuits hands it back - names the peer; absent or same-layer
    // entries take the owner's figure), derated by the half-tile load
    // factor. The one load sum behind the soca plan's leg amps, the chip's
    // fill and the share rule below - so they can never disagree.
    _circuitWatts(layer, panels, srcLayers) {
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const src = srcLayers || [];
        return (panels || []).reduce((s, p, pi) => {
            // a blank cabinet (on a hand-drawn path) draws nothing
            if (!p || p.blank) return s;
            const from = src[pi];
            const w = (from && from !== layer)
                ? (parseFloat(from.panelWatts) || 0) : panelWatts;
            return s + w * this.getPanelLoadFactor(from || layer, p);
        }, 0);
    }

    // The load this screen's CIRCUITS carry - the wall's load when the
    // screen carries a group's walk. A wall routed as one hands every
    // circuit to its first member and none to its peers, so the owner's
    // own cabinets say only part of what its circuits draw and the peer's
    // say nothing that any circuit of its own draws. This is the sum the
    // circuit table is built from (_circuitWatts: each cabinet at its own
    // screen's Watts per Panel and half-tile factor, at the carrying
    // screen's voltage), a blank cabinet left out the way every load
    // figure leaves it out, so a wall's figure is its members' panels
    // counted once - never a member twice, never one dropped.
    //   { watts, voltage, amps1, amps3, circuits, peerIds, peers }
    // `peers` are the OTHER screens whose cabinets ride these circuits,
    // in wall order; empty for every screen that routes alone.
    getCarriedPowerLoad(layer) {
        const voltage = layer ? (parseFloat(layer.powerVoltage) || 0) : 0;
        const out = { watts: 0, voltage, amps1: 0, amps3: 0, circuits: 0, peerIds: [], peers: [] };
        if (!layer || (layer.type || 'screen') !== 'screen') return out;
        const peers = new Map();
        for (const c of this.screenCircuits(layer)) {
            out.circuits++;
            const src = c.layers || [];
            const panels = [], from = [];
            (c.panels || []).forEach((p, i) => {
                if (!p || p.blank) return;
                panels.push(p);
                from.push(src[i]);
                const l = src[i];
                if (l && l !== layer && l.id !== layer.id && !peers.has(String(l.id))) peers.set(String(l.id), l);
            });
            out.watts += this._circuitWatts(layer, panels, from);
        }
        out.peers = [...peers.values()];
        out.peerIds = out.peers.map(l => l.id);
        out.amps1 = voltage > 0 ? out.watts / voltage : 0;
        // the service's line-to-line voltage (bug fix 3)
        const lineV = this.threePhaseLineVoltage(layer);
        out.amps3 = lineV > 0 ? out.watts / (lineV * 1.73) : 0;
        return out;
    }

    getSocaPlan(layer) {
        if (!layer) return [];
        const circuits = this.screenCircuits(layer);   // [{num, panels}] in circuit order
        if (!circuits.length) return [];
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
            const watts = this._circuitWatts(layer, c.panels, c.layers);
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
                // a blank cabinet on a drawn path is fed by nothing
                tiles: c.panels.filter(p => p && !p.blank).length, watts,
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
    // a multi is 6 channels); Edison is the 110V option beside them (user
    // ruling, 2026-09-22: a 110V / 120V screen runs a multi with True1,
    // powerCON or Edison breakouts), and L6-20 breakouts add L6-20 ->
    // panel tails per circuit.
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
            { id: 'soca-true1', name: 'Multi → TRUE1', connector: 'TRUE1', boxSize: 6, breakoutItem: 'Multi breakouts → TRUE1' },
            { id: 'soca-powercon', name: 'Multi → powerCON', connector: 'powerCON', boxSize: 6, breakoutItem: 'Multi breakouts → powerCON' },
            { id: 'soca-edison', name: 'Multi → Edison (110V)', connector: 'Edison', boxSize: 6, breakoutItem: 'Multi breakouts → Edison', tailItem: 'Edison → panels' },
            { id: 'soca-l620', name: 'Multi → L6-20', connector: 'L6-20', boxSize: 6, breakoutItem: 'Multi breakouts → L6-20', tailItem: 'L6-20 → panels' },
            // The L21-30 breakout (user ruling, 2026-08-28): fed by an
            // L21-30 at 30 A per leg, splitting to 3 x 208V circuits on
            // True1 or powerCON - a leg-PAIR circuit per tail, never a
            // 6-circuit soca. It hangs on a distro number like a multi
            // does, with 3 tails.
            { id: 'l2130-true1', name: 'L21-30 (3 × 208V) → TRUE1', connector: 'TRUE1', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → TRUE1' },
            { id: 'l2130-powercon', name: 'L21-30 (3 × 208V) → powerCON', connector: 'powerCON', boxSize: 3, feedLegA: 30, breakoutItem: 'L21-30 breakouts → powerCON' }
        ];
    }

    // The breakout a screen with nothing (eligible) stored reads and is
    // written: Edison for 0 < V <= 120, True1 for anything else - the
    // fallback normalizePowerBreakout stores and getPowerBreakout reads,
    // one rule so the paperwork and the reading never disagree.
    _defaultBreakoutFor(voltage) {
        const types = this.getPowerBreakoutTypes();
        const v = this.voltageNumber(voltage);
        if (v > 0 && v <= 120) {
            return types.find(t => t.id === 'soca-edison') || types[0];
        }
        return types[0];
    }

    // The breakout a screen with nothing (eligible) stored is written -
    // the second and third rungs of the write-in order (user ruling,
    // 2026-09-22: "if 208 is default then True1 is default, but that
    // should be set in preferences"): the Preferences breakout
    // (prefs.breakoutType, the key applyNewScreenPowerPreferences reads)
    // when the screen's voltage allows it, else the voltage class default
    // (_defaultBreakoutFor). The server's preferred_power_breakout is the
    // same two rungs, so both copies of a screen land on one answer.
    _preferredBreakoutFor(voltage) {
        const prefs = typeof this.getPreferences === 'function' ? this.getPreferences() : null;
        const wantId = prefs && prefs.breakoutType;
        const want = this.getPowerBreakoutTypes().find(t => t.id === wantId);
        if (want && this._breakoutEligible(want, voltage)) return want;
        return this._defaultBreakoutFor(voltage);
    }

    // The breakout in force on a screen. A stored choice that is eligible
    // at the screen's voltage stands as written (it is somebody's
    // paperwork). Anything else - nothing stored, an id the catalog no
    // longer has, or a choice the voltage cannot run (Edison at 208V,
    // L21-30 at 120V) - reads what normalizePowerBreakout would write
    // (_preferredBreakoutFor). User ruling, 2026-09-22: "screens need to
    // be set to true1 or powercon or edison. they have to be set" - so
    // the store is what decides, and normalizePowerBreakout writes the
    // same answer in on load and on a voltage change; this read-side
    // fallback only covers the moment between a bare property write and
    // that normalize, so no surface (box type, tails, cable sheet, pull
    // list) can ever read a breakout the screen's voltage cannot run.
    getPowerBreakout(layer) {
        const types = this.getPowerBreakoutTypes();
        const stored = types.find(t => t.id === (layer && layer.powerBreakoutType));
        if (stored && this._breakoutEligible(stored, layer.powerVoltage)) return stored;
        return this._preferredBreakoutFor(layer && layer.powerVoltage);
    }

    // ---- the panel input --------------------------------------------------
    //
    // Panels take power in on TRUE1 or powerCON and nothing else (owner,
    // 2026-10-21). A TRUE1 or powerCON breakout IS the panel input; an
    // Edison or L6-20 breakout is not, so those screens carry their own
    // choice, layer.powerPanelInput ('true1' / 'powercon'; absent reads
    // TRUE1, so a show from before it reads as it always did). The
    // jumpers, the splitters and the Edison / L6-20 adapter cables follow it.
    getPanelInputTypes() {
        return [{ id: 'true1', name: 'TRUE1' }, { id: 'powercon', name: 'powerCON' }];
    }

    // Whether a breakout leaves the panel input to the screen.
    breakoutHasPanelInputChoice(bt) {
        const id = bt && bt.id;
        return id === 'soca-edison' || id === 'soca-l620';
    }

    // The panel input in force on a screen: { id, name }.
    panelInput(layer) {
        const types = this.getPanelInputTypes();
        const bt = layer ? this.getPowerBreakout(layer) : null;
        if (bt && !this.breakoutHasPanelInputChoice(bt)) {
            const own = types.find(t => t.id === this._cableConnectorId(bt.connector));
            if (own) return own;
        }
        return types.find(t => t.id === (layer && layer.powerPanelInput)) || types[0];
    }

    // The type of a cable that runs straight to the panels off a distro
    // outlet (a direct output): the panel input alone where the plug is
    // already that, else both ends, "CEE 16A → TRUE1".
    directCableType(plugName, layer) {
        const input = this.panelInput(layer).name;
        const plug = String(plugName || '').trim();
        return !plug || plug === input ? input : `${plug} → ${input}`;
    }

    // The store's normalizer (user ruling, 2026-09-22: a screen always
    // carries an explicit breakout). Writes powerBreakoutType when it is
    // missing, empty, unknown to the catalog, or ineligible at the
    // layer's voltage: the Preferences breakout when the voltage allows
    // it, else Edison for 0 < V <= 120 and True1 otherwise. A stored
    // ELIGIBLE choice is never touched: l2130-* at 208V stays, soca-l620
    // above 120V stays. Runs on every load path beside
    // normalizePowerCircuitColors and after every voltage write
    // (setScreenVoltage), so 208 -> 120 with a stored L6-20 or L21-30 is
    // rewritten. The server runs the same rule on every route that stores
    // or serves a screen (app.normalize_power_breakout). Returns true when
    // it wrote.
    normalizePowerBreakout(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return false;
        const types = this.getPowerBreakoutTypes();
        const stored = types.find(t => t.id === layer.powerBreakoutType);
        if (stored && this._breakoutEligible(stored, layer.powerVoltage)) return false;
        layer.powerBreakoutType = this._preferredBreakoutFor(layer.powerVoltage).id;
        return true;
    }

    // The voltage options the sidebar select offers as-is; any other
    // figure is a Custom one, and powerVoltageCustom is where the custom
    // box's figure is cached. Kept beside setScreenVoltage, its only
    // reader, so the list cannot drift from the write.
    _stockScreenVoltages() { return [110, 208, 220, 230, 240]; }

    // THE one way a screen's voltage is written (2026-09-22). Stores
    // powerVoltage, keeps powerVoltageCustom in step when the figure is
    // not a stock option (so a reload of the sidebar shows the figure the
    // screen runs at), and normalizes the breakout in the same step, so
    // no write path - sidebar, group dialog, group propagation, the
    // defaults sweeps, Preferences on the pristine screen - can leave a
    // breakout the new voltage cannot run. tests/test_breakout_invariant.py
    // reads the JS source and fails on a bare `powerVoltage =` write that
    // does not go through here or normalize within a few lines. Returns
    // true when the breakout was rewritten.
    setScreenVoltage(layer, volts) {
        if (!layer) return false;
        layer.powerVoltage = volts;
        const v = this.voltageNumber(volts);
        if (v > 0 && !this._stockScreenVoltages().includes(v)) {
            layer.powerVoltageCustom = volts;
        }
        return this.normalizePowerBreakout(layer);
    }

    // How many circuits one physical box on THIS screen holds. The one
    // authority for the box shape - segmentation, tail clamps, the balance
    // search, the leg maps and the dock's chip grid all read it, so a
    // 3-tail L21-30 box can never render six chips or deal a tail 4.
    socaBoxSize(layer) {
        const n = Number(this.getPowerBreakout(layer).boxSize);
        return Number.isFinite(n) && n >= 1 ? n : 6;
    }

    // THE one reader of a screen's voltage figure for every rule below
    // (eligibility, the class, the defaults, the distro gate) - and the
    // server's _power_voltage_number (app.py) is written to answer the
    // same, so the two copies of a screen never hold different breakouts.
    // A string reads as parseFloat reads it ('208V' is 208, '1_000' is 1,
    // 'abc' is NaN); a number is itself; anything else (null, a bool, an
    // array, an object - parseFloat([208]) would read 208 through
    // toString, and the server has no such rule) is no voltage. A result
    // that is not finite ('Infinity', '1e400') is no voltage either:
    // before 2026-09-23 parseFloat('Infinity') put a screen in the 208
    // class here while the server read it as blank.
    // tests/test_breakout_invariant.py drives one table through both.
    voltageNumber(value) {
        if (typeof value !== 'number' && typeof value !== 'string') return 0;
        const v = parseFloat(value);
        return Number.isFinite(v) ? v : 0;
    }

    // Which breakouts a screen's voltage can legally run (user ruling,
    // 2026-09-22: a screen at 110V or 120V runs a multi with True1,
    // powerCON or Edison breakouts - this replaces the 2026-08-28 ruling
    // that a 110V screen could only have Edison on it; Edison is a 110V
    // breakout and is out ABOVE 120V; the L21-30 box is documented as
    // 3 x 208V and enables at exactly 208V. Nothing else is restricted,
    // and no rule is extrapolated to voltages or products the ruling does
    // not cover - an L6-20 breakout at 110V / 120V stays out because the
    // ruling does not name it, and a blank voltage (0) restricts nothing
    // but the L21-30). The select disables what is ineligible, and
    // normalizePowerBreakout rewrites a stored ineligible choice on load
    // and on a voltage change, so the store never holds one for long.
    _breakoutEligible(type, voltage) {
        const v = this.voltageNumber(voltage);
        const id = String(type && type.id);
        if (v > 0 && v <= 120) {
            return ['soca-true1', 'soca-powercon', 'soca-edison'].includes(id);
        }
        if (id === 'soca-edison') return v <= 0;
        if (id.startsWith('l2130-')) return v === 208;
        return true;
    }

    // Why the select greys a breakout at this voltage - the option title.
    _breakoutIneligibleTitle(type, voltage) {
        const v = this.voltageNumber(voltage);
        const at = v > 0 ? `at ${v}V` : 'until a voltage is set';
        const id = String(type && type.id);
        if (id.startsWith('l2130-')) return `Not available ${at}: L21-30 is 208V only.`;
        if (id === 'soca-edison') return `Not available ${at}: Edison is for screens up to 120V.`;
        return `Not available ${at}: a screen up to 120V runs Multi → TRUE1, powerCON or Edison.`;
    }

    // The voltage CLASS a screen belongs to for distro matching, as a
    // RANGE: 120 when 0 < V <= 120 (the single-leg circuits - 110V and
    // 120V ride one leg of the 208V three-phase distro), 208 when V > 120
    // (the leg-pair circuits: 208 and the stock 220 / 230 / 240 options
    // behave exactly as 208 does for gating - a Multi 208 feeds them, a
    // Multi 120 is refused naming the screen's voltage). Null for a blank
    // or non-positive figure, which is matched by breakout alone.
    _voltageClass(voltage) {
        const v = this.voltageNumber(voltage);
        if (v > 0 && v <= 120) return 120;
        if (v > 120) return 208;
        return null;
    }

    // Whether an output type feeds a screen at this voltage. A type's
    // `volts` list names the voltages it is documented for; a Multi
    // matches by CLASS (any listed figure in the screen's class - so
    // soca208's [208] covers 230V, soca120's [110, 120] covers 100V),
    // while a type marked `voltsExact` (the L21-30, documented at 208V
    // only) matches the figure itself. A screen at a blank voltage, or a
    // type without the list, is not gated on voltage.
    _outputFeedsVoltage(type, voltage) {
        if (!type || !Array.isArray(type.volts)) return true;
        const v = this.voltageNumber(voltage);
        if (!(v > 0)) return true;
        if (type.voltsExact) return type.volts.includes(v);
        const cls = this._voltageClass(v);
        return type.volts.some(x => this._voltageClass(x) === cls);
    }

    // What an output type feeds, in the screen's terms: "screens up to
    // 120V" / "screens above 120V" for a class-matched Multi, "208V
    // screens" for the exact-voltage L21-30.
    _outputFeedsText(type) {
        const volts = (type && type.volts) || [];
        if (type && type.voltsExact) {
            return `${volts.map(x => `${x}V`).join(' and ')} screens`;
        }
        const classes = [...new Set(volts.map(x => this._voltageClass(x)))]
            .filter(c => c != null);
        return classes.map(c => c === 120 ? 'screens up to 120V'
                                          : 'screens above 120V').join(' and ');
    }

    // How a refusal says the voltage mismatch: "WALL B runs at 120V — a
    // Multi 208 output feeds screens above 120V". Null when the type feeds
    // the screen's voltage.
    _voltageMismatchMessage(type, layer) {
        if (!type || !layer || this._outputFeedsVoltage(type, layer.powerVoltage)) return null;
        const v = this.voltageNumber(layer.powerVoltage);
        const article = /^(?:[AEIOU]|[FHLMNRSX](?![a-z]))/.test(type.name) ? 'an' : 'a';
        return `${layer.name} runs at ${v}V, and ${article} ${type.name} output `
            + `feeds ${this._outputFeedsText(type)}`;
    }

    // Gated like the sidebar select: a breakout the screen's voltage
    // cannot run is refused (nothing written, false returned), so no
    // caller can store an ineligible id through here.
    setPowerBreakout(layer, id) {
        if (!layer) return false;
        const type = this.getPowerBreakoutTypes().find(t => t.id === id);
        if (!type || !this._breakoutEligible(type, layer.powerVoltage)) return false;
        layer.powerBreakoutType = type.id;
        this.updateLayers([layer], true, 'Change Power Breakout');
        return true;
    }

    // ---- distro outputs -----------------------------------------------------
    //
    // The connector TYPES a distro can hand a screen (user ruling,
    // 2026-08-31: types only, no counts - the rating already bounds the
    // service and the LEGS line already says where it is). Each type names
    // the screen breakouts it can feed AND the voltages it feeds (`volts`,
    // read through _outputFeedsVoltage: by CLASS for a Multi - up to 120V
    // or above 120V - and by the exact figure for the L21-30), and that
    // table IS the matching rule (user ruling, 2026-09-22): a Multi 208
    // lands on a screen above 120V with a True1 / powerCON breakout, a
    // Multi 120 on a screen up to 120V with a True1, powerCON or Edison
    // breakout, an L21-30 on a 208V screen's L21-30 box. The voltage
    // matters because True1 and powerCON breakouts now exist at both
    // voltages. Nothing is extrapolated past the table - a breakout no
    // type names (L6-20) is a mismatch like any other, refused with the
    // fix said out loud, never silently re-typed; a screen at a blank
    // voltage matches by breakout alone. `faces` are the breakout
    // connectors the popover row shows beside the type; `badge` is the
    // bracket's text sub-pill.
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
            { id: 'soca208', name: 'Multi 208', sub: 'TRUE1 / powerCON',
              glyph: 'soca', faces: ['true1', 'powercon'], volts: [208],
              breakouts: ['soca-true1', 'soca-powercon'], badge: 'MULTI 208' },
            { id: 'soca120', name: 'Multi 120', sub: 'Edison / TRUE1 / powerCON',
              glyph: 'soca', faces: ['edison', 'true1', 'powercon'], volts: [110, 120],
              breakouts: ['soca-edison', 'soca-true1', 'soca-powercon'], badge: 'MULTI 120' },
            // voltsExact: the L21-30 is documented at 208V and nowhere
            // else, so it matches the figure, not the >120V class.
            { id: 'l2130', name: 'L21-30', sub: '3 × 208V',
              glyph: 'l2130', faces: ['true1', 'powercon'], volts: [208],
              voltsExact: true,
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
    //                   breakout AND voltage imply (a 120V True1 screen
    //                   implies Multi 120, a 208V True1 screen Multi 208),
    //                   the smallest-fan member deciding
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
        // Rung 0 (1.5): a box on a distro's FACE is what its output row
        // says - the connector is bolted to the distro, nothing on it or
        // stored about it changes that.
        const fbox = d ? this.faceBox(d, n) : null;
        if (fbox) {
            return { type: this.faceBoxType(d, fbox), source: 'face', implied: null,
                     clash: false, faceBox: fbox };
        }
        const list = Array.isArray(members) ? members
            : (d ? (this._distroMultiNumbers(d.id).get(n) || []) : []);
        let implied = null;
        for (const m of list) {
            const l = ((this.project && this.project.layers) || [])
                .find(x => x.id === m.layerId);
            const t = l ? this.outputTypeForBreakout(this.getPowerBreakout(l),
                                                     l.powerVoltage)
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
    // Returns true when it wrote. `persist` false leaves the save to the
    // caller: a whole-distro drop stamps every box it makes and persists
    // ONCE (one POST /api/project for the gesture, not one per multi).
    _stampBoxType(distroId, number, typeId, persist = true) {
        const d = this.getDistros().find(x => x.id === distroId);
        const n = parseInt(number, 10);
        if (!d || !Number.isFinite(n) || n < 1) return false;
        if (!this.getDistroOutputTypes().some(t => t.id === typeId)) return false;
        if (!d.boxTypes || typeof d.boxTypes !== 'object') d.boxTypes = {};
        if (d.boxTypes[n] === typeId) return false;
        d.boxTypes[n] = typeId;
        if (persist) this._persistDistros();
        return true;
    }

    // The output type a screen's (effective) breakout takes at its
    // voltage, or null for a breakout the table does not name. The
    // voltage decides between Multi 208 and Multi 120 for a True1 /
    // powerCON breakout (both feed those since 2026-09-22); left out, or
    // blank, the first type naming the breakout answers.
    outputTypeForBreakout(bt, voltage) {
        const id = bt && bt.id;
        return this.getDistroOutputTypes()
            .find(t => t.breakouts.includes(id)
                && this._outputFeedsVoltage(t, voltage)) || null;
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
    // screen, Edison on a Soca 120 feeding an Edison screen, the L21-30 breakout's own tail
    // connector) - so most of the time only a length gets typed. No entry
    // means no cable. A cleared circuit, multi or distro forgets its
    // cables with its label overrides: cables are programming.

    // The connectors a cable can be typed as - the breakout table's own
    // connector names, then every distro face connector's cable (CEE 16A,
    // Schuko, stage pin...), once each, in table order. Ids are the plug
    // chips' face ids (true1 / powercon / edison / l620), so the select's
    // value and the OUTPUTS row's faces name the same thing.
    getPowerCableConnectors() {
        const seen = new Set();
        const out = [];
        const add = (name) => {
            const id = this._cableConnectorId(name);
            if (!id || seen.has(id)) return;
            seen.add(id);
            out.push({ id, name });
        };
        this.getPowerBreakoutTypes().forEach(bt => add(bt.connector));
        const face = typeof this.distroConnectors === 'function' ? this.distroConnectors() : [];
        face.forEach(c => { if (c && c.kind === 'direct') add(c.cable); });
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
    // name, reads the box TYPE's first breakout in the type's OWN order -
    // Edison on a spare Multi 120 (its list leads with Edison), True1 on
    // a spare Multi 208 or L21-30 - never the breakout catalog's order,
    // which would read True1 for every spare. Off any distro the screen's
    // own breakout is the whole answer. A DIRECT output has no breakout:
    // its tail is the outlet itself. Returns a connector id.
    boxTailConnector(d, number, layer) {
        const bts = this.getPowerBreakoutTypes();
        const own = layer ? this.getPowerBreakout(layer) : null;
        if (!d) {
            return this._cableConnectorId((own || bts[0]).connector);
        }
        const type = this.distroBoxType(d, number).type;
        if (type && type.face && type.kind === 'direct' && type.cable) {
            return this._cableConnectorId(type.cable);
        }
        const ids = (type && type.breakouts) || [];
        const first = ids.map(id => bts.find(b => b.id === id)).find(Boolean);
        const pick = (own && ids.includes(own.id))
            ? own
            : first || own || bts[0];
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
    // the canvas tag and the paperwork all print ("10' TRUE1"). On a
    // DIRECT output the cable runs outlet to panel, so `name` is its type
    // (directCableType): "CEE 16A → TRUE1", or "TRUE1" where both ends
    // are TRUE1.
    powerCircuitCable(layer, circuitNum) {
        const store = layer && layer.powerCircuitCables;
        const rec = store && store[circuitNum];
        const ft = rec ? this.parseCableLength(rec.ft) : null;
        if (!rec || ft === null) return null;
        let id = rec.connector && this.cableConnectorName(rec.connector)
            ? rec.connector : null;
        const box = this._circuitBox(layer, circuitNum);
        if (!id) id = this.boxTailConnector(box.d, box.number, layer);
        let name = this.cableConnectorName(id) || '';
        const fbox = box.d && typeof this.faceBox === 'function' ? this.faceBox(box.d, box.number) : null;
        if (fbox && fbox.kind === 'direct') name = this.directCableType(name, layer);
        return {
            ft, connector: rec.connector || null, id, name,
            text: this.cableText(ft, name, 'circuit'),
        };
    }

    // The circuit's cable as the PAPERWORK prints it - the pull sheet, the
    // binder and an exported map: only where the circuit's multi is on a
    // distro. A circuit cable belongs to its feed (owner, 2026-10-17), and
    // every clear forgets it now, but an older file can still hold one on
    // a circuit nothing feeds; it stays stored as the file had it (opening
    // a show changes nothing) and prints nowhere.
    printedCircuitCable(layer, circuitNum) {
        const cable = this.powerCircuitCable(layer, circuitNum);
        if (!cable) return null;
        const box = this._circuitBox(layer, circuitNum);
        return box.idx != null && (layer.powerSocaDistro || {})[box.idx]
            ? cable : null;
    }

    // "10' True1" in a feet show, "3 m True1" in a meters one: the length
    // in the show's unit (app-cable-units.js), then the connector. `kind`
    // ('multi' / 'data' / 'circuit') writes the length as the show's cable
    // stock pieces ("100'+25' True1", cableStockText); without one, or
    // with no stock, the length as typed.
    cableText(ft, name, kind = null) {
        const n = Number(ft);
        const len = (kind && this.cableStockText(n, kind)) || (this.cableUnit() === 'm'
            ? `${this.cableFigure(n)} m` : `${this.cableFigure(n)}'`);
        return `${len}${name ? ` ${name}` : ''}`;
    }

    // Write one circuit's cable. `cable` is { ft, connector } - a blank or
    // zero length forgets the entry (no cable), a null connector follows
    // the box. `record` false is the sheet's quick-fill, which issues ONE
    // updateLayers over every layer it touched itself, so a fill is one
    // undo step the way a length commit is.
    // The length the box sheet's quick fill writes on every circuit: the
    // Power cable preference in the show's unit (10' / 3 m as shipped).
    // Read where the cables are made; a cable already typed is never
    // rewritten by it.
    defaultPowerCableFt() {
        const n = Number(this.cablePref('powerCable'));
        return Number.isFinite(n) && n > 0 ? n : (this.cableUnit() === 'm' ? 3 : 10);
    }

    // A length TYPED as text ("30m", "25 ft") reads the way every typed
    // length does (readTypedLength, 2026-10-22): the other unit converted
    // and said, text that is no length refused and said, the cable that
    // was there kept.
    setCircuitCable(layer, circuitNum, cable, record = true) {
        if (!layer) return false;
        let ft = cable ? Number(cable.ft) : NaN;
        if (cable && typeof cable.ft === 'string') {
            if (this._layerLocked(layer)) {
                const read = this.parseTypedCableLength(cable.ft);
                ft = read.n === null ? NaN : read.n;
            } else {
                const read = this.readTypedLength(cable.ft, 'cable');
                if (!read.ok) return false;
                ft = read.n === null ? NaN : read.n;
            }
        }
        const next = (!Number.isFinite(ft) || ft <= 0) ? null : {
            ft,
            connector: cable.connector && this.cableConnectorName(cable.connector)
                ? cable.connector : null,
        };
        const before = JSON.stringify((layer.powerCircuitCables || {})[circuitNum] || null);
        const changed = JSON.stringify(next) !== before;
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it - when the cable
        // would really change; setting the one it has says nothing.
        if (this._layerLocked(layer)) {
            if (changed) this._showLockedError([layer]);
            return false;
        }
        const store = layer.powerCircuitCables
            || (layer.powerCircuitCables = {});
        if (next) store[circuitNum] = next; else delete store[circuitNum];
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
            // 1.5's further faces (app-distro-systems.js): Harting 16E
            // (rectangular insert, two rows of pins), twist-lock (L5-20 /
            // L6-20: three curved slots), stage pin (three round pins in a
            // row), CEE (round, ground at the top, two pins below) and
            // Schuko (round, two pins, earth clips at the sides).
            + '<symbol id="hw-g-harting" viewBox="0 0 24 24">'
            + '<rect x="3" y="6" width="18" height="12" rx="2"/><g class="pin">'
            + '<circle cx="7" cy="10" r=".9"/><circle cx="10.3" cy="10" r=".9"/>'
            + '<circle cx="13.7" cy="10" r=".9"/><circle cx="17" cy="10" r=".9"/>'
            + '<circle cx="7" cy="14" r=".9"/><circle cx="10.3" cy="14" r=".9"/>'
            + '<circle cx="13.7" cy="14" r=".9"/><circle cx="17" cy="14" r=".9"/>'
            + '</g></symbol>'
            + '<symbol id="hw-g-twist" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/>'
            + '<g stroke-width="2.4" stroke-linecap="round" fill="none">'
            + '<path d="M10.6 5.3 a6.8 6.8 0 0 1 2.8 0"/>'
            + '<path d="M17.6 15.6 a6.8 6.8 0 0 1 -2 2"/>'
            + '<path d="M8.4 17.6 a6.8 6.8 0 0 1 -2 -2"/>'
            + '</g></symbol>'
            + '<symbol id="hw-g-stagepin" viewBox="0 0 24 24">'
            + '<rect x="2.5" y="7" width="19" height="10" rx="2"/><g class="pin">'
            + '<circle cx="7" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.6"/>'
            + '<circle cx="17" cy="12" r="1.3"/></g></symbol>'
            + '<symbol id="hw-g-cee" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/><g class="pin">'
            + '<circle cx="12" cy="6.5" r="1.6"/><circle cx="7.5" cy="15" r="1.3"/>'
            + '<circle cx="16.5" cy="15" r="1.3"/></g></symbol>'
            + '<symbol id="hw-g-schuko" viewBox="0 0 24 24">'
            + '<circle cx="12" cy="12" r="10.3"/><g class="pin">'
            + '<circle cx="8.5" cy="12" r="1.4"/><circle cx="15.5" cy="12" r="1.4"/>'
            + '<rect x="11" y="2.4" width="2" height="2.6" rx=".4"/>'
            + '<rect x="11" y="19" width="2" height="2.6" rx=".4"/></g></symbol>'
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

    // Rollup per distro across every shown screen, plus an 'unassigned' bucket so
    // no load is silently dropped. A distro with legs (three-phase, or
    // split-phase) also gets per-leg loads so you can see whether the
    // service is loaded evenly.
    //
    // THE HEADER FIGURE IS THE WORST LEG (1.5, bug fix 2): `amps`, `pct`
    // and `over` read the most loaded leg against the per-leg rating - the
    // breaker that trips is a leg's, and a whole Socapex on one leg can
    // trip it while the balanced W / (V x 1.73) still reads fine. The
    // balanced figure stays on the record as `balancedAmps`. A distro with
    // one hot reads W / V, as it always did. Since 2026-10-18 `over` reads
    // that leg against `limitA` - the main's continuous limit, 80% of the
    // rating on a US system unless its main is 100% rated - while `pct`
    // stays a share of the rating.
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
            // A hidden screen is left out of every distro and service load
            // (the owner's ruling, 2026-10-23), the way the pull sheet
            // leaves it out (_pullScreens): a distro whose screens are all
            // hidden reads empty.
            if (layer.visible === false) continue;
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
                // A single-hot distro reads its circuits' own amps (audit).
                const own = b.distro ? this._singleHotAmps(b.distro, s.watts, circuitV) : null;
                if (own != null) b.ownAmps = (b.ownAmps || 0) + own;
                // spread this multi's circuits across the legs - per
                // CIRCUIT, through the one authority (distroCircuitLegs): a
                // face box answers from its row and the distro, anything
                // else from the circuit's own voltage, so a 110V multi
                // rides one leg per circuit while a 208V multi on the same
                // service keeps its leg pairs - the mixed case sums
                // correctly because both land in one phasor store.
                const d = b.distro;
                if (d && this.distroLegNames(d).length) {
                    const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                    for (let li = 0; li < s.legs.length; li++) {
                        const info = this.distroCircuitLegs(d, layer, s, li, pos);
                        if (info.scheme) {
                            if (b.scheme && b.scheme.lineToLine !== info.scheme.lineToLine) {
                                b.schemeMixed = true;
                            }
                            b.scheme = info.scheme;
                        }
                        this._bookCircuitOnLegs(b, d, info, s.legs[li].watts, circuitV);
                    }
                }
            }
        }
        const shape = (b) => {
            const d = b.distro;
            const v = d ? d.voltage : 0;
            const names = d ? this.distroLegNames(d) : [];
            const balancedAmps = b.ownAmps != null ? b.ownAmps
                : (v > 0 ? (d.phase === 3 ? b.watts / (v * 1.73) : b.watts / v) : 0);
            const rating = d ? d.ratingA : 0;
            // The LIMIT the busiest leg is held to (2026-10-18): 80% of
            // the rating on a US system unless its main is 100% rated, the
            // rating on an EU one (distroMainLimit). `pct` stays a share
            // of the RATING - the real figure - and `over` reads the limit.
            const rule = d ? this.distroMainLimit(d) : null;
            const limit = rule && rating > 0 ? rule.limitA : 0;
            const past = (a) => limit > 0 && a > limit + 1e-9;
            // Per-leg amps are line-to-NEUTRAL: on a 208V wye that is 120V,
            // which is what each leg actually sees.
            let legs = null, imbalancePct = 0;
            let amps = balancedAmps;
            if (d && names.length) {
                // Per-leg current is the PHASOR magnitude, not watts/voltage:
                // line-to-line loads sit +-30 deg off their legs' L-N
                // reference, so scalar addition would misreport by 13-15%.
                const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
                const w = b.legWatts, ph = b.legPhasor;
                const one = (k) => {
                    const a = mag(ph[k]);
                    return { watts: w[k], amps: a, pct: rating > 0 ? (a / rating) * 100 : 0,
                             over: past(a) };
                };
                legs = { X: one('X'), Y: one('Y'), Z: one('Z') };
                // NEMA-style: max deviation from the AVERAGE (not max-min
                // spread, which reads roughly double and is not what a
                // genset spec or an electrician means by "% imbalance").
                const legAmps = names.map(k => legs[k].amps);
                const avg = legAmps.reduce((t, x) => t + x, 0) / legAmps.length;
                imbalancePct = avg > 0
                    ? (Math.max(...legAmps.map(x => Math.abs(x - avg))) / avg) * 100 : 0;
                legs.names = names.slice();
                legs.labels = names.map(k => this.distroLegLabel(d, k));
                legs.lineToNeutralV = this.distroNeutralVolts(d);
                legs.avgAmps = avg;
                legs.spreadAmps = Math.max(...legAmps) - Math.min(...legAmps);
                legs.worstAmps = Math.max(...legAmps);
                legs.worst = names[legAmps.indexOf(legs.worstAmps)];
                legs.over = past(legs.worstAmps);
                legs.scheme = b.scheme ? b.scheme.name : null;
                legs.schemeId = b.scheme ? b.scheme.id : null;
                // True when this service carries BOTH couplings at once -
                // 110V single-leg circuits beside 208V leg pairs. The
                // scheme fields above then name only the last one summed,
                // so a surface printing the scheme can say "mixed" instead.
                legs.schemeMixed = !!b.schemeMixed;
                legs.pairWatts = b.pairWatts;
                amps = legs.worstAmps;
            }
            return {
                id: d ? d.id : null,
                name: d ? this.distroLabel(d) : 'Unassigned',
                location: (d && d.location) || null,
                ratingA: rating, voltage: v, phase: d ? d.phase : null,
                system: d ? (d.system || null) : null,
                watts: b.watts, amps, balancedAmps,
                worstLeg: legs ? legs.worst : null,
                pct: rating > 0 ? (amps / rating) * 100 : 0,
                limitA: limit, limitPct: rule ? rule.pct : 1,
                main100: !!(rule && rule.main100),
                over: past(amps),
                // Accepted reads amber, never hides: `over` stays true and
                // the figures stay what they are. Kept on the record while
                // the distro carries it, over or not (it clears only when
                // somebody unticks it).
                overloadAccepted: !!(d && d.overloadAccepted),
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
        const store = {
            legWatts: { X: 0, Y: 0, Z: 0 },
            legPhasor: { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 }, Z: { re: 0, im: 0 } },
            pairWatts: {},
        };
        if (!distro) return { X: 0, Y: 0, Z: 0 };
        // a hidden screen loads nothing (getDistroLoads)
        members = (members || []).filter(m => !(m && m.layer && m.layer.visible === false));
        const legacy = this._legacyBoxFeedLegAmps(distro, members);
        if (legacy) return legacy;
        for (const m of (members || [])) {
            if (!m || !m.layer || !m.s) continue;
            const circuitV = parseFloat(m.layer.powerVoltage) || 0;
            const pos = this.socaCircuitPositions(
                m.layer, m.s.soca, m.s.legs.length);
            for (let li = 0; li < m.s.legs.length; li++) {
                const info = this.distroCircuitLegs(distro, m.layer, m.s, li, pos);
                this._bookCircuitOnLegs(store, distro, info, m.s.legs[li].watts, circuitV);
            }
        }
        const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
        const ph = store.legPhasor;
        return { X: mag(ph.X), Y: mag(ph.Y), Z: mag(ph.Z) };
    }

    // Keyed by the multi's stable index, like every other per-multi store, so
    // a home run stays with its multi when the distro renumbers it.
    // `record` mirrors setSocaName's: false for the dock's shared-box
    // write-through, which issues one updateLayers over every member itself.
    setSocaLength(layer, socaIndex, length, record = true) {
        if (!layer) return false;
        const v = String(length == null ? '' : length).trim();
        // A length typed in the show's unit keeps its number ("100ft" is
        // 100, relabelled by number on a unit change); one in the other
        // unit is converted and said ("30m" in a feet show is 98.4 ft);
        // text that is no length is refused, said, and the length that
        // was there stays (2026-10-22, the feeder field's rule).
        const read = this.parseTypedCableLength(v);
        const stored = read.bad ? v : (read.n !== null ? String(read.n) : '');
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it - when the
        // length would really change.
        if (this._layerLocked(layer)) {
            const cur = String((layer.powerSocaLengths || {})[socaIndex] || '').trim();
            if (cur !== stored) this._showLockedError([layer]);
            return false;
        }
        // On a direct output the length is the circuit's cable, not a
        // multi's home run, and the refusal and the undo entry say so.
        const direct = this._socaOnDirectOutput(layer, socaIndex);
        if (!this.readTypedLength(v, direct ? 'cable' : 'home run').ok) return false;
        const store = layer.powerSocaLengths || (layer.powerSocaLengths = {});
        if (stored) store[socaIndex] = stored; else delete store[socaIndex];
        if (record) {
            this.updateLayers([layer], true, direct ? 'Set Direct Cable' : 'Set Multi Home Run');
        }
        return true;
    }

    // Whether multi `socaIndex` of `layer` sits on a distro's DIRECT
    // output (one circuit on its own connector) rather than a multi box.
    _socaOnDirectOutput(layer, socaIndex) {
        const did = ((layer && layer.powerSocaDistro) || {})[socaIndex];
        if (!did || typeof this._isDirectBox !== 'function') return false;
        const rec = this._powerNaming(layer).socas.get(Number(socaIndex));
        return !!(rec && this._isDirectBox(did, rec.number));
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
    _distroPhasingOptions(ph, d = null) {
        // An EU distro can also be wired whole multi on one leg (ruling 4,
        // EU only) - a line-to-neutral ordering like the other two.
        const extra = d && typeof this._distroExtraSchemes === 'function'
            ? this._distroExtraSchemes(d) : [];
        const offered = [...this.powerPhasingSchemes(), ...extra]
            .filter(sc => sc.lineToLine === ph.derived.lineToLine);
        if (ph.explicit && !offered.some(sc => sc.id === ph.scheme.id)) {
            offered.push({ ...ph.scheme,
                name: `${ph.scheme.name}, which does not match the `
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
        // The display label (distroLabel): SR-1 where two distros are SR.
        heading.textContent = this.distroLabel(d) || 'distro';
        wrap.appendChild(heading);

        // Returns updateDistro's answer: null when it refused or asked.
        const patch = (p) => {
            const res = this.updateDistro(d.id, p);
            this._restateNaming();
            return res;
        };
        const cap = (text) => {
            const c = document.createElement('label');
            c.style.fontSize = '10px';
            c.style.color = 'var(--ps-dim, #c0c0c0)';
            c.style.textTransform = 'uppercase';
            c.textContent = text;
            return c;
        };

        // SYSTEM · INPUT · RATING per leg · 100% breakers (1.5,
        // app-distro-systems.js) - the old Voltage and 1φ/3φ selects
        // became the one system pick.
        this._buildDistroSupplySection(d, wrap, patch);
        // SERVICE (2026-10-20, app-services.js): the house power this
        // distro is fed from, once the show has one.
        if (typeof this._buildDistroServiceRow === 'function') {
            this._buildDistroServiceRow(d, wrap);
        }
        // FEEDER (2026-10-21, app-services.js): its length and where it is
        // fed from - the service, or another distro.
        if (typeof this._buildDistroFeederRow === 'function') {
            this._buildDistroFeederRow(d, wrap);
        }

        if (Number(d.phase) === 3) {
            const ph = this.distroPhasingState(d);
            const row2 = document.createElement('div');
            row2.style.display = 'flex';
            row2.style.gap = '6px';
            row2.style.alignItems = 'center';
            row2.style.marginTop = '6px';
            row2.title = 'Phasing. How a multi\'s 6 circuits land on the '
                + 'phase legs, a property of the distro\'s bus and breaker '
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
                `Follow the circuit voltage: ${this.distroSchemeName(d, ph.derived)}`;
            if (!ph.explicit) followOpt.selected = true;
            derive.appendChild(followOpt);
            sel.appendChild(derive);
            const wired = document.createElement('optgroup');
            const sysRec = this.distroSystem(d);
            wired.label = 'Read it off the distro · '
                + (sysRec && sysRec.lnOnly
                    ? `${sysRec.vln} V line-to-neutral`
                    : `${sysRec ? sysRec.vln : Math.round(d.voltage / Math.sqrt(3))} V line-to-neutral, `
                        + `${Math.round(sysRec ? sysRec.vll : d.voltage)} V line-to-line`);
            this._distroPhasingOptions(ph, d).forEach(sc => {
                const opt = document.createElement('option');
                opt.value = sc.id;
                opt.textContent = this.distroSchemeName(d, sc);
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
        // The order the direct outputs take the legs in (ruling 4).
        this._buildDistroDirectPhasing(d, wrap, patch);

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
        beachSelect.title = 'The beach this distro sits on: the dimmer beach, '
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
        // OUTPUT ROWS (1.5): a distro with rows IS its face - the rows
        // say what it hands a screen, so the old type checklist steps
        // aside. A distro with none keeps the checklist (it offers every
        // multi type, as it always has) and the rows section offers the
        // first row and the presets under it.
        const hasFace = !!this.distroFace(d);
        const outs = document.createElement('div');
        outs.className = 'hw-pop-outs';
        if (hasFace) outs.style.display = 'none';
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
        this._buildDistroOutputRows(d, wrap, patch);

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
            // Refused (a locked screen it would repack): nothing went, so
            // its fold keys stay.
            if (!this.removeDistro(d.id)) return;
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
            // A distro's 100% switch or system moves the packing %, which
            // the sidebar's Breaker line and Watts/Circuit read.
            if (this.currentLayer) this.updatePowerCapacityDisplay();
        });
    }

    // Why this screen's plan is empty, when a POWER ERROR is why - the
    // sentence, minus its lead-in, so the soca host ("No circuits — ...")
    // and the label editor ("No circuits to edit — ...") share one story.
    //
    // Live repro: a screen whose one cabinet draws more than a circuit
    // carries has an empty plan - and the soca panel rendered NOTHING,
    // which read as the soca feature being broken. The explanation lived
    // only in the left sidebar and the red wall tint. Since 1.5.4 that is
    // the only power error: Organized cuts a row (or a column) too big for
    // one circuit into several (calculatePowerAssignments), so no pattern
    // change is ever the fix. Every other empty state stays blank: a non-screen layer, a
    // screen with nothing visible on it, a group member counted on its
    // owner, and a custom-routed screen (whose drawn paths supersede the
    // auto error - the same rule updatePowerCapacityDisplay applies to
    // _powerError) have no error to explain.
    _socaPlanEmptyReason(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        if (this.usesCustomCircuits(layer)) return null;
        const err = this.calculatePowerAssignments(layer).error;
        if (!err) return null;
        const cap = this.circuitCapacity(layer);
        const fmt = (w) => `${Math.round(w).toLocaleString('en-US')} W`;
        const held = cap.pct < 1 ? ` (${Math.round(cap.pct * 100)}% of the breaker)` : '';
        const circuit = `a circuit at ${cap.voltage} V / ${cap.breakerA} A carries ${fmt(cap.watts)}${held}`;
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
            // Eligibility follows the screen's voltage (user ruling,
            // 2026-09-22: a 110V / 120V screen runs True1, powerCON or
            // Edison; Edison is out above 120V; the L21-30 box is 3 x
            // 208V). Disabled, not removed, so the list stays stable.
            // No stored choice is exempt: a screen always carries an
            // eligible breakout (normalizePowerBreakout writes one on
            // load and on a voltage change), so there is never paperwork
            // to defend here and the select shows what is in force.
            if (screen) {
                const v = layer.powerVoltage;
                const types = this.getPowerBreakoutTypes();
                Array.from(sel.options).forEach(opt => {
                    const t = types.find(x => x.id === opt.value);
                    const ok = !t || this._breakoutEligible(t, v);
                    opt.disabled = !ok;
                    opt.title = ok ? '' : this._breakoutIneligibleTitle(t, v);
                });
            }
            if (screen && sel !== document.activeElement) {
                sel.value = this.getPowerBreakout(layer).id;
            }
        }
        // The panel input: only where the breakout leaves it to the screen
        // (Edison, L6-20).
        const inp = document.getElementById('power-panel-input');
        const inpRow = document.getElementById('power-panel-input-row');
        if (inp) {
            if (!inp.options.length) {
                this.getPanelInputTypes().forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.id;
                    opt.textContent = t.name;
                    inp.appendChild(opt);
                });
            }
            const choice = !!(screen && this.breakoutHasPanelInputChoice(this.getPowerBreakout(layer)));
            if (inpRow) inpRow.style.display = choice ? 'flex' : 'none';
            if (screen && inp !== document.activeElement) inp.value = this.panelInput(layer).id;
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
            const type = this.getPowerBreakoutTypes().find(t => t.id === sel.value);
            if (!type) return;
            // The select greys what the CURRENT screen's voltage cannot
            // run; the other selected screens have voltages of their own,
            // so each is gated on its own (a 120V peer beside a 208V
            // current screen is not written L21-30). The ineligible ones
            // are skipped and named once; the rest are written.
            // A locked screen keeps its breakout (the owner's ruling,
            // 2026-10-16), named when this would have changed it.
            const all = this._socaPanelTargets(layer);
            this._showLockedError(all.filter(l => this._layerLocked(l)
                && this.getPowerBreakout(l).id !== type.id));
            const list = all.filter(l => !this._layerLocked(l));
            const skipped = list.filter(l => !this._breakoutEligible(type, l.powerVoltage));
            const write = list.filter(l => !skipped.includes(l));
            if (skipped.length) {
                const names = skipped.map(l => `${l.name || l.id} `
                    + `(${parseFloat(l.powerVoltage) || 0}V)`).join(', ');
                const msg = `${type.name} is not available at ${names}, so `
                    + `${skipped.length === 1 ? 'that screen keeps its' : 'those screens keep their'} breakout.`;
                if (typeof this._toast === 'function') this._toast(msg, true, 4000);
                else if (typeof this._dockSay === 'function') this._dockSay(msg);
            }
            if (!write.length) {
                sel.value = this.getPowerBreakout(layer).id;
                return;
            }
            write.forEach(l => { l.powerBreakoutType = type.id; });
            this.updateLayers(write, true, 'Change Power Breakout');
            this.refreshSocaRuns();
        });
        // The panel input, on every selected screen whose breakout leaves
        // it to the screen; a locked one keeps its own and is named.
        const inp = document.getElementById('power-panel-input');
        if (inp) inp.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const want = this.getPanelInputTypes().find(t => t.id === inp.value);
            if (!want) return;
            const all = this._socaPanelTargets(layer)
                .filter(l => this.breakoutHasPanelInputChoice(this.getPowerBreakout(l)));
            this._showLockedError(all.filter(l => this._layerLocked(l) && this.panelInput(l).id !== want.id));
            const write = all.filter(l => !this._layerLocked(l) && this.panelInput(l).id !== want.id);
            if (!write.length) {
                inp.value = this.panelInput(layer).id;
                return;
            }
            write.forEach(l => { l.powerPanelInput = want.id; });
            this.updateLayers(write, true, 'Change Panel Input');
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        const brk = document.getElementById('show-soca-brackets');
        if (brk) brk.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            const all = this._socaPanelTargets(layer);
            // A locked screen keeps its brackets setting, and is named.
            this._showLockedError(all.filter(l => this._layerLocked(l)
                && !!l.showSocaBrackets !== !!brk.checked));
            const list = all.filter(l => !this._layerLocked(l));
            if (!list.length) {
                brk.checked = !!layer.showSocaBrackets;
                return;
            }
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
            // One setting per wall (the owner's ruling, 2026-10-19 - see
            // _splitterWallHost): every selected screen's WALL takes the
            // patch, each member written with the wall's knobs plus the
            // patch so the members agree from here on. A wall is changed
            // whole or not at all: a locked member that the patch would
            // change blocks its whole wall and is named (a locked screen is
            // never changed, and a wall half-changed would read as the
            // first member's setting anyway). With nothing writable the
            // knobs snap back.
            const walls = new Map();
            this._socaPanelTargets(layer).forEach(l => {
                const host = this._splitterWallHost(l) || l;
                if (!walls.has(host.id)) walls.set(host.id, this._splitterWallMembers(l));
            });
            const changes = (l, next) => {
                const cur = this._ownPowerSplitters(l);
                return cur.enabled !== next.enabled || cur.maxWays !== next.maxWays;
            };
            const blocked = [];
            const list = [];
            walls.forEach(members => {
                const wall = this.getPowerSplitters(members[0]);
                const next = { enabled: wall.enabled, maxWays: wall.maxWays, ...patch };
                const locked = members.filter(l => this._layerLocked(l) && changes(l, next));
                if (locked.length) {
                    blocked.push(...locked);
                    return;
                }
                members.forEach(l => {
                    if (!changes(l, next)) return;
                    const cur = this._ownPowerSplitters(l);
                    l.powerSplitters = { ...cur, ...next, manual: cur.manual };
                    list.push(l);
                });
            });
            this._showLockedError(blocked);
            if (!list.length) {
                this.refreshSplitterPanel();
                return;
            }
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
        // A checkbox has no half-typed state to protect, so it always
        // shows the wall's value - focus left on it by the last click must
        // not keep the previous screen's tick when another one is selected.
        en.checked = !!(screen && sp.enabled);
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

    // ---- the amps rule ------------------------------------------------------
    //
    // Matt, 2026-09-15: "a shared circuit shouldn't be able to go past its
    // amps unless in custom mode." A share is a manual merge of runs onto
    // one circuit, and in AUTOMATIC mode (the custom toggle off) the model
    // refuses one whose runs together draw more than the screen's Amperage:
    // the menu item stays on the menu disabled with the reason as its hover
    // title, and the packer never made an over group on its own
    // (_packPowerRuns closes a circuit before the load passes
    // wattsPerCircuit). In CUSTOM mode the user owns the runs, so a share
    // past the amps is honored and the chip and the wall flag OVER - a
    // warning, not a label. The batch verb is the exception in both modes:
    // it never deals a group past the amps at all (the owner's ruling,
    // 2026-10-19 - see "the batch verb" below). A screen leaving custom mode with such a share
    // in place has it un-shared on the way out (toggleCustomPowerMode).
    //
    // The load is the soca plan's own leg figure: each run's cabinets at
    // their Watts per Panel over the screen's Voltage (110 V rides one
    // leg, so amps = watts / voltage on every voltage) - never a formula of
    // this rule's own.

    // Amps per run in the id space the screen reads right now - the run
    // ordinals of an auto screen (a packed circuit's branches, in runId
    // order), the drawn circuit numbers of a custom one. A taken-over
    // circuit is left out: its number is a circuit number, and read as a
    // run ordinal it overwrote the figure of the auto run that shares the
    // digits (_shareRunSegments, which keeps it out of every deal).
    _splitterRunAmps(layer) {
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amps = new Map();
        this.screenCircuits(layer).forEach(c => {
            if (this._isTakenOverCircuit(layer, c.num)) return;
            const ids = c.runIds || [c.num];
            const branches = c.branches || [c.panels];
            let off = 0;
            ids.forEach((id, i) => {
                const panels = branches[i] || [];
                const srcLayers = c.layers
                    ? c.layers.slice(off, off + panels.length) : null;
                off += panels.length;
                const watts = this._circuitWatts(layer, panels, srcLayers);
                amps.set(id, voltage > 0 ? watts / voltage : 0);
            });
        });
        return amps;
    }

    // What one group of runs would draw on one circuit: { amps, cap, over }.
    // `over` is the rule's verdict - past the amps AND not in custom mode -
    // so a caller that only wants the figure reads amps/cap. `runAmps` lets
    // a batch reuse one _splitterRunAmps walk across its groups.
    shareLoad(layer, runIds, runAmps) {
        // 80% of the breaker on a US screen (circuitCapacity).
        const cap = layer ? this.circuitCapacity(layer).amps : 0;
        const byRun = runAmps || this._splitterRunAmps(layer);
        const amps = (runIds || []).reduce((s, id) => s + (byRun.get(id) || 0), 0);
        const over = cap > 0 && amps > cap + 1e-9 && !this.isCustomPower(layer);
        return { amps, cap, over };
    }

    // The runs a refusal names, by the labels the wall prints (the owner,
    // 2026-10-21: a run number is nothing anybody can find on the wall):
    // "S1-1 and S1-2", "S1-1, S1-2 and S1-3". A run that is one leg of a
    // shared circuit is named by its leg, "S1-2 leg 3". `layer` is the
    // screen (or a custom wall's owner) whose id space the runs are in;
    // another member's run arrives as its `${layerId}:${run}` token.
    // Without a layer, the run numbers: "Runs 5 and 6".
    _runListText(runIds, layer) {
        const ids = (runIds || []).slice();
        const list = (xs) => (xs.length <= 1 ? `${xs[0]}`
            : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);
        if (!layer) {
            if (ids.length <= 1) return `Run ${ids[0]}`;
            return `Runs ${list(ids)}`;
        }
        const where = new Map();
        this._wallCircuits(layer).forEach(({ layer: m, c }) => {
            // A taken-over circuit's number is a circuit, not a run.
            if (this._isTakenOverCircuit(m, c.num)) return;
            const legs = c.runIds || [c.num];
            legs.forEach((id, k) => where.set(
                m.id === layer.id ? String(id) : `${m.id}:${id}`,
                { m, c, k, of: legs.length }));
        });
        const names = ids.map(id => {
            const at = where.get(String(id));
            if (!at) return `run ${id}`;
            const name = this.getPowerCircuitLabel(at.m, at.c.num);
            return at.of > 1 ? `${name} leg ${at.k + 1}` : name;
        });
        return list([...new Set(names)]);
    }

    // The refusal for a share of `groups` (arrays of run ids, each one
    // circuit), or null when every group fits or the screen is in custom
    // mode: { runs, amps, cap, text } for the FIRST group past the amps,
    // `text` the reason the menu item wears as its hover title.
    shareRefusal(layer, groups) {
        if (!layer || this.isCustomPower(layer)) return null;
        const runAmps = this._splitterRunAmps(layer);
        for (const g of groups || []) {
            if (!Array.isArray(g) || g.length < 2) continue;
            const load = this.shareLoad(layer, g, runAmps);
            if (!load.over) continue;
            return {
                runs: g.slice(), amps: load.amps, cap: load.cap,
                text: `${this._runListText(g, layer)} together draw `
                    + `${load.amps.toFixed(1)} A on ${this.circuitLimitText(layer)}. `
                    + 'Share past the amps only in custom mode.',
            };
        }
        return null;
    }

    // Custom mode follows the leg model (the owner's ruling 12, 2026-10-19:
    // "the batch button and the share verbs must split a wide custom
    // circuit into its own legs, never join it with neighbours. Joining
    // applies only to single-column circuits"). So Share with next joins
    // two circuits only while each is one run on one column (or row): a
    // circuit already shared - its runs are its legs - or one drawn across
    // several columns never joins a neighbor. `items` are the circuits a
    // share would join, [{ layer, c }] off screenCircuits / _wallCircuits.
    // Returns the reason the Share entry wears, disabled, or null.
    customShareBlock(items) {
        for (const { layer, c } of items || []) {
            if (!layer || !c) continue;
            const name = this.getPowerCircuitLabel(layer, c.num);
            const ways = (c.runIds || []).length;
            if (ways > 1) {
                return `${name} is already a ${ways}fer, and a shared circuit `
                    + 'never joins another. Only a circuit of one run shares.';
            }
            const legs = this._runLegs(layer, c.num);
            const n = legs ? legs.legs.length : 0;
            if (n > 1) {
                return `${name} runs across ${n} ${legs.noun}s, so it splits into `
                    + `its own legs (${n}fer it) and never joins another.`;
            }
        }
        return null;
    }

    // The shared circuits on the screen that the rule would refuse today -
    // empty in custom mode, and on an auto screen whose every share fits.
    // Read by the custom toggle on the way out, once the pattern has
    // flipped back, to see what the switch left past the amps.
    overSharedCircuits(layer) {
        if (!layer || this.isCustomPower(layer)) return [];
        const runAmps = this._splitterRunAmps(layer);
        return this.screenCircuits(layer)
            .filter(c => Array.isArray(c.runIds) && c.runIds.length > 1)
            .map(c => ({ num: c.num, runIds: c.runIds.slice(),
                         load: this.shareLoad(layer, c.runIds, runAmps) }))
            .filter(x => x.load.over);
    }

    // Merge the selected circuits into one manual group. The group is stored
    // as RUN ids: for auto screens the run ordinals the selected circuits
    // currently carry, for custom screens the drawn circuit numbers. Members
    // leave any previous group and lose their split pins. Returns false -
    // and writes nothing - when the amps rule refuses the share.
    mergeSplitterCircuits(layer, circuitNums) {
        if (!layer || !Array.isArray(circuitNums) || circuitNums.length < 2) return false;
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return false;
        // A circuit taken over by hand is a drawing, not a packed run - see
        // _shareRunSegments. It is never dealt into a share.
        if (circuitNums.some(n => this._isTakenOverCircuit(layer, n))) return false;
        // Custom mode joins only single-run circuits (customShareBlock).
        if (this.isCustomPower(layer) && this.customShareBlock(this.screenCircuits(layer)
            .filter(c => circuitNums.includes(c.num)).map(c => ({ layer, c })))) return false;
        const runIds = this._shareRunSegments(layer, circuitNums).flat();
        if (runIds.length < 2) return false;
        if (this.shareRefusal(layer, [runIds])) return false;
        const write = (manual) => {
            const inNew = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !inNew.has(n)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(n => !inNew.has(n));
            manual.merge.push([...runIds].sort((a, b) => a - b));
        };
        // A share that would REPACK a locked screen - one grouped with this
        // screen, whose packing % the group shares - is refused whole, the
        // screen named (owner, 2026-10-23): tried and put back first.
        if (this._repackRefused(() => this._writeSplitterManual(
            layer, write, null, { silent: true }), [layer])) return false;
        this._writeSplitterManual(layer, write);
        return true;
    }

    // Un-merge the selected circuits. Auto runs are additionally PINNED out
    // of packing (one circuit per run) - the pin is what defeats a re-pack;
    // custom circuits just fall back to their drawn numbering.
    // `action` (optional) names the history entry - the batch verb's
    // "Un-share all" passes its own so the step reads as what it was.
    // `opts.silent` (the custom toggle's way out) edits the store and
    // nothing else: the caller owns the history entry and the refresh.
    splitSplitterCircuits(layer, circuitNums, action, opts) {
        if (!layer || !Array.isArray(circuitNums) || !circuitNums.length) return;
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return;
        // A taken-over circuit's runs are its drawing's, not the store's.
        const runIds = this._shareRunSegments(layer, circuitNums).flat();
        if (!runIds.length) return;
        const custom = this.usesCustomCircuits(layer);
        const write = (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(n)) : []))
                .filter(g => g.length >= 2);
            if (!custom) {
                manual.split = [...new Set([...manual.split, ...runIds])]
                    .sort((a, b) => a - b);
            }
        };
        // Nor one that would repack a locked group member (owner,
        // 2026-10-23). A silent call's caller owns the check with its commit.
        if (!(opts && opts.silent) && this._repackRefused(() => this._writeSplitterManual(
            layer, write, null, { silent: true }), [layer])) return;
        this._writeSplitterManual(layer, write, action, opts);
    }

    // ---- the batch verb: "3fer them" ---------------------------------------
    //
    // 2026-08-30, tester + user ruling ("lets go for B and then right
    // click"): sweep a contiguous stretch of runs, right-click, and the
    // menu offers "2fer them / 3fer them / 4fer them" with the group math
    // spelled out. The verb PARTITIONS - consecutive adjacent groups dealt
    // left to right along the wall - so 18 circuits under "3fer them"
    // become six separate 3fers, never one mega-gang. Adjacency is the
    // splitter doctrine (never skip a run).
    //
    // The owner's ruling, 2026-10-19: the batch verb ("3fer Screen" /
    // "2fer Screen", the selection's "3fer them" alike, in automatic AND
    // in custom mode) NEVER builds an OVER gang. A group takes the next run
    // only while their load still fits the circuit - the amps rule's own
    // figure (shareLoad against the screen's Amperage, the limit the OVER
    // flag reads) - and closes at n runs, so the deal is the automatic
    // packer's walk (_packPowerRuns) at maxWays n. Whatever is left over,
    // and a run too big to share with its neighbour, stays on a circuit of
    // its own with no tag. Before this the deal cut by COUNT alone: on a
    // custom wall whose circuits were already three columns each, "3fer
    // Screen" joined them in threes into 45-cabinet circuits that all read
    // OVER, and it pulled the lone last column into a gang. This replaces
    // the 2026-08-30 remainder re-deal (16 @ 3fer as 3,3,3,3,2,2): a
    // remainder is a leftover, the way the automatic wall leaves it.

    // The one walk: `ids` in order cut into groups of at most `size`, a
    // group closing early when `fits` refuses the next run. Pure.
    _dealRunGroups(ids, size, fits) {
        const n = Math.max(2, Number(size) || 2);
        const groups = [];
        let cur = [];
        (ids || []).forEach(id => {
            if (cur.length && (cur.length >= n || (fits && !fits(cur.concat([id]))))) {
                groups.push(cur);
                cur = [];
            }
            cur.push(id);
        });
        if (cur.length) groups.push(cur);
        return groups;
    }

    // Group sizes for `count` runs that all fit together, dealt as Nfers:
    // full groups of n, the remainder a smaller fer, or one plain run.
    batchNferGroups(count, n) {
        const L = Math.max(0, Number(count) || 0);
        return this._dealRunGroups(Array.from({ length: L }, (_, i) => i), n)
            .map(g => g.length);
    }

    // "6 × 3fer", "4 × 4fer + 2fer", "3 × 2fer + 1 plain" - the group math
    // the menu entry carries, so the deal is read before it is taken.
    batchNferLabel(count, n) {
        return this._nferSizesLabel(this.batchNferGroups(count, n));
    }

    _nferSizesLabel(sizes) {
        const tally = new Map();
        (sizes || []).forEach(s => tally.set(s, (tally.get(s) || 0) + 1));
        return [...tally.entries()].sort((a, b) => b[0] - a[0])
            .map(([sz, k]) => sz === 1
                ? `${k} plain`
                : (k === 1 ? `1 × ${sz}fer` : `${k} × ${sz}fer`))
            .join(' + ');
    }

    // Does a group of runs fit one circuit? The amps rule's figure, in
    // either mode - the batch verb never leans on custom mode's licence.
    _shareFits(layer, runIds, runAmps) {
        const load = this.shareLoad(layer, runIds, runAmps);
        return !(load.cap > 0 && load.amps > load.cap + 1e-9);
    }

    // A circuit the user took over by hand on an automatic screen (the
    // Alt take-over, app-run-overrides.js). Never in whole-screen custom,
    // where isRunOverridden is false for every number.
    _isTakenOverCircuit(layer, num) {
        return typeof this.isRunOverridden === 'function'
            && this.isRunOverridden(layer, 'power', num);
    }

    // The runs of `circuitNums` a share may deal, in wall order, as
    // SEGMENTS of neighbours. A taken-over circuit is a drawing, not a
    // packed run: its runs are its own (a 3fer taken over stays a 3fer -
    // _mergeOverrideCircuits) and its number is a CIRCUIT number, not a run
    // ordinal. Dealing that number as a run - which every share verb did
    // through `c.runIds || [c.num]` - ganged whatever auto run happened to
    // carry the same ordinal: on a wall with circuit 2 taken over, "2fer
    // them" over circuits 1-3 wrote run 2 into two groups and left the
    // runs after it plain. So it is left out, and it breaks the line: the
    // runs either side of it are not neighbours.
    _shareRunSegments(layer, circuitNums) {
        const chosen = new Set(circuitNums || []);
        const segs = [[]];
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            if (this._isTakenOverCircuit(layer, c.num)) {
                if (segs[segs.length - 1].length) segs.push([]);
                return;
            }
            (c.runIds || [c.num]).forEach(id => segs[segs.length - 1].push(id));
        });
        return segs.filter(seg => seg.length);
    }

    // The deal itself, pure: the run ids of `circuitNums` in wall order cut
    // into groups that fit (see the ruling above). `over` names the first
    // group refused for its load - for a deal that shares nothing at all,
    // the first pair of neighbours - so a menu entry can say why. Read by
    // the menu (to label the deal before it is taken) and by
    // batchShareCircuits (to make it).
    // `refs` (optional, wall circuits {layerId, num} in wall order) deal a
    // custom group's wall across its members - `layer` is then the wall's
    // owner and another member's runs read as tokens (_wallRunSegments).
    batchShareGroups(layer, circuitNums, n, refs) {
        const size = Math.max(2, Number(n) || 0);
        const runAmps = refs ? this._wallRunAmps(layer) : this._splitterRunAmps(layer);
        const runIds = [];
        const groups = [];
        const splits = [];
        const sizes = [];
        const tooWide = [];
        let over = null;
        const fits = (g) => {
            if (this._shareFits(layer, g, runAmps)) return true;
            if (!over) over = g.slice();
            return false;
        };
        // Custom circuits follow the leg model (the owner's ruling,
        // 2026-10-19, "a wide circuit splits into its own legs"): a run
        // drawn across several columns is split into a run per column on
        // its own circuit when its columns fit the size dealt and its load
        // fits the amps, else left a circuit of its own - and it is never
        // joined with a neighbour, so it breaks the line the single-column
        // runs deal along. Automatic runs are always one column (the
        // packer's), so an automatic deal is the walk it always was.
        const custom = this.isCustomPower(layer);
        const deal = (ids) => {
            if (!ids.length) return;
            const gs = this._dealRunGroups(ids, size, fits);
            groups.push(...gs);
            sizes.push(...gs.map(g => g.length));
        };
        (refs ? this._wallRunSegments(layer, refs)
            : this._shareRunSegments(layer, circuitNums)).forEach(seg => {
            runIds.push(...seg);
            if (!custom) {
                deal(seg);
                return;
            }
            let line = [];
            seg.forEach(id => {
                const legs = this._runLegs(layer, id);
                if (!legs || legs.legs.length < 2) {
                    line.push(id);
                    return;
                }
                deal(line);
                line = [];
                const ways = legs.legs.length;
                if (ways <= size && this._shareFits(layer, [id], runAmps)) {
                    splits.push({ id, ways });
                    sizes.push(ways);
                } else {
                    if (ways > size) tooWide.push({ id, ways, noun: legs.noun });
                    sizes.push(1);
                }
            });
            deal(line);
        });
        return { runIds, groups, over, splits, sizes, tooWide };
    }

    // The legs of custom run `id` in a wall deal (_pathLegs): the wall's
    // owner's run by its number, another member's by its
    // `${layerId}:${run}` token. Null when the run has no drawing.
    _runLegs(owner, id) {
        let layer = owner;
        let num = id;
        if (typeof id === 'string') {
            const [lid, n] = id.split(':').map(v => parseInt(v, 10));
            layer = (this.project.layers || []).find(l => l.id === lid);
            num = n;
        }
        const path = layer && (layer.powerCustomPaths || {})[num];
        return (path && path.length) ? this._pathLegs(layer, path) : null;
    }

    // Deal the chosen circuits' RUNS into Nfer groups, one manual-store
    // write, ONE history entry (`action`). Operates at the run level so an
    // existing gang inside the batch re-deals with everything else. A solo
    // run on an auto screen is split-PINNED so re-packing cannot quietly
    // gang what the deal left plain (custom circuits need no pin - they
    // never auto-pack). Same id-space rules as every manual edit:
    // _writeSplitterManual stamps the space the screen currently reads.
    // Returns false - nothing written - when no two runs fit together.
    // `refs`: a custom group's wall circuits (batchShareGroups); runs of
    // another member are adopted first (_adoptWallCircuits), in the same
    // history entry.
    // `opts.tickSharing` ("2fer / 3fer this screen", the owner's ruling,
    // 2026-10-21): the wall's "Share circuits via splitters" is ticked too,
    // in the same history entry - every member of the wall at once, as the
    // box writes it (_wireScreenPowerKnobs), and refused whole, the locked
    // screens named, when a locked member would change.
    batchShareCircuits(layer, circuitNums, n, action, refs, opts) {
        if (!layer || !(Array.isArray(circuitNums) || Array.isArray(refs))) return false;
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return false;
        const wallWays = this.getPowerSplitters(layer).maxWays;
        const tick = (opts && opts.tickSharing && !this.getPowerSplitters(layer).enabled)
            ? this._splitterWallMembers(layer).filter(m => {
                const own = this._ownPowerSplitters(m);
                return !own.enabled || own.maxWays !== wallWays;
            }) : [];
        if (tick.some(m => this._layerLocked(m))) {
            this._showLockedError(tick.filter(m => this._layerLocked(m)));
            return false;
        }
        // A deal that would REPACK a locked screen (one grouped with this
        // screen) is refused whole, the screen named (owner, 2026-10-23):
        // everything below is written, checked, and put back before the
        // commit when it moves a locked screen's packing %.
        const repacked = this._repackTrial([layer]);
        // An automatic screen with sharing off (the owner's ruling,
        // 2026-10-22): its runs are the ones sharing gives, so sharing goes
        // on first and the whole screen is dealt on those. A deal that
        // shares nothing puts it back as it was.
        let untick = null;
        if (tick.length && !this.usesCustomCircuits(layer) && !refs) {
            untick = this._wallSharingOn(layer);
            circuitNums = this.screenCircuits(layer).map(c => c.num);
        }
        const deal = this.batchShareGroups(layer, circuitNums, n, refs);
        let { runIds, groups, splits } = deal;
        if (!runIds.length || (!groups.some(g => g.length >= 2) && !splits.length)) {
            if (untick) untick();
            return false;
        }
        // A split rewrites its run's path: a run drawn across a locked
        // screen's cabinets is not rewritten (another member's run is
        // checked by its adoption).
        const lockedRuns = new Map();
        splits.forEach(sp => {
            if (typeof sp.id === 'string') return;
            this._runLockedLayers(layer, 'power', sp.id)
                .forEach(l => lockedRuns.set(l.id, l));
        });
        if (lockedRuns.size) {
            if (untick) untick();
            this._showLockedError([...lockedRuns.values()]);
            return false;
        }
        let adopted = null;
        if (refs && this._refsAdopt(layer, refs)) {
            adopted = this._adoptWallCircuits(layer, refs);
            if (!adopted) {
                if (untick) untick();
                return false;
            }
            const num = id => (typeof id === 'string' ? adopted.ids.get(id) : id);
            runIds = runIds.map(num).filter(id => id !== undefined);
            groups = groups.map(g => g.map(num).filter(id => id !== undefined))
                .filter(g => g.length);
            splits = splits.map(sp => ({ ...sp, id: num(sp.id) }))
                .filter(sp => sp.id !== undefined);
        }
        const custom = this.usesCustomCircuits(layer);
        this._writeSplitterManual(layer, (manual) => {
            const hit = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(x => !hit.has(x)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(x => !hit.has(x));
            groups.forEach(g => {
                if (g.length >= 2) {
                    manual.merge.push([...g].sort((a, b) => a - b));
                } else if (!custom) {
                    manual.split.push(...g);
                }
            });
            manual.split = [...new Set(manual.split)].sort((a, b) => a - b);
        }, action, { silent: true });
        // The wide runs, highest number first so a split's renumbering
        // never moves a run still waiting for its own.
        splits.slice().sort((a, b) => b.id - a.id).forEach(sp => {
            const path = (layer.powerCustomPaths || {})[sp.id];
            if (path && path.length) {
                this._splitCustomRun(layer, sp.id, this._pathLegs(layer, path).legs);
            }
        });
        const written = new Map((adopted ? adopted.touched : [layer]).map(l => [l.id, l]));
        tick.forEach(m => {
            const own = this._ownPowerSplitters(m);
            m.powerSplitters = { ...own, enabled: true, maxWays: wallWays,
                                 manual: (m.powerSplitters || {}).manual || own.manual };
            written.set(m.id, m);
        });
        if (repacked()) return false;
        this._commitWallShare([...written.values()], action);
        return true;
    }

    // Turn "Share circuits via splitters" on for every member of `layer`'s
    // wall, at the wall's size, keeping each member's own shares. Returns
    // the undo: each member's stored field put back exactly as it was.
    // Unrecorded; the naming caches are dropped both ways.
    _wallSharingOn(layer) {
        const ways = this.getPowerSplitters(layer).maxWays;
        const saved = this._splitterWallMembers(layer).map(m => ({
            m, had: Object.prototype.hasOwnProperty.call(m, 'powerSplitters'),
            value: m.powerSplitters,
        }));
        saved.forEach(({ m }) => {
            m.powerSplitters = { ...(m.powerSplitters || {}), enabled: true, maxWays: ways };
        });
        this._circuitTailCache = null;
        this._displayNumCache = null;
        return () => {
            saved.forEach(({ m, had, value }) => {
                if (had) m.powerSplitters = value; else delete m.powerSplitters;
            });
            this._circuitTailCache = null;
            this._displayNumCache = null;
        };
    }

    // `fn()` read with the wall's sharing on, then put back - the menu
    // works out "2fer this screen" on the runs it would deal.
    _withWallSharingOn(layer, fn) {
        const undo = this._wallSharingOn(layer);
        try {
            return fn();
        } finally {
            undo();
        }
    }

    // ---- custom mode: a group is ONE wall -----------------------------------
    //
    // The owner's ruling, 2026-10-19: "3 fers etc can fill across screens
    // just like in auto when in a group. remember it's treated as one screen
    // in this way." Auto already packs a matching group as one wall whose
    // first member reports every circuit (getAutoRoutePlan). Custom mode now
    // does the same for EVERY group, mixed panels and wattages included (so
    // a share can cross the seam - auto is unchanged): the group's first
    // custom member owns and numbers every circuit drawn on the wall,
    // whichever member is selected (powerPathOwner - the fill, a click, an
    // arrow key, Tab and the active-circuit controls all draw there), so
    // labels and multis run as one sequence, like auto. The drawing itself
    // is the cross-layer path it always was: steps on a peer carry the
    // peer's layerId (app-cross-layer-paths.js).
    //
    // An old file can still hold runs owned by other members. They open
    // and draw unchanged. A wall action that needs one - a sweep, the batch
    // verb or Share reaching it - ADOPTS it first (_adoptWallCircuits): its
    // runs move into the owner's numbering after the owner's last number,
    // and the label typed on it, its cable and its place on the distro are
    // forgotten the way the dock's Clear circuit forgets them. The adoption
    // and the share are ONE history entry. A locked member is never
    // adopted from - the action is refused whole and the screen named.

    // The custom-power members of `layer`'s wall in the group's own order,
    // the owner first - or null off a group, off custom mode, or when no
    // other member draws custom (a locked member left in auto). Members on
    // another canvas are not on the wall (getPathScopeLayers).
    _customPowerWall(layer) {
        if (!layer || !this.isCustomPower(layer)) return null;
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return null;
        const rank = new Map();
        (this.getGroupMembers(group) || []).forEach((m, i) => {
            if (m) rank.set(m.id, i);
        });
        const at = m => (rank.has(m.id) ? rank.get(m.id) : Number.MAX_SAFE_INTEGER);
        const members = this.getPathScopeLayers(layer)
            .filter(m => m && this.isCustomPower(m))
            .sort((a, b) => at(a) - at(b) || (a.id - b.id));
        return members.length > 1 ? members : null;
    }

    // The layer a custom power drawing on `layer` is written to: the wall's
    // owner on a custom group, the layer itself everywhere else.
    powerPathOwner(layer) {
        const wall = this._customPowerWall(layer);
        return wall ? wall[0] : layer;
    }

    // The wall's circuits in wall order, [{ layer, c }]: the owner's, then
    // each other member's own (an old file's) in group order - the order
    // they take when adopted. Only DRAWN circuits: a member with nothing
    // drawn reports its auto fallback from screenCircuits, which is no
    // circuit at all here. One screen's circuits off a wall.
    _wallCircuits(layer) {
        const wall = this._customPowerWall(layer);
        if (!wall) return this.screenCircuits(layer).map(c => ({ layer, c }));
        const out = [];
        wall.forEach(m => {
            if (!this.usesCustomCircuits(m)) return;
            this.screenCircuits(m).forEach(c => out.push({ layer: m, c }));
        });
        return out;
    }

    // Every wall circuit as a ref, the shape a share across the wall reads.
    _wallRefs(layer) {
        return this._wallCircuits(layer)
            .map(x => ({ layerId: x.layer.id, num: x.c.num }));
    }

    // The run ids of `refs` (wall circuits, in wall order) as segments of
    // neighbours, the _shareRunSegments of a wall: the owner's runs by their
    // own ids, another member's by a `${layerId}:${run}` token until
    // adoption numbers them.
    _wallRunSegments(owner, refs) {
        const byKey = new Map(this._wallCircuits(owner)
            .map(x => [`${x.layer.id}:${x.c.num}`, x]));
        const segs = [[]];
        (refs || []).forEach(r => {
            const x = byKey.get(`${r.layerId}:${r.num}`);
            if (!x) return;
            const mine = x.layer.id === owner.id;
            if (mine && this._isTakenOverCircuit(owner, x.c.num)) {
                if (segs[segs.length - 1].length) segs.push([]);
                return;
            }
            (x.c.runIds || [x.c.num]).forEach(id => segs[segs.length - 1]
                .push(mine ? id : `${x.layer.id}:${id}`));
        });
        return segs.filter(seg => seg.length);
    }

    // _splitterRunAmps across the wall, keyed the way _wallRunSegments
    // names the runs.
    _wallRunAmps(owner) {
        const amps = this._splitterRunAmps(owner);
        (this._customPowerWall(owner) || []).forEach(m => {
            if (m.id === owner.id || !this.usesCustomCircuits(m)) return;
            this._splitterRunAmps(m).forEach((v, id) => amps.set(`${m.id}:${id}`, v));
        });
        return amps;
    }

    // Do `refs` reach past the owner's own circuits?
    _refsAdopt(owner, refs) {
        return (refs || []).some(r => r.layerId !== owner.id);
    }

    // Adopt other members' circuits into the wall's owner. `refs` are
    // circuits of those members, in wall order. Each moves whole: its feed
    // is let go first (_takeCircuitOffMember), then every run's path goes
    // to the owner under the next number after the owner's last, its steps
    // re-pointed (a step on the member names it; a step on the owner drops
    // the pointer, the plain form). Unrecorded - the caller's one entry
    // carries it. Returns { ids: Map(token -> new number), touched } or
    // null - nothing written, the locked screens named - when a member
    // adopted from, or a screen one of its runs crosses, is locked.
    _adoptWallCircuits(owner, refs) {
        const jobs = [];
        const locked = new Map();
        if (this._layerLocked(owner)) locked.set(owner.id, owner);
        (refs || []).forEach(r => {
            if (r.layerId === owner.id) return;
            const m = (this.project.layers || []).find(l => l.id === r.layerId);
            const c = m && this.screenCircuits(m).find(x => x.num === r.num);
            if (!c) return;
            const runs = c.runIds || [c.num];
            if (this._layerLocked(m)) locked.set(m.id, m);
            runs.forEach(n => this._runLockedLayers(m, 'power', n)
                .forEach(l => locked.set(l.id, l)));
            jobs.push({ m, num: c.num, runs });
        });
        if (locked.size) {
            this._showLockedError([...locked.values()]);
            return null;
        }
        const pullBefore = this._pullLiveRowKeys();
        this.ensureCustomPowerState(owner);
        const paths = owner.powerCustomPaths;
        let next = Object.keys(paths)
            .filter(n => (paths[n] || []).length > 0)
            .reduce((mx, n) => Math.max(mx, parseInt(n, 10) || 0), 0) + 1;
        const ids = new Map();
        const touched = new Set([owner]);
        jobs.forEach(({ m, num, runs }) => {
            const taken = this._takeCircuitOffMember(m, num, runs);
            taken.touched.forEach(l => touched.add(l));
            runs.forEach(n => {
                paths[next] = (taken.steps[n] || []).map(e => {
                    const entry = { ...e };
                    const lid = e.layerId === undefined || e.layerId === null
                        ? m.id : e.layerId;
                    if (lid === owner.id) delete entry.layerId;
                    else entry.layerId = lid;
                    return entry;
                });
                ids.set(`${m.id}:${n}`, next);
                next += 1;
            });
        });
        this._dropPullEditsGoneWith(pullBefore);
        this._circuitTailCache = null;
        return { ids, touched: [...touched] };
    }

    // Take circuit `num` (its runs `runs`) off member `m` for good, ahead of
    // its adoption. Its place on the distro goes the way the dock's Clear
    // circuit lets it go (_clearCircuitChip): cut out of a multi of several
    // (_socaReleaseCircuit), then the one-circuit multi it is left as
    // forgets its box, number, tails and home run and its cuts. Its typed
    // labels and cables go, and any share the member stored over its runs
    // dissolves. Then its paths come off, and the multi bookkeeping closes
    // the hole: every stored cut past it steps back one ordinal, and the
    // multi it stood alone in leaves the per-multi stores
    // (_spliceSocaStores). Returns { steps: {run: path}, touched }.
    _takeCircuitOffMember(m, num, runs) {
        const touched = new Set([m]);
        this._circuitTailCache = null;
        let slot = this._powerNaming(m).slots.get(num);
        if (slot) {
            const rec = this._powerNaming(m).socas.get(slot.multi);
            if (rec && rec.circuits.length > 1) {
                const r = this._socaReleaseCircuit(m, slot.multi, num);
                if (r) r.touched.forEach(l => touched.add(l));
                this._circuitTailCache = null;
                slot = this._powerNaming(m).slots.get(num);
            }
        }
        if (slot) {
            const idx = slot.multi;
            for (const field of ['powerSocaNumber', 'powerSocaDistro',
                                 'powerSocaPhasePos', 'powerSocaPhaseOffset',
                                 'powerSocaNames']) {
                if (m[field]) delete m[field][idx];
            }
            this._forgetFeedLengths(m, idx, [num]);
            this._resegmentSocaStores(m, this._socaClearSplitPoints(m, [idx]));
        }
        const list = this.screenCircuits(m);
        const count = list.length;
        const o = list.findIndex(x => x.num === num) + 1;
        const own = o > 0 ? this._socaSegments(m, count)
            .find(seg => seg.start === o && seg.end === o) : null;
        const points = this._socaSplitPoints(m, count);
        if (this._splitterManualSpace(m) === 'custom') {
            const cur = this._ownPowerSplitters(m);
            const hit = new Set(runs);
            m.powerSplitters = { ...cur, manual: {
                merge: cur.manual.merge.filter(g => Array.isArray(g)
                    && !g.some(n => hit.has(parseInt(n, 10)))),
                split: cur.manual.split.filter(n => !hit.has(parseInt(n, 10))),
                space: 'custom',
            } };
        }
        const steps = {};
        runs.forEach(n => {
            steps[n] = (m.powerCustomPaths && m.powerCustomPaths[n]) || [];
            if (m.powerCustomPaths) delete m.powerCustomPaths[n];
            if (m.powerLabelOverrides) delete m.powerLabelOverrides[n];
            this._forgetRunCable(m, 'power', n);
        });
        if (o > 0) {
            if (own) this._spliceSocaStores(m, own.index, -1);
            m.powerSocaSplits = [...new Set(points.filter(p => p !== o)
                .map(p => (p > o ? p - 1 : p)))]
                .filter(p => p >= 1).sort((a, b) => a - b);
        }
        this._circuitTailCache = null;
        return { steps, touched };
    }

    // Share wall circuits `refs` as ONE circuit through a splitter - the
    // single-run Share across the seam: adoption first, then the merge the
    // way mergeSplitterCircuits writes it (custom mode honors a share past
    // the amps and flags it OVER). One history entry.
    mergeWallCircuits(owner, refs) {
        if (!owner || !Array.isArray(refs) || refs.length < 2) return false;
        if (this._lockedRefused(owner)) return false;
        // Only single-run circuits join (customShareBlock), across the seam
        // as on one screen.
        const picked = new Set(refs.map(r => `${r.layerId}:${r.num}`));
        if (this.customShareBlock(this._wallCircuits(owner)
            .filter(x => picked.has(`${x.layer.id}:${x.c.num}`)))) return false;
        const tokens = this._wallRunSegments(owner, refs).flat();
        if (tokens.length < 2) return false;
        // A share that would repack a locked group member is refused whole
        // (owner, 2026-10-23): written, checked, put back before the commit.
        const repacked = this._repackTrial([owner]);
        const adopted = this._adoptWallCircuits(owner, refs);
        if (!adopted) return false;
        const runIds = tokens.map(id => (typeof id === 'string'
            ? adopted.ids.get(id) : id)).filter(id => id !== undefined);
        this._writeSplitterManual(owner, (manual) => {
            const inNew = new Set(runIds);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !inNew.has(n)) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(n => !inNew.has(n));
            manual.merge.push([...runIds].sort((a, b) => a - b));
        }, null, { silent: true });
        if (repacked()) return false;
        this._commitWallShare(adopted.touched, 'Edit Splitter Groups');
        return true;
    }

    // The one PUT and history entry of a share that adopted runs, and the
    // rebuild _writeSplitterManual would have run.
    _commitWallShare(layers, action) {
        this.updateLayers(layers, true, action);
        this._rebuildAfterGesture(() => {
            this.refreshSplitterPanel();
            this.refreshSocaRuns();
            this.refreshDistroPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
    }

    // ---- a wide circuit splits into its own legs ------------------------------
    //
    // The owner's ruling, 2026-10-19: "i am taking 3 columns and 1 port and
    // making it 3fer the single port. across 3 columns. which is how auto
    // has worked this whole time" (a port, to him, is a power circuit). A
    // 2fer or 3fer is ONE circuit split into legs, one run per column - or
    // per row, on a wall cabled across - exactly what the automatic packer
    // builds. So a circuit drawn as ONE run across several columns (a fill
    // made with sharing off, a file from before 1.5.3) can be split, on the
    // same circuit, into a run per column: right-click > "3fer it", or Alt
    // pick it and right-click (app-dock-menus.js _prepareNferItMenu). The
    // ways are the circuit's columns and nothing else: "three columns on
    // one port, the only option available should be a three fer. if 2 then
    // only a 2 fer. if 4 then 4 fer etc." (the owner, 2026-10-19). So the
    // one entry offered is the circuit's own Nfer, never a smaller one, and
    // the splitter size in Power Settings (maxWays) does not cap it - that
    // setting caps what the automatic packer and the batch verb gang. The
    // split is offered only while the circuit's own load fits the amps the
    // OVER flag reads, else it stays on the menu disabled with the reason.
    //
    // How the legs are written depends on what the circuit is:
    //   custom     each leg takes its own drawn number, the circuit's number
    //              for the first and the next ones after it (every circuit
    //              after it steps up, its typed label and cable with it), and
    //              the legs are one manual merge - the shape a sharing custom
    //              fill draws, so it numbers, labels, tags and deals the same.
    //              On a custom group the wall's owner holds it: a circuit an
    //              old file left on another member is adopted first.
    //   taken over the take-over's own shape: the step that heads every leg
    //              after the first is marked `branch: true` (overrideRun).
    //   automatic  taken over already split - the natural path for one
    //              circuit, since the automatic share store only gangs whole
    //              runs and cannot cut one packed with sharing off.
    // Each is ONE history entry ("3fer Circuit") and undoes whole.

    // A path's legs: its steps cut wherever the next step leaves the column
    // (or row) the last one sat in, on the wall's position lattice so a
    // column of one member is never a column of another. The cut is taken
    // both ways and the one that makes FEWER legs is the drawing's
    // direction - a run snaking down three columns is three column legs,
    // not fifteen row legs; a tie goes to the screen's pattern. A step that
    // does not resolve (a hidden cabinet) rides with the leg after it.
    // Returns { noun: 'column' | 'row', legs: [[entry, ...], ...] }.
    _pathLegs(layer, path) {
        const lattice = typeof this._pathLattice === 'function'
            ? this._pathLattice(layer) : null;
        const items = (Array.isArray(path) ? path : []).map(entry => {
            const hit = this.resolvePathEntry(layer, entry);
            return { entry, hit: (hit && !hit.panel.hidden) ? hit : null };
        });
        const key = (h, axis) => {
            if (lattice) {
                return axis === 'col' ? lattice.colOf(h.layer, h.panel)
                    : lattice.rowOf(h.layer, h.panel);
            }
            return `${h.layer.id}:${axis === 'col' ? h.panel.col : h.panel.row}`;
        };
        const cut = (axis) => {
            const legs = [];
            let pending = [];
            let last = null;
            items.forEach(it => {
                if (!it.hit) { pending.push(it); return; }
                const k = key(it.hit, axis);
                if (!legs.length || k !== last) legs.push([]);
                legs[legs.length - 1].push(...pending, it);
                pending = [];
                last = k;
            });
            if (pending.length) {
                if (legs.length) legs[legs.length - 1].push(...pending);
                else legs.push(pending);
            }
            return legs;
        };
        const byCol = cut('col');
        const byRow = cut('row');
        const vertical = byCol.length < byRow.length
            || (byCol.length === byRow.length
                && String(this.autoPowerPattern(layer)).includes('-v'));
        // Every leg is fed from the same end as the first, the way the
        // automatic wall feeds each column run at its head: a run that
        // snaked down one column and up the next becomes legs that all run
        // down. (A leg ran the other way would put its head - where the
        // splitter's tail lands - at the far end of the wall.)
        const along = vertical ? 'row' : 'col';
        const at = (h) => (lattice ? key(h, along) : (vertical ? h.panel.row : h.panel.col));
        const ends = (leg) => {
            const hits = leg.filter(it => it.hit);
            return hits.length > 1 ? at(hits[hits.length - 1].hit) - at(hits[0].hit) : 0;
        };
        const legs = vertical ? byCol : byRow;
        const lead = Math.sign(legs.length ? ends(legs[0]) : 0);
        const out = legs.map(leg => {
            const turn = lead !== 0 && Math.sign(ends(leg)) === -lead;
            return (turn ? leg.slice().reverse() : leg).map(it => it.entry);
        });
        return { noun: vertical ? 'column' : 'row', legs: out };
    }

    // What "Nfer it" would make of circuit `num` of `layer` (the layer whose
    // numbering holds it): { mode, layer, num, path, noun, legs, ways,
    // amps, cap, label, reason } - `reason` set when it cannot be
    // done - or null when the circuit is not there or is already shared
    // (its runs are its legs already; Un-share is that circuit's verb).
    nferCircuitPlan(layer, num) {
        if (!layer || !num) return null;
        const c = this.screenCircuits(layer).find(x => x.num === num);
        if (!c) return null;
        let mode;
        let path;
        if (this.isCustomPower(layer)) {
            if ((c.runIds || []).length > 1) return null;
            mode = 'custom';
            path = (layer.powerCustomPaths || {})[num] || [];
        } else if (this._isTakenOverCircuit(layer, num)) {
            if ((c.runIds || []).length > 1) return null;
            mode = 'override';
            path = (layer.powerCustomPaths || {})[num] || [];
        } else {
            if ((c.runIds || []).length > 1 || (c.branches || []).length > 1) return null;
            mode = 'auto';
            path = this._runSeedHits(layer, 'power', num)
                .map(h => this.makePathEntry(layer, h.layer, h.panel));
        }
        if (!path.length) return null;
        const { noun, legs } = this._pathLegs(layer, path);
        const ways = legs.length;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const watts = this._circuitWatts(layer, c.panels, c.layers);
        const amps = voltage > 0 ? watts / voltage : 0;
        // 80% of the breaker on a US screen (circuitCapacity).
        const cap = this.circuitCapacity(layer).amps;
        const name = this.getPowerCircuitLabel(layer, num);
        const label = ways >= 2 ? `${ways}fer it (${ways} ${noun} runs)` : '2fer / 3fer it';
        let reason = null;
        if (ways < 2) {
            reason = `${name} feeds one ${noun}. A 2fer or 3fer needs a run `
                + `per ${noun} on the circuit.`;
        } else if (cap > 0 && amps > cap + 1e-9) {
            reason = `${name} draws ${amps.toFixed(1)} A on ${this.circuitLimitText(layer)}. `
                + 'That is over the amps, so it cannot be one splitter circuit.';
        }
        return { mode, layer, num, path, noun, legs, ways, amps, cap,
                 label, reason };
    }

    // Split circuit `num` of `layer` into its legs - ONE history entry,
    // `${ways}fer Circuit`. False, nothing written, when the plan refuses or
    // a screen it would change is locked (named).
    nferCircuit(layer, num) {
        const plan = this.nferCircuitPlan(layer, num);
        if (!plan || plan.reason) return false;
        const action = `${plan.ways}fer Circuit`;
        if (plan.mode === 'custom') {
            const owner = this.powerPathOwner(layer);
            const locked = new Map();
            [owner, ...this._runLockedLayers(layer, 'power', num)]
                .forEach(l => { if (l && this._layerLocked(l)) locked.set(l.id, l); });
            if (locked.size) {
                this._showLockedError([...locked.values()]);
                return false;
            }
            // An Nfer that would repack a locked group member is refused
            // whole (owner, 2026-10-23): written, checked, put back first.
            const repacked = this._repackTrial([owner, layer]);
            let at = num;
            let touched = [owner];
            if (owner !== layer) {
                const adopted = this._adoptWallCircuits(owner, [{ layerId: layer.id, num }]);
                if (!adopted) return false;
                at = adopted.ids.get(`${layer.id}:${num}`);
                touched = adopted.touched;
            }
            const legs = this._pathLegs(owner, owner.powerCustomPaths[at]).legs;
            this._splitCustomRun(owner, at, legs);
            if (repacked()) return false;
            this._sweepSelection = null;
            this._commitWallShare(touched, action);
            return true;
        }
        const owner = layer;
        const locked = this._runLockedLayers(owner, 'power', num);
        if (this._layerLocked(owner) && !locked.includes(owner)) locked.unshift(owner);
        if (locked.length) {
            this._showLockedError(locked);
            return false;
        }
        const repacked = this._repackTrial([owner]);
        this.ensureCustomPowerState(owner);
        owner.powerCustomPaths[num] = plan.legs.flatMap((leg, k) => leg.map((e, i) => {
            const entry = { ...e };
            delete entry.branch;
            if (k > 0 && i === 0) entry.branch = true;
            return entry;
        }));
        if (plan.mode === 'auto') {
            const nums = this.getOverrideNums(owner, 'power');
            if (!nums.includes(num)) nums.push(num);
            owner.powerCustomOverrides = nums.sort((a, b) => a - b);
        }
        if (repacked()) return false;
        this._sweepSelection = null;
        this._circuitTailCache = null;
        this.saveState(action);
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        this._rebuildAfterGesture(() => {
            this.updatePowerCapacityDisplay();
            this.refreshSocaRuns();
            this.refreshDistroPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        return true;
    }

    // Write custom run `num`'s legs on `owner` (unrecorded - the caller's
    // one entry carries it): the first leg keeps `num`, the rest take the
    // numbers after it, every drawn number past `num` stepping up to make
    // room (_shiftCustomRuns), and the legs become one manual merge in the
    // custom id space, out of any group `num` sat in.
    _splitCustomRun(owner, num, legs) {
        const by = legs.length - 1;
        if (by < 1) return;
        this.ensureCustomPowerState(owner);
        this._shiftCustomRuns(owner, num, by);
        legs.forEach((leg, k) => {
            owner.powerCustomPaths[num + k] = leg.map(e => {
                const entry = { ...e };
                delete entry.branch;
                return entry;
            });
        });
        const ids = legs.map((_, k) => num + k);
        this._writeSplitterManual(owner, (manual) => {
            const hit = new Set(ids);
            manual.merge = manual.merge
                .map(g => (Array.isArray(g) ? g.filter(n => !hit.has(parseInt(n, 10))) : []))
                .filter(g => g.length >= 2);
            manual.split = manual.split.filter(n => !hit.has(parseInt(n, 10)));
            manual.merge.push(ids);
        }, null, { silent: true });
        this._circuitTailCache = null;
    }

    // Step every drawn custom number past `after` up by `by`, with what is
    // keyed by it: the typed label, the cable, the manual groups (custom id
    // space) and the active index. A circuit's place on the distro is keyed
    // by its multi, not its number, so it stays put. Unrecorded.
    _shiftCustomRuns(owner, after, by) {
        if (!by) return;
        const move = (store) => {
            if (!store) return;
            Object.keys(store).map(n => parseInt(n, 10))
                .filter(n => Number.isFinite(n) && n > after)
                .sort((a, b) => b - a)
                .forEach(n => {
                    store[n + by] = store[n];
                    delete store[n];
                });
        };
        move(owner.powerCustomPaths);
        move(owner.powerLabelOverrides);
        move(owner.powerCircuitCables);
        const step = n => {
            const v = parseInt(n, 10);
            return Number.isFinite(v) && v > after ? v + by : v;
        };
        const raw = owner.powerSplitters;
        if (raw && raw.manual && this._splitterManualSpace(owner) === 'custom') {
            const cur = this._ownPowerSplitters(owner);
            owner.powerSplitters = { ...cur, manual: {
                merge: cur.manual.merge.map(g => (Array.isArray(g) ? g.map(step) : g)),
                split: cur.manual.split.map(step),
                space: 'custom',
            } };
        }
        if ((owner.powerCustomIndex || 1) > after) {
            owner.powerCustomIndex = step(owner.powerCustomIndex);
        }
        this._circuitTailCache = null;
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
        // A taken-over circuit has no runs in the share store - its number
        // is a circuit number, not a run ordinal (_shareRunSegments), and
        // read as one it wiped the auto run of the same ordinal's share.
        const runIds = circuits.length
            ? this._shareRunSegments(layer, circuits).flat() : [];
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

    // ---- typed lengths go with their feed --------------------------------
    //
    // "if i delete a distro or clear a multi etc it needs to delete the
    // lengths for the cable and extensions. same goes for data tab" (owner,
    // 2026-10-17). A multi's home run (powerSocaLengths, by stable index)
    // and its circuits' cables (powerCircuitCables, by circuit number) are
    // the feed's paperwork: a delete, a clear or an unfeed forgets them,
    // so a later feed that takes the same index or circuit number starts
    // blank instead of wearing the old run's length. The screen's own V/H
    // jumpers are not the feed's and are never touched here. No history
    // entry and no lock check - the callers hold both. Keys are deleted,
    // the store objects left behind (see _wipeSocaProgramming).
    _forgetFeedLengths(layer, socaIndex, circuits) {
        if (!layer) return false;
        let changed = false;
        if (socaIndex != null && layer.powerSocaLengths
                && layer.powerSocaLengths[Number(socaIndex)] !== undefined) {
            delete layer.powerSocaLengths[Number(socaIndex)];
            changed = true;
        }
        if (layer.powerCircuitCables) {
            (circuits || []).forEach(num => {
                if (layer.powerCircuitCables[num] === undefined) return;
                delete layer.powerCircuitCables[num];
                changed = true;
            });
        }
        return changed;
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
        const cur = this._ownPowerSplitters(layer);
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

    // The custom toggle's way in (toggleCustomPowerMode): the share groups
    // stored against CUSTOM circuit numbers go with the circuits the toggle
    // wiped, keeping only a group whose every member is a run still drawn
    // (one kept for a locked screen). The caller reads the store's space
    // BEFORE the wipe - the legacy inference reads the drawn paths - and
    // calls only for a custom-space store; groups stored against the auto
    // run ordinals are not circuits and stay, dormant, for the way out.
    // Unrecorded: the toggle's one entry carries it. True when it wrote.
    _wipeCustomSplitterGroups(layer) {
        const raw = layer && layer.powerSplitters;
        if (!raw || !raw.manual) return false;
        const cur = this._ownPowerSplitters(layer);
        const paths = layer.powerCustomPaths || {};
        const drawn = new Set(Object.keys(paths)
            .filter(n => (paths[n] || []).length > 0).map(n => parseInt(n, 10)));
        const merge = cur.manual.merge
            .filter(g => Array.isArray(g) && g.length >= 2
                && g.every(n => drawn.has(parseInt(n, 10))));
        const split = cur.manual.split.filter(n => drawn.has(parseInt(n, 10)));
        if (merge.length === cur.manual.merge.length
                && split.length === cur.manual.split.length
                && cur.manual.space === 'custom') {
            return false;
        }
        layer.powerSplitters = { ...cur, manual: { merge, split, space: 'custom' } };
        return true;
    }

    // `action` names the history entry; the default keeps every existing
    // caller's entry byte-identical. The batch verb passes its own name
    // ('3fer Selection') so one commit is one legible undo step.
    // `opts.silent`: edit and stamp the store, but neither PUT nor snapshot
    // nor refresh - for a caller folding the edit into its own history
    // entry and its own rebuild (the custom toggle's way out).
    _writeSplitterManual(layer, fn, action, opts) {
        const cur = this._ownPowerSplitters(layer);
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
        if (opts && opts.silent) return;
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

    // Normalized read - the raw field may be absent or partial. The
    // packing knobs (`enabled`, `maxWays`) are the WALL's: on a grouped
    // screen they are read off the group's first member, whichever member
    // asks (the owner's ruling, 2026-10-19 - see _splitterWallHost); the
    // manual store is always the layer's own. Writers that keep a layer's
    // own knobs read _ownPowerSplitters instead, so a manual edit never
    // stamps the wall's knobs onto a member that disagreed in an old file.
    getPowerSplitters(layer) {
        const own = this._ownPowerSplitters(layer);
        const host = this._splitterWallHost(layer);
        if (!host || host === layer) return own;
        const wall = this._ownPowerSplitters(host);
        return { ...own, enabled: wall.enabled, maxWays: wall.maxWays };
    }

    // ---- one splitter setting per wall ---------------------------------------
    //
    // The owner's ruling, 2026-10-19: in a group, "Share circuits via
    // splitters" - the enabled flag AND the splitter size - is ONE setting
    // for the whole wall, in auto and in custom: "when grouped they should
    // be sharing that setting". The box writes every member at once
    // (_wireScreenPowerKnobs) and the sidebar shows the wall's value
    // whichever member is selected. Members that disagree - files saved
    // before this, where each member carried its own flag - read the
    // group's FIRST member's setting (the member an automatic wall's walk
    // already packs by, and the custom wall's owner on any ordinary group);
    // nothing is rewritten until the setting is touched. Before this the
    // box showed and wrote the selected member's own flag while the custom
    // fill read the wall owner's, so a member showing "on" filled one wide
    // run per circuit.

    // The screen whose knobs a grouped layer reads: its group's first screen
    // member, or the layer itself off a group.
    _splitterWallHost(layer) {
        if (!layer || !layer.group_id || typeof this.getGroupOfLayer !== 'function') {
            return layer;
        }
        const group = this.getGroupOfLayer(layer);
        if (!group) return layer;
        const first = (this.getGroupMembers(group) || [])
            .find(m => m && (m.type || 'screen') === 'screen');
        return first || layer;
    }

    // Every screen that shares `layer`'s splitter setting: its group's
    // screen members, or the layer alone.
    _splitterWallMembers(layer) {
        if (!layer) return [];
        const group = (layer.group_id && typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return [layer];
        const members = (this.getGroupMembers(group) || [])
            .filter(m => m && (m.type || 'screen') === 'screen');
        return members.length ? members : [layer];
    }

    // The layer's OWN stored knobs and manual store, normalized.
    _ownPowerSplitters(layer) {
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
    // reached (the amps rule keeps an auto screen's stored groups within
    // the amps - a custom screen's, or a file's older group past them, the
    // soca `over` convention flags); a split-pinned run is its own circuit
    // and a boundary.
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

    // ---- an older show's automatic shares (1.5.4) ---------------------------
    //
    // Before 1.5.4 a US circuit packed to 100% of its breaker; it packs to
    // 80% now (circuitCapacity). Automatic 2fers and 3fers are never
    // stored: the walk above derives them from that figure on every read,
    // so an older show whose 2fers fit at 100% but not at 80% opened with
    // them re-split - more circuits, more multis, a different pull sheet -
    // and nothing said. The owner's ruling (2026-10-30): keep them as they
    // were saved and flag the ones past the limit OVER; the user shares
    // them again.
    //
    // KEPT: opening a show saved before KEPT_SHARES_BEFORE
    // (olderShowKeepsShares, read off the file's app_version before the
    // load stamps it) runs keepOlderShowShares. Every screen whose
    // automatic walk shares circuits is packed the way the old build
    // packed it, at 100% of the breaker, and where that differs from
    // today's pack the old circuits are written on the screen as
    //   powerSplitters.kept = { groups: [[1, 2], [3, 4], ..., [11]], sig }
    // - every run ordinal in walk order, one array per circuit - and the
    // walk emits exactly those circuits (_packKeptRuns). A screen whose
    // 2fers still fit, and every manual share, gets nothing: it packs the
    // same either way. A locked screen is kept like any other, so it opens
    // unchanged too. Hand-drawn (custom) circuits never come here.
    //
    // OVER: nothing new. A kept circuit past the screen's figure is an
    // ordinary shared circuit past its amps: the Nfer pill on the wall and
    // on the binder's map reads "2fer · OVER" in red (canvas-power
    // _nferGangs), the tray's chip fills red past its figure, and the
    // distro's breaker check counts it.
    //
    // CLEARED: `sig` is the screen as it was packed - pattern, voltage,
    // breaker, splitter size, manual shares, and every run's cabinets and
    // watts (_keptShareSig). The keep holds only while the screen still
    // reads that. Any change that repacks the screen (its cabinets, watts,
    // power settings, pattern, splitters, a share made or removed) leaves
    // it stale: the walk packs normally, and the next layer commit drops
    // it (pruneStaleKeptShares). A write through the manual store drops it
    // at once (_ownPowerSplitters carries no `kept`), and so does turning
    // the splitters off or changing their size. Undo puts it back with the
    // state it belongs to. A change that only moves the packing % (a
    // distro's system, 100% rated breakers) is no repack: a kept screen's
    // circuits are what they were.

    // Was `project` saved by a build that packed US circuits to 100%?
    olderShowKeepsShares(project = this.project) {
        return this.projectPredatesVersion(KEPT_SHARES_BEFORE, project);
    }

    // The kept circuits the walk takes for `layer`'s `count` runs, or null:
    // no keep, a stale one (`sigOf()` is the screen now), or one that is
    // not every run once in walk order. Null while keepOlderShowShares or
    // the prune is probing, so the probe sees the screen's own pack.
    _keptShares(layer, count, sigOf) {
        if (this._keptShareProbe) return null;
        const kept = layer && layer.powerSplitters && layer.powerSplitters.kept;
        if (!kept || !Array.isArray(kept.groups) || typeof kept.sig !== 'string') return null;
        const flat = kept.groups.flat();
        if (flat.length !== count || flat.some((n, i) => n !== i + 1)
                || kept.groups.some(g => !Array.isArray(g) || !g.length)) return null;
        return kept.sig === sigOf() ? kept.groups : null;
    }

    // The kept circuits as the walk's result (_packPowerRuns' shape).
    _packKeptRuns(runs, groups) {
        const circuits = [], counts = [], runIds = [];
        groups.forEach(g => {
            circuits.push(g.flatMap(n => runs[n - 1].panels));
            counts.push(g.map(n => runs[n - 1].panels.length));
            runIds.push(g.slice());
        });
        return { circuits, runs: counts, runIds };
    }

    // What a keep is held to: the screen's automatic walk as it reads now,
    // everything but the packing % (FNV-1a over the description, short
    // enough to save). `runs` are the walk's runs, `manual` the applied
    // manual shares, `layerOfPanel` the screen each cabinet sits on (a
    // group packed as one wall walks its members' cabinets).
    _keptShareSig(layer, pattern, runs, maxWays, manual, layerOfPanel) {
        const text = JSON.stringify([
            pattern, parseFloat(layer.powerVoltage) || 0, parseFloat(layer.powerAmperage) || 0,
            maxWays, manual.merge, manual.split,
            runs.map(r => [(Number(r.load) || 0).toFixed(3), r.panels.map(p => {
                const on = layerOfPanel(p);
                return `${on ? on.id : ''}:${p.row}:${p.col}`;
            }).join(',')]),
        ]);
        let h = 0x811c9dc5;
        for (let i = 0; i < text.length; i += 1) {
            h ^= text.charCodeAt(i);
            h = Math.imul(h, 0x01000193) >>> 0;
        }
        return `${runs.length}:${h.toString(16).padStart(8, '0')}`;
    }

    // `layer`'s automatic splitter walk without its keep: { sig, runIds },
    // at `pct` of the breaker (null: the screen's own figure). Null when
    // the screen does not walk shares (custom, splitters off, a group
    // member packed on its owner) or a row or column cannot fit.
    _keptShareWalk(layer, pct) {
        const outerCap = this._capacityProbe;
        const outerProbe = this._keptShareProbe;
        const seen = new Map();
        this._keptShareProbe = seen;
        if (pct) this._capacityProbe = { pct };
        try {
            this.calculatePowerAssignments(layer);
        } finally {
            this._capacityProbe = outerCap;
            this._keptShareProbe = outerProbe;
        }
        return seen.get(layer) || null;
    }

    _dropKeptShares(layer) {
        const raw = layer && layer.powerSplitters;
        if (!raw || !Object.prototype.hasOwnProperty.call(raw, 'kept')) return false;
        const rest = { ...raw };
        delete rest.kept;
        layer.powerSplitters = rest;
        return true;
    }

    // Opening an older show (olderShowKeepsShares): keep every screen's
    // automatic shares as the old build packed them, at 100% of the
    // breaker, where they differ from today's pack - that is, where a 2fer
    // or 3fer that fit at 100% is past the limit now. Worked out afresh
    // from the screens as they are (a keep already on one is redone), so
    // a load may run it before and after the server's copy comes back.
    // Unrecorded: the load's own history reset takes it. Returns the
    // screens kept.
    keepOlderShowShares() {
        const screens = ((this.project && this.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen');
        screens.forEach(l => this._dropKeptShares(l));
        this._circuitTailCache = null;
        const kept = [];
        screens.forEach(layer => {
            const then = this._keptShareWalk(layer, 1);
            if (!then || !then.runIds.some(g => g.length > 1)) return;
            // A panel that cannot fit now has no circuits to keep:
            // the screen says it cannot fit (_bCannotFit).
            const now = this._keptShareWalk(layer, null);
            if (!now || JSON.stringify(now.runIds) === JSON.stringify(then.runIds)) return;
            layer.powerSplitters = { ...(layer.powerSplitters || {}),
                kept: { groups: then.runIds.map(g => g.slice()), sig: then.sig } };
            kept.push(layer);
        });
        this._circuitTailCache = null;
        if (kept.length) {
            sendClientLog('older_show_shares_kept', {
                layers: kept.map(l => ({ id: l.id, circuits: l.powerSplitters.kept.groups.length })),
            });
        }
        return kept;
    }

    // Drop every keep the screen no longer reads (a repack made it stale).
    // Run by the layer commits (updateLayers / updateLayer) before they
    // store anything; returns the screens it wrote.
    pruneStaleKeptShares() {
        const out = [];
        ((this.project && this.project.layers) || []).forEach(layer => {
            const kept = layer && layer.powerSplitters && layer.powerSplitters.kept;
            if (!kept) return;
            // the screen's walk as it reads now, its run count included
            const now = this._keptShareWalk(layer, null);
            const holds = !!now && now.sig === kept.sig && Array.isArray(kept.groups)
                && kept.groups.flat().length === now.runIds.flat().length;
            if (holds) return;
            if (this._dropKeptShares(layer)) out.push(layer);
        });
        if (out.length) this._circuitTailCache = null;
        return out;
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

    // The pattern the AUTOMATIC walk routes by. A screen in custom mode with
    // nothing drawn yet falls back to auto routing (screenCircuits), and it
    // routes by the pattern it had when custom mode went on - the toggle
    // keeps it as lastPowerFlowPattern - not by the word 'custom' read as
    // a pattern string (no '-h', no 'l-': organized column units dealt
    // right to left, which re-routed a wall the moment the toggle went on).
    autoPowerPattern(layer) {
        const raw = (layer && layer.powerFlowPattern) || 'tl-h';
        if (raw !== 'custom') return raw;
        const last = layer.lastPowerFlowPattern;
        return (last && last !== 'custom') ? last : 'tl-h';
    }

    // The screen's Circuit numbers switch (powerNumberOrder), the owner's
    // ruling of 2026-11-01, worded and read the way the data side's Port
    // numbers switch is (portNumberOrderOf). It decides only how the
    // circuits Organized cuts from a row (or a column) too big for one
    // circuit are NUMBERED; the circuits themselves never move:
    //   Across  along each row first: circuit 1 is row 1's first run,
    //           circuit 2 its next, and row 2 starts after the last;
    //   Down    down the stacks: circuit 1 is row 1's first run, circuit 2
    //           row 2's first, and when the stack ends the next one starts
    //           back at the first row.
    // For a vertical-first pattern the lines are columns and the two words
    // keep their meaning on the wall: Across numbers along the top band of
    // runs first, Down numbers down each column first. The pattern's start
    // corner decides where the first line and the first run are, so a
    // bottom-start pattern stacks up from the bottom and a right-start one
    // steps its stacks right to left. Missing (every show before the
    // switch) is Across; a screen whose lines all fit has nothing to
    // renumber either way, so no older show moves.
    powerNumberOrder(layer) {
        return (layer && layer.powerNumberOrder === 'down') ? 'down' : 'across';
    }

    // Does the Circuit numbers switch do anything on this screen? Only on
    // an automatic Organized screen whose walk cuts a row (or a column)
    // into several circuits; a group member routed on its owner reads the
    // owner's walk.
    powerNumberOrderApplies(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return false;
        const plan = (typeof this.getAutoRoutePlan === 'function')
            ? this.getAutoRoutePlan(layer, 'power') : null;
        const walker = (plan && !plan.isOwner && plan.owner) ? plan.owner : layer;
        if (walker.powerMaximize || !walker.powerOrganized) return false;
        if (this.usesCustomCircuits(walker)) return false;
        return !!this.calculatePowerAssignments(walker).cut;
    }

    // The Circuit numbers row under Organized: shown only where it does
    // something (powerNumberOrderApplies), its lit button the screen's
    // order as it reads now (powerNumberOrder - unset reads Across).
    syncPowerNumberOrder(layer = this.currentLayer) {
        const row = document.getElementById('power-number-order-row');
        if (!row) return;
        const on = !!layer && this.powerNumberOrderApplies(layer);
        row.style.display = on ? '' : 'none';
        if (!on) return;
        const order = this.powerNumberOrder(layer);
        row.querySelectorAll('[data-order]').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-order') === order);
        });
    }

    // A unit's cabinets less the blank ones - a blank draws no power and
    // rides no circuit ("they don't exist", 2026-10-18).
    _livePanels(panels) {
        return (panels || []).filter(p => p && !p.blank);
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

        const panelWatts = parseFloat(layer.panelWatts) || 0;
        // 80% of the breaker on a US screen (circuitCapacity).
        const wattsPerCircuit = this.circuitCapacityWatts(layer);
        const pattern = this.autoPowerPattern(layer);
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
        // A BLANK cabinet draws no power - "they don't exist" (owner,
        // 2026-10-18) - so the walk leaves it out the way it leaves out a
        // hidden one, and no circuit, distro load or label charges it: the
        // same figure the sidebar, group and project totals already read.
        const visibleOrdered = unclaimed(plan
            ? plan.ordered.filter(c => !c.panel.hidden && !c.panel.blank).map(c => c.panel)
            : this.getOrderedPanelsByPattern(layer, pattern, false).filter(p => !p.blank));
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

            // The units (rows, or columns for a vertical-first pattern) in
            // walk order, each with its load. A unit too big for one circuit
            // is CUT along its own walk (the owner's ruling, 2026-11-01):
            // each circuit takes as many whole cabinets as fit, the next
            // starts where it stopped in the same unit, and the last takes
            // the remainder - a 90-wide row of 150 W cabinets on a 3,328 W
            // circuit is 22, 22, 22, 22 and 2. A piece never wraps onto the
            // next unit. A one-unit circuit walks from the pattern's start
            // side, the way every one-row circuit always has, so the pieces
            // of every cut row line up in stacks. Rows that fit are the
            // walk they always were. One cabinet over a circuit is the
            // PANEL WATTS error above.
            const walkOf = (indices) => unclaimed(this._livePanels(this.getOrganizedPanelsForUnits(
                layer, pattern, isHorizontalFirst, indices, false, plan)));
            const units = [];
            for (const idx of unitIndices) {
                const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? rowOfPanel(p) === idx : colOfPanel(p) === idx));
                if (unitPanels.length === 0) continue;
                const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                const unit = { idx, load: unitLoad, pieces: null };
                if (unitLoad > wattsPerCircuit) {
                    unit.pieces = [];
                    let piece = null;
                    walkOf([idx]).forEach(p => {
                        const w = loadOf(p);
                        if (piece && piece.load + w > wattsPerCircuit) piece = null;
                        if (!piece) unit.pieces.push(piece = { panels: [], load: 0 });
                        piece.panels.push(p);
                        piece.load += w;
                    });
                }
                units.push(unit);
            }
            const anyCut = units.some(u => u.pieces);
            // STACKS. Read across the lines instead of along them: inside
            // every unbroken stretch of cut units, each unit's first piece,
            // then each unit's second, and so on (the data side's
            // _stackSplitRuns, the same rule); anything that is not a piece
            // of a cut unit ends the stretch and keeps its place. `items`
            // come in walk order and each carries `at` = [unit, piece] and
            // `piece` (true for a piece of a cut unit). Returns the indices.
            const stackOrder = (items) => {
                const out = [];
                let block = [];
                const flushBlock = () => {
                    block.sort((a, b) => (items[a].at[1] - items[b].at[1])
                        || (items[a].at[0] - items[b].at[0]) || (a - b));
                    out.push(...block);
                    block = [];
                };
                items.forEach((item, i) => {
                    if (item.piece) { block.push(i); return; }
                    flushBlock();
                    out.push(i);
                });
                flushBlock();
                return out;
            };
            // THE NUMBERS (the Circuit numbers switch, powerNumberOrder):
            // along the walk, or down the stacks - Down on a
            // horizontal-first pattern, Across on a vertical-first one,
            // where the lines are columns. `items` in walk order; returns
            // the indices in circuit-number order. Only the numbers move.
            const numberByStacks = isHorizontalFirst
                ? this.powerNumberOrder(layer) === 'down'
                : this.powerNumberOrder(layer) === 'across';
            const numberOrder = (items) => (numberByStacks
                ? stackOrder(items) : items.map((_, i) => i));

            // Splitter packing: one RUN per unit (row/column) - each branch
            // is its own short daisy fed at its head, the physical truth of
            // a wall cabled top-down - then _packPowerRuns gangs consecutive
            // runs onto shared circuits within maxWays and capacity. Off by
            // default; the default path below is byte-identical to the
            // pre-splitter code.
            //
            // A cut unit's pieces are runs like any other (the owner's
            // ruling, 2026-11-01: the short leftover is a circuit like any
            // other and shares). The runs of a cut stretch are read by
            // stacks (stackOrder), so the leftovers at the far end sit next
            // to each other and share the way neighbouring runs always
            // have. That reading is the packing's own and never moves with
            // the Circuit numbers switch: renumbering never changes which
            // cabinets share a circuit. An uncut screen reads one run per
            // unit in walk order, exactly as before.
            const splitters = this.getPowerSplitters(layer);
            if (splitters.enabled) {
                const walkRuns = [];
                units.forEach((u, k) => {
                    if (u.pieces) {
                        u.pieces.forEach((p, j) => walkRuns.push({ ...p, at: [k, j], piece: true }));
                    } else {
                        walkRuns.push({ panels: walkOf([u.idx]), load: u.load, at: [k, 0], piece: false });
                    }
                });
                const runs = anyCut ? stackOrder(walkRuns).map(i => walkRuns[i]) : walkRuns;
                const manual = this.appliedSplitterGroups(
                    layer, runs.map((_, i) => i + 1));
                // An older show's automatic shares, kept as it was saved
                // (_keptShares): while the screen is the one they were
                // packed on, the walk takes them as they are, over the
                // limit or not, and the OVER flags read them.
                const sigOf = () => this._keptShareSig(
                    layer, pattern, runs, splitters.maxWays, manual, layerOfPanel);
                const kept = this._keptShares(layer, runs.length, sigOf);
                const packed = kept ? this._packKeptRuns(runs, kept) : this._packPowerRuns(
                    runs, wattsPerCircuit, splitters.maxWays, manual);
                if (this._keptShareProbe) {
                    this._keptShareProbe.set(layer, { sig: sigOf(), runIds: packed.runIds });
                }
                const result = { circuits: packed.circuits, runs: packed.runs,
                    runIds: packed.runIds, error: null };
                if (anyCut) {
                    // Each circuit sits where its first run does; put them
                    // in walk order, then number them.
                    const heads = packed.runIds.map(ids => runs[ids[0] - 1]);
                    const walk = heads.map((_, i) => i).sort((a, b) =>
                        (heads[a].at[0] - heads[b].at[0]) || (heads[a].at[1] - heads[b].at[1]) || (a - b));
                    const order = numberOrder(walk.map(i => heads[i])).map(n => walk[n]);
                    result.circuits = order.map(i => packed.circuits[i]);
                    result.runs = order.map(i => packed.runs[i]);
                    result.runIds = order.map(i => packed.runIds[i]);
                    result.cut = true;
                }
                return this._mergeOverrideCircuits(layer, withOwners(result));
            }

            // Whole units that fit share one circuit while they fit, as
            // always; a cut unit closes the circuit in hand, and each of its
            // pieces is a circuit of its own (a piece joining the next unit
            // would wrap onto the next row).
            const items = [];
            let current = { unitIndices: [], load: 0, at: null };
            const flush = () => {
                if (current.unitIndices.length > 0) {
                    circuits.push(walkOf(current.unitIndices));
                    items.push({ at: current.at, piece: false });
                }
                current = { unitIndices: [], load: 0, at: null };
            };
            units.forEach((u, k) => {
                if (u.pieces) {
                    flush();
                    u.pieces.forEach((piece, j) => {
                        circuits.push(piece.panels);
                        items.push({ at: [k, j], piece: true });
                    });
                    return;
                }
                if (current.load > 0 && current.load + u.load > wattsPerCircuit) flush();
                if (current.unitIndices.length === 0) current.at = [k, 0];
                current.unitIndices.push(u.idx);
                current.load += u.load;
            });
            flush();
            if (anyCut) {
                const walked = circuits.splice(0, circuits.length);
                numberOrder(items).forEach(i => circuits.push(walked[i]));
                return this._mergeOverrideCircuits(layer, withOwners({ circuits, error: null, cut: true }));
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
        // A taken-over circuit that was SHARED keeps its runs (the owner's
        // ruling, 2026-10-19): the take-over seeds a `branch` mark on the
        // head of every run after the first (overrideRun), so a 3fer of
        // three columns stays three runs on the one circuit and draws, tags
        // and counts as a 3fer. Its run ids are its own - "2.1", "2.2" -
        // never the automatic run ordinals, which are a different space
        // (and the share verbs leave a taken-over circuit alone anyway,
        // _shareRunSegments). One run is the plain circuit it always was.
        let branched = false;
        overrides.forEach(o => {
            const counts = this._overrideRunCounts(o.hits);
            const shared = counts.length > 1;
            if (shared) branched = true;
            rows.push({
                num: o.num,
                panels: o.hits.map(h => h.panel),
                layers: (result.layers || crossing)
                    ? o.hits.map(h => h.layer) : null,
                runs: (result.runs || shared) ? counts : null,
                runIds: shared ? counts.map((_, k) => `${o.num}.${k + 1}`) : null,
            });
        });
        rows.sort((a, b) => a.num - b.num);
        const out = { circuits: rows.map(r => r.panels), error: null, nums: rows.map(r => r.num) };
        if (result.cut) out.cut = true;
        if (result.layers || crossing) {
            // Owner rows for the auto circuits that never had any: every
            // cabinet is this layer's own. _powerOwnerIdRows nulls those rows
            // back out downstream, so the tinting fast path stays untouched.
            out.layers = rows.map(r => r.layers || (r.panels || []).map(() => layer));
        }
        if (result.runs || branched) {
            out.runs = rows.map(r => r.runs || [(r.panels || []).length]);
            out.runIds = rows.map(r => r.runIds);
        }
        return out;
    }

    // The run sizes of one taken-over circuit, from its resolved hits: a
    // new run starts at every hit carrying the `branch` mark. [n] for a
    // plain circuit.
    _overrideRunCounts(hits) {
        const counts = [];
        (hits || []).forEach((h, i) => {
            if (i === 0 || h.branch) counts.push(0);
            counts[counts.length - 1] += 1;
        });
        return counts.length ? counts : [0];
    }

}

for (const k of Object.getOwnPropertyNames(_Power.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Power.prototype, k));
    }
}
