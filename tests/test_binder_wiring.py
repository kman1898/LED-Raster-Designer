"""The binder's SIGNAL + POWER sheet (app-binder-wiring.js) - a screen's
third sheet, after its Power and Data sheets (2026-09-08, on the last page
of the NACUBO packet: "he gave an example his binder and we could do this
for power and data drawing from a port to port … the last page is what i
was talking about").

The drawing is the one src/static/wiring-proto.html prototyped against two
real shows and the one that was approved (2026-09-09: "those are
fantastic", "that is much more legible", "that looks great"). The
prototype's page is 1000 units wide and a half carries every one of its
numbers across at K = the half's width / 1000, so these tests measure in
those units too.

The drawing area is split by a rule, SIGNAL over POWER (a screen with one
side draws that half alone). Each half:

  the WALL    - the same _bMap render, rulers and brackets off. THE WALL'S
                OWN LABEL DISCS ARE THE ORIGIN - no second tag is drawn on
                it; the runs leave the very discs the renderer laid down.
  the BLOCKS  - flat units at the BOTTOM, spread across the width, their
                sockets in a row and their name inside them, ordered by
                the mean position of their own runs. A device the ports
                land on ("CVT4K-S SR A · Card 1 · OPT 1-2", or the card
                itself), a backup its own block; a multi's BREAKOUT, the
                fan out ("there are no boxes... it is a breakout also
                known as a fan out"): "SR1 · Multi 208 breakout · 125'".
  the RUNS    - OUT OF THE WALL AND ROUND IT. A run leaves its disc at
                its own row, crosses to the WALL'S NEAREST EDGE and no
                further, and travels in the clear space beside and under
                the wall: down a rail past the wall's edge, along a lane
                under its foot, and into its socket from there. Where the
                socket already stands outside the wall on the side the run
                leaves by, the rail IS the drop and two segments suffice -
                the drawing that was approved. Nothing but that one stub
                is ever inside the wall, so a run can cover no disc, no
                cable tag, no gang pill, no band and none of the screen's
                own arrows. Every run is drawn twice - a white casing
                under it - so it reads over the wall's dark panels.

The fault this replaced shipped twice: on the user's own DJ BOOTH sheet
every run left its disc, travelled the whole width of the wall along the
INSIDE of its own row - straight through that port's own "25'" cable tag,
and over the screen's daisy-chain arrows - and then turned down through
the wall's second row. On SR, "IMAG SR-6" printed as "IMAG R-6", the S
eaten by the white casing of the run leaving it.

A socket's note is drawn only where it says something the socket number
does not; a shared multi keeps the other screen's name against its socket.
A stub on no card draws its disc, no run, and the half prints
"n of m not placed on any card" once.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15795 python3 -m pytest tests/test_binder_wiring.py -v --browser chromium
"""

import base64
import io
import json
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import (  # noqa: E402
    SEED_JS, _SHOW_JSON, W, H, SCALE, DA, SCRATCH_FIXTURE,
    BOX_WORD, _generic_breakout, _title_block,
)

HERE = os.path.dirname(os.path.abspath(__file__))
pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# Kelly Clarkson, frozen beside the Experts Only fixture: the vertical-flow
# screens (every circuit on the wall's top row) and the two screens whose
# ports are on no card at all.
KELLY_FIXTURE = os.environ.get('LRD_KELLY_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly.json')
# Kelly as the USER EXPORTED HER - the show the fault was seen on (UPSTAGE
# 22 x 7, SR and SL 9 x 6), frozen beside the Experts Only fixture.
KELLY_LIVE = os.environ.get('LRD_KELLY_LIVE_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly-live-fixture.json')

# app-binder-wiring.js, in the prototype's units; a half scales them by K.
PROTO_W = 1000


def _js_consts(*names):
    """Read the drawing's own constants out of app-binder-wiring.js rather
    than keeping a second copy here that can drift away from it."""
    src = io.open(os.path.join(HERE, '..', 'src', 'static', 'js',
                               'app-binder-wiring.js'), encoding='utf-8').read()
    out = []
    for name in names:
        m = re.search(r'\b%s\s*=\s*(-?[0-9.]+)' % name, src)
        assert m, 'app-binder-wiring.js no longer defines ' + name
        out.append(float(m.group(1)))
    return out


MARGIN, SOCK, SOCKET_DY, BOX_H, TITLE_DY, NOTE_DY = _js_consts(
    'MARGIN', 'SOCK', 'SOCKET_DY', 'BOX_H', 'TITLE_DY', 'NOTE_DY')
RUN_W, CASE_EXTRA = 1.4, 3.2
# Half the white casing: the width a run really takes out of the paper, and
# so the width at which it covers a label rather than passing beside it.
CASE_PAD = (RUN_W + CASE_EXTRA) / 2
STRAIGHT = 1.2
RETURN_DASH = [6, 4]
PRINTER_RETURN_DASH = [3, 4]
HUES = ['#c2410c', '#0f766e', '#6d28d9', '#a16207',
        '#b91c1c', '#1d4ed8', '#4d7c0f', '#9d174d']
GREEN, RED, INK, WHITE = '#00ff00', '#ff0000', '#111111', '#ffffff'

K = DA['w'] / PROTO_W          # the Tabloid half's scale, both halves alike


def _hv(a, b):
    """A segment as 'h' (a horizontal), 'v' (a vertical), or 'x' (neither -
    the drawing has no diagonals)."""
    if abs(a[1] - b[1]) < 0.01 and abs(a[0] - b[0]) >= 0.01:
        return 'h'
    if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) >= 0.01:
        return 'v'
    return 'x'


def _segs(run):
    pts = run['points']
    return [_hv(a, b) for a, b in zip(pts, pts[1:])]


def _spans(runs, want):
    """Every horizontal ('h') or vertical ('v') segment as
    (name, fixed coordinate, lo, hi)."""
    out = []
    for r in runs:
        for a, b in zip(r['points'], r['points'][1:]):
            if _hv(a, b) != want:
                continue
            if want == 'h':
                out.append((r['from'], a[1], min(a[0], b[0]), max(a[0], b[0])))
            else:
                out.append((r['from'], a[0], min(a[1], b[1]), max(a[1], b[1])))
    return out


def _crossings(runs, want):
    """Pairs of segments that lie on the same line AND overlap - two runs
    printed over one another, which is what makes a line unfollowable."""
    segs = _spans(runs, want)
    return [(a, b) for i, a in enumerate(segs) for b in segs[i + 1:]
            if abs(a[1] - b[1]) < 0.01 and a[2] < b[3] - 0.01 and b[2] < a[3] - 0.01]


def _overlap(a, b):
    return (a['x'] < b['x'] + b['w'] - 0.01 and b['x'] < a['x'] + a['w'] - 0.01
            and a['y'] < b['y'] + b['h'] - 0.01 and b['y'] < a['y'] + a['h'] - 0.01)


def _inside(r, area):
    return r['x'] >= area['x'] - 0.01 and r['x'] + r['w'] <= area['x'] + area['w'] + 0.01 \
        and r['y'] >= area['y'] - 0.01 and r['y'] + r['h'] <= area['y'] + area['h'] + 0.01


def _c(v):
    """A colour as the recorder writes it: the binder sets the screen's own
    inks, which the project holds in either case."""
    return str(v).lower()


def _line_ops(out):
    return [o for o in out['ops'] if o['op'] == 'line']


def _same_path(op, run):
    pts = run['points']
    return (len(op['points']) == len(pts)
            and all(abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) < 0.05
                    for a, b in zip(op['points'], pts)))


def _casing_of(out, run):
    """Every run is drawn twice: a white stroke wider than the run, on the
    very same path, immediately under it."""
    lines = _line_ops(out)
    for i, o in enumerate(lines):
        if i and _same_path(o, run) and abs(o['width'] - run['width']) < 0.05 \
                and o['stroke'] == _c(run['colour']):
            under = lines[i - 1]
            if under['stroke'] == WHITE and _same_path(under, run) \
                    and under['width'] > o['width'] + 1:
                return under
    return None


