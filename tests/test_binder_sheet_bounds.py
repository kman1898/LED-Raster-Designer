"""Nothing a binder sheet draws runs out of its drawing area.

A contributor's letter-size binder (2026-11-17): "i have a few instances of
things just running all the way in to the title block". Every sheet the
binder lays out is laid out for its drawing area - the room left of the
title block, inside the border - and at letter and A4 that room is a third
narrower than on tabloid. A layout that does not fit it at its base size
has to scale to the width the sheet allows, move what sits beside the
drawing under it, or continue on the next sheet; it may never simply run
on into the title block (or off the sheet's other edges).

Measured on the display list itself (app-binder.js _bRecCtx): every op the
sheet's BODY records - texts measured in their own font, lines and rects
at their centre lines, images - once the frame (border, title block, rev) is
down, against the drawing area as the app has it (_bGeo). Every sheet of
every show below, at letter and A4, the title block on and off.

The shows are synthetic and busy on purpose: long screen, distro and
processor names, groups, header and footer bars, fiber with backups, sixteen
processors, IP addresses. The real shows in the git-ignored
tests/fixtures-local are swept too when they are there (CI skips them).

Run locally (each session takes its own free port):
    python -m pytest tests/test_binder_sheet_bounds.py -v --browser chromium
"""

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import open_app, private_fixture, private_fixture_missing  # noqa: E402
from test_binder import SEED_JS as BINDER_SEED_JS  # noqa: E402
from test_fiber_connections import SEED_JS as FIBER_SEED_JS  # noqa: E402
from test_hidden_screen_binder import FEED_JS  # noqa: E402
from test_binder_wiring import LOAD_JS  # noqa: E402

SHOW_A = private_fixture('live-show-a-live.json', 'LRD_LIVE_SHOW_A_JSON')
SHOW_B = private_fixture('live-show-b.json', 'LRD_PULL_SMOKE_JSON')

SMALL = ('letter', 'a4')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _opts(**kw):
    opts = {'sheet': 'letter', 'palette': 'colour', 'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
            'fiber': True, 'network': True, 'rigging': True, 'wiring': True, 'titleBlock': True}
    opts.update(kw)
    return opts


# Every sheet painted in one pass, and of each the ops its BODY recorded
# (the frame - white, border, title block, rev - is what _bPageFrame drew,
# counted off as it is drawn) that stand outside the drawing area by more
# than a hair: each with its extent and by how much it is over on each
# side. `tb` is where the title block starts (the sheet's right margin with
# the block off).
BOUNDS_JS = """([opts, tol]) => {
    const app = window.app;
    const own = Object.prototype.hasOwnProperty.call(app, '_bPageFrame');
    const frame = app._bPageFrame;
    const marks = [];
    app._bPageFrame = function (book, page) {
        const r = frame.call(this, book, page);
        marks[page.index] = page.ops.length;
        return r;
    };
    let plan, recs;
    try {
        plan = app.planBinder(opts);
        recs = app.renderBinderPages(opts, {bitmaps: false});
    } finally {
        if (own) app._bPageFrame = frame; else delete app._bPageFrame;
    }
    const mc = document.createElement('canvas').getContext('2d');
    const on = opts.titleBlock !== false;
    const out = [];
    recs.forEach((rec, i) => {
        const g = app._bGeo({w: rec.width, h: rec.height}, on);
        const da = g.da;
        const bad = [];
        for (const o of rec.ops.slice(marks[i] || 0)) {
            let x0, y0, x1, y1, what;
            if (o.op === 'text') {
                const t = String(o.text);
                if (!t.trim()) continue;
                mc.font = app._bFont(o.size, o.weight);
                const w = mc.measureText(t).width, s = o.size;
                const lx = o.align === 'center' ? -w / 2 : (o.align === 'right' || o.align === 'end') ? -w : 0;
                const b = o.baseline;
                const [ly0, ly1] = b === 'middle' ? [-0.36 * s, 0.36 * s]
                    : (b === 'top' || b === 'hanging') ? [0, 0.9 * s]
                    : b === 'bottom' ? [-0.95 * s, 0] : [-0.72 * s, 0.05 * s];
                const c = Math.cos(o.rotate || 0), sn = Math.sin(o.rotate || 0);
                const pts = [[lx, ly0], [lx + w, ly0], [lx, ly1], [lx + w, ly1]]
                    .map(([px, py]) => [o.x + c * px - sn * py, o.y + sn * px + c * py]);
                x0 = Math.min(...pts.map(p => p[0])); x1 = Math.max(...pts.map(p => p[0]));
                y0 = Math.min(...pts.map(p => p[1])); y1 = Math.max(...pts.map(p => p[1]));
                what = 'text ' + t;
            } else if (o.op === 'line') {
                // (a rule is where its centre runs: one drawn ON the
                // drawing area's edge - a processor's block, a lane at the
                // room's edge - is on it, half its pen either side)
                const xs = o.points.map(p => p[0]), ys = o.points.map(p => p[1]);
                x0 = Math.min(...xs); x1 = Math.max(...xs);
                y0 = Math.min(...ys); y1 = Math.max(...ys);
                what = 'line';
            } else if (o.op === 'rect' || o.op === 'image') {
                x0 = Math.min(o.x, o.x + o.w); x1 = Math.max(o.x, o.x + o.w);
                y0 = Math.min(o.y, o.y + o.h); y1 = Math.max(o.y, o.y + o.h);
                what = o.op === 'image' ? 'image' : (o.fill ? 'rect ' + o.fill : 'rect');
            } else continue;
            const over = {
                right: x1 - (da.x + da.w), left: da.x - x0,
                top: da.y - y0, bottom: y1 - (da.y + da.h),
            };
            const worst = Math.max(over.right, over.left, over.top, over.bottom);
            if (worst > tol) {
                bad.push({what: what.slice(0, 60), x0: Math.round(x0), y0: Math.round(y0),
                          x1: Math.round(x1), y1: Math.round(y1),
                          right: Math.round(over.right), left: Math.round(over.left),
                          top: Math.round(over.top), bottom: Math.round(over.bottom),
                          intoBlock: on && x1 > g.tb.x + 0.5});
            }
        }
        const p = plan[i] || {};
        out.push({n: p.number, kind: p.kind, title: p.title, scale: p.scale,
                  da: {x: da.x, y: da.y, w: da.w, h: da.h}, tb: g.tb.x, bad});
    });
    return out;
}"""

