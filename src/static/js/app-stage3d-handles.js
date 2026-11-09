// app-stage3d-handles: the move and turn handles on the 3D tab's selection,
// snapping, and the arrow-key nudges (the owner's ruling, 2026-11-08: "we
// need to be able to manipulate screens easily too").
//
// The selected screens (and the rest of each one's group) carry one set of
// handles at their centre - a lone screen's own centre, several screens'
// combined one:
//
//   Move (W)     an arrow per stage axis, X red, Y green, Z blue; a drag
//                slides the screens along that axis only
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
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import {
    DEG, FT_MM, round, wrap180, quatFromPlacement, quatMul, quatRotate, anglesFromQuat, s3dSanitize,
} from './app-stage3d.js';

const RED = 0xe5484d, GREEN = 0x4cbb5a, BLUE = 0x3d7ef2, HOT = 0xffd200;
const AXES = { x: [1, 0, 0, RED], y: [0, 1, 0, GREEN], z: [0, 0, 1, BLUE] };
const RINGS = { pitch: RED, yaw: GREEN, roll: BLUE };
const ANGLE_NAMES = { pitch: 'Pitch', yaw: 'Yaw', roll: 'Roll' };
// Sizes on the page, px.
const SHAFT_FROM = 24, SHAFT_TO = 92, TIP = 22, SHAFT_R = 1.8, TIP_R = 7, ARROW_PICK_R = 10;
const RING_R = 86, RING_TUBE = 1.8, RING_PICK = 9;
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

    // The handles' centre and the three turn axes, from the screens as
    // drawn now (a drag holds its own centre). Null with nothing to carry.
    _s3dHandlesPose() {
        const st = this._s3dState();
        const h = st.handles;
        if (!h || !st.active) return null;
        const T = st.T;
        const entries = h.ids.map(id => st.entries.get(id)).filter(Boolean);
        if (!entries.length) return null;
        const primary = entries.find(e => this.currentLayer && e.id === this.currentLayer.id) || entries[0];
        let pivot;
        if (h.drag) {
            pivot = h.drag.pivot.clone();
        } else if (entries.length === 1) {
            pivot = primary.obj.position.clone();
        } else {
            const box = new T.Box3();
            entries.forEach(e => { e.obj.updateMatrixWorld(true); if (e.front) box.expandByObject(e.front); });
            pivot = box.isEmpty() ? primary.obj.position.clone() : box.getCenter(new T.Vector3());
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
        const out = { shown: true, ids: pose.ids, tool: st.tool === 'rotate' ? 'rotate' : 'move', centre: at(new st.T.Vector3(), 0), grips: {} };
        // A point on each handle a person would grab: an arrow's shaft two
        // thirds out, a ring's far side from the camera's right.
        for (const name of Object.keys(AXES)) {
            const p = h.parts[name];
            if (Math.abs(p.dir.dot(st.camera.getWorldDirection(new st.T.Vector3()))) < 0.97) {
                out.grips[name] = at(p.dir, SHAFT_FROM + (SHAFT_TO - SHAFT_FROM) * 0.66);
            }
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
        const moved = d.handle.kind === 'axis' ? d.delta.some(v => v !== 0) : !!(d.next && d.turn);
        if (cancelled || !moved || !d.movers.length) {
            this._s3dRevertPreview(d);
            return;
        }
        const changed = [];
        for (const layer of d.movers) {
            const p = d.starts.get(layer.id);
            if (!p) continue;
            let out;
            if (d.handle.kind === 'axis') {
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
        const action = d.handle.kind === 'axis' ? 'Move Screen (3D)' : 'Rotate Screen (3D)';
        sendClientLog('stage3d_handle', {
            handle: d.handle.name, ids: changed.map(l => l.id),
            delta: d.handle.kind === 'axis' ? d.delta : d.turn,
        });
        this.updateLayers(changed, true, action);
        this._s3dSchedule();
        this._s3dRefreshPanel(true);
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
        const p = d.next && d.next.has(layer.id) ? d.next.get(layer.id)
            : { ...start, x: start.x + d.delta[0], y: start.y + d.delta[1], z: start.z + d.delta[2] };
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
