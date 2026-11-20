"""No run on a WIRING sheet ever crosses a box (owner, 2026-11-18).

One wide screen on a two-card processor feeds eight breakout boxes, four
primaries over the wall and their four backups under it. Four boxes do not
fit one row across the sheet, so each side takes a second row - and that
row used to be centred like the first, its one box standing straight over
the first row's middle box. Its ten runs then went down through that box,
across its name, its input line and its sockets, each lying on top of the
inner box's own run to the same socket number: neither box could be read.

A box in an outer row now stands over the channel the inner row leaves
between its boxes, its runs come through that channel, and any that are
not under a socket over it turn to their sockets in the corridor between
the two rows. Where the channels cannot hold the runs, the inner row keeps
a gap open for them, or moves its last box out a row (_bwAcross). So: no
segment of any run meets a box other than its own, no run reaches its own
box before its last segment, no two runs print as one, and the turns in
the corridor cross nothing. A sheet whose boxes take one row a side is
laid out as it always was.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_wiring_stacked_boxes.py -v --browser chromium
"""

import io
import json
import os
import re

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

HERE = os.path.dirname(os.path.abspath(__file__))


def _js_consts(*names):
    """The drawing's own constants, read out of app-binder-wiring.js."""
    src = io.open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-binder-wiring.js'),
                  encoding='utf-8').read()
    out = []
    for name in names:
        m = re.search(r'\b%s\s*=\s*(-?[0-9.]+)' % name, src)
        assert m, 'app-binder-wiring.js no longer defines ' + name
        out.append(float(m.group(1)))
    return out


RUN_W, CASE_EXTRA, MARGIN, PROTO_W, MIN_BOX_GAP, LANE_STEP = _js_consts(
    'RUN_W', 'CASE_EXTRA', 'MARGIN', 'PROTO_W', 'MIN_BOX_GAP', 'LANE_STEP')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WIDE, `cols` x 7 cabinets, a port a column; a processor with `cards`
# cards, each with four fiber outputs and a 10-port breakout box on each -
# the first two boxes of a card its primaries, the last two their backups
# (redundancy by halves). Box 1 takes a card's ports 1-10, box 2 its ports
# 11-15.
SEED_JS = """async ([cols, cards]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    let proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WIDE', columns: cols, rows: 7,
                                                     cabinet_width: 256, cabinet_height: 256});
    const paths = {};
    for (let c = 0; c < cols; c++) {
        paths[String(c + 1)] = Array.from({length: 7}, (_, r) => ({col: c, row: r}));
    }
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'novastar-coex-1g',
        flowPattern: 'custom', customPortPaths: paths, customPortIndex: cols,
        portMappingMode: 'organized'});
    proj = await j('GET', '/api/project');
    const cables = (from, to) => Object.fromEntries(
        Array.from({length: to - from + 1}, (_, i) => [String(from + i), {ft: 50}]));
    let n = 0;
    const box = (cable, strand, from, to) => ({
        bidi: true, deviceId: 'novastar-cvt10', mode: 'default',
        id: 'box' + (++n), name: 'CVT ' + n,
        fiberLinks: {p1: {cable, strands: [strand]}}, portCables: cables(from, to)});
    const card = (id, s) => ({
        deviceId: 'novastar-card-mx-4x10g', fixed: false, id, mode: 'default', name: '',
        redundancyMode: 'halves',
        cvts: [box('fa', s, 1, 10), box('fa', s + 1, 11, 15),
               box('fb', s, 21, 30), box('fb', s + 1, 31, 35)]});
    const ids = ['cardA', 'cardB'].slice(0, cards);
    proj.processors = [{deviceId: 'novastar-mx2000-pro', id: 'proc1', mode: null, name: 'MX2000',
                        pairingsPerCard: true, redundancy: true,
                        slots: ids.map((id, i) => ({index: i, card: card(id, 1 + 2 * i)}))}];
    proj.fiberCables = ['fa', 'fb'].map((id, i) => ({connector: 'LC duplex', ft: 250, id,
        kind: 'tac', labels: 'colors', name: 'TAC ' + 'AB'[i], strandNames: {}, strands: 12,
        subunits: false}));
    const pins = [];
    for (let i = 0; i < cols; i++) {
        pins.push({cardId: ids[Math.floor(i / 15)], index: i, layerId: String(wall.id),
                   port: (i % 15) + 1});
    }
    proj.port_assignments = {auto: false, autoRetired: true, pins};
    proj.next_processor_seq = 2;
    await j('PUT', '/api/project', proj);
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('wiring_stack_seed');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    return {wall: wall.id};
}"""

