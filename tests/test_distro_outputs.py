"""Distro outputs: the connector is the thing you drag.

A distro declares the connector TYPES it offers (types only, no counts) in
its ⚙ popover's OUTPUTS checklist - Multi 208 (True1 / powerCON, 208V
screens), Multi 120 (Edison / True1 / powerCON, 110V / 120V screens - the
ruling of 2026-09-22), L21-30 (3 × 208V). The tray shows one plug chip per ticked type
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
    L21-30 against a soca, a soca against L21-30 - or its voltage - a
    Multi 208 against a 120V screen, a Multi 120 against a 208V screen,
    whatever the breakout - and nothing mutates
  * the voltage is a CLASS, as a range: up to 120V is the Multi 120 class,
    above 120V the Multi 208 class, so 220 / 230 / 240 gate exactly as
    208 does; the L21-30 alone matches 208V and nothing else
  * a screen always carries an eligible breakout (2026-09-22, "they have
    to be set"): normalizePowerBreakout writes Edison up to 120V and
    True1 above on every load path and after a sidebar voltage change,
    never touching a stored eligible choice
  * a whole-distro drag runs the plug gate per multi and refuses all or
    nothing, with the single-output drag's sentence; its preview lights
    nothing where the drop would refuse, and a landing drop stamps every
    box's type inside the one entry
  * the breakout follows the voltage on every path: picking "Custom"
    commits nothing until a figure is typed (one entry per real change),
    a group peer handed a voltage is normalized on the same PUT, the
    multi-select breakout skips (and names) a screen whose voltage refuses
    the choice, a delete's re-fetch keeps the breakout in force, the boot
    pass writes its rewrite through to the server, and the guide's demo
    wall carries one
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
    assert pop['names'] == ['Multi 208', 'Multi 120', 'L21-30'], pop
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
    # a Multi 208 onto a 120V screen on its DEFAULT breakout (nothing
    # stored: Edison): the voltage mismatch, named as such - changing the
    # breakout would not help, so the refusal does not send you there
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
        'WALL B runs at 120V — a Multi 208 output feeds screens above 120V', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    # and the Multi 120 chip is what that screen takes
    sx, sy = chip_center(pg, f'plug-{d}-soca120')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] and mid['pill']['cls'] == '', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    pg.evaluate(RESET_JS, ids)


def test_a_true1_screen_is_matched_by_its_voltage(page):
    """True1 (and powerCON) breakouts exist at 208V and at 110V / 120V
    since 2026-09-22, so the voltage decides the multi: a 120V True1
    screen lands on a Multi 120 and a Multi 208 refuses it naming the
    voltage; a 208V True1 screen the reverse. Nothing mutates on a
    refusal."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 120;
        b.powerBreakoutType = 'soca-true1';
        app.updateLayers([b]);
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    d = ids['distroId']
    n = pg.evaluate(HIST_LEN_JS)
    # 120V True1 against a Multi 208: refused for the voltage
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    tgt = panel_point(pg, ids['bId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL B runs at 120V — a Multi 208 output feeds screens above 120V', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    assert pg.evaluate(HIST_LEN_JS) == n
    # 120V True1 on a Multi 120: lands
    sx, sy = chip_center(pg, f'plug-{d}-soca120')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [1, 2, 3] and mid['pill']['cls'] == '', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    # 208V True1 (WALL A, the default breakout) against a Multi 120:
    # refused for the voltage, the reverse sentence
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'plug-{d}-soca120')
    tgt = panel_point(pg, ids['aId'], {})
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL A runs at 208V — a Multi 120 output feeds screens up to 120V', mid
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    assert pg.evaluate(HIST_LEN_JS) == n
    # and the Multi 208 lands on it
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [1, 2, 3, 4, 5, 6] and mid['pill']['cls'] == '', mid
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {'1': d}
    pg.evaluate(RESET_JS, ids)


def test_a_box_of_120v_true1_screens_implies_multi_120(page):
    """Rung 2 reads the voltage with the breakout: a box whose members are
    120V True1 screens implies Multi 120 (a legacy distro without boxTypes
    reads it so), the same screens at 208V imply Multi 208, and a box
    STORED as Multi 208 over 120V True1 members stands but clashes."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === ids.distroId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 120;
        b.powerBreakoutType = 'soca-true1';
        app.updateLayers([b]);
        // multi indices are 1-based: WALL B's three circuits are multi 1
        app.setSocaDistro(b, 1, dd.id, false);
        app.updateLayers([b]);
        app._restateNaming();
        delete dd.boxTypes;
        const n = [...app._distroMultiNumbers(dd.id).keys()][0];
        if (n === undefined) return { at120: 'no box on the distro' };
        const read = () => { const r = app.distroBoxType(dd, n);
            return [r.type.id, r.source, r.clash]; };
        const at120 = read();
        dd.boxTypes = { [n]: 'soca208' };
        const stored = read();
        delete dd.boxTypes;
        b.powerVoltage = 208;
        app.updateLayers([b]);
        app._restateNaming();
        const at208 = read();
        return { at120, stored, at208 };
    }""", ids)
    assert out['at120'] == ['soca120', 'members', False], out
    assert out['stored'] == ['soca208', 'stored', True], out
    assert out['at208'] == ['soca208', 'members', False], out
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
        assert m['label'] == 'Add Multi 208 from…', m
        assert [(e['label'], e['disabled']) for e in m['entries']] == [
            ('PD 0/400 A', False),
            ('SR — does not offer Multi 208', True)], m
        assert 'Tick Multi 208 under SR' in m['entries'][1]['title'], m
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
        assert m['label'] == 'Add Multi 208 from…', m
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
    assert on_screen.count('MULTI 208') == 2, on_screen   # one per multi
    assert any(t.startswith('PD1 · ') and '100ft' not in t
               for t in on_screen), on_screen
    exported = pg.evaluate(BRACKET_TEXTS_JS, [ids['aId'], True])
    assert exported.count('MULTI 208') == 2, exported
    assert any(t.startswith('PD1 · 100ft · ') for t in exported), exported
    assert 'L21-30' in pg.evaluate(BRACKET_TEXTS_JS, [ids['bId'], True])
    # Edison screen: MULTI 120 off the default breakout
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerBreakoutType = null;
        b.powerVoltage = 120;
        app.updateLayers([b]);
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(400)
    assert 'MULTI 120' in pg.evaluate(BRACKET_TEXTS_JS, [ids['bId'], False])
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
    assert texts == ['MULTI 208', 'PD1 · 46.2A'], texts
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


