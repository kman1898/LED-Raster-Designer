"""An echo of the page's own earlier save never moves a gesture back.

A gesture changes a screen on every move and saves only when it lets go: a
screen drag (Shift+drag) moves offset_x/y (Show Look: showOffsetX/Y) and the cabinets,
the Hue slider turns color1/color2, a bar edge drag rewrites the bars, a
module stroke marks idm. The reply to the save made just BEFORE the gesture,
or its socket echo, landing mid-move carried the screen as that save left
it: the screen jumped back under the hand until the next move, the slider
turned from the older colors and ended short, the stroke lost the marks it
had made (its touched modules are never marked twice), and a bar drag kept
writing into a screen object the reply had already swapped out, so the bars
froze where the reply put them (2026-11-08).

Now (app-core.js): an echo of the page's own save waits while a hand is on
a gesture and runs when it lets go (_holdForGesture), and any echo of the
page's own newest save keeps every field the page changed since it sent it
(_keepUnsavedEdits). Another window's edit still lands at once.

Each gesture test: a save of the screen goes out and its reply is HELD by a
page-side fetch wrapper; the gesture starts; mid-move the reply is let go
and the socket echo of the same save is fired; the gesture must not move.

Run locally:
    python -m pytest tests/test_echo_mid_gesture.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import settled  # noqa: E402
from test_idm_field_highlight import (  # noqa: E402
    _new_page, reset_project, set_layout, served_idm, marks_of, point,
)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


# Holds the RESPONSE of layer PUTs (the request goes out untouched), until
# released. Only while __hold is on.
HOLD_JS = """() => {
    window.__held = [];
    window.__hold = true;
    if (!window.__origFetch) {
        window.__origFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            const p = window.__origFetch(input, init);
            if (!(window.__hold && /\\/api\\/layer\\/\\d+/.test(url) && init && init.method === 'PUT')) return p;
            return new Promise(resolve => { window.__held.push(() => p.then(resolve)); });
        };
    }
}"""

UNHOLD_JS = """() => {
    if (window.__origFetch) window.fetch = window.__origFetch;
    delete window.__origFetch;
    window.__hold = false;
    (window.__held || []).forEach(f => f());
    window.__held = [];
}"""

# A save of `name` the way any edit makes one; its reply is held, and the
# screen as that save sent it is kept for the echo.
SAVE_HELD_JS = """async (name) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === name);
    l.screenNameSize = (Number(l.screenNameSize) || 24) + 1;
    app.updateLayers([l]);
    window.__echoCopy = JSON.parse(JSON.stringify(l));
    window.__echoCopy._echo = {seq: app._layerPutSeq.get(l.id), client: app._echoClientId};
    const t0 = Date.now();
    while (window.__held.length < 1 && Date.now() - t0 < 5000) await new Promise(r => setTimeout(r, 20));
    // its real socket echo (the same copy as the page) has landed and gone
    await new Promise(r => setTimeout(r, 300));
    window.__hold = false;   // the gesture's own save goes through
    return window.__held.length;
}"""

# Mid-gesture: the held reply lands, then the socket echo of the same save.
LAND_ECHOES_JS = """async () => {
    const app = window.app;
    (window.__held || []).forEach(f => f());
    window.__held = [];
    await new Promise(r => setTimeout(r, 250));
    const copy = JSON.parse(JSON.stringify(window.__echoCopy));
    app.socket.listeners('layer_updated').forEach(fn => fn(copy));
    await new Promise(r => setTimeout(r, 100));
}"""


def _hold_a_save(pg, name):
    pg.evaluate(HOLD_JS)
    assert pg.evaluate(SAVE_HELD_JS, name) == 1, 'no reply held: the test is not exercising the race'


def _layer(pg, name, expr):
    return pg.evaluate(f"""(name) => {{
        const l = window.app.project.layers.find(x => x.name === name);
        return JSON.parse(JSON.stringify({expr}));
    }}""", name)


def _served(pg, name, expr):
    return pg.evaluate(f"""async (name) => {{
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.name === name);
        return JSON.parse(JSON.stringify({expr}));
    }}""", name)


def _view(pg, mode):
    pg.click(f'.view-tab[data-mode="{mode}"]')
    pg.wait_for_function(f"() => window.canvasRenderer.viewMode === '{mode}'")
    pg.evaluate("() => { window.canvasRenderer.fitToView(); window.canvasRenderer.render(); }")
    pg.wait_for_timeout(200)


def _client(pg, wx, wy):
    return pg.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer, rect = r.canvas.getBoundingClientRect();
        return {x: rect.left + r.panX + wx * r.zoom, y: rect.top + r.panY + wy * r.zoom};
    }""", [wx, wy])


