"""A COPY of a screen never carries its feeds (owner ruling, 2026-09-23).

"They can't carry over because then they would be duplicates on the same
multi or processor." A copy starts with no distro outputs on its circuits
and no processor card ports; it is fed by a fresh drop. Everything that
describes the screen itself carries: voltage, breakout, colours, borders,
hand-drawn runs, processing settings, where its multis split.

Found by an end-to-end pass: Duplicate Canvas carried powerSocaDistro onto
the copied screens, so two screens claimed one multi on one distro. The
three copy paths now read one rule - app.strip_copied_feeds on the server's
own clones (duplicate canvas, duplicate to canvas), SCREEN_FEED_KEYS in
app-clipboard.js for Duplicate (Cmd+J), Paste (Cmd+C / Cmd+V) and
Duplicate Group - and every one is checked here against the SERVER's copy,
because that is what a reload reads.

Run locally:
    python3 -m pytest tests/test_copies_never_carry_feeds.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import app as app_module  # noqa: E402
import port_assignment as assignment  # noqa: E402

CARD = 'novastar-card-h-16xrj45-2xfiber'

# The run from a distro to the screen: which box, which slot, which legs
# and breaker position, what the multi is called, how long its home run is.
FEEDS = {
    'powerSocaDistro': {'1': 'd1'},
    'powerSocaNumber': {'1': 3},
    'powerSocaPhasePos': {'1': [1, 2, 3]},
    'powerSocaPhaseOffset': {'1': 1},
    'powerSocaNames': {'1': 'SL1'},
    'powerSocaLengths': {'1': '100ft'},
}
assert tuple(FEEDS) == app_module.COPIED_SCREEN_FEED_KEYS

# The screen itself. Values that are not the defaults.
CARRIED = {
    'powerVoltage': 208,
    'powerBreakoutType': 'soca-powercon',
    'color1': '#123456',
    'border_color_power': '#5E6F7A',
    'powerCircuitColors': {'1': '#ABCDEF', '2': '#FEDCBA'},
    'powerCustomPath': True,
    'powerCustomPaths': {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]},
    'customPortPaths': {'1': [{'row': 1, 'col': 0}, {'row': 1, 'col': 1}]},
    'powerSocaSplits': [2],
    'powerSocaKeying': 'index',
    'powerSplitters': {'enabled': True, 'maxWays': 2,
                       'manual': {'merge': [], 'split': []}},
    'processorType': 'novastar-coex-1g',
}


def feeds_of(layer):
    """The feed keys a layer still carries. An empty store is no feed: the
    browser's default pass stamps powerSocaNames = {} on every screen."""
    return {k: layer.get(k) for k in FEEDS if layer.get(k)}


def carried_of(layer):
    return {k: layer.get(k) for k in CARRIED}


def is_screen(layer):
    return (layer.get('type') or 'screen') == 'screen'


# ── Flask: the server's own clones ────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


def one_card(client):
    """One H9 with a 16-port card in slot 1; returns the card id."""
    resp = client.post('/api/processors', json={'deviceId': 'novastar-h9'})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    pid = resp.get_json()['resolved'][0]['id']
    resp = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': CARD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolved'][0]['slots'][0]['card']['id']


def screens(project, ports=2):
    return [{'layerId': str(l['id']), 'name': l['name'], 'ports': ports}
            for l in project['layers'] if is_screen(l)]


def pins(client):
    state = client.get('/api/project').get_json().get(assignment.STATE_KEY) or {}
    return state.get('pins') or []


