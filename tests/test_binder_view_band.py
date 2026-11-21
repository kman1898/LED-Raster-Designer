"""Every map sheet says which side it is drawn from, big, and where stage left is.

The owner, 2026-11-19: stage hands misread a rear-view binder because the
small "· REAR VIEW" in the sheet heading went unnoticed. Picked from
mockups:

  * a thick colour band across the top of every map sheet's drawing area,
    the words in big white capitals - red "REAR VIEW · BEHIND THE WALL" on
    a rear set, blue "FRONT VIEW · AUDIENCE SIDE" on a front one - dark
    enough to read on a black and white printout;
  * STAGE LEFT / STAGE RIGHT on ONE line under every map drawing (owner,
    2026-11-20: the words up the sides got lost beside multi names like
    "STAGE LEFT POWER DISTRO RACK A9"), each at its edge of the wall with
    an arrow pointing out: "< STAGE LEFT ... STAGE RIGHT >" on a rear sheet
    (the crew behind the wall face the audience), "< STAGE RIGHT ... STAGE
    LEFT >" on a front one;
  * no BACK badge on any binder map: the band says it;
  * on every map sheet - Power, Data, Power Wiring, Data Wiring,
    Header/Footer and the Simple sheets - and on the Overview, which is
    always drawn from the front and so always wears the FRONT band. The
    sheets that draw no wall (pull sheets, FACTS, contents, fiber,
    processors, a map sheet's "(cont.)" sheet of tables) wear no band.

Read off each sheet's display list (app-binder.js _bRecCtx): the band's
fill and its words in white, the stage line under the wall and over the
view bubble, its words at the right edges, clear of every other mark on
the sheet - text measured in its own font, rules, boxes - and of every
inked pixel of the map bitmaps. A show with a rotated wall with bars beside it and
a grouped pair with header and footer bars, Full and Simple, front and
rear, on letter (the tightest sheet) with the title block on and off.

Run locally (each session takes its own free port):
    python -m pytest tests/test_binder_view_band.py -n 4 --dist loadfile --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder_sheet_bounds import WALLS_JS, _opts, page  # noqa: E402,F401


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


BANDS = {
    'front': {'words': 'FRONT VIEW · AUDIENCE SIDE', 'fill': '#123f8c'},
    'rear': {'words': 'REAR VIEW · BEHIND THE WALL', 'fill': '#b3121b'},
}
MAP_KINDS = ('overview', 'power', 'data', 'wiring', 'rigging')

# The tall tower turned 90 on Pixel Map with header bars: on its
# Header/Footer sheet the bars stand BESIDE the wall, in the gutter the
# stage words must stay out of.
ROTATE_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const tower = app.project.layers.find(l => l.name.startsWith('STAGE LEFT'));
    await j('PUT', `/api/layer/${tower.id}`, {rotation: 90});
    const p = await j('GET', '/api/project');
    p.layers.find(l => l.id === tower.id).riggingBars = [2, 2, 2];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('view_band_rotate');
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    const t = app.project.layers.find(l => l.id === tower.id);
    return {rotation: t.rotation, bars: t.riggingBars};
}"""

