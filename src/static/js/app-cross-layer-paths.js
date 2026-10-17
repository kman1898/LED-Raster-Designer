// app-cross-layer-paths: cross-member manual paths for LEDRasterApp - the
// scope a hand-drawn port or circuit may reach, how a path step names a
// peer member's cabinet, and how a step resolves back to a cabinet (or
// reads as dangling). Also the owner lookups a conflicting click asks.
import { LEDRasterApp } from './app-core.js';

// The fields of a screen a lock does not hold (_holdLockedLayers): the lock
// itself, visibility (the eye button is not a change to the screen), and the
// leading-underscore render caches the canvas keeps on the layer.
const LOCK_EXEMPT_FIELD = (k) => k === 'locked' || k === 'visible' || k.charAt(0) === '_';

// The events of a control that is still moving: a keystroke in a field, a
// slider or colour drag. An edit the funnel holds back from a locked screen
// during one of these is reported, but the fields are not repainted until
// the commit (change, blur, pointer up) - a repaint mid-edit rewrote the very
// field being typed in.
const LIVE_EDIT_EVENTS = new Set(['input', 'mousemove', 'pointermove', 'touchmove', 'drag']);
// The moves of a pointer drag: its attempt ends on the button's release.
const POINTER_MOVE_EVENTS = new Set(['mousemove', 'pointermove', 'touchmove', 'drag']);

class _CrossLayerPaths {

    // ── Cross-member manual paths (v0.11.0, step 6) ──────────────────────
    //
    // A group IS ONE WALL, so a hand-drawn port path or power circuit has to
    // be allowed to run off one member and onto the next. The path itself
    // never moves: it stays on the layer that OWNS the port or circuit -
    // a port is a physical output on ONE processor - and only the individual
    // step learns where the cable landed.
    //
    //     {row, col}            a panel in the OWNING layer. Unchanged, and
    //                           the shape 100% of existing projects have.
    //     {row, col, layerId}   a panel in a PEER member of the same group.
    //
    // Why a key on the STEP rather than a new key on the layer: the server's
    // add / update allow-lists silently DROP layer keys they do not know,
    // which has already cost this codebase two features (processorType,
    // lowLatency). A step lives inside customPortPaths, which is already
    // allow-listed, so it rides in for free.
    //
    // Why (layerId, row, col) rather than panel.id: _build_panels regenerates
    // panel ids on every geometry rebuild, so an id is worthless the moment
    // anyone changes a column count. (row, col) is the only durable address.
    //
    // Every helper below returns the ungrouped answer for an ungrouped layer,
    // and a path with no layerId anywhere reads exactly as it did before, so a
    // project without groups takes precisely the code path it took before.

    // The canvas a manual path treats a layer as living on. Paths are only
    // ever drawn in Data Flow and Power, which are both Show Look views, so
    // the show override is the right answer REGARDLESS of which tab is open.
    // Deliberately NOT canvasRenderer._effectiveLayerCanvasId, which flips
    // with viewMode: reachability that changed the moment the user clicked the
    // Pixel Map tab would mean the same stored step resolving on one tab and
    // reading as dangling on another.
    _pathCanvasIdOf(layer) {
        if (!layer) return null;
        return layer.show_canvas_id || layer.canvas_id || null;
    }

    // Every layer a path owned by `layer` may legally touch. The owner is
    // always first, so callers that want "the owner, then its peers" get a
    // stable order without re-sorting.
    getPathScopeLayers(layer) {
        if (!layer) return [];
        const group = (typeof this.getGroupOfLayer === 'function')
            ? this.getGroupOfLayer(layer) : null;
        if (!group) return [layer];
        const cid = this._pathCanvasIdOf(layer);
        const scope = [layer];
        (this.getGroupMembers(group) || []).forEach(m => {
            if (!m || m.id === layer.id) return;
            if ((m.type || 'screen') !== 'screen') return;
            // The same rule canvas.js _groupDrawnMembers applies: a member
            // sitting on another canvas is a different workspace entirely, so
            // a cable drawn onto it would be drawn at a position that means
            // nothing. Hidden members are NOT excluded here (where
            // _groupDrawnMembers does exclude them) - hiding a screen must not
            // quietly invalidate paths the user already drew onto it, because
            // unhiding has to bring them straight back.
            if (this._pathCanvasIdOf(m) !== cid) return;
            scope.push(m);
        });
        return scope;
    }

