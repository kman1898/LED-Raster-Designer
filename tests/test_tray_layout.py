"""The hardware tray holds still: a fixed grid, and reorder by drag.

"still having weirdness in the data hardware screen. need to make sure this
doesnt happen in power either. also when i try and open the cable sheet it
jumps the whole screen around. this becomes very confusing / we need to
audit this and clean it up for each and every time" and "also being able to
drag them around and reorder them would be nice too" (user, 2026-09-08/09).

Before: #hardware-dock-body was a flex-wrap row of CONTENT-sized items - a
unit with an open data sheet took `flex: 0 1 auto`, a folded one `flex: 0 1
auto; max-width: 300px` - so one card's state re-packed every row: the card
beside it grew to the whole row, the rows below moved sideways and dropped
hundreds of pixels. Now the body is a GRID of equal 440px tracks. Every
top-level item is one cell, a cell's width is the tray's business alone, and
a state change can only make a cell TALLER, which pushes lower rows down and
moves nothing sideways.

This is the "each and every time" audit: for every interaction the tray
offers, in BOTH views, every cell's rect is snapshotted before and after and
asserted to keep its x and its width, to move in y only where the rows below
the interacted one are, and to leave the scroll where it was (or, where the
rebuild scrolls at all, to keep the interacted unit's top exactly where it
sat in the viewport).

Then the reorder: a processor's title strip and a distro's header drag along
the tray, an accent bar marks the gap, and the drop moves the machine in the
STORED order every reader follows - the tray, the binder's 'data' screen
order and its hardware sheets. A pair moves with its main. Undo restores it.
A drag that ends on the canvas still assigns.

Run locally (ONE pytest at a time - the browser-test servers use fixed
ports):
    LRD_E2E_PORT=15793 python -m pytest tests/test_tray_layout.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# His show's shape: three processors - one on its own ("DJ"), then a 1:1
# pair ("IMAG A" backed whole by "IMAG B") - one of them carrying a breakout
# box, two screens placed on two different processors so the binder's 'data'
# order has something to follow, and distros with one occupied multi and its
# spare. The H series is Legacy gear, so the screens' Processing must say so
# or every placement refuses (the platform wall, 2026-08-28).
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL A', columns: 12, rows: 8,
        cabinet_width: 200, cabinet_height: 200});
    await j('POST', '/api/layer/add', {name: 'WALL B', columns: 6, rows: 4,
        cabinet_width: 200, cabinet_height: 200, offset_x: 3000});
    const chassis = async (name, withBox) => {
        let st = await j('POST', '/api/processors',
                         {deviceId: 'novastar-h9', name});
        const id = st.processors[st.processors.length - 1].id;
        st = await j('PUT', `/api/processors/${id}/slots/0`,
                     {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        const proc = st.processors.find(p => p.id === id);
        const cardId = proc.slots[0].card.id;
        await j('PUT', `/api/processors/${id}/cards/${cardId}`, {name});
        let boxId = null;
        if (withBox) {
            st = await j('POST', `/api/processors/${id}/cards/${cardId}/cvts`,
                         {deviceId: 'novastar-cvt10', pair: false});
            boxId = st.processors.find(p => p.id === id)
                .slots[0].card.cvts[0].id;
        }
        return {id, cardId, boxId};
    };
    const dj = await chassis('DJ', true);
    const imagA = await chassis('IMAG A', false);
    const imagB = await chassis('IMAG B', false);
    await j('PUT', `/api/processors/${imagA.id}`, {redundancy: true});
    await j('PUT', `/api/processors/${imagA.id}`,
            {backupProcessorId: imagB.id});
    const app = window.app;
    const p0 = await j('GET', '/api/project');
    for (const l of p0.layers) {
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'novastar-armor',
            powerVoltage: 208, powerAmperage: 20});
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('tray_layout_seed');
    const a = app.project.layers.find(l => l.name === 'WALL A');
    const b = app.project.layers.find(l => l.name === 'WALL B');
    app.selectLayer(a);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow',
        'POST', {layerId: String(a.id), cardId: dj.cardId});
    await app._assignmentRequest('/api/port-assignments/place-overflow',
        'POST', {layerId: String(b.id), cardId: imagA.cardId});
    // Power: one distro carrying WALL A's first multi (so it has a box with
    // circuits and a spare beside it), plus two more so the tray's power
    // side has more than one cell to hold still.
    app.addDistro({name: 'S1'});
    app.addDistro({name: 'S2'});
    app.addDistro({name: 'S3'});
    const distros = app.getDistros().map(d => d.id);
    const plan = app.getSocaPlan(a);
    app.setSocaDistro(a, plan[0].soca, distros[0], false);
    app.setSocaNumber(a, plan[0].soca, 1, false);
    app.updateLayers([a], true, 'Seed Power');
    app._circuitTailCache = null;
    app.refreshSocaRuns();
    // The tray at the height his screenshot was taken at.
    const dock = document.getElementById('hardware-dock');
    dock.style.height = '520px';
    if (typeof app.settleLayout === 'function') app.settleLayout();
    app.renderLayers();
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.zoom = 0.22; r.panX = 60; r.panY = 40; r.render();
    app.resetHistory('Tray Layout Seed');
    return {
        aId: a.id, bId: b.id,
        djId: dj.id, djCard: dj.cardId, djBox: dj.boxId,
        imagAId: imagA.id, imagACard: imagA.cardId,
        imagBId: imagB.id, imagBCard: imagB.cardId,
        distros, soca: plan[0].soca,
    };
}"""


