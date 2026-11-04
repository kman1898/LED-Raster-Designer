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
                    // A legacy blank on a data override is no cabinet at
                    // all: not claimed, not carried (see isPanelDataDark).
                    if (kind !== 'power' && hit.panel.blank) return;
                    claimed.add(hit.panel);
                });
            });
        });
        // Several ports being redrawn as one (app-merge-runs.js): the
        // cabinets they freed stay out of the walk until the redraw ends.
        if (kind !== 'power' && typeof this._mergeHeldPanels === 'function') {
            this._mergeHeldPanels(scope).forEach(p => claimed.add(p));
        }
        // One port open for redrawing holds its cabinets the same way.
        if (kind !== 'power') this._overrideHeldPanels(scope).forEach(p => claimed.add(p));
        // And one circuit open for redrawing (_powerHoldLive).
        else this._powerHeldPanels(scope).forEach(p => claimed.add(p));
        return claimed;
    }

    // ── The cabinets a power redraw holds (1.6.0 QA, beta.5) ──────────────
    //
    // The owner, 2026-11-03: "clicking an earlier cabinet of the run being
    // drawn cuts it back", on power as on data ("i redrew ports so s1-1 is
    // a twofer and s1-2 is a single column, so column 4-5 should become a
    // twofer"). A circuit taken over on an AUTOMATIC screen holds the
    // cabinets it carried when the redraw opened, the way a data port does
    // (_overrideHoldLive): while it is open the walk leaves them alone, so
    // a cabinet cut off the path (a click on an earlier step, Clear
    // Circuit) stays free for this circuit to take again. Without it the
    // walk took the cut cabinets straight back as the next circuit, and
    // every click on them was refused as "already wired". When the redraw
    // ends the held cabinets left undrawn go back to the walk, and the
    // automatic circuits after it slide left onto them.
    //
    // Session state, never saved, and alive only while that very editing
    // state is: undo, a reset or another circuit picked up ends it.
    _powerHoldLive() {
        const h = this._powerHeld;
        if (!h) return null;
        const ed = this._overrideEditing;
        const owner = ed && h.editing === ed && this.project
            ? (this.project.layers || []).find(l => l.id === ed.layerId) : null;
        if (!owner || ed.kind !== 'power' || !this._isOverrideEditing(owner, 'power')) {
            if (!this._canvasMeasuring) this._powerHeld = null;
            return null;
        }
        return h;
    }

    _powerHeldPanels(scope) {
        const h = this._powerHoldLive();
        if (!h || h.keys.size === 0) return [];
        if (!(scope || []).some(m => m && m.id === h.layerId)) return [];
        const out = [];
        scope.forEach(m => (m && m.panels || []).forEach(p => {
            if (h.keys.has(this.getScopedPanelKey(m.id, p))) out.push(p);
        }));
        return out;
    }

    // Raise the hold for circuit `num` of `owner`, just opened for
    // redrawing: the cabinets on its path now.
    // `prev` is the hold live before the open: the same circuit reopened
    // keeps what it held, so a cabinet cut off stays free.
    _beginPowerHold(owner, num, prev) {
        const keys = new Set();
        ((owner.powerCustomPaths || {})[num] || []).forEach(e => {
            if (e) keys.add(this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e));
        });
        if (prev && prev.layerId === owner.id && prev.num === num) prev.keys.forEach(k => keys.add(k));
        this._powerHeld = { editing: this._overrideEditing, layerId: owner.id, num, keys };
    }

    // The hold `h` has ended (its redraw closed): the cabinets it held and
    // left undrawn are the walk's again. Says where they went.
    _endPowerHold(h) {
        if (!h || !this.project) return;
        if (h === this._powerHeld) this._powerHeld = null;
        const owner = (this.project.layers || []).find(l => l.id === h.layerId);
        if (!owner) return;
        const drawn = new Set();
        this.getOverrideNums(owner, 'power').forEach(n => ((owner.powerCustomPaths || {})[n] || [])
            .forEach(e => { if (e) drawn.add(this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e)); }));
        const left = [...h.keys].filter(k => !drawn.has(k));
        // A circuit let go whole (_dropUnchangedRedraw) says so itself.
        if (!left.length || this.isCustomPower(owner)
                || !this.isRunOverridden(owner, 'power', h.num)) return;
        const want = new Set(left);
        const res = this.calculatePowerAssignments(owner) || {};
        const nums = new Set();
        (res.circuits || []).forEach((panels, i) => (panels || []).forEach((p, j) => {
            const at = (res.layers && res.layers[i] && res.layers[i][j]) || owner;
            if (want.has(this.getScopedPanelKey(at.id, p))) {
                nums.add(Array.isArray(res.nums) ? res.nums[i] : i + 1);
            }
        }));
        sendClientLog('power_hold_released', { layerId: owner.id, num: h.num, left: left.length });
        const n = left.length;
        const cabs = `${n} cabinet${n === 1 ? '' : 's'} left over`;
        const labels = [...nums].sort((a, b) => a - b).map(x => this.getPowerCircuitLabel(owner, x));
        const note = labels.length
            ? `${cabs} went to circuit${labels.length === 1 ? '' : 's'} ${labels.join(', ')}.`
            : `${cabs} went back to the automatic circuits.`;
        if (typeof this._toast === 'function') this._toast(note, false, 6000);
    }

    // ── The cabinets a single redraw holds (QA, 1.6.0) ────────────────────
    //
    // A data port taken over on an AUTOMATIC screen keeps the cabinets it
    // carried when the redraw opened, the way "Redraw ports as one" holds
    // the ports it freed (_mergeHeldPanels): while the redraw is open the
    // walk leaves them alone, so a cabinet cut off the path (a click on an
    // earlier step, Clear Port) stays free for this port to take again in
    // a new order. Without the hold the walk took such a cabinet straight
    // back, every click on it was refused as wired, and the redraw had
    // nowhere to go. When the redraw ends, a held cabinet left undrawn goes
    // back to the walk (_endOverrideHold says where).
    //
    // Session state like _overrideEditing, never saved: it lives only while
    // that very editing state does (`editing` is the same object), so undo,
    // a reset or anything that drops the edit drops the hold with it.
    _overrideHoldLive() {
        const h = this._overrideHeld;
        if (!h) return null;
        const ed = this._overrideEditing;
        const owner = ed && h.editing === ed && this.project
            ? (this.project.layers || []).find(l => l.id === ed.layerId) : null;
        if (!owner || ed.kind !== 'data' || !this._isOverrideEditing(owner, 'data')) {
            // A canvas processor's edit guard measuring the base state
            // writes the base's fields onto the layer for a moment
            // (_canvasSpansWith): the hold does not apply to that state,
            // and it does not end there either.
            if (!this._canvasMeasuring) this._overrideHeld = null;
            return null;
        }
        return h;
    }

    // The held cabinets among `scope` (the walking screen's path scope), as
    // panel objects.
    _overrideHeldPanels(scope) {
        const h = this._overrideHoldLive();
        if (!h || h.keys.size === 0) return [];
        if (!(scope || []).some(m => m && m.id === h.layerId)) return [];
        const out = [];
        scope.forEach(m => (m && m.panels || []).forEach(p => {
            if (h.keys.has(this.getScopedPanelKey(m.id, p))) out.push(p);
        }));
        return out;
    }

    // The scoped keys of the cabinets on `owner`'s overridden paths, every
    // one: a held cabinet drawn onto any of them (Tab steps between them
    // while the redraw is open) is drawn.
    _overridePathKeys(owner) {
        const paths = (owner && owner.customPortPaths) || {};
        const out = new Set();
        this.getOverrideNums(owner, 'data').forEach(n => (paths[n] || []).forEach(e => {
            if (e) out.add(this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e));
        }));
        return out;
    }

    // Held, not drawn: the cabinets still to draw, on `layer` (for the
    // canvas's dashed ring, with the merge redraw's).
    overrideFreedPanels(layer) {
        const h = this._overrideHoldLive();
        if (!h || !layer || h.keys.size === 0) return [];
        const owner = (this.project.layers || []).find(l => l.id === h.layerId);
        const drawn = this._overridePathKeys(owner);
        return (layer.panels || []).filter(p => {
            const k = this.getScopedPanelKey(layer.id, p);
            return h.keys.has(k) && !drawn.has(k);
        });
    }

    // Raise the hold for the data port `num` of `owner`, just opened for
    // redrawing: the cabinets on its path now. `prev` is the hold that was
    // live before the open (read before the editing state was replaced): on
    // the same screen it carries on, so a cabinet cut off one port stays
    // free while another is picked up; on another screen it ends.
    _beginOverrideHold(owner, num, prev) {
        const keys = new Set();
        const paths = owner.customPortPaths || {};
        (paths[num] || []).forEach(e => {
            if (e) keys.add(this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e));
        });
        // `before`: which cabinets rode which port when the redraw opened,
        // for the names and cards to follow should a number be handed back
        // at the end (_repairEmptyOverrides). A hold carried on keeps the
        // reading its redraw opened with.
        let before = null;
        if (prev && prev.layerId === owner.id) {
            prev.keys.forEach(k => keys.add(k));
            before = prev.before || null;
        } else if (prev) this._endOverrideHold(prev);
        if (!before && typeof this._portCabinetKeys === 'function') {
            before = this._portCabinetKeys(owner);
        }
        this._overrideHeld = { editing: this._overrideEditing, layerId: owner.id, keys, before };
    }

    // Let the hold go (the redraw ended, or one on another screen opened).
    // The cabinets left undrawn go back to the walk; the toast names the
    // ports they went to, so the change is not silent.
    _endOverrideHold(h = this._overrideHeld) {
        if (!h) return;
        if (h === this._overrideHeld) this._overrideHeld = null;
        const owner = (this.project && this.project.layers || []).find(l => l.id === h.layerId);
        if (!owner) return;
        const drawn = this._overridePathKeys(owner);
        const left = [...h.keys].filter(k => !drawn.has(k));
        // A number the redraw left with nothing on it goes back to the walk
        // (no phantom ports, _repairEmptyOverrides).
        const repaired = typeof this._repairEmptyOverrides === 'function'
            ? this._repairEmptyOverrides(owner, h.before) : '';
        if (!left.length && !repaired) return;
        sendClientLog('override_hold_released', { layerId: owner.id, left: left.length });
        this.updatePortCapacityDisplay();
        if (typeof this.updateUI === 'function') this.updateUI();
        const note = [repaired, left.length ? this._leftoverPortsNote(owner, left) : '']
            .filter(Boolean).join(' ');
        if (note && typeof this._toast === 'function') this._toast(note, false, 6000);
    }

    // "2 cabinets left over went to ports P15-P16." - where the
    // cabinets `keys` (scoped keys) of `owner`'s path scope sit now that
    // nothing holds them: on an automatic screen the walk took them, on a
    // custom one they are unwired.
    _leftoverPortsNote(owner, keys) {
        const n = (keys || []).length;
        if (!owner || !n) return '';
        const cabs = `${n} cabinet${n === 1 ? '' : 's'} left over`;
        if (this.isCustomFlow(owner)) {
            return `${cabs} ${n === 1 ? 'is' : 'are'} unwired now.`;
        }
        const want = new Set(keys);
        const map = this._dockBuildDataMap();
        const nums = new Set();
        this.getPathScopeLayers(owner).forEach(m => (m && m.panels || []).forEach(p => {
            if (!want.has(this.getScopedPanelKey(m.id, p))) return;
            const run = map.get(p);
            if (run && run.ownerId === owner.id) nums.add(run.portNum);
        }));
        if (!nums.size) return `${cabs} went back to the automatic ports.`;
        const list = [...nums];
        return `${cabs} went to ${list.length === 1 ? 'port' : 'ports'} ${this._portNumbersText(list)}.`;
    }

    // This layer's own overridden runs, resolved and ready to merge into an
    // assignment: [{num, hits: [{layer, panel}...]}] in ascending number
    // order, empty paths dropped (a number with nothing drawn reserves its
    // number but is not a cable).
    // A power hit carries `branch: true` where its step starts a new run
    // of a shared circuit (see overrideRun); a mark on a step that does not
    // resolve (a hidden cabinet) passes to the next step that does, so the
    // run still starts where the drawing says.
    _ownOverrideRuns(layer, kind) {
        if (!this.hasRunOverrides(layer, kind)) return [];
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const paths = layer[pathsKey] || {};
        return this.getOverrideNums(layer, kind)
            .map(num => ({ num, hits: kind === 'power'
                ? this._resolvedRunHits(layer, paths[num] || [])
                : this.getResolvedPathPanels(layer, paths[num] || [])
                    .filter(hit => !hit.panel.blank) }))
            .filter(o => o.hits.length > 0);
    }

    // getResolvedPathPanels, carrying each step's run-head mark.
    _resolvedRunHits(layer, path) {
        const out = [];
        let pending = false;
        (Array.isArray(path) ? path : []).forEach(entry => {
            if (entry && entry.branch) pending = true;
            const hit = this.resolvePathEntry(layer, entry);
            if (!hit || hit.panel.hidden) return;
            out.push(pending && out.length ? { ...hit, branch: true } : hit);
            pending = false;
        });
        return out;
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
        // A redraw of several ports as one keeps its drawing when another
        // run is picked up, the way a single redraw does.
        if (typeof this._mergeRedrawLive === 'function' && this._mergeRedrawLive()) {
            this.finishMergeRedraw();
        }
        const run = this.runAtPoint(worldX, worldY);
        if (!run) return false;
        const { kind, layer: owner, num } = run;
        // A mirror screen's map is its source's (app-mirror-screens.js):
        // refused out loud, as every other edit of it is.
        if (this._overrideMirrorRefused(owner, kind)) return true;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        if (wholeCustom) {
            // A custom group's circuits are the wall owner's (app-power.js,
            // "custom mode: a group is ONE wall"): a run an old file left on
            // another member is adopted into the wall before it is opened -
            // one history entry for both.
            const wallOwner = kind === 'power' ? this.powerPathOwner(owner) : owner;
            if (wallOwner !== owner) {
                const adopted = this._adoptWallCircuits(wallOwner,
                    [{ layerId: owner.id, num }]);
                if (!adopted) return true;
                const first = adopted.ids.values().next().value;
                this.updateLayers(adopted.touched);
                this._activateRunForEdit(wallOwner, kind, first, 'Adopt Circuit');
                return true;
            }
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
    //
    // A SHARED circuit keeps its runs (the owner's ruling, 2026-10-19:
    // "taking over a circuit that is shared must keep its runs"). The
    // step that heads every run after the first is marked `branch: true`,
    // so a 3fer of three 5-cabinet columns is seeded as one path of 15
    // with two marks and reads back as runs [5, 5, 5] on the one circuit
    // (_mergeOverrideCircuits) - it still draws and tags as a 3fer. Before
    // this the seed was one run of 15 and the 3fer stopped drawing. A
    // cabinet added later joins the run it is added to (the last); the
    // mark rides its step, so a step removed takes its run's start with
    // it and that run joins the one before.
    overrideRun(owner, kind, num) {
        if (!owner || !num) return;
        // A locked screen stays unchanged (the owner's ruling, 2026-10-16):
        // taking a run over writes its owner's overrides and path.
        if (this._layerLocked(owner)) {
            if (typeof this._showLockedError === 'function') this._showLockedError([owner]);
            return;
        }
        if (this._overrideMirrorRefused(owner, kind)) return;
        const hits = this._runSeedHits(owner, kind, num);
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        if (kind === 'power') this.ensureCustomPowerState(owner);
        else this.ensureCustomFlowState(owner);
        owner[pathsKey][num] = hits.map(h => {
            const entry = this.makePathEntry(owner, h.layer, h.panel);
            if (h.branch) entry.branch = true;
            return entry;
        });
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
        if (this._overrideMirrorRefused(owner, kind)) return;
        this._activateRunForEdit(owner, kind, num, null);
    }

    // A data run on a mirror screen is its source's: redrawing it is
    // refused with the mirror's own message (_mirrorRefused). Power is the
    // screen's own and is not refused.
    _overrideMirrorRefused(owner, kind) {
        return kind !== 'power' && typeof this._mirrorRefused === 'function'
            && this._mirrorRefused(owner);
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
        // A locked screen stays unchanged (the owner's ruling, 2026-10-16):
        // moving its active port or circuit is a change, so the screen is
        // picked (selecting is not changing) and the error says why the run
        // did not become the active one. Alt+click on the run that is
        // already active changes nothing and says nothing.
        if (this._layerLocked(owner) && (idxChanged || undoLabel)) {
            this._showLockedError([owner]);
            return;
        }
        // The hold of the redraw open until now, read while it is still
        // live: before the active index moves, which ends it (QA, 1.6.0: a
        // second port picked up on the same screen lost the cabinets the
        // first had let go, and the walk took them).
        const prevHold = this._overrideHoldLive();
        const prevPowerHold = this._powerHoldLive();
        owner[idxKey] = num;
        const wholeCustom = kind === 'power'
            ? this.isCustomPower(owner) : this.isCustomFlow(owner);
        // The power redraw open until now ends here when this is another
        // circuit (_dropUnchangedRedraw, below).
        const prevEdit = this._overrideEditing;
        this._overrideEditing = wholeCustom
            ? null : { layerId: owner.id, kind, num };
        // A data port on an automatic screen holds its cabinets while it is
        // redrawn (_beginOverrideHold). Several ports redrawn as one hold
        // their own (_mergeHeldPanels).
        const merging = !!(this._mergeRedraw && this._mergeRedraw.layerId === owner.id);
        if (kind !== 'power' && !wholeCustom && !merging) {
            this._beginOverrideHold(owner, num, prevHold);
        } else if (prevHold) {
            this._endOverrideHold(prevHold);
        }
        // A circuit on an automatic screen holds its cabinets the same way
        // (_beginPowerHold); the hold of another circuit ends below.
        const samePowerRun = !!(prevPowerHold && kind === 'power'
            && prevPowerHold.layerId === owner.id && prevPowerHold.num === num);
        if (kind === 'power' && !wholeCustom) this._beginPowerHold(owner, num, prevPowerHold);
        else this._powerHeld = null;
        const label = undoLabel || (idxChanged
            ? (kind === 'power' ? 'Power Custom Circuit Change' : 'Custom Port Change')
            : null);
        if (label) {
            this.saveState(label);
            this.saveClientSideProperties();
            this.updateLayers(this._pathPersistLayers(owner));
        }
        if (prevEdit && prevEdit.kind === 'power'
                && !(kind === 'power' && prevEdit.layerId === owner.id && prevEdit.num === num)) {
            this._dropUnchangedRedraw(prevEdit);
        }
        if (prevPowerHold && !samePowerRun) this._endPowerHold(prevPowerHold);
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
        // Ending the edit of several ports redrawn as one keeps what was
        // drawn (Esc, which puts it all back, is caught before this).
        if (typeof this._mergeRedrawLive === 'function' && this._mergeRedrawLive()) {
            this.finishMergeRedraw();
            return;
        }
        if (!this._overrideEditing) return;
        const ended = this._overrideEditing;
        const wasPower = ended.kind === 'power';
        const hold = this._overrideHoldLive();
        const powerHold = this._powerHoldLive();
        this._overrideEditing = null;
        // The cabinets the redraw held and left undrawn go back to the
        // walk, and the toast says where they went.
        if (hold) this._endOverrideHold(hold);
        if (wasPower) {
            if (this.powerCustomSelection) this.powerCustomSelection.clear();
            // a redraw that changed nothing, or left nothing drawn, goes
            // back to the walk
            this._dropUnchangedRedraw(ended);
            // the cabinets it held and did not draw go back to the walk
            if (powerHold) this._endPowerHold(powerHold);
            this.updateCustomPowerUI();
        } else {
            if (this.customSelection) this.customSelection.clear();
            this.updateCustomFlowUI();
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // -- A circuit redrawn without a change (the owner's ruling, 2026-11-03)
    //
    // Taking a circuit over seeds its path with the cabinets it carries
    // (overrideRun), so a redraw that ends with exactly those - nothing
    // drawn, or Apply Pattern laying the same runs back down - used to
    // stay an override all the same, frozen where it was. A later redraw
    // that shrank the circuit before it then could not slide it left
    // (calculatePowerAssignments' `apart`): "i redrew ports so s1-1 is a
    // twofer and s1-2 is a single column. so column 4-5 should become a
    // twofer" - and the frozen one held 5-6. A power redraw that ends
    // unchanged goes back to the walk: Esc, a tab switch, or a redraw of
    // another circuit (_activateRunForEdit) ends it.
    //
    // "Unchanged" is the walk's own answer (_powerOverrideIsWalk): the
    // circuit the automatic walk puts under that number without the
    // override - the same cabinets in the same order and the same runs.
    // Letting it go then changes no circuit, so nothing else moves; it
    // just stops holding its place. A show saved before this rule has its
    // unchanged redraws let go as it opens (dropUnchangedRedrawsOnOpen).

    // Is `owner`'s taken-over circuit `num` exactly what the automatic
    // walk gives that number? `pristine` asks the walk with no circuit
    // taken over at all - the walk the redraw was made on when it came
    // first (the open's repair of an older show).
    _powerOverrideIsWalk(owner, num, { pristine = false } = {}) {
        if (!owner || !this.isRunOverridden(owner, 'power', num)) return false;
        const own = this._ownOverrideRuns(owner, 'power').find(o => o.num === num);
        if (!own) return false;
        const had = owner.powerCustomOverrides;
        let res;
        try {
            owner.powerCustomOverrides = pristine
                ? [] : this.getOverrideNums(owner, 'power').filter(n => n !== num);
            res = this.calculatePowerAssignments(owner) || {};
        } finally {
            owner.powerCustomOverrides = had;
        }
        if (res.error || !Array.isArray(res.circuits)) return false;
        const idx = Array.isArray(res.nums) ? res.nums.indexOf(num) : num - 1;
        const walk = idx >= 0 ? res.circuits[idx] : null;
        if (!Array.isArray(walk) || walk.length !== own.hits.length) return false;
        if (walk.some((p, i) => p !== own.hits[i].panel)) return false;
        const runs = (res.runs && res.runs[idx]) || [walk.length];
        const counts = this._overrideRunCounts(own.hits);
        return runs.length === counts.length && runs.every((n, i) => n === counts[i]);
    }

    // Let go of `owner`'s taken-over circuit `num`: the override and its
    // path go and the walk feeds the cabinets again. Model only.
    _releasePowerOverride(owner, num) {
        owner.powerCustomOverrides = this.getOverrideNums(owner, 'power').filter(n => n !== num);
        if (owner.powerCustomPaths) delete owner.powerCustomPaths[num];
        const s = this._overrideEditing;
        if (s && s.kind === 'power' && s.layerId === owner.id && s.num === num) {
            this._overrideEditing = null;
        }
    }

    // The power redraw `ended` ({ layerId, kind, num }, the editing state
    // that just closed): back to the walk when it changed nothing, as one
    // undo step. True when it was let go.
    //
    // NO PHANTOM CIRCUITS (1.6.0 QA, beta.5), the data ports' rule
    // (_repairEmptyOverrides): a redraw that ends with nothing drawn on
    // its circuit (Clear Circuit, then Esc) hands the number back to the
    // walk the same way, and the toast says so. Before this the circuit
    // stayed taken over with an empty path, and only Undo got it back.
    _dropUnchangedRedraw(ended) {
        if (!ended || ended.kind !== 'power' || !this.project) return false;
        const owner = (this.project.layers || []).find(l => l && l.id === ended.layerId);
        if (!owner || this._layerLocked(owner) || this.isCustomPower(owner)) return false;
        const empty = this._powerOverrideIsEmpty(owner, ended.num);
        if (!empty && !this._powerOverrideIsWalk(owner, ended.num)) return false;
        const label = this.getPowerCircuitLabel(owner, ended.num);
        this._releasePowerOverride(owner, ended.num);
        sendClientLog(empty ? 'override_empty_released' : 'override_unchanged_released',
            { layerId: owner.id, num: ended.num });
        this.saveState('Return Circuit To Auto');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        this.updatePowerCapacityDisplay();
        if (empty && typeof this._toast === 'function') {
            this._toast(`${owner.name || 'Screen'}: nothing was drawn on circuit ${label}, `
                + 'so it went back to automatic.', false, 6000);
        }
        return true;
    }

    // Is `owner`'s taken-over circuit `num` one with no cabinet on it?
    _powerOverrideIsEmpty(owner, num) {
        if (!owner || !this.isRunOverridden(owner, 'power', num)) return false;
        return !this._ownOverrideRuns(owner, 'power').some(o => o.num === num);
    }

    // The open's repair: every taken-over circuit that is the walk's own
    // circuit is let go, on every screen that is not locked. `older` (a
    // show saved before this rule) also lets go of one that is the walk
    // with no circuit taken over - a redraw made first that changed
    // nothing, frozen there before a later one shrank the circuit ahead
    // of it. Returns { layers: the screens changed, notes: the toast's
    // sentences }.
    dropUnchangedRedrawsOnOpen(older) {
        const out = { layers: [], notes: [] };
        if (!this.project || !Array.isArray(this.project.layers)) return out;
        this.project.layers.forEach(owner => {
            if (!owner || (owner.type || 'screen') !== 'screen') return;
            if (this.isCustomPower(owner) || this._layerLocked(owner)) return;
            const letGo = [];
            const emptied = [];
            // Labels read before anything is let go (they follow the walk).
            const labelOf = new Map(this.getOverrideNums(owner, 'power')
                .map(n => [n, this.getPowerCircuitLabel(owner, n)]));
            this.getOverrideNums(owner, 'power').forEach(num => {
                // A circuit taken over with nothing drawn on it (no phantom
                // circuits, _dropUnchangedRedraw) goes back too.
                if (this._powerOverrideIsEmpty(owner, num)) {
                    this._releasePowerOverride(owner, num);
                    emptied.push(num);
                    return;
                }
                const same = this._powerOverrideIsWalk(owner, num)
                    || (older && this._powerOverrideIsWalk(owner, num, { pristine: true }));
                if (!same) return;
                this._releasePowerOverride(owner, num);
                letGo.push(num);
            });
            if (!letGo.length && !emptied.length) return;
            out.layers.push(owner);
            const sentence = (nums, what) => {
                const labels = nums.map(n => labelOf.get(n));
                const one = labels.length === 1;
                return `${owner.name || 'Screen'}: circuit${one ? '' : 's'} ${labels.join(', ')} `
                    + `${what(one)} and ${one ? 'is' : 'are'} automatic again.`;
            };
            if (letGo.length) out.notes.push(sentence(letGo, one => `${one ? 'was' : 'were'} redrawn without a change`));
            if (emptied.length) out.notes.push(sentence(emptied, one => `had nothing drawn on ${one ? 'it' : 'them'}`));
            sendClientLog('override_unchanged_released_on_open',
                { layerId: owner.id, nums: letGo, emptied, older: !!older });
        });
        return out;
    }

    // Was `project` saved before an unchanged redraw went back to the walk
    // (after 1.6.0-beta.4)? Read off the file's own stamp, before the load
    // stamps it.
    redrawsPredateRelease(project = this.project) {
        if (this.projectPredatesVersion('1.6.0', project)) return true;
        const m = /^\s*v?1\.6\.0-beta\.(\d+)/.exec(String((project && project.app_version) || ''));
        return !!m && Number(m[1]) <= 4;
    }

    // Hand one overridden run back to the automatic walk: the override and
    // its drawn path go, and the engine re-flows the freed cabinets on the
    // next pass. One named undo step puts the drawing back.
    returnRunToAuto(owner, kind, num) {
        if (!owner || !this.isRunOverridden(owner, kind, num)) return;
        // Locked screens stay unchanged: neither a locked owner's override
        // nor one drawn across a locked screen's cabinets is let go.
        const locked = (typeof this._runLockedLayers === 'function')
            ? this._runLockedLayers(owner, kind, num) : [];
        if (locked.length) {
            this._showLockedError(locked);
            return;
        }
        const pathsKey = kind === 'power' ? 'powerCustomPaths' : 'customPortPaths';
        const ovrKey = kind === 'power' ? 'powerCustomOverrides' : 'customPortOverrides';
        // The automatic walk re-flows the freed cabinets, so a power run let
        // go can move a locked screen's circuits on a multi box it shares:
        // put back then, the screen named (_lockedPowerTrial).
        const shared = kind === 'power' ? this._lockedPowerTrial() : null;
        owner[ovrKey] = this.getOverrideNums(owner, kind).filter(n => n !== num);
        if (owner[pathsKey]) delete owner[pathsKey][num];
        if (shared && shared()) return;
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
        // The heads of a shared circuit's runs after the first - the
        // packer's per-run cabinet counts (see overrideRun).
        const heads = new Set();
        const counts = (res.runs && res.runs[idx]) || [];
        let at = 0;
        counts.forEach((n, k) => { if (k > 0) heads.add(at); at += n; });
        return circuits[idx].map((panel, i) => {
            const hit = { layer: (owners && owners[i]) ? owners[i] : owner, panel };
            if (heads.has(i)) hit.branch = true;
            return hit;
        });
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
            : `port ${this._portNumberText(num)}`;
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
