// app-box-power: POWERING A BREAKOUT BOX (owner rulings, 2026-11-18) - a
// CVT or XD box fed from the walls' power circuits, and the XD / XD-T
// daisy chained box to box through their TRUE1 thru.
//
// THE RULINGS, in the owner's terms:
//   * A box is powered from one of, picked per box: (a) the START of a
//     circuit - the circuit goes to the box first, then on to its panels;
//     (b) the END of a circuit - the last panel's power out jumps to the
//     box; (c) an OPEN circuit on a distro - the box gets that circuit or
//     output by itself; (d) a spare leg on a fan-out (2fer / 3fer): the box
//     rides a shared circuit's splitter.
//   * "a right click and add on power page": right-click a circuit's first
//     or last cabinet (the circuit's tag sits on its first), a free circuit
//     or output chip in the Power tray, or a shared circuit, and pick a box.
//     Removing it is a right-click too. Every gesture is one undo step and
//     reaches the other pages like any other power edit. A locked screen
//     refuses any change with the locked-screen dialog.
//   * DAISY CHAIN: only boxes with a power thru, the original XD and the
//     XD-T (TRUE1 in and thru). A powered one chains to another. Each link
//     is a TRUE1 jumper with a length. Brompton rates the thru "5 units,
//     2 A max": past 5 boxes in one chain, or past 2 A through the first
//     box's thru, is WARNED in gold, never refused.
//   * WATTS: each box adds its published figure to the circuit it rides
//     (catalog `power`, processor_catalog.box_power_watts is the server's
//     twin): its circuit's amps, the distro legs, the neutral at the
//     circuit's LED supply harmonics and every total. A box with no figure
//     adds nothing and is named where a figure is missing.
//   * CABLE follows the box's inlet (the catalog's `cables`), its typed
//     length written from the show's cable stock like a circuit cable, and
//     it goes on the pull sheet. A chain link is a TRUE1 jumper.
//   * A box removed, or moved to another card, takes its feed with it (the
//     record names the card it was powered on). Copies never carry feeds.
//
// THE MODEL. `project.boxPower = { [boxId]: rec }`, persisted on POST
// /api/project like the distros:
//   rec = { cardId, at, cable?, ft? }
//   at  = { kind: 'start' | 'end' | 'fanout', layerId, circuit }
//       | { kind: 'distro', distroId, number, tail }
//       | { kind: 'chain', from: <boxId upstream> }
// A record whose box is gone, whose card changed, whose screen or distro is
// gone, or whose chain is broken, reads as no feed at all (and is dropped
// the next time a box is removed or the store is written).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The cables a box's one feed can take, by id, as every surface says them.
// NovaStar never names the powerCON type, so it is plain "powerCON".
export const BOX_POWER_CABLES = {
    true1: 'TRUE1',
    powercon: 'powerCON',
    'true1-iec': 'TRUE1 → IEC',
    'edison-iec': 'Edison → IEC',
};
// Brompton's thru rating, the owner's pick of its two figures.
export const BOX_CHAIN_MAX_BOXES = 5;
export const BOX_CHAIN_MAX_AMPS = 2;

const CIRCUIT_KINDS = ['start', 'end', 'fanout'];

class _BoxPower {

    // ---- the catalog --------------------------------------------------------

    // The catalog `power` block of a box (its deviceId), or null: a box
    // with none is never offered.
    boxPowerSpec(box) {
        const id = box && (box.deviceId || box.id);
        if (!id) return null;
        const devices = (this._processorCatalog && this._processorCatalog.devices) || [];
        const dev = devices.find(d => d.id === (box.deviceId || id));
        const p = dev && dev.power;
        return p && typeof p === 'object' ? p : null;
    }

    // What a box of `spec` draws at `volts`, in watts, or null with no
    // figure. The original XD publishes amps only (0.4 A at 100 V, 0.2 A at
    // 240 V): the owner ruled "use whatever the voltage works it out to
    // be" - amps on the straight line between the two points at the
    // circuit's voltage, held to the end figure outside 100-240 V, and
    // watts = volts x amps: 110 V 42.4 W, 120 V 44.6 W, 208 V 51.1 W,
    // 230 V 49.3 W, 240 V 48.0 W.
    boxPowerWattsAt(spec, volts) {
        if (!spec) return null;
        const w = Number(spec.watts);
        if (Number.isFinite(w) && w > 0) return w;
        const pts = Array.isArray(spec.ampsAt) ? spec.ampsAt : null;
        const v = Number(volts);
        if (!pts || pts.length !== 2 || !(v > 0)) return null;
        const [[v1, a1], [v2, a2]] = pts.map(p => [Number(p[0]), Number(p[1])])
            .sort((a, b) => a[0] - b[0]);
        const at = Math.min(Math.max(v, v1), v2);
        return v * (a1 + (a2 - a1) * (at - v1) / (v2 - v1));
    }

    // Whether a box has the TRUE1 thru a daisy chain needs (XD, XD-T).
    boxPowerHasThru(box) {
        const s = this.boxPowerSpec(box);
        return !!(s && s.thru === 'true1');
    }

    // The box as every power surface names it: "XD SR A".
    boxPowerTitle(box) {
        if (!box) return 'a breakout box';
        return typeof this.pullBoxTitle === 'function'
            ? this.pullBoxTitle(box) : (box.displayTitle || box.name || box.deviceName || 'a breakout box');
    }

    // Every real box in the tree, in tray order: [{ box, card, proc }]. A
    // card cabled on links of its own (a QD-S) is not a box here.
    boxPowerBoxes() {
        const all = typeof this._fiberAllBoxes === 'function' ? this._fiberAllBoxes() : [];
        return all.filter(b => b.box !== b.card);
    }

    // The boxes a feed can be given: those whose catalog lists power.
    boxPowerOffered() {
        return this.boxPowerBoxes().filter(b => this.boxPowerSpec(b.box));
    }

    // ---- the store ------------------------------------------------------------

    _boxPowerStore() {
        const s = this.project && this.project.boxPower;
        return s && typeof s === 'object' ? s : {};
    }

