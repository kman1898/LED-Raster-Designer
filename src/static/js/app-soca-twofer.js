// app-soca-twofer: the SOCA TWO-FER (owner rulings, 2026-11-12) - a
// splitter on one Socapex output of a distro. One Socapex runs from the
// output to the splitter (its home run), and two Socapex leave it, each to
// a breakout of its own: "Can do 12 ports across 20A for two circuits
// each".
//
// THE RULINGS, in the owner's terms:
//   * PAIRED ONLY. Both legs carry all six circuits of the output, so the
//     output's six breakers feed twelve circuits: breaker N feeds circuit N
//     of leg A and circuit N of leg B.
//   * The two circuits on one breaker stay within 80% of it together (a
//     20 A breaker gives 16 A for the pair) on a US distro whose breakers
//     are not 100% rated, within the breaker on a UK or EU one: the same
//     limit every circuit on that distro packs to (_distroPackPct). The
//     breaker is the output row's own. On a distro with no output rows (an
//     older one, plugged by demand) no output carries a breaker, so the
//     pair is held to what its screens' circuits are packed to, the
//     smaller of the two (circuitCapacity - the screen's Amperage).
//     Over is a red OVER on the circuit chips and the distro, and a strip
//     line naming the pair.
//   * Right-click a Socapex output in the Power tray: Add Soca two-fer. The
//     output then shows its two legs, A and B, as one pair, the way a data
//     box shows its backup. Each leg drags onto a screen like any multi.
//     Remove Soca two-fer unplugs both legs the way Unplug multi does
//     (their typed lengths go with them) and takes the splitter away.
//   * Three lengths: the home run (output to splitter, kept on the distro)
//     and each leg's own (the leg's multi home run, as any multi keeps it).
//   * Socapex only, 208V or 120V by the output's own row; never L21-30,
//     Edison, L6-20 or a direct output.
//
// THE MODEL. `distro.twofers = { [output]: { homeRun } }`: an output with
// an entry IS a two-fer. Leg A is the output's own number, so whatever was
// on it stays on it as leg A. Leg B is the number TWOFER_LEG_B + output
// (1002 for output 2) - its own box to the naming, the sharing, the
// sticky numbers and the drags, and the same row, breakers and legs as the
// output to everything electrical (faceBox hands out the output's box under
// the leg's number). An old show has no key and nothing reads differently.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// Leg B of output N is box number TWOFER_LEG_B + N. Far past any face a
// distro can carry, so it never meets a real output's number.
export const TWOFER_LEG_B = 1000;

// The connector a two-fer rides: Socapex, on a face row; on a distro with
// no rows, its box types.
const TWOFER_FACE_CONNECTOR = 'soca';
const TWOFER_BOX_TYPES = ['soca208', 'soca120'];

class _SocaTwofer {

    // ---- the model -----------------------------------------------------------

    // The stored record of output `output` on `d`, or null.
    _twoferRecord(d, output) {
        const map = d && d.twofers;
        if (!map || typeof map !== 'object') return null;
        const rec = map[parseInt(output, 10)];
        return rec && typeof rec === 'object' ? rec : null;
    }

    // Whether box number `number` is a leg B number at all.
    isTwoferLegBNumber(number) {
        const n = parseInt(number, 10);
        return Number.isFinite(n) && n > TWOFER_LEG_B;
    }

    // The output a box number stands for: a leg B number's output, else
    // the number itself.
    twoferOutputOf(number) {
        const n = parseInt(number, 10);
        return Number.isFinite(n) && n > TWOFER_LEG_B ? n - TWOFER_LEG_B : n;
    }

    twoferLegBNumber(output) {
        return TWOFER_LEG_B + parseInt(output, 10);
    }

