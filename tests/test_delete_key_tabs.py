"""Delete and Backspace on every tab, and the canvas right-click Delete Screen.

Matt, 2026-11-08: Pixel Map is the only tab where the key deletes a screen,
so a stray key never costs one. Header/Footer takes off bars instead
(test_header_footer_custom.py), the IDM Locator clears its mark
(test_idm_interaction.py), and Cabinet ID, Show Look, Data, Power and 3D do
nothing to screens. The canvas right-click Delete Screen is on Pixel Map
only; the Screens list's own right-click Delete Screen is on every tab.

Run locally:
    python -m pytest tests/test_delete_key_tabs.py
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


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
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    await j('PUT', '/api/project', proj);
    const base = {cabinet_width: 128, cabinet_height: 128, columns: 4, rows: 3};
    await j('POST', '/api/layer/add', {...base, name: 'A', offset_x: 100, offset_y: 100});
    await j('POST', '/api/layer/add', {...base, name: 'B', offset_x: 900, offset_y: 100});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('delete_tabs_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Delete Tabs Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""

QUIET_TABS = ['cabinet-id', 'show-look', 'data-flow', 'power', 'rigging', '3d', 'idm']


@pytest.fixture()
def pg(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)
    page.ids = page.evaluate(SEED_JS)
    page.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")
    page.wait_for_timeout(300)
    yield page
    ctx.close()
    assert not errors, errors


def tab(p, mode):
    p.locator(f'.view-tab[data-mode="{mode}"]').click()
    p.wait_for_timeout(400)


def select(p, name):
    p.evaluate("(id) => { window.app.setSelectedLayersByIds([id], id); "
               "document.activeElement && document.activeElement.blur && document.activeElement.blur(); }",
               p.ids[name])
    p.wait_for_timeout(150)


def names(p):
    return sorted(p.evaluate("() => window.app.project.layers.map(l => l.name)"))


def canvas_menu_delete(p):
    """Right-click the middle of the view: whether the menu that opens
    offers Delete Screen (None when no menu opens there)."""
    box = p.locator('#canvas-container').bounding_box()
    p.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, button='right')
    p.wait_for_timeout(250)
    shown = p.evaluate("""() => { const m = document.getElementById('context-menu');
        if (!m || getComputedStyle(m).display === 'none') return null;
        const d = m.querySelector('[data-action="delete"]');
        return !!d && getComputedStyle(d).display !== 'none' ? d.textContent : false; }""")
    p.evaluate("() => window.app.hideContextMenu()")
    return shown


def list_menu_delete(p, name):
    p.locator(f'#layers-list .layer-item[data-layer-id="{p.ids[name]}"] .layer-info').click(button='right')
    p.wait_for_selector('#context-menu', state='visible')
    item = p.locator('#context-menu [data-action="delete"]')
    return item.inner_text() if item.is_visible() else None


@pytest.mark.parametrize('mode', QUIET_TABS)
def test_delete_and_backspace_never_delete_a_screen_off_pixel_map(pg, mode):
    p = pg
    tab(p, mode)
    select(p, 'B')
    steps = p.evaluate("() => window.app.history.length")
    for key in ('Delete', 'Backspace'):
        p.keyboard.press(key)
        p.wait_for_timeout(400)
        assert names(p) == ['A', 'B'], (mode, key)
    if mode != 'rigging':       # Header/Footer clears bars: B has none
        assert p.evaluate("() => window.app.history.length") == steps, mode
    # the canvas menu offers no Delete Screen here
    assert not canvas_menu_delete(p), mode
    # the Screens list's right-click still deletes, with no Del hint
    assert list_menu_delete(p, 'B') == 'Delete Screen', mode
    p.click('#context-menu [data-action="delete"]')
    p.wait_for_function("() => window.app.project.layers.length === 1", timeout=5000)
    assert names(p) == ['A']


def test_pixel_map_deletes_with_the_key_and_both_menus(pg):
    p = pg
    tab(p, 'pixel-map')
    select(p, 'B')
    p.keyboard.press('Delete')
    p.wait_for_function("() => window.app.project.layers.length === 1", timeout=5000)
    assert names(p) == ['A']
    p.evaluate("() => window.app.undo()")
    p.wait_for_function("() => window.app.project.layers.length === 2", timeout=5000)
    # the canvas menu has Delete Screen with its Del hint, as does the list
    select(p, 'B')
    assert (canvas_menu_delete(p) or '').startswith('Delete Screen (')
    assert (list_menu_delete(p, 'B') or '').startswith('Delete Screen (')
    p.evaluate("() => window.app.hideContextMenu()")
    # a field keeps its own keys
    p.click('#offset-x')
    p.keyboard.press('End')
    p.keyboard.press('Backspace')
    p.keyboard.press('Escape')
    assert names(p) == ['A', 'B']
