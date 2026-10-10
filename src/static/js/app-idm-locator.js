// app-idm-locator: the IDM Locator tab. A cabinet is built from modules
// (2, 4, 16 ...); when one goes bad the crew marks it here, and Output to
// Display puts the marks on a second monitor so the module can be found on
// the real wall. The view draws each canvas exactly like the Pixel Map, with
// every cabinet's module grid and the marks over it (canvas-idm.js).
//
// Each screen keeps its block on the layer:
//   idm: {modulesX, modulesY, marks: {"col,row,mx,my": {style, color}}}
// modulesX / modulesY are one cabinet's modules across and down (1 x 1 by
// default - the whole cabinet one module); a mark is keyed by the cabinet's
// grid column and row and the module's column and row inside the full
// cabinet, and keeps its own style ('color' fills the module, 'x' draws an
// X corner to corner) and colour. The server's app.sanitize_idm holds the
// shape (and drops marks a geometry change leaves on nothing); idmSanitize
// below is its twin, so a restore never comes back "repaired".
//
// Every edit - a click, a drag stroke, a module count, a clear - goes
// through updateLayers like any other layer edit: it saves, reaches the
// other machines on the LAN as layer_updated, and is one undo step. Copies
// keep the module layout but never the marks (a copy is another physical
// wall: idmCopyLayout, app-clipboard stripScreenFeeds, the server's
// strip_copied_idm_marks); a preset keeps the layout and never the marks.
// Nothing here exports, prints or reaches the 3D view.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const MAX_MODULES = 64;
const DEFAULT_COLOR = '#ff1a1a';
const FLASH_MS = 1800;
const BLINK_MS = 250;
const STYLE_KEY = 'lrdIdmMarkStyle';
const COLOR_KEY = 'lrdIdmMarkColor';

function idmCount(value) {
    if (typeof value === 'boolean' || value === null || value === undefined) return 1;
    const n = Number(value);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(MAX_MODULES, Math.trunc(n)));
}

// '#rrggbb' (lower case), or null when `value` is not a colour.
export function idmColor(value) {
    if (typeof value !== 'string') return null;
    const text = value.trim();
    let m = /^#?([0-9a-fA-F]{6})$/.exec(text);
    if (m) return '#' + m[1].toLowerCase();
    m = /^#?([0-9a-fA-F]{3})$/.exec(text);
    if (m) return '#' + m[1].split('').map(c => c + c).join('').toLowerCase();
    return null;
}

function idmKey(value) {
    const parts = String(value).split(',');
    if (parts.length !== 4) return null;
    const out = [];
    for (const part of parts) {
        const text = part.trim();
        if (!/^\d+$/.test(text)) return null;
        out.push(parseInt(text, 10));
    }
    return out.join(',');
}

function idmValidKeys(layer, modulesX, modulesY) {
    const r = window.canvasRenderer;
    const keys = new Set();
    if (!r || typeof r.idmModuleCells !== 'function') return keys;
    const seen = r._idmVisibleLookup(layer);
    for (const panel of (layer.panels || [])) {
        if (!panel) continue;
        for (const c of r.idmModuleCells(layer, panel, modulesX, modulesY, seen)) {
            keys.add(r.idmCellKey(panel, c));
        }
    }
    return keys;
}

// The client's copy of app.sanitize_idm: the same block for the same input
// against the same screen. null when `value` is not a block or the layer is
// not a screen.
export function idmSanitize(value, layer) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (!layer || (layer.type || 'screen') !== 'screen') return null;
    const out = { modulesX: idmCount(value.modulesX), modulesY: idmCount(value.modulesY), marks: {} };
    const raw = value.marks;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && Object.keys(raw).length) {
        const valid = idmValidKeys(layer, out.modulesX, out.modulesY);
        Object.keys(raw).forEach(key => {
            const k = idmKey(key);
            const mark = raw[key];
            if (!k || !valid.has(k) || !mark || typeof mark !== 'object' || Array.isArray(mark)) return;
            out.marks[k] = {
                style: mark.style === 'x' ? 'x' : 'color',
                color: idmColor(mark.color) || DEFAULT_COLOR,
            };
        });
    }
    return out;
}

// What a copy of `layer` carries: its module layout, no marks. Undefined
// when the screen never had a block (the copy then has none either).
export function idmCopyLayout(layer) {
    if (!layer || !layer.idm || typeof layer.idm !== 'object' || Array.isArray(layer.idm)) return undefined;
    return { modulesX: idmCount(layer.idm.modulesX), modulesY: idmCount(layer.idm.modulesY), marks: {} };
}

