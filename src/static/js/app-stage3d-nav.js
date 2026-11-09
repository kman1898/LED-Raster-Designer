// app-stage3d-nav: getting around the 3D tab, and picking screens in it.
//
// Standard 3D navigation (the owner's ruling, 2026-11-08: "the 3D interface
// needs to work like other 3D model software"):
//
//   middle-drag          orbit, round the point under the cursor when the
//                        press lands on a screen (else the view's centre),
//                        so what is grabbed stays put
//   Shift+middle-drag    pan; right-drag pans too
//   wheel                zoom toward the point under the cursor
//   Alt+drag             orbit, Alt+Shift+drag pan (a mouse with no middle
//                        button)
//   trackpad             two-finger drag orbits, Shift pans, pinch zooms
//                        toward the pointer
//   left                 select (Shift or Ctrl / Cmd adds), drag on empty
//                        space or an unselected screen to box-select, drag
//                        a selected screen to move it (Shift: up and down),
//                        double-click a screen to focus on it. A left press
//                        never moves the camera.
//   keys                 F frames the selection (every screen with none),
//                        Home goes back to the starting view, 1 to 6 are
//                        the view buttons, W and E pick the move or turn
//                        handles, the arrows and Page Up / Down nudge
//                        (app-stage3d-handles.js), Esc cancels a drag.
//
// The orbit controls (static/vendor/three) keep touch only; the mouse and
// the wheel never reach them. Every camera move is view state: saved with
// the show (_s3dSaveCameraSoon), never an undo step. Frame, focus, Home and
// the view buttons glide there over a short moment; a person who asks for
// less motion gets the jump.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog, isTypingTarget } from './helpers.js';
import { DEG } from './app-stage3d.js';

const DRAG_PX = 4;               // a press that travels this far is a drag
const GLIDE_MS = 320;            // frame, focus, Home and the view buttons
const NEAR_MM = 150;             // the wheel stops this close to what it nears
const FAR_MM = 400000;           // and backs off no further than this
const PAD_GAP_MS = 250;          // trackpad events closer than this are one gesture
const VIEW_KEYS = ['front', 'back', 'left', 'right', 'top', 'iso'];

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

class _Stage3DNav {
    // ── wiring ────────────────────────────────────────────────────────────

    _s3dWireViewport(view) {
        if (!view) return;
        // Capture: these run before the orbit controls hear anything.
        view.addEventListener('pointerdown', (ev) => this._s3dPointerDown(ev), true);
        // The middle button's own browser habits (autoscroll, paste) stay out.
        view.addEventListener('mousedown', (ev) => { if (ev.button === 1) ev.preventDefault(); }, true);
        view.addEventListener('auxclick', (ev) => { if (ev.button === 1) ev.preventDefault(); }, true);
        view.addEventListener('wheel', (ev) => this._s3dWheel(ev), { capture: true, passive: false });
        view.addEventListener('dblclick', (ev) => this._s3dDoubleClick(ev));
        view.addEventListener('contextmenu', (ev) => this._s3dContextMenu(ev), true);
        window.addEventListener('pointermove', (ev) => this._s3dPointerMove(ev));
        window.addEventListener('pointerup', (ev) => this._s3dPointerUp(ev, false));
        window.addEventListener('pointercancel', (ev) => this._s3dPointerUp(ev, true));
        window.addEventListener('keydown', (ev) => this._s3dKeyDown(ev), true);
        window.addEventListener('blur', () => this._s3dCancelDrag());
    }

    _s3dCanvasRect() {
        const st = this._s3dState();
        return st.renderer ? st.renderer.domElement.getBoundingClientRect() : null;
    }

    _s3dRayAt(clientX, clientY) {
        const st = this._s3dState();
        const rect = this._s3dCanvasRect();
        if (!rect || !rect.width || !rect.height) return null;
        const ndc = new st.T.Vector2(((clientX - rect.left) / rect.width) * 2 - 1,
            -((clientY - rect.top) / rect.height) * 2 + 1);
        st.camera.updateMatrixWorld();
        st.raycaster.setFromCamera(ndc, st.camera);
        return st.raycaster.ray.clone();
    }

    // A field being typed in lets go when the view is pressed, the way any
    // press elsewhere takes the focus: its change commits, and the view's
    // keys answer again. (The middle and right buttons do not move focus
    // by themselves, and their press is held back from the browser.)
    _s3dReleaseField() {
        const el = document.activeElement;
        if (el && el !== document.body && isTypingTarget(el) && typeof el.blur === 'function') el.blur();
    }

