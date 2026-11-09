"""The move cursor on a canvas's dashed outline (canvas-input.js).

A press on a canvas's outline edge drags the canvas only on the two tabs
that lay canvases out: Pixel Map and Show Look. The hover cursor must say
the same thing. On Cabinet ID, Data, Power and Header/Footer the edge does
not move (their canvas position comes from the other two), so it must not
show the move cursor there; the IDM Locator says mark or clear; the 3D tab
has no 2D canvas edge at all.

What this file pins, with real mouse events on every tab:

* Pixel Map and Show Look: the edge shows 'move', and a drag from it moves
  the canvas.
* Cabinet ID, Data, Power, Header/Footer, IDM: the edge never shows
  'move', and a drag from it leaves the canvas where it stands.
* 3D: hovering empty space never shows the move cursor.

Run locally:
    python -m pytest tests/test_canvas_edge_cursor.py -v -p no:cacheprovider
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_stage3d import _context, open_3d, open_tab, reset  # noqa: E402

ONE = [{'name': 'Edge', 'columns': 2, 'rows': 2, 'offset_x': 200, 'offset_y': 200}]

DRAG_TABS = ['pixel-map', 'show-look']
STILL_TABS = ['cabinet-id', 'data-flow', 'power', 'rigging', 'idm']


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = _context(pw_browser)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# The client point of the first canvas's left edge, low enough to miss the
# screen, and where that canvas stands in the active tab's workspace.
EDGE_JS = """() => {
    const r = window.canvasRenderer, c = window.app.project.canvases[0];
    const ws = r._canvasWorkspace(c);
    const show = r.isShowLookView();
    const h = (show && c.show_raster_height) || c.raster_height;
    const rect = r.canvas.getBoundingClientRect();
    const wy = ws.wy + h * 0.85;
    return {x: rect.left + r.panX + ws.wx * r.zoom, y: rect.top + r.panY + wy * r.zoom,
            wx: ws.wx, wy: ws.wy};
}"""


def edge(page):
    return page.evaluate(EDGE_JS)


def cursor(page):
    return page.evaluate("() => window.canvasRenderer.canvas.style.cursor")


def hover_edge(page):
    e = edge(page)
    page.mouse.move(e['x'] + 40, e['y'])
    page.mouse.move(e['x'], e['y'], steps=4)
    page.wait_for_timeout(50)
    return e


def drag_edge(page, by=60):
    e = hover_edge(page)
    page.mouse.down()
    page.mouse.move(e['x'] + by / 2, e['y'], steps=4)
    page.mouse.move(e['x'] + by, e['y'], steps=4)
    page.mouse.up()
    page.wait_for_timeout(400)
    return e


def fresh(page, tab):
    reset(page, ONE)
    open_tab(page, tab)
    page.evaluate("() => { const b = document.getElementById('btn-fit'); if (b) b.click(); }")
    page.wait_for_timeout(250)


@pytest.mark.parametrize('tab', DRAG_TABS)
def test_the_edge_says_move_where_a_drag_moves_the_canvas(page, tab):
    fresh(page, tab)
    hover_edge(page)
    assert cursor(page) == 'move', tab
    before = edge(page)
    drag_edge(page)
    after = edge(page)
    assert after['wx'] != before['wx'], f'{tab}: the edge drag did not move the canvas'
    assert page.errors == []


@pytest.mark.parametrize('tab', STILL_TABS)
def test_the_edge_never_says_move_where_it_does_not_move(page, tab):
    fresh(page, tab)
    hover_edge(page)
    assert cursor(page) != 'move', f'{tab}: the edge shows a move cursor it cannot honor'
    before = edge(page)
    drag_edge(page)
    after = edge(page)
    assert (after['wx'], after['wy']) == (before['wx'], before['wy']), f'{tab}: the edge drag moved the canvas'
    page.mouse.move(before['x'] + 3, before['y'] + 1)
    assert cursor(page) != 'move', tab
    assert page.errors == []


def test_the_3d_view_shows_no_move_cursor_on_empty_space(page):
    reset(page, ONE)
    open_3d(page, 1)
    page.evaluate("window.app.setSelectedLayersByIds([], null)")
    rect = page.evaluate("document.getElementById('s3d-canvas').getBoundingClientRect().toJSON()")
    for x, y in ((rect['left'] + 4, rect['top'] + 60), (rect['left'] + 20, rect['bottom'] - 40)):
        page.mouse.move(x, y)
        page.wait_for_timeout(50)
        got = page.evaluate("getComputedStyle(document.getElementById('s3d-canvas')).cursor")
        assert got != 'move', (x, y, got)
    open_tab(page, 'pixel-map')
    assert page.errors == []
