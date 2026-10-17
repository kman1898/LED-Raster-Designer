"""Cable lengths in feet or meters (app-cable-units.js).

Owner rulings, 2026-10-16:

  * BOTH. Preferences > Pull sheet & cables holds "Cable lengths: Feet /
    Meters", the unit a NEW show starts in. Each show keeps its own
    (project.cableUnit), saved with the project; a show with none stored -
    every file saved before the setting - opens in feet.
  * every cable length follows the show's unit: the pull sheet (rows and
    workbook), the binder, the cable tags on the maps, the jumper rows, the
    box cable sheets, the sidebars' fields.
  * lengths are stored as typed. Changing a show's unit keeps every number
    and relabels it (25 ft becomes 25 m) - it asks first when the show holds
    any - and only the long jumpers, which the app measures, are measured
    again.
  * labels: feet keep ' ("Data Jump 2'"), meters print "2 m".
  * rounding is the long jumper's alone: center to center + slack (1 ft /
    0.3 m), up to the stock ladder (3/6/10/15/25 ft, 1/2/3/5/10 m, both
    editable in Preferences), past the top up to the next 5 of the unit.

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_cable_units.py -v --browser chromium
"""

import base64
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)


# ── the server: a new show is stamped, an old one reads feet ─────────────

def test_a_new_show_starts_in_the_preference_unit(client):
    """POST /api/project/new stamps the Preferences' unit on the new show -
    feet when the preferences say nothing. Its screens hold no jumper
    lengths (2026-10-16): they read the set in the show's unit in the page
    (app-jumpers.js screenJumperLengths)."""
    import app as app_module
    jumps = ('dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH')
    app_module.server_preferences = {}
    p = client.post('/api/project/new').get_json()
    assert p['cableUnit'] == 'ft'
    assert not [k for k in jumps if k in p['layers'][0]]
    app_module.server_preferences = {'cableUnit': 'm', 'dataJumpLengthM': 1.5,
                                     'dataJumpLength': 9}
    p = client.post('/api/project/new').get_json()
    assert p['cableUnit'] == 'm'
    assert not [k for k in jumps if k in p['layers'][0]]
    r = client.post('/api/layer/add', json={'name': 'S', 'columns': 2, 'rows': 2,
                                            'cabinet_width': 100, 'cabinet_height': 100})
    assert not [k for k in jumps if k in r.get_json()]


def test_an_old_show_opens_in_feet(client):
    """A file saved before the setting carries no cableUnit: the load keeps
    it that way (nothing is written) and it reads as feet; a show that says
    meters keeps meters through a load."""
    import app as app_module
    proj = client.get('/api/project').get_json()
    proj.pop('cableUnit', None)
    loaded = client.put('/api/project', json=proj).get_json()
    assert 'cableUnit' not in loaded
    assert app_module.cable_unit() == 'ft'
    proj['cableUnit'] = 'm'
    assert client.put('/api/project', json=proj).get_json()['cableUnit'] == 'm'
    assert app_module.cable_unit() == 'm'
    # a stray value is feet
    assert app_module.cable_unit({'cableUnit': 'yards'}) == 'ft'


def test_the_shipped_jumper_literals_agree():
    """The meters shipped jumper length (2 m) is one figure in app-jumpers.js
    and the preferences' defaults."""
    import re
    js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-jumpers.js'), encoding='utf-8').read()
    shipped = int(re.search(r'const JUMPER_SHIPPED_M = (\d+);', js).group(1))
    assert shipped == 2
    prefs_js = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-preferences.js'), encoding='utf-8').read()
    for key in ('powerJumpLengthM', 'powerJumpLengthHM', 'dataJumpLengthM', 'dataJumpLengthHM'):
        assert re.search(rf'\b{key}: {shipped},', prefs_js), key


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")
openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')

from test_power_cables import SEED_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


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
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors, e2e_server
    context.close()


def _seed(pg, unit='ft'):
    """WALL (8 x 12 of 200 px cabinets, 500 mm, one row per circuit) on box
    1 of distro SR; its jumpers V 2 / H 1.5, circuit 1 a 3 cable and
    circuit 2 a 7.5 one, the show in `unit` - written straight onto the
    project, as a file would carry it."""
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    pg.evaluate("""async (unit) => {
        const app = window.app;
        const wall = app.project.layers[0];
        Object.assign(wall, {powerJumpV: 2, powerJumpH: 1.5, dataJumpV: 2, dataJumpH: 1.5});
        app.setCircuitCable(wall, 1, {ft: 3}, false);
        app.setCircuitCable(wall, 2, {ft: 7.5}, false);
        app.updateLayers([wall]);
        app.project.cableUnit = unit;
        delete app.project.pullSheetEdits;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cableUnit: unit, pullSheetEdits: null})});
        app._circuitTailCache = null;
        app.resetHistory('Units Seed');
        app.updateUI();
        app.renderHardwareDock();
    }""", unit)
    pg.wait_for_timeout(500)
    return ids


