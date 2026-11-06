"""The Header/Footer tab against the rules every other tab already keeps.

The owner's rulings of 2026-11-06, each proved through the gestures that
follow it, not just the first one:

  Bars that no longer fit  "the bars no longer fit and offer Auto again,
                           rather than changing them silently." A wall
                           resized or turned leaves its bars exactly as they
                           were, says so (toast, the tab's box, the canvas,
                           the pull rows, the binder, the exports) and offers
                           Auto. Auto fits the wall's real footprint. Bars are
                           never drawn stretched.
  Copies                   "copies keep them": duplicate, paste, group
                           duplicate, duplicate canvas.
  Rear view                "mirror it": a Rear binder's sheet is mirrored and
                           the bars' digits stay readable.
  Hidden screens           "hidden doesnt count": out of the Totals box and
                           the pull list alike.

And the rules a new tab has to meet: a locked screen stays unchanged and
says why; the screen name drags on this tab like any other, and stays put.

Run locally:
    python -m pytest tests/test_header_footer_rulings.py -n 2 --dist loadfile
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# A 12 x 6 wall, a 12 x 6 wall beside it, and two 4 x 3 walls grouped as WALL.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.binder; delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    await j('PUT', '/api/project', proj);
    const wall = {columns: 12, rows: 6, cabinet_width: 200, cabinet_height: 200, panelWatts: 200,
                  flowPattern: 'tl-h', powerVoltage: 208, powerAmperage: 20,
                  powerFlowPattern: 'tl-v', powerOrganized: true, processorType: 'novastar-armor'};
    await j('POST', '/api/layer/add', {...wall, name: 'A'});
    await j('POST', '/api/layer/add', {...wall, name: 'B', offset_x: 2800});
    await j('POST', '/api/layer/add', {...wall, columns: 4, rows: 3, name: 'L', offset_x: 5600});
    await j('POST', '/api/layer/add', {...wall, columns: 4, rows: 3, name: 'R', offset_x: 6400, panelWatts: 150});
    let p = await j('GET', '/api/project');
    const f = n => p.layers.find(l => l.name === n);
    f('L').group_id = 'g1'; f('R').group_id = 'g1';
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [f('L').id, f('R').id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('hf_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Header Footer Seed');
    return Object.fromEntries(app.project.layers.map(l => [l.name, l.id]));
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': False, 'data': False},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': False,
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
    yield page
    ctx.close()
    assert not errors, errors


def tab(p, mode='rigging'):
    p.locator(f'.view-tab[data-mode="{mode}"]').click()
    p.wait_for_timeout(300)


def sel(p, *names):
    p.evaluate("""(ids) => { const a = window.app; a.setSelectedLayersByIds(ids, ids[0]);
        a.refreshNameDisplayButtons && a.refreshNameDisplayButtons(); }""",
               [p.ids[n] for n in names])
    p.wait_for_timeout(150)


def lay(p, name, *fields):
    return p.evaluate("""([id, f]) => { const l = window.app.project.layers.find(x => x.id === id);
        return Object.fromEntries(f.map(k => [k, l[k] === undefined ? null : l[k]])); }""",
                      [p.ids[name], list(fields)])


def steps(p):
    return p.evaluate("() => window.app.history.length")


def auto(p, *names):
    sel(p, *names)
    p.locator('#rigging-auto-btn').click()
    p.wait_for_timeout(250)


def typed(p, selector, value):
    field = p.locator(selector)
    field.click()
    field.fill(str(value))
    p.keyboard.press('Enter')
    p.wait_for_timeout(350)


def resize(p, name, columns):
    """Columns typed in Screen Info on Pixel Map, where the field lives, and
    back to the Header/Footer tab."""
    tab(p, 'pixel-map')
    sel(p, name)
    typed(p, '#screen-columns', columns)
    tab(p)
    sel(p, name)


def turn(p, deg):
    """The rotation picked in Screen Info on Pixel Map, and back."""
    tab(p, 'pixel-map')
    p.locator('#screen-rotation').select_option(str(deg))
    p.wait_for_timeout(400)
    tab(p)


def whole_show_in_view(p):
    p.evaluate("""() => { const r = window.canvasRenderer; r.zoom = 0.15; r.panX = 20; r.panY = 120; r.render(); }""")
    p.wait_for_timeout(100)


def toasts(p):
    return p.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(e => e.textContent)")


def clear_toasts(p):
    p.evaluate("() => { const h = document.getElementById('app-toast-host'); if (h) h.innerHTML = ''; }")


def pull_rig(p):
    return p.evaluate("""() => window.app.buildPullSheet().totals.filter(t => t.side === 'rigging')
        .map(t => ({ type: t.type, qty: t.qty, label: t.label, notes: t.notes }))""")


def total(p):
    return int(p.locator('#rigging-total-count').text_content())


def eye(p, name):
    p.locator(f'.layer-visibility-btn[onclick*="toggleLayerVisibility({p.ids[name]})"]').click()
    p.wait_for_timeout(300)


def plan(p, opts=None):
    return p.evaluate("(o) => window.app.planBinder(o).map(x => ({ title: x.title, kind: x.kind }))", opts or OPTS)


def rig_titles(p, opts=None):
    return [x['title'] for x in plan(p, opts) if x['kind'] == 'rigging']


def hits(p, name):
    """Every bar drawn for a screen: its width on the screen and a panel's."""
    return p.evaluate("""(id) => { const r = window.canvasRenderer; r.render();
        return (r._riggingHits || []).filter(h => h.layerId === id)
            .map(h => ({ row: h.row, span: h.span, x0: h.x0, x1: h.x1, unit: h.unitPx })); }""", p.ids[name])


