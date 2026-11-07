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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
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


def test_pick_the_strands_survives_the_tray_rebuilding_after_the_click(page):
    """The strand pick is the chip swapped for a select in place, so a tray
    rebuild just after the click (a late echo of the Go to's restore) puts
    the chip back and the pick is gone. With the tray rebuilt after the
    first click on each strand chip, "Pick the strands" still takes."""
    page.evaluate("""() => {
        window.__injected = {};
        if (window.__strandRebuild) return;
        window.__strandRebuild = (e) => {
            const f = e.target && e.target.dataset && e.target.dataset.lrdField;
            if (!f || !/^fiber-strand-[^p]/.test(f) || window.__injected[f]) return;
            window.__injected[f] = 1;
            setTimeout(() => window.app.renderHardwareDock(), 0);
        };
        document.addEventListener('click', window.__strandRebuild, true);
    }""")
    try:
        i = _index(page, 'fiberStrands')
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i)
        assert st['state'] == 'done' and not st['fail'], st
        assert len(page.evaluate("Object.keys(window.__injected)")) == 2
    finally:
        page.evaluate("() => { document.removeEventListener('click', window.__strandRebuild, true); "
                      "window.__strandRebuild = null; }")


def test_pick_the_strands_survives_the_tray_rebuilding_on_the_way_to_the_pick(page):
    """The other half of the rebuild above: the first strand's own echo can
    restate the tray while the hand is on its way to the second strand's
    pick, after the pick was found. The hand's reach then found nothing and
    the step stopped, and in What's New's apply every step after it was
    left with no show (CI, 2026-11-04). The tray is rebuilt at the moment
    the hand reaches for each pick, once per strand."""
    page.evaluate("""() => {
        window.__injected = {};
        window.__realTimeout = window.__realTimeout || window.setTimeout;
        window.setTimeout = (fn, ms, ...rest) => {
            const pick = ms === 0 && document.querySelector('[data-lrd-field^="fiber-strand-pick-"]');
            const f = pick && pick.dataset.lrdField;
            if (f && !window.__injected[f]) {
                window.__injected[f] = 1;
                window.app.renderHardwareDock();
            }
            return window.__realTimeout(fn, ms, ...rest);
        };
    }""")
    try:
        i = _index(page, 'fiberStrands')
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i)
        assert st['state'] == 'done' and not st['fail'], st
        assert len(page.evaluate("Object.keys(window.__injected)")) == 2
    finally:
        page.evaluate("() => { window.setTimeout = window.__realTimeout; }")


def test_pick_the_strands_takes_with_the_tray_redrawing_on_a_steady_beat(page):
    """A tray that redraws faster than the hand reaches a pick (1.6.0 QA,
    the tray on a 350 ms timer: 0 of 3 replays took, "the strand pick did
    not open"). The rebuild took the pick every time it beat the hand, and
    each of the three tries lost the same way. At the shipped pace, on a
    steady beat, the step takes."""
    i = _index(page, 'fiberStrands')
    _open_advanced(page, 1)
    page.evaluate("() => { window.__beat = setInterval(() => window.app.renderHardwareDock(), 350); }")
    try:
        _go_to(page, i)
        st = _wait_step(page, i, timeout=120)
        assert st['state'] == 'done' and not st['fail'], st
    finally:
        page.evaluate("() => clearInterval(window.__beat)")


def test_pick_the_strands_takes_when_every_press_is_rebuilt_under_it(page):
    """The click's press lasts 70 ms, long enough for the tray to rebuild
    under it. The click then went to the copy the rebuild took out, which
    swapped nothing for nothing, and no try ever opened the pick."""
    page.evaluate("""() => {
        window.__presses = 0;
        window.__onPress = (e) => {
            const f = e.target && e.target.dataset && e.target.dataset.lrdField;
            if (!f || !/^fiber-strand-[^p]/.test(f)) return;
            window.__presses++;
            setTimeout(() => window.app.renderHardwareDock(), 0);
        };
        document.addEventListener('mousedown', window.__onPress, true);
    }""")
    try:
        i = _index(page, 'fiberStrands')
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i)
        assert st['state'] == 'done' and not st['fail'], st
        assert page.evaluate("window.__presses") == 2
    finally:
        page.evaluate("() => document.removeEventListener('mousedown', window.__onPress, true)")


