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

    // With several ports picked the menu acts on all of them (the owner,
    // 2026-11-03: "it should only allow redraw of all selected"): no item
    // names one port. `backToAuto` hands every picked port that is redrawn
    // back to the walk, `clear` takes every picked port that is on a card
    // off it, each ONE undo step; null where none of the picks has one.
    // Read only while _prepareMergeRunsMenu is armed (the picks' screen).
    _pickedPortsMenus() {
        const p = this._portPicks;
        const owner = p && (this.project.layers || []).find(l => l.id === p.layerId);
        if (!owner) return { backToAuto: null, clear: null };
        const nums = this.portPicksFor(owner);
        const redrawn = nums.filter(n => this.isRunOverridden(owner, 'data', n));
        const backToAuto = redrawn.length ? {
            label: `${redrawn.length > 1 ? 'Ports' : 'Port'} ${this._portNumbersText(redrawn)} back to auto`,
            title: 'Drop the hand-drawn runs; automatic routing takes their '
                + 'cabinets back. Undo puts the drawings back.',
            run: () => this._returnPicksToAuto(owner, redrawn),
        } : null;
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(owner.id));
        const on = ((scr && scr.ports) || []).filter(q => q.cardId && nums.includes(q.number));
        const word = this.showUnitWord() === 'card' ? 'a sending card' : `a ${this.showUnitWord()}`;
        const clearLabel = `Clear ${on.length > 1 || !on.length ? 'ports' : 'port'} `
            + this._portNumbersText(on.length ? on.map(q => q.number) : nums);
        const clear = on.length ? {
            label: clearLabel,
            title: 'Take these ports off their sockets; they stay unattached until '
                + 'you place them again. Names and templates are untouched, '
                + 'and undo puts them back.',
            run: () => {
                sendClientLog('dock_clear', { kind: 'runs', layerId: scr.layerId,
                    indices: on.map(q => q.index) });
                let chain = Promise.resolve();
                on.forEach((q, i) => {
                    chain = chain.then(() => this._assignmentRequest(
                        '/api/port-assignments/unpin', 'POST',
                        { layerId: scr.layerId, index: q.index }, null,
                        i === on.length - 1 ? 'Release Ports' : null));
                });
                return chain;
            },
        } : { label: clearLabel, disabled: true,
              title: `None of these ports is attached to ${word}, so there is nothing to clear.` };
        return { backToAuto, clear };
    }

    // The project's own copy of `layer` (same id), or `layer` itself when
    // the project holds none: a menu armed on one copy acts on the copy the
    // page holds when it is picked (beginMergeRedraw says why).
    _liveLayer(layer) {
        if (!layer || !this.project) return layer;
        const live = (this.project.layers || []).find(l => l && l.id === layer.id);
        return live || layer;
    }

    // Every port of `nums` on `owner` back to the walk, ONE undo step
    // (returnRunToAuto, for several).
    _returnPicksToAuto(owner, nums) {
        owner = this._liveLayer(owner);
        if (!owner || !nums.length) return;
        const locked = typeof this._runLockedLayers === 'function'
            ? [...new Set(nums.flatMap(n => this._runLockedLayers(owner, 'data', n)))] : [];
        if (locked.length) {
            this._showLockedError(locked);
            return;
        }
        owner.customPortOverrides = this.getOverrideNums(owner, 'data').filter(n => !nums.includes(n));
        if (owner.customPortPaths) nums.forEach(n => { delete owner.customPortPaths[n]; });
        const s = this._overrideEditing;
        if (s && s.layerId === owner.id && s.kind === 'data' && nums.includes(s.num)) {
            this._overrideEditing = null;
        }
        this.clearPortPicks();
        this.saveState('Return Ports To Auto');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        this.updatePortCapacityDisplay();
        this.updateCustomFlowUI();
        this.updatePortLabelEditor();
        sendClientLog('return_runs_to_auto', { layerId: owner.id, nums });
        if (window.canvasRenderer) window.canvasRenderer.render();
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
        // The screen as the page holds it NOW. The menu that calls this was
        // armed on the copy held when it opened (_prepareMergeRunsMenu), and
        // a save's reply or an echo landing while the menu was open puts a
        // fresh copy in that one's place (updateLayers, applyServerLayer).
        // Freeing the old copy's ports left the live screen's drawn, so the
        // session opened over ports still wired and a fill of the freed
        // cabinets was refused as "already wired to other ports" (QA,
        // 1.6.0: about one try in nine, a save still out from the redraw
        // just kept).
        owner = this._liveLayer(owner);
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
            // Overrides kept from an automatic spell (unused while custom)
            // follow their paths, so automatic mode gets them back intact.
            const kept = this.getOverrideNums(owner, 'data');
            if (kept.length) {
                owner.customPortOverrides = kept.filter(n => !out.includes(n)).map(shift);
            }
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
        if (!owner || !(removed || []).length || typeof this._assignmentRequest !== 'function') {
            return Promise.resolve(false);
        }
        // In line behind every pin follow already sent (_queuePinFollow),
        // and asked then: an earlier one may have released the screen's
        // last pin.
        return this._queuePinFollow(() => {
            const pins = (this.project && this.project.port_assignments
                && this.project.port_assignments.pins) || [];
            if (!pins.some(p => p && String(p.layerId) === String(owner.id))) return false;
            return this._assignmentRequest('/api/port-assignments/merge', 'POST',
                { layerId: owner.id, removed: removed.map(n => n - 1) }, null, null)
                .then(() => true);
        });
    }

    // ── The pin follows, one at a time ────────────────────────────────────
    //
    // Every request that moves or releases a screen's pins because its
    // port numbers changed (the close-ups, the cabinet follows, the
    // release of pins on ports that are gone) reads the pins as they are
    // when it runs, so they run in the order they were asked for, each
    // after the one before has answered. `task` returns a value or a
    // promise; the returned promise settles with it (false when it threw).
    _queuePinFollow(task) {
        const run = () => {
            try {
                return Promise.resolve(task()).catch(() => false);
            } catch (e) {
                return Promise.resolve(false);
            }
        };
        const out = (this._pinFollowTail || Promise.resolve()).then(run, run);
        this._pinFollowTail = out.then(() => undefined, () => undefined);
        return out;
    }

    // ── No socket on a port that is gone (QA, 1.6.0 beta 5) ──────────────
    //
    // The owner: "no phantom ports, nothing lands on an empty number". A
    // port number with no cabinets holds no socket: its pin is released
    // (the tray already shows that socket free), so another screen can
    // take the socket without a clash coming back later, and a port drawn
    // on that number later lands on no socket by itself. Two moments:
    //   a screen's ports drop (it shrank, or its capacity changed): every
    //     automatic screen a layer commit carries (updateLayers) lets go
    //     of the pins past its last port, the way removing a processor
    //     lets go of its pins. Undo puts them back with the screen.
    //   custom mode turned on (toggleCustomFlowMode, `custom`): after the
    //     drawing's gaps close up, every number with nothing drawn on it
    //     lets go of its pin, and so does every number past the drawing.
    // Left alone: a locked screen (it is unchanged), a mirror (it holds no
    // pins), a port open for redrawing (its number is the redraw's own),
    // a screen whose ports cannot be counted (a capacity error, or none),
    // and a show being opened. The releases ride the commit's own undo
    // step (_followPinsIntoHistory).
    _releasePinsOffPorts(layers, { custom = false } = {}) {
        if (!this.project || this._projectOpening || typeof this._assignmentRequest !== 'function') return;
        const pins = this.project.port_assignments && this.project.port_assignments.pins;
        if (!Array.isArray(pins) || !pins.length) return;
        const ids = [];
        (layers || []).forEach(l => {
            if (!l || (l.type || 'screen') !== 'screen' || ids.includes(String(l.id))) return;
            if (this.isCustomFlow(l) !== custom) return;
            if (!pins.some(p => p && String(p.layerId) === String(l.id))) return;
            ids.push(String(l.id));
        });
        if (!ids.length) return;
        const taken = new Set(Array.isArray(this.history) ? this.history : []);
        this._queuePinFollow(() => {
            const before = JSON.stringify(this.project.port_assignments || null,
                this._snapshotReplacer);
            let chain = Promise.resolve(false);
            ids.forEach(id => {
                const layer = (this.project.layers || []).find(l => String(l.id) === id);
                const off = this._pinsOffPorts(layer, custom);
                if (!off.length) return;
                sendClientLog('pins_off_ports_released', {
                    layerId: id, ports: off.map(i => i + 1), custom,
                });
                chain = chain.then(sent => this._assignmentRequest('/api/port-assignments/remap',
                    'POST', { layerId: layer.id, moves: off.map(i => [i, null]) }, null, null)
                    .then(() => true, () => sent));
            });
            return chain.then(sent => {
                if (sent) this._followPinsIntoHistory(before, taken);
                return sent;
            });
        });
    }

    // The 0-based indices of `layer`'s pins on ports that are gone (see
    // _releasePinsOffPorts): past its last port, and on a custom screen
    // (`custom`) any number with nothing drawn on it too.
    _pinsOffPorts(layer, custom = false) {
        if (!layer || this._layerLocked(layer) || this.isCustomFlow(layer) !== custom) return [];
        if (typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(layer)) return [];
        if (this._portRedrawOpenOn(layer)) return [];
        const ports = this.getLayerPortsRequired(layer) || 0;
        if (!(ports > 0) || layer._capacityError) return [];
        const empty = new Set(custom && typeof this._emptyPortIndices === 'function'
            ? this._emptyPortIndices(layer, ports) : []);
        const pins = (this.project.port_assignments && this.project.port_assignments.pins) || [];
        return pins.filter(p => p && String(p.layerId) === String(layer.id))
            .map(p => parseInt(p.index, 10))
            .filter(i => Number.isFinite(i) && (i >= ports || empty.has(i)))
            .sort((a, b) => a - b);
    }

    // ── Ports that follow their cabinets (QA, 1.6.0) ──────────────────────
    //
    // Where a screen's port numbers change under its cabinets (a redraw
    // that ends with a number held empty, an old show's numbering), the
    // cards and the typed names follow the CABINETS, so every pinned
    // socket keeps driving what it drove. One reading of which cabinets
    // ride which port is taken before the change and one after;
    // _portMovesByCabinet pairs them up.
    //
    // `owner`'s ports as Map(port number -> Set of scoped cabinet keys),
    // the dark cabinets left out: custom from its drawing, automatic from
    // the walk (the overrides folded in).
    _portCabinetKeys(owner) {
        const out = new Map();
        if (!owner) return out;
        const add = (n, layerId, panel) => {
            if (!panel || panel.hidden || panel.blank) return;
            if (!out.has(n)) out.set(n, new Set());
            out.get(n).add(this.getScopedPanelKey(layerId, panel));
        };
        if (this.isCustomFlow(owner)) {
            const paths = owner.customPortPaths || {};
            Object.keys(paths).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) return;
                this.getResolvedPathPanels(owner, paths[k] || [], 'data')
                    .forEach(h => add(n, h.layer ? h.layer.id : owner.id, h.panel));
            });
            return out;
        }
        (this.calculatePortAssignments(owner) || []).forEach(item => {
            if (!item || !item.port) return;
            const lid = (item.layerId === undefined || item.layerId === null)
                ? owner.id : item.layerId;
            add(item.port, lid, item.panel);
        });
        return out;
    }

    // Map(old number -> new number, or null where its cabinets ride no port
    // now) for every port of `before`, read against `after` (both from
    // _portCabinetKeys). A port goes where most of its cabinets went; two
    // old ports landing on one number leave it to the one that already had
    // that number, else to the one with more cabinets there, else the
    // lower one, and the other gets null (the cards release it).
    _portMovesByCabinet(before, after) {
        const at = new Map();
        after.forEach((keys, n) => keys.forEach(k => at.set(k, n)));
        const pick = new Map();
        before.forEach((keys, n) => {
            const tally = new Map();
            keys.forEach(k => {
                const to = at.get(k);
                if (to !== undefined) tally.set(to, (tally.get(to) || 0) + 1);
            });
            let best = null;
            tally.forEach((c, to) => {
                if (!best || c > best.c || (c === best.c && to < best.to)) best = { to, c };
            });
            pick.set(n, best);
        });
        const claim = new Map();
        pick.forEach((best, n) => {
            if (!best) return;
            const prev = claim.get(best.to);
            let wins = !prev;
            if (prev) {
                const mine = n === best.to;
                const theirs = prev.n === best.to;
                if (mine !== theirs) wins = mine;
                else if (best.c !== prev.c) wins = best.c > prev.c;
                else wins = n < prev.n;
            }
            if (wins) claim.set(best.to, { n, c: best.c });
        });
        const moves = new Map();
        pick.forEach((best, n) => {
            const won = best && claim.get(best.to) && claim.get(best.to).n === n;
            moves.set(n, won ? best.to : null);
        });
        return moves;
    }

    // Let the typed names and the cards follow `moves` (_portMovesByCabinet)
    // on `owner`. A name or pin on a number `moves` does not know stays put
    // unless a moved port lands on it. The names change at once; the cards
    // follow on the server (/remap) and the promise resolves true when pins
    // were sent. `local`: the project is not on the server yet (a show
    // being opened), so the pins are moved here, by the same rule as
    // port_assignment.remap_pins, and travel with the project's own PUT.
    _followPortsByCabinet(owner, moves, { local = false } = {}) {
        const where = this._portFollowWhere(moves);
        ['portLabelOverridesPrimary', 'portLabelOverridesReturn'].forEach(key => {
            const labels = owner[key];
            if (!labels || typeof labels !== 'object') return;
            const moved = {};
            Object.keys(labels).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { moved[k] = labels[k]; return; }
                const to = where(n);
                if (to !== null) moved[to] = labels[k];
            });
            owner[key] = moved;
        });
        const pinMoves = () => {
            const sent = [];
            ((this.project && this.project.port_assignments
                && this.project.port_assignments.pins) || []).forEach(p => {
                if (!p || String(p.layerId) !== String(owner.id)) return;
                const n = (parseInt(p.index, 10) || 0) + 1;
                const to = where(n);
                if (to !== n) sent.push([n - 1, to === null ? null : to - 1]);
            });
            return sent;
        };
        if (local) {
            const pins = (this.project.port_assignments && this.project.port_assignments.pins) || [];
            const sent = pinMoves();
            if (!sent.length) return Promise.resolve(false);
            const move = new Map(sent);
            const ranked = [];
            const others = [];
            pins.forEach(p => {
                if (!p || String(p.layerId) !== String(owner.id)) { others.push(p); return; }
                const i = parseInt(p.index, 10) || 0;
                if (!move.has(i)) { ranked.push([0, i, p]); return; }
                const to = move.get(i);
                if (to === null) return;
                ranked.push([to === i ? 0 : 1, i, { ...p, index: to }]);
            });
            ranked.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
            const seen = new Set();
            const kept = [];
            ranked.forEach(([, , p]) => {
                if (seen.has(p.index)) return;
                seen.add(p.index);
                kept.push(p);
            });
            kept.sort((a, b) => a.index - b.index);
            this.project.port_assignments.pins = others.concat(kept);
            return Promise.resolve(true);
        }
        if (typeof this._assignmentRequest !== 'function') return Promise.resolve(false);
        // In line behind every pin follow already sent, and read then: a
        // close-up ahead of this one moves the pins these moves apply to.
        return this._queuePinFollow(() => {
            const sent = pinMoves();
            if (!sent.length) return false;
            return this._assignmentRequest('/api/port-assignments/remap', 'POST',
                { layerId: owner.id, moves: sent }, null, null).then(() => true);
        });
    }

    // Where `moves` (_portMovesByCabinet) puts a number holding a name or a
    // pin: its own move, or itself on a number `moves` does not know unless
    // a moved port lands on it (then null: it goes).
    _portFollowWhere(moves) {
        const targets = new Set();
        moves.forEach(to => { if (to !== null) targets.add(to); });
        return n => (moves.has(n) ? moves.get(n) : (targets.has(n) ? null : n));
    }

    // ── A show saved before the column-first Down numbering (QA, 1.6.0) ──
    //
    // 1.6.0 beta 4 changed the numbers Port numbers on Down (Across on a
    // vertical pattern) gives a line cut differently from the stacks, like
    // a bottom row of half-height cabinets (_splitRunStacks): its runs
    // were numbered by their place along the line (5, 10, 15, ...) and now
    // join the stack they start under (5, 14, 23, ...). The cabinets did
    // not move, only the numbers, but the cards are pinned by number: an
    // older show opened as it was saved had its card sockets silently
    // driving other cabinets. So on open, each automatic screen of such a
    // show is read both ways and the card pins and typed port names move
    // with their cabinets to the new numbers (_followPortsByCabinet,
    // locally: this runs before the project's own PUT, which carries
    // them). Returns the sentences for the toast.

    // Was `project` written by a build from before 1.6.0 beta 4 (or one
    // that did not stamp)? The beta matters here, so this is not
    // projectPredatesVersion, which reads major.minor.patch only.
    predatesStackNumbering(project) {
        const m = /^\s*v?(\d+)\.(\d+)(?:\.(\d+))?(?:-beta\.(\d+))?/
            .exec(String((project && project.app_version) || ''));
        if (!m) return true;
        const saved = [Number(m[1]), Number(m[2]), Number(m[3] || 0)];
        const bar = [1, 6, 0];
        for (let i = 0; i < 3; i += 1) {
            if (saved[i] !== bar[i]) return saved[i] < bar[i];
        }
        return m[4] !== undefined && Number(m[4]) < 4;
    }

    _followOldStackNumbering() {
        const layers = ((this.project && this.project.layers) || []).filter(l => l
            && (l.type || 'screen') === 'screen' && !this.isCustomFlow(l)
            && (l.portNumberOrder === 'down' || l.portNumberOrder === 'across')
            && (l.portMappingMode || 'organized') === 'organized'
            && !(typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(l)));
        if (!this.project.port_assignments) this.project.port_assignments = {};
        const notes = [];
        layers.forEach(l => {
            let old;
            let now;
            // Both readings without the stacked leftovers, which came after
            // this numbering: their own follow goes on from the numbers this
            // one leaves (followOldLeftoverStacks).
            this._leftoversUnstacked = true;
            try {
                this._numberRunsByPlace = true;
                old = this._portCabinetKeys(l);
                this._numberRunsByPlace = false;
                now = this._portCabinetKeys(l);
            } finally {
                this._numberRunsByPlace = false;
                this._leftoversUnstacked = false;
            }
            const moves = this._portMovesByCabinet(old, now);
            const moved = [...moves].filter(([n, to]) => to !== n);
            if (!moved.length) return;
            const held = () => JSON.stringify([((this.project.port_assignments.pins) || [])
                .filter(p => p && String(p.layerId) === String(l.id)),
                l.portLabelOverridesPrimary || {}, l.portLabelOverridesReturn || {}]);
            const was = held();
            this._followPortsByCabinet(l, moves, { local: true });
            const followed = held() !== was;
            sendClientLog('old_stack_numbering_followed', { layerId: l.id, moved, followed });
            // Nothing pinned or named on the ports that moved: nothing to say.
            if (!followed) return;
            const shown = moved.filter(([, to]) => to !== null).slice(0, 3)
                .map(([n, to]) => `${this._portNumberText(n)} is now ${this._portNumberText(to)}`);
            notes.push(`${l.name || 'Screen'}: this show was saved before Port numbers on `
                + `${l.portNumberOrder === 'down' ? 'Down' : 'Across'} changed, so some ports have `
                + `new numbers (${shown.join(', ')}${moved.length > 3 ? ', ...' : ''}). `
                + 'Their card ports and names moved with their cabinets.');
        });
        return notes;
    }

    // ── A show saved before the leftovers stacked (the owner, 2026-11-04) ──
    //
    // Organized stacks the leftover at the end of each cut line with the
    // leftovers of the lines after it (_stackLineLeftovers), so a show saved
    // before that has new numbers the day it is opened: the 84 x 5 wall that
    // needed 49 ports needs 47, and the ports after each stack close up. The
    // cabinets did not move, only the numbers, and the cards are pinned by
    // number, so the pins past the new last port were released
    // (_releasePinsOffPorts) and the others drove other cabinets. The owner:
    // "follow like labels do". So on open each automatic screen is read
    // both ways and its pins and typed names ride their cabinets
    // (_portMovesByCabinet, _followPortsByCabinet). Two leftovers that are
    // one port now are that rule's collision: one keeps the number, the
    // other's name goes and its pin is released.
    //
    // This runs on the server's copy, behind the open's own repair
    // (trimPortsOffWall) and ahead of the load's commit and its release,
    // not ahead of the PUT the way _followOldStackNumbering does: a pin this
    // lets go of goes through /remap, so its socket forgets its port cable
    // the way any release does.
    //
    // A locked screen stays as it is. It carries `leftoverFollowDue` from
    // the open, since the stamp no longer says so after the next save, and
    // follows in the step that unlocks it (followDueLeftovers).
    //
    // A setting that renumbers (Organized or Max Capacity, Port numbers, a
    // pattern) is not this: there a typed name stays on its number and so
    // does the pin.

    // Was `project` written by a build from before the stacked leftovers
    // (1.6.0 beta 6), or one that did not stamp? As redrawsPredateRelease,
    // the beta read off the stamp.
    predatesLeftoverStacks(project) {
        if (this.projectPredatesVersion('1.6.0', project)) return true;
        const m = /^\s*v?1\.6\.0-beta\.(\d+)/.exec(String((project && project.app_version) || ''));
        return !!m && Number(m[1]) <= 5;
    }

    // Can the stacks have moved `l`'s numbers? Not on a custom screen (a
    // drawing is never rewritten), not on Max Capacity, and not on a mirror
    // (its map is its source's).
    _leftoversRenumber(l) {
        return !!l && (l.type || 'screen') === 'screen' && !this.isCustomFlow(l)
            && (l.portMappingMode || 'organized') === 'organized'
            && !(typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(l));
    }

    // _portMovesByCabinet from `l`'s walk without the stacks to its walk now.
    _leftoverMoves(l) {
        let old;
        this._leftoversUnstacked = true;
        try {
            old = this._portCabinetKeys(l);
        } finally {
            this._leftoversUnstacked = false;
        }
        return this._portMovesByCabinet(old, this._portCabinetKeys(l));
    }

    // What `moves` changes on `owner`: `changed` when a pin or a typed name
    // moves or goes, `lost` the port numbers whose pins are released.
    _leftoverHolds(owner, moves) {
        const where = this._portFollowWhere(moves);
        const pinned = ((this.project.port_assignments && this.project.port_assignments.pins) || [])
            .filter(p => p && String(p.layerId) === String(owner.id))
            .map(p => (parseInt(p.index, 10) || 0) + 1);
        const named = ['portLabelOverridesPrimary', 'portLabelOverridesReturn']
            .flatMap(key => Object.keys(owner[key] || {}))
            .map(k => parseInt(k, 10)).filter(n => Number.isFinite(n));
        return {
            changed: pinned.concat(named).some(n => where(n) !== n),
            lost: pinned.filter(n => where(n) === null),
        };
    }

    // The open's half: every automatic screen follows, or waits when it is
    // locked. A screen with nothing pinned or named on the ports that moved
    // has nothing to say. Returns the sentences for the toast.
    followOldLeftoverStacks() {
        const due = [];
        const notes = [];
        ((this.project && this.project.layers) || []).forEach(l => {
            if (!this._leftoversRenumber(l)) return;
            const moves = this._leftoverMoves(l);
            if (!this._leftoverHolds(l, moves).changed) return;
            if (!this._layerLocked(l)) {
                due.push({ owner: l, moves });
                return;
            }
            l.leftoverFollowDue = true;
            sendClientLog('old_leftovers_held', { layerId: l.id,
                moved: [...moves].filter(([n, to]) => to !== n) });
            notes.push(`${l.name || 'Screen'}: this show was saved before Organized stacked its `
                + 'leftovers, so some ports have new numbers. The screen is locked, so its '
                + 'processor ports and names stay as they are until it is unlocked.');
        });
        return notes.concat(this._followLeftovers(due));
    }

    // The unlock's half, from the commit that carries it (updateLayers),
    // ahead of that commit's release: every screen owed the follow that is
    // no longer locked gets it in the commit's own undo step, which an undo
    // takes back with the lock. Returns the screens it changed.
    followDueLeftovers() {
        if (!this.project || this._projectOpening) return [];
        const owed = this._leftoversOwed();
        if (!owed.length) return [];
        const notes = this._followLeftovers(owed.filter(l => this._leftoversRenumber(l))
            .map(owner => ({ owner, moves: this._leftoverMoves(owner) })));
        owed.forEach(l => { l.leftoverFollowDue = false; });
        if (notes.length && typeof this._toast === 'function') {
            this._toast(notes.join(' '), false, 12000);
        }
        return owed;
    }

    _leftoversOwed() {
        return ((this.project && this.project.layers) || [])
            .filter(l => l && l.leftoverFollowDue && !this._layerLocked(l));
    }

    // `due` ([{ owner, moves }]) follows, each screen's pins in line behind
    // whatever is already going to the server, and every undo step taken
    // since holds them (_followPinsIntoHistory). Returns the sentences.
    _followLeftovers(due) {
        if (!due.length) return [];
        const taken = new Set(Array.isArray(this.history) ? this.history : []);
        let before = null;
        this._queuePinFollow(() => {
            before = JSON.stringify(this.project.port_assignments || null, this._snapshotReplacer);
        });
        const notes = [];
        const sent = due.map(({ owner, moves }) => {
            const { changed, lost } = this._leftoverHolds(owner, moves);
            const moved = [...moves].filter(([n, to]) => to !== n);
            const pinned = this._followPortsByCabinet(owner, moves);
            sendClientLog('old_leftovers_followed', { layerId: owner.id, moved, released: lost });
            if (changed) notes.push(this._leftoverNote(owner, moved, lost));
            return pinned;
        });
        Promise.all(sent).then(moved => {
            if (moved.some(Boolean)) this._followPinsIntoHistory(before, taken);
        });
        return notes;
    }

    // "Wall: this show was saved before Organized stacked its leftovers, so
    // some ports have new numbers (P10 is now P9, ...). Their processor
    // ports and names moved with their cabinets."
    _leftoverNote(owner, moved, lost) {
        const shown = moved.filter(([, to]) => to !== null).slice(0, 3)
            .map(([n, to]) => `${this._portNumberText(n)} is now ${this._portNumberText(to)}`);
        const one = lost.length === 1;
        return `${owner.name || 'Screen'}: this show was saved before Organized stacked its `
            + `leftovers, so some ports have new numbers (${shown.join(', ')}`
            + `${moved.length > 3 ? ', ...' : ''}). `
            + 'Their processor ports and names moved with their cabinets.'
            + (lost.length ? ` ${this._portNumbersText(lost)} ${one ? 'is' : 'are'} now part of `
                + `${one ? 'another port' : 'other ports'}, so `
                + `${one ? 'its processor port was' : 'their processor ports were'} released.` : '');
    }

    // The data overrides of `owner` with nothing on them: no cabinet that
    // carries data on their path.
    _emptyOverrideNums(owner) {
        if (!owner || this.isCustomFlow(owner)) return [];
        const runs = new Set(this._ownOverrideRuns(owner, 'data').map(o => o.num));
        return this.getOverrideNums(owner, 'data').filter(n => !runs.has(n));
    }

    // Is a port of `owner` open for redrawing (a single redraw, its hold,
    // or several ports redrawn as one)? Then a number with nothing drawn on
    // it yet is the redraw's own, and it is left be.
    _portRedrawOpenOn(owner) {
        if (!owner) return false;
        const ed = this._overrideEditing;
        if (ed && ed.kind === 'data' && ed.layerId === owner.id) return true;
        const h = this._overrideHeld;
        if (h && h.layerId === owner.id && this._overrideHoldLive()) return true;
        return typeof this._mergeRedrawOn === 'function' && this._mergeRedrawOn(owner);
    }

    // NO PHANTOM PORTS (QA, 1.6.0): every port number has cabinets on it.
    // A single redraw that ends with a number held empty (Redraw port P44,
    // Clear Port, Esc) hands that number back to the walk, the way "Port
    // P44 back to auto" does, and any number left with no cabinet closes
    // up (_closeUpPorts). `before` is which cabinets rode which port when
    // the redraw opened (_beginOverrideHold): the names and the cards
    // follow the cabinets from there (_followPortsByCabinet), so a socket
    // never ends up on a number with nothing on it. ONE undo step, the
    // pins in it. Returns the sentence for the toast, or ''.
    _repairEmptyOverrides(owner, before) {
        const empty = this._emptyOverrideNums(owner);
        if (!empty.length || this._layerLocked(owner) || this._portRedrawOpenOn(owner)) return '';
        if (typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(owner)) return '';
        const taken = new Set(Array.isArray(this.history) ? this.history : []);
        const pinsBefore = JSON.stringify(this.project.port_assignments || null,
            this._snapshotReplacer);
        const ref = before instanceof Map ? before : this._portCabinetKeys(owner);
        const labels = {
            portLabelOverridesPrimary: owner.portLabelOverridesPrimary,
            portLabelOverridesReturn: owner.portLabelOverridesReturn,
        };
        owner.customPortOverrides = this.getOverrideNums(owner, 'data')
            .filter(n => !empty.includes(n));
        if (owner.customPortPaths) empty.forEach(n => { delete owner.customPortPaths[n]; });
        // A number still without a cabinet (the overrides after it held
        // their numbers, with no automatic port between) closes up.
        const mid = this._portCabinetKeys(owner);
        const top = Math.max(0, ...mid.keys());
        const holes = [];
        for (let n = 1; n < top; n++) if (!mid.has(n)) holes.push(n);
        if (holes.length) this._closeUpPorts(owner, holes);
        // The names follow the cabinets, not the close-up's shift.
        Object.assign(owner, labels);
        const moves = this._portMovesByCabinet(ref, this._portCabinetKeys(owner));
        const pinned = this._followPortsByCabinet(owner, moves);
        sendClientLog('empty_overrides_repaired', {
            layerId: owner.id, ports: empty, holes,
            moved: [...moves].filter(([n, to]) => to !== n),
        });
        this.saveState('Return Port To Auto');
        this.saveClientSideProperties();
        this.updateLayers(this._pathPersistLayers(owner));
        pinned.then(moved => { if (moved) this._followPinsIntoHistory(pinsBefore, taken); },
            () => {});
        this.updatePortCapacityDisplay();
        this.updateCustomFlowUI();
        this.updatePortLabelEditor();
        const one = empty.length === 1;
        return `${owner.name || 'Screen'}: nothing was drawn on port${one ? '' : 's'} `
            + `${this._portNumbersText(empty)}, so ${one ? 'it' : 'they'} went back to automatic.`;
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
            this._portRepairDone = new Set();
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
        // The screens getting the open's repair: their gaps close after the
        // trim (_customGapNumbers, _closeDormantGaps).
        const opened = [];
        screens.forEach(owner => {
            const old = owner.customPortPaths;
            if (!old || typeof old !== 'object') return;
            if (typeof this.mirrorSourceOf === 'function' && this.mirrorSourceOf(owner)) return;
            // The open's repair: on the open itself, or on a screen that
            // was locked then and is not any more.
            const opening = load || pending.has(String(owner.id));
            if (opening && !this._layerLocked(owner)) {
                opened.push(owner);
                if (pending.delete(String(owner.id))) {
                    (this._portRepairDone || (this._portRepairDone = new Set())).add(String(owner.id));
                }
            }
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
            // An override with nothing drawn on it is a phantom port: gone
            // on the open, and at any commit while no redraw is open on
            // the screen (QA, 1.6.0: one made live came back at the next
            // fill). While one is open the empty number is the redraw's.
            const emptied = gone.length;
            if (opening || !this._portRedrawOpenOn(owner)) {
                ovr.forEach(n => {
                    const path = trimmed[n] || old[n];
                    if (!gone.includes(n) && !(Array.isArray(path) && path.length)) gone.push(n);
                });
            }
            if (this._layerLocked(owner)) {
                if (opening) pending.add(String(owner.id));
                if (cut || gone.length) {
                    sendClientLog('ports_off_wall_locked', { layerId: owner.id, cut, ports: gone });
                    // Said, the way the power side says it (_sayTrimHeld):
                    // once while the same hold stands (QA, 1.6.0: the data
                    // side opened a locked screen's ghost ports in silence).
                    if (typeof this._sayTrimHeld === 'function') {
                        const one = gone.length === 1;
                        this._sayTrimHeld(owner, 'data', [owner], null, gone.length
                            ? `${owner.name || 'Screen'}: port${one ? '' : 's'} ${this._portNumbersText(gone)} `
                                + ((opening || emptied === 0) ? 'had no cabinets on the wall'
                                    : 'had only cabinets that came off the wall')
                                + ` and ${one ? 'stays' : 'stay'} as ${one ? 'it is' : 'they are'}.`
                            : `${owner.name || 'Screen'}: its ports keep the cabinets that came off the wall.`,
                        `${cut}:${gone.join(',')}`);
                    }
                }
                return;
            }
            if (!cut && !gone.length) return;
            plans.push({ owner, trimmed, gone: gone.sort((a, b) => a - b),
                dormantGone, cut, live, opening, emptyOnly: emptied === 0 });
        });
        this._portRepairPending = pending;
        const power = (typeof this._trimCircuitsOffWall === 'function')
            ? this._trimCircuitsOffWall({ load, onWall }) : { layers: [], notes: [] };
        const sayAll = (notes) => {
            if (notes.length && typeof this._toast === 'function') {
                this._toast(notes.join(' '), false, 8000);
            }
        };
        // The gaps an opened show's custom drawing has: worked out once the
        // trim below has run, read here only to know whether to look.
        const mayGap = opened.some(o => this.isCustomFlow(o)
            ? this._customGapNumbers(o).length > 0 : this._closeDormantGaps(o, true));
        if (!plans.length && !mayGap) {
            sayAll(power.notes);
            return power.layers;
        }

        const closing = plans.some(p => p.gone.length) || mayGap;
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
        // No gaps after an open (the owner, 2026-11-03): a custom screen's
        // ports close up to 1..N, the unused drawing of an automatic one
        // round its live overrides.
        const gapped = [];
        const touched = [];
        opened.forEach(owner => {
            if (this.isCustomFlow(owner)) {
                const gaps = this._customGapNumbers(owner);
                if (!gaps.length) return;
                this._closeUpPorts(owner, gaps);
                gapped.push({ owner, gaps });
                touched.push(owner);
                sendClientLog('custom_gaps_closed', { layerId: owner.id, gaps, on: 'open' });
            } else if (this._closeDormantGaps(owner)) {
                touched.push(owner);
                sendClientLog('custom_gaps_closed', { layerId: owner.id, on: 'open', unused: true });
            }
        });
        if (pullBefore && typeof this._dropPullEditsGoneWith === 'function') {
            this._dropPullEditsGoneWith(pullBefore);
        }

        // The cards follow, one screen after another; every undo step taken
        // since (the shrink's own, or a load's first) carries the moved pins.
        // Asked now, in this order, so they run ahead of any release this
        // commit asks for next (_queuePinFollow, _releasePinsOffPorts).
        const follows = plans.filter(p => p.gone.length)
            .map(({ owner, gone }) => this._closeUpPortPins(owner, gone))
            .concat(gapped.map(({ owner, gaps }) => this._closeUpPortPins(owner, gaps)));
        Promise.all(follows).then(moved => {
            if (moved.some(Boolean)) this._followPinsIntoHistory(pinsBefore, taken);
        });

        const said = plans.filter(p => p.gone.length);
        sayAll(said.map(({ owner, gone, opening, emptyOnly }) => {
            const one = gone.length === 1;
            // "the ports after moved up" only where a port came after.
            const ports = this._portCabinetKeys(owner);
            const after = ports.size && Math.max(...ports.keys()) >= gone[0];
            return `${owner.name || 'Screen'}: port${one ? '' : 's'} ${this._portNumbersText(gone)} `
                + ((opening || emptyOnly) ? 'had no cabinets on the wall'
                    : 'had only cabinets that came off the wall')
                + `, so ${one ? 'it is' : 'they are'} gone`
                + (after ? ' and the ports after moved up.' : '.');
        }).concat(gapped.map(({ owner, gaps }) => this._customGapNote(owner, gaps)))
            .concat(power.notes));
        const out = plans.map(p => p.owner);
        touched.forEach(l => { if (!out.includes(l)) out.push(l); });
        power.layers.forEach(l => { if (!out.includes(l)) out.push(l); });
        return out;
    }

    // ── No gaps in the custom numbers (the owner, 2026-11-03) ─────────────
    //
    // "on custom there should be no gaps like automatic": a custom screen's
    // ports run 1..N. A number with nothing drawn on it - missing from the
    // drawing, or an empty path - is a gap, and the ports after it close up
    // the way a removed port's do (_closeUpPorts: names, the active port,
    // and the cards through _closeUpPortPins all follow). Run when a show is
    // opened (trimPortsOffWall's repair) and when custom mode is turned on
    // (_closeCustomGapsOnToggle), so gaps an older file already had go too.
    //
    // The numbers with nothing drawn on a custom screen, ascending: every
    // gap below its highest drawn port, and any empty path above it.
    _customGapNumbers(owner) {
        const paths = (owner && owner.customPortPaths) || {};
        const nums = Object.keys(paths).map(k => parseInt(k, 10))
            .filter(n => Number.isFinite(n) && n >= 1);
        const drawn = nums.filter(n => Array.isArray(paths[n]) && paths[n].length > 0);
        if (!drawn.length) return nums.sort((a, b) => a - b);
        const max = Math.max(...drawn);
        const gaps = [];
        for (let n = 1; n < max; n++) if (!drawn.includes(n)) gaps.push(n);
        nums.forEach(n => { if (n > max) gaps.push(n); });
        return gaps.sort((a, b) => a - b);
    }

    // The unused drawing an automatic screen keeps from a custom spell,
    // closed up so custom mode turned on later shows no gap. Its paths take
    // the lowest numbers in order, stepping round every live override, so
    // a live port never moves and is never written over; an empty one goes.
    // The names and cards follow the automatic ports there, not this
    // drawing, so they stay. True when it changed; `dryRun` only says
    // whether it would.
    _closeDormantGaps(owner, dryRun = false) {
        if (!owner || this.isCustomFlow(owner)) return false;
        const paths = owner.customPortPaths;
        if (!paths || typeof paths !== 'object') return false;
        const ovr = this.getOverrideNums(owner, 'data');
        const dormant = Object.keys(paths).map(k => parseInt(k, 10))
            .filter(n => Number.isFinite(n) && n >= 1 && !ovr.includes(n))
            .sort((a, b) => a - b);
        const out = {};
        let slot = 1;
        let moved = false;
        Object.keys(paths).forEach(k => {
            const n = parseInt(k, 10);
            if (!Number.isFinite(n) || ovr.includes(n)) out[k] = paths[k];
        });
        dormant.forEach(n => {
            if (!(Array.isArray(paths[n]) && paths[n].length)) { moved = true; return; }
            while (ovr.includes(slot)) slot++;
            if (slot !== n) moved = true;
            out[slot] = paths[n];
            slot++;
        });
        if (!moved || dryRun) return moved;
        owner.customPortPaths = out;
        return true;
    }

    // Turning custom mode on (toggleCustomFlowMode) closes the drawing's
    // gaps on every screen it turned, inside the toggle's own step; the
    // cards follow on the server and into that step (_followPinsIntoHistory).
    _closeCustomGapsOnToggle(layers) {
        const closing = (layers || []).map(owner => ({ owner, gaps: this._customGapNumbers(owner) }))
            .filter(c => c.gaps.length);
        if (!closing.length) return;
        const pullBefore = typeof this._pullLiveRowKeys === 'function' ? this._pullLiveRowKeys() : null;
        const taken = new Set(Array.isArray(this.history) ? this.history : []);
        const pinsBefore = JSON.stringify(this.project.port_assignments || null, this._snapshotReplacer);
        closing.forEach(({ owner, gaps }) => {
            this._closeUpPorts(owner, gaps);
            sendClientLog('custom_gaps_closed', { layerId: owner.id, gaps, on: 'custom_on' });
        });
        if (pullBefore && typeof this._dropPullEditsGoneWith === 'function') {
            this._dropPullEditsGoneWith(pullBefore);
        }
        Promise.all(closing.map(({ owner, gaps }) => this._closeUpPortPins(owner, gaps)))
            .then(moved => { if (moved.some(Boolean)) this._followPinsIntoHistory(pinsBefore, taken); });
        if (typeof this._toast === 'function') {
            this._toast(closing.map(({ owner, gaps }) => this._customGapNote(owner, gaps)).join(' '),
                false, 8000);
        }
    }

    // "Screen1: port P45 had nothing drawn on it, so the ports after it
    // moved up and run 1-46 with no gaps." Read once the ports closed up.
    // One port left reads "moved up to port 1", never a "1-1" range; with no port
    // after the gaps nothing moved up, and the note says the numbers went
    // (the trim's own wording).
    _customGapNote(owner, gaps) {
        const one = gaps.length === 1;
        const paths = (owner && owner.customPortPaths) || {};
        const n = Object.keys(paths).filter(k => Array.isArray(paths[k]) && paths[k].length).length;
        // A port came after a gap when the first gap is now a drawn port.
        const moved = n > 0 && Math.min(...gaps) <= n;
        const head = `${(owner && owner.name) || 'Screen'}: port${one ? '' : 's'} ${this._portNumbersText(gaps)} `
            + `had nothing drawn on ${one ? 'it' : 'them'}, so `;
        if (!moved) return head + `${one ? 'it is' : 'they are'} gone.`;
        return head + (n === 1 ? 'the port after moved up to port 1.'
            : `the ports after moved up and run 1-${n} with no gaps.`);
    }

    // Does one of `layers` still wait for the open's repair (it was locked
    // when its show was opened)?
    // One that got it at an unlock is asked again at the next: an undo of
    // that unlock put the screen back locked with its ghost ports, and the
    // repair is the open's, so running it twice changes nothing more (QA,
    // 1.6.0: undo the unlock, unlock again, and the repair was skipped).
    portRepairPending(layers) {
        const pending = this._portRepairPending || (this._portRepairPending = new Set());
        const done = this._portRepairDone;
        (layers || []).forEach(l => {
            if (l && done && done.has(String(l.id))) pending.add(String(l.id));
        });
        // The stacked leftovers' follow rides the same commit.
        if (this._leftoversOwed().length) return true;
        if (pending.size === 0) return false;
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
