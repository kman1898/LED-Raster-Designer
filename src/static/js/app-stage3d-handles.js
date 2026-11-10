// app-stage3d-handles: the move and turn handles on the 3D tab's selection,
// snapping, and the arrow-key nudges (the owner's ruling, 2026-11-08: "we
// need to be able to manipulate screens easily too").
//
// The selected screens (and the rest of each one's group) carry one set of
// handles at the point they turn about - a lone screen's bottom middle (the
// point its X, Y and Z show, 2026-11-09: its footer's foot when it has one,
// else the panels' bottom edge), several screens' or a group's the middle
// of the bottom of their combined bounds - so a turn never lifts a screen
// off the floor and the arrows start where the fields measure:
//
//   Move (W)     an arrow per stage axis, X red, Y green, Z blue; a drag
//                slides the screens along that axis only. A small square
//                between two arrows moves them on that plane (XZ, the
//                floor, green; XY blue; YZ red, each the color of the axis
//                it keeps still)
//   Rotate (E)   a ring per angle, Pitch red, Yaw green, Roll blue, laid in
//                the screen's own order (yaw, then pitch, then roll), so a
//                ring turns that one angle and leaves the other two
//
// Ctrl (Cmd on a Mac) held during a drag snaps: moves in 6 in steps (0.1 m
// when the show is in meters), turns to whole 15 degrees. The figure rides
// beside the cursor and the panel's fields follow live. One drag is one
// undo step; Esc puts it back. The arrow keys nudge the selection across
// the floor as the view faces it, Page Up and Page Down raise and lower
// it; Shift makes the step bigger, and a burst of nudges is one undo step.
// Locked screens never move and are named, the same as every other edit.
//
// The handles keep their size on the page at any zoom and draw over the
// screens, so they can always be grabbed. The middle button never reaches
// them: it belongs to the camera (app-stage3d-nav.js).
//
// G AND R, THE KEYBOARD WAY (owner, 2026-11-10, the way 3D software does
// it; neither key was taken anywhere in the app): G moves the selection and
// R turns it, following the mouse with no button held. X, Y or Z then locks
// the move to that axis (the turn to pitch, yaw or roll; the same key again
// unlocks), a typed figure sets the move in the panel's units or the turn
// in degrees, and Enter or a click keeps it, Esc or a right-click puts it
// back. Unlocked, G moves on the plane facing the view and R turns the yaw.
// One gesture is one undo step, the same as a handle's drag.
import { LEDRasterApp } from './app-core.js';
import { evaluateMathExpression, sendClientLog } from './helpers.js';
import {
    DEG, FT_MM, round, wrap180, quatFromPlacement, quatMul, quatRotate, anglesFromQuat, s3dSanitize,
} from './app-stage3d.js';

const RED = 0xe5484d, GREEN = 0x4cbb5a, BLUE = 0x3d7ef2, HOT = 0xffd200;
const AXES = { x: [1, 0, 0, RED], y: [0, 1, 0, GREEN], z: [0, 0, 1, BLUE] };
const RINGS = { pitch: RED, yaw: GREEN, roll: BLUE };
// A plane square between two arrows, colored as the axis it keeps still.
const PLANES = { xy: ['x', 'y', BLUE], xz: ['x', 'z', GREEN], yz: ['y', 'z', RED] };
const PLANE_AT = 30, PLANE_SIZE = 18, PLANE_OPACITY = 0.55;
// G and R: the axis keys, and the angle each locks R to.
const KEY_AXES = { x: 'pitch', y: 'yaw', z: 'roll' };
const ANGLE_NAMES = { pitch: 'Pitch', yaw: 'Yaw', roll: 'Roll' };
// Sizes on the page, px.
const SHAFT_FROM = 24, SHAFT_TO = 92, TIP = 22, SHAFT_R = 2.2, TIP_R = 8, ARROW_PICK_R = 10;
const RING_R = 86, RING_TUBE = 2, RING_PICK = 9;
const NUDGE_SETTLE_MS = 700;     // a burst of nudges ends this long after the last

class _Stage3DHandles {
    // ── building ──────────────────────────────────────────────────────────

