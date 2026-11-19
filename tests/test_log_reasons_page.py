"""The log says why (2026-11-19 logging audit, phase 3), in the real app.

The page's lines for the choices it makes by itself and the refusals it
shows, each read off the beacons the page sends (window.__clog):

* a screen's automatic circuit plan is logged when it CHANGES, with its
  circuits, their amps and why they end where they do, and never on a
  redraw that changes nothing;
* a distro added, edited (what changed, old to new) and removed, and a
  phase balance applied with every leg's amps before and after;
* the Curve's answer as it lands: the bars, how many joints bend, the
  biggest, how many sit at the lock limit, the sweep reached;
* a guide step that passes says how long it took, and one that fails
  says which step, what it looked for and where the app stood, and the
  guide's end counts both (guides never fail, so a failure must show);
* a question dialog's title and answer, and a controller press once,
  never its repeats.

Run locally:
    python -m pytest tests/test_log_reasons_page.py -n 4 --dist loadfile
"""
import os
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_curve_obj import act, open_rigging, reset, singles_only  # noqa: E402
from test_tour_anchors import STATE_JS, _end, _wait_step  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
                            + CLIENT_LOG)
    pg = context.new_page()
    pg.errors = []
    pg.on('pageerror', lambda err: pg.errors.append(str(err)))
    pg.route('**/api/native-dialog/**', lambda r: r.fulfill(status=503, body='{}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)", timeout=30000)
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def lines(page, action):
    return page.evaluate("(a) => window.__clog.filter(x => x.action === a).map(x => x.details)", action)


def wait_line(page, action, pred='() => true', timeout=15000):
    """Until a line `action` whose details pass `pred` (a JS function of
    the details) has been sent; returns those details."""
    page.wait_for_function(
        f"(a) => window.__clog.some(x => x.action === a && ({pred})(x.details))", arg=action, timeout=timeout)
    return page.evaluate(
        f"(a) => window.__clog.filter(x => x.action === a && ({pred})(x.details)).pop().details", action)


def clear(page):
    page.evaluate("() => { window.__clog.length = 0; }")


# ── the automatic circuit plan ───────────────────────────────────────────

POWER_JS = """(args) => {
    const [id, watts] = args;
    const l = window.app.project.layers.find(x => x.id === id);
    l.panelWatts = watts; l.powerVoltage = 120; l.powerAmperage = 20;
    window.canvasRenderer.render();
}"""


def test_a_plan_is_logged_once_per_change_and_never_on_a_redraw(page):
    [lid] = reset(page, [{'name': 'PLAN', 'columns': 6, 'rows': 4, 'offset_x': 0, 'offset_y': 0}], locks=None)
    page.click('#view-tabs .view-tab[data-mode="power"]')
    # whatever the new screen's first plan says lands first
    page.wait_for_timeout(1500)
    clear(page)
    page.evaluate(POWER_JS, [lid, 200])
    first = wait_line(page, 'power_auto_planned', f'(d) => d.id === {lid}')
    assert first['name'] == 'PLAN' and first['circuits'] > 0
    assert len(first['perCircuit']) == first['circuits']
    assert sum(c[1] for c in first['perCircuit']) == 24, first
    assert all(c[2] is not None and c[2] <= 16 for c in first['perCircuit']), first
    assert first['limit'].startswith('a 20 A circuit')
    assert set(first['splits']) == {'full', 'lineEnd'}
    # the line's plain message (it rides to the server as _msg)
    assert re.match(rf"Power plan: PLAN \(#{lid}\): (\d+ to )?{first['circuits']} circuits on a 20 A circuit",
                    first['_msg']), first['_msg']
    assert '—' not in first['_msg'] and '–' not in first['_msg']

    # Redrawn over and over with nothing changed: no new line.
    clear(page)
    for _ in range(10):
        page.evaluate("() => { window.canvasRenderer.render(); window.app.updatePowerCapacityDisplay(); }")
        page.wait_for_timeout(120)
    page.wait_for_timeout(1500)
    assert lines(page, 'power_auto_planned') == []

    # Twice the watts a cabinet: a new plan, one line saying the change.
    page.evaluate(POWER_JS, [lid, 400])
    second = wait_line(page, 'power_auto_planned', f'(d) => d.id === {lid}')
    assert second['circuits'] > first['circuits']
    assert f"{first['circuits']} to {second['circuits']} circuits" in second['_msg']
    assert sum(c[1] for c in second['perCircuit']) == 24
    page.wait_for_timeout(1500)
    assert len(lines(page, 'power_auto_planned')) == 1
    assert page.errors == []


# ── distros and the phase balance ────────────────────────────────────────

def test_a_distro_and_a_balance_say_what_changed(page):
    reset(page, [{'name': 'D', 'columns': 4, 'rows': 2, 'offset_x': 0, 'offset_y': 0}], locks=None)
    clear(page)
    did = page.evaluate("() => window.app.addDistro({ name: 'LOG D', system: '120/208' }).id")
    added = wait_line(page, 'distro_added')
    assert added['id'] == did and added['name'] == 'LOG D' and added['system'] == '120/208'
    page.evaluate("(id) => window.app.updateDistro(id, { ratingA: 123 })", did)
    edited = wait_line(page, 'distro_edited')
    assert edited['diff']['ratingA'][1] == 123 and edited['diff']['ratingA'][0] != 123
    page.evaluate("() => window.app.applyPhaseBalance([])")
    applied = wait_line(page, 'phase_balance_applied')
    assert applied['moves'] == 0 and applied['screens'] == 0
    legs = applied['before']['LOG D']
    assert set(legs) >= {'imb'} and len(legs) >= 3, legs
    assert applied['after']['LOG D'] == legs
    page.evaluate("(id) => window.app.removeDistro(id)", did)
    removed = wait_line(page, 'distro_removed')
    assert removed['id'] == did and removed['name'] == 'LOG D'
    assert page.errors == []


# ── the Curve's answer ───────────────────────────────────────────────────

def test_the_curve_says_what_it_laid(page):
    [lid] = reset(page)
    open_rigging(page)
    singles_only(page)
    clear(page)
    act(page, lambda: page.check('#rigging-curve-on'))
    on = wait_line(page, 'curve_set')
    assert on['on'] is True and on['screens'] == ['WALL']
    solved = wait_line(page, 'curve_solved')
    lay = page.evaluate("(id) => window.app.project.layers.find(l => l.id === id)", lid)
    joints = [v for v in ((lay.get('stage3d') or {}).get('jointsCol') or {}).values()]
    assert solved['name'] == 'WALL' and solved['panels'] == 16
    assert solved['joints'] == sum(1 for a in joints if a) and solved['joints'] > 0
    assert solved['maxJoint'] == max(abs(a) for a in joints)
    assert solved['limit'] == 20 and solved['atLimit'] == 0
    assert sum(solved['bars']) == 16
    assert solved['asked']['bend'] in ('concave', 'convex')
    assert 'sweep' in solved
    assert page.errors == []


# ── guides ───────────────────────────────────────────────────────────────

def test_a_guide_step_that_passes_or_fails_is_in_the_log(page):
    at = page.evaluate("(k) => window.QuickStart.guideOf(k)", 'projectName')
    guide, i = at['tour'], at['index']
    clear(page)
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", 3)
    page.evaluate("(n) => { window.QuickStart.startTour(n); }", guide)
    started = wait_line(page, 'guide_started', timeout=120000)
    assert started['guide'] == guide and started['steps'] > i
    st = _wait_step(page, 0, timeout=120)
    while st['qs']['index'] < i:
        page.locator('#qs-next').click()
        st = _wait_step(page, st['qs']['index'] + 1, timeout=120)
    assert st['state'] == 'done', st
    passed = wait_line(page, 'guide_step_passed', "(d) => d.step === 'projectName'")
    assert passed['guide'] == guide and passed['n'] == i + 1 and passed['ms'] > 0

    # The same step again with a check that never answers: it fails, and
    # the line says which step, what it looked for and where the app was.
    page.evaluate("""() => {
        const s = window.QuickStart.steps().projectName;
        window.__origCheck = s.check;
        s.check = function () { return null; };
    }""")
    try:
        page.locator('#qs-replay').click()
        failed = wait_line(page, 'guide_step_failed', "(d) => d.step === 'projectName'", timeout=60000)
    finally:
        page.evaluate("() => { window.QuickStart.steps().projectName.check = window.__origCheck; }")
    assert failed['guide'] == guide and failed['n'] == i + 1
    assert failed['target'] == '#project-name' and failed['targetFound'] is True
    assert failed['view'] == 'pixel-map'
    assert failed['error'] == 'its check never answered'
    assert failed['ms'] >= 9000
    assert page.evaluate(STATE_JS)['fail']
    _end(page)
    ended = wait_line(page, 'guide_ended')
    assert ended['guide'] == guide and ended['failed'] == 1 and ended['passed'] >= 1
    assert ended['at'] == i + 1 and ended['finished'] is False
    assert page.errors == []


# ── dialogs and the controller ───────────────────────────────────────────

def test_a_dialog_and_a_controller_press_are_one_line_each(page):
    clear(page)
    page.evaluate("() => { window.__answer = window.app.appConfirm('Take the bars off?', { title: 'Clear bars', okLabel: 'Clear' }); }")
    page.wait_for_selector('.app-ask-modal')
    opened = wait_line(page, 'app_dialog_open')
    assert opened['title'] == 'Clear bars' and opened['question'] == 'Take the bars off?'
    page.click('.app-ask-modal .btn-primary')
    answered = wait_line(page, 'app_dialog_answered')
    assert answered['answer'] == 'Clear' and answered['via'] == 'button' and answered['value'] is True
    page.evaluate("""() => {
        const app = window.app;
        app._idmPadLog({ type: 'press', button: 0 }, false);
        app._idmPadLog({ type: 'move', dir: 'up', cabinet: false }, false);
        for (let k = 0; k < 5; k++) app._idmPadLog({ type: 'move', dir: 'up', cabinet: false }, true);
        app._idmPadLog({ type: 'release', button: 0 }, false);
        app._idmPadLog({ type: 'press', button: 1 }, false);
    }""")
    time.sleep(0.5)
    pads = lines(page, 'pad_button')
    assert [(p['button'], p['action']) for p in pads] == [('A', 'mark'), ('D-pad', 'move')], pads
    assert page.errors == []
