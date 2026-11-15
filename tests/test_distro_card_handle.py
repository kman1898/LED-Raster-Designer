"""The distro card in the Hardware tray: its OUTPUTS chips and its header bar.

Owner picks, 2026-10-20:
  * OUTPUTS, pick A "one chip per type": a distro whose face carries three
    one-Socapex rows shows ONE chip "Socapex 208V × 3", not three chips of
    "× 1" wrapping under the caption. The count is the outputs of that type
    on the face (what "× 1" meant per row), summed; a paired row keeps a
    chip of its own. The chips sit in a column of their own beside the
    OUTPUTS caption and wrap there, never under it. Dragging the grouped
    chip hands out the type's next free output, on whichever row it sits.
  * The header, pick C "whole header bar": the distro's header is a shaded
    bar with a bigger grip than the multi strips' own, a grab hand, and a
    "Drag onto a screen" hint in its empty stretch while hovered. A drag
    from anywhere on the bar is the grip's drag; a press on its controls
    (name field, Balance, gear, fold arrow) stays that control's gesture.

Real pointer drags and clicks throughout.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_card_handle.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL A: 8 wide x 18 rows of 200 W cabinets at 208 V / 10 A - a row is
# 1600 W and a circuit carries 2080 W, so one row per circuit: 18 circuits,
# three multis of six.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 8, rows: 18,
                              cabinet_width: 200, cabinet_height: 200})});
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 10, panelWatts: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    return p.layers[0].id;
}"""

# The show reshaped in the page: the distros given, nothing assigned.
SETUP_JS = """(distros) => {
    const app = window.app;
    const L = app.project.layers.find(l => l.name === 'WALL A');
    Object.assign(L, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                       powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                       powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                       powerBreakoutType: null, locked: false });
    app.normalizePowerBreakout(L);
    app.updateLayers([L]);
    app.project.distros = distros.map(d => JSON.parse(JSON.stringify(d)));
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app._persistDistros();
    app._restateNaming();
    app.renderHardwareDock();
    app.resetHistory('Card Seed');
    return app.getSocaPlan(L).length;
}"""

ROW = lambda rid, conn, count, coupling='ll', paired=None: {  # noqa: E731
    'id': rid, 'connector': conn, 'count': count, 'coupling': coupling,
    'breakerA': 20, 'pairedWith': paired}

# VX's Socapex on 10 A breakers, the screen's own Amperage: plugged-in
# circuits pack to the output's breaker (owner, 2026-11-12), so the wall
# keeps its three multis as each one lands (208 x 10 x 80% = 1,664 W, a
# row of eight 200 W cabinets a circuit, 18 circuits).
VX = {'id': 'd1', 'name': 'VX', 'ratingA': 200, 'system': '120/208',
      'outputRows': [dict(ROW(r, 'soca', 1), breakerA=10) for r in ('r1', 'r2', 'r3')]}

PANEL_POINT_JS = """() => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.name === 'WALL A');
    const p = layer.panels[0];
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + (p.x + p.width / 2 + dx + off.wx) * r.zoom + r.panX,
            y: rect.top + (p.y + p.height / 2 + dy + off.wy) * r.zoom + r.panY};
}"""

STATE_JS = """() => {
    const app = window.app;
    const L = app.project.layers.find(l => l.name === 'WALL A');
    app._circuitTailCache = null;
    return app.getSocaPlan(L).map(s => [s.distroId || null, s.number == null ? null : s.number]);
}"""

HIST_JS = "() => window.app.history.map(h => h.action)"
STATUS_JS = "() => document.getElementById('status-message').textContent"
HEAD = '[data-lrd-distro="d1"] > .hw-dock-head-row'


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
    pg.wait_for_timeout(1500)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def setup(pg, *distros):
    # The previous gesture's server echo lands first, so it cannot replace
    # the layer this setup writes.
    pg.wait_for_timeout(400)
    n = pg.evaluate(SETUP_JS, list(distros))
    pg.wait_for_timeout(300)
    return n


def center(pg, selector):
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", selector)
    box = pg.locator(selector).first.bounding_box()
    assert box, f'nothing at {selector}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def drag(pg, sx, sy, ex, ey, mid=None):
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    pg.mouse.move(ex, ey, steps=5)
    pg.wait_for_timeout(150)
    seen = mid() if mid else None
    pg.mouse.up()
    pg.wait_for_timeout(600)
    return seen


def chips(pg, distro_id):
    return pg.evaluate("""(id) => {
        const unit = document.querySelector(`[data-lrd-distro="${id}"]`);
        const row = unit.querySelector(':scope > .hw-dock-outputs');
        const cap = row.querySelector('.hw-dock-outputs-cap').getBoundingClientRect();
        return [...row.querySelectorAll('.hw-dock-plug')].map(c => {
            const r = c.getBoundingClientRect();
            return { name: c.querySelector('b').textContent,
                     sub: c.querySelector('small').textContent,
                     title: c.title,
                     group: JSON.parse(c.dataset.hwdockPayload).group,
                     rightOfCap: r.left >= cap.right };
        });
    }""", distro_id)


