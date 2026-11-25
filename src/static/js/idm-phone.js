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
// (the module's mark leaves the wall and its row moves to the Swapped list
// under the open one, newest first; an untick puts both back), is a PUT of
// the screen's idm block (PUT /api/layer/<id>, the page named as
// ?client=, so each computer keeps it as one undo step of its own), the
// field is PUT /api/project/idm-field, the highlight the `idm_highlight`
// socket event. All of it is saved with the show and reaches every device
// and the wall output. The page follows the show live: another device's
// highlight, marks and field, a screen added or removed, a show opened or
// replaced.
//
// Holding an arrow repeats it, faster the longer it is held (owner,
// 2026-11-24; idm-pad.js idmHoldStart, the computer's arrow keys and a
// held D-pad alike): every repeat is the single step a tap makes, and it
// stops the moment the finger lifts, the touch is cancelled or the page
// is put away. The highlight goes to the computer at most every SEND_MS,
// the newest last.
//
// Undo here takes back this phone's own last change (a mark, a paint, a
// tick), and only while the screen still holds what the phone left: a
// screen changed since by another device is left alone, with a note.
// Redo (owner, 2026-11-24) puts back what this phone's Undo took back, the
// same way: a PUT of the screen's block, one step on the computer. It is
// there only while the screen still holds what the Undo left, so it goes
// grey the moment another device changes that screen (an undo or a redo
// on the computer too) and comes back if that change is taken back. A new
// change here ends the redo steps, as it does on the computer.
//
// Swap mode (owner, 2026-11-24) is switched at the top of the swap list,
// with its colour on the chip beside it: the wall goes black but for the
// modules still to swap (PUT /api/project/idm-swap, `idm_swap_updated`,
// one undo step on the computer and on this phone's Undo). It stays on
// until it is switched off, wherever the phone goes: a tag on the main
// screen says so (a tap opens the swap list), and the arrows, Mark, Next
// screen, Change canvas and a tap on a row move and mark nothing.
//
// The controls keep to the canvas the highlight is on (owner, 2026-11-17);
// Change canvas in the menu (and View / Share on a controller) takes it to
// the next one.
//
// The main screen is the controls alone: the step switch, the arrows, Mark,
// Undo and Redo. The swap list opens as a sheet over it (owner,
// 2026-11-17), and so does the menu (owner, 2026-11-24), which holds what
// jumps the highlight, takes it off or repaints the wall, so a thumb on
// the arrows never hits it: Next screen, Change canvas, Clear highlight,
// the field colors and, while one is paired, the controller's button list. The phone's own back gesture
// closes a sheet. The page is dark unless this
// phone picked light (owner, 2026-11-17), kept per device.
import {
    idmHighlightOf, idmTargetOf, idmStepFrom, idmStartModule, idmNextScreenFrom, idmNextCanvasFrom,
    idmCanvasList, idmActiveCanvas, idmCanvasIdOf, idmDescribe, idmMarkGroups, idmLockedBy, idmLockedMessage,
    idmBlockOf, idmApplyMark, idmApplySwapped, idmApplyUnswapped, idmSwappedGroups, idmCanonical,
    idmFieldSanitize, idmColor, DEFAULT_COLOR, idmRowsFrom, idmRowsFromPicks, ROWS_FROM, idmSwapOf,
} from './idm-core.js';
import {
    FIELD_CYCLE, PAD_BUTTONS, idmPadFrame, idmPadDispatch, idmPadName, idmPadFillHelp, idmHoldStart,
} from './idm-pad.js';

// The page id: the one its log lines carry (idm_phone.html lrdPhonePage).
const ORIGIN = window.lrdPhonePage || ('phone' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8));
const SIDE_KEY = 'lrdIdmListSide';
const STEP_KEY = 'lrdIdmPhoneStep';
// idm_phone.html reads this before the first paint, so the page never
// flashes the other theme.
const THEME_KEY = 'lrdIdmPhoneTheme';
const UNDO_MAX = 50;
const TOAST_MS = 3200;
// The live highlight: the least time between two sends to the computer
// (25 a second, the tab's own rate), so a held arrow never floods it.
const SEND_MS = 40;

