// app-binder-overlays: what each binder map sheet put on its map, for the
// log (owner, 2026-11-20). A thin grey line with ticks turned up under a
// wall on a Power sheet and nothing said what drew it. Now every sheet
// that paints a map writes ONE info line naming every overlay it drew,
// with its count and the setting or source that put it there:
//
//   Binder 2.3 UPSTAGE · POWER · REAR: cabinets 48, runs 11 (power),
//   cable tags 5 (showPowerCableTags), 2fer brackets 2 (always on),
//   badge BACK (Rear view), rulers top/left
//
// and one debug line with each overlay's boxes in sheet units, so a mark
// at a place on the paper can be matched to what drew it.
//
// Complete by construction, not by a list someone has to keep up:
//   - The renderer's pass onto the map bitmap is watched at the canvas:
//     every fill, stroke, text and image it draws is boxed and put down to
//     the renderer method that was drawing (RENDER_OVERLAYS), else to the
//     stage the renderer said it was in (_svgGroup), else to "other ink".
//   - What the binder itself draws on the sheet is read off the sheet's
//     display list: the ops a tagged painter (BINDER_OVERLAYS, or a section
//     marked with _bInkMark) wrote go to it, and any other op that lands
//     on the map is "other ink on the map".
// So a new painter that draws something nobody tagged still shows, as
// "other ink", with its box.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const P = LEDRasterApp.prototype;

// The sheet's current ledger (one sheet paints at a time).
let LEDGER = null;

const MAX_BOXES = 12;

// ── the renderer's overlays ───────────────────────────────────────────────
//
// name: the renderer method; kind: the overlay it draws (a function of
// its args where one method draws two); why: the setting or source that
// turns it on; count: how many it drew - 'calls' (each call that inked),
// 'label:<kind>' (the label registry's notes of that kind made inside it)
// or a function of (renderer, args).
const view = (r) => (r.viewMode === 'power' ? 'power' : r.viewMode === 'data-flow' ? 'data' : r.viewMode);
const RENDER_OVERLAYS = {
    renderPanel: { kind: 'cabinets', why: null },
    renderImageLayer: { kind: 'images', why: 'image layer' },
    renderTextLayer: { kind: 'text layers', why: 'text layer' },
    renderCircleWithX: { kind: 'test pattern', why: 'showCircleWithX' },
    renderPixelGrid: { kind: 'pixel grid', why: 'zoom' },
    renderCabinetIDNumbers: { kind: 'cabinet ids', count: 'label:cabinetId',
        why: (r, [l]) => `cabinetIdStyle ${(l && l.cabinetIdStyle) || 'default'}` },
    renderDataFlowArrows: { kind: 'runs', why: () => 'data', count: 'label:disc' },
    renderPowerArrows: { kind: 'runs', why: () => 'power', count: 'label:disc' },
    _renderCrossMemberPaths: { kind: 'runs across the group', why: 'group' },
    drawCableTag: {
        kind: (r, args) => (args[6] === 'gang' ? '2fer tags' : 'cable tags'),
        why: (r, args) => (args[6] === 'gang' ? 'showPowerNferTags'
            : view(r) === 'power' ? 'showPowerCableTags' : 'showDataCableTags'),
    },
    renderNferBrackets: { kind: '2fer brackets', why: 'always on',
        count: (r, [l]) => { try { return r._nferGangs(l).length || 1; } catch (e) { return 1; } } },
    renderSocaBrackets: { kind: 'multi brackets', count: 'label:band',
        why: (r, [l, pendingOnly]) => (pendingOnly ? 'a plug drag' : 'showSocaBrackets') },
    renderBoxPower: {
        kind: (r, [, pass]) => (pass === 'feeds' ? 'box power feeds' : 'box power'),
        why: 'box power', count: 'label:box' },
    drawPortLoadBadge: { kind: 'port load badges', why: 'showDataFlowPortLoad' },
    _drawMergeFreedRings: { kind: 'freed port rings', why: 'a merge' },
    renderCapacityErrorOverlay: { kind: 'capacity error overlays', why: 'over capacity' },
    renderPowerErrorOverlay: { kind: 'power error overlays', why: 'power error' },
    renderRiggingBars: { kind: 'header/footer bars',
        why: (r, [l]) => (l && l.riggingSide ? `riggingSide ${l.riggingSide}` : 'Header/Footer'),
        count: (r, [l]) => ((l && Array.isArray(l.riggingBars) ? l.riggingBars.length : 0)
            + (l && Array.isArray(l.riggingFooterBars) ? l.riggingFooterBars.length : 0)) || 1 },
    _drawRiggingFold: { kind: 'bar folds', why: 'riggingCurve' },
    _drawRiggingGhost: { kind: 'bars over a neighbour (dashed)', why: 'a group seam' },
    _drawRiggingMisfit: { kind: 'bars that no longer fit', why: 'a misfit' },
    renderPerspectiveBadge: { kind: 'badge', why: 'Rear view', text: true },
    renderLayerLabels: { kind: 'screen labels', why: 'Screen name' },
    renderLayerOffsets: { kind: 'offsets', why: 'showOffsetX/Y' },
    _renderCornerReadouts: { kind: 'corner readouts', why: 'showOffsetTL/TR/BL/BR' },
    _drawCanvasOutline: { kind: 'canvas outline', why: 'canvas' },
    _drawActiveCanvasTint: { kind: 'canvas tint', why: 'canvas' },
};

