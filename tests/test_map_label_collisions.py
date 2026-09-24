"""The screen map must never write on top of itself.

A screen map reaches a binder sheet as ONE BITMAP. Its multi band pills,
its own circuit ruler (L1, L2, L4...), its port / circuit label discs, its
cable tags ("15' True1") and its 2fer pills are PIXELS INSIDE THAT IMAGE,
not ops in the binder's display list - on the Kelly power sheet the PDF
carries one /Image XObject and the string "L1" is not text in it, while
the table strings are. So no audit of the binder's ops can see the map
colliding with itself, and every one of these faults shipped:

  1. a leg tick of the map's OWN circuit ruler ran through the multi band
     pill, because the pill straddled the very line the ruler hangs from -
     "S1-1 · 250 · 65.8A" read "S1-4" on the user's export;
  2. the 2fer pills sat ON the wall's bottom edge rather than clear of it;
  3. two cable tags, each of them clear of every label DISC and neither
     aware of the other, printed straight through one another (Kelly,
     SL · POWER: "5' True1" over "10' True1", 185 x 51 pixels of the map).

canvas.js keeps a LABEL REGISTRY for exactly this: set
`canvasRenderer.labelProbe` for ONE render - startLabelProbe() /
endLabelProbe(), the same one-flag-for-one-render shape hideScreenNames
and printerMode use - and every disc, cable tag, gang tag, band pill,
ruler tick, ruler label and wall edge the map draws lands in it as
{ kind, text, x, y, w, h } IN THE BITMAP'S OWN PIXELS. These tests read
that registry off real screens and hold the map to it.

The two real shows are frozen in the git-ignored tests/fixtures-local
(conftest.private_fixture) and SKIPPED when absent - they are never
committed, so CI skips them; each env var overrides its file:
    LRD_KELLY_LIVE_JSON   kelly-live-fixture.json  (22x7 and 9x6 walls)
    LRD_PULL_SMOKE_JSON   experts-only-fixture.json

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_map_label_collisions.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import SEED_JS, _SHOW_JSON, SCRATCH_FIXTURE  # noqa: E402
from test_binder_wiring import LOAD_JS  # noqa: E402
from conftest import private_fixture, private_fixture_missing  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Kelly Clarkson as the user exported her: the show that produced all
# three faults. Frozen beside the Experts Only fixture.
KELLY_LIVE = private_fixture('kelly-live-fixture.json', 'LRD_KELLY_LIVE_JSON')

# A HAIR, in the map bitmap's own pixels. The maps these tests read are
# 3000-4300 pixels across, so a pixel of overlap is a rounding artefact of
# a rim's half width and nothing a reader could see; two pixels is ink on
# ink.
HAIR = 1.0

# Every kind the registry records. 'wallEdge' is a line (zero extent on
# the axis it runs along), the rest are boxes of ink.
INK = ('disc', 'tag', 'gang', 'band', 'rulerTick', 'rulerLabel')
PILLS = ('band', 'gang', 'tag')
# What is held clear of the wall's own edge lines: every pill, and the
# ruler's L labels.
OFF_THE_EDGE = PILLS + ('rulerLabel',)

# Every sheet that draws a screen's map: its Power and Data sheets, and its
# Power Wiring and Data Wiring sheets - each of those one side on a whole
# page, so the wall there is drawn BIGGER than on any other sheet, which is
# exactly when a map starts to write on top of itself.
MAP_KINDS = ('power', 'data', 'wiring')

PROBE_JS = """([opts, kinds]) => {
    const app = window.app, r = window.canvasRenderer;
    const plan = app.planBinder(opts);
    const out = {};
    for (let i = 0; i < plan.length; i++) {
        if (!kinds.includes(plan[i].kind)) continue;
        r.startLabelProbe();
        try { app.renderBinderPage(opts, i); }
        finally { out[plan[i].number + ' ' + plan[i].title] = r.endLabelProbe(); }
    }
    return out;
}"""


def _name(b):
    return '%s "%s"' % (b['kind'], b['text'])


def _overlap(a, b):
    """How far two boxes lie over one another, per axis."""
    return (min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x']),
            min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']))


def _over(a, b):
    dx, dy = _overlap(a, b)
    return dx > HAIR and dy > HAIR


def _straddles(box, edge):
    """The box has ink on BOTH sides of the edge's line, over the stretch
    the edge actually runs. A box merely touching the line is clear."""
    if edge['w'] == 0:                      # a vertical edge
        return (box['x'] + HAIR < edge['x'] < box['x'] + box['w'] - HAIR
                and box['y'] < edge['y'] + edge['h'] and edge['y'] < box['y'] + box['h'])
    return (box['y'] + HAIR < edge['y'] < box['y'] + box['h'] - HAIR
            and box['x'] < edge['x'] + edge['w'] and edge['x'] < box['x'] + box['w'])


def _ink(boxes):
    return [b for b in boxes if b['kind'] in INK]


def _edges(boxes):
    return [b for b in boxes if b['kind'] == 'wallEdge']


def _pairs_over(boxes):
    ink = _ink(boxes)
    out = []
    for i, a in enumerate(ink):
        for b in ink[i + 1:]:
            if _over(a, b):
                dx, dy = _overlap(a, b)
                out.append('%s over %s by %.1f x %.1f px' % (_name(a), _name(b), dx, dy))
    return out


def _is_wiring(name):
    return name.endswith(' - Power Wiring') or name.endswith(' - Data Wiring')


def _on_paper(boxes):
    """A wiring sheet gives its map NO gutter, so the bitmap is the wall and
    nothing else: the band pill and the circuit ruler the map lays over the
    wall's head fall outside it and are clipped away. Ink that never reaches
    the paper cannot collide, so only what lies over the wall is judged."""
    edges = _edges(boxes)
    if len(edges) != 4:
        return boxes
    x0 = min(e['x'] for e in edges)
    y0 = min(e['y'] for e in edges)
    x1 = max(e['x'] + e['w'] for e in edges)
    y1 = max(e['y'] + e['h'] for e in edges)
    return [b for b in boxes if b['kind'] == 'wallEdge'
            or (b['x'] + b['w'] > x0 and b['y'] + b['h'] > y0 and b['x'] < x1 and b['y'] < y1)]


def _check_map(name, boxes):
    """Every rule this file exists for, on one screen's map. Returns the
    faults as lines, so one failure names all of them."""
    bad = []
    assert boxes, ('the registry recorded nothing for ' + name
                   + ' - the probe is not reaching the map')
    assert len(_edges(boxes)) == 4, (name, 'the wall drew no edges', boxes)
    if _is_wiring(name):
        boxes = _on_paper(boxes)

    # 1. no two pieces of the map's lettering overlap by more than a hair
    bad += ['%s: %s' % (name, s) for s in _pairs_over(boxes)]

    # 2. no ruler tick (or its L label) crosses a band pill's box - the
    #    band gets a strip of its own, above the line the ruler hangs from
    for band in [b for b in boxes if b['kind'] == 'band']:
        for r in [b for b in boxes if b['kind'] in ('rulerTick', 'rulerLabel')]:
            if _over(band, r):
                dx, dy = _overlap(band, r)
                bad.append('%s: the circuit ruler %s runs through the band %s by %.1f x %.1f px'
                           % (name, _name(r), _name(band), dx, dy))

    # 3. no pill, tag or ruler label straddles one of the wall's own edge
    #    lines. A ruler label with the wall's edge line through it is the
    #    same fault one strip further down the gutter.
    for e in _edges(boxes):
        for b in [x for x in boxes if x['kind'] in OFF_THE_EDGE]:
            if _straddles(b, e):
                bad.append('%s: %s sits on the wall\'s %s edge'
                           % (name, _name(b), e['text']))

    # 4. a disc never overlaps its neighbour's disc or a cable tag
    discs = [b for b in boxes if b['kind'] == 'disc']
    tags = [b for b in boxes if b['kind'] == 'tag']
    for i, a in enumerate(discs):
        for b in discs[i + 1:] + tags:
            if _over(a, b):
                bad.append('%s: %s overlaps %s' % (name, _name(a), _name(b)))

    # 5. a pill hung UNDER or OVER a disc (centred on it) stands off it by
    #    at least half its own height - its corner radius. Any closer and
    #    the two rounded rims read as one thing, which is what "jammed
    #    into each other" looked like on the dense wall.
    for t in tags:
        tcx = t['x'] + t['w'] / 2
        for d in discs:
            if abs(tcx - (d['x'] + d['w'] / 2)) > HAIR:
                continue
            dx, dy = _overlap(t, d)
            if dx <= 0:
                continue
            standoff = -dy                  # positive when they are apart
            if standoff < t['h'] / 2:
                bad.append('%s: %s stands only %.1f px off %s, less than its own %.1f px corner'
                           % (name, _name(t), standoff, _name(d), t['h'] / 2))
    return bad


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _maps(pg, fixture, palette):
    with open(fixture) as fh:
        project = json.load(fh)
    pg.evaluate(LOAD_JS, project)
    opts = json.loads(_SHOW_JSON)
    opts['palette'] = palette
    return pg.evaluate(PROBE_JS, [opts, list(MAP_KINDS)])


def _sweep(pg, fixture, palette):
    maps = _maps(pg, fixture, palette)
    assert maps, 'the show planned no power or data sheet'
    assert [n for n in maps if _is_wiring(n)], ('the sweep reached no wiring sheet', list(maps))
    bad = []
    for name, boxes in maps.items():
        bad += _check_map(name, boxes)
    assert not bad, '\n'.join([''] + bad)
    return maps


def test_the_registry_records_the_map_the_seeded_show_drew(page):
    """The probe reaches the map at all: the seeded WALL-A's power sheet
    records its own circuit discs, the wall's four edges, and nothing that
    is not one of the kinds the registry knows. Every map sheet of the
    seeded show is held to the rules - its Power Wiring and Data Wiring
    sheets too, each one wall on a page of its own."""
    pg, ids = page
    opts = json.loads(_SHOW_JSON)
    boxes = pg.evaluate(PROBE_JS, [opts, list(MAP_KINDS)])
    power = [v for k, v in boxes.items() if k.endswith('WALL-A - Power - Front View')]
    assert len(power) == 1, list(boxes)
    kinds = {}
    for b in power[0]:
        kinds[b['kind']] = kinds.get(b['kind'], 0) + 1
    assert kinds.get('wallEdge') == 4, kinds
    assert kinds.get('disc') == 2, kinds          # SR1-1 and SR1-2
    assert set(kinds) <= set(INK) | {'wallEdge'}, kinds
    assert [b['text'] for b in power[0] if b['kind'] == 'disc'] == ['SR1-1', 'SR1-2']
    # every box is a real box in the bitmap
    for b in power[0]:
        assert b['w'] >= 0 and b['h'] >= 0, b
        assert b['kind'] == 'wallEdge' or (b['w'] > 0 and b['h'] > 0), b
    wiring = sorted(k.split(' ', 1)[1] for k in boxes if _is_wiring(k))
    assert wiring == sorted(['WALL-A - Power Wiring', 'WALL-A - Data Wiring', 'WALL-B - Power Wiring',
                             'WALL-B - Data Wiring', 'CENTER - Power Wiring', 'CENTER - Data Wiring']), list(boxes)
    for name in wiring:
        key = next(k for k in boxes if k.endswith(' ' + name))
        # one wall on the sheet: its four edges once, not twice
        assert len(_edges(boxes[key])) == 4, (name, _edges(boxes[key]))
    for name, bs in boxes.items():
        assert not _check_map(name, bs), _check_map(name, bs)
    assert ids['errors'] == []


def test_the_probe_costs_nothing_when_it_is_off(page):
    """Off by default, and a render with it off records nothing at all -
    the registry must not be a tax on every draw of the working view."""
    pg, _ids = page
    assert pg.evaluate("() => window.canvasRenderer.labelProbe === null") is True
    assert pg.evaluate("""() => {
        const r = window.canvasRenderer;
        r.renderLayers ? r.renderLayers() : r.render();
        return r.labelProbe === null && r._labelProbeRadii === null;
    }""") is True


@pytest.mark.skipif(bool(private_fixture_missing(KELLY_LIVE)),
                    reason=str(private_fixture_missing(KELLY_LIVE)))
@pytest.mark.parametrize('palette', ['printer', 'colour'])
def test_kelly_live_writes_on_top_of_nothing(page, palette):
    """The show the faults came from - UPSTAGE 22 x 7, SR and SL 9 x 6 -
    every screen's power and data map, in both palettes.

    Before the fix this failed on all three faults at once: two leg ticks
    of the map's own ruler through each band pill, every 2fer pill across
    the wall's bottom edge, and two cable tags on SL printed through each
    other."""
    pg, ids = page
    maps = _sweep(pg, KELLY_LIVE, palette)
    # the show really is the dense one, so the sweep means something
    biggest = max(maps.values(), key=lambda bs: len([b for b in bs if b['kind'] == 'disc']))
    assert len([b for b in biggest if b['kind'] == 'disc']) >= 11, biggest
    assert any(b['kind'] == 'band' for bs in maps.values() for b in bs), 'no multi band drawn'
    assert any(b['kind'] == 'gang' for bs in maps.values() for b in bs), 'no gang tag drawn'
    assert any(b['kind'] == 'rulerTick' for bs in maps.values() for b in bs), 'no circuit ruler drawn'
    assert ids['errors'] == []


@pytest.mark.skipif(bool(private_fixture_missing(SCRATCH_FIXTURE)),
                    reason=str(private_fixture_missing(SCRATCH_FIXTURE)))
@pytest.mark.parametrize('palette', ['printer', 'colour'])
def test_experts_only_writes_on_top_of_nothing(page, palette):
    """The other frozen show: 22 circuits on one wall, gangs that sit on a
    ROW SEAM rather than under the wall (so the edge rule must not fire on
    them), and the widest label discs of the two fixtures."""
    pg, ids = page
    maps = _sweep(pg, SCRATCH_FIXTURE, palette)
    assert any(len([b for b in bs if b['kind'] == 'disc']) >= 22 for bs in maps.values()), \
        {k: len(v) for k, v in maps.items()}
    assert ids['errors'] == []


# ---- cabinet ids -----------------------------------------------------------
#
# The Cabinet ID view numbers every cabinet, and the number used to be drawn
# at the user's label size whatever the cabinet's size on the bitmap: a
# label size of 200 on a wall of 64 px cabinets painted one white smear
# across the whole wall and past its edge, and even a sane size ran "1,10"
# into the cabinet next door once the view was zoomed out. "cabinet ids
# should not be able to extend to the panel next to it even if the text is
# too large" (2026-09-15). canvas-labels.js now fits each id to its own
# cabinet, drops it below a legibility floor judged on the bitmap it lands
# on, and clips it to the cabinet regardless; the registry records the id
# ('cabinetId', with the font size it was painted at) and the cabinet it
# belongs to ('cabinet'), both in the bitmap's pixels, so these tests read
# the geometry the ink got. The size is ONE per screen - the widest id fits
# the smallest cabinet - so neighbours never carry two sizes of type.

# The wall: 12 x 6 of 64 px cabinets, at (40, 40) so its top-left edge is
# not the raster's.
CAB_COLS, CAB_ROWS, CAB_PX = 12, 6, 64
# The label panel's maximum (index.html #number-size max="200").
CAB_LABEL_MAX = 200
# canvas-labels.js's CABINET_ID_PAD / CABINET_ID_CORNER: the id's box is
# the cabinet inset by 12% of its smaller side; at the top-left the corner
# keeps a 5 px stand-off where that is smaller.
CAB_PAD = max(1.0, 0.12 * CAB_PX)
CAB_CORNER = min(5.0, CAB_PAD)
# a cabinet ~18 px on screen, and ~60 px
CAB_ZOOM_SMALL = 18 / CAB_PX
CAB_ZOOM_NORMAL = 60 / CAB_PX
# a cabinet ~4 px on screen: every id is under the 5 px floor (at 6 px the
# narrow "I1".."I6" still fit at 5.2 px tall, and are rightly drawn)
CAB_ZOOM_TINY = 4 / CAB_PX
CAB_STYLES = ('row-col', 'column-row')
CAB_POSITIONS = ('center', 'top-left')
CAB_ROTATIONS = (0, 90)

CAB_SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = [];
    // one canvas at the raster a fresh project has: a real show loaded
    // earlier in the module (a 4096 x 2160 canvas, a workspace offset)
    // must not become this wall's export raster
    proj.canvases = [{id: 'c1', name: 'Canvas 1', color: '#4A90E2', workspace_x: 0, workspace_y: 0,
                      raster_width: 1920, raster_height: 1080,
                      show_raster_width: 1920, show_raster_height: 1080,
                      data_flow_perspective: 'front', power_perspective: 'front', visible: true}];
    proj.active_canvas_id = 'c1';
    proj.raster_width = 1920; proj.raster_height = 1080;
    proj.show_raster_width = 1920; proj.show_raster_height = 1080;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'SMALL', columns: %d, rows: %d,
                                       cabinet_width: %d, cabinet_height: %d,
                                       offset_x: 40, offset_y: 40});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('cabinet_ids');
    app.selectLayer(app.project.layers.find(l => l.name === 'SMALL'));
    app.renderLayers();
    document.querySelector('[data-mode="cabinet-id"]').click();
    const l = app.project.layers.find(l => l.name === 'SMALL');
    return { id: l.id, panels: l.panels.length, view: window.canvasRenderer.viewMode };
}""" % (CAB_COLS, CAB_ROWS, CAB_PX, CAB_PX)

