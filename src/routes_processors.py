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
import math

from flask import Blueprint, g, request, jsonify

import app
import processor_catalog as catalog
import port_assignment as assignment
from app import log_event, socketio

processors_bp = Blueprint('processors', __name__)


@processors_bp.before_request
def _note_fiber_in_use():
    # The fiber cables some link names as the request comes in, so _state
    # can prune the ones the request let go of - the last link off a TAC,
    # a box deleted with its links - and leave a cable made a moment ago
    # with no link yet alone (settle_fiber).
    g.fiber_used_before = catalog.fiber_cables_in_use(app.current_project)


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
    # A one-box unit's card goes by the unit's name (its one name slot,
    # 2026-09-24); a slot card by its own. card_display_name knows which.
    card_id = (card or {}).get('id')
    proc = next((p for p, c in _all_cards() if c.get('id') == card_id), None)
    return catalog.card_display_name(card, proc)


def _resolved_card(card_id):
    for rproc in catalog.resolve_all(_processors()):
        for slot in rproc.get('slots') or []:
            rcard = slot.get('card')
            if rcard and rcard['id'] == card_id:
                return rcard
    return None


def _port_numbers(card_id, cvt_id=None):
    """The sockets a card (or one of its boxes) resolves to right now -
    the range a snake or a port cable may name. Read off the resolved tree,
    never re-derived: a box's count is the trunk cap's answer, and a card's
    is its mode's."""
    rcard = _resolved_card(card_id) or {}
    if cvt_id is None:
        return [p['number'] for p in rcard.get('ports') or []]
    for box in rcard.get('cvts') or []:
        if box.get('id') == cvt_id:
            return [p['number'] for p in box.get('ports') or []]
    return []


def _take_cable_store(node, data, card_id, cvt_id=None):
    """Store a PUT's snakes / portCables on a card or box, or say why not.

    Validated, not allow-listed (the redundancy fields' rule): a socket the
    device does not have, a port in two snakes, a bad length or connector
    refuses the whole body with the reason and stores nothing.

    ``snakes`` is the LEGACY door - a snake is the show's now, formed
    through /api/snakes - kept because old undo snapshots and old clients
    still speak it, and because it says exactly what a device-scoped
    replacement means: every member THIS device has leaves the show's
    snakes, and the list given comes back in their place. The per-device
    key never survives the request; _migrate_snakes folds it in.
    """
    if 'snakes' not in data and 'portCables' not in data:
        return None
    ports = _port_numbers(card_id, cvt_id)
    why = catalog.check_cable_store(data, ports,
                                    'box' if cvt_id else 'card')
    if why:
        return why
    if 'snakes' in data:
        _drop_snake_members(('cvt', cvt_id) if cvt_id else ('card', card_id))
    catalog.apply_cable_store(node, data, ports, _next_seq)
    return None


def _drop_snake_members(device):
    """Take one device's sockets out of every show snake (an emptied snake
    goes with them) - the legacy device PUT's "these are my snakes now"."""
    kind, ident = device
    out = []
    for snake in catalog.show_snakes(app.current_project):
        members = [m for m in snake.get('members') or []
                   if not (m.get('kind') == kind and m.get('id') == ident)]
        if not members:
            continue
        snake['members'] = members
        out.append(snake)
    if out:
        app.current_project['snakes'] = out
    else:
        app.current_project.pop('snakes', None)


def _migrate_snakes():
    """Fold any per-device snakes into the show's list and re-home every
    member onto the device that delivers its socket. Run at the end of every
    mutating route (in _state), so a card that just lost its slot, a box
    that just went, or a legacy PUT all leave one consistent list."""
    catalog.migrate_device_snakes(app.current_project)


def _snake_devices():
    return catalog.snake_device_index(_processors())


def _find_snake(snake_id):
    return next((s for s in catalog.show_snakes(app.current_project)
                 if s.get('id') == snake_id), None)


def _prune_backup_refs(removed_ids):
    """Drop redundancy links that name a card which is no longer there.

    Same rule as a breakout box's backupOf on delete: left pointing at a
    dead id, the link would spring back to life the moment an id was ever
    reused - so it goes with the thing it named.
    """
    removed = set(removed_ids)
    if not removed:
        return
    # A backup box bound by hand to a box that went with those cards is
    # just a box again (settle_fiber also drops a binding whose backup
    # relation is gone, which covers the cards that stayed).
    boxes = {cvt.get('id') for _p, c in _all_cards()
             for cvt in c.get('cvts') or []}
    for _proc, card in _all_cards():
        for cvt in card.get('cvts') or []:
            if cvt.get('boundTo') and cvt['boundTo'] not in boxes:
                cvt.pop('boundTo', None)
    for _proc, card in _all_cards():
        if card.get('backupCardId') in removed:
            card.pop('backupCardId', None)
        entries = card.get('backupPorts') or {}
        for key in [k for k, v in entries.items()
                    if (v or {}).get('cardId') in removed]:
            entries.pop(key)
        if not entries:
            card.pop('backupPorts', None)