def wall_px(p, name):
    """The wall's footprint on the screen: left edge, width, one panel."""
    return p.evaluate("""(id) => { const r = window.canvasRenderer, a = window.app;
        const l = a.project.layers.find(x => x.id === id);
        const b = r.getLayerFootprintInActiveView(l);
        const { wx } = r._canvasWorkspace(a.project.canvases.find(c => c.id === (l.show_canvas_id || l.canvas_id)));
        return { x: (b.x + wx) * r.zoom + r.panX, w: b.width * r.zoom }; }""", p.ids[name])


# ── Hidden doesn't count ─────────────────────────────────────────────────

def test_the_owners_count_rule_in_the_box_and_on_the_pull_list(pg):
    """"If it is a 12 x 6 wall with double headers, then it is only six
    headers. If there are two walls, both not hidden, then the total would
    be 12" (owner, 2026-11-06). The third case is the same rule with one of
    the two hidden."""
    p = pg
    tab(p)

    def reads(n):
        assert total(p) == n
        assert p.locator('#rigging-total-breakdown').text_content() == f'Double: {n}'
        assert [(r['type'], r['qty']) for r in pull_rig(p)] == [('Header Bar - Double', n)]

    auto(p, 'A')
    reads(6)            # one 12 x 6 wall
    auto(p, 'B')
    reads(12)           # two, both shown
    eye(p, 'B')
    reads(6)            # two, one hidden


def test_a_hidden_screen_is_out_of_the_box_and_the_pull_list_alike(pg):
    p = pg
    tab(p)
    auto(p, 'A', 'B')
    assert total(p) == 12
    assert [r['qty'] for r in pull_rig(p)] == [12]
    eye(p, 'B')
    assert total(p) == 6 and [r['qty'] for r in pull_rig(p)] == [6]
    assert p.locator('#rigging-total-breakdown').text_content() == 'Double: 6'
    # Showing it again brings it back on both, with no other gesture.
    eye(p, 'B')
    assert total(p) == 12 and [r['qty'] for r in pull_rig(p)] == [12]


def test_hiding_a_group_takes_its_bars_off_and_undo_brings_them_back(pg):
    p = pg
    tab(p)
    auto(p, 'L', 'R')
    assert total(p) == 4
    p.evaluate("() => window.app.toggleGroupVisibility('g1')")
    p.wait_for_timeout(300)
    assert total(p) == 0 and pull_rig(p) == []
    p.evaluate("() => window.app.toggleGroupVisibility('g1')")
    p.wait_for_timeout(300)
    assert total(p) == 4
    p.evaluate("() => window.app.undo()")     # undo takes the box and the list together
    p.wait_for_timeout(500)
    assert total(p) == sum(r['qty'] for r in pull_rig(p))


def test_a_hidden_screens_bars_are_kept_for_when_it_shows_again(pg):
    p = pg
    tab(p)
    auto(p, 'B')
    eye(p, 'B')
    assert lay(p, 'B', 'riggingBars')['riggingBars'] == [2] * 6
    assert rig_titles(p) == []
    eye(p, 'B')
    assert len(rig_titles(p)) == 1


# ── A locked screen stays unchanged ──────────────────────────────────────

LOCK_MSG = 'locked. Unlock'


