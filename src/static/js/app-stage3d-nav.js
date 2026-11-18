// app-stage3d-nav: getting around the 3D tab, and picking screens in it.
//
// Standard 3D navigation (the owner's ruling, 2026-11-08), for ease of
// interaction - the Standard preset of Preferences > Controls, the one a
// new person has:
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
//                        handles, G and R move or turn from the keyboard,
//                        the arrows and Page Up / Down nudge
//                        (app-stage3d-handles.js), Esc cancels a drag.
//
// Preferences > Controls (2026-11-18) sets the mouse per person: the
// Standard preset above, Orbit first (a left drag on empty space orbits
// round the view's centre, Shift or Cmd / Ctrl + drag draws the box, a drag
// on a selected screen still moves it), then any action on its own button
// and modifier. controls.js resolvePress reads a press against that map;
// touch is never the map's.
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
// The wheel stops this close to what it nears: near enough that one LED
// pixel of the finest screen fills a good part of the view (2026-11-09,
// "pixel level zoom"); the near plane follows the camera in
// (app-stage3d.js _s3dFitNear), so nothing is cut away on the way.
const NEAR_MM = 2;
// Orthographic zoom goes in until the view is this many mm tall.
const ORTHO_MIN_MM = 4;
const FAR_MM = 400000;           // and backs off no further than this
const PAD_GAP_MS = 250;          // trackpad events closer than this are one gesture
const VIEW_KEYS = ['front', 'back', 'left', 'right', 'top', 'iso'];

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// The view's keys: each Controls action (controls.js) and what it does.
const KEY_ACTIONS = [
    ['frame3d', function () { this._s3dFrameSelection(); }],
    ['home3d', function () { this._s3dHome(); }],
    ['moveHandles', function () { this._s3dSetTool('move'); }],
    ['rotateHandles', function () { this._s3dSetTool('rotate'); }],
    ['grab3d', function () { this._s3dKeyTransformStart('move'); }],
    ['turn3d', function () { this._s3dKeyTransformStart('rotate'); }],
].concat(['viewFront', 'viewBack', 'viewLeft', 'viewRight', 'viewTop', 'viewIso'].map((id, i) =>
    [id, function () { this._s3dPreset(VIEW_KEYS[i]); }]));

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
        if (!st.renderer || !st.active) return;
        // A gesture whose release never came (the window lost it) ends here.
        if (st.nav) this._s3dCancelDrag();
        this._s3dNudgeCommit();
        this._s3dEndCameraMove(true);
        const touch = ev.pointerType === 'touch';
        // On a Mac, Ctrl+click is the right click (a one-button mouse, a
        // trackpad): it opens the menu on release, like the right button,
        // and never draws a box or moves the camera. Cmd+click adds to the
        // selection there; on Windows Ctrl+click still adds.
        if (!touch && ev.button === 0 && ev.ctrlKey && !ev.altKey && !ev.metaKey
                && typeof this._isMacPlatform === 'function' && this._isMacPlatform()) {
            ev.preventDefault();
            this._s3dReleaseField();
            st.nav = {
                kind: 'menu', id: ev.pointerId, x: ev.clientX, y: ev.clientY,
                lastX: ev.clientX, lastY: ev.clientY, moved: false,
            };
            if (st.controls) st.controls.enabled = false;
            try { st.renderer.domElement.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
            return;
        }
        // What the press is, by the person's mouse map (controls.js
        // resolvePress): a camera move at once, a press that waits to see
        // whether it is a click or a drag, or nothing. Touch keeps its own
        // way (a left press here, the orbit controls on empty space).
        const mods = { shift: ev.shiftKey, alt: ev.altKey, mod: ev.ctrlKey || ev.metaKey };
        const plan = touch
            ? (ev.button === 0 ? { pick: true, select: true, move: true, moveMod: 'none', box: false, defer: null } : null)
            : window.Controls.resolvePress(this.controlMouseMap(), Object.assign({ button: ev.button }, mods));
        if (!plan && !touch && ev.button === 2) {
            // Nothing set to the right button: a right press is the screen
            // menu, on its release, the way a Mac's Ctrl+click is.
            ev.preventDefault();
            this._s3dReleaseField();
            st.nav = {
                kind: 'menu', id: ev.pointerId, x: ev.clientX, y: ev.clientY,
                lastX: ev.clientX, lastY: ev.clientY, moved: false,
            };
            if (st.controls) st.controls.enabled = false;
            try { st.renderer.domElement.setPointerCapture(ev.pointerId); } catch (e) { /* a dispatched press */ }
            return;
        }
        if (!plan) return;
        if (plan.camera) {
            ev.preventDefault();
            this._s3dReleaseField();
            this._s3dStartCamera(ev, plan.camera);
            return;
        }
        if (ev.button !== 0) {
            // The middle or right button's own browser habits stay out of
            // a press the map gives to selecting.
            ev.preventDefault();
            this._s3dReleaseField();
        }
        const handle = this._s3dHandlePick(ev.clientX, ev.clientY);
        const hit = this._s3dPick(ev.clientX, ev.clientY);
        const n = {
            kind: 'press', id: ev.pointerId, x: ev.clientX, y: ev.clientY, lastX: ev.clientX, lastY: ev.clientY,
            moved: false, hit, handle, touch, shift: ev.shiftKey, mod: ev.ctrlKey || ev.metaKey,
            button: ev.button, plan,
        };
        st.nav = n;
        const moveOk = plan.move && (plan.moveMod === 'mod' || !n.mod);
        if (handle) {
            // A press on a handle drags it; a click on one (no travel) is a
            // click on what lies under it.
            st.controls.enabled = false;
        } else if (hit && this._s3dSelectedIds().has(hit.layerId) && moveOk) {
            this._s3dArmBodyMove(hit, ev.shiftKey && plan.moveMod !== 'shift');
        } else if (!touch) {
            // A drag from here draws the box, or from empty space is the
            // camera move the map gives that drag (Orbit first: a left drag
            // orbits); a click selects or lets go either way.
            st.controls.enabled = false;
            n.orbit = !hit && plan.defer ? plan.defer : null;
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
        if (n.kind === 'zoom') {
            // A drag that zooms (the mouse map's Zoom on a button): down
            // nears, up backs off, toward where the press came down.
            this._s3dZoomAt(n.x, n.y, Math.exp(clamp(dy * 0.005, -1, 1)));
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
            } else if (n.orbit) {
                this._s3dPressToCamera(n, ev);
                return;
            } else if (!n.plan || n.plan.box) {
                n.kind = 'box';
            } else {
                n.kind = 'idle';
            }
        }
        if (n.kind === 'handle') this._s3dHandleMove(n, ev);
        else if (n.kind === 'move') this._s3dBodyMove(ev);
        else if (n.kind === 'box') this._s3dBoxMove(n, ev);
    }

    // A press on empty space that travels turns into the camera move the
    // mouse map gives that drag (Orbit first: an orbit round the view's
    // centre), and takes the travel so far along. Its release logs and
    // saves the camera like any camera move (_s3dPointerUp).
    _s3dPressToCamera(n, ev) {
        const st = this._s3dState();
        n.kind = n.orbit;
        if (n.kind === 'orbit') {
            n.pivot = st.controls.target.clone();
            this._s3dPivotMark(n.pivot);
            this._s3dViewClass('s3d-orbiting', true);
            this._s3dOrbitBy(ev.clientX - n.x, ev.clientY - n.y, n.pivot);
        } else if (n.kind === 'pan') {
            n.depth = st.controls.target.clone();
            this._s3dViewClass('s3d-panning', true);
            this._s3dPanBy(ev.clientX - n.x, ev.clientY - n.y, n.depth);
        } else if (n.kind === 'zoom') {
            this._s3dZoomAt(n.x, n.y, Math.exp(clamp((ev.clientY - n.y) * 0.005, -1, 1)));
        }
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
        if (n.kind === 'orbit' || n.kind === 'pan' || n.kind === 'zoom') {
            if (n.moved) {
                this._s3dSaveCameraSoon();
                sendClientLog('stage3d_camera', { gesture: n.kind, button: n.button });
            } else if (n.button === 2 && !cancelled) {
                // A right click that did not pan: the app's menu, as before.
                if (typeof this.showContextMenu === 'function') this.showContextMenu(ev.clientX, ev.clientY);
            }
            return;
        }
        if (n.kind === 'menu') {
            // A Mac's Ctrl+click: the app's menu, as a right click opens it.
            // The left button's click that may follow would close it again
            // (the document's click shuts menus), so that one click is held.
            if (!cancelled && typeof this.showContextMenu === 'function') {
                const hold = (e) => { e.stopPropagation(); e.preventDefault(); };
                window.addEventListener('click', hold, { capture: true, once: true });
                setTimeout(() => window.removeEventListener('click', hold, true), 300);
                this.showContextMenu(ev.clientX, ev.clientY);
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
        if (n.kind === 'press' && !cancelled) {
            if (!n.plan || n.plan.select) this._s3dClick(n.hit, ev);
            // A right click the map gives to selecting still opens the menu.
            if (n.button === 2 && typeof this.showContextMenu === 'function') this.showContextMenu(ev.clientX, ev.clientY);
        }
    }

    // Puts the screens a preview moved back where they stand.
    _s3dRevertPreview(d) {
        const st = this._s3dState();
        if (!d || !d.starts) return;
        for (const [id, p] of d.starts) {
            const e = st.entries.get(id);
            if (!e) continue;
            e.obj.position.set(p.x, p.y, p.z);
            e.obj.rotation.set(p.pitch * DEG, p.yaw * DEG, p.roll * DEG, 'YXZ');
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
        if (kind !== 'zoom') this._s3dViewClass(kind === 'orbit' ? 's3d-orbiting' : 's3d-panning', true);
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
            const tallest = Math.max(1, (cam.top - cam.bottom) / ORTHO_MIN_MM);
            cam.zoom = clamp((cam.zoom || 1) / scale, 0.02, Math.max(500, tallest));
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
        this._s3dPickCorner(null);
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
        // G or R under way takes every key itself (app-stage3d-handles.js).
        if (st.keyX) return;
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
        if (st.nav) return;
        // The view's keys are the person's (Preferences > Controls), each
        // with exactly its own modifiers; shipped: F frame, Home, 1 to 6 the
        // views, W and E the handles, G and R move and turn from the
        // keyboard. The nudge keys are fixed, and never with Ctrl, Cmd or
        // Alt (Shift makes the step bigger).
        let act = null;
        const own = KEY_ACTIONS.find(([id]) => this.controlMatches(ev, id));
        if (own) act = () => own[1].call(this);
        else if (nudgeKey && !(ev.ctrlKey || ev.metaKey || ev.altKey)) act = () => this._s3dNudgeKey(ev);
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
