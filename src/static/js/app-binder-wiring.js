// app-binder-wiring: the WIRING sheets - a screen's POWER WIRING sheet right
// behind its Power sheet, its DATA WIRING sheet right behind its Data sheet
// (2026-09-08, on the last page of a client's packet: "he gave an example
// his binder and we could do this for power and data drawing from a port to
// port … the last page is what i was talking about").
//
// ONE SIDE, ONE SHEET. They began as one "Signal + Power" sheet, signal
// over power, each side half a page tall - and a big screen and its blocks
// were squeezed into it (2026-09-12: "when the screens get too big we will
// need to split the pages. or better yet we just should split them up").
// Now each side has the whole drawing area, and the set runs grouped by
// system: 2.1 SR · POWER, 2.2 SR · POWER WIRING, 2.3 SR · DATA, 2.4 SR ·
// DATA WIRING. A screen with no circuits has no Power sheet and so no
// Power Wiring sheet; the same for data. The sheet's own title names the
// side, so no SIGNAL / POWER head is drawn over it, and the reader's word
// is "data" - the side keeps its internal id `signal` in the log only.
//
// THE DRAWING IS THE PROTOTYPE'S. mocks/wiring-proto.html draws this
// picture from two real shows' own facts and is what was approved
// (2026-09-09: "those are fantastic", "that is much more legible", "that
// looks great") - casing on, fade off, the printer palette for the press.
// Every number below is in the prototype's page units (it is 1000 wide)
// and the sheet scales them by K = its drawing area's width / 1000, so it
// carries that drawing across whatever size the paper is. The wall is
// sized by the room the sheet leaves it and nothing else - the
// prototype's MAX_WALL_H, a bound for an SVG page of no fixed height,
// would have held a whole-page wall to the height of the old half.
//
// The side, top to bottom (the code and the log still call it a "half"):
//
//   the WALL      - the same _bMap render the Power / Data sheets use
//                   (the data-flow view on data, the power view on
//                   power), rulers and brackets off. THE WALL'S OWN LABEL DISCS ARE THE
//                   ORIGIN: no second tag is drawn on it - an earlier
//                   attempt hung rounded tags off the panels and they
//                   covered the wall. The disc's place and size are the
//                   renderer's own (its panel's centre, shifted inside
//                   the screen by its radius), read here so a run can
//                   leave its edge.
//   the BLOCKS    - flat units spread across the width, EACH ON THE SIDE
//                   OF THE WALL ITS OWN POINTS ARE ON: over the wall
//                   where its ports or circuits start on the top edge,
//                   under it where they start on the foot, and as close
//                   to the wall as its lanes allow (2026-10-18: "it makes
//                   more sense to put the breakouts up top right?", "as
//                   close as the y can be to the ports"). Their sockets
//                   in a row and THEIR NAME INSIDE on its own line on the
//                   far side of the numbers from the wall - a run comes
//                   into its socket from the wall's side, and on the line
//                   it crosses the run's white casing ate the letters -
//                   ordered by the mean position of their own runs. Signal: one per device the screen's port ends
//                   land on ("CVT4K-S SR A · Card 1 · OPT 1-2", or the
//                   card itself where no unit delivers the port); a
//                   backup is its own block ("one per cvt including
//                   backups"). Power: one per multi the circuits are on -
//                   its BREAKOUT, the fan out ("there are no boxes... it
//                   is a breakout also known as a fan out"): "SR1 · Multi
//                   208 breakout · 125'". The home run is the caption's
//                   length, not a wire.
//   the RUNS      - OUT OF THE WALL AND ROUND IT. A run leaves its disc
//                   by the nearest edge whose way out is clear of the
//                   map's own lettering - a side by preference, the top
//                   or the foot where both sides are blocked - and from
//                   there travels in the CLEAR SPACE round the wall: along
//                   a rail past the wall's edge, along a lane by the edge
//                   its box stands on (or across one by the other edge),
//                   and into its socket. Where the socket already stands
//                   outside the wall on the side the run leaves by, the
//                   rail IS the drop and two segments suffice - which is
//                   the drawing that was approved. Nothing but that one
//                   stub is ever inside the wall, so a run can cover no
//                   disc, no cable tag, no gang pill, no band and none of
//                   the screen's own arrows.
//
// A SOCKET'S NOTE earns its place only when it says something the socket
// number does not: "SR A-3" against socket 3 of the block called SR A is
// pure repetition, and repeating it widened the blocks until the pair
// wrapped to a second row whose runs then crossed the first. A shared
// multi keeps the other screen's name against its socket, and the pitch
// is measured from the widest note that survives.
//
// THE PITCH GIVES WAY BEFORE THE LAYOUT DOES. Wrapping to a second row of
// blocks puts that row's runs across the first, so the socket pitch
// shrinks - never below its floor, never below what a surviving note
// needs - until every block fits one row.
//
// THE FAULT THIS REPLACED, on the user's own export (rev 1.3, page 4, DJ
// BOOTH): the label discs sit at the ENDS of a 9 x 2 wall's rows and the
// blocks under its middle, so every run left its disc and travelled the
// whole width of the wall along the INSIDE of its own row - straight
// through that port's own "25'" cable tag, over the screen's daisy-chain
// arrows - and then turned down through the second row. On page 7 the same
// fault ate a letter: "IMAG SR-6" printed "IMAG R-6", the S taken by the
// white casing of the run leaving it. "We still have lines going over text
// labels, and where the heck are these lines ending?"; "extensions
// shouldnt be covered either". The old ESCAPE - a step out past the wall's
// near edge for a run that would otherwise drop through the discs under it
// - is not a special case any more: going round the wall is what every run
// now does, and a run already outside and above its socket still drops
// straight in.
//
// THE CASING. Every run is drawn twice: a white stroke ~3 units wider
// underneath, then the run itself. That is what makes a line read where
// it crosses the wall's dark panels, and it matters more on the printer
// page than in colour.
//
// COLOUR: a hue per breakout on power - its rim, its sockets, its runs,
// and a ring of that hue around its own discs on the wall (the wall's
// discs are the renderer's, so the hue is carried to them as a rim
// rather than by repainting them). On data, the screen's own primary and
// backup inks, the same the discs wear, a return dashed. PRINTER: no
// colour at all - the runs are black and told apart by a dash pattern per
// device; on data a primary is solid into a filled socket and a return
// finely dashed into a hollow one; the wall's greys and its white discs
// with black rims are the renderer's printer mode.
//
// A stub on no card draws its disc and no run, and the sheet prints
// "n of m not placed on any card" once.
//
// Everything is drawn in page units through the recorder, so the PDF gets
// the sheet as vector; circles are short polylines and the casing is
// simply the same path stroked white first (the recorder knows rects,
// lines, text and images, nothing else).
//
// One view per sheet: "n  SR - MAIN · DATA WIRING · FRONT VIEW", its
// bubble at the foot, the view named as the map sheet names it. Every
// figure is read from the same authorities the Power and Data sheets
// read - _pullPortRuns, _bPortHome,
// getPortLabelText, the pull list's byScreen units, screenCircuits,
// getDistroOutputTypes; nothing is recomputed here.
import { LEDRasterApp } from './app-core.js';
import { BINDER_STYLE } from './app-binder.js';

const { INK, MUTED, BUBBLE_H } = BINDER_STYLE;

// The wall takes the whole of the room it is given: this sheet draws no
// rulers and no brackets, and the discs are the renderer's own, inside it.
const GUT = { left: 0, right: 0, top: 0, bottom: 0 };

// ---- the prototype's page, in its own units (it is 1000 wide) -----------
const PROTO_W = 1000;
const MARGIN = 22;
// The wall's height is held to what rev 1.1 drew it at, even on a page of its
// own. Grown to fill the page, the wall spread under its own blocks and the
// runs to them had to go round it - 55 crossings on live show B's SR - MAIN
// power became 73, and the fans that used to leave at their row and drop
// straight into the socket below had to travel. The user, shown both:
// "The original way we had it was the best" (2026-09-12).
//
// That height is now where the wall STARTS, not where it must stop. On a
// sheet whose runs all come out of the wall's foot it left a band of
// empty paper over the wall, and the wall printed far smaller than on its
// own Data sheet - the owner, 2026-10-18: "there is a ton of vertical space
// it could fill". So the wall grows from there towards the whole of its
// room - the lanes over its head, the lanes under its foot and the blocks
// keep the room they need - for as long as the runs read no worse: no run
// that dropped straight has to travel, none takes a rail it did not, and
// no two runs cross that did not (_bwPlanHalf, `grown`).
const MAX_WALL_H = 360;
// The steps the wall's growth is searched in (halvings past the first try):
// six take it to within a sixty-fourth of the room the runs allow.
const GROW_STEPS = 6;
const FOOT_PAD = 6;              // the air under the last block row
const FOOT_LINE = 14;            // and the "not placed" line's own room
// The rails: the room outside the wall the sideways runs and the escape
// need, so a wide wall never leaves them nowhere to travel.
const RAIL_BASE = 16, RAIL_GAP = 12, RAIL_MAX = 190;
// The blocks: the socket disc, the pitch between sockets and its floor,
// the block's padding, its height, the gaps, its corner.
const SOCK = 10, PITCH = 32, MIN_PITCH = 21, PAD = 15;
const BOX_H = 60, MIN_BOX_GAP = 16, ROW_GAP = 38, BOX_R = 7;
// The name sits UNDER the numbers. A run comes down into its socket
// from above, so anything on the line above the sockets is crossed -
// and the run's white casing was eating the letters, on the printer
// sheet taking the very digit that tells SR3 from SR1. Below the
// sockets nothing crosses it. A box OVER the wall is the same box turned
// over - its runs come up into it - so there the name's baseline stands
// TOP_TITLE_DY under the box's head and the sockets SOCKET_DY over its foot.
const TITLE_DY = 50, NOTE_DY = 13, SOCKET_DY = 26, TOP_TITLE_DY = 18;
const CAPTION_SZ = 10, NUMBER_SZ = 8, NOTE_SZ = 7.5, NOTE_PAD = 8;
// A breakout box's INPUTS on the data side (owner, 2026-10-17: "X1 and X2
// can go under the numbers in wiring diagram"; 2026-10-18: "they dont need
// to be stacked"; 2026-11-05, of the row beside the name: "the right two
// are smaller and the left two are bigger. i like the smaller look"): each
// input a group - "X1", the cable it is on, then its strands, each
// strand's swatch where the cable reads in colours - in the thin outline
// the Breakout boxes table groups an input in, set at the caption's size,
// the groups side by side on their own line directly under the caption,
// never beside it, so no box is wider than its sockets, its caption and
// that line need. Names too long for one line take a line per group
// (_bwPlanHalf says when), and the box grows by its lines - every box on
// the sheet alike, so a row stays one height. Its type, the pitch of a
// line, the swatch, the outline's pad and the gap between two groups.
const IN_SZ = CAPTION_SZ, IN_LINE = 16, IN_SW = 9, IN_PAD = 3, IN_GAP = 6;
// The runs: their pen, the white casing under them, the rims.
const RUN_W = 1.4, CASE_EXTRA = 3.2;
const BOX_RIM = 1.8, SOCKET_RIM = 1.3, DISC_RIM = 1.6;
// The way round the wall: how far past its edge the first rail stands,
// how far apart two rails stand, and the room one lane wants - a lane is
// the run's pen and its casing, and a little white either side of them.
const RAIL_OUT = 12, RAIL_STEP = 7, LANE_STEP = 6;
// A run whose socket is this close to its own column drops straight.
const STRAIGHT = 1.2;

// A hue per breakout; a dash per device where the press has no hue.
const HUES = ['#c2410c', '#0f766e', '#6d28d9', '#a16207',
              '#b91c1c', '#1d4ed8', '#4d7c0f', '#9d174d'];
const DASHES = [[], [9, 5], [2, 5], [13, 5, 2, 5], [18, 6], [1, 6], [6, 4, 1, 4], [22, 7]];
const RETURN_DASH = [6, 4];              // a return in colour
const PRINTER_RETURN_DASH = [3, 4];      // a return on the press
const GREY_RING = '#aaaaaa';
const GREY_INK = '#999999';
const WHITE = '#ffffff';

class _BinderWiring {

    // ---- the sheet ----------------------------------------------------------

    // One side's WIRING sheet: one numbered view, the side on the whole
    // drawing area. `sides` = { power, data } names the ONE side this sheet
    // draws - the caller asks once per side, and only for a side the screen
    // has and the dialog's Maps choice wants; anything else draws no sheet.
    // `target` is a screen or a sheet subject (_bSubject, app-binder.js): a
    // grouped wall printed as its group wires every member on one sheet
    // under the group's name; a member printed by screens wires the runs
    // and circuits landing on its own cabinets (2026-10-01).
    _bWiringPage(book, target, pos, sides) {
        const power = !!(sides && sides.power), data = !!(sides && sides.data);
        if (power === data) return;
        const subject = this._bSubject(target);
        const layer = subject.layers[0];
        const side = power ? 'power' : 'signal';
        const scr = book.list.byScreen[layer.id] || {};
        const title = `${subject.name} - ${power ? 'Power' : 'Data'} Wiring`;
        // the side the wall is drawn from, named as its map sheet names it
        const sheetTitle = `${subject.name} · ${power ? 'POWER' : 'DATA'} WIRING · ${this._bViewName(book).toUpperCase()}`;
        // the VIEW BAND over it (the frame banded while it is laid out and
        // painted, app-binder.js _bViewBandGeo), and the wiring laid out in
        // its room less the stage line at its foot (_bLessStageLine)
        const band = this._bBandSide(book);
        const frame = book.geo;
        book.geo = this._bViewBandGeo(frame, band);
        const area = this._bwArea(book);
        const room = this._bLessStageLine(area.half);
        const plan = this._bwPlanHalf(book, subject, scr, side, room);
        const view = ++book.views;
        this._bPage(book, {
            kind: 'wiring', title, sheetTitle, viewName: sheetTitle, view,
            layerId: subject.id, subject: subject.name, position: pos ? pos.name : null,
            ...(subject.groupId != null ? { groupId: subject.groupId, layerIds: subject.layers.map(l => l.id) } : {}),
            layout: 'wiring', cols: 1, scale: plan.K,
            sides: { power, data },
            halves: [{ side: plan.side, scale: plan.K, rows: plan.rows,
                       discs: plan.discs.length, runs: plan.runs.length,
                       blocks: plan.blocks.length, unplaced: plan.unplaced }],
        }, () => {
            if (book.log) book.log.wiring = { halves: [] };
            const geo = this._bwDrawHalf(book, subject, plan);
            this._bStageLine(book, band, geo && geo.wall, room, room.y + room.h);
            this._bViewBubble(book, view, sheetTitle, book.geo.da.x + 20, area.bubbleY, null, book.geo.da.w - 20);
        });
        book.geo = frame;
    }

    // The drawing area for the one side: all of it but the bubble's room
    // at the foot.
    _bwArea(book) {
        const da = book.geo.da;
        return { half: { x: da.x, y: da.y, w: da.w, h: da.h - BUBBLE_H },
                 bubbleY: da.y + da.h - BUBBLE_H + 12 };
    }

    // ---- the facts ----------------------------------------------------------

