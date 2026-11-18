"""The binder's SIMPLE mode: a sheet per job to hand a stagehand.

The owner, 2026-11-18, on a two-page example of his own: the export gets a
Full | Simple choice, saved with the show like the binder's ticks. Simple
keeps every sheet but the screens' own: each screen's (or group's) Power,
Power Wiring, Data and Data Wiring sheets become ONE POWER WIRING sheet and
ONE DATA WIRING sheet, and its Header/Footer sheet its simple one:

  * the drawing - the wiring sheet's, the bars' map - with the row and
    column rulers the map sheets carry, on all the room the tables leave;
  * under it, power: CIRCUITS per multi with a ROWS column (the rows each
    circuit feeds) in place of CABLE, and CABLES THIS SCREEN; data: PORTS,
    PRIMARY | BACKUP, and CABLES THIS SCREEN; header/footer: every bar where
    it hangs and the header and footer totals by size, a group's wall once;
  * no FACTS on any of them, and nothing past the drawing area on any
    paper size, title block on and off.

The word is DATA, never SIGNAL: "SCREEN A · DATA WIRING · REAR VIEW".

Run locally (each session takes its own free port):
    python -m pytest tests/test_binder_simple.py -n 4 --dist loadfile --browser chromium
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder_sheet_bounds import (BOUNDS_JS, NINE_JS, TOL, WALLS_JS,  # noqa: E402
                                      _fiber, _offenders, _opts, page)  # noqa: F401


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _walls(pg):
    out = pg.evaluate(WALLS_JS)
    assert out['layers'] == 4 and all(out['circuits']) and all(out['ports']), out


def _simple(**kw):
    return _opts(mode='simple', **kw)


# The plan, and of each screen sheet its text, its log and the tables the
# binder built for it (each _bTableLines spec while that sheet is painted).
SHEETS_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    const origT = app._bTableLines;
    let tables = null;
    app._bTableLines = function (book, spec) {
        if (tables) tables.push({ title: spec.title, cols: (spec.cols || []).map(c => c.title),
                                  rows: (spec.rows || []).filter(r => r.cells).map(r => r.cells.slice()),
                                  bold: (spec.rows || []).filter(r => r.cells).map(r => !!r.bold) });
        return origT.apply(this, arguments);
    };
    try {
        plan.forEach((p, i) => {
            if (!['power', 'data', 'wiring', 'rigging'].includes(p.kind)) return;
            tables = [];
            const r = app.renderBinderPage(opts, i);
            out.push({ number: p.number, kind: p.kind, title: p.title, sheetTitle: p.sheetTitle, layout: p.layout,
                       layerId: p.layerId, texts: r.texts, textInfo: r.textInfo, tables });
            tables = null;
        });
    } finally { app._bTableLines = origT; }
    return { plan: plan.map(p => [p.number, p.kind, p.sheetTitle, p.layout]), sheets: out };
}"""

# Each circuit's rows on a screen of its own, read straight off the
# engine: screenCircuits' panels, their row + 1.
ROWS_JS = r"""(name) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === name);
    return app.screenCircuits(l).map(c => [app.getPowerCircuitLabel(l, c.num),
        [...new Set(c.panels.map(p => p.row + 1))].sort((a, b) => a - b)]);
}"""


def _rows_text(rows):
    out, i = [], 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[j] + 1:
            j += 1
        out.append('%d-%d' % (rows[i], rows[j]) if j > i else str(rows[i]))
        i = j + 1
    return ', '.join(out)


