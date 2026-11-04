"""Several data ports picked on the wall and redrawn as ONE.

The owner, 2026-11-02, on a show: "i need to be able to click multiple ports
and redraw them so 51-54 i want to be able to redraw all of those as one
port". His rulings, pinned here in a real browser with real mouse and
keyboard events:

* PICK - Shift+click a run picks it (and lights it); Shift+click again
  un-picks it. Shift+drag a box from a run picks every port it touches.
  Alt+drag across runs picks every port it crosses, the way Alt+drag
  sweeps circuits in Power; a plain Alt+click still takes one port over.
* MENU - with 2+ picked, right-click reads "Redraw ports P56-P59 as one", or
  a list where the numbers are not consecutive.
* REDRAW - the picked ports' cabinets are freed and one new path is drawn on
  the lowest number; drawing every freed cabinet (or Enter) keeps it.
* NUMBERS - the other picked numbers go and every later port closes up, on
  an automatic screen and on a custom one; the pins follow.
* RULES - picks that hold more than one port takes are refused before
  anything is freed (only cabinets on the wall count), a cabinet another
  port carries is refused out loud, Esc puts everything back with no
  change, one undo takes the whole thing back, and a locked screen is
  refused with the locked error.

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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
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
    assert menu_item(page, 2, 88) == 'Redraw ports P56-P59 as one'
    page.keyboard.press('Escape')
    page.evaluate("() => window.app.hideContextMenu()")
    shift_click(page, 1, 88)
    assert st(page, lid)['picks'] == [56, 58, 59]
    assert menu_item(page, 0, 88) == 'Redraw ports P56, P58, P59 as one'
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
    assert redraw_as_one(page, 1, 88) == 'Redraw ports P56-P59 as one'
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
    assert redraw_as_one(page, 0, 88) == 'Redraw ports P56, P58, P59 as one'
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

def test_picks_past_one_port_are_refused_before_anything_is_freed(page):
    """Ports 51 and 52 hold sixteen cabinets and a port takes eight: the
    redraw is refused up front, with the "is full" toast's own figures,
    and nothing changes."""
    lid = reset(page)
    base_ports = ports(page, lid)
    base = st(page, lid)
    assert base_ports[51] == [[0, c] for c in range(80, 88)]
    assert base_ports[52] == [[1, c] for c in range(80, 88)]
    shift_click(page, 0, 80)
    shift_click(page, 1, 80)
    assert menu_item(page, 0, 80) == 'Redraw ports P51-P52 as one'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_timeout(300)
    e = errs(page)
    assert e and e[-1] == ('Ports P51-P52 hold 16 panels together, and one port takes '
                           '8 panels at 659,722 px/port. Pick fewer ports to redraw as one.'), e
    after = st(page, lid)
    assert after['session'] is None
    assert ports(page, lid) == base_ports
    assert after['overrides'] == base['overrides']
    assert (after['historyIndex'], after['historyLength']) == \
        (base['historyIndex'], base['historyLength'])


def test_the_rectangle_around_the_picks_is_what_a_port_pays_for(page):
    """On Armor a port pays for the rectangle around its cabinets, the way
    its badge and the "is full" toast weigh it. Ports 56 and 59 are four
    cabinets in a 2 x 4 rectangle, eight cabinets' worth, which fits.
    Ports 51 and 57 are ten cabinets, two past the port, and refused."""
    lid = reset(page)
    base_ports = ports(page, lid)
    shift_click(page, 0, 88)
    shift_click(page, 3, 88)
    assert menu_item(page, 0, 88) == 'Redraw ports P56, P59 as one'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_function("() => window.app._mergeRedraw && window.app._mergeRedraw.ready")
    assert errs(page) == []
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)
    assert ports(page, lid) == base_ports
    shift_click(page, 0, 80)
    shift_click(page, 1, 88)
    assert st(page, lid)['picks'] == [51, 57]
    assert menu_item(page, 0, 80) == 'Redraw ports P51, P57 as one'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_timeout(300)
    e = errs(page)
    assert e and e[-1].startswith('Ports P51, P57 hold 10 panels together, and one port takes 8 panels'), e
    assert st(page, lid)['session'] is None
    assert ports(page, lid) == base_ports


def test_only_cabinets_on_the_wall_are_freed(page):
    """Until the server's echo rebuilds a shrunk screen, its old cabinets
    are still in the client's copy: the redraw counts only the ones inside
    the screen's rows and columns."""
    lid = reset(page)
    counts = page.evaluate("""(id) => {
        const app = window.app, l = window.__mrg.layer(id);
        const before = app._mergePickedCabinets(l, [51, 56]).length;
        l.columns = 85;   // the field typed, the echo not back yet
        const after = app._mergePickedCabinets(l, [51, 56]).map(h => [h.panel.row, h.panel.col]);
        l.columns = 90;
        return { before, after };
    }""", lid)
    assert counts['before'] == 10
    assert counts['after'] == [[0, c] for c in range(80, 85)]