const $ = (id) => document.getElementById(id);

// A line of the app log (idm_phone.html window.lrdPhoneLog): what the
// tech did here and what the page could not do, area 'phone'.
function plog(action, details, opts) {
    try {
        if (typeof window.lrdPhoneLog === 'function') window.lrdPhoneLog(action, details || {}, opts || null);
    } catch (_) { /* the log never stops the page */ }
}

// The phone's screen as the page sees it: its size, the window's, the
// pixel ratio and which way it is held.
function screenNow() {
    const w = window.innerWidth || 0, h = window.innerHeight || 0;
    let orientation = w > h ? 'landscape' : 'portrait';
    try { if (screen.orientation && screen.orientation.type) orientation = screen.orientation.type; } catch (_) { /* older phone */ }
    return { screen: [screen.width || 0, screen.height || 0], window: [w, h],
        dpr: window.devicePixelRatio || 1, orientation };
}

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
    sheet: null,                  // 'menu' | 'swap' | 'pad' while one is open
    stroke: null,                 // a paint under way (A held)
    undo: [],                     // this phone's own changes: {layerId, before, after, action}, or
                                  // {kind: 'swap', before, after, action} for Swap mode
    redo: [],                     // the changes its Undo took back, newest last
    seq: 0,
    pads: new Map(), padNames: new Map(), frame: 0,
    toastTimer: null,
    hold: null,                   // a held arrow: {stop, live}
    swapColors: false,            // Swap mode's colors open under its switch
    sendTimer: null, lastSend: 0,
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
    }).catch((err) => {
        toast('The change did not reach the computer. Check the connection.');
        plog('idm_phone_save_failed', { layerId: layer.id, error: String((err && err.message) || err) },
            { level: 'warn', msg: `Phone change to screen #${layer.id} did not reach the computer` });
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
    sendHighlight();
    render();
}

// Throttled: at most one send per SEND_MS, the newest position last.
function sendHighlight() {
    if (!socket || S.sendTimer) return;
    const flush = () => {
        S.sendTimer = null;
        S.lastSend = Date.now();
        if (!socket) return;
        const h = app.project ? idmHighlightOf(app.project.idmHighlight) : null;
        socket.emit('idm_highlight', { layerId: h ? h.layerId : null, key: h ? h.key : null, origin: ORIGIN });
    };
    const wait = SEND_MS - (Date.now() - S.lastSend);
    if (wait <= 0) flush();
    else S.sendTimer = setTimeout(flush, wait);
}

// A finger on an arrow: one step at once, then the repeat while it stays.
function holdArrow(dir) {
    holdStop();
    S.hold = idmHoldStart(() => jobs.move(dir, false), { still: () => !blocked() && !S.sheet });
}

function holdStop() {
    const h = S.hold;
    S.hold = null;
    if (h) h.stop();
}

function blocked() {
    return !S.connected || S.guide || !app.project || !S.showOpen || !idmCanvasList(r, app.project).length;
}

const jobs = {
    move(dir, cabinet) {
        if (blocked() || swapRefuses()) return;
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
    redo() { redo(); },
    fieldColor() {
        const cur = fieldNow().color;
        const i = FIELD_CYCLE.indexOf(cur);
        setField(FIELD_CYCLE[(i + 1) % FIELD_CYCLE.length]);
    },
    nextScreen() {
        if (blocked() || swapRefuses()) return;
        const next = idmNextScreenFrom(r, hl(), activeCanvas());
        if (next) setHighlight(next);
    },
    nextCanvas() {
        if (blocked() || swapRefuses()) return;
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
    if (blocked() || S.stroke || swapRefuses()) return;
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
    const modules = (b) => Object.keys((b && b.marks) || {});
    const was = new Set(modules(before)), now = new Set(modules(after));
    const changed = [...new Set([...was, ...now])].filter(k => was.has(k) !== now.has(k));
    putLayer(layer, after).then(saved => {
        plog('idm_phone_mark', {
            action, layerId: layer.id, name: layer.name || '', modules: changed.length, keys: changed.slice(0, 8),
            marked: now.size, saved: !!saved,
        }, { level: saved ? 'info' : 'warn',
            msg: `Phone: ${action} on ${layer.name || 'Screen'} (#${layer.id}), ${changed.length} module${changed.length === 1 ? '' : 's'}`
                + (saved ? `, ${now.size} marked` : ', not saved') });
        if (!saved) return;
        S.undo.push({ layerId: layer.id, before, after: saved.idm === undefined ? null : saved.idm, action });
        if (S.undo.length > UNDO_MAX) S.undo.shift();
        // a new change ends the redo steps, as it does on the computer
        S.redo = [];
        render();
    });
    render();
}

// A Swapped tick (`on`): the module's mark leaves the wall and its row
// moves to the Swapped list on every device; an untick there puts both
// back. Undo takes either back.
function setSwapped(layerId, key, on = true) {
    if (blocked()) { render(); return; }
    const layer = layerById(layerId);
    const map = layer && layer.idm && (on ? layer.idm.marks : layer.idm.swapped);
    if (!layer || !map || !map[key]) { render(); return; }
    if (lockedNote(layer)) { render(); return; }
    const before = idmBlockOf(r, layer);
    const after = idmBlockOf(r, layer);
    if (!(on ? idmApplySwapped(after, key) : idmApplyUnswapped(after, key))) return;
    layer.idm = after;
    commit(layer, before, after, on ? 'Module Swapped' : 'Module Not Swapped');
}

function undo() {
    if (S.stroke) return;
    const entry = S.undo.pop();
    if (!entry) {
        toast('Nothing to undo from this phone.');
        return;
    }
    if (entry.kind === 'swap') {
        undoSwap(entry);
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
        plog('idm_phone_undo_refused', { layerId: layer.id, action: entry.action, why: 'changed on another device' },
            { level: 'warn', msg: `Phone undo of ${entry.action} refused: the screen changed on another device` });
        return;
    }
    if (lockedNote(layer)) {
        S.undo.push(entry);
        return;
    }
    layer.idm = entry.before;
    S.redo.push(entry);
    putLayer(layer, entry.before).then(saved => {
        // what the screen holds now, as the computer keeps it, is what
        // Redo looks for
        if (saved) entry.before = saved.idm === undefined ? null : saved.idm;
        render();
    });
    plog('idm_phone_undo', { layerId: layer.id, action: entry.action },
        { msg: `Phone undid ${entry.action} on ${layer.name || 'Screen'} (#${layer.id})` });
    toast(`Undone: ${entry.action}`);
    render();
}

// The redo step at hand, while its screen still holds what this phone's
// Undo left there; otherwise null.
function redoNext() {
    const entry = S.redo[S.redo.length - 1];
    if (entry && entry.kind === 'swap') return idmCanonical(swapNow()) === idmCanonical(entry.before) ? entry : null;
    const layer = entry && layerById(entry.layerId);
    if (!layer) return null;
    return idmCanonical(layer.idm === undefined ? null : layer.idm) === idmCanonical(entry.before) ? entry : null;
}

function redo() {
    if (S.stroke) return;
    const entry = redoNext();
    if (!entry) {
        toast(S.redo.length ? 'That screen was changed on another device since, so it was left as it is.'
            : 'Nothing to redo from this phone.');
        render();
        return;
    }
    if (entry.kind === 'swap') {
        S.redo.pop();
        S.undo.push(entry);
        putSwap(entry.after).then(saved => {
            if (saved) entry.after = saved;
            render();
        });
        plog('idm_phone_redo', { action: entry.action }, { msg: `Phone redid ${entry.action}` });
        toast(`Redone: ${entry.action}`);
        render();
        return;
    }
    const layer = layerById(entry.layerId);
    if (lockedNote(layer)) return;
    S.redo.pop();
    layer.idm = entry.after;
    S.undo.push(entry);
    putLayer(layer, entry.after).then(saved => {
        if (saved) entry.after = saved.idm === undefined ? null : saved.idm;
        render();
    });
    plog('idm_phone_redo', { layerId: layer.id, action: entry.action },
        { msg: `Phone redid ${entry.action} on ${layer.name || 'Screen'} (#${layer.id})` });
    toast(`Redone: ${entry.action}`);
    render();
}

// ── Swap mode ─────────────────────────────────────────────────────────────

function swapNow() {
    return idmSwapOf(app.project && app.project.idmSwap);
}

// A move or a mark tried while Swap mode is on: refused, with a note.
function swapRefuses() {
    if (!swapNow().on) return false;
    toast('Swap mode is on. Turn it off on the swap list to move or mark.');
    return true;
}

// Swap mode as `swap`, on the computer and every device. The answer is
// the server's copy, or null when it did not get there.
function putSwap(swap) {
    app.project.idmSwap = swap;
    render();
    return fetch('/api/project/idm-swap', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ swap, origin: ORIGIN }),
    }).then(res => (res.ok ? res.json() : null)).then(data => {
        const saved = data && data.idmSwap ? idmSwapOf(data.idmSwap) : null;
        if (saved && app.project) app.project.idmSwap = saved;
        return saved;
    }).catch((err) => {
        toast('The change did not reach the computer. Check the connection.');
        plog('idm_phone_save_failed', { what: 'swap mode', error: String((err && err.message) || err) },
            { level: 'warn', msg: 'Phone Swap mode change did not reach the computer' });
        return null;
    });
}