# One render of the working view with the probe on, at the given style,
# position, rotation and zoom, the label size at the panel's maximum.
CAB_PROBE_JS = """([style, pos, rot, zoom, size]) => {
    const r = window.canvasRenderer, app = window.app;
    const l = app.project.layers.find(l => l.name === 'SMALL');
    l.number_size = size; l.cabinetIdStyle = style; l.cabinetIdPosition = pos; l.rotation = rot;
    r.zoom = zoom; r.panX = 20; r.panY = 20;
    r.startLabelProbe();
    try { r.render(); } finally { var out = r.endLabelProbe(); }
    return out;
}"""

# The export path, as performExport drives it: the renderer swapped onto a
# canvas of the raster's size, exportMode on, zoom = the export scale (1 for
# PNG and PDF), the pan putting the canvas's workspace origin at (0, 0).
# Returns the registry AND a scan of the bitmap for the id's own colour -
# magenta, which nothing else on the wall wears (the default cabinet colours
# are blue-greys, the borders white) - counted inside the cabinets' inner
# boxes and outside them.
CAB_EXPORT_JS = """([style, pos, rot, size, inset]) => {
    const r = window.canvasRenderer, app = window.app;
    const l = app.project.layers.find(l => l.name === 'SMALL');
    const keep = { zoom: r.zoom, panX: r.panX, panY: r.panY, canvas: r.canvas, ctx: r.ctx,
                   colour: l.cabinetIdColor };
    l.number_size = size; l.cabinetIdStyle = style; l.cabinetIdPosition = pos; l.rotation = rot;
    l.cabinetIdColor = '#ff00ff';
    const canvases = Array.isArray(app.project.canvases) ? app.project.canvases : [];
    const cv = canvases.find(c => c && c.id === app.project.active_canvas_id) || canvases[0] || null;
    const W = r.rasterWidth, H = r.rasterHeight;
    const ex = document.createElement('canvas');
    ex.width = W; ex.height = H;
    r.canvas = ex; r.ctx = ex.getContext('2d');
    r.exportMode = true;
    r.zoom = 1;
    r.panX = -((cv && cv.workspace_x) || 0);
    r.panY = -((cv && cv.workspace_y) || 0);
    let boxes;
    try {
        r.startLabelProbe();
        try { r.render(); } finally { boxes = r.endLabelProbe(); }
        const px = r.ctx.getImageData(0, 0, W, H).data;
        const cabs = boxes.filter(b => b.kind === 'cabinet');
        let inside = 0, outside = 0, first = null;
        for (let y = 0; y < H; y++) {
            for (let x = 0; x < W; x++) {
                const k = (y * W + x) * 4;
                // magenta-ness: the id's colour, and its blends with the
                // cabinet colours at a glyph's anti-aliased edge
                if ((px[k] + px[k + 2]) / 2 - px[k + 1] < 60) continue;
                const home = cabs.some(c => x + 0.5 >= c.x + inset && x + 0.5 <= c.x + c.w - inset
                                         && y + 0.5 >= c.y + inset && y + 0.5 <= c.y + c.h - inset);
                if (home) inside++;
                else { outside++; if (!first) first = [x, y]; }
            }
        }
        return { boxes, inside, outside, first, width: W, height: H };
    } finally {
        r.exportMode = false;
        r.canvas = keep.canvas; r.ctx = keep.ctx;
        r.zoom = keep.zoom; r.panX = keep.panX; r.panY = keep.panY;
        l.cabinetIdColor = keep.colour;
        r.render();
    }
}"""


