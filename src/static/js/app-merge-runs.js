// app-merge-runs: several data ports picked on the wall and redrawn as ONE
// for LEDRasterApp. Owns the port picks (Shift+click a run, Shift+drag a
// box, Alt+drag across runs), the "Redraw ports 51-54 as one" menu entry,
// and the redraw session that follows it: open, drawn, kept (Enter) or put
// back (Esc). Also owns closing the port numbers up when ports go away
// (_closeUpPorts), the one path the redraw and a shrinking wall share
// (trimPortsOffWall).
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
    //              every port the box touches. Alt+drag across runs picks
    //              every port it crosses, the way Alt+drag sweeps circuits
    //              in Power (canvas-input's armed Alt+press; released
    //              inside the click threshold it is still the Alt+click
    //              that redraws one port). Picked runs wear the run
    //              underlay. One screen's ports at a time: a pick on another
    //              screen starts over there. A plain click or Esc drops them.
    //   redraw     with 2+ picked, right-click offers "Redraw ports 51-54
    //              as one" (a list where they are not consecutive). The
    //              picked ports' cabinets are freed and ONE new path is
    //              drawn on the first number, with every rule the single
    //              redraw has: the port's capacity, a cabinet another port
    //              holds refused out loud, the run lit until it is done.
    //              Only cabinets on the wall count (a cabinet a shrink left
    //              on a path is no cabinet), and picks that together hold
    //              more than one port takes are refused before anything is
    //              freed, with the "is full" toast's own figures.
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

    // Alt+drag: the sweep adds every port of the anchor's screen it crosses
    // (a sweep adds, it never un-picks). `anchor` is { ownerId, num }, the
    // run the Alt+press came down on, the shape the Power sweep arms with;
    // `nums` the ports under the cursor since the last move. A port of
    // another screen never joins: the sweep never jumps walls.
    sweepPortPicks(anchor, nums) {
        if (!anchor || !anchor.num) return;
        const p = this._portPicks;
        const next = (p && p.layerId === anchor.ownerId) ? p.nums.slice() : [];
        const before = next.length;
        [anchor.num].concat(nums || []).forEach(n => {
            if (Number.isFinite(n) && n >= 1 && !next.includes(n)) next.push(n);
        });
        if (p && p.layerId === anchor.ownerId && next.length === before) return;
        this._portPicks = { layerId: anchor.ownerId, nums: next };
        this._portPicksChanged('sweep');
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

    // One screen port as every data redraw and fill message names it:
    // "P15", its screen port number, the way the tray numbers a screen's
    // ports. Never the socket's label beside it (QA, 1.6.0: "Filled ports 1
    // to P15" named one end by its socket and the other by its number).
    _portNumberText(num) {
        return `P${num}`;
    }

    // "P51-P54" for consecutive numbers, "P51, P53, P54" otherwise.
    _portNumbersText(nums) {
        const s = nums.slice().sort((a, b) => a - b);
        const consecutive = s.every((n, i) => i === 0 || n === s[i - 1] + 1);
        const p = n => this._portNumberText(n);
        return (consecutive && s.length > 1)
            ? `${p(s[0])}-${p(s[s.length - 1])}` : s.map(p).join(', ');
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
                + `numbered ${this._portNumberText(nums[0])}; the ports after it close up. Click the `
                + 'cabinets in order. Enter keeps it, Esc puts the ports back.',
            run: () => this.beginMergeRedraw(owner, nums),
        };
    }

    // The cabinets `owner`'s ports `nums` carry right now: [{layer, panel}].
    // Real cabinets on the wall only: a step a shrink left past the edge
    // names no cabinet, and until the server's echo rebuilds a shrunk
    // screen its old panels are still in the client's copy, so a cabinet
    // past the screen's rows or columns is left out here as well.
    _mergePickedCabinets(owner, nums) {
        const map = this._dockBuildDataMap();
        const out = [];
        (this.project.layers || []).forEach(l => (l.panels || []).forEach(panel => {
            const run = map.get(panel);
            if (run && run.ownerId === owner.id && nums.includes(run.portNum)
                    && this._panelOnWall(l, panel)) {
                out.push({ layer: l, panel });
            }
        }));
        return out;
    }

    // Is `panel` (or a path step, anything with row and col) inside
    // `layer`'s grid? A screen's cabinets are rows x columns; anything past
    // that came off the wall.
    _panelOnWall(layer, panel) {
        if (!layer || !panel) return false;
        const rows = Number(layer.rows), cols = Number(layer.columns);
        if (!Number.isFinite(rows) || !Number.isFinite(cols)) return true;
        const r = Number(panel.row), c = Number(panel.col);
        return r >= 0 && c >= 0 && r < rows && c < cols;
    }

    // Picks that together hold more than ONE port takes cannot be redrawn
    // as one: the message saying so, or null when they fit. The figures are
    // the "is full" toast's (customRunCapacity / customRunLoad, the port's
    // own badge): the limit of a port carrying all of them, against their
    // load, which on a rectangle processor is the rectangle around them.
    _mergeCapacityRefusal(owner, picks, freed) {
        if (!freed.length) return null;
        const cap = this.customRunCapacity(owner, 'data', freed.map(h => h.panel));
        if (!cap.known) return null;
        const load = this.customRunLoad(owner, 'data', freed);
        if (load <= cap.limit + 1e-6) return null;
        const sized = this._customRunSizing(owner, 'data', freed.map(h => h.layer), cap);
        const ports = `Ports ${this._portNumbersText(picks)}`;
        const n = freed.length;
        const px = v => Math.round(v).toLocaleString('en-US');
        if (!sized.mixed && n > sized.count) {
            return `${ports} hold ${n} panels together, and one port takes ${sized.describe}. `
                + 'Pick fewer ports to redraw as one.';
        }
        if (!sized.mixed) {
            return `${ports} hold ${n} panels, but one port pays for the whole rectangle around `
                + `them: ${px(load)} px, and one port takes ${cap.at}. Pick fewer ports to redraw as one.`;
        }
        return `${ports} carry ${px(load)} px together, and one port takes ${cap.at}. `
            + 'Pick fewer ports to redraw as one.';
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
        // More than one port takes: refused before anything is freed.
        const full = this._mergeCapacityRefusal(owner, picks, freed);
        if (full) {
            if (typeof this._toast === 'function') this._toast(full, true, 8000);
            sendClientLog('merge_runs_refused', {
                layerId: owner.id, why: 'capacity', picks, cabinets: freed.length,
            });
            return false;
        }
        if (this._overrideEditing) this.endOverrideEdit();
        this._flushPendingSaveState();
        const baseEntry = (this.history && this.history[this.historyIndex]) || null;
        const pullBefore = typeof this._pullLiveRowKeys === 'function'
            ? this._pullLiveRowKeys() : null;

        const first = picks[0];
        const removed = picks.slice(1);
        const custom = this.isCustomFlow(owner);
        // The removed numbers go and the ports after them close up (the
        // path a shrinking wall takes too); the first number then starts
        // empty, and on an automatic screen it is an override, so the walk
        // leaves its number to the drawing.
        this._closeUpPorts(owner, removed);
        owner.customPortPaths[first] = [];
        if (!custom) {
            const ovr = this.getOverrideNums(owner, 'data');
            if (!ovr.includes(first)) ovr.push(first);
            owner.customPortOverrides = ovr.sort((a, b) => a - b);
        }
        owner.customPortIndex = first;
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
                this._toast(`Draw port ${this._portNumberText(first)}: click the cabinets in order. `
                    + `Enter keeps it, Esc puts ports ${this._portNumbersText(picks)} back.`,
                    false, 6000);
            }
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        this._closeUpPortPins(owner, removed).then(open, open);
        return true;
    }

    // ── Closing the port numbers up ───────────────────────────────────────
    //
    // Ports that go away take their numbers with them, and every later
    // port of the screen closes up by the ports removed below it. ONE path
    // for every caller: Redraw-as-one (its removed numbers) and a wall that
    // shrank (the ports left with no cabinet, trimPortsOffWall).
    //   custom     every path is the screen's own: the removed ones go and
    //              the rest renumber.
    //   automatic  only the overrides are live: a removed one goes, the rest
    //              renumber, and the walk fills the numbers between. A
    //              drawing left from an earlier custom spell stays where it
    //              was, unused; one on a removed number goes.
    //              `dormantGone` (the shrink trim only): numbers of that
    //              unused drawing the trim emptied. Then the unused drawing
    //              closes up too, by those and the removed ports alike, so
    //              custom mode turned on later finds no holes where the
    //              wall shrank (QA, 1.6.0: holes at P45-47). Where a moved
    //              number would land on a live port's, the unused drawing is
    //              left where it was instead (only the emptied numbers go),
    //              so no part of it is overwritten.
    // A port's typed name follows its number, and the active port follows
    // its port. The cards follow on the server (_closeUpPortPins).
    // Returns the numbers removed, ascending.
    _closeUpPorts(owner, gone, dormantGone = null) {
        const clean = list => [...new Set((list || []).map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1))].sort((a, b) => a - b);
        const out = clean(gone);
        const outAll = clean(out.concat(dormantGone || []));
        if (!owner || outAll.length === 0) return out;
        const shift = n => n - out.filter(r => r < n).length;
        const shiftAll = n => n - outAll.filter(r => r < n).length;
        this.ensureCustomFlowState(owner);
        const old = owner.customPortPaths || {};
        const paths = {};
        if (this.isCustomFlow(owner)) {
            Object.keys(old).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { paths[k] = old[k]; return; }
                if (out.includes(n)) return;
                paths[shift(n)] = old[k];
            });
        } else {
            const ovr = this.getOverrideNums(owner, 'data');
            // The unused drawing closes up only where no moved number lands
            // on a live port's: otherwise it stays where it was, as before.
            const liveAfter = new Set(ovr.filter(n => !out.includes(n)).map(shift));
            const closes = !!dormantGone && Object.keys(old).every(k => {
                const n = parseInt(k, 10);
                return !Number.isFinite(n) || ovr.includes(n) || outAll.includes(n)
                    || !liveAfter.has(shiftAll(n));
            });
            Object.keys(old).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { paths[k] = old[k]; return; }
                if (ovr.includes(n) || (closes ? outAll : out).includes(n)) return;
                paths[closes ? shiftAll(n) : n] = old[k];
            });
            const next = [];
            ovr.forEach(n => {
                if (out.includes(n)) return;
                paths[shift(n)] = old[n];
                next.push(shift(n));
            });
            owner.customPortOverrides = next.sort((a, b) => a - b);
        }
        owner.customPortPaths = paths;
        owner.customPortIndex = Math.max(1, shift(parseInt(owner.customPortIndex, 10) || 1));
        ['portLabelOverridesPrimary', 'portLabelOverridesReturn'].forEach(key => {
            const labels = owner[key];
            if (!labels || typeof labels !== 'object') return;
            const moved = {};
            Object.keys(labels).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { moved[k] = labels[k]; return; }
                if (out.includes(n)) return;
                moved[shift(n)] = labels[k];
            });
            owner[key] = moved;
        });
        return out;
    }

    // The cards in step with _closeUpPorts: the removed ports' pins are
    // released and every later pin rides its port to the new number
    // (port_assignment.merge_pins via /merge). A promise that settles once
    // the server has answered, at once for a screen with nothing pinned;
    // it resolves true when pins were sent.
    _closeUpPortPins(owner, removed) {
        const pins = (this.project && this.project.port_assignments
            && this.project.port_assignments.pins) || [];
        const pinned = !!owner && pins.some(p => p && String(p.layerId) === String(owner.id));
        if (!pinned || !(removed || []).length || typeof this._assignmentRequest !== 'function') {
            return Promise.resolve(false);
        }
        return this._assignmentRequest('/api/port-assignments/merge', 'POST',
            { layerId: owner.id, removed: removed.map(n => n - 1) }, null, null)
            .then(() => true);
    }

    // ── A wall that shrinks (the owner, 2026-11-02) ───────────────────────
    //
    // A show drawn 90 cabinets wide and cut to 85 kept columns 85-89 on its
    // drawn ports: cabinets that no longer exist, a port standing wholly on
    // them, its number a hole in the run. The ruling: when a wall shrinks
    // (columns or rows, typed, by Size by Wall Dimensions, or through its
    // group), every drawn data port drops the cabinets that fell off; a
    // port left with none is removed and the ports after it close up the
    // way Redraw-as-one closes them (_closeUpPorts, the cards through
    // _closeUpPortPins). A show saved in that state is repaired the same
    // way when it is opened (`load`), where an override with nothing drawn
    // goes too: outside an open redraw it is only a number held empty.
    //
    // Off the wall means past the grid of the screen a step names (its own,
    // or a group peer's). Every layer commit runs through updateLayers,
    // which calls this, so the trim rides the shrink's own PUT and undo
    // step. A screen whose steps are all on the wall is not touched, so
    // the pass changes nothing the second time. A locked screen stays as
    // it is (logged), and a mirror's map is its source's.
    //
    // Power rides the same pass (app-power.js _trimCircuitsOffWall, the
    // owner's ruling of the same day: trim, and leave the hole): the drawn
    // circuits drop the cabinets that fell off, a circuit left with none
    // goes and the others keep their numbers. Its sentences join this
    // toast; the data ports are not touched by it.
    //
    // A screen that was LOCKED when its show was opened is left as it is
    // then; it is remembered (_portRepairPending) and gets the open's
    // repair, empty overrides included, the moment it is unlocked
    // (setLockOnSelected asks portRepairPending). Before that only the
    // shrink's half ran, at the next edit, and an empty override stayed a
    // hole until the show was opened again (QA, 1.6.0).
    //
    // Returns the screens it changed.
    trimPortsOffWall({ load = false } = {}) {
        // A show being opened is trimmed once, on the server's copy (the
        // load passes `load`); a layer save before then leaves it be.
        if (load) {
            this._projectOpening = false;
            this._portRepairPending = new Set();
        } else if (this._projectOpening) return [];
        if (!this.project || !Array.isArray(this.project.layers)) return [];
        const screens = this.project.layers
            .filter(l => l && (l.type || 'screen') === 'screen');
        const byId = new Map(screens.map(l => [String(l.id), l]));
        const onWall = (owner, e) => {
            if (!e || typeof e !== 'object') return true;
            const target = byId.get(String(this.getPathEntryLayerId(owner, e)));
            // A step naming a screen that is gone is the server's prune.
            return !target || this._panelOnWall(target, e);
        };
        const pending = this._portRepairPending || new Set();
        const plans = [];
        screens.forEach(owner => {
            const old = owner.customPortPaths;
            if (!old || typeof old !== 'object') return;
            if (typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(owner)) return;
            // The open's repair: on the open itself, or on a screen that
            // was locked then and is not any more.
            const opening = load || pending.has(String(owner.id));
            const custom = this.isCustomFlow(owner);
            const ovr = custom ? [] : this.getOverrideNums(owner, 'data');
            const live = n => custom || ovr.includes(n);
            const trimmed = {};
            let cut = 0;
            Object.keys(old).forEach(k => {
                const path = old[k];
                if (!Array.isArray(path)) return;
                const kept = path.filter(e => onWall(owner, e));
                if (kept.length === path.length) return;
                trimmed[k] = kept;
                cut += path.length - kept.length;
            });
            const gone = Object.keys(trimmed).map(k => parseInt(k, 10))
                .filter(n => Number.isFinite(n) && live(n) && trimmed[n].length === 0);
            // The unused drawing an automatic screen kept from a custom
            // spell: its numbers the trim emptied close up with it.
            const dormantGone = Object.keys(trimmed).map(k => parseInt(k, 10))
                .filter(n => Number.isFinite(n) && !live(n) && trimmed[n].length === 0);
            if (opening) {
                ovr.forEach(n => {
                    const path = trimmed[n] || old[n];
                    if (!gone.includes(n) && !(Array.isArray(path) && path.length)) gone.push(n);
                });
            }
            if (!cut && !gone.length) {
                pending.delete(String(owner.id));
                return;
            }
            if (this._layerLocked(owner)) {
                if (opening) pending.add(String(owner.id));
                sendClientLog('ports_off_wall_locked', { layerId: owner.id, cut, ports: gone });
                return;
            }
            pending.delete(String(owner.id));
            plans.push({ owner, trimmed, gone: gone.sort((a, b) => a - b),
                dormantGone, cut, live, opening });
        });
        this._portRepairPending = pending;
        const power = (typeof this._trimCircuitsOffWall === 'function')
            ? this._trimCircuitsOffWall({ load, onWall }) : { layers: [], notes: [] };
        const sayAll = (notes) => {
            if (notes.length && typeof this._toast === 'function') {
                this._toast(notes.join(' '), false, 8000);
            }
        };
        if (!plans.length) {
            sayAll(power.notes);
            return power.layers;
        }

        const closing = plans.some(p => p.gone.length);
        const pullBefore = (closing && typeof this._pullLiveRowKeys === 'function')
            ? this._pullLiveRowKeys() : null;
        const taken = new Set(Array.isArray(this.history) ? this.history : []);
        const pinsBefore = JSON.stringify(this.project.port_assignments || null,
            this._snapshotReplacer);
        plans.forEach(({ owner, trimmed, gone, dormantGone, cut, live, opening }) => {
            const paths = owner.customPortPaths;
            Object.keys(trimmed).forEach(k => {
                const n = parseInt(k, 10);
                // A drawing left from a custom spell that lost everything
                // simply goes; a live port that did is closed up below.
                if (trimmed[k].length || (Number.isFinite(n) && live(n))) paths[k] = trimmed[k];
                else delete paths[k];
            });
            this._closeUpPorts(owner, gone, dormantGone);
            const ed = this._overrideEditing;
            if (gone.length && ed && ed.kind === 'data' && ed.layerId === owner.id) {
                this._overrideEditing = null;
            }
            sendClientLog('ports_off_wall_trimmed', {
                layerId: owner.id, cut, removed: gone, unused: dormantGone,
                load: !!load, opening: !!opening,
            });
        });
        if (pullBefore && typeof this._dropPullEditsGoneWith === 'function') {
            this._dropPullEditsGoneWith(pullBefore);
        }

        // The cards follow, one screen after another; every undo step taken
        // since (the shrink's own, or a load's first) carries the moved pins.
        let chain = Promise.resolve(false);
        plans.filter(p => p.gone.length).forEach(({ owner, gone }) => {
            chain = chain.then(moved => this._closeUpPortPins(owner, gone)
                .then(m => moved || m, () => moved));
        });
        chain.then(moved => { if (moved) this._followPinsIntoHistory(pinsBefore, taken); });

        const said = plans.filter(p => p.gone.length);
        sayAll(said.map(({ owner, gone, opening }) => {
            const one = gone.length === 1;
            return `${owner.name || 'Screen'}: port${one ? '' : 's'} ${this._portNumbersText(gone)} `
                + (opening ? 'had no cabinets on the wall' : 'had only cabinets that came off the wall')
                + `, so ${one ? 'it is' : 'they are'} gone and the ports after moved up.`;
        }).concat(power.notes));
        const out = plans.map(p => p.owner);
        power.layers.forEach(l => { if (!out.includes(l)) out.push(l); });
        return out;
    }

    // Does one of `layers` still wait for the open's repair (it was locked
    // when its show was opened)?
    portRepairPending(layers) {
        const pending = this._portRepairPending;
        if (!pending || pending.size === 0) return false;
        return (layers || []).some(l => l && pending.has(String(l.id)));
    }

    // Pins the server moved after undo steps were already taken: each step
    // taken since (not among `taken`, the steps there were before) that
    // still holds the pins as they were (`before`, serialized the way a
    // step is) takes the pins as they are now.
    _followPinsIntoHistory(before, taken) {
        if (!Array.isArray(this.history) || !this.project) return;
        const now = JSON.stringify(this.project.port_assignments || null, this._snapshotReplacer);
        if (now === before) return;
        this.history.forEach(entry => {
            if (!entry || !entry.project || taken.has(entry)) return;
            if (JSON.stringify(entry.project.port_assignments || null, this._snapshotReplacer) !== before) return;
            entry.project.port_assignments = JSON.parse(now);
        });
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
    // A single port being redrawn rings the cabinets it holds the same way
    // (overrideFreedPanels).
    mergeFreedPanels(layer) {
        const s = this._mergeRedraw;
        if (!s && typeof this.overrideFreedPanels === 'function') {
            return this.overrideFreedPanels(layer);
        }
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
        // Freed cabinets the drawing did not take: on an automatic screen
        // the walk takes them back once the session closes, and the toast
        // names the ports they went to (QA, 1.6.0: they were re-walked into
        // new ports in silence); on a custom screen they are left unwired.
        const drawnKeys = new Set(path.filter(Boolean)
            .map(e => this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e)));
        const left = [...(s.held || [])].filter(k => !drawnKeys.has(k));
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
            layerId: owner.id, num: s.num, picks: s.picks, drawn: path.length, left: left.length,
        });
        if (typeof this._toast === 'function') {
            const leftover = left.length ? ` ${this._leftoverPortsNote(owner, left)}` : '';
            this._toast(`Ports ${this._portNumbersText(s.picks)} are now port `
                + `${this._portNumberText(s.num)}.${leftover}`, false, left.length ? 8000 : 4000);
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
