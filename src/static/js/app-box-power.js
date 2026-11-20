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
//     is a TRUE1 jumper with a length. The thru is for daisy chaining boxes
//     ONLY, never panels (owner, 2026-11-20, on Brompton's XD data sheet of
//     Mar 2026 and its processor manual V3.5 Rev F of Sep 2026): a chain
//     past the 5 units both are rated for is WARNED in gold, never refused;
//     an XD anywhere in a chain is warned too past its own thru's 2 A, the
//     draw of the boxes after it. The XD-T publishes no amp figure, so none
//     is used (catalog `thruUnits` / `thruAmps`).
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
// THE WIRING AT A CIRCUIT'S START (owner rulings, 2026-11-19, 2026-11-20):
//   * EVERY box at the start of a circuit, an XD or XD-T included, gets a
//     2fer at the head of the circuit, of the panels' own connector (TRUE1
//     on a TRUE1 wall): one leg to the box, one to the panels. No box sits
//     in line: nothing official runs panels off a thru. An older show that
//     had an XD in line just reads this way. The 2fer is on the pull sheet.
//   * On a circuit already shared by a 2fer (or wider): the box's own 2fer
//     comes first, its other leg into the circuit's 2fer. So a box on a
//     shared circuit is a box at its START, offered on the first panel of
//     any of its runs. (An older file's 'fanout' record reads as 'start'.)
//   * Off a distro: only a direct output, or a spare circuit of a multi
//     that already runs to a screen, is offered.
//   * Any change that renumbers a circuit or takes it away: the box follows
//     its panel (the first for the start, the last for the end) to the
//     circuit that panel now starts (or ends) a run of; a panel that no
//     longer does leaves the box with no power, named in gold until it is
//     powered again. In the change's own undo step (_boxPowerFollowPanels).
//   * A box's own 2fer counts wherever 2fers do: the pull sheet, the
//     binder's Shared circuits table and the screens' 2fer totals
//     (boxPowerExtraTwofers).
//
// THE MODEL. `project.boxPower = { [boxId]: rec }`, persisted on POST
// /api/project like the distros:
//   rec = { cardId, at, cable?, ft?, panel?, lost? }
//   (`panel`: the scoped cabinet key a box at a start or end follows;
//   `lost`: that panel stopped starting or ending a run, no power)
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
// The units a TRUE1 thru chain is rated for where a catalog entry with a
// thru says none (each XD and XD-T says its own `thruUnits`: 5).
export const BOX_CHAIN_MAX_BOXES = 5;

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
            // (a box whose panel stopped starting or ending a run has no
            // power: boxPowerLost names it)
            if (!rec || typeof rec !== 'object' || !hit || !rec.at || rec.lost) continue;
            if (rec.cardId != null && String(rec.cardId) !== String(hit.card.id)) continue;
            if (!this.boxPowerSpec(hit.box)) continue;
            // a box on a shared circuit is a box at its start (2026-11-19)
            const at = rec.at.kind === 'fanout' ? { ...rec.at, kind: 'start' } : rec.at;
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
    // circuit of that number (a renumber the box's panel is followed
    // across moves the record, _boxPowerCarryApply; a repack that takes
    // the number away leaves the box with no feed anywhere until it is
    // powered again), or an output and circuit the distro has.
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
        return `the ${at.kind === 'fanout' ? 'start' : at.kind} of ${label}${scr}`;
    }

    // How a box (or a daisy chain) at the START of a circuit is wired in,
    // or null for any other placement (owner, 2026-11-19, 2026-11-20):
    //   { ways, plug, splitter, words, tag }
    // EVERY box at a start, an XD or XD-T as much as the rest, is fed from
    // a 2fer at the head of the circuit, of the panels' own connector
    // (`splitter`, "TRUE1 2fer"): one leg to the box, the other to the
    // panels or into the circuit's own Nfer. A thru never feeds panels.
    // `ways` is the circuit's own splitter (1 for none). `words` is what
    // paper prints ("on a TRUE1 2fer, other leg to the 2fer"), `tag` the
    // canvas pill's short form ("on a TRUE1 2fer").
    boxPowerStartWiring(p) {
        if (!p || !p.layer || !p.at || !['start', 'fanout'].includes(p.at.kind) || !p.head) return null;
        const c = this.screenCircuits(p.layer).find(x => Number(x.num) === Number(p.at.circuit)) || null;
        const ways = c && Array.isArray(c.runIds) && c.runIds.length > 1 ? c.runIds.length : 1;
        const on = (c && c.layers && c.layers[0]) || p.layer;
        const plug = (typeof this.panelInput === 'function' && this.panelInput(on).name) || 'TRUE1';
        const to = ways > 1 ? `the ${ways}fer` : 'the panels';
        return { ways, plug, splitter: `${plug} 2fer`,
                 words: `on a ${plug} 2fer, other leg to ${to}`, tag: `on a ${plug} 2fer` };
    }

    // The placement box `boxId` is part of (its own, or its chain head's),
    // or null.
    _boxPowerPlacementOf(boxId) {
        return this.boxPowerPlacements().find(x => x.chain.some(c => c.box.id === boxId)) || null;
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
    // box at the start · 10' TRUE1 · on a TRUE1 2fer, other leg to the
    // panels"; a chain "XD-T A + XD-T B · breakout boxes, daisy chain at the
    // start · 15' TRUE1 · on a TRUE1 2fer, other leg to the panels"; at the
    // end "XD A · breakout box at the end · 10' TRUE1".
    boxPowerWiringCaption(p) {
        const kind = p.at.kind === 'fanout' ? 'start' : p.at.kind;
        const wiring = this.boxPowerStartWiring(p);
        return [p.chain.map(e => this.boxPowerTitle(e.box)).join(' + '),
                `${p.chain.length > 1 ? 'breakout boxes, daisy chain' : 'breakout box'} at the ${kind}`,
                this.boxPowerCableText(this.boxPowerCable(p.head.box.id)),
                wiring ? wiring.words : ''].filter(Boolean).join(' · ');
    }

    // The words a surface prints for a box's cable: "10' TRUE1", "TRUE1, no
    // length", "TRUE1, length unreadable".
    boxPowerCableText(cable) {
        if (!cable) return '';
        if (cable.bad || cable.ft != null) return cable.text;
        return `${cable.name}, no length`;
    }

    // ---- warnings -------------------------------------------------------------

    // The daisy chains past their TRUE1 thru's rating (owner, 2026-11-20,
    // on Brompton's XD data sheet of Mar 2026 and its processor manual V3.5
    // Rev F of Sep 2026): one entry per warning,
    //   { kind: 'units' | 'amps', head, box, layer, count, amps, units,
    //     rated, text }
    // where `box` is the entry the warning names.
    //   * UNITS, per chain: past the boxes the chain is rated for (5 on the
    //     XD and the XD-T; the least of its boxes' `thruUnits`), named by
    //     its head: "XD-T A chain: 6 boxes, rated for 5."
    //   * AMPS, per XD, wherever it stands in the chain (owner, 2026-11-20):
    //     the 2 A is the XD's OWN thru rating (`thruAmps`), so what counts
    //     is the draw of every box after it, down its thru - its own draw
    //     comes in through its input - at the circuit's voltage: "XD B
    //     thru: 2.14 A to the boxes after it, rated for 2 A." The XD-T
    //     publishes no amp figure, so its thru is never checked.
    // Gold, never refused.
    boxPowerChainChecks() {
        const out = [];
        for (const p of this.boxPowerPlacements()) {
            if (p.chain.length < 2) continue;
            const v = p.volts;
            const base = { head: p.head, layer: p.layer || null, count: p.chain.length };
            const units = Math.min(...p.chain.map(e => this.boxPowerThruUnits(e.box) || BOX_CHAIN_MAX_BOXES));
            if (p.chain.length > units) {
                out.push({ ...base, kind: 'units', box: p.head, units, amps: null, rated: null,
                           text: `${this.boxPowerTitle(p.head.box)} chain: ${p.chain.length} boxes, `
                               + `rated for ${units}.` });
            }
            p.chain.forEach((e, i) => {
                const rated = this.boxPowerThruAmps(e.box);
                const after = p.chain.slice(i + 1);
                if (rated == null || !after.length) return;
                const amps = v > 0 ? this._boxPowerChainWatts(after, v) / v : 0;
                if (!(amps > rated + 1e-9)) return;
                out.push({ ...base, kind: 'amps', box: e, units, amps, rated,
                           text: `${this.boxPowerTitle(e.box)} thru: ${amps.toFixed(2)} A to the `
                               + `${after.length === 1 ? 'box' : 'boxes'} after it, rated for ${rated} A.` });
            });
        }
        return out;
    }

    // The boxes a box's TRUE1 thru chain is rated for (the catalog's
    // `thruUnits`), or null for a box with no thru.
    boxPowerThruUnits(box) {
        if (!this.boxPowerHasThru(box)) return null;
        const n = Number((this.boxPowerSpec(box) || {}).thruUnits);
        return Number.isFinite(n) && n > 0 ? n : BOX_CHAIN_MAX_BOXES;
    }

    // The amps this box's own thru may carry on to the boxes after it (the
    // catalog's `thruAmps`), or null where none is published: the XD's
    // 2 A; the XD-T has none, and no other box has a thru. Never made up.
    boxPowerThruAmps(box) {
        if (!this.boxPowerHasThru(box)) return null;
        const a = Number((this.boxPowerSpec(box) || {}).thruAmps);
        return Number.isFinite(a) && a > 0 ? a : null;
    }

    // The 2fers boxes add to circuit `num` of `layer` (every box at its
    // start, owner 2026-11-20), as the pull sheet lists them: the
    // placements, less a box off paper. The binder's Shared circuits table
    // and the screens' 2fer counts read the same list (2026-11-19: "count
    // everywhere").
    boxPowerExtraTwofers(layer, num) {
        if (!layer || !this.project || !this.project.boxPower) return [];
        return this.boxPowerOnCircuit(layer, num).filter(p => {
            const w = this.boxPowerStartWiring(p);
            if (!w || !w.splitter) return false;
            const e = p.head;
            if (typeof this._pullHiddenOnlyBox === 'function' && this._pullHiddenOnlyBox(e.box, e.card)) return false;
            return !(typeof this._pullProcOffPaper === 'function' && this._pullProcOffPaper(e.proc));
        });
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
        // a box on a shared circuit is a box at its start (2026-11-19)
        if (at && at.kind === 'fanout') at = { ...at, kind: 'start' };
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
        // the panel it follows (_boxPowerFollowPanels)
        if (CIRCUIT_KINDS.includes(at.kind)) {
            const l = ((this.project && this.project.layers) || []).find(x => String(x.id) === String(at.layerId));
            const key = this._boxPowerPanelKey(l, at.circuit, at.kind === 'end' ? 'end' : 'start');
            if (key) rec.panel = key;
        }
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

    // ---- a box follows its panel ----------------------------------------------
    //
    // The owner, 2026-11-19: a powered box follows its PANEL, the way a card
    // pin rides its cabinets across a port renumber - on ANY change that
    // renumbers a circuit or takes it away (a repack, a resize, a redraw,
    // Organized or Max Capacity, 2fer packing, the Circuit numbers switch,
    // merged circuits, ...). A box at the start notes the circuit's first
    // panel, a box at the end its last (the record's `panel`, a scoped
    // cabinet key). After the change the box rides whatever circuit that
    // panel lands on, as long as the panel still STARTS one of its runs (a
    // box at the start) or ENDS one (a box at the end). Otherwise it loses
    // its power (`lost`): it draws nothing, a toast says so at once and the
    // Power tab and the binder keep naming it until it is powered again or
    // its power is removed. It runs as every undo step is taken
    // (saveState), so it is part of the step that caused it, and with a
    // circuit cable's carry (app-power.js _cableCarryBegin /
    // _cableCarryApply) at the moments a cable follows its cabinet.

    // The scoped key of the panel a box at the start (or end) of circuit
    // `num` of `layer` is on now: the circuit's first (or last) panel.
    _boxPowerPanelKey(layer, num, kind) {
        if (!layer || typeof this.getScopedPanelKey !== 'function') return null;
        const c = this.screenCircuits(layer).find(x => Number(x.num) === Number(num));
        if (!c || !(c.panels || []).length) return null;
        const i = kind === 'end' ? c.panels.length - 1 : 0;
        const on = (c.layers && c.layers[i]) || layer;
        return this.getScopedPanelKey(on.id, c.panels[i]);
    }

    // `layer`'s circuits by the panels that start and end their runs:
    // { heads: Map(key -> num), tails: Map(key -> num) }.
    _boxPowerRunEnds(layer) {
        const heads = new Map(), tails = new Map();
        for (const c of this.screenCircuits(layer)) {
            const panels = c.panels || [];
            const runs = Array.isArray(c.branches) && c.branches.length ? c.branches : [panels];
            const key = (i) => this.getScopedPanelKey(((c.layers && c.layers[i]) || layer).id, panels[i]);
            let off = 0;
            for (const run of runs) {
                const n = (run || []).length;
                if (n && panels[off] && panels[off + n - 1]) {
                    if (!heads.has(key(off))) heads.set(key(off), c.num);
                    if (!tails.has(key(off + n - 1))) tails.set(key(off + n - 1), c.num);
                }
                off += n;
            }
        }
        return { heads, tails };
    }

    // The panel a placement is drawn from: the record's own panel where it
    // is on the circuit, else the circuit's first (or last) panel.
    // { panel, layerId } or null.
    boxPowerAnchor(p) {
        if (!p || !p.layer) return null;
        const c = this.screenCircuits(p.layer).find(x => Number(x.num) === Number(p.at.circuit));
        if (!c || !(c.panels || []).length) return null;
        const key = p.head && p.head.rec ? p.head.rec.panel : null;
        if (key && typeof this.getScopedPanelKey === 'function') {
            for (let i = 0; i < c.panels.length; i++) {
                const on = (c.layers && c.layers[i]) || p.layer;
                if (c.panels[i] && this.getScopedPanelKey(on.id, c.panels[i]) === key) {
                    return { panel: c.panels[i], layerId: on.id };
                }
            }
        }
        const i = p.at.kind === 'end' ? c.panels.length - 1 : 0;
        return { panel: c.panels[i], layerId: ((c.layers && c.layers[i]) || p.layer).id };
    }

    // Follow every box at a circuit's start or end to its panel's circuit
    // now, or mark it `lost`. A record with no panel yet (an older file)
    // takes the one its circuit has now. A locked screen is left as it is.
    // Returns { moved, lost } (box ids) and sends the store when it wrote.
    // `say`: a toast names the boxes that lost their power.
    _boxPowerFollowPanels({ say = true } = {}) {
        const out = { moved: [], lost: [] };
        const store = this.project && this.project.boxPower;
        if (!store || typeof store !== 'object' || !Object.keys(store).length) return out;
        const layers = (this.project && this.project.layers) || [];
        const ends = new Map();
        let wrote = false;
        for (const [boxId, rec] of Object.entries(store)) {
            const at = rec && rec.at;
            if (!at || !CIRCUIT_KINDS.includes(at.kind) || rec.lost) continue;
            const layer = layers.find(l => String(l.id) === String(at.layerId));
            if (!layer || (typeof this._layerLocked === 'function' && this._layerLocked(layer))) continue;
            const kind = at.kind === 'end' ? 'end' : 'start';
            if (!rec.panel) {
                const key = this._boxPowerPanelKey(layer, at.circuit, kind);
                if (key) { store[boxId] = { ...rec, panel: key }; wrote = true; }
                continue;
            }
            if (!ends.has(layer)) ends.set(layer, this._boxPowerRunEnds(layer));
            const num = ends.get(layer)[kind === 'end' ? 'tails' : 'heads'].get(rec.panel);
            if (num === undefined) {
                store[boxId] = { ...rec, lost: true };
                out.lost.push(boxId);
                wrote = true;
            } else if (Number(num) !== Number(at.circuit)) {
                store[boxId] = { ...rec, at: { ...at, circuit: Number(num) } };
                out.moved.push(boxId);
                wrote = true;
            }
        }
        if (!wrote) return out;
        this._boxPowerMemo = null;
        this._boxPowerStandMemo = null;
        this._boxPowerCircuitIdx = null;
        if (out.moved.length || out.lost.length) sendClientLog('box_power_followed', out);
        this._persistBoxPower();
        if (say && out.lost.length && typeof this._toast === 'function') {
            this._toast(this.boxPowerLost().filter(x => out.lost.includes(x.boxId)).map(x => x.text).join(' '),
                        true, 9000);
        }
        return out;
    }

    // With a circuit cable's carry (app-power.js _cableCarryBegin): every
    // record takes its panel BEFORE the change, an older one included.
    _boxPowerCarryBegin() {
        this._boxPowerFollowPanels({ say: false });
        return true;
    }

    // ... and follows it after the change. True when a record moved or
    // lost its power.
    _boxPowerCarryApply(snap) {
        if (!snap) return false;
        const r = this._boxPowerFollowPanels();
        return !!(r.moved.length || r.lost.length);
    }

    // The boxes that lost their power when their panel stopped starting (or
    // ending) a run: [{ boxId, box, rec, layer, chained, text }], tray
    // order. `chained`: how many boxes daisy chained after it lost theirs
    // with it.
    boxPowerLost() {
        const store = this.project && this.project.boxPower;
        if (!store || typeof store !== 'object') return [];
        const out = [];
        for (const { box, card } of this.boxPowerBoxes()) {
            const rec = store[box.id];
            if (!rec || !rec.lost || !rec.at) continue;
            if (rec.cardId != null && String(rec.cardId) !== String(card.id)) continue;
            const layer = ((this.project && this.project.layers) || [])
                .find(l => String(l.id) === String(rec.at.layerId)) || null;
            let chained = 0;
            const seen = new Set([box.id]);
            for (let from = box.id, more = true; more;) {
                more = false;
                for (const [id, r] of Object.entries(store)) {
                    if (r && r.at && r.at.kind === 'chain' && r.at.from === from && !seen.has(id)) {
                        seen.add(id);
                        chained++;
                        from = id;
                        more = true;
                        break;
                    }
                }
            }
            const title = this.boxPowerTitle(box);
            const end = rec.at.kind === 'end';
            out.push({ boxId: box.id, box, rec, layer, chained,
                       text: `Breakout box ${title} has no power: the panel it was powered from no longer `
                           + `${end ? 'ends' : 'starts'} a circuit${layer ? ` on ${layer.name}` : ''}.`
                           + (chained ? ` The ${chained === 1 ? 'box' : `${chained} boxes`} daisy chained `
                               + 'after it lost theirs too.' : '')
                           + ' Power it again from the Power tab.' });
        }
        return out;
    }

    // Whether a record that does not stand is kept anyway: a box that lost
    // its power (or one chained after it), still on its card, so the
    // warning names it and powering it again brings its chain back.
    _boxPowerKeptLost(id) {
        const store = this.project && this.project.boxPower;
        const boxes = new Map(this.boxPowerBoxes().map(b => [b.box.id, b]));
        const seen = new Set();
        for (let cur = id; cur && !seen.has(cur);) {
            seen.add(cur);
            const rec = store && store[cur];
            const hit = boxes.get(cur);
            if (!rec || !rec.at || !hit) return false;
            if (rec.cardId != null && String(rec.cardId) !== String(hit.card.id)) return false;
            if (rec.at.kind !== 'chain') return !!rec.lost;
            cur = rec.at.from;
        }
        return false;
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
            if (!live.has(id) && !this._boxPowerKeptLost(id)) { delete store[id]; dropped = true; }
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

    // One power slot: a submenu of the show's boxes for spot `at`. `intro`
    // opens each entry's tip: words the box's name follows, or a function
    // of the box giving the whole sentence.
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
                title: (typeof intro === 'function' ? intro(box) : `${intro} ${title}.`)
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
        // a box that lost its power: its record can still be taken away
        const lost = !e ? this.boxPowerLost().find(x => x.boxId === boxId) : null;
        if (lost) {
            return { slots: [], items: [{
                label: 'Remove breakout box power',
                title: `${this.boxPowerTitle(lost.box)} has no power since its panel stopped `
                    + `${lost.rec.at.kind === 'end' ? 'ending' : 'starting'} a circuit. This takes its feed `
                    + 'away for good, its cable and length with it. One undoable step.',
                run: () => this.removeBoxPower(boxId),
            }] };
        }
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

    // Whether output `number` of `d` is offered to power a box straight off
    // the distro (owner, 2026-11-19): a direct output, or an output whose
    // multi already runs to a screen (its spare circuits). Never an output
    // with nothing on it, nor a multi that runs nowhere. The circuit itself
    // being free is the caller's check.
    boxPowerDistroOffered(d, number) {
        if (!d) return false;
        const fb = typeof this.faceBox === 'function' ? this.faceBox(d, number) : null;
        if (fb && fb.kind === 'direct') return true;
        const multis = typeof this._distroMultiNumbers === 'function'
            ? (this._distroMultiNumbers(d.id).get(Number(number)) || []) : [];
        const layers = (this.project && this.project.layers) || [];
        return multis.some(m => m.legs > 0 && layers.some(l => String(l.id) === String(m.layerId)
            && (l.type || 'screen') === 'screen'));
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
                    if (this.boxPowerDistroOffered(d, number)) {
                        out.slots.push(this._boxPowerSlot(`Power a breakout box from ${where}`,
                            { kind: 'distro', distroId: d.id, number, tail },
                            `${where} feeds, by itself,`));
                    } else {
                        out.items.push({ label: `Power a breakout box from ${where}`, disabled: true,
                                         title: 'A breakout box takes a direct output, or a spare circuit of '
                                             + 'a multi that already runs to a screen. Nothing runs from '
                                             + `${this.distroBoxName(d, number)} yet.` });
                    }
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
        // A circuit shared by a 2fer (or wider) starts at the first panel of
        // each of its runs: a box there is at the circuit's start, ahead of
        // its splitter (owner, 2026-11-19).
        const heads = [0];
        if (Array.isArray(c.branches) && c.branches.length > 1) {
            let off = 0;
            for (const run of c.branches) {
                if (off > 0 && off < c.panels.length) heads.push(off);
                off += (run || []).length;
            }
        }
        const first = heads.some(i => same(i));
        const last = same(c.panels.length - 1);
        const label = this.getPowerCircuitLabel(owner, c.num);
        const spot = (kind) => ({ kind, layerId: owner.id, circuit: c.num });
        const ways = Array.isArray(c.runIds) && c.runIds.length > 1 ? c.runIds.length : 1;
        if (first) {
            const plug = this.panelInput((c.layers && c.layers[0]) || owner).name;
            const to = ways > 1 ? `${label}'s ${ways}fer` : 'its panels';
            out.slots.push(this._boxPowerSlot(`Power a breakout box at the start of ${label}`, spot('start'),
                (box) => `A ${plug} 2fer at the head of ${label}: one leg to ${this.boxPowerTitle(box)}, `
                    + `the other to ${to}. The 2fer goes on the pull sheet.`));
        }
        if (first || last) {
            out.slots.push(this._boxPowerSlot(`Power a breakout box at the end of ${label}`, spot('end'),
                `The power out of ${label}'s last panel jumps to`));
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
        const p = this._boxPowerPlacementOf(box.id);
        const watts = p ? this.boxPowerWattsAt(this.boxPowerSpec(box), p.volts) : null;
        where.textContent = `From ${this.boxPowerWhereText(e)}`
            + (watts != null ? ` · ${Math.round(watts)} W` : ' · no power figure');
        wrap.appendChild(where);
        // at a circuit's start: how it is wired in, on its 2fer (the head
        // of a daisy chain only; the boxes after it hang off its thru)
        const wiring = p && p.head.box.id === box.id ? this.boxPowerStartWiring(p) : null;
        if (wiring) {
            const how = document.createElement('div');
            how.className = 'hw-box-power-where hw-box-power-wiring';
            how.textContent = `${wiring.words[0].toUpperCase()}${wiring.words.slice(1)}`;
            wrap.appendChild(how);
        }
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
