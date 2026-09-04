"""Undo/redo audit (2026-08-29): the fixes, driven through the live app.

"People complaining of undo and redo being broken" - the audit swept every
mutation path (power/dock, processors/ports, groups/screen-info/canvas-ui,
canvas gestures/core/colors/presets) against the post-mutation snapshot
convention. This module pins the client-side fixes the way
test_power_undo_coverage.py pins the power feature's:

* saveState refuses a no-op: an action that changed nothing must not grow a
  step (blurring an untouched field fired 'Update Properties' before this).
* File > New resets history AFTER the new project loads - the first Ctrl+Z
  in a new project used to restore (and PUT back!) the project just left.
* The eye toggle reaches the server, so a server-sourced adoption cannot
  resurrect a hidden layer - and undo restores it on both sides.
* One dock drag is ONE undo entry: the slot-onto-circuit drop, the chip
  drag-back-to-tray, and the distro-onto-screen drop each recorded 2..2N
  entries through per-setter snapshots before.
* The processor seq counter rides the client's project copy, so an undo
  round-trip cannot make the next add mint a duplicate id.
* A pure read never adds to port_assignments; the stamp every project
  carries is the funnel's, not the read's.
* The gradient funnel's empty-final commit (what the stop-marker drag's
  mouseup now calls) persists AND records exactly one coalesced step.
* Ctrl+Z mid-drag commits the gesture first instead of being silently
  reverted by the next mousemove.

Run locally:
    python3 -m pytest tests/test_undo_audit_browser.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


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
    context.close()


# One 4x3 screen of 128px cabinets at 110V/10A/200W tl-v organized: a
# 3-cabinet column is 600W against an 1,100W circuit, so the wall plans four
# one-column circuits - one multi (soca 1) under the default breakout. The
# reset also strips processors / port_assignments / next_processor_seq /
# distros so every test starts from a project that never defined them (PUT
# replaces wholesale, so deleting the keys client-side deletes them
# server-side). One exception since auto-numbering was retired
# (2026-09-03): the PUT funnel re-stamps the retired-auto mark, so the
# project comes back carrying port_assignments as
# {auto: false, autoRetired: true, pins: []} - the stamp, and nothing else.
RESET_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.distros = [];
    delete project.processors;
    delete project.port_assignments;
    delete project.next_processor_seq;
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'UndoAudit1',
            columns: 4, rows: 3, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0,
        }),
    });
    project = await (await fetch('/api/project')).json();
    project.layers.forEach(l => {
        if ((l.type || 'screen') !== 'screen') return;
        l.powerVoltage = '110'; l.powerAmperage = '10'; l.panelWatts = '200';
        l.powerOrganized = true; l.powerMaximize = false;
        l.powerFlowPattern = 'tl-v';
    });
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('undo_audit_reset');
    const live = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen');
    app.currentLayer = live[0];
    app.selectedLayerIds = new Set([live[0].id]);
    app.lastSelectedLayerId = live[0].id;
    app.selectionAnchorLayerId = live[0].id;
    app._circuitTailCache = null;
    r.viewMode = 'power';
    r.zoom = 0.5; r.panX = 80; r.panY = 80;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Undo Audit Reset');
    app.renderLayers();
    r.render();
    return { ids: live.map(l => l.id) };
}"""


def reset_project(page):
    state = page.evaluate(RESET_JS)
    page.wait_for_timeout(300)
    assert len(state['ids']) == 1, state
    return state


# ── saveState refuses a no-op ─────────────────────────────────────────────

def test_save_state_skips_an_identical_snapshot(page):
    reset_project(page)
    out = page.evaluate("""() => {
        const app = window.app;
        const before = app.history.length;
        app.saveState('Noop Probe');           // nothing changed since reset
        const afterNoop = app.history.length;
        app.project.name = 'Undo Audit Renamed';
        app.saveState('Rename Project');
        const afterReal = app.history.length;
        return { before, afterNoop, afterReal,
                 last: app.history[app.history.length - 1].action };
    }""")
    assert out['afterNoop'] == out['before'], out
    assert out['afterReal'] == out['before'] + 1, out
    assert out['last'] == 'Rename Project', out


def test_update_properties_blur_with_no_change_grows_no_step(page):
    """The real offender: updateLayerFromInputs snapshots unconditionally,
    so blurring an untouched field burned an undo step. The FIRST commit
    after a raw reset may genuinely canonicalize field types (string '110'
    to number, defaults stamped), so the pin is idempotency: the second
    commit of the same inputs must not grow a step."""
    reset_project(page)
    out = page.evaluate("""() => {
        const app = window.app;
        if (typeof app.loadLayerToInputs === 'function') app.loadLayerToInputs();
        app.updateLayerFromInputs();           // canonicalizing commit
        const before = app.history.length;
        app.updateLayerFromInputs();           // inputs now mirror the layer
        return { before, after: app.history.length };
    }""")
    page.wait_for_timeout(200)
    assert out['after'] == out['before'], out


