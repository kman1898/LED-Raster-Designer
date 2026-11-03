"""Pull sheet labels, edits that reach the binder, distro feeders and a
cable stock list per kind (owner rulings, 2026-10-21).

  * A box's rows on the pull sheet are labelled by the box's OWN name
    ("SR1", "DISTRO 1-1"), never the distro's name glued to the number
    ("DISTRO 11").
  * Name folding folds only a true run of numbered siblings sharing a
    prefix: a lone name is listed as typed ("SR 13x5", "CVT10"), a number
    is never cut out of a token like "13x5", and a dashed run of three or
    more reads "DISTRO 1-1 … 1-7".
  * A pull-sheet edit reaches the binder's per-screen CABLES THIS SCREEN
    tables and the hardware pull lists: a hidden row comes off every screen
    and sheet it was counted on; a changed count goes to a screen (or a
    sheet) only where the row maps 1:1 - every cable it counts came from
    that one screen. Free rows stay on the pull pages.
  * Each distro has a FEEDER behind its gear: a length (blank prints "no
    length") and where it is fed from - the service, or another distro
    (cam thru). The row follows the distro's input: "400 A cam set" with
    "5-wire" in Notes, "L21-30 feed", or "Feed" with no input. It is
    saved with the show and survives the server.
  * The cable stock keeps a list for L21-30 home runs, Harting home runs,
    direct-output cables and feeders beside multis, data and power; a show
    or preset saved before reads them from the lists those cables used.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_pull_feeders_and_edits.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the server ────────────────────────────────────────────────────────────

def test_the_server_keeps_a_feeder_and_clears_what_names_nothing(client):
    """A distro's feeder rides the project POST as typed; a feeder that is
    not a dict is dropped, a `from` naming no other distro is cleared, and
    a feeder left empty is dropped like one never set."""
    import app as app_module
    distros = [
        {'id': 'd1', 'name': 'SR', 'ratingA': 400, 'feeder': {'ft': 150, 'from': 'd2'}},
        {'id': 'd2', 'name': 'SL', 'ratingA': 400, 'feeder': {'ft': 50, 'from': 'd2'}},
        {'id': 'd3', 'name': 'FOH', 'ratingA': 200, 'feeder': 'cam'},
        {'id': 'd4', 'name': 'UP', 'ratingA': 200, 'feeder': {'from': 'gone'}},
    ]
    assert client.post('/api/project', json={'distros': distros}).status_code == 200
    got = {d['id']: d.get('feeder') for d in app_module.current_project['distros']}
    assert got == {'d1': {'ft': 150, 'from': 'd2'}, 'd2': {'ft': 50}, 'd3': None, 'd4': None}, got
    # a restore (undo, a file open) runs the same funnel
    proj = client.get('/api/project').get_json()
    proj['distros'] = [{'id': 'd1', 'name': 'SR', 'ratingA': 400, 'feeder': {'ft': 75, 'from': 'd9'}}]
    client.put('/api/project', json=proj)
    assert app_module.current_project['distros'][0]['feeder'] == {'ft': 75}


def test_presets_saved_before_the_new_lists_read_the_old_ones(client):
    """normalize_stock: an L21-30 or Harting list a preset never had reads
    its multi list, a direct-output list its circuit list; feeders start
    empty. A list that is there - empty or not - is the kind's own."""
    import routes_cable_stock as rcs
    s = rcs.normalize_stock({'perKind': True, 'ft': {'multi': [25, 50], 'circuit': [10, 25]}})
    assert s['ft']['l2130'] == [25, 50] and s['ft']['harting'] == [25, 50]
    assert s['ft']['direct'] == [10, 25] and s['ft']['feeder'] == []
    s = rcs.normalize_stock({'perKind': True, 'ft': {'multi': [25], 'harting': [], 'feeder': [100]}})
    assert s['ft']['harting'] == [] and s['ft']['l2130'] == [25] and s['ft']['feeder'] == [100]
    assert rcs.normalize_stock({'ft': {'feeder': ['x']}}) is None


