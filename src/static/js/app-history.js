// app-history: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _History {
    // ===== HISTORY SYSTEM =====
    // An 'Initial State' history is the project as it was loaded, opened
    // or made new: nothing unsaved (app-project-io markProjectClean). A
    // guide's 'Tutorial' and 'Recovered' are not: the recovered project
    // was never saved as it stands.
    resetHistory(initialAction = 'Initial State') {
        // Every project load and new project comes through here: the 3D
        // view takes the opened project's saved camera when this moves
        // (app-stage3d.js _s3dAdoptViewState).
        this._projectEpoch = (this._projectEpoch || 0) + 1;
        this.history = [];
        this.historyIndex = -1;
        // A new project's numbers are what it prints as opened: the commit
        // in saveState below takes them as the baseline and writes nothing
        // (app-naming _commitMultiNumbers).
        this._multiBaseline = null;
        this._multiHoldsDirty = false;
        if (typeof this._qpProjectChanged === 'function') this._qpProjectChanged();
        this.saveState(initialAction);
        if (initialAction === 'Initial State' && typeof this.markProjectClean === 'function') {
            this.markProjectClean();
        }
        sendClientLog('history_reset', { action: initialAction });
    }
    
    // Snapshot serializer: leading-underscore keys are runtime caches by
    // convention (the preset serializer skips them, file load deletes them),
    // and they have no business in an undo entry. This is not only hygiene:
    // the power render caches per-frame data on the layers, and one of those
    // caches held references back into project.layers - which made the whole
    // project CIRCULAR, so the plain JSON.stringify here THREW on every edit
    // made after a grouped wall rendered in Power view. History silently
    // stopped recording, and Ctrl+Z then restored whatever stale entry was
    // last - which is how a power edit "undid" the user's screen groups.
    // The cache itself now stores ids (canvas.js _powerOwnerIdRows), but the
    // snapshot must stay immune to the next cache someone parks on a layer.
    _snapshotReplacer(key, value) {
        return (typeof key === 'string' && key.length > 1 && key.charAt(0) === '_')
            ? undefined : value;
    }

    // The show's binder logo (project.binder.logo, app-binder.js) rides
    // every snapshot. A parse makes a new string each time, so fifty
    // entries of an unchanged logo held fifty copies of it; this points
    // `into`'s logo at `from`'s when the two are equal, so they share one
    // (strings are immutable: sharing is safe).
    _shareBinderLogo(into, from) {
        const a = into && into.binder, b = from && from.binder;
        if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return;
        if (typeof a.logo === 'string' && a.logo.length > 256 && a.logo === b.logo) a.logo = b.logo;
    }

    saveState(action) {
        // v0.10.7.2: history isn't allocated until resetHistory() runs, which is
        // after setupEventListeners(). Guard against any save that fires before
        // then (e.g. a debounced picker commit flushing during setup) rather than
        // throwing on this.history.length and aborting the caller mid-setup.
        if (!Array.isArray(this.history)) return;
        // A layer edit the canvas guard just refused put the screens back;
        // the caller's own step in the same task has nothing to record
        // (app-port-assignment _canvasGuardEdit).
        if (this._canvasRefusedEdit) return;
        // v0.10.5: a debounced snapshot still waiting to fire must land BEFORE
        // this one, or history ends up out of order (and the pending timer
        // would later snapshot a state that already includes this action).
        this._flushPendingSaveState();

        // Multi numbers do not shift (ruling 2026-10-16): whatever this
        // action would have renumbered is held in the distros' stores
        // before the entry is taken, so undo, redo and save carry it.
        if (typeof this._commitMultiNumbers === 'function') {
            try {
                this._commitMultiNumbers();
            } catch (e) {
                sendClientLog('multi_numbers_commit_failed', { action, error: String(e && e.message || e) });
            }
        }
        // A mirror screen's data map is its source's (2026-10-30): copied
        // onto it before the entry is taken, so undo, redo and save carry
        // the map the canvas draws (app-mirror-screens.js).
        if (typeof this._syncMirrorScreens === 'function') {
            try {
                this._syncMirrorScreens();
            } catch (e) {
                sendClientLog('mirror_sync_failed', { action, error: String(e && e.message || e) });
            }
        }

        const json = JSON.stringify(this.project, this._snapshotReplacer);

        // Undo audit: an action that changed nothing must not grow a step.
        // Several commit handlers snapshot unconditionally (blurring an
        // untouched field fires 'Update Properties', a locked selection skips
        // its own writes), and each no-op entry makes one Ctrl+Z that visibly
        // does nothing - and shifts a real step off the front once history is
        // full. Comparing serialized forms is exact: both sides went through
        // the same stringify with the same replacer.
        const current = this.history[this.historyIndex];
        if (current && JSON.stringify(current.project) === json) {
            sendClientLog('save_state_skipped_noop', {
                action, historyIndex: this.historyIndex,
            });
            return;
        }

        // Save current project state
        const snapshot = JSON.parse(json);
        // The show's binder logo (a data URL up to a few hundred KB) is
        // one string shared by every entry that holds the same logo, not
        // a fresh copy per entry (_shareBinderLogo).
        this._shareBinderLogo(snapshot, current ? current.project : this.project);
        const state = {
            action: action,
            project: snapshot,
            timestamp: Date.now(),
            // A circuit redraw open as this entry is taken: the project reads
            // right only with its hold (app-run-overrides _powerRedrawRecord).
            redraw: typeof this._powerRedrawRecord === 'function' ? this._powerRedrawRecord() : null,
            // The Hue slider as this entry leaves it (app-quick-palettes).
            quickPalette: typeof this._qpHistoryRecord === 'function' ? this._qpHistoryRecord() : null
        };


        // Remove any future states if we're not at the end
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }
        
        // Add new state
        this.history.push(state);
        
        // Limit history size
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        } else {
            this.historyIndex++;
        }
        sendClientLog('save_state', {
            action,
            historyIndex: this.historyIndex,
            historyLength: this.history.length,
            layers: this.project.layers ? this.project.layers.length : 0,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : [],
            currentLayerId: this.currentLayer ? this.currentLayer.id : null
        });
        // The server keeps "unsaved" across a reload (app-project-io).
        if (typeof this._noteUnsavedState === 'function') this._noteUnsavedState();
    }

    /**
     * Coalesce a continuous stream of edits (dragging a slider, typing in a
     * text field) into ONE undo step.
     *
     * `key` identifies what is being edited. When it changes, the pending
     * snapshot is flushed first so switching controls always starts a new undo
     * step instead of folding both edits together. Discrete, committed edits
     * should call saveState() directly rather than coming through here.
     */
    debouncedSaveState(action, delay = 500, key = null) {
        const k = key || action;
        if (this._saveStateTimer && this._pendingSaveKey !== k) {
            this._flushPendingSaveState();
        }
        this._pendingSaveAction = action;
        this._pendingSaveKey = k;
        if (this._saveStateTimer) clearTimeout(this._saveStateTimer);
        this._saveStateTimer = setTimeout(() => {
            this._saveStateTimer = null;
            const pending = this._pendingSaveAction || action;
            this._pendingSaveAction = null;
            this._pendingSaveKey = null;
            this.saveState(pending);
        }, delay);
    }

    /**
     * Commit a pending debounced snapshot immediately. Clearing the timer
     * first keeps saveState()'s own flush call from recursing.
     */
    _flushPendingSaveState() {
        if (!this._saveStateTimer) return;
        clearTimeout(this._saveStateTimer);
        this._saveStateTimer = null;
        const pending = this._pendingSaveAction;
        this._pendingSaveAction = null;
        this._pendingSaveKey = null;
        if (pending) this.saveState(pending);
    }

    undo() {
        // A delete still landing has not taken its step yet: the screen is
        // gone from the page as soon as the server answers the DELETE, and
        // its 'Delete Layer' entry is taken only once the project read that
        // follows comes back. An undo in that gap stepped back over the edit
        // before the delete (or did nothing), and the delete's entry then
        // cut the redo off. Held, it plays once the delete has its step
        // (1.7.0 CI, caught on a Linux runner with the page's log).
        if (this._holdHistoryKey('undo')) return;
        // Land any in-flight debounced snapshot first, so Ctrl+Z steps back
        // over the edit the user just made instead of skipping past it (and
        // so the timer can't overwrite the restored state a moment later).
        this._flushPendingSaveState();

        if (this.historyIndex > 0) {
            this.historyIndex--;
            const state = this.history[this.historyIndex];
            
            
            // The IDM Locator's field colour and live highlight are view
            // state, never an undo step (app-idm-locator.js): the restored
            // project keeps the ones on screen now, whatever the snapshot
            // held.
            const idmField = this.project ? this.project.idmField : undefined;
            const idmHighlight = this.project ? this.project.idmHighlight : undefined;
            this.project = JSON.parse(JSON.stringify(state.project));
            this._shareBinderLogo(this.project, state.project);
            if (idmField !== undefined) this.project.idmField = JSON.parse(JSON.stringify(idmField));
            if (idmHighlight !== undefined) this.project.idmHighlight = JSON.parse(JSON.stringify(idmHighlight));
            this.dedupeProjectLayers('undo_restore');
            // The restored entry's numbers are the ones in force now.
            if (typeof this._resetMultiBaseline === 'function') this._resetMultiBaseline();
            sendClientLog('undo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            this._reconcileSelectionAfterRestore();
            this._activeCanvasFollowsSelection(state);
            // The circuit redraw this entry had open comes back with it, and
            // one it did not have closes (app-run-overrides).
            if (typeof this._restorePowerRedraw === 'function') this._restorePowerRedraw(state.redraw);
            // The Hue slider stays true of the colors put back.
            if (typeof this._qpRestoreHistory === 'function') this._qpRestoreHistory(state.quickPalette);
            // Both, not just the data side. loadLayerToInputs() below happens
            // to refresh the power one too, so this was only exposed on its
            // early-return paths - but an undo in Power view has no business
            // depending on that.
            this.updateCustomFlowUI();
            this.updateCustomPowerUI();
            // The restored project can name different distros, multis and
            // splitter groups entirely, so the label ladder's tail cache and
            // the three power hosts all restate from the restored state -
            // the same set every distro/soca edit refreshes on its way in.
            this._refreshPowerPanelsAfterRestore();
            // v0.10.7.2: updateUI() re-renders the canvas but does NOT reload the
            // Screen Info fields or the toolbar Raster inputs, so without this an
            // undo/redo reverts the geometry while the sidebar keeps showing the
            // pre-undo numbers (panel size / columns / rows / raster) - the value
            // and the actual size disagree. Refresh them from the restored state,
            // exactly as deleteCurrentLayer already does for the same reason.
            if (typeof this.loadLayerToInputs === 'function') {
                try { this.loadLayerToInputs(); } catch (_) {}
            }
            if (typeof this.syncRasterFromProject === 'function') {
                try { this.syncRasterFromProject(); } catch (_) {}
            }

            // Sync the restored state to the backend - AFTER any layer PUT
            // still in flight has settled. The server is threaded, so a
            // drag's commit PUT racing past this one would re-write the
            // dragged offsets over the restored project server-side, and the
            // funnel's response would faithfully hand the un-undone drag
            // back for adoption. See _syncRestoredProject.
            this._syncRestoredProject(state, 'Undo');
            if (typeof this._noteUnsavedState === 'function') this._noteUnsavedState();
        } else {
        }
    }

    // The restore PUT both undo() and redo() make, sequenced behind the
    // in-flight layer PUTs updateLayers/updateLayer registered.
    // `keepPristine` (the guide's exit and recovery, quickstart
    // restoreProject): the world being put back is the user's own, taken
    // before the guide touched anything; when that snapshot is still
    // pristine the PUT says `keep_pristine` and the server keeps the flag
    // the snapshot carries instead of ending it (restore_project). Undo
    // and redo never pass it: an undone edit is still an edit.
    _syncRestoredProject(entry, label, { keepPristine = false } = {}) {
        const inflight = [...(this._inflightLayerPuts || [])];
        // And behind the pull sheet's POST queue (app-pull-list.js): a
        // cable-unit or edits POST still in flight carries the state being
        // undone, and landing after this PUT it would put it back.
        const sheet = typeof this._pullSheetStateSettled === 'function'
            ? this._pullSheetStateSettled() : null;
        if (sheet) inflight.push(sheet);
        const restoresPristine = keepPristine === true
            && !!this.project && this.project.is_pristine === true;
        // While this restore is on its way to the server, layer_updated
        // broadcasts describe the pre-restore server state (usually the very
        // edit being undone) - app-core's socket handler drops them while
        // this counter is up, and the adopted response below reconciles.
        this._restorePutPending = (this._restorePutPending || 0) + 1;
        const done = () => {
            this._restorePutPending = Math.max(0, (this._restorePutPending || 1) - 1);
        };
        // Why the project is replaced, for the other pages that follow it
        // (app-core _onProjectReplaced): an undo or redo stays on the show,
        // a guide's step or its end does not.
        const reason = label === 'Undo' ? 'undo' : label === 'Redo' ? 'redo'
            : (label === 'Tutorial Exit' || label === 'Tour Recovery') ? 'guide_end'
                : /^(Tutorial|Tour)/.test(label) ? 'guide' : 'restore';
        // Another page's replace taken in while this one was out: its
        // answer describes a project the page no longer shows.
        const replacesAtSend = this._foreignReplaces || 0;
        const stale = () => (this._foreignReplaces || 0) !== replacesAtSend;
        // Taken in before this one went: the project it would send is the
        // other page's, and nothing of this page's is left to put back.
        const send = () => stale()
            ? (done(), sendClientLog('restore_dropped_after_other_page', { label }), Promise.resolve())
            : fetch(`/api/project?${this._replaceQuery(reason)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            // Serialized at send time: this.project is exactly the restored
            // snapshot (nothing else mutates it between the restore and the
            // settle - a NEW user edit would snapshot and re-PUT itself).
            // The marker is a request field, never stored (the server pops
            // it) and never on this.project.
            body: JSON.stringify(restoresPristine
                ? { ...this.project, keep_pristine: true } : this.project)
        })
            .then(response => response.json())
            .then(repaired => {
                done();
                if (stale()) {
                    sendClientLog('restore_answer_after_other_page', { label });
                    return;
                }
                this._adoptRestoredProjectRepair(entry, repaired);
                this.updateUI();
            })
            .catch(error => {
                done();
                console.error(label + ' backend sync failed:', error);
            });
        // refreshProcessors waits on these and drops a read that was asked
        // before one began.
        this._restoreSeq = (this._restoreSeq || 0) + 1;
        const landed = inflight.length === 0 ? send() : Promise.all(inflight).then(send, send);
        const puts = this._restorePutsInFlight || (this._restorePutsInFlight = new Set());
        puts.add(landed);
        const drop = () => puts.delete(landed);
        landed.then(drop, drop);
        return landed;
    }

    // The PUT above is not a pure store: restore_project re-derives panel
    // geometry, enforces group integrity, re-stocks a boxless SX40's default
    // boxes and re-seeds the id counters - and returns the repaired body.
    // Throwing that body away (as undo/redo did before this) let this.project
    // silently diverge from the server's truth: the next refreshProcessors()
    // adopted the healed tree with no snapshot, and every repeat of the same
    // undo re-healed from scratch, minting fresh box ids each pass.
    // _commitGroupChange already adopts its repaired response for exactly this
    // reason; this is the same move for the restore funnel. The history entry
    // is rewritten too, so restoring it again round-trips to itself and the
    // walk stays deterministic.
    // Order-insensitive serialization for "did the funnel actually change
    // anything": Flask's jsonify sorts object keys, the client's stringify
    // keeps insertion order, so a plain string compare of the two calls every
    // response a repair and adoption would churn on every undo. Underscore
    // caches are dropped here for the same reason _snapshotReplacer drops
    // them from snapshots.
    _canonicalJson(value) {
        const walk = (v) => {
            if (Array.isArray(v)) return '[' + v.map(walk).join(',') + ']';
            if (v && typeof v === 'object') {
                const keys = Object.keys(v).filter(k =>
                    !(k.length > 1 && k.charAt(0) === '_')
                    && v[k] !== undefined).sort();
                return '{' + keys.map(k =>
                    JSON.stringify(k) + ':' + walk(v[k])).join(',') + '}';
            }
            return JSON.stringify(v) === undefined ? 'null' : JSON.stringify(v);
        };
        return walk(value);
    }

    _adoptRestoredProjectRepair(entry, repaired) {
        if (!repaired || !Array.isArray(repaired.layers)) return;  // error body
        // Another undo/redo (or a new edit) moved the index while this PUT was
        // in flight - its own round-trip owns the client state now.
        if (this.history[this.historyIndex] !== entry) return;
        // No repair -> no adoption. Canonical compare, or the server's sorted
        // key order alone would count as one.
        if (this._canonicalJson(repaired)
                === this._canonicalJson(entry.project)) return;
        const healed = JSON.stringify(repaired, this._snapshotReplacer);
        sendClientLog('restore_repair_adopted', {
            action: entry.action, historyIndex: this.historyIndex,
        });
        this.project = JSON.parse(healed);
        this.dedupeProjectLayers('restore_repair');
        entry.project = JSON.parse(healed);
        this._shareBinderLogo(entry.project, this.project);
        this._reconcileSelectionAfterRestore();
        this._refreshPowerPanelsAfterRestore();
        if (typeof this.loadLayerToInputs === 'function') {
            try { this.loadLayerToInputs(); } catch (_) {}
        }
        if (typeof this.syncRasterFromProject === 'function') {
            try { this.syncRasterFromProject(); } catch (_) {}
        }
    }

    // Re-point the selection at the project that was just swapped in.
    // Undo and redo used to re-resolve currentLayer from its OWN id and
    // leave selectedLayerIds alone. Undo back past a paste drops the pasted
    // layer, so currentLayer resolved to null while the selection kept the
    // id; redo then brought the layer back, but the `if (this.currentLayer)`
    // guard was false by then, so nothing re-pointed it. The app sat with
    // currentLayer null and a live selection, and the next view-tab click
    // threw inside loadLayerToInputs (2026-09-23). Now: ids that no longer
    // exist leave the selection, currentLayer follows its id when it can,
    // and otherwise falls back to the first selected layer that exists.
    _reconcileSelectionAfterRestore() {
        const layers = (this.project && Array.isArray(this.project.layers))
            ? this.project.layers : [];
        const byId = new Map(layers.map(l => [l.id, l]));
        if (this.selectedLayerIds instanceof Set) {
            for (const id of [...this.selectedLayerIds]) {
                if (!byId.has(id)) this.selectedLayerIds.delete(id);
            }
        } else {
            this.selectedLayerIds = new Set();
        }
        this.currentLayer = this.currentLayer
            ? (byId.get(this.currentLayer.id) || null) : null;
        if (!this.currentLayer && this.selectedLayerIds.size > 0) {
            const firstId = [...this.selectedLayerIds][0];
            this.currentLayer = byId.get(firstId) || null;
        }
        if (this.lastSelectedLayerId != null && !byId.has(this.lastSelectedLayerId)) {
            this.lastSelectedLayerId = this.currentLayer ? this.currentLayer.id : null;
        }
        if (this.selectionAnchorLayerId != null && !byId.has(this.selectionAnchorLayerId)) {
            this.selectionAnchorLayerId = this.currentLayer ? this.currentLayer.id : null;
        }
        // The restored project may have dropped or hidden screens the
        // cabinet selection named.
        if (typeof this._screenSelectionChanged === 'function') this._screenSelectionChanged();
    }

    // The active canvas is whichever one the selected screen sits on, however
    // the selection got there. A history entry holds the active canvas of the
    // moment it was taken, and selecting is not a step of its own: click B1 on
    // Canvas 2, change a figure, undo, and the entry from before the click put
    // the active canvas back on Canvas 1 with B1 still selected, so Raster read
    // the wrong canvas (1.6.0 QA, beta.6; owner: the raster size shows the
    // canvas of the screen you select). Called before the restore's PUT, which
    // carries it to the server. The entry takes it too, so the PUT's answer
    // does not read as a repair. Nothing selected: the entry's canvas stands.
    _activeCanvasFollowsSelection(entry) {
        const layer = this.currentLayer;
        if (!layer || !this.project) return;
        const canvases = Array.isArray(this.project.canvases) ? this.project.canvases : [];
        const r = window.canvasRenderer;
        const showView = !!(r && r.isShowLookView && r.isShowLookView());
        const id = (showView && layer.show_canvas_id) ? layer.show_canvas_id : layer.canvas_id;
        if (!id || id === this.project.active_canvas_id) return;
        if (!canvases.some(c => c.id === id)) return;
        this.project.active_canvas_id = id;
        if (entry && entry.project) entry.project.active_canvas_id = id;
    }

    // Undo/redo's half of the power feature's refresh discipline. Every write
    // to the distro list or a soca field drops _circuitTailCache and restates
    // the three hosts; a restore that swaps the whole project out from under
    // them has to do the same or the panels keep narrating the pre-undo state.
    _refreshPowerPanelsAfterRestore() {
        this._circuitTailCache = null;
        ['refreshDistroPanel', 'refreshSocaRuns', 'refreshSplitterPanel',
            'updatePowerLabelEditor', 'renderHardwareDock'].forEach(fn => {
            if (typeof this[fn] === 'function') {
                try { this[fn](); } catch (_) { /* host absent outside Power */ }
            }
        });
    }

    redo() {
        if (this._holdHistoryKey('redo')) return;
        this._flushPendingSaveState();

        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            const state = this.history[this.historyIndex];
            
            
            // The IDM Locator's field colour and live highlight are view
            // state, never an undo step (app-idm-locator.js): the restored
            // project keeps the ones on screen now, whatever the snapshot
            // held.
            const idmField = this.project ? this.project.idmField : undefined;
            const idmHighlight = this.project ? this.project.idmHighlight : undefined;
            this.project = JSON.parse(JSON.stringify(state.project));
            this._shareBinderLogo(this.project, state.project);
            if (idmField !== undefined) this.project.idmField = JSON.parse(JSON.stringify(idmField));
            if (idmHighlight !== undefined) this.project.idmHighlight = JSON.parse(JSON.stringify(idmHighlight));
            this.dedupeProjectLayers('redo_restore');
            if (typeof this._resetMultiBaseline === 'function') this._resetMultiBaseline();
            sendClientLog('redo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            this._reconcileSelectionAfterRestore();
            this._activeCanvasFollowsSelection(state);
            // The circuit redraw this entry had open comes back with it, and
            // one it did not have closes (app-run-overrides).
            if (typeof this._restorePowerRedraw === 'function') this._restorePowerRedraw(state.redraw);
            // The Hue slider stays true of the colors put back.
            if (typeof this._qpRestoreHistory === 'function') this._qpRestoreHistory(state.quickPalette);
            // Both, not just the data side. loadLayerToInputs() below happens
            // to refresh the power one too, so this was only exposed on its
            // early-return paths - but an undo in Power view has no business
            // depending on that.
            this.updateCustomFlowUI();
            this.updateCustomPowerUI();
            // Same restatement undo does - see _refreshPowerPanelsAfterRestore.
            this._refreshPowerPanelsAfterRestore();
            // v0.10.7.2: updateUI() re-renders the canvas but does NOT reload the
            // Screen Info fields or the toolbar Raster inputs, so without this an
            // undo/redo reverts the geometry while the sidebar keeps showing the
            // pre-undo numbers (panel size / columns / rows / raster) - the value
            // and the actual size disagree. Refresh them from the restored state,
            // exactly as deleteCurrentLayer already does for the same reason.
            if (typeof this.loadLayerToInputs === 'function') {
                try { this.loadLayerToInputs(); } catch (_) {}
            }
            if (typeof this.syncRasterFromProject === 'function') {
                try { this.syncRasterFromProject(); } catch (_) {}
            }
            
            // Same sequenced sync-and-adopt as undo - see _syncRestoredProject.
            this._syncRestoredProject(state, 'Redo');
            if (typeof this._noteUnsavedState === 'function') this._noteUnsavedState();
        } else {
        }
    }
    
    // ===== DELETE LAYER =====
    
    deleteCurrentLayer() {
        // A Delete pressed while the last one is still landing is not
        // dropped: it is held and played once that delete is done, on the
        // screen it left selected - or, with one screen left, says the last
        // screen cannot be deleted. Dropped, two quick Deletes on two
        // screens removed one and said nothing (1.7.0 QA).
        if (this.deletionInProgress) {
            this._deletesQueued = (this._deletesQueued || 0) + 1;
            return;
        }
        if (!this.currentLayer) {
            return;
        }
        
        // Collect all selected layer IDs to delete
        const requested = this.selectedLayerIds && this.selectedLayerIds.size > 1
            ? [...this.selectedLayerIds]
            : [this.currentLayer.id];
        // A locked screen stays until it is unlocked (the owner's ruling,
        // 2026-10-16): Delete removes the unlocked screens of the selection
        // and names the locked ones; with nothing left to remove it is only
        // the error.
        const { ids: idsToDelete, locked } = typeof this._deletableLayerIds === 'function'
            ? this._deletableLayerIds(requested) : { ids: requested, locked: [] };
        if (locked.length) this._showLockedError(locked);
        if (idsToDelete.length === 0) return;
        
        // Don't delete if it would remove ALL layers
        if (idsToDelete.length >= this.project.layers.length) {
            // Keep at least one layer
            if (this.project.layers.length <= 1) {
                this._toast('The last screen cannot be deleted.', true);
                return;
            }
            idsToDelete.pop(); // Remove last one from delete list to keep it
        }
        
        this.deletionInProgress = true;
        // The 'Delete Layer' snapshot is taken AFTER the deletes land, at the
        // bottom of deleteNext(), not here. Taken here it held the project
        // WITH the screen still in it, so redo restored the screen instead of
        // removing it: Delete -> Ctrl+Z -> Ctrl+Shift+Z left the screen on
        // screen with no way to get the delete back except doing it again.
        // Snapshotting after the mutation is what every other action in the
        // app does, and it leaves the undo side untouched - one Ctrl+Z still
        // lands on the previous entry, which still holds the edit made before
        // the delete.

        // Find index of current layer for post-delete selection
        const currentIndex = this.project.layers.findIndex(l => l.id === this.currentLayer.id);
        // A pull-sheet edit on a row that goes with the screens goes too
        // (owner, 2026-10-17) - the rows as they print before the first
        // request, dropped once the last has landed and before the snapshot.
        const pullBefore = typeof this._pullLiveRowKeys === 'function'
            ? this._pullLiveRowKeys() : null;
        this.currentLayer = null;
        
        // Delete all selected layers sequentially
        const deleteNext = (ids) => {
            if (ids.length === 0) {
                // All deletes done - refresh project
                fetch('/api/project')
                    .then(res => res.json())
                    .then(project => {
                        this.project = project;
                        this.dedupeProjectLayers('delete_layer');
                        
                        if (this.project.layers.length > 0) {
                            const newIndex = Math.min(currentIndex, this.project.layers.length - 1);
                            this.currentLayer = this.project.layers[newIndex];
                            this.selectedLayerIds = new Set([this.currentLayer.id]);
                            this.lastSelectedLayerId = this.currentLayer.id;
                            this.selectionAnchorLayerId = this.currentLayer.id;
                        } else {
                            this.currentLayer = null;
                            this.selectedLayerIds = new Set();
                            this.lastSelectedLayerId = null;
                            this.selectionAnchorLayerId = null;
                        }
                        if (typeof this._screenSelectionChanged === 'function') this._screenSelectionChanged();

                        // v0.8.7.6: refresh the layer-property inputs from
                        // the newly-promoted currentLayer. Without this the
                        // sidebar keeps showing the DELETED layer's
                        // cabinet_width / cabinet_height / columns / rows /
                        // etc., and the next "Update Properties" round-trip
                        // reads those stale values out of the inputs and
                        // writes them onto the surviving layer, clobbering
                        // its actual panel dimensions while the on-canvas
                        // panels stay sized correctly (because the panel
                        // geometry is already baked into layer.panels).
                        // Repro that exposed this: add a VN-8.3 preset
                        // screen (cabinet 60x120), delete the default
                        // Brompton screen (cabinet 192x384), edit the
                        // surviving screen's column count → its cabinet
                        // silently flipped to 192x384.
                        if (this.currentLayer && typeof this.loadLayerToInputs === 'function') {
                            try { this.loadLayerToInputs(); } catch (_) {}
                        }
                        if (pullBefore) this._dropPullEditsGoneWith(pullBefore);
                        // Post-mutation snapshot: this entry is the project
                        // WITHOUT the deleted screen, so redo re-applies the
                        // delete. See the note where deletionInProgress is
                        // set.
                        this.saveState('Delete Layer');
                        this.updateUI();
                    })
                    .finally(() => {
                        this.deletionInProgress = false;
                        // Play one held Delete; the rest wait on the delete
                        // it starts. One that starts none (the last screen,
                        // a locked one) says so once and the rest go with
                        // it - never left to fire on a later delete.
                        const held = this._deletesQueued || 0;
                        this._deletesQueued = 0;
                        if (held > 0) {
                            this.deleteCurrentLayer();
                            if (this.deletionInProgress) this._deletesQueued = held - 1;
                        }
                        // Undo and redo pressed meanwhile play now, in the
                        // order pressed, once no delete is left landing.
                        if (!this.deletionInProgress) this._playHeldHistoryKeys();
                    });
                return;
            }
            
            const id = ids.shift();
            sendClientLog('delete_layer', { id: id, name: (this.project.layers.find(l => l.id === id) || {}).name });
            
            fetch(`/api/layer/${id}`, { method: 'DELETE' })
                .then(res => res.json())
                .then(project => {
                    this.project = project;
                    deleteNext(ids);
                })
                .catch(error => {
                    console.error('DELETE failed:', error);
                    deleteNext(ids); // Continue with remaining deletes
                });
        };
        
        deleteNext([...idsToDelete]);
    }
    
    // Undo or redo pressed while a delete lands waits for it (see undo()).
    // True when the key was held.
    _holdHistoryKey(key) {
        if (!this.deletionInProgress) return false;
        (this._heldHistoryKeys || (this._heldHistoryKeys = [])).push(key);
        sendClientLog('history_key_held_for_delete', { key, held: this._heldHistoryKeys.length });
        return true;
    }

    _playHeldHistoryKeys() {
        const keys = this._heldHistoryKeys || [];
        this._heldHistoryKeys = [];
        for (const key of keys) {
            if (key === 'redo') this.redo();
            else this.undo();
        }
    }

    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 255, g: 0, b: 0 };
    }

    // Evaluate a simple arithmetic expression using + - * / and parentheses.
    // Returns a finite number, or null if the input is empty/invalid. Used by
    // the Watts per Panel field (and anywhere else we want a "spreadsheet-y"
    // numeric input) so users can type e.g. "200+50" or "1000/3" directly.
    evaluateNumericExpression(raw) {
        if (raw == null) return null;
        const s = String(raw).trim();
        if (s === '') return null;
        // Allow only digits, . , whitespace, and the four operators + - * / plus parentheses
        const cleaned = s.replace(/,/g, '').replace(/\s+/g, '');
        if (!/^[-+*/().\d]+$/.test(cleaned)) return null;
        // Reject dangerous patterns (consecutive operators other than a leading unary minus in a sub-expr)
        if (/[*/]{2,}|\+{2,}|-{3,}|[-+*/]$|^[*/]/.test(cleaned)) return null;
        try {
            // Function constructor with no scope access, still safer than eval(),
            // and the regex above guarantees only arithmetic characters are present.
            // eslint-disable-next-line no-new-func
            const result = Function('"use strict"; return (' + cleaned + ');')();
            if (typeof result !== 'number' || !isFinite(result)) return null;
            return result;
        } catch (e) {
            return null;
        }
    }

    // Format an evaluated number for display in the input: drop trailing zeros
    // but keep reasonable precision for fractional results (e.g. 1000/3).
    _formatEvaluatedNumber(n) {
        if (!isFinite(n)) return '0';
        if (Number.isInteger(n)) return String(n);
        // Up to 4 decimal places, trim trailing zeros
        return parseFloat(n.toFixed(4)).toString();
    }
    
    rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
}

for (const k of Object.getOwnPropertyNames(_History.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_History.prototype, k));
    }
}
