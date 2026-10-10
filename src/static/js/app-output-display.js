// app-output-display: View > Output to Display… - one canvas's raster sent
// full screen to another monitor, as a live test pattern / pixel map on an
// LED processor input. Not an export: it opens a window and keeps it fed.
//
// The output window (/output, templates/output.html + output-display.js)
// draws nothing itself. This window renders the chosen canvas the way an
// export does - the same renderer, swapped onto an offscreen canvas in
// exportMode with only that canvas visible and the workspace panned so its
// top-left is (0, 0) - and hands the frame to the page's present(). Every
// main render (canvas.js render() calls _outputDisplayOnRender) schedules a
// refresh; the refresh compares a signature of the project and the
// renderer's display switches and redraws only when something changed, so
// panning and zooming the designer costs one string compare, not a render.
// Because the frames come from this window's project, the output follows
// whatever this window shows - its own edits, undo, and the layer edits
// other LAN clients push to it.
//
// The windows are kept in _outputDisplayWindows (references, not ids), the
// dialog lists and closes them, and they close with this window.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const OUTPUT_VIEWS = [
    ['pixel-map', 'Pixel Map'],
    ['cabinet-id', 'Cabinet ID'],
    ['show-look', 'Show Look'],
    ['data-flow', 'Data'],
    ['power', 'Power'],
    // The Pixel Map with every cabinet's modules and the marked ones
    // (app-idm-locator.js), so the crew can find a bad module on the wall.
    ['idm', 'IDM Locator'],
];
const OUTPUT_SCALES = { fit: 'Fit to display', '1to1': '1:1 pixel' };

class _OutputDisplay {
    // ---- the dialog ---------------------------------------------------------

