// app-binder-wiring: the SIGNAL + POWER sheet - a screen's third sheet,
// after its Power and Data sheets (2026-09-08, on the last page of the
// NACUBO packet: "he gave an example his binder and we could do this for
// power and data drawing from a port to port … the last page is what i
// was talking about").
//
// The drawing area is split by a rule: SIGNAL above, POWER below (a screen
// with one side draws that half alone). Each half, top to bottom:
//   the WALL      - the same _bMap render the Power / Data sheets use
//                   (data-flow view above, power view below), rulers and
//                   brackets off: the stubs replace them
//   the STUBS     - a small rounded tag ON THE PANEL where its run BEGINS
//                   (a primary, a circuit: the run's first panel) or ENDS
//                   (a return: its last) - the very panel the wall's label
//                   disc is drawn on, the tag centred on it: the label the
//                   disc wears ("SR A-1", "SR B-1", "SR1-1"), green / red /
//                   the power label orange. "port 1 needs to go touch
//                   actual port one" (2026-09-09): a stub on the wall's
//                   bottom edge under the run's column landed nowhere. Two
//                   tags whose rows meet and whose panels are too narrow
//                   for both SPREAD along that row (the cluster centred on
//                   the panels it belongs to); a tag on a row of its own
//                   never leaves its panel
//   the WIRING    - an ORTHOGONAL wire from every stub to its socket: down
//                   from the tag THROUGH THE WALL (over the wall's bitmap,
//                   2 px, its colour) to the wall's bottom edge and on to
//                   a LEVEL, across, down onto the socket - the levels
//                   allocated so no two horizontals overlap on one level and
//                   no horizontal crosses another wire's drop (below).
//                   Runs that begin in one column (a wall whose runs go
//                   across: every primary in column 1) share the column's
//                   vertical LANE side by side, LANE_GAP apart, the wire
//                   landing farthest right in the rightmost lane, so the
//                   drops never overprint and the fan below never crosses
//   the DEVICES   - SCHEMATIC BLOCKS ("Schematic blocks", no product
//                   photos): a rounded block captioned with the device, a
//                   row of numbered sockets. Signal: one block per device
//                   the screen's port ends land on, in the order the ports
//                   meet them - a breakout box ("CVT4K-S SR A · Card 1 ·
//                   OPT 1-2"), or the card itself where no box delivers the
//                   port ("H9 Card 1 · H_16xRJ45+2xfiber"); a backup box is
//                   its own block ("one per cvt including backups so if two
//                   cvt's or 4 need to be on screen then so be it"); a
//                   socket is green where a primary lands, red where a
//                   return does, a grey ring unused. Power: one block per
//                   multi the screen's circuits are on - its BREAKOUT, the
//                   fan-out ("there are no boxes... it is a breakout also
//                   known as a fan out / but i like the first option"):
//                   "SR1 · Multi 208 breakout · 125'", its circuit slots as
//                   sockets (6 / 6 / 3), this screen's filled orange, another
//                   screen's on a shared multi grey with that screen's name
//                   under it, the rest grey rings. The home run is the
//                   caption's length, not a wire.
//
// THE LEVELS RULE. A wire is three segments: its stub's drop to level L,
// the horizontal at L to the socket's x, the drop onto the socket. Two
// wires a, b conflict where b's STUB drop passes through a's horizontal
// (b's stub x inside a's span - then b must sit ABOVE a, its drop stopping
// short of a's level) or where b's SOCKET drop does (b's socket x inside
// a's span - then b must sit BELOW a). Those pairs are edges of a graph;
// the wires are taken in a topological order of it (a cycle - a short wire
// wholly inside a long one's span - is broken at the wire with the least
// claim, and that one crossing stands) and each takes the highest level
// that keeps it under every wire it must be under and whose occupied
// horizontals it does not overlap. A fan that travels right lands its
// largest socket on top; the mirror fan its smallest; two fans that never
// overlap share their levels; a wire straight down takes none. That is the
// example's picture. Levels are 14 px apart at base, the band exactly as
// tall as it needs.
//
// THE FILL. The wall comes first: it takes the zoom the half's width allows
// (capped at 3x like every map) and the height that needs; the half's
// type - stubs, block captions, sockets - and its blocks then scale by the
// fill rule (1 to FILL_CAP) into the height the wall cannot use and the
// width the block row allows. A wall taller than the room (a 28 x 11 on a
// Tabloid half) leaves the type at 1 and takes what the stack at 1 leaves,
// never less than MAP_FLOOR_FRAC of the half - past that the wiring band
// tightens its level pitch instead. The sheet's plan reports the smaller
// half's scale. Everything is drawn in page units, so the recorder writes the
// display list as the sheet prints; the PDF gets it as vector. Circles are
// short polylines (a filled socket is a ring as wide as its radius) - the
// recorder knows rects, lines, text and images, nothing else.
//
// One view per sheet: "n  SR - MAIN · SIGNAL + POWER", its bubble under the
// lower half. Every figure is read from the same authorities the Power and
// Data sheets read - _pullPortRuns, _bPortHome, getPortLabelText, the pull
// list's byScreen boxes, screenCircuits, getDistroOutputTypes; nothing is
// recomputed here.
import { LEDRasterApp } from './app-core.js';
import { BINDER_STYLE } from './app-binder.js';

