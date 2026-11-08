"""Double-click to rename, in both browsers' event orders.

Field report on 1.6.0 beta.5: in Firefox for Windows a double-click on a
screen's name in the Screens list never opened the rename. The first click
of a double-click on a screen not yet selected selects it, and selecting
rebuilds the whole list, so the second click lands on a NEW name field.
Chrome sends the dblclick to the field under the second click; Firefox
sends a dblclick only when both clicks hit the same element, so after the
rebuild it sends none and the rename (opened only by the dblclick) never
opened.

The fix (2026-11-04): the second click itself (click with detail 2) opens
the rename on the field it lands on, which reaches the live field in every
browser; the dblclick handler stays and finds the edit already open. A
plain click on the screen that is already the only selection no longer
re-selects (no rebuild for a click that changes nothing).

The canvas, group and beach names do not rebuild on a click of their own,
but the list is rebuilt when a rename that just ended elsewhere comes back
from the server, so renaming one canvas, group or beach and double-clicking
the next put a new field under the second click the same way. They open on
the second click too.

Playwright's Firefox does not start on the Windows test PC, so the Firefox
order is replayed in Chromium: a real first click (detail 1), the rebuild,
then mousedown / mouseup / click with detail 2 dispatched on the NEW field
and no dblclick at all. The Chrome order (the same plus a dblclick, and a
real Playwright double-click) is kept beside it.

The second report (Safari / Mac app, same beta): a drag inside a name being
edited moved the screen instead of selecting text. Only the field was made
undraggable in edit mode; now everything above it that is draggable (the
screen row's header, info line and row; the canvas header; the beach row;
the group's row since 1.7.0, when groups began to drag) is turned off for
the edit and back on when it ends. WebKit cannot run here either, so the attributes are
asserted directly beside the drag.

The third (1.6.0 QA, beta.6): the first drag after the double-click selected
nothing, in all four kinds of name. Opening the edit selects the whole name, so
the press lands on selected text and the browser starts a text drag: the rows'
dragstart cancelled it and the highlight fell to a caret, and the group's ran.
The press now lets go of the selection first (helpers.js
installNameDragSelects). The drags above set the caret first and missed it.

The fourth (CI, Linux Chromium, 2026-11-05): the beach name's first drag still
selected nothing. It had nothing to do with the selection or the beach. Chromium
loses a drag's start when the press lands close to the middle of a letter and
off a whole CSS pixel, in a bare text field too, and Linux's font put 10% of
that field on one. The drag now keeps the press's place itself. Which presses do
it depends on the font, so the tests below sweep the press across the name
instead of trusting one point. What a double-click leaves differs by system
(the word, the word and its space, in an open name), so they set up each shape.

Run locally:
    python -m pytest tests/test_rename_click_order.py -v -n 4 --dist loadfile
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401
from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the wiring (new files must not rot) ──────────────────────────────────

def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_every_dblclick_rename_also_opens_on_the_second_click():
    main_js = _src('src', 'static', 'js', 'main.js')
    for name in ('app-layers-panel.js', 'app-canvas-ui.js',
                 'app-screen-groups.js', 'app-beaches.js'):
        assert f"import './{name}';" in main_js, name
    rows = _src('src', 'static', 'js', 'app-layers-panel.js')
    assert "if (onName && e.detail >= 2) {" in rows
    assert "if (!nameInput.readOnly) return;" in rows
    assert "!this._layerClickChangesNothing(layer)" in rows
    for name in ('app-canvas-ui.js', 'app-screen-groups.js', 'app-beaches.js'):
        js = _src('src', 'static', 'js', name)
        assert "if (nameInput.readOnly && e.detail >= 2) startRename();" in js, name
        assert "if (!nameInput.readOnly) return;" in js, name
    # and nothing above a name being edited is draggable (helpers.js)
    assert 'holdDragOff' in _src('src', 'static', 'js', 'helpers.js')
    assert "releaseDrag = holdDragOff(nameInput, headerEl, infoEl, layerDiv);" in rows
    assert "releaseDrag = holdDragOff(nameInput, header);" in _src('src', 'static', 'js', 'app-canvas-ui.js')
    assert "releaseDrag = holdDragOff(nameInput, row);" in _src('src', 'static', 'js', 'app-beaches.js')
    assert "releaseDrag = holdDragOff(nameInput, row);" in _src('src', 'static', 'js', 'app-screen-groups.js')


# ── the browser ───────────────────────────────────────────────────────────

# Three loose screens, two groups of two, two canvases and two beaches.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = (proj.canvases || []).slice(0, 1);
    const c1 = proj.canvases.length ? proj.canvases[0].id : null;
    if (c1) { proj.canvases[0].name = 'Canvas One'; proj.active_canvas_id = c1; }
    await j('PUT', '/api/project', proj);
    const add = (name, x, y) => j('POST', '/api/layer/add', {name, columns: 2, rows: 2,
        cabinet_width: 200, cabinet_height: 200, offset_x: x, offset_y: y});
    for (const [n, x, y] of [['ALPHA', 0, 0], ['BRAVO', 600, 0], ['CHARLIE', 1200, 0],
                             ['G1A', 0, 600], ['G1B', 400, 600],
                             ['G2A', 1000, 600], ['G2B', 1400, 600]]) {
        await add(n, x, y);
    }
    const c2 = (await j('POST', '/api/canvas', {name: 'Canvas Two'})).active_canvas_id;
    if (c1) await j('PUT', `/api/canvas/${c1}/active`);
    await j('POST', '/api/beaches', {name: 'SR'});
    await j('POST', '/api/beaches', {name: 'SL'});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('rename_click_order_setup');
    const by = (n) => app.project.layers.find(l => l.name === n);
    for (const pair of [['G1A', 'G1B'], ['G2A', 'G2B']]) {
        const ids = pair.map(n => by(n).id);
        app.setSelectedLayersByIds(ids, ids[0]);
        await app.groupSelectedLayers();
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('rename_click_order_setup');
    app.selectLayer(by('CHARLIE'));
    app.renderLayers();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Rename Click Order Seed');
    return {
        a: by('ALPHA').id, b: by('BRAVO').id, c: by('CHARLIE').id,
        groups: (app.project.groups || []).map(g => g.id),
        canvases: [c1, c2],
        beaches: (app.project.beaches || []).map(b => b.id),
    };
}"""

