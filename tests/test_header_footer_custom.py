"""The Header/Footer tab: one side per screen, Custom bars, rows across a
group's seams.

The owner's rulings of 2026-11-08, each proved through the gestures that
follow it:

  One side      "it can only be one or the other." Header | Footer sets the
                selected screens' side and moves their bars over unchanged,
                one undo step. A show saved with both opens unchanged and the
                tab's box offers Keep Header / Keep Footer per screen.
  Custom        "select doubles and click or drag and then click singles and
                click or drag more." One size at a time; a click drops a bar
                at the panel, a drag lays whole bars along it; a new bar
                replaces what it overlaps; gaps are fine; Delete takes a
                picked bar off; a locked screen refuses and says so.
  Groups cross  "they need to cross": grouped screens edge to edge in Show
                Look carry one row. Two 11-wide walls with only doubles lit
                take 11 doubles across the pair; 9 + 18 + 9 takes 18; a step
                breaks the row. A straddling bar is counted once.

And the polish of the same day ("fix all of that"), one test each at the
end: the Keep buttons fit one line, Auto | Custom is saved with the show,
Delete never deletes a screen on this tab, a copy of a crossing member keeps
only the bars over it, bars stay readable zoomed out, and a Custom press on
the wall selects and drags the screen (only the strip outside lays bars).

Run locally:
    python -m pytest tests/test_header_footer_custom.py -n 2 --dist loadfile
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# A 12 x 6 wall A; PAIR, two 11 x 4 walls edge to edge; TRIO, 9 + 18 + 9
# wide in a row (3 high); STEP, two 4 x 3 walls side by side with the second
# set 200 px lower (a step: the row breaks).
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.canvases = proj.canvases.slice(0, 1); proj.active_canvas_id = proj.canvases[0].id;
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.binder; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    delete proj.riggingTool;
    await j('PUT', '/api/project', proj);
    const base = {cabinet_width: 200, cabinet_height: 200, panelWatts: 200, flowPattern: 'tl-h',
                  powerVoltage: 208, powerAmperage: 20, powerFlowPattern: 'tl-v', powerOrganized: true,
                  processorType: 'novastar-armor'};
    const add = (b) => j('POST', '/api/layer/add', {...base, ...b});
    await add({name: 'A', columns: 12, rows: 6});
    await add({name: 'PL', columns: 11, rows: 4, offset_x: 3000});
    await add({name: 'PR', columns: 11, rows: 4, offset_x: 5200});
    await add({name: 'TL', columns: 9, rows: 3, offset_y: 1600});
    await add({name: 'TM', columns: 18, rows: 3, offset_x: 1800, offset_y: 1600});
    await add({name: 'TR', columns: 9, rows: 3, offset_x: 5400, offset_y: 1600});
    await add({name: 'SL', columns: 4, rows: 3, offset_y: 2600});
    await add({name: 'SR', columns: 4, rows: 3, offset_x: 800, offset_y: 2800});
    let p = await j('GET', '/api/project');
    const f = n => p.layers.find(l => l.name === n);
    const group = (id, name, names) => {
        names.forEach(n => { f(n).group_id = id; });
        p.groups.push({id, name, layer_ids: names.map(n => f(n).id), routeDataAsOne: false});
    };
    p.groups = [];
    group('gp', 'PAIR', ['PL', 'PR']);
    group('gt', 'TRIO', ['TL', 'TM', 'TR']);
    group('gs', 'STEP', ['SL', 'SR']);
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('hf_custom_setup');
    app._riggingCustomSize = 2;
    app._riggingPicked = null;
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Header Footer Custom Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': False, 'data': False},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
        'wiring': False, 'rigging': True, 'titleBlock': True}


@pytest.fixture()
def pg(e2e_server, pw_browser):
    ctx = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('**/api/native-dialog/save-file', lambda r: r.fulfill(json={'path': None}))
    page.route('**/api/native-dialog/open-file', lambda r: r.fulfill(json={'path': None}))
    page.route('**/api/native-dialog/select-directory', lambda r: r.fulfill(json={'path': None}))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function("() => window.app && window.app._initialLoadComplete")
    page.wait_for_timeout(1200)
    page.ids = page.evaluate(SEED_JS)
    page.wait_for_timeout(300)
    page.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")
    page.errors = errors
    page.e2e_server = e2e_server
    yield page
    ctx.close()
    assert not errors, errors


def tab(p, mode='rigging'):
    p.locator(f'.view-tab[data-mode="{mode}"]').click()
    p.wait_for_timeout(300)


def sel(p, *names):
    p.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[0])", [p.ids[n] for n in names])
    p.wait_for_timeout(150)


def lay(p, name, *fields):
    return p.evaluate("""([id, f]) => { const l = window.app.project.layers.find(x => x.id === id);
        return Object.fromEntries(f.map(k => [k, l[k] === undefined ? null : l[k]])); }""",
                      [p.ids[name], list(fields)])


def bars(p, name, kind='header'):
    """[[start, size], ...] of a screen's own row, in its own panels."""
    return p.evaluate("([id, k]) => window.app.riggingPlaced(window.app.project.layers.find(x => x.id === id), k)"
                      ".map(b => [b.start, b.size])", [p.ids[name], kind])


def steps(p):
    return p.evaluate("() => window.app.history.length")


def undo(p):
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)


def redo(p):
    p.evaluate("() => window.app.redo()")
    p.wait_for_timeout(500)


def light_only(p, size):
    """Auto's lit sizes on the selection: just `size`."""
    p.evaluate("""(size) => { const a = window.app;
        a._riggingWithGroups(a._riggingScreens()).forEach(l => { l.riggingSizes = [size]; });
        a.refreshRiggingPanel(); }""", size)


def auto(p, *names, size=None):
    sel(p, *names)
    if size:
        light_only(p, size)
    p.locator('#rigging-auto-btn').click()
    p.wait_for_timeout(300)


def toasts(p):
    return p.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(e => e.textContent)")


def clear_toasts(p):
    p.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


def pull_rig(p):
    return p.evaluate("""() => window.app.buildPullSheet().totals.filter(t => t.side === 'rigging')
        .map(t => [t.type, t.qty])""")


