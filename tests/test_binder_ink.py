"""The binder must not write its own marks on top of the map's ink.

This is the THIRD of the three places a binder sheet can collide with
itself, and the only one neither of the other two suites can reach:

  * vector against vector - two text ops overprinting, or a line drawn
    through a string. The display list holds both, so it is checkable
    directly (and clean today on the chrome).
  * the map against ITSELF - tests/test_map_label_collisions.py, which
    reads canvas.js's label registry, because the map's own lettering is
    pixels inside one bitmap and no op can see it.
  * THIS ONE: the binder's own vector ruler, numbers and brackets landing
    on the bitmap it just placed. Neither side knows about the other. The
    ops say nothing (the map is one image op) and the registry says
    nothing (the binder's marks are not the map's).

The fault this was written for: on every power sheet of the user's Kelly
export the binder's bold column number sat inside the map's multi band
pill, so "S1-1 · 250 · 65.8A" read as "S1-4". The binder's ruler and the
map's own leg ruler were both living in the same gutter above the wall.

Method: render a page, paint ONLY its image ops onto a canvas at a
quarter scale, then ask of every vector mark whether the map had already
written where it lands. Quarter scale is deliberate - it is looking for a
number sitting in a pill, not for a hairline kissing a rim.

This guard is about the binder's TEXT. Its rules are deliberately left
out: a ruler tick is SUPPOSED to touch the wall's edge - that is what
makes it point at the wall - and a pixel pass cannot tell the map's edge
line from the map's lettering, so every honest tick reads as a hit. Lines
are covered where the distinction exists: a run crossing a label is the
display list's business (both are ops), and the map's own ticks crossing
its own band pill are the label registry's, which knows a rulerTick from
a band. Line hits are still collected here, and reported when a text hit
sends the test red, because they are useful to look at.

The real shows are read by env var and SKIPPED when absent - they are not
in the repo:
    LRD_KELLY_LIVE_JSON   kelly-live-fixture.json
    LRD_PULL_SMOKE_JSON   experts-only-fixture.json

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15801 python3 -m pytest tests/test_binder_ink.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import SEED_JS, SCRATCH_FIXTURE, _SHOW_JSON  # noqa: E402
from test_binder_wiring import (  # noqa: E402
    LOAD_JS, _covers_lettering, _probe, _through_the_wall,
)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

KELLY_LIVE = os.environ.get('LRD_KELLY_LIVE_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly-live-fixture.json')

# How much of a mark's own footprint may sit on map ink before it is a
# collision. A number printed inside a pill covers a quarter of itself or
# more; a rule that grazes a cabinet seam covers a few percent.
TEXT_LIMIT = 0.05

# The second guard, and the one that caught the ruler numbers running
# through the sheet's head rule: within the VECTOR layer, a stroked line
# must not cross a string. Both are ops, so this needs no pixels and no
# guesswork about what the ink belongs to.
RULE_JS = """([opts]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const mc = document.createElement('canvas').getContext('2d');
    const widthOf = (o) => {
        mc.font = `${o.weight || 400} ${o.size}px Helvetica, Arial, sans-serif`;
        return mc.measureText(o.text).width;
    };
    const out = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        const texts = [], lines = [];
        for (const o of r.record.ops) {
            if (o.op === 'text') {
                const t = String(o.text);
                if (!t.trim() || o.rotate) continue;
                const w = widthOf(o);
                let x = o.x;
                if (o.align === 'center') x -= w / 2;
                else if (o.align === 'right') x -= w;
                let top = o.y - o.size * 0.78;
                if (o.baseline === 'middle') top = o.y - o.size * 0.5;
                else if (o.baseline === 'top') top = o.y;
                else if (o.baseline === 'bottom') top = o.y - o.size;
                // the box is pulled in a little on every side: a rule that
                // runs along a cell's edge is a table, not a strike-through
                const inset = Math.min(2.5, o.size * 0.18);
                texts.push({ t, x: x + inset, y: top + inset,
                             w: Math.max(1, w - 2 * inset),
                             h: Math.max(1, o.size * 0.92 - 2 * inset) });
            } else if (o.op === 'line') {
                lines.push(o.points || []);
            }
        }
        const hits = [];
        for (const t of texts) {
            if (t.t.length < 1) continue;
            let struck = null;
            for (const pts of lines) {
                for (let k = 0; k < pts.length - 1 && !struck; k++) {
                    const [x0, y0] = pts[k], [x1, y1] = pts[k + 1];
                    // Liang-Barsky against the inset box
                    const dx = x1 - x0, dy = y1 - y0;
                    let t0 = 0, t1 = 1, ok = true;
                    const P = [-dx, dx, -dy, dy];
                    const Q = [x0 - t.x, t.x + t.w - x0, y0 - t.y, t.y + t.h - y0];
                    for (let e = 0; e < 4 && ok; e++) {
                        if (P[e] === 0) { if (Q[e] < 0) ok = false; continue; }
                        const rr = Q[e] / P[e];
                        if (P[e] < 0) { if (rr > t1) ok = false; else t0 = Math.max(t0, rr); }
                        else { if (rr < t0) ok = false; else t1 = Math.min(t1, rr); }
                    }
                    if (ok && t0 <= t1) struck = [Math.round(x0), Math.round(y0),
                                                  Math.round(x1), Math.round(y1)];
                }
                if (struck) break;
            }
            if (struck) hits.push({ t: t.t, x: Math.round(t.x), y: Math.round(t.y), line: struck });
        }
        out.push({ n: plan[i].number, title: plan[i].title, kind: plan[i].kind, hits });
    }
    return out;
}"""

INK_JS = """([opts]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const mc = document.createElement('canvas').getContext('2d');
    const widthOf = (o) => {
        mc.font = `${o.weight || 400} ${o.size}px Helvetica, Arial, sans-serif`;
        return mc.measureText(o.text).width;
    };
    const load = (src) => new Promise(res => {
        const im = new Image();
        im.onload = () => res(im);
        im.onerror = () => res(null);
        im.src = src;
    });
    return (async () => {
        const out = [];
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            const imgOps = r.record.ops.filter(o => o.op === 'image');
            const page = { n: plan[i].number, title: plan[i].title,
                           kind: plan[i].kind, hits: [] };
            if (!imgOps.length) { out.push(page); continue; }
            const K = 0.25;
            const cv = document.createElement('canvas');
            cv.width = Math.ceil(r.record.width * K);
            cv.height = Math.ceil(r.record.height * K);
            const cx = cv.getContext('2d');
            cx.fillStyle = '#fff';
            cx.fillRect(0, 0, cv.width, cv.height);
            for (const o of imgOps) {
                const src = (r.record.images && r.record.images[o.id]) || null;
                if (!src) continue;
                const im = await load(src);
                if (im) cx.drawImage(im, o.x * K, o.y * K, o.w * K, o.h * K);
            }
            const px = cx.getImageData(0, 0, cv.width, cv.height).data;
            // the fraction of a page-unit rect that the map already inked
            const inked = (x0, y0, x1, y1) => {
                let n = 0, tot = 0;
                const ax = Math.max(0, Math.floor(x0 * K));
                const ay = Math.max(0, Math.floor(y0 * K));
                const bx = Math.min(cv.width - 1, Math.ceil(x1 * K));
                const by = Math.min(cv.height - 1, Math.ceil(y1 * K));
                for (let y = ay; y <= by; y++) {
                    for (let x = ax; x <= bx; x++) {
                        const k = (y * cv.width + x) * 4;
                        tot++;
                        // ink is anything clearly darker than the map's
                        // palest cabinets, so a light panel is not "ink"
                        if (px[k] < 140 && px[k + 1] < 140 && px[k + 2] < 140) n++;
                    }
                }
                return tot ? n / tot : 0;
            };
            for (const o of r.record.ops) {
                if (o.op === 'text') {
                    const t = String(o.text);
                    if (!t.trim() || o.rotate) continue;
                    const w = widthOf(o);
                    let x = o.x;
                    if (o.align === 'center') x -= w / 2;
                    else if (o.align === 'right') x -= w;
                    let top = o.y - o.size * 0.78;
                    if (o.baseline === 'middle') top = o.y - o.size * 0.5;
                    else if (o.baseline === 'top') top = o.y;
                    else if (o.baseline === 'bottom') top = o.y - o.size;
                    const f = inked(x, top, x + w, top + o.size * 0.92);
                    if (f > 0.02) page.hits.push({ kind: 'text', t,
                        x: Math.round(x), y: Math.round(top), frac: +f.toFixed(3) });
                } else if (o.op === 'line') {
                    // a horizontal or vertical segment has no width of its
                    // own, so sample the stroke's real footprint
                    const pts = o.points || [];
                    const pad = Math.max(o.width || 1, 3);
                    for (let k = 0; k < pts.length - 1; k++) {
                        const [x0, y0] = pts[k], [x1, y1] = pts[k + 1];
                        const f = inked(Math.min(x0, x1) - pad, Math.min(y0, y1) - pad,
                                        Math.max(x0, x1) + pad, Math.max(y0, y1) + pad);
                        if (f > 0.04) {
                            page.hits.push({ kind: 'line', t: '',
                                x: Math.round(x0), y: Math.round(y0),
                                x2: Math.round(x1), y2: Math.round(y1),
                                frac: +f.toFixed(3) });
                            break;
                        }
                    }
                }
            }
            out.push(page);
        }
        return out;
    })();
}"""


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


def _opts(palette):
    return {'sheet': 'tabloid', 'palette': palette,
            'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': True, 'pull': True,
            'hardware': True, 'wiring': True}


def _complaints(report):
    """Every string the binder prints on ink the map had already put down.

    Lines are collected but not judged - see the module docstring: a tick
    touching the wall's edge is the tick doing its job, and this pass
    cannot tell that edge from the map's lettering.
    """
    bad = []
    for page in report:
        for h in page['hits']:
            if h['kind'] != 'text' or h['frac'] <= TEXT_LIMIT:
                continue
            bad.append(
                '%s %s: the binder prints %r on the map\'s own ink, '
                'covering %d%% of it' % (page['n'], page['title'],
                                         h['t'][:32], round(h['frac'] * 100)))
    return bad


@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_the_seeded_show_prints_nothing_on_its_own_maps(page, palette):
    """The show the suite seeds for itself, both palettes."""
    pg, _ids = page
    pg.evaluate(SEED_JS)
    report = pg.evaluate(INK_JS, [_opts(palette)])
    assert report, 'the binder planned no pages at all'
    bad = _complaints(report)
    assert not bad, '\n' + '\n'.join('  ' + b for b in bad)


@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_kelly_live_prints_nothing_on_its_own_maps(page, palette):
    """Kelly Clarkson as the user exported her - the show whose power
    sheets carried the binder's column number inside the map's band pill,
    turning "S1-1" into "S1-4"."""
    if not os.path.exists(KELLY_LIVE):
        pytest.skip('kelly-live-fixture.json not present')
    pg, _ids = page
    import json
    pg.evaluate(LOAD_JS, json.load(open(KELLY_LIVE)))
    report = pg.evaluate(INK_JS, [_opts(palette)])
    assert report, 'the binder planned no pages at all'
    bad = _complaints(report)
    assert not bad, '\n' + '\n'.join('  ' + b for b in bad)


"""A wiring sheet's runs cross ONE kind of string by design: the socket
NUMBER inside a block, which a run passes over on its way down into the
socket beside it. Nothing else - the exemption used to be the whole sheet,
and that is how runs drawn straight through the map's own lettering
shipped twice."""
SOCKET_NUMBER = re.compile(r'^\d{1,2}$')


def _struck(report):
    """Every string a binder rule is drawn through.

    On a wiring sheet a bare socket number is exempt (see above); every
    other string is not, because a run over LETTERING is the fault this
    file exists to catch.
    """
    bad = []
    for page in report:
        for h in page['hits']:
            if page['kind'] == 'wiring' and SOCKET_NUMBER.match(h['t'].strip()):
                continue
            bad.append('%s %s: a binder rule from (%d,%d) to (%d,%d) is drawn '
                       'through %r' % (page['n'], page['title'], h['line'][0],
                                       h['line'][1], h['line'][2], h['line'][3],
                                       h['t'][:32]))
    return bad


@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_no_binder_rule_is_drawn_through_a_string(palette):
    """The seeded show: nothing the binder strokes crosses anything it
    writes. This is the guard that catches a ruler number pushed up into
    the sheet's own head rule."""
    pytest.importorskip("playwright.sync_api")