# Every sheet of the set painted one at a time: its band and stage words
# as the log has them, the band's own marks found on the display list,
# the wall the stage words stand beside, and whatever the stage words
# touch - any mark of the display list, any inked pixel of a bitmap.
SHEETS_JS = r"""async ([opts, i]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const mc = document.createElement('canvas').getContext('2d');
    const box = (o) => {
        if (o.op === 'text') {
            const t = String(o.text);
            if (!t.trim()) return null;
            mc.font = app._bFont(o.size, o.weight);
            const w = mc.measureText(t).width, s = o.size;
            const lx = o.align === 'center' ? -w / 2 : (o.align === 'right' || o.align === 'end') ? -w : 0;
            const b = o.baseline;
            const [ly0, ly1] = b === 'middle' ? [-0.36 * s, 0.36 * s]
                : (b === 'top' || b === 'hanging') ? [0, 0.9 * s]
                : b === 'bottom' ? [-0.95 * s, 0] : [-0.72 * s, 0.05 * s];
            const c = Math.cos(o.rotate || 0), sn = Math.sin(o.rotate || 0);
            const pts = [[lx, ly0], [lx + w, ly0], [lx, ly1], [lx + w, ly1]]
                .map(([px, py]) => [o.x + c * px - sn * py, o.y + sn * px + c * py]);
            return {x0: Math.min(...pts.map(p => p[0])), x1: Math.max(...pts.map(p => p[0])),
                    y0: Math.min(...pts.map(p => p[1])), y1: Math.max(...pts.map(p => p[1]))};
        }
        if (o.op === 'line') {
            const p = (o.width || 0) / 2;
            const xs = o.points.map(q => q[0]), ys = o.points.map(q => q[1]);
            return {x0: Math.min(...xs) - p, x1: Math.max(...xs) + p, y0: Math.min(...ys) - p, y1: Math.max(...ys) + p};
        }
        if (o.op === 'rect' || o.op === 'image') {
            const p = o.stroke ? (o.width || 0) / 2 : 0;
            return {x0: Math.min(o.x, o.x + o.w) - p, x1: Math.max(o.x, o.x + o.w) + p,
                    y0: Math.min(o.y, o.y + o.h) - p, y1: Math.max(o.y, o.y + o.h) + p};
        }
        return null;
    };
    const meets = (a, b) => Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0) > 0.5
        && Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0) > 0.5;
    // (never waiting on a bitmap for ever)
    const load = (src) => new Promise((res, rej) => {
        const im = new Image();
        const t = setTimeout(() => rej(new Error('bitmap never loaded')), 15000);
        im.onload = () => { clearTimeout(t); res(im); };
        im.onerror = (e) => { clearTimeout(t); rej(e); };
        im.src = src;
    });
    // the inked pixels of an image op inside `r` (page units), read off
    // that region alone (a whole map bitmap per sheet is a lot of memory)
    const cv = document.createElement('canvas');
    const inkIn = async (rec, o, r) => {
        const src = rec.images[o.id];
        if (!src) return 0;
        const im = await load(src);
        const kx = im.width / o.w, ky = im.height / o.h;
        const x0 = Math.max(0, Math.floor((Math.max(r.x0, o.x) - o.x) * kx));
        const x1 = Math.min(im.width, Math.ceil((Math.min(r.x1, o.x + o.w) - o.x) * kx));
        const y0 = Math.max(0, Math.floor((Math.max(r.y0, o.y) - o.y) * ky));
        const y1 = Math.min(im.height, Math.ceil((Math.min(r.y1, o.y + o.h) - o.y) * ky));
        if (x1 <= x0 || y1 <= y0) return 0;
        cv.width = x1 - x0; cv.height = y1 - y0;
        const cx = cv.getContext('2d', { willReadFrequently: true });
        cx.clearRect(0, 0, cv.width, cv.height);
        cx.drawImage(im, x0, y0, x1 - x0, y1 - y0, 0, 0, x1 - x0, y1 - y0);
        const d = cx.getImageData(0, 0, cv.width, cv.height).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] > 24 && (d[i] < 235 || d[i + 1] < 235 || d[i + 2] < 235)) n++;
        }
        im.src = '';
        return n;
    };
    {
        const p = plan[i];
        const r = app.renderBinderPage(opts, i);
        const rec = r.record;
        const g = app._bGeo({w: rec.width, h: rec.height}, opts.titleBlock !== false);
        const s = {n: p.number, kind: p.kind, title: p.sheetTitle, band: r.viewBand, stage: r.stage,
                   da: g.da, bandRect: false, bandText: false, bandWordsAnywhere: false, wall: null,
                   hits: [], ink: 0, bubble: r.bubble, badge: (r.mapTexts || []).filter(t => /^(BACK|FRONT)$/.test(t)),
                   // (level text only: a multi's label stands on end along
                   // its bracket, and a long name like "STAGE LEFT POWER
                   // DISTRO RACK A1" wraps to a "STAGE LEFT" line of its
                   // own beside a turned wall's short rows)
                   stageTexts: rec.ops.filter(o => o.op === 'text' && !o.rotate
                                               && /STAGE (LEFT|RIGHT)( >)?$/.test(o.text)
                                               && /^(< )?STAGE/.test(o.text)).map(o => o.text)};
        for (const o of rec.ops) {
            if (r.viewBand && o.op === 'rect' && o.fill === r.viewBand.fill && !o.stroke
                && Math.abs(o.x - r.viewBand.x) < 0.5 && Math.abs(o.y - r.viewBand.y) < 0.5
                && Math.abs(o.w - r.viewBand.w) < 0.5 && Math.abs(o.h - r.viewBand.h) < 0.5) s.bandRect = true;
            if (o.op === 'text' && /VIEW · (AUDIENCE SIDE|BEHIND THE WALL)/.test(o.text)) {
                s.bandWordsAnywhere = true;
                if (r.viewBand && o.text === r.viewBand.words && o.color === '#ffffff' && !o.rotate) {
                    const b = box(o);
                    s.bandText = {size: o.size, inside: b.x0 >= r.viewBand.x && b.x1 <= r.viewBand.x + r.viewBand.w
                                  && b.y0 >= r.viewBand.y && b.y1 <= r.viewBand.y + r.viewBand.h};
                }
            }
        }
        // the wall the stage words stand beside
        if (r.simple && r.simple.wall) s.wall = r.simple.wall;
        else if (r.wiring && r.wiring.halves && r.wiring.halves[0] && r.wiring.halves[0].map) s.wall = r.wiring.halves[0].map;
        else if (r.map) s.wall = {x: r.map.x, y: r.map.y, w: r.map.w, h: r.map.h};
        if (r.stage) {
            for (const where of ['left', 'right']) {
                const L = r.stage[where];
                const lb = {x0: L.x0, x1: L.x1, y0: L.y0, y1: L.y1};
                for (const o of rec.ops) {
                    if (o.op === 'text' && o.text === L.text) continue;     // the word itself
                    if (o.op === 'rect' && !o.stroke && (o.fill === '#ffffff' || !o.fill)) continue;
                    if (o.op === 'image') {
                        if (meets(lb, box(o))) s.ink += await inkIn(rec, o, lb);
                        continue;
                    }
                    // (a stroked rect is its four edges - the sheet's border,
                    // the overview map's frame - never its inside)
                    let boxes = [box(o)];
                    if (o.op === 'rect' && o.stroke) {
                        const p = (o.width || 0) / 2, x0 = Math.min(o.x, o.x + o.w), x1 = Math.max(o.x, o.x + o.w);
                        const y0 = Math.min(o.y, o.y + o.h), y1 = Math.max(o.y, o.y + o.h);
                        boxes = [{x0: x0 - p, x1: x1 + p, y0: y0 - p, y1: y0 + p}, {x0: x0 - p, x1: x1 + p, y0: y1 - p, y1: y1 + p},
                                 {x0: x0 - p, x1: x0 + p, y0: y0 - p, y1: y1 + p}, {x0: x1 - p, x1: x1 + p, y0: y0 - p, y1: y1 + p}];
                    }
                    for (const b of boxes) {
                        if (b && meets(lb, b)) s.hits.push({where, op: o.op, text: o.text || null,
                            box: [b.x0, b.y0, b.x1, b.y1].map(Math.round)});
                    }
                }
            }
        }
        return { count: plan.length, sheet: s };
    }
}"""


