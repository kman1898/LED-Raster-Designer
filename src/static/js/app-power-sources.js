// app-power-sources: ONE screen fed from different kinds of power source
// (owner rulings, 2026-11-11).
//
// "we need a way to combine different cable types and voltages if need
// be": a wall can run a Multi 208 and an L6-20 208, or a Multi 110 and an
// L6-20 208, or (his show) 110V Socapex beside L21-30 Edison boxes. How a
// circuit is fed follows the drag ("however they are dragged to via the
// distro"): dropping an output of another type or voltage onto a screen is
// allowed, where it used to be refused, and "the circuits after will need
// redrawing in the same [way] that the screen is set to": the circuits it
// takes over and every one after it are laid again with the screen's own
// draw setting (its pattern and Organized / Max Capacity), packed to THAT
// source's circuit (its voltage and breaker). The circuits before it keep
// the screen's own setting.
//
// THE MODEL - the smallest that does it. `layer.powerSources` is a list
// of where another kind of source takes over, by circuit ORDINAL (the
// circuit's place in the screen's circuit order, the same count the multi
// splits use):
//     [{ from: 25, type: 'l2130e', distroId, breakout: 'l2130-edison',
//        volts: 110, amps: 15 },
//      { from: 37, own: true }]
// Circuits 1..24 ride the screen's own setting (its breakout, voltage
// and Amperage), 25..36 the L21-30 Edison box, 37 on the screen's own
// again. A face output (1.5 distro rows) also names its row (`rowId`), so
// a direct output's breaker follows the row. No list - every show before
// this - is a screen of one kind, exactly as it always read: nothing here
// runs, nothing is written on open.
//
// A source is a FEED, so a copy of the screen never carries it (copies
// never carry feeds), and when the last multi on it is unplugged it goes
// (pruneDormantPowerSources, at the save that unplugs it) and the
// circuits fall back to the screen's own.
import { LEDRasterApp } from './app-core.js';
import { isZFlowPattern, isVerticalFlowPattern, sendClientLog } from './helpers.js';

class _PowerSources {

    // The stored list, cleaned: a numeric `from` of 1 or more, the last
    // record for one `from` winning, in circuit order.
    _powerSourceRecords(layer) {
        const raw = layer && layer.powerSources;
        if (!Array.isArray(raw) || !raw.length) return [];
        const byFrom = new Map();
        for (const r of raw) {
            if (!r || typeof r !== 'object') continue;
            const from = parseInt(r.from, 10);
            if (!Number.isFinite(from) || from < 1) continue;
            byFrom.set(from, r);
        }
        return [...byFrom.entries()].sort((a, b) => a[0] - b[0])
            .map(([from, r]) => Object.assign({}, r, { from }));
    }

    // What a screen's own circuits are: its breakout, voltage and breaker.
    //   { own, breakout, volts, breakerA, boxSize, feedLegA, typeId, conn,
    //     tailA, plugged }
    // The breaker is what the circuits are really on (owner, 2026-11-12:
    // "it should be what a real one would be plugged into"): the breaker
    // of the distro outputs the screen's own multis are plugged into, the
    // strictest where they differ (_pluggedBreaker), and the screen's
    // Amperage only while none is plugged in. `tailA` is the Amperage box
    // as typed, which picks an Edison breakout's outlet (screenEdisonType).
    ownPowerSpec(layer) {
        const spec = this._ownSpecBase(layer);
        if (!(Number(spec.breakout.circuitA) > 0)) {
            const plugged = this._pluggedBreaker(layer, null);
            if (plugged.amps > 0) {
                spec.breakerA = plugged.amps;
                spec.plugged = plugged;
            }
        }
        return spec;
    }

    // The screen's own spec as its sidebar says it, no distro read.
    _ownSpecBase(layer) {
        const bt = this.getPowerBreakout(layer);
        const fixed = Number(bt.circuitA) || 0;
        const size = Number(bt.boxSize);
        const typed = parseFloat(layer && layer.powerAmperage) || 0;
        return {
            own: true, breakout: bt, volts: this.voltageNumber(layer && layer.powerVoltage),
            breakerA: fixed > 0 ? fixed : typed,
            boxSize: Number.isFinite(size) && size >= 1 ? size : 6,
            feedLegA: Number(bt.feedLegA) || 0, typeId: null, conn: null,
            tailA: typed, plugged: null,
        };
    }

    // ---- the breaker a run of circuits is on (owner, 2026-11-12) ---------
    //
    // "the side panel amperage for the screen is without the distro
    // attached, but it should be what a real one would be plugged into":
    // a run of one source (the screen's own circuits, or one source's) is
    // packed and checked at the breaker of the distro outputs its multis
    // are plugged into - a Socapex row's breaker, an Edison output's
    // breaker held to its 5-15 or 5-20 receptacle, the L21-30 Edison box's
    // 15 A a circuit - the strictest where they differ, so every circuit
    // of the run fits on every one of them. A run with nothing plugged in
    // keeps its own figure: the screen's Amperage, or the breaker a source
    // was dropped with (so a source unplugged in the middle keeps its
    // circuits as they were: the hole of applySourceDrop's ruling).
    // Read off the stores, never the plan, which is built from this.

    // Each run's multis by their stable index, counted without packing:
    // the box grid of each run from its own first circuit (the way
    // _socaSegments cuts it), plus the stored splits.
    //   [{ start, end, rec, first, last }]   rec null: the screen's own
    // The last run is open-ended (end and last Infinity).
    _sourceSpans(layer) {
        const recs = this._powerSourceRecords(layer);
        const base = this._ownSpecBase(layer);
        const splits = new Set(this._socaSplitPoints(layer, null));
        const bounds = [{ from: 1, rec: null }].concat(recs.map(r => ({ from: r.from, rec: r })));
        const spans = [];
        let idx = 0;
        for (let b = 0; b < bounds.length; b++) {
            const start = bounds[b].from;
            const next = bounds[b + 1];
            if (next && next.from <= start) continue;
            const rec = bounds[b].rec;
            const spec = rec && !rec.own ? this._specFromRecordBase(layer, rec, base) : base;
            const size = spec.boxSize;
            const first = idx + 1;
            if (!next) {
                spans.push({ start, end: Infinity, rec, first, last: Infinity });
                break;
            }
            const end = next.from - 1;
            for (let i = start; i <= end; i++) {
                if (i === end || (i - start + 1) % size === 0 || splits.has(i)) idx++;
            }
            spans.push({ start, end, rec, first, last: idx });
        }
        return spans;
    }

