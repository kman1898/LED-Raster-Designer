"""A hidden screen keeps its lengths in the app and prints nothing in the
binder while it stays hidden.

The owner, 2026-11-17: "hidden screens can have lengths in the app but not
in the binder if they remain hidden".

One synthetic show:

  SHOWN   on distro SHARED's multi 1 and on RACK SHARED's XD A, port 1
  HID A   on distro SHARED's multi 2 and on RACK SHARED's XD A, port 2
          (shares the distro, the processor, the box and its TAC)
  HID B   alone on distro LONE (its Power in set) and on RACK LONE's XD A,
          its TAC LONE on that box

with a length on every circuit, multi and port: SHOWN's are 10' and 100',
the hidden screens' 63' and 163' (lengths no other row of the show uses).

While HID A and HID B are hidden, no sheet of the binder and no row of the
pull sheet (the workbook is built from the same list) says anything of
them: no name, no length, no circuit, no port, no box or distro or
processor that only they use. Unhidden, everything is back with the lengths
the app kept.

Run locally:
    python -m pytest tests/test_hidden_screen_binder.py -n 4 --dist loadfile --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402
from test_quick_fill_in_use import CLOSED_JS, FETCH_COUNT_JS, landed  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


DIALOGS = ('save-file', 'open-file', 'select-directory')

SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
    if (typeof app._layerSavesSettled === 'function') await app._layerSavesSettled();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.snakes = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services; delete proj.fiberCables;
    await j('PUT', '/api/project', proj);
    const names = ['SHOWN', 'HID A', 'HID B'];
    for (let i = 0; i < names.length; i++) {
        await j('POST', '/api/layer/add', { name: names[i], columns: 4, rows: 2,
            cabinet_width: 500, cabinet_height: 500, offset_x: i * 2100 });
    }
    const last = (st) => st.processors[st.processors.length - 1];
    const cable = (st) => st.fiberCables[st.fiberCables.length - 1];
    const procs = {};
    for (const [key, name, tac] of [['shared', 'RACK SHARED', 'TAC SHARED'],
                                    ['lone', 'RACK LONE', 'TAC LONE']]) {
        let st = await j('POST', '/api/processors', { deviceId: 'brompton-sx40', name });
        const p = last(st);
        const xd = p.slots[0].card.cvts[0].id;
        st = await j('POST', '/api/fiber-cables', { kind: 'tac', strands: 12,
            ft: key === 'shared' ? 300 : 263, connector: 'LC duplex',
            link: { boxId: xd, key: 'p1' } });
        await j('PUT', `/api/fiber-cables/${cable(st).id}`, { name: tac });
        await j('PUT', `/api/processors/${p.id}`,
                { network: { ip: key === 'shared' ? '10.0.0.10' : '10.0.0.63' } });
        procs[key] = { id: p.id, card: p.slots[0].card.id, xd };
    }
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    const layer = (n) => app.project.layers.find(l => l.name === n);
    const place = async (name, key, first) => {
        const wall = layer(name);
        const pr = procs[key];
        const box = app._processorsResolved.find(p => p.id === pr.id)
            .slots[0].card.cvts.find(b => b.id === pr.xd);
        const nums = app.boxMainPorts(box).map(p => p.number).sort((a, b) => a - b);
        const need = app.getLayerPortsRequired(wall);
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {
            layerId: String(wall.id), cardId: pr.card, boxId: pr.xd,
            firstPort: nums[first], lastPort: nums[nums.length - 1],
            screens: [{ layerId: String(wall.id), name, ports: need }] });
        await app.refreshPortAssignment();
        const got = [];
        for (let n = 1; n <= need; n++) {
            const pin = app._screenPortPin(wall, n);
            if (pin) got.push(pin.port);
        }
        return got;
    };
    const ports = {};
    ports['SHOWN'] = await place('SHOWN', 'shared', 0);
    ports['HID A'] = await place('HID A', 'shared', ports['SHOWN'].length);
    ports['HID B'] = await place('HID B', 'lone', 0);
    await app.refreshProcessors();
    // a port cable on every port a screen is on
    for (const [name, key] of [['SHOWN', 'shared'], ['HID A', 'shared'], ['HID B', 'lone']]) {
        const pr = procs[key];
        const box = app._processorsResolved.find(p => p.id === pr.id)
            .slots[0].card.cvts.find(b => b.id === pr.xd);
        const cables = Object.assign({}, box.portCables || {});
        for (const n of ports[name]) cables[String(n)] = { ft: name === 'SHOWN' ? 10 : 63 };
        await j('PUT', `/api/processors/${pr.id}/cvts/${pr.xd}`, { portCables: cables });
        await app.refreshProcessors();
    }
    // HID B's last two ports on a snake, its box placed at a location
    await j('POST', '/api/snakes', { name: 'SNAKE LONE', ft: 63, members:
        ports['HID B'].slice(2).map(n => ({ kind: 'cvt', id: procs.lone.xd, socket: n })) });
    await j('PUT', `/api/processors/${procs.lone.id}/cvts/${procs.lone.xd}`, { location: 'LONE DOCK' });
    await app.refreshProcessors();
    app.project = await j('GET', '/api/project');
    // power: SHOWN and HID A on distro SHARED's multis 1 and 2, HID B on
    // distro LONE (its Power in set)
    const out = (o) => ({ id: o.id, name: o.name, ratingA: 200, system: '120/208',
        outputRows: [{ id: 'r1', connector: 'soca', count: 4, coupling: 'll', breakerA: 20 }],
        serviceId: o.service, ...(o.feeder ? { feeder: o.feeder } : {}) });
    app.project.services = [
        { id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208', voltage: 208, phase: 3 },
        { id: 's2', name: 'GENNY LONE', ratingA: 400, system: '120/208', voltage: 208, phase: 3 }];
    app.project.distros = [out({ id: 'dshared', name: 'SHARED', feeder: { ft: 100 }, service: 's1' }),
                           out({ id: 'dlone', name: 'LONE', feeder: { ft: 163 }, service: 's2' })];
    const power = { 'SHOWN': ['dshared', 1, 10, 100], 'HID A': ['dshared', 2, 63, 163],
                    'HID B': ['dlone', 1, 63, 163] };
    for (const [name, [d, n, circuitFt, runFt]] of Object.entries(power)) {
        const l = layer(name);
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 300,
            powerFlowPattern: 'tl-h', powerSocaDistro: { '1': d }, powerSocaNumber: { '1': n },
            powerSocaLengths: { '1': String(runFt) }, powerSocaSplits: [],
            processorType: 'brompton' });
        app.normalizePowerBreakout(l);
        app._circuitTailCache = null;
        const cables = {};
        for (const c of app.screenCircuits(l)) cables[String(c.num)] = { ft: circuitFt, connector: null };
        l.powerCircuitCables = cables;
    }
    app.project.cableUnit = 'ft';
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    app.selectLayer(layer('SHOWN'));
    app.renderLayers();
    app.renderHardwareDock();
    return { ports, procs };
}"""

