"""Phase balancing, audited against an independent model.

The balancer chooses WHICH tails of its fan each partly-filled multi uses
(wall order on the chosen tails - the only lever there is). An audit with
hand math found it could make the legs worse. What these tests hold it to:

  * The optimum. Every combination of tail subsets is scored (bounded only
    past 50,000 combinations, and then the dialog says "best found"), and
    the answer equals an independent phasor model's exhaustive optimum.
  * The objective is lexicographic: lowest imbalance, then the lighter
    busiest leg - and a result whose busiest leg is heavier than today is
    never offered. Nothing better than today: no Apply.
  * Apply is never worse than leaving it. The dialog's figures are the real
    loads before and the real loads of the proposal (a dry run), and Apply
    is offered only when that real result strictly improves.
  * A shared box is scored as it SITS (a stored member can sit below an
    earlier one), not as a re-deal of the same tail set.
  * A circuit held through a paired connector is never patched twice.
  * A locked screen is held where it is: the search treats its tails as
    fixed, nothing writes it - in the browser or on the server - and Reset
    leaves its labels alone, naming it.
  * A legacy breaker offset does not come back after Apply.

Rulings: Apply moves circuits onto other tails of the same multi and never
renumbers multis; Reset clears and re-deals the multi numbers in screen
order, a locked screen keeping its own; a locked screen stays unchanged
until it is unlocked, and anything that would change it leaves it alone
and names it.
"""