def test_the_preferences_offer_a_list_per_kind(client):
    html = client.get('/').get_data(as_text=True)
    for kind in ('multi', 'data', 'circuit', 'l2130', 'harting', 'direct', 'feeder'):
        for unit in ('ft', 'm'):
            assert f'id="pref-cable-stock-{kind}-{unit}"' in html, (kind, unit)
        assert f'data-cable-stock-list="{kind}"' in html, kind


# ── the browser ───────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_pull_list import SEED_JS, LIST_JS  # noqa: E402


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    yield pg, ids, errors
    context.close()


def _rows(rows):
    return [(r['type'], r['length'], r['qty'], r['label'], r['notes']) for r in rows]


SHEET_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullSheet()));
}"""


def _reset(pg, distro_id):
    """No edits, no stock, SR alone and as seeded."""
    pg.evaluate("""async (id) => {
        const app = window.app;
        delete app.project.pullSheetEdits;
        delete app.project.cableStock;
        const d = app.getDistros().find(x => x.id === id);
        d.name = 'SR';
        delete d.feeder; delete d.input; delete d.boxTypes;
        app.project.distros = app.getDistros().filter(x => x.id === id);
        app._circuitTailCache = null;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pullSheetEdits: {positions: {}}, cableStock: null,
                                  distros: app.project.distros})});
        app.resetHistory('Pull Audit Reset');
    }""", distro_id)


@pytest.fixture()
def seeded(page):
    """The seeded page, put back as seeded after the test."""
    yield page
    pg, ids, _ = page
    _reset(pg, ids['distroId'])


def test_lone_names_stay_whole_and_only_runs_fold(seeded):
    pg, ids, errors = seeded
    cases = [
        (['SR 13x5'], 'SR 13x5'),
        (['IMAG SR 19x11'], 'IMAG SR 19x11'),
        (['9x5'], '9x5'),
        (['Floor H2'], 'Floor H2'),
        (['Delay Vx1000'], 'Delay Vx1000'),
        (['CVT10'], 'CVT10'),
        (['SR1'], 'SR1'),
        (['SR 13x5', 'SR 13x6'], 'SR 13x5, SR 13x6'),
        (['SR1', 'SR2', 'SR3', 'SR4'], 'SR 1-4'),
        (['SR1', 'SR2', 'SR5'], 'SR 1-2, 5'),
        (['SR1', 'SR5'], 'SR1, SR5'),
        (['CVT10', 'SR1', 'SR2'], 'CVT10, SR 1-2'),
        ([f'DISTRO 1-{n}' for n in range(1, 8)], 'DISTRO 1-1 … 1-7'),
        (['DISTRO 1-1', 'DISTRO 1-2'], 'DISTRO 1-1, DISTRO 1-2'),
        (['SR1-1', 'SR1-2'], 'SR1-1, SR1-2'),
        (['SR1-1', 'SR1-2', 'SR1-3', 'SR2-1'], 'SR1-1 … 1-3, SR2-1'),
        (['SR-1', 'SR-2'], 'SR-1, SR-2'),
        # two names whose prefixes differ are two names, never a run
        # (QA 1.6.0: "Screen1" and "Screen 2" read "Screen 1-2")
        (['Screen1', 'Screen 2'], 'Screen1, Screen 2'),
        (['Screen 1', 'Screen 2'], 'Screen 1-2'),
        (['Screen1', 'Screen2'], 'Screen 1-2'),
        (['WALL-A'], 'WALL-A'),
    ]
    got = pg.evaluate("(cases) => cases.map(c => window.app._pullCompressNames(c))", [c for c, _ in cases])
    assert got == [w for _, w in cases], [(c, g, w) for (c, w), g in zip(cases, got) if g != w]
    assert errors == [], errors


def test_a_box_is_labelled_by_its_own_name(seeded):
    """A distro whose name ends in a digit ("DISTRO 1") names its boxes
    DISTRO 1-1 and DISTRO 1-2: the Multi, Breakout and hardware rows say
    that - never "DISTRO 11" / "DISTRO 12" or a folding of them."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(id) => {
        const app = window.app;
        app.getDistros().find(x => x.id === id).name = 'DISTRO 1';
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullList()));
    }""", ids['distroId'])
    rows = _rows(out['positions'][0]['rows'])
    assert ('Multi', "125'", 1, 'DISTRO 1-1', '') in rows, rows
    assert ('Multi', "100'", 1, 'DISTRO 1-2', '') in rows, rows
    assert ('TRUE1 Breakout', 'EA', 2, 'DISTRO 1-1, DISTRO 1-2', '') in rows, rows
    assert not [r for r in rows if 'DISTRO 11' in r[3] or 'DISTRO 12' in r[3]], rows
    hw = next(h for h in out['hardware'] if h['kind'] == 'distro')
    assert ('Multi', "125'", 1, 'DISTRO 1-1', '') in _rows(hw['rows'])
    assert errors == [], errors


def test_only_a_name_two_boxes_share_takes_a_suffix(seeded):
    """Owner, 2026-10-21: "should be only listing the distros by name, if
    there happen to be 2 of the exact same name, then you can use a -1
    etc". Each box is its own name on the pull sheet, SR's pull list and
    the binder's distro table ("SR1", "SR2" - never "SR 1"); two boxes
    typed the same name ("MAIN") are MAIN-1 and MAIN-2, in box order."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const caught = [];
        const table = () => {
            caught.length = 0;
            const orig = app._bDistroBlocks;
            app._bDistroBlocks = function (book, d, load, boxes) {
                caught.push(...boxes.map(b => b.cells[0]));
                return orig.apply(this, arguments);
            };
            try {
                app.planBinder(Object.assign(app.readBinderOptions(),
                    { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
            } finally { app._bDistroBlocks = orig; }
            return caught.slice();
        };
        const labels = () => {
            app._circuitTailCache = null;
            const l = app.buildPullList();
            const hw = l.hardware.find(h => h.kind === 'distro');
            return { pull: l.positions[0].rows.filter(r => r.type === 'Multi').map(r => r.label),
                     hw: hw.rows.filter(r => r.type === 'Multi').map(r => r.label), table: table() };
        };
        const plain = labels();
        const a = app.project.layers.find(l => l.id === ids.a);
        const b = app.project.layers.find(l => l.id === ids.b);
        a.powerSocaNames = { 1: 'MAIN' };
        b.powerSocaNames = { 1: 'MAIN' };
        const twins = labels();
        delete a.powerSocaNames; delete b.powerSocaNames;
        app._circuitTailCache = null;
        return { plain, twins };
    }""", ids)
    assert sorted(out['plain']['pull']) == ['SR1', 'SR2'], out
    assert sorted(out['plain']['hw']) == ['SR1', 'SR2'], out
    assert out['plain']['table'] == ['SR1', 'SR2'], out
    assert sorted(out['twins']['pull']) == ['MAIN-1', 'MAIN-2'], out
    assert sorted(out['twins']['hw']) == ['MAIN-1', 'MAIN-2'], out
    assert out['twins']['table'] == ['MAIN-1', 'MAIN-2'], out
    assert errors == [], errors


def test_edits_reach_the_screens_and_the_hardware(seeded):
    """On SR Beach (WALL-A and WALL-B): hiding WALL-A's Multi 125' takes it
    off WALL-A's table and SR's pull list; WALL-A's TRUE1 10' x 2 set to 5
    is WALL-A's alone, so its table says 5; the Breakout x 2 (one from each
    wall) set to 3 leaves both walls' tables as they were but SR's pull
    list, the one sheet both came from, says 3. A free row is on the pull
    page only. The engine's own reading is untouched."""
    pg, ids, errors = seeded
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        app._circuitTailCache = null;
        const engine = JSON.stringify(app.buildPullList());
        app.removePullSheetRow('g1', "Multi|125'");
        app.setPullSheetRowEdit('g1', "TRUE1|10'", { qty: 5 });
        app.setPullSheetRowEdit('g1', 'TRUE1 Breakout|EA', { qty: 3 });
        app.addPullSheetRow('g1', { type: 'Spare Widget', length: 'EA', qty: 2 });
        app._circuitTailCache = null;
        const sheet = JSON.parse(JSON.stringify(app.buildPullSheet()));
        const row = (rows, t, l) => (rows.find(r => r.type === t && r.length === l) || {}).qty || 0;
        const a = sheet.byScreen[ids.a], b = sheet.byScreen[ids.b];
        const sr = sheet.hardware.find(h => h.kind === 'distro');
        const sum = (rows, t, l) => rows.filter(r => r.type === t && r.length === l)
            .reduce((n, r) => n + r.qty, 0);
        app._circuitTailCache = null;
        return {
            same: JSON.stringify(app.buildPullList()) === engine,
            a: { multi: row(a.rows, 'Multi', "125'"), tru: row(a.rows, 'TRUE1', "10'"),
                 brk: row(a.rows, 'TRUE1 Breakout', 'EA'),
                 onMulti: sum(a.rowsOn, 'Multi', "125'"), onTru: sum(a.rowsOn, 'TRUE1', "10'"),
                 widget: row(a.rows, 'Spare Widget', 'EA') },
            b: { multi: row(b.rows, 'Multi', "100'"), brk: row(b.rows, 'TRUE1 Breakout', 'EA') },
            sr: { m125: row(sr.rows, 'Multi', "125'"), m100: row(sr.rows, 'Multi', "100'"),
                  brk: row(sr.rows, 'TRUE1 Breakout', 'EA') },
            totals: { brk: row(sheet.totals, 'TRUE1 Breakout', 'EA'), tru: row(sheet.totals, 'TRUE1', "10'"),
                      widget: row(sheet.totals, 'Spare Widget', 'EA'), m125: row(sheet.totals, 'Multi', "125'") },
        };
    }""", ids)
    assert out['same'], 'the engine was written'
    assert out['a'] == {'multi': 0, 'tru': 5, 'brk': 1, 'onMulti': 0, 'onTru': 5, 'widget': 0}, out['a']
    assert out['b'] == {'multi': 1, 'brk': 1}, out['b']
    assert out['sr'] == {'m125': 0, 'm100': 1, 'brk': 3}, out['sr']
    assert out['totals'] == {'brk': 3, 'tru': 5, 'widget': 2, 'm125': 0}, out['totals']

    # the binder's CABLES THIS SCREEN table for WALL-A and SR's Pull list
    texts = pg.evaluate("""(ids) => {
        const app = window.app;
        const opts = Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false,
              sides: { power: true, data: false } });
        const book = app._binderBook(opts, { dry: true });
        const wallA = app.project.layers.find(l => l.id === ids.a);
        const rows = app._bSubjectRows(book, { kind: 'screen', layers: [wallA] }, 'power');
        return rows.map(r => [r.type, r.length, r.qty]);
    }""", ids)
    assert ['TRUE1', "10'", 5] in texts and not [t for t in texts if t[0] == 'Multi'], texts
    assert errors == [], errors


def test_a_distro_s_feeder_on_the_pull_sheet(seeded):
    """No input, no length: "Feed", "no length", under the distro where it
    sits and on its own pull list. A 400 A cam input with 150 typed: ONE
    "400 A cam set" row, 150', "5-wire". On a feeder stock of 50 / 100 it
    is pulled as a 100' and a 50'. An L21-30 input: "L21-30 feed"."""
    pg, ids, errors = seeded
    did = ids['distroId']
    base = pg.evaluate(LIST_JS)
    sr = _rows(base['positions'][0]['rows'])
    assert ('Power in', '', 1, 'SR', 'no length') in sr, sr
    hw = _rows(next(h for h in base['hardware'] if h['kind'] == 'distro')['rows'])
    assert ('Power in', '', 1, 'SR', 'no length') in hw, hw

    out = pg.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros().find(x => x.id === id);
        d.system = '120/208'; d.voltage = 208; d.phase = 3;
        d.input = 'cam400';
        const n0 = app.history.length;
        const changed = app.setDistroFeeder(id, { ft: '150' });
        const again = app.setDistroFeeder(id, { ft: 150 });
        const step = app.history[app.historyIndex].action;
        app._circuitTailCache = null;
        const one = JSON.parse(JSON.stringify(app.buildPullList()));
        app.project.cableStock = { perKind: true, ft: { feeder: [50, 100], multi: [] }, m: {} };
        app._circuitTailCache = null;
        const pieces = JSON.parse(JSON.stringify(app.buildPullList()));
        delete app.project.cableStock;
        d.input = 'l2130';
        app._circuitTailCache = null;
        const l2130 = JSON.parse(JSON.stringify(app.buildPullList()));
        return { changed, again, steps: app.history.length - n0, step, stored: d.feeder,
                 one: one.positions[0].rows, pieces: pieces.positions[0].rows,
                 totals: pieces.totals, l2130: l2130.positions[0].rows };
    }""", did)
    assert out['changed'] is True and out['again'] is False and out['steps'] == 1, out
    assert out['step'] == 'Set Distro Power In' and out['stored'] == {'ft': 150}, out
    assert ('400 A cam set', "150'", 1, 'SR', '5-wire') in _rows(out['one']), _rows(out['one'])
    assert not [r for r in _rows(out['one']) if r[0] == 'Power in'], 'the old blank row stayed'
    cams = sorted((r[1], r[2]) for r in _rows(out['pieces']) if r[0] == '400 A cam set')
    assert cams == [("100'", 1), ("50'", 1)], _rows(out['pieces'])
    assert ('L21-30 power in', "150'", 1, 'SR', '') in _rows(out['l2130']), _rows(out['l2130'])
    assert errors == [], errors