def test_simple_swaps_each_screens_sheets_for_a_sheet_per_job(page):
    """Simple: each screen's Power, Power Wiring, Data and Data Wiring sheets
    become one POWER WIRING and one DATA WIRING sheet, its Header/Footer
    sheet its simple one - named as the wiring sheets are, DATA never
    SIGNAL - and every other sheet of the set is the Full set's."""
    pg, errors = page
    _walls(pg)
    full = pg.evaluate(SHEETS_JS, _opts(sheet='tabloid'))['plan']
    simple = pg.evaluate(SHEETS_JS, _simple(sheet='tabloid'))['plan']
    screen_kinds = ('power', 'data', 'wiring', 'rigging')
    assert [p[:3] for p in full if p[1] not in screen_kinds] == [p[:3] for p in simple if p[1] not in screen_kinds], \
        (full, simple)
    mine = [p for p in simple if p[1] in screen_kinds]
    assert mine and not [p for p in mine if p[1] in ('power', 'data')], mine
    # (a sheet whose tables run on past it: its "(CONT.)" sheet of tables)
    assert all(p[3] == 'simple' or p[2].endswith(' (CONT.)') for p in mine), mine
    for _n, kind, title, _l in mine:
        assert re.fullmatch(r'.+ · (POWER WIRING|DATA WIRING|HEADER/FOOTER) · FRONT VIEW( \(CONT\.\))?', title), title
        assert 'SIGNAL' not in title, title
    # a screen's sheets: power, data, then its bars where it has any
    name = 'STAGE LEFT VERTICAL IMAG TOWER'
    assert [p[2] for p in mine if p[2].startswith(name + ' ·')] == [
        name + ' · POWER WIRING · FRONT VIEW', name + ' · DATA WIRING · FRONT VIEW']
    name = 'UPSTAGE CENTER WIDE BACKDROP WALL'
    assert [p[2] for p in mine if p[2].startswith(name + ' ·') and not p[2].endswith('(CONT.)')] == [
        name + ' · POWER WIRING · FRONT VIEW', name + ' · DATA WIRING · FRONT VIEW', name + ' · HEADER/FOOTER · FRONT VIEW']
    # the series numbers on with no gap
    twos = [p[0] for p in simple if p[0].startswith('2.')]
    assert twos == ['2.%d' % (i + 1) for i in range(len(twos))], twos
    # the rear view names itself on every simple sheet
    rear = pg.evaluate(SHEETS_JS, _simple(sheet='tabloid', view='rear'))['plan']
    assert all(p[2].replace(' (CONT.)', '').endswith('· REAR VIEW') for p in rear if p[1] in screen_kinds), rear
    assert errors == []


def test_simple_sheets_carry_rulers_rows_and_no_facts(page):
    """The drawing with its column and row rulers; the CIRCUITS table with a
    ROWS column (the rows each circuit feeds, as the engine has them) in
    place of CABLE, CABLES THIS SCREEN under it; the data sheet's PORTS and
    CABLES THIS SCREEN; and no FACTS on any simple sheet."""
    pg, errors = page
    _walls(pg)
    out = pg.evaluate(SHEETS_JS, _simple(sheet='tabloid'))
    sheets = out['sheets']
    for s in sheets:
        assert 'FACTS' not in s['texts'], (s['title'], s['texts'][:40])
        if s['layout'] != 'simple':
            continue                    # (a "(cont.)" sheet of tables alone)
        rulers = [t['text'] for t in s['textInfo'] if t['size'] == 22 and t['weight'] == 700]
        assert '1' in rulers, (s['title'], rulers)
    name = 'STAGE LEFT VERTICAL IMAG TOWER'
    power = next(s for s in sheets if s['sheetTitle'] == name + ' · POWER WIRING · FRONT VIEW')
    # (every sheet's tables are built while one is painted - the plan is the
    # whole set's - so the circuits are found by their labels)
    # (a table per multi since the review: the first titled CIRCUITS, the rest
    # untitled - all with the ROWS column)
    circuits = [t for t in power['tables'] if t['cols'] == ['circuit', 'no.', 'panels', 'amps', 'rows']]
    assert circuits and all(t['cols'] == ['circuit', 'no.', 'panels', 'amps', 'rows'] for t in circuits), circuits
    want = dict((label, _rows_text(rows)) for label, rows in pg.evaluate(ROWS_JS, name))
    got = {r[0]: r[4] for t in circuits for r in t['rows']}
    assert want and {k: got.get(k) for k in want} == want, (got, want)
    assert all(label in power['texts'] for label in want), power['texts']
    # (the wall runs columns of 24: a circuit feeds a run of rows)
    assert all(re.fullmatch(r'\d+(-\d+)?(, \d+(-\d+)?)*', v) for v in got.values()), got
    assert 'CABLES THIS SCREEN' in power['texts'], power['texts']
    data = next(s for s in sheets if s['sheetTitle'] == name + ' · DATA WIRING · FRONT VIEW')
    assert 'PORTS' in data['texts'] and 'CABLES THIS SCREEN' in data['texts'], data['texts']
    assert errors == []


