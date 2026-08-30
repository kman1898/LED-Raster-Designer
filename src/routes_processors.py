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


def _all_cards():
    for proc in _processors():
        for _slot, card in _cards_of(proc):
            yield proc, card


def _card_title(card):
    device = catalog.get_device((card or {}).get('deviceId')) or {}
    return ((card or {}).get('name') or '').strip() \
        or device.get('name', (card or {}).get('deviceId'))


def _resolved_card(card_id):
    for rproc in catalog.resolve_all(_processors()):
        for slot in rproc.get('slots') or []:
            rcard = slot.get('card')
            if rcard and rcard['id'] == card_id:
                return rcard
    return None


def _prune_backup_refs(removed_ids):
    """Drop redundancy links that name a card which is no longer there.

    Same rule as a breakout box's backupOf on delete: left pointing at a
    dead id, the link would spring back to life the moment an id was ever
    reused - so it goes with the thing it named.
    """
    removed = set(removed_ids)
    if not removed:
        return
    for _proc, card in _all_cards():
        if card.get('backupCardId') in removed:
            card.pop('backupCardId', None)
        entries = card.get('backupPorts') or {}
        for key in [k for k, v in entries.items()
                    if (v or {}).get('cardId') in removed]:
            entries.pop(key)
        if not entries:
            card.pop('backupPorts', None)


def _set_redundancy_mode(card, mode):
    """Store one card's redundancy mode, or refuse where the vendor fixed it.

    '1to1' is stored as ABSENCE - it is the default, and a stored copy of a
    default reads as a value nobody can tell from a choice (the template
    birth-stamp lesson). The stored 1to1 partner and manual picks survive a
    mode switch on purpose: they are choices somebody made, inert while
    another mode is active, and destroying them because the select was
    toggled to compare would be hostile.
    """
    device = catalog.get_device(card.get('deviceId')) or {}
    if ((device.get('redundancy') or {}).get('pairing')) == 'adjacent':
        return (f'{device.get("name", "This device")} pairs adjacent outputs '
                f'automatically - its pairing is a fact of the device, not a '
                f'mode.')
    if mode and mode not in catalog.REDUNDANCY_MODES:
        return f'Unknown redundancy mode: {mode}'
    if not mode or mode == '1to1':
        card.pop('redundancyMode', None)
    else:
        card['redundancyMode'] = mode
    return None


def _set_backup_card(card, card_id, backup_id):
    """Point one card at the unit that backs it up, 1:1, or clear the pick.

    The checks are against the RESOLVED tree, not raw keys, so a stale pick
    left inert by a mode switch blocks nothing: consumed means consumed in
    the resolution the whole app reads.
    """
    if not backup_id:
        card.pop('backupCardId', None)
        return None
    if backup_id == card_id:
        return 'A unit cannot back itself.'
    target = next((c for _p, c in _all_cards() if c.get('id') == backup_id),
                  None)
    if target is None:
        return 'That card is not in this project.'
    main_cap = catalog.port_capacity(card.get('deviceId'), card.get('mode'))
    back_cap = catalog.port_capacity(target.get('deviceId'),
                                     target.get('mode'))
    title, back_title = _card_title(card), _card_title(target)
    # A 1:1 backup mirrors port for port - main port N returns on backup
    # port N - so the counts must MATCH, and both must be settled: a backup
    # with ports left over is mislabelled spare capacity, one with too few
    # leaves mains with no return, and an unknown count could be either.
    if main_cap['count'] is None or back_cap['count'] is None:
        short = title if main_cap['count'] is None else back_title
        return (f'{short} has no settled port count, so a port-for-port '
                f'mirror cannot be checked.')
    if main_cap['count'] != back_cap['count']:
        return (f'{back_title} has {back_cap["count"]} ports and {title} '
                f'has {main_cap["count"]} - a 1:1 backup mirrors port for '
                f'port, so the counts must match.')
    resolved_target = _resolved_card(backup_id)
    taken = (resolved_target or {}).get('backupFor')
    if taken and taken.get('cardId') != card_id:
        return f'{back_title} already backs up {taken.get("title")}.'
    resolved_self = _resolved_card(card_id)
    mine = (resolved_self or {}).get('backupFor')
    if mine:
        return (f'{title} backs up {mine.get("title")} - a backup unit '
                f'cannot take a backup of its own.')
    t_shape = (resolved_target or {}).get('redundancyShape') or {}
    if t_shape.get('mode') == '1to1' and \
            (resolved_target or {}).get('backupCardId'):
        return (f'{back_title} has a backup of its own - it is a main, and '
                f'a main cannot also be one.')
    card['backupCardId'] = backup_id
    return None


