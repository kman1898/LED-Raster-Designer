// app-distros: the project-level distro model for LEDRasterApp - listing,
// adding, editing and removing distros - plus the per-soca assignment onto
// a distro: which distro, which multi number, its share of a box, and its
// user-typed name with collision checks.
import { LEDRasterApp } from './app-core.js';

class _Distros {

    // ---- distros / circuit groups -------------------------------------------

    // A distro is a project-level power source with its own rating, voltage
    // and phase. Socas (multis) are assigned to one, so load rolls up
    // circuits -> soca -> distro across every screen it feeds. Load is summed
    // as WATTS (the invariant) and only converted to amps at the distro's own
    // voltage/phase - 3-phase per I = P / (V x 1.73).
    getDistros() {
        if (!this.project) return [];
        if (!this.project.distros) this.project.distros = [];
        // Every record read is migrated to a SYSTEM once (1.5,
        // app-distro-systems.js): idempotent, so a paste, an undo restore
        // or a load all meet the same record. Nothing is pushed for it -
        // an old show opens unchanged and saves the system the next time
        // its distros are written.
        for (const d of this.project.distros) this._ensureDistroSystem(d);
        return this.project.distros;
    }

    // Serialized: two rapid fire-and-forget project POSTs can complete out of
    // order, and the server merges whatever lands last - so an older payload
    // could drop a just-added distro. Chain them instead (same reason the
    // rack allocation pushes are queued).
    // The services (app-services.js) ride the same push: a distro's
    // serviceId and the service it names always land together. A show that
    // never had a service sends no key for them.
    _persistDistros() {
        const send = () => {
            const body = { distros: this.getDistros() };
            if (this.project && Array.isArray(this.project.services)) {
                body.services = this.project.services;
            }
            return fetch('/api/project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            }).catch(() => {});
        };
        this._distroPushQueue = (this._distroPushQueue || Promise.resolve()).then(send);
        return this._distroPushQueue;
    }

    // What a new distro is, short of what the caller says: the Distros &
    // multis preferences (rating, system), read here at creation and
    // nowhere else - a distro that exists keeps what it has.
    _distroPreferenceDefaults() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const rating = Number(prefs.distroRatingA);
        return {
            ratingA: Number.isFinite(rating) && rating > 0 ? rating : 400,
            system: this.preferenceDistroSystem(prefs),
        };
    }

    addDistro(opts = {}) {
        const list = this.getDistros();
        const n = list.reduce((m, d) => Math.max(m, Number(String(d.id).replace('d', '')) || 0), 0) + 1;
        const dflt = this._distroPreferenceDefaults();
        const d = {
            id: 'd' + n,
            name: opts.name || `DISTRO ${n}`,
            ratingA: Number(opts.ratingA) || dflt.ratingA,
        };
        // A new distro is a SYSTEM from the start: the one asked for, else
        // the one a caller's voltage and phase migrate to (scripts, old
        // callers; 120/208 where the pair names none), else the one
        // Preferences pick.
        const asked = opts.system && this.distroSystemById(opts.system);
        const byPair = !asked && (opts.voltage != null || opts.phase != null)
            ? (this._systemForVoltagePhase(Number(opts.voltage) || 208,
                                           Number(opts.phase) === 1 ? 1 : 3).id || '120/208')
            : null;
        const sysId = asked ? asked.id : (byPair || dflt.system);
        const sys = this.distroSystemById(sysId);
        d.system = sys.id;
        d.voltage = sys.voltage;
        d.phase = sys.phase;
        list.push(d);
        // Its id may be a removed distro's: it starts with nothing open or
        // folded (app-dock-cable-sheets.js _forgetDistroViews).
        if (typeof this._forgetDistroViews === 'function') {
            this._forgetDistroViews({ ids: [d.id] });
        }
        // Adding a distro adds a bucket the numbering runs over, and its name
        // is what the multis landing on it will be called.
        this._circuitTailCache = null;
        // Distros live on the PROJECT, and the history snapshot is the whole
        // project - so the same saveState every layer edit takes covers them,
        // and undo's project PUT restores them (restore_project replaces
        // current_project wholesale). Post-mutation, like every other action.
        this.saveState('Add Distro');
        this._persistDistros();
        return d;
    }

