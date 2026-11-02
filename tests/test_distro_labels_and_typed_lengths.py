"""Distro systems across a thru link, typed lengths in the other unit, two
distros of one name, and a free row's side (owner rulings, 2026-10-22).

  * A distro fed thru another, or feeding one, keeps that distro's system:
    a system change on either end is refused, naming the linked distro,
    and nothing changes. An old distro saved as {voltage, phase} only is
    fed thru, or feeds, another only where both resolve to one system.
  * A length typed in the other unit converts everywhere a length is typed
    - a multi's home run, a direct output's cable, a circuit cable, a data
    port, a snake - with the feeder field's own words; text that is no
    length is refused and the length that was there stays. A meters show
    reads "100ft" as 30.48 m.
  * Two distros of one name read SR-1 and SR-2 everywhere, and their
    boxes and circuits derive from that label: boxes SR-1-1, circuits
    SR-1-1-1. A unique name is unchanged; a distro whose screens are all
    hidden is not counted, and the binder's maps never change a label.
  * The Feed "fed from" title uses no spaced hyphen as a dash.
  * A free row's side: RJ45, LC, coax, BNC and a network switch are data,
    and a catalog model's short name ("UHD JR") counts.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_labels_and_typed_lengths.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_services import (  # noqa: E402
    SEED_JS, US, SVC, HIST_JS, TOASTS_JS, _open, setup)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg, errors = _open(pw_browser, e2e_server)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def thru(i, name, src, rating=400, system='120/208', **kw):
    return dict(US(i, name, rating, system), feeder={'from': src}, **kw)


def toasts(pg):
    return pg.evaluate(TOASTS_JS)


def clear_toasts(pg):
    pg.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


# ── a system change never leaves a cross-system thru link ─────────────────

def test_a_system_change_on_either_end_of_a_thru_link_is_refused(page):
    """SR fed thru SL, both 120/208. SR to 120/240 is refused naming SL;
    SL to 120/240 (by system, or by an old voltage/phase patch) is refused
    naming SR. Nothing changes and no entry is taken. FOH, linked to
    nothing, changes freely."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), thru('d2', 'SR', 'd1'), US('d3', 'FOH')])
    n = len(pg.evaluate(HIST_JS))
    out = pg.evaluate("""() => {
        const app = window.app;
        const sys = () => app.getDistros().map(d => d.system);
        const a = app.updateDistro('d2', { system: '120/240' });
        const b = app.updateDistro('d1', { system: '120/240' });
        const c = app.updateDistro('d1', { voltage: 240, phase: 1 });
        const kept = sys();
        const fedFrom = app.distroFeeder(app.getDistros()[1]).from;
        return { a, b, c, kept, fedFrom: fedFrom ? fedFrom.id : null };
    }""")
    assert out['a'] is None and out['b'] is None and out['c'] is None, out
    assert out['kept'] == ['120/208', '120/208', '120/208'], out
    assert out['fedFrom'] == 'd1', out
    assert len(pg.evaluate(HIST_JS)) == n, 'a refusal took a history entry'
    said = toasts(pg)
    assert ('SR is powered thru SL, which is 120/208V 3φ. Power SR from its service before '
            'changing its system.') in said, said
    assert ("SR is powered thru SL and is 120/208V 3φ. Power SR from its service before "
            "changing SL's system.") in said, said
    # unlinked: it changes, one entry
    assert pg.evaluate("() => !!window.app.updateDistro('d3', { system: '120/240' })") is True
    assert pg.evaluate("() => window.app.getDistros()[2].system") == '120/240'
    assert len(pg.evaluate(HIST_JS)) == n + 1
    # fed from its service again, SR may change
    pg.evaluate("() => window.app.setDistroFeeder('d2', { from: null })")
    assert pg.evaluate("() => !!window.app.updateDistro('d2', { system: '120/240' })") is True
    assert not errors, errors


def test_old_distros_resolve_their_system_before_a_thru_link(page):
    """Saved as {voltage, phase} only: 208V 3φ and 208V 3φ are both
    120/208 and may be linked; 120V 1φ is 120V and may not; 240V 1φ names
    no system and is fed thru, and feeds, nothing."""
    pg, errors = page
    old = lambda i, name, v, ph: {'id': i, 'name': name, 'ratingA': 100, 'voltage': v, 'phase': ph}  # noqa: E731
    setup(pg, distros=[old('d1', 'A', 208, 3), old('d2', 'B', 120, 1), old('d3', 'C', 208, 3),
                       old('d4', 'D', 240, 1)])
    out = pg.evaluate("""() => {
        const app = window.app;
        const ds = app.getDistros();
        const src = (i) => app.feederSources(ds[i]).map(d => d.id);
        const fed = app.setDistroFeeder('d4', { from: 'd1' });
        return { c: src(2), a: src(0), d: src(3), b: src(1), fed,
                 feeder: ds[3].feeder || null };
    }""")
    assert out['c'] == ['d1'], out
    assert out['a'] == ['d3'], out
    assert out['d'] == [] and out['b'] == [], out
    assert out['fed'] is False and out['feeder'] is None, out
    assert not errors, errors