# ── File > New: history belongs to the NEW project ────────────────────────
# (Runs LAST in source order? No - the module guard restores the server
# project afterwards either way, and each test resets first. Kept here with
# the reset discipline.)

def test_new_project_first_undo_does_not_restore_old_project(page):
    reset_project(page)
    out = page.evaluate("""async () => {
        const app = window.app;
        app.createNewProject();
        await new Promise(r => setTimeout(r, 900));
        const baseline = {
            len: app.history.length,
            names: app.history[0].project.layers.map(l => l.name),
        };
        // An edit in the new project, then Ctrl+Z's worth of undo.
        const layer = app.project.layers[0];
        layer.name = 'FreshEdit';
        app.saveState('Rename Layer');
        app.undo();
        await new Promise(r => setTimeout(r, 500));
        return {
            baseline,
            afterUndo: app.project.layers.map(l => l.name),
        };
    }""")
    # History was re-seeded from the NEW project (the old one had
    # 'UndoAudit1'), and undoing the first edit lands on the new project's
    # initial state - not on the project the user left.
    assert 'UndoAudit1' not in out['baseline']['names'], out
    assert out['baseline']['len'] >= 1, out
    assert 'UndoAudit1' not in out['afterUndo'], out
    assert 'FreshEdit' not in out['afterUndo'], out


# ── the eye toggle round-trips ────────────────────────────────────────────

def test_hide_layer_reaches_server_and_undo_restores_it(page):
    ids = reset_project(page)['ids']
    out = page.evaluate("""async (ids) => {
        const app = window.app;
        app.toggleLayerVisibility(ids[0]);
        await new Promise(r => setTimeout(r, 300));
        const server = await (await fetch('/api/project')).json();
        const hiddenOnServer = server.layers.find(
            l => l.id === ids[0]).visible === false;
        app.undo();
        await new Promise(r => setTimeout(r, 500));
        const server2 = await (await fetch('/api/project')).json();
        return {
            hiddenOnServer,
            clientAfterUndo: app.project.layers.find(
                l => l.id === ids[0]).visible !== false,
            serverAfterUndo: server2.layers.find(
                l => l.id === ids[0]).visible !== false,
        };
    }""", ids)
    assert out['hiddenOnServer'] is True, out
    assert out['clientAfterUndo'] is True, out
    assert out['serverAfterUndo'] is True, out


# ── one dock drag, one undo entry ─────────────────────────────────────────

def _multi_state_read():
    return """(ids) => { const l = window.app.project.layers.find(
        x => x.id === ids[0]);
        return JSON.stringify([l.powerSocaDistro || {},
                               l.powerSocaNumber || {}]); }"""


def test_slot_drop_onto_circuit_is_one_entry(page):
    ids = reset_project(page)['ids']
    page.evaluate("(ids) => { window.app.addDistro({ name: 'PD' }); }", ids)
    page.wait_for_timeout(250)
    before = page.evaluate(_multi_state_read(), ids)
    out = page.evaluate("""async (ids) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === ids[0]);
        const socas = app._powerNaming(layer).socas;
        const socaIdx = [...socas.keys()][0];
        const rec = socas.get(socaIdx);
        const grewFrom = app.history.length;
        app._dockDropSlot(
            { distroId: app.getDistros()[0].id, number: 2, title: 'PD 2' },
            { kind: 'run', layerId: layer.id, socaIndex: socaIdx,
              num: rec.circuits[0] });
        await new Promise(r => setTimeout(r, 250));
        return { grew: app.history.length - grewFrom,
                 last: app.history[app.history.length - 1].action };
    }""", ids)
    assert out['grew'] == 1, (
        f'the slot drop is not ONE history entry: {out}')
    after = page.evaluate(_multi_state_read(), ids)
    assert after != before, 'the drop under test changed nothing'
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(400)
    assert page.evaluate(_multi_state_read(), ids) == before, (
        'one undo did not take back distro AND pin together')
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(400)
    assert page.evaluate(_multi_state_read(), ids) == after, (
        'redo did not re-apply the drop')


