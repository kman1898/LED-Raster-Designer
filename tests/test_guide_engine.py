"""The guide engine never lets a step fail from timing or from the person's
own hand (Matt, 2026-11-03: every guide step passes first time, every time).

src/static/js/quickstart.js, pinned here:

  - a step's check is POLLED after the app settles, never asked once: a
    check that answers late still passes, one that never answers fails
    only after the engine's limit;
  - the INPUT SHIELD: while a step runs, the person's real mouse, wheel
    and keys never reach the app (a resting hand moved the tray's drag off
    its target, a second click on Next shut the popover the act opened),
    Next does nothing, and between steps only the callout takes input;
  - every step STARTS FROM A KNOWN STATE: the replay button after a step
    that left a redraw armed plays the step again and it takes;
  - NO PREFERENCES LEAK into the guide: it runs on the shipped Preferences
    (a 10-bit, 30 Hz or 230/400 preference cut the practice screens into
    other ports and gave the service a system its distro could not join),
    on a scratch show with one canvas, and the person's own come back;
  - the Advanced steps that failed under a hand on the mouse and Matt's
    Preferences in the 1.6.0 QA pass, played with a wandering mouse and a
    double click on Next, all take.

Run locally (each session takes its own free port):
    python -m pytest tests/test_guide_engine.py -v --browser chromium
"""

import os
import random
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_tour_anchors import _end, _wait_step, STATE_JS   # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The guides mutate the shared server project and its preferences;
    leave both as this module found them."""


VIEWPORT = {'width': 1600, 'height': 950}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport=VIEWPORT)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


@pytest.fixture(autouse=True)
def _guide_closed(page):
    yield
    if page.evaluate("window.QuickStart.state().visible"):
        _end(page)
        page.wait_for_function(
            "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
            timeout=30000)


PREFS_JS = """async (patch) => {
    const r = await fetch('/api/preferences');
    const prefs = await r.json();
    if (patch) {
        Object.assign(prefs, patch);
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(prefs)});
        window.app._serverPreferences = prefs;
    }
    return prefs;
}"""

# Matt's own Preferences (Brompton, 10-bit, 30 Hz, Low Latency off), and a
# distro system the guide's 120/208 distro cannot join.
MATT_PREFS = {'processorType': 'brompton', 'bitDepth': 10, 'frameRate': 30,
              'lowLatency': False, 'distroSystem': '230/400'}


@pytest.fixture
def matt_prefs(page):
    original = page.evaluate(PREFS_JS, None)
    page.evaluate(PREFS_JS, MATT_PREFS)
    yield original
    # The guide first (its exit puts back the Preferences it found), then
    # the module's own.
    if page.evaluate("window.QuickStart.state().visible"):
        _end(page)
        page.wait_for_function(
            "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
            timeout=30000)
    page.evaluate("""async (prefs) => {
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(prefs)});
        window.app._serverPreferences = prefs;
    }""", original)


def _index(page, key):
    """The Advanced step `key`'s index (0-based)."""
    i = page.evaluate("""(k) => {
        const s = window.QuickStart.steps()[k];
        return window.QuickStart.tours().advanced.indexOf(s);
    }""", key)
    assert i is not None and i >= 0, key
    return i


def _open_advanced(page, speed):
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", speed)
    page.evaluate("() => { window.QuickStart.startTour('advanced'); }")
    return _wait_step(page, 0)


def _go_to(page, i):
    """Go to step i (0-based) the way the Go to box does it; returns as soon
    as the step is on screen (its act may still be running)."""
    page.evaluate("(n) => { window.QuickStart.jumpTo(n); }", i + 1)
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i, timeout=60000)


# Every real (trusted) event the app could see while a step runs, caught
# by a document listener - which the shield, on the window, runs before.
LEAK_JS = """() => {
    window.__leak = [];
    if (window.__leakArmed) return;
    window.__leakArmed = true;
    ['mousemove', 'mousedown', 'mouseup', 'click', 'contextmenu', 'wheel',
     'pointerdown', 'pointermove', 'keydown', 'keyup'].forEach(type => {
        document.addEventListener(type, (e) => {
            if (e.isTrusted && window.QuickStart.state().running) window.__leak.push(type);
        }, true);
    });
}"""


CALLOUT_BOX_JS = """() => {
    const c = document.getElementById('qs-callout');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return [r.left, r.top, r.right, r.bottom];
}"""


