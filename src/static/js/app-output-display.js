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
// Every output is 1:1: one canvas pixel per display pixel, at the
// resolution the OS shows for that display, from the top-left corner (Matt,
// 2026-11-09: "one to one means pixel pixel ... a 1920 canvas on a 4K
// display would fill the top left quadrant"). What the canvas leaves unused
// stays black on the output, and a canvas bigger than the display is not
// shown at all: the output says so (output-display.js). There is no scale
// to pick; an old ?scale= on an output's address is ignored.
//
// Where an output opens:
// * In the desktop app the server lists every display (GET
//   /api/output/native) and opens each output as a native window, full
//   screen on the display picked here, with no dragging and no click
//   (output_native.py). A native window is no child of this browser, so its
//   frames go through the server (routes_output.py): the same offscreen
//   render, sent as a PNG, latest frame wins.
// * In a plain browser the output is a browser window this page opened
//   (window.open) and feeds directly.
//   Chromium's Window Management API lets the dialog pick its display;
//   elsewhere the dialog says to drag it there and click for full screen.
//
// The outputs are kept in _outputDisplayWindows (window references, or a
// native output's feed id), the dialog lists and closes them, and they close
// with this window.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const OUTPUT_VIEWS = [
    ['pixel-map', 'Pixel Map'],
    ['cabinet-id', 'Cabinet ID'],
    ['show-look', 'Show Look'],
    ['data-flow', 'Data'],
    ['power', 'Power'],
    ['rigging', 'Header/Footer'],
    // The Pixel Map with every cabinet's modules and the marked ones
    // (app-idm-locator.js), so the crew can find a bad module on the wall.
    ['idm', 'IDM Locator'],
];

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
        // The desktop app lists every display and opens on any of them.
        // Otherwise the browser's own list: without a prompt when it already
        // has the permission, else "Find displays" asks for it.
        this._outputDisplayProbeNative().then((native) => {
            if (!native) this._outputDisplayProbeScreens(false);
        });
        this._outputDisplayNativeSync();
        clearInterval(this._outputDisplayListTimer);
        this._outputDisplayListTimer = setInterval(() => {
            if (modal.style.display === 'none') {
                clearInterval(this._outputDisplayListTimer);
                return;
            }
            this._outputDisplayNativeSync();
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
                <div class="od-row" id="output-display-screen-row"${canPickScreen ? '' : ' hidden'}>
                    <label for="output-display-screen">Display</label>
                    <select id="output-display-screen" data-tooltip="Display, The display the output opens on, full screen. Each is listed with its name, its resolution and its place on the desktop. A display that already has an output is picked last."></select>
                    <button type="button" class="btn" id="output-display-find-screens" data-tooltip="Find displays, Ask the browser for the displays connected to this computer, so each output can open on its own.">Find displays</button>
                </div>
                <div class="od-note" id="output-display-place-note"${canPickScreen ? ' hidden' : ''}>This browser opens each output as a window. Drag it onto its display, then click it for full screen.</div>
                <div class="od-note" id="output-display-note"></div>
                <div class="od-open" id="output-display-open-section">
                    <div class="od-open-title">Open outputs</div>
                    <div id="output-display-open-list"></div>
                </div>
                <div class="od-actions">
                    <button type="button" class="btn" id="output-display-close">Close</button>
                    <button type="button" class="btn btn-primary" id="output-display-open" data-tooltip="Open output, Open the canvas and view above full screen on the chosen display, one canvas pixel per display pixel from the top-left corner. Open as many as you need: each display gets its own output, and every one follows your edits live.">Open output</button>
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
        modal.querySelector('#output-display-screen')
            .addEventListener('change', () => this._outputDisplayUpdateNote());
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
        const screenSel = modal.querySelector('#output-display-screen');
        const screenIdx = screenSel && screenSel.value !== '' ? Number(screenSel.value) : -1;
        return {
            canvasId: modal.querySelector('#output-display-canvas').value || '',
            view: modal.querySelector('#output-display-view').value || 'pixel-map',
            screen: (this._outputDisplayScreens && screenIdx >= 0)
                ? this._outputDisplayScreens[screenIdx] || null : null,
        };
    }

    // The canvas the choice would show, so the note says what 1:1 needs, and
    // warns before opening when the chosen display is smaller than it.
    _outputDisplayUpdateNote() {
        const note = document.getElementById('output-display-note');
        if (!note) return;
        const { canvasId, view, screen } = this._outputDisplayChoice();
        const size = this._outputDisplayRasterSize(canvasId, view);
        let text = !size ? ''
            : `Canvas ${size.width} × ${size.height} at 1:1: one canvas pixel per display pixel, at the display's resolution, from the top-left corner. What the canvas leaves unused stays black.`;
        let tooBig = false;
        if (size && screen) {
            const d = this._outputDisplayResolution(screen);
            if (d && (size.width > d.width || size.height > d.height)) {
                tooBig = true;
                const i = (this._outputDisplayScreens || []).indexOf(screen);
                text = `This canvas is ${size.width} × ${size.height}; ${this._outputDisplayScreenName(i)} is ${d.width} × ${d.height}. Set the display to the canvas size, or use a smaller canvas. Until then its output stays black.`;
            }
        }
        note.textContent = text;
        note.classList.toggle('od-warn', tooBig);
    }

    // A display's resolution as its OS shows it (see output-display.js): a
    // native display's own figures; a browser-listed one is in CSS pixels,
    // which is points on a Mac and the display's pixels / its scale elsewhere.
    _outputDisplayResolution(s) {
        if (!s || !s.width || !s.height) return null;
        if (s.native) return { width: s.width, height: s.height };
        const mac = /Mac/i.test(String(navigator.platform || ''));
        const k = mac ? 1 : (Number(s.devicePixelRatio) || 1);
        return { width: Math.round(s.width * k), height: Math.round(s.height * k) };
    }

    _outputDisplayRasterSize(canvasId, view) {
        const show = view === 'show-look' || view === 'data-flow' || view === 'power' || view === 'rigging';
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

    // ---- displays: the desktop app's, or the browser's ---------------------

    // The desktop app's displays (output_native.py). True when outputs open
    // as native full-screen windows; the dialog then lists those displays
    // and needs no browser permission.
    async _outputDisplayProbeNative() {
        let res = null;
        try {
            const r = await fetch('/api/output/native', { cache: 'no-store' });
            res = r.ok ? await r.json() : null;
        } catch (_) { res = null; }
        const on = !!(res && res.available && Array.isArray(res.displays) && res.displays.length);
        const was = !!this._outputDisplayNative;
        this._outputDisplayNative = on;
        if (on) {
            this._outputDisplayScreenDetails = null;
            this._outputDisplayScreens = res.displays.map(d => ({
                native: true, index: d.index, label: d.name,
                left: d.x, top: d.y, width: d.width, height: d.height,
                isPrimary: !!d.main, scale: d.scale,
            }));
        } else if (was) {
            this._outputDisplayScreens = null;
        }
        this._outputDisplayShowPlacement();
        if (on || was) {
            this._outputDisplayFillScreens();
            this._outputDisplayUpdateNote();
        }
        if (on && !this._outputDisplayNativeLogged) {
            this._outputDisplayNativeLogged = true;
            sendClientLog('output_display_native_displays', { displays: res.displays });
        }
        return on;
    }

    // Which of the display row, Find displays and the drag note show.
    _outputDisplayShowPlacement() {
        const row = document.getElementById('output-display-screen-row');
        const find = document.getElementById('output-display-find-screens');
        const note = document.getElementById('output-display-place-note');
        const native = !!this._outputDisplayNative;
        const canPick = native || typeof window.getScreenDetails === 'function';
        if (row) row.hidden = !canPick;
        if (find) find.hidden = native;
        if (note) note.hidden = canPick;
    }

    async _outputDisplayProbeScreens(ask) {
        if (typeof window.getScreenDetails !== 'function') return;
        if (this._outputDisplayNative) return;
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
                    if (this._outputDisplayNative) return;
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

    // `keepChoice`: a display picked by hand stays picked (false after an
    // output opened, so the next pick moves on to a free display).
    _outputDisplayFillScreens(keepChoice = true) {
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
        // The displays an open output is on now.
        const used = new Set(this.listOutputDisplays().map(e => e.screenIndex).filter(i => i >= 0));
        let firstOther = -1;
        let firstFree = -1;
        // The desktop app cannot say which display this browser is on; the
        // main one is the likely one.
        const here = (s) => (s === current) || (!current && !!s.native && !!s.isPrimary);
        screens.forEach((s, i) => {
            const opt = document.createElement('option');
            opt.value = String(i);
            const tags = [];
            if (s.isPrimary) tags.push('main');
            if (s === current) tags.push('this window');
            if (used.has(i)) tags.push('has an output');
            const d = this._outputDisplayResolution(s) || { width: s.width, height: s.height };
            opt.textContent = `${this._outputDisplayScreenName(i)}: ${d.width} × ${d.height} at ${Math.round(s.left || 0)}, ${Math.round(s.top || 0)}${tags.length ? ' (' + tags.join(', ') + ')' : ''}`;
            sel.appendChild(opt);
            if (firstOther < 0 && !here(s)) firstOther = i;
            if (firstFree < 0 && !here(s) && !used.has(i)) firstFree = i;
        });
        // Another display than this window's is the usual point of it, and
        // one without an output yet is the next one to feed. A display the
        // crew picked stays picked while nothing is opened on it.
        const keep = keepChoice && prev !== '' && screens[Number(prev)] && !used.has(Number(prev));
        const pick = firstFree >= 0 ? firstFree : (firstOther >= 0 ? firstOther : 0);
        sel.value = keep ? prev : String(pick);
        this._outputDisplayUpdateNote();
    }

    _outputDisplayScreenName(i) {
        const s = (this._outputDisplayScreens || [])[i];
        return (s && s.label) || `Display ${i + 1}`;
    }

    // The display a window is on now: the index of the display (of those
    // the browser listed) holding the window's middle, or -1 (no list, or
    // the window cannot be read).
    _outputDisplayScreenOf(win) {
        const screens = this._outputDisplayScreens || [];
        if (!screens.length || !win || win.closed) return -1;
        try {
            const x = (win.screenX || 0) + (win.outerWidth || 0) / 2;
            const y = (win.screenY || 0) + (win.outerHeight || 0) / 2;
            return screens.findIndex(s => x >= s.left && x < s.left + s.width && y >= s.top && y < s.top + s.height);
        } catch (_) {
            return -1;
        }
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
        // The next output goes to a display that has none yet.
        this._outputDisplayFillScreens(false);
    }

    // Open one output, always 1:1. choice: { canvasId, view, screen }. Returns
    // the entry, or null when the browser refused the window.
    openOutputDisplay(choice) {
        const view = OUTPUT_VIEWS.some(([v]) => v === choice.view) ? choice.view : 'pixel-map';
        const canvasId = choice.canvasId || '';
        if (choice.screen && choice.screen.native) return this._outputDisplayOpenNative(canvasId, view, choice.screen);
        const qs = new URLSearchParams({ canvas: canvasId, view });
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
        // Each output its own window: a name no earlier session's window
        // still holds, so an open never lands in another output's window.
        if (!this._outputDisplayTag) this._outputDisplayTag = Date.now().toString(36);
        const win = window.open(`/output?${qs.toString()}`, `lrd-output-${this._outputDisplayTag}-${id}`, features);
        if (!win) {
            sendClientLog('output_display_blocked', { canvasId, view });
            return null;
        }
        const chosen = s ? (this._outputDisplayScreens || []).indexOf(s) : -1;
        const entry = { id, win, canvasId, view, lastSig: null, chosenScreen: chosen };
        this._outputDisplayTrack(entry);
        sendClientLog('output_display_open', {
            id, canvasId, view, native: false, screen: !!s,
            display: s ? { left: s.left, top: s.top, width: s.width, height: s.height, dpr: s.devicePixelRatio } : null,
            raster: this._outputDisplayRasterSize(canvasId, view),
        });
        return entry;
    }

    // The desktop app opens this output as a native window, full screen on
    // display `s` (output_native.py). The entry is back at once; its feed id
    // follows when the window is up, and the first frame goes out then.
    _outputDisplayOpenNative(canvasId, view, s) {
        this._outputDisplaySeq = (this._outputDisplaySeq || 0) + 1;
        const id = this._outputDisplaySeq;
        const entry = {
            id, win: null, native: true, feed: '', closed: false, canvasId, view,
            lastSig: null, chosenScreen: (this._outputDisplayScreens || []).indexOf(s),
            displayIndex: s.index, displayName: s.label || `Display ${s.index + 1}`,
        };
        this._outputDisplayTrack(entry);
        const raster = this._outputDisplayRasterSize(canvasId, view);
        entry.opening = fetch('/api/output/native/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas: canvasId, view, display: s.index, title: `${this._outputDisplayLabel(entry)} · Output` }),
        }).then(r => r.json().catch(() => ({})).then(j => {
            if (!r.ok || !j.ok || !j.id) throw new Error(j.error || `HTTP ${r.status}`);
            entry.feed = j.id;
            entry.lastSig = null;
            sendClientLog('output_display_open', {
                id, canvasId, view, native: true, feed: j.id, display: j.display, raster,
            });
            if (entry.closed) {
                this._outputDisplayNativeClose([entry.feed]);
                return;
            }
            this._outputDisplayRefresh();
            this._outputDisplayRenderList();
        })).catch(err => {
            entry.closed = true;
            const note = document.getElementById('output-display-note');
            if (note) note.textContent = 'The output window could not be opened. Try again, or restart the app.';
            sendClientLog('output_display_native_failed', { id, message: String(err && err.message || err) });
            this._outputDisplayRenderList();
        });
        return entry;
    }

    // Is this output still up? A native one until it is closed or the
    // server says its window went; a browser one while its window is open.
    _outputDisplayLive(e) {
        if (!e) return false;
        if (e.native) return !e.closed;
        return !!(e.win && !e.win.closed);
    }

    // Close native outputs by feed id. A beacon, so it still goes out while
    // this page is being unloaded.
    _outputDisplayNativeClose(feeds) {
        const ids = (feeds || []).filter(Boolean);
        if (!ids.length) return;
        const body = JSON.stringify({ ids });
        try {
            if (navigator.sendBeacon && navigator.sendBeacon('/api/output/native/close', new Blob([body], { type: 'text/plain' }))) return;
        } catch (_) { /* fall through */ }
        fetch('/api/output/native/close', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true })
            .catch(() => {});
    }

    // A native output closed in its own window (Esc) or by the OS: the
    // server no longer lists it.
    _outputDisplayNativeSync() {
        const natives = (this._outputDisplayWindows || []).filter(e => e.native && !e.closed && e.feed);
        if (!natives.length || this._outputDisplaySyncing) return;
        this._outputDisplaySyncing = true;
        fetch('/api/output/native/list', { cache: 'no-store' })
            .then(r => (r.ok ? r.json() : null))
            .then(j => {
                if (!j || !Array.isArray(j.open)) return;
                const open = new Set(j.open);
                let gone = false;
                natives.forEach(e => {
                    if (!open.has(e.feed)) { e.closed = true; gone = true; }
                });
                if (gone) this._outputDisplayRenderList();
            })
            .catch(() => {})
            .finally(() => { this._outputDisplaySyncing = false; });
    }

    // The stand-in for a native output's page: each frame goes to the
    // server as a PNG at the raster size. One send at a time; a frame that
    // comes while one is on its way replaces any other waiting, so a slow
    // display skips frames instead of falling behind.
    _outputDisplayNativePage(entry) {
        if (!entry.remote) {
            entry.remote = {
                present: (src, meta) => {
                    entry.sendSrc = src;
                    entry.sendTitle = (meta && meta.title) || '';
                    this._outputDisplayNativeSend(entry);
                },
                missing: (text) => {
                    fetch(`/api/output/feed/${encodeURIComponent(entry.feed)}/message`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text, title: entry.sendTitle || '' }),
                    }).then(r => { if (r.status === 404) this._outputDisplayNativeGone(entry); })
                        .catch(() => {});
                },
            };
        }
        return entry.remote;
    }

    _outputDisplayNativeSend(entry) {
        if (entry.sending) { entry.dirty = true; return; }
        const src = entry.sendSrc;
        if (!src || entry.closed || !entry.feed) return;
        entry.sending = true;
        entry.dirty = false;
        const done = () => {
            entry.sending = false;
            if (entry.dirty && !entry.closed) this._outputDisplayNativeSend(entry);
        };
        try {
            src.toBlob((blob) => {
                if (!blob || entry.closed) { done(); return; }
                fetch(`/api/output/feed/${encodeURIComponent(entry.feed)}/frame`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'image/png', 'X-Output-Title': encodeURIComponent(entry.sendTitle || '') },
                    body: blob,
                }).then(r => { if (r.status === 404) this._outputDisplayNativeGone(entry); })
                    .catch(() => {})
                    .finally(done);
            }, 'image/png');
        } catch (err) {
            sendClientLog('output_display_present_failed', { message: String(err && err.message || err) });
            done();
        }
    }

    _outputDisplayNativeGone(entry) {
        if (entry.closed) return;
        entry.closed = true;
        this._outputDisplayRenderList();
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
        this._outputDisplayWindows = all.filter(e => this._outputDisplayLive(e));
        return this._outputDisplayWindows.map(e => {
            const screenIndex = this._outputDisplayEntryScreen(e);
            return {
                id: e.id, canvasId: e.canvasId, view: e.view, screenIndex,
                display: screenIndex >= 0 ? this._outputDisplayScreenName(screenIndex) : '',
                label: this._outputDisplayLabel(e, screenIndex),
            };
        });
    }

    // The display an output is on: where its window is now, else the one it
    // was opened on; -1 when the browser lists no displays.
    _outputDisplayEntryScreen(entry) {
        if (entry.native) {
            return (this._outputDisplayScreens || []).findIndex(s => s && s.native && s.index === entry.displayIndex);
        }
        const now = this._outputDisplayScreenOf(entry.win);
        if (now >= 0) return now;
        const n = (this._outputDisplayScreens || []).length;
        return (entry.chosenScreen >= 0 && entry.chosenScreen < n) ? entry.chosenScreen : -1;
    }

    closeOutputDisplay(id) {
        const all = Array.isArray(this._outputDisplayWindows) ? this._outputDisplayWindows : [];
        const entry = all.find(e => e.id === id);
        if (entry && entry.native) {
            entry.closed = true;
            this._outputDisplayNativeClose([entry.feed]);
        } else if (entry && entry.win && !entry.win.closed) {
            entry.win.close();
        }
        this._outputDisplayWindows = all.filter(e => e !== entry);
        this._outputDisplayRenderList();
        sendClientLog('output_display_close', { id, native: !!(entry && entry.native) });
    }

    closeAllOutputDisplays() {
        const feeds = [];
        (this._outputDisplayWindows || []).forEach(e => {
            if (e.native) {
                e.closed = true;
                feeds.push(e.feed);
                return;
            }
            try { if (e.win && !e.win.closed) e.win.close(); } catch (_) { /* gone */ }
        });
        this._outputDisplayNativeClose(feeds);
        this._outputDisplayWindows = [];
    }

    // Canvas · view, and the display it is on when the browser
    // can say (`screenIndex`, worked out when not given).
    _outputDisplayLabel(entry, screenIndex) {
        const c = this._outputDisplayCanvases().find(x => x.id === entry.canvasId);
        const v = OUTPUT_VIEWS.find(([k]) => k === entry.view);
        const i = screenIndex === undefined ? this._outputDisplayEntryScreen(entry) : screenIndex;
        const on = entry.native ? ` · on ${entry.displayName}`
            : (i >= 0 ? ` · on ${this._outputDisplayScreenName(i)}` : '');
        return `${c ? c.name : 'Missing canvas'} · ${v ? v[1] : entry.view}${on}`;
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
        // With one up, the button opens another beside it.
        const open = document.getElementById('output-display-open');
        if (open) open.textContent = list.length ? 'Open another output' : 'Open output';
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
            btn.dataset.tooltip = 'Close output, Close this output window. The other outputs stay up.';
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
                lastSig: null,
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
    // switches and which images have finished loading. Not the IDM
    // Locator's live highlight: an IDM output lays it over its last frame
    // (_outputDisplayBlink), so a move never costs a render.
    _outputDisplaySignature() {
        const r = window.canvasRenderer;
        const flags = [];
        for (const k of Object.keys(r)) {
            // (spacePressed among them: holding Space to pan changes nothing
            // on the wall)
            if (/^_|mouse|drag|hover|cursor|select|pan|zoom|^is[A-Z]|viewMode|export|render|probe|pulse|pressed/i.test(k)) continue;
            const v = r[k];
            if (typeof v === 'boolean' || typeof v === 'string') flags.push(`${k}=${v}`);
        }
        const images = ((this.project && this.project.layers) || [])
            .map(l => (l && l._imageObj) ? (l._imageObj.complete ? '1' : '0') : '').join('');
        const replacer = (k, v) => (k === 'idmHighlight' ? undefined : this._snapshotReplacer(k, v));
        return JSON.stringify(this.project, replacer)
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
        if (entry.native) return (entry.closed || !entry.feed) ? null : this._outputDisplayNativePage(entry);
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
            // The TARGET canvas's raster for this view (pixel or Show Look),
            // read from the canvas itself rather than through the renderer's
            // active-canvas getters.
            const size = target ? this._outputDisplayRasterSize(target.id, entry.view) : null;
            const w = Math.max(1, Math.round(Number(size ? size.width : r.rasterWidth) || 1920));
            const h = Math.max(1, Math.round(Number(size ? size.height : r.rasterHeight) || 1080));
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
            page.present(off, { title: `${this._outputDisplayLabel(entry)} · Output` });
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
            // The designer's mouse over this canvas, over everything
            // (app-idm-locator.js _idmPointerFor), sized to the raster so
            // it reads on the wall: 6% of its shorter side, 24 px at least.
            const p = typeof this._idmPointerFor === 'function' ? this._idmPointerFor(entry.canvasId) : null;
            if (p && typeof r.renderIdmPointer === 'function') {
                r.renderIdmPointer(ctx, p.x, p.y, Math.max(24, Math.round(Math.min(base.width, base.height) * 0.06)));
            }
            ctx.restore();
        } finally {
            r.viewMode = savedView;
        }
        try {
            page.present(off, { title: `${this._outputDisplayLabel(entry)} · Output` });
        } catch (err) {
            sendClientLog('output_display_present_failed', { message: String(err && err.message || err) });
            return false;
        }
        return true;
    }

    // The IDM Locator's highlight moved or blinked (app-idm-locator.js
    // _idmRepaint), or the designer's mouse moved on the wall
    // (_idmPointerAt, which names the canvases in `canvasIds`): every IDM
    // output with a frame (of those canvases) gets the highlight and the
    // mouse laid over that frame again - a copy, never a render. An output
    // without a frame yet gets one from the next refresh.
    _outputDisplayBlink(canvasIds) {
        const all = Array.isArray(this._outputDisplayWindows) ? this._outputDisplayWindows : [];
        for (const e of all) {
            if (e.view !== 'idm' || !e.base || e.lastSig === null || !this._outputDisplayLive(e)) continue;
            if (canvasIds && !canvasIds.has(e.canvasId)) continue;
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
