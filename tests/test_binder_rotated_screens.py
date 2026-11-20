"""A screen whose picture is turned by its Pixel Map rotation prints the way
its tab shows it, on every map sheet of the binder.

The 1.6.0 binder framed a turned screen on its UNTURNED box: a quarter turn
of an 8 x 3 wall printed a picture 3 wide and 8 tall inside a frame 8 wide
and 3 tall, so the picture ran off the top and bottom of its room and was
cut there; on the Header/Footer sheet the bars, which stand beside a turned
picture, were cut off with it (and the simple sheet left them no room at
all); the rulers, the multi brackets and the wiring sheet's runs were laid
on the unturned cabinets, beside the picture instead of on it.

Here, for each map sheet - Power, Data, Power Wiring, Data Wiring and
Header/Footer, Full and Simple - of a lone screen and of a group member,
turned 90, 180 and 270, from the front and the rear:

* the wall sits inside the drawing area, framed on the turned picture (its
  width and height swapped on a quarter turn), and its picture is drawn
  over the whole frame, corner to corner;
* the map's lettering is the same as the unturned sheet's, label for
  label (the turn moves the labels, it never loses one);
* the rulers number the wall's own columns and rows where they draw: each
  ruler's "1" stands by the wall's first cabinet wherever the turn (and a
  rear view's mirror) puts it, and no ruler number stands on a bar;
* the Header/Footer sheet draws its bars, on the side of the picture the
  wall's top or bottom turns to.

Run locally:
    python -m pytest tests/test_binder_rotated_screens.py -n 4 --dist loadfile -p no:cacheprovider
"""
import collections
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import open_app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# LONE: an 8 x 3 wall with footer bars, on its own. WALL-A: an 8 x 3 wall
# with header bars, grouped with WALL-B (4 x 3) beside it. Every screen on
# one distro and one H9 card, so each has power, data and wiring sheets.
# Each stands inside the raster; turned a quarter, each runs past it (the
# binder's sheet of one screen is not bounded by the raster).
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', Object.assign({
        cabinet_width: 120, cabinet_height: 120, rows: 3,
        powerVoltage: 208, powerAmperage: 12.5, panelWatts: 200,
        powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
        processorType: 'novastar-armor'}, body));
    await add({name: 'WALL-A', columns: 8, offset_x: 0, offset_y: 400});
    await add({name: 'WALL-B', columns: 4, offset_x: 960, offset_y: 400, panelWatts: 250});
    await add({name: 'LONE', columns: 8, offset_x: 0, offset_y: 0});
    let p = await j('GET', '/api/project');
    const A = p.layers.find(l => l.name === 'WALL-A');
    const B = p.layers.find(l => l.name === 'WALL-B');
    const L = p.layers.find(l => l.name === 'LONE');
    A.riggingBars = [2, 2, 2, 2];
    B.riggingBars = [2, 2];
    L.riggingFooterBars = [4, 2, 2];
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [A.id, B.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('rotated_binder_seed');
    const a = app.project.layers.find(l => l.id === A.id);
    const b = app.project.layers.find(l => l.id === B.id);
    const lone = app.project.layers.find(l => l.id === L.id);
    app.selectLayer(a);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(a, 1, d.id); app.setSocaNumber(a, 1, 1); app.setSocaLength(a, 1, '125');
    app.setSocaDistro(b, 1, d.id); app.setSocaNumber(b, 1, 2); app.setSocaLength(b, 1, '100');
    app.setSocaDistro(lone, 1, d.id); app.setSocaNumber(lone, 1, 3); app.setSocaLength(lone, 1, '100');
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    for (const l of [a, b, lone]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(l.id), cardId});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Rotated Binder Seed');
    return { a: a.id, lone: lone.id };
}"""

# Every map sheet of the two screens, painted, and of each: the wall's
# rect and the map's room (page units), the drawing area, whether the
# picture is drawn at the wall's corners and middle, the map's lettering,
# and - on a Header/Footer sheet - whether ink stands in the strip beside
# the wall on each side. The rotation is put back after.
SHEETS_JS = """([ids, deg, opts, names]) => {
    const app = window.app;
    const turned = ids.map(id => app.project.layers.find(l => l.id === id));
    const was = turned.map(l => l.rotation);
    turned.forEach(l => { l.rotation = deg; });
    try {
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => {
            if (!['power', 'data', 'wiring', 'rigging'].includes(p.kind)) return;
            if (!names.some(n => p.title.startsWith(n + ' - '))) return;
            const r = app.renderBinderPage(opts, i);
            const rec = r.record, c = r.canvas, k = c.width / rec.width;
            const da = app._bGeo({ w: rec.width, h: rec.height }, opts.titleBlock !== false).da;
            const ctx = c.getContext('2d');
            const inked = (x, y) => {
                const px = ctx.getImageData(Math.round(x * k), Math.round(y * k), 1, 1).data;
                return px[3] > 0 && (px[0] < 235 || px[1] < 235 || px[2] < 235);
            };
            const m = r.map;
            let picture = null, strips = null;
            if (m) {
                const at = (fx, fy) => inked(m.x + m.w * fx, m.y + m.h * fy);
                picture = [at(0.04, 0.04), at(0.96, 0.04), at(0.04, 0.96), at(0.96, 0.96), at(0.45, 0.45)];
                // ink in the strip just past each edge of the wall, along
                // its middle half
                const strip = (side) => {
                    let n = 0;
                    for (let t = 0.25; t <= 0.75; t += 0.05) {
                        for (let d = 3; d <= 40; d += 2) {
                            const x = side === 'left' ? m.x - d : side === 'right' ? m.x + m.w + d : m.x + m.w * t;
                            const y = side === 'top' ? m.y - d : side === 'bottom' ? m.y + m.h + d : m.y + m.h * t;
                            if (inked(x, y)) { n++; break; }
                        }
                    }
                    return n;
                };
                strips = { top: strip('top'), right: strip('right'), bottom: strip('bottom'), left: strip('left') };
            }
            // the row ruler's numbers (bold, set right of their anchor,
            // left of the wall) standing on ink - a bar - not on paper
            const rulerOnInk = m ? rec.ops.filter(o => o.op === 'text' && o.weight === 700 && o.align === 'right'
                && /^[0-9]+$/.test(String(o.text)) && o.x < m.x && o.y > m.y && o.y < m.y + m.h + 20
                && inked(o.x + 3, o.y - 4)).map(o => o.text) : [];
            // where each ruler prints its "1": the column ruler over the
            // wall (its x), the row ruler left of it (its y). The row
            // ruler's numbers are bold digits set right of their anchor
            // left of the wall; the column ruler's are their size, centred
            // over the wall (a multi's socket numbers over the wall on a
            // wiring sheet are bold and centred too).
            const rowNos = m ? rec.ops.filter(o => o.op === 'text' && o.weight === 700 && o.align === 'right'
                && /^[0-9]+$/.test(String(o.text)) && o.x < m.x && o.y >= m.y - 1 && o.y <= m.y + m.h + 20) : [];
            const size = rowNos.length ? rowNos[0].size : null;
            const left1 = rowNos.find(o => String(o.text) === '1') || null;
            const top1 = m && size !== null ? (rec.ops.find(o => o.op === 'text' && o.weight === 700
                && o.align === 'center' && String(o.text) === '1' && Math.abs(o.size - size) < 0.01
                && o.y < m.y && o.x >= m.x - 1 && o.x <= m.x + m.w + 1) || null) : null;
            const rulerOne = { top: top1 ? top1.x : null, left: left1 ? left1.y : null };
            out.push({ title: p.title, kind: p.kind, layout: p.layout || null,
                       map: m ? { x: m.x, y: m.y, w: m.w, h: m.h, area: m.area } : null,
                       da: { x: da.x, y: da.y, w: da.w, h: da.h },
                       picture, strips, rulerOnInk, rulerOne, mapTexts: r.mapTexts.filter(t => String(t).trim()) });
        });
        return out;
    } finally {
        turned.forEach((l, i) => { l.rotation = was[i]; });
        window.canvasRenderer.render();
    }
}"""

NAMES = ['LONE', 'WALL-A', 'SR Beach']


def _opts(view, mode):
    return {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
            'fiber': False, 'network': False, 'rigging': True, 'wiring': True,
            'titleBlock': True, 'view': view, 'mode': mode}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
                        "localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    open_app(pg, e2e_server)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    yield pg, [ids['a'], ids['lone']], errors
    ctx.close()


_CACHE = {}


def _sheets(page, deg, view, mode):
    pg, ids, _ = page
    key = (deg, view, mode)
    if key not in _CACHE:
        _CACHE[key] = {s['title']: s for s in pg.evaluate(SHEETS_JS, [ids, deg, _opts(view, mode), NAMES])}
    return _CACHE[key]


TOL = 2.0


def _inside(a, b, tol=TOL):
    return (a['x'] >= b['x'] - tol and a['y'] >= b['y'] - tol
            and a['x'] + a['w'] <= b['x'] + b['w'] + tol and a['y'] + a['h'] <= b['y'] + b['h'] + tol)


# The side of the picture a wall's top or bottom lands on, turned
# clockwise (app-rigging.js riggingPictureSide); a rear view mirrors it.
def _picture_side(side, deg, view):
    order = ['top', 'right', 'bottom', 'left']
    s = order[(order.index(side) + deg // 90) % 4]
    if view == 'rear':
        s = {'left': 'right', 'right': 'left'}.get(s, s)
    return s


@pytest.mark.parametrize('mode', ['full', 'simple'])
@pytest.mark.parametrize('view', ['front', 'rear'])
@pytest.mark.parametrize('deg', [90, 180, 270])
def test_a_turned_screen_prints_as_its_tab_shows_it(page, deg, view, mode):
    flat = _sheets(page, 0, view, mode)
    turned = _sheets(page, deg, view, mode)
    assert flat, 'no map sheets for the unturned screens'
    assert set(turned) == set(flat), (sorted(turned), sorted(flat))
    # Full: each screen's Power and Data maps and their wiring sheets;
    # Simple: its Power and Data pages are the wiring drawings. Both: the
    # Header/Footer sheets.
    kinds = collections.Counter(s['kind'] for s in flat.values())
    wanted = ('power', 'data', 'rigging') if mode == 'full' else ('rigging',)
    for kind in wanted:
        assert kinds[kind] >= 2, kinds
    assert kinds['wiring'] >= 4, kinds
    problems = []
    for title, s in turned.items():
        f = flat[title]
        m, m0 = s['map'], f['map']
        if not m or not m0:
            problems.append('%s: no map logged' % title)
            continue
        # the drawing area holds the map's room and the wall
        if not _inside(m['area'], s['da']):
            problems.append('%s: map room %s runs out of the drawing area %s' % (title, m['area'], s['da']))
        if not _inside(m, s['da']):
            problems.append('%s: wall %s runs out of the drawing area %s' % (title, m, s['da']))
        # (a group's sheet frames the union of a turned member and an
        # unturned one: its room and its lettering are checked)
        group = title.startswith('SR Beach')
        # framed on the turned picture
        want = (m0['h'] / m0['w']) if deg in (90, 270) else (m0['w'] / m0['h'])
        if not group and abs((m['w'] / m['h']) / want - 1) > 0.03:
            problems.append('%s: wall framed %.0f x %.0f, the picture is %.3f wide to tall'
                            % (title, m['w'], m['h'], want))
        # the picture drawn over the whole frame
        if not group and not all(s['picture']):
            problems.append('%s: the picture is not drawn at the frame %s (corners, middle)' % (title, s['picture']))
        # the row ruler's numbers clear of the bars
        if s['rulerOnInk']:
            problems.append('%s: row ruler numbers %s stand on the bars' % (title, s['rulerOnInk']))
        # each ruler's "1" by the wall's first cabinet (its top left one,
        # unturned), wherever the turn puts it: the rulers number the wall's
        # own columns and rows where they draw
        corner = {0: ('left', 'top'), 90: ('right', 'top'), 180: ('right', 'bottom'),
                  270: ('left', 'bottom')}[deg]
        cx = corner[0] if view == 'front' else {'left': 'right', 'right': 'left'}[corner[0]]
        if not group and s['kind'] in ('power', 'data') and s['rulerOne']['left'] is None:
            problems.append('%s: no row ruler "1"' % title)
        if not group and s['kind'] == 'data' and s['rulerOne']['top'] is None:
            problems.append('%s: no column ruler "1"' % title)
        if not group and s['rulerOne']['top'] is not None:
            on_left = s['rulerOne']['top'] < m['x'] + m['w'] / 2
            if on_left != (cx == 'left'):
                problems.append('%s: column ruler "1" on the wrong side (want %s)' % (title, cx))
        if not group and s['rulerOne']['left'] is not None:
            on_top = s['rulerOne']['left'] < m['y'] + m['h'] / 2
            if on_top != (corner[1] == 'top'):
                problems.append('%s: row ruler "1" on the wrong side (want %s)' % (title, corner[1]))
        # the same lettering as unturned
        if collections.Counter(s['mapTexts']) != collections.Counter(f['mapTexts']):
            lost = collections.Counter(f['mapTexts']) - collections.Counter(s['mapTexts'])
            extra = collections.Counter(s['mapTexts']) - collections.Counter(f['mapTexts'])
            problems.append('%s: map lettering differs, lost %s, new %s' % (title, dict(lost), dict(extra)))
        # the bars, on the side the wall's top (header) or bottom (footer)
        # turns to
        if s['kind'] == 'rigging' and not group:
            edge = 'bottom' if title.startswith('LONE') else 'top'
            side = _picture_side(edge, deg, view)
            flat_side = _picture_side(edge, 0, view)
            if f['strips'][flat_side] < 8:
                problems.append('%s: unturned sheet shows no bars %s' % (title, f['strips']))
            if s['strips'][side] < 8:
                problems.append("%s: no bars on the picture's %s %s" % (title, side, s['strips']))
    assert not problems, '\n'.join(problems)


def test_no_page_errors(page):
    _sheets(page, 90, 'front', 'full')
    assert not page[2], page[2]
