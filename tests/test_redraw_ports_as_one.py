"""Several data ports picked on the wall and redrawn as ONE.

The owner, 2026-11-02, on a show: "i need to be able to click multiple ports
and redraw them so 51-54 i want to be able to redraw all of those as one
port". His rulings, pinned here in a real browser with real mouse and
keyboard events:

* PICK - Shift+click a run picks it (and lights it); Shift+click again
  un-picks it. Shift+drag a box from a run picks every port it touches.
* MENU - with 2+ picked, right-click reads "Redraw ports 56-59 as one", or
  a list where the numbers are not consecutive.
* REDRAW - the picked ports' cabinets are freed and one new path is drawn on
  the lowest number; drawing every freed cabinet (or Enter) keeps it.
* NUMBERS - the other picked numbers go and every later port closes up, on
  an automatic screen and on a custom one; the pins follow.
* RULES - the port's capacity refuses a cabinet out loud, Esc puts
  everything back with no change, one undo takes the whole thing back, and
  a locked screen is refused with the locked error.

The wall is synthetic (the show's shape, none of its data): 90 x 5 cabinets
of 192 x 384 on NovaStar Legacy at 8-bit 60 Hz - eight cabinets to a port -
walked tl-h, Organized, numbered Down. Each row cuts into eleven ports of
eight and a leftover of two (columns 88-89); numbered down the stacks, the
leftovers of rows 0-4 are ports 56-60 and the wall has 60 ports.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CAB_W, CAB_H = 192, 384


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


HELPERS_JS = """
window.__mrg = {
    async reset(opts) {
        opts = opts || {};
        const app = window.app, r = window.canvasRenderer;
        if (app._mergeRedraw) app._mergeRedraw = null;
        app._portPicks = null;
        app._overrideEditing = null;
        let project = await (await fetch('/api/project')).json();
        project.layers = [];
        project.groups = [];
        project.port_assignments = { auto: false, autoRetired: true, pins: [] };
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(project),
        });
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'MergeWall',
                columns: 90, rows: 5, cabinet_width: 192, cabinet_height: 384,
                offset_x: 0, offset_y: 0,
            }),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('merge_runs_reset');
        const layer = app.project.layers.filter(
            l => (l.type || 'screen') === 'screen')[0];
        layer.flowPattern = 'tl-h';
        layer.portMappingMode = 'organized';
        layer.portNumberOrder = 'down';
        layer.processorType = 'novastar-armor';
        layer.bitDepth = 8;
        layer.frameRate = 60;
        layer.lowLatency = false;
        layer.customPortPaths = {};
        layer.customPortOverrides = [];
        layer.customPortIndex = 1;
        layer.portLabelOverridesPrimary = {};
        layer.portLabelOverridesReturn = {};
        if (opts.custom) {
            // Whole-screen custom, drawn the way the automatic walk had it.
            const items = app.calculatePortAssignments(layer) || [];
            const paths = {};
            items.forEach(it => {
                (paths[it.port] = paths[it.port] || []).push({ row: it.panel.row, col: it.panel.col });
            });
            layer.lastFlowPattern = 'tl-h';
            layer.flowPattern = 'custom';
            layer.customPortPaths = paths;
        }
        if (opts.locked) layer.locked = true;
        app.currentLayer = layer;
        app.selectedLayerIds = new Set([layer.id]);
        if (app.customSelection) app.customSelection.clear();
        if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
        // Camera on the wall's right end: columns 78-89 in view.
        r.viewMode = 'data-flow';
        r.zoom = 0.1;
        r.panX = 40 - 78 * 192 * 0.1;
        r.panY = 60;
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        app.resetHistory('Merge Test Baseline');
        window.__errs = [];
        window.__notes = [];
        if (!app.__toastWrapped) {
            const real = app._toast.bind(app);
            app._toast = (m, err, ms) => {
                (err ? window.__errs : window.__notes).push(m);
                return real(m, err, ms);
            };
            app.__toastWrapped = true;
        }
        return { id: layer.id };
    },

    layer(id) {
        return window.app.project.layers.find(l => l.id === id);
    },

    dataMap(id) {
        const app = window.app, layer = this.layer(id);
        return (app.calculatePortAssignments(layer) || []).map(it => ({
            port: it.port, row: it.panel.row, col: it.panel.col,
        }));
    },

    // port -> [[row, col], ...] in feed order, on any screen kind.
    ports(id) {
        const app = window.app, layer = this.layer(id);
        const out = {};
        if (app.isCustomFlow(layer)) {
            Object.keys(layer.customPortPaths || {}).forEach(k => {
                const path = layer.customPortPaths[k] || [];
                if (path.length) out[k] = path.map(e => [e.row, e.col]);
            });
            return out;
        }
        (app.calculatePortAssignments(layer) || []).forEach(it => {
            (out[it.port] = out[it.port] || []).push([it.panel.row, it.panel.col]);
        });
        return out;
    },

    state(id) {
        const app = window.app, layer = this.layer(id);
        const s = app._mergeRedraw;
        return {
            picks: app._portPicks ? app.portPicksFor(layer) : [],
            session: s ? { num: s.num, ready: !!s.ready, picks: s.picks } : null,
            overrides: app.getOverrideNums(layer, 'data'),
            required: app.getLayerPortsRequired(layer),
            historyAction: (app.history && app.history[app.historyIndex])
                ? app.history[app.historyIndex].action : null,
            historyIndex: app.historyIndex,
            historyLength: app.history.length,
            pins: ((app.project.port_assignments || {}).pins || [])
                .map(p => [p.index, p.port]),
        };
    },
};
"""


def reset(page, **opts):
    state = page.evaluate("(o) => window.__mrg.reset(o)", opts)
    page.wait_for_timeout(300)
    return state['id']


def world_to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def cab(page, row, col):
    return world_to_client(page, col * CAB_W + CAB_W / 2, row * CAB_H + CAB_H / 2)


def st(page, lid):
    return page.evaluate("(id) => window.__mrg.state(id)", lid)


def ports(page, lid):
    return {int(k): v for k, v in page.evaluate("(id) => window.__mrg.ports(id)", lid).items()}


def errs(page):
    return page.evaluate("() => window.__errs")


def shift_click(page, row, col):
    x, y = cab(page, row, col)
    page.keyboard.down('Shift')
    page.mouse.click(x, y)
    page.keyboard.up('Shift')
    page.wait_for_timeout(120)


def shift_box(page, a, b):
    x1, y1 = cab(page, *a)
    x2, y2 = cab(page, *b)
    page.keyboard.down('Shift')
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=3)
    page.mouse.move(x2, y2, steps=3)
    page.mouse.up()
    page.keyboard.up('Shift')
    page.wait_for_timeout(150)


def menu_item(page, row, col):
    """Right-click the cabinet and read the merge entry: its text, or None
    when the menu does not show it."""
    x, y = cab(page, row, col)
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(200)
    return page.evaluate("""() => {
        const el = document.querySelector('[data-action="ovr-merge"]');
        return (el && el.style.display !== 'none') ? el.textContent : null;
    }""")


def redraw_as_one(page, row, col):
    label = menu_item(page, row, col)
    assert label, 'the merge entry is not on the menu'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_function("() => window.app._mergeRedraw && window.app._mergeRedraw.ready")
    return label


def draw(page, cells):
    for row, col in cells:
        x, y = cab(page, row, col)
        page.mouse.click(x, y)
        page.wait_for_timeout(60)
    page.wait_for_timeout(200)


LEFTOVERS = [[0, 88], [0, 89], [1, 89], [1, 88], [2, 88], [2, 89], [3, 89], [3, 88]]


def test_the_wall_is_what_the_rulings_describe(page):
    lid = reset(page)
    p = ports(page, lid)
    assert len(p) == 60 and st(page, lid)['required'] == 60
    assert all(len(p[n]) == 8 for n in range(1, 56))
    assert [p[n] for n in range(56, 61)] == [[[r, 88], [r, 89]] for r in range(5)]


# ── picking ───────────────────────────────────────────────────────────────

def test_shift_click_picks_and_unpicks_runs(page):
    lid = reset(page)
    layer_before = page.evaluate(
        "(id) => window.__mrg.layer(id).screenNameOffsetXDataFlow || 0", lid)
    shift_click(page, 0, 88)
    shift_click(page, 1, 89)
    assert st(page, lid)['picks'] == [56, 57]
    lit = page.evaluate("""(id) => [56, 57, 58].map(n => window.canvasRenderer._runUnderlayLit(
        window.__mrg.layer(id), n))""", lid)
    assert lit == [True, True, False]
    shift_click(page, 1, 88)
    assert st(page, lid)['picks'] == [56]
    # the press picked: the screen-name label did not move
    assert page.evaluate(
        "(id) => window.__mrg.layer(id).screenNameOffsetXDataFlow || 0", lid) == layer_before
    # a plain click away drops the picks; so does Esc
    shift_click(page, 2, 88)
    x, y = world_to_client(page, 78 * CAB_W, 5 * CAB_H + 300)
    page.mouse.click(x, y)
    page.wait_for_timeout(120)
    assert st(page, lid)['picks'] == []
    shift_click(page, 2, 88)
    page.keyboard.press('Escape')
    page.wait_for_timeout(120)
    assert st(page, lid)['picks'] == []


def test_shift_drag_box_picks_every_port_it_touches(page):
    lid = reset(page)
    shift_box(page, (0, 88), (3, 89))
    assert st(page, lid)['picks'] == [56, 57, 58, 59]
    # a box adds to what is picked
    shift_box(page, (4, 88), (4, 89))
    assert st(page, lid)['picks'] == [56, 57, 58, 59, 60]
    assert ports(page, lid)[56] == [[0, 88], [0, 89]], 'picking changed the wall'


# ── the menu ──────────────────────────────────────────────────────────────

def test_menu_names_the_picked_ports(page):
    lid = reset(page)
    shift_click(page, 0, 88)
    assert menu_item(page, 0, 88) is None, 'offered with one port picked'
    page.keyboard.press('Escape')
    shift_box(page, (0, 88), (3, 89))
    assert menu_item(page, 2, 88) == 'Redraw ports 56-59 as one'
    page.keyboard.press('Escape')
    page.evaluate("() => window.app.hideContextMenu()")
    shift_click(page, 1, 88)
    assert st(page, lid)['picks'] == [56, 58, 59]
    assert menu_item(page, 0, 88) == 'Redraw ports 56, 58, 59 as one'
    page.evaluate("() => window.app.hideContextMenu()")


# ── the redraw, on an automatic screen ────────────────────────────────────

def test_redraw_as_one_makes_one_port_and_closes_the_numbers_up(page):
    lid = reset(page)
    base = st(page, lid)
    shift_box(page, (0, 88), (3, 89))
    redraw_as_one(page, 0, 88)
    mid = st(page, lid)
    assert mid['session'] == {'num': 56, 'ready': True, 'picks': [56, 57, 58, 59]}
    assert mid['overrides'] == [56]
    draw(page, LEFTOVERS)
    after = st(page, lid)
    assert after['session'] is None, 'drawing every freed cabinet did not keep it'
    p = ports(page, lid)
    assert p[56] == LEFTOVERS
    # 60 ports became 57: the row-4 leftover closed up from 60 to 57
    assert sorted(p) == list(range(1, 58))
    assert p[57] == [[4, 88], [4, 89]]
    assert after['required'] == 57
    assert after['overrides'] == [56]
    # one undo step for the whole thing
    assert after['historyAction'] == 'Redraw Ports As One'
    assert after['historyIndex'] == base['historyIndex'] + 1
    assert errs(page) == []


def test_redraw_over_ports_already_redrawn_one_by_one(page):
    """The show's shape: 56, 58 and 59 were each taken over by hand, 57
    is still automatic; all four become one."""
    lid = reset(page)
    page.evaluate("""(id) => { const app = window.app, l = window.__mrg.layer(id);
        [56, 58, 59].forEach(n => app.overrideRun(l, 'data', n));
        app.endOverrideEdit(); }""", lid)
    page.wait_for_timeout(200)
    assert st(page, lid)['overrides'] == [56, 58, 59]
    shift_box(page, (0, 88), (3, 89))
    assert redraw_as_one(page, 1, 88) == 'Redraw ports 56-59 as one'
    draw(page, LEFTOVERS)
    after = st(page, lid)
    assert after['session'] is None
    assert after['overrides'] == [56]
    assert after['required'] == 57
    assert ports(page, lid)[56] == LEFTOVERS


def test_numbers_close_up_on_a_custom_screen(page):
    lid = reset(page, custom=True)
    assert len(ports(page, lid)) == 60
    shift_click(page, 0, 88)
    shift_click(page, 2, 88)
    shift_click(page, 3, 88)
    assert redraw_as_one(page, 0, 88) == 'Redraw ports 56, 58, 59 as one'
    # on a custom screen the freed cabinets are simply unwired
    draw(page, [[0, 88], [0, 89], [2, 88], [2, 89], [3, 88], [3, 89]])
    after = st(page, lid)
    assert after['session'] is None
    p = ports(page, lid)
    assert p[56] == [[0, 88], [0, 89], [2, 88], [2, 89], [3, 88], [3, 89]]
    # 57 (row 1's leftover) keeps its number; 60 closes up to 58
    assert p[57] == [[1, 88], [1, 89]]
    assert p[58] == [[4, 88], [4, 89]]
    assert sorted(p) == list(range(1, 59))
    assert after['required'] == 58


def test_pins_follow_the_ports(page):
    """The merged port keeps the first port's socket; the removed ports'
    sockets are released; a later port keeps its socket under its new
    number."""
    lid = reset(page)
    page.evaluate("""async (id) => {
        const app = window.app;
        const pins = [[55, 5], [56, 6], [57, 7], [58, 8], [59, 9]].map(([index, port]) =>
            ({ layerId: String(id), index, cardId: 'card-test', port }));
        app.project.port_assignments = { auto: false, autoRetired: true, pins };
        await fetch('/api/project', { method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(app.project) });
        app.resetHistory('Merge Pins Baseline');
    }""", lid)
    shift_box(page, (0, 88), (3, 89))
    redraw_as_one(page, 0, 88)
    # renumbered the moment the ports were: 56 stays on 6, 57-59 released,
    # 60 is port 57 now and still on 9
    assert st(page, lid)['pins'] == [[55, 5], [56, 9]]
    draw(page, LEFTOVERS)
    assert st(page, lid)['pins'] == [[55, 5], [56, 9]]
    server = page.evaluate("""async () => ((await (await fetch('/api/project')).json())
        .port_assignments || {}).pins.map(p => [p.index, p.port])""")
    assert server == [[55, 5], [56, 9]]
    # undo puts every pin back, on the server too
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(600)
    assert st(page, lid)['pins'] == [[55, 5], [56, 6], [57, 7], [58, 8], [59, 9]]
    server = page.evaluate("""async () => ((await (await fetch('/api/project')).json())
        .port_assignments || {}).pins.map(p => [p.index, p.port])""")
    assert server == [[55, 5], [56, 6], [57, 7], [58, 8], [59, 9]]


# ── the usual rules ───────────────────────────────────────────────────────

def test_capacity_and_other_ports_cabinets_are_refused_out_loud(page):
    lid = reset(page)
    # ports 51 and 52: rows 0 and 1, columns 80-87 - sixteen cabinets freed
    p = ports(page, lid)
    assert p[51] == [[0, c] for c in range(80, 88)]
    assert p[52] == [[1, c] for c in range(80, 88)]
    shift_click(page, 0, 80)
    shift_click(page, 1, 80)
    redraw_as_one(page, 0, 80)
    draw(page, [[0, c] for c in range(80, 88)])
    assert ports(page, lid)[51] == [[0, c] for c in range(80, 88)]
    assert errs(page) == []
    # a ninth cabinet is past the port
    draw(page, [[1, 80]])
    e = errs(page)
    assert e and 'is full' in e[-1] and 'Esc puts the ports back' in e[-1], e
    assert len(ports(page, lid)[51]) == 8
    # a cabinet another port carries is refused and named
    draw(page, [[2, 80]])
    e = errs(page)
    assert e and 'already wired' in e[-1], e
    assert st(page, lid)['session'] is not None, 'a refusal ended the redraw'
    # Enter keeps the eight; the other eight go back to the walk
    page.keyboard.press('Enter')
    page.wait_for_timeout(300)
    after = st(page, lid)
    assert after['session'] is None
    assert after['historyAction'] == 'Redraw Ports As One'
    assert ports(page, lid)[51] == [[0, c] for c in range(80, 88)]
    assert sum(len(v) for v in ports(page, lid).values()) == 450


def test_esc_puts_everything_back(page):
    lid = reset(page)
    base_ports = ports(page, lid)
    base = st(page, lid)
    shift_box(page, (0, 88), (3, 89))
    redraw_as_one(page, 0, 88)
    draw(page, LEFTOVERS[:3])
    assert ports(page, lid) != base_ports
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)
    after = st(page, lid)
    assert after['session'] is None
    assert ports(page, lid) == base_ports
    assert after['overrides'] == base['overrides']
    assert after['required'] == 60
    assert (after['historyIndex'], after['historyLength']) == \
        (base['historyIndex'], base['historyLength'])
    # nothing to redo: the session never happened
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(200)
    assert ports(page, lid) == base_ports


def test_undo_takes_the_whole_redraw_back_in_one_step(page):
    lid = reset(page)
    base_ports = ports(page, lid)
    shift_box(page, (0, 88), (3, 89))
    redraw_as_one(page, 0, 88)
    draw(page, LEFTOVERS)
    assert len(ports(page, lid)) == 57
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(400)
    after = st(page, lid)
    assert ports(page, lid) == base_ports
    assert after['overrides'] == []
    assert after['required'] == 60
    assert after['historyAction'] == 'Merge Test Baseline'
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(400)
    assert len(ports(page, lid)) == 57
    assert ports(page, lid)[56] == LEFTOVERS


def test_a_locked_screen_is_refused_with_the_locked_error(page):
    lid = reset(page, locked=True)
    base_ports = ports(page, lid)
    shift_box(page, (0, 88), (3, 89))
    assert st(page, lid)['picks'] == [56, 57, 58, 59], 'picking is not changing'
    assert menu_item(page, 0, 88) == 'Redraw ports 56-59 as one'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_timeout(300)
    after = st(page, lid)
    assert after['session'] is None
    e = errs(page)
    assert e and 'is locked' in e[-1], e
    assert ports(page, lid) == base_ports
    assert after['historyAction'] == 'Merge Test Baseline'
