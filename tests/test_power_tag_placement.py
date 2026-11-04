"""Where a power head's cable tags hang: by the way its run leaves the disc.

The owner's ruling (2026-09-25), chosen from rendered options on his show:
the POWER map's cable tag (the circuit's cable, "10' TRUE1") and the
splitter pill stacked with it ("3fer" / "2fer") go by the direction the
circuit's run LEAVES its label disc -

  - the run goes DOWN (it starts at the top)    -> the tags ABOVE the disc;
  - the run goes UP (it starts at the bottom)   -> the tags UNDER the disc;
  - the run goes RIGHT, or LEFT                 -> the tags ABOVE the disc;
  - a circuit of one cabinet has no step        -> ABOVE;

centred on the disc's x, the pill CENTRED on the tag ("3fer etc needs to
be centered under the TRUE1 extension"). The splitter pill is always the
one next to the disc, in the row of every other splitter pill on the
screen (the owner, 2026-11-03): above the disc the column reads tag, pill,
disc and under it disc, pill, tag. The direction is the run's first step AS DRAWN: on a
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

from conftest import open_app  # noqa: E402

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
            // A US circuit packs to 80 percent of its breaker (2026-10-22): the amps here are x 1.25, so a circuit carries what this wall was laid out for.
            panel_weight: 20, weight_unit: 'kg', panelWatts: 100, powerVoltage: 100, powerAmperage: 18.75,
            powerBreakoutType: 'soca-true1',
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: dataFlow ? pattern : 'tl-h', portMappingMode: 'organized',
            powerOrganized: true, powerMaximize: false,
            powerFlowPattern: dataFlow ? 'tl-h' : pattern, rotation: rot || 0,
            powerSplitters: { enabled: true, maxWays: 3, manual: { merge: [], split: [] } },
            // the cables ride a fed multi: a circuit no distro feeds draws
            // no extension (2026-10-20)
            powerSocaDistro: { 1: 'd1' }, powerSocaNames: { 1: 'S1' },
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
        // ONE SIDE PER SCREEN (2026-10-30). MIXED: seven columns run down
        // from the top row on cabinets 108 tall - circuit 1 a 3fer with a
        // length (tag and pill, too tall for the room over its disc),
        // circuit 2 a 3fer with no length (the pill alone fits over it),
        // circuit 3 one column with a length (the tag alone fits over it).
        MIXED: { id: 7, name: 'MIXED', columns: 7, rows: 5, offset_x: 0, offset_y: 0,
                 cabinet_height: 108, powerCircuitCables: { 1: { ft: 10 }, 3: { ft: 25 } } },
        // DEV: hand-drawn circuits on cabinets 40 tall, no splitters. 1 and
        // 2 run down from the top row (no room over their discs), 3 runs
        // down from the middle row (room both sides), 4 runs right along
        // the bottom row (no room under its disc) - the one head that
        // cannot hang where the rest do.
        DEV: { id: 8, name: 'DEV', columns: 6, rows: 3, offset_x: 0, offset_y: 0,
               cabinet_height: 40, powerFlowPattern: 'custom', powerCustomIndex: 5,
               powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } },
               powerCircuitCables: { 1: { ft: 10 }, 2: { ft: 10 }, 3: { ft: 10 }, 4: { ft: 10 } },
               powerCustomPaths: {
                   1: [{ row: 0, col: 0 }, { row: 1, col: 0 }, { row: 2, col: 0 }],
                   2: [{ row: 0, col: 1 }, { row: 1, col: 1 }, { row: 2, col: 1 }],
                   3: [{ row: 1, col: 2 }, { row: 2, col: 2 }],
                   4: [{ row: 2, col: 3 }, { row: 2, col: 4 }, { row: 2, col: 5 }] } },
        // DMIX: the data map's twin - ports 1 and 2 run down from the top
        // row, port 3 runs right along the middle row (room both sides).
        DMIX: { id: 9, name: 'DMIX', columns: 4, rows: 3, offset_x: 0, offset_y: 0,
                cabinet_height: 40, dataFlow: true, showDataCableTags: true,
                dataFlowLabelSize: 14,
                customPortPaths: {
                    1: [{ row: 0, col: 0 }, { row: 1, col: 0 }, { row: 2, col: 0 }],
                    2: [{ row: 0, col: 1 }, { row: 1, col: 1 }, { row: 2, col: 1 }],
                    3: [{ row: 1, col: 2 }, { row: 1, col: 3 }] } },
        // PEDGE (QA 1.6.0): three hand-drawn circuits, each one row run
        // right from column 0, on cabinets 40 wide and 80 tall, so a pill
        // centred on its disc is slid against the wall's left edge.
        PEDGE: { id: 11, name: 'PEDGE', columns: 4, rows: 3, offset_x: 0, offset_y: 0,
                 cabinet_width: 40, cabinet_height: 80, powerFlowPattern: 'custom', powerCustomIndex: 4,
                 powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } },
                 powerCircuitCables: { 1: { ft: 10 }, 2: { ft: 10 }, 3: { ft: 10 } },
                 powerCustomPaths: Object.fromEntries([1, 2, 3].map(n =>
                     [n, [0, 1, 2, 3].map(col => ({ row: n - 1, col }))])) },
    };
    const layers = walls.map(n => screen(all[n]));
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', { layers, groups: [], canvases: [], rack: [],
        distros: [{ id: 'd1', name: 'PD', ratingA: 200, system: '120/208', voltage: 208, phase: 3 }] });
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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    # The app and its first project load, not a fixed 2 s: under load
    # the first load can land after the sleep (conftest.open_app).
    open_app(pg, e2e_server)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
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
            # the pill centred on the tag, a hair apart, between the tag
            # and the disc: beneath the tag above the disc, over it under
            # the disc
            if abs(_cx(p) - _cx(t)) > HAIR:
                bad.append('%s: pill %s centre x %.1f, tag centre x %.1f' % (name, p['text'], _cx(p), _cx(t)))
            if want == 'above':
                gap = p['y'] - (t['y'] + t['h'])
                where = 'beneath'
            else:
                gap = t['y'] - (p['y'] + p['h'])
                where = 'over'
            if not (-HAIR <= gap < 6):
                bad.append('%s: pill %s is not directly %s the tag (gap %.1f)' % (name, p['text'], where, gap))
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
        ("10' TRUE1", '3fer'), ("25' TRUE1", '2fer')], [(d['text'], t['text'], p and p['text']) for d, t, p in wall]
    assert [(t['text'], p) for _, t, p in one] == [("10' TRUE1", None)], one
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
    it, the pill next to the disc and the tag beneath it (2026-11-03),
    covering nothing."""
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
        if p['y'] < d['y'] + d['h'] - HAIR:
            bad.append('%s: pill top %.1f is not under the disc (bottom %.1f)'
                       % (name, p['y'], d['y'] + d['h']))
        if abs(_cx(t) - _cx(d)) > HAIR:
            bad.append('%s: tag centre x %.1f, disc centre x %.1f' % (name, _cx(t), _cx(d)))
        if abs(_cx(p) - _cx(t)) > HAIR:
            bad.append('%s: pill centre x %.1f, tag centre x %.1f' % (name, _cx(p), _cx(t)))
        if not (-HAIR <= t['y'] - (p['y'] + p['h']) < 6):
            bad.append('%s: tag not directly beneath the pill' % name)
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