    // The store's records that stand, memoized on the store and the tree:
    // Map boxId -> { box, card, proc, rec, at }. Every reader goes through
    // it, so a record left behind by a removed box or a moved card reads as
    // no feed anywhere.
    _boxPowerLive() {
        const store = this._boxPowerStore();
        const keys = Object.keys(store);
        if (!keys.length) return new Map();
        const layers = (this.project && this.project.layers) || [];
        const distros = typeof this.getDistros === 'function' ? this.getDistros() : [];
        // the distros by id: an id a removed distro leaves can come back on
        // a new one, and a record must not ride it
        const sig = JSON.stringify(store) + '|' + layers.map(l => l.id).join(',')
            + '|' + distros.map(d => d.id).join(',');
        const memo = this._boxPowerMemo;
        if (memo && memo.sig === sig && memo.tree === this._processorsResolved
                && memo.layers === layers && memo.catalog === this._processorCatalog) {
            return memo.live;
        }
        const boxes = new Map(this.boxPowerBoxes().map(b => [b.box.id, b]));
        const raw = new Map();
        for (const id of keys) {
            const rec = store[id];
            const hit = boxes.get(id);
            if (!rec || typeof rec !== 'object' || !hit || !rec.at) continue;
            if (rec.cardId != null && String(rec.cardId) !== String(hit.card.id)) continue;
            if (!this.boxPowerSpec(hit.box)) continue;
            const at = rec.at;
            if (CIRCUIT_KINDS.includes(at.kind)) {
                if (!layers.some(l => String(l.id) === String(at.layerId))) continue;
            } else if (at.kind === 'distro') {
                if (!distros.some(d => String(d.id) === String(at.distroId))) continue;
            } else if (at.kind !== 'chain') continue;
            raw.set(id, { ...hit, rec, at });
        }
        // A chain stands while its links lead up to a fed head through
        // boxes with a thru, never round in a loop.
        const live = new Map();
        for (const [id, e] of raw) {
            let cur = e;
            const seen = new Set([id]);
            let ok = true;
            while (cur.at.kind === 'chain') {
                const up = raw.get(cur.at.from);
                if (!up || seen.has(cur.at.from) || !this.boxPowerHasThru(up.box)
                        || !this.boxPowerHasThru(cur.box)) { ok = false; break; }
                seen.add(cur.at.from);
                cur = up;
            }
            if (ok) live.set(id, e);
        }
        this._boxPowerMemo = { sig, tree: this._processorsResolved, layers,
                               catalog: this._processorCatalog, live };
        return live;
    }

    // Whether the spot a head record names is there NOW: a screen's
    // circuit of that number (a repack can take it away - then the box has
    // no feed anywhere until it is powered again; following its panel is
    // the owner's question), or an output and circuit the distro has.
    _boxPowerSpotStands(at) {
        if (CIRCUIT_KINDS.includes(at.kind)) {
            const layer = ((this.project && this.project.layers) || [])
                .find(l => String(l.id) === String(at.layerId));
            return !!layer && this.screenCircuits(layer).some(c => Number(c.num) === Number(at.circuit));
        }
        if (at.kind === 'distro') {
            const d = (typeof this.getDistros === 'function' ? this.getDistros() : [])
                .find(x => String(x.id) === String(at.distroId));
            if (!d) return false;
            const n = Number(at.number), t = Number(at.tail);
            if (!(n >= 1) || !(t >= 1)) return false;
            if (typeof this.distroFace === 'function' && this.distroFace(d)) {
                const fb = this.faceBox(d, n);
                return !!fb && t <= (Number(fb.size) || 1);
            }
            return t <= 6;
        }
        return true;
    }

    // The records that stand AND whose feed is there now (live, less every
    // head whose circuit or output is gone, and the chains off them).
    // Every reader of a feed reads this; held for the burst it is read in
    // (dropped on the next microtask and by every box-power edit), since a
    // repack moves circuits without touching the store.
    _boxPowerStanding() {
        const live = this._boxPowerLive();
        if (!live.size) return live;
        const memo = this._boxPowerStandMemo;
        if (memo && memo.live === live) return memo.map;
        const ok = new Map();
        const stands = (id, seen = new Set()) => {
            if (ok.has(id)) return ok.get(id);
            const e = live.get(id);
            if (!e || seen.has(id)) return false;
            seen.add(id);
            const yes = e.at.kind === 'chain' ? stands(e.at.from, seen) : this._boxPowerSpotStands(e.at);
            ok.set(id, yes);
            return yes;
        };
        const map = new Map();
        for (const [id, e] of live) if (stands(id)) map.set(id, e);
        this._boxPowerStandMemo = { live, map };
        Promise.resolve().then(() => { this._boxPowerStandMemo = null; });
        return map;
    }

    // One box's standing record, or null.
    boxPowerOf(boxId) {
        return this._boxPowerStanding().get(boxId) || null;
    }

    // The box chained straight after `boxId` in `map` (standing by
    // default), or null (one link out).
    boxPowerChild(boxId, map = null) {
        for (const e of (map || this._boxPowerStanding()).values()) {
            if (e.at.kind === 'chain' && e.at.from === boxId) return e;
        }
        return null;
    }

    // The head a box draws through: its own record, or the first record up
    // its chain that is not a link. Null for an unpowered box.
    boxPowerHead(boxId) {
        const live = this._boxPowerStanding();
        let cur = live.get(boxId);
        while (cur && cur.at.kind === 'chain') cur = live.get(cur.at.from);
        return cur || null;
    }

    // The boxes up the chain from `boxId`, nearest first (itself excluded).
    _boxPowerUpstream(boxId) {
        const live = this._boxPowerStanding();
        const out = [];
        let cur = live.get(boxId);
        while (cur && cur.at.kind === 'chain') {
            cur = live.get(cur.at.from);
            if (cur) out.push(cur);
        }
        return out;
    }

    // A head's whole chain, head first: [entry, ...], read off `map`
    // (standing by default).
    boxPowerChain(headId, map = null) {
        const m = map || this._boxPowerStanding();
        const head = m.get(headId);
        if (!head) return [];
        const out = [head];
        const seen = new Set([headId]);
        let next = this.boxPowerChild(headId, m);
        while (next && !seen.has(next.box.id)) {
            out.push(next);
            seen.add(next.box.id);
            next = this.boxPowerChild(next.box.id, m);
        }
        return out;
    }

