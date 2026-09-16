"""The 2fer / 3fer pill rides with the shared circuit's cable tag.

A shared circuit (two or three runs ganged through a splitter) used to say
so with a "2fer" pill floating on the gang bracket under the runs' feet -
on a wall of row runs, a row seam a long way from the runs' heads: "when
two fers or similar are enabled on the screen to be seen, the drawing
isn't obvious what it is connected to" (2026-09-15). The pill now hangs
off the shared circuit's own label disc as a second row of the cable
tag's stack - "it should just connect to 10' True1 for example. just put
it right above that or under it" - so a head reads S1-1 · 10' Edison ·
3fer. The rules, read off canvas.js's label registry (the boxes the map
really drew, in the bitmap's pixels):

  - every shared circuit's disc carries a pill (kind 'gang', the name the
    collision guards and the binder's ink price know it by), directly
    under or over that disc's cable tag, flush with the tag's edge nearest
    the disc, a hair of a gap between them;
  - an unshared circuit's disc gets none, and no pill sits away from a
    shared disc;
  - with Show Cable Tags off the pill takes the cable tag's place beside
    the disc; with Show 2fer/3fer Tags off there is no pill at all (the
    bracket under the feet stays - it is not touched here);
  - the pill never covers a disc, a tag or another pill, and stays inside
    its wall; the same at any zoom and on a rotated screen, where the
    stack is a stack ON THE PAGE (the tags are placed in the upright frame
    and painted upright about their anchor);
  - and the pill is really painted: its fill is on the canvas where the
    registry says the pill is.

Three walls: ROWS (5x5, row runs, packed [3, 2] = a 3fer and a 2fer),
COLS (the same packed by columns) and PLAIN (5x5 rows on a one-row circuit,
splitters off - five single-run circuits, two of them with cable tags).

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_nfer_brackets.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# A hair, in canvas pixels: half a rim's width of rounding, not ink on ink.
HAIR = 1.0

BUILD_JS = """async (rot) => {
    const app = window.app;
    const screen = (o) => {
        const panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) panels.push({
            row: r, col: c, x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
            width: o.cabinet_width, height: o.cabinet_height, hidden: false, blank: false, halfTile: 'none' });
        return Object.assign({ type: 'screen', visible: true, cabinet_width: 128, cabinet_height: 128,
            panel_weight: 20, weight_unit: 'kg', panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized', powerOrganized: true, powerMaximize: false,
            group_id: null, panels }, o);
    };
    // 100W tiles on a 100V x 15A circuit: a row or column of five is 500W,
    // so three runs fill the circuit exactly and the packer gangs [3, 2].
    const layers = [
        screen({ id: 1, name: 'ROWS', columns: 5, rows: 5, offset_x: 0, offset_y: 0,
                 powerFlowPattern: 'tl-h', rotation: rot || 0 }),
        screen({ id: 2, name: 'COLS', columns: 5, rows: 5, offset_x: 900, offset_y: 0,
                 powerFlowPattern: 'tl-v', rotation: rot || 0 }),
        // PLAIN: a 5A circuit holds one row exactly, so with the splitters
        // off every row is a circuit of its own - five unshared discs.
        screen({ id: 3, name: 'PLAIN', columns: 5, rows: 5, offset_x: 1800, offset_y: 0,
                 powerFlowPattern: 'tl-h', powerAmperage: 5, rotation: rot || 0 }),
    ];
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', { layers, groups: [], canvases: [], rack: [] });
    app.project = await j('GET', '/api/project');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    return app.project.layers.map(l => [l.id, l.name, l.rotation || 0]);
}"""

# The switches under test, set on the live layer objects (no server trip:
# the view is what is judged) and the caches the power pass keeps cleared.
SET_JS = """([cable, nfer]) => {
    const app = window.app;
    for (const l of app.project.layers) {
        l.powerSplitters = { enabled: l.name !== 'PLAIN', maxWays: 3, manual: { merge: [], split: [] } };
        l.powerCircuitCables = { 1: { ft: 10 }, 2: { ft: 25 } };
        l.showPowerCableTags = cable;
        l.showPowerNferTags = nfer;
        l.powerLabelSize = 14;
        delete l._powerCircuits; delete l._powerCircuitRuns;
        delete l._powerCircuitNumKeys; delete l._powerCircuitOwners;
    }
}"""

# Zoom to `z` with the world point (wx, wy) at the canvas centre, render
# under the label probe, and hand back the registry with the view.
PROBE_JS = """([z, wx, wy]) => {
    const r = window.canvasRenderer;
    r.zoom = z;
    r.panX = r.canvas.width / 2 - wx * z;
    r.panY = r.canvas.height / 2 - wy * z;
    r.startLabelProbe();
    let boxes;
    try { r.render(); } finally { boxes = r.endLabelProbe(); }
    return { boxes, zoom: z, panX: r.panX, panY: r.panY };
}"""

PIXEL_JS = """(pts) => {
    const c = document.getElementById('main-canvas');
    const ctx = c.getContext('2d');
    return pts.map(([x, y]) => Array.from(ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data).slice(0, 3));
}"""

# The pill's colours as canvas.js paints them (NFER_TAG_COLORS.fill and
# POWER_CABLE_TAG_COLORS.fill).
NFER_FILL = (0x2e, 0x2e, 0x2e)
CABLE_FILL = (0x1c, 0x1c, 0x1c)

# Which shared disc carries which pill: the packer gangs runs 1-3 into
# circuit 1 and runs 4-5 into circuit 2 on both shared walls.
PILL_OF = {'S1-1': '3fer', 'S1-2': '2fer'}


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950},
                                     device_scale_factor=1)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    built = pg.evaluate(BUILD_JS, 0)
    assert [b[1] for b in built] == ['ROWS', 'COLS', 'PLAIN'], built
    pg.wait_for_timeout(800)
    yield pg, errors
    context.close()


@pytest.fixture()
def unrotated(page):
    """Every test starts on the unrotated walls; the rotated test turns
    them and turns them back."""
    pg, _ = page
    pg.evaluate(BUILD_JS, 0)
    pg.wait_for_timeout(300)
    yield pg


def _view(pg, cable, nfer, zoom, at=(1400, 320)):
    pg.evaluate(SET_JS, [cable, nfer])
    return pg.evaluate(PROBE_JS, [zoom, at[0], at[1]])


def _kind(boxes, kind):
    return [b for b in boxes if b['kind'] == kind]


def _gap(a, b):
    """Edge-to-edge distance between two boxes, per axis (negative when
    they overlap on that axis)."""
    return (max(a['x'], b['x']) - min(a['x'] + a['w'], b['x'] + b['w']),
            max(a['y'], b['y']) - min(a['y'] + a['h'], b['y'] + b['h']))


def _over(a, b):
    dx, dy = _gap(a, b)
    return dx < -HAIR and dy < -HAIR


def _nearest_disc(box, discs):
    return min(discs, key=lambda d: max(_gap(box, d)))


def _world_x(view, box):
    return (box['x'] - view['panX']) / view['zoom']


def _wall_of(box, boxes):
    """The wall whose four edges enclose the box's centre: its rect."""
    cx, cy = box['x'] + box['w'] / 2, box['y'] + box['h'] / 2
    edges = _kind(boxes, 'wallEdge')
    for i in range(0, len(edges), 4):
        quad = edges[i:i + 4]
        x0 = min(e['x'] for e in quad)
        y0 = min(e['y'] for e in quad)
        x1 = max(e['x'] + e['w'] for e in quad)
        y1 = max(e['y'] + e['h'] for e in quad)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return x0, y0, x1, y1
    raise AssertionError('no wall encloses %r' % box)