# The screen's DATA WIRING sheet, as the binder logs it. `room`, where
# given, takes { top, side } page units off the drawing's room - a band
# over the drawing (a map sheet's view band takes 120) and a strip off
# either side - for as long as the sheet is laid out and painted.
SHEET_JS = """(opts) => {
    const app = window.app;
    const room = opts.room || null;
    const had = Object.prototype.hasOwnProperty.call(app, '_bwArea');
    const own = app._bwArea;
    if (room) {
        app._bwArea = function (book) {
            const a = own.call(this, book);
            return { ...a, half: { x: a.half.x + room.side, y: a.half.y + room.top,
                                   w: a.half.w - 2 * room.side, h: a.half.h - room.top } };
        };
    }
    try {
        const plan = app.planBinder(opts);
        const idx = plan.findIndex(p => /data wiring/i.test(p.title || ''));
        if (idx < 0) return { missing: true, plan: plan.map(p => p.title) };
        const r = app.renderBinderPage(opts, idx);
        return { halves: (r.wiring || {}).halves || [], title: plan[idx].title };
    } finally {
        if (had) app._bwArea = own; else delete app._bwArea;
    }
}"""

# _bwAcross on boxes made up for it: rows of { w, sockets } per side.
ACROSS_JS = """([rows, availW]) => {
    const app = window.app;
    const mk = (s) => rows[s].map((row, ri) => row.map((b, i) => ({
        key: `${s}${ri}.${i}`, w: b.w, lead: 25.5, pitch: 21, count: 10,
        sockets: b.sockets.map(n => ({ id: `${s}${ri}.${i}#${n}`, n })), target: b.target == null ? null : b.target })));
    const out = app._bwAcross({ top: mk('top'), bottom: mk('bottom') }, availW);
    return { x: Object.fromEntries(out.x), via: Object.fromEntries(out.via), log: out.log, moved: out.moved,
             rows: { top: out.rows.top.map(r => r.map(b => ({ key: b.key, w: b.w }))),
                     bottom: out.rows.bottom.map(r => r.map(b => ({ key: b.key, w: b.w }))) },
             corridor: out.corridor };
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
        'titleBlock': True}
AVAIL_W = PROTO_W - 2 * MARGIN


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    # a real save dialog never pops from a test
    context.route('**/api/native-dialog**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"ok": false, "cancelled": true}'))
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(SEED_JS, [30, 2])
    pg.wait_for_timeout(800)
    yield pg, errors
    context.close()


def _half(pg, palette='colour', view='front', **more):
    out = pg.evaluate(SHEET_JS, {**OPTS, 'palette': palette, 'view': view, **more})
    assert not out.get('missing'), out
    halves = out['halves']
    assert len(halves) == 1, out
    return halves[0]


def _segments(run):
    pts = run['points']
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _meets(a, b, box, pad):
    """Does the segment a-b, as wide as its casing (pad either side), reach
    inside the box?"""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return (x1 + pad > box['x'] + 0.01 and x0 - pad < box['x'] + box['w'] - 0.01
            and y1 + pad > box['y'] + 0.01 and y0 - pad < box['y'] + box['h'] - 0.01)


def _crossings_through_boxes(h):
    pad = (RUN_W + CASE_EXTRA) / 2 * h['scale']
    bad = []
    for r in h['runs']:
        segs = _segments(r)
        for i, (a, b) in enumerate(segs):
            for box in h['blocks']:
                own = box['title'] == r['device']
                # a run comes into its own box on its last segment, and only there
                if own and i == len(segs) - 1:
                    continue
                if _meets(a, b, box, pad):
                    bad.append((r['from'], r['device'], 'own box early' if own else box['title'], i))
    return bad


def _on_top_of_each_other(h):
    """Two runs whose parallel segments share a stretch closer than one
    run's pen and casing: they print as one line."""
    pen = (RUN_W + CASE_EXTRA) * h['scale']
    segs = []
    for ri, r in enumerate(h['runs']):
        for a, b in _segments(r):
            if abs(a[0] - b[0]) < 0.01:
                segs.append((ri, 0, a[0], min(a[1], b[1]), max(a[1], b[1])))
            elif abs(a[1] - b[1]) < 0.01:
                segs.append((ri, 1, a[1], min(a[0], b[0]), max(a[0], b[0])))
    out = []
    for i, s in enumerate(segs):
        for t in segs[i + 1:]:
            if s[0] == t[0] or s[1] != t[1]:
                continue
            if abs(s[2] - t[2]) < pen and min(s[4], t[4]) - max(s[3], t[3]) > 0.5:
                out.append((h['runs'][s[0]]['from'], h['runs'][t[0]]['from'], round(abs(s[2] - t[2]), 2)))
    return out


