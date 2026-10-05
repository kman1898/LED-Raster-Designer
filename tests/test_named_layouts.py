"""Named panel layouts: saved on the server, shared by every screen.

A named layout is a whole look - where each panel sits, its sizes, its
folds - saved under a name in one file beside the presets, so it survives a
restart and every screen connected to the app can switch to it. Each screen
still keeps its own current arrangement; picking a named layout changes only
the screen it was picked on. View › Layouts lists them, with Save Current
Layout…, Delete Layout… and Reset Layout.
"""

import json
import os

import pytest

import routes_layouts
from conftest import settled  # noqa: E402


def _layout(**over):
    base = {'v': 1, 'rings': [{'bar': 'menu', 'edge': 'top'}, {'panel': 'screens', 'edge': 'right'},
                              {'bar': 'status', 'edge': 'bottom'}, {'bar': 'tabs', 'edge': 'top'},
                              {'panel': 'settings', 'edge': 'left'}, {'panel': 'hardware', 'edge': 'bottom'}],
            'sizes': {'lrd_left_w': 300, 'lrd_dock_h': None}, 'folds': {'left': False, 'right': True, 'dock': False}}
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _empty_store():
    """Every test starts with no saved layouts."""
    if os.path.exists(routes_layouts.LAYOUTS_FILE):
        os.remove(routes_layouts.LAYOUTS_FILE)
    yield


# ── the server end ────────────────────────────────────────────────────────

def test_save_list_replace_and_delete(client):
    assert client.get('/api/layouts').get_json() == {'layouts': []}
    r = client.put('/api/layouts', json={'name': '  Show   day ', 'layout': _layout()})
    assert r.status_code == 200
    assert [i['name'] for i in r.get_json()['layouts']] == ['Show day']
    client.put('/api/layouts', json={'name': 'booth', 'layout': _layout()})
    # the same name in another case replaces it
    other = _layout(folds={'left': True})
    client.put('/api/layouts', json={'name': 'SHOW DAY', 'layout': other})
    items = client.get('/api/layouts').get_json()['layouts']
    assert [i['name'] for i in items] == ['booth', 'SHOW DAY']
    assert items[1]['layout']['folds'] == {'left': True}
    # it is on disk, as the one file
    with open(routes_layouts.LAYOUTS_FILE, encoding='utf-8') as f:
        assert len(json.load(f)['layouts']) == 2
    r = client.delete('/api/layouts', json={'name': 'Booth'})
    assert [i['name'] for i in r.get_json()['layouts']] == ['SHOW DAY']
    assert client.delete('/api/layouts', json={'name': 'nope'}).status_code == 404


@pytest.mark.parametrize('body', [
    {'name': '', 'layout': _layout()},
    {'name': 'x' * 61, 'layout': _layout()},
    {'name': 7, 'layout': _layout()},
    {'name': 'a', 'layout': 'not a layout'},
    {'name': 'a', 'layout': _layout(v=2)},
    {'name': 'a', 'layout': _layout(rings=[])},
    {'name': 'a', 'layout': _layout(rings=[{'panel': 'screens', 'edge': 'middle'}])},
    {'name': 'a', 'layout': _layout(rings=[{'panel': 'mystery', 'edge': 'left'}])},
    {'name': 'a', 'layout': _layout(sizes={'lrd_left_w': 'wide'})},
    {'name': 'a', 'layout': _layout(sizes={'lrd_left_w': True})},
    {'name': 'a', 'layout': _layout(sizes={'not_a_key': 200})},
    {'name': 'a', 'layout': _layout(folds={'left': 'yes'})},
    {'name': 'a', 'layout': _layout(folds={'middle': True})},
])
def test_what_could_not_be_a_layout_is_refused_and_nothing_is_stored(client, body):
    r = client.put('/api/layouts', json=body)
    assert r.status_code == 400 and r.get_json()['error'], r.get_json()
    assert client.get('/api/layouts').get_json() == {'layouts': []}


def test_a_damaged_file_reads_as_no_layouts_and_bad_rows_are_dropped(client):
    os.makedirs(os.path.dirname(routes_layouts.LAYOUTS_FILE), exist_ok=True)
    with open(routes_layouts.LAYOUTS_FILE, 'w', encoding='utf-8') as f:
        f.write('{ not json')
    assert client.get('/api/layouts').get_json() == {'layouts': []}
    with open(routes_layouts.LAYOUTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'layouts': [{'name': 'good', 'layout': _layout()}, {'name': 'bad', 'layout': {'v': 1}}, 'junk']}, f)
    assert [i['name'] for i in client.get('/api/layouts').get_json()['layouts']] == ['good']


def test_fifty_is_the_limit(client):
    for i in range(routes_layouts.MAX_LAYOUTS):
        assert client.put('/api/layouts', json={'name': f'L{i}', 'layout': _layout()}).status_code == 200
    r = client.put('/api/layouts', json={'name': 'one more', 'layout': _layout()})
    assert r.status_code == 400 and 'delete one' in r.get_json()['error']
    # replacing one already there is still fine
    assert client.put('/api/layouts', json={'name': 'L3', 'layout': _layout()}).status_code == 200


# ── View › Layouts, on two screens ───────────────────────────────────────

FOLDING_JS = """() => document.getAnimations().filter(a => a.playState === 'running'
    && a.effect && a.effect.target && a.effect.target.classList
    && a.effect.target.classList.contains('lrd-panel')).length"""


