"""The IDM Locator from a phone, the swap list, and the controls kept to one
canvas (routes_idm_phone.py, idm-phone.js, idm-core.js, idm-pad.js,
qr-code.js, app-idm-phone.js, app-idm-locator.js, app-idm-gamepad.js).

What this file pins:

* The server: a mark is its style and colour alone, through the layer
  route and both project funnels; a module ticked Swapped is kept apart
  (idm.swapped: the mark as it was and its order number), only on a module
  that is there and never on a marked one, and a show from before it loads
  and saves unchanged; the phone page is served with the
  renderer's geometry and none of the designer; the address route names
  this computer's LAN addresses with the port it was reached on, the one
  a launcher bound to alone, or none (and why) for a server set to this
  computer only; the show route says whether a show is open.
* The QR code: what qr-code.js draws reads back (an independent reader,
  tests/qr_reader.py) as the address, at every length an address takes,
  and the tab's Use a phone dialog, centred in the app's dialog style,
  shows the code of the address it prints, with a note when the computer
  can't be reached. qr-code.js keeps its MIT credit, and
  THIRD-PARTY-NOTICES lists it.
* The phone page: dark unless the phone picked light (kept per device,
  storage blocked or not); the main screen is the controls alone and fills
  390 x 844 and 375 x 667 with no scrolling either way and finger sized
  buttons; the swap list opens as a screen of its own (Back or the
  phone's back gesture returns), and so does the menu (owner, 2026-11-24:
  Next screen, Change canvas and the field colors, none of them on the
  main screen, so nothing that jumps or repaints the wall sits by the
  arrows) and, from the menu, the controller's button list. Its arrows,
  the cabinet step, Mark, Undo, Next screen, the field and the swap list
  reach the tab, the wall output and a second
  phone, through the same routes and rules (a locked screen refuses, each
  change is one undo step on the computer, its own Undo takes back its
  own change); it follows the show live and says so plainly when there is
  no show or no screen.
* The swap list (owner, 2026-11-24, after 2026-11-17's "count down as
  they are checked off"): a Swapped tick, on the tab or on a phone, takes
  that module's mark off the wall live everywhere (the server, the tab, a
  second device, the wall output) and moves its row to the Swapped list
  under the open one, newest first, on every device; the count counts only
  what is left. Unticking a row there, on either device, puts the row back
  on the open list and the mark back on the wall. Each is one undo step on
  the computer, and Undo (or the phone's own Undo) takes it back; a reload
  keeps both lists; a new mark on a swapped module takes it off the
  Swapped list; clearing the marks clears both lists. A row leads with where the
  module is (the cabinet's Col and Row in its screen, then the module's
  place in words), counted from the top-left of the side Front / Back
  picks, on 1 x 1 to 3 x 3, 4 x 4 and half cabinets; the Cabinet ID and
  Module ID follow, the same from either side. The phone's readout reads
  the same way. Nothing of it prints in the binder or any export.
* Rows from (owner, 2026-11-24): each screen's heading on both lists, on
  the tab and the phone, has a Top / Bottom switch; Bottom counts its
  cabinet rows up from the bottom (and, past 3 x 3, a module's row in its
  cabinet too), the words never change. A screen with a footer starts on
  Bottom, a header or neither on Top. A pick is that screen's, kept with
  the show (the field's rowsFrom): live on every device, through a reload,
  never an undo step; the phone's readout and its counting line follow.
* Holding an arrow on the phone (owner, 2026-11-24) repeats the step,
  faster the longer it is held, and stops the moment the finger lifts, the
  touch is cancelled or the page loses focus; a tap is one step; the
  highlight goes to the computer at most every 40 ms however fast it
  moves.
* The canvas: a game controller (on the computer and on the phone) and
  the phone's buttons step and go to the next screen only on the canvas
  the highlight is on; View / Share (the phone's Next canvas) goes to the
  next canvas. The keyboard's arrows are unchanged.

Run locally:
    python -m pytest tests/test_idm_phone.py -n 4 --dist loadfile --browser chromium
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

from conftest import settled  # noqa: E402
import app as app_module  # noqa: E402
import qr_reader  # noqa: E402


# ── 1. The server (no browser) ────────────────────────────────────────────

def _layer(client, **extra):
    body = {'name': 'Sw', 'columns': 2, 'rows': 1, 'cabinet_width': 128, 'cabinet_height': 128}
    body.update(extra)
    return client.post('/api/layer/add', json=body).get_json()


def test_a_mark_is_its_style_and_colour_alone(client):
    """No mark carries anything but its style and colour; a key left by an
    earlier build is dropped."""
    layer = {'type': 'screen', 'columns': 2, 'rows': 1, 'cabinet_width': 128, 'cabinet_height': 128,
             'panels': [{'id': 1, 'row': 0, 'col': 0, 'x': 0, 'y': 0, 'width': 128, 'height': 128},
                        {'id': 2, 'row': 0, 'col': 1, 'x': 128, 'y': 0, 'width': 128, 'height': 128}]}
    got = app_module.sanitize_idm({'modulesX': 2, 'modulesY': 2, 'marks': {
        '0,0,0,0': {'style': 'color', 'color': '#ff0000', 'swapped': True},
        '1,0,1,1': {'style': 'x', 'color': '#00ff00', 'swapped': False},
    }}, layer)
    assert got['marks'] == {'0,0,0,0': {'style': 'color', 'color': '#ff0000'},
                            '1,0,1,1': {'style': 'x', 'color': '#00ff00'}}, got
    assert app_module.sanitize_idm(got, layer) == got      # idempotent
    lay = _layer(client)
    idm = {'modulesX': 2, 'modulesY': 2, 'marks': {'1,0,1,1': {'style': 'color', 'color': '#ff1a1a', 'swapped': True}}}
    saved = client.put(f"/api/layer/{lay['id']}", json={'idm': idm}).get_json()
    assert saved['idm']['marks'] == {'1,0,1,1': {'style': 'color', 'color': '#ff1a1a'}}
    project = client.get('/api/project').get_json()
    mine = next(x for x in project['layers'] if x['id'] == lay['id'])
    mine['idm'] = idm
    assert client.post('/api/project', json=project).status_code == 200
    restored = client.put('/api/project', json=project).get_json()
    mine = next(x for x in restored['layers'] if x['id'] == lay['id'])
    assert mine['idm']['marks'] == {'1,0,1,1': {'style': 'color', 'color': '#ff1a1a'}}


def test_the_swapped_list_is_kept_apart_and_old_shows_are_unchanged(client):
    """Owner, 2026-11-24: a module ticked Swapped is kept under idm.swapped
    with its mark's style and colour and its order number, so the Swapped
    list runs newest first and an untick puts the mark back. Only modules
    that are there, never one that is marked (the mark wins), the order a
    whole number from 1; no key when nothing is swapped, so a show from
    before it is the same after a load and a save."""
    layer = {'type': 'screen', 'columns': 2, 'rows': 1, 'cabinet_width': 128, 'cabinet_height': 128,
             'panels': [{'id': 1, 'row': 0, 'col': 0, 'x': 0, 'y': 0, 'width': 128, 'height': 128},
                        {'id': 2, 'row': 0, 'col': 1, 'x': 128, 'y': 0, 'width': 128, 'height': 128}]}
    got = app_module.sanitize_idm({'modulesX': 2, 'modulesY': 2,
                                   'marks': {'0,0,0,0': {'style': 'color', 'color': '#ff0000'}},
                                   'swapped': {
                                       '1,0,1,1': {'style': 'x', 'color': '#00FF00', 'n': 3, 'extra': 1},
                                       '0,0,1,0': {'style': 'color', 'color': 'nope', 'n': 'x'},
                                       '0,0,0,0': {'style': 'color', 'color': '#ff0000', 'n': 4},
                                       '5,0,0,0': {'style': 'color', 'color': '#ff0000', 'n': 5},
                                       '1,0,0,1': {'style': 'color', 'color': '#ff0000', 'n': True},
                                   }}, layer)
    assert got == {'modulesX': 2, 'modulesY': 2,
                   'marks': {'0,0,0,0': {'style': 'color', 'color': '#ff0000'}},
                   'swapped': {'1,0,1,1': {'style': 'x', 'color': '#00ff00', 'n': 3},
                               '0,0,1,0': {'style': 'color', 'color': '#ff1a1a', 'n': 1},
                               '1,0,0,1': {'style': 'color', 'color': '#ff0000', 'n': 1}}}, got
    assert app_module.sanitize_idm(got, layer) == got      # idempotent
    # nothing swapped: no key at all
    assert 'swapped' not in app_module.sanitize_idm({'modulesX': 2, 'modulesY': 2, 'marks': {}, 'swapped': {}}, layer)
    # a module count that loses the module drops its entry
    assert 'swapped' not in app_module.sanitize_idm(dict(got, modulesX=1, modulesY=1), layer)
    # through the layer route and both project funnels
    lay = _layer(client)
    idm = {'modulesX': 2, 'modulesY': 2, 'marks': {}, 'swapped': {'1,0,1,1': {'style': 'color', 'color': '#ff1a1a', 'n': 2}}}
    saved = client.put(f"/api/layer/{lay['id']}", json={'idm': idm}).get_json()
    assert saved['idm'] == idm, saved['idm']
    project = client.get('/api/project').get_json()
    mine = next(x for x in project['layers'] if x['id'] == lay['id'])
    assert mine['idm'] == idm
    assert client.post('/api/project', json=project).status_code == 200
    restored = client.put('/api/project', json=project).get_json()
    assert next(x for x in restored['layers'] if x['id'] == lay['id'])['idm'] == idm
    # an old show's block (no swapped key) loads exactly as it was
    old = {'modulesX': 2, 'modulesY': 2, 'marks': {'0,0,1,1': {'style': 'x', 'color': '#ff1a1a'}}}
    mine['idm'] = old
    restored = client.put('/api/project', json=project).get_json()
    assert next(x for x in restored['layers'] if x['id'] == lay['id'])['idm'] == old
    # a copy of the screen starts with neither list
    copy = {'type': 'screen', 'idm': dict(idm, marks={'0,0,0,0': {'style': 'color', 'color': '#ff1a1a'}})}
    app_module.strip_copied_idm_marks(copy)
    assert copy['idm'] == {'modulesX': 2, 'modulesY': 2, 'marks': {}}


def test_rows_from_picks_are_kept_in_the_field(client):
    """The field's rowsFrom: a screen id (a whole number, as text) to 'top'
    or 'bottom', junk dropped, no key when empty; through the route."""
    clean = app_module.sanitize_idm_field({'rowsFrom': {'3': 'bottom', 12: 'top', ' 7 ': 'bottom', 'x': 'top',
                                                        '4': 'up', '-1': 'top', '\u00b2': 'top'}})
    assert clean['rowsFrom'] == {'3': 'bottom', '12': 'top', '7': 'bottom'}, clean
    assert app_module.sanitize_idm_field(clean) == clean
    assert 'rowsFrom' not in app_module.sanitize_idm_field({'rowsFrom': {}})
    assert 'rowsFrom' not in app_module.sanitize_idm_field({'rowsFrom': ['top']})
    resp = client.put('/api/project/idm-field', json={'field': {'color': '#ffffff', 'rowsFrom': {'5': 'bottom'}}})
    assert resp.status_code == 200
    assert client.get('/api/project').get_json()['idmField']['rowsFrom'] == {'5': 'bottom'}
    client.put('/api/project/idm-field', json={'field': {'color': '#ffffff'}})


def test_the_phone_page_is_served_without_the_designer(client):
    resp = client.get('/idm-phone')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for src in ('/static/js/socket.io.min.js', '/static/js/canvas.js', '/static/js/canvas-labels.js',
                '/static/js/canvas-idm.js', '/static/js/idm-phone.js'):
        assert src in html, src
    assert 'main.js' not in html and 'app-core.js' not in html
    assert 'name="viewport"' in html
    # dark unless this phone picked light, whatever the phone's own setting
    assert 'prefers-color-scheme' not in html
    assert ":root, :root[data-theme=\"dark\"]" in html and "localStorage.getItem('lrdIdmPhoneTheme') === 'light'" in html
    # the page's own script loads only the shared rules, never the designer
    with open(os.path.join(ROOT, 'src', 'static', 'js', 'idm-phone.js'), encoding='utf-8') as fh:
        imports = re.findall(r"from '\./([\w.-]+)'", fh.read())
    assert sorted(set(imports)) == ['idm-core.js', 'idm-pad.js'], imports


def test_the_address_route_names_the_lan_addresses_and_why_none(client, monkeypatch):
    import routes_idm_phone as rp
    monkeypatch.setattr(rp, '_lan_addresses', lambda: ['192.168.1.20', '10.0.0.7'])
    monkeypatch.setattr(app_module, 'BOUND_HOST', '0.0.0.0', raising=False)
    got = client.get('/api/idm-phone/address', environ_overrides={'SERVER_PORT': '8050'}).get_json()
    assert got['reachable'] is True and got['why'] == ''
    assert got['addresses'] == ['192.168.1.20', '10.0.0.7']
    assert got['urls'] == ['http://192.168.1.20:8050/idm-phone', 'http://10.0.0.7:8050/idm-phone']
    # a launcher bound to one network's address: that address only
    monkeypatch.setattr(app_module, 'BOUND_HOST', '10.0.0.7', raising=False)
    got = client.get('/api/idm-phone/address', environ_overrides={'SERVER_PORT': '9001'}).get_json()
    assert got['urls'] == ['http://10.0.0.7:9001/idm-phone']
    # set to this computer only (the launcher's default): no phone can reach it
    monkeypatch.setattr(app_module, 'BOUND_HOST', '127.0.0.1', raising=False)
    got = client.get('/api/idm-phone/address').get_json()
    assert got == dict(got, reachable=False, why='local-only', addresses=[], urls=[])
    # no network at all
    monkeypatch.setattr(app_module, 'BOUND_HOST', None, raising=False)
    monkeypatch.setattr(rp, '_lan_addresses', lambda: [])
    got = client.get('/api/idm-phone/address').get_json()
    assert got['reachable'] is False and got['why'] == 'no-network'


def test_lan_addresses_skip_loopback_and_link_local():
    import routes_idm_phone as rp
    assert rp._usable('192.168.1.20') and rp._usable('10.1.2.3')
    for ip in ('127.0.0.1', '169.254.10.2', '0.0.0.0', 'nope', '::1'):
        assert not rp._usable(ip), ip
    for ip in rp._lan_addresses():
        assert rp._usable(ip), ip


def test_the_show_route_says_whether_a_show_is_open(client, monkeypatch):
    import routes_project
    monkeypatch.setattr(routes_project, 'launch_settled', lambda: False)
    app_module.current_project['is_pristine'] = True
    assert client.get('/api/idm-phone/show').get_json()['open'] is False
    app_module.current_project['is_pristine'] = False
    assert client.get('/api/idm-phone/show').get_json()['open'] is True
    monkeypatch.setattr(routes_project, 'launch_settled', lambda: True)
    app_module.current_project['is_pristine'] = True
    assert client.get('/api/idm-phone/show').get_json()['open'] is True
    app_module.current_project['is_pristine'] = False


def test_nothing_of_the_swap_list_prints_or_exports():
    """The binder and the exports never read the marks or their ticks."""
    js = os.path.join(ROOT, 'src', 'static', 'js')
    names = [n for n in os.listdir(js) if n.startswith(('app-binder', 'app-export', 'app-pull', 'app-obj'))]
    assert names
    # a layer's idm block, a mark's tick, the list's rows
    reads = re.compile(r"\.idm\b|\bidm\.|\.swapped\b|'swapped'|idmMarkGroups|idm-core")
    for n in names:
        with open(os.path.join(js, n), encoding='utf-8') as fh:
            text = fh.read()
        assert not reads.search(text), (n, reads.search(text).group(0))
    for n in ('routes_export.py', 'pull_sheet.py', 'routes_pull_sheet.py', 'resolume_geometry.py', 'scr_project.py'):
        with open(os.path.join(ROOT, 'src', n), encoding='utf-8') as fh:
            text = fh.read()
        assert not reads.search(text), (n, reads.search(text).group(0))


def test_the_qr_encoder_is_credited_in_the_notices():
    """qr-code.js follows an MIT-licensed library in part: its header keeps
    the copyright line and the permission notice, and THIRD-PARTY-NOTICES
    (built by scripts/build_third_party_notices.py) lists it."""
    with open(os.path.join(ROOT, 'src', 'static', 'js', 'qr-code.js'), encoding='utf-8') as fh:
        head = fh.read(4000)
    assert 'Copyright (c) Project Nayuki.' in head
    assert 'The above copyright notice and this permission notice shall be' in head
    with open(os.path.join(ROOT, 'THIRD-PARTY-NOTICES'), encoding='utf-8') as fh:
        notices = fh.read()
    block = notices[notices.index('(src/static/js/qr-code.js)'):][:400]
    assert 'Copyright (c) Project Nayuki.' in block and 'License: MIT' in block, block


# ── 2. In the browser ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, served_idm, marks_of, hl, served_field, open_output, pixel,
    wait_layers, open_tab,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    pg.route('**/api/native-dialog/**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"ok": false, "cancelled": true}'))
    yield pg
    context.close()


def open_phone(pw_browser, base, scheme='light', size=(390, 844)):
    context = pw_browser.new_context(viewport={'width': size[0], 'height': size[1]}, is_mobile=True,
                                     has_touch=True, device_scale_factor=2, color_scheme=scheme)
    ph = context.new_page()
    ph._errors = []
    ph.on('pageerror', lambda err: ph._errors.append(str(err)))
    ph.goto(base.rstrip('/') + '/idm-phone', wait_until='domcontentloaded')
    ph.wait_for_function("() => window.idmPhone && window.idmPhone.S.connected && window.idmPhone.app.project",
                         timeout=15000)
    return context, ph


def phone_hl(ph):
    return ph.evaluate("""() => {
        const p = window.idmPhone.app.project, h = p && p.idmHighlight;
        if (!h) return null;
        const l = p.layers.find(x => x.id === h.layerId);
        return [l ? l.name : null, h.key];
    }""")


def phone_rows(ph):
    return ph.evaluate("""() => Array.from(document.querySelectorAll('#ph-list .ph-row')).map(r => ({
        key: r.dataset.phKey, text: r.querySelector('.ph-row-text').firstChild.textContent,
        where: r.querySelector('.ph-row-where').textContent,
        ticked: r.querySelector('input').checked}))""")


def tab_rows(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#idm-list .idm-row')).map(r => ({
        key: r.dataset.idmKey, text: r.querySelector('.idm-row-text').textContent,
        ids: r.querySelector('.idm-row-id').textContent,
        ticked: r.querySelector('input[data-idm-swap]').checked}))""")