def _cuts(a, b, c, d):
    """A horizontal and a vertical meeting strictly inside both."""
    def hv(p, q):
        return 'h' if abs(p[1] - q[1]) < 0.01 else 'v' if abs(p[0] - q[0]) < 0.01 else 'x'
    k1, k2 = hv(a, b), hv(c, d)
    if {k1, k2} != {'h', 'v'}:
        return False
    (h0, h1), (v0, v1) = ((a, b), (c, d)) if k1 == 'h' else ((c, d), (a, b))
    x, y = v0[0], h0[1]
    return (min(h0[0], h1[0]) + 0.01 < x < max(h0[0], h1[0]) - 0.01
            and min(v0[1], v1[1]) + 0.01 < y < max(v0[1], v1[1]) - 0.01)


# Where the runs go hangs on the room the sheet gives the drawing: its
# paper, the title block, the side it is seen from, and anything else
# drawn over it. Two runs printed as one on tabloid with the title block
# off, on letter, A3 and ARCH C (2026-11-20) - a stub up out of the wall
# lay along another run's drop into its socket - while tabloid with the
# block on, the one sheet this guarded, happened to be clear. So every
# paper, the block on and off, front and rear, and each with the room a
# view band over the drawing (120 high) and the stage strips beside it
# (48 a side) would leave.
ROOMS = {'whole': None, 'banded': {'top': 120, 'side': 48}, 'band only': {'top': 120, 'side': 0}}


@pytest.mark.parametrize('room', list(ROOMS))
@pytest.mark.parametrize('view', ['front', 'rear'])
@pytest.mark.parametrize('block', [True, False], ids=['block', 'no block'])
@pytest.mark.parametrize('sheet', ['letter', 'tabloid', 'a3', 'archc'])
def test_no_run_crosses_a_box_with_four_boxes_a_side(page, sheet, block, view, room):
    _no_run_crosses_a_box(page, 'colour', view, sheet=sheet, titleBlock=block, room=ROOMS[room])


@pytest.mark.parametrize('view', ['front', 'rear'])
def test_no_run_crosses_a_box_on_the_press(page, view):
    _no_run_crosses_a_box(page, 'printer', view)


def _no_run_crosses_a_box(page, palette, view, **more):
    pg, errors = page
    h = _half(pg, palette, view, **more)
    sides = [b['side'] for b in h['blocks']]
    assert sides.count('top') >= 4 and sides.count('bottom') >= 4, sides
    # the layout this guards: a side whose boxes take a second row
    assert h['rowsTop'] >= 2 and h['rowsBottom'] >= 2, (h['rowsTop'], h['rowsBottom'])
    assert len(h['runs']) == 60, len(h['runs'])
    for i, a in enumerate(h['blocks']):
        for b in h['blocks'][i + 1:]:
            assert not _meets((a['x'], a['y']), (a['x'] + a['w'], a['y'] + a['h']), b, 0), (
                'two boxes overprint', a['title'], b['title'])
    bad = _crossings_through_boxes(h)
    assert bad == [], ('a run crosses a box', len(bad), bad[:6])
    assert _on_top_of_each_other(h) == [], ('two runs print as one', _on_top_of_each_other(h)[:6])
    assert errors == []


def test_an_outer_box_stands_over_a_channel_of_the_inner_row(page):
    """The outer row's box is not centred over the inner row's middle box:
    some of its sockets stand clear of every inner box, and the runs to
    those go straight in. The log names the gap each of its runs took."""
    pg, _ = page
    h = _half(pg)
    for side in ('top', 'bottom'):
        inner = [b for b in h['blocks'] if b['side'] == side and b['row'] == 0]
        outer = [b for b in h['blocks'] if b['side'] == side and b['row'] > 0]
        assert outer, side
        for b in outer:
            clear = [s for s in b['sockets'] if s['state'] != 'free'
                     and not any(i['x'] <= s['x'] <= i['x'] + i['w'] for i in inner)]
            assert clear, ('every socket of an outer box stands over an inner box', b['title'])
            runs = [r for r in h['runs'] if r['device'] == b['title']]
            assert runs and all(r['through'] and r['gap'] for r in runs), runs[:2]
            for r in runs:
                g0, g1 = r['gap']
                assert not any(g0 < i['x'] + i['w'] and i['x'] < g1 for i in inner), (
                    'a gap a run took stands over an inner box', r['from'], r['gap'])
    assert h['across'] and h['across']['corridor']['top'][1] > 0, h['across']