def _check_runs(half, out=None):
    """Every run leaves its own disc's edge, lands on its socket's top, is
    two segments where two suffice and four where it must go round the
    wall (one where it is already outside and above its socket), and
    prints over no other run: no two horizontals overlap, no two verticals
    do, and there is not a diagonal on the sheet."""
    s = half['scale']
    discs = {d['text']: d for d in half['discs']}
    blocks = {b['title']: b for b in half['blocks']}
    for r in half['runs']:
        d = discs[r['from']]
        b = blocks[r['device']]
        sk = next(x for x in b['sockets'] if x['n'] == r['socket'])
        head = r['points'][0]
        assert abs(math.hypot(head[0] - d['x'], head[1] - d['y']) - d['r']) < 0.6, (
            'a run leaves its own disc, at its edge', r, d)
        tail = r['points'][-1]
        assert abs(tail[0] - sk['x']) < 0.01 and abs(tail[1] - (sk['y'] - SOCK * s)) < 0.01, (
            'a run lands on its socket', r, sk)
        shape = _segs(r)
        assert 'x' not in shape, ('the drawing has no diagonals', r)
        assert shape in (['v'], ['h', 'v'], ['h', 'v', 'h', 'v'],
                         ['v', 'h', 'v'], ['v', 'h', 'v', 'h', 'v']), (r, shape)
        if shape == ['v']:
            assert abs(sk['x'] - d['x']) < STRAIGHT * s + 0.01, (
                'only a run already above its socket drops straight', r, d, sk)
            assert abs(head[0] - sk['x']) < 0.01, ('straight down onto the socket', r, sk)
        elif shape[0] == 'h':
            assert abs(head[1] - d['y']) <= d['r'] + 0.01, ('out at the run OWN row', r, d)
        else:
            assert abs(head[0] - d['x']) <= d['r'] + 0.01, ('out of the run OWN column', r, d)
    assert _crossings(half['runs'], 'h') == [], _crossings(half['runs'], 'h')
    assert _crossings(half['runs'], 'v') == [], _crossings(half['runs'], 'v')
    if out is not None:
        for r in half['runs']:
            assert _casing_of(out, r), ('every run has a white casing under it', r)


# ---- the wall, and the map's own lettering on it -------------------------
#
# A screen map reaches this sheet as ONE BITMAP: its label discs, its cable
# tags, its gang pills, its multi band and its circuit ruler are pixels
# inside that image and no op in the display list can see them. canvas.js's
# label registry is the only thing that knows where they are - the same
# startLabelProbe() / endLabelProbe() pair tests/test_map_label_collisions.py
# reads - and it records them in the BITMAP'S OWN PIXELS. The bitmap is laid
# at the half's `map.area` at SCALE offscreen pixels to the page unit, so a
# box converts with  page = area + pixel / SCALE.

def _wall(half):
    m = half['map']
    return {'x': m['x'], 'y': m['y'], 'w': m['w'], 'h': m['h']}


def _labels(half):
    """The map's own lettering on this half, in the sheet's page units.

    The sheet gives the map NO gutter, so its bitmap is the wall and
    nothing else: the multi band pill and the circuit ruler the map draws
    over the wall's head fall outside it and are clipped away. Ink that
    never reaches the paper cannot be covered, so it is not lettering here.
    """
    a = half['map']['area']
    w, h = a['w'] * SCALE, a['h'] * SCALE
    return [{'kind': b['kind'], 'text': b['text'],
             'x': a['x'] + b['x'] / SCALE, 'y': a['y'] + b['y'] / SCALE,
             'w': b['w'] / SCALE, 'h': b['h'] / SCALE}
            for b in half['labels']
            if b['kind'] != 'wallEdge' and b['x'] + b['w'] > 0 and b['y'] + b['h'] > 0
            and b['x'] < w and b['y'] < h]