    // What box `number` of `d` is on a two-fer: { output, leg ('A'|'B'),
    // a, b (the two legs' numbers), rec } - or null when the output holds
    // none, or holds one no longer on a Socapex output (its row changed
    // under it: the legs are then numbers past the face, said by the
    // checks). Safe inside the naming build: it reads the record and the
    // face rows only.
    twoferOf(d, number) {
        const n = parseInt(number, 10);
        if (!d || !Number.isFinite(n) || n < 1) return null;
        const output = this.twoferOutputOf(n);
        const rec = this._twoferRecord(d, output);
        if (!rec) return null;
        const face = typeof this.distroFace === 'function' ? this.distroFace(d) : null;
        if (face) {
            const box = face.byNumber.get(output);
            if (!box || !box.conn || box.conn.id !== TWOFER_FACE_CONNECTOR || box.paired) return null;
        }
        return { output, leg: n > TWOFER_LEG_B ? 'B' : 'A', a: output,
                 b: TWOFER_LEG_B + output, rec };
    }

    // Every output of `d` that is a two-fer, ascending.
    distroTwoferOutputs(d) {
        const map = d && d.twofers;
        if (!map || typeof map !== 'object') return [];
        return Object.keys(map).map(k => parseInt(k, 10))
            .filter(n => Number.isFinite(n) && n >= 1 && this.twoferOf(d, n))
            .sort((a, b) => a - b);
    }

    // The number a box's name carries: "2A" and "2B" on a two-fer's legs,
    // else the number. Leg B reads "B" even after its splitter is gone, so
    // a stale leg is never mistaken for output 1002. The one place the
    // legs' letters are decided (owner to rule on the naming).
    distroBoxNumberText(d, number) {
        const n = parseInt(number, 10);
        if (!Number.isFinite(n)) return String(number);
        if (n > TWOFER_LEG_B) return `${n - TWOFER_LEG_B}B`;
        if (d && this._twoferRecord(d, n)) return `${n}A`;
        return String(n);
    }

    // The splitter's own name: the output's, with no leg letter ("SL2").
    twoferName(d, output) {
        const base = typeof this.distroLabel === 'function' ? this.distroLabel(d) : String(d.name || '');
        return this._deriveMultiName(base, parseInt(output, 10), null);
    }

    // Leg B's box on a face distro: output N's box under the leg's number,
    // so its size, row, breaker, coupling and legs are the output's, and
    // its circuits key to the same breakers (_facePhysical). Null when the
    // number is no live leg B.
    twoferLegBBox(d, face, number) {
        const tw = this.twoferOf(d, number);
        if (!tw || tw.leg !== 'B' || !face) return null;
        const base = face.byNumber.get(tw.output);
        if (!base) return null;
        if (!this._twoferBoxMemo) this._twoferBoxMemo = new WeakMap();
        let box = this._twoferBoxMemo.get(base);
        if (!box) {
            box = Object.assign({}, base, { number: tw.b, twoferLeg: 'B', twoferOutput: tw.output });
            this._twoferBoxMemo.set(base, box);
        }
        return box;
    }

    // Can output `number` of `d` become a two-fer: { ok, why }. Only a
    // Socapex output, 208V or 120V as its row says, never one paired with
    // another row. `quiet` callers only ask whether to offer it.
    twoferEligible(d, number) {
        const n = parseInt(number, 10);
        if (!d || !Number.isFinite(n) || n < 1 || n > TWOFER_LEG_B) {
            return { ok: false, why: 'That output no longer exists.' };
        }
        const face = this.distroFace(d);
        if (face) {
            const box = face.byNumber.get(n);
            if (!box) return { ok: false, why: `${this.distroLabel(d)} has no output ${n}.` };
            if (box.conn.id !== TWOFER_FACE_CONNECTOR) {
                return { ok: false, soca: false, why: `A two-fer splits a Socapex output, and `
                    + `${this.distroBoxName(d, n)} is ${this._aAn(box.conn.short)} ${box.conn.short}.` };
            }
            if (box.paired || face.rows.some(r => r.pairedWith === box.rowId)) {
                return { ok: false, soca: true, why: `${this.distroBoxName(d, n)} shares its circuits with `
                    + 'another row\'s connectors (paired), so it cannot also be split.' };
            }
            return { ok: true };
        }
        const typed = this.distroBoxType(d, n).type;
        if (!typed || !TWOFER_BOX_TYPES.includes(typed.id)) {
            return { ok: false, soca: false, why: `A two-fer splits a Socapex output, and `
                + `${this.distroBoxName(d, n)} is ${this._aAn(typed ? typed.name : 'box')} `
                + `${typed ? typed.name : 'box'}.` };
        }
        return { ok: true, typeId: typed.id };
    }

