"""Per-circuit cables: the 10' True1 on circuit 1, where it is typed and
where it reads back.

"we need to be able to add cables to each circuit on the distro besides just
soca length or l620 length etc. like say circuit 1 needs a 10ft true 1 and
circuit 2 needs 6ft and 3/4 need nothing and 5 needs 6ft and 6 needs a 10 ft.
since we are going to have those pdf docs we need to be able to have that
info if i want to add it." (user, 2026-09-06). Of src/static/cables-mock.html
the user picked B for the typing ("Option B is the Best for overall use case")
and D as a per-screen switch ("i like having D as an option when doing the
docs per screen").

The fact, per circuit of one screen: an optional cable = length in feet +
connector, stored like the label overrides:

  - layer.powerCircuitCables = { [circuitNum]: { ft, connector } } where a
    null connector FOLLOWS THE BOX - the connector the circuit's box type
    breaks out to (True1 on a Soca 208 feeding a True1 screen, Edison on a
    Soca 120, the L21-30 breakout's own tail connector).
  - Option B: a raised ≡ on the box header flips the chips into a sheet -
    tail · circuit · screen · ft · connector - Tab walking the ft column,
    quick fills under it, the flip remembered per box in localStorage. Each
    commit is ONE 'Set Circuit Cable' entry. A closed sheet's chip wears its
    cable small in its corner.
  - Option D: layer.showPowerCableTags (default FALSE), the "Show Cable Tags"
    box under "Show 2fer / 3fer Tags"; on, a gold tag beside the label on
    screen and in exportMode alike.
  - A cleared circuit forgets its cable the way it forgets its label.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    python -m pytest tests/test_power_cables.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL: 8 wide × 12 rows of 200 W cabinets at 208 V / 10 A - a row is
# 1600 W and a circuit carries 2080 W, so one row per circuit: 12 circuits,
# two multis of six (1–6, 7–12). One distro, SR, offering everything; multi
# 1 lands on SR box 1, so the box reads SR1-1 … SR1-6 with WALL on every
# tail.
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
        body: JSON.stringify({name: 'WALL', columns: 8, rows: 12,
                              cabinet_width: 200, cabinet_height: 200})});
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
    app.dedupeProjectLayers('cables_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(wall, 1, d.id);
    app.setSocaNumber(wall, 1, 1);
    await app.refreshProcessors();
    app.renderLayers();
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.viewMode = 'power';
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    app.resetHistory('Cables Seed');
    return {
        id: wall.id, distroId: d.id,
        labels: app.getSocaPlan(wall)
            .find(s => s.soca === 1).legs.map(g => g.label),
    };
}"""

STATE_JS = """(id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    return {
        cables: JSON.parse(JSON.stringify(l.powerCircuitCables || {})),
        flag: l.showPowerCableTags,
        action: app.history[app.historyIndex].action,
        steps: app.history.length,
        index: app.historyIndex,
    };
}"""

SERVED_JS = """async (id) => {
    const p = await (await fetch('/api/project')).json();
    const l = (p.layers || []).find(x => x.id === id);
    return l ? {
        present: 'powerCircuitCables' in l,
        cables: l.powerCircuitCables || null,
        flagPresent: 'showPowerCableTags' in l,
        flag: l.showPowerCableTags,
    } : null;
}"""

# The resolved reading of one circuit's cable - what the chip corner, the
# canvas tag and the paperwork print.
CABLE_JS = """([id, num]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    app._circuitTailCache = null;
    return app.powerCircuitCable(l, num);
}"""

