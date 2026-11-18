// idm-phone: the IDM Locator on a phone (templates/idm_phone.html). A tech
// walking the wall moves the live highlight, marks and clears modules, ticks
// off the swap list and changes the field from here, by touch or with a
// game controller paired to the phone.
//
// One set of rules: stepping, the next screen and canvas, module names, the
// swap list and the locked check are idm-core.js (the tab runs the same);
// the controller map is idm-pad.js (the computer reads the same table). The
// module geometry is the renderer's own (canvas.js, canvas-labels.js,
// canvas-idm.js), on a renderer that never draws.
//
// Every change goes the way the tab sends it: a mark, or a Swapped tick
// (which clears the module's mark, so the row leaves the list), is a
// PUT of the screen's idm block (PUT /api/layer/<id>, the page named as
// ?client=, so each computer keeps it as one undo step of its own), the
// field is PUT /api/project/idm-field, the highlight the `idm_highlight`
// socket event. All of it is saved with the show and reaches every device
// and the wall output. The page follows the show live: another device's
// highlight, marks and field, a screen added or removed, a show opened or
// replaced.
//
// Undo here takes back this phone's own last change (a mark, a paint, a
// tick), and only while the screen still holds what the phone left: a
// screen changed since by another device is left alone, with a note.
//
// The controls keep to the canvas the highlight is on (owner, 2026-11-17);
// the Canvas button (and View / Share on a controller) takes it to the
// next one.
//
// The main screen is the controls alone; the swap list and the
// controller's button list open as sheets over it (owner, 2026-11-17), and
// the phone's own back gesture closes them. The page is dark unless this
// phone picked light (owner, 2026-11-17), kept per device.
import {
    idmHighlightOf, idmTargetOf, idmStepFrom, idmStartModule, idmNextScreenFrom, idmNextCanvasFrom,
    idmCanvasList, idmActiveCanvas, idmCanvasIdOf, idmDescribe, idmMarkGroups, idmLockedBy, idmLockedMessage,
    idmBlockOf, idmApplyMark, idmApplySwapped, idmCanonical, idmFieldSanitize, idmColor, DEFAULT_COLOR,
} from './idm-core.js';
import {
    FIELD_CYCLE, PAD_BUTTONS, idmPadFrame, idmPadDispatch, idmPadName, idmPadFillHelp,
} from './idm-pad.js';

const ORIGIN = 'phone' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
const SIDE_KEY = 'lrdIdmListSide';
const STEP_KEY = 'lrdIdmPhoneStep';
// idm_phone.html reads this before the first paint, so the page never
// flashes the other theme.
const THEME_KEY = 'lrdIdmPhoneTheme';
const UNDO_MAX = 50;
const TOAST_MS = 3200;

const $ = (id) => document.getElementById(id);

function readStore(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
}
function writeStore(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* per device only */ }
}

// The renderer the geometry runs on: never drawn, in the IDM Locator's view.
const r = Object.create(window.CanvasRenderer ? window.CanvasRenderer.prototype : Object.prototype);
r.viewMode = 'idm';
r.zoom = 1;

// What the renderer's mixins ask of the app: the show, its groups.
const app = {
    project: null,
    getProjectFont() { return 'Arial'; },
    resolveGroup(group) {
        if (typeof group === 'string') {
            const groups = (this.project && this.project.groups) || [];
            return groups.find(g => g && g.id === group) || null;
        }
        return group || null;
    },
    getGroupMembers(group) {
        const g = this.resolveGroup(group);
        if (!g || !Array.isArray(g.layer_ids)) return [];
        const byId = new Map(((this.project && this.project.layers) || []).map(l => [l.id, l]));
        const out = [];
        g.layer_ids.forEach(id => { const l = byId.get(id); if (l && !out.includes(l)) out.push(l); });
        return out;
    },
};
window.app = app;