    // The screens on either leg of output `output`: [{ layerId, soca, ... }]
    // per leg, from the naming index.
    _twoferMembers(d, output) {
        const numbers = this._distroMultiNumbers(d.id);
        return { a: numbers.get(output) || [], b: numbers.get(TWOFER_LEG_B + output) || [] };
    }

    // ---- the gestures --------------------------------------------------------

    // Make output `number` of distro `distroId` a two-fer. Whatever is on
    // the output stays on it as leg A; leg B starts free. ONE undo step.
    // A locked screen on the output keeps its circuit names, so the add is
    // refused, naming it.
    addTwofer(distroId, number) {
        const d = this.getDistros().find(x => x.id === distroId);
        const n = parseInt(number, 10);
        if (!d) return false;
        if (this.twoferOf(d, n)) return false;
        const el = this.twoferEligible(d, n);
        if (!el.ok) {
            this._sayTwofer(el.why);
            return false;
        }
        const layers = (this.project && this.project.layers) || [];
        const onIt = (this._distroMultiNumbers(d.id).get(n) || [])
            .map(m => layers.find(l => l.id === m.layerId)).filter(Boolean);
        if (this._lockedRefused([...new Set(onIt)])) return false;
        if (!d.twofers || typeof d.twofers !== 'object') d.twofers = {};
        d.twofers[n] = { homeRun: '' };
        // A distro with no rows keeps the output's type on the box, so
        // both legs read it whatever lands on them first.
        if (el.typeId) this._stampBoxType(d.id, n, el.typeId, false);
        this._circuitTailCache = null;
        sendClientLog('soca_twofer_added', { distroId: d.id, output: n });
        this.saveState('Add Soca Two-fer');
        this._persistDistros();
        this._restateNaming();
        return true;
    }

    // Take the two-fer off output `number` (either leg's number names it):
    // every multi on both legs comes off as Unplug multi takes them off -
    // their stored programming and typed lengths with them - and the
    // splitter and its home run go. ONE undo step. A locked screen on
    // either leg refuses it whole, named.
    removeTwofer(distroId, number) {
        const d = this.getDistros().find(x => x.id === distroId);
        const tw = d ? this.twoferOf(d, number) : null;
        if (!tw) {
            // a record whose output is no longer a Socapex still goes
            const output = this.twoferOutputOf(number);
            if (!d || !this._twoferRecord(d, output)) return false;
        }
        const output = tw ? tw.output : this.twoferOutputOf(number);
        const members = this._twoferMembers(d, output);
        const all = [...members.a, ...members.b];
        const layers = (this.project && this.project.layers) || [];
        const locked = [...new Set(all.map(m => layers.find(l => l.id === m.layerId))
            .filter(l => l && this._layerLocked(l)))];
        if (this._lockedRefused(locked)) return false;
        sendClientLog('soca_twofer_removed', { distroId: d.id, output, multis: all.length });
        const forget = () => {
            // An explicit empty map, never a deleted key: a show that had
            // a two-fer says it has none.
            if (!d.twofers || typeof d.twofers !== 'object') d.twofers = {};
            delete d.twofers[output];
            this._circuitTailCache = null;
        };
        if (!all.length) {
            forget();
            this.saveState('Remove Soca Two-fer');
            this._persistDistros();
            this._restateNaming();
            return true;
        }
        // The legs' multis come off through the multi clear itself, the
        // splitter going with them before its one history entry.
        return this._clearMultis(all.map(m => ({ layerId: m.layerId, soca: m.soca })),
                                 'Remove Soca Two-fer', { also: () => { forget(); this._persistDistros(); } })
            !== false;
    }

