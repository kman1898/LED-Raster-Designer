"""The IDM Locator's Colours (app-idm-locator.js, canvas-idm.js, app.py,
routes_project.py).

One set for the whole show, kept in project.idmField next to the field
colour and border style - saved with the show, told to every client through
PUT /api/project/idm-field and `idm_field_updated`, never an undo step, and
held to its shape by the server (app.sanitize_idm_field):

* labelColor        the Module ID labels
* moduleEdgeColor   the Lines and Ticks module edges
* cabinetEdgeColor  the Lines and Ticks cabinet edges and the Shade ring
* shade             the Shade checker's second level: a colour or a whole
                    percent of the field
* markPresets       the saved mark colours beside the toolbar's mark swatch

Each key is there only when the crew chose something; missing is Auto,
drawn exactly as before (labels the field's hue at 50%, the mark's on a
colour mark, a lit grey on black; module edges 70%, cabinet edges 50%;
shade 85%, the ring 65%), and a show without them has the five default
presets. What this file pins: every setting changes the output window's
pixels as chosen, Auto puts back the exact previous values, a chosen black
is drawn (never blocked) with a note under its swatch, the settings and
the presets survive save, load and a reload and reach a second client, the
presets pick, add and remove, and an older show draws on Auto.

Run locally:
    python -m pytest tests/test_idm_colours.py -v -p no:cacheprovider --browser chromium
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

DEFAULT_PRESETS = ['#ff1a1a', '#ffff00', '#00ffff', '#ff00ff', '#ff8000']
BLACK_NOTE = 'Black pixels can look like dead pixels on the wall.'


# ── 1. The server (no browser) ────────────────────────────────────────────

def test_the_sanitizer_keeps_chosen_colours_and_drops_the_rest():
    s = app_module.sanitize_idm_field
    base = {'color': '#ffffff', 'border': 'shade', 'moduleIds': False}
    # an older block gains nothing: Auto is no key at all
    assert s({'color': '#fff', 'border': 'shade'}) == base
    got = s({'labelColor': '#FF0000', 'moduleEdgeColor': 'abc', 'cabinetEdgeColor': '#000',
             'shade': '#0F0', 'markPresets': ['#123456']})
    assert got == {**base, 'labelColor': '#ff0000', 'moduleEdgeColor': '#aabbcc',
                   'cabinetEdgeColor': '#000000', 'shade': '#00ff00', 'markPresets': ['#123456']}
    assert s(got) == got        # idempotent
    # bad colours are Auto (no key) - black is a colour and is kept
    for junk in ('auto', 'red', '#12', '#1234567', None, 5, True, ['#fff'], {'c': 1}):
        clean = s({'labelColor': junk, 'moduleEdgeColor': junk, 'cabinetEdgeColor': junk})
        assert clean == base, (junk, clean)
    # the shade: a colour or a whole percent 0..100, rounded half up as the
    # client rounds
    assert s({'shade': 85})['shade'] == 85
    assert s({'shade': 0})['shade'] == 0
    assert s({'shade': 100})['shade'] == 100
    assert s({'shade': 42.5})['shade'] == 43
    assert s({'shade': 70.4})['shade'] == 70
    assert type(s({'shade': 70.0})['shade']) is int
    for junk in (-1, 100.5, 250, float('nan'), float('inf'), True, False, '85', '85%', 'auto', None, [85]):
        assert 'shade' not in s({'shade': junk}), junk
    # the presets: colours only, no repeats, at most 12; not a list -> none
    # (the defaults); an empty list is the crew's own and is kept
    assert s({'markPresets': ['#F00', 'nope', '#ff0000', None, 7, '#00ff00']})['markPresets'] == ['#ff0000', '#00ff00']
    assert s({'markPresets': []})['markPresets'] == []
    many = ['#%06x' % i for i in range(20)]
    assert s({'markPresets': many})['markPresets'] == many[:12]
    for junk in ('#ff0000', {'a': '#ff0000'}, None, 3):
        assert 'markPresets' not in s({'markPresets': junk}), junk
    assert app_module.IDM_MARK_PRESETS_DEFAULT == tuple(DEFAULT_PRESETS)


def test_the_route_and_the_funnels_carry_the_colours(client):
    app_module.current_project['is_pristine'] = True
    sock = socketio.test_client(flask_app, flask_test_client=client)
    want = {'color': '#ff0000', 'border': 'lines', 'moduleIds': True,
            'labelColor': '#00ff00', 'cabinetEdgeColor': '#000000', 'shade': 60,
            'markPresets': ['#ff1a1a', '#123456']}
    try:
        sock.get_received()
        resp = client.put('/api/project/idm-field', json={'origin': 'tab1', 'field': {
            'color': '#F00', 'border': 'lines', 'moduleIds': True, 'labelColor': '#0f0',
            'moduleEdgeColor': 'auto', 'cabinetEdgeColor': '#000000', 'shade': 60,
            'markPresets': ['#ff1a1a', '#123456', '#FF1A1A', 'junk']}})
        assert resp.status_code == 200
        assert resp.get_json() == {'idmField': want}
        assert app_module.current_project['idmField'] == want
        assert app_module.current_project['is_pristine'] is True
        got = [r['args'][0] for r in sock.get_received() if r['name'] == 'idm_field_updated']
        assert got == [{'field': want, 'origin': 'tab1'}], got
    finally:
        sock.disconnect()
    # both funnels hold them: the load (PUT) and the save (POST)
    project = client.get('/api/project').get_json()
    assert client.put('/api/project', json=project).get_json()['idmField'] == want
    project['idmField'] = {**want, 'shade': 'bogus', 'labelColor': 'blue', 'markPresets': 'x'}
    restored = client.put('/api/project', json=project).get_json()['idmField']
    assert restored == {'color': '#ff0000', 'border': 'lines', 'moduleIds': True,
                        'cabinetEdgeColor': '#000000'}
    project['idmField'] = {**want, 'shade': 101}
    assert client.post('/api/project', json=project).status_code == 200
    assert 'shade' not in app_module.current_project['idmField']
    # an older show's block loads exactly as it was: no Colours keys
    project['idmField'] = {'color': '#00ff00', 'border': 'ticks', 'moduleIds': False}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['idmField'] == {'color': '#00ff00', 'border': 'ticks', 'moduleIds': False}
    assert app_module.normalize_idm_field(restored) is False


# ── 2. In the browser ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_idm_field_highlight import (  # noqa: E402
    _new_page, click_field, open_output, open_tab, point, reset_project,
    served_field, set_layout, served_idm, wait_layers, wait_pixel,
)
from test_idm_module_ids import ink, set_ids, settled_ink  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


ROWS = ('labelColor', 'moduleEdgeColor', 'cabinetEdgeColor', 'shade')


def set_colour(pg, key, hex_):
    """A colour through a row's swatch, the way the app's colour picker
    writes it (the value, then input and change)."""
    pg.evaluate("""([key, hex]) => {
        const c = document.querySelector(`input[data-idm-colour="${key}"]`);
        c.value = hex;
        c.dispatchEvent(new Event('input', {bubbles: true}));
        c.dispatchEvent(new Event('change', {bubbles: true}));
    }""", [key, hex_])
    settled(pg, lambda: (served_field(pg) or {}).get(key), lambda v: v == hex_)


def set_auto(pg, key):
    pg.click(f'[data-idm-auto="{key}"]')
    settled(pg, lambda: served_field(pg) or {}, lambda v: key not in v)
    assert key not in (served_field(pg) or {})


def set_percent(pg, n):
    pg.fill('#idm-shade-percent', str(n))
    pg.press('#idm-shade-percent', 'Enter')
    settled(pg, lambda: (served_field(pg) or {}).get('shade'), lambda v: v == n)


def auto_pressed(pg):
    return {k: pg.get_attribute(f'[data-idm-auto="{k}"]', 'aria-pressed') == 'true' for k in ROWS}


def notes_shown(pg):
    return {k: pg.is_visible(f'[data-idm-black="{k}"]') for k in ROWS}


def presets(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#idm-mark-presets [data-idm-preset]')]"
                       ".map(b => b.dataset.idmPreset)")


def test_an_old_show_draws_on_auto_with_the_default_presets(page):
    reset_project(page)
    assert served_field(page) is None
    spec = page.evaluate("() => window.canvasRenderer.idmFieldSpec()")
    assert {k: spec[k] for k in ROWS} == {k: None for k in ROWS}
    assert auto_pressed(page) == {k: True for k in ROWS}
    assert notes_shown(page) == {k: False for k in ROWS}
    assert page.input_value('#idm-shade-percent') == ''
    # each swatch shows what Auto draws in on the white field
    assert page.input_value('#idm-label-colour') == '#808080'
    assert page.input_value('#idm-module-edge-colour') == '#b3b3b3'
    assert page.input_value('#idm-cabinet-edge-colour') == '#a6a6a6'   # the shade ring, 65%
    assert page.input_value('#idm-shade-colour') == '#d9d9d9'
    click_field(page, None, 'lines')
    assert page.input_value('#idm-cabinet-edge-colour') == '#808080'   # lines: 50%
    assert presets(page) == DEFAULT_PRESETS
    # setting the field writes no Colours keys
    want = {'color': '#ffffff', 'border': 'lines', 'moduleIds': False}
    assert settled(page, lambda: served_field(page), lambda v: v == want) == want
    assert not page._errors, page._errors


def test_the_shade_level_as_a_percent_or_a_colour_and_auto_puts_it_back(page):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    try:
        # Auto (white, shade): module (1,0) at 85%, the ring at 65%
        wait_pixel(out, 32, 32, (255, 255, 255), tol=0)
        wait_pixel(out, 96, 32, (217, 217, 217), tol=0)
        wait_pixel(out, 0, 32, (166, 166, 166), tol=0)
        # a percent of the field
        set_percent(page, 50)
        wait_pixel(out, 96, 32, (128, 128, 128), tol=0)
        wait_pixel(out, 32, 96, (128, 128, 128), tol=0)
        wait_pixel(out, 32, 32, (255, 255, 255), tol=0)
        wait_pixel(out, 0, 32, (166, 166, 166), tol=0)     # the ring is the cabinet edge's
        assert page.input_value('#idm-shade-percent') == '50'
        assert auto_pressed(page)['shade'] is False
        assert page.input_value('#idm-shade-colour') == '#808080'
        # ... of a colour field too
        click_field(page, '#ff0000')
        wait_pixel(out, 96, 32, (128, 0, 0), tol=0)
        click_field(page, '#ffffff')
        # out of range is held to 0..100
        page.fill('#idm-shade-percent', '140')
        page.press('#idm-shade-percent', 'Enter')
        settled(page, lambda: served_field(page).get('shade'), lambda v: v == 100)
        assert served_field(page)['shade'] == 100
        wait_pixel(out, 96, 32, (255, 255, 255), tol=0)
        # a colour
        set_colour(page, 'shade', '#00ff00')
        wait_pixel(out, 96, 32, (0, 255, 0), tol=0)
        wait_pixel(out, 32, 32, (255, 255, 255), tol=0)
        assert page.input_value('#idm-shade-percent') == ''
        assert page.evaluate("() => document.querySelector('#idm-shade-colour')"
                             ".closest('.idm-swatch-custom').classList.contains('active')")
        # Auto: exactly the previous levels
        set_auto(page, 'shade')
        wait_pixel(out, 96, 32, (217, 217, 217), tol=0)
        wait_pixel(out, 0, 32, (166, 166, 166), tol=0)
        assert auto_pressed(page)['shade'] is True
        # and on black Auto still lifts the levels
        click_field(page, '#000000')
        wait_pixel(out, 96, 32, (26, 26, 26), tol=0)
        wait_pixel(out, 0, 32, (52, 52, 52), tol=0)
    finally:
        out.close()
    assert not page._errors, page._errors


def test_the_edge_colours_change_lines_ticks_and_the_shade_ring(page):
    cid = reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    try:
        # the shade ring takes the cabinet edge colour
        set_colour(page, 'cabinetEdgeColor', '#0000ff')
        wait_pixel(out, 0, 32, (0, 0, 255), tol=0)
        wait_pixel(out, 127, 32, (0, 0, 255), tol=0)
        wait_pixel(out, 96, 32, (217, 217, 217), tol=0)      # the checker unchanged
        # Lines: module edges their own colour, cabinet edges the chosen one
        click_field(page, None, 'lines')
        wait_pixel(out, 64, 32, (179, 179, 179), tol=0)      # module edge on Auto
        wait_pixel(out, 0, 32, (0, 0, 255), tol=0)
        set_colour(page, 'moduleEdgeColor', '#ff00ff')
        wait_pixel(out, 64, 32, (255, 0, 255), tol=0)
        wait_pixel(out, 32, 64, (255, 0, 255), tol=0)
        wait_pixel(out, 32, 32, (255, 255, 255), tol=0)
        # chosen colours stay as chosen on another field
        click_field(page, '#00ff00')
        wait_pixel(out, 64, 32, (255, 0, 255), tol=0)
        wait_pixel(out, 0, 32, (0, 0, 255), tol=0)
        click_field(page, '#ffffff')
        # Ticks
        click_field(page, None, 'ticks')
        wait_pixel(out, 66, 0, (255, 0, 255), tol=0)         # module (1,0)'s top-left tick
        wait_pixel(out, 64, 3, (255, 0, 255), tol=0)
        wait_pixel(out, 1, 1, (0, 0, 255), tol=0)            # the cabinet corner
        wait_pixel(out, 96, 0, (255, 255, 255), tol=0)       # mid-edge: no line
        # Auto: exactly the previous levels, ticks then lines then shade
        set_auto(page, 'moduleEdgeColor')
        set_auto(page, 'cabinetEdgeColor')
        wait_pixel(out, 66, 0, (179, 179, 179), tol=0)
        wait_pixel(out, 1, 1, (128, 128, 128), tol=0)
        click_field(page, None, 'lines')
        wait_pixel(out, 64, 32, (179, 179, 179), tol=0)
        wait_pixel(out, 0, 32, (128, 128, 128), tol=0)
        click_field(page, None, 'shade')
        wait_pixel(out, 0, 32, (166, 166, 166), tol=0)
        assert auto_pressed(page) == {k: True for k in ROWS}
        assert served_field(page) == {'color': '#ffffff', 'border': 'shade', 'moduleIds': False}
    finally:
        out.close()
    assert not page._errors, page._errors


def test_the_label_colour_and_auto_puts_it_back(page):
    cid = reset_project(page)
    click_field(page, '#ffffff', 'none')
    set_layout(page, 'IdmA', 2, 2)
    set_ids(page, True)
    out = open_output(page, cid)
    try:
        # Auto: the field's hue at 50%
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0)
        # chosen: drawn as chosen, everywhere
        set_colour(page, 'labelColor', '#ff0000')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20, ink_rgb=(255, 0, 0))
        assert ink(out, (16, 16, 32, 32))['hit'] == 0           # no 128 grey left
        settled_ink(out, (64 + 16, 64 + 16, 32, 32), lambda v: v['hit'] > 20, ink_rgb=(255, 0, 0))
        # ... on a colour mark too (Auto there is the mark's hue at 50%)
        page.evaluate("""() => {
            const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
            l.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#ff1a1a'}}};
            app.updateLayers([l], true, 'Mark');
            window.canvasRenderer.render();
        }""")
        set_colour(page, 'labelColor', '#0000ff')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20,
                    ink_rgb=(0, 0, 255), field=(255, 26, 26))
        settled_ink(out, (64 + 16, 16, 32, 32), lambda v: v['hit'] > 20, ink_rgb=(0, 0, 255))
        # Auto: back to exactly the previous inks
        set_auto(page, 'labelColor')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0,
                    ink_rgb=(128, 13, 13), field=(255, 26, 26))
        settled_ink(out, (64 + 16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0)
        # the swatch on Auto shows the auto ink of the field
        assert page.input_value('#idm-label-colour') == '#808080'
    finally:
        out.close()
    assert not page._errors, page._errors


def test_a_black_choice_is_drawn_and_carries_the_note(page):
    cid = reset_project(page)
    click_field(page, '#ffffff', 'lines')
    set_layout(page, 'IdmA', 2, 2)
    set_ids(page, True)
    out = open_output(page, cid)
    try:
        assert notes_shown(page) == {k: False for k in ROWS}
        set_colour(page, 'moduleEdgeColor', '#000000')
        wait_pixel(out, 64, 32, (0, 0, 0), tol=0)                # drawn, not blocked
        assert notes_shown(page) == {'labelColor': False, 'moduleEdgeColor': True,
                                     'cabinetEdgeColor': False, 'shade': False}
        assert page.inner_text('[data-idm-black="moduleEdgeColor"]') == BLACK_NOTE
        set_colour(page, 'cabinetEdgeColor', '#000000')
        wait_pixel(out, 0, 32, (0, 0, 0), tol=0)
        set_colour(page, 'labelColor', '#000000')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['dark'] > 20, ink_rgb=(0, 0, 0))
        # the shade: a black colour, or 0%
        click_field(page, None, 'shade')
        # (sampled clear of module (1,0)'s centred label)
        set_percent(page, 0)
        wait_pixel(out, 68, 6, (0, 0, 0), tol=0)
        assert notes_shown(page) == {k: True for k in ROWS}
        set_percent(page, 40)
        wait_pixel(out, 68, 6, (102, 102, 102), tol=0)
        assert notes_shown(page)['shade'] is False
        set_colour(page, 'shade', '#000000')
        assert notes_shown(page)['shade'] is True
        # a near-black that is not pure black: no note
        set_colour(page, 'labelColor', '#010101')
        assert notes_shown(page)['labelColor'] is False
        # Auto clears every note
        for k in ROWS:
            set_auto(page, k)
        assert notes_shown(page) == {k: False for k in ROWS}
    finally:
        out.close()
    assert not page._errors, page._errors


def test_the_colours_reach_a_second_client_survive_save_and_load_and_are_never_undone(page, e2e_server, pw_browser):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    context, other = _new_page(pw_browser, e2e_server)
    want = {'color': '#ffffff', 'border': 'lines', 'moduleIds': False,
            'labelColor': '#112233', 'moduleEdgeColor': '#445566', 'cabinetEdgeColor': '#778899',
            'shade': 70}
    try:
        wait_layers(other)
        before = page.evaluate("() => window.app.historyIndex")
        click_field(page, None, 'lines')
        set_colour(page, 'labelColor', '#112233')
        set_colour(page, 'moduleEdgeColor', '#445566')
        set_colour(page, 'cabinetEdgeColor', '#778899')
        set_percent(page, 70)
        assert served_field(page) == want
        got = settled(other, lambda: other.evaluate("() => window.app.project.idmField || null"),
                      lambda v: v == want)
        assert got == want, got
        open_tab(other)
        assert auto_pressed(other) == {k: False for k in ROWS}
        assert other.input_value('#idm-label-colour') == '#112233'
        assert other.input_value('#idm-module-edge-colour') == '#445566'
        assert other.input_value('#idm-cabinet-edge-colour') == '#778899'
        assert other.input_value('#idm-shade-percent') == '70'
        # and back the other way: Auto from the other client
        other.click('[data-idm-auto="labelColor"]')
        got = settled(page, lambda: page.evaluate("() => window.app.project.idmField"),
                      lambda v: 'labelColor' not in v)
        assert 'labelColor' not in got
        assert page.get_attribute('[data-idm-auto="labelColor"]', 'aria-pressed') == 'true'
        set_colour(page, 'labelColor', '#112233')
        settled(other, lambda: other.evaluate("() => window.app.project.idmField"), lambda v: v == want)
        # never an undo step: none so far; a mark (one step), a colour
        # change (none), then undo takes the mark and leaves the colour
        assert page.evaluate("() => window.app.historyIndex") == before
        pt = point(page, 'IdmA', 0, 0, 0, 0)
        page.mouse.click(pt['x'], pt['y'])
        settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,0,0,0' in v['marks'])
        page.mouse.move(5, 5)
        assert page.evaluate("() => window.app.historyIndex") == before + 1
        set_colour(page, 'moduleEdgeColor', '#abcdef')
        assert page.evaluate("() => window.app.historyIndex") == before + 1
        page.evaluate("() => window.app.undo()")
        settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and v['marks'] == {})
        page.wait_for_timeout(300)
        assert page.evaluate("() => window.app.project.idmField.moduleEdgeColor") == '#abcdef'
        assert served_field(page)['moduleEdgeColor'] == '#abcdef'
        set_colour(page, 'moduleEdgeColor', '#445566')
        assert not other._errors, other._errors
    finally:
        context.close()
    # the show as a file: saved, then loaded back through the load funnel
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(p)});
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(p)});
        window.app.loadProject();
    }""")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.project.idmField") == want
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.project.idmField") == want
    open_tab(page)
    assert auto_pressed(page) == {k: False for k in ROWS}
    assert page.input_value('#idm-label-colour') == '#112233'
    assert page.input_value('#idm-shade-percent') == '70'
    assert not page._errors, page._errors


