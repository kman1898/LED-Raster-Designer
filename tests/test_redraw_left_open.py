"""A circuit redraw's hold goes wherever the project goes without the session.

While a redraw is open, its hold decides the plan: the cabinets cut off stay
off the walk, and every cable and label sits on the number it had when the
redraw opened. Only the end of the redraw moves them. Read without the hold
the same project says something else, so a project restored or reopened
without it had its cables on the wrong circuits:

- Esc on a cut-back redraw, Ctrl+Z: the project went back to the cut with
  the redraw closed, so the plan stayed renumbered and the cables went home.
  Undo now opens the redraw again, and redo closes it.
- Clear Circuit, Esc, Ctrl+Z: the circuit sat taken over with nothing on it
  and nothing open, and its cabinets took no click. Ending the redraw and
  letting the circuit go are now one undo step, and undo opens the redraw.
- Save with a redraw open, reopen: the repair let the circuit go with no
  cable or label following. The file now says the redraw was open, and the
  show ends it as it opens, the same as Esc. A reload the same.
- A circuit picked up during another redraw and left as it was seeded did
  not go back to automatic, since that redraw's end had renumbered the walk
  around it.

Every gesture here is a real mouse click, key press or tab click.

Every test leaves the shared server project as it found it
(conftest.server_project_guard).
"""

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# What the last File > Save wrote.
WRITTEN = {}


def _caught_write(route):
    body = route.request.post_data_buffer
    start = body.index(b'\r\n\r\n', body.index(b'name="file"')) + 4
    WRITTEN['text'] = body[start:body.rindex(b'\r\n--')].decode('utf-8')
    route.fulfill(status=200, content_type='application/json', body='{"ok": true}')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # A real Windows dialog must never open on the desktop running the tests.
    for kind in ('open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{kind}',
                 lambda r: r.fulfill(status=200, content_type='application/json',
                                     body='{"cancelled": true}'))
    pg.route('**/api/native-dialog/save-file',
             lambda r: r.fulfill(status=200, content_type='application/json',
                                 body=json.dumps({'ok': True, 'path': 'C:/not-written/show.json'})))
    pg.route('**/api/native-dialog/write-file', _caught_write)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    _ready(pg)
    yield pg
    assert errors == [], errors
    context.close()


def _ready(pg):
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function(
        '() => window.app && Array.isArray(window.app.history) && window.app.history.length > 0',
        timeout=60000)
    pg.evaluate(HELPERS_JS)
    _tab(pg, 'power')