def _fixed_pairing_refusal(card):
    """The one sentence that turns away any stored shape on a card whose
    vendor fixes the pairing. Shared by the mode store and the whole-
    processor pairing, so the reason reads the same from either door."""
    device = catalog.get_device(card.get('deviceId')) or {}
    if ((device.get('redundancy') or {}).get('pairing')) == 'adjacent':
        return (f'{device.get("name", "This device")} pairs adjacent outputs '
                f'automatically - its pairing is a fact of the device, not a '
                f'mode.')
    return None


def _set_redundancy_mode(card, mode):
    """Store one card's redundancy mode, or refuse where the vendor fixed it.

    '1to1' is stored as ABSENCE - it is the default, and a stored copy of a
    default reads as a value nobody can tell from a choice (the template
    birth-stamp lesson). The stored 1to1 partner and manual picks survive a
    mode switch on purpose: they are choices somebody made, inert while
    another mode is active, and destroying them because the select was
    toggled to compare would be hostile.
    """
    why = _fixed_pairing_refusal(card)
    if why:
        return why
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
    why = _check_backup_card(card, card_id, backup_id)
    if why:
        return why
    card['backupCardId'] = backup_id
    return None


def _check_backup_card(card, card_id, backup_id):
    """Why `backup_id` cannot mirror `card` 1:1, or None where it can.

    Split from the store so the whole-processor pairing can run every
    slot's check BEFORE it writes a single one: a pairing that stored slot
    1 and then refused slot 2 would leave half a mirror behind, which is
    worse than none.
    """
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
    return None


def _proc_title(proc):
    device = catalog.get_device((proc or {}).get('deviceId')) or {}
    return ((proc or {}).get('name') or '').strip() \
        or device.get('name', (proc or {}).get('deviceId'))


def _derived_backup_processor(proc):
    """The processor that currently mirrors `proc` card for card, from the
    resolved view - the same derivation the panel reads - or None."""
    for rproc in catalog.resolve_all(_processors()):
        if rproc.get('id') == proc.get('id'):
            return rproc.get('backupProcessorId')
    return None


def _set_backup_processor(proc, partner_id):
    """Pair two processors whole, card for card, in ONE gesture - or undo it.

    The user's ruling (2026-09-04): "if you need to do processor redundancy
    i need to be able to set that." A whole-processor backup is nothing
    the cards do not already know how to be: it is every card of this
    processor pointed 1:1 at the partner's card in the same position, so
    that is exactly what is stored - no new key, and the view derives the
    pairing back from the cards (resolve_all). Card N mirrors card N in
    slot order; the two must have the SAME number of cards, and every
    pair must pass the SAME checks a single 1:1 pick passes (settled and
    equal port counts, not already consumed, no backup of a backup).
    All checks run first; the first failure names its slot and refuses
    the lot, and nothing is written.

    Clearing (an empty id) releases every card that pointed at the
    derived partner - the pairing the view was reporting - and touches no
    card pointed elsewhere.
    """
    mine = [(slot, card) for slot, card in _cards_of(proc)]
    if not partner_id:
        current = _derived_backup_processor(proc)
        partner = _find_processor(current) if current else None
        if not partner:
            return None
        theirs = {card.get('id') for _s, card in _cards_of(partner)}
        for _slot, card in mine:
            if card.get('backupCardId') in theirs:
                card.pop('backupCardId', None)
        return None
    if partner_id == proc.get('id'):
        return 'A processor cannot back itself.'
    partner = _find_processor(partner_id)
    if partner is None:
        return 'That processor is not in this project.'
    theirs = [(slot, card) for slot, card in _cards_of(partner)]
    if not mine:
        return f'{_proc_title(proc)} has no cards to mirror.'
    if len(mine) != len(theirs):
        def count(cards):
            return f'{len(cards)} card{"" if len(cards) == 1 else "s"}'
        return (f'{_proc_title(partner)} has {count(theirs)} and '
                f'{_proc_title(proc)} has {count(mine)} - a whole-processor '
                f'backup mirrors card for card, so the counts must match.')
    for (slot, card), (_pslot, pcard) in zip(mine, theirs):
        why = _fixed_pairing_refusal(card) \
            or _check_backup_card(card, card.get('id'), pcard.get('id'))
        if why:
            return f'Slot {slot.get("index", 0) + 1}: {why}'
    for (_slot, card), (_pslot, pcard) in zip(mine, theirs):
        # 1:1 is stored as absence (see _set_redundancy_mode); a card that
        # was sequential or manual a moment ago becomes a plain mirror.
        card.pop('redundancyMode', None)
        card['backupCardId'] = pcard.get('id')
    return None


def _set_cards_redundancy_mode(proc, mode):
    """Give EVERY card of `proc` the same redundancy mode, or refuse the lot.

    The bar behind the processor's gear speaks for the whole unit - "Per
    card" is every slot at 1:1, "Per port" is every slot at a port shape
    - because the user found the old one-select-per-slot surface "wayyy
    too busy" (2026-09-04). One request carries the level so one undo
    takes it back. Every card's refusal is gathered BEFORE any card is
    written: a chassis that stored slot 1 and then refused slot 2 would be
    left half at one level and half at another, and the bar could not
    say which. The first failure names its slot and nothing changes.

    Only the mode moves. A stored 1:1 partner or a manual pick survives
    underneath exactly as _set_redundancy_mode leaves it - "Per card"
    after a whole-unit pairing keeps the pairing, since that pairing IS
    every card's 1:1 pick.
    """
    if not mode or mode not in catalog.REDUNDANCY_MODES:
        return f'Unknown redundancy mode: {mode}'
    cards = list(_cards_of(proc))
    for slot, card in cards:
        why = _fixed_pairing_refusal(card)
        if why:
            return f'Slot {slot.get("index", 0) + 1}: {why}'
    for _slot, card in cards:
        _set_redundancy_mode(card, mode)
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