def _inside(box, home, clearance):
    """The box lies within `home` with at least `clearance` to every side."""
    return (box['x'] >= home['x'] + clearance - HAIR
            and box['y'] >= home['y'] + clearance - HAIR
            and box['x'] + box['w'] <= home['x'] + home['w'] - clearance + HAIR
            and box['y'] + box['h'] <= home['y'] + home['h'] - clearance + HAIR)


def _check_cabinet_ids(name, boxes, scale, present):
    """Every id the registry recorded sits inside the cabinet that carries
    its text, clear of the pad, and over no other cabinet; with `present`,
    every cabinet has its id. Returns the faults as lines."""
    cabs = [b for b in boxes if b['kind'] == 'cabinet']
    ids = [b for b in boxes if b['kind'] == 'cabinetId']
    bad = []
    if len(cabs) != CAB_COLS * CAB_ROWS:
        bad.append('%s: %d cabinets recorded, not %d' % (name, len(cabs), CAB_COLS * CAB_ROWS))
    by_text = {}
    for c in cabs:
        by_text.setdefault(c['text'], []).append(c)
    if present and len(ids) != len(cabs):
        missing = sorted(set(by_text) - set(b['text'] for b in ids))
        bad.append('%s: %d ids drawn for %d cabinets - missing %s'
                   % (name, len(ids), len(cabs), missing[:8]))
    # one size of type per screen: the layer's size is the user's size
    # shrunk until its widest id fits its smallest cabinet, and every id
    # on the layer is painted at it
    sizes = sorted(set(round(b.get('size', 0), 3) for b in ids))
    if ids and (len(sizes) != 1 or sizes[0] <= 0):
        bad.append('%s: the ids wear %d sizes: %s' % (name, len(sizes), sizes[:6]))
    for b in ids:
        assert b['w'] > 0 and b['h'] > 0, (name, b)
        homes = by_text.get(b['text'], [])
        if len(homes) != 1:
            bad.append('%s: id "%s" has %d cabinets' % (name, b['text'], len(homes)))
            continue
        home = homes[0]
        for other in cabs:
            if other is home:
                continue
            if _over(b, other):
                dx, dy = _overlap(b, other)
                bad.append('%s: id "%s" over cabinet "%s" by %.1f x %.1f px'
                           % (name, b['text'], other['text'], dx, dy))
        if not _inside(b, home, 0):
            bad.append('%s: id "%s" leaves its cabinet: id %s, cabinet %s' % (
                name, b['text'],
                [round(b[k], 1) for k in 'xywh'], [round(home[k], 1) for k in 'xywh']))
        elif not _inside(b, home, scale * CAB_CORNER):
            bad.append('%s: id "%s" sits closer than %.1f px to its cabinet\'s edge: id %s, cabinet %s' % (
                name, b['text'], scale * CAB_CORNER,
                [round(b[k], 1) for k in 'xywh'], [round(home[k], 1) for k in 'xywh']))
    return bad


