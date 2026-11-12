"""What every subject guide's own test module proves (tests/test_guide_*.py).

The one Advanced Guide became seven guides by subject under Help > Guides
(owner, 2026-11-11): Pixel Map, Data, Power, Header/Footer and Curves, 3D
and Output, IDM, and Binder and Exports. Each starts from a demo show of
its own (src/static/js/quickstart.js enterGuide: the scratch show with its
prep steps done, restored from the shipped snapshot file), so each stands
alone, and each has a test module of its own that proves, for that guide:

  - it STARTS on its own demo show, in one restore of the shipped file,
    holding what its subject builds on and nothing past it;
  - every step TAKES by Next, first time: its anchor resolves and is seen
    in the step's view, its check returns a note, and the callout holds
    still (placed once, moved at most once more);
  - Go to EVERY step lands on that step's shipped entry snapshot within
    three seconds, with no shade, and the step then takes.

Guides never fail (owner, 2026-11-03): a step that fails here at random is
a race in the app or the step, never a test to retry.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from test_tour_anchors import STATE_JS, CHECK_TARGET_JS, _wait_step, _end   # noqa: E402

# The snapshot builder's viewport, so the steps play on the walls the
# shipped snapshots frame.
VIEWPORT = {'width': 1600, 'height': 950}
# The shipped gestures, three times faster (every pace in quickstart.js
# scales with setSpeed; the waits on the app do not).
DRIVE_SPEED = 3
# A guide's start is one restore of its demo show; this is room for a
# loaded machine, never for the prep applied step by step (a stale file
# fails the start test instead).
START_TIMEOUT = 120


def _no_dialogs(route):
    route.fulfill(status=200, content_type='application/json',
                  body='{"ok": false, "cancelled": true}')


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The guides mutate the shared server project and its preferences;
    leave both as this module found them."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport=VIEWPORT)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real save or open dialog may come up on the desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _no_dialogs)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)",
        timeout=120000)
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


def start(page, guide, speed=DRIVE_SPEED):
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", speed)
    page.evaluate("(n) => { window.QuickStart.startTour(n); }", guide)
    return _wait_step(page, 0, timeout=START_TIMEOUT)


def step_count(page, guide):
    return page.evaluate("(n) => window.QuickStart.tours()[n].length", guide)


# What a guide's demo show holds, read the same way for every guide.
DEMO_SHOW_JS = """() => {
    const a = window.app, p = a.project;
    return {
        name: p.name,
        screens: (p.layers || []).map(l => l.name),
        processors: (a._processorsResolved || []).length,
        distros: (a.getDistros ? a.getDistros() : []).length,
        services: (a.getServices ? a.getServices() : []).length,
        beaches: (p.beaches || []).length,
        groups: (p.groups || []).length,
    };
}"""


def check_start(page, guide, want, via='snapshot'):
    """The guide opens on its own demo show (`want`, DEMO_SHOW_JS's shape),
    got the way `via` says, and its intro is on screen."""
    st = start(page, guide)
    assert st and st['qs']['index'] == 0 and st['state'] == 'idle', st
    qs = page.evaluate("window.QuickStart.state()")
    assert qs['tour'] == guide and qs['startedVia'] == via, qs
    show = page.evaluate(DEMO_SHOW_JS)
    assert show == want, show
    # Undo never takes the demo show back to the scratch show.
    assert page.evaluate("() => window.app.historyIndex") <= 0


def drive_whole_guide(page, guide):
    """The guide from its first step to its last by Next: every step's
    anchor resolves and is visible once its act settled, its check
    returned a note, and the callout moved at most once after it was
    placed (the complaint of 2026-09-14: "too much jumping after an action
    is done"). Every failing step is named in one message."""
    problems = []
    n = step_count(page, guide)
    # The engine records every placement of the callout (where and by
    # whom) when this hook is armed - see quickstart.js place().
    page.evaluate("window.__qsTrace = []")
    st = start(page, guide)
    for i in range(n):
        st = _wait_step(page, i)
        where = f"{guide} step {i + 1} ({st['title']!r})"
        if not st or st['qs']['index'] != i:
            problems.append(f"{where}: the engine never settled on this step ({st})")
            break
        res = page.evaluate(CHECK_TARGET_JS, [guide, i])
        if res['found'] is False:
            problems.append(f"{where}: selector {res['target']!r} matches nothing")
        elif res['found'] and not res['visible']:
            problems.append(f"{where}: {res['target']!r} is 0x0 in this step's view")
        if st['state'] == 'failed' or st['fail']:
            problems.append(f"{where}: check() returned null - {st['note']!r}")
        elif st['state'] == 'done' and not st['note'].strip():
            problems.append(f"{where}: no result note")
        if i < n - 1:
            page.locator('#qs-next').click()
    trace = page.evaluate("window.__qsTrace || []")
    titles = page.evaluate("(n) => window.QuickStart.tours()[n].map(s => s.title)", guide)
    moves = {}
    for e in trace:
        pos = (e['x'], e['y'])
        seq = moves.setdefault(e['step'], [])
        if not seq or seq[-1][0] != pos:
            seq.append((pos, e['by'].split('(')[0].strip()))
    for step, seq in sorted(moves.items()):
        if len(seq) > 2:
            problems.append(f"{guide} step {step + 1} ({titles[step]!r}): the callout "
                            f"moved {len(seq) - 1} times after it was placed: {seq}")
    # Done on the last step puts the person's world back.
    page.locator('#qs-next').click()
    page.wait_for_function(
        "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
        timeout=60000)
    assert not problems, "\n".join(problems)


LANDING_JS = """() => ({
    index: window.QuickStart.state().index,
    via: window.QuickStart.state().jumpedVia,
    shade: getComputedStyle(document.getElementById('qs-fast')).display,
    jumping: document.body.classList.contains('qs-jumping'),
    callout: getComputedStyle(document.getElementById('qs-callout')).visibility,
})"""


def go_to_step(page, guide, i, within=3.0):
    """From a fresh start of `guide`, type step i+1 into Go to and press
    Enter: the engine is on the step within `within` seconds, by one
    restore of the shipped entry snapshot and no shade, and the step then
    takes."""
    st = start(page, guide)
    assert st['qs']['index'] == 0, st
    page.fill('#qs-jump', str(i + 1))
    t0 = time.time()
    page.press('#qs-jump', 'Enter')
    landed = None
    while time.time() - t0 < within:
        if page.evaluate("window.QuickStart.state().index") == i:
            landed = time.time() - t0
            break
        time.sleep(0.02)
    landing = page.evaluate(LANDING_JS)
    st = _wait_step(page, i)
    where = f"{guide} step {i + 1} ({st['title'] if st else '?'!r})"
    assert landed is not None, f'{where}: not on the step within {within} s ({landing})'
    assert landing['via'] == 'snapshot', f'{where}: landed via {landing["via"]!r}, not the snapshot'
    assert landing['shade'] == 'none' and not landing['jumping'], f'{where}: the shade was up: {landing}'
    assert st and st['qs']['index'] == i, f'{where}: the engine never settled ({st})'
    assert st['state'] in ('done', 'idle') and not st['fail'], f"{where}: {st['state']} - {st['note']!r}"
    if st['state'] == 'done':
        assert st['note'].strip(), f'{where}: done, but no result note'
    _end(page)