// The switch or a color from the swap list: one change, one undo step here
// and on the computer.
function setSwap(patch) {
    if (blocked()) { render(); return; }
    const before = swapNow();
    const after = idmSwapOf({
        on: typeof patch.on === 'boolean' ? patch.on : before.on,
        color: idmColor(patch.color) || before.color,
    });
    if (idmCanonical(before) === idmCanonical(after)) { render(); return; }
    const action = after.color !== before.color ? 'Swap Mode Color' : (after.on ? 'Swap Mode On' : 'Swap Mode Off');
    plog('idm_phone_swap', { on: after.on, color: after.color },
        { msg: `Phone turned Swap mode ${after.on ? 'on' : 'off'}, modules to swap lit in ${after.color}` });
    putSwap(after).then(saved => {
        if (!saved) return;
        S.undo.push({ kind: 'swap', before, after: saved, action });
        if (S.undo.length > UNDO_MAX) S.undo.shift();
        S.redo = [];
        render();
    });
}

// This phone's Undo of its own Swap mode change, while Swap mode still is
// what it left.
function undoSwap(entry) {
    if (idmCanonical(swapNow()) !== idmCanonical(entry.after)) {
        S.undo = [];
        toast('Swap mode was changed on another device since, so it was left as it is.');
        plog('idm_phone_undo_refused', { action: entry.action, why: 'changed on another device' },
            { level: 'warn', msg: `Phone undo of ${entry.action} refused: Swap mode changed on another device` });
        render();
        return;
    }
    S.redo.push(entry);
    putSwap(entry.before).then(saved => {
        if (saved) entry.before = saved;
        render();
    });
    plog('idm_phone_undo', { action: entry.action }, { msg: `Phone undid ${entry.action}` });
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
    if (field.color !== fieldNow().color) {
        plog('idm_phone_field', { color: c }, { msg: `Phone set the IDM field to ${c}` });
    }
    app.project.idmField = field;
    fetch('/api/project/idm-field', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ field, origin: ORIGIN }),
    }).catch(() => toast('The change did not reach the computer. Check the connection.'));
    render();
}