def history_index(pg):
    return pg.evaluate("() => window.app.historyIndex")


def toast_text(ph):
    return ph.inner_text('#ph-toast')


def open_swap(ph):
    """The swap list's own screen, from the header's button."""
    ph.tap('#ph-swap-open')
    ph.wait_for_selector('#ph-swap-sheet', state='visible')


def close_swap(ph):
    ph.tap('#ph-swap-close')
    ph.wait_for_selector('#ph-swap-sheet', state='hidden')


def open_menu(ph):
    """The menu's own screen, from the header's button."""
    ph.tap('#ph-menu-open')
    ph.wait_for_selector('#ph-menu-sheet', state='visible')


def close_menu(ph):
    ph.tap('#ph-menu-close')
    ph.wait_for_selector('#ph-menu-sheet', state='hidden')


def test_the_phone_page_fits_a_phone_and_drives_the_wall(page, e2e_server, pw_browser):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    c1, ph = open_phone(pw_browser, e2e_server)
    c2, ph2 = open_phone(pw_browser, e2e_server)
    try:
        assert ph.is_visible('#ph-controls') and not ph.is_visible('#ph-message')
        assert ph.inner_text('#ph-place') == 'No module highlighted'
        # the first arrow starts on the first module, the next steps one module
        ph.tap('[data-ph-move="down"]')
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,0,0']) == ['IdmA', '0,0,0,0']
        ph.tap('[data-ph-move="right"]')
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,0,1,0']) == ['IdmA', '0,0,1,0']
        # where it is first, then the screen and the IDs
        assert ph.inner_text('#ph-place') == 'Col 1, Row 1 · Top right module'
        assert ph.inner_text('#ph-ids') == 'IdmA · Cabinet A1 · Module B1'
        # one cabinet a step
        ph.tap('[data-ph-step="cabinet"]')
        ph.tap('[data-ph-move="down"]')
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmA', '0,1,1,0']) == ['IdmA', '0,1,1,0']
        ph.tap('[data-ph-step="module"]')
        # the second phone follows
        assert settled(ph2, lambda: phone_hl(ph2), lambda v: v == ['IdmA', '0,1,1,0']) == ['IdmA', '0,1,1,0']
        assert ph2.inner_text('#ph-place') == 'Col 1, Row 2 · Top right module'
        assert ph2.inner_text('#ph-ids') == 'IdmA · Cabinet A2 · Module B1'
        # the wall output outlines it, steadily: cabinet (0,1) module (1,0)
        # is x 64..128, y 128..192, a black band at its left edge, on it
        settled(out, lambda: pixel(out, 66, 160), lambda v: v == [0, 0, 0])
        seen = set()
        for _ in range(12):
            seen.add((tuple(pixel(out, 66, 160) or ()), tuple(pixel(out, 96, 160) or ())))
            out.wait_for_timeout(80)
        assert len(seen) == 1, seen
        edge, middle = seen.pop()
        assert edge == (0, 0, 0) and middle != (0, 0, 0), (edge, middle)
        # the tab moves it: the phones follow
        page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
            window.app._idmSetHighlight(a.id, '1,0,0,1'); }""")
        assert settled(ph, lambda: phone_hl(ph), lambda v: v == ['IdmA', '1,0,0,1']) == ['IdmA', '1,0,0,1']
        # Mark: the module is marked on the server, on the tab, on the other phone
        h0 = history_index(page)
        ph.tap('#ph-mark')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,0,1' in v['marks'])
        assert got['marks']['1,0,0,1'] == {'style': 'color', 'color': '#ff1a1a'}, got
        settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,0,0,1' in v)
        # one undo step on the computer
        assert settled(page, lambda: history_index(page), lambda v: v == h0 + 1) == h0 + 1
        assert settled(ph2, lambda: [r['key'] for r in phone_rows(ph2)], lambda v: v == ['1,0,0,1']) == ['1,0,0,1']
        assert ph.inner_text('#ph-state') == 'Marked'
        assert ph.inner_text('#ph-mark') == 'Clear mark'
        # the wall shows the mark (red) in the middle of the highlighted module
        settled(out, lambda: pixel(out, 160, 96), lambda v: v and v[0] > 200 and v[1] < 60 and v[2] < 60)
        # the phone's own Undo takes it back
        ph.tap('#ph-undo')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
        assert got['marks'] == {}, got
        assert 'Undone: Mark Module' in toast_text(ph)
        # a mark from the phone undone on the computer
        ph.tap('#ph-mark')
        settled(page, lambda: marks_of(page, 'IdmA'), lambda v: '1,0,0,1' in v)
        page.evaluate("() => window.app.undo()")
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
        assert got['marks'] == {}, got
        settled(ph, lambda: phone_rows(ph), lambda v: v == [])
        # then the phone's Undo leaves the screen alone: it changed elsewhere
        ph.tap('#ph-undo')
        assert 'changed on another device' in toast_text(ph)
        # the field from the phone's menu reaches the server and the tab
        open_menu(ph)
        ph.tap('[data-ph-field="#00ff00"]')
        assert settled(page, lambda: (served_field(page) or {}).get('color'), lambda v: v == '#00ff00') == '#00ff00'
        settled(page, lambda: page.evaluate("() => window.app._idmFieldNow().color"), lambda v: v == '#00ff00')
        assert settled(ph2, lambda: ph2.get_attribute('[data-ph-field="#00ff00"]', 'aria-pressed'),
                       lambda v: v == 'true') == 'true'
        close_menu(ph)
        # Clear highlight
        ph.tap('#ph-clear')
        assert settled(page, lambda: hl(page), lambda v: v is None) is None
        assert not ph._errors and not ph2._errors, (ph._errors, ph2._errors)
    finally:
        page.evaluate("() => window.app._idmSetField({color: '#ffffff'})")
        c1.close()
        c2.close()
        out.close()


FIT_JS = """() => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const doc = document.documentElement;
    const out = {vw, vh, scrollW: doc.scrollWidth, scrollH: doc.scrollHeight, outside: [], small: [], pad: []};
    document.querySelectorAll('#ph-controls button, .ph-top button').forEach(b => {
        if (!b.offsetParent) return;
        const r = b.getBoundingClientRect();
        const name = (b.getAttribute('aria-label') || b.textContent).trim();
        if (r.left < 0 || r.top < 0 || r.right > vw + 0.5 || r.bottom > vh + 0.5) out.outside.push(name);
        if (r.height < 44 || r.width < 44) out.small.push([name, Math.round(r.width), Math.round(r.height)]);
    });
    document.querySelectorAll('.ph-pad button').forEach(b => {
        const r = b.getBoundingClientRect();
        out.pad.push([Math.round(r.width), Math.round(r.height)]);
    });
    return out;
}"""


@pytest.mark.parametrize('size', [(390, 844), (375, 667)])
def test_the_main_screen_fills_a_phone_in_dark_with_the_swap_list_on_its_own(page, e2e_server, pw_browser, size):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    put_marks(page, 'IdmA', 2, 2, ['0,0,0,0', '1,0,1,1'])
    # the phone itself set to light: the page is dark all the same
    ctx, ph = open_phone(pw_browser, e2e_server, scheme='light', size=size)
    try:
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'dark'
        assert ph.evaluate("() => getComputedStyle(document.body).backgroundColor") == 'rgb(21, 22, 24)'
        ph.tap('[data-ph-move="right"]')
        settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')
        ph.wait_for_timeout(200)
        fit = ph.evaluate(FIT_JS)
        # no scrolling either way, every control on the screen, finger sized
        assert fit['scrollH'] <= fit['vh'] and fit['scrollW'] <= fit['vw'], fit
        assert fit['outside'] == [] and fit['small'] == [], fit
        # the arrows and Mark take the room the rest leaves
        assert len(fit['pad']) == 5 and all(w >= 100 and h >= 80 for w, h in fit['pad']), fit
        # the canvas control is in the menu, naming the canvas
        assert not ph.is_visible('#ph-canvas-next')
        open_menu(ph)
        assert ph.is_visible('#ph-canvas-next') and ph.inner_text('#ph-canvas-name')
        close_menu(ph)
        # the swap list is not on the main screen; its button counts the marks
        assert not ph.is_visible('#ph-list')
        assert ph.inner_text('#ph-swap-open') == 'Swap list (2)'
        open_swap(ph)
        sheet = ph.evaluate("""() => { const r = document.getElementById('ph-swap-sheet').getBoundingClientRect();
            return [r.left, r.top, r.width, r.height, window.innerWidth, window.innerHeight]; }""")
        assert sheet[:2] == [0, 0] and sheet[2] == sheet[4] and sheet[3] == sheet[5], sheet
        assert ph.get_attribute('#ph-app', 'aria-hidden') == 'true'
        assert len(phone_rows(ph)) == 2
        rows = ph.evaluate("""() => Array.from(document.querySelectorAll('#ph-list .ph-row'))
            .map(r => Math.round(r.getBoundingClientRect().height))""")
        assert all(h >= 56 for h in rows), rows
        assert ph.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        close_swap(ph)
        assert ph.get_attribute('#ph-app', 'aria-hidden') is None
        # the phone's own back gesture closes it too
        open_swap(ph)
        ph.go_back()
        ph.wait_for_selector('#ph-swap-sheet', state='hidden')
        assert ph.is_visible('#ph-controls') and ph.url.endswith('/idm-phone')
        # light if picked, kept on this phone through a reload
        ph.tap('#ph-theme')
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'light'
        assert ph.evaluate("() => getComputedStyle(document.body).backgroundColor") == 'rgb(244, 244, 245)'
        ph.reload(wait_until='domcontentloaded')
        ph.wait_for_function("() => window.idmPhone && window.idmPhone.S.connected", timeout=15000)
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'light'
        ph.tap('#ph-theme')
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'dark'
        assert ph.evaluate("() => localStorage.getItem('lrdIdmPhoneTheme')") == 'dark'
        assert not ph._errors, ph._errors
    finally:
        ctx.close()


MENU_JS = """() => {
    const inside = (sel, host) => !!document.querySelector(host + ' ' + sel);
    const jumps = ['#ph-next-screen', '#ph-canvas-next', '[data-ph-field]'];
    const box = (el) => { const r = el.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
    return {
        main: jumps.filter(sel => inside(sel, '#ph-app')),
        menu: jumps.filter(sel => inside(sel, '#ph-menu-sheet')),
        colors: Array.from(document.querySelectorAll('#ph-menu-sheet [data-ph-field]')).map(b => b.getAttribute('aria-label')),
        mainButtons: Array.from(document.querySelectorAll('#ph-controls button')).map(b => (b.getAttribute('aria-label') || b.textContent).trim()),
        top: Array.from(document.querySelectorAll('.ph-top button')).filter(b => !b.hidden).map(b => b.id),
        pad: Array.from(document.querySelectorAll('.ph-pad button')).map(box),
    };
}"""


def test_the_menu_holds_what_jumps_or_repaints_the_wall(page, e2e_server, pw_browser):
    """Owner, 2026-11-24: the main screen keeps the step switch, the
    arrows, Mark, Undo and Clear highlight; Next screen, Change canvas and
    the field colors (Black among them) move to a menu opened from the top
    bar beside Swap list, so a thumb on the arrows never hits them, and the
    room they leave goes to the arrows and Mark."""
    two_canvases(page)
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        got = ph.evaluate(MENU_JS)
        assert got['main'] == [] and got['menu'] == ['#ph-next-screen', '#ph-canvas-next', '[data-ph-field]'], got
        assert got['colors'] == ['White', 'Red', 'Green', 'Blue', 'Black'], got
        assert got['mainButtons'] == ['One module', 'One cabinet', 'Up', 'Left', 'Mark', 'Right', 'Down',
                                      'Undo', 'Clear highlight'], got
        # Menu sits beside Swap list in the top bar
        assert got['top'][-2:] == ['ph-menu-open', 'ph-swap-open'], got
        assert ph.inner_text('#ph-menu-open') == 'Menu'
        # the arrows and Mark are bigger than the 1.7.0 betas' (about 120 x 96)
        assert len(got['pad']) == 5 and all(w >= 110 and h >= 120 for w, h in got['pad']), got
        assert not ph.is_visible('#ph-menu-sheet')
        open_menu(ph)
        assert ph.get_attribute('#ph-app', 'aria-hidden') == 'true'
        assert ph.inner_text('#ph-menu-where') == 'No module highlighted'
        # each control in the menu is finger sized and works from there
        sizes = ph.evaluate("""() => Array.from(document.querySelectorAll('#ph-menu-sheet button'))
            .filter(b => b.offsetParent).map(b => { const r = b.getBoundingClientRect(); return [b.id || b.getAttribute('aria-label'), r.width, r.height]; })""")
        assert all(w >= 44 and h >= 44 for _, w, h in sizes), sizes
        ph.tap('#ph-next-screen')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')[0] == 'IdmA'
        assert settled(ph, lambda: ph.inner_text('#ph-menu-where'), lambda v: 'IdmA' in v)\
            == 'Highlight on IdmA · Col 1, Row 1 · Whole cabinet'
        assert ph.inner_text('#ph-canvas-name') == 'Main'
        ph.tap('#ph-canvas-next')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmC') == ['IdmC', '0,0,0,0']
        assert settled(ph, lambda: ph.inner_text('#ph-canvas-name'), lambda v: v == 'Side') == 'Side'
        ph.tap('[data-ph-field="#000000"]')
        assert settled(page, lambda: (served_field(page) or {}).get('color'), lambda v: v == '#000000') == '#000000'
        assert ph.get_attribute('[data-ph-field="#000000"]', 'aria-pressed') == 'true'
        # Back returns to the controls; so does the phone's back gesture
        close_menu(ph)
        assert ph.is_visible('#ph-controls') and ph.get_attribute('#ph-app', 'aria-hidden') is None
        open_menu(ph)
        ph.go_back()
        ph.wait_for_selector('#ph-menu-sheet', state='hidden')
        assert ph.is_visible('#ph-controls') and ph.url.endswith('/idm-phone')
        # one canvas: Change canvas only names it
        reset_project(page)
        set_layout(page, 'IdmA', 2, 2)
        settled(ph, lambda: ph.evaluate("() => window.idmPhone.app.project.layers.length"), lambda v: v == 1)
        open_menu(ph)
        assert settled(ph, lambda: ph.is_enabled('#ph-canvas-next'), lambda v: v is False) is False
        assert ph.is_visible('#ph-canvas-one')
        # a message (no show reachable) closes the menu with the controls
        ph.evaluate("() => window.idmPhone.socket().disconnect()")
        ph.wait_for_selector('#ph-menu-sheet', state='hidden')
        assert not ph.is_visible('#ph-menu-open')
        ph.evaluate("() => window.idmPhone.socket().connect()")
        settled(ph, lambda: ph.is_visible('#ph-menu-open'), lambda v: v, 10000)
        assert not ph._errors, ph._errors
    finally:
        page.evaluate("() => window.app._idmSetField({color: '#ffffff'})")
        ctx.close()


def test_the_phone_page_is_dark_with_no_storage(e2e_server, pw_browser):
    """A phone that blocks storage (a private tab): dark, and the switch
    still works for the visit."""
    context = pw_browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                                     color_scheme='light')
    context.add_init_script("""Object.defineProperty(window, 'localStorage', {configurable: true,
        get() { throw new Error('storage blocked'); }});""")
    ph = context.new_page()
    errors = []
    ph.on('pageerror', lambda err: errors.append(str(err)))
    try:
        ph.goto(e2e_server.rstrip('/') + '/idm-phone', wait_until='domcontentloaded')
        ph.wait_for_function("() => window.idmPhone && window.idmPhone.S.connected", timeout=15000)
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'dark'
        ph.tap('#ph-theme')
        assert ph.evaluate("() => document.documentElement.dataset.theme") == 'light'
        assert errors == [], errors
    finally:
        context.close()


def test_a_locked_screen_refuses_the_phone(page, e2e_server, pw_browser):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        a.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#ff1a1a'}}};
        a.locked = true; app.updateLayers([a], true, 'Lock'); app._idmSetHighlight(a.id, '0,0,1,0'); }""")
    settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,0,0,0' in v['marks'])
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        settled(ph, lambda: ph.evaluate("() => window.idmPhone.app.project.layers.find(x => x.name === 'IdmA').locked"),
                lambda v: v is True)
        ph.tap('#ph-mark')
        assert 'IdmA is locked. Unlock it to change it.' in toast_text(ph)
        open_swap(ph)
        ph.tap('#ph-list .ph-swap input')
        ph.wait_for_timeout(300)
        assert served_idm(page, 'IdmA')['marks'] == {'0,0,0,0': {'style': 'color', 'color': '#ff1a1a'}}
        assert phone_rows(ph)[0]['ticked'] is False
    finally:
        page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
            a.locked = false; app.updateLayers([a], true, 'Unlock'); }""")
        ctx.close()


def test_the_phone_follows_the_show_and_says_when_there_is_none(page, e2e_server, pw_browser):
    reset_project(page)
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        assert ph.is_visible('#ph-controls')
        # every screen hidden: nothing to step through
        page.evaluate("""() => { const app = window.app;
            app.project.layers.forEach(l => { l.visible = false; });
            app.updateLayers(app.project.layers, true, 'Hide'); }""")
        msg = settled(ph, lambda: ph.inner_text('#ph-message') if ph.is_visible('#ph-message') else '',
                      lambda v: 'No screen is shown' in v)
        assert 'No screen is shown on the wall' in msg, msg
        assert not ph.is_visible('#ph-controls')
        # every screen gone
        page.evaluate("""async () => {
            for (const l of window.app.project.layers.slice()) await fetch('/api/layer/' + l.id, {method: 'DELETE'});
        }""")
        msg = settled(ph, lambda: ph.inner_text('#ph-message'), lambda v: 'no screens yet' in v)
        assert 'This show has no screens yet' in msg, msg
        # a new show replaces it: the phone follows
        reset_project(page)
        settled(ph, lambda: ph.is_visible('#ph-controls'), lambda v: v)
        assert ph.inner_text('#ph-place') == 'No module highlighted'
        # the computer gone: said plainly; back, it carries on
        ph.evaluate("() => window.idmPhone.socket().disconnect()")
        msg = settled(ph, lambda: ph.inner_text('#ph-message') if ph.is_visible('#ph-message') else '',
                      lambda v: 'Not connected' in v)
        assert 'Not connected to the computer' in msg, msg
        assert ph.inner_text('#ph-conn') == 'Not connected'
        ph.evaluate("() => window.idmPhone.socket().connect()")
        settled(ph, lambda: ph.is_visible('#ph-controls'), lambda v: v, 10000)
        assert not ph._errors, ph._errors
    finally:
        ctx.close()


def swapped_tab(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#idm-swapped-list .idm-row')).map(r => ({
        key: r.dataset.idmKey, text: r.querySelector('.idm-row-text').textContent,
        ticked: r.querySelector('input[data-idm-swap]').checked}))""")