    // The breaker the multis of one run are plugged into: `rec` null for
    // the screen's own circuits (every member of a grouped wall read, the
    // wall packs as one), else that source's. { amps, hits } - amps null
    // with nothing plugged; hits [{ screen, index, d, box, amps }]. Only a
    // multi pinned to an output is read (the face's number); an old
    // distro's outputs have no breaker, and an Edison output from before
    // the 5-15 / 5-20 choice has no say until somebody picks (its show
    // keeps its circuits, distroChecks offers the repack).
    _pluggedBreaker(layer, rec) {
        const out = { amps: null, hits: [] };
        if (!layer || typeof this.getDistros !== 'function' || typeof this.faceBox !== 'function') return out;
        const distros = this.getDistros() || [];
        if (!distros.length) return out;
        let screens = [layer];
        if (!rec && layer.group_id && typeof this.groupMembersOf === 'function') {
            const g = this.groupMembersOf(layer);
            if (g.length) screens = g;
        }
        for (const s of screens) {
            const map = (s && s.powerSocaDistro) || {};
            const keys = Object.keys(map).filter(k => map[k]);
            if (!keys.length) continue;
            const spans = this._sourceSpans(s).filter(sp => (rec
                ? sp.rec && !sp.rec.own && sp.rec.from === rec.from
                : !sp.rec || sp.rec.own));
            if (!spans.length) continue;
            const chosen = s.powerSocaNumber || {};
            for (const key of keys) {
                const index = parseInt(key, 10);
                if (!Number.isFinite(index) || !spans.some(sp => sp.first <= index && index <= sp.last)) continue;
                const d = distros.find(x => x && x.id === map[key]);
                if (!d) continue;
                let n = parseInt(chosen[key], 10);
                if (!(Number.isFinite(n) && n >= 1) && d.multiNumbers && typeof this._multiHoldKey === 'function') {
                    n = parseInt(d.multiNumbers[this._multiHoldKey(s.id, index)], 10);
                }
                if (!(Number.isFinite(n) && n >= 1)) continue;
                const box = this.faceBox(d, n);
                if (!box || !box.conn) continue;
                let amps = Number(box.conn.circuitA) || Number(box.breakerA) || 0;
                if (box.conn.id === 'edison' && typeof this.edisonRowType === 'function') {
                    const et = this.edisonRowType(box.row);
                    if (!et.picked) continue;
                    amps = Math.min(amps, et.ratingA);
                }
                if (!(amps > 0)) continue;
                out.hits.push({ screen: s, index, d, box, amps });
                if (out.amps === null || amps < out.amps) out.amps = amps;
            }
        }
        return out;
    }

    // One stored record as the circuits it feeds read it: as dropped
    // (_specFromRecordBase), on the breaker of the outputs its multis are
    // plugged into now (_pluggedBreaker).
    _specFromRecord(layer, rec, own) {
        const spec = this._specFromRecordBase(layer, rec, own);
        if (!rec || rec.own || spec === own || Number(spec.breakout && spec.breakout.circuitA) > 0) return spec;
        const plugged = this._pluggedBreaker(layer, rec);
        if (plugged.amps > 0) return Object.assign({}, spec, { breakerA: plugged.amps, plugged });
        return spec;
    }

    // One stored record as the circuits it feeds read it. A box that fixes
    // its circuits' breaker (the L21-30 Edison, 15 A) says so whatever was
    // stored; a face output's breaker is its row's, read live (a multi row
    // or a direct one: the output the source was dropped from), so an
    // Edison output's 5-15 / 5-20 pick carries to the circuit on it.
    _specFromRecordBase(layer, rec, own) {
        if (!rec || rec.own) return own;
        const bt = this.getPowerBreakoutTypes().find(b => b.id === rec.breakout) || own.breakout;
        let breakerA = Number(rec.amps) > 0 ? Number(rec.amps) : own.breakerA;
        let conn = null;
        if (rec.distroId && rec.rowId && typeof this.distroFace === 'function') {
            const d = (this.getDistros() || []).find(x => x.id === rec.distroId);
            const face = d ? this.distroFace(d) : null;
            const info = face ? face.rowInfo.get(rec.rowId) : null;
            if (info) {
                conn = info.conn;
                // the row's breaker, a multi row's as well as a direct
                // one's (owner, 2026-11-12: the output's breaker wins);
                // a paired row is on its primary's
                const primary = info.row.pairedWith && face.rowInfo.get(info.row.pairedWith);
                const rowA = Number(((primary && primary.row) || info.row).breakerA);
                if (rowA > 0) breakerA = rowA;
                // an Edison output picked 5-15 or 5-20 holds its circuit to
                // that receptacle (edisonRowType, where the app has it)
                if (info.conn.id === 'edison' && typeof this.edisonRowType === 'function') {
                    const et = this.edisonRowType(info.row);
                    if (et && et.picked && Number(et.ratingA) > 0) breakerA = Math.min(breakerA, Number(et.ratingA));
                }
            }
        }
        if (Number(bt.circuitA) > 0) breakerA = Number(bt.circuitA);
        const size = Number(bt.boxSize);
        return {
            own: false, breakout: bt,
            volts: Number(rec.volts) > 0 ? Number(rec.volts) : own.volts,
            breakerA, boxSize: Number.isFinite(size) && size >= 1 ? size : 6,
            feedLegA: Number(bt.feedLegA) || 0, typeId: rec.type || null, conn,
            // the Amperage it was dropped with picks an Edison breakout's
            // outlet, as the screen's own box does
            tailA: Number(rec.amps) > 0 ? Number(rec.amps) : (Number(own.tailA) || own.breakerA),
            plugged: null, from: rec.from,
        };
    }

