"""The 2fer / 3fer tag on a shared circuit's bracket, and the switch that
hides it.

"i need a way to disable the twofer/3fer text on the screen if i dont want it
there." (user, 2026-09-06). The Nfer bracket under a ganged circuit's runs
(canvas.js renderNferBrackets) is the share itself and always draws; the tag
pill on it - "2fer", "3fer", "2fer · OVER" - is TEXT the user may not want on
the wall. So the switch is per screen, default ON, and hides only the text:

  - layer.showPowerNferTags: boolean, default true. Only an explicit false
    hides the tag, so a project saved before the switch keeps its tags.
  - #show-power-nfer-tags: "Show 2fer / 3fer Tags" in the left sidebar's
    Power Settings, directly under "Show Circuit Info", wired the same way
    (every selected screen, one history step, 'Toggle 2fer / 3fer Tags').
  - The renderer runs the same test in exportMode, so the PDF/PNG matches
    the screen.

These tests drive a REAL project on the shared e2e server (not a synthetic
withProject tree) because the round trip - /api/layer PUT allow-list,
preservedKeys, undo snapshot - is half of what a per-screen switch is.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_nfer_tags.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Three 5-tall columns of 100W tiles on 110V x 15A (16-tile capacity),
# cabled top-down and organized, sharing through 2fers at most: the packer
# gangs columns 1+2 (10 tiles) and leaves column 3 plain, so the wall has
# exactly ONE shared circuit - one bracket, one "2fer" tag.
SETUP_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'NferWall', columns: 3, rows: 5,
            cabinet_width: 128, cabinet_height: 128,
            powerVoltage: 110, powerAmperage: 15, panelWatts: 100,
            powerFlowPattern: 'tl-v', powerOrganized: true,
            powerSplitters: { enabled: true, maxWays: 2,
                              manual: { merge: [], split: [] } },
        }),
    });
    const built = await (await fetch('/api/project')).json();
    app.project = built;
    app.dedupeProjectLayers('nfer_tags_setup');
    const screen = app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    app.selectLayer(screen);
    app.renderLayers();
    app.updatePowerCapacityDisplay();
    window.canvasRenderer.viewMode = 'power';
    window.canvasRenderer.render();
    app.resetHistory('Nfer Tags Setup');
    return {
        id: screen.id,
        runIds: app.calculatePowerAssignments(screen).runIds,
        flag: screen.showPowerNferTags,
    };
}"""

# What one pass of renderNferBrackets puts on the canvas: every stroke()
# (one per bracket) and every fillText (the tag). Called directly so the
# stroke count is the bracket count and nothing else's.
BRACKET_PASS_JS = """() => {
    const app = window.app, r = window.canvasRenderer, ctx = r.ctx;
    const layer = app.currentLayer;
    const oT = ctx.fillText, oS = ctx.stroke;
    const texts = [];
    let strokes = 0;
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
    ctx.stroke = function () { strokes++; return oS.apply(ctx, arguments); };
    try { r.renderNferBrackets(layer); } finally { ctx.fillText = oT; ctx.stroke = oS; }
    return { strokes, texts, flag: layer.showPowerNferTags };
}"""

# Every fillText the real render pass paints in power view - interactively
# and in exportMode, since the exporter drives this same renderer.
FRAME_TEXTS_JS = """() => {
    const r = window.canvasRenderer, ctx = r.ctx;
    const oT = ctx.fillText;
    const grab = () => {
        const texts = [];
        ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
        try { r.render(); } finally { ctx.fillText = oT; }
        return texts.filter(t => /\\dfer/.test(t));
    };
    const prevMode = r.viewMode, prevExport = r.exportMode;
    let interactive, exported;
    try {
        r.viewMode = 'power';
        r.exportMode = false;
        interactive = grab();
        r.exportMode = true;
        exported = grab();
    } finally {
        r.exportMode = prevExport;
        r.viewMode = prevMode;
        r.render();
    }
    return { interactive, exported };
}"""

