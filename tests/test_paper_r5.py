"""Binder and pull-sheet paperwork, round 5 (owner rulings, 2026-10-23).

  * A group routed as one that can't fit a circuit at 80%: its power
    sheet (the group's, or each member's) prints the owner's note in
    Circuits and "no circuits, cannot fit" in CABLES THIS SCREEN, no
    wiring sheet, and the export warning names the GROUP with its screens.
    Where one panel alone is over the circuit, the warning says no pattern
    helps.
  * A distro with nothing at all is off the Service sheet (row, ratings
    total, count) and the Overview's Distros count.
  * Hidden screens are left out of the distro sheet's boxes, its counts
    and Circuits, and of the Service sheet.
  * Bracket labels on a dense map stay inside their own room, never
    reaching the next bracket's, on every sheet size.
  * A combined sheet's long title wraps at its ", " onto up to four lines
    rather than being cut; a power sheet's long circuit band wraps.
  * Wording: FACTS "B · 400 A · thru A"; the workbook template's own
    " - " dashes rewritten at export.
  * Free rows: in notes an arrow turns only its own "tail" into "cable";
    old words glued to "s" or "-" are rewritten; "Tessera SX40" is data.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_r5.py -q --browser chromium
"""

import io
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402


# ── the xlsx ─────────────────────────────────────────────────────────────

def test_free_row_notes_rewrite_only_the_arrows_own_tail():
    n = pull_sheet.free_row_notes_spelling
    assert n('Tail rope for the Edison → TRUE1 tail') == 'Tail rope for the Edison → TRUE1 cable'
    assert n('Tail rope for the Edison -> True1 tail') == 'Tail rope for the Edison -> TRUE1 cable'
    assert n('safety tail, Edison tail · L6-20 TAIL') == 'safety tail, Edison cable · L6-20 CABLE'
    # round 6: the "tail" right after the arrow is the adapter's too
    assert n('tail end → tail') == 'tail end → cable'
    # the type keeps its rule: an arrow makes the row an adapter
    assert pull_sheet.free_row_spelling('Edison → True1 tail') == 'Edison → TRUE1 cable'


def test_old_words_glued_to_a_suffix_are_rewritten():
    s = pull_sheet.free_row_spelling
    assert s('Tru-1s') == 'TRUE1s'
    assert s('4 TRU-1s spare') == '4 TRUE1s spare'
    assert s('Ether-con-50') == 'etherCON-50'
    assert s('Ether-cons') == 'etherCONs'
    # still whole words: nothing inside another word
    assert s('Trust') == 'Trust' and s('True1st') == 'True1st' and s('xTru-1') == 'xTru-1'
    assert pull_sheet.free_row_notes_spelling('2 Tru-1s · Ether-con-50') == '2 TRUE1s · etherCON-50'


def test_the_workbook_template_text_has_no_spaced_hyphen_dash():
    openpyxl = pytest.importorskip('openpyxl')
    data, _ = pull_sheet.build_workbook({'positions': [{'name': 'P', 'rows': [
        {'type': 'Gaff', 'length': 'EA', 'qty': 1, 'label': '', 'notes': ''}]}]})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    dashed = [(ws.title, c.coordinate, c.value) for ws in wb.worksheets for row in ws.iter_rows()
              for c in row if isinstance(c.value, str) and ' - ' in c.value and not c.value.startswith('=')]
    assert dashed == [], dashed
    assert wb['TOTALS']['A1'].value == 'TOTALS · SHOP PULL'
    readme = [c.value for row in wb[pull_sheet.README].iter_rows() for c in row if isinstance(c.value, str)]
    assert 'LED GEAR PULL SHEET: how it works' in readme, readme
    assert any(t.endswith('Or use the one-click button (see APPS SCRIPT).') for t in readme), readme
    assert any(t.endswith('automatically, no button needed there.') for t in readme), readme
    # a meters show reads the same
    data, _ = pull_sheet.build_workbook({'positions': []}, {'cable_unit': 'm'})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb['TOTALS']['A1'].value == 'TOTALS · SHOP PULL'
    # the shipped template itself is untouched
    tpl = openpyxl.load_workbook(pull_sheet.TEMPLATE_PATH)
    assert tpl['TOTALS']['A1'].value == 'TOTALS  -  SHOP PULL'


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_paper_r4 import BINDER_JS, SHEETS  # noqa: E402
from test_power_naming import DIST, ev, setup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate(SEED_JS)
    pg.wait_for_function("() => window.app.project.layers.length === 3")
    yield pg, errors
    context.close()


