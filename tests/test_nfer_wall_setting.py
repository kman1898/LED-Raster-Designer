"""A grouped wall shares ONE splitter setting, and a wide circuit splits
into its own legs.

The owner's rulings, 2026-10-19, from a three-screen group show built on
1.5.3-beta.1 (the shape is rebuilt here in generic form: three members,
150 W cabinets on 208 V x 20 A, a half-height top row, the first member
with sharing off and the other two with it on, and old circuits that are
each ONE run covering three columns):

1. In a group, "Share circuits via splitters" - the enabled flag AND the
   splitter size - is ONE setting for the whole wall, in auto and custom:
   "when grouped they should be sharing that setting". Ticking or
   changing it on any member writes every member in one history entry,
   and the sidebar shows the wall's value whichever member is selected.
   Members that disagree (an old file) read the first member's setting;
   the file is not rewritten until the setting is touched. A locked
   member blocks the change for the whole wall and is named.
   (Before: the box wrote only the selected screens and showed the
   selected screen's own flag, while the custom fill read the wall
   owner's - so a member showing "on" filled one 15-cabinet run.)
2. A circuit drawn as ONE run across several columns (rows, on a wall
   cabled across) becomes a 2fer / 3fer of a run per column on the SAME
   circuit: right-click > "3fer it", or Alt pick it and right-click, in
   custom, on a taken-over circuit and on an automatic one. The one entry
   is the circuit's own Nfer - ways = its columns, never a smaller size,
   whatever the splitter size - offered only while its load fits the
   amps; refused with the reason otherwise.
   2b. The batch ("3fer this screen") and the Alt-sweep share verbs apply
   the same model to custom circuits: a wide circuit splits into its own
   legs and is never joined with a neighbour; single-column circuits
   still join into Nfers.

Run locally:
    python -m pytest tests/test_nfer_wall_setting.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, alt_click, alt_sweep, menu_at, take,
    fill, circuits, gangs, manual, history,
)


# Old-file shape: three members, A (6 columns) owns circuit 1, B holds
# circuits 2-6 drawn across all three screens - each a single run of three
# columns snaking top-down, except circuit 4, one column - and C holds
# nothing. All custom. Top row half height when `half` is set.
OLD_WALL_JS = """async ([a, b, c, half]) => {
    const app = window.app;
    if (half) {
        // Half-height cabinets are the server's geometry: set them there.
        await app._layerSavesSettled();
        const p = await window.__nf.j('GET', '/api/project');
        p.layers.forEach(l => { if ([a, b, c].includes(l.id)) l.panels.forEach(q => {
            if (q.row === 0) q.halfTile = 'height'; }); });
        await window.__nf.j('PUT', '/api/project', p);
        const fresh = await window.__nf.j('GET', '/api/project');
        fresh.layers.forEach(fl => { const l = window.__nf.layer(fl.id);
            if (l) l.panels = fl.panels; });
    }
    const A = window.__nf.layer(a), B = window.__nf.layer(b), C = window.__nf.layer(c);
    const snake = (cols, lid) => cols.flatMap((col, i) => {
        const rows = i % 2 ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
        return rows.map(r => Object.assign({ row: r, col }, lid ? { layerId: lid } : {}));
    });
    [A, B, C].forEach(l => {
        l.powerFlowPattern = 'custom';
        l.lastPowerFlowPattern = 'tl-v';
    });
    A.powerCustomPaths = { 1: snake([0, 1, 2]) };
    A.powerCustomIndex = 1;
    B.powerCustomPaths = { 2: snake([3, 4, 5], a), 3: snake([0, 1, 2]),
                           4: snake([3]), 5: snake([0, 1, 2], c),
                           6: snake([3, 4, 5], c) };
    B.powerCustomIndex = 6;
    C.powerCustomPaths = {};
    app._circuitTailCache = null;
    app.updateLayers([A, B, C]);
    app.renderLayers();
    app.resetHistory('Old file');
}"""

SHARING_OFF = {'powerSplitters': {'enabled': False, 'maxWays': 3,
                                  'manual': {'merge': [], 'split': []}}}


def three(page, a_props=None, b_props=None, c_props=None):
    """A three-member group: A (6 columns, sharing OFF), B (4 columns) and
    C (6 columns), both sharing on."""
    close_menu(page)
    return make(page, [
        {'name': 'A', 'columns': 6, 'props': dict(SHARING_OFF, **(a_props or {}))},
        {'name': 'B', 'columns': 4, 'x': 1200, 'props': b_props or {}},
        {'name': 'C', 'columns': 6, 'x': 2000, 'props': c_props or {}},
    ], group=True)


def old_wall(page, half=True, **kw):
    ids = three(page, **kw)
    page.evaluate(OLD_WALL_JS, [*ids, half])
    landed(page)
    return ids


def close_menu(page):
    """A menu left open by the test before must not catch this one's clicks."""
    page.evaluate("() => window.app.hideContextMenu()")