def _corridor(h, r):
    """The band between a run's outer box and the row inside it."""
    box = next(b for b in h['blocks'] if b['title'] == r['device'])
    inner = [b for b in h['blocks'] if b['side'] == box['side'] and b['row'] == box['row'] - 1]
    if box['side'] == 'top':
        return box['y'] + box['h'], min(b['y'] for b in inner)
    return max(b['y'] + b['h'] for b in inner), box['y']


def test_the_turns_in_the_corridor_cross_nothing(page):
    """Seen from the back the screen's ports run the other way to the
    sockets, so the runs to an outer box turn to their sockets between the
    two rows. Those turns nest: nothing crosses anything in the corridor."""
    pg, _ = page
    h = _half(pg, view='rear')
    through = [r for r in h['runs'] if r['through']]
    assert through, 'no run went through a gap'
    turned = []
    bad = []
    for r in through:
        lo, hi = _corridor(h, r)
        for a, b in _segments(r):
            if abs(a[1] - b[1]) < 0.01 and lo < a[1] < hi and abs(a[0] - b[0]) > 0.01:
                turned.append(r['from'])
            for o in h['runs']:
                if o is r:
                    continue
                for c, d in _segments(o):
                    if not _cuts(a, b, c, d):
                        continue
                    y = a[1] if abs(a[1] - b[1]) < 0.01 else c[1]
                    if lo - 0.01 < y < hi + 0.01:
                        bad.append((r['from'], o['from'], round(y, 1)))
    assert turned, 'no run turned in a corridor'
    assert bad == [], bad[:6]


# _bwLanes on spans made up for it: each { lo, hi, up (the line up from
# the wall), on (the line on to its socket) }; a span whose line up stands
# on another's line on must take the lane nearer the wall.
LANES_JS = """([spans, rule]) => {
    const app = window.app;
    const items = spans.map(s => ({ ...s }));
    const n = app._bwLanes(items, rule ? (a, b) => Math.abs(a.up - b.on) < 1 : null);
    return { n, lanes: items.map(i => i.lane) };
}"""


def test_a_line_up_from_the_wall_never_runs_on_up_another_runs_drop(page):
    """Two runs whose stretches along the lanes do not meet share a lane,
    as they always did - but where one's line up from the wall stands on
    the other's line down from its socket, the first turns on a lane
    nearer the wall, so the two never share a stretch of that line."""
    pg, _ = page
    # The first's stub comes up at 100, where the third's drop comes down at
    # 100.5. Their stretches along the lane do not meet, so they used to
    # share a lane - or, handed out the other way, the first's stub went on
    # up past the third's lane along the third's drop.
    spans =[{'lo': 0, 'hi': 100, 'up': 100, 'on': 0},
             {'lo': 200, 'hi': 300, 'up': 300, 'on': 200},
             {'lo': 100.5, 'hi': 160, 'up': 160, 'on': 100.5}]
    plain = pg.evaluate(LANES_JS, [spans, False])
    assert plain == {'n': 1, 'lanes': [0, 0, 0]}, plain
    # with the rule: the third's stub (at 160) stands on nothing, but the
    # first's stub (at 100) stands on the third's drop (at 100.5)
    ruled = pg.evaluate(LANES_JS, [spans, True])
    assert ruled['lanes'][0] < ruled['lanes'][2], ruled
    assert ruled['lanes'][1] == 0, ruled
    # a ring (each one's stub on the other's drop) still gives every span a lane
    ring = [{'lo': 0, 'hi': 50, 'up': 0, 'on': 50}, {'lo': 50.2, 'hi': 90, 'up': 50, 'on': 0}]
    out = pg.evaluate(LANES_JS, [ring, True])
    assert len(out['lanes']) == 2 and all(isinstance(v, int) for v in out['lanes']), out


def test_the_same_sheet_twice_draws_the_same(page):
    pg, _ = page
    a, b = _half(pg), _half(pg)
    assert json.dumps(a['runs'], sort_keys=True) == json.dumps(b['runs'], sort_keys=True)
    assert json.dumps(a['blocks'], sort_keys=True) == json.dumps(b['blocks'], sort_keys=True)


def _box(w, n=10, target=None):
    return {'w': w, 'sockets': list(range(1, n + 1)), 'target': target}