import cmath
import copy
import itertools
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function(
        '() => window.app && Array.isArray(window.app.history) && window.app.history.length > 0',
        timeout=60000)
    pg.evaluate(HELPERS_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg
    assert errors == [], errors
    context.close()


# A screen is one row of tiles drawn as custom circuits, `tiles` giving each
# circuit's tile count - 100 W a tile - so every circuit's watts are exact.
# Six circuits to a multi.
HELPERS_JS = r"""
window.__pb = {
    screen(id, name, tiles, opts) {
        const total = tiles.reduce((a, b) => a + b, 0);
        const o = Object.assign({
            id, name, type: 'screen', visible: true, locked: false,
            columns: total, rows: 1, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: id * 200, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 100, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'custom', powerOrganized: true, powerMaximize: false,
            group_id: null, powerSocaKeying: 'index',
        }, opts || {});
        o.panels = [];
        for (let c = 0; c < total; c++) o.panels.push({ row: 0, col: c,
            x: o.offset_x + c * 128, y: o.offset_y, width: 128, height: 128,
            hidden: false, blank: false, halfTile: 'none' });
        const paths = {};
        let col = 0;
        tiles.forEach((t, i) => {
            paths[i + 1] = [];
            for (let k = 0; k < t; k++) paths[i + 1].push({ row: 0, col: col++ });
        });
        o.powerCustomPaths = paths;
        o.powerCustomIndex = tiles.length + 1;
        return o;
    },
    distro(id, name, system, extra) {
        const sys = { '120/208': [208, 3], '230/400': [400, 3], '120/240': [240, 1] }[system];
        return Object.assign({ id, name, ratingA: 400, voltage: sys[0], phase: sys[1], system },
                             extra || {});
    },
    row(id, connector, count, coupling, breakerA, pairedWith) {
        return { id, connector, count, coupling, breakerA, pairedWith: pairedWith || null };
    },
    // Run `fn` against a synthetic project and put the page's own back.
    // Nothing reaches the server: the layer PUT is stubbed for the call.
    withProject(project, fn) {
        const app = window.app;
        const saved = app.project;
        const savedUpdate = app.updateLayers;
        const savedToast = app._toast;
        window.__pbToasts = [];
        app._toast = (m) => { window.__pbToasts.push(m); };
        app.project = Object.assign({ layers: [], groups: [], canvases: [], rack: [], distros: [] },
                                    project);
        app.updateLayers = () => {};
        app._circuitTailCache = null;
        if (app._distroFaceMemo) app._distroFaceMemo = new WeakMap();
        try { return fn(app); } finally {
            app.project = saved;
            app.updateLayers = savedUpdate;
            app._toast = savedToast;
            app._circuitTailCache = null;
        }
    },
    // Real figures of one distro, straight off getDistroLoads.
    loads(did) {
        const app = window.app;
        app._circuitTailCache = null;
        const L = app.getDistroLoads().find(x => x.id === did);
        return { X: L.legs.X.amps, Y: L.legs.Y.amps, Z: L.legs.Z.amps,
                 imb: L.imbalancePct, busiest: L.legs.worstAmps };
    },
    labels(layer) {
        const app = window.app;
        app._circuitTailCache = null;
        return app.getSocaPlan(layer).flatMap(s => s.legs.map(g => g.label));
    },
    tails(layer) {
        const app = window.app;
        app._circuitTailCache = null;
        return app.getSocaPlan(layer).flatMap(s => s.legs.map(g => g.leg));
    },
    // Suggest, then apply exactly what was suggested: the real figures
    // before and after, and what the dialog promised.
    balance(did) {
        const app = window.app;
        const before = this.loads(did);
        const r = app.suggestPhaseBalance(did);
        app.applyPhaseBalance(r.moves);
        const after = this.loads(did);
        return { before, after, r: {
            before: r.before, after: r.after,
            beforeBusiest: r.beforeBusiest, afterBusiest: r.afterBusiest,
            searched: r.searched, total: r.total, exhaustive: r.exhaustive,
            blockedByBusiest: r.blockedByBusiest, locked: r.locked,
            moves: r.moves.map(m => ({ name: m.name, layer: m.layerName,
                                       from: m.from, to: m.to })),
        } };
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        return r.json();
    },
    // The open path's own steps: the server takes the project, the client
    // adopts the server's copy, history starts over.
    async open(project) {
        const app = window.app;
        await this.j('PUT', '/api/project', project);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('phase_balance_audit');
        app.selectLayer(app.project.layers[0]);
        app.resetHistory('Initial State');
        app.renderLayers();
        return true;
    },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
};
"""


# ── the independent model ────────────────────────────────────────────────
#
# Leg phasors from first principles: a line-to-neutral circuit is its full
# current on one leg at 0 deg; a line-to-line circuit is one current in
# both legs, +30 deg on the first of the cyclic pair and -30 on the other.
# Imbalance is the largest deviation from the mean leg over the mean.

MAPS = {
    'paired-ll': [('X', 'Y'), ('X', 'Y'), ('Z', 'X'), ('Z', 'X'), ('Y', 'Z'), ('Y', 'Z')],
    'rotating-ln': [('X',), ('Y',), ('Z',), ('X',), ('Y',), ('Z',)],
}


def _cyc(a, b):
    c = 'XYZ'
    return (a, b) if c.index(b) == (c.index(a) + 1) % 3 else (b, a)


def model_legs(multis, tails, vll):
    ph = {k: 0j for k in 'XYZ'}
    for m, t in zip(multis, tails):
        for w, p in zip(m['watts'], sorted(t)):
            if m['scheme'] == 'whole-ln':
                legs = ('XYZ'[(m['number'] - 1) % 3],)
            else:
                legs = MAPS[m['scheme']][p - 1]
            if len(legs) == 1:
                ph[legs[0]] += w / m['v']
            else:
                a, b = _cyc(*legs)
                i = w / vll
                ph[a] += i * cmath.exp(1j * math.radians(30))
                ph[b] += i * cmath.exp(-1j * math.radians(30))
    amps = [abs(ph[k]) for k in 'XYZ']
    avg = sum(amps) / 3
    imb = max(abs(x - avg) for x in amps) / avg * 100 if avg > 0 else 0
    return imb, max(amps)


def _gains(after, before):
    """The app's offering rule: busiest leg no heavier, and the imbalance a
    hundredth of a point lower - or, level, the busiest leg lighter."""
    if after[1] > before[1] + 1e-6:
        return False
    if after[0] < before[0] - 0.01:
        return True
    return after[0] <= before[0] + 1e-7 and after[1] < before[1] - 0.001


def model_expected(multis, starts, vll, fixed=()):
    """(before, expected after) as (imbalance, busiest): the exhaustive
    lexicographic optimum over every partly-filled, unfixed multi's tail
    subsets, never heavier on the busiest leg than now - or `before` when
    nothing strictly beats it."""
    before = model_legs(multis, starts, vll)
    opts = []
    for i, m in enumerate(multis):
        if len(m['watts']) >= 6 or i in fixed:
            opts.append([starts[i]])
        else:
            opts.append(list(itertools.combinations(range(1, 7), len(m['watts']))))
    best = before
    for combo in itertools.product(*opts):
        f = model_legs(multis, combo, vll)
        if f[1] > before[1] + 1e-6:
            continue
        if f[0] < best[0] - 1e-7 or (abs(f[0] - best[0]) <= 1e-7 and f[1] < best[1] - 1e-6):
            best = f
    return before, (best if _gains(best, before) else before)


def _scheme(system, v, explicit=None):
    ll = system == '120/208' and v == 208
    if explicit == 'whole-ln' and not ll:
        return 'whole-ln'
    return 'paired-ll' if ll else 'rotating-ln'


def model_of(spec):
    """The spec as the model's multis: six circuits to a multi, auto numbers
    in layer order, a box pinned by several screens one multi (its members'
    circuits in member order) numbered by its pin."""
    d = spec['distros'][0]
    vll = {'120/208': 208, '230/400': 400}[d['system']]
    explicit = (d.get('extra') or {}).get('phasing')
    multis, starts, shared = [], [], {}
    for s in spec['screens']:
        pin = ((s.get('opts') or {}).get('powerSocaNumber') or {}).get('1')
        if pin:
            box = shared.setdefault(pin, dict(watts=[], v=s['v'],
                                              scheme=_scheme(d['system'], s['v'], explicit), number=pin))
            box['watts'] += [100 * t for t in s['tiles']]
            continue
        for k in range(0, len(s['tiles']), 6):
            w = [100 * t for t in s['tiles'][k:k + 6]]
            multis.append(dict(watts=w, v=s['v'], scheme=_scheme(d['system'], s['v'], explicit),
                               number=None))
    taken = set(shared)
    n = 0
    for m in multis:
        n += 1
        while n in taken:
            n += 1
        m['number'] = n
    multis = list(shared.values()) + multis
    starts = [tuple(range(1, len(m['watts']) + 1)) for m in multis]
    return multis, starts, vll


RUN_SPEC = r"""(spec) => {
    const B = window.__pb;
    const distros = spec.distros.map(d => B.distro(d.id, d.name, d.system, d.extra));
    const layers = spec.screens.map((s, i) => B.screen(i + 1, s.name, s.tiles,
        Object.assign({ powerVoltage: s.v, powerSocaDistro: s.assign || { 1: spec.distros[0].id } },
                      s.opts || {})));
    return B.withProject({ layers, distros }, () => B.balance(spec.distros[0].id));
}"""


def _sl(system='120/208', extra=None):
    d = dict(id='d1', name='SL', system=system)
    if extra:
        d['extra'] = extra
    return [d]


# The audit's cases. The greedy search missed the optimum on 2, 4c, 5,
# GAP208 and GAP120 (by up to 34 points); on BUSIEST it "improved" 63.50%
# to 63.49% by loading the busiest leg 6.67 -> 7.52 A.
CASES = {
    'three 208V multis': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[10, 8, 6, 4], v=208), dict(name='B', tiles=[9, 3], v=208),
        dict(name='C', tiles=[7, 7, 2, 5, 1], v=208)]),
    'mixed 120V + 208V': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[10, 6, 3], v=120), dict(name='B', tiles=[8, 8, 4, 2], v=208)]),
    'five 208V circuits': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[6, 5, 4, 3, 2], v=208)]),
    'three 120V circuits': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[9, 5, 2], v=120)]),
    'two screens, a full multi': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[8, 8, 8, 8, 8, 8, 5, 5], v=208, assign={'1': 'd1', '2': 'd1'}),
        dict(name='B', tiles=[6, 6, 6], v=208)]),
    'shared box pinned No.1': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[8, 6], v=208, opts=dict(powerSocaNumber={'1': 1})),
        dict(name='B', tiles=[5, 3, 2], v=208, opts=dict(powerSocaNumber={'1': 1})),
        dict(name='C', tiles=[9, 9, 4], v=208)]),
    '230/400 rotating': dict(distros=_sl('230/400'), screens=[
        dict(name='A', tiles=[10, 8, 6, 4], v=230), dict(name='B', tiles=[9, 3], v=230)]),
    '230/400 whole multi on one leg': dict(distros=_sl('230/400', dict(phasing='whole-ln')), screens=[
        dict(name='A', tiles=[10, 8, 6, 4], v=230), dict(name='B', tiles=[9, 3], v=230)]),
    'one 208V circuit': dict(distros=_sl(), screens=[dict(name='A', tiles=[10], v=208)]),
    'two 120V circuits': dict(distros=_sl(), screens=[dict(name='A', tiles=[10, 4], v=120)]),
    'BUSIEST': dict(distros=_sl(), screens=[
        dict(name='A', tiles=[2], v=208), dict(name='B', tiles=[1, 6, 8], v=120)]),
    'GAP208': dict(distros=_sl(), screens=[dict(name='A', tiles=[12, 10, 12, 2], v=208)]),
    'GAP120': dict(distros=_sl(), screens=[dict(name='A', tiles=[12, 4, 4, 9], v=120)]),
}


