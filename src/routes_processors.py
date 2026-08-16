"""
Processor routes: the chassis / slot / card / breakout box tree that feeds the
Signal panel. Thin controllers over processor_catalog, which owns every rule
about port counts and labels. ("CVT" in identifiers and routes is the stored
key and the API surface, kept stable so saved projects keep opening; the
GENERIC device is a breakout box - CVT is one vendor's name for theirs, the
same way Tessera XD is another's.)

The tree is project state, so it lives on current_project['processors'] and
rides the existing whole-project POST / PUT with no allow-list to fall through.
It is edited through these endpoints rather than by the client patching its own
copy and saving, for one reason: every response carries the RESOLVED tree back,
so the port counts and labels a user reads are the ones the server derived, not
a second implementation in the browser that agrees today.
"""
from flask import Blueprint, request, jsonify

import app
import processor_catalog as catalog
from app import log_event, socketio

processors_bp = Blueprint('processors', __name__)


def _processors():
    # Reading must not create the key. A project with no processors has to
    # stay byte-for-byte what it was before this feature existed, and the
    # panel GETs on every boot - including the boots of everyone who will
    # never define one.
    return app.current_project.get('processors') or []


def _processors_mut():
    return app.current_project.setdefault('processors', [])


def _next_seq():
    seq = app.current_project.get('next_processor_seq') or 1
    app.current_project['next_processor_seq'] = seq + 1
    return seq


def _find_processor(processor_id):
    return next((p for p in _processors() if p.get('id') == processor_id), None)


def _cards_of(proc):
    for slot in proc.get('slots') or []:
        if slot.get('card'):
            yield slot, slot['card']


def _find_card(proc, card_id):
    for _slot, card in _cards_of(proc):
        if card.get('id') == card_id:
            return card
    return None


def _find_cvt(proc, cvt_id):
    for _slot, card in _cards_of(proc):
        for cvt in card.get('cvts') or []:
            if cvt.get('id') == cvt_id:
                return card, cvt
    return None, None


def _state(status=200):
    """Every mutating route answers with the whole resolved tree. A caller that
    only got back what it sent could not tell a stored edit from a dropped one,
    which is the failure mode the layer routes' allow-list keeps producing."""
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    return jsonify({
        'processors': _processors(),
        'resolved': catalog.resolve_all(_processors()),
    }), status


def _apply(node, data, keys):
    changed = {}
    for key in keys:
        if key in data:
            node[key] = data[key]
            changed[key] = data[key]
    return changed


@processors_bp.route('/api/processor-catalog', methods=['GET'])
def processor_catalog():
    """The same file the browser fetches from /static/data, served through the
    API so a test can read the catalog without a web server or a path guess."""
    return jsonify(catalog.load_catalog())


@processors_bp.route('/api/processors', methods=['GET'])
def get_processors():
    return jsonify({
        'processors': _processors(),
        'resolved': catalog.resolve_all(_processors()),
    })


@processors_bp.route('/api/processors', methods=['POST'])
def add_processor():
    data = request.json or {}
    device_id = data.get('deviceId')
    proc = catalog.new_processor(device_id, _next_seq(), data.get('name', ''))
    if not proc:
        return jsonify({'error': f'Unknown device: {device_id}'}), 400
    # An all-in-one's fixed card was built with a seq derived from the
    # processor's, so it cannot collide; a chassis's cards get their own.
    _processors_mut().append(proc)
    log_event('processor_add', {'id': proc['id'], 'device': device_id})
    return _state(201)