# 208 W cabinets on 208 V x 5 A carry four to a circuit, cabled top-down, so
# an 8 x 4 wall is one column a circuit.
HELPERS_JS = r"""
window.__ro = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false, id: 1, name: 'A',
            columns: 8, rows: 4, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 208, powerVoltage: 208, powerAmperage: 5,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
            powerLabelTemplate: 'S1-#', powerLabelOverrides: {},
            group_id: null, powerSocaDistro: {}, powerSocaNumber: {},
            powerSocaLengths: {}, powerCircuitCables: {}, powerSocaKeying: 'index',
            showPowerCableTags: true,
        }, o || {});
        o.panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) {
            o.panels.push({ row: r, col: c,
                x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
                width: o.cabinet_width, height: o.cabinet_height,
                hidden: false, blank: false, halfTile: 'none' });
        }
        return o;
    },
    async j(method, url, body) {
        const r = await fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    async open(layer, more) {
        const app = window.app;
        if (app._overrideEditing) app.endOverrideEdit();
        await app._layerSavesSettled();
        await this.j('PUT', '/api/project', { name: 'Redraw left open', cableUnit: 'ft',
            layers: [this.screen(layer)].concat((more || []).map(o => this.screen(o))) });
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('redraw_left_open');
        app.selectLayer(app.project.layers[0]);
        app.selectedLayerIds = new Set([app.project.layers[0].id]);
        app._circuitTailCache = null;
        await app.refreshProcessors();
        app.resetHistory('Initial State');
        app.renderLayers();
        this.view();
        this.hook();
        this.toasts = [];
        return true;
    },
    view() {
        const r = window.canvasRenderer;
        r.zoom = 0.6; r.panX = 80; r.panY = 80;
        r.render();
    },
    hook() {
        const app = window.app;
        if (app.__roToast) return;
        const real = app._toast;
        app._toast = function (msg, ...rest) {
            window.__ro.toasts.push(String(msg));
            return real.call(this, msg, ...rest);
        };
        app.__roToast = true;
    },
    toasts: [],
    layer() { return window.app.project.layers[0]; },
    inflight() {
        const s = window.app._inflightLayerPuts;
        return !s || s.size === 0;
    },
    at(row, col) {
        const r = window.canvasRenderer, box = r.canvas.getBoundingClientRect();
        return { x: box.left + (col * 128 + 64) * r.zoom + r.panX,
                 y: box.top + (row * 128 + 64) * r.zoom + r.panY };
    },
    // circuit number -> its cabinets ("row.col", walk order)
    plan() {
        const app = window.app;
        app._circuitTailCache = null;
        const out = {};
        app.screenCircuits(this.layer()).forEach(c => {
            out[c.num] = c.panels.map(p => `${p.row}.${p.col}`);
        });
        return out;
    },
    // circuit number -> feet, as stored
    cables() {
        const out = {};
        const s = this.layer().powerCircuitCables || {};
        Object.keys(s).forEach(k => { out[k] = s[k].ft; });
        return out;
    },
    labels() {
        return JSON.parse(JSON.stringify(this.layer().powerLabelOverrides || {}));
    },
    // first cabinet -> feet, for the cables on real circuits
    byHead() {
        const plan = this.plan();
        const out = {};
        Object.entries(this.cables()).forEach(([k, ft]) => {
            if (plan[k]) out[plan[k][0]] = ft;
        });
        return out;
    },
    open_() {
        const app = window.app, ed = app._overrideEditing;
        return ed && app._isOverrideEditing(this.layer(), 'power') ? ed.num : null;
    },
    overrides() { return window.app.getOverrideNums(this.layer(), 'power'); },
    action() {
        const a = window.app;
        return a.history[a.historyIndex].action;
    },
    setCables(map) {
        const app = window.app;
        const l = this.layer();
        Object.entries(map).forEach(([num, ft]) => app.setCircuitCable(l, Number(num), { ft, connector: null }, false));
        app.saveClientSideProperties();
        app.updateLayers([l], true, 'Set Circuit Cable');
    },
};
"""


def _server():
    import app as app_module
    return app_module.current_project


def _srv_cables(project):
    layer = (project.get('layers') or [{}])[0]
    return {k: v.get('ft') for k, v in (layer.get('powerCircuitCables') or {}).items()}


def _srv_labels(project):
    layer = (project.get('layers') or [{}])[0]
    return dict(layer.get('powerLabelOverrides') or {})


def _settle(pg):
    pg.wait_for_function('() => window.__ro.inflight()')


def _wait_server(pg, cables=None, labels=None):
    if cables is not None:
        got = settled(pg, lambda: _srv_cables(copy.deepcopy(_server())), lambda v: v == cables, 8000)
        assert got == cables, got
    if labels is not None:
        got = settled(pg, lambda: _srv_labels(copy.deepcopy(_server())), lambda v: v == labels, 8000)
        assert got == labels, got


def _open(pg, layer=None, cables=None, more=None):
    if pg.evaluate("() => window.canvasRenderer.viewMode") != 'power':
        _tab(pg, 'power')
    pg.evaluate("([l, m]) => window.__ro.open(l, m)", [layer or {}, more or []])
    _settle(pg)
    if cables:
        pg.evaluate("(m) => window.__ro.setCables(m)", {str(k): v for k, v in cables.items()})
        _settle(pg)


def _at(pg, row, col):
    p = pg.evaluate("([r, c]) => window.__ro.at(r, c)", [row, col])
    return p['x'], p['y']


