"""
Port assignment routes: which sending-card port each screen's ports sit on.

Thin controllers over port_assignment, which owns every rule about allocation
order, clashes and overflow. The same reasoning as routes_processors: every
response carries the RESOLVED assignment back, so the port numbers a user reads
are the ones the server derived rather than a second implementation in the
browser that agrees today and disagrees on the wall that matters.

The one thing worth knowing before reading this file is why the client sends
its screens on every request instead of the server reading them off the
project. How many ports a screen needs is not a property of the screen - it
falls out of the cabinet grid, the flow pattern, any custom path the user drew,
and ports that cross into a group peer - and that maths lives in
getLayerPortsRequired on the client. Sending the answer keeps ONE implemen-
tation of it. It also means nothing derived is ever stored: the project holds
pins (and the retired-auto stamp), and everything else is worked out fresh.

The screen's processing platform rides in the same payload, because the
platform wall (port_assignment's "Who may drive whom") needs it on every
resolve and every edit - a Legacy screen may not land on COEX gear, and the
refusal has to know what the screen is programmed to say so.

Auto-numbering is retired (user ruling, 2026-09-03). The one place it still
touches these routes is the migration: a project saved before the ruling
reaches its first request here without the `autoRetired` mark, and because
the screens' port counts arrive with that request, THIS is where its
auto-drawn ports get frozen into pins (port_assignment.retire_auto) - the
project funnel could only stamp the hardware-less cases. Every route runs
the freeze first, so a legacy project's first edit and first read agree.
"""
from flask import Blueprint, request, jsonify

import app
import port_assignment as assignment
from app import log_event, socketio

port_assignment_bp = Blueprint('port_assignment', __name__)


def _retire():
    """The one-time freeze, run at the head of every route here (see the
    module docstring). Returns True when it changed the project, so the
    resolve read can tell the client its state moved."""
    if assignment.retire_auto(app.current_project, _screens()):
        log_event('port_assignment_auto_retired', {'at': request.path})
        return True
    return False


def _state():
    # Reading must not create the key: a read is a read, and the state a
    # project carries is the funnel's business (every project is born with
    # it, and a legacy file gets it from retire_auto).
    return app.current_project.get(assignment.STATE_KEY) or assignment.new_state()


def _working():
    """A copy to edit, so a refused edit leaves no trace.

    Editing the stored dict in place and then returning 409 would write a
    half-made edit onto the project - a refused placement must leave the
    state exactly as it found it. The copy is only written back once the
    edit actually succeeded. The copy carries the retired-auto stamp
    whatever the stored shape was; by the time an edit runs, _retire has
    already put it there.
    """
    stored = app.current_project.get(assignment.STATE_KEY)
    if not isinstance(stored, dict):
        return assignment.new_state()
    state = assignment.new_state()
    state['pins'] = [dict(p) for p in (stored.get('pins') or [])
                     if isinstance(p, dict)]
    return state


def _store(state):
    app.current_project[assignment.STATE_KEY] = state
    return state


def _processors():
    return app.current_project.get('processors') or []


def _screens():
    return (request.json or {}).get('screens') or []


def _payload(state=None):
    state = state if state is not None else _state()
    return {
        'state': state,
        'resolution': assignment.resolve(_processors(), _screens(), state),
    }


def _saved(state, status=200, extra=None):
    """Every mutating route answers with the whole resolved assignment. A
    caller that only got back what it sent could not tell a stored edit from a
    dropped one, which is the failure mode this codebase's allow-lists keep
    producing."""
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    body = _payload(state)
    if extra:
        body.update(extra)
    return jsonify(body), status


@port_assignment_bp.route('/api/port-assignments/resolve', methods=['POST'])
def resolve_assignments():
    """Read-only despite the verb. It is a POST because the screen port counts
    have to travel with it and they are a list, not a query string - and
    because a GET that quietly stamped a key onto the project is precisely the
    regression this feature is not allowed to have.

    The one write it may make is the migration (see the module docstring):
    a legacy project's first resolve is the first request that knows where
    its auto-drawn ports were, and freezing them there is the migration, not
    an edit. `migrated` in the body tells the client to take the returned
    state even though nothing was asked for - a legacy file's client-side
    copy has no state to update otherwise, and the pins have to reach it or
    the next undo snapshot would hand back a project the funnel has to
    freeze again."""
    migrated = _retire()
    body = _payload()
    if migrated:
        body['migrated'] = True
    return jsonify(body)


@port_assignment_bp.route('/api/port-assignments', methods=['PUT'])
def set_options():
    """410 Gone. This was the auto-numbering switch. Auto is retired (user
    ruling, 2026-09-03): nothing lands on a card unless a person put it
    there, so there is no option left to set. A client still sending one is
    an old build, and it gets told so rather than silently ignored - an
    ignored request would look like a state change that never happened."""
    return jsonify({
        'error': 'Auto-numbering is retired. Ports land only where they are '
                 'placed; there is no numbering option to set.',
    }), 410


