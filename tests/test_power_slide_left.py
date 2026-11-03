"""Automatic circuits slide left after a redraw (the owner's ruling, 2026-11-03).

A wall cabled top-down shares its columns two at a time through 2fers.
The user redraws circuit 2 down to one column. Before this fix the walk
read the columns either side of a redrawn circuit as neighbours: the
column left over before a redrawn 2fer was ganged with the column after
it, a 2fer whose cable jumped the other circuit and whose disc sat on
that circuit's disc. Two discs and two 2fer pills read as one "4fer".

The rulings:

- An automatic 2fer / 3fer (or a daisy of whole columns) never jumps
  over a redrawn circuit. The circuits after a redraw pack side by side
  from the first free column.
- A redraw that ends with the circuit's cabinets unchanged does not stay
  a frozen override. It goes back to the walk, so it no longer blocks
  the slide ("i redrew ports so s1-1 is a twofer and s1-2 is a single
  column. so column 4-5 should become a twofer").
- A show saved before this (1.6.0-beta.4 and older) has such a redraw
  let go as it opens, with a toast saying so. A show from this build
  keeps every redraw it has.

The wall is synthetic: 8 x 4 cabinets of 150 W on 208 V x 20 A, cabled
top-down (tl-v), Organized, 2fers (maxWays 2). Two columns draw 1,200 W,
well inside one circuit.

Run locally:
    python -m pytest tests/test_power_slide_left.py -v --browser chromium
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


FETCH_COUNT_JS = """(() => {
    const real = window.fetch;
    let out = 0;
    Object.defineProperty(window, '__lrdFetchesOut', { get: () => out });
    window.fetch = function (...args) {
        out++;
        const p = real.apply(this, args);
        p.then(() => { out--; }, () => { out--; });
        return p;
    };
})()"""


def _settle(pg):
    """Every fetch the page made has answered and every layer save landed."""
    pg.wait_for_function("() => window.__lrdFetchesOut === 0")
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")
    pg.wait_for_function("() => window.__lrdFetchesOut === 0 && !window.app._saveStateTimer")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    _settle(pg)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


def col_path(*cols):
    """A redrawn circuit down whole columns, each column after the first
    its own run of the shared circuit (the take-over's `branch` mark)."""
    out = []
    for k, c in enumerate(cols):
        for r in range(4):
            step = {'row': r, 'col': c}
            if k > 0 and r == 0:
                step['branch'] = True
            out.append(step)
    return out


# The show file: one screen built on the server and shaped as above, with
# the redrawn circuits `paths` ({num: path}) and stamped `version`.
SHOW_JS = """async ({ paths, version }) => {
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
    await window.app._layerSavesSettled();
    await fetch('/api/project/new', { method: 'POST' });
    const made = await j('POST', '/api/layer/add', {
        name: 'Wall', columns: 8, rows: 4, cabinet_width: 200, cabinet_height: 200,
        offset_x: 0, offset_y: 0 });
    const p = await j('GET', '/api/project');
    const l = p.layers.find(x => x.id === made.id);
    Object.assign(l, {
        powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v',
        powerCustomPath: false, powerOrganized: true, powerMaximize: false,
        powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
        powerCustomPaths: paths, powerCustomIndex: 1,
        powerCustomOverrides: Object.keys(paths).map(Number),
        powerSplitters: { enabled: true, maxWays: 2, manual: { merge: [], split: [] } },
        locked: false,
    });
    p.name = 'Slide Show';
    p.app_version = version;
    return p;
}"""


def open_show(pg, paths, version):
    """File > Open with the show, the way the user does, through the load's
    PUT and its layer sync."""
    project = pg.evaluate(SHOW_JS, {'paths': paths, 'version': version})
    _settle(pg)
    pg.evaluate("""() => {
        window.__loaded = false;
        const el = document.getElementById('status-message');
        const mo = new MutationObserver(() => {
            if (el.textContent === 'Project loaded') { window.__loaded = true; mo.disconnect(); }
        });
        mo.observe(el, { childList: true, characterData: true, subtree: true });
    }""")
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("() => window.app.loadProjectFromFile()")
    chooser.value.set_files({'name': 'slide-show.json', 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_function("() => window.__loaded === true")
    _settle(pg)


# The wall as the app reads it: each circuit's number, its columns (in
# order) and its runs; the redrawn numbers; and the server's copy of them.
READ_JS = """async () => {
    const app = window.app;
    app._circuitTailCache = null;
    const l = app.project.layers.find(x => x.name === 'Wall');
    const srv = (await (await fetch('/api/project')).json()).layers.find(x => x.id === l.id);
    return {
        circuits: app.screenCircuits(l).map(c => ({
            num: c.num,
            cols: [...new Set(c.panels.map(p => p.col))],
            ways: (c.runIds || [1]).length,
        })),
        overrides: app.getOverrideNums(l, 'power'),
        serverOverrides: srv.powerCustomOverrides || [],
        editing: app._overrideEditing,
    };
}"""


def read(pg):
    return pg.evaluate(READ_JS)


def toasts(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#app-toast-host > div')]
        .map(t => t.textContent.trim()).filter(Boolean)""")


def cols_of(state):
    return {c['num']: c['cols'] for c in state['circuits']}


def assert_no_jumps(state):
    """No circuit's columns skip a column another circuit holds, and every
    circuit starts on a column of its own (its own disc spot)."""
    taken = {}
    for c in state['circuits']:
        for col in c['cols']:
            taken[col] = c['num']
    for c in state['circuits']:
        lo, hi = min(c['cols']), max(c['cols'])
        between = {taken.get(k) for k in range(lo, hi + 1)} - {c['num']}
        assert not between, f"circuit {c['num']} cols {c['cols']} jump circuits {between}"
    heads = [c['cols'][0] for c in state['circuits']]
    assert len(heads) == len(set(heads)), heads


def test_a_redrawn_circuit_is_never_jumped(page):
    """Circuit 2 redrawn to column 2 alone, circuit 3 redrawn for real to
    columns 4-5 (a show from this build keeps it): column 3 is left on
    its own, and the 2fers after circuit 3 start at column 6. Before the
    fix column 3 was ganged with column 6, over circuit 3."""
    pg, errors = page
    open_show(pg, {'2': col_path(2), '3': col_path(4, 5)}, '1.6.0')
    s = read(pg)
    assert s['overrides'] == [2, 3]
    assert cols_of(s) == {1: [0, 1], 2: [2], 3: [4, 5], 4: [3], 5: [6, 7]}, s
    assert_no_jumps(s)
    assert errors == []


def test_an_older_shows_unchanged_redraw_is_let_go_and_the_circuits_slide(page):
    """The same wall saved by beta.3, where circuit 3's redraw is the walk
    it was made on (columns 4-5, before circuit 2 shrank): it is let go as
    the show opens, said in a toast, and the 2fers slide left - S1-3 on
    columns 3-4, S1-4 on 5-6, the last column alone."""
    pg, errors = page
    open_show(pg, {'2': col_path(2), '3': col_path(4, 5)}, '1.6.0-beta.3')
    s = read(pg)
    assert s['overrides'] == [2]
    assert s['serverOverrides'] == [2]
    assert cols_of(s) == {1: [0, 1], 2: [2], 3: [3, 4], 4: [5, 6], 5: [7]}, s
    assert_no_jumps(s)
    assert any('redrawn without a change' in t for t in toasts(pg)), toasts(pg)
    assert errors == []


def test_the_open_keeps_a_redraw_that_changed_something(page):
    """A redraw that is not the walk's circuit stays on an older show too."""
    pg, errors = page
    open_show(pg, {'2': col_path(2), '3': col_path(5)}, '1.6.0-beta.3')
    s = read(pg)
    assert s['overrides'] == [2, 3]
    assert_no_jumps(s)
    assert errors == []


def test_a_redraw_that_ends_unchanged_goes_back_to_the_walk(page):
    """Alt-redraw circuit 3 and press Esc with nothing changed: it is not
    left behind as a frozen override (one undo step puts it back)."""
    pg, errors = page
    open_show(pg, {'2': col_path(2)}, '1.6.0')
    before = read(pg)
    assert cols_of(before)[3] == [3, 4]
    pg.evaluate("""() => { const a = window.app;
        a.overrideRun(a.project.layers.find(x => x.name === 'Wall'), 'power', 3); }""")
    _settle(pg)
    assert read(pg)['overrides'] == [2, 3]
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    s = read(pg)
    assert s['editing'] is None
    assert s['overrides'] == [2]
    assert s['serverOverrides'] == [2]
    assert s['circuits'] == before['circuits']
    labels = pg.evaluate("() => window.app.history.map(h => h.action || h.label || '')")
    assert any('Return Circuit To Auto' in str(x) for x in labels), labels
    assert errors == []


def test_redrawing_another_circuit_ends_the_first_unchanged_one(page):
    """Alt-redraw circuit 3, then Alt-redraw circuit 4 with nothing changed
    on 3: circuit 3 goes back to the walk as the redraw moves on."""
    pg, errors = page
    open_show(pg, {'2': col_path(2)}, '1.6.0')
    pg.evaluate("""() => { const a = window.app;
        const l = a.project.layers.find(x => x.name === 'Wall');
        a.overrideRun(l, 'power', 3);
        a.overrideRun(l, 'power', 4); }""")
    _settle(pg)
    s = read(pg)
    assert s['overrides'] == [2, 4]
    assert s['editing']['num'] == 4
    assert errors == []


def test_a_redraw_that_changed_its_cabinets_stays(page):
    """Alt-redraw circuit 3 and cut it to its first column, then Esc: the
    redraw is real and stays; the column it gave up is a circuit of its
    own, never ganged over it."""
    pg, errors = page
    open_show(pg, {'2': col_path(2)}, '1.6.0')
    pg.evaluate("""() => { const a = window.app;
        const l = a.project.layers.find(x => x.name === 'Wall');
        a.overrideRun(l, 'power', 3);
        l.powerCustomPaths[3] = l.powerCustomPaths[3].slice(0, 4);
        a.saveState('Power Custom Path Edit');
        a.updateLayers([l]); }""")
    _settle(pg)
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    s = read(pg)
    assert s['overrides'] == [2, 3]
    assert cols_of(s)[3] == [3]
    assert_no_jumps(s)
    assert errors == []
