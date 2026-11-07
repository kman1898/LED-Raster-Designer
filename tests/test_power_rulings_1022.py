"""Power after the re-audit (the owner's rulings, 2026-10-22).

1. PACK TO 80% ON US SYSTEMS. A US screen (208 V or under: 110, 120,
   208) packs its circuits to 80% of the breaker: the automatic packer,
   Watts/Circuit and Panels/Circuit, the custom caps and the share rule.
   A 220/230/240V screen stays at the breaker, and so does a US screen
   whose circuits are all on distros marked "100% rated breakers".
2. "Share circuits via splitters" is a group setting: grouping stores the
   winning setting on every member (the locked screen's under "Lock the
   whole group", else the group's first member's), and ungrouping keeps it.
3. After Clear Circuit the active circuit field reads the circuit's place,
   the number its label is named by, and Next / Prev never land on the gap.
4. A custom 2fer / 3fer's fill readout, badge and click cap count the
   WHOLE circuit, every leg; with no cap the badge leaves blanks out.
5. "2fer / 3fer this screen" on an AUTO screen with sharing off is
   offered: it ticks sharing and deals the screen in one history entry,
   and a locked member that would change is named.

The wall is the nfer module's: 5 rows of 150 W cabinets on 208 V x 20 A,
cabled top-down, so a column is 750 W and an 80% circuit carries 3,328 W.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_rulings_1022.py -v --browser chromium
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
from test_power_rulings_1021 import (  # noqa: E402
    col, drawn, labels, active, errors_on, errors, ten_column_3fers,
)

SHARING_OFF = {'powerSplitters': {'enabled': False, 'maxWays': 3,
                                  'manual': {'merge': [], 'split': []}}}


def runs(page, layer_id):
    return [c['runs'] for c in circuits(page, layer_id)]


def readout(page, layer_id):
    return page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app.currentLayer = l;
        app.updatePowerCapacityDisplay();
        const cap = app.circuitCapacity(l);
        return { watts: document.getElementById('power-watts-per-circuit').textContent,
                 panels: document.getElementById('power-panels-per-circuit').textContent,
                 pct: cap.pct, amps: cap.amps,
                 custom: app.customRunCapacity(l, 'power').count };
    }""", layer_id)


def splitters(page, layer_id):
    return page.evaluate("""(id) => {
        const sp = window.app._ownPowerSplitters(window.__nf.layer(id));
        return [sp.enabled, sp.maxWays];
    }""", layer_id)


# ── 1. 80% on US screens ──────────────────────────────────────────────────

def test_a_us_screen_packs_to_80_percent_of_the_breaker(page):
    """208 V x 20 A, sharing off: four 750 W columns to a circuit (3,000 of
    3,328 W), not five (3,750 of 4,160 W). The sidebar and the custom cap
    read the same 3,328 W."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': SHARING_OFF}])
    assert runs(page, wall) == [[20], [20], [10]], runs(page, wall)
    out = readout(page, wall)
    assert out == {'watts': '3,328', 'panels': '22', 'pct': 0.8, 'amps': 16,
                   'custom': 22}, out


@pytest.mark.parametrize('volts, amps, watts, panels', [
    (110, 15, '1,320', '8'),
    (120, 20, '1,920', '12'),
])
def test_every_us_voltage_is_held_to_80_percent(page, volts, amps, watts, panels):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4, 'props': dict(
        SHARING_OFF, powerVoltage=volts, powerAmperage=amps)}])
    out = readout(page, wall)
    assert (out['watts'], out['panels'], out['pct']) == (watts, panels, 0.8), out


def test_a_240v_screen_stays_at_the_breaker(page):
    """240 V x 20 A carries 4,800 W: six 750 W columns, the 230/400 math."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, powerVoltage=240)}])
    assert runs(page, wall) == [[30], [20]], runs(page, wall)
    out = readout(page, wall)
    assert (out['watts'], out['pct']) == ('4,800', 1), out


US_DISTRO = {'id': 'd1', 'name': 'SL', 'ratingA': 100, 'system': '120/208',
             'outputRows': [{'connector': 'soca', 'count': 4, 'coupling': 'll',
                             'breakerA': 20}]}


def _on_distro(page, layer_id, distro):
    page.evaluate("""([id, d]) => {
        const app = window.app, l = window.__nf.layer(id);
        app.project.distros = [JSON.parse(JSON.stringify(d))];
        app._distroFaceMemo = null;
        app.getDistros();
        l.powerSocaDistro = { 1: d.id };
        app._circuitTailCache = null;
    }""", [layer_id, distro])