@pytest.mark.parametrize('name', list(CASES))
def test_balance_reaches_the_models_exhaustive_optimum(page, name):
    """E5 + E6: the real result of Apply equals the independent model's
    exhaustive lexicographic optimum (imbalance, then the busiest leg,
    never heavier on the busiest leg than now) - and the dialog promised
    exactly that real result."""
    spec = CASES[name]
    out = page.evaluate(RUN_SPEC, spec)
    multis, starts, vll = model_of(spec)
    before, expected = model_expected(multis, starts, vll)
    assert out['before']['imb'] == pytest.approx(before[0], abs=1e-3), 'model and app agree on today'
    assert out['before']['busiest'] == pytest.approx(before[1], abs=1e-3)
    assert out['after']['imb'] == pytest.approx(expected[0], abs=1e-3), (name, out['r'])
    assert out['after']['busiest'] == pytest.approx(expected[1], abs=1e-3), (name, out['r'])
    assert out['r']['after'] == pytest.approx(out['after']['imb'], abs=1e-9), \
        'the dialog promised the real result'
    assert out['r']['afterBusiest'] == pytest.approx(out['after']['busiest'], abs=1e-9)
    assert out['r']['exhaustive'] is True
    if expected == before:
        assert out['r']['moves'] == [], 'nothing beats today: no Apply'