def _stack_faults(view):
    """Every rule of the stack on one render, as lines."""
    boxes = view['boxes']
    discs, tags, pills = _kind(boxes, 'disc'), _kind(boxes, 'tag'), _kind(boxes, 'gang')
    bad = []
    if len(pills) != 4:
        bad.append('expected 4 pills (a 3fer and a 2fer on each shared wall), got %r'
                   % [p['text'] for p in pills])
    if sorted(p['text'] for p in pills) != ['2fer', '2fer', '3fer', '3fer']:
        bad.append('pill texts %r' % sorted(p['text'] for p in pills))
    # the shared walls are ROWS (x 0-640) and COLS (x 900-1540); PLAIN,
    # whose circuits are unshared, stands at x 1800-2440
    shared = [d for d in discs if _world_x(view, d) < 1700]
    plain = [d for d in discs if _world_x(view, d) >= 1700]
    assert len(plain) == 5, [d['text'] for d in plain]
    for p in pills:
        d = _nearest_disc(p, discs)
        if d in plain:
            bad.append('%s sits at %s of the unshared wall' % (p['text'], d['text']))
            continue
        if PILL_OF.get(d['text']) != p['text']:
            bad.append('%s sits at %s, which is a %s' % (p['text'], d['text'], PILL_OF.get(d['text'])))
        # beside its disc: within a label of it, never over it
        gx, gy = _gap(p, d)
        if max(gx, gy) > 14 * view['zoom']:
            bad.append('%s stands %.1f px off %s - not beside it' % (p['text'], max(gx, gy), d['text']))
        # stacked with the disc's cable tag: same left edge, a hair apart,
        # one directly over the other
        mine = [t for t in tags if _nearest_disc(t, discs) is d]
        if tags and len(mine) != 1:
            bad.append('%s at %s has %d cable tags beside it' % (p['text'], d['text'], len(mine)))
        for t in mine:
            # flush with the tag's edge nearest the disc: the left edge of
            # a tag hung right of its disc, the right edge of one hung left
            if t['x'] + t['w'] / 2 >= d['x'] + d['w'] / 2:
                if abs(t['x'] - p['x']) > 2:
                    bad.append('%s left edge %.1f, its tag %s left edge %.1f' % (p['text'], p['x'], t['text'], t['x']))
            elif abs((t['x'] + t['w']) - (p['x'] + p['w'])) > 2:
                bad.append('%s right edge %.1f, its tag %s right edge %.1f'
                           % (p['text'], p['x'] + p['w'], t['text'], t['x'] + t['w']))
            gx, gy = _gap(p, t)
            if gx > -HAIR:
                bad.append('%s is beside its tag %s, not over or under it' % (p['text'], t['text']))
            if not (-HAIR <= gy < 6):
                bad.append('%s stands %.1f px off its tag %s' % (p['text'], gy, t['text']))
        # covers nothing, and stays inside its wall
        for o in discs + tags + [q for q in pills if q is not p]:
            if _over(p, o):
                bad.append('%s covers %s "%s"' % (p['text'], o['kind'], o['text']))
        x0, y0, x1, y1 = _wall_of(d, boxes)
        if p['x'] < x0 - HAIR or p['x'] + p['w'] > x1 + HAIR or p['y'] < y0 - HAIR or p['y'] + p['h'] > y1 + HAIR:
            bad.append('%s at %s leaves its wall' % (p['text'], d['text']))
    for d in shared:
        if d['text'] in PILL_OF and not any(_nearest_disc(p, discs) is d for p in pills):
            bad.append('shared disc %s has no pill' % d['text'])
    return bad