# ── the voltage class is a range ──────────────────────────────────────────

def test_a_230v_screen_gates_as_the_208_class(page):
    """220 / 230 / 240 are stock voltage options and behave exactly as 208
    does for gating: a Multi 208 lands on a 230V True1 screen and the box
    reads Multi 208 with no clash, a Multi 120 is refused naming the
    screen's voltage, and the L21-30 - documented at 208V only - is
    refused by voltage too, with the exact figure it feeds. The refusal
    wording says "screens above 120V" / "screens up to 120V", never a
    list of voltages the class does not stop at."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 230;
        b.powerBreakoutType = 'soca-true1';
        app.updateLayers([b]);
        app._restateNaming();
    }""", ids)
    pg.wait_for_timeout(600)
    d = ids['distroId']
    n = pg.evaluate(HIST_LEN_JS)
    tgt = panel_point(pg, ids['bId'], {})
    # Multi 120 against 230V: refused for the voltage, class wording
    sx, sy = chip_center(pg, f'plug-{d}-soca120')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL B runs at 230V — a Multi 120 output feeds screens up to 120V', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    # L21-30 against 230V: refused for the voltage, the exact figure
    sx, sy = chip_center(pg, f'plug-{d}-l2130')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [] and mid['pill']['cls'] == 'hw-dock-pill-bad', mid
    assert mid['pill']['text'] == \
        'WALL B runs at 230V — an L21-30 output feeds 208V screens', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {}
    assert pg.evaluate(HIST_LEN_JS) == n
    # Multi 208 lands, and the box it makes reads Multi 208 without a clash
    sx, sy = chip_center(pg, f'plug-{d}-soca208')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['bId']))
    assert mid['lit'] == [1, 2, 3] and mid['pill']['cls'] == '', mid
    assert pg.evaluate(POWER_STATE_JS, ids['bId'])['distro'] == {'1': d}
    box = pg.evaluate("""(ids) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === ids.distroId);
        const n = [...app._distroMultiNumbers(dd.id).keys()][0];
        const r = app.distroBoxType(dd, n);
        delete dd.boxTypes;
        const implied = app.distroBoxType(dd, n);
        return { stored: [r.type.id, r.source, r.clash],
                 implied: [implied.type.id, implied.source, implied.clash],
                 cls: [app._voltageClass(230), app._voltageClass(240),
                       app._voltageClass(208), app._voltageClass(120),
                       app._voltageClass(110), app._voltageClass(''),
                       app._voltageClass(null)] };
    }""", ids)
    assert box['stored'] == ['soca208', 'stored', False], box
    assert box['implied'] == ['soca208', 'members', False], box
    assert box['cls'] == [208, 208, 208, 120, 120, None, None], box
    pg.evaluate(RESET_JS, ids)


# ── a screen always carries an eligible breakout ──────────────────────────

# The breakout preference, set the way the dialog's Save stores it (the
# live copy and the server), so the client's normalize and the server's
# read the same rung. Returns what it was. null puts the key back to
# unset (the shipped default, True1).
SET_BREAKOUT_PREF_JS = """async (bt) => {
    const app = window.app;
    const prefs = { ...app.getPreferences() };
    const before = prefs.breakoutType;
    if (bt === null) delete prefs.breakoutType; else prefs.breakoutType = bt;
    app._serverPreferences = prefs;
    await fetch('/api/preferences', { method: 'PUT',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(prefs) });
    return before;
}"""


