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
//   the RUNS      - two segments from the disc: out at the run's OWN ROW
//                   to its socket's x, then straight down into the
//                   socket. No shared corridor, no lanes, no levels - an
//                   earlier attempt turned every run down as soon as it
//                   cleared the wall and the fans knotted.
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
// THE ESCAPE. A run whose socket sits under its OWN column, with other
// discs below it on that column, would drop straight through them (SR1's
// socket 6 ran through five of them). It steps out past the wall's near
// edge instead, drops clear, and comes back to its socket. A run already
// above its socket simply drops straight - which is what a vertical flow
// wants.
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
// The escape: how far past the wall's edge it steps, how far above the
// socket row it comes back, how far apart two escapes stand.
const ESC_OUT = 14, ESC_LIFT = 14, ESC_NEAR = 6, ESC_STEP = 5;
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
        const wallAt = (nRows) => {
            const boxesH = nRows ? nRows * BOX_H + (nRows - 1) * ROW_GAP : 0;
            const roomH = Math.max(40, A.h / K - HEAD - BAND_GAP - boxesH - foot);
            const room = { x: A.x + (MARGIN + railRoom) * K, y: A.y + HEAD * K,
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
        let W = wallAt(rows.length);
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
        if (rows2.length !== rows.length) { W = wallAt(rows2.length); placeDiscs(W.geo); }
        rows = rows2;

        const geo = W.geo;
        const wall = geo ? geo.wall : { x: A.x, y: W.mapArea.y, w: A.w, h: 0 };

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
        // (the paint reads them off the render - a splitter circuit's label
        // sits at its fan-out, not on its first panel, and only the
        // renderer knows that).
        const draw = (placed) => {
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

            // the runs: out of the disc at its OWN row to its socket's x,
            // then straight down into it - unless it is already above its
            // socket, or its own column stands in the way
            const sameCol = (a, b) => Math.abs((a.panel.x + a.panel.w / 2) - (b.panel.x + b.panel.w / 2))
                < Math.max(1, Math.min(a.panel.w, b.panel.w) / 2);
            let escapes = 0;
            const runs = facts.wires.map((w) => {
                const disc = discFor.get(w.stub);
                const b = blockOf.get(w.device.key);
                const tx = (socketX.get(w.device.key) || new Map()).get(w.socket);
                const ty = b ? b.y + (SOCKET_DY - SOCK) * K : bottom;
                const colour = isData ? (w.kind === 'return' ? backupInk : primaryInk) : hue.get(w.device.key);
                const pattern = printer
                    ? (isData ? (w.kind === 'return' ? PRINTER_RETURN_DASH : []) : dash.get(w.device.key))
                    : (isData && w.kind === 'return' ? RETURN_DASH : []);
                const below = discs.some(o => o !== disc && sameCol(o, disc) && o.y > disc.y);
                let points;
                if (Math.abs(tx - disc.x) < (disc.r + ESC_NEAR * K) && below) {
                    // the escape: out past the wall's near edge, down clear
                    // of every disc under it, and back to its socket
                    const right = disc.x - wall.x > wall.w / 2;
                    const step = escapes++;
                    const out = (ESC_OUT + step * ESC_STEP) * K;
                    const clear = right ? wall.x + wall.w + out : wall.x - out;
                    const lift = ty - (ESC_LIFT + step * ESC_STEP) * K;
                    points = [[right ? disc.x + disc.r : disc.x - disc.r, disc.y],
                              [clear, disc.y], [clear, lift], [tx, lift], [tx, ty]];
                } else if (Math.abs(tx - disc.x) < STRAIGHT * K) {
                    // already above its socket: straight down, off the disc's
                    // own edge and onto the socket's very centre
                    const off = Math.sqrt(Math.max(0, disc.r * disc.r - (tx - disc.x) * (tx - disc.x)));
                    points = [[tx, disc.y + off], [tx, ty]];
                } else {
                    const outX = tx < disc.x ? disc.x - disc.r : disc.x + disc.r;
                    points = [[outX, disc.y], [tx, disc.y], [tx, ty]];
                }
                return { kind: w.kind, from: w.stub.text, device: w.device.title, socket: w.socket,
                         colour, dash: pattern.map(v => v * K), width: RUN_W * K, points };
            });
            return { discs, runs };
        };

        const first = draw(new Map());
        const unplaced = facts.stubs.length - facts.wires.length;
        return { side, view, K, A, mapArea: W.mapArea, geo, wall, printer, isData,
                 blocks, discs: first.discs, runs: first.runs, redraw: draw,
                 rows: nRows, pitch: fit * K,
                 unplaced, total: facts.stubs.length, facts };
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
            return { geo: this._bMap(book, layer, view, area, GUT), discs: null };
        }
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
            return { geo: this._bMap(book, layer, view, area, GUT), discs: seen };
        } finally {
            delete r._layoutCircleLabel;
            delete r._fillWrappedLabel;
            if (own[0]) Object.defineProperty(r, '_layoutCircleLabel', own[0]);
            if (own[1]) Object.defineProperty(r, '_fillWrappedLabel', own[1]);
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
            const seated = this._bwSeat(P.facts, geo, painted.discs);
            if (seated.size) {
                const again = P.redraw(seated);
                P = { ...P, discs: again.discs, runs: again.runs };
            }
        }
        const log = book.log && book.page && book.page.painting ? {
            side: P.side, scale: K, rows: P.rows, pitch: P.pitch,
            map: geo ? { x: geo.wall.x, y: geo.wall.y, w: geo.wall.w, h: geo.wall.h,
                         zoom: geo.zoom, area: geo.area } : null,
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
