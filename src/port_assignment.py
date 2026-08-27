"""Which sending-card port each screen's ports land on.

processor_catalog.py says what ports EXIST. This module says who has them. The
two are deliberately separate: a card's port count is a fact about hardware and
never changes, while an assignment is a decision someone made about a show and
changes all week.

The one rule that shapes everything below is that THE APP DETECTS AND OFFERS,
IT NEVER SILENTLY REARRANGES. By the time a numbering is wrong, cable has
usually been built to it - looms are made up and labelled off the drawing days
before anything is hung - so an app that quietly renumbered to fix a clash
would hand back a drawing that no longer matches the truck. Every problem this
module can find is therefore reported as an issue with an OFFER attached, and
the offer only runs when a person asks for it.

THE ALLOCATION RULE, in full, because everything else is a consequence of it:

    Screens are taken in the caller's order, which is project layer order.
    Pins are placed first and nothing may move them. Then each screen's
    remaining ports go, as one run, onto the FIRST card - processors in order,
    slots in order - with enough free ports for ALL of them; failing that, onto
    the first card with any free port at all. Within that card they take the
    lowest-numbered free ports, ascending, in the screen's own port order.
    Whatever does not fit is left unplaced and reported.

So six ports take 1-6 and the next screen starts at 7, which is the behaviour
this was asked for by name.

Four consequences are worth stating outright, because each one looks like a bug
until you know it is the point:

* TWO PINS ON ONE PORT BOTH STAY. A collision is reported, both screens keep
  their claim and both draw in red. Bumping the loser would be the silent
  renumber.
* A SCREEN'S PORTS NEVER SPAN TWO CARDS BY THEMSELVES. Ports that do not fit
  are left UNPLACED and reported, because a screen is cabled as one run and
  splitting one across two cards is a decision, not a rounding. A person may
  still make that decision - place_overflow takes the tail somewhere else,
  place_port takes one socket anywhere at all - and both say so when they do.
* AUTO WORKS AROUND PINS, WHICH CAN SPLIT A RUN. A pin sitting at port 3 makes
  the next screen take 1, 2, 4, 5 - a gap in the middle of a run. That is worse
  cabling than a clean block, so the block move exists to get out of it, but it
  is honest about where the ports actually are in the meantime.
* AUTO PORTS RE-PACK, AND THAT IS NOT THE SILENT REARRANGEMENT. An auto port is
  arithmetic, recomputed from nothing every time, so moving one screen slides
  another screen's auto ports down into the gap - exactly as deleting a screen
  would. The way to hold a numbering is to pin it; that is what pinning is for,
  and every port says PINNED or auto on the page before anything is moved.
  What the rule forbids is the app fixing a problem it found by itself.

Port counts come in from the caller, never from here. The maths for "how many
ports does this screen need" lives in getLayerPortsRequired / calculate-
PortAssignments on the client and is subtle enough already (custom flow, ports
that cross into a group peer, Low Latency derating); a second implementation
would agree in the office and disagree on a wall.
"""
import processor_catalog as catalog

STATE_KEY = 'port_assignments'


def new_state():
    """Auto-numbering is on until someone turns it off. A project that has
    never been touched here must number itself, or the panel opens on a wall of
    blanks and every screen needs a manual decision before it says anything."""
    return {'auto': True, 'pins': []}


# ── The cards ports can land on ───────────────────────────────────────────

def cards_in(processors):
    """Every card in the project, in the order the panel draws them.

    The order is load-bearing rather than cosmetic: it is the order auto-
    numbering fills cards in, so it has to be the order someone reads down the
    Processors panel - processor by processor, slot 1 downward - or the
    numbering appears to come from nowhere.
    """
    out = []
    for proc in catalog.resolve_all(processors):
        for slot in proc.get('slots') or []:
            card = slot.get('card')
            if not card:
                continue
            # The ports auto may hand out are the ones the card really has, not
            # the ones it enumerates. A card over its ceiling still lists the
            # ports past it - five CVT10s on a 32-port card is 40 - and those
            # already draw in red as a drawing mistake. Handing one out here
            # would promote that mistake into a cable order.
            out.append({
                'processorId': proc['id'],
                'processorName': proc['name'] or proc['deviceName'],
                'cardId': card['id'],
                'name': card['name'] or '',
                'deviceName': card['deviceName'],
                'slot': slot.get('index'),
                'capacity': card['ceiling'] if card['ceilingKnown'] else None,
                'capacityKnown': card['ceilingKnown'],
                'capacityReason': card['ceilingReason'],
                # Allocation is planned against the ports the CARD has, not
                # against how many of them the boxes currently on it deliver -
                # a half-patched card is a patching job someone has not
                # finished, and the ports are still coming. The one case that
                # is not is carried through here: every OPT spoken for and the
                # boxes still short of the ceiling, which is a wall planned
                # onto ports that no box will ever hand out.
                'shortfall': card.get('shortfall'),
                'labels': {p['number']: p['label'] for p in card['ports']},
                # Both ends of every socket, resolved once in resolve_card.
                # The return rides beside the primary so the canvas indexes
                # them from the same resolution instead of re-deriving one.
                'returnLabels': {p['number']: p['returnLabel']
                                 for p in card['ports']},
                # The number written beside each socket: the box's own 1..N
                # where a box delivers it (the 2026-08-27 silkscreen ruling),
                # the card-wide number where none does. Every message that
                # names a bare socket speaks THIS number - the card-wide one
                # stays the bookkeeping key and nothing more.
                'localNumbers': {p['number']: p['localNumber']
                                 for p in card['ports']},
                # Which box delivers each socket, by the box's display name
                # (its typed name, or model + trunk letter - resolve_card's
                # displayTitle). A bare local number only means something
                # beside its box's name, so a message naming an unlabeled
                # box-owned socket says both.
                'boxTitles': {
                    p['number']: next(
                        (c.get('displayTitle')
                         for c in card.get('cvts') or []
                         if c['id'] == p['cvtId']), None)
                    for p in card['ports'] if p.get('cvtId')},
                # Ports consumed as another main's return - the even half of
                # a sequential card, every port of a 1to1 backup unit, a
                # manual pick. Resolved with the labels above and carried
                # whole, because a backing port is CLAIMED BY ROLE: not free
                # to auto, refused to a hand placement, and the refusal has
                # to say which main it returns.
                'backupRoles': {p['number']: p['backsUp']
                                for p in card['ports'] if p.get('backsUp')},
            })
    return out