def _redraw(pg, row, col):
    """Right-click a cabinet, Redraw circuit."""
    x, y = _at(pg, row, col)
    pg.mouse.click(x, y, button='right')
    item = pg.locator('[data-action="ovr-redraw"]')
    item.wait_for(state='visible')
    item.click()
    _settle(pg)


def _click(pg, row, col):
    x, y = _at(pg, row, col)
    pg.mouse.click(x, y)
    _settle(pg)


def _alt_click(pg, row, col):
    x, y = _at(pg, row, col)
    pg.mouse.move(x, y)
    pg.keyboard.down('Alt')
    pg.mouse.click(x, y)
    pg.keyboard.up('Alt')
    _settle(pg)


def _esc(pg):
    pg.locator('#main-canvas').hover()
    pg.keyboard.press('Escape')
    _settle(pg)


def _undo(pg):
    pg.keyboard.press('Control+z')
    _settle(pg)


def _redo(pg):
    pg.keyboard.press('Control+Shift+z')
    _settle(pg)


def _clear_circuit(pg):
    pg.locator('#power-custom-clear-circuit').click()
    _settle(pg)


def _tab(pg, mode):
    pg.locator(f'[data-mode="{mode}"]').click()
    pg.wait_for_function("(m) => window.canvasRenderer && window.canvasRenderer.viewMode === m", arg=mode)
    _settle(pg)


def _save(pg):
    """File > Save through the toolbar button; the text it wrote."""
    WRITTEN.clear()
    pg.locator('#btn-save').click()
    settled(pg, lambda: WRITTEN.get('text'), bool, 8000)
    assert WRITTEN.get('text'), 'nothing was written'
    return WRITTEN['text']


def _reopen(pg, text):
    assert pg.evaluate("(t) => window.app._openProjectText(t, { source: 'file' })", text) is True
    _settle(pg)
    pg.evaluate("() => { window.__ro.view(); }")


def _reload(pg):
    pg.reload(wait_until='domcontentloaded')
    _ready(pg)
    pg.evaluate("() => { window.__ro.hook(); window.__ro.view(); }")
    _settle(pg)


def _plan(pg):
    return pg.evaluate("() => window.__ro.plan()")


def _cables(pg):
    return pg.evaluate("() => window.__ro.cables()")


def _labels(pg):
    return pg.evaluate("() => window.__ro.labels()")


def _heads(pg):
    return pg.evaluate("() => window.__ro.byHead()")


def _editing(pg):
    return pg.evaluate("() => window.__ro.open_()")


def _overrides(pg):
    return pg.evaluate("() => window.__ro.overrides()")


def _action(pg):
    return pg.evaluate("() => window.__ro.action()")


def _toasts(pg):
    return ' '.join(pg.evaluate("() => window.__ro.toasts.slice()"))


# Each cable on its column's first cabinet, as the cut-back cases start and
# must end: 25' on column 4, 30' on column 5, 50' on column 7 (1-based).
ON_THEIR_COLUMNS = {'0.3': 25, '0.4': 30, '0.6': 50}

CUT_PLAN_HEADS = {'3': '0.2', '4': '2.2', '5': '0.3', '6': '0.4', '8': '0.6', '9': '0.7'}


def _start_cut(pg):
    """8 x 4, one column a circuit, cables on 4, 5 and 7. Column 3 redrawn
    and cut back to its top half, the redraw still open."""
    _open(pg, {}, {4: 25, 5: 30, 7: 50})
    _redraw(pg, 0, 2)
    _click(pg, 1, 2)
    assert _editing(pg) == 3
    assert _plan(pg)['3'] == ['0.2', '1.2']
    assert _cables(pg) == {'4': 25, '5': 30, '7': 50}


