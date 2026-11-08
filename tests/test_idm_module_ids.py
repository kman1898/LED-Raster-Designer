"""The IDM Locator's Module ID labels and the stored live highlight
(app-idm-locator.js, canvas-idm.js, app.py, routes_project.py).

What this file pins:

* Module ID: project.idmField.moduleIds, a switch in the tab (off by
  default; app.sanitize_idm_field holds it to a bool, a missing key is
  off). It saves with the show, reaches a second client through the field
  route, and is never an undo step. On, every module carries its label -
  the screen's Cabinet ID style run over the cabinet's own module grid,
  starting again in every cabinet (canvas-idm idmModuleLabeler), the very
  label the locator list and the highlight readout print, a half cabinet's
  modules labelled as the same modules of a whole one - in the app and in
  the output window's frame (pixels); off, none. Changing the style in the
  Cabinet ID tab changes them, and they sit where its Label Position puts
  the cabinet IDs (centred or top-left). They are never black (an unlit
  pixel would hide or fake a dead one): the field's hue at 50% (128 grey
  on white, 128,0,0 on red), a lit grey on black, a colour mark's hue at
  50% on the mark. They turn with a turned screen, and modules too small
  for a legible label carry none.
* The stored highlight: project.idmHighlight = {layerId, key} | None, kept
  by the server from the `idm_highlight` event only when it names a module
  that exists, never written by a save, held in the load funnel, cleared
  when its screen or module goes, and a pristine project stays pristine. A
  client that connects later (or reloads) shows it at once, a saved show
  opens with it, an undo never moves it, and Esc clears it for everyone.

Run locally:
    python -m pytest tests/test_idm_module_ids.py -v -p no:cacheprovider --browser chromium
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
from app import app as flask_app, socketio  # noqa: E402


# ── 1. The server (no browser) ────────────────────────────────────────────

def test_the_module_id_switch_is_a_bool_and_missing_is_off():
    s = app_module.sanitize_idm_field
    assert s({'color': '#fff'})['moduleIds'] is False
    assert s({'moduleIds': True})['moduleIds'] is True
    for junk in ('yes', 1, 'true', None, [True], {'on': True}):
        assert s({'moduleIds': junk})['moduleIds'] is False, junk
    on = s({'color': '#00FF00', 'border': 'lines', 'moduleIds': True})
    assert on == {'color': '#00ff00', 'border': 'lines', 'moduleIds': True}
    assert s(on) == on


def test_the_field_route_carries_the_switch_and_keeps_a_pristine_project(client):
    app_module.current_project['is_pristine'] = True
    sock = socketio.test_client(flask_app, flask_test_client=client)
    try:
        sock.get_received()
        resp = client.put('/api/project/idm-field',
                          json={'field': {'color': '#ffffff', 'border': 'shade', 'moduleIds': True},
                                'origin': 'tab1'})
        want = {'color': '#ffffff', 'border': 'shade', 'moduleIds': True}
        assert resp.get_json() == {'idmField': want}
        assert app_module.current_project['idmField'] == want
        assert app_module.current_project['is_pristine'] is True
        got = [r['args'][0] for r in sock.get_received() if r['name'] == 'idm_field_updated']
        assert got == [{'field': want, 'origin': 'tab1'}], got
    finally:
        sock.disconnect()
    # both funnels keep it; a file without the key loads without it
    project = client.get('/api/project').get_json()
    assert client.put('/api/project', json=project).get_json()['idmField'] == want
    project['idmField'] = {'color': '#ffffff', 'border': 'shade'}
    assert client.put('/api/project', json=project).get_json()['idmField']['moduleIds'] is False


def _screen(client, name='S', columns=2, rows=2, size=128, modules=(2, 2)):
    layer = client.post('/api/layer/add', json={
        'name': name, 'columns': columns, 'rows': rows,
        'cabinet_width': size, 'cabinet_height': size}).get_json()
    if modules != (1, 1):
        layer = client.put(f"/api/layer/{layer['id']}", json={
            'idm': {'modulesX': modules[0], 'modulesY': modules[1], 'marks': {}}}).get_json()
    return layer


def test_the_server_keeps_the_highlight_and_a_late_client_gets_it(client):
    layer = _screen(client)
    app_module.current_project['is_pristine'] = True
    a = socketio.test_client(flask_app, flask_test_client=client)
    try:
        a.get_received()
        a.emit('idm_highlight', {'layerId': layer['id'], 'key': '1,1,0,1', 'origin': 'tablet'})
        want = {'layerId': layer['id'], 'key': '1,1,0,1'}
        assert app_module.current_project['idmHighlight'] == want
        # view state: a pristine project stays pristine
        assert app_module.current_project['is_pristine'] is True
        # a client that connects now is handed it with the project
        late = socketio.test_client(flask_app, flask_test_client=client)
        try:
            data = [r['args'][0] for r in late.get_received() if r['name'] == 'project_data']
            assert data and data[0]['idmHighlight'] == want
        finally:
            late.disconnect()
        assert client.get('/api/project').get_json()['idmHighlight'] == want
        # a module the screen does not have is relayed but never kept
        a.emit('idm_highlight', {'layerId': layer['id'], 'key': '5,0,0,0', 'origin': 'tablet'})
        assert app_module.current_project['idmHighlight'] is None
        a.emit('idm_highlight', {'layerId': layer['id'], 'key': '0,0,1,0', 'origin': 'tablet'})
        assert app_module.current_project['idmHighlight'] == {'layerId': layer['id'], 'key': '0,0,1,0'}
        # Esc / Clear highlight: cleared on the server too
        a.emit('idm_highlight', {'layerId': None, 'key': None, 'origin': 'tablet'})
        assert app_module.current_project['idmHighlight'] is None
    finally:
        a.disconnect()


def test_the_funnels_hold_the_highlight_and_a_save_never_writes_it(client):
    layer = _screen(client)
    lid = layer['id']
    project = client.get('/api/project').get_json()
    # the load funnel keeps a file's highlight on a module that is there...
    project['idmHighlight'] = {'layerId': lid, 'key': ' 1, 0 ,1,1'}
    restored = client.put('/api/project', json=project).get_json()
    assert restored['idmHighlight'] == {'layerId': lid, 'key': '1,0,1,1'}
    # ... and clears one on a module that is not, or junk
    for bad in ({'layerId': lid, 'key': '0,0,2,0'}, {'layerId': 999, 'key': '0,0,0,0'},
                {'layerId': str(lid), 'key': '0,0,0,0'}, 'A1', [1]):
        project['idmHighlight'] = bad
        assert client.put('/api/project', json=project).get_json()['idmHighlight'] is None, bad
    # an older file has no key and gets none
    project.pop('idmHighlight')
    assert 'idmHighlight' not in client.put('/api/project', json=project).get_json()
    # a save (a sidebar reorder, the Save button) carries whatever copy that
    # client had: the server's own stays
    sock = socketio.test_client(flask_app, flask_test_client=client)
    try:
        sock.emit('idm_highlight', {'layerId': lid, 'key': '0,1,1,0', 'origin': 'x'})
    finally:
        sock.disconnect()
    project['idmHighlight'] = {'layerId': lid, 'key': '0,0,0,0'}
    assert client.post('/api/project', json=project).status_code == 200
    assert app_module.current_project['idmHighlight'] == {'layerId': lid, 'key': '0,1,1,0'}


def test_the_highlight_goes_with_its_module_or_screen(client):
    layer = _screen(client)
    other = _screen(client, name='T')
    lid = layer['id']

    def put_hl(key, layer_id=lid):
        sock = socketio.test_client(flask_app, flask_test_client=client)
        try:
            sock.emit('idm_highlight', {'layerId': layer_id, 'key': key, 'origin': 'x'})
        finally:
            sock.disconnect()
        assert app_module.current_project['idmHighlight'] == {'layerId': layer_id, 'key': key}

    # fewer modules: the highlighted one is gone
    put_hl('0,0,1,1')
    client.put(f'/api/layer/{lid}', json={'idm': {'modulesX': 1, 'modulesY': 1, 'marks': {}}})
    assert app_module.current_project['idmHighlight'] is None
    # an edit that keeps the module keeps the highlight
    put_hl('1,0,0,0')
    client.put(f'/api/layer/{lid}', json={'name': 'S2'})
    assert app_module.current_project['idmHighlight'] == {'layerId': lid, 'key': '1,0,0,0'}
    # its cabinet blanked
    served = next(x for x in app_module.current_project['layers'] if x['id'] == lid)
    panel = next(p for p in served['panels'] if p['col'] == 1 and p['row'] == 0)
    client.post(f"/api/layer/{lid}/panel/{panel['id']}/toggle_hidden")
    assert app_module.current_project['idmHighlight'] is None
    # its screen deleted (another screen's delete leaves it alone)
    put_hl('0,0,0,0')
    client.delete(f"/api/layer/{other['id']}")
    assert app_module.current_project['idmHighlight'] == {'layerId': lid, 'key': '0,0,0,0'}
    resp = client.delete(f'/api/layer/{lid}').get_json()
    assert app_module.current_project['idmHighlight'] is None
    assert resp['idmHighlight'] is None


# ── 2. In the browser ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_idm_field_highlight import (  # noqa: E402
    _new_page, click_field, hl, open_output, open_tab, point, reset_project,
    served_field, set_layout, wait_layers,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


def fresh(pg):
    """The two-screen project of test_idm_field_highlight (IdmA 3 x 2
    cabinets of 128 at 0,0; IdmB 2 x 2 of 160 at 600,0), the field white
    with no borders and Module ID off."""
    cid = reset_project(pg)
    click_field(pg, '#ffffff', 'none')
    set_ids(pg, False)
    return cid


def set_ids(pg, on):
    pressed = pg.get_attribute('#idm-module-ids', 'aria-pressed') == 'true'
    if pressed != on:
        pg.click('#idm-module-ids')
    want = 'true' if on else 'false'
    assert pg.get_attribute('#idm-module-ids', 'aria-pressed') == want
    settled(pg, lambda: (served_field(pg) or {}).get('moduleIds', False), lambda v: v is on)


def labels(pg, name, scale=1):
    """The Module ID labels the renderer works out for screen `name`."""
    return pg.evaluate("""([name, scale]) => {
        const r = window.canvasRenderer, app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        const out = r.idmModuleLabels(l, {scale});
        return {px: out.px, position: out.position, sites: out.sites.map(s => ({
            key: s.key, text: s.text, x: s.x, y: s.y, w: s.w, h: s.h, color: s.color}))};
    }""", [name, scale])


def texts(pg, name):
    """key -> the label the Module ID labels draw on screen `name`."""
    return {s['key']: s['text'] for s in labels(pg, name)['sites']}


def list_labels(pg, name):
    """key -> the module label the locator list and highlight readout give."""
    return pg.evaluate("""(name) => {
        const r = window.canvasRenderer, app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        const out = {};
        r.idmLayerCells(l).forEach(({panel, cells}) => cells.forEach(c => {
            const k = r.idmCellKey(panel, c);
            out[k] = app._idmDescribe(l, k).module;
        }));
        return out;
    }""", name)


def set_style(pg, name, style):
    pg.evaluate("""([name, style]) => {
        const app = window.app, l = app.project.layers.find(x => x.name === name);
        l.cabinetIdStyle = style;
        app.updateLayers([l], true, 'Style');
        window.canvasRenderer.render();
    }""", [name, style])


# The output frame's pixels in a rectangle, against the colour the labels
# should be drawn in (`ink`) and the field (`field`): how many are the ink
# (within 3), how many the field (within 2), and how many are dark - every
# channel under 40, an unlit LED. Never black means `dark` stays 0.
INK_JS = """([x, y, w, h, ink, field]) => {
    const c = document.getElementById('output-canvas');
    if (!c.width) return null;
    const d = c.getContext('2d').getImageData(x, y, w, h).data;
    const near = (i, rgb, t) => Math.abs(d[i] - rgb[0]) <= t && Math.abs(d[i + 1] - rgb[1]) <= t
        && Math.abs(d[i + 2] - rgb[2]) <= t;
    let hit = 0, fieldPx = 0, dark = 0;
    for (let i = 0; i < d.length; i += 4) {
        if (near(i, ink, 3)) hit++;
        if (near(i, field, 2)) fieldPx++;
        if (d[i] < 40 && d[i + 1] < 40 && d[i + 2] < 40) dark++;
    }
    return {hit, field: fieldPx, dark, total: w * h};
}"""

WHITE = (255, 255, 255)
GREY50 = (128, 128, 128)


def ink(out, rect, ink_rgb=GREY50, field=WHITE):
    return out.evaluate(INK_JS, [*rect, list(ink_rgb), list(field)])


def settled_ink(out, rect, ok, ink_rgb=GREY50, field=WHITE, timeout=6000):
    got = settled(out, lambda: ink(out, rect, ink_rgb, field), lambda v: v is not None and ok(v), timeout)
    assert got is not None and ok(got), (rect, got)
    return got


def patch(out, rect):
    """The output's pixels in a rectangle, as rows of [r, g, b]."""
    return out.evaluate("""([x, y, w, h]) => {
        const d = document.getElementById('output-canvas').getContext('2d').getImageData(x, y, w, h).data;
        const rows = [];
        for (let j = 0; j < h; j++) {
            const row = [];
            for (let i = 0; i < w; i++) { const k = (j * w + i) * 4; row.push([d[k], d[k + 1], d[k + 2]]); }
            rows.push(row);
        }
        return rows;
    }""", list(rect))