def _card_title(card):
    """What to call a card in a message. The name a person gave it wins, the
    same way it wins for a port label - it is what is written on the case."""
    if card['name']:
        return card['name']
    if card['processorName']:
        return f"{card['processorName']} slot {(card['slot'] or 0) + 1}"
    return card['deviceName']


def _port_title(card, port):
    """How a message names ONE card port. The label the catalog derived wins
    where there is one, because it is what is silkscreened beside the socket
    the tech is standing in front of; a bare number is what is left when
    nothing upstream has been named yet."""
    label = (card.get('labels') or {}).get(port)
    title = _card_title(card)
    if not label:
        # A bare number is the LOCAL one - the number silkscreened beside
        # the socket (a box's own 1..N behind a box). The card-wide ordinal
        # is a key, not a thing anyone can read off metal - and since every
        # box counts from 1, the box's name rides along or the number names
        # four different sockets.
        spoken = (card.get('localNumbers') or {}).get(port, port)
        box = (card.get('boxTitles') or {}).get(port)
        where = f'{title} {box}' if box else title
        return f'{where} port {spoken}'
    # A label is usually built out of the card's own name - the template is
    # {name}-# - so naming both would read "SR SR-1". Where it is not, because
    # a box in front of the card named it or somebody typed it, both halves are
    # what it takes to find the socket.
    return label if label.startswith(title) else f'{title} {label}'


# ── Inputs ────────────────────────────────────────────────────────────────

def _clean_screens(screens):
    """Screens as the caller sent them, minus anything that cannot hold a port.

    Order is preserved exactly. It is the caller's screen order - project layer
    order - and it is the allocation order, so re-sorting here would renumber a
    show behind the user's back.
    """
    out = []
    for scr in screens or []:
        if not isinstance(scr, dict):
            continue
        layer_id = scr.get('layerId', scr.get('id'))
        if layer_id is None:
            continue
        try:
            count = int(scr.get('ports') or 0)
        except (TypeError, ValueError):
            count = 0
        out.append({
            'layerId': str(layer_id),
            'name': scr.get('name') or str(layer_id),
            'ports': max(0, count),
        })
    return out


def _clean_pins(pins):
    out = []
    for pin in pins or []:
        if not isinstance(pin, dict):
            continue
        try:
            index = int(pin.get('index'))
            port = int(pin.get('port'))
        except (TypeError, ValueError):
            continue
        if pin.get('layerId') is None or not pin.get('cardId'):
            continue
        out.append({
            'layerId': str(pin['layerId']),
            'index': index,
            'cardId': str(pin['cardId']),
            'port': port,
        })
    return out


# ── Resolution ────────────────────────────────────────────────────────────

def _free_ports(card, claims):
    """Port numbers on one card that nobody has claimed yet, lowest first.

    A card whose count was never settled - the SQ200 publishes connectors and
    no number - offers nothing to auto. Guessing a ceiling there would silently
    cap a wall, which is the one failure the catalog exists to prevent, and
    auto-numbering onto a guessed ceiling would do it twice over.
    """
    capacity = card['capacity']
    if not capacity:
        return []
    roles = card.get('backupRoles') or {}
    return [n for n in range(1, capacity + 1)
            if (card['cardId'], n) not in claims and n not in roles]


