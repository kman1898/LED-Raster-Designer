"""Grouping always finishes, or says why it can't (1.7.0 beta.3).

The report: while the group drag was being built (6dc299f), grouping a
selection with an existing group between its screens in the Screens list
seemed to hang: the Group action never completed.

What it was: the harness awaited app.groupSelectedLayers() on screens that
disagreed on their processor (screens made through the API carry none, and
selecting a screen fills its processor in from Preferences), so the Group
Settings dialog opened and the await waited for an answer nobody gave. The
page itself never stopped: every way to group finishes with a group between
the screens, closed or open, across Show Look canvases and across canvases,
and the tests below hold each one to a time limit.

One real never-settling promise was found on the way: a second Group
Settings ask while the first was open overwrote the first one's resolver, so
the earlier grouping waited forever (the lock question already answered the
earlier ask Cancel). The dialog's backdrop keeps a mouse from asking twice,
so nobody could reach it by hand; it now answers the earlier ask Cancel.

Each wait below is a browser-side wait with a time limit, so a page that
hangs fails the test instead of hanging the run.

Run locally:
    python -m pytest tests/test_group_hang.py -v
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

LIMIT_MS = 5000


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _cancelled(route):
    route.fulfill(status=200, content_type='application/json',
                  body=json.dumps({'ok': False, 'cancelled': True}))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real Windows dialog may open on the owner's desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{path}', _cancelled)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


# C1 holds, top to bottom: L2, the group G (B over A), L1. C2 holds M.
# `same`: every screen on one processor, as screens made in the app are;
# without it only the screens that were selected carry one.
SEED_JS = """async (opts) => {
    const app = window.app;
    if (app._groupSettingsResolve) app.closeGroupSettingsDialog(null);
    if (app._groupLockResolve) app.closeGroupLockDialog(null);
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    proj.canvases = proj.canvases.slice(0, 1);
    proj.canvases[0].name = 'C1';
    proj.active_canvas_id = proj.canvases[0].id;
    await j('PUT', '/api/project', proj);
    const c1 = proj.canvases[0].id;
    const c2 = (await j('POST', '/api/canvas', {name: 'C2'})).active_canvas_id;
    const add = async (name, cid, x) => (await j('POST', '/api/layer/add', {name, columns: 2, rows: 1,
        cabinet_width: 100, cabinet_height: 100, offset_x: x, offset_y: 0, canvas_id: cid})).id;
    const ids = {};
    ids.L1 = await add('L1', c1, 0);
    ids.A = await add('A', c1, 300);
    ids.B = await add('B', c1, 600);
    ids.L2 = await add('L2', c1, 900);
    ids.M = await add('M', c2, 0);
    await j('PUT', `/api/canvas/${c1}/active`);
    if (opts.same) {
        const all = await j('GET', '/api/project');
        all.layers.forEach(l => { l.processorType = 'novastar-armor'; });
        await j('PUT', '/api/project', all);
    }
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('group_hang_seed');
    app.setSelectedLayersByIds([ids.A, ids.B], ids.A);
    await app.groupSelectedLayers();
    const gid = app.project.groups[0].id;
    if (opts.expand) app.setGroupExpanded(gid, true);
    if (opts.showB) await app.moveLayerShowCanvas(ids.B, c2);
    app.selectLayer(app.project.layers.find(l => l.id === ids.L1));
    app.renderLayers();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Group Hang Seed');
    window.__toasts = [];
    if (!app.__toastSpy) {
        app.__toastSpy = true;
        const orig = app._toast;
        app._toast = function (msg, isError, ms) {
            window.__toasts.push(String(msg));
            return orig.call(this, msg, isError, ms);
        };
    }
    return {ids, gid, c1, c2};
}"""

# The list as drawn: [canvas, [row, ...]] with a group as G[members].
LIST_JS = """() => [...document.querySelectorAll('#layers-list .canvas-group')].map(cg => [
    cg.querySelector('.canvas-name-input').value,
    [...cg.querySelector('.canvas-group-body').children].map(el =>
        el.classList.contains('screen-group')
            ? 'G[' + [...el.querySelectorAll('.layer-item .layer-name-input')].map(i => i.value).join(',') + ']'
            : el.querySelector('.layer-name-input').value)])"""

# The page point of a screen's first cabinet.
PT_JS = """(lid) => {
    const a = window.app, r = window.canvasRenderer;
    const layer = a.project.layers.find(l => l.id === lid);
    const p = layer.panels[0];
    const off1 = r.getLayerRenderOffset(layer), off2 = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + off1.dx + off2.wx, wy = p.y + p.height / 2 + off1.dy + off2.wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + wx * r.zoom + r.panX, y: rect.top + wy * r.zoom + r.panY};
}"""


def _seed(pg, mode='pixel-map', **opts):
    pg.keyboard.press('Escape')
    pg.locator(f'.view-tab[data-mode="{mode}"]').first.click()
    pg.wait_for_timeout(250)
    return pg.evaluate(SEED_JS, {'same': True, **opts})


def _row(lid):
    return f'#layers-list .layer-item[data-layer-id="{lid}"] .layer-info'


def _click(pg, lid, mods=None):
    pg.locator(_row(lid)).click(modifiers=mods or [], timeout=LIMIT_MS)


def _finishes(pg, condition, arg=None, what='the action'):
    """`condition` (a page function) holds within LIMIT_MS. The wait runs in
    the browser with a time limit, so a page that hangs fails here."""
    try:
        pg.wait_for_function(condition, arg=arg, timeout=LIMIT_MS)
    except Exception as exc:  # the Playwright timeout
        raise AssertionError(f'{what} did not finish in {LIMIT_MS} ms') from exc


def _list_is(pg, want, what):
    try:
        _finishes(pg, f"(w) => JSON.stringify(({LIST_JS})()) === w",
                  json.dumps(want, separators=(",", ":")), what=what)
    except AssertionError as exc:
        raise AssertionError(f'{exc}: the list shows {pg.evaluate(LIST_JS)}, wanted {want}') from None


def _pick_group_screens(pg):
    opt = pg.locator('#context-menu .menu-option[data-action="group-screens"]')
    assert opt.is_visible(), 'Group Screens is on the menu'
    opt.click(timeout=LIMIT_MS)


def _grouped(pg, history='Group Screens'):
    _finishes(pg, "(h) => window.app.history.length === 2 && window.app.history[1].action === h",
              history, what=history)


# ── every way to group, with a group between the screens ─────────────────

def _row_menu(pg, ids, seed):
    pg.locator(_row(ids['L1'])).click(button='right', timeout=LIMIT_MS)
    _pick_group_screens(pg)


def _canvas_menu(pg, ids, seed):
    pt = pg.evaluate(PT_JS, ids['L1'])
    pg.mouse.click(pt['x'], pt['y'], button='right')
    _pick_group_screens(pg)


def _add_selected(pg, ids, seed):
    pg.locator(f'#layers-list .screen-group[data-group-id="{seed["gid"]}"] .screen-group-menu-btn').click(
        timeout=LIMIT_MS)
    pg.locator('.canvas-menu-popup [data-action="add"]').click(timeout=LIMIT_MS)


def _ctrl_pick(pg, ids):
    _click(pg, ids['L2'])
    _click(pg, ids['L1'], ['Control'])


def _shift_range(pg, ids):
    _click(pg, ids['L2'])
    _click(pg, ids['L1'], ['Shift'])


def _with_member(pg, ids):
    _click(pg, ids['L1'])
    _click(pg, ids['A'], ['Control'])


CASES = [
    # (id, select, gesture, history, C1's rows after)
    ('around, row menu', _ctrl_pick, _row_menu, 'Group Screens', ['G[L2,L1]', 'G[B,A]']),
    ('around, canvas menu', _ctrl_pick, _canvas_menu, 'Group Screens', ['G[L2,L1]', 'G[B,A]']),
    ('range across, row menu', _shift_range, _row_menu, 'Group Screens', ['G[L2,B,A,L1]']),
    ('range across, canvas menu', _shift_range, _canvas_menu, 'Group Screens', ['G[L2,B,A,L1]']),
    ('Add Selected Screens', _ctrl_pick, _add_selected, 'Add to Group', ['G[L2,B,A,L1]']),
]


@pytest.mark.parametrize('expand', [False, True], ids=['closed', 'open'])
@pytest.mark.parametrize('case', CASES, ids=[c[0] for c in CASES])
def test_grouping_with_a_group_between_finishes(page, case, expand):
    pg, errors = page
    _name, select, gesture, history, want = case
    seed = _seed(pg, expand=expand)
    ids = seed['ids']
    select(pg, ids)
    gesture(pg, ids, seed)
    _grouped(pg, history)
    _list_is(pg, [['C1', want], ['C2', ['M']]], 'the list redraw')
    assert errors == []


def test_a_screen_and_a_member_group_and_the_old_group_lets_go(page):
    """L1 and A (open group): A leaves the group, B is left alone and
    loose (a group of one is not a group)."""
    pg, errors = page
    seed = _seed(pg, expand=True)
    ids = seed['ids']
    _with_member(pg, ids)
    _row_menu(pg, ids, seed)
    _grouped(pg)
    _list_is(pg, [['C1', ['L2', 'B', 'G[A,L1]']], ['C2', ['M']]], 'the list redraw')
    assert errors == []


@pytest.mark.parametrize('mode', ['show-look', 'data-flow', 'power'])
def test_grouping_finishes_with_show_look_canvases_apart(page, mode):
    """B, a member, on C2 in Show Look only, so the group's rows sit on two
    canvases. A range from L2 to L1 groups across what is left on C1."""
    pg, errors = page
    seed = _seed(pg, mode, showB=True)
    ids = seed['ids']
    _list_is(pg, [['C1', ['L2', 'G[A]', 'L1']], ['C2', ['M', 'B']]], 'the seed')
    _shift_range(pg, ids)
    _row_menu(pg, ids, seed)
    _grouped(pg)
    _list_is(pg, [['C1', ['G[L2,A,L1]']], ['C2', ['M', 'B']]], 'the list redraw')
    assert errors == []


def test_grouping_across_canvases_finishes(page):
    pg, errors = page
    seed = _seed(pg)
    ids = seed['ids']
    _click(pg, ids['L1'])
    _click(pg, ids['M'], ['Control'])
    _row_menu(pg, ids, seed)
    _grouped(pg)
    assert errors == []


def test_a_locked_screen_asks_and_then_says_why(page):
    """A locked and an unlocked screen around the group: the lock question,
    then either a group or a toast that names the screen. Never silence."""
    pg, errors = page
    seed = _seed(pg)
    ids = seed['ids']
    pg.evaluate("(id) => { window.app.project.layers.find(l => l.id === id).locked = true;"
                " window.app.renderLayers(); }", ids['L1'])
    _ctrl_pick(pg, ids)
    _row_menu(pg, ids, seed)
    _finishes(pg, "() => getComputedStyle(document.getElementById('group-lock-modal')).display === 'block'",
              what='the lock question')
    pg.locator('#group-lock-lock').click(timeout=LIMIT_MS)
    _finishes(pg, "() => window.app.history.length === 2 || window.__toasts.length > 0",
              what='Lock the whole group')
    toasts = pg.evaluate("() => window.__toasts")
    if toasts:
        assert any('L1' in t for t in toasts), toasts
    assert errors == []


# ── what the harness waited on: the Group Settings question ──────────────

def test_screens_that_disagree_are_asked_and_the_answer_finishes(page):
    """The case that looked like a hang. L1 carries a processor (it was
    selected), A and B carry none: the dialog asks, names the field, and
    Apply groups within the limit. The awaited call settles with the id."""
    pg, errors = page
    seed = _seed(pg, same=False, expand=True)
    ids = seed['ids']
    pg.evaluate("""([a, b, c, d]) => {
        window.app.setSelectedLayersByIds([a, b, c, d], a);
        window.__groupCall = 'pending';
        window.app.groupSelectedLayers().then(v => { window.__groupCall = v; });
    }""", [ids['L1'], ids['A'], ids['B'], ids['L2']])
    _finishes(pg, "() => getComputedStyle(document.getElementById('group-settings-modal')).display === 'block'",
              what='the settings question')
    assert 'PROCESSOR' in pg.locator('#group-settings-conflicts').inner_text().upper()
    pg.locator('#group-settings-apply').click(timeout=LIMIT_MS)
    _finishes(pg, "() => typeof window.__groupCall === 'string' && window.__groupCall.startsWith('g')",
              what='Apply to Group')
    _grouped(pg)
    assert errors == []


def test_cancel_finishes_and_changes_nothing(page):
    pg, errors = page
    seed = _seed(pg, same=False)
    ids = seed['ids']
    pg.evaluate("""([a, b]) => {
        window.app.setSelectedLayersByIds([a, b], a);
        window.__groupCall = 'pending';
        window.app.groupSelectedLayers().then(v => { window.__groupCall = v; });
    }""", [ids['L1'], ids['L2']])
    _finishes(pg, "() => getComputedStyle(document.getElementById('group-settings-modal')).display === 'block'",
              what='the settings question')
    pg.locator('#group-settings-cancel').click(timeout=LIMIT_MS)
    _finishes(pg, "() => window.__groupCall === null", what='Cancel')
    assert pg.evaluate("() => window.app.history.map(h => h.action)") == ['Group Hang Seed']
    assert pg.evaluate("() => window.app.project.groups.length") == 1
    assert errors == []


def test_a_second_ask_settles_the_first(page):
    """The one promise that never settled: a second Group Settings ask while
    the first was open overwrote the first one's resolver. The first now
    settles as Cancel and the second, answered, groups."""
    pg, errors = page
    seed = _seed(pg, same=False)
    ids = seed['ids']
    pg.evaluate("""([a, b, c]) => {
        const app = window.app;
        window.__first = 'pending'; window.__second = 'pending';
        app.setSelectedLayersByIds([a, b], a);
        app.groupSelectedLayers().then(v => { window.__first = v; });
        app.setSelectedLayersByIds([a, c], a);
        app.groupSelectedLayers().then(v => { window.__second = v; });
    }""", [ids['L1'], ids['L2'], ids['A']])
    _finishes(pg, "() => window.__first === null", what='the first grouping')
    assert pg.locator('#group-settings-modal').is_visible()
    pg.locator('#group-settings-apply').click(timeout=LIMIT_MS)
    _finishes(pg, "() => typeof window.__second === 'string' && window.__second.startsWith('g')",
              what='the second grouping')
    _grouped(pg)
    assert errors == []