def test_a_lower_imbalance_that_loads_the_busiest_leg_is_not_offered(page):
    """E6: the only lower imbalance on this distro (63.50% -> 63.49%) raises
    the busiest leg 6.67 -> 7.52 A. No Apply, and the dialog says why."""
    spec = CASES['BUSIEST']
    out = page.evaluate(RUN_SPEC, spec)
    assert out['r']['moves'] == []
    assert out['r']['blockedByBusiest'] is True
    assert out['after'] == out['before']
    text = page.evaluate(r"""(spec) => {
        const B = window.__pb;
        const distros = spec.distros.map(d => B.distro(d.id, d.name, d.system, d.extra));
        const layers = spec.screens.map((s, i) => B.screen(i + 1, s.name, s.tiles,
            { powerVoltage: s.v, powerSocaDistro: { 1: 'd1' } }));
        return B.withProject({ layers, distros }, (app) => {
            app.showBalanceDialog('d1');
            const el = document.getElementById('balance-modal');
            const t = el.textContent.replace(/\s+/g, ' ');
            const apply = !!el.querySelector('.balance-apply');
            el.remove();
            return { t, apply };
        });
    }""", spec)
    assert text['apply'] is False
    assert 'Checked all' in text['t']
    assert 'without loading the busiest leg harder' in text['t']


FUZZ_JS = r"""(seed) => {
    const B = window.__pb;
    let s = seed;
    const rnd = (n) => { s = (s * 16807) % 2147483647; return 1 + (s % n); };
    const out = [];
    for (let trial = 0; trial < 60; trial++) {
        const screens = [];
        const n = 1 + rnd(3);
        for (let i = 0; i < n; i++) {
            const v = rnd(2) === 1 ? 120 : 208;
            screens.push(B.screen(i + 1, 'S' + i, Array.from({ length: rnd(5) }, () => rnd(12)),
                { powerVoltage: v, powerSocaDistro: { 1: 'd1' } }));
        }
        // now and then two of them share box No.1, one stored low
        if (n > 1 && rnd(3) === 1) {
            const a = screens[0], b = screens[1];
            const la = Object.keys(a.powerCustomPaths).length;
            const lb = Object.keys(b.powerCustomPaths).length;
            if (la + lb <= 5) {
                a.powerSocaNumber = { 1: 1 };
                b.powerSocaNumber = { 1: 1 };
                b.powerSocaPhasePos = { 1: Array.from({ length: lb }, (_, i) => i + 1) };
            }
        }
        out.push(B.withProject({ layers: screens, distros: [B.distro('d1', 'SL', '120/208')] },
            () => B.balance('d1')));
    }
    return out;
}"""


def test_apply_is_never_worse_and_never_loads_the_busiest_leg(page):
    """Sixty random distros, a third with a shared box whose stored member
    sits below an earlier one: Apply never raises the imbalance or the
    busiest leg, and every promise is the real result."""
    for seed in (7, 21, 99):
        for res in page.evaluate(FUZZ_JS, seed):
            b, a = res['before'], res['after']
            assert a['busiest'] <= b['busiest'] + 1e-6, res
            assert a['imb'] <= b['imb'] + 1e-6, res
            assert res['r']['after'] == pytest.approx(a['imb'], abs=1e-9), res
            if res['r']['moves']:
                assert a['imb'] < b['imb'] - 0.01 or a['busiest'] < b['busiest'] - 0.001, res


