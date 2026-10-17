"""Three fixes before the 1.5 beta, each pinned to its repro.

1. A multi left on a one-circuit DIRECT output (the flagged error state)
   no longer collapses on the pull sheet: every circuit's cable and the
   output's home run are their own rows, the box keeps its home run (the
   binder's captions read it), and the map's cable tag never hangs the
   output's home run on one of its circuits.
2. The binder's Distro page HOME RUN for a circuit alone on a direct
   output is that output's one cable - the circuit's own when typed - the
   figure the map tag and the pull sheet print.
3. The NovaStar Armor custom readout: "full" once no free cabinet would be
   accepted (one more can grow the rectangle by a whole row or column),
   and the count in cabinets actually placed against the port's capacity.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_audit_final_fixes.py -q --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' "
                         "&& window.canvasRenderer")
    yield pg, errors
    context.close()


# Screens from specs, the project replaced; waits on the saves themselves.
SEED_JS = """async (specs) => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = async (method, url, body) => (await fetch(url, {
        method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body) })).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    for (const s of specs) {
        await j('POST', '/api/layer/add', { name: s.name, columns: s.columns, rows: s.rows,
            cabinet_width: s.w || 200, cabinet_height: s.h || 200, offset_x: s.x || 0 });
    }
    const p = await j('GET', '/api/project');
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.length;
}"""


def ev(pg, body, arg=None):
    return pg.evaluate(
        "(arg) => { const app = window.app; "
        "const A = app.project.layers.find(l => l.name === 'WALL A'); "
        "const B = app.project.layers.find(l => l.name === 'WALL B'); "
        f"{body} }}", arg)


# ── 1 & 2: direct outputs ──────────────────────────────────────────────────

# True1 x5 + Socapex x2 on 120/208: outputs 1-5 are True1, 6-7 Socapex.
FACE = {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
        'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 5, 'coupling': 'll',
                        'breakerA': 20},
                       {'id': 'r2', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                        'breakerA': 20}]}

# Every assignment cleared, then the walls' own; returns each wall's circuits.
SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        const key = l.name === 'WALL A' ? 'a' : 'b';
        Object.assign(l, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerLabelOverrides: {}, powerCircuitCables: {},
                           powerBreakoutType: null, locked: false },
                      (o.walls || {})[key] || {});
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    const out = {};
    for (const l of app.project.layers) {
        out[l.name] = app.screenCircuits(l).map(c => c.num);
    }
    return out;
}"""

# The pull sheet's rows, jumpers / breakouts / distros left out.
ROWS_JS = """() => window.app.buildPullList().positions.flatMap(p => p.rows)
    .filter(r => !/Jump|Breakout|Distro/.test(r.type))
    .map(r => [r.type, r.length, r.qty, r.label, r.notes])"""


@pytest.fixture(scope="module")
def walls(page):
    pg, errors = page
    pg.locator('[data-mode="power"]').click()
    assert pg.evaluate(SEED_JS, [
        {'name': 'WALL A', 'columns': 10, 'rows': 6},
        {'name': 'WALL B', 'columns': 6, 'rows': 3, 'x': 2600}]) == 2
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    return pg, errors


# WALL A's six-circuit multi on output 4 (a True1), home run 100'.
CROWDED = {'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4},
                 'powerSocaLengths': {'1': '100'}}}


def _crowd(pg, cables):
    """WALL A crowded onto PD 4; `cables` the feet typed on its circuits in
    order (None leaves a circuit without one). Returns A's circuits."""
    nums = pg.evaluate(SETUP_JS, {'distros': [FACE], 'walls': CROWDED})['WALL A']
    assert len(nums) == 6, nums
    ev(pg, """
        A.powerCircuitCables = {};
        arg.nums.forEach((n, i) => {
            if (arg.cables[i] != null) A.powerCircuitCables[n] = { ft: arg.cables[i], connector: null };
        });
        app._circuitTailCache = null;
        return null;""", {'nums': nums, 'cables': cables})
    return nums


def test_the_crowded_output_is_the_flagged_error_state(walls):
    """The repro's footing: six circuits on PD4, a True1, flagged by the
    strip's own check and labelled PD4-1..PD4-6."""
    pg, _ = walls
    _crowd(pg, [10, 15, 20, 25, 30, 35])
    out = ev(pg, """
        const s = app.getSocaPlan(A)[0];
        return { labels: s.legs.map(g => g.label),
                 checks: app.distroChecks(app.getDistros()[0]).map(w => w.text) };""")
    assert out['labels'] == [f'PD4-{i}' for i in range(1, 7)], out
    assert ("WALL A's 6 circuits are on PD4, a True1 — one circuit only. "
            'Move it to a multi output.') in out['checks'], out['checks']