# Every dblclick that reaches the document, counted in the capture phase,
# so a Firefox-order replay can say none was sent.
COUNT_DBLCLICKS_JS = """() => {
    window.__dblclicks = 0;
    if (!window.__dblclickCounter) {
        window.__dblclickCounter = true;
        document.addEventListener('dblclick', () => { window.__dblclicks += 1; }, true);
    }
}"""

# Hold the field the first click will hit, to tell afterwards whether a
# rebuild replaced it.
HOLD_JS = """(sel) => { window.__held = document.querySelector(sel); return !!window.__held; }"""

HELD_JS = """(sel) => {
    const now = document.querySelector(sel);
    return {connected: !!(window.__held && window.__held.isConnected),
            same: !!now && now === window.__held};
}"""

# The second click of a double-click on the field now under the pointer:
# mousedown, mouseup, click with detail 2, and a dblclick only when asked
# (Chrome's order). Firefox's order has none after a rebuild.
SECOND_CLICK_JS = """([sel, withDblclick]) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const at = {bubbles: true, cancelable: true, composed: true, view: window, button: 0,
                clientX: r.left + Math.min(20, r.width / 2), clientY: r.top + r.height / 2};
    el.dispatchEvent(new MouseEvent('mousedown', {...at, detail: 2, buttons: 1}));
    el.dispatchEvent(new MouseEvent('mouseup', {...at, detail: 2}));
    el.dispatchEvent(new MouseEvent('click', {...at, detail: 2}));
    if (withDblclick) el.dispatchEvent(new MouseEvent('dblclick', {...at, detail: 2}));
    return true;
}"""

FIELD_JS = """(sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    return {readOnly: el.readOnly, editing: el.classList.contains('editing'),
            focused: document.activeElement === el, value: el.value,
            selStart: el.selectionStart, selEnd: el.selectionEnd};
}"""

SEL_JS = """() => ({
    current: window.app.currentLayer ? window.app.currentLayer.id : null,
    selected: [...(window.app.selectedLayerIds || [])].sort((x, y) => x - y),
})"""

SERVER_JS = """async () => {
    const p = await (await fetch('/api/project')).json();
    const pick = (xs) => Object.fromEntries((xs || []).map(x => [String(x.id), x.name]));
    return {layers: pick(p.layers), canvases: pick(p.canvases), groups: pick(p.groups),
            beaches: pick(p.beaches)};
}"""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert len(ids['groups']) == 2, ids
    assert all(ids['canvases']) and len(ids['canvases']) == 2, ids
    assert len(ids['beaches']) == 2, ids
    pg.evaluate(COUNT_DBLCLICKS_JS)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _screen(layer_id):
    return f'#layers-list .layer-item[data-layer-id="{layer_id}"] .layer-name-input'


def _canvas(canvas_id):
    return f'#layers-list .canvas-group[data-canvas-id="{canvas_id}"] .canvas-name-input'


def _group(group_id):
    return f'#layers-list .screen-group[data-group-id="{group_id}"] .screen-group-name-input'


def _beach(beach_id):
    return f'#beaches-panel .beach-row[data-beach-id="{beach_id}"] .beach-name-input'


def _field(pg, sel):
    return pg.evaluate(FIELD_JS, sel)


def _first_click(pg, sel):
    """A real click (detail 1) on the field, holding the element it hit."""
    assert pg.evaluate(HOLD_JS, sel), f'no field at {sel}'
    pg.evaluate("() => { window.__dblclicks = 0; }")
    pg.locator(sel).click()


def _wait_replaced(pg, sel):
    got = settled(pg, lambda: pg.evaluate(HELD_JS, sel),
                  lambda v: not v['connected'] and pg.evaluate(
                      "(s) => !!document.querySelector(s)", sel))
    return got


def _second_click(pg, sel, dblclick=False):
    assert pg.evaluate(SECOND_CLICK_JS, [sel, dblclick])
    pg.wait_for_timeout(150)


def _assert_editing(pg, sel, cls=True):
    f = settled(pg, lambda: _field(pg, sel), lambda v: v and not v['readOnly'] and v['focused'])
    assert f and not f['readOnly'] and f['focused'], f'the rename did not open at {sel}: {f}'
    if cls:
        assert f['editing'], f'the rename opened without its .editing cue: {f}'
    return f


def _type_and_enter(pg, text):
    pg.keyboard.press('Control+A')
    pg.keyboard.type(text)
    pg.keyboard.press('Enter')


def _server_name(pg, kind, key, want):
    got = settled(pg, lambda: pg.evaluate(SERVER_JS),
                  lambda v: v[kind].get(str(key)) == want)
    assert got[kind].get(str(key)) == want, f'the {kind} rename never reached the server: {got}'