    // ---- Clearing hand-drawn runs on a grouped screen -----------------------
    //
    // A group is one wall, and a run a member owns may sit on a peer's
    // cabinets: the owner is whichever screen was current when it was drawn.
    // Clear Circuit / Clear Port and Clear All used to reach only the current
    // layer's own runs, so a run a peer drew across this screen stayed put with
    // nothing on this screen able to remove it (Matt, 2026-09-22, on a
    // two-member wall where SL's circuit 1 was 13 cabinets of SR - "S1-1
    // can't be cleared ... nor have a way to delete it").
    //
    // clearCustomRun: the current layer's run `num` goes, and every peer's run
    // `num` that lands on this layer goes WHOLE - its steps on the peer and
    // on any third member included, with its override for `num` let go
    // (Matt's ruling, 2026-09-23, on a two-member wall: Screen3's 16 circuits
    // each ran 7 cabinets of Screen2 then 7 of its own, and Clear Circuit on
    // Screen2 left every one of them half-drawn - "a group is one screen and
    // a circuit is one circuit"). Until then a peer's run only LOST the steps
    // on this layer, which cut one physical cable into a stub nobody drew.
    // A peer's run `num` that never touches this layer is a different cable
    // on a different distro or processor output (numbers are per member -
    // see _findPathOwner) and is left alone, so a Clear that finds nothing
    // here still changes nothing. clearAllCustomRuns: every member of the
    // path scope drops all its runs and overrides - the wall is back to
    // automatic. Both return {touched, skipped}: the layers written, for the
    // PUT (_persistWith adds them to the selection), and the members left
    // alone because they are locked, for the toast.
    //
    // An emptied run's key is DELETED, on the clicked screen as on a peer
    // (2026-09-22). Every reader goes through `paths[num] || []` or filters
    // Object.keys by length, so `[]` and no key read the same; one shape means
    // one shape on the wire and in undo snapshots.
    //
    // Only a member that HELD something is written and returned in `touched`
    // (2026-09-22): a Clear that finds nothing on a member must leave it
    // byte-identical. Both used to run `ensure` on every member and write
    // `{}` / 1 / `[]` onto the ones that had nothing, which made saveState's
    // serialized compare see a change - a Clear All that cleared nothing
    // still took an undo step and a PUT. With nothing touched the handlers
    // (app-wiring.js) skip the snapshot and the PUT altogether.
    //
    // A LOCKED SCREEN STAYS UNCHANGED until it is unlocked (the owner's
    // ruling, 2026-10-16: "If it's locked it stays locked and unchanged until
    // unlocked. If you try to change it shows an error dialog and tells why
    // it can't change."). This replaces the 2026-09-22 rule, under which the
    // CLICKED screen was cleared even when locked. Now no Clear removes a run
    // that a locked screen owns or that crosses a locked screen's cabinets
    // (_runLockedLayers) - the clicked screen included - because either way a
    // locked screen would change on the canvas. Such a run is kept whole and
    // the locked screens are named in one error (_showLockedError).
    _customRunKeys(kind) {
        return kind === 'power'
            ? { paths: 'powerCustomPaths', index: 'powerCustomIndex',
                overrides: 'powerCustomOverrides', ensure: 'ensureCustomPowerState' }
            : { paths: 'customPortPaths', index: 'customPortIndex',
                overrides: 'customPortOverrides', ensure: 'ensureCustomFlowState' };
    }

    // The way returnRunToAuto lets go of a number: an automatic member whose
    // override run `num` was just emptied by a peer's Clear would otherwise
    // keep `num` reserved with nothing drawn - an invisible gap in its
    // numbering with no route back except Clear All.
    _dropRunOverride(owner, kind, num) {
        const k = this._customRunKeys(kind);
        const nums = (typeof this.getOverrideNums === 'function') ? this.getOverrideNums(owner, kind) : [];
        if (nums.includes(num)) owner[k.overrides] = nums.filter(n => n !== num);
        const s = this._overrideEditing;
        if (s && s.kind === kind && s.layerId === owner.id && s.num === num) {
            this._overrideEditing = null;
        }
    }

    // A power run cleared is a circuit gone: its typed cable (the "25'
    // True1" on the circuit, powerCircuitCables) goes with it, so a run
    // drawn later under the same number starts blank (owner, 2026-10-17:
    // the lengths go with the feed). The callers only reach here for a
    // member they may write - a locked one is skipped before this.
    _forgetRunCable(member, kind, num) {
        if (kind !== 'power' || !member || !member.powerCircuitCables) return;
        delete member.powerCircuitCables[num];
    }

