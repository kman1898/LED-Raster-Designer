// app-pixel-select: cabinet selection for LEDRasterApp - the custom-flow
// and custom-power edit modes (enter, leave, selection sets, marquee) and
// the Pixel Map bulk-select with its half-tile / blank bulk verbs.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// getPanelByRowCol's per-screen index: panels array -> { len, map of
// "row,col" -> the panel's SLOT in the array }. Weak, so a rebuilt screen's
// old array and its index simply go.
const PANEL_INDEX = new WeakMap();

class _PixelSelect {

    isCustomFlow(layer) {
        return !!layer && layer.flowPattern === 'custom';
    }

    // Is the path-EDITING machinery live for this layer right now? True in
    // whole-screen custom mode, exactly as every gate read before, and ALSO
    // while ONE overridden port is open for redrawing (see the per-run
    // override section below). Every editing gate - the click, the marquee,
    // the arrow keys, the pattern-on-selection - reads THIS; every gate about
    // what the map IS (rendering, counting, the group crossing) keeps reading
    // isCustomFlow, because a screen with one redrawn port is still an
    // automatic screen.
    isCustomFlowEditing(layer) {
        return this.isCustomFlow(layer) || this._isOverrideEditing(layer, 'data');
    }

    isCustomPowerEditing(layer) {
        return this.isCustomPower(layer) || this._isOverrideEditing(layer, 'power');
    }

    ensureCustomFlowState(layer) {
        if (!layer) return;
        if (!layer.customPortPaths) layer.customPortPaths = {};
        if (!layer.customPortIndex) layer.customPortIndex = 1;
    }

    // The screens a custom toggle acts on: the selected screen layers (the
    // group's peers follow through applyToSelectedLayers). An image or text
    // layer has no runs to draw, so it never decides the answer.
    _customModeTargets() {
        return (this.getSelectedLayers() || [])
            .filter(l => l && (l.type || 'screen') === 'screen');
    }

    // The screens one custom toggle changes: the selected screens and their
    // groups (a group is one screen), cut to the ones whose mode actually
    // differs from `enabled` - a screen already in the asked-for state is
    // never rewritten (2026-10-16: turning custom off used to reset the
    // pattern of every selected screen, including ones that were never
    // custom). Locked screens are split out: they stay exactly as they are
    // and the caller names them (_showLockedError).
    _customToggleScope(kind, enabled) {
        const isOn = kind === 'power'
            ? (l => this.isCustomPower(l)) : (l => this.isCustomFlow(l));
        const scope = [];
        const seen = new Set();
        const add = (l) => {
            if (!l || (l.type || 'screen') !== 'screen' || seen.has(l.id)) return;
            seen.add(l.id);
            scope.push(l);
        };
        this._customModeTargets().forEach(l => {
            add(l);
            if (typeof this.groupMembersOf === 'function') this.groupMembersOf(l).forEach(add);
        });
        const differ = scope.filter(l => isOn(l) !== !!enabled);
        return {
            change: differ.filter(l => !l.locked),
            locked: differ.filter(l => l.locked),
        };
    }

    // The pattern a screen goes back to when custom mode is turned off: its
    // own remembered one. A grouped screen takes ONE answer for its whole
    // group - the shown screen's when it is in that group, else the first
    // member that remembers one - because the pattern is a group-wide field
    // and the members must not come out of custom mode disagreeing.
    _customRestorePattern(layer, kind, changing) {
        const lastKey = kind === 'power' ? 'lastPowerFlowPattern' : 'lastFlowPattern';
        const usable = (l) => !!l && !!l[lastKey] && l[lastKey] !== 'custom';
        const group = (typeof this.getGroupOfLayer === 'function') ? this.getGroupOfLayer(layer) : null;
        if (group) {
            const members = (changing || []).filter(l => l && l.group_id === layer.group_id);
            const current = members.find(l => this.currentLayer && l.id === this.currentLayer.id);
            const pick = (current && usable(current)) ? current : members.find(usable);
            if (pick) return pick[lastKey];
        }
        return usable(layer) ? layer[lastKey] : 'tl-h';
    }

