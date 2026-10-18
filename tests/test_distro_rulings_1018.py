"""Four distro rulings (owner, 2026-10-18).

1. Blank cabinets draw no power - "they don't exist". The auto circuit
   packer and the canvas Power label leave them out (both the `blank` flag
   and `hidden`), so circuits, distro loads and labels match the totals.
2. Connector rating defaults with a per-row override: classic powerCON on
   an EU distro is 16 A like True1; a direct row's small "A" field
   overrides its connector's rating (blank is the default), the connector
   check reads it, and it is saved with the show and in presets.
3. A distro TYPE: a text field behind the gear, filled by a preset with the
   preset's name, saved, undoable and carried in presets. The pull sheet
   prints it - "Distro" where there is none - and never "<N> way".
4. A multi never lands on a one-circuit output. A row edit, a preset, a
   row removed: a dialog names the screen and the output and offers "Take
   it off and apply" or "Cancel"; a locked screen gets Cancel only. A pin
   or a carried pin onto one is refused. A show already in that state
   keeps its flag, opens unchanged, and says the output's load against its
   breaker and connector rating - "PD4 True1 at 57.7 A of 20 A - over
   capacity".

The figures, by hand:
  * WALL A, 10 x 6 cabinets at 200 W, 208V, 10 A circuits: a row of ten is
    2000 W / 208 V = 9.615 A, one circuit; six rows, six circuits.
    Five cabinets of row 1 blank: 55 x 200 = 11000 W. The first circuits
    take whole rows of what is left: 5 + 10 + 10 + ... - row 1's five live
    cabinets (1000 W, 4.81 A), then rows 2-6 (2000 W each).
  * Over capacity: WALL A's six circuits on one True1 = 6 x 9.615 =
    57.7 A against min(20 A breaker, 20 A True1) = 20 A; with the row's
    connector rated 15 A, against 15 A.
  * EU powerCON: 3600 W / 230 V = 15.65 A on a powerCON 20A is under 16 A;
    3800 W = 16.52 A is over it.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_rulings_1018.py -q --browser chromium
"""

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _open(pw_browser, url):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1200)
    return context, pg, errors


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg, errors = _open(pw_browser, e2e_server)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    yield pg, errors
    context.close()


SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 10, rows: 6,
                              cabinet_width: 200, cabinet_height: 200})});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL B', columns: 6, rows: 3,
                              cabinet_width: 200, cabinet_height: 200, offset_x: 2600})});
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    return p.layers.length;
}"""

SETUP_JS = """(o) => {
    const app = window.app;
    document.getElementById('crowd-modal')?.remove();
    for (const l of app.project.layers) {
        const key = l.name === 'WALL A' ? 'a' : 'b';
        Object.assign(l, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerCircuitCables: {}, powerLabelOverrides: {},
                           powerBreakoutType: null, locked: false },
                      (o.walls || {})[key] || {});
        (l.panels || []).forEach(p => { p.blank = false; p.hidden = false; });
        app.normalizePowerBreakout(l);
    }
    app.project.distros = (o.distros || []).map(d => JSON.parse(JSON.stringify(d)));
    app.project.cableUnit = 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    return app.project.layers.map(l => app.screenCircuits(l).length);
}"""

A = "window.app.project.layers.find(l => l.name === 'WALL A')"
B = "window.app.project.layers.find(l => l.name === 'WALL B')"


def setup(pg, **o):
    pg.wait_for_function("() => window.app._layerSavesSettled()")
    pg.wait_for_timeout(200)
    return pg.evaluate(SETUP_JS, o)


def ev(pg, body, arg=None):
    return pg.evaluate(
        f"(arg) => {{ const app = window.app; const A = {A}; const B = {B}; {body} }}", arg)


@pytest.fixture(scope="module")
def seeded(page):
    pg, errors = page
    assert pg.evaluate(SEED_JS) == 2
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    return pg, errors


# ── 1. blank cabinets draw no power ───────────────────────────────────────

LABEL_JS = """(layerName) => {
    const r = window.canvasRenderer, app = window.app;
    const l = app.project.layers.find(x => x.name === layerName);
    const keep = { view: r.viewMode, info: l.showPowerCircuitInfo };
    r.viewMode = 'power';
    l.showPowerCircuitInfo = true;
    const ctx = r.ctx, orig = ctx.fillText, texts = [];
    ctx.fillText = function (t, ...rest) { texts.push(String(t)); return orig.call(this, t, ...rest); };
    try { r.renderLayerLabels(l); }
    finally { ctx.fillText = orig; r.viewMode = keep.view; l.showPowerCircuitInfo = keep.info; }
    return texts.join(' ');
}"""


def test_blank_cabinets_draw_no_power_in_the_circuits_loads_and_label(seeded):
    pg, errors = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'PD', 'ratingA': 400, 'system': '120/208'}],
          walls={'a': {'powerSocaDistro': {'1': 'd1'}}})
    before = ev(pg, """
        app._circuitTailCache = null;
        return { circuits: app.screenCircuits(A).length,
                 watts: app.getDistroLoads()[0].watts,
                 carried: app.getCarriedPowerLoad(A).watts };""")
    # by hand: 60 x 200 W = 12000 W on six circuits
    assert before == {'circuits': 6, 'watts': 12000, 'carried': 12000}, before
    out = ev(pg, """
        // row 1's last five cabinets go blank
        A.panels.filter(p => p.row === 0 && p.col >= 5).forEach(p => { p.blank = true; });
        app._circuitTailCache = null;
        const circuits = app.screenCircuits(A);
        const plan = app.getSocaPlan(A);
        const counts = app.getPowerCounts ? app.getPowerCounts(A) : null;
        return {
            circuits: circuits.length,
            anyBlank: circuits.some(c => (c.panels || []).some(p => p.blank)),
            sizes: circuits.map(c => c.panels.length),
            legAmps: plan[0].legs.map(g => +g.amps.toFixed(3)),
            watts: app.getDistroLoads()[0].watts,
            carried: app.getCarriedPowerLoad(A).watts,
        };""")
    assert not out['anyBlank'], 'no circuit carries a blank cabinet'
    # by hand: 55 live cabinets x 200 W = 11000 W; still six circuits
    # (row 1's five live cabinets, then rows 2-6), each circuit at its own
    # cabinets' watts / 208 V
    assert out['watts'] == 11000 and out['carried'] == 11000, out
    assert out['circuits'] == 6 and out['sizes'] == [5, 10, 10, 10, 10, 10], out
    assert out['legAmps'] == [round(1000 / 208, 3)] + [round(2000 / 208, 3)] * 5, out
    label = pg.evaluate(LABEL_JS, 'WALL A')
    # the label's 1φ figure is the 11000 W, not 12000 W: 11000 / 208
    assert '6 Circuits' in label and f'{11000 / 208:.2f}A 1φ' in label, label
    assert f'{12000 / 208:.2f}A' not in label, label
    # hidden cabinets, as ever, draw nothing either
    out = ev(pg, """
        A.panels.filter(p => p.row === 0 && p.col >= 5).forEach(p => { p.blank = false; p.hidden = true; });
        app._circuitTailCache = null;
        return app.getDistroLoads()[0].watts;""")
    assert out == 11000
    assert not errors, errors


# ── 2. connector ratings and the per-row override ─────────────────────────

def test_eu_powercon_defaults_to_16a_and_a_row_overrides_it(seeded):
    pg, _ = seeded
    eu = {'id': 'd1', 'name': 'UK', 'ratingA': 63, 'system': '230/400',
          'outputRows': [{'id': 'r1', 'connector': 'powercon20', 'count': 3, 'coupling': 'ln',
                          'breakerA': 32}]}
    rating = ev(pg, """
        const pc = app.distroConnector('powercon20'), t1 = app.distroConnector('true1');
        return [app.connectorRatingA(pc, 'eu'), app.connectorRatingA(pc, 'us'),
                app.connectorRatingA(t1, 'eu')];""")
    assert rating == [16, 20, 16]
    # WALL B's first circuit cut off on its own, pinned to output 1
    walls = {'b': {'powerVoltage': 230, 'powerAmperage': 20, 'panelWatts': 600,
                   'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'},
                   'powerSocaNumber': {'1': 1}}}
    check = """
        app._circuitTailCache = null; app._distroFaceMemo = null;
        const s = app.getSocaPlan(B)[0];
        return { legs: s.legs.length, amps: +s.legs[0].amps.toFixed(2),
                 warn: app.distroChecks(app.getDistros()[0]).map(w => w.text) };"""
    # 6 x 600 W = 3600 W / 230 V = 15.65 A: under 16 A
    setup(pg, distros=[eu], walls=walls)
    out = ev(pg, check)
    assert out['legs'] == 1 and out['amps'] == pytest.approx(3600 / 230, abs=0.01), out
    assert not [w for w in out['warn'] if 'rated' in w], out
    # 3800 W / 230 V = 16.52 A: over a powerCON's 16 A here
    setup(pg, distros=[eu], walls={'b': dict(walls['b'], panelWatts=3800 / 6)})
    out = ev(pg, check)
    assert [w for w in out['warn'] if 'a powerCON 20A is rated 16 A here' in w], out
    # the row's override, 20 A: the check reads it
    rows = [dict(eu['outputRows'][0], connectorA=20)]
    setup(pg, distros=[dict(eu, outputRows=rows)], walls={'b': dict(walls['b'], panelWatts=3800 / 6)})
    out = ev(pg, check)
    assert not [w for w in out['warn'] if 'rated' in w], out
    # and 15 A: 15.65 A is over it
    rows = [dict(eu['outputRows'][0], connectorA=15)]
    setup(pg, distros=[dict(eu, outputRows=rows)], walls=walls)
    out = ev(pg, check)
    assert [w for w in out['warn'] if 'a powerCON 20A is rated 15 A here' in w], out


def test_the_override_field_saves_blank_is_the_default_and_presets_carry_it(seeded):
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
                        'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 3,
                                        'coupling': 'll', 'breakerA': 20},
                                       {'id': 'r2', 'connector': 'soca', 'count': 2,
                                        'coupling': 'll', 'breakerA': 20}]}])
    out = ev(pg, """
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
        const f = document.querySelector('[data-lrd-field="distro-row-connector-a-d1-r1"]');
        const multi = document.querySelector('[data-lrd-field="distro-row-connector-a-d1-r2"]');
        const r = { placeholder: f.placeholder, value: f.value, multi: !!multi, tip: f.title };
        f.value = '15'; f.dispatchEvent(new Event('change'));
        r.after = app.getDistros()[0].outputRows[0].connectorA;
        r.action = app.history[app.historyIndex].action;
        const f2 = document.querySelector('[data-lrd-field="distro-row-connector-a-d1-r1"]');
        r.shown = f2 ? f2.value : null;
        f2.value = ''; f2.dispatchEvent(new Event('change'));
        r.cleared = app.getDistros()[0].outputRows[0].connectorA;
        app._hwPopoverClose();
        return r;""")
    assert out['placeholder'] == '20' and out['value'] == '', out
    assert not out['multi'], 'a multi row has no connector rating to override'
    assert 'Blank is the default, 20 A here' in out['tip']
    assert out['after'] == 15 and out['shown'] == '15' and out['action'] == 'Edit Distro', out
    assert out['cleared'] is None, out
    saved = pg.evaluate("""async () => {
        const app = window.app;
        const rows = app.getDistros()[0].outputRows.map(r => ({ ...r }));
        rows[0].connectorA = 15;
        app.updateDistro('d1', { outputRows: rows });
        await app._distroPushQueue;
        const served = (await (await fetch('/api/project')).json()).distros[0].outputRows[0].connectorA;
        await app.saveDistroPreset('d1', 'Override test rack');
        const listed = await app.loadCustomDistroPresets(true);
        const p = listed.find(x => x.name === 'Override test rack');
        await app.deleteDistroPreset('Override test rack');
        return { served, preset: p.distro.rows[0].connectorA, other: p.distro.rows[1].connectorA };
    }""")
    assert saved == {'served': 15, 'preset': 15, 'other': None}, saved


def test_the_presets_route_checks_the_override_and_the_type(client):
    body = {'typeName': 'Rack 24ch', 'system': '120/208', 'input': 'cam200', 'ratingA': 200,
            'rows': [{'id': 'r1', 'connector': 'true1', 'count': 3, 'coupling': 'll',
                      'breakerA': 20, 'connectorA': 15, 'pairedWith': None}]}
    r = client.put('/api/distro-presets', json={'name': 'Route override test', 'distro': body})
    assert r.status_code == 200
    saved = [p for p in r.get_json()['presets'] if p['name'] == 'Route override test'][0]
    assert saved['distro']['typeName'] == 'Rack 24ch'
    assert saved['distro']['rows'][0]['connectorA'] == 15
    ok_null = dict(body, rows=[dict(body['rows'][0], connectorA=None)])
    assert client.put('/api/distro-presets', json={'name': 'Route override test',
                                                   'distro': ok_null}).status_code == 200
    for bad in ('15', 0, -3, 5000, True):
        b = dict(body, rows=[dict(body['rows'][0], connectorA=bad)])
        assert client.put('/api/distro-presets', json={'name': 'Route override test',
                                                       'distro': b}).status_code == 400, bad
    for bad in (5, 'x' * 61, ['a']):
        assert client.put('/api/distro-presets', json={'name': 'Route override test',
                                                       'distro': dict(body, typeName=bad)}
                          ).status_code == 400, bad
    client.delete('/api/distro-presets', json={'name': 'Route override test'})


# ── 3. the distro's Type ──────────────────────────────────────────────────

FED = {'a': {'powerSocaDistro': {'1': 'd1'}}}


def test_the_type_field_saves_undoes_and_names_the_pull_row(seeded):
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208'}], walls=FED)
    pull = """
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const hw = list.hardware.find(h => h.kind === 'distro');
        const all = JSON.stringify(list);
        return { row: hw.rows.find(r => r.label === 'PD' && r.length === 'EA'),
                 way: all.match(/\\d+ way/g) };"""
    out = ev(pg, pull)
    assert out['row']['type'] == 'Distro' and out['way'] is None, out
    pg.evaluate("() => { window.app.saveState('Setup'); }")
    out = ev(pg, """
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
        const f = document.querySelector('[data-lrd-field="distro-type-d1"]');
        const r = { placeholder: f.placeholder, value: f.value };
        f.value = '  200A 24ch rack '; f.dispatchEvent(new Event('change'));
        r.stored = app.getDistros()[0].typeName;
        r.action = app.history[app.historyIndex].action;
        app._hwPopoverClose();
        return r;""")
    assert out == {'placeholder': 'Distro', 'value': '', 'stored': '200A 24ch rack',
                   'action': 'Edit Distro'}, out
    assert ev(pg, pull)['row']['type'] == '200A 24ch rack'
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(500)
    assert ev(pg, "return 'typeName' in app.getDistros()[0];") is False
    assert ev(pg, pull)['row']['type'] == 'Distro'
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(500)
    assert ev(pg, pull)['row']['type'] == '200A 24ch rack'
    # blank forgets it
    ev(pg, "app.updateDistro('d1', { typeName: '   ' }); return null;")
    assert ev(pg, "return 'typeName' in app.getDistros()[0];") is False


def test_a_preset_fills_the_type_and_presets_carry_it(seeded):
    pg, _ = seeded
    setup(pg, distros=[{'id': 'd1', 'name': 'P', 'ratingA': 400, 'system': '120/208'},
                       {'id': 'd2', 'name': 'Q', 'ratingA': 400, 'system': '120/208'}])
    out = pg.evaluate("""async () => {
        const app = window.app;
        const p = app.builtInDistroPresets().find(x => x.id === 'us-400-8soca120-8soca208');
        app.applyDistroPreset('d1', p);
        const filled = app.getDistros()[0].typeName;
        app.updateDistro('d1', { typeName: 'Our 400A rack' });
        await app.saveDistroPreset('d1', 'Type test preset');
        const listed = await app.loadCustomDistroPresets(true);
        const saved = listed.find(x => x.name === 'Type test preset');
        app.applyDistroPreset('d2', saved);
        const carried = app.getDistros()[1].typeName;
        // a saved preset with no Type of its own gives its name
        const bare = JSON.parse(JSON.stringify(saved)); delete bare.distro.typeName;
        app.applyDistroPreset('d2', bare);
        const byName = app.getDistros()[1].typeName;
        await app.deleteDistroPreset('Type test preset');
        return { filled, presetName: p.name, body: saved.distro.typeName, carried, byName };
    }""")
    assert out['filled'] == out['presetName'] == '400A 3φ: 8 × Socapex 120V + 8 × Socapex 208V'
    assert out['body'] == 'Our 400A rack' and out['carried'] == 'Our 400A rack'
    assert out['byName'] == 'Type test preset'


OLD_SHOW = {
    'id': 'd1', 'name': 'OLD', 'ratingA': 200, 'system': '120/208', 'voltage': 208, 'phase': 3,
    'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 3, 'coupling': 'll',
                    'breakerA': 20, 'pairedWith': None},
                   {'id': 'r2', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                    'breakerA': 20, 'pairedWith': None}],
}


def test_an_old_crowded_show_prints_distro_and_opens_unchanged(e2e_server, pw_browser, seeded):
    """No Type, a six-circuit multi already on a True1 (output 2), no
    connectorA on its rows: it prints "Distro", keeps its flag, says its
    over capacity, and opening it writes nothing."""
    pg, _ = seeded
    pg.evaluate("""async (d) => {
        const proj = await (await fetch('/api/project')).json();
        const a = proj.layers.find(l => l.name === 'WALL A');
        Object.assign(a, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                           powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 2 },
                           powerSocaPhasePos: {}, powerSocaSplits: [], powerSocaLengths: { 1: '50' },
                           locked: false });
        (a.panels || []).forEach(p => { p.blank = false; p.hidden = false; });
        const b = proj.layers.find(l => l.name === 'WALL B');
        Object.assign(b, { powerSocaDistro: {}, powerSocaNumber: {}, powerSocaSplits: [] });
        proj.distros = [d];
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(proj)});
    }""", OLD_SHOW)
    pg.wait_for_timeout(400)
    before = pg.evaluate("async () => (await (await fetch('/api/project')).json())")
    assert before['distros'] == [OLD_SHOW]
    context, pg2, errors = _open(pw_browser, e2e_server)
    try:
        writes = []
        pg2.on('request', lambda r: writes.append(r.url) if (
            r.method in ('POST', 'PUT') and '/api/project' in r.url) else None)
        pg2.locator('[data-mode="power"]').click()
        pg2.wait_for_timeout(400)
        out = pg2.evaluate("""() => {
            const app = window.app;
            app.renderHardwareDock();
            const d = app.getDistros()[0];
            const caught = [];
            const orig = app._bKvLines;
            app._bKvLines = function (book, title, pairs) {
                if (title === 'Service') caught.push(pairs.map(p => p.slice()));
                return orig.apply(this, arguments);
            };
            try {
                app.planBinder(Object.assign(app.readBinderOptions(),
                    { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
            } finally { app._bKvLines = orig; }
            const hw = app.buildPullList().hardware.find(h => h.kind === 'distro');
            return {
                checks: app.distroChecks(d).map(w => w.text),
                strip: (app._dockPowerWarnings || []).map(w => w.text),
                binder: (caught[0] || []).filter(([k]) => k === 'Over capacity'),
                pull: hw.rows.find(r => r.length === 'EA' && r.label === 'OLD').type,
            };
        }""")
        pg2.wait_for_timeout(800)
        move = ("WALL A's 6 circuits are on OLD2, a True1 — one circuit only. "
                'Move it to a multi output.')
        cap = 'OLD2 True1 at 57.7 A of 20 A — over capacity'
        assert move in out['checks'] and cap in out['checks'], out['checks']
        assert move in out['strip'] and cap in out['strip'], out['strip']
        assert out['binder'] == [['Over capacity', cap + ' · a multi on a one-circuit output, '
                                  'move it to a multi output']], out['binder']
        assert out['pull'] == 'Distro'
        after = pg2.evaluate("async () => (await (await fetch('/api/project')).json())")
        assert after['distros'] == [OLD_SHOW], after['distros']
        a_before = next(l for l in before['layers'] if l['name'] == 'WALL A')
        a_after = next(l for l in after['layers'] if l['name'] == 'WALL A')
        assert a_after['powerSocaNumber'] == a_before['powerSocaNumber']
        assert not [w for w in writes if w.endswith('/api/project')], writes
        assert not errors, errors
    finally:
        context.close()


# ── 4. a multi never lands on a one-circuit output ────────────────────────

FACE = {'id': 'd1', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
        'outputRows': [{'id': 'r1', 'connector': 'true1', 'count': 3, 'coupling': 'll',
                        'breakerA': 20},
                       {'id': 'r2', 'connector': 'soca', 'count': 2, 'coupling': 'll',
                        'breakerA': 20}]}
# WALL A's six-circuit multi pinned on output 4 (the first Socapex), its
# home run typed; WALL B's first circuit alone on output 5 (the second).
WALLS = {'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 4},
               'powerSocaLengths': {'1': '75'}},
         'b': {'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1'},
               'powerSocaNumber': {'1': 5}}}

MODAL_JS = """() => {
    const m = document.getElementById('crowd-modal');
    if (!m) return null;
    return { text: m.querySelector('.modal-content').innerText,
             buttons: [...m.querySelectorAll('button')].map(b => b.textContent),
             cap: (m.querySelector('.crowd-cap') || {}).textContent || null,
             locked: (m.querySelector('.crowd-locked') || {}).textContent || null };
}"""

RAISE_TRUE1 = """
    const rows = app.getDistros()[0].outputRows.map(r => ({ ...r }));
    rows[0].count = 4;
    return app.updateDistro('d1', { outputRows: rows });"""


def _state(pg):
    return ev(pg, """
        const d = app.getDistros()[0];
        return { rows: app.distroRows(d).map(r => [r.connector, r.count]),
                 pinA: (A.powerSocaNumber || {})[1] ?? null,
                 lenA: (A.powerSocaLengths || {})[1] ?? null,
                 distroA: (A.powerSocaDistro || {})[1] ?? null,
                 pinB: (B.powerSocaNumber || {})[1] ?? null,
                 crowded: app._faceCrowding(d).map(c => c.number),
                 index: app.historyIndex, action: app.history[app.historyIndex].action };""")


def test_a_row_edit_that_would_crowd_asks_and_cancel_changes_nothing(seeded):
    pg, errors = seeded
    setup(pg, distros=[FACE], walls=WALLS)
    pg.evaluate("() => window.app.saveState('Setup')")
    before = _state(pg)
    assert before['rows'] == [['true1', 3], ['soca', 2]] and before['crowded'] == []
    # True1 x3 -> x4: output 4 becomes a True1 under WALL A's six circuits
    assert ev(pg, RAISE_TRUE1) is None, 'nothing applied while it asks'
    modal = pg.evaluate(MODAL_JS)
    assert modal, 'the dialog opened'
    assert ("WALL A's 6-circuit multi is on PD4. PD4 would become a True1, "
            "which carries one circuit.") in modal['text'], modal['text']
    # the load it would put there, said while it asks: 6 x 9.615 = 57.7 A
    assert modal['cap'] == 'PD4 True1 at 57.7 A of 20 A — over capacity', modal
    assert modal['buttons'] == ['Cancel the change',
                                "Take WALL A's 6-circuit multi off PD4 and apply the change"]
    assert _state(pg) == before, 'nothing changes while it asks'
    pg.locator('#crowd-modal .crowd-cancel').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(MODAL_JS) is None
    assert _state(pg) == before, 'cancel leaves everything as it was'
    assert not errors, errors


def test_take_it_off_unpins_forgets_its_lengths_applies_and_undoes_as_one(seeded):
    pg, _ = seeded
    setup(pg, distros=[FACE], walls=WALLS)
    pg.evaluate("() => window.app.saveState('Setup')")
    before = _state(pg)
    ev(pg, RAISE_TRUE1)
    pg.locator('#crowd-modal .crowd-take').click()
    pg.wait_for_timeout(400)
    after = _state(pg)
    assert after['rows'] == [['true1', 4], ['soca', 2]], after
    assert after['pinA'] is None and after['lenA'] is None, 'unpinned, its home run forgotten'
    assert after['distroA'] == 'd1', 'still on the distro, as an auto'
    assert after['pinB'] == 5, "WALL B's multi is not touched"
    assert after['crowded'] == []
    assert after['index'] == before['index'] + 1 and after['action'] == 'Edit Distro'
    # the auto lands on the first free multi output: output 6 (Socapex)
    num = ev(pg, "app._circuitTailCache = null; return app.getSocaPlan(A)[0].number;")
    assert num == 6, num
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(500)
    back = _state(pg)
    assert (back['rows'], back['pinA'], back['lenA']) == (before['rows'], 4, '75'), back


def test_a_locked_screen_offers_cancel_only(seeded):
    pg, _ = seeded
    setup(pg, distros=[FACE], walls={'a': dict(WALLS['a'], locked=True), 'b': WALLS['b']})
    before = _state(pg)
    ev(pg, RAISE_TRUE1)
    modal = pg.evaluate(MODAL_JS)
    assert modal['buttons'] == ['Cancel the change'], modal
    assert 'WALL A is locked' in modal['locked'], modal
    pg.locator('#crowd-modal .crowd-cancel').click()
    pg.wait_for_timeout(200)
    assert _state(pg) == before


def test_a_connector_change_a_preset_and_a_removed_row_all_ask(seeded):
    pg, _ = seeded
    cases = {
        'connector': """const rows = app.getDistros()[0].outputRows.map(r => ({ ...r }));
                        rows[1].connector = 'true1';
                        return app.updateDistro('d1', { outputRows: rows });""",
        # a saved preset of six True1s: output 4 is a True1
        'preset': """const six = { name: 'Six True1', distro: { system: '120/208', ratingA: 200,
                        rows: [{ id: 'r1', connector: 'true1', count: 6, coupling: 'll', breakerA: 20 }] } };
                     return app.applyDistroPreset('d1', six);""",
    }
    for name in ('connector', 'preset'):
        setup(pg, distros=[FACE], walls=WALLS)
        before = _state(pg)
        assert ev(pg, cases[name]) is None, name
        modal = pg.evaluate(MODAL_JS)
        assert modal and 'would become a True1' in modal['text'], (name, modal)
        pg.locator('#crowd-modal .crowd-cancel').click()
        pg.wait_for_timeout(200)
        assert _state(pg) == before, name
    # removing a row: Socapex x2 + True1 x3 (WALL A's multi on output 1, a
    # Socapex); remove the Socapex row and output 1 is a True1
    setup(pg, distros=[dict(FACE, outputRows=[FACE['outputRows'][1], FACE['outputRows'][0]])],
          walls={'a': dict(WALLS['a'], powerSocaNumber={'1': 1})})
    pg.evaluate("() => window.app.renderHardwareDock()")
    pg.locator('[data-hwpop="distro-d1"]').click()
    pg.wait_for_timeout(200)
    pg.locator('[data-lrd-field="distro-row-del-d1-r2"]').click()
    pg.wait_for_timeout(200)
    modal = pg.evaluate(MODAL_JS)
    assert modal and "WALL A's 6-circuit multi is on PD1. PD1 would become a True1" in modal['text'], modal
    pg.locator('#crowd-modal .crowd-cancel').click()
    pg.wait_for_timeout(300)
    assert ev(pg, "return app.distroRows(app.getDistros()[0]).length;") == 2
    pg.evaluate("() => window.app._hwPopoverClose()")


def test_a_pin_onto_a_direct_output_is_refused(seeded):
    pg, _ = seeded
    setup(pg, distros=[FACE], walls=WALLS)
    out = ev(pg, """
        const n = app.historyIndex;
        const touched = app.setSocaNumber(A, 1, 2);
        const status = document.getElementById('status-message').textContent;
        return { touched: touched.length, pin: A.powerSocaNumber[1], same: app.historyIndex === n,
                 status };""")
    assert out['touched'] == 0 and out['pin'] == 4 and out['same'], out
    assert out['status'] == ("WALL A's 6-circuit multi cannot go on PD 2 — a True1 carries "
                             'one circuit. Use a multi output.'), out
    # one circuit on True1 output 3 is fine; a second one-circuit multi
    # onto it is refused
    out = ev(pg, """
        B.powerSocaSplits = [1, 2];
        app._circuitTailCache = null;
        const plan = app.getSocaPlan(B);
        B.powerSocaDistro[plan[1].soca] = 'd1';
        B.powerSocaDistro[plan[2].soca] = 'd1';
        app._circuitTailCache = null;
        const first = app.setSocaNumber(B, plan[1].soca, 3).length;
        const t = app.setSocaNumber(B, plan[2].soca, 3);
        return { first, touched: t.length, pin: B.powerSocaNumber[plan[2].soca] ?? null,
                 status: document.getElementById('status-message').textContent };""")
    assert out['first'] == 1 and out['touched'] == 0 and out['pin'] is None, out
    assert out['status'] == 'PD 3 already carries its one circuit — a True1 takes no more.', out
    # carried pin: a multi pinned to 2 on another distro, moved onto this one
    out = ev(pg, """
        app.project.distros.push({ id: 'd2', name: 'XX', ratingA: 200, system: '120/208' });
        app.getDistros();
        A.powerSocaDistro[1] = 'd2'; A.powerSocaNumber[1] = 2;
        app._circuitTailCache = null;
        const t = app.setSocaDistro(A, 1, 'd1');
        return { touched: t.length, distro: A.powerSocaDistro[1] };""")
    assert out == {'touched': 0, 'distro': 'd2'}, out


def test_the_override_counts_in_the_over_capacity_check(seeded):
    pg, _ = seeded
    rows = [dict(FACE['outputRows'][0], connectorA=15), FACE['outputRows'][1]]
    setup(pg, distros=[dict(FACE, outputRows=[dict(rows[0], count=4), rows[1]])],
          walls={'a': WALLS['a']})
    out = ev(pg, "return app.distroChecks(app.getDistros()[0]).map(w => w.text);")
    # 57.7 A against min(20 A breaker, 15 A override)
    assert 'PD4 True1 at 57.7 A of 15 A — over capacity' in out, out
