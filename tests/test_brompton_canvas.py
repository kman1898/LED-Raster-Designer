"""A Brompton processor's screens must fit the canvas Brompton publishes.

The owner's ruling (2026-10-07), on Brompton's own figures: a Brompton
processor maps every screen it drives into ONE processing canvas, and
everything it drives must fit. Its SPAN is the bounding box, in Pixel Map
pixels, of every visible cabinet whose data reaches it - its own ports,
its cards', any box on it. A backup mirrors its main, so only the main is
measured.

  * SX40 / S8: 4096 x 2160 (4K DCI), or a custom canvas - width rounded up
    to even, at most 4094 wide, 4095 tall, 9,000,000 px. With Ultra Low
    Latency the presets go and the height limit is 2047.
  * M2 / S4 / T1: one of 1920x1080, 1080x1920, 1600x1200, 2880x720,
    720x2880.
  * SQ200: up to 65,535 px wide or tall.

Over it is REFUSED ("throw an error and not allow it"): a mapping, on the
server (port_assignment.canvas_refusal); an edit to a mapped screen, in the
client's guard before its PUT (app-port-assignment _canvasGuardEdit, on
canvasFit - the JS twin held to processor_catalog.canvas_fit here). A show
already over is never changed: it is flagged on the processor, in the tray
and in the binder.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_brompton_canvas.py -v --browser chromium
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402
from conftest import settled  # noqa: E402

SX = 'brompton-sx40'
SX_LIMIT = ("An SX40's canvas is 4096 × 2160, or up to 4094 wide and 4095 "
            "tall within 9,000,000 px.")

# (device, width, height, ull, fits)
FIT_TABLE = [
    (SX, 4096, 2160, False, True),       # the 4K DCI preset, exactly
    (SX, 4096, 2161, False, False),
    (SX, 4094, 2198, False, True),       # custom: 8,998,612 px
    (SX, 4094, 2199, False, False),      # custom: over 9,000,000
    (SX, 4093, 2198, False, True),       # 4093 is taken as 4094
    (SX, 4095, 2200, False, False),      # 4096 wide, past every limit
    (SX, 4095, 1000, False, True),       # inside the 4096 x 2160 preset
    (SX, 4095, 1000, True, False),       # ULL: no preset, 4096 > 4094
    (SX, 4094, 2047, True, True),
    (SX, 4094, 2048, True, False),
    (SX, 4096, 2000, True, False),       # no preset under ULL
    (SX, 720, 4095, False, True),
    ('brompton-s8', 4096, 2160, False, True),
    ('brompton-s8', 4094, 2199, False, False),
    ('brompton-m2', 1920, 1080, False, True),
    ('brompton-m2', 1080, 1920, False, True),
    ('brompton-m2', 2880, 720, False, True),
    ('brompton-m2', 720, 2880, False, True),
    ('brompton-m2', 1600, 1200, False, True),
    ('brompton-m2', 2000, 1100, False, False),
    ('brompton-m2', 1921, 1081, False, False),
    ('brompton-s4', 2000, 700, False, True),    # inside 2880 x 720
    ('brompton-t1', 1700, 1200, False, False),
    ('brompton-m2', 1920, 1080, True, True),    # ULL changes nothing here
    ('brompton-sq200', 65535, 65535, False, True),
    ('brompton-sq200', 65536, 100, False, False),
    ('brompton-sq200', 100, 65536, False, False),
]


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── A. the fit, and where its figures come from ──────────────────────────

@pytest.mark.parametrize('device_id,width,height,ull,fits', FIT_TABLE)
def test_the_canvas_fit_table(device_id, width, height, ull, fits):
    device = catalog.get_device(device_id)
    why = catalog.canvas_fit(device, width, height, ull, title='Unit')
    assert (why is None) == fits, why


def test_the_refusal_sentences_per_model():
    assert catalog.canvas_fit(catalog.get_device(SX), 4352, 2160,
                              title='Tessera SX40 S1') == (
        "Tessera SX40 S1 can't take this: its screens would span 4352 × "
        "2160 px. " + SX_LIMIT)
    assert catalog.canvas_fit(catalog.get_device(SX), 4094, 2100, True,
                              title='Tessera SX40') == (
        "Tessera SX40 can't take this: its screens would span 4094 × 2100 "
        "px. With low latency on, an SX40's canvas is up to 4094 wide and "
        "2047 tall within 9,000,000 px.")
    assert catalog.canvas_fit(catalog.get_device('brompton-m2'), 2000, 1100,
                              title='Tessera M2') == (
        "Tessera M2 can't take this: its screens would span 2000 × 1100 px. "
        "An M2's canvas is 1920 × 1080, 1080 × 1920, 1600 × 1200, 2880 × 720 "
        "or 720 × 2880.")
    assert catalog.canvas_fit(catalog.get_device('brompton-t1'), 2000, 1100,
                              title='Tessera T1').endswith(
        "A T1's canvas is 1920 × 1080, 1080 × 1920, 1600 × 1200, 2880 × 720 "
        "or 720 × 2880.")
    assert catalog.canvas_fit(catalog.get_device('brompton-sq200'), 70000, 10,
                              title='Tessera SQ200') == (
        "Tessera SQ200 can't take this: its screens would span 70000 × 10 "
        "px. An SQ200's canvas is up to 65,535 px wide or tall.")
    # a show already past it is said in the present
    assert catalog.canvas_fit(catalog.get_device(SX), 4352, 2160,
                              title='Tessera SX40', present=True).startswith(
        "Tessera SX40 can't take this: its screens span 4352 × 2160 px.")
    # a device with no published canvas is never refused
    assert catalog.canvas_fit(catalog.get_device('novastar-h9'), 99999, 99999) \
        is None


def test_every_canvas_carries_brompton_sources():
    """Each figure is read off Brompton's own pages: every canvas names
    its page and the words, and only Brompton processors carry one."""
    with_canvas = {d['id']: d['canvas'] for d in catalog.devices()
                   if d.get('canvas')}
    assert set(with_canvas) == {'brompton-sx40', 'brompton-s8', 'brompton-s4',
                                'brompton-m2', 'brompton-t1', 'brompton-sq200'}
    for device_id, spec in with_canvas.items():
        assert spec['source'].startswith('https://www.bromptontech.com/'), device_id
        assert spec['sourceText'], device_id
    for device_id in ('brompton-sx40', 'brompton-s8'):
        spec = with_canvas[device_id]
        assert 'Canvas%20Resolutions' in spec['source']
        assert '9,000,000' in spec['sourceText']
        assert 'Ultra%20Low%20Latency' in spec['ullSource']
        assert '2047' in spec['ullSourceText']
        assert spec['custom'] == {'maxW': 4094, 'maxH': 4095,
                                  'maxPixels': 9000000, 'evenWidth': True}
    for device_id in ('brompton-s4', 'brompton-m2', 'brompton-t1'):
        assert '1920x1080' in with_canvas[device_id]['sourceText']
    assert 'SQ200-Data-Sheet' in with_canvas['brompton-sq200']['source']
    assert '65535' in with_canvas['brompton-sq200']['sourceText']


# ── B. the server holds a mapping to the canvas ──────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 409, resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert body.get('canvas') is True, body
    return body['error']


def _sx40(client, name):
    st = _ok(client.post('/api/processors',
                         json={'deviceId': SX, 'name': name}), 201)
    proc = st['resolved'][-1]
    return proc['id'], proc['slots'][0]['card']['id']


def _screen(layer, x, ports=12, width=3840, height=1536, ull=False):
    """A screen as the client sends it where a canvas is in play: its ports
    and the Pixel Map rect each one's cabinets cover - here one column
    strip per port, left to right, from x."""
    step = width / ports
    return {'layerId': layer, 'name': layer, 'ports': ports,
            'platform': 'brompton', 'lowLatency': ull,
            'portRects': [[x + i * step, 0, x + (i + 1) * step, height]
                          for i in range(ports)]}


def _owner_screens():
    """The owner's wall: three screens of 20 x 4 cabinets at 192 x 384
    (3840 x 1536 each), 8256 x 1536 with their offsets."""
    return [_screen('S1', 0), _screen('S2', 2208), _screen('S3', 4416)]


def _fill(client, layer, card, screens):
    return client.post('/api/port-assignments/place-overflow', json={
        'layerId': layer, 'cardId': card, 'screens': screens})


def _pins(client):
    return (client.get('/api/project').get_json()
            .get('port_assignments') or {}).get('pins') or []


def _resolution(client, screens):
    return _ok(client.post('/api/port-assignments/resolve',
                           json={'screens': screens}))['resolution']


def test_the_owners_three_screens_each_on_its_own_sx40_fit(client):
    screens = _owner_screens()
    for layer in ('S1', 'S2', 'S3'):
        _pid, card = _sx40(client, layer)
        _ok(_fill(client, layer, card, screens))
    assert len(_pins(client)) == 36
    spans = _resolution(client, screens)['canvas']
    assert sorted((s['title'], s['width'], s['height'], s['fits'])
                  for s in spans.values()) == [
        ('Tessera SX40 S1', 3840, 1536, True),
        ('Tessera SX40 S2', 3840, 1536, True),
        ('Tessera SX40 S3', 3840, 1536, True)]


def test_one_sx40_on_screen_1_and_screen_2_is_refused(client):
    """Screen 1 on SX40 S1, then screen 2's ports onto the same unit: the
    span would run 0-6048 - refused, said, and nothing written. One socket
    at a time too: screen 2's last port is past the canvas on its own."""
    screens = _owner_screens()
    _pid, card = _sx40(client, 'S1')
    _ok(_fill(client, 'S1', card, screens))
    why = _refused(_fill(client, 'S2', card, screens))
    assert why == ("Tessera SX40 S1 can't take this: its screens would span "
                   "6048 × 1536 px. " + SX_LIMIT)
    assert len(_pins(client)) == 12
    why = _refused(client.post('/api/port-assignments/place', json={
        'layerId': 'S2', 'index': 11, 'cardId': card, 'port': 13,
        'screens': screens}))
    assert '6048 × 1536 px' in why
    # its first port lies inside screen 1's width and lands
    _ok(client.post('/api/port-assignments/place', json={
        'layerId': 'S2', 'index': 0, 'cardId': card, 'port': 13,
        'screens': screens}))
    assert len(_pins(client)) == 13