def _box_over(a, b, hair):
    return (min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x']) > hair
            and min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']) > hair)


def _seg_box(a, b, pad):
    return {'x': min(a[0], b[0]) - pad, 'y': min(a[1], b[1]) - pad,
            'w': abs(a[0] - b[0]) + 2 * pad, 'h': abs(a[1] - b[1]) + 2 * pad}


def _own_disc(box, d):
    """The one label a run is allowed to touch: the very disc it leaves."""
    return (box['kind'] == 'disc'
            and abs(box['x'] + box['w'] / 2 - d['x']) < 1.5
            and abs(box['y'] + box['h'] / 2 - d['y']) < 1.5)


def _is_stub(a, b, d, w):
    """The one crossing of the wall a run is allowed: straight off its own
    disc's edge, out to one of the wall's four edges - reaching it, and
    never running past the disc the other way. A run whose middle is
    covered leaves a hair to one side of it, so the line is anywhere on the
    disc rather than exactly through its centre."""
    if abs(b[1] - a[1]) < 0.01 and abs(b[0] - a[0]) >= 0.01:      # out at its own row
        if abs(a[1] - d['y']) > d['r'] + 0.01:
            return False
        if b[0] < a[0]:
            return min(a[0], b[0]) <= w['x'] + 0.5 and a[0] <= d['x'] + 0.01
        return max(a[0], b[0]) >= w['x'] + w['w'] - 0.5 and a[0] >= d['x'] - 0.01
    if abs(b[0] - a[0]) < 0.01 and abs(b[1] - a[1]) >= 0.01:      # up or down its column
        if abs(a[0] - d['x']) > d['r'] + 0.01:
            return False
        if b[1] < a[1]:
            return min(a[1], b[1]) <= w['y'] + 0.5 and a[1] <= d['y'] + 0.01
        return max(a[1], b[1]) >= w['y'] + w['h'] - 0.5 and a[1] >= d['y'] - 0.01
    return False


def _through_the_wall(half):
    """Every run segment with ink inside the wall's rectangle but for that
    one stub. This is the fault the user pointed at: a run travelling the
    inside of its own row across the whole wall, and turning down through
    the wall's other rows."""
    s = half['scale']
    w = _wall(half)
    discs = {d['text']: d for d in half['discs']}
    bad = []
    for r in half['runs']:
        d = discs[r['from']]
        for i, (a, b) in enumerate(zip(r['points'], r['points'][1:])):
            if not _box_over(_seg_box(a, b, 0.75 * s), w, 0.5 * s):
                continue
            if i == 0 and _is_stub(a, b, d, w):
                continue
            bad.append('%s: segment %d, (%.0f,%.0f)-(%.0f,%.0f), is inside the wall'
                       % (r['from'], i, a[0], a[1], b[0], b[1]))
    return bad


def _clear_ways_out(half, d):
    """The edges this disc could leave by without a mark on the map's own
    lettering, trying the run a hair to either side of the disc's middle -
    the way the sheet itself does."""
    s = half['scale']
    pad = CASE_PAD * s
    w = _wall(half)
    room = half['room']
    lab = [k for k in _labels(half) if not _own_disc(k, d)]
    out = []
    for edge in ('left', 'right', 'top', 'bottom'):
        for f in (0, 0.45, -0.45, 0.7, -0.7, 0.9, -0.9):
            t = f * d['r']
            q = math.sqrt(max(0.0, d['r'] ** 2 - t ** 2))
            if edge in ('left', 'right'):
                head = (d['x'] - q if edge == 'left' else d['x'] + q, d['y'] + t)
                far = (room['x0'] if edge == 'left' else room['x1'], d['y'] + t)
                gap = abs(head[0] - (w['x'] if edge == 'left' else w['x'] + w['w']))
            else:
                head = (d['x'] + t, d['y'] - q if edge == 'top' else d['y'] + q)
                far = (d['x'] + t, room['y0'] if edge == 'top' else room['y1'])
                gap = abs(head[1] - (w['y'] if edge == 'top' else w['y'] + w['h']))
            box = _seg_box(head, far, pad)
            if not [k for k in lab if _box_over(box, k, 0.5)]:
                out.append((edge, gap))
                break
    return out


def _covers_lettering(half):
    """Every piece of the map's own lettering a run is drawn over - a disc,
    a cable tag, a gang pill, a multi band or a ruler label - with its white
    casing counted, because the casing is what ate the S of "IMAG SR-6"."""
    s = half['scale']
    pad = CASE_PAD * s
    lab = _labels(half)
    discs = {d['text']: d for d in half['discs']}
    bad = []
    for r in half['runs']:
        d = discs[r['from']]
        for i, (a, b) in enumerate(zip(r['points'], r['points'][1:])):
            box = _seg_box(a, b, pad)
            for k in lab:
                if _own_disc(k, d) or not _box_over(box, k, 0.5):
                    continue
                bad.append('%s: segment %d is drawn over the %s "%s"'
                           % (r['from'], i, k['kind'], k['text']))
    return bad


def _dearer_way_out(half):
    """A run leaves by an edge the map left CLEAR - the nearer SIDE by
    preference, because a run beside the wall reads best and it is the
    drawing that was approved; an end only where both sides are blocked."""
    discs = {d['text']: d for d in half['discs']}
    bad = []
    for r in half['runs']:
        d = discs[r['from']]
        clear = _clear_ways_out(half, d)
        if not clear:
            continue                       # boxed in; the cheapest way stands
        a, b = r['points'][0], r['points'][1]
        took = ('left' if b[0] < a[0] else 'right') if abs(a[1] - b[1]) < 0.01 \
            else ('top' if b[1] < a[1] else 'bottom')
        if took not in [e for e, _g in clear]:
            bad.append('%s leaves by its %s, which the map had written on' % (r['from'], took))
            continue
        sides = [(e, g) for e, g in clear if e in ('left', 'right')]
        if sides and took not in ('left', 'right'):
            bad.append('%s leaves over the wall with its %s side clear' % (r['from'], sides[0][0]))
        elif sides and min(g for _e, g in sides) < dict(sides)[took] - 0.5:
            bad.append('%s leaves by the far side with the near one clear' % r['from'])
    return bad


def _check_off_the_wall(half):
    """The whole of the new rule on one half, so one failure names every
    fault on it."""
    bad = _through_the_wall(half) + _covers_lettering(half) + _dearer_way_out(half)
    assert not bad, '\n'.join(['', 'the %s half:' % half['side']] + ['  ' + b for b in bad])


def _check_blocks(half):
    """The blocks are flat units at the foot, spread across the width, none
    over the wall or over another, their sockets in a row inside them."""
    s = half['scale']
    m = half['map']
    for b in half['blocks']:
        assert abs(b['h'] - BOX_H * s) < 0.01, b
        assert not _overlap(b, {'x': m['x'], 'y': m['y'], 'w': m['w'], 'h': m['h']}), (
            'a block never sits over the wall', b, m)
        # A run comes down into its socket from above, so the unit's name
        # goes UNDER the row of numbers - on the line above, the run's white
        # casing ate the letters, and on the printer sheet it took the very
        # digit that tells SR3 from SR1.
        assert TITLE_DY > SOCKET_DY + SOCK, (TITLE_DY, SOCKET_DY, SOCK)
        assert NOTE_DY < SOCKET_DY - SOCK, (NOTE_DY, SOCKET_DY, SOCK)
        assert TITLE_DY < BOX_H, (TITLE_DY, BOX_H)
        for sk in b['sockets']:
            assert b['x'] < sk['x'] < b['x'] + b['w'], (sk, b)
            assert abs(sk['y'] - (b['y'] + SOCKET_DY * s)) < 0.01, (sk, b)
            assert abs(sk['r'] - SOCK * s) < 0.01, sk
    for i, a in enumerate(half['blocks']):
        for b in half['blocks'][i + 1:]:
            assert not _overlap(a, b), ('two blocks overprint', a, b)


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


# The sheet, its record, and - so "the discs are white with a black rim on
# the printer page" is a reading and not a hope - the painted pixel at
# every disc's centre and on its rim.
WIRING_JS = """([opts, title]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const r = app.renderBinderPage(opts, idx);
    const c = r.canvas, ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let coloured = 0;
    for (let i = 0; i < d.length; i += 4 * 61) {
        const R = d[i], G = d[i + 1], B = d[i + 2];
        if (Math.abs(R - G) > 10 || Math.abs(G - B) > 10 || Math.abs(R - B) > 10) coloured++;
    }
    const S = c.width / (r.record ? r.record.width : c.width);
    const at = (x, y) => { const p = ctx.getImageData(Math.round(x * S), Math.round(y * S), 1, 1).data;
                           return Math.min(p[0], p[1], p[2]); };
    // the darkest pixel on a ring of radius f * r, all the way round
    const ring = (k, f) => { let dark = 255;
        for (let i = 0; i < 24; i++) { const a = i / 24 * Math.PI * 2;
            dark = Math.min(dark, at(k.x + k.r * f * Math.cos(a), k.y + k.r * f * Math.sin(a))); }
        return dark; };
    const discPixels = (r.wiring ? r.wiring.halves : []).map(h => h.discs.map(k => ({
        text: k.text, middle: at(k.x, k.y),
        rim: Math.min(ring(k, 0.97), ring(k, 1.0), ring(k, 1.03)) })));
    return { texts: r.texts, wiring: r.wiring, bubble: r.bubble, page: r.page,
             plan: plan.map(p => [p.kind, p.number, p.title, p.view]),
             coloured, width: c.width, height: c.height, discPixels,
             ops: r.record.ops.map(o => o.op === 'line'
                    ? { op: 'line', n: o.points.length, width: o.width, dash: o.dash,
                        stroke: o.stroke, points: o.points }
                    : o.op === 'image' ? { op: 'image', x: o.x, y: o.y, w: o.w, h: o.h }
                    : { op: o.op }) };
}"""


# One sheet of the set as a PDF, through the same export route the app
# uses - for LRD_BINDER_PDF_DIR, so the sheet can be looked at (pdftoppm).
_PDF_JS = """async ([opts, title]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { status: 0, missing: title };
    const pages = app.renderBinderPages(opts, { bitmaps: false }).slice(idx, idx + 1);
    const resp = await fetch('/api/export/pdf-from-pages', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ project_name: app.project.name, pages }) });
    const buf = new Uint8Array(await resp.arrayBuffer());
    let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return { status: resp.status, b64: btoa(bin) };
}"""


# The same sheet, rendered with canvas.js's label registry running, so what
# the map wrote is readable beside what the sheet drew. A wiring sheet
# paints one map per half, in order, and r.render() is called once per map -
# so a mark taken at each call tells the two halves' boxes apart.
PROBE_JS = """([opts, title]) => {
    const app = window.app, r = window.canvasRenderer;
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const marks = [];
    const render = r.render;
    r.startLabelProbe();
    r.render = function (...a) {
        marks.push(r.labelProbe ? r.labelProbe.length : 0);
        return render.apply(this, a);
    };
    let res = null, boxes = [];
    try { res = app.renderBinderPage(opts, idx); }
    finally { r.render = render; boxes = r.endLabelProbe() || []; }
    const halves = (res.wiring && res.wiring.halves) || [];
    return { halves: halves.map((h, k) => ({ ...h,
        labels: boxes.slice(marks[k] == null ? 0 : marks[k],
                            marks[k + 1] == null ? boxes.length : marks[k + 1]) })) };
}"""


LOAD_JS = """async (project) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', project);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('wiring_smoke');
    app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
}"""


def _sheet(pg, opts, title):
    out = pg.evaluate(WIRING_JS, [opts, title])
    assert 'missing' not in out, out
    return out


def _probe(pg, opts, title):
    """One wiring sheet's halves, each with the map's own label boxes on
    it. The registry must have reached both maps, and every disc the sheet
    logged must be a disc the map really drew - which is also the check
    that the pixels-to-page-units conversion above is the right one."""
    out = pg.evaluate(PROBE_JS, [opts, title])
    assert 'missing' not in out, out
    halves = out['halves']
    assert halves, out
    for h in halves:
        assert [b for b in h['labels'] if b['kind'] == 'wallEdge'], (
            'the label registry never reached the %s half of %s' % (h['side'], title))
        lab = _labels(h)
        for d in h['discs']:
            assert [k for k in lab if _own_disc(k, d)], (
                'the sheet says there is a disc the map never drew', title, h['side'], d)
    return halves


def _half(out, side):
    halves = [h for h in out['wiring']['halves'] if h['side'] == side]
    assert len(halves) == 1, out['wiring']
    return halves[0]


def _socket(block, n):
    return next(s for s in block['sockets'] if s['n'] == n)


def _drop_pdf(pg, opts, title, name):
    out_dir = os.environ.get('LRD_BINDER_PDF_DIR')
    if not out_dir:
        return
    pdf = pg.evaluate(_PDF_JS, [opts, title])
    assert pdf['status'] == 200, pdf['status']
    with open(os.path.join(out_dir, name), 'wb') as fh:
        fh.write(base64.b64decode(pdf['b64']))


def test_the_sheet_is_the_screens_third_and_runs_its_port_and_its_circuits(page):
    """WALL-A (4 x 3, one port on card SR's socket 1 - no unit, no backup -
    two circuits on SR1 at 125'): sheet 2.3 "WALL-A · SIGNAL + POWER", view
    4, its bubble under the lower half. SIGNAL: the wall's own disc "SR-1"
    (no tag of ours over it), one CARD block "H9 SR · H_16xRJ45+2xfiber"
    with 16 sockets - socket 1 green, the rest grey rings - and one run
    from the disc onto socket 1, cased in white. POWER: two orange discs,
    one BREAKOUT block "SR1 · Multi 208 breakout · 125'" with six sockets,
    1 and 2 orange, and two runs. Both halves inside the drawing area, the
    signal half over the rule, the power half under it; the two walls are
    the two images; the printer sheet has no colour."""
    pg, ids = page
    out = _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')
    assert out['plan'][:4] == [['overview', '1.1', 'Overview', 1], ['power', '2.1', 'WALL-A - Power', 2],
                               ['data', '2.2', 'WALL-A - Data', 3], ['wiring', '2.3', 'WALL-A - Signal + Power', 4]]
    assert out['width'] == W * SCALE and out['height'] == H * SCALE
    texts = out['texts']
    _title_block(texts, 'WALL-A · SIGNAL + POWER', '2.3')
    assert out['page']['layout'] == 'wiring' and out['page']['cols'] == 2 and out['page']['view'] == 4
    assert out['page']['sides'] == {'power': True, 'data': True}
    assert [h['side'] for h in out['page']['halves']] == ['signal', 'power']
    assert out['bubble']['number'] == 4 and out['bubble']['name'] == 'WALL-A · SIGNAL + POWER'
    assert 'SIGNAL' in texts and 'POWER' in texts and texts.index('SIGNAL') < texts.index('POWER')
    sig, pwr = out['wiring']['halves']
    assert [h['side'] for h in (sig, pwr)] == ['signal', 'power']
    # the prototype's page carried across at K = the half's width / 1000
    for h in (sig, pwr):
        assert abs(h['scale'] - K) < 0.001, h['scale']
    # the signal half: the wall's own disc is the origin
    assert [(d['text'], d['kind'], d['placed']) for d in sig['discs']] == [('SR-1', 'primary', True)]
    disc = sig['discs'][0]
    m = sig['map']
    p = disc['panel']
    assert abs(disc['x'] - (p['x'] + p['w'] / 2)) <= p['w'] / 2 + 0.01, (disc, p)
    assert abs(disc['y'] - (p['y'] + p['h'] / 2)) <= p['h'] / 2 + 0.01, (disc, p)
    assert m['x'] <= disc['x'] <= m['x'] + m['w'] / 4, (disc, m)      # the first column
    assert m['y'] <= disc['y'] <= m['y'] + m['h'] / 4, (disc, m)      # the top row
    assert [b['title'] for b in sig['blocks']] == ['H9 SR · H_16xRJ45+2xfiber']
    card = sig['blocks'][0]
    assert [s['n'] for s in card['sockets']] == list(range(1, 17))
    assert [s['state'] for s in card['sockets']] == ['primary'] + ['free'] * 15
    assert [(w['from'], w['device'], w['socket'], w['kind']) for w in sig['runs']] == \
        [('SR-1', 'H9 SR · H_16xRJ45+2xfiber', 1, 'primary')]
    _check_runs(sig, out)
    _check_blocks(sig)
    run = sig['runs'][0]
    assert _c(run['colour']) == GREEN and run['dash'] == []
    assert abs(run['width'] - RUN_W * sig['scale']) < 0.01
    assert abs(_casing_of(out, run)['width'] - (RUN_W + CASE_EXTRA) * sig['scale']) < 0.05
    # the blocks stand under the wall, at the foot of the half
    assert card['y'] > m['y'] + m['h'], (card, m)
    # the power half
    assert [(d['text'], d['kind']) for d in pwr['discs']] == [('SR1-1', 'power'), ('SR1-2', 'power')]
    assert [b['title'] for b in pwr['blocks']] == ["SR1 · Multi 208 breakout · 125'"]
    bk = pwr['blocks'][0]
    assert [(s['n'], s['state'], s['note']) for s in bk['sockets']] == \
        [(1, 'power', None), (2, 'power', None), (3, 'free', None), (4, 'free', None),
         (5, 'free', None), (6, 'free', None)]
    assert [(w['from'], w['socket']) for w in pwr['runs']] == [('SR1-1', 1), ('SR1-2', 2)]
    # a hue per breakout: the one multi takes the first
    assert all(_c(w['colour']) == HUES[0] and w['dash'] == [] for w in pwr['runs'])
    _check_runs(pwr, out)
    _check_blocks(pwr)
    # the halves: the signal one wholly over the power one, both in the
    # drawing area, the walls the two images in that order
    sig_bottom = max(b['y'] + b['h'] for b in sig['blocks'])
    assert sig_bottom <= pwr['map']['area']['y'], (sig_bottom, pwr['map'])
    for h in (sig, pwr):
        for r in h['blocks']:
            assert _inside(r, DA), (h['side'], r)
        assert _inside(h['map']['area'], DA), h['map']
    images = [o for o in out['ops'] if o['op'] == 'image']
    assert len(images) == 2
    assert (images[0]['x'], images[0]['y'], images[0]['w'], images[0]['h']) == tuple(sig['map']['area'][k] for k in 'xywh')
    assert (images[1]['x'], images[1]['y'], images[1]['w'], images[1]['h']) == tuple(pwr['map']['area'][k] for k in 'xywh')
    bubble = out['bubble']
    assert bubble['y'] - bubble['r'] >= max(b['y'] + b['h'] for b in pwr['blocks']) \
        and bubble['y'] + bubble['r'] <= DA['y'] + DA['h'] + 1
    # every socket a polyline circle, never the bubble's 37 points
    assert len([o for o in out['ops'] if o['op'] == 'line' and o['n'] == 37]) == 1
    # every text logged is an op; no sheet word is "box", "tail" or the
    # generic breakout
    assert not [t for t in texts if BOX_WORD.search(t) and 'breakout box' not in t.lower()], texts
    assert not _generic_breakout(texts), _generic_breakout(texts)
    assert not [t for t in texts if re.search(r'\btails?\b', t.lower())], texts
    # the printer sheet: no colour, black runs
    printer = _sheet(pg, {**json.loads(_SHOW_JSON), 'palette': 'printer'}, 'WALL-A - Signal + Power')
    assert printer['coloured'] == 0
    psig, ppwr = printer['wiring']['halves']
    assert all(_c(w['colour']) == INK for w in psig['runs'] + ppwr['runs'])
    assert ids['errors'] == []


def test_a_return_lands_on_its_own_block_and_a_unit_replaces_the_card(page):
    """"one per cvt including backups": a CVT4K-S on card SR delivers WALL-A's
    port, a second card (its 1:1 partner) carries its return through its own
    CVT4K-S named BK. The signal half then has TWO discs - the primary
    "SR-1" on the run's FIRST PANEL, the return "BK-1" on its LAST - and
    TWO blocks, "CVT4K-S SR · SR · OPT 1-2" with socket 1 green and
    "CVT4K-S BK · slot 2 · OPT 1-2" with socket 1 red; two runs, the
    return's red and dashed - finely dashed into a hollow socket on the
    printer sheet."""
    pg, ids = page
    setup = pg.evaluate("""async (ids) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
        let st = await j('POST', `/api/processors/${ids.procId}/cards/${ids.cardId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[0].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxId}`, {name: 'SR'});
        st = await j('PUT', `/api/processors/${ids.procId}/slots/1`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const backupId = st.processors[0].slots[1].card.id;
        st = await j('POST', `/api/processors/${ids.procId}/cards/${backupId}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const backupBox = st.processors[0].slots[1].card.cvts[0].id;
        await j('PUT', `/api/processors/${ids.procId}/cvts/${backupBox}`, {name: 'BK'});
        await j('PUT', `/api/processors/${ids.procId}`, {redundancy: true});
        await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: backupId});
        await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        return { boxId, backupId, backupBox };
    }""", ids)
    try:
        out = _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')
        sig = _half(out, 'signal')
        assert [(d['text'], d['kind']) for d in sig['discs']] == [('SR-1', 'primary'), ('BK-1', 'return')], sig['discs']
        m = sig['map']
        first, last = sig['discs']
        assert first['x'] < m['x'] + m['w'] / 4 and last['x'] > m['x'] + m['w'] * 3 / 4, (first, last, m)
        # each on the very panel its run begins / ends on, and the run of a
        # 4 x 3 wall ends on the bottom row: the return's disc is lower
        assert last['y'] > first['y'], (first, last)
        assert [b['title'] for b in sig['blocks']] == ['CVT4K-S SR · SR · OPT 1-2', 'CVT4K-S BK · slot 2 · OPT 1-2'], sig['blocks']
        a, b = sig['blocks']
        assert len(a['sockets']) == 16 and len(b['sockets']) == 16
        assert [s['state'] for s in a['sockets']] == ['primary'] + ['free'] * 15
        assert [s['state'] for s in b['sockets']] == ['return'] + ['free'] * 15
        assert [(w['from'], w['device'], w['socket'], w['kind'], _c(w['colour'])) for w in sig['runs']] == [
            ('SR-1', 'CVT4K-S SR · SR · OPT 1-2', 1, 'primary', GREEN),
            ('BK-1', 'CVT4K-S BK · slot 2 · OPT 1-2', 1, 'return', RED)]
        s = sig['scale']
        assert [len(w['dash']) for w in sig['runs']] == [0, 2]
        assert [round(v / s, 2) for v in sig['runs'][1]['dash']] == RETURN_DASH
        _check_runs(sig, out)
        _check_blocks(sig)
        # the blocks side by side at the foot, the two of them spread over
        # the width the half has
        assert a['x'] + a['w'] < b['x'] and abs(a['y'] - b['y']) < 0.01
        assert abs(a['x'] - (DA['x'] + MARGIN * s)) < 0.5, (a, s)
        assert abs((b['x'] + b['w']) - (DA['x'] + (PROTO_W - MARGIN) * s)) < 0.5, (b, s)
        assert not [t for t in out['texts'] if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
        printer = _sheet(pg, {**json.loads(_SHOW_JSON), 'palette': 'printer'}, 'WALL-A - Signal + Power')
        psig = _half(printer, 'signal')
        assert [_c(w['colour']) for w in psig['runs']] == [INK, INK]
        assert [len(w['dash']) for w in psig['runs']] == [0, 2]
        assert [round(v / psig['scale'], 2) for v in psig['runs'][1]['dash']] == PRINTER_RETURN_DASH
        # a primary lands in a filled socket, a return in a hollow one
        pa, pb = psig['blocks']
        assert _c(_socket(pa, 1)['fill']) == INK and _c(_socket(pb, 1)['fill']) == WHITE
        assert _c(_socket(pb, 1)['rim']) == INK
        assert printer['coloured'] == 0
    finally:
        pg.evaluate("""async ([ids, s]) => {
            const app = window.app;
            const j = (method, url, body) => fetch(url, {method,
                headers: {'Content-Type': 'application/json'},
                body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
            await j('PUT', `/api/processors/${ids.procId}/cards/${ids.cardId}`, {backupCardId: null});
            await j('PUT', `/api/processors/${ids.procId}`, {redundancy: false});
            await j('DELETE', `/api/processors/${ids.procId}/cvts/${s.backupBox}`);
            await j('DELETE', `/api/processors/${ids.procId}/cvts/${s.boxId}`);
            await app.refreshProcessors(); await app.refreshPortAssignment(); app.renderLayers();
        }""", [ids, setup])
    after = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'signal')
    assert [b['title'] for b in after['blocks']] == ['H9 SR · H_16xRJ45+2xfiber']
    assert ids['errors'] == []


def test_a_shared_multi_shows_the_other_screens_circuits_against_its_socket(page):
    """WALL-B's multi moved onto SR's number 1 - the multi WALL-A is on: on
    WALL-A's sheet the SR1 breakout shows WALL-B's circuits as unfilled
    sockets with "WALL-B" printed against them (the hover text, on paper),
    WALL-A's own in the breakout's hue; on WALL-B's sheet the mirror. A
    note earns its place only where it says something the socket number
    does not, so WALL-A's own sockets carry none."""
    pg, ids = page
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(l => l.id === ids.b);
        app.setSocaNumber(b, 1, 1);
        app._circuitTailCache = null;
        app.renderLayers();
    }""", ids)
    try:
        out = _sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power')
        a_side = _half(out, 'power')
        assert len(a_side['blocks']) == 1 and a_side['blocks'][0]['title'].startswith('SR1 · Multi 208 breakout'), a_side['blocks']
        socks = a_side['blocks'][0]['sockets']
        mine = [s['n'] for s in socks if s['state'] == 'power']
        theirs = [(s['n'], s['note']) for s in socks if s['state'] == 'other']
        assert len(mine) == 2 and len(theirs) == 2 and all(n == 'WALL-B' for _k, n in theirs), socks
        assert not set(mine) & {k for k, _n in theirs}
        assert [s['note'] for s in socks if s['state'] == 'power'] == [None, None], socks
        assert [s['n'] for s in socks if s['state'] == 'free'] == sorted(set(range(1, 7)) - set(mine) - {k for k, _n in theirs})
        assert 'WALL-B' in out['texts']
        b_side = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-B - Signal + Power'), 'power')
        bsocks = b_side['blocks'][0]['sockets']
        assert sorted(s['n'] for s in bsocks if s['state'] == 'power') == sorted(k for k, _n in theirs)
        assert [(s['n'], s['note']) for s in bsocks if s['state'] == 'other'] == [(n, 'WALL-A') for n in mine]
    finally:
        pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(l => l.id === ids.b);
            app.setSocaNumber(b, 1, 2);
            app._circuitTailCache = null;
            app.renderLayers();
        }""", ids)
    restored = _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'power')
    assert [s['state'] for s in restored['blocks'][0]['sockets']] == ['power', 'power', 'free', 'free', 'free', 'free']
    assert ids['errors'] == []


