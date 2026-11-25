"""The IDM Locator's Swap mode (owner, 2026-11-24; app-idm-locator.js,
canvas-idm.js, idm-phone.js, idm-core.js, routes_project.py).

What this file pins:

* The server: project.idmSwap = {on, color} held to its shape
  (app.sanitize_idm_swap) on its own route and in both project funnels;
  the route stores it, tells every page (`idm_swap_updated`, with the
  sender's origin) and ends a pristine project (it is an edit); a show
  without the key opens with it off. The Black field colour is gone: a
  show saved with it opens on the default field, on the server and in the
  browser, and no Black swatch is left on the tab or the phone.
* The wall: switched on from the computer, every screen goes pure black
  and the modules still to swap (marked, not ticked Swapped) are filled
  solid in one colour, white by default, an X mark too. Nothing else
  draws: no field, borders, Module IDs or highlight, on the wall output or
  in the view (where only a faint line round each screen shows). The
  colour picked on its swatch applies; a tick turns that module black and
  an untick lights it again. The arrow keys, the pad's arrows and a click
  move and mark nothing and say why. It stays on through a reload, the
  tag at the top of the panel says so, and switching it and changing its
  colour are undo steps (undo and redo, on the server too).
* The phone: its swap list has the same switch and a color chip; the
  computer and the phone follow each other live; closing the swap list
  leaves it on; while it is on a tag on the main screen says so (a tap
  opens the swap list) and the arrows and Mark wait; a tick there darkens
  the module on the wall; its change is one undo step on the computer and
  its own Undo takes it back.
* The log: the view's render_view line and the output's output_frame line
  say Swap mode is on, its colour and how many modules it lit.

Run locally:
    python -m pytest tests/test_idm_swap_mode.py -n 4 --dist loadfile --browser chromium
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

from conftest import settled  # noqa: E402

import app as app_module  # noqa: E402
from app import app as flask_app, socketio  # noqa: E402


# ── 1. The server (no browser) ────────────────────────────────────────────

def test_the_swap_sanitizer_holds_on_and_colour():
    s = app_module.sanitize_idm_swap
    assert s({'on': True, 'color': '#FF0000'}) == {'on': True, 'color': '#ff0000'}
    # only a real true turns it on; a colour that is not one is white
    assert s({'on': 'yes', 'color': 'red'}) == {'on': False, 'color': '#ffffff'}
    assert s({}) == app_module.IDM_SWAP_DEFAULT == {'on': False, 'color': '#ffffff'}
    assert s({'on': True, 'color': 'abc', 'stray': 1}) == {'on': True, 'color': '#aabbcc'}
    assert s(None) is None and s('on') is None and s([True]) is None
    clean = s({'on': True, 'color': '#00ff00'})
    assert s(clean) == clean   # idempotent


def test_the_swap_route_stores_broadcasts_and_is_an_edit(client):
    app_module.current_project.pop('idmSwap', None)
    app_module.current_project['is_pristine'] = True
    sock = socketio.test_client(flask_app, flask_test_client=client)
    try:
        sock.get_received()
        resp = client.put('/api/project/idm-swap', json={'swap': {'on': True, 'color': '#00FF00'}, 'origin': 'tab1'})
        assert resp.status_code == 200
        assert resp.get_json() == {'idmSwap': {'on': True, 'color': '#00ff00'}}
        assert app_module.current_project['idmSwap'] == {'on': True, 'color': '#00ff00'}
        # an edit: the pristine startup project is pristine no more
        assert app_module.current_project['is_pristine'] is False
        got = [r for r in sock.get_received() if r['name'] == 'idm_swap_updated']
        assert got and got[0]['args'][0] == {'swap': {'on': True, 'color': '#00ff00'}, 'origin': 'tab1'}, got
        # junk is refused and the stored one kept
        assert client.put('/api/project/idm-swap', json={'swap': 'on'}).status_code == 400
        assert client.put('/api/project/idm-swap', json=[1]).status_code == 400
        assert app_module.current_project['idmSwap'] == {'on': True, 'color': '#00ff00'}
    finally:
        sock.disconnect()
        app_module.current_project.pop('idmSwap', None)


def test_the_funnels_hold_swap_mode_and_an_old_show_opens_with_it_off(client):
    project = client.get('/api/project').get_json()
    project['idmSwap'] = {'on': 1, 'color': '#F0F'}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['idmSwap'] == {'on': False, 'color': '#ff00ff'}
    project['idmSwap'] = 'on'
    restored = client.put('/api/project', json=project).get_json()
    assert 'idmSwap' not in restored
    # the save funnel too
    project['idmSwap'] = {'on': True, 'color': '#123'}
    assert client.post('/api/project', json=project).status_code == 200
    assert app_module.current_project['idmSwap'] == {'on': True, 'color': '#112233'}
    # a show from before it: no key, and none added
    del project['idmSwap']
    restored = client.put('/api/project', json=project).get_json()
    assert 'idmSwap' not in restored
    assert app_module.normalize_idm_swap(restored) is False


def test_a_show_saved_with_the_black_field_opens_on_the_default(client):
    """Owner, 2026-11-24: the Black field colour was held only for what Swap
    mode does; it is gone, and a show that had it opens on white."""
    s = app_module.sanitize_idm_field
    assert s({'color': '#000000', 'border': 'lines'})['color'] == '#ffffff'
    assert s({'color': '#000', 'border': 'lines'})['color'] == '#ffffff'
    # a dark colour of the crew's own is kept as it is
    assert s({'color': '#0a0a0a'})['color'] == '#0a0a0a'
    project = client.get('/api/project').get_json()
    project['idmField'] = {'color': '#000000', 'border': 'ticks', 'moduleIds': True}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['idmField'] == {'color': '#ffffff', 'border': 'ticks', 'moduleIds': True}
    # the field's own route too
    got = client.put('/api/project/idm-field', json={'field': {'color': '#000000', 'border': 'none'}}).get_json()
    assert got['idmField']['color'] == '#ffffff'


def test_no_black_swatch_is_left_on_the_tab_or_the_phone():
    for name in ('index.html', 'idm_phone.html'):
        with open(os.path.join(ROOT, 'src', 'templates', name), encoding='utf-8') as fh:
            html = fh.read()
        assert 'data-idm-field="#000000"' not in html and 'data-ph-field="#000000"' not in html, name
        assert 'aria-label="Black"' not in html, name
    with open(os.path.join(ROOT, 'src', 'static', 'js', 'idm-pad.js'), encoding='utf-8') as fh:
        pad = fh.read()
    assert "FIELD_CYCLE = ['#ffffff', '#ff0000', '#00ff00', '#0000ff'];" in pad


def test_no_displayed_swap_mode_text_has_a_dash():
    """Plain words: no em or en dash in anything Swap mode shows."""
    files = [('src', 'templates', 'index.html'), ('src', 'templates', 'idm_phone.html'),
             ('src', 'static', 'js', 'app-idm-locator.js'), ('src', 'static', 'js', 'idm-phone.js')]
    for parts in files:
        with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
            for line in fh:
                if 'Swap mode' in line and ("'" in line or '"' in line or '>' in line):
                    assert '—' not in line and '–' not in line, (parts[-1], line)


# ── 2. In the browser ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, served_idm, served_field, marks_of, hl, open_output, pixel,
    wait_pixel, point, open_tab,
)
from test_idm_phone import open_phone, open_swap, close_swap, history_index  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


# Every client log line the page sends, from now on (sendBeacon spied).
LOG_SPY_JS = """() => {
    window.__swLogs = [];
    if (window.__swLogReal) return;
    const real = navigator.sendBeacon.bind(navigator);
    window.__swLogReal = real;
    navigator.sendBeacon = (url, blob) => {
        try {
            blob.text().then(t => {
                try { const p = JSON.parse(t); window.__swLogs.push({action: p.action, details: p.details}); }
                catch (_) { /* not JSON */ }
            });
        } catch (_) { /* not a blob */ }
        return real(url, blob);
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    pg.route('**/api/native-dialog/**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"ok": false, "cancelled": true}'))
    yield pg
    context.close()


def logs(pg, action):
    return pg.evaluate("(a) => (window.__swLogs || []).filter(e => e.action === a).map(e => e.details)", action)


def served_swap(pg):
    return pg.evaluate("async () => (await (await fetch('/api/project')).json()).idmSwap || null")


def swap_of(pg):
    return pg.evaluate("() => window.app._idmSwapNow()")


# IdmA (3 x 2 cabinets of 128, 2 x 2 modules of 64) carries three marks:
#   0,0,0,0  an X       x 0..64,    y 0..64
#   1,0,1,1  a red fill x 192..256, y 64..128
#   2,1,0,0  a red fill x 256..320, y 128..192
MARKS = {'0,0,0,0': {'style': 'x', 'color': '#00ffff'},
         '1,0,1,1': {'style': 'color', 'color': '#ff1a1a'},
         '2,1,0,0': {'style': 'color', 'color': '#ff1a1a'}}
LIT = [(10, 50), (32, 32), (224, 96), (200, 70), (288, 160)]
DARK = [(96, 32), (32, 96), (160, 32), (0, 96), (127, 64), (224, 32), (352, 224), (700, 50), (500, 32)]


def fresh(pg):
    """The tab's show, with Swap mode gone from the server first."""
    pg.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        delete p.idmSwap;
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(p)});
    }""")
    cid = reset_project(pg)
    set_layout(pg, 'IdmA', 2, 2)
    pg.evaluate("""(marks) => {
        const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
        l.idm = {modulesX: 2, modulesY: 2, marks: JSON.parse(JSON.stringify(marks))};
        app.updateLayers([l], true, 'Mark Modules');
        window.canvasRenderer.render();
    }""", MARKS)
    settled(pg, lambda: served_idm(pg, 'IdmA'), lambda v: v and len(v['marks']) == 3)
    return cid


def region_max(out, x, y, w, h):
    """The brightest channel in a rectangle of the output."""
    return out.evaluate("""([x, y, w, h]) => {
        const d = document.getElementById('output-canvas').getContext('2d').getImageData(x, y, w, h).data;
        let m = 0;
        for (let i = 0; i < d.length; i += 4) m = Math.max(m, d[i], d[i + 1], d[i + 2]);
        return m;
    }""", [x, y, w, h])


# A pixel of the designer's own view at a workspace point (one canvas at 0, 0).
VIEW_PX_JS = """([x, y]) => {
    const r = window.canvasRenderer;
    const X = Math.round(Math.round(r.panX) + x * r.zoom), Y = Math.round(Math.round(r.panY) + y * r.zoom);
    return Array.from(r.ctx.getImageData(X, Y, 1, 1).data.slice(0, 3));
}"""


def view_px(pg, x, y):
    return pg.evaluate(VIEW_PX_JS, [x, y])


def wall_is(out, colour):
    for x, y in LIT:
        wait_pixel(out, x, y, colour, tol=0)
    for x, y in DARK:
        wait_pixel(out, x, y, (0, 0, 0), tol=0)


def set_swap_colour(pg, colour):
    """The swatch beside the switch, as the app's colour picker writes it."""
    pg.evaluate("""(c) => { const el = document.getElementById('idm-swap-color');
        el.value = c; el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true})); }""", colour)