def test_a_move_block_past_the_canvas_is_refused(client):
    screens = [_screen('A', 0, ports=10), _screen('B', 3000, ports=10,
                                                  width=1920)]
    _pid, card = _sx40(client, '')
    _ok(_fill(client, 'A', card, screens))
    why = _refused(client.post('/api/port-assignments/move-block', json={
        'layerId': 'B', 'cardId': card, 'screens': screens}))
    assert why.startswith("Tessera SX40 can't take this: its screens would "
                          "span 4920 × 1536 px.")
    assert len(_pins(client)) == 10


def test_a_resize_or_move_of_a_mapped_screen_is_refused(client):
    """The edit check (/link-check, the Processing guard's route, and the
    same canvas_refusal the client's edit guard twins): the screens as
    they are, and as they would be. A move or a resize past the canvas is
    refused; one inside it is not, and a check writes nothing."""
    now = [_screen('A', 0, ports=10, width=1920),
           _screen('B', 2000, ports=10, width=1920)]
    _pid, card = _sx40(client, 'S1')
    _ok(_fill(client, 'A', card, now))
    _ok(_fill(client, 'B', card, now))
    check = lambda after: client.post(  # noqa: E731
        '/api/port-assignments/link-check',
        json={'before': now, 'screens': after})
    moved = [now[0], _screen('B', 2400, ports=10, width=1920)]
    why = _refused(check(moved))
    assert why == ("Tessera SX40 S1 can't take this: its screens would span "
                   "4320 × 1536 px. " + SX_LIMIT)
    wider = [now[0], _screen('B', 2000, ports=10, width=2304)]
    assert '4304 × 1536 px' in _refused(check(wider))
    taller = [now[0], _screen('B', 2000, ports=10, width=1920, height=2400)]
    assert '3920 × 2400 px' in _refused(check(taller))
    assert _ok(check([now[0], _screen('B', 2100, ports=10, width=1920)])) \
        == {'ok': True}
    # low latency on: 3920 x 2100 fits the custom canvas but not ULL's 2047
    tall = [_screen('A', 0, ports=10, width=1920, height=2100),
            _screen('B', 2000, ports=10, width=1920, height=2100)]
    resp = client.post('/api/port-assignments/link-check', json={
        'before': tall,
        'screens': [dict(s, lowLatency=True) for s in tall]})
    assert 'With low latency on' in _refused(resp)
    assert len(_pins(client)) == 20


