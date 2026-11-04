"""A screen made with + Add > Screen… lands on the first free spot (1.6.0).

It landed at 0,0, on top of the screen already there. The owner's ruling,
2026-11-04: a new screen goes to the FIRST FREE SPOT on the active canvas,
the first gap big enough for it, scanning left to right, then top to
bottom. An empty canvas still gets 0,0, and the new screen never overlaps
a screen on that canvas.

The walls are synthetic, on a 1920 x 1080 canvas, every cabinet 100 x 100
px. The new screen is the Add Screen picker's first row (the last screen's
panel) at the Preferences' columns and rows (8 x 5, so 800 x 500 px).

Run locally (each session takes its own free port):
    python -m pytest tests/test_add_screen_first_free_spot.py -v --browser chromium
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    body = json.dumps({'ok': False, 'cancelled': True})
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}',
                      lambda route: route.fulfill(status=200, content_type='application/json', body=body))
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    yield pg, errors
    context.close()


# The show: a new project with `screens` ([name, columns, rows, x, y]) on
# its canvas, every cabinet 100 x 100 px, and with `second` a second canvas
# (empty, and the active one). Built on the server, then the page reloads.
SHOW_JS = """async ({ screens, second }) => {
    const send = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) });
    await window.app._layerSavesSettled();
    await send('POST', '/api/project/new');
    const p = await (await fetch('/api/project')).json();
    for (const l of p.layers) await send('DELETE', `/api/layer/${l.id}`);
    for (const [name, columns, rows, x, y] of screens) {
        await send('POST', '/api/layer/add', { name, columns, rows,
            cabinet_width: 100, cabinet_height: 100, offset_x: x, offset_y: y });
    }
    if (second) await send('POST', '/api/canvas', {});
}"""


def _show(pg, screens, second=False):
    pg.evaluate(SHOW_JS, {'screens': screens, 'second': second})
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    got = pg.evaluate("""() => window.app.project.layers.filter(l => (l.type || 'screen') === 'screen')
        .map(l => [l.name, l.offset_x, l.offset_y])""")
    assert got == [[s[0], s[3], s[4]] for s in screens], got
    prefs = pg.evaluate("() => { const p = window.app.getPreferences(); return [p.columns, p.rows]; }")
    assert prefs == [8, 5], prefs
    canvas = pg.evaluate("""() => { const p = window.app.project;
        const c = p.canvases.find(x => x.id === p.active_canvas_id);
        return [c.raster_width, c.raster_height]; }""")
    assert canvas == [1920, 1080], canvas


def _add_screen(pg):
    """+ Add on the active canvas, Screen…, then Add Screen on the first
    row. Returns the new screen: [name, x, y, width, height, canvas]."""
    before = pg.evaluate("() => window.app.project.layers.length")
    pg.locator('.canvas-group.active .canvas-add-btn').click()
    pg.locator('.canvas-add-popup button[data-action="screen"]').click()
    pg.wait_for_selector('#preset-picker-modal', state='visible', timeout=5000)
    pg.wait_for_function("() => { const b = document.getElementById('preset-picker-add');"
                         " return b && !b.disabled; }", timeout=10000)
    pg.locator('#preset-picker-add').click()
    pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=before, timeout=10000)
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")
    return pg.evaluate("""() => { const a = window.app, r = window.canvasRenderer;
        const l = a.currentLayer, b = r.getLayerFootprintBounds(l);
        return [l.name, l.offset_x, l.offset_y, b.width, b.height, l.canvas_id]; }""")


def _overlaps(pg):
    """Pairs of screens on one canvas whose drawn boxes overlap."""
    return pg.evaluate("""() => { const a = window.app, r = window.canvasRenderer;
        const s = a.project.layers.filter(l => (l.type || 'screen') === 'screen');
        const out = [];
        s.forEach((l, i) => s.slice(i + 1).forEach(o => {
            if (l.canvas_id !== o.canvas_id) return;
            const p = r.getLayerFootprintBounds(l), q = r.getLayerFootprintBounds(o);
            if (p.x < q.x + q.width && p.x + p.width > q.x && p.y < q.y + q.height && p.y + p.height > q.y)
                out.push([l.name, o.name]);
        }));
        return out; }""")


def _server_offset(pg, name):
    return pg.evaluate("""async (n) => { const l = (await (await fetch('/api/project')).json())
        .layers.find(x => x.name === n); return [l.offset_x, l.offset_y, l.showOffsetX, l.showOffsetY]; }""", name)


def test_a_new_screen_lands_beside_the_screen_there(page):
    pg, errors = page
    _show(pg, [['Left', 4, 2, 0, 0]])
    name, x, y, w, h, _ = _add_screen(pg)
    assert [w, h] == [800, 500]
    assert [x, y] == [400, 0]
    assert _server_offset(pg, name) == [400, 0, 400, 0]
    assert _overlaps(pg) == []
    assert errors == []


def test_a_gap_too_narrow_is_passed_over_for_the_next_row(page):
    """A 600 px gap between two screens cannot take an 800 px screen, and
    nothing fits to the right of them, so it starts the next row, under
    the first screen."""
    pg, errors = page
    _show(pg, [['Left', 4, 2, 0, 0], ['Right', 4, 2, 1000, 0]])
    name, x, y, w, h, _ = _add_screen(pg)
    assert [x, y] == [0, 200]
    assert _server_offset(pg, name) == [0, 200, 0, 200]
    assert _overlaps(pg) == []
    # and the next one goes into the first gap that takes it
    name2, x2, y2, _, _, _ = _add_screen(pg)
    assert [x2, y2] == [800, 200]
    assert _overlaps(pg) == []
    assert errors == []


def test_a_gap_wide_enough_is_taken(page):
    pg, errors = page
    _show(pg, [['Left', 4, 2, 0, 0], ['Right', 4, 2, 1300, 0]])
    _, x, y, _, _, _ = _add_screen(pg)
    assert [x, y] == [400, 0]
    assert _overlaps(pg) == []
    assert errors == []


def test_an_empty_canvas_still_starts_at_the_corner(page):
    """The active canvas has no screen (the other one has): 0,0."""
    pg, errors = page
    _show(pg, [['Left', 4, 2, 0, 0]], second=True)
    active = pg.evaluate("() => window.app.project.active_canvas_id")
    _, x, y, _, _, canvas = _add_screen(pg)
    assert canvas == active
    assert [x, y] == [0, 0]
    assert _overlaps(pg) == []
    assert errors == []


def test_with_no_room_left_it_goes_under_every_screen(page):
    """A canvas with no gap the new screen fits: it starts a row under the
    lowest screen, at the left edge, and still overlaps nothing."""
    pg, errors = page
    _show(pg, [['Top', 19, 6, 0, 0], ['Low', 4, 4, 0, 600]])
    _, x, y, _, _, _ = _add_screen(pg)
    assert [x, y] == [0, 1000]
    assert _overlaps(pg) == []
    assert errors == []
