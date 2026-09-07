"""Distro outputs: the connector is the thing you drag.

A distro declares the connector TYPES it offers (types only, no counts) in
its ⚙ popover's OUTPUTS checklist - Soca 208 (True1 / powerCON), Soca 120
(Edison), L21-30 (3 × 208V). The tray shows one plug chip per ticked type
on a slim OUTPUTS row under the distro's LEGS line, and dragging a chip onto
a screen lands one box of that type: the screen's next unassigned multi
(split-aware plan order) goes on that distro, numbered by the distro's own
sequence. Mid-drag, EXACTLY the circuits the drop would feed light under the
cursor, a dashed pending bracket names the box, and a cursor pill says what
the release will do; a type mismatch (the connector against the screen's
effective breakout) lights nothing, turns the pill red with the fix, and the
drop is refused on the status strip. The right-click path is the same drop
through a submenu: "Add <type> from…" lists every distro that offers the
screen's connector with its load, the rest greyed with the reason. The
opt-in soca brackets carry the type as a text badge, on screen and in
export.

Pinned here, with real pointer drags and real right-clicks:
  * the popover's three tick rows, all inside the popover's own box; a
    distro with no `outputs` key reads as offering everything (legacy
    files keep dragging), an explicit list stands as written, and each
    tick is one 'Edit Distro' entry that redraws the chips
  * chips render per ticked type; nothing ticked = no row, and the
    whole-distro handle stays
  * preview == result: the circuits lit mid-drag are the circuits the drop
    assigns, the pill's box name is the number the box actually gets,
    one 'Assign Multi Distro' entry, one undo walks it back
  * a second box lands on the NEXT multi (7–12), never the first again
  * mismatches refuse with the sentence naming the screen's breakout -
    L21-30 against a soca, a soca against L21-30, a Soca 208 against an
    Edison (110V) screen - and nothing mutates
  * the pill warns amber (still allowed) when the box would push the
    distro's legs past its rating
  * the submenu lists offering distros with their loads, greys the rest
    with the reason, and a pick is the same drop
  * brackets wear the type badge on screen and in export mode
  * the type lives on the BOX too (2026-09-05, "Type chip on the spare
    box ... or both places rather"): every multi header wears a type
    chip; a spare box's chip cycles the offered types (one 'Set Multi
    Type' entry, undo restores), an occupied box's chip is read-only and
    reads its members' breakout; a typed spare box drags as its plug -
    same gate, same refusal, same pill - and lands with the anchored
    take; every drop stamps `boxTypes`; a legacy distro without the key
    reads its occupied boxes from their members and shows no clash

Run locally:
    python3 -m pytest tests/test_distro_outputs.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL A: 8 wide × 12 rows of 200 W cabinets at 208 V / 10 A - a row is
# 1600 W and a circuit carries 2080 W, so one row per circuit: 12 circuits,
# two multis of six (1–6, 7–12). WALL B: 6 × 3, three circuits, far enough
# right that a drop on one can never smear onto the other. One distro, PD,
# with no `outputs` key - the legacy shape.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 8, rows: 12,
                              cabinet_width: 200, cabinet_height: 200})});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL B', columns: 6, rows: 3,
                              cabinet_width: 200, cabinet_height: 200,
                              offset_x: 2400})});
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 10,
                                  panelWatts: 200,
                                  processorType: 'novastar-coex-1g'})});
    }
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.addDistro({name: 'PD'});
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    app.resetHistory('Outputs Seed');
    return {
        aId: p.layers.find(l => l.name === 'WALL A').id,
        bId: p.layers.find(l => l.name === 'WALL B').id,
        distroId: app.getDistros()[0].id,
    };
}"""

# Back to virgin: no distro on any multi, no pin, no breakout choice, the
# distro offering everything again (no key), stock rating.
RESET_JS = """(ids) => {
    const app = window.app;
    const touched = [];
    for (const id of [ids.aId, ids.bId]) {
        const l = app.project.layers.find(x => x.id === id);
        if (!l) continue;
        for (const k of ['powerSocaDistro', 'powerSocaNumber',
                         'powerSocaPhasePos']) {
            if (l[k] && Object.keys(l[k]).length) { l[k] = {}; touched.push(l); }
        }
        if (l.powerBreakoutType || l.showSocaBrackets
                || Number(l.powerVoltage) !== 208) {
            l.powerBreakoutType = null;
            l.showSocaBrackets = false;
            l.powerVoltage = 208;
            touched.push(l);
        }
    }
    if (touched.length) app.updateLayers([...new Set(touched)]);
    const d = app.getDistros().find(x => x.id === ids.distroId);
    delete d.outputs;
    delete d.boxTypes;
    d.ratingA = 400;
    app._circuitTailCache = null;
    app._restateNaming();
    app.renderHardwareDock();
    app.resetHistory('Outputs Seed');
    return true;
}"""