def test_the_tick_takes_the_sheets_out_and_a_side_alone_draws_one_half(page):
    """The dialog's "Signal + Power" tick is on by default and stays on for
    a single-screen scope (it is that screen's sheet); off, no sheet is
    planned and the numbering closes up; the Maps radio on one side makes
    the sheet that half alone; the CONTENTS follows either way."""
    pg, ids = page
    out = pg.evaluate("""(o) => {
        const app = window.app;
        document.getElementById('export-format').value = 'binder';
        document.getElementById('export-format').dispatchEvent(new Event('change'));
        const tick = document.getElementById('export-binder-wiring');
        const dflt = { checked: tick.checked, read: app.readBinderOptions().wiring };
        tick.checked = false;
        const off = app.readBinderOptions().wiring;
        tick.checked = true;
        const scope = document.getElementById('export-binder-scope');
        scope.value = [...scope.options].find(x => x.value.startsWith('screen:')).value;
        scope.dispatchEvent(new Event('change'));
        const single = { wiring: document.getElementById('export-binder-wiring').checked,
                         cover: document.getElementById('export-binder-cover').checked };
        scope.value = 'show'; scope.dispatchEvent(new Event('change'));
        document.getElementById('export-cancel').click();
        const plan = (opts) => app.planBinder(opts).map(p => [p.kind, p.number, p.title, p.view]);
        const contents = (opts) => {
            const t = app.renderBinderPage(opts, 0).texts;
            const c = t.indexOf('CONTENTS');
            return t.slice(c + 3);
        };
        return { dflt, off, single,
                 without: plan({ ...o, wiring: false }), contentsWithout: contents({ ...o, wiring: false }),
                 power: plan({ ...o, sides: { power: true, data: false } }),
                 data: plan({ ...o, sides: { power: false, data: true }, cover: false, pull: false, hardware: false }),
                 sides: app.planBinder({ ...o, sides: { power: false, data: true } }).filter(p => p.kind === 'wiring').map(p => p.sides) };
    }""", json.loads(_SHOW_JSON))
    assert out['dflt'] == {'checked': True, 'read': True}
    assert out['off'] is False
    assert out['single'] == {'wiring': True, 'cover': False}
    assert out['without'] == [
        ['overview', '1.1', 'Overview', 1],
        ['power', '2.1', 'WALL-A - Power', 2], ['data', '2.2', 'WALL-A - Data', 3],
        ['power', '2.3', 'WALL-B - Power', 4], ['data', '2.4', 'WALL-B - Data', 5],
        ['power', '2.5', 'CENTER - Power', 6], ['data', '2.6', 'CENTER - Data', 7],
        ['pull', '3.1', 'Pull - SR Beach, CENTER', None], ['distro', '4.1', 'Distro - SR', None],
        ['processor', '4.2', 'Processor - H9 · Pull list', None]]
    listed = out['contentsWithout']
    assert listed[:6] == ['1.1', 'OVERVIEW', '2.1', 'WALL-A · POWER', '2.2', 'WALL-A · DATA'] and 'SIGNAL + POWER' not in ' '.join(listed)
    assert out['power'][1:5] == [['power', '2.1', 'WALL-A - Power', 2], ['wiring', '2.2', 'WALL-A - Signal + Power', 3],
                                 ['power', '2.3', 'WALL-B - Power', 4], ['wiring', '2.4', 'WALL-B - Signal + Power', 5]]
    assert out['data'][:2] == [['data', '2.1', 'WALL-A - Data', 1], ['wiring', '2.2', 'WALL-A - Signal + Power', 2]]
    assert out['sides'] == [{'power': False, 'data': True}] * 3
    # the one-sided sheet: the one half, no rule, the bubble still under it
    one = _sheet(pg, {**json.loads(_SHOW_JSON), 'sides': {'power': True, 'data': False}}, 'WALL-A - Signal + Power')
    assert [h['side'] for h in one['wiring']['halves']] == ['power'] and 'SIGNAL' not in one['texts']
    assert len([o for o in one['ops'] if o['op'] == 'image']) == 1
    pwr = one['wiring']['halves'][0]
    assert pwr['map']['h'] > _half(_sheet(pg, json.loads(_SHOW_JSON), 'WALL-A - Signal + Power'), 'power')['map']['h'], 'the half alone has the height'
    assert one['bubble'] and one['bubble']['y'] - one['bubble']['r'] >= max(b['y'] + b['h'] for b in pwr['blocks'])
    _check_runs(pwr, one)
    _check_blocks(pwr)
    assert ids['errors'] == []


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
def test_smoke_experts_only_sr_main(page):
    """The frozen Experts Only show, SR - MAIN's SIGNAL + POWER on Tabloid
    (2.9, view 10).

    POWER: 22 circuits on four multis; FOUR BREAKOUT BLOCKS IN ONE ROW at
    the foot, ordered by the mean position of their own circuits - SR3 and
    SR4 stand on the wall's left column, SR1 and SR2 on its right, so the
    row reads SR3 SR4 SR1 SR2 - and none of them over the wall or over
    another. Fifteen runs are TWO SEGMENTS, out at their own row and
    straight down into a socket already clear of the wall; the seven whose
    sockets stand UNDER the wall come down a rail beside it and back along
    a lane under its foot. No two horizontals overlap, no two verticals do.
    A white casing under every run.

    SIGNAL: four primaries and four returns onto TWO blocks in ONE row
    (the wrap-and-cross regression: a note that only repeated its socket
    number widened the blocks until the pair wrapped); primaries solid,
    returns dashed, and not one socket note repeating its own number.

    PRINTER: no colour anywhere, a dash of its own per device, and the
    wall's discs white with a black rim - read off the painted pixels."""
    pg, ids = page
    with open(SCRATCH_FIXTURE) as fh:
        project = json.load(fh)
    pg.evaluate(LOAD_JS, project)
    opts = json.loads(_SHOW_JSON)
    out = _sheet(pg, opts, 'SR - MAIN - Signal + Power')
    plan = out['plan']
    assert [p[1:3] for p in plan if p[2].startswith('SR - MAIN')] == \
        [['2.7', 'SR - MAIN - Power'], ['2.8', 'SR - MAIN - Data'], ['2.9', 'SR - MAIN - Signal + Power']]
    assert len(plan) == 16 and [p[3] for p in plan][:13] == list(range(1, 14)) and [p[3] for p in plan][13:] == [None] * 3
    _title_block(out['texts'], 'SR - MAIN · SIGNAL + POWER', '2.9', show='2026 Experts Only')
    assert out['bubble']['number'] == 10 and out['bubble']['name'] == 'SR - MAIN · SIGNAL + POWER'
    sig, pwr = out['wiring']['halves']
    assert sig['side'] == 'signal' and pwr['side'] == 'power'

    # ---- power ----------------------------------------------------------
    assert len(pwr['discs']) == 22 and all(d['kind'] == 'power' and d['placed'] for d in pwr['discs'])
    assert sorted(d['text'] for d in pwr['discs']) == sorted(f'SR{k}-{n}' for k, ns in
                                                             ((1, range(1, 7)), (2, range(2, 7)), (3, range(1, 7)), (4, (1, 2, 4, 5, 6)))
                                                             for n in ns)
    assert [b['title'] for b in pwr['blocks']] == ["SR3 · Multi 208 breakout · 125'", "SR4 · Multi 208 breakout · 100'",
                                                   "SR1 · Multi 208 breakout · 125'", "SR2 · Multi 208 breakout · 100'"], pwr['blocks']
    assert pwr['rows'] == 1 and len({round(b['y'], 2) for b in pwr['blocks']}) == 1
    # ordered by where their own circuits stand on the wall
    mean = {}
    for d in pwr['discs']:
        mean.setdefault(d['text'].split('-')[0], []).append(d['x'])
    order = [b['title'][:3] for b in pwr['blocks']]
    means = [sum(mean[k]) / len(mean[k]) for k in order]
    assert all(a <= b + 1e-6 for a, b in zip(means, means[1:])), (order, means)
    # a hue per breakout, in the order the facts read them
    assert {b['title'][:3]: _c(b['hue']) for b in pwr['blocks']} == \
        {'SR1': HUES[0], 'SR2': HUES[1], 'SR3': HUES[2], 'SR4': HUES[3]}
    states = {b['title'][:3]: [(s['n'], s['state'], s['note']) for s in b['sockets']] for b in pwr['blocks']}
    assert sum(1 for v in states.values() for _n, st, _note in v if st == 'power') == 22
    assert states['SR2'][0] == (1, 'free', None) and states['SR4'][2] == (3, 'free', None), states
    assert not [x for v in states.values() for x in v if x[1] == 'other']
    assert len(pwr['runs']) == 22
    _check_runs(pwr, out)
    _check_blocks(pwr)
    shapes = [_segs(r) for r in pwr['runs']]
    # TWO SEGMENTS WHERE TWO SUFFICE: SR3's and SR2's blocks stand clear of
    # the wall on the side their circuits leave by, so those fifteen runs go
    # out at their own row and straight down - the drawing that was
    # approved. SR4's and SR1's stand UNDER the wall, so their seven come
    # down a rail beside it and back along a lane under its foot.
    assert shapes.count(['h', 'v']) == 15 and shapes.count(['h', 'v', 'h', 'v']) == 7, shapes
    assert not [s for s in shapes if s[0] != 'h'], ('every circuit leaves by a side', shapes)
    m = pwr['map']
    for r, s in zip(pwr['runs'], shapes):
        if s != ['h', 'v', 'h', 'v']:
            continue
        rail = r['points'][1][0]
        assert rail < m['x'] or rail > m['x'] + m['w'], ('the rail stands past the wall', r, m)
        lane = r['points'][2][1]
        assert m['y'] + m['h'] < lane < min(b['y'] for b in pwr['blocks']), (
            'the lane runs under the wall and over the blocks', r, m)

    # ---- signal ---------------------------------------------------------
    assert [d['text'] for d in sig['discs'] if d['kind'] == 'primary'] == ['SR A-1', 'SR A-2', 'SR A-3', 'SR A-4']
    assert [d['text'] for d in sig['discs'] if d['kind'] == 'return'] == ['SR B-1', 'SR B-2', 'SR B-3', 'SR B-4']
    sm = sig['map']
    # the runs go across the 28 columns and snake: every primary begins in
    # column 1; ports 1-3 end in column 28, port 4 (an odd count of rows)
    # back in column 1
    for d in sig['discs']:
        if d['kind'] == 'primary' or d['text'] == 'SR B-4':
            assert d['x'] < sm['x'] + sm['w'] / 28 + 1, (d, sm)
        else:
            assert d['x'] > sm['x'] + sm['w'] * 27 / 28 - 1, (d, sm)
    prim = [d for d in sig['discs'] if d['kind'] == 'primary']
    ph = prim[0]['panel']['h']
    assert all(abs((b['y'] - a['y']) - 3 * ph) < 0.02 for a, b in zip(prim, prim[1:])), (
        'the four primaries begin three rows apart - rows 1, 4, 7, 10', prim)
    assert [b['title'] for b in sig['blocks']] == ['CVT4K-S SR A · Card 1 · OPT 1-2', 'CVT4K-S SR B · Card 3 · OPT 1-2']
    assert sig['rows'] == 1 and len({round(b['y'], 2) for b in sig['blocks']}) == 1
    a, b = sig['blocks']
    assert [s['state'] for s in a['sockets']] == ['primary'] * 4 + ['free'] * 12
    assert [s['state'] for s in b['sockets']] == ['return'] * 4 + ['free'] * 12
    # not one note repeats the socket number it stands against
    assert not [s for bl in sig['blocks'] for s in bl['sockets']
                if s['note'] and (s['note'] == str(s['n']) or s['note'].endswith('-%d' % s['n']))], sig['blocks']
    assert [(w['from'], w['socket'], w['kind']) for w in sig['runs']] == [
        ('SR A-1', 1, 'primary'), ('SR B-1', 1, 'return'), ('SR A-2', 2, 'primary'), ('SR B-2', 2, 'return'),
        ('SR A-3', 3, 'primary'), ('SR B-3', 3, 'return'), ('SR A-4', 4, 'primary'), ('SR B-4', 4, 'return')]
    _check_runs(sig, out)
    _check_blocks(sig)
    assert {_c(w['colour']) for w in sig['runs'] if w['kind'] == 'primary'} == {GREEN}
    assert {_c(w['colour']) for w in sig['runs'] if w['kind'] == 'return'} == {RED}
    assert [len(w['dash']) for w in sig['runs'] if w['kind'] == 'primary'] == [0] * 4
    assert [len(w['dash']) for w in sig['runs'] if w['kind'] == 'return'] == [2] * 4
    # everything in the drawing area, the halves apart
    for h in (sig, pwr):
        for r in h['blocks']:
            assert _inside(r, DA), (h['side'], r)
    assert max(bl['y'] + bl['h'] for bl in sig['blocks']) <= pwr['map']['area']['y']
    # the CONTENTS
    ov = pg.evaluate("(o) => window.app.renderBinderPage(o, 0).texts", opts)
    c = ov.index('CONTENTS')
    listed = [(ov[c + 3 + 2 * n], ov[c + 4 + 2 * n]) for n in range(len(plan))]
    assert listed[7:10] == [('2.7', 'SR - MAIN · POWER'), ('2.8', 'SR - MAIN · DATA'), ('2.9', 'SR - MAIN · SIGNAL + POWER')]
    # the words
    assert not [t for t in out['texts'] if BOX_WORD.search(t) and 'breakout box' not in t.lower()]
    assert not _generic_breakout(out['texts']) and not [t for t in out['texts'] if re.search(r'\btails?\b', t.lower())]

    # ---- the printer palette -------------------------------------------
    pr_opts = {**opts, 'palette': 'printer'}
    printer = _sheet(pg, pr_opts, 'SR - MAIN - Signal + Power')
    assert printer['coloured'] == 0
    psig, ppwr = printer['wiring']['halves']
    assert all(_c(w['colour']) == INK for w in psig['runs'] + ppwr['runs'])
    # a dash of its own per device on power - four breakouts, four patterns
    dashes = {}
    for w in ppwr['runs']:
        dashes.setdefault(w['device'][:3], set()).add(tuple(round(v, 2) for v in w['dash']))
    assert all(len(v) == 1 for v in dashes.values()), dashes
    patterns = [next(iter(v)) for v in dashes.values()]
    assert len(set(patterns)) == 4, patterns
    # on data a primary is solid and a return finely dashed
    assert [w['dash'] for w in psig['runs'] if w['kind'] == 'primary'] == [[]] * 4
    assert [[round(v / psig['scale'], 2) for v in w['dash']] for w in psig['runs'] if w['kind'] == 'return'] == \
        [PRINTER_RETURN_DASH] * 4
    # the wall's own discs: white in the middle, a black rim
    for pixels in printer['discPixels']:
        assert pixels, printer['discPixels']
        for k in pixels:
            # the centre falls between the label's lines: the disc's face
            assert k['middle'] > 200, ('a disc is white on the press', k)
            assert k['rim'] < 150, ('and wears a black rim', k)
    _check_blocks(ppwr)
    _check_runs(ppwr, printer)

    _drop_pdf(pg, opts, 'SR - MAIN - Signal + Power', 'sr-main-signal-power.pdf')
    _drop_pdf(pg, pr_opts, 'SR - MAIN - Signal + Power', 'sr-main-signal-power-printer.pdf')
    assert ids['errors'] == []


