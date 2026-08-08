"""v0.10.9 - appearance settings vanished when the page was reloaded.

Reported on macOS against 0.10.9: "things reverting when I reloaded the page".
The app log (14:20-14:21) shows it exactly. Layer 2 "UPSTAGE" had its gradient
stops walked from 0.25/0.4/0.6/0.8/1 down to 0/0.25/0.5/0.75/1 over ~11
seconds. At 14:21:02 the page reloaded. At 14:21:52 the same layer came back
holding 0.25/0.4/0.6/0.8/1 - the values from BEFORE the edits.

The cause was a hole in one allow-list. PUT /api/layer/<id> copies a fixed set
of keys out of the request; every gradient field, panelColors/panelColorMode,
transparentFill and the Pixel Map / Show Look screen-name offsets were absent
from it - never removed, never added (git log -S finds no commit that took
them out). The client PUT them on every edit and the route dropped them, then
echoed the layer back without them; the client re-stamped its own copy over
the echo, so the screen stayed right and the divergence stayed invisible.

Nothing reconciled it. POST/PUT /api/project store the whole layer dict, so a
full save or an undo healed it by accident - which is why this looked
intermittent. GET /api/project on reload served the stale copy, and
loadClientSideProperties only patches over that from localStorage for the
untouched single-layer "Untitled Project" (shouldUseSavedClientProps), which no
real drawing is. Hence `skip_saved_client_props` in the log and the lost work.

The last test here is the one that would have caught it: every field the client
treats as client-side-only has to be storable by the route, or it dies on
reload.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'

# The gradient the log shows being edited, before and after.
STOPS_BEFORE = [
    {'pos': 0.25, 'color': '#ff9900'}, {'pos': 0.4, 'color': '#ffee00'},
    {'pos': 0.6, 'color': '#00cc66'}, {'pos': 0.8, 'color': '#0099ff'},
    {'pos': 1, 'color': '#cc33ff'},
]
STOPS_AFTER = [
    {'pos': 0, 'color': '#ff9900'}, {'pos': 0.25, 'color': '#ffee00'},
    {'pos': 0.5, 'color': '#00cc66'}, {'pos': 0.75, 'color': '#0099ff'},
    {'pos': 1, 'color': '#cc33ff'},
]


def _layer_id(client):
    return client.get('/api/project').get_json()['layers'][0]['id']


# ── The reported bug ──────────────────────────────────────────────────────

def test_gradient_edits_survive_a_page_reload(client_with_layer):
    """The log, replayed. Edit the stops through the route the editor uses,
    then re-read the project the way a page reload does."""
    layer_id = _layer_id(client_with_layer)

    client_with_layer.put(f'/api/layer/{layer_id}', json={
        'gradientEnabled': True, 'gradientStops': STOPS_BEFORE})
    client_with_layer.put(f'/api/layer/{layer_id}', json={
        'gradientStops': STOPS_AFTER})

    # A page reload is exactly this GET - no localStorage, because
    # shouldUseSavedClientProps() refuses it for any named project.
    reloaded = client_with_layer.get('/api/project').get_json()['layers'][0]

    assert reloaded['gradientStops'] == STOPS_AFTER, (
        'gradient stops reverted across a reload: got '
        f'{reloaded["gradientStops"]}')


def test_gradient_edit_is_stored_not_just_echoed(client_with_layer):
    """The echo told the truth about the request and nothing about the store,
    which is why this stayed hidden. Assert the STORE."""
    layer_id = _layer_id(client_with_layer)
    client_with_layer.put(f'/api/layer/{layer_id}', json={
        'gradientStops': STOPS_AFTER})

    stored = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert stored.get('gradientStops') == STOPS_AFTER


@pytest.mark.parametrize('field,value', [
    ('gradientEnabled', True),
    ('gradientType', 'radial'),
    ('gradientScope', 'panel'),
    ('gradientPanelAlternate', True),
    ('gradientRadialCenterX', 0.25),
    ('gradientRadialCenterY', 0.75),
    ('gradientRadialRadius', 1.5),
    ('gradientAngle', 90),
    ('gradientOpacity', 1),
    ('gradientBlend', 'color'),
    ('panelColorMode', 'checker'),
    ('panelColors', ['#ff0000', '#00ff00']),
    ('transparentFill', True),
    # The only two views whose screen-name offset was missing, so a dragged
    # screen name reverted on reload here and nowhere else.
    ('screenNameOffsetXPixelMap', 42),
    ('screenNameOffsetYPixelMap', -17),
    ('screenNameOffsetXShowLook', 8),
    ('screenNameOffsetYShowLook', 96),
])
def test_appearance_field_round_trips(client_with_layer, field, value):
    layer_id = _layer_id(client_with_layer)
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={field: value})
    assert resp.status_code == 200
    assert resp.get_json()[field] == value, f'{field} missing from the echo'

    stored = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert stored.get(field) == value, (
        f'{field} was accepted and echoed but not stored - it will revert on '
        'the next page reload')


def test_gradient_survives_a_later_unrelated_edit(client_with_layer):
    """A PUT that says nothing about the gradient must not clear it. The route
    only copies keys present in the request, so this guards the shape of the
    fix as much as the fix."""
    layer_id = _layer_id(client_with_layer)
    client_with_layer.put(f'/api/layer/{layer_id}',
                          json={'gradientStops': STOPS_AFTER})
    client_with_layer.put(f'/api/layer/{layer_id}', json={'name': 'Renamed'})

    stored = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert stored['name'] == 'Renamed'
    assert stored['gradientStops'] == STOPS_AFTER


# ── The guard that would have caught it ───────────────────────────────────

def _put_allow_list():
    body = (SRC / 'routes_layers.py').read_text()
    block = body.split('def update_layer(layer_id):')[1].split(']:')[0]
    return set(re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", block))


def _client_side_props():
    lines = (SRC / 'static' / 'js' / 'app-core.js').read_text().splitlines()
    start = next(i for i, l in enumerate(lines)
                 if 'extractClientSideProps(layer) {' in l)
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == '    }')
    return {m.group(1) for l in lines[start:end]
            if (m := re.match(r'\s+([A-Za-z_][A-Za-z0-9_]*):', l))}


def test_allow_list_and_client_side_props_have_not_drifted():
    """extractClientSideProps names the fields the client re-applies on top of
    every server payload. That list masks whatever the server fails to store,
    so a field can sit in it for months looking fine and still be lost the
    moment the page reloads - which is precisely what happened to the whole
    gradient block.

    The invariant: anything the client carries per layer must be storable by
    the route that saves layers. Adding a field to extractClientSideProps
    without adding it to the PUT allow-list fails here instead of silently
    costing someone their work.
    """
    missing = sorted(_client_side_props() - _put_allow_list())
    assert not missing, (
        'these per-layer fields are re-applied client-side but PUT '
        '/api/layer/<id> will not store them, so they revert on reload:\n  '
        + '\n  '.join(missing))


# ── The same hole, on the route that CREATES a layer ──────────────────────
# Found while auditing the fix above: duplicate/paste posts the source
# screen's whole appearance to /api/layer/add, and that route has its own
# allow-list (optional_fields) with the identical gap. The copy carried a
# gradient in the browser and none on the server, so it survived until the
# next reload - the reported symptom, reached by a different door.

APPEARANCE_FIELDS = {
    'gradientEnabled': True,
    'gradientType': 'radial',
    'gradientScope': 'panel',
    'gradientPanelAlternate': True,
    'gradientRadialCenterX': 0.25,
    'gradientRadialCenterY': 0.75,
    'gradientRadialRadius': 1.5,
    'gradientAngle': 90,
    'gradientOpacity': 1,
    'gradientBlend': 'color',
    'gradientStops': STOPS_AFTER,
    'panelColorMode': 'checker',
    'panelColors': ['#ff0000', '#00ff00'],
    'transparentFill': True,
    'screenNameOffsetXPixelMap': 42,
    'screenNameOffsetYPixelMap': -17,
    'screenNameOffsetXShowLook': 8,
    'screenNameOffsetYShowLook': 96,
}


def test_duplicated_screen_keeps_its_gradient(client):
    """POST /api/layer/add is the duplicate/paste route. What it does not
    store is gone the moment the page reloads."""
    payload = {'name': 'Copy', 'columns': 2, 'rows': 2}
    payload.update(APPEARANCE_FIELDS)
    created = client.post('/api/layer/add', json=payload).get_json()

    for field, value in APPEARANCE_FIELDS.items():
        assert created.get(field) == value, f'{field} dropped on create'

    reloaded = client.get('/api/project').get_json()['layers'][-1]
    for field, value in APPEARANCE_FIELDS.items():
        assert reloaded.get(field) == value, (
            f'{field} was not stored on the duplicated layer - the copy loses '
            'it on the next page reload')


def test_duplicate_route_does_not_disturb_panel_geometry(client):
    """None of the appearance fields feed panel construction. Guard that,
    since they now flow through the same loop that triggers a rebuild for
    half-tile fields."""
    plain = client.post('/api/layer/add', json={
        'name': 'Plain', 'columns': 3, 'rows': 2,
        'cabinet_width': 128, 'cabinet_height': 128}).get_json()

    payload = {'name': 'Fancy', 'columns': 3, 'rows': 2,
               'cabinet_width': 128, 'cabinet_height': 128}
    payload.update(APPEARANCE_FIELDS)
    fancy = client.post('/api/layer/add', json=payload).get_json()

    def geom(layer):
        return [(p['row'], p['col'], p['x'], p['y'], p['width'], p['height'])
                for p in layer['panels']]

    assert geom(plain) == geom(fancy), (
        'appearance fields changed the panel grid on create')


def test_create_route_allow_list_covers_the_appearance_fields():
    body = (SRC / 'routes_layers.py').read_text()
    block = body.split('optional_fields = [')[1].split(']')[0]
    optional = set(re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", block))
    missing = sorted(set(APPEARANCE_FIELDS) - optional)
    assert not missing, (
        'POST /api/layer/add will not store these, so a duplicated or pasted '
        'screen loses them on reload:\n  ' + '\n  '.join(missing))


def test_allow_list_covers_the_fields_this_bug_lost():
    """Named explicitly, so deleting the parametrised test above cannot
    quietly retire the coverage."""
    allowed = _put_allow_list()
    for field in ('gradientEnabled', 'gradientType', 'gradientScope',
                  'gradientPanelAlternate', 'gradientRadialCenterX',
                  'gradientRadialCenterY', 'gradientRadialRadius',
                  'gradientAngle', 'gradientOpacity', 'gradientBlend',
                  'gradientStops', 'panelColorMode', 'panelColors',
                  'transparentFill', 'screenNameOffsetXPixelMap',
                  'screenNameOffsetYPixelMap', 'screenNameOffsetXShowLook',
                  'screenNameOffsetYShowLook'):
        assert field in allowed, f'{field} dropped back out of the allow-list'