# WALL A 10 x 6 and WALL B 6 x 3, as round 4's; TALL, a 10 x 60 wall,
# hidden unless a test shows it (setup() treats it as a "b" wall).
SEED_JS = """async () => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = async (method, url, body) => (await fetch(url, {
        method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body) })).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', { name: 'WALL A', columns: 10, rows: 6,
        cabinet_width: 200, cabinet_height: 200 });
    await j('POST', '/api/layer/add', { name: 'WALL B', columns: 6, rows: 3,
        cabinet_width: 200, cabinet_height: 200, offset_x: 2600 });
    await j('POST', '/api/layer/add', { name: 'TALL', columns: 10, rows: 60,
        cabinet_width: 200, cabinet_height: 200, offset_x: 5000 });
    const p = await j('GET', '/api/project');
    p.layers.find(l => l.name === 'TALL').visible = false;
    app.project = p;
    app.selectLayer(p.layers[0]);
    app.renderLayers();
}"""

OPTS_JS = ("Object.assign(app.readBinderOptions(), { scope: { kind: 'show' }, "
           "sides: { power: true, data: false } })")


def _reset(pg):
    ev(pg, """const T = app.project.layers.find(l => l.name === 'TALL');
        for (const l of app.project.layers) { l.visible = l !== T; delete l.group_id; }
        app.project.groups = []; delete app.project.groupNameDisplayByView;
        delete app.project.services; app._distroFaceMemo = null; app._circuitTailCache = null;
        return null;""")


# ── 1. a group that cannot fit ───────────────────────────────────────────

def _group(pg, mode):
    ev(pg, """A.group_id = 'g1'; B.group_id = 'g1';
        app.project.groups = [{ id: 'g1', name: 'MAIN WALL', layer_ids: [A.id, B.id] }];
        app.project.groupNameDisplayByView = { power: arg };
        app._circuitTailCache = null; return null;""", mode)


@pytest.mark.parametrize('mode', ['group', 'screens'])
def test_a_group_that_cannot_fit_prints_the_note_and_the_warning_names_it(page, mode):
    """WALL A and WALL B grouped, routed as one wall at 120 V / 10 A with
    1,200 W panels: one panel is over the 960 W a circuit carries at 80%.
    (A row too long for one circuit is cut since 2026-11-01, so it no longer
    cannot fit.) The group's sheet (or each member's) prints the owner's
    note, no wiring sheet, and the warning names MAIN WALL."""
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 1200},
                                     'b': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 1200}})
    _group(pg, mode)
    try:
        assert ev(pg, "return !!app.getAutoRoutePlan(A, 'power') && app.screenCircuits(A).length === 0;")
        note = 'Cannot fit a circuit: 1,200 W panels, 120 V / 10 A breaker, 8 A usable at 80%'
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert 'MAIN WALL (WALL A, WALL B): 1,200 W panels' in warn, warn
        assert 'WALL A: ' not in warn and warn.endswith(
            'No pattern helps: one panel alone draws more than a circuit carries.'), warn
        assert ' - ' not in warn, warn
        b = pg.evaluate(BINDER_JS, {'wiring': True, 'kinds': ['power', 'wiring']})
        power = [p for p in b['plan'] if p['kind'] == 'power']
        want = ['MAIN WALL'] if mode == 'group' else ['WALL A', 'WALL B']
        assert [p['title'].split(' - ')[0] for p in power] == want, b['plan']
        assert not [p for p in b['plan'] if p['kind'] == 'wiring'], b['plan']
        for p in b['pages']:
            if p['kind'] != 'power':
                continue
            assert note in p['logged'], (p['title'], p['logged'])
            assert 'no circuits, cannot fit' in p['logged'], p['logged']
            assert 'no cables typed' not in p['logged'], p['logged']
        circuits = [t['rows'] for t in b['tables'] if t['title'] == 'Circuits']
        assert circuits and all(rows == [[note]] for rows in circuits), circuits
        # a one-screen binder of the member that does not own the walk
        # warns about its wall too
        warn = ev(pg, "return app.binderCannotFitWarning(Object.assign(app.readBinderOptions(), "
                      "{ scope: { kind: 'screen', layerId: B.id }, sides: { power: true, data: false } }));")
        assert 'MAIN WALL (WALL A, WALL B)' in warn, warn
    finally:
        _reset(pg)
    assert errors == [], errors