def test_the_mark_presets_pick_add_remove_and_persist(page, e2e_server, pw_browser):
    reset_project(page)
    set_layout(page, 'IdmA', 2, 2)
    assert presets(page) == DEFAULT_PRESETS
    assert page.is_visible('#idm-mark-presets [data-idm-preset="#ffff00"]')
    # pick: the mark swatch takes it, and the next mark is that colour
    page.click('#idm-mark-presets [data-idm-preset="#ffff00"]')
    assert page.input_value('#idm-color') == '#ffff00'
    assert page.get_attribute('[data-idm-preset="#ffff00"]', 'aria-pressed') == 'true'
    assert page.get_attribute('[data-idm-preset="#ff1a1a"]', 'aria-pressed') == 'false'
    pt = point(page, 'IdmA', 0, 0, 0, 0)
    page.mouse.click(pt['x'], pt['y'])
    got = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and '0,0,0,0' in v['marks'])
    assert got['marks']['0,0,0,0'] == {'style': 'color', 'color': '#ffff00'}
    page.mouse.move(5, 5)
    # add: the mark swatch's colour joins the show's presets
    page.evaluate("""() => { const c = document.getElementById('idm-color');
        c.value = '#123456'; c.dispatchEvent(new Event('input', {bubbles: true}));
        c.dispatchEvent(new Event('change', {bubbles: true})); }""")
    page.click('#idm-preset-add')
    want = DEFAULT_PRESETS + ['#123456']
    got = settled(page, lambda: (served_field(page) or {}).get('markPresets'), lambda v: v == want)
    assert got == want, got
    assert presets(page) == want
    assert page.get_attribute('[data-idm-preset="#123456"]', 'aria-pressed') == 'true'
    # adding it again changes nothing
    page.click('#idm-preset-add')
    page.wait_for_timeout(300)
    assert served_field(page)['markPresets'] == want
    # a second client gets them
    context, other = _new_page(pw_browser, e2e_server)
    try:
        wait_layers(other)
        got = settled(other, lambda: other.evaluate("() => (window.app.project.idmField || {}).markPresets"),
                      lambda v: v == want)
        assert got == want
        open_tab(other)
        assert presets(other) == want
        # remove with the x (it shows on hover) ...
        page.hover('[data-idm-preset="#00ffff"]')
        page.click('[data-idm-preset-del="#00ffff"]')
        want = ['#ff1a1a', '#ffff00', '#ff00ff', '#ff8000', '#123456']
        got = settled(page, lambda: (served_field(page) or {}).get('markPresets'), lambda v: v == want)
        assert got == want, got
        # ... or a right-click, which opens no menu
        page.click('[data-idm-preset="#ff00ff"]', button='right')
        want = ['#ff1a1a', '#ffff00', '#ff8000', '#123456']
        got = settled(page, lambda: (served_field(page) or {}).get('markPresets'), lambda v: v == want)
        assert got == want, got
        assert presets(page) == want
        assert not page.is_visible('#context-menu')
        settled(other, lambda: presets(other), lambda v: v == want)
        assert presets(other) == want
        assert not other._errors, other._errors
    finally:
        context.close()
    # the field's other settings are untouched by the presets
    assert served_field(page)['color'] == '#ffffff' and 'shade' not in served_field(page)
    # the presets persist through a reload
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    open_tab(page)
    assert presets(page) == want
    # removing every one leaves none - not the defaults back
    for c in list(want):
        page.click(f'[data-idm-preset="{c}"]', button='right')
    got = settled(page, lambda: (served_field(page) or {}).get('markPresets'), lambda v: v == [])
    assert got == []
    assert presets(page) == []
    assert not page._errors, page._errors


