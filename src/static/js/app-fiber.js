// app-fiber: the show's fiber cables and a breakout box's links onto them.
//
// "tac is just for stranded fiber" (owner, 2026-09-25). The fiber that
// feeds a box is a CABLE the show owns - project.fiberCables = [{ id, name,
// kind, strands, ft, connector, labels, subunits, strandNames }] - and
// each of the box's trunk links takes strands of one:
// box.fiberLinks = { p1: { cable, strands: [1, 2] }, b1: {…} }.
//   * a TAC or an MTP (its own kind: "if i choose mtp 12 choose that") has
//     any number of strands and is SHARED - several boxes take different
//     strands of one cable;
//   * an opticalCON DUO (2 fibers) or QUAD (4) is shared the same way
//     (owner, 2026-10-08): a QUAD feeds two XD inputs or four BiDi links,
//     a DUO one XD input or two BiDi links;
//   * a link takes 2 strands, 1 on a box switched to BiDi;
//   * a link on an XD may be COPPER instead - { copper: 'Cat6A',
//     ft } - with no cable and no strands (owner: "anything that does
//     10Gbps max length is allowed. Cat 6A and under");
//   * a link is named by the box's own port (X1 / X2, OPT 1-4, else Link
//     1..) - the resolved box's linkTitles;
//   * a processor's BACKUP UNIT (an option on the processor) feeds the
//     same boxes on their documented backup inputs: such a box gains the
//     links b1..bK (X2, OPT 2, OPT 3-4), each with its own cable;
//   * a loop's two boxes (an SX40's XD A and B, a NovaStar backupOf pair)
//     are two boxes with their own links, SHOWN together as a pair.
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

// A FIBER EXTENSION (owner, 2026-11-02: "MTP cant run direct to X1 for
// example it would need an extension beyond that"): the cable between a
// TAC's or an MTP's end and the box's own port, at the box end only, per
// link - link.extension = { kind, trunkEnd?, boxEnd?, ft? } (the server's
// processor_catalog.FIBER_EXTENSION_KINDS has the rules). Its ends are
// offered from the fiber connector list of the 2026-09-25 ruling, and any
// other may be typed; a trunk end left blank reads the trunk's own.
export const FIBER_EXTENSION_KINDS = [['fanout', 'Fan-out'], ['patch', 'Duplex patch']];
export const FIBER_EXTENSION_CONNECTORS = ['ST', 'LC duplex', 'opticalCON DUO', 'opticalCON QUAD', 'MTP / MPO'];

