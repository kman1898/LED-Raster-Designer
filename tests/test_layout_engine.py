"""The panels take any edge: the frame's rings, built from one saved list.

layout.js builds the page as rings around the canvas from a list kept per
screen (localStorage lrd_layout). The Settings panel, the Screens panel and
the Hardware tray can each take the left, right, top or bottom edge; the
menu, status bar and toolbar stay put. These tests move every panel to
every edge through the engine (there is no control for it yet) and check
what a person would see: the panel on that side of the canvas at its size
for that direction, its fold tab and resize strip on its inner edge, the
fold working, the canvas filling the rest - and the saved list surviving a
reload, a damaged one falling back to the default.
"""

import json

import pytest

from conftest import settled  # noqa: E402

VIEWPORT = {'width': 1600, 'height': 900}
PANELS = {
    'settings': {'el': 'left-sidebar', 'toggle': 'left-sidebar-toggle', 'key': 'left'},
    'screens': {'el': 'right-sidebar', 'toggle': 'right-sidebar-toggle', 'key': 'right'},
    'hardware': {'el': 'hardware-dock', 'toggle': 'hardware-dock-toggle', 'key': 'dock'},
}
EDGES = ['left', 'right', 'top', 'bottom']
FOLD_TO = {'left': '‹', 'right': '›', 'bottom': '▾', 'top': '▴'}
OPEN_TO = {'left': '›', 'right': '‹', 'bottom': '▴', 'top': '▾'}

FOLDING_JS = """() => document.getAnimations().filter(a => a.playState === 'running'
    && a.effect && a.effect.target && a.effect.target.classList
    && a.effect.target.classList.contains('lrd-panel')).length"""

GEOM_JS = """(p) => {
    const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height,
                shown: getComputedStyle(el).display !== 'none' && (r.width > 0 || r.height > 0)}; };
    const panel = document.getElementById(p.el), toggle = document.getElementById(p.toggle);
    const strip = document.querySelector(`.lrd-resize-handle[data-lrd-resize="${p.key}"]`);
    const wrap = document.getElementById('canvas-wrapper'), canvas = document.getElementById('main-canvas');
    return {edge: panel.dataset.lrdEdge, collapsed: panel.classList.contains('collapsed'),
            panel: rect(panel), toggle: rect(toggle), toggleText: toggle.textContent, strip: rect(strip),
            center: rect(document.getElementById('canvas-container')),
            wrapW: wrap.clientWidth, wrapH: wrap.clientHeight, canvasW: canvas.width, canvasH: canvas.height};
}"""


@pytest.fixture
def page(e2e_server, pw_browser):
    """A fresh screen: nothing saved, guides off, on the Data view so the
    tray is in layout."""
    ctx = pw_browser.new_context(viewport=VIEWPORT)
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    ctx.close()


def _settle(pg):
    left = settled(pg, lambda: pg.evaluate(FOLDING_JS), lambda n: n == 0, timeout_ms=5000)
    assert left == 0, f'{left} panel animations still running'
    pg.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    pg.wait_for_timeout(300)


def _rings(pg):
    return pg.evaluate("() => window.LRD_LAYOUT.rings().map(r => (r.panel || r.bar) + ':' + r.edge)")


def _on_its_edge(g, edge):
    """The panel is on the canvas's `edge` side, and its tab and strip sit on
    the panel's inner edge, the one facing the canvas."""
    p, c, t, s = g['panel'], g['center'], g['toggle'], g['strip']
    inner = {'left': p['right'], 'right': p['left'], 'top': p['bottom'], 'bottom': p['top']}[edge]
    if edge == 'left':
        assert p['right'] <= c['left'] + 1, g
        assert abs(t['left'] - inner) <= 2, f'tab not on the inner edge: {g}'
        assert abs((s['left'] + 3) - inner) <= 2, f'strip not on the inner edge: {g}'
    elif edge == 'right':
        assert p['left'] >= c['right'] - 1, g
        assert abs(t['right'] - inner) <= 2, f'tab not on the inner edge: {g}'
        assert abs((s['left'] + 4) - inner) <= 2, f'strip not on the inner edge: {g}'
    elif edge == 'top':
        assert p['bottom'] <= c['top'] + 1, g
        assert abs(t['top'] - inner) <= 2, f'tab not on the inner edge: {g}'
        assert abs((s['top'] + 4) - inner) <= 2, f'strip not on the inner edge: {g}'
    else:
        assert p['top'] >= c['bottom'] - 1, g
        assert abs(t['bottom'] - inner) <= 2, f'tab not on the inner edge: {g}'
        assert abs((s['top'] + 3) - inner) <= 2, f'strip not on the inner edge: {g}'