def _settle_with_noise(page, index, rng, timeout=120):
    """Until step `index` settles, a hand on the mouse: it wanders, clicks,
    right-clicks, scrolls and presses keys whenever the step is running."""
    deadline = time.time() + timeout
    st = None
    while time.time() < deadline:
        st = page.evaluate(STATE_JS)
        q = st['qs']
        if q['index'] == index and not q['running'] and st['state'] in ('done', 'failed', 'idle'):
            return st
        if q['running']:
            x, y = rng.uniform(40, VIEWPORT['width'] - 40), rng.uniform(60, VIEWPORT['height'] - 30)
            # A click on the callout's Skip ends the guide by design (the
            # person meant it), so the stray hand keeps off the callout.
            box = page.evaluate(CALLOUT_BOX_JS)
            if box and any(box[0] - 8 <= px <= box[2] + 8 and box[1] - 8 <= py <= box[3] + 8
                           for px, py in ((x, y), (x + 60, y + 30))):
                continue
            page.mouse.move(x, y, steps=4)
            r = rng.random()
            if r < 0.2:
                page.mouse.click(x, y)
            elif r < 0.27:
                page.mouse.click(x, y, button='right')
            elif r < 0.34:
                page.mouse.wheel(0, rng.choice([-240, 240]))
            elif r < 0.40:
                page.keyboard.press(rng.choice(['Delete', 'a', 'Tab']))
            elif r < 0.48:
                page.mouse.down()
                page.mouse.move(x + 60, y + 30, steps=4)
                page.mouse.up()
        time.sleep(0.03)
    return st


def test_a_check_is_polled_until_it_answers(page):
    """A check that answers 1.5 s after the act ended still takes: the
    engine asks again until it answers. A check that never answers fails,
    and only after the engine's limit."""
    i = _index(page, 'projectName')
    page.evaluate("""() => {
        const s = window.QuickStart.steps().projectName;
        window.__origCheck = s.check;
        window.__polls = 0;
        let first = null;
        s.check = function (mem) {
            window.__polls++;
            if (first == null) first = Date.now();
            return Date.now() - first < 1500 ? null : window.__origCheck.call(this, mem);
        };
    }""")
    try:
        _open_advanced(page, 3)
        page.locator('#qs-next').click()
        st = _wait_step(page, i)
        assert st['state'] == 'done' and not st['fail'], st
        assert page.evaluate("window.__polls") > 5
        _end(page)

        page.evaluate("""() => {
            const s = window.QuickStart.steps().projectName;
            window.__polls = 0;
            s.check = function () { window.__polls++; return null; };
        }""")
        _open_advanced(page, 3)
        page.locator('#qs-next').click()
        t0 = time.time()
        st = _wait_step(page, i, timeout=60)
        took = time.time() - t0
        assert st['state'] == 'failed' and st['fail'], st
        assert took >= 9, f'the step failed after {took:.1f}s, before the check limit'
        assert page.evaluate("window.__polls") > 20
    finally:
        page.evaluate("() => { window.QuickStart.steps().projectName.check = window.__origCheck; }")


def test_real_input_never_reaches_the_app_while_a_step_runs(page):
    """Drag the processor onto the wall, at a person's pace, with a hand
    on the mouse the whole time and a double click on Next: the app sees
    none of it, Next stays disabled and does nothing, and the drag takes.
    Between steps a key outside the callout never reaches the app."""
    rng = random.Random(7)
    page.evaluate(LEAK_JS)
    i = _index(page, 'dropProcessor')
    _open_advanced(page, 1)
    _go_to(page, i - 1)
    st = _wait_step(page, i - 1)
    assert st['state'] == 'done', st
    page.evaluate("window.__leak = []")
    # Next, and the second click of the double click lands while the
    # next step runs.
    page.locator('#qs-next').dblclick()
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i, timeout=10000)
    assert page.evaluate("document.getElementById('qs-next').disabled"), 'Next is live while the step runs'
    st = _settle_with_noise(page, i, rng)
    assert st['qs']['index'] == i, st
    assert st['state'] == 'done' and not st['fail'], st
    assert page.evaluate("window.__leak") == [], 'real input reached the app during the act'
    assert not page.evaluate("document.getElementById('qs-next').disabled")
    # Settled: Delete with the demo wall selected goes nowhere.
    layers = page.evaluate("() => window.app.project.layers.length")
    page.mouse.click(700, 500)
    page.keyboard.press('Delete')
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.app.project.layers.length") == layers
    assert page.evaluate("window.QuickStart.state().index") == i