def test_the_simple_header_footer_sheet_lists_the_bars_and_their_totals(page):
    """The Header/Footer sheet: every bar where it hangs, then the header and
    footer totals - each size in the pull sheet's words, each side's total -
    a group's wall counted once."""
    pg, errors = page
    _walls(pg)
    out = pg.evaluate(SHEETS_JS, _simple(sheet='tabloid'))
    rig = [s for s in out['sheets'] if s['kind'] == 'rigging']
    assert rig, out['plan']
    # (every sheet's tables are built while one is painted - the plan is
    # the whole set's - so each is found by what it says)
    tables = [t for s in rig for t in s['tables']]
    totals = [t for t in tables if t['title'] == 'Totals']
    # the wide wall: eighteen doubles
    wide = {'rows': [['Header Bar - Double', '18'], ['Header total', '18']], 'bold': [False, True]}
    assert any({'rows': t['rows'], 'bold': t['bold']} == wide for t in totals), totals
    bars = [t for t in tables if t['title'] == 'Bars']
    wall = [r for t in bars for r in t['rows'] if r[0] == 'Header' and r[1] == 'Header Bar - Double']
    assert ['Header', 'Header Bar - Double', '1-2'] in wall and ['Header', 'Header Bar - Double', '35-36'] in wall, wall
    # the side fills, a group printed as one: L 2, 2, 2, 2 over a footer of
    # 4, 4; R 2, 1, 1, 2, 2 - the whole wall counted once
    pair = [['Header Bar - Single', '2'], ['Header Bar - Double', '7'], ['Header total', '9'],
            ['Footer Bar - Quad', '2'], ['Footer total', '2']]
    assert any(t['rows'] == pair for t in totals), totals
    for s in rig:
        assert 'TOTALS' in s['texts'] and 'BARS' in s['texts'] and 'FACTS' not in s['texts'], s['title']
    # its painted rows: the sheet's own totals, as the table says them
    side = next(s for s in rig if s['sheetTitle'].startswith('DOWNSTAGE'))
    i = side['texts'].index('TOTALS')
    assert side['texts'][i + 3:i + 13] == [c for r in pair for c in r], side['texts'][i:i + 14]
    assert errors == []


