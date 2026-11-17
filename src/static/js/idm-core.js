// idm-core: the IDM Locator's rules that the computer's tab
// (app-idm-locator.js, app-idm-gamepad.js) and the phone page
// (idm-phone.js) both run, so a step, a screen or canvas jump, a module's
// name, the swap list and a locked screen read the same on every device.
// No imports and nothing of the designer: the phone page loads it with the
// renderer's geometry (canvas.js, canvas-labels.js, canvas-idm.js) and
// nothing else. `r` below is a CanvasRenderer (the designer's, or the
// phone's own, never drawn), `project` the show as the server holds it.

export const MAX_MODULES = 64;
export const DEFAULT_COLOR = '#ff1a1a';
// The field's border styles; white with shaded borders when unset.
export const FIELD_BORDERS = ['shade', 'lines', 'ticks', 'none'];
export const FIELD_DEFAULT = { color: '#ffffff', border: 'shade', moduleIds: false };
// The Colours (app.sanitize_idm_field): the three plain colour settings,
// and how many saved mark colours a show may keep.
export const COLOUR_KEYS = ['labelColor', 'moduleEdgeColor', 'cabinetEdgeColor'];
export const PRESETS_MAX = 12;
export const ARROWS = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
};
const DIRS = { left: 'ArrowLeft', right: 'ArrowRight', up: 'ArrowUp', down: 'ArrowDown' };