    updateDistro(id, patch = {}, action = 'Edit Distro') {
        const d = this.getDistros().find(x => x.id === id);
        if (!d) return null;
        // A distro on a service keeps the service's system (2026-10-20):
        // a new system is refused, saying why, until it comes off.
        if (typeof this._serviceRefusesDistroPatch === 'function'
                && this._serviceRefusesDistroPatch(d, patch)) return null;
        // Ticking "100% rated breakers" (or a new system) moves the packing
        // % of the screens on this distro. A locked screen stays unchanged
        // (owner, 2026-10-16), so a patch that would repack one is refused
        // whole, the locked screens named, and nothing changes.
        if (this._repacksLockedScreens(d, patch)) return null;
        // A change to the face - its rows, its system, a preset laid on it,
        // a row removed - never leaves a multi on a one-circuit output
        // (owner, 2026-10-18): it asks first, take the multi off and apply,
        // or cancel, and nothing changes until it is answered. Returns
        // null while it asks. A show already crowded is not asked about.
        if (!this._crowdApplying && typeof this._crowdingMadeBy === 'function') {
            const made = this._crowdingMadeBy(d, patch);
            if (made.length) {
                this._askCrowding(d, made, () => {
                    this._crowdApplying = true;
                    try { this.updateDistro(id, patch, action); }
                    finally { this._crowdApplying = false; }
                }).then(() => { this._restateNaming && this._restateNaming(); });
                return null;
            }
        }
        // Nor does a change to its rows or outputs move a locked screen's
        // multis: a row removed or resized re-deals a box or re-numbers an
        // auto multi. Written, checked, and put back whole when it would
        // (_lockedPowerTrial), the locked screens named.
        const shared = this._lockedPowerTrial();
        if (patch.name !== undefined) d.name = String(patch.name).trim() || d.name;
        // The distro's TYPE (2026-10-18): what the gear is, as the pull
        // sheet names it ("200A 24 circuits"). Blank forgets the key - a
        // distro with none prints "Distro", the way an old show does.
        if (patch.typeName !== undefined) {
            const t = String(patch.typeName == null ? '' : patch.typeName).trim();
            if (t) d.typeName = t.slice(0, 60); else delete d.typeName;
        }
        if (patch.ratingA !== undefined) d.ratingA = Number(patch.ratingA) || d.ratingA;
        // The SYSTEM (1.5): the service as a whole - its voltage and phase
        // follow it. The old voltage/phase keys still patch (scripts, old
        // callers): the pair is re-read through the migration table, and a
        // pair naming no system unambiguously leaves the distro on the old
        // arithmetic, as an old file would be.
        if (patch.system !== undefined) {
            const sys = this.distroSystemById(patch.system);
            if (sys) {
                d.system = sys.id;
                d.voltage = sys.voltage;
                d.phase = sys.phase;
            }
        } else if (patch.voltage !== undefined || patch.phase !== undefined) {
            if (patch.voltage !== undefined) d.voltage = Number(patch.voltage) || d.voltage;
            if (patch.phase !== undefined) d.phase = Number(patch.phase) === 1 ? 1 : 3;
            delete d.system;
            this._ensureDistroSystem(d);
        }
        if (patch.phasing !== undefined) d.phasing = patch.phasing || null;
        // "Whole multi on one leg" is offered on EU distros only (ruling 4):
        // a distro that leaves the EU systems drops it back to deriving.
        if (d.phasing === 'whole-ln' && this.distroRegion(d) !== 'eu') d.phasing = null;
        if (patch.input !== undefined) {
            const inp = this.distroInputs().find(i => i.id === patch.input);
            if (inp) d.input = inp.id; else delete d.input;
        }
        if (patch.breakers100 !== undefined) {
            if (patch.breakers100) d.breakers100 = true; else delete d.breakers100;
        }
        // The main's own 100% rating (2026-10-18), separate from the
        // circuits' breakers: on lifts the US continuous limit from 80% of
        // the rating to the rating (distroMainLimit). Off forgets the key,
        // the way an old show never had it.
        if (patch.main100 !== undefined) {
            if (patch.main100) d.main100 = true; else delete d.main100;
        }
        // Accept overload: a call made about this show's load, kept until
        // somebody unticks it - it never clears itself when the load moves,
        // and it never changes a figure, only how the error reads.
        if (patch.overloadAccepted !== undefined) {
            if (patch.overloadAccepted) d.overloadAccepted = true;
            else delete d.overloadAccepted;
        }
        if (patch.directPhasing !== undefined) {
            if (patch.directPhasing === 'paired') d.directPhasing = 'paired';
            else delete d.directPhasing;
        }
        // The OUTPUT ROWS (1.5): stored cleaned for the system; an empty
        // list forgets the key, so the distro is the old demand-driven
        // kind again.
        if (patch.outputRows !== undefined) {
            const sys = this.distroSystem(d);
            const rows = sys ? this._normalizeOutputRows(patch.outputRows, sys) : [];
            if (rows.length) d.outputRows = rows; else delete d.outputRows;
        } else if (patch.system !== undefined && Array.isArray(d.outputRows)) {
            // A new system re-cleans the rows it has: a connector the
            // region does not offer goes, a coupling it cannot run is
            // corrected.
            const rows = this._normalizeOutputRows(d.outputRows, this.distroSystem(d));
            if (rows.length) d.outputRows = rows; else delete d.outputRows;
        }
        // Where the box physically sits - the dimmer beach, stage left
        // world. Prints on every power label that names this distro.
        if (patch.location !== undefined) d.location = String(patch.location).trim() || null;
        // The beach it sits on (2026-09-08, picked from project.beaches -
        // see app-beaches.js): null clears; a pick retires any typed
        // location left on the record, the beach is where it is now.
        if (patch.beachId !== undefined) {
            d.beachId = patch.beachId || null;
            if (d.beachId) delete d.location;
        }
        // The connector types it offers (the ⚙ OUTPUTS checklist). Stored
        // in catalog order, unknown ids dropped; null forgets the key,
        // which reads as "offers everything" again (distroOutputs).
        if (patch.outputs !== undefined) {
            if (Array.isArray(patch.outputs)) {
                const want = patch.outputs.map(String);
                d.outputs = this.getDistroOutputTypes()
                    .map(t => t.id).filter(id => want.includes(id));
            } else {
                delete d.outputs;
            }
        }
        // The type each numbered box IS (distroBoxType). Stored as a clean
        // { number: typeId } map - non-numbers and unknown ids dropped, a
        // null entry forgetting that box's type; an emptied map forgets
        // the key, so a file never carries `boxTypes: {}`.
        if (patch.boxTypes !== undefined) {
            const src = patch.boxTypes;
            const known = new Set(this.getDistroOutputTypes().map(t => t.id));
            const clean = {};
            if (src && typeof src === 'object') {
                Object.keys(src).forEach(k => {
                    const n = parseInt(k, 10);
                    if (Number.isFinite(n) && n >= 1 && known.has(src[k])) {
                        clean[n] = src[k];
                    }
                });
            }
            if (Object.keys(clean).length) d.boxTypes = clean;
            else delete d.boxTypes;
        }
        // The NAME is a label input: every multi following this distro is
        // renamed by it, and so is every circuit hanging off those multis.
        // (Location is not - it is descriptive and names nothing.)
        this._circuitTailCache = null;
        if (shared()) return null;
        // One entry per committed field (these fire on change, not per
        // keystroke), same as the other discrete label edits - under the
        // caller's name where the field has one of its own (the box type
        // chip's 'Set Multi Type').
        this.saveState(action || 'Edit Distro');
        this._persistDistros();
        return d;
    }

