// app-binder-wiring: the SIGNAL + POWER sheet - a screen's third sheet,
// after its Power and Data sheets (2026-09-08, on the last page of the
// NACUBO packet: "he gave an example his binder and we could do this for
// power and data drawing from a port to port … the last page is what i
// was talking about").
//
// THE DRAWING IS THE PROTOTYPE'S. src/static/wiring-proto.html draws this
// picture from two real shows' own facts and is what was approved
// (2026-09-09: "those are fantastic", "that is much more legible", "that
// looks great") - casing on, fade off, the printer palette for the press.
// Every number below is in the prototype's page units (it is 1000 wide)
// and a half scales them by K = its width / 1000, so the sheet carries
// that drawing across whatever size the paper is.
//
// The drawing area is split by a rule: SIGNAL above, POWER below (a
// screen with one side draws that half alone). Each half, top to bottom:
//
//   the WALL      - the same _bMap render the Power / Data sheets use
//                   (data-flow view above, power view below), rulers and
//                   brackets off. THE WALL'S OWN LABEL DISCS ARE THE
//                   ORIGIN: no second tag is drawn on it - an earlier
//                   attempt hung rounded tags off the panels and they
//                   covered the wall. The disc's place and size are the
//                   renderer's own (its panel's centre, shifted inside
//                   the screen by its radius), read here so a run can
//                   leave its edge.
//   the BLOCKS    - flat units at the BOTTOM, spread across the width,
//                   their sockets in a row and THEIR NAME INSIDE on its
//                   own line UNDER the numbers - a run comes down into
//                   its socket from above, and on the line above the
//                   numbers the run's white casing ate the letters,
//                   ordered by the mean position of their own
//                   runs. Signal: one per device the screen's port ends
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
//                   there travels in the CLEAR SPACE beside and under the
//                   wall: down a rail past the wall's edge, along a lane
//                   under its foot (or across one over its head), and
//                   into its socket. Where the socket already stands
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
// A stub on no card draws its disc and no run, and the half prints
// "n of m not placed on any card" once.
//
// Everything is drawn in page units through the recorder, so the PDF gets
// the sheet as vector; circles are short polylines and the casing is
// simply the same path stroked white first (the recorder knows rects,
// lines, text and images, nothing else).
//
// One view per sheet: "n  SR - MAIN · SIGNAL + POWER", its bubble under
// the lower half. Every figure is read from the same authorities the
// Power and Data sheets read - _pullPortRuns, _bPortHome,
// getPortLabelText, the pull list's byScreen units, screenCircuits,
// getDistroOutputTypes; nothing is recomputed here.
import { LEDRasterApp } from './app-core.js';
import { BINDER_STYLE } from './app-binder.js';

const { INK, RULE, MUTED, BUBBLE_H } = BINDER_STYLE;

// The wall takes the whole of the room it is given: this sheet draws no
// rulers and no brackets, and the discs are the renderer's own, inside it.
const GUT = { left: 0, right: 0, top: 0, bottom: 0 };
// The air between the two halves, where the rule between them runs.
const RULE_GAP = 40;