def test_another_ports_cabinet_is_refused_and_enter_keeps_the_drawing(page):
    lid = reset(page)
    shift_click(page, 0, 88)
    shift_click(page, 1, 88)
    redraw_as_one(page, 0, 88)
    draw(page, [[0, 88], [0, 89], [1, 89]])
    assert ports(page, lid)[56] == [[0, 88], [0, 89], [1, 89]]
    assert errs(page) == []
    # a cabinet another port carries is refused and named
    draw(page, [[2, 88]])
    e = errs(page)
    assert e and 'already wired' in e[-1], e
    assert st(page, lid)['session'] is not None, 'a refusal ended the redraw'
    # Enter keeps the three; the fourth goes back to the walk
    page.keyboard.press('Enter')
    page.wait_for_timeout(300)
    after = st(page, lid)
    assert after['session'] is None
    assert after['historyAction'] == 'Redraw Ports As One'
    p = ports(page, lid)
    assert p[56] == [[0, 88], [0, 89], [1, 89]]
    assert sorted(p) == list(range(1, 61))
    assert sum(len(v) for v in p.values()) == 450


# ── Alt+drag picks, as Alt+drag sweeps circuits in Power ──────────────────

def alt_drag(page, a, b, steps=6):
    x1, y1 = cab(page, *a)
    x2, y2 = cab(page, *b)
    page.keyboard.down('Alt')
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move(x1 + 6, y1 + 6, steps=2)
    page.mouse.move(x2, y2, steps=steps)
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(150)


def alt_click(page, row, col):
    x, y = cab(page, row, col)
    page.keyboard.down('Alt')
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(200)


def test_alt_drag_picks_every_port_it_crosses(page):
    lid = reset(page)
    base_ports = ports(page, lid)
    alt_drag(page, (0, 88), (3, 89))
    s = st(page, lid)
    assert s['picks'] == [56, 57, 58, 59]
    # a pick, not a take-over: nothing was redrawn and nothing changed
    assert s['overrides'] == []
    assert page.evaluate("() => window.app._overrideEditing") is None
    assert ports(page, lid) == base_ports
    assert s['historyAction'] == 'Merge Test Baseline'
    lit = page.evaluate("""(id) => [56, 59, 60].map(n => window.canvasRenderer._runUnderlayLit(
        window.__mrg.layer(id), n))""", lid)
    assert lit == [True, True, False]
    assert menu_item(page, 1, 88) == 'Redraw ports P56-P59 as one'
    page.evaluate("() => window.app.hideContextMenu()")


def test_alt_drag_adds_to_the_shift_picks_and_skips_no_port(page):
    lid = reset(page)
    shift_click(page, 4, 88)
    alt_drag(page, (0, 88), (1, 88))
    assert st(page, lid)['picks'] == [56, 57, 60]
    # one fast move down a column still picks every port it crossed
    page.evaluate("() => { window.app._portPicks = null; }")
    alt_drag(page, (0, 80), (4, 80), steps=1)
    assert st(page, lid)['picks'] == [51, 52, 53, 54, 55]


def test_alt_click_still_takes_one_port_over(page):
    lid = reset(page)
    alt_click(page, 0, 88)
    s = st(page, lid)
    assert s['overrides'] == [56]
    assert s['picks'] == []
    assert page.evaluate("() => window.app._overrideEditing") == \
        {'layerId': lid, 'kind': 'data', 'num': 56}
    assert s['historyAction'] == 'Override Port'
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)


def test_held_alt_still_lights_the_run_under_the_cursor(page):
    lid = reset(page)
    x, y = cab(page, 2, 88)
    page.keyboard.down('Alt')
    page.mouse.move(x - 3, y - 3)
    page.mouse.move(x, y)
    page.wait_for_timeout(100)
    hover = page.evaluate("() => window.app._overrideHover")
    page.keyboard.up('Alt')
    assert hover == {'layerId': lid, 'num': 58, 'kind': 'data'}