def _assert_cut_ended(pg):
    """The cut-back redraw is over: the bottom half of column 3 is circuit 4,
    the circuits after it one up, each cable on its column."""
    assert _editing(pg) is None
    plan = _plan(pg)
    assert {n: plan[n][0] for n in CUT_PLAN_HEADS} == CUT_PLAN_HEADS, plan
    assert _cables(pg) == {'5': 25, '6': 30, '8': 50}
    assert _heads(pg) == ON_THEIR_COLUMNS
    _wait_server(pg, {'5': 25, '6': 30, '8': 50})


def _assert_cut_open(pg):
    """The cut-back redraw is open: nothing renumbered, nothing moved."""
    assert _editing(pg) == 3
    assert _overrides(pg) == [3]
    plan = _plan(pg)
    assert plan['3'] == ['0.2', '1.2'], plan
    assert plan['4'][0] == '0.3' and plan['8'][0] == '0.7', plan
    assert len(plan) == 8, plan
    assert _cables(pg) == {'4': 25, '5': 30, '7': 50}
    assert _heads(pg) == ON_THEIR_COLUMNS
    _wait_server(pg, {'4': 25, '5': 30, '7': 50})


# ── Esc on a cut-back redraw, then undo ───────────────────────────────────

def test_undo_after_esc_opens_the_cut_redraw_again(page):
    """Esc moves the cables to 5, 6 and 8. One Ctrl+Z opens the redraw, so
    the plan is back with them. Redo ends it again; a second round the same.
    Undo walks on through the cut and the takeover."""
    pg = page
    _start_cut(pg)
    _esc(pg)
    _assert_cut_ended(pg)
    assert _action(pg) == 'End Circuit Redraw'
    _undo(pg)
    _assert_cut_open(pg)
    assert pg.locator('#power-custom-controls').is_visible()
    _redo(pg)
    _assert_cut_ended(pg)
    _undo(pg)
    _assert_cut_open(pg)
    _undo(pg)
    assert _editing(pg) == 3
    assert _plan(pg)['3'] == ['0.2', '1.2', '2.2', '3.2']
    _undo(pg)
    assert _editing(pg) is None
    assert _overrides(pg) == []
    assert _cables(pg) == {'4': 25, '5': 30, '7': 50}


def test_the_reopened_redraw_goes_on_drawing_and_ends_with_the_cables_right(page):
    """Reopened by undo it is a redraw like any other: the cabinets cut off
    are still its own to click, and Esc ends it."""
    pg = page
    _start_cut(pg)
    _esc(pg)
    _undo(pg)
    _click(pg, 2, 2)
    assert _plan(pg)['3'] == ['0.2', '1.2', '2.2']
    assert _editing(pg) == 3
    assert _cables(pg) == {'4': 25, '5': 30, '7': 50}
    _esc(pg)
    plan = _plan(pg)
    assert plan['4'] == ['3.2'], plan
    assert _heads(pg) == ON_THEIR_COLUMNS
    assert _cables(pg) == {'5': 25, '6': 30, '8': 50}
    _wait_server(pg, {'5': 25, '6': 30, '8': 50})


def test_esc_with_no_cable_to_move_leaves_nothing_open_on_redo(page):
    """No cable moves, so the end of the redraw is no step of its own: undo
    goes back over the cut, and redo lands where Esc left off, closed."""
    pg = page
    _open(pg)
    _redraw(pg, 0, 2)
    _click(pg, 1, 2)
    _esc(pg)
    assert _editing(pg) is None
    assert _plan(pg)['4'] == ['2.2', '3.2']
    _undo(pg)
    assert _editing(pg) == 3
    assert _plan(pg)['3'] == ['0.2', '1.2', '2.2', '3.2']
    _redo(pg)
    assert _editing(pg) is None
    assert _plan(pg)['4'] == ['2.2', '3.2']


def test_a_tab_switch_after_undo_ends_the_redraw_again(page):
    """The reopened redraw ends at a tab switch as any redraw does."""
    pg = page
    _start_cut(pg)
    _esc(pg)
    _undo(pg)
    _tab(pg, 'data-flow')
    _assert_cut_ended(pg)
    _tab(pg, 'power')
    _assert_cut_ended(pg)


