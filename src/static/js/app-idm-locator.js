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
//
// The FIELD: the tab draws every screen in one solid colour (the crew puts it
// on the real wall to spot dead pixels and bad modules) with a border style
// drawn into the raster - project.idmField = {color, border, moduleIds},
// canvas-idm.js draws it. moduleIds (the Module ID switch) labels every
// module in the screen's Cabinet ID style over its cabinet's module grid
// (A1, B1 ... starting again in every cabinet), in the app and on the wall,
// placed where the screen's Cabinet ID labels are. View state, not an edit: it saves with the
// show and reaches every client on the LAN (PUT /api/project/idm-field,
// `idm_field_updated`), but it is never an undo step - every history entry
// is stamped with the field as it changes, so an undo never puts an older
// one back.
//
// The COLOURS ride in the same block, one set for the show: the Module ID
// label colour, the module and cabinet edge colours, the shade level (a
// colour or a percent of the field) and the saved mark colours beside the
// toolbar's mark swatch (labelColor, moduleEdgeColor, cabinetEdgeColor,
// shade, markPresets). Each key is there only when the crew set it: missing
// is Auto, drawn exactly as before (canvas-idm idmBorderInks). A chosen
// colour is drawn as chosen; pure black gets a note in the panel.
//
// The LIVE HIGHLIGHT: the module the crew is pointing at - by mouse (hover),
// by the arrow keys, or from a tablet at the wall (a tap, or the arrow pad in
// the panel). It lives on the project as project.idmHighlight = {layerId,
// key} (or null) like the field: view state, never an undo step (every
// history entry is stamped with it as it moves). It goes to every client
// over Socket.IO (`idm_highlight`, throttled, the last mover wins) and the
// server keeps it, so the machine driving the wall shows a highlight moved
// from a tablet, a client that connects or reloads later shows it at once,
// and a saved show opens with it. It blinks white / the field's inverse on the wall
// (canvas-idm.js renderIdmHighlight); the blink refreshes the output window by
// laying the highlight over its last frame (app-output-display.js), not by
// rendering it again. It stays until Esc or Clear highlight, and goes when
// its screen or module does. A tap of Space marks it; Space held with a
// drag pans the view like every other tab and marks nothing.
//
// The MOUSE ON THE WALL: while the mouse is over a canvas of this view, an
// arrow sits at the same point on every IDM output of that canvas, laid on
// with the highlight (never a render). Per viewer, on unless Show mouse on
// wall is off; the tablet's tap is the highlight, so it sends no arrow.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog, isTypingTarget } from './helpers.js';