def test_chip_drag_to_tray_is_one_entry(page):
    ids = reset_project(page)['ids']
    page.evaluate("""(ids) => {
        const app = window.app;
        const d = app.addDistro({ name: 'PD' });
        const layer = app.project.layers.find(l => l.id === ids[0]);
        app.setSocaDistro(layer, 1, d.id);
    }""", ids)
    page.wait_for_timeout(250)
    page.evaluate("""(ids) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === ids[0]);
        app.setSocaNumber(layer, 1, 2);
    }""", ids)
    page.wait_for_timeout(250)
    before = page.evaluate(_multi_state_read(), ids)
    assert before != '[{},{}]'
    out = page.evaluate("""async (ids) => {
        const app = window.app;
        const grewFrom = app.history.length;
        app._dockDropSlot(
            { distroId: app.getDistros()[0].id, number: 2, title: 'PD 2' },
            { kind: 'dock' });
        await new Promise(r => setTimeout(r, 250));
        return { grew: app.history.length - grewFrom,
                 last: app.history[app.history.length - 1].action };
    }""", ids)
    assert out['grew'] == 1, (
        f'the tray drop is not ONE history entry: {out}')
    assert out['last'] == 'Clear Multi', out
    assert page.evaluate(_multi_state_read(), ids) == '[{},{}]'
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(400)
    assert page.evaluate(_multi_state_read(), ids) == before, (
        'one undo did not put the feed back')


def test_distro_drop_onto_screen_is_one_entry(page):
    ids = reset_project(page)['ids']
    page.evaluate("(ids) => { window.app.addDistro({ name: 'PD' }); }", ids)
    page.wait_for_timeout(250)
    before = page.evaluate(_multi_state_read(), ids)
    out = page.evaluate("""async (ids) => {
        const app = window.app;
        const grewFrom = app.history.length;
        app._dockDropDistro(
            { distroId: app.getDistros()[0].id, title: 'PD' },
            { kind: 'screen', layerId: ids[0] });
        await new Promise(r => setTimeout(r, 250));
        const l = app.project.layers.find(x => x.id === ids[0]);
        return { grew: app.history.length - grewFrom,
                 assigned: Object.keys(l.powerSocaDistro || {}).length };
    }""", ids)
    assert out['assigned'] > 0, 'the drop under test assigned nothing'
    assert out['grew'] == 1, (
        f'the distro drop is not ONE history entry: {out}')
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(400)
    assert page.evaluate(_multi_state_read(), ids) == before, (
        'one undo did not unassign every multi the drop fed')


# ── processors: the seq counter rides the snapshots ───────────────────────

def test_processor_add_undo_add_mints_no_duplicate_ids(page):
    reset_project(page)
    out = page.evaluate("""async () => {
        const app = window.app;
        const add = () => app._processorRequest(
            '/api/processors', 'POST',
            { deviceId: 'brompton-sx40' }, 'Add Processor');
        await add();
        await new Promise(r => setTimeout(r, 200));
        const counterStored = app.project.next_processor_seq;
        await add();
        await new Promise(r => setTimeout(r, 200));
        app.undo();
        await new Promise(r => setTimeout(r, 600));
        const afterUndo = (app.project.processors || []).map(p => p.id);
        await add();
        await new Promise(r => setTimeout(r, 300));
        const ids = [];
        (app.project.processors || []).forEach(p => {
            ids.push(p.id);
            (p.slots || []).forEach(s => {
                if (!s.card) return;
                ids.push(s.card.id);
                (s.card.cvts || []).forEach(c => ids.push(c.id));
            });
        });
        const server = await (await fetch('/api/processors')).json();
        const serverIds = server.processors.map(p => p.id);
        return { counterStored, afterUndo, ids, serverIds };
    }""")
    assert out['counterStored'], (
        'the client project copy never learned next_processor_seq', out)
    assert len(out['afterUndo']) == 1, out
    assert len(out['ids']) == len(set(out['ids'])), (
        'duplicate ids in the client tree', out)
    assert len(out['serverIds']) == len(set(out['serverIds'])), (
        'duplicate processor ids on the server', out)


# ── a pure read adds nothing ──────────────────────────────────────────────

def test_resolve_read_does_not_stamp_port_assignments(page):
    """Every project carries port_assignments from birth (or from the PUT
    funnel's retired-auto stamp - auto retired, 2026-09-03), so the line a
    read must hold is narrower than "no key": the state before the read is
    the funnel's bare stamp, and after the read - and the save that
    follows it - the client's copy and the server's are exactly that
    stamp still. No pins appeared, nothing was added."""
    reset_project(page)
    out = page.evaluate("""async () => {
        const app = window.app;
        const server0 = await (await fetch('/api/project')).json();
        const before = server0.port_assignments;
        await app.refreshPortAssignment();
        await new Promise(r => setTimeout(r, 200));
        const client = app.project.port_assignments;
        // And nothing extra may sneak to the server through the next save.
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
        const server = await (await fetch('/api/project')).json();
        return { before, client, after: server.port_assignments };
    }""")
    stamp = {'auto': False, 'autoRetired': True, 'pins': []}
    assert out['before'] == stamp, (
        f'the reset did not leave the funnel\'s bare stamp: {out}')
    assert out['client'] == stamp, f'the read added to the client copy: {out}'
    assert out['after'] == stamp, f'the read reached the server: {out}'