def total(p, kind='header'):
    sel_id = '#rigging-total-count' if kind == 'header' else '#rigging-footer-total-count'
    return int(p.locator(sel_id).text_content())


def view(p, zoom=0.18):
    p.evaluate("""(z) => { const r = window.canvasRenderer; r.zoom = z; r.panX = 40; r.panY = 160; r.render(); }""", zoom)
    p.wait_for_timeout(100)


def zone_point(p, name, panel, edge='middle'):
    """A client point in a screen's bar strip over its `panel`: the middle of
    the strip, or 3 px in from its wall side ('wall') or its outer side
    ('outer'), the two ends of where a Custom press lays bars."""
    return p.evaluate("""([id, panel, edge]) => { const r = window.canvasRenderer; r.render();
        const z = r._riggingZones.find(q => q.layerId === id);
        const b = r.canvas.getBoundingClientRect();
        const x = b.left + z.x0 + z.dir * (panel + 0.5) * z.unitPx;
        const header = z.kind !== 'footer';
        const wall = header ? z.y1 - 3 : z.y0 + 3, outer = header ? z.y0 + 3 : z.y1 - 3;
        const y = b.top + (edge === 'wall' ? wall : edge === 'outer' ? outer : (z.y0 + z.y1) / 2);
        return { x, y }; }""", [p.ids[name], panel, edge])


def wall_point(p, name, panel, row=0):
    """A client point on the wall itself: over its `panel`, in its `row` of
    panels from the top (the edge row a header's strip sits above)."""
    return p.evaluate("""([id, panel, row]) => { const r = window.canvasRenderer; r.render();
        const a = window.app; const l = a.project.layers.find(x => x.id === id);
        const z = r._riggingZones.find(q => q.layerId === id);
        const box = r.getLayerFootprintInActiveView(l);
        const b = r.canvas.getBoundingClientRect();
        // the footprint is in the layer's frame: the zone's own x and the
        // wall's top edge (the strip's wall side) place it on screen
        const rows = l.rows, h = box.height * Math.abs(r.zoom);
        const top = z.kind === 'footer' ? z.y0 - h : z.y1;
        return { x: b.left + z.x0 + z.dir * (panel + 0.5) * z.unitPx,
                 y: b.top + top + (row + 0.5) * h / rows }; }""", [p.ids[name], panel, row])


def bar_point(p, name, index=0):
    return p.evaluate("""([id, i]) => { const r = window.canvasRenderer; r.render();
        const h = r._riggingHits.filter(x => x.layerId === id)[i];
        const b = r.canvas.getBoundingClientRect();
        return { x: b.left + (h.x0 + h.x1) / 2, y: b.top + (h.y0 + h.y1) / 2 }; }""", [p.ids[name], index])


def click_at(p, pt):
    p.mouse.move(pt['x'], pt['y'])
    p.mouse.down()
    p.mouse.up()
    p.wait_for_timeout(250)


def drag(p, a, b):
    p.mouse.move(a['x'], a['y'])
    p.mouse.down()
    p.mouse.move(b['x'], b['y'], steps=8)
    p.mouse.up()
    p.wait_for_timeout(300)


def custom(p, size):
    if not p.locator('.rigging-tool-btn[data-tool="custom"]').evaluate("b => b.classList.contains('active')"):
        p.locator('.rigging-tool-btn[data-tool="custom"]').click()
    if size >= 3 and not p.locator('#rigging-size-extra').is_visible():
        p.locator('#rigging-size-more').click()
    p.locator(f'#rigging-size-picker [data-size="{size}"]').click()
    p.wait_for_timeout(150)


def reopen(p):
    """Reload the page: the show comes back from the server."""
    p.reload(wait_until='domcontentloaded')
    p.wait_for_function("() => window.app && window.app._initialLoadComplete")
    p.wait_for_timeout(1200)
    p.evaluate("() => { const s = document.querySelector('#start-page'); if (s) s.style.display = 'none'; }")


# ── One side per screen ──────────────────────────────────────────────────