def test_one_panel_over_the_circuit_says_no_pattern_helps(page):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={
        'a': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 1200},
        'b': {'powerVoltage': 120, 'powerAmperage': 10}})
    try:
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert 'WALL A: 1,200 W panels' in warn, warn
        # WALL B's row is too long for one circuit, so Organized cuts it
        # (2026-11-01) and only A is named
        assert 'WALL B' not in warn and 'another pattern' not in warn, warn
        assert warn.endswith('No pattern helps: one panel alone draws more than a circuit carries.'), warn
        ev(pg, "B.panelWatts = 1200; app._circuitTailCache = null; return null;")
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert 'another pattern' not in warn, warn
        assert warn.endswith('No pattern helps: one panel alone draws more than their circuits carry.'), warn
        ev(pg, "B.visible = false; app._circuitTailCache = null; return null;")
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert warn.endswith('higher voltage or amperage. No pattern helps: one panel alone draws more '
                             'than a circuit carries.'), warn
        # the group's sheet says so too, and so does a lone screen's
        b = pg.evaluate(BINDER_JS, {'kinds': ['power']})
        a = next(p for p in b['pages'] if p['title'].startswith('WALL A - Power'))
        assert 'no circuits, cannot fit' in a['logged'], a['logged']
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 2. a distro with nothing at all, on the Service sheet and Overview ───

def test_an_empty_distro_is_off_the_service_sheet_and_the_overview(page):
    pg, errors = page
    _reset(pg)
    sl = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208', 'serviceId': 's1',
          'outputRows': DIST['outputRows']}
    sr = dict(sl, id='d2', name='SR')
    spare = {'id': 'd3', 'name': 'SPARE', 'ratingA': 100, 'system': '120/208', 'serviceId': 's1'}
    setup(pg, distros=[sl, sr, spare], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 1}}})
    try:
        ev(pg, "app.project.services = [{ id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208',"
               " voltage: 208, phase: 3 }]; app._distroFaceMemo = null; app._circuitTailCache = null;"
               " return null;")
        b = pg.evaluate(BINDER_JS, {'cover': True, 'kinds': ['overview', 'service']})
        svc_tables = [t for t in b['tables'] if t['title'].upper().endswith('DISTROS')
                      or t['title'].upper().endswith('DISTRO')]
        assert svc_tables and all(t['title'] == '2 distros' for t in svc_tables), [t['title'] for t in svc_tables]
        names = [r[0] for t in svc_tables for r in t['rows']]
        assert 'SPARE' not in names and {'SL', 'SR', 'total'} <= set(names), names
        total = next(r for t in svc_tables for r in t['rows'] if r[0] == 'total')
        assert total[1] == '800 A', total
        svc = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Service')
        assert svc['Distros'] == 'ratings 800 A on 600 A', svc
        totals = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Show totals')
        assert totals['Distros'] == '2', totals
        # a feeder set brings it back, everywhere at once
        ev(pg, "app.project.distros.find(d => d.id === 'd3').feeder = { ft: 50 };"
               " app._distroFaceMemo = null; app.getDistros(); return null;")
        b = pg.evaluate(BINDER_JS, {'cover': True, 'kinds': ['overview', 'service']})
        totals = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Show totals')
        assert totals['Distros'] == '3', totals
        svc = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Service')
        assert svc['Distros'] == 'ratings 900 A on 600 A', svc
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 3. hidden screens on the distro and Service sheets ───────────────────