# Every fillText the power pass paints (cable tags on), interactive.
TAG_TEXTS_JS = """() => {
    const app = window.app, r = window.canvasRenderer, ctx = r.ctx;
    const l = app.project.layers[0];
    l.showPowerCableTags = true;
    const oT = ctx.fillText, texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
    const prev = r.viewMode;
    try { r.viewMode = 'power'; r.render(); } finally { ctx.fillText = oT; r.viewMode = prev; }
    l.showPowerCableTags = false;
    r.render();
    return texts;
}"""

PULL_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    const list = app.buildPullSheet();
    const rows = list.positions.flatMap(p => p.rows);
    return rows.filter(r => /Tru-1/.test(r.type)).map(r => [r.type, r.length, r.qty]);
}"""


def test_the_metric_ladder_and_past_its_top(page):
    """Meters round UP to 1, 2, 3, 5, 10; past 10 to the next 5 m - the
    feet rule in meters. The feet ladder is untouched."""
    pg, errors, _ = page
    table = [(0.2, 1), (1, 1), (1.01, 2), (1.3, 2), (2.5, 3), (3, 3), (3.2, 5), (5, 5),
             (5.5, 10), (10, 10), (10.2, 15), (15, 15), (16, 20)]
    got = pg.evaluate("(xs) => xs.map(x => window.app.jumperStockLength(x, 'm'))", [x for x, _ in table])
    assert got == [w for _, w in table], list(zip(table, got))
    feet = pg.evaluate("() => [2.1, 7, 26].map(x => window.app.jumperStockLength(x, 'ft'))")
    assert feet == [3, 10, 30]
    assert pg.evaluate("() => [window.app.jumperSlack('ft'), window.app.jumperSlack('m')]") == [1, 0.3]
    assert errors == [], errors


def test_a_long_jump_is_measured_in_the_show_s_unit(page):
    """WALL's cabinets are 500 mm: a skip over one cabinet (0,0) -> (0,2)
    is 1000 mm center to center. Feet: 3.28 + 1 = 4.28 -> 6'. Meters: 1.0 +
    0.3 = 1.3 -> 2 m. A short link is the screen's own figure in both."""
    pg, errors, _ = page
    _seed(pg, 'ft')
    js = """() => {
        const app = window.app, l = app.project.layers[0];
        const P = (r, c) => l.panels.find(p => p.row === r && p.col === c);
        const k = app.jumperLink(P(0, 0), l, P(0, 2), l, 'power');
        const s = app.jumperLink(P(0, 0), l, P(1, 0), l, 'power');
        return [k.kind, k.ft, Math.round(k.rawFt * 1000) / 1000, s.kind, s.ft];
    }"""
    assert pg.evaluate(js) == ['long', 6, round(1000 / 304.8 + 1, 3), 'vertical', 2]
    pg.evaluate("() => { window.app.project.cableUnit = 'm'; }")
    assert pg.evaluate(js) == ['long', 2, 1.3, 'vertical', 2]
    assert errors == [], errors


