// app-merge-runs: several data ports picked on the wall and redrawn as ONE
// for LEDRasterApp. Owns the port picks (Shift+click a run, Shift+drag a
// box), the "Redraw ports 51-54 as one" menu entry, and the redraw session
// that follows it: open, drawn, kept (Enter) or put back (Esc).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _MergeRuns {

    // ── The rulings (the owner, 2026-11-02) ───────────────────────────────
    //
    // "i need to be able to click multiple ports and redraw them so 51-54 i
    // want to be able to redraw all of those as one port":
    //
    //   picking    Shift+click a run in the Data view picks it, Shift+click
    //              again un-picks it; Shift+drag a box from a run picks
    //              every port the box touches. Picked runs wear the run
    //              underlay. One screen's ports at a time: a pick on another
    //              screen starts over there. A plain click or Esc drops them.
    //   redraw     with 2+ picked, right-click offers "Redraw ports 51-54
    //              as one" (a list where they are not consecutive). The
    //              picked ports' cabinets are freed and ONE new path is
    //              drawn on the first number, with every rule the single
    //              redraw has: the port's capacity, a cabinet another port
    //              holds refused out loud, the run lit until it is done.
    //   numbers    the new port keeps the lowest picked number; the others
    //              go and every later port closes up (54 ports become 51),
    //              on automatic and custom screens alike. Pins follow: the
    //              merged port keeps the first port's socket, the removed
    //              ports' sockets are released, later ports keep their
    //              sockets under their new numbers (/merge on the server).
    //   done       Enter keeps the drawing, and so does drawing every freed
    //              cabinet; Esc puts everything back with no change. Kept,
    //              the whole thing is ONE undo step.
    //   locked     a locked screen is refused with the locked error.
    //
    // On an AUTOMATIC screen the freed cabinets are held out of the walk
    // while the session is open (_mergeHeldPanels, read by _overrideClaims),
    // otherwise the walk would take them straight back and every click on
    // them would be refused as wired. Once the session ends, any freed
    // cabinet left undrawn goes back to the walk, the way a single redraw
    // lets go of a cabinet. On a CUSTOM screen a cabinet off every path is
    // simply unwired, so nothing needs holding there.

    // The picked port numbers on `layer`, ascending; [] for any other screen.
    portPicksFor(layer) {
        const p = this._portPicks;
        if (!p || !layer || p.layerId !== layer.id) return [];
        return p.nums.slice().sort((a, b) => a - b);
    }

    // Shift+click: pick the run, or un-pick it when it was picked. `run` is
    // { layerId, num } (the owner whose numbering the port lives in).
    togglePortPick(run) {
        if (!run || !run.num) return;
        const p = this._portPicks;
        if (!p || p.layerId !== run.layerId) {
            this._portPicks = { layerId: run.layerId, nums: [run.num] };
        } else if (p.nums.includes(run.num)) {
            p.nums = p.nums.filter(n => n !== run.num);
            if (p.nums.length === 0) this._portPicks = null;
        } else {
            p.nums.push(run.num);
        }
        this._portPicksChanged('toggle');
    }

    // Shift+drag: every port of the anchor's screen the box touches joins
    // the picks (a box adds, it never un-picks).
    pickPortsInRect(anchor, rect) {
        if (!anchor || !rect) return;
        const nums = this.portsInWorldRect(anchor.layerId, rect);
        if (!nums.includes(anchor.num)) nums.push(anchor.num);
        const p = this._portPicks;
        const base = (p && p.layerId === anchor.layerId) ? p.nums : [];
        const next = base.slice();
        nums.forEach(n => { if (!next.includes(n)) next.push(n); });
        this._portPicks = { layerId: anchor.layerId, nums: next };
        this._portPicksChanged('box');
    }

    clearPortPicks() {
        if (!this._portPicks) return;
        this._portPicks = null;
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    _portPicksChanged(how) {
        const p = this._portPicks;
        sendClientLog('port_picks', {
            how, layerId: p ? p.layerId : null, nums: p ? this.portPicksFor({ id: p.layerId }) : [],
        });
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The port numbers of `ownerId`'s runs with a cabinet inside the world
    // rect (the canvas's unmirrored world space, as every marquee). Each
    // screen converts the rect into its own frame the way
    // _selectPathPanelsInRect does: the workspace offset, then rotation.
    portsInWorldRect(ownerId, rect) {
        const r = window.canvasRenderer;
        if (!this.project || !rect) return [];
        const map = this._dockBuildDataMap();
        const out = new Set();
        (this.project.layers || []).forEach(layer => {
            if (!layer || layer.visible === false || !Array.isArray(layer.panels)) return;
            if ((layer.type || 'screen') !== 'screen') return;
            const off = this._getLayerWorkspaceOffset(layer);
            let x1 = Math.min(rect.x1, rect.x2) - off.wx;
            let x2 = Math.max(rect.x1, rect.x2) - off.wx;
            let y1 = Math.min(rect.y1, rect.y2) - off.wy;
            let y2 = Math.max(rect.y1, rect.y2) - off.wy;
            if (r && typeof r._unrotatePointForLayer === 'function') {
                const c = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                    .map(([x, y]) => r._unrotatePointForLayer(x, y, layer));
                x1 = Math.min(...c.map(q => q.x)); x2 = Math.max(...c.map(q => q.x));
                y1 = Math.min(...c.map(q => q.y)); y2 = Math.max(...c.map(q => q.y));
            }
            layer.panels.forEach(panel => {
                if (panel.hidden) return;
                if (panel.x > x2 || panel.x + panel.width < x1
                        || panel.y > y2 || panel.y + panel.height < y1) return;
                const run = map.get(panel);
                if (run && run.ownerId === ownerId) out.add(run.portNum);
            });
        });
        return [...out].sort((a, b) => a - b);
    }

    // "51-54" for consecutive numbers, "51, 53, 54" otherwise.
    _portNumbersText(nums) {
        const s = nums.slice().sort((a, b) => a - b);
        const consecutive = s.every((n, i) => i === 0 || n === s[i - 1] + 1);
        return (consecutive && s.length > 1) ? `${s[0]}-${s[s.length - 1]}` : s.join(', ');
    }

    // The right-click entry: armed in the Data view on a run of the screen
    // the picks belong to, with two or more picked. Null everywhere else.
    _prepareMergeRunsMenu(x, y) {
        const r = window.canvasRenderer;
        if (!r || !r.canvas || r.viewMode !== 'data-flow' || this._mergeRedraw) return null;
        const p = this._portPicks;
        if (!p || p.nums.length < 2) return null;
        const rect = r.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
        const worldY = ((y - rect.top) - r.panY) / r.zoom;
        const worldX = r._unmirrorWorldX(((x - rect.left) - r.panX) / r.zoom, worldY);
        const run = this.runAtPoint(worldX, worldY);
        if (!run || run.kind !== 'data' || run.layer.id !== p.layerId) return null;
        const owner = run.layer;
        const nums = this.portPicksFor(owner);
        return {
            label: `Redraw ports ${this._portNumbersText(nums)} as one`,
            title: `Free the cabinets of these ports and draw them as one port, `
                + `numbered ${nums[0]}; the ports after it close up. Click the `
                + 'cabinets in order. Enter keeps it, Esc puts the ports back.',
            run: () => this.beginMergeRedraw(owner, nums),
        };
    }

    // The cabinets `owner`'s ports `nums` carry right now: [{layer, panel}].
    _mergePickedCabinets(owner, nums) {
        const map = this._dockBuildDataMap();
        const out = [];
        (this.project.layers || []).forEach(l => (l.panels || []).forEach(panel => {
            const run = map.get(panel);
            if (run && run.ownerId === owner.id && nums.includes(run.portNum)) {
                out.push({ layer: l, panel });
            }
        }));
        return out;
    }

    // Open the session: renumber the screen, free the picked cabinets, pin
    // the cards in step, and open the first number for drawing.
    beginMergeRedraw(owner, nums) {
        if (!owner || this._mergeRedrawLive()) return false;
        const picks = [...new Set((nums || []).map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1))].sort((a, b) => a - b);
        if (picks.length < 2) return false;
        const freed = this._mergePickedCabinets(owner, picks);
        // A locked screen stays unchanged (the owner's standing rule): the
        // owner, or any screen a picked port's cabinets sit on.
        const locked = new Map();
        if (this._layerLocked(owner)) locked.set(owner.id, owner);
        freed.forEach(h => { if (this._layerLocked(h.layer)) locked.set(h.layer.id, h.layer); });
        if (locked.size) {
            this._showLockedError([...locked.values()]);
            sendClientLog('merge_runs_refused', { layerId: owner.id, why: 'locked' });
            return false;
        }
        if (typeof this._mirrorRefused === 'function' && this._mirrorRefused(owner)) return false;
        if (this._overrideEditing) this.endOverrideEdit();
        this._flushPendingSaveState();
        const baseEntry = (this.history && this.history[this.historyIndex]) || null;
        const pullBefore = typeof this._pullLiveRowKeys === 'function'
            ? this._pullLiveRowKeys() : null;

        const first = picks[0];
        const removed = picks.slice(1);
        const shift = n => n - removed.filter(r => r < n).length;
        const custom = this.isCustomFlow(owner);
        this.ensureCustomFlowState(owner);
        const old = owner.customPortPaths || {};
        const paths = {};
        if (custom) {
            // Every path is the screen's own: the picked ones go, the rest
            // close up, and the first number starts empty.
            Object.keys(old).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { paths[k] = old[k]; return; }
                if (picks.includes(n)) return;
                paths[shift(n)] = old[k];
            });
        } else {
            // Only the overrides are live; a drawing left from an earlier
            // custom spell stays where it was, unused.
            const ovr = this.getOverrideNums(owner, 'data');
            Object.keys(old).forEach(k => {
                const n = parseInt(k, 10);
                if (Number.isFinite(n) && (ovr.includes(n) || picks.includes(n))) return;
                paths[k] = old[k];
            });
            const next = [first];
            ovr.forEach(n => {
                if (picks.includes(n)) return;
                paths[shift(n)] = old[n];
                next.push(shift(n));
            });
            owner.customPortOverrides = next.sort((a, b) => a - b);
        }
        paths[first] = [];
        owner.customPortPaths = paths;
        owner.customPortIndex = first;
        // A port's typed name follows its number.
        ['portLabelOverridesPrimary', 'portLabelOverridesReturn'].forEach(key => {
            const labels = owner[key];
            if (!labels || typeof labels !== 'object') return;
            const out = {};
            Object.keys(labels).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { out[k] = labels[k]; return; }
                if (removed.includes(n)) return;
                out[shift(n)] = labels[k];
            });
            owner[key] = out;
        });
        if (this.customSelection) this.customSelection.clear();
        this._portPicks = null;
        this._mergeRedraw = {
            layerId: owner.id,
            num: first,
            picks,
            removed,
            custom,
            held: new Set(freed.map(h => this.getScopedPanelKey(h.layer.id, h.panel))),
            baseEntry,
            ready: false,
        };
        if (pullBefore) this._dropPullEditsGoneWith(pullBefore);
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        sendClientLog('merge_runs_begin', {
            layerId: owner.id, picks, custom, freed: freed.length,
        });

        const open = () => {
            const s = this._mergeRedraw;
            if (!s || s.layerId !== owner.id || s.ready) return;
            const live = (this.project.layers || []).find(l => l.id === owner.id) || owner;
            // The session's first history entry; every click after it is
            // folded into one step when the drawing is kept.
            this._activateRunForEdit(live, 'data', first, 'Redraw Ports As One');
            s.ready = true;
            if (s.cancelWhenReady) {
                this.cancelMergeRedraw(typeof s.cancelWhenReady === 'string'
                    ? s.cancelWhenReady : null);
                return;
            }
            if (typeof this._toast === 'function') {
                this._toast(`Draw port ${first}: click the cabinets in order. `
                    + `Enter keeps it, Esc puts ports ${this._portNumbersText(picks)} back.`,
                    false, 6000);
            }
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const pins = (this.project.port_assignments && this.project.port_assignments.pins) || [];
        const pinned = pins.some(p => p && String(p.layerId) === String(owner.id));
        if (pinned && typeof this._assignmentRequest === 'function') {
            this._assignmentRequest('/api/port-assignments/merge', 'POST',
                { layerId: owner.id, removed: removed.map(n => n - 1) }, null, null)
                .then(open, open);
        } else {
            open();
        }
        return true;
    }

    // The open session, or null. One that undo has walked back past its
    // first step (or whose screen is gone) is over: the model it drew on is
    // no longer there.
    _mergeRedrawLive() {
        const s = this._mergeRedraw;
        if (!s) return null;
        const owner = (this.project && this.project.layers || []).find(l => l.id === s.layerId);
        let dead = !owner;
        if (!dead && s.ready) {
            const idx = s.baseEntry ? this.history.indexOf(s.baseEntry) : -1;
            dead = idx < 0 || this.historyIndex <= idx;
        }
        if (dead) {
            this._mergeRedraw = null;
            return null;
        }
        return s;
    }

    // Is the session open on this owner (and this number, when given)?
    _mergeRedrawOn(owner, num = null) {
        const s = this._mergeRedrawLive();
        return !!(s && owner && s.layerId === owner.id && (num === null || s.num === num));
    }

    // The freed cabinets the automatic walk must leave alone while the
    // session is open, among `scope` (the walking screen's path scope).
    _mergeHeldPanels(scope) {
        const s = this._mergeRedraw;
        if (!s || s.custom || !s.held || s.held.size === 0) return [];
        if (!(scope || []).some(m => m && m.id === s.layerId)) return [];
        if (!this._mergeRedrawLive()) return [];
        const out = [];
        scope.forEach(m => (m && m.panels || []).forEach(p => {
            if (s.held.has(this.getScopedPanelKey(m.id, p))) out.push(p);
        }));
        return out;
    }

    // The freed cabinets not drawn yet, on `layer` (for the canvas's ring).
    mergeFreedPanels(layer) {
        const s = this._mergeRedraw;
        if (!s || !layer || !s.held || !s.ready) return [];
        const owner = (this.project.layers || []).find(l => l.id === s.layerId);
        if (!owner) return [];
        const drawn = new Set(((owner.customPortPaths || {})[s.num] || [])
            .map(e => this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e)));
        return (layer.panels || []).filter(p => {
            const k = this.getScopedPanelKey(layer.id, p);
            return s.held.has(k) && !drawn.has(k);
        });
    }

    // After every step the session's path takes: once every freed cabinet
    // is on it there is nothing left to draw, and the drawing is kept.
    _mergeRedrawAfterStep(owner) {
        const s = this._mergeRedrawLive();
        if (!s || !s.ready || !owner || owner.id !== s.layerId) return;
        const drawn = new Set(((owner.customPortPaths || {})[s.num] || [])
            .map(e => this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e)));
        for (const k of s.held) if (!drawn.has(k)) return;
        this.finishMergeRedraw();
    }

    // Keep the drawing: the session's steps fold into ONE history entry.
    // Nothing drawn is nothing to keep - that is the same as Esc.
    finishMergeRedraw() {
        const s = this._mergeRedrawLive();
        if (!s || !s.ready) return false;
        const owner = (this.project.layers || []).find(l => l.id === s.layerId);
        const path = ((owner && owner.customPortPaths) || {})[s.num] || [];
        if (path.length === 0) {
            this.cancelMergeRedraw(`Nothing was drawn, so ports ${this._portNumbersText(s.picks)} stay as they were.`);
            return false;
        }
        this._mergeRedraw = null;
        const idx = this.history.indexOf(s.baseEntry);
        if (idx >= 0) {
            this.history = this.history.slice(0, idx + 1);
            this.historyIndex = idx;
        }
        const ed = this._overrideEditing;
        if (ed && ed.kind === 'data' && ed.layerId === owner.id) this._overrideEditing = null;
        if (this.customSelection) this.customSelection.clear();
        this.saveState('Redraw Ports As One');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        this.updatePortCapacityDisplay();
        this.updateCustomFlowUI();
        this.updatePortLabelEditor();
        if (typeof this.updateUI === 'function') this.updateUI();
        sendClientLog('merge_runs_kept', {
            layerId: owner.id, num: s.num, picks: s.picks, drawn: path.length,
        });
        if (typeof this._toast === 'function') {
            this._toast(`Ports ${this._portNumbersText(s.picks)} are now port ${s.num}.`, false, 4000);
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // Put everything back: the project as it was before the session, and
    // the session's history entries gone, as if it never happened. Undo's
    // own restore does the work (the screens, the pins on the server).
    cancelMergeRedraw(message = null) {
        const s = this._mergeRedrawLive();
        if (s && !s.ready) {
            // The cards are still being renumbered on the server; putting
            // the project back under that reply would lose the race. The
            // session opens and is put back the moment it lands.
            s.cancelWhenReady = message || true;
            return true;
        }
        this._mergeRedraw = null;
        if (!s) return false;
        const ed = this._overrideEditing;
        if (ed && ed.kind === 'data' && ed.layerId === s.layerId) this._overrideEditing = null;
        if (this.customSelection) this.customSelection.clear();
        const idx = s.baseEntry ? this.history.indexOf(s.baseEntry) : -1;
        if (s.ready && idx >= 0 && this.historyIndex > idx) {
            // Undo from the session's first entry lands on the one before
            // it; the entries after it are then forgotten (no redo).
            this.history = this.history.slice(0, idx + 2);
            this.historyIndex = idx + 1;
            this.undo();
            this.history = this.history.slice(0, idx + 1);
        }
        sendClientLog('merge_runs_cancelled', { layerId: s.layerId, picks: s.picks });
        if (message && typeof this._toast === 'function') this._toast(message, false, 4000);
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }
}

for (const k of Object.getOwnPropertyNames(_MergeRuns.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_MergeRuns.prototype, k));
    }
}