function markCount(layer) {
    const marks = layer && layer.idm && layer.idm.marks;
    return (marks && typeof marks === 'object') ? Object.keys(marks).length : 0;
}

function plural(n, word) {
    return `${n} ${word}${n === 1 ? '' : 's'}`;
}

class _IdmLocator {
    _idmState() {
        if (!this._idmS) {
            let style = 'color';
            let color = DEFAULT_COLOR;
            try {
                style = localStorage.getItem(STYLE_KEY) === 'x' ? 'x' : 'color';
                color = idmColor(localStorage.getItem(COLOR_KEY)) || DEFAULT_COLOR;
            } catch (_) { /* storage blocked: the defaults */ }
            this._idmS = {
                active: false, wired: false, style, color,
                stroke: null, flash: null, flashTimer: null,
                fieldsKey: '', listKey: '',
            };
        }
        return this._idmS;
    }

    // ── wiring ────────────────────────────────────────────────────────────

    // Once, from setupEventListeners (app-core).
    _idmWire() {
        const st = this._idmState();
        if (st.wired) return;
        st.wired = true;
        const on = (id, ev, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener(ev, fn);
        };
        document.querySelectorAll('[data-idm-style]').forEach(btn => {
            btn.addEventListener('click', () => this._idmSetStyle(btn.dataset.idmStyle));
        });
        on('idm-color', 'input', (e) => this._idmSetColor(e.target.value));
        on('idm-color', 'change', (e) => this._idmSetColor(e.target.value));
        on('idm-clear-screen', 'click', () => this._idmClearSelected());
        on('idm-clear-all', 'click', () => this._idmClearAll());
        on('idm-modules-x', 'change', () => this._idmCommitModules());
        on('idm-modules-y', 'change', () => this._idmCommitModules());
        on('idm-list', 'click', (e) => {
            const row = e.target.closest('[data-idm-key]');
            if (!row) return;
            this._idmFlashModule(Number(row.dataset.idmLayer), row.dataset.idmKey);
        });
        this._idmSyncToolbar();
    }

    // The view-tab click (app-wiring _wireViewTabs).
    _idmSetActive(on) {
        const st = this._idmState();
        st.active = !!on;
        const bar = document.getElementById('idm-toolbar');
        if (bar) bar.hidden = !st.active;
        if (!st.active) {
            st.stroke = null;
            if (window.canvasRenderer) window.canvasRenderer.isIdmPainting = false;
            return;
        }
        st.fieldsKey = '';
        st.listKey = '';
        this._idmSyncToolbar();
    }

    // canvas.js render() calls this after every designer redraw of the tab:
    // any edit, selection change, undo, load or LAN update ends in one. The
    // panel only touches the DOM when what it shows has changed.
    _idmOnRender() {
        this._idmRefreshPanel();
    }

    _idmSetStyle(style) {
        const st = this._idmState();
        st.style = style === 'x' ? 'x' : 'color';
        try { localStorage.setItem(STYLE_KEY, st.style); } catch (_) { /* per-viewer only */ }
        this._idmSyncToolbar();
    }

    _idmSetColor(value) {
        const st = this._idmState();
        const c = idmColor(value);
        if (!c) return;
        st.color = c;
        try { localStorage.setItem(COLOR_KEY, c); } catch (_) { /* per-viewer only */ }
    }