def test_the_preferences_say_feeds_never_feeders(client):
    """The cable that powers a distro is its FEED (owner, 2026-11-01): the
    Preferences > Cable stock row reads "Feeds" and its fields' tooltips
    say "Feed lengths"; the list's id and key stay 'feeder'."""
    html = client.get('/').get_data(as_text=True)
    row = html[html.index('data-cable-stock-list="feeder"'):]
    row = row[:row.index('</div>', row.index('pref-cable-stock-feeder-m'))]
    assert '<label>Power in cables</label>' in row, row
    assert 'Power in cable lengths in feet' in row and 'Power in cable lengths in meters' in row, row
    assert 'Feeder' not in row and ' feeder ' not in row, row
    assert 'direct-output cables and power in cables."' in html


def test_the_feed_row_its_gear_and_old_feeder_edits(seeded):
    """The pull row and the distro gear say "Feed"; a pull-sheet edit kept
    on an old "Feeder" / "L21-30 feeder" row answers to the feed row; a
    free row's "feed" is power unless a data word says otherwise, and
    "feedback" is not a feed."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros().find(x => x.id === id);
        const row = app.pullFeederRow(d);
        const wrap = document.createElement('div');
        app._buildDistroFeederRow(d, wrap);
        const titles = [...wrap.querySelectorAll('[title]')].map(e => e.title).join(' ');
        return {
            type: row.type,
            cap: wrap.textContent,
            titles,
            keys: ["Feeder|50'", "L21-30 feeder|EA", "Feedback|EA", "Feed|50'"].map(k => app.pullEditKey(k)),
            sides: ['Power in', 'L21-30 power in', 'Feed', 'SDI feed', 'Feeder'].map(t => app.pullGuessSide(t)),
        };
    }""", ids['distroId'])
    assert out['type'] == 'Power in', out
    assert 'Power in' in out['cap'] and 'Feed' not in out['cap'], out
    assert 'feed' not in out['titles'].lower() and 'Where the power in comes from' in out['titles'], out
    assert out['keys'] == ["Power in|50'", "L21-30 power in|EA", "Feedback|EA", "Power in|50'"], out
    assert out['sides'] == ['power', 'power', 'power', 'data', 'power'], out
    assert errors == [], errors


