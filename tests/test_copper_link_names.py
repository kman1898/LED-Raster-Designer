"""A copper link's name, its label the way a fiber cable has one.

The owner (2026-11-07): "So we are able to label the fiber that is
connecting via a tac snake or MTP. But I cannot label CAT6A, for example.
Also don't need to add copper. Just Cat5 6 and A are fine for base names."

- A copper link on an XD is {copper, ft?, name}. Its default name is the
  kind and the first number free among the show's copper links of that
  kind - "Cat6A 1", "Cat6A 2", "Cat6 1", "Cat5e 1" - given by the server
  when the link is first set to copper.
- A typed name is kept through a length change and a kind change; a
  default follows the kind; a blank name hands the default back.
- A show saved before names gets each unnamed copper link its default on
  open (settle_fiber), in tree order, past every name already held - the
  same numbers on every open.
- The name prints wherever the link does: the box's sheet, the binder's
  box summary, Fiber connections and Fiber page, the Data Wiring box
  inputs and the pull sheet's Label column. The kind is never said twice
  ("Cat6A 1", but "SL Rack (Cat6A)").
- The link's list reads Cat6A, Cat6, Cat5e, with no "copper" after them.

Run locally (each session takes its own free port):
    python -m pytest tests/test_copper_link_names.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)[:400]
    return resp.get_json()['error']


def _raw_box(client, box_id):
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box
    return None


def _res_link(client, box_id, key='p1'):
    for proc in client.get('/api/processors').get_json()['resolved']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return (box.get('fiberLinks') or {}).get(key)
    return None


def _sx40(client, name=''):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40',
                                                  'name': name}), 201)
    proc = st['processors'][-1]
    return proc['id'], [b['id'] for b in proc['slots'][0]['card']['cvts']]


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}',
                      json=body)


def _name(client, box, key='p1'):
    return ((_raw_box(client, box).get('fiberLinks') or {}).get(key) or {}).get('name')


# ── the server: default names, numbering, keeping the name ──────────────

def test_a_copper_link_is_named_by_its_kind_and_the_first_free_number(client):
    pid, xds = _sx40(client)
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 150}))
    _ok(_link(client, pid, xds[1], 'p1', {'copper': 'Cat6A'}))
    _ok(_link(client, pid, xds[2], 'p1', {'copper': 'Cat6', 'ft': 90}))
    _ok(_link(client, pid, xds[3], 'p1', {'copper': 'Cat5e', 'ft': 60}))
    assert [_name(client, x) for x in xds] == ['Cat6A 1', 'Cat6A 2', 'Cat6 1', 'Cat5e 1']
    # stored on the link and read back on the resolved box
    assert _raw_box(client, xds[0])['fiberLinks']['p1'] == {'copper': 'Cat6A', 'ft': 150,
                                                           'name': 'Cat6A 1'}
    assert _res_link(client, xds[0]) == {'copper': 'Cat6A', 'ft': 150, 'name': 'Cat6A 1'}
    # numbered show-wide: a second SX40's XD takes the next Cat6A
    pid2, xds2 = _sx40(client)
    _ok(_link(client, pid2, xds2[0], 'p1', {'copper': 'Cat6A'}))
    assert _name(client, xds2[0]) == 'Cat6A 3'
    # a cleared link frees its number, and the first free one is given
    _ok(_link(client, pid, xds[0], 'p1', {'cable': None}))
    _ok(_link(client, pid2, xds2[1], 'p1', {'copper': 'Cat6A'}))
    assert _name(client, xds2[1]) == 'Cat6A 1'


def test_the_name_is_kept_through_a_length_and_a_kind_change(client):
    pid, xds = _sx40(client)
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 150}))
    _ok(_link(client, pid, xds[1], 'p1', {'copper': 'Cat6', 'ft': 50}))
    # a length change keeps the default
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 120}))
    assert _raw_box(client, xds[0])['fiberLinks']['p1'] == {'copper': 'Cat6A', 'ft': 120,
                                                           'name': 'Cat6A 1'}
    # a default follows the kind: Cat6A 1 picked as Cat6 is the next Cat6
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6', 'ft': 120}))
    assert _name(client, xds[0]) == 'Cat6 2'
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 120}))
    assert _name(client, xds[0]) == 'Cat6A 1'
    # a typed name is stored trimmed and rides the length and the kind
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 120, 'name': '  SL Rack '}))
    assert _name(client, xds[0]) == 'SL Rack'
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 80}))
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat5e', 'ft': 80}))
    assert _raw_box(client, xds[0])['fiberLinks']['p1'] == {'copper': 'Cat5e', 'ft': 80,
                                                           'name': 'SL Rack'}
    # a blank name hands the default back
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat5e', 'ft': 80, 'name': ''}))
    assert _name(client, xds[0]) == 'Cat5e 1'
    # a blank sent on a link already on its default keeps that default
    _ok(_link(client, pid, xds[1], 'p1', {'copper': 'Cat6', 'ft': 50, 'name': '   '}))
    assert _name(client, xds[1]) == 'Cat6 1'
    # a name that is not text is refused, and nothing changes
    assert _refused(_link(client, pid, xds[1], 'p1',
                          {'copper': 'Cat6', 'name': 7})) == 'name must be text.'
    assert _raw_box(client, xds[1])['fiberLinks']['p1'] == {'copper': 'Cat6', 'ft': 50,
                                                           'name': 'Cat6 1'}
    # fiber on the link drops the copper and its name; copper again is new
    tac = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 12}), 201)
    tac_id = tac['fiberCables'][-1]['id']
    _ok(_link(client, pid, xds[1], 'p1', {'cable': tac_id}))
    assert 'name' not in _raw_box(client, xds[1])['fiberLinks']['p1']
    _ok(_link(client, pid, xds[1], 'p1', {'copper': 'Cat6'}))
    assert _name(client, xds[1]) == 'Cat6 1'


def test_a_show_saved_before_names_gets_its_defaults_on_open_and_keeps_them(client):
    """Unnamed copper links (a file from before) take their defaults in
    tree order, numbered past the names already held; opening the result
    again changes nothing, and an undo snapshot round-trips the names."""
    pid, xds = _sx40(client)
    pid2, xds2 = _sx40(client)
    _ok(_link(client, pid2, xds2[0], 'p1', {'copper': 'Cat6A', 'name': 'Cat6A 1'}))
    project = client.get('/api/project').get_json()
    boxes = project['processors'][0]['slots'][0]['card']['cvts']
    boxes[0]['fiberLinks'] = {'p1': {'copper': 'Cat6A', 'ft': 150}}
    boxes[1]['fiberLinks'] = {'p1': {'copper': 'Cat6'}}
    boxes[2]['fiberLinks'] = {'p1': {'copper': 'Cat6A', 'ft': 60}}
    boxes[3]['fiberLinks'] = {'p1': {'copper': 'Cat6A', 'name': '  '}}
    _ok(client.put('/api/project', json=project))
    assert [_name(client, x) for x in xds] == ['Cat6A 2', 'Cat6 1', 'Cat6A 3', 'Cat6A 4']
    assert _name(client, xds2[0]) == 'Cat6A 1'
    once = client.get('/api/project').get_json()
    _ok(client.put('/api/project', json=copy.deepcopy(once)))
    twice = client.get('/api/project').get_json()
    assert twice['processors'] == once['processors']
    # the same file opened again names them the same way
    _ok(client.put('/api/project', json=project))
    assert [_name(client, x) for x in xds] == ['Cat6A 2', 'Cat6 1', 'Cat6A 3', 'Cat6A 4']


def test_settle_names_unnamed_copper_straight_through_the_catalog():
    """The open funnel's pass on a project that never met a server."""
    proc = catalog.new_processor('brompton-sx40', 1)
    a, b = proc['slots'][0]['card']['cvts'][:2]
    a['fiberLinks'] = {'p1': {'copper': 'Cat5e', 'ft': 40}}
    b['fiberLinks'] = {'p1': {'copper': 'Cat5e'}}
    project = {'processors': [proc]}
    assert catalog.settle_fiber(project) is True
    assert a['fiberLinks'] == {'p1': {'copper': 'Cat5e', 'ft': 40, 'name': 'Cat5e 1'}}
    assert b['fiberLinks'] == {'p1': {'copper': 'Cat5e', 'name': 'Cat5e 2'}}
    assert catalog.settle_fiber(project) is False
    assert catalog.copper_name_is_default('Cat6A 12', 'Cat6A')
    assert not catalog.copper_name_is_default('Cat6A 1', 'Cat6')
    assert not catalog.copper_name_is_default('SL Rack', 'Cat6A')