def select(page, *ids):
    page.evaluate("""(ids) => {
        const app = window.app;
        const l = window.__nf.layer(ids[0]);
        app.currentLayer = l;
        app.selectedLayerIds = new Set(ids);
        app.lastSelectedLayerId = ids[0];
        app.loadLayerToInputs();
        app.refreshSplitterPanel();
        app.updateCustomPowerUI && app.updateCustomPowerUI();
    }""", list(ids))
    landed(page)


def raw(page, ids):
    """Each member's STORED splitter setting, not the wall's read."""
    return page.evaluate("""(ids) => ids.map(id => {
        const s = window.__nf.layer(id).powerSplitters || {};
        return [!!s.enabled, s.maxWays];
    })""", list(ids))


def box(page):
    return page.evaluate("""() => {
        const en = document.getElementById('power-splitters-enabled');
        const mw = document.getElementById('power-splitters-maxways');
        return { checked: en.checked, ways: mw.value };
    }""")


def catch_locked(page):
    page.evaluate("""() => { window.__nf.errors = [];
        window.app._showLockedError = (ls) => { if (ls && ls.length)
            window.__nf.errors.push(window.app._lockedErrorNames(ls)); }; }""")


# ── 1. one splitter setting per wall ──────────────────────────────────────

def test_the_wall_reads_its_first_members_setting(page):
    """The old file: A sharing off, B and C on. Whichever member is
    selected, the box shows the wall's value - A's, off - and the app
    reads it so; nothing is rewritten by opening or selecting."""
    a, b, c = old_wall(page)
    for m in (a, b, c):
        select(page, m)
        assert box(page)['checked'] is False, (
            f'member {m} must show the wall setting (off): {box(page)}')
        assert page.evaluate("(id) => window.app.getPowerSplitters("
                             "window.__nf.layer(id)).enabled", m) is False
    assert raw(page, [a, b, c]) == [[False, 3], [True, 3], [True, 3]], (
        'an old file opens unchanged until the setting is touched')