def test_a_show_already_past_the_canvas_is_flagged_and_left_alone(client):
    """A file saved before the rule, one SX40 across two screens 4400 wide:
    it opens as it was, every pin kept, and the resolution flags the unit
    in the present tense. An edit that leaves it no worse goes through - a
    release, a port onto ANOTHER processor - and one that widens it is
    still refused."""
    a, b = (str(_ok(client.post('/api/layer/add', json={'name': n}))['id'])
            for n in ('A', 'B'))
    screens = [_screen(a, 0, ports=10, width=1920),
               _screen(b, 2480, ports=10, width=1920)]
    project = client.get('/api/project').get_json()
    project['processors'] = [{
        'id': 'procS', 'deviceId': SX, 'name': 'OLD', 'mode': None,
        'redundancy': False,
        'slots': [{'index': 0, 'card': {
            'id': 'cardS', 'deviceId': SX, 'name': '', 'mode': 'default',
            'fixed': True, 'cvts': [
                {'id': f'xd{i}', 'deviceId': 'brompton-xd', 'name': '',
                 'trunkIndex': i} for i in range(4)]}}]}]
    project['port_assignments'] = {
        'auto': False, 'autoRetired': True,
        'pins': [{'layerId': layer, 'index': i, 'cardId': 'cardS',
                  'port': (10 if layer == b else 0) + i + 1}
                 for layer in (a, b) for i in range(10)]}
    _ok(client.put('/api/project', json=project))
    before = _pins(client)
    res = _resolution(client, screens)
    flag = res['canvas']['procS']
    assert (flag['width'], flag['height'], flag['fits']) == (4400, 1536, False)
    assert flag['message'] == ("Tessera SX40 OLD can't take this: its "
                               "screens span 4400 × 1536 px. " + SX_LIMIT)
    assert _pins(client) == before, 'a read changed an over-limit show'
    # releasing a port leaves it no worse
    _ok(client.post('/api/port-assignments/unpin', json={
        'layerId': b, 'index': 0, 'screens': screens}))
    assert len(_pins(client)) == 19
    # put back where it was: the span is the same 4400, not worse
    _ok(client.post('/api/port-assignments/place', json={
        'layerId': b, 'index': 0, 'cardId': 'cardS', 'port': 11,
        'screens': screens}))
    # a screen further right would widen it: refused
    wide = screens + [_screen('C', 4800, ports=2, width=384)]
    assert '5184 × 1536 px' in _refused(_fill(client, 'C', 'cardS', wide))
    # another processor takes it as usual
    _pid, card = _sx40(client, 'NEW')
    _ok(_fill(client, 'C', card, wide))