# ── typed lengths in the other unit ───────────────────────────────────────

LENGTHS_JS = """() => {
    const app = window.app;
    const W = app.project.layers.find(l => l.name === 'WALL A');
    const out = {};
    app.setSocaLength(W, 1, '30m');
    out.home = W.powerSocaLengths[1];
    app.setSocaLength(W, 1, 'abc');
    out.homeKept = W.powerSocaLengths[1];
    out.homeRefused = app.setSocaLength(W, 1, 'abc');
    app.setCircuitCable(W, 1, { ft: '30m', connector: null });
    out.circuit = W.powerCircuitCables[1].ft;
    out.circuitRefused = app.setCircuitCable(W, 1, { ft: 'abc', connector: null });
    out.circuitKept = W.powerCircuitCables[1].ft;
    // the data setters, their writes caught before the server
    const caught = [];
    const origReq = app._processorRequest, origSnake = app.getShowSnake;
    app._processorRequest = (url, method, body) => { caught.push(JSON.parse(JSON.stringify(body))); return Promise.resolve(); };
    app.getShowSnake = (id) => ({ id, name: 'SNAKE A', ft: null });
    const owner = { id: 'o1', kind: 'card', rec: { portCables: {} } };
    const origUrl = app._dataCableOwnerUrl;
    app._dataCableOwnerUrl = () => '/nowhere';
    try {
        app.setPortCable(owner, 3, { ft: '30m', connector: null }, 'Set Port Cable');
        app.setPortCable(owner, 3, { ft: 'abc', connector: null }, 'Set Port Cable');
        app.setSnake('sn1', { ft: '30m' }, 'Set Snake Home Run');
        app.setSnake('sn1', { ft: 'abc' }, 'Set Snake Home Run');
    } finally {
        app._processorRequest = origReq; app.getShowSnake = origSnake; app._dataCableOwnerUrl = origUrl;
    }
    out.data = caught;
    app.project.cableUnit = 'm';
    app.setSocaLength(W, 2, '100ft');
    out.metric = W.powerSocaLengths[2];
    app.project.cableUnit = 'ft';
    return out;
}"""


def test_a_length_in_the_other_unit_converts_in_every_setter(page):
    """Feet show: "30m" is 98.4 on a multi's home run, a circuit cable, a
    data port and a snake, said in the feeder's words; "abc" is refused,
    said, and the length stays. A meters show reads "100ft" as 30.48."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')], assign=[['WALL A', 0, 4, 'd1']])
    out = pg.evaluate(LENGTHS_JS)
    assert out['home'] == '98.4' and out['homeKept'] == '98.4' and out['homeRefused'] is False, out
    assert out['circuit'] == 98.4 and out['circuitKept'] == 98.4 and out['circuitRefused'] is False, out
    assert out['data'] == [{'portCables': {'3': {'ft': 98.4}}}, {'ft': 98.4}], out['data']
    assert out['metric'] == '30.48', out
    said = toasts(pg)
    assert '30m is 98.4 ft in this feet show.' in said, said
    assert '"abc" is not a length. Type the home run\'s length in feet, like 100.' in said, said
    assert '"abc" is not a length. Type the cable\'s length in feet, like 100.' in said, said
    assert '"abc" is not a length. Type the snake\'s length in feet, like 100.' in said, said
    assert '100ft is 30.48 m in this meters show.' in said, said
    assert not errors, errors


def test_the_tray_fields_take_a_length_in_the_other_unit(page):
    """The multi header's home-run field: "30m" stores 98.4 on the multi
    and the pull sheet prints 98.4'; "abc" is refused, takes no entry and
    the field shows 98.4 again. The circuit cable sheet's field is text, so
    "30m" can be typed, and stores 98.4."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL')], assign=[['WALL A', 0, 0, 'd1']])
    lid = pg.evaluate("() => window.app.project.layers.find(l => l.name === 'WALL A').id")
    field = f'[data-lrd-field="power-soca-length-{lid}-1"]'
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", field)
    pg.locator(field).fill('30m')
    pg.locator(field).press('Enter')
    pg.wait_for_timeout(400)
    stored = pg.evaluate("(id) => (window.app.project.layers.find(l => l.id === id).powerSocaLengths || {})[1]", lid)
    assert stored == '98.4', stored
    rows = pg.evaluate("""() => { const app = window.app; app._circuitTailCache = null;
        return app.buildPullList().positions.flatMap(p => p.rows)
            .filter(r => r.type === 'Multi').map(r => [r.length, r.notes]); }""")
    assert ["98.4'", ''] in rows, rows
    n = len(pg.evaluate(HIST_JS))
    pg.locator(field).fill('abc')
    pg.locator(field).press('Enter')
    pg.wait_for_timeout(400)
    assert len(pg.evaluate(HIST_JS)) == n, 'a refused length took an entry'
    assert pg.locator(field).input_value() == '98.4'
    # the circuit cable sheet
    pg.evaluate("""() => { const app = window.app;
        app._setCableSheetOpen('d1', 1, true); app.renderHardwareDock(); }""")
    pg.wait_for_timeout(300)
    cell = f'[data-lrd-field="power-cable-ft-{lid}-1"]'
    assert pg.evaluate("(s) => document.querySelector(s).type", cell) == 'text'
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", cell)
    pg.locator(cell).fill('30m')
    pg.locator(cell).press('Tab')
    pg.wait_for_timeout(400)
    ft = pg.evaluate("(id) => (window.app.project.layers.find(l => l.id === id).powerCircuitCables || {})[1]", lid)
    assert ft and ft['ft'] == 98.4, ft
    pg.evaluate("() => { window.app._setCableSheetOpen('d1', 1, false); window.app.renderHardwareDock(); }")
    assert not errors, errors


