"""Canvas Size and Match Screens on the toolbar (owner, 2026-11-18).

The rulings:
  * "Raster" reads "Canvas Size" in every displayed string; the app's name
    and the internal ids (toolbar-raster-width, showRasterSize, ...) stay.
  * A Match Screens button right after the Canvas Size W x H fields acts on
    the active canvas: its origin stays 0,0, no screen moves, the width
    becomes the furthest right edge (x + width) and the height the furthest
    bottom edge (y + height) of the canvas's VISIBLE screens. One screen at
    960,540 sized 960 x 540 makes the canvas 1920 x 1080.
  * Each screen is measured as the app draws it (the renderer's
    getLayerFootprintInActiveView): its cabinets' own rectangles, half
    columns at their real size, turned for a 90 or 270 rotation.
  * It writes through the toolbar fields' own path, as one undo step. With
    no visible screen on the canvas it does nothing and says so.
  * It is hidden wherever the fields are (the 3D tab).

Run locally:
    python -m pytest tests/test_match_screens.py -v -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

TOAST_RED = 'rgb(168, 50, 75)'   # _toast's error colour, #a8324b


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true"
                         " && window.canvasRenderer"
                         " && window.canvasRenderer.zoom > 0", timeout=20000)
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


# A scratch project: one canvas ("Main", 3840 x 2160) and a second
# ("Other"), then the screens `specs` names. Each spec: name, x, y,
# columns, rows, cabinet w, cabinet h, and optional extras - canvas
# ('other'), visible (false), rotation, halfLastColumn.
SEED_JS = """async (specs) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(x => x.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    const base = proj.canvases[0];
    const size = {raster_width: 3840, raster_height: 2160,
                  show_raster_width: 3840, show_raster_height: 2160};
    proj.canvases = [
        Object.assign({}, base, size, {id: 'c1', name: 'Main', workspace_x: 0, workspace_y: 0}),
        Object.assign({}, base, size, {id: 'c2', name: 'Other', workspace_x: 0, workspace_y: 6000}),
    ];
    proj.active_canvas_id = 'c1';
    await j('PUT', '/api/project', proj);
    const ids = {};
    for (const s of specs) {
        const l = await j('POST', '/api/layer/add', Object.assign({
            name: s.name, offset_x: s.x, offset_y: s.y, columns: s.cols, rows: s.rows,
            cabinet_width: s.cw, cabinet_height: s.ch,
            canvas_id: s.canvas === 'other' ? 'c2' : 'c1'},
            s.halfLastColumn ? {halfLastColumn: true} : {}));
        const put = {};
        if (s.visible === false) put.visible = false;
        if (s.rotation) put.rotation = s.rotation;
        if (Object.keys(put).length) await j('PUT', `/api/layer/${l.id}`, put);
        ids[s.name] = l.id;
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('match_screens_seed');
    app.project.active_canvas_id = 'c1';
    const first = app.project.layers.find(l => l.canvas_id === 'c1');
    if (first) app.selectLayer(first);
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    r.viewMode = 'pixel-map';
    app.syncRasterFromProject();
    app.renderLayers();
    app.updateUI();
    r.fitToView();
    app.resetHistory('Match Screens Seed');
    const host = document.getElementById('app-toast-host');
    if (host) host.innerHTML = '';
    r.render();
    return ids;
}"""

STATE_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    const c = app.project.canvases.find(x => x.id === app.project.active_canvas_id);
    const srv = await (await fetch('/api/project')).json();
    const sc = srv.canvases.find(x => x.id === 'c1');
    return {
        active: app.project.active_canvas_id,
        renderer: [r.rasterWidth, r.rasterHeight],
        fields: [document.getElementById('toolbar-raster-width').value,
                 document.getElementById('toolbar-raster-height').value],
        canvas: [c.raster_width, c.raster_height, c.show_raster_width, c.show_raster_height],
        server: [sc.raster_width, sc.raster_height, sc.show_raster_width, sc.show_raster_height],
        at: Object.fromEntries(srv.layers.map(l => [l.name, [l.offset_x, l.offset_y]])),
        index: app.historyIndex,
        toasts: [...document.querySelectorAll('#app-toast-host > div')]
            .map(t => ({text: t.textContent, bg: getComputedStyle(t).backgroundColor})),
    };
}"""


def _state(pg):
    return pg.evaluate(STATE_JS)


def _seed(pg, specs):
    ids = pg.evaluate(SEED_JS, specs)
    s = _state(pg)
    assert s['fields'] == ['3840', '2160'] and s['server'][:2] == [3840, 2160], s
    return ids


def _match(pg):
    pg.locator('#btn-match-screens').click()


def _expect_size(pg, w, h):
    want = [str(w), str(h)]
    s = settled(pg, lambda: _state(pg),
                lambda v: v['fields'] == want and v['server'][:2] == [w, h])
    assert s['fields'] == want, s
    assert s['renderer'] == [w, h], s
    assert s['canvas'][:2] == [w, h] and s['server'][:2] == [w, h], s
    return s


def _screen(name, x, y, cols, rows, cw, ch, **extra):
    return dict(name=name, x=x, y=y, cols=cols, rows=rows, cw=cw, ch=ch, **extra)


# ── the rename ───────────────────────────────────────────────────────────

def test_the_toolbar_reads_canvas_size(page):
    pg, errors = page
    pg.locator('.view-tab[data-mode="pixel-map"]').click()
    got = pg.evaluate("""() => {
        const strip = document.getElementById('canvas-controls');
        const tip = (id) => document.getElementById(id).getAttribute('data-tooltip');
        const w = document.getElementById('toolbar-raster-width');
        const label = w.previousElementSibling;
        const h = document.getElementById('toolbar-raster-height');
        const btn = document.getElementById('btn-match-screens');
        return {
            label: label.textContent,
            width: tip('toolbar-raster-width'), height: tip('toolbar-raster-height'),
            fit: tip('btn-fit'),
            // the button sits right after the H field
            after: h.nextElementSibling === btn,
            button: btn.textContent, buttonTip: tip('btn-match-screens'),
            inStrip: btn.parentElement === strip,
            sameLook: getComputedStyle(btn).backgroundColor
                === getComputedStyle(document.getElementById('btn-fit')).backgroundColor,
            visible: btn.offsetParent !== null,
            textLayerOption: document.getElementById('text-layer-show-raster-size')
                .parentElement.textContent.trim(),
            scaleOption: document.querySelector('#export-scale option[value="1"]').textContent,
        };
    }""")
    assert got == {
        'label': 'Canvas Size:',
        'width': 'Canvas Width, Total canvas width in pixels. This is the output resolution width.',
        'height': 'Canvas Height, Total canvas height in pixels. This is the output resolution height.',
        'fit': 'Fit canvas to view (Ctrl/Cmd+Shift+1)',
        'after': True,
        'button': 'Match Screens',
        'buttonTip': 'Match Screens, Size the canvas so every visible screen on it fits, '
                     'from 0,0. The screens stay where they are.',
        'inStrip': True, 'sameLook': True, 'visible': True,
        'textLayerOption': 'Canvas Size',
        'scaleOption': '1x (native canvas size)',
    }, got
    assert errors == []


def test_no_displayed_string_on_the_page_says_raster(page):
    """Every label, option, tooltip, title and placeholder the page carries:
    none says raster, except the app's own name."""
    pg, _ = page
    hits = pg.evaluate("""() => {
        const out = [];
        const say = (s) => s && /raster/i.test(s.replace(/LED[ -]Raster[ -]Designer/gi, ''));
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n;
        while ((n = walker.nextNode())) {
            const tag = n.parentElement && n.parentElement.tagName;
            if (tag === 'SCRIPT' || tag === 'STYLE') continue;
            if (say(n.textContent)) out.push(n.textContent.trim().slice(0, 120));
        }
        document.querySelectorAll('[data-tooltip],[title],[placeholder],[aria-label]').forEach(el => {
            for (const a of ['data-tooltip', 'title', 'placeholder', 'aria-label']) {
                if (say(el.getAttribute(a))) out.push(a + ': ' + el.getAttribute(a).slice(0, 120));
            }
        });
        return out;
    }""")
    assert hits == [], hits


def test_the_text_layer_line_reads_canvas_size(page):
    """The Canvas Size line a text layer adds (Dynamic Info), as it draws on
    the canvas and in every exported image."""
    pg, errors = page
    _seed(pg, [_screen('ONE', 0, 0, 2, 2, 100, 100)])
    lines = pg.evaluate("""() => {
        const r = window.canvasRenderer;
        const drawn = [];
        const keep = r._fillText;
        r._fillText = function (text) { drawn.push(String(text)); return keep.apply(this, arguments); };
        try {
            for (const exportMode of [false, true]) {
                r.exportMode = exportMode;
                r.renderTextLayer({type: 'text', id: 'tx', showOnPixelMap: true, showRasterSize: true,
                    textContent: 'Note', offset_x: 0, offset_y: 0, textWidth: 900, textHeight: 300});
            }
        } finally {
            r._fillText = keep;
            r.exportMode = false;
            r.render();
        }
        return drawn;
    }""")
    assert lines.count('Canvas Size: 3840 × 2160') == 2, lines
    assert not any('Raster' in t for t in lines), lines
    assert errors == []


# ── Match Screens ────────────────────────────────────────────────────────

def test_the_owners_example_one_screen_at_960_540(page):
    """One screen at 960,540 sized 960 x 540 makes the canvas 1920 x 1080,
    and the screen stays at 960,540."""
    pg, errors = page
    _seed(pg, [_screen('MID', 960, 540, 2, 1, 480, 540)])
    _match(pg)
    s = _expect_size(pg, 1920, 1080)
    assert s['at'] == {'MID': [960, 540]}, s
    # Show Look followed, the two sizes were linked
    assert s['server'] == [1920, 1080, 1920, 1080], s
    assert errors == []


def test_several_screens_take_the_furthest_right_and_bottom_edges(page):
    pg, errors = page
    specs = [_screen('A', 0, 0, 5, 5, 100, 100),          # to 500, 500
             _screen('B', 1200, 100, 6, 3, 100, 100),     # right edge 1800
             _screen('C', 300, 900, 4, 4, 100, 100)]      # bottom edge 1300
    _seed(pg, specs)
    _match(pg)
    s = _expect_size(pg, 1800, 1300)
    assert s['at'] == {'A': [0, 0], 'B': [1200, 100], 'C': [300, 900]}, s
    assert errors == []


def test_a_hidden_screen_and_another_canvas_do_not_count(page):
    """A hidden screen further out is ignored, and so is a screen on the
    other canvas; both stay where they are."""
    pg, errors = page
    specs = [_screen('A', 0, 0, 5, 5, 100, 100),
             _screen('B', 1200, 100, 6, 3, 100, 100),
             _screen('GONE', 3000, 2000, 4, 4, 200, 200, visible=False),
             _screen('ELSEWHERE', 5000, 4000, 2, 2, 200, 200, canvas='other')]
    _seed(pg, specs)
    _match(pg)
    s = _expect_size(pg, 1800, 500)
    assert s['at']['GONE'] == [3000, 2000] and s['at']['ELSEWHERE'] == [5000, 4000], s
    other = pg.evaluate("""() => fetch('/api/project').then(r => r.json())
        .then(p => p.canvases.find(c => c.id === 'c2'))
        .then(c => [c.raster_width, c.raster_height])""")
    assert other == [3840, 2160], other
    assert errors == []


def test_a_rotated_screen_counts_as_drawn(page):
    """A 4 x 1 wall of 100 px cabinets at 1000,1000 is 400 x 100; turned 90
    degrees about its centre it stands 100 wide and 400 tall, from 1150,850
    to 1250,1250. The canvas takes the turned edges, not 1400 x 1100."""
    pg, errors = page
    ids = _seed(pg, [_screen('TURNED', 1000, 1000, 4, 1, 100, 100, rotation=90)])
    rot = pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).rotation",
                      ids['TURNED'])
    assert rot == 90, rot
    _match(pg)
    s = _expect_size(pg, 1250, 1250)
    assert s['at'] == {'TURNED': [1000, 1000]}, s
    assert errors == []