def test_footer_moves_the_bars_over_unchanged_in_one_step(pg):
    p = pg
    tab(p)
    auto(p, 'A', size=2)
    # a 2 + 4 + 3 + 3 shape, the guide's
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingBars = [2, 4, 3, 3]; a.updateLayers([l], true, 'Shape'); }""", p.ids['A'])
    n = steps(p)
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': [2, 4, 3, 3]}
    assert steps(p) == n + 1
    assert p.locator('.rigging-mode-btn[data-mode="footer"]').evaluate("b => b.classList.contains('active')")
    assert total(p, 'header') == 0 and total(p, 'footer') == 4
    assert sorted(pull_rig(p)) == [['Footer Bar - Double', 1], ['Footer Bar - Quad', 1], ['Footer Bar - Triple', 2]]
    # the canvas draws them under the wall now
    rows = p.evaluate("(id) => { window.canvasRenderer.render(); return window.canvasRenderer._riggingHits"
                      ".filter(h => h.layerId === id).map(h => h.row); }", p.ids['A'])
    assert rows == ['footer'] * 4
    # pressing Footer again changes nothing and records nothing
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(200)
    assert steps(p) == n + 1
    undo(p)
    assert bars(p, 'A') == [[0, 2], [2, 4], [6, 3], [9, 3]] and bars(p, 'A', 'footer') == []
    redo(p)
    assert lay(p, 'A', 'riggingFooterBars')['riggingFooterBars'] == [2, 4, 3, 3]
    # kept with the show, and the tab still reads Footer after a trip away
    tab(p, 'power')
    tab(p)
    sel(p, 'A')
    assert p.locator('.rigging-mode-btn[data-mode="footer"]').evaluate("b => b.classList.contains('active')")
    reopen(p)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': [2, 4, 3, 3]}


def test_an_empty_screen_remembers_its_side_and_auto_fills_that_side(pg):
    p = pg
    tab(p)
    sel(p, 'A')
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(200)
    assert lay(p, 'A', 'riggingSide')['riggingSide'] == 'footer'
    auto(p, 'A', size=2)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': [2] * 6}


def test_a_group_switches_side_together(pg):
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    sel(p, 'PL')
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(300)
    for n in ('PL', 'PR'):
        assert lay(p, n, 'riggingBars')['riggingBars'] == []
    # the crossing row moved whole: still 11 doubles, still across the seam
    assert bars(p, 'PL', 'footer')[-1] == [10, 2]
    assert bars(p, 'PR', 'footer')[0] == [1, 2]
    assert total(p, 'footer') == 11


SAVE_BOTH_JS = """async (id) => {
    const p = await (await fetch('/api/project')).json();
    const l = p.layers.find(x => x.id === id);
    l.riggingBars = [4, 4, 4]; l.riggingFooterBars = [2, 2, 2, 2, 2, 2];
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                 body: JSON.stringify(p)});
}"""


def test_an_old_show_with_both_opens_unchanged_and_asks_which_to_keep(pg):
    p = pg
    p.evaluate(SAVE_BOTH_JS, p.ids['A'])
    reopen(p)
    tab(p)
    # nothing dropped: both rows draw, both count
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [4, 4, 4], 'riggingFooterBars': [2] * 6}
    assert total(p, 'header') == 3 and total(p, 'footer') == 6
    assert sorted(pull_rig(p)) == [['Footer Bar - Double', 6], ['Header Bar - Quad', 3]]
    assert p.locator('#rigging-fit-warning').is_visible()
    assert p.locator('#rigging-both-section').is_visible()
    assert not p.locator('#rigging-fit-section').is_visible()
    keep = p.locator(f'#rigging-both-list [data-layer-id="{p.ids["A"]}"]')
    assert keep.count() == 2
    # Auto and the side buttons wait for the pick, and say so
    clear_toasts(p)
    auto(p, 'A', size=2)
    assert any('Pick the side to keep' in t for t in toasts(p)), toasts(p)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [4, 4, 4]
    n = steps(p)
    p.locator(f'#rigging-both-list [data-layer-id="{p.ids["A"]}"][data-keep="footer"]').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': [2] * 6}
    assert steps(p) == n + 1
    assert not p.locator('#rigging-fit-warning').is_visible()
    undo(p)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [4, 4, 4], 'riggingFooterBars': [2] * 6}
    assert p.locator('#rigging-both-section').is_visible()
    p.locator(f'#rigging-both-list [data-layer-id="{p.ids["A"]}"][data-keep="header"]').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [4, 4, 4], 'riggingFooterBars': []}


def test_keep_refuses_a_locked_screen(pg):
    p = pg
    p.evaluate(SAVE_BOTH_JS, p.ids['A'])
    reopen(p)
    tab(p)
    sel(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    clear_toasts(p)
    n = steps(p)
    p.locator(f'#rigging-both-list [data-layer-id="{p.ids["A"]}"][data-keep="footer"]').click()
    p.wait_for_timeout(300)
    assert any('A is locked' in t for t in toasts(p)), toasts(p)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [4, 4, 4]
    assert steps(p) == n


# ── Custom ────────────────────────────────────────────────────────────────

def test_custom_click_and_drag_with_two_sizes(pg):
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    custom(p, 2)
    assert not p.locator('#rigging-auto-btn').is_visible()
    assert p.locator('#rigging-custom-hint').is_visible()
    assert p.locator('#rigging-size-picker .rigging-size-btn.active').count() == 1
    n = steps(p)
    # a click drops one double at the panel
    click_at(p, zone_point(p, 'A', 0))
    assert bars(p, 'A') == [[0, 2]]
    assert steps(p) == n + 1
    # a drag along the edge lays doubles; the odd panel left over stays empty
    drag(p, zone_point(p, 'A', 4), zone_point(p, 'A', 8))
    assert bars(p, 'A') == [[0, 2], [4, 2], [6, 2]]
    assert steps(p) == n + 2
    # singles next: a click out in the bar strip, then a drag
    custom(p, 1)
    click_at(p, zone_point(p, 'A', 11, edge='outer'))
    drag(p, zone_point(p, 'A', 2), zone_point(p, 'A', 3))
    assert bars(p, 'A') == [[0, 2], [2, 1], [3, 1], [4, 2], [6, 2], [11, 1]]
    # gaps are fine: no warning
    assert not p.locator('#rigging-fit-warning').is_visible()
    assert lay(p, 'A', 'riggingCustom')['riggingCustom'] is True
    assert lay(p, 'A', 'riggingBarStarts')['riggingBarStarts'] == [0, 2, 3, 4, 6, 11]
    # a quad over two doubles replaces them, laid from past the bars (a
    # press on a bar picks it up)
    custom(p, 4)
    click_at(p, zone_point(p, 'A', 4, edge='outer'))
    assert bars(p, 'A') == [[0, 2], [2, 1], [3, 1], [4, 4], [11, 1]]
    assert total(p) == 5
    # undo steps back one gesture at a time
    undo(p)
    assert bars(p, 'A') == [[0, 2], [2, 1], [3, 1], [4, 2], [6, 2], [11, 1]]
    # the edge between two touching bars still drags: 2 | 1 becomes 1 | 2
    edge = p.evaluate("""(id) => { const r = window.canvasRenderer; r.render();
        const e = r._riggingEdges.find(x => x.layerId === id && x.boundary === 0);
        const b = r.canvas.getBoundingClientRect();
        return { x: b.left + e.x, y: b.top + (e.y0 + e.y1) / 2, unit: e.unitPx }; }""", p.ids['A'])
    drag(p, edge, {'x': edge['x'] - edge['unit'], 'y': edge['y']})
    assert bars(p, 'A')[:2] == [[0, 1], [1, 2]]
    # saved, reopened, the same
    reopen(p)
    assert bars(p, 'A') == [[0, 1], [1, 2], [3, 1], [4, 2], [6, 2], [11, 1]]


def test_a_click_shows_the_ghost_first_and_a_long_bar_stays_on_the_wall(pg):
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    custom(p, 4)
    pt = zone_point(p, 'A', 11)
    p.mouse.move(pt['x'], pt['y'])
    p.wait_for_timeout(150)
    ghost = p.evaluate("() => window.app._riggingGhost")
    assert ghost and ghost['size'] == 4 and ghost['start'] == 8, ghost
    assert p.evaluate("() => window.canvasRenderer.canvas.style.cursor") == 'copy'
    p.mouse.down()
    p.mouse.up()
    p.wait_for_timeout(250)
    assert bars(p, 'A') == [[8, 4]]


def test_a_picked_bar_goes_with_delete_and_the_menu(pg):
    p = pg
    tab(p)
    view(p)
    auto(p, 'A', size=2)
    custom(p, 2)
    n = steps(p)
    click_at(p, bar_point(p, 'A', 1))
    assert p.evaluate("() => window.app._riggingPicked") is not None
    assert steps(p) == n, 'a click on a bar picks it, nothing more'
    p.keyboard.press('Delete')
    p.wait_for_timeout(300)
    assert bars(p, 'A') == [[0, 2], [4, 2], [6, 2], [8, 2], [10, 2]]
    assert p.evaluate("(id) => window.app.project.layers.some(l => l.id === id)", p.ids['A']), 'the screen stays'
    assert steps(p) == n + 1
    # the gap left behind is no misfit: the row is custom now
    assert not p.locator('#rigging-fit-warning').is_visible()
    # right-click Remove Bar
    pt = bar_point(p, 'A', 0)
    p.mouse.click(pt['x'], pt['y'], button='right')
    p.wait_for_timeout(200)
    item = p.locator('#context-menu [data-action="rigging-remove-bar"]')
    assert item.is_visible() and item.text_content() == 'Remove Bar'
    item.click()
    p.wait_for_timeout(300)
    assert bars(p, 'A') == [[4, 2], [6, 2], [8, 2], [10, 2]]
    undo(p)
    assert bars(p, 'A')[0] == [0, 2]
    # Auto puts a whole row back and clears the custom mark
    p.locator('.rigging-tool-btn[data-tool="auto"]').click()
    auto(p, 'A', size=2)
    assert bars(p, 'A') == [[i, 2] for i in range(0, 12, 2)]
    assert lay(p, 'A', 'riggingCustom', 'riggingBarStarts') == {'riggingCustom': False, 'riggingBarStarts': None}


def test_custom_on_a_locked_screen_refuses_and_says_so(pg):
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    custom(p, 2)
    clear_toasts(p)
    n = steps(p)
    click_at(p, zone_point(p, 'A', 3))
    assert any('A is locked' in t for t in toasts(p)), toasts(p)
    assert bars(p, 'A') == [] and steps(p) == n
    clear_toasts(p)
    drag(p, zone_point(p, 'A', 0), zone_point(p, 'A', 6))
    assert any('A is locked' in t for t in toasts(p)), toasts(p)
    assert bars(p, 'A') == [] and steps(p) == n


def test_a_bar_past_the_edge_after_a_resize_is_flagged_but_gaps_are_not(pg):
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    custom(p, 2)
    click_at(p, zone_point(p, 'A', 10))
    click_at(p, zone_point(p, 'A', 2))
    assert bars(p, 'A') == [[2, 2], [10, 2]]
    assert not p.locator('#rigging-fit-warning').is_visible()
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.columns = 11; a.updateLayers([l], true, 'Narrower'); }""", p.ids['A'])
    p.wait_for_timeout(300)
    assert p.locator('#rigging-fit-section').is_visible()
    assert p.locator('#rigging-fit-text').text_content() == "A: header bars run 1 panel past the wall's edge."


