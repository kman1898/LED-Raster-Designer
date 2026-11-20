"""A screen standing past the processor's raster prints its labels whole on
the binder.

A binder sheet draws ONE screen on its own page, framed on its wall, so the
raster is not what bounds it (app-binder.js sets ignoreRasterBounds while a
map paints). The cabinets and runs already honoured that, but the label and
tag passes still clipped to the raster (canvas.js _clipToActiveRaster): a
screen below or beside the raster printed its circuit and port discs as
empty circles, their text and fill cut away.

Three screens alike: IN inside the raster, PART half past its right edge,
OUT wholly below it. On each one's Power, Data, Power Wiring and Data Wiring
sheets every disc the map draws has its text (ink of more than one shade
inside it), and each sheet draws as many discs as IN's.

Run locally:
    python -m pytest tests/test_binder_off_raster_labels.py -n 4 --dist loadfile -p no:cacheprovider
"""
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


SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const c = proj.canvases && proj.canvases[0];
    const rw = (c && c.raster_width) || window.canvasRenderer.rasterWidth || 1920;
    const rh = (c && c.raster_height) || window.canvasRenderer.rasterHeight || 1080;
    const add = (body) => j('POST', '/api/layer/add', Object.assign({
        columns: 6, rows: 3, cabinet_width: 120, cabinet_height: 120,
        powerVoltage: 208, powerAmperage: 12.5, panelWatts: 200,
        powerFlowPattern: 'tl-h', powerOrganized: true, flowPattern: 'tl-h',
        processorType: 'novastar-armor'}, body));
    await add({name: 'IN', offset_x: 0, offset_y: 0});
    await add({name: 'PART', offset_x: rw - 360, offset_y: 500});
    await add({name: 'OUT', offset_x: 0, offset_y: rh + 300});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('off_raster_seed');
    const L = (n) => app.project.layers.find(l => l.name === n);
    app.selectLayer(L('IN'));
    const d = app.addDistro({name: 'SR'});
    ['IN', 'PART', 'OUT'].forEach((n, i) => {
        app.setSocaDistro(L(n), 1, d.id); app.setSocaNumber(L(n), 1, i + 1); app.setSocaLength(L(n), 1, '100');
    });
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    for (const n of ['IN', 'PART', 'OUT']) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(L(n).id), cardId});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Off Raster Seed');
    const b = (n) => window.canvasRenderer.getLayerBounds(L(n));
    return { rw, rh, part: b('PART'), out: b('OUT') };
}"""

# Every disc the sheet's map draws, read off the map's own bitmap: its
# text, and the lightest and darkest ink inside it. A disc is drawn by
# _layoutCircleLabel (its size) and _fillWrappedLabel (its text) - the
# calls the wiring sheet watches too; only the map's last whole render
# on the binder's map bitmap counts.
DISCS_JS = """([opts, names, kinds]) => {
    const app = window.app, r = window.canvasRenderer;
    const plan = app.planBinder(opts);
    const own = ['_layoutCircleLabel', '_fillWrappedLabel', 'render']
        .map(k => [k, Object.getOwnPropertyDescriptor(r, k)]);
    const layout = r._layoutCircleLabel, fill = r._fillWrappedLabel, render = r.render;
    const radii = new WeakMap();
    let pass = 0, discs = [];
    r._layoutCircleLabel = function (...a) {
        const o = layout.apply(this, a);
        if (o && Array.isArray(o.lines) && Number.isFinite(o.radius)) radii.set(o.lines, o.radius);
        return o;
    };
    r._fillWrappedLabel = function (ls, x, y) {
        if (this.canvas === app._binderMapCanvas && radii.has(ls)) {
            const m = this.ctx.getTransform();
            discs.push({ pass, text: ls.join(' '), x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f,
                         r: radii.get(ls) * Math.hypot(m.a, m.b) });
        }
        return fill.apply(this, arguments);
    };
    r.render = function (...a) {
        if (this.canvas === app._binderMapCanvas) pass++;
        return render.apply(this, a);
    };
    const out = [];
    try {
        plan.forEach((p, i) => {
            if (!kinds.includes(p.kind) || !names.some(n => p.title.startsWith(n + ' - '))) return;
            discs = []; pass = 0;
            app.renderBinderPage(opts, i);
            const c = app._binderMapCanvas, ctx = c.getContext('2d');
            const seen = discs.filter(d => d.pass === pass).map(d => {
                const h = Math.max(2, Math.round(d.r * 0.6));
                const x0 = Math.max(0, Math.round(d.x - h)), y0 = Math.max(0, Math.round(d.y - h));
                const w = Math.min(c.width - x0, 2 * h), hh = Math.min(c.height - y0, 2 * h);
                let lo = 255, hi = 0, inked = 0;
                if (w > 0 && hh > 0) {
                    const px = ctx.getImageData(x0, y0, w, hh).data;
                    for (let k = 0; k < px.length; k += 4) {
                        if (px[k + 3] < 128) continue;
                        inked++;
                        const lum = 0.299 * px[k] + 0.587 * px[k + 1] + 0.114 * px[k + 2];
                        lo = Math.min(lo, lum); hi = Math.max(hi, lum);
                    }
                }
                return { text: d.text, inked, range: inked ? Math.round(hi - lo) : 0 };
            });
            out.push({ title: p.title, kind: p.kind, discs: seen });
        });
    } finally {
        for (const [k, d] of own) { delete r[k]; if (d) Object.defineProperty(r, k, d); }
    }
    return out;
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
        'fiber': False, 'network': False, 'rigging': False, 'wiring': True,
        'titleBlock': True, 'view': 'front', 'mode': 'full'}


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
    seed = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    # the fixture: PART runs past the raster's right edge, OUT starts below it
    assert seed['part']['x'] < seed['rw'] < seed['part']['x'] + seed['part']['width'], seed
    assert seed['out']['y'] >= seed['rh'], seed
    yield pg, errors
    ctx.close()