def test_replay_starts_the_step_from_a_known_state(page):
    """A redraw left armed (and ports left picked) by a failed try is put
    down when the step is played again: the replay button's run takes."""
    i = _index(page, 'redrawAsOne')
    _open_advanced(page, 3)
    _go_to(page, i)
    st = _wait_step(page, i)
    assert st['state'] == 'done', st
    page.evaluate("""() => {
        const a = window.app, l = a.project.layers[a.project.layers.length - 1];
        a._portPicks = {layerId: l.id, nums: [1, 2]};
        a._mergeRedraw = {layerId: l.id, picks: [1, 2], ready: true, baseEntry: null};
    }""")
    page.locator('#qs-replay').click()
    page.wait_for_function("() => window.QuickStart.state().running", timeout=10000)
    st = _wait_step(page, i)
    assert st['state'] == 'done' and not st['fail'], st


def test_the_guide_runs_on_the_shipped_preferences(page, matt_prefs):
    """Matt's Preferences (Brompton, 10-bit, 30 Hz) and a 230/400 distro
    system never reach the guide's objects: inside the guide the app reads
    the shipped Preferences, and at the end the person's own are back, on
    the server and in the app."""
    _open_advanced(page, 3)
    inside = page.evaluate("""() => { const p = window.app.getPreferences();
        return {bitDepth: p.bitDepth, frameRate: p.frameRate, processorType: p.processorType,
                distroSystem: p.distroSystem}; }""")
    assert inside == {'bitDepth': 8, 'frameRate': 60, 'processorType': 'novastar-armor',
                      'distroSystem': '120/208'}, inside
    _end(page)
    page.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                           timeout=30000)
    server = page.evaluate(PREFS_JS, None)
    for k, v in MATT_PREFS.items():
        assert server.get(k) == v, (k, server.get(k))
        assert page.evaluate("(k) => window.app.getPreferences()[k]", k) == v, k


def test_the_scratch_show_has_one_canvas(page):
    """A show with three canvases: the guide's scratch show has one canvas
    of its own, and the three come back at the end."""
    page.evaluate("""async () => {
        for (const n of ['SR', 'DJ']) {
            await fetch('/api/canvas', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({name: n})});
        }
        window.app.project = await (await fetch('/api/project')).json();
    }""")
    before = page.evaluate("() => window.app.project.canvases.map(c => c.id)")
    assert len(before) >= 3, before
    _open_advanced(page, 3)
    inside = page.evaluate("""async () => ({
        local: window.app.project.canvases.length,
        server: (await (await fetch('/api/project')).json()).canvases.length})""")
    assert inside == {'local': 1, 'server': 1}, inside
    _end(page)
    page.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                           timeout=30000)
    assert page.evaluate("() => window.app.project.canvases.map(c => c.id)") == before


# The Advanced steps that failed in the 1.6.0 QA pass under a hand on the
# mouse, a second click on Next, or Matt's Preferences, in guide order, as
# runs of consecutive steps (each run entered by Go to).
NOISY_RUNS = [
    ['cardNames', 'dropProcessor', 'releasePort', 'attachmentFlag', 'pinPort'],
    ['addService', 'serviceRating', 'serviceDistro'],
    ['mirrorScreen', 'portPlug', 'portNumbers', 'portsMinimum', 'powerZPattern',
     'circuitNumbers', 'redrawAsOne', 'sweepPorts'],
]


def test_advanced_steps_take_under_matt_prefs_with_a_hand_on_the_mouse(page, matt_prefs):
    """Under Matt's Preferences, with a wandering, clicking hand on the
    mouse during every act and a double click on every Next, each step of
    the runs that failed in the QA pass takes the first time."""
    rng = random.Random(11)
    page.evaluate(LEAK_JS)
    problems = []
    for run in NOISY_RUNS:
        first = _index(page, run[0])
        _open_advanced(page, 2)
        _go_to(page, first)
        st = _settle_with_noise(page, first, rng)
        for k, key in enumerate(run):
            i = first + k
            if k:
                page.locator('#qs-next').dblclick()
                page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i, timeout=10000)
                st = _settle_with_noise(page, i, rng)
            if st['qs']['index'] != i or st['state'] != 'done' or st['fail']:
                problems.append(f"{key}: {st['state']} {st['note']!r}")
        leak = page.evaluate("window.__leak")
        if leak:
            problems.append(f"{run[0]}..{run[-1]}: real input reached the app: {sorted(set(leak))}")
        page.evaluate("window.__leak = []")
        _end(page)
        page.wait_for_function(
            "() => !window.QuickStart.state().visible && !window.QuickStart.state().running", timeout=30000)
    assert not problems, "\n".join(problems)