def test_a_screen_is_written_an_eligible_breakout_on_load(page):
    """normalizePowerBreakout (user ruling, 2026-09-22: "screens need to be
    set to true1 or powercon or edison. they have to be set"; and the
    default "should be set in preferences"): a missing, empty, unknown or
    ineligible stored breakout is rewritten - the Preferences breakout
    when the voltage allows it, else Edison for 0 < V <= 120 and True1
    otherwise - and a stored ELIGIBLE choice is left alone (L21-30 at
    208V, L6-20 at 230V). Both load paths call it - the File > Open
    defaults pass and the startup client-props pass - and a 208V screen
    that somehow holds Edison reads the same answer on every surface
    until the write lands."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    saved_pref = pg.evaluate(SET_BREAKOUT_PREF_JS, 'l2130-true1')
    try:
        out = pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const saved = { v: b.powerVoltage, bt: b.powerBreakoutType };
            const run = (v, bt) => {
                b.powerVoltage = v; b.powerBreakoutType = bt;
                const wrote = app.normalizePowerBreakout(b);
                return [b.powerBreakoutType, wrote];
            };
            // the preference is L21-30: eligible at 208V only, so the
            // class default shows everywhere else
            const r = {
                missing208: run(208, undefined),
                empty120: run(120, ''),
                unknown110: run(110, 'no-such-breakout'),
                edisonAt208: run(208, 'soca-edison'),
                edisonAt230: run(230, 'soca-edison'),
                l2130At120: run(120, 'l2130-true1'),
                l620At120: run(120, 'soca-l620'),
                l2130At230: run(230, 'l2130-powercon'),
                blankMissing: run('', null),
                // stored eligible choices stand as written
                l2130At208: run(208, 'l2130-true1'),
                l620At230: run(230, 'soca-l620'),
                powerconAt120: run(120, 'soca-powercon'),
                edisonAt110: run(110, 'soca-edison'),
                edisonAtBlank: run('', 'soca-edison'),
            };
            b.powerVoltage = saved.v; b.powerBreakoutType = saved.bt;
            return r;
        }""", ids)
        assert out['missing208'] == ['l2130-true1', True], out
        assert out['empty120'] == ['soca-edison', True], out
        assert out['unknown110'] == ['soca-edison', True], out
        assert out['edisonAt208'] == ['l2130-true1', True], out
        assert out['edisonAt230'] == ['soca-true1', True], out
        assert out['l2130At120'] == ['soca-edison', True], out
        assert out['l620At120'] == ['soca-edison', True], out
        assert out['l2130At230'] == ['soca-true1', True], out
        assert out['blankMissing'] == ['soca-true1', True], out
        assert out['l2130At208'] == ['l2130-true1', False], out
        assert out['l620At230'] == ['soca-l620', False], out
        assert out['powerconAt120'] == ['soca-powercon', False], out
        assert out['edisonAt110'] == ['soca-edison', False], out
        assert out['edisonAtBlank'] == ['soca-edison', False], out
        # a preference every voltage allows is written everywhere a
        # screen needs one - and never over an eligible choice
        pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-powercon')
        out = pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const saved = { v: b.powerVoltage, bt: b.powerBreakoutType };
            const run = (v, bt) => {
                b.powerVoltage = v; b.powerBreakoutType = bt;
                const wrote = app.normalizePowerBreakout(b);
                return [b.powerBreakoutType, wrote];
            };
            const r = {
                missing208: run(208, undefined),
                empty120: run(120, ''),
                edisonAt208: run(208, 'soca-edison'),
                l2130At120: run(120, 'l2130-true1'),
                blankMissing: run('', null),
                edisonAt110: run(110, 'soca-edison'),
                l2130At208: run(208, 'l2130-true1'),
            };
            b.powerVoltage = saved.v; b.powerBreakoutType = saved.bt;
            return r;
        }""", ids)
        assert out['missing208'] == ['soca-powercon', True], out
        assert out['empty120'] == ['soca-powercon', True], out
        assert out['edisonAt208'] == ['soca-powercon', True], out
        assert out['l2130At120'] == ['soca-powercon', True], out
        assert out['blankMissing'] == ['soca-powercon', True], out
        assert out['edisonAt110'] == ['soca-edison', False], out
        assert out['l2130At208'] == ['l2130-true1', False], out
        # the read side agrees before the write, and both load paths
        # write it: with an Edison preference a 208V screen holding
        # Edison reads True1 (the class default) everywhere
        pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-edison')
        out = pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const saved = { v: b.powerVoltage, bt: b.powerBreakoutType };
            const r = {};
            b.powerVoltage = 208; b.powerBreakoutType = 'soca-edison';
            r.readsTrue1 = [
                app.getPowerBreakout(b).id,
                app.outputTypeForBreakout(app.getPowerBreakout(b), b.powerVoltage).id,
                app.cableConnectorName(app.boxTailConnector(null, null, b)),
            ];
            // the File > Open pass writes it
            b.powerVoltage = 208; b.powerBreakoutType = 'soca-edison';
            app.applyMissingLayerDefaults(b);
            r.fileOpen = b.powerBreakoutType;
            // the startup client-props pass writes it (the preference)
            b.powerVoltage = 120; b.powerBreakoutType = 'l2130-true1';
            app.loadClientSideProperties({ skipPreferences: true });
            r.startup = b.powerBreakoutType;
            b.powerVoltage = saved.v; b.powerBreakoutType = saved.bt;
            return r;
        }""", ids)
        assert out['readsTrue1'] == ['soca-true1', 'soca208', 'True1'], out
        assert out['fileOpen'] == 'soca-true1', out
        assert out['startup'] == 'soca-edison', out
    finally:
        pg.evaluate(SET_BREAKOUT_PREF_JS, saved_pref if saved_pref else None)
        pg.evaluate(RESET_JS, ids)