def test_a_crowded_direct_output_lists_every_cable(walls):
    """The pull sheet used to print one row - `Tru-1 35' PD 4` - each
    circuit's cable overwriting the output's one cable. Now all seven
    cables are listed: the six circuit cables under their circuits and the
    100' home run under the output, flagged in Notes."""
    pg, errors = walls
    _crowd(pg, [10, 15, 20, 25, 30, 35])
    rows = pg.evaluate(ROWS_JS)
    lengths = sorted(int(r[1].rstrip("'")) for r in rows if r[1].endswith("'"))
    assert lengths == [10, 15, 20, 25, 30, 35, 100], rows
    labels = {r[1]: r[3] for r in rows}
    for i, ft in enumerate([10, 15, 20, 25, 30, 35], start=1):
        assert labels[f"{ft}'"] == f'PD4-{i}', rows
    home = [r for r in rows if r[1] == "100'"]
    assert len(home) == 1 and home[0][3] == 'PD 4', rows
    assert '6 circuits on a one-circuit output' in home[0][4], home
    assert sum(r[2] for r in rows) == 7, 'nothing undercounted'
    # The box the binder's captions read keeps the output's home run.
    box = ev(pg, """
        const b = app.buildPullList().byScreen[A.id].boxes[0];
        return { homeRun: b.homeRun, crowded: b.crowded || 0, n: b.circuits.length };""")
    assert box == {'homeRun': 100, 'crowded': 6, 'n': 6}, box
    assert errors == [], errors


def test_a_crowded_output_with_no_circuit_cables_lists_its_home_run(walls):
    """No circuit cable typed: the home run is still its own row, flagged."""
    pg, _ = walls
    _crowd(pg, [None] * 6)
    rows = pg.evaluate(ROWS_JS)
    home = [r for r in rows if r[3] == 'PD 4']
    assert len(home) == 1 and home[0][1] == "100'", rows
    assert '6 circuits on a one-circuit output' in home[0][4], home


# Every cable tag the power map paints for WALL A, tags on.
TAGS_JS = """() => {
    const app = window.app, r = window.canvasRenderer;
    const A = app.project.layers.find(l => l.name === 'WALL A');
    A.showPowerCableTags = true;
    app.currentLayer = A;
    r.viewMode = 'power';
    const seen = [];
    const orig = r.drawCableTag;
    r.drawCableTag = function (text) { seen.push(String(text)); return orig.apply(this, arguments); };
    try { r.render(); } finally { r.drawCableTag = orig; A.showPowerCableTags = false; }
    return seen;
}"""


def test_the_map_tag_never_hangs_a_crowded_home_run_on_a_circuit(walls):
    """On a crowded output each circuit's tag is its own cable; a circuit
    with none gets no tag - not the output's 100' home run, which is no one
    circuit's cable."""
    pg, errors = walls
    _crowd(pg, [10, 15, 20, 25, 30, None])
    tags = pg.evaluate(TAGS_JS)
    assert sorted(t for t in tags if "'" in t) == sorted(
        f"{ft}' True1" for ft in (10, 15, 20, 25, 30)), tags
    assert not [t for t in tags if t.startswith("100'")], tags
    assert errors == [], errors


def test_a_lone_direct_circuit_keeps_its_one_cable(walls):
    """The legal case is unchanged: WALL B's one circuit on PD 5, home run
    25', circuit cable 10' - one `Tru-1 10'` row, the tag 10' True1."""
    pg, _ = walls
    nums = pg.evaluate(SETUP_JS, {'distros': [FACE], 'walls': {'b': {
        'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
        'powerSocaLengths': {'1': '25'}, 'powerCircuitCables': {}}}})['WALL B']
    ev(pg, "B.powerCircuitCables = { [arg]: { ft: 10, connector: null } }; return null;", nums[0])
    rows = [r for r in pg.evaluate(ROWS_JS) if r[0] == 'Tru-1']
    assert rows == [['Tru-1', "10'", 1, 'PD 5', '']], rows
    one = ev(pg, "const c = app.directCircuitCable(B, arg); return c && c.text;", nums[0])
    assert one == "10' True1"


# The Distro page's rows: each box's cells, caught as the page builds them.
DISTRO_ROWS_JS = """() => {
    const app = window.app;
    const caught = [];
    const orig = app._bDistroBlocks;
    app._bDistroBlocks = function (book, d, load, boxes) {
        caught.push(...boxes.map(b => b.cells));
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bDistroBlocks = orig; }
    return caught;
}"""