# What the sheet shows for a box: its rows (tail, label, screen, ft value,
# connector value, the blank option's text), the totals line, the quick
# fill keys, whether the chip grid is up instead, and the switch's state.
SHEET_JS = """([distroId, n]) => {
    const sec = document.querySelector(
        `[data-lrd-sec="hwdock-multi-${distroId}-${n}"]`).parentElement;
    const btn = sec.querySelector(
        `[data-lrd-field="power-cable-sheet-${distroId}-${n}"]`);
    const sheet = sec.querySelector('.hw-dock-cablesheet');
    const rows = sheet ? Array.from(sheet.querySelectorAll('tr'))
        .filter(tr => tr.querySelector('td')
            && !tr.classList.contains('hw-dock-cable-total'))
        .map(tr => {
            const tds = Array.from(tr.querySelectorAll('td'));
            const ft = tr.querySelector('.hw-dock-cable-ft');
            const sel = tr.querySelector('.hw-dock-cable-connector');
            return {
                tail: tds[0].textContent,
                free: tr.classList.contains('hw-dock-cable-free'),
                label: tds[1] ? tds[1].textContent : null,
                who: tds[2] ? tds[2].textContent : null,
                ft: ft ? ft.value : null,
                ftKey: ft ? ft.dataset.lrdField : null,
                connector: sel ? sel.value : null,
                blank: sel ? sel.options[0].textContent : null,
                options: sel ? Array.from(sel.options).map(o => o.value) : null,
            };
        }) : null;
    const tot = sheet && sheet.querySelector('.hw-dock-cable-total');
    return {
        btn: !!btn, on: !!(btn && btn.classList.contains('hw-dock-cablebtn-on')),
        open: !!sheet, rows,
        total: tot ? tot.lastElementChild.textContent : null,
        fills: sheet ? Array.from(sheet.querySelectorAll(
            '[data-lrd-field^="power-cable-fill-"]')).map(b => b.dataset.lrdField)
            : null,
        grid: !!sec.querySelector('.hw-dock-grid'),
        corners: Array.from(sec.querySelectorAll('[data-lrd-tile]')).map(t => ({
            key: t.dataset.lrdTile,
            corner: (t.querySelector('.hw-dock-chip-cable') || {}).textContent
                || null,
        })),
        stored: (() => { try {
            return localStorage.getItem(`lrd_cable_sheet_${distroId}_${n}`);
        } catch (e) { return null; } })(),
    };
}"""

# Every fillText the real render pass paints in power view that looks like
# a cable tag - interactively and in exportMode, since the exporter drives
# this same renderer.
FRAME_TEXTS_JS = """() => {
    const r = window.canvasRenderer, ctx = r.ctx;
    const oT = ctx.fillText;
    const grab = () => {
        const texts = [];
        ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return oT.call(ctx, t, x, y, w); };
        try { r.render(); } finally { ctx.fillText = oT; }
        return texts.filter(t => /^\\d+(\\.\\d+)?' /.test(t));
    };
    const prevMode = r.viewMode, prevExport = r.exportMode;
    let interactive, exported;
    try {
        r.viewMode = 'power';
        r.exportMode = false;
        interactive = grab();
        r.exportMode = true;
        exported = grab();
    } finally {
        r.exportMode = prevExport;
        r.viewMode = prevMode;
        r.render();
    }
    return { interactive, exported };
}"""

FOCUS_JS = """() => {
    const a = document.activeElement;
    return a && a.dataset ? (a.dataset.lrdField || a.tagName) : null;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    assert ids['labels'] == [f'SR1-{i}' for i in range(1, 7)], (
        f'fixture: multi 1 must sit on SR box 1: {ids}')
    yield pg, ids
    context.close()


def _served(page, layer_id, want, timeout_ms=4000):
    waited = 0
    served = None
    while waited <= timeout_ms:
        served = page.evaluate(SERVED_JS, layer_id)
        if served and want(served):
            return served
        page.wait_for_timeout(250)
        waited += 250
    return served


def _ft_field(page, ids, num):
    return page.locator(
        f'[data-lrd-field="power-cable-ft-{ids["id"]}-{num}"]')


def _sheet(page, ids):
    return page.evaluate(SHEET_JS, [ids['distroId'], 1])


def test_the_store_round_trips_through_the_project(page):
    """setCircuitCable writes {ft, connector} under the circuit number and
    the server keeps it: the PUT allow-list took the key, and GET
    /api/project serves it back - a reload would not lose the cable."""
    pg, ids = page
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {}, f'fresh screen must carry an empty store: {st}'
    assert st['flag'] is False, f'the tag switch defaults OFF: {st}'
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 1, { ft: 10, connector: null });
    }""", ids['id'])
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {'1': {'ft': 10, 'connector': None}}, st
    assert st['action'] == 'Set Circuit Cable', st
    served = _served(pg, ids['id'],
                     lambda s: s['present'] and s['cables'] == st['cables'])
    assert served and served['cables'] == {'1': {'ft': 10, 'connector': None}}, (
        f'the server never took powerCircuitCables: {served}')
    assert served['flagPresent'] and served['flag'] is False, served
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(600)
    assert pg.evaluate(STATE_JS, ids['id'])['cables'] == {}