def test_hidden_screens_are_off_the_distro_and_service_sheets(page):
    """WALL A and WALL B each on their own box of PD, WALL B hidden: PD's
    table lists WALL A's box alone, its counts and Circuits say one box,
    and a distro whose only screen is hidden is off the binder. (The
    Load figures read getDistroLoads, which leaves hidden screens out in
    r5-power's fix; this test pins the expected figures.)"""
    pg, errors = page
    _reset(pg)
    other = dict(DIST, id='d2', name='OTHER', serviceId='s1')
    pd = dict(DIST, serviceId='s1')
    setup(pg, distros=[pd, other], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd1', '2': 'd2'}, 'powerSocaNumber': {'1': 2, '2': 1},
              'powerAmperage': 12.5, 'powerSocaSplits': [1]}})
    try:
        ev(pg, "app.project.services = [{ id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208',"
               " voltage: 208, phase: 3 }]; app._distroFaceMemo = null; app._circuitTailCache = null;"
               " return null;")
        assert ev(pg, "return app.getSocaPlan(B).map(s => s.soca);") == [1, 2]
        # what the binder should read: the show without WALL B at all
        want = ev(pg, """
            const keep = app.project.layers;
            app.project.layers = keep.filter(l => l !== B && l.visible !== false);
            app._circuitTailCache = null;
            try {
                const d = app.getDistroLoads().find(x => x.id === 'd1');
                return { load: app._bDistroLoadText(app.getDistros()[0], d),
                         circuits: app.getSocaPlan(A).reduce((n, s) => n + s.legs.length, 0) };
            } finally { app.project.layers = keep; app._circuitTailCache = null; }""")
        ev(pg, "B.visible = false; app._circuitTailCache = null; return null;")
        b = pg.evaluate(BINDER_JS, {'kinds': ['distro', 'service']})
        titles = [p['title'] for p in b['plan'] if p['kind'] == 'distro']
        assert titles and not [t for t in titles if 'OTHER' in t], titles
        # (the table is built on the plan pass and again on each render)
        boxes = [t for t in b['tables'] if t['cols'][:2] == ['name', 'type']]
        assert boxes and all(t == boxes[0] for t in boxes), boxes
        rows = boxes[0]['rows']
        assert [r[3] for r in rows] == ['WALL A'], rows
        assert boxes[0]['title'] == '1 Socapex 208V', boxes[0]['title']
        pdkv = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Distro')
        assert pdkv['Circuits'].startswith(f"{want['circuits']} on 1 "), pdkv
        # the pull list the distro prints agrees: WALL B is on no paper
        texts = ' '.join(t for p in b['pages'] for t in p['logged'])
        assert 'WALL B' not in texts, [t for p in b['pages'] for t in p['logged'] if 'WALL B' in t]
        svc_rows = [r[0] for t in b['tables'] if t['title'].endswith('distro') or t['title'].endswith('distros')
                    for r in t['rows']]
        assert 'OTHER' not in svc_rows, svc_rows
        # the Load figures (getDistroLoads, r5-power): as if WALL B were gone
        assert pdkv['Load'] == want['load'], (pdkv, want)
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 4. bracket labels on a dense map ─────────────────────────────────────

