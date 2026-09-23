"""History restore keeps the selection and the current layer in step.

An end-to-end pass (2026-09-23) pasted a screen, pressed Cmd+Z 49 times and
Cmd+Shift+Z 49 times, and was left with ``currentLayer: null`` while
``selectedLayerIds`` still held the pasted layer's id. Clicking the Pixel
Map tab then threw inside loadLayerToInputs, and every refresh after the
throw (text panel, port capacity, port labels) was skipped for that click.

Two things are pinned here:

* app-history's restore (undo, redo, and the adoption of the server's
  repaired body) prunes selected ids that no longer exist and re-points
  currentLayer at the first selected layer that does, so after ANY step of
  a full undo/redo walk: currentLayer is non-null whenever the selection is
  non-empty, and every selected id names a layer in the project.
* loadLayerToInputs survives currentLayer being null with a live selection
  - a view-tab click in that state switches the tab, throws nothing, and
  runs the refreshes that follow it in the handler.

Run locally:
    python3 -m pytest tests/test_history_restore.py -v --browser chromium
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
    errors = []
    pg.on('pageerror', lambda err: errors.append(str(err)))
    pg.page_errors = errors
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# Three 2x2 screens of 128px cabinets, then a fresh history rooted on them.
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
    for (let i = 0; i < 3; i++) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'Restore' + (i + 1),
                columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                offset_x: i * 400, offset_y: 0,
            }),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('history_restore_reset');
    const live = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen');
    app.selectLayer(live[0]);
    app._circuitTailCache = null;
    r.viewMode = 'pixel-map';
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('History Restore Reset');
    app.renderLayers();
    r.render();
    return { ids: live.map(l => l.id) };
}"""


def reset_project(page):
    del page.page_errors[:]
    state = page.evaluate(RESET_JS)
    page.wait_for_timeout(300)
    assert len(state['ids']) == 3, state
    return state


# The invariant every step of the walk is held to.
INVARIANT_JS = """() => {
    const app = window.app;
    const ids = app.project.layers.map(l => l.id);
    const selected = app.selectedLayerIds ? [...app.selectedLayerIds] : [];
    return {
        current: app.currentLayer ? app.currentLayer.id : null,
        selected,
        currentInProject: !!app.currentLayer && ids.includes(app.currentLayer.id),
        missing: selected.filter(id => !ids.includes(id)),
        layers: ids,
    };
}"""


def _check_invariant(state, where):
    assert not state['missing'], (
        f'{where}: selected ids not in the project: {state}')
    if state['selected']:
        assert state['current'] is not None, (
            f'{where}: selection without a current layer: {state}')
        assert state['currentInProject'], (
            f'{where}: current layer is not in the project: {state}')
        assert state['current'] in state['selected'], (
            f'{where}: current layer is outside the selection: {state}')


# ── the full undo/redo walk ───────────────────────────────────────────────

def test_undo_redo_walk_keeps_current_layer_with_the_selection(page):
    ids = reset_project(page)['ids']
    # Build a stack: renames, a duplicate, a copy/paste, a move, a
    # multi-select rename. The paste is the one the field report hit.
    built = page.evaluate("""async (ids) => {
        const app = window.app;
        const wait = (ms) => new Promise(r => setTimeout(r, ms));
        const byId = (id) => app.project.layers.find(l => l.id === id);

        byId(ids[0]).name = 'Restore1a';
        app.saveState('Rename Layer');
        byId(ids[1]).name = 'Restore2a';
        app.saveState('Rename Layer');

        app.selectLayer(byId(ids[1]));
        app.duplicateLayer(byId(ids[1]));
        await wait(600);

        app.selectLayer(byId(ids[2]));
        app.copyLayer();
        app.pasteLayer();
        await wait(600);

        // The pasted layer is now the current one; move it and record.
        const pasted = app.currentLayer;
        pasted.offset_x = (Number(pasted.offset_x) || 0) + 100;
        app.saveState('Move Layer');

        // Current layer = the pasted one, inside a two-layer selection.
        // Undoing past the paste drops it from the project: the restore
        // has to re-point currentLayer at the survivor, not leave it null
        // (which is what the field report ended in).
        app.selectedLayerIds = new Set([pasted.id, ids[0]]);
        app.currentLayer = pasted;
        byId(ids[0]).name = 'Restore1b';
        pasted.name = 'PastedB';
        app.saveState('Rename Layers');

        return {
            depth: app.history.length,
            index: app.historyIndex,
            pastedId: pasted.id,
            layers: app.project.layers.length,
        };
    }""", ids)
    assert built['layers'] == 5, built
    assert built['depth'] >= 6, built
    assert built['pastedId'] not in ids, built
    _check_invariant(page.evaluate(INVARIANT_JS), 'after build')

    steps = built['depth'] + 5   # over-walk: extra presses must be no-ops
    for i in range(steps):
        page.evaluate("() => window.app.undo()")
        _check_invariant(page.evaluate(INVARIANT_JS), f'undo {i + 1}')
        page.wait_for_timeout(40)
    page.wait_for_timeout(700)
    bottom = page.evaluate(INVARIANT_JS)
    _check_invariant(bottom, 'after undo settle')
    assert built['pastedId'] not in bottom['layers'], (
        f'undo never got back past the paste: {bottom}')
    assert page.evaluate("() => window.app.historyIndex") == 0

    for i in range(steps):
        page.evaluate("() => window.app.redo()")
        _check_invariant(page.evaluate(INVARIANT_JS), f'redo {i + 1}')
        page.wait_for_timeout(40)
    page.wait_for_timeout(700)
    top = page.evaluate(INVARIANT_JS)
    _check_invariant(top, 'after redo settle')
    assert built['pastedId'] in top['layers'], top
    # The pasted id was pruned when its layer left the project; the
    # survivor of the selection owns the current layer all the way back up.
    assert top['selected'] == [ids[0]], top
    assert top['current'] == ids[0], top
    assert page.page_errors == [], page.page_errors