def test_ticking_the_box_on_one_member_sets_the_whole_wall(page):
    """B alone selected, the box ticked: all three members share - one
    history entry, saved to the server. The size picked on C reaches A
    and B; one undo puts the size back on every member."""
    a, b, c = old_wall(page)
    select(page, b)
    h0 = len(history(page))
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 3]] * 3, raw(page, [a, b, c])
    assert history(page)[h0:] == ['Change Splitter Packing'], history(page)
    saved = page.evaluate("""async (ids) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        return ids.map(id => !!(p.layers.find(l => l.id === id)
            .powerSplitters || {}).enabled);
    }""", [a, b, c])
    assert saved == [True, True, True], saved

    select(page, c)
    page.evaluate("""() => {
        const mw = document.getElementById('power-splitters-maxways');
        mw.value = '2';
        mw.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 2]] * 3, raw(page, [a, b, c])
    select(page, a)
    assert box(page) == {'checked': True, 'ways': '2'}, box(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 3]] * 3, raw(page, [a, b, c])


def test_a_locked_member_blocks_the_wall_setting(page):
    """C locked, its own flag off: ticking the box on B would change C, so
    no member changes, C is named, and the box snaps back to the wall's
    value. A locked member already holding the new value blocks nothing."""
    a, b, c = old_wall(page, c_props=dict(SHARING_OFF, locked=True))
    catch_locked(page)
    select(page, b)
    h0 = len(history(page))
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[False, 3], [True, 3], [False, 3]], (
        raw(page, [a, b, c]))
    assert len(history(page)) == h0, history(page)
    assert ['C'] in page.evaluate("() => window.__nf.errors")
    assert box(page)['checked'] is False

    # Round 6: C locked and A, B not is a half-locked group (an old
    # file's), locked as a whole until the user picks Lock or Unlock, so
    # even with C already holding the new value nothing changes.
    a, b, c = old_wall(page, c_props={'locked': True})
    catch_locked(page)
    select(page, b)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[False, 3], [True, 3], [True, 3]], raw(page, [a, b, c])
    assert ['C'] in page.evaluate("() => window.__nf.errors")


def test_a_custom_fill_on_a_member_follows_the_box_it_shows(page):
    """Custom group, nothing drawn, A sharing off: B selected shows the
    box off; ticked there, a three-column fill on B is ONE 3fer of three
    column runs (it used to tick B only, and the fill - which reads the
    wall's owner, A - poured one 15-cabinet run)."""
    a, b, c = three(page)
    page.evaluate("""(ids) => {
        const app = window.app;
        ids.forEach(id => { const l = window.__nf.layer(id);
            l.powerFlowPattern = 'custom'; });
        app.updateLayers(ids.map(id => window.__nf.layer(id)));
        app.resetHistory('Custom');
    }""", [a, b, c])
    landed(page)
    select(page, b)
    assert box(page)['checked'] is False, box(page)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert fill(page, [(b, 0, 2)])
    out = circuits(page, a)
    assert [(c_['num'], c_['runs']) for c_ in out] == [(1, [5, 5, 5])], out
    assert out[0]['on'] == [b], out
    assert gangs(page, a) == [{'num': 1, 'ways': 3, 'over': False}]


def test_an_auto_group_packs_every_member_by_the_wall_setting(page):
    """An auto group of two wattages (each member packs alone): A sharing
    off, B on. B packs by the wall's setting - plain circuits - and
    ticking the box on B shares both."""
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 1000,
                        'props': {'panelWatts': 100}}], group=True)
    assert all(len(c_['runs']) == 1 for c_ in circuits(page, b)), (
        f'B must follow the wall (sharing off): {circuits(page, b)}')
    select(page, b)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert any(len(c_['runs']) > 1 for c_ in circuits(page, a)), circuits(page, a)
    assert any(len(c_['runs']) > 1 for c_ in circuits(page, b)), circuits(page, b)


# ── 2. a wide circuit becomes a 2fer / 3fer of its own legs ───────────────
#
# The owner's ruling, 2026-10-19: "i am taking 3 columns and 1 port and
# making it 3fer the single port. across 3 columns. which is how auto has
# worked this whole time". A circuit that is ONE run across several columns
# (rows, on a wall cabled across) becomes one circuit split into legs, one
# run per column, on the SAME circuit: right-click > "3fer it", or Alt pick
# the circuit and right-click. Ways = its columns, capped at the splitter
# size, and only while the circuit's load fits the amps OVER reads.

NFER_IT_JS = """() => {
    const menu = document.getElementById('context-menu');
    const el = menu && menu.querySelector('[data-action="hw-nfer-it"]');
    if (!el || menu.style.display !== 'block' || el.style.display === 'none') return null;
    return { label: (el.textContent || '').trim(), title: el.title,
             disabled: el.classList.contains('menu-disabled') };
}"""

# A single custom screen whose circuits are drawn by hand: {num: [cols]},
# each run snaking top-down through its columns.
WIDE_JS = """([id, runs, props]) => {
    const app = window.app, l = window.__nf.layer(id);
    const snake = (cols) => cols.flatMap((col, i) => {
        const rows = i % 2 ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
        return rows.map(r => ({ row: r, col }));
    });
    l.powerFlowPattern = 'custom';
    l.powerCustomPaths = {};
    Object.keys(runs).forEach(n => { l.powerCustomPaths[n] = snake(runs[n]); });
    l.powerCustomIndex = Math.max(...Object.keys(runs).map(Number));
    Object.assign(l, props || {});
    app._circuitTailCache = null;
    app.updateLayers([l]);
    app.loadLayerToInputs();
    app.resetHistory('Drawn');
}"""

TEN = {1: [0, 1, 2], 2: [3, 4, 5], 3: [6, 7, 8], 4: [9]}


def wide(page, runs=None, columns=10, props=None, **kw):
    close_menu(page)
    (wall,) = make(page, [{'name': 'Wall', 'columns': columns}], **kw)
    page.evaluate(WIDE_JS, [wall, {str(k): v for k, v in (runs or TEN).items()},
                            props or {}])
    landed(page)
    return wall


def nfer_item(page, p):
    page.mouse.click(p['x'], p['y'], button='right')
    landed(page)
    return page.evaluate(NFER_IT_JS)