    // The signal half's facts: a stub per port end, the devices the ends
    // land on in the order the ports meet them, a wire per landed end.
    //   stubs:   [{ kind: 'primary'|'return', text, panel, port }]
    //   devices: [{ key, title, n, sockets: Map(n -> 'primary'|'return'), notes: Map }]
    //   wires:   [{ stub, device, socket, kind }]
    // Each stub carries the screen its panel is on (`layer`), which places
    // its disc on a sheet drawing more than one.
    _bwSignalFacts(book, target) {
        const subject = this._bSubject(target);
        const asgOf = (l) => ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(l.id));
        const runs = this._bSubjectRuns(subject);
        const devices = [];
        const byKey = new Map();
        const device = (home) => {
            const key = home.box ? 'cvt:' + home.box.id : 'card:' + home.card.id;
            let d = byKey.get(key);
            if (!d) {
                // The unit named ONCE and its model said once beside it -
                // _bPortHome's unitTitle, the very string the Data sheet's
                // band carries. A card going by Card N carries no model:
                // the model is said where gear is pulled.
                const title = home.box
                    ? [this._bBoxTitle(home.box), home.cardTitle, home.box.trunkTitle || ''].filter(Boolean).join(' · ')
                    : [home.unitTitle, home.named && !home.slotNamed ? home.card.deviceName : ''].filter(Boolean).join(' · ');
                const n = home.box
                    ? (home.box.portCount || (home.box.ports || []).length)
                    : (home.card.ceiling || (home.card.ports || []).length);
                d = { key, title, n: Number(n) || 0, sockets: new Map(), notes: new Map(),
                      box: home.box || null };
                byKey.set(key, d);
                devices.push(d);
            }
            return d;
        };
        const stubs = [], wires = [];
        for (const { carrier, run } of runs) {
            // the run's cabinets this sheet draws, each with its screen
            const own = [];
            (run.panels || []).forEach((p, i) => {
                if (!p || p.hidden) return;
                const on = (run.layers && run.layers[i]) || carrier;
                const drawn = subject.kind === 'group'
                    ? subject.layers.some(l => this._bSameLayer(l, on))
                    : this._bSameLayer(on, subject.member || carrier);
                if (drawn) own.push({ p, on });
            });
            if (!own.length) continue;
            const asg = asgOf(carrier);
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const home = placed && placed.cardId ? this._bPortHome(placed.cardId, placed.port) : null;
            const primary = { kind: 'primary', text: run.label, panel: own[0].p, layer: own[0].on, port: run.num };
            stubs.push(primary);
            if (!home) continue;
            const d = device(home);
            const socket = home.port && home.port.localNumber != null
                ? Number(home.port.localNumber) : parseInt(placed.port, 10);
            d.sockets.set(socket, 'primary');
            wires.push({ stub: primary, device: d, socket, kind: 'primary' });
            const bb = home.port && home.port.backedBy;
            if (!bb) continue;
            const last = own[own.length - 1];
            const ret = { kind: 'return', text: this.getPortLabelText(carrier, run.num, 'return'),
                          panel: last.p, layer: last.on, port: run.num };
            stubs.push(ret);
            const bh = bb.cardId ? this._bPortHome(bb.cardId, bb.port, bb.cvtId || null) : null;
            if (!bh) continue;
            const bd = device(bh);
            const bsock = bb.localPort != null ? Number(bb.localPort)
                : (bh.port && bh.port.localNumber != null ? Number(bh.port.localNumber) : parseInt(bb.port, 10));
            bd.sockets.set(bsock, 'return');
            wires.push({ stub: ret, device: bd, socket: bsock, kind: 'return' });
        }
        return { stubs, devices, wires };
    }

    // The power half's facts: a stub per circuit ON its first panel,
    // a BREAKOUT block per multi the screen's circuits are on (its slots as
    // sockets; a slot another screen uses on a shared multi noted with
    // that screen's name), a wire per circuit.
    _bwPowerFacts(book, target, scr) {
        const subject = this._bSubject(target);
        const layer = subject.layers[0];
        const circuitsOf = new Map();
        const byNumOf = (carrier) => {
            if (!circuitsOf.has(carrier)) {
                const list = (typeof this.screenCircuits === 'function') ? this.screenCircuits(carrier) : [];
                circuitsOf.set(carrier, new Map(list.map(c => [c.num, c])));
            }
            return circuitsOf.get(carrier);
        };
        // a circuit's cabinets this sheet draws, each with its screen
        const own = (c, carrier) => {
            const out = [];
            (c.panels || []).forEach((p, i) => {
                if (!p || p.hidden) return;
                const on = (c.layers && c.layers[i]) || carrier;
                const drawn = subject.kind === 'group'
                    ? subject.layers.some(l => this._bSameLayer(l, on))
                    : this._bSameLayer(on, subject.member || layer);
                if (drawn) out.push({ p, on });
            });
            return out;
        };
        const types = (typeof this.getDistroOutputTypes === 'function') ? this.getDistroOutputTypes() : [];
        const devices = [], stubs = [], wires = [];
        // a group's members can share a multi: one breakout per multi
        const byKey = new Map();
        const units = subject.kind === 'layer'
            ? (scr.boxes || []).map(box => ({ carrier: layer, box }))
            : this._bSubjectBoxes(book, subject);
        const sheetIds = new Set(subject.members.map(m => String(m.id)));
        for (const { carrier, box } of units) {
            if (byKey.has(box.key)) {
                const d = byKey.get(box.key);
                for (const c of box.circuits || []) this._bwPowerWire(d, c, byNumOf(carrier).get(c.num), carrier, own, stubs, wires);
                continue;
            }
            const t = types.find(x => x.id === box.typeId) || null;
            const tails = (box.circuits || []).map(c => Number(c.tail) || 0);
            // A face box (1.5) is as big as its connector - a direct output
            // one socket, an L21-30 three.
            const slots = box.boxSize && String(box.typeId || '').startsWith('face:')
                ? box.boxSize : (t ? (Number(t.boxSize) || 6) : Math.max(6, ...tails));
            // "SR1 · Multi 208 powerCON breakout · 125'"; a multi on no
            // distro has no type to name its breakout by and reads as the
            // band does (_bBoxTypeText). A DIRECT output is its own cable,
            // no breakout: "SL5 · Edison → TRUE1 · 25'". A direct output
            // carrying several circuits (the flagged error state) has no
            // one cable: its length is the output's home run, and the
            // caption says it is crowded.
            const crowd = box.crowded || 0;
            // an overfull multi box, as the pull sheet notes it
            const ovf = box.overfull && typeof this._fanWord === 'function' ? box.overfull : null;
            const caption = [box.name,
                             this._bBoxTypeText(box),
                             box.homeRun ? this.pullLengthText(box.homeRun, this.pullHomeRunKind(box)) : 'no length',
                             ...(crowd ? [`${crowd} circuits on a one-circuit output`] : []),
                             ...(ovf ? [`${ovf.circuits} circuits on a ${this._fanWord(ovf.size)}-circuit output`] : [])]
                .join(' · ');
            const d = { key: box.key, title: caption, n: slots, sockets: new Map(), notes: new Map() };
            if (box.distroId) {
                for (const [id, other] of Object.entries(book.list.byScreen)) {
                    if (sheetIds.has(String(id))) continue;
                    for (const ob of other.boxes || []) {
                        if (ob.key !== box.key) continue;
                        for (const oc of ob.circuits || []) {
                            const k = Number(oc.tail);
                            if (!d.sockets.has(k)) { d.sockets.set(k, 'other'); d.notes.set(k, other.name); }
                        }
                    }
                }
            }
            devices.push(d);
            byKey.set(box.key, d);
            for (const c of box.circuits || []) this._bwPowerWire(d, c, byNumOf(carrier).get(c.num), carrier, own, stubs, wires);
        }
        // A breakout box powered from a circuit (app-box-power.js): a block
        // of its own, its chain in the caption, its one inlet wired to the
        // circuit's disc (a box at the end: to the run's last panel) - "XD
        // SR A · breakout box at the start · 10' TRUE1 · on a TRUE1 2fer,
        // other leg to the panels".
        if (typeof this.boxPowerPlacements === 'function') {
            const carriers = new Set(units.map(u => String(u.carrier.id)));
            for (const p of this.boxPowerPlacements()) {
                if (!p.layer || !carriers.has(String(p.layer.id)) || !this.boxPowerShown(p)) continue;
                const circuit = byNumOf(p.layer).get(Number(p.at.circuit));
                // the caption is the box's own words (app-box-power.js)
                const head = p.head.box.id;
                const d = { key: `bp:${head}`, title: this.boxPowerWiringCaption(p), n: 1,
                            sockets: new Map([[1, 'power']]), notes: new Map() };
                devices.push(d);
                if (!circuit || !(circuit.panels || []).length) continue;
                // the box's own cabinet across the whole wall (the
                // circuit's first, or its last for the end), wired only
                // where this sheet draws it
                const i = p.at.kind === 'end' ? circuit.panels.length - 1 : 0;
                // the box's own panel (boxPowerAnchor), else the circuit's end
                const own0 = typeof this.boxPowerAnchor === 'function' ? this.boxPowerAnchor(p) : null;
                const anchor = (own0 && own0.panel) || circuit.panels[i];
                const end = p.at.kind === 'end' && anchor !== circuit.panels[0];
                const pick = own(circuit, p.layer).find(x => x.p === anchor);
                if (!pick) continue;
                // A box at the END is fed from the run's last panel, not the
                // circuit's label (owner, 2026-11-19): its stub is that
                // panel (`end`), never seated on the label's disc
                // (_bwSeat), and drawn as a dot there. (A box whose
                // panel is the circuit's first leaves the label's disc.)
                const stub = { kind: 'power', text: this.getPowerCircuitLabel(p.layer, p.at.circuit),
                               panel: pick.p, layer: pick.on, circuit: Number(p.at.circuit),
                               ...(end ? { end: true } : {}) };
                stubs.push(stub);
                wires.push({ stub, device: d, socket: 1, kind: 'power' });
            }
        }
        return { stubs, devices, wires };
    }

    // One circuit onto its breakout: its socket taken, and a stub and a
    // wire where the sheet draws any of its cabinets.
    _bwPowerWire(d, c, circuit, carrier, own, stubs, wires) {
        const k = Number(c.tail);
        d.sockets.set(k, 'power');
        d.notes.delete(k);
        const panels = circuit ? own(circuit, carrier) : [];
        if (!panels.length) return;
        const stub = { kind: 'power', text: c.label, panel: panels[0].p, layer: panels[0].on, circuit: c.num };
        stubs.push(stub);
        wires.push({ stub, device: d, socket: k, kind: 'power' });
    }

    // ---- the wall's own discs -----------------------------------------------

    // What the renderer needs to place a label disc on this view: the
    // label's own size, the natural radius its site gives it, its text
    // padding, and the bounds a disc is shifted inside. Read from the very
    // fields renderDataFlowArrows / renderPowerArrows read, so the disc
    // this sheet aims at is the disc the wall draws.
    // `boundsOf(screen)` is the screen a disc stands on, for a sheet that
    // draws more than one.
    _bwDiscRule(layer, side) {
        const r = window.canvasRenderer || null;
        const boundsOf = (l) => (r && typeof r.getLayerBounds === 'function' ? r.getLayerBounds(l) : null);
        const bounds = boundsOf(layer);
        const family = (typeof this.getProjectFont === 'function') ? this.getProjectFont() : 'Arial';
        if (side === 'signal') {
            const size = layer.dataFlowLabelSize || 30;
            return { r, bounds, boundsOf, family, size, minRadius: size * 1.2, padding: Math.max(4, size * 0.2) };
        }
        const size = layer.powerLabelSize || 14;
        const pen = Math.max(1, Math.round(layer.powerLineWidth || 8));
        return { r, bounds, boundsOf, family, size,
                 minRadius: Math.max(size * 0.7, pen * 1.4), padding: Math.max(6, size * 0.25) };
    }

    // One label disc, in page units: its radius the renderer's own
    // (_layoutCircleLabel, measured on the dry context so nothing on the
    // page is disturbed), its centre the panel's centre shifted inside the
    // screen by that radius, both carried onto the sheet through the map's
    // own rect(). A renderer that cannot be asked falls back to a third of
    // the panel.
    // `point`: no label stands there (a box fed from a run's last panel):
    // a dot of a sixth of the panel at its centre.
    _bwDisc(book, rule, geo, panel, text, onLayer = null, point = false) {
        const p = panel;
        let rad = Math.min(p.width, p.height) / (point ? 6 : 3);
        if (!point && rule.r && typeof rule.r._layoutCircleLabel === 'function') {
            const saved = rule.r.ctx;
            try {
                rule.r.ctx = book.measureCtx;
                book.measureCtx.font = `bold ${rule.size}px ${rule.family}`;
                const out = rule.r._layoutCircleLabel(String(text), rule.size, rule.minRadius, rule.padding);
                if (out && Number.isFinite(out.radius)) rad = out.radius;
            } catch (_) { /* the fallback stands */ } finally { rule.r.ctx = saved; }
        }
        let cx = p.x + p.width / 2, cy = p.y + p.height / 2;
        const b = onLayer && rule.boundsOf ? rule.boundsOf(onLayer) : rule.bounds;
        if (b && b.width > 2 * rad) cx = Math.min(Math.max(cx, b.x + rad), b.x + b.width - rad);
        if (b && b.height > 2 * rad) cy = Math.min(Math.max(cy, b.y + rad), b.y + b.height - rad);
        const on = onLayer || undefined;
        const rc = geo ? geo.rect(cx - rad, cy - rad, 2 * rad, 2 * rad, on)
                       : { x: cx, y: cy, w: 0, h: 0 };
        const pr = geo ? geo.rect(p.x, p.y, p.width, p.height, on) : { x: cx, y: cy, w: 0, h: 0 };
        return { x: rc.x + rc.w / 2, y: rc.y + rc.h / 2, r: rc.w / 2,
                 panel: { x: pr.x, y: pr.y, w: pr.w, h: pr.h } };
    }

    // ---- the way out of the wall --------------------------------------------

    // The one crossing of the wall a run is allowed: straight from its own
    // disc's edge to one of the wall's four edges. `off` slides the start
    // round the disc, across the way it leaves by - a ruler's leg label
    // sits directly over the disc of the circuit whose column it names, and
    // a run leaving a hair to one side of the disc's middle is past it and
    // still on the disc it belongs to. `at` is the row (or the column) the
    // run then travels on; `gap` is how much wall it has to cross, negative
    // where the disc already hangs over that edge.
    _bwStub(d, edge, wall, off) {
        const t = Math.max(-0.95, Math.min(0.95, off || 0)) * d.r;
        const s = Math.sqrt(Math.max(0, d.r * d.r - t * t));
        if (edge === 'left') return { head: [d.x - s, d.y + t], out: [wall.x, d.y + t],
                                      at: d.y + t, gap: (d.x - s) - wall.x };
        if (edge === 'right') return { head: [d.x + s, d.y + t], out: [wall.x + wall.w, d.y + t],
                                       at: d.y + t, gap: (wall.x + wall.w) - (d.x + s) };
        if (edge === 'top') return { head: [d.x + t, d.y - s], out: [d.x + t, wall.y],
                                     at: d.x + t, gap: (d.y - s) - wall.y };
        return { head: [d.x + t, d.y + s], out: [d.x + t, wall.y + wall.h],
                 at: d.x + t, gap: (wall.y + wall.h) - (d.y + s) };
    }

    // What a mark of this footprint costs in the map's own lettering, its
    // own disc apart: nothing where it is clear, and otherwise a price per
    // kind. Covering a NEIGHBOUR'S DISC is the fault the user saw - "IMAG
    // SR-6" printed "IMAG R-6" - and a cable tag or a gang pill is a figure
    // he needs ("extensions shouldnt be covered either"); a thin line across
    // a multi band or a ruler leg is the least of them. The boxes are the
    // ones canvas.js's label registry recorded for this very render.
    _bwCost(a, b, pad, labels, own) {
        const PRICE = { disc: 1000, tag: 120, gang: 120, band: 30, rulerLabel: 10, rulerTick: 3 };
        const x0 = Math.min(a[0], b[0]) - pad, x1 = Math.max(a[0], b[0]) + pad;
        const y0 = Math.min(a[1], b[1]) - pad, y1 = Math.max(a[1], b[1]) + pad;
        // a HAIR of overlap is a rounding artefact of a rim's half width,
        // not ink on ink - the same reading tests/test_map_label_collisions
        // takes of the map against itself
        const HAIR = 0.5;
        let cost = 0;
        for (const k of labels) {
            if (k === own) continue;
            if (Math.min(x1, k.x + k.w) - Math.max(x0, k.x) > HAIR
                    && Math.min(y1, k.y + k.h) - Math.max(y0, k.y) > HAIR) cost += PRICE[k.kind] || 50;
        }
        return cost;
    }

    // Where the run is slid round its disc when the middle is covered - a
    // ruler's leg label sits directly over the disc of the circuit whose
    // column it names, and a hair to one side is past it.
    static get OFFSETS() { return [0, 0.45, -0.45, 0.7, -0.7, 0.9, -0.9]; }

    // The way a run leaves the wall. The WHOLE first leg is weighed, not
    // just the stub: a run leaving by the top has to cross the strip where
    // the map keeps its multi band and its circuit ruler, and a way out
    // that is clear of the wall is no use if it is drawn through those.
    //
    // The nearer SIDE that is clear wins, because a run beside the wall
    // reads best and it is the drawing that was approved; then the nearer
    // end - a row of discs blocks its own neighbours, and then the way out
    // is up or down its own column. Where nothing is clear the cheapest
    // way out stands, and a disc is never the thing given up.
    // Of two ends as near as each other, the one on the side the run's box
    // stands (`near`) goes first: out that way it is already on its way.
    //
    // BY ITS BOX'S OWN EDGE FIRST, where the disc stands on that edge -
    // no further from it than from its nearer side, or than its own
    // diameter - and that way is clear (2026-10-18). A disc in the wall's
    // corner left by its side only while its socket stood clear of the
    // wall beside it, and that held the wall to the width of the row of
    // boxes: on a power sheet whose breakouts stand over the wall, the
    // two corner circuits alone kept the wall at half its growth and the
    // owner saw a wall "too justified" that "could be much bigger". Out by
    // its box's edge the run is on its way whatever the wall's width.
    //
    // OFF ANOTHER RUN'S LINE. Of the clear ways out by one edge, the first
    // whose line stands a pen's width from every line coming the other way
    // (`apart(edge, at)`: a drop into a socket or a run up a channel past a
    // box) and from the other discs is taken - a stub a hair beside another
    // run's drop into its socket printed as one line with it - and where
    // none does, the first clear one as before. The edge is chosen exactly
    // as it always was, and a way out it picks that crosses more of the
    // wall than its own panel then goes by the seams (_bwSeamExit).
    _bwExit(d, wall, labels, own, pad, room, near = 'bottom', taken = null, apart = null) {
        const far = (e, at) => e === 'left' ? [room.x0, at] : e === 'right' ? [room.x1, at]
            : e === 'top' ? [at, room.y0] : [at, room.y1];
        const by = (names) => names
            .map(e => ({ e, s: this._bwStub(d, e, wall, 0) }))
            .sort((p, q) => (Math.abs(p.s.gap - q.s.gap) > 0.01 ? p.s.gap - q.s.gap
                : (p.e === near ? -1 : 0) - (q.e === near ? -1 : 0)));
        const sides = by(['left', 'right']), ends = by(['top', 'bottom']);
        const free = (e, s) => !apart || apart(e, s.at);
        // A way out that crosses more of the wall than the disc's own panel
        // is not taken straight: straight along the middle of a row (or a
        // column) is exactly where the screen's own chain runs, and it lay
        // on top of the signal cables for panels on end (owner, 2026-11-17:
        // "its covering all the signal cables"). It goes by the SEAMS
        // instead - see _bwSeamExit.
        const seamOr = (pick) => (pick && taken && this._bwLong(d, pick.edge, pick.stub)
            ? this._bwSeamExit(d, wall, labels, own, pad, room, taken, pick) : pick);
        const own0 = this._bwStub(d, near, wall, 0);
        if (own0.gap <= Math.max(sides[0].s.gap, 2 * d.r) + 0.01) {
            let first = null;
            for (const off of _BinderWiring.OFFSETS) {
                const s = this._bwStub(d, near, wall, off);
                if (this._bwCost(s.head, far(near, s.at), pad, labels, own)) continue;
                if (free(near, s)) return seamOr({ edge: near, stub: s, cost: 0 });
                if (!first) first = { edge: near, stub: s, cost: 0 };
            }
            if (first) return seamOr(first);
        }
        let best = null;
        for (const list of [sides, ends]) {
            for (const c of list) {
                let first = null;
                for (const off of _BinderWiring.OFFSETS) {
                    const s = this._bwStub(d, c.e, wall, off);
                    const cost = this._bwCost(s.head, far(c.e, s.at), pad, labels, own);
                    if (!cost) {
                        if (free(c.e, s)) return seamOr({ edge: c.e, stub: s, cost: 0 });
                        if (!first) first = { edge: c.e, stub: s, cost: 0 };
                        continue;
                    }
                    if (!best || cost < best.cost) best = { edge: c.e, stub: s, cost };
                }
                if (first) return seamOr(first);
            }
        }
        return seamOr(best);
    }

    // Whether a straight way out by `edge` crosses wall beyond the disc's
    // own panel - its panel's half and a little more.
    _bwLong(d, edge, s) {
        if (!d.panel) return false;
        const across = edge === 'left' || edge === 'right' ? d.panel.w : d.panel.h;
        return s.gap > across * 0.6;
    }

    // THE WAY OUT BY THE SEAMS (2026-11-17). A disc in the middle of the
    // wall leaves along the line BETWEEN two rows (or two columns) of
    // panels: a short step off its rim to its own panel's edge, then along
    // that seam to the wall's edge, and from there round the wall like any
    // other run (`at` is the seam). The screen's chains run panel middle to
    // panel middle and its discs sit on the middles, so a run on a seam
    // never lies along a chain or over a disc - it only crosses a chain, at
    // a right angle. Every edge is weighed: by a seam where the edge is
    // past the disc's own panel, straight where it is not; the clear one
    // that crosses the least wall wins. Two runs never share a stretch of
    // the same seam (`taken`), so a seam is never nudged off its line.
    // `straight` is the straight way out it stands in for: kept where every
    // seam would be drawn through a neighbour's disc and it is not - a run
    // along a chain still reads, a name it covers does not ("IMAG SR-6"
    // printed "IMAG R-6", _bwCost).
    _bwSeamExit(d, wall, labels, own, pad, room, taken, straight = null) {
        const E = 0.5;
        const far = (e, at) => e === 'left' ? [room.x0, at] : e === 'right' ? [room.x1, at]
            : e === 'top' ? [at, room.y0] : [at, room.y1];
        const P = d.panel;
        const tries = [];
        for (const e of ['left', 'right', 'top', 'bottom']) {
            const flat = e === 'left' || e === 'right';
            const s0 = this._bwStub(d, e, wall, 0);
            if (!this._bwLong(d, e, s0)) {
                for (const off of _BinderWiring.OFFSETS) {
                    const s = this._bwStub(d, e, wall, off);
                    tries.push({ edge: e, stub: s, len: Math.max(0, s.gap),
                                 cost: this._bwCost(s.head, far(e, s.at), pad, labels, own) });
                }
                continue;
            }
            // the seams either side of the disc's own panel, never the
            // wall's own border (that is the way out by an end)
            const seams = flat ? [P.y, P.y + P.h] : [P.x, P.x + P.w];
            const lo = flat ? wall.y : wall.x, hi = flat ? wall.y + wall.h : wall.x + wall.w;
            for (const c of seams) {
                if (c <= lo + E || c >= hi - E) continue;
                const toward = flat ? (c < d.y ? -1 : 1) : (c < d.x ? -1 : 1);
                const along = flat ? (e === 'left' ? -1 : 1) : (e === 'top' ? -1 : 1);
                const dc = Math.abs(c - (flat ? d.y : d.x));
                let head, lead = [];
                if (dc < d.r - E) {
                    // the seam runs through the disc: off its rim on the seam
                    const q = Math.sqrt(d.r * d.r - dc * dc);
                    head = flat ? [d.x + along * q, c] : [c, d.y + along * q];
                } else {
                    head = flat ? [d.x, d.y + toward * d.r] : [d.x + toward * d.r, d.y];
                    lead = [flat ? [d.x, c] : [c, d.y]];
                }
                const start = lead.length ? lead[0] : head;
                const out = flat ? [e === 'left' ? wall.x : wall.x + wall.w, c]
                                 : [c, e === 'top' ? wall.y : wall.y + wall.h];
                const gap = flat ? Math.abs(out[0] - start[0]) : Math.abs(out[1] - start[1]);
                let cost = this._bwCost(start, far(e, c), pad, labels, own);
                if (lead.length) cost += this._bwCost(head, lead[0], pad, labels, own);
                // the seam's line on past the wall's edge too: a socket's
                // drop standing on it would print as one with the run
                const end = far(e, c);
                const span = { k: flat ? 1 : 0, c,
                               lo: Math.min(start[flat ? 0 : 1], end[flat ? 0 : 1]),
                               hi: Math.max(start[flat ? 0 : 1], end[flat ? 0 : 1]) };
                if (taken.some(t => t.k === span.k && Math.abs(t.c - c) < pad * 2
                        && Math.min(t.hi, span.hi) - Math.max(t.lo, span.lo) > E)) cost += 200;
                tries.push({ edge: e, stub: { head, lead, out, at: c, gap, seam: span },
                             len: gap + dc, cost });
            }
        }
        if (!tries.length) return straight;
        tries.sort((a, b) => (a.cost - b.cost) || (a.len - b.len));
        const pick = tries[0];
        // (1000: _bwCost's price for covering a disc)
        if (straight && pick.cost >= 1000 && pick.cost > straight.cost) return straight;
        if (pick.stub.seam) taken.push(pick.stub.seam);
        return { edge: pick.edge, stub: pick.stub, cost: pick.cost };
    }

    // The lanes: every run that has to travel along one is given the lowest
    // lane whose marks it does not lie on top of, so two runs share a lane
    // wherever their stretches do not meet and the sheet spends no room it
    // does not need. Returns the lane each took and how many there are.
    //
    // `nearer(a, b)`, where given, says item a must take a lane nearer the
    // wall than item b: a's line up from the wall to its lane stands on b's
    // line from its lane on to its socket, and with a's lane the further
    // out the two would share that stretch and print as one (2026-11-20).
    // Such an item waits for every item that must stand nearer than it and
    // then takes the lowest free lane past theirs; with no such pair the
    // lanes are handed out exactly as they always were. A ring of such
    // waits (each run's line on the other's) is broken by the order given.
    _bwLanes(items, nearer = null) {
        const taken = [];
        const need = items.map(() => []);
        if (nearer) {
            items.forEach((a, i) => items.forEach((b, j) => {
                if (i !== j && nearer(a, b)) need[j].push(i);
            }));
        }
        const done = items.map(() => false);
        for (let placed = 0; placed < items.length; placed++) {
            let idx = items.findIndex((_it, i) => !done[i] && need[i].every(q => done[q]));
            if (idx < 0) idx = done.indexOf(false);
            const it = items[idx];
            done[idx] = true;
            let k = 0;
            for (const q of need[idx]) if (done[q] && q !== idx) k = Math.max(k, items[q].lane + 1);
            for (; ; k++) {
                const on = taken[k] || (taken[k] = []);
                if (on.every(([lo, hi]) => it.hi <= lo + 0.01 || it.lo >= hi - 0.01)) {
                    on.push([it.lo, it.hi]);
                    break;
                }
            }
            it.lane = k;
        }
        return taken.length;
    }

    // THE LANES BY THE WALL ON A BOX'S SIDE (2026-11-20). A run there has a
    // line up from the wall to its lane (`up`: the stub off its disc, or the
    // rail it came along) and a line from its lane on to its socket (`on`).
    // Handed out first-fit in the order the runs come, a run could take a
    // lane further out than another run whose socket stands over its stub -
    // and then its stub went on up along that run's drop, the two printing
    // as one line. On a sheet whose wall is short and narrow (four boxes a
    // side on letter, A3, ARCH C, tabloid without its title block) a disc is
    // smaller than a run's pen, so no way off it steps aside, and the nudge
    // never moves a run's first or last line. So where the lanes as they
    // always were put any run's line up within `pen` of another's line on
    // past it, they are handed out again with that run nearer the wall
    // (_bwLanes' `nearer`), in whichever of a few orders - as they came,
    // left to right, or nested one way round or the other - wants the
    // fewest lanes and then crosses least; a sheet with no such pair is
    // laid out exactly as it always was. Returns the lanes wanted.
    _bwNearLanes(items, up, on, pen) {
        const E = 0.01;
        let n = this._bwLanes(items);
        const nearer = (a, b) => Math.abs(up(a) - on(b)) < pen;
        const clash = (list) => list.some(a => list.some(b => a !== b && nearer(a, b) && a.lane >= b.lane));
        if (!clash(items)) return n;
        // a horizontal crossing another run's line up (it stands past the
        // other's lane) or its line on (it stands inside it)
        const cross = (list) => {
            let c = 0;
            for (const a of list) {
                for (const b of list) {
                    if (a === b) continue;
                    const u = up(b), o = on(b);
                    if (u > a.lo + E && u < a.hi - E && a.lane < b.lane) c++;
                    if (o > a.lo + E && o < a.hi - E && a.lane > b.lane) c++;
                }
            }
            return c;
        };
        const left = (it) => on(it) < up(it);
        const nest = (first) => items.slice().sort((a, b) => ((left(a) === first ? 0 : 1) - (left(b) === first ? 0 : 1))
            || (left(a) ? up(a) - up(b) : up(b) - up(a)));
        const orders = [items, items.slice().sort((a, b) => (a.lo - b.lo) || (a.hi - b.hi)), nest(true), nest(false)];
        let best = null;
        for (const order of orders) {
            const list = order.map(it => ({ ...it }));
            const m = this._bwLanes(list, nearer);
            const c = cross(list);
            if (!best || m < best.m || (m === best.m && c < best.c)) best = { m, c, list };
        }
        const of = new Map(best.list.map(it => [it.p, it.lane]));
        for (const it of items) it.lane = of.get(it.p);
        n = best.m;
        return n;
    }

    // The turns a run through a channel makes in the corridor, from its
    // place in the channel (`x`) across to its socket (`t`): each given a
    // lane, counted out from the box it turns to. They nest - of two that
    // overlap (with `margin` of air), the one whose socket is further from
    // its channel turns further from its box - so with the runs in their
    // sockets' order across the channels no turn crosses another, and a
    // run turning one way never overlaps one turning the other. A run
    // straight up its channel has no turn. Returns the lanes wanted and
    // each turning run's lane, keyed by its `p`.
    _bwTurns(items, margin) {
        const E = 0.01;
        const of = new Map();
        const layer = (list) => {
            const done = [];
            for (const it of list) {
                const lo = Math.min(it.x, it.t), hi = Math.max(it.x, it.t);
                let L = 0;
                for (const q of done) if (q.hi > lo - margin && q.lo < hi + margin) L = Math.max(L, q.L + 1);
                done.push({ lo, hi, L });
                of.set(it.p, L);
            }
        };
        const byT = items.slice().sort((a, b) => a.t - b.t);
        layer(byT.filter(it => it.x < it.t - E));
        layer(byT.filter(it => it.x > it.t + E).reverse());
        return { n: of.size ? Math.max(...of.values()) + 1 : 0, of };
    }

    // A row spread across the width, as it always was - and never past it:
    // a crowded row takes the room it really has rather than a fixed gap
    // and a block hanging off the sheet's edge. `row` is [{ key, w }];
    // returns each box's left edge, in the prototype's units.
    _bwSpread(row, availW) {
        const out = new Map();
        const sum = row.reduce((s, b) => s + b.w, 0);
        const gp = row.length > 1 ? Math.max(MIN_BOX_GAP, (availW - sum) / (row.length - 1)) : 0;
        let x = MARGIN + Math.max(0, (availW - sum - gp * (row.length - 1)) / 2);
        for (const b of row) { out.set(b.key, x); x += b.w + gp; }
        return out;
    }

    // ACROSS THE WIDTH, for a sheet whose boxes take more than one row on
    // a side - settled once, in the prototype's units: where a box stands
    // across the sheet does not hang on the wall's height.
    //
    // NO RUN EVER CROSSES A BOX. A side whose boxes take a second row used
    // to centre that row too, so its box stood straight over the middle box
    // of the first and its runs went down through that box - its name, its
    // inputs, its sockets - and each lay on top of the inner box's own run
    // to the same socket number (owner, 2026-11-18, a sheet of eight
    // breakout boxes, CVT 1 over CVT 5 and CVT 7 over CVT 3: neither box
    // could be read). So the inner row is spread as it always was, and a
    // box in an OUTER row stands over the CHANNEL nearest its own points on
    // the wall - the clear space the rows inside it leave between their
    // boxes. Its runs come up (or down) that channel, every one under a
    // socket that is over the channel straight on, and the rest turn to
    // their sockets in the corridor between the two rows, which grows to
    // the lanes they want; the turns nest so they never cross each other.
    // A run to a third row keeps a lane off every run already given a
    // place in a channel on its way.
    //
    // WHERE THE CHANNELS CANNOT HOLD THEM - an inner row so full its gaps
    // are a hair wide - the rows inside are spread again with a gap kept
    // open for those runs, nearest the points they serve; and where a row
    // cannot keep that gap and its boxes too, its last box moves out a
    // row. The owner chose readable boxes over size: every line stays
    // clear of every box. Each step is logged.
    //
    // `rows` = { top, bottom }, each a list of rows, inner first; a box is
    // { key, w, lead (its first socket's centre from its left edge), pitch,
    // count, sockets: [{ id, n }], target (the mean of its points across
    // the width, or null) }. Returns { x: Map(key -> left edge), via:
    // Map(socket id -> { x, lane, s, ri, c0, c1 }), corridor and lanes per
    // side and row, rows (as they ended), moved, log }.
    _bwAcross(rows, availW) {
        const E = 0.01, CLR = LANE_STEP;
        const ROOM_L = MARGIN / 2, ROOM_R = PROTO_W - MARGIN / 2;
        const x = new Map(), via = new Map(), log = [];
        const corridor = { top: [], bottom: [] }, lanes = { top: [], bottom: [] };
        const out = { top: [], bottom: [] };
        let moved = false;
        const sockAt = (b, n) => x.get(b.key) + b.lead + (n - 1) * b.pitch;
        const span = (b) => {
            const ns = b.sockets.map(k => k.n);
            const n0 = ns.length ? Math.min(...ns) : 1, n1 = ns.length ? Math.max(...ns) : (b.count || 1);
            return [b.lead + (n0 - 1) * b.pitch, b.lead + (n1 - 1) * b.pitch];
        };
        const widthOf = (row) => row.reduce((s, b) => s + b.w, 0) + MIN_BOX_GAP * Math.max(0, row.length - 1);
        // the clear space across the width that the rows inside row `ri`
        // leave, less a lane either side of every run already passing
        // through them to a row further in
        const channelsFor = (R, s, ri) => {
            const iv = [];
            for (let j = 0; j < ri; j++) for (const b of R[j]) iv.push([x.get(b.key) - CLR, x.get(b.key) + b.w + CLR]);
            for (const v of via.values()) if (v.s === s && v.ri < ri) iv.push([v.x - LANE_STEP + E, v.x + LANE_STEP - E]);
            iv.sort((a, b) => a[0] - b[0]);
            const ch = [];
            let at = ROOM_L;
            for (const [a, b] of iv) {
                if (a >= at) ch.push([at, a]);
                at = Math.max(at, b);
            }
            if (ROOM_R >= at) ch.push([at, ROOM_R]);
            return ch;
        };
        // a row spread with a gap `res.G` wide kept open nearest `res.T`;
        // false where the row cannot hold the gap and its boxes too
        const spreadAround = (row, res) => {
            const n = row.length, sum = row.reduce((s, b) => s + b.w, 0);
            if (sum + res.G + MIN_BOX_GAP * n > availW + E) return false;
            const g = (availW - sum - res.G) / n;
            let best = null;
            for (let m = 0; m <= n; m++) {
                let at = MARGIN, centre = 0;
                const xs = [];
                for (let i = 0; i <= n; i++) {
                    if (i === m) { centre = at + res.G / 2; at += res.G + g; }
                    if (i < n) { xs.push(at); at += row[i].w + g; }
                }
                const d = Math.abs(centre - res.T);
                if (!best || d < best.d - E) best = { d, xs };
            }
            row.forEach((b, i) => x.set(b.key, best.xs[i]));
            return true;
        };
        // an outer row's boxes, in their order, each over the channel
        // nearest its own points (its spread place where it has none)
        const placeOuter = (R, s, ri) => {
            const row = R[ri];
            const ch = channelsFor(R, s, ri);
            const base = this._bwSpread(row, availW);
            let lo = MARGIN;
            row.forEach((b, i) => {
                const rest = row.slice(i + 1).reduce((a, e) => a + e.w + MIN_BOX_GAP, 0);
                const hi = MARGIN + availW - b.w - rest;
                const [u0, u1] = span(b);
                const mid = (u0 + u1) / 2, half = (u1 - u0) / 2;
                const T = b.target != null ? b.target : base.get(b.key) + mid;
                const away = ([a, c]) => (T < a ? a - T : T > c ? T - c : 0);
                const c = ch.slice().sort((p, q) => (away(p) - away(q)) || ((q[1] - q[0]) - (p[1] - p[0])))[0];
                let at = base.get(b.key);
                if (c) {
                    const centre = c[1] - c[0] >= 2 * half
                        ? Math.min(Math.max(T, c[0] + half), c[1] - half) : (c[0] + c[1]) / 2;
                    at = centre - mid;
                }
                at = Math.max(lo, Math.min(at, hi));
                x.set(b.key, at);
                lo = at + b.w + MIN_BOX_GAP;
            });
        };
        // The runs to an outer row through the channels: each given a place
        // in one, in the order of its socket so no two cross, as near its
        // socket as the channel lets it - the channels filled so the runs
        // travel least (a channel holds a run every `sp`; the fewest-travel
        // split is found over every way of sharing the runs out in order).
        // Null where the channels cannot hold them all.
        const fit = (runs, ch, sp) => {
            const m = ch.length, k = runs.length;
            if (!m) return null;
            const cap = ch.map(([a, b]) => Math.floor((b - a) / sp + 1e-6) + 1);
            const away = (t, [a, b]) => (t < a ? a - t : t > b ? t - b : 0);
            const g = [], how = [];
            for (let j = 0; j < m; j++) {
                g.push(new Array(k + 1).fill(Infinity));
                how.push(new Array(k + 1).fill(0));
                for (let i = 0; i <= k; i++) {
                    let acc = 0;
                    for (let n = 0; n <= Math.min(cap[j], i); n++) {
                        if (n) acc += away(runs[i - n].t, ch[j]);
                        const prev = j ? g[j - 1][i - n] : (i - n === 0 ? 0 : Infinity);
                        if (prev + acc < g[j][i]) { g[j][i] = prev + acc; how[j][i] = n; }
                    }
                }
            }
            if (!(g[m - 1][k] < Infinity)) return null;
            let i = k;
            for (let j = m - 1; j >= 0; j--) {
                const n = how[j][i];
                const [a, b] = ch[j];
                for (let q = 0; q < n; q++) {
                    const r = runs[i - n + q];
                    r.x = Math.min(Math.max(r.t, a + q * sp), b - (n - 1 - q) * sp);
                    r.c = ch[j];
                }
                i -= n;
            }
            return runs;
        };
        // true, or what a gap for the row's runs would need
        const route = (R, s, ri) => {
            const runs = [];
            for (const b of R[ri]) for (const k of b.sockets) runs.push({ id: k.id, t: sockAt(b, k.n) });
            if (!runs.length) return true;
            runs.sort((a, b) => a.t - b.t);
            const ch = channelsFor(R, s, ri);
            let fitted = null;
            for (const sp of [LANE_STEP, RUN_W + CASE_EXTRA + 0.4]) {
                fitted = fit(runs, ch, sp);
                if (fitted) break;
            }
            if (!fitted) {
                return { need: (runs.length - 1) * LANE_STEP + 2, runs: runs.length,
                         T: runs.reduce((a, r) => a + r.t, 0) / runs.length };
            }
            const { n, of } = this._bwTurns(runs.map(r => ({ p: r, x: r.x, t: r.t })), CLR);
            for (const r of runs) {
                via.set(r.id, { x: r.x, lane: of.has(r) ? of.get(r) : -1, s, ri, c0: r.c[0], c1: r.c[1] });
            }
            lanes[s][ri] = n;
            corridor[s][ri] = (n + 2) * LANE_STEP;
            return true;
        };
        for (const s of ['top', 'bottom']) {
            const R = (rows[s] || []).filter(r => r && r.length).map(r => r.slice());
            const tries = 4 * (R.reduce((a, r) => a + r.length, 0) + 2);
            let res = null;
            for (let attempt = 0; attempt < tries; attempt++) {
                for (const [k, v] of [...via]) if (v.s === s) via.delete(k);
                corridor[s] = [];
                lanes[s] = [];
                let fail = null, full = -1;
                for (let ri = 0; ri < R.length; ri++) {
                    if (res && ri < res.upto) {
                        if (!spreadAround(R[ri], res)) { full = ri; break; }
                    } else if (!ri) {
                        for (const [k, v] of this._bwSpread(R[ri], availW)) x.set(k, v);
                    } else placeOuter(R, s, ri);
                    if (ri) {
                        const r = route(R, s, ri);
                        if (r !== true) { fail = { ri, ...r }; break; }
                    }
                }
                if (full >= 0) {
                    // the row cannot keep the gap and its boxes too: its last
                    // box moves out a row (a new one where it was the last)
                    // (a row keeps its boxes in the order of their points)
                    const along = (r) => r.sort((p, q) => (p.target == null ? 1e9 : p.target)
                                                        - (q.target == null ? 1e9 : q.target));
                    const b = R[full].pop();
                    if (!R[full + 1]) R.push([]);
                    R[full + 1] = along(R[full + 1].concat([b]));
                    for (let j = full + 1; j < R.length; j++) {
                        while (R[j].length > 1 && widthOf(R[j]) > availW + E) {
                            if (!R[j + 1]) R.push([]);
                            R[j + 1] = along(R[j + 1].concat([R[j].pop()]));
                        }
                    }
                    for (let j = R.length - 1; j >= 0; j--) if (!R[j].length) R.splice(j, 1);
                    moved = true;
                    res = null;
                    log.push({ side: s, step: 'moved out a row', key: b.key, row: full + 1 });
                    continue;
                }
                if (!fail) break;
                // a gap kept open for the row's runs - wider each time the
                // one kept was not enough
                const G = res && res.upto === fail.ri ? res.G + 2 * LANE_STEP : fail.need;
                res = { G, T: fail.T, upto: fail.ri };
                log.push({ side: s, step: 'gap kept', row: fail.ri, runs: fail.runs, width: G });
                if (attempt === tries - 1) log.push({ side: s, step: 'no gap', row: fail.ri });
            }
            out[s] = R;
        }
        return { x, via, corridor, lanes, rows: out, moved, log };
    }

    // ---- the geometry -------------------------------------------------------

    // NOTHING LEAVES THE DRAWING AREA (2026-11-20). The prototype's page is
    // carried onto the sheet at K = the area's width / 1000, and the wall
    // takes whatever height the boxes, the corridors and the lanes leave it
    // - down to its floor of 40 units. Where even that is too much (eight
    // breakout boxes in two rows a side on tabloid without its title block,
    // on A3 under a view band) the stack ran on past the drawing's foot:
    // the last row of boxes and its input line were cut by the page edge.
    // So where the sheet laid out at K does not fit its area's height, the
    // whole drawing is laid out again at the largest K that does - the same
    // answer the binder gives any other drawing too big for its area
    // (_bFillScale: one uniform scale, as large as keeps it inside) - and
    // stands centred across the area's width. Only as much smaller as it
    // must be: a sheet that fits is laid out exactly as it always was.
    // `fit` false lays it out at K whatever it takes (the simple sheet asks
    // so first, and gives the drawing room from its tables before this).
    _bwPlanHalf(book, target, scr, side, A, fit = true) {
        const P = this._bwLayHalf(book, target, scr, side, A);
        if (!fit) return P;
        const K0 = P.K;
        const at = (k) => {
            const w = PROTO_W * k;
            return this._bwLayHalf(book, target, scr, side, { ...A, x: A.x + (A.w - w) / 2, w });
        };
        const fits = (Q) => !(this._bwOver(Q, A).by > 0.5);
        // (the room it was given, for the log)
        const within = { x: A.x, y: A.y, w: A.w, h: A.h };
        if (fits(P)) return Object.assign(P, { fit: 1, within });
        // the height the stack wants, in the prototype's units, against the
        // height the area gives at a smaller K - a step further each time a
        // layout at that K still wants more (its lanes are its own)
        let k = K0, Q = P;
        for (let i = 0; i < 8 && !fits(Q); i++) {
            k = Math.min(k * 0.99, A.h / this._bwOver(Q, A).need);
            Q = at(k);
        }
        if (fits(Q)) {
            // and the largest K that fits, between the first that did and
            // the one that did not: the wall a smaller layout grows into is
            // room a larger one could have used
            let lo = k, hi = K0;
            for (let i = 0; i < 5; i++) {
                const m = (lo + hi) / 2;
                const M = at(m);
                if (fits(M)) { lo = m; Q = M; } else hi = m;
            }
        }
        return Object.assign(Q, { fit: Q.K / K0, within });
    }

    // How far a laid-out half runs past its area's foot (`by`, page units),
    // and the height it wants in the prototype's units (`need`: its stack
    // from the area's head, and the foot it keeps).
    _bwOver(P, A) {
        let bottom = -Infinity;
        for (const b of P.blocks || []) bottom = Math.max(bottom, b.y + b.h);
        for (const r of P.runs || []) for (const pt of r.points || []) bottom = Math.max(bottom, pt[1]);
        for (const d of P.discs || []) bottom = Math.max(bottom, d.y + (d.r || 0));
        if (P.mapArea) bottom = Math.max(bottom, P.mapArea.y + P.mapArea.h);
        if (!Number.isFinite(bottom)) return { by: 0, need: 0 };
        const foot = FOOT_PAD + (P.unplaced ? FOOT_LINE : 0);
        return { by: bottom - (A.y + A.h - foot * P.K), need: (bottom - A.y) / P.K + foot };
    }

    // One half laid out in page units, nothing painted. The prototype's
    // page is 1000 wide; K carries its every number onto this half.
    _bwLayHalf(book, target, scr, side, A) {
        const subject = this._bSubject(target);
        const layer = subject.layers[0];
        // the runs' inks are the screen that carries them
        const inks = subject.carriers[0];
        const facts = side === 'signal' ? this._bwSignalFacts(book, subject) : this._bwPowerFacts(book, subject, scr);
        const view = side === 'signal' ? 'data-flow' : 'power';
        const isData = side === 'signal';
        const printer = book.meta.palette === 'printer';
        const K = A.w / PROTO_W;
        const availW = PROTO_W - 2 * MARGIN;
        const ctxM = book.measureCtx;
        // a width in the PROTOTYPE's units, measured in the type the page
        // will really be set in
        const measure = (text, size, weight) => {
            ctxM.font = this._bFont(size * K, weight);
            return ctxM.measureText(String(text)).width / K;
        };

        const devices = facts.devices;
        for (const d of devices) d.n = Math.max(1, Number(d.n) || 0, ...d.sockets.keys());
        const wiresOf = (key) => facts.wires.filter(w => w.device.key === key);

        // A note earns its place only when it says something the socket
        // number does not.
        const noteOf = (text, socket) => {
            const t = String(text == null ? '' : text);
            if (!t || t === String(socket) || t.endsWith('-' + socket)) return '';
            return t;
        };
        const noteFloor = (d) => Math.ceil(Math.max(0,
            ...wiresOf(d.key).map(w => measure(noteOf(w.stub.text, w.socket), NOTE_SZ, 400))) + NOTE_PAD);
        const capW = (d) => measure(d.title, CAPTION_SZ, 700);
        // a box's inputs on the data side (_bwBoxInputs) - none where no
        // input is on a cable, so such a sheet draws as it always did - and
        // the room each group's outline takes (the head column as wide as
        // the box's widest input name, so X1's and X2's strands start alike)
        for (const d of devices) d.inputs = isData && d.box ? this._bwBoxInputs(d.box) : null;
        const inHead = (d) => Math.max(0, ...(d.inputs || []).map(g => measure(g.head, IN_SZ, 700))) + 5;
        // and its cable after it, as wide as its own name: a second input
        // on a cable says only "TAC A", and the box is no wider for it
        const inSub = (g) => (g.sub ? measure(g.sub, IN_SZ, 400) + 6 : 0);
        const inLineW = (d, g) => inHead(d) + inSub(g) + g.strands.reduce((s, st) =>
            s + (st.swatch ? IN_SW + 3 : 0) + measure(st.text, IN_SZ, 400) + 6, 0) - 6;
        const groupW = (d, g) => inLineW(d, g) + IN_PAD * 2;
        // a box is never narrower than its widest group, so a wrapped group
        // is never cut, and it holds its groups side by side on the one
        // line under the caption as long as two such boxes still stand on
        // a row: past that a group takes a line of its own
        const inContent = (d) => {
            if (!d.inputs) return 0;
            const ws = d.inputs.map(g => groupW(d, g));
            const line = ws.reduce((s, w) => s + w, 0) + IN_GAP * (ws.length - 1);
            return line + PAD * 2 <= (availW - MIN_BOX_GAP) / 2 ? line : Math.max(...ws);
        };
        // WHERE THE GROUPS GO in a box w wide: on the lines under the
        // caption, from its left edge, each line taking groups in order
        // while they fit (a group is never split). `lines` is the lines
        // added under the caption; `at` each group's left edge and line,
        // in box units.
        const inPlace = (d, w) => {
            if (!d.inputs) return null;
            const ws = d.inputs.map(g => groupW(d, g));
            const right = w - PAD + 0.01;
            let line = 1, x = PAD;
            const at = ws.map(v => {
                if (x > PAD && x + v > right) { line += 1; x = PAD; }
                const a = { x, line };
                x += v + IN_GAP;
                return a;
            });
            return { lines: line, at };
        };
        const rowWidthAt = (pitch) => devices.reduce((s, d) =>
            s + Math.max(d.n * Math.max(pitch, noteFloor(d)) + PAD * 2, capW(d) + PAD * 2, inContent(d) + PAD * 2), 0)
            + MIN_BOX_GAP * Math.max(0, devices.length - 1);
        // The pitch gives way before the layout does.
        let fit = PITCH;
        while (fit > MIN_PITCH && rowWidthAt(fit) > availW) fit -= 1;
        const pitchOf = (d) => Math.max(fit, noteFloor(d));
        const boxW = (d) => Math.max(d.n * pitchOf(d) + PAD * 2, capW(d) + PAD * 2, inContent(d) + PAD * 2);
        // the lines under the caption: the most any box needs sets every
        // box's height on the sheet
        const BOXH = BOX_H + IN_LINE * Math.max(0,
            ...devices.map(d => { const pl = inPlace(d, boxW(d)); return pl ? pl.lines : 0; }));

        // the block rows, greedily; the row count is what the wall's room
        // is measured against
        const pack = (order) => {
            const rows = [];
            let row = [];
            let w = 0;
            for (const d of order) {
                const dw = boxW(d);
                if (row.length && w + MIN_BOX_GAP + dw > availW) { rows.push(row); row = []; w = 0; }
                w += (row.length ? MIN_BOX_GAP : 0) + dw;
                row.push(d);
            }
            if (row.length) rows.push(row);
            return rows;
        };

        // the wall: bounded on both axes, with the boxes hard against it
        const nRuns = facts.wires.length;
        const railRoom = Math.min(RAIL_MAX, RAIL_BASE + Math.ceil(nRuns / 2) * RAIL_GAP);
        const wallRoomW = Math.max(80, availW - 2 * railRoom);
        const spec = { measure: (area) => this._bMap(book, subject, view, area, GUT) };
        const foot = FOOT_PAD + (facts.stubs.length > facts.wires.length ? FOOT_LINE : 0);
        // THE GAP BETWEEN THE WALL AND ITS BOXES IS THE LANES' AND NO MORE
        // (owner, 2026-10-18, on a power sheet whose every circuit starts on
        // the wall's top row and whose breakouts sat at the foot of the page:
        // "it makes more sense to put the breakouts up top right?", "these
        // should be dynamic so they are as close as the y can be to the
        // ports"). A side's gap is a lane apiece for the runs that travel
        // along it and two lanes of air - a side with no boxes and no lanes
        // takes none - and the wall then grows into whatever is left.
        const laneNeed = (n) => (n + 2) * LANE_STEP;
        // A side's rows of boxes: a box's height a row, and between two rows
        // the corridor the runs to the outer row turn in - ROW_GAP, or the
        // lanes those runs want where that is more (set once the rows are
        // known, below).
        const corridor = { top: [], bottom: [] };
        const corrOf = (s, ri) => Math.max(ROW_GAP, corridor[s][ri] || 0);
        const stackH = (s, n) => {
            let h = 0;
            for (let ri = 0; ri < n; ri++) h += BOXH + (ri ? corrOf(s, ri) : 0);
            return h;
        };
        // the block rows on each side of the wall, counted out from it
        let rowsOn = { top: 0, bottom: 0 };
        const gapFor = (over, under) => ({
            top: rowsOn.top || over ? laneNeed(over) : 0,
            bottom: rowsOn.bottom || under ? laneNeed(under) : 0 });
        // The room over the wall's head and under its foot: the boxes on
        // that side and the gap the lanes want. The wall takes what is left
        // of the side's own area - its height is read from that area and
        // bounded by nothing else - with its boxes hard against it, never
        // a gap between a box and the ports it serves. What height the wall
        // cannot use (a wide wall stopped by the width) is shared above and
        // below the whole drawing - boxes, lanes and wall - so it stands in
        // the middle of the sheet (owner, 2026-10-18: "it can be moved down
        // since it's too justified").
        //
        // `grow` = { t, rail }: t 0 is the wall rev 1.1 drew (railRoom
        // either side, MAX_WALL_H tall); t 1 is the whole room - only
        // `rail` kept either side for the runs that come down a rail, and
        // all the height between the lanes. Between, the room is the mix.
        const wallAt = (gap, grow) => {
            const head = stackH('top', rowsOn.top) + gap.top;
            const tail = gap.bottom + stackH('bottom', rowsOn.bottom);
            const roomH = Math.max(40, A.h / K - head - tail - foot);
            const t = grow ? grow.t : 0;
            const baseH = Math.min(MAX_WALL_H, roomH);
            const fullW = grow ? Math.max(wallRoomW, availW - 2 * grow.rail) : wallRoomW;
            const rw = wallRoomW + (fullW - wallRoomW) * t;
            const rh = baseH + (roomH - baseH) * t;
            const room = { x: A.x + (PROTO_W - rw) / 2 * K, y: A.y + head * K,
                           w: rw * K, h: rh * K };
            const probe = this._bMeasureMap(book, spec, room);
            const h = probe ? probe.area.h : 0;
            const spare = Math.max(0, (A.h - foot * K) - (head + tail) * K - h);
            const mapArea = { ...room, y: room.y + spare / 2, h: Math.max(1, h) };
            return { mapArea, geo: this._bMeasureMap(book, spec, mapArea), roomH, room,
                     head, spare, gap: { top: gap.top, bottom: gap.bottom } };
        };
        // the wall as the runs see it: with whatever stands astride a
        // member's edge (geo.reach), so a rail never runs through a label
        // that hangs off the wall
        const wallOf = (Wc) => {
            if (!Wc.geo) return { x: A.x, y: Wc.mapArea.y, w: A.w, h: 0 };
            const { wall: g, reach: o } = Wc.geo;
            return o ? { x: g.x - o.left, y: g.y - o.top, w: g.w + o.left + o.right, h: g.h + o.top + o.bottom } : g;
        };

        // pass one, every box under the wall in the facts' own order, only
        // to see where each box's own connection points stand on the wall
        let rows = pack(devices);
        rowsOn = { top: 0, bottom: rows.length };
        let W = wallAt(gapFor(0, 0));
        const discOf = new Map();
        const rule = this._bwDiscRule(layer, side);
        const placeDiscs = (geo) => {
            discOf.clear();
            for (const st of facts.stubs) {
                discOf.set(st, this._bwDisc(book, rule, geo, st.panel, st.text, st.layer, !!st.end));
            }
        };
        placeDiscs(W.geo);
        const meanOf = (key) => {
            const ws = wiresOf(key);
            if (!ws.length) return 0;
            return ws.reduce((s, w) => s + (discOf.get(w.stub) || { x: 0 }).x, 0) / ws.length;
        };
        const meanYOf = (key) => {
            const ws = wiresOf(key);
            if (!ws.length) return 0;
            return ws.reduce((s, w) => s + (discOf.get(w.stub) || { y: 0 }).y, 0) / ws.length;
        };
        // EACH BOX ON THE SIDE OF THE WALL ITS OWN POINTS ARE ON. The discs
        // stand where the screen's flow pattern starts each port or circuit,
        // so a box goes over the wall when its points stand nearer the top
        // edge than the foot - on average, a disc on a side edge counting by
        // how far up that edge it is - and under it otherwise (a box with no
        // run on this sheet, or points dead on the middle, stays under it,
        // where every box used to stand). A box BESIDE the wall is never
        // shorter: the rails already run down the wall's sides, and a box
        // there would take the width the wall grows into.
        const wall0 = W.geo ? W.geo.wall : null;
        const leanOf = (key) => {
            const ws = wiresOf(key);
            if (!ws.length || !wall0 || !(wall0.h > 0)) return 0;
            return ws.reduce((s, w) => {
                const d = discOf.get(w.stub);
                return d ? s + ((d.y - wall0.y) - (wall0.y + wall0.h - d.y)) : s;
            }, 0) / ws.length;
        };
        const lean = new Map(devices.map(d => [d.key, leanOf(d.key)]));
        const sideOf = new Map(devices.map(d => [d.key, lean.get(d.key) < -0.01 * K ? 'top' : 'bottom']));
        const rank = new Map(devices.map((d, i) => [d.key, i]));
        // Two breakouts whose circuits stand in the same column of the wall
        // have all but the same mean, and the tie-break only ever fired on an
        // EXACT tie - so rounding decided the order, and it flipped with the
        // title block. Means closer than a disc's own radius are one column.
        //
        // Within a column, the breakout whose circuits stand HIGHER goes
        // further OUT: first on the wall's left half, last on its right. Its
        // runs leave above the other's, so standing outside them they nest
        // round the other fan instead of cutting through it. On live
        // show B's SR - MAIN power sheet that puts SR2 before SR1 - the runs
        // between the two breakouts stop crossing altogether, 55 crossings
        // become 25, and the 25 left are each fan's own. The user, shown
        // both: "the less crosings is better" (2026-09-13). Two breakouts at
        // the same height as well keep the facts' order. Two breakouts OVER
        // the wall are the mirror: the one whose circuits stand LOWER goes
        // further out.
        const TIE = SOCK * K;
        const midX = W.mapArea.x + W.mapArea.w / 2;
        const order = devices.slice().sort((a, b) => {
            const d = meanOf(a.key) - meanOf(b.key);
            if (Math.abs(d) >= TIE) return d;
            let dy = meanYOf(a.key) - meanYOf(b.key);
            if (Math.abs(dy) < TIE) return rank.get(a.key) - rank.get(b.key);
            if (sideOf.get(a.key) === 'top' && sideOf.get(b.key) === 'top') dy = -dy;
            return meanOf(a.key) < midX ? dy : -dy;
        });
        // The rows. Where every box fits ONE row they keep the places across
        // the width that row gives them, each simply over or under the wall,
        // so a run still finds its box under (or over) the part of the wall
        // it serves. Where they do not, each side is packed on its own - and
        // a side that would need a SECOND row first hands a box to the other
        // side, if that side still holds it in one row: the runs to a second
        // row pass between the boxes of the first, and where that row fills
        // the width they go straight through a box, its sockets and its name.
        // The box handed over is the one whose points lean least towards its
        // own side.
        const arrange = () => {
            const all = pack(order);
            const at = new Map();
            let xRows = [];
            if (all.length <= 1) {
                xRows = all;
                for (const d of order) at.set(d.key, { side: sideOf.get(d.key), ri: 0 });
            } else {
                const on = (s) => order.filter(d => sideOf.get(d.key) === s);
                for (const s of ['top', 'bottom']) {
                    const o = s === 'top' ? 'bottom' : 'top';
                    while (pack(on(s)).length > 1) {
                        const give = on(s).sort((a, b) => Math.abs(lean.get(a.key)) - Math.abs(lean.get(b.key)))
                            .find(d => pack(order.filter(x => x === d || sideOf.get(x.key) === o)).length <= 1);
                        if (!give) break;
                        sideOf.set(give.key, o);
                    }
                }
                for (const s of ['top', 'bottom']) {
                    pack(order.filter(d => sideOf.get(d.key) === s)).forEach((row, ri) => {
                        xRows.push(row);
                        for (const d of row) at.set(d.key, { side: s, ri });
                    });
                }
            }
            const n = { top: 0, bottom: 0 };
            for (const v of at.values()) n[v.side] = Math.max(n[v.side], v.ri + 1);
            return { xRows, at, n };
        };
        const arr = arrange();
        rowsOn = { ...arr.n };

        const CLR = LANE_STEP;                      // air between a box and a run past it
        // the rows on each side, inner first, as _bwAcross takes them
        const rowsIn = { top: [], bottom: [] };
        const devOf = new Map();
        const across = (() => {
            if (!arr.xRows.length || arr.xRows.every(row => row.every(d => !arr.at.get(d.key).ri))) return null;
            for (const row of arr.xRows) {
                const a = arr.at.get(row[0].key);
                rowsIn[a.side][a.ri] = row.map((d) => {
                    const ws = wiresOf(d.key);
                    devOf.set(d.key, d);
                    return { key: d.key, w: boxW(d), lead: PAD + pitchOf(d) / 2, pitch: pitchOf(d), count: d.n,
                             sockets: ws.map(w => ({ id: w, n: w.socket })),
                             target: ws.length ? (meanOf(d.key) - A.x) / K : null };
                });
            }
            return this._bwAcross(rowsIn, availW);
        })();
        const xOf = new Map();
        const via = new Map();
        if (!across) {
            // one row of boxes a side: spread across the width as it always was
            for (const row of arr.xRows) {
                for (const [k, x] of this._bwSpread(row.map(d => ({ key: d.key, w: boxW(d) })), availW)) xOf.set(k, x);
            }
        } else {
            for (const [k, x] of across.x) xOf.set(k, x);
            for (const [w, v] of across.via) via.set(w, v);
            for (const s of ['top', 'bottom']) {
                across.corridor[s].forEach((h, ri) => { if (h != null) corridor[s][ri] = h; });
            }
            // a box moved out a row to keep a gap open (_bwAcross) stands
            // in its new row
            if (across.moved) {
                arr.xRows = [];
                arr.n = { top: 0, bottom: 0 };
                for (const s of ['top', 'bottom']) {
                    across.rows[s].forEach((row, ri) => {
                        arr.xRows.push(row.map(b => devOf.get(b.key)));
                        for (const b of row) arr.at.set(b.key, { side: s, ri });
                        arr.n[s] = Math.max(arr.n[s], ri + 1);
                    });
                }
                rowsOn = { ...arr.n };
            }
        }

        const gap0 = gapFor(0, 0);
        W = wallAt(gap0);
        placeDiscs(W.geo);
        const nRows = Math.max(arr.n.top, arr.n.bottom);

        const bottom = A.y + A.h - foot * K;
        const hue = new Map(), dash = new Map();
        devices.forEach((d, i) => {
            hue.set(d.key, printer ? INK : HUES[i % HUES.length]);
            dash.set(d.key, DASHES[i % DASHES.length]);
        });
        const primaryInk = printer ? INK : (inks.primaryColor || '#00FF00');
        const backupInk = printer ? INK : (inks.backupColor || '#FF0000');

        // The blocks against a given wall: a row under the wall stands the
        // gap below its foot, a row over it the gap above its head, and the
        // next row out ROW_GAP further on. The blocks are spread across the
        // width rather than packed shoulder to shoulder: a run reads better
        // when its block is under (or over) the part of the wall it serves.
        //
        // A box OVER the wall is the box under it turned over: a run comes up
        // into its socket from below, so the sockets go to the box's foot and
        // the name - and the inputs on its row - to its head, the side no run
        // crosses, for the very reason the name went under the numbers.
        const placeBlocks = (Wc) => {
            const wall = wallOf(Wc);
            const gap = Wc.gap;
            // a row stands its corridor and a box's height further out
            // than the row inside it
            const outTo = (s, ri) => {
                let o = 0;
                for (let j = 1; j <= ri; j++) o += BOXH + corrOf(s, j);
                return o;
            };
            const rowYOf = (s, ri) => (s === 'top'
                ? wall.y - (gap.top + BOXH + outTo(s, ri)) * K
                : wall.y + wall.h + (gap.bottom + outTo(s, ri)) * K);
            const blocks = [];
            const socketX = new Map();
            arr.xRows.forEach((row) => {
                row.forEach((d) => {
                    const x = xOf.get(d.key);
                    const { side: bs, ri } = arr.at.get(d.key);
                    const over = bs === 'top';
                    const y = rowYOf(bs, ri);
                    const w = boxW(d), p = pitchOf(d);
                    const bx = A.x + x * K;
                    const used = new Map(wiresOf(d.key).map(w2 => [w2.socket, w2]));
                    const xs = new Map();
                    const sockets = [];
                    const sy = y + (over ? BOXH - SOCKET_DY : SOCKET_DY) * K;
                    for (let k = 1; k <= d.n; k++) {
                        const sx = A.x + (x + PAD + p / 2 + (k - 1) * p) * K;
                        xs.set(k, sx);
                        const on = used.get(k) || null;
                        const state = on ? (on.kind === 'power' ? 'power' : on.kind)
                                         : (d.sockets.get(k) === 'other' ? 'other' : 'free');
                        const note = on ? noteOf(on.stub.text, k) : (d.notes.get(k) || '');
                        sockets.push({ n: k, x: sx, y: sy, r: SOCK * K,
                                       state, note: note || null, on: !!on,
                                       kind: on ? on.kind : null });
                    }
                    socketX.set(d.key, xs);
                    const place = inPlace(d, w);
                    const inputs = place ? {
                        groups: d.inputs, head: inHead(d) * K, size: IN_SZ * K, line: IN_LINE * K,
                        sw: IN_SW * K, pad: IN_PAD * K, lines: place.lines,
                        at: place.at.map((a, gi) => ({ x: bx + a.x * K, line: a.line,
                                                      w: groupW(d, d.inputs[gi]) * K,
                                                      sub: inSub(d.inputs[gi]) * K })),
                    } : null;
                    blocks.push({ key: d.key, title: d.title, x: bx, y, w: w * K, h: BOXH * K,
                                  side: bs,
                                  titleY: y + (over ? TOP_TITLE_DY : TITLE_DY) * K,
                                  noteY: y + (over ? BOXH - NOTE_DY + NOTE_SZ * 0.72 : NOTE_DY) * K,
                                  inputs, row: ri, pitch: p * K, sockets,
                                  rim: isData ? INK : hue.get(d.key),
                                  hue: hue.get(d.key), dash: dash.get(d.key) });
                });
            });
            return { blocks, socketX, blockOf: new Map(blocks.map(b => [b.key, b])) };
        };

        // The discs on the wall and the runs that leave them. Taken as one
        // step so it can be done again with the discs the wall REALLY drew
        // and the lettering it REALLY laid down (the paint reads both off
        // the render - a splitter circuit's label sits at its fan-out, not
        // on its first panel, and only the renderer knows that).
        const draw = (placed, letters, W2) => {
            const Wc = W2 || W;
            const wall = wallOf(Wc);
            const { blocks, socketX, blockOf } = placeBlocks(Wc);
            const labels = letters || [];
            const pad = (RUN_W + CASE_EXTRA) / 2 * K;
            const discs = facts.stubs.map((st) => {
                const d = placed.get(st) || discOf.get(st);
                const w = facts.wires.find(x => x.stub === st) || null;
                return { kind: st.kind, text: st.text, x: d.x, y: d.y, r: d.r, panel: d.panel,
                         placed: !!w, ...(st.end ? { end: true } : {}),
                         hue: isData ? (st.kind === 'return' ? backupInk : primaryInk)
                                     : hue.get(w ? w.device.key : ''),
                         src: st };
            });
            const discFor = new Map(discs.map(d => [d.src, d]));
            // A disc the map drew stands in for the run's own disc, so its
            // own stub is not read as covering it. Where the registry was
            // not to be had, the discs the sheet measured stand in for the
            // lettering, which is enough to keep a run off its neighbours.
            const ink = labels.length ? labels
                : discs.map(d => ({ kind: 'disc', text: d.text,
                                    x: d.x - d.r, y: d.y - d.r, w: 2 * d.r, h: 2 * d.r }));
            const ownOf = (d) => {
                let best = null, bestD = Infinity;
                for (const k of ink) {
                    if (k.kind !== 'disc') continue;
                    const v = Math.abs(k.x + k.w / 2 - d.x) + Math.abs(k.y + k.h / 2 - d.y);
                    if (v < bestD) { best = k; bestD = v; }
                }
                return bestD <= 1.5 ? best : null;
            };

            // the clear space the runs travel in: over the wall's head (up
            // to the boxes over it), under its foot (down to the boxes under
            // it), and beside it either way
            const overTop = wall.y - Wc.gap.top * K + 2 * K, overBot = wall.y - 2 * K;
            const underTop = wall.y + wall.h + 2 * K;
            const underBot = wall.y + wall.h + Wc.gap.bottom * K - 2 * K;
            const room = { x0: A.x + 3 * K, x1: A.x + (PROTO_W - 3) * K,
                           y0: Math.min(overTop, wall.y), y1: Math.max(underBot, wall.y + wall.h) };

            // The lines that come in to each edge's lanes from the boxes on
            // that side - a drop into a socket, a run through a channel -
            // which a run leaving the wall keeps a pen's width off.
            const inbound = { top: [], bottom: [] };
            for (const w of facts.wires) {
                const b = blockOf.get(w.device.key);
                if (!b) continue;
                const v = via.get(w);
                const x = v ? A.x + v.x * K : (socketX.get(w.device.key) || new Map()).get(w.socket);
                if (Number.isFinite(x)) inbound[b.side].push(x);
            }

            // What each run wants: where it leaves the wall, where its
            // socket is, which side of the wall its box stands on, and
            // whether it can go straight to it from the side it leaves by.
            // the seams the runs leave by, taken as they are handed out,
            // and from the start every socket's drop: no seam is chosen on
            // a line a socket's run comes down (or up) on
            // (a run through a gap past an inner box comes down that gap,
            // from its outer box to the wall's edge, not down its socket)
            const taken = [];
            for (const w of facts.wires) {
                const b = blockOf.get(w.device.key);
                const v = b ? via.get(w) : null;
                const tx = v ? A.x + v.x * K : (socketX.get(w.device.key) || new Map()).get(w.socket);
                if (!b || !Number.isFinite(tx)) continue;
                const edgeY = b.side === 'top' ? wall.y : wall.y + wall.h;
                const sy = b.side === 'top' ? b.y + b.h : b.y;
                taken.push({ k: 0, c: tx, lo: Math.min(edgeY, sy), hi: Math.max(edgeY, sy) });
            }
            // the ways out already taken from each disc: a disc whose
            // circuit feeds two things (a multi's breakout and a breakout
            // box powered from the same circuit) sends two runs off it -
            // each its own stub, so two discs on the one spot - and by the
            // same way out they lay on top of one another
            const leftBy = new Map();
            const spot = (d) => `${Math.round(d.x * 10)}:${Math.round(d.y * 10)}`;
            const plans = facts.wires.map((w) => {
                const disc = discFor.get(w.stub);
                const b = blockOf.get(w.device.key);
                const T = b ? b.side : 'bottom';
                const near = T === 'top' ? 'top' : 'bottom';
                const sx = (socketX.get(w.device.key) || new Map()).get(w.socket);
                const ty = !b ? bottom
                    : T === 'top' ? b.y + (BOXH - SOCKET_DY + SOCK) * K : b.y + (SOCKET_DY - SOCK) * K;
                // A run to an outer row is laid as far as its channel as
                // any run is laid to its socket, and there turns in the
                // corridor to the socket itself: `tx` is where it travels
                // to, `sx` its socket, `vy` the corridor lane it turns on.
                const v = b ? via.get(w) : null;
                const tx = v ? A.x + v.x * K : sx;
                const own = ownOf(disc);
                // (and a pen's width off the middle of every other disc in
                // that half of the wall, where its own stub will most likely
                // stand)
                const midY = wall.y + wall.h / 2;
                // (and a pen's width off a run already leaving the same
                // disc the same way)
                const sibs = leftBy.get(spot(disc)) || [];
                const apart = (e, at) => sibs.every(o => o.edge !== e || Math.abs(o.at - at) >= 2 * pad)
                    && ((e !== 'top' && e !== 'bottom')
                        || (inbound[e].every(x => Math.abs(x - tx) < 0.01 || Math.abs(x - at) >= 2 * pad)
                            && discs.every(o => spot(o) === spot(disc) || (e === 'top' ? o.y > midY : o.y < midY)
                                                || Math.abs(o.x - at) >= 2 * pad)));
                const { edge, stub, cost } = this._bwExit(disc, wall, ink, own, pad, room, near, taken, apart);
                leftBy.set(spot(disc), sibs.concat([{ edge, at: stub.at }]));
                return { w, disc, b, v, tx, ty, sx, vy: null, edge, stub, cost, own, T, near };
            });

            // THE CHANNELS AGAIN, NOW THE STUBS ARE KNOWN. A run through a
            // channel goes up (or down) its lanes beside the stubs leaving
            // the wall's edge on that side, and where one stands within a
            // pen's width of a stub the two print as one line. So a run that
            // is that close is slid along its channel, between its
            // neighbours, to where it stands clear of every stub - nearest
            // its own socket where there is a choice - and the turns in the
            // corridor are nested again for the places the runs now have.
            // Where the corridor could not hold the lanes that would want,
            // the runs keep the places they were given.
            const runsOf = new Map();
            for (const p of plans) {
                if (!p.v) continue;
                const key = p.v.s + ':' + p.v.ri;
                if (!runsOf.has(key)) runsOf.set(key, []);
                runsOf.get(key).push(p);
            }
            const pen2 = 2 * pad, sp = LANE_STEP * K;
            for (const G of runsOf.values()) {
                const { s, ri } = G[0].v;
                // (and off the runs through the same gaps to another row)
                const stubs = plans.filter(q => q.edge === s).map(q => ({ x: q.stub.at, q }))
                    .concat(plans.filter(q => q.v && q.v.s === s && q.v.ri !== ri).map(q => ({ x: q.tx, q })));
                const clearOf = (p, x) => Math.min(pen2, ...stubs.filter(o => o.q !== p).map(o => Math.abs(o.x - x)));
                const was = G.map(p => p.tx);
                const inChannel = new Map();
                for (const p of G) {
                    const key = p.v.c0 + ':' + p.v.c1;
                    if (!inChannel.has(key)) inChannel.set(key, []);
                    inChannel.get(key).push(p);
                }
                // the places across the channel, chosen together: in their
                // sockets' order and a lane apart, as few as can be beside
                // a stub, and of those as near their sockets as they go
                for (const B of inChannel.values()) {
                    B.sort((p, q) => p.sx - q.sx);
                    const a = A.x + B[0].v.c0 * K, z = A.x + B[0].v.c1 * K, n = B.length;
                    const cand = B.map((p, q) => {
                        const lo = a + q * sp, hi = z - (n - 1 - q) * sp;
                        const xs = [p.sx, p.tx, lo, hi, ...stubs.flatMap(o => [o.x - pen2 - 0.01, o.x + pen2 + 0.01])];
                        return [...new Set(xs.map(x => Math.min(hi, Math.max(lo, x))))].sort((u, w) => u - w);
                    });
                    const price = (p, x) => (clearOf(p, x) < pen2 - 0.01 ? 1e6 : 0) + Math.abs(x - p.sx);
                    const best = [], back = [];
                    B.forEach((p, q) => {
                        best.push(cand[q].map(() => Infinity));
                        back.push(cand[q].map(() => -1));
                        cand[q].forEach((x, i) => {
                            if (!q) { best[q][i] = price(p, x); return; }
                            cand[q - 1].forEach((u, j) => {
                                if (u > x - sp + 0.001) return;
                                const c = best[q - 1][j] + price(p, x);
                                if (c < best[q][i]) { best[q][i] = c; back[q][i] = j; }
                            });
                        });
                    });
                    let i = best[n - 1].indexOf(Math.min(...best[n - 1]));
                    if (!(best[n - 1][i] < Infinity)) continue;
                    for (let q = n - 1; q >= 0; q--) {
                        B[q].tx = cand[q][i];
                        i = back[q][i];
                    }
                }
                // the corridor holds as many lanes as stand a pen and a
                // little air apart in it
                let L = this._bwTurns(G.map(p => ({ p, x: p.tx, t: p.sx })), CLR * K);
                if (corrOf(s, ri) * K / (L.n + 1) < pen2 + K) {
                    G.forEach((p, i) => { p.tx = was[i]; });
                    L = this._bwTurns(G.map(p => ({ p, x: p.tx, t: p.sx })), CLR * K);
                }
                // A RING (2026-11-20): two runs that change places, each up
                // its channel within a pen of the other's stub. The lanes by
                // the wall part a run's stub from a line it stands on by
                // turning that run nearer the wall (_bwNearLanes), but of two
                // such runs each would have to be nearer than the other, and
                // whichever is not prints its stub along the other's line.
                // So a run in a ring steps along its channel, between its
                // neighbours, off the other's stub - as little as it can -
                // where the corridor still holds the turns that wants.
                const onOf = (q) => (q.v ? q.tx : q.sx);
                const ups = plans.filter(q => q.edge === s && Number.isFinite(q.stub.at));
                const ring = (p, x) => p.edge === s && ups.some(q => q !== p
                    && Math.abs(x - q.stub.at) < pen2 && Math.abs(onOf(q) - p.stub.at) < pen2);
                for (const B of inChannel.values()) {
                    B.forEach((p, i) => {
                        if (!ring(p, p.tx)) return;
                        const a = Math.max(A.x + p.v.c0 * K, i ? B[i - 1].tx + sp : -Infinity);
                        const z = Math.min(A.x + p.v.c1 * K, i < B.length - 1 ? B[i + 1].tx - sp : Infinity);
                        const xs = [a, z, ...ups.flatMap(q => [q.stub.at - pen2 - 0.01, q.stub.at + pen2 + 0.01])]
                            .filter(x => x >= a - 0.01 && x <= z + 0.01 && !ring(p, x))
                            .sort((u, w) => Math.abs(u - p.tx) - Math.abs(w - p.tx));
                        if (!xs.length) return;
                        const at = p.tx;
                        p.tx = xs[0];
                        const L2 = this._bwTurns(G.map(q => ({ p: q, x: q.tx, t: q.sx })), CLR * K);
                        if (corrOf(s, ri) * K / (L2.n + 1) < pen2 + K) p.tx = at;
                        else L = L2;
                    });
                }
                for (const p of G) {
                    const step = corrOf(s, ri) * K / (L.n + 1);
                    const lane = L.of.has(p) ? L.of.get(p) : -1;
                    const k = lane < 0 ? (L.n - 1) / 2 : lane;
                    p.vy = s === 'top' ? p.b.y + p.b.h + (k + 1) * step : p.b.y - (k + 1) * step;
                }
            }

            plans.forEach((p) => {
                const { disc, tx, ty, vy, edge, stub, cost, own, near } = p;
                // is the socket already clear of the wall on the side this
                // run can travel? then the rail IS the way to it. Clear
                // means as far out as the first rail stands: a socket a
                // hair past the edge would run its line down the edge
                // discs' own rims (a wall grown to within two units of
                // one did exactly that)
                const clear = RAIL_OUT * K;
                const left = tx < wall.x - clear, right = tx > wall.x + wall.w + clear;
                const out = edge === 'left' ? left : edge === 'right' ? right : (left || right);
                // and if it is not, the side it travels is the one its
                // socket is nearer to, so the lane by the wall is short
                const side = edge === 'left' || edge === 'right' ? edge
                    : (tx - wall.x <= wall.x + wall.w - tx ? 'left' : 'right');
                // Straight down (or up) onto a socket already in line with
                // the disc, off the disc's edge AT THE SOCKET'S x - not at
                // the stub _bwExit weighed. So it is only taken where that
                // line is no dearer than the stub: a cable tag under the
                // disc is in its way, and then the run keeps its stub and
                // goes by the lane like any other (2026-11-02: once the
                // tags read the length alone, "50'" stood under a corner
                // disc, the stub stepped round it and the drop went through
                // it).
                let straight = false;
                if (edge === near && !stub.seam && Number.isFinite(tx) && Math.abs(tx - disc.x) < STRAIGHT * K
                        && !this._bwLong(disc, near, stub)) {
                    const dy = Math.sqrt(Math.max(0, disc.r * disc.r - (tx - disc.x) * (tx - disc.x)));
                    const head = [tx, near === 'top' ? disc.y - dy : disc.y + dy];
                    straight = this._bwCost(head, [tx, vy != null ? vy : ty], pad, ink, own) <= (cost || 0);
                }
                Object.assign(p, { side, out, straight });
            });

            // The rails, one per run that has to go along beside the wall,
            // nested so the fan does not knot: on the left the socket
            // furthest right takes the rail nearest the wall, on the right
            // the mirror of that. The runs to the boxes under the wall take
            // the rails nearest it, then those to the boxes over it.
            const bySide = (s, T) => plans
                .filter(p => p.T === T && p.side === s && !p.out && p.edge !== p.near)
                .sort((a, b) => s === 'left' ? b.tx - a.tx : a.tx - b.tx);
            const railX = new Map();
            const railed = { left: bySide('left', 'bottom').concat(bySide('left', 'top')),
                             right: bySide('right', 'bottom').concat(bySide('right', 'top')) };
            for (const s of ['left', 'right']) {
                const beside = s === 'left' ? wall.x - room.x0 : room.x1 - (wall.x + wall.w);
                const step = Math.min(RAIL_STEP * K,
                    Math.max(2 * K, (beside - RAIL_OUT * K) / Math.max(1, railed[s].length)));
                railed[s].forEach((p, i) => {
                    const d = RAIL_OUT * K + i * step;
                    railX.set(p, s === 'left' ? wall.x - d : wall.x + wall.w + d);
                });
            }

            // The lanes. By the wall on a box's side: every run coming
            // along a rail, and every run that left by that edge and is not
            // straight over (or under) its socket. On the far side: every
            // run that left by the far edge, from its own column across to
            // its socket or to the rail it comes along. The two sides of the
            // wall are woven together and the lanes handed out greedily, so
            // a left lane and a right lane that never meet are one lane and
            // cost the sheet no room.
            const weave = (l, r) => {
                const out2 = [];
                for (let i = 0; i < Math.max(l.length, r.length); i++) {
                    if (i < l.length) out2.push(l[i]);
                    if (i < r.length) out2.push(r[i]);
                }
                return out2;
            };
            const span = (p, a, b) => ({ p, lo: Math.min(a, b), hi: Math.max(a, b) });
            const acrossAt = (p) => (p.out ? p.tx : railX.get(p));
            const zone = (edge) => {
                const T = edge;   // the boxes this zone is the near side of
                const dropped = (s) => plans.filter(p => p.T === T && p.edge === p.near && p.side === s
                    && Number.isFinite(p.tx) && !p.straight);
                const nearL = railed.left.filter(p => p.T === T);
                const nearR = railed.right.filter(p => p.T === T);
                const nearSpans = weave(
                    nearL.map(p => span(p, railX.get(p), p.tx)).concat(dropped('left').map(p => span(p, p.stub.at, p.tx))),
                    nearR.map(p => span(p, railX.get(p), p.tx)).concat(dropped('right').map(p => span(p, p.stub.at, p.tx))));
                const far = plans.filter(p => p.T !== T && p.edge === edge);
                const farSpans = weave(
                    far.filter(p => acrossAt(p) < p.stub.at).sort((a, b) => a.stub.at - b.stub.at)
                        .map(p => span(p, p.stub.at, acrossAt(p))),
                    far.filter(p => acrossAt(p) >= p.stub.at).sort((a, b) => b.stub.at - a.stub.at)
                        .map(p => span(p, p.stub.at, acrossAt(p))));
                // (a near run's line up from the wall is its stub, or the
                // rail it came along; its line on, its drop or its channel:
                // _bwNearLanes keeps the one off the other)
                const upOf = (it) => (railX.has(it.p) ? railX.get(it.p) : it.p.stub.at);
                const nNear = this._bwNearLanes(nearSpans, upOf, (it) => it.p.tx, 2 * pad);
                const nFar = this._bwLanes(farSpans);
                const n = nNear + nFar;
                // counted out from the wall: the near lanes first, nearest
                // the wall in the order they were handed out; the far lanes
                // beyond them, the first handed out furthest from the wall
                const k = new Map();
                for (const it of nearSpans) k.set(it.p, it.lane);
                for (const it of farSpans) k.set(it.p, n - 1 - it.lane);
                // evenly through the room the wall's head (or foot) was given
                const y = (p) => (edge === 'top'
                    ? overBot - (overBot - overTop) * (k.get(p) + 1) / (n + 1)
                    : underTop + (underBot - underTop) * (k.get(p) + 1) / (n + 1));
                return { n, y };
            };
            const overZ = zone('top'), underZ = zone('bottom');
            const nOver = overZ.n, nUnder = underZ.n;

            const runs = plans.map((p) => {
                const { w, disc, tx, ty } = p;
                const colour = isData ? (w.kind === 'return' ? backupInk : primaryInk)
                                      : hue.get(w.device.key);
                const pattern = printer
                    ? (isData ? (w.kind === 'return' ? PRINTER_RETURN_DASH : []) : dash.get(w.device.key))
                    : (isData && w.kind === 'return' ? RETURN_DASH : []);
                const nearZ = p.near === 'top' ? overZ : underZ;
                const farZ = p.near === 'top' ? underZ : overZ;
                const nearY = () => nearZ.y(p);
                const at = p.stub.at;
                const pts = [p.stub.head, ...(p.stub.lead || [])];
                if (p.edge === 'left' || p.edge === 'right') {
                    // out at its own row, and on to its box - at its socket
                    // where the socket is already outside the wall on this
                    // side, else along the rail and a lane by the wall's edge
                    if (p.out) pts.push([tx, at]);
                    else {
                        const rx = railX.get(p);
                        pts.push([rx, at], [rx, nearY()], [tx, nearY()]);
                    }
                } else if (p.edge !== p.near) {
                    // out of its own column by the far edge, across there,
                    // and back - beside the wall to its socket, or along the
                    // rail and a lane by the edge its box is on
                    const oy = farZ.y(p);
                    const toX = p.out ? tx : railX.get(p);
                    pts.push([at, oy], [toX, oy]);
                    if (!p.out) pts.push([toX, nearY()], [tx, nearY()]);
                } else if (p.straight) {
                    // already outside its socket and in line with it:
                    // straight on, off the disc's own edge onto the socket
                    const off = Math.sqrt(Math.max(0, disc.r * disc.r - (tx - disc.x) * (tx - disc.x)));
                    pts.length = 0;
                    pts.push([tx, p.near === 'top' ? disc.y - off : disc.y + off]);
                } else {
                    pts.push([at, nearY()], [tx, nearY()]);
                }
                // up (or down) its channel past the inner row, along the
                // corridor, and into its socket
                if (p.vy != null) pts.push([tx, p.vy], [p.sx, p.vy]);
                pts.push([p.sx, ty]);
                return { kind: w.kind, from: w.stub.text, device: w.device.title, socket: w.socket,
                         colour, dash: pattern.map(v => v * K), width: RUN_W * K,
                         points: this._bwTidy(pts), seam: !!p.stub.seam, through: !!p.v,
                         gap: p.v ? [A.x + p.v.c0 * K, A.x + p.v.c1 * K] : null };
            });
            // The rev 1.1 lanes stand as they were placed; only two runs
            // that print as one are nudged apart (see _bwNudge) - and never
            // onto a box they were not already going into.
            const blockInk = blocks.map(b => ({ kind: 'block', x: b.x, y: b.y, w: b.w, h: b.h }));
            this._bwNudge(runs, wall, room, ink.concat(blockInk), (RUN_W + CASE_EXTRA) * K);
            return { discs, runs, blocks, over: nOver, under: nUnder, room,
                     railed: railed.left.concat(railed.right).map(p => p.w.stub.text + '>' + p.w.device.title + '#' + p.w.socket),
                     railedLeft: railed.left.length, railedRight: railed.right.length };
        };

        // A wall of a given growth: the runs laid once to count the lanes
        // they want, the gaps by the wall given exactly those lanes, and the
        // runs laid again - until the lanes they want are the lanes they
        // have (a gap only ever grows after its first fitting, so this
        // settles).
        const layoutAt = (grow) => {
            let gap = { ...gap0 };
            let Wc = wallAt(gap, grow);
            placeDiscs(Wc.geo);
            let e = draw(new Map(), null, Wc);
            for (let i = 0; i < 3; i++) {
                const want = gapFor(e.over, e.under);
                if (want.top === gap.top && want.bottom === gap.bottom) break;
                gap = i ? { top: Math.max(gap.top, want.top), bottom: Math.max(gap.bottom, want.bottom) } : want;
                Wc = wallAt(gap, grow);
                placeDiscs(Wc.geo);
                e = draw(new Map(), null, Wc);
            }
            return { W: Wc, runs: e, grow };
        };
        // What a layout costs the reader: the runs that come down a rail,
        // the runs that drop straight, and the crossings.
        const reading = (L) => {
            const straight = new Set(L.runs.runs.filter(r => r.points.length === 2
                || (r.points.length === 3 && Math.abs(r.points[0][1] - r.points[1][1]) < 0.01))
                .map(r => r.from + '>' + r.device + '#' + r.socket));
            return { railed: new Set(L.runs.railed), straight, cross: this._bwCrossings(L.runs.runs) };
        };
        let L = layoutAt(null);
        // `grown`: the wall grows while the runs read no worse than they do
        // round the wall rev 1.1 drew - first the whole room, then halving
        // back towards rev 1.1's wall until a growth that reads as well is
        // found. The rails keep the room the runs that take one need, and
        // where none does the wall may reach the sheet's margins - the
        // owner, 2026-10-18, of a wall held well inside them: "could be
        // much bigger if it is scaled up".
        const base = reading(L);
        const nRail = Math.max(L.runs.railedLeft, L.runs.railedRight);
        const rail = Math.min(railRoom, nRail ? RAIL_OUT + nRail * RAIL_STEP + RAIL_STEP : 0);
        const asGood = (C) => {
            const r = reading(C);
            for (const k of r.railed) if (!base.railed.has(k)) return false;
            for (const k of base.straight) if (!r.straight.has(k)) return false;
            return r.cross <= base.cross;
        };
        let best = null;
        const full = layoutAt({ t: 1, rail });
        if (asGood(full)) best = full;
        else {
            let lo = 0, hi = 1;
            for (let i = 0; i < GROW_STEPS; i++) {
                const mid = (lo + hi) / 2;
                const C = layoutAt({ t: mid, rail });
                if (asGood(C)) { lo = mid; best = C; } else hi = mid;
            }
        }
        if (best) L = best;
        // the discs stand where the chosen wall puts them
        W = L.W;
        placeDiscs(W.geo);
        const geo = W.geo;
        const wall = wallOf(W);
        const first = draw(new Map(), null, W);
        const unplaced = facts.stubs.length - facts.wires.length;
        return { side, view, K, A, mapArea: W.mapArea, wallRoom: W.room, geo, wall, printer, isData,
                 blocks: first.blocks, discs: first.discs, runs: first.runs, room: first.room,
                 redraw: (placed, letters) => draw(placed, letters, W),
                 rows: nRows, rowsTop: arr.n.top, rowsBottom: arr.n.bottom,
                 gap: { top: W.gap.top * K, bottom: W.gap.bottom * K },
                 lanes: { over: first.over, under: first.under },
                 pitch: fit * K, grow: L.grow ? L.grow.t : 0, head: W.head * K,
                 spare: W.spare || 0, rail: L.grow ? L.grow.rail * K : null, availW: availW * K,
                 unplaced, total: facts.stubs.length, facts,
                 // the rows past the first: the corridor each row turns in
                 // (in page units) and every step taken to keep a gap open
                 across: across ? {
                     corridor: { top: corridor.top.map(h => (h == null ? null : Math.max(ROW_GAP, h) * K)),
                                 bottom: corridor.bottom.map(h => (h == null ? null : Math.max(ROW_GAP, h) * K)) },
                     log: across.log } : null };
    }

    // How many times a run crosses a run: a horizontal of one through a
    // vertical of another, strictly inside both.
    _bwCrossings(runs) {
        const segs = runs.map(r => {
            const hs = [], vs = [];
            for (let i = 1; i < r.points.length; i++) {
                const a = r.points[i - 1], b = r.points[i];
                if (Math.abs(a[1] - b[1]) < 0.01) hs.push([Math.min(a[0], b[0]), Math.max(a[0], b[0]), a[1]]);
                else if (Math.abs(a[0] - b[0]) < 0.01) vs.push([Math.min(a[1], b[1]), Math.max(a[1], b[1]), a[0]]);
            }
            return { hs, vs };
        });
        let n = 0;
        for (let i = 0; i < segs.length; i++) {
            for (let j = 0; j < segs.length; j++) {
                if (i === j) continue;
                for (const [x0, x1, y] of segs[i].hs) {
                    for (const [y0, y1, x] of segs[j].vs) {
                        if (x > x0 + 0.01 && x < x1 - 0.01 && y > y0 + 0.01 && y < y1 - 0.01) n++;
                    }
                }
            }
        }
        return n;
    }

    // A path with its useless points taken out: a corner that goes nowhere,
    // and a bend that is no bend at all. Two segments where two suffice.
    _bwTidy(points) {
        const out = [];
        for (const p of points) {
            const last = out[out.length - 1];
            if (last && Math.abs(last[0] - p[0]) < 0.01 && Math.abs(last[1] - p[1]) < 0.01) continue;
            out.push(p);
        }
        for (let i = 1; i < out.length - 1;) {
            const a = out[i - 1], b = out[i], c = out[i + 1];
            if ((Math.abs(a[0] - b[0]) < 0.01 && Math.abs(b[0] - c[0]) < 0.01)
                    || (Math.abs(a[1] - b[1]) < 0.01 && Math.abs(b[1] - c[1]) < 0.01)) {
                out.splice(i, 1);
            } else i++;
        }
        return out;
    }

    // NUDGE APART ONLY WHERE THEY TOUCH. The rails stand where rev 1.1 stood
    // them (2026-09-12, "whatever was in here") and that layout stays. But
    // on one show's SR and SL Data Wiring sheets it stood SR-9's rail 8.4
    // units beside SR-13's straight drop, and SR-6's beside SR-4's, over
    // some 340 units of shared height - closer than one run's pen and its
    // white casing (12.7 at that sheet's scale), so each pair printed as one
    // line. The owner, shown them (2026-09-24): "Nudge apart only where they
    // touch".
    //
    // So once the lanes are placed, two parallel segments of DIFFERENT runs
    // whose centrelines stand closer than one run's full drawn width (`pen`:
    // the pen and the casing either side of it, at the sheet's scale) over a
    // stretch they share are pulled apart - one of them moves outward, away
    // from the wall, just far enough to clear the other. Only a segment
    // between two corners can move (a run's first leaves its disc, its last
    // lands on its socket); its neighbours stretch to meet it, so the corners
    // stay joined and the run stays square. Of two that could move, the one
    // further from the wall - the later lane - goes. A move that would leave
    // the room the runs travel in, fold a neighbour back on itself, or put
    // the run on the map's lettering is not made. After every move the sheet
    // is looked at again, so a nudge that brings a run against a third one
    // moves that one on too. A run that touches nothing does not move by a
    // hair: where there was no clash the drawing is rev 1.1's exactly.
    _bwNudge(runs, wall, room, ink, pen) {
        const E = 0.01;
        // every straight segment: `k` is the axis it stands at (0 = a
        // vertical at x, 1 = a horizontal at y), lo..hi the stretch it covers
        const segsOf = (ri) => {
            const p = runs[ri].points, out = [];
            for (let j = 0; j < p.length - 1; j++) {
                const a = p[j], b = p[j + 1];
                const k = Math.abs(a[0] - b[0]) < E ? 0 : Math.abs(a[1] - b[1]) < E ? 1 : -1;
                if (k < 0) continue;
                out.push({ ri, j, k, c: a[k], lo: Math.min(a[1 - k], b[1 - k]),
                           hi: Math.max(a[1 - k], b[1 - k]), movable: j > 0 && j < p.length - 2 });
            }
            return out;
        };
        const edge = (k) => k === 0 ? [wall.x, wall.x + wall.w] : [wall.y, wall.y + wall.h];
        const bound = (k) => k === 0 ? [room.x0, room.x1] : [room.y0, room.y1];
        const outward = (s) => {
            const [e0, e1] = edge(s.k);
            return s.c < e0 ? -1 : s.c > e1 ? 1 : (s.c < (e0 + e1) / 2 ? -1 : 1);
        };
        const fromWall = (s) => {
            const [e0, e1] = edge(s.k);
            return s.c < e0 ? e0 - s.c : s.c > e1 ? s.c - e1 : 0;
        };
        const boxOf = (a, b) => ({ x: Math.min(a[0], b[0]) - pen / 2, y: Math.min(a[1], b[1]) - pen / 2,
                                   w: Math.abs(a[0] - b[0]) + pen, h: Math.abs(a[1] - b[1]) + pen });
        const over = (a, b) => Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 0.5
                            && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 0.5;
        // A horizontal and a vertical meeting strictly inside both, and how
        // many times a run (on given points) meets the others so.
        const cuts = (a, b, c, d) => {
            const ah = Math.abs(a[1] - b[1]) < E, av = Math.abs(a[0] - b[0]) < E;
            const ch = Math.abs(c[1] - d[1]) < E, cv = Math.abs(c[0] - d[0]) < E;
            const [h, v] = ah && cv ? [[a, b], [c, d]] : av && ch ? [[c, d], [a, b]] : [null, null];
            if (!h) return false;
            const x = v[0][0], y = h[0][1];
            return x > Math.min(h[0][0], h[1][0]) + E && x < Math.max(h[0][0], h[1][0]) - E
                && y > Math.min(v[0][1], v[1][1]) + E && y < Math.max(v[0][1], v[1][1]) - E;
        };
        const crossOf = (ri, p) => {
            let n = 0;
            runs.forEach((r, rj) => {
                if (rj === ri) return;
                const q = r.points;
                for (let i = 1; i < p.length; i++) {
                    for (let j = 1; j < q.length; j++) if (cuts(p[i - 1], p[i], q[j - 1], q[j])) n++;
                }
            });
            return n;
        };
        const wallBox = { x: wall.x, y: wall.y, w: wall.w, h: wall.h };
        const tryMove = (s, to, inward = false, crossing = false) => {
            // a stretch inside the wall stays on its seam: moved, it would
            // lie along the screen's own chain
            const pa = runs[s.ri].points[s.j], pb = runs[s.ri].points[s.j + 1];
            const inX = (x) => x > wall.x + E && x < wall.x + wall.w - E;
            const inY = (y) => y > wall.y + E && y < wall.y + wall.h - E;
            if ((inX(pa[0]) && inY(pa[1])) || (inX(pb[0]) && inY(pb[1]))) return false;
            const [b0, b1] = bound(s.k);
            if (to < b0 || to > b1) return false;
            const old = runs[s.ri].points;
            const p = old.map(q => q.slice());
            p[s.j][s.k] = to;
            p[s.j + 1][s.k] = to;
            // the corners either side keep their sense - a neighbour only
            // stretches or shortens, it never folds back or vanishes
            for (const [q, r] of [[s.j - 1, s.j], [s.j + 2, s.j + 1]]) {
                const was = old[r][s.k] - old[q][s.k], now = p[r][s.k] - p[q][s.k];
                if (Math.abs(now) < E || Math.sign(now) !== Math.sign(was)) return false;
            }
            // and none of the three it touches lands on lettering it was not
            // already beside (the stub off its own disc is on that disc) -
            // nor, moved towards the wall, on the wall itself
            const marks = inward ? ink.concat([wallBox]) : ink;
            for (let j = s.j - 1; j <= s.j + 1; j++) {
                const was = boxOf(old[j], old[j + 1]), now = boxOf(p[j], p[j + 1]);
                if (marks.some(k => over(now, k) && !over(was, k))) return false;
            }
            // and pulling two runs apart makes a run cross one it did not
            // cross before only where nothing else will part them: a run
            // through a channel nudged off a stub beside it went over its
            // neighbour's line to the next socket. Two lines printed as one
            // are still worse than one more crossing.
            if (!crossing && crossOf(s.ri, p) > crossOf(s.ri, old)) return false;
            runs[s.ri].points = p;
            return true;
        };
        const skip = new Set();
        const clash = () => {
            const all = runs.map((_r, ri) => segsOf(ri));
            for (let r1 = 0; r1 < runs.length; r1++) {
                for (let r2 = r1 + 1; r2 < runs.length; r2++) {
                    for (const a of all[r1]) {
                        for (const b of all[r2]) {
                            if (a.k !== b.k || Math.abs(a.c - b.c) >= pen) continue;
                            if (Math.min(a.hi, b.hi) - Math.max(a.lo, b.lo) <= E) continue;
                            if (skip.has(`${a.ri}.${a.j}/${b.ri}.${b.j}`)) continue;
                            return [a, b];
                        }
                    }
                }
            }
            return null;
        };
        for (let pass = 0; pass < 8 * runs.length; pass++) {
            const pair = clash();
            if (!pair) break;
            const [a, b] = pair;
            const movers = pair.filter(s => s.movable)
                .sort((s, t) => (fromWall(t) - fromWall(s)) || (t.ri - s.ri));
            // outward, as it always was. A run through a channel past a box
            // (`through`) is moved only where that crosses no run it did not
            // cross before - else away from the other run on the side it
            // already stands - and outward whatever it crosses only where
            // neither will do; every other run moves as it always did.
            const away = (m, dir) => (m === a ? b : a).c + dir * (pen + E);
            const moved = movers.some((m) => {
                if (!runs[m.ri].through) return false;
                const out = outward(m), own = Math.sign(m.c - (m === a ? b : a).c) || out;
                return tryMove(m, away(m, out))
                    || (own !== out && tryMove(m, away(m, own), true));
            }) || movers.some(m => tryMove(m, away(m, outward(m)), false, true));
            if (!moved) skip.add(`${a.ri}.${a.j}/${b.ri}.${b.j}`);
        }
        return runs;
    }

    // ---- the discs the wall really drew -------------------------------------

    // The map painted for this half, with every label disc the renderer laid
    // down noted as it went. The renderer sizes a disc through
    // _layoutCircleLabel and then sets its lines through _fillWrappedLabel at
    // the disc's own centre - the same `lines` array travels between the
    // two - so wrapping that pair for the length of one paint reports every
    // disc's centre and radius without a word of the placement being
    // guessed here. A renderer that cannot be wrapped simply reports none.
    _bwPaintMap(book, layer, view, area) {
        // (`layer` may be a sheet subject - _bMap takes either)
        const r = window.canvasRenderer;
        if (!r || typeof r._layoutCircleLabel !== 'function' || typeof r._fillWrappedLabel !== 'function') {
            return { geo: this._bMap(book, layer, view, area, GUT), discs: null, labels: [] };
        }
        // Every piece of lettering the map lays down, so a run can be kept
        // off it: canvas.js's own label registry, which knows a disc from a
        // cable tag from a plain cabinet. It records in the BITMAP's pixels
        // and the bitmap is laid at `area` at S of them to the page unit,
        // so the boxes come back in page units. _bMap is re-entrant on the
        // probe, so starting one here simply lends it the same array.
        const S = this._bMapScale(book) * ((book.fill && book.fill.s) || 1);
        // Re-entrant, exactly as _bMap's own probe is: a caller already
        // probing this render (the label-collision suite is one) keeps its
        // array and we read the stretch this map added to it.
        const outer = r.labelProbe;
        const outerLen = outer ? outer.length : 0;
        const probe = outer || (typeof r.startLabelProbe === 'function' ? r.startLabelProbe() : null);
        // This sheet gives the map NO gutter, so the bitmap is the wall and
        // what stands astride a member's edge (_bAstride), and nothing else:
        // the multi band pill and the circuit ruler the map draws over the
        // wall's head fall outside it and are clipped away. Ink that never
        // reaches the paper cannot be covered, so it is not read as
        // lettering here.
        const carry = (used) => {
            if (!probe) return [];
            const boxes = outer ? outer.slice(outerLen) : r.endLabelProbe();
            const w = (used ? used.w : area.w) * S, h = (used ? used.h : area.h) * S;
            return (boxes || [])
                .filter(b => b && b.kind !== 'wallEdge'
                    && b.x + b.w > 0 && b.y + b.h > 0 && b.x < w && b.y < h)
                .map(b => ({ kind: b.kind, text: b.text, x: area.x + b.x / S, y: area.y + b.y / S,
                             w: b.w / S, h: b.h / S }));
        };
        const radii = new WeakMap();
        const seen = [];
        const layout = r._layoutCircleLabel, lines = r._fillWrappedLabel;
        // a split map's stage passes paint the discs again (_bSplitMapPair):
        // only the whole render's are this sheet's
        const app = this;
        // put back exactly what was there: an own property is restored, an
        // inherited one is uncovered
        const own = [Object.getOwnPropertyDescriptor(r, '_layoutCircleLabel'),
                     Object.getOwnPropertyDescriptor(r, '_fillWrappedLabel')];
        r._layoutCircleLabel = function (...a) {
            const out = layout.apply(this, a);
            if (!app._binderQuietPass && out && Array.isArray(out.lines) && Number.isFinite(out.radius)) {
                radii.set(out.lines, out.radius);
            }
            return out;
        };
        r._fillWrappedLabel = function (ls, x, y) {
            if (Array.isArray(ls) && radii.has(ls) && Number.isFinite(x) && Number.isFinite(y)) {
                // Where the disc landed on the bitmap, carried through the
                // transform it was painted under, then onto the page. x, y
                // alone name no place: a screen's own disc is painted in
                // that screen's frame, and a run across a group's members
                // in the wall's frame after every member is down
                // (_renderCrossMemberPaths). Where a member's Show Look
                // offset is not nil, the two differ by that offset.
                const m = this.ctx.getTransform();
                seen.push({ key: ls.join('').replace(/\s+/g, ''),
                            x: area.x + (m.a * x + m.c * y + m.e) / S,
                            y: area.y + (m.b * x + m.d * y + m.f) / S,
                            r: radii.get(ls) * Math.hypot(m.a, m.b) / S });
            }
            return lines.apply(this, arguments);
        };
        try {
            const geo = this._bMap(book, layer, view, area, GUT);
            // a member's sheet reads only the lettering left on its bitmap
            const labels = carry(geo && geo.area).filter(k => !geo || geo.keep(k));
            return { geo, discs: seen, labels };
        } finally {
            delete r._layoutCircleLabel;
            delete r._fillWrappedLabel;
            if (own[0]) Object.defineProperty(r, '_layoutCircleLabel', own[0]);
            if (own[1]) Object.defineProperty(r, '_fillWrappedLabel', own[1]);
            if (!outer && r.labelProbe) r.endLabelProbe();
        }
    }

    // Each stub against the disc the wall drew for it: the one whose label
    // reads the same (spaces are the wrap's, not the label's) and whose
    // centre is nearest the panel the stub belongs to. A stub the render
    // never labelled keeps the measured disc. `seen` is in page units
    // (_bwPaintMap), so a disc stands where the bitmap has it, whatever
    // frame it was painted in.
    _bwSeat(facts, geo, seen) {
        const placed = new Map();
        if (!geo || !seen || !seen.length) return placed;
        const by = new Map();
        for (const d of seen) {
            if (!by.has(d.key)) by.set(d.key, []);
            by.get(d.key).push(d);
        }
        for (const st of facts.stubs) {
            // a box at a circuit's end leaves the run's last panel, not the
            // label (_bwPowerFacts)
            if (st.end) continue;
            const list = by.get(String(st.text).replace(/\s+/g, ''));
            if (!list || !list.length) continue;
            const p = st.panel;
            const pr = geo.rect(p.x, p.y, p.width, p.height, st.layer || undefined);
            const cx = pr.x + pr.w / 2, cy = pr.y + pr.h / 2;
            // only a disc this sheet shows: on a member's sheet a crossing
            // port's label can stand on the other member, cut off the map
            // (its stub then keeps the disc measured on this member)
            let best = null, bestD = Infinity;
            for (const d of list) {
                const rcd = { x: d.x - d.r, y: d.y - d.r, w: 2 * d.r, h: 2 * d.r };
                if (typeof geo.keep === 'function' && !geo.keep(rcd)) continue;
                const v = (d.x - cx) * (d.x - cx) + (d.y - cy) * (d.y - cy);
                if (v < bestD) { best = d; bestD = v; }
            }
            if (!best) continue;
            placed.set(st, { x: best.x, y: best.y, r: best.r,
                             panel: { x: pr.x, y: pr.y, w: pr.w, h: pr.h } });
        }
        return placed;
    }

    // ---- the paint ----------------------------------------------------------

    _bwDrawHalf(book, target, P) {
        const subject = this._bSubject(target);
        const layer = subject.carriers[0];
        const ctx = book.ctx;
        const K = P.K;
        const A = P.A;
        const printer = P.printer;
        // no head word over the wall: the sheet's own title names the side
        // the wall - the same render, painted now, its own discs on it and
        // noted as they go, so the runs leave the discs that are really there
        const painted = this._bwPaintMap(book, subject, P.view, P.mapArea);
        const geo = painted.geo;
        if (P.redraw) {
            // The runs are laid again on what the wall REALLY drew: the
            // discs where the renderer put them, and its own lettering from
            // the label registry, so a run's way out of the wall is chosen
            // knowing what is beside it.
            const seated = this._bwSeat(P.facts, geo, painted.discs);
            const letters = painted.labels || [];
            if (seated.size || letters.length) {
                const again = P.redraw(seated, letters);
                P = { ...P, discs: again.discs, runs: again.runs, room: again.room,
                      lanes: { over: again.over, under: again.under } };
            }
        }
        const log = book.log && book.page && book.page.painting ? {
            side: P.side, scale: K, fit: P.fit || 1, rows: P.rows, pitch: P.pitch, grow: P.grow || 0, head: P.head || 0,
            rowsTop: P.rowsTop || 0, rowsBottom: P.rowsBottom || 0,
            spare: P.spare || 0, rail: P.rail, availW: P.availW,
            gap: P.gap || null, lanes: P.lanes || null,
            area: { x: A.x, y: A.y, w: A.w, h: A.h },
            within: P.within || { x: A.x, y: A.y, w: A.w, h: A.h },
            wallRoom: P.wallRoom ? { x: P.wallRoom.x, y: P.wallRoom.y, w: P.wallRoom.w, h: P.wallRoom.h } : null,
            map: geo ? { x: geo.wall.x, y: geo.wall.y, w: geo.wall.w, h: geo.wall.h,
                         zoom: geo.zoom, area: geo.area } : null,
            room: P.room || null, across: P.across || null,
            discs: [], runs: [], blocks: [], unplaced: P.unplaced, total: P.total,
        } : null;

        // the blocks: the name INSIDE, on its own line under the sockets
        for (const b of P.blocks) {
            this._bwRound(ctx, b.x, b.y, b.w, b.h, BOX_R * K, WHITE, b.rim, BOX_RIM * K);
            const title = this._bText(book, b.title, b.x + PAD * K, b.titleY || (b.y + TITLE_DY * K),
                                      { size: CAPTION_SZ * K, weight: 700, color: b.rim,
                                        maxWidth: b.w - 2 * PAD * K, shrink: true });
            const groups = b.inputs ? this._bwDrawInputs(book, ctx, b) : null;
            const entry = log ? { title, key: b.key, x: b.x, y: b.y, w: b.w, h: b.h,
                                  side: b.side || 'bottom', row: b.row, noteY: b.noteY, rim: b.rim, hue: b.hue, dash: b.dash, sockets: [],
                                  titleY: b.titleY, inputs: groups } : null;
            for (const sk of b.sockets) {
                const fill = !sk.on ? WHITE
                    : printer ? ((P.isData && sk.kind === 'return') ? WHITE : INK)
                    : (P.isData ? (sk.kind === 'return' ? (layer.backupColor || '#FF0000')
                                                        : (layer.primaryColor || '#00FF00'))
                                : b.hue);
                const rim = sk.on ? (fill === WHITE ? INK : fill) : GREY_RING;
                if (fill !== WHITE) this._bwSolid(ctx, sk.x, sk.y, sk.r, fill);
                this._bwRing(ctx, sk.x, sk.y, sk.r, rim, SOCKET_RIM * K);
                this._bText(book, String(sk.n), sk.x, sk.y + NUMBER_SZ * K * 0.375,
                            { size: NUMBER_SZ * K, weight: 700, align: 'center',
                              color: sk.on ? (fill === WHITE ? INK : WHITE) : GREY_INK });
                // A SOCKET'S NOTE NEVER UNDER A LINE. A run comes into its
                // socket across the note's line, so the note of a socket a
                // run comes into stands BESIDE that run, to its right and
                // short of the next socket's run (owner's rule: no line
                // crosses a box's lettering); a socket no run comes into
                // keeps its note centred on it, short of the runs either
                // side of it.
                let noteBox = null;
                if (sk.note && b.pitch > 0) {
                    const ny = b.noteY != null ? b.noteY : b.y + NOTE_DY * K;
                    const clear = (RUN_W + CASE_EXTRA) / 2 * K + 2 * K;
                    const i = b.sockets.indexOf(sk);
                    const lineAt = (q) => (q && q.on ? q.x : null);
                    const prev = b.sockets[i - 1], next = b.sockets[i + 1];
                    const style = { size: NOTE_SZ * K, weight: 400, shrink: true };
                    let x = sk.x, align = 'center', room = b.pitch * 2.4;
                    if (sk.on) {
                        const end = lineAt(next) != null ? next.x - clear
                            : next ? next.x - next.r : b.x + b.w - PAD * K / 2;
                        x = sk.x + clear;
                        align = 'left';
                        room = Math.max(0, end - x);
                    } else {
                        const left = lineAt(prev) != null ? sk.x - prev.x - clear : room / 2;
                        const right = lineAt(next) != null ? next.x - sk.x - clear : room / 2;
                        room = Math.max(0, 2 * Math.min(room / 2, left, right));
                    }
                    // (no room at all beside it: no note rather than one under a line)
                    if (room >= 1) {
                        const nw = Math.min(room, this._bTextWidth(book, sk.note, { ...style, maxWidth: room }));
                        this._bText(book, sk.note, x, ny,
                                    { ...style, align, color: sk.on ? MUTED : GREY_INK, maxWidth: room });
                        noteBox = { x: align === 'left' ? x : x - nw / 2, y: ny - NOTE_SZ * K * 0.75,
                                    w: nw, h: NOTE_SZ * K };
                    }
                }
                if (entry) entry.sockets.push({ n: sk.n, x: sk.x, y: sk.y, r: sk.r,
                                                state: sk.state, note: sk.note, fill, rim, noteBox });
            }
            if (log) log.blocks.push(entry);
        }

        // the wall's own discs are the origin - no second tag is drawn. On
        // power the breakout's hue is carried to them as a ring, so a run
        // and the disc it leaves read as one.
        for (const d of P.discs) {
            if (d.end && d.r > 0) {
                // a box fed from a run's last panel: no label there, so a
                // dot marks where its line leaves (owner, 2026-11-19)
                this._bwSolid(ctx, d.x, d.y, d.r, printer ? INK : (d.hue || INK));
            } else if (!printer && !P.isData && d.hue && d.r > 0) {
                this._bwRing(ctx, d.x, d.y, d.r, d.hue, DISC_RIM * K);
            }
            if (log) log.discs.push({ kind: d.kind, text: d.text, x: d.x, y: d.y, r: d.r,
                                      panel: d.panel, placed: d.placed, ...(d.end ? { end: true } : {}) });
        }

        // the runs, last, so a line can be followed over everything it
        // crosses - each drawn twice, the white casing first
        for (const r of P.runs) {
            this._bwPath(ctx, r.points, WHITE, r.width + CASE_EXTRA * K, []);
            this._bwPath(ctx, r.points, r.colour, r.width, r.dash);
            if (log) log.runs.push({ kind: r.kind, from: r.from, device: r.device, socket: r.socket,
                                     colour: r.colour, dash: r.dash, width: r.width,
                                     points: r.points.map(p => [p[0], p[1]]), seam: !!r.seam,
                                     through: !!r.through, gap: r.gap || null });
        }

        if (P.unplaced) {
            this._bText(book, `${P.unplaced} of ${P.total} not placed on any ${this.showUnitWord()}, no run to draw`,
                        A.x, A.y + A.h - 4 * K, { size: NOTE_SZ * K * 1.15, weight: 400, color: MUTED });
        }
        if (log) book.log.wiring.halves.push(log);
        // the wall it drew, for a caller that rules it (the simple sheet)
        return geo;
    }

    // A run's path, one polyline through the recorder.
    _bwPath(ctx, points, colour, width, dash) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.setLineDash(dash || []);
        ctx.beginPath();
        points.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // A rounded rectangle through the recorder's vocabulary: the fill as
    // three rects and four quarter discs (arcs stroked as wide as the
    // corner radius), the outline as one polyline.
    // A box's inputs as the wiring sheet draws them - [{ head: 'X1',
    // strands: [{ text, swatch }] }] in the order its links run (primaries,
    // then the backup inputs), each input's strands in the order they plug
    // in AT THE BOX (_bStrandPiecesAtBox: a TAC's pair flipped, an MTP's
    // real legs by its polarity, as FIBER CONNECTIONS' AT THE BREAKOUT
    // reads), named and swatched as the strand
    // map has them (_bStrandPiece - numbers with no swatch on a cable
    // labelled by number, sub-unit names as it prints them), after the
    // cable they are on (`sub`, _bBoxCableWords: "TAC A (TAC 12 SM)", the
    // data sheet's band word for word - "just listing the colors and
    // numbers makes no sense on a show with multiple fiber runs", owner,
    // 2026-11-05); a copper link its name, "Cat6A 1", a typed one with its
    // kind, "Stage left (Cat6A)" (copperLinkWords). Inputs with no cable and
    // no copper are left out, and a box with none on either is null.
    _bwBoxInputs(box) {
        const links = typeof this.fiberBoxLinks === 'function' ? this.fiberBoxLinks(box) : [];
        const on = links.filter(l => l.cable || l.copper);
        if (!on.length) return null;
        const typed = new Set();
        return on.map(l => {
            if (l.copper) return { head: l.title, strands: [{ text: this.copperLinkWords(l.copper), swatch: null }] };
            const what = this._bBoxCableWords(l.cable, typed);
            const pieces = this._bStrandPiecesAtBox(l.link, l.cable);
            return pieces.length
                ? { head: l.title, sub: what, strands: pieces }
                : { head: l.title, strands: [{ text: what, swatch: null }] };
        });
    }

    // A box's inputs as _bwPlanHalf placed them - side by side on the line
    // under the caption, or a line each where they are too long for one -
    // each group outlined: the input bold, its cable, then its strands, on
    // that line's baseline. Swatched as the
    // binder's strand map swatches, on either palette. Returns each group's
    // outline, for the log.
    _bwDrawInputs(book, ctx, b) {
        const I = b.inputs;
        const out = [];
        I.groups.forEach((g, gi) => {
            const at = I.at[gi];
            const base = b.titleY + at.line * I.line;
            const mid = base - I.size * 0.36;
            const box = { head: g.head, x: at.x, y: mid - I.line * 0.44, w: at.w, h: I.line * 0.88,
                          line: at.line, base };
            out.push(box);
            ctx.strokeStyle = MUTED;
            ctx.lineWidth = Math.max(0.5, I.size * 0.08);
            ctx.setLineDash([]);
            ctx.strokeRect(box.x, box.y, box.w, box.h);
            const x0 = at.x + I.pad;
            this._bText(book, g.head, x0, base, { size: I.size, weight: 700, color: INK });
            if (g.sub) this._bText(book, g.sub, x0 + I.head, base, { size: I.size, weight: 400, color: INK });
            let x = x0 + I.head + at.sub;
            for (const st of g.strands) {
                if (st.swatch) {
                    const sy = mid - I.sw / 2;
                    ctx.fillStyle = st.swatch.base || '#777777';
                    ctx.fillRect(x, sy, I.sw, I.sw);
                    if (st.swatch.tracer) {
                        ctx.fillStyle = st.swatch.tracer;
                        ctx.fillRect(x, sy + I.sw * 0.36, I.sw, I.sw * 0.28);
                    }
                    ctx.strokeStyle = INK;
                    ctx.lineWidth = Math.max(0.5, I.size * 0.08);
                    ctx.strokeRect(x, sy, I.sw, I.sw);
                    x += I.sw + 3 * (I.size / IN_SZ);
                }
                const t = this._bText(book, st.text, x, base, { size: I.size, weight: 400, color: INK });
                ctx.font = this._bFont(I.size, 400);
                x += ctx.measureText(String(t || st.text)).width + 6 * (I.size / IN_SZ);
            }
        });
        return out;
    }

    _bwRound(ctx, x, y, w, h, r, fill, stroke, width) {
        const rr = Math.max(0, Math.min(r, w / 2, h / 2));
        if (fill) {
            ctx.fillStyle = fill;
            ctx.fillRect(x + rr, y, w - 2 * rr, h);
            if (rr > 0) {
                ctx.fillRect(x, y + rr, rr, h - 2 * rr);
                ctx.fillRect(x + w - rr, y + rr, rr, h - 2 * rr);
                const corners = [[x + rr, y + rr, Math.PI, 1.5 * Math.PI], [x + w - rr, y + rr, 1.5 * Math.PI, 2 * Math.PI],
                                 [x + w - rr, y + h - rr, 0, 0.5 * Math.PI], [x + rr, y + h - rr, 0.5 * Math.PI, Math.PI]];
                ctx.strokeStyle = fill;
                ctx.lineWidth = rr;
                ctx.setLineDash([]);
                for (const [cx, cy, a0, a1] of corners) this._bwArc(ctx, cx, cy, rr / 2, a0, a1, 6);
            }
        }
        if (stroke) {
            ctx.strokeStyle = stroke;
            ctx.lineWidth = width || 2;
            ctx.setLineDash([]);
            ctx.beginPath();
            const seg = 6;
            const arc = (cx, cy, a0, a1) => {
                for (let i = 0; i <= seg; i++) {
                    const a = a0 + (a1 - a0) * i / seg;
                    ctx.lineTo(cx + rr * Math.cos(a), cy + rr * Math.sin(a));
                }
            };
            ctx.moveTo(x + rr, y);
            ctx.lineTo(x + w - rr, y);
            arc(x + w - rr, y + rr, 1.5 * Math.PI, 2 * Math.PI);
            ctx.lineTo(x + w, y + h - rr);
            arc(x + w - rr, y + h - rr, 0, 0.5 * Math.PI);
            ctx.lineTo(x + rr, y + h);
            arc(x + rr, y + h - rr, 0.5 * Math.PI, Math.PI);
            ctx.lineTo(x, y + rr);
            arc(x + rr, y + rr, Math.PI, 1.5 * Math.PI);
            ctx.lineTo(x + rr, y);
            ctx.stroke();
        }
    }

    // An arc as a short polyline, stroked with the context's pen.
    _bwArc(ctx, cx, cy, r, a0, a1, seg) {
        ctx.beginPath();
        for (let i = 0; i <= seg; i++) {
            const a = a0 + (a1 - a0) * i / seg;
            const px = cx + r * Math.cos(a), py = cy + r * Math.sin(a);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.stroke();
    }

    // A solid disc: a closed polyline at half the radius stroked as wide
    // as the radius. It runs a segment PAST its own start - a stroke that
    // stops exactly where it began leaves a wedge of a notch at the join,
    // and a notch in a socket reads as a mark that means something.
    _bwSolid(ctx, cx, cy, r, colour) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = r;
        ctx.setLineDash([]);
        this._bwArc(ctx, cx, cy, r / 2, 0, 2 * Math.PI * (25 / 24), 25);
    }

    // A ring: the same closed polyline at the radius.
    _bwRing(ctx, cx, cy, r, colour, width) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.setLineDash([]);
        this._bwArc(ctx, cx, cy, r, 0, 2 * Math.PI * (25 / 24), 25);
    }
}

for (const k of Object.getOwnPropertyNames(_BinderWiring.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_BinderWiring.prototype, k));
    }
}