def test_a_locked_screen_refuses_every_control_and_says_so(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    before = lay(p, 'A', 'riggingBars', 'riggingFooterBars', 'riggingSizes', 'riggingColor', 'riggingTextColor')
    n = steps(p)

    def refused(gesture):
        clear_toasts(p)
        gesture()
        p.wait_for_timeout(250)
        said = toasts(p)
        assert any(LOCK_MSG in t for t in said), said
        now = lay(p, 'A', 'riggingBars', 'riggingFooterBars', 'riggingSizes', 'riggingColor', 'riggingTextColor')
        assert now == before
        assert steps(p) == n

    refused(lambda: p.locator('#rigging-auto-btn').click())
    refused(lambda: p.locator('#rigging-clear-btn').click())
    refused(lambda: p.locator('.rigging-size-btn[data-size="1"]').click())
    refused(lambda: typed(p, '#rigging-color-hex', '#ff0000'))
    refused(lambda: typed(p, '#rigging-text-color-hex', '#00ff00'))
    # The fields snap back to what the screen really has.
    assert p.locator('#rigging-color-hex').input_value().lower() == '#000000'
    assert p.locator('#rigging-text-color-hex').input_value().lower() == '#ffffff'
    # A second press says it again: every attempt is told.
    refused(lambda: p.locator('#rigging-auto-btn').click())
    # Unlocked, the same gestures work.
    p.evaluate("() => window.app.setLockOnSelected(false)")
    p.wait_for_timeout(200)
    typed(p, '#rigging-color-hex', '#ff0000')
    assert lay(p, 'A', 'riggingColor')['riggingColor'].lower() == '#ff0000'
    p.locator('#rigging-clear-btn').click()
    p.wait_for_timeout(200)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == []


def test_a_mixed_selection_changes_the_unlocked_screens_and_names_the_locked(pg):
    p = pg
    tab(p)
    sel(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    clear_toasts(p)
    auto(p, 'A', 'B')
    assert lay(p, 'A', 'riggingBars')['riggingBars'] is None
    assert lay(p, 'B', 'riggingBars')['riggingBars'] == [2] * 6
    assert any('A is locked' in t for t in toasts(p)), toasts(p)


def _bar_point(p, name, index=0):
    return p.evaluate("""([id, i]) => { const r = window.canvasRenderer; r.render();
        const h = r._riggingHits.filter(x => x.layerId === id)[i];
        const b = r.canvas.getBoundingClientRect();
        return { x: b.left + (h.x0 + h.x1) / 2, y: b.top + (h.y0 + h.y1) / 2, unit: h.unitPx }; }""",
                      [p.ids[name], index])


def _drag_bar(p, name, panels=8):
    pt = _bar_point(p, name)
    p.mouse.move(pt['x'], pt['y'])
    p.mouse.down()
    p.mouse.move(pt['x'] + pt['unit'] * panels, pt['y'], steps=6)
    p.mouse.up()
    p.wait_for_timeout(300)


def test_a_half_locked_group_holds_the_bar_drag(pg):
    p = pg
    tab(p)
    p.evaluate("""(ids) => { const a = window.app;
        const l = a.project.layers.find(x => x.id === ids.L);
        const r = a.project.layers.find(x => x.id === ids.R);
        l.riggingBars = [1, 3]; r.riggingBars = [1, 3];
        a.updateLayers([l, r], true, 'Seed Bars'); }""", p.ids)
    p.wait_for_timeout(300)
    # Lock only R: L is free by its own flag, held by the half-locked group.
    p.evaluate("""(id) => { const a = window.app;
        const r = a.project.layers.find(x => x.id === id); r.locked = true; }""", p.ids['R'])
    held = p.evaluate("(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id); return [!!l.locked, a._layerLocked(l)]; }", p.ids['L'])
    assert held == [False, True]
    whole_show_in_view(p)
    clear_toasts(p)
    _drag_bar(p, 'L', 3)
    assert lay(p, 'L', 'riggingBars')['riggingBars'] == [1, 3]
    assert any('locked' in t for t in toasts(p)), toasts(p)


def test_a_locked_screens_bar_drag_says_so_and_an_unlocked_one_moves(pg):
    p = pg
    tab(p)
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingBars = [1, 11]; a.updateLayers([l], true, 'Seed Bars'); }""", p.ids['A'])
    p.wait_for_timeout(300)
    sel(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    clear_toasts(p)
    _drag_bar(p, 'A')
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [1, 11]
    assert any(LOCK_MSG in t for t in toasts(p)), toasts(p)
    p.evaluate("() => window.app.setLockOnSelected(false)")
    p.wait_for_timeout(200)
    _drag_bar(p, 'A')
    assert lay(p, 'A', 'riggingBars')['riggingBars'] != [1, 11]
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [1, 11]


# ── The screen name drags, and stays ─────────────────────────────────────

def _name_point(p):
    return p.evaluate("""() => { const a = window.app, c = window.canvasRenderer, l = a.currentLayer;
        c.render(); const h = l._screenNameHitRect; if (!h) return null;
        const wx = (h.x1 + h.x2) / 2, wy = (h.y1 + h.y2) / 2, b = c.canvas.getBoundingClientRect();
        return { vm: h.viewMode, x: b.left + wx * c.zoom + c.panX, y: b.top + wy * c.zoom + c.panY }; }""")


def test_the_screen_name_drags_on_this_tab_only_and_undo_steps_it_back(pg):
    p = pg
    tab(p)
    sel(p, 'A')
    pt = _name_point(p)
    assert pt and pt['vm'] == 'rigging', pt
    p.mouse.move(pt['x'], pt['y'])
    p.mouse.down()
    p.mouse.move(pt['x'] + 80, pt['y'] + 60, steps=6)
    p.mouse.up()
    p.wait_for_timeout(400)
    got = lay(p, 'A', 'screenNameOffsetXRigging', 'screenNameOffsetYRigging', 'screenNameOffsetXPower',
              'screenNameOffsetXShowLook')
    assert got['screenNameOffsetXRigging'] and got['screenNameOffsetYRigging'], got
    assert not got['screenNameOffsetXPower'] and not got['screenNameOffsetXShowLook'], got
    # It went to the server: a reload keeps it.
    p.wait_for_timeout(300)
    x = got['screenNameOffsetXRigging']
    server = p.evaluate("""(id) => fetch('/api/project').then(r => r.json())
        .then(j => j.layers.find(l => l.id === id).screenNameOffsetXRigging)""", p.ids['A'])
    assert server == x
    # A second drag starts from where the first ended, it does not jump back.
    pt = _name_point(p)
    p.mouse.move(pt['x'], pt['y'])
    p.mouse.down()
    p.mouse.move(pt['x'] + 40, pt['y'], steps=4)
    p.mouse.up()
    p.wait_for_timeout(400)
    assert lay(p, 'A', 'screenNameOffsetXRigging')['screenNameOffsetXRigging'] > x
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert lay(p, 'A', 'screenNameOffsetXRigging')['screenNameOffsetXRigging'] == x


def test_a_later_save_of_another_field_keeps_the_dragged_name(pg):
    p = pg
    tab(p)
    sel(p, 'A')
    pt = _name_point(p)
    p.mouse.move(pt['x'], pt['y'])
    p.mouse.down()
    p.mouse.move(pt['x'] + 80, pt['y'] + 60, steps=6)
    p.mouse.up()
    p.wait_for_timeout(300)
    x = lay(p, 'A', 'screenNameOffsetXRigging')['screenNameOffsetXRigging']
    p.evaluate("""() => { const a = window.app; const c = a.extractClientSideProps(a.currentLayer);
        window.__kept = [c.screenNameOffsetXRigging, c.screenNameOffsetYRigging]; }""")
    assert p.evaluate("() => window.__kept")[0] == x
    typed(p, '#screen-name-size-rigging', 44)
    assert lay(p, 'A', 'screenNameSizeRigging', 'screenNameOffsetXRigging') == {
        'screenNameSizeRigging': 44, 'screenNameOffsetXRigging': x}
    assert p.evaluate("() => (document.activeElement || {}).id || ''") != 'screen-name-size-rigging'


# ── The Names row ────────────────────────────────────────────────────────

def test_the_names_row_shows_only_with_a_group_selected(pg):
    p = pg
    tab(p)
    row = p.locator('#name-display-row-rigging')
    sel(p, 'A')
    assert not row.is_visible()
    sel(p, 'L')
    assert row.is_visible()
    tip = row.get_attribute('data-tooltip')
    assert 'selected group' in tip and 'layer' not in tip.lower()
    assert 'Group prints one sheet' in tip
    panel = p.locator('.panel[data-tab="rigging"]').first.inner_html().lower()
    assert 'layer' not in panel


# ── Copies keep them ─────────────────────────────────────────────────────

FIELDS = ['riggingSizes', 'riggingBars', 'riggingFooterBars', 'riggingColor', 'riggingTextColor',
          'showLabelNameRigging', 'screenNameSizeRigging', 'screenNameOffsetXRigging',
          'screenNameOffsetYRigging']


def _dress(p, name):
    p.evaluate("""([id, f]) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        Object.assign(l, { riggingSizes: [2, 4], riggingBars: [4, 4, 4], riggingFooterBars: [2, 2, 4, 2, 2],
            riggingColor: '#112233', riggingTextColor: '#445566', showLabelNameRigging: false,
            screenNameSizeRigging: 41, screenNameOffsetXRigging: 15, screenNameOffsetYRigging: 25 });
        a.updateLayers([l], true, 'Dress Bars'); }""", [p.ids[name], FIELDS])
    p.wait_for_timeout(350)


def _fields_of(p, name):
    return p.evaluate("""([n, f]) => { const l = window.app.project.layers.find(x => x.name === n);
        return Object.fromEntries(f.map(k => [k, l[k]])); }""", [name, FIELDS])


def _fields_on_server(p, name):
    return p.evaluate("""([n, f]) => fetch('/api/project').then(r => r.json()).then(j => {
        const l = j.layers.find(x => x.name === n);
        return Object.fromEntries(f.map(k => [k, l[k]])); })""", [name, FIELDS])


def test_duplicate_and_paste_keep_the_bars_on_their_own_arrays(pg):
    p = pg
    tab(p)
    _dress(p, 'A')
    want = _fields_of(p, 'A')
    sel(p, 'A')
    p.evaluate("() => window.app.duplicateLayer(window.app.currentLayer)")
    p.wait_for_timeout(700)
    names = p.evaluate("() => window.app.project.layers.map(l => l.name)")
    dup = [n for n in names if n not in ('A', 'B', 'L', 'R')][0]
    assert _fields_of(p, dup) == want
    assert _fields_on_server(p, dup) == want
    sel(p, 'A')
    p.evaluate("() => { window.app.copyLayer(); window.app.pasteLayer(); }")
    p.wait_for_timeout(700)
    names2 = p.evaluate("() => window.app.project.layers.map(l => l.name)")
    pasted = [n for n in names2 if n not in names][0]
    assert _fields_of(p, pasted) == want
    assert _fields_on_server(p, pasted) == want
    # The copy's bars are its own: an edit to one leaves the other alone.
    p.evaluate("""(n) => { const a = window.app; const l = a.project.layers.find(x => x.name === n);
        l.riggingBars[0] = 3; l.riggingBars.push(1); }""", dup)
    assert _fields_of(p, 'A')['riggingBars'] == [4, 4, 4]
    assert _fields_of(p, pasted)['riggingBars'] == [4, 4, 4]
    # And the pull list counts the copies.
    p.evaluate("""(n) => { const a = window.app; const l = a.project.layers.find(x => x.name === n);
        l.riggingBars = [4, 4, 4]; }""", dup)
    assert sum(r['qty'] for r in pull_rig(p) if r['type'].startswith('Header')) == 9


def test_a_duplicated_group_and_a_duplicated_canvas_keep_the_bars(pg):
    p = pg
    tab(p)
    _dress(p, 'L')
    want = _fields_of(p, 'L')
    p.evaluate("() => window.app.duplicateGroup('g1')")
    p.wait_for_timeout(800)
    names = p.evaluate("() => window.app.project.layers.map(l => l.name)")
    copy = [n for n in names if n not in ('A', 'B', 'L', 'R') and n.startswith('L')][0]
    assert _fields_of(p, copy) == want
    assert _fields_on_server(p, copy) == want
    cid = p.evaluate("() => window.app.project.active_canvas_id")
    p.evaluate("(c) => window.app.duplicateCanvas(c)", cid)
    p.wait_for_timeout(800)
    clones = p.evaluate("""(f) => window.app.project.layers.filter(l => (l.riggingBars || []).join() === '4,4,4')
        .map(l => Object.fromEntries(f.map(k => [k, l[k]])))""", FIELDS)
    assert len(clones) >= 4 and all(c == want for c in clones), clones


# ── Rear view: mirror it ─────────────────────────────────────────────────

REAR_JS = """([o, view]) => { const a = window.app, r = window.canvasRenderer;
    a.getBinderInfo().view; const q = o; const binder = a.project.binder;
    a.project.binder = { ...(binder || {}), view };
    const plan = a.planBinder(q);
    const i = plan.findIndex(x => x.kind === 'rigging');
    const P = CanvasRenderingContext2D.prototype, fill = P.fillText, rect = P.fillRect;
    const was = r._isCanvasMirrored.bind(r);
    const mirrored = [], digits = [], bars = [];
    r._isCanvasMirrored = function (c) { const v = was(c); mirrored.push(v); return v; };
    P.fillText = function (t, x, y, m) { const tr = this.getTransform();
        if (/^[0-9]$/.test(String(t))) digits.push(Math.sign(tr.a));
        return fill.call(this, t, x, y, m); };
    P.fillRect = function (x, y, w, h) { const tr = this.getTransform();
        if (this.fillStyle === '#123456') bars.push(Math.round(tr.a * x + tr.e)); return rect.call(this, x, y, w, h); };
    try { a.renderBinderPage(q, i); } finally {
        P.fillText = fill; P.fillRect = rect; r._isCanvasMirrored = was;
        if (binder === undefined) delete a.project.binder; else a.project.binder = binder; }
    return { title: plan[i].title, mirrored: mirrored.some(Boolean), digits: [...new Set(digits)], bars,
             keys: a.project.canvases.map(c => Object.keys(c).filter(k => k === 'rigging_perspective')).flat(),
             rootKey: 'rigging_perspective' in a.project }; }"""


def test_a_rear_binder_mirrors_the_sheet_and_keeps_its_digits_readable(pg):
    p = pg
    tab(p)
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingBars = [1, 2, 9]; l.riggingColor = '#123456'; a.updateLayers([l], true, 'Seed Bars'); }""", p.ids['A'])
    p.wait_for_timeout(300)
    front = p.evaluate(REAR_JS, [OPTS, 'front'])
    rear = p.evaluate(REAR_JS, [OPTS, 'rear'])
    assert front['title'].endswith('Header/Footer - Front View'), front
    assert rear['title'].endswith('Header/Footer - Rear View'), rear
    assert front['mirrored'] is False and rear['mirrored'] is True
    assert front['digits'] == [1] and rear['digits'] == [1], (front, rear)   # upright both ways
    # The narrow bar stood at the left from the front: its order turns round.
    # (The sheet paints twice, measuring and drawing: the first three are one row.)
    assert front['bars'][:3] == sorted(front['bars'][:3])
    assert rear['bars'][:3] == sorted(rear['bars'][:3], reverse=True)
    # Nothing of the paint is left on the show, and the tab itself never mirrors.
    assert rear['keys'] == [] and rear['rootKey'] is False
    assert p.evaluate("() => window.canvasRenderer.isMirroredView()") is False