def cols_of(page, layer_id):
    """Each drawn run's columns: {num: [[layerId, col], ...]}."""
    return page.evaluate("""(id) => {
        const p = window.__nf.layer(id).powerCustomPaths || {};
        const out = {};
        Object.keys(p).forEach(n => { if ((p[n] || []).length) out[n] =
            [...new Set(p[n].map(e => (e.layerId || id) + ':' + e.col))]; });
        return out;
    }""", layer_id)


def labels(page, layer_id, nums):
    return page.evaluate("([id, ns]) => { window.app._circuitTailCache = null;"
                         " return ns.map(n => window.app.getPowerCircuitLabel("
                         "window.__nf.layer(id), n)); }", [layer_id, nums])


def test_3fer_it_splits_one_wide_custom_circuit_into_its_columns(page):
    """Custom, circuit 2 one run of columns 3-5: right-click > "3fer it"
    makes it ONE circuit of three single-column runs, still circuit 2 and
    still the same label; the circuits after it keep their labels and
    their typed labels. One history entry; one undo puts it back."""
    wall = wide(page, props={'powerLabelOverrides': {'3': 'KEEP'}})
    before = circuits(page, wall)
    names = labels(page, wall, [1, 2, 4])
    h0 = len(history(page))
    item = nfer_item(page, pt(page, wall, 2, 4))
    assert item == {'label': '3fer it (3 column runs)', 'disabled': False,
                    'title': item and item['title']}, item
    take(page, 'hw-nfer-it')
    out = circuits(page, wall)
    assert [(c['num'], c['runs']) for c in out] == [
        (1, [15]), (2, [5, 5, 5]), (5, [15]), (6, [5])], out
    assert out[1]['runIds'] == [2, 3, 4], out
    assert cols_of(page, wall) == {
        '1': [f'{wall}:0', f'{wall}:1', f'{wall}:2'], '2': [f'{wall}:3'],
        '3': [f'{wall}:4'], '4': [f'{wall}:5'],
        '5': [f'{wall}:6', f'{wall}:7', f'{wall}:8'], '6': [f'{wall}:9']}
    assert gangs(page, wall) == [{'num': 2, 'ways': 3, 'over': False}]
    assert labels(page, wall, [1, 2, 6]) == names, 'every circuit keeps its name'
    assert labels(page, wall, [5]) == ['KEEP']
    assert history(page)[h0:] == ['3fer Circuit'], history(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert circuits(page, wall) == before


def test_nfer_it_is_refused_with_the_reason(page):
    """A single column, or a circuit over the amps: the entry stays on the
    menu disabled with the reason, and a click writes nothing."""
    wall = wide(page, runs={1: [0, 1, 2, 3], 2: [4, 5, 6], 3: [7]})
    one = nfer_item(page, pt(page, wall, 2, 7))
    assert one and one['disabled'] and 'one column' in one['title'], one
    h0 = len(history(page))
    take(page, 'hw-nfer-it')
    assert len(history(page)) == h0 and manual(page, wall)['merge'] == []

    wall = wide(page, props={'powerAmperage': 12.5})
    over = nfer_item(page, pt(page, wall, 2, 4))
    assert over and over['disabled'], over
    assert over['label'] == '3fer it (3 column runs)', over
    assert '10.8 A on a 12.5 A circuit held to 10 A (80%)' in over['title'], over
    take(page, 'hw-nfer-it')
    assert [c['runs'] for c in circuits(page, wall)] == [[15]] * 3 + [[5]]


def test_each_circuit_offers_only_the_nfer_its_columns_make(page):
    """The owner's ruling, 2026-10-19: "three columns on one port, the
    only option available should be a three fer. if 2 then only a 2 fer.
    if 4 then 4 fer etc." Two, three and four columns each offer exactly
    their own Nfer - four columns at the 3fer splitter size too: one
    circuit's split follows its columns, the splitter size caps auto
    packing and the batch. The 4fer tags "4fer" and the pull sheet counts
    a 4fer."""
    wall = wide(page, columns=9, runs={1: [0, 1], 2: [2, 3, 4], 3: [5, 6, 7, 8]})
    for col, n in ((1, 2), (3, 3), (6, 4)):
        item = nfer_item(page, pt(page, wall, 2, col))
        assert item == {'label': f'{n}fer it ({n} column runs)', 'disabled': False,
                        'title': item and item['title']}, (n, item)
        texts = page.evaluate("""() => [...document.querySelectorAll(
            '#context-menu .menu-option')].filter(el => el.style.display !== 'none')
            .map(el => (el.textContent || '').trim()).filter(t => / it [(]/.test(t))""")
        assert texts == [f'{n}fer it ({n} column runs)'], texts
    take(page, 'hw-nfer-it')
    four = [c for c in circuits(page, wall) if len(c['runs']) == 4]
    assert len(four) == 1 and four[0]['runs'] == [5, 5, 5, 5], circuits(page, wall)
    assert gangs(page, wall) == [{'num': four[0]['num'], 'ways': 4, 'over': False}]
    assert page.evaluate("() => window.__nf.tags()").count('4fer') == 1
    pull = page.evaluate("""(id) => {
        window.app._circuitTailCache = null;
        const scr = window.app.buildPullList().byScreen[id];
        return { gangs: scr.gangs, rows: scr.rows.map(r => r.type) };
    }""", wall)
    assert pull['gangs'] == {'twofer': 0, 'threefer': 0, 'wider': {'4': 1}}, pull
    assert any(t.endswith(' 4fer') for t in pull['rows']), pull
    assert not any(t.endswith(' 3fer') for t in pull['rows']), pull


def test_2fer_it_on_a_wall_cabled_across_makes_row_runs(page):
    """A custom circuit snaking across rows 0-1 of a four-column wall is a
    2fer of two row runs; maxWays 2 caps nothing here."""
    close_menu(page)
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4}], maxWays=2)
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        l.powerFlowPattern = 'custom'; l.lastPowerFlowPattern = 'tl-h';
        l.powerCustomPaths = { 1: [0, 1, 2, 3].map(c => ({ row: 0, col: c }))
            .concat([3, 2, 1, 0].map(c => ({ row: 1, col: c }))) };
        app.updateLayers([l]);
        app.resetHistory('Drawn');
    }""", wall)
    landed(page)
    item = nfer_item(page, pt(page, wall, 0, 1))
    assert item and item['label'] == '2fer it (2 row runs)' and not item['disabled'], item
    take(page, 'hw-nfer-it')
    assert [c['runs'] for c in circuits(page, wall)] == [[4, 4]]


def test_alt_click_then_right_click_makes_that_circuit_a_3fer(page):
    """Custom: Alt+click picks circuit 2 (the active circuit), and the
    right-click on it offers "3fer it"."""
    wall = wide(page)
    alt_click(page, pt(page, wall, 0, 4))
    assert page.evaluate("() => window.app.currentLayer.powerCustomIndex") == 2
    item = nfer_item(page, pt(page, wall, 0, 4))
    assert item and item['label'] == '3fer it (3 column runs)', item
    take(page, 'hw-nfer-it')
    assert circuits(page, wall)[1]['runs'] == [5, 5, 5]


def test_a_one_circuit_alt_sweep_offers_3fer_it(page):
    """An Alt sweep that stays on one circuit picks just that circuit; the
    right-click offers "3fer it" for it (the menu used to show neither the
    share items nor a batch entry for a one-circuit pick)."""
    wall = wide(page)
    alt_sweep(page, pt(page, wall, 0, 3), pt(page, wall, 4, 3))
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and sel['nums'] == [2], sel
    item = nfer_item(page, pt(page, wall, 4, 3))
    assert item and item['label'] == '3fer it (3 column runs)', item
    take(page, 'hw-nfer-it')
    assert circuits(page, wall)[1]['runs'] == [5, 5, 5]


def _auto_wide(page):
    """Auto, sharing off, 12 A (80% of 15 A): whole columns packed three to a circuit -
    circuits 1-3 are wide runs of three columns, circuit 4 the last one."""
    close_menu(page)
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, powerAmperage=15)}])
    assert [c['runs'] for c in circuits(page, wall)] == [[15]] * 3 + [[5]]
    return wall


def test_3fer_it_on_a_taken_over_auto_circuit(page):
    """Auto: Alt+click takes circuit 2 over (one run of 15); right-click >
    "3fer it" marks its column heads - three runs on the one circuit,
    tagged 3fer, the marks saved - in its own history entry."""
    wall = _auto_wide(page)
    alt_click(page, pt(page, wall, 0, 4))
    page.keyboard.press('Escape')
    landed(page)
    h0 = len(history(page))
    item = nfer_item(page, pt(page, wall, 0, 4))
    assert item and item['label'] == '3fer it (3 column runs)' and not item['disabled'], item
    take(page, 'hw-nfer-it')
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5] and len(c2['runIds']) == 3, c2
    assert gangs(page, wall) == [{'num': 2, 'ways': 3, 'over': False}]
    assert history(page)[h0:] == ['3fer Circuit'], history(page)
    saved = page.evaluate("""async (id) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id);
        return (l.powerCustomPaths[2] || []).map(e => !!e.branch);
    }""", wall)
    assert [i for i, b in enumerate(saved) if b] == [5, 10], saved
    page.evaluate("() => window.app.undo()")
    landed(page)
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [15], c2


def test_3fer_it_on_an_untaken_auto_circuit_takes_it_over_split(page):
    """Auto, no Alt: right-click > "3fer it" on a packed wide circuit takes
    it over already split into its column runs - ONE history entry."""
    wall = _auto_wide(page)
    h0 = len(history(page))
    item = nfer_item(page, pt(page, wall, 0, 4))
    assert item and item['label'] == '3fer it (3 column runs)', item
    take(page, 'hw-nfer-it')
    assert page.evaluate("(id) => window.app.isRunOverridden("
                         "window.__nf.layer(id), 'power', 2)", wall)
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], c2
    assert history(page)[h0:] == ['3fer Circuit'], history(page)


def test_3fer_it_on_a_group_acts_on_the_walls_circuit(page):
    """The old three-screen file: B's circuit 3 (B's columns 0-2) is
    adopted into the wall's owner A and split there - one history entry."""
    a, b, c = old_wall(page)
    h0 = len(history(page))
    item = nfer_item(page, pt(page, b, 2, 1))
    assert item and item['label'] == '3fer it (3 column runs)', item
    take(page, 'hw-nfer-it')
    assert history(page)[h0:] == ['3fer Circuit'], history(page)
    assert '3' not in cols_of(page, b), cols_of(page, b)
    out = circuits(page, a)
    shared = [x for x in out if len(x['runs']) == 3]
    assert len(shared) == 1 and shared[0]['on'] == [b], out
    assert not any(g['over'] for g in gangs(page, a))