    // This layer's run `num`, and - whole - every peer's run `num` with a
    // step on this layer (2026-09-23, "a circuit is one circuit"; see the
    // section comment above). A run that touches a locked screen is kept
    // whole and its locked screens are reported in `skipped`.
    clearCustomRun(layer, kind, num) {
        if (!layer) return { touched: [], skipped: [] };
        const k = this._customRunKeys(kind);
        const pullBefore = this._pullLiveRowKeys();
        const touched = [];
        const skipped = new Map();
        const own = layer[k.paths];
        if (own && Object.prototype.hasOwnProperty.call(own, num)) {
            const locked = this._runLockedLayers(layer, kind, num);
            if (locked.length) {
                locked.forEach(l => skipped.set(l.id, l));
            } else {
                delete own[num];
                this._forgetRunCable(layer, kind, num);
                touched.push(layer);
            }
        }
        this.getPathScopeLayers(layer).forEach(peer => {
            if (!peer || peer.id === layer.id) return;
            const paths = peer[k.paths];
            if (!paths || !Array.isArray(paths[num]) || paths[num].length === 0) return;
            const lands = paths[num].some(e => this.getPathEntryLayerId(peer, e) === layer.id);
            if (!lands) return;
            const locked = this._runLockedLayers(peer, kind, num);
            if (locked.length) { locked.forEach(l => skipped.set(l.id, l)); return; }
            delete paths[num];
            this._dropRunOverride(peer, kind, num);
            this._forgetRunCable(peer, kind, num);
            touched.push(peer);
        });
        // An edit on a pull-sheet row the clear took away goes with it -
        // before the caller's snapshot, so undo brings both back.
        if (touched.length) this._dropPullEditsGoneWith(pullBefore);
        return { touched, skipped: [...skipped.values()] };
    }

    // Every member's runs go, and the wall is back to automatic - except a
    // run that touches a locked screen (a locked member's own runs, or an
    // unlocked member's run across a locked member's cabinets), which is kept
    // whole with its override, and its locked screens are reported.
    clearAllCustomRuns(layer, kind) {
        if (!layer) return { touched: [], skipped: [] };
        const k = this._customRunKeys(kind);
        const pullBefore = this._pullLiveRowKeys();
        const touched = [];
        const skipped = new Map();
        this.getPathScopeLayers(layer).forEach(member => {
            if (!member) return;
            const paths = member[k.paths] || {};
            const drawnNums = Object.keys(paths).filter(n => (paths[n] || []).length > 0);
            const overrides = (typeof this.getOverrideNums === 'function')
                ? this.getOverrideNums(member, kind) : [];
            const drawn = drawnNums.length > 0 || overrides.length > 0;
            if (member.locked) {
                // Reported only when there was something to leave alone.
                if (drawn) skipped.set(member.id, member);
                return;
            }
            // Runs kept because they cross a locked member's cabinets.
            const kept = {};
            drawnNums.forEach(n => {
                const num = Number.isFinite(Number(n)) ? Number(n) : n;
                const locked = this._runLockedLayers(member, kind, num);
                if (!locked.length) return;
                locked.forEach(l => skipped.set(l.id, l));
                kept[n] = paths[n];
            });
            const keptNums = Object.keys(kept);
            // A cleared circuit's cable goes with it (owner, 2026-10-17);
            // a run kept for a locked screen keeps its cable.
            const forget = () => drawnNums
                .filter(n => !keptNums.includes(n))
                .forEach(n => this._forgetRunCable(member, kind, n));
            if (keptNums.length > 0) {
                if (keptNums.length === Object.keys(paths).length) return;
                forget();
                member[k.paths] = kept;
                member[k.overrides] = overrides.filter(n => keptNums.includes(`${n}`));
                const s = this._overrideEditing;
                if (s && s.kind === kind && s.layerId === member.id
                        && !keptNums.includes(`${s.num}`)) {
                    this._overrideEditing = null;
                }
                touched.push(member);
                return;
            }
            // Anything Clear All would change: a run key (an emptied `[]`
            // included - one shape, see above), an override entry, or an
            // index off 1.
            const index = member[k.index];
            const held = drawn || Object.keys(paths).length > 0
                || (Array.isArray(member[k.overrides]) && member[k.overrides].length > 0)
                || (index !== undefined && index !== null && Number(index) !== 1);
            if (!held) return;
            forget();
            member[k.paths] = {};
            member[k.index] = 1;
            member[k.overrides] = [];
            if (this._overrideEditing && this._overrideEditing.kind === kind
                    && this._overrideEditing.layerId === member.id) {
                this._overrideEditing = null;
            }
            touched.push(member);
        });
        if (touched.length) this._dropPullEditsGoneWith(pullBefore);
        return { touched, skipped: [...skipped.values()] };
    }