# ── Groups: one row across the seam ──────────────────────────────────────

def test_doubles_cross_the_seam_of_two_11_wide_walls(pg):
    """The owner's log: two 11-wide walls, only doubles lit, Auto did
    nothing. Across the pair, 22 panels, it is 11 doubles."""
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    assert lay(p, 'PL', 'riggingBars', 'riggingBarStarts') == {'riggingBars': [2] * 6, 'riggingBarStarts': None}
    assert lay(p, 'PR', 'riggingBars', 'riggingBarStarts') == {'riggingBars': [2] * 5, 'riggingBarStarts': [1, 3, 5, 7, 9]}
    assert p.locator('#rigging-status').text_content() == ''
    # one double straddles the seam, and it is counted once
    assert total(p) == 11
    assert pull_rig(p) == [['Header Bar - Double', 11]]
    assert not p.locator('#rigging-fit-warning').is_visible()
    # it draws as one bar running from PL over PR
    pl = p.evaluate("""(ids) => { const r = window.canvasRenderer; r.render();
        const a = window.app; const L = a.project.layers.find(x => x.id === ids[0]);
        const R = a.project.layers.find(x => x.id === ids[1]);
        const hl = r._riggingHits.filter(h => h.layerId === ids[0]);
        const hr = r._riggingHits.filter(h => h.layerId === ids[1]);
        const seam = (r.getLayerFootprintInActiveView(R).x) * r.zoom + r.panX;
        return { last: hl[hl.length - 1], first: hr[0], seam }; }""", [p.ids['PL'], p.ids['PR']])
    assert pl['last']['x0'] < pl['seam'] < pl['last']['x1']
    assert abs(pl['first']['x0'] - pl['last']['x1']) < 1.5
    # undo takes the whole row off in one step
    undo(p)
    assert bars(p, 'PL') == [] and bars(p, 'PR') == []


def test_9_18_9_takes_doubles_across(pg):
    p = pg
    tab(p)
    auto(p, 'TM', size=2)
    assert total(p) == 18
    assert bars(p, 'TL')[-1] == [8, 2]          # straddles onto TM
    assert bars(p, 'TM')[0] == [1, 2]
    assert bars(p, 'TR')[0] == [1, 2]
    assert sum(len(bars(p, n)) for n in ('TL', 'TM', 'TR')) == 18


def test_a_step_breaks_the_row(pg):
    p = pg
    tab(p)
    auto(p, 'SL', size=2)
    # 4 + 4 standing a step apart: each its own row
    assert bars(p, 'SL') == [[0, 2], [2, 2]] and bars(p, 'SR') == [[0, 2], [2, 2]]
    # the step lines their BOTTOM edges up as a footer? SL is 3 high at 2600,
    # SR 3 high at 2800: no. Footers break too.
    sel(p, 'SL')
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(300)
    assert bars(p, 'SL', 'footer') == [[0, 2], [2, 2]] and bars(p, 'SR', 'footer') == [[0, 2], [2, 2]]
    assert not p.locator('#rigging-fit-warning').is_visible()


