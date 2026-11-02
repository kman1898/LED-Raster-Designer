"""Binder and pull-sheet paperwork, round 4 (owner rulings, 2026-10-22).

  * A LIST cell (a pull list's LABEL) folds to "+N more" counting whole
    members: the draw pass keeps to the lines the row was measured at, a
    member the fold would cut is left out and counted, a member a hair too
    wide shrinks on a line of its own, a range's "…" is never a break, and
    two names never share a line. Every sheet size, long, medium and short
    names.
  * The Overview's SHOW TOTALS leave hidden screens out.
  * A direct output's Circuits cell prints its one cable when the length
    is typed on the output only.
  * A screen that can't fit a circuit at 80%: the export warns, and its
    power sheet prints with a note in place of circuits.
  * A distro with nothing at all is off the binder.
  * Old free rows: notes rewritten too; "tail" is "cable" only on an
    adapter; the editor's STALE list in today's spelling; a key whose type
    is the user's text is never rewritten.
  * pullGuessSide: "Card H 20xRJ45", "MX40", "Patch panel" are data;
    "Breakout panel", "Truss panel", "Light switch" are power.
  * A multi with no length says so on its bracket; LENGTH headings stay
    readable; a long sheet title wraps rather than losing its view.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_r4.py -q --browser chromium
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402


# ── the xlsx: old free rows ──────────────────────────────────────────────

def test_free_row_spelling_rewrites_tail_only_on_an_adapter_and_reads_notes():
    s = pull_sheet.free_row_spelling
    assert s('Tail rope') == 'Tail rope'
    assert s('Safety tail') == 'Safety tail'
    assert s('Edison tail') == 'Edison cable'
    assert s('L6-20 TAIL') == 'L6-20 CABLE'
    assert s('Edison → True1 tail') == 'Edison → TRUE1 cable'
    assert s('Tru-1 Breakout') == 'TRUE1 Breakout'
    n = pull_sheet.free_row_notes_spelling
    assert n('spare Edison → True1 tail · Tail rope; Tru-1 2fer, Ether-con') \
        == 'spare Edison → TRUE1 cable · Tail rope; TRUE1 2fer, etherCON'


def test_the_workbook_writes_old_free_row_notes_in_todays_spelling():
    openpyxl = pytest.importorskip('openpyxl')
    import io
    data, _ = pull_sheet.build_workbook({'positions': [{'name': 'P', 'rows': [
        {'type': 'Tail rope', 'length': 'EA', 'qty': 1, 'label': '',
         'notes': 'for the Tru-1 2fer · Edison → True1 tail', 'added': True},
        {'type': 'Gaff', 'length': 'EA', 'qty': 1, 'label': '', 'notes': 'Tru-1 as typed'},
    ]}]})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb[pull_sheet.SHEET]
    written = [str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert 'Tail rope' in written, written
    assert 'for the TRUE1 2fer · Edison → TRUE1 cable' in written, written
    # an engine row's notes are the app's own: untouched
    assert 'Tru-1 as typed' in written, written


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_naming import DIST, ev, setup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate("""async () => {
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
        const p = await j('GET', '/api/project');
        app.project = p;
        app.selectLayer(p.layers[0]);
        app.renderLayers();
    }""")
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    yield pg, errors
    context.close()


SHEETS = ('letter', 'tabloid', 'a4', 'a3', 'archc', 'archd')

# Every sheet at one sheet size: the plan, each page's texts and text
# sizes (only the kinds asked for, to keep it quick), and the tables and
# KV blocks the binder built.
BINDER_JS = """(o) => {
    const app = window.app;
    app._circuitTailCache = null;
    const tables = [], kv = [];
    const origT = app._bTableLines, origK = app._bKvLines;
    app._bTableLines = function (book, spec) {
        tables.push({ title: spec.title, cols: (spec.cols || []).map(c => c.title),
                      rows: (spec.rows || []).filter(r => r.cells).map(r => r.cells.slice()) });
        return origT.apply(this, arguments);
    };
    app._bKvLines = function (book, title, pairs) {
        kv.push({ title, pairs: pairs.map(p => p.slice()) });
        return origK.apply(this, arguments);
    };
    const opts = Object.assign(app.readBinderOptions(),
        { sheet: o.sheet || 'tabloid', scope: { kind: 'show' }, hardware: true, pull: true,
          cover: !!o.cover, wiring: !!o.wiring, sides: { power: true, data: !!o.data } });
    let plan;
    const pages = [];
    try {
        plan = app.planBinder(opts);
        for (let i = 0; i < plan.length; i++) {
            if (o.kinds && !o.kinds.includes(plan[i].kind)) continue;
            const r = app.renderBinderPage(opts, i);
            pages.push({ title: plan[i].title, kind: plan[i].kind, sheetTitle: plan[i].sheetTitle,
                         texts: r.record.ops.filter(op => op.op === 'text' && String(op.text).trim())
                                  .map(op => String(op.text)),
                         logged: r.texts, info: r.textInfo });
        }
    } finally { app._bTableLines = origT; app._bKvLines = origK; }
    return { plan: plan.map(p => ({ kind: p.kind, title: p.title, sheetTitle: p.sheetTitle })),
             pages, tables, kv };
}"""


# ── 1. list cells fold counting whole members ────────────────────────────

LONG = (['SL CVT %d-1 … %d-13' % (i, i) for i in range(1, 9)]
        + ['UHD JR SL Main BU (backup)', 'UHD JR SR Main BU (backup)', 'CVT10-1 … 10-10']
        + ['SR CVT %d-1 … %d-13' % (i, i) for i in range(1, 7)])
MEDIUM = ['WALL A-%d' % i for i in range(1, 40)]
SHORT = ['S%d' % i for i in range(1, 90)]


def _members_check(text, members):
    """The cell's text as drawn (its lines joined): each piece a whole
    member, in order, and shown + N == all of them."""
    m = re.search(r'\s*\+(\d+) more$', text)
    more = int(m.group(1)) if m else 0
    body = text[:m.start()] if m else text
    shown = [p.strip() for p in re.split(r',\s+', body.strip().rstrip(',')) if p.strip()]
    assert shown == members[:len(shown)], (shown, members)
    assert len(shown) + more == len(members), (text, len(shown), more, len(members))
    return len(shown), more


def test_cell_lines_hard_cap_and_whole_members(page):
    pg, errors = page
    out = pg.evaluate("""(o) => {
        const app = window.app;
        const book = app._binderBook(app.readBinderOptions(), { dry: true });
        const res = {};
        for (const [name, members] of Object.entries(o)) {
            const text = members.join(', ');
            const soft = app._bCellLines(book, text, 24, 400, 260, 3);
            // the draw pass, held to the lines the measure gave
            const hard = app._bCellLines(book, text, 24, 400, 260, soft.length, false, true);
            const narrow = app._bCellLines(book, text, 24, 400, 200, soft.length, false, true);
            res[name] = { soft, hard, narrow };
        }
        res.range = app._bCellLines(book, 'CVT10-1 … 10-10, CVT11-1 … 11-10', 24, 400, 205, 3);
        return res;
    }""", {'long': LONG, 'medium': MEDIUM, 'short': SHORT})
    for name, members in (('long', LONG), ('medium', MEDIUM), ('short', SHORT)):
        r = out[name]
        assert r['hard'] == r['soft'], (name, r)
        assert len(r['narrow']) <= len(r['soft']), (name, r)
        for lines in (r['soft'], r['narrow']):
            assert not [t for t in lines if t.endswith('…')], (name, lines)
            assert lines[-1].endswith(' more'), (name, lines)
            _members_check(' '.join(lines), members)
    # a range is never broken at its "…"
    assert not [t for t in out['range'] if t.endswith('…') or t.startswith('…')], out['range']
    assert ' '.join(out['range']) == 'CVT10-1 … 10-10, CVT11-1 … 11-10', out['range']
    assert errors == [], errors


TOTALS_JS = """(o) => {
    const app = window.app;
    const orig = app.buildPullSheet;
    app.buildPullSheet = function () {
        const l = orig.apply(this, arguments);
        l.totals = [...(l.totals || []), ...o.rows.map(r => ({ type: r[0], length: r[1], qty: r[2],
            label: r[3], notes: '', side: 'data' }))];
        return l;
    };
    try {
        const opts = Object.assign(app.readBinderOptions(), { sheet: o.sheet, scope: { kind: 'show' },
            hardware: true, pull: true, cover: false, wiring: false, sides: { power: true, data: false } });
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => {
            if (p.kind !== 'totals') return;
            const r = app.renderBinderPage(opts, i);
            out.push(...r.texts);
        });
        return out;
    } finally { app.buildPullSheet = orig; }
}"""


def test_the_totals_pull_list_folds_long_labels_on_every_sheet(page):
    """The all-positions pull list: a LABEL of long, medium or short names
    is never cut, never leaves part of a name before "+N more", and its
    count adds up - on every sheet size."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    rows = [['Cat6', "25'", 17, ', '.join(LONG)], ['Cat6', "50'", 39, ', '.join(MEDIUM)],
            ['Cat6', "75'", 89, ', '.join(SHORT)]]
    for sheet in SHEETS:
        texts = pg.evaluate(TOTALS_JS, {'sheet': sheet, 'rows': rows})
        assert texts, sheet
        cut = [t for t in texts if t.endswith('…')]
        assert cut == [], (sheet, cut)
        for members, head in ((LONG, 'SL CVT 1-1'), (MEDIUM, 'WALL A-1,'), (SHORT, 'S1, S2')):
            cell = [t for t in texts if t.startswith(head)]
            assert len(cell) == 1, (sheet, head, [t for t in texts if head.split()[0] in t])
            _members_check(cell[0], members)
        # no fragment of a name stands before the count
        assert not [t for t in texts if re.search(r'(^|, )(BU|Main|10-10|1-13) \+\d+ more$', t)], (sheet, texts)
    assert errors == [], errors