const { INK, RULE, MUTED, FILL_CAP, MAP_ZOOM_CAP, BUBBLE_H } = BINDER_STYLE;

// The wall's gutters on this sheet: no rulers, no brackets - a little air
// for the renderer's own discs and arrowheads at the edges.
const GUT = { left: 40, right: 40, top: 24, bottom: 0 };
// The half's head word (SIGNAL / POWER), the rule between the halves.
const HEAD_H = 44;
const RULE_GAP = 40;
// The stubs: on their panels, their type, their padding, their corner,
// the air between two that spread along a row.
const STUB_H = 30;
const STUB_PADX = 10;
const STUB_R = 7;
const STUB_SPREAD_GAP = 6;
// The lanes: wires dropping from tags in one column sit this far apart.
const LANE_GAP = 6;
// The wiring band: its padding, the level pitch (and the least pitch a
// crowded half may fall to before the wall gives up more room).
const GAP = 22;
const BAND_PAD = 20;
const LEVEL_PITCH = 14;
const LEVEL_PITCH_MIN = 8;
const WIRE_W = 2;
const RETURN_DASH = [14, 8];
// The blocks: the socket disc, the pitch between sockets (shrunk before a
// row wraps), the block's padding, caption, corner, the gaps.
const SOCKET_R = 12;
const SOCKET_PITCH = 44;
const SOCKET_MIN_PITCH = 28;
const BLOCK_PADX = 22;
const CAPTION_H = 42;
const SOCKET_DY = CAPTION_H + 20;           // the socket row's centre under the block's top
const NUMBER_DY = SOCKET_R + 18;            // the socket number's baseline under its centre
const NOTE_DY = SOCKET_R + 36;              // another screen's name under that
const BLOCK_H = SOCKET_DY + NUMBER_DY + 10;
const NOTE_H = 20;
const BLOCK_GAP = 60;
const ROW_GAP = 26;
const BLOCK_R = 12;
// Type, in page px at 200 px/in.
const SZW = { head: 26, stub: 20, caption: 22, socket: 15, note: 14 };
// Inks the palette does not set.
const GREY_RING = '#9a9a9a';
const GREY_FILL = '#bdbdbd';
const WHITE = '#ffffff';
// The wall's least share of a half's height, at 1; past that a crowded
// band tightens its pitch instead.
const MAP_FLOOR_FRAC = 0.4;

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
        const scale = Math.min(...plans.map(p => p.scale));
        const view = ++book.views;
        this._bPage(book, {
            kind: 'wiring', title, sheetTitle, viewName: sheetTitle, view,
            layerId: layer.id, subject: layer.name, position: pos ? pos.name : null,
            layout: 'wiring', cols: order.length, scale,
            sides: { power: !!sides.power, data: !!sides.data },
            halves: plans.map(p => ({ side: p.side, scale: p.scale, levels: p.levels,
                                      stubs: p.stubs.length, wires: p.wires.length, blocks: p.blocks.length })),
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
                const title = home.box
                    ? [this._bBoxTitle(home.box), home.cardTitle, home.box.trunkTitle || ''].filter(Boolean).join(' · ')
                    : `${home.procTitle} ${home.cardTitle} · ${home.card.deviceName}`;
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

    // ---- the geometry -------------------------------------------------------

    // One half laid out in page units, nothing painted: the map's area
    // and the wall's geometry (from a dry measure), the stubs, the wires
    // with their levels, the blocks with their sockets, and the half's
    // type scale.
    _bwPlanHalf(book, layer, scr, side, A) {
        const facts = side === 'signal' ? this._bwSignalFacts(book, layer) : this._bwPowerFacts(book, layer, scr);
        const view = side === 'signal' ? 'data-flow' : 'power';
        const ctxM = book.measureCtx;
        const measure = (text, size, weight) => {
            ctxM.font = this._bFont(size, weight);
            return ctxM.measureText(String(text)).width;
        };
        const devices = facts.devices;
        for (const d of devices) {
            d.n = Math.max(1, Number(d.n) || 0, ...d.sockets.keys());
            d.captionW = measure(d.title, SZW.caption, 700);
            d.hasNotes = d.notes.size > 0;
        }
        const anyNotes = devices.some(d => d.hasNotes);
        const blockH = BLOCK_H + (anyNotes ? NOTE_H : 0);
        const widthOf = (d, pitch) => Math.max(d.captionW + 2 * BLOCK_PADX, d.n * pitch + 2 * BLOCK_PADX);
        const rowW = (pitch) => devices.reduce((sum, d) => sum + widthOf(d, pitch), 0)
            + Math.max(0, devices.length - 1) * BLOCK_GAP;
        // the socket pitch: the base pitch, shrunk (never under its floor)
        // until the row fits the half's width at 1
        let pitch = SOCKET_PITCH;
        while (pitch > SOCKET_MIN_PITCH && rowW(pitch) > A.w) pitch -= 1;
        // the blocks in rows, greedily, at a scale s
        const rowsAt = (s) => {
            const rows = [];
            let cur = null;
            for (const d of devices) {
                const w = widthOf(d, pitch) * s;
                if (!cur || (cur.blocks.length && cur.w + BLOCK_GAP * s + w > A.w)) {
                    cur = { blocks: [], w: 0 };
                    rows.push(cur);
                }
                cur.w += (cur.blocks.length ? BLOCK_GAP * s : 0) + w;
                cur.blocks.push({ device: d, w });
            }
            return rows;
        };
        const nWires = facts.wires.length;
        const blocksH = (rows) => rows.length ? rows.length * blockH + (rows.length - 1) * ROW_GAP : 0;
        let levelPitch = LEVEL_PITCH;
        const bandH = (levels) => nWires ? 2 * BAND_PAD + Math.max(0, levels - 1) * levelPitch : 0;
        const fixedH = (levels, rows) => HEAD_H + (nWires ? GAP + bandH(levels) : 0)
            + (rows.length ? GAP + blocksH(rows) : 0);
        const clamp = (v) => Math.max(1, Math.min(FILL_CAP, Math.floor(v * 1000) / 1000));

        // pass A at 1 with every wire on its own level (the most the band
        // can need) - to learn how many levels the picture really takes
        const rows1 = rowsAt(1);
        let P = this._bwPlace(book, layer, facts, view, A, 1, pitch, nWires, levelPitch, rows1, blockH, bandH, fixedH);
        const F = fixedH(P.levels, rows1);
        // the wall first: the height it takes at the zoom the width allows
        // (the wall's world size from the probe; the cap like every map)
        const g = P.geo;
        const ww = g && g.zoom > 0 ? g.wall.w / g.zoom : 0, wh = g && g.zoom > 0 ? g.wall.h / g.zoom : 0;
        const zoomW = ww > 0 ? Math.min(MAP_ZOOM_CAP, (A.w - GUT.left - GUT.right) / ww) : 0;
        const wallH = HEAD_H + GUT.top + GUT.bottom + wh * zoomW;
        // pass B: the type and blocks fill the height the wall cannot use
        // and the width the block row allows
        let s = clamp(Math.min(FILL_CAP, devices.length ? A.w / rowW(pitch) : FILL_CAP,
                               (A.h - wallH) / Math.max(1, F)));
        // a crowded band at 1 (a wall of many circuits on a small sheet)
        // tightens its level pitch rather than squeezing the wall past its
        // floor
        if (s === 1 && F > A.h * (1 - MAP_FLOOR_FRAC) && P.levels > 1) {
            const budget = A.h * (1 - MAP_FLOOR_FRAC) - (F - bandH(P.levels)) - 2 * BAND_PAD;
            levelPitch = Math.max(LEVEL_PITCH_MIN, Math.min(LEVEL_PITCH, Math.floor(budget / (P.levels - 1))));
        }
        let rows = rowsAt(s);
        P = this._bwPlace(book, layer, facts, view, A, s, pitch, P.levels, levelPitch, rows, blockH, bandH, fixedH);
        // pass C, only when the picture at s needs more levels than the band
        // was sized for: the band grows and everything under it moves down
        if (P.levels > P.bandLevels) {
            P = this._bwPlace(book, layer, facts, view, A, s, pitch, P.levels, levelPitch, rows, blockH, bandH, fixedH);
        }
        return { ...P, side, view, scale: s, A, pitch: pitch * s, levelPitch, facts, anyNotes, blockH: blockH * s };
    }

    // The half's picture at scale s with a band sized for `bandLevels`
    // levels: the map's area (the room the fixed stack leaves), the wall's
    // geometry, the stubs on their panels, the blocks under the wall, the
    // wires with their lanes and their levels allocated. Returns the lot,
    // with the levels the wires actually took.
    _bwPlace(book, layer, facts, view, A, s, pitch, bandLevels, levelPitch, rows, blockH, bandH, fixedH) {
        const ctxM = book.measureCtx;
        const measure = (text, size, weight) => {
            ctxM.font = this._bFont(size, weight);
            return ctxM.measureText(String(text)).width;
        };
        const F = fixedH(bandLevels, rows) * s;
        const mapH = Math.max(Math.round(A.h * MAP_FLOOR_FRAC), A.h - F);
        const mapArea = { x: A.x, y: A.y + HEAD_H * s, w: A.w, h: Math.max(1, mapH - HEAD_H * s) };
        const geo = this._bMeasureMap(book, { measure: (area) => this._bMap(book, layer, view, area, GUT) }, mapArea);
        const wall = geo ? geo.wall : { x: A.x, y: mapArea.y, w: A.w, h: 0 };
        const wallBottom = wall.y + wall.h;
        const wallCx = wall.x + wall.w / 2;

        // the stubs: a tag ON THE PANEL its run begins (or ends) on - "port
        // 1 needs to go touch actual port one" (2026-09-09). `panel` is
        // that panel's rect on the page, `col` / `cy` its centre, `cx`
        // where the tag's centre lands once a row that would overprint has
        // spread. The tag keeps to the wall's bitmap: a run beginning on
        // the bottom row lifts its tag off the band.
        const stubs = facts.stubs.map((st, i) => {
            const p = st.panel;
            const rc = geo ? geo.rect(p.x, p.y, p.width, p.height)
                : { x: wallCx, y: wall.y, w: 0, h: wall.h };
            const col = rc.x + rc.w / 2;
            const cy = rc.y + rc.h / 2;
            const w = Math.ceil(measure(st.text, SZW.stub * s, 700) + 2 * STUB_PADX * s);
            const h = STUB_H * s;
            let y = cy - h / 2;
            if (wall.h >= h) y = Math.max(wall.y, Math.min(wallBottom - h, y));
            return { kind: st.kind, text: st.text, port: st.port, circuit: st.circuit,
                     col, cy, panel: { x: rc.x, y: rc.y, w: rc.w, h: rc.h },
                     cx: col, x: col - w / 2, w, h, y, order: i, src: st };
        });
        // a tag stays on its panel when it can: only tags whose rows meet
        // can overprint, so each band of tags spreads on its own
        for (const row of this._bwStubRows(stubs)) {
            this._bwSpread(row, A.x, A.x + A.w, STUB_SPREAD_GAP * s);
        }

        // the band, the blocks under it - the stubs are ON the wall now, so
        // the band starts under the wall itself
        const nWires = facts.wires.length;
        const bandTop = wallBottom + (nWires ? GAP * s : 0);
        const bandHeight = bandH(bandLevels) * s;
        const blocksTop = bandTop + bandHeight + (rows.length ? GAP * s : 0);
        const blocks = [];
        const socketAt = new Map();      // device key -> Map(socket n -> x)
        rows.forEach((row, ri) => {
            let x = Math.max(A.x, Math.min(A.x + A.w - row.w, wallCx - row.w / 2));
            const y = blocksTop + ri * (blockH + ROW_GAP) * s;
            for (const { device: d, w } of row.blocks) {
                const socketsW = d.n * pitch * s;
                const sx0 = x + (w - socketsW) / 2;
                const cy = y + SOCKET_DY * s;
                const sockets = [];
                const xs = new Map();
                for (let k = 1; k <= d.n; k++) {
                    const cx = sx0 + (k - 0.5) * pitch * s;
                    xs.set(k, cx);
                    sockets.push({ n: k, x: cx, y: cy, state: d.sockets.get(k) || 'free', note: d.notes.get(k) || null });
                }
                socketAt.set(d.key, xs);
                blocks.push({ key: d.key, title: d.title, x, y, w, h: blockH * s, sockets, device: d });
                x += w + BLOCK_GAP * s;
            }
        });

        // the wires: the tag's bottom edge - down THROUGH the wall, over
        // its bitmap - to the socket's top, their lanes and their levels
        const byStub = new Map(stubs.map(st => [st.src, st]));
        const wires = facts.wires.map(w => {
            const st = byStub.get(w.stub);
            const xs = socketAt.get(w.device.key);
            const x2 = xs ? xs.get(w.socket) : st.cx;
            const block = blocks.find(b => b.key === w.device.key);
            const y2 = block ? block.y + SOCKET_DY * s - SOCKET_R * s : bandTop + bandHeight;
            return { kind: w.kind, from: st.text, device: w.device.title, socket: w.socket,
                     x1: st.cx, y1: st.y + st.h, x2, y2, lane: null, level: null, y: null };
        });
        this._bwLanes(wires, LANE_GAP * s);
        const levels = this._bwLevels(wires, 6 * s);
        const levelY = (i) => bandTop + BAND_PAD * s + i * levelPitch * s;
        for (const w of wires) if (w.level != null) w.y = levelY(w.level);
        return { mapArea, geo, wall, stubs, blocks, wires, levels, bandLevels, bandTop, bandHeight, blocksTop, scale: s };
    }

    // The tags in bands that could overprint: sorted by their tops, a new
    // band begun wherever a tag clears the one before it. Tags on
    // different rows of the wall never meet, so each band spreads on its
    // own and a tag whose row is its alone never leaves its panel.
    _bwStubRows(stubs) {
        const rows = [];
        let cur = null, floor = -Infinity;
        for (const st of [...stubs].sort((a, b) => a.y - b.y || a.order - b.order)) {
            if (!cur || st.y >= floor) { cur = []; rows.push(cur); floor = -Infinity; }
            cur.push(st);
            floor = Math.max(floor, st.y + st.h);
        }
        return rows;
    }

    // Wires that drop from ONE column would print one drop over another -
    // the Experts Only walls run across, so every primary begins in column
    // 1. They share the column's vertical LANE side by side, `gap` apart
    // and still under their tag, in the order they land: the wire landing
    // farthest right in the rightmost lane, so the fan below never crosses
    // itself. Sets `lane` and moves `x1`; a column with one wire keeps it.
    _bwLanes(wires, gap) {
        const groups = new Map();
        for (const w of wires) {
            const key = Math.round(w.x1 * 100) / 100;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(w);
        }
        for (const [key, ws] of groups) {
            if (ws.length < 2) continue;
            ws.sort((a, b) => a.x2 - b.x2 || a.y2 - b.y2 || a.y1 - b.y1);
            ws.forEach((w, i) => {
                w.lane = i;
                w.x1 = key + (i - (ws.length - 1) / 2) * gap;
            });
        }
    }

    // Tags along one row, each wanting its centre at `col`, none
    // overlapping, all between lo and hi: tags in column order (ties in
    // their own order), a run of tags that would overlap merged into one
    // CLUSTER centred on the mean of its columns, clusters merged again
    // where they touch, until none do - the usual one-dimensional label
    // spread. Sets x and cx on every tag.
    _bwSpread(tags, lo, hi, gap) {
        if (!tags.length) return;
        const sorted = [...tags].sort((a, b) => a.col - b.col || a.order - b.order);
        let clusters = sorted.map(t => ({ items: [t], w: t.w, want: t.col - t.w / 2, x: 0 }));
        const settle = (c) => {
            c.w = c.items.reduce((sum, t) => sum + t.w, 0) + (c.items.length - 1) * gap;
            // where the cluster's left edge wants to be: the mean of each
            // tag's wish less its offset inside the cluster
            let off = 0, sum = 0;
            for (const t of c.items) { sum += t.col - t.w / 2 - off; off += t.w + gap; }
            c.want = sum / c.items.length;
            c.x = Math.max(lo, Math.min(hi - c.w, c.want));
        };
        clusters.forEach(settle);
        for (let guard = 0; guard < tags.length + 1; guard++) {
            let merged = false;
            const next = [];
            for (const c of clusters) {
                const prev = next[next.length - 1];
                if (prev && prev.x + prev.w + gap > c.x) {
                    prev.items.push(...c.items);
                    settle(prev);
                    merged = true;
                } else {
                    next.push(c);
                }
            }
            clusters = next;
            if (!merged) break;
        }
        for (const c of clusters) {
            let x = c.x;
            for (const t of c.items) { t.x = x; t.cx = x + t.w / 2; x += t.w + gap; }
        }
    }

    // The levels: see THE LEVELS RULE above. Sets `level` on every wire
    // that turns (null on a straight drop) and returns how many levels the
    // half takes. `margin` is the air two horizontals on one level keep.
    _bwLevels(wires, margin) {
        const eps = 0.5;
        const turning = wires.filter(w => Math.abs(w.x1 - w.x2) >= eps);
        for (const w of wires) w.level = null;
        if (!turning.length) return 0;
        const lo = (w) => Math.min(w.x1, w.x2), hi = (w) => Math.max(w.x1, w.x2);
        const inside = (x, w) => x > lo(w) + eps && x < hi(w) - eps;
        // over.get(w) = the wires that must sit OVER w
        const over = new Map(turning.map(w => [w, new Set()]));
        for (const a of turning) {
            for (const b of turning) {
                if (a === b) continue;
                if (inside(b.x1, a)) over.get(a).add(b);     // b's stub drop through a: b over a
                if (inside(b.x2, a)) over.get(b).add(a);     // b's socket drop through a: b under a
            }
        }
        // the topological order, top down: a wire is ready when everything
        // that must sit over it is placed; among the ready, a right-
        // travelling fan lands its largest socket first, a left-travelling
        // one its smallest (the mirror); a cycle is broken at the readiest
        // wire
        const rank = (w) => (w.x2 > w.x1 ? -w.x2 : w.x2 - 1e9);
        const pending = new Set(turning);
        const order = [];
        while (pending.size) {
            let ready = [...pending].filter(w => [...over.get(w)].every(u => !pending.has(u)));
            if (!ready.length) {
                // a cycle: take the wire with the fewest unplaced constraints
                let best = null, bestN = Infinity;
                for (const w of pending) {
                    const n = [...over.get(w)].filter(u => pending.has(u)).length;
                    if (n < bestN || (n === bestN && rank(w) < rank(best))) { best = w; bestN = n; }
                }
                ready = [best];
            }
            ready.sort((a, b) => rank(a) - rank(b));
            const w = ready[0];
            order.push(w);
            pending.delete(w);
        }
        // the levels: the highest that sits under every wire it must and
        // overlaps no horizontal already there
        const spans = [];        // per level: [{ lo, hi }]
        for (const w of order) {
            let min = 0;
            for (const u of over.get(w)) if (u.level != null) min = Math.max(min, u.level + 1);
            let L = min;
            const l = lo(w) - margin, h = hi(w) + margin;
            while (spans[L] && spans[L].some(sp => sp.lo < h && l < sp.hi)) L++;
            (spans[L] || (spans[L] = [])).push({ lo: l, hi: h });
            w.level = L;
        }
        return spans.length;
    }

    // ---- the paint ----------------------------------------------------------

    _bwDrawHalf(book, layer, P) {
        const ctx = book.ctx;
        const s = P.scale;
        const printer = book.meta.palette === 'printer';
        const A = P.A;
        // the head word
        this._bText(book, P.side === 'signal' ? 'SIGNAL' : 'POWER', A.x, A.y + 30 * s,
                    { size: SZW.head * s, weight: 700, color: MUTED });
        // the wall - the same render, painted now
        const geo = this._bMap(book, layer, P.view, P.mapArea, GUT);
        const log = book.log && book.page && book.page.painting ? {
            side: P.side, scale: s, levels: P.levels, levelPitch: P.levelPitch * s,
            map: geo ? { x: geo.wall.x, y: geo.wall.y, w: geo.wall.w, h: geo.wall.h, zoom: geo.zoom, area: geo.area } : null,
            stubs: [], wires: [], blocks: [], bandTop: P.bandTop, bandHeight: P.bandHeight,
        } : null;
        // the palette
        const primary = printer ? INK : (layer.primaryColor || '#00FF00');
        const primaryInk = printer ? INK : (layer.primaryTextColor || '#000000');
        const backup = printer ? INK : (layer.backupColor || '#FF0000');
        const backupInk = printer ? INK : (layer.backupTextColor || '#FFFFFF');
        const orange = printer ? INK : (layer.powerLabelBgColor || '#D95000');
        const orangeInk = printer ? INK : (layer.powerLabelTextColor || '#000000');
        const wireColour = (kind) => kind === 'primary' ? primary : kind === 'return' ? backup : INK;
        const tagFill = (kind) => printer ? WHITE : kind === 'primary' ? primary : kind === 'return' ? backup : orange;
        const tagInk = (kind) => printer ? INK : kind === 'primary' ? primaryInk : kind === 'return' ? backupInk : orangeInk;

        // the wires first, so the tags and the blocks sit over their ends
        for (const w of P.wires) {
            ctx.strokeStyle = wireColour(w.kind);
            ctx.lineWidth = WIRE_W;
            ctx.setLineDash(printer && w.kind === 'return' ? RETURN_DASH : []);
            ctx.beginPath();
            ctx.moveTo(w.x1, w.y1);
            if (w.level != null) {
                ctx.lineTo(w.x1, w.y);
                ctx.lineTo(w.x2, w.y);
                ctx.lineTo(w.x2, w.y2);
            } else {
                ctx.lineTo(w.x2, w.y2);
            }
            ctx.stroke();
            if (log) log.wires.push({ kind: w.kind, from: w.from, device: w.device, socket: w.socket,
                                      x1: w.x1, y1: w.y1, x2: w.x2, y2: w.y2, lane: w.lane, level: w.level, y: w.y,
                                      colour: ctx.strokeStyle, dash: printer && w.kind === 'return' ? RETURN_DASH : [] });
        }
        ctx.setLineDash([]);
        // the stubs
        for (const st of P.stubs) {
            this._bwRound(ctx, st.x, st.y, st.w, st.h, STUB_R * s, tagFill(st.kind), INK, printer ? 2 : 1.5);
            this._bText(book, st.text, st.x + st.w / 2, st.y + st.h / 2 + 7 * s,
                        { size: SZW.stub * s, weight: 700, align: 'center', color: tagInk(st.kind) });
            if (log) log.stubs.push({ kind: st.kind, text: st.text, x: st.x, y: st.y, w: st.w, h: st.h,
                                      cx: st.cx, cy: st.y + st.h / 2, col: st.col, panel: st.panel });
        }
        // the blocks
        for (const b of P.blocks) {
            this._bwRound(ctx, b.x, b.y, b.w, b.h, BLOCK_R * s, null, INK, 2.5);
            const title = this._bText(book, b.title, b.x + b.w / 2, b.y + 30 * s,
                                      { size: SZW.caption * s, weight: 700, align: 'center',
                                        maxWidth: b.w - 2 * BLOCK_PADX * s, shrink: true });
            const entry = log ? { title, x: b.x, y: b.y, w: b.w, h: b.h, sockets: [] } : null;
            for (const sk of b.sockets) {
                const r = SOCKET_R * s;
                if (sk.state === 'primary' || sk.state === 'power') {
                    this._bwDisc(ctx, sk.x, sk.y, r, sk.state === 'primary' ? primary : orange);
                    this._bwRing(ctx, sk.x, sk.y, r, INK, 1.5);
                } else if (sk.state === 'return') {
                    // a return's socket: red - on the printer page a hollow
                    // ring, the way its wire is dashed
                    if (printer) this._bwRing(ctx, sk.x, sk.y, r, INK, 3);
                    else { this._bwDisc(ctx, sk.x, sk.y, r, backup); this._bwRing(ctx, sk.x, sk.y, r, INK, 1.5); }
                } else if (sk.state === 'other') {
                    this._bwDisc(ctx, sk.x, sk.y, r, GREY_FILL);
                    this._bwRing(ctx, sk.x, sk.y, r, GREY_RING, 1.5);
                } else {
                    this._bwRing(ctx, sk.x, sk.y, r, GREY_RING, 2);
                }
                this._bText(book, String(sk.n), sk.x, sk.y + NUMBER_DY * s,
                            { size: SZW.socket * s, weight: 400, align: 'center', color: INK });
                if (sk.note) {
                    this._bText(book, sk.note, sk.x, sk.y + NOTE_DY * s,
                                { size: SZW.note * s, weight: 400, align: 'center', color: MUTED,
                                  maxWidth: P.pitch * 2.4, shrink: true });
                }
                if (entry) entry.sockets.push({ n: sk.n, x: sk.x, y: sk.y, state: sk.state, note: sk.note });
            }
            if (log) log.blocks.push(entry);
        }
        if (log) book.log.wiring.halves.push(log);
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

    // A filled disc: a closed polyline at half the radius stroked as wide
    // as the radius (24 segments).
    _bwDisc(ctx, cx, cy, r, colour) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = r;
        ctx.setLineDash([]);
        this._bwArc(ctx, cx, cy, r / 2, 0, 2 * Math.PI, 24);
    }

    // A ring: a closed polyline at the radius (24 segments).
    _bwRing(ctx, cx, cy, r, colour, width) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.setLineDash([]);
        this._bwArc(ctx, cx, cy, r, 0, 2 * Math.PI, 24);
    }
}

for (const k of Object.getOwnPropertyNames(_BinderWiring.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_BinderWiring.prototype, k));
    }
}