# ── the browser: the field, and the name wherever the link prints ───────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# WALL, a Brompton wall on an SX40 (no redundancy); XD A's X1 and XD C's
# X1 on Cat6A at 150 ft (Cat6A 1 and Cat6A 2); XD B's X1 on a TAC.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 30,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    const st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'WALL SR'});
    const sx = st.processors[0];
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[0]}/fiber-links/p1`, {copper: 'Cat6A', ft: 150});
    await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                          link: {boxId: xds[1], key: 'p1'}});
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[2]}/fiber-links/p1`, {copper: 'Cat6A', ft: 150});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('copper_names_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 19});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    for (const id of xds) {
        try { localStorage.removeItem(`lrd_data_cable_sheet_cvt_${id}`); } catch (e) { /* none */ }
    }
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Copper Names Seed');
    return {sx: sx.id, xds, wall: wall.id};
}"""

# One box's sheet opened alone; its first link row's select and name field.
ROW_JS = """(boxId) => {
    for (const k of Object.keys(localStorage)) {
        if (k.startsWith('lrd_data_cable_sheet_cvt_')) {
            try { localStorage.removeItem(k); } catch (e) { /* none */ }
        }
    }
    try { localStorage.setItem(`lrd_data_cable_sheet_cvt_${boxId}`, '1'); } catch (e) { /* none */ }
    window.app.renderHardwareDock();
    const row = document.querySelector(`[data-lrd-fiber-link="${boxId}:p1"]`);
    if (!row) return null;
    row.scrollIntoView({block: 'center'});
    const name = row.querySelector(`[data-lrd-field="fiber-copper-name-${boxId}-p1"]`);
    return {
        value: row.querySelector('select').value,
        options: [...row.querySelector('select').options].map(o => o.textContent),
        name: name ? name.value : null,
        placeholder: name ? name.placeholder : null,
        ft: (row.querySelector('input.hw-dock-cable-ft') || {}).value || null,
    };
}"""

# Every place the binder and the pull sheet print a box's links.
PRINTED_JS = """(ids) => {
    const app = window.app;
    const box = (id) => app._dockFindCvt(id).cvt;
    const sx = app._processorsResolved.find(p => p.id === ids.sx);
    const rows = app._bFiberConnectionRows(sx, 'WALL SR')
        .filter(r => r.link && r.link.copper).map(r => r.cells);
    const page = app.binderFiberPage();
    const links = page.procs.flatMap(p => p.links).filter(l => l.atProcessor[0] && /^Cat/.test(l.atProcessor[0]))
        .map(l => [l.cable, l.atProcessor, l.atBreakout]);
    app._circuitTailCache = null;
    const pull = JSON.parse(JSON.stringify(app.buildPullList())).totals
        .filter(r => /^Cat6A$/.test(r.type)).map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    return {
        a: app.fiberLinkSummary(box(ids.xds[0])),
        c: app.fiberLinkSummary(box(ids.xds[2])),
        groups: (app._bBoxInputGroups(box(ids.xds[0]), true) || []).map(g => g.text || g.head),
        wiring: app._bwBoxInputs(box(ids.xds[0])),
        rows, links, pull,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _stored_name(pg, box_id):
    return pg.evaluate("""(id) => {
        for (const p of window.app.project.processors || []) for (const s of p.slots || [])
            for (const b of ((s.card || {}).cvts || [])) if (b.id === id)
                return ((b.fiberLinks || {}).p1 || {}).name || null;
        return null;
    }""", box_id)


def _settle_name(pg, box_id, want):
    from conftest import settled
    return settled(pg, lambda: _stored_name(pg, box_id), lambda v: v == want, 5000)


def test_the_link_row_has_a_name_field_and_the_list_drops_copper(page):
    """XD A's X1 reads Cat6A in its list - no "copper" after any kind - with
    its name, Cat6A 1, in a field beside the length; typing a name is one
    request and one undo step, a kind change keeps it, a blank gives the
    default back."""
    pg, ids = page
    a = ids['xds'][0]
    row = pg.evaluate(ROW_JS, a)
    assert row['value'] == 'cu:Cat6A', row
    assert {'Cat6A', 'Cat6', 'Cat5e'} <= set(row['options']), row
    assert not [o for o in row['options'] if 'copper' in o.lower()], row
    assert (row['name'], row['placeholder'], row['ft']) == ('Cat6A 1', 'Cat6A', '150'), row
    field = pg.locator(f'[data-lrd-field="fiber-copper-name-{a}-p1"]')
    index = pg.evaluate('() => window.app.historyIndex')
    field.fill('SL Rack')
    field.press('Enter')
    assert _settle_name(pg, a, 'SL Rack') == 'SL Rack'
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'Rename Copper Link'
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    row = pg.evaluate(ROW_JS, a)
    assert (row['name'], row['ft']) == ('SL Rack', '150'), row
    # a kind change keeps the typed name
    pg.locator(f'[data-lrd-field="fiber-link-cable-{a}-p1"]').select_option('cu:Cat6')
    from conftest import settled
    assert settled(pg, lambda: pg.evaluate(ROW_JS, a)['value'], lambda v: v == 'cu:Cat6', 5000) == 'cu:Cat6'
    assert _stored_name(pg, a) == 'SL Rack'
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, lambda: pg.evaluate(ROW_JS, a)['value'], lambda v: v == 'cu:Cat6A', 5000) == 'cu:Cat6A'
    # a blank hands the default back; undo brings the typed name again
    field = pg.locator(f'[data-lrd-field="fiber-copper-name-{a}-p1"]')
    field.fill('')
    field.press('Enter')
    assert _settle_name(pg, a, 'Cat6A 1') == 'Cat6A 1'
    pg.evaluate('() => window.app.undo()')
    assert _settle_name(pg, a, 'SL Rack') == 'SL Rack'
    assert settled(pg, lambda: pg.evaluate(ROW_JS, a)['name'], lambda v: v == 'SL Rack', 5000) == 'SL Rack'
    assert ids['errors'] == []


def test_the_name_prints_in_the_binder_and_on_the_pull_sheet(page):
    """With XD A's X1 named SL Rack and XD C's still Cat6A 2: the box
    summary, the Breakout boxes groups, Fiber connections, the Fiber page,
    the Data Wiring inputs and the pull sheet's Label all carry the name;
    the kind is said once - beside a typed name, never after a default."""
    pg, ids = page
    a = ids['xds'][0]
    if _stored_name(pg, a) != 'SL Rack':
        pg.evaluate("""async ([sx, box]) => { await window.app.setFiberLink(
            window.app._dockFindCvt(box).cvt, 'p1', {copper: 'Cat6A', ft: 150, name: 'SL Rack'}); }""",
                    [ids['sx'], a])
        assert _settle_name(pg, a, 'SL Rack') == 'SL Rack'
    out = pg.evaluate(PRINTED_JS, ids)
    assert out['a'] == "X1 SL Rack (Cat6A) 150'", out
    assert out['c'] == "X1 Cat6A 2 150'", out
    assert out['groups'] == ["X1 SL Rack (Cat6A) 150'"], out
    assert out['wiring'] == [{'head': 'X1', 'strands': [{'text': 'SL Rack (Cat6A)', 'swatch': None}]}], out
    # Fiber connections: the run by its name, the kind at either end
    assert sorted(out['rows'], key=lambda r: r[0]) == [
        ['trunk A', "SL Rack (Cat6A) 150'", 'Cat6A', 'X1 on XD A', 'Cat6A'],
        ['trunk C', "Cat6A 2 150'", 'Cat6A', 'X1 on XD C', 'Cat6A'],
    ], out
    # the Fiber page's pill and plugs: name, kind where the name lacks it, length
    assert sorted(out['links']) == [
        ["Cat6A 2 · 150'", ['Cat6A'], ['Cat6A']],
        ["SL Rack · Cat6A · 150'", ['Cat6A'], ['Cat6A']],
    ], out
    # the pull sheet: one Cat6A 150' row of two, labeled by the names, the
    # boxes they land on in Notes
    assert len(out['pull']) == 1, out
    assert out['pull'] == [['Cat6A', "150'", 2, 'Cat6A 2, SL Rack', 'XD A (X1); XD C (X1)']], out
    # back on its default, the two names fold as a run, the way TAC names do
    pg.evaluate("""async (box) => { await window.app.setFiberLink(
        window.app._dockFindCvt(box).cvt, 'p1', {copper: 'Cat6A', ft: 150, name: ''}); }""", a)
    assert _settle_name(pg, a, 'Cat6A 1') == 'Cat6A 1'
    from conftest import settled
    out = settled(pg, lambda: pg.evaluate(PRINTED_JS, ids), lambda o: o['a'] == "X1 Cat6A 1 150'", 5000)
    assert out['a'] == "X1 Cat6A 1 150'", out
    assert out['wiring'] == [{'head': 'X1', 'strands': [{'text': 'Cat6A 1', 'swatch': None}]}], out
    assert ["Cat6A 1 · 150'", ['Cat6A'], ['Cat6A']] in out['links'], out
    assert out['pull'] == [['Cat6A', "150'", 2, 'Cat6A 1-2', 'XD A (X1); XD C (X1)']], out
    assert ids['errors'] == []