# Every frame between the press on a box's grip and the release, the ring,
# the box the step names and the tray's body, and where the press landed.
DRAG_WATCH_JS = """() => {
    window.__drag = {on: false, rows: [], press: null};
    const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {left: r.left, top: r.top, right: r.right, bottom: r.bottom};
    };
    window.__dragDown = (e) => {
        if (!e.target || !e.target.closest || !e.target.closest('.hw-dock-grip')) return;
        window.__drag.on = true;
        window.__drag.press = {x: e.clientX, y: e.clientY};
    };
    window.__dragUp = () => { window.__drag.on = false; };
    document.addEventListener('mousedown', window.__dragDown, true);
    document.addEventListener('mouseup', window.__dragUp, true);
    const tick = () => {
        if (window.__drag.on) {
            const q = window.QuickStart.state();
            const step = window.QuickStart.tours()[q.tour][q.index];
            const sel = step.target();
            window.__drag.rows.push({sel, ring: box(document.getElementById('qs-spot')),
                                     box: box(document.querySelector(sel)),
                                     tray: box(document.getElementById('hardware-dock-body'))});
        }
        window.__dragFrame = requestAnimationFrame(tick);
    };
    tick();
}"""
DRAG_UNWATCH_JS = """() => {
    cancelAnimationFrame(window.__dragFrame);
    document.removeEventListener('mousedown', window.__dragDown, true);
    document.removeEventListener('mouseup', window.__dragUp, true);
}"""
RING_PAD = 6


def _ring_is_on(ring, box, slack=2):
    return all(abs(ring[k] - (box[k] + (RING_PAD if k in ('right', 'bottom') else -RING_PAD))) <= slack
               for k in ('left', 'top', 'right', 'bottom'))


def test_the_ring_stays_on_the_box_through_the_mirror_drag(page):
    """Mirror a screen names its box only once the act has put the hardware
    in, so the ring measured before the act sat on another box for the whole
    drag, and the box was past the tray's bottom edge (1.6.0 QA, every run
    at 1600x950). From the press to the release the ring is on the box the
    callout says to drag, the box is in the tray's view, and the press
    landed on it. A rebuild does not move the stack: the box was revealed
    in a frame that drew the column short of its snake's bracket."""
    i = _index(page, 'mirrorScreen')
    _open_advanced(page, 3)
    page.evaluate(DRAG_WATCH_JS)
    try:
        _go_to(page, i)
        st = _wait_step(page, i, timeout=120)
        assert st['state'] == 'done' and not st['fail'], st
        drag = page.evaluate("window.__drag")
    finally:
        page.evaluate(DRAG_UNWATCH_JS)
    rows = drag['rows']
    assert len(rows) >= 5, drag
    for row in rows:
        assert 'data-hwdock="box-' in row['sel'], row
        assert _ring_is_on(row['ring'], row['box']), row
        assert row['box']['top'] >= row['tray']['top'] - 1, row
        assert row['box']['bottom'] <= row['tray']['bottom'] + 1, row
    first = rows[0]['box']
    assert first['left'] <= drag['press']['x'] <= first['right'], drag['press']
    assert first['top'] <= drag['press']['y'] <= first['bottom'], (drag['press'], first)
    heights = page.evaluate("""() => {
        const body = document.getElementById('hardware-dock-body');
        const before = [body.scrollHeight, body.scrollTop];
        window.app.renderHardwareDock();
        return [before, [body.scrollHeight, body.scrollTop]];
    }""")
    assert heights[0] == heights[1], heights


def test_mirror_a_screen_says_so_when_its_setup_does_not_take(page):
    """The act puts IMAG L on the box before the drag. When that request
    gets no answer the app logs it and carries on, and the drag was then
    refused as if the gesture were wrong. The step stops and names what
    went wrong instead."""
    page.route('**/api/port-assignments/place-overflow', lambda r: r.abort('addressunreachable'))
    try:
        i = _index(page, 'mirrorScreen')
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i, timeout=60)
        assert st['state'] == 'failed', st
        assert 'IMAG L did not go on the box' in st['note'], st
    finally:
        page.unroute('**/api/port-assignments/place-overflow')