def swapped_phone(ph):
    return ph.evaluate("""() => Array.from(document.querySelectorAll('#ph-swapped-list .ph-row')).map(r => ({
        key: r.dataset.phKey, text: r.querySelector('.ph-row-text').firstChild.textContent,
        ticked: r.querySelector('input').checked}))""")


def keys(rows):
    return [r['key'] for r in rows]


def test_a_swapped_tick_moves_the_row_and_an_untick_puts_it_back(page, e2e_server, pw_browser):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    page.evaluate("""() => { const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
        a.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#ff1a1a'},
                                                  '1,0,1,1': {style: 'color', color: '#ff1a1a'},
                                                  '2,1,0,0': {style: 'x', color: '#00ff00'}}};
        app.updateLayers([a], true, 'Marks'); window.canvasRenderer.render(); }""")
    settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and len(v['marks']) == 3)
    out = open_output(page, cid)
    ctx, ph = open_phone(pw_browser, e2e_server)
    ctx2, ph2 = open_phone(pw_browser, e2e_server)
    red = lambda v: v and v[0] > 200 and v[1] < 60 and v[2] < 60  # noqa: E731
    try:
        rows = tab_rows(page)
        assert keys(rows) == ['0,0,0,0', '1,0,1,1', '2,1,0,0'], rows
        assert not any(r['ticked'] for r in rows)
        assert page.inner_text('#idm-count') == '(3)'
        assert not page.is_visible('#idm-swapped') and swapped_tab(page) == []
        # module (1,0,1,1) is x 192..256, y 64..128 on the wall: red, marked
        settled(out, lambda: pixel(out, 224, 96), red)
        # tick on the tab: the mark leaves the server's marks, the tab, both
        # phones and the wall; the row moves to Swapped; one undo step
        h0 = history_index(page)
        page.click('#idm-list .idm-row[data-idm-key="1,0,1,1"] input[data-idm-swap]')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' not in v['marks'])
        assert sorted(got['marks']) == ['0,0,0,0', '2,1,0,0'], got
        assert got['swapped'] == {'1,0,1,1': {'style': 'color', 'color': '#ff1a1a', 'n': 1}}, got
        assert settled(page, lambda: keys(tab_rows(page)), lambda v: len(v) == 2) == ['0,0,0,0', '2,1,0,0']
        assert swapped_tab(page) == [{'key': '1,0,1,1', 'text': 'Col 2, Row 1 · Bottom right module', 'ticked': True}]
        assert page.is_visible('#idm-swapped')
        assert page.inner_text('#idm-count') == '(2)' and page.inner_text('#idm-swapped-count') == '(1)'
        assert history_index(page) == h0 + 1
        assert settled(ph, lambda: ph.inner_text('#ph-swap-open'), lambda v: v == 'Swap list (2)') == 'Swap list (2)'
        assert settled(ph2, lambda: keys(phone_rows(ph2)), lambda v: len(v) == 2) == ['0,0,0,0', '2,1,0,0']
        assert keys(swapped_phone(ph2)) == ['1,0,1,1'] and swapped_phone(ph2)[0]['ticked'] is True
        assert not red(settled(out, lambda: pixel(out, 224, 96), lambda v: v and not red(v)))
        # Undo on the computer: the mark and its row come back everywhere
        page.evaluate("() => window.app.undo()")
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' in v['marks'])
        assert got['marks']['1,0,1,1'] == {'style': 'color', 'color': '#ff1a1a'} and 'swapped' not in got, got
        assert settled(page, lambda: keys(tab_rows(page)), lambda v: len(v) == 3) == ['0,0,0,0', '1,0,1,1', '2,1,0,0']
        assert page.inner_text('#idm-count') == '(3)' and not page.is_visible('#idm-swapped')
        assert settled(ph2, lambda: len(phone_rows(ph2)), lambda v: v == 3) == 3
        settled(out, lambda: pixel(out, 224, 96), red)
        page.evaluate("() => window.app.redo()")
        settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' not in v['marks'])
        # tick on the phone: gone from the server's marks, the tab and the
        # other phone, onto Swapped on top (the newest), the counts go down
        assert settled(ph, lambda: ph.inner_text('#ph-swap-open'), lambda v: v == 'Swap list (2)') == 'Swap list (2)'
        open_swap(ph)
        assert ph.inner_text('#ph-count') == '(2)' and ph.inner_text('#ph-swapped-count') == '(1)'
        h1 = history_index(page)
        ph.tap('#ph-list .ph-row[data-ph-key="2,1,0,0"] input')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '2,1,0,0' not in v['marks'])
        assert sorted(got['marks']) == ['0,0,0,0'], got
        assert got['swapped']['2,1,0,0'] == {'style': 'x', 'color': '#00ff00', 'n': 2}, got
        assert settled(ph, lambda: keys(phone_rows(ph)), lambda v: len(v) == 1) == ['0,0,0,0']
        assert keys(swapped_phone(ph)) == ['2,1,0,0', '1,0,1,1']
        assert ph.inner_text('#ph-count') == '(1)' and ph.inner_text('#ph-swapped-count') == '(2)'
        assert settled(ph2, lambda: ph2.inner_text('#ph-swap-open'), lambda v: v == 'Swap list (1)') == 'Swap list (1)'
        assert settled(page, lambda: keys(swapped_tab(page)), lambda v: len(v) == 2) == ['2,1,0,0', '1,0,1,1']
        assert keys(tab_rows(page)) == ['0,0,0,0'] and page.inner_text('#idm-count') == '(1)'
        assert settled(page, lambda: history_index(page), lambda v: v == h1 + 1) == h1 + 1
        # untick on the computer: the row and the mark come back, on the
        # phones and on the wall; one undo step
        h2 = history_index(page)
        page.click('#idm-swapped-list .idm-row[data-idm-key="1,0,1,1"] input[data-idm-swap]')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '1,0,1,1' in v['marks'])
        assert got['marks']['1,0,1,1'] == {'style': 'color', 'color': '#ff1a1a'}, got
        assert list(got['swapped']) == ['2,1,0,0'], got
        assert settled(page, lambda: history_index(page), lambda v: v == h2 + 1) == h2 + 1
        assert keys(tab_rows(page)) == ['0,0,0,0', '1,0,1,1'] and keys(swapped_tab(page)) == ['2,1,0,0']
        settled(out, lambda: pixel(out, 224, 96), red)
        assert settled(ph, lambda: keys(phone_rows(ph)), lambda v: len(v) == 2) == ['0,0,0,0', '1,0,1,1']
        assert keys(swapped_phone(ph)) == ['2,1,0,0']
        assert settled(ph2, lambda: ph2.inner_text('#ph-swap-open'), lambda v: v == 'Swap list (2)') == 'Swap list (2)'
        # untick on the phone: the X mark is back as it was, on the tab too
        ph.tap('#ph-swapped-list .ph-row[data-ph-key="2,1,0,0"] input')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '2,1,0,0' in v['marks'])
        assert got['marks']['2,1,0,0'] == {'style': 'x', 'color': '#00ff00'} and 'swapped' not in got, got
        assert settled(page, lambda: keys(tab_rows(page)), lambda v: len(v) == 3) == ['0,0,0,0', '1,0,1,1', '2,1,0,0']
        assert settled(page, lambda: page.is_visible('#idm-swapped'), lambda v: not v) is False
        assert settled(ph, lambda: ph.is_visible('#ph-swapped'), lambda v: not v) is False
        # the phone's own Undo takes the untick back
        close_swap(ph)
        ph.tap('#ph-undo')
        assert 'Undone: Module Not Swapped' in toast_text(ph)
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '2,1,0,0' not in v['marks'])
        assert list(got.get('swapped', {})) == ['2,1,0,0'], got
        assert settled(ph2, lambda: keys(swapped_phone(ph2)), lambda v: v == ['2,1,0,0']) == ['2,1,0,0']
        # a reload keeps both lists, and the server's file
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function("() => window.app && window.app.project && window.app.history"
                               " && window.app.socket && window.app.socket.connected", timeout=15000)
        page.wait_for_timeout(600)
        open_tab(page)
        assert keys(tab_rows(page)) == ['0,0,0,0', '1,0,1,1'] and keys(swapped_tab(page)) == ['2,1,0,0']
        # the module marked again (a new one went bad): off the Swapped list
        page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
            window.app._idmSetHighlight(a.id, '2,1,0,0'); window.app._idmMarkHighlight(); }""")
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '2,1,0,0' in v['marks'])
        assert 'swapped' not in got, got
        assert settled(page, lambda: page.is_visible('#idm-swapped'), lambda v: not v) is False
        assert settled(ph2, lambda: len(phone_rows(ph2)), lambda v: v == 3) == 3
        # the last ticks empty the open list; Clear all marks clears both
        open_swap(ph)
        for k in ('0,0,0,0', '1,0,1,1', '2,1,0,0'):
            ph.tap(f'#ph-list .ph-row[data-ph-key="{k}"] input')
            settled(page, lambda: served_idm(page, 'IdmA'), lambda v, k=k: v and k not in v['marks'])
        assert settled(ph, lambda: ph.inner_text('#ph-list'), lambda v: 'Nothing left to swap' in v)
        assert ph.inner_text('#ph-count') == '' and keys(swapped_phone(ph)) == ['2,1,0,0', '1,0,1,1', '0,0,0,0']
        assert settled(ph2, lambda: ph2.inner_text('#ph-swap-open'), lambda v: v == 'Swap list') == 'Swap list'
        assert settled(page, lambda: page.inner_text('#idm-count'), lambda v: v == '') == ''
        assert settled(page, lambda: page.inner_text('#idm-list'), lambda v: 'Nothing left to swap' in v)
        page.click('#idm-clear-all')
        assert 'Clear all 3 swapped modules on 1 screen?' in page.inner_text('#idm-clear-all-confirm')
        page.click('#idm-clear-all-confirm .btn-primary')
        got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and 'swapped' not in v)
        assert got['marks'] == {} and 'swapped' not in got, got
        assert settled(ph, lambda: ph.is_visible('#ph-swapped'), lambda v: not v) is False
        assert 'No marks yet' in ph.inner_text('#ph-list')
        assert not ph._errors and not ph2._errors and not page._errors, (ph._errors, ph2._errors, page._errors)
    finally:
        ctx.close()
        ctx2.close()
        out.close()


NAMES_JS = """async ([name, back]) => {
    const core = await import('/static/js/idm-core.js');
    const groups = core.idmMarkGroups(window.canvasRenderer, window.app.project, {back});
    const g = groups.find(x => x.layer.name === name);
    return g ? Object.fromEntries(g.rows.map(r => [r.key, [r.place, r.ids]])) : {};
}"""


def put_marks(pg, name, mx, my, keys):
    pg.evaluate("""([name, mx, my, keys]) => { const app = window.app, l = app.project.layers.find(x => x.name === name);
        l.idm = {modulesX: mx, modulesY: my, marks: Object.fromEntries(keys.map(k => [k, {style: 'color', color: '#ff1a1a'}]))};
        app.updateLayers([l], true, 'Marks'); window.canvasRenderer.render(); }""", [name, mx, my, keys])
    settled(pg, lambda: served_idm(pg, name), lambda v: v and len(v['marks']) == len(keys))


def names(pg, name):
    return pg.evaluate(NAMES_JS, [name, False]), pg.evaluate(NAMES_JS, [name, True])


def test_front_and_back_name_the_place_then_the_ids(page, e2e_server, pw_browser):
    """Owner, 2026-11-17: a row leads with the cabinet's column and row in
    its screen, then the module's place in plain words, both from the
    viewer's top-left (from the back, column 1 is the front's rightmost and
    left and right swap); the Cabinet ID and Module ID follow as a hint,
    the same from either side. IdmA is 3 x 2 cabinets, IdmB 2 x 2."""
    reset_project(page)
    page.click('[data-idm-side="front"]')
    # the words for every layout up to 3 x 3, and past it
    spots = page.evaluate("""async () => {
        const {idmModuleSpot: s} = await import('/static/js/idm-core.js');
        return [s(0, 0, 1, 1), s(0, 0, 2, 1), s(1, 0, 2, 1), s(0, 0, 1, 2), s(0, 1, 1, 2),
                s(0, 0, 2, 2), s(1, 0, 2, 2), s(0, 1, 2, 2), s(1, 1, 2, 2),
                s(1, 1, 3, 3), s(2, 1, 3, 3), s(1, 0, 3, 3), s(0, 2, 3, 3), s(1, 0, 3, 1), s(0, 1, 1, 3),
                s(1, 0, 3, 2), s(2, 1, 4, 4), s(0, 3, 2, 4)];
    }""")
    assert spots == ['Whole cabinet', 'Left module', 'Right module', 'Top module', 'Bottom module',
                     'Top left module', 'Top right module', 'Bottom left module', 'Bottom right module',
                     'Center module', 'Middle right module', 'Top middle module', 'Bottom left module',
                     'Middle module', 'Middle module', 'Top middle module', 'Module row 2, col 3',
                     'Module row 4, col 1'], spots
    # 2 x 2 modules on IdmA (3 cabinets wide)
    set_layout(page, 'IdmA', 2, 2)
    put_marks(page, 'IdmA', 2, 2, ['0,0,0,0', '0,0,1,1', '2,1,1,0'])
    front, back = names(page, 'IdmA')
    assert front == {'0,0,0,0': ['Col 1, Row 1 · Top left module', 'Cabinet A1 · Module A1'],
                     '0,0,1,1': ['Col 1, Row 1 · Bottom right module', 'Cabinet A1 · Module B2'],
                     '2,1,1,0': ['Col 3, Row 2 · Top right module', 'Cabinet C2 · Module B1']}, front
    assert back == {'0,0,0,0': ['Col 3, Row 1 · Top right module', 'Cabinet A1 · Module A1'],
                    '0,0,1,1': ['Col 3, Row 1 · Bottom left module', 'Cabinet A1 · Module B2'],
                    '2,1,1,0': ['Col 1, Row 2 · Top left module', 'Cabinet C2 · Module B1']}, back
    # 4 x 4 modules on IdmB (2 cabinets wide): past 3, row and col
    set_layout(page, 'IdmB', 4, 4)
    put_marks(page, 'IdmB', 4, 4, ['0,0,0,0', '0,0,2,1', '1,1,3,3'])
    front, back = names(page, 'IdmB')
    assert front == {'0,0,0,0': ['Col 1, Row 1 · Module row 1, col 1', 'Cabinet A1 · Module A1'],
                     '0,0,2,1': ['Col 1, Row 1 · Module row 2, col 3', 'Cabinet A1 · Module C2'],
                     '1,1,3,3': ['Col 2, Row 2 · Module row 4, col 4', 'Cabinet B2 · Module D4']}, front
    assert back == {'0,0,0,0': ['Col 2, Row 1 · Module row 1, col 4', 'Cabinet A1 · Module A1'],
                    '0,0,2,1': ['Col 2, Row 1 · Module row 2, col 2', 'Cabinet A1 · Module C2'],
                    '1,1,3,3': ['Col 1, Row 2 · Module row 4, col 1', 'Cabinet B2 · Module D4']}, back
    # the switch and the ticks sit inside the panel, the tick's word as written
    fit = page.evaluate("""() => {
        const panel = document.getElementById('idm-list').parentElement.getBoundingClientRect();
        const bar = document.querySelector('.idm-side-bar');
        const swap = document.querySelector('#idm-list .idm-swap');
        const right = Math.max(...Array.from(bar.querySelectorAll('button')).map(b => b.getBoundingClientRect().right),
                               swap.getBoundingClientRect().right);
        return {right, panel: panel.right, overflow: bar.scrollWidth - bar.clientWidth,
                case: getComputedStyle(swap).textTransform};
    }""")
    assert fit['right'] <= fit['panel'] + 0.5 and fit['overflow'] <= 0 and fit['case'] == 'none', fit
    # the switch on the tab names the list rows that way, per viewer: the
    # place first, the IDs under it
    page.click('[data-idm-side="back"]')
    rows = tab_rows(page)
    assert [r['text'] for r in rows[:3]] == ['Col 3, Row 1 · Top right module', 'Col 3, Row 1 · Bottom left module',
                                            'Col 1, Row 2 · Top left module'], rows
    assert [r['ids'] for r in rows[:3]] == ['Cabinet A1 · Module A1', 'Cabinet A1 · Module B2',
                                           'Cabinet C2 · Module B1'], rows
    assert page.get_attribute('[data-idm-side="back"]', 'aria-pressed') == 'true'
    assert page.evaluate("() => localStorage.getItem('lrdIdmListSide')") == 'back'
    # the tab's highlight readout stays as it was
    page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
        window.app._idmSetHighlight(a.id, '0,0,0,0'); }""")
    assert page.inner_text('#idm-hl-readout') == 'IdmA · A1 · Module A1'
    page.click('[data-idm-side="front"]')
    rows = tab_rows(page)
    assert rows[0]['text'] == 'Col 1, Row 1 · Top left module' and rows[0]['ids'] == 'Cabinet A1 · Module A1', rows
    # the phone has its own switch; its readout follows it
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        assert settled(ph, lambda: ph.inner_text('#ph-place'), lambda v: v.startswith('Col 1'))\
            == 'Col 1, Row 1 · Top left module'
        assert ph.inner_text('#ph-ids') == 'IdmA · Cabinet A1 · Module A1'
        open_swap(ph)
        ph.tap('[data-ph-side="back"]')
        rows = phone_rows(ph)
        assert rows[0]['text'] == 'Col 3, Row 1 · Top right module' and rows[0]['where'] == 'Cabinet A1 · Module A1', rows
        assert page.get_attribute('[data-idm-side="front"]', 'aria-pressed') == 'true'
        close_swap(ph)
        assert ph.inner_text('#ph-place') == 'Col 3, Row 1 · Top right module'
        assert ph.inner_text('#ph-ids') == 'From the back · IdmA · Cabinet A1 · Module A1'
        # the readout still fits its line on a small phone
        assert ph.evaluate("() => document.documentElement.scrollHeight <= window.innerHeight")
    finally:
        ctx.close()
    # on the smallest phone a long place still reads whole on its own line,
    # with Marked beside the IDs under it
    page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
        window.app._idmSetHighlight(a.id, '0,0,1,1'); }""")
    ctx, ph = open_phone(pw_browser, e2e_server, size=(375, 667))
    try:
        assert settled(ph, lambda: ph.inner_text('#ph-place'), lambda v: 'Bottom' in v)\
            == 'Col 1, Row 1 · Bottom right module'
        fit = ph.evaluate("""() => {
            const place = document.getElementById('ph-place'), ids = document.getElementById('ph-ids');
            const state = document.getElementById('ph-state');
            return {whole: place.scrollWidth <= place.clientWidth, state: state.textContent,
                    below: state.getBoundingClientRect().top >= place.getBoundingClientRect().bottom - 1,
                    sameLine: Math.abs(state.getBoundingClientRect().bottom - ids.getBoundingClientRect().bottom) < 4,
                    fits: document.documentElement.scrollHeight <= window.innerHeight};
        }""")
        assert fit == {'whole': True, 'state': 'Marked', 'below': True, 'sameLine': True, 'fits': True}, fit
    finally:
        ctx.close()
    # narrower still (or a wider system font): the type steps down so the
    # place still reads whole, never cut short
    ctx, ph = open_phone(pw_browser, e2e_server, size=(300, 640))
    try:
        assert settled(ph, lambda: ph.inner_text('#ph-place'), lambda v: 'Bottom' in v)\
            == 'Col 1, Row 1 · Bottom right module'
        fit = ph.evaluate("""() => { const p = document.getElementById('ph-place');
            return {whole: p.scrollWidth <= p.clientWidth, px: parseFloat(getComputedStyle(p).fontSize)}; }""")
        assert fit['whole'] and 11 <= fit['px'] < 18, fit
    finally:
        ctx.close()
    # 3 x 3 modules on IdmB
    set_layout(page, 'IdmB', 3, 3)
    put_marks(page, 'IdmB', 3, 3, ['0,0,1,1', '0,0,0,1', '1,0,2,0', '1,1,1,2'])
    front, back = names(page, 'IdmB')
    assert front == {'0,0,1,1': ['Col 1, Row 1 · Center module', 'Cabinet A1 · Module B2'],
                     '0,0,0,1': ['Col 1, Row 1 · Middle left module', 'Cabinet A1 · Module A2'],
                     '1,0,2,0': ['Col 2, Row 1 · Top right module', 'Cabinet B1 · Module C1'],
                     '1,1,1,2': ['Col 2, Row 2 · Bottom middle module', 'Cabinet B2 · Module B3']}, front
    assert back == {'0,0,1,1': ['Col 2, Row 1 · Center module', 'Cabinet A1 · Module B2'],
                    '0,0,0,1': ['Col 2, Row 1 · Middle right module', 'Cabinet A1 · Module A2'],
                    '1,0,2,0': ['Col 1, Row 1 · Top left module', 'Cabinet B1 · Module C1'],
                    '1,1,1,2': ['Col 1, Row 2 · Bottom middle module', 'Cabinet B2 · Module B3']}, back
    # 1 x 2 (one across, two down) and 2 x 1 on IdmA
    set_layout(page, 'IdmA', 1, 2)
    put_marks(page, 'IdmA', 1, 2, ['0,0,0,1', '1,0,0,0'])
    front, back = names(page, 'IdmA')
    assert front == {'0,0,0,1': ['Col 1, Row 1 · Bottom module', 'Cabinet A1 · Module A2'],
                     '1,0,0,0': ['Col 2, Row 1 · Top module', 'Cabinet B1 · Module A1']}, front
    assert back == {'0,0,0,1': ['Col 3, Row 1 · Bottom module', 'Cabinet A1 · Module A2'],
                    '1,0,0,0': ['Col 2, Row 1 · Top module', 'Cabinet B1 · Module A1']}, back
    set_layout(page, 'IdmA', 2, 1)
    put_marks(page, 'IdmA', 2, 1, ['0,0,0,0', '2,1,1,0'])
    front, back = names(page, 'IdmA')
    assert front == {'0,0,0,0': ['Col 1, Row 1 · Left module', 'Cabinet A1 · Module A1'],
                     '2,1,1,0': ['Col 3, Row 2 · Right module', 'Cabinet C2 · Module B1']}, front
    assert back == {'0,0,0,0': ['Col 3, Row 1 · Right module', 'Cabinet A1 · Module A1'],
                    '2,1,1,0': ['Col 1, Row 2 · Left module', 'Cabinet C2 · Module B1']}, back
    # a half cabinet counts its own modules, and mirrors within them
    page.evaluate("""async () => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const ids = a.panels.filter(q => q.col === 0).map(q => ({id: q.id, halfTile: 'width'}));
        await fetch(`/api/layer/${a.id}/panels/set_half_tile`, {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({panels: ids})});
        app.loadProject();
    }""")
    page.wait_for_timeout(1000)
    open_tab(page)
    put_marks(page, 'IdmA', 4, 4, ['0,0,3,1', '0,0,2,0', '1,0,0,0'])
    front, back = names(page, 'IdmA')
    assert front == {'0,0,3,1': ['Col 1, Row 1 · Module row 2, col 2', 'Cabinet A1 · Module B2'],
                     '0,0,2,0': ['Col 1, Row 1 · Module row 1, col 1', 'Cabinet A1 · Module A1'],
                     '1,0,0,0': ['Col 2, Row 1 · Module row 1, col 1', 'Cabinet B1 · Module A1']}, front
    assert back == {'0,0,3,1': ['Col 3, Row 1 · Module row 2, col 1', 'Cabinet A1 · Module B2'],
                    '0,0,2,0': ['Col 3, Row 1 · Module row 1, col 2', 'Cabinet A1 · Module A1'],
                    '1,0,0,0': ['Col 2, Row 1 · Module row 1, col 4', 'Cabinet B1 · Module A1']}, back
    # a half cabinet of a 2 x 2 layout is one module across: top or bottom
    put_marks(page, 'IdmA', 2, 2, ['0,0,1,1', '1,0,0,1'])
    front, back = names(page, 'IdmA')
    assert front == {'0,0,1,1': ['Col 1, Row 1 · Bottom module', 'Cabinet A1 · Module A2'],
                     '1,0,0,1': ['Col 2, Row 1 · Bottom left module', 'Cabinet B1 · Module A2']}, front
    assert back == {'0,0,1,1': ['Col 3, Row 1 · Bottom module', 'Cabinet A1 · Module A2'],
                    '1,0,0,1': ['Col 2, Row 1 · Bottom right module', 'Cabinet B1 · Module A2']}, back


# ── holding an arrow ──────────────────────────────────────────────────────

HOLD_SPY_JS = """() => {
    const p = window.idmPhone;
    window.__moves = []; window.__sends = [];
    if (!window.__holdSpy) {
        window.__holdSpy = true;
        const move = p.jobs.move;
        p.jobs.move = function (...a) { window.__moves.push(performance.now()); return move.apply(this, a); };
        const s = p.socket(), emit = s.emit.bind(s);
        s.emit = (ev, ...a) => { if (ev === 'idm_highlight') window.__sends.push(performance.now()); return emit(ev, ...a); };
    }
}"""

PRESS_JS = """([dir, type]) => {
    const b = document.querySelector(`[data-ph-move="${dir}"]`);
    b.dispatchEvent(new PointerEvent(type, {pointerId: 7, button: 0, isPrimary: true, pointerType: 'touch',
                                            bubbles: true, cancelable: true}));
    return performance.now();
}"""


def test_holding_a_phone_arrow_speeds_up_and_stops_on_release(page, e2e_server, pw_browser):
    reset_project(page)
    set_layout(page, 'IdmA', 4, 4)
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        ph.evaluate(HOLD_SPY_JS)
        # held 1.3 s: a step at once, the next after a wait, then sooner
        # each step; let go, nothing more
        ph.evaluate(PRESS_JS, ['right', 'pointerdown'])
        ph.wait_for_timeout(1300)
        released = ph.evaluate(PRESS_JS, ['right', 'pointerup'])
        ph.wait_for_timeout(600)
        moves = ph.evaluate("() => window.__moves.slice()")
        sends = ph.evaluate("() => window.__sends.slice()")
        assert [t for t in moves if t > released + 5] == [], (moves, released)
        gaps = [round(b - a) for a, b in zip(moves, moves[1:])]
        assert len(moves) >= 12 and gaps[0] >= 300 and max(gaps[-3:]) <= 70 and gaps[1] > gaps[-1], gaps
        # the highlight travelled: right along IdmA's top row of modules
        assert settled(page, lambda: hl(page), lambda v: v and v[1] != '0,0,0,0' and v[1].endswith(',0'))
        # never more than one send each 40 ms (a timer's slack aside)
        send_gaps = [b - a for a, b in zip(sends, sends[1:])]
        assert sends and len(sends) <= len(moves) and all(g >= 35 for g in send_gaps), send_gaps
        # a tap is one step
        ph.evaluate("() => { window.__moves = []; }")
        ph.tap('[data-ph-move="left"]')
        ph.wait_for_timeout(500)
        assert len(ph.evaluate("() => window.__moves")) == 1
        # the touch cancelled (a scroll, a call), or the page losing focus:
        # it stops
        for end in ('pointercancel', 'blur'):
            ph.evaluate("() => { window.__moves = []; }")
            ph.evaluate(PRESS_JS, ['down', 'pointerdown'])
            ph.wait_for_timeout(450)
            if end == 'pointercancel':
                ph.evaluate(PRESS_JS, ['down', 'pointercancel'])
            else:
                ph.evaluate("() => window.dispatchEvent(new Event('blur'))")
            n = len(ph.evaluate("() => window.__moves"))
            ph.wait_for_timeout(500)
            assert len(ph.evaluate("() => window.__moves")) == n and n >= 2, end
        # the main screen's controls stay put: no text picked up, no
        # long-press menu on a held arrow
        css = ph.evaluate("""() => { const s = getComputedStyle(document.querySelector('[data-ph-move="up"]'));
            return [s.userSelect || s.webkitUserSelect, s.touchAction]; }""")
        assert css == ['none', 'none'], css
        assert not ph._errors, ph._errors
    finally:
        ctx.close()


# ── Rows from ─────────────────────────────────────────────────────────────

ROWS_TAB_JS = """() => Array.from(document.querySelectorAll('#idm-list .idm-group, #idm-swapped-list .idm-group')).map(h => [
    h.querySelector('.idm-group-name').textContent,
    h.querySelector('[data-idm-rows][aria-pressed="true"]').dataset.idmRows])"""

ROWS_PHONE_JS = """() => Array.from(document.querySelectorAll('#ph-list .ph-group, #ph-swapped-list .ph-group')).map(h => [
    h.querySelector('.ph-group-name').textContent,
    h.querySelector('[data-ph-rows][aria-pressed="true"]').dataset.phRows])"""


def rows_of(pg, name, bottom):
    return pg.evaluate("""async ([name, bottom]) => {
        const core = await import('/static/js/idm-core.js');
        const app = window.app, l = app.project.layers.find(x => x.name === name);
        const field = Object.assign({}, app.project.idmField || {});
        const keep = app.project.idmField;
        app.project.idmField = Object.assign({}, field, {rowsFrom: Object.assign({}, field.rowsFrom || {}, {[l.id]: bottom ? 'bottom' : 'top'})});
        const g = core.idmMarkGroups(window.canvasRenderer, app.project, {}).find(x => x.layer === l);
        const back = core.idmMarkGroups(window.canvasRenderer, app.project, {back: true}).find(x => x.layer === l);
        app.project.idmField = keep;
        return [Object.fromEntries(g.rows.map(r => [r.key, r.place])), Object.fromEntries(back.rows.map(r => [r.key, r.place]))];
    }""", [name, bottom])


def test_rows_count_from_the_top_or_the_bottom_per_screen(page, e2e_server, pw_browser):
    reset_project(page)
    # the defaults, from the Header/Footer side
    got = page.evaluate("""async () => { const c = await import('/static/js/idm-core.js');
        return [{}, {riggingBars: [2]}, {riggingFooterBars: [2, 2]}, {riggingSide: 'footer'},
                {riggingSide: 'footer', riggingFooterBars: []}, {riggingBars: [1], riggingFooterBars: [1]},
                {riggingSide: 'header'}].map(l => c.idmRowsFromDefault(l)); }""")
    assert got == ['top', 'top', 'bottom', 'bottom', 'bottom', 'top', 'top'], got
    # the words: IdmA is 3 x 2 cabinets; from the bottom, row 1 is the
    # bottom row; a module's place in words never changes
    set_layout(page, 'IdmA', 2, 2)
    put_marks(page, 'IdmA', 2, 2, ['0,0,0,0', '2,1,1,0'])
    top, top_back = rows_of(page, 'IdmA', False)
    bottom, bottom_back = rows_of(page, 'IdmA', True)
    assert top == {'0,0,0,0': 'Col 1, Row 1 · Top left module', '2,1,1,0': 'Col 3, Row 2 · Top right module'}, top
    assert bottom == {'0,0,0,0': 'Col 1, Row 2 · Top left module', '2,1,1,0': 'Col 3, Row 1 · Top right module'}, bottom
    assert bottom_back == {'0,0,0,0': 'Col 3, Row 2 · Top right module', '2,1,1,0': 'Col 1, Row 1 · Top left module'}, bottom_back
    # past 3 x 3 the module's row in its cabinet counts up too
    set_layout(page, 'IdmB', 4, 4)
    put_marks(page, 'IdmB', 4, 4, ['0,0,0,0', '1,1,2,3'])
    top, _ = rows_of(page, 'IdmB', False)
    bottom, bottom_back = rows_of(page, 'IdmB', True)
    assert top == {'0,0,0,0': 'Col 1, Row 1 · Module row 1, col 1', '1,1,2,3': 'Col 2, Row 2 · Module row 4, col 3'}, top
    assert bottom == {'0,0,0,0': 'Col 1, Row 2 · Module row 4, col 1', '1,1,2,3': 'Col 2, Row 1 · Module row 1, col 3'}, bottom
    assert bottom_back == {'0,0,0,0': 'Col 2, Row 2 · Module row 4, col 4', '1,1,2,3': 'Col 1, Row 1 · Module row 1, col 2'}, bottom_back
    # IdmB gets a footer (ground stacked): it starts on Bottom, IdmA on Top
    page.evaluate("""() => { const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        b.riggingFooterBars = [2]; b.riggingSide = 'footer'; app.updateLayers([b], true, 'Footer'); }""")
    page.click('[data-idm-side="front"]')
    assert settled(page, lambda: page.evaluate(ROWS_TAB_JS),
                   lambda v: v == [['IdmA · 2 marks', 'top'], ['IdmB · 2 marks', 'bottom']]) \
        == [['IdmA · 2 marks', 'top'], ['IdmB · 2 marks', 'bottom']]
    texts = [r['text'] for r in tab_rows(page)]
    assert texts == ['Col 1, Row 1 · Top left module', 'Col 3, Row 2 · Top right module',
                     'Col 1, Row 2 · Module row 4, col 1', 'Col 2, Row 1 · Module row 1, col 3'], texts
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        open_swap(ph)
        assert ph.evaluate(ROWS_PHONE_JS) == [['IdmA', 'top'], ['IdmB', 'bottom']]
        assert [r['text'] for r in phone_rows(ph)] == texts
        assert ph.inner_text('#ph-side-label') == ('Columns counted from the left as you face the front of the wall; '
                                                   'rows from the top or bottom, as set beside each screen.')
        # IdmA to Bottom on the tab: the phone follows live; never an undo step
        h0 = history_index(page)
        a_id = page.evaluate("() => window.app.project.layers.find(x => x.name === 'IdmA').id")
        page.click(f'#idm-list [data-idm-rows="bottom"][data-idm-layer="{a_id}"]')
        assert settled(page, lambda: (served_field(page) or {}).get('rowsFrom'), lambda v: v == {str(a_id): 'bottom'}) \
            == {str(a_id): 'bottom'}
        assert settled(ph, lambda: ph.evaluate(ROWS_PHONE_JS), lambda v: v[0] == ['IdmA', 'bottom'])[0] == ['IdmA', 'bottom']
        assert [r['text'] for r in phone_rows(ph)][:2] == ['Col 1, Row 2 · Top left module', 'Col 3, Row 1 · Top right module']
        assert ph.inner_text('#ph-side-label') == 'Counted from the bottom left as you face the front of the wall.'
        page.wait_for_timeout(300)
        assert history_index(page) == h0
        # the phone flips IdmB to Top: the tab follows live
        ph.tap('#ph-list [data-ph-rows="top"][data-ph-layer="%d"]' % page.evaluate(
            "() => window.app.project.layers.find(x => x.name === 'IdmB').id"))
        assert settled(page, lambda: page.evaluate(ROWS_TAB_JS), lambda v: v[1] == ['IdmB · 2 marks', 'top'])[1] \
            == ['IdmB · 2 marks', 'top']
        assert [r['text'] for r in tab_rows(page)][2:] == ['Col 1, Row 1 · Module row 1, col 1',
                                                           'Col 2, Row 2 · Module row 4, col 3']
        # the Swapped list counts the same way, with its own switch
        ph.tap('#ph-list .ph-row[data-ph-key="2,1,1,0"] input')
        assert settled(page, lambda: [r['text'] for r in swapped_tab(page)], lambda v: len(v) == 1) \
            == ['Col 3, Row 1 · Top right module']
        assert settled(ph, lambda: [r['text'] for r in swapped_phone(ph)], lambda v: len(v) == 1) \
            == ['Col 3, Row 1 · Top right module']
        page.click(f'#idm-swapped-list [data-idm-rows="top"][data-idm-layer="{a_id}"]')
        assert settled(ph, lambda: [r['text'] for r in swapped_phone(ph)], lambda v: v and 'Row 2' in v[0]) \
            == ['Col 3, Row 2 · Top right module']
        assert [r['text'] for r in tab_rows(page)][0] == 'Col 1, Row 1 · Top left module'
        page.click(f'#idm-list [data-idm-rows="bottom"][data-idm-layer="{a_id}"]')
        settled(ph, lambda: ph.evaluate(ROWS_PHONE_JS), lambda v: v and v[0] == ['IdmA', 'bottom'])
        # the phone's readout reads the same way, and says so
        close_swap(ph)
        page.evaluate(f"() => window.app._idmSetHighlight({a_id}, '0,0,0,0')")
        assert settled(ph, lambda: ph.inner_text('#ph-place'), lambda v: v.startswith('Col 1, Row 2')) \
            == 'Col 1, Row 2 · Top left module'
        assert ph.inner_text('#ph-ids') == 'Rows from the bottom · IdmA · Cabinet A1 · Module A1'
        # Undo on the computer leaves the picks as they are
        page.evaluate("() => window.app.undo()")
        page.wait_for_timeout(500)
        assert (served_field(page) or {}).get('rowsFrom', {}).get(str(a_id)) == 'bottom'
        page.evaluate("() => window.app.redo()")
        # a reload keeps them
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function("() => window.app && window.app.project && window.app.history"
                               " && window.app.socket && window.app.socket.connected", timeout=15000)
        page.wait_for_timeout(600)
        open_tab(page)
        assert page.evaluate(ROWS_TAB_JS)[0] == ['IdmA · 1 mark', 'bottom']
        assert not ph._errors and not page._errors, (ph._errors, page._errors)
    finally:
        page.evaluate("() => window.app._idmSetField({rowsFrom: {}})")
        ctx.close()


# ── the controls kept to one canvas ───────────────────────────────────────

# Two canvases: IdmA and IdmB on the first, IdmC on the second (beside it in
# the workspace, so a step right off IdmB would land on it if steps left the
# canvas).
TWO_JS = """async () => {
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const post = (url, body) => fetch(url, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    let project = await (await fetch('/api/project')).json();
    const base = Object.assign({}, project.canvases[0], {raster_width: 1920, raster_height: 1080,
        show_raster_width: 1920, show_raster_height: 1080, visible: true});
    delete base.show_workspace_x; delete base.show_workspace_y;
    const one = Object.assign({}, base, {id: 'cOne', name: 'Main', workspace_x: 0, workspace_y: 0});
    const two = Object.assign({}, base, {id: 'cTwo', name: 'Side', workspace_x: 1920, workspace_y: 0});
    project.layers = []; project.groups = [];
    project.canvases = [one, two];
    project.active_canvas_id = 'cOne';
    project.idmHighlight = null;
    await put('/api/project', project);
    await post('/api/layer/add', {name: 'IdmA', columns: 2, rows: 1, cabinet_width: 128, cabinet_height: 128,
        offset_x: 0, offset_y: 0, canvas_id: 'cOne'});
    await post('/api/layer/add', {name: 'IdmB', columns: 2, rows: 1, cabinet_width: 128, cabinet_height: 128,
        offset_x: 1664, offset_y: 0, canvas_id: 'cOne'});
    await post('/api/layer/add', {name: 'IdmC', columns: 2, rows: 1, cabinet_width: 128, cabinet_height: 128,
        offset_x: 0, offset_y: 0, canvas_id: 'cTwo'});
    window.app.closeAllOutputDisplays();
    window.app._idmClearHighlight();
    window.app.loadProject();
}"""


def two_canvases(pg):
    pg.evaluate(TWO_JS)
    pg.wait_for_function("() => window.app.project && (window.app.project.layers || []).length === 3"
                         " && (window.app.project.canvases || []).length === 2", timeout=10000)
    pg.wait_for_timeout(400)
    open_tab(pg)
    pg.mouse.move(5, 5)
    pg.evaluate("() => window.app._idmClearHighlight()")


FAKE_PAD_JS = """() => {
    const pad = {id: 'Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)',
        index: 0, connected: true, mapping: 'standard', axes: [0, 0, 0, 0], timestamp: 0,
        buttons: Array.from({length: 17}, () => ({pressed: false, touched: false, value: 0}))};
    window.__pad = pad;
    window.__focus = true;
    Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [window.__pad, null, null, null]});
    Object.defineProperty(document, 'hasFocus', {configurable: true, value: () => window.__focus});
    const ev = new Event('gamepadconnected');
    ev.gamepad = pad;
    window.dispatchEvent(ev);
}"""

PAD_SEEN = {
    'tab': "([bs, down]) => { const p = window.app._idmPad, s = p && p.pads.get(0); return !!s && bs.every(b => !!s.buttons[b] === down); }",
    'phone': "([bs, down]) => { const s = window.idmPhone.S.pads.get(0); return !!s && bs.every(b => !!s.buttons[b] === down); }",
}


def pad_tap(pg, kind, *buttons):
    for down in (True, False):
        pg.evaluate("([bs, down]) => bs.forEach(b => { window.__pad.buttons[b].pressed = down; window.__pad.buttons[b].value = down ? 1 : 0; })",
                    [list(buttons), down])
        pg.wait_for_function(PAD_SEEN[kind], arg=[list(buttons), down], timeout=5000)


def test_the_controller_keeps_to_its_canvas_and_view_jumps_canvas(page):
    two_canvases(page)
    page.evaluate(FAKE_PAD_JS)
    page.wait_for_function("() => !!window.app._idmPad.frame")
    # the help list is the one table's
    help_text = page.inner_text('#idm-pad-help')
    assert 'View / Share' in help_text and 'Next canvas' in help_text and 'Next screen on this canvas' in help_text
    assert 'Clear the highlight' not in help_text
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmB'))")
    tap = lambda *b: pad_tap(page, 'tab', *b)  # noqa: E731
    # Y from no highlight: the first screen on the active canvas
    tap(3)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')[0] == 'IdmA'
    tap(3)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmB')[0] == 'IdmB'
    # round to the first screen ON THIS CANVAS, never IdmC
    tap(3)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')[0] == 'IdmA'
    # right along the row stops at the canvas's last module: IdmB's last
    page.evaluate("""() => { const b = window.app.project.layers.find(x => x.name === 'IdmB');
        window.app._idmSetHighlight(b.id, '1,0,0,0'); }""")
    tap(15)
    page.wait_for_timeout(200)
    assert hl(page) == ['IdmB', '1,0,0,0']
    # View / Share: the next canvas, its first module, its name said
    tap(8)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmC') == ['IdmC', '0,0,0,0']
    assert 'Canvas: Side' in page.locator('#app-toast-host').inner_text()
    # and now Y stays on that canvas
    tap(3)
    page.wait_for_timeout(200)
    assert hl(page) == ['IdmC', '0,0,0,0']
    tap(8)
    assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA') == ['IdmA', '0,0,0,0']
    # the keyboard's arrows: unchanged, they keep to the canvas as before
    page.evaluate("""() => { const b = window.app.project.layers.find(x => x.name === 'IdmB');
        window.app._idmSetHighlight(b.id, '1,0,0,0'); }""")
    page.keyboard.press('ArrowRight')
    page.wait_for_timeout(150)
    assert hl(page) == ['IdmB', '1,0,0,0']
    assert not page._errors, page._errors
    unplug(page)


def unplug(pg):
    pg.evaluate("""() => { window.__pad.connected = false;
        const ev = new Event('gamepaddisconnected'); ev.gamepad = window.__pad; window.dispatchEvent(ev);
        Object.defineProperty(navigator, 'getGamepads', {configurable: true, value: () => [null, null, null, null]}); }""")


def test_the_phone_keeps_to_its_canvas_and_a_controller_drives_it(page, e2e_server, pw_browser):
    two_canvases(page)
    set_layout(page, 'IdmC', 2, 1)
    ctx, ph = open_phone(pw_browser, e2e_server)
    try:
        settled(ph, lambda: ph.is_enabled('#ph-canvas-next'), lambda v: v)
        open_menu(ph)
        assert ph.inner_text('#ph-canvas-name') == 'Main'
        ph.tap('#ph-next-screen')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')[0] == 'IdmA'
        ph.tap('#ph-next-screen')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmB')[0] == 'IdmB'
        ph.tap('#ph-next-screen')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA')[0] == 'IdmA'
        ph.tap('#ph-canvas-next')
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmC') == ['IdmC', '0,0,0,0']
        assert ph.inner_text('#ph-canvas-name') == 'Side'
        ph.tap('#ph-next-screen')
        ph.wait_for_timeout(200)
        assert hl(page) == ['IdmC', '0,0,0,0']
        # no controller: the menu has no controller line
        assert not ph.is_visible('#ph-pad-open')
        # a controller paired to the phone: the same map
        ph.evaluate(FAKE_PAD_JS)
        ph.wait_for_function("() => !!window.idmPhone.S.frame")
        # its button list is a screen of its own, from the menu; Back
        # returns to the menu, and the menu's Back to the controls
        ph.wait_for_selector('#ph-pad-open', state='visible')
        ph.tap('#ph-pad-open')
        assert ph.is_visible('#ph-pad-help') and 'View / Share' in ph.inner_text('#ph-pad-help')
        assert 'Clear the highlight' not in ph.inner_text('#ph-pad-help')
        ph.tap('#ph-pad-close')
        ph.wait_for_selector('#ph-pad-sheet', state='hidden')
        ph.wait_for_selector('#ph-menu-sheet', state='visible')
        close_menu(ph)
        tap = lambda *b: pad_tap(ph, 'phone', *b)  # noqa: E731
        tap(15)                       # D-pad right: one module
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmC', '0,0,1,0']) == ['IdmC', '0,0,1,0']
        tap(14)
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmC', '0,0,0,0']) == ['IdmC', '0,0,0,0']
        # RB held: a cabinet
        ph.evaluate("() => { window.__pad.buttons[5].pressed = true; window.__pad.buttons[5].value = 1; }")
        tap(15)
        ph.evaluate("() => { window.__pad.buttons[5].pressed = false; window.__pad.buttons[5].value = 0; }")
        assert settled(page, lambda: hl(page), lambda v: v == ['IdmC', '1,0,0,0']) == ['IdmC', '1,0,0,0']
        # A: mark (one step on the computer); B: the phone's undo
        tap(0)
        got = settled(page, lambda: served_idm(page, 'IdmC'), lambda v: v and '1,0,0,0' in v['marks'])
        assert '1,0,0,0' in got['marks']
        tap(1)
        settled(page, lambda: served_idm(page, 'IdmC'), lambda v: v and v['marks'] == {})
        # A held and moved: a paint, one change
        ph.evaluate("() => { window.__pad.buttons[0].pressed = true; window.__pad.buttons[0].value = 1; }")
        ph.wait_for_function(PAD_SEEN['phone'], arg=[[0], True])
        tap(14)
        ph.evaluate("() => { window.__pad.buttons[0].pressed = false; window.__pad.buttons[0].value = 0; }")
        ph.wait_for_function(PAD_SEEN['phone'], arg=[[0], False])
        got = settled(page, lambda: served_idm(page, 'IdmC'), lambda v: v and len(v['marks']) == 2)
        assert set(got['marks']) == {'1,0,0,0', '0,0,1,0'}, got
        # Y stays on this canvas; View / Share goes to the next
        tap(3)
        ph.wait_for_timeout(200)
        assert hl(page)[0] == 'IdmC'
        tap(8)
        assert settled(page, lambda: hl(page), lambda v: v and v[0] == 'IdmA') == ['IdmA', '0,0,0,0']
        # X: the next field color
        before = (served_field(page) or {}).get('color', '#ffffff')
        tap(2)
        assert settled(page, lambda: (served_field(page) or {}).get('color'), lambda v: v and v != before)
        assert not ph._errors, ph._errors
    finally:
        page.evaluate("() => window.app._idmSetField({color: '#ffffff'})")
        ctx.close()


# ── the QR code ───────────────────────────────────────────────────────────

def svg_matrix(svg):
    """The module matrix an SVG from qr-code.js draws (quiet zone off)."""
    n = int(re.search(r'viewBox="0 0 (\d+) \d+"', svg).group(1))
    dark = set((int(x), int(y)) for x, y in re.findall(r'M(\d+),(\d+)h1v1h-1z', svg))
    q = 4
    return [[1 if (x + q, y + q) in dark else 0 for x in range(n - 2 * q)] for y in range(n - 2 * q)]


def test_the_qr_code_reads_back_as_the_address(page):
    texts = ['http://192.168.1.20:8050/idm-phone', 'http://10.0.0.7/idm-phone',
             'https://172.16.250.199:65535/idm-phone', 'a', 'x' * 100, 'y' * 150, 'z' * 213]
    got = page.evaluate("""async (texts) => {
        const m = await import('/static/js/qr-code.js');
        return texts.map(t => [m.qrMatrix(t).map(r => r.map(v => v ? 1 : 0)), m.qrSvg(t)]);
    }""", texts)
    versions = []
    for text, (matrix, svg) in zip(texts, got):
        out = qr_reader.read(matrix)
        assert out['text'] == text and out['level'] == 'M', out
        assert svg_matrix(svg) == matrix
        versions.append(out['version'])
    assert versions[0] == 3 and versions[-1] == 10, versions
    assert page.evaluate("async () => (await import('/static/js/qr-code.js')).qrMatrix('w'.repeat(300))") is None


def test_use_a_phone_shows_the_code_and_the_address(page, e2e_server):
    import routes_idm_phone as rp
    port = int(e2e_server.rsplit(':', 1)[1].strip('/'))
    keep = (rp._lan_addresses, getattr(app_module, 'BOUND_HOST', None))
    rp._lan_addresses = lambda: ['192.168.1.20', '10.0.0.7']
    app_module.BOUND_HOST = '0.0.0.0'
    try:
        reset_project(page)
        page.evaluate("() => localStorage.removeItem('lrdIdmPhoneAddress')")
        assert page.is_visible('#idm-phone-open')
        page.click('#idm-phone-open')
        page.wait_for_selector('#idm-phone-qr svg', state='visible')
        # a dialog in the middle of the window, in the app's dialog style
        box = page.evaluate("""() => {
            const el = document.querySelector('#idm-phone-modal .modal-content');
            const c = el.getBoundingClientRect();
            const h = getComputedStyle(document.querySelector('#idm-phone-modal h2'));
            return {dx: (c.left + c.width / 2) - window.innerWidth / 2, dy: (c.top + c.height / 2) - window.innerHeight / 2,
                    top: c.top, left: c.left, w: c.width, padLeft: parseFloat(h.paddingLeft), bar: h.borderLeftWidth,
                    bg: getComputedStyle(el).backgroundColor};
        }""")
        assert abs(box['dx']) <= 1 and abs(box['dy']) <= 1, box
        assert box['top'] > 40 and box['left'] > 40 and 300 < box['w'] <= 480, box
        assert box['padLeft'] >= 12 and box['bar'] == '3px', box
        assert box['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent'), box
        qr_box = page.locator('#idm-phone-qr svg').bounding_box()
        assert qr_box['width'] >= 180 and qr_box['height'] >= 180, qr_box
        url = f'http://192.168.1.20:{port}/idm-phone'
        assert page.inner_text('#idm-phone-url') == url
        assert qr_reader.read(svg_matrix(page.inner_html('#idm-phone-qr')))['text'] == url
        # two networks: a picker, and the pick is remembered
        assert page.is_visible('#idm-phone-address')
        page.select_option('#idm-phone-address', '10.0.0.7')
        url2 = f'http://10.0.0.7:{port}/idm-phone'
        assert page.inner_text('#idm-phone-url') == url2
        assert qr_reader.read(svg_matrix(page.inner_html('#idm-phone-qr')))['text'] == url2
        page.click('#idm-phone-close')
        page.click('#idm-phone-open')
        page.wait_for_function("(u) => document.getElementById('idm-phone-url').textContent === u", arg=url2)
        page.click('#idm-phone-close')
        # set to this computer only: no code, and what to change
        app_module.BOUND_HOST = '127.0.0.1'
        page.click('#idm-phone-open')
        page.wait_for_function("() => document.getElementById('idm-phone-note').textContent.includes('this computer only')")
        assert not page.is_visible('#idm-phone-qr svg')
        note = page.inner_text('#idm-phone-note')
        assert 'set to this computer only' in note and 'All Interfaces' in note, note
        page.keyboard.press('Escape')
        assert not page.is_visible('#idm-phone-modal')
        assert not page._errors, page._errors
    finally:
        rp._lan_addresses, app_module.BOUND_HOST = keep


# ── pictures for the record ───────────────────────────────────────────────

SHOTS = os.environ.get('LRD_IDM_SHOTS')


@pytest.mark.skipif(not SHOTS, reason='set LRD_IDM_SHOTS to a folder to save the screenshots')
def test_screenshots(page, e2e_server, pw_browser):
    import routes_idm_phone as rp
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    put_marks(page, 'IdmA', 2, 2, ['0,0,0,0', '1,0,1,1', '2,1,0,0'])
    set_layout(page, 'IdmB', 2, 2)
    put_marks(page, 'IdmB', 2, 2, ['0,0,1,1', '1,1,0,0'])
    # IdmB stands on the ground (a footer): its rows count from the bottom
    page.evaluate("""() => { const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        b.riggingFooterBars = [2]; b.riggingSide = 'footer'; app.updateLayers([b], true, 'Footer'); }""")
    # two ticked Swapped, so the Swapped list shows under the open one
    for name, key in (('IdmA', '0,0,0,0'), ('IdmB', '1,1,0,0')):
        page.click(f'#idm-list .idm-row[data-idm-key="{key}"] input[data-idm-swap]')
        settled(page, lambda name=name, key=key: served_idm(page, name), lambda v, key=key: v and key in v.get('swapped', {}))
    page.evaluate("""() => { const a = window.app.project.layers.find(x => x.name === 'IdmA');
        window.app._idmSetHighlight(a.id, '1,0,1,1'); }""")
    for size in ((390, 844), (375, 667)):
        ctx, ph = open_phone(pw_browser, e2e_server, size=size)
        tag = f'{size[0]}x{size[1]}'
        try:
            ph.wait_for_timeout(500)
            ph.screenshot(path=os.path.join(SHOTS, f'idm-phone-main-dark-{tag}.png'))
            open_menu(ph)
            ph.wait_for_timeout(300)
            ph.screenshot(path=os.path.join(SHOTS, f'idm-phone-menu-dark-{tag}.png'))
            close_menu(ph)
            open_swap(ph)
            ph.wait_for_timeout(300)
            ph.screenshot(path=os.path.join(SHOTS, f'idm-phone-swap-list-dark-{tag}.png'))
            if size == (390, 844):
                ph.tap('[data-ph-side="back"]')
                ph.wait_for_timeout(200)
                ph.screenshot(path=os.path.join(SHOTS, f'idm-phone-swap-list-back-dark-{tag}.png'))
                ph.tap('[data-ph-side="front"]')
                close_swap(ph)
                ph.tap('#ph-theme')
                ph.wait_for_timeout(200)
                ph.screenshot(path=os.path.join(SHOTS, f'idm-phone-main-light-{tag}.png'))
                ph.tap('#ph-theme')
        finally:
            ctx.close()
    keep = (rp._lan_addresses, getattr(app_module, 'BOUND_HOST', None))
    rp._lan_addresses = lambda: ['192.168.1.20', '10.0.0.7']
    app_module.BOUND_HOST = '0.0.0.0'
    try:
        page.click('#idm-phone-open')
        page.wait_for_selector('#idm-phone-qr svg', state='visible')
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOTS, 'idm-phone-qr-dialog.png'))
        page.click('#idm-phone-close')
        page.evaluate("() => document.getElementById('idm-list').scrollIntoView({block: 'center'})")
        page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(SHOTS, 'idm-tab-swap-list.png'))
    finally:
        rp._lan_addresses, app_module.BOUND_HOST = keep
