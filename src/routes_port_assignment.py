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
import itertools
import uuid

from flask import Blueprint, g, request, jsonify

import app
import port_assignment as assignment
import processor_catalog as catalog
from app import log_event, socketio

port_assignment_bp = Blueprint('port_assignment', __name__)

# THE ORDER OF THE ASSIGNMENT'S ANSWERS. Every reply that carries a
# resolution takes the next number BEFORE it reads the stored pins, so a
# reply with a higher number was read from pins at least as new. The page
# keeps the newest it has applied and drops an older answer that arrives
# after it (app-port-assignment _assignmentRequest). A card's Release Ports
# is a chain of unpins, and a released socket that had a port cable
# re-reads the processor tree, which re-resolves the assignment while the
# chain's next unpin is already on its way: a resolve read before that
# unpin and answered after the chain's last reply put the released ports
# back on the not all attached list (owner, 2026-11-04). `boot` changes
# with the server, so a restarted server's numbers starting over are not
# taken for stale ones. itertools.count's next() is one atomic step, so two
# request threads never take the same number (app.processor_state_stamp,
# the processor tree's twin).
_STAMP_BOOT = uuid.uuid4().hex[:12]
_stamps = itertools.count(1)


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
    # A socket the edit lets go of - a released port, a pin moved to
    # another socket, the return a released main carried - forgets the
    # port cable typed on it (owner, 2026-10-17: the lengths go with the
    # feed they belong to). Its snake stays: that is the socket's loom.
    before = (app.current_project.get(assignment.STATE_KEY) or {}).get('pins')
    released = assignment.released_sockets(_processors(), before,
                                           state.get('pins'))
    if released and catalog.forget_port_cables(_processors(), released):
        g.port_cables_forgotten = True
        log_event('port_cables_forgotten', {
            'sockets': [f'{c}:{n}' for c, n in sorted(released)]})
    # A source unplugged from the card in Copy mode that fed its copy takes
    # the copy with it (owner, 2026-11-01): the mirror screen stops
    # mirroring (port_assignment.mirrors_unplugged).
    for layer in assignment.mirrors_unplugged(app.current_project,
                                              _processors(), before,
                                              state.get('pins')):
        clear_mirror(layer, 'source_unplugged')
    app.current_project[assignment.STATE_KEY] = state
    return state


def clear_mirror(layer, why):
    """Let one mirror screen go: its dataMirrorOf comes off the layer, and
    the reply names it (`mirrorsCleared`) so the client drops it from its
    own copy of the layer before the history snapshot."""
    src = layer.pop('dataMirrorOf', None)
    cleared = g.get('mirrors_cleared') or []
    cleared.append(layer.get('id'))
    g.mirrors_cleared = cleared
    log_event('mirror_screen_unplugged', {'id': layer.get('id'),
                                          'mirrorOf': src, 'why': why})


def _processors():
    return app.current_project.get('processors') or []


def _screens():
    """The screens the client sent, each carrying the screen it mirrors
    (mirror a screen, 2026-10-30): the payload's `mirrorOf` where it sent
    one, else the layer's stored dataMirrorOf - the project is where the
    setting lives, so a payload that leaves it out still resolves the
    mirror the way the drawing shows it."""
    screens = (request.json or {}).get('screens') or []
    layers = {str(l.get('id')): l
              for l in app.current_project.get('layers') or []
              if isinstance(l, dict)}
    canvas_names = {c.get('id'): (c.get('name') or '').strip()
                    for c in app.current_project.get('canvases') or []
                    if isinstance(c, dict)}
    stored = {k: l.get('dataMirrorOf') for k, l in layers.items()
              if l.get('dataMirrorOf') not in (None, '')}
    # A mirror this very request let go of (clear_mirror) is no mirror,
    # whatever the payload - sent before the request - still says.
    cleared = {str(i) for i in (g.get('mirrors_cleared') or [])}
    # The shape each mirrored or mirroring screen has on the client (its
    # `mirrorShape`): checked in place of the stored layer's, which a
    # resize's layer PUT may not have reached yet.
    shapes = {str(scr.get('layerId', scr.get('id'))):
              assignment.clean_mirror_shape(scr.get('mirrorShape'))
              for scr in screens if isinstance(scr, dict)}
    out = []
    for scr in screens:
        if not isinstance(scr, dict):
            out.append(scr)
            continue
        key = str(scr.get('layerId', scr.get('id')))
        # The canvas the screen sits on, by name, where the client sent
        # none: a canvas refusal names it (port_assignment.canvas_spans).
        if not isinstance(scr.get('canvas'), str) and key in layers:
            name = canvas_names.get(layers[key].get('canvas_id'))
            if name:
                scr = dict(scr, canvas=name)
        if key in cleared:
            scr = {k: v for k, v in scr.items() if k != 'mirrorOf'}
        elif 'mirrorOf' not in scr and key in stored:
            scr = dict(scr, mirrorOf=stored[key])
        src = scr.get('mirrorOf')
        # A mirror whose two screens no longer match (one resized after
        # the mirror was set) is flagged, never followed.
        if src not in (None, '') and str(src) in layers and key in layers:
            why = assignment.mirror_mismatch(
                layers[str(src)], layers[key],
                (shapes.get(str(src)), shapes.get(key)))
            if why:
                scr = dict(scr, mirrorMismatch=why)
        out.append(scr)
    return out