@port_assignment_bp.route('/api/port-assignments/pin', methods=['POST'])
def pin_port():
    data = request.json or {}
    layer_id = data.get('layerId')
    card_id = data.get('cardId')
    try:
        index = int(data.get('index'))
    except (TypeError, ValueError):
        return jsonify({'error': 'index is required'}), 400
    if layer_id is None or not card_id:
        return jsonify({'error': 'layerId and cardId are required'}), 400
    # The port number is optional: "put this one on that card" is the decision,
    # and which free number it lands on is arithmetic the server already owns.
    port = data.get('port')
    if port is not None:
        try:
            port = int(port)
        except (TypeError, ValueError):
            return jsonify({'error': 'port must be a number'}), 400
        if port < 1:
            return jsonify({'error': 'Port numbers start at 1'}), 400
    if str(card_id) not in {c['cardId'] for c in
                            assignment.cards_in(_processors())}:
        return jsonify({'error': 'That card is not in this project'}), 404
    _retire()
    state = _working()
    pinned, error = assignment.pin_to_card(
        _processors(), _screens(), state, layer_id, index, card_id, port)
    if error:
        return jsonify({'error': error}), 409
    log_event('port_assignment_pin', {'layer': layer_id, 'index': index,
                                      'card': card_id, 'port': pinned['port']})
    return _saved(_store(state), extra={'pinned': pinned})


@port_assignment_bp.route('/api/port-assignments/place', methods=['POST'])
def place_port():
    """Put one port of one screen on the card port somebody named.

    Deliberately not /pin. A pin says "hold this port, on that card, wherever
    that turns out to be" and lands on the lowest free number; a placement
    names the socket. Naming the socket is what makes landing on somebody
    else's claim possible on purpose, and that is the one case that has to be
    read out and agreed to rather than quietly reported afterwards - so it gets
    a 409 carrying the conflict, and the same request with confirm goes
    through.

    It is also the endpoint the Processors panel posts to. Pointing at a socket
    and saying what plugs into it, and pointing at a screen's port and saying
    where it goes, are the same edit written from the two ends of one cable;
    two routes for it would be two chances to disagree.
    """
    data = request.json or {}
    layer_id = data.get('layerId')
    card_id = data.get('cardId')
    try:
        index = int(data.get('index'))
        port = int(data.get('port'))
    except (TypeError, ValueError):
        return jsonify({'error': 'index and port are required'}), 400
    if layer_id is None or not card_id:
        return jsonify({'error': 'layerId and cardId are required'}), 400
    if str(card_id) not in {c['cardId'] for c in
                            assignment.cards_in(_processors())}:
        return jsonify({'error': 'That card is not in this project'}), 404
    _retire()
    state = _working()
    placed, error, conflict = assignment.place_port(
        _processors(), _screens(), state, layer_id, index, card_id, port,
        confirm=bool(data.get('confirm')))
    if error:
        body = {'error': error}
        # The client may not simply retry: a conflict is a question, and the
        # answer to it is a person reading who is already there.
        if conflict:
            body['conflict'] = conflict
        return jsonify(body), 409
    log_event('port_assignment_place', {'layer': layer_id, 'index': index,
                                        'card': card_id, 'port': placed['port'],
                                        'confirmed': bool(data.get('confirm'))})
    return _saved(_store(state), extra={'moved': placed})


@port_assignment_bp.route('/api/port-assignments/unpin', methods=['POST'])
def unpin_port():
    """Release one pinned port, or a whole screen's worth when no index is
    given. The port comes off its card and stays unattached until somebody
    places it again."""
    data = request.json or {}
    layer_id = data.get('layerId')
    if layer_id is None:
        return jsonify({'error': 'layerId is required'}), 400
    _retire()
    if not (app.current_project.get(assignment.STATE_KEY) or {}).get('pins'):
        return jsonify(_payload())  # nothing pinned; releasing changes nothing
    index = data.get('index')
    state = assignment.clear_pin(_working(), layer_id,
                                 None if index is None else int(index))
    log_event('port_assignment_unpin', {'layer': layer_id, 'index': index})
    return _saved(_store(state))


@port_assignment_bp.route('/api/port-assignments/move-block', methods=['POST'])
def move_block():
    data = request.json or {}
    layer_id = data.get('layerId')
    if layer_id is None:
        return jsonify({'error': 'layerId is required'}), 400
    start = data.get('startPort')
    first = data.get('firstPort')
    last = data.get('lastPort')
    _retire()
    state = _working()
    moved, error = assignment.move_block(
        _processors(), _screens(), state, layer_id,
        card_id=data.get('cardId'),
        start_port=None if start is None else int(start),
        # A breakout box is a span of card ports; the dock sends the span so
        # "drop the box on a screen" lands the run on the box and nowhere else.
        first_port=None if first is None else int(first),
        last_port=None if last is None else int(last))
    if error:
        return jsonify({'error': error}), 409
    log_event('port_assignment_move_block', {'layer': layer_id, 'to': moved})
    return _saved(_store(state), extra={'moved': moved})


@port_assignment_bp.route('/api/port-assignments/place-overflow', methods=['POST'])
def place_overflow():
    data = request.json or {}
    layer_id = data.get('layerId')
    card_id = data.get('cardId')
    if layer_id is None or not card_id:
        return jsonify({'error': 'layerId and cardId are required'}), 400
    first = data.get('firstPort')
    last = data.get('lastPort')
    _retire()
    state = _working()
    moved, error = assignment.place_overflow(
        _processors(), _screens(), state, layer_id, card_id,
        # Same box-span window move-block carries; see that route.
        first_port=None if first is None else int(first),
        last_port=None if last is None else int(last))
    if error:
        return jsonify({'error': error}), 409
    log_event('port_assignment_overflow', {'layer': layer_id, 'card': card_id,
                                           'ports': len(moved['moved'])})
    return _saved(_store(state), extra={'moved': moved})