SR = {'id': 'd1', 'name': 'SR', 'ratingA': 400, 'system': '120/208',
      'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 6, 'coupling': 'll', 'breakerA': 20}]}

BRACKETS_JS = """(sheet) => {
    const app = window.app;
    const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
        hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'power');
    const r = app.renderBinderPage(opts, i);
    return { brackets: r.brackets, texts: r.texts };
}"""


def test_bracket_labels_never_reach_the_next_bracket(page):
    """Two distros named SR, a 10 x 60 wall, a row per circuit so each
    multi spans six rows, no lengths: "SR-1-1" and "no length" stay inside
    their own bracket's room on every sheet size."""
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[SR, dict(SR, id='d2')], walls={})
    ev(pg, """const T = app.project.layers.find(l => l.name === 'TALL');
        for (const l of app.project.layers) l.visible = l === T;
        const dist = {}, num = {};
        for (let i = 1; i <= 10; i++) { dist[i] = i <= 5 ? 'd1' : 'd2'; num[i] = i <= 5 ? i : i - 5; }
        Object.assign(T, { powerAmperage: 12.5, powerSocaDistro: dist, powerSocaNumber: num });
        app._circuitTailCache = null; return null;""")
    try:
        names = ev(pg, "return app.getSocaPlan(app.project.layers.find(l => l.name === 'TALL'))"
                       ".map(s => [s.name, s.legs.length]);")
        assert names == [[f'SR-{d}-{n}', 6] for d in (1, 2) for n in range(1, 6)], names
        for sheet in SHEETS:
            out = pg.evaluate(BRACKETS_JS, sheet)
            br = out['brackets']
            assert len(br) == 10, (sheet, br)
            by = {}
            for b in br:
                by.setdefault((b['side'], b['depth']), []).append(b)
            for stack in by.values():
                stack.sort(key=lambda b: b['y1'])
                for a, b in zip(stack, stack[1:]):
                    assert a['labelY2'] <= b['labelY1'] + 0.5, (sheet, a, b)
                for b in stack:
                    # centred on its own bracket, inside its room
                    mid = (b['y1'] + b['y2']) / 2
                    assert abs((b['labelY1'] + b['labelY2']) / 2 - mid) < 1, (sheet, b)
            for b in br:
                # the name whole, and the length said where it fits at the
                # binder's 14 floor (round 6: else the name alone, legible,
                # rather than both at 10)
                assert b['lines'][0].startswith(b['name']), (sheet, b)
                assert 'no length' in ' '.join(b['lines']) or b['lines'] == [b['name']], (sheet, b)
                assert b['size'] >= 14, (sheet, b)
                assert not [t for t in b['lines'] if t.endswith('…')], (sheet, b)
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 5. cut text ──────────────────────────────────────────────────────────

TITLE_JS = """([sheet, title]) => {
    const app = window.app;
    const orig = app._bTitleBlock;
    app._bTitleBlock = function (book, page) { return orig.call(this, book, { ...page, sheetTitle: title }); };
    try {
        const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
            hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
        const plan = app.planBinder(opts);
        const r = app.renderBinderPage(opts, plan.findIndex(p => p.kind === 'power'));
        return r.textInfo.filter(t => t.text.startsWith(title.split(' ')[0]));
    } finally { app._bTitleBlock = orig; }
}"""

SIX = ('PROCESSORS · H9 SL MAIN, H9 SR MAIN, H9 CENTER MAIN, H9 SL BACKUP, H9 SR BACKUP, '
       'H9 FLOWN · PULL LIST')
NINE = ('PROCESSORS · ' + ', '.join(f'H9 SL UNIT {i}' for i in range(1, 10)) + ' · PULL LIST')


def test_a_combined_sheet_title_wraps_at_its_commas(page):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    try:
        for sheet in SHEETS:
            got = pg.evaluate(TITLE_JS, [sheet, SIX])
            assert len(got) == 1, (sheet, got)
            # whole, never cut, and at 21 px or more (it cut at 14 px)
            assert got[0]['text'] == SIX, (sheet, got)
            assert got[0]['size'] >= 21, (sheet, got)
            got = pg.evaluate(TITLE_JS, [sheet, NINE])
            assert got[0]['text'] == NINE and got[0]['size'] >= 17, (sheet, got)
        # the pieces: a name is never split at its own spaces while the
        # list can break at its commas
        lines = ev(pg, """
            const book = app._binderBook(app.readBinderOptions(), { dry: true });
            const c = document.createElement('canvas'); book.ctx = c.getContext('2d');
            const out = [];
            const orig = app._bText;
            app._bText = function (b, t, x, y, o) { out.push(t); return orig.apply(this, arguments); };
            try { app._bSheetTitle(book, arg, 0, 0, 440); } finally { app._bText = orig; }
            return out;""", SIX)
        assert 3 <= len(lines) <= 4, lines
        assert all(re.search(r'(,|·|LIST)$', t) for t in lines), lines
    finally:
        _reset(pg)
    assert errors == [], errors


