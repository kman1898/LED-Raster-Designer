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

THE ATTACHMENT RULE, in full, because everything else is a consequence of it:

    Nothing lands on a card unless a person put it there. Every placement is
    a PIN - one screen port held on one card port - made by a drag onto the
    dock's hardware, a strip offer, or the place/pin routes below. A screen
    port with no pin is NOT ATTACHED: it has no card, no label, and the
    dock's attachment flag counts it until somebody attaches it. Pins are
    kept exactly where they were put; nothing here moves one.

That rule was ruled in by name (user, 2026-09-03): "we have no way to turn
on or off auto. but honestly auto should be removed now." Until then the
resolver dealt every unpinned port out onto the first card with room, which
made an auto-filled card look attached while holding nothing anyone could
release. Auto-numbering is RETIRED - the pass no longer runs - and the only
trace of it is the one-time migration (retire_auto, below) that freezes a
project saved under the old rule into the pins it was already drawn with.

Three consequences are worth stating outright, because each one looks like a
bug until you know it is the point:

* TWO PINS ON ONE PORT BOTH STAY. A collision is reported, both screens keep
  their claim and both draw in red. Bumping the loser would be the silent
  renumber.
* A SCREEN'S PORTS NEVER SPAN TWO CARDS BY THEMSELVES. A run placed by a
  drop fills one card; ports that do not fit are left unattached and
  reported, because a screen is cabled as one run and splitting one across
  two cards is a decision, not a rounding. A person may still make that
  decision - place_overflow takes the tail somewhere else, place_port takes
  one socket anywhere at all - and both say so when they do.
* NOTHING RE-PACKS. Releasing a port leaves a hole, and the hole stays until
  somebody fills it. A drawing the truck was packed to never changes
  because something ELSE on it changed - that is the whole of why a pin is
  the only way onto a card.