def dress(client, layer_id):
    """Feed the screen (distro, number, legs, name, length), dress it, and
    land two of its ports on a card."""
    resp = client.put(f'/api/layer/{layer_id}', json=dict(FEEDS, **CARRIED))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = one_card(client)
    project = client.get('/api/project').get_json()
    resp = client.post('/api/port-assignments/place-overflow', json={
        'layerId': str(layer_id), 'cardId': card, 'screens': screens(project)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    src = next(l for l in client.get('/api/project').get_json()['layers']
               if l['id'] == layer_id)
    assert feeds_of(src) == FEEDS, 'the seed did not take'
    assert carried_of(src) == CARRIED, 'the seed did not take'
    assert {p['layerId'] for p in pins(client)} == {str(layer_id)}
    return src


def assert_copy_is_unfed(copy, original, client, how):
    assert feeds_of(copy) == {}, (
        f'{how}: the copy claims the original\'s feeds: {feeds_of(copy)}')
    assert carried_of(copy) == CARRIED, f'{how}: the copy lost its own settings'
    assert all(p['layerId'] != str(copy['id']) for p in pins(client)), (
        f'{how}: the copy has card ports pinned')
    # The original is untouched: its feeds, its settings and its pins.
    assert feeds_of(original) == FEEDS, f'{how}: the original lost its feeds'
    assert carried_of(original) == CARRIED
    assert {p['layerId'] for p in pins(client)} == {str(original['id'])}


def test_duplicate_canvas_copies_the_screen_without_its_feeds(client_with_layer):
    client = client_with_layer
    src_id = client.get('/api/project').get_json()['layers'][0]['id']
    dress(client, src_id)

    resp = client.post('/api/canvas/c1/duplicate')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    project = client.get('/api/project').get_json()
    copies = [l for l in project['layers'] if l['canvas_id'] == 'c2']
    assert len(copies) == 1
    original = next(l for l in project['layers'] if l['id'] == src_id)
    assert_copy_is_unfed(copies[0], original, client, 'Duplicate Canvas')


def test_duplicate_to_another_canvas_copies_the_screen_without_its_feeds(client_with_layer):
    client = client_with_layer
    src_id = client.get('/api/project').get_json()['layers'][0]['id']
    dress(client, src_id)
    client.post('/api/canvas', json={})  # c2

    resp = client.put(f'/api/layer/{src_id}/canvas',
                      json={'canvas_id': 'c2', 'mode': 'duplicate'})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    project = client.get('/api/project').get_json()
    copies = [l for l in project['layers'] if l['id'] != src_id]
    assert len(copies) == 1 and copies[0]['canvas_id'] == 'c2'
    original = next(l for l in project['layers'] if l['id'] == src_id)
    assert_copy_is_unfed(copies[0], original, client, 'Duplicate to canvas')


def test_a_full_layer_post_still_stores_the_feeds(client):
    """The strip is the copy paths' own, not the add route's: a loader
    posting a whole screen (quickstart, a preset) must keep its feeds."""
    resp = client.post('/api/layer/add', json=dict(
        FEEDS, name='Fed', columns=4, rows=3, cabinet_width=128, cabinet_height=128))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    stored = next(l for l in client.get('/api/project').get_json()['layers']
                  if l['name'] == 'Fed')
    assert feeds_of(stored) == FEEDS
    # The helper itself: screens only, and it says what it took.
    layer = dict(FEEDS, id=1)
    assert app_module.strip_copied_feeds(dict(layer, type='image')) == []
    assert sorted(app_module.strip_copied_feeds(layer)) == sorted(FEEDS)
    assert feeds_of(layer) == {}


# ── Browser: Duplicate (Cmd+J) and Paste (Cmd+C, Cmd+V) ───────────────────

MOD = 'Meta' if sys.platform == 'darwin' else 'Control'


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """This module adds a processor, pins ports and makes copies on the
    live server; put the project back the way it was found."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# Feed and dress the first screen, push it, and land two of its ports on a
# card - the same seed the Flask half uses, made through the page. Once per
# module: every copy below is made from this one screen.
DRESS_JS = """async ([feeds, carried, card]) => {
    const app = window.app;
    const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
    app.currentLayer = l;
    Object.assign(l, JSON.parse(JSON.stringify(feeds)),
                     JSON.parse(JSON.stringify(carried)));
    app.updateLayers([l]);
    const j = async (method, url, body) => {
        const r = await fetch(url, {method, headers: {'Content-Type': 'application/json'},
                                    body: body === undefined ? undefined : JSON.stringify(body)});
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    };
    const procs = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = procs.resolved[procs.resolved.length - 1].id;
    const slot = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: card});
    const cardId = slot.resolved.find(p => p.id === pid).slots[0].card.id;
    const screens = app.project.layers
        .filter(x => (x.type || 'screen') === 'screen')
        .map(x => ({layerId: String(x.id), name: x.name, ports: 2}));
    const placed = await j('POST', '/api/port-assignments/place-overflow',
                           {layerId: String(l.id), cardId, screens});
    app.project.port_assignments = placed.state;
    return l.id;
}"""

FEED_KEYS_JS = "['powerSocaDistro','powerSocaNumber','powerSocaPhasePos'," \
               "'powerSocaPhaseOffset','powerSocaNames','powerSocaLengths']"

# The copy as the browser holds it, and as the server holds it.
PICK_JS = """
    const feedKeys = %s;
    const pick = (l, carriedKeys, pins) => {
        const feeds = {};
        feedKeys.forEach(k => { if (l[k] && (typeof l[k] !== 'object' || Object.keys(l[k]).length)) feeds[k] = l[k]; });
        const carried = {};
        carriedKeys.forEach(k => { carried[k] = l[k] === undefined ? null : l[k]; });
        return {id: l.id, feeds, carried,
                pinned: (pins || []).filter(p => String(p.layerId) === String(l.id)).length};
    };
