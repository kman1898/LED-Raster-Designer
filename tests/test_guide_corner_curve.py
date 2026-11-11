"""The guide's corner steps leave the Curve building cleanly on each side.

QA report (2026-11-11, dev/draft caca84a7): Bend a corner and Corner bars
(Advanced 88 and 89 of 145, What's New in 1.7 12 and 13 of 45) both said
done while the Header/Footer tab warned. The Curve step had left the demo
wall curved at 7.5% of a circle on locks of 7.5 degrees at most, and Bend
a corner moved its corner down the middle of panel 6. With a corner each
side curves as its own wall at the Curve's % (owner, 2026-11-10), and the
5.5 panel left side could not reach it: "Out of range", "Off the drawing
... 5 in", 4.8% built against 7.5% asked, and the build in use marked
"over" in orange under Ways to build it.

The rule here: after each corner step (and the Curve step before them,
and Interior or Exterior after), the tab shows no "Out of range" and no
"Off the drawing" warning, and the build in use on every side is inside
Close enough (no orange "over" on it). Ways to build it also lists other
builds, ranked, and those may sit outside Close enough on any curved wall;
the one the tab builds may not. Each step's own check refuses a tab that
warns, so the guide can never say done over one.

Run locally:
    python -m pytest tests/test_guide_corner_curve.py -n 4 --dist loadfile
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_tour_anchors import _wait_step  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The guides mutate the shared server project and its preferences;
    leave both as this module found them."""


def _no_dialogs(route):
    route.fulfill(status=200, content_type='application/json',
                  body='{"ok": false, "cancelled": true}')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    # The snapshot builder's viewport, so the steps play on the walls the
    # shipped snapshots frame.
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _no_dialogs)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


@pytest.fixture(autouse=True)
def _guide_closed(page):
    yield
    page.evaluate("() => window.QuickStart.end()")
    page.wait_for_function(
        "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
        timeout=60000)


SPEED = 3
ORANGE = 'rgb(245, 166, 35)'

# The Curve as the Header/Footer tab shows it for DEMO WALL, once its
# answer has landed: the warnings shown, the errors shown, each side's
# readout title, and every row of Ways to build it (its two lines and the
# second line's color).
TAB_JS = """() => {
    const a = window.app;
    const w = a.project.layers.find(l => l.name === 'DEMO WALL');
    const shown = id => { const e = document.getElementById(id); return e && e.style.display !== 'none' ? e.textContent : ''; };
    const out = w && a.riggingCurveCached(w);
    return {
        on: !!(w && w.riggingCurve && w.riggingCurve.on),
        busy: a.riggingCurveBusy(),
        laid: !!(out && !out.errors.length && a._curveLaidMatches(w, out)),
        corners: (w && w.riggingCorners || []).map(c => c.at),
        warnings: shown('rigging-curve-warnings'),
        errors: shown('rigging-curve-errors'),
        asked: w && w.riggingCurve ? Number(w.riggingCurve.value) : null,
        sides: [...document.querySelectorAll('#rigging-curve-readouts > div')]
            .map(r => r.children[0] && r.children[0].textContent).filter(t => / side, |^Side \\d+, /.test(t || '')),
        sweeps: [...document.querySelectorAll('#rigging-curve-readouts > div')]
            .filter(r => r.children.length === 2 && r.children[0].textContent === 'Sweep')
            .map(r => r.children[1].textContent),
        ways: [...document.querySelectorAll('#rigging-curve-ways .rigging-curve-way')].map(e => {
            const t = e.firstElementChild.children;
            return {top: t[0].textContent, bottom: t[1].textContent, color: getComputedStyle(t[1]).color};
        }),
    };
}"""


def _tab(page):
    page.wait_for_function("() => !window.app.riggingCurveBusy()", timeout=30000)
    return page.evaluate(TAB_JS)


def _problems(tab, where, sides):
    """Everything the tab says is wrong with the Curve, in words."""
    out = []
    if not tab['on'] or not tab['laid']:
        out.append(f"{where}: the Curve is not laid ({tab})")
    if tab['errors'].strip():
        out.append(f"{where}: the tab shows an error: {tab['errors']!r}")
    for word in ('Out of range', 'Off the drawing'):
        if word in tab['warnings']:
            out.append(f"{where}: the tab warns {word!r}: {tab['warnings']!r}")
    in_use = [r for r in tab['ways'] if r['top'].endswith(', in use')]
    if len(in_use) != max(1, sides):
        out.append(f"{where}: {len(in_use)} builds in use for {sides} sides: {tab['ways']}")
    for r in in_use:
        if r['bottom'].endswith(', over') or r['color'] == ORANGE:
            out.append(f"{where}: the build in use is over Close enough: {r}")
    if len(tab['sides']) != sides:
        out.append(f"{where}: {len(tab['sides'])} sides on the tab, {sides} wanted: {tab['sides']}")
    # what the wall, or each side, builds is within half a percent of what
    # the Curve asks (test_whats_new holds the Curve step to the same)
    if len(tab['sweeps']) != max(1, sides):
        out.append(f"{where}: {len(tab['sweeps'])} Sweep readouts for {sides} sides: {tab['sweeps']}")
    for s in tab['sweeps']:
        m = re.search(r'([\d.]+)% of a circle', s)
        if not m or tab['asked'] is None or abs(float(m.group(1)) - tab['asked']) > 0.5:
            out.append(f"{where}: builds {s!r} against {tab['asked']}% asked")
    return out