    // The locked screens one run touches: its owner when the owner is
    // locked, and every locked screen one of its cabinets sits on. A run
    // with any is frozen - clearing, refilling or overwriting it would
    // change a locked screen on the canvas.
    _runLockedLayers(owner, kind, num) {
        if (!owner) return [];
        const k = this._customRunKeys(kind);
        const out = new Map();
        if (owner.locked) out.set(owner.id, owner);
        const path = (owner[k.paths] && owner[k.paths][num]) || [];
        path.forEach(e => {
            const target = this.resolvePathEntryLayer(owner, e);
            if (target && target.locked) out.set(target.id, target);
        });
        return [...out.values()];
    }

    // The one error every custom-mode change gives when it meets a locked
    // screen, naming each one: "Upper is locked - unlock it to change it."
    // An error toast (the app's error style), up a little longer than the
    // default so a list of names can be read.
    _showLockedError(layers) {
        if (!layers || layers.length === 0 || typeof this._toast !== 'function') return;
        const seen = new Set();
        const names = [];
        layers.forEach(l => {
            if (!l || seen.has(l.id)) return;
            seen.add(l.id);
            names.push(l.name || `Screen ${l.id}`);
        });
        if (names.length === 0) return;
        const one = names.length === 1;
        const list = one ? names[0]
            : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
        const msg = one
            ? `${list} is locked - unlock it to change it.`
            : `${list} are locked - unlock them to change them.`;
        // One gesture, one error: a verb guarded at its entry and again in
        // the setter it calls would otherwise say the same thing twice in
        // the same turn. An action that runs on across awaits (a chain of
        // server requests) opens a scope (_beginLockedAction) and says each
        // error once for the whole action. A later action says it again.
        if (this._lockedErrorThisTurn === msg) return;
        const scopes = this._lockedActions;
        if (scopes && scopes.size) {
            for (const scope of scopes) if (scope.said.has(msg)) return;
            scopes.forEach(scope => scope.said.add(msg));
        }
        this._lockedErrorThisTurn = msg;
        Promise.resolve().then(() => { this._lockedErrorThisTurn = null; });
        this._toast(msg, true, 5000);
    }

    // One action for the locked error, from here until the returned end()
    // is called - however many awaits lie between: each error is said once
    // within it. Call end() in a finally.
    _beginLockedAction() {
        if (!this._lockedActions) this._lockedActions = new Set();
        const scope = { said: new Set() };
        this._lockedActions.add(scope);
        return () => { this._lockedActions.delete(scope); };
    }

    // Stepping the active port or circuit (Tab, [ / ], Prev / Next, the
    // menu items, typing a number in the active box) is a change too, so a
    // locked screen refuses it with the same error (the owner's ruling,
    // 2026-10-16: "Block it too"). True when the step must not happen.
    _lockedStepRefused(layer) {
        if (!layer || !layer.locked) return false;
        this._showLockedError([layer]);
        return true;
    }

    // THE LOCK GUARDS EVERYTHING (the owner's ruling, 2026-10-16): a locked
    // screen stays unchanged until it is unlocked - not only its position -
    // and every change that meets one says so. The helpers below are the
    // shared shape of that rule; the lock toggle itself, visibility and
    // selection are not changes and never come through here.
    //
    // True when any of `layers` (one layer or a list) is locked; the locked
    // ones are named in the one error. For a change that must happen whole
    // or not at all.
    _lockedRefused(layers) {
        const list = (Array.isArray(layers) ? layers : [layers]).filter(Boolean);
        const locked = list.filter(l => l.locked);
        if (locked.length === 0) return false;
        this._showLockedError(locked);
        return true;
    }

    // The screens a change may touch: `layers` less the locked ones, which
    // are named in the one error. The unlocked ones still take the change.
    _writableLayers(layers) {
        const list = (layers || []).filter(Boolean);
        const locked = list.filter(l => l.locked);
        if (locked.length === 0) return list;
        this._showLockedError(locked);
        return list.filter(l => !l.locked);
    }

