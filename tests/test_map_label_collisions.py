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

The two real shows are read by env var and SKIPPED when absent - they are
not in the repo:
    LRD_KELLY_LIVE_JSON   kelly-live-fixture.json  (22x7 and 9x6 walls)
    LRD_PULL_SMOKE_JSON   experts-only-fixture.json

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15801 python3 -m pytest tests/test_map_label_collisions.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import SEED_JS, _SHOW_JSON, SCRATCH_FIXTURE  # noqa: E402
from test_binder_wiring import LOAD_JS  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Kelly Clarkson as the user exported her: the show that produced all
# three faults. Frozen beside the Experts Only fixture.
KELLY_LIVE = os.environ.get('LRD_KELLY_LIVE_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly-live-fixture.json')

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

PROBE_JS = """([opts]) => {
    const app = window.app, r = window.canvasRenderer;
    const plan = app.planBinder(opts);
    const out = {};
    for (let i = 0; i < plan.length; i++) {
        if (plan[i].kind !== 'power' && plan[i].kind !== 'data') continue;
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


def _check_map(name, boxes):
    """Every rule this file exists for, on one screen's map. Returns the
    faults as lines, so one failure names all of them."""
    bad = []
    assert boxes, ('the registry recorded nothing for ' + name
                   + ' - the probe is not reaching the map')
    assert len(_edges(boxes)) == 4, (name, 'the wall drew no edges', boxes)

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
    return pg.evaluate(PROBE_JS, [opts])


def _sweep(pg, fixture, palette):
    maps = _maps(pg, fixture, palette)
    assert maps, 'the show planned no power or data sheet'
    bad = []
    for name, boxes in maps.items():
        bad += _check_map(name, boxes)
    assert not bad, '\n'.join([''] + bad)
    return maps


def test_the_registry_records_the_map_the_seeded_show_drew(page):
    """The probe reaches the map at all: the seeded WALL-A's power sheet
    records its own circuit discs, the wall's four edges, and nothing that
    is not one of the kinds the registry knows."""
    pg, ids = page
    opts = json.loads(_SHOW_JSON)
    boxes = pg.evaluate(PROBE_JS, [opts])
    power = [v for k, v in boxes.items() if k.endswith('WALL-A - Power')]
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


@pytest.mark.skipif(not os.path.exists(KELLY_LIVE),
                    reason='kelly-live-fixture.json smoke fixture not present')
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


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
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