def test_set_screen_voltage_is_the_one_voltage_write(page):
    """setScreenVoltage writes the figure, keeps powerVoltageCustom in step
    for a figure that is not a stock option, and normalizes the breakout
    in the same step - the helper every voltage write path goes through
    (tests/test_breakout_invariant.py reads the source for the rest)."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    saved_pref = pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-edison')
    try:
        out = pg.evaluate("""(ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const saved = { v: b.powerVoltage, c: b.powerVoltageCustom, bt: b.powerBreakoutType };
            const r = {};
            b.powerVoltageCustom = 999; b.powerBreakoutType = 'l2130-true1'; b.powerVoltage = 208;
            r.custom100 = [app.setScreenVoltage(b, 100), b.powerVoltage, b.powerVoltageCustom, b.powerBreakoutType];
            r.stock208 = [app.setScreenVoltage(b, 208), b.powerVoltage, b.powerVoltageCustom, b.powerBreakoutType];
            b.powerBreakoutType = 'soca-powercon';
            r.keeps = [app.setScreenVoltage(b, 230), b.powerVoltage, b.powerVoltageCustom, b.powerBreakoutType];
            b.powerVoltage = saved.v; b.powerVoltageCustom = saved.c; b.powerBreakoutType = saved.bt;
            return r;
        }""", ids)
        # 100 V is not stock: the cache follows, and L21-30 is rewritten
        # to the preference (Edison runs at 100 V)
        assert out['custom100'] == [True, 100, 100, 'soca-edison'], out
        # 208 V is stock: the cache stays where the custom figure left
        # it; Edison is out above 120 V -> True1 (the class default)
        assert out['stock208'] == [True, 208, 100, 'soca-true1'], out
        # an eligible choice rides through a voltage change
        assert out['keeps'] == [False, 230, 100, 'soca-powercon'], out
    finally:
        pg.evaluate(SET_BREAKOUT_PREF_JS, saved_pref if saved_pref else None)
        pg.evaluate(RESET_JS, ids)


def test_the_custom_voltage_box_takes_whole_volts_only(page):
    """The sidebar's custom box commits whole volts, 1 or more. A blank,
    0, a negative figure, a fraction (0.5, 1e-9) or text commits nothing
    and the box is re-seeded with the voltage in force; 100 commits, with
    its breakout following, and the box shows the figure the screen runs
    at."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        app.selectLayer(b);
    }""", ids)
    pg.wait_for_timeout(300)
    _fire(pg, 'power-voltage-select', 'custom')
    pg.wait_for_timeout(200)

    def typed(value):
        n = pg.evaluate(HIST_LEN_JS)
        pg.evaluate("""(v) => {
            const box = document.getElementById('power-voltage-custom');
            box.value = v;
            box.dispatchEvent(new Event('change', { bubbles: true }));
        }""", value)
        pg.wait_for_timeout(400)
        return pg.evaluate("""([ids, n]) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const box = document.getElementById('power-voltage-custom');
            return { v: b.powerVoltage, bt: b.powerBreakoutType, box: box.value,
                     entries: app.history.length - n };
        }""", [ids, n])

    for bad in ['', '0', '-5', '0.5', '1e-9', 'abc', '120.5']:
        out = typed(bad)
        assert out['v'] == 208 and out['bt'] == 'soca-true1', (bad, out)
        assert out['box'] == '208', (bad, out)
        assert out['entries'] == 0, (bad, out)
    out = typed('100')
    assert out['v'] == 100 and out['box'] == '100', out
    assert out['bt'] in ('soca-true1', 'soca-powercon', 'soca-edison'), out
    assert out['entries'] == 1, out
    served = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert served['served'][0] == 100, served
    # the box shows the screen's voltage after a reload of the sidebar,
    # not the cache: a group dialog can hand a screen a custom figure
    # without touching powerVoltageCustom
    shown = pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltageCustom = 777;
        app.loadLayerToInputs();
        const sel = document.getElementById('power-voltage-select');
        const box = document.getElementById('power-voltage-custom');
        return [sel.value, box.value, box.style.display];
    }""", ids)
    assert shown == ['custom', '100', 'inline-block'], shown
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
    }""", ids)
    pg.evaluate(RESET_JS, ids)


def test_the_group_dialog_s_voltage_reaches_the_sidebar_box(page):
    """_applyGroupSettings hands every member the chosen voltage through
    setScreenVoltage: a custom figure lands with its cache in step and an
    eligible breakout, and the sidebar's custom box shows it."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const b = app.project.layers.find(x => x.id === ids.bId);
        const saved = [a, b].map(l => ({ v: l.powerVoltage, c: l.powerVoltageCustom, bt: l.powerBreakoutType }));
        b.powerBreakoutType = 'l2130-true1';
        app._applyGroupSettings([a, b], { powerVoltage: 100 });
        app.selectLayer(a);
        app.loadLayerToInputs();
        const sel = document.getElementById('power-voltage-select');
        const box = document.getElementById('power-voltage-custom');
        const r = { a: [a.powerVoltage, a.powerVoltageCustom, a.powerBreakoutType],
                    b: [b.powerVoltage, b.powerVoltageCustom, b.powerBreakoutType],
                    sidebar: [sel.value, box.value] };
        [a, b].forEach((l, i) => { l.powerVoltage = saved[i].v; l.powerVoltageCustom = saved[i].c;
                                   l.powerBreakoutType = saved[i].bt; });
        app.loadLayerToInputs();
        return r;
    }""", ids)
    assert out['a'][:2] == [100, 100] and out['a'][2] in ('soca-true1', 'soca-powercon', 'soca-edison'), out
    assert out['b'][:2] == [100, 100] and out['b'][2] in ('soca-true1', 'soca-powercon', 'soca-edison'), out
    assert out['sidebar'] == ['custom', '100'], out
    pg.evaluate(RESET_JS, ids)


def test_a_sidebar_voltage_change_rewrites_an_ineligible_breakout(page):
    """The sidebar's voltage select: 208 -> 110 on a screen stored L21-30
    rewrites the breakout to Edison in the same 'Change Power Voltage'
    step, and the server is sent the rewrite on that PUT; 110 -> 208 on
    the Edison screen rewrites to True1. A stored eligible choice rides
    through untouched (powerCON at 120V stays powerCON at 208V). The
    preference is Edison for the test, so the write-in at 110V is the
    preference and at 208V the class default."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    saved_pref = pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-edison')
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 208;
        b.powerBreakoutType = 'l2130-true1';
        app.updateLayers([b]);
        app.selectLayer(b);
    }""", ids)
    pg.wait_for_timeout(500)
    served = pg.evaluate("""async (ids) => {
        const p = await (await fetch('/api/project')).json();
        return p.layers.find(l => l.id === ids.bId).powerBreakoutType;
    }""", ids)
    assert served == 'l2130-true1', served

    def change(value):
        pg.evaluate("""(v) => {
            const sel = document.getElementById('power-voltage-select');
            sel.value = v;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }""", value)
        pg.wait_for_timeout(700)
        return pg.evaluate("""async (ids) => {
            const app = window.app;
            const b = app.project.layers.find(x => x.id === ids.bId);
            const p = await (await fetch('/api/project')).json();
            const s = p.layers.find(l => l.id === ids.bId);
            return { local: [b.powerVoltage, b.powerBreakoutType],
                     served: [s.powerVoltage, s.powerBreakoutType],
                     last: app.history[app.historyIndex].action,
                     select: document.getElementById('power-breakout-type').value };
        }""", ids)

    out = change('110')
    assert out['local'] == [110, 'soca-edison'], out
    assert out['served'] == [110, 'soca-edison'], out
    assert out['last'] == 'Change Power Voltage', out
    assert out['select'] == 'soca-edison', out
    out = change('208')
    assert out['local'] == [208, 'soca-true1'], out
    assert out['served'] == [208, 'soca-true1'], out
    # an eligible choice rides through
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 120;
        b.powerBreakoutType = 'soca-powercon';
        app.updateLayers([b]);
    }""", ids)
    pg.wait_for_timeout(400)
    out = change('208')
    assert out['local'] == [208, 'soca-powercon'], out
    assert out['served'] == [208, 'soca-powercon'], out
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
    }""", ids)
    pg.evaluate(SET_BREAKOUT_PREF_JS, saved_pref if saved_pref else None)
    pg.evaluate(RESET_JS, ids)


# ── the whole-distro drag passes the plug gate ────────────────────────────

def test_a_whole_distro_drag_passes_the_plug_gate(page):
    """Dragging the distro's own handle onto a screen runs the plug gate
    for the type each unassigned multi would land as, all or nothing: a
    distro whose OUTPUTS list leaves that type out refuses on the strip
    with nothing assigned and no history entry; a screen whose breakout
    no output type names (L6-20) is refused naming the breakout, as its
    chip drops are; and the legacy distro (no list) still lands both
    multis of a 208V True1 screen."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    d = ids['distroId']
    # the distro offers only Multi 120; WALL A is 208V True1 -> Multi 208
    pg.evaluate("(id) => window.app.updateDistro(id, {outputs: ['soca120']})", d)
    pg.wait_for_timeout(500)
    pg.evaluate("() => window.app.resetHistory('Outputs Seed')")
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'distro-{d}')
    tgt = panel_point(pg, ids['aId'], {})
    # the handle's preview runs the same gate: nothing lights where the
    # drop would refuse (the chip path's rule), and the dock's resolved
    # target carries no circuits
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    assert mid['lit'] == [], mid
    assert mid['target'] and mid['target']['nums'] == [], mid
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}, \
        'a refused whole-distro drop assigned a multi'
    assert pg.evaluate(STATUS_JS) == \
        'PD does not offer Multi 208 — tick Multi 208 under its ⚙ Outputs first'
    assert pg.evaluate(HIST_LEN_JS) == n, 'a refused drop earned an entry'
    # an L6-20 screen: no output type names the breakout
    pg.evaluate(RESET_JS, ids)
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        a.powerBreakoutType = 'soca-l620';
        app.updateLayers([a]);
        app._restateNaming();
        const dd = app.getDistros().find(x => x.id === ids.distroId);
        const s = app.getSocaPlan(a)[0];
        return {
            refusal: app._distroDropRefusal({ distroId: dd.id }, a, s),
            expect: `WALL A is set to ${app._breakoutShortName(
                app.getPowerBreakout(a))} — change its breakout first`,
        };
    }""", ids)
    assert out['refusal'] == out['expect'], out
    pg.wait_for_timeout(300)
    n = pg.evaluate(HIST_LEN_JS)
    sx, sy = chip_center(pg, f'distro-{d}')
    drag(pg, sx, sy, tgt['x'], tgt['y'])
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    assert pg.evaluate(STATUS_JS) == out['expect']
    assert pg.evaluate(HIST_LEN_JS) == n
    # the gate says yes for the legacy distro and a 208V True1 screen, and
    # the drop lands both multis
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(300)
    assert pg.evaluate("""(ids) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === ids.aId);
        const dd = app.getDistros().find(x => x.id === ids.distroId);
        return app.getSocaPlan(a).map(
            s => app._distroDropRefusal({ distroId: dd.id }, a, s));
    }""", ids) == [None, None]
    # count the project saves the drop makes: the two stamps persist ONCE
    pg.evaluate("""() => {
        const orig = window.fetch;
        window.__projectPosts = 0;
        window.__origFetch = orig;
        window.fetch = function (url, opts) {
            if (String(url).endsWith('/api/project') && opts && opts.method === 'POST') {
                window.__projectPosts += 1;
            }
            return orig.apply(this, arguments);
        };
    }""")
    sx, sy = chip_center(pg, f'distro-{d}')
    mid = drag(pg, sx, sy, tgt['x'], tgt['y'],
               mid_check=lambda p: p.evaluate(MID_JS, ids['aId']))
    pg.wait_for_timeout(300)
    posts = pg.evaluate("""() => {
        const n = window.__projectPosts;
        window.fetch = window.__origFetch;
        return n;
    }""")
    assert mid['lit'] == list(range(1, 13)), mid
    st = pg.evaluate(POWER_STATE_JS, ids['aId'])
    assert st['distro'] == {'1': d, '2': d}, st
    assert posts == 1, f'the whole-distro drop persisted {posts} times (stamp all, persist once)'
    assert pg.evaluate(HIST_JS, 1) == ['Assign Multi Distro']
    # both boxes wear the type they landed as, stamped the way a chip
    # drop stamps its one box - inside the same entry, so one undo
    # forgets the stamps with the assignments
    assert pg.evaluate(BOX_TYPES_JS, d) == {'1': 'soca208', '2': 'soca208'}
    pg.evaluate("() => window.app.handleMenuAction('undo')")
    pg.wait_for_timeout(900)
    assert pg.evaluate(POWER_STATE_JS, ids['aId'])['distro'] == {}
    assert not (pg.evaluate(BOX_TYPES_JS, d) or {}), \
        'undo left the whole-distro drop\'s box types behind'
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
    # a legacy distro offers everything: the spare box reads Multi 208, the
    # catalog's first, stored nowhere yet
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip and chip['tag'] == 'BUTTON' and not chip['ro'], chip
    assert chip['text'] == 'Multi 208' and chip['chips'] == 6, chip
    assert chip['payload']['output'] == 'soca208', chip
    assert pg.evaluate(BOX_TYPES_JS, d) is None
    before = pg.evaluate(HIST_LEN_JS)
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    chip = pg.evaluate(TYPECHIP_JS, [d, 1])
    assert chip['text'] == 'Multi 120' and chip['chips'] == 6, chip
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
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Multi 208'
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
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Multi 120'
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'L21-30'
    pg.locator(f'[data-lrd-field="distro-box-type-{d}-1"]').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Multi 120'
    # nothing offered: the default is Multi 208
    pg.evaluate("""(id) => {
        const app = window.app;
        const dd = app.getDistros().find(x => x.id === id);
        delete dd.boxTypes;
        app.updateDistro(id, {outputs: []});
        app.renderHardwareDock();
    }""", d)
    pg.wait_for_timeout(400)
    assert pg.evaluate(TYPECHIP_JS, [d, 1])['text'] == 'Multi 208'
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
    assert chip['text'] == 'Multi 208' and chip['chips'] == 6, chip
    assert 'is a Multi 208 - ' in chip['title'] and 'Clear its circuits' in chip['title'], chip
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
    assert one['text'] == 'Multi 208' and one['chips'] == 6, one
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
    assert two['text'] == 'Multi 208' and two['clash'] and two['boxClash'], two
    assert two['stripTyped'] == ['PD 2 is typed Multi 208 but holds L21-30 '
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
    # type the spare box L21-30 by its chip (two clicks from Multi 208)
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
    # a typed Multi 208 spare box on a soca screen's fourth circuit takes
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
    assert two and two['tag'] == 'BUTTON' and two['text'] == 'Multi 208', two
    pg.evaluate(RESET_JS, ids)


# ── the breakout follows the voltage on every path ────────────────────────

VOLT_STATE_JS = """async (id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    const p = await (await fetch('/api/project')).json();
    const s = p.layers.find(x => x.id === id);
    const box = document.getElementById('power-voltage-custom');
    return { local: [l.powerVoltage, l.powerBreakoutType],
             served: [s.powerVoltage, s.powerBreakoutType],
             n: app.history.length,
             last: app.history[app.historyIndex].action,
             select: document.getElementById('power-voltage-select').value,
             box: box.value, boxShown: box.style.display !== 'none' };
}"""


def _fire(page, el_id, value):
    page.evaluate("""([id, v]) => {
        const el = document.getElementById(id);
        el.value = v;
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [el_id, value])
    page.wait_for_timeout(600)