def test_the_box_header_flips_into_the_sheet(page):
    """The raised ≡ on the box header flips the chips into the sheet: six
    rows, tail · circuit · screen · ft · connector, WALL on every tail,
    the connector blank reading "follows breakout (True1)" - a Soca 208 breakout
    feeding a True1 screen. The flip is per box in localStorage, and the
    chip grid is gone while the sheet is up."""
    pg, ids = page
    before = _sheet(pg, ids)
    assert before['btn'] and not before['open'] and before['grid'], before
    pg.locator(f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
    pg.wait_for_timeout(400)
    s = _sheet(pg, ids)
    assert s['open'] and s['on'] and not s['grid'], s
    assert s['stored'] == '1', f'the flip must ride localStorage: {s}'
    assert [r['tail'] for r in s['rows']] == ['1', '2', '3', '4', '5', '6'], s
    assert [r['label'] for r in s['rows']] == ids['labels'], s
    assert all(r['who'] == 'WALL' and not r['free'] for r in s['rows']), s
    assert all(r['ft'] == '' and r['connector'] == '' for r in s['rows']), s
    assert all(r['blank'] == 'follows breakout (True1)' for r in s['rows']), s
    assert s['rows'][0]['options'] == ['', 'true1', 'powercon', 'edison', 'l620'], s
    assert s['total'] == 'no cables', s
    assert s['fills'] == [
        f'power-cable-fill-{ids["distroId"]}-1-10',
        f'power-cable-fill-{ids["distroId"]}-1-6',
        f'power-cable-fill-{ids["distroId"]}-1-none'], s


def test_a_length_commit_is_one_entry_and_undo_restores(page):
    """Typing 10 in circuit 1's ft field and leaving it is ONE 'Set Circuit
    Cable' step: the store holds {ft: 10, connector: null}, the resolved
    cable reads 10' True1 (the box's connector), the totals line counts it,
    and undo forgets it."""
    pg, ids = page
    # History position, not length: an undo earlier in the module leaves
    # a redo tail that the next commit truncates, so the honest count of
    # "one entry" is the index moving by one.
    index = pg.evaluate(STATE_JS, ids['id'])['index']
    _ft_field(pg, ids, 1).fill('10')
    _ft_field(pg, ids, 1).press('Tab')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {'1': {'ft': 10, 'connector': None}}, st
    assert st['action'] == 'Set Circuit Cable' and st['index'] == index + 1, (
        f'one commit, one entry: {st}')
    cable = pg.evaluate(CABLE_JS, [ids['id'], 1])
    assert cable['text'] == "10' True1" and cable['id'] == 'true1', cable
    s = _sheet(pg, ids)
    assert s['rows'][0]['ft'] == '10', s
    assert s['total'] == "1 × 10' True1", s
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {} and st['index'] == index, st
    assert _sheet(pg, ids)['rows'][0]['ft'] == '', 'undo must clear the field'
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids['id'])['cables'] == {
        '1': {'ft': 10, 'connector': None}}


def test_tab_walks_the_length_column(page):
    """Tab from a ft field lands on the NEXT ROW's ft field - across the
    rebuild the commit triggers - and Shift+Tab walks back. Six cables is
    one open: type, Tab, type, Tab."""
    pg, ids = page
    _ft_field(pg, ids, 2).click()
    pg.keyboard.type('6')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    assert pg.evaluate(FOCUS_JS) == f'power-cable-ft-{ids["id"]}-3', (
        'Tab must land on row 3\'s ft field, not the connector or <body>')
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'].get('2') == {'ft': 6, 'connector': None}, st
    pg.keyboard.press('Shift+Tab')
    pg.wait_for_timeout(300)
    assert pg.evaluate(FOCUS_JS) == f'power-cable-ft-{ids["id"]}-2'
    # Row 5 and 6 by the same walk: 5 gets 6', 6 gets 10'.
    _ft_field(pg, ids, 5).click()
    pg.keyboard.type('6')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    assert pg.evaluate(FOCUS_JS) == f'power-cable-ft-{ids["id"]}-6'
    pg.keyboard.type('10')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(900)
    # Row 6 is the last: Tab leaves the column to the browser (no wrap),
    # but the commit still lands.
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {
        '1': {'ft': 10, 'connector': None}, '2': {'ft': 6, 'connector': None},
        '5': {'ft': 6, 'connector': None}, '6': {'ft': 10, 'connector': None},
    }, f'the user\'s own example - 1: 10, 2: 6, 3/4 none, 5: 6, 6: 10: {st}'
    s = _sheet(pg, ids)
    assert s['total'] == "2 × 10' True1 · 2 × 6' True1", s


