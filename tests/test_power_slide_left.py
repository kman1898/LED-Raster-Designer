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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
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


# ── Redrawn smaller by clicking (1.6.0 QA, beta.5) ────────────────────────
#
# "Clicking an earlier cabinet of the run being drawn cuts it back", on
# power as on data, and the cabinets cut off stay with the redraw until it
# ends (the walk does not take them back as the next circuit). Clear
# Circuit in a redraw frees the circuit's own cabinets to be drawn again,
# and a redraw that ends with nothing drawn goes back to automatic (no
# phantom circuits). All by hand: Alt+click, clicks, Esc.

CELL_JS = """([col, row]) => {
    const a = window.app, r = window.canvasRenderer;
    const l = a.project.layers.find(x => x.name === 'Wall');
    const p = l.panels.find(q => q.col === col && q.row === row);
    const off = a._getLayerWorkspaceOffset(l);
    const rc = r.canvas.getBoundingClientRect();
    const sx = rc.width / r.canvas.width;
    return { x: rc.left + (r.panX + (off.wx + p.x + p.width / 2) * r.zoom) * sx,
             y: rc.top + (r.panY + (off.wy + p.y + p.height / 2) * r.zoom) * sx };
}"""


def _cell(pg, col, row):
    return pg.evaluate(CELL_JS, [col, row])


def _click(pg, col, row, alt=False):
    c = _cell(pg, col, row)
    pg.mouse.move(c['x'], c['y'])
    if alt:
        pg.keyboard.down('Alt')
    pg.mouse.click(c['x'], c['y'])
    if alt:
        pg.keyboard.up('Alt')
    _settle(pg)


def _fit(pg):
    pg.evaluate("() => window.canvasRenderer.fitToView()")
    pg.wait_for_timeout(200)


def _path(pg, num):
    return pg.evaluate("""(n) => (window.app.project.layers.find(x => x.name === 'Wall')
        .powerCustomPaths || {})[n] || null""", num)


def test_clicking_an_earlier_cabinet_cuts_the_circuit_back_and_the_rest_slide_left(page):
    """The owner's case end to end: Alt+click S1-2 (columns 2-3), click its
    first cabinet (the circuit now ends there), draw column 2 down, Esc.
    S1-2 is one column, and the automatic circuits after it slide left
    and pair: columns 3-4 a 2fer, 5-6 a 2fer, 7 alone."""
    pg, errors = page
    open_show(pg, {}, '1.6.0')
    _fit(pg)
    assert cols_of(read(pg)) == {1: [0, 1], 2: [2, 3], 3: [4, 5], 4: [6, 7]}
    _click(pg, 2, 1, alt=True)
    assert read(pg)['editing']['num'] == 2
    assert len(_path(pg, 2)) == 8
    _click(pg, 2, 0)
    assert _path(pg, 2) == [{'row': 0, 'col': 2}], _path(pg, 2)
    assert any('now ends at' in t for t in toasts(pg)), toasts(pg)
    # the cut cabinets stay with the redraw: column 3 is no circuit yet
    held = cols_of(read(pg))
    assert 3 not in [c for cols in held.values() for c in cols], held
    for r in (1, 2, 3):
        _click(pg, 2, r)
    assert not any('already wired' in t for t in toasts(pg)), toasts(pg)
    pg.keyboard.press('Escape')
    _settle(pg)
    s = read(pg)
    assert s['editing'] is None
    assert s['overrides'] == [2] and s['serverOverrides'] == [2]
    assert cols_of(s) == {1: [0, 1], 2: [2], 3: [3, 4], 4: [5, 6], 5: [7]}, s
    ways = {c['num']: c['ways'] for c in s['circuits']}
    assert ways[3] == 2 and ways[4] == 2 and ways[5] == 1, ways
    assert_no_jumps(s)
    assert errors == []


