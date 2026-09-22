// app-export-svg: the SVG export. A view is drawn once through a RECORDING
// context - a stand-in for the export canvas's Context2D that paints AND
// writes down every op with the transform, style, clip and group in force -
// and that record is written out as vectors and real text: cabinets and
// borders as shapes, runs and arrows as paths, every label a <text>, image
// layers embedded, each screen a <g id> with a <g id> per element inside
// it (Panels, Borders, Test pattern, Cabinet IDs, Data, Power, Screen name),
// Images, Text, Background and Back view at the top. Illustrator opens
// <g id> as named groups and every element stays editable; Photoshop places
// the file as a smart object (GitHub #12).
//
// Its own recorder rather than the binder's (_bRecCtx, app-binder.js): that
// one is shaped for the binder's sheets - page units with the sheet scale
// undone, hex colours only, rects, polylines and text, an op shape the PDF
// route (routes_export.py) replays - and the views draw with the whole
// Context2D: arcs and roundRects filled and stroked, clips, gradients,
// globalAlpha, blend modes, a mirror or a rotation in the transform, text
// with any baseline. Teaching the binder's recorder all of that would put
// the PDF contract at risk for nothing the binder needs; the view recorder
// keeps every op in the canvas's own terms (the CTM at the call, styles as
// the context serialises them), which is also what lets the test replay
// the record onto a canvas and compare it with the real render pixel for
// pixel (tests/test_export_svg.py).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';

// A number for an attribute: three decimals, no "-0", no exponent.
function num(v) {
    const r = Math.round((Number(v) || 0) * 1000) / 1000;
    return String(r === 0 ? 0 : r);
}

function escText(s) {
    return String(s)
        // XML 1.0 has no room for control characters
        .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]/g, '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escAttr(s) {
    return escText(s).replace(/"/g, '&quot;');
}

// An XML id from the words a user reads. Letters, digits, '_', '-' and '.'
// stand; anything else is written the way Illustrator writes it in its own
// SVGs (_x20_ for a space), which it turns back into the character on import.
function xmlId(name) {
    let out = '';
    for (const ch of String(name || 'Group')) {
        out += /[A-Za-z0-9_.\-]/.test(ch) ? ch
            : '_x' + ch.codePointAt(0).toString(16).toUpperCase() + '_';
    }
    if (!/^[A-Za-z_]/.test(out)) out = '_' + out;
    return out;
}