# Each simple data sheet's PORTS and CABLES THIS SCREEN headings as painted,
# its drawing's room, and the drawing area.
DATA_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const res = [];
    plan.forEach((p, i) => {
        if (p.layout !== 'simple' || p.kind !== 'wiring' || !(p.sides && p.sides.data)) return;
        const r = app.renderBinderPage(opts, i);
        const head = (t) => r.record.ops.filter(o => o.op === 'text' && o.text === t && o.weight === 700)
            .map(o => ({ x: o.x, y: o.y }));
        res.push({ title: p.title, ports: head('PORTS'), cables: head('CABLES THIS SCREEN'),
                   area: r.wiring.halves[0].area,
                   da: app._bGeo({ w: r.record.width, h: r.record.height }, opts.titleBlock !== false).da });
    });
    return res;
}"""


def test_the_drawing_takes_the_room_its_tables_leave(page):
    """A data sheet shaped like the owner's - a fiber breakout box with its
    inputs, backups, a TAC - on letter: CABLES THIS SCREEN stood under the
    wide PORTS table for want of ~40 px and took the drawing's height. Built
    at the width PORTS leaves, its CABLE cells wrapping, it stands beside
    PORTS, the two headings on one line, and the drawing keeps the room
    (never under 45 % of the area, its rulers' head and bubble out of it)."""
    pg, errors = page
    _fiber(pg)
    out = pg.evaluate(DATA_JS, _simple(sheet='letter'))
    assert out, 'no simple data sheet'
    for s in out:
        assert len(s['ports']) == 1 and len(s['cables']) == 1, s
        (px, py), (cx, cy) = (s['ports'][0]['x'], s['ports'][0]['y']), (s['cables'][0]['x'], s['cables'][0]['y'])
        assert abs(py - cy) < 0.5 and cx > px, (s['title'], s['ports'], s['cables'])
        area, da = s['area'], s['da']
        assert area['h'] >= 0.45 * da['h'] - 96 - 52 - 1, (s['title'], area, da)
        assert area['y'] + area['h'] <= da['y'] + da['h'] - 96 + 1, (s['title'], area, da)
    assert errors == []


def test_the_choice_is_saved_with_the_show(page):
    """Full | Simple is one of the choices a whole-show export saves on the
    show (project.binder.sheets.mode) and the dialog opens on; an older
    show, or a broken entry, reads Full."""
    pg, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const of = app._binderChoicesOf({ mode: 'simple', sides: { power: true, data: true } });
        const back = app._binderStoredChoices({ mode: 'simple' });
        const old = app._binderStoredChoices({ palette: 'colour' });
        const bad = app._binderStoredChoices({ mode: 'tiny' });
        const was = app.project.binder;
        app.project.binder = { ...(was || {}), sheets: { ...of } };
        app.openExportModal('binder');
        const picked = document.getElementById('export-binder-mode-simple').checked;
        const read = app.readBinderOptions().mode;
        document.getElementById('export-binder-mode-full').click();
        const after = app.readBinderOptions().mode;
        document.getElementById('export-cancel').click();
        app.project.binder = was;
        return { of: of.mode, back: back.mode, old: old.mode, bad: bad.mode, picked, read, after };
    }""")
    assert out == {'of': 'simple', 'back': 'simple', 'old': 'full', 'bad': 'full',
                   'picked': True, 'read': 'simple', 'after': 'full'}, out
    assert errors == []


# A wide table and a narrow one, built as the binder builds its tables, in
# a letter sheet's band: the columns the band lays them in.
SIDE_JS = r"""() => {
    const app = window.app;
    const book = { measureCtx: document.createElement('canvas').getContext('2d'),
                   geo: app._bGeo({ w: 2200, h: 1700 }, true) };
    const rows = (n, w) => Array.from({ length: n }, (_, i) => ({ cells: ['x'.repeat(w) + i, 'y'] }));
    const wide = app._bTableLines(book, { title: 'Wide', cols: [{ title: 'a', w: 3 }, { title: 'b', w: 1 }],
                                          rows: rows(10, 40), width: 1000 });
    const narrow = app._bTableLines(book, { title: 'Narrow', cols: [{ title: 'c', w: 1 }, { title: 'd', w: 1 }],
                                            rows: rows(4, 4), width: 700 });
    const band = app._bSimpleBand(book, [{ lines: wide, minW: 1000 }, { lines: narrow }]);
    return { cols: band.cols.map(c => ({ x: c.x, w: c.w, n: c.items.length, h: c.h })), h: band.h,
             da: book.geo.da };
}"""


def test_a_wide_table_and_a_narrow_one_stand_side_by_side(page):
    """The data sheet's wide PORTS and its narrow CABLES THIS SCREEN, as the
    owner's example lays them: side by side, each in a column of its own
    width, where the drawing area's width holds both - one under the other
    took the drawing's room."""
    pg, errors = page
    out = pg.evaluate(SIDE_JS)
    cols, da = out['cols'], out['da']
    assert len(cols) == 2 and cols[0]['x'] == da['x'], out
    assert cols[1]['x'] >= cols[0]['x'] + cols[0]['w'] + 30 - 0.5, out
    assert cols[1]['x'] + cols[1]['w'] <= da['x'] + da['w'] + 0.5, out
    assert out['h'] == max(c['h'] for c in cols), out
    assert errors == []