def test_a_shared_box_is_scored_as_it_sits(page):
    """E1: box No.1 holds A (four circuits, unstored) and B (one, stored on
    tail 1) - so A sits on tails 2-5, below nothing: 8.4%, busiest 10.84 A.
    A re-deal of the same five tails puts A on 1-4 and B on 5: 36.9%,
    13.91 A. The balancer used to score the box as re-dealt and Apply made
    it worse. Now the current arrangement is the baseline and the moves
    start from where every circuit really is."""
    out = page.evaluate(r"""() => {
        const B = window.__pb;
        const a = B.screen(1, 'A', [2, 1, 11, 10], { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 } });
        const b = B.screen(2, 'B', [12], { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
                                         powerSocaPhasePos: { 1: [1] } });
        return B.withProject({ layers: [a, b], distros: [B.distro('d1', 'SL', '120/208')] }, () => {
            const tails = [B.tails(a), B.tails(b)];
            const res = B.balance('d1');
            return Object.assign(res, { tails, tailsAfter: [B.tails(a), B.tails(b)] });
        });
    }""")
    assert out['tails'] == [[2, 3, 4, 5], [1]]
    assert out['before']['imb'] == pytest.approx(8.4193, abs=1e-3)
    assert out['after']['imb'] <= out['before']['imb'] + 1e-9, out
    assert out['after']['busiest'] <= out['before']['busiest'] + 1e-9, out
    for m in out['r']['moves']:
        assert m['from'] == [2, 3, 4, 5, 1], 'a move starts from where the circuits are'
    if not out['r']['moves']:
        assert out['tailsAfter'] == out['tails']


PAIRED_JS = r"""([ta, tb, bpos]) => {
    const B = window.__pb;
    const d = B.distro('d1', 'EU', '230/400', { ratingA: 63, outputRows: [
        B.row('r1', 'soca', 2, 'ln', 16), B.row('r2', 'harting', 2, 'ln', 16, 'r1'),
        B.row('r3', 'schuko', 9, 'ln', 16)] });
    const a = B.screen(1, 'A', ta, { powerVoltage: 230, powerSocaDistro: { 1: 'd1' },
                                     powerSocaNumber: { 1: 1 } });
    const b = B.screen(2, 'B', tb, { powerVoltage: 230, powerSocaDistro: { 1: 'd1' },
                                     powerSocaNumber: { 1: 3 }, powerSocaPhasePos: { 1: bpos } });
    return B.withProject({ layers: [a, b], distros: [d] }, (app) => {
        const D = app.getDistros()[0];
        const doubled = () => app.distroChecks(D).filter(w => /\(paired\)/.test(w.text)).map(w => w.text);
        const before = doubled();
        const res = B.balance('d1');
        return Object.assign(res, { doubledBefore: before, doubledAfter: doubled(),
                                    tailsA: B.tails(a), tailsB: B.tails(b) });
    });
}"""


def test_balance_never_patches_a_paired_circuit_twice(page):
    """E2: on an EU distro the Hartings (outputs 3-4) are paired with the
    Socapexes (1-2) - the same circuits on a second connector. A on
    Socapex 1 and B on Harting 3 must never land on the same circuit. The
    balancer only checked a multi's own tails, and Apply put B on circuits
    1 and 4 of Socapex 1 under A's loads."""
    out = page.evaluate(PAIRED_JS, [[5, 9, 1, 10], [1, 2], [5, 6]])
    assert out['doubledBefore'] == []
    assert out['doubledAfter'] == [], out
    assert not set(out['tailsA']) & set(out['tailsB']), out
    assert out['after']['imb'] <= out['before']['imb'] + 1e-9


def test_paired_rows_are_never_double_patched_on_random_loads(page):
    """E2, swept: forty random A/B loads on the paired Socapex/Harting
    face - never a double patch after Apply, never worse."""
    cases = page.evaluate(r"""() => {
        let s = 5;
        const rnd = (n) => { s = (s * 16807) % 2147483647; return 1 + (s % n); };
        const out = [];
        for (let i = 0; i < 40; i++) {
            const la = 1 + rnd(3), lb = 1 + rnd(6 - la - 1);
            out.push([Array.from({ length: la }, () => rnd(12)), Array.from({ length: lb }, () => rnd(12)),
                      Array.from({ length: lb }, (_, k) => la + 1 + k)]);
        }
        return out;
    }""")
    for case in cases:
        out = page.evaluate(PAIRED_JS, case)
        assert out['doubledAfter'] == [], (case, out)
        assert out['after']['imb'] <= out['before']['imb'] + 1e-9, (case, out)
        assert out['after']['busiest'] <= out['before']['busiest'] + 1e-9, (case, out)


LOCKED_JS = r"""([lockWho, tiles]) => {
    const B = window.__pb;
    const layers = tiles.map((t, i) => B.screen(i + 1, 'ABC'[i], t, { powerSocaDistro: { 1: 'd1' } }));
    const L = layers['ABC'.indexOf(lockWho)];
    L.locked = true;
    return B.withProject({ layers, distros: [B.distro('d1', 'SL', '120/208')] }, () => {
        const snap = JSON.stringify(L);
        const labels = B.labels(L);
        const res = B.balance('d1');
        return Object.assign(res, { untouched: JSON.stringify(L) === snap,
            hasPos: Object.prototype.hasOwnProperty.call(L, 'powerSocaPhasePos'),
            labelsSame: JSON.stringify(B.labels(L)) === JSON.stringify(labels),
            movedLocked: res.r.moves.some(m => m.layer === lockWho), toasts: window.__pbToasts.slice() });
    });
}"""