def test_a_screen_with_no_rects_is_not_measured(client):
    """A screen sent without portRects - every caller before this rule, a
    project with no canvas in play - adds nothing to a span."""
    _pid, card = _sx40(client, '')
    screens = [{'layerId': 'A', 'name': 'A', 'ports': 10,
                'platform': 'brompton'}]
    _ok(_fill(client, 'A', card, screens))
    assert _resolution(client, screens)['canvas'] == {}


def test_an_sq200_is_held_to_65535(client):
    st = _ok(client.post('/api/processors',
                         json={'deviceId': 'brompton-sq200', 'name': 'SQ'}),
             201)
    pid = st['resolved'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                        json={'deviceId': 'brompton-card-qd-s'}))
    proc = next(p for p in st['resolved'] if p['id'] == pid)
    card = proc['slots'][0]['card']['id']
    _ok(client.post(f'/api/processors/{pid}/cards/{card}/cvts',
                    json={'deviceId': 'brompton-xd-s'}), 201)
    screens = [_screen('A', 0, ports=2, width=30000, height=100),
               _screen('B', 60000, ports=2, width=6000, height=100)]
    _ok(_fill(client, 'A', card, screens))
    assert _refused(_fill(client, 'B', card, screens)) == (
        "Tessera SQ200 SQ can't take this: its screens would span 66000 × "
        "100 px. An SQ200's canvas is up to 65,535 px wide or tall.")