def _start_edit_by_dblclick(pg, sel, text):
    """Open a rename with a real double-click and type into it, leaving it
    open (the next gesture ends it by taking the focus)."""
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel, cls=False)
    pg.keyboard.press('Control+A')
    pg.keyboard.type(text)


# ── screens ──────────────────────────────────────────────────────────────

def test_screen_firefox_order_on_a_screen_not_yet_selected(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", c)
    pg.wait_for_timeout(200)
    sel = _screen(a)
    _first_click(pg, sel)
    # The hazard is real: the first click selected ALPHA and rebuilt the list.
    held = _wait_replaced(pg, sel)
    assert not held['connected'], f'the first click no longer rebuilds the list: {held}'
    assert pg.evaluate(SEL_JS) == {'current': a, 'selected': [a]}
    _second_click(pg, sel)
    assert pg.evaluate("() => window.__dblclicks") == 0
    _assert_editing(pg, sel)
    assert pg.evaluate(SEL_JS) == {'current': a, 'selected': [a]}
    _type_and_enter(pg, 'ALPHA-FF')
    _server_name(pg, 'layers', a, 'ALPHA-FF')
    f = _field(pg, sel)
    assert f['readOnly'] and not f['editing'] and f['value'] == 'ALPHA-FF', f


def test_screen_plain_click_on_the_only_selection_keeps_the_field(page):
    pg, ids = page
    a = ids['a']
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", a)
    pg.wait_for_timeout(200)
    sel = _screen(a)
    _first_click(pg, sel)
    pg.wait_for_timeout(250)
    held = pg.evaluate(HELD_JS, sel)
    assert held['connected'] and held['same'], f'a click that changes nothing rebuilt the list: {held}'
    f = _field(pg, sel)
    assert f['readOnly'] and not f['editing'], f'a single click opened the rename: {f}'
    assert pg.evaluate(SEL_JS) == {'current': a, 'selected': [a]}
    # and its second click, no dblclick, opens the rename on that same field
    _second_click(pg, sel)
    _assert_editing(pg, sel)
    assert pg.evaluate(HELD_JS, sel)['same']
    _type_and_enter(pg, 'ALPHA-2')
    _server_name(pg, 'layers', a, 'ALPHA-2')


def test_screen_plain_click_inside_a_multi_selection_narrows_it(page):
    """The no-rebuild short cut only covers a click that changes nothing."""
    pg, ids = page
    a, b = ids['a'], ids['b']
    pg.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[0])", [a, b])
    pg.wait_for_timeout(200)
    pg.locator(_screen(a)).click()
    got = settled(pg, lambda: pg.evaluate(SEL_JS), lambda v: v['selected'] == [a])
    assert got == {'current': a, 'selected': [a]}, got


def test_screen_chrome_order_with_the_rebuild(page):
    pg, ids = page
    b, c = ids['b'], ids['c']
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", c)
    pg.wait_for_timeout(200)
    sel = _screen(b)
    _first_click(pg, sel)
    assert not _wait_replaced(pg, sel)['connected']
    _second_click(pg, sel, dblclick=True)
    _assert_editing(pg, sel)
    assert pg.evaluate(SEL_JS) == {'current': b, 'selected': [b]}
    _type_and_enter(pg, 'BRAVO-CR')
    _server_name(pg, 'layers', b, 'BRAVO-CR')


def test_screen_dblclick_on_an_open_edit_changes_nothing(page):
    """The dblclick after the second click must not redo the edit: a caret
    placed in the open field stays where it is."""
    pg, ids = page
    b = ids['b']
    sel = _screen(b)
    _second_click(pg, sel)
    _assert_editing(pg, sel)
    pg.evaluate("(s) => { const el = document.querySelector(s); el.setSelectionRange(2, 2); }", sel)
    pg.evaluate("""(s) => document.querySelector(s).dispatchEvent(
        new MouseEvent('dblclick', {bubbles: true, cancelable: true, detail: 2}))""", sel)
    pg.wait_for_timeout(100)
    f = _field(pg, sel)
    assert not f['readOnly'] and f['focused'] and (f['selStart'], f['selEnd']) == (2, 2), f
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    assert _field(pg, sel)['readOnly']


def test_screen_real_double_click_on_a_screen_not_yet_selected(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", c)
    pg.wait_for_timeout(200)
    sel = _screen(a)
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel)
    assert pg.evaluate(SEL_JS) == {'current': a, 'selected': [a]}
    _type_and_enter(pg, 'ALPHA-3')
    _server_name(pg, 'layers', a, 'ALPHA-3')


# ── canvases, groups, beaches: the rename that just ended rebuilds ───────

def _chain(pg, first_sel, second_sel, first_text):
    """Rename the first one and, without ending it, click the second: the
    press ends the first rename, whose answer from the server rebuilds the
    list under the second click."""
    _start_edit_by_dblclick(pg, first_sel, first_text)
    _first_click(pg, second_sel)
    held = _wait_replaced(pg, second_sel)
    assert not held['connected'], (
        f'the rename that just ended did not rebuild the list: {held}')


def test_canvas_firefox_order_after_another_canvas_rename(page):
    pg, ids = page
    c1, c2 = ids['canvases']
    _chain(pg, _canvas(c1), _canvas(c2), 'STAGE')
    _server_name(pg, 'canvases', c1, 'STAGE')
    _second_click(pg, _canvas(c2))
    assert pg.evaluate("() => window.__dblclicks") == 0
    _assert_editing(pg, _canvas(c2), cls=False)
    _type_and_enter(pg, 'IMAG')
    _server_name(pg, 'canvases', c2, 'IMAG')
    assert _field(pg, _canvas(c2))['readOnly']