# ── the gradient funnel's final commit ────────────────────────────────────

def test_gradient_drag_commit_is_one_coalesced_entry(page):
    """The stop-marker drag's mouseup now commits through
    _applyGradient({}, true) - live frames record nothing, the final
    commit persists and earns exactly one step, and undo restores the
    dragged stop."""
    reset_project(page)
    out = page.evaluate("""async () => {
        const app = window.app;
        const layer = app.currentLayer;
        layer.gradientEnabled = true;
        app.saveState('Update Gradient Seed');
        const before = JSON.stringify(layer.gradientStops || []);
        const grewFrom = app.history.length;
        // The drag: live frames (isFinal=false), then the mouseup commit.
        for (const pos of [0.2, 0.4, 0.6]) {
            const cur = (app._gradientStops()).map(
                x => ({ pos: x.pos, color: x.color }));
            cur[0].pos = pos;
            app._applyGradient({ gradientStops: cur }, false);
        }
        const during = app.history.length - grewFrom;
        app._applyGradient({}, true);
        await new Promise(r => setTimeout(r, 700));   // debounce is 400ms
        if (typeof app._flushPendingSaveState === 'function') {
            app._flushPendingSaveState();
        }
        const after = app.history.length - grewFrom;
        const dragged = JSON.stringify(
            app.currentLayer.gradientStops || []);
        app.undo();
        await new Promise(r => setTimeout(r, 500));
        const restored = JSON.stringify(
            app.currentLayer.gradientStops || []);
        return { during, after, before, dragged, restored };
    }""")
    assert out['during'] == 0, ('live drag frames must not record', out)
    assert out['after'] == 1, ('the commit must be exactly one step', out)
    assert out['dragged'] != out['before'], out
    assert out['restored'] == out['before'], (
        'undo did not restore the pre-drag stops', out)


# ── Ctrl+Z mid-drag commits the gesture first ─────────────────────────────

def test_undo_during_layer_drag_is_not_reverted_by_the_drag(page):
    ids = reset_project(page)['ids']
    page.evaluate("""() => {
        const r = window.canvasRenderer;
        r.viewMode = 'pixel-map';
        r.zoom = 0.5; r.panX = 100; r.panY = 100;
        r.render();
    }""")
    page.wait_for_timeout(200)
    start = page.evaluate("""(ids) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === ids[0]);
        const rect = r.canvas.getBoundingClientRect();
        return {
            offset: [l.offset_x, l.offset_y],
            cx: rect.left + (l.offset_x + 200) * r.zoom + r.panX,
            cy: rect.top + (l.offset_y + 150) * r.zoom + r.panY,
        };
    }""", ids)
    # Shift+drag = move gesture; Ctrl+Z lands mid-drag.
    page.keyboard.down("Shift")
    page.mouse.move(start['cx'], start['cy'])
    page.mouse.down()
    page.mouse.move(start['cx'] + 120, start['cy'] + 80, steps=5)
    page.keyboard.up("Shift")
    page.keyboard.press("ControlOrMeta+z")
    page.wait_for_timeout(500)
    mid = page.evaluate("""(ids) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === ids[0]);
        return { offset: [l.offset_x, l.offset_y],
                 dragging: !!r.isDraggingLayer,
                 hist: app.history.map(h => h.action),
                 idx: app.historyIndex };
    }""", ids)
    page.mouse.move(start['cx'] + 200, start['cy'] + 160, steps=3)
    page.mouse.up()
    page.wait_for_timeout(400)
    end = page.evaluate("""(ids) => {
        const l = window.app.project.layers.find(x => x.id === ids[0]);
        return [l.offset_x, l.offset_y];
    }""", ids)
    # The undo committed the in-flight move and then took it back - and the
    # still-held mouse must not re-apply it.
    assert mid['dragging'] is False, mid
    assert mid['offset'] == start['offset'], (
        'Ctrl+Z mid-drag did not restore the pre-drag position', mid, start)
    assert end == start['offset'], (
        'the continuing drag re-applied the undone move', end, start)
