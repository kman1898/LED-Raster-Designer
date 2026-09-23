"""Data port pins die with their layer (2026-09-23).

A pin names a layer by id and nothing else ties the two together. Until this
fix a screen deleted on its own, or taken with its canvas, left its pins in
project['port_assignments']: invisible in the panel (resolve only draws the
layers it is given), but returned by GET /api/project, mirrored by the
client, written by File > Save and read back by the next open - and still
counted as claims on their sockets. Found by an end-to-end pass: pin a
screen, duplicate its canvas, delete the original, and the dead screen's
pins were still in the file while the alive ids had all moved on.

The prune runs in app._enforce_group_integrity, the funnel every delete,
undo, redo and file load passes through, so every route here is covered by
the one change. Only pins on a dead layer go: a living screen's pins are
the user's decisions and stay exactly as stored.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import port_assignment as assignment  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


CARD = 'novastar-card-h-16xrj45-2xfiber'


def one_card(client):
    """One H9 with a 16-port card in slot 1; returns the card id."""
    resp = client.post('/api/processors', json={'deviceId': 'novastar-h9'})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    pid = resp.get_json()['resolved'][0]['id']
    resp = client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': CARD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['resolved'][0]['slots'][0]['card']['id']


def add_screen(client, name, canvas_id=None, cols=4, rows=3):
    body = {'name': name, 'columns': cols, 'rows': rows,
            'cabinet_width': 128, 'cabinet_height': 128}
    if canvas_id:
        body['canvas_id'] = canvas_id
    resp = client.post('/api/layer/add', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['id']


def add_canvas(client):
    resp = client.post('/api/canvas', json={})
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()['canvases'][-1]['id']


def screens(project, ports=2):
    """The client's picture of the project's screens, `ports` each."""
    return [{'layerId': str(l['id']), 'name': l['name'], 'ports': ports}
            for l in project['layers'] if (l.get('type') or 'screen') == 'screen']


def attach(client, layer_id, card_id):
    """Land one screen on the card - the request a card drop sends; every
    port it lands is a pin."""
    project = client.get('/api/project').get_json()
    resp = client.post('/api/port-assignments/place-overflow', json={
        'layerId': str(layer_id), 'cardId': card_id,
        'screens': screens(project)})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def pins(client):
    state = client.get('/api/project').get_json().get(assignment.STATE_KEY) or {}
    return state.get('pins') or []


def pinned_layers(client):
    return sorted({p['layerId'] for p in pins(client)})


def alive_ids(client):
    return {str(l['id']) for l in client.get('/api/project').get_json()['layers']}


def assert_no_dead_pins(client):
    alive = alive_ids(client)
    dead = [p for p in pins(client) if p['layerId'] not in alive]
    assert dead == [], f'pins on layers that no longer exist: {dead}'


# ── Deleting a canvas ─────────────────────────────────────────────────────

def test_the_repro_duplicate_the_canvas_then_delete_the_original(client):
    """The end-to-end pass, step for step: two pins on the only screen, the
    canvas duplicated (the copy's screen has a new id and no pins), the
    original deleted. Nothing may point at the deleted screen."""
    card = one_card(client)
    original = add_screen(client, 'Main')
    attach(client, original, card)
    assert pinned_layers(client) == [str(original)]
    assert len(pins(client)) == 2

    resp = client.post('/api/canvas/c1/duplicate')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    resp = client.delete('/api/canvas/c1')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # The response the client adopts, and the project it re-reads, agree.
    body = resp.get_json()
    assert body[assignment.STATE_KEY]['pins'] == []
    assert pins(client) == []
    assert str(original) not in alive_ids(client)
    assert_no_dead_pins(client)


def test_deleting_a_canvas_keeps_the_other_canvases_pins(client):
    """Only the deleted screens' pins go. A screen on the surviving canvas
    keeps its pins byte for byte."""
    card = one_card(client)
    c2 = add_canvas(client)
    gone = add_screen(client, 'Gone', 'c1')
    kept = add_screen(client, 'Kept', c2)
    attach(client, gone, card)
    attach(client, kept, card)
    kept_pins_before = [p for p in pins(client) if p['layerId'] == str(kept)]
    assert len(kept_pins_before) == 2
    assert pinned_layers(client) == sorted([str(gone), str(kept)])

    resp = client.delete('/api/canvas/c1')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert pins(client) == kept_pins_before
    assert_no_dead_pins(client)


def test_a_screen_that_moves_house_keeps_its_pins(client):
    """Issue 112: a screen shown on another canvas survives its home canvas's
    delete by moving there. It is still the same layer, so its pins stay."""
    card = one_card(client)
    c2 = add_canvas(client)
    mover = add_screen(client, 'Mover', 'c1')
    gone = add_screen(client, 'Gone', 'c1')
    resp = client.put(f'/api/layer/{mover}/show_canvas', json={'show_canvas_id': c2})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    attach(client, mover, card)
    attach(client, gone, card)
    mover_pins = [p for p in pins(client) if p['layerId'] == str(mover)]
    assert len(mover_pins) == 2

    resp = client.delete('/api/canvas/c1')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert str(mover) in alive_ids(client)
    assert pins(client) == mover_pins
    assert_no_dead_pins(client)


# ── Deleting one screen ───────────────────────────────────────────────────

def test_deleting_a_screen_drops_its_pins_and_nobody_elses(client):
    card = one_card(client)
    gone = add_screen(client, 'Gone')
    kept = add_screen(client, 'Kept')
    attach(client, gone, card)
    attach(client, kept, card)
    kept_pins_before = [p for p in pins(client) if p['layerId'] == str(kept)]
    assert pinned_layers(client) == sorted([str(gone), str(kept)])

    resp = client.delete(f'/api/layer/{gone}')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    # The response the client adopts carries no dead pin either.
    assert resp.get_json()[assignment.STATE_KEY]['pins'] == kept_pins_before
    assert pins(client) == kept_pins_before
    assert_no_dead_pins(client)


# ── Opening a file that already carries orphan pins ───────────────────────

def _file_with_orphans(client):
    """A saved project whose pins name one living screen and one long-gone
    layer - what a file written before this fix looks like."""
    card = one_card(client)
    kept = add_screen(client, 'Kept')
    attach(client, kept, card)
    project = client.get('/api/project').get_json()
    live = [dict(p) for p in project[assignment.STATE_KEY]['pins']]
    orphans = [{'layerId': '3', 'index': 0, 'cardId': card, 'port': 9},
               {'layerId': '3', 'index': 1, 'cardId': card, 'port': 10}]
    project[assignment.STATE_KEY]['pins'] = orphans + live
    assert '3' not in {str(l['id']) for l in project['layers']}
    return project, live


def test_a_loaded_file_is_cleaned_of_orphan_pins_on_open(client):
    """PUT /api/project is the open/undo funnel."""
    project, live = _file_with_orphans(client)
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()[assignment.STATE_KEY]['pins'] == live
    assert pins(client) == live
    assert_no_dead_pins(client)


def test_a_saved_project_is_cleaned_of_orphan_pins_too(client):
    """POST /api/project is the save/reorder funnel; same repair."""
    project, live = _file_with_orphans(client)
    resp = client.post('/api/project', json=project)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert pins(client) == live
    assert_no_dead_pins(client)


def test_a_clean_file_round_trips_its_pins_unchanged(client):
    """The prune is idempotent and touches nothing on a living screen: the
    pins come back exactly as saved, and a second load changes nothing."""
    card = one_card(client)
    kept = add_screen(client, 'Kept')
    attach(client, kept, card)
    project = client.get('/api/project').get_json()
    saved = [dict(p) for p in project[assignment.STATE_KEY]['pins']]
    assert len(saved) == 2
    for _ in range(2):
        resp = client.put('/api/project', json=project)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert pins(client) == saved


# ── The helper on its own ─────────────────────────────────────────────────

def test_prune_orphan_pins_leaves_odd_shapes_alone():
    """A project with no state, a retired-but-pinless state, or a state whose
    pins are not a list is not something to repair; nothing is raised and
    nothing is written."""
    assert assignment.prune_orphan_pins(None) is False
    assert assignment.prune_orphan_pins({'layers': []}) is False
    no_pins = {'layers': [], assignment.STATE_KEY: {'auto': False}}
    assert assignment.prune_orphan_pins(no_pins) is False
    assert no_pins[assignment.STATE_KEY] == {'auto': False}
    odd = {'layers': [], assignment.STATE_KEY: {'pins': 'nope'}}
    assert assignment.prune_orphan_pins(odd) is False
    assert odd[assignment.STATE_KEY]['pins'] == 'nope'


def test_prune_orphan_pins_matches_ids_as_strings():
    """Layer ids are ints on the layer and strings on the pin."""
    project = {
        'layers': [{'id': 8}, {'id': 9, 'type': 'image'}],
        assignment.STATE_KEY: {'auto': False, 'autoRetired': True, 'pins': [
            {'layerId': '8', 'index': 0, 'cardId': 'c', 'port': 1},
            {'layerId': 8, 'index': 1, 'cardId': 'c', 'port': 2},
            {'layerId': '3', 'index': 0, 'cardId': 'c', 'port': 3},
            'garbage',
        ]},
    }
    assert assignment.prune_orphan_pins(project) is True
    assert project[assignment.STATE_KEY]['pins'] == [
        {'layerId': '8', 'index': 0, 'cardId': 'c', 'port': 1},
        {'layerId': 8, 'index': 1, 'cardId': 'c', 'port': 2},
    ]
    assert assignment.prune_orphan_pins(project) is False