def test_canvas_chrome_order(page):
    pg, ids = page
    c1, c2 = ids['canvases']
    _chain(pg, _canvas(c2), _canvas(c1), 'IMAG-2')
    _second_click(pg, _canvas(c1), dblclick=True)
    _assert_editing(pg, _canvas(c1), cls=False)
    _type_and_enter(pg, 'STAGE-2')
    _server_name(pg, 'canvases', c1, 'STAGE-2')
    _server_name(pg, 'canvases', c2, 'IMAG-2')
    # and a real double-click on a field nothing rebuilds
    pg.locator(_canvas(c2)).dblclick()
    _assert_editing(pg, _canvas(c2), cls=False)
    _type_and_enter(pg, 'IMAG-3')
    _server_name(pg, 'canvases', c2, 'IMAG-3')


def test_group_firefox_order_after_another_group_rename(page):
    pg, ids = page
    g1, g2 = ids['groups']
    _chain(pg, _group(g1), _group(g2), 'MAIN WALL')
    _server_name(pg, 'groups', g1, 'MAIN WALL')
    _second_click(pg, _group(g2))
    assert pg.evaluate("() => window.__dblclicks") == 0
    _assert_editing(pg, _group(g2))
    _type_and_enter(pg, 'SIDE WALL')
    _server_name(pg, 'groups', g2, 'SIDE WALL')
    f = _field(pg, _group(g2))
    assert f['readOnly'] and not f['editing'], f


def test_group_chrome_order(page):
    pg, ids = page
    g1, g2 = ids['groups']
    _chain(pg, _group(g2), _group(g1), 'SIDE-2')
    _second_click(pg, _group(g1), dblclick=True)
    _assert_editing(pg, _group(g1))
    _type_and_enter(pg, 'MAIN-2')
    _server_name(pg, 'groups', g1, 'MAIN-2')
    _server_name(pg, 'groups', g2, 'SIDE-2')
    pg.locator(_group(g2)).dblclick()
    _assert_editing(pg, _group(g2))
    _type_and_enter(pg, 'SIDE-3')
    _server_name(pg, 'groups', g2, 'SIDE-3')


def test_beach_firefox_order_after_another_beach_rename(page):
    pg, ids = page
    b1, b2 = ids['beaches']
    _chain(pg, _beach(b1), _beach(b2), 'Stage Right')
    _server_name(pg, 'beaches', b1, 'Stage Right')
    _second_click(pg, _beach(b2))
    assert pg.evaluate("() => window.__dblclicks") == 0
    _assert_editing(pg, _beach(b2))
    _type_and_enter(pg, 'Stage Left')
    _server_name(pg, 'beaches', b2, 'Stage Left')
    f = _field(pg, _beach(b2))
    assert f['readOnly'] and not f['editing'], f


def test_beach_chrome_order(page):
    pg, ids = page
    b1, b2 = ids['beaches']
    _chain(pg, _beach(b2), _beach(b1), 'Video Village')
    _second_click(pg, _beach(b1), dblclick=True)
    _assert_editing(pg, _beach(b1))
    _type_and_enter(pg, 'FOH')
    _server_name(pg, 'beaches', b1, 'FOH')
    _server_name(pg, 'beaches', b2, 'Video Village')
    pg.locator(_beach(b2)).dblclick()
    _assert_editing(pg, _beach(b2))
    _type_and_enter(pg, 'Monitor World')
    _server_name(pg, 'beaches', b2, 'Monitor World')


def test_a_single_click_on_a_canvas_group_or_beach_name_keeps_the_field(page):
    """The audit's finding: these names are not rebuilt by a click of their
    own (the header and row handlers skip a click on an input)."""
    pg, ids = page
    for sel in (_canvas(ids['canvases'][1]), _group(ids['groups'][0]), _beach(ids['beaches'][0])):
        _first_click(pg, sel)
        pg.wait_for_timeout(300)
        held = pg.evaluate(HELD_JS, sel)
        assert held['connected'] and held['same'], f'a single click rebuilt {sel}: {held}'
        assert _field(pg, sel)['readOnly'], sel
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")


# ── a drag inside a name being edited selects text (WebKit) ───────────────
#
# Owner's report, Safari / Mac app, 1.6.0 beta.5: "I want to click and drag
# to select the text but it just tries to move the screen layer." WebKit
# starts a draggable ancestor's drag from a press-and-drag inside a text
# field, and only the field itself was made undraggable in edit mode; the
# header, info line and row stayed draggable. Chromium selects the text
# either way, so the drag is checked here AND the draggable attributes,
# which are what WebKit acts on, are asserted directly.

DRAGSTARTS_JS = """() => {
    window.__dragstarts = [];
    if (!window.__dragstartCounter) {
        window.__dragstartCounter = true;
        document.addEventListener('dragstart', (e) => {
            window.__dragstarts.push(e.target.className || e.target.tagName);
        }, true);
    }
}"""

ROW_DRAG_ATTRS_JS = """(id) => {
    const row = document.querySelector(`#layers-list .layer-item[data-layer-id="${id}"]`);
    const up = [];
    for (let el = row.parentElement; el; el = el.parentElement) if (el.draggable) up.push(el.className);
    return {row: row.draggable, header: row.querySelector('.layer-header').draggable,
            info: row.querySelector('.layer-info').draggable,
            name: row.querySelector('.layer-name-input').draggable,
            readOnly: row.querySelector('.layer-name-input').readOnly, ancestors: up};
}"""

LAYERS_JS = """() => window.app.project.layers.map(l => [l.id, l.offset_x, l.offset_y])"""