# Every top-level CELL of the tray as it sits: its x, its width, its height
# and its y in the body's own CONTENT space (so a scroll does not read as a
# move), plus where every header sits in the VIEWPORT and where the scroll
# stands. `owns` names the headers each cell holds, so the audit can find
# the cell the interaction belongs to.
CELLS_JS = """() => {
    const body = document.getElementById('hardware-dock-body');
    const bt = body.getBoundingClientRect().top;
    const cells = [...body.children].filter(el => el.classList
        && !el.classList.contains('hw-dock-drop-mark')
        && !el.classList.contains('hw-dock-note'));
    const heads = (el) => [...el.querySelectorAll(
        '.hw-dock-head-row[data-hwdock], .hw-dock-proc-name[data-hwdock]')]
        .map(x => x.dataset.hwdock);
    return {
        scrollTop: body.scrollTop,
        scrollHeight: body.scrollHeight,
        clientHeight: body.clientHeight,
        display: getComputedStyle(body).display,
        tracks: getComputedStyle(body).gridTemplateColumns,
        cells: cells.map((el, i) => {
            const r = el.getBoundingClientRect();
            const own = heads(el);
            return {key: own[0] || `cell-${i}`, own,
                    span: el.classList.contains('hw-dock-span2'),
                    x: r.left, w: r.width, h: r.height,
                    cy: r.top - bt + body.scrollTop};
        }),
        tops: Object.fromEntries([...body.querySelectorAll('[data-hwdock]')]
            .map(el => [el.dataset.hwdock,
                        el.getBoundingClientRect().top])),
    };
}"""

TRAY_ORDER_JS = """() => [...document.querySelectorAll(
    '#hardware-dock-body .hw-dock-proc-name[data-hwdock]')]
    .map(el => el.dataset.hwdock.slice('processor-'.length))"""

# The binder the reorder is read through: the show, its screen sheets and
# its hardware sheets - the shape readBinderOptions serves (sides, not
# top-level power/data).
BINDER_OPTS = ('{"sheet": "tabloid", "palette": "colour",'
               ' "sides": {"power": true, "data": false},'
               ' "scope": {"kind": "show"}, "cover": false, "pull": false,'
               ' "wiring": false, "hardware": true}')

DISTRO_ORDER_JS = ("() => window.app.getDistros().map(d => d.id)")
STORED_ORDER_JS = ("async () => (await (await fetch('/api/processors'))"
                   ".json()).processors.map(p => p.id)")
HIST_JS = ("() => ({action: "
           "window.app.history[window.app.historyIndex].action, "
           "index: window.app.historyIndex})")


def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(500)


@pytest.fixture(scope="module")
def tray(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1500)
    yield pg, ids
    context.close()


def _cell_of(shot, key):
    for i, c in enumerate(shot['cells']):
        if key in c['own']:
            return i, c
    raise AssertionError(f'no cell holds {key}: '
                         f'{[c["own"] for c in shot["cells"]]}')


def _tracks(shot):
    """The grid's track widths. A tray that is not a grid has none (the
    flex tray below computes 'none'), and then the only thing holding a
    cell's width is the x/width comparison - which is the point."""
    out = []
    for t in (shot['tracks'] or '').split():
        if not t.endswith('px'):
            return []
        out.append(float(t[:-2]))
    return out