    _idmSyncToolbar() {
        const st = this._idmState();
        document.querySelectorAll('[data-idm-style]').forEach(btn => {
            const active = btn.dataset.idmStyle === st.style;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const colour = document.getElementById('idm-color');
        if (colour && colour.value.toLowerCase() !== st.color) colour.value = st.color;
    }

    // ── marking ───────────────────────────────────────────────────────────

    // A press on the canvas in this view (canvas-input.js). True when the
    // press is this view's own - a module was marked or cleared and the
    // stroke begun, or the press landed on a screen that cannot be marked
    // (locked, or a blanked cabinet) - so the canvas does nothing else
    // with it. False off every screen: the press then selects as usual.
    _idmPointerDown(worldX, worldY) {
        const r = window.canvasRenderer;
        if (!r || typeof r.idmHitAt !== 'function') return false;
        const hit = r.idmHitAt(worldX, worldY);
        if (!hit) return false;
        const layer = hit.layer;
        if (!this.currentLayer || this.currentLayer.id !== layer.id) r._selectLayerFromCanvas(layer);
        if (layer.locked) {
            this._toast(`${layer.name || 'This screen'} is locked. Unlock it to mark its modules.`);
            return true;
        }
        if (!hit.cell) {
            this._toast('A blanked cabinet has no modules to mark.');
            return true;
        }
        const st = this._idmState();
        const key = r.idmCellKey(hit.panel, hit.cell);
        const before = JSON.stringify(layer.idm || null);
        const block = this._idmEnsureBlock(layer);
        st.stroke = {
            layerId: layer.id,
            mode: block.marks[key] ? 'clear' : 'mark',
            touched: new Set(),
            before,
        };
        this._idmApply(layer, key);
        r.render();
        return true;
    }

    // The drag: every module the pointer crosses on the stroke's screen
    // takes the stroke's mode - the first module decided paint or clear.
    _idmPointerMove(worldX, worldY) {
        const st = this._idmState();
        const stroke = st.stroke;
        const r = window.canvasRenderer;
        if (!stroke || !r) return;
        const hit = r.idmHitAt(worldX, worldY);
        if (!hit || !hit.cell || hit.layer.id !== stroke.layerId) return;
        const key = r.idmCellKey(hit.panel, hit.cell);
        if (stroke.touched.has(key)) return;
        this._idmApply(hit.layer, key);
        r.render();
    }

    // The stroke ends: one layer edit, one undo step.
    _idmPointerUp() {
        const st = this._idmState();
        const stroke = st.stroke;
        st.stroke = null;
        if (!stroke || !this.project) return;
        const layer = (this.project.layers || []).find(l => l.id === stroke.layerId);
        if (!layer || JSON.stringify(layer.idm || null) === stroke.before) return;
        const action = stroke.mode === 'clear'
            ? (stroke.touched.size > 1 ? 'Clear Module Marks' : 'Clear Module Mark')
            : (stroke.touched.size > 1 ? 'Mark Modules' : 'Mark Module');
        sendClientLog('idm_mark', { id: layer.id, mode: stroke.mode, modules: [...stroke.touched], style: st.style, color: st.color });
        this.updateLayers([layer], true, action);
    }

    // `layer.idm` as a fresh, whole block (its own marks object), so an
    // edit never writes into an object an earlier state still holds.
    _idmEnsureBlock(layer) {
        const r = window.canvasRenderer;
        const counts = r ? r.idmCounts(layer) : { x: 1, y: 1 };
        const marks = (layer.idm && layer.idm.marks && typeof layer.idm.marks === 'object' && !Array.isArray(layer.idm.marks))
            ? { ...layer.idm.marks } : {};
        layer.idm = { modulesX: counts.x, modulesY: counts.y, marks };
        return layer.idm;
    }

    _idmApply(layer, key) {
        const st = this._idmState();
        const stroke = st.stroke;
        if (!stroke) return;
        stroke.touched.add(key);
        if (stroke.mode === 'clear') delete layer.idm.marks[key];
        else layer.idm.marks[key] = { style: st.style, color: st.color };
    }

    // ── module counts and clears ──────────────────────────────────────────

    _idmSelectedScreens() {
        const list = typeof this.getSelectedLayers === 'function' ? this.getSelectedLayers() : [];
        return list.filter(l => l && (l.type || 'screen') === 'screen');
    }

    // The two fields, committed together (Enter or Tab ends the edit and
    // fires change - helpers.js installEnterEndsEdit). A field left empty
    // (a mixed selection's) keeps each screen's own figure. A change of
    // count on a screen with marks clears them, after a confirm that says
    // how many.
    _idmCommitModules() {
        const r = window.canvasRenderer;
        const read = (id) => {
            const el = document.getElementById(id);
            const text = el ? String(el.value).trim() : '';
            if (text === '') return { keep: true };
            const n = Number(text);
            if (!Number.isFinite(n)) return { bad: true };
            return { value: idmCount(n) };
        };
        const ax = read('idm-modules-x');
        const ay = read('idm-modules-y');
        const st = this._idmState();
        if (ax.bad || ay.bad || !r) {
            this._idmRevertFields();
            return;
        }
        const screens = this._idmSelectedScreens();
        const locked = screens.filter(l => l.locked);
        const changes = [];
        screens.filter(l => !l.locked).forEach(layer => {
            const cur = r.idmCounts(layer);
            const nx = ax.keep ? cur.x : ax.value;
            const ny = ay.keep ? cur.y : ay.value;
            if (nx !== cur.x || ny !== cur.y) changes.push({ layer, nx, ny });
        });
        if (locked.length) this._toast(`${plural(locked.length, 'locked screen')} kept ${locked.length === 1 ? 'its' : 'their'} modules.`);
        if (!changes.length) {
            this._idmRevertFields();
            return;
        }
        const losing = changes.filter(c => markCount(c.layer) > 0);
        const lost = losing.reduce((n, c) => n + markCount(c.layer), 0);
        if (lost > 0) {
            const msg = losing.length === 1
                ? `Changing the modules on ${losing[0].layer.name || 'this screen'} clears its ${plural(lost, 'mark')}. Continue?`
                : `Changing the modules clears ${plural(lost, 'mark')} on ${losing.length} screens. Continue?`;
            if (!window.confirm(msg)) {
                this._idmRevertFields();
                return;
            }
        }
        changes.forEach(c => {
            c.layer.idm = { modulesX: c.nx, modulesY: c.ny, marks: {} };
        });
        sendClientLog('idm_modules', { ids: changes.map(c => c.layer.id), x: ax.value, y: ay.value, cleared: lost });
        this.updateLayers(changes.map(c => c.layer), true, 'Set Modules');
        st.fieldsKey = '';
        r.render();
    }

    _idmClearLayers(layers, action) {
        const open = layers.filter(l => !l.locked && markCount(l) > 0);
        const locked = layers.filter(l => l.locked && markCount(l) > 0);
        if (locked.length) this._toast(`${plural(locked.length, 'locked screen')} kept ${locked.length === 1 ? 'its' : 'their'} marks.`);
        if (!open.length) return 0;
        open.forEach(layer => {
            this._idmEnsureBlock(layer);
            layer.idm.marks = {};
        });
        sendClientLog('idm_clear', { action, ids: open.map(l => l.id) });
        this.updateLayers(open, true, action);
        if (window.canvasRenderer) window.canvasRenderer.render();
        return open.length;
    }

    _idmClearSelected() {
        const screens = this._idmSelectedScreens();
        if (!screens.some(l => markCount(l) > 0)) {
            this._toast(screens.length ? 'The selected screens have no marks.' : 'Select a screen first.');
            return;
        }
        this._idmClearLayers(screens, 'Clear Screen Marks');
    }

    _idmClearAll() {
        const screens = ((this.project && this.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen' && markCount(l) > 0);
        if (!screens.length) {
            this._toast('There are no marks to clear.');
            return;
        }
        const total = screens.reduce((n, l) => n + markCount(l), 0);
        const msg = `Clear all ${plural(total, 'mark')} on ${plural(screens.length, 'screen')}?`;
        if (!window.confirm(msg)) return;
        this._idmClearLayers(screens, 'Clear All Marks');
    }

    // ── echoes, presets ───────────────────────────────────────────────────

    // updateLayers merges each PUT's echo onto the layer; the marks the
    // browser holds NOW are the newest (a second click can land while the
    // first PUT is out), held to the screen the server sent back - so a
    // mark the server dropped with a column stays dropped.
    _idmMergeEcho(live, updated) {
        if (!live || !updated || live.idm === undefined) return;
        const clean = idmSanitize(live.idm, updated);
        if (clean) updated.idm = clean;
        else delete updated.idm;
    }

    // A preset keeps the module layout, never the marks.
    _idmPresetLayout(layer) {
        const copy = idmCopyLayout(layer);
        return copy ? { modulesX: copy.modulesX, modulesY: copy.modulesY } : undefined;
    }

    // A preset's layout onto a screen: the screen's marks stay when the
    // layout is the one it already has, and go when it is not.
    _idmApplyPresetLayout(layer, given) {
        if (!layer || !given || typeof given !== 'object' || Array.isArray(given)) return;
        const nx = idmCount(given.modulesX);
        const ny = idmCount(given.modulesY);
        const r = window.canvasRenderer;
        const cur = r ? r.idmCounts(layer) : { x: 1, y: 1 };
        const keep = cur.x === nx && cur.y === ny && layer.idm && layer.idm.marks;
        layer.idm = { modulesX: nx, modulesY: ny, marks: keep ? { ...layer.idm.marks } : {} };
    }

    // ── the panel ─────────────────────────────────────────────────────────

    _idmRefreshPanel() {
        const st = this._idmState();
        if (!st.active) return;
        this._idmRefreshFields();
        this._idmRenderList();
    }

    // The fields back to what the screens hold, even the one with the
    // caret (a refused or unusable entry).
    _idmRevertFields() {
        const st = this._idmState();
        st.fieldsKey = '';
        this._idmRefreshFields(true);
    }

    _idmRefreshFields(force = false) {
        const st = this._idmState();
        const r = window.canvasRenderer;
        const screens = this._idmSelectedScreens();
        const none = document.getElementById('idm-none');
        const fields = document.getElementById('idm-fields');
        if (!fields || !r) return;
        const counts = screens.map(l => r.idmCounts(l));
        const key = JSON.stringify([screens.map(l => [l.id, l.name, l.cabinet_width, l.cabinet_height, l.locked]), counts]);
        if (key === st.fieldsKey) return;
        st.fieldsKey = key;
        if (none) none.hidden = screens.length > 0;
        fields.hidden = screens.length === 0;
        if (!screens.length) return;
        const name = document.getElementById('idm-screen-name');
        if (name) name.textContent = screens.length === 1 ? (screens[0].name || 'Screen') : `${screens.length} screens`;
        const put = (id, values) => {
            const el = document.getElementById(id);
            if (!el) return;
            const mixed = values.some(v => v !== values[0]);
            if (!force && document.activeElement === el) return;
            el.value = mixed ? '' : String(values[0]);
            el.placeholder = mixed ? '-' : '';
        };
        put('idm-modules-x', counts.map(c => c.x));
        put('idm-modules-y', counts.map(c => c.y));
        const size = document.getElementById('idm-module-size');
        if (size) {
            const span = (total, n) => {
                const w = [];
                for (let k = 0; k < n; k++) w.push(Math.floor(total * (k + 1) / n) - Math.floor(total * k / n));
                const lo = Math.min(...w), hi = Math.max(...w);
                return lo === hi ? String(lo) : `${lo}-${hi}`;
            };
            const sizes = new Set(screens.map((l, i) => {
                const W = Math.round(Number(l.cabinet_width) || 0), H = Math.round(Number(l.cabinet_height) || 0);
                if (W <= 0 || H <= 0) return '';
                return `${span(W, counts[i].x)} × ${span(H, counts[i].y)} px`;
            }));
            size.textContent = sizes.size === 1 && [...sizes][0] ? `Each module: ${[...sizes][0]}` : '';
        }
    }

    // Every mark, screen by screen: Screen · Cabinet ID · Module N, and the
    // module's row and column inside its cabinet. Modules are numbered 1..
    // row by row from the top-left of the cabinet as seen from the front
    // (the screen as built, before any Pixel Map rotation). Cabinet IDs are
    // the Cabinet ID view's own (canvas-labels cabinetIdLabeler).
    _idmMarkGroups() {
        const r = window.canvasRenderer;
        const groups = [];
        if (!r || !this.project) return groups;
        for (const layer of (this.project.layers || [])) {
            if (!layer || (layer.type || 'screen') !== 'screen' || markCount(layer) === 0) continue;
            const labelOf = r.cabinetIdLabeler(layer);
            const counts = r.idmCounts(layer);
            const seen = r._idmVisibleLookup(layer);
            const byCell = new Map();
            (layer.panels || []).forEach(p => { if (p) byCell.set(`${p.col || 0},${p.row || 0}`, p); });
            const rows = [];
            Object.keys(layer.idm.marks).forEach(key => {
                const parts = key.split(',').map(n => parseInt(n, 10));
                const panel = byCell.get(`${parts[0]},${parts[1]}`);
                if (!panel) return;
                const cells = r.idmModuleCells(layer, panel, counts.x, counts.y, seen);
                const index = cells.findIndex(c => c.mx === parts[2] && c.my === parts[3]);
                if (index < 0) return;
                const xs = [...new Set(cells.map(c => c.mx))].sort((a, b) => a - b);
                const ys = [...new Set(cells.map(c => c.my))].sort((a, b) => a - b);
                const mark = layer.idm.marks[key];
                rows.push({
                    key, panel, index,
                    cabinet: labelOf(panel),
                    module: index + 1,
                    row: ys.indexOf(parts[3]) + 1,
                    col: xs.indexOf(parts[2]) + 1,
                    style: mark.style === 'x' ? 'x' : 'color',
                    color: idmColor(mark.color) || DEFAULT_COLOR,
                });
            });
            rows.sort((a, b) => (a.panel.row - b.panel.row) || (a.panel.col - b.panel.col) || (a.index - b.index));
            if (rows.length) groups.push({ layer, rows });
        }
        return groups;
    }

    _idmRenderList() {
        const st = this._idmState();
        const host = document.getElementById('idm-list');
        const count = document.getElementById('idm-count');
        if (!host) return;
        const groups = this._idmMarkGroups();
        const flash = st.flash && Date.now() < st.flash.until ? `${st.flash.layerId}:${st.flash.key}` : '';
        const key = JSON.stringify([flash, groups.map(g => [g.layer.id, g.layer.name,
            g.rows.map(x => [x.key, x.cabinet, x.module, x.row, x.col, x.style, x.color])])]);
        if (key === st.listKey) return;
        st.listKey = key;
        const total = groups.reduce((n, g) => n + g.rows.length, 0);
        if (count) count.textContent = total ? `(${total})` : '';
        host.innerHTML = '';
        if (!groups.length) {
            const empty = document.createElement('div');
            empty.className = 'idm-empty';
            empty.textContent = 'No marks. Click a module in the view to mark it.';
            host.appendChild(empty);
            return;
        }
        groups.forEach(g => {
            const head = document.createElement('div');
            head.className = 'idm-group';
            head.textContent = `${g.layer.name || 'Screen'} · ${plural(g.rows.length, 'mark')}`;
            host.appendChild(head);
            g.rows.forEach(x => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'idm-row';
                if (flash === `${g.layer.id}:${x.key}`) row.classList.add('active');
                row.dataset.idmLayer = String(g.layer.id);
                row.dataset.idmKey = x.key;
                const chip = document.createElement('span');
                chip.className = 'idm-chip' + (x.style === 'x' ? ' idm-chip-x' : '');
                if (x.style === 'x') chip.style.setProperty('--idm-chip', x.color);
                else chip.style.background = x.color;
                const text = document.createElement('span');
                text.className = 'idm-row-text';
                text.textContent = `${g.layer.name || 'Screen'} · ${x.cabinet} · Module ${x.module} `;
                const where = document.createElement('span');
                where.className = 'idm-row-where';
                where.textContent = `(row ${x.row}, col ${x.col})`;
                text.appendChild(where);
                row.title = `${g.layer.name || 'Screen'} · ${x.cabinet} · Module ${x.module} (row ${x.row}, col ${x.col})`;
                row.appendChild(chip);
                row.appendChild(text);
                host.appendChild(row);
            });
        });
    }

    // A row of the list: select its screen and make the module blink in
    // the view for a moment.
    _idmFlashModule(layerId, key) {
        const st = this._idmState();
        const layer = ((this.project && this.project.layers) || []).find(l => l.id === layerId);
        if (!layer) return;
        if (!this.currentLayer || this.currentLayer.id !== layer.id
                || (this.selectedLayerIds && this.selectedLayerIds.size > 1)) {
            this.selectLayer(layer);
        }
        const now = Date.now();
        st.flash = { layerId, key, start: now, until: now + FLASH_MS };
        clearInterval(st.flashTimer);
        st.flashTimer = setInterval(() => {
            if (!st.flash || Date.now() >= st.flash.until) {
                clearInterval(st.flashTimer);
                st.flashTimer = null;
                st.flash = null;
            }
            if (window.canvasRenderer) window.canvasRenderer.render();
        }, BLINK_MS / 2);
        sendClientLog('idm_locate', { id: layerId, key });
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // canvas-idm.js asks, per screen, whether a module of it is blinking:
    // {key, colour} while it is, the colour alternating accent and white.
    _idmFlashFor(layer) {
        const st = this._idmS;
        const f = st && st.flash;
        if (!f || !layer || f.layerId !== layer.id) return null;
        const now = Date.now();
        if (now >= f.until) return null;
        let accent = '#e22330';
        try {
            accent = getComputedStyle(document.documentElement).getPropertyValue('--ps-accent').trim() || accent;
        } catch (_) { /* the default accent */ }
        const on = Math.floor((now - f.start) / BLINK_MS) % 2 === 0;
        return { key: f.key, colour: on ? accent : '#ffffff' };
    }
}

for (const k of Object.getOwnPropertyNames(_IdmLocator.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_IdmLocator.prototype, k));
    }
}
