"""Power after the final audit (the owner's rulings, 2026-10-22).

1. The packing % is valid for the REGION: a circuit on a US distro packs at
   80% of its breaker whatever its voltage (240 V on a US 120/240 distro
   is 80%), a UK/EU distro packs at 100%, a US distro with "100% rated
   breakers" at 100%, and a screen on no distro decides by voltage. The
   distro's own breaker check always agrees with the packing. A multi
   assignment past the screen's multis is stale and left out.
2. The screen's amperage box is the BREAKER SIZE, and the usable amps show
   beside it ("20 A breaker · 16 A usable").
3. Ticking "100% rated breakers" never silently repacks a locked screen.
4. Two boxes typed with one name on different distros warn and ask for a
   rename; the circuits take no suffix.
5. The distro display label: a hidden distro that still prints counts
   toward duplicates, a suffix never equals another distro's name, and the
   gear heading and the Balance title use it.
6. Wording: a direct output's length is a cable, the grouped "2fer this
   screen" says it turns sharing on for the whole group, and Prev from a
   leading cleared gap never moves forward.

The wall is the nfer module's: 5 rows of 150 W cabinets on 208 V x 20 A,
cabled top-down, so a column is 750 W.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_region_rulings.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, menu_at, custom_on, circuits, history,
)
from test_power_rulings_1021 import col, drawn, active, errors_on, errors  # noqa: E402

SHARING_OFF = {'powerSplitters': {'enabled': False, 'maxWays': 3,
                                  'manual': {'merge': [], 'split': []}}}


def _distro(id_, name, system='120/208', **extra):
    d = {'id': id_, 'name': name, 'ratingA': 400, 'system': system,
         'outputRows': [{'connector': 'soca', 'count': 6, 'coupling': 'll',
                         'breakerA': 20}]}
    d.update(extra)
    return d


def set_distros(page, distros, feeds=None):
    """Put `distros` on the project and each {layerId: {multi: distroId}}
    of `feeds` on its screen."""
    page.evaluate("""([ds, feeds]) => {
        const app = window.app;
        app.project.distros = JSON.parse(JSON.stringify(ds));
        app._distroFaceMemo = null;
        app.getDistros();
        Object.entries(feeds || {}).forEach(([id, map]) => {
            window.__nf.layer(Number(id)).powerSocaDistro = map;
        });
        app._circuitTailCache = null;
    }""", [distros, {str(k): {str(n): v for n, v in m.items()}
                     for k, m in (feeds or {}).items()}])


def runs(page, layer_id):
    return [c['runs'] for c in circuits(page, layer_id)]


def capacity(page, layer_id):
    return page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app._circuitTailCache = null;
        app.currentLayer = l;
        app.updatePowerCapacityDisplay();
        const cap = app.circuitCapacity(l);
        const el = document.getElementById('power-amperage-usable');
        return { pct: cap.pct, amps: cap.amps, usable: el && el.textContent,
                 watts: document.getElementById('power-watts-per-circuit').textContent,
                 wattsTip: document.getElementById('power-watts-per-circuit').title,
                 panelsTip: document.getElementById('power-panels-per-circuit').title };
    }""", layer_id)


def breaker_checks(page, distro_id):
    return page.evaluate("""(id) => {
        const app = window.app;
        app._circuitTailCache = null;
        const d = app.getDistros().find(x => x.id === id);
        return app.distroChecks(d).map(c => c.text)
            .filter(t => / breaker/.test(t) && /draws/.test(t));
    }""", distro_id)


# ── 1. the packing % is the region's ──────────────────────────────────────