def audit(page, what, unit_key, act, settle=700, regroups=False):
    """Do `act`, then hold the tray to the rule: nothing changes x or
    width, only cells at or below the interacted one's row move in y, and
    the scroll either stands still or moves exactly enough to keep the
    interacted unit's top where it was in the viewport.

    `regroups` is for the one gesture that legitimately changes WHICH
    cells there are - switching a paired card to a per-port redundancy
    mode retires the whole-processor pairing, so the backup leaves its
    main's cell and becomes a cell of its own. The tray still holds the
    rule that matters: every cell that survives keeps its x and its
    width, and every cell - old or new - is a whole number of tracks
    wide, sitting on a track, because the grid decides that and no
    unit's state ever does.
    """
    before = page.evaluate(CELLS_JS)
    act()
    page.wait_for_timeout(settle)
    after = page.evaluate(CELLS_JS)
    note = json.dumps({'what': what, 'before': before['cells'],
                       'after': after['cells'],
                       'scroll': [before['scrollTop'], after['scrollTop']]})
    if not regroups:
        assert [c['key'] for c in before['cells']] \
            == [c['key'] for c in after['cells']], note
    bi, bcell = _cell_of(before, unit_key)
    was = {c['key']: c for c in before['cells']}
    tracks = _tracks(after)
    gap = 10
    for a in after['cells']:
        # Every cell is the grid's width, never its content's: one track,
        # or two for a device past 24 sockets.
        if tracks:
            want = tracks[0] * 2 + gap if a['span'] else tracks[0]
            assert abs(a['w'] - want) <= 1.0, (
                f'{what}: {a["key"]} is not a whole number of tracks wide\n'
                f'{note}')
        b = was.get(a['key'])
        if not b:
            continue
        assert abs(a['x'] - b['x']) <= 0.5, f'{what}: {b["key"]} moved in x\n{note}'
        assert abs(a['w'] - b['w']) <= 0.5, f'{what}: {b["key"]} changed width\n{note}'
        if abs(a['cy'] - b['cy']) > 0.5:
            assert b['cy'] >= bcell['cy'] - 0.5, (
                f'{what}: {b["key"]} sits above the interacted cell and '
                f'still moved\n{note}')
    if abs(after['scrollTop'] - before['scrollTop']) > 0.5:
        assert unit_key in before['tops'] and unit_key in after['tops'], note
        assert abs(after['tops'][unit_key] - before['tops'][unit_key]) <= 1.5, (
            f'{what}: the tray scrolled and did not keep {unit_key} under '
            f'the pointer\n{note}')
    return before, after


def click_field(page, key):
    page.locator(f'[data-lrd-field="{key}"]').click()


def fold_arrow(page, sec):
    page.locator(f'[data-lrd-sec="{sec}"] .lrd-sec-arrow').click()


def test_the_tray_is_a_fixed_grid_of_equal_tracks(tray):
    """The body is a CSS grid of equal 440px tracks, not a flex row: every
    top-level cell is one track wide (a >24-socket device may take two),
    and two cells side by side are exactly as wide as each other."""
    page, ids = tray
    open_view(page, 'data-flow')
    shot = page.evaluate(CELLS_JS)
    print('\ndata tray:', json.dumps(shot['cells']))
    assert shot['display'] == 'grid', shot['display']
    tracks = [float(t.replace('px', '')) for t in shot['tracks'].split()]
    assert len(tracks) >= 1, shot['tracks']
    assert all(abs(t - tracks[0]) <= 0.5 for t in tracks), shot['tracks']
    # two cells: DJ on its own, IMAG A + IMAG B as one pair
    assert len(shot['cells']) == 2, [c['own'] for c in shot['cells']]
    assert shot['cells'][0]['own'][0] == f'processor-{ids["djId"]}'
    assert set(shot['cells'][1]['own'][:1] + shot['cells'][1]['own'][1:2]) \
        >= {f'processor-{ids["imagAId"]}'}, shot['cells'][1]['own']
    assert f'processor-{ids["imagBId"]}' in shot['cells'][1]['own'], (
        'the pair is ONE cell')
    # every cell is a whole number of tracks wide, and no card in the seed
    # crosses 24 sockets, so nothing spans
    for c in shot['cells']:
        assert not c['span'], c
        assert abs(c['w'] - tracks[0]) <= 1.0, (c, tracks)


