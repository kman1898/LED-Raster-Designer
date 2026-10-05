"""A guide borrows the default layout and gives the person's back.

The guides' steps point at the panels where they sit by default - Screens
down the right, the tray under the canvas - so a guide started with the
panels moved puts them in their default places for its run. The screen's
saved arrangement is not written over while it does, and the person's own
comes back when the guide ends, or on the next launch if it never did.
"""

import pytest

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """A guide swaps the shared project for its demo show; leave it as found."""


@pytest.fixture
def page(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    yield pg, errors, e2e_server
    try:
        pg.evaluate("() => window.QuickStart && window.QuickStart.end()")
    except Exception:
        pass
    ctx.close()


def _rings(pg):
    return pg.evaluate("() => window.LRD_LAYOUT.rings().map(r => (r.panel || r.bar) + ':' + r.edge)")


def _move_panels(pg):
    pg.evaluate("() => { window.LRD_LAYOUT.move('hardware', 'left', 0); window.LRD_LAYOUT.move('settings', 'bottom'); }")
    pg.wait_for_timeout(500)
    return _rings(pg), pg.evaluate("() => localStorage.getItem('lrd_layout')")


def _start_guide(pg):
    pg.evaluate("() => { window.QuickStart.setSpeed(4); window.QuickStart.start(); }")
    settled(pg, lambda: pg.evaluate("() => !!(window.QuickStart.state().running || window.QuickStart.state().visible)"),
            lambda v: v, timeout_ms=10000)
    # the demo is set up once the default places are in and the callout shows
    settled(pg, lambda: pg.evaluate("() => window.LRD_LAYOUT.isDefault()"), lambda v: v, timeout_ms=10000)


def test_a_guide_runs_on_the_default_layout_and_gives_the_persons_back(page):
    pg, errors, _ = page
    mine, saved = _move_panels(pg)
    assert 'hardware:left' in mine and saved
    _start_guide(pg)
    assert pg.evaluate("() => window.LRD_LAYOUT.isDefault()"), _rings(pg)
    assert pg.evaluate("() => localStorage.getItem('lrd_layout')") == saved, \
        'the guide wrote over the screen\'s saved arrangement'
    pg.evaluate("() => window.QuickStart.end()")
    settled(pg, lambda: pg.evaluate("() => !window.QuickStart.state().visible && !window.QuickStart.state().running"),
            lambda v: v, timeout_ms=20000)
    settled(pg, lambda: _rings(pg), lambda r: r == mine, timeout_ms=5000)
    assert _rings(pg) == mine
    assert pg.evaluate("() => localStorage.getItem('lrd_layout')") == saved
    assert errors == [], errors


def test_a_guide_that_never_ended_gives_it_back_on_the_next_launch(page):
    pg, errors, server = page
    mine, saved = _move_panels(pg)
    _start_guide(pg)
    stash = pg.evaluate("() => JSON.parse(localStorage.getItem('lrd_tour_saved_world') || 'null')")
    assert stash and stash.get('layout'), 'the guide did not keep the person\'s layout in its stash'
    # the window goes away mid-guide; the next launch finds the stash and
    # puts everything back, the layout with it
    pg.reload(wait_until='domcontentloaded')
    settled(pg, lambda: pg.evaluate("() => !!window.LRD_LAYOUT && !localStorage.getItem('lrd_tour_saved_world')"),
            lambda v: v, timeout_ms=20000)
    pg.wait_for_timeout(1500)
    assert _rings(pg) == mine, _rings(pg)
    assert pg.evaluate("() => localStorage.getItem('lrd_layout')") == saved
    assert errors == [], errors