@pytest.mark.parametrize('lock_who,tiles', [
    ('A', [[3, 2, 10], [6]]),
    ('A', [[10, 8, 6, 4], [9, 3], [7, 7, 2, 5, 1]]),
    ('C', [[10, 8, 6, 4], [9, 3], [7, 7, 2, 5, 1]]),
])
def test_a_locked_screen_is_held_fixed_by_the_search(page, lock_who, tiles):
    """E3: a locked screen's multi is held where it is - the search scores
    every OTHER multi around it, so the promise is what Apply delivers
    (the audit's case promised 22.2% and delivered 62.5%), the result is
    the model's optimum with the locked multi fixed, the locked screen is
    byte-identical (not even an empty store left on it), and the dialog
    names it."""
    out = page.evaluate(LOCKED_JS, [lock_who, tiles])
    multis = [dict(watts=[100 * t for t in ts], v=208, scheme='paired-ll', number=i + 1)
              for i, ts in enumerate(tiles)]
    starts = [tuple(range(1, len(ts) + 1)) for ts in tiles]
    before, expected = model_expected(multis, starts, 208, fixed=('ABC'.index(lock_who),))
    assert out['untouched'] and not out['hasPos'], out
    assert out['labelsSame'] and not out['movedLocked']
    assert out['toasts'] == [], 'nothing was refused - the locked multi was never proposed'
    assert out['r']['after'] == pytest.approx(out['after']['imb'], abs=1e-9), 'promise = result'
    assert out['after']['imb'] == pytest.approx(expected[0], abs=1e-3), out
    assert out['after']['busiest'] == pytest.approx(expected[1], abs=1e-3), out
    assert [x['layers'] for x in out['r']['locked']] == [[lock_who]]


def _server():
    import app as app_module
    return app_module.current_project


def _open_balance(pg, distro='d1'):
    """Press the distro's own Balance button, a dialog left open by an
    earlier failure closed first."""
    pg.evaluate("() => document.getElementById('balance-modal')?.remove()")
    pg.locator(f'[data-lrd-field="distro-balance-{distro}"]').first.click()
    pg.wait_for_selector('#balance-modal')


def _server_layer(name):
    return next((l for l in (_server().get('layers') or []) if l.get('name') == name), None)


def test_locked_screens_stay_untouched_on_the_server_through_the_dialog(page):
    """E3 end to end: the Balance dialog's Apply on a distro with a locked
    screen - the locked layer is never PUT, the server keeps it byte for
    byte, and the unlocked screen's move lands."""
    page.evaluate(r"""() => {
        const B = window.__pb;
        const a = B.screen(1, 'LockedA', [3, 2, 10], { powerSocaDistro: { 1: 'd1' }, locked: true });
        const b = B.screen(2, 'OpenB', [6], { powerSocaDistro: { 1: 'd1' } });
        return B.open({ name: 'audit', distros: [B.distro('d1', 'SL', '120/208')], layers: [a, b] });
    }""")
    page.wait_for_function('() => window.__pb.inflight()')
    locked_before = copy.deepcopy(_server_layer('LockedA'))
    page.evaluate(r"""() => {
        window.__pbPuts = [];
        if (!window.__pbFetch) {
            window.__pbFetch = window.fetch;
            window.fetch = (url, opts) => {
                const m = ((opts && opts.method) || 'GET').toUpperCase();
                if (m !== 'GET' && window.__pbPuts) window.__pbPuts.push([m, String(url), opts && opts.body ? String(opts.body).slice(0, 200) : '']);
                return window.__pbFetch(url, opts);
            };
        }
    }""")
    _open_balance(page)
    text = ' '.join(page.locator('#balance-modal').inner_text().split())
    assert 'LockedA is locked' in text, text
    page.locator('#balance-modal .balance-apply').click()
    page.wait_for_function('() => window.__pb.inflight()')
    srv = settled(page, lambda: copy.deepcopy(_server_layer('OpenB')),
                  lambda l: (l.get('powerSocaPhasePos') or {}).get('1') == [5])
    assert (srv.get('powerSocaPhasePos') or {}).get('1') == [5], srv
    assert _server_layer('LockedA') == locked_before
    puts = page.evaluate('() => window.__pbPuts')
    locked_id = locked_before['id']
    open_id = _server_layer('OpenB')['id']
    layer_puts = [p[1].split('?')[0] for p in puts if '/api/layer/' in p[1]]
    assert any(u.endswith(f'/api/layer/{open_id}') for u in layer_puts), puts
    assert not any(u.endswith(f'/api/layer/{locked_id}') for u in layer_puts), puts
    page.evaluate('() => { window.fetch = window.__pbFetch; window.__pbFetch = null; window.__pbPuts = null; }')