# The tray as it was on 2026-09-08, put back as one stylesheet: the
# flex-wrap body with content-sized items, the folded card's 300px cap and
# the open sheet's `flex: 0 1 auto` with its 480px floor. Injected LAST, so
# it wins over the grid rules it replaced.
FLEX_TRAY_CSS = """
#hardware-dock-body {
    display: flex; flex-wrap: wrap; gap: 10px;
    align-items: flex-start; align-content: flex-start;
}
.hw-dock-proc {
    display: flex; flex-direction: row; flex-wrap: wrap; gap: 8px;
    align-items: flex-start; flex: 1 1 300px; min-width: 0;
}
.hw-dock-proc-name { flex: 1 1 100%; }
.hw-dock-unit { flex: 1 1 240px; min-width: 170px; max-width: 100%; }
#hardware-dock-body > .lrd-red-pair { flex: 1 1 300px; }
.hw-dock-proc > .lrd-red-pair {
    flex: 1 1 240px; min-width: 170px; max-width: 100%;
}
#hardware-dock-body .hw-dock-proc .hw-dock-unit.lrd-sec-collapsed {
    flex: 0 1 auto; min-width: 0; max-width: 300px;
}
#hardware-dock-body > .hw-dock-unit:has(.hw-dock-cablesheet-data),
#hardware-dock-body > .hw-dock-proc:has(.hw-dock-cablesheet-data),
#hardware-dock-body > .lrd-red-pair:has(.hw-dock-cablesheet-data),
#hardware-dock-body .hw-dock-proc > .lrd-red-pair:has(.hw-dock-cablesheet-data),
#hardware-dock-body .hw-dock-proc .hw-dock-unit:has(.hw-dock-cablesheet-data) {
    flex: 0 1 auto; max-width: 100%;
}
.hw-dock-cablesheet-data { min-width: 480px; }
"""


def test_the_audit_catches_the_tray_it_retired(tray):
    """The audit is only worth running if it FAILS on the thing it was
    written against. Put the flex tray back as a stylesheet, open a card's
    cable sheet through the same audit every test below uses, and the
    audit must refuse it: on the flex tray that one click re-packs the
    row - the neighbour grows, the cells move sideways. Then take the
    stylesheet away and the same click is clean."""
    page, ids = tray
    open_view(page, 'data-flow')
    card = ids['djCard']
    page.add_style_tag(content=FLEX_TRAY_CSS)
    page.wait_for_timeout(400)
    try:
        assert page.evaluate(CELLS_JS)['display'] == 'flex'
        with pytest.raises(AssertionError) as caught:
            audit(page, 'card sheet open ON THE FLEX TRAY', f'card-{card}',
                  lambda: click_field(page, f'data-cable-sheet-{card}'))
        print('\nthe flex tray fails the audit:', str(caught.value)[:200])
        assert 'moved in x' in str(caught.value) \
            or 'changed width' in str(caught.value), str(caught.value)[:400]
    finally:
        # close the sheet again, then drop the stylesheet
        click_field(page, f'data-cable-sheet-{card}')
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            const s = [...document.querySelectorAll('style')].filter(
                el => el.textContent.includes('hw-dock-cablesheet-data')
                   && el.textContent.includes('flex-wrap'));
            s.forEach(el => el.remove());
        }""")
        page.wait_for_timeout(400)
    assert page.evaluate(CELLS_JS)['display'] == 'grid'
    # the same gesture, on the grid, holds still
    audit(page, 'card sheet open', f'card-{card}',
          lambda: click_field(page, f'data-cable-sheet-{card}'))
    audit(page, 'card sheet close', f'card-{card}',
          lambda: click_field(page, f'data-cable-sheet-{card}'))


def test_a_device_past_24_sockets_takes_two_tracks(tray):
    """The span rule, and the only thing that decides it: a card with more
    than 24 sockets (H_4xfiber enhanced, 40) takes two of the tray's
    tracks so its chips still wrap into a readable block. A static fact of
    the model - the port count - so no sheet, fold, name or pairing ever
    changes it, and the cells beside it keep their own x and width."""
    page, ids = tray
    open_view(page, 'data-flow')
    before = page.evaluate(CELLS_JS)
    wide = page.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body)})
            .then(r => r.json());
        let st = await j('POST', '/api/processors',
                         {deviceId: 'novastar-h9', name: 'WIDE'});
        const id = st.processors[st.processors.length - 1].id;
        await j('PUT', `/api/processors/${id}/slots/0`,
                {deviceId: 'novastar-card-h-4xfiber-enhanced'});
        await app.refreshProcessors();
        app.renderHardwareDock();
        return id;
    }""")
    page.wait_for_timeout(900)
    try:
        after = page.evaluate(CELLS_JS)
        print('\nwith a 40-socket card:', json.dumps(after['cells']))
        tracks = _tracks(after)
        assert len(tracks) >= 2, after['tracks']
        cell = [c for c in after['cells']
                if f'processor-{wide}' in c['own']]
        assert len(cell) == 1, after['cells']
        assert cell[0]['span'], cell[0]
        assert abs(cell[0]['w'] - (tracks[0] * 2 + 10)) <= 1.0, (cell, tracks)
        # the cells that were there keep theirs
        was = {c['key']: c for c in before['cells']}
        for c in after['cells']:
            b = was.get(c['key'])
            if not b:
                continue
            assert abs(c['x'] - b['x']) <= 0.5 and abs(c['w'] - b['w']) <= 0.5, (
                b, c)
        # and no 16-socket card ever spans
        assert not any(c['span'] for c in after['cells']
                       if f'processor-{wide}' not in c['own']), after['cells']
    finally:
        page.evaluate("""async (id) => {
            await fetch(`/api/processors/${id}`, {method: 'DELETE'});
            await window.app.refreshProcessors();
            window.app.renderHardwareDock();
        }""", wide)
        page.wait_for_timeout(800)
    back = page.evaluate(CELLS_JS)
    assert [c['key'] for c in back['cells']] == [c['key'] for c in before['cells']], back