# ── 2. the Overview's totals leave hidden screens out ─────────────────────

def test_the_overview_show_totals_leave_hidden_screens_out(page):
    pg, errors = page
    setup(pg, distros=[DIST], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 2}}})
    ev(pg, "B.visible = false; app._circuitTailCache = null; return null;")
    try:
        b = pg.evaluate(BINDER_JS, {'cover': True, 'kinds': ['overview']})
        totals = dict(next(k['pairs'] for k in b['kv'] if k['title'] == 'Show totals'))
        want = ev(pg, "return { panels: app._bScreenFacts(A).active,"
                      " pull: app._pullScreens().length };")
        assert totals['Screens'] == '1' == str(want['pull']), totals
        assert totals['Panels'] == str(want['panels']), (totals, want)
    finally:
        ev(pg, "B.visible = true; app._circuitTailCache = null; return null;")
    assert errors == [], errors


# ── 3. a direct output's length typed on the output alone ─────────────────

def test_the_circuits_cell_on_a_direct_output_reads_the_outputs_length(page):
    """WALL B alone on PD 3 (Edison), 40' typed in the tray's direct Cable
    field and no cable on the circuit: the Circuits cell says the output's
    one cable, never "—"."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={
        'b': {'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 3},
              'powerSocaLengths': {'1': '40'}}})
    n = ev(pg, "B.powerCircuitCables = {}; app._circuitTailCache = null; return app.screenCircuits(B)[0].num;")
    want = ev(pg, "return app.directCircuitCable(B, arg).text;", n)
    assert 'Edison' in want and '40' in want, want
    b = pg.evaluate(BINDER_JS, {'kinds': []})
    circuits = [t for t in b['tables'] if t['title'] == 'Circuits']
    # (the direct output's circuit; the screens' unfed circuits print no cable)
    label = ev(pg, "return app.getPowerCircuitLabel(B, arg);", n)
    cells = [r[4] for t in circuits for r in t['rows'] if len(r) == 5 and r[0] == label]
    assert cells == [want], (label, circuits)
    assert errors == [], errors


# ── 4. a screen that can't fit a circuit ─────────────────────────────────

def test_a_screen_that_cannot_fit_prints_its_power_sheet_with_a_note(page):
    """WALL A at 120 V / 10 A with 1,000 W panels: a circuit carries 960 W
    at 80%, so one panel alone is over. (A row too long for one circuit is
    cut since 2026-11-01, so it is no longer a reason.) The export warns;
    its power sheet prints the note in place of circuits; no wiring sheet."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={
        'a': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 1000},
        'b': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    note = 'Cannot fit a circuit: 1,000 W panels, 120 V / 10 A breaker, 8 A usable at 80%'
    got = ev(pg, "return { n: app.screenCircuits(A).length, list: app.binderCannotFit(Object.assign("
                 "app.readBinderOptions(), { scope: { kind: 'show' }, sides: { power: true, data: false } }))"
                 ".map(x => [x.layer.name, x.note]), warn: app.binderCannotFitWarning(Object.assign("
                 "app.readBinderOptions(), { scope: { kind: 'show' }, sides: { power: true, data: false } })) };")
    assert got['n'] == 0, got
    assert got['list'] == [['WALL A', note]], got
    assert 'WALL A: 1,000 W panels' in got['warn'] and ' - ' not in got['warn'], got
    b = pg.evaluate(BINDER_JS, {'wiring': True, 'kinds': ['power']})
    titles = [p['title'] for p in b['plan']]
    assert any(t.startswith('WALL A - Power') for t in titles), titles
    assert not [p for p in b['plan'] if p['kind'] == 'wiring' and 'WALL A' in p['title']], titles
    a = next(p for p in b['pages'] if p['title'].startswith('WALL A - Power'))
    assert note in a['logged'], a['logged']
    # a screen that fits is unchanged
    assert any(p['title'].startswith('WALL B - Power') for p in b['pages']), titles
    # 100% where the region allows: the same wall at 230 V fits
    ev(pg, "A.powerVoltage = 230; A.powerAmperage = 16; app._circuitTailCache = null; return null;")
    assert ev(pg, "return app._bCannotFit(A);") is None
    assert errors == [], errors