@pytest.mark.parametrize('zoom', [1.0, 3.7])
def test_every_shared_head_stacks_its_pill_under_the_cable_tag(unrotated, zoom):
    """Cable tags on, Nfer tags on: each shared disc reads disc · tag ·
    pill, the pill directly under the tag with the tag's left edge; the
    unshared wall's discs get none; nothing is covered."""
    view = _view(unrotated, True, True, zoom)
    bad = _stack_faults(view)
    assert not bad, '\n'.join([''] + bad)


@pytest.mark.parametrize('zoom', [1.0, 3.7])
def test_with_cable_tags_off_the_pill_takes_the_tags_place(unrotated, zoom):
    """The pill hangs where the cable tag would: same left edge, same
    centre line, beside the disc."""
    with_tags = _view(unrotated, True, True, zoom)
    without = _view(unrotated, False, True, zoom)
    assert not _kind(without['boxes'], 'tag'), 'cable tags off drew a tag'
    discs = _kind(without['boxes'], 'disc')
    pills = _kind(without['boxes'], 'gang')
    assert sorted(p['text'] for p in pills) == ['2fer', '2fer', '3fer', '3fer']
    tags = _kind(with_tags['boxes'], 'tag')
    seen = 0
    for p in pills:
        d = _nearest_disc(p, discs)
        assert PILL_OF.get(d['text']) == p['text'], (p, d)
        tag = [t for t in tags if abs(_nearest_disc(t, _kind(with_tags['boxes'], 'disc'))['x'] - d['x']) < HAIR
               and abs(_nearest_disc(t, _kind(with_tags['boxes'], 'disc'))['y'] - d['y']) < HAIR]
        assert len(tag) == 1, (p['text'], d['text'], tag)
        t = tag[0]
        assert abs(t['x'] - p['x']) <= HAIR, 'pill left %.1f, tag left %.1f' % (p['x'], t['x'])
        assert abs((t['y'] + t['h'] / 2) - (p['y'] + p['h'] / 2)) <= HAIR, \
            'pill centre %.1f, tag centre %.1f' % (p['y'] + p['h'] / 2, t['y'] + t['h'] / 2)
        seen += 1
    assert seen == 4