# ── C. the app: the edit guard, the tray and the binder ──────────────────

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const add = async (name, columns, x, rows = 4) => {
        const l = await j('POST', '/api/layer/add', {name, columns, rows,
            cabinet_width: 192, cabinet_height: 384, offset_x: x, offset_y: 0});
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'brompton',
            bitDepth: 8, frameRate: 60, flowPattern: 'tl-v'});
        return l;
    };
    const a = await add('A', 10, 0);
    const b = await add('B', 10, 2000, 6);
    // B's bottom two rows hidden: 1920 x 1536 of B is visible
    const bl = await j('GET', '/api/project').then(p => p.layers.find(l => l.id === b.id));
    await j('POST', `/api/layer/${b.id}/panels/set_hidden`, {panels: bl.panels
        .filter(p => p.row >= 4).map(p => ({id: p.id, hidden: true}))});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('canvas_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._processorRequest('/api/processors', 'POST',
                                {deviceId: 'brompton-sx40', name: 'S1'}, 'Add Processor');
    const sx = app._processorsResolved[0];
    const card = sx.slots[0].card.id;
    for (const l of [a, b]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(l.id), cardId: card}, null, 'Fill Ports In Order');
    }
    app.renderLayers();
    app.renderHardwareDock();
    app.updateUI();
    app.resetHistory('Canvas Seed');
    return {sx: sx.id, card, a: a.id, b: b.id};
}"""

SPAN_JS = """(sx) => {
    const c = (window.app._assignment || {}).canvas || {};
    return c[sx] || null;
}"""

LAYER_JS = """(id) => {
    const l = window.app.project.layers.find(x => x.id === id);
    return {columns: l.columns, offset_x: l.offset_x,
            hidden: l.panels.filter(p => p.hidden).length,
            index: window.app.historyIndex,
            status: document.getElementById('status-message').textContent};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function('() => window.app && window.app.project', timeout=20000)
    pg.wait_for_timeout(1000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(300)
    ids = pg.evaluate(SEED_JS)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _server_layer(pg, layer_id):
    return pg.evaluate("""(id) => fetch('/api/project').then(r => r.json())
        .then(p => p.layers.find(l => l.id === id))""", layer_id)


def test_the_js_and_python_canvas_fits_agree(page):
    pg, _ids = page
    cases = [(catalog.canvas_spec(catalog.get_device(d)), w, h, u)
             for d, w, h, u, _fits in FIT_TABLE]
    cases += [(catalog.canvas_spec(catalog.get_device(SX)), 4352, 2160, False),
              (catalog.canvas_spec(catalog.get_device('brompton-t1')), 1, 3000,
               False)]
    js = pg.evaluate("""(cases) => cases.map(([spec, w, h, u]) => [
        window.app.canvasFit(spec, w, h, u, 'Unit', false),
        window.app.canvasFit(spec, w, h, u, 'Unit', true)])""", cases)
    py = [[catalog.canvas_fit({'canvas': spec}, w, h, u, title='Unit'),
           catalog.canvas_fit({'canvas': spec}, w, h, u, title='Unit',
                              present=True)]
          for spec, w, h, u in cases]
    assert js == py


def test_the_client_sends_each_ports_rect_and_the_span_fits(page):
    """A on 0-1920 and B's visible 1920 from 2000: S1 spans 3920 x 1536,
    measured off the port rects the client sends."""
    pg, ids = page
    span = settled(pg, lambda: pg.evaluate(SPAN_JS, ids['sx']),
                   lambda s: bool(s))
    assert span and (span['width'], span['height'], span['fits']) == \
        (3920, 1536, True), span
    pins = pg.evaluate('() => window.app.project.port_assignments.pins.length')
    assert pins > 0
    assert pg.locator(f'[data-lrd-field="processor-canvas-{ids["sx"]}"]').count() == 0
    assert ids['errors'] == []


def test_a_cabinet_size_edit_past_the_canvas_is_refused_in_screen_info(page):
    """A's cabinets to 600 px tall make the wall 2400 tall - past 4096 x
    2160 and, 3920 wide, past 9,000,000 px: refused - A keeps 384, the
    status line says why, no undo step, nothing reaches the server."""
    pg, ids = page
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                ids['a'])
    pg.wait_for_timeout(200)
    before = pg.evaluate(LAYER_JS, ids['a'])
    pg.evaluate("""() => {
        const el = document.getElementById('cabinet-height');
        el.value = '600';
        el.dispatchEvent(new Event('change'));
    }""")
    out = pg.evaluate(LAYER_JS, ids['a'])
    assert out['index'] == before['index'], out
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).cabinet_height",
                       ids['a']) == 384
    assert out['status'] == ("Tessera SX40 S1 can't take this: its screens "
                             "would span 3920 × 2400 px. " + SX_LIMIT), out
    assert pg.evaluate("() => document.getElementById('cabinet-height').value") == '384'
    pg.wait_for_timeout(400)
    assert _server_layer(pg, ids['a'])['cabinet_height'] == 384
    assert ids['errors'] == []