# How far past the drawing area's edge a mark may stand: a rounding hair,
# a hundredth of an inch.
TOL = 2.0


def _bounds(pg, **kw):
    return pg.evaluate(BOUNDS_JS, [_opts(**kw), TOL])


def _offenders(report):
    """One line per sheet that draws outside its drawing area: the sheet,
    how far over at worst on which side, and the first few marks."""
    lines = []
    for s in report:
        if not s['bad']:
            continue
        worst = max(s['bad'], key=lambda b: max(b['right'], b['left'], b['top'], b['bottom']))
        side = max(('right', 'left', 'top', 'bottom'), key=lambda k: worst[k])
        lines.append('%s %s (%s, scale %s): %d marks, worst %s by %d%s - %s' % (
            s['n'], s['title'], s['kind'], s['scale'], len(s['bad']), side, worst[side],
            ' INTO THE TITLE BLOCK' if any(b['intoBlock'] for b in s['bad']) else '',
            '; '.join('%s [%d,%d - %d,%d]' % (b['what'], b['x0'], b['y0'], b['x1'], b['y1'])
                      for b in s['bad'][:4])))
    return lines


# ── the shows ────────────────────────────────────────────────────────────

# Long names everywhere a sheet prints one: the screens, the group, the
# distro, the processor and its card.
LONG_NAMES_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const names = {'WALL-A': 'UPSTAGE LEFT MAIN IMAG WALL', 'WALL-B': 'UPSTAGE RIGHT MAIN IMAG WALL',
                   'CENTER': 'DOWNSTAGE CENTER FLOOR RISER FASCIA'};
    for (const l of app.project.layers) {
        if (names[l.name]) await j('PUT', `/api/layer/${l.id}`, {name: names[l.name]});
    }
    let p = await j('GET', '/api/project');
    for (const g of p.groups || []) g.name = 'STAGE RIGHT SIDE IMAG BEACH';
    for (const d of p.distros || []) d.name = 'STAGE RIGHT POWER DISTRO RACK 1';
    await j('PUT', '/api/project', p);
    for (const proc of p.processors || []) {
        await j('PUT', `/api/processors/${proc.id}`, {name: 'FRONT OF HOUSE VIDEO WORLD PROCESSOR A',
            network: {ip: '192.168.100.200', subnet: '255.255.255.0', gateway: '192.168.100.1',
                      note: 'control laptop on the FOH switch, port 24, VLAN 300'}});
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('bounds_long_names');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    return app.project.layers.map(l => l.name);
}"""

# Every processor of the fiber show with an IP (the Network page), its
# backup unit too, and the walls with header and footer bars.
FIBER_EXTRAS_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let p = await j('GET', '/api/project');
    let n = 10;
    for (const proc of p.processors || []) {
        const body = {network: {ip: `10.10.20.${n}`, subnet: '255.255.255.0', gateway: '10.10.20.1',
                                note: 'video world switch, rack 2, top patch panel'}};
        // (a backup unit's own address only where there is one)
        if (proc.backupUnit) body.backupNetwork = {ip: `10.10.20.${n + 100}`, note: 'backup unit, same switch'};
        await j('PUT', `/api/processors/${proc.id}`, body);
        n++;
    }
    p = await j('GET', '/api/project');
    for (const l of p.layers) { l.riggingBars = [2, 2, 1]; l.riggingFooterBars = [4, 1]; }
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('bounds_fiber_extras');
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    return (app._processorsResolved || []).length;
}"""

# Sixteen SX40s, four XDs each on the processor's own TAC, a fan-out on
# the first: the Fiber page past one sheet, sixteen processor sheets.
MANY_JS = """async (n) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.binder;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'MAIN LED WALL CENTER STAGE', columns: 16, rows: 9,
                                       cabinet_width: 200, cabinet_height: 200});
    const last = (st) => st.processors[st.processors.length - 1];
    const cable = (st) => st.fiberCables[st.fiberCables.length - 1];
    for (let i = 0; i < n; i++) {
        let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40',
                                                      name: `VIDEO WORLD RACK ${i + 1} PROCESSOR`});
        const sx = last(st).id;
        const xds = last(st).slots[0].card.cvts.map(b => b.id);
        st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300,
                                                   connector: 'LC duplex', link: {boxId: xds[0], key: 'p1'}});
        const tac = cable(st);
        for (const b of xds.slice(1)) {
            await j('PUT', `/api/processors/${sx}/cvts/${b}/fiber-links/p1`, {cable: tac.id});
        }
        await j('PUT', `/api/processors/${sx}/cvts/${xds[0]}/fiber-links/p1`,
                {extension: {kind: 'fanout', ft: 10}});
        await j('PUT', `/api/processors/${sx}`, {network: {ip: `10.0.0.${i + 10}`, subnet: '255.255.255.0',
                                                          gateway: '10.0.0.1'}});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('bounds_many');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    return (app._processorsResolved || []).length;
}"""