// ---- the prototype's page, in its own units (it is 1000 wide) -----------
const PROTO_W = 1000;
const MARGIN = 22;
const HEAD = 22;                 // the SIGNAL / POWER word over the wall
const HEAD_SZ = 11;
const MAX_WALL_H = 360;
const BAND_GAP = 26;             // the wall's foot to the first block row
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
// sockets nothing crosses it.
const TITLE_DY = 50, NOTE_DY = 13, SOCKET_DY = 26;
const CAPTION_SZ = 10, NUMBER_SZ = 8, NOTE_SZ = 7.5, NOTE_PAD = 8;
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

    // The screen's SIGNAL + POWER sheet: one numbered view, a half per side
    // the screen has (`sides` = { power, data }, already true only where
    // the screen has that side and the dialog asked for it).
    _bWiringPage(book, layer, pos, sides) {
        const scr = book.list.byScreen[layer.id] || {};
        const title = `${layer.name} - Signal + Power`;
        const sheetTitle = `${layer.name} · SIGNAL + POWER`;
        const order = [];
        if (sides.data) order.push('signal');
        if (sides.power) order.push('power');
        if (!order.length) return;
        const areas = this._bwAreas(book, order.length);
        const plans = order.map((side, i) => this._bwPlanHalf(book, layer, scr, side, areas.halves[i]));
        const scale = Math.min(...plans.map(p => p.K));
        const view = ++book.views;
        this._bPage(book, {
            kind: 'wiring', title, sheetTitle, viewName: sheetTitle, view,
            layerId: layer.id, subject: layer.name, position: pos ? pos.name : null,
            layout: 'wiring', cols: order.length, scale,
            sides: { power: !!sides.power, data: !!sides.data },
            halves: plans.map(p => ({ side: p.side, scale: p.K, rows: p.rows,
                                      discs: p.discs.length, runs: p.runs.length,
                                      blocks: p.blocks.length, unplaced: p.unplaced })),
        }, () => {
            if (book.log) book.log.wiring = { halves: [] };
            if (areas.ruleY != null) {
                const ctx = book.ctx;
                const da = book.geo.da;
                ctx.strokeStyle = RULE;
                ctx.lineWidth = 2;
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(da.x, areas.ruleY);
                ctx.lineTo(da.x + da.w, areas.ruleY);
                ctx.stroke();
            }
            for (const p of plans) this._bwDrawHalf(book, layer, p);
            this._bViewBubble(book, view, sheetTitle, book.geo.da.x + 20, areas.bubbleY);
        });
    }

    // The drawing area cut for `n` halves: the bubble's room at the foot,
    // a rule between two halves.
    _bwAreas(book, n) {
        const da = book.geo.da;
        const total = da.h - BUBBLE_H;
        const bubbleY = da.y + da.h - BUBBLE_H + 12;
        if (n < 2) return { halves: [{ x: da.x, y: da.y, w: da.w, h: total }], ruleY: null, bubbleY };
        const halfH = (total - RULE_GAP) / 2;
        return {
            halves: [{ x: da.x, y: da.y, w: da.w, h: halfH },
                     { x: da.x, y: da.y + halfH + RULE_GAP, w: da.w, h: halfH }],
            ruleY: da.y + halfH + RULE_GAP / 2,
            bubbleY,
        };
    }

    // ---- the facts ----------------------------------------------------------

    // The signal half's facts: a stub per port end, the devices the ends
    // land on in the order the ports meet them, a wire per landed end.
    //   stubs:   [{ kind: 'primary'|'return', text, panel, port }]
    //   devices: [{ key, title, n, sockets: Map(n -> 'primary'|'return'), notes: Map }]
    //   wires:   [{ stub, device, socket, kind }]
    _bwSignalFacts(book, layer) {
        const asg = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        const runs = this._pullPortRuns(layer);
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
                d = { key, title, n: Number(n) || 0, sockets: new Map(), notes: new Map() };
                byKey.set(key, d);
                devices.push(d);
            }
            return d;
        };
        const stubs = [], wires = [];
        for (const run of runs) {
            const own = (run.panels || []).filter((p, i) => p && !p.hidden
                && (!run.layers || !run.layers[i] || run.layers[i] === layer || run.layers[i].id === layer.id));
            if (!own.length) continue;
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const home = placed && placed.cardId ? this._bPortHome(placed.cardId, placed.port) : null;
            const primary = { kind: 'primary', text: run.label, panel: own[0], port: run.num };
            stubs.push(primary);
            if (!home) continue;
            const d = device(home);
            const socket = home.port && home.port.localNumber != null
                ? Number(home.port.localNumber) : parseInt(placed.port, 10);
            d.sockets.set(socket, 'primary');
            wires.push({ stub: primary, device: d, socket, kind: 'primary' });
            const bb = home.port && home.port.backedBy;
            if (!bb) continue;
            const ret = { kind: 'return', text: this.getPortLabelText(layer, run.num, 'return'),
                          panel: own[own.length - 1], port: run.num };
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
    _bwPowerFacts(book, layer, scr) {
        const circuits = (typeof this.screenCircuits === 'function') ? this.screenCircuits(layer) : [];
        const byNum = new Map(circuits.map(c => [c.num, c]));
        const own = (c) => (c.layers
            ? c.panels.filter((p, i) => !c.layers[i] || c.layers[i] === layer || c.layers[i].id === layer.id)
            : c.panels).filter(p => p && !p.hidden);
        const types = (typeof this.getDistroOutputTypes === 'function') ? this.getDistroOutputTypes() : [];
        const devices = [], stubs = [], wires = [];
        for (const box of scr.boxes || []) {
            const t = types.find(x => x.id === box.typeId) || null;
            const tails = (box.circuits || []).map(c => Number(c.tail) || 0);
            const slots = t ? (Number(t.boxSize) || 6) : Math.max(6, ...tails);
            // "SR1 · Multi 208 breakout · 125'"; a multi on no distro has no
            // type to name its breakout by and reads as the band does
            const caption = [box.name, box.type ? `${box.type} breakout` : 'no distro',
                             box.homeRun ? this.pullLengthText(box.homeRun) : 'no length'].join(' · ');
            const d = { key: box.key, title: caption, n: slots, sockets: new Map(), notes: new Map() };
            if (box.distroId) {
                for (const [id, other] of Object.entries(book.list.byScreen)) {
                    if (String(id) === String(layer.id)) continue;
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
            for (const c of box.circuits || []) {
                const k = Number(c.tail);
                d.sockets.set(k, 'power');
                d.notes.delete(k);
                const circuit = byNum.get(c.num);
                const panels = circuit ? own(circuit) : [];
                if (!panels.length) continue;
                const stub = { kind: 'power', text: c.label, panel: panels[0], circuit: c.num };
                stubs.push(stub);
                wires.push({ stub, device: d, socket: k, kind: 'power' });
            }
        }
        return { stubs, devices, wires };
    }

    // ---- the wall's own discs -----------------------------------------------

    // What the renderer needs to place a label disc on this view: the
    // label's own size, the natural radius its site gives it, its text
    // padding, and the bounds a disc is shifted inside. Read from the very
    // fields renderDataFlowArrows / renderPowerArrows read, so the disc
    // this sheet aims at is the disc the wall draws.
    _bwDiscRule(layer, side) {
        const r = window.canvasRenderer || null;
        const bounds = r && typeof r.getLayerBounds === 'function' ? r.getLayerBounds(layer) : null;
        const family = (typeof this.getProjectFont === 'function') ? this.getProjectFont() : 'Arial';
        if (side === 'signal') {
            const size = layer.dataFlowLabelSize || 30;
            return { r, bounds, family, size, minRadius: size * 1.2, padding: Math.max(4, size * 0.2) };
        }
        const size = layer.powerLabelSize || 14;
        const pen = Math.max(1, Math.round(layer.powerLineWidth || 8));
        return { r, bounds, family, size,
                 minRadius: Math.max(size * 0.7, pen * 1.4), padding: Math.max(6, size * 0.25) };
    }

    // One label disc, in page units: its radius the renderer's own
    // (_layoutCircleLabel, measured on the dry context so nothing on the
    // page is disturbed), its centre the panel's centre shifted inside the
    // screen by that radius, both carried onto the sheet through the map's
    // own rect(). A renderer that cannot be asked falls back to a third of
    // the panel.
    _bwDisc(book, rule, geo, panel, text) {
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
        const b = rule.bounds;
        if (b && b.width > 2 * rad) cx = Math.min(Math.max(cx, b.x + rad), b.x + b.width - rad);
        if (b && b.height > 2 * rad) cy = Math.min(Math.max(cy, b.y + rad), b.y + b.height - rad);
        const rc = geo ? geo.rect(cx - rad, cy - rad, 2 * rad, 2 * rad)
                       : { x: cx, y: cy, w: 0, h: 0 };
        const pr = geo ? geo.rect(p.x, p.y, p.width, p.height) : { x: cx, y: cy, w: 0, h: 0 };
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
    _bwExit(d, wall, labels, own, pad, room) {
        const far = (e, at) => e === 'left' ? [room.x0, at] : e === 'right' ? [room.x1, at]
            : e === 'top' ? [at, room.y0] : [at, room.y1];
        const by = (names) => names
            .map(e => ({ e, s: this._bwStub(d, e, wall, 0) }))
            .sort((p, q) => p.s.gap - q.s.gap);
        const sides = by(['left', 'right']), ends = by(['top', 'bottom']);
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
    _bwPlanHalf(book, layer, scr, side, A) {
        const facts = side === 'signal' ? this._bwSignalFacts(book, layer) : this._bwPowerFacts(book, layer, scr);
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
        const rowWidthAt = (pitch) => devices.reduce((s, d) =>
            s + Math.max(d.n * Math.max(pitch, noteFloor(d)) + PAD * 2, capW(d) + PAD * 2), 0)
            + MIN_BOX_GAP * Math.max(0, devices.length - 1);
        // The pitch gives way before the layout does.
        let fit = PITCH;
        while (fit > MIN_PITCH && rowWidthAt(fit) > availW) fit -= 1;
        const pitchOf = (d) => Math.max(fit, noteFloor(d));
        const boxW = (d) => Math.max(d.n * pitchOf(d) + PAD * 2, capW(d) + PAD * 2);

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

        // the wall: bounded on both axes and centred in what is left
        const nRuns = facts.wires.length;
        const railRoom = Math.min(RAIL_MAX, RAIL_BASE + Math.ceil(nRuns / 2) * RAIL_GAP);
        const wallRoomW = Math.max(80, availW - 2 * railRoom);
        const spec = { measure: (area) => this._bMap(book, layer, view, area, GUT) };
        const foot = FOOT_PAD + (facts.stubs.length > facts.wires.length ? FOOT_LINE : 0);
        // The room over the wall's head and under its foot: the head word's
        // strip and the air before the blocks, plus a lane apiece for the
        // runs that have to travel along one.
        const wallAt = (nRows, head, band) => {
            const boxesH = nRows ? nRows * BOX_H + (nRows - 1) * ROW_GAP : 0;
            const roomH = Math.max(40, A.h / K - head - band - boxesH - foot);
            const room = { x: A.x + (MARGIN + railRoom) * K, y: A.y + head * K,
                           w: wallRoomW * K, h: Math.min(MAX_WALL_H, roomH) * K };
            const probe = this._bMeasureMap(book, spec, room);
            const h = probe ? probe.area.h : 0;
            const mapArea = { ...room, y: room.y + Math.max(0, (roomH * K - h) / 2), h: Math.max(1, h) };
            return { mapArea, geo: this._bMeasureMap(book, spec, mapArea), roomH };
        };

        // pass one in the facts' own order, only to learn how many rows the
        // blocks take; then the order the runs ask for, and the wall again
        // if that changed the count
        let rows = pack(devices);
        let head = HEAD, band = BAND_GAP;
        let W = wallAt(rows.length, head, band);
        const discOf = new Map();
        const rule = this._bwDiscRule(layer, side);
        const placeDiscs = (geo) => {
            discOf.clear();
            for (const st of facts.stubs) discOf.set(st, this._bwDisc(book, rule, geo, st.panel, st.text));
        };
        placeDiscs(W.geo);
        const meanOf = (key) => {
            const ws = wiresOf(key);
            if (!ws.length) return 0;
            return ws.reduce((s, w) => s + (discOf.get(w.stub) || { x: 0 }).x, 0) / ws.length;
        };
        const rank = new Map(devices.map((d, i) => [d.key, i]));
        const order = devices.slice().sort((a, b) =>
            (meanOf(a.key) - meanOf(b.key)) || (rank.get(a.key) - rank.get(b.key)));
        const rows2 = pack(order);
        if (rows2.length !== rows.length) { W = wallAt(rows2.length, head, band); placeDiscs(W.geo); }
        rows = rows2;

        // the blocks are spread across the width rather than packed
        // shoulder to shoulder: a run reads better when its block is under
        // the part of the wall it serves
        const nRows = rows.length;
        const boxesH = nRows ? nRows * BOX_H + (nRows - 1) * ROW_GAP : 0;
        const bottom = A.y + A.h - foot * K;
        const rowY = (ri) => bottom - (boxesH - ri * (BOX_H + ROW_GAP)) * K;
        const hue = new Map(), dash = new Map();
        devices.forEach((d, i) => {
            hue.set(d.key, printer ? INK : HUES[i % HUES.length]);
            dash.set(d.key, DASHES[i % DASHES.length]);
        });
        const primaryInk = printer ? INK : (layer.primaryColor || '#00FF00');
        const backupInk = printer ? INK : (layer.backupColor || '#FF0000');
        const blocks = [];
        const socketX = new Map();
        rows.forEach((row, ri) => {
            const sum = row.reduce((s, d) => s + boxW(d), 0);
            // spread across the width - and never past it: a crowded row
            // takes the room it really has rather than a fixed gap and a
            // block hanging off the sheet's edge
            const gap = row.length > 1
                ? Math.max(MIN_BOX_GAP, (availW - sum) / (row.length - 1)) : 0;
            const span = sum + gap * (row.length - 1);
            let x = MARGIN + Math.max(0, (availW - span) / 2);
            const y = rowY(ri);
            for (const d of row) {
                const w = boxW(d), p = pitchOf(d);
                const bx = A.x + x * K;
                const used = new Map(wiresOf(d.key).map(w2 => [w2.socket, w2]));
                const xs = new Map();
                const sockets = [];
                for (let k = 1; k <= d.n; k++) {
                    const sx = A.x + (x + PAD + p / 2 + (k - 1) * p) * K;
                    xs.set(k, sx);
                    const on = used.get(k) || null;
                    const state = on ? (on.kind === 'power' ? 'power' : on.kind)
                                     : (d.sockets.get(k) === 'other' ? 'other' : 'free');
                    const note = on ? noteOf(on.stub.text, k) : (d.notes.get(k) || '');
                    sockets.push({ n: k, x: sx, y: y + SOCKET_DY * K, r: SOCK * K,
                                   state, note: note || null, on: !!on,
                                   kind: on ? on.kind : null });
                }
                socketX.set(d.key, xs);
                blocks.push({ key: d.key, title: d.title, x: bx, y, w: w * K, h: BOX_H * K,
                              row: ri, pitch: p * K, sockets,
                              rim: isData ? INK : hue.get(d.key),
                              hue: hue.get(d.key), dash: dash.get(d.key) });
                x += w + gap;
            }
        });
        const blockOf = new Map(blocks.map(b => [b.key, b]));

        // The discs on the wall and the runs that leave them. Taken as one
        // step so it can be done again with the discs the wall REALLY drew
        // and the lettering it REALLY laid down (the paint reads both off
        // the render - a splitter circuit's label sits at its fan-out, not
        // on its first panel, and only the renderer knows that).
        const draw = (placed, letters, W2) => {
            const wall = (W2 || W).geo ? (W2 || W).geo.wall
                                       : { x: A.x, y: (W2 || W).mapArea.y, w: A.w, h: 0 };
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

            // the clear space the runs travel in: over the wall's head,
            // under its foot, and beside it either way
            const overTop = A.y + 2 * K, overBot = wall.y - 2 * K;
            const underTop = wall.y + wall.h + 2 * K, underBot = rowY(0) - 2 * K;
            const room = { x0: A.x + 3 * K, x1: A.x + (PROTO_W - 3) * K,
                           y0: overTop, y1: underBot };

            // What each run wants: where it leaves the wall, where its
            // socket is, and whether it can drop straight into it from the
            // side it leaves by.
            const plans = facts.wires.map((w) => {
                const disc = discFor.get(w.stub);
                const b = blockOf.get(w.device.key);
                const tx = (socketX.get(w.device.key) || new Map()).get(w.socket);
                const ty = b ? b.y + (SOCKET_DY - SOCK) * K : bottom;
                const { edge, stub } = this._bwExit(disc, wall, ink, ownOf(disc), pad, room);
                // is the socket already clear of the wall on the side this
                // run can come down? then the rail IS the drop
                const left = tx < wall.x - 0.5, right = tx > wall.x + wall.w + 0.5;
                const out = edge === 'left' ? left : edge === 'right' ? right : (left || right);
                // and if it is not, the side it comes down is the one its
                // socket is nearer to, so the lane under the wall is short
                const side = edge === 'left' || edge === 'right' ? edge
                    : (tx - wall.x <= wall.x + wall.w - tx ? 'left' : 'right');
                return { w, disc, tx, ty, edge, stub, side, out };
            });

            // The rails, one per run that has to come down beside the wall,
            // nested so the fan does not knot: on the left the socket
            // furthest right takes the rail nearest the wall, on the right
            // the mirror of that.
            const bySide = (s) => plans
                .filter(p => p.side === s && !p.out && p.edge !== 'bottom')
                .sort((a, b) => s === 'left' ? b.tx - a.tx : a.tx - b.tx);
            const railX = new Map();
            const railed = { left: bySide('left'), right: bySide('right') };
            for (const s of ['left', 'right']) {
                const beside = s === 'left' ? wall.x - room.x0 : room.x1 - (wall.x + wall.w);
                const step = Math.min(RAIL_STEP * K,
                    Math.max(2 * K, (beside - RAIL_OUT * K) / Math.max(1, railed[s].length)));
                railed[s].forEach((p, i) => {
                    const d = RAIL_OUT * K + i * step;
                    railX.set(p, s === 'left' ? wall.x - d : wall.x + wall.w + d);
                });
            }

            // The lanes: one over the wall's head for a run that left by
            // its top, one under its foot for a run coming down a rail or
            // out of its foot. The two sides are woven together and the
            // lanes handed out greedily, so a left lane and a right lane
            // that never meet are one lane and cost the sheet no room.
            const weave = (l, r) => {
                const out2 = [];
                for (let i = 0; i < Math.max(l.length, r.length); i++) {
                    if (i < l.length) out2.push(l[i]);
                    if (i < r.length) out2.push(r[i]);
                }
                return out2;
            };
            const span = (p, a, b) => ({ p, lo: Math.min(a, b), hi: Math.max(a, b) });
            const overOf = new Map(), underOf = new Map();
            // over the wall's head: every run that left by its top, from its
            // own column across to its socket or to the rail it comes down
            const overAt = (p) => (p.out ? p.tx : railX.get(p));
            const over = plans.filter(p => p.edge === 'top');
            const overs = weave(
                over.filter(p => overAt(p) < p.stub.at).sort((a, b) => a.stub.at - b.stub.at)
                    .map(p => span(p, p.stub.at, overAt(p))),
                over.filter(p => overAt(p) >= p.stub.at).sort((a, b) => b.stub.at - a.stub.at)
                    .map(p => span(p, p.stub.at, overAt(p))));
            // under its foot: every run coming down a rail, and every run
            // that left by the foot and is not straight over its socket
            const dropped = (s) => plans.filter(p => p.edge === 'bottom' && p.side === s
                && Math.abs(p.tx - p.disc.x) >= STRAIGHT * K);
            const unders = weave(
                railed.left.map(p => span(p, railX.get(p), p.tx))
                    .concat(dropped('left').map(p => span(p, p.stub.at, p.tx))),
                railed.right.map(p => span(p, railX.get(p), p.tx))
                    .concat(dropped('right').map(p => span(p, p.stub.at, p.tx))));
            const nOver = this._bwLanes(overs);
            const nUnder = this._bwLanes(unders);
            for (const it of overs) overOf.set(it.p, it.lane);
            for (const it of unders) underOf.set(it.p, it.lane);

            // and where those lanes lie: evenly through the room the wall's
            // head and foot were given
            const laneAt = (lo, hi, i, n) => lo + (hi - lo) * (i + 1) / (n + 1);

            const runs = plans.map((p) => {
                const { w, disc, tx, ty } = p;
                const colour = isData ? (w.kind === 'return' ? backupInk : primaryInk)
                                      : hue.get(w.device.key);
                const pattern = printer
                    ? (isData ? (w.kind === 'return' ? PRINTER_RETURN_DASH : []) : dash.get(w.device.key))
                    : (isData && w.kind === 'return' ? RETURN_DASH : []);
                const under = () => laneAt(underTop, underBot, underOf.get(p), nUnder);
                const at = p.stub.at;
                const pts = [p.stub.head];
                if (p.edge === 'left' || p.edge === 'right') {
                    // out at its own row, and down - at its socket where the
                    // socket is already outside the wall on this side, else
                    // down the rail and along a lane under the wall's foot
                    if (p.out) pts.push([tx, at]);
                    else {
                        const rx = railX.get(p);
                        pts.push([rx, at], [rx, under()], [tx, under()]);
                    }
                } else if (p.edge === 'top') {
                    // up out of its own column, across over the wall's head,
                    // and down - beside the wall to its socket, or down the
                    // rail and back along a lane under the wall's foot
                    const oy = laneAt(overTop, overBot, overOf.get(p), nOver);
                    const toX = p.out ? tx : railX.get(p);
                    pts.push([at, oy], [toX, oy]);
                    if (!p.out) pts.push([toX, under()], [tx, under()]);
                } else if (Math.abs(tx - disc.x) < STRAIGHT * K) {
                    // already outside and above its socket: straight down,
                    // off the disc's own edge and onto the socket's centre
                    const off = Math.sqrt(Math.max(0, disc.r * disc.r - (tx - disc.x) * (tx - disc.x)));
                    pts.length = 0;
                    pts.push([tx, disc.y + off]);
                } else {
                    pts.push([at, under()], [tx, under()]);
                }
                pts.push([tx, ty]);
                return { kind: w.kind, from: w.stub.text, device: w.device.title, socket: w.socket,
                         colour, dash: pattern.map(v => v * K), width: RUN_W * K,
                         points: this._bwTidy(pts) };
            });
            return { discs, runs, over: nOver, under: nUnder, room };
        };

        // The wall's head and foot are given the lanes the runs really
        // want, and a couple over - the discs the sheet measured are all it
        // knows of the lettering here, and the paint may find a tag beside
        // one of them and send that run round the top instead.
        const est = draw(new Map(), null, W);
        if (est.over || est.under) {
            head = HEAD + (est.over ? (est.over + 2) * LANE_STEP : 0);
            band = Math.max(BAND_GAP, (est.under + 2) * LANE_STEP);
            W = wallAt(rows.length, head, band);
            placeDiscs(W.geo);
        }
        const geo = W.geo;
        const wall = geo ? geo.wall : { x: A.x, y: W.mapArea.y, w: A.w, h: 0 };
        const first = draw(new Map(), null, W);
        const unplaced = facts.stubs.length - facts.wires.length;
        return { side, view, K, A, mapArea: W.mapArea, geo, wall, printer, isData,
                 blocks, discs: first.discs, runs: first.runs, room: first.room,
                 redraw: (placed, letters) => draw(placed, letters, W),
                 rows: nRows, pitch: fit * K,
                 unplaced, total: facts.stubs.length, facts };
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

    // ---- the discs the wall really drew -------------------------------------

    // The map painted for this half, with every label disc the renderer laid
    // down noted as it went. The renderer sizes a disc through
    // _layoutCircleLabel and then sets its lines through _fillWrappedLabel at
    // the disc's own centre - the same `lines` array travels between the
    // two - so wrapping that pair for the length of one paint reports every
    // disc's centre and radius without a word of the placement being
    // guessed here. A renderer that cannot be wrapped simply reports none.
    _bwPaintMap(book, layer, view, area) {
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
            return { geo, discs: seen, labels: carry(geo && geo.area) };
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
            let best = null, bestD = Infinity;
            for (const d of list) {
                const v = (d.x - cx) * (d.x - cx) + (d.y - cy) * (d.y - cy);
                if (v < bestD) { best = d; bestD = v; }
            }
            const rc = geo.rect(best.x - best.r, best.y - best.r, 2 * best.r, 2 * best.r);
            const pr = geo.rect(p.x, p.y, p.width, p.height);
            placed.set(st, { x: rc.x + rc.w / 2, y: rc.y + rc.h / 2, r: rc.w / 2,
                             panel: { x: pr.x, y: pr.y, w: pr.w, h: pr.h } });
        }
        return placed;
    }

    // ---- the paint ----------------------------------------------------------

    _bwDrawHalf(book, layer, P) {
        const ctx = book.ctx;
        const K = P.K;
        const A = P.A;
        const printer = P.printer;
        // the head word
        this._bText(book, P.side === 'signal' ? 'SIGNAL' : 'POWER', A.x, A.y + (HEAD - 6) * K,
                    { size: HEAD_SZ * K, weight: 700, color: MUTED });
        // the wall - the same render, painted now, its own discs on it and
        // noted as they go, so the runs leave the discs that are really there
        const painted = this._bwPaintMap(book, layer, P.view, P.mapArea);
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
                P = { ...P, discs: again.discs, runs: again.runs, room: again.room };
            }
        }
        const log = book.log && book.page && book.page.painting ? {
            side: P.side, scale: K, rows: P.rows, pitch: P.pitch,
            map: geo ? { x: geo.wall.x, y: geo.wall.y, w: geo.wall.w, h: geo.wall.h,
                         zoom: geo.zoom, area: geo.area } : null,
            room: P.room || null,
            discs: [], runs: [], blocks: [], unplaced: P.unplaced, total: P.total,
        } : null;

        // the blocks: the name INSIDE, on its own line under the sockets
        for (const b of P.blocks) {
            this._bwRound(ctx, b.x, b.y, b.w, b.h, BOX_R * K, WHITE, b.rim, BOX_RIM * K);
            const title = this._bText(book, b.title, b.x + PAD * K, b.y + TITLE_DY * K,
                                      { size: CAPTION_SZ * K, weight: 700, color: b.rim,
                                        maxWidth: b.w - 2 * PAD * K, shrink: true });
            const entry = log ? { title, key: b.key, x: b.x, y: b.y, w: b.w, h: b.h,
                                  rim: b.rim, hue: b.hue, dash: b.dash, sockets: [] } : null;
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
                    this._bText(book, sk.note, sk.x, b.y + NOTE_DY * K,
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
            this._bText(book, `${P.unplaced} of ${P.total} not placed on any card — no run to draw`,
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
