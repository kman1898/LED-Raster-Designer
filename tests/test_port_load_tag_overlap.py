"""A port's load % and its home run's cable tag never print over each other.

1.5.3, the owner's Brompton wall on an SX40, Data view, with SHOW PORT LOAD %
and SHOW CABLE TAGS both on: the ports start on the wall's BOTTOM row and run
up, so each primary marker hangs its home run's tag ("25'") UNDER the disc
(the run's side, the owner's ruling of 2026-09-25) - and the load badge was
painted under the disc too, before the tags were placed, so the pill covered
the percentage: "when you have port load percentage enabled on the data
screen, it is hidden by the cable length."

The rule now (canvas-data.js, placePortLoadBadge): the tag keeps its run's
side and the badge takes the other one - under the marker as it always was,
over it where the tag hangs under - then beside the marker when neither is
clear. Placed after every tag, so it is held off all of them, off every label
disc and inside the screen.

Read off canvas.js's label registry (startLabelProbe / endLabelProbe: the
boxes the map really drew, in the bitmap's pixels): 'disc', 'tag' and the
badge's 'load'. The ports are hand-drawn paths so each wall puts its markers
on exactly one edge; the tag text is stubbed to "25'" for the frame, as
test_power_tag_placement.py does, because the placement is under test here.

Run locally (each session takes its own free port, so it runs beside any
other):
    python -m pytest tests/test_port_load_tag_overlap.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder import _SHOW_JSON  # noqa: E402

# A hair, in bitmap pixels.
HAIR = 1.0
LABEL = 30          # the data map's default label size

# Five ports on a 5 x 5 wall, each a hand-drawn path that starts on one edge:
#   bottom - up each column from the bottom row (the owner's wall)
#   top    - down each column from the top row, on cabinets too short for
#            the tag to stand over the disc, so it goes under it
#   left   - along each row from the left column, going right
#   right  - along each row from the right column, going left
EDGES = {
    'bottom': dict(cabinet_height=176,
                   paths={n: [(r, n - 1) for r in (4, 3, 2, 1, 0)] for n in range(1, 6)}),
    'top': dict(cabinet_height=100,
                paths={n: [(r, n - 1) for r in (0, 1, 2, 3, 4)] for n in range(1, 6)}),
    'left': dict(cabinet_height=176,
                 paths={n: [(n - 1, c) for c in (0, 1, 2, 3, 4)] for n in range(1, 6)}),
    'right': dict(cabinet_height=176,
                  paths={n: [(n - 1, c) for c in (4, 3, 2, 1, 0)] for n in range(1, 6)}),
}

BUILD_JS = """async ([edge, cabH, paths, tags, rot]) => {
    const app = window.app;
    const cw = 176, rows = 5, cols = 5;
    const panels = [];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) panels.push({
        row: r, col: c, x: c * cw, y: r * cabH, width: cw, height: cabH,
        hidden: false, blank: false, halfTile: 'none' });
    const layer = { id: 1, name: 'WALL', type: 'screen', visible: true,
        columns: cols, rows, offset_x: 0, offset_y: 0,
        cabinet_width: cw, cabinet_height: cabH, panel_weight: 20, weight_unit: 'kg',
        processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
        flowPattern: 'custom', portMappingMode: 'organized', rotation: rot || 0,
        customPortPaths: Object.fromEntries(Object.entries(paths).map(([n, p]) =>
            [n, p.map(([row, col]) => ({ row, col }))])),
        showDataCableTags: tags, showDataFlowPortLoad: true,
        dataFlowLabelSize: %d, group_id: null, panels };
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', { layers: [layer], groups: [], rack: [] });
    app.project = await j('GET', '/api/project');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    return app.project.layers.map(l => [l.name, l.flowPattern]);
}""" % LABEL

# One frame of the data map at zoom 1, the world's origin at (120, 120) of
# the bitmap, under the label probe; `back` turns every canvas to the Back
# view for the frame. The home runs read "25'" for the frame.
PROBE_JS = """(back) => {
    const r = window.canvasRenderer, app = window.app;
    const prevMode = r.viewMode;
    const canvases = Array.isArray(app.project.canvases) ? app.project.canvases : [];
    const prevPersp = canvases.map(c => c.data_flow_perspective);
    const prevRoot = app.project.data_flow_perspective;
    if (back) {
        canvases.forEach(c => { c.data_flow_perspective = 'back'; });
        app.project.data_flow_perspective = 'back';
    }
    app.dataPortCableForScreen = () => ({ text: "25'" });
    app.dataPortBackupCableForScreen = () => null;
    r.viewMode = 'data-flow';
    r.zoom = 1;
    r.panX = 120;
    r.panY = 120;
    r.startLabelProbe();
    let boxes, mirrored;
    try { mirrored = r.isMirroredView(); r.render(); } finally {
        boxes = r.endLabelProbe();
        delete app.dataPortCableForScreen;
        delete app.dataPortBackupCableForScreen;
        canvases.forEach((c, i) => { c.data_flow_perspective = prevPersp[i]; });
        app.project.data_flow_perspective = prevRoot;
        r.viewMode = prevMode;
    }
    return { boxes, mirrored };
}"""

# The same wall on the binder's data sheets (each screen's Data map and its
# Data Wiring sheet): the binder lays a bitmap of the same renderer, so the
# registry reads the map that lands on the page.
BINDER_JS = """(opts) => {
    const app = window.app, r = window.canvasRenderer;
    app.dataPortCableForScreen = () => ({ text: "25'" });
    app.dataPortBackupCableForScreen = () => null;
    const out = {};
    try {
        const plan = app.planBinder(opts);
        for (let i = 0; i < plan.length; i++) {
            const p = plan[i];
            if (!(p.kind === 'data' || (p.kind === 'wiring' && / - Data Wiring$/.test(p.title)))) continue;
            r.startLabelProbe();
            try { app.renderBinderPage(opts, i); }
            finally { out[p.number + ' ' + p.title] = r.endLabelProbe(); }
        }
    } finally {
        delete app.dataPortCableForScreen;
        delete app.dataPortBackupCableForScreen;
    }
    return out;
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950},
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
    yield pg, errors
    context.close()