def test_3fer_it_on_a_locked_screen_is_refused(page):
    wall = wide(page, props={'locked': True})
    catch_locked(page)
    h0 = len(history(page))
    nfer_item(page, pt(page, wall, 2, 4))
    take(page, 'hw-nfer-it')
    assert len(history(page)) == h0
    assert [c['runs'] for c in circuits(page, wall)] == [[15]] * 3 + [[5]]
    assert ['Wall'] in page.evaluate("() => window.__nf.errors")


# ── 2b. the batch and the sweep split wide circuits into their legs ───────
#
# The owner's clarification, 2026-10-19: "3fer Screen" and the Alt-sweep
# share verbs apply the same model to custom circuits. A circuit that
# already spans several columns as one run is split into its own legs
# (ways = its columns, capped at the size picked, while the load fits) -
# never joined with its neighbours. Single-column circuits still join into
# Nfers the way auto packs columns.

def _batch_items(page, p):
    return menu_at(page, p)


def test_3fer_screen_on_the_old_group_makes_every_3_column_circuit_a_3fer(page):
    """The owner's three-screen shape: old single-run circuits of three
    columns (the top row half height) and one single column. "3fer this
    screen": every three-column circuit becomes a 3fer of its own three
    columns, none OVER, the single column stays plain - one history entry,
    adopted onto the wall's owner. (It used to pair the lone column with a
    neighbour - "only 2fers".) "2fer this screen" is disabled: no circuit
    here fits a 2fer and none is joined to another."""
    a, b, c = old_wall(page)
    items = _batch_items(page, pt(page, b, 2, 1))
    assert items['n0'] and items['n0']['disabled'], items
    assert 'columns' in items['n0']['title'], items
    assert items['n1'] and items['n1']['label'] == (
        '3fer this screen (5 × 3fer + 1 plain)'), items
    assert not items['n1']['disabled'], items
    h0 = len(history(page))
    take(page, 'hw-batch-n1')
    out = circuits(page, a)
    assert [x['runs'] for x in out] == [[5, 5, 5]] * 3 + [[5]] + [[5, 5, 5]] * 2, out
    cols = cols_of(page, a)
    assert all(len(v) == 1 for v in cols.values()), (
        f'every run is one column: {cols}')
    assert len(cols) == 16, cols
    assert [g['ways'] for g in gangs(page, a)] == [3] * 5, gangs(page, a)
    assert not any(g['over'] for g in gangs(page, a)), gangs(page, a)
    assert cols_of(page, b) == {} and cols_of(page, c) == {}
    assert history(page)[h0:] == ['3fer Screen'], history(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert sorted(cols_of(page, b), key=int) == ['2', '3', '4', '5', '6']


def test_a_sweep_over_wide_circuits_makes_each_its_own_3fer(page):
    """The same shape, a sweep from A's circuit 1 onto B's circuit 3:
    "3fer them" makes each of the three its own 3fer."""
    a, b, c = old_wall(page)
    alt_sweep(page, pt(page, a, 2, 1), pt(page, b, 2, 1))
    items = _batch_items(page, pt(page, b, 2, 1))
    assert items['n1'] and items['n1']['label'] == '3fer them (3 × 3fer)', items
    take(page, 'hw-batch-n1')
    out = circuits(page, a)
    assert [x['runs'] for x in out[:3]] == [[5, 5, 5]] * 3, out
    assert not any(g['over'] for g in gangs(page, a))


def test_3fer_screen_splits_wide_circuits_and_joins_single_columns(page):
    """One custom screen: columns 0 and 1 single, columns 2-4 one run,
    then three single columns. "3fer this screen": the two singles before
    the wide run pair up (the wide run breaks the line), the wide run is
    its own 3fer, the three singles after it join one 3fer."""
    wall = wide(page, columns=8, runs={1: [0], 2: [1], 3: [2, 3, 4], 4: [5],
                                       5: [6], 6: [7]})
    items = _batch_items(page, pt(page, wall, 2, 0))
    assert items['n1'] and items['n1']['label'] == (
        '3fer this screen (2 × 3fer + 1 × 2fer)'), items
    take(page, 'hw-batch-n1')
    assert [c['runs'] for c in circuits(page, wall)] == [[5, 5], [5, 5, 5], [5, 5, 5]]
    assert not any(g['over'] for g in gangs(page, wall))


# ── what the user reads: a custom Nfer wall numbers like auto ─────────────
#
# A shared custom circuit is several drawn run numbers (one per leg) under
# the first leg's number. Whatever the user reads - the circuit labels on
# the wall (a multi template like S1-# and a plain one like C#), the
# colour-coded view, the multis and tails in the tray and the binder, the
# pull sheet - must count the shared circuit ONCE, exactly as auto prints
# the same wall.

HALF_JS = """async (ids) => {
    const app = window.app;
    await app._layerSavesSettled();
    const p = await window.__nf.j('GET', '/api/project');
    p.layers.forEach(l => { if (ids.includes(l.id)) l.panels.forEach(q => {
        if (q.row === 0) q.halfTile = 'height'; }); });
    await window.__nf.j('PUT', '/api/project', p);
    const fresh = await window.__nf.j('GET', '/api/project');
    fresh.layers.forEach(fl => { const l = window.__nf.layer(fl.id);
        if (l) l.panels = fl.panels; });
    app._circuitTailCache = null;
    app.renderLayers();
}"""

SNAP_JS = """([id, tpl]) => {
    const app = window.app;
    app.project.layers.forEach(l => { if (l.group_id) l.powerLabelTemplate = tpl; });
    app._circuitTailCache = null;
    const l = window.__nf.layer(id);
    const cs = app.screenCircuits(l);
    const scr = app.buildPullList().byScreen[id] || {};
    return {
        labels: cs.map(c => app.getPowerCircuitLabel(l, c.num)),
        colors: cs.map(c => app.getPowerCircuitColor(l, c.num)),
        ways: cs.map(c => (c.runIds || [c.num]).length),
        boxes: (scr.boxes || []).map(b => (b.circuits || []).map(c => [c.label, c.tail, c.tiles])),
        gangRows: (scr.rows || []).filter(r => /fer$/.test(r.type)).map(r => [r.type, r.label]),
        gangs: scr.gangs,
    };
}"""

# The automatic wall's own layout, drawn as old single runs on the wall's
# owner A: columns 0-2, 3-5 (A), 6-8 (B 0-2), 9-11 (B 3, C 0-1), 12-14
# (C 2-4) and the lone 15 (C 5), each run snaking top-down.
AUTO_LAYOUT_JS = """([a, b, c]) => {
    const app = window.app;
    const A = window.__nf.layer(a), B = window.__nf.layer(b), C = window.__nf.layer(c);
    const at = (w) => (w < 6 ? [null, w] : (w < 10 ? [b, w - 6] : [c, w - 10]));
    const snake = (cols) => cols.flatMap((w, i) => {
        const rows = i % 2 ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
        const [lid, col] = at(w);
        return rows.map(r => Object.assign({ row: r, col }, lid ? { layerId: lid } : {}));
    });
    [A, B, C].forEach(l => { l.powerFlowPattern = 'custom'; l.powerCustomPaths = {}; });
    A.powerCustomPaths = { 1: snake([0, 1, 2]), 2: snake([3, 4, 5]), 3: snake([6, 7, 8]),
                           4: snake([9, 10, 11]), 5: snake([12, 13, 14]), 6: snake([15]) };
    A.powerCustomIndex = 6;
    app._circuitTailCache = null;
    app.updateLayers([A, B, C]);
    app.renderLayers();
    app.resetHistory('Old file');
}"""


def test_a_custom_nfer_wall_reads_like_the_same_wall_in_auto(page):
    close_menu(page)
    a, b, c = make(page, [{'name': 'A', 'columns': 6},
                          {'name': 'B', 'columns': 4, 'x': 1200},
                          {'name': 'C', 'columns': 6, 'x': 2000}], group=True)
    page.evaluate(HALF_JS, [a, b, c])
    landed(page)
    auto = {t: page.evaluate(SNAP_JS, [a, t]) for t in ('S1-#', 'C#')}
    assert auto['S1-#']['ways'] == [3, 3, 3, 3, 3, 1], auto
    page.evaluate(AUTO_LAYOUT_JS, [a, b, c])
    landed(page)
    menu_at(page, pt(page, a, 2, 0))
    take(page, 'hw-batch-n1')
    for t in ('S1-#', 'C#'):
        custom = page.evaluate(SNAP_JS, [a, t])
        assert custom == auto[t], (t, custom, auto[t])


def test_a_split_feeds_every_leg_from_the_same_end_like_auto(page):
    """A snaking run of three columns split into a 3fer: every leg starts
    at the top, where the automatic wall feeds its column runs - not up the
    middle column the way the snake ran."""
    wall = wide(page)
    nfer_item(page, pt(page, wall, 2, 4))
    take(page, 'hw-nfer-it')
    heads = page.evaluate("""(id) => {
        const p = window.__nf.layer(id).powerCustomPaths;
        return [2, 3, 4].map(n => [p[n][0].row, p[n][p[n].length - 1].row]);
    }""", wall)
    assert heads == [[0, 4]] * 3, heads


DRAWN_LABELS_JS = """(ids) => {
    const app = window.app;
    const l = window.__nf.layer(ids[0]);
    const asked = [];
    const real = app.getPowerCircuitLabel;
    app.getPowerCircuitLabel = function (layer, num) {
        if (layer && ids.includes(layer.id)) asked.push(parseInt(num, 10));
        return real.apply(this, arguments);
    };
    app._circuitTailCache = null;
    try { window.canvasRenderer.render(); } finally { app.getPowerCircuitLabel = real; }
    return { asked: [...new Set(asked)].sort((x, y) => x - y),
             circuits: app.screenCircuits(l).map(c => c.num) };
}"""


def test_a_grouped_custom_3fer_on_a_peer_draws_as_one_circuit(page):
    """The owner's wall after "3fer this screen" (2026-10-20): every 3fer
    whose legs sit on a group peer - wholly on B, or across B and C - draws
    ONE bubble under its circuit's number. It drew every leg as a circuit
    of its own, each printing its own raw leg number: S2-2, S2-2, S2-3 ...
    and an S3-4 on a wall of 15 circuits."""
    close_menu(page)
    a, b, c = make(page, [{'name': 'A', 'columns': 6},
                          {'name': 'B', 'columns': 4, 'x': 1200},
                          {'name': 'C', 'columns': 6, 'x': 2000}], group=True)
    page.evaluate(AUTO_LAYOUT_JS, [a, b, c])
    landed(page)
    menu_at(page, pt(page, a, 2, 0))
    take(page, 'hw-batch-n1')
    assert [x['runs'] for x in circuits(page, a)] == [[5, 5, 5]] * 5 + [[5]]
    drawn = page.evaluate(DRAWN_LABELS_JS, [a, b, c])
    assert drawn['asked'] == drawn['circuits'], drawn