    // Every fed head with its chain and where it is fed:
    //   [{ head, chain, at, layer|null, d|null, volts }]
    boxPowerPlacements() {
        const out = [];
        const layers = (this.project && this.project.layers) || [];
        const distros = typeof this.getDistros === 'function' ? this.getDistros() : [];
        for (const e of this._boxPowerStanding().values()) {
            if (e.at.kind === 'chain') continue;
            const at = e.at;
            const layer = CIRCUIT_KINDS.includes(at.kind)
                ? layers.find(l => String(l.id) === String(at.layerId)) || null : null;
            const d = at.kind === 'distro'
                ? distros.find(x => String(x.id) === String(at.distroId)) || null : null;
            out.push({ head: e, chain: this.boxPowerChain(e.box.id), at, layer, d,
                       volts: layer ? this.boxPowerCircuitVolts(layer, at.circuit)
                           : this.boxPowerDistroVolts(d, at.number) });
        }
        return out;
    }

    // The screen a distro-fed box is drawn beside: the first screen its
    // ports feed (the port map's occupants), or null.
    boxPowerHomeLayerId(box) {
        const hit = this.boxPowerBoxes().find(b => b.box.id === (box && box.id));
        const occ = this._assignment && this._assignment.occupancy;
        if (!hit || !occ || !occ[hit.card.id]) return null;
        for (const port of hit.box.ports || []) {
            const here = occ[hit.card.id][String(port.number)] || [];
            const o = here.find(x => x && x.layerId != null);
            if (o) return o.layerId;
        }
        return null;
    }

    // The voltage a screen's circuit runs at: its own source's on a screen
    // fed from several kinds, else the screen's.
    boxPowerCircuitVolts(layer, num) {
        if (!layer) return 0;
        if (typeof this._powerSourceRecords === 'function' && this._powerSourceRecords(layer).length
                && typeof this.circuitPowerSpec === 'function') {
            const spec = this.circuitPowerSpec(layer, num);
            if (spec && Number(spec.volts) > 0) return Number(spec.volts);
        }
        return parseFloat(layer.powerVoltage) || 0;
    }

    // The voltage of a distro output's circuits: the face row's, else the
    // output type's, else the distro's line to neutral.
    boxPowerDistroVolts(d, number) {
        if (!d) return 0;
        const fb = typeof this.faceBox === 'function' ? this.faceBox(d, number) : null;
        if (fb && Number(fb.volts) > 0) return Number(fb.volts);
        const t = typeof this.distroBoxType === 'function' ? this.distroBoxType(d, number) : null;
        const v = t && t.type && Array.isArray(t.type.volts) ? Number(t.type.volts[0]) : 0;
        if (v > 0) return v;
        return typeof this.distroNeutralVolts === 'function' ? (this.distroNeutralVolts(d) || 0) : 0;
    }

    // The watts every box of a chain draws at `volts`, summed; a box with
    // no figure adds nothing.
    _boxPowerChainWatts(chain, volts) {
        return (chain || []).reduce((t, e) => t + (this.boxPowerWattsAt(this.boxPowerSpec(e.box), volts) || 0), 0);
    }

    // What the boxes riding circuit `num` of `layer` add to it at `volts`
    // (start, end or fan-out, their chains with them). 0 where none ride it
    // - the common case, read without building anything.
    boxPowerCircuitWatts(layer, num, volts) {
        if (!layer || !this.project || !this.project.boxPower) return 0;
        const list = this.boxPowerOnCircuit(layer, num);
        if (!list.length) return 0;
        const v = volts != null ? volts : this.boxPowerCircuitVolts(layer, num);
        return list.reduce((t, p) => t + this._boxPowerChainWatts(p.chain, v), 0);
    }

    // The placements riding circuit `num` of `layer`, start first:
    // [{ head, chain, at, layer }]. Read off an index built once per
    // store, so the soca plan can ask it for every circuit. Only a circuit
    // that is there is ever asked about, so a record whose circuit a
    // repack took away adds nothing here either.
    boxPowerOnCircuit(layer, num) {
        if (!layer || !this.project || !this.project.boxPower) return [];
        const live = this._boxPowerLive();
        if (!live.size) return [];
        let idx = this._boxPowerCircuitIdx;
        if (!idx || idx.live !== live) {
            const map = new Map();
            const order = { start: 0, fanout: 1, end: 2 };
            for (const e of live.values()) {
                if (!CIRCUIT_KINDS.includes(e.at.kind)) continue;
                const key = `${e.at.layerId}:${Number(e.at.circuit)}`;
                const arr = map.get(key) || [];
                arr.push({ head: e, chain: this.boxPowerChain(e.box.id, live), at: e.at });
                arr.sort((a, b) => order[a.at.kind] - order[b.at.kind]);
                map.set(key, arr);
            }
            idx = this._boxPowerCircuitIdx = { live, map };
        }
        return (idx.map.get(`${layer.id}:${Number(num)}`) || []).map(p => ({ ...p, layer }));
    }

    // The placements fed straight off a distro output.
    boxPowerOnDistros() {
        if (!this.project || !this.project.boxPower) return [];
        return this.boxPowerPlacements().filter(p => p.d);
    }

    // The box fed straight from circuit `tail` of output `number` on `d`.
    boxPowerAtTail(d, number, tail) {
        return this.boxPowerOnDistros().find(p => String(p.d.id) === String(d.id)
            && Number(p.at.number) === Number(number) && Number(p.at.tail) === Number(tail)) || null;
    }

    // Book the distro-fed boxes onto getDistroLoads' buckets: watts, the
    // single-hot amps, and their circuit's legs and neutral at the show's
    // LED supply harmonics (no screen to read one from).
    _boxPowerBookDistros(buckets) {
        for (const p of this.boxPowerOnDistros()) {
            const b = buckets.get(p.d.id);
            if (!b) continue;
            const watts = this._boxPowerChainWatts(p.chain, p.volts);
            b.watts += watts;
            (b.boxes || (b.boxes = [])).push({ boxId: p.head.box.id, name: this.boxPowerTitle(p.head.box),
                                               watts, chain: p.chain.length });
            const own = this._singleHotAmps(p.d, watts, p.volts);
            if (own != null) b.ownAmps = (b.ownAmps || 0) + own;
            if (!this.distroLegNames(p.d).length) continue;
            const info = this.distroCircuitLegs(p.d, null,
                { number: p.at.number, spec: { volts: p.volts, boxSize: 6, breakout: null } },
                Math.max(0, (Number(p.at.tail) || 1) - 1), null);
            const triplen = typeof this.supplyTriplenFraction === 'function' ? this.supplyTriplenFraction(null) : 0;
            this._bookCircuitOnLegs(b, p.d, info, watts, p.volts, triplen);
        }
    }