ALL_ON = {'row': True, 'header': True, 'info': True, 'name': True, 'readOnly': True, 'ancestors': []}
ALL_OFF = {'row': False, 'header': False, 'info': False, 'name': False, 'readOnly': False, 'ancestors': []}


def _drag_select(pg, sel, text):
    """Set the open field to `text`, caret at 0, then press near its left
    edge and drag to its right edge with real mouse moves."""
    pg.evaluate("([s, t]) => { const el = document.querySelector(s); el.value = t; el.setSelectionRange(0, 0); }",
                [sel, text])
    box = pg.locator(sel).bounding_box()
    y = box['y'] + box['height'] / 2
    pg.evaluate("() => { window.__dragstarts = []; }")
    pg.mouse.move(box['x'] + 4, y)
    pg.mouse.down()
    for step in range(1, 9):
        pg.mouse.move(box['x'] + 4 + step * (box['width'] - 12) / 8, y)
    pg.mouse.up()
    pg.wait_for_timeout(100)
    return pg.evaluate("""(s) => { const el = document.querySelector(s);
        return {start: el.selectionStart, end: el.selectionEnd, focused: document.activeElement === el,
                readOnly: el.readOnly}; }""", sel)


def test_screen_drag_inside_the_open_name_selects_text(page):
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    a = ids['a']
    sel = _screen(a)
    assert pg.evaluate(ROW_DRAG_ATTRS_JS, a) == ALL_ON
    before = pg.evaluate(LAYERS_JS)
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel)
    assert pg.evaluate(ROW_DRAG_ATTRS_JS, a) == ALL_OFF
    got = _drag_select(pg, sel, 'A LONG SCREEN NAME')
    assert got['start'] != got['end'], f'a drag in the open name selected no text: {got}'
    assert got['focused'] and not got['readOnly'], got
    assert pg.evaluate("() => window.__dragstarts") == []
    assert pg.evaluate(LAYERS_JS) == before, 'a drag in the open name moved or reordered a screen'
    pg.keyboard.press('Escape')
    settled(pg, lambda: _field(pg, sel), lambda v: v['readOnly'])
    assert pg.evaluate(ROW_DRAG_ATTRS_JS, a) == ALL_ON


def test_screen_rename_ended_by_enter_or_a_rebuild_leaves_rows_draggable(page):
    pg, ids = page
    a, b = ids['a'], ids['b']
    pg.locator(_screen(b)).dblclick()
    _assert_editing(pg, _screen(b))
    pg.keyboard.press('Control+A')
    pg.keyboard.type('BRAVO-E')
    pg.keyboard.press('Enter')
    _server_name(pg, 'layers', b, 'BRAVO-E')
    assert pg.evaluate(ROW_DRAG_ATTRS_JS, b) == ALL_ON
    # an edit the list rebuild ends (no blur reaches the old field)
    pg.locator(_screen(a)).dblclick()
    _assert_editing(pg, _screen(a))
    pg.evaluate("() => window.app.renderLayers()")
    pg.wait_for_timeout(150)
    for lid in (ids['a'], ids['b'], ids['c']):
        assert pg.evaluate(ROW_DRAG_ATTRS_JS, lid) == ALL_ON, lid
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")
    pg.wait_for_timeout(150)


def test_screen_row_drags_to_reorder_after_an_edit(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    order = lambda: [i for i, _, _ in pg.evaluate(LAYERS_JS) if i in (ids['a'], ids['b'], ids['c'])]
    start = order()
    # open and close an edit on the row first
    pg.locator(_screen(a)).dblclick()
    _assert_editing(pg, _screen(a))
    pg.keyboard.press('Escape')
    settled(pg, lambda: _field(pg, _screen(a)), lambda v: v['readOnly'])
    pg.evaluate("() => { window.__dragstarts = []; }")
    src = pg.locator(f'#layers-list .layer-item[data-layer-id="{a}"] .layer-info')
    dst = pg.locator(f'#layers-list .layer-item[data-layer-id="{c}"]')
    box = dst.bounding_box()
    src.drag_to(dst, target_position={'x': box['width'] / 2, 'y': box['height'] * 0.2})
    got = settled(pg, order, lambda v: v != start)
    assert got != start, f'the row did not drag to a new place: {got}'
    assert pg.evaluate("() => window.__dragstarts.length") >= 1
    # and by the name field, read-only again
    start = got
    src = pg.locator(_screen(a))
    dst = pg.locator(f'#layers-list .layer-item[data-layer-id="{ids["b"]}"]')
    box = dst.bounding_box()
    src.drag_to(dst, target_position={'x': box['width'] / 2, 'y': box['height'] * 0.8})
    got = settled(pg, order, lambda v: v != start)
    assert got != start, f'the row did not drag by its name: {got}'


def test_screen_shift_and_ctrl_clicks_keep_range_and_toggle(page):
    pg, ids = page
    a, b, c = ids['a'], ids['b'], ids['c']
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", a)
    pg.wait_for_timeout(150)
    pg.locator(_screen(c)).click(modifiers=['Control'])
    got = settled(pg, lambda: pg.evaluate(SEL_JS), lambda v: v['selected'] == sorted([a, c]))
    assert got['selected'] == sorted([a, c]) and got['current'] == c, got
    pg.locator(_screen(c)).click(modifiers=['Control'])
    got = settled(pg, lambda: pg.evaluate(SEL_JS), lambda v: v['selected'] == [a])
    assert got['selected'] == [a], got
    pg.locator(_screen(c)).click(modifiers=['Shift'])
    got = settled(pg, lambda: pg.evaluate(SEL_JS), lambda v: len(v['selected']) >= 3)
    assert set([a, b, c]) <= set(got['selected']), got
    # no rename opened by any of them
    for lid in (a, b, c):
        assert _field(pg, _screen(lid))['readOnly'], lid


def test_beach_drag_inside_the_open_name_selects_text(page):
    pg, ids = page
    b1 = ids['beaches'][0]
    sel = _beach(b1)
    attrs = lambda: pg.evaluate("""(s) => { const n = document.querySelector(s); const row = n.closest('.beach-row');
        return {row: row.draggable, name: n.draggable, readOnly: n.readOnly}; }""", sel)
    assert attrs() == {'row': True, 'name': True, 'readOnly': True}
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel)
    assert attrs() == {'row': False, 'name': False, 'readOnly': False}
    got = _drag_select(pg, sel, 'A LONG BEACH NAME')
    assert got['start'] != got['end'], got
    assert pg.evaluate("() => window.__dragstarts") == []
    pg.keyboard.press('Escape')
    settled(pg, attrs, lambda v: v['readOnly'])
    assert attrs() == {'row': True, 'name': True, 'readOnly': True}