def _mirror_refused(layer_id):
    """The 409 for placing a mirror screen's ports on their own
    (port_assignment.mirror_refusal), else None."""
    why = assignment.mirror_refusal(_screens(), layer_id, _processors(),
                                    _state())
    if why:
        return jsonify({'error': why, 'mirror': True}), 409
    return None


def _payload():
    # The number is taken first and the pins read after it, never the other
    # way round (see _stamps): a reply never pairs a newer number with pins
    # read before it.
    stamp = {'boot': _STAMP_BOOT, 'n': next(_stamps)}
    state = _state()
    return {
        'state': state,
        'resolution': assignment.resolve(_processors(), _screens(), state),
        'assignmentStamp': stamp,
    }


def _link_refused(state):
    """The 409 for an edit that would push a box past its link cap (a box
    behind a QD-S - port_assignment.link_cap_refusal) or a processor past
    its canvas (port_assignment.canvas_refusal), else None. Checked
    on the working copy BEFORE it is stored, so a refused edit leaves the
    project exactly as it found it."""
    why = assignment.link_cap_refusal(_processors(), _screens(), _state(),
                                      _screens(), state)
    if why:
        return jsonify({'error': why, 'linkCap': True}), 409
    # THE CANVAS (owner, 2026-10-07): a mapping that would take a Brompton
    # processor's screens past the canvas it publishes is refused the same
    # way, on the same working copy - port_assignment.canvas_refusal.
    why = assignment.canvas_refusal(_processors(), _screens(), _state(),
                                    _screens(), state)
    if why:
        return jsonify({'error': why, 'canvas': True}), 409
    # CARDS THAT CANNOT LOAD ONE SCREEN TOGETHER (NovaStar's H cards -
    # port_assignment.mix_refusal): refused, never warned.
    why = assignment.mix_refusal(_processors(), _state(), _processors(),
                                 state, _screens())
    if why:
        return jsonify({'error': why, 'cardMix': True}), 409
    return None


def _saved(state, status=200, extra=None):
    """Every mutating route answers with the whole resolved assignment. A
    caller that only got back what it sent could not tell a stored edit from a
    dropped one, which is the failure mode this codebase's allow-lists keep
    producing.

    `state` is what the route just stored. The reply reads the stored pins
    again after taking its number (_payload), so an edit another request
    stored in between is in it and the number tells the page the truth."""
    app.current_project['is_pristine'] = False
    import routes_project
    routes_project.emit_project_edited()
    body = _payload()
    if g.get('port_cables_forgotten'):
        # The tree changed with the pins (a released socket's cable went),
        # so it rides the reply the way the processor routes send it: the
        # client folds it in before its snapshot, and undo holds both.
        body.update({
            'stateStamp': app.processor_state_stamp(),
            'processors': _processors(),
            'resolved': catalog.resolve_all(_processors()),
            'next_processor_seq':
                app.current_project.get('next_processor_seq'),
            'dataCableConnectors': catalog.data_cable_connectors(),
            'snakes': catalog.resolved_show_snakes(app.current_project),
            'fiberCables': catalog.resolved_fiber_cables(app.current_project),
        })
    if g.get('mirrors_cleared'):
        # The mirror screens this edit unplugged (clear_mirror): the
        # client drops their dataMirrorOf before its snapshot.
        body['mirrorsCleared'] = list(g.mirrors_cleared)
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


@port_assignment_bp.route('/api/port-assignments/link-check', methods=['POST'])
def link_check():
    """Whether a PROCESSING change may go ahead: `before` is the screens as
    they are, `screens` as they would be with the new bit depth, frame rate
    or ULL - pixels and settings both, from the client's port maths. The
    pins stay as stored. 409 with the reason where a box behind a QD-S
    would be pushed past its link cap (port_assignment.link_cap_refusal) -
    the client then leaves the setting as it was - else 200. Read-only:
    nothing is stored, and the legacy freeze is not run on counts that are
    only a proposal."""
    data = request.json or {}
    why = assignment.link_cap_refusal(_processors(), data.get('before') or [],
                                      _state(), _screens(), _state())
    if why:
        return jsonify({'error': why, 'linkCap': True}), 409
    # Low latency lowers an SX40's canvas height and the port maths moves
    # with the bit depth, so a Processing change is held to the canvas too.
    why = assignment.canvas_refusal(_processors(), data.get('before') or [],
                                    _state(), _screens(), _state())
    if why:
        return jsonify({'error': why, 'canvas': True}), 409
    return jsonify({'ok': True})


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
    refused = _mirror_refused(layer_id)
    if refused:
        return refused
    _retire()
    state = _working()
    pinned, error = assignment.pin_to_card(
        _processors(), _screens(), state, layer_id, index, card_id, port)
    if error:
        return jsonify({'error': error}), 409
    refused = _link_refused(state)
    if refused:
        return refused
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
    refused = _mirror_refused(layer_id)
    if refused:
        return refused
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
    refused = _link_refused(state)
    if refused:
        return refused
    log_event('port_assignment_place', {'layer': layer_id, 'index': index,
                                        'card': card_id, 'port': placed['port'],
                                        'confirmed': bool(data.get('confirm'))})
    return _saved(_store(state), extra={'moved': placed})


