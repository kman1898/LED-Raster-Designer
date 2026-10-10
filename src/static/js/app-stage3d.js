// app-stage3d: the 3D tab. Every screen Show Look shows stands on the stage
// in three dimensions, built from its own cabinets - their physical size in
// mm, blanked cabinets left out, half cabinets at half size - with its Pixel
// Map drawing on the front and plain dark grey behind.
//
// Each screen keeps its place on the layer as `stage3d` (centre in mm, Y up,
// +Z towards the audience; pitch / yaw / roll in degrees; the bend at every
// joint between columns and rows - the server's app.sanitize_stage3d holds
// the shape). A screen without one stands where its Show Look position puts
// it, so older files open unchanged. Every edit goes through updateLayers
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
const FT_MM = 304.8;
const TEX_MAX = 4096;            // a screen's texture, longest side
const TEX_MIN = 1024;            // small screens are drawn up to this
const SYNC_MS = 120;             // edits settle this long before a rebuild
const DEG = Math.PI / 180;

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
    const p = s3dSanitize(layer.stage3d);
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

function wrap180(deg) {
    let d = ((deg + 180) % 360 + 360) % 360 - 180;
    if (d <= -180) d += 360;
    return Math.abs(d) < 1e-9 ? 0 : d;
}

const round = (v, places) => {
    const f = Math.pow(10, places);
    return Math.round(v * f) / f;
};

// ── Rotation arithmetic (Euler order Y, X, Z: yaw, then pitch, then roll -
// three.js's 'YXZ', which is how the view turns each screen) ──────────────