// What the label registry notes inside an overlay, given an entry of its
// own (the leg ruler under a multi's bracket is drawn by renderSocaBrackets
// but is a thing of its own on the paper).
const LABEL_ENTRIES = {
    rulerTick: { kind: 'leg ticks', why: 'showSocaBrackets' },
};

// The renderer's stages (_svgGroup), for ink no method above was drawing.
const GROUP_KINDS = {
    Panels: 'cabinets', Borders: 'cabinet borders', 'Screen name': 'screen labels',
    'Cabinet IDs': 'cabinet ids', 'Test pattern': 'test pattern', 'Back view': 'badge',
    Images: 'images', Text: 'text layers', Rigging: 'header/footer (other)',
    Power: 'power (other)', Data: 'data (other)',
};

// ── the binder's own overlays ────────────────────────────────────────────
//
// Painters that draw on the sheet. `furniture`: sheet furniture, boxed in
// the debug line but not an overlay of the map (the view bubble, tables);
// `internal`: the map bitmap itself.
const BINDER_OVERLAYS = {
    _bLayMapBitmap: { kind: 'map bitmap', internal: true },
    _bRulers: { kind: 'rulers', why: null, sides: 2 },
    _bRulersAcross: { kind: 'rulers', why: 'group', sides: 2 },
    _bSimpleRulers: { kind: 'rulers', why: null, sides: 2 },
    _bWallOutline: { kind: 'wall outline', why: null },
    _bBoxBrackets: { kind: 'gutter brackets', why: 'power sheet' },
    _bBracketKey: { kind: 'bracket key', why: 'brackets too long for the gutter' },
    _bViewBubble: { kind: 'view bubble', furniture: true },
    _bDrawLayout: { kind: 'tables', furniture: true },
    _bSimpleTables: { kind: 'tables', furniture: true },
};

// ── geometry ─────────────────────────────────────────────────────────────

function grow(box, x1, y1, x2, y2) {
    if (!(Number.isFinite(x1) && Number.isFinite(y1) && Number.isFinite(x2) && Number.isFinite(y2))) return box;
    if (!box) return [x1, y1, x2, y2];
    box[0] = Math.min(box[0], x1); box[1] = Math.min(box[1], y1);
    box[2] = Math.max(box[2], x2); box[3] = Math.max(box[3], y2);
    return box;
}