// Copper on an XD link, each kind with its 10G maximum in feet: Cat6A 60 m
// and Cat5e 30 m are Brompton's, Cat6 100 ft the owner's. The meter
// figures are converted exactly (60 m = 196.85 ft, 30 m = 98.43 ft); they
// used to be floored to the foot, so a 98.4 ft Cat5e run was warned. The
// server's twin is processor_catalog.COPPER_LINK_KINDS, written the same
// way; a test pins that they agree.
const FT_PER_M = 1 / 0.3048;
export const COPPER_LINK_KINDS = [['Cat6A', 60 * FT_PER_M], ['Cat6', 100], ['Cat5e', 30 * FT_PER_M]];
// The same maxima in a meters show (2026-10-16): Brompton's own 60 m and
// 30 m, and the owner's 100 ft exactly (30.48 m).
export const COPPER_LINK_KINDS_M = [['Cat6A', 60], ['Cat6', 30.48], ['Cat5e', 30]];

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
        const ft = this.parseCableLength(cable.ft);
        if (ft !== null) parts.push(this.pullLengthText(ft));
        if (cable.kind === 'tac' && String(cable.connector || '').trim()) {
            parts.push(String(cable.connector).trim());
        }
        return parts.join(' · ');
    }

    // ---- extensions at the box end ----------------------------------------

    // The connector a trunk ends in, as an extension's trunk end reads it
    // when none is typed: a TAC's own ends ('' where it names none), an
    // MTP's MTP / MPO, an opticalCON its own.
    fiberCableEndText(cable) {
        if (!cable) return '';
        if (cable.kind === 'tac') return String(cable.connector || '').trim();
        return { mtp: 'MTP / MPO', 'opticalcon-duo': 'opticalCON DUO',
                 'opticalcon-quad': 'opticalCON QUAD' }[cable.kind] || '';
    }

    fiberExtensionKindWord(kind) {
        const hit = FIBER_EXTENSION_KINDS.find(([k]) => k === kind);
        return hit ? hit[1] : 'Extension';
    }

    // A link's extension, or null: one rides a TAC or an MTP only.
    fiberLinkExtension(l) {
        const ext = l && l.link && l.link.extension;
        return ext && l.cable && this.fiberCableIsStranded(l.cable) ? ext : null;
    }

    // Its two ends as they read: the trunk end typed, else the trunk's own.
    fiberExtensionEnds(ext, cable) {
        const typed = String((ext && ext.trunkEnd) || '').trim();
        return { trunk: typed || this.fiberCableEndText(cable),
                 box: String((ext && ext.boxEnd) || '').trim() };
    }

    // "MTP / MPO to LC duplex" - '' where neither end is named.
    fiberExtensionPathText(ext, cable) {
        const { trunk, box } = this.fiberExtensionEnds(ext, cable);
        if (trunk && box) return `${trunk} to ${box}`;
        if (trunk) return `from ${trunk}`;
        return box ? `to ${box}` : '';
    }

    // The pull sheet's type for it: "Fan-out · MTP / MPO to LC duplex".
    // Two extensions of one kind, ends and length are one row, counted.
    fiberExtensionType(ext, cable) {
        const path = this.fiberExtensionPathText(ext, cable);
        return this.fiberExtensionKindWord(ext && ext.kind) + (path ? ` · ${path}` : '');
    }

    // The whole of it in one line, the length or "no length" last: "Fan-out ·
    // MTP / MPO to LC duplex · 10'".
    fiberExtensionText(ext, cable) {
        const ft = this.parseCableLength(ext && ext.ft);
        return `${this.fiberExtensionType(ext, cable)} · `
            + (Number.isFinite(ft) && ft > 0 ? this.pullLengthText(ft) : 'no length');
    }

    // A link by the box's own port name - "X1", "OPT 3" - off the
    // resolved box's linkTitles; "Link 1" where the box documents none.
    fiberLinkTitle(key, box) {
        const k = String(key || '');
        const named = box && box.linkTitles && box.linkTitles[k];
        if (named) return named;
        return `${k.startsWith('b') ? 'Backup' : 'Link'} ${k.slice(1)}`;
    }

    copperLinkMaxFt(kind) {
        const hit = COPPER_LINK_KINDS.find(([k]) => k === kind);
        return hit ? hit[1] : null;
    }

    // A kind's 10G maximum in the show's unit (a copper link's length is
    // typed in it, like every cable's).
    copperLinkMax(kind) {
        if (this.cableUnit() !== 'm') return this.copperLinkMaxFt(kind);
        const hit = COPPER_LINK_KINDS_M.find(([k]) => k === kind);
        return hit ? hit[1] : null;
    }

    // The plain warning a copper link past its kind's 10G length wears,
    // on the row and in the binder: "Cat6 runs 100 ft max at 10G" ("Cat6
    // runs 30.48 m max at 10G" in a meters show). '' within it, or with
    // no length.
    copperOverText(copper) {
        const max = copper ? this.copperLinkMax(copper.copper) : null;
        const ft = this.parseCableLength(copper && copper.ft);
        if (!max || !Number.isFinite(ft) || ft <= max) return '';
        return `${copper.copper} runs ${this.copperLinkMaxWords(max)} max at 10G`;
    }

    // A 10G maximum as words, never rounded UP past the real limit: feet
    // print to the tenth and meters to the centimeter, floored, so the
    // figure said is always a length that fits ("196.8 ft" for Cat6A's
    // 196.85, "98.4 ft" for Cat5e's 98.43; "100 ft", "30.48 m").
    copperLinkMaxWords(max) {
        const step = this.cableUnitAbbr() === 'm' ? 100 : 10;
        return this.cableLengthWords(Math.floor(max * step + 1e-9) / step);
    }

    // Every resolved box, in tray order: [{ box, proc, card }]. A card
    // cabled to its processor on links of its own - a QD-S's IN 1 / IN 2
    // (card.linkHost) - is one more, ahead of its boxes, with `box` the
    // card itself: its links read, list and pull exactly as a box's do.
    _fiberAllBoxes() {
        const out = [];
        for (const proc of this._processorsResolved || []) {
            for (const slot of (proc && proc.slots) || []) {
                const card = slot && slot.card;
                if (!card) continue;
                if (card.linkHost) out.push({ box: card, proc, card });
                for (const box of card.cvts || []) if (box) out.push({ box, proc, card });
            }
        }
        return out;
    }

    fiberBoxById(id) {
        const hit = this._fiberAllBoxes().find(b => b.box.id === id);
        return hit ? hit.box : null;
    }

    // The box's links in order - its primaries (X1, OPT 1-2 ...), then
    // the backup inputs (X2, OPT 3-4 ...) its processor's backup unit
    // feeds: [{ key, title, backup, link, cable, copper, box }].
    // `copper` is the copper link as stored ({ copper, ft }), else null.
    fiberBoxLinks(box) {
        const host = box || null;
        if (!host) return [];
        const links = host.fiberLinks || {};
        return (host.fiberLinkKeys || []).map(key => {
            const link = links[key] || null;
            const copper = link && link.copper ? link : null;
            return { key, title: this.fiberLinkTitle(key, host), backup: key.startsWith('b'),
                     link, copper, box: host,
                     cable: link && !copper ? this.getFiberCable(link.cable) : null };
        });
    }

    // Whether any link of the box (its host's) has a cable or copper - the
    // moment a 1.3 typed note stops printing.
    fiberBoxHasLink(box) {
        return this.fiberBoxLinks(box).some(l => l.cable || l.copper);
    }

    // A loop's two boxes, in trunk order, where `box` is one of them: the
    // near box (an SX40's XD A) and the far one its strings loop back into
    // (XD B, `backupOf` the near box - a NovaStar in-unit backup box the
    // same way). Two boxes with their own links, shown TOGETHER (owner,
    // 2026-09-25: "loops are seperate boxes yes but really they are paired
    // so keeping them together when looped makes sense"). null where the
    // box is in no loop.
    fiberLoopPair(box) {
        if (!box) return null;
        if (box.backupOf) {
            const near = this.fiberBoxById(box.backupOf);
            return near ? { near, far: box } : null;
        }
        const far = this._fiberAllBoxes().map(b => b.box)
            .find(b => b.backupOf === box.id);
        return far ? { near: box, far } : null;
    }

    // A BACKUP BOUND PORT BY PORT (owner, 2026-11-02: "pair port by
    // port"). A box on a copy OPT set to Backup whose OPTs are not its
    // primary's - a CVT4K-S on OPT 5-6 behind two CVT10s, two CVT10s on
    // OPT 5 and 6 behind one CVT4K-S - backs up the same port numbers on
    // whichever primary boxes carry them. The server says which, socket by
    // socket: `backsUpPorts` on the backup box ({ number, socket, boxId,
    // local }), `backedUpBy` on each primary. A port with no box on its
    // primary OPT is the unit's own Ethernet port (boxId null - owner,
    // 2026-11-02: "you could use 16 ports on processor and then opt 3/4
    // for 16 ports of backup/copy"), and the card lists those backups as
    // `ownBackedUpBy`. A one-to-one pair keeps `backupOf` and reads as
    // before; this is true only past it.
    boxLoopMixed(box) {
        return !!(box && !box.backupOf && (box.backsUpPorts || []).length);
    }

    // A backup box's sockets as the tray and its sheet show them. Port by
    // port, each reads the box's own silkscreen number (the standing
    // silkscreen rule wins, owner 2026-11-02: a CVT10 behind ports 11-16
    // shows 1-6), `loopOf` saying which primary box (null: the unit's own
    // port) and that box's own number for the port it backs up. `mainId` keeps the sockets backing
    // one primary box (null: the unit's own ports); left out, all of them.
    // A one-to-one pair keeps its sockets as they are. Any other box: its
    // ports.
    boxLoopPorts(box, mainId) {
        const map = (box && box.backsUpPorts) || [];
        if (!map.length) return (box && box.ports) || [];
        const mixed = this.boxLoopMixed(box);
        const byNumber = new Map((box.ports || []).map(p => [p.number, p]));
        const out = [];
        for (const m of map) {
            if (mainId !== undefined && (m.boxId || null) !== mainId) continue;
            const port = byNumber.get(m.number);
            if (!port) continue;
            out.push(!mixed ? port : { ...port, localNumber: m.socket,
                loopOf: { boxId: m.boxId || null, local: m.local, socket: m.socket } });
        }
        return out;
    }

    // The port-by-port backups behind one primary box (`near` null: the
    // unit's own ports), each with the sockets backing it, in the card's
    // order: [{ box, ports }]. A one-to-one partner is not one of them.
    boxLoopSlices(near, cvts) {
        const id = near ? near.id : null;
        return (cvts || []).filter(b => b !== near && (b.backsUpPorts || []).length
                && (this.boxLoopMixed(b) || !near)
                && b.backsUpPorts.some(m => (m.boxId || null) === id))
            .map(b => ({ box: b, ports: this.boxLoopPorts(b, id) }));
    }

    // What a port-by-port backup backs up, per primary box: "loop of CVT10
    // A 1-10, CVT10 B 1-6 on sockets 11-16" - the primary's own numbers,
    // and this box's own sockets for them where they differ. '' on any
    // other box. `titleOf` names a box the way the reader's sheet does.
    boxLoopText(box, cvts, titleOf) {
        const own = (box && box.backsUpPorts || []).some(m => !m.boxId);
        if (!this.boxLoopMixed(box) && !own) return '';
        const groups = new Map();
        for (const m of box.backsUpPorts) {
            if (box.backupOf && m.boxId) continue;
            if (!groups.has(m.boxId)) groups.set(m.boxId, { locals: [], numbers: [] });
            groups.get(m.boxId).locals.push(m.local);
            groups.get(m.boxId).numbers.push(m.socket);
        }
        const parts = [...groups].map(([id, g]) => {
            const main = (cvts || []).find(b => b.id === id);
            const mine = this.fiberStrandRangeText(g.locals);
            const shown = this.fiberStrandRangeText(g.numbers);
            return `${id ? (main ? titleOf(main) : 'its primary') : 'own ports'} ${mine}`
                + (shown !== mine ? ` on sockets ${shown}` : '');
        });
        return `loop of ${parts.join(', ')}`;
    }

    // Every box looped with `box`, one-to-one or port by port, on its own
    // card: the primaries (`nears`) and their backups (`fars`), each in the
    // card's order. A CVT4K-S on OPT 5-6 behind CVT10s on OPT 1 and 2 is
    // one group of three. null where the box is in no loop.
    fiberLoopGroup(box) {
        if (!box) return null;
        const hit = this._fiberAllBoxes().find(b => b.box.id === box.id);
        const cvts = (hit && hit.card && hit.card.cvts) || [];
        const backs = (b) => [b.backupOf, ...(b.backsUpPorts || []).map(m => m.boxId)]
            .filter(Boolean);
        const seen = new Set([box.id]);
        const queue = [box];
        while (queue.length) {
            const b = queue.shift();
            for (const o of cvts) {
                if (seen.has(o.id)) continue;
                if (backs(b).includes(o.id) || backs(o).includes(b.id)) {
                    seen.add(o.id);
                    queue.push(o);
                }
            }
        }
        if (seen.size < 2) return null;
        const members = cvts.filter(b => seen.has(b.id));
        return { nears: members.filter(b => !backs(b).length),
                 fars: members.filter(b => backs(b).length) };
    }

    // Every strand of one cable some link holds: Map strand -> { box, key }.
    fiberStrandUsers(cableId) {
        const used = new Map();
        for (const { box } of this._fiberAllBoxes()) {
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

    // Port names as one run: ["OPT 3", "OPT 4"] -> "OPT 3-4", ["X2"] ->
    // "X2"; names that do not run are listed.
    fiberPortRunText(names) {
        const parts = names.map(n => String(n).match(/^(.*?)(\d+)$/));
        if (names.length > 1 && parts.every(Boolean)
                && parts.every(m => m[1] === parts[0][1])
                && parts.every((m, i) => i === 0 || Number(m[2]) === Number(parts[i - 1][2]) + 1)) {
            return `${parts[0][1]}${parts[0][2]}-${parts[parts.length - 1][2]}`;
        }
        return names.join(', ');
    }

    // The box's links as one line: "X1 TAC A (TAC 8) 1-2 · X2 TAC A 3-4" -
    // each cable once per side, its strands as runs, EVERY input under its
    // port name, and the first mention of a named cable carrying what it is
    // in brackets (owner, 2026-09-26: "i see no mention of X1 and on the
    // data pages i see no mention of Tac 8"). A copper link reads by its
    // port too, "X1 Cat6A 150'", with the plain warning where it runs past
    // its 10G length. '' where nothing is set.
    fiberLinkSummary(box) {
        return this.fiberLinkInputs(box).map(i => i.text).join(' · ');
    }

    // The same links one input at a time, in the order the summary says
    // them, for a sheet that lays each strand out on its own (the binder's
    // data-sheet band and Breakout boxes table): a fiber input is
    //   { text: 'X1 TAC A (TAC 8) 1-2', head: 'X1 TAC A (TAC 8)', cable, strands: [1, 2] }
    // - `head` the summary's words before the strands, `strands` in
    // order - and a copper one { text: "X1 Cat6A 150'" } alone.
    fiberLinkInputs(box) {
        const sides = { p: new Map(), b: new Map() };
        for (const l of this.fiberBoxLinks(box)) {
            const side = l.backup ? sides.b : sides.p;
            if (l.copper) {
                side.set(`cu:${l.key}`, { copper: l.copper, titles: [l.title] });
                continue;
            }
            if (!l.cable) continue;
            const got = side.get(l.cable.id) || { cable: l.cable, strands: [], titles: [] };
            got.strands.push(...(l.link.strands || []));
            got.titles.push(l.title);
            side.set(l.cable.id, got);
        }
        const typed = new Set();
        const say = (m) => [...m.values()].map(({ cable, copper, strands, titles }) => {
            if (copper) {
                const ft = this.parseCableLength(copper.ft);
                const over = this.copperOverText(copper);
                return { text: [titles[0], copper.copper,
                                Number.isFinite(ft) && ft > 0 ? this.pullLengthText(ft) : '']
                    .filter(Boolean).join(' ') + (over ? ` (${over})` : '') };
            }
            let what = cable.name || this.fiberCableTypeText(cable);
            if (cable.name && !typed.has(cable.id)) {
                const kind = this.fiberCableIsStranded(cable)
                    ? `${this.fiberKindWord(cable.kind)} ${cable.strands}`
                    : this.fiberKindWord(cable.kind);
                what += ` (${kind})`;
            }
            typed.add(cable.id);
            const head = `${this.fiberPortRunText(titles)} ${what}`;
            const list = [...new Set(strands.map(Number))].filter(Number.isFinite).sort((a, b) => a - b);
            return { text: `${head} ${this.fiberStrandRangeText(strands)}`, head, cable, strands: list };
        });
        return [...say(sides.p), ...say(sides.b)];
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
        if (found) return `/api/processors/${found.proc.id}/cvts/${box.id}`;
        // A link-host card (a QD-S) takes its links at its card's URL.
        const card = box.linkHost && typeof this._dockFindCard === 'function'
            ? this._dockFindCard(box.id) : null;
        return card ? `/api/processors/${card.proc.id}/cards/${box.id}` : null;
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

    // A link's extension: {} adds one, the keys sent change it, null
    // removes it - one request, one history entry.
    setFiberExtension(box, key, body, action = 'Set Fiber Extension') {
        return this.setFiberLink(box, key, { extension: body }, action);
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