    // `canvasId`: the canvas to start on (the right-click menu passes the one
    // under the cursor); otherwise the active canvas.
    openOutputDisplayDialog(canvasId) {
        const modal = this._outputDisplayDialog();
        const canvases = this._outputDisplayCanvases();
        const pick = (canvasId && canvases.some(c => c.id === canvasId))
            ? canvasId
            : ((this.project && this.project.active_canvas_id) || (canvases[0] && canvases[0].id) || '');
        const canvasSel = modal.querySelector('#output-display-canvas');
        canvasSel.innerHTML = '';
        canvases.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            canvasSel.appendChild(opt);
        });
        canvasSel.value = pick;
        this._outputDisplayUpdateNote();
        this._outputDisplayFillScreens();
        this._outputDisplayRenderList();
        modal.style.display = 'block';
        // Screens are listed without a prompt when the browser already has
        // the permission; otherwise "Find displays" asks for it.
        this._outputDisplayProbeScreens(false);
        clearInterval(this._outputDisplayListTimer);
        this._outputDisplayListTimer = setInterval(() => {
            if (modal.style.display === 'none') {
                clearInterval(this._outputDisplayListTimer);
                return;
            }
            this._outputDisplayRenderList(true);
        }, 1000);
        sendClientLog('output_display_dialog', { canvases: canvases.length });
    }

    closeOutputDisplayDialog() {
        const modal = document.getElementById('output-display-modal');
        if (modal) modal.style.display = 'none';
        clearInterval(this._outputDisplayListTimer);
    }

    // The canvases the dialog offers: the project's, or one entry standing
    // for the whole raster of a legacy single-canvas project (id '').
    _outputDisplayCanvases() {
        const list = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        if (!list.length) return [{ id: '', name: (this.project && this.project.name) || 'Canvas' }];
        return list.filter(c => c && c.id).map(c => ({ id: c.id, name: c.name || c.id }));
    }

    _outputDisplayDialog() {
        let modal = document.getElementById('output-display-modal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'output-display-modal';
        modal.className = 'modal';
        modal.style.display = 'none';
        const views = OUTPUT_VIEWS.map(([v, label]) => `<option value="${v}">${label}</option>`).join('');
        const canPickScreen = typeof window.getScreenDetails === 'function';
        modal.innerHTML = `
            <div class="modal-content output-display-dialog">
                <h2>Output to Display</h2>
                <div class="od-row">
                    <label for="output-display-canvas">Canvas</label>
                    <select id="output-display-canvas"></select>
                </div>
                <div class="od-row">
                    <label for="output-display-view">View</label>
                    <select id="output-display-view">${views}</select>
                </div>
                <div class="od-row">
                    <span class="od-label">Scale</span>
                    <div class="od-choices">
                        <label><input type="radio" name="output-display-scale" value="fit" checked> Fit to display</label>
                        <label><input type="radio" name="output-display-scale" value="1to1"> 1:1 pixel</label>
                    </div>
                </div>
                <div class="od-row" id="output-display-screen-row"${canPickScreen ? '' : ' hidden'}>
                    <label for="output-display-screen">Display</label>
                    <select id="output-display-screen"></select>
                    <button type="button" class="btn" id="output-display-find-screens">Find displays</button>
                </div>
                <div class="od-note" id="output-display-note"></div>
                <div class="od-open" id="output-display-open-section">
                    <div class="od-open-title">Open outputs</div>
                    <div id="output-display-open-list"></div>
                </div>
                <div class="od-actions">
                    <button type="button" class="btn" id="output-display-close">Close</button>
                    <button type="button" class="btn btn-primary" id="output-display-open">Open output</button>
                </div>
            </div>`;
        document.body.appendChild(modal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.closeOutputDisplayDialog();
        });
        modal.querySelector('#output-display-close')
            .addEventListener('click', () => this.closeOutputDisplayDialog());
        // window.open runs inside this click, so the browser counts it as
        // the user's own gesture and lets the window open.
        modal.querySelector('#output-display-open')
            .addEventListener('click', () => this._outputDisplayOpenFromDialog());
        modal.querySelector('#output-display-find-screens')
            .addEventListener('click', () => this._outputDisplayProbeScreens(true));
        modal.querySelector('#output-display-canvas')
            .addEventListener('change', () => this._outputDisplayUpdateNote());
        modal.querySelector('#output-display-view')
            .addEventListener('change', () => this._outputDisplayUpdateNote());
        modal.querySelectorAll('input[name="output-display-scale"]').forEach(r =>
            r.addEventListener('change', () => this._outputDisplayUpdateNote()));
        modal.querySelector('#output-display-open-list').addEventListener('click', (e) => {
            const btn = e.target.closest('[data-output-id]');
            if (!btn) return;
            this.closeOutputDisplay(Number(btn.dataset.outputId));
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.style.display !== 'none') this.closeOutputDisplayDialog();
        });
        return modal;
    }

    _outputDisplayChoice() {
        const modal = this._outputDisplayDialog();
        const scaleEl = modal.querySelector('input[name="output-display-scale"]:checked');
        const screenSel = modal.querySelector('#output-display-screen');
        const screenIdx = screenSel && screenSel.value !== '' ? Number(screenSel.value) : -1;
        return {
            canvasId: modal.querySelector('#output-display-canvas').value || '',
            view: modal.querySelector('#output-display-view').value || 'pixel-map',
            scale: (scaleEl && scaleEl.value === '1to1') ? '1to1' : 'fit',
            screen: (this._outputDisplayScreens && screenIdx >= 0)
                ? this._outputDisplayScreens[screenIdx] || null : null,
        };
    }

    // The raster the choice would show, so 1:1 says what it needs.
    _outputDisplayUpdateNote() {
        const note = document.getElementById('output-display-note');
        if (!note) return;
        const { canvasId, view, scale } = this._outputDisplayChoice();
        const size = this._outputDisplayRasterSize(canvasId, view);
        const dims = size ? `${size.width} × ${size.height}` : '';
        note.textContent = !size ? ''
            : (scale === '1to1'
                ? `Raster ${dims}, one raster pixel per display pixel from the top-left corner. A display smaller than the raster cuts off the rest.`
                : `Raster ${dims}, scaled to fill the display.`);
    }

    _outputDisplayRasterSize(canvasId, view) {
        const show = view === 'show-look' || view === 'data-flow' || view === 'power';
        const list = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        if (!list.length) {
            const r = window.canvasRenderer;
            if (!r) return null;
            return show
                ? { width: r.showRasterWidth, height: r.showRasterHeight }
                : { width: r.pixelRasterWidth, height: r.pixelRasterHeight };
        }
        const c = list.find(x => x && x.id === canvasId);
        if (!c) return null;
        const w = show ? (Number(c.show_raster_width) || Number(c.raster_width)) : Number(c.raster_width);
        const h = show ? (Number(c.show_raster_height) || Number(c.raster_height)) : Number(c.raster_height);
        return (w && h) ? { width: w, height: h } : null;
    }

    // ---- displays (the Window Management API, where the browser has it) ----

    async _outputDisplayProbeScreens(ask) {
        if (typeof window.getScreenDetails !== 'function') return;
        if (!ask) {
            let granted = false;
            try {
                const st = await navigator.permissions.query({ name: 'window-management' });
                granted = st && st.state === 'granted';
            } catch (_) { granted = false; }
            if (!granted) return;
        }
        try {
            const details = await window.getScreenDetails();
            this._outputDisplayScreenDetails = details;
            this._outputDisplayScreens = Array.from(details.screens || []);
            if (!this._outputDisplayScreensWatched && details.addEventListener) {
                this._outputDisplayScreensWatched = true;
                details.addEventListener('screenschange', () => {
                    this._outputDisplayScreens = Array.from(details.screens || []);
                    this._outputDisplayFillScreens();
                });
            }
        } catch (err) {
            sendClientLog('output_display_screens_refused', { message: String(err && err.message || err) });
            this._outputDisplayScreens = null;
        }
        this._outputDisplayFillScreens();
    }

    _outputDisplayFillScreens() {
        const sel = document.getElementById('output-display-screen');
        if (!sel) return;
        const screens = this._outputDisplayScreens || [];
        const current = this._outputDisplayScreenDetails && this._outputDisplayScreenDetails.currentScreen;
        const prev = sel.value;
        sel.innerHTML = '';
        if (!screens.length) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Where the browser opens it';
            sel.appendChild(opt);
            return;
        }
        let firstOther = -1;
        screens.forEach((s, i) => {
            const opt = document.createElement('option');
            opt.value = String(i);
            const name = s.label || `Display ${i + 1}`;
            const tags = [];
            if (s.isPrimary) tags.push('main');
            if (s === current) tags.push('this window');
            opt.textContent = `${name} (${s.width} × ${s.height}${tags.length ? ', ' + tags.join(', ') : ''})`;
            sel.appendChild(opt);
            if (firstOther < 0 && s !== current) firstOther = i;
        });
        // Another display than this window's is the usual point of it.
        sel.value = (prev !== '' && screens[Number(prev)]) ? prev : String(firstOther >= 0 ? firstOther : 0);
    }

    // ---- opening, listing, closing -----------------------------------------

    _outputDisplayOpenFromDialog() {
        const choice = this._outputDisplayChoice();
        const entry = this.openOutputDisplay(choice);
        if (!entry) {
            const note = document.getElementById('output-display-note');
            if (note) note.textContent = 'The browser blocked the new window. Allow pop-ups for this address and try again.';
            return;
        }
        this._outputDisplayRenderList();
    }

    // Open one output. choice: { canvasId, view, scale, screen }. Returns
    // the entry, or null when the browser refused the window.
    openOutputDisplay(choice) {
        const view = OUTPUT_VIEWS.some(([v]) => v === choice.view) ? choice.view : 'pixel-map';
        const scale = choice.scale === '1to1' ? '1to1' : 'fit';
        const canvasId = choice.canvasId || '';
        const qs = new URLSearchParams({ canvas: canvasId, view, scale });
        const s = choice.screen;
        let features;
        if (s) {
            qs.set('fs', '1');
            features = `popup=yes,left=${s.availLeft},top=${s.availTop},width=${s.availWidth},height=${s.availHeight}`;
        } else {
            const w = Math.round((window.screen.availWidth || 1280) * 0.6);
            const h = Math.round((window.screen.availHeight || 720) * 0.6);
            features = `popup=yes,width=${w},height=${h}`;
        }
        this._outputDisplaySeq = (this._outputDisplaySeq || 0) + 1;
        const id = this._outputDisplaySeq;
        const win = window.open(`/output?${qs.toString()}`, `lrd-output-${id}`, features);
        if (!win) {
            sendClientLog('output_display_blocked', { canvasId, view, scale });
            return null;
        }
        const entry = { id, win, canvasId, view, scale, lastSig: null };
        this._outputDisplayTrack(entry);
        sendClientLog('output_display_open', { id, canvasId, view, scale, screen: !!s });
        return entry;
    }

    _outputDisplayTrack(entry) {
        if (!Array.isArray(this._outputDisplayWindows)) this._outputDisplayWindows = [];
        this._outputDisplayWindows.push(entry);
        if (!this._outputDisplayUnloadBound) {
            this._outputDisplayUnloadBound = true;
            // The outputs belong to this window: closing or reloading it
            // closes them too (the page also checks its opener each second).
            window.addEventListener('pagehide', () => this.closeAllOutputDisplays());
        }
    }

    // The open outputs, oldest first; a window the user closed is dropped.
    listOutputDisplays() {
        const all = Array.isArray(this._outputDisplayWindows) ? this._outputDisplayWindows : [];
        this._outputDisplayWindows = all.filter(e => e.win && !e.win.closed);
        return this._outputDisplayWindows.map(e => ({
            id: e.id, canvasId: e.canvasId, view: e.view, scale: e.scale,
            label: this._outputDisplayLabel(e),
        }));
    }

    closeOutputDisplay(id) {
        const all = Array.isArray(this._outputDisplayWindows) ? this._outputDisplayWindows : [];
        const entry = all.find(e => e.id === id);
        if (entry && entry.win && !entry.win.closed) entry.win.close();
        this._outputDisplayWindows = all.filter(e => e !== entry);
        this._outputDisplayRenderList();
        sendClientLog('output_display_close', { id });
    }

    closeAllOutputDisplays() {
        (this._outputDisplayWindows || []).forEach(e => {
            try { if (e.win && !e.win.closed) e.win.close(); } catch (_) { /* gone */ }
        });
        this._outputDisplayWindows = [];
    }

    _outputDisplayLabel(entry) {
        const c = this._outputDisplayCanvases().find(x => x.id === entry.canvasId);
        const v = OUTPUT_VIEWS.find(([k]) => k === entry.view);
        return `${c ? c.name : 'Missing canvas'} · ${v ? v[1] : entry.view} · ${OUTPUT_SCALES[entry.scale] || entry.scale}`;
    }

    // `quiet`: the once-a-second poll - rewrite only when the list changed.
    _outputDisplayRenderList(quiet) {
        const host = document.getElementById('output-display-open-list');
        const section = document.getElementById('output-display-open-section');
        if (!host || !section) return;
        const list = this.listOutputDisplays();
        const key = list.map(e => `${e.id}:${e.label}`).join('|');
        if (quiet && key === host.dataset.key) return;
        host.dataset.key = key;
        host.innerHTML = '';
        section.hidden = list.length === 0;
        list.forEach(e => {
            const row = document.createElement('div');
            row.className = 'od-open-row';
            const name = document.createElement('span');
            name.className = 'od-open-name';
            name.textContent = e.label;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn od-open-close';
            btn.dataset.outputId = String(e.id);
            btn.textContent = 'Close';
            row.appendChild(name);
            row.appendChild(btn);
            host.appendChild(row);
        });
    }

    // ---- the right-click menu ----------------------------------------------

    // The canvas under the cursor when the right-click landed on the canvas
    // area; undefined anywhere else (the item is then not offered).
    _prepareOutputDisplayMenu(x, y) {
        const under = document.elementFromPoint(x, y);
        if (!under || !under.closest || !under.closest('#canvas-wrapper')) return undefined;
        const r = window.canvasRenderer;
        if (!r || !r.canvas) return '';
        const rect = r.canvas.getBoundingClientRect();
        const wx = (x - rect.left - r.panX) / r.zoom;
        const wy = (y - rect.top - r.panY) / r.zoom;
        const hit = typeof r._canvasAtPoint === 'function' ? r._canvasAtPoint(wx, wy) : null;
        return hit ? hit.id : ((this.project && this.project.active_canvas_id) || '');
    }

    // ---- feeding the windows -----------------------------------------------

    // Called by an output page when it loads (and again after it reloads).
    _outputDisplayAttach(win) {
        if (!Array.isArray(this._outputDisplayWindows)) this._outputDisplayWindows = [];
        let entry = this._outputDisplayWindows.find(e => e.win === win);
        if (!entry) {
            // A window this list lost track of (opened before a reload of
            // this one): take it back on its own address.
            const p = (win.lrdOutput && win.lrdOutput.params) || {};
            this._outputDisplaySeq = (this._outputDisplaySeq || 0) + 1;
            entry = {
                id: this._outputDisplaySeq, win, canvasId: p.canvas || '',
                view: OUTPUT_VIEWS.some(([v]) => v === p.view) ? p.view : 'pixel-map',
                scale: p.scale === '1to1' ? '1to1' : 'fit', lastSig: null,
            };
            this._outputDisplayTrack(entry);
        }
        entry.lastSig = null;
        setTimeout(() => this._outputDisplayRefresh(), 0);
    }

    // canvas.js render() calls this on every main (non-export) render.
    _outputDisplayOnRender() {
        // A redraw for the IDM Locator's highlight alone (app-idm-locator.js
        // _idmRepaint): the outputs get it through _outputDisplayBlink.
        if (this._idmQuietRender) return;
        if (this._outputDisplayBusy || this._outputDisplayTimer) return;
        if (!Array.isArray(this._outputDisplayWindows) || !this._outputDisplayWindows.length) return;
        this._outputDisplayTimer = setTimeout(() => {
            this._outputDisplayTimer = null;
            this._outputDisplayRefresh();
        }, 120);
    }

    // What the output picture depends on: the project (runtime caches
    // dropped, as history does), the preferences, the renderer's display
    // switches and which images have finished loading.
    _outputDisplaySignature() {
        const r = window.canvasRenderer;
        const flags = [];
        for (const k of Object.keys(r)) {
            if (/^_|mouse|drag|hover|cursor|select|pan|zoom|^is[A-Z]|viewMode|export|render|probe|pulse/i.test(k)) continue;
            const v = r[k];
            if (typeof v === 'boolean' || typeof v === 'string') flags.push(`${k}=${v}`);
        }
        const images = ((this.project && this.project.layers) || [])
            .map(l => (l && l._imageObj) ? (l._imageObj.complete ? '1' : '0') : '').join('');
        return JSON.stringify(this.project, this._snapshotReplacer)
            + '|' + JSON.stringify(this._serverPreferences || null)
            + '|' + flags.join(',') + '|' + images;
    }

    _outputDisplayRefresh(force) {
        this.listOutputDisplays();
        const live = this._outputDisplayWindows;
        if (!live.length || !this.project || !window.canvasRenderer) return;
        let sig;
        try { sig = this._outputDisplaySignature(); } catch (_) { sig = `t${Date.now()}`; }
        const due = live.filter(e => force || e.lastSig !== sig);
        if (!due.length) return;
        this._outputDisplayBusy = true;
        let drew = false;
        try {
            for (const e of due) {
                if (this._outputDisplayRenderEntry(e)) {
                    e.lastSig = sig;
                    drew = true;
                }
            }
        } finally {
            // The offscreen passes rewrote the renderer's hit areas in
            // raster coordinates; one main render puts them back.
            try { if (drew) window.canvasRenderer.render(); } finally { this._outputDisplayBusy = false; }
        }
    }

    _outputDisplayPage(entry) {
        try {
            const win = entry.win;
            if (!win || win.closed) return null;
            const page = win.lrdOutput;
            return (page && typeof page.present === 'function') ? page : null;
        } catch (_) {
            return null;
        }
    }

    // One frame for one output: the export recipe (performExport) for a
    // single canvas and view at scale 1, onto this entry's own offscreen
    // canvas, then handed to the page.
    _outputDisplayRenderEntry(entry) {
        const page = this._outputDisplayPage(entry);
        if (!page) return false;
        const r = window.canvasRenderer;
        const project = this.project;
        const canvases = Array.isArray(project.canvases) ? project.canvases : [];
        let target = null;
        if (canvases.length) {
            target = canvases.find(c => c && c.id === entry.canvasId) || null;
            if (!target) {
                page.missing('This canvas is no longer in the project.');
                return true;
            }
        }
        if (!entry.offscreen) {
            entry.offscreen = document.createElement('canvas');
            entry.offCtx = entry.offscreen.getContext('2d', { alpha: false });
        }
        // The IDM Locator's frame is drawn WITHOUT its live highlight, into
        // a canvas of its own: _outputDisplayCompose lays the highlight over
        // a copy of it, so the highlight's blink and moves never need a
        // render (_outputDisplayBlink).
        const idm = entry.view === 'idm';
        if (idm && !entry.base) {
            entry.base = document.createElement('canvas');
            entry.baseCtx = entry.base.getContext('2d', { alpha: false });
        }
        const off = idm ? entry.base : entry.offscreen;
        const saved = {
            viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode,
            exportTransparentBg: r.exportTransparentBg, renderStages: r.renderStages,
            active: project.active_canvas_id,
        };
        const visibility = canvases.map(c => c.visible);
        try {
            if (target) {
                canvases.forEach(c => { c.visible = (c === target); });
                project.active_canvas_id = target.id;
            }
            r.canvas = off;
            r.ctx = idm ? entry.baseCtx : entry.offCtx;
            r._idmNoHighlight = idm;
            r.exportMode = true;
            r.exportTransparentBg = false;
            r.renderStages = null;
            r.viewMode = entry.view;
            const w = Math.max(1, Math.round(Number(r.rasterWidth) || 1920));
            const h = Math.max(1, Math.round(Number(r.rasterHeight) || 1080));
            if (off.width !== w) off.width = w;
            if (off.height !== h) off.height = h;
            const ws = target ? r._canvasWorkspace(target) : { wx: 0, wy: 0 };
            entry.ws = ws;
            r.zoom = 1;
            r.panX = -ws.wx;
            r.panY = -ws.wy;
            r.render();
        } finally {
            r._idmNoHighlight = false;
            canvases.forEach((c, i) => { c.visible = visibility[i]; });
            project.active_canvas_id = saved.active;
            r.canvas = saved.canvas;
            r.ctx = saved.ctx;
            r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.exportTransparentBg;
            r.renderStages = saved.renderStages;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom;
            r.panX = saved.panX;
            r.panY = saved.panY;
        }
        if (idm) return this._outputDisplayCompose(entry, page);
        try {
            page.present(off, { title: `${this._outputDisplayLabel(entry)} - Output` });
        } catch (err) {
            sendClientLog('output_display_present_failed', { message: String(err && err.message || err) });
            return false;
        }
        return true;
    }

    // An IDM Locator output's frame: its last render (entry.base) with the
    // live highlight laid over it in the output's own raster frame, handed
    // to the page.
    _outputDisplayCompose(entry, page) {
        const r = window.canvasRenderer;
        const base = entry.base;
        if (!r || !base || !base.width || !base.height) return false;
        const off = entry.offscreen;
        const ctx = entry.offCtx;
        if (off.width !== base.width) off.width = base.width;
        if (off.height !== base.height) off.height = base.height;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(base, 0, 0);
        const ws = entry.ws || { wx: 0, wy: 0 };
        // The highlight's place is worked out the way this view draws: the
        // Pixel Map positions, whatever tab the designer shows right now.
        const savedView = r.viewMode;
        const hasCanvases = this.project && Array.isArray(this.project.canvases) && this.project.canvases.length;
        try {
            r.viewMode = 'idm';
            ctx.save();
            ctx.translate(-ws.wx, -ws.wy);
            r.renderIdmHighlight(ctx, { exportMode: true, canvasId: hasCanvases ? entry.canvasId : undefined });
            ctx.restore();
        } finally {
            r.viewMode = savedView;
        }
        try {
            page.present(off, { title: `${this._outputDisplayLabel(entry)} - Output` });
        } catch (err) {
            sendClientLog('output_display_present_failed', { message: String(err && err.message || err) });
            return false;
        }
        return true;
    }

    // The IDM Locator's highlight moved or blinked (app-idm-locator.js
    // _idmRepaint): every IDM output with a frame gets the highlight laid
    // over that frame again - a copy, never a render. An output without a
    // frame yet gets one from the next refresh.
    _outputDisplayBlink() {
        const all = Array.isArray(this._outputDisplayWindows) ? this._outputDisplayWindows : [];
        for (const e of all) {
            if (e.view !== 'idm' || !e.base || e.lastSig === null || !e.win || e.win.closed) continue;
            const page = this._outputDisplayPage(e);
            if (page) this._outputDisplayCompose(e, page);
        }
    }
}

for (const k of Object.getOwnPropertyNames(_OutputDisplay.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_OutputDisplay.prototype, k));
    }
}