    // The home run, output to splitter: typed like any multi's home run
    // (a length in the show's unit, the other unit converted, text that is
    // no length refused and said). ONE undo step. Not a screen's, so no
    // lock: the screens on the legs keep their circuits.
    setTwoferHomeRun(distroId, number, value) {
        const d = this.getDistros().find(x => x.id === distroId);
        const tw = d ? this.twoferOf(d, number) : null;
        if (!tw) return false;
        const v = String(value == null ? '' : value).trim();
        if (!this.readTypedLength(v, 'home run').ok) return false;
        const read = this.parseTypedCableLength(v);
        const stored = read.n !== null ? String(read.n) : '';
        if (String(tw.rec.homeRun || '') === stored) return false;
        tw.rec.homeRun = stored;
        this.saveState('Set Two-fer Home Run');
        this._persistDistros();
        return true;
    }

    // The home run as a length (null when none is typed).
    twoferHomeRunFt(d, output) {
        const rec = this._twoferRecord(d, output);
        return rec ? this.parseCableLength(rec.homeRun) : null;
    }

    _sayTwofer(text) {
        if (typeof this._toast === 'function') this._toast(text, true);
        if (typeof this._dockSay === 'function') this._dockSay(text);
    }

    // ---- the load on each breaker --------------------------------------------

    // Every breaker of every two-fer on `d` with a circuit on it: [{
    // distro, output, tail, breakerA, pct, limitA, amps, over, holders:
    // [{ layer, leg, circuit, label, amps }], keys ("layerId:circuit") }],
    // by output then breaker. A hidden screen is left out, as from every
    // distro check. The limit is the breaker the output row carries times
    // the packing % of the distro (80% US unless its breakers are 100%
    // rated, the breaker itself UK/EU); on a distro with no rows, what the
    // pair's screens pack a circuit to, the smaller.
    twoferPairs(d) {
        const outputs = this.distroTwoferOutputs(d);
        if (!outputs.length) return [];
        const face = this.distroFace(d);
        const sys = typeof this.distroSystem === 'function' ? this.distroSystem(d) : null;
        const own = typeof this._distroPackPct === 'function' ? this._distroPackPct(d) : null;
        const pct = own === null ? (sys && sys.region === 'us' && !d.breakers100 ? 0.8 : 1) : own;
        const by = new Map();
        for (const layer of (this.project && this.project.layers) || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            // hidden as the user left it (the binder hides screens for a
            // moment while it draws one: _screenHidden reads through that)
            if (typeof this._screenHidden === 'function' ? this._screenHidden(layer)
                : layer.visible === false) continue;
            const assign = layer.powerSocaDistro || {};
            for (const s of this.getSocaPlan(layer)) {
                if (assign[s.soca] !== d.id) continue;
                const tw = this.twoferOf(d, s.number);
                if (!tw) continue;
                const capA = s.spec ? s.spec.breakerA * this.circuitCapacity(layer).pct
                    : this.circuitCapacity(layer).amps;
                for (const leg of s.legs) {
                    const key = `${tw.output}:${leg.leg}`;
                    let rec = by.get(key);
                    if (!rec) {
                        const box = face ? face.byNumber.get(tw.output) : null;
                        const breakerA = box ? Number(box.breakerA) || 0 : 0;
                        rec = { distro: d, output: tw.output, tail: leg.leg, breakerA, pct,
                                limitA: breakerA > 0 ? breakerA * pct : Infinity,
                                amps: 0, over: false, holders: [], keys: [] };
                        by.set(key, rec);
                    }
                    if (!face && capA > 0) rec.limitA = Math.min(rec.limitA, capA);
                    rec.amps += Number(leg.amps) || 0;
                    rec.holders.push({ layer, leg: tw.leg, circuit: leg.circuit,
                                       label: leg.label, amps: Number(leg.amps) || 0 });
                    rec.keys.push(`${layer.id}:${leg.circuit}`);
                }
            }
        }
        const out = [...by.values()].filter(r => Number.isFinite(r.limitA));
        out.forEach(r => {
            r.holders.sort((a, b) => (a.leg < b.leg ? -1 : a.leg > b.leg ? 1 : 0));
            r.over = r.amps > r.limitA + 1e-9;
            r.text = this.twoferPairText(r);
        });
        return out.sort((a, b) => (a.output - b.output) || (a.tail - b.tail));
    }