@pytest.mark.parametrize('edge', EDGES)
@pytest.mark.parametrize('name', list(PANELS))
def test_a_panel_takes_any_edge_and_folds_there(page, name, edge):
    pg, errors = page
    p = PANELS[name]
    assert pg.evaluate('([n, e]) => window.LRD_LAYOUT.move(n, e)', [name, edge])
    _settle(pg)
    g = pg.evaluate(GEOM_JS, p)
    assert g['edge'] == edge and not g['collapsed'], g
    assert g['strip']['shown'] and g['toggle']['shown'], g
    _on_its_edge(g, edge)
    assert g['toggleText'] == FOLD_TO[edge], g
    assert (g['canvasW'], g['canvasH']) == (g['wrapW'], g['wrapH']), f'the canvas missed the move: {g}'
    # its size is the one for this direction
    vertical = edge in ('left', 'right')
    size = g['panel']['width'] if vertical else g['panel']['height']
    want = {('settings', True): 260, ('screens', True): 260, ('hardware', True): 460,
            ('settings', False): 220, ('screens', False): 200, ('hardware', False): 172}[(name, vertical)]
    assert abs(size - want) <= 1, f'{name} on the {edge} is {size}px, not {want}: {g}'

    # fold: the panel gives its room back, the tab turns, the strip goes
    pg.locator('#' + p['toggle']).click()
    _settle(pg)
    f = pg.evaluate(GEOM_JS, p)
    gone = f['panel']['width'] if vertical else f['panel']['height']
    assert f['collapsed'] and gone <= 1, f'folding on the {edge} left {gone}px: {f}'
    assert f['toggleText'] == OPEN_TO[edge], f
    assert not f['strip']['shown'], f'a folded panel still offers a strip: {f}'
    assert (f['canvasW'], f['canvasH']) == (f['wrapW'], f['wrapH']), f
    pg.locator('#' + p['toggle']).click()
    _settle(pg)
    o = pg.evaluate(GEOM_JS, p)
    assert not o['collapsed'] and abs((o['panel']['width'] if vertical else o['panel']['height']) - want) <= 1, o
    assert errors == [], errors


def test_the_arrangement_is_kept_per_screen_and_reset_clears_it(page):
    pg, errors = page
    pg.evaluate("() => window.LRD_LAYOUT.move('hardware', 'left', 0)")
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'bottom')")
    before = _rings(pg)
    assert 'hardware:left' in before and 'settings:bottom' in before, before
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    assert _rings(pg) == before, 'the arrangement did not survive a reload'
    pg.evaluate("() => window.LRD_LAYOUT.reset()")
    assert pg.evaluate("() => window.LRD_LAYOUT.isDefault()")
    assert pg.evaluate("() => localStorage.getItem('lrd_layout')") is None
    assert errors == [], errors


BAD_SAVES = {
    'not json': 'not json at all',
    'a panel missing': {'v': 1, 'rings': [{'bar': 'menu', 'edge': 'top'}, {'panel': 'screens', 'edge': 'right'},
                                          {'bar': 'status', 'edge': 'bottom'}, {'bar': 'tabs', 'edge': 'top'},
                                          {'panel': 'settings', 'edge': 'left'}]},
    'a panel twice': {'v': 1, 'rings': [{'bar': 'menu', 'edge': 'top'}, {'panel': 'screens', 'edge': 'right'},
                                        {'bar': 'status', 'edge': 'bottom'}, {'bar': 'tabs', 'edge': 'top'},
                                        {'panel': 'settings', 'edge': 'left'}, {'panel': 'hardware', 'edge': 'bottom'},
                                        {'panel': 'screens', 'edge': 'left'}]},
    'an edge that is not one': {'v': 1, 'rings': [{'bar': 'menu', 'edge': 'top'}, {'panel': 'screens', 'edge': 'middle'},
                                                  {'bar': 'status', 'edge': 'bottom'}, {'bar': 'tabs', 'edge': 'top'},
                                                  {'panel': 'settings', 'edge': 'left'}, {'panel': 'hardware', 'edge': 'bottom'}]},
    'a bar moved': {'v': 1, 'rings': [{'bar': 'menu', 'edge': 'top'}, {'panel': 'screens', 'edge': 'right'},
                                      {'bar': 'status', 'edge': 'top'}, {'bar': 'tabs', 'edge': 'top'},
                                      {'panel': 'settings', 'edge': 'left'}, {'panel': 'hardware', 'edge': 'bottom'}]},
    'the menu not outermost': {'v': 1, 'rings': [{'panel': 'screens', 'edge': 'right'}, {'bar': 'menu', 'edge': 'top'},
                                                 {'bar': 'status', 'edge': 'bottom'}, {'bar': 'tabs', 'edge': 'top'},
                                                 {'panel': 'settings', 'edge': 'left'}, {'panel': 'hardware', 'edge': 'bottom'}]},
    'an unknown version': {'v': 9, 'rings': []},
}


