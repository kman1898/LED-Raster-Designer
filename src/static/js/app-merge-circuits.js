// app-merge-circuits: several POWER circuits picked on the wall and redrawn
// as ONE, for LEDRasterApp - the power side of app-merge-runs.js. Owns the
// circuit picks (Shift+click a run, Shift+drag a box; an Alt+drag sweep
// counts too), the "Redraw circuits S1-5 to S2-1 as one" menu entry, and
// opening, keeping and closing up the redraw. The session itself is the
// data side's (_mergeRedraw, with kind 'power'): Enter keeps, Esc puts it
// all back, undo past it ends it.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _MergeCircuits {

    // ── The rulings (the owner, 2026-11-12) ───────────────────────────────
    //
    // "I was trying to redraw multiple circuits using the alt key ... it
    // wouldn't let me do multiple at the same time". Ruled the same day:
    // "Redraw should work just like data", and "if I select 2 ports to
    // redraw then draw 1 in its place all circuits after it will be
    // renumbered":
    //
    //   picking    in the Power view, Shift+click a run picks its circuit
    //              (again un-picks it), Shift+drag a box from a run picks
    //              every circuit the box touches, and an Alt+drag sweep
    //              (the 2fer / 3fer batch selection) is a pick too. One
    //              wall's circuits at a time; a grouped wall is one wall.
    //   redraw     with 2+ picked, right-click offers "Redraw circuits S1-5
    //              to S2-1 as one" (a list where the numbers are not
    //              consecutive). The picked circuits' cabinets are freed and
    //              ONE new circuit is drawn on the first number, with every
    //              rule a circuit's path has: one circuit's limit, a cabinet
    //              another circuit carries refused out loud. Picks whose
    //              cabinets one circuit cannot carry are refused before
    //              anything is freed.
    //   numbers    the new circuit keeps the first number; the other picks
    //              go and every circuit after them closes up. What is kept
    //              per circuit stays with its circuit as it moves: a typed
    //              circuit name and a circuit's cable follow its cabinets
    //              (on an automatic screen the walk numbers them, so they
    //              follow the cabinets the way a redraw ending moves them,
    //              _cableCarryApply / _followCircuitLabelsByCabinet); the
    //              first circuit's own name and cable stay on the new one.
    //              A multi keeps its distro, its number and its name. On a
    //              custom screen every circuit kept stays on its multi and
    //              its tail (_removeCircuitsKeepFeeds, the Clear Circuit
    //              rule), so a circuit on a distro keeps its label; one on
    //              no distro is named by its place and reads one place down
    //              per circuit removed before it, as on an automatic screen.
    //   done       Enter keeps the drawing, and so does drawing every freed
    //              cabinet; Esc puts everything back. Kept, the whole thing
    //              is ONE undo step. A locked screen is refused with the
    //              locked error, and so is a change that would move a
    //              locked screen's circuits on a shared multi.

    // The circuit numbers picked on `layer` (the wall's owner), ascending:
    // the Shift picks and the Alt sweep together.
    circuitPicksFor(layer) {
        if (!layer) return [];
        const out = new Set(typeof this.portPicksFor === 'function'
            ? this.portPicksFor(layer, 'power') : []);
        const sw = this._sweepSelection;
        if (sw && sw.layerId === layer.id && Array.isArray(sw.nums)) {
            sw.nums.forEach(n => out.add(n));
        }
        return [...out].sort((a, b) => a - b);
    }

    // A Shift press in the Power view keeps what an Alt sweep picked: the
    // press drops the sweep (a plain press does), so its circuits move into
    // the Shift picks first.
    adoptSweepAsPicks() {
        const sw = this._sweepSelection;
        if (!sw || !Array.isArray(sw.nums) || !sw.nums.length) return;
        const p = this._portPicks;
        const same = p && p.kind === 'power' && p.layerId === sw.layerId;
        const nums = same ? p.nums.slice() : [];
        sw.nums.forEach(n => { if (!nums.includes(n)) nums.push(n); });
        this._portPicks = { kind: 'power', layerId: sw.layerId, nums };
    }

    // The circuit numbers of `ownerId`'s circuits with a cabinet inside the
    // world rect, the way portsInWorldRect reads the data map.
    circuitsInWorldRect(ownerId, rect) {
        const r = window.canvasRenderer;
        if (!this.project || !rect || !r || typeof r._powerCircuitForPanel !== 'function') return [];
        const out = new Set();
        (this.project.layers || []).forEach(layer => {
            if (!layer || layer.visible === false || !Array.isArray(layer.panels)) return;
            if ((layer.type || 'screen') !== 'screen') return;
            const off = this._getLayerWorkspaceOffset(layer);
            let x1 = Math.min(rect.x1, rect.x2) - off.wx;
            let x2 = Math.max(rect.x1, rect.x2) - off.wx;
            let y1 = Math.min(rect.y1, rect.y2) - off.wy;
            let y2 = Math.max(rect.y1, rect.y2) - off.wy;
            if (typeof r._unrotatePointForLayer === 'function') {
                const c = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]]
                    .map(([x, y]) => r._unrotatePointForLayer(x, y, layer));
                x1 = Math.min(...c.map(q => q.x)); x2 = Math.max(...c.map(q => q.x));
                y1 = Math.min(...c.map(q => q.y)); y2 = Math.max(...c.map(q => q.y));
            }
            if (!(layer._powerPanelCircuitMap instanceof Map)
                    && typeof r.preparePowerLayerRenderData === 'function') {
                r.preparePowerLayerRenderData(layer);
            }
            layer.panels.forEach(panel => {
                if (panel.hidden) return;
                if (panel.x > x2 || panel.x + panel.width < x1
                        || panel.y > y2 || panel.y + panel.height < y1) return;
                const c = r._powerCircuitForPanel(layer, panel);
                if (c && c.owner && c.owner.id === ownerId) out.add(c.circuitNum);
            });
        });
        return [...out].sort((a, b) => a - b);
    }

    // "S1-5 to S2-1" for consecutive numbers, "S1-5, S2-1 and S2-2"
    // otherwise: the circuits named by their labels, as the wall prints them.
    _circuitNumbersText(owner, nums, labels = null) {
        const s = nums.slice().sort((a, b) => a - b);
        const names = labels || s.map(n => this.getPowerCircuitLabel(owner, n));
        const consecutive = s.every((n, i) => i === 0 || n === s[i - 1] + 1);
        if (consecutive && s.length > 2) return `${names[0]} to ${names[names.length - 1]}`;
        if (names.length < 2) return names[0] || '';
        return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    }

    // The right-click entry: armed in the Power view on a run of the wall
    // the picks belong to, with two or more picked. Null everywhere else.
    _prepareMergeCircuitsMenu(x, y) {
        const r = window.canvasRenderer;
        if (!r || !r.canvas || r.viewMode !== 'power' || this._mergeRedraw) return null;
        const rect = r.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
        const worldY = ((y - rect.top) - r.panY) / r.zoom;
        const worldX = r._unmirrorWorldX(((x - rect.left) - r.panX) / r.zoom, worldY);
        const run = this.runAtPoint(worldX, worldY);
        if (!run || run.kind !== 'power') return null;
        const owner = run.layer;
        const nums = this.circuitPicksFor(owner);
        if (nums.length < 2) return null;
        const list = this._circuitNumbersText(owner, nums);
        const first = this.getPowerCircuitLabel(owner, nums[0]);
        return {
            kind: 'power',
            label: `Redraw circuits ${list} as one`,
            title: `Free the cabinets of these circuits and draw them as one circuit, `
                + `${first}; the circuits after it close up. Click the cabinets in order. `
                + 'Enter keeps it, Esc puts the circuits back.',
            run: () => this.beginCircuitMergeRedraw(owner, nums),
        };
    }

    // The picked circuits of `owner` as the wall reads them now:
    // [{ num, runs (the drawn numbers of a custom circuit), hits }].
    _mergeCircuitInfo(owner, nums) {
        this._circuitTailCache = null;
        const custom = this.isCustomPower(owner);
        return this.screenCircuits(owner)
            .filter(c => nums.includes(c.num))
            .map(c => ({
                num: c.num,
                runs: custom ? (c.runIds || [c.num]).map(n => parseInt(n, 10)) : [c.num],
                hits: (c.panels || []).map((panel, i) => ({
                    layer: (c.layers && c.layers[i]) || owner, panel,
                })).filter(h => h.panel && this._panelOnWall(h.layer, h.panel)),
            }));
    }

    // Picks whose cabinets one circuit cannot carry: the message saying so,
    // or null when they fit. One circuit's limit is the figure every custom
    // circuit is drawn against (customRunCapacity: 80% of the breaker on a
    // US screen; a 2fer or 3fer shares that same breaker).
    _mergeCircuitCapacityRefusal(owner, list, hits) {
        if (!hits.length) return null;
        const cap = this.customRunCapacity(owner, 'power');
        if (!cap.known) return null;
        const load = this.customRunLoad(owner, 'power', hits);
        if (load <= cap.limit + 1e-6) return null;
        const sized = this._customRunSizing(owner, 'power', hits.map(h => h.layer), cap);
        const circuits = `Circuits ${list}`;
        const n = hits.length;
        const w = v => Math.round(v).toLocaleString('en-US');
        if (!sized.mixed && n > sized.count) {
            return `${circuits} hold ${n} panels together, and one circuit takes ${sized.describe}. `
                + 'Pick fewer circuits to redraw as one.';
        }
        return `${circuits} draw ${w(load)} W together, and one circuit takes ${w(cap.limit)} W `
            + `at ${cap.at}. Pick fewer circuits to redraw as one.`;
    }

    // Open the session: free the picked circuits' cabinets, close the
    // numbers up behind the first, and open the first for drawing.
    beginCircuitMergeRedraw(owner, nums) {
        owner = this._liveLayer(owner);
        if (!owner || this._mergeRedrawLive()) return false;
        // A redraw open now ends first: the walk it holds is the one the
        // picks are read on.
        if (this._overrideEditing) this.endOverrideEdit();
        owner = this._liveLayer(owner);
        const want = [...new Set((nums || []).map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1))];
        const info = this._mergeCircuitInfo(owner, want);
        const picks = info.map(c => c.num).sort((a, b) => a - b);
        if (picks.length < 2) return false;
        const labels = picks.map(n => this.getPowerCircuitLabel(owner, n));
        const list = this._circuitNumbersText(owner, picks, labels);
        const freed = info.flatMap(c => c.hits);
        // A locked screen stays unchanged (the owner's standing rule): the
        // wall's owner, or any screen a picked circuit's cabinets sit on.
        const locked = new Map();
        if (this._layerLocked(owner)) locked.set(owner.id, owner);
        freed.forEach(h => { if (this._layerLocked(h.layer)) locked.set(h.layer.id, h.layer); });
        if (locked.size) {
            this._showLockedError([...locked.values()]);
            sendClientLog('merge_runs_refused', { kind: 'power', layerId: owner.id, why: 'locked' });
            return false;
        }
        // More than one circuit carries: refused before anything is freed.
        const full = this._mergeCircuitCapacityRefusal(owner, list, freed);
        if (full) {
            if (typeof this._toast === 'function') this._toast(full, true, 8000);
            sendClientLog('merge_runs_refused', {
                kind: 'power', layerId: owner.id, why: 'capacity', picks, cabinets: freed.length,
            });
            return false;
        }
        this._flushPendingSaveState();
        const baseEntry = (this.history && this.history[this.historyIndex]) || null;
        const pullBefore = typeof this._pullLiveRowKeys === 'function'
            ? this._pullLiveRowKeys() : null;
        const custom = this.isCustomPower(owner);
        const first = picks[0];
        // The first circuit's own name and cable stay on the new circuit.
        const keepLabel = (owner.powerLabelOverrides || {})[first];
        const keepCable = (owner.powerCircuitCables || {})[first];
        // Moving a circuit can move a locked screen's circuits on a multi
        // box it shares: put back then, the screen named.
        const shared = this._lockedPowerTrial();
        const held = new Set(freed.map(h => this.getScopedPanelKey(h.layer.id, h.panel)));
        let touched = [owner];
        let carried = [];
        if (custom) {
            // Every picked circuit comes off its multi the way Clear Circuit
            // takes one off, every other circuit kept on its distro, multi
            // and tail; then the drawn numbers close up behind the first.
            const r = this._removeCircuitsKeepFeeds(owner, info.map(c => ({ num: c.num, runs: c.runs })));
            touched = r.touched;
            const gone = info.flatMap(c => c.runs).filter(n => n !== first);
            this._closeUpCircuitNumbers(owner, gone);
            if (!owner.powerCustomPaths) owner.powerCustomPaths = {};
            owner.powerCustomPaths[first] = [];
            owner.powerCustomIndex = first;
        } else {
            carried = this._closeUpTakenCircuits(owner, picks, held, () => {
                this._mergeRedraw = { kind: 'power', layerId: owner.id, num: first,
                    picks, labels, custom, held, baseEntry, ready: false };
            });
        }
        if (keepLabel !== undefined) {
            owner.powerLabelOverrides = owner.powerLabelOverrides || {};
            owner.powerLabelOverrides[first] = keepLabel;
        }
        if (keepCable !== undefined) {
            owner.powerCircuitCables = owner.powerCircuitCables || {};
            owner.powerCircuitCables[first] = keepCable;
        }
        if (shared()) {
            this._mergeRedraw = null;
            this._circuitTailCache = null;
            sendClientLog('merge_runs_refused', { kind: 'power', layerId: owner.id, why: 'shared' });
            if (window.canvasRenderer) window.canvasRenderer.render();
            return false;
        }
        this._mergeRedraw = { kind: 'power', layerId: owner.id, num: first,
            picks, labels, custom, held, baseEntry, ready: false };
        if (this.powerCustomSelection) this.powerCustomSelection.clear();
        this._portPicks = null;
        this._sweepSelection = null;
        if (pullBefore) this._dropPullEditsGoneWith(pullBefore);
        // The session's first history entry; every click after it is
        // folded into one step when the drawing is kept.
        this._activateRunForEdit(owner, 'power', first, 'Redraw Circuits As One');
        this._mergeRedraw.ready = true;
        this.updateLayers([...new Set([...this._pathPersistLayers(owner), ...touched, ...carried])]);
        sendClientLog('merge_runs_begin', {
            kind: 'power', layerId: owner.id, picks, custom, freed: freed.length,
        });
        if (typeof this._toast === 'function') {
            this._toast(`Draw circuit ${this.getPowerCircuitLabel(owner, first)}: click the cabinets `
                + `in order. Enter keeps it, Esc puts circuits ${list} back.`, false, 6000);
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // An AUTOMATIC screen: the picked circuits taken over by hand go, the
    // first number becomes a taken-over circuit with nothing drawn yet, and
    // every circuit taken over after them closes up (the walk numbers the
    // rest around them, so its circuits close up on their own). `open`
    // raises the session, so the walk leaves the freed cabinets alone while
    // the circuits are read again. Typed names and cables follow their
    // cabinets onto the new numbers; the picks' own are dropped here (the
    // caller puts the first one's back). Model only. Returns the screens a
    // carried cable was written on.
    _closeUpTakenCircuits(owner, picks, held, open) {
        const before = this._circuitCabinetKeys(owner);
        const carry = this._cableCarryBegin([owner]);
        ['powerLabelOverrides', 'powerCircuitCables'].forEach(key => {
            const store = owner[key];
            if (store) picks.forEach(n => { delete store[n]; });
        });
        const first = picks[0];
        const removed = picks.slice(1);
        const shift = n => n - removed.filter(r => r < n).length;
        const ovr = this.getOverrideNums(owner, 'power');
        const old = owner.powerCustomPaths || {};
        const paths = {};
        // A drawing left from an earlier custom spell (unused here) stays
        // where it is, unless a live circuit's number lands on it.
        Object.keys(old).forEach(k => {
            const n = parseInt(k, 10);
            if (!Number.isFinite(n)) { paths[k] = old[k]; return; }
            if (!ovr.includes(n)) paths[n] = old[k];
        });
        const next = [];
        ovr.forEach(n => {
            if (picks.includes(n)) return;
            paths[shift(n)] = old[n];
            next.push(shift(n));
        });
        paths[first] = [];
        next.push(first);
        owner.powerCustomPaths = paths;
        owner.powerCustomOverrides = [...new Set(next)].sort((a, b) => a - b);
        owner.powerCustomIndex = first;
        open();
        this._circuitTailCache = null;
        const moves = this._portMovesByCabinet(before, this._circuitCabinetKeys(owner));
        this._followCircuitLabelsByCabinet(owner, moves);
        this._cableCarryApply(carry);
        sendClientLog('merge_runs_renumbered', {
            kind: 'power', layerId: owner.id,
            moved: [...moves].filter(([n, to]) => to !== null && to !== n),
        });
        return carry.changed;
    }

    // A CUSTOM screen: the drawn numbers `gone` go and every later number
    // closes up, with everything kept by number (the typed name, the
    // cable, the manual share groups, the active circuit, and the taken-
    // over numbers an automatic spell left). Model only.
    _closeUpCircuitNumbers(owner, gone) {
        const out = [...new Set((gone || []).map(n => parseInt(n, 10))
            .filter(n => Number.isFinite(n) && n >= 1))].sort((a, b) => a - b);
        if (!owner || !out.length) return;
        const shift = n => n - out.filter(r => r < n).length;
        const move = (key) => {
            const store = owner[key];
            if (!store || typeof store !== 'object') return;
            const moved = {};
            Object.keys(store).forEach(k => {
                const n = parseInt(k, 10);
                if (!Number.isFinite(n)) { moved[k] = store[k]; return; }
                if (out.includes(n)) return;
                moved[shift(n)] = store[k];
            });
            owner[key] = moved;
        };
        move('powerCustomPaths');
        move('powerLabelOverrides');
        move('powerCircuitCables');
        const kept = this.getOverrideNums(owner, 'power');
        if (kept.length) owner.powerCustomOverrides = kept.filter(n => !out.includes(n)).map(shift);
        const raw = owner.powerSplitters;
        if (raw && raw.manual && this._splitterManualSpace(owner) === 'custom') {
            const cur = this._ownPowerSplitters(owner);
            const step = n => {
                const v = parseInt(n, 10);
                return Number.isFinite(v) ? shift(v) : n;
            };
            const live = n => !out.includes(parseInt(n, 10));
            owner.powerSplitters = { ...cur, manual: {
                merge: cur.manual.merge
                    .map(g => (Array.isArray(g) ? g.filter(live).map(step) : g))
                    .filter(g => !Array.isArray(g) || g.length >= 2),
                split: cur.manual.split.filter(live).map(step),
                space: 'custom',
            } };
        }
        owner.powerCustomIndex = Math.max(1, shift(parseInt(owner.powerCustomIndex, 10) || 1));
        this._circuitTailCache = null;
    }

    // "2 cabinets left over went to circuits S1-6, S1-7." - where the freed
    // cabinets `keys` the drawing did not take sit now that nothing holds
    // them: on an automatic screen the walk took them, on a custom one they
    // are unwired.
    _leftoverCircuitsNote(owner, keys) {
        const n = (keys || []).length;
        if (!owner || !n) return '';
        const cabs = `${n} cabinet${n === 1 ? '' : 's'} left over`;
        if (this.isCustomPower(owner)) return `${cabs} ${n === 1 ? 'is' : 'are'} unwired now.`;
        const want = new Set(keys);
        const nums = new Set();
        this._circuitTailCache = null;
        this.screenCircuits(owner).forEach(c => (c.panels || []).forEach((p, i) => {
            const at = (c.layers && c.layers[i]) || owner;
            if (want.has(this.getScopedPanelKey(at.id, p))) nums.add(c.num);
        }));
        if (!nums.size) return `${cabs} went back to the automatic circuits.`;
        const labels = [...nums].sort((a, b) => a - b).map(x => this.getPowerCircuitLabel(owner, x));
        return `${cabs} went to ${labels.length === 1 ? 'circuit' : 'circuits'} ${labels.join(', ')}.`;
    }

    // Keep the drawing (finishMergeRedraw for a power session): the
    // session's steps fold into ONE history entry. The freed cabinets the
    // drawing did not take go back to the walk on an automatic screen, the
    // circuits after them renumbering with their names and cables, or stay
    // unwired on a custom one.
    _finishCircuitMergeRedraw(s) {
        const owner = (this.project.layers || []).find(l => l.id === s.layerId);
        const path = ((owner && owner.powerCustomPaths) || {})[s.num] || [];
        const list = this._circuitNumbersText(owner, s.picks, s.labels);
        if (!owner || path.length === 0) {
            this.cancelMergeRedraw(`Nothing was drawn, so circuits ${list} stay as they were.`);
            return false;
        }
        const drawnKeys = new Set(path.filter(Boolean)
            .map(e => this.getScopedPanelKey(this.getPathEntryLayerId(owner, e), e)));
        const left = [...(s.held || [])].filter(k => !drawnKeys.has(k));
        let carried = [];
        const before = !s.custom && left.length ? this._circuitCabinetKeys(owner) : null;
        const carry = before ? this._cableCarryBegin([owner]) : null;
        this._mergeRedraw = null;
        const ed = this._overrideEditing;
        if (ed && ed.kind === 'power' && ed.layerId === owner.id) this._overrideEditing = null;
        this._powerHeld = null;
        if (before) {
            this._circuitTailCache = null;
            const moves = this._portMovesByCabinet(before, this._circuitCabinetKeys(owner));
            this._followCircuitLabelsByCabinet(owner, moves);
            this._cableCarryApply(carry);
            carried = carry.changed;
        }
        const idx = this.history.indexOf(s.baseEntry);
        if (idx >= 0) {
            this.history = this.history.slice(0, idx + 1);
            this.historyIndex = idx;
        }
        if (this.powerCustomSelection) this.powerCustomSelection.clear();
        this._circuitTailCache = null;
        this.saveState('Redraw Circuits As One');
        this._notePowerRedraw();
        this.saveClientSideProperties();
        this.updateLayers([...new Set([...this._pathPersistLayers(owner), ...carried])]);
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        if (typeof this.updateUI === 'function') this.updateUI();
        sendClientLog('merge_runs_kept', {
            kind: 'power', layerId: owner.id, num: s.num, picks: s.picks,
            drawn: path.length, left: left.length,
        });
        if (typeof this._toast === 'function') {
            const leftover = left.length ? ` ${this._leftoverCircuitsNote(owner, left)}` : '';
            this._toast(`Circuits ${list} are now circuit `
                + `${this.getPowerCircuitLabel(owner, s.num)}.${leftover}`, false, left.length ? 8000 : 4000);
        }
        if (carry) this._cableCarrySay(carry);
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // What Esc says when it puts the open redraw back.
    _mergeRedrawBackText() {
        const s = this._mergeRedraw;
        if (!s) return '';
        if (s.kind === 'power') {
            const owner = (this.project.layers || []).find(l => l.id === s.layerId);
            return `Circuits ${this._circuitNumbersText(owner, s.picks, s.labels)} are back as they were.`;
        }
        return `Ports ${this._portNumbersText(s.picks)} are back as they were.`;
    }
}

for (const k of Object.getOwnPropertyNames(_MergeCircuits.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_MergeCircuits.prototype, k));
    }
}