def resolve(processors, screens, state=None):
    """Work out where every port of every screen sits, and what is wrong.

    Two passes, and the order between them is the whole of rule 4: pins are
    placed FIRST and auto fills in around whatever is left. Auto cannot move a
    pin, only avoid it.
    """
    cards = cards_in(processors)
    by_id = {c['cardId']: c for c in cards}
    screens = _clean_screens(screens)
    state = state or {}
    auto_on = state.get('auto', True) is not False
    pins = _clean_pins(state.get('pins'))

    claims = {}          # (cardId, port) -> [(layerId, index), ...]
    placed = {}          # (layerId, index) -> placement dict
    issues = []

    def claim(card_id, port, layer_id, index, source):
        claims.setdefault((card_id, port), []).append((layer_id, index))
        placed[(layer_id, index)] = {
            'cardId': card_id, 'port': port, 'source': source,
        }

    known = {s['layerId'] for s in screens}

    # ── pass 1: pins ──────────────────────────────────────────────────────
    for pin in pins:
        if pin['layerId'] not in known:
            # The screen was deleted, or the caller sent a partial list. Keep
            # the pin - a deleted screen is very often an undo away - but say
            # so, because it is still holding a port number nobody can see.
            issues.append({
                'kind': 'pin-orphaned',
                'layerId': pin['layerId'],
                'cardId': pin['cardId'],
                'port': pin['port'],
                'message': 'A pinned port belongs to a screen that is no '
                           'longer in the project. It still holds its port '
                           'number until the pin is released.',
                'offers': [{'action': 'release', 'layerId': pin['layerId']}],
            })
            continue
        card = by_id.get(pin['cardId'])
        if card is None:
            issues.append({
                'kind': 'pin-card-gone',
                'layerId': pin['layerId'],
                'cardId': pin['cardId'],
                'port': pin['port'],
                'message': 'A port is pinned to a card that is no longer in '
                           'this project. Release the pin to hand it back to '
                           'auto-numbering.',
                'offers': [{'action': 'release', 'layerId': pin['layerId'],
                            'index': pin['index']}],
            })
            continue
        claim(card['cardId'], pin['port'], pin['layerId'], pin['index'], 'pin')

    # ── pass 2: auto ──────────────────────────────────────────────────────
    #
    # A screen goes onto the first card with room for ALL of it, and only onto
    # a partly-free card when no card can hold it whole. Filling a card's last
    # four ports with the first four of a six-port screen would split a run for
    # no reason and leave a two-port overflow that nobody asked for.
    if auto_on:
        for scr in screens:
            wanted = [i for i in range(scr['ports'])
                      if (scr['layerId'], i) not in placed]
            if not wanted:
                continue
            free_by_card = [(c, _free_ports(c, claims)) for c in cards]
            target = next((pair for pair in free_by_card
                           if len(pair[1]) >= len(wanted)), None)
            if target is None:
                target = next((pair for pair in free_by_card if pair[1]), None)
            if target is None:
                continue  # nothing free anywhere; reported as overflow below
            card, free = target
            for index, port in zip(wanted, free):
                claim(card['cardId'], port, scr['layerId'], index, 'auto')

    # ── what came out, and what is wrong with it ──────────────────────────
    overlapping = {key for key, owners in claims.items() if len(owners) > 1}

    resolved_screens = []
    for scr in screens:
        ports = []
        for index in range(scr['ports']):
            spot = placed.get((scr['layerId'], index))
            if spot is None:
                ports.append({
                    'index': index, 'number': index + 1,
                    'cardId': None, 'port': None, 'label': None,
                    'returnLabel': None,
                    'source': None, 'overlap': False, 'beyondCapacity': False,
                })
                continue
            card = by_id.get(spot['cardId'])
            capacity = card['capacity'] if card else None
            ports.append({
                'index': index,
                'number': index + 1,
                'cardId': spot['cardId'],
                'cardName': _card_title(card) if card else spot['cardId'],
                'port': spot['port'],
                'label': (card or {}).get('labels', {}).get(spot['port']),
                'returnLabel': (card or {}).get('returnLabels', {})
                               .get(spot['port']),
                'source': spot['source'],
                'overlap': (spot['cardId'], spot['port']) in overlapping,
                'beyondCapacity': bool(capacity and spot['port'] > capacity),
            })
        unplaced = [p['index'] for p in ports if p['cardId'] is None]
        used_cards = []
        for p in ports:
            if p['cardId'] and p['cardId'] not in used_cards:
                used_cards.append(p['cardId'])
        resolved_screens.append({
            'layerId': scr['layerId'],
            'name': scr['name'],
            'ports': ports,
            'required': scr['ports'],
            'unplaced': unplaced,
            'cardIds': used_cards,
            'split': len(used_cards) > 1,
        })

    issues.extend(_overlap_issues(overlapping, claims, by_id, screens))
    issues.extend(_overflow_issues(resolved_screens, cards, claims))
    issues.extend(_capacity_issues(cards, screens, auto_on))

    occupancy = _occupancy(resolved_screens)
    _mirror_returns(cards, occupancy)

    return {
        'configured': bool(cards),
        'auto': auto_on,
        'cards': [_card_summary(c, claims) for c in cards],
        'screens': resolved_screens,
        'occupancy': occupancy,
        'issues': issues,
    }