Port counts come in from the caller, never from here. The maths for "how many
ports does this screen need" lives in getLayerPortsRequired / calculate-
PortAssignments on the client and is subtle enough already (custom flow, ports
that cross into a group peer, Low Latency derating); a second implementation
would agree in the office and disagree on a wall.
"""
import processor_catalog as catalog

STATE_KEY = 'port_assignments'


def new_state():
    """The state every project is born with: no pins, and the stamp that says
    auto-numbering was never in play here.

    `auto` stays in the shape (False, always) so a file written by this
    version reads as "auto off" to the version before it, and `autoRetired`
    is the migration's mark - retire_auto reads it to know a project has
    already been through the freeze (or never needed one) and leaves it
    alone. A project WITHOUT the mark is one saved before the ruling, and
    the funnel treats it as such.
    """
    return {'auto': False, 'autoRetired': True, 'pins': []}


def is_retired(state):
    """Has this state been through retire_auto (or was it born after it)?"""
    return isinstance(state, dict) and state.get('autoRetired') is True


# ── Who may drive whom ────────────────────────────────────────────────────
#
# A screen's processing platform (the Processing setting on the layer) and a
# card's product line have to agree before a port may land. The ruling
# (user, 2026-08-28): "any screen programmed with say Novastar cannot be
# mapped to a Brompton processor and vice versa, etc. etc. all examples like
# that. A Novastar legacy processor cannot be mapped to an MX 40 since that
# is a coex processor."
#
# THE MATRIX LIVES HERE AND NOWHERE ELSE. The card side is data-driven off
# the catalog's `family` field, the screen side is the value the Processing
# dropdown stores on the layer, and the client gates off the `platforms`
# list each card summary carries back - never off a copy of this table.

# What the Processing dropdown calls each value. A refusal speaks the label
# the user picked, not the stored token.
PLATFORM_LABELS = {
    'novastar-armor': 'NovaStar (Legacy)',
    'novastar-coex-1g': 'NovaStar COEX A10s/A8s (1G)',
    'novastar-5g': 'NovaStar COEX CX40 (5G)',
    'brompton': 'Brompton Tessera',
    'megapixel-1g': 'Megapixel HELIOS (1G)',
    'megapixel-2.5g': 'Megapixel HELIOS (2.5G)',
}

# platform -> the catalog families whose ports may carry it. The Legacy row
# is the ruling by name - "VX, MCTRL, NovaPro, MSD, H", every non-COEX
# NovaStar line (the MSD300 files under novastar-mctrl) - and the COEX rows
# are "CX only map to 5G" with the 1G COEX all-in-ones keeping the 1G COEX
# setting to themselves.
PLATFORM_FAMILIES = {
    'novastar-armor': {'novastar-vx', 'novastar-mctrl', 'novastar-novapro',
                       'novastar-h'},
    'novastar-coex-1g': {'novastar-mx'},
    'novastar-5g': {'novastar-cx'},
    # ASSUMPTION (pending user confirmation): every Tessera is one family,
    # so any Brompton device drives a screen set to Brompton.
    'brompton': {'brompton'},
    # ASSUMPTION (pending user confirmation): both Megapixel settings accept
    # every Megapixel processor - 1G vs 2.5G is a port rate on the tile, not
    # a different product line.
    'megapixel-1g': {'megapixel'},
    'megapixel-2.5g': {'megapixel'},
}

# Devices whose compatibility crosses their family's line, by device id.
# An entry here replaces the family answer outright.
DEVICE_PLATFORMS = {
    # Ruled COEX (user, 2026-08-28, hedged: "ku20 is coex i beleive"). The
    # 1G-vs-5G sub-split is UNRULED, so both COEX settings pass until it is.
    'novastar-ku20': {'novastar-coex-1g', 'novastar-5g'},
    # The 40G MX-chassis card feeds the CVT8-5G and only the CVT8-5G, so its
    # ports are 5GBASE-T: "mx6000 and 2000 with 5g fiber only work with 5g
    # settings" (user, 2026-08-28).
    'novastar-card-mx-1x40g': {'novastar-5g'},
}

# What a refusal calls the card's side of the disagreement.
_FAMILY_GEAR = {
    'novastar-mx': 'COEX gear',
    'novastar-cx': '5G COEX gear',
    'novastar-vx': 'NovaStar legacy gear',
    'novastar-mctrl': 'NovaStar legacy gear',
    'novastar-novapro': 'NovaStar legacy gear',
    'novastar-h': 'NovaStar legacy gear',
    'brompton': 'Brompton gear',
    'megapixel': 'Megapixel gear',
}
_DEVICE_GEAR = {
    'novastar-card-mx-1x40g': '5G fiber gear',
}

# The dropdown's retired tokens, folded onto their successors the same way
# app-core folds them on load - a project saved before a rename still has to
# land on the right side of the wall.
_PLATFORM_ALIASES = {
    'novastar-1g': 'novastar-coex-1g',
    'novastar-armor-1g': 'novastar-armor',
    'brompton-ull': 'brompton',
}


def accepted_platforms(device_id):
    """The platform values a device's ports accept, or None for no
    restriction.

    None, not "everything": a device the matrix does not know - no family,
    or a family no platform names - refuses nobody, because a wrong refusal
    strands a real rig on site and a missed one only skips a warning.
    """
    if device_id in DEVICE_PLATFORMS:
        return set(DEVICE_PLATFORMS[device_id])
    family = (catalog.get_device(device_id) or {}).get('family')
    accepted = {p for p, fams in PLATFORM_FAMILIES.items() if family in fams}
    return accepted or None


def _gear(device_id):
    if device_id in _DEVICE_GEAR:
        return _DEVICE_GEAR[device_id]
    family = (catalog.get_device(device_id) or {}).get('family')
    return _FAMILY_GEAR.get(family, "a different line's gear")


def platform_allows(card, platform):
    """May a screen on this platform land on this card? A screen carrying no
    platform is never refused - old payloads carry none, and the safe side
    of that gap is a warning missed, not a wall stranded."""
    accepted = card.get('platforms')
    return not platform or accepted is None or platform in accepted


def _platform_refusal(name, platform, card):
    """The refusal, naming both sides in the user's own words for each:
    "IMAG SR is programmed NovaStar (Legacy); MX40 Pro is COEX gear." """
    label = PLATFORM_LABELS.get(platform, platform)
    return (f'{name} is programmed {label}; '
            f'{_card_title(card)} is {card["gear"]}.')


# ── The cards ports can land on ───────────────────────────────────────────

def cards_in(processors):
    """Every card in the project, in the order the dock draws them.

    The order is load-bearing rather than cosmetic: it is the order the block
    move searches cards in (and the order the retired auto pass filled them
    in, which the migration replays), so it has to be the order someone reads
    down the dock - processor by processor, slot 1 downward - or a move
    appears to land from nowhere.
    """
    out = []
    for proc in catalog.resolve_all(processors):
        for slot in proc.get('slots') or []:
            card = slot.get('card')
            if not card:
                continue
            # The ports a fill may hand out are the ones the card really has,
            # not the ones it enumerates. A card over its ceiling still lists
            # the ports past it - five CVT10s on a 32-port card is 40 - and
            # those already draw in red as a drawing mistake. Handing one out
            # here would promote that mistake into a cable order.
            out.append({
                'processorId': proc['id'],
                'processorName': proc['name'] or proc['deviceName'],
                'cardId': card['id'],
                'name': card['name'] or '',
                'deviceName': card['deviceName'],
                'deviceId': card['deviceId'],
                # Which processing platforms this card's ports may carry
                # (None = no restriction), and what a refusal calls the
                # card. Resolved here once so every placement path and the
                # dock's gating all read the same word.
                'platforms': accepted_platforms(card['deviceId']),
                'gear': _gear(card['deviceId']),
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
                # whole, because a backing port is CLAIMED BY ROLE: never
                # free to a fill, refused to a hand placement, and the
                # refusal has to say which main it returns.
                'backupRoles': {p['number']: p['backsUp']
                                for p in card['ports'] if p.get('backsUp')},
                # The other end of the link: the socket each main's return
                # lands on, by the number written beside THAT socket. Read
                # by _attached_labels when nothing upstream is named, so an
                # unnamed card's return end prints the socket it comes back
                # on rather than nothing.
                'backupSockets': {p['number']: p['backedBy']['localPort']
                                  for p in card['ports']
                                  if p.get('backedBy')},
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


def _attached_labels(card, port):
    """What an ATTACHED port prints, both ends: the label the catalog
    derived where anything upstream is named, and the socket's own number
    where nothing is.

    The user's ruling (2026-09-03): "Whatever card they are attached to
    those are the ports in the numbering that they should be taking, which
    has been the standard since we added this new stuff." A screen's ports
    count 1..N on their own (P1, P2 - the screen's template) only while
    they sit on nothing; the moment one is on a card socket it prints that
    socket. A card nobody named used to give no answer here, and the client
    fell back to the screen's template - so SL - MAIN on H9 slot 1 sockets
    6-9 printed P1 P2 P3 P4 while the dock said 6 7 8 9. Now the bare socket
    number IS the label: "6" on an unnamed card, the box's own silkscreen
    ("1".."10" on XD B just like XD A) behind an unnamed box. Nothing
    changes where a name or template exists - H9-6 stays H9-6 - because
    the catalog already answered and that answer wins outright.

    The return end goes the same way: the catalog's ladder where it spoke
    (a typed name, a template, the mapped backup's own label, the derived
    P-to-R), else the socket the return LANDS on where the redundancy
    mapping put one there (main on socket 1 of XD A returns on XD B's own
    socket 1 - "1"), else the primary's number with the derived R after it
    (derive_return_label, the one statement of that rule). The silkscreen
    number is the resolver's localNumber, reused rather than re-derived.
    """
    if card is None:
        return None, None
    label = (card.get('labels') or {}).get(port)
    return_label = (card.get('returnLabels') or {}).get(port)
    if label is None:
        label = str((card.get('localNumbers') or {}).get(port, port))
    if return_label is None:
        lands_on = (card.get('backupSockets') or {}).get(port)
        return_label = (str(lands_on) if lands_on is not None
                        else catalog.derive_return_label(label))
    return label, return_label


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
    order - and it is the order the resolution reports in (and the order the
    migration's one replay of the old fill deals in), so re-sorting here would
    renumber a legacy show behind the user's back.
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
        # The layer's Processing setting rides with the port count, because
        # the two travel from the same place (the client owns the layer the
        # same way it owns the port maths) and compatibility needs it on
        # every path. Absent stays absent - platform_allows treats a screen
        # with no platform as free to land anywhere.
        platform = scr.get('platform')
        if isinstance(platform, str):
            platform = _PLATFORM_ALIASES.get(platform, platform)
        else:
            platform = None
        out.append({
            'layerId': str(layer_id),
            'name': scr.get('name') or str(layer_id),
            'ports': max(0, count),
            'platform': platform or None,
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
    no number - offers nothing to a fill. Guessing a ceiling there would
    silently cap a wall, which is the one failure the catalog exists to
    prevent, and filling onto a guessed ceiling would do it twice over.
    """
    capacity = card['capacity']
    if not capacity:
        return []
    roles = card.get('backupRoles') or {}
    return [n for n in range(1, capacity + 1)
            if (card['cardId'], n) not in claims and n not in roles]


def resolve(processors, screens, state=None, _legacy_auto=False):
    """Work out where every port of every screen sits, and what is wrong.

    One pass: the pins. A screen port with no pin has no card and is
    reported as not attached; nothing here invents a place for it.

    `_legacy_auto` is the MIGRATION'S switch and nobody else's: it replays
    the retired auto fill (see _legacy_auto_pass) so retire_auto can read
    off where a pre-ruling project's ports were drawn and pin them there
    once. Every other caller leaves it off, and the routes never expose it.
    """
    cards = cards_in(processors)
    by_id = {c['cardId']: c for c in cards}
    screens = _clean_screens(screens)
    state = state or {}
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
                'offers': [{'action': 'release', 'layerId': pin['layerId'],
                            'label': 'Release pin'}],
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
                           'this project. Release the pin, then place the '
                           'port where it should go.',
                'offers': [{'action': 'release', 'layerId': pin['layerId'],
                            'index': pin['index'], 'label': 'Release pin'}],
            })
            continue
        claim(card['cardId'], pin['port'], pin['layerId'], pin['index'], 'pin')

    # ── the retired pass, for the migration only ──────────────────────────
    if _legacy_auto:
        _legacy_auto_pass(cards, screens, claims, placed, claim)

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
            # THE ONE AUTHORITY on what an attached port prints. The canvas
            # bubbles, the dock chips and every export index these two
            # fields (the client's _indexAssignmentLabels) and fall back to
            # the screen's own P#/R# template only where they are None -
            # which, since the 2026-09-03 ruling, is only a port that sits
            # on nothing. See _attached_labels.
            label, return_label = _attached_labels(card, spot['port'])
            ports.append({
                'index': index,
                'number': index + 1,
                'cardId': spot['cardId'],
                'cardName': _card_title(card) if card else spot['cardId'],
                'port': spot['port'],
                'label': label,
                'returnLabel': return_label,
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
            'platform': scr['platform'],
            'ports': ports,
            'required': scr['ports'],
            'unplaced': unplaced,
            'cardIds': used_cards,
            'split': len(used_cards) > 1,
        })

    issues.extend(_overlap_issues(overlapping, claims, by_id, screens))
    issues.extend(_platform_issues(resolved_screens, by_id))
    issues.extend(_overflow_issues(resolved_screens, cards))
    issues.extend(_capacity_issues(cards, screens))

    occupancy = _occupancy(resolved_screens)
    _mirror_returns(cards, occupancy)

    return {
        'configured': bool(cards),
        'cards': [_card_summary(c, claims) for c in cards],
        'screens': resolved_screens,
        'occupancy': occupancy,
        'issues': issues,
    }