def _build(pg, edge, tags=True, rot=0):
    e = EDGES[edge]
    paths = {str(n): p for n, p in e['paths'].items()}
    built = pg.evaluate(BUILD_JS, [edge, e['cabinet_height'], paths, tags, rot])
    assert built == [['WALL', 'custom']], built
    pg.wait_for_timeout(300)


def _probe(pg, edge, back=False, tags=True, rot=0):
    _build(pg, edge, tags, rot)
    out = pg.evaluate(PROBE_JS, back)
    assert out['mirrored'] is back, ('the Back view did not take', out['mirrored'])
    return out['boxes']


def _kind(boxes, kind):
    return [b for b in boxes if b['kind'] == kind]


def _cx(b):
    return b['x'] + b['w'] / 2


def _cy(b):
    return b['y'] + b['h'] / 2


def _overlap(a, b):
    return (min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x']),
            min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']))


def _over(a, b):
    dx, dy = _overlap(a, b)
    return dx > HAIR and dy > HAIR


def _meets_disc(rect, disc):
    """The rect against the disc's circle, shrunk by a hair."""
    r = disc['w'] / 2 - HAIR
    qx = max(rect['x'], min(_cx(disc), rect['x'] + rect['w']))
    qy = max(rect['y'], min(_cy(disc), rect['y'] + rect['h']))
    return (qx - _cx(disc)) ** 2 + (qy - _cy(disc)) ** 2 < r * r


def _gap(a, b):
    return max(max(a['x'], b['x']) - min(a['x'] + a['w'], b['x'] + b['w']),
               max(a['y'], b['y']) - min(a['y'] + a['h'], b['y'] + b['h']))


def _name(b):
    return '%s %r at (%.1f, %.1f) %.1f x %.1f' % (b['kind'], b['text'], b['x'], b['y'], b['w'], b['h'])


def _primaries(boxes):
    return [d for d in _kind(boxes, 'disc') if d['text'].startswith('P')]


def _faults(boxes):
    """Every load badge clear of every tag, disc and other badge, inside
    the wall, and close to the primary marker it belongs to (a third of
    the marker's radius at most - the scale of whatever bitmap it is)."""
    bad = []
    loads, tags, discs = _kind(boxes, 'load'), _kind(boxes, 'tag'), _kind(boxes, 'disc')
    edges = _kind(boxes, 'wallEdge')
    for b in loads:
        for t in tags:
            if _over(b, t):
                dx, dy = _overlap(b, t)
                bad.append('%s under %s by %.1f x %.1f px' % (_name(b), _name(t), dx, dy))
        for d in discs:
            if _meets_disc(b, d):
                bad.append('%s covers disc %s' % (_name(b), d['text']))
        for o in loads:
            if o is not b and _over(b, o):
                bad.append('%s covers %s' % (_name(b), _name(o)))
        d = _owner(b, boxes)
        if _gap(b, d) > d['w'] / 2 / 3:
            bad.append('%s stands %.1f px off its marker %s' % (_name(b), _gap(b, d), d['text']))
        if len(edges) == 4:
            x0 = min(e['x'] for e in edges) - HAIR
            y0 = min(e['y'] for e in edges) - HAIR
            x1 = max(e['x'] + e['w'] for e in edges) + HAIR
            y1 = max(e['y'] + e['h'] for e in edges) + HAIR
            if not (b['x'] >= x0 and b['y'] >= y0 and b['x'] + b['w'] <= x1 and b['y'] + b['h'] <= y1):
                bad.append('%s leaves the wall' % _name(b))
    for t in tags:
        for d in discs:
            if _meets_disc(t, d):
                bad.append('%s covers disc %s' % (_name(t), d['text']))
    return bad


def _owner(b, boxes):
    return min(_primaries(boxes), key=lambda d: _gap(b, d))


CASES = [
    # edge, Back view, where the tag hangs (the run's side), where the badge goes
    ('bottom', False, 'under', 'over'),
    ('bottom', True, 'under', 'over'),
    ('top', False, 'under', 'beside'),
    ('top', True, 'under', 'beside'),
    ('left', False, 'over', 'under'),
    ('right', False, 'over', 'under'),
    ('left', True, 'over', 'under'),
]


def _where(b, d):
    if b['y'] >= d['y'] + d['h'] - HAIR:
        return 'under'
    if b['y'] + b['h'] <= d['y'] + HAIR:
        return 'over'
    return 'beside'


@pytest.mark.parametrize('edge,back,tag_at,load_at', CASES,
                         ids=['%s%s' % (c[0], '-back' if c[1] else '') for c in CASES])
def test_the_load_badge_and_the_cable_tag_never_overlap(page, edge, back, tag_at, load_at):
    """Both options on, the five ports starting on one edge of the wall
    (Front and Back view): every primary marker has its tag on the run's
    side and its load % on a side of its own, the two never touching, and
    neither covering any disc."""
    pg, errors = page
    boxes = _probe(pg, edge, back)
    loads, tags = _kind(boxes, 'load'), _kind(boxes, 'tag')
    assert len(_primaries(boxes)) == 5, [b['text'] for b in _kind(boxes, 'disc')]
    assert len(loads) == 5 and all(b['text'].endswith('%') for b in loads), loads
    assert [t['text'] for t in tags] == ["25'"] * 5, tags
    bad = _faults(boxes)
    # the tag keeps the owner's run-side placement; the badge takes its own
    for t in tags:
        d = _owner(t, boxes)
        if _where(t, d) != tag_at:
            bad.append('tag of %s is %s its disc, want %s' % (d['text'], _where(t, d), tag_at))
    owners = [_owner(b, boxes)['text'] for b in loads]
    assert sorted(owners) == sorted(d['text'] for d in _primaries(boxes)), owners
    for b in loads:
        d = _owner(b, boxes)
        if _where(b, d) != load_at:
            bad.append('load of %s is %s its disc, want %s' % (d['text'], _where(b, d), load_at))
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_with_the_tags_off_the_badge_stays_under_its_marker(page):
    """Nothing to make room for: the badge sits where it always has, centred
    under its primary marker."""
    pg, errors = page
    boxes = _probe(pg, 'bottom', tags=False)
    loads = _kind(boxes, 'load')
    assert len(loads) == 5 and not _kind(boxes, 'tag'), boxes
    bad = _faults(boxes)
    for b in loads:
        d = _owner(b, boxes)
        if _where(b, d) != 'under' or abs(_cx(b) - _cx(d)) > HAIR:
            bad.append('load of %s is not centred under it: %s' % (d['text'], _name(b)))
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_a_turned_screen_keeps_them_apart(page):
    """A quarter turn of the owner's wall: the badge is placed in the same
    upright frame the tags are, so the two stay apart on the sheet."""
    pg, errors = page
    try:
        boxes = _probe(pg, 'bottom', rot=90)
        assert len(_kind(boxes, 'load')) == 5 and len(_kind(boxes, 'tag')) == 5, boxes
        bad = _faults(boxes)
        assert not bad, '\n'.join([''] + bad)
    finally:
        _build(pg, 'bottom')
    assert errors == []


@pytest.mark.parametrize('edge', ['bottom', 'top'])
def test_the_binder_data_sheets_keep_them_apart(page, edge):
    """The binder's data sheets reuse the renderer, bitmap and all: on the
    wall's Data sheet the load % and the cable tag are both there and clear
    of each other."""
    pg, errors = page
    _build(pg, edge)
    opts = json.loads(_SHOW_JSON)
    opts['sides'] = {'power': False, 'data': True}
    sheets = pg.evaluate(BINDER_JS, opts)
    data = {k: v for k, v in sheets.items() if ' - Data' in k and 'Wiring' not in k}
    assert data, list(sheets)
    for name, boxes in sheets.items():
        if name in data:
            assert len(_kind(boxes, 'load')) == 5 and len(_kind(boxes, 'tag')) == 5, (name, boxes)
        bad = _faults(boxes)
        assert not bad, '\n'.join([name] + bad)
    assert errors == []