def test_canvas_drag_inside_the_open_name_selects_text(page):
    pg, ids = page
    c1 = ids['canvases'][0]
    sel = _canvas(c1)
    attrs = lambda: pg.evaluate("""(s) => { const n = document.querySelector(s);
        const h = n.closest('.canvas-group-header');
        return {header: h.draggable, name: n.draggable, readOnly: n.readOnly}; }""", sel)
    assert attrs() == {'header': True, 'name': True, 'readOnly': True}
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel, cls=False)
    assert attrs() == {'header': False, 'name': False, 'readOnly': False}
    got = _drag_select(pg, sel, 'A LONG CANVAS NAME')
    assert got['start'] != got['end'], got
    assert pg.evaluate("() => window.__dragstarts") == []
    pg.keyboard.press('Escape')
    settled(pg, attrs, lambda v: v['readOnly'])
    assert attrs() == {'header': True, 'name': True, 'readOnly': True}


# ── the first drag after the double-click ─────────────────────────────────

LONG_NAME = 'A LONG NAME TO DRAG OVER'


def _name_sel(ids, kind):
    return {'screen': lambda: _screen(ids['a']), 'canvas': lambda: _canvas(ids['canvases'][0]),
            'group': lambda: _group(ids['groups'][0]), 'beach': lambda: _beach(ids['beaches'][0])}[kind]()


def _open_long_name(pg, sel):
    """A real double-click on a long name, with nothing done to the
    selection it leaves. The name is only on the field: Esc puts it back.
    A click first, so the double-click rebuilds no row (a read-only field
    that leaves with its focus commits what it holds)."""
    pg.locator(sel).click()
    pg.evaluate("""([s, t]) => {
        if (document.activeElement) document.activeElement.blur();
        document.querySelector(s).value = t;
    }""", [sel, LONG_NAME])
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel, cls=False)
    f = pg.evaluate("(s) => { const el = document.querySelector(s); return [el.selectionStart, el.selectionEnd]; }", sel)
    assert f == [0, len(LONG_NAME)], f'the double-click left {f} selected'


def _selection(pg, sel):
    return pg.evaluate("""(s) => { const el = document.querySelector(s);
        return {start: el.selectionStart, end: el.selectionEnd, value: el.value,
                focused: document.activeElement === el, readOnly: el.readOnly}; }""", sel)


def _mouse_drag(pg, sel, x0=0.1, x1=0.6):
    box = pg.locator(sel).bounding_box()
    y = box['y'] + box['height'] / 2
    pg.mouse.move(box['x'] + box['width'] * x0, y)
    pg.mouse.down()
    for step in range(1, 9):
        pg.mouse.move(box['x'] + box['width'] * (x0 + (x1 - x0) * step / 8), y)
    pg.mouse.up()
    pg.wait_for_timeout(100)


@pytest.fixture
def closes_the_edit(page):
    """An edit left open by a failed assert is committed by the next test's
    click, and that rename rebuilds the list under it: one failure on CI read
    as a second, unrelated one (the double-click left [0, 7], ALPHA-3's length).
    """
    yield
    pg, _ = page
    pg.evaluate("""() => { const el = document.activeElement;
        if (el && el.matches('input') && !el.readOnly) el.dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); }""")


def _end_edit_and_check(pg, sel):
    pg.keyboard.press('Escape')
    settled(pg, lambda: _field(pg, sel), lambda v: v['readOnly'])
    assert _field(pg, sel)['readOnly']
    assert pg.evaluate("(s) => document.querySelector(s).value", sel) != LONG_NAME


@pytest.mark.parametrize('kind', ['screen', 'canvas', 'group', 'beach'])
def test_the_first_drag_after_the_double_click_selects_text(page, closes_the_edit, kind):
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _name_sel(ids, kind)
    before = pg.evaluate(LAYERS_JS)
    _open_long_name(pg, sel)
    _mouse_drag(pg, sel)
    got = _selection(pg, sel)
    assert 0 < got['end'] - got['start'] < len(LONG_NAME), f'the first drag selected {got}'
    assert got['focused'] and not got['readOnly'], got
    assert got['value'] == LONG_NAME, got
    assert pg.evaluate("() => window.__dragstarts") == []
    # typing replaces just what the drag selected
    pg.keyboard.type('Z')
    typed = _selection(pg, sel)
    assert typed['value'] == LONG_NAME[:got['start']] + 'Z' + LONG_NAME[got['end']:], typed
    _end_edit_and_check(pg, sel)
    assert pg.evaluate(LAYERS_JS) == before, 'a drag in the open name moved or reordered something'