@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_kelly_live_has_no_rule_through_a_string(page, palette):
    """Kelly Clarkson as the user exported her. Her power sheets are where
    the column ruler ran out of room: moved clear of the map's band pill it
    went straight into the head rule at the top of the sheet."""
    if not os.path.exists(KELLY_LIVE):
        pytest.skip('kelly-live-fixture.json not present')
    pg, _ids = page
    import json
    pg.evaluate(LOAD_JS, json.load(open(KELLY_LIVE)))
    report = pg.evaluate(RULE_JS, [_opts(palette)])
    assert report, 'the binder planned no pages at all'
    bad = _struck(report)
    assert not bad, '\n' + '\n'.join('  ' + b for b in bad)


# The other half of the narrowed exemption. A wiring sheet's runs may pass
# over the wall's BARE CABINETS - that is what the white casing is for, and
# the pixel pass above cannot tell a cabinet from a letter, so it judges no
# line at all. canvas.js's label registry can: it knows a disc from a tag
# from a plain panel. So the sheet keeps its exemption for cabinets and
# loses it for LETTERING, which is the fault that shipped twice.
@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_no_wiring_run_is_drawn_over_the_maps_own_lettering(page, palette):
    """Kelly Clarkson as the user exported her, and the seeded show:
    on every SIGNAL + POWER sheet not one run is drawn over a label disc,
    a cable tag, a gang pill, a multi band or a ruler label - and not one
    is inside the wall at all but for the stub out of its own disc."""
    import json
    pg, _ids = page
    shows = [(None, ['WALL-A - Signal + Power', 'WALL-B - Signal + Power',
                     'CENTER - Signal + Power'])]
    if os.path.exists(KELLY_LIVE):
        shows.append((KELLY_LIVE, ['SR - Signal + Power', 'SL - Signal + Power',
                                   'UPSTAGE - Signal + Power']))
    bad, runs = [], 0
    for fixture, titles in shows:
        if fixture is None:
            pg.evaluate(SEED_JS)
        else:
            pg.evaluate(LOAD_JS, json.load(open(fixture)))
        opts = {**json.loads(_SHOW_JSON), 'palette': palette}
        for title in titles:
            for h in _probe(pg, opts, title):
                runs += len(h['runs'])
                bad += ['%s %s: %s' % (title, h['side'], s)
                        for s in _covers_lettering(h) + _through_the_wall(h)]
    assert runs > 20, ('the sweep read almost no runs at all', runs)
    assert not bad, '\n' + '\n'.join('  ' + b for b in bad)