def _keys(page):
    return page.evaluate(
        "() => { const S = window.QuickStart.steps(); return window.QuickStart.tours().advanced"
        ".map(s => Object.keys(S).find(k => S[k] === s)); }")


# Each step, and how many sides DEMO WALL has once it is done.
STEPS = [('riggingCurve', 0), ('riggingCorner', 2), ('riggingCornerBars', 2), ('riggingCornerSide', 0)]


def test_advanced_corner_steps_leave_the_curve_clean(page):
    """The Advanced guide from Curve a wall through Interior or Exterior,
    by Next: every step takes and leaves the tab without a warning that
    the build falls short of the drawing."""
    keys = _keys(page)
    first = keys.index('riggingCurve')
    assert [k for k, _ in STEPS] == keys[first:first + len(STEPS)], keys[first:first + len(STEPS)]
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", SPEED)
    page.evaluate("() => { window.QuickStart.startAdvanced(); }")
    _wait_step(page, 0)
    page.evaluate("(n) => { window.QuickStart.jumpTo(n); }", first + 1)
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=first, timeout=240000)
    problems = []
    for j, (key, sides) in enumerate(STEPS):
        if j:
            page.locator('#qs-next').click()
        st = _wait_step(page, first + j, timeout=120)
        where = f"Advanced step {first + j + 1} ({key})"
        if st['state'] != 'done' or st['fail']:
            problems.append(f"{where} did not take: {st['state']} {st['note']!r}")
        problems += _problems(_tab(page), where, sides)
    assert not problems, "\n".join(problems)


def test_whats_new_corner_steps_leave_the_curve_clean(page):
    """What's New in 1.7 plays Bend a corner and Corner bars from their own
    entry snapshots: the same, on each."""
    keys = page.evaluate("() => window.QuickStart.newSteps('1.6.0', '1.7.0')")
    i = keys.index('riggingCorner')
    assert keys[i:i + 2] == ['riggingCorner', 'riggingCornerBars'], keys
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", SPEED)
    page.evaluate("(k) => { window.QuickStart.startSteps(k); }", ['riggingCorner', 'riggingCornerBars'])
    problems = []
    for j, key in enumerate(['riggingCorner', 'riggingCornerBars']):
        if j:
            page.locator('#qs-next').click()
        st = _wait_step(page, j, timeout=120)
        where = f"What's New {key}"
        if st['state'] != 'done' or st['fail']:
            problems.append(f"{where} did not take: {st['state']} {st['note']!r}")
        problems += _problems(_tab(page), where, 2)
    assert not problems, "\n".join(problems)


def test_the_corner_steps_refuse_a_tab_that_warns(page):
    """Each corner step's check reads the tab: with the corner moved down
    the middle of panel 6, where the shorter side cannot reach the Curve,
    neither Bend a corner nor Corner bars has a note to give."""
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", SPEED)
    page.evaluate("() => { window.QuickStart.startSteps(['riggingCornerBars']); }")
    st = _wait_step(page, 0, timeout=120)
    assert st['state'] == 'done' and not st['fail'], st
    at = page.evaluate("() => window.app.project.layers.find(l => l.name === 'DEMO WALL').riggingCorners[0].at")
    assert page.evaluate("(at) => !!window.QuickStart.steps().riggingCorner.check({at})", at)
    assert page.evaluate("() => !!window.QuickStart.steps().riggingCornerBars.check({})")
    page.evaluate("(at) => window.app.setRiggingCorner(at, 'at', '6')", at)
    page.wait_for_function(
        "() => window.app.project.layers.find(l => l.name === 'DEMO WALL').riggingCorners[0].at === 6",
        timeout=10000)
    page.wait_for_function(
        """() => { const a = window.app, w = a.project.layers.find(l => l.name === 'DEMO WALL');
                   const out = !a.riggingCurveBusy() && a.riggingCurveCached(w);
                   const e = document.getElementById('rigging-curve-warnings');
                   return out && a._curveLaidMatches(w, out) && /Out of range|Off the drawing/.test(e.textContent); }""",
        timeout=30000)
    assert page.evaluate("() => window.QuickStart.steps().riggingCorner.check({at: 6})") is None
    assert page.evaluate("() => window.QuickStart.steps().riggingCornerBars.check({})") is None