PANEL_POINT_JS = """([layerId, which]) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    let p;
    if (which.circuit !== undefined) {
        p = app.screenCircuits(layer)[which.circuit].panels[0];
    } else {
        p = layer.panels[0];
    }
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + dx + off.wx;
    const wy = p.y + p.height / 2 + dy + off.wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + wx * r.zoom + r.panX,
            y: rect.top + wy * r.zoom + r.panY};
}"""

HIST_JS = "(n) => window.app.history.map(h => h.action).slice(-n)"
HIST_LEN_JS = "() => window.app.history.length"
STATUS_JS = "() => document.getElementById('status-message').textContent"

# The mid-drag picture, in the user's terms: the target the dock resolved,
# the pill as shown, and which circuits of the screen the renderer lights.
MID_JS = """(layerId) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const t = app._dockDropTarget;
    const pill = document.getElementById('hw-dock-pill');
    const layer = app.project.layers.find(l => l.id === layerId);
    const count = app.screenCircuits(layer).length;
    const lit = [];
    for (let n = 1; n <= count; n++) if (r._runUnderlayLit(layer, n)) lit.push(n);
    return {
        target: t,
        pill: pill && pill.style.display !== 'none' ? {
            text: pill.textContent, cls: pill.className,
        } : null,
        lit,
        ghost: !!document.getElementById('hw-dock-ghost'),
    };
}"""

POWER_STATE_JS = """(layerId) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === layerId);
    app._circuitTailCache = null;
    return {
        distro: l.powerSocaDistro || {},
        num: l.powerSocaNumber || {},
        plan: app.getSocaPlan(l).map(s => ({
            soca: s.soca, distroId: s.distroId, number: s.number,
            name: s.name, circuits: s.legs.map(g => g.circuit),
        })),
    };
}"""

CHIPS_JS = """(distroId) => {
    const unit = document.querySelector(
        `[data-lrd-sec="hwdock-distro-${distroId}"]`).parentElement;
    const row = unit.querySelector(':scope > .hw-dock-outputs');
    return {
        row: !!row,
        chips: Array.from(unit.querySelectorAll('[data-hwdock^="plug-"]'))
            .map(el => el.dataset.hwdock),
        distroHandle: !!unit.querySelector(`[data-hwdock="distro-${distroId}"]`),
        legsBeforeRow: !!(row && row.previousElementSibling
            && row.previousElementSibling.classList.contains('hw-dock-legs')),
    };
}"""

