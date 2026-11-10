"""Header and footer bars on a screen with a Pixel Map rotation, and on a
wall with a half column (the owner's rulings, 2026-11-10).

* A Pixel Map rotation turns only the PICTURE. The bars follow the wall
  as built: one panel of bar to each of its columns, along its real
  bottom. The Header/Footer tab draws them turned with the picture, so
  each stays by the cabinets it is under; their count, the pull list and
  the binder are what they are at 0 degrees, and the 3D tab, which builds
  the wall unturned, stands the same bars in the same order. At 180 the
  tab and 3D agree on the order. No new setting.
* A show saved when a quarter-turned screen's bars ran across its rows:
  an Auto row is laid again along its columns as the show opens, and
  said; a custom row is left, and what no longer fits is in the tab's
  "Bars no longer fit" box.
* A bar over a half column is its FULL stock length and hangs past the
  wall's edge, never cut: a double is two whole panels. The tab says so in
  plain words ("the footer double at the right end hangs 250 mm past the
  wall"), and the tab's drawing, 3D and the pull list agree.

Run locally:
    python -m pytest tests/test_bars_rotation.py -n 4 --dist loadfile -p no:cacheprovider
"""
import pytest

from conftest import settled

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    pg.errors = []
    pg.on('pageerror', lambda e: pg.errors.append(str(e)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete")
    pg.wait_for_timeout(1200)
    yield pg
    ctx.close()


# The screens asked for (200 px cabinets of 500 x 500 mm), each with any
# extra fields; a show in meters; history rebased.
SEED_JS = """async (specs) => {
    const app = window.app;
    for (let i = 0; i < 600; i++) {
        if (!(app._inflightLayerPuts && app._inflightLayerPuts.size)) break;
        await new Promise(r => setTimeout(r, 25));
    }
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = [];
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    proj.cableUnit = 'm';
    for (const k of ['stage3dCamera', 'stage3dUnits', 'stage3dBars', 'riggingTool', 'pullSheetEdits']) delete proj[k];
    await j('PUT', '/api/project', proj);
    const ids = {};
    for (const s of specs) {
        const made = await j('POST', '/api/layer/add', Object.assign({
            cabinet_width: 200, cabinet_height: 200, panel_width_mm: 500, panel_height_mm: 500,
        }, s.add));
        ids[s.add.name] = made.id;
        if (s.extra) await j('PUT', `/api/layer/${made.id}`, s.extra);
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('bars_rotation_seed');
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Bars Rotation Seed');
    app.renderLayers();
    app.updateUI();
    return ids;
}"""


def seed(page, specs):
    page.evaluate("""() => { const t = document.querySelector('#view-tabs .view-tab[data-mode="pixel-map"]');
        if (t) t.click(); }""")
    page.wait_for_timeout(150)
    ids = page.evaluate(SEED_JS, specs)
    page.wait_for_timeout(300)
    return ids


def tab(page, mode):
    page.click(f'#view-tabs .view-tab[data-mode="{mode}"]')
    page.wait_for_timeout(300)


def lay(page, layer_id, *fields):
    return page.evaluate("""([id, f]) => { const l = window.app.project.layers.find(x => x.id === id);
        return Object.fromEntries(f.map(k => [k, l[k] === undefined ? null : l[k]])); }""",
                         [layer_id, list(fields)])


def hits(page, layer_id):
    """Every bar the tab drew for a screen: its start, size and the screen
    box round it."""
    return page.evaluate("""(id) => { const r = window.canvasRenderer; r.render();
        return (r._riggingHits || []).filter(h => h.layerId === id)
            .map(h => ({ start: h.start, span: h.span, x0: h.x0, x1: h.x1, y0: h.y0, y1: h.y1 })); }""", layer_id)


def picture(page, layer_id):
    """The screen's picture on the screen, turned as the tab draws it."""
    return page.evaluate("""(id) => { const r = window.canvasRenderer, a = window.app;
        const l = a.project.layers.find(x => x.id === id);
        const b = r.getLayerFootprintInActiveView(l);
        const ws = r._canvasWorkspace(a.project.canvases.find(c => c.id === (l.show_canvas_id || l.canvas_id)));
        return { x: (b.x + ws.wx) * r.zoom + r.panX, y: (b.y + ws.wy) * r.zoom + r.panY,
                 w: b.width * r.zoom, h: b.height * r.zoom, unit: l.cabinet_width * r.zoom }; }""", layer_id)


def pull_rig(page):
    return sorted((t['type'], t['qty']) for t in page.evaluate(
        "() => window.app.buildPullSheet().totals.filter(t => t.side === 'rigging').map(t => ({type: t.type, qty: t.qty}))"))


def stage_slices(page, layer_id):
    """The bars the 3D tab stands over the screen (riggingStageSlices)."""
    return page.evaluate("""(id) => window.app.riggingStageSlices(window.app.project.layers.find(l => l.id === id))
        .map(s => ({ row: s.row, bars: s.bars.map(b => [b.start, b.size]), fits: s.fits }))""", layer_id)


def turn(page, layer_id, deg):
    page.evaluate("""([id, deg]) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.rotation = deg; a.updateLayers([l], true, 'Rotation'); }""", [layer_id, deg])
    page.wait_for_timeout(400)


def toasts(page):
    return page.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(e => e.textContent).join(' | ')")


def clear_toasts(page):
    page.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


def open_3d_bars(page, layer_id):
    tab(page, '3d')
    got = settled(page, lambda: page.evaluate('window.app._s3dDebug()'),
                  lambda d: d['loaded'] and any(s['id'] == layer_id and s['bars'] for s in d['screens']), 10000)
    return next(s for s in got['screens'] if s['id'] == layer_id)


# ── 1. A Pixel Map rotation turns only the picture ───────────────────────

WALL = {'add': {'name': 'A', 'columns': 12, 'rows': 6}}


@pytest.mark.parametrize('deg', [90, 180, 270])
def test_a_turned_screen_keeps_its_bars_on_its_columns_on_the_tab_in_3d_and_the_pull_list(page, deg):
    ids = seed(page, [WALL])
    a = ids['A']
    tab(page, 'rigging')
    page.evaluate(f"window.app.setSelectedLayersByIds([{a}], {a})")
    page.locator('#rigging-auto-btn').click()
    page.wait_for_timeout(300)
    assert lay(page, a, 'riggingBars')['riggingBars'] == [2] * 6
    clear_toasts(page)
    turn(page, a, deg)
    tab(page, 'rigging')
    # nothing changes and nothing warns: the wall is still 12 columns
    assert lay(page, a, 'rotation', 'riggingBars') == {'rotation': deg, 'riggingBars': [2] * 6}
    assert not page.locator('#rigging-fit-warning').is_visible()
    assert 'no longer fit' not in toasts(page)
    # the tab draws them along the wall's top as the picture turns it:
    # on the right at 90, under the picture at 180, on the left at 270
    pic = picture(page, a)
    bars = sorted(hits(page, a), key=lambda h: h['start'])
    assert [(h['start'], h['span']) for h in bars] == [(s, 2) for s in range(0, 12, 2)]
    if deg == 90:
        assert all(h['x0'] >= pic['x'] + pic['w'] - 1 for h in bars), (bars, pic)
        assert abs(sum(h['y1'] - h['y0'] for h in bars) - pic['h']) < 2
        # column 0 (the wall's left) is at the top of the picture
        assert bars[0]['y0'] < bars[-1]['y0']
    elif deg == 180:
        assert all(h['y0'] >= pic['y'] + pic['h'] - 1 for h in bars), (bars, pic)
        assert abs(sum(h['x1'] - h['x0'] for h in bars) - pic['w']) < 2
        # column 0 is on the right of the picture, as 3D builds it turned round
        assert bars[0]['x0'] > bars[-1]['x0']
    else:
        assert all(h['x1'] <= pic['x'] + 1 for h in bars), (bars, pic)
        assert abs(sum(h['y1'] - h['y0'] for h in bars) - pic['h']) < 2
        assert bars[0]['y0'] > bars[-1]['y0']
    # the 3D tab stands the same bars, in the wall's column order
    assert stage_slices(page, a) == [{'row': 'header', 'bars': [[s, 2] for s in range(0, 12, 2)], 'fits': True}]
    # the pull list counts what it counts at 0
    assert pull_rig(page) == [('Header Bar - Double', 6)]
    s = open_3d_bars(page, a)
    row = s['bars'][0]
    assert row['bars'] == [2] * 6 and row['wallSlots'] == 12 and row['fits']
    assert row['lengthMm'] == pytest.approx(6000)
    assert page.errors == []


def test_a_turned_screen_takes_corners_and_the_curve_in_its_column_order(page):
    """At 180 the corner bar sits on the same columns on the tab and in 3D,
    and the Curve is no longer refused for a turned screen."""
    ids = seed(page, [{'add': {'name': 'A', 'columns': 6, 'rows': 2},
                       'extra': {'rotation': 180, 'riggingSizes': [1, 2],
                                 'riggingCorners': [{'at': 2.5, 'angle': 90, 'side': 'interior'}]}}])
    a = ids['A']
    tab(page, 'rigging')
    page.evaluate(f"window.app.setSelectedLayersByIds([{a}], {a})")
    page.locator('#rigging-auto-btn').click()
    page.wait_for_timeout(300)
    spots = page.evaluate(f"window.app.riggingCornerSpots(window.app.project.layers.find(l => l.id === {a}))")
    # the corner between panels 2 and 3 of the wall covers columns 1 and 2,
    # read in the wall's own order (it used to be mirrored at 180)
    assert [(s['start'], s['size'], s['bar']) for s in spots] == [(1, 2, True)]
    assert [1, 2] in stage_slices(page, a)[0]['bars']
    # the tab draws the corner bar on those columns, turned with the picture
    corner = [h for h in hits(page, a) if h['start'] == 1 and h['span'] == 2]
    assert len(corner) == 1
    assert page.evaluate(f"window.app._curveCannot(window.app.project.layers.find(l => l.id === {a}))") == ''
    assert page.errors == []


def test_an_old_show_with_bars_across_a_turned_screens_rows_opens_fixed_or_flagged(page):
    """Saved when a quarter-turned screen's bars ran across its rows: the
    Auto row is laid again along its columns as the show opens, and said;
    the custom row is left, and the box says it runs past the wall."""
    ids = seed(page, [
        {'add': {'name': 'AUTO', 'columns': 12, 'rows': 6},
         'extra': {'rotation': 90, 'riggingBars': [2, 2, 2], 'riggingSizes': [2], 'riggingCustom': False}},
        {'add': {'name': 'HAND', 'columns': 4, 'rows': 6, 'offset_x': 3000},
         'extra': {'rotation': 270, 'riggingBars': [2, 2, 2], 'riggingSizes': [2], 'riggingCustom': True}},
    ])
    clear_toasts(page)
    page.evaluate("""async () => { const p = await (await fetch('/api/project')).json();
        await window.app._openProjectData(p, {source: 'file'}); }""")
    page.wait_for_timeout(1500)
    auto = settled(page, lambda: lay(page, ids['AUTO'], 'riggingBars'), lambda v: v['riggingBars'] == [2] * 6)
    assert auto['riggingBars'] == [2] * 6
    said = settled(page, lambda: toasts(page), lambda t: 'laid again' in t)
    assert "Header/Footer bars on AUTO were laid again along the wall's columns" in said, said
    # saved with the show
    srv = page.evaluate(f"""async () => (await (await fetch('/api/project')).json()).layers.find(l => l.id === {ids['AUTO']}).riggingBars""")
    assert srv == [2] * 6
    # the custom row is left as it was and flagged
    assert lay(page, ids['HAND'], 'riggingBars')['riggingBars'] == [2, 2, 2]
    tab(page, 'rigging')
    assert page.locator('#rigging-fit-warning').is_visible()
    assert 'HAND: header bars run 2 panels past the wall' in page.locator('#rigging-fit-text').text_content()
    assert page.errors == []


# ── 2. A bar over a half column is its full length ──────────────────────

HALF = [
    {'add': {'name': 'RIGHT', 'columns': 4, 'rows': 2, 'halfLastColumn': True},
     'extra': {'riggingFooterBars': [2, 2], 'riggingSide': 'footer', 'riggingSizes': [2]}},
    {'add': {'name': 'LEFT', 'columns': 4, 'rows': 2, 'halfFirstColumn': True, 'offset_x': 2000},
     'extra': {'riggingFooterBars': [2, 2], 'riggingSide': 'footer', 'riggingSizes': [2]}},
]


def test_a_bar_over_a_half_column_is_full_length_hangs_past_and_says_so(page):
    ids = seed(page, HALF)
    r, l = ids['RIGHT'], ids['LEFT']
    widths = page.evaluate(f"window.app.riggingColumns(window.app.project.layers.find(x => x.id === {r})).widths")
    assert widths == [200, 200, 200, 100]
    tab(page, 'rigging')
    # said in plain words, nothing to press
    assert page.locator('#rigging-fit-warning').is_visible()
    assert page.locator('#rigging-overhang-section').is_visible()
    assert not page.locator('#rigging-fit-section').is_visible()
    text = page.locator('#rigging-overhang-text').text_content()
    assert 'RIGHT: the footer double at the right end hangs 250 mm past the wall.' in text, text
    assert 'LEFT: the footer double at the left end hangs 250 mm past the wall.' in text, text
    # the tab draws each double two whole panels long
    pic = picture(page, r)
    bars = sorted(hits(page, r), key=lambda h: h['start'])
    assert [round((h['x1'] - h['x0']) / pic['unit'], 3) for h in bars] == [2, 2]
    assert bars[0]['x0'] == pytest.approx(pic['x'], abs=1)
    assert bars[1]['x1'] - (pic['x'] + pic['w']) == pytest.approx(pic['unit'] / 2, abs=1)
    pic = picture(page, l)
    bars = sorted(hits(page, l), key=lambda h: h['start'])
    assert [round((h['x1'] - h['x0']) / pic['unit'], 3) for h in bars] == [2, 2]
    assert pic['x'] - bars[0]['x0'] == pytest.approx(pic['unit'] / 2, abs=1)
    assert bars[1]['x1'] == pytest.approx(pic['x'] + pic['w'], abs=1)
    # the pull list counts two doubles each, nothing cut
    assert pull_rig(page) == [('Footer Bar - Double', 4)]
    # 3D stands them at full length too, hanging past the same end
    s = open_3d_bars(page, r)
    row = s['bars'][0]
    assert row['lengthMm'] == pytest.approx(2000)
    assert row['last'][0] - row['first'][0] == pytest.approx(2000, abs=0.01)
    assert row['last'][0] == pytest.approx(s['widthMm'] / 2 + 250, abs=0.01)
    s = next(x for x in page.evaluate('window.app._s3dDebug()')['screens'] if x['id'] == l)
    row = s['bars'][0]
    assert row['lengthMm'] == pytest.approx(2000)
    assert row['first'][0] == pytest.approx(-s['widthMm'] / 2 - 250, abs=0.01)
    assert page.errors == []


def test_a_wall_of_whole_columns_says_nothing_of_overhangs(page):
    ids = seed(page, [{'add': {'name': 'FULL', 'columns': 4, 'rows': 2},
                       'extra': {'riggingFooterBars': [2, 2], 'riggingSide': 'footer'}}])
    tab(page, 'rigging')
    assert page.evaluate(f"window.app.riggingOverhangs(window.app.project.layers.find(l => l.id === {ids['FULL']}))") == []
    assert not page.locator('#rigging-overhang-section').is_visible()
    assert page.errors == []