def test_the_connector_follows_the_box_and_an_override_wins(page):
    """Blank connector = the box's: True1 here. Picking powerCON on circuit
    1 stores the id, the reading says 10' powerCON, and it is its own 'Set
    Circuit Cable' step; back to blank follows the box again."""
    pg, ids = page
    index = pg.evaluate(STATE_JS, ids['id'])['index']
    sel = pg.locator(
        f'[data-lrd-field="power-cable-connector-{ids["id"]}-1"]')
    sel.select_option('powercon')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables']['1'] == {'ft': 10, 'connector': 'powercon'}, st
    assert st['action'] == 'Set Circuit Cable' and st['index'] == index + 1, st
    cable = pg.evaluate(CABLE_JS, [ids['id'], 1])
    assert cable['text'] == "10' powerCON" and cable['connector'] == 'powercon', cable
    assert _sheet(pg, ids)['total'] == "1 × 10' powerCON · 2 × 6' True1 · 1 × 10' True1"
    pg.locator(
        f'[data-lrd-field="power-cable-connector-{ids["id"]}-1"]'
    ).select_option('')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables']['1'] == {'ft': 10, 'connector': None}, st
    assert pg.evaluate(CABLE_JS, [ids['id'], 1])['text'] == "10' True1"


def test_quick_fill_is_one_entry(page):
    """all 6' writes every held circuit on the box as one step; none
    forgets them all as one step; undo puts the whole box back."""
    pg, ids = page
    index = pg.evaluate(STATE_JS, ids['id'])['index']
    pg.locator(f'[data-lrd-field="power-cable-fill-{ids["distroId"]}-1-6"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {
        str(i): {'ft': 6, 'connector': None} for i in range(1, 7)}, st
    assert st['action'] == 'Set Circuit Cable' and st['index'] == index + 1, (
        f'a quick fill is ONE entry: {st}')
    assert _sheet(pg, ids)['total'] == "6 × 6' True1"
    pg.locator(f'[data-lrd-field="power-cable-fill-{ids["distroId"]}-1-none"]').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {} and st['index'] == index + 2, st
    assert _sheet(pg, ids)['total'] == 'no cables'
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids['id'])['cables'] == {
        str(i): {'ft': 6, 'connector': None} for i in range(1, 7)}
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {
        '1': {'ft': 10, 'connector': None}, '2': {'ft': 6, 'connector': None},
        '5': {'ft': 6, 'connector': None}, '6': {'ft': 10, 'connector': None},
    }, f'two undos must put the user\'s own example back: {st}'