def test_undo_on_another_tab_keeps_the_plan_and_cables_together(page):
    """A tab switch ended the redraw; Ctrl+Z on the Data tab opens it again
    and it waits there, on the Power tab, with the plan and the cables back
    together. Esc ends it as usual."""
    pg = page
    _start_cut(pg)
    _tab(pg, 'data-flow')
    _assert_cut_ended(pg)
    _undo(pg)
    assert pg.evaluate("() => window.canvasRenderer.viewMode") == 'data-flow'
    _assert_cut_open(pg)
    _tab(pg, 'power')
    _assert_cut_open(pg)
    assert pg.locator('#power-custom-controls').is_visible()
    _esc(pg)
    _assert_cut_ended(pg)


def test_undo_picks_the_redrawn_screen_back_up(page):
    """Another screen picked after the redraw ended: undo opens the redraw
    on its own screen, and the next click draws there."""
    pg = page
    _open(pg, {}, {4: 25, 5: 30, 7: 50},
          [{'id': 2, 'name': 'B', 'offset_y': 640, 'columns': 4}])
    _redraw(pg, 0, 2)
    _click(pg, 1, 2)
    _esc(pg)
    # the second screen's first cabinet, row 5 of the world grid
    _click(pg, 5, 0)
    assert pg.evaluate("() => window.app.currentLayer.id") == 2
    _undo(pg)
    assert pg.evaluate("() => window.app.currentLayer.id") == 1
    _assert_cut_open(pg)
    _click(pg, 2, 2)
    assert _plan(pg)['3'] == ['0.2', '1.2', '2.2']


def test_undo_then_save_and_reopen_ends_the_redraw_the_same(page):
    pg = page
    _start_cut(pg)
    _esc(pg)
    _undo(pg)
    text = _save(pg)
    _reopen(pg, text)
    _assert_cut_ended(pg)


# ── Clear Circuit, Esc, undo ──────────────────────────────────────────────
#
# Circuit 3 drawn on the top half of column 3 leaves the bottom half as
# circuit 4, so column 4 is 5 and column 8 is 9.

SHORT = {'powerCustomOverrides': [3],
         'powerCustomPaths': {'3': [{'row': 0, 'col': 2}, {'row': 1, 'col': 2}]},
         'powerCustomIndex': 3,
         'powerLabelOverrides': {'3': 'THREE', '4': 'FOUR', '5': 'FIVE', '9': 'NINE'}}
SHORT_CABLES = {5: 25, 6: 30, 8: 50}
SHORT_LABELS = {'3': 'THREE', '4': 'FOUR', '5': 'FIVE', '9': 'NINE'}
HANDED_BACK_LABELS = {'3': 'THREE', '4': 'FIVE', '8': 'NINE'}
HANDED_BACK_CABLES = {'4': 25, '5': 30, '7': 50}


def _start_cleared(pg):
    _open(pg, SHORT, SHORT_CABLES)
    _redraw(pg, 0, 2)
    _clear_circuit(pg)
    assert _editing(pg) == 3


def _assert_handed_back(pg):
    assert _editing(pg) is None
    assert _overrides(pg) == []
    plan = _plan(pg)
    assert len(plan) == 8 and plan['3'][0] == '0.2' and plan['8'][0] == '0.7', plan
    assert _labels(pg) == HANDED_BACK_LABELS
    assert _cables(pg) == HANDED_BACK_CABLES
    assert _heads(pg) == ON_THEIR_COLUMNS
    _wait_server(pg, HANDED_BACK_CABLES, HANDED_BACK_LABELS)