function hull(m, pts) {
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (let i = 0; i < pts.length; i += 2) {
        const x = m.a * pts[i] + m.c * pts[i + 1] + m.e;
        const y = m.b * pts[i] + m.d * pts[i + 1] + m.f;
        if (x < x1) x1 = x; if (x > x2) x2 = x;
        if (y < y1) y1 = y; if (y > y2) y2 = y;
    }
    return [x1, y1, x2, y2];
}

// The map context watched: each drawing call boxes its ink in the
// bitmap's pixels and hands it to ctx.__inkSink while one is set. Wrapped
// once per context (the offscreen map canvas is reused for every sheet);
// with no sink set every call goes straight through.
function watchContext(ctx) {
    if (!ctx || ctx.__inkWatched) return;
    ctx.__inkWatched = true;
    let path = null;
    const note = (pts, inflate) => {
        const sink = ctx.__inkSink;
        if (!sink) return;
        const op = ctx.globalCompositeOperation;
        if (op === 'destination-out' || op === 'destination-in') return;
        let m;
        try { m = ctx.getTransform(); } catch (e) { return; }
        const b = hull(m, pts);
        const k = inflate ? inflate * Math.hypot(m.a, m.b) : 0;
        sink(b[0] - k, b[1] - k, b[2] + k, b[3] + k);
    };
    const addPath = (pts) => {
        if (!ctx.__inkSink) return;
        let m;
        try { m = ctx.getTransform(); } catch (e) { return; }
        path = grow(path, ...hull(m, pts));
    };
    const wrap = (name, fn) => {
        const real = ctx[name];
        if (typeof real !== 'function') return;
        ctx[name] = function (...args) { fn(...args); return real.apply(ctx, args); };
    };
    wrap('beginPath', () => { path = null; });
    wrap('moveTo', (x, y) => addPath([x, y]));
    wrap('lineTo', (x, y) => addPath([x, y]));
    wrap('rect', (x, y, w, h) => addPath([x, y, x + w, y, x, y + h, x + w, y + h]));
    wrap('roundRect', (x, y, w, h) => addPath([x, y, x + w, y, x, y + h, x + w, y + h]));
    wrap('arc', (x, y, r) => addPath([x - r, y - r, x + r, y - r, x - r, y + r, x + r, y + r]));
    wrap('ellipse', (x, y, rx, ry) => {
        const r = Math.max(rx, ry);
        addPath([x - r, y - r, x + r, y - r, x - r, y + r, x + r, y + r]);
    });
    wrap('arcTo', (x1, y1, x2, y2) => addPath([x1, y1, x2, y2]));
    wrap('quadraticCurveTo', (cx, cy, x, y) => addPath([cx, cy, x, y]));
    wrap('bezierCurveTo', (a, b, c, d, x, y) => addPath([a, b, c, d, x, y]));
    const drawPath = (stroke, first) => {
        const sink = ctx.__inkSink;
        if (!sink) return;
        if (typeof Path2D !== 'undefined' && first instanceof Path2D) {
            // a Path2D's extent is not readable: the whole bitmap
            sink(0, 0, ctx.canvas.width, ctx.canvas.height);
            return;
        }
        if (!path) return;
        const op = ctx.globalCompositeOperation;
        if (op === 'destination-out' || op === 'destination-in') return;
        let k = 0;
        if (stroke) {
            try { const m = ctx.getTransform(); k = (ctx.lineWidth || 1) / 2 * Math.hypot(m.a, m.b); } catch (e) { k = 0; }
        }
        sink(path[0] - k, path[1] - k, path[2] + k, path[3] + k);
    };
    wrap('fill', (first) => drawPath(false, first));
    wrap('stroke', (first) => drawPath(true, first));
    wrap('fillRect', (x, y, w, h) => note([x, y, x + w, y, x, y + h, x + w, y + h], 0));
    wrap('strokeRect', (x, y, w, h) => note([x, y, x + w, y, x, y + h, x + w, y + h], (ctx.lineWidth || 1) / 2));
    const text = (stroke) => (t, x, y) => {
        if (!ctx.__inkSink) return;
        let mt = null;
        try { mt = ctx.measureText(String(t)); } catch (e) { mt = null; }
        if (!mt) return;
        const l = Number.isFinite(mt.actualBoundingBoxLeft) ? mt.actualBoundingBoxLeft : 0;
        const r = Number.isFinite(mt.actualBoundingBoxRight) ? mt.actualBoundingBoxRight : mt.width;
        const a = Number.isFinite(mt.actualBoundingBoxAscent) ? mt.actualBoundingBoxAscent : 10;
        const d = Number.isFinite(mt.actualBoundingBoxDescent) ? mt.actualBoundingBoxDescent : 0;
        note([x - l, y - a, x + r, y - a, x - l, y + d, x + r, y + d], stroke ? (ctx.lineWidth || 1) / 2 : 0);
        if (ctx.__inkText) ctx.__inkText(String(t));
    };
    wrap('fillText', text(false));
    wrap('strokeText', text(true));
    wrap('drawImage', (img, ...a) => {
        let x, y, w, h;
        if (a.length >= 8) [, , , , x, y, w, h] = a;
        else if (a.length >= 4) [x, y, w, h] = a;
        else { [x, y] = a; w = (img && img.width) || 0; h = (img && img.height) || 0; }
        note([x, y, x + w, y, x, y + h, x + w, y + h], 0);
    });
}