_CACHE = {}


def _sheets(page, view):
    if view not in _CACHE:
        opts = dict(OPTS, view=view)
        _CACHE[view] = {s['title']: s for s in page[0].evaluate(
            DISCS_JS, [opts, ['IN', 'PART', 'OUT'], ['power', 'data', 'wiring']])}
    return _CACHE[view]


def _kind_of(title):
    rest = title.split(' - ', 1)[1]
    return rest.split(' - ')[0]          # Power, Data, Power Wiring, Data Wiring


@pytest.mark.parametrize('view', ['front', 'rear'])
@pytest.mark.parametrize('screen', ['IN', 'PART', 'OUT'])
def test_every_disc_has_its_text_wherever_the_screen_stands(page, screen, view):
    sheets = _sheets(page, view)
    mine = {_kind_of(t): s for t, s in sheets.items() if t.startswith(screen + ' - ')}
    inside = {_kind_of(t): s for t, s in sheets.items() if t.startswith('IN - ')}
    assert sorted(mine) == ['Data', 'Data Wiring', 'Power', 'Power Wiring'], sorted(sheets)
    problems = []
    for kind, s in sorted(mine.items()):
        if not s['discs']:
            problems.append('%s: no discs drawn' % s['title'])
        if len(s['discs']) != len(inside[kind]['discs']):
            problems.append('%s: %d discs, %d inside the raster' % (
                s['title'], len(s['discs']), len(inside[kind]['discs'])))
        for d in s['discs']:
            if d['range'] < 60:
                problems.append('%s: disc %r is blank (ink %d px, shade range %d)' % (
                    s['title'], d['text'], d['inked'], d['range']))
    assert not problems, '\n'.join(problems)


def test_no_page_errors(page):
    _sheets(page, 'front')
    assert not page[1], page[1]