def test_old_group_bars_stay_as_drawn_until_the_next_edit(pg):
    p = pg
    tab(p)
    # an older show: each member fitted alone (11 = 1 + 5 doubles)
    p.evaluate("""(ids) => { const a = window.app;
        ids.forEach(id => { const l = a.project.layers.find(x => x.id === id); l.riggingBars = [1, 2, 2, 2, 2, 2]; });
        a.updateLayers(ids.map(id => a.project.layers.find(x => x.id === id)), true, 'Old'); }""",
               [p.ids['PL'], p.ids['PR']])
    p.wait_for_timeout(300)
    assert not p.locator('#rigging-fit-warning').is_visible()
    assert lay(p, 'PR', 'riggingBars')['riggingBars'] == [1, 2, 2, 2, 2, 2]
    assert total(p) == 12
    auto(p, 'PR', size=2)
    assert total(p) == 11


def test_custom_drag_crosses_the_seam(pg):
    p = pg
    tab(p)
    view(p)
    sel(p, 'PL')
    custom(p, 4)
    # from PL's panel 8 to PR's panel 4 (the row's 15): 8 panels, two
    # quads laid from 8, the first across the seam
    drag(p, zone_point(p, 'PL', 8), zone_point(p, 'PR', 4))
    assert bars(p, 'PL') == [[8, 4]]
    assert bars(p, 'PR') == [[1, 4]]
    assert total(p) == 2
    # a double on PR's panel 0 replaces both quads it overlaps
    custom(p, 2)
    click_at(p, zone_point(p, 'PR', 0, edge='outer'))
    assert bars(p, 'PL') == [] and bars(p, 'PR') == [[0, 2]]
    undo(p)
    assert bars(p, 'PL') == [[8, 4]] and bars(p, 'PR') == [[1, 4]]


def test_a_locked_member_holds_the_whole_row(pg):
    p = pg
    tab(p)
    sel(p, 'PR')
    p.evaluate("(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id); l.locked = true; }",
               p.ids['PR'])
    clear_toasts(p)
    auto(p, 'PL', size=2)
    assert bars(p, 'PL') == [] and bars(p, 'PR') == []
    assert any('locked' in t for t in toasts(p)), toasts(p)


def test_the_group_sheet_draws_the_row_and_counts_the_straddler_once(pg):
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    out = p.evaluate("""(o) => { const a = window.app;
        a.project.groupNameDisplayByView = { rigging: 'group' };
        const plan = a.planBinder(o);
        const i = plan.findIndex(x => x.title === 'PAIR - Header/Footer - Front View');
        const r = i < 0 ? null : a.renderBinderPage(o, i);
        return { titles: plan.filter(x => x.kind === 'rigging').map(x => x.title),
                 texts: r && r.texts, map: r && r.mapTexts, dashes: r && r.dashes }; }""", OPTS)
    assert 'PAIR - Header/Footer - Front View' in out['titles'], out['titles']
    texts = out['texts']
    head = texts[texts.index('HEADER BARS'):]
    i = head.index('Header Bar - Double')
    assert head[i + 1:i + 3] == ['2', '11'], head
    # the map draws the row whole, each bar once, nothing dashed
    assert out['map'].count('2') == 11, out['map']
    assert not [d for d in out['dashes'] if d], out['dashes']


def test_a_member_sheet_shows_the_bar_continuing_on_the_neighbor(pg):
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    out = p.evaluate("""(o) => { const a = window.app;
        a.project.groupNameDisplayByView = { rigging: 'screens' };
        const plan = a.planBinder(o);
        const pick = (t) => { const i = plan.findIndex(x => x.title === t); return i < 0 ? null : a.renderBinderPage(o, i); };
        const l = pick('PL - Header/Footer - Front View'), r = pick('PR - Header/Footer - Front View');
        return { titles: plan.filter(x => x.kind === 'rigging').map(x => x.title),
                 l: l && l.texts, r: r && r.texts, lm: l && l.mapTexts, rm: r && r.mapTexts,
                 ld: l && l.dashes, rd: r && r.dashes }; }""", OPTS)
    assert 'PL - Header/Footer - Front View' in out['titles'] and 'PR - Header/Footer - Front View' in out['titles']
    note = "A double header bar runs from PL onto PR. It is counted on PL."
    assert note in out['l'] and note in out['r'], (out['l'], out['r'])
    # each sheet counts the bars that start on it: 6 on PL, 5 on PR
    for texts, qty in ((out['l'], '6'), (out['r'], '5')):
        head = texts[texts.index('HEADER BARS'):]
        i = head.index('Header Bar - Double')
        assert head[i + 1:i + 3] == ['2', qty], head
    # each map draws its 5 or 6 own bars plus the straddling one, whose part
    # over the neighbor is dashed (a map laid as a fill and an overlay is
    # painted twice, so its lettering is logged twice)
    assert out['lm'].count('2') in (6, 12) and out['rm'].count('2') in (6, 12), (out['lm'], out['rm'])
    assert [d for d in out['ld'] if d] and [d for d in out['rd'] if d]


def test_3d_stands_the_straddling_bar_half_on_each_member(pg):
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    tab(p, '3d')
    d = None
    for _ in range(40):
        d = p.evaluate("() => window.app._s3dDebug()")
        if d['loaded'] and len(d['screens']) >= 8:
            break
        p.wait_for_timeout(250)
    by = {s['name']: {r['row']: r for r in s['bars']} for s in d['screens']}
    left, right = by['PL']['header'], by['PR']['header']
    assert left['bars'] == [2] * 6 and left['starts'] == [0, 2, 4, 6, 8, 10]
    assert right['bars'] == [2] * 6 and right['starts'] == [-1, 1, 3, 5, 7, 9]
    # each stands only over its own 11 columns: the halves meet at the seam
    assert left['slots'] == 11 and right['slots'] == 11
    assert left['fits'] and right['fits']
    assert 'footer' not in by['PL']


# ── Polish, 2026-11-08 ("fix all of that") ──────────────────────────────