def _occupancy(resolved_screens):
    """The same placements read from the CARD's end: who is on port 7.

    The screens list answers "where did my ports go", which is what the Port
    Assignment panel asks. The Processors panel is standing at the other end of
    the cable and asks the opposite question, and answering it by walking every
    screen for every port row would be the same join done once per row. A port
    nobody claims is simply absent, so the panel can say free without having to
    know what free looks like.

    A contested port carries EVERY claimant, in the order they claimed it,
    rather than the last one to win a dict key. Two screens on one port is a
    real state this module reports and refuses to fix, and a row that named one
    of them would hide half of exactly the thing the user needs to see.
    """
    out = {}
    for scr in resolved_screens:
        for port in scr['ports']:
            if not port['cardId']:
                continue
            on_card = out.setdefault(port['cardId'], {})
            on_card.setdefault(str(port['port']), []).append({
                'layerId': scr['layerId'],
                'name': scr['name'],
                'number': port['number'],
                'source': port['source'],
                'overlap': port['overlap'],
            })
    return out


def _mirror_returns(cards, occupancy):
    """A backup socket displays the occupancy of the socket it backs.

    Assign main A-1 to a screen and its return loom lands on B-1, so B-1
    reading "free" (or only "backs up A-1") understates a socket that is
    now physically carrying that screen's return. The display follows the
    main through the same backedBy/backsUp link every pairing shape wires
    (fixed SX40 boxes, sequential, 1:1, manual): one rule, whatever put the
    link there.

    DERIVED, NEVER STORED. The mirrored entry is the main's own occupant
    read through the link on every resolve, so un-assigning the main clears
    the backup's display with it and there is nothing extra to undo. It is
    also display-only by construction: `claims` never sees it (used/free
    counts stand), and its source is 'return' - never 'pin' - so no release
    path can mistake the mirrored claim for one it may act on. `role` marks
    it for the tiles, and `main` names the socket it follows, because a
    refusal on the backup end has to say where the clear actually lands.
    """
    for card in cards:
        for number, role in (card.get('backupRoles') or {}).items():
            here = occupancy.get(role['cardId'], {}).get(str(role['port']))
            for occupant in here or []:
                if occupant.get('role'):
                    continue  # a mirrored entry is never itself mirrored
                occupancy.setdefault(card['cardId'], {}) \
                    .setdefault(str(number), []).append({
                        'layerId': occupant['layerId'],
                        'name': occupant['name'],
                        'number': occupant['number'],
                        'source': 'return',
                        'overlap': occupant['overlap'],
                        'role': 'return',
                        'main': {'cardId': role['cardId'],
                                 'port': role['port'],
                                 'localPort': role.get('localPort',
                                                       role['port']),
                                 'boxTitle': role.get('boxTitle'),
                                 'label': role.get('label')},
                    })


def _card_summary(card, claims):
    used = sum(1 for key in claims if key[0] == card['cardId'])
    capacity = card['capacity']
    # Ports consumed as returns are not free, and not "used" either - they
    # are spoken for by a role, so they come off the free count the same way
    # they come out of _free_ports.
    backing = len(card.get('backupRoles') or {})
    return {
        'cardId': card['cardId'],
        'processorId': card['processorId'],
        'title': _card_title(card),
        'deviceName': card['deviceName'],
        'capacity': capacity,
        'capacityKnown': card['capacityKnown'],
        'used': used,
        'backing': backing,
        'free': None if capacity is None
        else max(0, capacity - used - backing),
        # The names the ports carry, so a panel offering somebody a choice of
        # sockets can call each one what the box calls it. Without them a port
        # picker reads "1, 2, 3..." while the card in the rack reads
        # "SR-1, SR-2", and the two have to be matched up by counting.
        'labels': dict(card['labels']),
    }


def _screen_name(screens, layer_id):
    return next((s['name'] for s in screens if s['layerId'] == layer_id),
                layer_id)


def _and_list(names):
    """"A and B", "A, B and C". Three screens on one port is rarer than two but
    it happens, and "A and B and C both claim" is the kind of sentence that
    makes someone stop trusting the rest of the message."""
    if len(names) <= 2:
        return ' and '.join(names)
    return f'{", ".join(names[:-1])} and {names[-1]}'


def _overlap_issues(overlapping, claims, by_id, screens):
    """Say who is on the contested port, and offer to move each of them.

    The offer is a BLOCK move per screen, never a single port: a screen is one
    cable run, and shifting one port out of the middle of it to clear a clash
    would leave a loom that no longer matches its labels.
    """
    out = []
    for key in sorted(overlapping, key=lambda k: (k[0], k[1])):
        card_id, port = key
        owners = claims[key]
        layer_ids = []
        for layer_id, _index in owners:
            if layer_id not in layer_ids:
                layer_ids.append(layer_id)
        names = [_screen_name(screens, lid) for lid in layer_ids]
        card = by_id.get(card_id)
        out.append({
            'kind': 'overlap',
            'cardId': card_id,
            'port': port,
            'layerIds': layer_ids,
            'message': (
                f'{_and_list(names)} {"both" if len(names) == 2 else "all"} '
                f'claim port {port} on '
                f'{_card_title(card) if card else card_id}. Nothing has been '
                f'renumbered - move one of them if the clash is wrong.'),
            'offers': [{'action': 'move-block', 'layerId': lid,
                        'label': f'Move {_screen_name(screens, lid)}'}
                       for lid in layer_ids],
        })
    return out


