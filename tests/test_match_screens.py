"""Canvas Size and Match Screens on the toolbar (owner, 2026-11-18).

The rulings:
  * "Raster" reads "Canvas Size" in every displayed string; the app's name
    and the internal ids (toolbar-raster-width, showRasterSize, ...) stay.
  * A Match Screens button right after the Canvas Size W x H fields acts on
    the active canvas: its origin stays 0,0, no screen moves, the width
    becomes the furthest right edge (x + width) and the height the furthest
    bottom edge (y + height) of the canvas's VISIBLE screens. One screen at
    960,540 sized 960 x 540 makes the canvas 1920 x 1080.
  * Each screen is measured as the app draws it (the renderer's draw
    frame): its cabinets' own rectangles, half columns at their real size,
    turned for a 90 or 270 rotation, at its Show Look position in Show
    Look, Data and Power. Only cabinets with pixels count: hidden and blank
    cabinets are left out, as the processor span leaves them out. A screen
    counts where the renderer draws it (its `visible` flag is truthy);
    text and image layers never count.
  * Pixel Map and Cabinet ID size the Pixel Map canvas (raster_* fields,
    and the Show Look size with it only while the two are linked); Show
    Look, Data and Power size only the Show Look canvas (show_raster_*).
  * A screen that starts left of or above 0,0 stays put, and a toast
    names it: part of it is outside the canvas.
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
# ('other'), visible (false), rotation, halfLastColumn, panelStates
# ([{row, col, hidden|blank}]), show ([x, y], its Show Look position),
# group (a group name; members of one name are grouped), kind ('text' or
# 'image', placed at x, y and cols x cw by rows x ch). `opts.show` gives
# both canvases a Show Look size of their own ([w, h]), unlinked.
SEED_JS = """async ({specs, opts}) => {
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
    const show = (opts && opts.show) || [3840, 2160];
    const size = {raster_width: 3840, raster_height: 2160,
                  show_raster_width: show[0], show_raster_height: show[1]};
    proj.canvases = [
        Object.assign({}, base, size, {id: 'c1', name: 'Main', workspace_x: 0, workspace_y: 0}),
        Object.assign({}, base, size, {id: 'c2', name: 'Other', workspace_x: 0, workspace_y: 6000}),
    ];
    proj.active_canvas_id = 'c1';
    await j('PUT', '/api/project', proj);
    const ids = {};
    const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    for (const s of specs) {
        const canvas_id = s.canvas === 'other' ? 'c2' : 'c1';
        let l;
        if (s.kind === 'text') {
            l = await j('POST', '/api/layer/add-text', {name: s.name, textContent: s.name,
                offset_x: s.x, offset_y: s.y, textWidth: s.cols * s.cw,
                textHeight: s.rows * s.ch, canvas_id});
        } else if (s.kind === 'image') {
            l = await j('POST', '/api/layer/add-image', {name: s.name, imageData: PNG,
                imageWidth: s.cols * s.cw, imageHeight: s.rows * s.ch,
                offset_x: s.x, offset_y: s.y, canvas_id});
        } else {
            l = await j('POST', '/api/layer/add', Object.assign({
                name: s.name, offset_x: s.x, offset_y: s.y, columns: s.cols, rows: s.rows,
                cabinet_width: s.cw, cabinet_height: s.ch, canvas_id},
                s.halfLastColumn ? {halfLastColumn: true} : {},
                s.panelStates ? {panelStates: s.panelStates} : {}));
        }
        const put = {};
        if (s.visible === false) put.visible = false;
        if (s.rotation) put.rotation = s.rotation;
        if (s.show) { put.showOffsetX = s.show[0]; put.showOffsetY = s.show[1]; }
        if (Object.keys(put).length) await j('PUT', `/api/layer/${l.id}`, put);
        ids[s.name] = l.id;
    }
    const groupNames = [...new Set(specs.filter(s => s.group).map(s => s.group))];
    if (groupNames.length) {
        const now = await j('GET', '/api/project');
        now.groups = groupNames.map((g, i) => ({id: 'g' + (i + 1), name: g,
            layer_ids: specs.filter(s => s.group === g).map(s => ids[s.name])}));
        now.layers.forEach(l => {
            const s = specs.find(x => ids[x.name] === l.id);
            if (s && s.group) l.group_id = 'g' + (groupNames.indexOf(s.group) + 1);
        });
        await j('PUT', '/api/project', now);
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
    const sc = srv.canvases.find(x => x.id === app.project.active_canvas_id);
    return {
        active: app.project.active_canvas_id,
        renderer: [r.rasterWidth, r.rasterHeight],
        fields: [document.getElementById('toolbar-raster-width').value,
                 document.getElementById('toolbar-raster-height').value],
        canvas: [c.raster_width, c.raster_height, c.show_raster_width, c.show_raster_height],
        server: [sc.raster_width, sc.raster_height, sc.show_raster_width, sc.show_raster_height],
        at: Object.fromEntries(srv.layers.map(l => [l.name, [l.offset_x, l.offset_y]])),
        show: Object.fromEntries(srv.layers.map(l => [l.name, [l.showOffsetX ?? null, l.showOffsetY ?? null]])),
        index: app.historyIndex,
        toasts: [...document.querySelectorAll('#app-toast-host > div')]
            .map(t => ({text: t.textContent, bg: getComputedStyle(t).backgroundColor})),
    };
}"""


def _state(pg):
    return pg.evaluate(STATE_JS)


def _seed(pg, specs, **opts):
    ids = pg.evaluate(SEED_JS, {'specs': specs, 'opts': opts})
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


# ── what counts ──────────────────────────────────────────────────────────

def test_hidden_and_blank_cabinets_do_not_count(page):
    """A 4 x 3 wall of 100 px cabinets whose last column is hidden and whose
    bottom row is blank has pixels out to 300 x 200 only, and the canvas
    ends there. A hidden cabinet inside the wall changes nothing, and a
    screen further out whose cabinets are all hidden does not count."""
    pg, errors = page
    hidden_col = [dict(row=r, col=3, hidden=True) for r in range(3)]
    blank_row = [dict(row=2, col=c, blank=True) for c in range(3)]
    inner = [dict(row=0, col=1, hidden=True)]
    dark = [dict(row=r, col=c, hidden=True) for r in range(2) for c in range(2)]
    ids = _seed(pg, [_screen('WALL', 0, 0, 4, 3, 100, 100, panelStates=hidden_col + blank_row + inner),
                     _screen('DARK', 2000, 1500, 2, 2, 100, 100, panelStates=dark)])
    flags = pg.evaluate("""(ids) => Object.fromEntries(Object.entries(ids).map(([n, id]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        return [n, [l.panels.filter(p => p.hidden).length, l.panels.filter(p => p.blank).length]];
    }))""", ids)
    assert flags == {'WALL': [4, 3], 'DARK': [4, 0]}, flags
    _match(pg)
    s = _expect_size(pg, 300, 200)
    assert s['at'] == {'WALL': [0, 0], 'DARK': [2000, 1500]}, s
    assert errors == []


def test_a_screen_the_renderer_does_not_draw_does_not_count(page):
    """The renderer draws a screen only when its visible flag is truthy, so
    a screen with no flag at all is not drawn and Match leaves it out."""
    pg, errors = page
    ids = _seed(pg, [_screen('A', 0, 0, 5, 5, 100, 100),
                     _screen('NOFLAG', 2000, 1000, 2, 2, 100, 100)])
    drawn = pg.evaluate("""(id) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        delete l.visible;
        const seen = [];
        const keep = r.renderPanel;
        r.renderPanel = function (panel, layer) {
            if (layer && !seen.includes(layer.name)) seen.push(layer.name);
            return keep.apply(this, arguments);
        };
        try { r.render(); } finally { r.renderPanel = keep; }
        return seen;
    }""", ids['NOFLAG'])
    assert 'A' in drawn and 'NOFLAG' not in drawn, drawn
    _match(pg)
    s = _expect_size(pg, 500, 500)
    assert s['at']['NOFLAG'] == [2000, 1000], s
    assert errors == []


def test_text_and_image_layers_further_out_do_not_count(page):
    pg, errors = page
    _seed(pg, [_screen('A', 0, 0, 5, 5, 100, 100),
               _screen('NOTE', 3000, 1500, 3, 1, 300, 300, kind='text'),
               _screen('LOGO', 2500, 1800, 1, 1, 300, 300, kind='image')])
    kinds = pg.evaluate("() => window.app.project.layers.map(l => [l.name, l.type || 'screen'])")
    assert sorted(kinds) == [['A', 'screen'], ['LOGO', 'image'], ['NOTE', 'text']], kinds
    _match(pg)
    s = _expect_size(pg, 500, 500)
    assert s['at'] == {'A': [0, 0], 'NOTE': [3000, 1500], 'LOGO': [2500, 1800]}, s
    assert errors == []


def test_a_grouped_wall_counts_each_member_where_it_is(page):
    """Two screens of different cabinets grouped as one wall: the canvas
    takes the members' own edges (600 + 400 wide, 4 x 100 tall), and
    neither member moves."""
    pg, errors = page
    ids = _seed(pg, [_screen('G1', 0, 0, 3, 2, 200, 200, group='Wall'),
                     _screen('G2', 600, 0, 4, 4, 100, 100, group='Wall')])
    groups = pg.evaluate("""() => window.app.project.groups.map(g => [g.name, g.layer_ids.slice().sort()])""")
    assert groups == [['Wall', sorted([ids['G1'], ids['G2']])]], groups
    _match(pg)
    s = _expect_size(pg, 1000, 400)
    assert s['at'] == {'G1': [0, 0], 'G2': [600, 0]}, s
    assert errors == []


def test_the_active_canvas_is_the_one_sized(page):
    """With the second canvas active, Match sizes it from its own screens
    and leaves the first canvas as it was."""
    pg, errors = page
    _seed(pg, [_screen('MAIN', 0, 0, 10, 5, 100, 100),
               _screen('OTHER', 500, 300, 4, 3, 100, 100, canvas='other')])
    pg.evaluate("() => window.app.setActiveCanvas('c2')")
    s = settled(pg, lambda: _state(pg), lambda v: v['active'] == 'c2' and v['fields'] == ['3840', '2160'])
    assert s['active'] == 'c2' and s['fields'] == ['3840', '2160'], s
    _match(pg)
    s = _expect_size(pg, 900, 600)
    assert s['active'] == 'c2', s
    first = pg.evaluate("""() => fetch('/api/project').then(r => r.json())
        .then(p => p.canvases.find(c => c.id === 'c1'))
        .then(c => [c.raster_width, c.raster_height, c.show_raster_width, c.show_raster_height])""")
    assert first == [3840, 2160, 3840, 2160], first
    assert s['at'] == {'MAIN': [0, 0], 'OTHER': [500, 300]}, s
    pg.evaluate("() => window.app.setActiveCanvas('c1')")
    assert errors == []


# ── left of or above 0,0 ─────────────────────────────────────────────────

PAST_ORIGIN = ('Match Screens: {} starts left of or above 0,0 and stays there, '
               'so the canvas does not show all of it.')


def _toasts(pg, n):
    s = settled(pg, lambda: _state(pg), lambda v: len(v['toasts']) >= n)
    return s


def test_a_screen_partly_past_0_0_counts_its_far_edges_and_is_named(page):
    """LEFT starts at -200,-100 and is 600 x 400, so its far edges are 400
    and 300. The canvas takes those, LEFT stays where it is, and a toast
    (not the red one) says part of it is outside the canvas."""
    pg, errors = page
    _seed(pg, [_screen('LEFT', -200, -100, 6, 4, 100, 100),
               _screen('B', 0, 0, 2, 2, 100, 100)])
    assert _state(pg)['at']['LEFT'] == [-200, -100]
    _match(pg)
    s = _expect_size(pg, 400, 300)
    assert s['at'] == {'LEFT': [-200, -100], 'B': [0, 0]}, s
    s = _toasts(pg, 1)
    assert [t['text'] for t in s['toasts']] == [PAST_ORIGIN.format('LEFT')], s
    assert s['toasts'][0]['bg'] != TOAST_RED, s
    assert errors == []


def test_screens_wholly_past_0_0_do_nothing_and_say_so(page):
    pg, errors = page
    _seed(pg, [_screen('GONE', -1000, -800, 2, 2, 100, 100)])
    before = _state(pg)
    _match(pg)
    s = _toasts(pg, 1)
    assert [t['text'] for t in s['toasts']] == [
        'Match Screens: the visible screens all sit above or left of 0,0.'], s
    assert s['toasts'][0]['bg'] != TOAST_RED, s
    pg.wait_for_timeout(300)
    s = _state(pg)
    assert s['fields'] == ['3840', '2160'] and s['server'][:2] == [3840, 2160], s
    assert s['index'] == before['index'], s
    assert errors == []


# ── Show Look, Data and Power ────────────────────────────────────────────

# Pixel Map: A to 500,500 and B to 2200,1200. Show Look: A at 1000,600 to
# 1500,1100 and B at 200,200 to 400,400.
SHOW_SPECS = [_screen('A', 0, 0, 5, 5, 100, 100, show=[1000, 600]),
              _screen('B', 2000, 1000, 2, 2, 100, 100, show=[200, 200])]


def _view(pg, mode):
    pg.locator(f'#view-tabs .view-tab[data-mode="{mode}"]').click()
    pg.wait_for_function("(m) => window.canvasRenderer.viewMode === m", arg=mode, timeout=10000)


@pytest.mark.parametrize('mode', ['show-look', 'data-flow', 'power'])
def test_in_a_show_view_it_sizes_only_the_show_look_canvas(page, mode):
    """In Show Look, Data and Power the screens are where Show Look puts
    them, and Match writes only the Show Look size: 1500 x 1100 from the
    show positions, while the Pixel Map size stays 3840 x 2160."""
    pg, errors = page
    _seed(pg, SHOW_SPECS)
    try:
        _view(pg, mode)
        s = settled(pg, lambda: _state(pg), lambda v: v['fields'] == ['3840', '2160'])
        assert s['fields'] == ['3840', '2160'], s
        _match(pg)
        s = settled(pg, lambda: _state(pg),
                    lambda v: v['server'] == [3840, 2160, 1500, 1100] and v['fields'] == ['1500', '1100'])
        assert s['fields'] == ['1500', '1100'], s
        assert s['renderer'] == [1500, 1100], s
        assert s['canvas'] == [3840, 2160, 1500, 1100], s
        assert s['server'] == [3840, 2160, 1500, 1100], s
        assert s['at'] == {'A': [0, 0], 'B': [2000, 1000]}, s
        assert s['show'] == {'A': [1000, 600], 'B': [200, 200]}, s
    finally:
        _view(pg, 'pixel-map')
    s = settled(pg, lambda: _state(pg), lambda v: v['fields'] == ['3840', '2160'])
    assert s['fields'] == ['3840', '2160'] and s['renderer'] == [3840, 2160], s
    assert errors == []


def test_pixel_map_reads_pixel_map_positions_not_show_look(page):
    """The same screens on Pixel Map: 2200 x 1200 from where they sit on
    the Pixel Map, and the Show Look size, linked, follows."""
    pg, errors = page
    _seed(pg, SHOW_SPECS)
    _match(pg)
    s = _expect_size(pg, 2200, 1200)
    assert s['server'] == [2200, 1200, 2200, 1200], s
    assert s['show'] == {'A': [1000, 600], 'B': [200, 200]}, s
    assert errors == []


def test_pixel_map_leaves_an_unlinked_show_look_size_alone(page):
    """The Show Look canvas has a size of its own (3000 x 2000): Match on
    the Pixel Map sizes only the Pixel Map canvas."""
    pg, errors = page
    _seed(pg, [_screen('MID', 960, 540, 2, 1, 480, 540)], show=[3000, 2000])
    assert _state(pg)['server'] == [3840, 2160, 3000, 2000]
    _match(pg)
    s = _expect_size(pg, 1920, 1080)
    assert s['server'] == [1920, 1080, 3000, 2000], s
    assert s['canvas'] == [1920, 1080, 3000, 2000], s
    assert errors == []


# ── the words ────────────────────────────────────────────────────────────

RECORD_TOASTS_JS = """() => {
    const app = window.app;
    if (!app.__matchToastKeep) {
        app.__matchToastKeep = app._toast;
        app._toast = function (msg) {
            (window.__matchToasts = window.__matchToasts || []).push(String(msg));
            return app.__matchToastKeep.apply(this, arguments);
        };
    }
    window.__matchToasts = [];
}"""


def test_no_toast_or_guide_text_says_raster(page):
    """Every toast Match Screens can show, and every guide step's title and
    text, read Canvas Size or canvas, never raster."""
    pg, errors = page
    pg.evaluate(RECORD_TOASTS_JS)
    try:
        # no visible screen; all past 0,0; one past 0,0; already fits
        _seed(pg, [_screen('GONE', 3000, 2000, 2, 2, 100, 100, visible=False)])
        _match(pg)
        _toasts(pg, 1)
        _seed(pg, [_screen('UP', -1000, -800, 2, 2, 100, 100)])
        _match(pg)
        _toasts(pg, 1)
        _seed(pg, [_screen('LEFT', -200, -100, 6, 4, 100, 100)])
        _match(pg)
        _expect_size(pg, 400, 300)
        _toasts(pg, 1)
        _match(pg)
        said = settled(pg, lambda: pg.evaluate("() => window.__matchToasts.slice()"),
                       lambda v: len(v) >= 5)
    finally:
        pg.evaluate("""() => { const app = window.app;
            if (app.__matchToastKeep) { app._toast = app.__matchToastKeep; delete app.__matchToastKeep; } }""")
    assert len(said) >= 5, said
    assert 'The canvas already fits its screens: 400 × 300.' in said, said
    assert not [t for t in said if 'raster' in t.lower()], said
    guide = pg.evaluate("""() => {
        const out = [];
        const steps = window.QuickStart.steps();
        for (const [key, s] of Object.entries(steps)) {
            for (const f of ['title', 'body', 'intro', 'outro']) {
                let v = s && s[f];
                if (typeof v === 'function') { try { v = v(); } catch (e) { v = null; } }
                if (typeof v === 'string') out.push([key, f, v]);
            }
        }
        return out;
    }""")
    assert any(k == 'matchScreens' and f == 'body' for k, f, _ in guide), guide[:5]
    hits = [(k, f, v) for k, f, v in guide
            if 'raster' in v.lower().replace('led raster designer', '')]
    assert hits == [], hits
    assert errors == []