def _fresh(pg):
    reset_project(pg)
    pg.evaluate("() => window.app._layerSavesSettled()")
    pg._errors.clear()


@pytest.mark.parametrize('mode,field', [('pixel-map', 'offset_x'), ('show-look', 'showOffsetX')])
def test_a_screen_drag_never_jumps_back(page, mode, field):
    _fresh(page)
    _view(page, mode)
    page.evaluate("() => { window.canvasRenderer.magneticSnap = false; }")
    start = _layer(page, 'IdmA', f"l.{field} ?? l.offset_x")
    a = _client(page, start + 192, 128)
    _hold_a_save(page, 'IdmA')
    try:
        page.mouse.move(a['x'], a['y'])
        page.keyboard.down('Shift')   # Shift+drag moves the screen
        page.mouse.down()
        page.mouse.move(a['x'] + 60, a['y'], steps=6)
        mid = _layer(page, 'IdmA', f"[l.{field}, l.panels[0].x]")
        assert mid[0] > start, (start, mid)
        page.evaluate(LAND_ECHOES_JS)
        after = _layer(page, 'IdmA', f"[l.{field}, l.panels[0].x]")
        assert after == mid, f'the screen jumped back mid-drag: {mid} -> {after}'
        page.mouse.move(a['x'] + 90, a['y'], steps=3)
        page.mouse.up()
    finally:
        page.keyboard.up('Shift')
        page.evaluate(UNHOLD_JS)
    end = _layer(page, 'IdmA', f"l.{field}")
    assert end > mid[0], (mid, end)
    assert settled(page, lambda: _served(page, 'IdmA', f"l.{field}"), lambda v: v == end) == end
    assert not page._errors, page._errors


def test_a_module_stroke_keeps_every_mark_it_made(page):
    _fresh(page)   # opens the IDM Locator tab
    set_layout(page, 'IdmA', 2, 2)
    keys = [(0, 0, 0, 0), (0, 0, 1, 0), (0, 0, 1, 1), (1, 0, 0, 1)]
    pts = [point(page, 'IdmA', *k) for k in keys]
    _hold_a_save(page, 'IdmA')
    try:
        page.mouse.move(pts[0]['x'], pts[0]['y'])
        page.mouse.down()
        page.mouse.move(pts[1]['x'], pts[1]['y'], steps=4)
        page.mouse.move(pts[2]['x'], pts[2]['y'], steps=4)
        mid = sorted(marks_of(page, 'IdmA'))
        assert len(mid) >= 3, mid
        page.evaluate(LAND_ECHOES_JS)
        assert sorted(marks_of(page, 'IdmA')) == mid, 'the stroke lost its marks mid-drag'
        page.mouse.move(pts[3]['x'], pts[3]['y'], steps=4)
        page.mouse.up()
    finally:
        page.evaluate(UNHOLD_JS)
    want = {','.join(map(str, k)) for k in keys}
    got = set(marks_of(page, 'IdmA'))
    assert want <= got, (want, got)
    served = settled(page, lambda: served_idm(page, 'IdmA'), lambda v: v and set(v['marks']) == got)
    assert set(served['marks']) == got, served
    assert not page._errors, page._errors


# The first edge between two bars of IdmA's header, in canvas pixels.
EDGE_JS = """() => {
    const r = window.canvasRenderer, rect = r.canvas.getBoundingClientRect();
    const e = (r._riggingEdges || [])[0];
    return e ? {x: rect.left + e.x, y: rect.top + (e.y0 + e.y1) / 2, unit: e.unitPx} : null;
}"""


