// app-phase-balance: the 3-phase balancing engine for LEDRasterApp - the
// search over partly-filled multis, the suggest/apply pair, the Balance
// dialog and the phasing help sheet. It also owns the phasing schemes,
// leg phasors and per-soca circuit positions / phase offsets the engine
// and the distro panel both read.
import { LEDRasterApp } from './app-core.js';

// The exhaustive search's ceiling, in arrangements - the product of every
// partly-filled multi's tail subsets on one distro. A multi has at most
// C(6,3) = 20 subsets and the largest real distro measured 540
// arrangements, so this is far past anything a show builds; past it the
// search falls back to a bounded descent and the dialog says its answer
// is the best FOUND, not the best there is.
const BALANCE_EXHAUSTIVE_CAP = 50000;
// Two scores within these are a tie: imbalance in points, busiest leg in
// amps. Ties keep the arrangement found first, and the current one is
// always tried first.
const BALANCE_TIE_PCT = 1e-7;
const BALANCE_TIE_A = 1e-6;
// What a result must beat to be offered at all: a hundredth of a point of
// imbalance, or (at equal imbalance) a thousandth of an amp off the
// busiest leg. Anything smaller is rounding, not a better arrangement.
const BALANCE_GAIN_PCT = 0.01;
const BALANCE_GAIN_A = 0.001;

class _PhaseBalance {

