"""Undo covers the power feature, and power custom drawing keeps data's scope.

Three live-session reports, one root cause between them:

* "undo isnt working with power change i just made. we need undo to wrok
  everywhere." Between two snapshots of the session the user's screen groups
  vanished while they were undoing a power edit.

* The power render cached each crossing circuit's owner LAYERS on the layer
  itself (`_powerCircuitOwners`), and a grouped plan's stay-home cabinets put
  the layer INSIDE ITS OWN CACHE - project.layers became circular, and every
  JSON.stringify of the project (saveState, updateLayers' PUT, the group
  commit) threw instead of saving. History silently stopped recording the
  moment a grouped wall rendered in Power view, so Ctrl+Z restored whatever
  stale entry was last - which is how a power edit "undid" the groups.
  The cache now stores ids (canvas.js _powerOwnerIdRows) and the history
  snapshot strips leading-underscore runtime caches outright.

* On top of that, none of the power feature's write paths took a snapshot at
  all. They do now, through the same updateLayers(save, action) / saveState
  convention every other edit uses.

Pinned here:

* Rendering a grouped wall in Power view leaves the project serializable,
  and saveState still records afterwards. (The poisoning regression.)
* Snapshots carry no leading-underscore runtime caches.
* Every power write path is one undo entry: undo restores the prior value,
  redo re-applies it. Distros are project-level and ride the same snapshot.
* Removing a distro orphans its multi assignments; ONE undo restores the
  distro WITH the assignments, not a distro with its feeds cut loose.
* The user-shaped case: make groups, make a power edit, Ctrl+Z - the power
  edit reverts and the groups survive.
* Power custom drawing obeys the same scope as data custom drawing, from the
  same authority (canPathReachLayer / getSelectionScopeLayers): the owner and
  its same-canvas group peers accept steps, a screen outside the group
  refuses them, on both the click and the marquee entry point.

Run locally:
    python -m pytest tests/test_power_undo_coverage.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    # The e2e server is shared by every browser suite in the session, and the
    # suites that run after this one expect an ungrouped project - leave the
    # groups (and this module's distros) behind and their guard asserts trip.
    try:
        pg.evaluate("""async () => {
            const project = await (await fetch('/api/project')).json();
            project.groups = [];
            project.distros = [];
            (project.layers || []).forEach(l => { l.group_id = null; });
            await fetch('/api/project', {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(project),
            });
        }""")
    except Exception:
        pass
    context.close()


# Three 4x3 screens of 128px cabinets. S1+S2 share group g1 and sit flush;
# S3 stands apart and ungrouped. 110V/10A/200W puts a 3-cabinet column at
# 600W against an 1,100W circuit: one column fits, two do not, so organized
# tl-v yields one straight column per circuit - the shape the crossing-walk
# pin below leans on.
RESET_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.distros = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    const offsets = [[0, 0], [512, 0], [1400, 0]];
    for (let i = 0; i < offsets.length; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'PowerUndo' + (i + 1),
                columns: 4, rows: 3, cabinet_width: 128, cabinet_height: 128,
                offset_x: offsets[i][0], offset_y: offsets[i][1],
            }),
        });
    }
    project = await (await fetch('/api/project')).json();
    const screens = project.layers.filter(l => (l.type || 'screen') === 'screen');
    const [s1, s2] = screens;
    project.groups = [{ id: 'g1', layer_ids: [s1.id, s2.id], name: 'WALL' }];
    s1.group_id = 'g1'; s2.group_id = 'g1';
    screens.forEach(l => {
        l.powerVoltage = '110'; l.powerAmperage = '10'; l.panelWatts = '200';
        l.powerOrganized = true; l.powerMaximize = false;
        l.powerFlowPattern = 'tl-v';
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('power_undo_test_reset');
    const live = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    app.currentLayer = live[0];
    app.selectedLayerIds = new Set([live[0].id]);
    app.lastSelectedLayerId = live[0].id;
    app.selectionAnchorLayerId = live[0].id;
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    app._circuitTailCache = null;
    r.viewMode = 'power';
    // Small zoom so the loose third screen's cabinets land inside the canvas
    // ELEMENT - a click computed past its right edge never fires mousedown,
    // and a refusal test that never pressed would pass without testing.
    r.zoom = 0.25; r.panX = 60; r.panY = 80;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Power Undo Test Reset');
    app.renderLayers();
    r.render();
    return { ids: live.map(l => l.id), groups: app.project.groups.map(g => g.id) };
}"""