    // ---- words ----------------------------------------------------------------

    // Where a box gets its power, in a user's words: "the start of S1-1
    // (WALL)", "the 2fer of S1-1 (WALL)", "D1 3 circuit 2", "XD SR A (daisy
    // chain)".
    boxPowerWhereText(entry) {
        if (!entry) return 'nothing';
        const at = entry.at;
        if (at.kind === 'chain') {
            const up = this.boxPowerOf(at.from);
            return `${up ? this.boxPowerTitle(up.box) : 'another box'} (daisy chain)`;
        }
        if (at.kind === 'distro') {
            const d = this.getDistros().find(x => String(x.id) === String(at.distroId));
            if (!d) return 'a distro';
            const fb = typeof this.faceBox === 'function' ? this.faceBox(d, at.number) : null;
            const name = this.distroBoxName(d, at.number);
            return fb && fb.kind === 'direct' ? name : `${name} circuit ${at.tail}`;
        }
        const layer = ((this.project && this.project.layers) || []).find(l => String(l.id) === String(at.layerId));
        const label = layer ? this.getPowerCircuitLabel(layer, at.circuit) : `circuit ${at.circuit}`;
        const scr = layer ? ` (${layer.name})` : '';
        if (at.kind === 'fanout') {
            const c = layer ? this.screenCircuits(layer).find(x => Number(x.num) === Number(at.circuit)) : null;
            const ways = c && Array.isArray(c.runIds) ? c.runIds.length : 2;
            return `the ${ways}fer of ${label}${scr}`;
        }
        return `the ${at.kind} of ${label}${scr}`;
    }

    // The cables box `box`'s feed can take: [{ id, name }]. A chain link is
    // a TRUE1 jumper.
    boxPowerCableOptions(box, chained = false) {
        if (chained) return [{ id: 'true1', name: BOX_POWER_CABLES.true1 }];
        const s = this.boxPowerSpec(box);
        return ((s && s.cables) || []).filter(id => BOX_POWER_CABLES[id])
            .map(id => ({ id, name: BOX_POWER_CABLES[id] }));
    }

    // A powered box's cable: { id, name, ft (or null), bad, text } - text
    // as the chips, the canvas and the paper print it ("10' TRUE1"), the
    // length written from the show's cable stock like a circuit cable.
    // `bad`: a length is stored that is no length (a hand-edited file), and
    // every surface says so rather than reading it as none.
    boxPowerCable(boxId) {
        const e = this.boxPowerOf(boxId);
        if (!e) return null;
        const opts = this.boxPowerCableOptions(e.box, e.at.kind === 'chain');
        const pick = opts.find(o => o.id === e.rec.cable) || opts[0] || { id: null, name: '' };
        const raw = e.rec.ft;
        const ft = this.parseCableLength(raw);
        const bad = ft === null && raw != null && String(raw).trim() !== '';
        return { id: pick.id, name: pick.name, ft, bad, raw: bad ? String(raw) : null,
                 text: bad ? `${pick.name}, length unreadable`
                     : (ft === null ? pick.name : this.cableText(ft, pick.name, 'circuit')) };
    }

    // A powered box's block on the Power Wiring sheet: "XD SR A · breakout
    // box at the start · 10' TRUE1"; a chain "XD-T A + XD-T B · breakout
    // boxes, daisy chain at the start · 15' TRUE1".
    boxPowerWiringCaption(p) {
        const at = p.at.kind === 'fanout' ? 'on the fan-out' : `at the ${p.at.kind}`;
        return [p.chain.map(e => this.boxPowerTitle(e.box)).join(' + '),
                `${p.chain.length > 1 ? 'breakout boxes, daisy chain' : 'breakout box'} ${at}`,
                this.boxPowerCableText(this.boxPowerCable(p.head.box.id))].filter(Boolean).join(' · ');
    }

    // The words a surface prints for a box's cable: "10' TRUE1", "TRUE1, no
    // length", "TRUE1, length unreadable".
    boxPowerCableText(cable) {
        if (!cable) return '';
        if (cable.bad || cable.ft != null) return cable.text;
        return `${cable.name}, no length`;
    }

    // ---- warnings -------------------------------------------------------------

    // The daisy chains past Brompton's thru rating: [{ head, count, amps,
    // over: { boxes, amps }, text }]. The current is what the head's thru
    // carries - every box after the head - at the head's circuit voltage.
    boxPowerChainChecks() {
        const out = [];
        for (const p of this.boxPowerPlacements()) {
            if (p.chain.length < 2) continue;
            const v = p.volts;
            const downstream = this._boxPowerChainWatts(p.chain.slice(1), v);
            const amps = v > 0 ? downstream / v : 0;
            const tooMany = p.chain.length > BOX_CHAIN_MAX_BOXES;
            const tooMuch = amps > BOX_CHAIN_MAX_AMPS + 1e-9;
            if (!tooMany && !tooMuch) continue;
            const name = this.boxPowerTitle(p.head.box);
            const parts = [];
            if (tooMany) parts.push(`${p.chain.length} boxes`);
            if (tooMuch) parts.push(`${amps.toFixed(2)} A through its thru`);
            out.push({ head: p.head, count: p.chain.length, amps, over: { boxes: tooMany, amps: tooMuch },
                       text: `The daisy chain from ${name} has ${parts.join(' and ')}. `
                           + `A TRUE1 thru is rated for ${BOX_CHAIN_MAX_BOXES} boxes and `
                           + `${BOX_CHAIN_MAX_AMPS} A.` });
        }
        return out;
    }

    // The powered boxes with no power figure (they add nothing): names. A
    // box on a hidden screen's circuit is left out with the screen, and a
    // box whose figure needs a voltage on a circuit with none (the XD) has
    // a figure: its circuit has no voltage, which the screen says itself.
    boxPowerUnfigured() {
        const out = [];
        for (const p of this.boxPowerPlacements()) {
            if (!this.boxPowerShown(p)) continue;
            for (const e of p.chain) {
                const spec = this.boxPowerSpec(e.box);
                if (this.boxPowerWattsAt(spec, p.volts) != null) continue;
                if (spec && Array.isArray(spec.ampsAt) && spec.ampsAt.length === 2 && !(p.volts > 0)) continue;
                out.push(this.boxPowerTitle(e.box));
            }
        }
        return out;
    }