def test_swap_mode_lights_only_the_modules_still_to_swap(page):
    cid = fresh(page)
    page.evaluate(LOG_SPY_JS)
    # Module IDs on and a highlight on an unmarked module: both go in Swap mode
    page.evaluate("() => window.app._idmSetField({moduleIds: true})")
    page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmA');
        window.app._idmSetHighlight(l.id, '0,0,1,0'); }""")
    out = open_output(page, cid)
    try:
        # before: the field, the highlight and the labels on the wall
        assert region_max(out, 64, 0, 64, 64) > 200
        assert not page.is_visible('#idm-swap-tag')
        h0 = history_index(page)
        page.click('#idm-swap-mode')
        assert page.get_attribute('#idm-swap-mode', 'aria-pressed') == 'true'
        assert settled(page, lambda: served_swap(page), lambda v: v and v['on']) == {'on': True, 'color': '#ffffff'}
        # one undo step
        assert history_index(page) == h0 + 1
        assert page.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Swap Mode On'
        # the wall: pure black but for the open marks, solid white (the X too)
        wall_is(out, (255, 255, 255))
        # nothing else: the highlighted, labelled module and a whole cabinet
        # with no mark are pure black, edges and all
        assert region_max(out, 64, 0, 64, 64) == 0
        assert region_max(out, 128, 0, 128, 64) == 0
        assert region_max(out, 600, 0, 320, 320) == 0
        # the lit module is lit to its edges, solid
        assert out.evaluate("""() => {
            const d = document.getElementById('output-canvas').getContext('2d').getImageData(192, 64, 64, 64).data;
            for (let i = 0; i < d.length; i += 4) if (d[i] !== 255 || d[i + 1] !== 255 || d[i + 2] !== 255) return false;
            return true;
        }""")
        # the view draws the same: black, the open marks lit, no highlight
        assert view_px(page, 224, 96) == [255, 255, 255]
        assert view_px(page, 96, 32) == [0, 0, 0]
        assert view_px(page, 32, 96) == [0, 0, 0]
        assert page.evaluate("() => window.canvasRenderer.renderIdmHighlight()") is None
        # the tag at the top of the panel says so; a click goes to the switch
        assert page.is_visible('#idm-swap-tag') and page.inner_text('#idm-swap-tag') == 'Swap mode is on'
        page.click('#idm-swap-tag')
        assert settled(page, lambda: page.evaluate("() => document.activeElement && document.activeElement.id"),
                       lambda v: v == 'idm-swap-mode') == 'idm-swap-mode'
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        # the log says what was drawn: Swap mode, its colour, three lit
        view = settled(page, lambda: [d for d in logs(page, 'render_view')
                                      if d.get('view') == 'idm' and d['counts'].get('swapMode') == 'on'],
                       lambda v: len(v) >= 1, 6000)
        assert view and view[-1]['counts']['lit'] == 3 and view[-1]['counts']['swapColor'] == '#ffffff', view
        assert 'Swap mode on, 3 lit in #ffffff' in view[-1]['_msg'], view[-1]
        frame = settled(page, lambda: [d for d in logs(page, 'output_frame') if d.get('swapMode') == 'on'],
                        lambda v: len(v) >= 1, 6000)
        assert frame and frame[-1]['lit'] == 3 and frame[-1]['swapColor'] == '#ffffff', frame
        # the colour: picked on the swatch, one undo step, the wall follows
        h1 = history_index(page)
        set_swap_colour(page, '#00ff00')
        wall_is(out, (0, 255, 0))
        assert settled(page, lambda: served_swap(page), lambda v: v and v['color'] == '#00ff00')['on'] is True
        assert settled(page, lambda: history_index(page), lambda v: v == h1 + 1) == h1 + 1
        assert page.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Swap Mode Color'
        # a tick: that module goes black; an untick lights it again
        page.click('#idm-list .idm-row[data-idm-key="1,0,1,1"] input[data-idm-swap]')
        wait_pixel(out, 224, 96, (0, 0, 0), tol=0)
        wait_pixel(out, 288, 160, (0, 255, 0), tol=0)
        assert '1,0,1,1' not in marks_of(page, 'IdmA')
        assert view_px(page, 224, 96) == [0, 0, 0]
        page.click('#idm-swapped-list .idm-row[data-idm-key="1,0,1,1"] input[data-idm-swap]')
        wait_pixel(out, 224, 96, (0, 255, 0), tol=0)
        assert '1,0,1,1' in marks_of(page, 'IdmA')
        # ... and once more, the next tick goes dark too
        page.click('#idm-list .idm-row[data-idm-key="2,1,0,0"] input[data-idm-swap]')
        wait_pixel(out, 288, 160, (0, 0, 0), tol=0)
        wait_pixel(out, 224, 96, (0, 255, 0), tol=0)
        assert not page._errors, page._errors
    finally:
        out.close()


def test_the_arrows_a_click_and_the_pad_change_nothing_in_swap_mode(page):
    cid = fresh(page)
    page.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'IdmA');
        window.app._idmSetHighlight(l.id, '0,0,1,0'); }""")
    page.click('#idm-swap-mode')
    settled(page, lambda: served_swap(page), lambda v: v and v['on'])
    out = open_output(page, cid)
    try:
        wall_is(out, (255, 255, 255))
        page.evaluate("() => { document.activeElement && document.activeElement.blur();"
                      " const t = document.getElementById('app-toast-host'); if (t) t.innerHTML = ''; }")
        marks = marks_of(page, 'IdmA')
        h0 = history_index(page)
        # the arrow keys, held and tapped, Shift too
        page.mouse.move(5, 5)
        for key in ('ArrowRight', 'ArrowDown', 'Shift+ArrowLeft'):
            page.keyboard.press(key)
        page.keyboard.down('ArrowRight')
        page.wait_for_timeout(600)
        page.keyboard.up('ArrowRight')
        assert hl(page) == ['IdmA', '0,0,1,0']
        said = 'Swap mode is on. Turn it off to move the highlight or mark modules.'
        assert said in settled(page, lambda: page.inner_text('#app-toast-host'), lambda t: said in t, 3000)
        # the pad's arrows, Mark and a press of Space mark or move nothing
        page.click('[data-idm-step="down"]')
        page.click('#idm-pad-mark')
        page.keyboard.press('Space')
        # a click on an unmarked module, and a hover, neither marks nor moves
        pt = point(page, 'IdmA', 1, 0, 0, 0)
        page.mouse.move(pt['x'], pt['y'])
        page.mouse.click(pt['x'], pt['y'])
        page.wait_for_timeout(300)
        assert hl(page) == ['IdmA', '0,0,1,0']
        assert marks_of(page, 'IdmA') == marks
        assert history_index(page) == h0
        # a row of the swap list keeps the highlight where it is too
        page.click('#idm-list .idm-row[data-idm-key="2,1,0,0"] .idm-row-go')
        page.wait_for_timeout(200)
        assert hl(page) == ['IdmA', '0,0,1,0']
        # the wall is as it was: nothing moved on it
        wall_is(out, (255, 255, 255))
        assert region_max(out, 64, 0, 64, 64) == 0
        assert page.evaluate("() => window.app._idmPointerFor('')") is None
        # off again: the highlight is back where it was, and the arrows move it
        page.click('#idm-swap-mode')
        settled(page, lambda: served_swap(page), lambda v: v and not v['on'])
        assert not page.is_visible('#idm-swap-tag')
        assert settled(out, lambda: region_max(out, 64, 0, 64, 64), lambda v: v > 200) > 200
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.mouse.move(5, 5)
        page.keyboard.press('ArrowRight')
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,0,0']) == ['IdmA', '1,0,0,0']
        assert not page._errors, page._errors
    finally:
        out.close()