// ── the ledger ───────────────────────────────────────────────────────────

function newLedger(book, page) {
    return {
        book, page,
        entries: new Map(),      // kind -> { kind, n, why, detail, boxes, furniture }
        pending: new Map(),      // canvas -> renderer ink not yet laid on the sheet
        // [page.ops index, binder tag] from that op on; the sheet's frame
        // (its white, border and title block) went down before and is not
        // the map's
        segs: [[(page.ops || []).length, null]],
        stack: [],               // binder tags in force (wrappers)
        mark: null,              // the section a painter marked (_bInkMark)
        counts: new Map(),       // binder kind -> explicit count (_bInkCount)
        maps: [],                // the map bitmaps laid: sheet rects
        mapLaid: false,
    };
}

function entry(L, kind, why) {
    let e = L.entries.get(kind);
    if (!e) {
        e = { kind, n: 0, why: why || null, detail: null, boxes: [], union: null };
        L.entries.set(kind, e);
    } else if (why && !e.why) {
        e.why = why;
    } else if (why && e.why && !String(e.why).split(', ').includes(String(why))) {
        e.why = `${e.why}, ${why}`;
    }
    return e;
}

function addBox(e, b) {
    if (!b) return;
    e.union = grow(e.union, b[0], b[1], b[2], b[3]);
    if (e.boxes.length < MAX_BOXES) e.boxes.push(b);
}

function segTag(L) {
    const top = L.stack.length ? L.stack[L.stack.length - 1] : null;
    return top || L.mark;
}

function noteSeg(L) {
    const ops = L.page && L.page.ops;
    if (!ops) return;
    const tag = segTag(L);
    const last = L.segs[L.segs.length - 1];
    if (last[0] === ops.length) last[1] = tag;
    else if (last[1] !== tag) L.segs.push([ops.length, tag]);
}