@processors_bp.route('/api/processors/<processor_id>', methods=['PUT'])
def update_processor(processor_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    data = request.json or {}
    changed = _apply(proc, data, ('name', 'mode', 'redundancy'))
    log_event('processor_update', {'id': processor_id, 'changed': list(changed)})
    return _state()


@processors_bp.route('/api/processors/<processor_id>', methods=['DELETE'])
def delete_processor(processor_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    _processors_mut().remove(proc)
    log_event('processor_delete', {'id': processor_id})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/slots/<int:index>', methods=['PUT'])
def set_slot_card(processor_id, index):
    """Put a card in a slot, or clear it with deviceId: null. The card is what
    the ports come from, so this is the edit that changes a chassis's capacity
    - the same H9 is a different machine either side of it."""
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    slot = next((s for s in proc.get('slots') or [] if s.get('index') == index), None)
    if slot is None:
        return jsonify({'error': 'Slot not found'}), 404
    if slot.get('card') and slot['card'].get('fixed'):
        return jsonify({'error': 'This device has fixed outputs'}), 400
    data = request.json or {}
    device_id = data.get('deviceId')
    if not device_id:
        slot['card'] = None
        log_event('processor_slot_clear', {'id': processor_id, 'slot': index})
        return _state()
    card = catalog.new_card(device_id, _next_seq(), data.get('name', ''))
    if not card:
        return jsonify({'error': f'Unknown device: {device_id}'}), 400
    slot['card'] = card
    log_event('processor_slot_card', {'id': processor_id, 'slot': index,
                                      'device': device_id})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cards/<card_id>', methods=['PUT'])
def update_card(processor_id, card_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    card = _find_card(proc, card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    data = request.json or {}
    changed = _apply(card, data, ('name', 'portLabelTemplate',
                                  'returnLabelTemplate', 'mode'))
    # A blank template is the ABSENCE of one, on either side. The primary
    # falls back to the built-in {name}-#, the return to <primary>R - rung
    # two of its ladder stepping aside. Deleted rather than stored empty,
    # the same as a cleared port name: an untemplated card is the normal
    # state of every card and must leave nothing behind in the saved file.
    for key in ('portLabelTemplate', 'returnLabelTemplate'):
        if key in data and not (card.get(key) or '').strip():
            card.pop(key, None)
    log_event('processor_card_update', {'id': card_id, 'changed': list(changed)})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cards/<card_id>/ports/<int:number>',
                     methods=['PUT'])
def update_card_port(processor_id, card_id, number):
    """Name one port by hand. A blank hands it back to the card's template.

    Per PORT rather than per card, and on the card rather than on the screen,
    because a port is a socket on a machine: it keeps its name when the wall in
    front of it is renumbered, moved to another screen or deleted. This is the
    only override an assigned port has - the screen's own portLabelOverrides no
    longer reach one - so it is deliberately a plain PUT that any port row can
    make, not a mode anyone has to find.

    `returnName` names the port's RETURN end the same way - the redundancy run
    that leaves this socket and comes back to it. A blank hands it back to the
    derived <primary>R. Either field alone is a valid PUT; a PUT carrying
    neither would silently do nothing, so it is refused instead.
    """
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    card = _find_card(proc, card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    if number < 1:
        return jsonify({'error': 'Port numbers start at 1'}), 400
    data = request.json or {}
    if 'name' not in data and 'returnName' not in data:
        return jsonify({'error': 'name or returnName is required'}), 400
    changed = {'card': card_id, 'port': number}
    if 'name' in data:
        stored = catalog.set_port_name(card, number, data.get('name'))
        changed['named'] = bool(stored)
    if 'returnName' in data:
        stored = catalog.set_return_port_name(card, number,
                                              data.get('returnName'))
        changed['returnNamed'] = bool(stored)
    log_event('processor_port_name', changed)
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cards/<card_id>/cvts', methods=['POST'])
def add_cvt(processor_id, card_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    card = _find_card(proc, card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404
    data = request.json or {}
    device_id = data.get('deviceId')
    # A card has a fixed number of trunks and nothing can add one, so a box
    # with no trunk left is refused rather than drawn and flagged. This is the
    # one place in the feature that blocks instead of reporting: an
    # over-subscribed CARD is a real situation with a real answer, but a box
    # hung on a trunk that does not exist is not a situation at all.
    ok, why = catalog.can_add_cvt(card, device_id)
    if not ok:
        return jsonify({'error': why}), 400
    cvt = catalog.new_cvt(device_id, _next_seq(), data.get('name', ''))
    if not cvt:
        return jsonify({'error': f'Unknown device: {device_id}'}), 400
    card.setdefault('cvts', []).append(cvt)
    # NOVASTAR'S DEFAULT IS A PAIR: a primary box and a backup box, unit to
    # unit, whenever the card's mode has trunks backing other trunks - and a
    # DEFAULT is all it is. `pair: false` declines it up front, deleting the
    # backup box undoes it afterwards, and the backup rides its primary's
    # backup trunk (resolve_card) so the pair really is one set of ports
    # twice. default_backup_pair names the one vendor this is documented for;
    # Brompton pairs the fixed way it pairs, and Megapixel gets no default.
    backup_id = None
    if data.get('pair') is not False and catalog.default_backup_pair(card):
        ok_backup, _why = catalog.can_add_cvt(card, device_id)
        if ok_backup:
            backup = catalog.new_cvt(device_id, _next_seq(), '')
            backup['backupOf'] = cvt['id']
            card['cvts'].append(backup)
            backup_id = backup['id']
    log_event('processor_cvt_add', {'card': card_id, 'device': device_id,
                                    'backup': backup_id})
    return _state(201)


@processors_bp.route('/api/processors/<processor_id>/cvts/<cvt_id>', methods=['PUT'])
def update_cvt(processor_id, cvt_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    _card, cvt = _find_cvt(proc, cvt_id)
    if not cvt:
        return jsonify({'error': 'Breakout box not found'}), 404
    data = request.json or {}
    changed = _apply(cvt, data, ('name', 'portLabelTemplate',
                                 'returnLabelTemplate', 'mode'))
    # Same clearing rule as the card's, for the same reason: a blank hands
    # either template back to what it derives from, and stores nothing.
    for key in ('portLabelTemplate', 'returnLabelTemplate'):
        if key in data and not (cvt.get(key) or '').strip():
            cvt.pop(key, None)
    log_event('processor_cvt_update', {'id': cvt_id, 'changed': list(changed)})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cvts/<cvt_id>', methods=['DELETE'])
def delete_cvt(processor_id, cvt_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    card, cvt = _find_cvt(proc, cvt_id)
    if not cvt:
        return jsonify({'error': 'Breakout box not found'}), 404
    card['cvts'].remove(cvt)
    # A backup whose primary is gone is just a box again. Left pointing at a
    # deleted id, it would jump back onto a backup trunk the moment an id was
    # ever reused - so the link goes with the thing it named.
    for other in card['cvts']:
        if other.get('backupOf') == cvt_id:
            other.pop('backupOf', None)
    log_event('processor_cvt_delete', {'id': cvt_id})
    return _state()