    // A HOLD on the locked screens among `layers` for the edit funnels
    // (applyToSelectedLayers, updateLayerFromInputs), which run one handler
    // over the whole selection. Every field of each locked screen is
    // recorded; release() puts back any field the handler changed and
    // returns the screens it had to put back. So a locked screen comes out
    // byte-identical, and it is reported only when the edit would really
    // have changed it - setting a field to the value it already has is not
    // a change and says nothing. `locked`, `visible` and the
    // leading-underscore render caches are not the screen's content and are
    // never held.
    _holdLockedLayers(layers) {
        const held = [];
        (layers || []).forEach(layer => {
            if (!layer || !layer.locked) return;
            const fields = new Map();
            Object.keys(layer).forEach(k => {
                if (LOCK_EXEMPT_FIELD(k)) return;
                fields.set(k, JSON.stringify(layer[k] === undefined ? null : layer[k]));
            });
            held.push({ layer, fields });
        });
        return {
            release: () => {
                const changed = [];
                held.forEach(({ layer, fields }) => {
                    let touched = false;
                    Object.keys(layer).forEach(k => {
                        if (LOCK_EXEMPT_FIELD(k) || fields.has(k)) return;
                        // A field the handler added goes again; an empty
                        // one (an ensure-style `{}` / `[]` / null) reads
                        // the same as no field and is not reported.
                        const added = JSON.stringify(layer[k] === undefined ? null : layer[k]);
                        delete layer[k];
                        if (added !== 'null' && added !== '{}' && added !== '[]') touched = true;
                    });
                    fields.forEach((json, k) => {
                        const now = JSON.stringify(layer[k] === undefined ? null : layer[k]);
                        if (now === json) return;
                        layer[k] = JSON.parse(json);
                        touched = true;
                    });
                    if (touched) changed.push(layer);
                });
                return changed;
            },
        };
    }

    // The screens a Delete may remove, out of `ids`: never a locked one, and
    // never the last unlocked member of a group a locked screen would be
    // left alone in - a group of one is dissolved, which would change the
    // locked screen's group. Returns { ids, locked } with the locked screens
    // that held something back, for the one error.
    _deletableLayerIds(ids) {
        const layers = (this.project && this.project.layers) || [];
        const byId = new Map(layers.map(l => [l.id, l]));
        const locked = new Map();
        let keep = (ids || []).filter(id => {
            const l = byId.get(id);
            if (l && l.locked) { locked.set(l.id, l); return false; }
            return true;
        });
        const going = new Set(keep);
        const heldGroups = new Set();
        keep.forEach(id => {
            const l = byId.get(id);
            if (!l || !l.group_id || heldGroups.has(l.group_id)) return;
            const members = typeof this.groupMembersOf === 'function' ? this.groupMembersOf(l) : [];
            const left = members.filter(m => !going.has(m.id));
            const lockedLeft = left.filter(m => m.locked);
            if (lockedLeft.length && left.length < 2) {
                heldGroups.add(l.group_id);
                lockedLeft.forEach(m => locked.set(m.id, m));
            }
        });
        if (heldGroups.size) {
            keep = keep.filter(id => {
                const l = byId.get(id);
                return !(l && l.group_id && heldGroups.has(l.group_id));
            });
        }
        return { ids: keep, locked: [...locked.values()] };
    }

    // The error for an edit the funnel held back from locked screens, said
    // ONCE PER ATTEMPT on a control: a colour drag or typing fires the
    // handler on every input, and the commit (change / blur / release) runs
    // it once more - one error for all of it, Tab or Enter included.
    //
    // The fields are repainted so a locked screen's own values snap back -
    // but only on the commit, never mid-edit (a repaint on every keystroke
    // rewrote the field being typed in to the selection's "mixed" value, and
    // a slider snapped back under the pointer), and never into the focused
    // field. The repaint waits for the commit's own event sequence to finish
    // (a Tab's change, blur and focus), so it sees where focus landed.
    //
    // The attempt is read from the event being handled (window.event): an
    // `input` or a pointer move is live; anything else - a change, a key, a
    // release, or no event at all (a programmatic call) - is a commit.
    _reportLockedEdit(layers) {
        const list = (layers || []).filter(Boolean);
        const ev = (typeof window !== 'undefined' && window.event) || null;
        const live = !!(ev && LIVE_EDIT_EVENTS.has(ev.type));
        if (list.length) {
            const ids = [...new Set(list.map(l => l.id))].sort().join(',');
            const target = ev && ev.target && ev.target.nodeType === 1 ? ev.target : null;
            const now = Date.now();
            const last = this._lastLockedEditReport;
            // A native colour input fires `change` over and over while the
            // macOS picker is dragged: each is a commit, but one drag is one
            // attempt, so a change on the same colour input moments after
            // the last says nothing more.
            const colourStream = !!(last && target && target.type === 'color'
                && last.el === target && now - last.at < 1500);
            const sameAttempt = !!(last && last.ids === ids && (last.open || colourStream
                || (ev && (last.ev === ev || last.closedBy === ev))));
            if (!sameAttempt) this._showLockedError(list);
            this._lastLockedEditReport = {
                ids, ev, open: live, el: target, at: now,
                pointer: !!(ev && POINTER_MOVE_EVENTS.has(ev.type)),
            };
            this._lockedRepaintPending = true;
            if (live) {
                this._watchLockedEditEnd();
                return;
            }
        }
        if (!live) this._lockedEditSettled();
    }