def _overflow_issues(resolved_screens, cards, claims):
    """A screen with more ports than its card had left.

    The ports that did not fit are simply not placed. Spilling them onto the
    next card on their own would be the app deciding to split a run across two
    machines, which is a patching decision with a physical consequence - two
    trunks to one wall - and belongs to a person.
    """
    # No cards at all is the default state of every project and not a problem
    # to nag about; no card with a settled count is already reported as such,
    # and saying "full" about a card whose size nobody knows would be a second,
    # wronger version of the same news.
    if not [c for c in cards if c['capacity']]:
        return []
    out = []
    for scr in resolved_screens:
        if not scr['unplaced']:
            continue
        somewhere = [c for c in cards if _free_ports(c, claims)]
        numbers = [i + 1 for i in scr['unplaced']]
        out.append({
            'kind': 'overflow',
            'layerId': scr['layerId'],
            'ports': numbers,
            'cardIds': scr['cardIds'],
            'message': (
                f'{scr["name"]} needs {scr["required"]} ports and '
                f'{len(numbers)} of them '
                f'({", ".join(str(n) for n in numbers)}) did not fit. Place '
                f'them on another card, or free up room on this one.'
                if somewhere else
                f'{scr["name"]} needs {scr["required"]} ports and '
                f'{len(numbers)} of them did not fit. Every card in this '
                f'project is full.'),
            'offers': [{'action': 'place-overflow', 'layerId': scr['layerId'],
                        'cardId': c['cardId'],
                        'label': f'Place on {_card_title(c)}'}
                       for c in somewhere],
        })
    return out


def _capacity_issues(cards, screens, auto_on):
    out = []
    if screens and not cards:
        return out  # no processors at all is not a problem, it is the default
    for card in cards:
        short = card.get('shortfall')
        if short:
            reach = short['reachesWith']
            out.append({
                'kind': 'card-short-of-its-ceiling',
                'cardId': card['cardId'],
                'delivered': short['delivered'],
                'capacity': short['ceiling'],
                'message': (
                    f'{_card_title(card)} has {short["ceiling"]} ports but the '
                    f'boxes on it deliver {short["delivered"]}, and every OPT '
                    f'is used. '
                    + (f'It reaches {short["ceiling"]} with '
                       f'{" or ".join(reach)}.' if reach else
                       'No box in the catalog reaches its full count on this '
                       'card.')),
                'offers': [],
            })
        if card['capacityKnown']:
            continue
        out.append({
            'kind': 'capacity-unknown',
            'cardId': card['cardId'],
            'message': (
                f'{_card_title(card)} has no settled port count, so auto-'
                f'numbering will not use it. Ports can still be pinned to it '
                f'by hand.'),
            'reason': card['capacityReason'],
            'offers': [],
        })
    if not auto_on:
        out.append({
            'kind': 'auto-off',
            'message': 'Auto-numbering is off. Only pinned ports have a card.',
            'offers': [{'action': 'auto-on', 'label': 'Turn auto-numbering on'}],
        })
    return out


# ── Edits ─────────────────────────────────────────────────────────────────

def set_pin(state, layer_id, index, card_id, port):
    """Pin one port of one screen, and let it win.

    A pin is the user overruling the app, so it replaces whatever was there and
    nothing in this module may move it afterwards - not auto-numbering, not
    another screen's arrival. Only a release, or a block move of the SAME
    screen, may take it back.
    """
    pins = [p for p in _clean_pins(state.get('pins'))
            if not (p['layerId'] == str(layer_id) and p['index'] == int(index))]
    pins.append({'layerId': str(layer_id), 'index': int(index),
                 'cardId': str(card_id), 'port': int(port)})
    pins.sort(key=lambda p: (p['layerId'], p['index']))
    state['pins'] = pins
    return state


def clear_pin(state, layer_id, index=None):
    """Release a pin, or every pin on a screen when index is None. The port
    goes straight back to auto on the next resolve, which is the whole point of
    keeping auto derived rather than stored."""
    def keep(pin):
        if pin['layerId'] != str(layer_id):
            return True
        return index is not None and pin['index'] != int(index)
    state['pins'] = [p for p in _clean_pins(state.get('pins')) if keep(p)]
    return state


def _foreign_claims(processors, screens, state, layer_id, index=None):
    """Every port claimed by somebody other than the thing being moved.

    With no index that means the whole screen, because a block move vacates all
    of it; with one it means just that port, because pinning a single port
    leaves the screen's others exactly where they are and they are as much an
    obstacle as anyone else's.

    Both pinned and auto claims count. Auto ones would re-flow if they were
    landed on, but re-flowing another screen to make room is the silent
    rearrangement this module refuses to do.
    """
    resolution = resolve(processors, screens, state)
    taken = set()
    for scr in resolution['screens']:
        mine = scr['layerId'] == str(layer_id)
        for port in scr['ports']:
            if mine and (index is None or port['index'] == index):
                continue
            if port['cardId']:
                taken.add((port['cardId'], port['port']))
    return resolution, taken