def test_every_surface_prints_the_show_s_unit(page):
    """In a meters show: the circuit cable reads "3 m True1" (the chip, the
    tag, the paperwork), the canvas tags say so, the pull sheet's rows are
    "3 m" / "7.5 m" and the jumpers "2 m" / "1.5 m", the workbook carries
    them (and its GEAR LIST takes them), the binder's power sheet prints
    them in its circuits table and Cables this screen, the box's cable sheet
    and the sidebars' jumper fields say m, the copper warning reads meters.
    The same show in feet reads the way it always has."""
    pg, errors, _ = page
    _seed(pg, 'ft')
    feet = pg.evaluate(PULL_JS)
    assert ['Tru-1', "3'", 1] in feet and ['Tru-1', "7.5'", 1] in feet, feet
    assert any(r[0] == 'Tru-1 Power Jump' and r[1] == "1.5'" for r in feet), feet
    assert "3' True1" in pg.evaluate(TAG_TEXTS_JS)

    _seed(pg, 'm')
    cable = pg.evaluate("() => window.app.powerCircuitCable(window.app.project.layers[0], 1)")
    assert cable['text'] == '3 m True1', cable
    tags = pg.evaluate(TAG_TEXTS_JS)
    assert '3 m True1' in tags and '7.5 m True1' in tags, tags
    assert not [t for t in tags if t.endswith("' True1")], tags
    rows = pg.evaluate(PULL_JS)
    assert ['Tru-1', '3 m', 1] in rows and ['Tru-1', '7.5 m', 1] in rows, rows
    jumps = {r[1] for r in rows if r[0] == 'Tru-1 Power Jump'}
    assert jumps and jumps <= {'2 m', '1.5 m'}, rows
    assert not [r for r in rows if r[1].endswith("'")], rows

    # the workbook: the rows as printed, and the GEAR LIST takes them
    b64 = pg.evaluate("""async () => {
        const app = window.app;
        const list = app.buildPullSheet();
        const resp = await fetch('/api/export/pull-sheet', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pull_list: list, project_name: 'Units', engineer: '', rev: '1.0',
                                  date: '', date_iso: ''})});
        const bytes = new Uint8Array(await resp.arrayBuffer());
        let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000)
            bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        return btoa(bin);
    }""")
    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(b64)))
    import pull_sheet
    ws = wb['Pull Sheet']
    col = pull_sheet.BLOCK_COLS[0]
    block = [tuple(ws.cell(r, col + i).value for i in range(3)) for r in range(7, 40)]
    assert ('Tru-1', '3 m', 1) in block and ('Tru-1', '7.5 m', 1) in block, block
    gear = [wb['GEAR LIST'].cell(r, 2).value for r in range(1, 70)]
    assert '3 m' in gear and '7.5 m' in gear, gear

    # the binder's power sheet
    out = pg.evaluate("""() => {
        const app = window.app;
        const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: true, data: false},
                       scope: {kind: 'show'}, cover: false, pull: true, hardware: false, titleBlock: true };
        const plan = app.planBinder(opts);
        const idx = plan.findIndex(p => /^WALL - Power/.test(p.title));
        const r = app.renderBinderPage(opts, idx);
        return { title: plan[idx].title, texts: r.texts };
    }""")
    texts = out['texts']
    assert '3 m True1' in texts and '7.5 m True1' in texts, (out['title'], texts)
    cables = texts[texts.index('CABLES THIS SCREEN'):]
    assert '3 m' in cables and '1.5 m' in cables, cables
    assert not [t for t in texts if t.endswith("' True1") or t in ("3'", "1.5'", "2'")], texts

    # the box's cable sheet and the sidebars
    dock = pg.evaluate("""(distroId) => {
        const app = window.app;
        app._setCableSheetOpen(distroId, 1, true);
        app.renderHardwareDock();
        const sheet = document.querySelector('.hw-dock-cablesheet');
        const out = {
            unit: sheet ? sheet.querySelector('tr .hw-dock-cable-ft').parentElement.textContent.trim() : null,
            title: sheet ? sheet.querySelector('tr .hw-dock-cable-ft').title : null,
            fills: sheet ? [...sheet.querySelectorAll('.hw-dock-cable-quick button')].map(b => b.textContent) : [],
            any: sheet ? sheet.querySelector('.hw-dock-cable-quick input').placeholder : null,
            jumpUnit: document.querySelector('#power-jump-v + span').textContent,
            jumpAria: document.getElementById('power-jump-v').getAttribute('aria-label'),
            jumpTip: document.getElementById('power-jump-v').closest('[data-tooltip]').dataset.tooltip,
        };
        app._setCableSheetOpen(distroId, 1, false);
        app.renderHardwareDock();
        return out;
    }""", _distro_id(pg))
    assert dock['unit'] == 'm' and dock['title'] == 'Length in meters. Blank = no cable.', dock
    assert dock['fills'][:3] == ['all 3 m', 'all 2 m', 'none'], dock
    assert dock['any'] == 'm', dock
    assert dock['jumpUnit'] == 'm' and dock['jumpAria'] == 'Power jumper vertical length (m)', dock
    assert 'in meters' in dock['jumpTip'] and 'plus 0.3 m' in dock['jumpTip'], dock

    # the data side's run texts: a snake and its extension, the tag
    data = pg.evaluate("""() => [
        window.app.runText({kind: 'snake', snake: {name: 'SR', ft: 30}, ext: 5}),
        window.app.snakeTagText({name: 'SNAKE A', ft: 30, members: [{}, {}]}),
        window.app.pullLengthText('EA')]""")
    assert data[0] == 'SR 30 m +5 m' and data[1].endswith(' · 30 m') and data[2] == 'EA', data

    over = pg.evaluate("""() => [window.app.copperOverText({copper: 'Cat6', ft: 31}),
                                window.app.copperOverText({copper: 'Cat6', ft: 30}),
                                window.app.copperOverText({copper: 'Cat6A', ft: 61})]""")
    assert over == ['Cat6 runs 30.48 m max at 10G', '', 'Cat6A runs 60 m max at 10G'], over
    assert errors == [], errors