// A screen's Rows from picked on the swap list (owner, 2026-11-24): kept
// with the show for that screen, on every device, never an undo step (it
// rides in the field, as the tab sends it).
function setRowsFrom(layerId, value) {
    if (blocked() || !Number.isInteger(layerId) || !ROWS_FROM.includes(value)) return;
    const cur = fieldNow();
    const field = { ...cur, rowsFrom: { ...(idmRowsFromPicks(cur.rowsFrom) || {}), [String(layerId)]: value } };
    const layer = layerById(layerId);
    plog('idm_phone_rows_from', { layerId, rowsFrom: value },
        { msg: `Phone counts the rows of ${(layer && layer.name) || 'Screen'} (#${layerId}) from the ${value}` });
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
    // what stands in the way of the controls, when it changes
    if (msg !== S.saidMessage) {
        S.saidMessage = msg;
        plog('idm_phone_message', { message: msg }, {
            level: S.everConnected ? 'info' : 'debug',
            msg: msg ? `Phone page shows: ${msg}` : 'Phone page controls are up' });
    }
    const conn = $('ph-conn');
    if (conn) {
        conn.textContent = S.connected ? ((app.project && app.project.name) || 'Connected') : 'Not connected';
        conn.classList.toggle('on', S.connected);
    }
    renderTheme();
    $('ph-message').textContent = msg;
    $('ph-message').hidden = !msg;
    $('ph-controls').hidden = !!msg;
    if (msg) holdStop();
    $('ph-swap-open').hidden = !!msg;
    $('ph-menu-open').hidden = !!msg;
    if (msg) $('ph-swap-tag').hidden = true;
    // the swap list and the menu wait behind a message like the controls do
    if (msg && (S.sheet === 'swap' || S.sheet === 'menu')) closeSheet();
    renderSheets();
    if (msg) return;
    renderReadout();
    renderField();
    renderSwap();
    renderList();
}