def reset_project(page):
    state = page.evaluate(RESET_JS)
    page.wait_for_timeout(300)
    assert len(state['ids']) == 3, state
    assert state['groups'] == ['g1'], state
    return state


# ── the poisoning regression ──────────────────────────────────────────────

def test_grouped_power_render_leaves_project_serializable(page):
    """After a grouped wall renders in Power view, the owner cache holds ids
    (never layer objects) and JSON.stringify(project) still succeeds."""
    ids = reset_project(page)['ids']
    out = page.evaluate("""(ids) => {
        const app = window.app, r = window.canvasRenderer;
        r.render();
        const owner = app.project.layers.find(l => l.id === ids[0]);
        const rows = owner._powerCircuitOwners;
        const holdsObjects = Array.isArray(rows) && rows.some(row =>
            Array.isArray(row) && row.some(x => x !== null && typeof x === 'object'));
        let circular = false;
        try { JSON.stringify(app.project); } catch (e) { circular = String(e); }
        return { hasRows: Array.isArray(rows), holdsObjects, circular };
    }""", ids)
    # The grouped plan crosses members, so the cache rows must exist - if the
    # walk stopped crossing, this test would pass without testing anything.
    assert out['hasRows'] is True, out
    assert out['holdsObjects'] is False, out
    assert out['circular'] is False, out


def test_save_state_records_after_grouped_power_render(page):
    reset_project(page)
    out = page.evaluate("""() => {
        const app = window.app;
        window.canvasRenderer.render();
        const before = app.history.length;
        app.saveState('poison probe');
        const snap = app.history[app.history.length - 1];
        const layer = snap.project.layers[0];
        return {
            grew: app.history.length === before + 1,
            underscoreKeys: Object.keys(layer).filter(k => k.startsWith('_')),
        };
    }""")
    assert out['grew'] is True, out
    assert out['underscoreKeys'] == [], out


# ── every power write path is one undo entry ──────────────────────────────