@pytest.fixture(scope="module")
def walls(page):
    pg, errors = page
    out = pg.evaluate(WALLS_JS)
    assert out['layers'] == 4 and all(out['circuits']) and all(out['ports']), out
    turned = pg.evaluate(ROTATE_JS)
    assert turned == {'rotation': 90, 'bars': [2, 2, 2]}, turned
    return pg, errors


def _sheets(pg, **kw):
    """Every sheet of the set, one evaluate each: a whole set painted in
    one long call starves the page's server link, which then reloads it."""
    opts = _opts(**kw)
    first = pg.evaluate(SHEETS_JS, [opts, 0])
    out = [first['sheet']]
    for i in range(1, first['count']):
        out.append(pg.evaluate(SHEETS_JS, [opts, i])['sheet'])
    return out


def _is_map(s):
    return s['kind'] in MAP_KINDS and '(CONT.)' not in s['title'] and s['title'] != 'CONTENTS' \
        and not s['title'].startswith('CONTENTS')


def _check_band(s, view):
    """The band across the head of a map sheet's drawing area: the view's
    fill edge to edge, the view's words in big white capitals inside it."""
    want = 'front' if s['kind'] == 'overview' else view
    band = s['band']
    assert band and band['side'] == want, (s['n'], s['title'], band)
    assert band['words'] == BANDS[want]['words'] and band['fill'] == BANDS[want]['fill'], (s['title'], band)
    assert s['bandRect'], (s['n'], s['title'], 'no band fill on the display list')
    assert s['bandText'] and s['bandText']['inside'], (s['n'], s['title'], s['bandText'])
    # big: the words at full size on every sheet of this show's letter set
    assert s['bandText']['size'] >= 40, (s['title'], s['bandText'])
    da = s['da']
    assert abs(band['x'] - da['x']) < 0.5 and abs(band['w'] - da['w']) < 0.5 and abs(band['y'] - da['y']) < 0.5, \
        (s['title'], band, da)
    # the sheet names its view in its title as it always has
    if s['kind'] != 'overview':
        assert s['title'].endswith('· %s VIEW' % view.upper()), s['title']


