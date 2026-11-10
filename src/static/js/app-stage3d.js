// app-stage3d: the 3D tab. Every screen Show Look shows stands on the stage
// in three dimensions, built from its own cabinets - their physical size in
// mm, blanked cabinets left out, half cabinets at half size - with its Pixel
// Map drawing on the front and plain dark grey behind.
//
// Each screen keeps its place on the layer as `stage3d` (mm, Y up, +Z
// towards the audience; pitch / yaw / roll in degrees; the bend at every
// joint between columns and rows - the server's app.sanitize_stage3d holds
// the shape). X, Y and Z are the middle of the screen's bottom edge (the
// owner's ruling, 2026-11-09): Y is how high the bottom edge stands, so a
// screen on the floor reads 0, and the screen turns about that point, so a
// screen on the floor stays on it. The block says so with `pivot:
// 'bottom'`; a block without it (the first 1.7.0 betas stored the screen's
// centre) is read as the centre and moved to the bottom middle on read
// (s3dResolve), the screen standing exactly where it stood. A screen
// without one stands where its Show Look position puts it, so older files
// open unchanged. Every edit goes through updateLayers
// like any other layer edit: it saves, reaches the other machines on the LAN
// and undoes. The camera, the units and the floor grid are the view's own
// state, saved with the project through PUT /api/project/stage3d and kept out
// of the undo history.
//
// The drawing library (three.js, MIT, static/vendor/three) is imported the
// first time the tab opens, so nothing about start-up changes for anyone who
// never opens it. Everything that edits placement works without it - the
// rotation maths below is plain arithmetic - so the panel still places
// screens where WebGL is not available.
import { LEDRasterApp } from './app-core.js';
import { evaluateMathExpression, sendClientLog } from './helpers.js';

const JOINT_LIMIT = 15;          // degrees, either way, at any joint
export const FT_MM = 304.8;
// X, Y and Z measure the middle of the bottom edge (the block's marker).
export const PIVOT = 'bottom';
const TEX_MAX = 4096;            // a screen's texture, longest side
const TEX_MIN = 1024;            // small screens are drawn up to this
// Up close, the one screen whose texture is coarser than its own pixels is
// drawn again at one texel per pixel (2026-11-09, "pixel level zoom"): at
// most this long a side and this many texels, one screen at a time, with
// no mipmaps (it is only ever seen magnified) - 128 MB of video memory at
// the most for the face and as much for its writing, on top of the
// ordinary textures.
const DETAIL_SIDE = 8192;
const DETAIL_TEXELS = 8192 * 4096;
const DETAIL_AT = 1.5;           // a texel this many page px wide asks for it
const DETAIL_SETTLE_MS = 250;    // after the camera stops
// The near plane follows the camera in: a thousandth of the way to what it
// looks at, never past a quarter of the way to the nearest screen, 0.05 mm
// to 20 mm (the depth buffer is logarithmic, so the far end keeps its
// precision).
const NEAR_MIN = 0.05, NEAR_MAX = 20;
const SYNC_MS = 120;             // edits settle this long before a rebuild
export const DEG = Math.PI / 180;

// ── The placement block ─────────────────────────────────────────────────

function finite(v, fallback) {
    if (typeof v === 'boolean' || v === null || v === undefined || v === '') return fallback;
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
}

function clampJoint(v) {
    const n = finite(v, 0);
    return Math.max(-JOINT_LIMIT, Math.min(JOINT_LIMIT, n));
}

// The client's copy of app.sanitize_stage3d - the same block for the same
// input, so a restore through the server never comes back "repaired".
export function s3dSanitize(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const out = {};
    ['x', 'y', 'z', 'pitch', 'yaw', 'roll'].forEach(k => { out[k] = finite(value[k], 0); });
    if (value.pivot === PIVOT) out.pivot = PIVOT;
    out.curveCol = clampJoint(value.curveCol);
    out.curveRow = clampJoint(value.curveRow);
    ['jointsCol', 'jointsRow'].forEach(k => {
        const raw = value[k];
        const joints = {};
        if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
            Object.keys(raw).forEach(idx => {
                const text = String(idx).trim();
                if (!/^\d+$/.test(text)) return;
                if (finite(raw[idx], null) === null) return;
                joints[String(parseInt(text, 10))] = clampJoint(raw[idx]);
            });
        }
        out[k] = joints;
    });
    return out;
}

function mmPerPx(layer, axis) {
    const px = Number(axis === 'x' ? layer.cabinet_width : layer.cabinet_height) || 128;
    const mm = Number(axis === 'x' ? layer.panel_width_mm : layer.panel_height_mm) || 500;
    return mm / px;
}

// A duplicate or paste is nudged (dx, dy) Show Look pixels from its source;
// a source that has a 3D place hands the copy the same place, nudged the
// same distance in mm (Show Look's down is the stage's down), so the two
// never stand inside each other. Undefined when the source has none - the
// copy is then placed from its own, already nudged, Show Look position.
// `ref` is the screen whose mm per pixel sets the nudge (a group's copy
// nudges every member by the first member's, so the wall keeps its shape).
export function s3dCopyPlacement(layer, dxPx, dyPx, ref = null) {
    if (!layer || (layer.type || 'screen') !== 'screen') return undefined;
    const p = s3dResolve(layer, layer.stage3d);
    if (!p) return undefined;
    const scale = ref || layer;
    p.x = round(p.x + (Number(dxPx) || 0) * mmPerPx(scale, 'x'), 3);
    p.y = round(p.y - (Number(dyPx) || 0) * mmPerPx(scale, 'y'), 3);
    return p;
}

function jointAt(p, axis, j) {
    const table = axis === 'col' ? p.jointsCol : p.jointsRow;
    const own = table ? table[String(j)] : undefined;
    if (finite(own, null) !== null) return clampJoint(own);
    return clampJoint(axis === 'col' ? p.curveCol : p.curveRow);
}

export function wrap180(deg) {
    let d = ((deg + 180) % 360 + 360) % 360 - 180;
    if (d <= -180) d += 360;
    return Math.abs(d) < 1e-9 ? 0 : d;
}

export const round = (v, places) => {
    const f = Math.pow(10, places);
    return Math.round(v * f) / f;
};

// ── Rotation arithmetic (Euler order Y, X, Z: yaw, then pitch, then roll -
// three.js's 'YXZ', which is how the view turns each screen) ──────────────

export function quatFromPlacement(p) {
    const x = finite(p.pitch, 0) * DEG / 2, y = finite(p.yaw, 0) * DEG / 2, z = finite(p.roll, 0) * DEG / 2;
    const c1 = Math.cos(x), c2 = Math.cos(y), c3 = Math.cos(z);
    const s1 = Math.sin(x), s2 = Math.sin(y), s3 = Math.sin(z);
    return [
        s1 * c2 * c3 + c1 * s2 * s3,
        c1 * s2 * c3 - s1 * c2 * s3,
        c1 * c2 * s3 - s1 * s2 * c3,
        c1 * c2 * c3 + s1 * s2 * s3,
    ];
}

export function quatMul(a, b) {
    const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
    return [
        ax * bw + aw * bx + ay * bz - az * by,
        ay * bw + aw * by + az * bx - ax * bz,
        az * bw + aw * bz + ax * by - ay * bx,
        aw * bw - ax * bx - ay * by - az * bz,
    ];
}

export const quatInv = (q) => [-q[0], -q[1], -q[2], q[3]];

export function quatRotate(q, v) {
    const [qx, qy, qz, qw] = q, [vx, vy, vz] = v;
    const tx = 2 * (qy * vz - qz * vy), ty = 2 * (qz * vx - qx * vz), tz = 2 * (qx * vy - qy * vx);
    return [
        vx + qw * tx + qy * tz - qz * ty,
        vy + qw * ty + qz * tx - qx * tz,
        vz + qw * tz + qx * ty - qy * tx,
    ];
}

export function anglesFromQuat(q) {
    const [x, y, z, w] = q;
    const x2 = x + x, y2 = y + y, z2 = z + z;
    const xx = x * x2, xy = x * y2, xz = x * z2, yy = y * y2, yz = y * z2, zz = z * z2;
    const wx = w * x2, wy = w * y2, wz = w * z2;
    const m11 = 1 - (yy + zz), m21 = xy + wz, m31 = xz - wy;
    const m22 = 1 - (xx + zz);
    const m13 = xz + wy, m23 = yz - wx, m33 = 1 - (xx + yy);
    const pitch = Math.asin(-Math.max(-1, Math.min(1, m23)));
    let yaw, roll;
    if (Math.abs(m23) < 0.9999999) {
        yaw = Math.atan2(m13, m33);
        roll = Math.atan2(m21, m22);
    } else {
        yaw = Math.atan2(-m31, m11);
        roll = 0;
    }
    return { pitch: pitch / DEG, yaw: yaw / DEG, roll: roll / DEG };
}

// ── Corners ──────────────────────────────────────────────────────────────

// A screen's corners (the Header/Footer tab's Corners, app-corners.js): a
// bend between two columns or down the middle of one panel, any angle up
// to 90 degrees, Interior or Exterior (owner, 2026-11-09). Stored on the
// layer as riggingCorners, [{ at, angle, side }]: `at` in half steps as
// the Curve's build-from point counts them (3 is the middle of panel 3,
// 3.5 the seam between panels 3 and 4), `angle` in degrees, `side`
// 'interior' (the sides fold toward the audience, like a concave curve)
// or 'exterior' (they fold away). Columns only: a corner never runs
// along a row. The hinge is the panels' front face.
//
// A CORNER'S SEAM CARRIES NO CURVE ANGLE (owner, 2026-11-09: "think of the
// 90 as the edge of a wall, so the 90 itself cannot have an angle on it,
// but the other side of the panel could"): a corner on a seam takes the
// place of whatever angle the Curve or the 3D tab gives that joint; every
// other seam keeps its own, the seams either side of a folded panel too.
// The stored angles are left as they are, so taking the corner off brings
// the joint's own angle back.
//
// THE SIDE AT THE BUILD-FROM POINT STAYS PUT (owner, 2026-11-09): the
// screen stands where it stood without its corners at the Curve's
// build-from point (s3dCornerAnchor), and the rest folds away from it. A
// corner exactly at that point folds both sides evenly.
//
// `bar` (true) marks a corner whose header or footer piece is laid, the
// "Header Bar - Corner" (rigging-math.js cornerPieces); it never changes
// the shape. A show without corners builds as it always did.
export const CORNER_MAX = 90;
export const CORNER_SIDES = ['interior', 'exterior'];

// The corners as they are kept: each `at` a half step from 1 (any panel
// middle or seam; the screen's own width is checked where it is built),
// each angle above 0 and at most 90 to the tenth of a degree, one corner
// per spot (the last one kept), left to right, `bar` only where true.
// Junk is dropped.
export function s3dCleanCorners(raw) {
    const out = new Map();
    for (const c of (Array.isArray(raw) ? raw : [])) {
        if (!c || typeof c !== 'object') continue;
        const at = finite(c.at, null);
        const angle = finite(c.angle, null);
        if (at === null || angle === null) continue;
        if (at < 1 || Math.abs(at * 2 - Math.round(at * 2)) > 1e-9) continue;
        const a = Math.round(Math.min(CORNER_MAX, angle) * 10) / 10;
        if (!(a > 0)) continue;
        const spot = Math.round(at * 2) / 2;
        const kept = { at: spot, angle: a, side: c.side === 'exterior' ? 'exterior' : 'interior' };
        if (c.bar === true) kept.bar = true;
        out.set(spot, kept);
    }
    return [...out.values()].sort((p, q) => p.at - q.at);
}

// Where a screen's corners fold from: the Curve's build-from point when
// its Curve is on ('left', 'right', 'center', or a spot in half panels:
// 3 the middle of panel 3, 3.5 the seam between 3 and 4), else the
// middle, the Curve's own default.
export function s3dCornerAnchor(layer, cols) {
    const c = layer && layer.riggingCurve;
    if (!c || typeof c !== 'object' || c.on !== true) return 'center';
    const from = c.from;
    if (typeof from === 'number' && Number.isFinite(from) && from > 0) {
        const half = Math.round(from * 2) / 2;
        return Math.min(Math.max(half, 0.5), Math.max(1, cols) + 0.5);
    }
    return ['left', 'right', 'center'].includes(from) ? from : 'center';
}

// The seams (0-based joint index j, between columns j + 1 and j + 2) a
// corner on `layer` takes over: { j: corner }.
export function s3dCornerSeams(layer, cols) {
    const out = new Map();
    for (const c of s3dCornersOn(layer, cols)) if (!Number.isInteger(c.at)) out.set(Math.round(c.at - 1.5), c);
    return out;
}

// The corners of `layer` that land on a screen `cols` columns wide: a
// panel middle 1..cols or a seam between two of them.
export function s3dCornersOn(layer, cols) {
    return s3dCleanCorners(layer && layer.riggingCorners)
        .filter(c => (Number.isInteger(c.at) ? c.at <= cols : c.at < cols));
}

// A corner's turn in the column chain's terms: interior positive.
export const s3dCornerTurn = (c) => (c.side === 'exterior' ? -c.angle : c.angle);

// ── Building a screen from its cabinets ──────────────────────────────────

// One chain of rigid segments (the columns across, or the rows down) that
// turns `joints[i]` degrees between segment i and i + 1, re-centred so the
// middle of its length sits at the origin heading straight along the first
// axis - a curve bends about the screen's own centre and never walks off.
// Positive turns towards the second axis (the audience), so both ends of a
// positively curved screen come forward.
function s3dWalk(lengths, joints) {
    const n = lengths.length;
    const raw = [];
    const heads = [];
    let a = 0, b = 0, th = 0;
    for (let i = 0; i < n; i++) {
        raw.push([a, b]);
        heads.push(th);
        a += lengths[i] * Math.cos(th);
        b += lengths[i] * Math.sin(th);
        if (i < n - 1) th += (joints[i] || 0) * DEG;
    }
    return { raw, heads };
}

// Where a chain (its segments' `starts`, `heads` and `lengths`) is `s` mm
// along its length, and which way it heads there: { p, h }. On a joint
// the heading is halfway between the two segments' (an end takes its own
// segment's), so a fold right at `s` turns both sides evenly about it.
function s3dChainPoint(starts, heads, lengths, s) {
    const n = lengths.length;
    if (!n) return { p: [0, 0], h: 0 };
    let acc = 0;
    for (let k = 0; k < n; k++) {
        const end = acc + lengths[k];
        if (s <= end + 1e-6 || k === n - 1) {
            const t = Math.max(0, Math.min(lengths[k], s - acc));
            const p = [starts[k][0] + t * Math.cos(heads[k]), starts[k][1] + t * Math.sin(heads[k])];
            let h = heads[k];
            if (t < 1e-6 && k > 0) h = (heads[k - 1] + heads[k]) / 2;
            else if (lengths[k] - t < 1e-6 && k < n - 1) h = (heads[k] + heads[k + 1]) / 2;
            return { p, h };
        }
        acc = end;
    }
    return { p: [0, 0], h: 0 };
}