def test_a_distro_with_100_percent_rated_breakers_packs_at_the_breaker(page):
    """The same wall on a US distro with 100% rated breakers packs five
    columns to a circuit again; on a distro without them, four."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': SHARING_OFF}])
    _on_distro(page, wall, US_DISTRO)
    assert runs(page, wall) == [[20], [20], [10]], runs(page, wall)
    _on_distro(page, wall, dict(US_DISTRO, breakers100=True))
    assert runs(page, wall) == [[25], [25]], runs(page, wall)
    assert readout(page, wall)['watts'] == '4,160'


def test_the_share_rule_reads_80_percent(page):
    """Auto at 3fer: three columns (2,250 W, 10.8 A) share one 16 A
    circuit; at 12 A (held to 9.6 A) they cannot, and the refusal names
    the breaker and the limit."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 6, 'props': {'powerAmperage': 12}}])
    assert runs(page, wall) == [[5, 5], [5, 5], [5, 5]], runs(page, wall)
    text = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        const r = app.shareRefusal(l, [[1, 2, 3]]);
        return r && r.text;
    }""", wall)
    assert text and 'on a 12 A circuit held to 9.6 A (80%)' in text, text


# ── 2. the splitter setting is the group's ───────────────────────────────

def _group(page, ids, pick=None):
    page.evaluate("""async ([ids, pick]) => {
        const app = window.app;
        if (pick) app.askGroupLock = () => Promise.resolve(pick);
        app.selectedLayerIds = new Set(ids);
        await app.groupSelectedLayers();
    }""", [ids, pick])
    landed(page)


def test_grouping_stores_the_first_members_splitter_setting_on_every_member(page):
    a, b = make(page, [
        {'name': 'A', 'columns': 3},
        {'name': 'B', 'columns': 3, 'x': 800, 'props': {
            'powerSplitters': {'enabled': False, 'maxWays': 2,
                               'manual': {'merge': [], 'split': []}}}}])
    _group(page, [a, b])
    assert splitters(page, a) == [True, 3]
    assert splitters(page, b) == [True, 3], 'B stores the group setting'
    page.evaluate("async () => { await window.app.ungroupSelectedLayers(); }")
    landed(page)
    assert splitters(page, b) == [True, 3], 'ungrouping reverts nothing'


def test_lock_the_whole_group_keeps_the_locked_screens_splitter_setting(page):
    a, b = make(page, [
        {'name': 'A', 'columns': 3},
        {'name': 'B', 'columns': 3, 'x': 800, 'props': {
            # other watts: the walls do not walk as one, which would
            # re-walk the locked screen's circuits and be refused (round 5)
            'locked': True, 'panelWatts': 140,
            'powerSplitters': {'enabled': False, 'maxWays': 2,
                               'manual': {'merge': [], 'split': []}}}}])
    raw = "(id) => JSON.parse(JSON.stringify(window.__nf.layer(id).powerSplitters))"
    before = page.evaluate(raw, b)
    _group(page, [a, b], 'lock')
    assert page.evaluate(raw, b) == before, 'the locked screen does not change'
    assert splitters(page, a) == [False, 2], 'the locked setting wins'
    page.evaluate("() => { window.app.project.layers.forEach(l => { l.locked = false; }); }")
    assert splitters(page, a) == [False, 2]


def test_add_to_group_stores_the_groups_setting(page):
    a, b, c = make(page, [
        {'name': 'A', 'columns': 3},
        {'name': 'B', 'columns': 3, 'x': 800},
        {'name': 'C', 'columns': 3, 'x': 1600, 'props': SHARING_OFF}])
    _group(page, [a, b])
    gid = page.evaluate("(id) => window.__nf.layer(id).group_id", a)
    page.evaluate("""async ([c, gid]) => {
        const app = window.app;
        app.selectedLayerIds = new Set([c]);
        await app.addSelectedToGroup(gid);
    }""", [c, gid])
    landed(page)
    assert splitters(page, c) == [True, 3]


# ── 3. the active circuit field after Clear Circuit ──────────────────────

def test_after_clear_circuit_the_field_reads_the_circuits_place(page):
    """Six single-column circuits, S1-3 cleared: drawn 4 reads 3 (it is
    labelled S1-3 now), Next / Prev step over the gap, a typed 5 is the
    fifth circuit and a typed 6 is the next free one."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 8, 'props': SHARING_OFF}])
    custom_on(page)
    drawn(page, wall, {str(c + 1): col(c) for c in range(6)})
    page.evaluate("(id) => { window.__nf.layer(id).powerCustomIndex = 3; }", wall)
    page.locator('#power-custom-clear-circuit').click()
    landed(page)
    assert [c['num'] for c in circuits(page, wall)] == [1, 2, 4, 5, 6]
    names = labels(page, wall)
    nxt, prv = '#power-custom-next', '#power-custom-prev'
    page.locator(nxt).click()
    landed(page)
    assert active(page) == {'shown': '3', 'index': 4}, active(page)
    shown_label = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        return app.getPowerCircuitLabel(l, app.customCircuitRun(l, 3));
    }""", wall)
    assert shown_label == names[2], (shown_label, names)
    page.locator(nxt).click()
    landed(page)
    assert active(page) == {'shown': '4', 'index': 5}, active(page)
    page.locator(prv).click()
    page.locator(prv).click()
    landed(page)
    assert active(page) == {'shown': '2', 'index': 2}, 'Prev steps over the gap'
    for typed, want in (('5', {'shown': '5', 'index': 6}), ('6', {'shown': '6', 'index': 7})):
        page.locator('#power-custom-active').fill(typed)
        page.locator('#power-custom-active').dispatch_event('change')
        landed(page)
        assert active(page) == want, (typed, active(page))
    inverse = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        return [1, 2, 4, 5, 6, 7].map(n => app.customCircuitRun(l, app.customCircuitShown(l, n)));
    }""", wall)
    assert inverse == [1, 2, 4, 5, 6, 7], inverse