def test_a_240v_screen_on_a_us_distro_packs_at_80_percent(page):
    """240 V x 20 A on a US 120/240 distro: 80% (3,840 W), five 750 W
    columns to a circuit, not six. The distro's breaker check, at 80% of
    its 20 A breakers, finds nothing over: the two always agree."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, powerVoltage=240)}])
    assert runs(page, wall) == [[30], [20]], 'off a distro 240 V packs at the breaker'
    set_distros(page, [_distro('us', 'SL', '120/240')], {wall: {1: 'us'}})
    assert runs(page, wall) == [[25], [25]], runs(page, wall)
    cap = capacity(page, wall)
    assert (cap['pct'], cap['amps'], cap['watts']) == (0.8, 16, '3,840'), cap
    assert breaker_checks(page, 'us') == []


def test_a_us_distro_with_100_percent_rated_breakers_packs_at_the_breaker(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, powerVoltage=240)}])
    set_distros(page, [_distro('us', 'SL', '120/240', breakers100=True)], {wall: {1: 'us'}})
    assert runs(page, wall) == [[30], [20]], runs(page, wall)
    assert capacity(page, wall)['pct'] == 1
    assert breaker_checks(page, 'us') == []


def test_a_uk_eu_distro_packs_at_the_breaker(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, powerVoltage=230)}])
    eu = {'id': 'eu', 'name': 'EU', 'ratingA': 63, 'system': '230/400'}
    set_distros(page, [eu], {wall: {1: 'eu'}})
    cap = capacity(page, wall)
    assert (cap['pct'], cap['usable']) == (1, '20 A breaker · 20 A usable'), cap
    assert runs(page, wall) == [[30], [20]], runs(page, wall)


def test_a_screen_on_no_distro_decides_by_voltage(page):
    a, b = make(page, [
        {'name': 'A', 'columns': 4, 'props': SHARING_OFF},
        {'name': 'B', 'columns': 4, 'x': 1000, 'props': dict(SHARING_OFF, powerVoltage=240)}])
    assert capacity(page, a)['pct'] == 0.8
    assert capacity(page, b)['pct'] == 1


def test_a_stale_multi_assignment_is_left_out(page):
    """Ten columns at 80% make three circuits, one multi. Its multi 1 is on
    a 100% rated distro; an entry for a multi 2 it no longer has, on a
    distro without, is left out: the wall packs at the breaker."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': SHARING_OFF}])
    set_distros(page, [_distro('d100', 'SL', breakers100=True), _distro('d80', 'SR')],
                {wall: {1: 'd100', 2: 'd80'}})
    assert capacity(page, wall)['pct'] == 1
    assert runs(page, wall) == [[25], [25]], runs(page, wall)


def test_a_multi_that_exists_at_80_percent_keeps_the_screen_at_80(page):
    """26 columns: seven circuits and two multis at 80%, six circuits and
    one multi at 100%. Multi 2 is on a distro without 100% rated breakers,
    so the screen packs at 80% - and at 80% that multi is real, on that
    distro: the answer agrees with itself."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 26, 'props': SHARING_OFF}])
    set_distros(page, [_distro('d100', 'SL', breakers100=True), _distro('d80', 'SR')],
                {wall: {1: 'd100', 2: 'd80'}})
    assert capacity(page, wall)['pct'] == 0.8
    plan = page.evaluate("""(id) => {
        const app = window.app; app._circuitTailCache = null;
        return app.getSocaPlan(window.__nf.layer(id)).map(s => [s.soca, s.distroId, s.legs.length]);
    }""", wall)
    assert plan == [[1, 'd100', 6], [2, 'd80', 1]], plan
    assert breaker_checks(page, 'd80') == [] and breaker_checks(page, 'd100') == []


# ── 2. the amperage box is the breaker ───────────────────────────────────

def test_the_amperage_box_shows_the_usable_amps(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4}])
    label = page.evaluate("""() => {
        const row = document.getElementById('power-amperage-select').closest('.info-row');
        return { label: row.querySelector('label').textContent,
                 tip: row.getAttribute('data-tooltip') };
    }""")
    # The box keeps its Amperage label (owner, 2026-10-22); the tooltip
    # says it takes the breaker size, and the usable amps show beside it.
    assert label['label'] == 'Amperage (A)', label
    assert label['tip'].startswith('Amperage, the size of the breaker'), label
    assert 'Breaker (A)' not in page.content()
    assert 'breaker' in label['tip'] and '16 A usable' in label['tip'], label
    cap = capacity(page, wall)
    assert cap['usable'] == '20 A breaker · 16 A usable', cap
    assert '16 A usable' in cap['wattsTip'] and '80%' in cap['wattsTip'], cap
    assert '16 A usable of the 20 A breaker' in cap['panelsTip'], cap
    # typing 16 shows the double derating
    page.evaluate("(id) => { window.__nf.layer(id).powerAmperage = 16; }", wall)
    assert capacity(page, wall)['usable'] == '16 A breaker · 12.8 A usable'
    # a 100% rated US distro uses the whole breaker
    page.evaluate("(id) => { window.__nf.layer(id).powerAmperage = 20; }", wall)
    set_distros(page, [_distro('d100', 'SL', breakers100=True)], {wall: {1: 'd100'}})
    cap = capacity(page, wall)
    assert cap['usable'] == '20 A breaker · 20 A usable', cap
    assert '100% rated' in cap['wattsTip'], cap


# ── 3. a locked screen is never repacked by the distro's switch ──────────

def _tick(page, distro_id, on):
    return page.evaluate("""([id, on]) => {
        const app = window.app;
        const res = app.updateDistro(id, { breakers100: on });
        const d = app.getDistros().find(x => x.id === id);
        return { refused: res === null, rated: !!d.breakers100 };
    }""", [distro_id, on])


def test_ticking_100_percent_breakers_refuses_a_locked_screen_it_repacks(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10, 'props': dict(
        SHARING_OFF, locked=True)}])
    set_distros(page, [_distro('d1', 'SL')], {wall: {1: 'd1'}})
    errors_on(page)
    before = runs(page, wall)
    h0 = len(history(page))
    assert _tick(page, 'd1', True) == {'refused': True, 'rated': False}
    assert errors(page)['locked'] == [['Wall']], errors(page)
    assert runs(page, wall) == before and len(history(page)) == h0
    # the gear's box goes back to the way the distro still is
    checked = page.evaluate("""() => {
        const app = window.app;
        const d = app.getDistros()[0];
        const wrap = app._buildDistroGearContent(d);
        document.body.appendChild(wrap);
        const cb = wrap.querySelector('[data-lrd-field="distro-breakers100-d1"]');
        cb.click();
        const out = { checked: cb.checked, heading: wrap.querySelector('.hw-pop-heading').textContent };
        wrap.remove();
        return out;
    }""")
    assert checked == {'checked': False, 'heading': 'SL'}, checked
    # unlocked, the tick takes
    page.evaluate("(id) => { window.__nf.layer(id).locked = false; }", wall)
    assert _tick(page, 'd1', True) == {'refused': False, 'rated': True}
    assert runs(page, wall) == [[25], [25]]


def test_a_locked_group_member_is_named_too(page):
    """B is locked and fed by nothing; A, in its group, is on the distro.
    The wall packs as one, so the tick would repack B: refused, B named."""
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 800,
                        'props': dict(SHARING_OFF, locked=True)}], group=True)
    set_distros(page, [_distro('d1', 'SL')], {a: {1: 'd1'}})
    errors_on(page)
    assert _tick(page, 'd1', True) == {'refused': True, 'rated': False}
    assert errors(page)['locked'] == [['B']], errors(page)


def test_a_locked_screen_the_tick_does_not_repack_does_not_block_it(page):
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 1000,
                        'props': dict(SHARING_OFF, locked=True)}])
    set_distros(page, [_distro('d1', 'SL'), _distro('d2', 'SR')], {a: {1: 'd1'}, b: {1: 'd2'}})
    assert _tick(page, 'd1', True) == {'refused': False, 'rated': True}


# ── 4. one typed multi name on two distros ───────────────────────────────

DOCK_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    app.renderHardwareDock();
    return { warn: (app._dockPowerWarnings || []).map(w => [w.text, !!w.mild]),
             flagged: [...document.querySelectorAll('[data-lrd-dup-name]')]
                 .map(el => [el.dataset.lrdDupName, el.title]) };
}"""