// The canvas's colour string as SVG paint: "#rrggbb" stays, "rgba(r, g, b,
// a)" becomes the hex plus an opacity. Chrome serialises fill and stroke
// styles this way (opaque colours as hex, the rest as rgba).
function paintOf(color) {
    const s = String(color == null ? '' : color).trim();
    if (/^#[0-9a-f]{6}$/i.test(s)) return { color: s.toLowerCase(), opacity: 1 };
    if (/^#[0-9a-f]{3}$/i.test(s)) {
        return { color: ('#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]).toLowerCase(), opacity: 1 };
    }
    if (/^#[0-9a-f]{8}$/i.test(s)) {
        return { color: s.slice(0, 7).toLowerCase(), opacity: parseInt(s.slice(7), 16) / 255 };
    }
    const m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(s);
    if (m) {
        const hex = [m[1], m[2], m[3]].map(n => Math.max(0, Math.min(255, Math.round(+n)))
            .toString(16).padStart(2, '0')).join('');
        return { color: '#' + hex, opacity: m[4] === undefined ? 1 : Math.max(0, Math.min(1, +m[4])) };
    }
    return { color: s || '#000000', opacity: 1 };
}

// The canvas font shorthand, as the context serialises it: "[style]
// [variant] [weight] [stretch] size family". Sizes are px there.
function parseFont(font) {
    const s = String(font || '').trim();
    const m = /^(?:(italic|oblique|normal)\s+)?(?:(small-caps|normal)\s+)?(?:(bold|bolder|lighter|normal|\d{3})\s+)?(?:(?:ultra-|extra-|semi-)?(?:condensed|expanded)\s+|normal\s+)?(\d+(?:\.\d+)?)(px|pt)(?:\/[^\s]+)?\s+(.+)$/.exec(s);
    if (!m) return { style: 'normal', weight: 'normal', size: 10, family: 'sans-serif' };
    const size = parseFloat(m[4]) * (m[5] === 'pt' ? 4 / 3 : 1);
    return { style: m[1] || 'normal', variant: m[2] || 'normal', weight: m[3] || 'normal', size, family: m[6] };
}

const BLEND_MODES = new Set(['multiply', 'screen', 'overlay', 'darken', 'lighten',
    'color-dodge', 'color-burn', 'hard-light', 'soft-light', 'difference',
    'exclusion', 'hue', 'saturation', 'color', 'luminosity']);

const IDENTITY = [1, 0, 0, 1, 0, 0];

function sameMatrix(a, b) {
    for (let i = 0; i < 6; i++) if (Math.abs(a[i] - b[i]) > 1e-6) return false;
    return true;
}

function isTranslation(m) {
    return Math.abs(m[0] - 1) < 1e-9 && Math.abs(m[1]) < 1e-9
        && Math.abs(m[2]) < 1e-9 && Math.abs(m[3] - 1) < 1e-9;
}

function applyMatrix(m, x, y) {
    return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

// roundRect's radii the way the canvas normalises them: one number or up to
// four (top-left, top-right, bottom-right, bottom-left), scaled down together
// when they do not fit the box.
function normRadii(radii, w, h) {
    let list = Array.isArray(radii) ? radii : [radii == null ? 0 : radii];
    list = list.map(r => (r && typeof r === 'object') ? Math.max(0, Number(r.x) || 0) : Math.max(0, Number(r) || 0));
    let tl, tr, br, bl;
    if (list.length === 1) tl = tr = br = bl = list[0];
    else if (list.length === 2) { tl = br = list[0]; tr = bl = list[1]; }
    else if (list.length === 3) { tl = list[0]; tr = bl = list[1]; br = list[2]; }
    else [tl, tr, br, bl] = list;
    const aw = Math.abs(w), ah = Math.abs(h);
    const scale = Math.min(1,
        aw / ((tl + tr) || 1e-9), aw / ((bl + br) || 1e-9),
        ah / ((tl + bl) || 1e-9), ah / ((tr + br) || 1e-9));
    if (scale < 1) { tl *= scale; tr *= scale; br *= scale; bl *= scale; }
    return [tl, tr, br, bl];
}

// The canvas arc's sweep, normalised the way the spec does: a whole circle
// where the angles span one or more, otherwise the span within (-2π, 2π).
function arcSpan(a0, a1, ccw) {
    const TAU = Math.PI * 2;
    let d = a1 - a0;
    if (!ccw && d >= TAU) return TAU;
    if (ccw && d <= -TAU) return -TAU;
    d = d % TAU;
    if (!ccw && d < 0) d += TAU;
    if (ccw && d > 0) d -= TAU;
    return d;
}

class _ExportSvg {

    // ---- the recording context ----------------------------------------------

    // A Context2D stand-in over the export canvas's real context `t`: every
    // call and property goes through, so the canvas is painted exactly as
    // it would be, and each drawing op is written to `rec.ops` with the
    // transform (t.getTransform() at the call, so a rotated screen or a
    // mirrored canvas is carried exactly), the clip chain and the current
    // group in force. Path segments keep the matrix they were added under
    // - that is the canvas's own rule: a point joins the path in the space
    // of the moment - and a paint keeps the matrix it was painted under.
    //   { op: 'path', kind: 'fill'|'stroke', segs, m, style, alpha, comp, clips, group, ... }
    //   { op: 'text', kind, text, x, y, maxWidth, m, font, align, baseline, shift, width, style, ... }
    //   { op: 'image', id, x, y, w, h, m, smooth, alpha, comp, clips, group }
    //   { op: 'clear', x, y, w, h, m }
    // Gradients live in rec.gradients (the coordinates and stops handed to
    // the real gradient), clips in rec.clips (their segments), bitmaps in
    // rec.images (a PNG data URL each). `rec.unsupported` names anything
    // the views drew that this cannot write - a test keeps it empty.
    createSvgRecorder(t) {
        const rec = { ops: [], images: {}, gradients: {}, clips: {}, unsupported: [], group: null, ctx: null };
        const imageIds = new Map();     // data URL -> id
        const gradOf = new WeakMap();   // CanvasGradient -> id
        let gradSeq = 0, clipSeq = 0, imageSeq = 0;
        let segs = [];
        let clips = [];
        const clipStack = [];

        const matrix = () => {
            const m = t.getTransform();
            return [m.a, m.b, m.c, m.d, m.e, m.f];
        };
        const styleOf = (v, what) => {
            if (typeof v === 'string') return paintOf(v);
            if (v && gradOf.has(v)) return { gradient: gradOf.get(v) };
            rec.unsupported.push(`${what}: ${v && v.constructor ? v.constructor.name : typeof v}`);
            return { color: '#000000', opacity: 1 };
        };
        const common = () => ({
            m: matrix(),
            alpha: t.globalAlpha,
            comp: t.globalCompositeOperation,
            clips: clips.slice(),
            group: rec.group,
        });
        const strokeBits = () => ({
            width: t.lineWidth,
            cap: t.lineCap,
            join: t.lineJoin,
            miter: t.miterLimit,
            dash: Array.from(t.getLineDash() || []),
            dashOffset: t.lineDashOffset || 0,
        });
        const seg = (s) => { s.m = matrix(); segs.push(s); };
        const paint = (kind, rule) => {
            if (!segs.length) return;
            const op = Object.assign({ op: 'path', kind, segs: segs.slice() }, common());
            if (kind === 'fill') {
                op.style = styleOf(t.fillStyle, 'fillStyle');
                if (rule && rule !== 'nonzero') op.rule = rule;
            } else {
                op.style = styleOf(t.strokeStyle, 'strokeStyle');
                Object.assign(op, strokeBits());
            }
            rec.ops.push(op);
        };
        // Where the alphabetic baseline sits for the baseline in force: the
        // SVG anchors every <text> alphabetically (Illustrator reads no
        // dominant-baseline), so the op carries the shift the browser's own
        // metrics give for this text and font.
        const baselineShift = (text) => {
            const b = t.textBaseline;
            if (b === 'alphabetic') return 0;
            const here = t.measureText(text);
            t.textBaseline = 'alphabetic';
            const alpha = t.measureText(text);
            t.textBaseline = b;
            const shift = (alpha.actualBoundingBoxAscent || 0) - (here.actualBoundingBoxAscent || 0);
            return Number.isFinite(shift) ? shift : 0;
        };
        const textOp = (kind, text, x, y, maxWidth) => {
            const s = String(text);
            const mt = t.measureText(s);
            const op = Object.assign({
                op: 'text', kind, text: s, x, y,
                maxWidth: maxWidth === undefined ? null : maxWidth,
                font: t.font, align: t.textAlign || 'start', baseline: t.textBaseline || 'alphabetic',
                width: mt.width, shift: baselineShift(s),
                // the ink's box about the anchor, for the writer's clip test
                box: { left: mt.actualBoundingBoxLeft || 0, right: mt.actualBoundingBoxRight || 0,
                       asc: mt.actualBoundingBoxAscent || 0, desc: mt.actualBoundingBoxDescent || 0 },
            }, common());
            if (kind === 'fill') op.style = styleOf(t.fillStyle, 'fillStyle');
            else { op.style = styleOf(t.strokeStyle, 'strokeStyle'); Object.assign(op, strokeBits()); }
            rec.ops.push(op);
        };
        // The bitmap as a PNG data URL - an <img> whose src already is one
        // gives it as is; anything else (a canvas, a cropped source) is
        // copied through a scratch canvas.
        const bitmapOf = (img, sx, sy, sw, sh) => {
            const nw = img.naturalWidth || img.videoWidth || img.width || 0;
            const nh = img.naturalHeight || img.videoHeight || img.height || 0;
            const whole = sx === 0 && sy === 0 && sw === nw && sh === nh;
            if (whole && typeof HTMLImageElement !== 'undefined' && img instanceof HTMLImageElement
                    && /^data:image\/(png|jpeg|jpg|gif|webp);/i.test(img.src)) {
                return img.src;
            }
            const c = document.createElement('canvas');
            c.width = Math.max(1, Math.ceil(sw));
            c.height = Math.max(1, Math.ceil(sh));
            c.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
            return c.toDataURL('image/png');
        };
        const wrapGradient = (g, record) => {
            if (!g) return g;
            const id = `gradient${++gradSeq}`;
            record.stops = [];
            rec.gradients[id] = record;
            gradOf.set(g, id);
            const add = CanvasGradient.prototype.addColorStop;
            g.addColorStop = function (offset, color) {
                record.stops.push({ offset: Math.max(0, Math.min(1, Number(offset) || 0)), color: String(color) });
                return add.call(this, offset, color);
            };
            return g;
        };

        const methods = {
            __lrdGroup(name, layer) {
                if (!name) { rec.group = null; return; }
                if (!layer) { rec.group = [String(name)]; return; }
                const type = layer.type || 'screen';
                const layerName = String(layer.name || `${type} ${layer.id}`);
                rec.group = (type === 'image' || type === 'text') ? [String(name), layerName] : [layerName, String(name)];
            },
            save() { clipStack.push(clips.slice()); return t.save(); },
            restore() { if (clipStack.length) clips = clipStack.pop(); return t.restore(); },
            beginPath() { segs = []; return t.beginPath(); },
            moveTo(x, y) { seg({ t: 'M', x, y }); return t.moveTo(x, y); },
            lineTo(x, y) { seg({ t: 'L', x, y }); return t.lineTo(x, y); },
            closePath() { seg({ t: 'Z' }); return t.closePath(); },
            quadraticCurveTo(cx, cy, x, y) { seg({ t: 'Q', cx, cy, x, y }); return t.quadraticCurveTo(cx, cy, x, y); },
            bezierCurveTo(c1x, c1y, c2x, c2y, x, y) {
                seg({ t: 'C', c1x, c1y, c2x, c2y, x, y });
                return t.bezierCurveTo(c1x, c1y, c2x, c2y, x, y);
            },
            arc(x, y, r, a0, a1, ccw) {
                seg({ t: 'A', x, y, r, a0, a1, ccw: !!ccw });
                return t.arc(x, y, r, a0, a1, ccw);
            },
            arcTo(...args) { rec.unsupported.push('arcTo'); return t.arcTo(...args); },
            ellipse(...args) { rec.unsupported.push('ellipse'); return t.ellipse(...args); },
            rect(x, y, w, h) { seg({ t: 'R', x, y, w, h }); return t.rect(x, y, w, h); },
            roundRect(x, y, w, h, radii) {
                seg({ t: 'RR', x, y, w, h, radii: normRadii(radii, w, h) });
                return t.roundRect(x, y, w, h, radii);
            },
            fill(...args) {
                const rule = typeof args[0] === 'string' ? args[0] : (args[1] || 'nonzero');
                if (args[0] && typeof args[0] === 'object') rec.unsupported.push('fill(Path2D)');
                paint('fill', rule);
                return t.fill(...args);
            },
            stroke(...args) {
                if (args[0] && typeof args[0] === 'object') rec.unsupported.push('stroke(Path2D)');
                paint('stroke');
                return t.stroke(...args);
            },
            clip(...args) {
                const rule = typeof args[0] === 'string' ? args[0] : (args[1] || 'nonzero');
                if (args[0] && typeof args[0] === 'object') rec.unsupported.push('clip(Path2D)');
                const id = `clip${++clipSeq}`;
                rec.clips[id] = { segs: segs.slice(), rule: rule === 'evenodd' ? 'evenodd' : 'nonzero' };
                clips = clips.concat(id);
                return t.clip(...args);
            },
            fillRect(x, y, w, h) {
                const op = Object.assign({ op: 'path', kind: 'fill', segs: [{ t: 'R', x, y, w, h, m: matrix() }] }, common());
                op.style = styleOf(t.fillStyle, 'fillStyle');
                rec.ops.push(op);
                return t.fillRect(x, y, w, h);
            },
            strokeRect(x, y, w, h) {
                const op = Object.assign({ op: 'path', kind: 'stroke', segs: [{ t: 'R', x, y, w, h, m: matrix() }] }, common());
                op.style = styleOf(t.strokeStyle, 'strokeStyle');
                Object.assign(op, strokeBits());
                rec.ops.push(op);
                return t.strokeRect(x, y, w, h);
            },
            clearRect(x, y, w, h) {
                rec.ops.push({ op: 'clear', x, y, w, h, m: matrix(), group: rec.group });
                return t.clearRect(x, y, w, h);
            },
            fillText(text, x, y, maxWidth) {
                textOp('fill', text, x, y, maxWidth);
                return maxWidth === undefined ? t.fillText(text, x, y) : t.fillText(text, x, y, maxWidth);
            },
            strokeText(text, x, y, maxWidth) {
                textOp('stroke', text, x, y, maxWidth);
                return maxWidth === undefined ? t.strokeText(text, x, y) : t.strokeText(text, x, y, maxWidth);
            },
            drawImage(img, ...args) {
                let sx = 0, sy = 0, sw, sh, dx, dy, dw, dh;
                const nw = img.naturalWidth || img.videoWidth || img.width || 0;
                const nh = img.naturalHeight || img.videoHeight || img.height || 0;
                if (args.length >= 8) [sx, sy, sw, sh, dx, dy, dw, dh] = args;
                else if (args.length >= 4) { [dx, dy, dw, dh] = args; sw = nw; sh = nh; }
                else { [dx, dy] = args; sw = nw; sh = nh; dw = nw; dh = nh; }
                let data = null;
                try { data = bitmapOf(img, sx, sy, sw, sh); } catch (e) { data = null; }
                if (data) {
                    let id = imageIds.get(data);
                    if (!id) { id = `image${++imageSeq}`; imageIds.set(data, id); rec.images[id] = data; }
                    rec.ops.push(Object.assign({ op: 'image', id, x: dx, y: dy, w: dw, h: dh,
                                                 smooth: !!t.imageSmoothingEnabled }, common()));
                } else {
                    rec.unsupported.push('drawImage: source could not be read');
                }
                return t.drawImage(img, ...args);
            },
            createLinearGradient(x0, y0, x1, y1) {
                return wrapGradient(t.createLinearGradient(x0, y0, x1, y1), { type: 'linear', x0, y0, x1, y1 });
            },
            createRadialGradient(x0, y0, r0, x1, y1, r1) {
                return wrapGradient(t.createRadialGradient(x0, y0, r0, x1, y1, r1), { type: 'radial', x0, y0, r0, x1, y1, r1 });
            },
            createConicGradient(...args) { rec.unsupported.push('createConicGradient'); return t.createConicGradient(...args); },
            createPattern(...args) { rec.unsupported.push('createPattern'); return t.createPattern(...args); },
            putImageData(...args) { rec.unsupported.push('putImageData'); return t.putImageData(...args); },
            reset() { segs = []; clips = []; clipStack.length = 0; return t.reset(); },
        };
        rec.ctx = new Proxy(t, {
            get(target, k) {
                if (Object.prototype.hasOwnProperty.call(methods, k)) return methods[k];
                const v = target[k];
                return typeof v === 'function' ? v.bind(target) : v;
            },
            set(target, k, v) { target[k] = v; return true; },
        });
        // Start a fresh record for the next view (the same context is
        // reused across the export's views).
        rec.begin = () => {
            rec.ops = []; rec.images = {}; rec.gradients = {}; rec.clips = {}; rec.unsupported = [];
            rec.group = null; imageIds.clear(); segs = []; clips = []; clipStack.length = 0;
            gradSeq = 0; clipSeq = 0; imageSeq = 0;
        };
        return rec;
    }

    // ---- the writer -----------------------------------------------------------

    // The record as an SVG document, `width` x `height` px with a matching
    // viewBox. Ops are filed under their group path in the order each group
    // first drew, so the z-order the canvas painted in is the order of the
    // groups and of the ops within each.
    buildSvgFromRecording(rec, width, height, opts) {
        const o = opts || {};
        const ids = new Map();          // XML id -> count, for uniqueness
        const uniqueId = (name) => {
            const base = xmlId(name);
            const n = (ids.get(base) || 0) + 1;
            ids.set(base, n);
            return n === 1 ? base : `${base}_${n}`;
        };
        const defs = [];
        const gradientDefs = new Map();   // key -> id
        const clipDefs = new Map();       // clip id -> def id
        let flattened = 0;

        // Segments to a path `d` in the paint's space. Where every segment
        // shares the paint's matrix, coordinates are local (the element
        // carries the matrix); otherwise the geometry is baked into device
        // space, arcs and rounded corners as short chords.
        const pathD = (segsIn, m, ox, oy) => {
            const local = segsIn.every(s => sameMatrix(s.m, m));
            if (!local) flattened++;
            const pt = (s, x, y) => {
                if (local) return [x + ox, y + oy];
                return applyMatrix(s.m, x, y);
            };
            const parts = [];
            let hasPoint = false;
            const arcCmds = (s, cx, cy, r, a0, span) => {
                // an arc of up to π per command; a full circle as two
                if (local) {
                    const steps = Math.abs(span) > Math.PI + 1e-9 ? 2 : 1;
                    const sweep = span >= 0 ? 1 : 0;
                    let a = a0;
                    for (let i = 0; i < steps; i++) {
                        const b = a + span / steps;
                        const [ex, ey] = pt(s, cx + r * Math.cos(b), cy + r * Math.sin(b));
                        const large = Math.abs(span / steps) > Math.PI ? 1 : 0;
                        parts.push(`A${num(r)} ${num(r)} 0 ${large} ${sweep} ${num(ex)} ${num(ey)}`);
                        a = b;
                    }
                } else {
                    const n = Math.max(2, Math.ceil(Math.abs(span) / (Math.PI / 36)));
                    for (let i = 1; i <= n; i++) {
                        const b = a0 + span * i / n;
                        const [ex, ey] = pt(s, cx + r * Math.cos(b), cy + r * Math.sin(b));
                        parts.push(`L${num(ex)} ${num(ey)}`);
                    }
                }
            };
            for (const s of segsIn) {
                switch (s.t) {
                    case 'M': { const [x, y] = pt(s, s.x, s.y); parts.push(`M${num(x)} ${num(y)}`); hasPoint = true; break; }
                    case 'L': {
                        const [x, y] = pt(s, s.x, s.y);
                        parts.push(`${hasPoint ? 'L' : 'M'}${num(x)} ${num(y)}`); hasPoint = true; break;
                    }
                    case 'Q': {
                        const [cx, cy] = pt(s, s.cx, s.cy); const [x, y] = pt(s, s.x, s.y);
                        if (!hasPoint) parts.push(`M${num(cx)} ${num(cy)}`);
                        parts.push(`Q${num(cx)} ${num(cy)} ${num(x)} ${num(y)}`); hasPoint = true; break;
                    }
                    case 'C': {
                        const [ax, ay] = pt(s, s.c1x, s.c1y); const [bx, by] = pt(s, s.c2x, s.c2y); const [x, y] = pt(s, s.x, s.y);
                        if (!hasPoint) parts.push(`M${num(ax)} ${num(ay)}`);
                        parts.push(`C${num(ax)} ${num(ay)} ${num(bx)} ${num(by)} ${num(x)} ${num(y)}`); hasPoint = true; break;
                    }
                    case 'Z': parts.push('Z'); break;
                    case 'A': {
                        const span = arcSpan(s.a0, s.a1, s.ccw);
                        const [sx, sy] = pt(s, s.x + s.r * Math.cos(s.a0), s.y + s.r * Math.sin(s.a0));
                        parts.push(`${hasPoint ? 'L' : 'M'}${num(sx)} ${num(sy)}`);
                        if (s.r > 0 && span !== 0) arcCmds(s, s.x, s.y, s.r, s.a0, span);
                        hasPoint = true; break;
                    }
                    case 'R': {
                        const [x0, y0] = pt(s, s.x, s.y); const [x1, y1] = pt(s, s.x + s.w, s.y);
                        const [x2, y2] = pt(s, s.x + s.w, s.y + s.h); const [x3, y3] = pt(s, s.x, s.y + s.h);
                        parts.push(`M${num(x0)} ${num(y0)}L${num(x1)} ${num(y1)}L${num(x2)} ${num(y2)}L${num(x3)} ${num(y3)}Z`);
                        parts.push(`M${num(x0)} ${num(y0)}`);
                        hasPoint = true; break;
                    }
                    case 'RR': {
                        const [tl, tr, br, bl] = s.radii;
                        const x = s.x, y = s.y, w = s.w, h = s.h;
                        const corner = (cx, cy, r, a0) => arcCmds(s, cx, cy, r, a0, Math.PI / 2);
                        const p0 = pt(s, x + tl, y);
                        parts.push(`M${num(p0[0])} ${num(p0[1])}`);
                        const p1 = pt(s, x + w - tr, y); parts.push(`L${num(p1[0])} ${num(p1[1])}`);
                        if (tr > 0) corner(x + w - tr, y + tr, tr, -Math.PI / 2);
                        const p2 = pt(s, x + w, y + h - br); parts.push(`L${num(p2[0])} ${num(p2[1])}`);
                        if (br > 0) corner(x + w - br, y + h - br, br, 0);
                        const p3 = pt(s, x + bl, y + h); parts.push(`L${num(p3[0])} ${num(p3[1])}`);
                        if (bl > 0) corner(x + bl, y + h - bl, bl, Math.PI / 2);
                        const p4 = pt(s, x, y + tl); parts.push(`L${num(p4[0])} ${num(p4[1])}`);
                        if (tl > 0) corner(x + tl, y + tl, tl, Math.PI);
                        parts.push('Z');
                        const p5 = pt(s, x, y); parts.push(`M${num(p5[0])} ${num(p5[1])}`);
                        hasPoint = true; break;
                    }
                    default: break;
                }
            }
            return { d: parts.join(''), local };
        };

        // The op's placement: a translation folds into its coordinates, any
        // other matrix rides on the element as a transform.
        const placement = (m) => {
            if (isTranslation(m)) return { ox: m[4], oy: m[5], transform: '' };
            return { ox: 0, oy: 0, transform: ` transform="matrix(${m.map(num).join(' ')})"` };
        };
        const gradientRef = (gid, ox, oy) => {
            const key = `${gid}@${num(ox)},${num(oy)}`;
            if (gradientDefs.has(key)) return gradientDefs.get(key);
            const g = rec.gradients[gid];
            const id = uniqueId(gid);
            gradientDefs.set(key, id);
            if (!g) return id;
            const stops = g.stops.map(s => {
                const p = paintOf(s.color);
                return `<stop offset="${num(s.offset)}" stop-color="${p.color}"${p.opacity < 1 ? ` stop-opacity="${num(p.opacity)}"` : ''}/>`;
            }).join('');
            if (g.type === 'linear') {
                defs.push(`<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${num(g.x0 + ox)}" y1="${num(g.y0 + oy)}" x2="${num(g.x1 + ox)}" y2="${num(g.y1 + oy)}">${stops}</linearGradient>`);
            } else {
                defs.push(`<radialGradient id="${id}" gradientUnits="userSpaceOnUse" cx="${num(g.x1 + ox)}" cy="${num(g.y1 + oy)}" r="${num(g.r1)}" fx="${num(g.x0 + ox)}" fy="${num(g.y0 + oy)}" fr="${num(g.r0)}">${stops}</radialGradient>`);
            }
            return id;
        };
        const paintAttrs = (style, prop, ox, oy) => {
            if (style.gradient) return ` ${prop}="url(#${gradientRef(style.gradient, ox, oy)})"`;
            let a = ` ${prop}="${escAttr(style.color)}"`;
            if (style.opacity < 1) a += ` ${prop}-opacity="${num(style.opacity)}"`;
            return a;
        };
        const commonAttrs = (op) => {
            let a = '';
            if (op.alpha < 1) a += ` opacity="${num(op.alpha)}"`;
            if (op.comp && op.comp !== 'source-over') {
                if (BLEND_MODES.has(op.comp)) a += ` style="mix-blend-mode:${op.comp}"`;
                else rec.unsupported.push(`globalCompositeOperation: ${op.comp}`);
            }
            return a;
        };
        const strokeAttrs = (op) => {
            let a = ` stroke-width="${num(op.width)}"`;
            if (op.cap && op.cap !== 'butt') a += ` stroke-linecap="${op.cap}"`;
            if (op.join && op.join !== 'miter') a += ` stroke-linejoin="${op.join}"`;
            else a += ` stroke-miterlimit="${num(op.miter == null ? 10 : op.miter)}"`;
            if (op.dash && op.dash.length) {
                a += ` stroke-dasharray="${op.dash.map(num).join(' ')}"`;
                if (op.dashOffset) a += ` stroke-dashoffset="${num(op.dashOffset)}"`;
            }
            return a;
        };
        // A clip that is one axis-aligned rectangle, as its device-space
        // box - null for any other shape.
        const clipBoxes = new Map();
        const clipBox = (cid) => {
            if (clipBoxes.has(cid)) return clipBoxes.get(cid);
            const c = rec.clips[cid];
            let box = null;
            if (c && c.segs.length === 1 && c.segs[0].t === 'R') {
                const s = c.segs[0], m = s.m;
                const aligned = (Math.abs(m[1]) < 1e-9 && Math.abs(m[2]) < 1e-9)
                    || (Math.abs(m[0]) < 1e-9 && Math.abs(m[3]) < 1e-9);
                if (aligned) box = bboxOf([[s.x, s.y], [s.x + s.w, s.y], [s.x, s.y + s.h], [s.x + s.w, s.y + s.h]].map(p => applyMatrix(m, p[0], p[1])));
            }
            clipBoxes.set(cid, box);
            return box;
        };
        const bboxOf = (pts) => {
            let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
            for (const [x, y] of pts) { x1 = Math.min(x1, x); x2 = Math.max(x2, x); y1 = Math.min(y1, y); y2 = Math.max(y2, y); }
            return { x1, y1, x2, y2 };
        };
        const scaleOf = (m) => Math.max(Math.hypot(m[0], m[1]), Math.hypot(m[2], m[3]));
        // The op's ink, as a device-space box that surely holds it: every
        // path point and control point, a whole circle for an arc, the
        // measured box for text, the stroke's reach added. null = unknown.
        const opBox = (op) => {
            let pts = [];
            let margin = 0;
            if (op.op === 'path') {
                for (const s of op.segs) {
                    const add = (x, y) => pts.push(applyMatrix(s.m, x, y));
                    switch (s.t) {
                        case 'M': case 'L': add(s.x, s.y); break;
                        case 'Q': add(s.cx, s.cy); add(s.x, s.y); break;
                        case 'C': add(s.c1x, s.c1y); add(s.c2x, s.c2y); add(s.x, s.y); break;
                        case 'A': add(s.x - s.r, s.y - s.r); add(s.x + s.r, s.y - s.r); add(s.x - s.r, s.y + s.r); add(s.x + s.r, s.y + s.r); break;
                        case 'R': case 'RR': add(s.x, s.y); add(s.x + s.w, s.y); add(s.x, s.y + s.h); add(s.x + s.w, s.y + s.h); break;
                        default: break;
                    }
                }
                if (op.kind === 'stroke') {
                    const rectsOnly = op.segs.every(s => s.t === 'R' || s.t === 'RR');
                    const miter = (op.join === 'miter' || !op.join) && !rectsOnly ? (op.miter == null ? 10 : op.miter) : 1;
                    margin = (op.width / 2) * Math.max(1, miter) * scaleOf(op.m);
                    if (op.cap === 'square') margin = Math.max(margin, (op.width / Math.SQRT2) * scaleOf(op.m));
                }
            } else if (op.op === 'text') {
                if (!op.box) return null;
                const b = op.box;
                pts = [[op.x - b.left, op.y - b.asc], [op.x + b.right, op.y - b.asc],
                       [op.x - b.left, op.y + b.desc], [op.x + b.right, op.y + b.desc]].map(p => applyMatrix(op.m, p[0], p[1]));
                if (op.kind === 'stroke') margin = (op.width / 2) * (op.miter == null ? 10 : op.miter) * scaleOf(op.m);
            } else if (op.op === 'image') {
                pts = [[op.x, op.y], [op.x + op.w, op.y], [op.x, op.y + op.h], [op.x + op.w, op.y + op.h]].map(p => applyMatrix(op.m, p[0], p[1]));
            } else {
                return null;
            }
            if (!pts.length) return null;
            const b = bboxOf(pts);
            return { x1: b.x1 - margin, y1: b.y1 - margin, x2: b.x2 + margin, y2: b.y2 + margin };
        };
        // The clips an op really needs: a rectangular clip the op's ink
        // lies inside changes nothing and is left off, so a cabinet drawn
        // inside its own clip (renderPanel) is a plain shape in the file.
        const neededClips = (op) => {
            const chain = op.clips || [];
            if (!chain.length) return chain;
            const box = opBox(op);
            if (!box) return chain;
            const EPS = 1e-3;
            return chain.filter(cid => {
                const c = clipBox(cid);
                if (!c) return true;
                return !(box.x1 >= c.x1 - EPS && box.y1 >= c.y1 - EPS && box.x2 <= c.x2 + EPS && box.y2 <= c.y2 + EPS);
            });
        };
        const clipRef = (cid) => {
            if (clipDefs.has(cid)) return clipDefs.get(cid);
            const c = rec.clips[cid];
            const id = uniqueId(cid);
            clipDefs.set(cid, id);
            const m = c.segs.length ? c.segs[0].m : IDENTITY;
            const { d, local } = pathD(c.segs, m, 0, 0);
            const tf = local && !sameMatrix(m, IDENTITY) ? ` transform="matrix(${m.map(num).join(' ')})"` : '';
            defs.push(`<clipPath id="${id}"><path d="${d}"${tf}${c.rule === 'evenodd' ? ' clip-rule="evenodd"' : ''}/></clipPath>`);
            return id;
        };

        const emitOp = (op) => {
            if (op.op === 'clear') return '';
            const { ox, oy, transform } = placement(op.m);
            if (op.op === 'path') {
                const single = op.segs.length === 1 && op.segs[0].t === 'R' && sameMatrix(op.segs[0].m, op.m);
                let geom;
                if (single) {
                    const s = op.segs[0];
                    const x = Math.min(s.x, s.x + s.w), y = Math.min(s.y, s.y + s.h);
                    geom = `<rect x="${num(x + ox)}" y="${num(y + oy)}" width="${num(Math.abs(s.w))}" height="${num(Math.abs(s.h))}"`;
                } else {
                    const { d } = pathD(op.segs, op.m, ox, oy);
                    if (!d) return '';
                    geom = `<path d="${d}"`;
                }
                let attrs = transform;
                if (op.kind === 'fill') {
                    attrs += paintAttrs(op.style, 'fill', ox, oy);
                    if (op.rule === 'evenodd') attrs += ' fill-rule="evenodd"';
                } else {
                    attrs += ' fill="none"' + paintAttrs(op.style, 'stroke', ox, oy) + strokeAttrs(op);
                }
                return `${geom}${attrs}${commonAttrs(op)}/>`;
            }
            if (op.op === 'text') {
                if (!op.text) return '';
                const f = parseFont(op.font);
                let attrs = ` x="${num(op.x + ox)}" y="${num(op.y + op.shift + oy)}"${transform}`;
                attrs += ` font-family="${escAttr(f.family)}" font-size="${num(f.size)}"`;
                if (f.weight !== 'normal') attrs += ` font-weight="${f.weight}"`;
                if (f.style !== 'normal') attrs += ` font-style="${f.style}"`;
                if (f.variant && f.variant !== 'normal') attrs += ` font-variant="${f.variant}"`;
                const anchor = op.align === 'center' ? 'middle' : (op.align === 'right' || op.align === 'end') ? 'end' : '';
                if (anchor) attrs += ` text-anchor="${anchor}"`;
                if (op.maxWidth != null && op.width > op.maxWidth) {
                    attrs += ` textLength="${num(op.maxWidth)}" lengthAdjust="spacingAndGlyphs"`;
                }
                if (op.kind === 'fill') attrs += paintAttrs(op.style, 'fill', ox, oy);
                else attrs += ' fill="none"' + paintAttrs(op.style, 'stroke', ox, oy) + strokeAttrs(op);
                if (/^\s|\s$|\s\s/.test(op.text)) attrs += ' xml:space="preserve"';
                return `<text${attrs}${commonAttrs(op)}>${escText(op.text)}</text>`;
            }
            if (op.op === 'image') {
                const href = rec.images[op.id];
                if (!href) return '';
                const x = Math.min(op.x, op.x + op.w), y = Math.min(op.y, op.y + op.h);
                let attrs = ` x="${num(x + ox)}" y="${num(y + oy)}" width="${num(Math.abs(op.w))}" height="${num(Math.abs(op.h))}"${transform}`;
                attrs += ' preserveAspectRatio="none"';
                if (!op.smooth) attrs += ' image-rendering="pixelated"';
                return `<image${attrs}${commonAttrs(op)} xlink:href="${href}" href="${href}"/>`;
            }
            return '';
        };

        // The group tree: a node per group path, entries (ops and child
        // nodes) in the order they first appeared.
        const root = { name: null, entries: [], children: new Map() };
        for (const op of rec.ops) {
            let node = root;
            for (const name of (op.group || [])) {
                let child = node.children.get(name);
                if (!child) {
                    child = { name, entries: [], children: new Map() };
                    node.children.set(name, child);
                    node.entries.push({ node: child });
                }
                node = child;
            }
            node.entries.push({ op });
        }
        const indent = (n) => '  '.repeat(n);
        const emitNode = (node, depth) => {
            const lines = [];
            let open = [];   // the clip chain wrapped around the entries so far
            const closeTo = (n) => {
                while (open.length > n) { open.pop(); lines.push(`${indent(depth + open.length)}</g>`); }
            };
            for (const e of node.entries) {
                if (e.node) {
                    closeTo(0);
                    const child = e.node;
                    const inner = emitNode(child, depth + 1);
                    if (!inner.length) continue;          // nothing drawn: no group
                    const id = uniqueId(child.name);
                    lines.push(`${indent(depth)}<g id="${id}" data-name="${escAttr(child.name)}">`);
                    lines.push(...inner);
                    lines.push(`${indent(depth)}</g>`);
                    continue;
                }
                const op = e.op;
                if (op.op === 'clear') continue;
                const chain = neededClips(op);
                let keep = 0;
                while (keep < open.length && keep < chain.length && open[keep] === chain[keep]) keep++;
                closeTo(keep);
                while (open.length < chain.length) {
                    const cid = chain[open.length];
                    lines.push(`${indent(depth + open.length)}<g clip-path="url(#${clipRef(cid)})">`);
                    open.push(cid);
                }
                const s = emitOp(op);
                if (s) lines.push(`${indent(depth + open.length)}${s}`);
            }
            closeTo(0);
            return lines;
        };
        const body = emitNode(root, 1);

        const head = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            `<svg xmlns="${SVG_NS}" xmlns:xlink="${XLINK_NS}" width="${num(width)}" height="${num(height)}" viewBox="0 0 ${num(width)} ${num(height)}">`,
        ];
        if (o.title) head.push(`  <title>${escText(o.title)}</title>`);
        head.push(`  <desc>${escText(o.description || 'LED Raster Designer export. Every group is one element of the view; labels are text.')}</desc>`);
        if (defs.length) head.push('  <defs>', ...defs.map(d => '    ' + d), '  </defs>');
        rec.flattenedPaths = flattened;
        return head.concat(body, ['</svg>', '']).join('\n');
    }

    // ---- replay (the recorder's proof) ------------------------------------------

    // Draw a record back onto a real context, op for op, with the matrix,
    // clip chain and styles each op carried. The canvas this paints and the
    // canvas the view was recorded from must match pixel for pixel: that is
    // the test of the recorder (tests/test_export_svg.py), and it is what
    // makes the SVG's geometry trustworthy.
    async replaySvgRecording(rec, ctx) {
        const bitmaps = {};
        await Promise.all(Object.keys(rec.images).map(id => new Promise(resolve => {
            const img = new Image();
            img.onload = () => { bitmaps[id] = img; resolve(); };
            img.onerror = () => resolve();
            img.src = rec.images[id];
        })));
        const setM = (m) => ctx.setTransform(m[0], m[1], m[2], m[3], m[4], m[5]);
        const tracePath = (segs) => {
            ctx.beginPath();
            for (const s of segs) {
                setM(s.m);
                switch (s.t) {
                    case 'M': ctx.moveTo(s.x, s.y); break;
                    case 'L': ctx.lineTo(s.x, s.y); break;
                    case 'Z': ctx.closePath(); break;
                    case 'Q': ctx.quadraticCurveTo(s.cx, s.cy, s.x, s.y); break;
                    case 'C': ctx.bezierCurveTo(s.c1x, s.c1y, s.c2x, s.c2y, s.x, s.y); break;
                    case 'A': ctx.arc(s.x, s.y, s.r, s.a0, s.a1, s.ccw); break;
                    case 'R': ctx.rect(s.x, s.y, s.w, s.h); break;
                    case 'RR': ctx.roundRect(s.x, s.y, s.w, s.h, s.radii); break;
                    default: break;
                }
            }
        };
        const paintStyle = (style) => {
            if (!style) return '#000000';
            if (style.gradient) {
                const g = rec.gradients[style.gradient];
                if (!g) return '#000000';
                const grad = g.type === 'linear'
                    ? ctx.createLinearGradient(g.x0, g.y0, g.x1, g.y1)
                    : ctx.createRadialGradient(g.x0, g.y0, g.r0, g.x1, g.y1, g.r1);
                g.stops.forEach(s => grad.addColorStop(s.offset, s.color));
                return grad;
            }
            return style.opacity < 1
                ? `rgba(${parseInt(style.color.slice(1, 3), 16)}, ${parseInt(style.color.slice(3, 5), 16)}, ${parseInt(style.color.slice(5, 7), 16)}, ${style.opacity})`
                : style.color;
        };
        for (const op of rec.ops) {
            ctx.save();
            for (const cid of (op.clips || [])) {
                const c = rec.clips[cid];
                if (!c) continue;
                tracePath(c.segs);
                ctx.clip(c.rule || 'nonzero');
            }
            if (op.op === 'clear') {
                setM(op.m);
                ctx.clearRect(op.x, op.y, op.w, op.h);
                ctx.restore();
                continue;
            }
            ctx.globalAlpha = op.alpha == null ? 1 : op.alpha;
            ctx.globalCompositeOperation = op.comp || 'source-over';
            if (op.op === 'path') {
                // a lone rect under the paint's own matrix is what fillRect
                // / strokeRect recorded: drawn the same way, so the corner
                // pixels of a fractional rect rasterise as they did
                const rect = op.segs.length === 1 && op.segs[0].t === 'R' && sameMatrix(op.segs[0].m, op.m)
                    ? op.segs[0] : null;
                if (!rect) tracePath(op.segs);
                setM(op.m);
                if (op.kind === 'fill') {
                    ctx.fillStyle = paintStyle(op.style);
                    if (rect) ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
                    else ctx.fill(op.rule || 'nonzero');
                } else {
                    ctx.strokeStyle = paintStyle(op.style);
                    ctx.lineWidth = op.width; ctx.lineCap = op.cap; ctx.lineJoin = op.join;
                    if (op.miter != null) ctx.miterLimit = op.miter;
                    ctx.setLineDash(op.dash || []); ctx.lineDashOffset = op.dashOffset || 0;
                    if (rect) ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
                    else ctx.stroke();
                }
            } else if (op.op === 'text') {
                setM(op.m);
                ctx.font = op.font; ctx.textAlign = op.align; ctx.textBaseline = op.baseline;
                if (op.kind === 'fill') {
                    ctx.fillStyle = paintStyle(op.style);
                    if (op.maxWidth == null) ctx.fillText(op.text, op.x, op.y);
                    else ctx.fillText(op.text, op.x, op.y, op.maxWidth);
                } else {
                    ctx.strokeStyle = paintStyle(op.style);
                    ctx.lineWidth = op.width; ctx.lineCap = op.cap; ctx.lineJoin = op.join;
                    ctx.setLineDash(op.dash || []); ctx.lineDashOffset = op.dashOffset || 0;
                    if (op.maxWidth == null) ctx.strokeText(op.text, op.x, op.y);
                    else ctx.strokeText(op.text, op.x, op.y, op.maxWidth);
                }
            } else if (op.op === 'image') {
                const img = bitmaps[op.id];
                if (img) {
                    setM(op.m);
                    ctx.imageSmoothingEnabled = !!op.smooth;
                    ctx.drawImage(img, op.x, op.y, op.w, op.h);
                }
            }
            ctx.restore();
        }
    }

    // ---- the save --------------------------------------------------------------

    // One .svg per rendered view, through the file paths the PNG takes: one
    // file through the save dialog, several through the folder chooser.
    async downloadAsSvg(projectName, renderedViews) {
        const files = renderedViews
            .filter(v => typeof v.svg === 'string')
            .map(v => ({ filename: `${v.fileBase}.svg`, blob: new Blob([v.svg], { type: 'image/svg+xml' }) }));
        if (!files.length) throw new Error('No SVG was recorded for the export');
        sendClientLog('export_svg', { files: files.length, bytes: files.reduce((n, f) => n + f.blob.size, 0) });
        if (files.length === 1) {
            await this.saveBlobWithPicker(files[0].blob, files[0].filename, 'image/svg+xml');
            return;
        }
        await this.saveMultipleFiles(files);
    }
}

for (const k of Object.getOwnPropertyNames(_ExportSvg.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ExportSvg.prototype, k));
    }
}
