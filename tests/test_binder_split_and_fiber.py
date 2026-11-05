"""The binder where a group prints screen by screen, and which fiber a box is on.

Three faults from a real show (owner, 2026-11-05):

  * "on binders where a groups gets split any info that is cut off needs to
    show through on the page". A circuit shared across a group's seam stands
    on the seam: its disc, its 2fer pill and its cable tag are half on one
    member's wall and half on the next. A member's sheet cut everything of
    the other member off its bitmap, so each sheet printed half a label, and
    the wiring sheet, whose bitmap stops at the wall, half a disc inside a
    whole ring. Each label now prints whole on every sheet it reaches, the
    wall framed so it stays on the sheet, and the brackets, the rulers, the
    wall's outline and the runs all stand clear of it.

  * "have the circles around the circuits in the wrong places". A wiring
    sheet aims its runs at the discs the wall really drew, and read each
    disc's place from the coordinates it was drawn at. A run across a group's
    members is drawn in the wall's frame, a screen's own in that screen's,
    and where a member's Show Look offset is not nil the two differ by it:
    the rings and the runs landed that far from their discs, off the wall and
    off the sheet. A disc's place is now read through the transform it was
    painted under.

  * "we need to mention which fiber is going on the wiring page. just listing
    the colors and numbers makes no sense on a show with multiple fiber
    runs". A box on a Data Wiring sheet listed its strands and no cable. Each
    input now names its cable as the data sheet's band does, TAC A (TAC 12
    SM). The Fiber page's strand maps, the processor pages' strand maps and
    their Fiber connections tables always named theirs, and are held to it
    here.

Run locally:
    python -m pytest tests/test_binder_split_and_fiber.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Four walls on one raster big enough for all of them:
#   WALL   two 5 x 3 members side by side, routed as one, their Show Look
#          offsets not their processor offsets. Two columns to a 2fer, so
#          the third circuit stands on the seam, its cable tag with it, and
#          the third port crosses it, on a TAC.
#   WIDE   two 45 x 4 members, so wide their Power sheets take the wrap layout.
#   STACK  two 3 x 5 members one above the other, the seam across the wall.
#   LONE   a screen of its own on a second TAC, of the other mode.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder; delete proj.fiberCables;
    delete proj.snakes; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    proj.raster_width = 9000; proj.raster_height = 6000;
    proj.show_raster_width = 9000; proj.show_raster_height = 6000;
    (proj.canvases || []).forEach(c => { c.raster_width = 9000; c.raster_height = 6000;
                                         c.show_raster_width = 9000; c.show_raster_height = 6000; });
    await j('PUT', '/api/project', proj);
    const wall = {columns: 5, rows: 3, cabinet_width: 320, cabinet_height: 320,
                  powerVoltage: 208, powerAmperage: 20, panelWatts: 500,
                  powerFlowPattern: 'tl-v', powerOrganized: true, processorType: 'novastar-armor'};
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({...wall, name: 'WALL-L', offset_x: 800});
    await add({...wall, name: 'WALL-R', offset_x: 3200});
    await add({...wall, name: 'LONE', columns: 4, offset_x: 5000});
    const wide = {...wall, columns: 45, rows: 4, cabinet_width: 60, cabinet_height: 120, panelWatts: 400};
    await add({...wide, name: 'WIDE-L', offset_y: 2000});
    await add({...wide, name: 'WIDE-R', offset_x: 2700, offset_y: 2000});
    const stack = {...wall, columns: 3, rows: 5, cabinet_width: 320, cabinet_height: 320,
                   powerFlowPattern: 'tl-h'};
    await add({...stack, name: 'STACK-T', offset_y: 3000});
    await add({...stack, name: 'STACK-B', offset_y: 4600});
    let p = await j('GET', '/api/project');
    const named = (n) => p.layers.find(l => l.name === n);
    for (const l of p.layers) {
        l.powerSplitters = {enabled: true, maxWays: 2, manual: {merge: [], space: null, split: []}};
        l.showPowerCableTags = true; l.showPowerNferTags = true; l.showDataCableTags = true;
        l.powerLabelSize = l.name.startsWith('WIDE') ? 30 : 90;
        l.powerLabelTemplate = 'S1-#';
        l.dataFlowLabelSize = l.name.startsWith('WALL') ? 150 : 50;
        l.flowPattern = 'tl-v';
        l.showOffsetX = l.offset_x; l.showOffsetY = l.offset_y;
    }
    named('WALL-L').showOffsetX = 0;
    named('WALL-R').showOffsetX = 1600;
    // the wall's multi on a distro, so a circuit's own cable prints
    p.distros = [{id: 'd1', name: 'DIST', input: 'cam400', outputs: ['soca208'], phase: 3,
                  ratingA: 400, system: '120/208', voltage: 208, feeder: {ft: 100}, phasing: null,
                  outputRows: [{id: 'r1', connector: 'soca', connectorA: null, count: 4, breakerA: 20,
                                coupling: 'll', pairedWith: null}]}];
    named('WALL-L').powerSocaDistro = {'1': 'd1'};
    named('WALL-L').powerSocaLengths = {'1': '50'};
    named('WALL-L').powerSocaNumber = {'1': 1};
    named('WALL-L').powerCircuitCables = {'3': {connector: null, ft: 10}};
    const screens = {power: 'screens', 'data-flow': 'screens'};
    p.groups = ['WALL', 'WIDE', 'STACK'].map((name, i) => {
        const [a, b] = name === 'STACK' ? ['STACK-T', 'STACK-B'] : [`${name}-L`, `${name}-R`];
        named(a).group_id = `g${i}`; named(b).group_id = `g${i}`;
        return {id: `g${i}`, name, layer_ids: [named(a).id, named(b).id], powerPerMember: false,
                nameDisplayByView: {...screens}};
    });
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    for (const deviceId of ['novastar-cvt10', 'novastar-cvt10-m', 'novastar-cvt4k-s']) {
        st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, {deviceId, pair: false});
    }
    const [s, m, two] = st.processors[0].slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 1000, connector: 'ST',
                                               link: {boxId: s, key: 'p1'}});
    const tacA = st.fiberCables[st.fiberCables.length - 1].id;
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 24, ft: 600, connector: 'ST',
                                               link: {boxId: m, key: 'p1'}});
    // a box with both its inputs on the first TAC: the cable is said in
    // full once, then by its name
    await j('PUT', `/api/processors/${pid}/cvts/${two}/fiber-links/p1`, {cable: tacA});
    await j('PUT', `/api/processors/${pid}/cvts/${two}/fiber-links/p2`, {cable: tacA});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('split_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    const lay = (n) => app.project.layers.find(x => x.name === n);
    const card = app._processorsResolved.find(q => q.id === pid).slots[0].card;
    const first = (id) => card.cvts.find(x => x.id === id).ports[0].number;
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(lay('WALL-L').id), cardId: cid, firstPort: first(s), lastPort: first(s) + 4});
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(lay('LONE').id), cardId: cid, firstPort: first(m), lastPort: first(m) + 3});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Split Seed');
    const across = (l) => app.screenCircuits(lay(l)).filter(c =>
        new Set((c.layers || []).map(x => x && x.id)).size > 1).length;
    return {two, walls: ['WALL-L', 'WALL-R', 'WIDE-L', 'WIDE-R', 'STACK-T', 'STACK-B'].map(across),
            shifted: [lay('WALL-L'), lay('WALL-R')].map(l => l.showOffsetX - l.offset_x),
            cables: app.project.fiberCables.map(c => c.name)};
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
        'fiber': False, 'wiring': True, 'titleBlock': True}

# One sheet, with the map's own label registry running: each label of the map
# on the page, and what the sheet really printed in the part of it past the
# screen's wall. `share` is the part of a grid over that part that is not
# paper: nil where the label was cut off.
SHEET_JS = """([opts, title]) => {
    const app = window.app, r = window.canvasRenderer;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    r.startLabelProbe();
    let res, boxes;
    try { res = app.renderBinderPage(opts, idx); } finally { boxes = r.endLabelProbe() || []; }
    const half = res.wiring ? res.wiring.halves[0] : null;
    const map = half ? half.map : res.map;
    const area = map.area;
    const S = app._binderMapCanvas.width / area.w;
    const c = res.canvas, ctx = c.getContext('2d');
    const P = c.width / res.record.width;
    const rgb = (x, y) => Array.from(ctx.getImageData(Math.round(x * P), Math.round(y * P), 1, 1).data).slice(0, 3);
    const paper = (x, y) => Math.min(...rgb(x, y)) > 235;
    // (`round`: only the part of the grid on the label's disc)
    const share = (x1, y1, x2, y2, round) => {
        let on = 0, n = 0;
        for (let i = 0; i <= 12; i++) for (let k = 0; k <= 8; k++) {
            const x = x1 + (x2 - x1) * i / 12, y = y1 + (y2 - y1) * k / 8;
            if (round && Math.hypot(x - round.x, y - round.y) > round.r * 0.96) continue;
            n++;
            if (!paper(x, y)) on++;
        }
        return n ? on / n : 1;
    };
    const W = { x: map.x, y: map.y, w: map.w, h: map.h };
    const labels = boxes.filter(b => ['disc', 'tag', 'gang', 'jump'].includes(b.kind))
        .map(b => ({ kind: b.kind, text: b.text, x: area.x + b.x / S, y: area.y + b.y / S, w: b.w / S, h: b.h / S }));
    const astride = labels.filter(b => {
        const meets = Math.min(b.x + b.w, W.x + W.w) - Math.max(b.x, W.x) > 1
            && Math.min(b.y + b.h, W.y + W.h) - Math.max(b.y, W.y) > 1;
        const inside = b.x >= W.x - 1 && b.y >= W.y - 1 && b.x + b.w <= W.x + W.w + 1 && b.y + b.h <= W.y + W.h + 1;
        return meets && !inside;
    }).map(b => {
        // the label past the wall, side by side: left, right, over, under
        const parts = [];
        if (b.x < W.x - 1) parts.push([b.x, b.y, W.x - 1, b.y + b.h]);
        if (b.x + b.w > W.x + W.w + 1) parts.push([W.x + W.w + 1, b.y, b.x + b.w, b.y + b.h]);
        if (b.y < W.y - 1) parts.push([b.x, b.y, b.x + b.w, W.y - 1]);
        if (b.y + b.h > W.y + W.h + 1) parts.push([b.x, W.y + W.h + 1, b.x + b.w, b.y + b.h]);
        const round = b.kind === 'disc' ? { x: b.x + b.w / 2, y: b.y + b.h / 2, r: b.w / 2 } : null;
        const seen = parts.map(([x1, y1, x2, y2]) => share(x1 + 1, y1 + 1, x2 - 1, y2 - 1, round));
        return { ...b, shares: seen };
    });
    return { title, layout: plan[idx].layout, wall: W, area, labels, astride,
             brackets: res.brackets || [], texts: res.texts, discs: half ? half.discs : null,
             blocks: half ? half.blocks : null, runs: half ? half.runs : null,
             strip: { left: share(W.x - 22, W.y + W.h * 0.62, W.x - 6, W.y + W.h * 0.92),
                      right: share(W.x + W.w + 6, W.y + W.h * 0.62, W.x + W.w + 22, W.y + W.h * 0.92) },
             seam: astride.map(b => {
                 // on the wall's edge, through the label: never the black
                 // outline, below the lettering of a disc
                 const y = b.y + b.h * 0.86;
                 const x = b.x < W.x ? W.x : W.x + W.w;
                 return { kind: b.kind, text: b.text, at: rgb(x, y), ok: b.kind !== 'disc' || !(b.y < W.y - 1) };
             }),
             sheet: { w: res.record.width, h: res.record.height } };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    # the fixture's premise: every group crosses, every side of it, and the
    # members stand off their processor positions
    assert sum(ids['walls'][:2]) >= 1 and sum(ids['walls'][2:4]) >= 1 and sum(ids['walls'][4:]) >= 1, ids
    assert all(ids['shifted']), ids
    assert ids['cables'] == ['TAC A', 'TAC B'], ids
    yield pg, ids, errors
    context.close()


def _sheet(pg, title, **over):
    out = pg.evaluate(SHEET_JS, [{**OPTS, **over}, title])
    assert 'missing' not in out, out
    return out


def _names(pg, power=None, data=None):
    """Each group's Names switch for the Power and Data tabs."""
    pg.evaluate("""([power, data]) => {
        for (const g of window.app.project.groups) {
            if (power) g.nameDisplayByView.power = power;
            if (data) g.nameDisplayByView['data-flow'] = data;
        }
    }""", [power, data])


SIDES = [(f'{name} - {tab}', view) for name in ('WALL-L', 'WALL-R')
         for tab in ('Power - Front View', 'Power Wiring', 'Data - Front View', 'Data Wiring')
         for view in ('front',)]
SIDES += [('WIDE-L - Power - Front View', 'front'), ('WIDE-R - Power - Front View', 'front'),
          ('WIDE-L - Power Wiring', 'front'), ('WIDE-R - Power Wiring', 'front'),
          ('STACK-T - Power - Front View', 'front'), ('STACK-B - Power - Front View', 'front'),
          ('STACK-T - Power Wiring', 'front'), ('STACK-B - Power Wiring', 'front'),
          ('WALL-L - Power - Rear View', 'rear'), ('WALL-R - Power Wiring', 'rear')]


# ── 1. what stands on the seam prints whole on both sides of it ──────────

@pytest.mark.parametrize('title,view', SIDES)
def test_a_label_on_the_seam_prints_whole(page, title, view):
    """Every disc, 2fer pill and cable tag that reaches the screen's wall
    prints past its edge too, on Power and Data, map and wiring sheets, on
    both sides of the seam and in the wrap layout."""
    pg, _ids, errors = page
    out = _sheet(pg, title, view=view)
    assert out['astride'], (title, 'the fixture has nothing on the seam here', out['labels'][:6])
    for b in out['astride']:
        for part in b['shares']:
            assert part >= 0.55, (title, 'label cut off at the edge of the screen', b)
    assert not errors, errors


def test_every_kind_of_label_is_on_the_seam(page):
    """The shared circuit's disc, its 2fer pill and its cable tag, on both
    members: what the test above reads is the owner's case."""
    pg, _ids, _errors = page
    for name in ('WALL-L', 'WALL-R'):
        out = _sheet(pg, f'{name} - Power - Front View')
        kinds = {b['kind'] for b in out['astride']}
        assert {'disc', 'gang', 'tag'} <= kinds, (name, out['astride'])


def test_the_wide_walls_are_on_the_wrap_layout(page):
    pg, _ids, _errors = page
    for name in ('WIDE-L', 'WIDE-R'):
        assert _sheet(pg, f'{name} - Power - Front View')['layout'] == 'wrap'


@pytest.mark.parametrize('title', [t for t, v in SIDES if 'Wiring' not in t and v == 'front'])
def test_only_the_labels_come_back(page, title):
    """Nothing else of the other member comes back with them: the paper
    beside the wall, clear of the labels, stays paper."""
    pg, _ids, _errors = page
    out = _sheet(pg, title)
    assert out['strip']['left'] < 0.02 and out['strip']['right'] < 0.02, (title, out['strip'])


@pytest.mark.parametrize('title', [t for t, v in SIDES if v == 'front'])
def test_a_label_on_the_seam_stays_on_the_sheet(page, title):
    """The wall is framed with what hangs off it: every label stands inside
    the map's area, over no bracket."""
    pg, _ids, _errors = page
    out = _sheet(pg, title)
    a = out['area']
    for b in out['astride']:
        assert b['x'] >= a['x'] - 0.5 and b['x'] + b['w'] <= a['x'] + a['w'] + 0.5, (title, a, b)
        for k in out['brackets']:
            assert k['inkX2'] <= b['x'] or k['inkX1'] >= b['x'] + b['w'] \
                or k['y2'] <= b['y'] or k['y1'] >= b['y'] + b['h'], (title, 'bracket over a label', k, b)


def test_the_wall_outline_stops_at_a_label(page):
    """The map's black outline never runs through a label on the seam."""
    pg, _ids, _errors = page
    for name in ('WALL-L', 'WALL-R'):
        out = _sheet(pg, f'{name} - Power - Front View')
        discs = [s for s in out['seam'] if s['kind'] == 'disc']
        assert discs, out['seam']
        for s in discs:
            assert max(s['at']) > 120, (name, 'the outline runs through the disc', s)


@pytest.mark.parametrize('title', ['WALL-L - Power Wiring', 'WALL-R - Power Wiring',
                                   'WIDE-L - Power Wiring', 'WIDE-R - Power Wiring',
                                   'STACK-T - Power Wiring', 'STACK-B - Power Wiring'])
def test_a_run_goes_round_a_label_that_hangs_off_the_wall(page, title):
    """A rail stands outside what hangs off the wall, not inside it: no run
    crosses the middle of a disc on the seam."""
    pg, _ids, _errors = page
    out = _sheet(pg, title)
    discs = [b for b in out['astride'] if b['kind'] == 'disc']
    assert discs
    for run in out['runs']:
        pts = run['points']
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            for b in discs:
                cx, cy, r = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2, b['w'] / 2 * 0.6
                hits = (min(x1, x2) <= cx + r and max(x1, x2) >= cx - r
                        and min(y1, y2) <= cy + r and max(y1, y2) >= cy - r)
                assert not hits, (title, 'a run through the disc', run, b)


def test_a_wall_with_nothing_on_its_edge_keeps_its_size(page):
    """The frame is only as big as what hangs off the wall: a screen outside
    a group draws exactly as it did."""
    pg, _ids, _errors = page
    assert _sheet(pg, 'LONE - Power - Front View')['astride'] == []


# ── 2. the rings and the runs land on the discs ──────────────────────────

def _on_their_discs(out):
    """Every disc the wiring sheet logged is a disc the map drew."""
    drawn = [b for b in out['labels'] if b['kind'] == 'disc']
    assert out['discs'], out['title']
    for d in out['discs']:
        if not d['placed']:
            continue
        near = [b for b in drawn if abs(b['x'] + b['w'] / 2 - d['x']) < 1.5
                and abs(b['y'] + b['h'] / 2 - d['y']) < 1.5 and abs(b['w'] / 2 - d['r']) < 1.5]
        assert near, (out['title'], 'a ring away from its disc', d, drawn[:8])


@pytest.mark.parametrize('names,title', [
    ({'power': 'group'}, 'WALL - Power Wiring'),
    ({'power': 'screens'}, 'WALL-L - Power Wiring'),
    ({'power': 'screens'}, 'WALL-R - Power Wiring'),
    ({'data': 'group'}, 'WALL - Data Wiring'),
    ({'data': 'screens'}, 'WALL-L - Data Wiring'),
])
def test_the_rings_and_the_runs_stand_on_the_discs_the_wall_drew(page, names, title):
    """A wall whose members stand off their processor positions: the discs
    the sheet rings and runs to are the discs on the map, whichever frame
    the renderer drew them in, printed by group or by screen."""
    pg, _ids, _errors = page
    _names(pg, **names)
    try:
        out = _sheet(pg, title)
    finally:
        _names(pg, power='screens', data='screens')
    _on_their_discs(out)
    # and all of them on the sheet, on the wall
    w = out['wall']
    for d in out['discs']:
        if d['placed']:
            assert w['x'] - d['r'] - 1 <= d['x'] <= w['x'] + w['w'] + d['r'] + 1, (title, d, w)


def test_the_rings_stand_on_the_discs_on_a_rear_view(page):
    """A mirrored map: the transform carries the mirror too."""
    pg, _ids, _errors = page
    _names(pg, power='group')
    try:
        out = _sheet(pg, 'WALL - Power Wiring', view='rear')
    finally:
        _names(pg, power='screens')
    _on_their_discs(out)


# ── 3. a box on a wiring sheet names its fiber ───────────────────────────

@pytest.mark.parametrize('title,cable,other', [
    ('WALL-L - Data Wiring', 'TAC A (TAC 12 SM)', 'TAC B'),
    ('LONE - Data Wiring', 'TAC B (TAC 24 MM)', 'TAC A'),
])
def test_a_box_on_the_wiring_sheet_names_its_cable(page, title, cable, other):
    """The input, its cable with its mode in short, then the strands, inside
    the group's outline. Each box says its own cable, not the other run's."""
    pg, _ids, _errors = page
    out = _sheet(pg, title)
    assert cable in out['texts'], (title, [t for t in out['texts'] if 'TAC' in t])
    assert not [t for t in out['texts'] if t.startswith(other)], out['texts']
    (box,) = [b for b in out['blocks'] if b.get('inputs')]
    g = box['inputs'][0]
    assert g['x'] >= box['x'] and g['x'] + g['w'] <= box['x'] + box['w'] + 0.5, (box, g)


def test_a_box_says_a_cable_in_full_once(page):
    """Two inputs on one TAC: the first says what it is, the second its name,
    as the data sheet's band does, the strands starting level."""
    pg, ids, _errors = page
    groups = pg.evaluate("""(id) => {
        const app = window.app;
        const box = app._processorsResolved.flatMap(p => p.slots.flatMap(s => (s.card && s.card.cvts) || []))
            .find(b => b.id === id);
        return app._bwBoxInputs(box);
    }""", ids['two'])
    assert [g.get('sub') for g in groups] == ['TAC A (TAC 12 SM)', 'TAC A'], groups


def test_the_wiring_sheet_says_the_same_as_the_data_sheets_band(page):
    """One cable, one name: the wiring sheet and the band over the ports."""
    pg, _ids, _errors = page
    wiring = _sheet(pg, 'WALL-L - Data Wiring')['texts']
    band = _sheet(pg, 'WALL-L - Data - Front View')['texts']
    assert 'TAC A (TAC 12 SM)' in wiring and 'TAC A (TAC 12 SM)' in band, (wiring, band)


def test_every_other_strand_list_names_its_cable(page):
    """The strand maps of the Fiber page and the processor page carry the
    cable in their titles, and the Fiber connections table in its column:
    no list of strands in the binder goes without its cable."""
    pg, _ids, _errors = page
    texts = pg.evaluate("""(opts) => {
        const app = window.app;
        const o = {...opts, fiber: true, hardware: true};
        const plan = app.planBinder(o);
        const read = (kind) => plan.flatMap((p, i) => (p.kind === kind ? app.renderBinderPage(o, i).texts : []));
        return {fiber: read('fiber'), processor: read('processor')};
    }""", OPTS)
    up = [t.upper() for t in texts['fiber']]
    assert [t for t in up if t.startswith('STRAND MAP · TAC A · TAC 12')], up
    assert [t for t in up if t.startswith('STRAND MAP · TAC B · TAC 24')], up
    up = [t.upper() for t in texts['processor']]
    assert [t for t in up if t.startswith('STRAND MAP · TAC A · TAC 12')], up
    assert [t for t in up if t.startswith('STRAND MAP · TAC B · TAC 24')], up
    assert 'CABLE' in up and [t for t in up if t.startswith('TAC A')], up