def test_esc_mid_sweep_drops_the_picks(page):
    lid = reset(page)
    x1, y1 = cab(page, 0, 88)
    x2, y2 = cab(page, 2, 88)
    page.keyboard.down('Alt')
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move(x2, y2, steps=6)
    assert st(page, lid)['picks'] == [56, 57, 58]
    page.keyboard.press('Escape')
    page.mouse.move(x2, y2 + 60, steps=3)
    page.mouse.up()
    page.keyboard.up('Alt')
    page.wait_for_timeout(150)
    s = st(page, lid)
    assert s['picks'] == []
    assert s['overrides'] == [], 'the release after Esc took a port over'


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
    assert menu_item(page, 0, 88) == 'Redraw ports P56-P59 as one'
    page.click('[data-action="ovr-merge"]')
    page.wait_for_timeout(300)
    after = st(page, lid)
    assert after['session'] is None
    e = errs(page)
    assert e and 'is locked' in e[-1], e
    assert ports(page, lid) == base_ports
    assert after['historyAction'] == 'Merge Test Baseline'


def test_merge_pins_moves_only_that_screens_pins():
    """port_assignment.merge_pins on its own: the removed ports' pins go,
    later pins of that screen close up on the sockets they had, and
    another screen's pins are untouched."""
    import port_assignment as pa
    pin = lambda layer, index, port: {'layerId': layer, 'index': index,
                                      'cardId': 'c1', 'port': port}
    state = {'pins': [pin('1', 0, 1), pin('1', 2, 3), pin('1', 3, 4),
                      pin('1', 5, 6), pin('2', 3, 9)]}
    pa.merge_pins(state, 1, [2, 3])
    assert [(p['layerId'], p['index'], p['port']) for p in state['pins']] == [
        ('1', 0, 1), ('1', 3, 6), ('2', 3, 9)]


# ── QA, 1.6.0 ─────────────────────────────────────────────────────────────

def notes(page):
    return page.evaluate("() => window.__notes")


def test_enter_on_a_half_drawn_redraw_says_where_the_leftovers_went(page):
    """Enter keeps a half-drawn redraw; the freed cabinets left undrawn go
    back to the automatic walk, and the toast says which ports took them
    instead of re-walking them in silence."""
    lid = reset(page)
    shift_click(page, 0, 88)
    shift_click(page, 1, 88)
    redraw_as_one(page, 0, 88)
    draw(page, [[0, 88], [0, 89]])
    page.keyboard.press('Enter')
    page.wait_for_timeout(300)
    assert st(page, lid)['session'] is None
    p = ports(page, lid)
    took = sorted({n for n, cells in p.items() for c in cells if c in ([1, 88], [1, 89])})
    assert took, p
    if len(took) == 1:
        where = 'port P%d' % took[0]
    elif took == list(range(took[0], took[-1] + 1)):
        where = 'ports P%d-P%d' % (took[0], took[-1])
    else:
        where = 'ports ' + ', '.join('P%d' % n for n in took)
    assert notes(page)[-1] == ('Ports P56-P57 are now port P56. '
                               '2 cabinets left over went to %s.' % where), notes(page)
    assert errs(page) == []


def test_a_click_on_a_drawn_step_cuts_the_redraw_back(page):
    """A click on a step already drawn cuts the new path back to it; the
    cabinets after it are still the redraw's and are drawn again in a new
    order, and drawing the last of them keeps the drawing as before."""
    lid = reset(page)
    shift_click(page, 0, 88)
    shift_click(page, 1, 88)
    redraw_as_one(page, 0, 88)
    draw(page, [[0, 88], [0, 89], [1, 89]])
    draw(page, [[0, 88]])
    assert ports(page, lid)[56] == [[0, 88]]
    assert st(page, lid)['session'] is not None
    ringed = page.evaluate("""(id) => window.app.mergeFreedPanels(window.__mrg.layer(id))
        .map(p => [p.row, p.col]).sort()""", lid)
    assert ringed == [[0, 89], [1, 88], [1, 89]]
    assert notes(page)[-1].startswith('Port P56 now ends at R1C89.'), notes(page)
    draw(page, [[1, 88], [1, 89], [0, 89]])
    assert st(page, lid)['session'] is None, 'drawing every freed cabinet did not keep it'
    assert ports(page, lid)[56] == [[0, 88], [1, 88], [1, 89], [0, 89]]
    assert errs(page) == []


def _redraw_entries(page, row, col):
    """Right-click the cabinet: the redraw entries the menu shows."""
    x, y = cab(page, row, col)
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(200)
    shown = page.evaluate("""() => ['ovr-redraw', 'ovr-merge'].map(a => {
        const el = document.querySelector(`[data-action="${a}"]`);
        return (el && el.style.display !== 'none') ? el.textContent : null;
    }).filter(Boolean)""")
    page.evaluate("() => window.app.hideContextMenu()")
    return shown