    // The watts the boxes riding `layer`'s circuits draw, chains and all, at
    // their circuits' voltages: what the screen's own load figures add.
    boxPowerScreenWatts(layer) {
        if (!layer || !this.project || !this.project.boxPower) return 0;
        return this.boxPowerPlacements().filter(p => p.layer && String(p.layer.id) === String(layer.id))
            .reduce((t, p) => t + this._boxPowerChainWatts(p.chain, p.volts), 0);
    }

    // The boxes fed straight off a distro, for the show's totals:
    // [{ volts, watts }].
    boxPowerDistroFedLoads() {
        return this.boxPowerOnDistros().map(p => ({ volts: p.volts, watts: this._boxPowerChainWatts(p.chain, p.volts) }));
    }

    // The outputs of `d` a box is fed straight off: their numbers, held so
    // no multi is dealt onto them (_faceAutoNumber, faceRowFreeBoxes).
    boxPowerHeldNumbers(d) {
        const out = new Set();
        if (!d || !this.project || !this.project.boxPower) return out;
        for (const p of this.boxPowerOnDistros()) {
            if (String(p.d.id) === String(d.id)) out.add(Number(p.at.number));
        }
        return out;
    }

    // A screen's circuit on the very circuit of `d` a box is fed straight
    // off: [{ text }] for the distro's checks, red - two loads on one
    // circuit nobody planned for.
    boxPowerDistroClashes(d) {
        const out = [];
        if (!d || !this.project || !this.project.boxPower) return out;
        for (const p of this.boxPowerOnDistros()) {
            if (String(p.d.id) !== String(d.id)) continue;
            const n = Number(p.at.number), t = Number(p.at.tail);
            const held = typeof this._dockTailHolder === 'function' ? this._dockTailHolder(d.id, n, t) : null;
            const paired = !held && typeof this._facePairedHolders === 'function'
                ? this._facePairedHolders(d, n, t)[0] : null;
            if (!held && !paired) continue;
            const who = held ? `${held.layer.name}'s ${this.getPowerCircuitLabel(held.layer, held.circuit)}`
                : paired.label;
            const names = p.chain.map(e => this.boxPowerTitle(e.box)).join(' + ');
            out.push({ key: `bpclash:${p.head.box.id}`,
                       text: `Breakout box ${names} is powered from ${this.boxPowerWhereText(p.head)}, and `
                           + `${who} is on that circuit too. Move one of them.` });
        }
        return out;
    }

    // Whether a placement prints: a box riding a hidden screen's circuit is
    // left out, the way the screen is.
    boxPowerShown(p) {
        return !p.layer || p.layer.visible !== false;
    }

    // ---- gestures ---------------------------------------------------------------

    // The screens a change to box `boxId`'s feed would change: the screen
    // whose circuit it (or its chain's head) rides now.
    _boxPowerLayersOf(boxId) {
        const head = this.boxPowerHead(boxId);
        if (!head || !CIRCUIT_KINDS.includes(head.at.kind)) return [];
        const l = ((this.project && this.project.layers) || []).find(x => String(x.id) === String(head.at.layerId));
        return l ? [l] : [];
    }

    // The box already at a spot (another one), or null.
    _boxPowerAtSpot(at, except = null) {
        for (const e of this._boxPowerStanding().values()) {
            if (e.box.id === except || e.at.kind !== at.kind) continue;
            if (CIRCUIT_KINDS.includes(at.kind) && String(e.at.layerId) === String(at.layerId)
                    && Number(e.at.circuit) === Number(at.circuit)) return e;
            if (at.kind === 'distro' && String(e.at.distroId) === String(at.distroId)
                    && Number(e.at.number) === Number(at.number) && Number(e.at.tail) === Number(at.tail)) return e;
        }
        return null;
    }

    // Power box `boxId` from `at` - ONE undo step, 'Power Breakout Box'. Its
    // feed so far goes, and its cable and length with it (a new feed starts
    // with none); the boxes chained after it come along. False, nothing
    // written, when the box takes no power, the spot is taken or a screen
    // it would change is locked (named in the dialog).
    setBoxPower(boxId, at) {
        const hit = this.boxPowerBoxes().find(b => b.box.id === boxId);
        if (!hit || !this.boxPowerSpec(hit.box) || !at) return false;
        const layers = [...this._boxPowerLayersOf(boxId)];
        if (CIRCUIT_KINDS.includes(at.kind)) {
            const l = ((this.project && this.project.layers) || []).find(x => String(x.id) === String(at.layerId));
            if (!l) return false;
            layers.push(l);
        }
        if (this._lockedRefused([...new Set(layers)])) return false;
        const taken = this._boxPowerAtSpot(at, boxId);
        if (taken) {
            sendClientLog('box_power_spot_taken', { boxId, at, holder: taken.box.id });
            this._toast(`${this.boxPowerTitle(taken.box)} is already powered from ${this.boxPowerWhereText(taken)}. `
                + 'Daisy chain to it, or remove it first.', true, 6000);
            return false;
        }
        const store = this.project.boxPower && typeof this.project.boxPower === 'object'
            ? this.project.boxPower : (this.project.boxPower = {});
        const rec = { cardId: hit.card.id, at: { ...at } };
        const opts = this.boxPowerCableOptions(hit.box, at.kind === 'chain');
        if (opts.length) rec.cable = opts[0].id;
        store[boxId] = rec;
        this._boxPowerPrune();
        sendClientLog('box_power_set', { boxId, at: rec.at });
        this._boxPowerCommit(at.kind === 'chain' ? 'Daisy Chain Breakout Box' : 'Power Breakout Box');
        return true;
    }

