// app-fiber: the show's fiber cables and a breakout box's links onto them.
//
// "tac is just for stranded fiber" (owner, 2026-09-25). The fiber that
// feeds a box is a CABLE the show owns - project.fiberCables = [{ id, name,
// kind, strands, ft, connector, labels, subunits, strandNames,
// ownerBoxId }] - and each of the box's trunk links takes strands of one:
// box.fiberLinks = { p1: { cable, strands: [1, 2] }, b1: {…} }.
//   * a TAC or an MTP (its own kind: "if i choose mtp 12 choose that") has
//     any number of strands and is SHARED - several boxes take different
//     strands of one cable;
//   * an opticalCON DUO (2 fibers) or QUAD (4) is ONE box's (ownerBoxId);
//   * a link takes 2 strands, 1 on a box switched to BiDi;
//   * a backup record BOUND to its primary (boundTo - the same physical box
//     taking a second fiber) has no links of its own: its backup links b1..
//     bK live on the primary.
// The server owns every rule (processor_catalog's fiber-cable section) and
// refuses with the reason; this side reads the resolved boxes and the
// show's list, names the strands, and writes one request per gesture.
import { LEDRasterApp } from './app-core.js';

// TIA-598-D, in order, with the swatch the app paints for each. The
// server's twin is processor_catalog.FIBER_COLORS.
export const FIBER_COLORS = [
    ['Blue', '#1F5FA8'], ['Orange', '#F28020'], ['Green', '#1A9A48'],
    ['Brown', '#7A4A2E'], ['Slate', '#777777'], ['White', '#F5F5F5'],
    ['Red', '#B82535'], ['Black', '#1A1A1A'], ['Yellow', '#EDD31C'],
    ['Violet', '#7A3F9E'], ['Rose', '#E09BA8'], ['Aqua', '#5EBFC2'],
];

// What the New TAC / New MTP step offers; any count may be typed.
export const FIBER_STRAND_SUGGESTIONS = [4, 6, 8, 12, 24, 48];
// A TAC's ends, offered; free text is taken too. An MTP names none.
export const TAC_CONNECTORS = ['ST', 'LC duplex'];

// One strand as the paper says it - the ONE JS implementation, pinned
// against processor_catalog.fiber_strand_name by a test. Blue..Aqua for
// 1-12; past 12 the colors repeat with a black tracer ("14 Orange/Black";
// the Black strand takes a WHITE one, "20 Black/White"), then a double
// ("26 Orange/Black x2"), a triple, and on. Sub-units read "Orange unit · 2
// Orange"; a cable in numbers reads "14"; a typed rename wins.
export function fiberStrandName(n, cable) {
    const c = cable || {};
    const num = parseInt(n, 10);
    const typed = ((c.strandNames || {})[String(num)] || '');
    if (typeof typed === 'string' && typed.trim()) return typed.trim();
    if (!Number.isFinite(num) || num < 1) return String(n);
    if (c.labels === 'numbers') return String(num);
    const color = FIBER_COLORS[(num - 1) % 12][0];
    if (c.subunits) {
        const unit = FIBER_COLORS[(Math.ceil(num / 12) - 1) % 12][0];
        return `${unit} unit · ${((num - 1) % 12) + 1} ${color}`;
    }
    const tier = Math.floor((num - 1) / 12);
    if (tier === 0) return `${num} ${color}`;
    const tracer = color === 'Black' ? 'White' : 'Black';
    return `${num} ${color}/${tracer}` + (tier > 1 ? ` x${tier}` : '');
}

// The swatch a strand wears: its color, and the tracer stripe past 12 (none
// in sub-units, where the strand's own color is plain).
export function fiberStrandSwatch(n, cable) {
    const c = cable || {};
    const num = parseInt(n, 10);
    if (!Number.isFinite(num) || num < 1) return { base: '#777777', tracer: null };
    const [name, base] = FIBER_COLORS[(num - 1) % 12];
    const tier = Math.floor((num - 1) / 12);
    if (c.subunits || tier === 0) return { base, tracer: null };
    return { base, tracer: name === 'Black' ? '#F5F5F5' : '#1A1A1A' };
}