// The column chain with corners, held so the point `anchorMm` along it
// stands exactly where it stands on `ref` (the same screen's chain
// without its corners, s3dChain's frame) and heads the same way there:
// the side at the build-from point stays put and the rest folds away.
function s3dChainHeld(lengths, joints, ref, refLengths, anchorMm) {
    const { raw, heads } = s3dWalk(lengths, joints);
    const total = lengths.reduce((s, v) => s + v, 0);
    if (!lengths.length) return { starts: [], heads: [], total: 0 };
    const want = s3dChainPoint(ref.starts, ref.heads, refLengths, anchorMm);
    const have = s3dChainPoint(raw, heads, lengths, anchorMm);
    const dh = want.h - have.h;
    const c = Math.cos(dh), s = Math.sin(dh);
    const starts = raw.map(([x, y]) => {
        const dx = x - have.p[0], dy = y - have.p[1];
        return [dx * c - dy * s + want.p[0], dx * s + dy * c + want.p[1]];
    });
    return { starts, heads: heads.map(h => h + dh), total };
}

function s3dChain(lengths, joints) {
    const n = lengths.length;
    const { raw, heads } = s3dWalk(lengths, joints);
    const total = lengths.reduce((s, v) => s + v, 0);
    if (!n) return { starts: [], heads: [], total: 0 };
    const half = total / 2;
    let acc = 0, k = 0;
    for (k = 0; k < n - 1; k++) {
        if (acc + lengths[k] >= half - 1e-9) break;
        acc += lengths[k];
    }
    const t = half - acc;
    const mid = [raw[k][0] + t * Math.cos(heads[k]), raw[k][1] + t * Math.sin(heads[k])];
    let hm = heads[k];
    if (t < 1e-6 && k > 0) hm = (heads[k - 1] + heads[k]) / 2;
    else if (lengths[k] - t < 1e-6 && k < n - 1) hm = (heads[k] + heads[k + 1]) / 2;
    const c = Math.cos(-hm), s = Math.sin(-hm);
    const starts = raw.map(([x, y]) => {
        const dx = x - mid[0], dy = y - mid[1];
        return [dx * c - dy * s, dx * s + dy * c];
    });
    return { starts, heads: heads.map(h => h - hm), total };
}

// The cabinets of one screen as rigid flat quads in the screen's own frame
// (mm, X right, Y up, the front facing +Z), its origin at the middle of the
// bottom edge - the point stage3d's X, Y and Z place and the screen turns
// about. Pure data: no drawing library, so the debug hook, the tests and the
// OBJ export (app-obj-export.js) read it as it is.
//
// The middle of the bottom edge is on the screen itself: the middle of the
// column chain (half its length along the cabinets, so on a curved wall the
// middle of the curve, not of the chord across it) at the foot of the row
// chain. A screen curved only across keeps it straight under its middle;
// one bent along its rows (an arch, a kick) has it at the foot of the
// bottom row, as bent. `base` is that point in the frame centred on the
// screen (the chains' own middle) - what an old block's centre is moved by.
//
// Columns and rows are the panels' own slots. The column chain bends the
// screen about the upright (a curved wall), the row chain about the
// left-right line (an arch, a ceiling, a kick); a cabinet is placed on its
// row first and the result carried by its column, so a screen curved both
// ways opens small gaps at the corners rather than warping a cabinet.
//
// Corners (s3dCornersOn) bend the column chain too: one on a seam takes
// that joint's angle in place of the curve's; one down the middle of a
// panel splits that column into two halves hinged at its middle, so each
// cabinet of the column is two quads (`fold` 0 and 1), each with its own
// share of the drawing. The chain is then held at the build-from point
// (s3dCornerAnchor) where the same screen without corners stands, so that
// side stays put. `colHeads` is the heading each column starts on;
// `cornerSeams` the joints a corner took over (index -> corner).
export function s3dBuild(layer, placement) {
    const panels = Array.isArray(layer.panels) ? layer.panels : [];
    const mx = mmPerPx(layer, 'x'), my = mmPerPx(layer, 'y');
    const colSpan = new Map(), rowSpan = new Map();
    let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
    for (const p of panels) {
        const x = Number(p.x) || 0, y = Number(p.y) || 0;
        const w = Number(p.width) || 0, h = Number(p.height) || 0;
        bx0 = Math.min(bx0, x); by0 = Math.min(by0, y);
        bx1 = Math.max(bx1, x + w); by1 = Math.max(by1, y + h);
        const c = Number(p.col) || 0, r = Number(p.row) || 0;
        const cs = colSpan.get(c) || [Infinity, -Infinity];
        colSpan.set(c, [Math.min(cs[0], x), Math.max(cs[1], x + w)]);
        const rs = rowSpan.get(r) || [Infinity, -Infinity];
        rowSpan.set(r, [Math.min(rs[0], y), Math.max(rs[1], y + h)]);
    }
    const cols = [...colSpan.keys()].sort((a, b) => a - b);
    const rows = [...rowSpan.keys()].sort((a, b) => a - b);
    const ci = new Map(cols.map((c, i) => [c, i]));
    const ri = new Map(rows.map((r, i) => [r, i]));
    const colLen = cols.map(c => (colSpan.get(c)[1] - colSpan.get(c)[0]) * mx);
    const rowLen = rows.map(r => (rowSpan.get(r)[1] - rowSpan.get(r)[0]) * my);
    const rowJ = rows.slice(0, -1).map((_, j) => jointAt(placement, 'row', j));
    // The corners: a seam's turn in place of its joint's, a panel's own fold.
    const fold = cols.map(() => 0);
    const corners = s3dCornersOn(layer, cols.length);
    const seams = new Map();
    for (const c of corners) {
        if (Number.isInteger(c.at)) fold[c.at - 1] = s3dCornerTurn(c);
        else seams.set(Math.round(c.at - 1.5), c);
    }
    const ownJ = cols.slice(0, -1).map((_, j) => jointAt(placement, 'col', j));
    const colJ = ownJ.map((a, j) => (seams.has(j) ? s3dCornerTurn(seams.get(j)) : a));
    // The column chain's segments: a column, or the two halves of a folded one.
    const segLen = [], segJ = [], colSeg = [];
    colLen.forEach((len, i) => {
        if (i > 0) segJ.push(colJ[i - 1]);
        colSeg.push(segLen.length);
        if (fold[i]) {
            segLen.push(len / 2, len / 2);
            segJ.push(fold[i]);
        } else {
            segLen.push(len);
        }
    });
    let cc;
    if (corners.length) {
        // Held at the build-from point where the straight screen stands.
        const ref = s3dChain(colLen, ownJ);
        const anchor = s3dCornerAnchor(layer, cols.length);
        const cum = [0];
        colLen.forEach(len => cum.push(cum[cum.length - 1] + len));
        const total = cum[cum.length - 1];
        let at = total / 2;
        if (anchor === 'left') at = 0;
        else if (anchor === 'right') at = total;
        else if (typeof anchor === 'number') {
            if (Number.isInteger(anchor)) {
                const k = Math.min(cols.length, Math.max(1, anchor)) - 1;
                at = cum[k] + colLen[k] / 2;
            } else {
                at = cum[Math.min(cols.length, Math.max(0, Math.round(anchor - 0.5)))];
            }
        }
        cc = s3dChainHeld(segLen, segJ, ref, colLen, at);
    } else {
        cc = s3dChain(segLen, segJ);
    }
    const rc = s3dChain(rowLen, rowJ);
    // Where column i folds (mm across it), or null.
    const foldAt = (i) => (fold[i] ? colLen[i] / 2 : null);
    // The chain segment of column i that `u` mm across it lies on, and how
    // far along that segment.
    const segOf = (i, u) => {
        const s = colSeg[i];
        if (s === undefined) return [i, u];
        const f = foldAt(i);
        return f !== null && u > f ? [s + 1, u - f] : [s, u];
    };

    // The foot of the row chain under the middle of the column chain (which
    // the chain puts at the origin, heading straight across, its front +Z).
    let base = [0, 0, 0];
    const lastRow = rowLen.length - 1;
    if (lastRow >= 0) {
        const g = rc.heads[lastRow] || 0, q = rc.starts[lastRow] || [0, 0];
        base = [0, -(q[0] + rowLen[lastRow] * Math.cos(g)), q[1] + rowLen[lastRow] * Math.sin(g)];
    }

    // a point at `u` mm across chain column i and `w` mm down chain row k,
    // from the middle of the bottom edge
    const point = (i, uIn, k, w) => {
        const [s, u] = segOf(i, uIn);
        const h = cc.heads[s] || 0, o = cc.starts[s] || [0, 0];
        const g = rc.heads[k] || 0, q = rc.starts[k] || [0, 0];
        const down = q[0] + w * Math.cos(g);       // along the row chain's first axis (down)
        const fwd = q[1] + w * Math.sin(g);        // towards the audience
        const yy = -down;
        const dX = Math.cos(h), dZ = Math.sin(h);  // the column's across direction
        const nX = -Math.sin(h), nZ = Math.cos(h); // the column's front
        return [o[0] + u * dX + fwd * nX - base[0], yy - base[1], o[1] + u * dZ + fwd * nZ - base[2]];
    };

    const quads = [];
    for (const p of panels) {
        if (p.hidden || p.blank) continue;
        const c = Number(p.col) || 0, r = Number(p.row) || 0;
        const i = ci.get(c), k = ri.get(r);
        const x = Number(p.x) || 0, y = Number(p.y) || 0;
        const w = Number(p.width) || 0, h = Number(p.height) || 0;
        if (!(w > 0 && h > 0)) continue;
        const u0 = (x - colSpan.get(c)[0]) * mx, u1 = u0 + w * mx;
        const w0 = (y - rowSpan.get(r)[0]) * my, w1 = w0 + h * my;
        const piece = (a, b, xa, wa, half) => {
            const q = {
                row: r, col: c, ci: i, ri: k, u0: a, u1: b, w0, w1,
                tl: point(i, a, k, w0), tr: point(i, b, k, w0),
                br: point(i, b, k, w1), bl: point(i, a, k, w1),
                px: [xa, y, wa, h],
            };
            if (half !== undefined) q.fold = half;
            quads.push(q);
        };
        // A cabinet across its column's fold is two quads, hinged there.
        const f = foldAt(i);
        if (f !== null && u0 < f - 1e-6 && u1 > f + 1e-6) {
            const wa = (f - u0) / mx;
            piece(u0, f, x, wa, 0);
            piece(f, u1, x + wa, w - wa, 1);
        } else {
            piece(u0, u1, x, w);
        }
    }
    return {
        quads, point, colLen, rowLen, colJ, rowJ, base, foldAt, cornerSeams: seams,
        colHeads: colSeg.map(s => cc.heads[s] || 0), rowHeads: rc.heads,
        bounds: { x: bx0, y: by0, w: Math.max(1, bx1 - bx0), h: Math.max(1, by1 - by0) },
        widthMm: cc.total, heightMm: rc.total,
    };
}

// The middle of the bottom edge in the frame centred on the screen (see
// s3dBuild): it hangs on the screen's cabinets and its row bends only.
export function s3dBaseOffset(layer, placement) {
    return s3dBuild(layer || {}, s3dSanitize(placement) || {}).base;
}

// `block` as the placement it stands for: X, Y and Z the middle of the
// bottom edge. A block saved before the marker held the screen's centre:
// the centre is moved to the bottom middle by the screen's own turn, so
// every cabinet stands exactly where it stood. Null with no block.
export function s3dResolve(layer, block) {
    const p = s3dSanitize(block);
    if (!p || p.pivot === PIVOT) return p;
    const off = quatRotate(quatFromPlacement(p), s3dBaseOffset(layer, p));
    return { ...p, x: p.x + off[0], y: p.y + off[1], z: p.z + off[2], pivot: PIVOT };
}

// The world corners [tl, tr, br, bl] of every cabinet of `layer` placed by
// `block` (resolved as above), with the cabinet's row and column. Pure: the
// tests hold the stage's own drawing to it.
export function s3dWorldCorners(layer, block) {
    const p = s3dResolve(layer, block);
    if (!p) return [];
    const q = quatFromPlacement(p);
    const at = (c) => { const r = quatRotate(q, c); return [p.x + r[0], p.y + r[1], p.z + r[2]]; };
    return s3dBuild(layer, p).quads.map(k => ({ row: k.row, col: k.col, corners: [k.tl, k.tr, k.br, k.bl].map(at) }));
}

// The point the panel's X, Y and Z show and the screen turns about, from
// the middle of the panels' bottom edge (the stored point), in the
// screen's own frame: the bottom middle of whatever is lowest - the
// footer's foot, `footerMm` down the bottom row as it leans, when there is
// one; the panels' own edge (no offset) when there is none. The stored
// point stays the panels' edge, so a footer added or taken away leaves the
// panels where they stand and moves the zero instead.
export function s3dDatumOffset(layer, placement, footerMm) {
    if (!(footerMm > 0)) return [0, 0, 0];
    const built = s3dBuild(layer || {}, s3dSanitize(placement) || {});
    const g = built.rowHeads[built.rowLen.length - 1] || 0;
    return [0, -footerMm * Math.cos(g), footerMm * Math.sin(g)];
}

// Stored placement -> what the panel shows (the datum), and back.
export function s3dShown(layer, placement, footerMm) {
    const off = quatRotate(quatFromPlacement(placement), s3dDatumOffset(layer, placement, footerMm));
    return { ...placement, x: placement.x + off[0], y: placement.y + off[1], z: placement.z + off[2] };
}
export function s3dStoredFrom(layer, shown, footerMm) {
    const off = quatRotate(quatFromPlacement(shown), s3dDatumOffset(layer, shown, footerMm));
    return { ...shown, x: shown.x - off[0], y: shown.y - off[1], z: shown.z - off[2] };
}