def test_undo_after_a_cleared_redraw_opens_it_with_its_cabinets_clickable(page):
    """Esc hands the number back in one step. Ctrl+Z opens the redraw: the
    circuit reads empty, the labels and cables are home, and a click on its
    own cabinet draws. Before this the redraw stayed shut and the click did
    nothing."""
    pg = page
    _start_cleared(pg)
    _esc(pg)
    _assert_handed_back(pg)
    assert _action(pg) == 'Return Circuit To Auto'
    assert 'nothing was drawn on circuit THREE, so it went back to automatic' in _toasts(pg)
    _undo(pg)
    assert _editing(pg) == 3
    assert _overrides(pg) == [3]
    assert _action(pg) == 'Power Custom Clear Circuit'
    assert _labels(pg) == SHORT_LABELS
    assert _cables(pg) == {str(k): v for k, v in SHORT_CABLES.items()}
    _wait_server(pg, {str(k): v for k, v in SHORT_CABLES.items()}, SHORT_LABELS)
    plan = _plan(pg)
    assert '3' not in plan and plan['4'] == ['2.2', '3.2'] and plan['5'][0] == '0.3', plan
    _click(pg, 0, 2)
    assert _plan(pg)['3'] == ['0.2']
    assert _editing(pg) == 3


def test_redo_after_undo_of_a_cleared_redraw_hands_it_back_again(page):
    pg = page
    _start_cleared(pg)
    _esc(pg)
    _undo(pg)
    _redo(pg)
    _assert_handed_back(pg)
    _undo(pg)
    assert _editing(pg) == 3
    _esc(pg)
    _assert_handed_back(pg)


def test_a_cleared_redraw_undone_then_a_tab_switch_hands_it_back(page):
    pg = page
    _start_cleared(pg)
    _esc(pg)
    _undo(pg)
    _tab(pg, 'data-flow')
    _assert_handed_back(pg)
    _tab(pg, 'power')
    _assert_handed_back(pg)


def test_a_cleared_redraw_ended_by_another_circuit_undoes_in_one_step(page):
    """Alt+click another circuit ends the cleared redraw: the hand-back and
    the takeover are one step, so undo never lands on the number held with
    nothing open."""
    pg = page
    _start_cleared(pg)
    _alt_click(pg, 0, 6)
    assert 3 not in _overrides(pg)
    assert _editing(pg) is not None
    assert _heads(pg) == ON_THEIR_COLUMNS
    _undo(pg)
    assert _editing(pg) == 3
    assert _overrides(pg) == [3]
    assert _labels(pg) == SHORT_LABELS
    assert _cables(pg) == {str(k): v for k, v in SHORT_CABLES.items()}


# ── Save with a redraw open ───────────────────────────────────────────────

def test_save_with_a_cleared_redraw_open_reopens_the_same_as_esc(page):
    """Saved with Clear Circuit done and no Esc. The session goes on as it
    was; the file says the redraw was open; the show ends it as it opens."""
    pg = page
    _start_cleared(pg)
    text = _save(pg)
    assert _editing(pg) == 3, 'Save ended the redraw'
    saved = json.loads(text)
    assert saved['openPowerRedraw']['num'] == 3
    assert 'openPowerRedraw' not in pg.evaluate("() => window.app.project")
    _reopen(pg, text)
    _assert_handed_back(pg)
    said = _toasts(pg)
    assert 'nothing was drawn on circuit THREE, so it went back to automatic' in said, said
    assert 'openPowerRedraw' not in _server()
    assert 'openPowerRedraw' not in pg.evaluate("() => window.app.project")
    assert pg.evaluate("() => window.app.history.length") == 1
    # Saved again it is a plain show.
    again = _save(pg)
    assert 'openPowerRedraw' not in json.loads(again)
    _reopen(pg, again)
    _assert_handed_back(pg)


def test_save_with_a_cut_back_redraw_open_reopens_the_same_as_esc(page):
    pg = page
    _start_cut(pg)
    text = _save(pg)
    _assert_cut_open(pg)
    _reopen(pg, text)
    _assert_cut_ended(pg)
    # The live show carries on: the circuit redraws and undoes as normal.
    _redraw(pg, 0, 2)
    assert _editing(pg) == 3
    _esc(pg)
    _assert_cut_ended(pg)