def test_a_typed_offset_past_the_canvas_is_refused_and_one_inside_lands(page):
    pg, ids = page
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                ids['b'])
    pg.wait_for_timeout(200)
    before = pg.evaluate(LAYER_JS, ids['b'])
    typed = """(v) => {
        const el = document.getElementById('offset-x');
        el.value = String(v);
        el.dispatchEvent(new Event('change'));
    }"""
    pg.evaluate(typed, 2200)
    out = pg.evaluate(LAYER_JS, ids['b'])
    assert out['offset_x'] == 2000 and out['index'] == before['index'], out
    assert '4120 × 1536 px' in out['status'], out
    pg.evaluate(typed, 2100)
    out = settled(pg, lambda: pg.evaluate(LAYER_JS, ids['b']),
                  lambda o: o['offset_x'] == 2100)
    assert out['offset_x'] == 2100 and out['index'] == before['index'] + 1, out
    span = settled(pg, lambda: pg.evaluate(SPAN_JS, ids['sx']),
                   lambda s: s and s['width'] == 4020)
    assert span['width'] == 4020 and span['fits'], span
    pg.evaluate('() => window.app.undo()')
    out = settled(pg, lambda: pg.evaluate(LAYER_JS, ids['b']),
                  lambda o: o['offset_x'] == 2000)
    assert out['offset_x'] == 2000
    assert ids['errors'] == []


def test_a_pixel_map_drag_past_the_canvas_snaps_back(page):
    """The drag's end, in its own order (canvas-input: the PUT, then the
    snapshot): B dragged 400 px right is put back, panels and all, and the
    drag records no step."""
    pg, ids = page
    out = pg.evaluate("""(id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        const x0 = layer.panels[0].x;
        const index = app.historyIndex;
        layer.offset_x += 400;
        layer.showOffsetX = layer.offset_x;
        layer.panels.forEach(p => { p.x += 400; });
        app.updateLayers([layer], false);
        app.saveState('Move Layers');
        const now = app.project.layers.find(l => l.id === id);
        return {offset: now.offset_x, x: now.panels[0].x, x0,
                same: app.historyIndex === index};
    }""", ids['b'])
    assert out['offset'] == 2000 and out['x'] == out['x0'] and out['same'], out
    assert ids['errors'] == []