DATA_ACTS = ['card sheet', 'box sheet', 'fold card', 'fold processor',
             'fold pair backup', 'chip editor', 'rename card',
             'redundancy mode']


def test_the_data_tray_holds_still_through_every_interaction(tray):
    """The audit, data side. Every gesture the data tray offers, opened and
    closed again, with every cell measured before and after."""
    page, ids = tray
    open_view(page, 'data-flow')
    card = ids['djCard']
    box = ids['djBox']
    imag = ids['imagACard']

    # a card's data sheet, open then closed
    for turn in ('open', 'close'):
        audit(page, f'card sheet {turn}', f'card-{card}',
              lambda: click_field(page, f'data-cable-sheet-{card}'))
    # a box's sheet
    for turn in ('open', 'close'):
        audit(page, f'box sheet {turn}', f'box-{box}',
              lambda: click_field(page, f'data-cable-sheet-{box}'))
    # a card folds and unfolds (the IMAG A card, inside the pair's cell)
    for turn in ('fold', 'unfold'):
        audit(page, f'{turn} card', f'card-{imag}',
              lambda: fold_arrow(page, f'hwdock-card-{imag}'))
    # a whole processor folds: DJ's only card is DJ's whole content
    for turn in ('fold', 'unfold'):
        audit(page, f'{turn} processor', f'card-{card}',
              lambda: fold_arrow(page, f'hwdock-card-{card}'))
    # the BACKUP half of the pair folds on its own
    for turn in ('fold', 'unfold'):
        audit(page, f'{turn} pair backup', f'card-{ids["imagBCard"]}',
              lambda: fold_arrow(page, f'hwdock-card-{ids["imagBCard"]}'))
    # a chip's editor opens and closes in place
    for turn in ('open', 'close'):
        audit(page, f'chip editor {turn}', f'card-{card}',
              lambda: page.locator(
                  f'[data-hwdock="port-{card}-9"]').click())
    # a card is renamed

    def rename(to):
        f = page.locator(f'[data-lrd-field="processor-card-name-{card}"]')
        f.fill(to)
        f.press('Tab')
    audit(page, 'rename card', f'card-{card}', lambda: rename('DJ MAIN'), 1100)
    audit(page, 'rename back', f'card-{card}', lambda: rename('DJ'), 1100)
    # the redundancy mode switches on the pair's main card

    def mode(m):
        page.evaluate("""([pid, cid, m]) => window.app._processorRequest(
            `/api/processors/${pid}/cards/${cid}`, 'PUT',
            {redundancyMode: m}, 'Set Redundancy Mode')""",
                      [ids['imagAId'], imag, m])
    # Switching the pair's main to a PER-PORT mode retires the whole-unit
    # pairing, so the backup leaves the pair's cell and takes a cell of its
    # own - a regrouping the model asks for, not the tray re-packing.
    audit(page, 'redundancy mode → halves', f'card-{imag}',
          lambda: mode('halves'), 1100, regroups=True)
    audit(page, 'redundancy mode → 1to1', f'card-{imag}',
          lambda: mode('1to1'), 1100, regroups=True)
    # and the pair is whole again, in one cell, exactly as it started
    page.evaluate("""([pid, bid]) => window.app._processorRequest(
        `/api/processors/${pid}`, 'PUT',
        {backupProcessorId: bid}, 'Set Backup Processor')""",
                  [ids['imagAId'], ids['imagBId']])
    page.wait_for_timeout(1100)
    shot = page.evaluate(CELLS_JS)
    assert len(shot['cells']) == 2, [c['own'] for c in shot['cells']]