# ── two distros of one name ───────────────────────────────────────────────

NAMES_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const W = app.project.layers.find(l => l.name === 'WALL A');
    const B = app.project.layers.find(l => l.name === 'WALL B');
    const list = app.buildPullList();
    const hwNames = list.hardware.filter(h => h.kind === 'distro').map(h => h.name);
    const distroRows = list.positions.flatMap(p => p.rows).filter(r => r.type === 'Distro')
        .map(r => r.label);
    const multis = list.positions.flatMap(p => p.rows).filter(r => r.type === 'Multi').map(r => r.label);
    const boxes = [...app.distroBoxLabels().entries()];
    const plan = app.getSocaPlan(W);
    const circuit = (l, n) => app.getPowerCircuitLabel(l, n);
    return {
        labels: app.getDistros().map(d => app.distroLabel(d)),
        boxes, hwNames, distroRows, multis,
        circuits: [circuit(W, 1), circuit(W, 2), circuit(W, 31), circuit(B, 1)],
        loads: app.getDistroLoads().filter(L => L.id).map(L => L.name),
        suffix: [...document.querySelectorAll('[data-lrd-distro-suffix]')]
            .map(e => [e.dataset.lrdDistroSuffix, e.textContent]),
        plan: plan.length,
    };
}"""


def test_two_distros_of_one_name_read_sr_1_and_sr_2_everywhere(page):
    """Two distros named SR, WALL A's first five multis on one and the
    next five on the other: they read SR-1 and SR-2 on the pull sheet, in
    the tray and in the roll-ups; their boxes are SR-1-1 ... SR-2-5 and
    their circuits SR-1-1-1 ..., so no box reads like a circuit."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SR'), US('d2', 'SR'), US('d3', 'SL')],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL A', 5, 9, 'd2'], ['WALL B', 0, 0, 'd3']])
    out = pg.evaluate(NAMES_JS)
    assert out['labels'] == ['SR-1', 'SR-2', 'SL'], out
    boxes = dict(out['boxes'])
    assert [boxes[f'd1|{i}'] for i in range(1, 6)] == [f'SR-1-{i}' for i in range(1, 6)], boxes
    assert [boxes[f'd2|{i}'] for i in range(1, 6)] == [f'SR-2-{i}' for i in range(1, 6)], boxes
    assert boxes['d3|1'] == 'SL1', boxes
    assert out['circuits'] == ['SR-1-1-1', 'SR-1-1-2', 'SR-2-1-1', 'SL1-1'], out['circuits']
    circuit_names = set(out['circuits'])
    assert not circuit_names & set(boxes.values()), 'a box reads like a circuit'
    assert sorted(out['hwNames']) == ['SL', 'SR-1', 'SR-2'], out['hwNames']
    # the pull sheet folds one position's Distro rows into one, its labels
    # joined: "SR-1, SR-2"
    assert sorted(n for r in out['distroRows'] for n in r.split(', ')) == ['SL', 'SR-1', 'SR-2'], \
        out['distroRows']
    assert 'SR-1-1 … 1-5, SR-2-1 … 2-5' in out['multis'], out['multis']
    assert out['loads'] == ['SR-1', 'SR-2', 'SL'], out['loads']
    assert sorted(out['suffix']) == [['d1', '-1'], ['d2', '-2']], out['suffix']
    # the name field keeps the name as typed
    assert pg.locator('[data-lrd-field="distro-name-d1"]').input_value() == 'SR'
    # renamed apart: unique names are unchanged
    pg.evaluate("() => { window.app.updateDistro('d2', { name: 'SC' }); window.app._restateNaming(); }")
    out = pg.evaluate(NAMES_JS)
    assert out['labels'] == ['SR', 'SC', 'SL'], out
    assert out['circuits'] == ['SR1-1', 'SR1-2', 'SC1-1', 'SL1-1'], out['circuits']
    assert out['suffix'] == [], out['suffix']
    assert not errors, errors