const S = {
    connected: false, guide: false, showOpen: true,
    canvas: null,                 // the canvas last used here
    cabinet: readStore(STEP_KEY) === 'cabinet',
    side: readStore(SIDE_KEY) === 'back' ? 'back' : 'front',
    theme: readStore(THEME_KEY) === 'light' ? 'light' : 'dark',
    sheet: null,                  // 'swap' | 'pad' while one is open
    stroke: null,                 // a paint under way (A held)
    undo: [],                     // this phone's own changes: {layerId, before, after, action}
    seq: 0,
    pads: new Map(), padNames: new Map(), frame: 0,
    toastTimer: null,
};

// ── the show ──────────────────────────────────────────────────────────────

function layers() {
    return (app.project && Array.isArray(app.project.layers)) ? app.project.layers : [];
}

function layerById(id) {
    return layers().find(l => l && l.id === id) || null;
}

function hl() {
    return idmHighlightOf(app.project && app.project.idmHighlight);
}

function target() {
    return idmTargetOf(r, app.project, hl());
}

function activeCanvas() {
    return idmActiveCanvas(r, app.project, hl(), S.canvas);
}

function adopt(project) {
    if (!project || typeof project !== 'object') return;
    delete project._replace;
    delete project._rev;
    app.project = project;
    if (S.stroke && !layerById(S.stroke.layerId)) S.stroke = null;
    else if (S.stroke) restroke();
    render();
}

async function refetch() {
    try {
        const res = await fetch('/api/project', { cache: 'no-store' });
        if (res.ok) adopt(await res.json());
    } catch (_) { /* the socket's next message brings it */ }
    checkShow();
}

// Is a show open on the computer: the launch's question answered, or a
// show past its untouched startup state.
async function checkShow() {
    try {
        const res = await fetch('/api/idm-phone/show', { cache: 'no-store' });
        if (res.ok) {
            const data = await res.json();
            S.showOpen = !!data.open;
            render();
        }
    } catch (_) { /* keep what we knew */ }
}

function putLayer(layer, idm) {
    S.seq += 1;
    const url = `/api/layer/${layer.id}?edited=1&seq=${S.seq}&client=${encodeURIComponent(ORIGIN)}`;
    return fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idm }),
    }).then(res => (res.ok ? res.json() : null)).then(saved => {
        if (saved && saved.id === layer.id) {
            const i = layers().findIndex(l => l && l.id === saved.id);
            if (i >= 0) app.project.layers[i] = saved;
            render();
        }
        return saved;
    }).catch(() => {
        toast('The change did not reach the computer. Check the connection.');
        return null;
    });
}

// ── the highlight ─────────────────────────────────────────────────────────

function setHighlight(next) {
    if (!app.project) return;
    const value = next ? { layerId: next.layerId, key: next.key } : null;
    app.project.idmHighlight = value;
    if (value) {
        const l = layerById(value.layerId);
        if (l) S.canvas = idmCanvasIdOf(r, l);
    }
    if (socket) socket.emit('idm_highlight', { layerId: value ? value.layerId : null, key: value ? value.key : null, origin: ORIGIN });
    render();
}

function blocked() {
    return !S.connected || S.guide || !app.project || !S.showOpen || !idmCanvasList(r, app.project).length;
}

const jobs = {
    move(dir, cabinet) {
        if (blocked()) return;
        const t = target();
        if (!t) {
            const start = idmStartModule(r, { canvasId: activeCanvas() });
            if (start) setHighlight(start);
            return;
        }
        const pick = idmStepFrom(r, t, dir, cabinet || S.cabinet);
        if (pick) setHighlight(pick);
        paintHere();
    },
    mark: {
        press() { startMark(); },
        release() { endMark(); },
    },
    undo() { undo(); },
    fieldColor() {
        const cur = fieldNow().color;
        const i = FIELD_CYCLE.indexOf(cur);
        setField(FIELD_CYCLE[(i + 1) % FIELD_CYCLE.length]);
    },
    nextScreen() {
        if (blocked()) return;
        const next = idmNextScreenFrom(r, hl(), activeCanvas());
        if (next) setHighlight(next);
    },
    nextCanvas() {
        if (blocked()) return;
        const next = idmNextCanvasFrom(r, app.project, activeCanvas());
        if (!next) {
            toast('This show has one canvas with screens.');
            return;
        }
        S.canvas = next.canvasId;
        setHighlight(next);
        const c = idmCanvasList(r, app.project).find(x => x.id === next.canvasId);
        toast(`Canvas: ${(c && c.name) || 'Canvas'}`);
    },
    clearHighlight() {
        if (!app.project) return;
        setHighlight(null);
    },
};

