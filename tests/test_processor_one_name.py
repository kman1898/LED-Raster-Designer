"""One name slot per one-box unit; two levels only on a card chassis.

The owner's ruling (2026-09-24): "the H series and MX6000 and 2000 are the
only card based processors. all others should only have 1 name slot." Until
1.3.0 every processor got a fixed single-slot card and the tray drew BOTH the
processor's strip with a name field and the fixed card's strip with its own,
and a port's label took the nearest named level upstream - so a name typed
on the card silently outranked the unit's. Now:

* WHICH UNITS ARE CHASSIS IS THE CATALOG'S CALL, by `form`, and nothing
  else (processor_catalog.is_chassis). The ruling has to come OUT of the
  catalog: the H series and the MX2000 / MX6000 are chassis, every other
  processor is a one-box unit with one fixed card that IS its face.
* A ONE-BOX UNIT HAS EXACTLY ONE NAME SLOT, the processor strip's. Its
  fixed card's strip carries no name field (a read-only header: model,
  glance, gear), and its labels, the binder, the pull sheet and the cable
  sheet read the unit's name - _label_owner treats a fixed card as unnamed
  and the client mirrors it (cardTypedName / cardIsUnitFace).
* A NAME A 1.3 FILE LEFT ON THE CARD IS NOT LOST. On load (the project
  funnel: PUT /api/project, POST /api/project) a fixed card's name moves up
  to the unit where the unit has none, is cleared off the card either way,
  and is logged. A chassis's slot cards keep their own names.
* BREAKOUT BOXES KEEP THEIR OWN NAME FIELD - an SX40's four XDs are four
  things a tech stands in front of.

Run locally:
    python3 -m pytest tests/test_processor_one_name.py -q --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402
import processor_catalog as catalog  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────

def processors():
    return catalog.devices('processor')


def chassis_ids():
    return [d['id'] for d in processors() if catalog.is_chassis(d)]


def one_box_ids():
    return [d['id'] for d in processors() if not catalog.is_chassis(d)]


def h_series_id():
    """The H-series chassis the browser tests use, found in the catalog
    rather than named here: the H9 where the catalog has one, else the
    first H-series chassis it lists."""
    hs = [d for d in processors()
          if catalog.is_chassis(d) and d.get('name', '').startswith('H')]
    assert hs, 'the catalog lists no H-series chassis'
    return next((d['id'] for d in hs if d.get('name') == 'H9'), hs[0]['id'])


def first_card_for(chassis_device_id):
    cards = catalog.cards_for(catalog.get_device(chassis_device_id))
    assert cards, f'{chassis_device_id} accepts no card'
    return cards[0]['id']


def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def only(state):
    assert len(state['resolved']) == 1, state['resolved']
    return state['resolved'][0]


def first_card(proc):
    return next(s['card'] for s in proc['slots'] if s['card'])


def screens(*pairs):
    return [{'layerId': name, 'name': name, 'ports': count}
            for name, count in pairs]


def assigned(client, *pairs):
    """Every screen dropped, in order, on the first card that takes it, then
    the resolution (test_processor_labels' idiom)."""
    state = client.get('/api/processors').get_json()
    cards = [slot['card']['id'] for proc in state.get('resolved') or []
             for slot in proc['slots'] if slot['card']]
    sc = screens(*pairs)
    for name, _count in pairs:
        for card in cards:
            resp = client.post('/api/port-assignments/place-overflow',
                               json={'layerId': name, 'cardId': card,
                                     'screens': sc})
            if resp.status_code == 200:
                break
    resp = client.post('/api/port-assignments/resolve', json={'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolution']


def labels(resolution, name):
    scr = next(s for s in resolution['screens'] if s['layerId'] == name)
    return [p['label'] for p in scr['ports']]


def stored_processors(client):
    return client.get('/api/project').get_json()['processors']


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    """Point the app's event log at a throwaway file and return its path."""
    path = tmp_path / 'led_raster_designer.log'
    path.write_text('', encoding='utf-8')
    monkeypatch.setattr(app_module, 'LOG_FILE_PATH', str(path))
    monkeypatch.setattr(app_module, 'LOG_DIR_PATH', str(tmp_path))
    return path


def logged(path, action):
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('action') == action:
            out.append(rec.get('details') or {})
    return out


# ── 1. The catalog states the ruling ──────────────────────────────────────

def test_the_h_series_and_the_mx2000_and_mx6000_are_the_chassis():
    """Read off the catalog, never hard-coded here: every chassis it marks
    is an H-series unit or an MX2000 / MX6000, and every one of those it
    lists is marked a chassis. No other device is."""
    marked = {d['id']: d.get('name', '') for d in processors()
              if catalog.is_chassis(d)}
    assert marked, 'the catalog marks no chassis at all'
    for device_id, name in marked.items():
        assert name.startswith('H') or name.startswith('MX2000') \
            or name.startswith('MX6000'), (
            f'{device_id} ({name}) is marked a chassis but is not an H '
            f'series unit or an MX2000 / MX6000')
    for d in processors():
        name = d.get('name', '')
        expected = (name.startswith('H') and d['id'].startswith('novastar-')) \
            or name.startswith('MX2000') or name.startswith('MX6000')
        assert catalog.is_chassis(d) is expected, (
            f'{d["id"]} ({name}) chassis={catalog.is_chassis(d)}, '
            f'the ruling says {expected}')


def test_every_other_processor_is_a_one_box_unit_with_one_fixed_card():
    """new_processor gives a one-box unit exactly one slot holding a card
    born fixed - the card that IS the unit's face - and a chassis one empty
    slot per documented output card, nothing fixed about it."""
    for device_id in one_box_ids():
        proc = catalog.new_processor(device_id, 1)
        assert proc and len(proc['slots']) == 1, (device_id, proc)
        card = proc['slots'][0]['card']
        assert card and card.get('fixed') is True, (device_id, card)
        assert catalog.card_is_unit_face(card, proc), device_id
        assert not catalog.unit_is_chassis(proc), device_id
    for device_id in chassis_ids():
        proc = catalog.new_processor(device_id, 1)
        assert proc['slots'] and all(s['card'] is None
                                     for s in proc['slots']), (device_id, proc)
        assert catalog.unit_is_chassis(proc), device_id
        card = catalog.new_card(first_card_for(device_id), '1a')
        assert not catalog.card_is_unit_face(card, proc), device_id


def test_the_chassis_call_is_the_catalogs_form_and_nothing_else():
    """A device with any other form - all-in-one, sender, legacy, or none
    at all - is a one-box unit. The catalog is the one statement."""
    assert catalog.is_chassis({'form': 'chassis'})
    for form in ('all-in-one', 'sender', 'legacy', '', None):
        assert not catalog.is_chassis({'form': form}), form
    assert not catalog.is_chassis(None)
    # A card whose processor the catalog does not know falls back to what
    # it was born as.
    unknown = {'id': 'procX', 'deviceId': 'no-such-device'}
    assert catalog.card_is_unit_face({'fixed': True}, unknown)
    assert not catalog.card_is_unit_face({'fixed': False}, unknown)


# ── 2. Labels read the unit's name ────────────────────────────────────────

def test_a_one_box_units_ports_read_the_unit_name_over_a_stray_card_name(client):
    """A name left on the fixed card - by a 1.3 file, by a direct PUT - is
    not a name the unit has. The processor's is."""
    state = add_processor(client, 'novastar-mx40-pro')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'name': 'STRAY'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert client.put(f'/api/processors/{pid}',
                      json={'name': 'FOH'}).status_code == 200

    res = assigned(client, ('Main', 3))
    assert labels(res, 'Main') == ['FOH-1', 'FOH-2', 'FOH-3']
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['ports'][0]['labelSource'] == 'processor', card['ports'][0]
    assert card['ports'][0]['returnLabel'] == 'FOH-1R'


def test_a_card_name_alone_labels_nothing_on_a_one_box_unit(client):
    """With the unit unnamed, a stray card name does not step in: the
    ports print their sockets, exactly as an unnamed unit's do."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})

    res = assigned(client, ('Main', 2))
    assert labels(res, 'Main') == ['1', '2']


def test_a_box_in_front_of_a_one_box_unit_still_names_its_ports(client):
    """The breakout box keeps its own name slot: an SX40's XD named A labels
    its ten sockets A-1..A-10 whatever the unit is called."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    boxes = first_card(only(state))['cvts']
    assert len(boxes) == 4, 'a fresh SX40 arrives with its four XDs'
    client.put(f'/api/processors/{pid}', json={'name': 'SL'})
    client.put(f'/api/processors/{pid}/cvts/{boxes[0]["id"]}',
               json={'name': 'A'})

    res = assigned(client, ('Main', 12))
    got = labels(res, 'Main')
    assert got[:2] == ['A-1', 'A-2'], got
    assert got[10:12] == ['SL-1', 'SL-2'], (
        'the second box is unnamed, so its sockets read the unit\'s name '
        'with the box\'s own 1..N numbering')


def test_a_chassis_card_keeps_its_own_name_level(client):
    """Two levels on a chassis: the card's name wins over the processor's
    for the ports in that slot, as it always did."""
    chassis = h_series_id()
    state = add_processor(client, chassis)
    pid = only(state)['id']
    resp = client.put(f'/api/processors/{pid}/slots/0',
                      json={'deviceId': first_card_for(chassis)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card_id = first_card(only(resp.get_json()))['id']
    client.put(f'/api/processors/{pid}', json={'name': 'H9 SR'})
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})

    res = assigned(client, ('Main', 2))
    assert labels(res, 'Main') == ['SR-1', 'SR-2']


def test_a_backup_unit_is_titled_by_the_units_name(client):
    """The tag a consumed 1:1 backup wears ("backs up X") and the message a
    refused pick carries name the UNIT, never a fixed card's own name or
    the bare model."""
    state = add_processor(client, 'novastar-mx20')
    a_pid = state['resolved'][0]['id']
    a_card = first_card(state['resolved'][0])['id']
    state = add_processor(client, 'novastar-mx20')
    b_pid = state['resolved'][1]['id']
    b_card = first_card(state['resolved'][1])['id']
    client.put(f'/api/processors/{a_pid}', json={'name': 'A'})
    client.put(f'/api/processors/{b_pid}', json={'name': 'B'})
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': b_card})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    backup = next(c for p in resp.get_json()['resolved']
                  for s in p['slots'] for c in [s['card']]
                  if c and c['id'] == b_card)
    assert backup['backupFor']['title'] == 'A', backup['backupFor']

    state = add_processor(client, 'novastar-mx20')
    c_pid = state['resolved'][2]['id']
    c_card = first_card(state['resolved'][2])['id']
    client.put(f'/api/processors/{c_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{c_pid}/cards/{c_card}',
                      json={'backupCardId': b_card})
    assert resp.status_code == 400
    assert 'B already backs up A' in resp.get_json()['error']


# ── 3. Loading a 1.3 file ─────────────────────────────────────────────────

def test_load_adopts_the_fixed_card_name_when_the_unit_has_none(client, log_file):
    """A 1.3 file with the name on the card and none on the unit comes back
    with the unit named - through both funnels, once, logged - and the
    card cleared, so the file carries nothing invisible."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})
    legacy = client.get('/api/project').get_json()
    assert legacy['processors'][0]['slots'][0]['card']['name'] == 'SR'
    assert not legacy['processors'][0].get('name')

    assert client.put('/api/project', json=legacy).status_code == 200
    proc = stored_processors(client)[0]
    assert proc['name'] == 'SR', proc
    assert proc['slots'][0]['card']['name'] == '', proc['slots'][0]['card']
    assert labels(assigned(client, ('Main', 2)), 'Main') == ['SR-1', 'SR-2']
    events = logged(log_file, 'processor_name_adopted_from_card')
    assert len(events) == 1, events
    assert events[0]['adopted'] is True and events[0]['cardName'] == 'SR'
    assert events[0]['processorId'] == pid and events[0]['cardId'] == card_id

    # Idempotent: the healed project passes through untouched and unlogged.
    healed = client.get('/api/project').get_json()
    assert client.put('/api/project', json=healed).status_code == 200
    assert len(logged(log_file, 'processor_name_adopted_from_card')) == 1

    # The save funnel heals the same way.
    assert client.post('/api/project', json=legacy).status_code == 200
    proc = stored_processors(client)[0]
    assert proc['name'] == 'SR' and proc['slots'][0]['card']['name'] == ''
    assert len(logged(log_file, 'processor_name_adopted_from_card')) == 2


def test_load_keeps_the_units_own_name_over_the_cards(client, log_file):
    """Both named: the unit's name is the unit's, the card's is cleared and
    logged as dropped - the record carries what it said."""
    state = add_processor(client, 'novastar-vx400')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}', json={'name': 'FOH'})
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'OLD'})
    legacy = client.get('/api/project').get_json()

    assert client.put('/api/project', json=legacy).status_code == 200
    proc = stored_processors(client)[0]
    assert proc['name'] == 'FOH' and proc['slots'][0]['card']['name'] == ''
    events = logged(log_file, 'processor_name_adopted_from_card')
    assert events == [{'processorId': pid, 'deviceId': 'novastar-vx400',
                       'cardId': card_id, 'cardName': 'OLD',
                       'adopted': False, 'unitName': 'FOH'}]


def test_load_leaves_a_chassis_cards_name_alone(client, log_file):
    """A slot card is a part with a name of its own: an H-series card named
    SR in an unnamed chassis stays SR, and the chassis stays unnamed."""
    chassis = h_series_id()
    state = add_processor(client, chassis)
    pid = only(state)['id']
    resp = client.put(f'/api/processors/{pid}/slots/0',
                      json={'deviceId': first_card_for(chassis)})
    card_id = first_card(only(resp.get_json()))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})
    saved = client.get('/api/project').get_json()

    assert client.put('/api/project', json=saved).status_code == 200
    proc = stored_processors(client)[0]
    assert not proc.get('name'), proc
    assert proc['slots'][0]['card']['name'] == 'SR', proc['slots'][0]
    assert logged(log_file, 'processor_name_adopted_from_card') == []


def test_the_migration_is_the_catalogs_and_reports_what_it_moved():
    """Straight on the module: a one-box unit's card name moves up, a
    chassis's does not, an unknown device is left alone."""
    box = catalog.new_processor('novastar-mx20', 1)
    box['slots'][0]['card']['name'] = 'SR'
    chassis = catalog.new_processor(h_series_id(), 2)
    chassis['slots'][0]['card'] = catalog.new_card(
        first_card_for(h_series_id()), '2a', name='SL')
    unknown = {'id': 'proc3', 'deviceId': 'no-such-device', 'name': '',
               'slots': [{'index': 0, 'card': {'id': 'card3', 'name': 'X',
                                                'fixed': True}}]}
    project = {'processors': [box, chassis, unknown]}
    moved = catalog.adopt_fixed_card_names(project)
    assert [m['processorId'] for m in moved] == ['proc1']
    assert box['name'] == 'SR' and box['slots'][0]['card']['name'] == ''
    assert chassis['slots'][0]['card']['name'] == 'SL' and not chassis['name']
    assert unknown['slots'][0]['card']['name'] == 'X'
    assert catalog.adopt_fixed_card_names(project) == []


# ── 4. The tray, in a browser ─────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def tray_page(e2e_server, pw_browser):
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    yield pg
    context.close()


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 6, rows: 4,
        cabinet_width: 200, cabinet_height: 200});
    const app = window.app;
    const p = await j('GET', '/api/project');
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    app.resetHistory('One Name Seed');
    return p.layers[0].id;
}"""

# Replace every processor with ONE of the given device (and, for a chassis,
# a card in its first slot), stamp the screen for its platform, and put the
# screen's ports on the unit's first card. Returns the ids the tray keys on.
STAGE_JS = """async ([deviceId, cardDeviceId, platform]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const app = window.app;
    let st = await j('GET', '/api/processors');
    for (const p of (st.processors || [])) {
        await fetch(`/api/processors/${p.id}`, {method: 'DELETE'});
    }
    st = await j('POST', '/api/processors', {deviceId});
    const pid = st.processors[st.processors.length - 1].id;
    if (cardDeviceId) {
        st = await j('PUT', `/api/processors/${pid}/slots/0`,
                     {deviceId: cardDeviceId});
    }
    const screen = app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    screen.processorType = platform;
    await j('PUT', `/api/layer/${screen.id}`, {processorType: platform});
    await app.refreshProcessors();
    const proc = app._processorsResolved.find(p => p.id === pid);
    const card = proc.slots.map(s => s.card).find(Boolean);
    await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
                                 {layerId: String(screen.id)});
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', {layerId: String(screen.id),
                                          cardId: card.id});
    app.renderHardwareDock();
    return {pid, cardId: card.id, screenId: screen.id,
            boxIds: (card.cvts || []).map(c => c.id), form: proc.form};
}"""

# What name fields the tray draws for one unit: the strip's, the card
# head's, and each box's.
FIELDS_JS = """(ids) => {
    const q = (sel) => document.querySelector(sel);
    const strip = q(`[data-lrd-field="processor-name-${ids.pid}"]`);
    const head = q(`[data-hwdock="card-${ids.cardId}"]`);
    const cardField = head && head.querySelector('input.hw-dock-name');
    return {
        strip: !!strip,
        stripTitle: strip ? strip.title : null,
        cardField: cardField ? cardField.dataset.lrdField : null,
        cardHeadModel: head ? head.querySelector('.hw-dock-unit-name')
            .textContent : null,
        boxFields: ids.boxIds.map(id => !!q(
            `[data-lrd-field="processor-cvt-name-${id}"]`)),
        allNameFields: [...document.querySelectorAll(
            '#hardware-dock input.hw-dock-name')].map(i => i.dataset.lrdField),
    };
}"""


def stage(page, device_id, card_device_id, platform):
    ids = page.evaluate(STAGE_JS, [device_id, card_device_id, platform])
    page.wait_for_timeout(800)
    return ids


def test_the_tray_offers_an_sx40_one_name_field_and_its_boxes_their_own(tray_page):
    """An SX40: the processor strip's field is the unit's one name slot, its
    fixed card's head carries no name input, and each of its four XDs keeps
    a name field of its own."""
    ids = stage(tray_page, 'brompton-sx40', None, 'brompton')
    assert ids['form'] != 'chassis'
    assert len(ids['boxIds']) == 4, ids
    out = tray_page.evaluate(FIELDS_JS, ids)
    assert out['strip'], f'the SX40 strip lost its name field: {out}'
    assert out['cardField'] is None, (
        f'the SX40\'s fixed card offered a second name field: {out}')
    assert out['boxFields'] == [True] * 4, (
        f'a breakout box lost its own name field: {out}')
    assert sorted(out['allNameFields']) == sorted(
        [f'processor-name-{ids["pid"]}']
        + [f'processor-cvt-name-{b}' for b in ids['boxIds']]), out
    assert 'SR-1, SR-2' in out['stripTitle'], (
        f'the one name field must say the ports read it: {out}')


def test_the_tray_offers_an_mx40_pro_exactly_one_name_field(tray_page):
    ids = stage(tray_page, 'novastar-mx40-pro', None, 'novastar-coex-1g')
    assert ids['form'] != 'chassis'
    out = tray_page.evaluate(FIELDS_JS, ids)
    assert out['strip'] and out['cardField'] is None, out
    assert out['allNameFields'] == [f'processor-name-{ids["pid"]}'], out
    assert out['cardHeadModel'] == 'MX40 Pro', (
        f'the card head reads the model as static text: {out}')


def test_the_tray_offers_an_h_series_chassis_two_levels(tray_page):
    """A chassis keeps both: the processor strip's name and a name field on
    each slot card's head."""
    chassis = h_series_id()
    ids = stage(tray_page, chassis, first_card_for(chassis), 'novastar-armor')
    assert ids['form'] == 'chassis'
    out = tray_page.evaluate(FIELDS_JS, ids)
    assert out['strip'], out
    assert out['cardField'] == f'processor-card-name-{ids["cardId"]}', out
    assert sorted(out['allNameFields']) == sorted(
        [f'processor-name-{ids["pid"]}',
         f'processor-card-name-{ids["cardId"]}']), out
    assert 'nearest name above' in out['stripTitle'], out