    // The over pairs of every distro (or of `d`).
    twoferOverChecks(d = null) {
        const list = d ? [d] : (this.getDistros() || []);
        return list.flatMap(x => this.twoferPairs(x).filter(r => r.over));
    }

    // "SL2A-3 + SL2B-3 share SL2's 20 A breaker 3 on the Soca two-fer:
    // 17.4 A, over the 80% continuous limit (16 A)."
    twoferPairText(r) {
        const labels = r.holders.map(h => h.label).join(' + ');
        const amps = `${r.amps.toFixed(1)} A`;
        const lim = +r.limitA.toFixed(1);
        const name = this.twoferName(r.distro, r.output);
        const brk = r.breakerA > 0 ? `${+r.breakerA.toFixed(1)} A breaker ${r.tail}` : `breaker ${r.tail}`;
        const sys = typeof this.distroSystem === 'function' ? this.distroSystem(r.distro) : null;
        const limit = r.breakerA > 0
            ? (sys && sys.region === 'us' && r.pct < 1
                ? `over the 80% continuous limit (${lim} A)` : `over the breaker (${lim} A)`)
            : `over the ${lim} A its circuits are packed to`;
        return `${labels} share ${name}'s ${brk} on the Soca two-fer: ${amps}, ${limit}.`;
    }

    // ---- the right-click ------------------------------------------------------

    // "Add Soca two-fer" on a Socapex output's box in the Power tray, and
    // "Remove Soca two-fer" on a two-fer, either leg or the pair's own
    // header. Null anywhere else, and on an output that is not a Socapex
    // (no offer at all there).
    _prepareTwoferMenu(x, y) {
        const el = document.elementFromPoint(x, y);
        if (!el || !el.closest || !el.closest('#hardware-dock')) return null;
        const payload = typeof this._dockChipPayload === 'function' ? this._dockChipPayload(el) : null;
        if (!payload || (payload.type !== 'slot' && payload.type !== 'twofer')) return null;
        const d = this.getDistros().find(x2 => x2.id === payload.distroId);
        if (!d) return null;
        const n = parseInt(payload.number, 10);
        const tw = this.twoferOf(d, n);
        if (tw || (payload.type === 'twofer' && this._twoferRecord(d, this.twoferOutputOf(n)))) {
            const output = tw ? tw.output : this.twoferOutputOf(n);
            const name = this.twoferName(d, output);
            const m = this._twoferMembers(d, output);
            const multis = m.a.length + m.b.length;
            return {
                label: 'Remove Soca two-fer',
                title: `Take the two-fer off ${name}.`
                    + (multis ? ' Both legs are unplugged, the way Unplug multi does it: '
                        + 'their circuits, names and lengths go with them.' : '')
                    + ' Its home run goes too. One undoable step.',
                run: () => this.removeTwofer(d.id, output),
            };
        }
        if (payload.type !== 'slot' || this.isTwoferLegBNumber(n)) return null;
        const el2 = this.twoferEligible(d, n);
        // never offered on an output that is not a Socapex
        if (!el2.ok && el2.soca === false) return null;
        if (!el2.ok) return { label: 'Add Soca two-fer', disabled: true, title: el2.why };
        const name = this.distroBoxName(d, n);
        return {
            label: 'Add Soca two-fer',
            title: `Split ${name} into two Socapex, leg A and leg B, each to its own `
                + 'breakout. Circuit N of both legs shares breaker N, and the pair stays '
                + 'within its limit together. Whatever is on it now stays on leg A. '
                + 'One undoable step.',
            run: () => this.addTwofer(d.id, n),
        };
    }

    // ---- the Power tray -------------------------------------------------------