@pytest.mark.skipif(not os.path.exists(KELLY_FIXTURE),
                    reason='kelly.json smoke fixture not present')
def test_a_row_of_circuits_leaves_by_the_top_and_an_unplaced_port_draws_no_run(page):
    """Kelly Clarkson's SR, frozen: a VERTICAL FLOW - every circuit begins
    on the wall's TOP ROW, so the discs stand shoulder to shoulder along it
    with a cable tag between each pair. Only the two at the ends can leave
    by a side; the rest are blocked both ways by their neighbours and go up
    out of their own column instead, and not one of them crosses the wall
    to get out. And the screen's six ports are on no card: the half draws
    their discs, no run at all, and prints "6 of 6 not placed on any card"
    once."""
    pg, ids = page
    with open(KELLY_FIXTURE) as fh:
        project = json.load(fh)
    pg.evaluate(LOAD_JS, project)
    opts = json.loads(_SHOW_JSON)
    out = _sheet(pg, opts, 'SR - Signal + Power')
    sig, pwr = out['wiring']['halves']

    # the vertical flow
    m = pwr['map']
    assert len(pwr['discs']) == 5 and len(pwr['blocks']) == 1
    assert len({round(d['y'], 2) for d in pwr['discs']}) == 1, ('every circuit on the top row', pwr['discs'])
    assert pwr['discs'][0]['y'] < m['y'] + m['h'] / 4, (pwr['discs'][0], m)
    _check_runs(pwr, out)
    _check_blocks(pwr)
    shapes = [_segs(r) for r in pwr['runs']]
    assert shapes.count(['h', 'v']) == 2, ('the two on the ends leave by their side', shapes)
    assert len([s for s in shapes if s[0] == 'v']) == 3, (
        'the three shut in leave by an end of their own column', shapes)
    for r, sh in zip(pwr['runs'], shapes):
        if sh[0] != 'v':
            continue
        head, turn = r['points'][0], r['points'][1]
        assert head[1] < m['y'] + m['h'] / 4, ('off a disc on the top row', r, m)
        assert turn[1] < m['y'] or turn[1] > m['y'] + m['h'], (
            'and clear of the wall before it turns', r, m)

    # the ports on no card
    assert len(sig['discs']) == 6 and not any(d['placed'] for d in sig['discs'])
    assert sig['runs'] == [] and sig['blocks'] == []
    assert sig['unplaced'] == 6 and sig['total'] == 6
    line = [t for t in out['texts'] if 'not placed on any card' in t]
    assert len(line) == 1 and line[0].startswith('6 of 6 not placed on any card'), out['texts']
    _drop_pdf(pg, opts, 'SR - Signal + Power', 'kelly-sr-signal-power.pdf')
    assert ids['errors'] == []