def test_reset_leaves_a_locked_screens_labels_alone_on_a_shared_box(page):
    """E4: box No.1 is shared by A (locked, unstored - dealt onto tails 3-4)
    and B (stored on 1-2). Reset used to drop B's store and re-deal the box
    around the locked screen: A read SL1-1, SL1-2 with no error. Now the
    reset deals B around A's tails, A's labels do not change - in the
    browser or on the server - and A is named."""
    page.evaluate(r"""() => {
        const B = window.__pb;
        const a = B.screen(1, 'A', [6, 6], { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
                                             locked: true, offset_x: 0 });
        const b = B.screen(2, 'B', [9, 3], { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 1 },
                                             powerSocaPhasePos: { 1: [1, 2] }, offset_x: 2000 });
        return B.open({ name: 'audit', distros: [B.distro('d1', 'SL', '120/208')], layers: [a, b] });
    }""")
    page.wait_for_function('() => window.__pb.inflight()')
    labels = lambda n: page.evaluate(
        "(n) => window.__pb.labels(window.app.project.layers.find(l => l.name === n))", n)
    a0, b0 = labels('A'), labels('B')
    assert a0 == ['SL1-3', 'SL1-4'] and b0 == ['SL1-1', 'SL1-2']
    server_a = copy.deepcopy(_server_layer('A'))
    page.evaluate("""() => { window.__pbToasts = [];
        window.__pbToastSaved = window.app._toast;
        window.app._toast = (m, e, t) => { window.__pbToasts.push(m); return window.__pbToastSaved.call(window.app, m, e, t); }; }""")
    _open_balance(page)
    page.locator('#balance-modal .balance-reset').click()
    page.wait_for_function('() => window.__pb.inflight()')
    toasts = page.evaluate('() => { window.app._toast = window.__pbToastSaved; return window.__pbToasts; }')
    assert labels('A') == a0, 'a locked screen keeps its labels through Reset'
    assert labels('B') == b0
    assert any('A is locked' in t for t in toasts), toasts
    page.wait_for_timeout(300)
    assert _server_layer('A') == server_a


def test_apply_clears_a_legacy_offset_it_replaces(page):
    """E7: A's multi carries a legacy block offset (tails 2-3). Apply's best
    puts it on the natural 1-2, which drops the stored tails - and the old
    offset used to come straight back, delivering 18.1% for a promised
    3.3%. The offset goes with the arrangement it replaced."""
    out = page.evaluate(r"""() => {
        const B = window.__pb;
        const a = B.screen(1, 'A', [1, 3], { powerSocaDistro: { 1: 'd1' }, powerSocaPhaseOffset: { 1: 1 } });
        const b = B.screen(2, 'B', [6, 11, 10], { powerSocaDistro: { 1: 'd1' } });
        return B.withProject({ layers: [a, b], distros: [B.distro('d1', 'SL', '120/208')] }, () => {
            const t0 = B.tails(a);
            const res = B.balance('d1');
            return Object.assign(res, { t0, t1: B.tails(a), off: a.powerSocaPhaseOffset,
                                        pos: a.powerSocaPhasePos || null });
        });
    }""")
    assert out['t0'] == [2, 3]
    assert out['r']['after'] == pytest.approx(out['after']['imb'], abs=1e-9), out
    assert out['after']['imb'] == pytest.approx(3.2506, abs=1e-3), out
    assert out['t1'] == [1, 2]
    assert out['off'] == {}, 'the legacy offset is cleared, the object kept for the PUT'


def test_past_the_cap_the_search_is_bounded_and_says_so(page):
    """Six 3-circuit multis are 20^6 = 64 million arrangements - past the
    50,000 cap. The bounded search still never makes it worse, and the
    dialog says its answer is the best found."""
    out = page.evaluate(r"""() => {
        const B = window.__pb;
        const layers = [[9, 2, 5], [3, 7, 1], [12, 4, 6], [2, 2, 8], [10, 1, 3], [5, 9, 4]]
            .map((t, i) => B.screen(i + 1, 'M' + i, t, { powerSocaDistro: { 1: 'd1' } }));
        return B.withProject({ layers, distros: [B.distro('d1', 'SL', '120/208')] }, (app) => {
            const t0 = performance.now();
            const res = B.balance('d1');
            res.ms = performance.now() - t0;
            // undo the apply for the dialog's own read
            layers.forEach(l => { l.powerSocaPhasePos = {}; });
            app.showBalanceDialog('d1');
            const el = document.getElementById('balance-modal');
            res.text = el.textContent.replace(/\s+/g, ' ');
            el.remove();
            return res;
        });
    }""")
    assert out['r']['exhaustive'] is False
    assert out['r']['total'] == 20 ** 6
    assert out['after']['imb'] <= out['before']['imb'] + 1e-9
    assert out['after']['busiest'] <= out['before']['busiest'] + 1e-9
    assert out['r']['after'] == pytest.approx(out['after']['imb'], abs=1e-9)
    assert 'best found' in out['text'], out['text']
    assert out['ms'] < 5000