def test_the_tab_stays_front_on_when_power_is_set_to_back(pg):
    p = pg
    tab(p)
    p.evaluate("() => { const c = window.app.project.canvases[0]; c.power_perspective = 'back'; c.data_flow_perspective = 'back'; }")
    assert p.evaluate("() => window.canvasRenderer._isCanvasMirrored(window.app.project.canvases[0])") is False


# ── Bars that no longer fit ──────────────────────────────────────────────

def _no_stretch(p, name, have):
    """Every bar is whole panels of the wall, from the wall's left edge."""
    bars = hits(p, name)
    wall = wall_px(p, name)
    panel = wall['w'] / lay(p, name, 'columns')['columns'] if not lay(p, name, 'rotation')['rotation'] else None
    assert sum(b['span'] for b in bars) == have
    left = min(b['x0'] for b in bars)
    assert abs(left - wall['x']) < 1.5, (left, wall)
    if panel:
        for b in bars:
            assert abs((b['x1'] - b['x0']) - b['span'] * panel) < 1.5, (b, panel)
    return bars


def test_a_wall_made_wider_keeps_its_bars_says_so_and_auto_fits_it(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    assert not p.locator('#rigging-fit-warning').is_visible()
    n = steps(p)
    clear_toasts(p)
    # Typed in Screen Info, the way a person does it.
    resize(p, 'A', 16)
    assert lay(p, 'A', 'columns', 'riggingBars') == {'columns': 16, 'riggingBars': [2] * 6}
    assert any('no longer fit' in t and 'cover 12 panels' in t and 'is 16' in t for t in toasts(p)), toasts(p)
    box = p.locator('#rigging-fit-warning')
    assert box.is_visible()
    assert 'A: header bars cover 12 panels, the wall is 16.' in p.locator('#rigging-fit-text').text_content()
    _no_stretch(p, 'A', 12)
    # The pull list keeps the count and says it cannot be trusted.
    [row] = pull_rig(p)
    assert row['qty'] == 6 and 'no longer fit' in row['label'], row
    assert 'cover 12 panels' in row['notes'] and 'Auto' in row['notes'], row
    # One step for the edit; Auto is another, and undo walks them back.
    typed_steps = steps(p)
    assert typed_steps == n + 1
    p.locator('#rigging-fit-auto').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2] * 8
    assert not box.is_visible()
    assert pull_rig(p)[0]['qty'] == 8 and 'no longer' not in pull_rig(p)[0]['label']
    _no_stretch(p, 'A', 16)
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2] * 6
    assert box.is_visible()
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(600)
    assert lay(p, 'A', 'columns')['columns'] == 12
    assert not box.is_visible()


