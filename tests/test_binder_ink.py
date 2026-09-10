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
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import SEED_JS, SCRATCH_FIXTURE  # noqa: E402
from test_binder_wiring import LOAD_JS  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

KELLY_LIVE = os.environ.get('LRD_KELLY_LIVE_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly-live-fixture.json')

# How much of a mark's own footprint may sit on map ink before it is a
# collision. A number printed inside a pill covers a quarter of itself or
# more; a rule that grazes a cabinet seam covers a few percent.
TEXT_LIMIT = 0.05

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