def _cut_with_label(pg):
    _open(pg, {'powerLabelOverrides': {'8': 'NINE'}}, {4: 25, 5: 30, 7: 50})
    _redraw(pg, 0, 2)
    _click(pg, 1, 2)


@pytest.mark.parametrize('end', ['esc', 'tab', 'reopen', 'reload'])
def test_a_cut_back_redraw_ends_the_same_whichever_way_it_ends(page, end):
    """A cut back keeps a typed label on its number (only a redraw handed
    back moves them), so NINE reads on the next column to the left, and the
    cables stay on their cabinets. All four ways end alike."""
    pg = page
    _cut_with_label(pg)
    if end == 'esc':
        _esc(pg)
    elif end == 'tab':
        _tab(pg, 'data-flow')
    elif end == 'reopen':
        _reopen(pg, _save(pg))
    else:
        _reload(pg)
    assert _editing(pg) is None
    assert _heads(pg) == ON_THEIR_COLUMNS
    assert _labels(pg) == {'8': 'NINE'}
    assert _plan(pg)['8'][0] == '0.6'
    _wait_server(pg, {'5': 25, '6': 30, '8': 50}, {'8': 'NINE'})


def test_a_redraw_saved_open_goes_on_after_the_save(page):
    """Save changes nothing about the redraw in hand: the cabinets stay held
    and Esc ends it, cables carried."""
    pg = page
    _start_cut(pg)
    _save(pg)
    _click(pg, 2, 2)
    assert _plan(pg)['3'] == ['0.2', '1.2', '2.2']
    _esc(pg)
    assert _heads(pg) == ON_THEIR_COLUMNS
    assert _cables(pg) == {'5': 25, '6': 30, '8': 50}


def test_a_show_saved_with_nothing_open_says_nothing_of_a_redraw(page):
    pg = page
    _start_cut(pg)
    _esc(pg)
    assert 'openPowerRedraw' not in json.loads(_save(pg))


def test_an_open_redraw_does_not_outlive_its_show(page):
    """Reopening with no redraw in the file drops the one in hand, cabinets
    held and all, even on the same screen id and circuit number."""
    pg = page
    _start_cut(pg)
    _esc(pg)
    text = _save(pg)
    _undo(pg)
    assert _editing(pg) == 3
    _reopen(pg, text)
    _assert_cut_ended(pg)
    assert pg.evaluate("() => window.app._powerHeld") is None


def test_undo_entries_never_put_the_record_on_the_project(page):
    pg = page
    _start_cut(pg)
    assert pg.evaluate("() => window.app.history.every(h => !('openPowerRedraw' in h.project))")
    assert pg.evaluate("() => !!window.app.history[window.app.historyIndex].redraw")


# ── Reload with a redraw open ─────────────────────────────────────────────

def test_reload_with_a_cut_back_redraw_open_ends_it_like_esc(page):
    pg = page
    _start_cut(pg)
    _reload(pg)
    _assert_cut_ended(pg)
    assert pg.evaluate("() => window.localStorage.getItem('lrd_open_power_redraw')") is None
    # Once only: a second reload has nothing left to end.
    _reload(pg)
    _assert_cut_ended(pg)


def test_reload_with_a_cleared_redraw_open_hands_it_back(page):
    pg = page
    _start_cleared(pg)
    _reload(pg)
    _assert_handed_back(pg)


def test_reload_after_undo_opened_the_redraw_ends_it_again(page):
    pg = page
    _start_cut(pg)
    _esc(pg)
    _undo(pg)
    _reload(pg)
    _assert_cut_ended(pg)


def test_reload_after_esc_has_nothing_to_end(page):
    pg = page
    _start_cut(pg)
    _esc(pg)
    assert pg.evaluate("() => window.localStorage.getItem('lrd_open_power_redraw')") is None
    _reload(pg)
    _assert_cut_ended(pg)