    _s3dViewClass(name, on) {
        const view = document.getElementById('s3d-view');
        if (view) view.classList.toggle(name, !!on);
    }

    // ── the press ─────────────────────────────────────────────────────────

    _s3dPointerDown(ev) {
        const st = this._s3dState();
        if (!st.renderer || !st.active || st.nav) return;
        this._s3dNudgeCommit();
        this._s3dEndCameraMove(true);
        const touch = ev.pointerType === 'touch';
        const camera = !touch && (ev.button === 1 || ev.button === 2 || (ev.button === 0 && ev.altKey));
        if (camera) {
            ev.preventDefault();
            this._s3dReleaseField();
            this._s3dStartCamera(ev, (ev.button === 2 || ev.shiftKey) ? 'pan' : 'orbit');
            return;
        }
        if (ev.button !== 0) return;
        const handle = this._s3dHandlePick(ev.clientX, ev.clientY);
        const hit = this._s3dPick(ev.clientX, ev.clientY);
        const n = {
            kind: 'press', id: ev.pointerId, x: ev.clientX, y: ev.clientY, lastX: ev.clientX, lastY: ev.clientY,
            moved: false, hit, handle, touch, shift: ev.shiftKey, mod: ev.ctrlKey || ev.metaKey,
        };
        st.nav = n;
        if (handle) {
            // A press on a handle drags it; a click on one (no travel) is a
            // click on what lies under it.
            st.controls.enabled = false;
        } else if (hit && this._s3dSelectedIds().has(hit.layerId) && !n.mod) {
            this._s3dArmBodyMove(hit, ev.shiftKey);
        } else if (!touch) {
            // A left press never moves the camera: a drag from here draws a
            // selection box.
            st.controls.enabled = false;
        }
        // Touch on empty space or an unselected screen is the orbit
        // controls' own (one finger orbits), as before.
        if (!touch) {
            try { st.renderer.domElement.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
        }
    }

    // A press on a selected screen: the drag that may follow moves every
    // selected screen (and the rest of each one's group) on the floor, or
    // up and down with Shift. Locked screens stay put and are named once
    // the press becomes a drag.
    _s3dArmBodyMove(hit, vertical) {
        const st = this._s3dState();
        const T = st.T;
        st.controls.enabled = false;
        const layout = this._s3dLayout();
        const sel = this._s3dSelectedIds();
        const moveSet = this._s3dMoveSet(sel.size ? [...sel] : [hit.layerId]);
        const movers = moveSet.filter(l => !this._layerLocked(l));
        const held = moveSet.filter(l => this._layerLocked(l));
        const starts = new Map(movers.map(l => [l.id, this._s3dPlacementOf(l, layout)]));
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
            kind: 'move', plane: new T.Plane().setFromNormalAndCoplanarPoint(normal, hit.point),
            from: hit.point.clone(), vertical, movers, held, starts, active: false, delta: [0, 0, 0],
        };
    }

    // ── the drag ──────────────────────────────────────────────────────────

    _s3dPointerMove(ev) {
        const st = this._s3dState();
        const n = st.nav;
        if (!n) {
            if (st.active && st.renderer && ev.target === st.renderer.domElement) {
                this._s3dHandlesHover(ev.clientX, ev.clientY);
            }
            return;
        }
        if (n.id !== undefined && ev.pointerId !== undefined && ev.pointerId !== n.id) return;
        const dx = ev.clientX - n.lastX, dy = ev.clientY - n.lastY;
        n.lastX = ev.clientX;
        n.lastY = ev.clientY;
        if (!n.moved && Math.hypot(ev.clientX - n.x, ev.clientY - n.y) > DRAG_PX) n.moved = true;
        if (n.kind === 'orbit') {
            this._s3dOrbitBy(dx, dy, n.pivot);
            return;
        }
        if (n.kind === 'pan') {
            this._s3dPanBy(dx, dy, n.depth);
            return;
        }
        if (n.kind === 'press') {
            if (!n.moved) return;
            if (n.handle) {
                n.kind = 'handle';
                this._s3dHandleStart(n);
            } else if (st.drag && st.drag.kind === 'move') {
                n.kind = 'move';
            } else if (n.touch) {
                n.kind = 'touch';
            } else {
                n.kind = 'box';
            }
        }
        if (n.kind === 'handle') this._s3dHandleMove(n, ev);
        else if (n.kind === 'move') this._s3dBodyMove(ev);
        else if (n.kind === 'box') this._s3dBoxMove(n, ev);
    }