@pytest.mark.parametrize('cable', [True, False])
def test_with_nfer_tags_off_there_is_no_pill(unrotated, cable):
    on = _view(unrotated, cable, True, 1.0)
    off = _view(unrotated, cable, False, 1.0)
    assert _kind(on['boxes'], 'gang'), 'the switch-on render drew no pill'
    assert not _kind(off['boxes'], 'gang'), [b['text'] for b in _kind(off['boxes'], 'gang')]
    # the discs and the cable tags are untouched by the switch
    strip = lambda bs: [(b['kind'], b['text'], round(b['x'], 1), round(b['y'], 1))
                        for b in bs if b['kind'] in ('disc', 'tag')]
    assert strip(off['boxes']) == strip(on['boxes'])


@pytest.mark.parametrize('zoom', [1.0, 3.7])
def test_a_rotated_screen_stacks_its_pill_on_the_page(page, zoom):
    """Turned 90 degrees, the tag and the pill are still a column beside
    the disc ON THE PAGE - placed in the upright frame and painted upright
    - and cover nothing. The walls are turned back afterwards."""
    pg, _ = page
    built = pg.evaluate(BUILD_JS, 90)
    assert [b[2] for b in built] == [90, 90, 90], built
    pg.wait_for_timeout(300)
    try:
        view = _view(pg, True, True, zoom)
        bad = _stack_faults(view)
        assert not bad, '\n'.join([''] + bad)
        bare = _view(pg, False, True, zoom)
        assert sorted(p['text'] for p in _kind(bare['boxes'], 'gang')) == ['2fer', '2fer', '3fer', '3fer']
    finally:
        pg.evaluate(BUILD_JS, 0)
        pg.wait_for_timeout(300)


def test_the_pill_is_painted_where_the_registry_says(unrotated):
    """Zoomed on the ROWS wall's 3fer head, the canvas holds the pill's own
    fill inside the pill's box and the cable tag's fill inside the tag's -
    the stack is ink, not just a registry entry."""
    pg = unrotated
    view = _view(pg, True, True, 3.7, at=(150, 200))
    boxes = view['boxes']
    w, h = pg.evaluate("[document.getElementById('main-canvas').width, document.getElementById('main-canvas').height]")
    on_canvas = lambda b: 0 <= b['x'] and b['x'] + b['w'] <= w and 0 <= b['y'] and b['y'] + b['h'] <= h
    pill = [p for p in _kind(boxes, 'gang') if p['text'] == '3fer' and on_canvas(p)]
    tag = [t for t in _kind(boxes, 'tag') if t['text'] == "10' Edison" and on_canvas(t)]
    assert len(pill) == 1 and len(tag) == 1, (pill, tag)
    p, t = pill[0], tag[0]
    # inside the left cap of each pill, off the rim and short of the text
    pts = [(b['x'] + b['h'] * 0.2, b['y'] + b['h'] * f) for b in (p, t) for f in (0.4, 0.5, 0.6)]
    got = pg.evaluate(PIXEL_JS, pts)
    want = [NFER_FILL] * 3 + [CABLE_FILL] * 3
    for (px, py), rgb, exp in zip(pts, got, want):
        assert all(abs(a - b) <= 8 for a, b in zip(rgb, exp)), \
            'at (%.0f, %.0f) got %r, wanted %r' % (px, py, rgb, exp)


def test_no_page_errors(page):
    _, errors = page
    assert errors == []