class _Fiber {
    getFiberCables() {
        return (this.project && this.project.fiberCables) || [];
    }

    getFiberCable(id) {
        return this.getFiberCables().find(c => c && c.id === id) || null;
    }

    fiberStrandName(n, cable) {
        return fiberStrandName(n, cable);
    }

    fiberStrandSwatch(n, cable) {
        return fiberStrandSwatch(n, cable);
    }

    // Whether a cable takes a strand count of the user's (TAC, MTP) or has
    // the connector's (opticalCON).
    fiberCableIsStranded(cable) {
        return !!cable && (cable.kind === 'tac' || cable.kind === 'mtp');
    }

    fiberKindWord(kind) {
        return { tac: 'TAC', mtp: 'MTP', 'opticalcon-duo': 'opticalCON DUO',
                 'opticalcon-quad': 'opticalCON QUAD' }[kind] || 'Fiber';
    }

    // The pull sheet's words, and the binder's: "TAC 12 · ST", "MTP 24",
    // "opticalCON QUAD" - the kind and its strand count, a TAC's ends.
    fiberCableTypeText(cable) {
        if (!cable) return '';
        if (!this.fiberCableIsStranded(cable)) return this.fiberKindWord(cable.kind);
        const conn = cable.kind === 'tac' ? String(cable.connector || '').trim() : '';
        return `${this.fiberKindWord(cable.kind)} ${cable.strands}` + (conn ? ` · ${conn}` : '');
    }

    // The cable as a picker lists it: "TAC A · 12 · 1000' · ST", "MTP A ·
    // 12 · 300'", "QUAD 1 · 50'".
    fiberCableOptionText(cable) {
        if (!cable) return '';
        const parts = [cable.name || this.fiberKindWord(cable.kind)];
        if (this.fiberCableIsStranded(cable)) parts.push(String(cable.strands));
        const ft = Number(cable.ft);
        if (Number.isFinite(ft) && ft > 0) parts.push(this.pullLengthText(ft));
        if (cable.kind === 'tac' && String(cable.connector || '').trim()) {
            parts.push(String(cable.connector).trim());
        }
        return parts.join(' · ');
    }

    fiberLinkTitle(key) {
        const k = String(key || '');
        return `${k.startsWith('b') ? 'Backup' : 'Primary'} ${k.slice(1)}`;
    }

    // Every resolved box, in tray order: [{ box, proc, card }].
    _fiberAllBoxes() {
        const out = [];
        for (const proc of this._processorsResolved || []) {
            for (const slot of (proc && proc.slots) || []) {
                const card = slot && slot.card;
                if (!card) continue;
                for (const box of card.cvts || []) if (box) out.push({ box, proc, card });
            }
        }
        return out;
    }

    fiberBoxById(id) {
        const hit = this._fiberAllBoxes().find(b => b.box.id === id);
        return hit ? hit.box : null;
    }

    // The record a box's fiber is set on: its primary where it is a bound
    // backup (the same physical box), else itself.
    fiberHostBox(box) {
        if (box && box.boundTo) return this.fiberBoxById(box.boundTo) || box;
        return box || null;
    }

    // The host's links in order - Primary 1..K, then Backup 1..K where a
    // backup is bound: [{ key, title, backup, link, cable }].
    fiberBoxLinks(box) {
        const host = this.fiberHostBox(box);
        if (!host) return [];
        const links = host.fiberLinks || {};
        return (host.fiberLinkKeys || []).map(key => {
            const link = links[key] || null;
            return { key, title: this.fiberLinkTitle(key), backup: key.startsWith('b'),
                     link, cable: link ? this.getFiberCable(link.cable) : null };
        });
    }