def test_a_scrolled_tray_keeps_the_unit_under_the_pointer(tray):
    """"when i try and open the cable sheet it jumps the whole screen
    around". The rebuild wipes the body, so a tray that is SCROLLED has to
    come back where it was - and when the rebuild came from a control on a
    unit, that unit has to come back under the pointer, however much taller
    the sheet above it made the column."""
    page, ids = tray
    open_view(page, 'data-flow')
    # the pair's BACKUP card: its ≡ sits low in the column, so the tray is
    # a long way down when the button is in view
    card = ids['imagBCard']
    # a short tray, so the column has more than it can show
    page.evaluate("""() => {
        const d = document.getElementById('hardware-dock');
        d.style.height = '240px';
        if (typeof window.app.settleLayout === 'function') window.app.settleLayout();
    }""")
    page.wait_for_timeout(500)
    try:
        # scroll so the ≡ we are about to press is comfortably in view and
        # the tray is a long way from the top - a click that had to scroll
        # the button into view would move the tray for its own reasons
        room = page.evaluate("""(key) => {
            const b = document.getElementById('hardware-dock-body');
            const el = document.querySelector(`[data-lrd-field="${key}"]`);
            let y = 0, n = el;
            while (n && n !== b) { y += n.offsetTop; n = n.offsetParent; }
            b.scrollTop = Math.max(0, Math.min(
                b.scrollHeight - b.clientHeight,
                y - Math.max(30, b.clientHeight - 80)));
            return {top: b.scrollTop, over: b.scrollHeight - b.clientHeight};
        }""", f'data-cable-sheet-{card}')
        page.wait_for_timeout(300)
        print('\nscrolled to', room)
        assert room['over'] > 60 and room['top'] > 20, (
            'the tray must have somewhere to scroll or this proves nothing',
            room)
        # the audit itself holds the rule: scrollTop unchanged, or the
        # unit's top unchanged in the viewport
        for turn in ('open', 'close'):
            before, _after = audit(
                page, f'card sheet {turn}, tray scrolled', f'card-{card}',
                lambda: click_field(page, f'data-cable-sheet-{card}'))
            assert before['scrollTop'] > 20, before['scrollTop']
    finally:
        page.evaluate("""() => {
            const d = document.getElementById('hardware-dock');
            d.style.height = '520px';
            if (typeof window.app.settleLayout === 'function') window.app.settleLayout();
            document.getElementById('hardware-dock-body').scrollTop = 0;
        }""")
        page.wait_for_timeout(500)


def test_the_power_tray_holds_still_through_every_interaction(tray):
    """The audit, power side - the "need to make sure this doesnt happen in
    power either" half. The distros deal into columns; a column is a cell,
    and nothing a multi does changes any column's x or width."""
    page, ids = tray
    open_view(page, 'power')
    d = ids['distros'][0]
    shot = page.evaluate(CELLS_JS)
    print('\npower tray:', json.dumps(shot['cells']))
    assert shot['display'] == 'grid', shot['display']
    key = f'distro-{d}'
    # a multi's power sheet
    for turn in ('open', 'close'):
        audit(page, f'multi sheet {turn}', key,
              lambda: click_field(page, f'power-cable-sheet-{d}-1'))
    # a multi folds
    for turn in ('fold', 'unfold'):
        audit(page, f'{turn} multi', key,
              lambda: fold_arrow(page, f'hwdock-multi-{d}-1'))
    # the distro folds
    for turn in ('fold', 'unfold'):
        audit(page, f'{turn} distro', key,
              lambda: fold_arrow(page, f'hwdock-distro-{d}'))
    # a home-run length typed on the occupied multi

    def length(to):
        f = page.locator(
            f'[data-lrd-field="power-soca-length-{ids["aId"]}-{ids["soca"]}"]')
        f.fill(to)
        f.press('Tab')
    audit(page, 'type a length', key, lambda: length('125'), 1100)
    audit(page, 'clear the length', key, lambda: length(''), 1100)
    # the type chip on the spare multi cycles
    audit(page, 'flip the type chip', key,
          lambda: click_field(page, f'distro-box-type-{d}-2'), 900)
    audit(page, 'flip the type chip back', key,
          lambda: click_field(page, f'distro-box-type-{d}-2'), 900)