def _distro_id(pg):
    return pg.evaluate("() => window.app.getDistros()[0].id")


def test_changing_the_unit_keeps_every_number_and_asks_first(page):
    """The export dialog's Cable lengths select (Pull Sheet and Binder
    sections - one setting): on a show holding typed lengths it asks first,
    and No changes nothing. Yes relabels: the stored numbers are the same
    (3 stays 3, the jumpers 2 / 1.5), the papers say m, a pull-sheet edit
    keyed "Tru-1|3'" follows its row to "Tru-1|3 m", one undo step that the
    server holds - and undo puts feet back."""
    pg, errors, _ = page
    _seed(pg, 'ft')
    pg.evaluate("""() => {
        const app = window.app;
        app.project.pullSheetEdits = {positions: {x: {rows: [{key: "Tru-1|3'", notes: 'spare'}],
                                                       added: [{type: 'Tru-1', length: "25'", qty: 2}]}}};
    }""")
    asked = []

    def no(d):
        asked.append(d.message)
        d.dismiss()
    pg.once('dialog', no)
    pg.evaluate("() => { window.app.openExportModal ? window.app.openExportModal() : null; }")
    pg.evaluate("""() => { const s = document.getElementById('export-pull-sheet-cable-unit');
                          s.value = 'm'; s.dispatchEvent(new Event('change')); }""")
    pg.wait_for_timeout(300)
    assert asked and '25 ft becomes 25 m' in asked[0] and 'meters' in asked[0], asked
    st = pg.evaluate("() => [window.app.cableUnit(), document.getElementById('export-pull-sheet-cable-unit').value]")
    assert st == ['ft', 'ft'], st

    pg.once('dialog', lambda d: d.accept())
    pg.evaluate("""() => { const s = document.getElementById('export-binder-cable-unit');
                          s.value = 'm'; s.dispatchEvent(new Event('change')); }""")
    pg.wait_for_timeout(600)
    st = pg.evaluate("""async () => {
        const app = window.app, l = app.project.layers[0];
        const srv = await (await fetch('/api/project')).json();
        return { unit: app.cableUnit(), both: [...document.querySelectorAll('select.cable-unit-select')].map(s => s.value),
                 cables: l.powerCircuitCables, jumps: [l.powerJumpV, l.powerJumpH],
                 edits: app.project.pullSheetEdits.positions.x,
                 action: app.history[app.historyIndex].action,
                 served: srv.cableUnit, servedEdits: srv.pullSheetEdits };
    }""")
    # every unit select: the export dialog's two and the Data and Power
    # sidebars' beside the jumper fields (2026-10-17)
    assert st['unit'] == 'm' and st['both'] == ['m'] * 4, st
    assert st['cables']['1']['ft'] == 3 and st['cables']['2']['ft'] == 7.5, st
    assert st['jumps'] == [2, 1.5], st
    assert st['edits']['rows'][0]['key'] == 'Tru-1|3 m', st
    assert st['edits']['added'][0]['length'] == '25 m', st
    assert st['action'] == 'Set Cable Lengths Unit' and st['served'] == 'm', st
    assert st['servedEdits']['positions']['x']['rows'][0]['key'] == 'Tru-1|3 m', st

    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    back = pg.evaluate("() => [window.app.cableUnit(), document.querySelector('#power-jump-v + span').textContent]")
    assert back == ['ft', 'ft'], back
    # a show with no typed length changes without asking
    pg.evaluate("() => { window.app.project.layers.forEach(l => { l.powerCircuitCables = {};"
                " ['dataJumpV','dataJumpH','powerJumpV','powerJumpH'].forEach(k => { l[k] = null; }); }); }")
    assert pg.evaluate("() => window.app.typedCableLengthCount()") == 0
    assert pg.evaluate("() => window.app.setCableUnit('m')") is True
    assert errors == [], errors