def test_a_distro_on_hidden_screens_only_is_not_counted(page):
    """SR on WALL A, another SR on WALL B only. With WALL B hidden, WALL A's
    SR is plain SR (boxes SR1, circuits SR1-1); shown again, SR-1."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SR'), US('d2', 'SR')],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL B', 0, 0, 'd2']])
    hide = """(on) => { const app = window.app;
        app.project.layers.find(l => l.name === 'WALL B').visible = on; app._circuitTailCache = null; }"""
    pg.evaluate(hide, False)
    out = pg.evaluate(NAMES_JS)
    assert out['labels'] == ['SR', 'SR'], out
    assert dict(out['boxes'])['d1|1'] == 'SR1', out['boxes']
    assert out['circuits'][0] == 'SR1-1', out['circuits']
    pg.evaluate(hide, True)
    out = pg.evaluate(NAMES_JS)
    assert out['labels'] == ['SR-1', 'SR-2'], out
    assert out['circuits'][0] == 'SR-1-1-1' and out['circuits'][3] == 'SR-2-1-1', out['circuits']
    assert not errors, errors


def test_the_binder_reads_the_suffixed_labels_and_its_maps_never_change_them(page):
    """The binder's distro sheets are titled SR-1 and SR-2 and their box
    tables read SR-1-1 ...; while a screen's map hides every other screen
    the labels stay as the show has them."""
    pg, errors = page
    setup(pg, distros=[US('d1', 'SR'), US('d2', 'SR')],
          assign=[['WALL A', 0, 4, 'd1'], ['WALL B', 0, 0, 'd2']])
    out = pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const seen = new Set();
        const orig = app.distroLabel;
        app.distroLabel = function (d) { const v = orig.call(this, d); seen.add(`${d && d.id}:${v}`); return v; };
        const boxes = [];
        const origBlocks = app._bDistroBlocks;
        app._bDistroBlocks = function (book, d, load, rows) {
            boxes.push(...rows.map(b => b.cells[0]));
            return origBlocks.apply(this, arguments);
        };
        const titles = [];
        try {
            const opts = Object.assign(app.readBinderOptions(),
                { scope: { kind: 'show' }, hardware: true, pull: true, cover: false, wiring: false,
                  sides: { power: true, data: false } });
            const plan = app.planBinder(opts);
            for (let i = 0; i < plan.length; i++) {
                titles.push(plan[i].title);
                app.renderBinderPage(opts, i);
            }
        } finally { app.distroLabel = orig; app._bDistroBlocks = origBlocks; }
        return { seen: [...seen].sort(), boxes, titles };
    }""")
    assert out['seen'] == ['d1:SR-1', 'd2:SR-2'], out['seen']
    assert 'SR-1-1' in out['boxes'] and 'SR-2-1' in out['boxes'], out['boxes']
    assert any('SR-1' in t for t in out['titles']) and any('SR-2' in t for t in out['titles']), out['titles']
    assert not errors, errors


# ── wording ───────────────────────────────────────────────────────────────

def test_the_fed_from_title_uses_no_spaced_hyphen(page):
    pg, errors = page
    setup(pg, distros=[US('d1', 'SL'), US('d2', 'SR')])
    title = pg.evaluate("""() => {
        const wrap = document.createElement('div');
        window.app._buildDistroFeederRow(window.app.getDistros()[0], wrap);
        return wrap.querySelector('select').title;
    }""")
    assert ' - ' not in title, title
    assert "it is powered thru. Its load then counts on that distro's service." in title, title
    assert not errors, errors


# ── a free row's side ─────────────────────────────────────────────────────

def test_rj45_lc_coax_bnc_switch_and_a_model_short_name_are_data(page):
    pg, errors = page
    data = ['RJ45 coupler', 'UHD JR', 'LC duplex patch', 'Network switch', 'Coax', 'BNC',
            'UHD Jr spare', 'RJ-45 barrel']
    power = ['Power switch', 'Calc sheet', 'Gaff', 'Socapex', 'Pro', 'Jr']
    sides = pg.evaluate("(ts) => Object.fromEntries(ts.map(t => [t, window.app.pullGuessSide(t)]))",
                        data + power)
    assert {t: sides[t] for t in data} == {t: 'data' for t in data}, sides
    assert {t: sides[t] for t in power} == {t: 'power' for t in power}, sides
    assert not errors, errors
