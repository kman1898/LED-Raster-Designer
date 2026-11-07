"""Custom power after the full audit (the owner's rulings, 2026-10-21).

1. "Share with next run" in custom joins only single-run circuits: a 2fer
   or 3fer, or a circuit drawn across several columns, never joins a
   neighbor (ruling 12, 2026-10-19). The entry stays on the menu,
   disabled, with the reason; "Nfer it" splits a wide one.
2. Custom Clear Circuit on a 2fer / 3fer clears the WHOLE circuit, every
   leg, as one history entry.
4. "Remove 3fers from this screen" on a locked custom group names the
   locked screen, as "Remove 3fer" does (it failed silently).
5. A custom wall of 3fers reads by CIRCUIT: the active-circuit field
   shows 4 after a 10-column fill (not the drawn 10), Next / Prev step
   circuit by circuit, a typed 5 is the fifth circuit, and refusals name
   labels ("circuit S1-2", "S1-1 and S1-2"), never drawn numbers.
7. "2fer / 3fer this screen" also ticks "Share circuits via splitters",
   in the same history entry; the batch respects the Max splitter (no
   "4fer this screen" at 3fer), and Share with next in auto never builds
   past it.
9. The "Remove 3fer" hover in custom says nothing about auto packing, and
   the share menu hovers use no " - " dash.

The synthetic wall is the nfer module's: 150 W cabinets, 5 rows, 208 V x
20 A, cabled top-down, sharing at 3fer.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_rulings_1021.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, menu_at, take, custom_on, fill,
    circuits, manual, history,
)


def col(c):
    return [{'row': r, 'col': c} for r in range(5)]


def drawn(page, layer_id, paths):
    """Seed a custom screen's drawn runs ({num: [entries]}) as a file holds
    them, one history baseline."""
    page.evaluate("""([id, paths]) => {
        const app = window.app, l = window.__nf.layer(id);
        l.powerCustomPaths = paths;
        app._circuitTailCache = null;
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", [layer_id, paths])
    landed(page)


SHARE_AT_JS = """([x, y]) => {
    const app = window.app;
    app._sweepSelection = null;
    app._circuitTailCache = null;
    const m = app._prepareShareMenus(x, y);
    const one = (s) => s ? { label: s.label, disabled: !!s.disabled,
                             title: s.title || '', runnable: typeof s.run === 'function' } : null;
    const nfer = app._prepareNferItMenu(x, y);
    return { share: one(m.share), unshare: one(m.unshare), nfer: one(nfer) };
}"""


def share_at(page, p):
    return page.evaluate(SHARE_AT_JS, [p['x'], p['y']])


def labels(page, layer_id):
    return page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app._circuitTailCache = null;
        return app.screenCircuits(l).map(c => app.getPowerCircuitLabel(l, c.num));
    }""", layer_id)


def active(page):
    """The active-circuit field and the drawn number under it."""
    return page.evaluate("""() => ({
        shown: document.getElementById('power-custom-active').value,
        index: window.app.powerPathOwner(window.app.currentLayer).powerCustomIndex,
    })""")


def errors_on(page):
    page.evaluate("""() => {
        window.__r2 = { toasts: [], locked: [] };
        const app = window.app;
        const realToast = app._toast.bind(app);
        app._toast = (m, err, ms) => { if (err) window.__r2.toasts.push(m); return realToast(m, err, ms); };
        app._showLockedError = (ls) => { if (ls && ls.length)
            window.__r2.locked.push(window.app._lockedErrorNames(ls)); };
    }""")


def errors(page):
    return page.evaluate("() => window.__r2")


def ten_column_3fers(page, columns=10):
    """Custom on, columns 0-9 filled at 3fer: drawn runs 1-10, merged
    1-3, 4-6, 7-9 - four circuits."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': columns}])
    custom_on(page)
    assert fill(page, [(wall, 0, 9)])
    assert manual(page, wall)['merge'] == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    return wall


# ── 1. Share with next joins only single-run circuits ────────────────────

def test_custom_share_never_joins_a_3fer(page):
    """On a custom wall of 3fers the Share entry stays on the menu,
    disabled, saying why - for the 3fer clicked and for the 3fer next to
    a single run - and the model writes nothing."""
    wall = ten_column_3fers(page)
    s1, s2 = labels(page, wall)[:2]
    out = share_at(page, pt(page, wall, 2, 0))
    assert out['share'] and out['share']['disabled'] and not out['share']['runnable'], out
    assert out['share']['label'] == 'Share with next run', out
    assert out['share']['title'] == (f'{s1} is already a 3fer, and a shared circuit '
                                     'never joins another. Only a circuit of one run shares.'), out
    # the last 3fer, beside the lone column, is refused the same way
    out = share_at(page, pt(page, wall, 2, 7))
    assert out['share']['disabled'] and 'is already a 3fer' in out['share']['title'], out
    before = manual(page, wall)
    h0 = len(history(page))
    assert page.evaluate("(id) => window.app.mergeSplitterCircuits(window.__nf.layer(id), [7, 10])",
                         wall) is False
    assert manual(page, wall) == before and len(history(page)) == h0
    assert s2  # four circuits, labelled