def test_picking_custom_voltage_commits_nothing_until_a_figure_is_typed(page):
    """Picking "Custom" in the sidebar's voltage select used to commit the
    box's stock 110 at once, so a 208V L21-30 screen was written 110V +
    Edison before a figure was typed - and typing 208 back then left it
    True1. The pick now seeds the box with the screen's current voltage
    and commits nothing; a typed figure equal to what the screen holds
    is a no-op; a real figure is one 'Change Power Voltage' entry that
    rewrites an ineligible breakout in the same step; an emptied box
    commits nothing."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 208;
        b.powerBreakoutType = 'l2130-true1';
        app.updateLayers([b]);
        app.selectLayer(b);
    }""", ids)
    pg.wait_for_timeout(600)
    base = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert base['local'] == [208, 'l2130-true1'], base
    assert base['served'] == [208, 'l2130-true1'], base
    n = base['n']
    # the pick: box seeded with 208, shown, nothing committed
    _fire(pg, 'power-voltage-select', 'custom')
    out = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert out['local'] == [208, 'l2130-true1'], out
    assert out['served'] == [208, 'l2130-true1'], out
    assert out['n'] == n, out
    assert out['select'] == 'custom' and out['boxShown'], out
    assert out['box'] == '208', out
    # the seed typed back is a no-op
    _fire(pg, 'power-voltage-custom', '208')
    out = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert out['local'] == [208, 'l2130-true1'], out
    assert out['n'] == n, out
    # a real figure: one entry, and the 208V-only L21-30 becomes True1
    _fire(pg, 'power-voltage-custom', '230')
    out = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert out['local'] == [230, 'soca-true1'], out
    assert out['served'] == [230, 'soca-true1'], out
    assert out['n'] == n + 1 and out['last'] == 'Change Power Voltage', out
    # an emptied box is not a 0V screen
    _fire(pg, 'power-voltage-custom', '')
    out = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert out['local'] == [230, 'soca-true1'], out
    assert out['n'] == n + 1, out
    assert out['box'] == '230', out
    # a preset equal to what the screen holds commits nothing either
    _fire(pg, 'power-voltage-select', '230')
    out = pg.evaluate(VOLT_STATE_JS, ids['bId'])
    assert out['n'] == n + 1, out
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
    }""", ids)
    pg.evaluate(RESET_JS, ids)


def test_a_group_peer_handed_a_voltage_carries_an_eligible_breakout(page):
    """A screen group shares its voltage: the edited member's handler
    normalizes its own breakout, and the copy to the peers now runs the
    same normalize, so a peer holding L21-30 at 208V is written Edison
    when the wall goes to 110V - on the SAME PUT and in the same entry.
    The breakout itself is not shared: an eligible choice on the peer
    stands, and the edited member's choice is not copied across. The
    preference is Edison for the test: the write-in at 110V is the
    preference, at 208V the class default (True1)."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    saved_pref = pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-edison')
    gid = pg.evaluate("""async (ids) => {
        const app = window.app;
        app.setSelectedLayersByIds([ids.aId, ids.bId], ids.aId);
        const gid = await app.groupSelectedLayers();
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerBreakoutType = 'l2130-true1';
        app.updateLayers([b]);
        app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
        return gid;
    }""", ids)
    pg.wait_for_timeout(800)
    assert gid, 'no group was made'
    try:
        # the propagation itself, on the model
        direct = pg.evaluate("""(ids) => {
            const app = window.app;
            const a = app.project.layers.find(x => x.id === ids.aId);
            const b = app.project.layers.find(x => x.id === ids.bId);
            const snap = app._snapshotSharedFields([a]);
            a.powerVoltage = 110;
            app.normalizePowerBreakout(a);
            const peers = app._propagateChangedSharedFields([a], snap);
            const out = { peers: peers.map(p => p.id),
                          a: [a.powerVoltage, a.powerBreakoutType],
                          b: [b.powerVoltage, b.powerBreakoutType] };
            // put back without a PUT: the sidebar path below is the real one
            a.powerVoltage = 208; a.powerBreakoutType = 'soca-true1';
            b.powerVoltage = 208; b.powerBreakoutType = 'l2130-true1';
            app._pendingGroupPeerIds = null;
            return out;
        }""", ids)
        assert direct['peers'] == [ids['bId']], direct
        # the member holds True1 (the server wrote it for the reset's
        # null, and it is eligible at 110V) so it stands; the peer's
        # L21-30 is rewritten to the preference
        assert direct['a'] == [110, 'soca-true1'], direct
        assert direct['b'] == [110, 'soca-edison'], direct
        # the sidebar's select on the current member alone: both members
        # land at 110V on the server in one entry - the member keeps its
        # True1 (eligible at 110V), the peer's L21-30 is rewritten Edison
        n = pg.evaluate(HIST_LEN_JS)
        _fire(pg, 'power-voltage-select', '110')
        pg.wait_for_timeout(300)
        a = pg.evaluate(VOLT_STATE_JS, ids['aId'])
        b = pg.evaluate(VOLT_STATE_JS, ids['bId'])
        assert a['local'] == [110, 'soca-true1'] and a['served'] == [110, 'soca-true1'], a
        assert b['local'] == [110, 'soca-edison'] and b['served'] == [110, 'soca-edison'], b
        assert a['n'] == n + 1 and a['last'] == 'Change Power Voltage', a
        # back to 208: Edison is out above 120V on the peer too
        _fire(pg, 'power-voltage-select', '208')
        pg.wait_for_timeout(300)
        b = pg.evaluate(VOLT_STATE_JS, ids['bId'])
        assert b['local'] == [208, 'soca-true1'] and b['served'] == [208, 'soca-true1'], b
        # the breakout is per screen: the member's own pick stays its own
        _fire(pg, 'power-breakout-type', 'soca-powercon')
        a = pg.evaluate(VOLT_STATE_JS, ids['aId'])
        b = pg.evaluate(VOLT_STATE_JS, ids['bId'])
        assert a['local'][1] == 'soca-powercon', a
        assert b['local'][1] == 'soca-true1', b
    finally:
        pg.evaluate("""async ([ids, gid]) => {
            const app = window.app;
            await app.ungroupSelectedLayers(gid);
            app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
        }""", [ids, gid])
        pg.wait_for_timeout(800)
        pg.evaluate(SET_BREAKOUT_PREF_JS, saved_pref if saved_pref else None)
        pg.evaluate(RESET_JS, ids)