    _s3dBodyMove(ev) {
        const st = this._s3dState();
        const d = st.drag;
        if (!d || d.kind !== 'move') return;
        if (!d.active && d.held.length) this._showLockedError(d.held);
        d.active = true;
        const ray = this._s3dRayAt(ev.clientX, ev.clientY);
        const at = ray ? ray.intersectPlane(d.plane, new st.T.Vector3()) : null;
        if (!at) return;
        const delta = at.sub(d.from);
        const snap = ev.ctrlKey || ev.metaKey;
        const s = (v) => (snap ? this._s3dSnapLength(v) : v);
        d.delta = d.vertical ? [0, s(delta.y), 0] : [s(delta.x), 0, s(delta.z)];
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (e) e.obj.position.set(p.x + d.delta[0], p.y + d.delta[1], p.z + d.delta[2]);
        }
        this._s3dLiveFields(d);
        const text = d.vertical
            ? `Y ${this._s3dSignedLength(d.delta[1])}`
            : `X ${this._s3dSignedLength(d.delta[0])}, Z ${this._s3dSignedLength(d.delta[2])}`;
        this._s3dReadout(text, ev.clientX, ev.clientY);
        this._s3dRequestRender();
    }

    _s3dPointerUp(ev, cancelled) {
        const st = this._s3dState();
        const n = st.nav;
        if (!n) return;
        if (n.id !== undefined && ev.pointerId !== undefined && ev.pointerId !== n.id) return;
        st.nav = null;
        try { if (st.renderer) st.renderer.domElement.releasePointerCapture(n.id); } catch (e) { /* not held */ }
        if (st.controls) st.controls.enabled = true;
        this._s3dReadout(null);
        this._s3dViewClass('s3d-orbiting', false);
        this._s3dViewClass('s3d-panning', false);
        this._s3dViewClass('s3d-grab', false);
        this._s3dPivotMark(null);
        if (n.kind === 'orbit' || n.kind === 'pan') {
            if (n.moved) {
                this._s3dSaveCameraSoon();
                sendClientLog('stage3d_camera', { gesture: n.kind, button: n.button });
            } else if (n.button === 2 && !cancelled) {
                // A right click that did not pan: the app's menu, as before.
                if (typeof this.showContextMenu === 'function') this.showContextMenu(ev.clientX, ev.clientY);
            }
            return;
        }
        if (n.kind === 'handle') {
            this._s3dHandleEnd(cancelled);
            return;
        }
        const d = st.drag;
        st.drag = null;
        if (n.kind === 'move') {
            if (d && d.active && !cancelled) this._s3dCommitMove(d);
            else this._s3dRevertPreview(d);
            return;
        }
        if (n.kind === 'box') {
            this._s3dBoxEnd(n, cancelled);
            return;
        }
        if (n.kind === 'press' && !cancelled) this._s3dClick(n.hit, ev);
    }

    // Puts the screens a preview moved back where they stand.
    _s3dRevertPreview(d) {
        const st = this._s3dState();
        if (!d || !d.starts) return;
        const DEGR = Math.PI / 180;
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (!e) continue;
            e.obj.position.set(p.x, p.y, p.z);
            e.obj.rotation.set(p.pitch * DEGR, p.yaw * DEGR, p.roll * DEGR, 'YXZ');
        }
        this._s3dRefreshPanel(true);
        this._s3dRequestRender();
    }

    // Esc, a lost window or leaving the tab: whatever was being dragged goes
    // back to where it started, and nothing is recorded.
    _s3dCancelDrag() {
        const st = this._s3dState();
        const n = st.nav;
        const d = st.drag;
        st.nav = null;
        st.drag = null;
        if (st.handles) st.handles.drag = null;
        const nd = st.nudge;
        if (nd) {
            clearTimeout(nd.timer);
            st.nudge = null;
            if (nd !== d) this._s3dRevertPreview(nd);
        }
        if (d) this._s3dRevertPreview(d);
        if (st.controls) st.controls.enabled = true;
        this._s3dReadout(null);
        this._s3dBoxShow(null);
        this._s3dPivotMark(null);
        ['s3d-orbiting', 's3d-panning', 's3d-grab'].forEach(c => this._s3dViewClass(c, false));
        return !!(d || (n && n.kind !== 'press'));
    }

    // ── orbit, pan, zoom ──────────────────────────────────────────────────

    _s3dStartCamera(ev, kind) {
        const st = this._s3dState();
        const hit = this._s3dPick(ev.clientX, ev.clientY);
        const n = {
            kind, id: ev.pointerId, button: ev.button, x: ev.clientX, y: ev.clientY,
            lastX: ev.clientX, lastY: ev.clientY, moved: false,
        };
        if (kind === 'orbit') {
            n.pivot = hit ? hit.point.clone() : st.controls.target.clone();
            this._s3dPivotMark(n.pivot);
        } else {
            n.depth = hit ? hit.point.clone() : st.controls.target.clone();
        }
        st.nav = n;
        this._s3dViewClass(kind === 'orbit' ? 's3d-orbiting' : 's3d-panning', true);
        try { st.renderer.domElement.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
    }

    // Turn the camera round `pivot`: across by dx (round the vertical) and
    // up or down by dy, as far as straight down or straight up. The pivot
    // keeps its place on the page.
    _s3dOrbitBy(dx, dy, pivot) {
        const st = this._s3dState();
        const T = st.T;
        const cam = st.camera, tgt = st.controls.target;
        const h = (st.renderer && st.renderer.domElement.clientHeight) || 600;
        const Y = new T.Vector3(0, 1, 0);
        const off = cam.position.clone().sub(tgt);
        const len = off.length() || 1;
        const phi = Math.acos(clamp(off.y / len, -1, 1));
        const EPS = 0.0005;
        const dTheta = -2 * Math.PI * dx / h;
        const dPhi = clamp(phi - 2 * Math.PI * dy / h, EPS, Math.PI - EPS) - phi;
        const qYaw = new T.Quaternion().setFromAxisAngle(Y, dTheta);
        const fwd = tgt.clone().sub(cam.position).normalize();
        let right = new T.Vector3().crossVectors(fwd, Y);
        if (right.lengthSq() < 1e-12) {
            cam.updateMatrixWorld();
            right = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
        }
        right.normalize().applyQuaternion(qYaw);
        const q = new T.Quaternion().setFromAxisAngle(right, dPhi).multiply(qYaw);
        const p = pivot || tgt.clone();
        cam.position.sub(p).applyQuaternion(q).add(p);
        tgt.sub(p).applyQuaternion(q).add(p);
        cam.up.set(0, 1, 0);
        cam.lookAt(tgt);
        cam.updateMatrixWorld();
        this._s3dRequestRender();
    }

    // Slide the camera and its centre across the view, by dx, dy page px
    // measured at the depth of `depth`, so what was grabbed follows the
    // cursor.
    _s3dPanBy(dx, dy, depth) {
        const st = this._s3dState();
        const T = st.T;
        const cam = st.camera, tgt = st.controls.target;
        const h = (st.renderer && st.renderer.domElement.clientHeight) || 600;
        cam.updateMatrixWorld();
        let perPx;
        if (cam.isOrthographicCamera) {
            perPx = (cam.top - cam.bottom) / (cam.zoom || 1) / h;
        } else {
            const fwd = cam.getWorldDirection(new T.Vector3());
            const d = Math.max(1, (depth || tgt).clone().sub(cam.position).dot(fwd));
            perPx = 2 * d * Math.tan(cam.fov * DEG / 2) / h;
        }
        const right = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
        const up = new T.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
        const move = right.multiplyScalar(-dx * perPx).add(up.multiplyScalar(dy * perPx));
        cam.position.add(move);
        tgt.add(move);
        cam.updateMatrixWorld();
        this._s3dRequestRender();
    }

    // Zoom by `scale` (under 1 nears) toward the point under (clientX,
    // clientY): a screen there, or the point at the view centre's depth.
    // That point stays under the cursor.
    _s3dZoomAt(clientX, clientY, scale) {
        const st = this._s3dState();
        const T = st.T;
        const cam = st.camera, tgt = st.controls.target;
        if (!(scale > 0) || scale === 1) return;
        const rect = this._s3dCanvasRect();
        if (!rect || !rect.width) return;
        if (cam.isOrthographicCamera) {
            const ndc = new T.Vector3(((clientX - rect.left) / rect.width) * 2 - 1,
                -((clientY - rect.top) / rect.height) * 2 + 1, 0);
            cam.updateMatrixWorld();
            const before = ndc.clone().unproject(cam);
            cam.zoom = clamp((cam.zoom || 1) / scale, 0.02, 500);
            cam.updateProjectionMatrix();
            const after = ndc.clone().unproject(cam);
            const shift = before.sub(after);
            cam.position.add(shift);
            tgt.add(shift);
        } else {
            const hit = this._s3dPick(clientX, clientY);
            let P = hit ? hit.point.clone() : null;
            if (!P) {
                const ray = this._s3dRayAt(clientX, clientY);
                const fwd = cam.getWorldDirection(new T.Vector3());
                const plane = new T.Plane().setFromNormalAndCoplanarPoint(fwd, tgt);
                P = ray ? ray.intersectPlane(plane, new T.Vector3()) : null;
                if (!P) P = tgt.clone();
            }
            let s = scale;
            const near = cam.position.distanceTo(P);
            if (s < 1 && near * s < NEAR_MM) s = Math.min(1, NEAR_MM / Math.max(near, 1e-6));
            const far = cam.position.distanceTo(tgt);
            if (s > 1 && far * s > FAR_MM) s = Math.max(1, FAR_MM / Math.max(far, 1e-6));
            if (s === 1) return;
            cam.position.sub(P).multiplyScalar(s).add(P);
            tgt.sub(P).multiplyScalar(s).add(P);
        }
        cam.updateMatrixWorld();
        this._s3dRequestRender();
        this._s3dSaveCameraSoon();
    }

    // ── the wheel and the trackpad ────────────────────────────────────────

    // What a wheel event is. A pinch arrives with ctrlKey set (Chromium,
    // Safari and Firefox on a Mac; Ctrl+wheel on a mouse zooms the same
    // way). A mouse wheel moves in lines or pages, or in whole notches the
    // browser reports in its legacy wheelDelta as something other than
    // three times the delta; a trackpad scrolls in fine pixel steps, often
    // sideways. One gesture keeps the kind its first event had.
    _s3dWheelKind(ev) {
        const st = this._s3dState();
        if (ev.ctrlKey) return 'pinch';
        const mode = ev.deltaMode;
        if (mode !== 0) return 'wheel';
        const w = st.wheel;
        const now = performance.now();
        if (w && now - w.at < PAD_GAP_MS && (w.kind === 'pad' || w.kind === 'wheel')) return w.kind;
        if (ev.deltaX && ev.deltaY && !ev.shiftKey) return 'pad';
        const sideways = !ev.deltaY;
        const d = sideways ? ev.deltaX : ev.deltaY;
        const legacy = sideways ? ev.wheelDeltaX : ev.wheelDeltaY;
        if (typeof legacy === 'number' && legacy !== 0) return legacy === -3 * d ? 'pad' : 'wheel';
        if (!ev.shiftKey && sideways) return 'pad';
        return Math.abs(d) >= 50 ? 'wheel' : 'pad';
    }

    _s3dWheel(ev) {
        const st = this._s3dState();
        if (!st.renderer || !st.active) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (st.nav && st.nav.kind !== 'press') return;
        this._s3dEndCameraMove(true);
        const kind = this._s3dWheelKind(ev);
        const h = st.renderer.domElement.clientHeight || 600;
        let dx = ev.deltaX, dy = ev.deltaY;
        if (ev.deltaMode === 1) { dx *= 33; dy *= 33; } else if (ev.deltaMode === 2) { dx *= h; dy *= h; }
        const now = performance.now();
        const fresh = !st.wheel || now - st.wheel.at >= PAD_GAP_MS || st.wheel.kind !== kind;
        if (fresh) {
            st.wheel = { kind, at: now, pivot: null, depth: null };
            if (kind === 'pad') {
                const hit = this._s3dPick(ev.clientX, ev.clientY);
                st.wheel.pivot = hit ? hit.point.clone() : st.controls.target.clone();
                st.wheel.depth = st.wheel.pivot.clone();
            }
            sendClientLog('stage3d_wheel', { kind, mode: ev.deltaMode, dx: ev.deltaX, dy: ev.deltaY });
        }
        st.wheel.at = now;
        if (kind === 'pad') {
            if (ev.shiftKey) this._s3dPanBy(-dx, -dy, st.wheel.depth);
            else this._s3dOrbitBy(-dx, -dy, st.wheel.pivot);
            this._s3dSaveCameraSoon();
            return;
        }
        const d = dy || dx;
        const rate = kind === 'pinch' && Math.abs(d) < 50 ? 0.01 : 0.0015;
        this._s3dZoomAt(ev.clientX, ev.clientY, Math.exp(clamp(d * rate, -1, 1)));
    }

    // ── the right button's menu ───────────────────────────────────────────

    // The browser's menu, and the app's own, wait for the release: a right
    // drag pans and opens nothing; a right click opens the app's menu then
    // (_s3dPointerUp), on a Mac as on Windows.
    _s3dContextMenu(ev) {
        const st = this._s3dState();
        if (!st.active || !st.renderer) return;
        ev.preventDefault();
        ev.stopPropagation();
    }

    // ── box select ────────────────────────────────────────────────────────

    _s3dBoxShow(rect) {
        const view = document.getElementById('s3d-view');
        if (!view) return;
        let box = document.getElementById('s3d-box');
        if (!rect) {
            if (box) box.hidden = true;
            return;
        }
        if (!box) {
            box = document.createElement('div');
            box.id = 's3d-box';
            view.appendChild(box);
        }
        const vr = view.getBoundingClientRect();
        box.hidden = false;
        box.style.left = `${rect.left - vr.left}px`;
        box.style.top = `${rect.top - vr.top}px`;
        box.style.width = `${rect.right - rect.left}px`;
        box.style.height = `${rect.bottom - rect.top}px`;
    }

    _s3dBoxRect(n) {
        return {
            left: Math.min(n.x, n.lastX), top: Math.min(n.y, n.lastY),
            right: Math.max(n.x, n.lastX), bottom: Math.max(n.y, n.lastY),
        };
    }

    _s3dBoxMove(n) {
        this._s3dBoxShow(this._s3dBoxRect(n));
    }

    // Each screen's outline on the page (client px), from its cabinets'
    // corners; null for one wholly behind the camera.
    _s3dScreenRect(e) {
        const st = this._s3dState();
        const rect = this._s3dCanvasRect();
        const pos = e.front && e.front.geometry && e.front.geometry.getAttribute('position');
        if (!rect || !pos) return null;
        e.obj.updateMatrixWorld(true);
        st.camera.updateMatrixWorld();
        const v = new st.T.Vector3();
        let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
        for (let i = 0; i < pos.count; i++) {
            v.fromBufferAttribute(pos, i).applyMatrix4(e.front.matrixWorld).project(st.camera);
            if (v.z > 1 || v.z < -1) continue;
            const x = rect.left + (v.x + 1) / 2 * rect.width, y = rect.top + (1 - v.y) / 2 * rect.height;
            l = Math.min(l, x); r = Math.max(r, x); t = Math.min(t, y); b = Math.max(b, y);
        }
        return Number.isFinite(l) ? { left: l, top: t, right: r, bottom: b } : null;
    }

    // Every screen the box touches is selected; with Shift or Ctrl / Cmd
    // held they join the selection, otherwise they are it (none: nothing).
    _s3dBoxEnd(n, cancelled) {
        const st = this._s3dState();
        this._s3dBoxShow(null);
        if (cancelled) return;
        const box = this._s3dBoxRect(n);
        const caught = [];
        for (const e of st.entries.values()) {
            const r = this._s3dScreenRect(e);
            if (r && r.left <= box.right && r.right >= box.left && r.top <= box.bottom && r.bottom >= box.top) {
                caught.push(e.id);
            }
        }
        const add = n.shift || n.mod;
        const ids = add ? [...this._s3dSelectedIds()] : [];
        caught.forEach(id => { if (!ids.includes(id)) ids.push(id); });
        const primary = add && this.currentLayer && ids.includes(this.currentLayer.id)
            ? this.currentLayer.id : (caught[0] || null);
        st.joint = null;
        sendClientLog('stage3d_box_select', { caught, add, ids });
        this.setSelectedLayersByIds(ids, primary);
        this._s3dRefreshPanel();
    }

    // ── focus and framing ─────────────────────────────────────────────────

    // Double-click a screen: the camera turns to it and frames it.
    _s3dDoubleClick(ev) {
        const st = this._s3dState();
        if (!st.active || !st.renderer || ev.button !== 0 || ev.altKey) return;
        const hit = this._s3dPick(ev.clientX, ev.clientY);
        if (!hit) return;
        sendClientLog('stage3d_focus', { id: hit.layerId });
        this._s3dFit(true, null, { ids: new Set([hit.layerId]), animate: true });
    }

    // F: the selected screens (and the rest of their groups) fill the view,
    // seen from where the camera looks now; every screen with none.
    _s3dFrameSelection() {
        const st = this._s3dState();
        const sel = [...this._s3dSelectedIds()];
        const ids = new Set(this._s3dMoveSet(sel).map(l => l.id).filter(id => st.entries.has(id)));
        sendClientLog('stage3d_frame', { ids: [...ids] });
        this._s3dFit(true, null, { ids: ids.size ? ids : null, animate: true });
    }

    // Home: the view a new show opens with - in perspective, from the
    // audience's left and a little above, every screen in frame.
    _s3dHome() {
        const st = this._s3dState();
        if (!st.T || !st.controls) return;
        if (st.camera === st.ortho) this._s3dSetMode('perspective');
        sendClientLog('stage3d_home', {});
        this._s3dFit(true, new st.T.Vector3(0.35, 0.3, 1), { animate: true });
    }

    // ── the camera's glide ────────────────────────────────────────────────

    _s3dCurrentPose() {
        const st = this._s3dState();
        return {
            position: st.camera.position.clone(), target: st.controls.target.clone(),
            orthoHalf: st.orthoHalf, zoom: st.ortho.zoom,
        };
    }

    _s3dPutPose(p) {
        const st = this._s3dState();
        st.camera.position.copy(p.position);
        st.controls.target.copy(p.target);
        st.orthoHalf = p.orthoHalf;
        st.ortho.zoom = p.zoom;
        st.camera.up.set(0, 1, 0);
        st.camera.lookAt(p.target);
        this._s3dFrameCameras();
        st.controls.update();
        this._s3dRequestRender();
    }

    // Round the centre, not through it: the direction swings the short
    // way round the vertical and over, the distance and zoom scale evenly.
    _s3dLerpPose(a, b, k) {
        const st = this._s3dState();
        const T = st.T;
        const sa = new T.Spherical().setFromVector3(a.position.clone().sub(a.target));
        const sb = new T.Spherical().setFromVector3(b.position.clone().sub(b.target));
        let dTheta = sb.theta - sa.theta;
        while (dTheta > Math.PI) dTheta -= 2 * Math.PI;
        while (dTheta < -Math.PI) dTheta += 2 * Math.PI;
        const geo = (x, y) => (x > 0 && y > 0 ? x * Math.pow(y / x, k) : x + (y - x) * k);
        const s = new T.Spherical(geo(sa.radius, sb.radius), sa.phi + (sb.phi - sa.phi) * k, sa.theta + dTheta * k);
        const target = a.target.clone().lerp(b.target, k);
        return {
            target, position: target.clone().add(new T.Vector3().setFromSpherical(s)),
            orthoHalf: geo(a.orthoHalf, b.orthoHalf), zoom: geo(a.zoom, b.zoom),
        };
    }

    // Take the camera to `pose` ({position, target, orthoHalf, zoom}):
    // gliding when asked (and the person has not asked for less motion),
    // saved with the show when `save`.
    _s3dCameraTo(pose, opts = {}) {
        const st = this._s3dState();
        this._s3dEndCameraMove(false);
        let calm = false;
        try { calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* none */ }
        if (!opts.animate || calm || !st.active) {
            this._s3dPutPose(pose);
            if (opts.save) this._s3dSaveCameraSoon();
            return;
        }
        const g = { from: this._s3dCurrentPose(), to: pose, t0: performance.now(), save: !!opts.save };
        // Lands on time even when the page draws no frames (hidden behind
        // another window).
        g.timer = setTimeout(() => { if (st.glide === g) this._s3dEndCameraMove(true); }, GLIDE_MS + 150);
        st.glide = g;
        const tick = () => {
            if (st.glide !== g) return;
            const k = Math.min(1, (performance.now() - g.t0) / GLIDE_MS);
            if (k >= 1) {
                this._s3dEndCameraMove(true);
                return;
            }
            const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
            this._s3dPutPose(this._s3dLerpPose(g.from, g.to, e));
            requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    // A glide under way lands at its end now; `keepSave` keeps the save it
    // was to make (a project being replaced drops it).
    _s3dEndCameraMove(keepSave = true) {
        const st = this._s3dState();
        const g = st.glide;
        if (!g) return;
        st.glide = null;
        clearTimeout(g.timer);
        this._s3dPutPose(g.to);
        if (keepSave && g.save) this._s3dSaveCameraSoon();
    }

    // ── keys ──────────────────────────────────────────────────────────────

    _s3dDialogOpen() {
        return [...document.querySelectorAll('.modal')]
            .some(m => m.style.display !== 'none' && getComputedStyle(m).display !== 'none');
    }

    _s3dKeyDown(ev) {
        const st = this._s3dState();
        if (!st.active || !st.renderer || ev.defaultPrevented || ev.isComposing) return;
        if (ev.key === 'Escape') {
            if ((st.nav && st.nav.kind !== 'press') || st.nudge) {
                this._s3dCancelDrag();
                ev.preventDefault();
                ev.stopPropagation();
            }
            return;
        }
        // A modifier on its own (Shift for a bigger nudge) is no new key.
        if (/^(Shift|Control|Alt|Meta|OS|CapsLock)$/.test(ev.key || '')) return;
        const nudgeKey =/^(Arrow(Up|Down|Left|Right)|PageUp|PageDown)$/.test(ev.key || '');
        if (!nudgeKey) this._s3dNudgeCommit();
        if (isTypingTarget(document.activeElement) || this._s3dDialogOpen()) return;
        if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
        if (st.nav) return;
        const key = ev.key || '';
        const letter = key.length === 1 ? key.toLowerCase() : '';
        const code = ev.code || '';
        const digit = /^(Digit|Numpad)[1-6]$/.test(code) ? Number(code.slice(-1))
            : (/^[1-6]$/.test(key) && !ev.shiftKey ? Number(key) : 0);
        let act = null;
        if (nudgeKey) act = () => this._s3dNudgeKey(ev);
        else if (letter === 'f') act = () => this._s3dFrameSelection();
        else if (key === 'Home') act = () => this._s3dHome();
        else if (letter === 'w') act = () => this._s3dSetTool('move');
        else if (letter === 'e') act = () => this._s3dSetTool('rotate');
        else if (digit && !ev.shiftKey) act = () => this._s3dPreset(VIEW_KEYS[digit - 1]);
        if (!act) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (ev.repeat && !nudgeKey) return;
        act();
    }

    // ── what the cursor carries ───────────────────────────────────────────

    // The live figure beside the cursor while a drag or a nudge runs (null
    // hides it).
    _s3dReadout(text, clientX, clientY) {
        const view = document.getElementById('s3d-view');
        if (!view) return;
        let el = document.getElementById('s3d-readout');
        if (!text) {
            if (el) el.hidden = true;
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.id = 's3d-readout';
            view.appendChild(el);
        }
        const vr = view.getBoundingClientRect();
        el.textContent = text;
        el.hidden = false;
        el.style.left = `${clamp(clientX - vr.left + 16, 0, Math.max(0, vr.width - 160))}px`;
        el.style.top = `${clamp(clientY - vr.top + 18, 0, Math.max(0, vr.height - 24))}px`;
    }

    // The point an orbit turns round, marked while it turns (null hides).
    _s3dPivotMark(point) {
        const st = this._s3dState();
        const view = document.getElementById('s3d-view');
        if (!view) return;
        let el = document.getElementById('s3d-pivot');
        if (!point) {
            if (el) el.hidden = true;
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.id = 's3d-pivot';
            view.appendChild(el);
        }
        const rect = this._s3dCanvasRect();
        const vr = view.getBoundingClientRect();
        st.camera.updateMatrixWorld();
        const v = point.clone().project(st.camera);
        el.hidden = false;
        el.style.left = `${rect.left - vr.left + (v.x + 1) / 2 * rect.width}px`;
        el.style.top = `${rect.top - vr.top + (1 - v.y) / 2 * rect.height}px`;
    }

    // ── read-only hooks for the tests ─────────────────────────────────────

    // The world point under a page point (a screen, or null) and where a
    // world point is drawn on the page. Change nothing.
    _s3dDebugProbe(clientX, clientY) {
        const hit = this._s3dPick(clientX, clientY);
        return hit ? hit.point.toArray() : null;
    }

    _s3dDebugWhere(point) {
        const st = this._s3dState();
        const rect = this._s3dCanvasRect();
        if (!rect || !st.T) return null;
        st.camera.updateMatrixWorld();
        const v = new st.T.Vector3(point[0], point[1], point[2]).project(st.camera);
        return [rect.left + (v.x + 1) / 2 * rect.width, rect.top + (1 - v.y) / 2 * rect.height];
    }
}

for (const k of Object.getOwnPropertyNames(_Stage3DNav.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Stage3DNav.prototype, k));
    }
}