def _one_line(p, sel_):
    """Each matching element's text: how many lines it takes, and the top
    of the element: [(lines, top), ...]."""
    return p.evaluate("""(s) => [...document.querySelectorAll(s)].map(el => {
        const range = document.createRange(); range.selectNodeContents(el);
        const tops = new Set([...range.getClientRects()].map(r => Math.round(r.top)));
        return [tops.size, Math.round(el.getBoundingClientRect().top)]; })""", sel_)


def test_the_header_and_footer_keep_buttons_fit_one_line_at_any_sidebar_width(pg):
    p = pg
    p.evaluate(SAVE_BOTH_JS, p.ids['A'])
    p.evaluate("""async (id) => { const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id); l.name = 'Main Wall Left Of Stage Long Name';
        l.riggingBars = [2, 2]; l.riggingFooterBars = [2, 2];
        await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                     body: JSON.stringify(p)}); }""", p.ids['TL'])
    reopen(p)
    tab(p)
    for width in (260, 180):     # the default and the narrowest the sidebar goes
        p.evaluate("(w) => document.documentElement.style.setProperty('--lrd-left-w', w + 'px')", width)
        p.wait_for_timeout(300)
        assert round(p.evaluate("() => document.getElementById('left-sidebar').getBoundingClientRect().width")) == width
        btns = p.locator('#rigging-both-list [data-keep]')
        assert btns.count() == 4
        assert [b.text_content() for b in btns.all()] == ['Header', 'Footer'] * 2
        lines = _one_line(p, '#rigging-both-list [data-keep]')
        assert all(n == 1 for n, _ in lines), (width, lines)
        # and the word fits inside its button, nothing cut off
        room = p.evaluate("""() => [...document.querySelectorAll('#rigging-both-list [data-keep]')].map(b => {
            const range = document.createRange(); range.selectNodeContents(b);
            const cs = getComputedStyle(b);
            const inner = b.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            return inner - range.getBoundingClientRect().width; })""")
        assert all(r >= 0 for r in room), (width, room)
        # the two of a screen side by side, one row per screen
        assert lines[0][1] == lines[1][1] and lines[2][1] == lines[3][1] and lines[2][1] > lines[0][1], lines
        # the long name stays on its line too
        names = _one_line(p, '#rigging-both-list .rigging-both-row > div:first-child')
        assert all(n == 1 for n, _ in names), names
    p.evaluate("() => document.documentElement.style.removeProperty('--lrd-left-w')")
    # and they still keep the side they say
    p.locator(f'#rigging-both-list [data-layer-id="{p.ids["A"]}"][data-keep="footer"]').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': [2] * 6}


def _tool(p):
    return p.evaluate("""() => [...document.querySelectorAll('#rigging-tool-picker .rigging-tool-btn.active')]
        .map(b => b.dataset.tool)""")


def _server_tool(p):
    return p.evaluate("async () => (await (await fetch('/api/project')).json()).riggingTool || null")


def test_auto_or_custom_is_saved_with_the_show(pg):
    """One choice for the show, view state: never an undo step, kept by
    undo, redo, a reload and a reopened file; a show without it is Auto."""
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    assert _tool(p) == ['auto']
    n = steps(p)
    custom(p, 2)
    assert _tool(p) == ['custom'] and steps(p) == n, 'switching is not an undo step'
    p.wait_for_timeout(300)
    assert _server_tool(p) == 'custom'
    click_at(p, zone_point(p, 'A', 0))
    assert bars(p, 'A') == [[0, 2]] and steps(p) == n + 1
    undo(p)
    assert bars(p, 'A') == [] and _tool(p) == ['custom']
    redo(p)
    assert bars(p, 'A') == [[0, 2]] and _tool(p) == ['custom']
    # one choice for the show: another screen selected still reads Custom
    sel(p, 'PL')
    assert _tool(p) == ['custom']
    reopen(p)
    tab(p)
    sel(p, 'A')
    assert _tool(p) == ['custom']
    assert p.locator('#rigging-custom-hint').is_visible() and not p.locator('#rigging-auto-btn').is_visible()
    # back to Auto, kept the same way; undo does not bring Custom back
    p.locator('.rigging-tool-btn[data-tool="auto"]').click()
    p.wait_for_timeout(300)
    assert _tool(p) == ['auto'] and _server_tool(p) == 'auto'
    undo(p)
    assert _tool(p) == ['auto']
    # a show opened with Custom saved on it comes back on Custom, and an
    # older show without the choice opens on Auto
    for saved, shown in (('custom', 'custom'), (None, 'auto')):
        p.evaluate("""async (t) => { const p = await (await fetch('/api/project')).json();
            if (t) p.riggingTool = t; else delete p.riggingTool;
            await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                         body: JSON.stringify(p)}); }""", saved)
        reopen(p)
        tab(p)
        sel(p, 'A')
        assert _tool(p) == [shown], (saved, _tool(p))


def _has(p, name):
    return p.evaluate("(id) => window.app.project.layers.some(l => l.id === id)", p.ids[name])