def test_a_bar_edge_drag_follows_the_hand(page):
    _fresh(page)
    page.evaluate("""async () => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'IdmA');
        l.riggingBars = [1, 2]; l.riggingBarStarts = null;
        l.riggingFooterBars = []; l.riggingFooterBarStarts = null;
        l.riggingSide = 'header'; l.riggingCustom = false;
        app.updateLayers([l]);
        await app._layerSavesSettled();
    }""")
    _view(page, 'rigging')
    edge = page.evaluate(EDGE_JS)
    assert edge, 'no bar edge on the canvas'
    _hold_a_save(page, 'IdmA')
    try:
        page.mouse.move(edge['x'], edge['y'])
        page.mouse.down()
        page.mouse.move(edge['x'] + edge['unit'] * 1.2, edge['y'], steps=6)
        mid = _layer(page, 'IdmA', "l.riggingBars")
        assert mid != [1, 2], mid
        page.evaluate(LAND_ECHOES_JS)
        assert _layer(page, 'IdmA', "l.riggingBars") == mid, 'the bars jumped back mid-drag'
        assert page.evaluate("""() => {
            const d = window.canvasRenderer._riggingDrag;
            const l = window.app.project.layers.find(x => x.name === 'IdmA');
            return !!d && d.rowObj.layers.includes(l);
        }"""), 'the drag is writing into a screen the page no longer holds'
        page.mouse.move(edge['x'] + edge['unit'] * 1.4, edge['y'], steps=2)
        page.mouse.up()
    finally:
        page.evaluate(UNHOLD_JS)
    end = _layer(page, 'IdmA', "l.riggingBars")
    assert end == mid, (mid, end)
    assert settled(page, lambda: _served(page, 'IdmA', "l.riggingBars"), lambda v: v == end) == end
    assert not page._errors, page._errors


HUE_X_JS = """(value) => {
    const el = document.getElementById('quick-palette-hue');
    el.scrollIntoView({block: 'center'});
    const box = el.getBoundingClientRect();
    const span = box.width - 10;
    return {x: box.left + 5 + (value + 180) / 360 * span, y: box.top + box.height / 2};
}"""

PAIR_JS = """(name) => {
    const app = window.app, l = app.project.layers.find(x => x.name === name);
    const hex = (c) => app.rgbToHex(c.r, c.g, c.b).toUpperCase();
    return [hex(l.color1), hex(l.color2)];
}"""

HUE_SEED_JS = """async () => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === 'IdmA');
    l.color1 = {r: 64, g: 70, b: 128}; l.color2 = {r: 149, g: 156, b: 184};
    l.panelColorMode = 'checker'; l.transparentFill = false; l.locked = false;
    app.updateLayers([l]);
    await app._layerSavesSettled();
    app._quickPalette = null;
    app.setSelectedLayersByIds([l.id], l.id);
    app.selectLayer(l);
    app.loadQuickPalettes();
    app.resetHistory('Hue Seed');
}"""


def _hue_drag(pg, echo):
    pg.evaluate(HUE_SEED_JS)
    pg.wait_for_timeout(200)
    if echo:
        _hold_a_save(pg, 'IdmA')
    try:
        v = int(pg.locator('#quick-palette-hue').input_value())
        a = pg.evaluate(HUE_X_JS, v)
        b = pg.evaluate(HUE_X_JS, v + 40)
        c = pg.evaluate(HUE_X_JS, v + 80)
        pg.mouse.move(a['x'], a['y'])
        pg.mouse.down()
        pg.mouse.move(b['x'], a['y'], steps=8)
        if echo:
            mid = pg.evaluate(PAIR_JS, 'IdmA')
            pg.evaluate(LAND_ECHOES_JS)
            assert pg.evaluate(PAIR_JS, 'IdmA') == mid, 'the colors went back mid-drag'
        pg.mouse.move(c['x'], a['y'], steps=8)
        pg.mouse.up()
    finally:
        pg.evaluate(UNHOLD_JS)
    pg.evaluate("() => window.app._layerSavesSettled()")
    return pg.evaluate(PAIR_JS, 'IdmA')


def test_a_hue_drag_ends_where_the_slider_says(page):
    _fresh(page)
    _view(page, 'pixel-map')
    clean = _hue_drag(page, echo=False)
    raced = _hue_drag(page, echo=True)
    assert raced == clean, (clean, raced)
    assert not page._errors, page._errors


# The fields every gesture streams, changed on the page after its save went
# out and before that save's reply or echo lands, with no hand on anything
# (a native color picker streams with the pointer in the OS dialog): the
# page's value stays, on both paths.
FIELD_EDITS = {
    'offset_x': "l.offset_x = (l.offset_x || 0) + 37",
    'showOffsetY': "l.showOffsetY = (l.showOffsetY || 0) + 41",
    'panels': "l.panels.forEach(p => { p.x += 37; })",
    'color1': "l.color1 = {r: 1, g: 2, b: 3}",
    'riggingBars': "l.riggingBars = [3]",
    'stage3d': "l.stage3d = Object.assign({}, l.stage3d || {}, {x: 1.5, y: 0, z: 2.25})",
    'idm': "l.idm = {modulesX: 2, modulesY: 2, marks: {'0,0,1,1': {style: 'color', color: '#ff1a1a'}}}",
    'border_color_pixel': "l.border_color_pixel = '#123456'",
    'screenNameSize': "l.screenNameSize = 77",
}