def test_custom_share_never_joins_a_wide_circuit(page):
    """A circuit drawn across three columns (a file from before 1.5.3)
    is split by its own "3fer it", never joined: its Share is disabled
    with the reason, while two single-column circuits still share
    through a 2fer."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 6}])
    custom_on(page)
    drawn(page, wall, {'1': col(0) + col(1) + col(2), '2': col(3), '3': col(4)})
    name = labels(page, wall)[0]
    out = share_at(page, pt(page, wall, 2, 1))
    assert out['share']['disabled'], out
    assert out['share']['title'] == (f'{name} runs across 3 columns, so it splits into '
                                     'its own legs (3fer it) and never joins another.'), out
    assert out['nfer'] and out['nfer']['label'] == '3fer it (3 column runs)', out
    assert not out['nfer']['disabled'], out
    # two single-column circuits still share
    single = share_at(page, pt(page, wall, 2, 3))
    assert single['share'] and not single['share']['disabled'], single
    assert single['share']['label'] == 'Share with next run via 2fer', single
    assert ' - ' not in single['share']['title'], single
    assert page.evaluate("(id) => window.app.mergeSplitterCircuits(window.__nf.layer(id), [1, 2])",
                         wall) is False
    assert manual(page, wall)['merge'] == []


# ── 2. Clear Circuit on a custom 3fer clears every leg ───────────────────

def test_clear_circuit_on_a_custom_3fer_clears_every_leg(page):
    """The active circuit set to S1-2 (typed 2: its first leg, drawn 4),
    Clear Circuit takes all three legs and the 3fer's group in ONE history
    entry; undo puts the 3fer back whole. Active on its MIDDLE leg (drawn
    5), the clear is the same."""
    wall = ten_column_3fers(page)
    before = circuits(page, wall)
    page.locator('#power-custom-active').fill('2')
    page.locator('#power-custom-active').dispatch_event('change')
    landed(page)
    assert active(page)['index'] == 4, active(page)
    h0 = len(history(page))
    page.locator('#power-custom-clear-circuit').click()
    landed(page)
    out = circuits(page, wall)
    assert [c['num'] for c in out] == [1, 7, 10], out
    assert manual(page, wall)['merge'] == [[1, 2, 3], [7, 8, 9]], manual(page, wall)
    assert history(page)[h0:] == ['Power Custom Clear Circuit'], history(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert circuits(page, wall) == before, 'one undo puts the whole 3fer back'

    page.evaluate("() => { window.app.currentLayer.powerCustomIndex = 5; }")
    page.locator('#power-custom-clear-circuit').click()
    landed(page)
    assert [c['num'] for c in circuits(page, wall)] == [1, 7, 10], circuits(page, wall)


# ── 4. Remove 3fers from a locked custom group names the screen ──────────

def test_remove_3fers_on_a_locked_custom_group_names_it(page):
    """A custom group's wall of 3fers, then locked: "Remove 3fers from
    this screen" changes nothing and names the locked screen (it used to
    do nothing at all, silently)."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}],
                       group=True)
    page.evaluate("(ids) => { window.app.selectedLayerIds = new Set(ids); }", [left, right])
    custom_on(page)
    assert fill(page, [(left, 0, 3), (right, 0, 2)])
    merge = manual(page, left)['merge']
    assert merge, merge
    page.evaluate("""(ids) => ids.forEach(id => { window.__nf.layer(id).locked = true; })""",
                  [left, right])
    errors_on(page)
    h0 = len(history(page))
    menu_at(page, pt(page, left, 2, 0))
    item = page.locator('#context-menu [data-action="hw-batch-unshare"]')
    assert item.is_visible() and item.inner_text().startswith('Remove 3fers'), item.inner_text()
    item.click()
    landed(page)
    assert manual(page, left)['merge'] == merge
    assert len(history(page)) == h0
    assert errors(page)['locked'] == [['Left']], errors(page)


# ── 5. a custom wall of 3fers reads by circuit ───────────────────────────

def test_the_active_circuit_reads_and_steps_by_circuit(page):
    """After a 10-column fill at 3fer the wall prints S1-1..S1-4, and the
    field reads 4 (the drawn number is 10). Next goes to circuit 5 (a
    new one), Prev back through 4 and 3 - never a leg - and a typed 5 is
    the fifth circuit: a click on a free cabinet starts it, it does not
    grow a leg."""
    wall = ten_column_3fers(page, columns=12)
    assert len(labels(page, wall)) == 4, labels(page, wall)
    assert active(page) == {'shown': '4', 'index': 10}, active(page)
    page.locator('#power-custom-next').click()
    landed(page)
    assert active(page) == {'shown': '5', 'index': 11}, active(page)
    page.locator('#power-custom-prev').click()
    page.locator('#power-custom-prev').click()
    landed(page)
    assert active(page) == {'shown': '3', 'index': 7}, active(page)

    page.locator('#power-custom-active').fill('5')
    page.locator('#power-custom-active').dispatch_event('change')
    landed(page)
    assert active(page) == {'shown': '5', 'index': 11}, active(page)
    q = pt(page, wall, 0, 10)
    page.mouse.click(q['x'], q['y'])
    landed(page)
    paths = page.evaluate("(id) => Object.fromEntries(Object.entries("
                          "window.__nf.layer(id).powerCustomPaths).map(([k, v]) => [k, v.length]))",
                          wall)
    assert paths.get('11') == 1 and paths.get('5') == 5, paths
    assert len(labels(page, wall)) == 5, labels(page, wall)