def _check_stage(s, view):
    """The stage line: ONE line under the wall, "< STAGE LEFT" and "STAGE
    RIGHT >" on a rear sheet ("< STAGE RIGHT" and "STAGE LEFT >" on a front
    one, the Overview always), each at its edge of the wall - or the pair
    centred under a wall too narrow for that - over the view bubble, inside
    the drawing area, touching no mark of the sheet and no inked pixel of a
    map bitmap. Each word printed once."""
    st = s['stage']
    side = 'front' if s['kind'] == 'overview' else view
    assert st and st['side'] == side, (s['n'], s['title'], st)
    left, right = ('< STAGE LEFT', 'STAGE RIGHT >') if side == 'rear' else ('< STAGE RIGHT', 'STAGE LEFT >')
    assert st['left']['text'] == left and st['right']['text'] == right, (s['title'], st)
    assert sorted(s['stageTexts']) == sorted([left, right]), (s['title'], s['stageTexts'])
    L, R = st['left'], st['right']
    # one line: the same baseline, left word left of the right one
    assert L['y1'] == R['y1'] and L['x1'] < R['x0'], (s['title'], st)
    wall = s['wall']
    assert wall, (s['n'], s['title'])
    # under the wall
    assert L['y0'] >= wall['y'] + wall['h'] - 0.5, (s['title'], st, wall)
    # at the wall's edges, or centred under a narrow one
    if wall['w'] >= (L['x1'] - L['x0']) + (R['x1'] - R['x0']) + 48:
        assert abs(L['x0'] - wall['x']) < 1 and abs(R['x1'] - (wall['x'] + wall['w'])) < 1, (s['title'], st, wall)
    else:
        mid = (L['x0'] + R['x1']) / 2
        da = s['da']
        assert abs(mid - (wall['x'] + wall['w'] / 2)) < 1 or L['x0'] <= da['x'] + 1 \
            or R['x1'] >= da['x'] + da['w'] - 1, (s['title'], st, wall)
    # inside the drawing area, under the band; over the view bubble
    band, da = s['band'], s['da']
    for W in (L, R):
        assert W['x0'] >= da['x'] - 0.5 and W['x1'] <= da['x'] + da['w'] + 0.5, (s['title'], W, da)
        assert W['y0'] >= band['y'] + band['h'] - 0.5 and W['y1'] <= da['y'] + da['h'] + 0.5, (s['title'], W, da)
    assert st['size'] >= 16, (s['title'], st)
    b = s['bubble']
    assert b and b['y'] - b['r'] >= L['y1'] + 2, (s['title'], st, b)
    assert s['hits'] == [], (s['n'], s['title'], s['hits'][:6])
    assert s['ink'] == 0, (s['n'], s['title'], 'inked pixels under the stage words', s['ink'])


