"""An older show keeps its circuits until a screen's power is edited
(owner, 2026-11-14).

The power rulings of 2026-11-12 change how circuits pack: the breaker of
the distro output a screen is plugged into wins over its Amperage, an
Edison breakout's outlet follows the Amperage (5-15 is 12 A, 5-20 is 16 A),
and a 240 V screen on no distro packs to 80%. The ruling: "old shows must
not repack on open". A show saved before them opens with every screen's
circuits as they were (same count, same cabinets, same names), and stays
that way through a save and a reopen and a page reload. A screen takes the
new rules at the next edit of ITS power (a plug, its Amperage, its panel
input, a row breaker it is on); a locked screen never changes.

The show is built here, shaped the way a 1.7.0 beta 5 file is (no
`powerRules` on it). Every wall is 10 x 6 cabinets, tl-h, not Organized:
  PLUGGED  110 V TRUE1, typed 15 A, 300 W, multi 1 on VX's 20 A Socapex
           (120 V, line to neutral) output 1.
             kept: 80% of 15 A = 12 A, 110 x 12 = 1,320 W, 4 cabinets a
                   circuit: 15 circuits of 4.
             new:  80% of the output's 20 A = 16 A, 1,760 W, 5 cabinets:
                   12 circuits of 5.
  EDISON30 110 V Edison breakout typed 30 A, 300 W, no distro.
             kept: 80% of 30 A = 24 A, 2,640 W, 8 cabinets: 7 of 8 + 4.
             new:  held to the 5-20's 16 A: 12 circuits of 5.
  V240     240 V, 20 A, 400 W, no distro.
             kept: the breaker (above 208 V on no distro), 4,800 W, 12
                   cabinets: 5 circuits of 12.
             new:  80%, 3,840 W, 9 cabinets: 6 of 9 + 6.
  LOCKED   PLUGGED's twin on output 2, locked.
  SAME     208 V TRUE1, 20 A, 400 W, no distro: 80% either way, 3,328 W,
           8 cabinets: 7 of 8 + 4. Nothing to keep, so no mark.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_power_old_shows_keep.py -n 4 --dist loadfile
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
    Object.defineProperty(window, '__lrdFetchesOut', { get: () => out, configurable: true });
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


def _ready(pg, url):
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    _settle(pg)
    pg.locator('[data-mode="power"]').click()
    _settle(pg)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    _ready(pg, e2e_server)
    yield pg, errors, e2e_server
    context.close()


VX = {'id': 'g1', 'name': 'VX', 'system': '120/208', 'voltage': 208, 'phase': 3,
      'input': 'cam400', 'ratingA': 400,
      'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 4, 'coupling': 'ln',
                      'breakerA': 20}]}

SCREENS = [
    {'name': 'PLUGGED', 'powerVoltage': 110, 'powerAmperage': 15, 'panelWatts': 300,
     'powerBreakoutType': 'soca-true1', 'powerSocaDistro': {'1': 'g1'}, 'powerSocaNumber': {'1': 1}},
    {'name': 'EDISON30', 'powerVoltage': 110, 'powerAmperage': 30, 'panelWatts': 300,
     'powerBreakoutType': 'soca-edison'},
    {'name': 'V240', 'powerVoltage': 240, 'powerAmperage': 20, 'panelWatts': 400},
    {'name': 'LOCKED', 'powerVoltage': 110, 'powerAmperage': 15, 'panelWatts': 300,
     'powerBreakoutType': 'soca-true1', 'powerSocaDistro': {'1': 'g1'}, 'powerSocaNumber': {'1': 2},
     'locked': True},
    {'name': 'SAME', 'powerVoltage': 208, 'powerAmperage': 20, 'panelWatts': 400,
     'powerBreakoutType': 'soca-true1'},
    # a 208 V L21-30 wall at 20 A on no distro (see the L21-30 test)
    {'name': 'L2130', 'powerVoltage': 208, 'powerAmperage': 20, 'panelWatts': 400,
     'powerBreakoutType': 'l2130-true1'},
    # a wall of two, grouped: 240 V on no distro like V240
    {'name': 'G1', 'powerVoltage': 240, 'powerAmperage': 20, 'panelWatts': 400, 'group': 'g7'},
    {'name': 'G2', 'powerVoltage': 240, 'powerAmperage': 20, 'panelWatts': 400, 'group': 'g7'},
]

KEPT = {
    'PLUGGED': [4] * 15,
    'EDISON30': [8] * 7 + [4],
    'V240': [12] * 5,
    'LOCKED': [4] * 15,
    'SAME': [8] * 7 + [4],
}

# The show file a build from before the rulings wrote: built on the
# server, shaped as above, without `powerRules`.
SHOW_JS = """async ({ screens, distro }) => {
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
    await window.app._layerSavesSettled();
    await fetch('/api/project/new', { method: 'POST' });
    const ids = [];
    for (let i = 0; i < screens.length; i++) {
        const made = await j('POST', '/api/layer/add', {
            name: screens[i].name, columns: 10, rows: 6, cabinet_width: 200, cabinet_height: 200,
            offset_x: i * 2200, offset_y: 0 });
        ids.push(made.id);
    }
    const p = await j('GET', '/api/project');
    p.layers = p.layers.filter(l => ids.includes(l.id));
    const groups = {};
    screens.forEach((s, i) => {
        const l = p.layers.find(x => x.id === ids[i]);
        const spec = Object.assign({}, s);
        delete spec.group;
        if (s.group) {
            l.group_id = s.group;
            (groups[s.group] = groups[s.group] || []).push(l.id);
        }
        Object.assign(l, {
            powerFlowPattern: 'tl-h', lastPowerFlowPattern: 'tl-h', powerCustomPath: false,
            powerOrganized: false, powerMaximize: false, powerCustomPaths: {},
            powerSocaDistro: {}, powerSocaNumber: {}, powerSocaSplits: [], powerSocaKeying: 'index',
            locked: false,
        }, spec);
    });
    p.groups = Object.keys(groups).map(id => ({ id, name: 'WALL ' + id, layer_ids: groups[id] }));
    p.next_group_seq = 8;
    p.distros = [distro];
    p.name = 'Older Power Show';
    p.app_version = '1.7.0-beta.5';
    delete p.powerRules;
    return p;
}"""


def show(pg):
    project = pg.evaluate(SHOW_JS, {'screens': SCREENS, 'distro': VX})
    _settle(pg)
    assert 'powerRules' not in project
    for l in project['layers']:
        assert 'powerOldRules' not in l, l['name']
    return project


def open_file(pg, project, name='older-power-show.json'):
    """File > Open with the show, the way the user does, through the load's
    PUT and its layer sync."""
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
    chooser.value.set_files({'name': name, 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_function("() => window.__loaded === true")
    _settle(pg)


# Each screen as the app lays it out: the cabinets of every circuit, their
# names, the mark, and the server's copy of the mark.
READ_JS = """async () => {
    const app = window.app;
    app._circuitTailCache = null;
    const server = await (await fetch('/api/project')).json();
    const out = { _rules: app.project.powerRules, _serverRules: server.powerRules };
    app.project.layers.filter(l => (l.type || 'screen') === 'screen').forEach(l => {
        const srv = server.layers.find(x => x.id === l.id) || {};
        const circuits = app.screenCircuits(l);
        out[l.name] = {
            n: circuits.map(c => c.panels.length),
            ids: circuits.map(c => c.panels.map(p => `${p.row}:${p.col}`).join(',')),
            names: circuits.map(c => app.getPowerCircuitLabel(l, c.num)),
            mark: !!(l.powerOldRules && l.powerOldRules.sig),
            serverMark: !!(srv.powerOldRules && srv.powerOldRules.sig),
            line: app.powerBreakerSourceText(l),
        };
    });
    return out;
}"""


def read(pg):
    return pg.evaluate(READ_JS)


def layout(got):
    return {k: {f: v[f] for f in ('n', 'ids', 'names')} for k, v in got.items()
            if not k.startswith('_')}


def select(pg, name):
    pg.evaluate("""(name) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === name);
        app.selectLayer(l);
        app.loadLayerToInputs && app.loadLayerToInputs();
        app.updatePowerCapacityDisplay();
    }""", name)


def test_an_older_show_opens_with_every_circuit_as_saved(page):
    pg, errors, _ = page
    open_file(pg, show(pg))
    got = read(pg)
    for name, n in KEPT.items():
        assert got[name]['n'] == n, (name, got[name]['n'])
    # the screens the rulings would move carry the mark, the server's copy
    # too; the one they would not, none
    for name in ('PLUGGED', 'EDISON30', 'V240', 'LOCKED'):
        assert got[name]['mark'] and got[name]['serverMark'], name
    assert not got['SAME']['mark'] and not got['SAME']['serverMark']
    # the project is this build's from here
    assert got['_rules'] == 2 and got['_serverRules'] == 2, got
    # the sidebar says the circuits are kept, and what an edit does
    assert got['PLUGGED']['line'] == ('Kept as the show was saved: 12 A a circuit. '
                                      "Any change to this screen's power packs them to 16 A.")
    assert got['EDISON30']['line'] == ('Kept as the show was saved: 24 A a circuit. '
                                       "Any change to this screen's power packs them to 16 A.")
    assert got['V240']['line'] == ('Kept as the show was saved: 20 A a circuit. '
                                   "Any change to this screen's power packs them to 16 A.")
    assert got['SAME']['line'] == ''
    select(pg, 'PLUGGED')
    shown = pg.evaluate("() => document.getElementById('power-amperage-source').textContent")
    assert shown == got['PLUGGED']['line']
    assert errors == [], errors


def test_save_reopen_and_reload_still_move_nothing(page):
    pg, errors, url = page
    open_file(pg, show(pg))
    first = read(pg)
    saved = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    assert saved['powerRules'] == 2
    by = {l['name']: l for l in saved['layers']}
    assert by['PLUGGED']['powerOldRules']['sig'], by['PLUGGED'].get('powerOldRules')
    # reopened from the file this build saved
    open_file(pg, saved, 'saved-again.json')
    again = read(pg)
    assert layout(again) == layout(first)
    assert all(again[n]['mark'] for n in ('PLUGGED', 'EDISON30', 'V240', 'LOCKED'))
    # and the page reloaded on the server's copy
    _ready(pg, url)
    reloaded = read(pg)
    assert layout(reloaded) == layout(first)
    assert all(reloaded[n]['mark'] for n in ('PLUGGED', 'EDISON30', 'V240', 'LOCKED'))
    assert errors == [], errors


def test_a_power_edit_lays_that_screen_out_by_the_new_rules(page):
    pg, errors, _ = page
    open_file(pg, show(pg))
    # a move is no power edit: nothing changes
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'V240');
        l.offset_y = 40;
        app.updateLayers([l], true, 'Move');
    }""")
    _settle(pg)
    got = read(pg)
    assert got['V240']['n'] == KEPT['V240'] and got['V240']['mark']
    # plugging PLUGGED's second multi: its circuits go on the output's
    # 20 A breaker, 16 A, 12 circuits of 5
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'PLUGGED');
        app.setSocaDistro(l, 2, 'g1');
    }""")
    _settle(pg)
    got = read(pg)
    assert got['PLUGGED']['n'] == [5] * 12, got['PLUGGED']
    assert not got['PLUGGED']['mark'] and not got['PLUGGED']['serverMark']
    assert got['PLUGGED']['line'].startswith('Circuits 1 to 6 use VX output 1 (Socapex, 20 A).')
    # V240's Amperage picked 15 A on the sidebar: 80% of 15 A = 12 A,
    # 240 x 12 = 2,880 W, 7 cabinets, 8 of 7 + 4 (kept, it would be 15 A,
    # 3,600 W, 9 cabinets)
    select(pg, 'V240')
    pg.select_option('#power-amperage-select', '15')
    _settle(pg)
    got = read(pg)
    assert got['V240']['n'] == [7] * 8 + [4], got['V240']
    assert not got['V240']['mark'] and not got['V240']['serverMark']
    # undo puts the screen back as kept, mark and all
    pg.evaluate("() => window.app.undo()")
    _settle(pg)
    got = read(pg)
    assert got['V240']['n'] == KEPT['V240'] and got['V240']['mark'], got['V240']
    # EDISON30's panel input (a connector) picked: held to the 5-20's 16 A
    select(pg, 'EDISON30')
    pg.select_option('#power-panel-input', 'powercon')
    _settle(pg)
    got = read(pg)
    assert got['EDISON30']['n'] == [5] * 12, got['EDISON30']
    assert not got['EDISON30']['mark']
    # the others never moved
    for name in ('LOCKED', 'SAME', 'V240'):
        assert got[name]['n'] == KEPT[name], name
    assert errors == [], errors


def test_a_row_breaker_change_moves_the_unlocked_screen_and_never_the_locked_one(page):
    """VX's row taken to 30 A: PLUGGED's circuits are on it, so it packs to
    80% of 30 A = 24 A, 2,640 W, 8 cabinets: 7 of 8 + 4. LOCKED stays as
    it was, and stays so once unlocked, until its own power is edited:
    then it packs the same as PLUGGED."""
    pg, errors, _ = page
    open_file(pg, show(pg))
    pg.evaluate("""() => {
        const app = window.app;
        const d = app.getDistros()[0];
        app.updateDistro('g1', { outputRows: d.outputRows.map(r => Object.assign({}, r, { breakerA: 30 })) });
    }""")
    _settle(pg)
    got = read(pg)
    assert got['PLUGGED']['n'] == [8] * 7 + [4], got['PLUGGED']
    assert not got['PLUGGED']['mark'] and not got['PLUGGED']['serverMark']
    assert got['LOCKED']['n'] == KEPT['LOCKED'] and got['LOCKED']['mark'], got['LOCKED']
    # unlocking is no power edit
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'LOCKED');
        l.locked = false;
        app.updateLayers([l], true, 'Unlock');
    }""")
    _settle(pg)
    got = read(pg)
    assert got['LOCKED']['n'] == KEPT['LOCKED'] and got['LOCKED']['mark'], got['LOCKED']
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'LOCKED');
        app.setSocaDistro(l, 2, 'g1');
    }""")
    _settle(pg)
    got = read(pg)
    assert got['LOCKED']['n'] == [8] * 7 + [4], got['LOCKED']
    assert not got['LOCKED']['mark']
    assert errors == [], errors


def test_a_show_this_build_saved_is_never_kept(page):
    """A new show carries the rules from the start, so a file of it opens
    by them: PLUGGED on the 20 A Socapex packs 12 circuits of 5."""
    pg, errors, _ = page
    project = show(pg)
    project['powerRules'] = 2
    open_file(pg, project, 'new-show.json')
    got = read(pg)
    assert got['PLUGGED']['n'] == [5] * 12
    assert got['V240']['n'] == [9] * 6 + [6]
    assert got['EDISON30']['n'] == [5] * 12
    assert not any(got[n]['mark'] for n in KEPT)
    fresh = pg.evaluate("async () => (await (await fetch('/api/project/new', {method: 'POST'})).json()).powerRules")
    assert fresh == 2
    assert errors == [], errors


def test_a_wall_takes_the_new_rules_as_one(page):
    """G1 and G2 are one wall: both are kept, the wall stays as saved
    through a reload, and an Amperage change written on G1 alone takes the
    marks off both, so the wall packs as one by the new rules."""
    pg, errors, url = page
    open_file(pg, show(pg))
    got = read(pg)
    assert got['G1']['mark'] and got['G2']['mark'], (got['G1'], got['G2'])
    kept = {n: got[n]['n'] for n in ('G1', 'G2')}
    _ready(pg, url)
    again = read(pg)
    assert {n: again[n]['n'] for n in ('G1', 'G2')} == kept
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'G1');
        l.powerAmperage = 15;
        app._circuitTailCache = null;
        app.updateLayers([l], true, 'Edit Power');
    }""")
    _settle(pg)
    got = read(pg)
    for n in ('G1', 'G2'):
        assert not got[n]['mark'] and not got[n]['serverMark'], (n, got[n])
    assert errors == [], errors