def test_the_distro_page_home_run_is_the_direct_outputs_one_cable(walls):
    """WALL B's first circuit on PD 5, home run '25', circuit cable 10'.
    The map tag and the pull list say 10'; the Distro page's HOME RUN said
    25'. It now says 10' too."""
    pg, errors = walls
    nums = pg.evaluate(SETUP_JS, {'distros': [FACE], 'walls': {'b': {
        'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
        'powerSocaLengths': {'1': '25'}}}})['WALL B']
    ev(pg, "B.powerCircuitCables = { [arg]: { ft: 10, connector: null } }; return null;", nums[0])
    cells = pg.evaluate(DISTRO_ROWS_JS)
    pd5 = [c for c in cells if c[0] == 'PD 5']
    assert len(pd5) == 1, cells
    assert pd5[0][2] == "10'", pd5
    pull = [r for r in pg.evaluate(ROWS_JS) if r[3] == 'PD 5']
    assert [r[1] for r in pull] == ["10'"], pull
    # No circuit cable: the output's home run, as the tag and the sheet say.
    ev(pg, "B.powerCircuitCables = {}; return null;")
    pd5 = [c for c in pg.evaluate(DISTRO_ROWS_JS) if c[0] == 'PD 5']
    assert pd5[0][2] == "25'", pd5
    assert errors == [], errors


# The power wiring sheet's device captions for one wall.
CAPTIONS_JS = """(name) => {
    const app = window.app;
    const L = app.project.layers.find(l => l.name === name);
    const list = app.buildPullSheet();
    const book = { list, layers: new Map(app.project.layers.map(l => [String(l.id), l])) };
    return app._bwPowerFacts(book, L, list.byScreen[L.id]).devices.map(d => d.title);
}"""

# The home-run text the exported map's multi brackets print for WALL B.
BRACKETS_JS = """() => {
    const app = window.app, r = window.canvasRenderer;
    const B = app.project.layers.find(l => l.name === 'WALL B');
    B.showSocaBrackets = true;
    app.currentLayer = B;
    r.viewMode = 'power';
    const seen = [];
    const orig = r._homeRunText;
    r._homeRunText = function () { const t = orig.apply(this, arguments); seen.push(t); return t; };
    const was = r.exportMode;
    r.exportMode = true;
    try { r.render(); } finally {
        r._homeRunText = orig; r.exportMode = was; B.showSocaBrackets = false; r.render();
    }
    return seen;
}"""


def test_the_captions_say_the_one_cable_or_the_crowd(walls):
    """The wiring sheet's caption and the exported map's bracket for a lone
    direct circuit print its one cable (10', not the 25' home run); a
    crowded output's caption prints the home run and says it is crowded -
    never one circuit's cable."""
    pg, errors = walls
    nums = pg.evaluate(SETUP_JS, {'distros': [FACE], 'walls': {'b': {
        'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
        'powerSocaLengths': {'1': '25'}}}})['WALL B']
    ev(pg, "B.powerCircuitCables = { [arg]: { ft: 10, connector: null } }; return null;", nums[0])
    caps = pg.evaluate(CAPTIONS_JS, 'WALL B')
    assert caps[0] == "PD5 · True1 208V · 10'", caps
    assert "10'" in pg.evaluate(BRACKETS_JS)
    _crowd(pg, [10, 15, 20, 25, 30, 35])
    caps = pg.evaluate(CAPTIONS_JS, 'WALL A')
    assert caps == ["PD4 · True1 208V · 100' · 6 circuits on a one-circuit output"], caps
    assert errors == [], errors


def test_the_distro_page_keeps_a_crowded_outputs_home_run(walls):
    """A crowded output has no one cable: its row reads the home run."""
    pg, _ = walls
    _crowd(pg, [10, 15, 20, 25, 30, 35])
    pd4 = [c for c in pg.evaluate(DISTRO_ROWS_JS) if c[0] == 'PD 4']
    assert len(pd4) == 1 and pd4[0][2] == "100'" and pd4[0][4] == '6', pd4


# ── 3: the Armor custom readout ────────────────────────────────────────────