def _drag(page, x1, y1, x2, y2):
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=6)
    page.mouse.move(x2, y2, steps=6)
    page.wait_for_timeout(120)
    mark = page.evaluate("""() => {
        const m = document.querySelector('#hardware-dock-body > .hw-dock-drop-mark');
        if (!m) return null;
        const r = m.getBoundingClientRect();
        return {index: m.dataset.lrdIndex, x: r.left, w: r.width,
                colour: getComputedStyle(m).backgroundColor};
    }""")
    page.mouse.up()
    page.wait_for_timeout(900)
    return mark


def _head_point(page, key):
    """The middle of the header's GRIP - the ⋮⋮ every draggable header
    wears. Anywhere else on the strip may be a control (the name field,
    the redundancy pill, the ⚙), and a press on a control is that
    control's gesture, never a pickup. Scrolled into view first: a header
    below the tray's fold has a bounding box but nothing under the
    cursor."""
    head = page.locator(f'[data-hwdock="{key}"]')
    head.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    grip = head.locator('.hw-dock-grip').first
    box = (grip if grip.count() else head).bounding_box()
    assert box, f'no header {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def test_a_processor_drags_along_the_tray_to_reorder(tray):
    """Drag the pair's header to the front: an accent bar marks the gap it
    would land in, the drop moves the processor - with the backup it is
    paired to - in the STORED order, the tray follows, and so do the
    binder's 'data' screen order and its hardware sheets. Undo puts it
    back."""
    page, ids = tray
    open_view(page, 'data-flow')
    order = page.evaluate(STORED_ORDER_JS)
    assert order == [ids['djId'], ids['imagAId'], ids['imagBId']], order
    assert page.evaluate(TRAY_ORDER_JS) == order
    page.evaluate("""() => window.app.setBinderField(
        'screenOrder', 'data', 'Set Screen Order')""")
    page.wait_for_timeout(300)
    screens = lambda: page.evaluate(  # noqa: E731
        """() => window.app.planBinder(%s)""" % BINDER_OPTS)
    before = screens()
    data_before = [p['subject'] for p in before if p['kind'] == 'power']
    hw_before = [p['subject'] for p in before if p['kind'] == 'processor']
    assert data_before == ['WALL A', 'WALL B'], data_before
    index = page.evaluate(HIST_JS)['index']
    # drag processor 3's header (the pair's backup - a pair moves with its
    # main) to the far left of the tray
    x1, y1 = _head_point(page, f'processor-{ids["imagBId"]}')
    body = page.locator('#hardware-dock-body').bounding_box()
    mark = _drag(page, x1, y1, body['x'] + 6, body['y'] + 40)
    print('\nmarker:', json.dumps(mark))
    assert mark and mark['index'] == '0', mark
    assert abs(mark['w'] - 3) < 0.6, mark
    after = page.evaluate(STORED_ORDER_JS)
    assert after == [ids['imagAId'], ids['imagBId'], ids['djId']], after
    assert page.evaluate(TRAY_ORDER_JS) == after
    hist = page.evaluate(HIST_JS)
    assert hist['action'] == 'Reorder Processors' \
        and hist['index'] == index + 1, hist
    moved = screens()
    assert [p['subject'] for p in moved if p['kind'] == 'power'] \
        == ['WALL B', 'WALL A'], moved
    hw_after = [p['subject'] for p in moved if p['kind'] == 'processor']
    assert hw_after != hw_before, (hw_before, hw_after)
    assert hw_after[0].startswith('IMAG A'), hw_after
    page.evaluate('() => window.app.undo()')
    page.wait_for_timeout(1400)
    back = page.evaluate(STORED_ORDER_JS)
    assert back == [ids['djId'], ids['imagAId'], ids['imagBId']], back
    assert page.evaluate(TRAY_ORDER_JS) == back
    page.evaluate("""() => window.app.setBinderField(
        'screenOrder', 'alpha', 'Set Screen Order')""")
    page.wait_for_timeout(400)