# Each case: (label, seed JS or None, mutate JS, read JS). Every function is
# called with `ids` bound. `seed` runs FIRST and must itself go through a
# history-recording path (or be part of the reset), because the convention is
# post-mutation snapshots: undo restores the previous SNAPSHOT, so a pre-state
# that never entered history cannot come back. `read` runs against the
# CURRENT project so undo/redo swaps are visible.
WRITE_PATHS = [
    ("Assign Multi Distro",
     """(ids) => { window.app.addDistro({ name: 'PD' }); }""",
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaDistro(l, 1, app.getDistros()[0].id); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaDistro || {}); }"""),
    ("Rename Multi",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaName(l, 1, 'STAGE LEFT'); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaNames || {}); }"""),
    ("Set Multi Home Run",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaLength(l, 1, '125ft'); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaLengths || {}); }"""),
    ("Change Power Breakout",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setPowerBreakout(l, 'soca-l620'); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return l.powerBreakoutType || null; }"""),
    ("Set Breaker Offset",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaPhaseOffset(l, 1, 1, 4); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaPhaseOffset || {}); }"""),
    ("Move Circuit Tails",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaCircuitPositions(l, 1, [1, 2, 3, 5], 4); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaPhasePos || {}); }"""),
    ("Balance Phase Legs",
     None,
     """(ids) => { const app = window.app;
        app.applyPhaseBalance([{ layerId: ids[0], soca: 1, to: [1, 2, 4, 6] }]); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaPhasePos || {}); }"""),
    ("Reset Phase Offsets",
     # Seed through the recording setter, so the clear under test undoes back
     # to a state history actually holds.
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaCircuitPositions(l, 1, [2, 3, 4, 6], 4); }""",
     """(ids) => { window.app.clearPhaseBalance(); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaPhasePos || {}); }"""),
    ("Split Multi",
     None,
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.splitSocaAfter(l, 1, 2); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify([l.powerSocaSplits || [], l.powerSocaDistro || {}]); }"""),
    ("Un-split Multi",
     # Seed through the recording splitter, so the un-split under test
     # undoes back to a split state history actually holds.
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.splitSocaAfter(l, 1, 2); }""",
     """(ids) => { const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.unsplitSocaAfter(l, 1); }""",
     """(ids) => { const l = window.app.project.layers.find(x => x.id === ids[0]);
        return JSON.stringify(l.powerSocaSplits || []); }"""),
    ("Add Distro",
     None,
     """(ids) => { window.app.addDistro({ name: 'CAMLOK A' }); }""",
     """(ids) => JSON.stringify(window.app.getDistros())"""),
    ("Edit Distro",
     """(ids) => { window.app.addDistro({ name: 'PD' }); }""",
     """(ids) => { const app = window.app;
        app.updateDistro(app.getDistros()[0].id, { name: 'FOH PD', ratingA: 200 }); }""",
     """(ids) => JSON.stringify(window.app.getDistros())"""),
]


@pytest.mark.parametrize("action,seed,mutate,read", WRITE_PATHS,
                         ids=[w[0] for w in WRITE_PATHS])
def test_power_write_is_undoable_and_redoable(page, action, seed, mutate, read):
    ids = reset_project(page)['ids']
    if seed:
        page.evaluate(seed, ids)
        page.wait_for_timeout(250)
    before = page.evaluate(read, ids)
    out = page.evaluate("""async ([mutSrc, ids]) => {
        const app = window.app;
        const mutate = eval(mutSrc);
        const before = app.history.length;
        mutate(ids);
        await new Promise(r => setTimeout(r, 250));
        return { grew: app.history.length > before,
                 last: app.history[app.history.length - 1].action };
    }""", [mutate, ids])
    assert out['grew'] is True, (action, out)
    after = page.evaluate(read, ids)
    assert after != before, (action, "mutation under test changed nothing")

    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(400)
    assert page.evaluate(read, ids) == before, (action, "undo did not restore")

    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(400)
    assert page.evaluate(read, ids) == after, (action, "redo did not re-apply")


def test_remove_distro_undo_restores_assignments(page):
    """One undo brings the distro back WITH the multis still assigned to it."""
    ids = reset_project(page)['ids']
    state = page.evaluate("""async (ids) => {
        const app = window.app;
        // Re-find at every read: the setter round-trips can swap the layer
        // OBJECT in project.layers, and a reference captured before the echo
        // reads the pre-echo state forever.
        const live = () => app.project.layers.find(x => x.id === ids[0]);
        const d = app.addDistro({ name: 'PD 1' });
        app.setSocaDistro(live(), 1, d.id);
        await new Promise(r => setTimeout(r, 250));
        app.setSocaDistro(live(), 2, d.id);
        await new Promise(r => setTimeout(r, 250));
        const assignedBefore = JSON.stringify(live().powerSocaDistro);
        app.removeDistro(d.id);
        await new Promise(r => setTimeout(r, 250));
        const afterRemove = {
            distros: app.getDistros().length,
            assigned: JSON.stringify(live().powerSocaDistro || {}),
        };
        app.undo();
        await new Promise(r => setTimeout(r, 400));
        const afterUndo = {
            distros: app.getDistros().length,
            assigned: JSON.stringify(live().powerSocaDistro || {}),
        };
        app.redo();
        await new Promise(r => setTimeout(r, 400));
        const afterRedo = {
            distros: app.getDistros().length,
            assigned: JSON.stringify(live().powerSocaDistro || {}),
        };
        return { assignedBefore, afterRemove, afterUndo, afterRedo };
    }""", ids)
    assert state['afterRemove']['distros'] == 0
    assert state['afterRemove']['assigned'] == '{}'
    assert state['afterUndo']['distros'] == 1
    assert state['afterUndo']['assigned'] == state['assignedBefore'], state
    assert state['afterRedo']['distros'] == 0
    assert state['afterRedo']['assigned'] == '{}'


def test_groups_survive_power_edit_undo(page):
    """The user-shaped case, on the real keyboard: make groups, make a power
    edit, Ctrl+Z. The power edit reverts; the groups do not."""
    ids = reset_project(page)['ids']
    page.evaluate("""(ids) => {
        const app = window.app;
        const d = app.addDistro({ name: 'PD' });
        const l = app.project.layers.find(x => x.id === ids[0]);
        app.setSocaDistro(l, 1, d.id);
    }""", ids)
    page.wait_for_timeout(300)
    assigned = page.evaluate(
        "(ids) => JSON.stringify(window.app.project.layers"
        ".find(x => x.id === ids[0]).powerSocaDistro || {})", ids)
    assert assigned != '{}'
    page.keyboard.press("ControlOrMeta+z")
    page.wait_for_timeout(500)
    out = page.evaluate("""(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === ids[0]);
        return {
            assigned: JSON.stringify(l.powerSocaDistro || {}),
            groups: (app.project.groups || []).map(g => g.id),
            memberGroup: l.group_id || null,
        };
    }""", ids)
    assert out['assigned'] == '{}', out
    assert out['groups'] == ['g1'], out
    assert out['memberGroup'] == 'g1', out


# ── power custom drawing keeps data's scope ───────────────────────────────

SCOPE_SETUP_JS = """(ids) => {
    const app = window.app, r = window.canvasRenderer;
    const owner = app.project.layers.find(l => l.id === ids[0]);
    owner.flowPattern = 'custom';
    owner.powerFlowPattern = 'custom';
    app.ensureCustomFlowState(owner);
    app.ensureCustomPowerState(owner);
    app.currentLayer = owner;
    app.selectedLayerIds = new Set([owner.id]);
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    r.render();
    return true;
}"""


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def panel_world(page, layer_id, row, col):
    return page.evaluate("""([id, row, col]) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        const p = l.panels.find(q => q.row === row && q.col === col);
        const { dx, dy } = r.getLayerRenderOffset(l);
        const { wx, wy } = r._layerCanvasOffset(l);
        return { x: p.x + p.width / 2 + dx + wx, y: p.y + p.height / 2 + dy + wy };
    }""", [layer_id, row, col])


def click_world(page, wx, wy):
    cx, cy = world_to_client(page, wx, wy)
    page.mouse.click(cx, cy)
    page.wait_for_timeout(200)


PATHS_READ = """([view, ids]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === ids[0]);
    const store = view === 'power' ? (l.powerCustomPaths || {}) : (l.customPortPaths || {});
    const num = view === 'power' ? (l.powerCustomIndex || 1) : (l.customPortIndex || 1);
    return JSON.stringify(store[num] || []);
}"""


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_custom_path_scope_click(page, view):
    """Click entry point: the owner's own cabinet and a group peer's cabinet
    take a step; a cabinet on a screen outside the group refuses it and the
    press falls through to layer select - identically in both views."""
    ids = reset_project(page)['ids']
    page.evaluate(SCOPE_SETUP_JS, ids)
    page.evaluate("(v) => { window.canvasRenderer.viewMode = v; window.canvasRenderer.render(); }", view)
    page.wait_for_timeout(200)

    w = panel_world(page, ids[0], 0, 0)
    click_world(page, w['x'], w['y'])
    own = page.evaluate(PATHS_READ, [view, ids])
    assert '"row":0' in own and '"layerId"' not in own, (view, own)

    w = panel_world(page, ids[1], 0, 0)          # group peer
    click_world(page, w['x'], w['y'])
    peer = page.evaluate(PATHS_READ, [view, ids])
    assert f'"layerId":{ids[1]}' in peer, (view, peer)

    w = panel_world(page, ids[2], 1, 1)          # outside the group
    click_world(page, w['x'], w['y'])
    after = page.evaluate(PATHS_READ, [view, ids])
    assert after == peer, (view, "step landed on an out-of-group screen", after)
    current = page.evaluate("() => window.app.currentLayer && window.app.currentLayer.id")
    assert current == ids[2], "refused press should fall through to layer select"


@pytest.mark.parametrize('view', ['data-flow', 'power'])
def test_custom_path_scope_marquee(page, view):
    """Drag entry point: a marquee swept across all three screens selects
    cabinets of the owner and its peer only - never the loose screen's."""
    ids = reset_project(page)['ids']
    page.evaluate(SCOPE_SETUP_JS, ids)
    page.evaluate("(v) => { window.canvasRenderer.viewMode = v; window.canvasRenderer.render(); }", view)
    page.wait_for_timeout(200)

    start = panel_world(page, ids[0], 0, 0)
    end = panel_world(page, ids[2], 2, 3)
    sx, sy = world_to_client(page, start['x'] - 20, start['y'] - 20)
    ex, ey = world_to_client(page, end['x'] + 20, end['y'] + 20)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move((sx + ex) / 2, (sy + ey) / 2, steps=4)
    page.mouse.move(ex, ey, steps=4)
    page.mouse.up()
    page.wait_for_timeout(300)

    keys = page.evaluate("""(view) => {
        const app = window.app;
        const sel = view === 'power' ? app.powerCustomSelection : app.customSelection;
        return [...(sel || [])];
    }""", view)
    assert len(keys) > 0, (view, "marquee selected nothing")
    swept_layers = {int(k.split(':')[0]) for k in keys}
    assert ids[2] not in swept_layers, (view, sorted(swept_layers), keys)
    assert swept_layers <= {ids[0], ids[1]}, (view, sorted(swept_layers))