def test_two_boxes_typed_main_on_two_distros_warn_and_ask_to_rename(page):
    a, b = make(page, [{'name': 'A', 'columns': 2}, {'name': 'B', 'columns': 2, 'x': 1000}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SL')],
                {a: {1: 'd1'}, b: {1: 'd2'}})
    page.evaluate("""([a, b]) => {
        window.__nf.layer(a).powerSocaNames = { 1: 'MAIN' };
        window.__nf.layer(b).powerSocaNames = { 1: 'MAIN' };
    }""", [a, b])
    out = page.evaluate(DOCK_JS)
    want = 'MAIN is used on 2 boxes, SR1 and SL1. Rename one so each box reads its own name.'
    assert [want, True] in out['warn'], out
    assert len(out['flagged']) == 2 and all(f[0] == 'MAIN' and f[1].startswith(want)
                                            for f in out['flagged']), out
    names = page.evaluate("""([a, b]) => {
        const app = window.app; app._circuitTailCache = null;
        return [a, b].map(id => { const l = window.__nf.layer(id);
            return app.screenCircuits(l).map(c => app.getPowerCircuitLabel(l, c.num)); });
    }""", [a, b])
    assert names[0] == names[1] and names[0][0].startswith('MAIN'), names
    # renamed, the warning goes
    page.evaluate("(b) => { window.__nf.layer(b).powerSocaNames = { 1: 'SIDE' }; }", b)
    out = page.evaluate(DOCK_JS)
    assert not [w for w in out['warn'] if 'is used on' in w[0]] and not out['flagged'], out


# ── 5. the distro display label ──────────────────────────────────────────

LABELS_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return app.getDistros().map(d => app.distroLabel(d));
}"""


def test_a_suffix_never_reads_as_another_distros_name(page):
    """SR, SR and a distro typed SR-1: the two SRs skip SR-1 (SR-2, SR-3),
    and the typed SR-1 keeps its name, so every label is one distro's. The
    two SRs print (their feeders are set): only a distro that prints is
    counted (round 5)."""
    make(page, [{'name': 'Wall', 'columns': 2}])
    set_distros(page, [_distro('d1', 'SR', feeder={'ft': 50}), _distro('d2', 'SR', feeder={'ft': 50}),
                       _distro('d3', 'SR-1')])
    assert page.evaluate(LABELS_JS) == ['SR-2', 'SR-3', 'SR-1']


def test_a_hidden_distro_that_still_prints_counts_toward_duplicates(page):
    a, b = make(page, [{'name': 'A', 'columns': 2}, {'name': 'B', 'columns': 2, 'x': 1000}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR'), _distro('d3', 'X')],
                {a: {1: 'd1'}, b: {1: 'd2'}})
    page.evaluate("(b) => { window.__nf.layer(b).visible = false; }", b)
    assert page.evaluate(LABELS_JS) == ['SR', 'SR', 'X'], 'not printed, not counted'
    page.evaluate("() => { window.app.getDistros()[1].feeder = { ft: 50 }; }")
    assert page.evaluate(LABELS_JS) == ['SR-1', 'SR-2', 'X'], 'its feeder prints it'
    page.evaluate("""() => { const ds = window.app.getDistros();
        delete ds[1].feeder; ds[2].feeder = { from: 'd2' }; }""")
    assert page.evaluate(LABELS_JS) == ['SR-1', 'SR-2', 'X'], 'a distro fed thru it prints it'
    page.evaluate("(b) => { window.__nf.layer(b).visible = true; }", b)


def test_the_gear_heading_and_balance_title_use_the_label(page):
    a, b = make(page, [{'name': 'A', 'columns': 2}, {'name': 'B', 'columns': 2, 'x': 1000}])
    set_distros(page, [_distro('d1', 'SR'), _distro('d2', 'SR')], {a: {1: 'd1'}, b: {1: 'd2'}})
    out = page.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const d = app.getDistros()[1];
        const heading = app._buildDistroGearContent(d).querySelector('.hw-pop-heading').textContent;
        app.showBalanceDialog(d.id);
        const modal = document.getElementById('balance-modal');
        const title = modal.querySelector('h2').textContent;
        modal.remove();
        return { heading, title };
    }""")
    assert out == {'heading': 'SR-2', 'title': 'BALANCE PHASE LEGS: SR-2'}, out