def test_fed_from_another_distro_and_the_server_round_trip(seeded):
    """SR fed thru from SL: stored, sent and served; SL cannot then be fed
    from SR (no loop). The binder's distro block reads "Fed from SL, cam
    thru · 400 A cam set 150'". SL removed: the server clears the `from`,
    and SR reads as fed from the service again."""
    pg, ids, errors = seeded
    did = ids['distroId']
    out = pg.evaluate("""async (id) => {
        const app = window.app;
        const d = app.getDistros().find(x => x.id === id);
        d.system = '120/208'; d.voltage = 208; d.phase = 3; d.input = 'cam400';
        const sl = app.addDistro({ name: 'SL', system: '120/208' });
        app.setDistroFeeder(id, { ft: 150, from: sl.id });
        const stored = JSON.parse(JSON.stringify(d.feeder));
        const loop = app.setDistroFeeder(sl.id, { from: id });
        const sources = app.feederSources(sl).map(x => x.id);
        await app._distroPushQueue;
        const served = (await (await fetch('/api/project')).json()).distros.find(x => x.id === id).feeder;
        const caught = [];
        const orig = app._bKvLines;
        app._bKvLines = function (book, title, pairs) {
            if (title === 'Distro') caught.push(pairs.map(p => p.slice()));
            return orig.apply(this, arguments);
        };
        try {
            const opts = Object.assign(app.readBinderOptions(),
                { scope: { kind: 'show' }, hardware: true, pull: false, cover: false });
            app.planBinder(opts);
        } finally { app._bKvLines = orig; }
        const block = caught.map(p => Object.fromEntries(p)).find(p => p.Circuits);
        app.removeDistro(sl.id);
        await app._distroPushQueue;
        const after = (await (await fetch('/api/project')).json()).distros.find(x => x.id === id).feeder;
        return { slId: sl.id, stored, loop, sources, served, fed: block && block['Powered from'],
                 after, client: d.feeder, source: app.feederSourceText(d), text: app.feederText(d) };
    }""", did)
    assert out['stored']['from'] == out['slId'] and out['served'] == {'ft': 150, 'from': out['slId']}, out
    assert out['loop'] is False and did not in out['sources'], out
    assert out['fed'] == "SL, cam thru · 400 A cam set 150'", out
    # the removal clears it in the page too (2026-10-21), not only the server
    assert out['after'] == {'ft': 150} and out['client'] == {'ft': 150}, out
    assert out['source'] is None and out['text'] == "400 A cam set 150'", out
    assert errors == [], errors