HIDE_JS = """(hidden) => {
    const app = window.app;
    for (const l of app.project.layers) l.visible = !hidden.includes(l.name);
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
}"""

# Every sheet of the binder with every extra on: every text it writes, and
# every table and fact list it builds; the pull sheet as the workbook gets
# it (routes_pull_sheet builds the xlsx from this very list).
BINDER_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const opts = Object.assign(app.readBinderOptions(), {
        sheet: 'tabloid', palette: 'colour', scope: { kind: 'show' },
        sides: { power: true, data: true }, cover: true, pull: true, hardware: true,
        wiring: true, rigging: true, fiber: true, network: true, titleBlock: true });
    const tables = [], kv = [];
    const origT = app._bTableLines, origK = app._bKvLines;
    app._bTableLines = function (book, spec) {
        if (!book.dry) {
            tables.push({ title: spec.title,
                          rows: (spec.rows || []).filter(r => r.cells).map(r => r.cells.slice()) });
        }
        return origT.apply(this, arguments);
    };
    app._bKvLines = function (book, title, pairs) {
        if (!book.dry) kv.push({ title, pairs: pairs.map(p => p.slice()) });
        return origK.apply(this, arguments);
    };
    const pages = [];
    let plan;
    try {
        plan = app.planBinder(opts);
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            pages.push({ number: plan[i].number, kind: plan[i].kind, title: plan[i].title,
                         texts: r.record.ops.filter(op => op.op === 'text' && String(op.text).trim())
                             .map(op => String(op.text)) });
        }
    } finally { app._bTableLines = origT; app._bKvLines = origK; }
    return { pages, tables, kv, uses: { fiber: app.binderUsesFiber(), network: app.binderUsesNetwork() },
             pull: JSON.parse(JSON.stringify(app.buildPullSheet())) };
}"""

# What only the hidden screens have: their names, the gear only they use
# (distro LONE, its service GENNY LONE, processor RACK LONE, its TAC LONE,
# SNAKE LONE, the LONE DOCK its box sits at) and their lengths (63', 163',
# 263'), RACK LONE's IP.
HIDDEN_WORDS = ('HID A', 'HID B', 'LONE', "63'", "163'", "263'", '10.0.0.63')


def _hits(texts):
    return sorted({(w, t) for t in texts for w in HIDDEN_WORDS if w in str(t)})


def _page_hits(out, kinds=None):
    return [(p['number'], p['title'], hit) for p in out['pages']
            if kinds is None or p['kind'] in kinds
            for hit in _hits(p['texts'] + [p['title']])]


def _once(items):
    """Each table or fact list once: a sheet measures them more than once."""
    seen, out = set(), []
    for x in items:
        k = json.dumps(x, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _table(out, title_start):
    return _once([t for t in out['tables'] if str(t['title']).startswith(title_start)])


def _kv(out, title):
    return [dict((k, v) for k, v in x['pairs'])
            for x in _once([x for x in out['kv'] if x['title'] == title])]


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    for name in DIALOGS:
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"ok": false, "cancelled": true, "unavailable": false}'))
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " === true && window.app._socketConnects >= 1")
    landed(pg)
    seed = pg.evaluate(SEED_JS)
    landed(pg)
    yield pg, seed, errors
    context.close()


@pytest.fixture(scope="module")
def binders(page):
    """The binder and pull sheet three times: every screen shown, HID A and
    HID B hidden, and both shown again."""
    pg, seed, errors = page
    pg.evaluate(HIDE_JS, [])
    before = pg.evaluate(BINDER_JS)
    pg.evaluate(HIDE_JS, ['HID A', 'HID B'])
    hidden = pg.evaluate(BINDER_JS)
    pg.evaluate(HIDE_JS, [])
    again = pg.evaluate(BINDER_JS)
    assert errors == [], errors
    return {'before': before, 'hidden': hidden, 'again': again, 'seed': seed}


def test_the_fixture_puts_every_hidden_screen_on_paper_while_shown(binders):
    """Shown, the hidden screens' gear and lengths are all over the binder:
    the words the tests below look for are real."""
    b = binders['before']
    found = {w for _, _, (w, _) in _page_hits(b)}
    assert found == set(HIDDEN_WORDS), found
    assert binders['seed']['ports'] == {'SHOWN': [1, 2, 3, 4], 'HID A': [5, 6, 7, 8],
                                        'HID B': [1, 2, 3, 4]}, binders['seed']
    assert b['uses'] == {'fiber': True, 'network': True}, b['uses']


def test_the_pull_sheet_lists_nothing_of_a_hidden_screen(binders):
    """The workbook's list: no row, label or total of a hidden screen, and
    no gear only hidden screens use - the distro LONE and its Power in,
    RACK LONE, its box at LONE DOCK, TAC LONE, SNAKE LONE."""
    pull = binders['hidden']['pull']
    assert _hits([json.dumps(pull)]) == [], _hits([json.dumps(pull)])
    assert [p['name'] for p in pull['positions']] == ['SHOWN'], pull['positions']
    assert sorted((h['kind'], h['name']) for h in pull['hardware']) == [
        ('distro', 'SHARED'), ('processor', 'RACK SHARED')], pull['hardware']
    # the shared processor's own rows stay: the SX40 and TAC SHARED
    rows = [(r['type'], r['length'], r['label']) for r in pull['totals']]
    assert any(r[2] == 'RACK SHARED' for r in rows), rows
    assert any(r[2] == 'TAC SHARED' and r[1] == "300'" for r in rows), rows


def test_no_sheet_prints_a_hidden_screen(binders):
    """No page of the binder - screen sheets, Fiber, pull, distro, service,
    processor, Network, Overview - names a hidden screen, a length of one,
    or gear only hidden screens use."""
    hidden = binders['hidden']
    assert _page_hits(hidden) == [], _page_hits(hidden)
    assert [p['title'] for p in hidden['pages']] == [
        'Overview', 'SHOWN - Power - Front View', 'SHOWN - Power Wiring',
        'SHOWN - Data - Front View', 'SHOWN - Data Wiring', 'Fiber', 'Pull - SHOWN',
        'Service - HOUSE', 'Distro - SHARED', 'Processor - RACK SHARED · Pull list',
        'Network'], [p['title'] for p in hidden['pages']]


def test_the_shared_distro_and_service_print_only_the_shown_screen(binders):
    """SHARED (SHOWN on multi 1, HID A on multi 2) lists multi 1 alone; the
    service HOUSE counts SHARED alone; LONE (HID B's, its Power in set) and
    its service GENNY LONE are off; the Overview counts one of each."""
    hidden, before = binders['hidden'], binders['before']
    multis = _table(hidden, '1 Socapex 208V')
    assert [r[:4] for t in multis for r in t['rows']] == [['SHARED1', 'Socapex 208V', "100'", 'SHOWN']], multis
    assert [x['Circuits'] for x in _kv(hidden, 'Distro')] == ['1 on 1 Socapex 208V'], _kv(hidden, 'Distro')
    assert [x['Distros'] for x in _kv(hidden, 'Service')] == ['ratings 200 A on 600 A'], _kv(hidden, 'Service')
    assert len(_kv(before, 'Service')) == 2 and len(_kv(before, 'Distro')) == 2
    totals = _kv(hidden, 'Show totals')
    assert len(totals) == 1, totals
    assert {k: totals[0][k] for k in ('Screens', 'Circuits', 'Ports', 'Distros', 'Processors')} == {
        'Screens': '1', 'Circuits': '1', 'Ports': '4', 'Distros': '1', 'Processors': '1'}, totals
    assert [r[0] for t in _table(hidden, 'Positions') for r in t['rows']] == ['SHOWN']


def test_the_shared_processor_prints_only_the_shown_screens_ports(binders):
    """RACK SHARED's sheet: its home runs are SHOWN's four 10' cables, never
    HID A's 63' ones; the ports it counts taken are SHOWN's; its canvas
    line (the two walls are past an SX40's canvas together) does not name
    HID A; RACK LONE, its box and its TAC are on no sheet."""
    hidden, before = binders['hidden'], binders['before']
    runs = _table(hidden, 'Snakes & home runs')
    assert [r for t in runs for r in t['rows']] == [
        [f'XD A {n}', 'cable', "10'", 'etherCON'] for n in (1, 2, 3, 4)], runs
    assert [r[1] for t in _table(hidden, 'Processor') for r in t['rows']] == ['4 / 40']
    assert sorted(r[1] for t in _table(before, 'Processor') for r in t['rows']) == ['4 / 40', '8 / 40']
    assert any('HID A' in str(x.get('Canvas', '')) for x in _kv(before, 'Redundancy'))
    assert [x for x in _kv(hidden, 'Redundancy') if 'Canvas' in x] == []
    assert [r[0] for t in _table(hidden, 'Breakout boxes') for r in t['rows']] == ['XD A', 'XD B', 'XD C', 'XD D']
    assert sorted({t['title'] for t in _table(hidden, 'Strand map')}) == [
        "Strand map · TAC SHARED · TAC 12 · LC duplex · 300'"], _table(hidden, 'Strand map')
    assert [r[0] for t in _table(hidden, '1 unit') for r in t['rows']] == ['RACK SHARED']


def test_unhiding_brings_everything_back_with_its_lengths(binders):
    """Shown again, the binder and the pull sheet are what they were before
    the screens were hidden, every length the app kept on them included."""
    before, again = binders['before'], binders['again']
    assert [p['title'] for p in again['pages']] == [p['title'] for p in before['pages']]
    for a, b in zip(again['pages'], before['pages']):
        assert a['texts'] == b['texts'], (a['title'], set(a['texts']) ^ set(b['texts']))
    assert again['pull'] == before['pull']
    hid = {s['name']: s for s in again['pull']['byScreen'].values()}
    assert [p['cable'] for p in hid['HID A']['ports']] == ["63' etherCON"] * 4, hid['HID A']['ports']
    circuits = [c['cable'] for b in hid['HID A']['boxes'] for c in b['circuits']]
    assert circuits and all(c.startswith("63'") for c in circuits), circuits


# ── quick fill keeps filling a hidden screen ──────────────────────────────

STORED_JS = """(xd) => {
    const app = window.app;
    for (const p of app._processorsResolved || []) for (const s of p.slots || []) {
        const b = s.card && (s.card.cvts || []).find(x => x.id === xd);
        if (b) return Object.fromEntries(Object.entries(b.portCables || {})
            .map(([k, v]) => [k, Number(v && v.ft) || null]));
    }
    return null;
}"""


def test_quick_fill_fills_a_hidden_screen_and_its_binder_stays_clean(page):
    """Quick fill still gives a hidden screen its lengths in the app: all
    100' on RACK SHARED's XD A writes SHOWN's ports and hidden HID A's,
    never the two empty ones; a ticked empty port takes the ticked length;
    the multi's 10' writes hidden HID A's circuits. The binder prints none
    of HID A's; shown again, they are there."""
    pg, seed, errors = page
    seed = pg.evaluate(SEED_JS)
    landed(pg)
    pg.evaluate(HIDE_JS, ['HID A', 'HID B'])
    shared = seed['procs']['shared']
    xd = shared['xd']
    pg.evaluate("""async ([p, b]) => {
        await fetch(`/api/processors/${p}/cvts/${b}`, { method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portCables: {} }) });
        await window.app.refreshProcessors();
        window.app.renderHardwareDock();
        window.app.resetHistory('Hidden Fill Seed');
    }""", [shared['id'], xd])
    landed(pg)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'data-flow'")
    landed(pg)
    for _ in range(12):
        shut = pg.evaluate(CLOSED_JS, False)
        if not shut:
            break
        pg.locator(f'[data-lrd-field="{shut[0]}"]').first.click()
        landed(pg)
    pg.locator(f'[data-lrd-field="data-cable-fill-{xd}-100"]').first.click()
    landed(pg)
    want = {str(n): 100 for n in seed['ports']['SHOWN'] + seed['ports']['HID A']}
    got = settled(pg, lambda: pg.evaluate(STORED_JS, xd), lambda c: c == want)
    assert got == want, got
    # a ticked port with nothing on it takes the ticked length
    pg.locator(f'[data-lrd-field="data-snake-tick-{xd}-10"]').first.check()
    pg.locator(f'[data-lrd-field="data-cable-ticked-fill-{xd}"]').first.fill('42')
    pg.locator(f'[data-lrd-field="data-cable-ticked-fill-{xd}-btn"]').first.click()
    landed(pg)
    got = settled(pg, lambda: pg.evaluate(STORED_JS, xd), lambda c: c.get('10') == 42)
    assert got == {**want, '10': 42}, got

    # power: the multi HID A is on, hidden, takes the fill
    pg.evaluate("""() => { const app = window.app;
        const l = app.project.layers.find(x => x.name === 'HID A');
        for (const n of Object.keys(l.powerCircuitCables || {})) app.setCircuitCable(l, Number(n), null);
        app.renderHardwareDock(); }""")
    landed(pg)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    landed(pg)
    pg.locator('[data-lrd-field="power-cable-sheet-dshared-2"]').click()
    landed(pg)
    pg.locator('[data-lrd-field="power-cable-fill-dshared-2-10"]').click()
    landed(pg)
    circuits = settled(pg, lambda: pg.evaluate("""() => { const l = window.app.project.layers
            .find(x => x.name === 'HID A');
        return Object.values(l.powerCircuitCables || {}).map(c => c && c.ft); }"""),
        lambda v: v and all(x == 10 for x in v))
    assert circuits and all(x == 10 for x in circuits), circuits

    hidden = pg.evaluate(BINDER_JS)
    runs = _table(hidden, 'Snakes & home runs')
    assert [r[2] for r in runs[0]['rows']] == ["100'"] * 4, runs
    assert _page_hits(hidden) == [], _page_hits(hidden)
    scr = {s['name']: s for s in hidden['pull']['byScreen'].values()}
    assert sorted(scr) == ['SHOWN'], sorted(scr)
    pg.evaluate(HIDE_JS, [])
    again = pg.evaluate(BINDER_JS)
    scr = {s['name']: s for s in again['pull']['byScreen'].values()}
    assert [p['cable'] for p in scr['HID A']['ports']] == ["100' etherCON"] * 4, scr['HID A']['ports']
    cables = [c['cable'] for b in scr['HID A']['boxes'] for c in b['circuits']]
    assert cables and all(c.startswith("10'") for c in cables), cables
    runs = [r for t in _table(again, 'Snakes & home runs') for r in t['rows']]
    assert [r[2] for r in runs if r[0].startswith('XD A') and r[1] == 'cable'].count("100'") == 8, runs
    assert errors == [], errors