def _state(status=200, extra=None):
    """Every mutating route answers with the whole resolved tree. A caller that
    only got back what it sent could not tell a stored edit from a dropped one,
    which is the failure mode the layer routes' allow-list keeps producing.
    `extra` rides on top of the tree - a route with something to SAY about
    what it did (a box delete that dropped pins) puts its note there.

    The seq counter rides along so the CLIENT's project copy carries it into
    undo snapshots. Without it, undo's whole-project PUT dropped the counter,
    and a retired processor id was handed straight back out - delete proc3,
    add a machine, get proc3 again, then undo the delete and two machines
    both answer to it. Same lesson sync_next_group_seq records for groups,
    whose counter lives on the project for exactly this reason."""
    # Every mutating route ends here, so this is the one place the show's
    # snakes are settled against the tree that just changed: a legacy
    # device PUT folded in, a member re-homed onto the box that now
    # delivers its socket, a member of a deleted card dropped, an emptied
    # snake gone. Idempotent, so a route that changed nothing changes
    # nothing here either.
    _migrate_snakes()
    # ...and the fiber cables the same way: links that no longer hold go,
    # a backup binding nothing backs goes, an opticalCON whose box went
    # goes, and a cable the request left with no link goes.
    catalog.settle_fiber(app.current_project,
                         g.get('fiber_used_before'))
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    body = {
        'processors': _processors(),
        'resolved': catalog.resolve_all(_processors()),
        'next_processor_seq': app.current_project.get('next_processor_seq'),
        'dataCableConnectors': catalog.data_cable_connectors(),
        # The show's snakes ride the processor state: they hold sockets
        # from several devices, so the tray, the sheet and the paperwork
        # all read them beside the tree they point into.
        'snakes': catalog.resolved_show_snakes(app.current_project),
        # The show's fiber cables ride it for the same reason: a TAC is
        # shared by several boxes, on several processors.
        'fiberCables': catalog.resolved_fiber_cables(app.current_project),
    }
    if extra:
        body.update(extra)
    return jsonify(body), status


def _apply(node, data, keys):
    changed = {}
    for key in keys:
        if key in data:
            node[key] = data[key]
            changed[key] = data[key]
    return changed


@processors_bp.route('/api/processor-catalog', methods=['GET'])
def processor_catalog():
    """The catalog file, with the platform wall stated per device: what the
    Add-processor picker and the slot-card picker filter on, so the client
    never holds a copy of port_assignment's tables.

    `platforms` is accepted_platforms(id) - the list a card summary carries
    and a drop is refused on - and `slotPlatforms` is a chassis's cards'
    union (slot_platforms). Both are sorted lists, None for unrestricted.
    `platformAliases` folds a retired Processing token the way the resolve
    does. The cached catalog is copied, never written."""
    data = dict(catalog.load_catalog())
    devices = []
    for device in data.get('devices', []):
        accepted = assignment.accepted_platforms(device.get('id'))
        slots = assignment.slot_platforms(device.get('id'))
        devices.append(dict(
            device,
            platforms=sorted(accepted) if accepted is not None else None,
            slotPlatforms=sorted(slots) if slots is not None else None,
        ))
    data['devices'] = devices
    data['platformAliases'] = assignment.platform_aliases()
    return jsonify(data)