# ── the review's fixes ───────────────────────────────────────────────────

# Two walls grouped, side by side on stage (their Show Look places) but one
# over the other on the Pixel Map: each circuit's ROWS as the group sheet
# prints them, and the rows its rulers number.
GROUP_ROWS_JS = r"""async () => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = (method, url, body) => fetch(url, {method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const add = (name, offset_y) => j('POST', '/api/layer/add', {name, columns: 4, rows: 3,
        cabinet_width: 200, cabinet_height: 200, offset_x: 0, offset_y, powerVoltage: 208, powerAmperage: 20,
        panelWatts: 200, powerOrganized: true, powerFlowPattern: 'tl-h', flowPattern: 'tl-h'});
    await add('WALL-L', 0);
    await add('WALL-R', 600);
    const p = await j('GET', '/api/project');
    const L = p.layers.find(l => l.name === 'WALL-L'), R = p.layers.find(l => l.name === 'WALL-R');
    L.showOffsetX = 0; L.showOffsetY = 0; R.showOffsetX = 800; R.showOffsetY = 0;
    L.group_id = 'g1'; R.group_id = 'g1';
    p.groups = [{ id: 'g1', name: 'WALL', layer_ids: [L.id, R.id] }];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('simple_group_rows');
    const l = app.project.layers.find(x => x.name === 'WALL-L'), r = app.project.layers.find(x => x.name === 'WALL-R');
    const s = { kind: 'group', name: 'WALL', layers: [l, r], members: [l, r], carriers: [l, r], member: null };
    const rows = [];
    for (const carrier of [l, r]) {
        for (const c of app.screenCircuits(carrier)) rows.push([carrier.name, c.num, app._bCircuitRows(s, carrier, c.num)]);
    }
    const bands = app._bWallBands([l, r], 'power', 'y').bands.length;
    return { rows, bands };
}"""


def test_a_group_sheets_rows_are_its_rulers_rows(page):
    """WALL-R stands beside WALL-L on stage but under it on the Pixel Map:
    its circuits fed rows 4-6 by the Pixel Map's places against a ruler of
    1-3. ROWS now numbers the wall's rows the way the rulers do, from where
    each member draws (its Show Look place)."""
    pg, errors = page
    out = pg.evaluate(GROUP_ROWS_JS)
    assert out['bands'] == 3, out
    assert out['rows'] and all(re.fullmatch(r'[1-3](-[1-3])?(, [1-3](-[1-3])?)*', r) for _n, _c, r in out['rows']), out
    assert {r for name, _c, r in out['rows'] if name == 'WALL-R'} <= {'1', '2', '3', '1-2', '2-3', '1-3'}, out
    assert errors == []


# Every simple sheet's band as it is laid out: for each block it was given
# that is to stay whole (a multi), the columns its lines landed in.
WHOLE_JS = r"""(opts) => {
    const app = window.app;
    const orig = app._bSimpleBand;
    const seen = [];
    app._bSimpleBand = function (book, blocks) {
        const band = orig.apply(this, arguments);
        const where = (line) => band.cols.findIndex(c => c.items.some(it => it.line === line));
        seen.push(blocks.filter(b => b.whole).map(b => [...new Set(b.lines.map(where))]));
        return band;
    };
    try {
        const plan = app.planBinder(opts);
        plan.forEach((p, i) => { if (p.layout === 'simple' && p.sides && p.sides.power) app.renderBinderPage(opts, i); });
    } finally { app._bSimpleBand = orig; }
    return seen;
}"""