def test_a_wall_made_narrower_draws_past_its_edge_never_squeezed(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    p.locator('.rigging-mode-btn[data-mode="footer"]').click()
    p.wait_for_timeout(150)
    p.locator('#rigging-auto-btn').click()
    p.wait_for_timeout(250)
    resize(p, 'A', 10)
    text = p.locator('#rigging-fit-text').text_content()
    assert 'A: header bars cover 12 panels, the wall is 10.' in text
    assert 'A: footer bars cover 12 panels, the wall is 10.' in text
    bars = hits(p, 'A')
    wall = wall_px(p, 'A')
    assert max(b['x1'] for b in bars) > wall['x'] + wall['w'] + 1
    # The size picks and the Auto button in the box fit both rows.
    p.locator('#rigging-fit-auto').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars', 'riggingFooterBars') == {'riggingBars': [2] * 5, 'riggingFooterBars': [2] * 5}


def test_a_turned_wall_warns_and_auto_fits_its_rows(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    clear_toasts(p)
    turn(p, 90)
    assert lay(p, 'A', 'rotation', 'riggingBars') == {'rotation': 90, 'riggingBars': [2] * 6}
    assert 'A: header bars cover 12 panels, the wall is 6.' in p.locator('#rigging-fit-text').text_content()
    assert any('no longer fit' in t for t in toasts(p)), toasts(p)
    # Auto on the tab: the wall's real footprint, its six rows.
    sel(p, 'A')
    p.locator('#rigging-auto-btn').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2, 2, 2]
    assert not p.locator('#rigging-fit-warning').is_visible()
    bars = hits(p, 'A')
    wall = wall_px(p, 'A')
    assert abs(sum(b['x1'] - b['x0'] for b in bars) - wall['w']) < 1.5
    # Turned 180 the wall is its columns again, 12: three doubles no longer fit.
    turn(p, 180)
    assert 'A: header bars cover 6 panels, the wall is 12.' in p.locator('#rigging-fit-text').text_content()


def test_a_square_turn_needs_no_warning(pg):
    p = pg
    tab(p)
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.rows = 12; a.updateLayers([l], true, 'Square'); }""", p.ids['A'])
    p.wait_for_timeout(500)
    auto(p, 'A')
    turn(p, 90)
    assert not p.locator('#rigging-fit-warning').is_visible()


def test_the_box_auto_refuses_a_locked_screen_and_fits_the_rest(pg):
    p = pg
    tab(p)
    auto(p, 'A', 'B')
    p.evaluate("""(ids) => { const a = window.app; for (const id of [ids.A, ids.B]) {
        const l = a.project.layers.find(x => x.id === id); l.columns = 14; }
        a.updateLayers(a.project.layers.filter(l => l.id === ids.A || l.id === ids.B), true, 'Wider'); }""", p.ids)
    p.wait_for_timeout(500)
    sel(p, 'A')
    p.evaluate("() => window.app.setLockOnSelected(true)")
    p.wait_for_timeout(200)
    clear_toasts(p)
    p.locator('#rigging-fit-auto').click()
    p.wait_for_timeout(300)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2] * 6
    assert lay(p, 'B', 'riggingBars')['riggingBars'] == [2] * 7
    assert any(LOCK_MSG in t for t in toasts(p)), toasts(p)
    assert p.locator('#rigging-fit-warning').is_visible()


def test_a_hidden_screen_that_no_longer_fits_does_not_warn(pg):
    p = pg
    tab(p)
    auto(p, 'B')
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.columns = 14; a.updateLayers([l], true, 'Wider'); }""", p.ids['B'])
    p.wait_for_timeout(400)
    assert p.locator('#rigging-fit-warning').is_visible()
    eye(p, 'B')
    assert not p.locator('#rigging-fit-warning').is_visible()
    assert p.evaluate("() => window.app.riggingFitWarning()") == ''