// ── marking ───────────────────────────────────────────────────────────────

function lockedNote(layer) {
    const by = idmLockedBy(app.project, layer);
    if (!by.length) return false;
    toast(idmLockedMessage(by));
    return true;
}

// A press of Mark (or A / Cross): the highlighted module marked or cleared,
// the paint begun. With no highlight, it starts one.
function startMark() {
    if (blocked() || S.stroke) return;
    const t = target();
    if (!t) {
        jobs.move('right', false);
        return;
    }
    if (lockedNote(t.layer)) return;
    const base = idmBlockOf(r, t.layer);
    S.stroke = {
        layerId: t.layer.id, base, touched: [t.key],
        mode: base.marks[t.key] ? 'clear' : 'mark',
    };
    restroke();
    render();
}

// A move with the paint on: the module reached takes the paint's change, on
// the paint's own screen.
function paintHere() {
    const st = S.stroke;
    const t = target();
    if (!st || !t || t.layer.id !== st.layerId || st.touched.includes(t.key)) return;
    st.touched.push(t.key);
    restroke();
    render();
}

// The paint over the screen as it stands (another device's change that
// landed meanwhile is the new base).
function restroke() {
    const st = S.stroke;
    const layer = st && layerById(st.layerId);
    if (!layer) return;
    const block = JSON.parse(JSON.stringify(st.base));
    st.touched.forEach(k => idmApplyMark(block, k, st.mode, 'color', DEFAULT_COLOR));
    layer.idm = block;
}

// Mark let go: the paint is one change, one undo step.
function endMark() {
    const st = S.stroke;
    S.stroke = null;
    if (!st) return;
    const layer = layerById(st.layerId);
    if (!layer) return;
    const before = st.base;
    const after = layer.idm;
    if (idmCanonical(before) === idmCanonical(after)) return;
    const action = st.mode === 'clear'
        ? (st.touched.length > 1 ? 'Clear Module Marks' : 'Clear Module Mark')
        : (st.touched.length > 1 ? 'Mark Modules' : 'Mark Module');
    commit(layer, before, after, action);
}

function commit(layer, before, after, action) {
    putLayer(layer, after).then(saved => {
        if (!saved) return;
        S.undo.push({ layerId: layer.id, before, after: saved.idm === undefined ? null : saved.idm, action });
        if (S.undo.length > UNDO_MAX) S.undo.shift();
        render();
    });
    render();
}

// A Swapped tick: the module's mark cleared, its row gone from every
// device's list and the module from the wall; Undo brings both back.
function setSwapped(layerId, key) {
    if (blocked()) { render(); return; }
    const layer = layerById(layerId);
    if (!layer || !layer.idm || !layer.idm.marks || !layer.idm.marks[key]) { render(); return; }
    if (lockedNote(layer)) { render(); return; }
    const before = idmBlockOf(r, layer);
    const after = idmBlockOf(r, layer);
    if (!idmApplySwapped(after, key)) return;
    layer.idm = after;
    commit(layer, before, after, 'Module Swapped');
}

function undo() {
    if (S.stroke) return;
    const entry = S.undo.pop();
    if (!entry) {
        toast('Nothing to undo from this phone.');
        return;
    }
    const layer = layerById(entry.layerId);
    if (!layer) {
        toast('That screen is gone, so there is nothing to undo there.');
        return;
    }
    if (idmCanonical(layer.idm === undefined ? null : layer.idm) !== idmCanonical(entry.after)) {
        S.undo = [];
        toast('That screen was changed on another device since, so it was left as it is.');
        return;
    }
    if (lockedNote(layer)) {
        S.undo.push(entry);
        return;
    }
    layer.idm = entry.before;
    putLayer(layer, entry.before);
    toast(`Undone: ${entry.action}`);
    render();
}