@pytest.mark.skipif(not os.path.exists(KELLY_FIXTURE),
                    reason='kelly.json smoke fixture not present')
@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_the_dj_booth_sheet_the_user_pointed_at(page, palette):
    """Page 4 of the user's own rev 1.3 export. A 9 x 2 wall whose label
    discs sit at the ENDS of its rows - DJ-1 and DJ-3 at the left, DJ-2 and
    DJ-4 at the right - with the card block under the middle of it. Every
    run used to leave its disc and travel the INSIDE of its own row the
    whole width of the wall, straight through that port's own "25'" cable
    tag and over the screen's daisy-chain arrows, and then turn down through
    the second row: all four tags cut and unreadable. Now each one goes
    STRAIGHT OUT to the end of the wall it is already at, down a rail beside
    it, and back along a lane under its foot - four segments, and nothing of
    the wall crossed but the stub off its own disc."""
    pg, ids = page
    with open(KELLY_FIXTURE) as fh:
        pg.evaluate(LOAD_JS, json.load(fh))
    opts = {**json.loads(_SHOW_JSON), 'palette': palette}
    halves = _probe(pg, opts, 'DJ Booth - Signal + Power')
    sig = next(h for h in halves if h['side'] == 'signal')
    assert [d['text'] for d in sig['discs']] == ['DJ-1', 'DJ-2', 'DJ-3', 'DJ-4'], sig['discs']
    assert len({round(d['y'], 2) for d in sig['discs']}) == 2, ('two rows of discs', sig['discs'])
    w = _wall(sig)
    ends = sorted(round((d['x'] - w['x']) / w['w'], 2) for d in sig['discs'])
    assert ends[1] < 0.15 and ends[2] > 0.85, ('the discs sit at the ends of their rows', ends)
    for h in halves:
        _check_off_the_wall(h)
        _check_runs(h)
        _check_blocks(h)
        assert [_segs(r) for r in h['runs']] == [['h', 'v', 'h', 'v']] * len(h['runs']), (
            h['side'], [_segs(r) for r in h['runs']])
    assert ids['errors'] == []