# ── the crossing walk stays straight down ─────────────────────────────────

def test_group_power_walk_matches_single_screen_columns(page):
    """tl-v organized with one column per circuit: the grouped wall's
    circuits are each ONE member's column walked top-down, r0->r2 - the same
    shape the members produce ungrouped. (The user's report "wiring should
    be straight down"; the crossing walk must not change column direction.)"""
    ids = reset_project(page)['ids']
    out = page.evaluate("""(ids) => {
        const app = window.app;
        const owner = app.project.layers.find(l => l.id === ids[0]);
        const res = app.calculatePowerAssignments(owner);
        const bad = [];
        (res.circuits || []).forEach((circ, ci) => {
            const lay = (res.layers || [])[ci] || [];
            const owners = new Set(circ.map((p, i) =>
                (lay[i] && lay[i].id !== undefined) ? lay[i].id : owner.id));
            const cols = new Set(circ.map(p => p.col));
            const rowsAsc = circ.every((p, i) => i === 0 || p.row === circ[i - 1].row + 1);
            if (owners.size !== 1 || cols.size !== 1 || !rowsAsc) {
                bad.push({ ci, owners: [...owners], cols: [...cols],
                           rows: circ.map(p => p.row) });
            }
        });
        return { err: res.error, count: (res.circuits || []).length, bad };
    }""", ids)
    assert out['err'] is None, out
    # 4 columns per member x 2 members: the wall walk covers both screens.
    assert out['count'] == 8, out
    assert out['bad'] == [], out