// ── the field ─────────────────────────────────────────────────────────────

function fieldNow() {
    return idmFieldSanitize(app.project && app.project.idmField);
}

function setField(color) {
    if (blocked()) return;
    const c = idmColor(color);
    if (!c) return;
    const field = { ...fieldNow(), color: c };
    app.project.idmField = field;
    fetch('/api/project/idm-field', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ field, origin: ORIGIN }),
    }).catch(() => toast('The change did not reach the computer. Check the connection.'));
    render();
}

// ── the page ──────────────────────────────────────────────────────────────

function toast(text) {
    const el = $('ph-toast');
    if (!el) return;
    el.textContent = text;
    el.classList.add('show');
    clearTimeout(S.toastTimer);
    S.toastTimer = setTimeout(() => el.classList.remove('show'), TOAST_MS);
}

// What stands in the way of the controls, in plain words, or ''.
function messageNow() {
    if (!S.connected) {
        return 'Not connected to the computer. Keep this phone on the same network as the computer; it connects again by itself.';
    }
    if (S.guide) return 'A guide is running on the computer. This page waits until it ends.';
    if (!app.project) return 'Waiting for the show from the computer.';
    if (!S.showOpen) return 'No show is open on the computer yet. Open or start one there.';
    if (!idmCanvasList(r, app.project).length) {
        return layers().some(l => l && (l.type || 'screen') === 'screen')
            ? 'No screen is shown on the wall to step through. Show a screen on the computer.'
            : 'This show has no screens yet. Add one on the computer.';
    }
    return '';
}

function render() {
    const msg = messageNow();
    const conn = $('ph-conn');
    if (conn) {
        conn.textContent = S.connected ? ((app.project && app.project.name) || 'Connected') : 'Not connected';
        conn.classList.toggle('on', S.connected);
    }
    renderTheme();
    $('ph-message').textContent = msg;
    $('ph-message').hidden = !msg;
    $('ph-controls').hidden = !!msg;
    $('ph-swap-open').hidden = !!msg;
    // the swap list waits behind a message like the controls do
    if (msg && S.sheet === 'swap') closeSheet();
    renderSheets();
    if (msg) return;
    renderReadout();
    renderField();
    renderList();
}

// ── the theme and the sheets ──────────────────────────────────────────────

function renderTheme() {
    const light = S.theme === 'light';
    document.documentElement.setAttribute('data-theme', light ? 'light' : 'dark');
    const btn = $('ph-theme');
    if (btn) {
        const label = light ? 'Dark mode' : 'Light mode';
        btn.setAttribute('aria-label', label);
        btn.title = label;
    }
}

function setTheme(theme) {
    S.theme = theme === 'light' ? 'light' : 'dark';
    writeStore(THEME_KEY, S.theme);
    renderTheme();
}

function renderSheets() {
    $('ph-swap-sheet').hidden = S.sheet !== 'swap';
    $('ph-pad-sheet').hidden = S.sheet !== 'pad';
    // the controls underneath are out of reach while a sheet covers them
    const app = $('ph-app');
    if (S.sheet) app.setAttribute('aria-hidden', 'true');
    else app.removeAttribute('aria-hidden');
}

// A sheet opens as a step of the phone's history, so its own back
// gesture (or the browser's Back) closes it, as Back on the sheet does.
function openSheet(name) {
    if (S.sheet === name) return;
    const wasOpen = !!S.sheet;
    S.sheet = name;
    try {
        if (wasOpen) history.replaceState({ phSheet: name }, '');
        else history.pushState({ phSheet: name }, '');
    } catch (_) { /* no history: Back on the sheet still closes it */ }
    render();
    const sheet = $(name === 'swap' ? 'ph-swap-sheet' : 'ph-pad-sheet');
    const back = sheet && sheet.querySelector('.ph-back');
    if (back) back.focus({ preventScroll: true });
}

function closeSheet() {
    if (!S.sheet) return;
    const pushed = !!(history.state && history.state.phSheet);
    S.sheet = null;
    render();
    if (pushed) {
        try { history.back(); } catch (_) { /* closed already */ }
    }
}