const MAX_MODULES = 64;
const DEFAULT_COLOR = '#ff1a1a';
const FLASH_MS = 1800;
const BLINK_MS = 250;
const STYLE_KEY = 'lrdIdmMarkStyle';
const COLOR_KEY = 'lrdIdmMarkColor';
// Show the mouse on the wall (per viewer, on unless turned off).
const POINTER_KEY = 'lrdIdmPointer';
// A Space press held longer than this, or with a press of the mouse in it,
// is a pan (or nothing), never a mark: only a tap marks.
const SPACE_TAP_MS = 500;
// The field's border styles; white with shaded borders when unset.
const FIELD_BORDERS = ['shade', 'lines', 'ticks', 'none'];
const FIELD_DEFAULT = { color: '#ffffff', border: 'shade', moduleIds: false };
const FIELD_PUT_MS = 150;
// The Colours (app.sanitize_idm_field): the three plain colour settings,
// the saved mark colours a show starts with, and how many it may keep.
const COLOUR_KEYS = ['labelColor', 'moduleEdgeColor', 'cabinetEdgeColor'];
const PRESETS_DEFAULT = ['#ff1a1a', '#ffff00', '#00ffff', '#ff00ff', '#ff8000'];
const PRESETS_MAX = 12;
// The live highlight: half a blink (2.5 blinks a second) and the least time
// between two sends to the other clients (25 a second).
const BLINK_HALF_MS = 200;
const SEND_MS = 40;
// The tablet layout: the IDM Locator tab on a narrow window or a touch
// screen (style.css carries the same query).
const COMPACT_QUERY = '(max-width: 1100px), (pointer: coarse)';
// The cursor over a module: a crosshair with a plus (a click marks) or a
// minus (a click clears), white edged in black so it reads on any field.
function idmCursor(minus) {
    const sign = minus ? 'M15 20h9' : 'M15 20h9M19.5 15.5v9';
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26">'
        + '<g fill="none" stroke-linecap="round">'
        + `<path d="M9 1v16M1 9h16 ${sign}" stroke="#000" stroke-width="4"/>`
        + `<path d="M9 1v16M1 9h16 ${sign}" stroke="#fff" stroke-width="2"/>`
        + '</g></svg>';
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 9 9, ${minus ? 'cell' : 'crosshair'}`;
}
const IDM_CURSOR_MARK = idmCursor(false);
const IDM_CURSOR_CLEAR = idmCursor(true);
const ARROWS = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
};

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

// The shade setting: '#rrggbb', a whole percent 0..100 (half up), or null
// for Auto (app.idm_shade_level).
function idmShadeLevel(value) {
    if (typeof value === 'number') {
        if (!Number.isFinite(value) || value < 0 || value > 100) return null;
        return Math.floor(value + 0.5);
    }
    return idmColor(value);
}

// The saved mark colours: '#rrggbb' each, no repeats, at most PRESETS_MAX;
// null when not a list (app.idm_mark_presets).
function idmMarkPresets(value) {
    if (!Array.isArray(value)) return null;
    const out = [];
    for (const item of value) {
        const c = idmColor(item);
        if (c && !out.includes(c)) out.push(c);
        if (out.length >= PRESETS_MAX) break;
    }
    return out;
}

// The field block held to its shape (the client's copy of
// app.sanitize_idm_field): the defaults for anything unusable, and a
// Colours key only when it holds something usable (missing = Auto).
export function idmFieldSanitize(value) {
    const v = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};
    const out = {
        color: idmColor(v.color) || FIELD_DEFAULT.color,
        border: FIELD_BORDERS.includes(v.border) ? v.border : FIELD_DEFAULT.border,
        moduleIds: v.moduleIds === true,
    };
    COLOUR_KEYS.forEach(k => {
        const c = idmColor(v[k]);
        if (c) out[k] = c;
    });
    const shade = idmShadeLevel(v.shade);
    if (shade !== null) out.shade = shade;
    const presets = idmMarkPresets(v.markPresets);
    if (presets) out.markPresets = presets;
    return out;
}

// The stored highlight held to its shape: {layerId, key} or null.
function idmHighlightOf(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const id = value.layerId;
    if (typeof id !== 'number' || !Number.isInteger(id)) return null;
    const key = typeof value.key === 'string' ? idmKey(value.key) : null;
    return key ? { layerId: id, key } : null;
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
            let pointerOn = true;
            try {
                style = localStorage.getItem(STYLE_KEY) === 'x' ? 'x' : 'color';
                color = idmColor(localStorage.getItem(COLOR_KEY)) || DEFAULT_COLOR;
                pointerOn = localStorage.getItem(POINTER_KEY) !== '0';
            } catch (_) { /* storage blocked: the defaults */ }
            this._idmS = {
                active: false, wired: false, style, color,
                stroke: null, flash: null, flashTimer: null,
                fieldsKey: '', listKey: '', fieldUiKey: '', readoutKey: '', presetsKey: '',
                // the field's PUT, held back while a colour is dragged
                fieldTimer: null, fieldPending: null,
                // the live highlight's blink (the highlight itself is
                // project.idmHighlight - _idmHl)
                blinkOn: true, blinkStart: 0, blinkTimer: null,
                sendTimer: null, lastSend: 0, cabinetJump: false,
                // the last pointer's kind ('mouse', 'touch', 'pen') and when
                lastPointer: '', lastPointerAt: 0,
                // a Space press that may yet be a tap (_idmKeyDown): {at}
                spaceTap: null,
                // the mouse on the wall: {canvasId, x, y} in workspace
                // coordinates or null, its switch, the frame it waits for
                // and the canvases that frame redraws
                pointer: null, pointerOn, pointerFrame: 0, pointerCanvases: null, leaveBound: false,
                origin: 'idm' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
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
        // The field: the quick colours, the custom swatch (the app's colour
        // picker opens on it), the border styles.
        document.querySelectorAll('[data-idm-field]').forEach(btn => {
            btn.addEventListener('click', () => {
                this._idmSetField({ color: btn.dataset.idmField });
                this._idmBlurButton(btn);
            });
        });
        on('idm-field-custom', 'input', (e) => this._idmSetField({ color: e.target.value }, { soon: true }));
        on('idm-field-custom', 'change', (e) => this._idmSetField({ color: e.target.value }));
        document.querySelectorAll('[data-idm-border]').forEach(btn => {
            btn.addEventListener('click', () => {
                this._idmSetField({ border: btn.dataset.idmBorder });
                this._idmBlurButton(btn);
            });
        });
        on('idm-module-ids', 'click', (e) => {
            this._idmSetField({ moduleIds: !this._idmFieldNow().moduleIds });
            this._idmBlurButton(e.currentTarget);
        });
        // The Colours: each row's Default button and swatch (the app's colour
        // picker opens on it), the shade's percent.
        document.querySelectorAll('[data-idm-auto]').forEach(btn => {
            btn.addEventListener('click', () => {
                this._idmSetField({ [btn.dataset.idmAuto]: null });
                this._idmBlurButton(btn);
            });
        });
        document.querySelectorAll('input[data-idm-color]').forEach(input => {
            const key = input.dataset.idmColor;
            input.addEventListener('input', () => this._idmSetField({ [key]: input.value }, { soon: true }));
            input.addEventListener('change', () => this._idmSetField({ [key]: input.value }));
        });
        on('idm-shade-percent', 'change', () => this._idmCommitShadePercent());
        // The saved mark colours beside the mark swatch: a click picks one,
        // its x or a right-click removes it, + saves the mark colour.
        const presets = document.getElementById('idm-mark-presets');
        if (presets) {
            presets.addEventListener('click', (e) => {
                const del = e.target.closest('[data-idm-preset-del]');
                if (del) {
                    this._idmRemovePreset(del.dataset.idmPresetDel);
                    return;
                }
                const pick = e.target.closest('[data-idm-preset]');
                if (pick) {
                    this._idmSetColor(pick.dataset.idmPreset);
                    this._idmBlurButton(pick);
                }
            });
            presets.addEventListener('contextmenu', (e) => {
                const pick = e.target.closest('[data-idm-preset]');
                if (!pick) return;
                // This right-click is the preset's: the app's own menu
                // never hears it.
                e.preventDefault();
                e.stopPropagation();
                if (typeof this.hideContextMenu === 'function') this.hideContextMenu();
                this._idmRemovePreset(pick.dataset.idmPreset);
            });
        }
        on('idm-preset-add', 'click', (e) => {
            this._idmAddPreset();
            this._idmBlurButton(e.currentTarget);
        });
        // The highlight pad: arrows, the cabinet jump, Mark, Clear.
        document.querySelectorAll('[data-idm-step]').forEach(btn => {
            btn.addEventListener('click', () => {
                this._idmStep(btn.dataset.idmStep, this._idmState().cabinetJump);
                this._idmBlurButton(btn);
            });
        });
        on('idm-pad-cabinet', 'click', (e) => {
            st.cabinetJump = !st.cabinetJump;
            this._idmSyncPad();
            this._idmBlurButton(e.currentTarget);
        });
        on('idm-pad-mark', 'click', (e) => {
            this._idmMarkHighlight();
            this._idmBlurButton(e.currentTarget);
        });
        on('idm-pad-clear', 'click', (e) => {
            this._idmClearHighlight();
            this._idmBlurButton(e.currentTarget);
        });
        on('idm-pointer', 'click', (e) => {
            this._idmSetPointerOn(!this._idmState().pointerOn);
            this._idmBlurButton(e.currentTarget);
        });
        // What kind of pointer pressed last: a tap on a touch screen moves
        // the highlight, it never marks (_idmPointerDown).
        document.addEventListener('pointerdown', (e) => {
            st.lastPointer = e.pointerType || '';
            st.lastPointerAt = Date.now();
        }, true);
        if (this.socket && typeof this.socket.on === 'function') {
            this.socket.on('idm_field_updated', (data) => {
                if (!data || data.origin === st.origin) return;
                this._idmAdoptField(idmFieldSanitize(data.field));
            });
            this.socket.on('idm_highlight', (data) => {
                if (!data || data.origin === st.origin) return;
                const id = data.layerId;
                this._idmSetHighlight(id === null || id === undefined ? null : Number(id),
                    typeof data.key === 'string' ? data.key : null, { send: false });
            });
        }
        if (typeof window.matchMedia === 'function') {
            const mq = window.matchMedia(COMPACT_QUERY);
            if (mq.addEventListener) mq.addEventListener('change', () => { if (st.active) this._idmRelayout(true); });
        }
        this._idmSyncToolbar();
        this._idmSyncPad();
        // A game controller (app-idm-gamepad.js).
        if (typeof this._idmPadWire === 'function') this._idmPadWire();
    }

    // A button that took focus from a click lets it go, so Space and the
    // arrows keep driving the highlight instead of pressing it again.
    _idmBlurButton(btn) {
        if (btn && document.activeElement === btn && typeof btn.blur === 'function') btn.blur();
    }

    // The view-tab click (app-wiring _wireViewTabs).
    _idmSetActive(on) {
        const st = this._idmState();
        st.active = !!on;
        const bar = document.getElementById('idm-toolbar');
        if (bar) bar.hidden = !st.active;
        // The tablet layout (style.css) keys off this class.
        const was = document.body.classList.contains('idm-tab');
        document.body.classList.toggle('idm-tab', st.active);
        if (was !== st.active) this._idmRelayout();
        if (!st.active) {
            st.stroke = null;
            st.spaceTap = null;
            if (window.canvasRenderer) window.canvasRenderer.isIdmPainting = false;
            this._idmPointerAt(null);
            this._idmRefreshReadout();
            // a controller is read only on this tab
            if (typeof this._idmPadRun === 'function') this._idmPadRun();
            return;
        }
        st.fieldsKey = '';
        st.listKey = '';
        st.fieldUiKey = '';
        st.readoutKey = '';
        this._idmSyncToolbar();
        this._idmSyncPad();
        if (typeof this._idmPadRun === 'function') this._idmPadRun();
    }

    // The tablet layout hides the side panels it does not need, so the
    // canvas is sized again once the page has laid out - only when that
    // layout is (or was) in play, or `force` says the window crossed it.
    _idmRelayout(force = false) {
        const r = window.canvasRenderer;
        if (!r || typeof r.setupCanvas !== 'function') return;
        const compact = typeof window.matchMedia === 'function' && window.matchMedia(COMPACT_QUERY).matches;
        if (!force && !compact) return;
        const entering = compact && this._idmState().active;
        requestAnimationFrame(() => {
            try {
                r.setupCanvas();
                // On a tablet the wall fills the room the panels left.
                if (entering && typeof r.fitToView === 'function') r.fitToView();
            } catch (_) { /* no canvas yet */ }
        });
    }

    // canvas.js render() calls this after every designer redraw of the tab:
    // any edit, selection change, undo, load or LAN update ends in one. The
    // panel only touches the DOM when what it shows has changed.
    _idmOnRender() {
        this._idmRefreshPanel();
    }

    // ── the field ─────────────────────────────────────────────────────────

    _idmFieldNow() {
        return idmFieldSanitize(this.project && this.project.idmField);
    }

    // A change of colour, border, the Module ID switch or one of the
    // Colours from this client: drawn at once, sent to the server (which
    // tells every other client). A Colours key set to null goes back to
    // Auto. `soon` holds the send back while a colour is being dragged in
    // the picker.
    _idmSetField(patch, { soon = false } = {}) {
        const st = this._idmState();
        if (!this.project) return;
        const p = (patch && typeof patch === 'object') ? patch : {};
        const cur = this._idmFieldNow();
        const next = { ...cur };
        if (idmColor(p.color)) next.color = idmColor(p.color);
        if (FIELD_BORDERS.includes(p.border)) next.border = p.border;
        if (typeof p.moduleIds === 'boolean') next.moduleIds = p.moduleIds;
        COLOUR_KEYS.forEach(k => {
            if (!(k in p)) return;
            const c = idmColor(p[k]);
            if (c) next[k] = c;
            else if (p[k] === null) delete next[k];
        });
        if ('shade' in p) {
            const v = idmShadeLevel(p.shade);
            if (v !== null) next.shade = v;
            else if (p.shade === null) delete next.shade;
        }
        if (Array.isArray(p.markPresets)) next.markPresets = p.markPresets;
        const clean = idmFieldSanitize(next);
        const stored = this.project.idmField;
        const same = !!stored && JSON.stringify(idmFieldSanitize(stored)) === JSON.stringify(clean);
        if (same && !st.fieldPending) return;
        if (!same) this._idmAdoptField(clean);
        st.fieldPending = clean;
        clearTimeout(st.fieldTimer);
        st.fieldTimer = null;
        const send = () => {
            st.fieldTimer = null;
            const field = st.fieldPending;
            st.fieldPending = null;
            if (!field) return;
            sendClientLog('idm_field', field);
            fetch('/api/project/idm-field', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ field, origin: st.origin }),
            }).catch(() => {});
        };
        if (soon) st.fieldTimer = setTimeout(send, FIELD_PUT_MS);
        else send();
    }

    // The field onto this window's project - and onto every history entry,
    // so no undo or redo ever brings an older field back (it is view state,
    // not an edit) and the next snapshot does not count it as a change.
    _idmAdoptField(field) {
        if (!this.project) return;
        const clean = idmFieldSanitize(field);
        this.project.idmField = { ...clean };
        (Array.isArray(this.history) ? this.history : []).forEach(entry => {
            if (entry && entry.project && typeof entry.project === 'object') {
                entry.project.idmField = { ...clean };
            }
        });
        this._idmSyncField(true);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The panel's swatches, border buttons and Module ID switch say what
    // the project holds.
    _idmSyncField(force = false) {
        const st = this._idmState();
        const f = this._idmFieldNow();
        const key = JSON.stringify(f);
        if (!force && key === st.fieldUiKey) return;
        st.fieldUiKey = key;
        this._idmSyncColours(f);
        this._idmRenderPresets();
        let quick = false;
        document.querySelectorAll('[data-idm-field]').forEach(btn => {
            const on = btn.dataset.idmField === f.color;
            quick = quick || on;
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        const custom = document.getElementById('idm-field-custom');
        if (custom) {
            if (custom.value.toLowerCase() !== f.color) custom.value = f.color;
            const wrap = custom.closest('.idm-swatch-custom');
            if (wrap) wrap.classList.toggle('active', !quick);
        }
        document.querySelectorAll('[data-idm-border]').forEach(btn => {
            const on = btn.dataset.idmBorder === f.border;
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        const ids = document.getElementById('idm-module-ids');
        if (ids) {
            ids.classList.toggle('active', f.moduleIds);
            ids.setAttribute('aria-pressed', f.moduleIds ? 'true' : 'false');
        }
    }

    // ── the Colours ───────────────────────────────────────────────────────

    // The Colours rows say what the project holds: Auto pressed, or the
    // swatch outlined with the chosen colour in it. On Auto a swatch shows
    // the colour Auto draws in on this field (so the picker opens on it),
    // and a chosen colour that comes out pure black carries the note.
    _idmSyncColours(f) {
        const r = window.canvasRenderer;
        if (!r || typeof r.idmBorderInks !== 'function') return;
        const rgb = r._idmRgb(f.color);
        const spec = { ...f, rgb, labelColor: null, moduleEdgeColor: null, cabinetEdgeColor: null, shade: null };
        const auto = r.idmBorderInks(spec);
        const used = r.idmBorderInks({ ...spec, shade: r._idmShadeOrNull(f.shade) });
        const autoLabel = r.idmInkLevels(rgb).cabinet;
        const hex = (c) => '#' + c.map(v => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('');
        const rows = {
            labelColor: { set: !!f.labelColor, value: f.labelColor || hex(autoLabel) },
            moduleEdgeColor: { set: !!f.moduleEdgeColor, value: f.moduleEdgeColor || hex(auto.module) },
            cabinetEdgeColor: {
                set: !!f.cabinetEdgeColor,
                value: f.cabinetEdgeColor || hex(f.border === 'shade' ? auto.ring : auto.cabinet),
            },
            // the shade: Auto, a colour (the swatch outlined) or a percent
            // (the percent box outlined, the swatch showing what it makes)
            shade: {
                set: f.shade !== undefined,
                value: hex(used.alt),
                swatch: typeof f.shade === 'string',
            },
        };
        // A row shows only while what it colors is drawn: the labels with
        // Module ID on, module edges in Lines and Ticks, cabinet edges in
        // every border but None, the shade level in Shade.
        const applies = {
            labelColor: f.moduleIds,
            moduleEdgeColor: f.border === 'lines' || f.border === 'ticks',
            cabinetEdgeColor: f.border !== 'none',
            shade: f.border === 'shade',
        };
        Object.keys(applies).forEach(k => {
            const el = document.querySelector(`[data-idm-row="${k}"]`);
            if (el) el.hidden = !applies[k];
        });
        const none = document.getElementById('idm-colors-none');
        if (none) none.hidden = Object.values(applies).some(Boolean);
        Object.keys(rows).forEach(k => {
            const row = rows[k];
            const btn = document.querySelector(`[data-idm-auto="${k}"]`);
            if (btn) {
                btn.classList.toggle('active', !row.set);
                btn.setAttribute('aria-pressed', row.set ? 'false' : 'true');
            }
            const input = document.querySelector(`input[data-idm-color="${k}"]`);
            if (input) {
                if (input.value.toLowerCase() !== row.value) input.value = row.value;
                const wrap = input.closest('.idm-swatch-custom');
                if (wrap) wrap.classList.toggle('active', row.swatch !== undefined ? row.swatch : row.set);
            }
            const note = document.querySelector(`[data-idm-black="${k}"]`);
            if (note) note.hidden = !(applies[k] && row.set && row.value === '#000000');
        });
        const pct = document.getElementById('idm-shade-percent');
        if (pct) {
            if (document.activeElement !== pct) pct.value = typeof f.shade === 'number' ? String(f.shade) : '';
            pct.classList.toggle('active', typeof f.shade === 'number');
        }
    }

    // The shade percent typed in: a whole 0..100 (Enter or Tab ends the
    // edit). Empty or not a number puts the box back.
    _idmCommitShadePercent() {
        const el = document.getElementById('idm-shade-percent');
        if (!el) return;
        const text = String(el.value).trim().replace(/%$/, '').trim();
        const n = Number(text);
        if (text === '' || !Number.isFinite(n)) {
            const f = this._idmFieldNow();
            el.value = typeof f.shade === 'number' ? String(f.shade) : '';
            return;
        }
        const pct = Math.max(0, Math.min(100, Math.round(n)));
        el.value = String(pct);
        this._idmSetField({ shade: pct });
    }

    // The show's saved mark colours (the defaults until the crew changes
    // them).
    _idmPresets() {
        const f = this._idmFieldNow();
        return Array.isArray(f.markPresets) ? f.markPresets.slice() : PRESETS_DEFAULT.slice();
    }

    _idmAddPreset() {
        const st = this._idmState();
        const list = this._idmPresets();
        if (list.includes(st.color)) {
            this._toast('That color is already a preset.');
            return false;
        }
        if (list.length >= PRESETS_MAX) {
            this._toast(`Up to ${PRESETS_MAX} presets. Remove one first.`);
            return false;
        }
        sendClientLog('idm_preset_add', { color: st.color });
        this._idmSetField({ markPresets: [...list, st.color] });
        return true;
    }

    _idmRemovePreset(hex) {
        const c = idmColor(hex);
        const list = this._idmPresets();
        if (!c || !list.includes(c)) return false;
        sendClientLog('idm_preset_remove', { color: c });
        this._idmSetField({ markPresets: list.filter(x => x !== c) });
        return true;
    }

    // The preset buttons beside the mark swatch, rebuilt only when the
    // list or the mark colour changed; the one that is the mark colour is
    // outlined.
    _idmRenderPresets() {
        const st = this._idmState();
        const host = document.getElementById('idm-mark-presets');
        if (!host) return;
        const list = this._idmPresets();
        const key = `${list.join(',')}|${st.color}`;
        if (key === st.presetsKey) return;
        st.presetsKey = key;
        host.innerHTML = '';
        list.forEach(c => {
            const on = c === st.color;
            const wrap = document.createElement('span');
            wrap.className = 'idm-preset';
            const pick = document.createElement('button');
            pick.type = 'button';
            pick.className = 'idm-preset-pick' + (on ? ' active' : '');
            pick.dataset.idmPreset = c;
            pick.style.setProperty('--idm-sw', c);
            pick.setAttribute('aria-label', `Mark color ${c}`);
            pick.setAttribute('aria-pressed', on ? 'true' : 'false');
            pick.dataset.tooltip = `Mark color ${c}, Use this color for the next mark. Right-click it, or press its x, to remove it from the show's presets.`;
            const del = document.createElement('button');
            del.type = 'button';
            del.className = 'idm-preset-del';
            del.dataset.idmPresetDel = c;
            del.setAttribute('aria-label', `Remove preset ${c}`);
            del.dataset.tooltip = `Remove preset, Take ${c} off the show's mark color presets.`;
            del.textContent = '\u00d7';
            wrap.appendChild(pick);
            wrap.appendChild(del);
            host.appendChild(wrap);
        });
        const add = document.getElementById('idm-preset-add');
        if (add) add.disabled = list.length >= PRESETS_MAX;
    }

    // ── the live highlight ────────────────────────────────────────────────

    // The highlight as the project holds it: {layerId, key} or null.
    _idmHl() {
        return idmHighlightOf(this.project && this.project.idmHighlight);
    }

    // The highlight onto this window's project - and onto every history
    // entry, so it is never an undo step and the next snapshot does not
    // count a move as a change (the field's way, _idmAdoptField).
    _idmPutHighlight(next) {
        if (!this.project) return;
        const value = next ? { layerId: next.layerId, key: next.key } : null;
        this.project.idmHighlight = value;
        (Array.isArray(this.history) ? this.history : []).forEach(entry => {
            if (entry && entry.project && typeof entry.project === 'object') {
                entry.project.idmHighlight = value ? { ...value } : null;
            }
        });
    }

    // The blink runs while there is a highlight - whichever way it came
    // (this client, another one, a project or file load, a reconnect).
    _idmEnsureBlink() {
        const st = this._idmState();
        const has = !!this._idmHl();
        if (has && !st.blinkTimer) {
            st.blinkOn = true;
            st.blinkStart = Date.now();
            st.blinkTimer = setInterval(() => this._idmBlinkTick(), BLINK_HALF_MS);
        } else if (!has && st.blinkTimer) {
            clearInterval(st.blinkTimer);
            st.blinkTimer = null;
        }
    }

    // The highlighted module as the canvas draws it: {layer, panel, cell,
    // key, on} (on: the white half of the blink), or null. A highlight on a
    // screen or module that is gone answers null.
    _idmHighlightTarget() {
        const st = this._idmState();
        const hl = this._idmHl();
        const r = window.canvasRenderer;
        if (hl && !st.blinkTimer) this._idmEnsureBlink();
        if (!hl || !r || !this.project) return null;
        const layer = (this.project.layers || []).find(l => l && l.id === hl.layerId);
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        const parts = String(hl.key).split(',').map(n => parseInt(n, 10));
        if (parts.length !== 4 || parts.some(n => !Number.isFinite(n))) return null;
        const panel = (layer.panels || []).find(p => p && (p.col || 0) === parts[0] && (p.row || 0) === parts[1]);
        if (!panel) return null;
        const counts = r.idmCounts(layer);
        const cell = r.idmModuleCells(layer, panel, counts.x, counts.y, r._idmVisibleLookup(layer))
            .find(c => c.mx === parts[2] && c.my === parts[3]);
        if (!cell) return null;
        return { layer, panel, cell, key: hl.key, on: st.blinkOn !== false };
    }

    // Move the highlight (null clears it). `send`: tell the other clients
    // (false for a move that came from one of them).
    _idmSetHighlight(layerId, key, { send = true } = {}) {
        const st = this._idmState();
        const next = idmHighlightOf({ layerId, key });
        const cur = this._idmHl();
        const same = (!next && !cur)
            || (next && cur && cur.layerId === next.layerId && cur.key === next.key);
        if (same) return;
        this._idmPutHighlight(next);
        st.blinkOn = true;
        st.blinkStart = Date.now();
        this._idmEnsureBlink();
        if (send) this._idmSendHighlight();
        this._idmRefreshReadout();
        this._idmRepaint();
    }

    _idmClearHighlight() {
        this._idmSetHighlight(null, null);
    }

    // Throttled: at most one send per SEND_MS, the newest position last.
    _idmSendHighlight() {
        const st = this._idmState();
        if (!this.socket || typeof this.socket.emit !== 'function') return;
        if (st.sendTimer) return;
        const flush = () => {
            st.sendTimer = null;
            st.lastSend = Date.now();
            const hl = this._idmHl();
            this.socket.emit('idm_highlight', {
                layerId: hl ? hl.layerId : null, key: hl ? hl.key : null, origin: st.origin,
            });
        };
        const wait = SEND_MS - (Date.now() - st.lastSend);
        if (wait <= 0) flush();
        else st.sendTimer = setTimeout(flush, wait);
    }

    // Half a blink: the highlight changes colour. A highlight whose screen
    // or module has gone is dropped here (on every client alike; the server
    // clears its own copy when the screen changes), and one a project load
    // took away stops the blink and leaves the wall.
    _idmBlinkTick() {
        const st = this._idmState();
        const gone = !this._idmHl() || !this._idmHighlightTarget();
        if (gone) {
            if (this._idmHl()) this._idmPutHighlight(null);
            clearInterval(st.blinkTimer);
            st.blinkTimer = null;
            this._idmRefreshReadout();
            this._idmRepaint();
            return;
        }
        st.blinkOn = Math.floor((Date.now() - st.blinkStart) / BLINK_HALF_MS) % 2 === 0;
        this._idmRepaint();
    }

    // The highlight changed and nothing else: the designer redraws (when it
    // shows this tab) without asking the outputs to compare the whole
    // project, and each IDM output lays the highlight over its last frame.
    _idmRepaint() {
        const r = window.canvasRenderer;
        if (r && r.viewMode === 'idm' && document.visibilityState !== 'hidden') {
            this._idmQuietRender = true;
            try { r.render(); } finally { this._idmQuietRender = false; }
        }
        if (typeof this._outputDisplayBlink === 'function') this._outputDisplayBlink();
    }

    // The mouse over the view: the module under it is highlighted. Off every
    // module the highlight stays where it was.
    _idmHover(worldX, worldY) {
        const st = this._idmState();
        const r = window.canvasRenderer;
        if (!st.active || !r || st.stroke) return;
        const hit = r.idmHitAt(worldX, worldY);
        if (!hit || !hit.cell) return;
        this._idmSetHighlight(hit.layer.id, r.idmCellKey(hit.panel, hit.cell));
    }

    // A press that came from a finger (a touch screen's tap): it moves the
    // highlight and never marks.
    _idmTouchPress() {
        const st = this._idmState();
        return st.lastPointer === 'touch' && Date.now() - st.lastPointerAt < 1000;
    }

    // The arrow keys and the pad: one module in `dir` ('left', 'right', 'up',
    // 'down' or an Arrow key name), or with `cabinet` one whole cabinet. The
    // step is taken on the wall as drawn (a turned screen steps the way it
    // looks), carries on across cabinet edges and onto the next screen in
    // that row of the same canvas, and stops at the last module. With no
    // highlight it starts on the first module of the selected screen.
    _idmStep(dir, cabinet = false) {
        const r = window.canvasRenderer;
        if (!r || !this.project) return false;
        const names = { left: 'ArrowLeft', right: 'ArrowRight', up: 'ArrowUp', down: 'ArrowDown' };
        const vec = ARROWS[names[dir] || dir];
        if (!vec) return false;
        const t = this._idmHighlightTarget();
        if (!t) return this._idmStartHighlight();
        const canvasId = r._effectiveLayerCanvasId(t.layer);
        const all = r.idmModuleRects(l => r._effectiveLayerCanvasId(l) === canvasId);
        const cur = r.idmModuleWorldRect(t.layer, t.panel, t.cell);
        const cx = cur.x + cur.w / 2, cy = cur.y + cur.h / 2;
        const [dx, dy] = vec;
        const eps = 0.5;
        let pick = null;
        if (!cabinet) {
            let best = Infinity;
            for (const m of all) {
                if (m.layer === t.layer && m.key === t.key) continue;
                let gap;
                if (dx) {
                    if (!(m.y - eps <= cy && cy < m.y + m.h - eps)) continue;
                    gap = dx > 0 ? m.x - (cur.x + cur.w) : cur.x - (m.x + m.w);
                } else {
                    if (!(m.x - eps <= cx && cx < m.x + m.w - eps)) continue;
                    gap = dy > 0 ? m.y - (cur.y + cur.h) : cur.y - (m.y + m.h);
                }
                if (gap < -eps) continue;
                // the nearest; on a tie the current screen's own module
                const score = gap + (m.layer === t.layer ? 0 : 0.25);
                if (score < best) { best = score; pick = m; }
            }
        } else {
            // A whole cabinet on: the point one cabinet along, as the
            // cabinet stands on the wall (a quarter turn swaps its sides).
            // A blanked cabinet is stepped over; past the last one, stop.
            const swap = r._layerDrawFrame(t.layer).swap;
            const cw = Math.round(Number(t.layer.cabinet_width) || 0);
            const ch = Math.round(Number(t.layer.cabinet_height) || 0);
            const ext = dx ? (swap ? ch : cw) : (swap ? cw : ch);
            if (ext > 0 && all.length) {
                const minX = Math.min(...all.map(m => m.x)), maxX = Math.max(...all.map(m => m.x + m.w));
                const minY = Math.min(...all.map(m => m.y)), maxY = Math.max(...all.map(m => m.y + m.h));
                for (let n = 1; n <= 512 && !pick; n++) {
                    const px = cx + dx * ext * n, py = cy + dy * ext * n;
                    if (px < minX || px > maxX || py < minY || py > maxY) break;
                    const inside = all.filter(m => px >= m.x && px < m.x + m.w && py >= m.y && py < m.y + m.h);
                    pick = inside.find(m => m.layer === t.layer) || inside[inside.length - 1] || null;
                }
            }
        }
        if (!pick) return false;
        this._idmSetHighlight(pick.layer.id, pick.key);
        return true;
    }

    // The first module (top-left as drawn) of the selected screen, or of
    // the topmost-leftmost screen.
    _idmStartHighlight() {
        const r = window.canvasRenderer;
        if (!r) return false;
        const sel = this.currentLayer && (this.currentLayer.type || 'screen') === 'screen' ? this.currentLayer : null;
        let mods = sel ? r.idmModuleRects(l => l === sel) : [];
        if (!mods.length) mods = r.idmModuleRects();
        if (!mods.length) return false;
        const topLeft = (list) => list.reduce((a, m) =>
            ((m.y < a.y - 0.5 || (Math.abs(m.y - a.y) <= 0.5 && m.x < a.x)) ? m : a));
        const first = topLeft(mods);
        const start = topLeft(mods.filter(m => m.layer === first.layer));
        this._idmSetHighlight(start.layer.id, start.key);
        return true;
    }

    // A Space tap or the Mark button: the highlighted module marked or cleared,
    // the same rules and the same single undo step a click makes.
    _idmMarkHighlight() {
        const t = this._idmHighlightTarget();
        if (!t) {
            this._toast('Move the highlight onto a module first.');
            return false;
        }
        const layer = t.layer;
        if (this._layerLocked(layer)) {
            this._showLockedError([layer]);
            return true;
        }
        const st = this._idmState();
        const before = JSON.stringify(layer.idm || null);
        const block = this._idmEnsureBlock(layer);
        st.stroke = { layerId: layer.id, mode: block.marks[t.key] ? 'clear' : 'mark', touched: new Set(), before };
        this._idmApply(layer, t.key);
        this._idmPointerUp();
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // canvas-input.js handleKeyDown, in this view: arrows move the
    // highlight (Shift: a whole cabinet), Space marks the highlighted
    // module, Esc clears the highlight. Never while a field is typed in or
    // a dialog is open. True when the key was this view's.
    _idmKeyDown(e) {
        const st = this._idmState();
        if (!st.active || e.metaKey || e.ctrlKey || e.altKey) return false;
        if (isTypingTarget(document.activeElement)) return false;
        const modalOpen = Array.from(document.querySelectorAll('.modal'))
            .some(m => getComputedStyle(m).display !== 'none');
        if (modalOpen) return false;
        if (ARROWS[e.key]) {
            this._idmStep(e.key, e.shiftKey);
            return true;
        }
        // Space is the pan every tab has: held with a drag it moves the
        // view. Only a tap - let go within SPACE_TAP_MS with no press of
        // the mouse in it - marks the highlighted module, on the release
        // (_idmSpaceUp), so a press never marks and pans at once. The key
        // goes on to canvas-input, which arms the pan.
        if (e.code === 'Space') {
            const el = document.activeElement;
            const owned = !!(el && el.tagName === 'INPUT');
            if (!e.repeat && !st.spaceTap && !owned && !st.stroke && this._idmHl()) {
                st.spaceTap = { at: Date.now() };
            }
            return false;
        }
        if (e.key === 'Escape') {
            // Esc in the middle of a drag puts every module it touched
            // back and makes no edit.
            if (st.stroke) {
                this._idmCancelStroke();
                return true;
            }
            if (!this._idmHl()) return false;
            this._idmClearHighlight();
            return true;
        }
        return false;
    }

    // Space let go (canvas-input handleKeyUp): a tap marks or clears the
    // highlighted module, the same single undo step a click makes.
    _idmSpaceUp() {
        const st = this._idmState();
        const tap = st.spaceTap;
        st.spaceTap = null;
        if (!tap || !st.active || Date.now() - tap.at > SPACE_TAP_MS) return false;
        if (isTypingTarget(document.activeElement)) return false;
        return this._idmMarkHighlight();
    }

    // A press of the mouse while Space is down is a pan: no tap.
    _idmSpacePan() {
        if (this._idmS) this._idmS.spaceTap = null;
    }

    // Esc during a drag: the screen's modules as they were before it.
    _idmCancelStroke() {
        const st = this._idmState();
        const stroke = st.stroke;
        st.stroke = null;
        const r = window.canvasRenderer;
        if (r) r.isIdmPainting = false;
        if (!stroke || !this.project) return;
        const layer = (this.project.layers || []).find(l => l.id === stroke.layerId);
        if (layer) {
            const before = JSON.parse(stroke.before);
            if (before) layer.idm = before;
            else delete layer.idm;
        }
        sendClientLog('idm_mark_cancel', { id: stroke.layerId, modules: [...stroke.touched] });
        if (r) r.render();
    }

    // A right-click on a marked module clears that mark (one undo step);
    // anywhere else the app's own menu opens. True when it was this view's.
    _idmContextClear(worldX, worldY) {
        const st = this._idmState();
        const r = window.canvasRenderer;
        if (!st.active || st.stroke || !r || this._idmTouchPress()) return false;
        const hit = r.idmHitAt(worldX, worldY);
        if (!hit || !hit.cell) return false;
        const layer = hit.layer;
        const key = r.idmCellKey(hit.panel, hit.cell);
        if (!(layer.idm && layer.idm.marks && layer.idm.marks[key])) return false;
        if (this._layerLocked(layer)) {
            this._showLockedError([layer]);
            return true;
        }
        const before = JSON.stringify(layer.idm || null);
        this._idmEnsureBlock(layer);
        st.stroke = { layerId: layer.id, mode: 'clear', touched: new Set(), before };
        this._idmApply(layer, key);
        this._idmPointerUp();
        this._idmSetHighlight(layer.id, key);
        r.render();
        return true;
    }

    // The cursor over the view: a plus where a click marks, a minus where
    // it clears, no-entry on a locked screen or a blanked cabinet, the
    // arrow off every screen.
    _idmCursorAt(worldX, worldY) {
        const r = window.canvasRenderer;
        const hit = r && typeof r.idmHitAt === 'function' ? r.idmHitAt(worldX, worldY) : null;
        if (!hit) return 'default';
        if (!hit.cell || this._layerLocked(hit.layer)) return 'not-allowed';
        const marks = hit.layer.idm && hit.layer.idm.marks;
        return marks && marks[r.idmCellKey(hit.panel, hit.cell)] ? IDM_CURSOR_CLEAR : IDM_CURSOR_MARK;
    }

    // ── the mouse on the wall ─────────────────────────────────────────────

    // canvas-input handleMouseMove, in this view: the point under the
    // mouse in workspace coordinates; null, or a point off every canvas,
    // takes it off the wall. Every IDM output of the canvas it is on, and
    // of the one it left, lays it over its last frame on the next animation
    // frame (_outputDisplayBlink): a copy, never a render.
    _idmPointerAt(worldX, worldY) {
        const st = this._idmState();
        const r = window.canvasRenderer;
        let next = null;
        if (st.active && st.pointerOn && r && Number.isFinite(worldX) && Number.isFinite(worldY)) {
            const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
            if (canvases.length) {
                const c = typeof r._canvasAtPoint === 'function' ? r._canvasAtPoint(worldX, worldY) : null;
                if (c) next = { canvasId: c.id, x: worldX, y: worldY };
            } else if (worldX >= 0 && worldY >= 0
                    && worldX <= (Number(r.rasterWidth) || 0) && worldY <= (Number(r.rasterHeight) || 0)) {
                next = { canvasId: '', x: worldX, y: worldY };
            }
        }
        const cur = st.pointer;
        if (!next && !cur) return;
        if (next && cur && next.canvasId === cur.canvasId && next.x === cur.x && next.y === cur.y) return;
        this._idmBindLeave();
        st.pointer = next;
        if (!st.pointerCanvases) st.pointerCanvases = new Set();
        if (cur) st.pointerCanvases.add(cur.canvasId);
        if (next) st.pointerCanvases.add(next.canvasId);
        if (st.pointerFrame) return;
        const flush = () => {
            st.pointerFrame = 0;
            const ids = st.pointerCanvases;
            st.pointerCanvases = null;
            if (ids && typeof this._outputDisplayBlink === 'function') this._outputDisplayBlink(ids);
        };
        // A hidden designer gets no animation frames: a timer then.
        st.pointerFrame = (document.visibilityState !== 'hidden' && typeof requestAnimationFrame === 'function')
            ? requestAnimationFrame(flush) : setTimeout(flush, 16);
    }

    // The mouse leaving the view takes the pointer off the wall.
    _idmBindLeave() {
        const st = this._idmState();
        const r = window.canvasRenderer;
        if (st.leaveBound || !r || !r.canvas) return;
        st.leaveBound = true;
        r.canvas.addEventListener('mouseleave', () => this._idmPointerAt(null));
    }

    // The pointer an IDM output of `canvasId` draws: {x, y} in workspace
    // coordinates, or null (app-output-display.js _outputDisplayCompose).
    _idmPointerFor(canvasId) {
        const st = this._idmS;
        const p = st && st.active && st.pointerOn ? st.pointer : null;
        if (!p) return null;
        const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        if (canvases.length && p.canvasId !== canvasId) return null;
        return { x: p.x, y: p.y };
    }

    // The Show mouse on wall switch (per viewer).
    _idmSetPointerOn(on) {
        const st = this._idmState();
        st.pointerOn = !!on;
        try { localStorage.setItem(POINTER_KEY, st.pointerOn ? '1' : '0'); } catch (_) { /* per-viewer only */ }
        sendClientLog('idm_pointer', { on: st.pointerOn });
        if (!st.pointerOn) this._idmPointerAt(null);
        this._idmSyncPad();
    }

    // Screen · Cabinet ID · Module label for one module - the locator list's
    // own naming (_idmMarkGroups), the module label the Module ID labels
    // draw (canvas-idm idmModuleLabeler). Null when the module is not there.
    _idmDescribe(layer, key) {
        const r = window.canvasRenderer;
        if (!r || !layer) return null;
        const parts = String(key).split(',').map(n => parseInt(n, 10));
        const panel = (layer.panels || []).find(p => p && (p.col || 0) === parts[0] && (p.row || 0) === parts[1]);
        if (!panel) return null;
        const counts = r.idmCounts(layer);
        const cells = r.idmModuleCells(layer, panel, counts.x, counts.y, r._idmVisibleLookup(layer));
        const cell = cells.find(c => c.mx === parts[2] && c.my === parts[3]);
        if (!cell) return null;
        const xs = [...new Set(cells.map(c => c.mx))].sort((a, b) => a - b);
        const ys = [...new Set(cells.map(c => c.my))].sort((a, b) => a - b);
        const screen = layer.name || 'Screen';
        const cabinet = r.cabinetIdLabeler(layer)(panel);
        const module = r.idmModuleLabeler(layer)(cell, cells);
        return {
            screen, cabinet, module,
            row: ys.indexOf(parts[3]) + 1, col: xs.indexOf(parts[2]) + 1,
            text: `${screen} · ${cabinet} · Module ${module}`,
        };
    }

    // The readout in the pad and in the status bar.
    _idmRefreshReadout() {
        const st = this._idmState();
        const t = st.active ? this._idmHighlightTarget() : null;
        const d = t ? this._idmDescribe(t.layer, t.key) : null;
        const marked = !!(t && t.layer.idm && t.layer.idm.marks && t.layer.idm.marks[t.key]);
        const key = JSON.stringify([st.active, d && d.text, d && d.row, d && d.col, marked]);
        if (key === st.readoutKey) return;
        st.readoutKey = key;
        const out = document.getElementById('idm-hl-readout');
        const where = document.getElementById('idm-hl-where');
        const status = document.getElementById('idm-status-readout');
        if (out) {
            out.textContent = d ? d.text : 'No module highlighted';
            out.classList.toggle('idm-hl-none', !d);
        }
        if (where) {
            where.textContent = d
                ? `Row ${d.row}, col ${d.col}${marked ? ' · marked' : ''}`
                : 'Point at a module, tap it, or use the arrows.';
        }
        if (status) {
            status.textContent = d ? d.text : '';
            status.hidden = !d;
        }
        this._idmSyncPad();
    }

    _idmSyncPad() {
        const st = this._idmState();
        const cab = document.getElementById('idm-pad-cabinet');
        if (cab) {
            cab.classList.toggle('active', !!st.cabinetJump);
            cab.setAttribute('aria-pressed', st.cabinetJump ? 'true' : 'false');
        }
        const ptr = document.getElementById('idm-pointer');
        if (ptr) {
            ptr.classList.toggle('active', !!st.pointerOn);
            ptr.setAttribute('aria-pressed', st.pointerOn ? 'true' : 'false');
        }
        const has = !!this._idmHl();
        ['idm-pad-mark', 'idm-pad-clear'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.disabled = !has;
        });
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
        this._idmSyncToolbar();
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
        this._idmRenderPresets();
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
        // A finger on a touch screen (a tablet at the wall) moves the
        // highlight; the pad's Mark button marks.
        if (this._idmTouchPress()) {
            if (hit.cell) this._idmSetHighlight(hit.layer.id, r.idmCellKey(hit.panel, hit.cell));
            return true;
        }
        const layer = hit.layer;
        if (!this.currentLayer || this.currentLayer.id !== layer.id) r._selectLayerFromCanvas(layer);
        if (this._layerLocked(layer)) {
            this._showLockedError([layer]);
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
            last: { x: worldX, y: worldY },
        };
        this._idmApply(layer, key);
        r.render();
        return true;
    }

    // The drag: every module the pointer crosses on the stroke's screen
    // takes the stroke's mode - the first module decided paint or clear.
    // The line from the last point is walked in steps of half a module, so
    // a quick drag leaves no module out between two mouse moves.
    _idmPointerMove(worldX, worldY) {
        const st = this._idmState();
        const stroke = st.stroke;
        const r = window.canvasRenderer;
        if (!stroke || !r) return;
        const last = stroke.last || { x: worldX, y: worldY };
        stroke.last = { x: worldX, y: worldY };
        const layer = ((this.project && this.project.layers) || []).find(l => l.id === stroke.layerId);
        let stepLen = 1;
        if (layer) {
            const counts = r.idmCounts(layer);
            const mw = (Number(layer.cabinet_width) || 1) / counts.x;
            const mh = (Number(layer.cabinet_height) || 1) / counts.y;
            stepLen = Math.max(1, Math.min(mw, mh) / 2);
        }
        const n = Math.min(4000, Math.max(1, Math.ceil(Math.hypot(worldX - last.x, worldY - last.y) / stepLen)));
        let changed = false;
        for (let i = 1; i <= n; i++) {
            const hit = r.idmHitAt(last.x + (worldX - last.x) * i / n, last.y + (worldY - last.y) * i / n);
            if (!hit || !hit.cell || hit.layer.id !== stroke.layerId) continue;
            const key = r.idmCellKey(hit.panel, hit.cell);
            if (stroke.touched.has(key)) continue;
            this._idmApply(hit.layer, key);
            changed = true;
        }
        if (changed) r.render();
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
    // count on a screen with marks clears them, after the app's own dialog
    // says how many.
    async _idmCommitModules() {
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
        const held = [];
        const changes = [];
        screens.forEach(layer => {
            const cur = r.idmCounts(layer);
            const nx = ax.keep ? cur.x : ax.value;
            const ny = ay.keep ? cur.y : ay.value;
            if (nx === cur.x && ny === cur.y) return;
            if (this._layerLocked(layer)) held.push(layer);
            else changes.push({ layer, nx, ny });
        });
        this._showLockedError(held);
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
            const yes = await this.appConfirm(msg, {
                id: 'idm-modules-confirm', title: 'Change the modules', okLabel: 'Change', danger: true,
            });
            if (!yes) {
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
        const open = this._writableLayers(layers.filter(l => markCount(l) > 0));
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

    async _idmClearAll() {
        const screens = ((this.project && this.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen' && markCount(l) > 0);
        if (!screens.length) {
            this._toast('There are no marks to clear.');
            return;
        }
        const total = screens.reduce((n, l) => n + markCount(l), 0);
        const msg = `Clear all ${plural(total, 'mark')} on ${plural(screens.length, 'screen')}?`;
        const yes = await this.appConfirm(msg, {
            id: 'idm-clear-all-confirm', title: 'Clear all marks', okLabel: 'Clear', danger: true,
        });
        if (!yes) return;
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
        this._idmSyncField();
        this._idmRefreshReadout();
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

    // Every mark, screen by screen: Screen · Cabinet ID · Module label, and
    // the module's row and column inside its cabinet. A module's label is
    // the screen's Cabinet ID style over the cabinet's module grid, as seen
    // from the front (canvas-idm idmModuleLabeler - what the Module ID
    // labels draw); Cabinet IDs are the Cabinet ID view's own (canvas-labels
    // cabinetIdLabeler). Rows run in reading order, cabinet by cabinet.
    _idmMarkGroups() {
        const r = window.canvasRenderer;
        const groups = [];
        if (!r || !this.project) return groups;
        for (const layer of (this.project.layers || [])) {
            if (!layer || (layer.type || 'screen') !== 'screen' || markCount(layer) === 0) continue;
            const labelOf = r.cabinetIdLabeler(layer);
            const moduleOf = r.idmModuleLabeler(layer);
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
                const cell = cells.find(c => c.mx === parts[2] && c.my === parts[3]);
                if (!cell) return;
                const index = cells.indexOf(cell);
                const xs = [...new Set(cells.map(c => c.mx))].sort((a, b) => a - b);
                const ys = [...new Set(cells.map(c => c.my))].sort((a, b) => a - b);
                const mark = layer.idm.marks[key];
                rows.push({
                    key, panel, index,
                    cabinet: labelOf(panel),
                    module: moduleOf(cell, cells),
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