    // ---- an Edison breakout's outlet (owner, 2026-11-12) ------------------
    //
    // "if I choose 20 amps, then it should be 5-20. If I choose 15, it
    // should be 5-15": the screen's Amperage picks its Multi → Edison
    // breakout's outlet. 20 A or more is a 5-20 (16 A continuous), anything
    // under is a 5-15 (12 A). An old show maps from the Amperage it was
    // saved with: 15 and 16 A read 5-15, 20 A reads 5-20, and 30 A reads
    // 5-20 behind a breaker larger than it (breakerOverChecks says OVER).
    // Null for every other breakout - the L21-30 Edison box's outlets are
    // its own 5-20s on 15 A circuits.
    edisonTypeForAmps(amps) {
        const types = typeof this.edisonTypes === 'function' ? this.edisonTypes() : [];
        const want = Number(amps) >= 20 ? '5-20' : '5-15';
        return types.find(t => t.id === want) || null;
    }

    specEdisonType(spec) {
        if (!spec || !spec.breakout || spec.breakout.id !== 'soca-edison') return null;
        return this.edisonTypeForAmps(spec.tailA);
    }

    screenEdisonType(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        return this.specEdisonType(this._ownSpecBase(layer));
    }

    // A connector name as one source's circuits say it: "Edison" is the
    // outlet its Amperage picks, "Edison 5-15"; anything else as it is.
    specConnectorText(spec, name) {
        const n = String(name || '');
        if (n !== 'Edison') return n;
        const et = this.specEdisonType(spec);
        return et ? `Edison ${et.name}` : n;
    }

    // What one circuit of `spec` carries: `pct` of its breaker, held to
    // 80% of an Edison breakout's outlet (12 A on a 5-15, 16 A on a 5-20).
    specUsableA(spec, pct) {
        if (!spec) return 0;
        let a = (Number(spec.breakerA) || 0) * pct;
        const et = this.specEdisonType(spec);
        if (et) a = Math.min(a, et.ratingA * 0.8);
        return a;
    }

    // The screen's power info line (owner, 2026-11-12): where the outputs
    // its circuits are plugged into differ from its Amperage, the output
    // wins and the line says so - "Circuits 4 to 9 use DS1 output 3
    // (Edison 5-20, 20 A)." - and the breaker its own circuits are on. ''
    // where every output agrees with the Amperage.
    powerBreakerSourceText(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return '';
        const typed = parseFloat(layer.powerAmperage) || 0;
        const plan = typeof this.getSocaPlan === 'function' ? this.getSocaPlan(layer) : [];
        if (!plan.length) return '';
        const distros = this.getDistros() || [];
        const groups = new Map();
        let differs = false;
        for (const s of plan) {
            const d = s.distroId ? distros.find(x => x && x.id === s.distroId) : null;
            const box = d && typeof this.faceBox === 'function' ? this.faceBox(d, s.number) : null;
            if (!box) continue;
            let amps = Number(box.conn.circuitA) || Number(box.breakerA) || 0;
            let name = typeof this._faceConnName === 'function' ? this._faceConnName(box) : box.conn.short;
            if (box.conn.id === 'edison') {
                const et = this.edisonRowType(box.row);
                if (et.picked) amps = Math.min(amps, et.ratingA);
            }
            if (box.conn.id === 'l2130e') name = 'L21-30 Edison';
            if (Math.abs(amps - typed) > 1e-9) differs = true;
            const key = `${d.id}|${box.number}`;
            const g = groups.get(key) || { d, box, name, amps, circuits: [] };
            s.legs.forEach(l => g.circuits.push(l.circuit));
            groups.set(key, g);
        }
        if (!differs) return '';
        const ranges = (list) => {
            const nums = [...new Set(list.map(Number).filter(Number.isFinite))].sort((a, b) => a - b);
            const parts = [];
            for (let i = 0; i < nums.length; i++) {
                let j = i;
                while (j + 1 < nums.length && nums[j + 1] === nums[j] + 1) j++;
                parts.push(j > i ? `${nums[i]} to ${nums[j]}` : String(nums[i]));
                i = j;
            }
            return { text: parts.join(', '), many: nums.length > 1 };
        };
        const lines = [...groups.values()]
            .sort((a, b) => Math.min(...a.circuits) - Math.min(...b.circuits))
            .map(g => {
                const r = ranges(g.circuits);
                return `Circuit${r.many ? 's' : ''} ${r.text} use${r.many ? '' : 's'} `
                    + `${this.distroLabel(g.d)} output ${g.box.number} (${g.name}, ${+g.amps.toFixed(1)} A).`;
            });
        const own = this.ownPowerSpec(layer);
        if (own.plugged && typed > 0 && Math.abs(own.breakerA - typed) > 1e-9) {
            lines.push(`Its circuits are on ${+own.breakerA.toFixed(1)} A breakers, not the `
                + `${+typed.toFixed(1)} A Amperage, which counts only on no distro.`);
        }
        return lines.join(' ');
    }

    // Two specs feed alike when breakout, voltage and breaker agree.
    powerSpecKey(spec) {
        return spec ? `${spec.breakout && spec.breakout.id}|${spec.volts}|${spec.breakerA}` : '';
    }

    // The screen's circuits 1..count as runs of one source each:
    // [{ start, end, spec }]. Null on a screen of one kind - every screen
    // with no list, and one whose list says nothing that differs from the
    // screen's own within its circuits - so every reader keeps its old
    // path there, byte for byte.
    powerSourceRanges(layer, count) {
        const recs = this._powerSourceRecords(layer);
        if (!recs.length) return null;
        const n = Math.max(0, Number(count) || 0);
        if (!n) return null;
        const own = this.ownPowerSpec(layer);
        const ownKey = this.powerSpecKey(own);
        const ranges = [];
        let start = 1;
        let spec = own;
        for (const rec of recs) {
            if (rec.from > n) break;
            if (rec.from > start) ranges.push({ start, end: rec.from - 1, spec });
            spec = this._specFromRecord(layer, rec, own);
            start = rec.from;
        }
        if (start <= n) ranges.push({ start, end: n, spec });
        if (ranges.every(r => this.powerSpecKey(r.spec) === ownKey)) return null;
        return ranges;
    }

    // Whether a screen is fed from more than one kind of source now.
    isMixedPower(layer) {
        if (!layer || !this._powerSourceRecords(layer).length) return false;
        return !!this.powerSourceRanges(layer, this.screenCircuits(layer).length);
    }