def test_the_binder_prints_the_note_and_the_export_says_so(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    resize(p, 'A', 16)
    out = p.evaluate("""(o) => { const a = window.app; const plan = a.planBinder(o);
        const i = plan.findIndex(x => x.kind === 'rigging');
        const j = plan.findIndex(x => x.kind === 'pull');
        return { sheet: a.renderBinderPage(o, i).texts, pull: a.renderBinderPage(o, j).texts }; }""", OPTS)
    sheet = ' '.join(out['sheet'])
    assert 'Bars no longer fit' in sheet.replace('BARS NO LONGER FIT', 'Bars no longer fit')
    assert 'Header bars cover 12 panels, the wall is 16.' in sheet, sheet
    assert 'A (bars no longer fit)' in ' '.join(out['pull'])
    warn = p.evaluate("() => window.app.riggingFitWarning()")
    assert warn.startswith('Header/Footer bars no longer fit.') and 'Auto' in warn


def test_a_saved_show_with_bars_that_no_longer_fit_opens_as_it_was(pg):
    p = pg
    tab(p)
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingBars = [2, 2]; a.updateLayers([l], false); }""", p.ids['A'])
    p.wait_for_timeout(300)
    p.reload()
    p.wait_for_function("() => window.app && window.app._initialLoadComplete")
    p.wait_for_timeout(1000)
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2, 2]
    tab(p)
    assert p.locator('#rigging-fit-warning').is_visible()


def test_an_older_show_with_none_of_the_fields_reads_empty(pg):
    p = pg
    tab(p)
    p.evaluate("""() => { const a = window.app; for (const l of a.project.layers) {
        for (const k of Object.keys(l)) if (/[Rr]igging/.test(k)) delete l[k]; }
        a.loadLayerToInputs(); a.renderLayers(); window.canvasRenderer.render(); }""")
    p.wait_for_timeout(200)
    assert total(p) == 0 and pull_rig(p) == [] and rig_titles(p) == []
    assert not p.locator('#rigging-fit-warning').is_visible()
    assert p.evaluate("() => window.app.riggingFitWarning()") == ''
    auto(p, 'A')
    assert lay(p, 'A', 'riggingBars')['riggingBars'] == [2] * 6


# ── The exports say so too ───────────────────────────────────────────────

SAVES_JS = """async ([how]) => { const a = window.app; const keep = [a.saveBlobWithPicker, a.saveMultipleFiles];
    const files = [];
    a.saveBlobWithPicker = async (b, name) => { const blob = typeof b === 'function' ? await b() : b;
        files.push({ name, text: name.endsWith('.svg') ? await blob.text() : '' }); };
    a.saveMultipleFiles = async (list) => { for (const f of list)
        files.push({ name: f.filename, text: f.filename.endsWith('.svg') ? await f.blob.text() : '' }); };
    try {
        if (how === 'binder') { a.openExportModal('binder'); await a.exportBinder('Show'); }
        else if (how === 'pull') await a.exportPullSheet('Show');
        else await a.performExport('Show', how, ['rigging'], a.project.canvases.map(c => c.id));
    } finally { [a.saveBlobWithPicker, a.saveMultipleFiles] = keep;
        document.getElementById('export-modal').style.display = 'none'; }
    return files; }"""


@pytest.mark.parametrize('how', ['binder', 'pull'])
def test_the_paper_exports_go_ahead_and_warn(pg, how):
    p = pg
    tab(p)
    auto(p, 'A')
    resize(p, 'A', 16)
    clear_toasts(p)
    files = p.evaluate(SAVES_JS, [how])
    assert files, 'nothing saved'
    assert any('Header/Footer bars no longer fit' in t and 'cover 12 panels' in t for t in toasts(p)), toasts(p)


def test_paper_exports_say_nothing_when_every_bar_fits(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    clear_toasts(p)
    assert p.evaluate(SAVES_JS, ['pull'])
    assert not any('no longer fit' in t for t in toasts(p)), toasts(p)


def test_the_svg_draws_the_mark_and_the_bars_at_their_true_width(pg):
    p = pg
    tab(p)
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.riggingBars = [2, 2]; a.updateLayers([l], false); }""", p.ids['A'])
    p.wait_for_timeout(300)
    [svg] = p.evaluate(SAVES_JS, ['svg'])
    assert 'No longer fits' in svg['text'] and 'stroke-dasharray' in svg['text']