SHOT = os.environ.get('LRD_IDM_COLOURS_SHOT')


@pytest.mark.skipif(not SHOT, reason='set LRD_IDM_COLOURS_SHOT to a .png path to save the screenshot')
def test_screenshot(page):
    reset_project(page)
    page.evaluate("""async () => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const b = app.project.layers.find(x => x.name === 'IdmB');
        a.idm = {modulesX: 2, modulesY: 2, marks: {'1,0,1,0': {style: 'color', color: '#ff1a1a'}}};
        b.idm = {modulesX: 4, modulesY: 4, marks: {'0,1,2,1': {style: 'x', color: '#0050ff'}}};
        app.updateLayers([a, b], true, 'Modules');
    }""")
    page.wait_for_timeout(600)
    click_field(page, '#ffffff', 'lines')
    set_ids(page, True)
    set_colour(page, 'labelColor', '#0050ff')
    set_colour(page, 'moduleEdgeColor', '#00b050')
    set_colour(page, 'cabinetEdgeColor', '#000000')
    set_percent(page, 70)
    page.click('#idm-mark-presets [data-idm-preset="#ff00ff"]')
    page.evaluate("""() => { const r = window.canvasRenderer;
        r.zoom = Math.min((r.canvas.clientWidth - 40) / 920, (r.canvas.clientHeight - 40) / 320);
        r.panX = 20; r.panY = 20; r.render();
        const s = document.querySelector('.idm-colours'); if (s) s.scrollIntoView({block: 'center'}); }""")
    page.mouse.move(5, 5)
    page.wait_for_timeout(400)
    page.screenshot(path=SHOT)
