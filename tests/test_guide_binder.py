"""The Binder and Exports guide (Help > Guides > Binder and Exports): it starts on its own demo
show, every step takes by Next, and Go to lands on every step.

The guide's demo show is the finished show: two walls grouped as one.
tests/guide_suite.py says what each check proves;
tests/test_guide_windows.py holds the guide's shared windows open.

Run locally (each session takes its own free port):
    python -m pytest tests/test_guide_binder.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from guide_suite import (page, _restore_server_project, _guide_closed,  # noqa: E402,F401
                         check_start, drive_whole_guide, go_to_step, step_count)
from test_tour_anchors import _wait_step  # noqa: E402

GUIDE = 'binder'
# The guide's steps, its intro and outro among them. A step added or taken
# away changes this; the parametrized Go to below covers every one.
STEPS = 13
DEMO_SHOW = dict(name='Demo Show', screens=['DEMO WALL', 'DEMO WALL 2'], processors=2, distros=1, services=1, beaches=1, groups=1)


def test_the_guide_has_its_steps(page):
    assert step_count(page, GUIDE) == STEPS, f'the {GUIDE} guide has another step count; update STEPS'


def test_it_starts_on_its_own_demo_show(page):
    check_start(page, GUIDE, DEMO_SHOW, via='snapshot')


def test_every_step_takes_by_next(page):
    drive_whole_guide(page, GUIDE)


@pytest.mark.parametrize('i', range(1, STEPS))
def test_go_to_every_step_lands_on_the_snapshot(page, i):
    go_to_step(page, GUIDE, i)


# The scratch show's own requests, marked by the page as they go: its one
# screen DEMO WALL on no processor (quickstart.js buildScratch).
_MARK_SCRATCH_JS = r"""() => {
    window.__heldJson = 0;
    if (window.__scratchMarked) { window.__scratchMarked.armed = true; return; }
    const of = window.fetch;
    const state = window.__scratchMarked = {armed: true, resolve: false, layer: false};
    const scratch = () => {
        const p = window.app && window.app.project;
        return !!p && (p.layers || []).length === 1 && p.layers[0].name === 'DEMO WALL'
            && !(p.processors || []).length;
    };
    window.fetch = function (url, opts) {
        const u = String(url);
        const m = (opts && opts.method) || 'GET';
        let hold = null;
        if (state.armed && scratch()) {
            if (!state.resolve && /\/api\/port-assignments\/resolve$/.test(u)) { state.resolve = true; hold = 'resolve'; }
            else if (!state.layer && m === 'PUT' && /\/api\/layer\//.test(u)) { state.layer = true; hold = 'layer'; }
        }
        if (!hold) return of.apply(this, arguments);
        if (state.resolve && state.layer) state.armed = false;
        const o = Object.assign({}, opts, {headers: Object.assign({}, (opts && opts.headers) || {}, {'X-Test-Hold': hold})});
        return of.call(this, url, o).then(r => {
            if (hold !== 'resolve') return r;
            // The reply has been read and acted on once the page's own
            // handlers (promise jobs) have run: a task after its body.
            const j = r.json.bind(r);
            r.json = () => j().then(d => { setTimeout(() => { window.__heldJson += 1; }, 0); return d; });
            return r;
        });
    };
}"""


def test_a_late_answer_for_the_scratch_show_keeps_the_demo_shows_ports(page):
    """The race behind the Fiber page step failing at random (a hidden
    Fiber tick, 2026-11-17): the scratch show's first resolve was answered
    after the guide had put its demo show on the page, while the demo
    show's restore still waited behind the scratch screen's own PUT. The
    server had read it after the scratch show's second resolve (two
    requests, two threads), so it was the newest answer and was taken - and
    it wrote the scratch show's port state (no pins) onto the demo show,
    which the restore then carried to the server. DEMO WALL lost its ports
    on SR; a processor with no screen is off the binder, and its Fiber page
    with it.

    Forced here in that order: the scratch show's first resolve is held
    unsent and its screen PUT unanswered; once the demo show is on the page
    the resolve goes (the server still holds the scratch show) and is
    answered, then the PUT. The demo show keeps its six pins, on the page
    and on the server, and the binder offers the Fiber page."""
    held = {}

    def hold(route):
        kind = route.request.headers.get('x-test-hold')
        if not kind:
            route.continue_()
            return
        # the screen PUT reaches the server now and is answered later; the
        # resolve reaches it only when let go
        held[kind] = (route, route.fetch() if kind == 'layer' else None)

    page.route('**/api/port-assignments/resolve', hold)
    page.route('**/api/layer/*', hold)
    try:
        page.evaluate(_MARK_SCRATCH_JS)
        page.evaluate("(s) => window.QuickStart.setSpeed(s)", 3)
        page.evaluate("() => { window.QuickStart.startTour('binder'); }")
        # the demo show on the page, its restore held behind the screen PUT
        page.wait_for_function(
            "() => { const a = window.app; return a.project && a.project.name === 'Demo Show'"
            " && (a._restorePutPending || 0) > 0; }", timeout=60000)
        assert set(held) == {'resolve', 'layer'}, held.keys()
        route, _ = held.pop('resolve')
        route.fulfill(response=route.fetch())
        page.wait_for_function("() => window.__heldJson > 0", timeout=30000)
        route, resp = held.pop('layer')
        route.fulfill(response=resp)
        st = _wait_step(page, 0)
        assert st and st['qs']['index'] == 0, st
        page.wait_for_function("() => !window.app._restorePutPending", timeout=30000)
        got = page.evaluate("""async () => {
            const a = window.app;
            const pins = p => ((p.port_assignments || {}).pins || []).filter(x => x.cardId === 'card1f').length;
            const server = await fetch('/api/project').then(r => r.json());
            a.openExportModal('binder');
            const tick = document.getElementById('export-binder-fiber-label').getBoundingClientRect();
            document.getElementById('export-modal').style.display = 'none';
            return {page: pins(a.project), server: pins(server), fiber: a.binderUsesFiber(),
                    tick: tick.width > 0 && tick.height > 0};
        }""")
        assert got == {'page': 6, 'server': 6, 'fiber': True, 'tick': True}, got
    finally:
        for route, resp in held.values():
            route.fulfill(response=resp or route.fetch())
        page.unroute('**/api/port-assignments/resolve', hold)
        page.unroute('**/api/layer/*', hold)
        page.evaluate("() => { if (window.__scratchMarked) window.__scratchMarked.armed = false; }")
