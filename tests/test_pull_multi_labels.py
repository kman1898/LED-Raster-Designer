"""The pull sheet's labels never fold a run of MULTIS into a hyphen range
(QA beta.5, 2026-11-03): a TRUE1 Breakout row read "PD UPSTG 1-3" for
multis 1 to 3, over TRUE1 rows where "PD UPSTG 1-3" is multi 1's circuit
3. Multis fold the way the ruling for digit-ending distro names does: two
read "PD UPSTG1, PD UPSTG2", three or more "PD UPSTG1 … 3".

And the pull sheet's overflow notice says "is" for one position and "are"
for several ("WALL went to the Overflow tab and are not in TOTALS").

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_pull_multi_labels.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

import pull_sheet  # noqa: E402


# ── the overflow notice (server) ──────────────────────────────────────────

def _positions(n):
    rows = [{'type': 'Multi', 'length': "100'", 'qty': 1, 'label': '', 'notes': ''}]
    return {'positions': [{'name': f'P{i}', 'rows': rows} for i in range(n)]}


def test_one_overflowing_position_is_not_in_totals():
    _, warnings = pull_sheet.build_workbook(_positions(pull_sheet.MAX_POSITIONS + 1))
    last = f'P{pull_sheet.MAX_POSITIONS}'
    assert warnings == [f'The sheet holds {pull_sheet.MAX_POSITIONS} positions; {last} went to the '
                        'Overflow tab and is not in TOTALS or Spares.'], warnings


def test_several_overflowing_positions_are_not_in_totals():
    n = pull_sheet.MAX_POSITIONS
    _, warnings = pull_sheet.build_workbook(_positions(n + 2))
    assert warnings == [f'The sheet holds {n} positions; P{n}, P{n + 1} went to the '
                        'Overflow tab and are not in TOTALS or Spares.'], warnings


# ── the labels (browser) ──────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_r3_fixes import HELPERS_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.evaluate(HELPERS_JS)
    yield pg
    assert errors == [], errors
    context.close()


# One screen of `cols` circuits (five cabinets each, tl-v) on a distro
# named PD UPSTG: six circuits to a multi. The multis' names, and the pull
# list's Multi and Breakout rows.
LIST_JS = """async (cols) => {
    const pu = window.__pu;
    await pu.open(pu.project([{columns: cols, powerSocaDistro: {'1': 'd2', '2': 'd2', '3': 'd2'}}],
        {distros: [{id: 'd2', name: 'PD UPSTG', ratingA: 400, system: '120/208', voltage: 208, phase: 3}]}));
    const app = window.app;
    const list = app.buildPullList();
    const rows = (type) => list.totals.filter(r => r.type === type).map(r => r.label);
    return {names: [...app.distroBoxLabels().values()], multi: rows('Multi'),
            breakout: rows('TRUE1 Breakout')};
}"""


def test_three_multis_read_first_to_last(page):
    """PD UPSTG1, PD UPSTG2, PD UPSTG3 (the names the distro gives them)
    read "PD UPSTG1 … 3" on their Multi and Breakout rows - never "PD UPSTG
    1-3", which reads as a circuit of multi PD UPSTG1."""
    out = page.evaluate(LIST_JS, 15)
    assert out['names'] == ['PD UPSTG1', 'PD UPSTG2', 'PD UPSTG3'], out
    assert out['breakout'] == ['PD UPSTG1 … 3'], out
    assert out['multi'] == ['PD UPSTG1 … 3'], out
    assert not [t for t in out['breakout'] + out['multi'] if re.search(r'\d-\d', t)], out


def test_two_multis_read_both_names(page):
    out = page.evaluate(LIST_JS, 12)
    assert out['names'] == ['PD UPSTG1', 'PD UPSTG2'], out
    assert out['breakout'] == ['PD UPSTG1, PD UPSTG2'], out
    assert out['multi'] == ['PD UPSTG1, PD UPSTG2'], out


def test_a_run_with_a_multi_in_it_never_folds_with_a_hyphen(page):
    """Multis PD UPSTG2 and PD UPSTG3 beside a plain name PD UPSTG4 (not a
    multi) read "PD UPSTG2 … 4", never "PD UPSTG 2-4"."""
    page.evaluate(LIST_JS, 15)
    out = page.evaluate("() => window.app._pullCompressNames(['PD UPSTG2', 'PD UPSTG3', 'PD UPSTG4'])")
    assert out == 'PD UPSTG2 … 4', out
    assert not re.search(r'\d-\d', out), out
