"""Layout that follows the panels, not a guess at when their fold ends.

A side panel folds in 0.18 s and the hardware tray the same. Code that waited
a fixed time and then measured was right on a fast machine and wrong on a
slow one: on a Windows box drawing in software the page went 550 ms without a
frame, the fold was still running when the timer fired, and what was measured
was a mid-fold size. Here every fold is slowed to 0.9 s, so each fixed timer
lands mid-fold on any machine, and what must still come out right is checked
after the fold has ended.

The resize strips also had a 1.2 s sweep that put them right eventually; it is
switched off here (setInterval of exactly 1200 ms is dropped), because a strip
in the wrong place for a second is the bug - the sweep only hid it.
"""

import pytest

from conftest import settled  # noqa: E402

SLOW_CSS = """
#left-sidebar, #right-sidebar { transition: width 0.9s linear, padding 0.9s linear !important; }
#hardware-dock { transition: height 0.9s linear !important; }
"""

INIT_JS = """(() => {
    try { localStorage.setItem('lrd_quickstart_disabled', '1'); } catch (e) {}
    const realSetInterval = window.setInterval;
    window.setInterval = function (fn, ms, ...rest) {
        if (ms === 1200) return 0;   // the resize strips' safety sweep
        return realSetInterval.call(this, fn, ms, ...rest);
    };
    document.addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = %r;
        document.head.appendChild(s);
    });
})();""" % SLOW_CSS

STRIPS_JS = """() => {
    const out = {};
    for (const [key, id] of [['left', 'left-sidebar'], ['right', 'right-sidebar'], ['dock', 'hardware-dock']]) {
        const panel = document.getElementById(id);
        const h = document.querySelector(`.lrd-resize-handle[data-lrd-resize="${key}"]`);
        if (!panel || !h) { out[key] = null; continue; }
        const p = panel.getBoundingClientRect(), r = h.getBoundingClientRect();
        out[key] = {shown: getComputedStyle(h).display !== 'none' && r.width > 0 && r.height > 0,
                    collapsed: panel.classList.contains('collapsed'),
                    panel: {left: Math.round(p.left), right: Math.round(p.right), top: Math.round(p.top),
                            width: Math.round(p.width), height: Math.round(p.height)},
                    strip: {left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width),
                            height: Math.round(r.height)}};
    }
    return out;
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _open(e2e_server, pw_browser, storage=None):
    ctx = pw_browser.new_context(viewport={'width': 1700, 'height': 900})
    if storage:
        ctx.add_init_script("(() => { const s = %r; for (const k in s) localStorage.setItem(k, s[k]); })();" % storage)
    ctx.add_init_script(INIT_JS)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(1200)
    return ctx, page, errors


FOLDING_JS = """() => document.getAnimations().filter(a => a.playState === 'running' && a.effect
    && a.effect.target && ['left-sidebar', 'right-sidebar', 'hardware-dock'].includes(a.effect.target.id)).length"""


def _after_the_fold(page):
    """Wait until no panel is folding - the fold's real end, however slowly
    this machine paints - and one frame more for anything placed on it."""
    left = settled(page, lambda: page.evaluate(FOLDING_JS), lambda n: n == 0, timeout_ms=10000)
    assert left == 0, f'{left} panel folds still running after 10 s'
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


def _strip_fits(s, key):
    """Where the strip must be for its panel: on the dragged edge."""
    p, r = s['panel'], s['strip']
    if key == 'dock':
        return abs(r['top'] - (p['top'] - 3)) <= 1 and abs(r['left'] - p['left']) <= 1 and abs(r['width'] - p['width']) <= 1
    edge = p['right'] - 3 if key == 'left' else p['left'] - 4
    return abs(r['left'] - edge) <= 1 and abs(r['top'] - p['top']) <= 1 and abs(r['height'] - p['height']) <= 1


@pytest.mark.parametrize('key,toggle', [('left', '#left-sidebar-toggle'),
                                        ('right', '#right-sidebar-toggle'),
                                        ('dock', '#hardware-dock-toggle')])
def test_a_strip_follows_its_panel_through_a_slow_fold(e2e_server, pw_browser, key, toggle):
    ctx, page, errors = _open(e2e_server, pw_browser)
    try:
        if not page.locator(toggle).count():
            pytest.skip(f'{toggle} is not on the page')
        for _ in range(2):   # fold, then open again
            page.locator(toggle).click()
            page.wait_for_timeout(300)    # the old 220 ms timer has fired, mid-fold
            _after_the_fold(page)
            s = page.evaluate(STRIPS_JS)
            for k, v in s.items():
                if v is None:
                    continue
                if v['collapsed']:
                    assert not v['shown'], f'after the {key} toggle a folded {k} panel still offers a strip: {v}'
                else:
                    assert v['shown'] and _strip_fits(v, k), (
                        f'after the {key} toggle the {k} strip is not on its panel: {v}')
        assert errors == [], errors
    finally:
        ctx.close()


def test_the_first_fit_is_made_after_a_saved_fold_has_ended(e2e_server, pw_browser):
    """A panel saved folded folds again as the app starts. The wall is fitted
    to the canvas once; if that fit came while the fold was running it used
    a mid-fold canvas and stayed wrong until the user pressed Fit."""
    ctx, page, errors = _open(e2e_server, pw_browser, storage={
        'ledRasterSidebarCollapsed_left': '1', 'ledRasterSidebarCollapsed_right': '1'})
    try:
        page.locator('[data-mode="pixel-map"]').click()
        _after_the_fold(page)
        page.wait_for_timeout(500)
        first = page.evaluate("""() => ({zoom: window.canvasRenderer.zoom,
            panX: window.canvasRenderer.panX, panY: window.canvasRenderer.panY,
            w: document.getElementById('main-canvas').width})""")
        refit = page.evaluate("""() => { window.canvasRenderer.setupCanvas(); window.canvasRenderer.fitToView();
            return {zoom: window.canvasRenderer.zoom, panX: window.canvasRenderer.panX,
                    panY: window.canvasRenderer.panY, w: document.getElementById('main-canvas').width}; }""")
        assert abs(first['zoom'] - refit['zoom']) < 1e-6 and abs(first['panX'] - refit['panX']) < 1 \
            and abs(first['panY'] - refit['panY']) < 1, (
            f'the first fit does not match a fit made now: {first} vs {refit}')
        assert errors == [], errors
    finally:
        ctx.close()
