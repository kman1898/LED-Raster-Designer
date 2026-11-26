"""A guide's Next takes every click it looks ready for, and never one more.

src/static/js/quickstart.js, pinned here:

  - a step is SETTLED (data-qs-state done/failed/idle, state().running
    false, Next live) only once the callout has finished its slide to its
    spot: a press aimed at Next mid-slide landed where Next no longer was
    and the input shield swallowed it (a snapshot build waited 120 s on
    a Next that never came);
  - a press on a callout button is TAKEN even when the box slid away
    under the held press, and a press the shield does swallow on a
    settled step leaves one log line (guide_press_swallowed) saying where
    it landed and where the box was;
  - while Go to waits for the shipped snapshot file, Next looks disabled,
    and a click or a double click there neither skips a step nor is lost
    behind a Next that looked live.

Run locally (each session takes its own free port):
    python -m pytest tests/test_guide_next_live.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_tour_anchors import _end, _wait_step   # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The guides mutate the shared server project and its preferences;
    leave both as this module found them."""


VIEWPORT = {'width': 1600, 'height': 950}

# Every client log line the page sends, kept in the page (the log goes out
# by sendBeacon).
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)
FIRST_RUN_DONE = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
READY = "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)"


def _new_page(pw_browser, e2e_server):
    context = pw_browser.new_context(viewport=VIEWPORT)
    context.add_init_script(FIRST_RUN_DONE + CLIENT_LOG)
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(READY, timeout=30000)
    pg.wait_for_timeout(1500)
    return context, pg


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context, pg = _new_page(pw_browser, e2e_server)
    yield pg
    context.close()


def _close_guide(pg):
    if pg.evaluate("window.QuickStart.state().visible"):
        _end(pg)
        pg.wait_for_function(
            "() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
            timeout=30000)


@pytest.fixture(autouse=True)
def _guide_closed(page):
    yield
    _close_guide(page)


def _index(page, key):
    at = page.evaluate("(k) => window.QuickStart.guideOf(k)", key)
    assert at and at['index'] >= 0, key
    return at['tour'], at['index']


def _open_guide(page, guide, speed):
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", speed)
    page.evaluate("(n) => { window.QuickStart.startTour(n); }", guide)
    return _wait_step(page, 0, timeout=120)


def _to_project_name(page):
    """The step that names the show, played and settled; its index."""
    guide, i = _index(page, 'projectName')
    _open_guide(page, guide, 3)
    for _ in range(i):
        page.locator('#qs-next').click()
    st = _wait_step(page, i)
    assert st['qs']['index'] == i and st['state'] == 'done', st
    return i


# The callout sent to the other side of the window, by a write to its
# style that the engine did not make.
SHOVE_JS = """() => {
    const c = document.getElementById('qs-callout');
    const left = c.getBoundingClientRect().left;
    c.style.left = (left > 700 ? 80 : 1180) + 'px';
}"""

CENTER_JS = """(sel) => {
    const r = document.querySelector(sel).getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
}"""