// An op of the display list, boxed in sheet units.
function opBox(op) {
    if (!op) return null;
    if (op.op === 'rect' || op.op === 'image') {
        const k = (op.width || 0) / 2;
        return [op.x - k, op.y - k, op.x + op.w + k, op.y + op.h + k];
    }
    if (op.op === 'line') {
        let b = null;
        for (const [x, y] of op.points || []) b = grow(b, x, y, x, y);
        const k = (op.width || 0) / 2;
        return b ? [b[0] - k, b[1] - k, b[2] + k, b[3] + k] : null;
    }
    if (op.op === 'text') {
        const w = String(op.text || '').length * (op.size || 10) * 0.6;
        const x1 = op.align === 'center' ? op.x - w / 2 : (op.align === 'right' || op.align === 'end') ? op.x - w : op.x;
        const h = op.size || 10;
        const y1 = op.baseline === 'top' ? op.y : op.baseline === 'middle' ? op.y - h / 2 : op.y - h * 0.8;
        if (op.rotate) {
            // the text's box turned about its anchor, as it prints
            const c = Math.cos(op.rotate), s = Math.sin(op.rotate);
            let b = null;
            for (const [px, py] of [[x1, y1], [x1 + w, y1], [x1, y1 + h], [x1 + w, y1 + h]]) {
                const dx = px - op.x, dy = py - op.y;
                const X = op.x + dx * c - dy * s, Y = op.y + dx * s + dy * c;
                b = grow(b, X, Y, X, Y);
            }
            return b;
        }
        return [x1, y1, x1 + w, y1 + h];
    }
    return null;
}

const meets = (a, b) => a && b && Math.min(a[2], b[2]) > Math.max(a[0], b[0]) && Math.min(a[3], b[3]) > Math.max(a[1], b[1]);

// Which sides of the wall a ruler's ops stand on.
function sidesOf(boxes, wall) {
    if (!wall) return null;
    const s = new Set();
    for (const b of boxes) {
        if (b[3] <= wall[1] + 1) s.add('top');
        else if (b[1] >= wall[3] - 1) s.add('bottom');
        else if (b[2] <= wall[0] + 1) s.add('left');
        else if (b[0] >= wall[2] - 1) s.add('right');
    }
    return ['top', 'bottom', 'left', 'right'].filter(x => s.has(x)).join('/') || null;
}

const round = (b) => b.map(v => Math.round(v));

class _BinderOverlays {
    // A painter marks the section it is drawing ("wiring boxes"), up to the
    // next mark or a mark of null: its ops go to that overlay.
    _bInkMark(book, kind, why = null) {
        const L = LEDGER;
        if (!L || L.book !== book) return;
        L.mark = kind ? { kind, why } : null;
        noteSeg(L);
    }

    // A painter says how many of an overlay it drew (otherwise the count is
    // the calls of its painter that put ink down).
    _bInkCount(book, kind, n = 1) {
        const L = LEDGER;
        if (!L || L.book !== book) return;
        L.counts.set(kind, (L.counts.get(kind) || 0) + n);
    }

