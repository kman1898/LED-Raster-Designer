// app-stage3d-png: Export > 3D PNG. A picture of the 3D stage as the 3D tab
// draws it (owner, 2026-11-24, from a user who renders shows elsewhere:
// "a 3D PNG export with a view pick"). The screens' Pixel Map faces, their
// bends, curves and corners, the header and footer bars and the floor grid
// as the tab's Bars and Grid switches show them; never the selection's
// accent seams, the move and turn handles, a corner spot or anything else
// laid over the stage for editing.
//
// The view: the tab's camera as it stands ("Current view"), or one of the
// tab's view buttons (Front, Back, Left, Right, Top, Iso), framed on every
// screen exactly as the button frames it (_s3dFitPose), in the tab's
// Perspective or Orthographic. The picture is drawn with a camera of its
// own on a renderer of its own, so the tab's camera, its size and what it
// shows are never touched. A picture shaped differently from the view
// keeps everything the view shows: it only ever gains stage at the sides
// or the top and bottom.
//
// The size: the view's own pixels, or 1920 x 1080, 3840 x 2160 or
// 7680 x 4320. One the graphics card cannot draw is refused, plainly,
// before anything is drawn. The background: the 3D view's, or transparent.
//
// Saved straight to a file like every export (saveBlobWithPicker), nothing
// opened. Its doors: File > Export 3D PNG beside Export OBJ, the Export
// dialog's format list, and the Export button itself while the 3D tab is
// open, which opens the dialog on 3D PNG there (the tab's camera bar is
// full: at a 1280 px window it has no room for one more button and still
// keeps to one row).
//
// The log: render_3d_png says what was drawn (source, view, mode, size,
// background, the screens and how many are in frame, a few colours read
// off the picture, the marks left out); export_3d_png where it went;
// export_3d_png_refused a size refused and why.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import { DEG, S3D_VIEW_DIRS } from './app-stage3d.js';
import { objName } from './obj-export.js';

export const PNG3D_VIEWS = ['current', 'front', 'back', 'left', 'right', 'top', 'iso'];
const VIEW_WORDS = {
    current: 'Current view', front: 'Front', back: 'Back', left: 'Left',
    right: 'Right', top: 'Top', iso: 'Iso',
};
// A seam's own colour when its screen is not selected (_s3dHighlight).
const SEAM_COLOR = 0x0a0a0a;
const SEAM_OPACITY = 0.9;
// The near plane, as the tab sets it (_s3dFitNear).
const NEAR_MIN = 0.05, NEAR_MAX = 20;
// No browser canvas is drawn bigger than this a side.
const CANVAS_SIDE_MAX = 16384;

function refusal(message, details) {
    const err = new Error(message);
    err.refused = true;
    err.details = details || null;
    return err;
}

function hex(px) {
    if (!px) return null;
    if (px[3] === 0) return 'clear';
    return '#' + [px[0], px[1], px[2]].map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();
}

class _Stage3DPng {
    // ── the dialog ────────────────────────────────────────────────────────