FIELD_RACE_JS = """async ([edit, key]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === 'IdmA');
    (new Function('l', edit))(l);
    const want = JSON.stringify(l[key]);
    const read = () => JSON.stringify(app.project.layers.find(x => x.id === l.id)[key]);
    const out = {};
    // the reply lands
    (window.__held || []).forEach(f => f());
    window.__held = [];
    await new Promise(r => setTimeout(r, 300));
    out.reply = read() === want || [want, read()];
    // then the socket echo of the same save
    const copy = JSON.parse(JSON.stringify(window.__echoCopy));
    app.socket.listeners('layer_updated').forEach(fn => fn(copy));
    await new Promise(r => setTimeout(r, 100));
    out.echo = read() === want || [want, read()];
    return out;
}"""


@pytest.mark.parametrize('key', sorted(FIELD_EDITS))
def test_an_unsaved_field_outlives_the_echo_of_the_save_before(page, key):
    _fresh(page)
    _hold_a_save(page, 'IdmA')
    try:
        out = page.evaluate(FIELD_RACE_JS, [FIELD_EDITS[key], key])
    finally:
        page.evaluate(UNHOLD_JS)
    assert out == {'reply': True, 'echo': True}, out
    assert not page._errors, page._errors


def test_a_field_the_page_left_alone_takes_the_servers_value(page):
    """The echo is still the server's word on everything the page did not
    change since its save: a value the server set lands."""
    _fresh(page)
    _hold_a_save(page, 'IdmA')
    try:
        got = page.evaluate("""async () => {
            const app = window.app;
            const copy = JSON.parse(JSON.stringify(window.__echoCopy));
            copy.name = 'Server Name';
            app.socket.listeners('layer_updated').forEach(fn => fn(copy));
            await new Promise(r => setTimeout(r, 100));
            return app.project.layers.find(x => x.id === copy.id).name;
        }""")
    finally:
        page.evaluate(UNHOLD_JS)
    assert got == 'Server Name', got


HAND_DOWN_ECHO_JS = """async ([own, name]) => {
    const app = window.app;
    const copy = JSON.parse(JSON.stringify(window.__echoCopy));
    copy.name = name;
    if (!own) copy._echo = {seq: 1, client: 'another-window'};
    const ref = app.project.layers.find(x => x.id === copy.id);
    app.socket.listeners('layer_updated').forEach(fn => fn(copy));
    await new Promise(r => setTimeout(r, 100));
    const now = app.project.layers.find(x => x.id === copy.id);
    return {same: now === ref, name: now.name};
}"""


def _press_off_canvas(pg):
    box = pg.locator('#status-message').bounding_box()
    pg.mouse.move(box['x'] + 2, box['y'] + box['height'] / 2)
    pg.mouse.down()


def test_while_a_hand_is_down_the_pages_own_echo_waits_then_lands(page):
    _fresh(page)
    _hold_a_save(page, 'IdmA')
    try:
        page.evaluate("() => { (window.__held || []).forEach(f => f()); window.__held = []; }")
        page.wait_for_timeout(250)
        _press_off_canvas(page)
        held = page.evaluate(HAND_DOWN_ECHO_JS, [True, 'Server Name'])
        assert held == {'same': True, 'name': 'IdmA'}, held
        page.mouse.up()
        page.wait_for_timeout(150)
        assert _layer(page, 'Server Name', "l.name") == 'Server Name'
    finally:
        page.mouse.up()
        page.evaluate(UNHOLD_JS)
    assert not page._errors, page._errors


def test_another_windows_edit_lands_mid_gesture(page):
    _fresh(page)
    _hold_a_save(page, 'IdmA')
    try:
        _press_off_canvas(page)
        got = page.evaluate(HAND_DOWN_ECHO_JS, [False, 'From Another Window'])
        assert got['name'] == 'From Another Window', got
    finally:
        page.mouse.up()
        page.evaluate(UNHOLD_JS)
    assert not page._errors, page._errors