    // The renderer's pass `fn` onto r.ctx, watched: its ink by overlay, in
    // the bitmap's pixels, held for the canvas until the bitmap is laid.
    _bInkRender(r, fn) {
        const L = LEDGER;
        if (!L || this._binderQuietPass || !r || !r.ctx || !r.canvas) return fn();
        const ctx = r.ctx;
        watchContext(ctx);
        // the pass draws the bitmap afresh: what an earlier pass onto this
        // canvas noted (a probe render) is gone with its pixels
        const held = { items: new Map() };
        L.pending.set(r.canvas, held);
        const stack = [];
        let group = null;
        const item = (kind, why) => {
            let it = held.items.get(kind);
            if (!it) { it = { kind, why: null, n: 0, boxes: [], union: null, explicit: false, text: null }; held.items.set(kind, it); }
            if (why && !it.why) it.why = why;
            else if (why && it.why && !String(it.why).split(', ').includes(String(why))) it.why = `${it.why}, ${why}`;
            return it;
        };
        const sinkTo = (frame) => (x1, y1, x2, y2) => { frame.box = grow(frame.box, x1, y1, x2, y2); };
        const closeGroup = () => {
            if (group && group.box) {
                const it = item(group.kind, null);
                it.n += 1;
                it.boxes.length < MAX_BOXES && it.boxes.push(group.box);
                it.union = grow(it.union, ...group.box);
            }
        };
        const setSink = () => {
            const top = stack.length ? stack[stack.length - 1] : null;
            ctx.__inkSink = top ? sinkTo(top) : (group ? sinkTo(group) : sinkTo(otherFrame));
            ctx.__inkText = top && top.spec.text ? (t) => { if (!top.text) top.text = t; } : null;
        };
        const otherFrame = { kind: 'other ink', box: null };
        const hadGroup = Object.prototype.hasOwnProperty.call(ctx, '__lrdGroup');
        const oldGroup = ctx.__lrdGroup;
        ctx.__lrdGroup = (name) => {
            closeGroup();
            const kind = GROUP_KINDS[name];
            group = kind ? { kind, box: null } : null;
            setSink();
        };
        const owned = new Map();
        const wrapMethod = (name, spec) => {
            const real = r[name];
            if (typeof real !== 'function') return;
            owned.set(name, Object.getOwnPropertyDescriptor(r, name) || null);
            r[name] = function (...args) {
                const kind = typeof spec.kind === 'function' ? spec.kind(r, args) : spec.kind;
                const frame = { kind, spec, args, box: null, labels: {}, text: null };
                stack.push(frame);
                setSink();
                try {
                    return real.apply(this, args);
                } finally {
                    stack.pop();
                    setSink();
                    let why = null;
                    try { why = typeof spec.why === 'function' ? spec.why(r, args) : spec.why; } catch (e) { why = null; }
                    // how many it drew: what its count says, else one a call
                    // that put ink down (a run with no disc is still a run)
                    let n = 1;
                    if (typeof spec.count === 'function') {
                        try { n = spec.count(r, args) || 1; } catch (e) { n = 1; }
                    } else if (typeof spec.count === 'string' && spec.count.startsWith('label:')) {
                        n = frame.labels[spec.count.slice(6)] || 1;
                    }
                    if (frame.box) {
                        const it = item(kind, why);
                        it.n += n;
                        it.boxes.length < MAX_BOXES && it.boxes.push(frame.box);
                        it.union = grow(it.union, ...frame.box);
                        if (frame.text && !it.text) it.text = frame.text;
                    }
                    // the label registry's own things inside it (leg ticks)
                    for (const [lk, spec2] of Object.entries(LABEL_ENTRIES)) {
                        const lab = frame.labelBoxes && frame.labelBoxes[lk];
                        if (lab && lab.length) {
                            const it = item(spec2.kind, spec2.why);
                            it.n += lab.length;
                            it.explicit = true;
                            for (const b of lab) {
                                it.boxes.length < MAX_BOXES && it.boxes.push(b);
                                it.union = grow(it.union, ...b);
                            }
                        }
                    }
                }
            };
        };
        for (const [name, spec] of Object.entries(RENDER_OVERLAYS)) wrapMethod(name, spec);
        // the label registry's notes, counted on the overlay drawing them
        const realNote = r._noteLabelBox;
        const hadNote = Object.prototype.hasOwnProperty.call(r, '_noteLabelBox');
        if (typeof realNote === 'function') {
            r._noteLabelBox = function (kind, text, x, y, w, h, extra) {
                const top = stack.length ? stack[stack.length - 1] : null;
                if (top) {
                    top.labels[kind] = (top.labels[kind] || 0) + 1;
                    if (LABEL_ENTRIES[kind]) {
                        let m = null;
                        try { m = r.ctx.getTransform(); } catch (e) { m = null; }
                        if (m) {
                            const b = hull(m, [x, y, x + w, y, x, y + h, x + w, y + h]);
                            ((top.labelBoxes || (top.labelBoxes = {}))[kind] || (top.labelBoxes[kind] = [])).push(b);
                        }
                    }
                }
                return realNote.call(this, kind, text, x, y, w, h, extra);
            };
        }
        setSink();
        try {
            return fn();
        } finally {
            closeGroup();
            if (otherFrame.box) {
                const it = item('other ink', 'not put down to any painter');
                it.n += 1;
                it.boxes.push(otherFrame.box);
                it.union = grow(it.union, ...otherFrame.box);
            }
            ctx.__inkSink = null;
            ctx.__inkText = null;
            if (hadGroup) ctx.__lrdGroup = oldGroup; else delete ctx.__lrdGroup;
            for (const [name, desc] of owned) {
                if (desc) Object.defineProperty(r, name, desc); else delete r[name];
            }
            if (typeof realNote === 'function') {
                if (hadNote) r._noteLabelBox = realNote; else delete r._noteLabelBox;
            }
        }
    }