def test_restore_prunes_selected_ids_that_left_the_project(page):
    ids = reset_project(page)['ids']
    out = page.evaluate("""async (ids) => {
        const app = window.app;
        const byId = (id) => app.project.layers.find(l => l.id === id);
        app.selectLayer(byId(ids[2]));
        app.copyLayer();
        app.pasteLayer();
        await new Promise(r => setTimeout(r, 600));
        const pastedId = app.currentLayer.id;
        // A multi-select spanning an original and the pasted layer.
        app.selectedLayerIds = new Set([pastedId, ids[0]]);
        app.currentLayer = byId(pastedId);
        app.undo();   // back before the paste: pastedId leaves the project
        const afterUndo = {
            current: app.currentLayer ? app.currentLayer.id : null,
            selected: [...app.selectedLayerIds],
            anchor: app.selectionAnchorLayerId,
            last: app.lastSelectedLayerId,
        };
        app.redo();
        const afterRedo = {
            current: app.currentLayer ? app.currentLayer.id : null,
            selected: [...app.selectedLayerIds],
        };
        return { pastedId, afterUndo, afterRedo };
    }""", ids)
    page.wait_for_timeout(700)
    p = out['pastedId']
    assert out['afterUndo']['selected'] == [ids[0]], out
    assert out['afterUndo']['current'] == ids[0], out
    assert out['afterUndo']['anchor'] != p and out['afterUndo']['last'] != p, out
    # The pruned id does not come back with the layer; what is left of the
    # selection still owns the current layer.
    assert out['afterRedo']['selected'] == [ids[0]], out
    assert out['afterRedo']['current'] == ids[0], out
    assert page.page_errors == [], page.page_errors


# ── loadLayerToInputs with no current layer ───────────────────────────────

VIEW_MODES = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']


@pytest.mark.parametrize('mode', VIEW_MODES)
def test_view_tab_click_survives_null_current_layer(page, mode):
    ids = reset_project(page)['ids']
    page.evaluate("""(ids) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(l => l.id === ids[1]));
        app.currentLayer = null;
        // Spy on the refresh that follows loadLayerToInputs in the tab
        // handler: it only runs if loadLayerToInputs returned normally.
        window.__textRefreshes = 0;
        if (!app.__origLoadText) app.__origLoadText = app.loadTextLayerToInputs;
        app.loadTextLayerToInputs = function () {
            window.__textRefreshes += 1;
            return app.__origLoadText.apply(this, arguments);
        };
    }""", ids)
    del page.page_errors[:]
    page.click(f'#view-tabs .view-tab[data-mode="{mode}"]')
    page.wait_for_timeout(150)
    out = page.evaluate("""(mode) => {
        const app = window.app;
        const tab = document.querySelector(
            '#view-tabs .view-tab[data-mode="' + mode + '"]');
        const res = {
            viewMode: window.canvasRenderer.viewMode,
            active: tab.classList.contains('active'),
            textRefreshes: window.__textRefreshes,
            current: app.currentLayer ? app.currentLayer.id : null,
            selected: [...app.selectedLayerIds],
        };
        app.loadTextLayerToInputs = app.__origLoadText;
        delete app.__origLoadText;
        return res;
    }""", mode)
    assert page.page_errors == [], page.page_errors
    assert out['viewMode'] == mode, out
    assert out['active'] is True, out
    assert out['textRefreshes'] >= 1, (
        f'the handler did not get past loadLayerToInputs: {out}')
    assert out['selected'] == [ids[1]], out