    // The source of one multi (its stable index) - the screen's own on a
    // screen of one kind.
    socaSpec(layer, socaIndex) {
        if (!layer || !this._powerSourceRecords(layer).length) return layer ? this.ownPowerSpec(layer) : null;
        const count = this._sourceCircuitCount(layer);
        const seg = this._socaSegments(layer, count).find(s => s.index === Number(socaIndex));
        return (seg && seg.spec) || this.ownPowerSpec(layer);
    }

    // The source of the circuit at `ordinal` (1-based).
    powerSpecAt(layer, ordinal, count = null) {
        const n = count == null ? this._sourceCircuitCount(layer) : count;
        const ranges = this.powerSourceRanges(layer, n);
        if (!ranges) return this.ownPowerSpec(layer);
        const r = ranges.find(x => x.start <= ordinal && ordinal <= x.end);
        return r ? r.spec : (ordinal > n ? ranges[ranges.length - 1].spec : this.ownPowerSpec(layer));
    }

    // The source of circuit number `num`.
    circuitPowerSpec(layer, num) {
        if (!layer || !this._powerSourceRecords(layer).length) return layer ? this.ownPowerSpec(layer) : null;
        const circuits = this.screenCircuits(layer);
        const o = circuits.findIndex(c => Number(c.num) === Number(num)) + 1;
        return o ? this.powerSpecAt(layer, o, circuits.length) : this.ownPowerSpec(layer);
    }

    // The circuit count the box sizes read, held for the naming burst
    // (_circuitTailCache, which every edit that moves circuits drops).
    _sourceCircuitCount(layer) {
        const cache = this._circuitTailCache;
        if (cache && this._sourceCountFor !== cache) {
            this._sourceCountFor = cache;
            this._sourceCountMemo = new WeakMap();
        }
        const memo = cache ? this._sourceCountMemo : null;
        if (memo && memo.has(layer)) return memo.get(layer);
        const n = this.screenCircuits(layer).length;
        if (memo) memo.set(layer, n);
        return n;
    }

    // How a chip or a label names a source: "110V Edison", "208V TRUE1",
    // "110V L21-30 Edison". Said only on a screen fed from several kinds.
    powerSpecText(spec) {
        if (!spec) return '';
        const bt = spec.breakout || {};
        let what = bt.id === 'l2130-edison' ? 'L21-30 Edison'
            : (spec.conn && spec.conn.kind === 'direct' ? spec.conn.short : (bt.connector || ''));
        if (String(bt.id || '').startsWith('l2130-') && bt.id !== 'l2130-edison') what = `L21-30 ${what}`;
        return `${+Number(spec.volts).toFixed(1)}V ${what}`.trim();
    }

    // The circuit's source in words, or '' on a screen of one kind - what
    // the circuit chips and labels add so a mixed wall says which circuit
    // rides which source.
    circuitSourceText(layer, num) {
        if (!this.isMixedPower(layer)) return '';
        return this.powerSpecText(this.circuitPowerSpec(layer, num));
    }

    // ---- packing --------------------------------------------------------

    // The automatic walk of a screen with sources: the screen's own walk,
    // then, from each source's first circuit on, the cabinets those
    // circuits held laid again at that source's circuit - the same
    // pattern, the same Organized / Max Capacity, the same 2fers - with
    // the circuits before it left exactly as they were. Null where the
    // list says nothing (the caller then walks as always).
    _mixedPowerAssignments(layer) {
        const recs = this._powerSourceRecords(layer);
        if (!recs.length) return null;
        const own = this.ownPowerSpec(layer);
        const pct = this.circuitCapacity(layer).pct;
        const wattsOf = (spec) => (Number(spec.volts) || 0) * this.specUsableA(spec, pct);
        const pass = (watts, claimed) => {
            this._packOverride = { watts, claimed, raw: true };
            try {
                return this.calculatePowerAssignments(layer);
            } finally {
                this._packOverride = null;
            }
        };
        // the screen's own circuits pack exactly as a screen of one kind
        // does (circuitCapacity, every limit it knows)
        let res = pass(this.circuitCapacityWatts(layer), null);
        const reserved = (typeof this.getOverrideNums === 'function' && !this.isCustomPower(layer))
            ? this.getOverrideNums(layer, 'power') : [];
        for (const rec of recs) {
            if (res.error) break;
            const circuits = res.circuits || [];
            // the source's first circuit in the walk's own count (a
            // redrawn circuit holds its number outside the walk)
            const k = this._walkOrdinal(rec.from, reserved, circuits.length);
            if (k == null || k > circuits.length) break;
            const spec = this._specFromRecord(layer, rec, own);
            const keep = circuits.slice(0, k - 1);
            const claimed = new Set(keep.flat());
            const sub = pass(wattsOf(spec), claimed);
            if (sub.error) { res = sub; break; }
            const subCircuits = sub.circuits || [];
            const out = { circuits: keep.concat(subCircuits), error: null };
            if (res.layers || sub.layers) {
                out.layers = (res.layers || keep.map(() => null)).slice(0, k - 1)
                    .concat(sub.layers || subCircuits.map(() => null));
            }
            if (res.runs || sub.runs) {
                const keptRuns = (res.runs || keep.map(c => [c.length])).slice(0, k - 1);
                const keptIds = (res.runIds || keep.map((_, i) => [i + 1])).slice(0, k - 1);
                const top = Math.max(0, ...keptIds.flat().map(Number).filter(Number.isFinite));
                out.runs = keptRuns.concat(sub.runs || subCircuits.map(c => [c.length]));
                out.runIds = keptIds.concat((sub.runIds || subCircuits.map((_, i) => [i + 1]))
                    .map(ids => ids.map(id => Number(id) + top)));
            }
            if (res.cut || sub.cut) out.cut = true;
            res = out;
        }
        return this._mergeOverrideCircuits(layer, res);
    }

    // A circuit ordinal in the screen's circuit order -> its place in the
    // automatic walk, which skips the numbers a redrawn circuit holds.
    _walkOrdinal(ordinal, reserved, walkCount) {
        if (!reserved || !reserved.length) return ordinal;
        const held = new Set(reserved.map(Number));
        let seen = 0, walk = 0, num = 0;
        while (seen < ordinal - 1) {
            num += 1;
            if (held.has(num)) { seen += 1; continue; }
            if (walk >= walkCount) return null;
            walk += 1;
            seen += 1;
        }
        return walk + 1;
    }

