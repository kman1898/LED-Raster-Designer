"""The log says why (2026-11-19 logging audit, phase 3), server side.

The port assignment's fills and placements make choices nobody spelled
out: which free socket, where a run split at a card's capacity, which
cards were skipped, a block moved whole. Each now hands back a short list
of reasons (port_assignment `reasons=`) that the routes log with the
placement, a refused placement is logged as a warning with its reason,
and a screen's port state ("6 of 17 ports on a card, not attached: port
17") is logged when it changes, never on every resolve. Callers that pass
no list get exactly the answer they always got.

Also here: a run of folded lines that carried their own message reads as
its last message (app.py log_event), so a page's plain line keeps its
words when a gesture repeats it.

Run locally:
    python -m pytest tests/test_log_reasons.py -n 4 --dist loadfile
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402
import port_assignment as assignment  # noqa: E402
import routes_logs  # noqa: E402
import routes_port_assignment  # noqa: E402
from test_port_assignment import add_processor, card_ids, screens, set_card  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture()
def seen(monkeypatch):
    """Every line the port assignment routes write: (action, details, kw)."""
    lines = []
    monkeypatch.setattr(routes_port_assignment, 'log_event',
                        lambda action, details=None, *a, **kw: lines.append((action, details or {}, kw)))
    # Each test starts with no memory of what a screen's ports read like.
    monkeypatch.setattr(routes_port_assignment, '_last_reasons', {'project': None, 'by_layer': {}})
    return lines


def _of(lines, action):
    return [d for a, d, _kw in lines if a == action]


@pytest.fixture()
def one_card(client):
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    return client, card_ids(state)[0]


@pytest.fixture()
def two_cards(client):
    state = add_processor(client, 'novastar-h9')
    pid = state['resolved'][0]['id']
    set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    state = set_card(client, pid, 1, 'novastar-card-h-16xrj45-2xfiber')
    ids = card_ids(state)
    return client, ids[0], ids[1]


def test_a_drop_past_a_cards_capacity_says_where_it_split_and_why(one_card, seen):
    client, card = one_card
    sc = screens(('Main', 17))
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Main', 'cardId': card, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    # the reply is the shape it always was
    assert set(resp.get_json()['moved']) == {'cardId', 'moved', 'note'}
    [line] = _of(seen, 'port_assignment_overflow')
    assert line['ports'] == 16
    reasons = line['reasons']
    assert reasons[0] == '17 unplaced ports'
    assert any(r.startswith('packed from port 1 on ') for r in reasons), reasons
    assert any(r.startswith('split at capacity: 16 free on ') and r.endswith('1 left not attached')
               for r in reasons), reasons
    # and the screen's state, said once
    [state] = _of(seen, 'port_assignment_reasons')
    [main] = state['screens']
    assert main['name'] == 'Main'
    assert main['reasons'][:2] == ['16 of 17 ports on a card', 'not attached: port 17']


def test_a_refused_placement_is_a_warning_with_its_reason(one_card, seen):
    client, card = one_card
    sc = screens(('Main', 16), ('Side', 2))
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card, 'screens': sc})
    resp = client.post('/api/port-assignments/place-overflow',
                       json={'layerId': 'Side', 'cardId': card, 'screens': sc})
    assert resp.status_code == 409
    [refused] = [(d, kw) for a, d, kw in seen if a == 'port_assignment_refused']
    details, kw = refused
    assert kw.get('level') == 'warn' and kw.get('area') == 'data'
    assert details['route'] == 'place-overflow' and details['layer'] == 'Side'
    assert details['why'] == resp.get_json()['error']
    assert 'has no free ports' in details['why']


def test_the_port_state_is_logged_on_a_change_not_on_every_resolve(one_card, seen):
    client, card = one_card
    sc = screens(('Main', 3), ('Side', 2))
    for _ in range(3):
        assert client.post('/api/port-assignments/resolve', json={'screens': sc}).status_code == 200
    states = _of(seen, 'port_assignment_reasons')
    assert len(states) == 1, states
    assert {s['name'] for s in states[0]['screens']} == {'Main', 'Side'}
    seen.clear()
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Side', 'cardId': card, 'screens': sc})
    client.post('/api/port-assignments/resolve', json={'screens': sc})
    [state] = _of(seen, 'port_assignment_reasons')
    # only the screen that changed
    assert [s['name'] for s in state['screens']] == ['Side']
    assert state['screens'][0]['reasons'] == ['2 of 2 ports on a card']


def test_a_pin_says_which_free_port_it_took(one_card, seen):
    client, card = one_card
    sc = screens(('Main', 3), ('Side', 2))
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card, 'screens': sc})
    resp = client.post('/api/port-assignments/pin', json={
        'layerId': 'Side', 'index': 0, 'cardId': card, 'screens': sc})
    assert resp.status_code == 200
    assert resp.get_json()['pinned'] == {'cardId': card, 'port': 4}
    [pin] = _of(seen, 'port_assignment_pin')
    assert pin['port'] == 4
    assert pin['reasons'] == [f'lowest free port on {_title(client, card)} is 4 (3 before it taken or held for backup)']


def _title(client, card):
    res = client.post('/api/port-assignments/resolve', json={'screens': []}).get_json()['resolution']
    return next(c['title'] for c in res['cards'] if c['cardId'] == card)


def test_a_block_move_says_where_it_looked_and_where_it_landed(two_cards, seen):
    client, card_a, card_b = two_cards
    sc = screens(('Main', 10), ('Side', 8))
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card_a, 'screens': sc})
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Side', 'cardId': card_b, 'screens': sc})
    seen.clear()
    resp = client.post('/api/port-assignments/move-block', json={'layerId': 'Main', 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    [move] = _of(seen, 'port_assignment_move_block')
    reasons = move['reasons']
    assert reasons[0].startswith('searched forward from port 1 on ')
    assert any(r.startswith('first free run of 10 starts at port 2 on ') for r in reasons), reasons
    assert reasons[-1] == "whole run moved together; this screen's own pins replaced"


def test_a_hand_placement_names_where_the_port_came_from(two_cards, seen):
    client, card_a, card_b = two_cards
    sc = screens(('Main', 4))
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card_a, 'screens': sc})
    resp = client.post('/api/port-assignments/place', json={
        'layerId': 'Main', 'index': 3, 'cardId': card_b, 'port': 5, 'screens': sc})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    [place] = _of(seen, 'port_assignment_place')
    assert place['reasons'][0].startswith('moved from ')
    assert place['reasons'][-1] == 'Main now spans 2 cards'
    [state] = _of(seen, 'port_assignment_reasons')[-1:]
    assert any(r.startswith('split across 2 cards') for r in state['screens'][0]['reasons'])


def test_the_solver_answers_as_before_when_no_one_asks_why(one_card):
    """A caller that passes no list (the routes above all pass one) gets
    the dict it always got."""
    _client, card = one_card
    procs = app_module.current_project.get('processors') or []
    moved, error = assignment.place_overflow(procs, screens(('Main', 3)), assignment.new_state(), 'Main', card)
    assert error is None and set(moved) == {'cardId', 'moved', 'note'}
    pinned, error = assignment.pin_to_card(procs, screens(('Main', 3)), assignment.new_state(), 'Main', 0, card)
    assert error is None and pinned == {'cardId': card, 'port': 1}


# ── the written line ─────────────────────────────────────────────────────

@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    app_module.flush_log()
    path = tmp_path / 'led_raster_designer.log'
    path.write_text('', encoding='utf-8')
    for mod in (app_module, routes_logs):
        monkeypatch.setattr(mod, 'LOG_FILE_PATH', str(path))
        monkeypatch.setattr(mod, 'LOG_DIR_PATH', str(tmp_path))
    yield path
    app_module.flush_log()


def _lines(path):
    app_module.flush_log()
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def test_the_written_lines_read_plainly(one_card, log_file, monkeypatch):
    client, card = one_card
    monkeypatch.setattr(routes_port_assignment, '_last_reasons', {'project': None, 'by_layer': {}})
    sc = screens(('Main', 17))
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card, 'screens': sc})
    client.post('/api/port-assignments/place-overflow',
                json={'layerId': 'Main', 'cardId': card, 'screens': sc})
    lines = {x['action']: x for x in _lines(log_file)
             if x['action'].startswith('port_assignment_')}
    drop = lines['port_assignment_overflow']
    assert drop['area'] == 'data' and drop['lvl'] == 'info'
    assert drop['msg'].startswith(f'Screen #Main dropped on card {card}: 16 ports placed (17 unplaced ports; ')
    assert 'split at capacity' in drop['msg']
    state = lines['port_assignment_reasons']
    assert state['msg'] == 'Ports: Main: 16 of 17 ports on a card, not attached: port 17'
    refused = lines['port_assignment_refused']
    assert refused['lvl'] == 'warn'
    assert refused['msg'].startswith('Port placement refused (place-overflow): ')
    for line in lines.values():
        assert '—' not in line['msg'] and '–' not in line['msg']


def test_a_folded_run_reads_as_its_last_message(log_file):
    for n in range(4):
        app_module.log_event('pad_button', {'button': 'A', 'page': 'P'}, source='client',
                             area='pad', msg=f'Controller: A pressed ({n})', fold='client:P:pad-A')
    lines = [x for x in _lines(log_file) if x['action'] == 'pad_button']
    assert [x['msg'] for x in lines][0] == 'Controller: A pressed (0)'
    assert lines[-1]['msg'].startswith('Controller: A pressed (3) (4 steps, ')
    assert lines[-1]['details']['steps'] == 4