def test_a_distro_drags_along_the_tray_to_reorder(tray):
    """The same gesture on the power side: the distro's header drags along
    the tray, the marker names the gap, the drop reorders the project's
    distros in ONE 'Reorder Distros' entry, and undo restores them."""
    page, ids = tray
    open_view(page, 'power')
    order = page.evaluate(DISTRO_ORDER_JS)
    assert order == ids['distros'], order
    index = page.evaluate(HIST_JS)['index']
    x1, y1 = _head_point(page, f'distro-{ids["distros"][2]}')
    body = page.locator('#hardware-dock-body').bounding_box()
    mark = _drag(page, x1, y1, body['x'] + 6, body['y'] + 40)
    print('\ndistro marker:', json.dumps(mark))
    assert mark and mark['index'] == '0', mark
    after = page.evaluate(DISTRO_ORDER_JS)
    assert after == [ids['distros'][2], ids['distros'][0],
                     ids['distros'][1]], after
    hist = page.evaluate(HIST_JS)
    assert hist['action'] == 'Reorder Distros' \
        and hist['index'] == index + 1, hist
    page.evaluate('() => window.app.undo()')
    page.wait_for_timeout(1400)
    assert page.evaluate(DISTRO_ORDER_JS) == ids['distros']


def test_a_drag_that_ends_on_the_canvas_still_assigns(tray):
    """The reorder is the tray's meaning of the gesture and nothing else's:
    a card header dropped on a screen assigns its ports exactly as before,
    and a processor's own strip dropped on a screen does what its first
    card does."""
    page, ids = tray
    open_view(page, 'data-flow')
    page.evaluate("""async (ids) => {
        await window.app._assignmentRequest('/api/port-assignments/unpin',
            'POST', {layerId: String(ids.bId)});
    }""", ids)
    page.wait_for_timeout(700)
    pins = page.evaluate(
        "(id) => ((window.app.project.port_assignments || {}).pins || [])"
        ".filter(p => String(p.layerId) === String(id)).length", ids['bId'])
    assert pins == 0, pins
    pt = page.evaluate("""(id) => {
        const app = window.app, r = window.canvasRenderer;
        const layer = app.project.layers.find(l => l.id === id);
        const p = layer.panels[0];
        const {dx, dy} = r.getLayerRenderOffset(layer);
        const off = r._layerCanvasOffset(layer);
        const rect = r.canvas.getBoundingClientRect();
        return {x: rect.left + (p.x + p.width / 2 + dx + off.wx) * r.zoom + r.panX,
                y: rect.top + (p.y + p.height / 2 + dy + off.wy) * r.zoom + r.panY};
    }""", ids['bId'])
    x1, y1 = _head_point(page, f'processor-{ids["imagAId"]}')
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + pt['x']) / 2, (y1 + pt['y']) / 2, steps=6)
    page.mouse.move(pt['x'], pt['y'], steps=6)
    page.mouse.up()
    page.wait_for_timeout(1200)
    pins = page.evaluate(
        "(id) => ((window.app.project.port_assignments || {}).pins || [])"
        ".filter(p => String(p.layerId) === String(id)).length", ids['bId'])
    assert pins > 0, 'a processor dropped on a screen assigned nothing'


def test_the_order_route_takes_a_permutation_and_nothing_else(client):
    """PUT /api/processors/order is the whole order or a refusal: a short
    list, a repeat or an unknown id is 400 and stores nothing."""
    a = client.post('/api/processors',
                    json={'deviceId': 'novastar-h9'}).get_json()
    b = client.post('/api/processors',
                    json={'deviceId': 'novastar-h9'}).get_json()
    ids = [p['id'] for p in b['processors']]
    assert len(ids) == 2, ids
    for bad in ([ids[0]], [ids[0], ids[0]], ids + ['nope'], 'x', [1, 2]):
        r = client.put('/api/processors/order', json={'ids': bad})
        assert r.status_code == 400, (bad, r.status_code)
    assert [p['id'] for p in
            client.get('/api/processors').get_json()['processors']] == ids
    r = client.put('/api/processors/order', json={'ids': ids[::-1]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert [p['id'] for p in r.get_json()['processors']] == ids[::-1]
    assert [p['id'] for p in
            client.get('/api/processors').get_json()['processors']] \
        == ids[::-1]
    assert a is not None