def _cabinet_sweep(pg, zoom, size, present):
    bad = []
    seen = 0
    for style in CAB_STYLES:
        for pos in CAB_POSITIONS:
            for rot in CAB_ROTATIONS:
                name = '%s %s rot%d zoom%.2f' % (style, pos, rot, zoom)
                boxes = pg.evaluate(CAB_PROBE_JS, [style, pos, rot, zoom, size])
                seen += len([b for b in boxes if b['kind'] == 'cabinetId'])
                bad += _check_cabinet_ids(name, boxes, zoom, present)
    return bad, seen


@pytest.fixture(scope="module")
def cabinet_page(page):
    pg, ids = page
    seed = pg.evaluate(CAB_SEED_JS)
    pg.wait_for_timeout(600)
    assert seed['panels'] == CAB_COLS * CAB_ROWS, seed
    assert seed['view'] == 'cabinet-id', seed
    return pg, ids


def test_cabinet_ids_never_leave_their_cabinet(cabinet_page):
    """The wall zoomed out to ~18 px cabinets, the label size at the panel's
    maximum, the widest style ("1,10") and the column style ("A1"), both
    positions, unrotated and turned 90: every id the map drew lies inside
    its own cabinet, clear of the pad, and over no neighbour, and all of
    them at one size. And at ~4 px
    cabinets, where no id could be read, none is drawn at all - the cabinets
    are recorded, the ids are not.

    Before the fix the first sweep failed on every one of the 72 cabinets
    in every combination: "1,1" at 200 px covered the cabinets three to the
    right and two below it."""
    pg, ids = cabinet_page
    bad, seen = _cabinet_sweep(pg, CAB_ZOOM_SMALL, CAB_LABEL_MAX, present=True)
    assert not bad, '\n'.join([''] + bad)
    assert seen == CAB_COLS * CAB_ROWS * len(CAB_STYLES) * len(CAB_POSITIONS) * len(CAB_ROTATIONS)
    bad, seen = _cabinet_sweep(pg, CAB_ZOOM_TINY, CAB_LABEL_MAX, present=False)
    assert not bad, '\n'.join([''] + bad)
    assert seen == 0, 'ids drawn under the legibility floor: %d' % seen
    assert ids['errors'] == []