# Walls that strain the sheet: a tall one, a wide one with many multis on
# two long-named distros (a bracket key), a grouped pair with header and
# footer bars, on an H9's two cards; a service over the distros.
WALLS_JS = """async () => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services; delete proj.cableStock; delete proj.fiberCables; delete proj.binder;
    proj.raster_width = proj.show_raster_width = 7680; proj.raster_height = proj.show_raster_height = 4320;
    for (const c of proj.canvases || []) {
        c.raster_width = c.show_raster_width = 7680; c.raster_height = c.show_raster_height = 4320;
    }
    await j('PUT', '/api/project', proj);
    const power = {powerVoltage: 208, powerAmperage: 20, panelWatts: 180, powerOrganized: true,
                   processorType: 'novastar-armor'};
    const walls = [
        {name: 'STAGE LEFT VERTICAL IMAG TOWER', columns: 6, rows: 24, offset_x: 0,
         powerFlowPattern: 'tl-v', flowPattern: 'tl-v'},
        {name: 'UPSTAGE CENTER WIDE BACKDROP WALL', columns: 36, rows: 6, offset_x: 1400, powerAmperage: 10,
         powerFlowPattern: 'tl-v', flowPattern: 'tl-h'},
        {name: 'DOWNSTAGE LEFT SIDE FILL', columns: 8, rows: 5, offset_x: 0, offset_y: 5000,
         powerFlowPattern: 'tl-h', flowPattern: 'tl-h'},
        {name: 'DOWNSTAGE RIGHT SIDE FILL', columns: 8, rows: 5, offset_x: 1600, offset_y: 5000,
         powerFlowPattern: 'tl-h', flowPattern: 'tl-h', panelWatts: 150},
    ];
    for (const w of walls) {
        await j('POST', '/api/layer/add', {cabinet_width: 128, cabinet_height: 128, ...power, ...w});
    }
    let p = await j('GET', '/api/project');
    const L = p.layers.find(l => l.name === 'DOWNSTAGE LEFT SIDE FILL');
    const R = p.layers.find(l => l.name === 'DOWNSTAGE RIGHT SIDE FILL');
    L.group_id = 'g1'; R.group_id = 'g1';
    L.riggingBars = [2, 2, 2, 2]; L.riggingFooterBars = [4, 4];
    R.riggingBars = [2, 1, 1, 2, 2];
    p.layers.find(l => l.name.startsWith('UPSTAGE')).riggingBars = Array(18).fill(2);
    p.groups = [{id: 'g1', name: 'DOWNSTAGE SIDE FILL PAIR BOTH SIDES', layer_ids: [L.id, R.id],
                 routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    // an H9 with two 16 x RJ45 cards: the tall and the wide wall on the
    // first, the side fills on the second
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'VIDEO WORLD MAIN H9 RACK A'});
    const pid = st.processors[st.processors.length - 1].id;
    const cards = [];
    for (const i of [0, 1]) {
        st = await j('PUT', `/api/processors/${pid}/slots/${i}`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        cards.push(st.processors.find(x => x.id === pid).slots.find(x => x.index === i).card.id);
    }
    await j('PUT', `/api/processors/${pid}/cards/${cards[0]}`, {name: 'UPSTAGE AND TOWER'});
    await j('PUT', `/api/processors/${pid}`, {network: {ip: '10.20.30.40', subnet: '255.255.255.0',
        gateway: '10.20.30.1', note: 'main control laptop, FOH video world switch port 12'}});
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('bounds_walls');
    const s = app.addService({name: 'HOUSE COMPANY SWITCH STAGE RIGHT 400A'});
    const d1 = app.addDistro({name: 'STAGE LEFT POWER DISTRO RACK A'});
    const d2 = app.addDistro({name: 'UPSTAGE CENTER POWER DISTRO RACK B'});
    for (const d of [d1, d2]) if (s) app.setDistroService(d.id, s.id);
    let n = 0;
    for (const l of app.project.layers) {
        const k = app.screenCircuits(l).length;
        const multis = Math.ceil(k / 6);
        for (let m = 1; m <= multis; m++) {
            const d = l.name.startsWith('UPSTAGE') ? d2 : d1;
            app.setSocaDistro(l, m, d.id); app.setSocaNumber(l, m, ++n); app.setSocaLength(l, m, String(75 + 25 * (m % 4)));
        }
        l.showPowerCableTags = true;
    }
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    for (const [i, l] of app.project.layers.entries()) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId: cards[i < 2 ? 0 : 1]});
        await app.refreshPortAssignment();
    }
    await app.refreshProcessors();
    app.selectLayer(app.project.layers[0]);
    app.renderLayers();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    app.resetHistory('Sheet Bounds Walls');
    return {layers: app.project.layers.length, distros: app.getDistros().length,
            circuits: app.project.layers.map(l => app.screenCircuits(l).length),
            ports: app.project.layers.map(l => !!app._screenPortPin(l, 1))};
}"""