def test_the_gear_sets_the_feeder(seeded):
    """Behind the distro's gear: a FEEDER row with its length and a Fed from
    pick (the service, or thru another distro). Each change is one undo
    step."""
    pg, ids, errors = seeded
    did = ids['distroId']
    pg.evaluate("() => { window.app.renderHardwareDock(); }")
    pg.wait_for_timeout(300)
    up = pg.evaluate("""(popId) => {
        const gear = document.querySelector(`[data-hwpop="${popId}"]`);
        if (!gear) return false;
        gear.scrollIntoView({ block: 'center' });
        gear.click();
        const pop = document.getElementById('hw-gear-popover');
        return !!(pop && pop.style.display !== 'none');
    }""", f'distro-{did}')
    assert up, 'the distro gear did not open'
    ft = f'#hw-gear-popover [data-lrd-field="distro-feeder-ft-{did}"]'
    src = f'#hw-gear-popover [data-lrd-field="distro-feeder-from-{did}"]'
    assert pg.locator(ft).count() == 1 and pg.locator(src).count() == 1
    # SR is on no service: the first pick says so, not "from the service"
    assert pg.locator(src).locator('option').first.text_content() == 'Powered from: none'
    n0 = pg.evaluate("() => window.app.history.length")
    pg.locator(ft).fill('80')
    pg.locator(ft).dispatch_event('change')
    pg.wait_for_timeout(300)
    st = pg.evaluate("(id) => [window.app.getDistros().find(x => x.id === id).feeder, "
                     "window.app.history.length, window.app.history[window.app.historyIndex].action]", did)
    assert st[0] == {'ft': 80} and st[1] == n0 + 1 and st[2] == 'Set Distro Power In', st
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(500)
    assert pg.evaluate("(id) => window.app.getDistros().find(x => x.id === id).feeder || null", did) is None
    pg.evaluate("() => window.app._hwPopoverClose && window.app._hwPopoverClose()")
    assert errors == [], errors