def test_a_step_settles_only_once_the_box_is_still(page):
    """The box slides (slowed to 1.2 s here) as the step's verdict comes in.
    The step reports settled, and Next goes live, only once the box is at
    its spot: never mid-slide."""
    _, i = _index(page, 'projectName')
    page.evaluate("""() => {
        const st = document.createElement('style');
        st.id = 'qs-test-slow-slide';
        st.textContent = '#qs-callout{transition:left 1.2s linear,top 1.2s linear !important;}';
        document.head.appendChild(st);
        const s = window.QuickStart.steps().projectName;
        window.__origCheck = s.check;
        window.__moved = false;
        window.__sawSlide = false;
        window.__liveMidSlide = false;
        s.check = function (mem) {
            const note = window.__origCheck.call(this, mem);
            if (note && !window.__moved) {
                window.__moved = true;
                const c = document.getElementById('qs-callout');
                const top = c.getBoundingClientRect().top;
                c.style.top = (top > 400 ? top - 300 : top + 300) + 'px';
            }
            return note;
        };
    }""")
    try:
        guide, _ = _index(page, 'projectName')
        _open_guide(page, guide, 3)
        for _ in range(i):
            page.locator('#qs-next').click()
        seen = page.wait_for_function("""(i) => {
            const c = document.getElementById('qs-callout');
            const st = window.QuickStart.state();
            const next = document.getElementById('qs-next');
            const sliding = c.getAnimations().some(a => a.playState === 'running');
            if (st.index === i && window.__moved && sliding) {
                window.__sawSlide = true;
                if (next && !next.disabled) window.__liveMidSlide = true;
            }
            const settled = st.index === i && !st.running
                && ['done', 'failed', 'idle'].includes(c.getAttribute('data-qs-state'));
            if (!settled) return false;
            const r = c.getBoundingClientRect();
            return {sliding, dx: Math.abs(r.left - parseFloat(c.style.left)),
                    dy: Math.abs(r.top - parseFloat(c.style.top)), nextDisabled: !!(next && next.disabled),
                    phase: st.phase, state: c.getAttribute('data-qs-state'),
                    saw: window.__sawSlide, liveMidSlide: window.__liveMidSlide};
        }""", arg=i, polling='raf', timeout=90000).json_value()
        assert seen['saw'], f'the box never slid after the verdict, nothing was proved: {seen}'
        assert seen['state'] == 'done', seen
        assert not seen['sliding'] and seen['dx'] < 1 and seen['dy'] < 1, \
            f'the step reported settled while its box was still sliding: {seen}'
        assert not seen['nextDisabled'] and seen['phase'] == 'settled', seen
        assert not seen['liveMidSlide'], f'Next was live while the box slid: {seen}'
    finally:
        page.evaluate("""() => {
            window.QuickStart.steps().projectName.check = window.__origCheck;
            const st = document.getElementById('qs-test-slow-slide');
            if (st) st.remove();
        }""")


def test_a_press_on_next_is_taken_when_the_box_slides_away_under_it(page):
    """Next pressed, the box slides away under the held press, the release
    lands on the overlay: the press is still Next's, and the guide goes on
    (one step: never two)."""
    i = _to_project_name(page)
    nx, ny = page.evaluate(CENTER_JS, '#qs-next')
    page.mouse.move(nx, ny)
    page.mouse.down()
    page.evaluate(SHOVE_JS)
    page.wait_for_timeout(700)
    away = page.evaluate("""([x, y]) => {
        const el = document.elementFromPoint(x, y);
        return !document.getElementById('qs-callout').contains(el);
    }""", [nx, ny])
    assert away, 'the box did not move off the press; nothing was proved'
    page.mouse.up()
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i + 1, timeout=10000)
    st = _wait_step(page, i + 1)
    page.wait_for_timeout(600)
    assert page.evaluate("window.QuickStart.state().index") == i + 1, st