def test_clear_circuit_in_a_redraw_frees_its_own_cabinets_and_an_empty_redraw_goes_back(page):
    """Redraw S1-2, Clear Circuit: its own cabinets are free to draw again
    (each click was refused as "already wired to circuit S1-2"). Clear it
    again and Esc: nothing is drawn, so the circuit goes back to automatic
    and says so - it is never left taken over with an empty path."""
    pg, errors = page
    open_show(pg, {}, '1.6.0')
    _fit(pg)
    before = read(pg)
    _click(pg, 2, 1, alt=True)
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)
    for r in range(4):
        _click(pg, 2, r)
    assert not any('already wired' in t for t in toasts(pg)), toasts(pg)
    assert _path(pg, 2) == [{'row': r, 'col': 2} for r in range(4)], _path(pg, 2)
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    s = read(pg)
    assert s['editing'] is None
    assert s['overrides'] == [] and s['serverOverrides'] == [], s
    assert _path(pg, 2) is None
    assert s['circuits'] == before['circuits']
    assert any('nothing was drawn on circuit' in t for t in toasts(pg)), toasts(pg)
    assert errors == []


def test_an_older_show_with_an_empty_taken_over_circuit_opens_automatic(page):
    """A show saved in that state (circuit 2 taken over, nothing on it)
    opens with circuit 2 back to automatic, and the toast says so."""
    pg, errors = page
    open_show(pg, {'2': []}, '1.6.0')
    s = read(pg)
    assert s['overrides'] == [] and s['serverOverrides'] == [], s
    assert cols_of(s) == {1: [0, 1], 2: [2, 3], 3: [4, 5], 4: [6, 7]}, s
    assert any('had nothing drawn on it' in t for t in toasts(pg)), toasts(pg)
    assert errors == []


# Every label the Wall's frame draws, as {circuit number: [labels]}: the
# discs on the wall and the redraw's own badge.
WALL_LABELS_JS = """() => {
    const a = window.app, r = window.canvasRenderer;
    const real = a.getPowerCircuitLabel;
    const out = {};
    a.getPowerCircuitLabel = function (layer, n) {
        const v = real.call(this, layer, n);
        if (layer && layer.name === 'Wall') (out[n] = out[n] || []).push(v);
        return v;
    };
    try { a._circuitTailCache = null; r.render(); } finally { a.getPowerCircuitLabel = real; }
    return out;
}"""


def _wall_labels(pg):
    """{num: label} for the frame, each circuit read one way only."""
    drawn = pg.evaluate(WALL_LABELS_JS)
    out = {}
    for n, labels in drawn.items():
        assert len(set(labels)) == 1, (n, labels)
        out[int(n)] = labels[0]
    return out


def test_clear_circuit_in_a_redraw_leaves_every_other_circuit_its_name(page):
    """Redraw S1-2 and Clear Circuit: circuit 3 kept reading S1-2 beside
    the redraw's own S1-2 badge (two S1-2 labels) until Esc. The circuit
    being redrawn keeps its place, so the others keep their names while
    it is empty, while it is drawn again, and after Esc."""
    pg, errors = page
    open_show(pg, {}, '1.6.0')
    _fit(pg)
    before = _wall_labels(pg)
    assert before == {1: 'S1-1', 2: 'S1-2', 3: 'S1-3', 4: 'S1-4'}, before
    _click(pg, 2, 1, alt=True)
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)
    assert read(pg)['editing']['num'] == 2
    held = _wall_labels(pg)
    assert held == before, held
    assert len(set(held.values())) == len(held), held
    # one cabinet drawn on it again: still one name each
    _click(pg, 2, 0)
    assert _wall_labels(pg) == before
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)
    assert read(pg)['editing'] is None
    # the redraw kept its one cabinet, so the walk after it has one more
    # circuit: still a name each, in order
    after = _wall_labels(pg)
    assert after == {n: f'S1-{n}' for n in range(1, len(after) + 1)}, after
    assert errors == []