// Swap mode: the switch and its chip on the swap list, the tag on the main
// screen, and the arrows and Mark waiting while it is on.
function renderSwap() {
    const sw = swapNow();
    document.querySelectorAll('[data-ph-swap]').forEach(b => {
        b.setAttribute('aria-pressed', (b.dataset.phSwap === 'on') === sw.on ? 'true' : 'false');
    });
    const chip = $('ph-swap-color');
    const named = document.querySelector(`[data-ph-swap-color="${sw.color}"]`);
    chip.querySelector('.ph-sw-chip').style.setProperty('--sw', sw.color);
    chip.setAttribute('aria-label', `Swap mode color: ${named ? named.getAttribute('aria-label') : sw.color}`);
    chip.setAttribute('aria-expanded', S.swapColors ? 'true' : 'false');
    $('ph-swap-colors').hidden = !S.swapColors;
    document.querySelectorAll('[data-ph-swap-color]').forEach(b => {
        b.setAttribute('aria-pressed', b.dataset.phSwapColor === sw.color ? 'true' : 'false');
    });
    $('ph-swap-tag').hidden = !sw.on;
    document.querySelectorAll('[data-ph-move], #ph-mark, [data-ph-step]').forEach(b => { b.disabled = sw.on; });
    if (sw.on) holdStop();
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

const SHEETS = { menu: 'ph-menu-sheet', swap: 'ph-swap-sheet', pad: 'ph-pad-sheet' };

function renderSheets() {
    Object.keys(SHEETS).forEach(name => { $(SHEETS[name]).hidden = S.sheet !== name; });
    // the controls underneath are out of reach while a sheet covers them
    const app = $('ph-app');
    if (S.sheet) app.setAttribute('aria-hidden', 'true');
    else app.removeAttribute('aria-hidden');
}

// A sheet opens as a step of the phone's history, so its own back
// gesture (or the browser's Back) closes it, as Back on the sheet does.
// The controller's list opens from the menu as a step past it: Back
// returns to the menu.
function openSheet(name) {
    if (S.sheet === name || !SHEETS[name]) return;
    const replace = !!S.sheet && !(S.sheet === 'menu' && name === 'pad');
    S.sheet = name;
    try {
        if (replace) history.replaceState({ phSheet: name }, '');
        else history.pushState({ phSheet: name }, '');
    } catch (_) { /* no history: Back on the sheet still closes it */ }
    render();
    const sheet = $(SHEETS[name]);
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

// The place reads whole on its one line: on a narrow phone, or a wider
// system font, the type steps down until it fits rather than being cut
// short ("Col 1, Row 1 · Bottom right mod…").
const PLACE_PX = 18, PLACE_MIN_PX = 11;
function fitPlace() {
    const el = $('ph-place');
    if (!el) return;
    el.style.fontSize = '';
    for (let px = PLACE_PX; px > PLACE_MIN_PX && el.scrollWidth > el.clientWidth; px--) {
        el.style.fontSize = `${px - 1}px`;
    }
}
window.addEventListener('resize', fitPlace);

// The phone turned: its new screen, once it settles.
let turnTimer = null;
window.addEventListener('resize', () => {
    clearTimeout(turnTimer);
    turnTimer = setTimeout(() => {
        const sn = screenNow();
        const way = sn.window[0] > sn.window[1] ? 'landscape' : 'portrait';
        if (way === S.held) return;
        const first = !S.held;
        S.held = way;
        if (first) return;
        plog('idm_phone_screen', sn, { msg: `Phone turned to ${way}, ${sn.window[0]}x${sn.window[1]}` });
    }, 600);
});

function renderReadout() {
    const t = target();
    // Where it is first, read from the side the swap list is set to, then
    // its screen, Cabinet ID and Module ID.
    const back = S.side === 'back';
    const bottom = !!t && idmRowsFrom(app.project, t.layer) === 'bottom';
    const d = t ? idmDescribe(r, t.layer, t.key, { back, bottom }) : null;
    const mark = t && t.layer.idm && t.layer.idm.marks ? t.layer.idm.marks[t.key] : null;
    $('ph-place').textContent = d ? d.place : 'No module highlighted';
    fitPlace();
    $('ph-ids').textContent = d
        ? `${back ? 'From the back · ' : ''}${bottom ? 'Rows from the bottom · ' : ''}${d.screen} · ${d.ids}`
        : 'Tap an arrow to start.';
    const state = $('ph-state');
    state.textContent = mark ? 'Marked' : '';
    state.classList.toggle('marked', !!mark);
    $('ph-mark').textContent = mark ? 'Clear mark' : 'Mark';
    // The menu: where the highlight is, and the canvas the controls are
    // on; Change canvas goes to the next one. With one canvas it only
    // names it.
    $('ph-menu-where').textContent = d ? `Highlight on ${d.screen} · ${d.place}` : 'No module highlighted';
    const canvases = idmCanvasList(r, app.project);
    const cid = activeCanvas();
    const c = canvases.find(x => x.id === cid);
    const name = (c && c.name) || 'Canvas';
    $('ph-canvas-name').textContent = name;
    $('ph-canvas-one').hidden = canvases.length >= 2;
    const canvasBtn = $('ph-canvas-next');
    canvasBtn.disabled = canvases.length < 2;
    canvasBtn.setAttribute('aria-label', canvases.length < 2
        ? `Canvas: ${name}, the only canvas with screens` : `Change canvas. Now on ${name}.`);
    document.querySelectorAll('[data-ph-step]').forEach(b => {
        b.setAttribute('aria-pressed', (b.dataset.phStep === 'cabinet') === S.cabinet ? 'true' : 'false');
    });
    $('ph-undo').disabled = !S.undo.length;
    $('ph-redo').disabled = !redoNext();
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
    const done = idmSwappedGroups(r, app.project, { back: S.side === 'back' });
    const h = hl();
    document.querySelectorAll('[data-ph-side]').forEach(b => {
        b.setAttribute('aria-pressed', b.dataset.phSide === S.side ? 'true' : 'false');
    });
    // how the rows read: one way for every screen listed, or each its own
    const ways = new Set(groups.concat(done).map(g => g.rowsFrom));
    const face = S.side === 'back' ? 'back' : 'front';
    $('ph-side-label').textContent = ways.size > 1
        ? `Columns counted from the left as you face the ${face} of the wall; rows from the top or bottom, as set beside each screen.`
        : `Counted from the ${ways.has('bottom') ? 'bottom' : 'top'} left as you face the ${face} of the wall.`;
    // the count is what is left to swap; the Swapped list counts its own
    const total = groups.reduce((n, g) => n + g.rows.length, 0);
    const swapped = done.reduce((n, g) => n + g.rows.length, 0);
    $('ph-count').textContent = total ? `(${total})` : '';
    $('ph-swap-open').textContent = total ? `Swap list (${total})` : 'Swap list';
    host.innerHTML = '';
    if (!groups.length) {
        const empty = document.createElement('div');
        empty.className = 'ph-empty';
        empty.textContent = swapped ? 'Nothing left to swap.' : 'No marks yet. Mark a bad module and it is listed here.';
        host.appendChild(empty);
    }
    groups.forEach(g => listGroup(host, g, h, false));
    $('ph-swapped').hidden = !swapped;
    $('ph-swapped-count').textContent = swapped ? `(${swapped})` : '';
    const list = $('ph-swapped-list');
    list.innerHTML = '';
    done.forEach(g => listGroup(list, g, h, true));
}

// One screen's rows in a list: its name, then a row per module with its
// Swapped tick (ticked on the Swapped list).
function listGroup(host, g, h, swapped) {
    const name = g.layer.name || 'Screen';
    const head = document.createElement('div');
    head.className = 'ph-group';
    const label = document.createElement('span');
    label.className = 'ph-group-name';
    label.textContent = name;
    head.appendChild(label);
    // the screen's Rows from switch: Top, or Bottom for a wall
    // stacked on the ground
    const rows = document.createElement('div');
    rows.className = 'ph-rows';
    const word = document.createElement('span');
    word.className = 'ph-rows-label';
    word.textContent = 'Rows from';
    const seg = document.createElement('div');
    seg.className = 'ph-seg';
    seg.setAttribute('role', 'group');
    seg.setAttribute('aria-label', `${name}: rows counted from the`);
    ROWS_FROM.forEach(v => {
        const b = document.createElement('button');
        b.type = 'button';
        b.dataset.phRows = v;
        b.dataset.phLayer = String(g.layer.id);
        b.setAttribute('aria-pressed', g.rowsFrom === v ? 'true' : 'false');
        b.textContent = v === 'bottom' ? 'Bottom' : 'Top';
        seg.appendChild(b);
    });
    rows.appendChild(word);
    rows.appendChild(seg);
    head.appendChild(rows);
    host.appendChild(head);
    g.rows.forEach(x => {
        const words = `${name} · ${x.place}`;
        const row = document.createElement('div');
        row.className = 'ph-row' + (swapped ? ' done' : '')
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
        box.checked = swapped;
        box.dataset.phSwap = '1';
        box.setAttribute('aria-label', `Swapped: ${words}`);
        tick.appendChild(box);
        tick.appendChild(document.createTextNode('Swapped'));
        row.appendChild(go);
        row.appendChild(tick);
        host.appendChild(row);
    });
}

// ── a game controller paired with the phone ──────────────────────────────

function padList() {
    try {
        return Array.from((typeof navigator.getGamepads === 'function' && navigator.getGamepads()) || [])
            .filter(p => p && p.connected !== false);
    } catch (_) { return []; }
}

// The menu's Controller buttons shows while one is connected; it opens
// the button list.
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
    plog('idm_phone_pad', { connected: true, name: idmPadName(pad.id), buttons: (pad.buttons || []).length },
        { msg: `Phone controller connected: ${idmPadName(pad.id)}` });
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
    plog('idm_phone_pad', { connected: false, name }, { msg: `Phone controller disconnected: ${name}` });
    toast(`Controller disconnected: ${name}`);
    padHelp();
    padRun();
});
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') holdStop();
    padRun();
});