SERVED_FLAG_JS = """async (layerId) => {
    const p = await (await fetch('/api/project')).json();
    const l = (p.layers || []).find(x => x.id === layerId);
    return l ? { present: 'showPowerNferTags' in l, flag: l.showPowerNferTags } : null;
}"""

STATE_JS = """() => {
    const app = window.app;
    const box = document.getElementById('show-power-nfer-tags');
    return {
        flag: app.currentLayer.showPowerNferTags,
        checked: !!(box && box.checked),
        visible: !!(box && box.offsetParent !== null),
        action: app.history[app.historyIndex].action,
        steps: app.history.length,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    built = pg.evaluate(SETUP_JS)
    assert built['runIds'] == [[1, 2], [3]], (
        f'fixture: columns 1+2 must gang through a 2fer: {built}')
    pg.wait_for_timeout(400)
    pg.evaluate('(id) => { window.__nferLayerId = id; }', built['id'])
    yield pg
    context.close()


def _served_flag(page, layer_id, expect, timeout_ms=4000):
    waited = 0
    served = None
    while waited <= timeout_ms:
        served = page.evaluate(SERVED_FLAG_JS, layer_id)
        if served and served['present'] and served['flag'] is expect:
            return served
        page.wait_for_timeout(250)
        waited += 250
    return served


def test_a_fresh_screen_draws_the_bracket_and_the_tag(page):
    """Default ON: a screen that never had the key draws its 2fer tag - the
    checkbox shows ticked, the bracket strokes once, the pill says 2fer."""
    state = page.evaluate(STATE_JS)
    assert state['flag'] is True, state
    assert state['visible'] and state['checked'], (
        f'the switch must sit ticked under Show Circuit Info: {state}')
    out = page.evaluate(BRACKET_PASS_JS)
    assert out['strokes'] == 1, f'one shared circuit, one bracket: {out}'
    assert out['texts'] == ['2fer'], out
    frame = page.evaluate(FRAME_TEXTS_JS)
    assert frame['interactive'] == ['2fer'], frame
    assert frame['exported'] == ['2fer'], frame


def test_a_project_without_the_key_keeps_its_tags(page):
    """A project saved before the switch existed carries no key at all, and
    it must open looking exactly as it did: only an explicit false hides."""
    out = page.evaluate("""() => {
        const l = window.app.currentLayer;
        const saved = l.showPowerNferTags;
        delete l.showPowerNferTags;
        try { return (%s)(); } finally { l.showPowerNferTags = saved; }
    }""" % BRACKET_PASS_JS)
    assert out['flag'] is None, out
    assert out['strokes'] == 1 and out['texts'] == ['2fer'], out


def test_unticking_hides_the_text_and_keeps_the_bracket(page):
    """The switch off: the bracket still strokes, no fer text - on screen
    and in the export pass alike. The flag lands on the layer and on the
    server, so a reload keeps the choice. The toggle is one history step:
    undo restores the tag (and re-ticks the box from the restored layer),
    redo hides it again."""
    layer_id = page.evaluate('() => window.__nferLayerId')
    page.locator('#show-power-nfer-tags').click()
    page.wait_for_timeout(900)   # PUT + response merge + socket echo
    state = page.evaluate(STATE_JS)
    assert state['flag'] is False and not state['checked'], state
    assert state['action'] == 'Toggle 2fer / 3fer Tags', (
        f'the toggle must be one named history step: {state}')

    out = page.evaluate(BRACKET_PASS_JS)
    assert out['strokes'] == 1, f'the bracket must survive the switch: {out}'
    assert out['texts'] == [], f'the tag text must be gone: {out}'
    frame = page.evaluate(FRAME_TEXTS_JS)
    assert frame['interactive'] == [], frame
    assert frame['exported'] == [], (
        f'the export pass must match the screen: {frame}')

    served = _served_flag(page, layer_id, False)
    assert served and served['present'] and served['flag'] is False, (
        f'the server never took showPowerNferTags=false - a reload would '
        f'bring the tags back: {served}')

    page.evaluate('() => window.app.undo()')
    page.wait_for_timeout(900)
    state = page.evaluate(STATE_JS)
    assert state['flag'] is True and state['checked'], (
        f'undo must restore the flag and the checkbox with it: {state}')
    out = page.evaluate(BRACKET_PASS_JS)
    assert out['strokes'] == 1 and out['texts'] == ['2fer'], out
    served = _served_flag(page, layer_id, True)
    assert served and served['flag'] is True, served

    page.evaluate('() => window.app.redo()')
    page.wait_for_timeout(900)
    state = page.evaluate(STATE_JS)
    assert state['flag'] is False and not state['checked'], state
    out = page.evaluate(BRACKET_PASS_JS)
    assert out['strokes'] == 1 and out['texts'] == [], out

    # Leave the switch on for whoever runs next.
    page.locator('#show-power-nfer-tags').click()
    page.wait_for_timeout(600)
    assert page.evaluate(STATE_JS)['flag'] is True


OVER_TEXTS_JS = """() => {
    const r = window.canvasRenderer, ctx = r.ctx;
    const oT = ctx.fillText;
    const texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
    const prev = r.viewMode;
    try { r.viewMode = 'power'; r.render(); } finally { ctx.fillText = oT; r.viewMode = prev; r.render(); }
    return texts.filter(t => /^\\dfer|OVER/.test(t));
}"""

# A hand-forced gang past the figure: merge all three column runs into
# one circuit (15 tiles x 100 W on 110 V is 13.6 A) on a 12 A figure. A
# manual merge is the user's call, so the packer keeps it and the
# bracket goes red + OVER - the case the tag's warning exists for.
FORCE_OVER_JS = """() => {
    const app = window.app, l = app.currentLayer;
    l.powerAmperage = 12;
    l.powerSplitters = Object.assign({}, l.powerSplitters || {}, {
        enabled: true, maxWays: 3,
        manual: { merge: [[1, 2, 3]], split: [], space: 'auto' },
    });
    app._circuitTailCache = null;
    window.canvasRenderer.render();
    return app.screenCircuits(l).map(c => c.runIds || [c.num]);
}"""


def test_an_over_gang_still_says_over_with_the_tags_off(page):
    """The tag is decoration the user may not want; the OVER on an
    over-capacity gang is a warning and survives the switch, printed
    alone. A red stroke by itself is easy to miss on a busy wall."""
    runs = page.evaluate(FORCE_OVER_JS)
    assert runs == [[1, 2, 3]], f'the forced 3fer did not form: {runs}'
    assert page.evaluate(OVER_TEXTS_JS) == ['3fer · OVER']
    page.locator('#show-power-nfer-tags').click()
    page.wait_for_timeout(700)
    assert page.evaluate(STATE_JS)['flag'] is False
    assert page.evaluate(OVER_TEXTS_JS) == ['OVER'], 'the warning must outlive the tag'
    # back to the fixture's wall and the switch on, for whoever runs next
    page.locator('#show-power-nfer-tags').click()
    page.wait_for_timeout(600)
    # A manual merge is remembered past the store it came from, so the
    # cleanest way back is the fixture itself: rebuild the wall.
    built = page.evaluate(SETUP_JS)
    assert built['runIds'] == [[1, 2], [3]], built
    page.wait_for_timeout(400)
    page.evaluate('(id) => { window.__nferLayerId = id; }', built['id'])
    assert page.evaluate(STATE_JS)['flag'] is True
    assert page.evaluate(OVER_TEXTS_JS) == ['2fer']


def test_the_switch_reads_the_selected_screen(page):
    """loadLayerToInputs: the box follows the layer it shows. A screen
    holding false shows unticked; select one holding true and it ticks."""
    out = page.evaluate("""() => {
        const app = window.app;
        const l = app.currentLayer;
        const box = document.getElementById('show-power-nfer-tags');
        l.showPowerNferTags = false;
        app.loadLayerToInputs();
        const off = box.checked;
        l.showPowerNferTags = true;
        app.loadLayerToInputs();
        const on = box.checked;
        delete l.showPowerNferTags;
        app.loadLayerToInputs();
        const absent = box.checked;
        l.showPowerNferTags = true;
        return { off, on, absent };
    }""")
    assert out == {'off': False, 'on': True, 'absent': True}, out