// A length typed in the panel, in mm, or null. A figure with its own unit
// is taken in it whatever the panel shows - 2m, 250 mm, 6'6", 6 ft 6 in, 18
// in - and a plain figure or sum (10+2.5) is in the panel's unit.
const LENGTH_UNITS = { mm: 1, cm: 10, m: 1000, ft: FT_MM, "'": FT_MM, '′': FT_MM, in: 25.4, '"': 25.4, '″': 25.4 };
const LENGTH_PART = /\s*(\d*\.?\d+)\s*(mm|cm|m|ft|in|'|′|"|″)\s*/y;
export function s3dParseLength(raw, units, evaluate = null) {
    const text = String(raw == null ? '' : raw).trim();
    if (text === '') return null;
    // 12' 6 - feet, then inches without their mark
    const ftIn = text.match(/^([-+]?)\s*(\d*\.?\d+)\s*['′]\s*(\d*\.?\d+)$/);
    if (ftIn) return (ftIn[1] === '-' ? -1 : 1) * (parseFloat(ftIn[2]) * FT_MM + parseFloat(ftIn[3]) * 25.4);
    if (/(mm|cm|m|ft|in|'|′|"|″)$/.test(text)) {
        let body = text, sign = 1;
        if (body[0] === '-' || body[0] === '+') { sign = body[0] === '-' ? -1 : 1; body = body.slice(1); }
        let at = 0, total = 0;
        while (at < body.length) {
            LENGTH_PART.lastIndex = at;
            const m = LENGTH_PART.exec(body);
            if (!m) return null;
            total += parseFloat(m[1]) * LENGTH_UNITS[m[2]];
            at = LENGTH_PART.lastIndex;
        }
        return sign * total;
    }
    const v = typeof evaluate === 'function' ? evaluate(text) : Number(text);
    if (!Number.isFinite(v)) return null;
    return v * (units === 'm' ? 1000 : FT_MM);
}

// The Header/Footer tab's bars (header above the wall, footer below it) as
// flat quads in the screen's own frame, one per panel slot they cover,
// built on the same column chain as the cabinets: a bar follows the
// screen's curve and every joint, and leans with the top (or bottom) row.
// A panel of bar is a panel of wall: bars that no longer fit the wall stop
// short of it or run past its last column at the wall's average column
// width, at their true width and never stretched, as the tab draws them;
// a gap in a custom row is a gap here too.
// `slices` (app-rigging riggingStageSlices) are the bars over THIS screen
// in its own panels: across a group's seam each member stands the part of
// a bar over itself, so the two halves meet at the seam. Without them, the
// screen's own bars end to end, as before.
// A bar stands at its real height against the panels, with no gap (the
// owner, 2026-11-09): a header 3.5 in, a footer 6 in, floor to panel, on
// every wall whatever its size.
export const HEADER_BAR_MM = 88.9;
export const FOOTER_BAR_MM = 152.4;
function s3dBarHeight(row) {
    return row === 'footer' ? FOOTER_BAR_MM : HEADER_BAR_MM;
}
function s3dOwnBars(raw) {
    let x = 0;
    return (Array.isArray(raw) ? raw : []).map(Number).filter(v => Number.isInteger(v) && v > 0)
        .map(size => { const b = { start: x, size }; x += size; return b; });
}
// How far the footer stands below the panels: 6 in when the screen has a
// footer row on the stage (its own, or its part of a group's row across
// the seam - the same rows s3dBarRows stands), else 0. A header never
// counts.
export function s3dFooterMm(layer, slices = null) {
    const rows = slices || [{ row: 'footer', bars: s3dOwnBars(layer && layer.riggingFooterBars) }];
    return rows.some(r => r && r.row === 'footer' && (r.bars || []).some(b => Number.isInteger(b.size) && b.size > 0))
        ? FOOTER_BAR_MM : 0;
}
function s3dBarRows(layer, built, slices) {
    const out = [];
    const n = built.colLen.length, last = built.rowLen.length - 1;
    if (!n || last < 0) return out;
    const avg = built.widthMm / n;
    const hHead = s3dBarHeight('header'), hFoot = s3dBarHeight('footer');
    const foot = built.rowLen[last];
    const at = { header: [0, -hHead, 0, hHead], footer: [last, foot, foot + hFoot, hFoot] };
    const rows = slices || [
        { row: 'header', bars: s3dOwnBars(layer.riggingBars), end: true, fits: null },
        { row: 'footer', bars: s3dOwnBars(layer.riggingFooterBars), end: true, fits: null },
    ];
    for (const sl of rows) {
        const [k, wTop, wBot, h] = at[sl.row === 'footer' ? 'footer' : 'header'];
        const bars = (sl.bars || []).filter(b => Number.isInteger(b.size) && b.size > 0);
        // The slots this screen stands: the ones a bar covers on the wall,
        // and past its last column only at the row's own end.
        const covered = new Set();
        for (const b of bars) {
            const hi = sl.end ? b.start + b.size : Math.min(b.start + b.size, n);
            for (let s = Math.max(0, b.start); s < hi; s++) covered.add(s);
        }
        const list = [...covered].sort((a, b) => a - b);
        if (!list.length) continue;
        const from = list[0];
        const span = list[list.length - 1] + 1 - from;
        const quads = [];
        let lengthMm = 0;
        for (const s of list) {
            let i = s, ua = 0, ub = built.colLen[s];
            if (s >= n) {
                i = n - 1;
                ua = built.colLen[n - 1] + (s - n) * avg;
                ub = ua + avg;
            }
            lengthMm += ub - ua;
            // A bar over a folded panel folds with it: two quads, each with
            // its share of the slot (f0..f1) for the drawing.
            const f = built.foldAt ? built.foldAt(i) : null;
            const cuts = f !== null && ua < f - 1e-6 && ub > f + 1e-6 ? [[ua, f], [f, ub]] : [[ua, ub]];
            for (const [a, b] of cuts) {
                quads.push({
                    slot: s, f0: (a - ua) / (ub - ua), f1: (b - ua) / (ub - ua),
                    tl: built.point(i, a, k, wTop), tr: built.point(i, b, k, wTop),
                    br: built.point(i, b, k, wBot), bl: built.point(i, a, k, wBot),
                });
            }
        }
        const slots = list.length;
        const fits = sl.fits == null ? (bars.reduce((a, b) => a + b.size, 0) === n) : !!sl.fits;
        // `corners` marks each corner piece (riggingStageSlices): it is
        // drawn "Corner", and its quads already fold with the panels.
        out.push({ row: sl.row, bars: bars.map(b => b.size), starts: bars.map(b => b.start),
                   corners: bars.map(b => b.corner === true), from, span,
                   slots, wallSlots: n, fits, heightMm: h, lengthMm, quads });
    }
    return out;
}

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

class _Stage3D {
    // ── state and the tab ────────────────────────────────────────────────

    _s3dState() {
        if (!this._s3d) {
            this._s3d = {
                active: false, loading: null, T: null, Orbit: null, failed: '',
                renderer: null, webgl: false, scene: null, root: null, gridGroup: null,
                persp: null, ortho: null, camera: null, controls: null, raycaster: null,
                entries: new Map(), joint: null, epoch: null, cam: null,
                units: 'ft', grid: true, bars: true, timer: null, frame: 0, gridKey: '',
                wired: false, drag: null, down: null, needsFit: false, saveTimer: null,
                orthoHalf: 5000,
                // app-stage3d-nav.js and app-stage3d-handles.js: the gesture
                // under way, a camera glide, the handles and their mode.
                nav: null, glide: null, wheel: null, tool: 'move', handles: null,
                nudge: null, hover: null,
            };
        }
        return this._s3d;
    }

    // The view-tab click (app-wiring _wireViewTabs): the viewport over the
    // canvas and the camera bar in the controls strip while 3D is open.
    _s3dSetActive(on) {
        const st = this._s3dState();
        st.active = !!on;
        const container = document.getElementById('canvas-container');
        if (container) container.classList.toggle('s3d-on', st.active);
        const view = document.getElementById('s3d-view');
        const bar = document.getElementById('s3d-toolbar');
        if (view) view.hidden = !st.active;
        if (bar) bar.hidden = !st.active;
        if (!st.active) {
            // Nudges already made land; a drag under way goes back.
            this._s3dNudgeCommit();
            this._s3dCancelDrag();
            this._s3dEndCameraMove(true);
            return;
        }
        this._s3dWire();
        this._s3dLoad().then(() => {
            this._s3dResize();
            this._s3dSync();
        }, () => {});
        this._s3dSchedule();
    }

    _s3dLoad() {
        const st = this._s3dState();
        if (st.loading) return st.loading;
        st.loading = Promise.all([
            import('three'),
            import('/static/vendor/three/OrbitControls.js'),
        ]).then(([T, orbit]) => {
            st.T = T;
            st.Orbit = orbit.OrbitControls;
            this._s3dBuildStage();
        }).catch((err) => {
            st.failed = 'The 3D view could not load its drawing library. Placement can still be typed in the panel.';
            this._s3dMessage(st.failed);
            sendClientLog('stage3d_load_failed', { error: String((err && err.message) || err) });
            throw err;
        });
        return st.loading;
    }

    _s3dMessage(text) {
        const el = document.getElementById('s3d-message');
        if (!el) return;
        el.textContent = text || '';
        el.hidden = !text;
    }

    _s3dBuildStage() {
        const st = this._s3dState();
        const T = st.T;
        st.scene = new T.Scene();
        st.root = new T.Group();
        st.scene.add(st.root);
        st.scene.add(new T.AmbientLight(0xffffff, 0.8));
        const sun = new T.DirectionalLight(0xffffff, 0.7);
        sun.position.set(0.4, 1, 0.7);
        st.scene.add(sun);
        st.gridGroup = new T.Group();
        st.scene.add(st.gridGroup);
        st.persp = new T.PerspectiveCamera(45, 1, 20, 600000);
        st.ortho = new T.OrthographicCamera(-1, 1, 1, -1, 1, 1200000);
        st.camera = st.persp;
        st.persp.position.set(4000, 4000, 12000);
        st.raycaster = new T.Raycaster();
        const view = document.getElementById('s3d-view');
        try {
            st.renderer = new T.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
            st.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
            st.renderer.outputColorSpace = T.SRGBColorSpace;
            st.renderer.domElement.id = 's3d-canvas';
            if (view) view.insertBefore(st.renderer.domElement, view.firstChild);
            st.webgl = true;
        } catch (err) {
            st.renderer = null;
            st.webgl = false;
            this._s3dMessage('The 3D view needs WebGL, which this browser or its graphics driver does not provide. Placement can still be typed in the panel.');
            sendClientLog('stage3d_no_webgl', { error: String((err && err.message) || err) });
        }
        if (st.renderer) {
            st.controls = new st.Orbit(st.camera, st.renderer.domElement);
            st.controls.enableDamping = false;
            st.controls.screenSpacePanning = true;
            // The mouse, the wheel and the trackpad are the view's own
            // (app-stage3d-nav.js): standard 3D navigation with the middle
            // button, and a left press that never moves the camera. The
            // orbit controls keep touch: one finger orbits, two pinch and pan.
            st.controls.mouseButtons = { LEFT: -1, MIDDLE: -1, RIGHT: -1 };
            st.controls.addEventListener('change', () => this._s3dRequestRender());
            st.controls.addEventListener('end', () => this._s3dSaveCameraSoon());
            this._s3dWireViewport(view);
            if (typeof ResizeObserver === 'function' && view) {
                new ResizeObserver(() => this._s3dResize()).observe(view);
            }
        }
        // Another machine's edit lands as layer_updated (app-core applies it
        // and redraws, which reaches _s3dOnRender); project_updated carries
        // the canvas and processor moves. Either way the stage rebuilds.
        if (this.socket && typeof this.socket.on === 'function') {
            this.socket.on('layer_updated', () => this._s3dSchedule());
            this.socket.on('project_updated', () => this._s3dSchedule());
        }
    }

    // canvas.js render() hands every redraw here while the 3D tab is open:
    // any edit, selection change, undo, load or LAN update ends in one, so
    // this is the one door the stage needs. Debounced.
    _s3dOnRender() {
        this._s3dSchedule();
    }

    _s3dSchedule() {
        const st = this._s3dState();
        if (!st.active || st.timer) return;
        st.timer = setTimeout(() => {
            st.timer = null;
            this._s3dSync();
        }, SYNC_MS);
    }

    // ── which screens, and where ──────────────────────────────────────────

    _s3dIsScreen(layer) {
        return !!layer && (layer.type || 'screen') === 'screen'
            && Array.isArray(layer.panels) && layer.panels.length > 0;
    }

    // A screen's Show Look rectangle in mm on the stage (Show Look's Y
    // turned over so up is up), using the screen's own mm per pixel.
    _s3dShowRect(layer, canvasById) {
        const cid = layer.show_canvas_id || layer.canvas_id || null;
        const canvas = cid ? canvasById.get(cid) : null;
        let wx = 0, wy = 0;
        if (canvas) {
            wx = canvas.show_workspace_x == null ? (Number(canvas.workspace_x) || 0) : (Number(canvas.show_workspace_x) || 0);
            wy = canvas.show_workspace_y == null ? (Number(canvas.workspace_y) || 0) : (Number(canvas.show_workspace_y) || 0);
        }
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of layer.panels || []) {
            const x = Number(p.x) || 0, y = Number(p.y) || 0;
            x0 = Math.min(x0, x); y0 = Math.min(y0, y);
            x1 = Math.max(x1, x + (Number(p.width) || 0)); y1 = Math.max(y1, y + (Number(p.height) || 0));
        }
        if (!Number.isFinite(x0)) { x0 = 0; y0 = 0; x1 = 0; y1 = 0; }
        const procX = Number(layer.offset_x) || 0, procY = Number(layer.offset_y) || 0;
        const showX = layer.showOffsetX != null ? Number(layer.showOffsetX) || 0 : procX;
        const showY = layer.showOffsetY != null ? Number(layer.showOffsetY) || 0 : procY;
        const mx = mmPerPx(layer, 'x'), my = mmPerPx(layer, 'y');
        const left = (wx + x0 + showX - procX) * mx;
        const top = -(wy + y0 + showY - procY) * my;
        const w = (x1 - x0) * mx, h = (y1 - y0) * my;
        return { left, top, w, h, bottom: top - h };
    }

    // The screens on the stage (Show Look's: visible screens whose Show Look
    // canvas is not hidden) and the one figure the defaults share - how far
    // up everything goes so the lowest screen's bottom edge, or its
    // footer's when it has one, is on the floor.
    _s3dLayout() {
        const p = this.project || {};
        const canvases = Array.isArray(p.canvases) ? p.canvases : [];
        const byId = new Map(canvases.filter(c => c && c.id).map(c => [c.id, c]));
        const items = [];
        let floor = Infinity;
        for (const layer of (p.layers || [])) {
            if (!this._s3dIsScreen(layer) || layer.visible === false) continue;
            const cid = layer.show_canvas_id || layer.canvas_id || null;
            const canvas = cid ? byId.get(cid) : null;
            if (canvas && canvas.visible === false) continue;
            const rect = this._s3dShowRect(layer, byId);
            floor = Math.min(floor, rect.bottom - this._s3dFooterMm(layer));
            items.push({ layer, rect });
        }
        return { items, lift: Number.isFinite(floor) ? -floor : 0, byId };
    }

    // Where `layer` stands: its own stage3d (an old centre block moved to
    // the bottom middle, s3dResolve), or - with none - upright and flat at
    // its Show Look position, facing the audience, Z 0: X the middle of its
    // bottom edge, Y that edge's height (0 for the lowest screen, which
    // stands on the floor).
    _s3dPlacementOf(layer, layout) {
        const own = layer ? s3dResolve(layer, layer.stage3d) : null;
        if (own) return own;
        const lay = layout || this._s3dLayout();
        const rect = this._s3dShowRect(layer, lay.byId);
        return {
            x: round(rect.left + rect.w / 2, 3), y: round(rect.bottom + lay.lift, 3), z: 0,
            pitch: 0, yaw: 0, roll: 0, curveCol: 0, curveRow: 0, jointsCol: {}, jointsRow: {}, pivot: PIVOT,
        };
    }

    // 6 in when `layer` stands a footer on the stage, else 0 (s3dFooterMm).
    _s3dFooterMm(layer) {
        let slices = null;
        try {
            slices = typeof this.riggingStageSlices === 'function' ? this.riggingStageSlices(layer) : null;
        } catch (err) { slices = null; }
        return s3dFooterMm(layer, slices);
    }

    // The footer each placed screen of `project` (a history entry's show)
    // stands, by id: _s3dFooterMm read against that show, since a group's
    // footer row depends on its members as they stood then.
    _s3dFootersIn(project) {
        const out = new Map();
        const live = this.project;
        try {
            this.project = project;
            for (const l of (project && project.layers) || []) {
                if (this._s3dIsScreen(l) && l.stage3d) out.set(l.id, this._s3dFooterMm(l));
            }
        } finally {
            this.project = live;
        }
        return out;
    }

    // A FOOTER ADDED TO A SCREEN ALREADY PLACED IN 3D LIFTS ITS PANELS 6 in
    // (owner, 2026-11-09): the footer lands where the panels stood, and Y,
    // which reads the footer's foot, reads what it read before. Taken away,
    // the panels drop back by the same, so Y 0 is the panels' bottom again.
    // A header sits on top and moves nothing; a screen not yet placed
    // follows Show Look already. Run by updateLayers ahead of the history
    // entry: against that entry (the show before this edit), every placed
    // screen whose footer came or went while its place did not is moved,
    // along its own lean, so the point Y measures stays put. A screen whose
    // place the edit set itself is left as the edit put it, so running this
    // twice never lifts twice. Returns the screens it moved, which ride in
    // the edit's PUT and undo step.
    _s3dFollowFooters() {
        const layers = (this.project && this.project.layers) || [];
        const entry = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const before = entry && entry.project;
        if (!before || !Array.isArray(before.layers) || !layers.some(l => l && l.stage3d)) return [];
        const was = new Map(before.layers.map(l => [l.id, l]));
        let feet = null;
        const out = [];
        for (const layer of layers) {
            if (!this._s3dIsScreen(layer) || !layer.stage3d) continue;
            const old = was.get(layer.id);
            if (!old || !old.stage3d) continue;
            const now = s3dResolve(layer, layer.stage3d);
            const prev = s3dResolve(old, old.stage3d);
            if (!now || !prev) continue;
            if (['x', 'y', 'z'].some(k => Math.abs(now[k] - prev[k]) > 1e-6)) continue;
            const footNow = this._s3dFooterMm(layer);
            if (!feet) feet = this._s3dFootersIn(before);
            const footWas = feet.get(layer.id) || 0;
            if (footNow === footWas) continue;
            const shown = s3dShown(old, prev, footWas);
            const next = s3dStoredFrom(layer, { ...now, x: shown.x, y: shown.y, z: shown.z }, footNow);
            layer.stage3d = s3dSanitize({ ...now, x: round(next.x, 3), y: round(next.y, 3), z: round(next.z, 3) });
            out.push(layer);
        }
        if (out.length) {
            sendClientLog('stage3d_footer_follow', { ids: out.map(l => l.id) });
            this._s3dSchedule();
        }
        return out;
    }

    // What the panel shows for `layer` placed at `p` (stored form): X, Y
    // and Z at the bottom middle of whatever is lowest - the footer's foot
    // when there is one (s3dDatumOffset).
    _s3dShownOf(layer, p) {
        return s3dShown(layer, p, this._s3dFooterMm(layer));
    }

    // An edit made in the panel's terms, committed: that point stays where
    // the edit puts it (a turn or a curve leaves it where it was, so a
    // footer on the floor stays on the floor).
    _s3dCommitShown(layer, shown, action) {
        this._s3dCommit(layer, s3dStoredFrom(layer, shown, this._s3dFooterMm(layer)), action);
    }

    // The other screens of `layer`'s group: a group stands, moves and turns
    // as one wall.
    _s3dGroupPeers(layer) {
        const p = this.project || {};
        if (!layer || layer.group_id == null) return [];
        const group = (p.groups || []).find(g => g && g.id === layer.group_id);
        const ids = new Set(group ? (group.layer_ids || []) : []);
        return (p.layers || []).filter(l => l !== layer && ids.has(l.id) && this._s3dIsScreen(l));
    }

    _s3dCurrentScreen() {
        const l = this.currentLayer;
        return (l && (l.type || 'screen') === 'screen') ? l : null;
    }

    _s3dSelectedIds() {
        const ids = new Set();
        if (this.selectedLayerIds instanceof Set && this.selectedLayerIds.size) {
            this.selectedLayerIds.forEach(id => ids.add(id));
        } else if (this.currentLayer) {
            ids.add(this.currentLayer.id);
        }
        return ids;
    }

    // ── committing an edit ────────────────────────────────────────────────

    // `next` is the edited screen's new placement. Its group follows
    // rigidly: every peer is carried by the same move and turn about the
    // edited screen's bottom middle (a peer with no 3D place yet starts from its
    // Show Look one). Curves stay each screen's own. One updateLayers call,
    // one undo step.
    //
    // A locked screen stays where it is, and a group with a locked member
    // counts as locked whole (app-cross-layer-paths.js _layerLocked), so
    // one check covers every peer below: the edit is refused, the screens
    // are named and the panel goes back to its figures.
    _s3dCommit(layer, next, action) {
        if (!layer) return;
        if (this._lockedRefused(layer)) {
            this._s3dRefreshPanel(true);
            return;
        }
        const layout = this._s3dLayout();
        const prev = this._s3dPlacementOf(layer, layout);
        const placed = s3dSanitize(next);
        ['x', 'y', 'z'].forEach(k => { placed[k] = round(placed[k], 3); });
        ['pitch', 'yaw', 'roll'].forEach(k => { placed[k] = round(wrap180(placed[k]), 6); });
        const changed = [layer];
        const turned = placed.pitch !== prev.pitch || placed.yaw !== prev.yaw || placed.roll !== prev.roll;
        const dq = turned ? quatMul(quatFromPlacement(placed), quatInv(quatFromPlacement(prev))) : null;
        for (const peer of this._s3dGroupPeers(layer)) {
            const mp = this._s3dPlacementOf(peer, layout);
            const rel = [mp.x - prev.x, mp.y - prev.y, mp.z - prev.z];
            const moved = dq ? quatRotate(dq, rel) : rel;
            const out = { ...mp, x: round(placed.x + moved[0], 3), y: round(placed.y + moved[1], 3), z: round(placed.z + moved[2], 3) };
            if (dq) {
                const a = anglesFromQuat(quatMul(dq, quatFromPlacement(mp)));
                out.pitch = round(wrap180(a.pitch), 6);
                out.yaw = round(wrap180(a.yaw), 6);
                out.roll = round(wrap180(a.roll), 6);
            }
            peer.stage3d = s3dSanitize(out);
            changed.push(peer);
        }
        layer.stage3d = placed;
        sendClientLog('stage3d_edit', { action, ids: changed.map(l => l.id), placed });
        this.updateLayers(changed, true, action);
        this._s3dSchedule();
        this._s3dRefreshPanel();
    }

    _s3dParseLength(raw) {
        return s3dParseLength(raw, this._s3dUnits(), evaluateMathExpression);
    }

    // Feet to the hundredth, meters to the mm. A hair under zero (a turn
    // rounded to the stored thousandth of a mm) reads 0, never -0.00.
    _s3dFormatLength(mm) {
        const v = Number(mm) || 0;
        const text = this._s3dUnits() === 'm' ? (v / 1000).toFixed(3) : (v / FT_MM).toFixed(2);
        return /^-0\.0+$/.test(text) ? text.slice(1) : text;
    }

    _s3dParseAngle(raw) {
        const text = String(raw == null ? '' : raw).replace(/°/g, '').trim();
        if (text === '') return null;
        const v = evaluateMathExpression(text);
        return Number.isFinite(v) ? v : null;
    }

    // One field of the panel, committed on change (Enter ends the edit and
    // fires it - helpers.js installEnterEndsEdit).
    _s3dCommitField(key) {
        const layer = this._s3dCurrentScreen();
        const el = document.getElementById(`s3d-${key}`);
        if (!layer || !el) return;
        const prev = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        const next = { ...prev, jointsCol: { ...prev.jointsCol }, jointsRow: { ...prev.jointsRow } };
        if (key === 'x' || key === 'y' || key === 'z') {
            const mm = this._s3dParseLength(el.value);
            if (mm === null) { this._s3dRefreshPanel(true); return; }
            next[key] = mm;
            this._s3dCommitShown(layer, next, 'Move Screen (3D)');
        } else if (key === 'pitch' || key === 'yaw' || key === 'roll') {
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) { this._s3dRefreshPanel(true); return; }
            next[key] = deg;
            this._s3dCommitShown(layer, next, 'Rotate Screen (3D)');
        } else if (key === 'curve-col' || key === 'curve-row') {
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) { this._s3dRefreshPanel(true); return; }
            next[key === 'curve-col' ? 'curveCol' : 'curveRow'] = clampJoint(deg);
            this._s3dCommitShown(layer, next, 'Curve Screen (3D)');
        } else if (key === 'joint-angle') {
            const st = this._s3dState();
            const jt = st.joint;
            if (!jt || jt.layerId !== layer.id) return;
            const table = jt.axis === 'col' ? next.jointsCol : next.jointsRow;
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) delete table[String(jt.index)];
            else table[String(jt.index)] = clampJoint(deg);
            this._s3dCommitShown(layer, next, 'Bend Joint (3D)');
        }
    }

    _s3dRotateBy(axis, step) {
        const layer = this._s3dCurrentScreen();
        if (!layer || !['pitch', 'yaw', 'roll'].includes(axis) || !Number.isFinite(step)) return;
        const prev = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        this._s3dCommitShown(layer, { ...prev, [axis]: prev[axis] + step }, 'Rotate Screen (3D)');
    }

    _s3dClearJoint() {
        const layer = this._s3dCurrentScreen();
        const jt = this._s3dState().joint;
        if (!layer || !jt || jt.layerId !== layer.id) return;
        const prev = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        const next = { ...prev, jointsCol: { ...prev.jointsCol }, jointsRow: { ...prev.jointsRow } };
        const table = jt.axis === 'col' ? next.jointsCol : next.jointsRow;
        if (!(String(jt.index) in table)) return;
        delete table[String(jt.index)];
        this._s3dCommitShown(layer, next, 'Bend Joint (3D)');
    }

    _s3dClearAllJoints() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const prev = this._s3dShownOf(layer, this._s3dPlacementOf(layer));
        if (!Object.keys(prev.jointsCol).length && !Object.keys(prev.jointsRow).length) return;
        this._s3dCommitShown(layer, { ...prev, jointsCol: {}, jointsRow: {} }, 'Clear Joint Angles (3D)');
    }

    // Back to the Show Look place: the screen and its group lose their 3D
    // block (null, so the PUT carries the removal - the route drops the key).
    _s3dReset() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const all = this._writableLayers([layer, ...this._s3dGroupPeers(layer)].filter(l => l.stage3d));
        if (!all.length) return;
        all.forEach(l => { l.stage3d = null; });
        this._s3dState().joint = null;
        this.updateLayers(all, true, 'Reset 3D Placement');
        this._s3dSchedule();
        this._s3dRefreshPanel();
    }

    // ── the panel ─────────────────────────────────────────────────────────

    // The 3D panel's own length unit (ft | m beside Position): the show's
    // pick when it made one, else the show's unit (its cable unit) - a new
    // show and an old one start there. Nothing else in the show follows it.
    _s3dUnits() {
        const st = this._s3dState();
        if (st.epoch !== null && st.epoch === (this._projectEpoch || 0)) return st.units;
        return this._s3dShowUnits();
    }

    _s3dShowUnits() {
        const p = this.project || {};
        if (p.stage3dUnits === 'm' || p.stage3dUnits === 'ft') return p.stage3dUnits;
        const unit = typeof this.cableUnit === 'function' ? this.cableUnit() : p.cableUnit;
        return unit === 'm' ? 'm' : 'ft';
    }

    _s3dWire() {
        const st = this._s3dState();
        if (st.wired) return;
        st.wired = true;
        const on = (id, ev, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener(ev, fn);
        };
        ['x', 'y', 'z', 'pitch', 'yaw', 'roll', 'curve-col', 'curve-row', 'joint-angle'].forEach(key => {
            on(`s3d-${key}`, 'change', () => this._s3dCommitField(key));
        });
        document.querySelectorAll('[data-s3d-step]').forEach(btn => {
            btn.addEventListener('click', () => {
                const row = btn.closest('[data-s3d-axis]');
                this._s3dRotateBy(row ? row.dataset.s3dAxis : '', Number(btn.dataset.s3dStep));
            });
        });
        on('s3d-joint-clear', 'click', () => this._s3dClearJoint());
        on('s3d-clear-joints', 'click', () => this._s3dClearAllJoints());
        on('s3d-reset', 'click', () => this._s3dReset());
        document.querySelectorAll('[data-s3d-units]').forEach(btn => {
            btn.addEventListener('click', () => this._s3dSetUnits(btn.dataset.s3dUnits));
        });
        on('s3d-mode-persp', 'click', () => this._s3dSetMode('perspective'));
        on('s3d-mode-ortho', 'click', () => this._s3dSetMode('ortho'));
        document.querySelectorAll('[data-s3d-view]').forEach(btn => {
            btn.addEventListener('click', () => this._s3dPreset(btn.dataset.s3dView));
        });
        on('s3d-fit', 'click', () => this._s3dFit(true, null, { animate: true }));
        on('s3d-home', 'click', () => this._s3dHome());
        on('s3d-tool-move', 'click', () => this._s3dSetTool('move'));
        on('s3d-tool-rotate', 'click', () => this._s3dSetTool('rotate'));
        on('s3d-grid', 'click', () => this._s3dSetGrid(!this._s3dState().grid));
        on('s3d-bars', 'click', () => this._s3dSetBars(!this._s3dState().bars));
    }

    // Values only - the fields are never rebuilt, and the one being typed in
    // is left alone (`force` rewrites it too, after a value it refused).
    _s3dRefreshPanel(force = false) {
        const st = this._s3dState();
        const layer = this._s3dCurrentScreen();
        const units = this._s3dUnits();
        const byId = (id) => document.getElementById(id);
        document.querySelectorAll('[data-s3d-unit]').forEach(el => { el.textContent = units; });
        document.querySelectorAll('[data-s3d-units]').forEach(el => {
            el.classList.toggle('active', el.dataset.s3dUnits === units);
        });
        const persp = byId('s3d-mode-persp'), ortho = byId('s3d-mode-ortho'), grid = byId('s3d-grid');
        const isOrtho = st.camera && st.camera === st.ortho;
        if (persp) persp.classList.toggle('active', !isOrtho);
        if (ortho) ortho.classList.toggle('active', !!isOrtho);
        if (grid) grid.classList.toggle('active', st.grid !== false);
        const bars = byId('s3d-bars');
        if (bars) bars.classList.toggle('active', st.bars !== false);
        const tool = st.tool === 'rotate' ? 'rotate' : 'move';
        const move = byId('s3d-tool-move'), turn = byId('s3d-tool-rotate');
        if (move) move.classList.toggle('active', tool === 'move');
        if (turn) turn.classList.toggle('active', tool === 'rotate');
        const none = byId('s3d-none'), fields = byId('s3d-fields');
        if (none) none.hidden = !!layer;
        if (fields) fields.hidden = !layer;
        if (!layer) return;
        const p = this._s3dPlacementOf(layer);
        const shown = this._s3dShownOf(layer, p);
        const set = (id, value) => {
            const el = byId(id);
            if (!el) return;
            if (!force && document.activeElement === el) return;
            if (el.value !== value) el.value = value;
        };
        const name = byId('s3d-screen-name');
        if (name) name.textContent = layer.name || 'Screen';
        const peers = this._s3dGroupPeers(layer);
        const note = byId('s3d-group-note');
        if (note) {
            const group = peers.length ? (this.project.groups || []).find(g => g && g.id === layer.group_id) : null;
            note.hidden = !group;
            note.textContent = group ? `Moves and turns with its group, ${group.name || 'Group'}. The curve is this screen's own.` : '';
        }
        set('s3d-x', this._s3dFormatLength(shown.x));
        set('s3d-y', this._s3dFormatLength(shown.y));
        set('s3d-z', this._s3dFormatLength(shown.z));
        set('s3d-pitch', String(round(p.pitch, 2)));
        set('s3d-yaw', String(round(p.yaw, 2)));
        set('s3d-roll', String(round(p.roll, 2)));
        set('s3d-curve-col', String(round(p.curveCol, 2)));
        set('s3d-curve-row', String(round(p.curveRow, 2)));
        const counts = this._s3dGridCounts(layer);
        // A corner's seam carries no joint angle (its corner takes its place).
        const cornerSeams = s3dCornerSeams(layer, counts.cols);
        const arc = (axis, n) => {
            let total = 0;
            for (let j = 0; j < n - 1; j++) if (!(axis === 'col' && cornerSeams.has(j))) total += jointAt(p, axis, j);
            const joints = Math.max(0, n - 1);
            const own = Object.keys(axis === 'col' ? p.jointsCol : p.jointsRow).length;
            const corners = axis === 'col' ? cornerSeams.size : 0;
            return `${joints} joint${joints === 1 ? '' : 's'}, ${round(total, 1)}° in all`
                + (own ? ` (${own} set alone)` : '')
                + (corners ? `, ${corners === 1 ? 'a corner' : `${corners} corners`} not counted` : '');
        };
        const arcCol = byId('s3d-arc-col'), arcRow = byId('s3d-arc-row');
        if (arcCol) arcCol.textContent = arc('col', counts.cols);
        if (arcRow) arcRow.textContent = arc('row', counts.rows);
        const jt = st.joint && st.joint.layerId === layer.id ? st.joint : null;
        const label = byId('s3d-joint-label'), input = byId('s3d-joint-angle');
        const atCorner = jt && jt.axis === 'col' ? cornerSeams.get(jt.index) : null;
        if (label) {
            label.textContent = jt
                ? (jt.axis === 'col'
                    ? `Joint between columns ${jt.index + 1} and ${jt.index + 2}.`
                        + (atCorner ? ` It is a ${round(atCorner.angle, 1)}° ${atCorner.side === 'exterior' ? 'Exterior' : 'Interior'} corner, set under Corners on the Header/Footer tab, so it takes no joint angle.` : '')
                    : `Joint between rows ${jt.index + 1} and ${jt.index + 2}.`)
                : 'Click a seam between two columns or two rows of the selected screen to bend that joint alone.';
        }
        if (input) {
            input.disabled = !jt || !!atCorner;
            const table = jt ? (jt.axis === 'col' ? p.jointsCol : p.jointsRow) : null;
            const own = table ? table[String(jt.index)] : undefined;
            input.placeholder = jt ? String(round(jt.axis === 'col' ? p.curveCol : p.curveRow, 2)) : '';
            set('s3d-joint-angle', own === undefined ? '' : String(round(own, 2)));
        }
    }

    _s3dGridCounts(layer) {
        const cols = new Set(), rows = new Set();
        for (const p of (layer && layer.panels) || []) {
            cols.add(Number(p.col) || 0);
            rows.add(Number(p.row) || 0);
        }
        return { cols: cols.size, rows: rows.size };
    }

    // ── the view's own state: camera, units, grid ─────────────────────────

    // A project opened, or a new one started (resetHistory bumps the epoch):
    // its saved camera, units and grid take over. Within one project the
    // view's state is this machine's - an undo that put back an older camera
    // in the project copy is quietly given the current one again.
    _s3dAdoptViewState() {
        const st = this._s3dState();
        const p = this.project || {};
        const epoch = this._projectEpoch || 0;
        if (st.epoch !== epoch) {
            st.epoch = epoch;
            st.units = this._s3dShowUnits();
            st.grid = p.stage3dGrid !== false;
            st.bars = p.stage3dBars !== false;
            st.joint = null;
            st.cam = (p.stage3dCamera && Array.isArray(p.stage3dCamera.position)
                && Array.isArray(p.stage3dCamera.target)) ? JSON.parse(JSON.stringify(p.stage3dCamera)) : null;
            // Applied by the next stage sync, once the library is in.
            st.needsCam = !!st.cam;
            st.needsFit = !st.cam;
            return;
        }
        if (st.cam && JSON.stringify(p.stage3dCamera) !== JSON.stringify(st.cam)) {
            p.stage3dCamera = JSON.parse(JSON.stringify(st.cam));
        }
        if ((p.stage3dUnits === 'm' || p.stage3dUnits === 'ft') && p.stage3dUnits !== st.units) p.stage3dUnits = st.units;
        if (p.stage3dGrid !== undefined && p.stage3dGrid !== st.grid) p.stage3dGrid = st.grid;
        if (p.stage3dBars !== undefined && p.stage3dBars !== st.bars) p.stage3dBars = st.bars;
    }

    _s3dPutView(body) {
        return fetch('/api/project/stage3d', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).catch(() => {});
    }

    _s3dSetUnits(units) {
        if (units !== 'ft' && units !== 'm') return;
        const st = this._s3dState();
        this._s3dAdoptViewState();
        st.units = units;
        if (this.project) this.project.stage3dUnits = units;
        this._s3dPutView({ units });
        this._s3dRefreshPanel(true);
        st.gridKey = '';
        this._s3dSchedule();
    }

    _s3dSetGrid(on) {
        const st = this._s3dState();
        this._s3dAdoptViewState();
        st.grid = !!on;
        if (this.project) this.project.stage3dGrid = st.grid;
        this._s3dPutView({ grid: st.grid });
        st.gridKey = '';
        this._s3dRefreshPanel();
        this._s3dSchedule();
    }

    // The header and footer bars shown or hidden on the stage: view state,
    // saved with the show beside the grid switch, never an undo step.
    _s3dSetBars(on) {
        const st = this._s3dState();
        this._s3dAdoptViewState();
        st.bars = !!on;
        if (this.project) this.project.stage3dBars = st.bars;
        this._s3dPutView({ bars: st.bars });
        for (const e of st.entries.values()) if (e.barGroup) e.barGroup.visible = st.bars;
        this._s3dRefreshPanel();
        this._s3dRequestRender();
    }

    _s3dCameraState() {
        const st = this._s3dState();
        if (!st.camera || !st.controls) return null;
        const r = (v) => round(v, 2);
        const pos = st.camera.position, tgt = st.controls.target;
        return {
            mode: st.camera === st.ortho ? 'ortho' : 'perspective',
            position: [r(pos.x), r(pos.y), r(pos.z)],
            target: [r(tgt.x), r(tgt.y), r(tgt.z)],
            zoom: round(st.camera === st.ortho ? st.ortho.zoom : 1, 4),
        };
    }

    _s3dSaveCameraSoon() {
        const st = this._s3dState();
        if (st.saveTimer) clearTimeout(st.saveTimer);
        st.saveTimer = setTimeout(() => this._s3dSaveCamera(), 400);
    }

    _s3dSaveCamera() {
        const st = this._s3dState();
        st.saveTimer = null;
        const cam = this._s3dCameraState();
        if (!cam) return;
        st.cam = cam;
        if (this.project) this.project.stage3dCamera = JSON.parse(JSON.stringify(cam));
        this._s3dPutView({ camera: cam });
    }

    // A camera move still waiting on its timer, saved now. The guides call
    // this as a step settles, so the show a step leaves holds the camera
    // however fast the step ran (quickstart.js appSettled).
    _s3dFlushCamera() {
        const st = this._s3dState();
        // A camera still gliding to a view lands there first.
        this._s3dEndCameraMove(true);
        if (!st.saveTimer) return;
        clearTimeout(st.saveTimer);
        this._s3dSaveCamera();
    }

    // A camera move still waiting, dropped: the project it belonged to has
    // just been replaced, and it must not land on the one that came back.
    _s3dDropPendingCamera() {
        const st = this._s3dState();
        this._s3dEndCameraMove(false);
        if (st.saveTimer) clearTimeout(st.saveTimer);
        st.saveTimer = null;
    }

    _s3dApplyCamera(cam) {
        const st = this._s3dState();
        if (!st.T || !cam) return;
        this._s3dEndCameraMove(false);
        const ortho = cam.mode === 'ortho';
        const pos = cam.position, tgt = cam.target;
        st.camera = ortho ? st.ortho : st.persp;
        st.camera.position.set(pos[0], pos[1], pos[2]);
        if (st.controls) {
            st.controls.object = st.camera;
            st.controls.target.set(tgt[0], tgt[1], tgt[2]);
        }
        const dist = Math.hypot(pos[0] - tgt[0], pos[1] - tgt[1], pos[2] - tgt[2]) || 10000;
        st.orthoHalf = dist * Math.tan(st.persp.fov * DEG / 2);
        st.ortho.zoom = ortho ? (Number(cam.zoom) > 0 ? Number(cam.zoom) : 1) : 1;
        st.camera.lookAt(tgt[0], tgt[1], tgt[2]);
        this._s3dFrameCameras();
        if (st.controls) st.controls.update();
        this._s3dRefreshPanel();
        this._s3dRequestRender();
    }

    _s3dSetMode(mode) {
        const st = this._s3dState();
        if (!st.T || !st.controls) return;
        const want = mode === 'ortho' ? st.ortho : st.persp;
        if (st.camera === want) return;
        this._s3dEndCameraMove(true);
        const tgt = st.controls.target.clone();
        const from = st.camera.position.clone();
        let dir = from.clone().sub(tgt);
        let dist = dir.length() || 10000;
        if (want === st.ortho) {
            st.orthoHalf = dist * Math.tan(st.persp.fov * DEG / 2);
            st.ortho.zoom = 1;
        } else {
            dist = (st.orthoHalf / Math.tan(st.persp.fov * DEG / 2)) / (st.ortho.zoom || 1);
        }
        dir = dir.normalize().multiplyScalar(dist);
        want.position.copy(tgt).add(dir);
        want.up.copy(st.camera.up);
        st.camera = want;
        st.controls.object = want;
        want.lookAt(tgt);
        this._s3dFrameCameras();
        st.controls.update();
        this._s3dRefreshPanel();
        this._s3dRequestRender();
        this._s3dSaveCameraSoon();
    }

    // Both cameras' projections from the viewport's shape.
    _s3dFrameCameras() {
        const st = this._s3dState();
        const view = document.getElementById('s3d-view');
        const w = (view && view.clientWidth) || 800, h = (view && view.clientHeight) || 600;
        const aspect = w / Math.max(1, h);
        st.persp.aspect = aspect;
        st.persp.updateProjectionMatrix();
        const half = Math.max(100, st.orthoHalf || 5000);
        st.ortho.left = -half * aspect;
        st.ortho.right = half * aspect;
        st.ortho.top = half;
        st.ortho.bottom = -half;
        st.ortho.updateProjectionMatrix();
    }

    _s3dResize() {
        const st = this._s3dState();
        if (!st.renderer) return;
        const view = document.getElementById('s3d-view');
        if (!view || !view.clientWidth || !view.clientHeight) return;
        st.renderer.setSize(view.clientWidth, view.clientHeight, false);
        this._s3dFrameCameras();
        this._s3dRequestRender();
    }

    // Every screen's world box (or only the screens in `ids`), or a 10 m
    // stage round the origin with none.
    _s3dWorldBox(ids = null) {
        const st = this._s3dState();
        const T = st.T;
        const box = new T.Box3();
        st.root.updateMatrixWorld(true);
        for (const e of st.entries.values()) {
            if (ids && !ids.has(e.id)) continue;
            if (e.front && e.front.geometry) box.expandByObject(e.front);
        }
        if (box.isEmpty()) box.set(new T.Vector3(-5000, 0, -5000), new T.Vector3(5000, 3000, 5000));
        return box;
    }

    // Frame every screen (or only `opts.ids`), looking along `dir` (from the
    // target towards the camera) - the current direction when none is given.
    // `opts.animate` glides there (app-stage3d-nav.js _s3dCameraTo); the
    // opening fit and a restored show jump.
    _s3dFit(save = false, dir = null, opts = {}) {
        const st = this._s3dState();
        if (!st.T || !st.controls) {
            if (st.T) st.needsFit = true;
            return;
        }
        const T = st.T;
        this._s3dEndCameraMove(false);
        const box = this._s3dWorldBox(opts.ids || null);
        const centre = box.getCenter(new T.Vector3());
        const radius = Math.max(500, box.getSize(new T.Vector3()).length() / 2);
        let look = dir ? dir.clone() : st.camera.position.clone().sub(st.controls.target);
        if (look.lengthSq() < 1e-6) look = new T.Vector3(0.35, 0.3, 1);
        look.normalize();
        const fov = st.persp.fov * DEG;
        const aspect = st.persp.aspect || 1;
        const fit = radius / Math.sin(Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * aspect)) / 2);
        const pose = {
            target: centre.clone(),
            position: centre.clone().add(look.multiplyScalar(fit * 0.9)),
            orthoHalf: radius * 0.95, zoom: 1,
        };
        st.camera.up.set(0, 1, 0);
        this._s3dCameraTo(pose, { animate: !!opts.animate, save });
    }

    _s3dPreset(name) {
        const st = this._s3dState();
        if (!st.T || !st.controls) return;
        const T = st.T;
        const dirs = {
            front: [0, 0, 1], back: [0, 0, -1], left: [-1, 0, 0], right: [1, 0, 0],
            top: [0, 1, 0.0001], iso: [0.7, 0.55, 0.9],
        };
        const d = dirs[name];
        if (!d) return;
        sendClientLog('stage3d_view', { view: name });
        this._s3dFit(true, new T.Vector3(d[0], d[1], d[2]), { animate: true });
    }

    // ── the stage ─────────────────────────────────────────────────────────

    _s3dTokens() {
        const cs = getComputedStyle(document.documentElement);
        const read = (name, fallback) => (cs.getPropertyValue(name) || '').trim() || fallback;
        return {
            canvas: read('--ps-canvas', '#1b1b1b'),
            accent: read('--ps-accent', '#e22330'),
            minor: read('--ps-tile', '#3c3c3c'),
            major: read('--ps-control-hi', '#545454'),
        };
    }

    _s3dSync() {
        const st = this._s3dState();
        if (!st.active) return;
        if (!st.T) {
            this._s3dRefreshPanel();
            return;
        }
        this._s3dAdoptViewState();
        const layout = this._s3dLayout();
        const seen = new Set();
        for (const item of layout.items) {
            seen.add(item.layer.id);
            this._s3dUpdateEntry(item.layer, this._s3dPlacementOf(item.layer, layout));
        }
        for (const id of [...st.entries.keys()]) {
            if (!seen.has(id)) this._s3dDropEntry(id);
        }
        if (st.joint && !st.entries.has(st.joint.layerId)) st.joint = null;
        const tokens = this._s3dTokens();
        if (st.renderer) st.renderer.setClearColor(tokens.canvas, 1);
        this._s3dHighlight(tokens);
        this._s3dHandlesSync();
        this._s3dGrid(tokens);
        if (st.needsCam) {
            st.needsCam = false;
            this._s3dApplyCamera(st.cam);
        }
        if (st.needsFit && st.controls) {
            st.needsFit = false;
            this._s3dFit(false, new st.T.Vector3(0.35, 0.3, 1));
        }
        this._s3dRefreshPanel();
        this._s3dRequestRender();
    }

    _s3dDropEntry(id) {
        const st = this._s3dState();
        const e = st.entries.get(id);
        if (!e) return;
        st.root.remove(e.obj);
        if (e.geo) e.geo.dispose();
        if (e.lineGeo) e.lineGeo.dispose();
        if (e.labelGeo) e.labelGeo.dispose();
        if (e.tex) e.tex.dispose();
        if (e.labelTex) e.labelTex.dispose();
        if (e.seam) { e.seam.geometry.dispose(); e.seam.material.dispose(); }
        this._s3dDropBars(e);
        [e.frontMat, e.backMat, e.lineMat, e.labelMat].forEach(m => { if (m) m.dispose(); });
        st.entries.delete(id);
    }

    _s3dUpdateEntry(layer, placement) {
        const st = this._s3dState();
        const T = st.T;
        let e = st.entries.get(layer.id);
        if (!e) {
            e = { id: layer.id, obj: new T.Group(), geoKey: '', texKey: '' };
            e.frontMat = new T.MeshBasicMaterial({ color: 0xffffff, side: T.FrontSide });
            e.backMat = new T.MeshLambertMaterial({ color: 0x2c2c2c, side: T.BackSide });
            e.lineMat = new T.LineBasicMaterial({ color: 0x0a0a0a, transparent: true, opacity: 0.9 });
            // The screen's writing (_s3dPaint's label pass) on a sheet of its
            // own over the seams: see _s3dBuildMesh.
            e.labelMat = new T.MeshBasicMaterial({ transparent: true, depthWrite: false, side: T.FrontSide });
            e.obj.userData.layerId = layer.id;
            st.root.add(e.obj);
            st.entries.set(layer.id, e);
        }
        const geoKey = JSON.stringify([
            (layer.panels || []).map(p => [p.row, p.col, p.x, p.y, p.width, p.height, !!p.hidden, !!p.blank]),
            layer.panel_width_mm, layer.panel_height_mm, layer.cabinet_width, layer.cabinet_height,
            placement.curveCol, placement.curveRow, placement.jointsCol, placement.jointsRow,
            s3dCleanCorners(layer.riggingCorners).map(c => [c.at, c.angle, c.side]),
            // where the corners fold from (the Curve's build-from point)
            s3dCornerAnchor(layer, Number(layer.columns) || 1),
        ]);
        if (e.geoKey !== geoKey) {
            e.geoKey = geoKey;
            this._s3dBuildMesh(e, layer, placement);
        }
        // A neighbor's bar across a group's seam stands partly on this
        // screen: the slices (riggingStageSlices) carry it.
        const slices = typeof this.riggingStageSlices === 'function' ? this.riggingStageSlices(layer) : null;
        const barsKey = JSON.stringify([geoKey, slices, layer.riggingBars, layer.riggingFooterBars,
            layer.riggingColor, layer.riggingTextColor]);
        if (e.barsKey !== barsKey) {
            e.barsKey = barsKey;
            this._s3dBuildBars(e, layer, slices);
        }
        if (e.barGroup) e.barGroup.visible = st.bars !== false;
        const texKey = this._s3dTexKey(layer);
        if (e.texKey !== texKey) {
            e.texKey = texKey;
            this._s3dPaint(e, layer);
        }
        e.placement = placement;
        e.footerMm = this._s3dFooterMm(layer);
        e.datumOff = s3dDatumOffset(layer, placement, e.footerMm);
        e.stored = !!s3dSanitize(layer.stage3d);
        e.name = layer.name;
        if (!(st.drag && st.drag.active && st.drag.starts.has(layer.id))) {
            e.obj.position.set(placement.x, placement.y, placement.z);
            e.obj.rotation.set(placement.pitch * DEG, placement.yaw * DEG, placement.roll * DEG, 'YXZ');
        }
    }

    // One BufferGeometry per screen: a quad per cabinet with its UVs on the
    // screen's drawing, shared by the front (the drawing) and the back (dark
    // grey) meshes; the seams are line pairs a hair in front of each face.
    _s3dBuildMesh(e, layer, placement) {
        const st = this._s3dState();
        const T = st.T;
        const built = s3dBuild(layer, placement);
        e.built = built;
        const n = built.quads.length;
        const pos = new Float32Array(n * 12);
        const uv = new Float32Array(n * 8);
        const idx = new Uint32Array(n * 6);
        const lines = new Float32Array(n * 2 * 8 * 3);
        const over = new Float32Array(n * 12);
        const b = built.bounds;
        const off = 2;   // mm, seams off the faces
        const labelOff = 5;   // mm, the writing off the front face
        built.quads.forEach((q, i) => {
            const corners = [q.tl, q.tr, q.br, q.bl];
            corners.forEach((c, k) => pos.set(c, i * 12 + k * 3));
            const [x, y, w, h] = q.px;
            const u0 = (x - b.x) / b.w, u1 = (x + w - b.x) / b.w;
            const v0 = 1 - (y - b.y) / b.h, v1 = 1 - (y + h - b.y) / b.h;
            uv.set([u0, v0, u1, v0, u1, v1, u0, v1], i * 8);
            const base = i * 4;
            idx.set([base + 3, base + 2, base + 1, base + 3, base + 1, base], i * 6);
            const nrm = norm(cross(sub(q.br, q.bl), sub(q.tr, q.bl)));
            q.normal = nrm;
            corners.forEach((c, k) => over.set([c[0] + nrm[0] * labelOff, c[1] + nrm[1] * labelOff,
                c[2] + nrm[2] * labelOff], i * 12 + k * 3));
            let li = i * 48;
            for (const sign of [1, -1]) {
                const lift = (c) => [c[0] + nrm[0] * off * sign, c[1] + nrm[1] * off * sign, c[2] + nrm[2] * off * sign];
                for (let k = 0; k < 4; k++) {
                    lines.set(lift(corners[k]), li); li += 3;
                    lines.set(lift(corners[(k + 1) % 4]), li); li += 3;
                }
            }
        });
        if (e.geo) e.geo.dispose();
        if (e.lineGeo) e.lineGeo.dispose();
        if (e.labelGeo) e.labelGeo.dispose();
        e.geo = new T.BufferGeometry();
        e.geo.setAttribute('position', new T.BufferAttribute(pos, 3));
        e.geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
        e.geo.setIndex(new T.BufferAttribute(idx, 1));
        e.geo.computeBoundingBox();
        e.geo.computeBoundingSphere();
        e.lineGeo = new T.BufferGeometry();
        e.lineGeo.setAttribute('position', new T.BufferAttribute(lines, 3));
        // The screen's writing - name plate, sizes, corner readouts - on
        // the same cabinets 5 mm proud of the front: over the seam lines
        // (2 mm) and a picked joint's strip (4 mm), so the seams never cross
        // a label (Matt, 2026-11-09). It is depth tested, so a screen truly
        // in front of this one still hides it, writes no depth, and is
        // drawn after the seams (renderOrder); never picked.
        e.labelGeo = new T.BufferGeometry();
        e.labelGeo.setAttribute('position', new T.BufferAttribute(over, 3));
        e.labelGeo.setAttribute('uv', new T.BufferAttribute(uv, 2));
        e.labelGeo.setIndex(new T.BufferAttribute(idx, 1));
        e.labelGeo.computeBoundingSphere();
        if (!e.front) {
            e.front = new T.Mesh(e.geo, e.frontMat);
            e.back = new T.Mesh(e.geo, e.backMat);
            e.lines = new T.LineSegments(e.lineGeo, e.lineMat);
            e.labels = new T.Mesh(e.labelGeo, e.labelMat);
            e.labels.renderOrder = 2;
            e.labels.visible = !!e.labelMat.map;
            [e.front, e.back].forEach(m => { m.userData.layerId = e.id; });
            e.obj.add(e.front, e.back, e.lines, e.labels);
        } else {
            e.front.geometry = e.geo;
            e.back.geometry = e.geo;
            e.lines.geometry = e.lineGeo;
            e.labels.geometry = e.labelGeo;
        }
        e.seamKey = '';
    }

    // The screen's header and footer bars (s3dBarRows): one mesh per row,
    // its own drawing in the screen's bar and text colors with each bar's
    // size on it, the back the cabinets' dark grey. Children of the
    // screen's group, so they move, turn and curve with it; never picked,
    // so a click on a bar does not land on a cabinet or a seam.
    _s3dBuildBars(e, layer, slices) {
        const st = this._s3dState();
        const T = st.T;
        this._s3dDropBars(e);
        e.barRows = e.built ? s3dBarRows(layer, e.built, slices || null) : [];
        if (!e.barRows.length) return;
        const hex = /^#[0-9a-f]{6}$/i;
        const fill = hex.test(layer.riggingColor || '') ? layer.riggingColor : '#000000';
        const ink = hex.test(layer.riggingTextColor || '') ? layer.riggingTextColor : '#ffffff';
        e.barColors = { fill, ink };
        e.barGroup = new T.Group();
        e.barGroup.userData.bars = true;
        for (const row of e.barRows) {
            const n = row.quads.length;
            const pos = new Float32Array(n * 12), uv = new Float32Array(n * 8), idx = new Uint32Array(n * 6);
            row.quads.forEach((q, i) => {
                [q.tl, q.tr, q.br, q.bl].forEach((c, k) => pos.set(c, i * 12 + k * 3));
                const u0 = (q.slot + q.f0 - row.from) / row.span, u1 = (q.slot + q.f1 - row.from) / row.span;
                uv.set([u0, 1, u1, 1, u1, 0, u0, 0], i * 8);
                const base = i * 4;
                idx.set([base + 3, base + 2, base + 1, base + 3, base + 1, base], i * 6);
            });
            const geo = new T.BufferGeometry();
            geo.setAttribute('position', new T.BufferAttribute(pos, 3));
            geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
            geo.setIndex(new T.BufferAttribute(idx, 1));
            geo.computeBoundingSphere();
            const canvas = this._s3dPaintBars(row, fill, ink);
            const tex = new T.CanvasTexture(canvas);
            tex.colorSpace = T.SRGBColorSpace;
            if (st.renderer) tex.anisotropy = st.renderer.capabilities.getMaxAnisotropy();
            const front = new T.Mesh(geo, new T.MeshBasicMaterial({ map: tex, side: T.FrontSide }));
            const back = new T.Mesh(geo, e.backMat);
            front.userData.barRow = row.row;
            e.barGroup.add(front, back);
            row.canvas = canvas;
        }
        e.obj.add(e.barGroup);
    }

    // One row of bars drawn the way the Header/Footer tab draws it: each
    // bar filled, outlined in the text color, its size in the middle.
    // The texture spans the row's slots on this screen from its first
    // (row.from, row.span), so a bar across a seam is painted at its full
    // width and cut where this screen ends: its two halves meet.
    _s3dPaintBars(row, fill, ink) {
        const texH = 128;
        const avg = row.lengthMm / row.slots;
        const slotPx = Math.max(8, Math.min(Math.round(texH * avg / row.heightMm), Math.floor(4096 / row.span)));
        const canvas = document.createElement('canvas');
        canvas.width = slotPx * row.span;
        canvas.height = texH;
        const ctx = canvas.getContext('2d', { alpha: false });
        const line = Math.max(2, Math.round(texH * 0.04));
        for (let b = 0; b < row.bars.length; b++) {
            const span = row.bars[b];
            const x = (row.starts[b] - row.from) * slotPx;
            const w = span * slotPx;
            ctx.fillStyle = fill;
            ctx.fillRect(x, 0, w, texH);
            ctx.strokeStyle = ink;
            ctx.lineWidth = line;
            ctx.strokeRect(x + line / 2, line / 2, w - line, texH - line);
            // A corner piece says so; its fold runs down the middle of a
            // one panel piece or along the seam of a two panel one.
            const corner = !!(row.corners && row.corners[b]);
            const text = corner ? 'Corner' : String(span);
            let fontPx = Math.max(10, Math.min(texH * 0.6, w * 0.5));
            ctx.fillStyle = ink;
            ctx.font = `bold ${fontPx}px sans-serif`;
            if (corner) {
                const fit = (w * 0.8) / Math.max(1, ctx.measureText(text).width) * fontPx;
                fontPx = Math.max(8, Math.min(texH * 0.5, fit));
                ctx.font = `bold ${fontPx}px sans-serif`;
            }
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(text, x + w / 2, texH / 2);
        }
        return canvas;
    }

    _s3dDropBars(e) {
        if (!e.barGroup) return;
        e.barGroup.children.forEach(m => {
            if (m.userData.barRow) {
                if (m.material.map) m.material.map.dispose();
                m.material.dispose();
                m.geometry.dispose();
            }
        });
        if (e.obj) e.obj.remove(e.barGroup);
        e.barGroup = null;
    }

    // What the screen's Pixel Map drawing depends on: the layer itself (not
    // its 3D block or the runtime caches), the canvas font, and the group
    // names a group's label reads.
    _s3dTexKey(layer) {
        const strip = (k, v) => ((k === 'stage3d' || k === 'locked' || (k.length > 1 && k.charAt(0) === '_')) ? undefined : v);
        let font = '';
        try { font = (this.getPreferences && this.getPreferences().font) || ''; } catch (_) { font = ''; }
        return JSON.stringify(layer, strip) + '|' + font + '|' + JSON.stringify((this.project && this.project.groups) || []);
    }

    // The screen's front, drawn by the Pixel Map renderer itself onto a
    // canvas of its own - the binder's single-screen route (app-binder
    // _bPaintMap): the renderer pointed at an offscreen canvas in export
    // mode, every other layer and canvas switched off for the one paint,
    // the raster clip off, framed on this screen's own bounds - and every
    // value put back afterwards. The Pixel Map rotation is a processor
    // mapping, not how the wall stands, so the drawing is taken unrotated.
    // It is taken in two passes: the cabinets with every line on them onto
    // the face, and the screen's writing alone (the Screen name stage) onto
    // a transparent sheet laid over the seams (_s3dBuildMesh).
    _s3dPaint(e, layer) {
        const st = this._s3dState();
        const T = st.T;
        const r = window.canvasRenderer;
        if (!r || !e.built) return;
        const b = e.built.bounds;
        const side = Math.max(b.w, b.h);
        const maxTex = st.renderer ? st.renderer.capabilities.maxTextureSize : TEX_MAX;
        const cap = Math.min(TEX_MAX, maxTex);
        const baseScale = Math.min(cap / side, Math.max(1, TEX_MIN / side));
        // Up close (_s3dDetailCheck): one texel per pixel, within the caps.
        const detailScale = Math.min(1, Math.min(DETAIL_SIDE, maxTex) / side, Math.sqrt(DETAIL_TEXELS / (b.w * b.h)));
        e.baseScale = baseScale;
        e.detail = !!e.detail && detailScale > baseScale;
        const scale = e.detail ? detailScale : baseScale;
        const w = Math.max(1, Math.round(b.w * scale)), h = Math.max(1, Math.round(b.h * scale));
        if (!e.canvas) e.canvas = document.createElement('canvas');
        e.canvas.width = w;
        e.canvas.height = h;
        const ctx = e.canvas.getContext('2d', { alpha: false });
        if (!e.labelCanvas) e.labelCanvas = document.createElement('canvas');
        e.labelCanvas.width = w;
        e.labelCanvas.height = h;
        const labelCtx = e.labelCanvas.getContext('2d', { alpha: true });
        const stages = (window.CanvasRenderer && window.CanvasRenderer.RENDER_STAGES) || [];
        const proj = this.project;
        const canvases = (proj && Array.isArray(proj.canvases)) ? proj.canvases : [];
        const saved = {
            canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
            printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            hideNames: r.hideScreenNames, ignoreRaster: r.ignoreRasterBounds, stages: r.renderStages,
            active: proj ? proj.active_canvas_id : null,
            canvasVis: canvases.map(c => [c, c.visible]),
            layerVis: (proj.layers || []).map(l => [l, l.visible]),
            hadRotation: Object.prototype.hasOwnProperty.call(layer, 'rotation'),
            rotation: layer.rotation,
        };
        try {
            r.viewMode = 'pixel-map';
            const cid = layer.canvas_id || null;
            const canvas = canvases.find(c => c && c.id === cid) || null;
            canvases.forEach(c => { c.visible = canvas ? c.id === canvas.id : true; });
            if (canvas) proj.active_canvas_id = canvas.id;
            (proj.layers || []).forEach(l => { l.visible = (l === layer); });
            layer.rotation = 0;
            const ws = r._canvasWorkspace(canvas);
            r.canvas = e.canvas;
            r.ctx = ctx;
            r.exportMode = true;
            r.exportTransparentBg = false;
            r.printerMode = false;
            r.hideScreenNames = false;
            r.ignoreRasterBounds = true;
            r.zoom = scale;
            r.panX = -(ws.wx + b.x) * scale;
            r.panY = -(ws.wy + b.y) * scale;
            if (stages.includes('Screen name')) {
                r.renderStages = new Set(stages.filter(n => n !== 'Screen name'));
                r.render();
                r.canvas = e.labelCanvas;
                r.ctx = labelCtx;
                r.renderStages = new Set(['Screen name']);
                r.render();
            } else {
                r.render();
            }
        } catch (err) {
            sendClientLog('stage3d_paint_failed', { id: layer.id, error: String((err && err.message) || err) });
        } finally {
            saved.canvasVis.forEach(([c, v]) => { c.visible = v; });
            saved.layerVis.forEach(([l, v]) => { l.visible = v; });
            if (saved.hadRotation) layer.rotation = saved.rotation;
            else delete layer.rotation;
            if (proj) proj.active_canvas_id = saved.active;
            r.canvas = saved.canvas;
            r.ctx = saved.ctx;
            r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent;
            r.printerMode = saved.printer;
            r.hideScreenNames = saved.hideNames;
            r.ignoreRasterBounds = saved.ignoreRaster;
            r.renderStages = saved.stages;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom;
            r.panX = saved.panX;
            r.panY = saved.panY;
        }
        // A texel seen bigger than a page pixel is drawn as a crisp
        // square, the way Pixel Map shows its pixels at high zoom.
        if (!e.tex) {
            e.tex = new T.CanvasTexture(e.canvas);
            e.tex.colorSpace = T.SRGBColorSpace;
            if (st.renderer) e.tex.anisotropy = st.renderer.capabilities.getMaxAnisotropy();
            e.tex.magFilter = T.NearestFilter;
            e.frontMat.map = e.tex;
            e.frontMat.needsUpdate = true;
        } else if (e.tex.image !== e.canvas || e.tex.image.width !== w || e.tex.image.height !== h) {
            e.tex.dispose();
            e.tex.image = e.canvas;
        }
        e.tex.generateMipmaps = !e.detail;
        e.tex.minFilter = e.detail ? T.LinearFilter : T.LinearMipmapLinearFilter;
        e.tex.needsUpdate = true;
        e.texSize = [w, h];
        e.texScale = scale;
        if (!e.labelTex) {
            e.labelTex = new T.CanvasTexture(e.labelCanvas);
            e.labelTex.colorSpace = T.SRGBColorSpace;
            if (st.renderer) e.labelTex.anisotropy = st.renderer.capabilities.getMaxAnisotropy();
            e.labelMat.map = e.labelTex;
            e.labelMat.needsUpdate = true;
        } else if (!e.labelTexSize || e.labelTexSize[0] !== w || e.labelTexSize[1] !== h) {
            // a new size needs new storage on the card
            e.labelTex.dispose();
            e.labelTex.image = e.labelCanvas;
        }
        e.labelTexSize = [w, h];
        e.labelTex.generateMipmaps = !e.detail;
        e.labelTex.minFilter = e.detail ? T.LinearFilter : T.LinearMipmapLinearFilter;
        e.labelTex.needsUpdate = true;
        if (e.labels) e.labels.visible = true;
    }

    // ── up close ──────────────────────────────────────────────────────────

    // Page px per stage mm at `point`, as the camera draws it now.
    _s3dPagePxPerMm(point) {
        const st = this._s3dState();
        const cam = st.camera;
        const h = (st.renderer && st.renderer.domElement.clientHeight) || 600;
        if (cam.isOrthographicCamera) return h * (cam.zoom || 1) / Math.max(1e-9, cam.top - cam.bottom);
        const fwd = cam.getWorldDirection(new st.T.Vector3());
        const d = point.clone().sub(cam.position).dot(fwd);
        return d > 0 ? h / (2 * d * Math.tan(cam.fov * DEG / 2)) : 0;
    }

    // Before every frame: the near plane follows the camera in, so a screen
    // seen from a few mm is not cut away.
    _s3dFitNear() {
        const st = this._s3dState();
        const cam = st.camera;
        if (!cam || !cam.isPerspectiveCamera || !st.controls) return;
        let d = cam.position.distanceTo(st.controls.target) / 1000;
        const sphere = new st.T.Sphere();
        for (const e of st.entries.values()) {
            if (!e.geo || !e.geo.boundingSphere) continue;
            e.obj.updateMatrixWorld();
            sphere.copy(e.geo.boundingSphere).applyMatrix4(e.obj.matrixWorld);
            d = Math.min(d, Math.max(0, sphere.distanceToPoint(cam.position)) / 4);
        }
        const near = Math.max(NEAR_MIN, Math.min(NEAR_MAX, d));
        if (Math.abs(near - cam.near) > cam.near * 0.05) {
            cam.near = near;
            cam.updateProjectionMatrix();
        }
    }

    // Which screen, if any, is seen so close that its texture shows its
    // texels (one wider than DETAIL_AT page px) while it could be drawn
    // finer: the closest such screen is drawn again at one texel per pixel
    // once the camera settles, and the one drawn so before goes back to
    // its ordinary texture. One at a time, so a big show never holds more
    // than one such texture.
    _s3dDetailCheck() {
        const st = this._s3dState();
        if (!st.T || !st.camera || !st.controls) return;
        let best = null, bestRatio = DETAIL_AT;
        const box = new st.T.Box3(), near = new st.T.Vector3();
        const from = st.camera.isOrthographicCamera ? st.controls.target : st.camera.position;
        for (const e of st.entries.values()) {
            if (!e.geo || !e.geo.boundingBox || !e.built || !e.texSize) continue;
            if (!(e.baseScale < 1)) continue;
            box.copy(e.geo.boundingBox).applyMatrix4(e.obj.matrixWorld);
            box.clampPoint(from, near);
            const mmPerTexel = (e.built.bounds.w > 0 ? e.built.widthMm / e.built.bounds.w : 1) / e.baseScale;
            const ratio = mmPerTexel * this._s3dPagePxPerMm(near);
            if (ratio > bestRatio) { bestRatio = ratio; best = e; }
        }
        const want = best ? best.id : null;
        if (want === st.detailWant) return;
        st.detailWant = want;
        clearTimeout(st.detailTimer);
        st.detailTimer = setTimeout(() => this._s3dDetailApply(), DETAIL_SETTLE_MS);
    }

    _s3dDetailApply() {
        const st = this._s3dState();
        st.detailTimer = null;
        if (!st.active) return;
        const layers = (this.project && this.project.layers) || [];
        for (const e of st.entries.values()) {
            const on = e.id === st.detailWant;
            if (!!e.detail === on) continue;
            const layer = layers.find(l => l.id === e.id);
            if (!layer) continue;
            e.detail = on;
            this._s3dPaint(e, layer);
            sendClientLog('stage3d_detail', { id: e.id, on: !!e.detail, tex: e.texSize });
        }
        this._s3dRequestRender();
    }

    // The selected screens' seams in the accent colour, and the picked
    // joint as a strip along its seam.
    _s3dHighlight(tokens) {
        const st = this._s3dState();
        const T = st.T;
        const sel = this._s3dSelectedIds();
        const accent = new T.Color(tokens.accent);
        for (const e of st.entries.values()) {
            const on = sel.has(e.id);
            e.lineMat.color.set(on ? accent : new T.Color(0x0a0a0a));
            e.lineMat.opacity = on ? 1 : 0.9;
            const jt = st.joint && st.joint.layerId === e.id ? st.joint : null;
            const key = jt ? `${jt.axis}:${jt.index}:${e.geoKey.length}:${tokens.accent}` : '';
            if (e.seamKey === key && (key || !e.seam)) continue;
            e.seamKey = key;
            if (e.seam) {
                e.obj.remove(e.seam);
                e.seam.geometry.dispose();
                e.seam.material.dispose();
                e.seam = null;
            }
            if (!jt || !e.built) continue;
            const strip = this._s3dSeamStrip(e.built, jt.axis, jt.index);
            if (!strip) continue;
            const geo = new T.BufferGeometry();
            geo.setAttribute('position', new T.BufferAttribute(strip, 3));
            e.seam = new T.Mesh(geo, new T.MeshBasicMaterial({ color: accent, side: T.DoubleSide }));
            e.obj.add(e.seam);
        }
    }

    // Triangles along one joint's seam, a little proud of both faces.
    _s3dSeamStrip(built, axis, index) {
        const segs = [];
        const nCols = built.colLen.length, nRows = built.rowLen.length;
        // a tenth of a cabinet each side of the seam, so it reads at a glance
        const cab = Math.min(...built.colLen, ...built.rowLen) || 500;
        const halfW = Math.max(30, cab * 0.1);
        if (axis === 'col') {
            if (index < 0 || index >= nCols - 1) return null;
            const i = index + 1;
            const h = built.colHeads[i] || 0;
            const across = [Math.cos(h), 0, Math.sin(h)];
            for (let k = 0; k < nRows; k++) {
                segs.push([built.point(i, 0, k, 0), built.point(i, 0, k, built.rowLen[k]), across]);
            }
        } else {
            if (index < 0 || index >= nRows - 1) return null;
            const k = index + 1;
            for (let i = 0; i < nCols; i++) {
                const a = built.point(i, 0, k, 0), b = built.point(i, built.colLen[i], k, 0);
                const down = norm(sub(built.point(i, 0, k, 1), a));
                segs.push([a, b, down]);
            }
        }
        const out = [];
        for (const [a, b, across] of segs) {
            const along = sub(b, a);
            const nrm = norm(cross(along, across));
            for (const lift of [4, -4]) {
                const m = (p, s) => [p[0] + across[0] * halfW * s + nrm[0] * lift,
                    p[1] + across[1] * halfW * s + nrm[1] * lift,
                    p[2] + across[2] * halfW * s + nrm[2] * lift];
                const p1 = m(a, -1), p2 = m(a, 1), p3 = m(b, 1), p4 = m(b, -1);
                out.push(...p1, ...p2, ...p3, ...p1, ...p3, ...p4);
            }
        }
        return new Float32Array(out);
    }

    // The floor grid in the panel's units (1 ft with a line every 10, or
    // 1 m with one every 5) and the origin mark, sized to the stage.
    _s3dGrid(tokens) {
        const st = this._s3dState();
        const T = st.T;
        const units = st.units;
        const minor = units === 'm' ? 1000 : FT_MM;
        const every = units === 'm' ? 5 : 10;
        const major = minor * every;
        let reach = 10000;
        for (const e of st.entries.values()) {
            if (!e.geo || !e.geo.boundingSphere) continue;
            const c = e.obj.position;
            reach = Math.max(reach, Math.abs(c.x) + e.geo.boundingSphere.radius * 1.5, Math.abs(c.z) + e.geo.boundingSphere.radius * 1.5);
        }
        const half = Math.ceil(Math.max(reach * 1.5, 15000) / major) * major;
        const key = [st.grid, units, half, tokens.minor, tokens.major, tokens.accent].join('|');
        if (key === st.gridKey) return;
        st.gridKey = key;
        st.gridGroup.children.slice().forEach(child => {
            st.gridGroup.remove(child);
            if (child.geometry) child.geometry.dispose();
            if (child.material) child.material.dispose();
        });
        if (!st.grid) return;
        const size = half * 2;
        const fine = new T.GridHelper(size, Math.round(size / minor), tokens.minor, tokens.minor);
        fine.material.transparent = true;
        fine.material.opacity = 0.5;
        const coarse = new T.GridHelper(size, Math.round(size / major), tokens.major, tokens.major);
        coarse.position.y = 1;
        const ring = new T.Mesh(new T.RingGeometry(140, 180, 48), new T.MeshBasicMaterial({ color: new T.Color(tokens.accent), side: T.DoubleSide }));
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = 2;
        const crossGeo = new T.BufferGeometry();
        crossGeo.setAttribute('position', new T.BufferAttribute(new Float32Array([
            -400, 2, 0, 400, 2, 0, 0, 2, -400, 0, 2, 400]), 3));
        const crossLines = new T.LineSegments(crossGeo, new T.LineBasicMaterial({ color: new T.Color(tokens.accent) }));
        st.gridGroup.add(fine, coarse, ring, crossLines);
    }

    _s3dRequestRender() {
        const st = this._s3dState();
        if (!st.renderer || !st.active || st.frame) return;
        st.frame = requestAnimationFrame(() => {
            st.frame = 0;
            if (!st.active) return;
            // The move and turn handles keep their size on the page.
            this._s3dHandlesFrame();
            this._s3dFitNear();
            this._s3dDetailCheck();
            st.renderer.render(st.scene, st.camera);
        });
    }

    // ── picking, clicking and dragging in the viewport ────────────────────

    _s3dPick(clientX, clientY) {
        const st = this._s3dState();
        if (!st.renderer) return null;
        const rect = st.renderer.domElement.getBoundingClientRect();
        if (!rect.width || !rect.height) return null;
        const ndc = new st.T.Vector2(((clientX - rect.left) / rect.width) * 2 - 1,
            -((clientY - rect.top) / rect.height) * 2 + 1);
        st.raycaster.setFromCamera(ndc, st.camera);
        const meshes = [];
        for (const e of st.entries.values()) if (e.front) meshes.push(e.front, e.back);
        const hits = st.raycaster.intersectObjects(meshes, false);
        if (!hits.length) return null;
        const hit = hits[0];
        const e = st.entries.get(hit.object.userData.layerId);
        if (!e) return null;
        return { layerId: e.id, entry: e, point: hit.point.clone(), quad: Math.floor(hit.faceIndex / 2) };
    }

    // Which joint a hit lies on, if it is close to a seam of its cabinet.
    _s3dSeamAt(hit) {
        if (!hit || !hit.entry.built) return null;
        const built = hit.entry.built;
        const q = built.quads[hit.quad];
        if (!q) return null;
        const local = hit.entry.obj.worldToLocal(hit.point.clone());
        const p = [local.x, local.y, local.z];
        const ax = sub(q.tr, q.tl), ay = sub(q.bl, q.tl);
        const W = Math.hypot(...ax), H = Math.hypot(...ay);
        if (!W || !H) return null;
        const u = dot(sub(p, q.tl), ax) / W, w = dot(sub(p, q.tl), ay) / H;
        const near = Math.min(120, 0.18 * Math.min(W, H));
        const nCols = built.colLen.length, nRows = built.rowLen.length;
        const cands = [];
        if (u < near && q.ci > 0 && q.u0 < 1) cands.push([u, 'col', q.ci - 1]);
        if (W - u < near && q.ci < nCols - 1 && Math.abs(q.u1 - built.colLen[q.ci]) < 1) cands.push([W - u, 'col', q.ci]);
        if (w < near && q.ri > 0 && q.w0 < 1) cands.push([w, 'row', q.ri - 1]);
        if (H - w < near && q.ri < nRows - 1 && Math.abs(q.w1 - built.rowLen[q.ri]) < 1) cands.push([H - w, 'row', q.ri]);
        if (!cands.length) return null;
        cands.sort((a, b) => a[0] - b[0]);
        return { axis: cands[0][1], index: cands[0][2] };
    }

    // Pick one joint of one screen for the Joint angle field (null clears).
    _s3dSelectJoint(layerId, axis, index) {
        const st = this._s3dState();
        if (layerId == null) {
            st.joint = null;
        } else {
            const layer = ((this.project && this.project.layers) || []).find(l => l.id === layerId);
            const counts = this._s3dGridCounts(layer);
            const n = axis === 'col' ? counts.cols : counts.rows;
            if (!layer || (axis !== 'col' && axis !== 'row') || !(index >= 0 && index < n - 1)) return false;
            st.joint = { layerId, axis, index };
        }
        this._s3dRefreshPanel();
        if (st.T) {
            this._s3dHighlight(this._s3dTokens());
            this._s3dRequestRender();
        }
        return true;
    }

    _s3dClick(hit, ev) {
        const st = this._s3dState();
        const layers = (this.project && this.project.layers) || [];
        if (!hit) {
            if (st.joint) this._s3dSelectJoint(null);
            // A click on empty space lets go of the selection, as in any 3D
            // view; with Shift or Ctrl / Cmd held it keeps it.
            const keep = ev && (ev.shiftKey || ev.metaKey || ev.ctrlKey);
            if (!keep && this._s3dSelectedIds().size) {
                this.setSelectedLayersByIds([], null);
                this._s3dRefreshPanel();
            }
            return;
        }
        const layer = layers.find(l => l.id === hit.layerId);
        if (!layer) return;
        const multi = ev && (ev.shiftKey || ev.metaKey || ev.ctrlKey);
        const sel = this._s3dSelectedIds();
        if (multi) {
            this.toggleLayerSelection(layer);
            return;
        }
        if (!sel.has(layer.id) || sel.size > 1 || !this.currentLayer || this.currentLayer.id !== layer.id) {
            st.joint = null;
            this.selectLayer(layer);
            if (typeof this.renderLayers === 'function') this.renderLayers();
            if (window.canvasRenderer) window.canvasRenderer.render();
            this._s3dRefreshPanel();
            return;
        }
        const seam = this._s3dSeamAt(hit);
        if (seam) this._s3dSelectJoint(layer.id, seam.axis, seam.index);
        else if (st.joint) this._s3dSelectJoint(null);
    }

    // Everything a drag of `layerIds` carries: those screens and the rest of
    // each one's group.
    _s3dMoveSet(layerIds) {
        const layers = (this.project && this.project.layers) || [];
        const out = new Map();
        for (const id of layerIds) {
            const layer = layers.find(l => l.id === id);
            if (!this._s3dIsScreen(layer)) continue;
            out.set(layer.id, layer);
            this._s3dGroupPeers(layer).forEach(p => out.set(p.id, p));
        }
        return [...out.values()];
    }

    _s3dCommitMove(d) {
        const [dx, dy, dz] = d.delta;
        if (!dx && !dy && !dz) return;
        const changed = [];
        for (const layer of d.movers) {
            const p = d.starts.get(layer.id);
            if (!p) continue;
            layer.stage3d = s3dSanitize({ ...p, x: round(p.x + dx, 3), y: round(p.y + dy, 3), z: round(p.z + dz, 3) });
            changed.push(layer);
        }
        if (!changed.length) return;
        sendClientLog('stage3d_drag', { ids: changed.map(l => l.id), delta: d.delta });
        this.updateLayers(changed, true, 'Move Screen (3D)');
        this._s3dSchedule();
        this._s3dRefreshPanel();
    }

    // ── read-only hook for the tests ──────────────────────────────────────

    // What the stage holds right now: each screen's cabinet count, place,
    // texture size and on-screen centre. Changes nothing.
    _s3dDebug() {
        const st = this._s3dState();
        const screens = [];
        for (const e of st.entries.values()) {
            let at = null;
            if (st.renderer && st.camera && e.front) {
                const rect = st.renderer.domElement.getBoundingClientRect();
                const box = new st.T.Box3().setFromObject(e.front);
                const c = box.getCenter(new st.T.Vector3()).project(st.camera);
                at = [rect.left + (c.x + 1) / 2 * rect.width, rect.top + (1 - c.y) / 2 * rect.height];
            }
            const world = e.front ? new st.T.Box3().setFromObject(e.front) : null;
            screens.push({
                id: e.id, name: e.name, quads: e.built ? e.built.quads.length : 0,
                cols: e.built ? e.built.colLen.length : 0, rows: e.built ? e.built.rowLen.length : 0,
                widthMm: e.built ? round(e.built.widthMm, 3) : 0, heightMm: e.built ? round(e.built.heightMm, 3) : 0,
                placement: e.placement, stored: e.stored, tex: e.texSize || null, at,
                footerMm: e.footerMm || 0,
                shown: e.placement ? this._s3dShownOf(((this.project && this.project.layers) || []).find(l => l.id === e.id) || {}, e.placement) : null,
                datum: this._s3dDatumWorld(e),
                bars: (e.barRows || []).map(r => ({
                    row: r.row, bars: r.bars.slice(), starts: r.starts.slice(), slots: r.slots, wallSlots: r.wallSlots, fits: r.fits,
                    corners: (r.corners || []).slice(),
                    // each quad's slot and its bottom and top edges, in the screen's frame
                    quads: r.quads.map(q => ({ slot: q.slot, f0: q.f0, f1: q.f1,
                        tl: q.tl.map(v => round(v, 3)), tr: q.tr.map(v => round(v, 3)),
                        bl: q.bl.map(v => round(v, 3)), br: q.br.map(v => round(v, 3)) })),
                    heightMm: round(r.heightMm, 3), lengthMm: round(r.lengthMm, 3),
                    first: r.quads[0].tl.map(v => round(v, 3)), last: r.quads[r.quads.length - 1].tr.map(v => round(v, 3)),
                    tex: r.canvas ? [r.canvas.width, r.canvas.height] : null,
                    shown: !!(e.barGroup && e.barGroup.visible),
                })),
                barColors: e.barColors || null,
                world: world ? { min: world.min.toArray().map(v => round(v, 2)), max: world.max.toArray().map(v => round(v, 2)) } : null,
            });
        }
        return {
            loaded: !!st.T, webgl: st.webgl, active: st.active, failed: st.failed,
            message: (document.getElementById('s3d-message') || {}).hidden === false
                ? document.getElementById('s3d-message').textContent : '',
            units: this._s3dUnits(), grid: st.grid, bars: st.bars,
            joint: st.joint ? { ...st.joint } : null,
            camera: this._s3dCameraState(),
            gliding: !!st.glide, wheel: st.wheel ? st.wheel.kind : null,
            tool: st.tool === 'rotate' ? 'rotate' : 'move',
            handles: this._s3dHandlesDebug(),
            gridLines: st.gridGroup ? st.gridGroup.children.length : 0,
            screens,
        };
    }

    // The point the screen turns about and the panel's X, Y and Z show, in
    // stage mm, as drawn now (its group placed, a drag under way included).
    _s3dDatumWorld(e) {
        const st = this._s3dState();
        if (!e || !e.obj || !st.T) return null;
        e.obj.updateMatrixWorld(true);
        const off = e.datumOff || [0, 0, 0];
        return new st.T.Vector3(off[0], off[1], off[2]).applyMatrix4(e.obj.matrixWorld).toArray().map(n => round(n, 4));
    }

    // Every cabinet's four corners [tl, tr, br, bl] in stage mm as the
    // stage draws them now (the screen's own mesh through its placed
    // group), with its row and column. Changes nothing.
    _s3dDebugCorners(layerId) {
        const st = this._s3dState();
        const e = st.entries.get(layerId);
        if (!e || !e.built || !e.geo) return null;
        e.obj.updateMatrixWorld(true);
        const pos = e.geo.getAttribute('position');
        const v = new st.T.Vector3();
        return e.built.quads.map((q, i) => ({
            row: q.row, col: q.col,
            corners: [0, 1, 2, 3].map(k => v.fromBufferAttribute(pos, i * 4 + k)
                .applyMatrix4(e.obj.matrixWorld).toArray().map(n => round(n, 4))),
        }));
    }

    // Where on the page one joint's seam is drawn (client px): a point on
    // the cabinet before the joint, 20 mm short of the seam and a third of
    // the way along it, so a test can click it the way a person would.
    // Changes nothing.
    _s3dDebugSeam(layerId, axis, index) {
        const st = this._s3dState();
        const e = st.entries.get(layerId);
        if (!e || !e.built || !st.renderer) return null;
        const b = e.built;
        let local;
        if (axis === 'col') {
            if (!(index >= 0 && index < b.colLen.length - 1)) return null;
            const k = Math.floor(b.rowLen.length / 2);
            local = b.point(index, b.colLen[index] - 20, k, b.rowLen[k] / 3);
        } else {
            if (!(index >= 0 && index < b.rowLen.length - 1)) return null;
            const i = Math.floor(b.colLen.length / 2);
            local = b.point(i, b.colLen[i] / 3, index, b.rowLen[index] - 20);
        }
        e.obj.updateMatrixWorld(true);
        const v = new st.T.Vector3(local[0], local[1], local[2]).applyMatrix4(e.obj.matrixWorld).project(st.camera);
        const rect = st.renderer.domElement.getBoundingClientRect();
        return [rect.left + (v.x + 1) / 2 * rect.width, rect.top + (1 - v.y) / 2 * rect.height];
    }
}

for (const k of Object.getOwnPropertyNames(_Stage3D.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Stage3D.prototype, k));
    }
}