    // A hand-drawn (custom) screen's circuits from `ordinal` on, laid again
    // at `spec`'s circuit with the screen's own fill rule (Organized whole
    // rows, or Max Capacity packed full - _chunkPicksByCapacity) along its
    // flow pattern. The circuits before it are left as drawn. Writes the
    // paths, records nothing. Returns { ok } or { ok: false, why }.
    _relayCustomPowerFrom(layer, ordinal, spec) {
        if (!this.usesCustomCircuits(layer)) return { ok: true };
        const circuits = this.screenCircuits(layer);
        const tail = circuits.slice(ordinal - 1);
        if (!tail.length) return { ok: true };
        const startNum = Number(tail[0].num);
        const picks = [];
        tail.forEach(c => (c.panels || []).forEach((p, i) => {
            if (p && !p.blank) picks.push({ panel: p, layer: (c.layers && c.layers[i]) || layer });
        }));
        if (!picks.length) return { ok: true };
        const pattern = this.autoPowerPattern(layer);
        const lattice = this._latticeGridForPicks(layer, picks);
        const lines = this._patternLines(pattern, lattice.grid, lattice.bucket);
        const vertical = isVerticalFlowPattern(pattern);
        const corner = pattern.split('-')[0] || 'tl';
        const fromEnd = vertical ? corner[0] === 'b' : corner[1] === 'r';
        const posOf = (pick) => {
            const at = (vertical ? lattice.rowOf : lattice.colOf).get(pick.panel);
            return Number.isFinite(at) ? (fromEnd ? -at : at) : undefined;
        };
        let cut;
        this._specProbe = spec;
        try {
            cut = this._chunkPicksByCapacity(layer, 'power', startNum, lines, null,
                { vertical, zigzag: isZFlowPattern(pattern), posOf });
        } finally {
            this._specProbe = null;
        }
        if (!cut || cut.error) return { ok: false, why: (cut && cut.error) || 'nothing to lay' };
        const paths = layer.powerCustomPaths || (layer.powerCustomPaths = {});
        tail.forEach(c => { delete paths[c.num]; });
        cut.chunks.forEach(c => {
            if (!c.picks.length) return;
            paths[c.num] = c.picks.map(pick => this.makePathEntry(layer, pick.layer, pick.panel));
        });
        this._circuitTailCache = null;
        return { ok: true };
    }

    // ---- the drop -------------------------------------------------------

    // The voltage a source of nominal `nominal` (120 or 208, or an EU
    // figure) puts on this screen's circuits: the screen's own typed
    // figure where it is that nominal, else 110 for a 120V source (the
    // app's own figure for a 110V screen: amps divide by the typed 110 as
    // they always have) and the nominal itself otherwise.
    _sourceVoltsFor(layer, nominal) {
        const own = this.voltageNumber(layer && layer.powerVoltage);
        if (own > 0 && this.voltsMatch(own, nominal)) return own;
        return Number(nominal) === 120 ? 110 : Number(nominal);
    }

    // What a drop of an output puts on circuits that ride `atSpec` now:
    // null when the output feeds them as they are (the ordinary drop),
    // { refuse } when nothing can (a stage pin at 208V, a voltage the
    // distro does not give), else { rec, spec } - the record the drop
    // writes and the source it makes. `box` is the face box (a 1.5 row)
    // the drop lands on, or null for an old distro's typed output `type`.
    sourceForOutput(layer, atSpec, d, type, box = null) {
        const own = this.ownPowerSpec(layer);
        const bts = this.getPowerBreakoutTypes();
        const eligibleAt = (bt, v) => !!bt && this._breakoutEligible(bt, v);
        let rec;
        if (box) {
            const el = this.faceBoxEligible(d, box, layer, atSpec);
            if (el.ok) return null;
            if (!el.mixable) return { refuse: el.why };
            const volts = this.voltsMatch(atSpec.volts, box.volts)
                ? atSpec.volts : this._sourceVoltsFor(layer, box.volts);
            const ftype = this.faceBoxType(d, box);
            let bt;
            if (box.kind === 'multi') {
                const ids = ftype.breakouts || [];
                const pick = [atSpec.breakout, own.breakout].find(b => b && ids.includes(b.id)
                    && eligibleAt(b, volts));
                bt = pick || ids.map(id => bts.find(b => b.id === id))
                    .find(b => eligibleAt(b, volts)) || bts.find(b => b.id === ids[0]);
            } else {
                bt = [atSpec.breakout, own.breakout].find(b => b && b.id !== 'soca-l620'
                    && !String(b.id).startsWith('l2130-') && eligibleAt(b, volts))
                    || this._preferredBreakoutFor(volts);
            }
            if (!bt) return { refuse: el.why };
            rec = { type: 'face', distroId: d.id, rowId: box.rowId, breakout: bt.id, volts,
                    amps: Number(bt.circuitA) || parseFloat(layer.powerAmperage) || atSpec.breakerA };
        } else {
            const feedsV = this._outputFeedsVoltage(type, atSpec.volts);
            if (feedsV && type.breakouts.includes(atSpec.breakout.id)) return null;
            let volts;
            if (feedsV) volts = atSpec.volts;
            else if (this._outputFeedsVoltage(type, own.volts)) volts = own.volts;
            else volts = (type.volts || []).includes(208) ? 208 : 110;
            const sys = this.distroSystem(d);
            if (sys && this.systemVoltsFor(sys, volts) === null) {
                return { refuse: `${this.distroLabel(d)} gives ${this._systemFigures(sys).map(f => `${f}V`).join(' or ')}, `
                    + `and ${this._aAn(type.name)} ${type.name} runs at ${volts}V` };
            }
            const pick = [atSpec.breakout, own.breakout].find(b => b && type.breakouts.includes(b.id)
                && eligibleAt(b, volts));
            const bt = pick || type.breakouts.map(id => bts.find(b => b.id === id))
                .find(b => eligibleAt(b, volts)) || bts.find(b => b.id === type.breakouts[0]);
            rec = { type: type.id, distroId: d.id, breakout: bt.id, volts,
                    amps: Number(bt.circuitA) || parseFloat(layer.powerAmperage) || atSpec.breakerA };
        }
        const spec = this._specFromRecord(layer, rec, own);
        if (this.powerSpecKey(spec) === this.powerSpecKey(atSpec)) return null;
        if (this.powerSpecKey(spec) === this.powerSpecKey(own)) rec = { own: true };
        return { rec, spec: rec.own ? own : spec };
    }