@pytest.mark.parametrize('show', ['walls', 'nine'])
def test_a_multi_stays_whole_in_one_column(page, show):
    """The simple CIRCUITS table is a block per multi, and a multi stays in
    one column of the band (it was split, 2-1 in one column and 2-2, 2-3
    under a repeated heading in the next) - unless it is taller than a
    column, which none of these is."""
    pg, errors = page
    if show == 'walls':
        _walls(pg)
    else:
        assert pg.evaluate(NINE_JS)['layers'] == 9
    for sheet in ('letter', 'a4', 'tabloid'):
        seen = pg.evaluate(WHOLE_JS, _simple(sheet=sheet))
        assert seen and any(seen), (sheet, seen)
        for blocks in seen:
            for cols in blocks:
                # one column - or none: the whole multi carried on to the
                # "(cont.)" sheet the band could not spare it room on
                assert len(cols) == 1, (sheet, seen)
        assert any(cols == [0] or (cols and cols[0] > 0) for blocks in seen for cols in blocks), seen
    assert errors == []


# A screen's bar list as the simple sheet builds it, with the bars set by
# the caller: [kind, sizes, starts] per side.
BARS_JS = r"""([name, header, starts]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.name === name);
    const keep = { b: l.riggingBars, s: l.riggingBarStarts };
    l.riggingBars = header; l.riggingBarStarts = starts;
    const book = { measureCtx: document.createElement('canvas').getContext('2d'),
                   geo: app._bGeo({ w: 3400, h: 2200 }, true) };
    let rows = null;
    const origT = app._bTableLines;
    app._bTableLines = function (bk, spec) {
        if (spec.title === 'Bars') rows = spec.rows.map(r => r.cells.slice());
        return origT.apply(this, arguments);
    };
    try { app._bSimpleBarList(book, l); }
    finally { app._bTableLines = origT; l.riggingBars = keep.b; l.riggingBarStarts = keep.s; }
    return rows;
}"""

GROUP_BARS_JS = r"""() => {
    const app = window.app;
    const L = app.project.layers.find(x => x.name === 'DOWNSTAGE LEFT SIDE FILL');
    const R = app.project.layers.find(x => x.name === 'DOWNSTAGE RIGHT SIDE FILL');
    const book = { measureCtx: document.createElement('canvas').getContext('2d'),
                   geo: app._bGeo({ w: 3400, h: 2200 }, true) };
    let rows = null;
    const origT = app._bTableLines;
    app._bTableLines = function (bk, spec) {
        if (spec.title === 'Bars') rows = spec.rows.map(r => r.cells.slice());
        return origT.apply(this, arguments);
    };
    const s = { kind: 'group', name: 'PAIR', layers: [L, R], members: [L, R], carriers: [L, R], member: null };
    try { app._bSimpleBarList(book, s); } finally { app._bTableLines = origT; }
    return rows;
}"""


def test_the_bar_list_numbers_columns_as_the_ruler_does(page):
    """A group sheet's bars are numbered by the group ruler, straight through
    the wall (WALL-R's first bar is column 9, not 1); a footer row says
    Footer, a header row Header; and a bar hanging past the wall's edge is
    never cut to the wall - its row says so."""
    pg, errors = page
    _walls(pg)
    rows = pg.evaluate(GROUP_BARS_JS)
    left = [r for r in rows if r[0] == 'DOWNSTAGE LEFT SIDE FILL · Header']
    right = [r for r in rows if r[0] == 'DOWNSTAGE RIGHT SIDE FILL · Header']
    foot = [r for r in rows if r[0] == 'DOWNSTAGE LEFT SIDE FILL · Footer']
    assert [r[2] for r in left] == ['1-2', '3-4', '5-6', '7-8'], rows
    assert [r[2] for r in right] == ['9-10', '11', '12', '13-14', '15-16'], rows
    assert [r[1:3] for r in foot] == [['Footer Bar - Quad', '1-4'], ['Footer Bar - Quad', '5-8']], rows
    # a double laid on the 36-column wall's last column: it hangs one panel
    # past the edge, and the list says so rather than cutting it to 36
    past = pg.evaluate(BARS_JS, ['UPSTAGE CENTER WIDE BACKDROP WALL', [2], [35]])
    assert past == [['Header', 'Header Bar - Double', '36 · past the edge']], past
    assert errors == []