def test_a_half_column_counts_at_its_real_size(page):
    """Three 100 px columns with a half last column end at 250, not 300."""
    pg, errors = page
    ids = _seed(pg, [_screen('HALF', 0, 0, 3, 2, 100, 100, halfLastColumn=True)])
    widths = pg.evaluate("""(id) => window.app.project.layers.find(l => l.id === id)
        .panels.filter(p => p.col === 2).map(p => p.width)""", ids['HALF'])
    assert widths == [50, 50], widths
    _match(pg)
    _expect_size(pg, 250, 200)
    assert errors == []


def test_it_is_one_undo_step(page):
    pg, errors = page
    _seed(pg, [_screen('MID', 960, 540, 2, 1, 480, 540)])
    before = _state(pg)
    _match(pg)
    after = _expect_size(pg, 1920, 1080)
    assert after['index'] == before['index'] + 1, (before['index'], after['index'])
    pg.evaluate("() => window.app.undo()")
    back = settled(pg, lambda: _state(pg),
                   lambda v: v['fields'] == ['3840', '2160'] and v['server'][:2] == [3840, 2160])
    assert back['fields'] == ['3840', '2160'], back
    assert back['renderer'] == [3840, 2160] and back['server'] == [3840, 2160, 3840, 2160], back
    assert back['index'] == before['index'], back
    pg.evaluate("() => window.app.redo()")
    _expect_size(pg, 1920, 1080)
    assert errors == []