    // Chain box `toId` after powered box `fromId` (both with a thru): one
    // undo step. Refused where `from` already has a box after it, where
    // `to` is up its own chain, or where a screen it changes is locked.
    chainBoxPower(fromId, toId) {
        const from = this.boxPowerOf(fromId);
        const to = this.boxPowerBoxes().find(b => b.box.id === toId);
        if (!from || !to || fromId === toId) return false;
        if (!this.boxPowerHasThru(from.box) || !this.boxPowerHasThru(to.box)) return false;
        if (this.boxPowerChild(fromId)) return false;
        if (this._boxPowerUpstream(fromId).some(e => e.box.id === toId)) return false;
        const layers = [...this._boxPowerLayersOf(fromId), ...this._boxPowerLayersOf(toId)];
        if (this._lockedRefused([...new Set(layers)])) return false;
        return this.setBoxPower(toId, { kind: 'chain', from: fromId });
    }

    // Take box `boxId`'s power away - and the boxes chained after it,
    // which have no power without it: one undo step. Their cables and
    // lengths go with the feed.
    removeBoxPower(boxId) {
        const store = this.project && this.project.boxPower;
        if (!store || !store[boxId]) return false;
        if (this._lockedRefused(this._boxPowerLayersOf(boxId))) return false;
        const gone = [boxId];
        const live = this._boxPowerLive();
        let next = this.boxPowerChild(boxId, live);
        while (next && !gone.includes(next.box.id)) {
            gone.push(next.box.id);
            next = this.boxPowerChild(next.box.id, live);
        }
        const wasChain = store[boxId].at && store[boxId].at.kind === 'chain';
        gone.forEach(id => { delete store[id]; });
        this._boxPowerPrune();
        sendClientLog('box_power_removed', { boxIds: gone });
        this._boxPowerCommit(wasChain ? 'Remove Daisy Chain' : 'Remove Breakout Box Power');
        return true;
    }

    // The cable of box `boxId`'s feed: `patch` { cable } or { ft } (typed
    // text reads the way every typed length does). One undo step.
    setBoxPowerCable(boxId, patch) {
        const e = this.boxPowerOf(boxId);
        if (!e || !patch) return false;
        const rec = this.project.boxPower[boxId];
        const next = { ...rec };
        if (patch.cable !== undefined) {
            const opts = this.boxPowerCableOptions(e.box, e.at.kind === 'chain');
            if (!opts.some(o => o.id === patch.cable)) return false;
            next.cable = patch.cable;
        }
        if (patch.ft !== undefined) {
            const read = typeof patch.ft === 'string' ? this.readTypedLength(patch.ft, 'cable')
                : { ok: true, n: this.parseCableLength(patch.ft) };
            if (!read.ok) return false;
            if (read.n === null || !(read.n > 0)) delete next.ft; else next.ft = read.n;
        }
        if (JSON.stringify(next) === JSON.stringify(rec)) return false;
        if (this._lockedRefused(this._boxPowerLayersOf(boxId))) return false;
        this.project.boxPower[boxId] = next;
        sendClientLog('box_power_cable', { boxId, cable: next.cable || null, ft: next.ft == null ? null : next.ft });
        this._boxPowerCommit('Set Breakout Box Cable');
        return true;
    }

    // Drop the records whose head `match`es (its `at`), and the chains off
    // them: a removed distro, an output edited away. Returns the ids
    // dropped; the caller's own undo step and push carry the change.
    _boxPowerDropWhere(match, why) {
        const store = this.project && this.project.boxPower;
        if (!store || typeof store !== 'object') return [];
        const gone = new Set(Object.keys(store).filter(id => store[id] && store[id].at
            && store[id].at.kind !== 'chain' && match(store[id].at)));
        if (!gone.size) return [];
        for (let grew = true; grew;) {
            grew = false;
            for (const id of Object.keys(store)) {
                const at = store[id] && store[id].at;
                if (!gone.has(id) && at && at.kind === 'chain' && gone.has(at.from)) { gone.add(id); grew = true; }
            }
        }
        gone.forEach(id => { delete store[id]; });
        this._boxPowerMemo = null;
        this._boxPowerStandMemo = null;
        this._boxPowerCircuitIdx = null;
        sendClientLog('box_power_dropped', { why, boxIds: [...gone] });
        return [...gone];
    }

    // A distro removed: the boxes fed straight off it go with it.
    boxPowerDropForDistro(distroId) {
        return this._boxPowerDropWhere(at => at.kind === 'distro' && String(at.distroId) === String(distroId),
                                       'distro removed');
    }

    // A distro's outputs edited: a box on an output or circuit the face no
    // longer has goes.
    boxPowerDropStaleOutputs(d) {
        if (!d) return [];
        return this._boxPowerDropWhere(at => at.kind === 'distro' && String(at.distroId) === String(d.id)
            && !this._boxPowerSpotStands(at), 'distro outputs changed');
    }

    // What a renderBoxPower pass drew on one screen, logged when it
    // changes (each redraw draws the same thing; one line per change).
    _boxPowerLogDrawn(layerId, drawn) {
        const sig = JSON.stringify(drawn);
        const seen = this._boxPowerDrawnLog || (this._boxPowerDrawnLog = new Map());
        if (seen.get(String(layerId)) === sig) return;
        seen.set(String(layerId), sig);
        sendClientLog('box_power_drawn', { layerId, boxes: drawn });
    }

    // Drop the records that no longer stand (a box gone, moved to another
    // card, a chain left without its head). Returns true when it dropped
    // any. Never writes a key onto a project that has none.
    _boxPowerPrune() {
        const store = this.project && this.project.boxPower;
        if (!store || typeof store !== 'object') return false;
        this._boxPowerMemo = null;
        this._boxPowerStandMemo = null;
        this._boxPowerCircuitIdx = null;
        const live = this._boxPowerLive();
        let dropped = false;
        for (const id of Object.keys(store)) {
            if (!live.has(id)) { delete store[id]; dropped = true; }
        }
        if (dropped) this._boxPowerMemo = null;
        return dropped;
    }

    // After a box removal or a card change (_processorRequest): the feeds
    // that went with it go in the same undo step, and are persisted.
    _boxPowerAfterTreeEdit() {
        if (!this.project || !this.project.boxPower || !this._processorCatalog) return;
        if (this._boxPowerPrune()) this._persistBoxPower();
    }