def test_the_wiring_tick_stands_off_in_simple(page):
    """Simple prints each screen's wiring drawings as its sheets, so the
    Wiring tick is off and greyed there, its tooltip saying why, and back as
    it was in Full."""
    pg, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        app.openExportModal('binder');
        const box = document.getElementById('export-binder-wiring');
        const label = document.getElementById('export-binder-wiring-label');
        const full0 = label.getAttribute('data-tooltip');
        document.getElementById('export-binder-mode-simple').click();
        const simple = { disabled: box.disabled, tip: label.getAttribute('data-tooltip') };
        document.getElementById('export-binder-mode-full').click();
        const full = { disabled: box.disabled, tip: label.getAttribute('data-tooltip') };
        document.getElementById('export-cancel').click();
        return { full0, simple, full };
    }""")
    assert out['simple']['disabled'] is True and out['simple']['tip'].startswith('Not used in Simple'), out
    assert out['full'] == {'disabled': False, 'tip': out['full0']}, out
    assert errors == []


def test_the_export_logs_its_mode_and_sheets_by_kind(page):
    """export_binder_start says Full or Simple and how many sheets of each
    kind it sends."""
    pg, errors = page
    _walls(pg)
    out = pg.evaluate("""async () => {
        const app = window.app;
        const sent = [];
        const beacon = navigator.sendBeacon;
        navigator.sendBeacon = (url, blob) => { blob.text().then(t => sent.push(JSON.parse(t))); return true; };
        const f = window.fetch;
        window.fetch = (url, init) => String(url).includes('/api/export/pdf-from-pages')
            ? Promise.resolve(new Response(new Blob(['%PDF']), { status: 200 })) : f(url, init);
        const save = app.saveBlobWithPicker;
        app.saveBlobWithPicker = async () => true;
        app.openExportModal('binder');
        document.getElementById('export-binder-mode-simple').click();
        try { await app.exportBinder('x'); } finally {
            navigator.sendBeacon = beacon; window.fetch = f; app.saveBlobWithPicker = save;
            document.getElementById('export-binder-mode-full').click();
            document.getElementById('export-cancel').click();
        }
        await new Promise(r => setTimeout(r, 300));
        const start = sent.find(s => s.action === 'export_binder_start');
        return start ? start.details : null;
    }""")
    assert out and out['mode'] == 'simple', out
    assert out['kinds'].get('wiring', 0) >= 8 and 'power' not in out['kinds'] and 'data' not in out['kinds'], out
    assert sum(out['kinds'].values()) == out['pages'], out
    assert errors == []


@pytest.mark.parametrize('show', ['walls', 'nine'])
def test_nothing_on_a_simple_sheet_runs_out_of_the_drawing_area(page, show):
    """Every simple sheet - and every other sheet of the simple set - on
    every paper size, the title block on and off: not one mark past the
    drawing area's edge."""
    pg, errors = page
    if show == 'walls':
        _walls(pg)
    else:
        out = pg.evaluate(NINE_JS)
        assert out['layers'] == 9, out
    bad = []
    for sheet in ('letter', 'tabloid', 'archc', 'archd', 'a4', 'a3'):
        for tb in (True, False):
            report = pg.evaluate(BOUNDS_JS, [_simple(sheet=sheet, titleBlock=tb), TOL])
            assert any(s['kind'] == 'wiring' for s in report), (sheet, tb)
            bad += ['%s %s: %s' % (sheet, 'block' if tb else 'no block', line) for line in _offenders(report)]
    assert not bad, '\n' + '\n'.join(bad)
    assert errors == []
