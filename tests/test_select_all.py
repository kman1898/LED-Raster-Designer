"""Cmd/Ctrl+A is the app's Select All, never the browser's text select-all.

The report (Windows/Firefox, 2026-09-16): Ctrl+A to "select all tiles"
turned every label in the app blue - the browser's native select-all -
and the next click-and-drag on the canvas dragged that text selection (a
ghost image of the whole GUI under a no-drop cursor) instead of
marquee-selecting screens.

Two fixes, both guarded here:

(1) The chord is a real shortcut (app-menubar's handleMenuShortcut ->
    app-selection's selectAllInView). Out of a field it is
    preventDefault'd and selects every visible layer on the active canvas
    - or, on Pixel Map with a cabinet selection already open, every
    cabinet of that screen (app-pixel-select's selectAllPixelMapPanels).
    In a text field it does nothing, so the browser's select-all keeps
    selecting the field's text.

(2) #app is user-select: none (style.css), with fields, textareas, the
    Notes area and contenteditable put back to text. So even a native
    select-all (document.execCommand) finds no chrome text to take, and a
    drag on empty canvas is always a marquee.

Run: python3 -m pytest tests/test_select_all.py -q --browser chromium
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it: the
    reset below empties the layer list and adds two screens of its own."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 850})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


# Two 2x2 screens of 128px cabinets (256x256 world units each), far enough
# apart that a marquee has empty space around both.
LAYER_OFFSETS = [(0, 0), (600, 0)]

RESET_JS = """async (offsets) => {
    const app = window.app;
    const r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    // One canvas: a second one carries its own workspace offset, which
    // would shift every world coordinate the tests below compute.
    for (const c of (project.canvases || []).slice(1)) {
        await fetch('/api/canvas/' + c.id, { method: 'DELETE' });
    }
    project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (let i = 0; i < offsets.length; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'SelAll' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                offset_x: offsets[i][0], offset_y: offsets[i][1],
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('select_all_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, offsets.length);
    app.currentLayer = screens[0];
    app.selectedLayerIds = new Set([screens[0].id]);
    app.lastSelectedLayerId = screens[0].id;
    app.selectionAnchorLayerId = screens[0].id;
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    if (typeof app.updatePixelMapBulkActionUI === 'function') app.updatePixelMapBulkActionUI();
    r.viewMode = 'pixel-map';
    r.zoom = 0.5; r.panX = 100; r.panY = 100;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    r.render();
    // Firefox keeps a blurred field's selection and reports it through
    // window.getSelection(); collapse the one field a test types in.
    const pn = document.getElementById('project-name');
    if (pn && pn.setSelectionRange) pn.setSelectionRange(0, 0);
    if (document.activeElement) document.activeElement.blur();
    window.getSelection().removeAllRanges();
    return screens.map(l => l.id);
}"""


def reset_project(page):
    ids = page.evaluate(RESET_JS, LAYER_OFFSETS)
    page.wait_for_timeout(400)
    assert len(ids) == len(LAYER_OFFSETS), ids
    return ids


def _mod(page):
    """The modifier the dispatcher honours - the client platform through
    app._isMacPlatform(), the same read the printed labels use."""
    return 'Meta' if page.evaluate('window.app._isMacPlatform()') else 'Control'


def selected_ids(page):
    return sorted(page.evaluate('[...window.app.selectedLayerIds]'))


def page_text_selection(page):
    return page.evaluate('window.getSelection().toString()')


def active_rows(page):
    return page.locator('#layers-list .layer-item.active').count()


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def _save_shot(page, name):
    """A picture for the eyes, when a run asks for one (LRD_SHOT_DIR)."""
    out = os.environ.get('LRD_SHOT_DIR')
    if not out:
        return
    os.makedirs(out, exist_ok=True)
    page.screenshot(path=os.path.join(out, name))


# ── (1) the chord ─────────────────────────────────────────────────────────

def test_ctrl_a_on_the_body_selects_both_screens_and_no_text(page):
    ids = reset_project(page)
    assert selected_ids(page) == [ids[0]]
    page.keyboard.press(f'{_mod(page)}+KeyA')
    page.wait_for_timeout(200)
    assert selected_ids(page) == sorted(ids), 'both screens should be selected'
    assert page_text_selection(page) == '', 'the browser select-all ran'
    # The Screens panel rows follow the multi-select set.
    assert active_rows(page) == 2
    _save_shot(page, 'select-all-both-screens.png')


def test_ctrl_a_stays_on_the_active_canvas(page):
    """A screen on another canvas is not "all": the chord selects what is
    on the canvas the person is working in."""
    ids = reset_project(page)
    other = page.evaluate("""async (layerId) => {
        const app = window.app;
        const made = await (await fetch('/api/canvas', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: 'Elsewhere' }),
        })).json();
        const canvases = (made && made.canvases) || (made.project && made.project.canvases) || [];
        const created = canvases[canvases.length - 1];
        if (!created) return null;
        await fetch(`/api/layer/${layerId}/canvas`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ canvas_id: created.id, mode: 'move' }),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('select_all_test_canvas');
        const first = app.project.layers.find(l => l.id !== layerId);
        app.project.active_canvas_id = first.canvas_id;
        app.currentLayer = first;
        app.selectedLayerIds = new Set([first.id]);
        app.renderLayers();
        window.canvasRenderer.render();
        return { moved: layerId, movedTo: created.id, active: first.canvas_id };
    }""", ids[1])
    if not other or other['movedTo'] == other['active']:
        pytest.skip('could not put a screen on a second canvas here')
    try:
        page.keyboard.press(f'{_mod(page)}+KeyA')
        page.wait_for_timeout(200)
        assert selected_ids(page) == [ids[0]], 'a screen on another canvas was selected'
        assert page_text_selection(page) == ''
    finally:
        # The reset trims canvases too, but leave nothing for it to find.
        page.evaluate("(cid) => fetch('/api/canvas/' + cid, { method: 'DELETE' })",
                      other['movedTo'])
        page.wait_for_timeout(200)


def test_ctrl_a_in_a_text_input_selects_its_text_not_screens(page):
    ids = reset_project(page)
    name = page.locator('#project-name')
    value = name.input_value()
    assert value, 'the project-name field should carry text to select'
    name.focus()
    page.evaluate("document.getElementById('project-name').setSelectionRange(0, 0)")
    page.keyboard.press(f'{_mod(page)}+KeyA')
    page.wait_for_timeout(200)
    sel = page.evaluate("""() => {
        const el = document.getElementById('project-name');
        return [el.selectionStart, el.selectionEnd];
    }""")
    assert sel == [0, len(value)], f'the field text was not selected: {sel}'
    assert selected_ids(page) == [ids[0]], 'screens were selected out of a text field'
    assert name.input_value() == value
    page.evaluate("""() => {
        const el = document.getElementById('project-name');
        el.setSelectionRange(0, 0);
        el.blur();
    }""")


def test_ctrl_a_with_a_cabinet_selection_selects_every_cabinet(page):
    ids = reset_project(page)
    count = page.evaluate("""() => {
        const app = window.app;
        app.togglePixelMapPanelSelection(app.currentLayer.panels[0]);
        return [app.pixelMapSelection.size, app.currentLayer.panels.length];
    }""")
    assert count == [1, 4], count
    page.keyboard.press(f'{_mod(page)}+KeyA')
    page.wait_for_timeout(200)
    assert page.evaluate('window.app.pixelMapSelection.size') == 4
    assert page.evaluate('window.app.getPixelMapSelectedPanels().length') == 4
    # The badge follows, and the screen selection is untouched.
    assert page.locator('#pixel-map-bulk-actions').is_visible()
    assert page.locator('#pixel-map-bulk-count').inner_text() == '4'
    assert selected_ids(page) == [ids[0]]
    assert page_text_selection(page) == ''
    _save_shot(page, 'select-all-cabinets.png')
    page.evaluate('window.app.clearPixelMapSelection()')


def test_ctrl_a_on_another_tab_selects_the_screens(page):
    ids = reset_project(page)
    page.evaluate("window.canvasRenderer.setViewMode('data-flow'); window.canvasRenderer.render();")
    page.wait_for_timeout(150)
    page.keyboard.press(f'{_mod(page)}+KeyA')
    page.wait_for_timeout(200)
    assert selected_ids(page) == sorted(ids)
    assert page_text_selection(page) == ''
    page.evaluate("window.canvasRenderer.setViewMode('pixel-map'); window.canvasRenderer.render();")


# ── (2) the chrome is never a text selection ─────────────────────────────

def test_native_select_all_finds_no_chrome_text(page):
    """Even the browser's own select-all (execCommand, no keydown to
    prevent) takes nothing from the app shell."""
    reset_project(page)
    text = page.evaluate("""() => {
        document.execCommand('selectAll');
        const s = window.getSelection().toString();
        window.getSelection().removeAllRanges();
        return s;
    }""")
    assert text.strip() == '', f'chrome text became a selection: {text[:200]!r}'
    rule = page.evaluate("""() => ({
        app: getComputedStyle(document.getElementById('app')).userSelect,
        menu: getComputedStyle(document.getElementById('menu-bar')).userSelect,
        canvas: getComputedStyle(document.getElementById('canvas-wrapper')).userSelect,
        rightSidebar: getComputedStyle(document.getElementById('right-sidebar')).userSelect,
        projectName: getComputedStyle(document.getElementById('project-name')).userSelect,
        notes: getComputedStyle(document.getElementById('project-notes')).userSelect,
    })""")
    # Chromium reports the inherited value ('none') on descendants; Firefox
    # reports 'auto', which resolves to the ancestor's 'none' - either way
    # the chrome must not opt back in.
    assert rule['app'] == 'none', rule
    for key in ('menu', 'canvas', 'rightSidebar'):
        assert rule[key] in ('none', 'auto'), rule
    for key in ('projectName', 'notes'):
        assert rule[key] == 'text', rule


def test_drag_on_empty_canvas_marquee_selects_after_ctrl_a(page):
    """The drag the report made after Ctrl+A: it must marquee-select the
    screens it sweeps, never drag a text selection."""
    ids = reset_project(page)
    page.keyboard.press(f'{_mod(page)}+KeyA')
    page.wait_for_timeout(150)
    # Click empty space to drop the selection, then sweep both screens.
    ex, ey = world_to_client(page, -120, 700)
    page.mouse.click(ex, ey)
    page.wait_for_timeout(150)
    x1, y1 = world_to_client(page, -80, -80)
    x2, y2 = world_to_client(page, 940, 340)
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=4)
    page.mouse.move(x2, y2, steps=4)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert selected_ids(page) == sorted(ids), 'the drag did not marquee-select'
    assert page_text_selection(page) == ''