def test_a_multi_select_breakout_skips_the_screen_its_voltage_refuses(page):
    """The breakout select writes every selected screen, and each is
    gated on its OWN voltage: L21-30 picked with a 208V current screen
    and a 120V peer selected lands on the 208V screen only, the peer
    keeps its breakout and is named once on a toast, one entry. A
    choice both can run is written to both. The 120V peer holds True1
    (the server wrote it for the reset's null; eligible at 120V, so it
    stands through the voltage change) and keeps it."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    saved_pref = pg.evaluate(SET_BREAKOUT_PREF_JS, 'soca-edison')
    pg.evaluate("""(ids) => {
        const app = window.app;
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerVoltage = 120;
        app.normalizePowerBreakout(b);
        app.updateLayers([b]);
        app.setSelectedLayersByIds([ids.aId, ids.bId], ids.aId);
        app.loadLayerToInputs();
    }""", ids)
    pg.wait_for_timeout(600)
    n = pg.evaluate(HIST_LEN_JS)
    _fire(pg, 'power-breakout-type', 'l2130-true1')
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const p = await (await fetch('/api/project')).json();
        const pick = id => {
            const l = app.project.layers.find(x => x.id === id);
            const s = p.layers.find(x => x.id === id);
            return [l.powerBreakoutType, s.powerBreakoutType];
        };
        const host = document.getElementById('app-toast-host');
        return { a: pick(ids.aId), b: pick(ids.bId),
                 n: app.history.length,
                 last: app.history[app.historyIndex].action,
                 toast: host ? host.textContent : '' };
    }""", ids)
    assert out['a'] == ['l2130-true1', 'l2130-true1'], out
    assert out['b'] == ['soca-true1', 'soca-true1'], out
    assert out['n'] == n + 1 and out['last'] == 'Change Power Breakout', out
    assert 'WALL B' in out['toast'] and 'L21-30' in out['toast'], out
    assert 'WALL A' not in out['toast'], out
    # a choice both voltages run lands on both
    _fire(pg, 'power-breakout-type', 'soca-powercon')
    out = pg.evaluate("""(ids) => ids.map(id => window.app.project.layers
        .find(x => x.id === id).powerBreakoutType)""", [ids['aId'], ids['bId']])
    assert out == ['soca-powercon', 'soca-powercon'], out
    assert pg.evaluate(HIST_LEN_JS) == n + 2
    pg.evaluate("""(ids) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(x => x.id === ids.aId));
    }""", ids)
    pg.evaluate(SET_BREAKOUT_PREF_JS, saved_pref if saved_pref else None)
    pg.evaluate(RESET_JS, ids)