@processors_bp.route('/api/processors', methods=['GET'])
def get_processors():
    return jsonify({
        'processors': _processors(),
        'resolved': catalog.resolve_all(_processors()),
        # The connectors a data cable can be typed as (catalog
        # DATA_CABLE_CONNECTORS) - served, so the sheet's select and the
        # server's refusals name the same list.
        'dataCableConnectors': catalog.data_cable_connectors(),
        'snakes': catalog.resolved_show_snakes(app.current_project),
        'fiberCables': catalog.resolved_fiber_cables(app.current_project),
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


@processors_bp.route('/api/processors/order', methods=['PUT'])
def set_processor_order():
    """Reorder the processors (2026-09-09: "also being able to drag them
    around and reorder them would be nice too").

    The body is the whole order - a PERMUTATION of the ids that exist, so a
    stale tray cannot silently drop or duplicate a machine; anything else
    refuses with the reason and stores nothing. Order is the only thing
    that moves: the records themselves are re-seated, never rewritten, and
    everything that reads processor order (the tray, the pull list's
    hardware order, the binder's 'data' screen order, _bFirstPortKey's
    processor index) follows from this one array.

    A static rule, so it is matched ahead of /api/processors/<id>.
    """
    data = request.json or {}
    ids = data.get('ids')
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return jsonify({'error': 'ids must be a list of processor ids.'}), 400
    have = [p.get('id') for p in _processors()]
    if sorted(ids) != sorted(have):
        return jsonify({
            'error': 'ids must name every processor exactly once - '
                     f'{len(have)} on file, {len(ids)} given.'}), 400
    by_id = {p.get('id'): p for p in _processors()}
    _processors_mut()[:] = [by_id[i] for i in ids]
    log_event('processor_order', {'ids': ids})
    return _state()


@processors_bp.route('/api/processors/<processor_id>', methods=['PUT'])
def update_processor(processor_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    data = request.json or {}
    # The whole-processor pairing and the whole-unit level are validated,
    # not allow-listed, like the card's redundancy fields: any slot that
    # cannot mirror (or cannot take the mode) refuses the whole gesture
    # with its reason, and nothing is stored. The level rides in the same
    # body as `redundancy: true`, so the bar's "Per card" / "Per port" is
    # ONE request and ONE undo step.
    if 'cardsRedundancyMode' in data:
        why = _set_cards_redundancy_mode(proc, data.get('cardsRedundancyMode'))
        if why:
            return jsonify({'error': why}), 400
    if 'backupProcessorId' in data:
        why = _set_backup_processor(proc, data.get('backupProcessorId') or '')
        if why:
            return jsonify({'error': why}), 400
    changed = _apply(proc, data, ('name', 'mode', 'redundancy'))
    if 'backupProcessorId' in data:
        changed['backupProcessorId'] = data.get('backupProcessorId') or None
    if 'cardsRedundancyMode' in data:
        changed['cardsRedundancyMode'] = data.get('cardsRedundancyMode')
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
    # Data snakes and port home runs (2026-09-06): the card's own stores,
    # validated against the sockets it resolves to, before anything else in
    # the body is written - a refused cable leaves the name and mode alone.
    why = _take_cable_store(card, data, card_id)
    if why:
        return jsonify({'error': why}), 400
    changed = _apply(card, data, ('name', 'portLabelTemplate',
                                  'returnLabelTemplate', 'mode'))
    for key in ('redundancyMode', 'backupCardId', 'snakes', 'portCables'):
        if key in data:
            changed[key] = card.get(key)
    if 'mode' in data:
        # A mode can halve the card (H_4xfiber independent → copy/backup):
        # snakes and cables on sockets that no longer exist go with them,
        # and so do the boxes' - a box's span follows the card's count.
        catalog.prune_cable_store(card, _port_numbers(card_id))
        for cvt in card.get('cvts') or []:
            catalog.prune_cable_store(
                cvt, _port_numbers(card_id, cvt.get('id')))
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


def _take_fiber(cvt, data):
    """Validate and store a breakout box's fiber fields from a PUT body:
    `fiberType` (a string; blank clears) and `fiberFt` (a finite number of
    feet, 0 or more; null / blank clears). Returns the refusal, or None."""
    if 'fiberType' in data:
        value = data.get('fiberType')
        if value is not None and not isinstance(value, str):
            return 'Fiber type must be text'
        text = (value or '').strip()
        if text:
            cvt['fiberType'] = text
        else:
            cvt.pop('fiberType', None)
    if 'fiberFt' in data:
        value = data.get('fiberFt')
        if value is None or (isinstance(value, str) and not value.strip()):
            cvt.pop('fiberFt', None)
        else:
            if isinstance(value, bool):
                return 'Fiber length must be a number of feet, 0 or more'
            try:
                ft = float(value)
            except (TypeError, ValueError):
                return 'Fiber length must be a number of feet, 0 or more'
            if not math.isfinite(ft) or ft < 0:
                return 'Fiber length must be a number of feet, 0 or more'
            if ft == 0:
                cvt.pop('fiberFt', None)
            else:
                cvt['fiberFt'] = int(ft) if ft == int(ft) else ft
    return None


@processors_bp.route('/api/processors/<processor_id>/cvts/<cvt_id>', methods=['PUT'])
def update_cvt(processor_id, cvt_id):
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    card, cvt = _find_cvt(proc, cvt_id)
    if not cvt:
        return jsonify({'error': 'Breakout box not found'}), 404
    data = request.json or {}
    # The box's snakes and port home runs, against the sockets IT delivers
    # (2026-09-06). Same door as the card's, same refusals.
    why = _take_cable_store(cvt, data, card.get('id'), cvt_id)
    if why:
        return jsonify({'error': why}), 400
    # The box's fiber trunk (2026-09-07: "we need to add fiber types when
    # cvt's or similar are used"): what the fiber is (free text, the GEAR
    # LIST's words offered) and how long its home run is, in feet. Both are
    # facts about THIS box, so they live on its record and ride resolve_card
    # out to the dock, the pull list and the binder. A length must be a
    # number of feet, 0 or more; blank / null clears either field.
    why = _take_fiber(cvt, data)
    if why:
        return jsonify({'error': why}), 400
    # Where the box physically sits (2026-09-07: "We need to be able to put
    # CVT's or processor's at beach locations so they can be accounted for
    # on the pull sheets"). Free text, the same field a distro carries;
    # blank / null clears it and leaves no key behind. The pull list files
    # every row the box produces - the data cables of the ports it
    # delivers, its fiber trunk, its own "CVT4K-S EA" line - under this
    # name, matched case-blind against the screen groups.
    if 'location' in data:
        value = data.get('location')
        if value is not None and not isinstance(value, str):
            return jsonify({'error': 'Location must be text'}), 400
        text = (value or '').strip()
        if text:
            cvt['location'] = text
        else:
            cvt.pop('location', None)
    # Beaches (2026-09-08): the box sits on one of the project's beaches -
    # picked, never typed. null / blank clears and leaves no key; an id
    # that names no beach is refused. Setting a beach retires a typed
    # location left on the record (the beach is where the box is now).
    if 'beachId' in data:
        value = data.get('beachId')
        if value is None or value == '':
            cvt.pop('beachId', None)
        elif not isinstance(value, str) or not app._find_beach(app.current_project, value):
            return jsonify({'error': 'Unknown beach'}), 400
        else:
            cvt['beachId'] = value
            cvt.pop('location', None)
    changed = _apply(cvt, data, ('name', 'portLabelTemplate',
                                 'returnLabelTemplate', 'mode'))
    for key in ('fiberType', 'fiberFt', 'location', 'beachId'):
        if key in data:
            changed[key] = cvt.get(key)
    for key in ('snakes', 'portCables'):
        if key in data:
            changed[key] = cvt.get(key)
    if 'mode' in data:
        catalog.prune_cable_store(cvt, _port_numbers(card.get('id'), cvt_id))
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
    # What the box was called and which sockets it delivered, read off the
    # resolved tree BEFORE it goes - the title (trunk letter included) is
    # what the reply calls it, and the span is what the pins below pointed
    # into.
    rcard = _resolved_card(card.get('id')) or {}
    rbox = next((b for b in rcard.get('cvts') or [] if b.get('id') == cvt_id),
                {})
    box_title = rbox.get('displayTitle') or rbox.get('name') \
        or rbox.get('deviceName') or cvt.get('deviceId') or cvt_id
    # The survivors keep their trunks (hold_box_trunks): on a box-fed
    # device the box IS the trunk's sockets, so C must not slide down onto
    # B's trunk when B goes - B's sockets are gone, C's stay 21-30, and a
    # box added later takes the empty trunk.
    if rcard.get('boxFed'):
        catalog.hold_box_trunks(card, rcard)
    card['cvts'].remove(cvt)
    # A backup whose primary is gone is just a box again. Left pointing at a
    # deleted id, it would jump back onto a backup trunk the moment an id was
    # ever reused - so the link goes with the thing it named.
    for other in card['cvts']:
        if other.get('backupOf') == cvt_id:
            other.pop('backupOf', None)
            other.pop('unbound', None)
    # A box bound to it by hand - a backup processor's box that was this
    # same metal - is a box of its own again. The box's links went with its
    # record; the opticalCONs it owned and the TACs it was the last user of
    # go in _state (settle_fiber).
    for _p, other_card in _all_cards():
        for other in other_card.get('cvts') or []:
            if other.get('boundTo') == cvt_id:
                other.pop('boundTo', None)
    # ON A BOX-FED DEVICE THE BOX'S SOCKETS GO WITH IT. The SX40 and the
    # HELIOS Standard have no ports outside a box (the 2026-09-24 ruling:
    # "SX40's can't use ports outside of an XD box"), so once the box is
    # gone resolve_card lists only the surviving boxes' sockets, and every
    # pin that pointed into the removed span is dropped with it - those
    # screen ports are unplaced again, and the reply says which, so the
    # tray can say so too. Undo (the whole-project PUT) brings the box and
    # its pins back together. A card that is not box-fed keeps its own
    # ports, so nothing of its is pruned.
    dropped = []
    if rcard.get('boxFed'):
        dropped = assignment.prune_pins_off_sockets(
            app.current_project, card.get('id'), _port_numbers(card.get('id')))
    log_event('processor_cvt_delete', {
        'id': cvt_id, 'box': box_title,
        'droppedPins': [{'layerId': p['layerId'], 'index': p['index'],
                         'port': p['port']} for p in dropped]})
    extra = None
    if dropped:
        extra = {
            'note': _box_removed_note(box_title, dropped),
            # The pruned state rides the reply so the client's project copy
            # (and the undo snapshot it takes off it) carries the pins as
            # the server now holds them, not the ones it had a moment ago.
            'portAssignments': app.current_project.get(assignment.STATE_KEY),
        }
    return _state(extra=extra)


def _box_removed_note(box_title, dropped):
    """'Removed box Tessera XD B - 3 ports of LEFT are unplaced again':
    one clause per screen, in the order their pins came off, each screen
    called by the name on its layer."""
    names = {str(l.get('id')): (l.get('name') or f'Screen {l.get("id")}')
             for l in app.current_project.get('layers') or []
             if isinstance(l, dict) and l.get('id') is not None}
    counts = {}
    for pin in dropped:
        counts[pin['layerId']] = counts.get(pin['layerId'], 0) + 1
    parts = [f'{n} port{"" if n == 1 else "s"} of '
             f'{names.get(layer_id, f"Screen {layer_id}")}'
             for layer_id, n in counts.items()]
    verb = 'is' if len(dropped) == 1 else 'are'
    return f'Removed box {box_title} - {_and_list(parts)} {verb} unplaced again'


def _and_list(names):
    if len(names) <= 2:
        return ' and '.join(names)
    return f'{", ".join(names[:-1])} and {names[-1]}'


# ── Show snakes ───────────────────────────────────────────────────────────
#
# "Any sockets, any device" (2026-09-09). A snake holds members - (device,
# socket) pairs - and lives on the project, so one loom can carry a card's
# A-1..A-4 and its backup box's B-1..B-4 together. The rules are the cable
# stores': validated, never allow-listed, every refusal names its reason and
# stores nothing; every answer is the whole resolved state, so one gesture is
# one request and one undo step.


def _take_snake_members(data, snake_id=None):
    """Check a body's `members` against the tree, or say why not."""
    devices, _delivers = _snake_devices()
    taken = catalog.snake_sockets_taken(app.current_project, snake_id)
    return catalog.check_snake_members(data.get('members'), devices, taken)


def _check_snake_cable(data):
    """The snake's own length and plug, checked the way a port cable is."""
    if 'ft' in data and data['ft'] not in (None, ''):
        try:
            ft = float(data['ft'])
        except (TypeError, ValueError):
            return 'ft must be a number of feet.'
        if ft != ft or ft < 0 or ft in (float('inf'), float('-inf')):
            return 'ft must be a non-negative number.'
    conn = data.get('connector')
    ids = catalog.data_cable_connector_ids()
    if 'connector' in data and conn not in (None, '') and conn not in ids:
        return (f'unknown connector {conn!r} - one of '
                f'{", ".join(sorted(ids))}, or null to follow the port.')
    if 'name' in data and data.get('name') is not None \
            and not isinstance(data.get('name'), str):
        return 'name must be text.'
    return None


@processors_bp.route('/api/snakes', methods=['POST'])
def add_snake():
    """Form one snake of the members given - sockets from as many cards and
    boxes as the gesture gathered."""
    data = request.json or {}
    why = _check_snake_cable(data) or _take_snake_members(data)
    if why:
        return jsonify({'error': why}), 400
    devices, _delivers = _snake_devices()
    snake = catalog.store_show_snake(app.current_project, data, devices,
                                     _next_seq)
    log_event('snake_add', {'id': snake['id'],
                            'members': len(snake['members'])})
    return _state(201)


@processors_bp.route('/api/snakes/loosen', methods=['POST'])
def loosen_snake_members():
    """Take the members given out of whatever snakes hold them, in ONE
    request: the sheet's "Unsnake" can tick sockets on several devices and
    so touch several snakes, and one gesture has to be one undo step. An
    emptied snake goes with its last member. A member no snake holds is
    quietly nothing - unsnaking a loose socket is not an error.

    A static rule, so it is matched ahead of /api/snakes/<snake_id>.
    """
    data = request.json or {}
    members = data.get('members')
    if not isinstance(members, list):
        return jsonify({'error': 'members must be a list of '
                                 '{kind, id, socket}.'}), 400
    drop = set()
    for raw in members:
        if not isinstance(raw, dict):
            continue
        try:
            drop.add((raw.get('kind'), raw.get('id'), int(raw.get('socket'))))
        except (TypeError, ValueError):
            continue
    out = []
    for snake in catalog.show_snakes(app.current_project):
        kept = [m for m in snake.get('members') or []
                if (m.get('kind'), m.get('id'), m.get('socket')) not in drop]
        if not kept:
            continue
        snake['members'] = kept
        out.append(snake)
    if out:
        app.current_project['snakes'] = out
    else:
        app.current_project.pop('snakes', None)
    log_event('snake_loosen', {'members': len(drop)})
    return _state()


@processors_bp.route('/api/snakes/<snake_id>', methods=['PUT'])
def update_snake(snake_id):
    """Rename / re-length / re-plug one snake, and set its members where the
    body carries them. One snake, wherever it was edited from."""
    snake = _find_snake(snake_id)
    if not snake:
        return jsonify({'error': 'Snake not found'}), 404
    data = request.json or {}
    why = _check_snake_cable(data)
    if not why and 'members' in data:
        why = _take_snake_members(data, snake_id)
    if why:
        return jsonify({'error': why}), 400
    devices, _delivers = _snake_devices()
    catalog.store_show_snake(app.current_project, data, devices, _next_seq,
                             snake)
    log_event('snake_update', {'id': snake_id, 'changed': list(data)})
    return _state()


@processors_bp.route('/api/snakes/<snake_id>/members', methods=['PUT'])
def set_snake_members(snake_id):
    """The whole membership of one snake at once - the bulk door the sheet's
    tick + Snake and the tray's sweep both write through when they are
    adding to a snake that already exists."""
    snake = _find_snake(snake_id)
    if not snake:
        return jsonify({'error': 'Snake not found'}), 404
    data = request.json or {}
    why = _take_snake_members(data, snake_id)
    if why:
        return jsonify({'error': why}), 400
    devices, _delivers = _snake_devices()
    catalog.store_show_snake(app.current_project, {'members':
                                                   data.get('members')},
                             devices, _next_seq, snake)
    log_event('snake_members', {'id': snake_id,
                                'members': len(snake['members'])})
    return _state()


@processors_bp.route('/api/snakes/<snake_id>', methods=['DELETE'])
def delete_snake(snake_id):
    """Unsnake the whole loom: the sockets stay where they are, and each
    keeps the portCables entry it had - what was its extension off the
    snake reads as its own home run again."""
    snake = _find_snake(snake_id)
    if not snake:
        return jsonify({'error': 'Snake not found'}), 404
    app.current_project['snakes'] = [
        s for s in catalog.show_snakes(app.current_project)
        if s.get('id') != snake_id]
    if not app.current_project['snakes']:
        app.current_project.pop('snakes', None)
    log_event('snake_delete', {'id': snake_id})
    return _state()


# ── Fiber cables ──────────────────────────────────────────────────────────
#
# TAC, MTP and opticalCON cables on the breakout boxes (2026-09-25; the
# model is processor_catalog's fiber-cable section). A cable lives on the
# show - a TAC is shared by several boxes' links - and a box's links live on
# its record. Every refusal names its reason and stores nothing; every
# answer is the whole resolved state, so one gesture is one request and one
# undo step.


def _fiber_boxes():
    return catalog.fiber_box_index(_processors())


def _fiber_cables_by_id():
    return {c.get('id'): c for c in catalog.show_fiber_cables(
        app.current_project) if isinstance(c, dict)}


def _find_fiber_cable(cable_id):
    return _fiber_cables_by_id().get(cable_id)


def _fiber_link_strands(boxes, cables, box_id, key, cable_id, strands):
    """The strands a link will take - the ones given, else the cable's next
    free ones - or the refusal. Returns (strands, why)."""
    why = catalog.check_fiber_link(boxes, cables, box_id, key, cable_id,
                                   None)
    if why:
        return None, why
    if strands is None:
        need = catalog.fiber_link_need(boxes[box_id]['raw'])
        taken = catalog.fiber_strands_taken(boxes, (box_id, key))
        cable = cables[cable_id]
        strands = catalog.fiber_next_free(cable, taken, need)
        if strands is None:
            return None, (f'{cable.get("name") or "That cable"} has no '
                          f'{need} free strand{"" if need == 1 else "s"} '
                          f'left.')
    why = catalog.check_fiber_link(boxes, cables, box_id, key, cable_id,
                                   strands)
    return (None, why) if why else (list(strands), None)


def _set_fiber_link(raw, key, cable_id, strands):
    raw.setdefault('fiberLinks', {})[key] = {'cable': cable_id,
                                            'strands': list(strands)}


@processors_bp.route('/api/fiber-cables', methods=['POST'])
def add_fiber_cable():
    """Make one cable - a TAC or an MTP of any strand count, or a box's own
    opticalCON DUO / QUAD - and, where the body carries `link`
    ({boxId, key, strands?}), put that link on it in the same request (the
    Fiber section's "New TAC…" is one gesture, one undo step)."""
    data = request.json or {}
    why = catalog.check_fiber_cable(data)
    if why:
        return jsonify({'error': why}), 400
    link = data.get('link')
    if link is not None and (not isinstance(link, dict)
                             or not isinstance(link.get('boxId'), str)
                             or not isinstance(link.get('key'), str)):
        return jsonify({'error': 'link must be {boxId, key, strands?}.'}), 400
    boxes = _fiber_boxes()
    kind = data.get('kind')
    rec = dict(data)
    if kind in catalog.FIBER_KIND_FIBERS:
        owner = data.get('ownerBoxId') or (link or {}).get('boxId')
        entry = boxes.get(owner)
        if entry is None:
            return jsonify({'error': 'An opticalCON belongs to one box - '
                                     'name it (ownerBoxId).'}), 400
        if entry['res'].get('boundTo'):
            return jsonify({'error': (
                f'{catalog.fiber_box_title(entry)} is bound to '
                f'{entry["res"].get("boundTitle")} - its fiber is set '
                f'there.')}), 400
        rec['ownerBoxId'] = owner
    cable = catalog.store_fiber_cable(app.current_project, rec, _next_seq)
    if link is not None:
        strands, why = _fiber_link_strands(
            boxes, _fiber_cables_by_id(), link['boxId'], link['key'],
            cable['id'], link.get('strands'))
        if why:
            # Nothing is stored on a refusal: the cable made a moment ago
            # goes back out.
            left = [c for c in catalog.show_fiber_cables(app.current_project)
                    if c is not cable]
            if left:
                app.current_project['fiberCables'] = left
            else:
                app.current_project.pop('fiberCables', None)
            return jsonify({'error': why}), 400
        _set_fiber_link(boxes[link['boxId']]['raw'], link['key'],
                        cable['id'], strands)
    log_event('fiber_cable_add', {'id': cable['id'], 'kind': kind,
                                  'link': link})
    return _state(201)


@processors_bp.route('/api/fiber-cables/<cable_id>', methods=['PUT'])
def update_fiber_cable(cable_id):
    """Rename / re-count / re-length one cable, pick its ends, its labels,
    its sub-units, or rename one strand ({strandName: {strand, name}}, a
    blank name handing the strand back to its color)."""
    cable = _find_fiber_cable(cable_id)
    if not cable:
        return jsonify({'error': 'Fiber cable not found'}), 404
    data = request.json or {}
    boxes = _fiber_boxes()
    used = max([s for (cid, s) in catalog.fiber_strands_taken(boxes)
                if cid == cable_id] or [0])
    why = catalog.check_fiber_cable(data, cable, used)
    if why:
        return jsonify({'error': why}), 400
    catalog.store_fiber_cable(app.current_project, data, _next_seq, cable)
    log_event('fiber_cable_update', {'id': cable_id, 'changed': list(data)})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cvts/<cvt_id>/fiber-links/<key>',
                     methods=['PUT'])
def set_fiber_link(processor_id, cvt_id, key):
    """Set or clear one of a box's links: {cable, strands?}, or
    {cable: null} to clear. With no strands the cable's next free ones are
    taken; a backup link given no cable takes its primary link's (the
    default the owner asked for: the primary's TAC at the next free
    strands)."""
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    _card, cvt = _find_cvt(proc, cvt_id)
    if not cvt:
        return jsonify({'error': 'Breakout box not found'}), 404
    data = request.json or {}
    boxes = _fiber_boxes()
    entry = boxes.get(cvt_id)
    if 'cable' in data and not data.get('cable'):
        links = cvt.get('fiberLinks') or {}
        if key in links:
            links.pop(key)
            if not links:
                cvt.pop('fiberLinks', None)
        log_event('fiber_link_clear', {'box': cvt_id, 'key': key})
        return _state()
    cable_id = data.get('cable')
    if 'cable' not in data and key.startswith('b'):
        primary = catalog.resolved_fiber_links(cvt).get('p' + key[1:])
        if not primary:
            return jsonify({'error': (
                f'Pick a cable for {catalog.fiber_link_title(key)} - '
                f'{catalog.fiber_link_title("p" + key[1:])} has none to '
                f'follow.')}), 400
        cable_id = primary['cable']
    if not isinstance(cable_id, str):
        return jsonify({'error': 'cable must be a fiber cable id, or null '
                                 'to clear the link.'}), 400
    strands, why = _fiber_link_strands(boxes, _fiber_cables_by_id(), cvt_id,
                                       key, cable_id, data.get('strands'))
    if why:
        return jsonify({'error': why}), 400
    _set_fiber_link(entry['raw'], key, cable_id, strands)
    log_event('fiber_link_set', {'box': cvt_id, 'key': key,
                                 'cable': cable_id, 'strands': strands})
    return _state()


@processors_bp.route('/api/processors/<processor_id>/cvts/<cvt_id>/fiber',
                     methods=['PUT'])
def update_box_fiber(processor_id, cvt_id):
    """A box's fiber switches: `bidi` (NovaStar and Megapixel boxes only;
    re-fits its links), `unbound` (a same-card backup record let go of, or
    taken back by, its primary) and `boundTo` (a backup processor's box
    named as the same metal as one of the boxes it backs up; null clears).
    Everything is checked before anything is written."""
    proc = _find_processor(processor_id)
    if not proc:
        return jsonify({'error': 'Processor not found'}), 404
    _card, cvt = _find_cvt(proc, cvt_id)
    if not cvt:
        return jsonify({'error': 'Breakout box not found'}), 404
    data = request.json or {}
    boxes = _fiber_boxes()
    entry = boxes.get(cvt_id)
    res = entry['res']
    title = catalog.fiber_box_title(entry)
    for field in ('bidi', 'unbound'):
        if field in data and not isinstance(data[field], bool):
            return jsonify({'error': f'{field} must be true or false.'}), 400
    if 'bidi' in data:
        if data['bidi'] and not res.get('bidiAllowed'):
            vendor = res.get('vendor') or 'this vendor'
            return jsonify({'error': (
                f'{res.get("deviceName") or title} is a {vendor} box - BiDi '
                f'is offered on NovaStar and Megapixel boxes only.')}), 400
        if res.get('boundTo'):
            return jsonify({'error': (
                f'{title} is bound to {res.get("boundTitle")} - its fiber '
                f'is set there.')}), 400
    if 'unbound' in data and not res.get('backupOf'):
        return jsonify({'error': (
            f'{title} backs up no box on its card - there is nothing to '
            f'unbind.')}), 400
    target = data.get('boundTo') if 'boundTo' in data else None
    if target:
        if res.get('backupOf'):
            return jsonify({'error': (
                f'{title} backs up a box on its own card, so it is bound '
                f'automatically - unbind it there instead.')}), 400
        targets = res.get('fiberBindTargets')
        if targets is None:
            return jsonify({'error': (
                f'{title} is not on a card that backs up another processor '
                f'- only such a box is bound by hand.')}), 400
        if target not in [t['id'] for t in targets]:
            return jsonify({'error': (
                f'{title} can be bound to a box of the processor it backs '
                f'up that is not bound already.')}), 400
    if 'bidi' in data and bool(cvt.get('bidi')) != data['bidi']:
        if data['bidi']:
            cvt['bidi'] = True
        else:
            cvt.pop('bidi', None)
        catalog.refit_fiber_bidi(boxes, _fiber_cables_by_id(), cvt_id,
                                 data['bidi'])
    if 'unbound' in data:
        if data['unbound']:
            cvt['unbound'] = True
        else:
            cvt.pop('unbound', None)
    if 'boundTo' in data:
        if target:
            cvt['boundTo'] = target
        else:
            cvt.pop('boundTo', None)
    log_event('box_fiber_update', {'id': cvt_id, 'changed': list(data)})
    return _state()