    // A commit reached the funnel (or an attempt ended without one): close
    // the open attempt, so the next one says its error again, and repaint
    // the fields if a held-back edit is waiting for it.
    _lockedEditSettled() {
        const last = this._lastLockedEditReport;
        if (last) {
            last.open = false;
            // A second handler of the same commit event is the same attempt.
            const ev = (typeof window !== 'undefined' && window.event) || null;
            if (ev) last.closedBy = ev;
        }
        if (!this._lockedRepaintPending) return;
        this._lockedRepaintPending = false;
        if (this._lockedRepaintTimer) clearTimeout(this._lockedRepaintTimer);
        this._lockedRepaintTimer = setTimeout(() => {
            this._lockedRepaintTimer = null;
            this._repaintLockedFields();
        }, 0);
    }

    // True while a held-back edit's repaint is still to come (tests wait on
    // it going false).
    _lockedRepaintBusy() {
        return !!(this._lockedRepaintPending || this._lockedRepaintTimer);
    }

    // Screen Info and the sidebar repainted from the screens as they are,
    // except the field that has focus: it keeps what is in it, and the
    // baseline updateLayerFromInputs compares against is told so, so the
    // field does not read as edited later.
    _repaintLockedFields() {
        if (typeof this.loadLayerToInputs !== 'function') return;
        const el = typeof document !== 'undefined' ? document.activeElement : null;
        const keep = (el && el !== document.body && 'value' in el)
            ? { el, value: el.value, checked: el.checked } : null;
        if (keep) {
            try { keep.start = el.selectionStart; keep.end = el.selectionEnd; } catch (_) {}
        }
        try { this.loadLayerToInputs(); } catch (_) {}
        if (!keep) return;
        if (el.value !== keep.value) el.value = keep.value;
        if (el.checked !== keep.checked) el.checked = keep.checked;
        if (keep.start != null) {
            try { el.setSelectionRange(keep.start, keep.end); } catch (_) {}
        }
        if (el.id && this._screenInfoShown && typeof this._screenInfoState === 'function') {
            this._screenInfoShown.set(el.id, this._screenInfoState(el));
        }
    }

    // An attempt that never reaches a committing funnel call still ends:
    // when its field loses focus, or when the pointer drag that drove it is
    // released. Checked a task later, so a change event fired by the same
    // blur is the commit it should be.
    _watchLockedEditEnd() {
        if (this._lockedEditWatch || typeof document === 'undefined') return;
        this._lockedEditWatch = true;
        const end = (ev) => {
            const last = this._lastLockedEditReport;
            if (!last || !last.open) return;
            if (ev.type === 'focusout' ? last.el !== ev.target : !last.pointer) return;
            setTimeout(() => {
                if (this._lastLockedEditReport === last && last.open) this._lockedEditSettled();
            }, 0);
        };
        document.addEventListener('focusout', end, true);
        document.addEventListener('mouseup', end, true);
        document.addEventListener('pointerup', end, true);
    }

    _persistWith(touched) {
        const sel = this.getSelectedLayers() || [];
        const ids = new Set(sel.map(l => l && l.id));
        return sel.concat((touched || []).filter(l => l && !ids.has(l.id)));
    }