def pin_to_card(processors, screens, state, layer_id, index, card_id,
                port=None):
    """Pin one port of one screen to a named card.

    The port number is optional, and leaving it out is the normal case from the
    panel: "put this one on that card" is the decision, and which free number
    it lands on is arithmetic. Doing that arithmetic in the browser means a
    second implementation of "which ports are free", and it gets it wrong the
    moment a pin has left a hole in the middle of a card.
    """
    by_id = {c['cardId']: c for c in cards_in(processors)}
    card = by_id.get(str(card_id))
    if card is None:
        return None, 'That card is not in this project.'
    if port is None:
        _res, taken = _foreign_claims(processors, screens, state, layer_id,
                                      int(index))
        port = next((n for n in range(1, (card['capacity'] or 0) + 1)
                     if (card['cardId'], n) not in taken), None)
        if port is None:
            return None, f'{_card_title(card)} has no free ports.'
    set_pin(state, layer_id, index, card['cardId'], port)
    return {'cardId': card['cardId'], 'port': int(port)}, None


# ── Placing one port by hand ──────────────────────────────────────────────
#
# The block move relocates a screen's whole run, because a screen is normally
# cabled as one. This is the other half of the same decision, for the port that
# genuinely is not like its neighbours: the spare patched across the room, the
# run that has to land on the socket the house rig was made up to. Underneath
# it is still a pin - a pin already means "this port, here, and auto may not
# touch it" - and what is new is only that a person may say WHICH socket.

def _spot_index(resolution):
    """(layerId, index) -> (cardId, port), for comparing two resolutions."""
    return {(scr['layerId'], port['index']): (port['cardId'], port['port'])
            for scr in resolution['screens'] for port in scr['ports']}


def _resolved_screen(resolution, layer_id):
    return next((s for s in resolution['screens']
                 if s['layerId'] == str(layer_id)), None)


def _foreign_occupants(resolution, card_id, port, layer_id, index):
    """Who is on a card port, not counting the port being placed onto it."""
    here = resolution['occupancy'].get(card_id, {}).get(str(port), [])
    return [o for o in here
            if not (o['layerId'] == str(layer_id) and o['number'] == index + 1)]


def _hold_screen(state, resolution, layer_id, skip_index):
    """Pin a screen's other ports where they already are, and say how many.

    Placing one port by hand overrules the app's arithmetic for THAT port; it
    is not permission to renumber the five beside it. Left alone they would be
    renumbered, because an auto port is recomputed from nothing every time and
    packs into whatever room appears - including the room the moved port has
    just left, which slides the whole tail of the run down by one. One click
    would then change four numbers on a drawing, which is the opposite of an
    override.

    So the rest of the run is held first. That is the same trade the block move
    already makes and it is as visible: every held port prints PINNED, and
    Release all pins hands the lot back.
    """
    scr = _resolved_screen(resolution, layer_id)
    held = 0
    for port in (scr or {}).get('ports', []):
        if port['index'] == skip_index or not port['cardId']:
            continue
        if port['source'] != 'pin':
            held += 1
        set_pin(state, layer_id, port['index'], port['cardId'], port['port'])
    return held


def _placement_note(before, after, scr, index, card, port, held):
    """What the move actually did, in the one line the panel has for it.

    Everything past the first sentence is a consequence nobody asked for, and
    each one is here because the alternative is finding it by reading twenty
    rows: another screen's auto ports packing into the vacated socket, a run
    that now leaves the card it was on, and a port deliberately placed on top
    of somebody after the offer to do it was accepted.
    """
    name = scr['name']
    parts = [f'{name} port {index + 1} is now on {_port_title(card, port)}.']
    if held:
        parts.append(f'Its other {held} ports are held where they were, so '
                     f'only this one moved.')

    moved_key = (scr['layerId'], index)
    was = _spot_index(before)
    now = _spot_index(after)
    shifted = []
    for key, spot in now.items():
        if key == moved_key or was.get(key) == spot:
            continue
        other = _resolved_screen(after, key[0])
        if other and other['name'] not in shifted:
            shifted.append(other['name'])
    if shifted:
        parts.append(f'Auto ports on {_and_list(shifted)} packed into the room '
                     f'it left - pin them to hold a numbering.')

    mine = _resolved_screen(after, scr['layerId'])
    if mine and len(mine['cardIds']) > 1:
        parts.append(f'{name} now spans {len(mine["cardIds"])} cards, which is '
                     f'that many trunks to one wall.')
    if mine and any(p['overlap'] for p in mine['ports']):
        parts.append('It shares the port with what was already there; nothing '
                     'was displaced.')
    return ' '.join(parts)