# ── OUTPUTS: one chip per connector type ──────────────────────────────────

def test_three_one_socapex_rows_read_as_one_chip_of_three(page):
    pg, errors = page
    setup(pg, VX)
    out = chips(pg, 'd1')
    assert [(c['name'], c['sub']) for c in out] == [('Socapex 208V', '× 3')], out
    assert out[0]['group'] == ['face:r1', 'face:r2', 'face:r3'], out
    assert out[0]['title'].startswith('3 × Socapex 208V on VX, 3 free.'), out[0]['title']
    assert not errors, errors


def test_types_sum_per_type_and_flow_beside_the_caption(page):
    """Rows of one type sum (Socapex 1 + 1, Edison 3 + 3); a paired row
    keeps its own chip; at a narrow tray the chips wrap in their own
    column, every one right of the caption."""
    pg, errors = page
    mixed = {'id': 'd1', 'name': 'SL', 'ratingA': 200, 'system': '120/208',
             'outputRows': [ROW('r1', 'soca', 1), ROW('r2', 'l2130', 1),
                            ROW('r3', 'soca', 1), ROW('r4', 'edison', 3, 'ln'),
                            ROW('r5', 'edison', 3, 'ln'),
                            ROW('r6', 'true1', 6, 'll', paired='r1')]}
    setup(pg, mixed)
    pg.evaluate("""() => {
        window.LRD_LAYOUT.move('hardware', 'right', 0);
        window.LRD_SIZES.restore({lrd_hardware_w: 340});
        window.app.renderHardwareDock();
    }""")
    pg.wait_for_timeout(300)
    try:
        out = chips(pg, 'd1')
        assert [(c['name'], c['sub']) for c in out] == [
            ('Socapex 208V', '× 2'), ('L21-30 208V', '× 1'), ('Edison', '× 6'),
            ('TRUE1 208V', '× 6 · paired')], out
        assert out[0]['group'] == ['face:r1', 'face:r3'], out
        assert out[2]['group'] == ['face:r4', 'face:r5'], out
        tops = pg.evaluate("""() => [...document.querySelectorAll(
            '[data-lrd-distro="d1"] .hw-dock-plug')].map(c => Math.round(c.getBoundingClientRect().top))""")
        assert len(set(tops)) > 1, f'the 340px tray should wrap the chips: {tops}'
        assert all(c['rightOfCap'] for c in out), out
    finally:
        pg.evaluate("""() => {
            window.LRD_SIZES.restore({lrd_hardware_w: 0});
            window.LRD_LAYOUT.reset();
            window.app.renderHardwareDock();
        }""")
    assert not errors, errors


def test_the_grouped_chip_hands_out_the_next_free_output_of_its_type(page):
    """Each drag of "Socapex 208V × 3" lands the screen's next multi on the
    next free Socapex - VX 1, then VX 2 on the second row, then VX 3 on the
    third - and a fourth is refused: every one is in use."""
    pg, errors = page
    assert setup(pg, VX) == 3
    tgt = pg.evaluate(PANEL_POINT_JS)
    for n in (1, 2, 3):
        sx, sy = center(pg, '[data-hwdock="plug-d1-face:r1"]')
        drag(pg, sx, sy, tgt['x'], tgt['y'])
        st = pg.evaluate(STATE_JS)
        assert st[:n] == [['d1', i] for i in range(1, n + 1)], (n, st)
        assert pg.evaluate(HIST_JS)[-1] == 'Assign Multi Distro'
    out = chips(pg, 'd1')
    assert out[0]['sub'] == '× 3' and '0 free' in out[0]['title'], out
    # a fourth: no free Socapex left - said on the strip, nothing changes
    pg.evaluate("""() => {
        const app = window.app;
        const L = app.project.layers.find(l => l.name === 'WALL A');
        app._dockDropPlug({ type: 'plug', distroId: 'd1', output: 'face:r1',
                            group: ['face:r1', 'face:r2', 'face:r3'], title: 'VX · Socapex 208V' },
                          { kind: 'screen', layerId: L.id });
    }""")
    assert pg.evaluate(STATUS_JS) == 'Every Socapex 208V on VX is in use.'
    assert not errors, errors


# ── the header bar is the distro's handle ─────────────────────────────────