function renderReadout() {
    const t = target();
    // Where it is first, read from the side the swap list is set to, then
    // its screen, Cabinet ID and Module ID.
    const back = S.side === 'back';
    const d = t ? idmDescribe(r, t.layer, t.key, { back }) : null;
    const mark = t && t.layer.idm && t.layer.idm.marks ? t.layer.idm.marks[t.key] : null;
    $('ph-place').textContent = d ? d.place : 'No module highlighted';
    $('ph-ids').textContent = d ? `${back ? 'From the back · ' : ''}${d.screen} · ${d.ids}` : 'Tap an arrow to start.';
    const state = $('ph-state');
    state.textContent = mark ? 'Marked' : '';
    state.classList.toggle('marked', !!mark);
    $('ph-mark').textContent = mark ? 'Clear mark' : 'Mark';
    // The canvas the controls are on; a tap goes to the next one. With
    // one canvas it only names it.
    const canvases = idmCanvasList(r, app.project);
    const cid = activeCanvas();
    const c = canvases.find(x => x.id === cid);
    const name = (c && c.name) || 'Canvas';
    $('ph-canvas-name').textContent = name;
    const canvasBtn = $('ph-canvas-next');
    canvasBtn.disabled = canvases.length < 2;
    canvasBtn.setAttribute('aria-label', canvases.length < 2 ? `Canvas: ${name}` : `Canvas: ${name}. Tap for the next canvas.`);
    document.querySelectorAll('[data-ph-step]').forEach(b => {
        b.setAttribute('aria-pressed', (b.dataset.phStep === 'cabinet') === S.cabinet ? 'true' : 'false');
    });
    $('ph-undo').disabled = !S.undo.length;
    $('ph-clear').disabled = !hl();
}

function renderField() {
    const f = fieldNow();
    document.querySelectorAll('[data-ph-field]').forEach(b => {
        b.setAttribute('aria-pressed', b.dataset.phField === f.color ? 'true' : 'false');
    });
}

function renderList() {
    const host = $('ph-list');
    const groups = idmMarkGroups(r, app.project, { back: S.side === 'back' });
    const h = hl();
    document.querySelectorAll('[data-ph-side]').forEach(b => {
        b.setAttribute('aria-pressed', b.dataset.phSide === S.side ? 'true' : 'false');
    });
    $('ph-side-label').textContent = S.side === 'back'
        ? 'Counted from the top left as you face the back of the wall.'
        : 'Counted from the top left as you face the front of the wall.';
    const total = groups.reduce((n, g) => n + g.rows.length, 0);
    $('ph-count').textContent = total ? `(${total})` : '';
    $('ph-swap-open').textContent = total ? `Swap list (${total})` : 'Swap list';
    host.innerHTML = '';
    if (!groups.length) {
        const empty = document.createElement('div');
        empty.className = 'ph-empty';
        empty.textContent = 'No marks yet. Mark a bad module and it is listed here.';
        host.appendChild(empty);
        return;
    }
    groups.forEach(g => {
        const name = g.layer.name || 'Screen';
        const head = document.createElement('div');
        head.className = 'ph-group';
        head.textContent = name;
        host.appendChild(head);
        g.rows.forEach(x => {
            const words = `${name} · ${x.place}`;
            const row = document.createElement('div');
            row.className = 'ph-row'
                + (h && h.layerId === g.layer.id && h.key === x.key ? ' here' : '');
            row.dataset.phLayer = String(g.layer.id);
            row.dataset.phKey = x.key;
            const go = document.createElement('button');
            go.type = 'button';
            go.className = 'ph-row-go';
            const chip = document.createElement('span');
            chip.className = 'ph-chip' + (x.style === 'x' ? ' x' : '');
            if (x.style === 'x') chip.style.setProperty('--chip', x.color);
            else chip.style.background = x.color;
            const text = document.createElement('span');
            text.className = 'ph-row-text';
            // where it is first, then its Cabinet ID and Module ID
            text.textContent = x.place;
            const where = document.createElement('span');
            where.className = 'ph-row-where';
            where.textContent = x.ids;
            text.appendChild(where);
            go.appendChild(chip);
            go.appendChild(text);
            go.setAttribute('aria-label', `Go to ${words}`);
            const tick = document.createElement('label');
            tick.className = 'ph-swap';
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.dataset.phSwap = '1';
            box.setAttribute('aria-label', `Swapped: ${words}`);
            tick.appendChild(box);
            tick.appendChild(document.createTextNode('Swapped'));
            row.appendChild(go);
            row.appendChild(tick);
            host.appendChild(row);
        });
    });
}