def place_port(processors, screens, state, layer_id, index, card_id, port,
               confirm=False):
    """Put ONE port of ONE screen on the card port somebody chose.

    Three answers instead of the usual two, because this is the one edit that
    can be refused for a reason the user is entitled to overrule. A port
    somebody else already claims is refused the FIRST time and named in the
    refusal: two screens on one socket is a state this module supports and
    reports - a hot spare on the same port is a real thing - so it stays
    reachable, but never as the silent result of a click somewhere else. Say
    what is there and what happens next, then let them ask again with confirm.
    """
    layer_id = str(layer_id)
    index = int(index)
    port = int(port)
    by_id = {c['cardId']: c for c in cards_in(processors)}
    card = by_id.get(str(card_id))
    if card is None:
        return None, 'That card is not in this project.', None
    scr = next((s for s in _clean_screens(screens)
                if s['layerId'] == layer_id), None)
    if scr is None:
        return None, 'That screen is not in this project.', None
    if index < 0 or index >= scr['ports']:
        return None, f'{scr["name"]} has no port {index + 1}.', None
    if port < 1:
        return None, 'Port numbers start at 1.', None
    # A card whose count nobody settled takes any number, which is the whole of
    # what "ports can still be pinned to it by hand" means. A card with a
    # settled one is a fact about metal and there is no port past it to place
    # onto - offering one would put a wall on a socket that does not exist.
    if card['capacity'] and port > card['capacity']:
        return None, (f'{_card_title(card)} has {card["capacity"]} ports, so '
                      f'there is no port {port} on it.'), None
    # A port consumed as a return is refused OUTRIGHT - no confirm, unlike
    # the occupied-port question below. Sharing a socket with another screen
    # is a real rig (a hot spare); sharing it with its own backup role is
    # not a rig at all, because the socket's job is carrying a main's return
    # loom. The refusal names the main it returns.
    role = (card.get('backupRoles') or {}).get(port)
    if role:
        main = role.get('label') \
            or (f'port {role.get("localPort", role.get("port"))} on '
                f'{role.get("boxTitle") or role.get("cardTitle")}')
        return None, (f'{_port_title(card, port)} backs up {main} - it is '
                      f'that port\'s return end, not a free port.'), None

    before, taken = _foreign_claims(processors, screens, state, layer_id, index)
    if (card['cardId'], port) in taken and not confirm:
        here = _foreign_occupants(before, card['cardId'], port, layer_id, index)
        names = _and_list([f'{o["name"]} port {o["number"]}' for o in here])
        # What happens next depends entirely on how the sitting tenant got
        # there, and the two outcomes are nothing like each other. A pinned
        # port is somebody's decision and stays: both claims are kept and the
        # socket draws as a clash. An auto port is arithmetic and gets out of
        # the way, which is the same thing as saying the screen it belongs to
        # is renumbered. Only one of those two can be true of any one port -
        # auto is dealt out around pins and never onto them - so this reads as
        # one sentence rather than a table of cases.
        held = [o for o in here if o['source'] == 'pin']
        outcome = (
            'held there by hand and would keep the claim, so the socket would '
            'draw as a clash' if held else
            'numbered automatically and would pack around this one, which '
            'renumbers that screen')
        return None, (
            f'{names} {"is" if len(here) == 1 else "are"} already on '
            f'{_port_title(card, port)}. Nothing has been renumbered: '
            f'{"they are" if len(here) > 1 else "it is"} {outcome}. Place '
            f'{scr["name"]} port {index + 1} here anyway, or choose a port '
            f'nobody is on.'
        ), {'cardId': card['cardId'], 'port': port, 'occupants': here}

    held = _hold_screen(state, before, layer_id, index)
    set_pin(state, layer_id, index, card['cardId'], port)
    after = resolve(processors, screens, state)
    was = _spot_index(before).get((layer_id, index))
    return {
        'cardId': card['cardId'],
        'port': port,
        'from': None if not was or was[0] is None else {'cardId': was[0],
                                                        'port': was[1]},
        'held': held,
        'note': _placement_note(before, after, scr, index, card, port, held),
    }, None, None


def _fits(card, start, size, taken):
    capacity = card['capacity']
    if not capacity or start < 1 or start + size - 1 > capacity:
        return False
    roles = card.get('backupRoles') or {}
    return all((card['cardId'], n) not in taken and n not in roles
               for n in range(start, start + size))