    // Wired once from setupEventListeners, after the binder's controls, so
    // this sync has the last word on which sections show for 3D PNG.
    initStage3dPngControls() {
        if (this._png3dWired) return;
        this._png3dWired = true;
        const fmt = document.getElementById('export-format');
        if (fmt) fmt.addEventListener('change', () => this.syncStage3dPngControls());
        ['export-3d-png-view', 'export-3d-png-size', 'export-3d-png-background'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.updateExportPreview());
        });
        // Export pressed on the 3D tab opens on 3D PNG. Ahead of the button's
        // own handler (app-wiring.js), which opens the dialog on the format
        // picked; on any other tab the dialog keeps its last format.
        document.addEventListener('click', (ev) => {
            const btn = ev.target && ev.target.closest ? ev.target.closest('#btn-export') : null;
            if (!btn || !this._s3dState().active) return;
            const f = document.getElementById('export-format');
            if (f) f.value = 'png-3d';
        }, true);
    }

    syncStage3dPngControls() {
        const fmt = document.getElementById('export-format');
        const on = !!fmt && fmt.value === 'png-3d';
        const show = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.style.display = v ? '' : 'none';
        };
        show('export-3d-png-section', on);
        if (!on) return;
        ['export-canvases-section', 'export-views-section', 'export-options-section',
            'export-pull-sheet-section', 'export-binder-section'].forEach(id => show(id, false));
        const vs = this._s3dPngViewSize();
        const opt = document.querySelector('#export-3d-png-size option[value="view"]');
        if (opt) opt.textContent = `Same as the 3D view (${vs.w} x ${vs.h})`;
    }

    // What the dialog asks for: { view, width, height, background }.
    stage3dPngOptions() {
        const val = (id, fallback) => {
            const el = document.getElementById(id);
            return (el && el.value) || fallback;
        };
        const view = PNG3D_VIEWS.includes(val('export-3d-png-view', 'current')) ? val('export-3d-png-view', 'current') : 'current';
        const size = val('export-3d-png-size', 'view');
        let width, height;
        const m = /^(\d+)x(\d+)$/.exec(size);
        if (m) {
            width = Number(m[1]);
            height = Number(m[2]);
        } else {
            const vs = this._s3dPngViewSize();
            width = vs.w;
            height = vs.h;
        }
        const background = val('export-3d-png-background', 'view') === 'transparent' ? 'transparent' : 'view';
        return { view, width, height, background, size };
    }

    stage3dPngFileName(projectName, view) {
        const word = view === 'current' || !VIEW_WORDS[view] ? 'View' : VIEW_WORDS[view];
        return `${objName(projectName, 'Project')}_3D_${word}.png`;
    }

    // The Export dialog's Export button on 3D PNG (app-wiring.js): a size
    // the card cannot draw, or a stage with no screens, is refused with
    // the dialog still up, so a smaller size is one pick away.
    async exportStage3dPngFromDialog(projectName) {
        const opts = this.stage3dPngOptions();
        const status = document.getElementById('status-message');
        try {
            await this.stage3dPngCheck(opts);
        } catch (err) {
            if (typeof this._toast === 'function') this._toast(err.message, true, 8000);
            return;
        }
        document.getElementById('export-modal').style.display = 'none';
        if (status) status.textContent = 'Exporting 3D PNG...';
        try {
            await this.exportStage3dPng(projectName, opts);
            if (status) status.textContent = 'Export complete!';
            setTimeout(() => { if (status) status.textContent = 'Ready'; }, 3000);
        } catch (error) {
            console.error('3D PNG export error:', error);
            if (status) status.textContent = 'Export failed!';
            sendClientLog('export_failed', { message: error.message, format: 'png-3d' });
            if (typeof this._toast === 'function') this._toast(error.message, true, 8000);
        }
    }

    // ── the picture ───────────────────────────────────────────────────────

    // The pixels the 3D view draws now; with the tab shut, the space it
    // opens into at the same pixel ratio.
    _s3dPngViewSize() {
        const st = this._s3dState();
        const c = st.renderer && st.renderer.domElement;
        if (st.active && c && c.width > 0 && c.height > 0) return { w: c.width, h: c.height };
        const host = document.getElementById('canvas-wrapper') || document.getElementById('canvas-container');
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        const w = host ? host.clientWidth : 0, h = host ? host.clientHeight : 0;
        return w > 0 && h > 0 ? { w: Math.round(w * dpr), h: Math.round(h * dpr) } : { w: 1920, h: 1080 };
    }

    // The most this computer's graphics card draws a side: { w, h }, or
    // null before the 3D library is in.
    stage3dPngLimit() {
        const st = this._s3dState();
        const gl = st.renderer && st.renderer.getContext && st.renderer.getContext();
        if (!gl || (gl.isContextLost && gl.isContextLost())) return null;
        const tex = gl.getParameter(gl.MAX_TEXTURE_SIZE);
        const rb = gl.getParameter(gl.MAX_RENDERBUFFER_SIZE);
        const vp = gl.getParameter(gl.MAX_VIEWPORT_DIMS) || [tex, tex];
        return {
            w: Math.min(tex || CANVAS_SIDE_MAX, rb || CANVAS_SIDE_MAX, vp[0] || CANVAS_SIDE_MAX, CANVAS_SIDE_MAX),
            h: Math.min(tex || CANVAS_SIDE_MAX, rb || CANVAS_SIDE_MAX, vp[1] || CANVAS_SIDE_MAX, CANVAS_SIDE_MAX),
        };
    }

    _s3dPngTooBig(w, h, limit, why) {
        const msg = `${w} x ${h} is too big for this computer's graphics card. `
            + `The most it can draw is ${limit.w} x ${limit.h}; pick a smaller size.`;
        sendClientLog('export_3d_png_refused', { size: [w, h], limit: [limit.w, limit.h], why },
            { area: 'export', level: 'warn', msg: `3D PNG refused: ${w}x${h}, the card draws ${limit.w}x${limit.h} at most (${why})` });
        return refusal(msg, { size: [w, h], limit: [limit.w, limit.h] });
    }

    // Throws a plain refusal when the picture cannot be drawn: no 3D
    // library or no WebGL, no screens on the stage, a size the card does
    // not draw. Resolves to the limit otherwise.
    async stage3dPngCheck(opts) {
        const w = Math.round(Number(opts && opts.width)), h = Math.round(Number(opts && opts.height));
        if (!(w >= 1 && h >= 1)) throw refusal('Pick a size for the 3D PNG.');
        if (!this._s3dLayout().items.length) {
            throw refusal('No screens on the 3D stage to export. Show a screen in Show Look first.');
        }
        const st = this._s3dState();
        try {
            await this._s3dLoad();
        } catch (_) {
            throw refusal('The 3D view could not load its drawing library, so there is no 3D PNG to save.');
        }
        if (!st.renderer) {
            throw refusal('The 3D PNG needs WebGL, which this browser or its graphics driver does not provide.');
        }
        const limit = this.stage3dPngLimit();
        if (limit && (w > limit.w || h > limit.h)) throw this._s3dPngTooBig(w, h, limit, 'card limit');
        return limit;
    }

    // The stage brought up to date. With the tab shut it is built (or
    // rebuilt) for the picture alone: the tab, its camera and its first
    // fit are left for when it opens.
    _s3dPngStage() {
        const st = this._s3dState();
        if (st.active) {
            if (st.timer) { clearTimeout(st.timer); st.timer = null; }
            this._s3dSync();
            return;
        }
        const opened = !!st.wired;
        st.active = true;
        try {
            this._s3dSync();
        } finally {
            st.active = false;
            if (st.frame) { cancelAnimationFrame(st.frame); st.frame = 0; }
            // a tab never opened still frames itself to its own shape when it does
            if (!opened && !st.cam) st.needsFit = true;
        }
    }

    // A camera of the picture's own for `view`, `w` x `h` pixels.
    _s3dPngCamera(view, w, h) {
        const st = this._s3dState();
        const T = st.T;
        const aspect = w / h;
        const ortho = st.camera === st.ortho;
        let pose, quat = null, viewAspect = aspect;
        if (view === 'current') {
            pose = {
                position: st.camera.position.clone(), target: st.controls.target.clone(),
                orthoHalf: st.orthoHalf, zoom: ortho ? (st.ortho.zoom || 1) : 1,
            };
            quat = st.camera.quaternion.clone();
            const vs = this._s3dPngViewSize();
            viewAspect = vs.w / vs.h;
        } else {
            const d = S3D_VIEW_DIRS[view];
            pose = this._s3dFitPose(new T.Vector3(d[0], d[1], d[2]), aspect, null);
        }
        // A picture narrower than the view keeps the view's width of stage.
        const grow = viewAspect > aspect ? viewAspect / aspect : 1;
        let cam;
        if (ortho) {
            const half = Math.max(100, pose.orthoHalf || 5000) * grow;
            cam = new T.OrthographicCamera(-half * aspect, half * aspect, half, -half, st.ortho.near, st.ortho.far);
            cam.zoom = pose.zoom || 1;
        } else {
            const fov = 2 * Math.atan(Math.tan(st.persp.fov * DEG / 2) * grow) / DEG;
            cam = new T.PerspectiveCamera(fov, aspect, st.persp.near, st.persp.far);
        }
        cam.position.copy(pose.position);
        if (quat) {
            cam.quaternion.copy(quat);
        } else {
            cam.up.set(0, 1, 0);
            cam.lookAt(pose.target);
        }
        if (cam.isPerspectiveCamera) {
            // the near plane follows the camera in, as on the tab
            let d = cam.position.distanceTo(pose.target) / 1000;
            const sphere = new T.Sphere();
            for (const e of st.entries.values()) {
                if (!e.geo || !e.geo.boundingSphere) continue;
                e.obj.updateMatrixWorld();
                sphere.copy(e.geo.boundingSphere).applyMatrix4(e.obj.matrixWorld);
                d = Math.min(d, Math.max(0, sphere.distanceToPoint(cam.position)) / 4);
            }
            cam.near = Math.max(NEAR_MIN, Math.min(NEAR_MAX, d));
        }
        cam.updateProjectionMatrix();
        cam.updateMatrixWorld(true);
        return { cam, pose, mode: ortho ? 'orthographic' : 'perspective' };
    }

    // Every editing mark off the stage for the one draw: anything in the
    // scene but the screens, the grid and the lights (the handles, and any
    // mark added later), each screen's corner spot, and the selection's
    // accent on the seams. Returns how to put them back, and what was hidden.
    _s3dPngHideMarks() {
        const st = this._s3dState();
        const keep = new Set([st.root, st.gridGroup]);
        const undo = [];
        const hidden = { overlays: 0, cornerSpots: 0, selectedSeams: 0 };
        for (const o of st.scene.children) {
            if (keep.has(o) || o.isLight || !o.visible) continue;
            o.visible = false;
            hidden.overlays += 1;
            undo.push(() => { o.visible = true; });
        }
        for (const e of st.entries.values()) {
            if (e.seam && e.seam.visible) {
                e.seam.visible = false;
                hidden.cornerSpots += 1;
                undo.push(() => { e.seam.visible = true; });
            }
            if (e.lineMat) {
                const color = e.lineMat.color.getHex(), opacity = e.lineMat.opacity;
                if (color !== SEAM_COLOR) hidden.selectedSeams += 1;
                e.lineMat.color.setHex(SEAM_COLOR);
                e.lineMat.opacity = SEAM_OPACITY;
                undo.push(() => { e.lineMat.color.setHex(color); e.lineMat.opacity = opacity; });
            }
        }
        return { hidden, restore: () => { for (const f of undo.reverse()) f(); } };
    }

    // The picture: { blob, width, height, view, mode, background, camera,
    // screens, inFrame, colors, marks, ms }. `opts`: { view, width, height,
    // background }. The tab's camera is read, never written.
    async stage3dPngRender(opts = {}) {
        const t0 = performance.now();
        const view = PNG3D_VIEWS.includes(opts.view) ? opts.view : 'current';
        const w = Math.round(Number(opts.width)), h = Math.round(Number(opts.height));
        const background = opts.background === 'transparent' ? 'transparent' : 'view';
        await this.stage3dPngCheck({ width: w, height: h });
        const st = this._s3dState();
        const T = st.T;
        this._s3dPngStage();
        let r2;
        try {
            r2 = new T.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true, alpha: true, preserveDrawingBuffer: true });
        } catch (err) {
            throw refusal('The 3D PNG could not get a drawing surface from the graphics card. Close other 3D windows and try again.');
        }
        try {
            r2.setPixelRatio(1);
            r2.setSize(w, h, false);
            r2.outputColorSpace = T.SRGBColorSpace;
            const gl = r2.getContext();
            if (gl.drawingBufferWidth !== w || gl.drawingBufferHeight !== h) {
                // the browser shrank the surface: it draws no bigger
                throw this._s3dPngTooBig(w, h, { w: gl.drawingBufferWidth, h: gl.drawingBufferHeight }, 'surface shrunk');
            }
            const tokens = this._s3dTokens();
            r2.setClearColor(tokens.canvas, background === 'transparent' ? 0 : 1);
            const { cam, pose, mode } = this._s3dPngCamera(view, w, h);
            const marks = this._s3dPngHideMarks();
            let colors, inFrame = 0;
            try {
                r2.render(st.scene, cam);
                // a few colours read off the picture (never the picture)
                const read = (fx, fy) => {
                    const px = new Uint8Array(4);
                    gl.readPixels(Math.floor(fx * (w - 1)), Math.floor((1 - fy) * (h - 1)), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
                    return hex(px);
                };
                colors = { middle: read(0.5, 0.5), tl: read(0.1, 0.1), tr: read(0.9, 0.1), bl: read(0.1, 0.9), br: read(0.9, 0.9) };
                const frustum = new T.Frustum().setFromProjectionMatrix(
                    new T.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse));
                for (const e of st.entries.values()) {
                    if (e.front && e.front.geometry && frustum.intersectsObject(e.front)) inFrame += 1;
                }
            } finally {
                marks.restore();
            }
            const blob = await new Promise((res, rej) => {
                r2.domElement.toBlob(b => (b ? res(b) : rej(new Error('The 3D PNG could not be encoded.'))), 'image/png');
            });
            const r = (v) => Math.round(v * 100) / 100;
            const camera = {
                mode, position: cam.position.toArray().map(r), target: pose.target.toArray().map(r),
                fov: cam.isPerspectiveCamera ? r(cam.fov) : undefined,
                half: cam.isOrthographicCamera ? r(cam.top) : undefined,
                zoom: cam.isOrthographicCamera ? cam.zoom : undefined,
            };
            const screens = [...st.entries.values()].map(e => `${e.name || 'Screen'} (#${e.id})`);
            const ms = Math.round(performance.now() - t0);
            const out = {
                blob, width: w, height: h, view, mode, background, camera,
                screens: screens.length, inFrame, colors, marks: marks.hidden, grid: st.grid !== false,
                bars: st.bars !== false, ms, source: st.active ? '3D tab' : '3D stage, tab shut',
            };
            sendClientLog('render_3d_png', {
                source: out.source, view, mode, size: [w, h], background, grid: out.grid, bars: out.bars,
                screens: { n: screens.length, inFrame, names: screens.slice(0, 8) }, colors, marksLeftOut: marks.hidden,
                camera, bytes: blob.size, ms,
            }, { area: '3d', level: screens.length && !inFrame ? 'warn' : 'info',
                msg: `3D PNG drew ${screens.length} screen${screens.length === 1 ? '' : 's'} (${inFrame} in frame), `
                    + `${VIEW_WORDS[view]}, ${mode}, ${w}x${h}, background ${background === 'transparent' ? 'transparent' : 'as the 3D view'}` });
            return out;
        } finally {
            r2.dispose();
            if (typeof r2.forceContextLoss === 'function') r2.forceContextLoss();
        }
    }

    async exportStage3dPng(projectName, opts) {
        const out = await this.stage3dPngRender(opts);
        const filename = this.stage3dPngFileName(projectName, out.view);
        const saved = await this.saveBlobWithPicker(out.blob, filename, 'image/png');
        const where = saved && saved.path ? saved.path : (saved && saved.how) || null;
        sendClientLog('export_3d_png', {
            file: filename, view: out.view, mode: out.mode, size: [out.width, out.height], background: out.background,
            bytes: out.blob.size, path: where, saved: !!(saved && saved.saved), cancelled: !!(saved && saved.cancelled),
        }, { area: 'export',
            msg: `3D PNG ${saved && saved.cancelled ? 'drawn, not saved' : 'saved'}: ${filename}, ${out.width}x${out.height}, `
                + `${Math.round(out.blob.size / 1024).toLocaleString('en-US')} KB` + (saved && saved.path ? ` to ${saved.path}` : '') });
        return { ...out, filename, saved };
    }
}

for (const k of Object.getOwnPropertyNames(_Stage3DPng.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Stage3DPng.prototype, k));
    }
}