def test_cabinet_ids_all_show_at_a_working_zoom(cabinet_page):
    """At ~60 px cabinets every one of the 72 ids is drawn and inside its
    cabinet - in every style, position and rotation, at the panel's maximum
    size and at the default 30."""
    pg, ids = cabinet_page
    for size in (CAB_LABEL_MAX, 30):
        bad, seen = _cabinet_sweep(pg, CAB_ZOOM_NORMAL, size, present=True)
        assert not bad, '\n'.join([''] + bad)
        assert seen == CAB_COLS * CAB_ROWS * len(CAB_STYLES) * len(CAB_POSITIONS) * len(CAB_ROTATIONS)
    assert ids['errors'] == []


@pytest.mark.parametrize('pos', CAB_POSITIONS)
@pytest.mark.parametrize('rot', CAB_ROTATIONS)
def test_cabinet_ids_stay_home_in_the_export(cabinet_page, pos, rot):
    """The export is the same renderer on a hidden canvas at the export
    scale (performExport: exportMode on, zoom = 1 for PNG and PDF), so the
    legibility floor is judged at THAT scale: a 64 px cabinet prints its id
    even when the working view, zoomed out, shows none. Checked two ways on
    the export bitmap - the registry, and the pixels: every pixel of the
    id's colour lies inside some cabinet's inner box, none in the pad or
    over the cabinet next door."""
    pg, ids = cabinet_page
    # pixels of the id's colour must lie this far inside a cabinet's edge:
    # the corner stand-off, less a pixel for the glyph's anti-aliased fringe
    inset = CAB_CORNER - 1
    out = pg.evaluate(CAB_EXPORT_JS, ['row-col', pos, rot, CAB_LABEL_MAX, inset])
    assert (out['width'], out['height']) == (1920, 1080), out
    name = 'export row-col %s rot%d' % (pos, rot)
    bad = _check_cabinet_ids(name, out['boxes'], 1.0, present=True)
    assert not bad, '\n'.join([''] + bad)
    assert out['inside'] > CAB_COLS * CAB_ROWS * 20, out['inside']
    assert out['outside'] == 0, 'id ink outside every cabinet\'s inner box: %d px, first at %s' % (
        out['outside'], out['first'])
    assert ids['errors'] == []