    // IDEMPOTENT, not time-guarded (2026-10-16). The model follows the
    // state the caller asks for - the checkbox's own `checked` - and a call
    // that would change nothing is a no-op that only re-syncs the controls.
    // A platform that fires `change` twice for one click hands the same
    // state twice, so the second is a no-op; a reversed echo is caught at
    // the box (app-wiring.js _customToggleEcho). Only the screens whose mode
    // differs are written, and a locked one stays as it is and is named.
    toggleCustomFlowMode(enabled) {
        if (!this.currentLayer) return;
        enabled = !!enabled;
        const { change, locked } = this._customToggleScope('data', enabled);
        this._showLockedError(locked);
        if (change.length === 0) {
            this.syncCustomModeControls();
            return;
        }
        change.forEach(layer => {
            if (enabled) {
                if (layer.flowPattern && layer.flowPattern !== 'custom') {
                    layer.lastFlowPattern = layer.flowPattern;
                }
                layer.flowPattern = 'custom';
                this.ensureCustomFlowState(layer);
            } else {
                layer.flowPattern = this._customRestorePattern(layer, 'data', change);
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
        // The group's members ride the same PUT as the selection.
        this.updateLayers(this._persistWith(change));
        this.syncCustomModeControls();
        window.canvasRenderer.render();
    }

    // Both custom checkboxes and both custom panels, from the shown screen.
    // Called wherever a pattern or custom state can change - the toggles,
    // the pattern tiles, the right-click item - so a box can never show a
    // mode the screen is not in. updateCustomFlowUI / updateCustomPowerUI
    // each set their own box, so every older caller of those resyncs too.
    syncCustomModeControls() {
        this.updateCustomFlowUI();
        this.updateCustomPowerUI();
    }

    // The checkbox face of one side: ticked exactly when the shown screen is
    // in whole-screen custom mode (the pattern reads 'custom'). An open
    // per-run override is not custom mode, so it leaves the box unticked.
    _syncCustomModeBox(kind) {
        const box = document.getElementById(kind === 'power'
            ? 'power-custom-toggle' : 'custom-flow-toggle');
        if (!box) return;
        const layer = this.currentLayer;
        const on = !!layer && (layer.type || 'screen') === 'screen'
            && (kind === 'power' ? this.isCustomPower(layer) : this.isCustomFlow(layer));
        if (box.checked !== on) box.checked = on;
    }

    updateCustomFlowUI() {
        this._syncCustomModeBox('data');
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('custom-flow-controls');
            if (container) container.style.display = 'none';
            return;
        }
        // The editing predicate, not the pattern: while one overridden port is
        // open for redrawing the same controls (active port, clear, patterns)
        // are the tools of THAT edit, so the panel shows without the screen
        // ever leaving its automatic pattern.
        const isCustom = this.currentLayer && this.isCustomFlowEditing(this.currentLayer);
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
        this._syncCustomFillReadout('data');
    }

    isCustomPower(layer) {
        return !!layer && layer.powerFlowPattern === 'custom';
    }

    ensureCustomPowerState(layer) {
        if (!layer) return;
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (!layer.powerCustomIndex) layer.powerCustomIndex = 1;
    }

    // The way OUT of custom mode carries the amps rule (app-power.js, "the
    // amps rule"): a share past the circuit's amps holds only in custom
    // mode, so one still in place once the pattern has flipped back is
    // un-shared here - the app's own un-share (splitSplitterCircuits: the
    // runs back onto circuits of their own, pinned out of re-packing),
    // folded into the toggle's one history entry, and a toast says why.
    // Shares drawn against custom circuit numbers are not touched: they go
    // dormant with the drawn paths (the id-space doctrine) and come back
    // with custom mode, where they are allowed. Only a share the auto
    // screen actually reads can be past the amps here.
    // Idempotent like its data twin above: a call that changes nothing only
    // re-syncs the controls; only screens whose mode differs are written,
    // and a locked one stays as it is and is named.
    toggleCustomPowerMode(enabled) {
        if (!this.currentLayer) return;
        enabled = !!enabled;
        const { change, locked } = this._customToggleScope('power', enabled);
        this._showLockedError(locked);
        if (change.length === 0) {
            this.syncCustomModeControls();
            return;
        }
        const undone = [];
        change.forEach(layer => {
            if (enabled) {
                if (layer.powerFlowPattern && layer.powerFlowPattern !== 'custom') {
                    layer.lastPowerFlowPattern = layer.powerFlowPattern;
                }
                layer.powerFlowPattern = 'custom';
                layer.powerCustomPath = true;
                this.ensureCustomPowerState(layer);
            } else {
                layer.powerFlowPattern = this._customRestorePattern(layer, 'power', change);
                layer.powerCustomPath = false;
                const over = this.overSharedCircuits(layer);
                if (over.length) {
                    this.splitSplitterCircuits(layer, over.map(o => o.num),
                                               null, { silent: true });
                    undone.push({ layer, over });
                }
            }
        });
        if (!enabled) {
            this.powerCustomSelection.clear();
        }
        this.saveState('Power Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updateLayers(this._persistWith(change));
        this.updatePowerCapacityDisplay();
        this.syncCustomModeControls();
        if (undone.length) {
            this._circuitTailCache = null;
            this._rebuildAfterGesture(() => {
                this.refreshSplitterPanel();
                this.refreshSocaRuns();
                this.refreshDistroPanel();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
            const first = undone[0].over[0];
            const count = undone.reduce((s, u) => s + u.over.length, 0);
            const who = undone.length > 1 || this.getSelectedLayers().length > 1
                ? `${undone[0].layer.name}: ` : '';
            this._toast(
                `Custom mode off - ${who}${this._runListText(first.runIds)
                    .toLowerCase()} drew ${first.load.amps.toFixed(1)} A on a `
                + `${+first.load.cap.toFixed(1)} A circuit, so the share was `
                + 'undone'
                + (count > 1 ? ` (${count - 1} more like it)` : '')
                + '. A share past the amps holds only in custom mode.',
                false, 6000);
        }
        window.canvasRenderer.render();
    }

    updateCustomPowerUI() {
        this._syncCustomModeBox('power');
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('power-custom-controls');
            if (container) container.style.display = 'none';
            return;
        }
        // Editing predicate, not the pattern - same reason as the data twin.
        const isCustom = this.currentLayer && this.isCustomPowerEditing(this.currentLayer);
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
        this._syncCustomFillReadout('power');
    }

    // One screen's own grid address. Every cabinet SELECTION is keyed by
    // getScopedPanelKey instead (`${layerId}:${row},${col}`).
    getPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    // A per-screen row/col index (1.5 audit): this was a linear find, and the
    // Pixel Map selection resolves every selected key through it several
    // times per mouse move - 6 screens of 80x40 took ~112 ms a move.
    //
    // It can never hand back a stale panel. The index is keyed by the panels
    // ARRAY, so a rebuild (a new array) starts a new one; it is rebuilt when
    // the array was grown or cut in place; and it holds each address's SLOT,
    // not the panel object - a hit reads whatever panel is in that slot NOW
    // and checks its address, so a panel replaced in place is found as the
    // new object, and a slot whose panel moved address rebuilds the index.
    // A replacement that gives a slot a NEW address is announced with
    // _panelsReplaced(layer) by the code that makes it.
    getPanelByRowCol(layer, row, col) {
        if (!layer || !Array.isArray(layer.panels)) return null;
        const panels = layer.panels;
        const key = `${row},${col}`;
        for (let attempt = 0; attempt < 2; attempt++) {
            let index = attempt === 0 ? PANEL_INDEX.get(panels) : null;
            if (!index || index.len !== panels.length) {
                const map = new Map();
                // Backwards, so a duplicated address keeps the FIRST panel -
                // the one the find() this replaced returned.
                for (let i = panels.length - 1; i >= 0; i--) {
                    const p = panels[i];
                    if (p) map.set(`${p.row},${p.col}`, i);
                }
                index = { len: panels.length, map };
                PANEL_INDEX.set(panels, index);
                attempt = 1;
            }
            const slot = index.map.get(key);
            if (slot === undefined) return null;
            const hit = panels[slot];
            if (hit && hit.row === row && hit.col === col) return hit;
            // The slot's panel is not at this address any more: rebuild once.
        }
        return null;
    }

    // Panels were replaced in place on `layer` (same array, new objects that
    // may sit at other addresses): its row/col index starts again.
    _panelsReplaced(layer) {
        if (layer && Array.isArray(layer.panels)) PANEL_INDEX.delete(layer.panels);
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
     * row and column. Silently wrong, not partly working. (pixelMapSelection
     * moved to the same scoped key in 1.5 - see the Pixel Map section.)
     *
     * Each member converts the WORLD rect into its OWN frame:
     * _getLayerWorkspaceOffset is per-layer (canvas workspace + that layer's
     * Show Look delta), and rotation is undone per member the way
     * selectPixelMapPanelsInRect and canvas.js getPanelAt do it. Note the
     * members of one canvas already share an origin - _build_panels lays each
     * member's columns out from its own offset_x - so there is no second offset
     * to apply on top of that, and applying one would drag the peer's hit-test
     * off the wall.
     *
     * A LOCKED member's cabinets ARE selected: selecting is not changing a
     * screen (the owner's ruling, 2026-10-16), so the marquee picks them
     * without a word. The verb that would change them (Apply Pattern, the
     * fill) leaves them out and names the screen. Returns the locked members
     * the rect touched, for a caller that wants to know.
     */
    _selectPathPanelsInRect(ownerLayer, rect, selection) {
        selection.clear();
        const locked = [];
        if (!ownerLayer || !rect) return locked;
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
            const hit = member.panels.filter(panel => !panel.hidden
                && panel.x <= x2 && (panel.x + panel.width) >= x1
                && panel.y <= y2 && (panel.y + panel.height) >= y1);
            if (hit.length === 0) return;
            if (member.locked) locked.push(member);
            hit.forEach(panel => selection.add(this.getScopedPanelKey(member.id, panel)));
        });
        return locked;
    }

    // `layer` is the path's OWNER - the screen whose port is being drawn - and
    // its group decides how far the marquee reaches. canvas.js still passes
    // currentLayer. A selection only: a locked member's cabinets are picked
    // with no error (the verb names it). `opts` is kept for the callers.
    selectPanelsInRect(layer, rect, opts = {}) {
        if (!layer) return;
        if (!this.isCustomFlowEditing(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.customSelection);
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    // ---------- Pixel Map bulk-select (panel selection on the Pixel Map tab) ----------
    //
    // CROSS-SCREEN (the owner's ruling, 2026-10-16: "when i group screens i
    // cant select panels across screens for setting blanks or halfs etc." -
    // for any selected screens, grouped or not). pixelMapSelection holds
    // getScopedPanelKey keys, `${layerId}:${row},${col}`, the same address
    // customSelection uses: with two screens in play `${row},${col}` names
    // two cabinets at once. A marquee, a click or a Cmd/Ctrl-click reaches
    // every screen in getPixelMapScopeLayers, and the bulk verbs (Set Blank,
    // Restore, the half tiles) write each screen through its own server call
    // and record ONE undo step for the whole action.
    //
    // A LOCKED SCREEN stays unchanged until it is unlocked - but SELECTING
    // its cabinets is not changing it (the owner's ruling, 2026-10-16), so
    // every selection gesture (marquee, click, Cmd/Ctrl-click, Ctrl+A) picks
    // them without a word. The verb that would change them (Set Blank,
    // Restore, the half tiles, Alt-paint) leaves them alone and names the
    // screen in one error (_showLockedError); the other screens still go.

    // The screens a Pixel Map cabinet selection may reach: the current
    // screen, then every other selected screen. A grouped wall is reached
    // through the selection too - clicking or boxing any member on the
    // canvas selects the whole group - so a member left out of the selection
    // (picked alone in the Screens list) stays out, exactly as the ruling
    // reads: the selected screens. A hidden screen is not drawn and cannot
    // be clicked, so it is out of scope - except a hidden current screen
    // that is the ONLY screen in play, which keeps the single-screen case
    // exactly what it was (the getSelectionScopeLayers rule). A hidden
    // current screen used to be kept always, so a drag across the visible
    // screens of a selection swept up its invisible cabinets too.
    getPixelMapScopeLayers() {
        const out = [];
        const seen = new Set();
        const add = (l) => {
            if (!l || seen.has(l.id) || (l.type || 'screen') !== 'screen') return;
            seen.add(l.id);
            if (l.visible === false) return;
            out.push(l);
        };
        const cur = this.currentLayer;
        add(cur);
        if (this.selectedLayerIds && this.selectedLayerIds.size > 0) {
            (this.getSelectedLayers() || []).forEach(l => add(l));
        }
        if (cur && cur.visible === false && (cur.type || 'screen') === 'screen'
                && out.length === 0) {
            out.push(cur);
        }
        return out;
    }

    isPixelMapScopeLayer(layer) {
        if (!layer) return false;
        return this.getPixelMapScopeLayers().some(l => l.id === layer.id);
    }

    // One pixelMapSelection key back to its cabinet, or null. `scope` is a
    // Map of id -> layer (getPixelMapScopeLayers): a key naming a screen
    // that has left the selection resolves to nothing.
    _resolvePixelMapKey(key, scope) {
        if (typeof key !== 'string') return null;
        const sep = key.indexOf(':');
        if (sep < 0) return null;
        const layer = scope.get(parseInt(key.slice(0, sep), 10));
        if (!layer) return null;
        const [row, col] = key.slice(sep + 1).split(',').map(n => parseInt(n, 10));
        const panel = this.getPanelByRowCol(layer, row, col);
        return panel ? { layer, panel } : null;
    }

    // The live selection as {layer, panel} pairs, current screen first. A
    // key that no longer names a cabinet on a screen in scope (the screen
    // left the selection, was hidden or deleted) is simply not a hit, so
    // every reader - the counts, the highlight, the verbs - agrees on one
    // selection. READ-ONLY (1.5 audit): this runs from the render, the
    // overlay, the badge and renderLayers, where currentLayer and
    // selectedLayerIds can disagree mid-update, and pruning there dropped
    // keys that were about to be in scope again. The Set is pruned only on a
    // real selection change (_prunePixelMapSelection).
    _pixelMapSelectionHits() {
        const sel = this.pixelMapSelection;
        if (!sel || sel.size === 0) return [];
        const layers = this.getPixelMapScopeLayers();
        const scope = new Map(layers.map(l => [l.id, l]));
        const order = new Map(layers.map((l, i) => [l.id, i]));
        const hits = [];
        sel.forEach(key => {
            const hit = this._resolvePixelMapKey(key, scope);
            if (hit) hits.push(hit);
        });
        return hits.sort((a, b) => order.get(a.layer.id) - order.get(b.layer.id));
    }

    // Drop the keys that no longer name a cabinet on a screen in scope, so a
    // screen that leaves the selection (or is hidden) and comes back does
    // not bring its old cabinets back with it. Called on a real selection
    // change only, once currentLayer and selectedLayerIds agree.
    _prunePixelMapSelection() {
        const sel = this.pixelMapSelection;
        if (!sel || sel.size === 0) return;
        const scope = new Map(this.getPixelMapScopeLayers().map(l => [l.id, l]));
        [...sel].forEach(key => {
            if (!this._resolvePixelMapKey(key, scope)) sel.delete(key);
        });
    }

    // The cabinets under a world rect on every screen in scope, per screen.
    // Each screen converts the rect into its OWN frame (its canvas workspace
    // offset, then its rotation undone), as the single-screen marquee did.
    // Hidden ("blank") panels are included so they can be selected for bulk
    // restore via the sidebar / Alt+click action. Returns
    // { keys, locked }: the keys on every screen (a locked screen's cabinets
    // are selected - selecting is not changing), and the locked screens the
    // rect touched.
    _pixelMapPanelsInRect(rect) {
        const keys = [];
        const locked = [];
        const _r = window.canvasRenderer;
        this.getPixelMapScopeLayers().forEach(layer => {
            if (!Array.isArray(layer.panels)) return;
            const off = this._getLayerWorkspaceOffset(layer);
            let x1 = Math.min(rect.x1, rect.x2) - off.wx;
            let x2 = Math.max(rect.x1, rect.x2) - off.wx;
            let y1 = Math.min(rect.y1, rect.y2) - off.wy;
            let y2 = Math.max(rect.y1, rect.y2) - off.wy;
            // v0.9.3: if the screen is rotated, map the marquee back into the
            // screen's unrotated panel space (rotation is 90/180/270, so it
            // stays axis-aligned).
            if (_r && _r._unrotatePointForLayer) {
                const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                    .map(([x, y]) => _r._unrotatePointForLayer(x, y, layer));
                x1 = Math.min(...corners.map(c => c.x)); x2 = Math.max(...corners.map(c => c.x));
                y1 = Math.min(...corners.map(c => c.y)); y2 = Math.max(...corners.map(c => c.y));
            }
            const hit = layer.panels.filter(panel => panel.x <= x2 && (panel.x + panel.width) >= x1
                && panel.y <= y2 && (panel.y + panel.height) >= y1);
            if (hit.length === 0) return;
            if (layer.locked) locked.push(layer);
            hit.forEach(panel => keys.push(this.getScopedPanelKey(layer.id, panel)));
        });
        return { keys, locked };
    }

    // `layer` is kept for the existing callers and no longer limits the
    // reach - the scope does. A selection only, so a locked screen's
    // cabinets are picked with no error; `opts` is kept for the callers.
    selectPixelMapPanelsInRect(layer, rect, opts = {}) {
        if (!rect) return;
        this.pixelMapSelection.clear();
        const { keys } = this._pixelMapPanelsInRect(rect);
        keys.forEach(k => this.pixelMapSelection.add(k));
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    // The screen a cabinet belongs to, among the screens in scope. Identity
    // first (the click hands the panel straight out of a layer's array);
    // `panelLayer` names it outright when the caller knows it.
    _pixelMapPanelLayer(panel, panelLayer = null) {
        if (!panel) return null;
        const scope = this.getPixelMapScopeLayers();
        if (panelLayer) return scope.find(l => l.id === panelLayer.id) || null;
        return scope.find(l => Array.isArray(l.panels) && l.panels.includes(panel))
            || (this.currentLayer && this.getPanelByRowCol(this.currentLayer, panel.row, panel.col)
                ? this.currentLayer : null);
    }

    // A plain click on one cabinet: the selection becomes just that cabinet,
    // on a locked screen too - picking it is not changing it (1.4.1 picked
    // the screen and the cabinet quietly; 1.5 must as well).
    selectOnlyPixelMapPanel(panel, panelLayer = null) {
        const layer = this._pixelMapPanelLayer(panel, panelLayer);
        if (!layer) return;
        this.pixelMapSelection.clear();
        this.pixelMapSelection.add(this.getScopedPanelKey(layer.id, panel));
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    togglePixelMapPanelSelection(panel, panelLayer = null) {
        const layer = this._pixelMapPanelLayer(panel, panelLayer);
        if (!layer) return;
        this._prunePixelMapSelection();
        const key = this.getScopedPanelKey(layer.id, panel);
        if (this.pixelMapSelection.has(key)) {
            this.pixelMapSelection.delete(key);
        } else {
            this.pixelMapSelection.add(key);
        }
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    // Cmd/Ctrl+A while a cabinet selection is open (selectAllInView): every
    // cabinet of every screen in scope, blank ones included - the same set a
    // marquee over all of them builds, so a bulk restore can follow. A
    // locked screen's cabinets are selected too, with no error - the verb
    // that would change them names it.
    selectAllPixelMapPanels() {
        const layers = this.getPixelMapScopeLayers();
        if (layers.length === 0) return;
        this.pixelMapSelection.clear();
        layers.forEach(layer => {
            if (!Array.isArray(layer.panels) || layer.panels.length === 0) return;
            layer.panels.forEach(panel => this.pixelMapSelection.add(
                this.getScopedPanelKey(layer.id, panel)));
        });
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    clearPixelMapSelection() {
        if (!this.pixelMapSelection || this.pixelMapSelection.size === 0) return;
        this.pixelMapSelection.clear();
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The selected cabinets, on every screen in scope, current screen first.
    getPixelMapSelectedPanels() {
        return this._pixelMapSelectionHits().map(hit => hit.panel);
    }

    // The cabinets a bulk verb was handed, sorted onto their screens in
    // scope order. A panel that is in no screen's array is matched by id on
    // the current screen - the single-screen assumption every older caller
    // was written against. Locked screens are split out for the error:
    // `locked` the screens, `lockedGroups` their share of the panels, so a
    // verb can name a locked screen only when it would really change it.
    _pixelMapPanelsByLayer(panels) {
        const want = new Set(panels || []);
        const groups = [];
        const locked = [];
        const lockedGroups = [];
        const placed = new Set();
        const layers = this.getPixelMapScopeLayers();
        (this.project && this.project.layers || []).forEach(l => {
            if (l && !layers.includes(l) && (l.type || 'screen') === 'screen') layers.push(l);
        });
        layers.forEach(layer => {
            if (!Array.isArray(layer.panels)) return;
            const mine = layer.panels.filter(p => want.has(p) && !placed.has(p));
            if (mine.length === 0) return;
            mine.forEach(p => placed.add(p));
            if (layer.locked) { locked.push(layer); lockedGroups.push({ layer, panels: mine }); return; }
            groups.push({ layer, panels: mine });
        });
        const strays = (panels || []).filter(p => p && !placed.has(p));
        const cur = this.currentLayer;
        if (strays.length && cur && Array.isArray(cur.panels)) {
            const ids = new Set(strays.map(p => p.id));
            const mine = cur.panels.filter(p => ids.has(p.id));
            if (mine.length) {
                if (cur.locked) {
                    const lg = lockedGroups.find(x => x.layer === cur);
                    if (lg) mine.forEach(p => { if (!lg.panels.includes(p)) lg.panels.push(p); });
                    else { locked.push(cur); lockedGroups.push({ layer: cur, panels: mine }); }
                } else {
                    const g = groups.find(x => x.layer === cur);
                    if (g) mine.forEach(p => { if (!g.panels.includes(p)) g.panels.push(p); });
                    else groups.unshift({ layer: cur, panels: mine });
                }
            }
        }
        return { groups, locked, lockedGroups };
    }

    // One bulk verb's server calls: each screen through its own endpoint,
    // every rebuilt layer merged, then ONE history entry for the whole
    // action. The snapshot waits for the server's rebuilt layers (v0.10.8):
    // a half tile or a hide resizes / re-anchors cabinets and that rebuild
    // only happens server-side, so a snapshot taken before the merge pairs
    // the new flags with the old geometry. A screen whose call brought no
    // rebuilt layer back means no trustworthy snapshot, so none is taken -
    // the socket `layer_updated` event still reconciles the live state.
    async _pixelMapBulkPost(groups, route, bodyOf, reason, historyLabel) {
        let applied = 0;
        for (const g of groups) {
            try {
                const res = await fetch(`/api/layer/${g.layer.id}/panels/${route}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bodyOf(g)),
                });
                const data = await res.json();
                if (data && data.layer && this.applyServerLayer(data.layer, reason)) applied++;
            } catch (err) {
                console.error(`${reason} failed`, err);
            }
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        if (applied > 0 && applied === groups.length) this.saveState(historyLabel);
        return applied;
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

    // The half-tile verb, on every screen the panels sit on (see
    // _pixelMapBulkPost for the one undo step and the snapshot contract).
    async setPanelsHalfTileBulk(panels, halfTile) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const { groups, lockedGroups } = this._pixelMapPanelsByLayer(panels);
        // A locked screen keeps its cabinets as they are, and is named when
        // the verb would have changed one of them.
        const wouldChange = (p) => {
            const cur = p.halfTile || 'none';
            if (halfTile === 'none') return cur !== 'none';
            if (halfTile === 'auto') return cur === 'none';
            return cur !== halfTile;
        };
        this._showLockedError(lockedGroups
            .filter(g => g.panels.some(wouldChange)).map(g => g.layer));
        if (groups.length === 0) return;
        // For 'auto', vote across each screen's share of the selection: pick
        // the direction the majority of its panels would auto-detect to, then
        // apply that uniformly. Avoids a row of selected panels splitting into
        // different directions when one happens to be an interior panel. Each
        // screen votes against its own neighbours, so two separate screens
        // each get the edge they actually have.
        groups.forEach(g => {
            let resolved = halfTile;
            if (halfTile === 'auto') {
                let widthVotes = 0;
                let heightVotes = 0;
                g.panels.forEach(p => {
                    const d = this.autoDetectHalfDirection(g.layer, p);
                    if (d === 'width') widthVotes++;
                    else heightVotes++;
                });
                // Tie goes to 'height' (top/bottom is the more common case).
                resolved = widthVotes > heightVotes ? 'width' : 'height';
            }
            g.resolved = resolved;
        });
        // Apply locally so the canvas updates immediately while the POSTs are
        // in flight; the flags alone are enough to redraw at the old geometry.
        groups.forEach(g => g.panels.forEach(p => { p.halfTile = g.resolved; }));
        // A half tile moves cabinets: held to a Brompton processor's canvas
        // like any layer edit (refused = the flags are back as they were).
        if (typeof this._canvasGuardEdit === 'function' && !this._canvasGuardEdit()) return;
        if (window.canvasRenderer) window.canvasRenderer.render();
        await this._pixelMapBulkPost(groups, 'set_half_tile',
            g => ({ panels: g.panels.map(p => ({ id: p.id, halfTile: g.resolved })) }),
            'bulk_set_half_tile', 'Bulk Set Half-tile');
        sendClientLog && sendClientLog('bulk_set_half_tile', {
            layer_id: groups[0].layer.id,
            layer_ids: groups.map(g => g.layer.id),
            count: groups.reduce((s, g) => s + g.panels.length, 0),
            mode: halfTile,
        });
    }

    /**
     * Bulk hide/show panels, what the UI calls "Set Blank" (matching the
     * Alt+click behaviour, which toggles the per-panel `hidden` flag so the
     * cabinet disappears from the wall layout). On every screen the panels
     * sit on, as one undo step (_pixelMapBulkPost).
     */
    async setPanelsBlankBulk(panels, blank) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const targetHidden = !!blank;
        const { groups: all, lockedGroups } = this._pixelMapPanelsByLayer(panels);
        // Named only when the verb would have changed one of its cabinets.
        this._showLockedError(lockedGroups
            .filter(g => g.panels.some(p => !!p.hidden !== targetHidden)).map(g => g.layer));
        const groups = all
            .map(g => ({ layer: g.layer, panels: g.panels.filter(p => !!p.hidden !== targetHidden) }))
            .filter(g => g.panels.length > 0);
        if (groups.length === 0) return;
        // Apply locally so the canvas updates immediately while the server
        // calls are in flight.
        groups.forEach(g => g.panels.forEach(p => { p.hidden = targetHidden; }));
        // Showing cabinets can widen a processor's canvas span.
        if (typeof this._canvasGuardEdit === 'function' && !this._canvasGuardEdit()) return;
        if (window.canvasRenderer) window.canvasRenderer.render();
        // v0.10.8.1: hiding a panel re-anchors any neighbouring half-tile,
        // and that rebuild only happens server-side - same contract as the
        // half-tile verb above.
        await this._pixelMapBulkPost(groups, 'set_hidden',
            g => ({ panels: g.panels.map(p => ({ id: p.id, hidden: targetHidden })) }),
            'bulk_set_blank', 'Bulk Set Blank');
        sendClientLog && sendClientLog('bulk_set_blank', {
            layer_id: groups[0].layer.id,
            layer_ids: groups.map(g => g.layer.id),
            count: groups.reduce((s, g) => s + g.panels.length, 0),
            hidden: targetHidden,
        });
    }

    /**
     * Update the sidebar bulk-action panel based on current selection.
     * Shows count + action buttons when at least one panel is selected,
     * hides when empty. The count is every selected cabinet on every screen.
     */
    updatePixelMapBulkActionUI() {
        const panel = document.getElementById('pixel-map-bulk-actions');
        if (!panel) return;
        const count = this._pixelMapSelectionHits().length;
        const countEl = document.getElementById('pixel-map-bulk-count');
        // Wrap label too so we can fix pluralization without rebuilding markup.
        const labelEl = document.getElementById('pixel-map-bulk-label');
        if (count > 0) {
            panel.style.display = 'block';
            if (countEl) countEl.textContent = count.toLocaleString('en-US');
            if (labelEl) labelEl.textContent = count === 1 ? 'panel' : 'panels';
        } else {
            panel.style.display = 'none';
        }
    }

    // Power's half of the marquee. Same scoping rule, same owner semantics -
    // see _selectPathPanelsInRect.
    selectPowerPanelsInRect(layer, rect, opts = {}) {
        if (!layer) return;
        if (!this.isCustomPowerEditing(layer)) return;
        this._selectPathPanelsInRect(layer, rect, this.powerCustomSelection);
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }
}

for (const k of Object.getOwnPropertyNames(_PixelSelect.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PixelSelect.prototype, k));
    }
}