def test_a_swallowed_press_on_a_settled_step_is_in_the_log(page):
    """A press outside the box on a settled step goes nowhere, and says so
    in the log: one line per gesture, where it landed and where the box and
    Next were. A press on Next itself is never in it."""
    i = _to_project_name(page)
    box = page.evaluate("""() => {
        const r = document.getElementById('qs-callout').getBoundingClientRect();
        return [r.left, r.top, r.right, r.bottom];
    }""")
    # A point well clear of the box, on the other half of the window.
    x, y = (300 if (box[0] + box[2]) / 2 > 800 else 1300), 500
    assert not (box[0] - 10 <= x <= box[2] + 10 and box[1] - 10 <= y <= box[3] + 10), box
    page.evaluate("() => { window.__clog.length = 0; }")
    page.mouse.click(x, y)
    page.wait_for_function(
        "() => window.__clog.some(l => l.action === 'guide_press_swallowed')", timeout=10000)
    page.wait_for_timeout(900)
    lines = page.evaluate(
        "() => window.__clog.filter(l => l.action === 'guide_press_swallowed').map(l => l.details)")
    assert len(lines) == 1, lines
    d = lines[0]
    assert d['x'] == x and d['y'] == y, d
    assert d['step'] == 'projectName' and d['n'] == i + 1 and d['guide'], d
    assert 'qs-catch' in d['on'], d
    assert isinstance(d['box'], list) and len(d['box']) == 4, d
    assert isinstance(d['next'], list) and len(d['next']) == 4, d
    assert d['_area'] == 'guide' and d['_lvl'] == 'warn', d
    assert d['folded'] == 0, d
    # Two more presses in quick succession: one line, the second folded
    # into the line after it.
    page.evaluate("() => { window.__clog.length = 0; }")
    page.mouse.click(x, y)
    page.mouse.click(x + 40, y + 20)
    page.wait_for_timeout(900)
    page.mouse.click(x, y)
    page.wait_for_timeout(900)
    lines = page.evaluate(
        "() => window.__clog.filter(l => l.action === 'guide_press_swallowed').map(l => l.details)")
    assert len(lines) == 2 and lines[1]['folded'] == 1, lines
    assert page.evaluate("window.QuickStart.state().index") == i
    # Next itself: taken, and not a swallowed press.
    page.evaluate("() => { window.__clog.length = 0; }")
    page.locator('#qs-next').click()
    page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i + 1, timeout=10000)
    _wait_step(page, i + 1)
    assert page.evaluate(
        "() => window.__clog.filter(l => l.action === 'guide_press_swallowed').length") == 0


def test_next_looks_disabled_while_go_to_waits_and_never_skips(pw_browser, e2e_server):
    """Go to waits for the shipped snapshot file (held here): Next, Back and
    the replay button look disabled the whole time, a click and a double
    click on Next there change nothing, and the jump lands on the step it
    was asked for and stays there."""
    context, pg = _new_page(pw_browser, e2e_server)
    held = []
    hold = {'on': False}

    def route(r):
        if hold['on']:
            held.append(r)
        else:
            r.continue_()

    context.route('**/static/data/tour_snapshots.json', route)
    try:
        pg.evaluate("(s) => window.QuickStart.setSpeed(s)", 3)
        pg.evaluate("() => { window.QuickStart.startTour('quick'); }")
        st = _wait_step(pg, 0, timeout=120)
        assert st['qs']['index'] == 0, st
        pg.wait_for_function(
            "() => !window.QuickStart.state().running && !document.getElementById('qs-next').disabled",
            timeout=10000)
        hold['on'] = True
        pg.evaluate("() => { window.QuickStart.jumpTo(3); }")
        for _ in range(100):
            if held:
                break
            pg.wait_for_timeout(50)
        assert held, 'Go to never asked for the snapshot file; nothing was proved'
        look = pg.evaluate("""() => {
            const c = document.getElementById('qs-callout');
            const next = document.getElementById('qs-next');
            return {state: c.getAttribute('data-qs-state'), disabled: next.disabled,
                    opacity: getComputedStyle(next).opacity, running: window.QuickStart.state().running};
        }""")
        assert look['running'], look
        assert look['state'] == 'running' and look['disabled'], f'Next looked live while Go to waited: {look}'
        assert float(look['opacity']) < 0.6, look
        nx, ny = pg.evaluate(CENTER_JS, '#qs-next')
        pg.mouse.click(nx, ny)
        pg.mouse.dblclick(nx, ny)
        pg.wait_for_timeout(300)
        assert pg.evaluate("window.QuickStart.state().index") == 0
        hold['on'] = False
        for r in held:
            r.continue_()
        st = _wait_step(pg, 2, timeout=120)
        assert st['qs']['index'] == 2, st
        pg.wait_for_timeout(1500)
        st = pg.evaluate("() => window.QuickStart.state()")
        assert st['index'] == 2 and not st['running'], st
        assert not pg.evaluate("document.getElementById('qs-next').disabled")
    finally:
        hold['on'] = False
        for r in held:
            try:
                r.continue_()
            except Exception:
                pass
        try:
            _close_guide(pg)
        finally:
            context.close()