    // The layers a SELECTION owned by `layer` may touch: the path scope, less
    // the members the user cannot see.
    //
    // getPathScopeLayers deliberately keeps hidden members, because a path
    // already drawn onto a screen must survive that screen being hidden and
    // come straight back when it is unhidden. That is right for RESOLVING a
    // path and wrong for BUILDING one: a hidden member is not drawn
    // (canvas.js _groupDrawnMembers filters visible !== false) and cannot be
    // clicked (getPanelAt skips it), so a marquee, an arrow handoff or an
    // Apply Pattern that reached it wired cabinets nobody could see - 12 of
    // them, on a screen that is not on the canvas, into the visible screen's
    // port 1.
    //
    // The OWNER is never filtered out. It is the layer the user is working on
    // and the port belongs to it; dropping it would make a hidden current
    // layer un-drawable rather than merely un-reachable, and it keeps an
    // ungrouped screen byte-identical to before.
    //
    // `visible === false`, not `!visible`: a layer with no visible key is
    // visible everywhere else in this app (the server reads
    // layer.get('visible', True)).
    getSelectionScopeLayers(layer) {
        if (!layer) return [];
        return this.getPathScopeLayers(layer)
            .filter(l => l && (l.id === layer.id || l.visible !== false));
    }

    canPathReachLayer(ownerLayer, targetLayer) {
        if (!ownerLayer || !targetLayer) return false;
        if (ownerLayer.id === targetLayer.id) return true;
        return this.getPathScopeLayers(ownerLayer).some(l => l && l.id === targetLayer.id);
    }

    // The layer id a step names, resolving the plain form to the owner. Kept
    // separate from resolvePathEntryLayer because the conflict scan wants the
    // id without paying for a lookup and a legality check per step.
    getPathEntryLayerId(ownerLayer, entry) {
        const lid = entry ? entry.layerId : undefined;
        if (lid === undefined || lid === null) return ownerLayer ? ownerLayer.id : null;
        return lid;
    }

    resolvePathEntryLayer(ownerLayer, entry) {
        if (!ownerLayer || !entry) return null;
        const lid = entry.layerId;
        if (lid === undefined || lid === null || lid === ownerLayer.id) return ownerLayer;
        const target = ((this.project && this.project.layers) || [])
            .find(l => l && l.id === lid) || null;
        if (!target) return null;
        // A pointer at a layer that exists but is no longer a reachable peer
        // (ungrouped, regrouped, or dragged onto another canvas) is dead, not
        // drawable. The server prunes it on the next round-trip; until then
        // reading it as null keeps the renderer from drawing a cable onto an
        // unrelated screen.
        return this.canPathReachLayer(ownerLayer, target) ? target : null;
    }

    resolvePathEntry(ownerLayer, entry) {
        const layer = this.resolvePathEntryLayer(ownerLayer, entry);
        if (!layer || !entry) return null;
        const panel = this.getPanelByRowCol(layer, entry.row, entry.col);
        if (!panel) return null;
        return { layer, panel };
    }

    // Hidden panels are dropped HERE rather than by each caller, matching the
    // read-time `.filter(p => p && !p.hidden)` every path consumer already ran
    // before a step could name a peer.
    getResolvedPathPanels(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return [];
        const out = [];
        path.forEach(entry => {
            const resolved = this.resolvePathEntry(ownerLayer, entry);
            if (resolved && !resolved.panel.hidden) out.push(resolved);
        });
        return out;
    }

