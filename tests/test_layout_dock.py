"""Moving a panel by hand: drag its title bar, or right-click it.

Each panel has one handle - the Settings panel's title bar, the Screens
panel's header, the Hardware tray's header. Dragging one lights up the places
the panel can go and dropping on one moves it there (the engine is
test_layout_engine's); Escape, or letting go away from every place, leaves
it where it was. A right-click on a handle offers Move to, Fold, Reset size
and Reset Layout, and the View menu has Reset Layout too. Everything here is
driven with the mouse, the way a person does it.
"""

import pytest

from conftest import settled  # noqa: E402

VIEWPORT = {'width': 1600, 'height': 900}
HANDLES = {
    'settings': '#left-sidebar-head',
    'screens': '#right-sidebar > .panel > .panel-header',
    'hardware': '#hardware-dock .hw-dock-head > label',
}

FOLDING_JS = """() => document.getAnimations().filter(a => a.playState === 'running'
    && a.effect && a.effect.target && a.effect.target.classList
    && a.effect.target.classList.contains('lrd-panel')).length"""

ZONES_JS = """() => [...document.querySelectorAll('.lrd-drop-zone')].map(z => {
    const r = z.getBoundingClientRect();
    return {place: z.dataset.lrdPlace, hot: z.classList.contains('lrd-drop-hot'),
            x: r.left + r.width / 2, y: r.top + r.height / 2};
})"""


@pytest.fixture
def page(e2e_server, pw_browser):
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
    settled(pg, lambda: pg.evaluate(FOLDING_JS), lambda n: n == 0, timeout_ms=5000)
    pg.wait_for_timeout(300)


def _rings(pg):
    return pg.evaluate("() => window.LRD_LAYOUT.rings().map(r => (r.panel || r.bar) + ':' + r.edge)")


def _grab(pg, name):
    box = pg.locator(HANDLES[name]).first.bounding_box()
    x, y = box['x'] + min(40, box['width'] / 2), box['y'] + box['height'] / 2
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(x + 12, y + 12, steps=3)   # past the threshold: now a drag
    return x, y


def _drag_to(pg, name, place):
    _grab(pg, name)
    zones = pg.evaluate(ZONES_JS)
    target = [z for z in zones if z['place'] == place]
    assert target, f'no place "{place}" while dragging {name}: {[z["place"] for z in zones]}'
    pg.mouse.move(target[0]['x'], target[0]['y'], steps=8)
    hot = [z['place'] for z in pg.evaluate(ZONES_JS) if z['hot']]
    assert hot == [place], hot
    ghost = pg.evaluate("() => document.querySelector('.lrd-drag-ghost').textContent")
    assert place in ghost, ghost
    pg.mouse.up()
    _settle(pg)


def test_the_settings_title_bar_names_the_view(page):
    pg, errors = page
    for mode, name in (('pixel-map', 'Pixel Map'), ('power', 'Power'), ('data-flow', 'Data')):
        pg.locator(f'[data-mode="{mode}"]').click()
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => document.getElementById('left-sidebar-view').textContent") == name
    assert errors == [], errors


@pytest.mark.parametrize('name', list(HANDLES))
def test_dragging_a_title_bar_to_a_place_moves_the_panel_there(page, name):
    pg, errors = page
    _drag_to(pg, name, 'Left, full height')
    rings = _rings(pg)
    assert rings[1] == f'{name}:left', f'{name} is not the full-height left panel: {rings}'
    assert pg.evaluate("() => document.querySelectorAll('.lrd-drop-zone, .lrd-drag-ghost').length") == 0
    _drag_to(pg, name, 'Bottom, under the canvas')
    assert _rings(pg)[-1] == f'{name}:bottom', _rings(pg)
    assert errors == [], errors


def test_every_side_offers_full_height_and_under_the_toolbar(page):
    pg, errors = page
    _grab(pg, 'hardware')
    places = {z['place'] for z in pg.evaluate(ZONES_JS)}
    pg.keyboard.press('Escape')
    pg.mouse.up()
    for want in ('Left, full height', 'Left, under the toolbar', 'Right, full height',
                 'Right, under the toolbar', 'Top, under the toolbar', 'Bottom, under the canvas',
                 'Bottom, across'):
        assert want in places, (want, places)
    assert errors == [], errors