def test_showing_hidden_cabinets_past_the_canvas_is_refused(page):
    """B's two hidden bottom rows ride its column ports: shown, S1 would
    span 3920 x 2304 - 9,031,680 px. Refused, the cabinets stay hidden here
    and on the server; one cabinet by its own toggle the same."""
    pg, ids = page
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                ids['b'])
    before = pg.evaluate(LAYER_JS, ids['b'])
    assert before['hidden'] == 20, before
    pg.evaluate("""async (id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        await app.setPanelsBlankBulk(layer.panels.filter(p => p.row >= 4), false);
    }""", ids['b'])
    out = pg.evaluate(LAYER_JS, ids['b'])
    assert out['hidden'] == 20, out
    assert '3920 × 2304 px' in out['status'], out
    assert out['index'] == before['index']
    pg.wait_for_timeout(300)
    assert len([p for p in _server_layer(pg, ids['b'])['panels'] if p['hidden']]) == 20
    pid = pg.evaluate("""(id) => window.app.project.layers.find(l => l.id === id)
        .panels.find(p => p.col === 0 && p.row === 5).id""", ids['b'])
    pg.evaluate("() => { document.getElementById('status-message').textContent = 'Ready'; }")
    pg.evaluate("([l, p]) => window.app.togglePanelHidden(l, p)", [ids['b'], pid])
    pg.wait_for_timeout(300)
    out = pg.evaluate(LAYER_JS, ids['b'])
    assert out['hidden'] == 20 and '3920 × 2304 px' in out['status'], out
    assert len([p for p in _server_layer(pg, ids['b'])['panels'] if p['hidden']]) == 20
    # showing one row stays inside the canvas (3920 x 1920) and lands
    pg.evaluate("""async (id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        await app.setPanelsBlankBulk(layer.panels.filter(p => p.row === 4), false);
    }""", ids['b'])
    out = settled(pg, lambda: pg.evaluate(LAYER_JS, ids['b']),
                  lambda o: o['hidden'] == 10)
    assert out['hidden'] == 10 and out['index'] == before['index'] + 1, out
    pg.evaluate('() => window.app.undo()')
    out = settled(pg, lambda: pg.evaluate(LAYER_JS, ids['b']),
                  lambda o: o['hidden'] == 20)
    assert out['hidden'] == 20, out
    assert ids['errors'] == []


def test_a_mapping_past_the_canvas_is_refused_in_the_tray(page):
    """A third screen to the right of B, filled onto S1 from the client:
    the server refuses, the status line says so, no pin lands."""
    pg, ids = page
    out = pg.evaluate("""async (card) => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, {method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)}).then(r => r.json());
        const c = await j('POST', '/api/layer/add', {name: 'C', columns: 2, rows: 4,
            cabinet_width: 192, cabinet_height: 384, offset_x: 4000, offset_y: 0});
        c.processorType = 'brompton';
        app.project.layers.push(c);
        app.updateLayers([c], false);
        await app._layerSavesSettled();
        const pins = app.project.port_assignments.pins.length;
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(c.id), cardId: card}, null, 'Fill Ports In Order');
        return {pins, after: app.project.port_assignments.pins.length,
                status: document.getElementById('status-message').textContent};
    }""", ids['card'])
    assert out['after'] == out['pins'], out
    assert out['status'].startswith("Tessera SX40 S1 can't take this: its "
                                    "screens would span 4384 × 1536 px."), out
    assert ids['errors'] == []