// ── wiring ────────────────────────────────────────────────────────────────

let socket = null;

function wire() {
    document.querySelectorAll('[data-ph-move]').forEach(b => {
        // A press starts the hold; the finger lifting, the touch being
        // cancelled (a scroll, a call) or the button losing it ends it.
        b.addEventListener('pointerdown', (e) => {
            if (e.button !== undefined && e.button !== 0) return;
            e.preventDefault();
            try { b.setPointerCapture(e.pointerId); } catch (_) { /* an older phone: the ends below still fire */ }
            holdArrow(b.dataset.phMove);
        });
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(ev => b.addEventListener(ev, holdStop));
        // the keyboard's Enter or Space on a focused arrow: one step
        b.addEventListener('click', (e) => { if (e.detail === 0) jobs.move(b.dataset.phMove, false); });
        b.addEventListener('contextmenu', (e) => e.preventDefault());
    });
    window.addEventListener('blur', holdStop);
    window.addEventListener('pagehide', holdStop);
    $('ph-mark').addEventListener('click', () => { startMark(); endMark(); });
    $('ph-undo').addEventListener('click', () => jobs.undo());
    $('ph-redo').addEventListener('click', () => jobs.redo());
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
    $('ph-menu-open').addEventListener('click', () => openSheet('menu'));
    $('ph-menu-close').addEventListener('click', () => closeSheet());
    $('ph-swap-close').addEventListener('click', () => closeSheet());
    $('ph-pad-open').addEventListener('click', () => openSheet('pad'));
    $('ph-pad-close').addEventListener('click', () => closeSheet());
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && S.sheet) closeSheet();
    });
    window.addEventListener('popstate', (e) => {
        const want = e.state && e.state.phSheet;
        if (want === S.sheet) return;
        S.sheet = SHEETS[want] ? want : null;
        render();
    });
    // Swap mode: its switch, its chip (the colors open under it), a color,
    // and the main screen's tag, which opens the swap list.
    document.querySelectorAll('[data-ph-swap]').forEach(b => {
        b.addEventListener('click', () => setSwap({ on: b.dataset.phSwap === 'on' }));
    });
    $('ph-swap-color').addEventListener('click', () => {
        S.swapColors = !S.swapColors;
        render();
    });
    document.querySelectorAll('[data-ph-swap-color]').forEach(b => {
        b.addEventListener('click', () => {
            S.swapColors = false;
            setSwap({ color: b.dataset.phSwapColor });
        });
    });
    $('ph-swap-tag').addEventListener('click', () => openSheet('swap'));
    document.querySelectorAll('[data-ph-side]').forEach(b => {
        b.addEventListener('click', () => {
            S.side = b.dataset.phSide === 'back' ? 'back' : 'front';
            writeStore(SIDE_KEY, S.side);
            render();
        });
    });
    // the open list and the Swapped list: a row's words find the module,
    // its tick moves it from one list to the other
    ['ph-list', 'ph-swapped-list'].forEach(id => {
        const list = $(id);
        list.addEventListener('click', (e) => {
            const rows = e.target.closest('[data-ph-rows]');
            if (rows) {
                setRowsFrom(Number(rows.dataset.phLayer), rows.dataset.phRows);
                return;
            }
            if (e.target.closest('.ph-swap')) return;
            const row = e.target.closest('[data-ph-key]');
            if (!row || blocked() || swapRefuses()) return;
            setHighlight({ layerId: Number(row.dataset.phLayer), key: row.dataset.phKey });
        });
        list.addEventListener('change', (e) => {
            const box = e.target.closest('[data-ph-swap]');
            const row = box && box.closest('[data-ph-key]');
            if (!row) return;
            setSwapped(Number(row.dataset.phLayer), row.dataset.phKey, box.checked);
        });
    });
    idmPadFillHelp($('ph-pad-map'));

    socket = window.io ? window.io() : null;
    if (!socket) {
        render();
        return;
    }
    socket.on('connect', () => {
        const again = !!S.everConnected;
        S.everConnected = true;
        S.connected = true;
        const sn = screenNow();
        plog('idm_phone_connect', { reconnect: again, ...sn },
            { msg: `Phone page ${again ? 'connected again' : 'connected'}, ${sn.window[0]}x${sn.window[1]} ${sn.orientation}` });
        render();
        checkShow();
    });
    socket.on('disconnect', (why) => {
        S.connected = false;
        if (S.stroke) S.stroke = null;
        plog('idm_phone_disconnect', { why: String(why || '') },
            { level: 'warn', msg: `Phone page lost the computer (${String(why || 'no reason given')})` });
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
    socket.on('idm_swap_updated', (data) => {
        if (!data || data.origin === ORIGIN || !app.project) return;
        app.project.idmSwap = idmSwapOf(data.swap);
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
    S, jobs, app, renderer: r, origin: ORIGIN, render, setSwapped, setSwap, padTick, openSheet, closeSheet, holdStop,
    socket: () => socket,
};

// A reload while a sheet was open lands on the controls.
try {
    if (history.state && history.state.phSheet) history.replaceState(null, '');
} catch (_) { /* nothing to tidy */ }
{
    const sn = screenNow();
    S.held = sn.window[0] > sn.window[1] ? 'landscape' : 'portrait';
}
wire();
// A pad paired before the page loaded shows once a button is pressed.
for (const pad of padList()) S.padNames.set(pad.index, idmPadName(pad.id));
padHelp();
padRun();