    // The bitmap of `canvas` laid on the sheet at `rect` ([x, y, w, h]):
    // its held ink comes onto the ledger in sheet units.
    _bInkLaid(canvas, rect) {
        const L = LEDGER;
        if (!L || !canvas || !rect) return;
        L.mapLaid = true;
        const [rx, ry, rw, rh] = rect;
        L.maps.push([rx, ry, rx + rw, ry + rh]);
        const held = L.pending.get(canvas);
        L.pending.delete(canvas);
        if (!held) return;
        const sx = rw / Math.max(1, canvas.width), sy = rh / Math.max(1, canvas.height);
        const toSheet = (b) => [rx + b[0] * sx, ry + b[1] * sy, rx + b[2] * sx, ry + b[3] * sy];
        for (const it of held.items.values()) {
            const e = entry(L, it.kind, it.why);
            e.n += it.n;
            if (it.text && !e.detail) e.detail = it.text;
            for (const b of it.boxes) addBox(e, toSheet(b));
            if (it.union && it.boxes.length >= MAX_BOXES) e.union = grow(e.union, ...toSheet(it.union));
        }
    }

    // The sheet's line, from its ledger: written once the sheet is painted.
    _bInkFinish(L) {
        const page = L.page;
        const ops = page.ops || [];
        // the binder's own ops, by the tag in force when each was written
        const binder = new Map();
        for (let s = 0; s < L.segs.length; s++) {
            const [from, tag] = L.segs[s];
            const to = s + 1 < L.segs.length ? L.segs[s + 1][0] : ops.length;
            for (let i = from; i < to; i++) {
                const b = opBox(ops[i]);
                if (!b) continue;
                if (tag) {
                    let g = binder.get(tag.kind);
                    if (!g) binder.set(tag.kind, g = { tag, boxes: [], calls: new Set() });
                    g.boxes.push(b);
                    if (tag.call) g.calls.add(tag.call);
                } else if (L.maps.some(m => meets(m, b))) {
                    let g = binder.get('other ink on the map');
                    if (!g) binder.set('other ink on the map', g = { tag: { kind: 'other ink on the map', why: 'not put down to any painter' }, boxes: [], calls: new Set() });
                    g.boxes.push(b);
                }
            }
        }
        const wall = (L.wall && [L.wall.x, L.wall.y, L.wall.x + L.wall.w, L.wall.y + L.wall.h]) || null;
        for (const [kind, g] of binder) {
            if (g.tag.internal) continue;
            const e = entry(L, kind, g.tag.why);
            e.furniture = !!g.tag.furniture;
            e.n += L.counts.has(kind) ? L.counts.get(kind) : Math.max(1, g.calls.size);
            if (g.tag.sides) e.detail = sidesOf(g.boxes, wall) || e.detail;
            for (const b of g.boxes) addBox(e, b);
        }
        // an explicit count with no ink of its own (a count said, nothing drawn) is not drawn
        if (!L.mapLaid && ![...L.entries.values()].some(e => !e.furniture)) return null;
        const list = [...L.entries.values()].filter(e => !e.furniture && e.n > 0);
        const say = (e) => {
            if (e.detail && e.n <= 1 && (e.kind === 'rulers' || e.kind === 'badge')) {
                return `${e.kind} ${e.detail}` + (e.why && e.kind !== 'rulers' ? ` (${e.why})` : '');
            }
            return `${e.kind} ${e.n}` + (e.why ? ` (${e.why})` : '');
        };
        const sheet = `${page.number} ${page.sheetTitle || page.title || ''}`.trim();
        const msg = `Binder ${sheet}: ` + (list.length ? list.map(say).join(', ') : 'no overlays');
        const overlays = list.map(e => ({ kind: e.kind, n: e.n, ...(e.why ? { why: e.why } : {}),
                                          ...(e.detail ? { detail: e.detail } : {}) }));
        const boxes = {};
        for (const e of L.entries.values()) {
            if (!e.boxes.length) continue;
            boxes[e.kind] = { union: round(e.union), at: e.boxes.map(round) };
        }
        const summary = { page: page.number, sheet: page.sheetTitle || page.title || '', kind: page.kind || null,
                          overlays, boxes, msg };
        const book = L.book;
        (book.overlayLog || (book.overlayLog = [])).push(summary);
        sendClientLog('binder_sheet_overlays', { page: summary.page, sheet: summary.sheet, kind: summary.kind, overlays },
                      { level: 'info', area: 'binder', msg });
        sendClientLog('binder_sheet_overlay_boxes', { page: summary.page, sheet: summary.sheet, boxes },
                      { level: 'debug', area: 'binder',
                        msg: `Binder ${sheet}: overlay boxes in sheet units for ${Object.keys(boxes).join(', ') || 'nothing'}` });
        return summary;
    }
}