@pytest.mark.parametrize('kind', ['screen', 'canvas', 'group', 'beach'])
def test_a_drag_on_text_a_drag_selected_starts_a_new_selection(page, closes_the_edit, kind):
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _name_sel(ids, kind)
    _open_long_name(pg, sel)
    _mouse_drag(pg, sel, 0.1, 0.6)
    first = _selection(pg, sel)
    _mouse_drag(pg, sel, 0.3, 0.45)
    second = _selection(pg, sel)
    assert second['end'] - second['start'] > 0, second
    assert second['start'] > first['start'] and second['end'] < first['end'], (first, second)
    assert pg.evaluate("() => window.__dragstarts") == []
    _end_edit_and_check(pg, sel)


# What the name holds selected as the press comes down. Which of the two word
# shapes a double-click in an open name leaves depends on the system.
SHAPES = {'whole': (0, len(LONG_NAME)), 'word': (2, 6), 'word-and-space': (2, 7), 'caret': (0, 0)}


def _sweep_drags(pg, sel, start, end, first=3, last=33, step=0.5):
    """A real drag from every press point along the first letters, each one
    starting from the shape given. Returns the presses that selected nothing."""
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    missed = []
    x = first
    while x <= last:
        pg.evaluate("([s, a, b]) => document.querySelector(s).setSelectionRange(a, b)", [sel, start, end])
        px = box['x'] + x
        pg.mouse.move(px, y)
        pg.mouse.down()
        for hop in range(1, 5):
            pg.mouse.move(px + hop * 11, y)
        pg.mouse.up()
        got = pg.evaluate("(s) => { const el = document.querySelector(s); return [el.selectionStart, el.selectionEnd]; }", sel)
        if got[1] - got[0] < 2:
            missed.append((x, got))
        x += step
    return missed


@pytest.mark.parametrize('shape', list(SHAPES))
@pytest.mark.parametrize('kind', ['screen', 'canvas', 'group', 'beach'])
def test_a_drag_selects_text_from_any_press_point_and_any_selection(page, closes_the_edit, kind, shape):
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _name_sel(ids, kind)
    _open_long_name(pg, sel)
    start, end = SHAPES[shape]
    assert _sweep_drags(pg, sel, start, end) == []
    assert pg.evaluate("() => window.__dragstarts") == []
    _end_edit_and_check(pg, sel)


def test_a_drag_right_to_left_keeps_its_start_too(page, closes_the_edit):
    pg, ids = page
    sel = _screen(ids['a'])
    _open_long_name(pg, sel)
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    x = 40.0
    while x < 60:
        pg.evaluate("(s) => document.querySelector(s).select()", sel)
        pg.mouse.move(box['x'] + x, y)
        pg.mouse.down()
        for hop in range(1, 5):
            pg.mouse.move(box['x'] + x - hop * 8, y)
        pg.mouse.up()
        got = _selection(pg, sel)
        assert got['end'] - got['start'] >= 2, (x, got)
        x += 0.25
    _end_edit_and_check(pg, sel)


def test_a_drag_selects_text_on_a_scaled_screen(e2e_server, pw_browser, page):
    """A device pixel is half a CSS pixel here, so a real mouse can press off a
    whole CSS pixel, which is where the browser loses the drag's start."""
    _, ids = page
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100}, device_scale_factor=2)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    try:
        for path in ('save-file', 'open-file', 'select-directory'):
            pg.route(f'**/api/native-dialog/{path}', _cancelled)
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(800)
        sel = _beach(ids['beaches'][0])
        _open_long_name(pg, sel)
        assert _sweep_drags(pg, sel, 0, len(LONG_NAME)) == []
        pg.keyboard.press('Escape')
    finally:
        context.close()


@pytest.mark.parametrize('kind', ['screen', 'canvas', 'group', 'beach'])
def test_a_drag_let_go_past_the_end_of_the_name_keeps_the_edit(page, closes_the_edit, kind):
    """The release lands on the row, or on a button in it, and the browser
    clicks the row. That click ended a group's rename."""
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _name_sel(ids, kind)
    _open_long_name(pg, sel)
    held = pg.evaluate(HOLD_JS, sel)
    assert held
    selected = pg.evaluate("() => [...window.app.selectedLayerIds].sort()")
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    x = round(box['x'] + box['width'] / 2)
    pg.mouse.move(x, y)
    pg.mouse.down()
    for hop in range(1, 9):
        pg.mouse.move(x + hop * (box['width'] / 2 + 12) / 8, y)
    pg.mouse.up()
    pg.wait_for_timeout(150)
    assert pg.evaluate(HELD_JS, sel) == {'connected': True, 'same': True}, 'the list was rebuilt under the edit'
    got = _selection(pg, sel)
    assert got['end'] > got['start'] and got['focused'] and not got['readOnly'], got
    assert pg.evaluate("() => [...window.app.selectedLayerIds].sort()") == selected
    pg.keyboard.press('Escape')
    settled(pg, lambda: _field(pg, sel), lambda v: v['readOnly'])
    assert _field(pg, sel)['readOnly']
    assert pg.evaluate("() => window.__dragstarts") == []