# A real show's shape on a letter binder (owner, 2026-11-18): nine loose
# screens - nine positions - with long names, each with power, data and
# header bars, two distros, an H9: about sixty sheets, a CONTENTS too long
# to stand beside the map on letter, POSITIONS names that wrapped three
# lines tall in a one-column table.
NINE_JS = """async () => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services; delete proj.cableStock; delete proj.fiberCables; delete proj.binder;
    proj.raster_width = proj.show_raster_width = 7680; proj.raster_height = proj.show_raster_height = 4320;
    for (const c of proj.canvases || []) {
        c.raster_width = c.show_raster_width = 7680; c.raster_height = c.show_raster_height = 4320;
    }
    await j('PUT', '/api/project', proj);
    const names = ['Screen A - HL IMAG - SWITCH', 'Screen B - HR IMAG - SWITCH', 'Screen C - LEFT PILLAR TALL',
                   'Screen D - RIGHT PILLAR TALL', 'Screen E - UPSTAGE WIDE BACKDROP', 'Screen F - DOWNSTAGE LIP FASCIA',
                   'Screen G - CENTER HANG MAIN', 'Screen H - SIDE FILL LEFT DELAY', 'Screen I - SIDE FILL RIGHT DELAY'];
    const sizes = [[16, 9], [16, 9], [5, 10], [5, 10], [30, 4], [30, 4], [20, 6], [9, 5], [9, 5]];
    for (const [i, name] of names.entries()) {
        await j('POST', '/api/layer/add', {name, columns: sizes[i][0], rows: sizes[i][1],
            cabinet_width: 128, cabinet_height: 128, offset_x: (i % 3) * 4200, offset_y: Math.floor(i / 3) * 1400,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 120, powerOrganized: true,
            powerFlowPattern: 'tl-h', flowPattern: 'tl-h', processorType: 'novastar-armor'});
    }
    let p = await j('GET', '/api/project');
    for (const l of p.layers) l.riggingBars = Array(Math.floor(l.columns / 2)).fill(2);
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'VIDEO WORLD H9 MAIN'});
    const pid = st.processors[st.processors.length - 1].id;
    const cards = [];
    for (const i of [0, 1]) {
        st = await j('PUT', `/api/processors/${pid}/slots/${i}`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        cards.push(st.processors.find(x => x.id === pid).slots.find(x => x.index === i).card.id);
    }
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('bounds_nine');
    const d1 = app.addDistro({name: 'STAGE LEFT DISTRO'});
    const d2 = app.addDistro({name: 'STAGE RIGHT DISTRO'});
    let n = 0;
    for (const [i, l] of app.project.layers.entries()) {
        const multis = Math.ceil(app.screenCircuits(l).length / 6);
        for (let m = 1; m <= multis; m++) {
            const d = i % 2 ? d2 : d1;
            app.setSocaDistro(l, m, d.id); app.setSocaNumber(l, m, ++n); app.setSocaLength(l, m, '100');
        }
    }
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    for (const [i, l] of app.project.layers.entries()) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId: cards[i % 2]});
        await app.refreshPortAssignment();
    }
    await app.refreshProcessors();
    app.selectLayer(app.project.layers[0]);
    app.renderLayers();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    app.resetHistory('Sheet Bounds Nine');
    return {layers: app.project.layers.length,
            circuits: app.project.layers.map(l => app.screenCircuits(l).length),
            ports: app.project.layers.map(l => !!app._screenPortPin(l, 1))};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    open_app(pg, e2e_server)
    # the export never opens a save dialog here, but stub it all the same
    pg.route('**/api/native-dialog**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"cancelled": true}'))
    yield pg, errors
    context.close()


def _seeded(pg):
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate(BINDER_SEED_JS)
    pg.wait_for_timeout(600)
    names = pg.evaluate(LONG_NAMES_JS)
    assert 'UPSTAGE LEFT MAIN IMAG WALL' in names, names


def _fiber(pg):
    pg.evaluate(FIBER_SEED_JS)
    assert pg.evaluate(FEED_JS) == 4
    assert pg.evaluate(FIBER_EXTRAS_JS) >= 4


def _many(pg):
    assert pg.evaluate(MANY_JS, 16) == 16
    assert pg.evaluate(FEED_JS) == 16


def _walls(pg):
    out = pg.evaluate(WALLS_JS)
    assert out['layers'] == 4 and out['distros'] == 2 and all(out['circuits']), out
    assert all(out['ports']), out


def _nine(pg):
    out = pg.evaluate(NINE_JS)
    assert out['layers'] == 9 and all(out['circuits']) and all(out['ports']), out


SHOWS = {'seeded': _seeded, 'fiber': _fiber, 'many': _many, 'walls': _walls, 'nine': _nine}


def _sweep(pg, sheets=SMALL):
    report = {}
    for sheet in sheets:
        for tb in (True, False):
            report[(sheet, tb)] = _bounds(pg, sheet=sheet, titleBlock=tb)
    return report


@pytest.mark.parametrize('show', sorted(SHOWS))
def test_nothing_runs_out_of_the_drawing_area_at_letter_and_a4(page, show):
    """Every sheet of the show - the overview, each screen's power and data
    maps and their wiring, header and footer, the Fiber page and its
    continuations, the pull sheets, the services, distros, processors and
    backup units, the totals, the Network page - at letter and A4, the title
    block on and off: not one mark past the drawing area's edge."""
    pg, errors = page
    SHOWS[show](pg)
    bad = []
    for (sheet, tb), report in _sweep(pg).items():
        assert report, (sheet, tb, 'no sheets')
        bad += ['%s %s: %s' % (sheet, 'block' if tb else 'no block', line) for line in _offenders(report)]
    assert not bad, '\n' + '\n'.join(bad)
    assert errors == []


@pytest.mark.parametrize('fixture', [SHOW_A, SHOW_B], ids=['show-a', 'show-b'])
def test_the_real_shows_stay_in_the_drawing_area(page, fixture):
    if private_fixture_missing(fixture):
        pytest.skip(private_fixture_missing(fixture))
    pg, errors = page
    pg.evaluate(LOAD_JS, json.load(open(fixture, encoding='utf-8')))
    bad = []
    for (sheet, tb), report in _sweep(pg).items():
        bad += ['%s %s: %s' % (sheet, 'block' if tb else 'no block', line) for line in _offenders(report)]
    assert not bad, '\n' + '\n'.join(bad)
    assert errors == []