def test_a_record_that_no_longer_fits_the_project_is_dropped(page):
    """A record left in the browser by a page that died, read over a project
    with no such circuit taken over: nothing opens and nothing moves."""
    pg = page
    _open(pg, {}, {4: 25})
    pg.evaluate("""() => window.localStorage.setItem('lrd_open_power_redraw', JSON.stringify(
        { layerId: 1, num: 3, held: 3, keys: ['1:0,2'], before: [], seed: null }))""")
    _reload(pg)
    assert _editing(pg) is None
    assert _overrides(pg) == []
    assert _cables(pg) == {'4': 25}
    assert pg.evaluate("() => window.localStorage.getItem('lrd_open_power_redraw')") is None


# ── A second circuit picked up and left unchanged ─────────────────────────

def _start_second(pg):
    """Column 3 cut back, then Alt+click column 6 with the redraw open: that
    ends the cut, the walk renumbers, and the circuit taken over keeps the
    number it was picked up with."""
    _start_cut(pg)
    _alt_click(pg, 0, 5)
    assert _editing(pg) == 6
    assert _overrides(pg) == [3, 6]
    assert _heads(pg) == ON_THEIR_COLUMNS


def _assert_second_gone(pg):
    assert _editing(pg) is None
    assert _overrides(pg) == [3]
    plan = _plan(pg)
    heads = {n: cells[0] for n, cells in plan.items()}
    assert [heads[str(n)] for n in range(5, 10)] == ['0.3', '0.4', '0.5', '0.6', '0.7'], plan
    assert _cables(pg) == {'5': 25, '6': 30, '8': 50}
    assert _heads(pg) == ON_THEIR_COLUMNS
    _wait_server(pg, {'5': 25, '6': 30, '8': 50})


def test_a_circuit_picked_up_during_a_redraw_and_left_alone_goes_back(page):
    pg = page
    _start_second(pg)
    _esc(pg)
    _assert_second_gone(pg)
    assert _action(pg) == 'Return Circuit To Auto'
    # One undo: open again, the plan as it stood. Redo lets it go again.
    _undo(pg)
    assert _editing(pg) == 6
    assert _overrides(pg) == [3, 6]
    assert _heads(pg) == ON_THEIR_COLUMNS
    _redo(pg)
    _assert_second_gone(pg)
    # Undo all the way: the first redraw comes back open too.
    _undo(pg)
    _undo(pg)
    _assert_cut_open(pg)


def test_a_circuit_left_alone_goes_back_at_a_tab_switch(page):
    pg = page
    _start_second(pg)
    _tab(pg, 'data-flow')
    _assert_second_gone(pg)


def test_a_circuit_left_alone_goes_back_when_saved_open_and_reopened(page):
    pg = page
    _start_second(pg)
    text = _save(pg)
    _reopen(pg, text)
    _assert_second_gone(pg)


def test_a_circuit_left_alone_goes_back_on_a_reload(page):
    pg = page
    _start_second(pg)
    _reload(pg)
    _assert_second_gone(pg)


def test_a_circuit_left_alone_goes_back_when_a_third_is_picked_up(page):
    pg = page
    _start_second(pg)
    _alt_click(pg, 0, 7)
    assert 6 not in _overrides(pg)
    assert _heads(pg) == ON_THEIR_COLUMNS


def test_a_circuit_picked_up_and_changed_stays_drawn(page):
    """Cut back, it is a real redraw: it keeps its number and its drawing."""
    pg = page
    _start_second(pg)
    _click(pg, 1, 5)
    _esc(pg)
    assert _overrides(pg) == [3, 6]
    assert _plan(pg)['6'] == ['0.5', '1.5']


def test_a_redrawn_circuit_reopened_without_a_change_keeps_its_drawing(page):
    """The seed is the walk's own takeover, not any path: a real redraw
    reopened and closed untouched stays, as it always has."""
    pg = page
    _open(pg, SHORT, SHORT_CABLES)
    _redraw(pg, 0, 2)
    _esc(pg)
    assert _overrides(pg) == [3]
    assert _plan(pg)['3'] == ['0.2', '1.2']