    // The circuit a drop of another kind of source starts at: the first
    // unfed circuit of the cell `ordinal` sits in (the take's own anchor),
    // or for a whole-screen drop the first circuit of the first multi
    // nobody feeds. Null when there is none.
    _sourceDropStart(layer, ordinal) {
        const circuits = this.screenCircuits(layer);
        const count = circuits.length;
        if (!count) return null;
        const segs = this._socaSegments(layer, count);
        const assign = layer.powerSocaDistro || {};
        if (ordinal == null) {
            const s = segs.find(x => !assign[x.index]);
            return s ? s.start : null;
        }
        const o = Math.max(1, Math.min(count, ordinal));
        const cell = this._socaGridCell(layer, o, count);
        let start = cell.start;
        for (const s of segs) {
            if (s.end < cell.start || s.start > o) continue;
            if (assign[s.index]) start = Math.max(start, s.end + 1);
        }
        return start <= o ? start : null;
    }

    // Why circuits from `k` on cannot be laid again: one of them is fed
    // already (another box is cabled to it), or null.
    _sourceRelayBlocked(layer, k) {
        const count = this.screenCircuits(layer).length;
        const assign = layer.powerSocaDistro || {};
        const fed = this._socaSegments(layer, count)
            .filter(s => s.end >= k && assign[s.index]);
        if (!fed.length) return null;
        const nm = this._powerNaming(layer);
        const names = [...new Set(fed.map(s => {
            const rec = nm.socas.get(s.index);
            return (rec && rec.name) || `multi ${s.index}`;
        }))];
        return `${layer.name}'s circuits after this one are already on ${names.join(', ')}. `
            + 'Another kind of source lays the circuits after it again, so unplug those first.';
    }

    // The plan of a drop of another kind of source: { ok, mixed, from,
    // rec, spec, nums, text, boxName } or { ok: false, message }. `gate`
    // is the plug gate's pass ({ d, type, faceRow, mixed }); `ordinal`
    // the circuit dropped on, or null for a whole-screen drop.
    sourceDropPlan(payload, layer, gate, ordinal = null) {
        const glyph = gate.glyph;
        const k = this._sourceDropStart(layer, ordinal);
        if (k == null) {
            return { ok: false, glyph,
                     message: this.screenCircuits(layer).length
                        ? `Every circuit on ${layer.name} already has a distro.`
                        : `${layer.name} has no circuits to feed.` };
        }
        const blocked = this._sourceRelayBlocked(layer, k);
        if (blocked) return { ok: false, glyph, message: blocked };
        const atSpec = this.powerSpecAt(layer, k);
        const box = gate.faceRow ? (this.faceRowFreeBoxes(gate.d, gate.faceRow)[0] || null) : null;
        if (gate.faceRow && !box) {
            return { ok: false, glyph,
                     message: `Every ${gate.type.name} on ${this.distroLabel(gate.d)} is in use.` };
        }
        const src = this.sourceForOutput(layer, atSpec, gate.d, gate.type, box);
        if (!src) return null;
        if (src.refuse) return { ok: false, glyph, message: src.refuse };
        const circuits = this.screenCircuits(layer);
        const nums = circuits.slice(k - 1).map(c => c.num);
        const from = this.getPowerCircuitLabel(layer, circuits[k - 1].num);
        const number = box ? box.number : (payload.number != null ? parseInt(payload.number, 10) : null);
        const boxName = number != null ? this.distroBoxName(gate.d, number) : this.distroLabel(gate.d);
        const what = this.powerSpecText(src.spec);
        const usable = +this.specUsableA(src.spec, this.circuitCapacity(layer).pct).toFixed(2);
        return {
            ok: true, mixed: true, glyph, from: k, rec: src.rec, spec: src.spec, nums,
            number, boxName, face: !!box, direct: !!(box && box.kind === 'direct'),
            badge: gate.type.badge, warn: null, amps: 0,
            text: `${boxName} → ${from} on · ${what}, circuits after it re-laid at ${usable} A`,
        };
    }