def _legacy_auto_pass(cards, screens, claims, placed, claim):
    """The RETIRED auto-numbering fill, kept for retire_auto and nothing else.

    This is, verbatim in effect, the pass every resolve ran before the ruling
    of 2026-09-03: each screen's unpinned ports go, as one run, onto the
    first card - processors in order, slots in order - with enough free
    ports for all of them, failing that onto the first card with any free
    port, skipping a card the screen's platform cannot drive; within the
    card they take the lowest free numbers ascending. It has to stay
    byte-for-byte the old behaviour because its one job is to reproduce the
    drawing a pre-ruling file was saved with, so the migration can pin the
    ports exactly where the truck was packed to. Nothing outside the
    migration may call it: a resolve that ran this would be auto-numbering
    under another name.
    """
    for scr in screens:
        wanted = [i for i in range(scr['ports'])
                  if (scr['layerId'], i) not in placed]
        if not wanted:
            continue
        usable = [c for c in cards if platform_allows(c, scr['platform'])]
        free_by_card = [(c, _free_ports(c, claims)) for c in usable]
        target = next((pair for pair in free_by_card
                       if len(pair[1]) >= len(wanted)), None)
        if target is None:
            target = next((pair for pair in free_by_card if pair[1]), None)
        if target is None:
            continue  # nothing free anywhere; reported as overflow
        card, free = target
        for index, port in zip(wanted, free):
            claim(card['cardId'], port, scr['layerId'], index, 'auto')