def test_the_show_s_unit_rides_a_reload_and_an_old_show_reads_feet(page):
    """Set on the show, the unit is the server's project: a reload opens in
    meters, labels and all. An old show - no cableUnit - loads in feet."""
    pg, errors, url = page
    _seed(pg, 'ft')
    pg.evaluate("() => window.app.setCableUnit('m', false)")
    pg.wait_for_timeout(500)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    st = pg.evaluate("() => [window.app.cableUnit(), window.app.project.cableUnit,"
                     " document.querySelector('#data-jump-v + span').textContent]")
    assert st == ['m', 'm', 'm'], st
    pg.evaluate("""async () => {
        const proj = await (await fetch('/api/project')).json();
        delete proj.cableUnit;
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                     body: JSON.stringify(proj)});
    }""")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    st = pg.evaluate("() => [window.app.cableUnit(), 'cableUnit' in window.app.project,"
                     " document.querySelector('#data-jump-v + span').textContent,"
                     " window.app.pullLengthText(25)]")
    assert st == ['ft', False, 'ft', "25'"], st
    assert errors == [], errors


def test_the_stock_ladders_are_preferences(page):
    """Preferences > Pull sheet & cables: the two ladders as lists. A typed
    list is stored ascending and once each, and the long jumper rounds to
    it (past its top, the next 5); text that is no list keeps the stored
    one; Reset Defaults brings the shipped ladders back."""
    pg, errors, _ = page
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")
    shown = pg.evaluate("() => [document.getElementById('pref-jumper-stock-ft').value,"
                        " document.getElementById('pref-jumper-stock-m').value]")
    assert shown == ['3, 6, 10, 15, 25', '1, 2, 3, 5, 10'], shown
    pg.fill('#pref-jumper-stock-ft', '12, 4 8')
    pg.fill('#pref-jumper-stock-m', '1.5; 0.5, 1.5, 4')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert served['jumperStockFt'] == [4, 8, 12] and served['jumperStockM'] == [0.5, 1.5, 4], served
    got = pg.evaluate("""() => [[3, 5, 12, 13].map(x => window.app.jumperStockLength(x, 'ft')),
                                [0.4, 1, 3, 4.1].map(x => window.app.jumperStockLength(x, 'm'))]""")
    assert got == [[4, 8, 12, 15], [0.5, 1.5, 4, 5]], got
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")
    assert pg.evaluate("() => document.getElementById('pref-jumper-stock-ft').value") == '4, 8, 12'
    pg.fill('#pref-jumper-stock-ft', 'six, ten')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert served['jumperStockFt'] == [4, 8, 12], served
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")
    pg.once('dialog', lambda d: d.accept())
    pg.click('#preferences-reset')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert served['jumperStockFt'] == [3, 6, 10, 15, 25] and served['jumperStockM'] == [1, 2, 3, 5, 10]
    assert served['cableUnit'] == 'ft'
    assert errors == [], errors


def test_a_new_show_takes_the_preference_unit_and_its_lengths(page):
    """Preferences: Cable lengths Meters, the meters jumper set 1 / 1.5 and
    the meters power cable 4. File > New: the show is meters, its screen's
    jumpers the meters set, the box sheet's quick fill 4 m. Back to Feet:
    the next new show is feet, 6' jumpers. The open show never changes."""
    pg, errors, _ = page
    _seed(pg, 'ft')
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")
    pg.select_option('#pref-cable-unit', 'm')
    pg.fill('#pref-pull-data-jump-length-m', '1')
    pg.fill('#pref-pull-data-jump-length-h-m', '1.5')
    pg.fill('#pref-power-cable-length-m', '4')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert (served['cableUnit'], served['dataJumpLengthM'], served['dataJumpLengthHM'],
            served['powerCableM'], served['dataJumpLength']) == ('m', 1, 1.5, 4, 6), served
    # the open show is not a new one: it stays in feet
    assert pg.evaluate("() => window.app.cableUnit()") == 'ft'
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    st = pg.evaluate("""() => { const app = window.app, l = app.project.layers[0];
        const j = app.screenJumperLengths(l);
        return [app.project.cableUnit, j.data.v, j.data.h, j.power.v,
                app.defaultPowerCableFt(), document.querySelector('#data-jump-v + span').textContent]; }""")
    assert st == ['m', 1, 1.5, 2, 4, 'm'], st
    pg.evaluate("() => { window.app.openPreferencesModal(); window.app.showPreferencesTab('pull'); }")
    pg.select_option('#pref-cable-unit', 'ft')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    st = pg.evaluate("""() => { const app = window.app, l = app.project.layers[0];
        const j = app.screenJumperLengths(l);
        return [app.project.cableUnit, j.data.v, j.power.h, app.defaultPowerCableFt()]; }""")
    assert st == ['ft', 6, 6, 10], st
    assert errors == [], errors