def _set_port_backup(card, card_id, number, spec):
    """Store or clear one main port's hand-picked backup port.

    Refusals mirror the assignment resolver's wording where the situation is
    the same one (a card that is not there, a port past the ceiling),
    because the person reading them is standing in the same place.
    """
    if not spec:
        entries = card.get('backupPorts') or {}
        entries.pop(str(number), None)
        entries.pop(number, None)
        if not entries:
            card.pop('backupPorts', None)
        return None
    target_id = spec.get('cardId') or card_id
    target = next((c for _p, c in _all_cards() if c.get('id') == target_id),
                  None)
    if target is None:
        return 'That card is not in this project.'
    try:
        port = int(spec.get('port'))
    except (TypeError, ValueError):
        return 'backup.port must be a number.'
    if port < 1:
        return 'Port numbers start at 1.'
    if target_id == card_id and port == number:
        return 'A port cannot back itself.'
    cap = catalog.port_capacity(target.get('deviceId'), target.get('mode'))
    if cap['count'] is not None and port > cap['count']:
        return (f'{_card_title(target)} has {cap["count"]} ports, so there '
                f'is no port {port} on it.')
    resolved_target = _resolved_card(target_id)
    ports = {p['number']: p for p in (resolved_target or {}).get('ports', [])}
    role = (ports.get(port) or {}).get('backsUp')
    if role and not (role.get('cardId') == card_id
                     and role.get('port') == number):
        desc = role.get('label') \
            or f'port {role.get("port")} on {role.get("cardTitle")}'
        return (f'Port {port} on {_card_title(target)} already backs up '
                f'{desc}.')
    card.setdefault('backupPorts', {})[str(number)] = {
        'cardId': target_id, 'port': port}
    return None


def _state(status=200):
    """Every mutating route answers with the whole resolved tree. A caller that
    only got back what it sent could not tell a stored edit from a dropped one,
    which is the failure mode the layer routes' allow-list keeps producing.

    The seq counter rides along so the CLIENT's project copy carries it into
    undo snapshots. Without it, undo's whole-project PUT dropped the counter,
    and a retired processor id was handed straight back out - delete proc3,
    add a machine, get proc3 again, then undo the delete and two machines
    both answer to it. Same lesson sync_next_group_seq records for groups,
    whose counter lives on the project for exactly this reason."""
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    return jsonify({
        'processors': _processors(),
        'resolved': catalog.resolve_all(_processors()),
        'next_processor_seq': app.current_project.get('next_processor_seq'),
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
    removed = [card.get('id') for _slot, card in _cards_of(proc)]
    _processors_mut().remove(proc)
    _prune_backup_refs(removed)
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
    outgoing = (slot.get('card') or {}).get('id')
    if not device_id:
        slot['card'] = None
        _prune_backup_refs([outgoing] if outgoing else [])
        log_event('processor_slot_clear', {'id': processor_id, 'slot': index})
        return _state()
    card = catalog.new_card(device_id, _next_seq(), data.get('name', ''))
    if not card:
        return jsonify({'error': f'Unknown device: {device_id}'}), 400
    slot['card'] = card
    # The outgoing card's redundancy links go with it - the new card in the
    # slot is different metal with a different id and (maybe) another count.
    _prune_backup_refs([outgoing] if outgoing else [])
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
    # The redundancy fields are validated, not allow-listed: a mode the
    # catalog does not know, a partner that cannot mirror this card, or a
    # vendor-fixed pairing are all refused with the reason, never stored.
    if 'redundancyMode' in data:
        why = _set_redundancy_mode(card, data.get('redundancyMode') or '')
        if why:
            return jsonify({'error': why}), 400
    if 'backupCardId' in data:
        why = _set_backup_card(card, card_id, data.get('backupCardId') or '')
        if why:
            return jsonify({'error': why}), 400
    changed = _apply(card, data, ('name', 'portLabelTemplate',
                                  'returnLabelTemplate', 'mode'))
    for key in ('redundancyMode', 'backupCardId'):
        if key in data:
            changed[key] = card.get(key)
    # A blank template is the ABSENCE of one, on either side. The primary
    # falls back to the built-in {name}-#, the return to the derived return
    # (derive_return_label) - rung two of its ladder stepping aside. Deleted rather than stored empty,
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
    derived return (derive_return_label: P1-1 back as R1-1, SR-1 back as
    SR-1R). Either field alone is a valid PUT; a PUT carrying
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
    if 'name' not in data and 'returnName' not in data \
            and 'backup' not in data:
        return jsonify({'error': 'name, returnName or backup is required'}), 400
    # `backup` names the port this one's manual-mode return comes back on -
    # {'cardId', 'port'}, same card or another - and null clears it. Sparse
    # on purpose: manual mode maps only the ports somebody named.
    if 'backup' in data:
        why = _set_port_backup(card, card_id, number, data.get('backup'))
        if why:
            return jsonify({'error': why}), 400
    changed = {'card': card_id, 'port': number}
    if 'name' in data:
        stored = catalog.set_port_name(card, number, data.get('name'))
        changed['named'] = bool(stored)
    if 'returnName' in data:
        stored = catalog.set_return_port_name(card, number,
                                              data.get('returnName'))
        changed['returnNamed'] = bool(stored)
    if 'backup' in data:
        changed['backup'] = (card.get('backupPorts') or {}).get(str(number))
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