# ONE SIDE PER SCREEN (the owner, 2026-10-30, on a 16 x 5 wall run down
# from its top row in 3fers): placed head by head, the heads whose tag and
# 3fer stack was too tall for the room over the disc went under it while
# the heads with one pill stayed over it - "all the cable lengths should
# realistically be on the same side so that they match - only in
# extenuating circumstances should they be different". The side is picked
# once for the screen: the run's side when every head fits there, else the
# other side when every head fits there, else the side most heads fit, and
# only a head that cannot fit there goes elsewhere. A 3fer with no length
# takes the cable tag's slot on that same side.

def _side(b, d):
    if b['y'] + b['h'] <= d['y'] + HAIR:
        return 'above'
    if b['y'] >= d['y'] + d['h'] - HAIR:
        return 'under'
    return 'beside'


def _stacks(boxes):
    """Every disc wearing a cable tag or a splitter pill, left to right:
    (disc, [(kind, text, side of the disc)])."""
    discs = _kind(boxes, 'disc')
    near = lambda b: min(discs, key=lambda d: _gap(b, d))
    worn = {}
    for b in _kind(boxes, 'tag') + _kind(boxes, 'gang'):
        d = near(b)
        worn.setdefault(id(d), (d, []))[1].append((b['kind'], b['text'], _side(b, d)))
    return sorted(worn.values(), key=lambda v: _cx(v[0]))


def _covers(boxes):
    """Every disc or pill a tag or pill covers, as lines."""
    bad = []
    ink = _kind(boxes, 'tag') + _kind(boxes, 'gang')
    for b in ink:
        for d in _kind(boxes, 'disc'):
            if _meets_disc(b, d):
                bad.append('%s %r covers disc %s' % (b['kind'], b['text'], d['text']))
        for o in ink:
            if o is not b and _over(b, o):
                bad.append('%s %r covers %s %r' % (b['kind'], b['text'], o['kind'], o['text']))
    return bad