# (Full with the title block, Simple without it: both frames, both modes)
@pytest.mark.parametrize('mode', ['full', 'simple'])
@pytest.mark.parametrize('view', ['front', 'rear'])
def test_every_map_sheet_wears_its_band_and_its_stage_words(walls, view, mode):
    """Every map sheet - each kind there is, the Overview always as the
    front - wears the view's band and its stage line under the drawing
    ("< STAGE LEFT ... STAGE RIGHT >" on a rear sheet: the crew behind the
    wall face the audience), clear of everything else on the sheet, and
    its map carries no BACK badge. No other sheet wears either."""
    pg, errors = walls
    sheets = _sheets(pg, view=view, mode=mode, titleBlock=(mode == 'full'))
    kinds = set()
    for s in sheets:
        if not _is_map(s):
            assert s['band'] is None and s['stage'] is None, (s['n'], s['title'], s['band'])
            assert not s['bandWordsAnywhere'], (s['n'], s['title'])
            continue
        kinds.add(s['kind'])
        _check_band(s, view)
        _check_stage(s, view)
        # no BACK (or FRONT) badge on the map: the band says it
        assert s['badge'] == [], (s['n'], s['title'], s['badge'])
    # (Simple swaps each screen's Power and Data sheets for its wiring ones)
    want_kinds = {'overview', 'wiring', 'rigging'} | ({'power', 'data'} if mode == 'full' else set())
    assert kinds == want_kinds, kinds
    assert errors == []


PRINTER_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'power');
    const r = app.renderBinderPage(opts, i);
    const b = r.viewBand;
    return { band: b, fills: !b ? 0 : r.record.ops.filter(o => o.op === 'rect' && o.fill === b.fill
                 && Math.abs(o.x - b.x) < 0.5 && Math.abs(o.y - b.y) < 0.5 && Math.abs(o.w - b.w) < 0.5
                 && Math.abs(o.h - b.h) < 0.5).length };
}"""


@pytest.mark.parametrize('view', ['front', 'rear'])
def test_the_printer_palette_band_is_grey_and_still_reads(walls, view):
    """The printer palette has no colour: the rear band black, the front a
    dark grey, the same white words on both."""
    pg, errors = walls
    out = pg.evaluate(PRINTER_JS, _opts(view=view, palette='printer'))
    band = out['band']
    assert band and band['fill'] == {'front': '#4d4d4d', 'rear': '#111111'}[view], band
    assert band['words'] == BANDS[view]['words'] and band['color'] == '#ffffff', band
    assert out['fills'] == 1, out
    assert errors == []


# The run pen's red pixels on a Power sheet's map bitmaps (the circuits'
# runs, the default palette), one sheet per call.
RUNS_JS = r"""async ([opts, i]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    if (i == null) return plan.map((p, k) => [k, p.kind, p.title]).filter(p => p[1] === 'power');
    const r = app.renderBinderPage(opts, i);
    const rec = r.record;
    let red = 0;
    for (const o of rec.ops) {
        if (o.op !== 'image' || !rec.images[o.id]) continue;
        const im = await new Promise((res, rej) => {
            const x = new Image(); x.onload = () => res(x); x.onerror = rej; x.src = rec.images[o.id];
        });
        const cv = document.createElement('canvas');
        cv.width = im.width; cv.height = im.height;
        const cx = cv.getContext('2d', { willReadFrequently: true });
        cx.drawImage(im, 0, 0);
        const d = cx.getImageData(0, 0, cv.width, cv.height).data;
        for (let k = 0; k < d.length; k += 4) if (d[k + 3] > 100 && d[k] > 180 && d[k + 1] < 90 && d[k + 2] < 90) red++;
        cv.width = 0; cv.height = 0;
    }
    return { title: plan[i].title, red };
}"""


def test_every_power_sheet_draws_its_runs(walls):
    """Every Power sheet's map carries its circuits' runs - the side fills
    too, which stand further down the canvas than its raster reaches (their
    cabinets printed with no circuit on them: the runs and discs were cut
    to the raster the sheet is told to ignore, canvas.js
    _clipToActiveRaster)."""
    pg, errors = walls
    opts = _opts(view='front')
    sheets = pg.evaluate(RUNS_JS, [opts, None])
    titles = [t for _i, _k, t in sheets]
    assert any(t.startswith('DOWNSTAGE LEFT SIDE FILL') for t in titles), titles
    for i, _kind, title in sheets:
        if '(cont.)' in title:
            continue
        out = pg.evaluate(RUNS_JS, [opts, i])
        assert out['red'] > 200, (title, 'no runs on the map', out)
    assert errors == []