# ── 4. a custom 3fer is judged whole ─────────────────────────────────────

FILL_JS = """([id, num]) => {
    const app = window.app, l = window.__nf.layer(id);
    app._circuitTailCache = null;
    const f = app.customRunFill(l, 'power', num);
    return { text: f.text, full: f.full, known: f.known };
}"""


def test_a_3fer_fills_as_one_circuit(page):
    """Each 3fer of the ten-column fill is 15 cabinets on one circuit: the
    readout counts 15 on any of its legs, and at 13.6 A (15 cabinets'
    worth at 80%) a click past it is refused on the middle leg too."""
    wall = ten_column_3fers(page, columns=12)
    for leg in (4, 5, 6):
        assert page.evaluate(FILL_JS, [wall, leg]) == {
            'text': '15/22', 'full': False, 'known': True}, leg
    page.evaluate("""(id) => { const l = window.__nf.layer(id);
        l.powerAmperage = 13.6; l.powerCustomIndex = 5; }""", wall)
    page.evaluate("() => window.app.updateCustomPowerUI()")
    assert page.evaluate(FILL_JS, [wall, 5])['full'] is True
    text = page.evaluate("() => document.getElementById('power-custom-fill-readout').textContent")
    assert '15/15 panels · full' in text, text
    errors_on(page)
    q = pt(page, wall, 0, 11)
    page.mouse.click(q['x'], q['y'])
    landed(page)
    toasts = errors(page)['toasts']
    assert toasts and 'is full, 15 panels at 208V/13.6A at 80%' in toasts[0], toasts
    assert page.evaluate("(id) => (window.__nf.layer(id).powerCustomPaths[5] || []).length",
                         wall) == 5


def test_with_no_cap_the_badge_counts_the_whole_circuit_without_blanks(page):
    wall = ten_column_3fers(page, columns=12)
    out = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        l.panelWatts = 0;
        app.getPanelByRowCol(l, 0, 4).blank = true;
        l.powerCustomIndex = 5;
        app.updateCustomPowerUI();
        return { count: window.canvasRenderer._getCustomPowerCircuitPanelCount(l, 5),
                 text: document.getElementById('power-custom-fill-readout').textContent };
    }""", wall)
    assert out['count'] == 14, out
    assert '14 panels, no cap' in out['text'], out


# ── 5. "2fer this screen" in auto with sharing off ───────────────────────

def test_2fer_this_screen_in_auto_ticks_sharing_and_packs(page):
    """Auto, sharing off: the whole screen's 2fer entry is offered, worked
    out on the runs sharing gives (ten columns, five 2fers). Taking it
    ticks sharing and deals the screen in one history entry; undo puts
    both back."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': SHARING_OFF}])
    items = menu_at(page, pt(page, wall, 0, 0))
    item = items['n0']
    assert item and not item['disabled'], items
    assert item['label'] == '2fer this screen (5 × 2fer)', items
    assert 'Also turns on "Share circuits via splitters"' in item['title'], items
    h0 = len(history(page))
    take(page, 'hw-batch-n0')
    assert splitters(page, wall) == [True, 3]
    assert manual(page, wall)['merge'] == [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
    assert runs(page, wall) == [[5, 5]] * 5, runs(page, wall)
    assert history(page)[h0:] == ['2fer Screen'], history(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert splitters(page, wall) == [False, 3]
    assert runs(page, wall) == [[20], [20], [10]]


def test_2fer_this_screen_names_a_locked_member_and_changes_nothing(page):
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 800,
                        'props': dict(SHARING_OFF, locked=True)}], group=True)
    errors_on(page)
    before = runs(page, a)
    h0 = len(history(page))
    menu_at(page, pt(page, a, 0, 0))
    take(page, 'hw-batch-n0')
    assert errors(page)['locked'] == [['B']], errors(page)
    assert splitters(page, a) == [False, 3] and splitters(page, b) == [False, 3]
    assert runs(page, a) == before and len(history(page)) == h0


def test_no_page_errors(page):
    assert page._nf_errors == [], page._nf_errors
