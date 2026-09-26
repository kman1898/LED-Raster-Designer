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
the OTHER side of the disc (above <-> under), and beside it only after
that - least bad wins when none is clear.

The DATA map's port tags go by the same rule (the owner, same day: "we need
to make the cable tag in the top correct not on the side like it is"),
read off the port run's first step; a RETURN marker's run leaves it the way
the backup feeds it, from the last cabinet back to the one before. A data
tag has no second pill.

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
# top row has no room over its disc inside the screen. DWALL, DONE and
# DSHORT are their data-map twins (the data pass, flowPattern = the
# pattern; 12-bit at 250 Hz, so a port holds one run of five cabinets).
BUILD_JS = """async ([walls, pattern, rot]) => {
    const app = window.app;
    const screen = ({ dataFlow, ...o }) => {
        const panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) panels.push({
            row: r, col: c, x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
            width: o.cabinet_width, height: o.cabinet_height, hidden: false, blank: false, halfTile: 'none' });
        return Object.assign({ type: 'screen', visible: true, cabinet_width: 128, cabinet_height: 128,
            panel_weight: 20, weight_unit: 'kg', panelWatts: 100, powerVoltage: 100, powerAmperage: 15,
            powerBreakoutType: 'soca-true1',
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: dataFlow ? pattern : 'tl-h', portMappingMode: 'organized',
            powerOrganized: true, powerMaximize: false,
            powerFlowPattern: dataFlow ? 'tl-h' : pattern, rotation: rot || 0,
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
        DWALL: { id: 4, name: 'DWALL', columns: 5, rows: 5, offset_x: 0, offset_y: 0,
                 dataFlow: true, bitDepth: 12, frameRate: 250,
                 showDataCableTags: true, dataFlowLabelSize: 14 },
        DONE: { id: 5, name: 'DONE', columns: 1, rows: 1, offset_x: 900, offset_y: 0,
                dataFlow: true, bitDepth: 12, frameRate: 250,
                showDataCableTags: true, dataFlowLabelSize: 14 },
        DSHORT: { id: 6, name: 'DSHORT', columns: 5, rows: 5, offset_x: 0, offset_y: 0,
                  cabinet_height: 24, dataFlow: true, showDataCableTags: true,
                  dataFlowLabelSize: 14,
                  // a port down each column, top to bottom (flow 'custom')
                  customPortPaths: Object.fromEntries([1, 2, 3, 4, 5].map(n =>
                      [n, [0, 1, 2, 3, 4].map(row => ({ row, col: n - 1 }))])) },
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


# THE DATA MAP (the owner, 2026-09-25: "we need to make the cable tag in
# the top correct not on the side like it is"): a port's tag goes by the
# same rule, read off the port run's first step. A data tag's text comes
# from the processor's card and cable sheet; the placement is what is
# under test here, so the probe hands every primary marker "25'" (and,
# with `backup`, every return marker "BU 25'") for the one frame and puts
# the readings back. The frame is drawn in the data view.
DATA_PROBE_JS = """(backup) => {
    const r = window.canvasRenderer, app = window.app;
    const prevMode = r.viewMode;
    app.dataPortCableForScreen = () => ({ text: "25'" });
    app.dataPortBackupCableForScreen = () => (backup ? { text: "BU 25'" } : null);
    r.viewMode = 'data-flow';
    r.zoom = 1;
    r.panX = 120;
    r.panY = 120;
    r.startLabelProbe();
    let boxes;
    try { r.render(); } finally {
        boxes = r.endLabelProbe();
        delete app.dataPortCableForScreen;
        delete app.dataPortBackupCableForScreen;
        r.viewMode = prevMode;
    }
    return boxes;
}"""


def _data_probe(pg, walls, pattern, backup=False, rot=0):
    built = pg.evaluate(BUILD_JS, [walls, pattern, rot])
    assert [b[0] for b in built] == walls, built
    pg.wait_for_timeout(300)
    return pg.evaluate(DATA_PROBE_JS, backup)


@pytest.mark.parametrize('pattern,step,want', FLOWS, ids=[f[1] for f in FLOWS])
def test_a_data_tag_hangs_by_the_way_the_port_run_leaves_its_disc(page, pattern, step, want):
    """The data map, each flow direction on a 5 x 5 wall of five ports:
    every port's tag hangs on the ruled side of its primary marker, centred
    on it, covering nothing - the ISR B-8 head of the owner's show, whose
    run goes down, wore its "25'" LEFT of the disc. The one-cabinet port
    beside the wall hangs its tag above whatever the pattern."""
    pg, errors = page
    boxes = _data_probe(pg, ['DWALL', 'DONE'], pattern)
    heads = _heads(boxes)
    wall = [h for h in heads if _cx(h[0]) < 120 + 800]
    one = [h for h in heads if _cx(h[0]) >= 120 + 800]
    # the fixture: five ports on the wall, each primary with its tag
    assert sorted((d['text'], t['text']) for d, t, _ in wall) == [
        ('P%d' % n, "25'") for n in range(1, 6)], [(d['text'], t['text']) for d, t, _ in wall]
    assert [t['text'] for _, t, _ in one] == ["25'"], one
    bad = _faults(_wall_boxes(boxes, wall), want)
    bad += _faults(_wall_boxes(boxes, one), 'above')
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_a_return_marker_hangs_its_tag_by_the_way_the_backup_leaves_it(page):
    """Run down the columns with backups on: each primary's tag above its
    disc on the top row; each RETURN marker sits at its run's foot, where
    the backup feeds the run back up the column - so its tag hangs UNDER
    the disc, centred on it, covering nothing."""
    pg, errors = page
    boxes = _data_probe(pg, ['DWALL'], 'tl-v', backup=True)
    heads = _heads(boxes)
    prim = [h for h in heads if h[0]['text'].startswith('P')]
    ret = [h for h in heads if h[0]['text'].startswith('R')]
    assert sorted(t['text'] for _, t, _ in prim) == ["25'"] * 5, heads
    assert sorted(t['text'] for _, t, _ in ret) == ["BU 25'"] * 5, heads
    bad = _faults(_wall_boxes(boxes, prim), 'above')
    bad += _faults(_wall_boxes(boxes, ret), 'under')
    assert not bad, '\n'.join([''] + bad)
    assert errors == []


def test_a_turned_data_screen_reads_the_run_on_the_sheet(page):
    """A quarter turn on the data map: turned 90 degrees, a row run that
    goes left along the wall goes UP on the sheet - so its tags hang under
    its discs, on the page."""
    pg, errors = page
    try:
        boxes = _data_probe(pg, ['DWALL'], 'tr-h', rot=90)
        heads = _heads(boxes)
        assert sorted(d['text'] for d, _, _ in heads) == ['P%d' % n for n in range(1, 6)], heads
        bad = _faults(boxes, 'under')
        assert not bad, '\n'.join([''] + bad)
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


def test_a_data_tag_with_no_room_over_its_disc_goes_under_it(page):
    """DSHORT: the data wall on cabinets 24 px tall, a port run down each
    column (drawn as custom paths - a wall this small is one port).
    The ruling wants each tag over its head, but the heads sit on the top
    row and a tag over the disc would leave the screen - so it goes to the
    OTHER side of the disc, UNDER it, centred on it (not beside it, where
    the data map used to put it), covering nothing."""
    pg, errors = page
    boxes = _data_probe(pg, ['DSHORT'], 'custom')
    heads = _heads(boxes)
    assert sorted(d['text'] for d, _, _ in heads) == ['P%d' % n for n in range(1, 6)], heads
    top = min(e['y'] for e in _kind(boxes, 'wallEdge'))
    for d, t, _ in heads:
        # the preferred spot really is off the screen
        assert d['y'] - t['h'] < top, ('the fixture must leave no room above', d, t, top)
    bad = _faults(boxes, 'under')
    assert not bad, '\n'.join([''] + bad)
    assert errors == []