def test_every_head_of_a_screen_hangs_its_tags_on_one_side(page):
    """MIXED, run down from the top row: the 3fer with a length has no room
    for its tag and pill over its disc, while the 3fer with no length and
    the lone 25' tag would each fit there. Every head hangs under its disc
    - the pill next to the disc, the tag centred under it; the lone 3fer
    pill in the same row as the stacked one (the owner, 2026-11-03: the
    splitter pills line up) - covering nothing."""
    pg, errors = page
    try:
        boxes = _probe(pg, ['MIXED'], 'tl-v')
        stacks = _stacks(boxes)
        shape = [sorted((k, t) for k, t, _ in worn) for _, worn in stacks]
        assert shape == [[('gang', '3fer'), ('tag', "10' TRUE1")], [('gang', '3fer')],
                         [('tag', "25' TRUE1")]], shape
        (d1, _), (d2, _), (d3, _) = stacks
        tag1 = [b for b in _kind(boxes, 'tag') if b['text'] == "10' TRUE1"][0]
        pill2 = [b for b in _kind(boxes, 'gang') if _gap(b, d2) < 20][0]
        # the fixture: the first head's stack cannot stand over its disc,
        # the other two heads' single pills could
        top = min(e['y'] for e in _kind(boxes, 'wallEdge'))
        stand = 14 * 0.6
        assert d1['y'] - top < stand + tag1['h'] + 1 + pill2['h'], ('no room for the stack over head 1', d1, top)
        assert d2['y'] - top >= stand + pill2['h'], ('room for one pill over head 2', d2, top)
        assert d3['y'] - top >= stand + tag1['h'], ('room for one tag over head 3', d3, top)
        sides = [(d['text'], sorted(set(s for _, _, s in worn))) for d, worn in stacks]
        assert all(s == ['under'] for _, s in sides), sides
        bad = _faults(_wall_boxes(boxes, _heads(boxes)), 'under') + _covers(boxes)
        # the lone pill stands where the stacked one does: centred under
        # its disc, the stand-off a pill keeps, in the same row; the lone
        # tag (head 3) stands where a tag with no pill does
        pill1 = [b for b in _kind(boxes, 'gang') if _gap(b, d1) < 20][0]
        tag3 = [b for b in _kind(boxes, 'tag') if b['text'] == "25' TRUE1"][0]
        if abs(_cx(pill2) - _cx(d2)) > HAIR:
            bad.append('lone 3fer centre x %.1f, disc %.1f' % (_cx(pill2), _cx(d2)))
        p1 = pill1['y'] - (d1['y'] + d1['h'])
        p2 = pill2['y'] - (d2['y'] + d2['h'])
        t3 = tag3['y'] - (d3['y'] + d3['h'])
        if abs(p2 - p1) > HAIR:
            bad.append('lone 3fer stands %.1f off its disc, the stacked 3fer %.1f' % (p2, p1))
        if abs(t3 - p1) > HAIR:
            bad.append('lone tag stands %.1f off its disc, the stacked 3fer %.1f' % (t3, p1))
        if tag1['y'] < pill1['y'] + pill1['h'] - HAIR:
            bad.append("the 10' tag is not beneath its 3fer")
        assert not bad, '\n'.join([''] + bad)
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


def test_only_the_head_that_cannot_fit_leaves_the_screen_s_side(page):
    """DEV, hand-drawn: heads 1 and 2 on the top row (no room over them),
    head 3 on the middle row (room both sides), head 4 on the bottom row
    running right (no room under it). Under fits three, over fits two:
    heads 1 to 3 hang under, and head 4 alone - the extenuating
    circumstance - goes over its disc. Head 3 used to hang over."""
    pg, errors = page
    try:
        boxes = _probe(pg, ['DEV'], 'custom')
        stacks = _stacks(boxes)
        sides = [(d['text'], [s for _, _, s in worn]) for d, worn in stacks]
        assert [s for _, s in sides] == [['under'], ['under'], ['under'], ['above']], sides
        assert all(t == "10' TRUE1" for _, worn in stacks for _, t, _ in worn), stacks
        bad = _covers(boxes)
        assert not bad, '\n'.join([''] + bad)
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


def test_a_data_screen_hangs_its_tags_on_one_side(page):
    """DMIX on the data map: ports 1 and 2 run down from the top row (no
    room over their discs), port 3 runs right along the middle row and has
    room either side. All three tags hang under their markers."""
    pg, errors = page
    try:
        boxes = _data_probe(pg, ['DMIX'], 'custom')
        heads = _heads(boxes)
        assert sorted(d['text'] for d, _, _ in heads) == ['P1', 'P2', 'P3'], heads
        p3, t3 = [(d, t) for d, t, _ in heads if d['text'] == 'P3'][0]
        top = min(e['y'] for e in _kind(boxes, 'wallEdge'))
        assert p3['y'] - top >= 14 * 0.6 + t3['h'], ('room over port 3', p3, top)
        bad = _faults(boxes, 'under')
        assert not bad, '\n'.join([''] + bad)
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