    // True (and the locked screens named) when `patch` would change the
    // packing % (circuitCapacity) of any locked screen: one this distro
    // feeds, or one grouped with a screen it feeds, since a wall packs as
    // one. Worked out by laying the patch's breakers100 / system (or an
    // old caller's voltage / phase) on the distro for a moment and putting
    // it back (_repackRefused).
    _repacksLockedScreens(d, patch) {
        if (!d || !patch) return false;
        const flips = patch.breakers100 !== undefined && !!patch.breakers100 !== !!d.breakers100;
        const sys = patch.system !== undefined && typeof this.distroSystemById === 'function'
            ? this.distroSystemById(patch.system) : null;
        const moves = !!sys && sys.id !== d.system;
        const pair = patch.system === undefined
            && (patch.voltage !== undefined || patch.phase !== undefined);
        if (!flips && !moves && !pair) return false;
        return this._repackRefused(() => {
            if (flips) d.breakers100 = !!patch.breakers100;
            if (moves) {
                d.system = sys.id; d.voltage = sys.voltage; d.phase = sys.phase;
            } else if (pair) {
                // the pair re-read the way updateDistro reads it, without
                // the migration's own logging
                if (patch.voltage !== undefined) d.voltage = Number(patch.voltage) || d.voltage;
                if (patch.phase !== undefined) d.phase = Number(patch.phase) === 1 ? 1 : 3;
                const m = typeof this._systemForVoltagePhase === 'function'
                    ? this._systemForVoltagePhase(d.voltage, d.phase) : { id: null };
                const to = m.id && this.distroSystemById(m.id);
                d.system = to ? to.id : null;
                if (to) { d.voltage = to.voltage; d.phase = to.phase; }
            }
        });
    }

    // THE LOCK HOLDS THE PACKING TOO (the owner's ruling, 2026-10-22): a
    // distro or multi change that would move a LOCKED screen's packing %
    // (circuitCapacity, through the distros its multis are on and
    // _distroPackPct) is refused whole, the locked screens named in the
    // one error, and nothing changes - no store, no history entry. That
    // takes in a locked screen reached through an unlocked member of its
    // group, since a wall packs as one.
    //
    // `apply` makes the change on the live records for a moment, with the
    // same store moves the real gesture runs; everything it can reach is
    // put back exactly before this returns (_holdPowerRecords). `near`
    // (a layer or a list) narrows the check to the locked screens that
    // pack with those screens - themselves and their groups - for a
    // change that touches only their multis; left out, every locked
    // screen is checked (a distro's own change reaches any of them).
    // True when the change must not happen.
    //
    // The error says why (_showLockedError's 'repack'): the user acted on
    // another screen, a distro or a group, never on the locked screen,
    // which every caller has refused with the plain error already.
    _repackRefused(apply, near) {
        if (typeof this.circuitCapacity !== 'function' || typeof apply !== 'function') return false;
        const locked = this._repackLockedScreens(near);
        if (!locked.length) return false;
        const pctOf = () => new Map(locked.map(l => [l, this.circuitCapacity(l).pct]));
        this._circuitTailCache = null;
        const before = pctOf();
        const release = this._holdPowerRecords();
        let after;
        try {
            apply();
            this._circuitTailCache = null;
            after = pctOf();
        } finally {
            release();
        }
        const repacked = locked.filter(l => before.get(l) !== after.get(l));
        return repacked.length ? this._lockedRefused(repacked, 'repack') : false;
    }

    // The locked screens a change near `near` (a layer or a list) can
    // repack: themselves and every member of their groups. Left out, every
    // locked screen.
    _repackLockedScreens(near) {
        const layers = (this.project && this.project.layers) || [];
        let locked = layers.filter(l => l && this._layerLocked(l) && (l.type || 'screen') === 'screen');
        if (locked.length && near) {
            const reach = new Set();
            (Array.isArray(near) ? near : [near]).filter(Boolean).forEach(l => {
                reach.add(l);
                if (l.group_id && typeof this.groupMembersOf === 'function') {
                    this.groupMembersOf(l).forEach(m => reach.add(m));
                }
            });
            locked = locked.filter(l => reach.has(l));
        }
        return locked;
    }