    // The drop of another kind of source, in ONE undo step: the source
    // written from its first circuit, the circuits from there laid again
    // (a hand-drawn screen's paths are redrawn; an automatic one re-walks
    // on read), and the first box of them fed from the output dropped.
    applySourceDrop(payload, layer, plan, action = 'Feed From Another Source') {
        if (!plan || !plan.ok || !plan.mixed) return false;
        if (this._lockedRefused(layer)) return false;
        const k = plan.from;
        const before = JSON.stringify(layer.powerSources || null);
        const keep = this._powerSourceRecords(layer).filter(r => r.from < k)
            .map(r => { const c = Object.assign({}, r); return c; });
        const rec = Object.assign({ from: k }, plan.rec);
        // A run that only says "the screen's own" after the screen's own is
        // no source at all.
        const ownKey = this.powerSpecKey(this.ownPowerSpec(layer));
        const prevOwn = k === 1
            || this.powerSpecKey(this.powerSpecAt(layer, k - 1)) === ownKey;
        if (!(rec.own && prevOwn)) keep.push(rec);
        const shared = this._lockedPowerTrial();
        // The splits past the source's first circuit named circuits that
        // are laid again.
        if (Array.isArray(layer.powerSocaSplits)) {
            layer.powerSocaSplits = layer.powerSocaSplits.filter(p => parseInt(p, 10) < k - 1);
        }
        // an emptied list is written as [] (a missing key would leave the
        // server's copy as it was, and a reload would bring it back)
        layer.powerSources = keep;
        this._circuitTailCache = null;
        if (this.usesCustomCircuits(layer)) {
            const relaid = this._relayCustomPowerFrom(layer, k, plan.spec);
            if (!relaid.ok) {
                if (before === 'null') delete layer.powerSources; else layer.powerSources = JSON.parse(before);
                this._circuitTailCache = null;
                this._dockSay && this._dockSay(`Cannot lay ${layer.name}'s circuits again: ${relaid.why}`);
                return false;
            }
        }
        // Feed the first box of the new source from the output dropped.
        const count = this.screenCircuits(layer).length;
        if (k > count) {
            if (shared()) return false;
            this.updateLayers([layer], true, action);
            return true;
        }
        const cell = this._socaGridCell(layer, k, count);
        const touched = new Set([layer]);
        let number = plan.number;
        if (number == null) {
            // a whole-screen plug onto an old distro: the number its own
            // sequence deals
            const segs = this._socaSegments(layer, count);
            const seg = segs.find(s => s.start === k);
            if (!seg) {
                if (shared()) return false;
                this.updateLayers([layer], true, action);
                return true;
            }
            (this.setSocaDistro(layer, seg.index, payload.distroId, false) || [])
                .forEach(l => touched.add(l));
            this._circuitTailCache = null;
            const nrec = this._powerNaming(layer).socas.get(seg.index);
            number = nrec ? nrec.number : null;
            if (number != null && plan.rec.type && !plan.face) {
                this._stampBoxType(payload.distroId, number, plan.rec.type);
            }
        } else {
            if (!plan.face && plan.rec.type) this._stampBoxType(payload.distroId, number, plan.rec.type);
            const lastOf = plan.direct ? k : Math.min(cell.start + cell.size - 1, cell.end);
            const take = this._socaTakePlan(layer, lastOf, payload.distroId, number);
            if (take.ok) this._takeSocaApply(layer, take, payload.distroId).forEach(l => touched.add(l));
        }
        if (shared()) return false;
        this.updateLayers([...touched], true, action);
        if (typeof this._restateNaming === 'function') this._restateNaming();
        sendClientLog('power_source_drop', { layerId: layer.id, from: k, rec: plan.rec });
        const spec = plan.spec;
        const usable = +this.specUsableA(spec, this.circuitCapacity(layer).pct).toFixed(2);
        const label = this.getPowerCircuitLabel(layer, (this.screenCircuits(layer)[k - 1] || {}).num);
        this._dockSay && this._dockSay(`${layer.name}: ${label} on ride ${this.powerSpecText(spec)}, `
            + `laid again at ${usable} A a circuit. The circuits before it are as they were.`);
        return true;
    }

    // ---- a hole, and closing it (owner, 2026-11-12) -----------------------
    //
    // "Unplugging a source in the middle leaves a hole": a source whose
    // circuits nobody feeds any more, with fed circuits after it, keeps its
    // circuits where they were (pruneDormantPowerSources only lets go of
    // the LAST source, from the end back), so the circuits after it never
    // shift under the boxes they are plugged into. The hole stays until
    // somebody resets it: right-click it on the canvas, "Reset these
    // circuits" (resetPowerHole).

    // The holes on a screen: [{ rec, index, start, end, first, last }] -
    // the source record, its place in the list, its circuits (ordinals)
    // and its multis (stable indexes, first..last; none when its circuits
    // make no whole multi of their own).
    powerSourceHoles(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return [];
        const recs = this._powerSourceRecords(layer);
        if (!recs.length) return [];
        const count = this.screenCircuits(layer).length;
        if (!count) return [];
        const segs = this._socaSegments(layer, count);
        const assign = layer.powerSocaDistro || {};
        const fed = (s) => !!assign[s.index];
        const out = [];
        recs.forEach((rec, i) => {
            const start = rec.from;
            const end = Math.min(count, recs[i + 1] ? recs[i + 1].from - 1 : count);
            if (start > count || end < start) return;
            const mine = segs.filter(s => s.end >= start && s.start <= end);
            if (mine.some(fed)) return;
            if (!segs.some(s => s.start > end && fed(s))) return;
            out.push({ rec, index: i, start, end,
                       first: mine.length ? mine[0].index : null,
                       last: mine.length ? mine[mine.length - 1].index : null });
        });
        return out;
    }

    // The hole circuit number `num` of `layer` sits in, or null.
    powerHoleAt(layer, num) {
        if (!layer) return null;
        const circuits = this.screenCircuits(layer);
        const o = circuits.findIndex(c => Number(c.num) === Number(num)) + 1;
        if (!o) return null;
        return this.powerSourceHoles(layer).find(h => h.start <= o && o <= h.end) || null;
    }