// ── a game controller paired with the phone ──────────────────────────────

function padList() {
    try {
        return Array.from((typeof navigator.getGamepads === 'function' && navigator.getGamepads()) || [])
            .filter(p => p && p.connected !== false);
    } catch (_) { return []; }
}

// The Controller button shows while one is connected; it opens the
// button list.
function padHelp() {
    const none = S.padNames.size === 0;
    $('ph-pad-open').hidden = none;
    $('ph-pad-name').textContent = [...S.padNames.values()].join(', ');
    if (none && S.sheet === 'pad') closeSheet();
}

function padRun() {
    const want = S.padNames.size > 0 && document.visibilityState !== 'hidden';
    if (want && !S.frame) {
        const tick = () => {
            S.frame = 0;
            if (!padTick()) return;
            S.frame = requestAnimationFrame(tick);
        };
        S.frame = requestAnimationFrame(tick);
    } else if (!want && S.frame) {
        cancelAnimationFrame(S.frame);
        S.frame = 0;
    }
    if (!want) {
        if (S.stroke) endMark();
        S.pads.clear();
    }
}

function padTick(now = performance.now()) {
    if (!S.padNames.size || document.visibilityState === 'hidden') return false;
    for (const pad of padList()) {
        if (!S.padNames.has(pad.index)) {
            S.padNames.set(pad.index, idmPadName(pad.id));
            padHelp();
        }
        const { state, actions } = idmPadFrame(S.pads.get(pad.index), pad, now);
        S.pads.set(pad.index, state);
        for (const a of actions) idmPadDispatch(jobs, a);
    }
    return true;
}

window.addEventListener('gamepadconnected', (e) => {
    const pad = e && e.gamepad;
    if (!pad) return;
    S.padNames.set(pad.index, idmPadName(pad.id));
    toast(`Controller connected: ${idmPadName(pad.id)}`);
    padHelp();
    padRun();
});
window.addEventListener('gamepaddisconnected', (e) => {
    const pad = e && e.gamepad;
    const index = pad ? pad.index : -1;
    const name = S.padNames.get(index) || idmPadName(pad && pad.id);
    S.padNames.delete(index);
    const held = S.pads.get(index);
    S.pads.delete(index);
    if (held && held.buttons[PAD_BUTTONS.A]) endMark();
    toast(`Controller disconnected: ${name}`);
    padHelp();
    padRun();
});
document.addEventListener('visibilitychange', () => padRun());

// ── wiring ────────────────────────────────────────────────────────────────

let socket = null;