    // One two-fer in the tray: ONE strip framed like a data box and its
    // backup, its header the splitter (its name, the two legs, a gold
    // "two-fer" tag, the circuits in use of twelve and the home run
    // length), and the two legs as its rows - each the multi box it is,
    // dragged, named, measured and cleared like any other.
    _dockBuildTwofer(d, output, inUse) {
        const tw = this.twoferOf(d, output);
        const strip = document.createElement('div');
        strip.className = 'hw-dock-loop hw-dock-twofer';
        strip.dataset.lrdTwofer = `${d.id}-${output}`;
        const name = this.twoferName(d, output);
        const a = inUse.get(tw.a) || [];
        const b = inUse.get(tw.b) || [];
        const used = [...a, ...b].reduce((t, m) => t + (m.legs || 0), 0);
        const pairs = this.twoferPairs(d).filter(r => r.output === output);
        const over = pairs.filter(r => r.over);
        const head = document.createElement('div');
        head.className = 'hw-dock-head-row hw-dock-twofer-head';
        // what the right-click reads (_prepareTwoferMenu); the strip itself
        // drags nothing - each leg drags as its own multi
        head.dataset.hwdockPayload = JSON.stringify({
            type: 'twofer', distroId: d.id, number: output, title: `${name} two-fer` });
        const label = document.createElement('span');
        label.className = 'hw-dock-unit-name';
        label.textContent = name;
        head.appendChild(label);
        const names = document.createElement('span');
        names.className = 'hw-dock-loop-names';
        names.textContent = `${this.distroBoxName(d, tw.a)} + ${this.distroBoxName(d, tw.b)}`;
        head.appendChild(names);
        const tag = document.createElement('span');
        tag.className = 'hw-dock-redpill hw-dock-looptag';
        tag.textContent = 'two-fer';
        tag.title = `${name} is a Soca two-fer: one Socapex from ${this.distroLabel(d)} to the `
            + 'splitter, and two leaving it, leg A and leg B, each to its own breakout. '
            + 'Circuit N of both legs is on breaker N. Right-click to remove it.';
        head.appendChild(tag);
        const use = document.createElement('span');
        use.className = 'hw-dock-unit-use' + (over.length ? ' hw-dock-unit-use-over' : '');
        use.textContent = `${used}/12`;
        use.title = `${used} of the twelve circuits in use, six on each leg.`;
        head.appendChild(use);
        if (over.length) {
            const flag = document.createElement('span');
            flag.className = 'hw-dock-unit-flag';
            flag.dataset.lrdTwoferOver = `${d.id}-${output}`;
            flag.textContent = 'OVER';
            flag.title = over.map(r => r.text).join(' ');
            head.appendChild(flag);
        }
        const len = this._dockHeadName({
            value: tw.rec.homeRun || '',
            placeholder: this.cableUnit() === 'm' ? '30m' : '100ft',
            key: `twofer-home-run-${d.id}-${output}`,
            title: `The home run from ${this.distroLabel(d)} to the two-fer, one Socapex. `
                + 'Each leg\'s own length is on its row.'
                + this.cableStockHint(tw.rec.homeRun, 'multi'),
            onCommit: (val) => {
                if (this.setTwoferHomeRun(d.id, output, val)) this.renderHardwareDock();
            },
        });
        len.classList.add('hw-dock-name-len');
        head.appendChild(len);
        head.title = `${name}: a Soca two-fer. Drag leg A or leg B onto a circuit like any multi. `
            + 'Right-click for Remove Soca two-fer.';
        strip.appendChild(head);
        const body = this._dockSectionBody(strip, head, `hwdock-twofer-${d.id}-${output}`);
        const legA = this._dockBuildMulti(d, tw.a, a);
        legA.classList.add('hw-dock-loop-row');
        const legB = this._dockBuildMulti(d, tw.b, b);
        legB.classList.add('hw-dock-loop-row', 'hw-dock-loop-far');
        body.appendChild(legA);
        body.appendChild(legB);
        return strip;
    }
}

for (const k of Object.getOwnPropertyNames(_SocaTwofer.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_SocaTwofer.prototype, k));
    }
}