def _screen(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    return ctx, pg, errors


def _settle(pg):
    settled(pg, lambda: pg.evaluate(FOLDING_JS), lambda n: n == 0, timeout_ms=5000)
    pg.wait_for_timeout(300)


def _open_layouts(pg):
    pg.locator('.menu-item', has_text='View').first.click()
    pg.locator('#menu-view .menu-has-submenu[data-action="layouts"]').hover()
    pg.wait_for_timeout(400)
    return pg.evaluate("""() => [...document.querySelectorAll('#layouts-submenu .menu-option')]
        .map(o => ({text: o.textContent, name: o.dataset.lrdLayout || null, act: o.dataset.lrdLayoutAct || null,
                    current: o.classList.contains('lrd-layout-current'), off: o.classList.contains('menu-disabled')}))""")


def _rings(pg):
    return pg.evaluate("() => window.LRD_LAYOUT.rings().map(r => (r.panel || r.bar) + ':' + r.edge)")


def test_a_layout_saved_on_one_screen_opens_on_another(e2e_server, pw_browser):
    a_ctx, a, a_err = _screen(e2e_server, pw_browser)
    b_ctx, b, b_err = _screen(e2e_server, pw_browser)
    try:
        # screen A: tray on the left, Settings along the bottom, Screens folded, a wider tray
        a.evaluate("() => { window.LRD_LAYOUT.move('hardware', 'left', 0); window.LRD_LAYOUT.move('settings', 'bottom'); }")
        a.evaluate("() => window.LRD_SIZES.restore({lrd_hardware_w: 520})")
        a.locator('#right-sidebar-toggle').click()
        _settle(a)
        want = _rings(a)
        items = _open_layouts(a)
        assert [i['text'] for i in items if i['act']] == ['Save Current Layout…', 'Delete Layout…', 'Reset Layout']
        assert [i for i in items if i['act'] == 'delete'][0]['off'], 'Delete offered with nothing saved'
        a.locator('#layouts-submenu .menu-option[data-lrd-layout-act="save"]').click()
        a.locator('#lrd-layout-name').fill('Show day')
        a.locator('#lrd-layout-name').press('Enter')
        a.wait_for_timeout(500)
        assert a.locator('.lrd-layout-dialog').count() == 0
        assert 'saved' in a.evaluate("() => document.getElementById('status-message').textContent")
        items = _open_layouts(a)
        assert [i['name'] for i in items if i['current']] == ['Show day'], items
        a.keyboard.press('Escape')

        # screen B never moved anything, and still has its own default look
        assert b.evaluate("() => window.LRD_LAYOUT.isDefault()")
        items = _open_layouts(b)
        assert [i['name'] for i in items if i['name']] == ['Show day'] and not any(i['current'] for i in items)
        b.locator('#layouts-submenu .menu-option[data-lrd-layout="Show day"]').click()
        _settle(b)
        assert _rings(b) == want
        got = b.evaluate("""() => ({hwW: Math.round(document.getElementById('hardware-dock').getBoundingClientRect().width),
            rightFolded: document.getElementById('right-sidebar').classList.contains('collapsed'),
            stored: localStorage.getItem('ledRasterSidebarCollapsed_right')})""")
        assert got == {'hwW': 520, 'rightFolded': True, 'stored': '1'}, got
        # and A was not touched by B's pick
        assert _rings(a) == want
        assert a_err == [] and b_err == [], (a_err, b_err)
    finally:
        a_ctx.close()
        b_ctx.close()


def test_saving_over_a_name_says_so_and_delete_takes_it_away(e2e_server, pw_browser):
    ctx, pg, errors = _screen(e2e_server, pw_browser)
    try:
        pg.evaluate("""() => fetch('/api/layouts', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Booth', layout: window.LRD_LAYOUT.snapshot()})})""")
        _open_layouts(pg)
        pg.locator('#layouts-submenu .menu-option[data-lrd-layout-act="save"]').click()
        assert pg.locator('#lrd-layout-name').input_value() == 'Booth', 'the matching name was not offered'
        assert 'replaces the layout "Booth"' in pg.locator('.lrd-layout-note').text_content()
        pg.locator('#lrd-layout-name').press('Escape')
        assert pg.locator('.lrd-layout-dialog').count() == 0
        _open_layouts(pg)
        pg.locator('#layouts-submenu .menu-option[data-lrd-layout-act="delete"]').click()
        pg.locator('.lrd-layout-row', has_text='Booth').locator('button').click()
        pg.wait_for_timeout(400)
        assert pg.locator('.lrd-layout-list').text_content() == 'No saved layouts.'
        assert pg.evaluate("() => fetch('/api/layouts').then(r => r.json()).then(d => d.layouts.length)") == 0
        assert errors == [], errors
    finally:
        ctx.close()


def test_a_layout_this_screen_cannot_read_changes_nothing(e2e_server, pw_browser):
    ctx, pg, errors = _screen(e2e_server, pw_browser)
    try:
        before = _rings(pg)
        ok = pg.evaluate("""() => window.LRD_LAYOUT.restore({v: 1, rings: [{panel: 'screens', edge: 'right'}],
            sizes: {}, folds: {}})""")
        assert ok is False and _rings(pg) == before
        assert errors == [], errors
    finally:
        ctx.close()