# ---- a run never crosses the wall, and never covers a label --------------
#
# The user's own export, rev 1.3: on page 4, DJ BOOTH · SIGNAL + POWER, the
# label discs sit at the ENDS of a 9 x 2 wall's rows and the blocks under
# its middle, so every run left its disc and travelled the INSIDE of its
# own row the whole width of the wall - through that port's own "25'" cable
# tag, over the screen's daisy-chain arrows - and then turned down through
# the second row. On page 7, SR, the same fault ate the S of "IMAG SR-6".
# "We still have lines going over text labels"; "extensions shouldnt be
# covered either".

def _sweep_off_the_wall(pg, fixture, palette, titles):
    with open(fixture) as fh:
        pg.evaluate(LOAD_JS, json.load(fh))
    opts = {**json.loads(_SHOW_JSON), 'palette': palette}
    seen = 0
    for title in titles:
        for h in _probe(pg, opts, title):
            _check_off_the_wall(h)
            _check_runs(h)
            _check_blocks(h)
            if h['runs']:
                assert h['rows'] == 1, ('the blocks stand in one row', title, h['side'], h['rows'])
            seen += len(h['runs'])
    return seen


@pytest.mark.skipif(not os.path.exists(KELLY_LIVE),
                    reason='kelly-live-fixture.json smoke fixture not present')