    // Every PARTLY-FILLED multi that lands on a 3-phase distro, with the
    // tail set it currently occupies. The unit of balancing is the multi,
    // so this is what the balancer searches over. Full multis are excluded:
    // under the wall-order rule the only lever is WHICH tails a multi uses,
    // and a 6-circuit multi uses all six - there is nothing to choose.
    //
    // `distroId` scopes the walk to one distro. Balancing is per distro now
    // (each Balance button lives on its distro's row): legs never interact
    // across services, so a show-wide pass was only ever N independent
    // problems solved at once - and it moved multis on distros the user was
    // not looking at. No argument keeps the show-wide walk for the callers
    // that genuinely want every distro (clearPhaseBalance's preview, tests).
    //
    // Each target carries `fromFlat` - the tail every circuit sits on NOW,
    // in walk order - and `circuits`, the plan records the leg maths books
    // them from. A target on a LOCKED screen (any member of a shared box)
    // is flagged `locked`: the search holds it exactly where it is.
    _balanceTargets(distroId) {
        const out = [];
        const distros = this.getDistros();
        const seenBoxes = new Set();
        const layers = this.project.layers || [];
        for (const layer of layers) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of this.getSocaPlan(layer)) {
                const d = distros.find(x => x.id === assign[s.soca]);
                if (!d || this.distroLegNames(d).length < 2) continue;
                if (distroId && d.id !== distroId) continue;
                // A face box (1.5) is as big as its connector: a direct
                // output is one circuit and always full, and nothing on a
                // box can move past its own tails.
                const faceBox = this.faceBox(d, s.number);
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    // A shared box is ONE multi to the balancer: its
                    // used-tail set spans every member, and moving tails
                    // re-deals the whole box - member order (layer order),
                    // ascending within each member, the same rule
                    // _resolveSharedSocas states. Emitted once, at the
                    // first member; a box already in clash or overflow has
                    // no legal arrangement to search, so it is left alone
                    // until the clash is resolved.
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    if (share.clash || share.overflow) continue;
                    const total = share.members.reduce((t, m) => t + m.legs, 0);
                    const members = share.members.map(m => {
                        const ml = layers.find(l => l.id === m.layerId);
                        const ms = ml && this.getSocaPlan(ml).find(x => x.soca === m.soca);
                        return ml && ms && ms.legs.length === m.legs
                            ? { layer: ml, soca: m.soca, legs: m.legs,
                                tails: m.tails.slice(), s: ms }
                            : null;
                    }).filter(Boolean);
                    if (members.length !== share.members.length) continue;
                    // Full is full against the BOX's fan - the smallest
                    // member breakout's size, the same capacity the shared
                    // deal answers to. Six for socas, three for an L21-30.
                    const boxSize = Math.min(...members
                        .map(m => this.socaBoxSize(m.layer)),
                        faceBox ? faceBox.size : Infinity);
                    if (total >= boxSize) continue;
                    // per circuit, member order - index k of from/to is the
                    // k-th circuit of this walk
                    const circuits = members.flatMap(m => m.s.legs
                        .map((leg, li) => ({ layer: m.layer, s: m.s, li, leg })));
                    out.push({
                        layer, soca: s.soca, name: s.name, distroId: d.id,
                        legs: total, members, boxSize,
                        locked: members.some(m => !!m.layer.locked),
                        layerName: members.map(m => m.layer.name).join(' + '),
                        positions: members.flatMap(m => m.tails)
                            .sort((a, b) => a - b),
                        fromFlat: members.flatMap(m => m.tails),
                        circuits,
                        amps: circuits.map(c => c.leg.amps),
                        labels: circuits.map(c => c.leg.label),
                        scheme: this._circuitSchemeFor(d, circuitV).id
                    });
                    continue;
                }
                const ownSize = Math.min(this.socaBoxSize(layer),
                                         faceBox ? faceBox.size : Infinity);
                if (s.legs.length >= ownSize) continue;
                const positions = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                out.push({
                    layer, soca: s.soca, name: s.name, distroId: d.id,
                    legs: s.legs.length,
                    boxSize: ownSize,
                    locked: !!layer.locked,
                    positions,
                    fromFlat: positions.slice(),
                    circuits: s.legs.map((leg, li) => ({ layer, s, li, leg })),
                    amps: s.legs.map(l => l.amps),
                    // The circuits' CURRENT labels through the one authority -
                    // the balance dialog names each moved circuit by the
                    // bubble on the canvas, never by a re-derived ordinal.
                    labels: s.legs.map(l => l.label),
                    scheme: this._circuitSchemeFor(d, circuitV).id
                });
            }
        }
        return out;
    }

    // Why nothing on this distro is movable, said in the balancer's own
    // terms. The reference show pressed Balance and read silence: the DJ
    // booths' three multis were assigned to C2 but the grouped wall's auto
    // plan errors out, so the multis do not EXIST - and the dialog computed
    // to a no-op without saying why. Every reason a multi is passed over is
    // collected here so the no-targets dialog can state them instead:
    //   full     multis (and shared boxes) with every circuit of their
    //            connector taken - nothing to choose
    //   crowded  multis with more circuits than their connector holds - a
    //            several-circuit multi left on a one-circuit direct output
    //   clashed  shared boxes left alone until their tail clash/overflow is
    //            resolved
    //   phantom  screens whose powerSocaDistro names this distro for a multi
    //            the current circuit plan does not produce - an empty plan
    //            (power error, peer-served member) or one that shrank
    // Sizes are the CONNECTOR's (the face box's), never the screen's six.
    _balanceBlockers(distroId) {
        const out = { full: [], crowded: [], clashed: [], phantom: [] };
        if (!distroId) return out;
        const d = this.getDistros().find(x => x.id === distroId) || null;
        const layers = this.project.layers || [];
        const seenBoxes = new Set();
        for (const layer of layers) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            for (const s of plan) {
                if (assign[s.soca] !== distroId) continue;
                const fbox = d ? this.faceBox(d, s.number) : null;
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    // deduped: a box whose members are two multis of ONE
                    // screen should not name the screen twice
                    const names = [...new Set(share.members
                        .map(m => m.layerName))].join(' + ');
                    const size = Math.min(...share.members.map(m => {
                        const ml = layers.find(l => l.id === m.layerId);
                        return ml ? this.socaBoxSize(ml) : Infinity;
                    }), this.socaBoxSize(layer), fbox ? fbox.size : Infinity);
                    if (share.clash || share.overflow) {
                        out.clashed.push({ name: s.name, layers: names,
                            overflow: !!share.overflow, size });
                    } else if (share.members.reduce((t, m) => t + m.legs, 0) >= size) {
                        out.full.push({ name: s.name, layers: names });
                    }
                    continue;
                }
                const size = Math.min(this.socaBoxSize(layer),
                                      fbox ? fbox.size : Infinity);
                if (s.legs.length > size) {
                    out.crowded.push({ name: s.name, layers: layer.name,
                        legs: s.legs.length, size,
                        conn: fbox ? fbox.conn.short : '' });
                } else if (s.legs.length >= size) {
                    out.full.push({ name: s.name, layers: layer.name });
                }
            }
            // Assignments pointing past the plan: the multi the user set up
            // is not in the drawing any more. Say so - this is exactly the
            // state that reads as "balancing won't calculate".
            const have = new Set(plan.map(s => s.soca));
            const missing = Object.keys(assign)
                .filter(k => assign[k] === distroId
                    && !have.has(parseInt(k, 10)));
            if (missing.length) {
                out.phantom.push({
                    layers: layer.name, count: missing.length,
                    reason: plan.length
                        ? 'the circuit plan no longer reaches that multi'
                        : (this._socaPlanEmptyReason(layer)
                            || 'the screen routes no circuits'),
                });
            }
        }
        return out;
    }

    // Worst imbalance across every 3-phase distro show-wide, or over the
    // one distro a scoped balance is working.
    _worstImbalance(distroId) {
        return this.getDistroLoads()
            .filter(b => b.id && b.legs && (!distroId || b.id === distroId))
            .reduce((m, b) => Math.max(m, b.imbalancePct), 0);
    }

    // The real figures of one distro as it stands: imbalance and the
    // busiest leg, read off getDistroLoads itself. Null for a distro with
    // no legs.
    _balanceRealFigures(distroId) {
        this._circuitTailCache = null;
        const L = this.getDistroLoads().find(b => b.id === distroId);
        if (!L || !L.legs) return null;
        return { imb: L.imbalancePct, busiest: L.legs.worstAmps };
    }

    // The leg phasor ONE circuit adds when it sits on `tail`, as
    // [Xre, Xim, Yre, Yim, Zre, Zim] - booked through the same authority
    // getDistroLoads books with (distroCircuitLegs, _bookCircuitOnLegs), so
    // the search scores exactly what the dock will print.
    _balanceCircuitPhasor(d, c, tail) {
        const store = {
            legWatts: { X: 0, Y: 0, Z: 0 },
            legPhasor: { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 }, Z: { re: 0, im: 0 } },
            pairWatts: {},
        };
        const info = this.distroCircuitLegs(d, c.layer, c.s, 0, [tail]);
        this._bookCircuitOnLegs(store, d, info, Number(c.leg.watts) || 0,
                                parseFloat(c.layer.powerVoltage) || 0);
        const p = store.legPhasor;
        return [p.X.re, p.X.im, p.Y.re, p.Y.im, p.Z.re, p.Z.im];
    }

    // Imbalance (NEMA-style, as getDistroLoads states it) and the busiest
    // leg of a summed phasor vector over the distro's legs.
    _balanceFigures(v, names) {
        const at = { X: 0, Y: 2, Z: 4 };
        const amps = names.map(k => Math.hypot(v[at[k]], v[at[k] + 1]));
        const avg = amps.reduce((t, x) => t + x, 0) / amps.length;
        return {
            imb: avg > 0 ? (Math.max(...amps.map(x => Math.abs(x - avg))) / avg) * 100 : 0,
            busiest: Math.max(...amps),
        };
    }

    // The objective, lexicographic: lower imbalance first, then the lighter
    // busiest leg. (A result whose busiest leg is heavier than before is
    // never a candidate at all - see _balanceSolve.)
    _balanceBetter(a, b) {
        if (a.imb < b.imb - BALANCE_TIE_PCT) return true;
        return Math.abs(a.imb - b.imb) <= BALANCE_TIE_PCT
            && a.busiest < b.busiest - BALANCE_TIE_A;
    }

    // Whether a REAL result is worth offering over the REAL current
    // figures: the busiest leg no heavier, and either the imbalance
    // clearly lower or - at the same imbalance - the busiest leg clearly
    // lighter.
    _balanceGains(after, before) {
        if (!after || !before) return false;
        if (after.busiest > before.busiest + BALANCE_TIE_A) return false;
        if (after.imb < before.imb - BALANCE_GAIN_PCT) return true;
        return after.imb <= before.imb + BALANCE_TIE_PCT
            && after.busiest < before.busiest - BALANCE_GAIN_A;
    }

    // Every k-subset of tails 1..n, ascending, in lexicographic order.
    _balanceSubsets(n, k) {
        const out = [];
        const cur = [];
        const walk = (start) => {
            if (cur.length === k) { out.push(cur.slice()); return; }
            for (let t = start; t <= n - (k - cur.length) + 1; t++) {
                cur.push(t);
                walk(t + 1);
                cur.pop();
            }
        };
        if (k >= 0 && k <= n) walk(1);
        return out;
    }

    // Solve one distro. Wall-order rule: circuits always map to the chosen
    // tails ascending in wall order, so a multi's options are its tail
    // SUBSETS (C(6,L) - at most 20) plus where it sits now; a shared box's
    // options are the subsets dealt across its members, plus where it sits
    // now (which need not be a deal - a stored member can sit below an
    // earlier one). Every combination is scored when the product is within
    // BALANCE_EXHAUSTIVE_CAP; past it a bounded descent (best single-multi
    // change, repeated) runs instead and the result says so.
    //
    // Held fixed, booked where they sit: every circuit that is not a
    // searched target - full multis, locked screens' multis (a shared box
    // with a locked member whole), clashed boxes.
    // Never offered: a tail whose circuit something else on the distro
    // already holds - a paired connector's twin is one circuit, and two
    // loads on it is a double patch. Two searched multis on paired
    // connectors are kept apart the same way.
    // Never accepted: a result whose busiest leg is heavier than now.
    //
    // Nothing is written; the score is the summed phasors.
    _balanceSolve(distroId) {
        const d = this.getDistros().find(x => x.id === distroId) || null;
        const names = d ? this.distroLegNames(d) : [];
        const all = this._balanceTargets(distroId);
        const free = all.filter(t => !t.locked);
        const res = {
            distroId, targets: free, locked: all.filter(t => t.locked),
            options: [], choice: free.map(() => 0),
            before: this._balanceRealFigures(distroId), model: null,
            searched: 0, total: 0, exhaustive: true, blockedByBusiest: false,
        };
        if (!d || names.length < 2 || !res.before || !free.length) return res;

        const face = this.distroFace(d);
        const keyOf = (s, tail) => {
            const box = face ? this.faceBox(d, s.number) : null;
            return box ? this._facePhysical(face, box, tail).key : `${s.number}:${tail}`;
        };
        const searchedMulti = new Set();
        free.forEach(t => t.circuits.forEach(c => searchedMulti.add(`${c.layer.id}:${c.s.soca}`)));
        // Everything on the distro that is not searched, where it sits now;
        // and how many circuits each physical circuit carries now.
        const base = [0, 0, 0, 0, 0, 0];
        const fixed = new Map();
        const now = new Map();
        const bump = (m, k) => m.set(k, (m.get(k) || 0) + 1);
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            for (const s of this.getSocaPlan(layer)) {
                if (assign[s.soca] !== d.id) continue;
                const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                const searched = searchedMulti.has(`${layer.id}:${s.soca}`);
                s.legs.forEach((leg, li) => {
                    const tail = pos[li] || li + 1;
                    const key = keyOf(s, tail);
                    bump(now, key);
                    if (searched) return;
                    bump(fixed, key);
                    const v = this._balanceCircuitPhasor(d, { layer, s, leg }, tail);
                    for (let i = 0; i < 6; i++) base[i] += v[i];
                });
            }
        }
        // A physical circuit may carry what it carries now (a double patch
        // already on the drawing is the distro check's to say), never more.
        const limit = (k) => Math.max(1, now.get(k) || 0);

        const options = free.map(t => {
            const opts = [{ keep: true, tails: t.fromFlat.slice() }];
            const seen = new Set([opts[0].tails.join(',')]);
            for (const set of this._balanceSubsets(t.boxSize, t.legs)) {
                if (seen.has(set.join(','))) continue;
                seen.add(set.join(','));
                opts.push({ keep: false, tails: set });
            }
            for (const o of opts) {
                o.keys = t.circuits.map((c, k) => keyOf(c.s, o.tails[k]));
                o.vec = [0, 0, 0, 0, 0, 0];
                t.circuits.forEach((c, k) => {
                    const v = this._balanceCircuitPhasor(d, c, o.tails[k]);
                    for (let i = 0; i < 6; i++) o.vec[i] += v[i];
                });
            }
            return opts.filter(o => o.keep
                || o.keys.every(k => (fixed.get(k) || 0) + 1 <= limit(k)));
        });
        res.options = options;
        res.total = options.reduce((p, o) => p * o.length, 1);

        const used = new Map(fixed);
        const fits = (o) => o.keys.every(k => (used.get(k) || 0) + 1 <= limit(k));
        const take = (o, sign) => o.keys.forEach(k => used.set(k, (used.get(k) || 0) + sign));
        const plus = (a, b) => a.map((x, i) => x + b[i]);

        const current = this._balanceFigures(
            options.reduce((v, o) => plus(v, o[0].vec), base), names);
        res.model = current;
        let best = current;
        let bestChoice = free.map(() => 0);
        const consider = (f, choice) => {
            res.searched += 1;
            if (f.busiest > current.busiest + BALANCE_TIE_A) {
                if (f.imb < current.imb - BALANCE_GAIN_PCT) res.blockedByBusiest = true;
                return false;
            }
            if (!this._balanceBetter(f, best)) return false;
            best = f;
            bestChoice = choice.slice();
            return true;
        };

        if (res.total <= BALANCE_EXHAUSTIVE_CAP) {
            const cur = free.map(() => 0);
            const walk = (t, vec) => {
                if (t === options.length) {
                    consider(this._balanceFigures(vec, names), cur);
                    return;
                }
                for (let i = 0; i < options[t].length; i++) {
                    const o = options[t][i];
                    if (!fits(o)) continue;
                    take(o, 1);
                    cur[t] = i;
                    walk(t + 1, plus(vec, o.vec));
                    take(o, -1);
                }
                cur[t] = 0;
            };
            walk(0, base);
        } else {
            res.exhaustive = false;
            const valid = (choice) => {
                used.clear();
                fixed.forEach((n, k) => used.set(k, n));
                for (let t = 0; t < options.length; t++) {
                    const o = options[t][choice[t]];
                    if (!fits(o)) return false;
                    take(o, 1);
                }
                return true;
            };
            const vecOf = (choice) => choice.reduce((v, i, t) => plus(v, options[t][i].vec), base);
            let choice = free.map(() => 0);
            for (let pass = 0; pass < 100; pass++) {
                let moved = false;
                for (let t = 0; t < options.length; t++) {
                    for (let i = 0; i < options[t].length; i++) {
                        if (i === choice[t]) continue;
                        const next = choice.slice();
                        next[t] = i;
                        if (!valid(next)) continue;
                        if (consider(this._balanceFigures(vecOf(next), names), next)) {
                            choice = next;
                            moved = true;
                        }
                    }
                }
                if (!moved) break;
            }
        }
        res.choice = bestChoice;
        return res;
    }

    // The moves one solve proposes: every target whose chosen option is not
    // where it sits now. `from`/`to` are per circuit, walk order.
    _balanceMovesOf(res) {
        return res.targets.map((t, i) => {
            const o = res.options[i] && res.options[i][res.choice[i]];
            if (!o || o.keep) return null;
            return {
                layerId: t.layer.id, layerName: t.layerName || t.layer.name,
                soca: t.soca, distroId: t.distroId,
                name: t.name, legs: t.legs,
                members: t.members ? t.members.map(m => ({
                    layerId: m.layer.id, soca: m.soca, legs: m.legs })) : null,
                from: t.fromFlat.slice(), to: o.tails.slice(),
                amps: t.amps, labels: t.labels,
            };
        }).filter(m => m && m.from.some((p, k) => p !== m.to[k]));
    }

    // Write one move onto the layers it names; returns the layers written.
    // A shared box re-deals its whole set - ascending tails to members in
    // member order, each member's slice on its own layer. A lone multi
    // stores its sorted set, or drops the store when the set is the natural
    // 1..L - and either way drops a legacy block offset under it, which
    // would otherwise come back the moment the store is gone.
    _balanceWriteMove(m) {
        const layers = this.project.layers || [];
        const out = [];
        if (m.members && m.members.length) {
            const sorted = m.to.slice().sort((a, b) => a - b);
            let off = 0;
            for (const mem of m.members) {
                const layer = layers.find(l => l.id === mem.layerId);
                if (!layer) { off += mem.legs; continue; }
                const store = layer.powerSocaPhasePos
                    || (layer.powerSocaPhasePos = {});
                store[mem.soca] = sorted.slice(off, off + mem.legs);
                off += mem.legs;
                out.push(layer);
            }
            return out;
        }
        const layer = layers.find(l => l.id === m.layerId);
        if (!layer) return out;
        const sorted = m.to.slice().sort((a, b) => a - b);
        const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
        if (sorted.every((p, k) => p === k + 1)) delete store[m.soca];
        else store[m.soca] = sorted;
        const offs = layer.powerSocaPhaseOffset;
        if (offs && Object.prototype.hasOwnProperty.call(offs, m.soca)) delete offs[m.soca];
        out.push(layer);
        return out;
    }

    // Write `moves`, read the real loads of every distro, put every layer
    // back exactly as it was. Returns distro id -> real figures after.
    _balanceDryRun(moves) {
        const layers = this.project.layers || [];
        const ids = new Set();
        for (const m of moves) {
            if (m.members && m.members.length) m.members.forEach(x => ids.add(x.layerId));
            else ids.add(m.layerId);
        }
        const fields = ['powerSocaPhasePos', 'powerSocaPhaseOffset'];
        const saved = layers.filter(l => ids.has(l.id)).map(layer => ({
            layer,
            f: fields.map(k => {
                const had = Object.prototype.hasOwnProperty.call(layer, k);
                const ref = layer[k];
                return { k, had, ref,
                         json: ref && typeof ref === 'object' ? JSON.stringify(ref) : null };
            }),
        }));
        const out = new Map();
        try {
            moves.forEach(m => this._balanceWriteMove(m));
            this._circuitTailCache = null;
            for (const L of this.getDistroLoads()) {
                if (L.id && L.legs) out.set(L.id, { imb: L.imbalancePct, busiest: L.legs.worstAmps });
            }
        } finally {
            for (const { layer, f } of saved) {
                for (const { k, had, ref, json } of f) {
                    if (!had) { delete layer[k]; continue; }
                    layer[k] = ref;
                    if (json !== null) {
                        Object.keys(ref).forEach(x => delete ref[x]);
                        Object.assign(ref, JSON.parse(json));
                    }
                }
            }
            this._circuitTailCache = null;
        }
        return out;
    }

    // What Balance offers. Per distro (`distroId`), or every distro when
    // none is named - legs never interact across services, so the show-wide
    // call is each distro solved on its own.
    //
    // The figures are REAL: `before` is getDistroLoads on the drawing as it
    // stands, `after` is getDistroLoads on the proposal, written for a dry
    // run and put back. A distro's moves are offered only when that real
    // result strictly beats the real current one under the lexicographic
    // objective (imbalance, then the busiest leg) with the busiest leg no
    // heavier - so Apply is never worse than leaving it.
    //
    // Nothing is persisted.
    suggestPhaseBalance(distroId) {
        const ids = distroId ? [distroId]
            : [...new Set(this._balanceTargets().map(t => t.distroId))];
        const solved = ids.map(id => this._balanceSolve(id));
        const proposed = solved.map(r => this._balanceMovesOf(r));
        const flat = proposed.flat();
        const afterReal = flat.length ? this._balanceDryRun(flat) : new Map();
        const kept = new Set();
        solved.forEach((r, i) => {
            if (proposed[i].length
                    && this._balanceGains(afterReal.get(r.distroId), r.before)) {
                kept.add(r.distroId);
            }
        });
        const moves = proposed.filter((p, i) => kept.has(solved[i].distroId)).flat();

        // The headline figures. Scoped: that distro's. Show-wide: the worst
        // distro, before and after, the busiest leg likewise.
        this._circuitTailCache = null;
        const loads = this.getDistroLoads()
            .filter(b => b.id && b.legs && (!distroId || b.id === distroId));
        const beforeOf = (b) => ({ imb: b.imbalancePct, busiest: b.legs.worstAmps });
        const afterOf = (b) => (kept.has(b.id) && afterReal.get(b.id)) || beforeOf(b);
        const worst = (f) => loads.reduce((m, b) => ({
            imb: Math.max(m.imb, f(b).imb), busiest: Math.max(m.busiest, f(b).busiest),
        }), { imb: 0, busiest: 0 });
        const before = worst(beforeOf);
        const after = worst(afterOf);
        const targets = solved.flatMap(r => r.targets);
        return {
            before: before.imb, after: after.imb,
            beforeBusiest: before.busiest, afterBusiest: after.busiest,
            searched: solved.reduce((t, r) => t + r.searched, 0),
            total: solved.reduce((t, r) => t + r.total, 0),
            exhaustive: solved.every(r => r.exhaustive),
            blockedByBusiest: solved.some(r => r.blockedByBusiest && !kept.has(r.distroId)),
            targets: targets.map(t => `${t.name} (${t.layerName || t.layer.name}, ${t.legs} circuits)`),
            // Partly-filled multis held where they are because a screen
            // they sit on is locked - the dialog names them.
            locked: solved.flatMap(r => r.locked).map(t => ({
                name: t.name, layerName: t.layerName || t.layer.name,
                layers: [...new Set((t.members ? t.members.map(m => m.layer) : [t.layer])
                    .filter(l => l.locked).map(l => l.name))],
            })),
            moves,
        };
    }

    applyPhaseBalance(moves) {
        const touched = new Set();
        // A locked screen keeps its breakers (the owner's ruling,
        // 2026-10-16): a move that would write one is left out - a shared
        // box's move whole - and the locked screens are named once. The
        // search already holds locked screens fixed, so this only meets a
        // move from somewhere else.
        const byId = (id) => (this.project.layers || []).find(l => l.id === id);
        const lockedMet = new Map();
        for (const m of moves || []) {
            const ids = (m.members && m.members.length)
                ? m.members.map(mem => mem.layerId) : [m.layerId];
            const locked = ids.map(byId).filter(l => l && l.locked);
            if (locked.length) {
                locked.forEach(l => lockedMet.set(l.id, l));
                continue;
            }
            this._balanceWriteMove(m).forEach(l => touched.add(l));
        }
        this._showLockedError([...lockedMet.values()]);
        this._circuitTailCache = null;
        if (touched.size) this.updateLayers([...touched], true, 'Balance Phase Legs');
        return touched.size;
    }

    // Show what the balancer found and let the user accept or decline it.
    // Advisory by design: this moves a multi to a different set of breakers
    // on paper, and somebody still has to plug it in that way.
    //
    // Scoped to one distro when `distroId` is given - the per-distro
    // Balance button's dialog reports that distro's before/after and moves
    // only its multis. With nothing movable it STATES why (full multis,
    // clashed boxes, assignments the plan no longer produces, locked
    // screens) rather than computing silently to a no-op: the reference
    // show read that silence as "balancing won't calculate".
    showBalanceDialog(distroId) {
        const r = this.suggestPhaseBalance(distroId);
        const ID = 'balance-modal';
        document.getElementById(ID)?.remove();
        const esc = (s) => this._esc ? this._esc(s) : s;
        const gain = r.before - r.after;
        const distro = distroId
            ? this.getDistros().find(d => d.id === distroId) : null;
        const plural = (n, one, many) => (n === 1 ? one : many);
        const lockedLines = (r.locked || []).map(l =>
            `${esc(l.name)} (${esc(l.layerName)}) stays where it is — ${esc(l.layers.join(', '))} ${plural(l.layers.length, 'is', 'are')} locked.`);
        const lockedHtml = lockedLines.length
            ? lockedLines.map(l => `<div style="color:#a6b0bb; margin:6px 0 0; padding-left:10px;">· ${l}</div>`).join('')
            : '';
        let noTargets = `<p style="margin:0; color:#a6b0bb;">Every multi on a three-phase distro is full, so the legs are already
               as even as the pattern allows. Imbalance comes from partly-filled
               multis — there are none here.</p>`;
        if (distroId) {
            const b = this._balanceBlockers(distroId);
            const lines = [];
            if (b.full.length) lines.push(
                `${b.full.map(f => esc(f.name)).join(', ')} ${b.full.length === 1 ? 'is' : 'are'} full — with every circuit taken the legs are already as even as they get, there is nothing to choose.`);
            b.crowded.forEach(c => lines.push(
                `${esc(c.name)} (${esc(c.layers)}) has ${c.legs} circuits on ${c.conn ? `${/^(?:[aeiou]|L\d)/i.test(c.conn) ? 'an' : 'a'} ${esc(c.conn)}, which carries ` : 'a connector that carries '}${c.size === 1 ? 'one circuit' : `${c.size} circuits`} — move it to a multi output.`));
            b.clashed.forEach(c => lines.push(
                `${esc(c.name)} (${esc(c.layers)}) is shared ${c.overflow
                    ? `with more circuits than the ${Number.isFinite(c.size) ? c.size : 'tails'} it holds`
                    : 'with a circuit claimed twice'} — resolve the clash first.`));
            b.phantom.forEach(p => lines.push(
                `${esc(p.layers)} assigns ${p.count === 1 ? 'a multi' : p.count + ' multis'} to this distro but ${esc(p.reason)}`));
            lines.push(...lockedLines);
            noTargets = `<p style="margin:0 0 6px; color:#a6b0bb;">Nothing on this distro can move${lines.length ? ':' : ' — no partly-filled multi lands on it.'}</p>`
                + lines.map(l => `<div style="color:#a6b0bb; margin:0 0 4px; padding-left:10px;">· ${l}</div>`).join('');
        } else if (lockedLines.length) {
            noTargets += lockedHtml;
        }
        const n = r.targets.length;
        const multis = `${n} partly-filled multi${n === 1 ? '' : 's'}`;
        const checked = r.exhaustive
            ? `Checked all ${r.searched} arrangement${plural(r.searched, '', 's')} of ${multis}`
            : `Checked ${r.searched} of ${r.total} arrangements of ${multis} — too many to try them all, so this is the best found, not necessarily the best there is`;
        const amps = (a) => `${a.toFixed(1)} A`;
        const body = !r.targets.length
            ? noTargets
            : !r.moves.length
            ? `<p style="margin:0; color:#a6b0bb;">${checked}. ${r.exhaustive ? 'None beats' : 'None found beats'} the current
               ${r.before.toFixed(1)}% imbalance${r.blockedByBusiest
                   ? ' without loading the busiest leg harder than its ' + amps(r.beforeBusiest) + ' today'
                   : ''}. Landing them elsewhere will not help;
               filling the short multis or moving circuits between them would.</p>${lockedHtml}`
            : `<div style="display:flex; align-items:baseline; gap:10px; margin-bottom:4px;">
                 <span style="font-size:22px; color:#e05050;">${r.before.toFixed(1)}%</span>
                 <span style="color:#7d8894;">→</span>
                 <span style="font-size:22px; color:#5fa85f;">${r.after.toFixed(1)}%</span>
                 <span style="color:#8fa0b2; font-size:11px;">worst-leg imbalance · ${gain.toFixed(1)} points better</span>
               </div>
               <div class="balance-busiest" style="color:#8fa0b2; font-size:11px; margin-bottom:14px;">Busiest leg ${amps(r.beforeBusiest)} → ${amps(r.afterBusiest)}</div>
               <div style="font-size:11px; color:#8a949f; margin-bottom:6px;">Re-plug these circuits along the same
               fan — no rewiring, no re-patching:</div>
               ${r.moves.map(m => `
                 <div style="margin-bottom:10px;">
                   <div style="color:#e8eef5; margin-bottom:3px;">${esc(m.name)}
                     <span style="color:#7d8894; font-weight:400;">· ${esc(m.layerName)}</span></div>
                   <table style="width:100%; border-collapse:collapse; font-size:11px;">
                     ${m.to.map((p, k) => p === m.from[k] ? '' : `<tr>
                       <td style="padding:2px 8px; color:#a6b0bb; width:40%;">${esc((m.labels || [])[k] || `circuit ${k + 1}`)}
                         <span style="color:#6d7681;">(${m.amps[k].toFixed(1)} A)</span></td>
                       <td style="padding:2px 8px; color:#a6b0bb;">socket ${m.from[k]} → <strong style="color:#e8eef5;">socket ${p}</strong></td>
                     </tr>`).join('')}
                   </table>
                 </div>`).join('')}
               ${lockedHtml}
               <div style="margin-top:12px; font-size:11px; color:#7d8894;">Balancing picks WHICH sockets of the fan a partly-filled
               multi uses — skipping one lands the remainder on different
               legs. Circuits keep wall order across the chosen sockets,
               so the labels still read in order across the wall.
               ${checked}.</div>`;

        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:540px; max-width:94vw; margin:80px auto; border:1px solid #3a3a3a; overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">BALANCE PHASE LEGS${distro ? ` — ${esc(distro.name).toUpperCase()}` : ''}</h2>
    <button class="btn btn-secondary balance-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; font-size:12px; line-height:1.55;">${body}</div>
  <div style="display:flex; gap:8px; justify-content:flex-end; padding:0 20px 16px;">
    <button class="btn btn-secondary balance-reset" title="Put every multi back on its natural breaker position and number the multis again in screen order">Reset offsets</button>
    <button class="btn btn-secondary balance-close">${r.moves.length ? 'Leave it' : 'Close'}</button>
    ${r.moves.length ? '<button class="btn balance-apply">Apply</button>' : ''}
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelectorAll('.balance-close').forEach(b =>
            b.addEventListener('click', () => el.remove()));
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
        // Balancing renumbers labels (true tails), so refresh EVERY pane
        // that prints them - splitter rows and the label editor included,
        // plus the canvas bubbles - not just the load roll-ups. The server
        // echo would repaint them a round-trip later anyway; doing it here
        // means the left pane and the map agree the moment the dialog
        // closes (same refresh set as _writeSplitterManual).
        const refreshAll = () => {
            this.refreshDistroPanel();
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const resetBtn = el.querySelector('.balance-reset');
        if (resetBtn) resetBtn.addEventListener('click', () => {
            // A scoped dialog resets only its own distro's multis - the
            // other services' arrangements are not this button's to drop.
            this.clearPhaseBalance(distroId);
            el.remove();
            refreshAll();
        });
        const applyBtn = el.querySelector('.balance-apply');
        if (applyBtn) applyBtn.addEventListener('click', () => {
            this.applyPhaseBalance(r.moves);
            el.remove();
            refreshAll();
        });
    }

    // Plain-language explanation of what the phasing schemes mean and why the
    // choice changes the leg loads. Built on demand rather than living in
    // index.html so the copy sits next to the math it describes.
    //
    // The scheme table is GENERATED from powerPhasingSchemes and the leg map
    // itself: names come from the same records the select prints, and the
    // circuit row is read out of _circuitLegs. A user asked what the
    // difference between "line-to-line" and "paired" was because the same
    // scheme was named one way here and another way there; nothing here
    // restates a name or a mapping in prose, so they cannot drift apart again.
    showPhasingHelp() {
        const ID = 'phasing-help-modal';
        document.getElementById(ID)?.remove();
        const schemes = this.powerPhasingSchemes();
        const byId = (id) => schemes.find(s => s.id === id);
        // the six positions of the fan, straight out of the leg map
        const spread = (id) => [1, 2, 3, 4, 5, 6]
            .map(i => this._circuitLegs(i, id).join('')).join(' ');
        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:660px; max-width:94vw; margin:60px auto; border:1px solid #3a3a3a; display:flex; flex-direction:column; max-height:calc(100vh - 120px); overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">HOW MULTIS LAND ON THE PHASE LEGS</h2>
    <button class="btn btn-secondary phasing-help-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; overflow-y:auto; font-size:12px; color:#c3ccd6; line-height:1.6;">

    <p style="margin:0 0 14px;"><strong style="color:#e8eef5;">A distro fed from camlock is three-phase. Every circuit
    coming off the breakout is single-phase</strong> — whether it sits on one
    hot and a neutral, or across two hots with no neutral. Three-phase never
    reaches a panel. The legs only decide <em>which</em> hots each circuit
    sits across, and therefore how the load spreads over the service.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px;">
      <div style="color:#e8eef5; margin-bottom:5px;">Two things vary, and they are independent</div>
      <div style="color:#a6b0bb; margin-bottom:8px;">Every scheme is named for both, coupling first, order second — so
      <em>${byId('paired-ll').name}</em> and <em>${byId('rotating-ll').name}</em>
      are the same coupling dealt differently, not two answers to one question.</div>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Coupling</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Line-to-neutral</strong> is one hot and
          a neutral (X). <strong style="color:#c3ccd6;">Line-to-line</strong> is two hots and no neutral (XY). This is the
          electrical relationship, and it follows the circuit voltage: line-to-neutral
          runs at the service divided by √3 — 120 V off a 208 V service, 230 V off a
          400 V one.</td>
        </tr>
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Order</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Rotating</strong> advances on every
          circuit (X Y Z X Y Z). <strong style="color:#c3ccd6;">Paired</strong> puts two consecutive circuits on the same
          assignment before advancing (X X Y Y Z Z). This is how the distro is wired
          internally, which is why it is a setting here and not something the voltage
          can answer.</td>
        </tr>
      </table>
    </div>

    <div style="background:#3a2626; border-left:3px solid #b34a3a; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px; color:#e0c0ba;">
      <strong style="color:#f5cdc4;">No standard assigns a circuit to a leg.</strong>
      ANSI E1.80, USITT RP-1 and NEC 520.68 all cover the <em>pinout</em> —
      which pin carries which circuit's conductors — and none of them assigns
      a circuit to a leg. No major distro manufacturer publishes a universal
      mapping. Motion Laboratories' own maintenance manual says to "verify
      the pinout of each output, including that the correct phase is on the
      correct pin per the pinout. (The pinout is marked on the panel near the
      output devices.)" <strong style="color:#f5cdc4;">Read the unit.</strong>
    </div>

    <p style="margin:0 0 14px; color:#a6b0bb;">What every source does agree on is the
    <em>balance goal</em>: two circuits per leg line-to-neutral, two circuits
    per leg-pair line-to-line. Only the order varies — and the order is exactly
    what decides where a partly-filled multi dumps its remainder. Each pattern
    below is documented on a real distro or rack, none is a default.</p>

    <table class="phasing-scheme-table" style="width:100%; border-collapse:collapse; margin-bottom:10px;">
      <tr style="border-bottom:1px solid #3a3a3a;">
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Scheme</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Circuits 1–6</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Where it is documented</th>
      </tr>
      ${schemes.map(sc => `
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">${sc.name}<br><span style="color:#7d8894; font-size:11px;">${sc.lineToLine ? 'two hots, no neutral' : 'one hot and a neutral'}</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px;">${spread(sc.id)}</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">${sc.where}</td>
      </tr>`).join('')}
    </table>

    <p style="margin:0 0 16px; color:#a6b0bb;">The two paired line-to-line schemes differ
    only in the order the pairs come round: <em>${byId('paired-ll-alt').pattern}</em>
    follows the cyclic order X → Y → Z → X, the way AB → BC → CA does, and
    <em>${byId('paired-ll').pattern}</em> does not. That is the ordering fact,
    not a ranking — neither is a default, and the only way to know which one a
    given soca uses is to read it.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0;">
      <div style="color:#e8eef5; margin-bottom:5px;">Why your legs are uneven</div>
      <div style="color:#a6b0bb;">Imbalance almost always comes from <strong>partly-filled
      multis</strong>, not from the screens. A full 6-circuit multi balances
      itself under any scheme. A multi that stops at 4 or 5 circuits dumps its
      remainder onto whichever legs come first in the pattern — with paired
      legs that is always X. Fill the multi, move a circuit to another multi,
      or use the rotating pattern if the distro is wired that way.</div>
    </div>

    <div style="margin-top:14px; color:#7d8894; font-size:11px;">
      Per-leg current is a phasor sum, not a straight addition: a line-to-line
      circuit is one load drawing the <em>same</em> current in both its legs, sitting
      ±30° off each leg's line-to-neutral reference. Imbalance is NEMA-style —
      the largest deviation from the average of the three legs.
    </div>
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelector('.phasing-help-close').addEventListener('click', () => el.remove());
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
    }

    // How a distro lands a multi's 6 circuits on its phase legs.
    //
    // This is a property of the DISTRO's internal bus and breaker
    // arrangement. It is NOT the connector pinout: ANSI E1.80-2024 defines
    // 120V Type U and 208V Types C/D/E, but those describe which PIN carries
    // which circuit's conductors - the standard's own table key is only
    // "L = Ungrounded Circuit Conductor" and it never assigns a circuit to
    // L1, L2 or L3. Two distros with identical E1.80 pinouts can still land
    // their circuits on different legs. Read the distro, not the connector.
    //
    // Every pattern below is documented on a real North American distro or
    // rack. There is no national standard for phase rotation - a search of
    // E1.80, USITT RP-1, NEC 520.68, and the published material from every
    // major distro manufacturer turned up nothing that assigns a circuit to
    // a leg. Motion Laboratories' own maintenance manual says to "verify the
    // pinout of each output, including that the correct phase is on the
    // correct pin per the pinout. (The pinout is marked on the panel near the
    // output devices.)" That is the industry position: read the unit.
    //
    // What IS consistent across every source is the balance goal - two
    // circuits per leg line-to-neutral, two circuits per leg-PAIR
    // line-to-line. Only the order varies, and the order is what changes a
    // partly-filled multi.
    //
    // NAMING. A scheme varies along TWO independent axes and the name gives
    // both, coupling first, order second:
    //   coupling  line-to-neutral (one leg, X) or line-to-line (two, XY)
    //   order     rotating (advance every circuit) or paired (two circuits
    //             on one assignment, then advance)
    // Naming only one axis made two orthogonal things look like alternatives
    // - the same scheme read as "paired" in the list and "line-to-line" on
    // the derived entry, and a user asked what the difference was. `name` is
    // therefore COMPUTED from the axes so no caller can spell it its own way.
    //
    // The volts are deliberately not in the name: line-to-neutral is 120V on
    // a 208V service and 230V on a 400V one, so the figure belongs to the
    // SERVICE, not the scheme. It is derived as V / sqrt(3) where it helps.
    powerPhasingSchemes() {
        const named = (s) => ({
            ...s,
            coupling: s.lineToLine ? 'Line-to-line' : 'Line-to-neutral',
            name: `${s.lineToLine ? 'Line-to-line' : 'Line-to-neutral'}, ${s.order} (${s.pattern})`,
        });
        return [
            { id: 'rotating-ln', lineToLine: false, order: 'rotating',
              pattern: 'X Y Z X Y Z',
              where: 'Published phasing sheet for a 36-way house distro. No practitioner source corroborates it, so confirm before relying on it.' },
            { id: 'paired-ln', lineToLine: false, order: 'paired',
              pattern: 'X X Y Y Z Z',
              where: 'What several practitioners report as usual.' },
            { id: 'paired-ll', lineToLine: true, order: 'paired',
              pattern: 'XY ZX YZ',
              where: 'Two independent rental houses publish this exact map.' },
            { id: 'paired-ll-alt', lineToLine: true, order: 'paired',
              pattern: 'XY YZ ZX',
              where: 'Same grouping, other pair order — published as the Strand LightRack module pinout.' },
            { id: 'rotating-ll', lineToLine: true, order: 'rotating',
              pattern: 'XY XZ YZ',
              where: 'Reported as a competing family. Spreads a partly-filled multi best.' }
        ].map(named);
    }

    // Default scheme for a distro: line-to-line when the circuit voltage
    // matches the service voltage (208V circuits on a 208V wye), otherwise
    // line-to-neutral.
    // 1.5: on a distro with a SYSTEM, "matches" is which of the system's
    // figures the circuit voltage is, by nominal name (_distroLineToLine)
    // - a 230V circuit on 230/400 is line-to-neutral (bug fix 1). An old
    // record with no system keeps the old test, within a volt of the
    // service voltage. An EU distro can also be wired whole multi on one
    // leg (_distroExtraSchemes).
    powerPhasingFor(distro, circuitVoltage) {
        const schemes = this.powerPhasingSchemes();
        const extra = distro && distro.system && typeof this._distroExtraSchemes === 'function'
            ? this._distroExtraSchemes(distro) : [];
        const explicit = distro && distro.phasing
            && (schemes.find(s => s.id === distro.phasing)
                || extra.find(s => s.id === distro.phasing));
        if (explicit) return explicit;
        const ll = !!distro && circuitVoltage > 0 && this._distroLineToLine(distro, circuitVoltage);
        return schemes.find(s => s.id === (ll ? 'paired-ll' : 'rotating-ln'));
    }

    // The circuit voltage this distro actually sees: whatever the screens
    // feeding it run at, walked in the SAME order getDistroLoads walks them so
    // the select and the leg maths can never name two different schemes.
    //
    // A distro with nothing assigned yet has no evidence to read, so it is
    // taken at its word - a service whose circuits sit at the service voltage,
    // which is what choosing 208V means. It is a default like any other here
    // and the moment a multi lands on the distro the real circuit voltage
    // replaces it.
    distroCircuitVoltage(distro) {
        if (!distro || !this.project) return 0;
        let seen = null;
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            if (!plan.some(s => assign[s.soca] === distro.id)) continue;
            seen = parseFloat(layer.powerVoltage) || 0;
        }
        return seen === null ? (Number(distro.voltage) || 0) : seen;
    }

    // What the phasing control has to say out loud: the scheme in force, and
    // whether it is DERIVED from the voltage or was picked by hand.
    //
    // Two distros can run the same scheme, one because somebody read the box
    // and one because nobody has - and only the first survives a voltage
    // change. Without this distinction on screen "a manual choice overrides
    // the default" is a rule the user cannot see operating.
    distroPhasingState(distro) {
        if (distro && typeof this._ensureDistroSystem === 'function') {
            this._ensureDistroSystem(distro);
        }
        const schemes = this.powerPhasingSchemes();
        const extra = distro && typeof this._distroExtraSchemes === 'function'
            ? this._distroExtraSchemes(distro) : [];
        const chosen = distro && distro.phasing
            && (schemes.find(s => s.id === distro.phasing)
                || extra.find(s => s.id === distro.phasing));
        const circuitV = this.distroCircuitVoltage(distro);
        // Ask for the derived answer explicitly rather than reading it off
        // powerPhasingFor(distro, ...), which would hand back the explicit
        // choice and hide what the voltage would have chosen.
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, system: distro && distro.system,
              phasing: null }, circuitV);
        return {
            explicit: !!chosen,
            derived,
            circuitVoltage: circuitV,
            scheme: chosen || derived
        };
    }

    // Order a leg pair cyclically (X>Y>Z>X). The first leg of the cyclic pair
    // carries the line-to-line current at +30 deg relative to its own
    // line-to-neutral voltage, the second at -30 deg.
    _cyclicPair(a, b) {
        const C = ['X', 'Y', 'Z'];
        const ia = C.indexOf(a), ib = C.indexOf(b);
        return ib === (ia + 1) % 3 ? [a, b] : [b, a];
    }

    _addLegPhasor(store, leg, amps, degrees) {
        const r = degrees * Math.PI / 180;
        store[leg].re += amps * Math.cos(r);
        store[leg].im += amps * Math.sin(r);
    }

    // `offset` slides the used circuits along the multi's own six positions:
    // a multi with 4 circuits in use can occupy positions 1-4, 2-5 or 3-6.
    // The load does not move to another multi - it is the same 6-way fan,
    // just landed on different legs of it.
    //
    // The offset MUST be bounded by socaPhaseOffsetMax so the last circuit
    // stays within position 6. The modulo below is only a guard; if it ever
    // actually wraps, the offset was invalid and the answer is nonsense -
    // a 5-circuit multi at offset 3 would want positions 4..8, and wrapping
    // 7 and 8 back to 1 and 2 silently invents a plan nobody can patch.
    //
    // `boxSize` is the fan the positions index into. A 3-tail L21-30 box
    // has no order axis to choose - one circuit per assignment - so its
    // line-to-line map is the fixed cyclic pair walk (XY YZ ZX, the box's
    // own internal wiring) whatever paired/rotating scheme the distro
    // runs its socas on, and its line-to-neutral map is one leg per tail.
    _circuitLegs(legIndex, schemeId, offset = 0, boxSize = 6) {
        const size = Number(boxSize) === 3 ? 3 : 6;
        const i = ((legIndex - 1 + (Number(offset) || 0)) % size + size) % size;
        if (size === 3) {
            const ln = schemeId === 'paired-ln' || schemeId === 'rotating-ln';
            if (ln) return [['X'], ['Y'], ['Z']][i];
            return [['X','Y'], ['Y','Z'], ['Z','X']][i];
        }
        if (schemeId === 'paired-ll') return [['X','Y'], ['X','Y'], ['Z','X'], ['Z','X'], ['Y','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ll-alt') return [['X','Y'], ['X','Y'], ['Y','Z'], ['Y','Z'], ['Z','X'], ['Z','X']][i];
        if (schemeId === 'rotating-ll') return [['X','Y'], ['X','Z'], ['Y','Z'], ['X','Y'], ['X','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ln') return [['X'], ['X'], ['Y'], ['Y'], ['Z'], ['Z']][i];
        return [['X', 'Y', 'Z'][i % 3]];
    }

    // How far a multi's used circuits can slide as a BLOCK before the last
    // one runs off the end of the fan. Kept for the legacy block model;
    // socaCircuitPositions supersedes it.
    socaPhaseOffsetMax(legsUsed, boxSize = 6) {
        return Math.max(0, (Number(boxSize) || 6) - (Number(legsUsed) || 6));
    }

    // Which position on the multi's 6-way fan each used circuit occupies.
    //
    // WALL-ORDER RULE (user decision, fixed): balancing - or anything else -
    // only ever chooses WHICH tails of the fan are in use (the SET). The
    // assignment of circuits to the chosen tails is always wall order ->
    // ascending tail number, so a wall using tails {1,2,3,5,6} reads
    // S1-1, S1-2, S1-3, S1-5, S1-6 left to right, never a permutation.
    // Stored arrays are therefore sorted ascending ON READ: projects that
    // still carry a permutation from the old balancer ([6,2,5,1,3]) or a
    // rotation ([5,6,1,2,3]) display wall-ordered immediately, keeping the
    // same occupied tails, without a re-balance.
    //
    // Returns a position (1-6) per used circuit, ascending in circuit
    // (wall) order. Falls back to the legacy block offset - which selects
    // the occupied tails off+1..off+L, already ascending - then to the
    // natural 1..L.
    socaCircuitPositions(layer, socaNum, legsUsed) {
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const saved = ((layer && layer.powerSocaPhasePos) || {})[socaNum];
        if (Array.isArray(saved) && saved.length === L
            && saved.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(saved).size === L) {
            return saved.slice().sort((a, b) => a - b);
        }
        // A multi PINNED to a number can be sharing one physical box with a
        // multi on another screen, and then its unstored default is not the
        // natural 1..L - it is the box's NEXT FREE tails, dealt in
        // _resolveSharedSocas with every member on the table. Read the dealt
        // answer rather than re-deriving it here; a pin the naming pass has
        // not resolved (mid-build, an orphan screen) falls through to the
        // legacy default below.
        if (layer && (layer.powerSocaDistro || {})[socaNum]) {
            const pin = parseInt((layer.powerSocaNumber || {})[socaNum], 10);
            if (Number.isFinite(pin) && pin >= 1) {
                const rec = this._powerNaming(layer).socas.get(Number(socaNum));
                if (rec && Array.isArray(rec.positions)
                        && rec.positions.length === (Number(legsUsed) || 0)) {
                    return rec.positions.slice();
                }
            }
        }
        const off = this.socaPhaseOffset(layer, socaNum, L);
        return Array.from({ length: L }, (_, i) => i + 1 + off);
    }

    // The scheme ONE CIRCUIT actually lands with: coupling is physics -
    // a 110V Edison circuit needs a hot and a neutral, a 208V circuit two
    // hots - so the circuit's own voltage decides line-to-neutral vs
    // line-to-line, and only the dealing ORDER is the distro's wiring to
    // declare. An explicit distro scheme therefore applies to a circuit
    // only when its coupling matches what that circuit's voltage derives;
    // otherwise the voltage's own derived default takes over for that
    // circuit alone. This is what lets a 110V multi and a 208V multi share
    // one distro without the explicit choice pairing up Edison circuits:
    // the 110V circuits ride one leg each, the 208V circuits their pairs
    // (user ruling, 2026-08-28). The gear select still shows a mismatched
    // explicit choice and says so - paperwork is displayed, never obeyed
    // into an impossible hookup.
    _circuitSchemeFor(distro, circuitVoltage) {
        if (distro && typeof this._ensureDistroSystem === 'function') {
            this._ensureDistroSystem(distro);
        }
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, system: distro && distro.system,
              phasing: null },
            circuitVoltage);
        const chosen = this.powerPhasingFor(distro, circuitVoltage);
        return chosen.lineToLine === derived.lineToLine ? chosen : derived;
    }

    // Positions must be a set of distinct 1-6 values, one per used circuit -
    // two circuits cannot share a tail. Only the SET matters (wall-order
    // rule): stored sorted ascending, and a permutation of 1..L is the
    // natural arrangement - but only on a multi that owns its whole box.
    // On a SHARED box tails 1..L are one specific claim among six, not a
    // default: dropping the store there hands the member back to the deal,
    // and the deal answers by layer order - which is exactly how "put me
    // back on 1-4" once evaporated and let the joiner keep tail 1.
    setSocaCircuitPositions(layer, socaNum, positions, legsUsed) {
        if (!layer) return false;
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const ok = Array.isArray(positions) && positions.length === L
            && positions.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(positions).size === L;
        if (!ok) return false;
        const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
        const sorted = positions.slice().sort((a, b) => a - b);
        const natural = sorted.every((p, i) => p === i + 1);
        if (natural && !this.getSocaShare(layer, socaNum)) {
            delete store[socaNum];
        } else {
            store[socaNum] = sorted;
        }
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Move Circuits');
        return true;
    }

    // Which position within the multi the first used circuit sits on (0-based).
    // Clamped on read as well as on write, so a stored value that is no longer
    // valid - the screen shed a circuit since it was set - degrades to the
    // nearest legal position instead of wrapping off the end.
    socaPhaseOffset(layer, socaNum, legsUsed) {
        const map = (layer && layer.powerSocaPhaseOffset) || {};
        const raw = Math.max(0, Number(map[socaNum]) || 0);
        return Math.min(raw,
            this.socaPhaseOffsetMax(legsUsed, this.socaBoxSize(layer)));
    }

    setSocaPhaseOffset(layer, socaNum, offset, legsUsed) {
        if (!layer) return;
        // Always leave an object behind, never delete the property itself:
        // an absent key is simply missing from the update payload and the
        // server keeps whatever it had, so "clear this" would silently not
        // clear. An empty object overwrites.
        const map = layer.powerSocaPhaseOffset || (layer.powerSocaPhaseOffset = {});
        const v = Math.min(Math.max(0, Number(offset) || 0),
                           this.socaPhaseOffsetMax(legsUsed,
                               this.socaBoxSize(layer)));
        if (v) map[socaNum] = v; else delete map[socaNum];
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Set Breaker Offset');
    }

    // Drop every multi back to its natural breaker position - show-wide, or
    // only the multis assigned to one distro when `distroId` is given (the
    // scoped balance dialog's reset) - and renumber those multis in screen
    // order, the only thing that moves a multi number once it has one.
    //
    // A locked screen stays exactly as it prints. Its own stores are held
    // (_holdLockedLayers), its numbers are held (_releaseMultiNumbers), and
    // on a SHARED box its tails are held too: dropping the other members'
    // stores would re-deal the box around it and move its labels, so those
    // members are dealt, in member order, into the lowest tails the locked
    // members do not hold. Every locked screen the reset would otherwise
    // have changed is named.
    clearPhaseBalance(distroId) {
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        const lockedBoxes = this._lockedSharedBoxes(screens, distroId);
        // Every screen's stores as they were, for a multi the reset has to
        // leave where it is (_resetAroundPairedRows).
        const preReset = new Map(screens.map(l => [l.id, {
            pos: JSON.stringify(l.powerSocaPhasePos || {}),
            off: JSON.stringify(l.powerSocaPhaseOffset || {}),
        }]));
        const hold = this._holdLockedLayers(screens);
        if (!distroId) {
            screens.forEach(l => { l.powerSocaPhaseOffset = {}; l.powerSocaPhasePos = {}; });
        } else {
            screens.forEach(l => {
                const assign = l.powerSocaDistro || {};
                for (const store of [l.powerSocaPhaseOffset, l.powerSocaPhasePos]) {
                    if (!store) continue;
                    for (const k of Object.keys(store)) {
                        if (assign[k] === distroId) delete store[k];
                    }
                }
            });
        }
        const lockedHit = new Map(hold.release().map(l => [l.id, l]));
        // The reset is also the one gesture that lets the multi numbers move
        // (ruling 2026-10-16): the held numbers on this distro are cleared
        // and its multis deal again in screen order, gaps closed. A locked
        // screen keeps the numbers it prints (_releaseMultiNumbers).
        if (typeof this._releaseMultiNumbers === 'function') {
            this._releaseMultiNumbers(distroId || null);
        }
        this._circuitTailCache = null;
        this._holdLockedBoxTails(lockedBoxes).forEach(l => lockedHit.set(l.id, l));
        this._showLockedError([...lockedHit.values()]);
        this._circuitTailCache = null;
        this._showPairedResetError(this._resetAroundPairedRows(screens, distroId, preReset));
        this._circuitTailCache = null;
        // Locked screens are not written: nothing on them changed.
        const writable = screens.filter(l => !l.locked);
        if (writable.length) this.updateLayers(writable, true, 'Reset Phase Offsets');
        return screens.length;
    }

    // After a reset re-dealt the multis: on a distro whose face pairs two
    // rows (a Harting carrying the same circuits as a Socapex), no circuit
    // may end up patched through both connectors - Balance never offers
    // that, and neither may Reset. Walked in screen order with the locked
    // screens' circuits held first: a multi whose natural tails land on a
    // circuit something before it already holds is dealt, wall order, into
    // the lowest tails of its connector whose circuits are free (a shared
    // box as one unit, its members in member order). One that cannot fit
    // is left where it was before the reset and returned, to be named.
    _resetAroundPairedRows(screens, distroId, preReset) {
        const named = [];
        for (const d of this.getDistros()) {
            if (distroId && d.id !== distroId) continue;
            const face = typeof this.distroFace === 'function' ? this.distroFace(d) : null;
            if (!face || !face.boxes.some(b => b.paired)) continue;
            const keyOf = (s, tail) => {
                const box = this.faceBox(d, s.number);
                return box ? this._facePhysical(face, box, tail).key : `${s.number}:${tail}`;
            };
            // the units on this distro, screen order: a lone multi, or a
            // shared box once at its first member
            const units = [];
            const seen = new Set();
            for (const layer of screens) {
                const assign = layer.powerSocaDistro || {};
                for (const s of this.getSocaPlan(layer)) {
                    if (assign[s.soca] !== d.id) continue;
                    const share = this.getSocaShare(layer, s.soca);
                    if (!share) {
                        units.push({ members: [{ layer, soca: s.soca, legs: s.legs.length }],
                                     number: s.number, s, shared: false,
                                     locked: !!layer.locked });
                        continue;
                    }
                    if (seen.has(share.key)) continue;
                    seen.add(share.key);
                    const members = share.members.map(m => ({
                        layer: screens.find(l => l.id === m.layerId), soca: m.soca, legs: m.legs,
                    }));
                    if (members.some(m => !m.layer)) continue;
                    units.push({ members, number: s.number, s, shared: true,
                                 locked: members.some(m => !!m.layer.locked) });
                }
            }
            const tailsOf = (u) => {
                this._circuitTailCache = null;
                return u.members.flatMap(m => this.socaCircuitPositions(m.layer, m.soca, m.legs));
            };
            const used = new Set();
            const take = (u, tails) => tails.forEach(t => used.add(keyOf(u.s, t)));
            units.filter(u => u.locked).forEach(u => take(u, tailsOf(u)));
            for (const u of units) {
                if (u.locked) continue;
                const now = tailsOf(u);
                if (now.every(t => !used.has(keyOf(u.s, t)))) { take(u, now); continue; }
                const fbox = this.faceBox(d, u.number);
                const size = Math.min(...u.members.map(m => this.socaBoxSize(m.layer)),
                                      fbox ? fbox.size : Infinity);
                const legs = u.members.reduce((t, m) => t + m.legs, 0);
                const free = [];
                for (let t = 1; t <= size; t++) if (!used.has(keyOf(u.s, t))) free.push(t);
                if (free.length >= legs) {
                    let off = 0;
                    for (const m of u.members) {
                        const store = m.layer.powerSocaPhasePos || (m.layer.powerSocaPhasePos = {});
                        store[m.soca] = free.slice(off, off + m.legs);
                        off += m.legs;
                        const offs = m.layer.powerSocaPhaseOffset;
                        if (offs) delete offs[m.soca];
                    }
                    take(u, free.slice(0, legs));
                    continue;
                }
                // No room: back where it was before the reset.
                for (const m of u.members) {
                    const was = preReset.get(m.layer.id);
                    if (!was) continue;
                    for (const [k, json] of [['powerSocaPhasePos', was.pos], ['powerSocaPhaseOffset', was.off]]) {
                        const old = JSON.parse(json);
                        const store = m.layer[k] || (m.layer[k] = {});
                        if (Object.prototype.hasOwnProperty.call(old, m.soca)) store[m.soca] = old[m.soca];
                        else delete store[m.soca];
                    }
                    named.push(m.layer);
                }
                take(u, tailsOf(u));
            }
        }
        this._circuitTailCache = null;
        return named;
    }

    // Name the screens a reset left where they were because their natural
    // tails would have patched a circuit through two paired connectors.
    _showPairedResetError(layers) {
        const names = [...new Set((layers || []).filter(Boolean)
            .map(l => l.name || `Screen ${l.id}`))];
        if (!names.length || typeof this._toast !== 'function') return;
        const list = names.length === 1 ? names[0]
            : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
        this._toast(`${list} ${names.length === 1 ? 'stays' : 'stay'} where `
            + `${names.length === 1 ? 'it was' : 'they were'} - the reset would have patched a circuit `
            + 'through two paired connectors.', true, 5000);
    }

    // The shared boxes (on `distroId`, or any distro) with a locked member,
    // as they print now: [{ members: [{ layer, soca, legs, tails, locked,
    // store }] }] in member order. `store` is the member's stored tails as
    // they were, to put back if the box cannot be held.
    _lockedSharedBoxes(screens, distroId) {
        const out = [];
        const seen = new Set();
        for (const layer of screens) {
            const assign = layer.powerSocaDistro || {};
            for (const idx of Object.keys(assign)) {
                if (!assign[idx] || (distroId && assign[idx] !== distroId)) continue;
                const share = this.getSocaShare(layer, idx);
                if (!share || seen.has(share.key)) continue;
                seen.add(share.key);
                const members = share.members.map(m => {
                    const ml = screens.find(l => l.id === m.layerId);
                    if (!ml) return null;
                    const saved = (ml.powerSocaPhasePos || {})[m.soca];
                    return { layer: ml, soca: m.soca, legs: m.legs,
                             tails: m.tails.slice(), locked: !!ml.locked,
                             store: Array.isArray(saved) ? saved.slice() : null };
                });
                if (members.some(m => !m)) continue;
                if (members.some(m => m.locked)) out.push({ members });
            }
        }
        return out;
    }

    // After a reset dropped the stores: where a locked member's tails moved,
    // deal the box's unlocked members into the lowest tails the locked
    // members held, so the locked tails come back exactly. Returns the
    // locked screens that needed it. Should even that not bring them back,
    // the unlocked members get their pre-reset stores again - the box is
    // left alone - and the locked screens are still named.
    _holdLockedBoxTails(boxes) {
        const hit = [];
        const tailsNow = (m) => {
            const rec = this._powerNaming(m.layer).socas.get(Number(m.soca));
            return rec && Array.isArray(rec.positions) ? rec.positions : [];
        };
        const same = (a, b) => a.length === b.length && a.every((p, i) => p === b[i]);
        for (const box of boxes) {
            const locked = box.members.filter(m => m.locked);
            this._circuitTailCache = null;
            if (locked.every(m => same(tailsNow(m), m.tails))) continue;
            const held = new Set(locked.flatMap(m => m.tails));
            let t = 1;
            for (const m of box.members) {
                if (m.locked) continue;
                const pos = [];
                while (pos.length < m.legs) {
                    if (!held.has(t)) pos.push(t);
                    t += 1;
                }
                const store = m.layer.powerSocaPhasePos || (m.layer.powerSocaPhasePos = {});
                store[m.soca] = pos;
            }
            this._circuitTailCache = null;
            if (!locked.every(m => same(tailsNow(m), m.tails))) {
                for (const m of box.members) {
                    if (m.locked) continue;
                    const store = m.layer.powerSocaPhasePos || (m.layer.powerSocaPhasePos = {});
                    if (m.store) store[m.soca] = m.store.slice();
                    else delete store[m.soca];
                }
                this._circuitTailCache = null;
            }
            locked.forEach(m => hit.push(m.layer));
        }
        return hit;
    }
}

for (const k of Object.getOwnPropertyNames(_PhaseBalance.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PhaseBalance.prototype, k));
    }
}
