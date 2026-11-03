"""Binder fixes from the 1.6.0 QA pass.

  * A circuit over its limit (the app's own test: its amps past
    circuitCapacity, the one that turns it red) prints OVER beside its amps
    in CIRCUITS and SHARED CIRCUITS, as the map's tag does; FACTS gains an
    Over row; the export warns, naming the screens and circuits, and still
    exports. A custom wall drawn at 19.2 A on a 20 A breaker printed clean.
  * No em dash on the paper (owner, 2026-11-03: "get rid of the em
    dashes"): an empty cell is blank, a range a plain hyphen ("6-12").
  * The pull sheet editor's Export Binder prints on the saved sheet size,
    not on the select's first option before the Export dialog has opened.
  * A screen with two multis on one box is named once on the distro sheet.

Run locally:
    python -m pytest tests/test_binder_over_and_blanks.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_paper_r4 import BINDER_JS  # noqa: E402
from test_paper_r5 import SEED_JS  # noqa: E402
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
    pg.evaluate(SEED_JS)
    pg.wait_for_function("() => window.app.project.layers.length === 3")
    yield pg, errors
    context.close()


OPTS_JS = ("Object.assign(app.readBinderOptions(), { scope: { kind: 'show' }, "
           "sides: { power: true, data: false } })")


# WALL A hand-drawn at 208 V / 20 A (16 A usable at 80%), 200 W panels:
# circuit 1 one row of ten (2,000 W, 9.6 A), circuit 2 two rows of ten
# (4,000 W, 19.2 A) - over. Both on PD's soca 1.
OVER = {
    'powerAmperage': 20, 'powerFlowPattern': 'custom', 'powerCustomIndex': 3,
    'powerCustomPaths': {
        '1': [{'row': 0, 'col': k} for k in range(10)],
        '2': [{'row': r, 'col': k} for r in (1, 2) for k in range(10)],
    },
    'powerSocaDistro': {'1': 'd1'},
}


def _power_sheet(b, name):
    return next(p for p in b['pages'] if p['kind'] == 'power' and p['title'].startswith(name))


def test_a_circuit_over_its_limit_prints_over_and_the_export_warns(page):
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': OVER})
    amps = ev(pg, "return app.getSocaPlan(A).flatMap(s => s.legs).map(l => [l.label, +l.amps.toFixed(1)]);")
    assert [a for _, a in amps] == [9.6, 19.2], amps
    over_label = amps[1][0]
    # the app's own reading turns it red: the tray's chip and the binder
    # agree on the one test (circuitCapacity)
    assert ev(pg, "return app.circuitCapacity(A).amps;") == 16
    b = pg.evaluate(BINDER_JS, {'kinds': ['power']})
    circuits = [t for t in b['tables'] if t['title'] == 'Circuits']
    cells = {r[0]: r for t in circuits for r in t['rows']}
    assert cells[amps[0][0]][3] == '9.6', cells
    assert cells[over_label][3] == '19.2 · OVER', cells
    facts = [k for k in b['kv'] if k['title'] == 'Facts']
    over = [p for k in facts for p in k['pairs'] if p[0] == 'Over']
    # (the sheet is laid out more than once: each pass the same row)
    assert over and all(p == ['Over', '1 circuit over a 20 A circuit held to 16 A (80%)'] for p in over), facts
    sheet = _power_sheet(b, 'WALL A')
    assert '19.2 · OVER' in sheet['logged'], sheet['logged']
    # the export's warning: one message, the screen and its circuit, the
    # limit said once; WALL B is under its limit and not named
    warn = ev(pg, f"return app.binderOverWarning({OPTS_JS});")
    assert warn == (f'Circuits over their limit print marked OVER: WALL A, 1 circuit up to 19.2 A '
                    f'({over_label}). Each is a 20 A circuit held to 16 A (80%).'), warn
    assert '—' not in warn and ' - ' not in warn, warn
    # a data-only binder prints no circuits, so it warns about none
    data_only = ev(pg, "return app.binderOverWarning(Object.assign(app.readBinderOptions(), "
                       "{ scope: { kind: 'show' }, sides: { power: false, data: true } }));")
    assert data_only == '', data_only
    # under the limit: no mark, no Over row, no warning
    setup(pg, distros=[DIST], walls={'a': dict(OVER, powerAmperage=30)})
    b = pg.evaluate(BINDER_JS, {'kinds': ['power']})
    assert not [r for t in b['tables'] if t['title'] == 'Circuits' for r in t['rows'] if 'OVER' in r[3]], b['tables']
    assert not [p for k in b['kv'] for p in k['pairs'] if p[0] == 'Over'], b['kv']
    assert ev(pg, f"return app.binderOverWarning({OPTS_JS});") == ''
    assert errors == [], errors


def test_an_amps_cell_reads_over_by_the_screens_own_limit(page):
    """The SHARED CIRCUITS table's amps go through the same cell: past the
    carrier's usable amps it says OVER; at it, not."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {'powerAmperage': 20}})
    out = ev(pg, "return [app._bAmpsCell(A, 16), app._bAmpsCell(A, 16.04), app._bAmpsCell(A, 17.6)];")
    assert out == ['16.0', '16.0 · OVER', '17.6 · OVER'], out
    assert errors == [], errors