    // The edit funnel's repack check (applyToSelectedLayers): called before
    // the edit, with the selection; returns check(), which after the edit
    // answers the locked screens it repacked - [] when none, else every
    // screen the edit could reach (the selection and their groups) is put
    // back field by field (_holdLayerFields). Null when no locked screen
    // packs with the selection or shares a distro with it.
    //
    // The shared-box lock too (_lockedPowerTrial): an edit that changes an
    // unlocked screen's circuits (its panel watts, say) re-deals a multi
    // box it shares with a locked screen. A locked screen on a distro the
    // reached screens are on that shows other circuits, tails or numbers
    // after the edit is answered the same way, the list marked
    // `why: 'shared'` for the error.
    _repackEditTrial(layers) {
        const screens = (layers || []).filter(l => l && (l.type || 'screen') === 'screen');
        if (!screens.length) return null;
        const locked = typeof this.circuitCapacity === 'function'
            ? this._repackLockedScreens(screens) : [];
        const reach = new Set(screens);
        screens.forEach(l => {
            if (l.group_id && typeof this.groupMembersOf === 'function') {
                this.groupMembersOf(l).forEach(m => reach.add(m));
            }
        });
        const shared = typeof this._lockedOnDistrosOf === 'function'
            ? this._lockedOnDistrosOf([...reach]) : [];
        if (!locked.length && !shared.length) return null;
        const pctOf = () => new Map(locked.map(l => [l, this.circuitCapacity(l).pct]));
        const factsOf = () => new Map(shared.map(l => [l, this._lockedPowerFacts(l)]));
        this._circuitTailCache = null;
        const before = pctOf();
        const factsBefore = factsOf();
        const release = this._holdLayerFields([...reach]);
        return () => {
            this._circuitTailCache = null;
            const after = pctOf();
            const repacked = locked.filter(l => before.get(l) !== after.get(l));
            const moved = repacked.length ? []
                : shared.filter(l => this._lockedPowerFacts(l) !== factsBefore.get(l));
            if (!repacked.length && !moved.length) return [];
            release();
            this._circuitTailCache = null;
            if (repacked.length) return repacked;
            moved.why = 'shared';
            return moved;
        };
    }

    // _repackRefused for a gesture that writes its change in place before
    // it commits (a circuit share, an Nfer): called BEFORE the first write,
    // it returns refused(), to call after the writes and before the commit.
    // refused() is true when the change moved a locked screen's packing %:
    // then every record the change can reach is already put back
    // (_holdPowerRecords), the screens are named, and the caller returns
    // without its commit or its history entry. False keeps the change.
    // It runs the shared-box lock with it (_lockedPowerTrial): a change
    // that would move a locked screen's circuits, tails or numbers on a
    // multi box it shares is refused the same way, as 'shared'.
    // `say(screens, why)`, when given, says the refusal in place of the
    // plain error, `why` 'repack' or 'shared' (a wall that shrank names
    // what the lock kept).
    _repackTrial(near, say = null) {
        const shared = typeof this._lockedPowerTrial === 'function'
            ? this._lockedPowerTrial(typeof say === 'function'
                ? (screens => say(screens, 'shared')) : null)
            : () => false;
        if (typeof this.circuitCapacity !== 'function') return shared;
        const locked = this._repackLockedScreens(near);
        if (!locked.length) return shared;
        const pctOf = () => new Map(locked.map(l => [l, this.circuitCapacity(l).pct]));
        this._circuitTailCache = null;
        const before = pctOf();
        const release = this._holdPowerRecords();
        return () => {
            this._circuitTailCache = null;
            const after = pctOf();
            const repacked = locked.filter(l => before.get(l) !== after.get(l));
            if (!repacked.length) return shared();
            release();
            if (typeof say === 'function') say(repacked, 'repack');
            else this._showLockedError(repacked, 'repack');
            return true;
        };
    }