def test_delete_takes_off_the_picked_bar_or_the_selected_screens_bars_never_a_screen(pg):
    """Matt, 2026-11-08: on this tab Delete and Backspace take off the
    picked bar; with none picked they clear the selected screens' bars, as
    Clear does, one undo step; a locked screen is named and kept; a screen
    is never deleted. Delete Screen is on the Screens list's right-click
    only."""
    p = pg
    tab(p)
    view(p)
    sel(p, 'A')
    n = steps(p)
    # no bars yet: nothing to take off, and the screen stays
    for key in ('Delete', 'Backspace'):
        p.keyboard.press(key)
        p.wait_for_timeout(400)
        assert _has(p, 'A'), key
    assert steps(p) == n
    # a picked bar goes with Backspace, one step
    auto(p, 'A', size=2)
    custom(p, 2)
    n = steps(p)
    click_at(p, bar_point(p, 'A', 0))
    p.keyboard.press('Backspace')
    p.wait_for_timeout(300)
    assert bars(p, 'A') == [[2, 2], [4, 2], [6, 2], [8, 2], [10, 2]] and steps(p) == n + 1
    # nothing picked: Delete clears the selected screen's bars, one step
    p.keyboard.press('Delete')
    p.wait_for_timeout(300)
    assert bars(p, 'A') == [] and steps(p) == n + 2 and _has(p, 'A')
    undo(p)
    assert bars(p, 'A') == [[2, 2], [4, 2], [6, 2], [8, 2], [10, 2]]
    redo(p)
    assert bars(p, 'A') == []
    # a group's row goes whole, both members, from either one
    p.locator('.rigging-tool-btn[data-tool="auto"]').click()
    auto(p, 'PL', size=2)
    sel(p, 'PR')
    p.keyboard.press('Delete')
    p.wait_for_timeout(300)
    assert bars(p, 'PL') == [] and bars(p, 'PR') == [] and _has(p, 'PL') and _has(p, 'PR')
    # a locked screen is named and stays as it is
    auto(p, 'A', size=2)
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    clear_toasts(p)
    n = steps(p)
    p.keyboard.press('Delete')
    p.wait_for_timeout(300)
    assert len(bars(p, 'A')) == 6 and steps(p) == n
    assert any('A is locked' in t for t in toasts(p)), toasts(p)
    p.evaluate("() => window.app.setLockOnSelected(false)")
    p.wait_for_timeout(200)
    # the canvas right-click has no Delete Screen on this tab
    pt = wall_point(p, 'A', 5, row=2)
    p.mouse.click(pt['x'], pt['y'], button='right')
    p.wait_for_timeout(250)
    assert not p.locator('#context-menu [data-action="delete"]').is_visible()
    p.keyboard.press('Escape')
    p.evaluate("() => window.app.hideContextMenu()")
    # the Screens list's does, without the Del hint, and it deletes
    p.locator(f'#layers-list .layer-item[data-layer-id="{p.ids["A"]}"] .layer-info').click(button='right')
    p.wait_for_timeout(250)
    item = p.locator('#context-menu [data-action="delete"]')
    assert item.is_visible() and item.inner_text() == 'Delete Screen'
    item.click()
    p.wait_for_timeout(500)
    assert not _has(p, 'A')
    # and Keyboard Shortcuts says so
    row = p.evaluate("""() => [...document.querySelectorAll('tr')].map(t => t.textContent)
        .find(t => t.startsWith('Delete / Backspace'))""")
    assert 'on the Pixel Map tab' in row and 'Header/Footer' in row and 'IDM Locator' in row, row


def test_delete_on_an_older_screen_with_both_rows_clears_both(pg):
    p = pg
    p.evaluate(SAVE_BOTH_JS, p.ids['A'])
    reopen(p)
    tab(p)
    sel(p, 'A')
    n = steps(p)
    p.keyboard.press('Delete')
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [], 'riggingFooterBars': []}
    assert steps(p) == n + 1 and _has(p, 'A')
    undo(p)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [4, 4, 4], 'riggingFooterBars': [2] * 6}