def test_an_l2130_wall_keeps_its_circuits_until_its_power_is_edited(page):
    """L2130 is a 208 V wall on an L21-30 breakout at 20 A, as 1.6.0 laid
    it: 80% of 20 A = 16 A, 208 x 16 = 3,328 W, 8 cabinets of 400 W a
    circuit, 7 of 8 + 4 = 8 circuits. Today an L21-30's three 208 V
    circuits are held to 80% of its 30 A per leg over the square root of 3,
    24 / 1.732 = 13.86 A (2,882 W, 7 cabinets: 8 of 7 + 4 = 9 circuits),
    but the show opens as it was saved, through a reload too. Its watts
    taken to 350 W is a power edit: 2,882 / 350 = 8 cabinets, 7 of 8 + 4,
    held to 13.86 A (the kept 16 A would give 9 a circuit, 6 of 9 + 6)."""
    pg, errors, url = page
    open_file(pg, show(pg))
    got = read(pg)
    assert got['L2130']['n'] == [8] * 7 + [4], got['L2130']
    assert got['L2130']['mark'] and got['L2130']['serverMark']
    _ready(pg, url)
    assert read(pg)['L2130']['n'] == [8] * 7 + [4]
    pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'L2130');
        l.panelWatts = 350;
        app._circuitTailCache = null;
        app.updateLayers([l], true, 'Change Panel Watts');
    }""")
    _settle(pg)
    got = read(pg)
    assert got['L2130']['n'] == [8] * 7 + [4], got['L2130']
    assert not got['L2130']['mark'] and not got['L2130']['serverMark']
    amps = pg.evaluate("""() => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'L2130');
        app._circuitTailCache = null;
        return app.circuitCapacity(l).amps;
    }""")
    assert amps == pytest.approx(24 / 3 ** 0.5)
    assert errors == [], errors