    // A hold on everything a trial distro or multi change can write: the
    // distro list and each distro record (held multi numbers, system,
    // breakers), every screen's power fields (assignments, numbers, cuts,
    // tails, names, lengths, cables, label overrides, splitters, drawn
    // paths), the held-number baseline and the pull sheet's edits. The
    // returned release() puts back whatever
    // changed, in place, and drops the naming cache that read the trial.
    _holdPowerRecords() {
        const project = this.project || {};
        const list = Array.isArray(project.distros) ? project.distros : null;
        const distros = list ? list.slice() : [];
        const distroJson = distros.map(d => JSON.stringify(d));
        const layers = (project.layers || []).slice();
        const powerOf = (l) => {
            const out = {};
            Object.keys(l || {}).forEach(k => {
                if (k.startsWith('power')) out[k] = JSON.stringify(l[k]);
            });
            return out;
        };
        const fields = layers.map(powerOf);
        const baseline = this._multiBaseline;
        const baselineCopy = baseline instanceof Map ? new Map(baseline) : null;
        const dirty = this._multiHoldsDirty;
        // the pull sheet's edits too: a gesture that moves circuits drops
        // the edits on rows it takes away (_dropPullEditsGoneWith)
        const hadPull = Object.prototype.hasOwnProperty.call(project, 'pullSheetEdits');
        const pullJson = hadPull ? JSON.stringify(project.pullSheetEdits) : null;
        return () => {
            if (hadPull && JSON.stringify(project.pullSheetEdits) !== pullJson) {
                project.pullSheetEdits = pullJson === undefined ? undefined : JSON.parse(pullJson);
            } else if (!hadPull && Object.prototype.hasOwnProperty.call(project, 'pullSheetEdits')) {
                delete project.pullSheetEdits;
            }
            if (list) {
                if (list.length !== distros.length || list.some((d, i) => d !== distros[i])) {
                    list.length = 0;
                    distros.forEach(d => list.push(d));
                }
                distros.forEach((d, i) => {
                    if (!d || typeof d !== 'object' || JSON.stringify(d) === distroJson[i]) return;
                    Object.keys(d).forEach(k => { delete d[k]; });
                    Object.assign(d, JSON.parse(distroJson[i]));
                });
            }
            layers.forEach((l, i) => {
                if (!l) return;
                const was = fields[i];
                Object.keys(l).forEach(k => {
                    if (k.startsWith('power') && !Object.prototype.hasOwnProperty.call(was, k)) delete l[k];
                });
                Object.keys(was).forEach(k => {
                    if (JSON.stringify(l[k]) === was[k]) return;
                    l[k] = was[k] === undefined ? undefined : JSON.parse(was[k]);
                });
            });
            this._multiBaseline = baseline;
            if (baselineCopy) {
                baseline.clear();
                baselineCopy.forEach((v, k) => baseline.set(k, v));
            }
            this._multiHoldsDirty = dirty;
            this._circuitTailCache = null;
        };
    }

    // The multi assignment `pairs` ([socaIndex, distroId | null], ...) would
    // make on `layer`, refused when it repacks a locked screen
    // (_repackRefused): the setter's check, and a composite drop's before
    // anything of the drop is written.
    _assignRepacksLocked(layer, pairs) {
        if (!layer || !pairs || !pairs.length) return false;
        return this._repackRefused(() => {
            const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
            pairs.forEach(([idx, id]) => {
                if (id) map[idx] = id; else delete map[idx];
            });
        }, [layer]);
    }

    removeDistro(id) {
        const list = this.getDistros();
        const i = list.findIndex(x => x.id === id);
        if (i === -1) return false;
        // Removing a distro unfeeds every multi on it, so a locked screen
        // fed from it keeps the distro in place (the owner's ruling,
        // 2026-10-16) - whole or not at all, and the error names it.
        const fedLocked = (this.project.layers || []).filter(l => l && this._layerLocked(l)
            && Object.values(l.powerSocaDistro || {}).includes(id));
        if (this._lockedRefused(fedLocked)) return false;
        // ...and so does a locked screen the removal would REPACK (owner,
        // 2026-10-22): one grouped with a screen it feeds, whose packing %
        // the group shares (_repackRefused). Refused whole, nothing moved.
        if (this._repackRefused(() => {
            list.splice(i, 1);
            for (const layer of this.project.layers || []) {
                const map = layer && layer.powerSocaDistro;
                if (!map) continue;
                for (const k of Object.keys(map)) if (map[k] === id) delete map[k];
            }
        })) return false;
        // ...and so does a locked screen whose multis the removal would
        // deal again or re-number (_lockedPowerTrial): written, checked,
        // put back whole.
        const shared = this._lockedPowerTrial();
        // The multis it fed lose their typed lengths with it (owner,
        // 2026-10-17): each one's home run - a direct output's included -
        // and its circuits' cables. Read off the naming index before any
        // assignment moves, which is what says which circuits a multi has.
        const pullBefore = this._pullLiveRowKeys();
        const forget = [];
        for (const layer of this.project.layers || []) {
            const map = layer.powerSocaDistro;
            if (!map) continue;
            for (const k of Object.keys(map)) {
                if (map[k] !== id) continue;
                forget.push({ layer, idx: Number(k),
                              circuits: this._socaClearTargets(layer, k).circuits });
            }
        }
        list.splice(i, 1);
        forget.forEach(f => this._forgetFeedLengths(f.layer, f.idx, f.circuits));
        // A distro fed thru the one removed is fed from its service again:
        // its feeder forgets the `from`, so a later distro that reuses the
        // id is never read as the one it is fed thru (owner, 2026-10-21).
        // A feeder left empty is forgotten, as one never set.
        for (const other of list) {
            const f = other && other.feeder;
            if (!f || typeof f !== 'object' || f.from !== id) continue;
            delete f.from;
            if (!Object.keys(f).length) delete other.feeder;
        }
        // orphaned soca assignments fall back to unassigned
        const touched = [];
        for (const layer of this.project.layers || []) {
            const map = layer.powerSocaDistro;
            if (!map) continue;
            let changed = false;
            for (const k of Object.keys(map)) if (map[k] === id) { delete map[k]; changed = true; }
            if (changed) touched.push(layer);
        }
        if (shared()) return false;
        if (touched.length) this.updateLayers(touched);
        // The orphaned multis fall back into the unassigned bucket, which
        // renumbers it and everything after it.
        this._circuitTailCache = null;
        // A pull-sheet edit on a row the removal took away goes with it.
        this._dropPullEditsGoneWith(pullBefore);
        // ONE entry for the removal AND the orphaning it caused, taken after
        // both so a single Ctrl+Z brings the distro back with its multis
        // still assigned to it - not a distro with its feeds cut loose.
        this.saveState('Remove Distro');
        this._persistDistros();
        return true;
    }