def test_the_paper_has_no_em_dash_and_ranges_use_a_hyphen(page):
    """Every power sheet, the pull pages and the hardware pages: no em dash
    and no en dash anywhere they print - an empty CABLE cell is blank, and
    the FACTS panels range reads "10-20 panels each"."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': OVER})
    b = pg.evaluate(BINDER_JS, {})
    for p in b['pages']:
        bad = [t for t in p['logged'] + p['texts'] if '—' in t or '–' in t]
        assert not bad, (p['title'], bad)
    circuits = [r for t in b['tables'] if t['title'] == 'Circuits' for r in t['rows']]
    assert circuits and all(r[4] == '' for r in circuits), circuits
    facts = [p for k in b['kv'] if k['title'] == 'Facts' for p in k['pairs'] if p[0] == 'Circuits']
    assert ['Circuits', '2 at 208 V / 20 A · 10-20 panels each'] in facts, facts
    assert errors == [], errors


def test_the_saved_sheet_size_wins_over_a_select_not_yet_synced(page):
    """The select is filled on its first option (Letter) at start-up and
    synced only when the Export dialog opens: the pull sheet editor's
    Export Binder read the select and printed Letter."""
    pg, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const was = app.getBinderSheet();
        app.setBinderSheet('tabloid');
        const sel = document.getElementById('export-binder-sheet');
        sel.value = 'letter';
        const got = app.readBinderOptions().sheet;
        app.setBinderSheet(was);
        return got;
    }""")
    assert out == 'tabloid', out
    assert errors == [], errors


# The Distro page's rows: each box's cells, caught as the page builds them.
DISTRO_ROWS_JS = """() => {
    const app = window.app;
    const caught = [];
    const orig = app._bDistroBlocks;
    app._bDistroBlocks = function (book, d, load, boxes) {
        caught.push(...boxes.map(b => b.cells));
        return orig.apply(this, arguments);
    };
    try {
        app.planBinder(Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false }));
    } finally { app._bDistroBlocks = orig; }
    return caught;
}"""


def test_a_screen_on_two_multis_of_one_box_is_named_once(page):
    """WALL A's circuits split onto two multis (a split after circuit 1),
    both numbered PD 1: the distro sheet's SCREENS said "WALL A + WALL A"."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={'a': {
        'powerSocaSplits': [1], 'powerSocaDistro': {'1': 'd1', '2': 'd1'},
        'powerSocaNumber': {'1': 1, '2': 1}}})
    assert ev(pg, "return app.getSocaPlan(A).length;") == 2
    rows = pg.evaluate(DISTRO_ROWS_JS)
    mine = [r for r in rows if 'WALL A' in r[3]]
    assert mine and all(r[3] == 'WALL A' for r in mine), rows
    assert errors == [], errors
