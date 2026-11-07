"""Data map cable tags read the length alone; the binder names the connector.

The owner's ruling of 2026-11-02 ("option 3 is the best just list 25'"): on a
wall of narrow columns (11 x 4 cabinets of 192 x 384, flow bl-v, every port
and return on a 25' etherCON) the tags read "25' etherCON", wider than a
column, so they zig-zagged over and under the discs and ran together on the
top row. Now:

  - every data map port tag and return tag reads the length only ("25'"),
    on every data screen, narrow or wide (app-processors.js dataMapTagText);
  - the working map prints no connector note;
  - the binder prints one line under the screen's name on its data sheet,
    "Port cables: etherCON", or each connector with its ports where a
    screen mixes them, "Port cables: etherCON 1-10 · Cat6 11"
    (app-binder.js _bDataCableNote);
  - the power map is unchanged: its tags still carry the connector.

The show is seeded through the real API (an SX40 with its four boxes, the
ports filled in order, redundancy on), so the tag text comes from the real
cable records, not a stub. The placement is read off canvas.js's label
registry (startLabelProbe / endLabelProbe, bitmap pixels).

Run locally (each session takes its own free port, so it runs beside any
other):
    python -m pytest tests/test_data_tags_length.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder import _SHOW_JSON  # noqa: E402

HAIR = 1.0
ZOOM = 0.75
PAN = 40

# Two walls side by side, each on its own SX40 with redundancy on and every
# box socket on a 25' etherCON: UL the owner's narrow-column wall, CTR a
# wide one. `cfg.mixed` puts UL's last port on a Cat6 instead. UL also
# carries two power circuits on a fed multi with 25' cables, for the power
# map's tags.
SEED_JS = r"""async (cfg) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    proj.raster_width = 4096; proj.raster_height = 2160;
    proj.show_raster_width = 4096; proj.show_raster_height = 2160;
    if (Array.isArray(proj.canvases)) for (const c of proj.canvases) {
        c.raster_width = 4096; c.raster_height = 2160;
        c.show_raster_width = 4096; c.show_raster_height = 2160;
    }
    await j('PUT', '/api/project', proj);
    const app = window.app;
    const out = {};
    const walls = [
        {name: 'Upstage Left', prefix: 'UL', columns: 11, rows: 4, cw: 192, ch: 384, x: 0, y: 0,
         power: true},
        {name: 'Center', prefix: 'CTR', columns: 4, rows: 4, cw: 352, ch: 352, x: 2362, y: 0},
    ];
    for (const w of walls) {
        const l = await j('POST', '/api/layer/add', {name: w.name, columns: w.columns, rows: w.rows,
            cabinet_width: w.cw, cabinet_height: w.ch, offset_x: w.x, offset_y: w.y});
        const props = {processorType: 'brompton', bitDepth: 8, frameRate: 60, flowPattern: 'bl-v',
            showDataCableTags: true, dataFlowLabelSize: cfg.labelSize};
        if (w.power) Object.assign(props, {panelWatts: 100, powerVoltage: 208, powerAmperage: 20,
            powerBreakoutType: 'soca-true1', powerSocaDistro: {1: 'd1'}, powerSocaNames: {1: 'S1'},
            powerCircuitCables: {1: {ft: 25}, 2: {ft: 25}}, showPowerCableTags: true,
            powerLabelSize: cfg.labelSize});
        await j('PUT', `/api/layer/${l.id}`, props);
        let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: w.prefix + ' SX40'});
        const proc = st.processors[st.processors.length - 1];
        const card = proc.slots[0].card;
        const letters = ['A', 'B', 'C', 'D'];
        await j('PUT', `/api/processors/${proc.id}`, {redundancy: true});
        for (let i = 0; i < card.cvts.length; i++) {
            const r1 = await j('PUT', `/api/processors/${proc.id}/cvts/${card.cvts[i].id}`,
                               {name: `${w.prefix} ${letters[i]}`});
            const box = (r1.resolved || []).find(p => p.id === proc.id).slots[0].card.cvts[i];
            const pc = {};
            for (const p of box.ports || []) pc[String(p.number)] = {ft: 25, connector: 'ethercon'};
            const r2 = await j('PUT', `/api/processors/${proc.id}/cvts/${card.cvts[i].id}`, {portCables: pc});
            if (r2.error) out['err_' + w.prefix + i] = r2.error;
        }
        app.project = await j('GET', '/api/project');
        await app.refreshProcessors();
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(l.id), cardId: card.id}, null, 'Fill Ports In Order');
        out[w.prefix] = l.id;
    }
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    const ul = app.project.layers.find(l => l.name === 'Upstage Left');
    const scr = app._assignment.screens.find(s => String(s.layerId) === String(ul.id));
    out.ports = scr.ports.length;
    if (cfg.mixed) {
        // UL's last port onto a Cat6: the socket its pin lands on and the
        // socket its backup comes back on
        const last = scr.ports.reduce((a, b) => (b.number > a.number ? b : a));
        const ends = [{cardId: last.cardId, port: last.port}];
        const bb = app._pullBackedBy(last.cardId, last.port);
        if (bb) ends.push(bb);
        for (const end of ends) {
            const owner = app._dataPortOwner(end.cardId, end.port);
            const pc = Object.assign({}, owner.rec.portCables || {});
            pc[String(end.port)] = {ft: 25, connector: 'cat'};
            const url = owner.kind === 'cvt' ? `/api/processors/${owner.procId}/cvts/${owner.id}`
                : `/api/processors/${owner.procId}/cards/${owner.id}`;
            const r = await j('PUT', url, {portCables: pc});
            if (r.error) out.mixedErr = r.error;
            app.project = await j('GET', '/api/project');
            await app.refreshProcessors();
        }
        out.lastPort = last.number;
        out.backed = !!bb;
        app.project = await j('GET', '/api/project');
        await app.refreshProcessors();
        await app.refreshPortAssignment();
    }
    app.setSelectedLayersByIds([]);
    app.renderLayers();
    app.updateUI();
    return out;
}"""

# One frame at ZOOM under the label probe, in `mode`, with every layer but
# `name` hidden for the frame; also the wall's rect and cabinet size in the
# bitmap's pixels, and every fillText the frame painted.
PROBE_JS = r"""(cfg) => {
    const r = window.canvasRenderer, app = window.app;
    const prev = { mode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY };
    const vis = app.project.layers.map(l => [l, l.visible]);
    const wall = app.project.layers.find(l => l.name === cfg.name);
    app.project.layers.forEach(l => { l.visible = l === wall; });
    r.viewMode = cfg.mode; r.zoom = cfg.zoom; r.panX = cfg.pan; r.panY = cfg.pan;
    const ctx = r.ctx, oT = ctx.fillText, texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
    r.startLabelProbe();
    let boxes;
    try { r.render(); } finally {
        boxes = r.endLabelProbe();
        ctx.fillText = oT;
        vis.forEach(([l, v]) => { l.visible = v; });
        Object.assign(r, { viewMode: prev.mode, zoom: prev.zoom, panX: prev.panX, panY: prev.panY });
    }
    const dpr = r.canvas.width / r.canvas.getBoundingClientRect().width;
    const s = cfg.zoom * dpr;
    const port = (n) => app.dataPortCableForScreen(wall, n);
    const scr = app._assignment.screens.find(x => String(x.layerId) === String(wall.id));
    return {
        boxes, texts,
        wall: { x: (cfg.pan + wall.offset_x * cfg.zoom) * dpr, y: (cfg.pan + wall.offset_y * cfg.zoom) * dpr,
                cw: wall.cabinet_width * s, ch: wall.cabinet_height * s,
                cols: wall.columns, rows: wall.rows },
        cables: scr.ports.map(p => (port(p.number) || {}).text || null),
        power: [1, 2].map(n => (app.powerCircuitCable(wall, n) || {}).text || null),
    };
}"""

BINDER_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    for (let i = 0; i < plan.length; i++) {
        const p = plan[i];
        if (p.kind !== 'data' && p.kind !== 'power') continue;
        const page = app.renderBinderPage(opts, i);
        out.push({ title: p.title, kind: p.kind, bubble: page.bubble, texts: page.texts,
                   mapTexts: page.mapTexts });
    }
    return out;
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 2600, 'height': 1400},
                                     device_scale_factor=1)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    seeded = pg.evaluate(SEED_JS, {'mixed': False, 'labelSize': 40})
    assert not [k for k in seeded if k.startswith('err') or k == 'mixedErr'], seeded
    assert seeded['ports'] >= 6, seeded
    pg.wait_for_timeout(500)
    yield pg, errors, seeded
    context.close()


def _probe(pg, name, mode='data-flow'):
    return pg.evaluate(PROBE_JS, {'name': name, 'mode': mode, 'zoom': ZOOM, 'pan': PAN})


def _kind(boxes, kind):
    return [b for b in boxes if b['kind'] == kind]


def _cx(b):
    return b['x'] + b['w'] / 2


def _cy(b):
    return b['y'] + b['h'] / 2


def _gap(a, b):
    return max(max(a['x'], b['x']) - min(a['x'] + a['w'], b['x'] + b['w']),
               max(a['y'], b['y']) - min(a['y'] + a['h'], b['y'] + b['h']))


def _over(a, b):
    dx = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
    dy = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
    return dx > HAIR and dy > HAIR


def _name(b):
    return '%s %r at (%.1f, %.1f) %.1f x %.1f' % (b['kind'], b['text'], b['x'], b['y'], b['w'], b['h'])


def test_the_narrow_wall_tags_read_the_length_alone(page):
    """Every port and return tag on the narrow wall reads "25'", one per
    marker, while the cable records still say "25' etherCON" (the pull
    sheet and the binder tables read those)."""
    pg, errors, seeded = page
    out = _probe(pg, 'Upstage Left')
    tags = _kind(out['boxes'], 'tag')
    assert set(out['cables']) == {"25' etherCON"}, out['cables']
    assert [t['text'] for t in tags] == ["25'"] * len(tags), [t['text'] for t in tags]
    assert len(tags) == 2 * seeded['ports'], (len(tags), seeded)
    assert not [t for t in out['texts'] if 'etherCON' in t or 'Port cables' in t], out['texts']
    assert errors == []


def test_the_wide_wall_tags_read_the_length_alone(page):
    """The same on a wide wall, where the whole tag would have fitted: the
    rule is every data screen, always."""
    pg, errors, _ = page
    out = _probe(pg, 'Center')
    tags = _kind(out['boxes'], 'tag')
    assert tags and [t['text'] for t in tags] == ["25'"] * len(tags), [t['text'] for t in tags]
    assert not [t for t in out['texts'] if 'etherCON' in t or 'Port cables' in t], out['texts']
    assert errors == []


def test_the_narrow_wall_tags_sit_in_one_row_inside_their_columns(page):
    """No zig-zag, no strip: the tags under the bottom row's discs share one
    y, the tags of each other row of markers share theirs, every tag stays
    inside the column of the disc it hangs off, and no two tags touch."""
    pg, errors, _ = page
    out = _probe(pg, 'Upstage Left')
    w = out['wall']
    tags, discs = _kind(out['boxes'], 'tag'), _kind(out['boxes'], 'disc')
    bad = []

    def owner(t):
        return min(discs, key=lambda d: _gap(t, d))

    rows = {}
    for t in tags:
        d = owner(t)
        rows.setdefault((round(_cy(d)), t['y'] > _cy(d)), []).append(t)
        col = int((_cx(d) - w['x']) // w['cw'])
        left, right = w['x'] + col * w['cw'], w['x'] + (col + 1) * w['cw']
        if t['x'] < left - HAIR or t['x'] + t['w'] > right + HAIR:
            bad.append('%s leaves column %d (%.1f-%.1f) of disc %s' % (_name(t), col + 1, left, right, d['text']))
    bottom_edge = w['y'] + w['rows'] * w['ch']
    bottom = [t for t in tags if _cy(owner(t)) > bottom_edge - w['ch']]
    assert bottom, [_name(t) for t in tags]
    if len({round(t['y'], 1) for t in bottom}) != 1:
        bad.append('bottom-row tags on more than one y: %s' % sorted({round(t['y'], 1) for t in bottom}))
    for (dy, under), row in rows.items():
        if len({round(t['y'], 1) for t in row}) != 1:
            bad.append('the row of discs at y %d zig-zags: %s' % (dy, [_name(t) for t in row]))
    for i, a in enumerate(tags):
        for b in tags[i + 1:]:
            if _over(a, b):
                bad.append('%s overlaps %s' % (_name(a), _name(b)))
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_the_power_tags_keep_the_connector(page):
    """The power map is not touched ("Data only"): its circuit tags still
    read the whole cable, "25' True1", as powerCircuitCable says it."""
    pg, errors, _ = page
    out = _probe(pg, 'Upstage Left', mode='power')
    tags = [t['text'] for t in _kind(out['boxes'], 'tag')]
    want = [t for t in out['power'] if t]
    assert want and all(' ' in t for t in want), out['power']
    assert sorted(tags) == sorted(want), (tags, want)
    assert errors == []


def test_the_binder_names_the_connector_once(page):
    """The narrow wall's data sheet prints "Port cables: etherCON" under the
    screen's name (the view bubble); its map's tags read "25'"; the power
    sheet prints no such line."""
    pg, errors, _ = page
    opts = json.loads(_SHOW_JSON)
    opts['sides'] = {'power': True, 'data': True}
    sheets = pg.evaluate(BINDER_JS, opts)
    data = [s for s in sheets if s['kind'] == 'data' and 'Upstage Left' in s['title']]
    assert len(data) == 1, [s['title'] for s in sheets]
    s = data[0]
    assert s['bubble']['note'] == 'Port cables: etherCON', s['bubble']
    assert s['texts'].count('Port cables: etherCON') == 1, s['texts']
    assert "25'" in s['mapTexts'] and not [t for t in s['mapTexts'] if 'etherCON' in t], s['mapTexts']
    for p in sheets:
        if p['kind'] == 'power':
            assert not p['bubble'].get('note'), p['bubble']
            assert not [t for t in p['texts'] if t.startswith('Port cables')], p['title']
    assert errors == []


def test_the_binder_note_lists_mixed_connectors_by_port(page):
    """UL's last port on a Cat6, the rest on etherCON: the note names each
    with its ports, in port order - "Port cables: etherCON 1-N · Cat6 N+1"
    - and the map still shows lengths only. Put back afterwards."""
    pg, errors, _ = page
    try:
        seeded = pg.evaluate(SEED_JS, {'mixed': True, 'labelSize': 40})
        assert 'mixedErr' not in seeded, seeded
        n = seeded['lastPort']
        opts = json.loads(_SHOW_JSON)
        opts['sides'] = {'power': False, 'data': True}
        sheets = pg.evaluate(BINDER_JS, opts)
        s = [p for p in sheets if p['kind'] == 'data' and 'Upstage Left' in p['title']][0]
        assert s['bubble']['note'] == 'Port cables: etherCON 1-%d · Cat6 %d' % (n - 1, n), s['bubble']
        ctr = [p for p in sheets if p['kind'] == 'data' and 'Center' in p['title']][0]
        assert ctr['bubble']['note'] == 'Port cables: etherCON', ctr['bubble']
        out = _probe(pg, 'Upstage Left')
        assert set(t['text'] for t in _kind(out['boxes'], 'tag')) == {"25'"}, out['boxes']
    finally:
        pg.evaluate(SEED_JS, {'mixed': False, 'labelSize': 40})
    assert errors == []


def test_no_typed_cable_no_note(page):
    """A screen with no typed cable on its ports prints no line, and the
    note helper says so."""
    pg, errors, _ = page
    got = pg.evaluate("""() => {
        const app = window.app;
        const ul = app.project.layers.find(l => l.name === 'Upstage Left');
        const a = app.dataPortCableForScreen, b = app.dataPortBackupCableForScreen;
        app.dataPortCableForScreen = () => null;
        app.dataPortBackupCableForScreen = () => ({ kind: 'snake', text: "SNAKE A +25'", ext: 25 });
        try { return [app._bDataCableNote(ul), app.dataMapTagText({ kind: 'snake', text: "SNAKE A +25'" })]; }
        finally { app.dataPortCableForScreen = a; app.dataPortBackupCableForScreen = b;
                  if (a === Object.getPrototypeOf(app).dataPortCableForScreen) delete app.dataPortCableForScreen;
                  if (b === Object.getPrototypeOf(app).dataPortBackupCableForScreen) delete app.dataPortBackupCableForScreen; }
    }""")
    assert got == [None, "SNAKE A +25'"], got
    assert errors == []