def test_a_crowded_direct_output_is_said_in_the_connectors_terms(page):
    """The no-targets dialog sizes a multi by its CONNECTOR: three circuits
    left on a one-circuit True1 direct output are not "partly filled" of
    six - the dialog says the True1 carries one circuit."""
    out = page.evaluate(r"""() => {
        const B = window.__pb;
        const d = B.distro('d1', 'SL', '120/208', { outputRows: [
            B.row('r1', 'soca', 4, 'll', 20), B.row('r2', 'true1', 6, 'll', 20)] });
        const a = B.screen(1, 'A', [8, 6, 4], { powerSocaDistro: { 1: 'd1' }, powerSocaNumber: { 1: 5 } });
        return B.withProject({ layers: [a], distros: [d] }, (app) => {
            app.showBalanceDialog('d1');
            const el = document.getElementById('balance-modal');
            const t = el.textContent.replace(/\s+/g, ' ');
            el.remove();
            return { t, blockers: app._balanceBlockers('d1') };
        });
    }""")
    assert out['blockers']['crowded'] == [
        {'name': 'SL5', 'layers': 'A', 'legs': 3, 'size': 1, 'conn': 'True1'}], out
    assert 'has 3 circuits on a True1, which carries one circuit' in out['t'], out['t']
    assert 'no partly-filled multi lands on it' not in out['t']


RESET_PAIRED_JS = r"""([ta, apos, tb, bpos]) => {
    const B = window.__pb;
    const d = B.distro('d1', 'EU', '230/400', { ratingA: 63, outputRows: [
        B.row('r1', 'soca', 2, 'ln', 16), B.row('r2', 'harting', 2, 'ln', 16, 'r1'),
        B.row('r3', 'schuko', 9, 'ln', 16)] });
    const a = B.screen(1, 'A', ta, { powerVoltage: 230, powerSocaDistro: { 1: 'd1' },
        powerSocaNumber: { 1: 1 }, powerSocaPhasePos: apos ? { 1: apos } : {} });
    const b = B.screen(2, 'B', tb, { powerVoltage: 230, powerSocaDistro: { 1: 'd1' },
        powerSocaNumber: { 1: 3 }, powerSocaPhasePos: { 1: bpos } });
    return B.withProject({ layers: [a, b], distros: [d] }, (app) => {
        const D = app.getDistros()[0];
        const doubled = () => { app._circuitTailCache = null;
            return app.distroChecks(D).filter(w => /\(paired\)/.test(w.text)).length; };
        const before = doubled();
        app.clearPhaseBalance('d1');
        return { before, after: doubled(), tailsA: B.tails(a), tailsB: B.tails(b),
                 toasts: window.__pbToasts.slice() };
    });
}"""


def test_reset_deals_around_a_paired_connectors_circuits(page):
    """Reset re-deals every multi to its natural tails - but on an EU face
    the Hartings (3-4) carry the Socapexes' (1-2) circuits. A sat on 3-6 of
    Socapex 1 and B on 1-2 of Harting 3: no circuit twice. Reset used to put
    both back on 1..L, patching circuits 1 and 2 through both connectors.
    Now A takes its natural 1-4 and B is dealt into the circuits still
    free, 5-6 - no double patch, nothing to name."""
    out = page.evaluate(RESET_PAIRED_JS, [[5, 9, 1, 10], [3, 4, 5, 6], [1, 2], [1, 2]])
    assert out['before'] == 0
    assert out['after'] == 0, out
    assert out['tailsA'] == [1, 2, 3, 4]
    assert out['tailsB'] == [5, 6], out
    assert out['toasts'] == []


def test_reset_leaves_a_multi_that_cannot_fit_around_a_paired_row_and_names_it(page):
    """Seven circuits on one physical Socapex (four through it, three
    through its paired Harting) cannot avoid a double patch whatever Reset
    does. A takes its natural 1-4; B cannot be dealt around it, so it stays
    on the tails it had and is named - Reset does not make it worse."""
    out = page.evaluate(RESET_PAIRED_JS, [[5, 9, 1, 10], None, [1, 2, 3], [4, 5, 6]])
    assert out['tailsA'] == [1, 2, 3, 4]
    assert out['tailsB'] == [4, 5, 6], out
    assert out['after'] <= out['before'], out
    assert any(t.startswith('B stays where it was') and 'paired' in t for t in out['toasts']), out