def test_escape_or_letting_go_nowhere_changes_nothing(page):
    pg, errors = page
    before = _rings(pg)
    _grab(pg, 'screens')
    zone = [z for z in pg.evaluate(ZONES_JS) if z['place'] == 'Left, full height'][0]
    pg.mouse.move(zone['x'], zone['y'], steps=6)
    pg.keyboard.press('Escape')
    pg.mouse.up()
    _settle(pg)
    assert _rings(pg) == before
    assert pg.evaluate("() => document.querySelectorAll('.lrd-drop-zone, .lrd-drag-ghost').length") == 0
    # let go over the middle of the canvas, away from every place
    _grab(pg, 'screens')
    wrap = pg.locator('#canvas-wrapper').bounding_box()
    pg.mouse.move(wrap['x'] + wrap['width'] / 2, wrap['y'] + wrap['height'] / 2, steps=6)
    assert not [z for z in pg.evaluate(ZONES_JS) if z['hot']]
    pg.mouse.up()
    _settle(pg)
    assert _rings(pg) == before
    assert errors == [], errors


def test_a_press_on_a_header_control_or_a_plain_click_moves_nothing(page):
    pg, errors = page
    before = _rings(pg)
    sel = pg.locator('#processor-add-device').bounding_box()
    pg.mouse.move(sel['x'] + 10, sel['y'] + 5)
    pg.mouse.down()
    pg.mouse.move(sel['x'] - 200, sel['y'] - 200, steps=6)
    assert pg.evaluate("() => document.querySelectorAll('.lrd-drop-zone').length") == 0, \
        'the tray\'s add picker started a panel drag'
    pg.mouse.up()
    pg.keyboard.press('Escape')
    pg.locator(HANDLES['screens']).first.click()
    _settle(pg)
    assert _rings(pg) == before
    assert errors == [], errors


def _menu(pg, name):
    box = pg.locator(HANDLES[name]).first.bounding_box()
    pg.mouse.click(box['x'] + 20, box['y'] + box['height'] / 2, button='right')
    pg.wait_for_timeout(150)
    return pg.evaluate("""() => [...document.querySelectorAll('.lrd-panel-menu .menu-option')]
        .map(o => [o.textContent, !o.classList.contains('menu-disabled')])""")


def _choose(pg, label):
    pg.locator('.lrd-panel-menu .menu-option', has_text=label).first.click()
    _settle(pg)


def test_the_right_click_menu_moves_folds_and_resets(page):
    pg, errors = page
    items = dict(_menu(pg, 'screens'))
    assert items['Move to Right'] is False and items['Move to Top'] is True, items
    assert items['Reset Layout'] is False, 'Reset Layout offered on the default arrangement'
    _choose(pg, 'Move to Top')
    assert 'screens:top' in _rings(pg)
    # Fold from the menu; folded, the title bar is gone with the panel, and
    # its tab is the way back
    _menu(pg, 'screens')
    _choose(pg, 'Fold')
    assert pg.evaluate("() => document.getElementById('right-sidebar').classList.contains('collapsed')")
    pg.locator('#right-sidebar-toggle').click()
    _settle(pg)
    assert not pg.evaluate("() => document.getElementById('right-sidebar').classList.contains('collapsed')")
    # Reset size: a strip dragged taller goes back to its default height
    pg.evaluate("() => { document.documentElement.style.setProperty('--lrd-screens-h', '320px');"
                " localStorage.setItem('lrd_screens_h', '320'); }")
    _settle(pg)
    assert abs(pg.locator('#right-sidebar').bounding_box()['height'] - 320) <= 1
    _menu(pg, 'screens')
    _choose(pg, 'Reset size')
    assert abs(pg.locator('#right-sidebar').bounding_box()['height'] - 200) <= 1
    assert pg.evaluate("() => localStorage.getItem('lrd_screens_h')") is None
    # Reset Layout from the same menu
    _menu(pg, 'screens')
    _choose(pg, 'Reset Layout')
    assert pg.evaluate("() => window.LRD_LAYOUT.isDefault()")
    assert errors == [], errors


def test_view_layouts_reset_layout(page):
    pg, errors = page
    pg.evaluate("() => window.LRD_LAYOUT.move('settings', 'bottom')")
    _settle(pg)
    pg.locator('.menu-item', has_text='View').first.click()
    pg.locator('#menu-view .menu-has-submenu[data-action="layouts"]').hover()
    pg.locator('#layouts-submenu .menu-option[data-lrd-layout-act="reset"]').click()
    _settle(pg)
    assert pg.evaluate("() => window.LRD_LAYOUT.isDefault()")
    assert errors == [], errors