@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_kelly_live_runs_travel_outside_the_wall(page, palette):
    """Kelly Clarkson as the user exported her - UPSTAGE 22 x 7, SR and SL
    9 x 6, both palettes.

    SR's signal half is where it was clearest: the card block spans the
    sheet's width, so sockets 9-14 stand directly beneath the wall and
    every return dropped through the wall's interior, across the "SR B" and
    "SR C" tags and through the disc it had just left. Not one segment of
    any run may be inside the wall now but the stub from its own disc out
    to the nearest edge, and not one may be drawn over a disc, a cable tag,
    a gang pill, a band or a ruler label."""
    pg, ids = page
    n = _sweep_off_the_wall(pg, KELLY_LIVE, palette,
                            ['SR - Signal + Power', 'SL - Signal + Power',
                             'UPSTAGE - Signal + Power'])
    assert n >= 40, ('the sweep read almost no runs at all', n)
    assert ids['errors'] == []


@pytest.mark.skipif(not os.path.exists(SCRATCH_FIXTURE),
                    reason='experts-only-fixture.json smoke fixture not present')
@pytest.mark.parametrize('palette', ['colour', 'printer'])
def test_experts_only_runs_travel_outside_the_wall(page, palette):
    """The frozen Experts Only show, SR - MAIN: 22 circuits on four multis
    and eight port ends on two cards, on a 28-column wall whose blocks
    stand right across the sheet - two of the four breakouts sit under the
    wall itself, so their runs are the ones that must go round it."""
    pg, ids = page
    n = _sweep_off_the_wall(pg, SCRATCH_FIXTURE, palette, ['SR - MAIN - Signal + Power'])
    assert n == 30, ('22 circuits and eight port ends', n)
    assert ids['errors'] == []