def _new_layer(p, js, *args):
    before = set(p.evaluate("() => window.app.project.layers.map(l => l.id)"))
    p.evaluate(js, *args)
    for _ in range(30):
        p.wait_for_timeout(200)
        made = [i for i in p.evaluate("() => window.app.project.layers.map(l => l.id)") if i not in before]
        if made:
            p.wait_for_timeout(300)
            # out of the way, so its own strip is never under a later press
            p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
                l.offset_y = 9000 + 1500 * id; l.showOffsetY = l.offset_y; a.updateLayers([l], true, 'Away'); }""", made[0])
            p.wait_for_timeout(200)
            return made[0]
    raise AssertionError('no copy was made')


def _fields(p, lid):
    return p.evaluate("""(id) => { const l = window.app.project.layers.find(x => x.id === id);
        return { bars: l.riggingBars, starts: l.riggingBarStarts, custom: !!l.riggingCustom,
                 group: l.group_id || null, misfit: window.app.riggingMisfits(l).length }; }""", lid)


COPY_PASTE = "() => { window.app.copyLayer(); window.app.pasteLayer(); }"


def test_a_copy_of_one_member_of_a_crossing_row_keeps_only_the_bars_over_it(pg):
    """PAIR, 11 doubles across 22 panels: PL holds 6 (the last over the
    seam), PR 5 from its panel 1. A copy of either alone is covered edge
    to edge and nothing runs past its edge; the originals are untouched."""
    p = pg
    tab(p)
    auto(p, 'PL', size=2)
    pl_before, pr_before = bars(p, 'PL'), bars(p, 'PR')
    # Copy + Paste of PL: the straddler is cut to the panel over PL
    sel(p, 'PL')
    f = _fields(p, _new_layer(p, COPY_PASTE))
    assert f == {'bars': [2, 2, 2, 2, 2, 1], 'starts': None, 'custom': False, 'group': None, 'misfit': 0}, f
    # Duplicate of PR: the part of PL's straddler over PR comes with it
    sel(p, 'PR')
    f = _fields(p, _new_layer(p, "(id) => window.app.duplicateLayer(window.app.project.layers.find(l => l.id === id))",
                              p.ids['PR']))
    assert f == {'bars': [1, 2, 2, 2, 2, 2], 'starts': None, 'custom': False, 'group': None, 'misfit': 0}, f
    assert bars(p, 'PL') == pl_before and bars(p, 'PR') == pr_before
    assert not p.locator('#rigging-fit-warning').is_visible()
    # a custom row's gaps come along as they are, cut at the seam too
    view(p)
    sel(p, 'PL')
    p.locator('#rigging-clear-btn').click()
    custom(p, 4)
    drag(p, zone_point(p, 'PL', 8), zone_point(p, 'PR', 4))
    assert bars(p, 'PL') == [[8, 4]] and bars(p, 'PR') == [[1, 4]]
    sel(p, 'PR')
    f = _fields(p, _new_layer(p, COPY_PASTE))
    # PL's quad over PR's panel 0 comes as a single, then PR's own quad
    assert f == {'bars': [1, 4], 'starts': None, 'custom': True, 'group': None, 'misfit': 0}, f
    # a screen on its own keeps every bar exactly (copies keep their bars)
    click_at(p, zone_point(p, 'A', 2))
    sel(p, 'A')
    f = _fields(p, _new_layer(p, COPY_PASTE))
    assert (f['bars'], f['starts'], f['custom']) == ([4], [2], True), f


def _bar_px(p, name):
    """The on-screen height of each of a screen's bars, and the size in
    screen pixels of the numbers drawn on them."""
    return p.evaluate("""(id) => { const r = window.canvasRenderer;
        const fonts = []; const orig = r._fillText;
        r._fillText = function (text, x, y, ...rest) {
            const m = this.ctx.getTransform();
            if (/^[1-4]$/.test(String(text))) {
                fonts.push({ px: parseFloat(this.ctx.font.replace(/^bold /, '')) * Math.abs(m.d), y: m.d * y + m.f });
            }
            return orig.call(this, text, x, y, ...rest);
        };
        try { r.render(); } finally { r._fillText = orig; }
        const hits = r._riggingHits.filter(h => h.layerId === id);
        const on = fonts.filter(f => hits.some(h => f.y >= h.y0 - 1 && f.y <= h.y1 + 1));
        return { h: hits.map(h => h.y1 - h.y0), font: on.map(f => f.px) }; }""", p.ids[name])


def test_bars_stay_readable_zoomed_out_and_true_to_size_zoomed_in(pg):
    p = pg
    tab(p)
    auto(p, 'A', size=2)
    view(p, zoom=0.04)
    out = _bar_px(p, 'A')
    assert len(out['h']) == 6 and min(out['h']) >= 17.9, out
    assert len(out['font']) == 6 and min(out['font']) >= 10.9, out
    # a Custom press lands anywhere in the taller strip
    custom(p, 1)
    click_at(p, zone_point(p, 'A', 9, edge='outer'))
    assert [9, 1] in bars(p, 'A'), bars(p, 'A')
    # zoomed in, the bars are their real size: 96 units tall on a 1200 tall wall
    view(p, zoom=0.5)
    out = _bar_px(p, 'A')
    assert all(abs(h - 48) < 0.6 for h in out['h']), out
    # the binder sheet is drawn at its own size, never the tab's floor
    view(p, zoom=0.04)
    heights = p.evaluate("""(o) => { const a = window.app; const r = window.canvasRenderer;
        const plan = a.planBinder(o);
        const i = plan.findIndex(x => x.title === 'A - Header/Footer - Front View');
        const seen = []; const orig = r._drawRiggingRow;
        r._drawRiggingRow = function (layer, row, box, top, barH, ...rest) {
            seen.push({ barH, wallH: box.height, live: !this.exportMode && this.viewMode === 'rigging' });
            return orig.call(this, layer, row, box, top, barH, ...rest);
        };
        try { if (i >= 0) a.renderBinderPage(o, i); } finally { r._drawRiggingRow = orig; }
        return seen; }""", OPTS)
    sheet = [h for h in heights if not h['live']]
    assert sheet and all(h['barH'] <= max(36, min(96, h['wallH'] * 0.18)) + 0.01 for h in sheet), heights


def test_custom_press_on_the_wall_selects_and_drags_the_screen(pg):
    """In Custom only the strip outside the wall lays bars (from the wall's
    edge out past the bars); a press on the wall, its edge row included,
    selects the screen, and a drag there does what it does with Auto (this
    tab moves no screens: Pixel Map and Show Look do)."""
    p = pg
    tab(p)
    view(p)
    sel(p, 'PL')
    custom(p, 2)
    n = steps(p)
    # hovering the wall's top row: no ghost, no copy cursor
    pt = wall_point(p, 'A', 3, row=0)
    p.mouse.move(pt['x'], pt['y'])
    p.wait_for_timeout(150)
    assert p.evaluate("() => window.app._riggingGhost") is None
    assert p.evaluate("() => window.canvasRenderer.canvas.style.cursor") != 'copy'
    # a click there selects A and lays nothing
    click_at(p, pt)
    assert p.evaluate("() => [...window.app.selectedLayerIds]") == [p.ids['A']]
    assert bars(p, 'A') == [] and steps(p) == n
    # a drag from there does what the same drag does with Auto: no bars
    def dragged():
        sel(p, 'PL')
        before = (lay(p, 'A', 'offset_x', 'offset_y'), steps(p))
        drag(p, pt, {'x': pt['x'] + 60, 'y': pt['y'] - 2})
        p.wait_for_timeout(200)
        return (lay(p, 'A', 'offset_x', 'offset_y'), steps(p)) == before,             p.evaluate("() => [...window.app.selectedLayerIds]"), bars(p, 'A')
    in_custom = dragged()
    p.locator('.rigging-tool-btn[data-tool="auto"]').click()
    in_auto = dragged()
    assert in_custom == in_auto, (in_custom, in_auto)
    assert in_custom[2] == [] and in_custom[1] == [p.ids['A']], in_custom
    custom(p, 2)
    # the strip still lays bars right up to the wall's edge, and a few
    # pixels past the bars' outer edge, with the ghost first
    for edge, panel in (('wall', 0), ('outer', 6)):
        q = zone_point(p, 'A', panel, edge=edge)
        p.mouse.move(q['x'], q['y'])
        p.wait_for_timeout(150)
        assert p.evaluate("() => window.app._riggingGhost") is not None, edge
        assert p.evaluate("() => window.canvasRenderer.canvas.style.cursor") == 'copy'
        click_at(p, q)
    assert bars(p, 'A') == [[0, 2], [6, 2]]
    # the strip ends where the wall begins, and reaches past the bars
    z = p.evaluate("""(id) => { const r = window.canvasRenderer; r.render();
        const z = r._riggingZones.find(q => q.layerId === id);
        const h = r._riggingHits.filter(x => x.layerId === id);
        return { y0: z.y0, y1: z.y1, barTop: Math.min(...h.map(x => x.y0)), barBottom: Math.max(...h.map(x => x.y1)) }; }""",
                   p.ids['A'])
    top = p.evaluate("() => window.canvasRenderer.canvas.getBoundingClientRect().top")
    wall_top = wall_point(p, 'A', 0, row=0)['y'] - top
    assert z['y1'] < wall_top and z['y0'] < z['barTop'] and z['barBottom'] <= z['y1'], (z, wall_top)
