"""Cable lengths in feet or meters: the fixes after the 1.5 audit.

* A direct output's cable is printed once on the pull sheet: the circuit's
  own cable when it has one (what the map's cable tag shows), else the
  output's home run - never both, and never a "no length" row beside a
  circuit cable that has one.
* Jumpers nobody typed are not stored: a new screen follows the
  Preferences' jumper lengths in the show's unit, the way a screen from an
  older file always has, and only lengths somebody typed count in the unit
  change's "N cable lengths already typed". A feet show that stores its
  jumpers prints exactly what it printed before.
* One reading of a typed length (parseCableLength): a bare number, or a
  number with the show's own unit ("30m" / "30 m" in meters; "100ft",
  "100 ft", "100'" in feet). The other unit's suffix is unreadable and
  reads as no length - never silently taken as the show's unit.
* Undo and redo wait for the pull sheet's POST queue (cable unit, edits)
  so an older POST can not land after the restore.
* Load readouts print en-US figures whatever the browser's locale.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ── the server: a new screen stores no jumper lengths ──────────────────────

JUMPER_FIELDS = ('dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH')


def test_a_new_screen_is_made_without_jumper_lengths(client):
    """create_layer stores none of the four: the screen reads the
    Preferences in its show's unit until somebody types one. A body that
    carries them (duplicate, paste) still stores them."""
    import app as app_module
    keep = app_module.server_preferences
    try:
        app_module.server_preferences = {'dataJumpLength': 1}
        r = client.post('/api/layer/add', json={'name': 'S', 'columns': 2, 'rows': 2,
                                                'cabinet_width': 100, 'cabinet_height': 100})
        assert not [k for k in JUMPER_FIELDS if k in r.get_json()], r.get_json()
        p = client.post('/api/project/new').get_json()
        assert not [k for k in JUMPER_FIELDS if k in p['layers'][0]], p['layers'][0]
        r = client.post('/api/layer/add', json={'name': 'T', 'columns': 2, 'rows': 2,
                                                'cabinet_width': 100, 'cabinet_height': 100,
                                                'dataJumpV': 2, 'powerJumpH': None})
        layer = r.get_json()
        assert layer['dataJumpV'] == 2 and layer['powerJumpH'] is None
        assert 'dataJumpH' not in layer and 'powerJumpV' not in layer
    finally:
        app_module.server_preferences = keep


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) the way this
    module found them."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && Array.isArray(window.app.project.layers)"
                         " && window.canvasRenderer")
    yield pg, errors
    context.close()


J = """const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());"""

# A fresh project of screens made through the real add route; `strip`
# names screens whose jumper fields are taken off on the server, the way a
# file saved before them reads. Answers {name: id}.
RESET_JS = """async ({bodies, unit, strip}) => {
    """ + J + """
    await app._layerSavesSettled();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    proj.cableUnit = unit || 'ft';
    await j('PUT', '/api/project', proj);
    for (const b of bodies) await j('POST', '/api/layer/add', b);
    const p = await j('GET', '/api/project');
    for (const l of p.layers) {
        if ((strip || []).includes(l.name)) {
            for (const k of ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']) delete l[k];
        }
    }
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('metric_audit');
    for (const b of bodies) {
        const l = app.project.layers.find(x => x.name === b.name);
        for (const k of ['flowPattern', 'processorType']) if (b[k] !== undefined) l[k] = b[k];
    }
    app.selectLayer(app.project.layers[0]);
    app.resetHistory('Metric Audit');
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""


def _reset(pg, bodies, unit='ft', strip=()):
    return pg.evaluate(RESET_JS, {'bodies': bodies, 'unit': unit, 'strip': list(strip)})


def _screen(name, cols, rows, w=60, h=60, **extra):
    body = {'name': name, 'columns': cols, 'rows': rows, 'cabinet_width': w, 'cabinet_height': h,
            'processorType': 'novastar-armor', 'flowPattern': 'tl-h',
            'powerVoltage': 208, 'powerAmperage': 20, 'panelWatts': 200}
    body.update(extra)
    return body


def ev(pg, body, arg=None):
    return pg.evaluate(f"(arg) => {{ const app = window.app; {body} }}", arg)


# ── #12: jumpers nobody typed follow the Preferences ─────────────────────

JUMP_ROWS_JS = """() => {
    const app = window.app;
    const list = app.buildPullList();
    const rows = list.positions.flatMap(p => p.rows)
        .filter(r => /Jump/.test(r.type))
        .map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    const per = Object.fromEntries(app.project.layers.map(l =>
        [l.name, list.byScreen[String(l.id)].jumperLengths]));
    return { rows, per };
}"""


def test_a_feet_show_that_stores_its_jumpers_prints_exactly_as_before(page):
    """STORED holds the four (as every 1.4 screen does - 6' seeded, or a
    figure typed), OLD holds none (a file from before the fields). The
    jumper rows and the per-screen tallies are the 1.4.1 output, byte for
    byte."""
    pg, errors = page
    _reset(pg, [_screen('STORED', 3, 2, dataJumpV=6, dataJumpH=2, powerJumpV=6, powerJumpH=None),
                _screen('OLD', 3, 2)], strip=['OLD'])
    out = pg.evaluate(JUMP_ROWS_JS)
    # captured from 1.5 before the fix, on this same show
    assert out['rows'] == [
        ['Data Jump', "2'", 4, 'STORED', ''],
        ['Data Jump', "6'", 1, 'STORED', ''],
        ['Tru-1 Power Jump', "6'", 1, 'STORED', ''],
        ['Data Jump', "6'", 5, 'OLD', ''],
        ['Tru-1 Power Jump', "6'", 5, 'OLD', ''],
    ], out
    assert out['per'] == {
        'STORED': {'data': {'2': 4, '6': 1}, 'power': {'6': 1}},
        'OLD': {'data': {'6': 5}, 'power': {'6': 5}},
    }, out
    assert errors == [], errors


def test_a_new_screens_untouched_jumpers_follow_the_unit_and_are_not_counted(page):
    """A screen made in the app stores no jumper lengths: in a feet show
    it reads the feet Preferences (6'), and after a change to meters the
    meters ones (2 m) - not "6 m". A length somebody typed keeps its
    number and is the only one the change counts."""
    pg, errors = page
    _reset(pg, [])
    ev(pg, "app.addLayer(); return null;")
    pg.wait_for_function("() => window.app.project.layers.length === 1 && window.app.currentLayer")
    out = pg.evaluate("""async () => {
        """ + J + """
        await app._layerSavesSettled();
        const l = app.project.layers[app.project.layers.length - 1];
        const served = (await j('GET', '/api/project')).layers.find(x => x.id === l.id);
        return { stored: ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH'].filter(k => k in l),
                 served: ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH'].filter(k => k in served),
                 reads: app.screenJumperLengths(l), count: app.typedCableLengthCount() };
    }""")
    assert out['stored'] == [] and out['served'] == [], out
    assert out['reads'] == {'data': {'v': 6, 'h': 6}, 'power': {'v': 6, 'h': 6}}, out
    assert out['count'] == 0, out
    # one length typed in the sidebar
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => document.getElementById('power-jump-v').offsetParent !== null")
    pg.fill('#power-jump-v', '4')
    pg.locator('#power-jump-v').dispatch_event('change')
    pg.wait_for_function("() => window.app.typedCableLengthCount() === 1")
    asked = []
    pg.once('dialog', lambda d: (asked.append(d.message), d.accept()))
    assert ev(pg, "return app.setCableUnit('m');") is True
    assert asked and '1 cable length already typed' in asked[0], asked
    out = ev(pg, """const l = app.currentLayer;
        return { reads: app.screenJumperLengths(l), shown: document.getElementById('data-jump-v').value };""")
    assert out['reads'] == {'data': {'v': 2, 'h': 2}, 'power': {'v': 4, 'h': 2}}, out
    pg.locator('[data-mode="pixel-map"]').click()
    assert errors == [], errors


def test_a_preset_carries_only_the_lengths_the_screen_holds(page):
    """Saved as a panel preset, a screen nobody typed jumpers on carries
    none, so the preset's screens follow the Preferences in whatever unit
    they land in; a typed one (and a blank, null) travels."""
    pg, _ = page
    _reset(pg, [_screen('P', 2, 2), _screen('Q', 2, 2, dataJumpV=1.5, powerJumpH=None)],
           strip=['P'])
    out = ev(pg, """
        const P = app.project.layers.find(l => l.name === 'P');
        const Q = app.project.layers.find(l => l.name === 'Q');
        const keys = (o) => ['dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']
            .filter(k => k in o && o[k] !== undefined).map(k => [k, o[k]]);
        const fresh = {id: 999, type: 'screen', columns: 2, rows: 2, panels: []};
        app.initializeLayerDefaults(fresh);
        return { p: keys(app.serializeLayerAsPreset(P)), q: keys(app.serializeLayerAsPreset(Q)),
                 fresh: keys(fresh) };""")
    assert out['p'] == [] and out['fresh'] == [], out
    assert ['dataJumpV', 1.5] in out['q'] and ['powerJumpH', None] in out['q'], out


# ── #13: one reading of a typed length ───────────────────────────────────

def test_the_one_length_parser(page):
    pg, _ = page
    table = [
        # value, unit, reading
        ('30', 'm', 30), ('30m', 'm', 30), ('30 m', 'm', 30), ('30 M', 'm', 30),
        ('7.62 m', 'm', 7.62), ('30ft', 'm', None), ("30'", 'm', None),
        ('100', 'ft', 100), ('100ft', 'ft', 100), ('100 ft', 'ft', 100), ("100'", 'ft', 100),
        ("100 '", 'ft', 100), ('2.5ft', 'ft', 2.5), ('30m', 'ft', None), ('30 m', 'ft', None),
        ('', 'ft', None), ('0', 'ft', None), ('-5', 'ft', None), ('abc', 'ft', None),
        ('ft', 'ft', None), (25, 'ft', 25), (0, 'm', None), (None, 'ft', None),
    ]
    got = pg.evaluate("(t) => t.map(([v, u]) => window.app.parseCableLength(v, u))",
                      [[v, u] for v, u, _ in table])
    assert got == [want for _, _, want in table], [
        (row, g) for row, g in zip(table, got) if g != row[2]]


DIST_US = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208',
           'outputRows': [{'connector': 'soca', 'count': 4, 'coupling': 'll'},
                          {'connector': 'true1', 'count': 3, 'coupling': 'll'}]}

SETUP_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        Object.assign(l, { powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerCircuitCables: {}, locked: false }, (o.walls || {})[l.name] || {});
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = o.cableUnit || 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    return app.project.layers.map(l => app.screenCircuits(l).map(c => c.num));
}"""

ROWS_JS = """() => {
    const app = window.app;
    const list = app.buildPullList();
    return list.positions.flatMap(p => p.rows)
        .filter(r => !/Jump|Breakout|Distro/.test(r.type))
        .map(r => [r.type, r.length, r.qty, r.label, r.notes]);
}"""


def _power_show(pg, unit='ft'):
    _reset(pg, [_screen('W', 6, 3, 200, 200, panelWatts=600)], unit=unit)


def test_a_multi_home_run_typed_with_the_shows_unit_prints_its_length(page):
    """'100ft' / "100'" in a feet show and '30m' / '30 m' in a meters show
    are the lengths they say, on the pull sheet, the canvas bracket and in
    the typed count; '30m' in a feet show is no length, flagged."""
    pg, errors = page
    _power_show(pg)
    for typed, unit, length, note, counted in (
            ('100ft', 'ft', "100'", '', 1), ("100'", 'ft', "100'", '', 1),
            ('100 ft', 'ft', "100'", '', 1), ('30m', 'ft', '', 'no length', 0),
            ('30m', 'm', '30 m', '', 1), ('30 m', 'm', '30 m', '', 1),
            ('100ft', 'm', '', 'no length', 0)):
        pg.evaluate(SETUP_JS, {'distros': [DIST_US], 'cableUnit': unit,
                               'walls': {'W': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1},
                                               'powerSocaLengths': {'1': typed}}}})
        rows = pg.evaluate(ROWS_JS)
        multi = [r for r in rows if r[0] == 'Multi']
        assert multi == [['Multi', length, 1, 'SL 1', note]], (typed, unit, rows)
        out = ev(pg, """const W = app.project.layers[0];
            const s = app.getSocaPlan(W)[0];
            return { count: app.typedCableLengthCount(),
                     bracket: s.length == null ? '' : window.canvasRenderer._homeRunText(s.length) };""")
        assert out['count'] == counted, (typed, unit, out)
        assert out['bracket'] == length, (typed, unit, out)
    assert errors == [], errors


def test_typing_a_home_run_with_the_unit_stores_the_number(page):
    """setSocaLength keeps the number of a length typed with the show's
    unit, so a later unit change relabels it by number like any other."""
    pg, _ = page
    _power_show(pg)
    pg.evaluate(SETUP_JS, {'distros': [DIST_US],
                           'walls': {'W': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}}})
    out = ev(pg, """const W = app.project.layers[0];
        app.setSocaLength(W, 1, '125 ft', false);
        const a = W.powerSocaLengths[1];
        app.setSocaLength(W, 1, '30m', false);
        const b = W.powerSocaLengths[1];
        return [a, b];""")
    # the other unit's suffix is kept as typed - it reads as no length
    assert out == ['125', '30m'], out


def test_a_direct_output_reads_the_same_lengths(page):
    """directOutputCable (the map's tag) and the dock chip read a typed
    length the way the pull sheet does: '25ft' is 25' in a feet show,
    '30m' there is no length - not 30'."""
    pg, _ = page
    _power_show(pg)
    for typed, want, row in (('25ft', "25' True1", ['Tru-1', "25'", 1, 'SL 5', '']),
                             ('30m', None, ['Tru-1', '', 1, 'SL 5', 'no length'])):
        nums = pg.evaluate(SETUP_JS, {'distros': [DIST_US], 'walls': {'W': {
            'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
            'powerSocaLengths': {'1': typed}}}})
        out = ev(pg, """const W = app.project.layers[0];
            const c = app.directOutputCable(W, arg);
            return c && c.text;""", nums[0][0])
        assert out == want, (typed, out)
        rows = pg.evaluate(ROWS_JS)
        assert row in rows, (typed, rows)


def test_the_jumper_fields_take_the_shows_unit(page):
    """'2 m' in a meters show is 2; '2m' in a feet show is refused and the
    field flagged, the stored length untouched."""
    pg, errors = page
    _reset(pg, [_screen('J', 2, 2, dataJumpV=1)], unit='m')
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function("() => document.getElementById('data-jump-v').offsetParent !== null")
    pg.fill('#data-jump-v', '2 m')
    pg.locator('#data-jump-v').dispatch_event('change')
    pg.wait_for_function("() => window.app.currentLayer.dataJumpV === 2")
    ev(pg, "app.project.cableUnit = 'ft'; return null;")
    pg.fill('#data-jump-v', '3m')
    pg.locator('#data-jump-v').dispatch_event('change')
    out = ev(pg, """return [app.currentLayer.dataJumpV,
        document.getElementById('data-jump-v').classList.contains('invalid')];""")
    assert out == [2, True], out
    pg.locator('[data-mode="pixel-map"]').click()
    assert errors == [], errors


# ── #11: a direct output's cable is printed once ─────────────────────────

def test_a_direct_output_with_its_own_circuit_cable_prints_one_cable(page):
    """The map tags a direct output's circuit with the circuit's own cable
    when it has one, else the output's home run (canvas-power.js). The pull
    sheet prints that one cable - not both, and no "no length" row beside
    a circuit cable that has one."""
    pg, errors = page
    _power_show(pg)
    for lengths, cable, want in (
            ({'1': '25'}, {'ft': 10, 'connector': None}, [['Tru-1', "10'", 1, 'SL 5', '']]),
            ({}, {'ft': 10, 'connector': None}, [['Tru-1', "10'", 1, 'SL 5', '']]),
            ({'1': '25'}, None, [['Tru-1', "25'", 1, 'SL 5', '']]),
            ({}, None, [['Tru-1', '', 1, 'SL 5', 'no length']])):
        nums = pg.evaluate(SETUP_JS, {'distros': [DIST_US], 'walls': {'W': {
            'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 5},
            'powerSocaLengths': lengths}}})
        circuit = nums[0][0]
        out = ev(pg, """const W = app.project.layers[0];
            if (arg.cable) W.powerCircuitCables = { [arg.circuit]: arg.cable };
            const own = app.powerCircuitCable(W, arg.circuit);
            const direct = app.directOutputCable(W, arg.circuit);
            return { tag: (own && own.text) || (direct && direct.text) || null };""",
                 {'circuit': circuit, 'cable': cable})
        every = pg.evaluate(ROWS_JS)
        rows = [r for r in every if r[0] == 'Tru-1']
        assert rows == want, (lengths, cable, every, out)
        if want[0][1]:
            assert out['tag'] == f"{want[0][1]} True1", out
    assert errors == [], errors


# ── #14: undo waits for the pull sheet's POST queue ──────────────────────

# The page's fetch, with the first POST that carries the show's cable unit
# held until the test lets it go: the POST is in flight (the queue is busy)
# but has not reached the server.
HOLD_UNIT_POST_JS = """() => {
    const orig = window.__lrdFetch || (window.__lrdFetch = window.fetch);
    window.__unitPostRelease = null;
    let holding = true;
    window.fetch = (url, opts) => {
        const body = opts && typeof opts.body === 'string' ? opts.body : '';
        if (holding && opts && opts.method === 'POST' && /\\/api\\/project$/.test(String(url))
                && body.includes('"cableUnit"')) {
            holding = false;
            return new Promise((resolve, reject) => {
                window.__unitPostRelease = () => orig(url, opts).then(resolve, reject);
            });
        }
        return orig(url, opts);
    };
}"""


def test_undo_waits_for_a_cable_unit_post_still_in_flight(page):
    """The unit change's POST is held in flight; undo is pressed while it
    waits. The restore PUT must go after it, so the server ends on the
    undone (feet) show, not the meters POST landing late."""
    pg, errors = page
    _reset(pg, [_screen('U', 2, 2)])
    pg.evaluate(HOLD_UNIT_POST_JS)
    try:
        assert ev(pg, "return app.setCableUnit('m', false);") is True
        pg.wait_for_function("() => typeof window.__unitPostRelease === 'function'")
        ev(pg, "app.undo(); return null;")
        assert ev(pg, "return app.cableUnit();") == 'ft'
        # the restore is waiting on the held POST, not on the server
        assert ev(pg, "return app._restorePutPending || 0;") == 1
        pg.evaluate("() => window.__unitPostRelease()")
        pg.wait_for_function("() => !window.app._restorePutPending")
        pg.evaluate("() => window.app._layerSavesSettled()")
    finally:
        pg.evaluate("() => { if (window.__lrdFetch) window.fetch = window.__lrdFetch; }")
    served = ev(pg, "return fetch('/api/project').then(r => r.json()).then(p => p.cableUnit || 'ft');")
    assert served == 'ft', served
    assert errors == [], errors


# ── #15: figures in en-US whatever the locale ────────────────────────────

def test_run_load_readouts_print_en_us_figures_in_a_german_browser(e2e_server, pw_browser):
    context = pw_browser.new_context(locale='de-DE')
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => window.app && typeof window.app._formatRunLoadPair === 'function'")
        out = pg.evaluate("""() => ({
            local: (589824).toLocaleString(),
            data: window.app._formatRunLoadPair('data', 589824, 659722),
            power: window.app._formatRunLoadPair('power', 1660, 4160),
        })""")
    finally:
        context.close()
    assert out['local'] == '589.824', 'the context is not German - the test proves nothing'
    assert out['data'] == '589,824 / 659,722 px', out
    assert out['power'] == '1,660 / 4,160 W', out



def test_no_figure_is_printed_in_the_browsers_locale():
    """Every number the page formats says which format it wants: a bare
    toLocaleString() prints "589.824" in a German browser."""
    import re
    js_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')
    bare = []
    for name in sorted(os.listdir(js_dir)):
        if not name.endswith('.js'):
            continue
        with open(os.path.join(js_dir, name), encoding='utf-8') as fh:
            for i, line in enumerate(fh, 1):
                if re.search(r'\.toLocaleString\(\s*\)', line):
                    bare.append(f'{name}:{i}')
    assert bare == [], bare