    // layerId is written ONLY when it differs from the owner, so a path that
    // never leaves its own screen is byte-for-byte the shape it has always
    // been. (The server's prune pass normalises a self-pointer the same way,
    // so the two sides can never drift into writing different files.)
    makePathEntry(ownerLayer, panelLayer, panel) {
        if (!panel) return null;
        const entry = { row: panel.row, col: panel.col };
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            entry.layerId = panelLayer.id;
        }
        return entry;
    }

    // The address of ONE cabinet on the wall. Path ownership, path dedupe,
    // (since v0.11.0's marquee) customSelection / powerCustomSelection and
    // (since 1.5's cross-screen Pixel Map selection) pixelMapSelection are all
    // keyed on this, because across two screens `${row},${col}` names two
    // cabinets at once and every one of those jobs has to tell them apart.
    // getPanelKey stays `${row},${col}` for any caller that wants one
    // screen's own grid address.
    getScopedPanelKey(layerId, panel) {
        return `${layerId}:${panel.row},${panel.col}`;
    }

    pathCrossesMembers(ownerLayer, path) {
        if (!ownerLayer || !Array.isArray(path)) return false;
        return path.some(e => e && e.layerId !== undefined && e.layerId !== null
            && e.layerId !== ownerLayer.id);
    }

    // Which layer does this panel object belong to, as far as a path owned by
    // `ownerLayer` is concerned? Null when the panel is not reachable at all.
    // Identity first - the click handler and the arrow keys both hand us the
    // panel straight out of a layer's own array - and the (row, col) fallback
    // is what keeps a caller that rebuilt the panel behaving exactly as before.
    _resolvePathPanelLayer(ownerLayer, panel, explicitLayer) {
        if (!ownerLayer || !panel) return null;
        if (explicitLayer) {
            return this.canPathReachLayer(ownerLayer, explicitLayer) ? explicitLayer : null;
        }
        const scope = this.getPathScopeLayers(ownerLayer);
        const byIdentity = scope.find(l => l && Array.isArray(l.panels)
            && l.panels.includes(panel));
        if (byIdentity) return byIdentity;
        return this.getPanelByRowCol(ownerLayer, panel.row, panel.col) ? ownerLayer : null;
    }

    _pathLayerName(layer) {
        if (!layer) return 'another screen';
        return layer.name || `Screen ${layer.id}`;
    }

    // "port 2", or "port 2 on North Lower" when the conflict lives on a peer.
    // R3C4 alone stops meaning anything the moment two grids are in play, so
    // a toast that names only the number sends the user hunting.
    _describePathConflict(conflict, kind) {
        if (!conflict) return '';
        const base = `${kind} ${conflict.number}`;
        return conflict.foreign ? `${base} on ${this._pathLayerName(conflict.layer)}` : base;
    }

    _describePathPanel(ownerLayer, panelLayer, panel) {
        const base = `R${panel.row + 1}C${panel.col + 1}`;
        if (panelLayer && ownerLayer && panelLayer.id !== ownerLayer.id) {
            return `${base} on ${this._pathLayerName(panelLayer)}`;
        }
        return base;
    }

    /**
     * Which port / circuit (if any) already owns this cabinet, anywhere in the
     * owner's path scope. Returns {number, layer, layerId, foreign} or null.
     *
     * `foreign` is the whole reason this returns an object rather than the
     * bare number it used to: with a group in play the answer may live on a
     * different screen, and the caller has to be able to say which.
     */
    _findPathOwner(ownerLayer, panel, excludeNum, panelLayer, pathsKey) {
        if (!ownerLayer || !panel) return null;
        const source = panelLayer || ownerLayer;
        const key = this.getScopedPanelKey(source.id, panel);
        for (const scope of this.getPathScopeLayers(ownerLayer)) {
            const paths = scope && scope[pathsKey];
            if (!paths) continue;
            for (const numStr of Object.keys(paths)) {
                // Number("0") is 0, which is falsy - the old `Number(s) || s`
                // handed back the STRING "0" and then failed to match a
                // numeric exclude. Ports and circuits are 1-based so it never
                // bit anyone, but a quirk that only works because a value is
                // impossible is a trap for whoever changes that.
                const parsed = Number(numStr);
                const num = Number.isFinite(parsed) ? parsed : numStr;
                // Only the port being drawn RIGHT NOW is exempt, and only on
                // its own layer: port 1 of member A and port 1 of member B are
                // two different physical outputs (getGroupTotals sums each
                // member's own requirement), so a cabinet already claimed by
                // the peer's port 1 genuinely is taken.
                if (scope.id === ownerLayer.id && num === excludeNum) continue;
                const path = paths[numStr] || [];
                const hit = path.some(e => e && this.getScopedPanelKey(
                    this.getPathEntryLayerId(scope, e), e) === key);
                if (hit) {
                    return {
                        number: num,
                        layer: scope,
                        layerId: scope.id,
                        foreign: scope.id !== ownerLayer.id,
                    };
                }
            }
        }
        return null;
    }

    /**
     * The OTHER port (if any) that already owns this panel. Scans every layer
     * in the owner's path scope, not just the owner's own paths, so a cabinet
     * claimed by a port drawn from member A is seen as taken while drawing
     * from member B.
     */
    _findPanelOwnerPort(layer, panel, excludePortNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludePortNum, panelLayer, 'customPortPaths');
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum, panelLayer) {
        return this._findPathOwner(layer, panel, excludeCircuitNum, panelLayer, 'powerCustomPaths');
    }
}

for (const k of Object.getOwnPropertyNames(_CrossLayerPaths.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CrossLayerPaths.prototype, k));
    }
}
