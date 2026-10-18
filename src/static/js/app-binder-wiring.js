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
// One view per sheet: "n  SR - MAIN · DATA WIRING", its bubble at the
// foot. Every figure is read from the same authorities the
// Power and Data sheets read - _pullPortRuns, _bPortHome,
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
// to be stacked. they can be side by side and on the same row as the name
// of the box"): each input a group - "X1" then its strands, each strand's
// swatch where the cable reads in colours - in the thin outline the
// Breakout boxes table groups an input in, set at the caption's size, the
// groups side by side on the caption's own row, to its right. Where that
// row cannot hold the caption and every group, the groups wrap to lines
// under the caption (_bwPlanHalf says when, and the box grows by those
// lines - every box on the sheet alike, so a row stays one height). Its
// type, the pitch of a wrapped line, the swatch, the outline's pad, the
// gap between two groups and the gap after the caption.
const IN_SZ = CAPTION_SZ, IN_LINE = 16, IN_SW = 9, IN_PAD = 3, IN_GAP = 6, IN_CAP_GAP = 12;
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
        const sheetTitle = `${subject.name} · ${power ? 'POWER' : 'DATA'} WIRING`;
        const area = this._bwArea(book);
        const plan = this._bwPlanHalf(book, subject, scr, side, area.half);
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
            this._bwDrawHalf(book, subject, plan);
            this._bViewBubble(book, view, sheetTitle, book.geo.da.x + 20, area.bubbleY);
        });
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
                // band carries.
                const title = home.box
                    ? [this._bBoxTitle(home.box), home.cardTitle, home.box.trunkTitle || ''].filter(Boolean).join(' · ')
                    : [home.unitTitle, home.named ? home.card.deviceName : ''].filter(Boolean).join(' · ');
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
            const bh = bb.cardId ? this._bPortHome(bb.cardId, bb.port) : null;
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
            // "SR1 · Multi 208 breakout · 125'"; a multi on no distro has no
            // type to name its breakout by and reads as the band does. A
            // DIRECT output is its own cable, no breakout: "SL5 · True1
            // 208V · 25'". A direct output carrying several circuits (the
            // flagged error state) has no one cable: its length is the
            // output's home run, and the caption says it is crowded.
            const crowd = box.crowded || 0;
            const caption = [box.name,
                             box.kind === 'direct' ? box.type
                                 : (box.type ? `${box.type} breakout` : 'no distro'),
                             box.homeRun ? this.pullLengthText(box.homeRun) : 'no length',
                             ...(crowd ? [`${crowd} circuits on a one-circuit output`] : [])]
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
    _bwDisc(book, rule, geo, panel, text, onLayer = null) {
        const p = panel;
        let rad = Math.min(p.width, p.height) / 3;
        if (rule.r && typeof rule.r._layoutCircleLabel === 'function') {
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
    _bwExit(d, wall, labels, own, pad, room, near = 'bottom') {
        const far = (e, at) => e === 'left' ? [room.x0, at] : e === 'right' ? [room.x1, at]
            : e === 'top' ? [at, room.y0] : [at, room.y1];
        const by = (names) => names
            .map(e => ({ e, s: this._bwStub(d, e, wall, 0) }))
            .sort((p, q) => (Math.abs(p.s.gap - q.s.gap) > 0.01 ? p.s.gap - q.s.gap
                : (p.e === near ? -1 : 0) - (q.e === near ? -1 : 0)));
        const sides = by(['left', 'right']), ends = by(['top', 'bottom']);
        const own0 = this._bwStub(d, near, wall, 0);
        if (own0.gap <= Math.max(sides[0].s.gap, 2 * d.r) + 0.01) {
            for (const off of _BinderWiring.OFFSETS) {
                const s = this._bwStub(d, near, wall, off);
                if (!this._bwCost(s.head, far(near, s.at), pad, labels, own)) return { edge: near, stub: s, cost: 0 };
            }
        }
        let best = null;
        for (const list of [sides, ends]) {
            for (const c of list) {
                for (const off of _BinderWiring.OFFSETS) {
                    const s = this._bwStub(d, c.e, wall, off);
                    const cost = this._bwCost(s.head, far(c.e, s.at), pad, labels, own);
                    if (!cost) return { edge: c.e, stub: s, cost: 0 };
                    if (!best || cost < best.cost) best = { edge: c.e, stub: s, cost };
                }
            }
        }
        return best;
    }

    // The lanes: every run that has to travel along one is given the lowest
    // lane whose marks it does not lie on top of, so two runs share a lane
    // wherever their stretches do not meet and the sheet spends no room it
    // does not need. Returns the lane each took and how many there are.
    _bwLanes(items) {
        const taken = [];
        for (const it of items) {
            let k = 0;
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

    // ---- the geometry -------------------------------------------------------

    // One half laid out in page units, nothing painted. The prototype's
    // page is 1000 wide; K carries its every number onto this half.
    _bwPlanHalf(book, target, scr, side, A) {
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
        const inLineW = (d, g) => inHead(d) + g.strands.reduce((s, st) =>
            s + (st.swatch ? IN_SW + 3 : 0) + measure(st.text, IN_SZ, 400) + 6, 0) - 6;
        const groupW = (d, g) => inLineW(d, g) + IN_PAD * 2;
        // a box is never narrower than its widest group, so a wrapped group
        // is never cut
        const inContent = (d) => (d.inputs ? Math.max(...d.inputs.map(g => groupW(d, g))) : 0);
        // the width that holds the caption and every group on one row
        const inRowW = (d) => (d.inputs ? capW(d) + IN_CAP_GAP + d.inputs.reduce((s, g) =>
            s + groupW(d, g), 0) + IN_GAP * (d.inputs.length - 1) + PAD * 2 : 0);
        // WHERE THE GROUPS GO in a box w wide: all on the caption's row,
        // after it, when the caption and every group fit there; otherwise
        // none of them - they wrap to lines under the caption, from its
        // left edge, each line taking groups in order while they fit (a
        // group is never split). `lines` is the lines added under the
        // caption; `at` each group's left edge and line, in box units.
        const inPlace = (d, w) => {
            if (!d.inputs) return null;
            const ws = d.inputs.map(g => groupW(d, g));
            const right = w - PAD + 0.01;
            if (inRowW(d) <= w + 0.01) {
                let x = PAD + capW(d) + IN_CAP_GAP;
                return { lines: 0, at: ws.map(v => { const a = { x, line: 0 }; x += v + IN_GAP; return a; }) };
            }
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
        // A box in the row FURTHEST FROM THE WALL on its side is widened to
        // put its groups on the caption's row where that row has the room:
        // the pitch and the rows are settled first, so the inputs never
        // squeeze the sockets or push a box onto another row, and only that
        // row - no run passes through it on its way to a socket - so a wider
        // box never stands in a run's way. The cheapest widening goes first.
        const wide = new Map();
        const widen = (farRows) => {
            wide.clear();
            for (const last of farRows) {
                let room = availW - last.reduce((s, d) => s + boxW(d), 0) - MIN_BOX_GAP * Math.max(0, last.length - 1);
                const want = last.map(d => ({ d, more: inRowW(d) - boxW(d) }))
                    .filter(o => o.d.inputs && o.more > 0).sort((a, b) => a.more - b.more);
                for (const o of want) {
                    if (o.more > room + 0.01) break;
                    wide.set(o.d.key, boxW(o.d) + o.more);
                    room -= o.more;
                }
            }
        };
        const widthOf = (d) => wide.get(d.key) || boxW(d);
        // the lines under the caption: the most any box needs sets every
        // box's height on the sheet
        const heightOf = () => BOX_H + IN_LINE * Math.max(0,
            ...devices.map(d => { const pl = inPlace(d, widthOf(d)); return pl ? pl.lines : 0; }));
        let BOXH = heightOf();

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
        const stackH = (n) => (n ? n * BOXH + (n - 1) * ROW_GAP : 0);
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
            const head = stackH(rowsOn.top) + gap.top;
            const tail = gap.bottom + stackH(rowsOn.bottom);
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
        const wallOf = (Wc) => (Wc.geo ? Wc.geo.wall : { x: A.x, y: Wc.mapArea.y, w: A.w, h: 0 });

        // pass one, every box under the wall in the facts' own order, only
        // to see where each box's own connection points stand on the wall
        let rows = pack(devices);
        widen([rows[rows.length - 1] || []]);
        BOXH = heightOf();
        rowsOn = { top: 0, bottom: rows.length };
        let W = wallAt(gapFor(0, 0));
        const discOf = new Map();
        const rule = this._bwDiscRule(layer, side);
        const placeDiscs = (geo) => {
            discOf.clear();
            for (const st of facts.stubs) discOf.set(st, this._bwDisc(book, rule, geo, st.panel, st.text, st.layer));
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
            const far = all.length <= 1 ? xRows
                : xRows.filter(row => { const v = at.get(row[0].key); return v.ri === n[v.side] - 1; });
            return { xRows, at, n, far };
        };
        const arr = arrange();
        widen(arr.far);
        BOXH = heightOf();
        rowsOn = { ...arr.n };
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
            const rowYOf = (s, ri) => (s === 'top'
                ? wall.y - (gap.top + BOXH + ri * (BOXH + ROW_GAP)) * K
                : wall.y + wall.h + (gap.bottom + ri * (BOXH + ROW_GAP)) * K);
            const blocks = [];
            const socketX = new Map();
            arr.xRows.forEach((row) => {
                const sum = row.reduce((s, d) => s + widthOf(d), 0);
                // spread across the width - and never past it: a crowded row
                // takes the room it really has rather than a fixed gap and a
                // block hanging off the sheet's edge
                const gp = row.length > 1
                    ? Math.max(MIN_BOX_GAP, (availW - sum) / (row.length - 1)) : 0;
                const span = sum + gp * (row.length - 1);
                let x = MARGIN + Math.max(0, (availW - span) / 2);
                row.forEach((d, di) => {
                    const { side: bs, ri } = arr.at.get(d.key);
                    const over = bs === 'top';
                    const y = rowYOf(bs, ri);
                    const w = widthOf(d), p = pitchOf(d);
                    const bx = A.x + x * K;
                    // A box widened for its inputs keeps its sockets towards the
                    // sheet's edge on its own side - the first box's at its left
                    // end, the last box's at its right, a lone box's centred - so
                    // its outer sockets stand where they stood and the runs to
                    // them still clear the wall.
                    const slide = (w - boxW(d)) * (row.length > 1 ? di / (row.length - 1) : 0.5);
                    const used = new Map(wiresOf(d.key).map(w2 => [w2.socket, w2]));
                    const xs = new Map();
                    const sockets = [];
                    const sy = y + (over ? BOXH - SOCKET_DY : SOCKET_DY) * K;
                    for (let k = 1; k <= d.n; k++) {
                        const sx = A.x + (x + slide + PAD + p / 2 + (k - 1) * p) * K;
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
                                                      w: groupW(d, d.inputs[gi]) * K })),
                    } : null;
                    blocks.push({ key: d.key, title: d.title, x: bx, y, w: w * K, h: BOXH * K,
                                  side: bs,
                                  titleY: y + (over ? TOP_TITLE_DY : TITLE_DY) * K,
                                  noteY: y + (over ? BOXH - NOTE_DY + NOTE_SZ * 0.72 : NOTE_DY) * K,
                                  inputs, row: ri, pitch: p * K, sockets,
                                  rim: isData ? INK : hue.get(d.key),
                                  hue: hue.get(d.key), dash: dash.get(d.key) });
                    x += w + gp;
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
                         placed: !!w,
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

            // What each run wants: where it leaves the wall, where its
            // socket is, which side of the wall its box stands on, and
            // whether it can go straight to it from the side it leaves by.
            const plans = facts.wires.map((w) => {
                const disc = discFor.get(w.stub);
                const b = blockOf.get(w.device.key);
                const T = b ? b.side : 'bottom';
                const near = T === 'top' ? 'top' : 'bottom';
                const tx = (socketX.get(w.device.key) || new Map()).get(w.socket);
                const ty = !b ? bottom
                    : T === 'top' ? b.y + (BOXH - SOCKET_DY + SOCK) * K : b.y + (SOCKET_DY - SOCK) * K;
                const { edge, stub } = this._bwExit(disc, wall, ink, ownOf(disc), pad, room, near);
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
                return { w, disc, tx, ty, edge, stub, side, out, T, near };
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
                    && Math.abs(p.tx - p.disc.x) >= STRAIGHT * K);
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
                const nNear = this._bwLanes(nearSpans), nFar = this._bwLanes(farSpans);
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
                const pts = [p.stub.head];
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
                } else if (Math.abs(tx - disc.x) < STRAIGHT * K) {
                    // already outside its socket and in line with it:
                    // straight on, off the disc's own edge onto the socket
                    const off = Math.sqrt(Math.max(0, disc.r * disc.r - (tx - disc.x) * (tx - disc.x)));
                    pts.length = 0;
                    pts.push([tx, p.near === 'top' ? disc.y - off : disc.y + off]);
                } else {
                    pts.push([at, nearY()], [tx, nearY()]);
                }
                pts.push([tx, ty]);
                return { kind: w.kind, from: w.stub.text, device: w.device.title, socket: w.socket,
                         colour, dash: pattern.map(v => v * K), width: RUN_W * K,
                         points: this._bwTidy(pts) };
            });
            // The rev 1.1 lanes stand as they were placed; only two runs
            // that print as one are nudged apart (see _bwNudge).
            this._bwNudge(runs, wall, room, ink, (RUN_W + CASE_EXTRA) * K);
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
                 unplaced, total: facts.stubs.length, facts };
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
        const tryMove = (s, to) => {
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
            // already beside (the stub off its own disc is on that disc)
            for (let j = s.j - 1; j <= s.j + 1; j++) {
                const was = boxOf(old[j], old[j + 1]), now = boxOf(p[j], p[j + 1]);
                if (ink.some(k => over(now, k) && !over(was, k))) return false;
            }
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
            const moved = movers.some((m) => {
                const o = m === a ? b : a;
                return tryMove(m, o.c + outward(m) * (pen + E));
            });
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
        const S = (book.scale || 2) * ((book.fill && book.fill.s) || 1);
        // Re-entrant, exactly as _bMap's own probe is: a caller already
        // probing this render (the label-collision suite is one) keeps its
        // array and we read the stretch this map added to it.
        const outer = r.labelProbe;
        const outerLen = outer ? outer.length : 0;
        const probe = outer || (typeof r.startLabelProbe === 'function' ? r.startLabelProbe() : null);
        // This sheet gives the map NO gutter, so the bitmap is the wall and
        // nothing else: the multi band pill and the circuit ruler the map
        // draws over the wall's head fall outside it and are clipped away.
        // Ink that never reaches the paper cannot be covered, so it is not
        // read as lettering here.
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
        // put back exactly what was there: an own property is restored, an
        // inherited one is uncovered
        const own = [Object.getOwnPropertyDescriptor(r, '_layoutCircleLabel'),
                     Object.getOwnPropertyDescriptor(r, '_fillWrappedLabel')];
        r._layoutCircleLabel = function (...a) {
            const out = layout.apply(this, a);
            if (out && Array.isArray(out.lines) && Number.isFinite(out.radius)) radii.set(out.lines, out.radius);
            return out;
        };
        r._fillWrappedLabel = function (ls, x, y) {
            if (Array.isArray(ls) && radii.has(ls) && Number.isFinite(x) && Number.isFinite(y)) {
                seen.push({ key: ls.join('').replace(/\s+/g, ''), x, y, r: radii.get(ls) });
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
    // never labelled keeps the measured disc.
    _bwSeat(facts, geo, seen) {
        const placed = new Map();
        if (!geo || !seen || !seen.length) return placed;
        const by = new Map();
        for (const d of seen) {
            if (!by.has(d.key)) by.set(d.key, []);
            by.get(d.key).push(d);
        }
        for (const st of facts.stubs) {
            const list = by.get(String(st.text).replace(/\s+/g, ''));
            if (!list || !list.length) continue;
            const p = st.panel;
            const cx = p.x + p.width / 2, cy = p.y + p.height / 2;
            const on = st.layer || undefined;
            // only a disc this sheet shows: on a member's sheet a crossing
            // port's label can stand on the other member, cut off the map
            // (its stub then keeps the disc measured on this member)
            let best = null, bestD = Infinity, bestRc = null;
            for (const d of list) {
                const rcd = geo.rect(d.x - d.r, d.y - d.r, 2 * d.r, 2 * d.r, on);
                if (typeof geo.keep === 'function' && !geo.keep(rcd)) continue;
                const v = (d.x - cx) * (d.x - cx) + (d.y - cy) * (d.y - cy);
                if (v < bestD) { best = d; bestD = v; bestRc = rcd; }
            }
            if (!best) continue;
            const rc = bestRc;
            const pr = geo.rect(p.x, p.y, p.width, p.height, on);
            placed.set(st, { x: rc.x + rc.w / 2, y: rc.y + rc.h / 2, r: rc.w / 2,
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
            side: P.side, scale: K, rows: P.rows, pitch: P.pitch, grow: P.grow || 0, head: P.head || 0,
            rowsTop: P.rowsTop || 0, rowsBottom: P.rowsBottom || 0,
            spare: P.spare || 0, rail: P.rail, availW: P.availW,
            gap: P.gap || null, lanes: P.lanes || null,
            area: { x: A.x, y: A.y, w: A.w, h: A.h },
            wallRoom: P.wallRoom ? { x: P.wallRoom.x, y: P.wallRoom.y, w: P.wallRoom.w, h: P.wallRoom.h } : null,
            map: geo ? { x: geo.wall.x, y: geo.wall.y, w: geo.wall.w, h: geo.wall.h,
                         zoom: geo.zoom, area: geo.area } : null,
            room: P.room || null,
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
                if (sk.note) {
                    this._bText(book, sk.note, sk.x, b.noteY != null ? b.noteY : b.y + NOTE_DY * K,
                                { size: NOTE_SZ * K, weight: 400, align: 'center',
                                  color: sk.on ? MUTED : GREY_INK,
                                  maxWidth: b.pitch * 2.4, shrink: true });
                }
                if (entry) entry.sockets.push({ n: sk.n, x: sk.x, y: sk.y, r: sk.r,
                                                state: sk.state, note: sk.note, fill, rim });
            }
            if (log) log.blocks.push(entry);
        }

        // the wall's own discs are the origin - no second tag is drawn. On
        // power the breakout's hue is carried to them as a ring, so a run
        // and the disc it leaves read as one.
        for (const d of P.discs) {
            if (!printer && !P.isData && d.hue && d.r > 0) {
                this._bwRing(ctx, d.x, d.y, d.r, d.hue, DISC_RIM * K);
            }
            if (log) log.discs.push({ kind: d.kind, text: d.text, x: d.x, y: d.y, r: d.r,
                                      panel: d.panel, placed: d.placed });
        }

        // the runs, last, so a line can be followed over everything it
        // crosses - each drawn twice, the white casing first
        for (const r of P.runs) {
            this._bwPath(ctx, r.points, WHITE, r.width + CASE_EXTRA * K, []);
            this._bwPath(ctx, r.points, r.colour, r.width, r.dash);
            if (log) log.runs.push({ kind: r.kind, from: r.from, device: r.device, socket: r.socket,
                                     colour: r.colour, dash: r.dash, width: r.width,
                                     points: r.points.map(p => [p[0], p[1]]) });
        }

        if (P.unplaced) {
            this._bText(book, `${P.unplaced} of ${P.total} not placed on any ${this.showUnitWord()} — no run to draw`,
                        A.x, A.y + A.h - 4 * K, { size: NOTE_SZ * K * 1.15, weight: 400, color: MUTED });
        }
        if (log) book.log.wiring.halves.push(log);
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
    // in AT THE BOX (_bStrandsAtBox: a TAC's pair flipped, as FIBER
    // CONNECTIONS' AT THE BREAKOUT reads), named and swatched as the strand
    // map has them (_bStrandPiece - numbers with no swatch on a cable
    // labelled by number, sub-unit names as it prints them); a copper link
    // its run's kind. Inputs with no cable and no copper are left out, and
    // a box with none on either is null.
    _bwBoxInputs(box) {
        const links = typeof this.fiberBoxLinks === 'function' ? this.fiberBoxLinks(box) : [];
        const on = links.filter(l => l.cable || l.copper);
        if (!on.length) return null;
        return on.map(l => {
            if (l.copper) return { head: l.title, strands: [{ text: String(l.copper.copper || 'copper'), swatch: null }] };
            const set = this._bStrandsAtBox(l.link, l.cable);
            return { head: l.title,
                     strands: set.length ? set.map(n => this._bStrandPiece(n, l.cable))
                         : [{ text: l.cable.name || this.fiberCableTypeText(l.cable), swatch: null }] };
        });
    }

    // A box's inputs as _bwPlanHalf placed them - side by side on the
    // caption's row, or on the lines it wrapped them to under the caption -
    // each group outlined: the input bold, then its strands, on the
    // caption's own baseline (or a wrapped line's). Swatched as the
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
            let x = x0 + I.head;
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