def test_a_delete_s_re_fetch_keeps_the_others_breakout(page):
    """deleteLayer replaces the project with the server's copy and puts
    the remaining screens' client props back. The breakout in force is
    among what it keeps now: a breakout the client holds but the server
    does not yet survives the re-fetch, and every screen handed back
    still carries an eligible one."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const scratch = await (await fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'SCRATCH', columns: 2, rows: 2,
                                  cabinet_width: 200, cabinet_height: 200,
                                  offset_x: 5000})})).json();
        app.upsertProjectLayer(scratch);
        // the client holds powerCON on WALL B; the server still holds True1
        const b = app.project.layers.find(x => x.id === ids.bId);
        b.powerBreakoutType = 'soca-powercon';
        // and the server's WALL A copy is bare
        await fetch(`/api/layer/${ids.aId}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerBreakoutType: null})});
        const a = app.project.layers.find(x => x.id === ids.aId);
        a.powerBreakoutType = null;
        app.deleteLayer(scratch.id);
        await new Promise(r => setTimeout(r, 900));
        const p = await (await fetch('/api/project')).json();
        return {
            gone: !p.layers.some(l => l.id === scratch.id),
            b: app.project.layers.find(x => x.id === ids.bId).powerBreakoutType,
            a: app.project.layers.find(x => x.id === ids.aId).powerBreakoutType,
        };
    }""", ids)
    assert out['gone'], out
    assert out['b'] == 'soca-powercon', out
    assert out['a'] == 'soca-true1', out
    pg.evaluate(RESET_JS, ids)