@port_assignment_bp.route('/api/port-assignments/unpin', methods=['POST'])
def unpin_port():
    """Release one pinned port, or a whole screen's worth when no index is
    given. The port comes off its card and stays unattached until somebody
    places it again.

    On a MIRROR screen a release is "unplug the copy" (owner, 2026-11-01:
    "Unplugging only the copy screen just removes the copy"): the screen
    stops mirroring - its dataMirrorOf comes off - and its source keeps
    every port. A mirror holds no pins, so nothing else changes."""
    data = request.json or {}
    layer_id = data.get('layerId')
    if layer_id is None:
        return jsonify({'error': 'layerId is required'}), 400
    layer = next((l for l in app.current_project.get('layers') or []
                  if isinstance(l, dict) and str(l.get('id')) == str(layer_id)),
                 None)
    sent = next((s for s in (request.json or {}).get('screens') or []
                 if isinstance(s, dict)
                 and str(s.get('layerId', s.get('id'))) == str(layer_id)), None)
    if layer is not None and (layer.get('dataMirrorOf') not in (None, '')
                              or (sent and sent.get('mirrorOf')
                                  not in (None, ''))):
        clear_mirror(layer, 'copy_unplugged')
        return _saved(_state())
    _retire()
    if not (app.current_project.get(assignment.STATE_KEY) or {}).get('pins'):
        return jsonify(_payload())  # nothing pinned; releasing changes nothing
    index = data.get('index')
    state = assignment.clear_pin(_working(), layer_id,
                                 None if index is None else int(index))
    log_event('port_assignment_unpin', {'layer': layer_id, 'index': index})
    return _saved(_store(state))


@port_assignment_bp.route('/api/port-assignments/merge', methods=['POST'])
def merge_ports():
    """Several ports of one screen redrawn as one (port_assignment.
    merge_pins): the removed ports' pins are released, every later pin of
    the screen follows its port to the number it closed up to. The client
    has already renumbered the screen's runs; this keeps the cards in step
    with them. Released sockets forget their port cable the way any release
    does (_store)."""
    data = request.json or {}
    layer_id = data.get('layerId')
    if layer_id is None:
        return jsonify({'error': 'layerId is required'}), 400
    try:
        removed = [int(i) for i in data.get('removed') or []]
    except (TypeError, ValueError):
        return jsonify({'error': 'removed must be port indices'}), 400
    _retire()
    state = assignment.merge_pins(_working(), layer_id, removed)
    log_event('port_assignment_merge', {'layer': layer_id, 'removed': removed})
    return _saved(_store(state))


@port_assignment_bp.route('/api/port-assignments/remap', methods=['POST'])
def remap_ports():
    """A screen's ports renumbered under their cabinets (port_assignment.
    remap_pins): each pin moves with its cabinets to the port number they
    ride now, and one whose cabinets are gone is released. `moves` is
    [[oldIndex, newIndex or null], ...], worked out by the client, which
    owns which cabinets ride which port."""
    data = request.json or {}
    layer_id = data.get('layerId')
    if layer_id is None:
        return jsonify({'error': 'layerId is required'}), 400
    moves = {}
    try:
        for pair in data.get('moves') or []:
            old, new = pair
            moves[int(old)] = None if new is None else int(new)
    except (TypeError, ValueError):
        return jsonify({'error': 'moves must be [old, new] port indices'}), 400
    _retire()
    state = assignment.remap_pins(_working(), layer_id, moves)
    log_event('port_assignment_remap', {'layer': layer_id,
                                        'moves': sorted(moves.items())})
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
    refused = _mirror_refused(layer_id)
    if refused:
        return refused
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
    refused = _link_refused(state)
    if refused:
        return refused
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
    last_index = data.get('lastIndex')
    refused = _mirror_refused(layer_id)
    if refused:
        return refused
    _retire()
    state = _working()
    moved, error = assignment.place_overflow(
        _processors(), _screens(), state, layer_id, card_id,
        # Same box-span window move-block carries; see that route.
        first_port=None if first is None else int(first),
        last_port=None if last is None else int(last),
        # ...and the box itself, whose sockets need not run unbroken.
        box_id=data.get('boxId') or None,
        # The dock's drop names the screen port under the cursor (0-based):
        # the fill takes the unplaced ports up to it and no further.
        last_index=None if last_index is None else int(last_index))
    if error:
        return jsonify({'error': error}), 409
    refused = _link_refused(state)
    if refused:
        return refused
    log_event('port_assignment_overflow', {'layer': layer_id, 'card': card_id,
                                           'ports': len(moved['moved'])})
    return _saved(_store(state), extra={'moved': moved})