# A step of the test's own: its act runs `act`, its check is a yes.
STAND_IN_JS = """(body) => {
    const step = window.QuickStart.steps().cableSheet;
    window.__standIn = {act: step.act, check: step.check, after: step.after};
    step.act = new Function('t', body);
    step.check = () => 'stood in';
    step.after = () => {};
}"""
STAND_DOWN_JS = """() => {
    const step = window.QuickStart.steps().cableSheet;
    Object.assign(step, window.__standIn);
    document.getElementById('hardware-dock-body').style.paddingTop = '';
}"""


def test_the_ring_follows_a_target_the_act_moves_and_holds_when_it_scrolls_away(page):
    """The ring through an act, on any step: a target the act moves is
    followed without anything being scrolled for it, and one the tray has
    scrolled out of sight leaves the ring where it is, on the tray rather
    than on whatever lies past its edge."""
    i = _index(page, 'cableSheet')
    page.evaluate(STAND_IN_JS, """
        const body = document.getElementById('hardware-dock-body');
        const sel = '#hardware-dock-body .hw-dock-cablebtn-data';
        const box = (el) => { const r = el.getBoundingClientRect();
            return {left: r.left, top: r.top, right: r.right, bottom: r.bottom}; };
        const rest = () => new Promise(r => setTimeout(r, 450));
        window.__ring = {};
        body.scrollTop = 0;
        return rest().then(() => {
            body.style.paddingTop = '40px';
            return rest();
        }).then(() => {
            window.__ring.moved = {ring: box(document.getElementById('qs-spot')),
                                   target: box(document.querySelector(sel)), scroll: body.scrollTop};
            body.style.paddingTop = '';
            body.scrollTop = 400;
            return rest();
        }).then(() => {
            window.__ring.away = {ring: box(document.getElementById('qs-spot')),
                                  target: box(document.querySelector(sel)),
                                  tray: box(body)};
            body.scrollTop = 0;
        });
    """)
    try:
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i, timeout=60)
        assert st['state'] == 'done' and not st['fail'], st
        ring = page.evaluate("window.__ring")
    finally:
        page.evaluate(STAND_DOWN_JS)
    moved = ring['moved']
    assert moved['scroll'] == 0, moved
    assert _ring_is_on(moved['ring'], moved['target']), moved
    away = ring['away']
    assert away['target']['bottom'] <= away['tray']['top'], away
    assert away['ring']['bottom'] > away['tray']['top'], away


def test_the_hand_lands_where_the_element_is_now(page):
    """The tray moves while the hand travels (a save's echo restates it, a
    column grows): the hand ends on the element, not on where it was when
    it set off."""
    i = _index(page, 'cableSheet')
    page.evaluate(STAND_IN_JS, """
        const sel = '#hardware-dock-body .hw-dock-cablebtn-data';
        setTimeout(() => {
            document.getElementById('hardware-dock-body').style.paddingTop = '40px';
        }, 30);
        return t.moveTo(sel).then((p) => {
            const r = document.querySelector(sel).getBoundingClientRect();
            window.__aim = {hand: [p.x, p.y], at: [r.left + r.width / 2, r.top + r.height / 2]};
        });
    """)
    try:
        _open_advanced(page, 3)
        _go_to(page, i)
        st = _wait_step(page, i, timeout=60)
        assert st['state'] == 'done' and not st['fail'], st
        aim = page.evaluate("window.__aim")
    finally:
        page.evaluate(STAND_DOWN_JS)
    assert abs(aim['hand'][0] - aim['at'][0]) < 2 and abs(aim['hand'][1] - aim['at'][1]) < 2, aim


def test_a_menu_opened_right_after_skip_stays_open(page):
    """Skip puts the person's world back a beat later, and that restore
    closed every menu, twice: Help opened at once was shut under the hand,
    and a click on its item waited 30 s on an item that had gone (1.6.0 QA).
    The guide's own menus go at Skip; one opened after it is left up."""
    _open_advanced(page, 1)
    page.locator('#qs-skip').click()
    page.locator('.menu-item[data-menu="help"]').click()
    page.wait_for_function("() => !window.QuickStart.state().running", timeout=30000)
    page.wait_for_timeout(300)
    try:
        assert page.evaluate("document.getElementById('menu-help').style.display") == 'block'
        page.locator('.menu-option[data-action="about"]').wait_for(state='visible', timeout=1000)
    finally:
        page.evaluate("() => window.app._hideMenuBarMenus()")