# The width of a pill's rim (canvas-power _tagRim): the tag's text is 85%
# of the label size, the rim a tenth of that; half of it is stroked
# outside the pill's box.
def _rim(label_size=14):
    return max(1, max(8, label_size * 0.85) * 0.1)


def test_a_tag_slid_to_the_wall_edge_keeps_its_rim_inside(page):
    """PEDGE: a pill centred under its disc on cabinets 40 wide slides
    against the wall's left edge - and stops its rim's width short of it,
    so no ink prints past the wall (QA 1.6.0)."""
    pg, errors = page
    try:
        boxes = _probe(pg, ['PEDGE'], 'custom')
        tags = _kind(boxes, 'tag')
        assert tags, boxes
        left, right = 120, 120 + 4 * 40
        half = _rim() / 2
        for t in tags:
            assert t['x'] - half >= left - 0.01 and t['x'] + t['w'] + half <= right + 0.01, (t, left, right)
        # the fixture: at least one pill is pressed against the edge
        assert min(t['x'] for t in tags) - half <= left + 0.5, tags
    finally:
        pg.evaluate(BUILD_JS, [['WALL'], 'tl-h', 0])
    assert errors == []


def test_a_stacked_pill_clears_its_tags_rim(page):
    """A 2fer / 3fer stacked under its cable tag: the two rims, each half
    outside its pill's box, used to touch - the 2fer read as printed into
    its TRUE1 (QA 1.6.0). The gap between the boxes now holds both rims
    and a hair."""
    pg, errors = page
    boxes = _probe(pg, ['WALL'], 'tl-v')
    stacked = [(t, p) for _, t, p in _heads(boxes) if p]
    assert len(stacked) == 2, stacked
    for t, p in stacked:
        gap = p['y'] - (t['y'] + t['h'])
        assert gap >= _rim() + 1 - 0.01, (t['text'], p['text'], gap)
    assert errors == []


# A 2fer / 3fer pill with NO length tag sits where the screen's other heads
# sit (the owner's ruling, 2026-11-03, on a return wall: three heads hung
# their TRUE1 tag and 2fer pill left of the disc, the fourth - a lone
# "2fer · OVER" - stood over its disc across its upper leg's run line: "It
# needs to go to the left like the others"). The heads here are placed
# through placeTagHeads directly, in the page frame: four discs down the
# wall's right edge, so the tagged heads can only hang left; the lone
# pill's own leg runs right over its disc, where the ruled side (above)
# would put it.
LONE_JS = """([direction]) => {
    const r = window.canvasRenderer;
    const bounds = { left: 0, top: 0, right: 600, bottom: 600 };
    const disc = (y) => ({ x: 560, y, r: 40 });
    // three tagged heads packed down the edge (no room over or under
    // them), a fourth disc that is no head, then the lone pill's head
    const ds = [disc(60), disc(150), disc(240), disc(330), disc(500)];
    const head = (d, text) => ({ text, nfer: text ? '2fer' : '2fer · OVER', own: d,
        prefer: 'above', run: direction, line: { x: d.x, y: d.y },
        segs: [[0, d.y - 70, d.x, d.y - 70]] });
    const heads = [head(ds[0], "25' TRUE1"), head(ds[1], "10' TRUE1"),
                   head(ds[2], "6' TRUE1"), head(ds[4], null)];
    const out = r.placeTagHeads(heads, 20, bounds, ds, [], null);
    return out.map(o => ({ tag: o.tag && o.tag.opts.side, pill: o.pill && o.pill.opts.side,
                           rect: o.pill && { x: o.pill.rect.x, y: o.pill.rect.y,
                                             w: o.pill.rect.w, h: o.pill.rect.h } }));
}"""


@pytest.mark.parametrize('direction', ['left', 'up', 'down'])
def test_a_lone_splitter_pill_sits_where_the_other_heads_sit(page, direction):
    pg, errors = page
    out = pg.evaluate(LONE_JS, [direction])
    assert [o['tag'] for o in out[:3]] == ['left'] * 3, out
    lone = out[3]
    assert lone['tag'] is None and lone['pill'] == 'left', out
    r = lone['rect']
    # beside its disc, and off its leg's line (y 430)
    assert r['x'] + r['w'] <= 560 - 40 + 0.01, out
    assert not (r['y'] <= 430 <= r['y'] + r['h']), out
    assert errors == []
