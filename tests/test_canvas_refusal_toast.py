"""A move a processor's canvas can't take is always said, in a red toast.

The owner's report (2026-11-04, from his own log): a screen dragged on its
canvas snapped back every time with no message he could see. The canvas
guard (app-port-assignment _canvasGuardEdit) had refused it, but said so
only on the status line beside the hardware dock, and his dock was folded
away. And the reason was hard to guess: one SX40 drove a screen on each of
two canvases, and a processor's span is measured across canvases (one
input takes them all).

The rulings, the same day:
  * "Keep it, explain it." The span stays measured across canvases. The
    refusal names the screens that make up the span, and each one's canvas
    where they sit on more than one.
  * "Yes, red error toast." Every refused edit of this kind shows the red
    error toast a locked screen gets, with the dock open or folded.

Built from a scratch project: two screens, one SX40 driving both.

Run locally (each session takes its own free port):
    python -m pytest tests/test_canvas_refusal_toast.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402

SX_LIMIT = ("An SX40's canvas is 4096 × 2160, or up to 4094 wide and 4095 "
            "tall within 9,000,000 px.")
TOAST_RED = 'rgb(168, 50, 75)'   # _toast's error colour, #a8324b

# The dialog endpoints that would open a real window on the desktop: each
# answers "cancelled" here.
DIALOGS = ('save-file', 'open-file', 'select-directory')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    for name in DIALOGS:
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"ok": false, "cancelled": true, "unavailable": false}'))
    # The hardware dock starts FOLDED, as the owner's was.
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
        "localStorage.setItem('ledRasterSidebarCollapsed_dock','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true"
                         " && window.canvasRenderer"
                         " && window.canvasRenderer.zoom > 0", timeout=20000)
    pg.wait_for_timeout(800)
    yield pg, errors
    context.close()


# Two screens of 9 x 7 cabinets at 192 px (1728 x 1344 each): Wing L at x 0
# and Wing R at x 2000, one SX40 driving both - 3728 x 1344, inside its
# 4096 x 2160. `split` puts Wing L on a second canvas, far below the first
# in the workspace so the two never overlap on screen.
SEED_JS = """async (split) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(x => x.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    const base = proj.canvases[0];
    proj.canvases = [
        Object.assign({}, base, {id: 'c1', name: 'Upper', workspace_x: 0, workspace_y: 0}),
        Object.assign({}, base, {id: 'c2', name: 'Lower', workspace_x: 0, workspace_y: 4000}),
    ];
    proj.active_canvas_id = 'c1';
    await j('PUT', '/api/project', proj);
    const add = async (name, x, canvas_id) => {
        const l = await j('POST', '/api/layer/add', {name, columns: 9, rows: 7,
            cabinet_width: 192, cabinet_height: 192, offset_x: x, offset_y: 0,
            canvas_id});
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'brompton',
            bitDepth: 8, frameRate: 60, flowPattern: 'tl-v'});
        return l;
    };
    const left = await add('Wing L', 0, split ? 'c2' : 'c1');
    const right = await add('Wing R', 2000, 'c1');
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('canvas_toast_seed');
    await app.refreshProcessors();
    await app._processorRequest('/api/processors', 'POST',
                                {deviceId: 'brompton-sx40', name: 'WINGS'}, 'Add Processor');
    const sx = app._processorsResolved[0];
    const card = sx.slots[0].card.id;
    for (const l of [left, right]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(l.id), cardId: card}, null, 'Fill Ports In Order');
    }
    const cur = app.project.layers.find(l => l.id === right.id);
    app.currentLayer = cur;
    app.selectedLayerIds = new Set([cur.id]);
    app.lastSelectedLayerId = cur.id;
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    r.viewMode = 'pixel-map';
    r.zoom = 0.2; r.panX = 40; r.panY = 40;
    app.renderLayers();
    app.renderHardwareDock();
    app.updateUI();
    app.loadLayerToInputs();
    app.resetHistory('Canvas Toast Seed');
    const host = document.getElementById('app-toast-host');
    if (host) host.innerHTML = '';
    document.getElementById('status-message').textContent = 'Ready';
    r.render();
    return {sx: sx.id, left: left.id, right: right.id,
            pins: app.project.port_assignments.pins.length};
}"""

STATE_JS = """(id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    const toasts = [...document.querySelectorAll('#app-toast-host > div')]
        .map(t => ({text: t.textContent, bg: getComputedStyle(t).backgroundColor}));
    const span = ((app._assignment || {}).canvas || {});
    return {offset_x: l.offset_x, panel_x: l.panels[0].x, index: app.historyIndex,
            toasts, docked: document.getElementById('hardware-dock')
                .classList.contains('collapsed'),
            spans: Object.values(span).map(s => [s.width, s.height, s.fits])};
}"""


def _seed(pg, split):
    ids = pg.evaluate(SEED_JS, split)
    assert ids['pins'] > 0, ids
    settled(pg, lambda: pg.evaluate(STATE_JS, ids['right'])['spans'],
            lambda s: s == [[3728, 1344, True]])
    return ids


def _to_client(pg, layer_id, wx, wy):
    """A point on a screen, in raster pixels on its canvas, in the window."""
    pt = pg.evaluate("""([id, wx, wy]) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        const c = (app.project.canvases || []).find(x => x.id === l.canvas_id) || {};
        const rect = r.canvas.getBoundingClientRect();
        const x = (c.workspace_x || 0) + wx, y = (c.workspace_y || 0) + wy;
        return {x: rect.left + x * r.zoom + r.panX, y: rect.top + y * r.zoom + r.panY};
    }""", [layer_id, wx, wy])
    return pt['x'], pt['y']


def _shift_drag(pg, layer_id, start, end, steps=12):
    sx, sy = _to_client(pg, layer_id, *start)
    ex, ey = _to_client(pg, layer_id, *end)
    pg.keyboard.down('Shift')
    try:
        pg.mouse.move(sx, sy)
        pg.mouse.down()
        pg.mouse.move(ex, ey, steps=steps)
        pg.mouse.up()
    finally:
        pg.keyboard.up('Shift')


def _refused_back(pg, ids, before):
    """The screen is back where it was, no undo step, and one red toast:
    returns that toast's text."""
    out = settled(pg, lambda: pg.evaluate(STATE_JS, ids['right']),
                  lambda o: len(o['toasts']) == 1)
    assert out['offset_x'] == 2000 and out['panel_x'] == before['panel_x'], out
    assert out['index'] == before['index'], out
    assert out['docked'] is True, 'the hardware dock was meant to be folded'
    assert len(out['toasts']) == 1, out
    toast = out['toasts'][0]
    assert toast['bg'] == TOAST_RED, toast
    assert pg.locator('#app-toast-host > div').first.is_visible()
    pg.wait_for_timeout(400)
    server = pg.evaluate("""(id) => fetch('/api/project').then(r => r.json())
        .then(p => p.layers.find(l => l.id === id).offset_x)""", ids['right'])
    assert server == 2000, server
    return toast['text']


