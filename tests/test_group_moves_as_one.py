"""A screen group moves as one from the Screen Info X / Y fields.

Matt, 2026-09-22, on 1.1.1: two screens grouped, both selected, 0 typed into
Offset Y - and the app wrote 0 to EACH screen, stacking Screen2 (at y 1040)
on top of Screen1 (at y 0). "They should be remaining as a group and only
able to move as a group."

So for a grouped screen the X / Y fields show the GROUP's position (the
top-left of its members) and a typed value moves every member by the same
distance - whether the whole group or one member is selected - in one write
and one undo step. Ungrouped screens keep the old per-screen write.
"""
import pytest

pytestmark = pytest.mark.usefixtures('server_project_guard')


SEED = """async () => {
    const app = window.app;
    const j = (m, u, body) => fetch(u, {method: m, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project'); proj.layers = []; proj.groups = [];
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'TOP', columns: 20, rows: 5, cabinet_width: 104, cabinet_height: 208, offset_x: 0, offset_y: 0});
    await j('POST', '/api/layer/add', {name: 'BOTTOM', columns: 20, rows: 1, cabinet_width: 104, cabinet_height: 104, offset_x: 0, offset_y: 1040});
    await j('POST', '/api/layer/add', {name: 'LOOSE', columns: 4, rows: 4, cabinet_width: 100, cabinet_height: 100, offset_x: 3000, offset_y: 500});
    const p = await j('GET', '/api/project');
    const byName = Object.fromEntries(p.layers.map(l => [l.name, l]));
    // the group, seeded the way the project stores one
    byName.TOP.group_id = 'g1'; byName.BOTTOM.group_id = 'g1';
    p.groups = [{id: 'g1', name: 'Group 1', layer_ids: [byName.TOP.id, byName.BOTTOM.id], canvas_id: byName.TOP.canvas_id}];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project'); app.dedupeProjectLayers('test');
    app.renderLayers();
    app.resetHistory('Initial State');
    const b = Object.fromEntries(app.project.layers.map(l => [l.name, l]));
    return {top: b.TOP.id, bottom: b.BOTTOM.id, loose: b.LOOSE.id, group: b.TOP.group_id};
}"""

POS = """(names) => { const app = window.app;
    return Object.fromEntries(app.project.layers.filter(l => names.includes(l.name)).map(l => [l.name, [l.offset_x, l.offset_y]])); }"""

SERVER_POS = """async (names) => { const p = await fetch('/api/project').then(r => r.json());
    return Object.fromEntries(p.layers.filter(l => names.includes(l.name)).map(l => [l.name, [l.offset_x, l.offset_y]])); }"""


def _select(page, ids):
    page.evaluate("(ids) => { const app = window.app; app.setSelectedLayersByIds(ids); app.loadLayerToInputs(); }", ids)
    page.wait_for_timeout(150)


def _type_offset(page, field, value):
    page.evaluate("""([id, v]) => { const app = window.app; const el = document.getElementById(id);
        el.value = String(v); app._lastChangedInputId = id; el.dispatchEvent(new Event('change', {bubbles: true})); }""", [field, value])
    page.wait_for_timeout(400)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


@pytest.fixture
def grouped(page):
    ids = page.evaluate(SEED)
    assert ids['group'] == 'g1', ids
    page.wait_for_timeout(300)
    return ids


def test_the_fields_show_the_groups_position_for_every_member(page, grouped):
    _select(page, [grouped['bottom']])
    assert page.evaluate("[document.getElementById('offset-x').value, document.getElementById('offset-y').value]") == ['0', '0']
    _select(page, [grouped['top'], grouped['bottom']])
    assert page.evaluate("[document.getElementById('offset-x').value, document.getElementById('offset-y').value]") == ['0', '0']
    _select(page, [grouped['loose']])
    assert page.evaluate("[document.getElementById('offset-x').value, document.getElementById('offset-y').value]") == ['3000', '500']


def test_typing_y_with_the_whole_group_selected_moves_the_group(page, grouped):
    _select(page, [grouped['top'], grouped['bottom']])
    _type_offset(page, 'offset-y', 200)
    assert page.evaluate(POS, ['TOP', 'BOTTOM']) == {'TOP': [0, 200], 'BOTTOM': [0, 1240]}
    assert page.evaluate(SERVER_POS, ['TOP', 'BOTTOM']) == {'TOP': [0, 200], 'BOTTOM': [0, 1240]}
    # and 0 puts it back where it was, both screens, not on top of each other
    _type_offset(page, 'offset-y', 0)
    assert page.evaluate(POS, ['TOP', 'BOTTOM']) == {'TOP': [0, 0], 'BOTTOM': [0, 1040]}


def test_typing_x_with_one_member_selected_moves_the_whole_group(page, grouped):
    _select(page, [grouped['bottom']])
    _type_offset(page, 'offset-x', 500)
    assert page.evaluate(POS, ['TOP', 'BOTTOM', 'LOOSE']) == {'TOP': [500, 0], 'BOTTOM': [500, 1040], 'LOOSE': [3000, 500]}
    assert page.evaluate(SERVER_POS, ['TOP', 'BOTTOM']) == {'TOP': [500, 0], 'BOTTOM': [500, 1040]}
    # the fields now read the group's new position
    assert page.evaluate("document.getElementById('offset-x').value") == '500'


def test_one_undo_puts_the_whole_group_back(page, grouped):
    _select(page, [grouped['bottom']])
    _type_offset(page, 'offset-y', 300)
    assert page.evaluate(POS, ['TOP', 'BOTTOM']) == {'TOP': [0, 300], 'BOTTOM': [0, 1340]}
    page.evaluate("window.app.undo()")
    page.wait_for_timeout(500)
    assert page.evaluate(POS, ['TOP', 'BOTTOM']) == {'TOP': [0, 0], 'BOTTOM': [0, 1040]}


def test_an_ungrouped_screen_still_takes_the_value_itself(page, grouped):
    _select(page, [grouped['loose']])
    _type_offset(page, 'offset-x', 100)
    assert page.evaluate(POS, ['LOOSE', 'TOP']) == {'LOOSE': [100, 500], 'TOP': [0, 0]}