# ── The one-time migration ────────────────────────────────────────────────

def _screen_layers(project):
    return [l for l in (project.get('layers') or [])
            if isinstance(l, dict) and l.get('id') is not None
            and (l.get('type') or 'screen') == 'screen']


def _screens_match_project(screens, project):
    """Are these screens a picture of THIS project's layers?

    The freeze pins ports by the counts the client sent, and the client is
    the only place those counts exist - so the one thing that must never
    happen is a stale list (a resolve fired for the project that was open a
    moment ago) being frozen onto the project that has just been loaded.
    Layer ids are small integers and collide across projects, so an id
    match is not enough: every sent screen has to carry the name the
    project's layer of that id carries. A miss on any of them means "not
    this project", and the migration waits for the next request.
    """
    known = {str(l['id']): l.get('name') for l in _screen_layers(project)}
    if not screens:
        return False
    for scr in screens:
        if not isinstance(scr, dict):
            return False
        layer_id = str(scr.get('layerId', scr.get('id')))
        if layer_id not in known:
            return False
        expected = known[layer_id] or f'Screen {layer_id}'
        if (scr.get('name') or f'Screen {layer_id}') != expected:
            return False
    return True


def retire_auto(project, screens=None):
    """Freeze a pre-ruling project's auto placements into pins, ONCE.

    Runs at the project funnel (routes_project PUT/POST) and again at the
    head of every port-assignment route. A project already carrying the
    autoRetired mark is left untouched, which is the whole of idempotence.
    For one without it:

    * auto was OFF in the file, or there is no card with a settled count,
      or no screen layer at all: nothing was ever auto-drawn, so the state
      is just stamped (pins kept as they are).
    * auto was ON (or the flag absent - the pre-flag default) and there is
      hardware to have drawn onto: the retired fill is replayed with the
      SAME pins, over the screens the client sent in layer order, and every
      port it dealt becomes a pin at that exact socket. The drawing does
      not change; what changes is that every port on it can now be
      released. Clashes stay (they were pins), overflow stays unattached
      (the fill never spilled), backup mirrors follow the pinned mains as
      they always did, the platform wall holds (the fill skipped
      mismatched gear).

    The port counts live on the client, so the freeze can only run on a
    request that carries screens - and only when those screens are this
    project's (_screens_match_project). The funnel carries none and can
    settle only the hardware-less cases; the first resolve after a load
    settles the rest. Returns True when the project changed.
    """
    state = project.get(STATE_KEY)
    if is_retired(state):
        return False
    if not isinstance(state, dict):
        state = {}
    pins = _clean_pins(state.get('pins'))
    auto_was_on = state.get('auto', True) is not False
    processors = project.get('processors') or []
    cards = [c for c in cards_in(processors) if c['capacity']]
    if auto_was_on and cards and _screen_layers(project):
        if not _screens_match_project(screens, project):
            return False  # needs this project's port counts; wait for them
        replay = resolve(processors, screens, {'pins': pins},
                         _legacy_auto=True)
        for scr in replay['screens']:
            for port in scr['ports']:
                if port['source'] == 'auto':
                    pins.append({'layerId': scr['layerId'],
                                 'index': port['index'],
                                 'cardId': port['cardId'],
                                 'port': port['port']})
        pins.sort(key=lambda p: (p['layerId'], p['index']))
    project[STATE_KEY] = {'auto': False, 'autoRetired': True, 'pins': pins}
    return True


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
        # The server's word on which platforms may land here, for any client-
        # side gating - None means no restriction. The matrix itself never
        # crosses the wire; only its answer does.
        'platforms': sorted(card['platforms']) if card['platforms'] else None,
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