def test_the_header_bar_reads_as_the_distro_s_handle(page):
    pg, errors = page
    setup(pg, VX)
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", HEAD)
    look = pg.evaluate("""(sel) => {
        const head = document.querySelector(sel);
        const multiGrip = document.querySelector('[data-lrd-distro="d1"] .hw-dock-multi .hw-dock-grip');
        const cs = getComputedStyle(head);
        return {
            cls: head.classList.contains('hw-dock-distro-head'),
            cursor: cs.cursor,
            shaded: cs.backgroundImage.includes('gradient'),
            grip: parseFloat(getComputedStyle(head.querySelector('.hw-dock-grip')).fontSize),
            multiGrip: parseFloat(getComputedStyle(multiGrip).fontSize),
            title: head.title,
            text: head.textContent,
        };
    }""", HEAD)
    assert look['cls'] and look['cursor'] == 'grab' and look['shaded'], look
    assert look['grip'] > look['multiGrip'], look
    assert look['title'].startswith('Drag onto a screen'), look
    assert 'Drag onto' not in look['text'], 'the hint leaked into the header text'
    cue = '[data-lrd-distro="d1"] .hw-dock-dragcue > i'
    shown = "(s) => getComputedStyle(document.querySelector(s)).opacity"
    x, y = center(pg, '[data-lrd-distro="d1"] .hw-dock-dragcue')
    pg.mouse.move(x, y)
    pg.wait_for_timeout(250)
    assert pg.evaluate(shown, cue) == '1', 'the hint does not show over the bar'
    bx, by = center(pg, '[data-lrd-field="distro-balance-d1"]')
    pg.mouse.move(bx, by)
    pg.wait_for_timeout(250)
    assert pg.evaluate(shown, cue) == '0', 'the hint shows over Balance'
    pg.mouse.move(5, 5)
    assert not errors, errors


def test_a_drag_from_the_bar_s_empty_stretch_moves_the_distro(page):
    pg, errors = page
    assert setup(pg, VX) == 3
    x, y = center(pg, '[data-lrd-distro="d1"] .hw-dock-dragcue')
    hit = pg.evaluate("([x, y]) => document.elementFromPoint(x, y).classList.contains('hw-dock-distro-head')",
                      [x, y])
    assert hit, 'the empty stretch is not the bar'
    tgt = pg.evaluate(PANEL_POINT_JS)
    ghost = drag(pg, x, y, tgt['x'], tgt['y'],
                 mid=lambda: pg.evaluate("() => (document.getElementById('hw-dock-ghost') || {}).textContent"))
    assert ghost == 'VX', ghost
    st = pg.evaluate(STATE_JS)
    assert [s[0] for s in st] == ['d1', 'd1', 'd1'], st
    assert pg.evaluate(HIST_JS)[-1] == 'Assign Multi Distro'
    assert not errors, errors


@pytest.mark.parametrize('control', ['name', 'balance', 'gear', 'arrow'])
def test_the_bar_s_controls_stay_controls(page, control):
    """A press on the name field, Balance, the gear or the fold arrow,
    dragged onto the screen, starts no drag and assigns nothing; a plain
    click does what that control does."""
    pg, errors = page
    setup(pg, VX)
    sel = {
        'name': '[data-lrd-field="distro-name-d1"]',
        'balance': '[data-lrd-field="distro-balance-d1"]',
        'gear': '[data-hwpop="distro-d1"]',
        'arrow': f'{HEAD} .lrd-sec-arrow',
    }[control]
    pg.evaluate("() => { window.__balanced = null; window.app.__showBalance = window.app.showBalanceDialog;"
                " window.app.showBalanceDialog = (id) => { window.__balanced = id; }; }")
    try:
        tgt = pg.evaluate(PANEL_POINT_JS)
        sx, sy = center(pg, sel)
        ghost = drag(pg, sx, sy, tgt['x'], tgt['y'],
                     mid=lambda: pg.evaluate("() => !!document.getElementById('hw-dock-ghost')"))
        assert ghost is False, f'a press on {control} started a drag'
        assert all(s[0] is None for s in pg.evaluate(STATE_JS)), 'a control press assigned a multi'
        pg.evaluate("() => window.app._hwPopoverClose && window.app._hwPopoverClose()")
        pg.evaluate("() => { window.__balanced = null; }")
        sx, sy = center(pg, sel)
        pg.mouse.click(sx, sy)
        pg.wait_for_timeout(250)
        if control == 'name':
            assert pg.evaluate("() => document.activeElement.dataset.lrdField") == 'distro-name-d1'
        elif control == 'balance':
            assert pg.evaluate("() => window.__balanced") == 'd1'
        elif control == 'gear':
            assert pg.evaluate("() => document.getElementById('hw-gear-popover').style.display") == 'block'
        else:
            assert pg.evaluate("() => document.querySelector('[data-lrd-distro=\"d1\"]')"
                               ".classList.contains('lrd-sec-collapsed')"), 'the arrow did not fold'
            pg.mouse.click(sx, sy)
            pg.wait_for_timeout(200)
    finally:
        pg.evaluate("() => { window.app.showBalanceDialog = window.app.__showBalance;"
                    " delete window.app.__showBalance;"
                    " window.app._hwPopoverClose && window.app._hwPopoverClose();"
                    " document.activeElement && document.activeElement.blur(); }")
    assert not errors, errors