def test_picked_ports_offer_only_the_redraw_of_all_of_them(page):
    """The owner, 2026-11-03: "when multi selecting on auto to draw when i
    click redraw it should not give the option to redraw just one". Two or
    more picked: only "Redraw ports ... as one". One picked, or none: the
    single "Redraw port" as before."""
    reset(page)
    assert _redraw_entries(page, 0, 88) == ['Redraw port P56']
    shift_click(page, 0, 88)
    assert _redraw_entries(page, 0, 88) == ['Redraw port P56']
    shift_click(page, 1, 88)
    assert _redraw_entries(page, 0, 88) == ['Redraw ports P56-P57 as one']
    assert _redraw_entries(page, 1, 89) == ['Redraw ports P56-P57 as one']
    # the Alt+drag sweep's picks too
    page.evaluate("() => { window.app._portPicks = null; }")
    alt_drag(page, (0, 88), (2, 88))
    assert _redraw_entries(page, 2, 88) == ['Redraw ports P56-P58 as one']


def test_a_click_on_an_earlier_step_cuts_back_on_a_custom_screen_too(page):
    """The owner, 2026-11-03: "custom should do the same as automatic if
    there are ports after the one i am clicking". Drawing a port on a
    custom screen, a click on an earlier cabinet of its path cuts the path
    back to end there, in one undo step; the cabinets cut off are free to
    draw again. A click on the last cabinet still does nothing."""
    lid = reset(page, custom=True)
    page.evaluate("""(id) => { const app = window.app, l = window.__mrg.layer(id);
        l.customPortIndex = 51; app.updateCustomFlowUI(); app.resetHistory('Cut Baseline'); }""", lid)
    assert ports(page, lid)[51] == [[0, c] for c in range(80, 88)]
    base = st(page, lid)
    draw(page, [[0, 82]])
    assert ports(page, lid)[51] == [[0, 80], [0, 81], [0, 82]]
    after = st(page, lid)
    assert after['historyAction'] == 'Custom Path Edit'
    assert after['historyIndex'] == base['historyIndex'] + 1
    assert notes(page)[-1] == ('Port P51 now ends at R1C83. '
                               'The 5 cabinets after it can be drawn again, in any order.'), notes(page)
    # the last cabinet: nothing
    draw(page, [[0, 82]])
    assert st(page, lid)['historyIndex'] == after['historyIndex']
    # the cabinets cut off are free: drawn again, in a new order
    draw(page, [[0, 87], [0, 86], [0, 85]])
    assert ports(page, lid)[51] == [[0, 80], [0, 81], [0, 82], [0, 87], [0, 86], [0, 85]]
    assert errs(page) == []


def _menu_entries(page, row, col):
    """Right-click the cabinet: every port entry the menu shows."""
    x, y = cab(page, row, col)
    page.mouse.click(x, y, button='right')
    page.wait_for_timeout(200)
    return page.evaluate("""() => ['ovr-redraw', 'ovr-merge', 'ovr-auto', 'hw-clear'].map(a => {
        const el = document.querySelector(`[data-action="${a}"]`);
        return (el && el.style.display !== 'none') ? el.textContent : null;
    }).filter(Boolean)""")


def test_picked_ports_offer_no_item_for_one_port(page):
    """QA, 1.6.0: with two or more ports picked, "Port P56 back to auto"
    and "Clear port P56" were still offered for the port under the cursor.
    Every item acts on all the picks and names them."""
    lid = reset(page)
    page.evaluate("""(id) => { const app = window.app;
        [56, 57].forEach(n => { app.overrideRun(window.__mrg.layer(id), 'data', n);
                                app.endOverrideEdit(); }); }""", lid)
    page.wait_for_timeout(400)
    page.evaluate("() => window.app.resetHistory('Picks Baseline')")
    shift_click(page, 0, 88)
    shift_click(page, 1, 88)
    shown = _menu_entries(page, 0, 88)
    assert shown == ['Redraw ports P56-P57 as one', 'Ports P56-P57 back to auto',
                     'Clear ports P56-P57'], shown
    page.click('[data-action="ovr-auto"]')
    page.wait_for_timeout(400)
    s = st(page, lid)
    assert s['overrides'] == []
    assert s['historyAction'] == 'Return Ports To Auto' and s['historyIndex'] == 1
    # one port picked: the single items as before
    page.evaluate("() => window.app.hideContextMenu()")
    shift_click(page, 0, 88)
    assert _menu_entries(page, 0, 88) == ['Redraw port P56', 'Clear port P56']
    page.evaluate("() => window.app.hideContextMenu()")