export function idmCount(value) {
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

// "col,row,mx,my" as whole numbers, or null.
export function idmKey(value) {
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

// One mark held to its shape (app.sanitize_idm): style 'color' or 'x', a
// colour, and swapped: true only once the module has been replaced.
export function idmMarkOf(mark) {
    const out = {
        style: mark && mark.style === 'x' ? 'x' : 'color',
        color: idmColor(mark && mark.color) || DEFAULT_COLOR,
    };
    if (mark && mark.swapped === true) out.swapped = true;
    return out;
}

// The shade setting: '#rrggbb', a whole percent 0..100 (half up), or null
// for Auto (app.idm_shade_level).
export function idmShadeLevel(value) {
    if (typeof value === 'number') {
        if (!Number.isFinite(value) || value < 0 || value > 100) return null;
        return Math.floor(value + 0.5);
    }
    return idmColor(value);
}

// The saved mark colours: '#rrggbb' each, no repeats, at most PRESETS_MAX;
// null when not a list (app.idm_mark_presets).
export function idmMarkPresets(value) {
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
export function idmHighlightOf(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const id = value.layerId;
    if (typeof id !== 'number' || !Number.isInteger(id)) return null;
    const key = typeof value.key === 'string' ? idmKey(value.key) : null;
    return key ? { layerId: id, key } : null;
}

// JSON with every object's keys in order: two copies of a block compare
// equal however the server or the socket ordered them.
export function idmCanonical(value) {
    const walk = (v) => {
        if (Array.isArray(v)) return v.map(walk);
        if (v && typeof v === 'object') {
            const out = {};
            Object.keys(v).sort().forEach(k => { out[k] = walk(v[k]); });
            return out;
        }
        return v;
    };
    return JSON.stringify(walk(value === undefined ? null : value));
}

function isScreen(layer) {
    return !!layer && (layer.type || 'screen') === 'screen';
}

function layersOf(project) {
    return (project && Array.isArray(project.layers)) ? project.layers : [];
}

export function idmMarkCount(layer) {
    const marks = layer && layer.idm && layer.idm.marks;
    return (marks && typeof marks === 'object') ? Object.keys(marks).length : 0;
}

// ── where the highlight is, and where it goes ─────────────────────────────

// The canvas a screen stands on in this view ('' for a show with none).
export function idmCanvasIdOf(r, layer) {
    if (!r || !layer || typeof r._effectiveLayerCanvasId !== 'function') return '';
    return r._effectiveLayerCanvasId(layer) || '';
}

// The module a highlight names: {layer, panel, cell, key}, or null when
// its screen, cabinet or module is not there.
export function idmTargetOf(r, project, hl) {
    if (!hl || !r || !project) return null;
    const layer = layersOf(project).find(l => l && l.id === hl.layerId);
    if (!isScreen(layer)) return null;
    const parts = String(hl.key).split(',').map(n => parseInt(n, 10));
    if (parts.length !== 4 || parts.some(n => !Number.isFinite(n))) return null;
    const panel = (layer.panels || []).find(p => p && (p.col || 0) === parts[0] && (p.row || 0) === parts[1]);
    if (!panel) return null;
    const counts = r.idmCounts(layer);
    const cell = r.idmModuleCells(layer, panel, counts.x, counts.y, r._idmVisibleLookup(layer))
        .find(c => c.mx === parts[2] && c.my === parts[3]);
    if (!cell) return null;
    return { layer, panel, cell, key: hl.key };
}

// One step from module `t` (an idmTargetOf answer) in `dir` ('left',
// 'right', 'up', 'down' or an Arrow key name), or with `cabinet` one whole
// cabinet. The step is taken on the wall as drawn (a turned screen steps
// the way it looks), carries on across cabinet edges and onto the next
// screen in that row of the SAME canvas, and stops at the last module:
// {layerId, key}, or null when there is nowhere to go.
export function idmStepFrom(r, t, dir, cabinet = false) {
    const vec = ARROWS[DIRS[dir] || dir];
    if (!vec || !t || !r) return null;
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
        // A whole cabinet on: the point one cabinet along, as the cabinet
        // stands on the wall (a quarter turn swaps its sides). A blanked
        // cabinet is stepped over; past the last one, stop.
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
    return pick ? { layerId: pick.layer.id, key: pick.key } : null;
}

// The top-left module (as drawn) of a list of module rectangles.
function topLeft(list) {
    return list.reduce((a, m) => ((m.y < a.y - 0.5 || (Math.abs(m.y - a.y) <= 0.5 && m.x < a.x)) ? m : a));
}

// Where a highlight starts: the first module (top-left as drawn) of
// `layer`, else of the topmost-leftmost screen - kept to `canvasId` when
// one is given (null: any canvas). {layerId, key} or null.
export function idmStartModule(r, { layer = null, canvasId = null } = {}) {
    if (!r || typeof r.idmModuleRects !== 'function') return null;
    const onCanvas = (l) => canvasId === null || canvasId === undefined || idmCanvasIdOf(r, l) === canvasId;
    let mods = isScreen(layer) && onCanvas(layer) ? r.idmModuleRects(l => l === layer) : [];
    if (!mods.length) mods = r.idmModuleRects(onCanvas);
    if (!mods.length) return null;
    const first = topLeft(mods);
    const start = topLeft(mods.filter(m => m.layer === first.layer));
    return { layerId: start.layer.id, key: start.key };
}

// The first module of the next screen after the highlighted one, in the
// Screens order, round to the first after the last - only screens on
// `canvasId` when one is given. {layerId, key} or null.
export function idmNextScreenFrom(r, hl, canvasId = null) {
    if (!r || typeof r.idmModuleRects !== 'function') return null;
    const keep = (canvasId === null || canvasId === undefined) ? undefined : (l => idmCanvasIdOf(r, l) === canvasId);
    const mods = r.idmModuleRects(keep);
    if (!mods.length) return null;
    const order = [];
    mods.forEach(m => { if (!order.includes(m.layer)) order.push(m.layer); });
    const at = hl ? order.findIndex(l => l.id === hl.layerId) : -1;
    const next = order[(at + 1) % order.length];
    const first = topLeft(mods.filter(m => m.layer === next));
    return { layerId: next.id, key: first.key };
}

// The canvases that have a module to highlight, in the show's order:
// [{id, name}]. A show with no canvases is one, id ''.
export function idmCanvasList(r, project) {
    if (!r || typeof r.idmModuleRects !== 'function') return [];
    const mods = r.idmModuleRects();
    const ids = new Set(mods.map(m => idmCanvasIdOf(r, m.layer)));
    const canvases = (project && Array.isArray(project.canvases)) ? project.canvases : [];
    if (!canvases.length) return ids.size ? [{ id: '', name: (project && project.name) || 'Canvas' }] : [];
    return canvases.filter(c => c && ids.has(c.id || '')).map(c => ({ id: c.id, name: c.name || c.id }));
}

// The canvas the controls are on: the highlight's; with none, the one
// last used here (`remembered`), else the show's active canvas, else the
// first with modules. null when no canvas has one.
export function idmActiveCanvas(r, project, hl, remembered = null) {
    const list = idmCanvasList(r, project);
    if (!list.length) return null;
    const t = idmTargetOf(r, project, hl);
    if (t) return idmCanvasIdOf(r, t.layer);
    const has = (id) => id !== null && id !== undefined && list.some(c => c.id === id);
    if (has(remembered)) return remembered;
    const active = project && project.active_canvas_id;
    if (has(active)) return active;
    return list[0].id;
}

// The next canvas with modules after `canvasId`, round to the first, and
// its first module: {canvasId, layerId, key}, or null when there is no
// other canvas.
export function idmNextCanvasFrom(r, project, canvasId) {
    const list = idmCanvasList(r, project);
    if (list.length < 2 && list.some(c => c.id === canvasId)) return null;
    if (!list.length) return null;
    const at = list.findIndex(c => c.id === canvasId);
    const next = list[(at + 1) % list.length];
    const start = idmStartModule(r, { canvasId: next.id });
    return start ? { canvasId: next.id, ...start } : null;
}

// ── names ─────────────────────────────────────────────────────────────────

// Screen · Cabinet ID · Module for one module, as the list and the
// readouts print it. `back`: the module named as it reads from behind the
// wall (canvas-idm idmModuleLabeler), its column counted from the other
// side; the Cabinet ID stays the cabinet's own, as the binder's Rear view
// prints it. Null when the module is not there.
export function idmDescribe(r, layer, key, { back = false } = {}) {
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
    const module = r.idmModuleLabeler(layer, { back })(cell, cells);
    const col = xs.indexOf(parts[2]) + 1;
    return {
        screen, cabinet, module,
        row: ys.indexOf(parts[3]) + 1, col: back ? xs.length - col + 1 : col,
        text: `${screen} · ${cabinet} · Module ${module}`,
    };
}

// Every mark, screen by screen: [{layer, rows}], each row {key, panel,
// index, cabinet, module, row, col, style, color, swapped}. Rows run in
// reading order, cabinet by cabinet (from the front, whichever side the
// names read from, so a row never moves when the side changes).
export function idmMarkGroups(r, project, { back = false } = {}) {
    const groups = [];
    if (!r || !project) return groups;
    for (const layer of layersOf(project)) {
        if (!isScreen(layer) || idmMarkCount(layer) === 0) continue;
        const labelOf = r.cabinetIdLabeler(layer);
        const moduleOf = r.idmModuleLabeler(layer, { back });
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
            const mark = idmMarkOf(layer.idm.marks[key]);
            const col = xs.indexOf(parts[2]) + 1;
            rows.push({
                key, panel, index,
                cabinet: labelOf(panel),
                module: moduleOf(cell, cells),
                row: ys.indexOf(parts[3]) + 1,
                col: back ? xs.length - col + 1 : col,
                style: mark.style, color: mark.color, swapped: !!mark.swapped,
            });
        });
        rows.sort((a, b) => (a.panel.row - b.panel.row) || (a.panel.col - b.panel.col) || (a.index - b.index));
        if (rows.length) groups.push({ layer, rows });
    }
    return groups;
}

// ── locks ─────────────────────────────────────────────────────────────────

export function idmResolveGroup(project, group) {
    if (typeof group === 'string') {
        const groups = (project && project.groups) || [];
        return groups.find(g => g && g.id === group) || null;
    }
    return group || null;
}

export function idmGroupMembers(project, group) {
    const g = idmResolveGroup(project, group);
    if (!g || !Array.isArray(g.layer_ids)) return [];
    const byId = new Map(layersOf(project).map(l => [l.id, l]));
    const out = [];
    g.layer_ids.forEach(id => {
        const l = byId.get(id);
        if (l && !out.includes(l)) out.push(l);
    });
    return out;
}

// The screens that hold `layer` from a change: itself when locked, the
// locked members of a half-locked group it is in (the designer's
// _layerLocked and _lockedErrorNames), or [] when it is free.
export function idmLockedBy(project, layer) {
    if (!layer) return [];
    if (layer.locked) return [layer];
    if (!layer.group_id) return [];
    const g = idmResolveGroup(project, layer.group_id);
    if (!g) return [];
    const members = layersOf(project).filter(l => l && l.group_id === g.id && isScreen(l));
    const locked = members.filter(l => l.locked);
    if (!locked.length || locked.length === members.length) return [];
    return locked;
}

// The designer's locked error, word for word (_showLockedError).
export function idmLockedMessage(layers) {
    const names = [];
    (layers || []).forEach(l => {
        const n = (l && l.name) || 'Screen';
        if (!names.includes(n)) names.push(n);
    });
    if (!names.length) return '';
    if (names.length === 1) return `${names[0]} is locked. Unlock it to change it.`;
    const list = names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
    return `${list} are locked. Unlock them to change them.`;
}

// ── edits ─────────────────────────────────────────────────────────────────

// `layer.idm` as a fresh, whole block (its own marks, each its own copy),
// so an edit never writes into an object an earlier state still holds.
export function idmBlockOf(r, layer) {
    const counts = r ? r.idmCounts(layer) : { x: 1, y: 1 };
    const raw = (layer && layer.idm && layer.idm.marks && typeof layer.idm.marks === 'object' && !Array.isArray(layer.idm.marks))
        ? layer.idm.marks : {};
    const marks = {};
    Object.keys(raw).forEach(k => { marks[k] = { ...raw[k] }; });
    return { modulesX: counts.x, modulesY: counts.y, marks };
}

// One module of a stroke: marked in `style` and `color` ('mark') or
// cleared ('clear'). A module already marked keeps its Swapped tick when
// it is marked again.
export function idmApplyMark(block, key, mode, style, color) {
    if (mode === 'clear') {
        delete block.marks[key];
        return;
    }
    const was = block.marks[key];
    const next = { style: style === 'x' ? 'x' : 'color', color: idmColor(color) || DEFAULT_COLOR };
    if (was && was.swapped === true) next.swapped = true;
    block.marks[key] = next;
}

// The Swapped tick of the mark on `key`: true when the block changed.
export function idmApplySwapped(block, key, on) {
    const mark = block.marks[key];
    if (!mark) return false;
    if (!!mark.swapped === !!on) return false;
    if (on) mark.swapped = true;
    else delete mark.swapped;
    return true;
}