    _persistBoxPower() {
        if (typeof this._followingHolds === 'function' && this._followingHolds('boxPower')) {
            return Promise.resolve();
        }
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ boxPower: (this.project && this.project.boxPower) || {} }),
        }).catch(() => {});
        // the distros' queue: two quick POSTs must land in order
        this._distroPushQueue = (this._distroPushQueue || Promise.resolve()).then(send);
        return this._distroPushQueue;
    }

    _boxPowerCommit(action) {
        this._boxPowerMemo = null;
        this._boxPowerStandMemo = null;
        this._boxPowerCircuitIdx = null;
        this._circuitTailCache = null;
        this.saveState(action);
        this._persistBoxPower();
        this.boxPowerRefreshViews();
    }

    // Every surface a feed shows on.
    boxPowerRefreshViews() {
        this._boxPowerMemo = null;
        this._boxPowerStandMemo = null;
        if (typeof this.updatePowerCapacityDisplay === 'function') this.updatePowerCapacityDisplay();
        if (typeof this.refreshDistroPanel === 'function') this.refreshDistroPanel();
        if (typeof this.renderHardwareDock === 'function') this.renderHardwareDock();
        if (typeof this.renderProcessorPanel === 'function') this.renderProcessorPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // ---- the right-click --------------------------------------------------------

    // The box symbol the canvas drew under client point (x, y), or null
    // (canvas-power.js renderBoxPower records each one with its frame).
    _boxPowerSymbolAt(x, y) {
        const r = window.canvasRenderer;
        if (!r || !r.canvas || r.viewMode !== 'power' || !Array.isArray(r._boxPowerHits)) return null;
        const rect = r.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
        const px = (x - rect.left) * (r.canvas.width / Math.max(1, rect.width));
        const py = (y - rect.top) * (r.canvas.height / Math.max(1, rect.height));
        for (let i = r._boxPowerHits.length - 1; i >= 0; i--) {
            const h = r._boxPowerHits[i];
            let p;
            try { p = h.inv.transformPoint(new DOMPoint(px, py)); } catch (_) { continue; }
            if (p.x >= h.x && p.x <= h.x + h.w && p.y >= h.y && p.y <= h.y + h.h) return h.boxId;
        }
        return null;
    }

    // One power slot: a submenu of the show's boxes for spot `at`.
    _boxPowerSlot(label, at, intro) {
        const offered = this.boxPowerOffered();
        const here = this._boxPowerAtSpot(at);
        const entries = offered.map(({ box }) => {
            const title = this.boxPowerTitle(box);
            const now = this.boxPowerOf(box.id);
            if (here && here.box.id === box.id) {
                return { label: `${title} (here now)`, disabled: true,
                         title: `${title} is powered from here already.` };
            }
            if (here) {
                return { label: title, disabled: true,
                         title: `${this.boxPowerTitle(here.box)} is powered from here already. `
                             + 'Daisy chain to it, or remove it first.' };
            }
            return {
                label: now ? `${title} (now on ${this.boxPowerWhereText(now)})` : title,
                title: `${intro} ${title}.`
                    + (now ? ` It comes off ${this.boxPowerWhereText(now)}, its cable and length with it.` : '')
                    + ' Its watts count on the circuit. One undoable step.',
                run: () => this.setBoxPower(box.id, at),
            };
        });
        if (!entries.length) {
            entries.push({ label: 'No breakout boxes', disabled: true,
                           title: 'No CVT or XD box in the show lists a power figure. Add one to a '
                               + 'processor card in the Data tray first.' });
        }
        return { label, entries };
    }

    // The items for a powered box (its symbol on the canvas, or the box in
    // the Data tray): remove its power, and daisy chain on from it.
    _boxPowerBoxItems(boxId) {
        const e = this.boxPowerOf(boxId);
        if (!e) return { slots: [], items: [] };
        const title = this.boxPowerTitle(e.box);
        const chained = e.at.kind === 'chain';
        const after = this.boxPowerChain(this.boxPowerHead(boxId).box.id);
        const at = after.findIndex(x => x.box.id === boxId);
        const tail = at >= 0 ? after.length - at - 1 : 0;
        const items = [{
            label: chained ? 'Remove daisy chain' : 'Remove breakout box power',
            title: `${title} stops getting power from ${this.boxPowerWhereText(e)}; its cable and `
                + 'length go with it.'
                + (tail ? ` The ${tail === 1 ? 'box' : `${tail} boxes`} chained after it lose power too.` : '')
                + ' One undoable step.',
            run: () => this.removeBoxPower(boxId),
        }];
        const slots = [];
        if (this.boxPowerHasThru(e.box) && !this.boxPowerChild(boxId)) {
            const up = new Set(this._boxPowerUpstream(boxId).map(x => x.box.id));
            const entries = this.boxPowerOffered()
                .filter(b => b.box.id !== boxId && !up.has(b.box.id) && this.boxPowerHasThru(b.box))
                .map(({ box }) => {
                    const name = this.boxPowerTitle(box);
                    const now = this.boxPowerOf(box.id);
                    return {
                        label: now ? `${name} (now on ${this.boxPowerWhereText(now)})` : name,
                        title: `A TRUE1 jumper from ${title}'s thru to ${name}.`
                            + (now ? ` It comes off ${this.boxPowerWhereText(now)}.` : '')
                            + ' One undoable step.',
                        run: () => this.chainBoxPower(boxId, box.id),
                    };
                });
            if (!entries.length) {
                entries.push({ label: 'No other XD or XD-T', disabled: true,
                               title: 'Only an XD or an XD-T has the TRUE1 thru a daisy chain needs.' });
            }
            slots.push({ label: 'Daisy chain to', entries });
        }
        return { slots, items };
    }

    // The right-click's box-power items at client point (x, y):
    //   { slots: [{ label, entries }], items: [{ label, title, run }] }
    // or null where none apply. On the Power tab canvas: a box symbol, or a
    // circuit's first cabinet (its tag sits there: start and end), its last
    // (end), a shared circuit (its fan-out). In the tray: a free circuit
    // or output chip, or a box.
    _prepareBoxPowerMenu(x, y) {
        if (!this.project) return null;
        const under = document.elementFromPoint(x, y);
        const inDock = !!(under && under.closest && under.closest('#hardware-dock'));
        const out = { slots: [], items: [] };
        const add = (part) => { out.slots.push(...part.slots); out.items.push(...part.items); };
        if (inDock) {
            const payload = typeof this._dockChipPayload === 'function' ? this._dockChipPayload(under) : null;
            if (!payload) return null;
            if (payload.type === 'box' && payload.boxId) add(this._boxPowerBoxItems(payload.boxId));
            if (payload.type === 'tail') {
                const d = this.getDistros().find(z => String(z.id) === String(payload.distroId));
                if (!d) return null;
                const number = parseInt(payload.number, 10);
                const tail = parseInt(payload.tail, 10) || 1;
                const fed = this.boxPowerAtTail(d, number, tail);
                if (fed) add(this._boxPowerBoxItems(fed.head.box.id));
                const held = this._dockTailHolder(d.id, number, tail)
                    || (typeof this._facePairedHolders === 'function' && this._facePairedHolders(d, number, tail).length);
                if (!held && !fed) {
                    const fb = typeof this.faceBox === 'function' ? this.faceBox(d, number) : null;
                    const where = fb && fb.kind === 'direct'
                        ? this.distroBoxName(d, number) : `${this.distroBoxName(d, number)} circuit ${tail}`;
                    out.slots.push(this._boxPowerSlot(`Power a breakout box from ${where}`,
                        { kind: 'distro', distroId: d.id, number, tail },
                        `${where} feeds, by itself,`));
                }
            }
            return out.slots.length || out.items.length ? out : null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas || renderer.viewMode !== 'power') return null;
        const sym = this._boxPowerSymbolAt(x, y);
        if (sym) {
            add(this._boxPowerBoxItems(sym));
            return out.slots.length || out.items.length ? out : null;
        }
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const layer = (this.project.layers || []).find(l => l.id === hit.layerId);
        const circuit = layer ? renderer._powerCircuitForPanel(layer, hit.panel) : null;
        if (!circuit || !circuit.owner) return null;
        const owner = circuit.owner;
        const c = this.screenCircuits(owner).find(z => Number(z.num) === Number(circuit.circuitNum));
        if (!c || !(c.panels || []).length) return null;
        const same = (i) => {
            const p = c.panels[i];
            const on = (c.layers && c.layers[i]) || owner;
            return !!p && (p === hit.panel || (String(on.id) === String(hit.layerId)
                && p.row === hit.panel.row && p.col === hit.panel.col));
        };
        const first = same(0);
        const last = same(c.panels.length - 1);
        const label = this.getPowerCircuitLabel(owner, c.num);
        const spot = (kind) => ({ kind, layerId: owner.id, circuit: c.num });
        if (first) {
            out.slots.push(this._boxPowerSlot(`Power a breakout box at the start of ${label}`, spot('start'),
                `${label} goes to the box first, then on to its panels:`));
        }
        if (first || last) {
            out.slots.push(this._boxPowerSlot(`Power a breakout box at the end of ${label}`, spot('end'),
                `The power out of ${label}'s last panel jumps to`));
        }
        if (Array.isArray(c.runIds) && c.runIds.length > 1) {
            out.slots.push(this._boxPowerSlot(
                `Power a breakout box from the ${c.runIds.length}fer of ${label}`, spot('fanout'),
                `A leg of ${label}'s ${c.runIds.length}fer feeds`));
        }
        // the boxes already on this circuit's ends, to take off
        for (const p of this.boxPowerOnCircuit(owner, c.num)) {
            if ((p.at.kind === 'start' && !first) || (p.at.kind === 'end' && !first && !last)) continue;
            add(this._boxPowerBoxItems(p.head.box.id));
        }
        return out.slots.length || out.items.length ? out : null;
    }

    // ---- the gear: Power in ----------------------------------------------------

    // The box gear's "Power in" block: where it is fed, its cable and
    // length (the chain link's TRUE1 on a chained box). Null for an
    // unpowered box, or one with no power figure in the catalog.
    boxPowerGearBlock(box) {
        const e = this.boxPowerOf(box && box.id);
        if (!e) return null;
        const wrap = document.createElement('div');
        wrap.className = 'hw-box-power';
        wrap.dataset.lrdBoxPower = box.id;
        const head = document.createElement('div');
        head.className = 'hw-pop-head';
        head.textContent = 'Power in';
        wrap.appendChild(head);
        const where = document.createElement('div');
        where.className = 'hw-box-power-where';
        const p = this.boxPowerPlacements().find(x => x.chain.some(c => c.box.id === box.id));
        const watts = p ? this.boxPowerWattsAt(this.boxPowerSpec(box), p.volts) : null;
        where.textContent = `From ${this.boxPowerWhereText(e)}`
            + (watts != null ? ` · ${Math.round(watts)} W` : ' · no power figure');
        wrap.appendChild(where);
        const row = document.createElement('div');
        row.className = 'hw-box-power-row';
        const sel = document.createElement('select');
        sel.className = 'hw-box-power-cable';
        const opts = this.boxPowerCableOptions(box, e.at.kind === 'chain');
        const cur = this.boxPowerCable(box.id);
        opts.forEach(o => {
            const op = document.createElement('option');
            op.value = o.id;
            op.textContent = o.name;
            if (cur && cur.id === o.id) op.selected = true;
            sel.appendChild(op);
        });
        sel.disabled = opts.length < 2;
        sel.title = 'The cable to the box\'s power inlet.';
        sel.addEventListener('change', () => this.setBoxPowerCable(box.id, { cable: sel.value }));
        row.appendChild(sel);
        const len = document.createElement('input');
        len.type = 'text';
        len.className = 'hw-box-power-ft';
        len.placeholder = this.cableUnit() === 'm' ? '3' : '10';
        len.value = cur && cur.ft != null ? String(cur.ft) : (cur && cur.bad ? cur.raw : '');
        len.title = (cur && cur.bad ? `"${cur.raw}" is not a length: type the cable's length again. ` : '')
            + `The cable's length, in ${this.cableUnitWord()}. It goes on the pull sheet.`
            + (typeof this.cableStockHint === 'function' && cur && cur.ft != null
                ? this.cableStockHint(cur.ft, 'circuit') : '');
        const commit = () => this.setBoxPowerCable(box.id, { ft: len.value });
        len.addEventListener('change', commit);
        row.appendChild(len);
        const unit = document.createElement('span');
        unit.className = 'hw-box-power-unit';
        unit.textContent = this.cableUnitAbbr();
        row.appendChild(unit);
        wrap.appendChild(row);
        return wrap;
    }
}

for (const k of Object.getOwnPropertyNames(_BoxPower.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_BoxPower.prototype, k));
    }
}