    // "Reset these circuits": close the hole. Its circuits and every one
    // after are laid again from the hole's first circuit: the next
    // source's setting takes over there (the screen's own where the next
    // is the screen's own), every later source keeps its circuit count,
    // and every multi after the hole keeps its distro, number, length,
    // name and phase spots, re-keyed down past the hole's multis, so each
    // box stays plugged into the circuits it fed. A circuit's cable and
    // typed label follow it the same way. ONE undo step; a locked screen
    // (or a locked member of its wall) refuses, saying why.
    resetPowerHole(layer, from) {
        if (!layer) return false;
        const hole = this.powerSourceHoles(layer).find(h => h.rec.from === Number(from));
        if (!hole) return false;
        const group = layer.group_id && typeof this.groupMembersOf === 'function'
            ? this.groupMembersOf(layer) : [];
        if (this._lockedRefused(group.length ? group : [layer])) return false;
        const recs = this._powerSourceRecords(layer);
        const i = hole.index;
        const next = recs[i + 1];
        if (!next) return false;
        const delta = next.from - hole.start;          // circuits the hole held
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const cut = hole.first != null ? hole.last - hole.first + 1 : 0;
        const firstAfter = segs.find(s => s.start >= next.from);
        const fromIdx = firstAfter ? firstAfter.index : null;
        const shared = this._lockedPowerTrial();
        // The records: the hole's goes, the next source starts where the
        // hole did, every later one moves down with it.
        const before = recs.slice(0, i);
        const prevOwn = !before.length || !!before[before.length - 1].own;
        const out = before.map(r => Object.assign({}, r));
        if (!(next.own && prevOwn)) out.push(Object.assign({}, next, { from: hole.start }));
        recs.slice(i + 2).forEach(r => out.push(Object.assign({}, r, { from: r.from - delta })));
        // The splits: the hole's go, the ones after it move down; where the
        // screen's own circuits run on into the next source's (the next was
        // the screen's own), the multi before the hole still ends there.
        const splits = (Array.isArray(layer.powerSocaSplits) ? layer.powerSocaSplits : [])
            .map(p => parseInt(p, 10)).filter(Number.isFinite);
        const nextSplits = [];
        for (const p of splits) {
            if (p < hole.start) nextSplits.push(p);
            else if (p >= next.from) nextSplits.push(p - delta);
        }
        if (next.own && prevOwn && hole.start > 1) {
            const prevStart = before.length ? before[before.length - 1].from : 1;
            const size = this._ownSpecBase(layer).boxSize;
            if ((hole.start - prevStart) % size !== 0 && !nextSplits.includes(hole.start - 1)) {
                nextSplits.push(hole.start - 1);
            }
        }
        layer.powerSocaSplits = [...new Set(nextSplits)].sort((a, b) => a - b);
        // The per-multi stores: the hole's multis go, the ones after it
        // move down by as many.
        if (fromIdx != null && hole.first != null) {
            const indexOf = (n) => (n < hole.first ? n : (n >= fromIdx ? n - cut : null));
            if (typeof this._rekeyMultiHolds === 'function') this._rekeyMultiHolds(layer, indexOf);
            for (const field of ['powerSocaDistro', 'powerSocaLengths', 'powerSocaPhasePos',
                                 'powerSocaPhaseOffset', 'powerSocaNames', 'powerSocaNumber']) {
                const store = layer[field];
                if (!store || typeof store !== 'object') continue;
                const moved = {};
                for (const key of Object.keys(store)) {
                    const n = parseInt(key, 10);
                    if (!Number.isFinite(n)) { moved[key] = store[key]; continue; }
                    const ni = indexOf(n);
                    if (ni != null) moved[ni] = store[key];
                }
                layer[field] = moved;
            }
        }
        // The per-circuit stores: a circuit after the hole keeps its cable
        // and typed label as it moves down; the hole's are forgotten (no
        // feed, no cable).
        for (const field of ['powerCircuitCables', 'powerLabelOverrides']) {
            const store = layer[field];
            if (!store || typeof store !== 'object') continue;
            const moved = {};
            for (const key of Object.keys(store)) {
                const n = parseInt(key, 10);
                if (!Number.isFinite(n)) { moved[key] = store[key]; continue; }
                if (n < hole.start) moved[key] = store[key];
                else if (n >= next.from) moved[n - delta] = store[key];
            }
            layer[field] = moved;
        }
        layer.powerSources = out;
        this._circuitTailCache = null;
        // A hand-drawn screen's circuits from the hole on are drawn again,
        // each source from its own first circuit, in order (an automatic
        // one re-walks on read).
        if (this.usesCustomCircuits(layer)) {
            const own = this.ownPowerSpec(layer);
            const runs = out.filter(r => r.from >= hole.start)
                .map(r => ({ from: r.from, rec: r }));
            if (!runs.length || runs[0].from !== hole.start) runs.unshift({ from: hole.start, rec: null });
            for (const run of runs) {
                const spec = run.rec ? this._specFromRecord(layer, run.rec, own) : own;
                const relaid = this._relayCustomPowerFrom(layer, run.from, spec);
                this._circuitTailCache = null;
                if (!relaid.ok) break;
            }
        }
        if (shared()) return false;
        this.updateLayers([layer], true, 'Reset Circuits');
        if (typeof this._restateNaming === 'function') this._restateNaming();
        sendClientLog('power_hole_reset', { layerId: layer.id, from: hole.start, circuits: delta });
        return true;
    }

    // The canvas right-click on a hole's circuit: { label, title, run } or
    // null where the circuit under the cursor is in no hole.
    _prepareResetHoleMenu(x, y) {
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || []).find(l => l.id === hit.layerId);
        const circuit = under ? renderer._powerCircuitForPanel(under, hit.panel) : null;
        if (!circuit || !circuit.owner) return null;
        return this._resetHoleMenuFor(circuit.owner, circuit.circuitNum);
    }

    _resetHoleMenuFor(owner, num) {
        const hole = this.powerHoleAt(owner, num);
        if (!hole) return null;
        const circuits = this.screenCircuits(owner);
        const first = circuits[hole.start - 1];
        const last = circuits[hole.end - 1];
        const a = first ? this.getPowerCircuitLabel(owner, first.num) : hole.start;
        const b = last ? this.getPowerCircuitLabel(owner, last.num) : hole.end;
        const span = a === b ? `${a}` : `${a} to ${b}`;
        return {
            label: 'Reset these circuits',
            title: `${owner.name}'s circuits ${span} are on no distro, and the circuits after them are. `
                + 'Reset lays them again from here to the end of the screen with the next source\'s '
                + 'setting, closing the gap. The plugged boxes keep their circuits. One undo puts it back.',
            run: () => this.resetPowerHole(owner, hole.rec.from),
        };
    }

    // At a save: a source whose circuits nobody feeds any more goes, from
    // the last one back, and those circuits fall back to the source before
    // it ("Circuits follow their own source": no source, the screen's
    // own). Returns the layers it changed.
    pruneDormantPowerSources(layers) {
        const changed = [];
        for (const layer of layers || []) {
            if (!layer || !Array.isArray(layer.powerSources) || !layer.powerSources.length) continue;
            let recs = this._powerSourceRecords(layer);
            let dropped = false;
            while (recs.length) {
                const last = recs[recs.length - 1];
                const count = this.screenCircuits(layer).length;
                const assign = layer.powerSocaDistro || {};
                // A source whose first circuit lies past the screen's
                // circuits (no watts or voltage typed yet, or a wall that
                // shrank) is kept as it is, the way a split past the end is:
                // there is nothing to read it against, so nothing proves it
                // unfed.
                if (last.from > count) break;
                const fed = this._socaSegments(layer, count)
                    .some(s => s.end >= last.from && assign[s.index]);
                if (fed) break;
                recs = recs.slice(0, -1);
                dropped = true;
                layer.powerSources = recs;
                this._circuitTailCache = null;
            }
            if (dropped) changed.push(layer);
        }
        return changed;
    }
}

for (const k of Object.getOwnPropertyNames(_PowerSources.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PowerSources.prototype, k));
    }
}