def test_whats_new_never_carries_on_from_an_entry_it_did_not_reach(page):
    """What's New, with the shipped file stale, applies the Advanced steps
    before each step. When that apply stops on the way, the step still
    plays, but the show is not the next step's entry: the next step starts
    over from a fresh scratch show instead of carrying on from a broken
    one (a played step that took on a broken entry sent "Put the distro on
    the service" to a show with no distro)."""
    keys = page.evaluate("() => window.QuickStart.newSteps('1.5.2', '1.5.3')")
    picked = [keys[0], keys[-1]]
    assert picked[-1] == 'serviceDistro', picked
    page.evaluate("""() => {
        window.__warns = [];
        if (!window.__warnWrapped) {
            window.__warnWrapped = true;
            const w = console.warn;
            console.warn = function (...a) {
                try { window.__warns.push(a.map(x => x && x.message ? x.message : String(x)).join(' ').slice(0, 300)); } catch (e) {}
                return w.apply(this, a);
            };
        }
        const st = window.QuickStart.steps();
        window.__qsTitle = st.cabinetSize.title;
        st.cabinetSize.title += ' (changed)';
        // The apply for the FIRST What's New step stops at Add distro.
        window.__origAddDistro = st.addDistro.check;
        st.addDistro.check = function (mem) {
            if (window.QuickStart.state().index === 0) return null;
            return window.__origAddDistro.call(this, mem);
        };
    }""")
    try:
        page.evaluate("(s) => window.QuickStart.setSpeed(s)", 3)
        page.evaluate("(k) => { window.QuickStart.startSteps(k); }", picked)
        st = _wait_step(page, 0, timeout=240)
        assert st['state'] == 'done', st      # Cable stock needs no distro
        page.locator('#qs-next').click()
        st = _wait_step(page, 1, timeout=300)
        assert st['state'] == 'done' and not st['fail'], (st, page.evaluate("window.__warns"))
    finally:
        _end(page)
        page.evaluate("""() => { const st = window.QuickStart.steps();
            st.cabinetSize.title = window.__qsTitle; st.addDistro.check = window.__origAddDistro; }""")


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


def test_a_guide_started_while_the_last_one_ends_waits_for_it(page):
    """A guide started the moment the last one is left (its restore of the
    person's project still on its way) waits for that restore: it runs on
    its own scratch show, and leaving it puts the person's project back.
    Started at once, the restore landed over the new scratch show and the
    new guide captured the scratch show as the world to put back, so the
    person's project was lost when it ended."""
    page.evaluate("""async () => {
        const p = await (await fetch('/api/project')).json();
        p.name = 'Own Show';
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                     body: JSON.stringify(p)});
        window.app.project = await (await fetch('/api/project')).json();
    }""")
    own = page.evaluate("() => window.app.project.layers.map(l => l.name)")
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", 3)
    page.evaluate("() => { window.QuickStart.startTour('quick'); }")
    _wait_step(page, 0)
    # Left, and the next guide asked for in the same moment.
    page.evaluate("() => { window.QuickStart.end(); window.QuickStart.startTour('quick'); }")
    page.wait_for_function("() => window.QuickStart.state().visible && window.QuickStart.state().index === 0",
                           timeout=30000)
    st = _wait_step(page, 0)
    assert st['state'] in ('done', 'idle'), st
    inside = page.evaluate("""async () => ({
        local: window.app.project.layers.map(l => l.name),
        server: (await (await fetch('/api/project')).json()).layers.map(l => l.name)})""")
    assert inside == {'local': ['DEMO WALL'], 'server': ['DEMO WALL']}, inside
    _end(page)
    page.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                           timeout=30000)
    back = page.evaluate("() => ({name: window.app.project.name, layers: window.app.project.layers.map(l => l.name)})")
    assert back == {'name': 'Own Show', 'layers': own}, back


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