def test_a_long_distro_name_wraps_the_circuit_band(page):
    pg, errors = page
    _reset(pg)
    name = 'UPSTAGE LEFT DISTRIBUTION RACK FOR VIDEO1'
    setup(pg, distros=[dict(DIST, name=name)], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    try:
        band = ev(pg, "const scr = app.buildPullSheet().byScreen[A.id];"
                      " return app._bBoxBand(app._binderBook(app.readBinderOptions(), { dry: true }), A, scr.boxes[0]);")
        band = band if isinstance(band, str) else band.get('band', '')
        assert 'no length' in band and name in band, band
        for sheet in SHEETS:
            b = pg.evaluate(BINDER_JS, {'sheet': sheet, 'kinds': ['power']})
            p = next(p for p in b['pages'] if p['title'].startswith('WALL A - Power'))
            cut = [t for t in p['logged'] if t.endswith('…')]
            assert cut == [], (sheet, cut)
            # the band's lines, in order, make the band whole (the
            # bracket's label, logged first, says the name and length only)
            logged = p['logged']
            whole = []
            for at, t in enumerate(logged):
                if not t.startswith(name):
                    continue
                for n in (1, 2, 3):
                    if ' '.join(logged[at:at + n]) == band:
                        whole.append(logged[at:at + n])
            assert whole, (sheet, [t for t in logged if name in t or 'circuits' in t], band)
            assert all(len(w) <= 3 for w in whole), whole
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 6. wording ───────────────────────────────────────────────────────────

def test_a_thru_fed_distros_facts_say_its_rating_beside_its_name(page):
    pg, errors = page
    _reset(pg)
    sl = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208', 'serviceId': 's1'}
    sr = {'id': 'd2', 'name': 'SR', 'ratingA': 200, 'system': '120/208', 'feeder': {'from': 'd1'}}
    setup(pg, distros=[sl, sr], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 1}}})
    try:
        ev(pg, "app.project.services = [{ id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208',"
               " voltage: 208, phase: 3 }]; app._distroFaceMemo = null; app._circuitTailCache = null;"
               " return null;")
        b = pg.evaluate(BINDER_JS, {'kinds': []})
        rows = [v for k in b['kv'] if k['title'] == 'Facts' for key, v in k['pairs'] if key == 'Distro']
        assert any(v.startswith('SR · 200 A · thru SL') for v in rows), rows
        assert any(v.startswith('SL · 400 A') for v in rows), rows
        assert not [v for v in rows if ' · thru SL · 200 A' in v], rows
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 7. free rows and a free row's side ───────────────────────────────────

def test_free_rows_in_the_app_read_the_round_5_rules(page):
    pg, errors = page
    out = ev(pg, """return {
        notes: ['Tail rope for the Edison → True1 tail', 'tail end → tail', 'Edison tail · Tail rope',
                '2 Tru-1s; Ether-con-50'].map(t => app.pullFreeRowNotes(t)),
        types: ['Tru-1s', 'Ether-con-50', 'Edison → True1 tail', 'Trust', 'True1st', 'Tail rope']
            .map(t => app.pullFreeRowType(t)) };""")
    assert out['notes'] == ['Tail rope for the Edison → TRUE1 cable', 'tail end → cable',
                            'Edison cable · Tail rope', '2 TRUE1s; etherCON-50'], out
    assert out['types'] == ['TRUE1s', 'etherCON-50', 'Edison → TRUE1 cable', 'Trust', 'True1st',
                            'Tail rope'], out
    # the app and the workbook spell a free row alike
    for t in ('Tail rope for the Edison → True1 tail', '2 Tru-1s; Ether-con-50', 'Edison tail · Tail rope'):
        assert pull_sheet.free_row_notes_spelling(t) == ev(pg, "return app.pullFreeRowNotes(arg);", t), t
    assert errors == [], errors


def test_a_retired_tessera_prefix_still_reads_as_data(page):
    pg, errors = page
    sides = pg.evaluate("(ts) => Object.fromEntries(ts.map(t => [t, window.app.pullGuessSide(t)]))",
                        ['Tessera SX40', 'Tessera S8', 'Tessera SX40 rack', 'SX40', 'Tessera rope'])
    assert sides == {'Tessera SX40': 'data', 'Tessera S8': 'data', 'Tessera SX40 rack': 'data',
                     'SX40': 'data', 'Tessera rope': 'power'}, sides
    assert errors == [], errors