# ── 5. a distro with nothing at all ──────────────────────────────────────

def test_a_distro_with_nothing_at_all_is_off_the_binder(page):
    pg, errors = page
    empty = {'id': 'd2', 'name': 'SPARE', 'ratingA': 100, 'system': '120/208'}
    setup(pg, distros=[DIST, empty], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    b = pg.evaluate(BINDER_JS, {'kinds': []})
    names = [p['title'] for p in b['plan'] if p['kind'] == 'distro']
    assert names and not [t for t in names if 'SPARE' in t], names
    texts = ' '.join(str(c) for t in b['tables'] for r in t['rows'] for c in r)
    assert 'nothing on this distro' not in texts.lower(), texts
    # a feeder set keeps it on, the way the pull sheet lists it
    setup(pg, distros=[DIST, dict(empty, feeder={'ft': 50})],
          walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    b = pg.evaluate(BINDER_JS, {'kinds': []})
    names = [p['title'] for p in b['plan'] if p['kind'] == 'distro']
    assert [t for t in names if 'SPARE' in t], names
    assert errors == [], errors


# ── 6. old free rows and old keys ────────────────────────────────────────

def test_old_free_rows_read_notes_and_tail_only_on_adapters(page):
    pg, errors = page
    out = ev(pg, """
        const P = 'pos:free';
        app.project.pullSheetEdits = { positions: { [P]: { rows: [], added: [
            { type: 'Tail rope', length: 'EA', qty: 1, label: '', notes: 'Tru-1 2fer · Edison → True1 tail' },
            { type: 'Edison tail', length: 'EA', qty: 1, label: '', notes: 'Tail rope' },
            { type: 'Edison → True1 tail', length: 'EA', qty: 1, label: '', notes: '' } ] } } };
        try {
            const added = app.getPullSheetEdits().positions[P].added;
            return { added: added.map(a => [a.type, a.notes]),
                     types: ['Tail rope', 'Edison tail', 'L6-20 tail', 'Edison → powerCON tail',
                             'Safety tail line'].map(t => app.pullFreeRowType(t)) };
        } finally { delete app.project.pullSheetEdits; }""")
    assert out['added'] == [['Tail rope', 'TRUE1 2fer · Edison → TRUE1 cable'],
                            ['Edison cable', 'Tail rope'],
                            ['Edison → TRUE1 cable', '']], out
    assert out['types'] == ['Tail rope', 'Edison cable', 'L6-20 cable', 'Edison → powerCON cable',
                            'Safety tail line'], out
    assert errors == [], errors


def test_a_key_whose_type_is_the_users_text_is_never_rewritten(page):
    pg, errors = page
    setup(pg, distros=[dict(DIST, typeName='Tru-1 Rack')], walls={})
    out = ev(pg, """
        app.project.pullSheet = { powerJumpNamePowercon: 'TRU-1 Long Jump' };
        A.panelModelName = 'Tru-1 Tile';
        try {
            return ["Tru-1 Rack|EA", "TRU-1 Long Jump|6'", "Tru-1 Tile|EA", "Tru-1 Breakout|EA",
                    "Tru-1 Power Jump|6'"].map(k => app.pullEditKey(k));
        } finally { delete app.project.pullSheet; delete A.panelModelName; }""")
    assert out == ["Tru-1 Rack|EA", "TRU-1 Long Jump|6'", "Tru-1 Tile|EA", "TRUE1 Breakout|EA",
                   "TRUE1 Power Jump|6'"], out
    assert errors == [], errors


def test_the_editors_stale_list_reads_todays_spelling(page):
    pg, errors = page
    out = ev(pg, """return {
        split: app._pullStaleKeyText("Tru-1 Power Jump|6'", ["TRUE1 Power Jump|6'", "powerCON Power Jump|6'"]),
        one: app._pullStaleKeyText("Tru-1 Power Jump|6'", []),
        data: app._pullStaleKeyText("Ether-con|25'", ["Cat6|25'", "etherCON|25'"]),
    };""")
    assert out['split'] == ['TRUE1 Power Jump / powerCON Power Jump', "6'"], out
    assert out['one'] == ['TRUE1 Power Jump', "6'"], out
    assert out['data'] == ['Cat6 / etherCON', "25'"], out
    src = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-pull-sheet-editor.js'),
               encoding='utf-8').read()
    assert "s.key.split('|')" not in src and src.count('_pullStaleKeyText(s.key') == 2
    assert errors == [], errors


# ── 7. a free row's side ─────────────────────────────────────────────────

def test_a_free_rows_side_round_4(page):
    pg, errors = page
    data = ['Card H 20xRJ45', 'MX40', 'Patch panel', 'MX40 Pro', 'Network switch', 'RJ45 coupler']
    power = ['Breakout panel', 'Truss panel', 'Light switch', 'Socapex panel', 'Shackle', 'Pro']
    panel = ['Spare panel', 'Half tile', 'cabinet', 'Spare panels (4)']
    sides = pg.evaluate("(ts) => Object.fromEntries(ts.map(t => [t, window.app.pullGuessSide(t)]))",
                        data + power + panel)
    assert {t: sides[t] for t in data} == {t: 'data' for t in data}, sides
    assert {t: sides[t] for t in power} == {t: 'power' for t in power}, sides
    assert {t: sides[t] for t in panel} == {t: 'panel' for t in panel}, sides
    assert errors == [], errors


# ── 8. cosmetic ──────────────────────────────────────────────────────────

def test_a_multi_with_no_length_says_so_on_its_bracket(page):
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    out = pg.evaluate("""() => {
        const app = window.app;
        const opts = Object.assign(app.readBinderOptions(), { sheet: 'tabloid', scope: { kind: 'show' },
            hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
        const plan = app.planBinder(opts);
        const i = plan.findIndex(p => p.kind === 'power');
        const r = app.renderBinderPage(opts, i);
        return { brackets: r.brackets.map(b => b.name), texts: r.texts };
    }""")
    assert out['brackets'], out
    name = out['brackets'][0]
    t = out['texts']
    # one line, or the name then the length on a line of its own
    on_bracket = f'{name} · no length' in t or any(
        t[i] == name and t[i + 1] == 'no length' for i in range(len(t) - 1))
    assert on_bracket, [x for x in t if name in x or 'length' in x]
    assert errors == [], errors


CROWDED_JS = """(o) => {
    const app = window.app;
    const orig = app.buildPullSheet;
    const extra = o.rows.map(r => ({ type: r[0], length: r[1], qty: r[2], label: r[3], notes: '', side: 'power' }));
    app.buildPullSheet = function () {
        const l = orig.apply(this, arguments);
        l.totals = [...(l.totals || []), ...extra];
        (l.positions || []).forEach(p => { p.rows = [...(p.rows || []), ...extra]; });
        (l.hardware || []).forEach(h => { h.rows = [...(h.rows || []), ...extra]; });
        return l;
    };
    try {
        const opts = Object.assign(app.readBinderOptions(), { sheet: o.sheet, scope: { kind: 'show' },
            hardware: true, pull: true, cover: false, wiring: false, sides: { power: true, data: false } });
        const plan = app.planBinder(opts);
        const out = [];
        plan.forEach((p, i) => {
            if (!['pull', 'distro', 'totals'].includes(p.kind)) return;
            const r = app.renderBinderPage(opts, i);
            r.textInfo.filter(t => t.text === 'LENGTH').forEach(t => out.push([p.kind, t.size]));
        });
        return out;
    } finally { app.buildPullSheet = orig; }
}"""


def test_length_headings_stay_readable_on_small_sheets(page):
    """LENGTH on the Letter and A4 pull pages and distro pull lists, with
    long cable names and labels crowding the table, stands at its full
    size (it shrank to 16 px here, 10 or 11 px on a real show)."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={
        'a': {'powerSocaDistro': {'1': 'd1', '2': 'd1'}, 'powerSocaNumber': {'1': 1, '2': 2},
              'powerSocaLengths': {'1': '100'}}})
    rows = [['Edison → powerCON cable', "30'+10'", 17, ', '.join(LONG)],
            ['STAGE LEFT DISTRO 400 A cam set · 5-wire', 'no length', 1, ', '.join(MEDIUM)]]
    for sheet in ('letter', 'a4'):
        sizes = pg.evaluate(CROWDED_JS, {'sheet': sheet, 'rows': rows})
        kinds = {k for k, _ in sizes}
        assert {'pull', 'distro', 'totals'} <= kinds, (sheet, sizes)
        # at its full size: the wrapping columns lend it their room
        assert min(s for _, s in sizes) >= 20, (sheet, sizes)
    assert errors == [], errors


def test_a_long_sheet_title_keeps_its_view(page):
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    aid = ev(pg, "A.name = 'UPSTAGE CENTER MAIN LED VIDEO WALL WITH A VERY LONG NAME'; return A.id;")
    try:
        for sheet in ('letter', 'tabloid'):
            b = pg.evaluate(BINDER_JS, {'sheet': sheet, 'wiring': True, 'kinds': ['power', 'wiring']})
            pages = [p for p in b['pages'] if 'UPSTAGE' in p['sheetTitle']]
            assert len(pages) == 2, (sheet, [p['sheetTitle'] for p in b['pages']])
            for p in pages:
                want = p['sheetTitle'].upper()
                assert want.endswith('FRONT VIEW'), want
                hits = [t for t in p['logged'] if 'FRONT VIEW' in t and 'UPSTAGE' in t]
                # the title block's title, whole, and the map's view heading
                assert len(hits) >= 2 and all(t == want for t in hits), (sheet, want, hits)
    finally:
        ev(pg, "app.project.layers.find(l => l.id === arg).name = 'WALL A'; return null;", aid)
    assert errors == [], errors