# ── With the rest of 1.6.0 ───────────────────────────────────────────────

def test_a_hex_field_saves_on_enter_lets_go_and_undoes_in_one_step(pg):
    p = pg
    tab(p)
    sel(p, 'A')
    n = steps(p)
    typed(p, '#rigging-color-hex', '#336699')
    assert lay(p, 'A', 'riggingColor')['riggingColor'].lower() == '#336699'
    assert p.evaluate("() => document.activeElement.id") != 'rigging-color-hex'
    assert steps(p) == n + 1
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert p.locator('#rigging-color-hex').input_value().lower() == '#000000'


def test_a_fill_the_field_guard_refuses_changes_nothing(pg):
    # A write past the app's setters, the way a browser's filler lands: the
    # guard puts the field back before the color or the size handler runs.
    p = pg
    tab(p)
    sel(p, 'A')
    n = steps(p)
    out = p.evaluate("""() => {
        const frame = document.createElement('iframe');
        frame.style.display = 'none';
        document.body.appendChild(frame);
        const fill = (el, value) => {
            Object.getOwnPropertyDescriptor(frame.contentWindow.HTMLInputElement.prototype, 'value').set.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        };
        document.activeElement && document.activeElement.blur();
        const hex = document.getElementById('rigging-color-hex');
        const size = document.getElementById('screen-name-size-rigging');
        fill(hex, '#ff0000');
        fill(size, '99');
        frame.remove();
        return [hex.value, size.value]; }""")
    p.wait_for_timeout(200)
    assert out[0].lower() == '#000000' and out[1] == '30', out
    assert lay(p, 'A', 'riggingColor', 'screenNameSizeRigging') == {'riggingColor': None, 'screenNameSizeRigging': None}
    assert steps(p) == n