def _platform_issues(resolved_screens, by_id):
    """A pin holding a screen on gear its platform cannot drive.

    Every placement path refuses this outright, so the only ways in are a
    project pinned before the wall existed and a layer whose Processing
    changed after the pin went down. Same treatment as
    every other found problem: reported red, NOTHING UNPINNED, and the
    offers are the only thing that moves anything - silently releasing the
    pin would renumber a drawing the truck was packed to.
    """
    out = []
    for scr in resolved_screens:
        if not scr.get('platform'):
            continue
        flagged = []
        for port in scr['ports']:
            card = by_id.get(port['cardId']) if port['cardId'] else None
            if card is None or platform_allows(card, scr['platform']):
                continue
            if card['cardId'] in flagged:
                continue
            flagged.append(card['cardId'])
            out.append({
                'kind': 'platform-mismatch',
                'layerId': scr['layerId'],
                'cardId': card['cardId'],
                'message': (
                    f'{_platform_refusal(scr["name"], scr["platform"], card)}'
                    f' Nothing has been unpinned - move the run to matching '
                    f'gear, or release the pins.'),
                'offers': [
                    {'action': 'move-block', 'layerId': scr['layerId'],
                     'label': f'Move {scr["name"]}'},
                    {'action': 'release', 'layerId': scr['layerId'],
                     'label': 'Release pins'},
                ],
            })
    return out