def test_a_closed_sheet_shows_the_cable_on_the_chip(page):
    """Flip back to chips: a chip with a cable wears it in its corner
    ("10' True1"), a chip with none wears nothing, and the flip is
    forgotten from localStorage."""
    pg, ids = page
    pg.locator(f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
    pg.wait_for_timeout(400)
    s = _sheet(pg, ids)
    assert not s['open'] and not s['on'] and s['grid'], s
    assert s['stored'] is None, s
    corners = {c['key']: c['corner'] for c in s['corners']}
    d = ids['distroId']
    assert corners == {
        f'ptail-{d}-1-1': "10' True1", f'ptail-{d}-1-2': "6' True1",
        f'ptail-{d}-1-3': None, f'ptail-{d}-1-4': None,
        f'ptail-{d}-1-5': "6' True1", f'ptail-{d}-1-6': "10' True1",
    }, corners


def test_clearing_the_circuit_forgets_its_cable(page):
    """The chip's clear forgets the circuit's cable with its label - cables
    are programming (the 2026-08-30 rule, extended 2026-09-06). Circuit 6
    comes off the box: its cable is gone, the others stay; undo brings it
    back. Then the multi's clear forgets every cable it held."""
    pg, ids = page
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app._clearCircuitChip(l, 1, 6);
    }""", ids['id'])
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert '6' not in st['cables'] and st['action'] == 'Clear Circuit', st
    assert st['cables']['1'] == {'ft': 10, 'connector': None}, st
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables']['6'] == {'ft': 10, 'connector': None}, (
        f'undo must bring the cable back with the circuit: {st}')
    pg.evaluate("""(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === ids.id);
        app._clearMultis([{ layerId: l.id, soca: 1 }], 'Clear Multi');
    }""", ids)
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables'] == {}, f'a cleared multi forgets its cables: {st}'
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['cables']['1'] == {'ft': 10, 'connector': None}, st
    assert pg.evaluate(CABLE_JS, [ids['id'], 1])['text'] == "10' True1", (
        'undo must put the multi back on SR 1 so the connector follows it')


def test_the_canvas_tag_follows_the_switch(page):
    """Off (the default): the power pass paints no cable text, on screen or
    in exportMode. Tick Show Cable Tags: one 'Toggle Cable Tags' step, the
    flag lands on the server, and both passes paint 10' True1 beside
    circuit 1 (and the others' cables). Undo un-ticks and un-paints."""
    pg, ids = page
    box = pg.locator('#show-power-cable-tags')
    assert box.is_visible() and not box.is_checked(), 'default OFF, under 2fer'
    frame = pg.evaluate(FRAME_TEXTS_JS)
    assert frame == {'interactive': [], 'exported': []}, frame
    index = pg.evaluate(STATE_JS, ids['id'])['index']
    box.click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['flag'] is True and st['action'] == 'Toggle Cable Tags', st
    assert st['index'] == index + 1, st
    frame = pg.evaluate(FRAME_TEXTS_JS)
    want = ["10' True1", "6' True1", "6' True1", "10' True1"]
    assert sorted(frame['interactive']) == sorted(want), frame
    assert sorted(frame['exported']) == sorted(want), (
        f'the export pass must match the screen: {frame}')
    served = _served(pg, ids['id'], lambda s: s['flag'] is True)
    assert served and served['flag'] is True, (
        f'the server never took showPowerCableTags=true: {served}')
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids['id'])
    assert st['flag'] is False and not box.is_checked(), st
    assert pg.evaluate(FRAME_TEXTS_JS) == {'interactive': [], 'exported': []}
    pg.evaluate('() => window.app.redo()')
    pg.wait_for_timeout(900)
    assert pg.evaluate(STATE_JS, ids['id'])['flag'] is True and box.is_checked()
    box.click()
    pg.wait_for_timeout(600)
    assert pg.evaluate(STATE_JS, ids['id'])['flag'] is False


# Where each tag sits relative to its label, in the power pass: for every
# label row, the x of the label text and of the tag text painted at that y.
TAG_SIDES_JS = """([pattern, labelSize]) => {
    const app = window.app, r = window.canvasRenderer, l = app.currentLayer;
    l.powerFlowPattern = pattern;
    if (labelSize) l.powerLabelSize = labelSize;
    l._powerCircuits = null;          // the cached auto plan follows the pattern
    l._powerCircuitNumKeys = null;
    app._circuitTailCache = null;
    const ctx = r.ctx, oT = ctx.fillText, texts = [];
    ctx.fillText = function (t, x, y, w) { texts.push([String(t), x, y]); return oT.call(ctx, t, x, y, w); };
    const prev = r.viewMode;
    try { r.viewMode = 'power'; r.render(); } finally { ctx.fillText = oT; r.viewMode = prev; }
    const tags = texts.filter(t => /^\\d+(\\.\\d+)?' /.test(t[0]));
    const labels = texts.filter(t => /^S[A-Z]*\\d+-\\d+$/.test(t[0]));
    return tags.map(t => {
        const lab = labels.find(x => Math.abs(x[2] - t[2]) < 1);
        return { tag: t[0], side: lab ? (t[1] > lab[1] ? 'right' : 'left') : 'none',
                 lx: lab ? Math.round(lab[1]) : null, tx: Math.round(t[1]) };
    });
}"""