def test_bars_ride_the_wall_in_show_look_and_stay_out_of_it(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    before = p.evaluate("(id) => window.canvasRenderer._riggingHits.filter(h => h.layerId === id)[0].x0", p.ids['A'])
    p.evaluate("""(id) => { const a = window.app; const l = a.project.layers.find(x => x.id === id);
        l.showOffsetX = (l.showOffsetX || 0) + 400; a.updateLayers([l], true, 'Move'); }""", p.ids['A'])
    p.wait_for_timeout(300)
    bars = hits(p, 'A')
    wall = wall_px(p, 'A')
    assert bars[0]['x0'] != before and abs(bars[0]['x0'] - wall['x']) < 1.5
    tab(p, 'show-look')
    drawn = p.evaluate("() => { const r = window.canvasRenderer; r.render(); return r.viewMode; }")
    assert drawn == 'show-look'
    assert not p.locator('#rigging-auto-btn').is_visible()


def test_auto_on_a_grouped_wall_writes_each_member_and_undoes_as_one(pg):
    p = pg
    tab(p)
    auto(p, 'L', 'R')
    assert lay(p, 'L', 'riggingBars')['riggingBars'] == [2, 2]
    assert lay(p, 'R', 'riggingBars')['riggingBars'] == [2, 2]
    assert total(p) == 4
    p.evaluate("() => window.app.undo()")
    p.wait_for_timeout(500)
    assert not lay(p, 'L', 'riggingBars')['riggingBars']
    assert not lay(p, 'R', 'riggingBars')['riggingBars']


def test_a_mirror_screen_keeps_its_own_bars_and_is_counted(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    p.evaluate("""(ids) => { const a = window.app; const b = a.project.layers.find(x => x.id === ids.B);
        b.dataMirrorOf = ids.A; a.updateLayers([b], true, 'Mirror'); }""", p.ids)
    p.wait_for_timeout(400)
    assert not lay(p, 'B', 'riggingBars')['riggingBars']     # a data mirror, not a bar mirror
    auto(p, 'B')
    assert lay(p, 'B', 'dataMirrorOf')['dataMirrorOf'] == p.ids['A']
    assert total(p) == 12 and pull_rig(p)[0]['qty'] == 12


def test_the_sheet_takes_its_number_in_the_screens_series(pg):
    p = pg
    tab(p)
    auto(p, 'A')
    numbers = p.evaluate("""(o) => window.app.planBinder(o).filter(x => x.kind === 'rigging').map(x => x.number)""", OPTS)
    assert numbers == ['2.1'], numbers
