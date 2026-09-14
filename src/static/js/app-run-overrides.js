// app-run-overrides: per-run overrides for LEDRasterApp - a single port or
// circuit number the user has taken over on an otherwise automatic screen.
// Owns the override lists, the hover / click / context-menu entry points,
// opening and closing an override for redrawing, and returning it to auto.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _RunOverrides {

    // ── Per-run overrides (data ports and power circuits) ─────────────────
    //
    // Custom used to be all or nothing: the WHOLE screen goes to
    // flowPattern 'custom' and every port is hand-drawn. The motivating wall
    // is the other way round - auto-cable the whole thing, then redraw the
    // ONE run that jumped somewhere a cable cannot go. So an override is a
    // single port (or circuit) number the user has taken over:
    //
    //     customPortOverrides / powerCustomOverrides   the numbers taken over,
    //                           per member and NEVER group-shared - a redrawn
    //                           port is one physical cable on one screen
    //     customPortPaths / powerCustomPaths            still where the drawn
    //                           path lives, keyed by that number - the same
    //                           dict, the same step shape ({row, col
    //                           [, layerId]}), the same editing tools
    //
    // Whole-screen custom keeps its exact semantics: isCustomFlow /
    // isCustomPower still mean the pattern, and a screen in that mode has no
    // overrides (the paths are ALL hand-drawn there). Overrides only exist
    // against an automatic pattern, where the engines lay the auto walk over
    // every cabinet an override has not claimed and skip the overridden
    // numbers - see calculatePortAssignments / calculatePowerAssignments.

    // The override numbers of one layer, validated: ints >= 1, deduped, in
    // ascending order. Tolerant of anything a stale file could hold.
    getOverrideNums(layer, kind) {
        const key = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        const arr = layer && layer[key];
        if (!Array.isArray(arr)) return [];
        const out = [];
        arr.forEach(v => {
            const n = parseInt(v, 10);
            if (Number.isFinite(n) && n >= 1 && !out.includes(n)) out.push(n);
        });
        return out.sort((a, b) => a - b);
    }

    // Overrides are meaningful only against an automatic pattern - in
    // whole-screen custom every path is hand-drawn already and the array is
    // ignored outright, so flipping to custom and back cannot double-apply.
    hasRunOverrides(layer, kind) {
        if (!layer) return false;
        if (kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer)) return false;
        return this.getOverrideNums(layer, kind).length > 0;
    }

    isRunOverridden(layer, kind, num) {
        if (!layer) return false;
        if (kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer)) return false;
        return this.getOverrideNums(layer, kind).includes(num);
    }

    // Is ONE overridden run open for redrawing right now? Session state, not
    // layer state: it must not travel through undo snapshots, saves or
    // presets. It only reads true while the layer still carries the override
    // AND the active index still points at it - undo can revert either, and
    // a click that then wrote into some other number would be corruption,
    // not editing.
    _isOverrideEditing(layer, kind) {
        const s = this._overrideEditing;
        if (!s || !layer || s.layerId !== layer.id || s.kind !== kind) return false;
        if (!this.isRunOverridden(layer, kind, s.num)) return false;
        const idx = kind === 'power'
            ? (layer.powerCustomIndex || 1) : (layer.customPortIndex || 1);
        return idx === s.num;
    }

    // Every cabinet claimed by an override path anywhere in this layer's path
    // scope, as the panel OBJECTS the engines walk. The scope matters: an
    // override drawn from the group's first member can run onto a peer, and
    // the peer's own walk must not feed those cabinets twice. Members in
    // whole-screen custom contribute nothing here - their paths are not
    // overrides and their screens are not on the automatic map at all.
    _overrideClaims(layer, kind) {
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const scope = (typeof this.getPathScopeLayers === 'function')
            ? this.getPathScopeLayers(layer) : [layer];
        const claimed = new Set();
        scope.forEach(member => {
            if (!member) return;
            if (kind === 'power' ? this.isCustomPower(member) : this.isCustomFlow(member)) return;
            const nums = this.getOverrideNums(member, kind);
            if (!nums.length) return;
            const paths = member[pathsKey] || {};
            nums.forEach(n => {
                this.getResolvedPathPanels(member, paths[n] || []).forEach(hit => {
                    claimed.add(hit.panel);
                });
            });
        });
        return claimed;
    }

    // This layer's own overridden runs, resolved and ready to merge into an
    // assignment: [{num, hits: [{layer, panel}...]}] in ascending number
    // order, empty paths dropped (a number with nothing drawn reserves its
    // number but is not a cable).
    _ownOverrideRuns(layer, kind) {
        if (!this.hasRunOverrides(layer, kind)) return [];
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const paths = layer[pathsKey] || {};
        return this.getOverrideNums(layer, kind)
            .map(num => ({ num, hits: this.getResolvedPathPanels(layer, paths[num] || []) }))
            .filter(o => o.hits.length > 0);
    }

    // The run under a canvas point in the CURRENT view, or null: the port in
    // Data Flow, the circuit in Power, auto or hand-drawn alike. Owner is the
    // layer whose numbering space the run lives in - for a crossing group
    // that is the member that owns the walk, not the member under the cursor.
    runAtPoint(worldX, worldY) {
        const r = window.canvasRenderer;
        if (!r || !this.project) return null;
        const view = r.viewMode;
        if (view !== 'data-flow' && view !== 'power') return null;
        const hit = r.getPanelAt(worldX, worldY);
        if (!hit) return null;
        if (view === 'data-flow') {
            // The dock's panel -> run map is THE lookup for this already;
            // cached per microtask because hover asks on every mouse move.
            if (!this._hoverDataMapCache) {
                this._hoverDataMapCache = this._dockBuildDataMap();
                Promise.resolve().then(() => { this._hoverDataMapCache = null; });
            }
            const run = this._hoverDataMapCache.get(hit.panel);
            if (!run) return null;
            const owner = (this.project.layers || []).find(l => l.id === run.ownerId);
            return owner ? { kind: 'data', layer: owner, num: run.portNum } : null;
        }
        const under = (this.project.layers || []).find(l => l.id === hit.layerId);
        if (!under) return null;
        if (!(under._powerPanelCircuitMap instanceof Map)
                && typeof r.preparePowerLayerRenderData === 'function') {
            r.preparePowerLayerRenderData(under);
        }
        const circuit = (typeof r._powerCircuitForPanel === 'function')
            ? r._powerCircuitForPanel(under, hit.panel) : null;
        return circuit
            ? { kind: 'power', layer: circuit.owner, num: circuit.circuitNum } : null;
    }

    // The held-modifier highlight: while Alt is down, the run under the
    // cursor lights up with the same underlay the dock drag paints - the
    // user's own words for the gesture ("when we hold a certain key it will
    // highlight whatever your mouse goes over"). Re-rendered only when the
    // lit run actually changes.
    updateOverrideHover(active, worldX, worldY) {
        let next = null;
        if (active) {
            const run = this.runAtPoint(worldX, worldY);
            if (run) next = { layerId: run.layer.id, num: run.num, kind: run.kind };
        }
        const prev = this._overrideHover;
        const same = (!prev && !next) || (prev && next
            && prev.layerId === next.layerId && prev.num === next.num
            && prev.kind === next.kind);
        if (same) return;
        this._overrideHover = next;
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Alt+click on a run. Three cases, none of them a mode the user has to
    // know about first:
    //   * the owner is in whole-screen custom - every run is already
    //     editable, so the click just makes that run the active one;
    //   * the run is already overridden - reopen it for editing;
    //   * an automatic run - take it over (overrideRun below).
    // Returns true when the click was consumed.
    handleOverrideClick(worldX, worldY) {
        const run = this.runAtPoint(worldX, worldY);
        if (!run) return false;
        const { kind, layer: owner, num } = run;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        if (wholeCustom) {
            this._activateRunForEdit(owner, kind, num, null);
            return true;
        }
        if (this.isRunOverridden(owner, kind, num)) {
            this.beginOverrideEdit(owner, kind, num);
            return true;
        }
        this.overrideRun(owner, kind, num);
        return true;
    }

    // Take one automatic run over: seed its path with the cabinets it carries
    // RIGHT NOW, in the order the walk feeds them - so nothing on the canvas
    // moves at the moment of entry - reserve its number, and open it for
    // editing. ONE undo step for the whole transition.
    overrideRun(owner, kind, num) {
        if (!owner || !num) return;
        const hits = this._runSeedHits(owner, kind, num);
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        if (kind === 'power') this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        owner[pathsKey][num] = hits.map(h => this.makePathEntry(owner, h.layer, h.panel));
        const nums = this.getOverrideNums(owner, kind);
        if (!nums.includes(num)) nums.push(num);
        owner[ovrKey] = nums.sort((a, b) => a - b);
        this._activateRunForEdit(owner, kind, num,
            kind === 'power' ? 'Override Circuit' : 'Override Port');
        if (typeof sendClientLog === 'function') {
            sendClientLog('override_run', {
                kind, layerId: owner.id, num, seeded: hits.length,
            });
        }
    }

    // Reopen an existing override for editing. The only model change is the
    // active index, so the undo entry is the one that change has always had.
    beginOverrideEdit(owner, kind, num) {
        if (!this.isRunOverridden(owner, kind, num)) return;
        this._activateRunForEdit(owner, kind, num, null);
    }

    // The shared tail of every entry path: select the owner, point the active
    // index at the run, raise the session editing state, persist, refresh.
    // `undoLabel` names the ONE undo step when the caller already mutated the
    // model (overrideRun); null means only the index may have moved and the
    // step is the ordinary index change - or nothing at all.
    _activateRunForEdit(owner, kind, num, undoLabel) {
        if (this.currentLayer !== owner && typeof this.selectLayer === 'function') {
            this.selectLayer(owner);
        }
        const idxKey = kind === 'power' ? 'powerCustomIndex' : 'customPortIndex';
        const idxChanged = (owner[idxKey] || 1) !== num;
        owner[idxKey] = num;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        this._overrideEditing = wholeCustom
            ? null : { layerId: owner.id, kind, num };
        const label = undoLabel || (idxChanged
            ? (kind === 'power' ? 'Power Custom Circuit Change' : 'Custom Port Change')
            : null);
        if (label) {
            this.saveState(label);
            this.saveClientSideProperties();
            this.updateLayers(this._pathPersistLayers(owner));
        }
        if (kind === 'power') {
            this.updatePowerCapacityDisplay();
            this.updateCustomPowerUI();
        } else {
            this.updatePortCapacityDisplay();
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Close the open override edit. No model change - the override and its
    // path stay exactly as drawn - so no undo entry.
    endOverrideEdit() {
        if (!this._overrideEditing) return;
        const wasPower = this._overrideEditing.kind === 'power';
        this._overrideEditing = null;
        if (wasPower) {
            if (this.powerCustomSelection) this.powerCustomSelection.clear();
            this.updateCustomPowerUI();
        } else {
            if (this.customSelection) this.customSelection.clear();
            this.updateCustomFlowUI();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Hand one overridden run back to the automatic walk: the override and
    // its drawn path go, and the engine re-flows the freed cabinets on the
    // next pass. One named undo step puts the drawing back.
    returnRunToAuto(owner, kind, num) {
        if (!owner || !this.isRunOverridden(owner, kind, num)) return;
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        owner[ovrKey] = this.getOverrideNums(owner, kind).filter(n => n !== num);
        if (owner[pathsKey]) delete owner[pathsKey][num];
        const s = this._overrideEditing;
        if (s && s.layerId === owner.id && s.kind === kind && s.num === num) {
            this._overrideEditing = null;
        }
        this.saveState(kind === 'power' ? 'Return Circuit To Auto' : 'Return Port To Auto');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        if (kind === 'power') {
            this.updatePowerCapacityDisplay();
            this.updateCustomPowerUI();
        } else {
            this.updatePortCapacityDisplay();
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
        }
        if (typeof sendClientLog === 'function') {
            sendClientLog('return_run_to_auto', { kind, layerId: owner.id, num });
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The cabinets one run carries right now, in feed order, resolved to
    // {layer, panel} so a crossing run seeds with the peer's real cabinets.
    _runSeedHits(owner, kind, num) {
        const scope = (typeof this.getPathScopeLayers === 'function')
            ? this.getPathScopeLayers(owner) : [owner];
        const byId = new Map(scope.map(l => [l.id, l]));
        const resolve = (layerId) => (layerId === undefined || layerId === null)
            ? owner : (byId.get(layerId) || owner);
        if (kind === 'data') {
            return (this.calculatePortAssignments(owner) || [])
                .filter(item => item && item.port === num && item.panel && !item.panel.hidden)
                .map(item => ({ layer: resolve(item.layerId), panel: item.panel }));
        }
        const res = this.calculatePowerAssignments(owner) || { circuits: [] };
        const circuits = res.circuits || [];
        const idx = res.nums ? res.nums.indexOf(num) : num - 1;
        if (idx < 0 || !circuits[idx]) return [];
        const owners = res.layers ? res.layers[idx] : null;
        return circuits[idx].map((panel, i) => ({
            layer: (owners && owners[i]) ? owners[i] : owner,
            panel,
        }));
    }

    // The context-menu offers for a right-click on a run: "Redraw ..." on any
    // run the gesture could take over, plus "... back to auto" only where an
    // override actually exists to drop - the house rule that a menu only
    // shows what applies. Null anywhere the cursor is not on a run, and in
    // whole-screen custom, where redrawing is the whole mode already.
    _prepareOverrideMenu(x, y) {
        const r = window.canvasRenderer;
        if (!r || !r.canvas) return null;
        if (r.viewMode !== 'data-flow' && r.viewMode !== 'power') return null;
        const rect = r.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            return null;
        }
        const worldY = ((y - rect.top) - r.panY) / r.zoom;
        const worldX = r._unmirrorWorldX(((x - rect.left) - r.panX) / r.zoom, worldY);
        const run = this.runAtPoint(worldX, worldY);
        if (!run) return null;
        const { kind, layer: owner, num } = run;
        if (kind === 'power' ? this.isCustomPower(owner) : this.isCustomFlow(owner)) {
            return null;
        }
        const noun = kind === 'power'
            ? `circuit ${this.getPowerCircuitLabel(owner, num)}`
            : `port ${this.getPortLabelText(owner, num, 'primary')}`;
        const overridden = this.isRunOverridden(owner, kind, num);
        return {
            redraw: {
                label: `Redraw ${noun}`,
                title: overridden
                    ? 'Reopen this hand-drawn run: click cabinets to extend it, '
                        + 'arrow keys to walk it, Esc when done.'
                    : 'Take this run over from automatic routing. It keeps the '
                        + 'cabinets it has now; click cabinets to redraw it, and '
                        + 'the rest of the screen re-flows around it.',
                run: () => (overridden
                    ? this.beginOverrideEdit(owner, kind, num)
                    : this.overrideRun(owner, kind, num)),
            },
            backToAuto: overridden ? {
                label: `${noun.charAt(0).toUpperCase()}${noun.slice(1)} back to auto`,
                title: 'Drop the hand-drawn run; automatic routing takes its '
                    + 'cabinets back. Undo puts the drawing back.',
                run: () => this.returnRunToAuto(owner, kind, num),
            } : null,
        };
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
}

for (const k of Object.getOwnPropertyNames(_RunOverrides.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_RunOverrides.prototype, k));
    }
}