    // Whether any link of the box (its host's) has a cable - the moment a
    // 1.3 typed note stops printing.
    fiberBoxHasLink(box) {
        return this.fiberBoxLinks(box).some(l => l.cable);
    }

    // Every strand of one cable some link holds: Map strand -> { box, key }.
    fiberStrandUsers(cableId) {
        const used = new Map();
        for (const { box } of this._fiberAllBoxes()) {
            if (box.boundTo) continue;
            for (const [key, link] of Object.entries(box.fiberLinks || {})) {
                if (!link || link.cable !== cableId) continue;
                (link.strands || []).forEach(s => { if (!used.has(s)) used.set(s, { box, key }); });
            }
        }
        return used;
    }

    // "1-4", "1-2, 5", "3" - strands as runs.
    fiberStrandRangeText(strands) {
        const list = [...new Set((strands || []).map(Number))].filter(Number.isFinite).sort((a, b) => a - b);
        const out = [];
        let i = 0;
        while (i < list.length) {
            let j = i;
            while (j + 1 < list.length && list[j + 1] === list[j] + 1) j++;
            out.push(j > i ? `${list[i]}-${list[j]}` : String(list[i]));
            i = j + 1;
        }
        return out.join(', ');
    }

    // The box's links as one line: "TAC A 1-4 · backup TAC B 1-4" - each
    // cable once per side, its strands as runs. '' where nothing is set.
    // (What a TAC A is - its kind, count, ends - is its strand map's header.)
    fiberLinkSummary(box) {
        const sides = { p: new Map(), b: new Map() };
        for (const l of this.fiberBoxLinks(box)) {
            if (!l.cable) continue;
            const side = l.backup ? sides.b : sides.p;
            const got = side.get(l.cable.id) || { cable: l.cable, strands: [] };
            got.strands.push(...(l.link.strands || []));
            side.set(l.cable.id, got);
        }
        const say = (m, word) => [...m.values()].map(({ cable, strands }) =>
            `${word}${cable.name || this.fiberCableTypeText(cable)} ${this.fiberStrandRangeText(strands)}`);
        return [...say(sides.p, ''), ...say(sides.b, 'backup ')].join(' · ');
    }

    // A 1.3 box's typed fiber, kept as a NOTE: "12 Tac Fiber 250'", the type
    // alone where no length was typed, '' where nothing was.
    fiberLegacyNote(box) {
        if (!box) return '';
        const full = typeof this.pullBoxFiberText === 'function' ? this.pullBoxFiberText(box) : '';
        if (full) return full;
        return String(box.fiberType || '').trim();
    }

    // The URL of a box's own routes, from its id.
    _fiberBoxUrl(box) {
        const found = typeof this._dockFindCvt === 'function' ? this._dockFindCvt(box.id) : null;
        return found ? `/api/processors/${found.proc.id}/cvts/${box.id}` : null;
    }

    // ---- writes: one request per gesture, one history entry ----------------

    createFiberCable(body, action = 'New Fiber Cable') {
        return this._processorRequest('/api/fiber-cables', 'POST', body, action);
    }

    setFiberCable(cableId, body, action = 'Edit Fiber Cable') {
        return this._processorRequest(`/api/fiber-cables/${cableId}`, 'PUT', body, action);
    }

    setFiberLink(box, key, body, action = 'Set Fiber Link') {
        const url = this._fiberBoxUrl(box);
        if (!url) return Promise.resolve();
        return this._processorRequest(`${url}/fiber-links/${key}`, 'PUT', body, action);
    }

    setBoxFiber(box, body, action = 'Set Box Fiber') {
        const url = this._fiberBoxUrl(box);
        if (!url) return Promise.resolve();
        return this._processorRequest(`${url}/fiber`, 'PUT', body, action);
    }
}

for (const k of Object.getOwnPropertyNames(_Fiber.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Fiber.prototype, k));
    }
}