def test_a_drag_across_two_canvases_snaps_back_with_a_red_toast(page):
    """Wing L on Lower, Wing R on Upper, one SX40: Wing R dragged 1000 px
    right would take the span past 4096. It snaps back, and with the dock
    folded the red toast names both screens and both canvases."""
    pg, errors = page
    ids = _seed(pg, split=True)
    before = pg.evaluate(STATE_JS, ids['right'])
    assert before['docked'] is True, before
    _shift_drag(pg, ids['right'], (2800, 600), (3800, 600))
    text = _refused_back(pg, ids, before)
    assert text.startswith("SX40 WINGS can't take this: Wing L (Lower) and "
                           "Wing R (Upper) would span "), text
    assert text.endswith(" × 1344 px. " + SX_LIMIT), text
    # the status line says it too
    assert pg.evaluate("() => document.getElementById('status-message')"
                       ".textContent") == text
    assert errors == []


def test_on_one_canvas_the_toast_names_the_screens_only(page):
    pg, errors = page
    ids = _seed(pg, split=False)
    before = pg.evaluate(STATE_JS, ids['right'])
    _shift_drag(pg, ids['right'], (2800, 600), (3800, 600))
    text = _refused_back(pg, ids, before)
    assert text.startswith("SX40 WINGS can't take this: Wing L and Wing R "
                           "would span "), text
    assert '(Upper)' not in text and '(Lower)' not in text, text
    assert text.endswith(" × 1344 px. " + SX_LIMIT), text
    assert errors == []


def test_an_offset_typed_in_screen_info_gets_the_toast(page):
    """Screen Info's X offset to 3000: 4728 wide, refused - the field reads
    2000 again and the red toast says why, naming both canvases."""
    pg, errors = page
    ids = _seed(pg, split=True)
    before = pg.evaluate(STATE_JS, ids['right'])
    pg.evaluate("""() => {
        const el = document.getElementById('offset-x');
        el.value = '3000';
        el.dispatchEvent(new Event('change'));
    }""")
    text = _refused_back(pg, ids, before)
    assert text == ("SX40 WINGS can't take this: Wing L (Lower) and Wing R "
                    "(Upper) would span 4728 × 1344 px. " + SX_LIMIT), text
    assert pg.evaluate("() => document.getElementById('offset-x').value") == '2000'
    assert errors == []


def test_a_refused_pin_gets_the_toast(page):
    """The server's refusal reaches the user the same way: Wing R's ports
    released, Wing R moved out to 3000 (it rides no SX40 port, so nothing
    refuses the move), then filled back onto the SX40 - refused by the
    server, said in the red toast."""
    pg, errors = page
    ids = _seed(pg, split=True)
    out = pg.evaluate("""async ([id, sx]) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
            {layerId: String(id)}, null, 'Release Ports');
        const l = app.project.layers.find(x => x.id === id);
        l.offset_x = 3000;
        app.updateLayers([l], false);
        await app._layerSavesSettled();
        const host = document.getElementById('app-toast-host');
        if (host) host.innerHTML = '';
        const card = app._processorsResolved.find(p => p.id === sx).slots[0].card.id;
        const pins = app.project.port_assignments.pins.length;
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(id), cardId: card}, null, 'Fill Ports In Order');
        return {pins, after: app.project.port_assignments.pins.length,
                offset: app.project.layers.find(x => x.id === id).offset_x};
    }""", [ids['right'], ids['sx']])
    assert out['offset'] == 3000 and out['after'] == out['pins'], out
    toasts = settled(pg, lambda: pg.evaluate(STATE_JS, ids['right'])['toasts'],
                     lambda t: len(t) == 1)
    assert len(toasts) == 1 and toasts[0]['bg'] == TOAST_RED, toasts
    assert toasts[0]['text'] == (
        "SX40 WINGS can't take this: Wing L (Lower) and Wing R (Upper) would "
        "span 4728 × 1344 px. " + SX_LIMIT), toasts
    assert errors == []