def test_the_click_after_a_drag_let_go_on_the_row_still_works(page, closes_the_edit):
    pg, ids = page
    sel = _group(ids['groups'][0])
    _open_long_name(pg, sel)
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    x = round(box['x'] + box['width'] / 2)
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(x + box['width'] / 2 + 12, y, steps=6)
    pg.mouse.up()
    pg.keyboard.press('Escape')
    settled(pg, lambda: _field(pg, sel), lambda v: v['readOnly'])
    info = f'#layers-list .screen-group[data-group-id="{ids["groups"][0]}"] .screen-group-info'
    pg.locator(info).click()
    members = pg.evaluate("(g) => window.app.getGroupMembers(window.app.resolveGroup(g)).map(l => l.id).sort()",
                          ids['groups'][0])
    got = settled(pg, lambda: pg.evaluate("() => [...window.app.selectedLayerIds].sort()"), lambda v: v == members)
    assert got == members


def test_a_real_double_click_in_an_open_name_then_a_drag_on_that_word(page, closes_the_edit):
    """Whatever this system's double-click picked, the press on it starts a
    new selection and no text drag."""
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _screen(ids['a'])
    _open_long_name(pg, sel)
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    x = round(box['x'] + box['width'] * 0.3)
    pg.mouse.click(x, y, click_count=2)
    word = _selection(pg, sel)
    assert 0 < word['end'] - word['start'] < len(LONG_NAME), word
    pg.mouse.move(x, y)
    pg.mouse.down()
    for hop in range(1, 5):
        pg.mouse.move(x + hop * 10, y)
    pg.mouse.up()
    got = _selection(pg, sel)
    assert got['end'] - got['start'] >= 2 and got['end'] > word['end'], (word, got)
    assert pg.evaluate("() => window.__dragstarts") == []
    _end_edit_and_check(pg, sel)


def test_a_press_still_inside_the_double_click_starts_no_text_drag(page, closes_the_edit):
    """Pressing again at once makes it the third click of a row. That press is
    the browser's own, and what it selects is its business; it starts no text
    drag and the name stays open with text selected."""
    pg, ids = page
    pg.evaluate(DRAGSTARTS_JS)
    sel = _beach(ids['beaches'][0])
    _open_long_name(pg, sel)
    box = pg.locator(sel).bounding_box()
    y = round(box['y'] + box['height'] / 2)
    x = round(box['x'] + box['width'] / 2)
    pg.mouse.move(x, y)
    pg.mouse.down(click_count=3)
    for hop in range(1, 5):
        pg.mouse.move(x + hop * 6, y)
    pg.mouse.up(click_count=3)
    got = _selection(pg, sel)
    assert got['end'] > got['start'], got
    assert got['focused'] and not got['readOnly'], got
    assert pg.evaluate("() => window.__dragstarts") == []
    _end_edit_and_check(pg, sel)


def test_double_and_triple_clicks_and_shift_in_an_open_name_keep_their_meaning(page):
    pg, ids = page
    sel = _screen(ids['a'])
    _open_long_name(pg, sel)
    box = pg.locator(sel).bounding_box()
    x, y = box['x'] + box['width'] * 0.35, box['y'] + box['height'] / 2
    pg.mouse.click(x, y, click_count=2)
    word = _selection(pg, sel)
    assert 0 < word['end'] - word['start'] < len(LONG_NAME), word
    assert ' ' not in LONG_NAME[word['start']:word['end']].strip(), word
    pg.mouse.click(x, y, click_count=3)
    line = _selection(pg, sel)
    assert (line['start'], line['end']) == (0, len(LONG_NAME)), line
    # Shift extends what is there, so a press with it lets nothing go
    pg.mouse.click(box['x'] + box['width'] * 0.1, y)
    caret = _selection(pg, sel)
    assert caret['start'] == caret['end'], caret
    pg.keyboard.down('Shift')
    pg.mouse.click(box['x'] + box['width'] * 0.6, y)
    pg.keyboard.up('Shift')
    grown = _selection(pg, sel)
    assert grown['start'] == caret['start'] and grown['end'] > caret['end'], grown
    _end_edit_and_check(pg, sel)


def test_a_rename_after_the_first_drag_saves_and_undoes(page):
    pg, ids = page
    sel = _screen(ids['b'])
    name = pg.evaluate("(s) => document.querySelector(s).value", sel)
    pg.locator(sel).dblclick()
    _assert_editing(pg, sel)
    _mouse_drag(pg, sel, 0.02, 0.5)
    got = _selection(pg, sel)
    assert got['end'] > got['start'], got
    pg.keyboard.type('NEW')
    pg.keyboard.press('Enter')
    want = name[:got['start']] + 'NEW' + name[got['end']:]
    _server_name(pg, 'layers', ids['b'], want)
    pg.keyboard.press('Control+z')
    _server_name(pg, 'layers', ids['b'], name)


def test_a_group_name_being_edited_has_nothing_draggable_above_it(page, closes_the_edit):
    """Since 1.7.0 a group's row drags the group (tests/test_group_drag.py),
    and the read-only name with it. While the name is edited neither drags,
    so WebKit has no drag to start from it, and both drag again after."""
    pg, ids = page
    chain = """(s) => { const out = [];
        for (let el = document.querySelector(s); el; el = el.parentElement) if (el.draggable) out.push(el.className.split(' ')[0]);
        return out; }"""
    for gid in ids['groups']:
        sel = _group(gid)
        assert pg.evaluate(chain, sel) == ['screen-group-name-input', 'screen-group-row'], gid
        pg.locator(sel).dblclick()
        _assert_editing(pg, sel)
        assert pg.evaluate(chain, sel) == [], gid
        pg.keyboard.press('Escape')
        settled(pg, lambda: _field(pg, sel), lambda v: v['readOnly'])
        assert pg.evaluate(chain, sel) == ['screen-group-name-input', 'screen-group-row'], gid


def test_no_page_errors(page):
    pg, ids = page
    assert ids['errors'] == [], ids['errors']
