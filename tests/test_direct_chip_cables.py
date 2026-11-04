"""A direct output's cable reads the same in the tray as on the map, the
pull sheet and the binder (owner ruling, 2026-10-21).

  * the direct output's chip corner names the cable outlet to panel
    ("Edison → powerCON", directCableType), never the outlet alone, and
    writes its length from the direct-output stock;
  * a circuit alone on a direct output with its own cable typed wears that
    cable from the direct-output stock too (directCircuitCable), on the
    chip, the map tag and the box's cable sheet - never the circuit stock;
  * the chip's length field says what the pull sheet will list.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_direct_chip_cables.py -q --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_naming import DIST, ROWS_JS, ev, setup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate("""async () => {
        const app = window.app;
        await app._layerSavesSettled();
        const j = async (method, url, body) => (await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body) })).json();
        const proj = await j('GET', '/api/project');
        proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
        delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
        await j('PUT', '/api/project', proj);
        await j('POST', '/api/layer/add', { name: 'WALL A', columns: 10, rows: 6,
            cabinet_width: 200, cabinet_height: 200 });
        await j('POST', '/api/layer/add', { name: 'WALL B', columns: 6, rows: 3,
            cabinet_width: 200, cabinet_height: 200, offset_x: 2600 });
        const p = await j('GET', '/api/project');
        app.project = p;
        app.selectLayer(p.layers[0]);
        app.renderLayers();
    }""")
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    yield pg, errors
    context.close()


# A 40' cable: the circuit stock writes it as one 50' piece, the
# direct-output stock as 30' + 10'.
STOCK = {'perKind': True, 'ft': {'circuit': [50], 'direct': [10, 30]}, 'm': {}}

CHIPS_JS = """
    app.renderHardwareDock();
    const unit = document.querySelector('[data-lrd-distro="d1"]');
    const corners = [...unit.querySelectorAll('.hw-dock-direct .lrd-tile')]
        .map(t => (t.querySelector('.hw-dock-chip-cable') || {}).textContent || null);
    const field = unit.querySelector(`[data-lrd-field="direct-length-${B.id}-1"]`);
    return { corners, tip: field ? field.title : null };"""


def _direct_setup(pg):
    """WALL B (120V, powerCON panels) alone on PD 3, an Edison outlet,
    its home run 40'."""
    nums = setup(pg, distros=[DIST], walls={
        'b': {'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 3},
              'powerSocaLengths': {'1': '40'}}})
    ev(pg, "app.project.cableStock = arg; return null;", STOCK)
    return nums['WALL B'][0]


def test_the_chip_names_the_cable_outlet_to_panel_from_the_direct_stock(page):
    """Home run only: the chip's corner is "30'+10' Edison → powerCON", what
    the pull sheet lists, and its field says the pull sheet lists it as
    "Edison → powerCON"."""
    pg, errors = page
    b1 = _direct_setup(pg)
    try:
        want = ev(pg, "return app.directCircuitCable(B, arg).text;", b1)
        assert want == "30'+10' Edison → powerCON", want
        rows = pg.evaluate(ROWS_JS)
        assert sorted(r[1] for r in rows if r[3] == 'PD3' and r[0] == 'Edison → powerCON') == [
            "10'", "30'"], rows
        out = ev(pg, CHIPS_JS)
        assert want in out['corners'], out
        assert not [c for c in out['corners'] if c and c.endswith(' Edison')], out
        assert out['tip'] and 'in feet. It goes on the pull sheet as Edison → powerCON.' in out['tip'], out
        assert ' run.' not in out['tip'], out
    finally:
        ev(pg, "delete app.project.cableStock; return null;")
    assert errors == [], errors


def test_a_circuits_own_cable_on_a_direct_output_reads_the_direct_stock(page):
    """The circuit's own 40' cable on the direct output: the chip, the map
    tag and the box's cable sheet total all say "30'+10' Edison →
    powerCON" (the direct-output stock), never "50' Edison → powerCON"
    (the circuit stock)."""
    pg, errors = page
    b1 = _direct_setup(pg)
    try:
        ev(pg, "B.powerCircuitCables = { [arg]: { ft: 40, connector: null } };"
               " app._circuitTailCache = null; return null;", b1)
        texts = ev(pg, "return { own: app.powerCircuitCable(B, arg).text,"
                       " direct: app.directCircuitCable(B, arg).text };", b1)
        assert texts == {'own': "50' Edison → powerCON", 'direct': "30'+10' Edison → powerCON"}, texts
        out = ev(pg, CHIPS_JS)
        assert texts['direct'] in out['corners'] and texts['own'] not in out['corners'], out
        # the map's cable tag
        tags = ev(pg, """
            B.showPowerCableTags = true;
            const r = window.canvasRenderer;
            const seen = [];
            const orig = r.drawCableTag;
            r.drawCableTag = function (t, ...rest) { seen.push(String(t)); return orig.call(this, t, ...rest); };
            try { r.render(); } finally { r.drawCableTag = orig; delete B.showPowerCableTags; }
            return seen.filter(t => /Edison/.test(t));""")
        assert tags == [texts['direct']], tags
        # the box's cable sheet totals this box's cables
        total = ev(pg, """
            const d = app.getDistros()[0];
            const byTail = new Map([[1, [{ layerId: B.id, circuit: arg, label: 'x', who: B.name }]]]);
            const sheet = app._dockBuildCableSheet(d, 3, 1, byTail);
            return sheet.querySelector('.hw-dock-cable-total').lastElementChild.textContent;""", b1)
        assert total == f"1 × {texts['direct']}", total
    finally:
        ev(pg, "delete app.project.cableStock; B.powerCircuitCables = {};"
               " app._circuitTailCache = null; return null;")
    assert errors == [], errors