# The popover's outputs block: every tick row, and whether every element of
# the popover sits inside the popover's own box (the resize suite's rule).
POPOVER_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop || pop.style.display === 'none') return null;
    const box = pop.getBoundingClientRect();
    const strays = [];
    pop.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5
                || r.bottom > box.bottom + 0.5 || r.top < box.top - 0.5) {
            strays.push({tag: el.tagName, cls: el.className.baseVal
                         || el.className, over: Math.round(Math.max(
                r.right - box.right, box.left - r.left,
                r.bottom - box.bottom, box.top - r.top))});
        }
    });
    return {
        ticks: Array.from(pop.querySelectorAll('[data-lrd-field^="distro-out-"]'))
            .map(cb => ({key: cb.dataset.lrdField, checked: cb.checked})),
        names: Array.from(pop.querySelectorAll('.hw-pop-out b'))
            .map(b => b.textContent),
        strays, w: Math.round(box.width), h: Math.round(box.height),
    };
}"""

MENU_JS = """() => {
    const menu = document.getElementById('context-menu');
    const parent = menu.querySelector('[data-action="hw-outputs"]');
    const shown = el => !!el && getComputedStyle(el).display !== 'none';
    return {
        menuShown: menu.style.display === 'block',
        shown: shown(parent),
        label: (menu.querySelector('#hw-outputs-label') || {}).textContent,
        entries: Array.from(menu.querySelectorAll(
            '#hw-outputs-submenu .menu-option')).map(el => ({
                label: el.textContent, action: el.dataset.action,
                disabled: el.classList.contains('menu-disabled'),
                title: el.title,
            })),
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(600)
    yield pg, ids
    context.close()


def panel_point(page, layer_id, which):
    return page.evaluate(PANEL_POINT_JS, [layer_id, which])


def drag(page, sx, sy, ex, ey, mid_check=None):
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=5)
    page.mouse.move(ex, ey, steps=5)
    page.wait_for_timeout(150)
    mid = mid_check(page) if mid_check else None
    page.mouse.up()
    page.wait_for_timeout(700)
    return mid


def chip_center(page, key):
    page.evaluate(
        """(key) => {
            const el = document.querySelector(`[data-hwdock="${key}"]`);
            if (el) el.scrollIntoView({ block: 'nearest' });
        }""", key)
    box = page.locator(f'[data-hwdock="{key}"]').bounding_box()
    assert box, f'no dock chip {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def close_menu(page):
    pt = page.evaluate("""() => {
        const r = window.canvasRenderer.canvas.getBoundingClientRect();
        return {x: r.left + 15, y: r.top + 15};
    }""")
    page.mouse.click(pt['x'], pt['y'])
    page.wait_for_timeout(250)


# ── the popover and the chips ─────────────────────────────────────────────

def test_the_popover_ticks_three_outputs_inside_its_box_and_writes_them(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    pg.locator(f'[data-hwpop="distro-{ids["distroId"]}"]').click()
    pg.wait_for_timeout(300)
    pop = pg.evaluate(POPOVER_JS)
    assert pop, 'the distro gear opened no popover'
    assert pop['names'] == ['Soca 208', 'Soca 120', 'L21-30'], pop
    # legacy shape: no key reads as everything offered
    assert [t['checked'] for t in pop['ticks']] == [True, True, True], pop
    assert not pop['strays'], (
        f"outputs rows overflow the popover's box: {pop['strays']} "
        f"(popover is {pop['w']}x{pop['h']}px)")
    before = pg.evaluate(HIST_LEN_JS)
    pg.locator(f'#hw-gear-popover [data-lrd-field="distro-out-soca120-'
               f'{ids["distroId"]}"]').click()
    pg.wait_for_timeout(500)
    out = pg.evaluate("""(id) => {
        const d = window.app.getDistros().find(x => x.id === id);
        return {outputs: d.outputs,
                popOpen: document.getElementById('hw-gear-popover')
                    .style.display !== 'none'};
    }""", ids['distroId'])
    assert out['outputs'] == ['soca208', 'l2130'], out
    assert out['popOpen'], 'the tick closed the popover'
    assert pg.evaluate(HIST_LEN_JS) == before + 1
    assert pg.evaluate(HIST_JS, 1) == ['Edit Distro']
    chips = pg.evaluate(CHIPS_JS, ids['distroId'])
    assert chips['chips'] == [f'plug-{ids["distroId"]}-soca208',
                              f'plug-{ids["distroId"]}-l2130'], chips
    # the popover re-rendered against the fresh state, still bounded
    pop = pg.evaluate(POPOVER_JS)
    assert [t['checked'] for t in pop['ticks']] == [True, False, True], pop
    assert not pop['strays'], pop['strays']
    pg.locator(f'#hw-gear-popover [data-lrd-field="distro-out-soca120-'
               f'{ids["distroId"]}"]').click()
    pg.wait_for_timeout(500)
    assert pg.evaluate("(id) => window.app.getDistros().find(x => x.id === id)"
                       ".outputs", ids['distroId']) == \
        ['soca208', 'soca120', 'l2130']
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    pg.evaluate(RESET_JS, ids)


def test_chips_render_per_ticked_type_under_the_legs_line(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    chips = pg.evaluate(CHIPS_JS, d)
    assert chips['row'] and chips['legsBeforeRow'], chips
    assert chips['chips'] == [f'plug-{d}-soca208', f'plug-{d}-soca120',
                              f'plug-{d}-l2130'], chips
    # an explicit list stands as written; nothing ticked = no row, and the
    # whole-distro handle stays
    pg.evaluate("""(id) => {
        window.app.updateDistro(id, {outputs: []});
        window.app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(300)
    chips = pg.evaluate(CHIPS_JS, d)
    assert chips['chips'] == [] and not chips['row'], chips
    assert chips['distroHandle'], chips
    pg.evaluate("""(id) => {
        window.app.updateDistro(id, {outputs: ['l2130']});
        window.app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(300)
    chips = pg.evaluate(CHIPS_JS, d)
    assert chips['chips'] == [f'plug-{d}-l2130'], chips
    # unknown ids are dropped, order is the catalog's
    pg.evaluate("""(id) => {
        window.app.updateDistro(id, {outputs: ['l2130', 'bogus', 'soca208']});
    }""", d)
    assert pg.evaluate("(id) => window.app.getDistros().find(x => x.id === id)"
                       ".outputs", d) == ['soca208', 'l2130']
    pg.evaluate(RESET_JS, ids)


# ── the drag: preview == result ───────────────────────────────────────────

def test_drag_preview_lights_exactly_what_the_drop_assigns(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    # aim past the first multi: the drop still feeds the NEXT unassigned
    # multi (1–6), wherever on the screen the chip lands
    tgt = panel_point(pg, ids['aId'], {'circuit': 8})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['ghost'], 'no ghost rode the drag'
    t = mid['target']
    assert t and t['kind'] == 'screen' and t['layerId'] == ids['aId'], mid
    assert t['nums'] == [1, 2, 3, 4, 5, 6], mid
    assert mid['lit'] == [1, 2, 3, 4, 5, 6], (
        f'the underlay lit something other than the drop\'s reach: {mid}')
    # the box is named the way the wall will print it (the naming index's
    # own derivation, "PD1"), so the pending bracket and the committed one
    # read the same
    assert t['plug']['ok'] and t['plug']['boxName'] == 'PD1', mid
    assert mid['pill'] and mid['pill']['cls'] == '', mid
    assert mid['pill']['text'] == 'PD1 → circuits 1–6 · 46 A', mid
    # the release: the same multi, the same number, one entry
    st = pg.evaluate(POWER_STATE_JS, ids['aId'])
    assert st['distro'] == {'1': d}, st
    assert st['num'] == {}, f'the plug drop pinned a number: {st}'
    first = next(s for s in st['plan'] if s['soca'] == 1)
    assert first['distroId'] == d and first['number'] == 1, st
    assert first['circuits'] == mid['lit'], (
        f'the drop fed {first["circuits"]} but the preview lit {mid["lit"]}')
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    assert not pg.evaluate("() => document.getElementById('hw-dock-pill')"), (
        'the pill outlived the drag')
    # a second box lands on the NEXT multi, named by the sequence
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['aId'], {'circuit': 0})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [7, 8, 9, 10, 11, 12], mid
    assert mid['pill']['text'] == 'PD2 → circuits 7–12 · 46 A', mid
    st = pg.evaluate(POWER_STATE_JS, ids['aId'])
    assert st['distro'] == {'1': d, '2': d}, st
    second = next(s for s in st['plan'] if s['soca'] == 2)
    assert second['number'] == 2 and second['circuits'] == mid['lit'], st
    # nothing left to feed: the chip says so and changes nothing
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert 'Every multi on WALL A already has a distro' in mid['pill']['text']
    assert pg.evaluate(HIST_LEN_JS) == n
    # one undo per box
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {'1': d}
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    pg.evaluate(RESET_JS, ids)


def test_a_mismatched_connector_is_refused_with_the_fix(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setPowerBreakout(b, 'l2130-true1');
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    d = ids['distroId']
    n = pg.evaluate(HIST_LEN_JS)
    # a soca against an L21-30 box
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['bId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['target']['nums'] == [] and mid['lit'] == [], mid
    assert mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL B is set to L21-30 — change its breakout first', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    assert pg.evaluate(STATUS_JS) == \
        'WALL B is set to L21-30 — change its breakout first'
    assert pg.evaluate(HIST_LEN_JS) == n, 'a refused drop earned an entry'
    # an L21-30 against a soca screen (WALL A defaults to Multi → True1)
    sx, sy = chip_center(pg, f'plug-{d}-l2130')
    tgt = panel_point(pg, ids['aId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL A is set to Multi → True1 — change its breakout first', mid
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    # the L21-30 chip DOES land on the L21-30 box - three circuits, one box
    sx, sy = chip_center(pg, f'plug-{d}-l2130')
    tgt = panel_point(pg, ids['bId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [1, 2, 3], mid
    assert mid['pill']['text'].startswith('PD1 → circuits 1–3 ·'), mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    # a Soca 208 onto an Edison (110V) screen: the voltage mismatch, off
    # the screen's DEFAULT breakout (nothing stored)
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 120;
        app.updateLayers([b]);
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['bId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL B is set to Edison (110V) — change its breakout first', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    # and the Soca 120 chip is what that screen takes
    sx, sy = chip_center(pg, f'plug-{d}-soca120')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] and mid['pill']['cls'] == '', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    pg.evaluate(RESET_JS, ids)


def test_the_pill_warns_amber_past_the_rating_and_still_lands(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(id) => {
        window.app.updateDistro(id, {ratingA: 5});
        window.app._restateNaming();
    }""", ids['distroId'])
    pg.wait_for_timeout(600)
    d = ids['distroId']
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['aId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [1, 2, 3, 4, 5, 6], mid
    assert mid['pill']['cls'] == 'hw-dock-pill-warn', mid
    assert mid['pill']['text'].startswith('PD1 → circuits 1–6 · 46 A — '
                                          'PD legs to '), mid
    assert ' A of 5 A' in mid['pill']['text'], mid
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {'1': d}
    assert 'PD1 landed on WALL A' in pg.evaluate(STATUS_JS)
    pg.evaluate(RESET_JS, ids)


def test_escape_cancels_a_plug_drag_without_a_drop(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    d = ids['distroId']
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['aId'], {})
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move(tgt['x'], tgt['y'], steps=8)
    pg.wait_for_timeout(150)
    assert pg.evaluate(MID_JS, ids['aId'])['lit'] == [1, 2, 3, 4, 5, 6]
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    gone = pg.evaluate("""() => ({
        ghost: !!document.getElementById('hw-dock-ghost'),
        pill: !!document.getElementById('hw-dock-pill'),
        target: window.app._dockDropTarget,
    })""")
    assert not gone['ghost'] and not gone['pill'] and gone['target'] is None, gone
    pg.mouse.up()
    pg.wait_for_timeout(400)
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    assert pg.evaluate(HIST_LEN_JS) == n
    pg.evaluate(RESET_JS, ids)


# ── the click path ────────────────────────────────────────────────────────

def test_the_submenu_lists_offering_distros_with_loads(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    sr = pg.evaluate("""() => {
        const app = window.app;
        const d = app.addDistro({name: 'SR'});
        app.updateDistro(d.id, {outputs: ['l2130']});
        app._restateNaming();
        return d.id;
    }""")
    pg.wait_for_timeout(600)
    try:
        d = ids['distroId']
        tgt = panel_point(pg, ids['aId'], {'circuit': 3})
        pg.mouse.click(tgt['x'], tgt['y'], button='right')
        pg.wait_for_timeout(400)
        m = pg.evaluate(MENU_JS)
        assert m['menuShown'] and m['shown'], m
        assert m['label'] == 'Add Soca 208 from…', m
        assert [(e['label'], e['disabled']) for e in m['entries']] == [
            ('PD 0/400 A', False),
            ('SR — does not offer soca 208', True)], m
        assert 'Tick Soca 208 under SR' in m['entries'][1]['title'], m
        # hover opens the submenu; the pick is the drop
        pg.locator('#context-menu [data-action="hw-outputs"]').hover()
        pg.wait_for_timeout(200)
        pg.locator('#hw-outputs-submenu [data-action="hw-out-0"]').click()
        pg.wait_for_timeout(700)
        st = pg.evaluate(POWER_STATE_JS, ids['aId'])
        assert st['distro'] == {'1': d}, st
        assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
        assert not pg.evaluate("() => document.getElementById('context-menu')"
                               ".style.display === 'block'"), 'menu stayed up'
        # the load moved with it (the roll-up's own figure - six 1600 W
        # circuits on a 208 V 3φ service, I = P / (V × 1.73) = 27 A), and
        # the greyed entry cannot act
        pg.mouse.click(tgt['x'], tgt['y'], button='right')
        pg.wait_for_timeout(400)
        m = pg.evaluate(MENU_JS)
        assert m['entries'][0]['label'] == 'PD 27/400 A', m
        pg.locator('#context-menu [data-action="hw-outputs"]').hover()
        pg.wait_for_timeout(200)
        n = pg.evaluate(HIST_LEN_JS)
        pg.locator('#hw-outputs-submenu [data-action="hw-out-1"]').click()
        pg.wait_for_timeout(400)
        assert pg.evaluate(HIST_LEN_JS) == n
        assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {'1': d}
        close_menu(pg)
        # an L21-30 screen asks for its own connector: SR offers it, PD too
        pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            app.setPowerBreakout(b, 'l2130-true1');
            app._restateNaming();
        }""", ids)
        pg.wait_for_timeout(600)
        tgt = panel_point(pg, ids['bId'], {})
        pg.mouse.click(tgt['x'], tgt['y'], button='right')
        pg.wait_for_timeout(400)
        m = pg.evaluate(MENU_JS)
        assert m['label'] == 'Add L21-30 from…', m
        assert [(e['label'], e['disabled']) for e in m['entries']] == [
            ('PD 27/400 A', False), ('SR 0/400 A', False)], m
        close_menu(pg)
        # the same item from the tray: a circuit chip names its screen
        key = pg.evaluate("""(d) => {
            const el = document.querySelector(
                `[data-hwdock^="tail-${d}-1-"]`);
            return el ? el.dataset.hwdock : null;
        }""", d)
        assert key, 'no circuit chip on PD 1'
        cx, cy = chip_center(pg, key)
        pg.mouse.click(cx, cy, button='right')
        pg.wait_for_timeout(400)
        m = pg.evaluate(MENU_JS)
        assert m['menuShown'] and m['shown'], m
        assert m['label'] == 'Add Soca 208 from…', m
        close_menu(pg)
    finally:
        pg.evaluate("(id) => window.app.removeDistro(id)", sr)
        pg.evaluate(RESET_JS, ids)


# ── the brackets ──────────────────────────────────────────────────────────

BRACKET_TEXTS_JS = """([layerId, exportMode]) => {
    const app = window.app;
    const cr = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    const seen = [];
    const orig = cr._fillText;
    const wasExport = cr.exportMode;
    cr._fillText = function (text) { seen.push(String(text)); };
    cr.exportMode = !!exportMode;
    try { cr.renderSocaBrackets(layer); }
    finally { cr._fillText = orig; cr.exportMode = wasExport; }
    return seen;
}"""


def test_brackets_wear_the_type_badge_on_screen_and_in_export(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        a.showSocaBrackets = true;
        b.showSocaBrackets = true;
        app.setPowerBreakout(b, 'l2130-powercon');
        app.setSocaDistro(a, 1, ids.distroId);
        app.setSocaLength(a, 1, '100ft');
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    on_screen = pg.evaluate(BRACKET_TEXTS_JS, [ids['aId'], False])
    assert on_screen.count('SOCA 208') == 2, on_screen   # one per multi
    assert any(t.startswith('PD1 · ') and '100ft' not in t
               for t in on_screen), on_screen
    exported = pg.evaluate(BRACKET_TEXTS_JS, [ids['aId'], True])
    assert exported.count('SOCA 208') == 2, exported
    assert any(t.startswith('PD1 · 100ft · ') for t in exported), exported
    assert 'L21-30' in pg.evaluate(BRACKET_TEXTS_JS, [ids['bId'], True])
    # Edison screen: SOCA 120 off the default breakout
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerBreakoutType = null;
        b.powerVoltage = 120;
        app.updateLayers([b]);
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(400)
    assert 'SOCA 120' in pg.evaluate(BRACKET_TEXTS_JS, [ids['bId'], False])
    pg.evaluate(RESET_JS, ids)


def test_the_pending_bracket_names_the_box_the_drop_would_make(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    d = ids['distroId']
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['aId'], {})
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move(tgt['x'], tgt['y'], steps=8)
    pg.wait_for_timeout(150)
    # brackets OFF: the pending-only pass draws exactly the one box
    texts = pg.evaluate("""(layerId) => {
        const app = window.app;
        const cr = window.canvasRenderer;
        const layer = app.project.layers.find(l => l.id === layerId);
        const seen = [];
        const orig = cr._fillText;
        cr._fillText = function (text) { seen.push(String(text)); };
        try { cr.renderSocaBrackets(layer, true); }
        finally { cr._fillText = orig; }
        return seen;
    }""", ids['aId'])
    assert texts == ['SOCA 208', 'PD1 · 46.2A'], texts
    pg.keyboard.press('Escape')
    pg.mouse.up()
    pg.wait_for_timeout(300)
    # and with no drag on, the pending-only pass draws nothing
    texts = pg.evaluate("""(layerId) => {
        const app = window.app;
        const cr = window.canvasRenderer;
        const layer = app.project.layers.find(l => l.id === layerId);
        const seen = [];
        const orig = cr._fillText;
        cr._fillText = function (text) { seen.push(String(text)); };
        try { cr.renderSocaBrackets(layer, true); }
        finally { cr._fillText = orig; }
        return seen;
    }""", ids['aId'])
    assert texts == [], texts
    pg.evaluate(RESET_JS, ids)


# ── legacy files ──────────────────────────────────────────────────────────

def test_a_distro_with_no_outputs_key_still_drags_whole(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    d = ids['distroId']
    assert pg.evaluate("(id) => 'outputs' in window.app.getDistros()"
                       ".find(x => x.id === id)", d) is False
    sx, sy = chip_center(pg, f'distro-{d}')
    tgt = panel_point(pg, ids['aId'], {})
    drag(pg, sx, sy, tgt['x'], tgt['y'])
    st = pg.evaluate(POWER_STATE_JS, ids['aId'])
    assert st['distro'] == {'1': d, '2': d}, st
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    # the key survives a project round-trip untouched (no server allow-list
    # rewrites the distro)
    pg.evaluate("(id) => window.app.updateDistro(id, {outputs: ['soca120']})", d)
    pg.wait_for_timeout(600)
    served = pg.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        return p.distros.find(x => x.id === id).outputs;
    }""", d)
    assert served == ['soca120'], served
    pg.evaluate(RESET_JS, ids)


# ── the type chip on the box ──────────────────────────────────────────────

TYPECHIP_JS = """([distroId, n]) => {
    const el = document.querySelector(
        `[data-lrd-field="distro-box-type-${distroId}-${n}"]`);
    if (!el) return null;
    const head = el.closest('[data-hwdock]');
    const sec = el.closest('.hw-dock-multi');
    const chips = sec ? Array.from(sec.querySelectorAll(
        `[data-hwdock^="tail-${distroId}-${n}-"]`)).length : 0;
    const strip = Array.from(document.querySelectorAll(
        '#hardware-dock .hw-dock-issue-msg')).map(e => e.textContent);
    return {
        tag: el.tagName, text: el.textContent, title: el.title,
        ro: el.classList.contains('hw-dock-typechip-ro'),
        clash: el.classList.contains('hw-dock-typechip-clash'),
        boxClash: !!(sec && sec.classList.contains('hw-dock-multi-clash')),
        handle: head && head.dataset.hwdock,
        payload: head ? JSON.parse(head.dataset.hwdockPayload) : null,
        chips,
        stripTyped: strip.filter(t => t.includes('is typed')),
    };
}"""

BOX_TYPES_JS = """(id) => {
    const d = window.app.getDistros().find(x => x.id === id);
    return d.boxTypes === undefined ? null : d.boxTypes;
}"""


def test_the_spare_box_wears_the_first_offered_type_and_a_click_cycles_it(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    # a legacy distro offers everything: the spare box reads Soca 208, the
    # catalog's first, stored nowhere yet
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip and chip['tag'] == 'BUTTON' and not chip['ro'], chip
    assert chip['text'] == 'Soca 208' and chip['chips'] == 6, chip
    assert chip['payload']['output'] == 'soca208', chip
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    before = pg.evaluate(HIST_LEN_JS)
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip['text'] == 'Soca 120' and chip['chips'] == 6, chip
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca120'}
    assert pg.evaluate(HIST_LEN_JS) == before + 1
    assert pg.evaluate(HIST_JS, 1) == ['Set Multi Type']
    # the pick rides the drag payload, so the box drags as that plug
    assert chip['payload']['output'] == 'soca120', chip
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    # an L21-30 box is a three-circuit box before anything lands on it
    assert chip['text'] == 'L21-30' and chip['chips'] == 3, chip
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'l2130'}
    # wraps
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Soca 208'
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca208'}
    # undo walks one pick back
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'l2130'}
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip['text'] == 'L21-30' and chip['chips'] == 3, chip
    # the stored type survives a project round-trip (no server allow-list)
    served = pg.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        return p.distros.find(x => x.id === id).boxTypes;
    }""", d)
    assert served == {'1': 'l2130'}, served
    # the cycle is the distro's OWN list: offering only two, the spare box
    # reads the first offered and the click skips the unticked one
    pg.evaluate("""(id) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === id);
        delete dd.boxTypes;
        app.updateDistro(id, {outputs: ['soca120', 'l2130']});
        app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Soca 120'
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'L21-30'
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Soca 120'
    # nothing offered: the default is Soca 208
    pg.evaluate("""(id) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === id);
        delete dd.boxTypes;
        app.updateDistro(id, {outputs: []});
        app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Soca 208'
    pg.evaluate(RESET_JS, ids)


def test_a_spare_box_follows_the_distro_s_other_boxes(page):
    """Rung 3: a box with nothing on it and no stored type reads the type of
    the nearest lower-numbered settled box (else the nearest higher), so a
    spare on an Edison distro is Edison without a click. Only boxes that
    settle by a stored type or by members count - a memberless untyped box
    is not asked, or it would ask the same question back."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === id);
        const read = (n) => { const r = app.distroBoxType(dd, n); return [r.type.id, r.source]; };
        dd.boxTypes = { 1: 'soca120' };
        const a = read(2);
        dd.boxTypes = { 1: 'l2130', 3: 'soca120' };
        const b = [read(2), read(4), read(5)];
        dd.boxTypes = { 4: 'soca120' };
        const c = read(1);
        delete dd.boxTypes;
        const e = read(2);
        return { a, b, c, e };
    }""", d)
    assert out['a'] == ['soca120', 'neighbour'], out
    # nearest LOWER wins: box 2 follows box 1, boxes 4 and 5 follow box 3
    assert out['b'] == [['l2130', 'neighbour'], ['soca120', 'neighbour'],
                        ['soca120', 'neighbour']], out
    # nothing lower: the nearest higher
    assert out['c'] == ['soca120', 'neighbour'], out
    # no settled box anywhere: back to the offered list
    assert out['e'][1] in ('offered', 'default'), out
    pg.evaluate(RESET_JS, ids)


def test_an_occupied_box_chip_is_read_only_and_reads_its_members(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    # a plug drop makes box 1 and stamps its type
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['aId'], {})
    drag(pg, sx, sy, tgt['x'], tgt['y'])
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {'1': d}
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca208'}
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip['tag'] == 'SPAN' and chip['ro'], chip
    assert chip['text'] == 'Soca 208' and chip['chips'] == 6, chip
    assert 'Clear the breakout' in chip['title'], chip
    assert 'output' not in chip['payload'], chip
    assert not chip['clash'] and chip['stripTyped'] == [], chip
    # one undo forgets the stamp with the assignment
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca208'}
    # a LEGACY distro (no boxTypes) reads its occupied boxes off their
    # members: WALL B as an L21-30 box on number 2, WALL A's soca on 1
    pg.evaluate("""(ids) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === ids.distroId);
        delete dd.boxTypes;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerBreakoutType = 'l2130-true1';
        app.setSocaDistro(b, 1, ids.distroId, false);
        app.setSocaNumber(b, 1, 2, false);
        app.updateLayers([b]);
        app._restateNaming();
        app.renderHardwareDock();
    }""", ids)
    pg.wait_for_timeout(600)
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    one = pg.evaluate(TYPECHIP_JS, [d, 1])
    two = pg.evaluate(TYPECHIP_JS, [d, 2])
    assert one['text'] == 'Soca 208' and one['chips'] == 6, one
    assert two['text'] == 'L21-30' and two['chips'] == 3 and two['ro'], two
    assert not one['clash'] and not two['clash'], (one, two)
    assert two['stripTyped'] == [], two
    # a stored type at odds with the box's circuits is a clash: said on
    # the strip with the fix, the stored type still standing on the chip
    pg.evaluate("""(id) => {
        window.app.updateDistro(id, {boxTypes: {2: 'soca208'}});
        window.app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(500)
    two = pg.evaluate(TYPECHIP_JS, [d, 2])
    assert two['text'] == 'Soca 208' and two['clash'] and two['boxClash'], two
    assert two['stripTyped'] == ['PD 2 is typed Soca 208 but holds L21-30 '
                                 'circuits.'], two
    # the strip's fix retypes it to follow the circuits, one entry
    n = pg.evaluate(HIST_LEN_JS)
    pg.locator('#hardware-dock .hw-dock-issue button',
               has_text='Make it L21-30').click()
    pg.wait_for_timeout(500)
    assert pg.evaluate(BOX_TYPES_JS, d) == {'2': 'l2130'}
    assert pg.evaluate(HIST_LEN_JS) == n + 1
    assert pg.evaluate(HIST_JS, 1) == ['Set Multi Type']
    two = pg.evaluate(TYPECHIP_JS, [d, 2])
    assert two['text'] == 'L21-30' and not two['clash'], two
    assert two['stripTyped'] == [], two
    pg.evaluate(RESET_JS, ids)


def test_a_typed_spare_box_drags_as_its_plug(page):
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    d = ids['distroId']
    # type the spare box L21-30 by its chip (two clicks from Soca 208)
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(300)
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'L21-30'
    n = pg.evaluate(HIST_LEN_JS)
    # onto a soca screen: the plug's own refusal, nothing lit, nothing moved
    sx, sy = chip_center(pg, f'slot-{d}-1')
    tgt = panel_point(pg, ids['aId'], {'circuit': 0})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['ghost'], mid
    t = mid['target']
    assert t and t['kind'] == 'run' and t['nums'] == [], mid
    assert mid['lit'] == [], mid
    assert mid['pill'] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL A is set to Multi → True1 — change its breakout first', mid
    assert pg.evaluate(STATUS_JS) == \
        'WALL A is set to Multi → True1 — change its breakout first'
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    assert pg.evaluate(HIST_LEN_JS) == n, 'a refused drop earned an entry'
    # onto an L21-30 screen, dropped on its THIRD circuit: the anchored
    # take - circuits 1-3 - previewed and landed, the box pinned to 1
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setPowerBreakout(b, 'l2130-true1');
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'slot-{d}-1')
    tgt = panel_point(pg, ids['bId'], {'circuit': 2})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    t = mid['target']
    assert t['kind'] == 'run' and t['nums'] == [1, 2, 3], mid
    assert mid['lit'] == [1, 2, 3], mid
    assert t['plug']['ok'] and t['plug']['boxName'] == 'PD 1', mid
    assert t['plug']['badge'] == 'L21-30', mid
    assert mid['pill']['cls'] == '', mid
    assert mid['pill']['text'].startswith('PD 1 → circuits 1–3 · '), mid
    st = pg.evaluate(POWER_STATE_JS, ids['bId'])
    assert st['distro'] == {'1': d} and st['num'] == {'1': 1}, st
    assert pg.evaluate(HIST_LEN_JS) == n + 1
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'l2130'}
    one = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert one['ro'] and one['text'] == 'L21-30' and one['chips'] == 3, one
    pg.evaluate(RESET_JS, ids)
    # the stamp, proven where nothing was stored: a distro offering only
    # L21-30 types its spare box L21-30 by default, and the drop records it
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.updateDistro(ids.distroId, {outputs: ['l2130']});
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.setPowerBreakout(b, 'l2130-true1');
        app._restateNaming();
        app.renderHardwareDock();
    }""", ids)
    pg.wait_for_timeout(600)
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'L21-30'
    sx, sy = chip_center(pg, f'slot-{d}-1')
    tgt = panel_point(pg, ids['bId'], {'circuit': 0})
    drag(pg, sx, sy, tgt['x'], tgt['y'])
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'l2130'}
    # one undo takes the type away with the assignment
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    pg.evaluate(RESET_JS, ids)
    # a typed Soca 208 spare box on a soca screen's fourth circuit takes
    # 1-4 (the anchored span), and the next spare box appears typed
    pg.wait_for_timeout(400)
    sx, sy = chip_center(pg, f'slot-{d}-1')
    tgt = panel_point(pg, ids['aId'], {'circuit': 3})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['target']['nums'] == [1, 2, 3, 4], mid
    assert mid['lit'] == [1, 2, 3, 4], mid
    assert mid['pill']['text'].startswith('PD 1 → circuits 1–4 · '), mid
    st = pg.evaluate(POWER_STATE_JS, ids['aId'])
    first = next(s for s in st['plan'] if s['distroId'] == d)
    assert first['circuits'] == [1, 2, 3, 4] and first['number'] == 1, st
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca208'}
    two = pg.evaluate(TYPECHIP_JS, [d, 2])
    assert two and two['tag'] == 'BUTTON' and two['text'] == 'Soca 208', two
    pg.evaluate(RESET_JS, ids)