# The Wall in plain Custom mode, drawn as `paths` with circuit `idx` active.
CUSTOM_JS = """([paths, idx]) => { const a = window.app;
    const l = a.project.layers.find(x => x.name === 'Wall');
    a.selectLayer(l);
    Object.assign(l, { powerCustomPath: true, powerFlowPattern: 'custom', powerCustomOverrides: [],
                       powerCustomPaths: paths, powerCustomIndex: idx });
    l._powerCircuits = null;
    a.updateLayers([l]);
    a.resetHistory('Custom Baseline');
    a.updateCustomPowerUI();
    window.canvasRenderer.render(); }"""

FOUR = {'1': col_path(0, 1), '2': col_path(2, 3), '3': col_path(4, 5), '4': col_path(6, 7)}


def _custom_wall(pg, paths, idx):
    open_show(pg, {}, '1.6.0')
    pg.evaluate(CUSTOM_JS, [paths, idx])
    _settle(pg)
    _fit(pg)


def _wall_state(pg):
    return pg.evaluate("""() => { const l = window.app.project.layers.find(x => x.name === 'Wall');
        return { idx: l.powerCustomIndex,
                 drawn: Object.keys(l.powerCustomPaths || {}).filter(k => (l.powerCustomPaths[k] || []).length)
                     .map(Number) }; }""")


def test_a_cleared_custom_circuit_off_a_multi_never_shares_a_name(page):
    """Plain Custom mode, no distro: Clear Circuit on S1-2 of four. The
    drawn circuits close up over the gap (3 reads S1-2, 4 reads S1-3), and
    the active circuit's badge read S1-2 too. The owner, 2026-11-04: "If
    they have not been attached to a multi, they cannot be the same
    number." The badge reads the next circuit after the last drawn one,
    S1-4. The active circuit stays on the gap (Next and Prev step from
    it), and a cabinet drawn there seats it back in its place: still one
    name each."""
    pg, errors = page
    _custom_wall(pg, FOUR, 2)
    assert _wall_labels(pg) == {1: 'S1-1', 2: 'S1-2', 3: 'S1-3', 4: 'S1-4'}
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)
    labels = _wall_labels(pg)
    assert len(set(labels.values())) == len(labels), labels
    assert _wall_state(pg) == {'idx': 2, 'drawn': [1, 3, 4]}
    assert labels == {1: 'S1-1', 2: 'S1-4', 3: 'S1-2', 4: 'S1-3'}, labels
    # a cabinet drawn on it: back in its place, one name each
    _click(pg, 2, 0)
    assert _wall_state(pg) == {'idx': 2, 'drawn': [1, 2, 3, 4]}
    assert _wall_labels(pg) == {1: 'S1-1', 2: 'S1-2', 3: 'S1-3', 4: 'S1-4'}
    assert errors == []


def test_a_cleared_circuit_on_a_plugged_multi_keeps_its_tail(page):
    """On a distro the multi keeps its tails where the clear left them
    (sticky multi numbers): circuit 3 stays SL1-3, the cleared circuit
    reads its own free tail SL1-2, and it stays the active circuit."""
    pg, errors = page
    _custom_wall(pg, FOUR, 2)
    pg.evaluate("""() => { const a = window.app; const l = a.project.layers.find(x => x.name === 'Wall');
        const d = a.addDistro({ name: 'SL' });
        l.powerSocaDistro = { 1: (d && d.id) || a.getDistros()[0].id };
        a.updateLayers([l]); a._circuitTailCache = null; window.canvasRenderer.render(); }""")
    _settle(pg)
    assert _wall_labels(pg) == {1: 'SL1-1', 2: 'SL1-2', 3: 'SL1-3', 4: 'SL1-4'}
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)
    assert _wall_state(pg) == {'idx': 2, 'drawn': [1, 3, 4]}
    assert _wall_labels(pg) == {1: 'SL1-1', 2: 'SL1-2', 3: 'SL1-3', 4: 'SL1-4'}
    assert errors == []