def test_the_switch_reaches_a_second_client_and_is_never_an_undo_step(page, e2e_server, pw_browser):
    fresh(page)
    assert page.get_attribute('#idm-module-ids', 'aria-pressed') == 'false'
    assert labels(page, 'IdmA')['sites'] == []
    context, other = _new_page(pw_browser, e2e_server)
    try:
        wait_layers(other)
        before = page.evaluate("() => window.app.historyIndex")
        set_ids(page, True)
        assert served_field(page)['moduleIds'] is True
        got = settled(other, lambda: other.evaluate("() => (window.app.project.idmField || {}).moduleIds"),
                      lambda v: v is True)
        assert got is True
        open_tab(other)
        assert other.get_attribute('#idm-module-ids', 'aria-pressed') == 'true'
        assert page.evaluate("() => window.app.historyIndex") == before
        # off from the other client
        other.click('#idm-module-ids')
        got = settled(page, lambda: page.evaluate("() => window.app.project.idmField.moduleIds"),
                      lambda v: v is False)
        assert got is False
        assert page.get_attribute('#idm-module-ids', 'aria-pressed') == 'false'
        assert not other._errors, other._errors
    finally:
        context.close()


def test_the_switch_survives_save_and_load(page):
    fresh(page)
    set_ids(page, True)
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        const text = JSON.stringify(p);
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: text});
        window.app.loadProject();
    }""")
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.app.project.idmField.moduleIds") is True
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    open_tab(page)
    assert page.get_attribute('#idm-module-ids', 'aria-pressed') == 'true'
    set_ids(page, False)


def test_the_labels_are_on_the_output_when_on_and_never_black(page):
    cid = fresh(page)
    set_layout(page, 'IdmA', 2, 2)        # 64 px modules
    out = open_output(page, cid)
    try:
        # off: the white field, nothing else, in A1's first module
        settled_ink(out, (0, 0, 64, 64), lambda v: v['field'] == v['total'])
        set_ids(page, True)
        # on: type in the middle of every module in the field's hue at 50%
        # (white -> 128 grey) - never an unlit pixel - the rim untouched
        for x, y in [(16, 16), (64 + 16, 64 + 16), (256 + 64 + 16, 64 + 16)]:
            settled_ink(out, (x, y, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0)
        assert ink(out, (0, 0, 6, 64))['field'] == 384
        assert ink(out, (0, 0, 384, 256))['dark'] == 0
        # red: 128, 0, 0 on the red field
        click_field(page, '#ff0000')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0,
                    ink_rgb=(128, 0, 0), field=(255, 0, 0))
        # blue: 0, 0, 128
        click_field(page, '#0000ff')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20, ink_rgb=(0, 0, 128), field=(0, 0, 255))
        # black: half of black is still dark, so a lit grey
        click_field(page, '#000000')
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20,
                    ink_rgb=(102, 102, 102), field=(0, 0, 0))
        # the shade's alternate module (85% white): still the field at 50%
        click_field(page, '#ffffff', 'shade')
        settled_ink(out, (64 + 16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0,
                    field=(217, 217, 217))
        # a colour mark (red on white): the mark's hue at 50%
        page.evaluate("""() => {
            const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
            l.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,0,0': {style: 'color', color: '#ff1a1a'}}};
            app.updateLayers([l], true, 'Mark');
            window.canvasRenderer.render();
        }""")
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20 and v['dark'] == 0,
                    ink_rgb=(128, 13, 13), field=(255, 26, 26))
        # off again: gone
        click_field(page, None, 'none')
        set_ids(page, False)
        settled_ink(out, (64, 0, 64, 64), lambda v: v['field'] == v['total'])
        settled_ink(out, (64, 64, 64, 64), lambda v: v['field'] == v['total'])
    finally:
        out.close()
    assert not page._errors, page._errors


def test_the_labels_follow_the_cabinet_id_label_position(page):
    cid = fresh(page)
    set_layout(page, 'IdmA', 2, 2)
    set_ids(page, True)
    out = open_output(page, cid)
    try:
        # centred (the default): in the middle of the module, none in its corner
        lab = labels(page, 'IdmA')
        assert lab['position'] == 'center'
        s = next(x for x in lab['sites'] if x['key'] == '0,0,0,0')
        assert abs((s['x'] + s['w'] / 2) - 32) < 1 and abs((s['y'] + s['h'] / 2) - 32) < 1, s
        settled_ink(out, (16, 16, 32, 32), lambda v: v['hit'] > 20)
        settled_ink(out, (0, 0, 14, 14), lambda v: v['field'] == v['total'])
        # the Cabinet ID tab's Label Position: top-left
        page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmA'))")
        page.click('.view-tab[data-mode="cabinet-id"]')
        page.check('input[name="cabinet-id-position"][value="top-left"]')
        settled(page, lambda: page.evaluate(
            "() => window.app.project.layers.find(x => x.name === 'IdmA').cabinetIdPosition"),
            lambda v: v == 'top-left')
        open_tab(page)
        lab = labels(page, 'IdmA')
        assert lab['position'] == 'top-left'
        s = next(x for x in lab['sites'] if x['key'] == '0,0,1,0')
        assert 64 + 2 < s['x'] < 64 + 12 and 2 < s['y'] < 12, s
        settled_ink(out, (64 + 2, 2, 28, 24), lambda v: v['hit'] > 10)
        settled_ink(out, (64 + 34, 30, 28, 30), lambda v: v['field'] == v['total'])
        # IdmB was never changed: still centred
        assert labels(page, 'IdmB')['position'] == 'center'
    finally:
        out.close()


def test_the_labels_follow_the_cabinet_id_style_and_match_the_list(page):
    fresh(page)
    set_ids(page, True)
    set_layout(page, 'IdmB', 4, 4)        # 40 px modules
    # the Cabinet ID default, A1 B1 C1 (column letter, row number), run over
    # each cabinet's own 4 x 4 module grid and starting again in every one
    got = texts(page, 'IdmB')
    assert len(got) == 4 * 16
    assert got == list_labels(page, 'IdmB')
    for key, text in got.items():
        _col, _row, mx, my = (int(v) for v in key.split(','))
        assert text == 'ABCD'[mx] + str(my + 1), (key, text)
    # the Cabinet ID tab's style buttons change them: A1 A2 A3 (row letter,
    # column number) ...
    page.evaluate("() => window.app.selectLayer(window.app.project.layers.find(x => x.name === 'IdmB'))")
    page.click('.view-tab[data-mode="cabinet-id"]')
    page.check('input[name="cabinet-id-style"][value="row-column"]')
    settled(page, lambda: page.evaluate(
        "() => window.app.project.layers.find(x => x.name === 'IdmB').cabinetIdStyle"),
        lambda v: v == 'row-column')
    open_tab(page)
    got = texts(page, 'IdmB')
    assert got['1,1,3,0'] == 'A4' and got['1,1,0,1'] == 'B1' and got['0,0,0,0'] == 'A1', got
    assert got == list_labels(page, 'IdmB')
    # ... and 1,1  1,2 (row, column)
    set_style(page, 'IdmB', 'row-col')
    got = texts(page, 'IdmB')
    assert got['0,1,3,0'] == '1,4' and got['0,1,0,1'] == '2,1', got
    assert got == list_labels(page, 'IdmB')
    # the highlight readout says the same
    page.evaluate("""() => {
        const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        app._idmSetHighlight(b.id, '1,0,2,3');
    }""")
    assert page.inner_text('#idm-hl-readout') == 'IdmB · 1,2 · Module 4,3'
    page.evaluate("() => window.app._idmClearHighlight()")


def test_a_half_cabinet_labels_its_modules_as_the_whole_cabinet_does(page):
    fresh(page)
    set_ids(page, True)
    # IdmA's left column cut to half width, 4 x 4 modules of 32 px: the half
    # keeps two columns (it meets the wall on its right, so the cut is on its
    # free left edge) and labels them as those columns of a whole cabinet
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
    set_layout(page, 'IdmA', 4, 4)
    got = texts(page, 'IdmA')
    assert got == list_labels(page, 'IdmA')
    half = {k: t for k, t in got.items() if k.startswith('0,0,')}
    whole = {k: t for k, t in got.items() if k.startswith('1,0,')}
    assert len(half) == 8 and len(whole) == 16, (half, whole)
    assert sorted(half.values()) == sorted(['C1', 'D1', 'C2', 'D2', 'C3', 'D3', 'C4', 'D4']), half
    for k, t in half.items():
        assert whole['1,0,' + k[4:]] == t, (k, t)
    # a mark on the half cabinet: the list names the module by its label
    page.evaluate("""() => {
        const app = window.app, l = app.project.layers.find(x => x.name === 'IdmA');
        l.idm = {modulesX: 4, modulesY: 4, marks: {'0,0,3,1': {style: 'x', color: '#ff1a1a'}}};
        app.updateLayers([l], true, 'Mark');
        window.canvasRenderer.render();
    }""")
    row = page.inner_text('#idm-list .idm-row-text')
    assert half['0,0,3,1'] == 'D2'
    assert re.search(r'Module D2(?!\d)', row), row
    assert '(row 2, col 2)' in row, row


def test_the_labels_turn_with_a_turned_screen(page):
    cid = fresh(page)
    set_ids(page, True)
    set_layout(page, 'IdmA', 2, 2)
    out = open_output(page, cid)
    try:
        settled_ink(out, (0, 0, 64, 64), lambda v: v['hit'] > 20)
        upright = patch(out, (0, 0, 64, 64))
        before = patch(out, (320, 192, 64, 64))      # C2's last module: "B2"
        ink_px = sum(1 for row in upright for px in row if px != [255, 255, 255])
        # turned 180 on the Pixel Map: A1's first module - and its label -
        # is now the screen's bottom-right corner, drawn in the screen's
        # frame the way the Cabinet ID labels are: the same picture, upside
        # down (glyph edges rasterize a little differently turned over)
        page.evaluate("""() => {
            const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
            a.rotation = 180;
            app.updateLayers([a], true, 'Rotate');
            window.canvasRenderer.render();
        }""")

        def off_by(other):
            bad = 0
            for y in range(64):
                for x in range(64):
                    a, b = upright[y][x], other[63 - y][63 - x]
                    if max(abs(a[i] - b[i]) for i in range(3)) > 60:
                        bad += 1
            return bad

        unlike = off_by(before)
        bad = settled(out, lambda: off_by(patch(out, (320, 192, 64, 64))), lambda n: n <= ink_px * 0.3)
        assert bad <= ink_px * 0.3 and bad * 3 < unlike, (bad, ink_px, unlike)
        assert page.evaluate("""() => {
            const r = window.canvasRenderer;
            const h = r.idmHitAt(380, 250);
            return h && h.cell ? [h.panel.col, h.panel.row, h.cell.mx, h.cell.my] : null;
        }""") == [0, 0, 0, 0]
    finally:
        out.close()


def test_modules_too_small_carry_no_labels(page):
    cid = fresh(page)
    set_ids(page, True)
    set_layout(page, 'IdmA', 16, 16)      # 8 px modules: too small to read
    set_layout(page, 'IdmB', 2, 2)        # 80 px modules: labelled
    assert labels(page, 'IdmA') == {'px': 0, 'position': 'center', 'sites': []}
    assert len(labels(page, 'IdmB')['sites']) == 16
    out = open_output(page, cid)
    try:
        settled_ink(out, (600 + 20, 20, 40, 40), lambda v: v['hit'] > 20)
        for x, y in [(0, 0), (128, 0), (256, 128)]:
            settled_ink(out, (x, y, 128, 128), lambda v: v['field'] == v['total'])
    finally:
        out.close()


# ── the stored highlight, in the browser ──────────────────────────────────

def test_a_client_that_connects_later_shows_the_highlight_at_once(page, e2e_server, pw_browser):
    fresh(page)
    set_layout(page, 'IdmB', 2, 2)
    page.evaluate("""() => {
        const app = window.app, b = app.project.layers.find(x => x.name === 'IdmB');
        app._idmSetHighlight(b.id, '1,1,0,1');
    }""")
    lid = page.evaluate("() => window.app.project.layers.find(x => x.name === 'IdmB').id")
    got = settled(page, lambda: app_module.current_project.get('idmHighlight'),
                  lambda v: v == {'layerId': lid, 'key': '1,1,0,1'})
    assert got == {'layerId': lid, 'key': '1,1,0,1'}, got
    context, late = _new_page(pw_browser, e2e_server)
    try:
        wait_layers(late)
        # straight from the project it loaded - no move needed
        assert hl(late) == ['IdmB', '1,1,0,1']
        open_tab(late)
        assert late.inner_text('#idm-hl-readout') == 'IdmB · B2 · Module A2'
        assert not late.is_disabled('#idm-pad-mark')
        # and it blinks there
        late.wait_for_function("() => !!window.app._idmS.blinkTimer", timeout=3000)
        assert not late._errors, late._errors
    finally:
        context.close()


def test_the_highlight_survives_save_and_load_and_undo_never_moves_it(page):
    fresh(page)
    set_layout(page, 'IdmA', 2, 2)
    pt = point(page, 'IdmA', 1, 0, 1, 1)
    page.mouse.move(pt['x'], pt['y'])
    settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,1,1'])
    page.mouse.move(5, 5)
    # an edit, a move, an undo: the edit goes, the highlight stays put
    before = page.evaluate("() => window.app.historyIndex")
    page.keyboard.press('Space')
    settled(page, lambda: page.evaluate("() => window.app.historyIndex"), lambda v: v == before + 1)
    page.keyboard.press('ArrowLeft')
    assert hl(page) == ['IdmA', '1,0,0,1']
    assert page.evaluate("() => window.app.historyIndex") == before + 1
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(500)
    assert hl(page) == ['IdmA', '1,0,0,1']
    lid = page.evaluate("() => window.app.project.layers.find(x => x.name === 'IdmA').id")
    got = settled(page, lambda: app_module.current_project.get('idmHighlight'),
                  lambda v: v == {'layerId': lid, 'key': '1,0,0,1'})
    assert got == {'layerId': lid, 'key': '1,0,0,1'}, got
    # the show as a file (what Save writes: the browser's project), the
    # highlight cleared, the file opened again: it is back
    text = page.evaluate("() => window.app.serializeProjectForFile()")
    assert '"idmHighlight"' in text
    page.keyboard.press('Escape')
    assert hl(page) is None
    settled(page, lambda: app_module.current_project.get('idmHighlight'), lambda v: v is None)
    page.evaluate("""async (text) => {
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: text});
        window.app.loadProject();
    }""", text)
    got = settled(page, lambda: hl(page), lambda v: v == ['IdmA', '1,0,0,1'])
    assert got == ['IdmA', '1,0,0,1'], got
    # a reload keeps it
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app.project && window.app.history", timeout=15000)
    page.wait_for_timeout(800)
    assert hl(page) == ['IdmA', '1,0,0,1']
    open_tab(page)
    page.mouse.move(5, 5)
    page.evaluate("() => window.app._idmClearHighlight()")


def test_esc_clears_the_highlight_for_everyone(page, e2e_server, pw_browser):
    fresh(page)
    context, other = _new_page(pw_browser, e2e_server)
    try:
        wait_layers(other)
        page.evaluate("""() => {
            const app = window.app, a = app.project.layers.find(x => x.name === 'IdmA');
            app._idmSetHighlight(a.id, '2,1,0,0');
        }""")
        got = settled(other, lambda: hl(other), lambda v: v == ['IdmA', '2,1,0,0'])
        assert got == ['IdmA', '2,1,0,0'], got
        page.keyboard.press('Escape')
        assert hl(page) is None
        got = settled(other, lambda: hl(other), lambda v: v is None)
        assert got is None, got
        got = settled(page, lambda: app_module.current_project.get('idmHighlight', 'missing'),
                      lambda v: v is None)
        assert got is None, got
        # and a client that connects after the clear has none
        context2, late = _new_page(pw_browser, e2e_server)
        try:
            wait_layers(late)
            assert hl(late) is None
        finally:
            context2.close()
    finally:
        context.close()


# ── 3. A picture for the record ───────────────────────────────────────────

SHOT = os.environ.get('LRD_IDM_MODULE_IDS_SHOT')


@pytest.mark.skipif(not SHOT, reason='set LRD_IDM_MODULE_IDS_SHOT to a .png path to save the screenshot')
def test_screenshot(page):
    fresh(page)
    click_field(page, '#ffffff', 'shade')
    page.evaluate("""async () => {
        const app = window.app;
        const a = app.project.layers.find(x => x.name === 'IdmA');
        const b = app.project.layers.find(x => x.name === 'IdmB');
        a.idm = {modulesX: 2, modulesY: 2, marks: {'1,0,1,0': {style: 'color', color: '#ff1a1a'}}};
        b.idm = {modulesX: 4, modulesY: 4, marks: {'0,1,2,1': {style: 'x', color: '#0050ff'}}};
        app.updateLayers([a, b], true, 'Modules');
    }""")
    page.wait_for_timeout(600)
    set_ids(page, True)
    # close on the two screens (the canvas is 1920 wide; they fill 920 of it)
    page.evaluate("""() => { const r = window.canvasRenderer;
        r.zoom = Math.min((r.canvas.clientWidth - 40) / 920, (r.canvas.clientHeight - 40) / 320);
        r.panX = 20; r.panY = 20; r.render(); }""")
    page.mouse.move(5, 5)
    page.wait_for_timeout(400)
    page.screenshot(path=SHOT)