""" % FEED_KEYS_JS

LIVE_JS = "async ([before, sourceId, carriedKeys]) => {" + PICK_JS + """
    const app = window.app;
    const fresh = app.project.layers.filter(l => !before.includes(l.id));
    if (fresh.length !== 1) return {error: `${fresh.length} new layers in the browser`};
    const pins = ((app.project.port_assignments || {}).pins) || [];
    return {copy: pick(fresh[0], carriedKeys, pins),
            original: pick(app.project.layers.find(l => l.id === sourceId), carriedKeys, pins)};
}"""

SERVER_JS = "async ([before, sourceId, carriedKeys]) => {" + PICK_JS + """
    const p = await (await fetch('/api/project')).json();
    const fresh = p.layers.filter(l => !before.includes(l.id));
    if (fresh.length !== 1) return {error: `${fresh.length} new layers on the server`};
    const pins = ((p.port_assignments || {}).pins) || [];
    return {copy: pick(fresh[0], carriedKeys, pins),
            original: pick(p.layers.find(l => l.id === sourceId), carriedKeys, pins)};
}"""


def _assert_unfed(result, how):
    assert 'error' not in result, f'{how}: {result["error"]}'
    copy, original = result['copy'], result['original']
    assert copy['feeds'] == {}, (
        f'{how}: the copy claims the original\'s feeds: {copy["feeds"]}')
    assert copy['carried'] == CARRIED, f'{how}: the copy lost its own settings'
    assert copy['pinned'] == 0, f'{how}: the copy has {copy["pinned"]} card ports pinned'
    assert original['feeds'] == FEEDS, f'{how}: the original lost its feeds'
    assert original['carried'] == CARRIED, f'{how}: the original lost its settings'
    assert original['pinned'] == 2, f'{how}: the original lost its pins'


@pytest.fixture(scope="module")
def source_id(page):
    """The one fed screen every copy in this module is made from."""
    sid = page.evaluate(DRESS_JS, [FEEDS, CARRIED, CARD])
    page.wait_for_timeout(800)
    return sid


def _select(page, layer_id):
    """Make the screen current, with the keys going to the document rather
    than a field so the shortcut handler reads them as canvas keys."""
    page.evaluate("""(id) => {
        window.app.currentLayer = window.app.project.layers.find(x => x.id === id);
        if (document.activeElement) document.activeElement.blur();
    }""", layer_id)
    return page.evaluate("() => window.app.project.layers.map(x => x.id)")


def _check_both(page, before, source_id, how):
    args = [before, source_id, list(CARRIED)]
    _assert_unfed(page.evaluate(LIVE_JS, args), f'{how} (browser)')
    _assert_unfed(page.evaluate(SERVER_JS, args), f'{how} (server)')


def test_cmd_j_duplicates_the_screen_without_its_feeds(page, source_id):
    before = _select(page, source_id)
    page.keyboard.press(f'{MOD}+j')
    page.wait_for_timeout(1500)
    _check_both(page, before, source_id, 'Duplicate')


def test_cmd_c_cmd_v_pastes_the_screen_without_its_feeds(page, source_id):
    before = _select(page, source_id)
    page.keyboard.press(f'{MOD}+c')
    page.wait_for_timeout(200)
    page.keyboard.press(f'{MOD}+v')
    page.wait_for_timeout(1500)
    _check_both(page, before, source_id, 'Paste')


def test_the_copies_stay_unfed_after_a_reload(page, source_id):
    """What a reload reads is the server's copy; nothing on the way back
    in (the browser's default pass, the keying migration) refeeds it."""
    before = page.evaluate("() => window.app.project.layers.map(x => x.id)")
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    result = page.evaluate("([ids, carriedKeys]) => {" + PICK_JS + """
        const app = window.app;
        const pins = ((app.project.port_assignments || {}).pins) || [];
        return app.project.layers
            .filter(l => ids.includes(l.id) && (l.type || 'screen') === 'screen')
            .map(l => pick(l, carriedKeys, pins));
    }""", [before, list(CARRIED)])
    by_id = {r['id']: r for r in result}
    assert by_id[source_id]['feeds'] == FEEDS, 'the original lost its feeds on reload'
    assert by_id[source_id]['pinned'] == 2, 'the original lost its pins on reload'
    copies = [r for r in result if r['id'] != source_id]
    assert len(copies) >= 2, 'the duplicate and the paste should both be here'
    for r in copies:
        assert r['feeds'] == {}, f'copy {r["id"]} is fed after a reload: {r["feeds"]}'
        assert r['pinned'] == 0, f'copy {r["id"]} has pins after a reload'