def _inside_inner(out, rows, side):
    """Every place a run to an outer row was given that stands on a box of
    a row inside it (with a lane of air)."""
    bad = []
    for key, v in out['via'].items():
        if v['s'] != side:
            continue
        for j in range(v['ri']):
            for b in out['rows'][side][j]:
                x0 = out['x'][b['key']]
                if x0 - LANE_STEP + 0.01 < v['x'] < x0 + b['w'] + LANE_STEP - 0.01:
                    bad.append((key, round(v['x'], 2), b['key']))
    return bad


def test_a_crowded_inner_row_keeps_a_gap_or_moves_a_box_out(page):
    """Three wide boxes leave the inner row gaps a few runs wide; the box
    over them has ten runs. The inner row makes room - here its last box
    moves out a row - and the step is logged; every run still has a place
    clear of every inner box."""
    pg, _ = page
    rows = {'top': [[_box(305), _box(305), _box(305)], [_box(240, target=500)]], 'bottom': []}
    out = pg.evaluate(ACROSS_JS, [rows, AVAIL_W])
    steps = [e['step'] for e in out['log']]
    assert 'gap kept' in steps or 'moved out a row' in steps, out['log']
    assert 'no gap' not in steps, out['log']
    assert out['moved'] and len(out['rows']['top'][0]) == 2, out['rows']
    # every socket of the outer rows has a place in a gap
    want = sum(10 for r in out['rows']['top'][1:] for _b in r)
    assert len([v for v in out['via'].values() if v['s'] == 'top']) == want
    assert _inside_inner(out, out['rows'], 'top') == []
    # and no two boxes of a row overprint
    for row in out['rows']['top']:
        xs = sorted((out['x'][b['key']], b['w']) for b in row)
        for (x0, w0), (x1, _w1) in zip(xs, xs[1:]):
            assert x0 + w0 + MIN_BOX_GAP - 0.01 <= x1, xs


def test_a_side_of_three_rows_gives_every_run_its_own_place(page):
    """A third row's runs pass the first two rows' gaps beside the second
    row's runs, never on the same line. The second row's box stands at the
    sheet's left edge, so most of its runs go up the gap to its right -
    the very gap the third row's box stands over."""
    pg, _ = page
    rows = {'top': [[_box(240), _box(240), _box(240)], [_box(240, target=20)], [_box(240, target=320)]],
            'bottom': []}
    out = pg.evaluate(ACROSS_JS, [rows, AVAIL_W])
    assert 'no gap' not in [e['step'] for e in out['log']], out['log']
    vs = [v for v in out['via'].values() if v['s'] == 'top']
    assert {v['ri'] for v in vs} == {1, 2}, vs
    second = [v['x'] for v in vs if v['ri'] == 1]
    third = [v['x'] for v in vs if v['ri'] == 2]
    assert len(second) == 10 and len(third) == 10
    close = [(a, b) for a in third for b in second if abs(a - b) < LANE_STEP - 0.02]
    assert close == [], close[:4]
    assert _inside_inner(out, out['rows'], 'top') == []


def test_a_one_row_data_sheet_is_laid_out_as_before(page):
    """One card - four boxes, two a side - fits one row a side: no run goes
    through a gap, no corridor is kept, and the boxes are spread across the
    width exactly as they always were."""
    pg, errors = page
    pg.evaluate(SEED_JS, [15, 1])
    pg.wait_for_timeout(500)
    try:
        h = _half(pg)
        assert h['rowsTop'] <= 1 and h['rowsBottom'] <= 1, (h['rowsTop'], h['rowsBottom'])
        assert h['across'] is None, h['across']
        assert not any(r['through'] for r in h['runs'])
        s = h['scale']
        ax = h['area']['x']
        blocks = sorted(h['blocks'], key=lambda b: b['x'])
        # one row for both sides where every box fits it, else a row a side
        together = sum(b['w'] / s for b in blocks) + MIN_BOX_GAP * (len(blocks) - 1) <= AVAIL_W
        for side in (['both'] if together else ['top', 'bottom']):
            row = [b for b in blocks if side == 'both' or b['side'] == side]
            if not row:
                continue
            ws = [b['w'] / s for b in row]
            gp = max(MIN_BOX_GAP, (AVAIL_W - sum(ws)) / (len(ws) - 1)) if len(ws) > 1 else 0
            x = MARGIN + max(0, (AVAIL_W - sum(ws) - gp * (len(ws) - 1)) / 2)
            for b, w in zip(row, ws):
                assert abs((b['x'] - ax) / s - x) < 0.01, (side, b['title'], (b['x'] - ax) / s, x)
                x += w + gp
        assert _crossings_through_boxes(h) == []
        assert errors == []
    finally:
        pg.evaluate(SEED_JS, [30, 2])
        pg.wait_for_timeout(500)