    _s3dHandlesBuild() {
        const st = this._s3dState();
        if (st.handles || !st.T || !st.scene) return st.handles;
        const T = st.T;
        const mat = (color) => new T.MeshBasicMaterial({
            color, depthTest: false, depthWrite: false, transparent: true, opacity: 1, toneMapped: false,
        });
        const pickMat = new T.MeshBasicMaterial({
            colorWrite: false, depthTest: false, depthWrite: false, transparent: true, opacity: 0,
        });
        const group = new T.Group();
        group.name = 's3d-handles';
        group.visible = false;
        const move = new T.Group(), rotate = new T.Group();
        group.add(move, rotate);
        const parts = {};
        const Yup = new T.Vector3(0, 1, 0), Zup = new T.Vector3(0, 0, 1);
        for (const [name, [x, y, z, color]] of Object.entries(AXES)) {
            const g = new T.Group();
            const m = mat(color);
            const shaft = new T.Mesh(new T.CylinderGeometry(SHAFT_R, SHAFT_R, SHAFT_TO - SHAFT_FROM, 10), m);
            shaft.position.y = (SHAFT_FROM + SHAFT_TO) / 2;
            const tip = new T.Mesh(new T.ConeGeometry(TIP_R, TIP, 20), m);
            tip.position.y = SHAFT_TO + TIP / 2;
            const pick = new T.Mesh(new T.CylinderGeometry(ARROW_PICK_R, ARROW_PICK_R, SHAFT_TO + TIP - SHAFT_FROM + 6, 8), pickMat);
            pick.position.y = (SHAFT_FROM + SHAFT_TO + TIP) / 2;
            [shaft, tip, pick].forEach(o => { o.renderOrder = 1000; });
            pick.userData.handle = { kind: 'axis', name };
            g.add(shaft, tip, pick);
            g.quaternion.setFromUnitVectors(Yup, new T.Vector3(x, y, z));
            move.add(g);
            parts[name] = { group: g, mat: m, color, pick, dir: new T.Vector3(x, y, z) };
        }
        const pickBoth = new T.MeshBasicMaterial({
            colorWrite: false, depthTest: false, depthWrite: false, transparent: true, opacity: 0, side: T.DoubleSide,
        });
        for (const [name, [a, b, color]] of Object.entries(PLANES)) {
            const g = new T.Group();
            const m = mat(color);
            m.side = T.DoubleSide;
            m.opacity = PLANE_OPACITY;
            const ua = new T.Vector3(...AXES[a].slice(0, 3)), ub = new T.Vector3(...AXES[b].slice(0, 3));
            const normal = ua.clone().cross(ub);
            const square = new T.Mesh(new T.PlaneGeometry(PLANE_SIZE, PLANE_SIZE), m);
            const pick = new T.Mesh(new T.PlaneGeometry(PLANE_SIZE + 6, PLANE_SIZE + 6), pickBoth);
            [square, pick].forEach(o => { o.position.set(PLANE_AT, PLANE_AT, 0); o.renderOrder = 1000; });
            pick.userData.handle = { kind: 'plane', name };
            g.add(square, pick);
            g.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(ua, ub, normal));
            move.add(g);
            parts[name] = { group: g, mat: m, color, pick, a: ua, b: ub, normal };
        }
        for (const [name, color] of Object.entries(RINGS)) {
            const g = new T.Group();
            const m = mat(color);
            const ring = new T.Mesh(new T.TorusGeometry(RING_R, RING_TUBE, 8, 120), m);
            const pick = new T.Mesh(new T.TorusGeometry(RING_R, RING_PICK, 6, 60), pickMat);
            [ring, pick].forEach(o => { o.renderOrder = 1000; });
            pick.userData.handle = { kind: 'ring', name };
            g.add(ring, pick);
            rotate.add(g);
            parts[name] = { group: g, mat: m, color, pick, zUp: Zup };
        }
        st.scene.add(group);
        st.handles = { group, move, rotate, parts, ids: [], hover: null, drag: null };
        return st.handles;
    }

    // The screens that carry the handles: the selection on the stage and
    // the rest of each one's group. Called on every stage sync.
    _s3dHandlesSync() {
        const st = this._s3dState();
        const h = this._s3dHandlesBuild();
        if (!h) return;
        const sel = [...this._s3dSelectedIds()];
        h.ids = this._s3dMoveSet(sel).map(l => l.id).filter(id => st.entries.has(id));
    }

    _s3dSetTool(tool) {
        const st = this._s3dState();
        const next = tool === 'rotate' ? 'rotate' : 'move';
        if (st.tool !== next) sendClientLog('stage3d_tool', { tool: next });
        st.tool = next;
        if (st.handles) st.handles.hover = null;
        this._s3dRefreshPanel();
        this._s3dRequestRender();
    }

    // ── where they stand ──────────────────────────────────────────────────

    // World mm per page px at `point`, as the camera draws it now.
    _s3dPxToWorld(point) {
        const st = this._s3dState();
        const cam = st.camera;
        const h = (st.renderer && st.renderer.domElement.clientHeight) || 600;
        if (cam.isOrthographicCamera) return (cam.top - cam.bottom) / (cam.zoom || 1) / h;
        const fwd = cam.getWorldDirection(new st.T.Vector3());
        const d = point.clone().sub(cam.position).dot(fwd);
        if (!(d > cam.near)) return 0;
        return 2 * d * Math.tan(cam.fov * DEG / 2) / h;
    }

    // The handles' pivot and the three turn axes, from the screens as
    // drawn now (a drag holds its own pivot). One screen: its bottom middle,
    // where its group stands it. Several: the middle of the bottom face of
    // the box round them all - the lowest point of their combined bounds,
    // under their middle. Null with nothing to carry.
    _s3dHandlesPose() {
        const st = this._s3dState();
        const h = st.handles;
        if (!h || !st.active) return null;
        const T = st.T;
        const entries = h.ids.map(id => st.entries.get(id)).filter(Boolean);
        if (!entries.length) return null;
        const primary = entries.find(e => this.currentLayer && e.id === this.currentLayer.id) || entries[0];
        let pivot;
        const datum = (e) => new T.Vector3().fromArray(this._s3dDatumWorld(e) || e.obj.position.toArray());
        if (h.drag) {
            pivot = h.drag.pivot.clone();
        } else if (entries.length === 1) {
            pivot = datum(primary);
        } else {
            const box = new T.Box3();
            entries.forEach(e => {
                e.obj.updateMatrixWorld(true);
                if (e.front) box.expandByObject(e.front);
                box.expandByPoint(datum(e));
            });
            if (box.isEmpty()) {
                pivot = primary.obj.position.clone();
            } else {
                pivot = box.getCenter(new T.Vector3());
                pivot.y = box.min.y;
            }
        }
        const r = primary.obj.rotation;
        const qYaw = new T.Quaternion().setFromAxisAngle(new T.Vector3(0, 1, 0), r.y);
        const qYawPitch = qYaw.clone().multiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(1, 0, 0), r.x));
        return {
            pivot, primaryId: primary.id, ids: entries.map(e => e.id),
            axes: {
                yaw: new T.Vector3(0, 1, 0),
                pitch: new T.Vector3(1, 0, 0).applyQuaternion(qYaw),
                roll: new T.Vector3(0, 0, 1).applyQuaternion(qYawPitch),
            },
        };
    }

    // Every frame: the handles at the selection's centre, their size held
    // on the page, the arrow pointing at the camera put away.
    _s3dHandlesFrame() {
        const st = this._s3dState();
        const h = st.handles;
        if (!h) return;
        const pose = this._s3dHandlesPose();
        const s = pose ? this._s3dPxToWorld(pose.pivot) : 0;
        if (!pose || !(s > 0)) {
            h.group.visible = false;
            return;
        }
        const T = st.T;
        h.group.visible = true;
        h.group.position.copy(pose.pivot);
        h.group.scale.setScalar(s);
        const tool = st.tool === 'rotate' ? 'rotate' : 'move';
        h.move.visible = tool === 'move';
        h.rotate.visible = tool === 'rotate';
        const cam = st.camera;
        const look = cam.isOrthographicCamera
            ? cam.getWorldDirection(new T.Vector3())
            : pose.pivot.clone().sub(cam.position).normalize();
        const active = h.drag ? h.drag.handle.name : null;
        for (const name of Object.keys(AXES)) {
            const p = h.parts[name];
            p.group.visible = Math.abs(p.dir.dot(look)) < 0.97;
            p.mat.color.setHex(active === name || (!active && h.hover === name) ? HOT : p.color);
            p.mat.opacity = active && active !== name ? 0.35 : 1;
        }
        for (const name of Object.keys(PLANES)) {
            const p = h.parts[name];
            // put away when seen edge on
            p.group.visible = Math.abs(p.normal.dot(look)) > 0.2;
            p.mat.color.setHex(active === name || (!active && h.hover === name) ? HOT : p.color);
            p.mat.opacity = active && active !== name ? 0.2 : PLANE_OPACITY;
        }
        for (const name of Object.keys(RINGS)) {
            const p = h.parts[name];
            p.group.quaternion.setFromUnitVectors(p.zUp, pose.axes[name]);
            p.mat.color.setHex(active === name || (!active && h.hover === name) ? HOT : p.color);
            p.mat.opacity = active && active !== name ? 0.35 : 1;
        }
        h.group.updateMatrixWorld(true);
    }

    // The handle under a page point: {kind: 'axis' | 'ring', name, point}.
    _s3dHandlePick(clientX, clientY) {
        const st = this._s3dState();
        const h = st.handles;
        if (!h || !st.renderer || !st.active) return null;
        this._s3dHandlesFrame();
        if (!h.group.visible) return null;
        const ray = this._s3dRayAt(clientX, clientY);
        if (!ray) return null;
        const live = h.group.visible ? (st.tool === 'rotate' ? h.rotate : h.move) : null;
        const picks = [];
        live.children.forEach(g => { if (g.visible) g.children.forEach(o => { if (o.userData.handle) picks.push(o); }); });
        const hits = st.raycaster.intersectObjects(picks, false);
        if (!hits.length) return null;
        return { ...hits[0].object.userData.handle, point: hits[0].point.clone() };
    }

    _s3dHandlesHover(clientX, clientY) {
        const st = this._s3dState();
        const h = st.handles;
        if (!h) return;
        const got = this._s3dHandlePick(clientX, clientY);
        const name = got ? got.name : null;
        this._s3dViewClass('s3d-on-handle', !!got);
        if (h.hover === name) return;
        h.hover = name;
        this._s3dRequestRender();
    }

    _s3dHandlesDebug() {
        const st = this._s3dState();
        const h = st.handles;
        if (!h || !st.renderer || !st.T) return null;
        const pose = this._s3dHandlesPose();
        if (!pose) return { shown: false, ids: [] };
        const s = this._s3dPxToWorld(pose.pivot);
        const at = (v, px) => this._s3dDebugWhere(pose.pivot.clone().add(v.clone().multiplyScalar(px * s)).toArray());
        const gripPx = SHAFT_FROM + (SHAFT_TO - SHAFT_FROM) * 0.66;
        const out = {
            shown: true, ids: pose.ids, tool: st.tool === 'rotate' ? 'rotate' : 'move',
            centre: at(new st.T.Vector3(), 0), pivot: pose.pivot.toArray(), perPx: s, gripPx, grips: {},
        };
        // A point on each handle a person would grab: an arrow's shaft two
        // thirds out, a ring's far side from the camera's right.
        for (const name of Object.keys(AXES)) {
            const p = h.parts[name];
            if (Math.abs(p.dir.dot(st.camera.getWorldDirection(new st.T.Vector3()))) < 0.97) {
                out.grips[name] = at(p.dir, gripPx);
            }
        }
        // A plane square's middle.
        for (const name of Object.keys(PLANES)) {
            const p = h.parts[name];
            if (p.group.visible) out.grips[name] = at(p.a.clone().add(p.b), PLANE_AT);
        }
        // A ring's grip lies midway between the places the other two rings
        // cross it, on the side that shows most on the page.
        const centre = out.centre;
        for (const name of Object.keys(RINGS)) {
            const a = pose.axes[name];
            const [b, c] = Object.keys(RINGS).filter(k => k !== name).map(k => pose.axes[k]);
            const u1 = a.clone().cross(b).normalize(), u2 = a.clone().cross(c).normalize();
            let best = null, far = -1;
            for (const u of [u1.clone().add(u2), u1.clone().sub(u2), u2.clone().sub(u1), u1.clone().add(u2).negate()]) {
                if (u.lengthSq() < 1e-6) continue;
                const p = at(u.normalize(), RING_R);
                const r = p && centre ? Math.hypot(p[0] - centre[0], p[1] - centre[1]) : -1;
                if (r > far) { far = r; best = p; }
            }
            out.grips[name] = best;
        }
        return out;
    }

    // ── a handle dragged ──────────────────────────────────────────────────

    // Along the line through `pivot` in `axis`: the place nearest the ray
    // under the cursor (null when the axis points at the camera).
    _s3dAxisParam(clientX, clientY, pivot, axis) {
        const ray = this._s3dRayAt(clientX, clientY);
        if (!ray) return null;
        const w0 = pivot.clone().sub(ray.origin);
        const b = axis.dot(ray.direction);
        const den = 1 - b * b;
        if (den < 1e-4) return null;
        return (b * ray.direction.dot(w0) - axis.dot(w0)) / den;
    }

    _s3dHandleStart(n) {
        const st = this._s3dState();
        const T = st.T;
        const h = st.handles;
        const pose = this._s3dHandlesPose();
        if (!h || !pose) return;
        const layers = ((this.project && this.project.layers) || []).filter(l => pose.ids.includes(l.id));
        const movers = layers.filter(l => !this._layerLocked(l));
        const held = layers.filter(l => this._layerLocked(l));
        if (held.length) this._showLockedError(held);
        const layout = this._s3dLayout();
        const starts = new Map(movers.map(l => [l.id, this._s3dPlacementOf(l, layout)]));
        const handle = n.handle;
        const d = {
            kind: 'handle', handle, pivot: pose.pivot.clone(), movers, held, starts, active: true,
            delta: [0, 0, 0], primaryId: starts.has(pose.primaryId) ? pose.primaryId : (movers[0] ? movers[0].id : null),
            next: null, snapped: false,
        };
        if (handle.kind === 'axis') {
            d.axis = h.parts[handle.name].dir.clone();
            d.t0 = this._s3dAxisParam(n.x, n.y, d.pivot, d.axis);
        } else if (handle.kind === 'plane') {
            // on the plane of the square, or (G unlocked) the plane facing the view
            d.normal = handle.name === 'view' ? st.camera.getWorldDirection(new T.Vector3())
                : h.parts[handle.name].normal.clone();
            d.plane = new T.Plane().setFromNormalAndCoplanarPoint(d.normal, d.pivot);
            const ray = this._s3dRayAt(n.x, n.y);
            d.p0 = ray && Math.abs(ray.direction.dot(d.normal)) > 0.1 ? ray.intersectPlane(d.plane, new T.Vector3()) : null;
        } else {
            d.axis = pose.axes[handle.name].clone();
            d.angle = 0;
            const ray = this._s3dRayAt(n.x, n.y);
            const plane = new T.Plane().setFromNormalAndCoplanarPoint(d.axis, d.pivot);
            const p0 = ray && Math.abs(ray.direction.dot(d.axis)) > 0.15 ? ray.intersectPlane(plane, new T.Vector3()) : null;
            if (p0) {
                d.plane = plane;
                d.v0 = p0.sub(d.pivot);
            } else {
                // Seen edge on, the ring is a line on the page: travel along
                // it turns, a ring's radius of travel a radian.
                const g = (handle.point || d.pivot).clone();
                const tangent = d.axis.clone().cross(g.clone().sub(d.pivot)).normalize();
                const a = this._s3dDebugWhere(g.toArray());
                const b = this._s3dDebugWhere(g.clone().add(tangent.multiplyScalar(this._s3dPxToWorld(g) * 20)).toArray());
                const L = a && b ? [b[0] - a[0], b[1] - a[1]] : [1, 0];
                const len = Math.hypot(L[0], L[1]) || 1;
                d.line = [L[0] / len, L[1] / len];
            }
            const p = starts.get(d.primaryId);
            d.startAngle = p ? Number(p[handle.name]) || 0 : 0;
        }
        h.drag = d;
        st.drag = d;
        this._s3dRequestRender();
    }

    _s3dHandleMove(n, ev) {
        const st = this._s3dState();
        const T = st.T;
        const d = st.drag;
        if (!d || d.kind !== 'handle') return;
        const snap = ev.ctrlKey || ev.metaKey;
        let text = '';
        if (d.handle.kind === 'axis') {
            if (d.t0 === null) return;
            const t = this._s3dAxisParam(ev.clientX, ev.clientY, d.pivot, d.axis);
            if (t === null) return;
            let dist = t - d.t0;
            if (snap) dist = this._s3dSnapLength(dist);
            d.delta = d.axis.toArray().map(c => c * dist);
            for (const [id, p] of d.starts) {
                const e = st.entries.get(id);
                if (e) e.obj.position.set(p.x + d.delta[0], p.y + d.delta[1], p.z + d.delta[2]);
            }
            text = `${d.handle.name.toUpperCase()} ${this._s3dSignedLength(dist)}`;
        } else if (d.handle.kind === 'plane') {
            if (!d.p0) return;
            const ray = this._s3dRayAt(ev.clientX, ev.clientY);
            const p = ray ? ray.intersectPlane(d.plane, new T.Vector3()) : null;
            if (!p) return;
            let v = p.sub(d.p0).toArray();
            if (snap) v = v.map(c => this._s3dSnapLength(c));
            this._s3dHandleShift(d, v);
            text = ['X', 'Y', 'Z'].filter((_, i) => Math.abs(v[i]) > 1e-6)
                .map(name => `${name} ${this._s3dSignedLength(v['XYZ'.indexOf(name)])}`).join(', ') || 'X +0 in';
        } else {
            if (d.plane) {
                const ray = this._s3dRayAt(ev.clientX, ev.clientY);
                const p = ray ? ray.intersectPlane(d.plane, new T.Vector3()) : null;
                if (p) {
                    const v = p.sub(d.pivot);
                    if (v.lengthSq() > 1e-6 && d.v0.lengthSq() > 1e-6) {
                        const cross = new T.Vector3().crossVectors(d.v0, v).dot(d.axis);
                        d.angle += Math.atan2(cross, d.v0.dot(v)) / DEG;
                        d.v0 = v;
                    }
                }
            } else {
                d.angle = ((ev.clientX - n.x) * d.line[0] + (ev.clientY - n.y) * d.line[1]) / RING_R / DEG;
            }
            let turn = d.angle;
            if (snap) turn = Math.round((d.startAngle + turn) / 15) * 15 - d.startAngle;
            this._s3dTurnPreview(d, turn);
            text = `${ANGLE_NAMES[d.handle.name]} ${this._s3dAngleText(d.startAngle + turn)}`;
        }
        this._s3dLiveFields(d);
        this._s3dReadout(text, ev.clientX, ev.clientY);
        this._s3dRequestRender();
    }

    // Every screen of the drag carried `v` (stage mm) along.
    _s3dHandleShift(d, v) {
        const st = this._s3dState();
        d.delta = v.map(c => c);
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (e) e.obj.position.set(p.x + d.delta[0], p.y + d.delta[1], p.z + d.delta[2]);
        }
    }

    // Every screen of the drag turned `turnDeg` round the ring's axis
    // through the drag's centre: the screen the ring belongs to changes
    // only that angle; the others turn with it as one piece.
    _s3dTurnPreview(d, turnDeg) {
        const st = this._s3dState();
        const half = turnDeg * DEG / 2;
        const a = d.axis;
        const dq = [a.x * Math.sin(half), a.y * Math.sin(half), a.z * Math.sin(half), Math.cos(half)];
        const c = d.pivot;
        d.turn = turnDeg;
        d.next = new Map();
        for (const [id, p] of d.starts) {
            const rel = quatRotate(dq, [p.x - c.x, p.y - c.y, p.z - c.z]);
            const out = { ...p, x: c.x + rel[0], y: c.y + rel[1], z: c.z + rel[2] };
            if (id === d.primaryId) {
                out[d.handle.name] = p[d.handle.name] + turnDeg;
            } else {
                const ang = anglesFromQuat(quatMul(dq, quatFromPlacement(p)));
                out.pitch = ang.pitch; out.yaw = ang.yaw; out.roll = ang.roll;
            }
            d.next.set(id, out);
            const e = st.entries.get(id);
            if (e) {
                e.obj.position.set(out.x, out.y, out.z);
                e.obj.rotation.set(out.pitch * DEG, out.yaw * DEG, out.roll * DEG, 'YXZ');
            }
        }
    }

    _s3dHandleEnd(cancelled) {
        const st = this._s3dState();
        const d = st.drag;
        st.drag = null;
        if (st.handles) st.handles.drag = null;
        if (!d || d.kind !== 'handle') return;
        const ring = d.handle.kind === 'ring';
        const moved = !ring ? d.delta.some(v => v !== 0) : !!(d.next && d.turn);
        if (cancelled || !moved || !d.movers.length) {
            this._s3dRevertPreview(d);
            return;
        }
        const changed = [];
        for (const layer of d.movers) {
            const p = d.starts.get(layer.id);
            if (!p) continue;
            let out;
            if (!ring) {
                out = { ...p, x: p.x + d.delta[0], y: p.y + d.delta[1], z: p.z + d.delta[2] };
            } else {
                out = d.next.get(layer.id);
            }
            const placed = s3dSanitize(out);
            ['x', 'y', 'z'].forEach(k => { placed[k] = round(placed[k], 3); });
            ['pitch', 'yaw', 'roll'].forEach(k => { placed[k] = round(wrap180(placed[k]), 6); });
            layer.stage3d = placed;
            changed.push(layer);
        }
        const action = !ring ? 'Move Screen (3D)' : 'Rotate Screen (3D)';
        sendClientLog('stage3d_handle', {
            handle: d.handle.name, ids: changed.map(l => l.id),
            delta: !ring ? d.delta : d.turn,
        });
        this.updateLayers(changed, true, action);
        this._s3dSchedule();
        this._s3dRefreshPanel(true);
    }

    // ── G and R: move and turn from the keyboard ──────────────────────────

    // G ('move') or R ('rotate') pressed on the 3D tab with screens picked.
    _s3dKeyTransformStart(kind) {
        const st = this._s3dState();
        if (!st.T || !st.renderer || st.keyX || st.nav || st.drag) return false;
        this._s3dHandlesFrame();
        if (!this._s3dHandlesPose()) return false;
        const rect = st.renderer.domElement.getBoundingClientRect();
        const pt = st.pointer && st.pointer.x >= rect.left && st.pointer.x <= rect.right
            && st.pointer.y >= rect.top && st.pointer.y <= rect.bottom
            ? st.pointer : { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        const k = {
            kind: kind === 'rotate' ? 'rotate' : 'move', axis: null, typed: '',
            x0: pt.x, y0: pt.y, last: { clientX: pt.x, clientY: pt.y, shiftKey: false, ctrlKey: false, metaKey: false },
        };
        st.keyX = k;
        k.onMove = (ev) => {
            k.last = { clientX: ev.clientX, clientY: ev.clientY, shiftKey: ev.shiftKey, ctrlKey: ev.ctrlKey, metaKey: ev.metaKey };
            if (!k.typed) this._s3dKeyXFollow();
        };
        k.onDown = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            this._s3dKeyTransformEnd(ev.button !== 0);
        };
        k.onMenu = (ev) => { ev.preventDefault(); ev.stopPropagation(); };
        k.onKey = (ev) => this._s3dKeyXKey(ev);
        window.addEventListener('pointermove', k.onMove, true);
        window.addEventListener('pointerdown', k.onDown, true);
        window.addEventListener('contextmenu', k.onMenu, true);
        window.addEventListener('keydown', k.onKey, true);
        this._s3dKeyXBegin();
        sendClientLog('stage3d_key_transform', { kind: k.kind });
        return true;
    }

    // The gesture as a handle's drag from where it started: G unlocked on
    // the plane facing the view, locked along its axis; R on the ring of
    // the locked angle (yaw unlocked), turned by sideways travel.
    _s3dKeyXBegin() {
        const st = this._s3dState();
        const k = st.keyX;
        const handle = k.kind === 'move'
            ? (k.axis ? { kind: 'axis', name: k.axis } : { kind: 'plane', name: 'view' })
            : { kind: 'ring', name: KEY_AXES[k.axis] || 'yaw' };
        this._s3dHandleStart({ handle, x: k.x0, y: k.y0 });
        const d = st.drag;
        if (d && handle.kind === 'ring') {
            d.plane = null;
            d.line = [1, 0];
        }
        if (k.typed) this._s3dKeyXTyped();
        else this._s3dKeyXFollow();
    }

    _s3dKeyXFollow() {
        const st = this._s3dState();
        const k = st.keyX;
        if (!k || !st.drag) return;
        this._s3dHandleMove({ x: k.x0, y: k.y0 }, k.last);
        this._s3dKeyXSay();
    }

    // A typed figure: the move in the panel's units, the turn in degrees.
    _s3dKeyXTyped() {
        const st = this._s3dState();
        const k = st.keyX;
        const d = st.drag;
        if (!k || !d) return;
        const v = k.typed && k.typed !== '-' ? evaluateMathExpression(k.typed) : 0;
        const n = Number.isFinite(v) ? v : 0;
        if (k.kind === 'move') {
            const mm = n * (this._s3dUnits() === 'm' ? 1000 : FT_MM);
            this._s3dHandleShift(d, d.axis.toArray().map(c => c * mm));
        } else {
            this._s3dTurnPreview(d, n);
        }
        this._s3dLiveFields(d);
        this._s3dRequestRender();
        this._s3dKeyXSay();
    }

    _s3dKeyXSay() {
        const st = this._s3dState();
        const k = st.keyX;
        const d = st.drag;
        if (!k || !d) return;
        const lock = k.kind === 'move' ? (k.axis ? k.axis.toUpperCase() : 'free')
            : ({ pitch: 'Pitch', yaw: 'Yaw', roll: 'Roll' })[KEY_AXES[k.axis] || 'yaw'];
        let what;
        if (k.kind === 'move') {
            const i = k.axis ? 'xyz'.indexOf(k.axis) : -1;
            what = i >= 0 ? this._s3dSignedLength(d.delta[i]) : d.delta.map(v => this._s3dSignedLength(v)).join(', ');
        } else {
            what = `${round(d.turn || 0, 2)}°`;
        }
        const typed = k.typed ? ` (typed ${k.typed})` : '';
        this._s3dReadout(`${k.kind === 'move' ? 'Move' : 'Turn'} ${lock}: ${what}${typed}. Enter keeps it, Esc puts it back.`,
            k.last.clientX, k.last.clientY);
    }

    _s3dKeyXKey(ev) {
        const st = this._s3dState();
        const k = st.keyX;
        if (!k) return;
        const key = ev.key || '';
        if (/^(Shift|Control|Alt|Meta|OS|CapsLock)$/.test(key)) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (key === 'Escape') { this._s3dKeyTransformEnd(true); return; }
        if (key === 'Enter') { this._s3dKeyTransformEnd(false); return; }
        const letter = key.length === 1 ? key.toLowerCase() : '';
        if (KEY_AXES[letter] !== undefined) {
            k.axis = k.axis === letter ? null : letter;
            this._s3dKeyXRestart();
            return;
        }
        if (key === 'Backspace') {
            k.typed = k.typed.slice(0, -1);
        } else if (/^[0-9.+\-*/]$/.test(key)) {
            k.typed += key;
            // a figure moves along an axis: X until another is locked
            if (k.kind === 'move' && !k.axis) {
                k.axis = 'x';
                this._s3dKeyXRestart();
                return;
            }
        } else {
            return;
        }
        if (k.typed) this._s3dKeyXTyped();
        else this._s3dKeyXFollow();
    }

    // A new lock: the preview back where it started, then begun again.
    _s3dKeyXRestart() {
        const st = this._s3dState();
        const d = st.drag;
        st.drag = null;
        if (st.handles) st.handles.drag = null;
        if (d) this._s3dRevertPreview(d);
        this._s3dKeyXBegin();
    }

    _s3dKeyTransformEnd(cancelled) {
        const st = this._s3dState();
        const k = st.keyX;
        if (!k) return;
        st.keyX = null;
        window.removeEventListener('pointermove', k.onMove, true);
        window.removeEventListener('pointerdown', k.onDown, true);
        window.removeEventListener('keydown', k.onKey, true);
        // the right-click's own menu event comes after its press
        setTimeout(() => window.removeEventListener('contextmenu', k.onMenu, true), 300);
        this._s3dReadout(null);
        sendClientLog('stage3d_key_transform_end', { kind: k.kind, axis: k.axis, typed: k.typed, cancelled: !!cancelled });
        this._s3dHandleEnd(!!cancelled);
    }

    // ── snapping and the figures shown ────────────────────────────────────

    _s3dSnapStep() {
        return this._s3dUnits() === 'm' ? 100 : 152.4;
    }

    _s3dSnapLength(mm) {
        const step = this._s3dSnapStep();
        return round(Math.round(mm / step) * step, 3);
    }

    // A signed distance in the show's units: "+2 ft 6 in", "-0.75 m".
    _s3dSignedLength(mm) {
        const v = Number(mm) || 0;
        const sign = v < 0 ? '-' : '+';
        if (this._s3dUnits() === 'm') {
            return `${sign}${String(round(Math.abs(v) / 1000, 3))} m`;
        }
        const quarters = Math.round(Math.abs(v) / 25.4 * 4);
        const ft = Math.floor(quarters / 48);
        const inch = (quarters - ft * 48) / 4;
        if (!ft) return `${sign}${inch} in`;
        return inch ? `${sign}${ft} ft ${inch} in` : `${sign}${ft} ft`;
    }

    _s3dAngleText(deg) {
        return `${round(wrap180(deg), 1)}°`;
    }

    // The panel's fields follow the screen it shows while a drag or a
    // nudge runs (the one being typed in is left alone).
    _s3dLiveFields(d) {
        const layer = this._s3dCurrentScreen();
        if (!layer || !d || !d.starts || !d.starts.has(layer.id)) return;
        const start = d.starts.get(layer.id);
        const p = this._s3dShownOf(layer, d.next && d.next.has(layer.id) ? d.next.get(layer.id)
            : { ...start, x: start.x + d.delta[0], y: start.y + d.delta[1], z: start.z + d.delta[2] });
        const set = (id, value) => {
            const el = document.getElementById(id);
            if (el && document.activeElement !== el && el.value !== value) el.value = value;
        };
        set('s3d-x', this._s3dFormatLength(p.x));
        set('s3d-y', this._s3dFormatLength(p.y));
        set('s3d-z', this._s3dFormatLength(p.z));
        set('s3d-pitch', String(round(wrap180(p.pitch), 2)));
        set('s3d-yaw', String(round(wrap180(p.yaw), 2)));
        set('s3d-roll', String(round(wrap180(p.roll), 2)));
    }

    // ── nudges ────────────────────────────────────────────────────────────

    // A stage axis for a direction on the page: the floor axis nearest to
    // where the view faces (or to its right), so a nudge keeps the screens
    // square to the stage.
    _s3dFloorAxis(v) {
        const st = this._s3dState();
        const T = st.T;
        if (Math.abs(v.x) < 1e-9 && Math.abs(v.z) < 1e-9) return null;
        return Math.abs(v.x) >= Math.abs(v.z)
            ? new T.Vector3(Math.sign(v.x), 0, 0) : new T.Vector3(0, 0, Math.sign(v.z));
    }

    _s3dNudgeKey(ev) {
        const st = this._s3dState();
        const T = st.T;
        if (!T || st.nav) return;
        const sel = [...this._s3dSelectedIds()];
        if (!sel.length) return;
        const cam = st.camera;
        cam.updateMatrixWorld();
        const fwd = cam.getWorldDirection(new T.Vector3());
        // Looking straight across, the page's up is the stage's up: use it
        // for the floor only when the view looks down or up enough.
        let ahead = new T.Vector3(fwd.x, 0, fwd.z);
        if (ahead.length() < 0.2) {
            const up = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
            ahead = new T.Vector3(up.x, 0, up.z);
        }
        const right = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
        const fwdAxis = this._s3dFloorAxis(ahead) || new T.Vector3(0, 0, -1);
        const rightAxis = this._s3dFloorAxis(right) || new T.Vector3(1, 0, 0);
        const dirs = {
            ArrowUp: fwdAxis, ArrowDown: fwdAxis.clone().negate(),
            ArrowRight: rightAxis, ArrowLeft: rightAxis.clone().negate(),
            PageUp: new T.Vector3(0, 1, 0), PageDown: new T.Vector3(0, -1, 0),
        };
        const dir = dirs[ev.key];
        if (!dir) return;
        const metric = this._s3dUnits() === 'm';
        const step = ev.shiftKey ? (metric ? 100 : 152.4) : (metric ? 10 : 25.4);
        let d = st.nudge;
        if (!d) {
            const layout = this._s3dLayout();
            const moveSet = this._s3dMoveSet(sel);
            const movers = moveSet.filter(l => !this._layerLocked(l));
            const held = moveSet.filter(l => this._layerLocked(l));
            if (held.length) this._showLockedError(held);
            d = {
                kind: 'nudge', active: true, movers, held, delta: [0, 0, 0],
                starts: new Map(movers.map(l => [l.id, this._s3dPlacementOf(l, layout)])),
            };
            st.nudge = d;
            st.drag = d;
        }
        if (!d.movers.length) return;
        d.delta = d.delta.map((v, i) => round(v + dir.getComponent(i) * step, 3));
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (e) e.obj.position.set(p.x + d.delta[0], p.y + d.delta[1], p.z + d.delta[2]);
        }
        this._s3dLiveFields(d);
        const parts = [];
        ['X', 'Y', 'Z'].forEach((name, i) => { if (d.delta[i]) parts.push(`${name} ${this._s3dSignedLength(d.delta[i])}`); });
        const pose = this._s3dHandlesPose();
        const at = pose ? this._s3dDebugWhere(pose.pivot.toArray()) : null;
        if (at) this._s3dReadout(parts.join(', ') || 'X +0 in', at[0] + 40, at[1] + 40);
        clearTimeout(d.timer);
        d.timer = setTimeout(() => this._s3dNudgeCommit(), NUDGE_SETTLE_MS);
        this._s3dRequestRender();
    }

    // The burst of nudges under way lands as one undo step.
    _s3dNudgeCommit() {
        const st = this._s3dState();
        const d = st.nudge;
        if (!d) return;
        clearTimeout(d.timer);
        st.nudge = null;
        if (st.drag === d) st.drag = null;
        this._s3dReadout(null);
        this._s3dCommitMove(d);
    }
}

for (const k of Object.getOwnPropertyNames(_Stage3DHandles.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Stage3DHandles.prototype, k));
    }
}