# ── a set too long for the overview's CONTENTS ───────────────────────────

# The plan, and every (number, title) row the CONTENTS prints, in order -
# each sheet's from its contents table's SHEET / TITLE headings on (the
# title block, drawn first, names the sheet and its number too) - and the
# sheets that print the POSITIONS table.
CONTENTS_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const listed = [], overview = {}, positions = [];
    plan.forEach((p, i) => {
        if (p.kind !== 'overview' && p.kind !== 'contents') return;
        const r = app.renderBinderPage(opts, i);
        const texts = r.texts;
        if (p.kind === 'overview') {
            overview.contents = texts.some(t => /^CONTENTS( \d+)?$/.test(t));
            overview.bubble = r.bubble ? r.bubble.name : null;
            overview.map = !!(r.mapBitmaps || []).length || !!r.map;
        }
        // (the POSITIONS table by its headings: a CONTENTS row may read
        // POSITIONS too, a sheet's title)
        if (texts.some((t, k) => t === 'POSITION' && texts[k + 1] === 'SCREENS')) positions.push(p.number);
        const from = texts.findIndex((t, k) => t === 'SHEET' && texts[k + 1] === 'TITLE');
        if (from < 0) return;
        for (let k = from; k < texts.length - 1; k++) {
            if (/^\d+\.\d+$/.test(texts[k])) listed.push([texts[k], texts[k + 1]]);
        }
    });
    return {plan: plan.map(p => [p.number, p.kind, p.sheetTitle, p.scale]), listed, overview, positions};
}"""



def _listed_right(listed, plan):
    """The CONTENTS rows are the plan's sheets, in order, by number, each
    title as printed (its first line where it wraps)."""
    return ([n for n, _t in listed] == [p[0] for p in plan]
            and all(p[2].startswith(t.rstrip(chr(0x2026))) for (_n, t), p in zip(listed, plan)))

def test_a_long_set_lists_its_sheets_on_contents_sheets_after_the_overview(page):
    """Sixteen processors: some ninety sheets, a CONTENTS taller than a
    letter sheet (it ran off the overview's foot). The overview keeps its
    positions, totals and drawing (owner, 2026-11-18); the CONTENTS goes
    whole onto sheets of its own right after it, 1.2 on, and the FACTS
    sheet after those - every sheet of the set listed in order by the
    number it prints under, the CONTENTS sheets too, at the overview's own
    size. Every sheet past the overview's series keeps its number."""
    pg, errors = page
    _many(pg)
    for sheet in SMALL + ('tabloid',):
        out = pg.evaluate(CONTENTS_JS, _opts(sheet=sheet))
        plan = out['plan']
        kinds = [k for _n, k, _t, _s in plan]
        assert kinds[0] == 'overview' and kinds[1] == 'contents', (sheet, plan[:4])
        n = kinds.count('contents')
        assert kinds[1:1 + n] == ['contents'] * n, (sheet, kinds[:n + 2])
        assert [p[0] for p in plan[:1 + n]] == ['1.%d' % i for i in range(1, n + 2)], (sheet, plan[:n + 2])
        assert [p[2] for p in plan[1:1 + n]] == ['CONTENTS'] + ['CONTENTS (CONT.)'] * (n - 1), plan[:n + 2]
        # the POSITIONS table: on the overview, always
        assert out['positions'] == ['1.1'], (sheet, out['positions'])
        assert all(p[3] == 1 for p in plan[1:1 + n]), plan[:n + 2]
        assert plan[1 + n][1] == 'facts' and plan[1 + n][0] == '1.%d' % (n + 2), plan[n:n + 3]
        assert plan[2 + n][0] == '2.1', plan[n:n + 4]
        assert _listed_right(out['listed'], plan), (sheet, out['listed'][:5], len(out['listed']), len(plan))
        assert out['overview'] == {'contents': False, 'bubble': 'OVERVIEW', 'map': True}, out['overview']
    # the numbers of every sheet past the overview's series stand as they
    # did with no overview at all
    without = pg.evaluate("(o) => window.app.planBinder(o).map(p => [p.number, p.sheetTitle])",
                          _opts(sheet='letter', cover=False))
    withit = pg.evaluate(CONTENTS_JS, _opts(sheet='letter'))['plan']
    assert [[p[0], p[2]] for p in withit if not p[0].startswith('1.')] == [p for p in without if not p[0].startswith('1.')]
    assert errors == []


def test_a_set_whose_contents_fit_keeps_them_on_the_overview(page):
    """The seeded show's few sheets: the CONTENTS on the overview, as it
    always was, and no CONTENTS sheet - at letter and at tabloid; the FACTS
    sheet right after the overview, 1.2."""
    pg, errors = page
    _seeded(pg)
    for sheet in ('letter', 'tabloid'):
        out = pg.evaluate(CONTENTS_JS, _opts(sheet=sheet))
        assert [k for _n, k, _t, _s in out['plan']].count('contents') == 0, out['plan']
        assert out['plan'][1][:3] == ['1.2', 'facts', 'FACTS'] and out['plan'][2][0] == '2.1', out['plan'][:3]
        assert out['overview']['contents'] is True, out['overview']
        assert _listed_right(out['listed'], out['plan']), out['listed']
    assert errors == []


# ── the FACTS sheet ──────────────────────────────────────────────────────

# The FACTS sheet's tables as the binder builds them (the last of each the
# plan made), the plan, and each screen sheet's text.
FACTS_JS = r"""(opts) => {
    const app = window.app;
    const spied = {};
    const origT = app._bTableLines;
    app._bTableLines = function (book, spec) {
        if (/^\d+ screens?$/.test(spec.title) || spec.title === 'Notes') {
            spied[spec.title === 'Notes' ? 'notes' : 'rows'] = spec.rows.filter(r => r.cells)
                .map(r => ({cells: r.cells.slice(), bold: !!r.bold}));
            spied.cols = spied.cols || spec.cols.map(c => c.title);
        }
        return origT.apply(this, arguments);
    };
    let plan;
    try { plan = app.planBinder(opts); } finally { app._bTableLines = origT; }
    const sheets = {};
    plan.forEach((p, i) => {
        if (!['power', 'data', 'facts'].includes(p.kind)) return;
        sheets[p.number] = {kind: p.kind, title: p.title, texts: app.renderBinderPage(opts, i).texts};
    });
    const screens = app._pullScreens().map(l => ({name: l.name, panels: app._bScreenFacts(l).active,
                                                  watts: app._bScreenFacts(l).watts}));
    return {plan: plan.map(p => [p.number, p.kind, p.title]), rows: spied.rows || [], notes: spied.notes || [],
            cols: spied.cols || [], sheets, screens};
}"""

# (no AMPS 1φ column on a show on 3-phase distros only, as these shows are)
FACTS_COLS = ['screen', 'size', 'panels', 'resolution', 'watts', 'amps 3φ', 'circuits', 'power in', 'ports']
# A service's line under the table (owner, 2026-11-18): "Service: <name>",
# then its size and its whole load against its limit, as its Service sheet
# reads it (owner, 2026-11-19).
SERVICE_NOTE = re.compile(r'[\d,.]+ A · 120/208V 3φ · load X [\d,.]+ · Y [\d,.]+ · Z [\d,.]+ A'
                          r' · 3φ [\d,.]+ A · [\d,.]+ kW( · .+)?')


def _num(s):
    return float(s.replace(',', '')) if s else 0.0


def test_the_facts_sheet_lists_every_screen_with_its_totals(page):
    """One FACTS sheet right after the overview: a row per screen in the
    order the screen sheets run (alphabetical here), its size, panels,
    resolution, watts, amps 1φ and 3φ, circuits, POWER IN (its distro and
    the legs it draws on) and ports, and a TOTAL row that adds them up; the
    NOTES carry the service's load against its limit. No screen's power or
    data sheet carries a FACTS block. A hidden screen prints no row; a
    screen with no power figure prints no watts, is left out of the total
    and is named in the NOTES."""
    pg, errors = page
    _walls(pg)
    opts = _opts(sheet='letter')
    out = pg.evaluate(FACTS_JS, opts)
    facts = [p for p in out['plan'] if p[1] == 'facts']
    assert [p[0] for p in facts] == ['1.2'] and out['plan'][0][1] == 'overview', out['plan'][:3]
    assert out['cols'] == FACTS_COLS, out['cols']
    rows = [r['cells'] for r in out['rows']]
    body, total = rows[:-1], rows[-1]
    names = [r[0] for r in body]
    assert names == sorted(names) and len(names) == 4, names
    assert total[0] == 'Total' and out['rows'][-1]['bold'], total
    tall = next(r for r in body if r[0] == 'STAGE LEFT VERTICAL IMAG TOWER')
    assert tall[1] == '6 × 24' and tall[2] == '144' and tall[3] == '768 × 3072', tall
    assert _num(tall[4]) == 144 * 180, tall
    # (on 3-phase distros: no 1φ figure anywhere, so no AMPS 1φ column)
    assert abs(_num(tall[5]) - 144 * 180 / (208 * 1.73)) < 0.06, tall
    for col in (2, 4, 6, 8):
        assert abs(sum(_num(r[col]) for r in body) - _num(total[col])) < 1, (col, body, total)
    assert all(int(r[6]) > 0 and int(r[8]) > 0 for r in body), body
    # POWER IN: the distro the screen's multis run from, a dot, and its legs
    # (owner, 2026-11-19: "STAGE LEFT POWER DISTRO RACK A · X Y Z")
    for r in body:
        distro = 'UPSTAGE CENTER POWER DISTRO RACK B' if r[0].startswith('UPSTAGE') \
            else 'STAGE LEFT POWER DISTRO RACK A'
        assert re.fullmatch(re.escape(distro) + r' · [XYZ]( [XYZ])*', r[7]), r
    assert total[7] == '', total
    notes = [r['cells'] for r in out['notes']]
    assert [n[0] for n in notes] == ['Service: HOUSE COMPANY SWITCH STAGE RIGHT 400A'], notes
    assert SERVICE_NOTE.fullmatch(notes[0][1]), notes
    # a single-phase distro (no legs to read) prints its name alone
    pg.evaluate("() => { const a = window.app; a.__legs = a._bScreenLegsOn; a._bScreenLegsOn = () => null; }")
    try:
        one = pg.evaluate(FACTS_JS, opts)
    finally:
        pg.evaluate("() => { const a = window.app; a._bScreenLegsOn = a.__legs; delete a.__legs; }")
    tall = next(r['cells'] for r in one['rows'] if r['cells'][0] == 'STAGE LEFT VERTICAL IMAG TOWER')
    assert tall[7] == 'STAGE LEFT POWER DISTRO RACK A', tall
    # no FACTS block on any screen sheet; the FACTS sheet prints the table
    for n, s in out['sheets'].items():
        if s['kind'] == 'facts':
            assert 'FACTS' in s['texts'] and 'TOTAL' not in s['texts'] and 'Total' in s['texts'], s['texts']
            assert not [t for t in s['texts'] if '\u2014' in t or '\u2013' in t], s['texts']
        else:
            assert 'FACTS' not in s['texts'], (n, s['title'])
    # the hidden screen and the screen with no power figure
    pg.evaluate("""() => {
        const app = window.app;
        const L = (n) => app.project.layers.find(l => l.name === n);
        L('DOWNSTAGE RIGHT SIDE FILL').visible = false;
        L('UPSTAGE CENTER WIDE BACKDROP WALL').panelWatts = 0;
        app._circuitTailCache = null;
    }""")
    try:
        out = pg.evaluate(FACTS_JS, opts)
    finally:
        pg.evaluate("""() => {
            const app = window.app;
            const L = (n) => app.project.layers.find(l => l.name === n);
            L('DOWNSTAGE RIGHT SIDE FILL').visible = true;
            L('UPSTAGE CENTER WIDE BACKDROP WALL').panelWatts = 180;
            app._circuitTailCache = null;
        }""")
    rows = [r['cells'] for r in out['rows']]
    names = [r[0] for r in rows[:-1]]
    assert 'DOWNSTAGE RIGHT SIDE FILL' not in names and len(names) == 3, names
    wide = next(r for r in rows if r[0] == 'UPSTAGE CENTER WIDE BACKDROP WALL')
    assert wide[4] == '' and wide[5] == '', wide
    assert abs(sum(_num(r[4]) for r in rows[:-1]) - _num(rows[-1][4])) < 1, rows
    notes = [r['cells'] for r in out['notes']]
    assert ['UPSTAGE CENTER WIDE BACKDROP WALL',
            'No power figure: watts left out of the totals. Type them in Power Settings.'] in notes, notes
    assert errors == []


def test_a_one_screen_export_prints_its_facts_without_the_overview(page):
    """A one-screen export starts with the Overview unticked: its FACTS
    sheet prints all the same, 1.1, the screen's own row and the Total,
    ahead of the screen's sheets; with neither map side, no FACTS sheet."""
    pg, errors = page
    _walls(pg)
    lid = pg.evaluate("() => String(window.app.project.layers.find(l => l.name === "
                      "'STAGE LEFT VERTICAL IMAG TOWER').id)")
    opts = _opts(sheet='letter', cover=False, pull=False, hardware=False, scope={'kind': 'screen', 'layerId': lid})
    out = pg.evaluate(FACTS_JS, opts)
    assert out['plan'][0][:2] == ['1.1', 'facts'] and out['plan'][1][0] == '2.1', out['plan'][:3]
    assert [r['cells'][0] for r in out['rows']] == ['STAGE LEFT VERTICAL IMAG TOWER', 'Total'], out['rows']
    none = pg.evaluate("(o) => window.app.planBinder(o).map(p => p.kind)",
                       dict(opts, sides={'power': False, 'data': False}))
    assert 'facts' not in none, none
    assert errors == []


def test_the_facts_sheet_follows_the_screen_order(page):
    """The export's Screen order: the FACTS rows run in the order the screen
    sheets do, whichever order is picked."""
    pg, errors = page
    _walls(pg)
    opts = _opts(sheet='tabloid')
    for order in ('alpha', 'layers-up'):
        pg.evaluate("(o) => { const b = window.app.project.binder || (window.app.project.binder = {}); "
                    "b.screenOrder = o; }", order)
        out = pg.evaluate(FACTS_JS, opts)
        sheets = []
        for _n, kind, title in out['plan']:
            if kind == 'power':
                name = title.split(' - Power')[0]
                if name not in sheets:
                    sheets.append(name)
        rows = [r['cells'][0] for r in out['rows'][:-1]]
        assert rows == sheets, (order, rows, sheets)
    pg.evaluate("() => { delete window.app.project.binder.screenOrder; }")
    assert errors == []


# ── the owner's letter overview (2026-11-18) ─────────────────────────────

# The overview's POSITIONS table as painted: each row's height (from the
# table's text ops: a row is as tall as its lines) and the band's log.
POSITIONS_JS = r"""(opts) => {
    const app = window.app;
    const r = app.renderBinderPage(opts, 0);
    const texts = r.textInfo || [];
    return {band: r.map && r.map.band, tables: r.map && r.map.tables, posW: r.map && r.map.positionsW,
            texts: r.texts};
}"""


def test_a_long_set_on_letter_moves_the_whole_contents_and_keeps_positions_wide(page):
    """The owner's letter binder (nine positions with long names, about sixty
    sheets): the CONTENTS ran past the sheet's frame, and POSITIONS stood
    its names three lines tall in one narrow column. Now the CONTENTS is
    whole on its own sheet, 1.2 - not one row of it left on the overview -
    the FACTS sheet 1.3, the screens from 2.1; the overview keeps
    POSITIONS, SHOW TOTALS and the map, POSITIONS wider than one of the
    band's columns. On every paper size, title block on and off, nothing
    runs past the drawing area. (The owner's export: no pull or hardware
    sheets. The sweep stands last in the module: six sizes of a sixty-sheet
    set keep the page busy long enough for its server link to lapse.)"""
    pg, errors = page
    _nine(pg)
    out = pg.evaluate(CONTENTS_JS, _opts(sheet='letter', pull=False, hardware=False))
    plan = out['plan']
    assert 45 <= len(plan) <= 65, len(plan)
    assert [p[:3] for p in plan[:3]] == [['1.1', 'overview', 'OVERVIEW'], ['1.2', 'contents', 'CONTENTS'],
                                          ['1.3', 'facts', 'FACTS']], plan[:4]
    assert plan[3][0] == '2.1', plan[:5]
    assert out['overview'] == {'contents': False, 'bubble': 'OVERVIEW', 'map': True}, out['overview']
    assert out['positions'] == ['1.1'], out['positions']
    assert _listed_right(out['listed'], plan), (out['listed'][:5], len(out['listed']), len(plan))
    pos = pg.evaluate(POSITIONS_JS, _opts(sheet='letter', pull=False, hardware=False))
    da_w = 2200 - 2 * 50 - 480 - 2 * 10
    wide = (da_w - 30) / 2
    assert pos['posW'] > wide + 1, pos
    # every name on one line: no wrapped half of "Screen A - HL IMAG - SWITCH"
    assert 'Screen A - HL IMAG - SWITCH' in pos['texts'], [t for t in pos['texts'] if 'Screen A' in t]
    bad = []
    for sheet in ('letter', 'tabloid', 'archc', 'archd', 'a4', 'a3'):
        for tb in (True, False):
            report = _bounds(pg, sheet=sheet, titleBlock=tb, pull=False, hardware=False)
            bad += ['%s %s: %s' % (sheet, 'block' if tb else 'no block', line) for line in _offenders(report)]
            kinds = [s['kind'] for s in report]
            assert kinds.count('overview') == 1 and kinds.count('facts') >= 1, (sheet, tb, kinds[:5])
    assert not bad, '\n' + '\n'.join(bad)
    assert errors == []


# ── the marks that stood past the edge, one at a time ────────────────────

# A context that records what is written and filled on it, for the
# binder's drawing helpers called straight: each text's left, right, top
# and baseline as measured in its own font, each filled rect.
SPY_JS = r"""
    const spy = () => {
        const ctx = document.createElement('canvas').getContext('2d');
        const texts = [], rects = [];
        const fillText = ctx.fillText.bind(ctx), fillRect = ctx.fillRect.bind(ctx);
        ctx.fillText = (t, x, y) => {
            const w = ctx.measureText(String(t)).width;
            const size = parseFloat(/(\d+(?:\.\d+)?)px/.exec(ctx.font)[1]);
            const left = ctx.textAlign === 'center' ? x - w / 2 : ctx.textAlign === 'right' ? x - w : x;
            texts.push({t: String(t), left, right: left + w, top: y - 0.72 * size, y, size});
            return fillText(t, x, y);
        };
        ctx.fillRect = (x, y, w, h) => { rects.push({x, y, w, h}); return fillRect(x, y, w, h); };
        const book = {ctx, measureCtx: document.createElement('canvas').getContext('2d'),
                      log: {texts: [], textInfo: []}, page: {painting: true}};
        return {book, texts, rects};
    };
"""

# The column ruler over a 10-column wall whose top stands `room` under
# its map's area: the column numbers it writes.
RULER_JS = """(room) => {""" + SPY_JS + """
    const {book, texts} = spy();
    const geo = {wall: {x: 100, y: room, w: 600, h: 300}, mapArea: {x: 0, y: 0, w: 800, h: 400 + room},
                 mirrored: false};
    const cols = new Map([...Array(10).keys()].map(i => [i, {x1: 100 + 60 * i, x2: 160 + 60 * i}]));
    const rows = new Map([[0, {y1: room, y2: room + 300}]]);
    window.app._bRulersDraw(book, geo, cols, rows);
    return texts.filter(o => o.y < room);
}"""


def test_the_column_ruler_prints_only_where_its_numbers_fit_under_the_maps_top(page):
    """A power map that leaves the column ruler between 34 and 46 over
    the wall (a letter sheet of a real show): the numbers, 30 over it with
    their own height on that, stood up to a dozen over the map's area -
    over the drawing area's top, against the border. They print where
    they fit, whole, and stand down where they do not, as the ruler
    already did over a power map's own band."""
    pg, _errors = page
    for room in (40, 45):
        assert pg.evaluate(RULER_JS, room) == [], room
    for room in (46, 60, 120):
        nums = pg.evaluate(RULER_JS, room)
        assert [n['t'] for n in nums] == ['1', '5', '10'], (room, nums)
        assert all(n['top'] >= -0.01 for n in nums), (room, nums)


# The view bubble with a long name in a room `room` wide: its name's
# right edge and its rule's.
BUBBLE_JS = """([name, room]) => {""" + SPY_JS + """
    const {book, texts, rects} = spy();
    window.app._bViewBubble(book, 12, name, 0, 0, null, room);
    const label = texts.find(o => o.t !== '12');
    return {label: label.t, right: label.right, size: label.size,
            rule: Math.max(...rects.map(r => r.x + r.w))};
}"""


def test_the_view_bubble_name_stands_in_its_room(page):
    """A Header/Footer sheet on letter whose type the fill grows: the
    bubble's name - the screen's long name, HEADER/FOOTER, the view - ran
    its letters and its rule into the title block. Given its room, the
    name shrinks to it (then cuts) and the rule under it stops there; a
    name that fits is drawn at its size, the rule 40 past it."""
    pg, _errors = page
    long = 'UPSTAGE CENTER WIDE BACKDROP WALL · HEADER/FOOTER · FRONT VIEW'
    out = pg.evaluate(BUBBLE_JS, [long, 640])
    assert out['right'] <= 640.5 and out['rule'] <= 640.5, out
    assert out['size'] < 26, out
    short = pg.evaluate(BUBBLE_JS, ['WALL · DATA · FRONT VIEW', 1600])
    assert short['size'] == 26 and short['label'] == 'WALL · DATA · FRONT VIEW', short
    assert abs(short['rule'] - (short['right'] + 40)) < 1.5, short
