"""Per-run overrides - the HYBRID engine (data ports and power circuits).

The motivating wall: auto-cable the whole screen, then redraw the ONE run
that jumped somewhere a cable cannot go. An override is a single port or
circuit number the user has taken over (layer.customPortOverrides /
layer.powerCustomOverrides); its path lives in the same customPortPaths /
powerCustomPaths dict every hand-drawn path has always lived in. The engines
(calculatePortAssignments / calculatePowerAssignments) then lay the automatic
walk over every cabinet an override has not claimed and SKIP the overridden
numbers, so a run the user never touched keeps the number it always had.

Pinned here, always relative to the same screen's own automatic baseline
rather than to absolute capacity figures, so a published-capacity change
cannot fail these for the wrong reason:

* SEEDING IS A NO-OP. Taking a run over seeds its path with the cabinets it
  carries right now, so the assignment after the override is byte-equal to
  the assignment before it. "Nothing visibly changes at entry" is the
  contract the gesture was specified with.
* EXCLUSION + RE-FLOW. Cabinets on an override path are off the automatic
  walk; cabinets removed from the path re-flow into the automatic ports. No
  cabinet is fed twice, none is dropped.
* NUMBER SKIPPING. The walk's ports take 1, 2, 3... skipping every
  overridden number - port 2 overridden means no automatic port is ever
  numbered 2.
* THE GROUP WALK STAYS ALIVE. Whole-screen custom on any member still takes
  the group back to per-member routing (unchanged); a per-run override does
  NOT - that was the whole point ("the last run jumps a group but i dont
  want it to jump").
* BACK TO AUTO restores the automatic baseline exactly.
* WHOLE-SCREEN CUSTOM IS UNTOUCHED. A layer on flowPattern 'custom' ignores
  the overrides array outright.

Run locally:
    python -m pytest tests/test_run_overrides_engine.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# One screen (or two matching members for the group tests) built through the
# real add endpoint, so panels carry real geometry. 4 columns x 6 rows of
# 256px cabinets on COEX 1G at 8-bit/60 (659,722 px a port) organizes into
# 3 data ports (two 262,144 px rows each), and 1000 W cabinets on a
# 208 V / 20 A circuit (4160 W) pack 4 to a circuit - both walks split
# mid-wall several times over, which is what makes exclusion and renumbering
# observable. Grouped, the two members make an 8-wide wall whose every row is
# its own crossing port.
HELPERS_JS = """
window.__ovr = {
    async reset(memberCount) {
        const app = window.app, r = window.canvasRenderer;
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        for (let i = 0; i < memberCount; i++) {
            await fetch('/api/layer/add', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: 'Ovr' + (i + 1),
                    columns: 4, rows: 6, cabinet_width: 256, cabinet_height: 256,
                    offset_x: i * 1024, offset_y: 0,
                }),
            });
        }
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('run_override_engine_reset');
        const screens = app.project.layers.filter(
            l => (l.type || 'screen') === 'screen');
        screens.forEach(l => {
            l.flowPattern = 'tl-h';
            l.powerFlowPattern = 'tl-h';
            l.powerOrganized = false;
            l.powerMaximize = false;
            l.powerVoltage = 208;
            l.powerAmperage = 20;
            l.panelWatts = 1000;
            l.processorType = 'novastar-coex-1g';
            l.bitDepth = 8;
            l.frameRate = 60;
            l.customPortPaths = {};
            l.customPortOverrides = [];
            l.powerCustomPaths = {};
            l.powerCustomOverrides = [];
        });
        if (memberCount > 1) {
            app.selectedLayerIds = new Set(screens.map(l => l.id));
            app.currentLayer = screens[0];
            await app.groupSelectedLayers();
        }
        app.currentLayer = screens[0];
        app.selectedLayerIds = new Set([screens[0].id]);
        app._overrideEditing = null;
        app._overrideHover = null;
        if (app.customSelection) app.customSelection.clear();
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        r.viewMode = 'data-flow';
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        return { ids: screens.map(l => l.id) };
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    // The data assignment as comparable facts: one row per cabinet, in
    // engine order, addressed by (layerId, row, col) - panel objects mean
    // nothing across page.evaluate.
    dataMap(id) {
        const app = window.app, layer = this.layer(id);
        return (app.calculatePortAssignments(layer) || []).map(it => ({
            port: it.port,
            layerId: (it.layerId === undefined || it.layerId === null)
                ? layer.id : it.layerId,
            row: it.panel.row, col: it.panel.col,
        }));
    },

    // The power assignment the same way, carrying the engine's own numbers.
    powerMap(id) {
        const app = window.app, layer = this.layer(id);
        const res = app.calculatePowerAssignments(layer);
        return {
            error: res.error ? res.error.message : null,
            circuits: (res.circuits || []).map((panels, i) => ({
                num: res.nums ? res.nums[i] : i + 1,
                panels: panels.map((p, j) => ({
                    layerId: (res.layers && res.layers[i] && res.layers[i][j])
                        ? res.layers[i][j].id : layer.id,
                    row: p.row, col: p.col,
                })),
            })),
        };
    },
};
"""


def reset(page, members=1):
    state = page.evaluate("(n) => window.__ovr.reset(n)", members)
    page.wait_for_timeout(400)
    assert len(state['ids']) == members, state
    return state['ids']


def data_map(page, layer_id):
    return page.evaluate("(id) => window.__ovr.dataMap(id)", layer_id)


def power_map(page, layer_id):
    return page.evaluate("(id) => window.__ovr.powerMap(id)", layer_id)


def override_data_run(page, layer_id, num):
    return page.evaluate("""([id, num]) => {
        const app = window.app;
        app.overrideRun(window.__ovr.layer(id), 'data', num);
        const l = window.__ovr.layer(id);
        return {
            overrides: app.getOverrideNums(l, 'data'),
            path: (l.customPortPaths[num] || []).map(e => ({
                row: e.row, col: e.col,
                layerId: (e.layerId === undefined || e.layerId === null)
                    ? l.id : e.layerId,
            })),
            editing: app._overrideEditing,
            activePort: l.customPortIndex,
        };
    }""", [layer_id, num])


def ports_of(rows):
    return sorted({r['port'] for r in rows})


def cabinets_of(rows):
    return sorted((r['layerId'], r['row'], r['col']) for r in rows)


# ── the premise ───────────────────────────────────────────────────────────

def test_the_baseline_screen_splits_into_several_runs(page):
    """Everything below compares against the automatic baseline; a screen
    that fits on one port and one circuit would pass all of it vacuously."""
    (lid,) = reset(page)
    base = data_map(page, lid)
    assert len(ports_of(base)) >= 2, ports_of(base)
    pbase = power_map(page, lid)
    assert pbase['error'] is None
    assert len(pbase['circuits']) >= 2, pbase


# ── data: seeding, exclusion, numbering ──────────────────────────────────

def test_taking_a_port_over_changes_nothing_at_entry(page):
    (lid,) = reset(page)
    base = data_map(page, lid)
    target = ports_of(base)[1]
    out = override_data_run(page, lid, target)
    assert out['overrides'] == [target]
    assert out['activePort'] == target
    assert out['editing'] == {'layerId': lid, 'kind': 'data', 'num': target}
    # the seeded path IS the run the walk was feeding, in the same order
    seeded = [(e['layerId'], e['row'], e['col']) for e in out['path']]
    walked = [(r['layerId'], r['row'], r['col']) for r in base if r['port'] == target]
    assert seeded == walked
    # and the whole assignment is byte-equal to the baseline
    assert data_map(page, lid) == base


def test_cabinets_freed_from_an_override_reflow_into_the_walk(page):
    (lid,) = reset(page)
    base = data_map(page, lid)
    target = ports_of(base)[1]
    override_data_run(page, lid, target)
    dropped = page.evaluate("""([id, num]) => {
        const l = window.__ovr.layer(id);
        return l.customPortPaths[num].pop();
    }""", [lid, target])
    after = data_map(page, lid)
    # nothing fed twice, nothing dropped: the union still covers exactly the
    # baseline's cabinets, the freed one included
    assert cabinets_of(after) == cabinets_of(base)
    assert len(cabinets_of(after)) == len(after), "a cabinet is on two runs"
    # the freed cabinet is back on an AUTOMATIC port, not the override
    freed = next(r for r in after
                 if (r['row'], r['col']) == (dropped['row'], dropped['col']))
    assert freed['port'] != target


def test_no_automatic_port_ever_takes_an_overridden_number(page):
    (lid,) = reset(page)
    base = data_map(page, lid)
    target = ports_of(base)[1]
    override_data_run(page, lid, target)
    # shrink the override to one cabinet so the walk has to renumber around it
    page.evaluate("""([id, num]) => {
        const l = window.__ovr.layer(id);
        l.customPortPaths[num] = l.customPortPaths[num].slice(0, 1);
    }""", [lid, target])
    after = data_map(page, lid)
    override_rows = [r for r in after if r['port'] == target]
    assert len(override_rows) == 1, "the overridden number leaked into the walk"
    # the automatic numbers are a clean 1, 2, 3... with only `target` skipped
    auto_ports = sorted({r['port'] for r in after if r['port'] != target})
    expected = [n for n in range(1, len(auto_ports) + 2) if n != target][:len(auto_ports)]
    assert auto_ports == expected, (auto_ports, target)


def test_ports_required_is_the_highest_number_in_use(page):
    (lid,) = reset(page)
    base = data_map(page, lid)
    target = ports_of(base)[1]
    override_data_run(page, lid, target)
    required = page.evaluate(
        "(id) => window.app.getLayerPortsRequired(window.__ovr.layer(id))", lid)
    assert required == max(ports_of(data_map(page, lid)))


def test_back_to_auto_restores_the_baseline_exactly(page):
    (lid,) = reset(page)
    base = data_map(page, lid)
    target = ports_of(base)[1]
    override_data_run(page, lid, target)
    # redraw it first, so the restore is doing real work
    page.evaluate("""([id, num]) => {
        const l = window.__ovr.layer(id);
        l.customPortPaths[num] = l.customPortPaths[num].slice(0, 2);
    }""", [lid, target])
    assert data_map(page, lid) != base
    page.evaluate("""([id, num]) => {
        window.app.returnRunToAuto(window.__ovr.layer(id), 'data', num);
    }""", [lid, target])
    assert data_map(page, lid) == base
    assert page.evaluate(
        "(id) => window.app.getOverrideNums(window.__ovr.layer(id), 'data')",
        lid) == []
    assert page.evaluate("() => window.app._overrideEditing") is None


def test_whole_screen_custom_ignores_the_overrides_array(page):
    (lid,) = reset(page)
    stale = page.evaluate("""(id) => {
        const app = window.app, l = window.__ovr.layer(id);
        // whole-screen custom, with a drawn path in the shared dict - the
        // exact state a screen lands in when its overrides pre-date the
        // switch to custom mode
        l.flowPattern = 'custom';
        l.customPortPaths = { 1: [{ row: 0, col: 0 }, { row: 0, col: 1 }] };
        const before = window.__ovr.dataMap(id);
        l.customPortOverrides = [1, 2];
        return {
            before,
            after: window.__ovr.dataMap(id),
            overridden: app.isRunOverridden(l, 'data', 1),
            has: app.hasRunOverrides(l, 'data'),
        };
    }""", lid)
    # the engine's walk (custom mode's auto-equivalent upper bound) does not
    # move by a cabinet when the array appears, and the predicates read it as
    # inert - custom mode's semantics are exactly what they were
    assert stale['after'] == stale['before']
    assert stale['overridden'] is False
    assert stale['has'] is False


# ── power: the same contract on circuits ─────────────────────────────────

def test_taking_a_circuit_over_changes_nothing_at_entry(page):
    (lid,) = reset(page)
    base = power_map(page, lid)
    target = base['circuits'][1]['num']
    out = page.evaluate("""([id, num]) => {
        const app = window.app, l = window.__ovr.layer(id);
        app.overrideRun(l, 'power', num);
        return {
            overrides: app.getOverrideNums(l, 'power'),
            editing: app._overrideEditing,
            active: l.powerCustomIndex,
        };
    }""", [lid, target])
    assert out['overrides'] == [target]
    assert out['editing'] == {'layerId': lid, 'kind': 'power', 'num': target}
    assert out['active'] == target
    assert power_map(page, lid) == base


def test_automatic_circuits_skip_the_overridden_number(page):
    (lid,) = reset(page)
    base = power_map(page, lid)
    target = base['circuits'][1]['num']
    page.evaluate("""([id, num]) => {
        const l = window.__ovr.layer(id);
        window.app.overrideRun(l, 'power', num);
        l.powerCustomPaths[num] = l.powerCustomPaths[num].slice(0, 1);
    }""", [lid, target])
    after = power_map(page, lid)
    nums = [c['num'] for c in after['circuits']]
    assert nums == sorted(nums), "circuits came back out of number order"
    assert nums.count(target) == 1
    override_row = next(c for c in after['circuits'] if c['num'] == target)
    assert len(override_row['panels']) == 1
    # union unchanged: every baseline cabinet is fed exactly once
    def cabs(pm):
        out = []
        for c in pm['circuits']:
            out.extend((p['layerId'], p['row'], p['col']) for p in c['panels'])
        return sorted(out)
    assert cabs(after) == cabs(base)
    assert len(set(cabs(after))) == len(cabs(after))
    # screenCircuits reports the engine's numbers, not ordinals
    nums_via_screen = page.evaluate(
        "(id) => window.app.screenCircuits(window.__ovr.layer(id)).map(c => c.num)",
        lid)
    assert nums_via_screen == nums


def test_circuit_back_to_auto_restores_the_baseline(page):
    (lid,) = reset(page)
    base = power_map(page, lid)
    target = base['circuits'][1]['num']
    page.evaluate("""([id, num]) => {
        const l = window.__ovr.layer(id);
        window.app.overrideRun(l, 'power', num);
        l.powerCustomPaths[num] = l.powerCustomPaths[num].slice(0, 1);
        window.app.returnRunToAuto(l, 'power', num);
    }""", [lid, target])
    assert power_map(page, lid) == base


# ── the motivating case: a grouped wall keeps its combined walk ──────────

def test_the_group_walk_survives_an_override(page):
    ids = reset(page, members=2)
    owner = ids[0]
    plan_alive = page.evaluate("""(id) => {
        const p = window.app.getAutoRoutePlan(window.__ovr.layer(id), 'data');
        return p ? p.isOwner : null;
    }""", owner)
    assert plan_alive is True, "the two matching members must cross to begin with"
    base = data_map(page, owner)
    # a run that actually reaches the second member, so the seed carries
    # cross-member steps
    crossing = sorted({r['port'] for r in base if r['layerId'] == ids[1]})
    assert crossing, "no run crosses - the layout no longer exercises the seam"
    target = crossing[0]
    out = override_data_run(page, owner, target)
    assert any(e['layerId'] == ids[1] for e in out['path']), (
        "the seed lost the peer's cabinets")
    # the walk is STILL the combined one - this is the line that used to die
    # the moment anything on the wall was custom
    still_alive = page.evaluate("""(id) => {
        const p = window.app.getAutoRoutePlan(window.__ovr.layer(id), 'data');
        return p ? p.isOwner : null;
    }""", owner)
    assert still_alive is True
    assert data_map(page, owner) == base
    # whole-screen custom on a member still kills it - unchanged on purpose
    killed = page.evaluate("""(id) => {
        const l = window.__ovr.layer(id);
        l.flowPattern = 'custom';
        const p = window.app.getAutoRoutePlan(l, 'data');
        l.flowPattern = 'tl-h';
        return p;
    }""", owner)
    assert killed is None


def test_group_counting_stays_whole_under_an_override(page):
    ids = reset(page, members=2)
    owner, peer = ids
    base_total = page.evaluate("""(ids) => ids.reduce((t, id) =>
        t + window.app.getLayerPortsRequired(window.__ovr.layer(id)), 0)""", ids)
    base = data_map(page, owner)
    target = ports_of(base)[1]
    override_data_run(page, owner, target)
    after_total = page.evaluate("""(ids) => ids.reduce((t, id) =>
        t + window.app.getLayerPortsRequired(window.__ovr.layer(id)), 0)""", ids)
    assert after_total == base_total
    # the peer still reports 0 - the wall's ports live on the owner
    assert page.evaluate(
        "(id) => window.app.getLayerPortsRequired(window.__ovr.layer(id))",
        peer) == 0