@pytest.mark.parametrize('case', list(BAD_SAVES))
def test_a_damaged_saved_arrangement_falls_back_to_the_default(e2e_server, pw_browser, case):
    raw = BAD_SAVES[case]
    raw = raw if isinstance(raw, str) else json.dumps(raw)
    ctx = pw_browser.new_context(viewport=VIEWPORT)
    ctx.add_init_script("(() => { try { localStorage.setItem('lrd_quickstart_disabled', '1'); "
                        "localStorage.setItem('lrd_layout', %s); } catch (e) {} })();" % json.dumps(raw))
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        assert pg.evaluate("() => window.LRD_LAYOUT.isDefault()"), f'{case}: {_rings(pg)}'
        for p in PANELS.values():
            assert pg.evaluate("(id) => !!document.getElementById(id) && document.getElementById(id).isConnected",
                               p['el']), f'{case}: {p["el"]} was lost'
        assert errors == [], errors
    finally:
        ctx.close()


def test_each_direction_keeps_its_own_size(page):
    """A panel moved to the bottom is sized by its height; brought back to
    its side it finds its width as it was. Resizing it in one direction
    never touches the other's saved size."""
    pg, errors = page
    pg.evaluate("() => { localStorage.setItem('lrd_left_w', '320'); }")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    _settle(pg)
    assert abs(pg.evaluate(GEOM_JS, PANELS['settings'])['panel']['width'] - 320) <= 1
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'bottom')")
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['settings'])
    assert abs(g['panel']['height'] - 220) <= 1, g
    # drag its strip up by 80: the height grows, the width key stays 320
    s = g['strip']
    x, y = s['left'] + 200, s['top'] + 3
    pg.mouse.move(x, y)
    pg.mouse.down()
    for k in range(1, 5):
        pg.mouse.move(x, y - 20 * k)
    pg.mouse.up()
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['settings'])
    assert abs(g['panel']['height'] - 300) <= 2, g
    saved = pg.evaluate("() => [localStorage.getItem('lrd_left_w'), localStorage.getItem('lrd_settings_h')]")
    assert saved[0] == '320' and abs(int(saved[1]) - 300) <= 2, saved
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'left')")
    _settle(pg)
    assert abs(pg.evaluate(GEOM_JS, PANELS['settings'])['panel']['width'] - 320) <= 1
    assert errors == [], errors


def test_the_tray_down_a_side_deals_one_column_then_two(page):
    pg, errors = page
    pg.evaluate("() => window.LRD_LAYOUT.move('hardware', 'left', 0)")
    _settle(pg)
    assert pg.evaluate("() => window.app._dockPickColCount()") == 1
    pg.evaluate("() => { localStorage.setItem('lrd_hardware_w', '930'); }")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['hardware'])
    assert abs(g['panel']['width'] - 930) <= 1, g
    assert pg.evaluate("() => window.app._dockPickColCount()") == 2
    assert errors == [], errors


def test_a_strip_lays_its_contents_across(page):
    """Across the top or bottom the Settings panel's sections run side by
    side, and the Screens panel keeps its list in view."""
    pg, errors = page
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'bottom')")
    pg.evaluate("() => window.LRD_LAYOUT.move('screens', 'top')")
    _settle(pg)
    tops = pg.evaluate("""() => [...document.querySelectorAll('#left-sidebar > .panel')]
        .filter(p => getComputedStyle(p).display !== 'none')
        .map(p => Math.round(p.getBoundingClientRect().top))""")
    assert len(tops) >= 2 and len(set(tops[:2])) == 1, f'the sections did not run across: {tops}'
    lst = pg.evaluate("() => document.getElementById('layers-list').getBoundingClientRect().height")
    assert lst > 40, f'the Screens list has no room in the strip: {lst}px'
    assert errors == [], errors