def test_the_guide_s_demo_screen_carries_a_breakout(page):
    """The first-run guide seeds a scratch show whose 208V demo wall
    used to carry no breakout at all; it is normalized like any other
    screen and written through to the server."""
    from test_tour_anchors import _start, _end
    pg, ids = page
    st = _start(pg, 'quick')
    try:
        assert st and st['qs']['index'] == 0, st
        out = pg.evaluate("""async () => {
            const app = window.app;
            const w = app.project.layers.find(l => l.name === 'DEMO WALL');
            const p = await (await fetch('/api/project')).json();
            const s = p.layers.find(l => l.id === w.id);
            return { local: [w.powerVoltage, w.powerBreakoutType],
                     served: [s.powerVoltage, s.powerBreakoutType] };
        }""")
        assert out['local'] == [208, 'soca-true1'], out
        assert out['served'] == [208, 'soca-true1'], out
    finally:
        _end(pg)


def test_the_boot_pass_writes_the_breakout_through_to_the_server(page):
    """The startup client-props pass rewrites a bare breakout, and that
    write used to stay client-only, so the next re-fetch dropped it.
    Now exactly the screens it rewrote are PUT - and since the server
    holds the invariant itself, a PUT of null never even stores a bare
    breakout: the server writes True1 (the shipped preference) on the
    spot, a reload reads it on both sides, and an eligible stored choice
    is left as it was. Last in the module: it reloads the page."""
    pg, ids = page
    pg.evaluate(RESET_JS, ids)
    pg.wait_for_timeout(400)
    pg.evaluate("""async (ids) => {
        const put = (id, body) => fetch(`/api/layer/${id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)});
        await put(ids.bId, {powerVoltage: 208, powerBreakoutType: null});
        await put(ids.aId, {powerVoltage: 208, powerBreakoutType: 'l2130-true1'});
    }""", ids)
    served = pg.evaluate("""async (ids) => {
        const p = await (await fetch('/api/project')).json();
        return [ids.aId, ids.bId].map(id =>
            p.layers.find(l => l.id === id).powerBreakoutType);
    }""", ids)
    assert served == ['l2130-true1', 'soca-true1'], served
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const p = await (await fetch('/api/project')).json();
        return [ids.aId, ids.bId].map(id => [
            app.project.layers.find(l => l.id === id).powerBreakoutType,
            p.layers.find(l => l.id === id).powerBreakoutType]);
    }""", ids)
    assert out == [['l2130-true1', 'l2130-true1'], ['soca-true1', 'soca-true1']], out