    // `socaIndex` is the multi's stable index within its screen, never its
    // displayed number - the number is what this call CHANGES, since it comes
    // out of the distro's own sequence.
    // `record` (default true) is for composite gestures only: a dock drop
    // that drives this setter alongside others passes false and issues ONE
    // updateLayers(..., true, action) itself over every returned layer, so
    // the whole drop is one undo entry. Returns the touched layers either way.
    setSocaDistro(layer, socaIndex, distroId, record = true) {
        if (!layer) return [];
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return [];
        // Nor does a locked screen this move would REPACK - one grouped
        // with this screen, whose packing % the group shares (owner,
        // 2026-10-22): refused whole, nothing written.
        if (this._assignRepacksLocked(layer, [[socaIndex, distroId || null]])) return [];
        // A multi carrying its pin onto another distro never lands on a
        // one-circuit output with more than it carries (2026-10-18).
        const carried = (layer.powerSocaNumber || {})[socaIndex];
        const crowd = distroId && typeof this._crowdRefusal === 'function'
            ? this._crowdRefusal(layer, socaIndex, distroId, carried) : null;
        if (crowd) { this._sayCrowdRefusal(crowd); return []; }
        // A locked screen on the box this leaves or lands on keeps its
        // circuits where they are: the move is written, checked, and put
        // back whole when it would deal them again (_lockedPowerTrial).
        const shared = this._lockedPowerTrial();
        const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
        // A multi that carries its pin onto another distro can land on an
        // occupied box there - the same join as pinning, spelled as an
        // assignment - so the incumbents on the target box hold their
        // rendered tails the same way.
        const pin = parseInt((layer.powerSocaNumber || {})[socaIndex], 10);
        const stamped = (distroId && Number.isFinite(pin) && pin >= 1)
            ? this._materializeSocaBox(distroId, pin, layer, socaIndex)
            : [];
        // A multi that leaves its distro - off it, or onto another - leaves
        // the old feed's home run and circuit cables behind (owner,
        // 2026-10-17); one that had no distro had no feed, so whatever an
        // older file left under its index is not the new feed's either.
        // Staying on the same distro keeps them.
        if ((map[socaIndex] || null) !== (distroId || null)) {
            this._forgetFeedLengths(layer, socaIndex,
                this._socaClearTargets(layer, socaIndex).circuits);
        }
        if (distroId) map[socaIndex] = distroId; else delete map[socaIndex];
        // Assignment renumbers both buckets it touches, so every label on the
        // show can move. Stale labels for a frame is a bug this has already
        // been bitten by once.
        this._circuitTailCache = null;
        if (shared()) return [];
        const touched = [...new Set([layer, ...stamped])];
        if (record) {
            this.updateLayers(touched, true, 'Assign Multi Distro');
        }
        return touched;
    }

    // Pin a multi to a NUMBER under its distro - the "which output of the
    // box am I plugged into" choice. Auto (no entry) numbers exactly as
    // always: per distro, layer order, dealing around every pinned slot.
    //
    // The pin is also how one PHYSICAL soca serves two screens: two multis
    // pinned to the same (distro, number) ARE one box, and the second
    // screen's circuits land on the box's next free tails - the shape the
    // user used to build by hand-typing powerLabelOverrides (C2-3-4..6)
    // onto a twin multi that the rollup then counted twice. There is no
    // separate link to manage: picking the number joins, re-picking (or
    // Auto, or another distro) separates.
    // `record` mirrors setSocaDistro's: false lets a composite dock gesture
    // fold this write into its own single history entry.
    setSocaNumber(layer, socaIndex, number, record = true) {
        if (!layer) return [];
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return [];
        // A pin onto a DIRECT output never puts more circuits on it than
        // it carries (2026-10-18): refused, saying why.
        const crowd = typeof this._crowdRefusal === 'function'
            ? this._crowdRefusal(layer, socaIndex, (layer.powerSocaDistro || {})[socaIndex], number)
            : null;
        if (crowd) { this._sayCrowdRefusal(crowd); return []; }
        // A locked screen on the box this joins or leaves keeps its
        // circuits where they are (_lockedPowerTrial): a pin that would
        // deal them again is put back whole, the screen named.
        const shared = this._lockedPowerTrial();
        // Always leave an object behind, never delete the property: an
        // absent key is missing from the update payload and the server
        // keeps whatever it had, so "back to Auto" would silently not clear.
        const store = layer.powerSocaNumber || (layer.powerSocaNumber = {});
        const n = parseInt(number, 10);
        // Landing on an occupied box is the JOIN, and the incumbents keep
        // the tails they were rendering: stamp them before the pin so the
        // joiner deals into what is genuinely free. Un-pinning (Auto) is
        // the leave - nobody's tails move, so there is nothing to stamp.
        const stamped = (Number.isFinite(n) && n >= 1)
            ? this._materializeSocaBox(
                (layer.powerSocaDistro || {})[socaIndex], n, layer, socaIndex)
            : [];
        if (Number.isFinite(n) && n >= 1) store[socaIndex] = n;
        else delete store[socaIndex];
        // A pin renumbers the whole distro bucket (autos deal around it) and
        // can merge or split a shared box, so every label can move.
        this._circuitTailCache = null;
        if (shared()) return [];
        const touched = [...new Set([layer, ...stamped])];
        if (record) {
            this.updateLayers(touched, true, 'Set Multi Number');
        }
        return touched;
    }