def test_swap_mode_is_undone_and_redone_and_survives_a_reload(page):
    cid = fresh(page)
    h0 = history_index(page)
    page.click('#idm-swap-mode')
    settled(page, lambda: served_swap(page), lambda v: v and v['on'])
    set_swap_colour(page, '#ff0000')
    settled(page, lambda: served_swap(page), lambda v: v and v['color'] == '#ff0000')
    settled(page, lambda: history_index(page), lambda v: v == h0 + 2)
    out = open_output(page, cid)
    try:
        wall_is(out, (255, 0, 0))
        # undo the colour: white again, on the server too
        page.evaluate("() => window.app.undo()")
        assert swap_of(page) == {'on': True, 'color': '#ffffff'}
        assert settled(page, lambda: served_swap(page), lambda v: v and v['color'] == '#ffffff')['on'] is True
        wall_is(out, (255, 255, 255))
        # undo the switch: the field and the marks are back
        page.evaluate("() => window.app.undo()")
        assert swap_of(page)['on'] is False
        assert settled(page, lambda: served_swap(page), lambda v: not v or not v['on']) in (None, {'on': False, 'color': '#ffffff'})
        wait_pixel(out, 96, 32, (217, 217, 217))
        wait_pixel(out, 224, 96, (255, 26, 26))
        assert page.get_attribute('#idm-swap-mode', 'aria-pressed') == 'false'
        assert not page.is_visible('#idm-swap-tag')
        # redo both
        page.evaluate("() => window.app.redo()")
        settled(page, lambda: served_swap(page), lambda v: v and v['on'])
        wall_is(out, (255, 255, 255))
        assert page.is_visible('#idm-swap-tag')
        page.evaluate("() => window.app.redo()")
        settled(page, lambda: served_swap(page), lambda v: v and v['color'] == '#ff0000')
        wall_is(out, (255, 0, 0))
    finally:
        out.close()
    # a reload keeps it on, in its colour, with the tag
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history"
                           " && window.app.socket && window.app.socket.connected", timeout=15000)
    page.wait_for_timeout(600)
    open_tab(page)
    assert swap_of(page) == {'on': True, 'color': '#ff0000'}
    assert page.is_visible('#idm-swap-tag')
    assert page.get_attribute('#idm-swap-mode', 'aria-pressed') == 'true'
    assert page.input_value('#idm-swap-color') == '#ff0000'
    assert view_px(page, 224, 96) == [255, 0, 0]
    assert view_px(page, 96, 32) == [0, 0, 0]
    # another tab of the app and back: still on
    page.click('.view-tab[data-mode="pixel-map"]')
    page.wait_for_timeout(200)
    open_tab(page)
    assert page.is_visible('#idm-swap-tag')
    page.click('#idm-swap-mode')
    settled(page, lambda: served_swap(page), lambda v: v and not v['on'])
    assert not page._errors, page._errors