def test_renaming_the_unit_relabels_its_ports_on_the_canvas(tray_page):
    """The one name reaches the drawing: typing into the strip commits as
    Rename Processor, and the screen's ports on the unit read the name the
    way the canvas asks for it."""
    ids = stage(tray_page, 'novastar-mx40-pro', None, 'novastar-coex-1g')
    read = """(ids) => {
        const app = window.app;
        const l = app.project.layers.find(x => String(x.id) === String(ids.screenId));
        return [1, 2].map(n => [app.getPortLabelText(l, n, 'primary'),
                                app.getPortLabelText(l, n, 'return')]);
    }"""
    assert tray_page.evaluate(read, ids) == [['1', '1R'], ['2', '2R']], (
        'an unnamed unit\'s attached ports print their sockets')
    try:
        field = tray_page.locator(f'[data-lrd-field="processor-name-{ids["pid"]}"]')
        field.click()
        field.fill('SL')
        tray_page.keyboard.press('Tab')
        tray_page.wait_for_timeout(1000)
        assert tray_page.evaluate(
            "() => window.app.history.map(h => h.action).slice(-1)"
        ) == ['Rename Processor']
        assert tray_page.evaluate(read, ids) == [['SL-1', 'SL-1R'],
                                                 ['SL-2', 'SL-2R']]
        # and the tray still offers exactly the one field, now holding it
        out = tray_page.evaluate(FIELDS_JS, ids)
        assert out['allNameFields'] == [f'processor-name-{ids["pid"]}'], out
        assert tray_page.evaluate(
            "(ids) => document.querySelector("
            "`[data-lrd-field=\"processor-name-${ids.pid}\"]`).value", ids
        ) == 'SL'
        stored = tray_page.evaluate(
            "async () => (await (await fetch('/api/processors')).json())"
            ".processors[0]")
        assert stored['name'] == 'SL', stored
        assert stored['slots'][0]['card']['name'] == '', (
            'the rename landed on the fixed card, not the unit')
    finally:
        tray_page.evaluate("""async (ids) => {
            await fetch(`/api/processors/${ids.pid}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: ''})});
            await window.app.refreshProcessors();
        }""", ids)
        tray_page.wait_for_timeout(300)
