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
                                      _offenders, _opts, page)  # noqa: F401


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
    circuits = [t for t in power['tables'] if t['title'] == 'Circuits']
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


def test_the_drawing_takes_the_room_its_tables_leave(page):
    """The drawing's room is the drawing area less its bubble and its tables'
    band: the shorter the tables, the bigger the drawing ("always prefer a
    bigger drawing")."""
    pg, errors = page
    _walls(pg)
    out = pg.evaluate("""(opts) => {
        const app = window.app;
        const plan = app.planBinder(opts);
        const res = [];
        plan.forEach((p, i) => {
            if (p.layout !== 'simple' || p.kind !== 'wiring') return;
            const r = app.renderBinderPage(opts, i);
            res.push({ title: p.title, wiring: r.wiring, da: app._bGeo({w: r.record.width, h: r.record.height},
                                                                       opts.titleBlock !== false).da });
        });
        return res;
    }""", _simple(sheet='letter'))
    assert out, 'no simple sheet'
    for s in out:
        half = s['wiring']['halves'][0]
        area = half['area']
        # (the drawing keeps 45 % of the area at least; its rulers' head
        # and its bubble come out of that)
        assert area['h'] >= 0.45 * s['da']['h'] - 96 - 52 - 1, (s['title'], area, s['da'])
        assert area['y'] + area['h'] <= s['da']['y'] + s['da']['h'] - 96 + 1, (s['title'], area, s['da'])
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