function wire() {
    document.querySelectorAll('[data-ph-move]').forEach(b => {
        b.addEventListener('click', () => jobs.move(b.dataset.phMove, false));
    });
    $('ph-mark').addEventListener('click', () => { startMark(); endMark(); });
    $('ph-undo').addEventListener('click', () => jobs.undo());
    $('ph-next-screen').addEventListener('click', () => jobs.nextScreen());
    $('ph-canvas-next').addEventListener('click', () => jobs.nextCanvas());
    $('ph-clear').addEventListener('click', () => jobs.clearHighlight());
    document.querySelectorAll('[data-ph-step]').forEach(b => {
        b.addEventListener('click', () => {
            S.cabinet = b.dataset.phStep === 'cabinet';
            writeStore(STEP_KEY, S.cabinet ? 'cabinet' : 'module');
            render();
        });
    });
    document.querySelectorAll('[data-ph-field]').forEach(b => {
        b.addEventListener('click', () => setField(b.dataset.phField));
    });
    $('ph-theme').addEventListener('click', () => setTheme(S.theme === 'light' ? 'dark' : 'light'));
    $('ph-swap-open').addEventListener('click', () => openSheet('swap'));
    $('ph-swap-close').addEventListener('click', () => closeSheet());
    $('ph-pad-open').addEventListener('click', () => openSheet('pad'));
    $('ph-pad-close').addEventListener('click', () => closeSheet());
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && S.sheet) closeSheet();
    });
    window.addEventListener('popstate', (e) => {
        const want = e.state && e.state.phSheet;
        if (want === S.sheet) return;
        S.sheet = want === 'swap' || want === 'pad' ? want : null;
        render();
    });
    document.querySelectorAll('[data-ph-side]').forEach(b => {
        b.addEventListener('click', () => {
            S.side = b.dataset.phSide === 'back' ? 'back' : 'front';
            writeStore(SIDE_KEY, S.side);
            render();
        });
    });
    const list = $('ph-list');
    list.addEventListener('click', (e) => {
        if (e.target.closest('.ph-swap')) return;
        const row = e.target.closest('[data-ph-key]');
        if (!row || blocked()) return;
        setHighlight({ layerId: Number(row.dataset.phLayer), key: row.dataset.phKey });
    });
    list.addEventListener('change', (e) => {
        const box = e.target.closest('[data-ph-swap]');
        const row = box && box.closest('[data-ph-key]');
        if (!row) return;
        if (box.checked) setSwapped(Number(row.dataset.phLayer), row.dataset.phKey);
    });
    idmPadFillHelp($('ph-pad-map'));

    socket = window.io ? window.io() : null;
    if (!socket) {
        render();
        return;
    }
    socket.on('connect', () => {
        S.connected = true;
        render();
        checkShow();
    });
    socket.on('disconnect', () => {
        S.connected = false;
        if (S.stroke) S.stroke = null;
        render();
    });
    socket.on('project_data', (p) => { adopt(p); checkShow(); });
    socket.on('project_updated', (p) => { if (p && p._replace) { adopt(p); checkShow(); } });
    socket.on('project_cleared', () => refetch());
    socket.on('layer_updated', (layer) => {
        if (!layer || !app.project) return;
        delete layer._echo;
        const i = layers().findIndex(l => l && l.id === layer.id);
        if (i < 0) return;
        app.project.layers[i] = layer;
        if (S.stroke && S.stroke.layerId === layer.id) {
            S.stroke.base = idmBlockOf(r, layer);
            restroke();
        }
        render();
    });
    socket.on('layer_added', (layer) => {
        if (!layer || !app.project) return;
        if (!layers().some(l => l && l.id === layer.id)) app.project.layers.push(layer);
        render();
    });
    socket.on('layer_deleted', (data) => {
        if (!app.project || !data) return;
        app.project.layers = layers().filter(l => l && l.id !== data.id);
        if (S.stroke && S.stroke.layerId === data.id) S.stroke = null;
        render();
    });
    socket.on('idm_highlight', (data) => {
        if (!data || data.origin === ORIGIN || !app.project) return;
        app.project.idmHighlight = idmHighlightOf(data);
        render();
    });
    socket.on('idm_field_updated', (data) => {
        if (!data || data.origin === ORIGIN || !app.project) return;
        app.project.idmField = idmFieldSanitize(data.field);
        render();
    });
    socket.on('guide_state', (data) => {
        S.guide = !!(data && typeof data.page === 'string' && data.page);
        render();
    });
    render();
}

// For the tests: the page's state and its jobs.
window.idmPhone = {
    S, jobs, app, renderer: r, origin: ORIGIN, render, setSwapped, padTick, openSheet, closeSheet,
    socket: () => socket,
};

// A reload while a sheet was open lands on the controls.
try {
    if (history.state && history.state.phSheet) history.replaceState(null, '');
} catch (_) { /* nothing to tidy */ }
wire();
// A pad paired before the page loaded shows once a button is pressed.
for (const pad of padList()) S.padNames.set(pad.index, idmPadName(pad.id));
padHelp();
padRun();