# One 8 x 8 wall of 200 px cabinets, custom data on `proc`, port 1 drawn
# over `cells` ([row, col]); the readout, the badge and the fill read back.
ARMOR_JS = """async (o) => {
    const app = window.app, r = window.canvasRenderer;
    const L = app.project.layers[0];
    Object.assign(L, { processorType: o.proc, bitDepth: 8, frameRate: 60, lowLatency: false,
                       flowPattern: 'custom', portMappingMode: 'organized',
                       customPortPaths: { 1: o.cells.map(([row, col]) => ({ row, col })) },
                       customPortIndex: 1, customPortOverrides: [], locked: false });
    app.currentLayer = L;
    app.selectedLayerIds = new Set([L.id]);
    if (app.customSelection) app.customSelection.clear();
    app._toast = () => {};
    r.viewMode = 'data-flow';
    app.loadLayerToInputs();
    app._syncCustomFillReadout('data');
    r.render();
    const fill = app.customRunFill(L, 'data', 1);
    return {
        limit: app.customRunCapacity(L, 'data').limit,
        text: fill.text, full: fill.full, used: fill.used, count: fill.count,
        load: fill.load, unit: fill.unit,
        readout: document.getElementById('custom-fill-readout').textContent,
        badge: r._lastActiveBadge ? r._lastActiveBadge.pill : null,
    };
}"""

# Every free cabinet clicked onto port 1: how many the run took. The path
# is put back after each so every click is judged against the same run.
CLICK_ALL_JS = """() => {
    const app = window.app;
    const L = app.project.layers[0];
    const start = L.customPortPaths[1].slice();
    const keys = new Set(start.map(e => `${e.row},${e.col}`));
    app.updateLayers = () => {};
    app.saveState = () => {};
    app.saveClientSideProperties = () => {};
    let took = 0;
    for (const p of L.panels) {
        if (keys.has(`${p.row},${p.col}`)) continue;
        app.addPanelToCustomPath(p, L);
        if (L.customPortPaths[1].length > start.length) took++;
        L.customPortPaths[1] = start.slice();
    }
    return took;
}"""


@pytest.fixture()
def armor(page):
    pg, errors = page
    pg.locator('[data-mode="data-flow"]').click()
    assert pg.evaluate(SEED_JS, [{'name': 'ARMOR', 'columns': 8, 'rows': 8}]) == 1
    pg.wait_for_function("() => window.app.project.layers.length === 1 "
                         "&& window.app.project.layers[0].name === 'ARMOR'")
    yield pg, errors
    # The click sweep stubbed the saves on the page; a fresh load next time.
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")


SOLID_3x5 = [[row, col] for row in range(5) for col in range(3)]
# An L of 7: the top row four wide, then down the first column - a 4 x 4
# rectangle (16 cabinets of pixels) with nine free holes inside it.
L_OF_7 = [[0, 0], [0, 1], [0, 2], [0, 3], [1, 0], [2, 0], [3, 0]]


def test_a_solid_armor_run_that_takes_no_cabinet_reads_full(armor):
    """Armor, 200 px cabinets, cap 659,722 px, a solid 3 x 5 run: every
    other cabinet grows the rectangle past the cap and is refused, so the
    readout says full - it used to read "15/16" with no "· full"."""
    pg, errors = armor
    out = pg.evaluate(ARMOR_JS, {'proc': 'novastar-armor', 'cells': SOLID_3x5})
    assert out['limit'] == 659722, out
    assert out['text'] == '15/16' and out['full'] is True, out
    assert out['readout'].startswith('Port ') and '15/16 panels · full' in out['readout'], out
    assert out['badge'] == '15/16 on port · full', out
    assert pg.evaluate(CLICK_ALL_JS) == 0, 'full means no click is taken'
    assert errors == [], errors


def test_an_armor_l_reads_its_placed_cabinets_and_is_not_full(armor):
    """An L of 7 cabinets pays for its 4 x 4 rectangle, but it is 7 placed
    cabinets of 16, and its holes still fit: "7/16", not full. It used to
    read "16/16 · full" while the holes took clicks."""
    pg, errors = armor
    out = pg.evaluate(ARMOR_JS, {'proc': 'novastar-armor', 'cells': L_OF_7})
    assert out['text'] == '7/16' and out['full'] is False, out
    assert '· full' not in out['readout'] and '7/16 panels' in out['readout'], out
    assert out['badge'] == '7/16 on port', out
    assert out['load'] == 640000, 'the badge still charges the rectangle'
    assert pg.evaluate(CLICK_ALL_JS) > 0
    assert errors == [], errors


def test_other_processors_keep_their_readout(armor):
    """A processor that pays the sum of its cabinets reads as it always
    did: used = load / cabinet, full when another whole cabinet would not
    fit."""
    pg, _ = armor
    out = pg.evaluate(ARMOR_JS, {'proc': 'brompton', 'cells': SOLID_3x5})
    assert out['limit'] > 0, out
    assert out['load'] == 15 * 40000
    assert out['used'] == pytest.approx(out['load'] / out['unit'])
    assert out['full'] is (out['load'] + out['unit'] > out['limit'] + 1e-6), out
    assert out['text'] == f"15/{out['limit'] // 40000}", out