def test_each_kind_reads_its_own_stock_list(seeded):
    """An L21-30 box's home run is pulled from the L21-30 list, a multi's
    from the multi list; a direct output's cable is a 'direct' run. A
    per-kind stock saved before the new lists reads the L21-30 and Harting
    lists from its multi list and the direct list from its circuit list;
    one list for everything covers every kind."""
    pg, ids, errors = seeded
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros().find(x => x.id === id);
        d.boxTypes = { 1: 'l2130' };
        app.project.cableStock = { perKind: true, ft: { multi: [100], l2130: [25, 100] }, m: {} };
        app._circuitTailCache = null;
        const own = app.buildPullList().totals.map(r => [r.type, r.length, r.qty]);
        app.project.cableStock = { perKind: true, ft: { multi: [50], circuit: [10, 25] }, m: {} };
        app._circuitTailCache = null;
        const old = app.buildPullList().totals.map(r => [r.type, r.length, r.qty]);
        const lists = ['l2130', 'harting', 'direct', 'feeder'].map(k => app.cableStockList(k, 'ft'));
        app.project.cableStock = { perKind: false, ft: { all: [50, 100] }, m: {} };
        const all = ['multi', 'l2130', 'harting', 'direct', 'feeder', 'circuit', 'data']
            .map(k => app.cableStockText(150, k));
        delete d.boxTypes;
        return { own, old, lists, all,
                 kinds: [app.pullHomeRunKind({ kind: 'direct' }), app.pullHomeRunKind({ conn: { id: 'harting' } }),
                         app.pullHomeRunKind({ typeId: 'l2130' }), app.pullHomeRunKind({ kind: 'multi' }),
                         app.pullHomeRunKind(null)] };
    }""", ids['distroId'])
    own = sorted((r[1], r[2]) for r in out['own'] if r[0] == 'L21-30')
    assert own == [("100'", 1), ("25'", 1)], out['own']
    assert sorted((r[1], r[2]) for r in out['own'] if r[0] == 'Multi') == [("100'", 1)], out['own']
    # the old per-kind stock: the L21-30 run reads the multi list (50s)
    assert sorted((r[1], r[2]) for r in out['old'] if r[0] == 'L21-30') == [("50'", 3)], out['old']
    assert out['lists'] == [[50], [50], [10, 25], []], out['lists']
    assert out['all'] == ["100'+50'"] * 7, out['all']
    assert out['kinds'] == ['direct', 'harting', 'l2130', 'multi', 'multi'], out['kinds']
    assert errors == [], errors