# ── 6. wording ───────────────────────────────────────────────────────────

def test_a_direct_outputs_length_is_its_cable(page):
    """A one-circuit multi on a TRUE1 direct output: a bad length is
    refused as the cable's, and the undo entry is Set Direct Cable."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 2, 'props': {
        'powerBreakoutType': 'soca-true1', 'powerSocaSplits': [1],
        'powerSocaNumber': {'1': 1}}}])
    direct = {'id': 'dd', 'name': 'PD', 'ratingA': 200, 'system': '120/208',
              'outputRows': [{'connector': 'true1', 'count': 2, 'coupling': 'll',
                              'breakerA': 20}]}
    set_distros(page, [direct], {wall: {1: 'dd'}})
    errors_on(page)
    out = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app._circuitTailCache = null;
        const onDirect = app._socaOnDirectOutput(l, 1);
        const bad = app.setSocaLength(l, 1, 'banana');
        const good = app.setSocaLength(l, 1, '40');
        return { onDirect, bad, good, last: app.history[app.history.length - 1].action };
    }""", wall)
    assert out == {'onDirect': True, 'bad': False, 'good': True, 'last': 'Set Direct Cable'}, out
    toasts = errors(page)['toasts']
    assert [t for t in toasts if "Type the cable's length" in t], toasts
    assert not [t for t in toasts if 'home run' in t], toasts


def test_2fer_this_screen_on_a_grouped_wall_names_every_member(page):
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 800, 'props': SHARING_OFF}],
                group=True)
    items = menu_at(page, pt(page, a, 0, 0))
    item = items['n0']
    assert item and not item['disabled'], items
    assert ('Also turns on "Share circuits via splitters" for every screen in its '
            'group (A and B).') in item['title'], items
    assert 'for this screen' not in item['title'], items
    page.keyboard.press('Escape')


def test_prev_from_a_leading_gap_never_moves_forward(page):
    """Circuit 1 cleared: there is no circuit before the gap, so Prev stays
    put instead of jumping to circuit 2."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 8, 'props': SHARING_OFF}])
    custom_on(page)
    drawn(page, wall, {str(c + 1): col(c) for c in range(6)})
    page.evaluate("(id) => { window.__nf.layer(id).powerCustomIndex = 1; }", wall)
    page.locator('#power-custom-clear-circuit').click()
    landed(page)
    assert [c['num'] for c in circuits(page, wall)] == [2, 3, 4, 5, 6]
    before = active(page)
    page.locator('#power-custom-prev').click()
    landed(page)
    assert active(page) == before and before['index'] == 1, (before, active(page))
    page.locator('#power-custom-next').click()
    landed(page)
    assert active(page)['index'] == 2, active(page)


def test_no_page_errors(page):
    assert page._nf_errors == [], page._nf_errors