def test_no_visible_screens_does_nothing_and_says_so(page):
    pg, errors = page
    _seed(pg, [_screen('GONE', 3000, 2000, 4, 4, 200, 200, visible=False)])
    before = _state(pg)
    _match(pg)
    s = settled(pg, lambda: _state(pg), lambda v: len(v['toasts']) == 1)
    assert [t['text'] for t in s['toasts']] == [
        'Match Screens: there are no visible screens on this canvas.'], s
    assert s['toasts'][0]['bg'] != TOAST_RED, s
    pg.wait_for_timeout(300)
    s = _state(pg)
    assert s['fields'] == ['3840', '2160'] and s['server'][:2] == [3840, 2160], s
    assert s['index'] == before['index'], s
    assert errors == []


def test_a_canvas_that_already_fits_is_left_alone(page):
    pg, errors = page
    _seed(pg, [_screen('MID', 960, 540, 2, 1, 480, 540)])
    _match(pg)
    s = _expect_size(pg, 1920, 1080)
    pg.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")
    _match(pg)
    t = settled(pg, lambda: _state(pg), lambda v: len(v['toasts']) == 1)
    assert [x['text'] for x in t['toasts']] == ['The canvas already fits its screens: 1920 × 1080.'], t
    assert t['index'] == s['index'], t
    assert errors == []