def test_a_tag_on_the_wall_s_edge_flips_inside_the_screen(page):
    """A label on the right edge of the wall would push its tag off the
    screen and under the next one - "there are no tags for SR 1-1 and so
    on. they are to the right behind the other screen. they should be on
    the inside of the screen" (2026-09-06). Runs from the left: tags hang
    right of the label. Runs from the right: the label sits on the wall's
    right edge and the tag flips to its left, inside."""
    pg, ids = page
    box = pg.locator('#show-power-cable-tags')
    if not box.is_checked():
        box.click()
        pg.wait_for_timeout(700)
    size = pg.evaluate('() => window.app.currentLayer.powerLabelSize')
    try:
        # Big labels, so a right-edge label plus its tag cannot fit inside
        # the last cabinet - the shape of the user's 60 px wall at 30 px.
        left_runs = pg.evaluate(TAG_SIDES_JS, ['tl-h', 60])
        assert left_runs and all(t['side'] == 'right' for t in left_runs), left_runs
        right_runs = pg.evaluate(TAG_SIDES_JS, ['tr-h', 60])
        assert right_runs and all(t['side'] == 'left' for t in right_runs), (
            f'a right-edge label must carry its tag on the inside: {right_runs}')
    finally:
        pg.evaluate(TAG_SIDES_JS, ['tl-h', size])
        box.click()
        pg.wait_for_timeout(600)
    assert not box.is_checked()