def _overflow_issues(resolved_screens, cards):
    """A screen with ports on no card - never placed, or more than its card
    had room for.

    Unattached ports are simply not placed, and the row only says so.
    Putting them somewhere on their own would be the app deciding where a
    run lands, which is a patching decision with a physical consequence and
    belongs to a person. The person's way to make it is the dock itself:
    drag the ports (or the screen) onto the card they should land on. The
    strip carries no place buttons for it, and the dock's attachment flag
    is where this issue is drawn.
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
        numbers = [i + 1 for i in scr['unplaced']]
        out.append({
            'kind': 'overflow',
            'layerId': scr['layerId'],
            'ports': numbers,
            'cardIds': scr['cardIds'],
            'message': (
                f'{scr["name"]} needs {scr["required"]} ports and '
                f'{len(numbers)} of them '
                f'({", ".join(str(n) for n in numbers)}) are not attached.'),
            'offers': [],
        })
    return out


def _capacity_issues(cards, screens):
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
                f'{_card_title(card)} has no settled port count, so a whole-'
                f'card fill cannot use it. Ports can still be placed on it '
                f'one at a time.'),
            'reason': card['capacityReason'],
            'offers': [],
        })
    return out


# ── Edits ─────────────────────────────────────────────────────────────────

def set_pin(state, layer_id, index, card_id, port):
    """Pin one port of one screen, and let it win.

    A pin is the user's decision about where a port lives, so it replaces
    whatever that port had and nothing in this module may move it
    afterwards - not another screen's arrival, not a release next door.
    Only a release, or a block move of the SAME screen, may take it back.
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
    comes off its card and is not attached until somebody places it again;
    nothing slides into the socket it left."""
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
    # Wrong-line gear is refused outright, with both sides named. No confirm
    # path, unlike an occupied port: sharing a socket is a real rig, driving
    # a Brompton wall off a NovaStar card is not.
    scr = next((s for s in _clean_screens(screens)
                if s['layerId'] == str(layer_id)), None)
    if scr and not platform_allows(card, scr['platform']):
        return None, _platform_refusal(scr['name'], scr['platform'], card)
    if port is None:
        _res, taken = _foreign_claims(processors, screens, state, layer_id,
                                      int(index))
        # A socket spoken for by a redundancy role is not free, and with
        # the auto pass gone this is the arithmetic that has to know it -
        # the same skip _free_ports makes.
        roles = card.get('backupRoles') or {}
        port = next((n for n in range(1, (card['capacity'] or 0) + 1)
                     if (card['cardId'], n) not in taken and n not in roles),
                    None)
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
# it is still a pin - every placement is - and what is different is only that
# a person names WHICH socket rather than which card.

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


def _placement_note(after, scr, index, card, port):
    """What the move actually did, in the one line the panel has for it.

    Everything past the first sentence is a consequence nobody asked for, and
    each one is here because the alternative is finding it by reading twenty
    rows: a run that now leaves the card it was on, and a port deliberately
    placed on top of somebody after the offer to do it was accepted. Nothing
    else on the drawing moved - a placement touches one port and one port
    only, and every other pin stays where it was.
    """
    name = scr['name']
    parts = [f'{name} port {index + 1} is now on {_port_title(card, port)}.']

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
    # Wrong-line gear is refused OUTRIGHT, like the return-end refusal below
    # and unlike the occupied-port question: two screens on one socket is a
    # rig somebody may mean, a Legacy screen on COEX gear is not a rig at
    # all. The refusal names both sides so the fix is legible from the strip.
    if not platform_allows(card, scr['platform']):
        return None, _platform_refusal(scr['name'], scr['platform'],
                                       card), None
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
        # The sitting tenant is somebody's decision - every claim is a pin -
        # and stays: both claims are kept and the socket draws as a clash.
        # Nothing gets out of the way, because nothing here ever moves a
        # port the user did not point at.
        return None, (
            f'{names} {"is" if len(here) == 1 else "are"} already on '
            f'{_port_title(card, port)}. Nothing has been moved: '
            f'{"they keep their claims" if len(here) > 1 else "it keeps its claim"}'
            f', so the socket would draw as a clash. Place '
            f'{scr["name"]} port {index + 1} here anyway, or choose a port '
            f'nobody is on.'
        ), {'cardId': card['cardId'], 'port': port, 'occupants': here}

    set_pin(state, layer_id, index, card['cardId'], port)
    after = resolve(processors, screens, state)
    was = _spot_index(before).get((layer_id, index))
    return {
        'cardId': card['cardId'],
        'port': port,
        'from': None if not was or was[0] is None else {'cardId': was[0],
                                                        'port': was[1]},
        'note': _placement_note(after, scr, index, card, port),
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
    block - the unattached ones included, which is how a screen with nothing
    on a card lands whole. That is a real decision and it is worth naming:
    honouring the old pins would mean moving only the rest and tearing the
    run in two, which defeats the purpose of the move. Other screens' pins
    are never touched - they are obstacles the block has to clear.

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
    # A named destination on the wrong side of the platform wall is refused
    # before any fit is looked for - a free run on gear the screen cannot
    # drive is not an answer.
    if card_id and not platform_allows(by_id[card_id], scr['platform']):
        return None, _platform_refusal(scr['name'], scr['platform'],
                                       by_id[card_id])

    # An explicit destination is an instruction, not a hint: place it there or
    # say why not, rather than sliding it somewhere nearby that does fit.
    if start_port is not None:
        card = by_id.get(card_id or current_card or cards[0]['cardId'])
        if not platform_allows(card, scr['platform']):
            return None, _platform_refusal(scr['name'], scr['platform'], card)
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
        # The search only walks cards the screen's platform can drive, or
        # "next free block" would relocate a run onto gear it cannot use.
        # When that leaves nowhere at all, say the real reason rather than
        # "no run free".
        search = [cid for cid in search
                  if platform_allows(by_id[cid], scr['platform'])]
        if not search:
            label = PLATFORM_LABELS.get(scr['platform'], scr['platform'])
            return None, (f'{scr["name"]} is programmed {label}, and no card '
                          f'in this project matches it.')

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
    """Put a screen's unattached ports onto a card, in order.

    This is the fill a card or box drop runs - a screen with nothing on a
    card lands here whole - and it is one of the two paths by which a
    screen's ports end up on two cards (the other is place_port, one socket
    at a time), both of them somebody asking for it in as many words. A
    17-port wall on a 16-port card is a real thing someone builds. `.scr`
    stores the sending card per CABINET, so the format has no objection
    either; it is only the app that must not do it unasked.

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
    # The tail of a run obeys the same wall its head does: overflow may
    # cross onto a second card, never onto a second product line.
    if not platform_allows(card, current.get('platform')):
        return None, _platform_refusal(current['name'],
                                       current['platform'], card)
    spare = [i for i in current['unplaced']]
    if not spare:
        return None, 'Every port on that screen already has a card.'
    # The screen's OWN placed ports are not free either. _foreign_claims
    # leaves the whole screen out (a block move vacates all of it), but a
    # fill only moves the tail, and dropping a half-placed screen on its
    # own card again must land that tail beside its head, never on top of
    # it.
    for port in current['ports']:
        if port['cardId']:
            taken.add((port['cardId'], port['port']))

    # The ports keep their own order and are packed from the card's lowest
    # free socket, so a run reads as a block on the card rather than being
    # scattered through its gaps. A socket spoken for by a redundancy role
    # is not free - the even half of a sequential card, every port of a
    # 1:1 backup unit - and since this fill is the one that lands whole
    # screens now, it makes the same skip the retired auto pass made.
    roles = card.get('backupRoles') or {}
    lo = max(1, int(first_port)) if first_port is not None else 1
    hi = min((card['capacity'] or 0), int(last_port)) \
        if last_port is not None else (card['capacity'] or 0)
    free = [n for n in range(lo, hi + 1)
            if (card['cardId'], n) not in taken and n not in roles]
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