def test_hidden_on_the_3d_tab_with_the_fields(page):
    pg, errors = page
    pg.locator('.view-tab[data-mode="3d"]').click()
    pg.wait_for_function("() => document.getElementById('canvas-container').classList.contains('s3d-on')",
                         timeout=10000)
    shown = pg.evaluate("""() => ['toolbar-raster-width', 'btn-match-screens']
        .map(id => getComputedStyle(document.getElementById(id)).display)""")
    assert shown == ['none', 'none'], shown
    pg.locator('.view-tab[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(300)
    shown = pg.evaluate("""() => ['toolbar-raster-width', 'btn-match-screens']
        .map(id => getComputedStyle(document.getElementById(id)).display)""")
    assert 'none' not in shown, shown
    assert errors == []


# ── a Brompton's canvas ──────────────────────────────────────────────────

BROMPTON_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(x => x.json());
    for (const name of ['Wing L', 'Wing R']) {
        const l = app.project.layers.find(x => x.name === name);
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'brompton',
            bitDepth: 8, frameRate: 60, flowPattern: 'tl-v'});
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('match_screens_brompton');
    await app.refreshProcessors();
    await app._processorRequest('/api/processors', 'POST',
                                {deviceId: 'brompton-sx40', name: 'WINGS'}, 'Add Processor');
    const sx = app._processorsResolved[0];
    const card = sx.slots[0].card.id;
    for (const name of ['Wing L', 'Wing R']) {
        const l = app.project.layers.find(x => x.name === name);
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(l.id), cardId: card}, null, 'Fill Ports In Order');
    }
    app.resetHistory('Match Screens Brompton');
    const host = document.getElementById('app-toast-host');
    if (host) host.innerHTML = '';
    return app.project.port_assignments.pins.length;
}"""

SPANS_JS = """() => Object.values(((window.app._assignment || {}).canvas) || {})
    .map(s => [s.width, s.height, s.fits])"""


def test_a_brompton_span_is_its_screens_not_the_canvas_size(page):
    """An SX40 drives Wing L and Wing R (3728 x 1344, inside its 4096 x
    2160); a third screen no processor feeds sits out at 4500. Match
    Screens makes the canvas 5500 wide, past 4096: the SX40's span is the
    cabinets its ports feed, which no screen move changed, so nothing is
    refused, no red toast shows and the mapping stays as it was. The
    refusal stays where a span can grow (test_canvas_refusal_toast)."""
    pg, errors = page
    _seed(pg, [_screen('Wing L', 0, 0, 9, 7, 192, 192),
               _screen('Wing R', 2000, 0, 9, 7, 192, 192),
               _screen('Side', 4500, 0, 5, 2, 200, 200)])
    pins = pg.evaluate(BROMPTON_JS)
    assert pins > 0
    spans = settled(pg, lambda: pg.evaluate(SPANS_JS), lambda s: s == [[3728, 1344, True]])
    assert spans == [[3728, 1344, True]], spans
    _match(pg)
    s = _expect_size(pg, 5500, 1344)
    assert s['at'] == {'Wing L': [0, 0], 'Wing R': [2000, 0], 'Side': [4500, 0]}, s
    pg.wait_for_timeout(400)
    s = _state(pg)
    assert not any(t['bg'] == TOAST_RED for t in s['toasts']), s
    assert pg.evaluate(SPANS_JS) == [[3728, 1344, True]]
    assert pg.evaluate("() => window.app.project.port_assignments.pins.length") == pins
    assert errors == []
