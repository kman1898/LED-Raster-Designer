"""Cabinet ids on a zoomed-out workspace (owner, 2026-10-17).

An id is skipped only when it would paint under 3 px on the bitmap
(canvas-labels.js CABINET_ID_FLOOR_PX, 5 px until this date), and the
workspace logs each screen's switch between shown and hidden once - not per
frame, and never from an export.
"""

import pytest

PROBE = """(zooms) => {
    const r = window.canvasRenderer;
    const L = window.app.currentLayer;
    const logs = [];
    const realLog = window.sendClientLog;
    window.sendClientLog = (action, details) => {
        if (/^cabinet_ids_/.test(action)) logs.push([action, details]);
    };
    const realFill = r._fillText;
    const rows = [];
    try {
        for (const z of zooms) {
            let ids = 0;
            r._fillText = function (...a) { ids++; return realFill.apply(this, a); };
            r.zoom = z; r.render();
            rows.push([z, ids]);
        }
    } finally {
        r._fillText = realFill;
        window.sendClientLog = realLog;
    }
    return {rows, logs, cells: L.panels.filter(p => !p.hidden).length};
}"""


@pytest.fixture()
def page(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1600, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = ctx.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function('window.app && window.app.currentLayer && window.canvasRenderer')
    pg.locator('[data-mode="cabinet-id"]').click()
    pg.wait_for_function("window.canvasRenderer.viewMode === 'cabinet-id'")
    yield pg
    ctx.close()


def test_ids_stay_down_to_three_pixels_and_each_switch_logs_once(page):
    # The startup screen: 128 px cabinets, 30 px ids - one label each plus
    # the screen's name. 30 * 0.12 = 3.6 px is drawn now (5 px used to drop
    # it); 30 * 0.08 = 2.4 px is not.
    out = page.evaluate(PROBE, [1, 0.12, 0.08, 0.06, 0.12, 1])
    drawn = {z: n for z, n in out['rows'][:2]}
    assert drawn[0.12] == drawn[1] >= out['cells'], out
    by_zoom = [n for _, n in out['rows']]
    assert by_zoom[2] < by_zoom[1] and by_zoom[2] == by_zoom[3], out
    assert by_zoom[4] == by_zoom[1], out
    assert [a for a, _ in out['logs']] == ['cabinet_ids_hidden', 'cabinet_ids_shown'], out
    hidden = out['logs'][0][1]
    assert hidden['floorPx'] == 3 and hidden['screenPx'] < 3 and hidden['zoom'] == 0.08, out
    assert hidden['layer']['name'], out