def test_an_over_limit_show_is_flagged_in_the_tray_and_the_binder(page):
    """The show is put past the canvas behind the app's back (a file from
    before the rule): nothing is changed, the processor's strip carries the
    sentence in red, its binder page a Canvas line - and an edit that
    leaves it no worse still goes through."""
    pg, ids = page
    pg.evaluate("""async (id) => {
        const app = window.app;
        const proj = await fetch('/api/project').then(r => r.json());
        const b = proj.layers.find(l => l.id === id);
        b.offset_x = 2600;
        b.showOffsetX = 2600;
        b.panels.forEach(p => { p.x += 600; });
        await fetch('/api/project', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(proj)});
        app.project = await fetch('/api/project').then(r => r.json());
        app.dedupeProjectLayers('canvas_over');
        app.selectLayer(app.project.layers[0]);
        app.updateUI();
        app.renderHardwareDock();
    }""", ids['b'])
    span = settled(pg, lambda: pg.evaluate(SPAN_JS, ids['sx']),
                   lambda s: s and not s['fits'])
    message = ("Tessera SX40 S1 can't take this: its screens span 4520 × "
               "1536 px. " + SX_LIMIT)
    assert span and span['message'] == message, span
    flag = pg.locator(f'[data-lrd-field="processor-canvas-{ids["sx"]}"]')
    settled(pg, flag.count, lambda n: n == 1)
    assert flag.text_content() == message
    assert pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).offset_x""", ids['b']) == 2600
    pairs = pg.evaluate("""(sx) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === sx);
        const keep = [app._bTableLines, app._bKvLines];
        const seen = [];
        app._bTableLines = () => [];
        app._bKvLines = (book, title, pairs) => { seen.push({title, pairs}); return []; };
        try {
            app._bProcessorGroup({list: {hardware: []}}, proc);
        } finally {
            [app._bTableLines, app._bKvLines] = keep;
        }
        return (seen.find(b => b.title === 'Redundancy') || {}).pairs;
    }""", ids['sx'])
    assert ['Canvas', message] in pairs, pairs
    # no worse: A moves right inside the span it already has
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                ids['a'])
    pg.evaluate("""() => {
        const el = document.getElementById('offset-x');
        el.value = '100';
        el.dispatchEvent(new Event('change'));
    }""")
    out = settled(pg, lambda: pg.evaluate(LAYER_JS, ids['a']),
                  lambda o: o['offset_x'] == 100)
    assert out['offset_x'] == 100, out
    assert ids['errors'] == []


OWNER_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    const ids = [];
    for (const [i, x] of [0, 2208, 4416].entries()) {
        const l = await j('POST', '/api/layer/add', {name: `S${i + 1}`, columns: 20,
            rows: 4, cabinet_width: 192, cabinet_height: 384, offset_x: x, offset_y: 0});
        // a column a port (a 20-wide row is more than one port carries)
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'brompton', bitDepth: 8,
                                              frameRate: 60, flowPattern: 'tl-v'});
        ids.push(l.id);
    }
    const p = await j('GET', '/api/project');
    p.groups = [{id: 'grp-wall', name: 'Wall', layer_ids: ids, routeDataAsOne: false}];
    p.layers.forEach(l => { l.group_id = 'grp-wall'; });
    await j('PUT', '/api/project', p);
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('canvas_owner');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    const cards = [];
    for (const name of ['S1', 'S2', 'S3']) {
        await app._processorRequest('/api/processors', 'POST',
                                    {deviceId: 'brompton-sx40', name}, 'Add Processor');
        cards.push(app._processorsResolved[app._processorsResolved.length - 1].slots[0].card.id);
    }
    const fill = (layer, card) => app._assignmentRequest(
        '/api/port-assignments/place-overflow', 'POST',
        {layerId: String(layer), cardId: card}, null, 'Fill Ports In Order');
    for (const i of [0, 1, 2]) await fill(ids[i], cards[i]);
    app.updateUI();
    const placed = app.project.port_assignments.pins.length;
    const spans = Object.values(app._assignment.canvas || {})
        .map(s => [s.title, s.width, s.height, s.fits]);
    // S1 onto screen 2 as well: S2 lets go of it first
    await app._assignmentRequest('/api/port-assignments/unpin', 'POST',
        {layerId: String(ids[1])}, null, 'Release Ports');
    const released = app.project.port_assignments.pins.length;
    await fill(ids[1], cards[0]);
    return {group: (app.project.groups || []).length, placed, spans, released,
            after: app.project.port_assignments.pins.length,
            status: document.getElementById('status-message').textContent};
}"""


def test_the_owners_grouped_wall_fits_one_sx40_a_screen(page):
    """The owner's example in the app: a group of three screens 20 x 4 at
    192 x 384 (3840 x 1536 each), 8256 x 1536 with their offsets, each on
    its own SX40 - every unit fits. SX40 S1 taking screen 2 as well would
    span 6048 - refused, and screen 2 stays off it."""
    pg, ids = page
    out = pg.evaluate(OWNER_JS)
    assert out['group'] == 1, out
    assert out['placed'] == 60, out
    assert sorted(out['spans']) == [['Tessera SX40 S1', 3840, 1536, True],
                                    ['Tessera SX40 S2', 3840, 1536, True],
                                    ['Tessera SX40 S3', 3840, 1536, True]], out
    assert out['after'] == out['released'] < out['placed'], out
    assert out['status'].startswith("Tessera SX40 S1 can't take this: its "
                                    "screens would span 6048 × 1536 px."), out
    assert ids['errors'] == []