    // The shared-box record for one multi, or null when it shares with
    // nobody. Non-null only for a PINNED multi whose (distro, number) is
    // claimed by at least one other multi - see _resolveSharedSocas for the
    // fields. This is what the soca tiles, the rollup and the balancer read,
    // so "is this one box or two" has exactly one answer.
    getSocaShare(layer, socaIndex) {
        if (!layer) return null;
        const idx = Number(socaIndex);
        if (!((layer.powerSocaDistro || {})[idx])) return null;
        const n = parseInt((layer.powerSocaNumber || {})[idx], 10);
        if (!Number.isFinite(n) || n < 1) return null;
        const rec = this._powerNaming(layer).socas.get(idx);
        return (rec && rec.share) || null;
    }

    // What was SHOWING becomes HELD - the pin philosophy applied to tails.
    // Called by every gesture that lands a multi on box (distroId, number)
    // - a pin, a re-assignment carrying a pin, a split or un-split of a
    // member - BEFORE the gesture mutates anything, while "current tails"
    // still means what the wall shows today. Each multi already on the box
    // (the incumbents) gets its rendered tails stamped into its own
    // powerSocaPhasePos, so the joiner deals into the tails that are
    // actually free and never renumbers a wall someone may have already
    // cabled. A member that already holds a stored set is already law and
    // is left alone; a rendering the fan cannot hold (an overflowed box)
    // is not an arrangement worth freezing. Returns the layers stamped so
    // the caller's updateLayers carries them - the incumbents can live on
    // other screens than the joiner.
    //
    // A LOCKED incumbent is never written, not even to hold the tails it
    // shows (the owner's rule: a locked screen stays unchanged until
    // unlocked). Every gesture that stamps runs the shared-box lock
    // (_lockedPowerTrial): when the gesture would deal the locked screen's
    // tails again, it is put back whole and the locked screen named; when
    // they stay as they are, it goes through without touching that screen.
    _materializeSocaBox(distroId, number, exceptLayer, exceptSoca) {
        const touched = [];
        const n = parseInt(number, 10);
        if (!distroId || !Number.isFinite(n) || n < 1) return touched;
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            if (this._layerLocked(l)) continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                // Only a PIN holds a slot against the joiner: an auto at
                // this number re-deals around the new pin and keeps its
                // own box, so it has nothing to defend.
                if (!rec.pinned) continue;
                if (rec.distroId !== distroId || rec.number !== n) continue;
                if (l === exceptLayer && rec.index === Number(exceptSoca)) continue;
                const store = l.powerSocaPhasePos || (l.powerSocaPhasePos = {});
                if (Array.isArray(store[rec.index])) continue;
                const L = rec.circuits.length;
                const pos = rec.positions;
                const cap = this.socaBoxSize(l);
                if (!Array.isArray(pos) || pos.length !== L) continue;
                if (!pos.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
                    || new Set(pos).size !== L) continue;
                store[rec.index] = pos.slice();
                touched.push(l);
            }
        }
        return touched;
    }

    // Every multi number in use on one distro, show-wide:
    // number -> [{layerId, layerName, soca, legs, pinned}]. The number
    // select prints this so a tech picking a slot can see who is already on
    // it - picking an occupied number is the combine gesture, and it should
    // read that way before the click, not after.
    _distroMultiNumbers(distroId) {
        const out = new Map();
        if (!distroId) return out;
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                if (rec.distroId !== distroId) continue;
                const arr = out.get(rec.number) || [];
                arr.push({ layerId: l.id, layerName: l.name, soca: rec.index,
                           legs: rec.circuits.length, pinned: !!rec.pinned });
                out.set(rec.number, arr);
            }
        }
        return out;
    }

    // Other multis on this multi's distro that DISPLAY the same name while
    // sitting on a DIFFERENT number. Same name on the same number IS the
    // shared-box gesture; the same name across two numbers is two labels
    // claiming one box on paper while the patch says two boxes - never
    // intentional now that sharing is a pin. Flagged on the tiles, never
    // blocked: the fix is either pinning both to one number (one box) or
    // renaming one (two boxes), and that is the user's call.
    _socaNameCollisions(layer, socaIndex) {
        if (!layer) return [];
        const rec = this._powerNaming(layer).socas.get(Number(socaIndex));
        if (!rec || !rec.distroId || !rec.name) return [];
        const out = [];
        for (const l of ((this.project && this.project.layers) || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const other of this._powerNaming(l).socas.values()) {
                if (l.id === layer.id && other.index === rec.index) continue;
                if (other.distroId !== rec.distroId) continue;
                if (other.number === rec.number) continue;
                if (String(other.name) !== String(rec.name)) continue;
                out.push({ layerName: l.name, number: other.number });
            }
        }
        return out;
    }

    // TYPED multi names worn by boxes on two or more distros (owner,
    // 2026-10-22: two boxes both typed "MAIN" - "Warn instead"). Paper
    // tells them apart as MAIN-1 and MAIN-2 (distroBoxLabels) and the
    // circuits take no suffix, so the tray warns and asks for a rename.
    // One distro wearing a name on two numbers is _socaNameCollisions'
    // warning, not this one. Screens left hidden are not counted, as on
    // paper. [{ name, boxes: [{ distroId, number, label }] }], each box
    // once however many screens share it, in tray order.
    _typedMultiNameDuplicates() {
        // Read once per naming burst: every box tile in the tray asks.
        if (this._circuitTailCache && this._dupNamesFor === this._circuitTailCache) {
            return this._dupNames;
        }
        const distros = typeof this.getDistros === 'function' ? this.getDistros() : [];
        const order = new Map(distros.map((d, i) => [d.id, i]));
        const byName = new Map();       // name -> Map(distroId|number -> box)
        for (const l of ((this.project && this.project.layers) || [])) {
            if (!l || (l.type || 'screen') !== 'screen') continue;
            if (typeof this._screenHidden === 'function' ? this._screenHidden(l) : l.visible === false) continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                if (!rec || !rec.distroId || !order.has(rec.distroId)) continue;
                const name = String(rec.name || '').trim();
                if (!name) continue;
                const boxes = byName.get(name) || new Map();
                const key = `${rec.distroId}|${rec.number}`;
                const box = boxes.get(key)
                    || { distroId: rec.distroId, number: Number(rec.number), hand: false };
                box.hand = box.hand || !!rec.hand;
                boxes.set(key, box);
                byName.set(name, boxes);
            }
        }
        const out = [];
        for (const [name, boxes] of byName) {
            const list = [...boxes.values()];
            if (list.length < 2 || !list.some(b => b.hand)) continue;
            if (new Set(list.map(b => b.distroId)).size < 2) continue;
            list.sort((a, b) => (order.get(a.distroId) - order.get(b.distroId)) || (a.number - b.number));
            // each box named the way it prints ("SR1", "SR-1-2"), never
            // "SR 1" (_deriveMultiName, as distroBoxLabels names it)
            out.push({ name, boxes: list.map(b => {
                const base = this.distroLabel(distros[order.get(b.distroId)]);
                return { distroId: b.distroId, number: b.number,
                         label: typeof this._deriveMultiName === 'function'
                             ? this._deriveMultiName(base, b.number, null) : `${base}${b.number}` };
            }) });
        }
        this._dupNamesFor = this._circuitTailCache;
        this._dupNames = out;
        return out;
    }

    // The warning one duplicate reads, in the strip and on the box's name:
    // "MAIN is used on 2 boxes, SR1 and SL3. Rename one so each box reads
    // its own name." Used, not typed: one of the boxes can wear the name
    // as its own automatic one (a box typed SR1 beside distro SR's box 1).
    _typedMultiNameText(dup) {
        const labels = dup.boxes.map(b => b.label);
        const list = labels.length > 1
            ? `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}` : labels[0];
        return `${dup.name} is used on ${labels.length} boxes, ${list}. `
            + 'Rename one so each box reads its own name.';
    }

    // "4-6" for [4,5,6], "1-3, 5" for [1,2,3,5] - the way a tail set is
    // said out loud on a tile face.
    _fmtTails(tails) {
        const t = (tails || []).slice().sort((a, b) => a - b);
        if (!t.length) return '';
        const runs = [[t[0], t[0]]];
        for (let i = 1; i < t.length; i++) {
            if (t[i] === runs[runs.length - 1][1] + 1) runs[runs.length - 1][1] = t[i];
            else runs.push([t[i], t[i]]);
        }
        return runs.map(([a, b]) => a === b ? `${a}` : `${a}-${b}`).join(', ');
    }

    // A multi named by hand. Per-MULTI, so unlike the bracket toggle and the
    // breakout type it never sweeps the selection (_socaPanelTargets): a name
    // belongs to one multi on one screen. Blank hands it back to the distro.
    // `record` mirrors setSocaDistro's: false lets a composite gesture (the
    // dock's one-field-per-box header writing through to every member of a
    // shared box) fold this write into its own single history entry.
    setSocaName(layer, socaIndex, name, record = true) {
        if (!layer) return;
        // A locked screen stays unchanged (owner, 2026-10-16) - the setter
        // refuses and names it, whichever control called it.
        if (this._lockedRefused(layer)) return;
        // Always leave an object behind, never delete the property: an absent
        // key is simply missing from the update payload and the server keeps
        // whatever it had, so "clear this" would silently not clear.
        const store = layer.powerSocaNames || (layer.powerSocaNames = {});
        const v = String(name || '').trim();
        if (v) store[socaIndex] = v; else delete store[socaIndex];
        this._circuitTailCache = null;
        if (record) {
            this.updateLayers([layer], true, 'Rename Multi');
        }
    }
}

for (const k of Object.getOwnPropertyNames(_Distros.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Distros.prototype, k));
    }
}