def test_refusals_name_circuit_labels(page):
    """A cabinet already on S1-2's middle leg is refused as "circuit S1-2"
    (it said "circuit 5"), and a list of runs reads as the labels the wall
    prints - a leg of a shared circuit by its leg."""
    wall = ten_column_3fers(page, columns=12)
    names = labels(page, wall)
    errors_on(page)
    page.locator('#power-custom-active').fill('5')
    page.locator('#power-custom-active').dispatch_event('change')
    landed(page)
    q = pt(page, wall, 0, 4)
    page.mouse.click(q['x'], q['y'])
    landed(page)
    toasts = errors(page)['toasts']
    assert toasts and f'already wired to circuit {names[1]}.' in toasts[0], toasts
    assert 'circuit 5' not in toasts[0], toasts
    texts = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        return [app._runListText([4, 5, 6], l), app._runListText([10], l),
                app._runListText([1, 2], null)];
    }""", wall)
    assert texts == [f'{names[1]} leg 1, {names[1]} leg 2 and {names[1]} leg 3',
                     names[3], 'Runs 1 and 2'], texts


# ── 7. the batch ticks sharing and respects the Max splitter ─────────────

def test_3fer_this_screen_ticks_share_circuits_via_splitters(page):
    """Custom with sharing OFF, ten single-column circuits: "3fer this
    screen" deals 3fers AND ticks "Share circuits via splitters", in the
    one history entry; undo takes both back. Its hover says so."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': {
        'powerSplitters': {'enabled': False, 'maxWays': 3,
                           'manual': {'merge': [], 'split': []}}}}])
    custom_on(page)
    drawn(page, wall, {str(c + 1): col(c) for c in range(10)})
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n1'] and items['n1']['label'] == '3fer this screen (3 × 3fer + 1 plain)', items
    assert 'Also turns on "Share circuits via splitters"' in items['n1']['title'], items
    assert ' - ' not in items['n1']['title'], items
    h0 = len(history(page))
    take(page, 'hw-batch-n1')
    enabled = "(id) => window.app.getPowerSplitters(window.__nf.layer(id)).enabled"
    assert page.evaluate(enabled, wall) is True
    assert page.evaluate("() => document.getElementById('power-splitters-enabled').checked")
    assert manual(page, wall)['merge'] == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert history(page)[h0:] == ['3fer Screen'], history(page)
    saved = page.evaluate("""async (id) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        return !!p.layers.find(l => l.id === id).powerSplitters.enabled;
    }""", wall)
    assert saved is True
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert page.evaluate(enabled, wall) is False
    assert manual(page, wall)['merge'] == []


def test_the_batch_offers_no_size_past_the_max_splitter(page):
    """At 3fer there is no "4fer this screen"; at 4fer there is."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    drawn(page, wall, {str(c + 1): col(c) for c in range(10)})
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n0']['label'].startswith('2fer this screen'), items
    assert items['n1']['label'].startswith('3fer this screen'), items
    assert items['n2'] is None, items
    page.evaluate("() => window.app.hideContextMenu()")
    page.evaluate("(id) => { window.__nf.layer(id).powerSplitters.maxWays = 4; }", wall)
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n2'] and items['n2']['label'].startswith('4fer this screen'), items


def test_auto_share_with_next_never_builds_past_the_max_splitter(page):
    """Auto at 3fer packs 3fers; sharing one with the next would make a
    6fer, so the entry is disabled, naming the Max splitter."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': {'powerAmperage': 50}}])
    name = labels(page, wall)[0]
    out = share_at(page, pt(page, wall, 2, 0))
    assert out['share'] and out['share']['disabled'], out
    assert out['share']['label'] == 'Share with next run via 6fer', out
    assert out['share']['title'] == ('A 6fer is bigger than the Max splitter set in Power '
                                     f'Settings (3fer), so {name} shares no further.'), out


# ── 9. wording ────────────────────────────────────────────────────────────

def test_remove_3fer_in_custom_says_nothing_of_auto_packing(page):
    wall = ten_column_3fers(page)
    out = share_at(page, pt(page, wall, 2, 0))
    assert out['unshare']['label'] == 'Remove 3fer', out
    assert 'auto packing' not in out['unshare']['title'], out
    (auto,) = make(page, [{'name': 'Auto', 'columns': 10}])
    out = share_at(page, pt(page, auto, 2, 0))
    assert 'pin them out of auto packing' in out['unshare']['title'], out


def test_no_page_errors(page):
    assert page._nf_errors == [], page._nf_errors