def test_the_caret_stays_where_it_was_through_a_move(page):
    pg, errors = page
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    pg.locator('#offset-x').click()
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'right')")
    assert pg.evaluate("() => document.activeElement && document.activeElement.id") == 'offset-x'
    assert errors == [], errors


def test_the_tray_still_leaves_layout_outside_its_views_wherever_it_is(page):
    pg, errors = page
    pg.evaluate("() => window.LRD_LAYOUT.move('hardware', 'left', 0)")
    pg.locator('[data-mode="pixel-map"]').click()
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['hardware'])
    assert not g['panel']['shown'] and not g['toggle']['shown'] and not g['strip']['shown'], g
    assert (g['canvasW'], g['canvasH']) == (g['wrapW'], g['wrapH']), g
    pg.locator('[data-mode="power"]').click()
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['hardware'])
    assert g['panel']['shown'] and g['edge'] == 'left', g
    assert errors == [], errors


def test_a_hidden_panels_tab_is_not_parked_at_the_window_edge(page):
    """Reported with the tray folded down the right: switching between the
    views left its tab floating. Out of Data and Power the tray is out of
    layout and measures as nothing at the window's corner; re-pinning its
    tab then parked it at the window's far edge, and when the tray came back
    the tab slid across the whole window from there. A hidden panel's tab
    now stays where it was."""
    pg, errors = page
    pg.locator('[data-mode="power"]').click()
    pg.evaluate("""() => { const L = window.LRD_LAYOUT; const r = L.rings().filter(x => x.panel !== 'hardware');
        r.splice(1, 0, {panel: 'hardware', edge: 'right'}); L.apply(r); }""")
    _settle(pg)
    pg.locator('#hardware-dock-toggle').click()
    _settle(pg)
    before = pg.evaluate("() => document.getElementById('hardware-dock-toggle').style.right")
    pg.locator('[data-mode="show-look"]').click()
    pg.evaluate("() => window.app.remeasureCanvas()")   # what every settle does
    hidden = pg.evaluate("() => document.getElementById('hardware-dock-toggle').style.right")
    assert hidden == before, f'the hidden tray\'s tab was moved to {hidden} (it was {before})'
    pg.locator('[data-mode="power"]').click()
    _settle(pg)
    g = pg.evaluate(GEOM_JS, PANELS['hardware'])
    assert g['toggle']['shown'] and abs(g['toggle']['right'] - g['panel']['left']) <= 2, g
    assert errors == [], errors


def test_a_tab_follows_its_panel_while_a_neighbour_folds(page):
    """Two panels down the right: folding the outer one slides the inner one
    along without changing its size. Its tab is re-pinned every frame of the
    fold, not only once the fold has ended. (The tab eases to each new pin
    over its own short slide, so the pin is read, not the painted box.)"""
    pg, errors = page
    pg.evaluate("""() => { const L = window.LRD_LAYOUT; const r = L.rings().filter(x => x.panel !== 'hardware');
        r.splice(1, 0, {panel: 'hardware', edge: 'right'}); L.apply(r); }""")
    _settle(pg)
    pg.evaluate("() => { document.getElementById('hardware-dock').style.transition = 'width 3s linear'; }")
    pg.locator('#hardware-dock-toggle').click()
    hw = "() => document.getElementById('hardware-dock').getBoundingClientRect().width"
    settled(pg, lambda: pg.evaluate(hw), lambda w: 40 < w < 420, timeout_ms=5000)   # mid-fold
    mid = pg.evaluate("""() => {
        const p = document.getElementById('right-sidebar').getBoundingClientRect();
        const pin = parseFloat(document.getElementById('right-sidebar-toggle').style.right);
        const hw = document.getElementById('hardware-dock').getBoundingClientRect().width;
        return { pinnedAt: window.innerWidth - pin, panelLeft: p.left, hardwareWidth: hw };
    }""")
    assert 0 < mid['hardwareWidth'] < 460, f'not mid-fold: {mid}'
    assert abs(mid['pinnedAt'] - mid['panelLeft']) <= 3, f'the Screens tab was not re-pinned mid-fold: {mid}'
    _settle(pg)
    pg.evaluate("() => { document.getElementById('hardware-dock').style.transition = ''; }")
    assert errors == [], errors
