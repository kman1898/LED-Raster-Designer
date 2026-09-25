"""Where a power head's cable tags hang: by the way its run leaves the disc.

The owner's ruling (2026-09-25), chosen from rendered options on his show:
the POWER map's cable tag (the circuit's cable, "10' True1") and the
splitter pill stacked with it ("3fer" / "2fer") go by the direction the
circuit's run LEAVES its label disc -

  - the run goes DOWN (it starts at the top)    -> the tags ABOVE the disc;
  - the run goes UP (it starts at the bottom)   -> the tags UNDER the disc;
  - the run goes RIGHT, or LEFT                 -> the tags ABOVE the disc;
  - a circuit of one cabinet has no step        -> ABOVE;

centred on the disc's x, the tag first and the pill beneath it, the pill
CENTRED under the tag ("3fer etc needs to be centered under the True1
extension") - so above the disc the column reads tag, pill, disc and under
it disc, tag, pill. The direction is the run's first step AS DRAWN: on a
rotated screen "down" is down on the sheet. When the preferred spot would
leave the screen or cover another disc or pill, the tags fall back through
the old order (right-or-left, the other, below, above - least bad wins when
none is clear). The data map's order is untouched.

Read off canvas.js's label registry (startLabelProbe / endLabelProbe: the
boxes the map really drew, in the bitmap's pixels, 'disc' / 'tag' /
'gang').

Run locally (each session takes its own free port, so it runs beside any
other):
    python3 -m pytest tests/test_power_tag_placement.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# A hair, in bitmap pixels.
HAIR = 1.0

# WALL: 5 x 5 cabinets of 100 W on a 100 V x 15 A circuit - a row or a
# column of five is 500 W, so three runs fill a circuit and the packer
# gangs [3, 2]: circuit 1 a 3fer, circuit 2 a 2fer, on whichever axis the
# flow pattern runs. ONE: a single cabinet, a circuit with no step. SHORT
# (the fallback): the WALL's shape on cabinets 40 tall, so a head on the
# top row has no room over its disc inside the screen.
BUILD_JS = """async ([walls, pattern, rot]) => {
    const app = window.app;
    const screen = (o) => {
        const panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) panels.push({
            row: r, col: c, x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
            width: o.cabinet_width, height: o.cabinet_height, hidden: false, blank: false, halfTile: 'none' });
        return Object.assign({ type: 'screen', visible: true, cabinet_width: 128, cabinet_height: 128,
            panel_weight: 20, weight_unit: 'kg', panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
            powerBreakoutType: 'soca-true1',
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized', powerOrganized: true, powerMaximize: false,
            powerFlowPattern: pattern, rotation: rot || 0,
            powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } },
            powerCircuitCables: { 1: { ft: 10 }, 2: { ft: 25 } },
            showPowerCableTags: true, showPowerNferTags: true, powerLabelSize: 14,
            group_id: null, panels }, o);
    };
    const all = {
        WALL: { id: 1, name: 'WALL', columns: 5, rows: 5, offset_x: 0, offset_y: 0 },
        ONE: { id: 2, name: 'ONE', columns: 1, rows: 1, offset_x: 900, offset_y: 0,
               powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } } },
        SHORT: { id: 3, name: 'SHORT', columns: 5, rows: 5, offset_x: 0, offset_y: 0,
                 cabinet_height: 40 },
    };
    const layers = walls.map(n => screen(all[n]));
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', { layers, groups: [], canvases: [], rack: [] });
    app.project = await j('GET', '/api/project');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    return app.project.layers.map(l => [l.name, l.powerFlowPattern, l.rotation || 0]);
}"""

# Zoom 1 with the world's origin at (120, 120) of the bitmap: render under
# the label probe, and hand back the registry.
PROBE_JS = """() => {
    const r = window.canvasRenderer;
    for (const l of window.app.project.layers) {
        delete l._powerCircuits; delete l._powerCircuitRuns;
        delete l._powerCircuitNumKeys; delete l._powerCircuitOwners;
    }
    window.app._circuitTailCache = null;
    r.zoom = 1;
    r.panX = 120;
    r.panY = 120;
    r.startLabelProbe();
    let boxes;
    try { r.render(); } finally { boxes = r.endLabelProbe(); }
    return boxes;
}"""


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
    yield pg, errors
    context.close()


def _probe(pg, walls, pattern, rot=0):
    built = pg.evaluate(BUILD_JS, [walls, pattern, rot])
    assert [b[0] for b in built] == walls, built
    pg.wait_for_timeout(300)
    return pg.evaluate(PROBE_JS)


def _kind(boxes, kind):
    return [b for b in boxes if b['kind'] == kind]


def _cx(b):
    return b['x'] + b['w'] / 2


def _cy(b):
    return b['y'] + b['h'] / 2


def _over(a, b):
    """Two boxes overlap by more than a hair on both axes."""
    dx = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
    dy = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
    return dx > HAIR and dy > HAIR


def _meets_disc(rect, disc):
    """The rect against the disc's circle (its box is the circle's square),
    shrunk by a hair: a rim touching is not a cover."""
    r = disc['w'] / 2 - HAIR
    qx = max(rect['x'], min(_cx(disc), rect['x'] + rect['w']))
    qy = max(rect['y'], min(_cy(disc), rect['y'] + rect['h']))
    return (qx - _cx(disc)) ** 2 + (qy - _cy(disc)) ** 2 < r * r


def _gap(a, b):
    return max(max(a['x'], b['x']) - min(a['x'] + a['w'], b['x'] + b['w']),
               max(a['y'], b['y']) - min(a['y'] + a['h'], b['y'] + b['h']))


def _heads(boxes):
    """Each disc that carries a tag: (disc, tag, pill or None). A pill or a
    tag belongs to the disc it stands nearest."""
    discs, tags, pills = _kind(boxes, 'disc'), _kind(boxes, 'tag'), _kind(boxes, 'gang')
    near = lambda b: min(discs, key=lambda d: _gap(b, d))
    out = []
    for d in discs:
        mine = [t for t in tags if near(t) is d]
        ps = [p for p in pills if near(p) is d]
        assert len(mine) <= 1 and len(ps) <= 1, (d['text'], mine, ps)
        if mine:
            out.append((d, mine[0], ps[0] if ps else None))
    return out


def _faults(boxes, want):
    """Every rule of the ruling, for heads that should hang `want` ('above'
    or 'under'), as lines."""
    bad = []
    discs = _kind(boxes, 'disc')
    pills = _kind(boxes, 'gang')
    ink = _kind(boxes, 'tag') + pills
    for d, t, p in _heads(boxes):
        name = '%s %r' % (d['text'], t['text'])
        if abs(_cx(t) - _cx(d)) > HAIR:
            bad.append('%s: tag centre x %.1f, disc centre x %.1f' % (name, _cx(t), _cx(d)))
        column = [t] + ([p] if p else [])
        if want == 'above':
            if not all(b['y'] + b['h'] <= d['y'] + HAIR for b in column):
                bad.append('%s: the column is not above the disc (disc top %.1f, %r)'
                           % (name, d['y'], [(b['text'], b['y'], b['h']) for b in column]))
        else:
            if not all(b['y'] >= d['y'] + d['h'] - HAIR for b in column):
                bad.append('%s: the column is not under the disc (disc bottom %.1f, %r)'
                           % (name, d['y'] + d['h'], [(b['text'], b['y'], b['h']) for b in column]))
        if p:
            # the pill centred under the tag, a hair apart; above the disc
            # that puts it between the tag and the disc
            if abs(_cx(p) - _cx(t)) > HAIR:
                bad.append('%s: pill %s centre x %.1f, tag centre x %.1f' % (name, p['text'], _cx(p), _cx(t)))
            gap = p['y'] - (t['y'] + t['h'])
            if not (-HAIR <= gap < 6):
                bad.append('%s: pill %s is not directly beneath the tag (gap %.1f)' % (name, p['text'], gap))
    # nothing the tags drew covers a disc - its own or another - or
    # another pill
    for b in ink:
        for d in discs:
            if _meets_disc(b, d):
                bad.append('%s %r covers disc %s' % (b['kind'], b['text'], d['text']))
        for o in ink:
            if o is not b and _over(b, o):
                bad.append('%s %r covers %s %r' % (b['kind'], b['text'], o['kind'], o['text']))
    return bad


# pattern -> the run's first step -> the side the ruling hangs the tags
FLOWS = [
    ('tl-v', 'down', 'above'),
    ('bl-v', 'up', 'under'),
    ('tl-h', 'right', 'above'),
    ('tr-h', 'left', 'above'),
]


@pytest.mark.parametrize('pattern,step,want', FLOWS, ids=[f[1] for f in FLOWS])
def test_the_tags_hang_by_the_way_the_run_leaves_its_disc(page, pattern, step, want):
    """Each flow direction on the 5 x 5 wall: both shared heads (a 3fer and
    a 2fer) hang tag and pill on the ruled side, centred on the disc, the
    pill centred under the tag, nothing covered; the one-cabinet circuit
    beside it hangs its tag above whatever the pattern."""
    pg, errors = page
    boxes = _probe(pg, ['WALL', 'ONE'], pattern)
    heads = _heads(boxes)
    wall = [h for h in heads if _cx(h[0]) < 120 + 800]
    one = [h for h in heads if _cx(h[0]) >= 120 + 800]
    # the fixture: two shared heads on the wall, each with its tag and pill
    assert sorted((t['text'], p and p['text']) for _, t, p in wall) == [
        ("10' True1", '3fer'), ("25' True1", '2fer')], [(d['text'], t['text'], p and p['text']) for d, t, p in wall]
    assert [(t['text'], p) for _, t, p in one] == [("10' True1", None)], one
    bad = _faults(_wall_boxes(boxes, wall), want)
    bad += _faults(_wall_boxes(boxes, one), 'above')
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def _wall_boxes(boxes, heads):
    """The discs of the whole map (a tag must clear every one) and only the
    tags and pills of these heads."""
    keep = {id(b) for h in heads for b in h if b}
    return [b for b in boxes if b['kind'] == 'disc' or id(b) in keep]


# A quarter turn: the tags go by the step AS DRAWN. Turned 90 degrees, a
# run that goes left along the wall goes UP on the sheet, and one that goes
# up along the wall goes RIGHT - so the right-to-left wall hangs its tags
# under its discs and the bottom-up wall hangs them above.
TURNED = [
    ('tr-h', 'under'),
    ('bl-v', 'above'),
]


@pytest.mark.parametrize('pattern,want', TURNED, ids=[t[0] for t in TURNED])
def test_a_turned_screen_reads_the_run_on_the_sheet(page, pattern, want):
    pg, errors = page
    try:
        boxes = _probe(pg, ['WALL'], pattern, 90)
        heads = _heads(boxes)
        assert len(heads) == 2 and all(p for _, _, p in heads), heads
        bad = _faults(boxes, want)
        assert not bad, '\n'.join([''] + bad)
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


def test_with_no_room_over_the_disc_the_tags_go_under_it(page):
    """SHORT: the wall's shape on cabinets 40 px tall, run down its columns.
    The ruling wants the tags over the heads, but a head sits on the top
    row and the column (tag, pill, stand-off) is taller than the room above
    it inside the screen - so the tags go to the OTHER side of the disc
    (the owner, 2026-09-25: "we should go below"): UNDER it, centred on
    it, the pill still centred under the tag, covering nothing."""
    pg, errors = page
    boxes = _probe(pg, ['SHORT'], 'tl-v')
    heads = _heads(boxes)
    assert len(heads) == 2 and all(p for _, _, p in heads), heads
    edges = _kind(boxes, 'wallEdge')
    top = min(e['y'] for e in edges)
    bad = []
    for d, t, p in heads:
        name = '%s %r' % (d['text'], t['text'])
        # the preferred spot really is off the screen: the column above
        # the disc would start over the wall's top edge
        column_h = t['h'] + p['h'] + 1 + 14 * 0.6
        assert d['y'] - column_h < top, ('the fixture must leave no room above', name, d, top)
        if t['y'] < d['y'] + d['h'] - HAIR:
            bad.append('%s: tag top %.1f is not under the disc (bottom %.1f)'
                       % (name, t['y'], d['y'] + d['h']))
        if abs(_cx(t) - _cx(d)) > HAIR:
            bad.append('%s: tag centre x %.1f, disc centre x %.1f' % (name, _cx(t), _cx(d)))
        if abs(_cx(p) - _cx(t)) > HAIR:
            bad.append('%s: pill centre x %.1f, tag centre x %.1f' % (name, _cx(p), _cx(t)))
        if not (-HAIR <= p['y'] - (t['y'] + t['h']) < 6):
            bad.append('%s: pill not directly beneath the tag' % name)
    ink = _kind(boxes, 'tag') + _kind(boxes, 'gang')
    for b in ink:
        for d in _kind(boxes, 'disc'):
            if _meets_disc(b, d):
                bad.append('%s %r covers disc %s' % (b['kind'], b['text'], d['text']))
        for o in ink:
            if o is not b and _over(b, o):
                bad.append('%s %r covers %s %r' % (b['kind'], b['text'], o['kind'], o['text']))
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_the_data_map_keeps_its_order(page):
    """placeCableTag with no `place` argument is the data map's call: it
    still hangs a tag right of its disc when that is clear, whatever run
    it names - the power ruling reaches only the power pass."""
    pg, _ = page
    out = pg.evaluate("""() => {
        const r = window.canvasRenderer;
        const bounds = { left: 0, top: 0, right: 1000, bottom: 1000 };
        const own = { x: 500, y: 500, r: 20 };
        const plain = r.placeCableTag("10' Cat6", 500, 500, 20, 14, bounds, [own], own, []);
        const ruled = r.placeCableTag("10' Cat6", 500, 500, 20, 14, bounds, [own], own, [],
                                      { prefer: 'above' });
        return { plain: plain.opts.side, ruled: ruled.opts.side,
                 ruledCx: ruled.rect.x + ruled.rect.w / 2 };
    }""")
    assert out['plain'] == 'right', out
    assert out['ruled'] == 'above' and abs(out['ruledCx'] - 500) < 1e-6, out