for (const k of Object.getOwnPropertyNames(_BinderOverlays.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(P, k, Object.getOwnPropertyDescriptor(_BinderOverlays.prototype, k));
    }
}

// ── the hooks: one ledger a painted sheet ──────────────────────────────

const realPage = P._bPage;
P._bPage = function (book, spec, body) {
    return realPage.call(this, book, spec, (page, scaled) => {
        if (!page || !page.painting) return body(page, scaled);
        const outer = LEDGER;
        const L = LEDGER = newLedger(book, page);
        try {
            return body(page, scaled);
        } finally {
            LEDGER = outer;
            try { this._bInkFinish(L); } catch (e) {
                sendClientLog('binder_sheet_overlays_failed', { page: page.number, error: String(e && e.message || e) });
            }
        }
    });
};

// The binder's painters, tagged while they draw.
let callSeq = 0;
for (const [name, spec] of Object.entries(BINDER_OVERLAYS)) {
    const real = P[name];
    if (typeof real !== 'function') continue;
    P[name] = function (...args) {
        const L = LEDGER;
        if (!L) return real.apply(this, args);
        L.stack.push({ kind: spec.kind, why: spec.why || null, furniture: !!spec.furniture,
                       internal: !!spec.internal, sides: !!spec.sides, call: ++callSeq });
        noteSeg(L);
        try {
            if (name === '_bLayMapBitmap') this._bInkLaid(args[1], args[2]);
            return real.apply(this, args);
        } finally {
            L.stack.pop();
            noteSeg(L);
        }
    };
}

// The maps: the renderer's pass onto the map bitmap is watched, and the
// wall's place kept for the rulers' sides.
for (const name of ['_bPaintMap', '_bPaintShowMap']) {
    const real = P[name];
    if (typeof real !== 'function') continue;
    P[name] = function (...args) {
        const L = LEDGER;
        const r = window.canvasRenderer;
        if (!L || !r || !(args[0] && args[0].page && args[0].page.painting)) return real.apply(this, args);
        const had = Object.prototype.hasOwnProperty.call(r, 'render');
        const own = had ? r.render : null;
        const app = this;
        const renderReal = r.render;
        let depth = 0;
        r.render = function (...ra) {
            if (depth > 0) return renderReal.apply(this, ra);
            depth += 1;
            try { return app._bInkRender(r, () => renderReal.apply(this, ra)); } finally { depth -= 1; }
        };
        try {
            const geo = real.apply(this, args);
            if (geo && geo.wall && name === '_bPaintMap') L.wall = geo.wall;
            return geo;
        } finally {
            if (had) r.render = own; else delete r.render;
        }
    };
}