def move_block(processors, screens, state, layer_id, card_id=None,
               start_port=None, first_port=None, last_port=None):
    """Move a screen's WHOLE set of ports to the next free block.

    Whole set, in the same relative order, or not at all. A screen is cabled as
    one run and the labels on that loom are consecutive, so relocating half of
    it is worse than the clash it was meant to fix.

    The move overrides this screen's own pins and re-pins every port at the new
    block. That is a real decision and it is worth naming: honouring the old
    pins would mean moving only the auto ports and tearing the run in two,
    which defeats the purpose of the move. Other screens' pins are never
    touched - they are obstacles the block has to clear.

    `first_port`/`last_port` bound the search to one window of the card - a
    breakout box is a contiguous span of card ports, so "move onto that box"
    is this move with the box's span as the window. Only meaningful with a
    card_id; the block must land wholly inside the window, because a run that
    half-leaves the box is not on the box.
    """
    layer_id = str(layer_id)
    cards = cards_in(processors)
    if not cards:
        return None, 'This project has no sending cards to move onto.'
    scr = next((s for s in _clean_screens(screens) if s['layerId'] == layer_id),
               None)
    if scr is None or scr['ports'] <= 0:
        return None, 'That screen needs no ports.'

    resolution, taken = _foreign_claims(processors, screens, state, layer_id)
    current = next((s for s in resolution['screens']
                    if s['layerId'] == layer_id), None)
    here = [p for p in (current or {}).get('ports', []) if p['cardId']]
    current_card = here[0]['cardId'] if here else None
    current_start = here[0]['port'] if here else 0

    size = scr['ports']
    by_id = {c['cardId']: c for c in cards}

    if card_id and card_id not in by_id:
        return None, 'That card is not in this project.'

    # An explicit destination is an instruction, not a hint: place it there or
    # say why not, rather than sliding it somewhere nearby that does fit.
    if start_port is not None:
        card = by_id.get(card_id or current_card or cards[0]['cardId'])
        if not _fits(card, int(start_port), size, taken):
            return None, (f'Ports {start_port}-{int(start_port) + size - 1} on '
                          f'{_card_title(card)} are not all free.')
        return _pin_block(state, layer_id, card['cardId'], int(start_port),
                          size), None

    # Search order: on this card, strictly forward from where it sits now
    # ("next free block"), then each following card, then round to the front.
    # The wrap matters - a screen sitting at the end of the last card would
    # otherwise have no move offered at all, which is the case most likely to
    # be in a clash.
    order = [c['cardId'] for c in cards]
    if card_id:
        search = [card_id]
    else:
        pivot = order.index(current_card) if current_card in order else 0
        search = order[pivot:] + order[:pivot]

    # A window narrows the scan to the box's span of card ports; outside it
    # the loop below simply never starts a block.
    lo = int(first_port) if first_port is not None else None
    hi = int(last_port) if last_port is not None else None

    for position, cid in enumerate(search):
        card = by_id[cid]
        lowest = current_start + 1 if (position == 0 and cid == current_card
                                       and not card_id) else 1
        if lo is not None:
            lowest = max(lowest, lo)
        capacity = card['capacity'] or 0
        highest = capacity - size + 1
        if hi is not None:
            highest = min(highest, hi - size + 1)
        for start in range(lowest, highest + 1):
            if _fits(card, start, size, taken):
                return _pin_block(state, layer_id, cid, start, size), None

    if lo is not None or hi is not None:
        return None, (f'No run of {size} consecutive free ports between ports '
                      f'{lo or 1}-{hi or "end"} on that card. Free up a run, '
                      f'or place the ports by hand.')
    return None, (f'No card has {size} consecutive free ports. Free up a run, '
                  f'or place the ports by hand.')


def _pin_block(state, layer_id, card_id, start, size):
    clear_pin(state, layer_id)
    for index in range(size):
        set_pin(state, layer_id, index, card_id, start + index)
    return {'cardId': card_id, 'startPort': start, 'ports': size}


def place_overflow(processors, screens, state, layer_id, card_id,
                   first_port=None, last_port=None):
    """Put the ports that did not fit onto a different card.

    One of the two paths by which a screen's ports end up on two cards - the
    other is place_port, one socket at a time - and both are somebody asking
    for it in as many words. It exists because a 17-port wall on a 16-port card
    is a real thing someone builds. `.scr` stores the sending card per CABINET,
    so the format has no objection either; it is only the app that must not do
    it unasked.

    `first_port`/`last_port` bound the fill to one window of the card: a
    breakout box is a contiguous span of card ports, so "fill onto that box"
    is this fill with the box's span as the window.
    """
    layer_id = str(layer_id)
    by_id = {c['cardId']: c for c in cards_in(processors)}
    card = by_id.get(str(card_id))
    if card is None:
        return None, 'That card is not in this project.'

    resolution, taken = _foreign_claims(processors, screens, state, layer_id)
    current = next((s for s in resolution['screens']
                    if s['layerId'] == layer_id), None)
    if current is None:
        return None, 'That screen is not in this project.'
    spare = [i for i in current['unplaced']]
    if not spare:
        return None, 'Every port on that screen already has a card.'

    # The overflow keeps its own order and is packed from the card's lowest
    # free port, so ports 17-20 of a wall read as a block on the new card
    # rather than being scattered through its gaps.
    lo = max(1, int(first_port)) if first_port is not None else 1
    hi = min((card['capacity'] or 0), int(last_port)) \
        if last_port is not None else (card['capacity'] or 0)
    free = [n for n in range(lo, hi + 1)
            if (card['cardId'], n) not in taken]
    if not free:
        if first_port is not None or last_port is not None:
            return None, (f'No free ports between {lo} and {hi} on '
                          f'{_card_title(card)}.')
        return None, f'{_card_title(card)} has no free ports.'

    moved = []
    for index, port in zip(spare, free):
        set_pin(state, layer_id, index, card['cardId'], port)
        moved.append({'index': index, 'port': port})
    left = len(spare) - len(moved)
    note = None
    if left:
        note = (f'{_card_title(card)} took {len(moved)} of {len(spare)} ports. '
                f'{left} still have nowhere to go.')
    return {'cardId': card['cardId'], 'moved': moved, 'note': note}, None