function quatFromPlacement(p) {
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

function quatMul(a, b) {
    const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
    return [
        ax * bw + aw * bx + ay * bz - az * by,
        ay * bw + aw * by + az * bx - ax * bz,
        az * bw + aw * bz + ax * by - ay * bx,
        aw * bw - ax * bx - ay * by - az * bz,
    ];
}

const quatInv = (q) => [-q[0], -q[1], -q[2], q[3]];

function quatRotate(q, v) {
    const [qx, qy, qz, qw] = q, [vx, vy, vz] = v;
    const tx = 2 * (qy * vz - qz * vy), ty = 2 * (qz * vx - qx * vz), tz = 2 * (qx * vy - qy * vx);
    return [
        vx + qw * tx + qy * tz - qz * ty,
        vy + qw * ty + qz * tx - qx * tz,
        vz + qw * tz + qx * ty - qy * tx,
    ];
}

function anglesFromQuat(q) {
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

// ── Building a screen from its cabinets ──────────────────────────────────

// One chain of rigid segments (the columns across, or the rows down) that
// turns `joints[i]` degrees between segment i and i + 1, re-centred so the
// middle of its length sits at the origin heading straight along the first
// axis - a curve bends about the screen's own centre and never walks off.
// Positive turns towards the second axis (the audience), so both ends of a
// positively curved screen come forward.
function s3dChain(lengths, joints) {
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
// (mm, origin at its centre, X right, Y up, the front facing +Z). Pure data:
// no drawing library, so the debug hook and the tests read it as it is.
//
// Columns and rows are the panels' own slots. The column chain bends the
// screen about the upright (a curved wall), the row chain about the
// left-right line (an arch, a ceiling, a kick); a cabinet is placed on its
// row first and the result carried by its column, so a screen curved both
// ways opens small gaps at the corners rather than warping a cabinet.
function s3dBuild(layer, placement) {
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
    const colJ = cols.slice(0, -1).map((_, j) => jointAt(placement, 'col', j));
    const rowJ = rows.slice(0, -1).map((_, j) => jointAt(placement, 'row', j));
    const cc = s3dChain(colLen, colJ);
    const rc = s3dChain(rowLen, rowJ);

    // a point at `u` mm across chain column i and `w` mm down chain row k
    const point = (i, u, k, w) => {
        const h = cc.heads[i] || 0, o = cc.starts[i] || [0, 0];
        const g = rc.heads[k] || 0, q = rc.starts[k] || [0, 0];
        const down = q[0] + w * Math.cos(g);       // along the row chain's first axis (down)
        const fwd = q[1] + w * Math.sin(g);        // towards the audience
        const yy = -down;
        const dX = Math.cos(h), dZ = Math.sin(h);  // the column's across direction
        const nX = -Math.sin(h), nZ = Math.cos(h); // the column's front
        return [o[0] + u * dX + fwd * nX, yy, o[1] + u * dZ + fwd * nZ];
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
        quads.push({
            row: r, col: c, ci: i, ri: k, u0, u1, w0, w1,
            tl: point(i, u0, k, w0), tr: point(i, u1, k, w0),
            br: point(i, u1, k, w1), bl: point(i, u0, k, w1),
            px: [x, y, w, h],
        });
    }
    return {
        quads, point, colLen, rowLen, colJ, rowJ,
        colHeads: cc.heads, rowHeads: rc.heads,
        bounds: { x: bx0, y: by0, w: Math.max(1, bx1 - bx0), h: Math.max(1, by1 - by0) },
        widthMm: cc.total, heightMm: rc.total,
    };
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
                units: 'ft', grid: true, timer: null, frame: 0, gridKey: '',
                wired: false, drag: null, down: null, needsFit: false, saveTimer: null,
                orthoHalf: 5000,
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
            this._s3dCancelDrag();
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
    // up everything goes so the lowest screen's bottom edge is on the floor.
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
            floor = Math.min(floor, rect.bottom);
            items.push({ layer, rect });
        }
        return { items, lift: Number.isFinite(floor) ? -floor : 0, byId };
    }

    // Where `layer` stands: its own stage3d, or - with none - upright and
    // flat at its Show Look position, facing the audience, Z 0.
    _s3dPlacementOf(layer, layout) {
        const own = s3dSanitize(layer && layer.stage3d);
        if (own) return own;
        const lay = layout || this._s3dLayout();
        const rect = this._s3dShowRect(layer, lay.byId);
        return {
            x: round(rect.left + rect.w / 2, 3), y: round(rect.top - rect.h / 2 + lay.lift, 3), z: 0,
            pitch: 0, yaw: 0, roll: 0, curveCol: 0, curveRow: 0, jointsCol: {}, jointsRow: {},
        };
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
    // edited screen's centre (a peer with no 3D place yet starts from its
    // Show Look one). Curves stay each screen's own. One updateLayers call,
    // one undo step.
    _s3dCommit(layer, next, action) {
        if (!layer) return;
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
        const text = String(raw == null ? '' : raw).trim();
        if (text === '') return null;
        const units = this._s3dUnits();
        if (units === 'ft' && /['"]/.test(text)) {
            const neg = /^-/.test(text);
            const ft = text.match(/(\d+(?:\.\d+)?)\s*'/);
            const inch = text.match(/(\d+(?:\.\d+)?)\s*"/);
            const total = (ft ? parseFloat(ft[1]) : 0) * FT_MM + (inch ? parseFloat(inch[1]) : 0) * 25.4;
            return neg ? -total : total;
        }
        const v = evaluateMathExpression(text);
        if (!Number.isFinite(v)) return null;
        return v * (units === 'm' ? 1000 : FT_MM);
    }

    _s3dFormatLength(mm) {
        const v = Number(mm) || 0;
        return this._s3dUnits() === 'm' ? (v / 1000).toFixed(3) : (v / FT_MM).toFixed(2);
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
        const prev = this._s3dPlacementOf(layer);
        const next = { ...prev, jointsCol: { ...prev.jointsCol }, jointsRow: { ...prev.jointsRow } };
        if (key === 'x' || key === 'y' || key === 'z') {
            const mm = this._s3dParseLength(el.value);
            if (mm === null) { this._s3dRefreshPanel(true); return; }
            next[key] = mm;
            this._s3dCommit(layer, next, 'Move Screen (3D)');
        } else if (key === 'pitch' || key === 'yaw' || key === 'roll') {
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) { this._s3dRefreshPanel(true); return; }
            next[key] = deg;
            this._s3dCommit(layer, next, 'Rotate Screen (3D)');
        } else if (key === 'curve-col' || key === 'curve-row') {
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) { this._s3dRefreshPanel(true); return; }
            next[key === 'curve-col' ? 'curveCol' : 'curveRow'] = clampJoint(deg);
            this._s3dCommit(layer, next, 'Curve Screen (3D)');
        } else if (key === 'joint-angle') {
            const st = this._s3dState();
            const jt = st.joint;
            if (!jt || jt.layerId !== layer.id) return;
            const table = jt.axis === 'col' ? next.jointsCol : next.jointsRow;
            const deg = this._s3dParseAngle(el.value);
            if (deg === null) delete table[String(jt.index)];
            else table[String(jt.index)] = clampJoint(deg);
            this._s3dCommit(layer, next, 'Bend Joint (3D)');
        }
    }

    _s3dRotateBy(axis, step) {
        const layer = this._s3dCurrentScreen();
        if (!layer || !['pitch', 'yaw', 'roll'].includes(axis) || !Number.isFinite(step)) return;
        const prev = this._s3dPlacementOf(layer);
        this._s3dCommit(layer, { ...prev, [axis]: prev[axis] + step }, 'Rotate Screen (3D)');
    }

    _s3dClearJoint() {
        const layer = this._s3dCurrentScreen();
        const jt = this._s3dState().joint;
        if (!layer || !jt || jt.layerId !== layer.id) return;
        const prev = this._s3dPlacementOf(layer);
        const next = { ...prev, jointsCol: { ...prev.jointsCol }, jointsRow: { ...prev.jointsRow } };
        const table = jt.axis === 'col' ? next.jointsCol : next.jointsRow;
        if (!(String(jt.index) in table)) return;
        delete table[String(jt.index)];
        this._s3dCommit(layer, next, 'Bend Joint (3D)');
    }

    _s3dClearAllJoints() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const prev = this._s3dPlacementOf(layer);
        if (!Object.keys(prev.jointsCol).length && !Object.keys(prev.jointsRow).length) return;
        this._s3dCommit(layer, { ...prev, jointsCol: {}, jointsRow: {} }, 'Clear Joint Angles (3D)');
    }

    // Back to the Show Look place: the screen and its group lose their 3D
    // block (null, so the PUT carries the removal - the route drops the key).
    _s3dReset() {
        const layer = this._s3dCurrentScreen();
        if (!layer) return;
        const all = [layer, ...this._s3dGroupPeers(layer)].filter(l => l.stage3d);
        if (!all.length) return;
        all.forEach(l => { l.stage3d = null; });
        this._s3dState().joint = null;
        this.updateLayers(all, true, 'Reset 3D Placement');
        this._s3dSchedule();
        this._s3dRefreshPanel();
    }

    // ── the panel ─────────────────────────────────────────────────────────

    _s3dUnits() {
        const st = this._s3dState();
        if (st.epoch !== null && st.epoch === (this._projectEpoch || 0)) return st.units;
        return (this.project && this.project.stage3dUnits === 'm') ? 'm' : 'ft';
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
        on('s3d-fit', 'click', () => this._s3dFit(true));
        on('s3d-grid', 'click', () => this._s3dSetGrid(!this._s3dState().grid));
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
        const none = byId('s3d-none'), fields = byId('s3d-fields');
        if (none) none.hidden = !!layer;
        if (fields) fields.hidden = !layer;
        if (!layer) return;
        const p = this._s3dPlacementOf(layer);
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
        set('s3d-x', this._s3dFormatLength(p.x));
        set('s3d-y', this._s3dFormatLength(p.y));
        set('s3d-z', this._s3dFormatLength(p.z));
        set('s3d-pitch', String(round(p.pitch, 2)));
        set('s3d-yaw', String(round(p.yaw, 2)));
        set('s3d-roll', String(round(p.roll, 2)));
        set('s3d-curve-col', String(round(p.curveCol, 2)));
        set('s3d-curve-row', String(round(p.curveRow, 2)));
        const counts = this._s3dGridCounts(layer);
        const arc = (axis, n) => {
            let total = 0;
            for (let j = 0; j < n - 1; j++) total += jointAt(p, axis, j);
            const joints = Math.max(0, n - 1);
            const own = Object.keys(axis === 'col' ? p.jointsCol : p.jointsRow).length;
            return `${joints} joint${joints === 1 ? '' : 's'}, ${round(total, 1)}° in all`
                + (own ? ` (${own} set alone)` : '');
        };
        const arcCol = byId('s3d-arc-col'), arcRow = byId('s3d-arc-row');
        if (arcCol) arcCol.textContent = arc('col', counts.cols);
        if (arcRow) arcRow.textContent = arc('row', counts.rows);
        const jt = st.joint && st.joint.layerId === layer.id ? st.joint : null;
        const label = byId('s3d-joint-label'), input = byId('s3d-joint-angle');
        if (label) {
            label.textContent = jt
                ? (jt.axis === 'col'
                    ? `Joint between columns ${jt.index + 1} and ${jt.index + 2}.`
                    : `Joint between rows ${jt.index + 1} and ${jt.index + 2}.`)
                : 'Click a seam between two columns or two rows of the selected screen to bend that joint alone.';
        }
        if (input) {
            input.disabled = !jt;
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
            st.units = p.stage3dUnits === 'm' ? 'm' : 'ft';
            st.grid = p.stage3dGrid !== false;
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
        if (p.stage3dUnits !== undefined && p.stage3dUnits !== st.units) p.stage3dUnits = st.units;
        if (p.stage3dGrid !== undefined && p.stage3dGrid !== st.grid) p.stage3dGrid = st.grid;
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
        st.saveTimer = setTimeout(() => {
            st.saveTimer = null;
            const cam = this._s3dCameraState();
            if (!cam) return;
            st.cam = cam;
            if (this.project) this.project.stage3dCamera = JSON.parse(JSON.stringify(cam));
            this._s3dPutView({ camera: cam });
        }, 400);
    }

    _s3dApplyCamera(cam) {
        const st = this._s3dState();
        if (!st.T || !cam) return;
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

    // Every screen's world box, or a 10 m stage round the origin with none.
    _s3dWorldBox() {
        const st = this._s3dState();
        const T = st.T;
        const box = new T.Box3();
        st.root.updateMatrixWorld(true);
        for (const e of st.entries.values()) {
            if (e.front && e.front.geometry) box.expandByObject(e.front);
        }
        if (box.isEmpty()) box.set(new T.Vector3(-5000, 0, -5000), new T.Vector3(5000, 3000, 5000));
        return box;
    }

    // Frame every screen, looking along `dir` (from the target towards the
    // camera) - the current direction when none is given.
    _s3dFit(save = false, dir = null) {
        const st = this._s3dState();
        if (!st.T || !st.controls) {
            if (st.T) st.needsFit = true;
            return;
        }
        const T = st.T;
        const box = this._s3dWorldBox();
        const centre = box.getCenter(new T.Vector3());
        const radius = Math.max(500, box.getSize(new T.Vector3()).length() / 2);
        let look = dir ? dir.clone() : st.camera.position.clone().sub(st.controls.target);
        if (look.lengthSq() < 1e-6) look = new T.Vector3(0.35, 0.3, 1);
        look.normalize();
        const fov = st.persp.fov * DEG;
        const aspect = st.persp.aspect || 1;
        const fit = radius / Math.sin(Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * aspect)) / 2);
        st.controls.target.copy(centre);
        st.camera.position.copy(centre).add(look.multiplyScalar(fit * 0.9));
        st.orthoHalf = radius * 0.95;
        st.ortho.zoom = 1;
        st.camera.lookAt(centre);
        this._s3dFrameCameras();
        st.controls.update();
        this._s3dRequestRender();
        if (save) this._s3dSaveCameraSoon();
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
        st.camera.up.set(0, 1, 0);
        this._s3dFit(true, new T.Vector3(d[0], d[1], d[2]));
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
        if (e.tex) e.tex.dispose();
        if (e.seam) { e.seam.geometry.dispose(); e.seam.material.dispose(); }
        [e.frontMat, e.backMat, e.lineMat].forEach(m => { if (m) m.dispose(); });
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
            e.obj.userData.layerId = layer.id;
            st.root.add(e.obj);
            st.entries.set(layer.id, e);
        }
        const geoKey = JSON.stringify([
            (layer.panels || []).map(p => [p.row, p.col, p.x, p.y, p.width, p.height, !!p.hidden, !!p.blank]),
            layer.panel_width_mm, layer.panel_height_mm, layer.cabinet_width, layer.cabinet_height,
            placement.curveCol, placement.curveRow, placement.jointsCol, placement.jointsRow,
        ]);
        if (e.geoKey !== geoKey) {
            e.geoKey = geoKey;
            this._s3dBuildMesh(e, layer, placement);
        }
        const texKey = this._s3dTexKey(layer);
        if (e.texKey !== texKey) {
            e.texKey = texKey;
            this._s3dPaint(e, layer);
        }
        e.placement = placement;
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
        const b = built.bounds;
        const off = 2;   // mm, seams off the faces
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
        e.geo = new T.BufferGeometry();
        e.geo.setAttribute('position', new T.BufferAttribute(pos, 3));
        e.geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
        e.geo.setIndex(new T.BufferAttribute(idx, 1));
        e.geo.computeBoundingBox();
        e.geo.computeBoundingSphere();
        e.lineGeo = new T.BufferGeometry();
        e.lineGeo.setAttribute('position', new T.BufferAttribute(lines, 3));
        if (!e.front) {
            e.front = new T.Mesh(e.geo, e.frontMat);
            e.back = new T.Mesh(e.geo, e.backMat);
            e.lines = new T.LineSegments(e.lineGeo, e.lineMat);
            [e.front, e.back].forEach(m => { m.userData.layerId = e.id; });
            e.obj.add(e.front, e.back, e.lines);
        } else {
            e.front.geometry = e.geo;
            e.back.geometry = e.geo;
            e.lines.geometry = e.lineGeo;
        }
        e.seamKey = '';
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
    _s3dPaint(e, layer) {
        const st = this._s3dState();
        const T = st.T;
        const r = window.canvasRenderer;
        if (!r || !e.built) return;
        const b = e.built.bounds;
        const side = Math.max(b.w, b.h);
        const cap = Math.min(TEX_MAX, st.renderer ? st.renderer.capabilities.maxTextureSize : TEX_MAX);
        const scale = Math.min(cap / side, Math.max(1, TEX_MIN / side));
        const w = Math.max(1, Math.round(b.w * scale)), h = Math.max(1, Math.round(b.h * scale));
        if (!e.canvas) e.canvas = document.createElement('canvas');
        e.canvas.width = w;
        e.canvas.height = h;
        const ctx = e.canvas.getContext('2d', { alpha: false });
        const proj = this.project;
        const canvases = (proj && Array.isArray(proj.canvases)) ? proj.canvases : [];
        const saved = {
            canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
            printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            hideNames: r.hideScreenNames, ignoreRaster: r.ignoreRasterBounds,
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
            r.render();
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
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom;
            r.panX = saved.panX;
            r.panY = saved.panY;
        }
        if (!e.tex) {
            e.tex = new T.CanvasTexture(e.canvas);
            e.tex.colorSpace = T.SRGBColorSpace;
            if (st.renderer) e.tex.anisotropy = st.renderer.capabilities.getMaxAnisotropy();
            e.frontMat.map = e.tex;
            e.frontMat.needsUpdate = true;
        } else if (e.tex.image !== e.canvas || e.tex.image.width !== w || e.tex.image.height !== h) {
            e.tex.dispose();
            e.tex.image = e.canvas;
        }
        e.tex.needsUpdate = true;
        e.texSize = [w, h];
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
            st.renderer.render(st.scene, st.camera);
        });
    }

    // ── picking, clicking and dragging in the viewport ────────────────────

    _s3dWireViewport(view) {
        if (!view) return;
        // Capture: this runs before the orbit controls hear the press, so a
        // press on a selected screen can take the pointer for a move.
        view.addEventListener('pointerdown', (ev) => this._s3dPointerDown(ev), true);
        window.addEventListener('pointermove', (ev) => this._s3dPointerMove(ev));
        window.addEventListener('pointerup', (ev) => this._s3dPointerUp(ev));
    }

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

    _s3dPointerDown(ev) {
        const st = this._s3dState();
        st.down = null;
        if (ev.button !== 0 || !st.renderer) return;
        const hit = this._s3dPick(ev.clientX, ev.clientY);
        st.down = { x: ev.clientX, y: ev.clientY, hit, moved: false, shift: ev.shiftKey, meta: ev.metaKey || ev.ctrlKey };
        const sel = this._s3dSelectedIds();
        if (!hit || !sel.has(hit.layerId) || ev.altKey || ev.ctrlKey || ev.metaKey) return;
        const T = st.T;
        // This press moves the screen, not the camera.
        st.controls.enabled = false;
        const layout = this._s3dLayout();
        const movers = this._s3dMoveSet(sel.size ? [...sel] : [hit.layerId]);
        const starts = new Map(movers.map(l => [l.id, this._s3dPlacementOf(l, layout)]));
        const vertical = ev.shiftKey;
        let normal;
        if (vertical) {
            normal = st.camera.position.clone().sub(hit.point);
            normal.y = 0;
            if (normal.lengthSq() < 1e-6) normal.set(0, 0, 1);
            normal.normalize();
        } else {
            normal = new T.Vector3(0, 1, 0);
        }
        st.drag = {
            plane: new T.Plane().setFromNormalAndCoplanarPoint(normal, hit.point),
            from: hit.point.clone(), vertical, movers, starts, active: false, delta: [0, 0, 0],
        };
        const view = document.getElementById('s3d-view');
        if (view) view.classList.add('s3d-grab');
    }

    _s3dPointerMove(ev) {
        const st = this._s3dState();
        if (st.down && !st.down.moved
                && Math.hypot(ev.clientX - st.down.x, ev.clientY - st.down.y) > 4) {
            st.down.moved = true;
        }
        const d = st.drag;
        if (!d || !st.down) return;
        if (!d.active && !st.down.moved) return;
        d.active = true;
        const rect = st.renderer.domElement.getBoundingClientRect();
        const ndc = new st.T.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1,
            -((ev.clientY - rect.top) / rect.height) * 2 + 1);
        st.raycaster.setFromCamera(ndc, st.camera);
        const at = st.raycaster.ray.intersectPlane(d.plane, new st.T.Vector3());
        if (!at) return;
        const delta = at.sub(d.from);
        d.delta = d.vertical ? [0, delta.y, 0] : [delta.x, 0, delta.z];
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (e) e.obj.position.set(p.x + d.delta[0], p.y + d.delta[1], p.z + d.delta[2]);
        }
        this._s3dRequestRender();
    }

    _s3dPointerUp(ev) {
        const st = this._s3dState();
        const down = st.down;
        const d = st.drag;
        st.down = null;
        st.drag = null;
        const view = document.getElementById('s3d-view');
        if (view) view.classList.remove('s3d-grab');
        if (st.controls) st.controls.enabled = true;
        if (!down) return;
        if (d && d.active) {
            this._s3dCommitMove(d);
            return;
        }
        if (!down.moved) this._s3dClick(down.hit, ev);
    }

    _s3dCancelDrag() {
        const st = this._s3dState();
        if (st.drag && st.drag.active) {
            for (const [id, p] of st.drag.starts) {
                const e = st.entries.get(id);
                if (e) e.obj.position.set(p.x, p.y, p.z);
            }
        }
        st.drag = null;
        st.down = null;
        if (st.controls) st.controls.enabled = true;
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
                world: world ? { min: world.min.toArray().map(v => round(v, 2)), max: world.max.toArray().map(v => round(v, 2)) } : null,
            });
        }
        return {
            loaded: !!st.T, webgl: st.webgl, active: st.active, failed: st.failed,
            message: (document.getElementById('s3d-message') || {}).hidden === false
                ? document.getElementById('s3d-message').textContent : '',
            units: this._s3dUnits(), grid: st.grid,
            joint: st.joint ? { ...st.joint } : null,
            camera: this._s3dCameraState(),
            gridLines: st.gridGroup ? st.gridGroup.children.length : 0,
            screens,
        };
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