def test_the_switch_reads_the_selected_screen(page):
    """loadLayerToInputs: the box follows the layer it shows, and an absent
    key reads OFF - the docs option is opted into, never inherited."""
    pg, ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const l = app.currentLayer;
        const box = document.getElementById('show-power-cable-tags');
        l.showPowerCableTags = true;
        app.loadLayerToInputs();
        const on = box.checked;
        l.showPowerCableTags = false;
        app.loadLayerToInputs();
        const off = box.checked;
        delete l.showPowerCableTags;
        app.loadLayerToInputs();
        const absent = box.checked;
        l.showPowerCableTags = false;
        return { on, off, absent };
    }""")
    assert out == {'on': True, 'off': False, 'absent': False}, out


def test_a_box_typed_l2130_defaults_its_tails_to_that_breakout(page):
    """A spare box typed L21-30 breaks out to True1 (the breakout table's
    first L21-30 entry) for a tail nobody holds; a holder whose breakout is
    l2130-powercon reads powerCON; a Soca 120 box is Edison. Off any distro
    the screen's own breakout answers."""
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const d = app.getDistros().find(x => x.id === ids.distroId);
        const l = app.project.layers.find(x => x.id === ids.id);
        app.setDistroBoxType(d.id, 3, 'l2130');
        app.setDistroBoxType(d.id, 4, 'soca120');
        const name = (id) => app.cableConnectorName(id);
        const r = {
            spare: name(app.boxTailConnector(d, 3, null)),
            true1Holder: name(app.boxTailConnector(d, 3, l)),
            box1: name(app.boxTailConnector(d, 1, l)),
            soca120: name(app.boxTailConnector(d, 4, l)),
            offDistro: name(app.boxTailConnector(null, null, l)),
        };
        const saved = l.powerBreakoutType;
        l.powerBreakoutType = 'l2130-powercon';
        r.powerconHolder = name(app.boxTailConnector(d, 3, l));
        l.powerBreakoutType = 'soca-l620';
        r.offDistroL620 = name(app.boxTailConnector(null, null, l));
        l.powerBreakoutType = saved;
        app.setDistroBoxType(d.id, 3, null);
        app.setDistroBoxType(d.id, 4, null);
        return r;
    }""", ids)
    assert out == {
        'spare': 'True1', 'true1Holder': 'True1', 'box1': 'True1',
        'soca120': 'Edison', 'offDistro': 'True1',
        'powerconHolder': 'powerCON', 'offDistroL620': 'L6-20',
    }, out


# ── the sheet leaves the fold alone ──────────────────────────────────────
#
# "when i have the multi collapsed and i open the cable size page and make
# changes and close the page it uncollapses the multi. this seems clunky."
# (user, 2026-09-06). The fold is the user's; the sheet must not touch it.
# The sheet rides between the header and the foldable body - the LEGS
# line's seat on a distro - so a folded box shows it without unfolding,
# and each commit's rebuild puts the caret back without opening a fold
# that never hid the field.

FOLD_JS = """([distroId, n]) => {
    const secId = `hwdock-multi-${distroId}-${n}`;
    const head = document.querySelector(`[data-lrd-sec="${secId}"]`);
    const sec = head.parentElement;
    const body = sec.querySelector(':scope > .lrd-sec-body');
    const sheet = sec.querySelector('.hw-dock-cablesheet');
    return {
        collapsed: sec.classList.contains('lrd-sec-collapsed'),
        stored: localStorage.getItem(`ledRasterPanelCollapsed_${secId}`),
        bodyHidden: getComputedStyle(body).display === 'none',
        sheet: !!sheet,
        sheetVisible: !!(sheet && sheet.offsetParent !== null),
        gridVisible: !!(sec.querySelector('.hw-dock-grid')
                        && sec.querySelector('.hw-dock-grid').offsetParent),
    };
}"""


def _fold(page, ids):
    return page.evaluate(FOLD_JS, [ids['distroId'], 1])


def _flip(page, ids):
    page.locator(
        f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
    page.wait_for_timeout(500)


def test_the_sheet_leaves_a_folded_box_folded(page):
    """Fold the box, open the sheet, type a length, close the sheet: the
    box is still folded - stored key and rendered state alike - and the
    sheet was visible the whole time it was open."""
    pg, ids = page
    _sheet(pg, ids)['open'] and _flip(pg, ids)
    pg.locator(
        f'[data-lrd-sec="hwdock-multi-{ids["distroId"]}-1"] .lrd-sec-arrow'
    ).click()
    pg.wait_for_timeout(300)
    st = _fold(pg, ids)
    assert st['collapsed'] and st['stored'] == '1' and st['bodyHidden'], st
    _flip(pg, ids)
    st = _fold(pg, ids)
    assert st['sheet'] and st['sheetVisible'], (
        f'a folded box must still show the sheet it was asked for: {st}')
    assert st['collapsed'] and st['stored'] == '1', (
        f'opening the sheet unfolded the box: {st}')
    before = pg.evaluate(STATE_JS, ids['id'])
    _ft_field(pg, ids, 5).fill('12')
    _ft_field(pg, ids, 5).press('Tab')
    pg.wait_for_timeout(900)
    st_c = pg.evaluate(STATE_JS, ids['id'])
    assert st_c['cables'].get('5') == {'ft': 12, 'connector': None}, st_c
    assert st_c['index'] == before['index'] + 1, st_c
    assert pg.evaluate(FOCUS_JS) == f'power-cable-ft-{ids["id"]}-6', (
        'Tab must still walk the column on a folded box')
    st = _fold(pg, ids)
    assert st['collapsed'] and st['stored'] == '1' and st['sheetVisible'], (
        f'a length commit unfolded the box: {st}')
    _flip(pg, ids)
    st = _fold(pg, ids)
    assert not st['sheet'] and not st['gridVisible'], st
    assert st['collapsed'] and st['stored'] == '1' and st['bodyHidden'], (
        f'closing the sheet unfolded the box: {st}')
    # leave the box open and the cable gone for the tests that follow
    pg.locator(
        f'[data-lrd-sec="hwdock-multi-{ids["distroId"]}-1"] .lrd-sec-arrow'
    ).click()
    pg.wait_for_timeout(300)
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st_c = pg.evaluate(STATE_JS, ids['id'])
    assert st_c['cables'] == before['cables'] and st_c['index'] == before['index']
    st = _fold(pg, ids)
    assert not st['collapsed'] and st['stored'] == '0', st


def test_the_sheet_leaves_an_open_box_open(page):
    """The other half of the rule: an unfolded box stays unfolded through
    open, commit and close - and the sheet never writes the fold key."""
    pg, ids = page
    st = _fold(pg, ids)
    assert not st['collapsed'] and st['stored'] == '0', st
    _flip(pg, ids)
    st = _fold(pg, ids)
    assert st['sheetVisible'] and not st['collapsed'] and st['stored'] == '0', st
    before = pg.evaluate(STATE_JS, ids['id'])
    _ft_field(pg, ids, 6).fill('12')
    _ft_field(pg, ids, 6).press('Tab')
    pg.wait_for_timeout(900)
    st = _fold(pg, ids)
    assert st['sheetVisible'] and not st['collapsed'] and st['stored'] == '0', st
    _flip(pg, ids)
    st = _fold(pg, ids)
    assert st['gridVisible'] and not st['collapsed'] and st['stored'] == '0', st
    st_c = pg.evaluate(STATE_JS, ids['id'])
    assert st_c['cables'].get('6') == {'ft': 12, 'connector': None}, st_c
    assert st_c['index'] == before['index'] + 1, st_c
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    st_c = pg.evaluate(STATE_JS, ids['id'])
    assert st_c['cables'] == before['cables'] and st_c['index'] == before['index']