def test_an_old_show_with_the_black_field_opens_on_the_default(page):
    cid = fresh(page)
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        p.idmField = {color: '#000000', border: 'lines', moduleIds: false};
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(p)});
        window.app.loadProject();
    }""")
    settled(page, lambda: page.evaluate("() => (window.app.project.idmField || {}).border"), lambda v: v == 'lines')
    assert served_field(page)['color'] == '#ffffff'
    assert page.evaluate("() => window.app._idmFieldNow().color") == '#ffffff'
    assert page.evaluate("() => window.canvasRenderer.idmFieldSpec().color") == '#ffffff'
    # a copy still holding black (a page that never reloaded) draws white too
    page.evaluate("() => { window.app.project.idmField = {color: '#000000', border: 'lines'}; window.canvasRenderer.render(); }")
    assert page.evaluate("() => window.canvasRenderer.idmFieldSpec().color") == '#ffffff'
    page.evaluate("() => window.app._idmSyncField(true)")
    assert page.get_attribute('[data-idm-field="#ffffff"]', 'aria-pressed') == 'true'
    assert page.locator('[data-idm-field="#000000"]').count() == 0
    out = open_output(page, cid)
    try:
        wait_pixel(out, 96, 96, (255, 255, 255))
    finally:
        out.close()
    page.evaluate("() => window.app._idmSetField({color: '#ffffff', border: 'shade'})")
    assert not page._errors, page._errors


def test_the_phone_and_the_computer_follow_each_other(page, e2e_server, pw_browser):
    cid = fresh(page)
    out = open_output(page, cid)
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        # off: no tag on the phone, its arrows free
        assert not ph.is_visible('#ph-swap-tag')
        assert ph.is_enabled('[data-ph-move="up"]')
        # the computer turns it on: the phone's tag shows and its arrows wait
        page.click('#idm-swap-mode')
        settled(ph, lambda: ph.is_visible('#ph-swap-tag'), lambda v: v)
        assert 'Swap mode is on' in ph.inner_text('#ph-swap-tag')
        assert ph.is_disabled('[data-ph-move="up"]') and ph.is_disabled('#ph-mark')
        hl0 = hl(page)
        ph.evaluate("() => window.idmPhone.jobs.move('right', false)")
        assert 'Swap mode is on' in ph.inner_text('#ph-toast')
        assert hl(page) == hl0
        # the tag opens the swap list, where the switch reads On
        ph.tap('#ph-swap-tag')
        ph.wait_for_selector('#ph-swap-sheet', state='visible')
        assert ph.get_attribute('[data-ph-swap="on"]', 'aria-pressed') == 'true'
        # the phone turns it off: the computer, the server and the wall follow,
        # and it is one undo step on the computer
        h0 = history_index(page)
        ph.tap('[data-ph-swap="off"]')
        assert settled(page, lambda: swap_of(page)['on'], lambda v: v is False) is False
        assert settled(page, lambda: history_index(page), lambda v: v == h0 + 1) == h0 + 1
        assert page.get_attribute('#idm-swap-mode', 'aria-pressed') == 'false'
        wait_pixel(out, 96, 32, (217, 217, 217))
        # and on again from the phone
        ph.tap('[data-ph-swap="on"]')
        assert settled(page, lambda: swap_of(page)['on'], lambda v: v is True) is True
        wall_is(out, (255, 255, 255))
        # a color from the chip: the computer's swatch and the wall follow
        ph.tap('#ph-swap-color')
        assert ph.is_visible('#ph-swap-colors')
        ph.tap('[data-ph-swap-color="#ff0000"]')
        assert settled(page, lambda: swap_of(page)['color'], lambda v: v == '#ff0000') == '#ff0000'
        assert settled(page, lambda: page.input_value('#idm-swap-color'), lambda v: v == '#ff0000') == '#ff0000'
        wall_is(out, (255, 0, 0))
        assert not ph.is_visible('#ph-swap-colors')
        assert ph.get_attribute('#ph-swap-color', 'aria-label') == 'Swap mode color: Red'
        # the phone's own Undo takes the color back
        ph.tap('#ph-swap-close')
        ph.wait_for_selector('#ph-swap-sheet', state='hidden')
        ph.tap('#ph-undo')
        assert settled(page, lambda: swap_of(page), lambda v: v['color'] == '#ffffff') == {'on': True, 'color': '#ffffff'}
        assert 'Undone: Swap Mode Color' in ph.inner_text('#ph-toast')
        wall_is(out, (255, 255, 255))
        # closing the swap list left it on; so does the phone's back gesture
        assert served_swap(page)['on'] is True and ph.is_visible('#ph-swap-tag')
        open_swap(ph)
        ph.go_back()
        ph.wait_for_selector('#ph-swap-sheet', state='hidden')
        assert served_swap(page)['on'] is True and ph.is_visible('#ph-swap-tag')
        # a tick on the phone darkens that module on the wall
        open_swap(ph)
        ph.tap('#ph-list .ph-row[data-ph-key="1,0,1,1"] input')
        wait_pixel(out, 224, 96, (0, 0, 0), tol=0)
        wait_pixel(out, 288, 160, (255, 255, 255), tol=0)
        # untick it there: lit again
        ph.tap('#ph-swapped-list .ph-row[data-ph-key="1,0,1,1"] input')
        wait_pixel(out, 224, 96, (255, 255, 255), tol=0)
        # a row tapped moves no highlight
        ph.tap('#ph-list .ph-row[data-ph-key="2,1,0,0"] .ph-row-go')
        page.wait_for_timeout(200)
        assert hl(page) == hl0
        close_swap(ph)
        # the computer turns it off: the phone's tag goes and its arrows are back
        page.click('#idm-swap-mode')
        settled(ph, lambda: ph.is_visible('#ph-swap-tag'), lambda v: not v)
        assert ph.is_enabled('[data-ph-move="up"]') and ph.is_enabled('#ph-mark')
        # a computer undo turns it on again, on the phone too
        page.evaluate("() => window.app.undo()")
        settled(ph, lambda: ph.is_visible('#ph-swap-tag'), lambda v: v)
        page.evaluate("() => window.app.redo()")
        settled(ph, lambda: ph.is_visible('#ph-swap-tag'), lambda v: not v)
        assert not ph._errors, ph._errors
        assert not page._errors, page._errors
    finally:
        ctx.close()
        out.close()


FIT_JS = """() => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const doc = document.documentElement;
    const tag = document.getElementById('ph-swap-tag').getBoundingClientRect();
    const pad = Array.from(document.querySelectorAll('.ph-pad button')).map(b => b.getBoundingClientRect());
    return {scrolls: doc.scrollHeight > vh + 1 || doc.scrollWidth > vw + 1,
            tagIn: tag.top >= 0 && tag.bottom <= vh && tag.height >= 48,
            padIn: pad.every(r => r.bottom <= vh + 0.5 && r.height >= 44)};
}"""


@pytest.mark.parametrize('size', [(390, 844), (375, 667)])
def test_the_phone_tag_fits_the_main_screen(page, e2e_server, pw_browser, size):
    fresh(page)
    page.click('#idm-swap-mode')
    settled(page, lambda: served_swap(page), lambda v: v and v['on'])
    ctx, ph = open_phone(pw_browser, e2e_server, scheme='light', size=size)
    try:
        settled(ph, lambda: ph.is_visible('#ph-swap-tag'), lambda v: v)
        # dark by default, whatever the phone's own setting
        assert ph.evaluate("() => document.documentElement.getAttribute('data-theme')") == 'dark'
        got = ph.evaluate(FIT_JS)
        assert got == {'scrolls': False, 'tagIn': True, 'padIn': True}, got
        open_swap(ph)
        sizes = ph.evaluate("""() => ['[data-ph-swap="off"]', '[data-ph-swap="on"]', '#ph-swap-color'].map(s => {
            const r = document.querySelector(s).getBoundingClientRect(); return [r.width, r.height]; })""")
        assert all(w >= 44 and h >= 44 for w, h in sizes), sizes
        close_swap(ph)
        assert not ph._errors, ph._errors
    finally:
        ctx.close()
        page.click('#idm-swap-mode')
        settled(page, lambda: served_swap(page), lambda v: v and not v['on'])
