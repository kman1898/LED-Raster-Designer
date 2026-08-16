"""The processor catalog, and the rules for turning one into numbered ports.

The catalog itself is static/data/processor_catalog.json so the browser can
fetch it the same way app-presets.js fetches the panel catalog - one file, one
set of numbers, no second copy to drift. This module is the server's reader and
the only implementation of the port / label rules; the panel round-trips
through /api/processors rather than re-deriving them in JavaScript, because two
implementations of "which name wins" is exactly the kind of thing that agrees
in testing and disagrees on site.

Three things here are deliberately awkward, and all three are the hardware:

* A CHASSIS HAS NO PORT COUNT. The card in the slot does. An H9 full of
  H_20xRJ45 and an H9 full of H_4xfiber are 100 ports and 160 ports, and
  nothing about the chassis says so. So the ceiling is summed from the cards,
  never read off the processor.
* A COUNT CAN BE UNKNOWN. The SQ200 publishes connectors and no port count.
  It is still a real device someone specs, so it stays selectable and reports
  its ceiling as unknown. A guessed ceiling silently caps a wall.
* A COUNT CAN BE CONDITIONAL. H_4xfiber is 32 independent and 16 in
  copy/backup; MX40 Pro is 40 or 20 by optical mode; a redundant Brompton is
  half of what its datasheet says. Those are modes on the device, chosen per
  instance, not separate devices.
"""
import json
import os

# The nearest named device upstream supplies both halves of a port's label, so
# the default template names it and numbers within it: card "SR" -> SR-1, SR-2.
DEFAULT_PORT_LABEL_TEMPLATE = '{name}-#'

_catalog_cache = None


def _catalog_path():
    return os.path.join(os.path.dirname(__file__), 'static', 'data',
                        'processor_catalog.json')


def load_catalog(force=False):
    """Read the catalog once and hold it. It ships with the build and never
    changes at runtime, unlike the panel catalog which can be refreshed."""
    global _catalog_cache
    if _catalog_cache is None or force:
        with open(_catalog_path(), encoding='utf-8') as fh:
            _catalog_cache = json.load(fh)
    return _catalog_cache


def devices(kind=None):
    out = load_catalog().get('devices', [])
    if kind:
        out = [d for d in out if d.get('kind') == kind]
    return out


def get_device(device_id):
    for d in load_catalog().get('devices', []):
        if d.get('id') == device_id:
            return d
    return None


def cards_for(chassis_device):
    """Cards a chassis will accept, by family. This is a picker filter, not a
    capacity claim - it says an H card goes in an H chassis, and says nothing
    about how many ports that makes."""
    accepts = (chassis_device or {}).get('accepts') or []
    return [d for d in devices('card') if d.get('family') in accepts]


# ── Port counts ───────────────────────────────────────────────────────────

def port_capacity(device_id, mode=None, redundancy=False):
    """Resolve one device's port ceiling.

    Returns {'count', 'known', 'mode', 'reason'}. `count` is None whenever the
    number is not knowable from the source table - either the table never found
    one (SQ200) or its sources disagree and it declined to adjudicate (HELIOS
    Standard 4K, 2 or 3). Callers must carry the None through rather than
    substituting a zero or a sibling's number.
    """
    device = get_device(device_id)
    if not device:
        return {'count': None, 'known': False, 'mode': None,
                'reason': f'unknown device: {device_id}'}
    ports = device.get('ports') or {}
    modes = ports.get('modes') or []
    chosen_id = mode or ports.get('defaultMode')
    chosen = next((m for m in modes if m.get('id') == chosen_id), None)

    if ports.get('unknown'):
        return {'count': None, 'known': False, 'mode': chosen_id,
                'reason': ports.get('unknownReason', '')}
    if chosen is None:
        # A conflict device has no default mode on purpose: until someone says
        # which document they are working from, the ceiling is not settled.
        reason = ports.get('conflictReason', '') if ports.get('conflict') else ''
        return {'count': None, 'known': False, 'mode': None, 'reason': reason}

    count = chosen.get('count')
    if count is None:
        return {'count': None, 'known': False, 'mode': chosen_id,
                'reason': ports.get('unknownReason', '')}

    # Brompton's own capacity tool is `ports / (redundancy ? 2 : 1)`. A backup
    # port consumes a port number on both non-NovaStar vendors; it is never a
    # hidden extra one, so redundancy can only ever take capacity away.
    if redundancy and ((device.get('redundancy') or {}).get('halvesPorts')):
        count = count // 2
    return {'count': count, 'known': True, 'mode': chosen_id, 'reason': ''}


def trunks_in(cvt_device):
    """How many OPT trunks a box takes IN. One unless the table says otherwise.

    This is the number that stops a box being counted by its nameplate. A
    CVT4K-S is 2 OPT in - its four LC connectors are TWO optical ports, because
    LC is duplex, and counting connectors would double every box on the list
    exactly the way counting them doubled the four-fiber cards.
    """
    return (cvt_device or {}).get('trunksIn') or 1


def trunks_used(card):
    """OPTs already spoken for on one card. Trunks, not boxes - a CVT4K-S is
    two of them, so it fills a two-trunk card on its own."""
    return sum(trunks_in(get_device(cvt.get('deviceId')))
               for cvt in (card or {}).get('cvts') or [])


def can_add_cvt(card, device_id):
    """Whether one more box will physically go on this card.

    A card has a fixed number of OPTs and there is no way round it: a
    16xRJ45+2xfiber has two, so two CVT10s fill it and so does one CVT4K-S. A
    third box has nothing to plug into.

    This one is REFUSED rather than reported, which is the opposite of how the
    rest of this feature behaves, and the difference is worth stating. A wall
    that needs more ports than a card has is a real situation with a real
    answer - add a card - so the app shows it and lets someone decide. A box
    hung on an OPT that does not exist is not a situation at all; there is
    nothing to decide and nothing it could mean on site.
    """
    device = get_device((card or {}).get('deviceId')) or {}
    trunks = device.get('trunks') or 0
    name = device.get('name', 'This card')
    if not trunks:
        return False, (f'{name} has no OPT trunks - its ports come out on '
                       f'copper, so there is nothing to hang a box off.')
    box = get_device(device_id)
    if not box:
        return False, f'Unknown device: {device_id}'
    need = trunks_in(box)
    free = trunks - trunks_used(card)
    if need > free:
        if free <= 0:
            return False, (f'All {trunks} OPTs on {name} are used. Remove a '
                           f'box before adding another.')
        return False, (f'{box.get("name", device_id)} takes {need} OPTs and '
                       f'{name} has {free} left.')
    return True, ''


def _fills_the_card(card_device, ceiling):
    """Which boxes would reach this card's ceiling if it were filled with them.

    Derived, never listed: the answer moves with the card's ports-per-trunk, so
    a hand-written list would be right for the H_4xfiber and wrong for the
    enhanced one. Same vendor only - naming a Brompton box on a NovaStar card
    would be advice nobody can take.
    """
    trunks = card_device.get('trunks') or 0
    if not trunks or not ceiling:
        return []
    out = []
    for box in devices('cvt'):
        if box.get('vendor') != card_device.get('vendor'):
            continue
        takes = trunks_in(box)
        each = _cvt_port_count(box, card_device)
        if not each or takes > trunks:
            continue
        if (trunks // takes) * each >= ceiling:
            out.append(box.get('name', box['id']))
    return out


def _cvt_port_count(cvt_device, card_device):
    """How many ports actually land on one breakout box:

        min(box ports, trunks in x the card's ports per trunk)

    A CVT fans out whatever its trunks carry, so the box's own port count is a
    maximum and not a promise. Both halves of the minimum are load-bearing and
    each is documented by a case the other gets wrong:

    * a CVT10 gives 10 on a 64B/66B trunk and 8 on an 8B/10B one, and only the
      first 10 of an XD-S's 12 work behind an SX40 - the box is bigger than
      what one trunk carries;
    * a CVT4K-S is 16 out on 2 OPT in, so behind an H_4xfiber at 8 per trunk it
      delivers all 16 - capping it at one trunk's worth would report half a
      box, which is the same error pointing the other way.
    """
    own = port_capacity(cvt_device.get('id'))
    count = own['count']
    if count is None:
        return None
    if cvt_device.get('capAtTrunk'):
        per_trunk = (card_device or {}).get('portsPerTrunk')
        if per_trunk:
            count = min(count, trunks_in(cvt_device) * per_trunk)
    return count


# ── The project model ─────────────────────────────────────────────────────

def new_processor(device_id, seq, name=''):
    """Build a processor node. A chassis gets one empty slot per documented
    output card; an all-in-one gets a single fixed slot holding itself, so the
    slot / card / CVT / port shape is the same all the way down and the label
    rules do not need a second code path for it."""
    device = get_device(device_id)
    if not device:
        return None
    proc = {
        'id': f'proc{seq}',
        'deviceId': device_id,
        'name': name or '',
        'mode': (device.get('ports') or {}).get('defaultMode'),
        'redundancy': False,
        'slots': [],
    }
    if device.get('form') == 'chassis':
        for i in range((device.get('slots') or {}).get('count') or 0):
            proc['slots'].append({'index': i, 'card': None})
    else:
        proc['mode'] = None  # the fixed card carries the mode instead
        proc['slots'].append({
            'index': 0,
            'card': new_card(device_id, f'{seq}f', fixed=True),
        })
    return proc


def new_card(device_id, seq, name='', fixed=False):
    device = get_device(device_id)
    if not device:
        return None
    return {
        'id': f'card{seq}',
        'deviceId': device_id,
        'name': name or '',
        'portLabelTemplate': DEFAULT_PORT_LABEL_TEMPLATE,
        'mode': (device.get('ports') or {}).get('defaultMode'),
        'fixed': bool(fixed),
        'cvts': [],
    }


def new_cvt(device_id, seq, name=''):
    device = get_device(device_id)
    if not device:
        return None
    return {
        'id': f'cvt{seq}',
        'deviceId': device_id,
        'name': name or '',
        'portLabelTemplate': DEFAULT_PORT_LABEL_TEMPLATE,
        'mode': (device.get('ports') or {}).get('defaultMode'),
    }


# ── Labels ────────────────────────────────────────────────────────────────

def render_port_label(name, template, number):
    text = template if template else DEFAULT_PORT_LABEL_TEMPLATE
    return text.replace('{name}', name or '').replace('#', str(number))


def _stored_port_name(card, store, number):
    names = (card or {}).get(store) or {}
    value = names.get(str(number))
    if value is None:
        value = names.get(number)
    value = (value or '').strip()
    return value or None


def _store_port_name(card, store, number, name):
    names = card.setdefault(store, {})
    text = (name or '').strip()
    if text:
        names[str(number)] = text
    else:
        names.pop(str(number), None)
        names.pop(number, None)
    if not names:
        card.pop(store, None)
    return text or None


def port_name(card, number):
    """A name typed onto ONE port of one card, or None.

    Stored on the card and keyed by the CARD's own port number, because that is
    the port - a CVT is where it comes out, not a second port. Keys arrive as
    strings from JSON and as ints from Python, so both are read; blank is not a
    name, it is the absence of one, and returns None so the generated label
    takes back over.
    """
    return _stored_port_name(card, 'portNames', number)


def set_port_name(card, number, name):
    """Name one port by hand, or hand it back to the template with a blank.

    Clearing DELETES the key rather than storing an empty string. A port with
    no name is the normal state of every port, and a card carrying forty empty
    strings would put them in the saved file of anyone who typed a name and
    thought better of it.
    """
    return _store_port_name(card, 'portNames', number, name)


def return_port_name(card, number):
    """The name typed onto the RETURN end of one port, or None.

    A redundant loop leaves a socket and comes back to it, so the return end is
    the same port - which is why this lives beside portNames on the card and is
    keyed the same way. It is a separate store rather than a suffix rule on the
    primary because the whole point of typing one is that the house does NOT
    call the return end <primary>R: the backup loom is often labelled off its
    own series (BU-1 back for SR-1 out).
    """
    return _stored_port_name(card, 'returnPortNames', number)


def set_return_port_name(card, number, name):
    """Name one port's return end, or hand it back to <primary>R with a blank.

    Same clearing rule as set_port_name, for the same reason: an untyped return
    end is the normal state of every port, and it must leave nothing behind in
    the saved file.
    """
    return _store_port_name(card, 'returnPortNames', number, name)


def _label_owner(cvt, card, proc):
    """The nearest NAMED device upstream of a port, and nothing else.

    A fiber card's ports physically arrive at a CVT, so that box is what a tech
    stands in front of and its name wins. Failing that the card, failing that
    the processor. If nothing upstream carries a name there is no
    processor-derived label at all - the caller falls back to the screen's own
    portLabelTemplatePrimary / Return, which is what every project did before
    processors existed and what every project with no processor still does.
    """
    for node, source in ((cvt, 'cvt'), (card, 'card'), (proc, 'processor')):
        if node and (node.get('name') or '').strip():
            return node, source
    return None, None


# ── Resolution ────────────────────────────────────────────────────────────

def resolve_card(card, proc):
    """Expand one card into its ports, with the label each port carries."""
    device = get_device(card.get('deviceId')) or {}
    cap = port_capacity(card.get('deviceId'), card.get('mode'),
                        redundancy=bool(proc.get('redundancy')))
    ceiling = cap['count']

    # A TRUNK DELIVERS A BLOCK OF THE CARD'S PORTS. IT DOES NOT CREATE ANY.
    #
    # This is the rule that stops a CVT inflating a card, and it has to be one
    # rule rather than a case per device, because the same shape turns up on
    # cards that look nothing alike:
    #
    # * H_4xfiber, independent: 32 ports, 8 per trunk, four trunks. Each OPT
    #   carries its own block - 1-8, 9-16, 17-24, 25-32 - and the CVTs on them
    #   are the only way to get copper out of the card at all.
    # * H_4xfiber, copy/backup: the same card at 16 ports. OPT 3 and 4 back up
    #   OPT 1 and 2, so the third box delivers ports 1-8 AGAIN.
    # * H_16xRJ45+2xfiber: 16 ports that are already on the front of the card,
    #   and two OPTs that copy Ethernet 1-8 and 9-16. A CVT here is a different
    #   place to plug into the same sixteen ports, not sixteen more.
    # * MX40 Pro: four trunks that are four distinct blocks in 40-port mode and
    #   two blocks delivered twice in 20-port mode.
    #
    # All four fall out of: chop the card's ports into blocks of portsPerTrunk,
    # and hand trunk N the block (N mod block count). Nothing about that needs
    # to know which device it is looking at, and none of it can add a port -
    # which matters because a card that read 24 ports for a machine with 16
    # would be wrong in the direction that leaves cabinets with nothing to plug
    # into on the day.
    # The model only applies where the device HAS the ports its trunks carry -
    # that is what "a block of the card's ports" means. A HELIOS 8K is 8 ports
    # with eight fiber outs at 12 each: its trunks feed downstream boxes rather
    # than dividing up its own ports, and nothing documents them as copies of
    # one another. Rather than extrapolate a NovaStar card rule onto it, cards
    # of that shape keep the behaviour they had before this model existed.
    per_trunk = device.get('portsPerTrunk')
    trunks = device.get('trunks') or 0
    block_count = (((ceiling + per_trunk - 1) // per_trunk)
                   if (ceiling and per_trunk and ceiling >= per_trunk) else 0)

    cvts = []
    claimed = 0
    # Boxes past the last trunk have nothing to hang off, and can_add_cvt now
    # refuses to create one - but a PROJECT can still arrive carrying one, from
    # a file saved before that rule or edited by hand. This branch is the read
    # path staying safe on its own: the box is shown over its ceiling rather
    # than quietly dropped, because a box somebody drew is a box they meant,
    # and it is the only way a card's defined count can exceed its ceiling.
    # Where the block model does not apply at all, boxes simply take
    # consecutive ports from 1 as they always did.
    beyond = 1 if not block_count else (ceiling or 0) + 1
    # A BOX CONSUMES TRUNKS, NOT JUST PORTS. A CVT4K-S takes two OPTs, so two
    # of them fill a four-trunk card and a third has nothing left to plug into.
    # Counting boxes instead of trunks would let three of them read as 48 ports
    # off a machine with 32 and four fibers.
    used_trunks = 0
    for cvt in card.get('cvts') or []:
        cvt_device = get_device(cvt.get('deviceId')) or {}
        size = _cvt_port_count(cvt_device, device)
        takes = trunks_in(cvt_device)
        index = used_trunks
        used_trunks += takes
        if block_count and index + takes <= trunks:
            block = index % block_count
            first = block * per_trunk + 1
            over_trunk = False
            # A box can never deliver ports the card does not have, however
            # many trunks it takes in. Reporting its nameplate here is how a
            # wall ends up looking like it has ports that are not there.
            if ceiling and size:
                size = min(size, ceiling - first + 1)
        else:
            first = beyond
            block = None
            over_trunk = True
            beyond += size or 0
        earlier = next((c for c in cvts if c['firstPort'] == first), None)
        resolved = {
            'id': cvt.get('id'),
            'deviceId': cvt.get('deviceId'),
            'deviceName': cvt_device.get('name', cvt.get('deviceId')),
            'vendor': cvt_device.get('vendor', ''),
            'name': cvt.get('name', ''),
            'portLabelTemplate': cvt.get('portLabelTemplate') or DEFAULT_PORT_LABEL_TEMPLATE,
            'portCount': size,
            'firstPort': first,
            'trunkIndex': index,
            'trunksIn': takes,
            'trunkBlock': block,
            # A second delivery of ports an earlier box already carries: OPT 3
            # backing up OPT 1, or a copy OPT mirroring the card's own copper.
            'duplicateOf': earlier['id'] if earlier else None,
            'beyondTrunks': over_trunk,
            'ports': [],
        }
        cvts.append(resolved)
        if size:
            claimed = max(claimed, first + size - 1)

    # A CVT can only claim past the ceiling by hanging off a trunk that is not
    # there - five CVT10s on a four-trunk card. That stays visible rather than
    # being clamped away, because it is a real mistake to make on paper.
    defined = max(ceiling or 0, claimed)

    ports = []
    for number in range(1, defined + 1):
        # More than one box can reach the same port now that a trunk can be a
        # copy of an earlier one. They all list it, because a port really does
        # come out of both boxes - but the FIRST one names it, since the backup
        # is not what anyone patches to or reads a number off.
        covering = [c for c in cvts
                    if c['portCount']
                    and c['firstPort'] <= number < c['firstPort'] + c['portCount']]
        cvt = covering[0] if covering else None
        local = number - cvt['firstPort'] + 1 if cvt else number
        owner, source = _label_owner(cvt, card, proc)
        # A port is numbered within whatever is naming it. On the box, because
        # that is what is silkscreened on its face; on the card otherwise -
        # which matters the moment a card carries two unnamed CVTs, where
        # numbering both from 1 would print the same eight labels twice.
        numbered = local if source == 'cvt' else number
        # A NAME TYPED ONTO ONE PORT BEATS EVERY RULE ABOVE IT.
        #
        # The rules produce a whole card at a time - SR-1 to SR-16 - which is
        # what makes naming a card enough to label a wall. What they cannot
        # produce is the one port that is not like its neighbours: the spare
        # patched to the far side of the room, the port a house rig already
        # calls something else. That port used to be handled by overriding the
        # label on the SCREEN, and a screen's override no longer reaches an
        # assigned port, so this is where it lives now.
        manual = port_name(card, number)
        if manual:
            label = manual
            source = 'manual'
        elif owner is None:
            label = None
        elif source == 'processor':
            # A processor carries a name but no template of its own - it lends
            # the name to the card's template, which is what makes naming an
            # all-in-one enough to label its ports.
            label = render_port_label(proc.get('name'),
                                      card.get('portLabelTemplate'), numbered)
        else:
            label = render_port_label(owner.get('name'),
                                      owner.get('portLabelTemplate'), numbered)
        # THE RETURN END IS THE SAME SOCKET, RESOLVED HERE FOR THE SAME REASON
        # THE PRIMARY IS: every reader - the panel row's placeholder, the
        # assignment the canvas indexes - takes the answer rather than deriving
        # one of its own. A name typed on the return end wins outright; with
        # none typed the return is the primary with an R after it, which is
        # what P1 / R1 said before a processor was naming anything. A port
        # whose primary resolves to nothing has no derived return either - the
        # screen's own R# template is still doing the work there.
        manual_return = return_port_name(card, number)
        if manual_return:
            return_label = manual_return
            return_source = 'manual'
        else:
            return_label = f'{label}R' if label else None
            return_source = source
        port = {
            'number': number,
            'localNumber': local,
            'labelNumber': numbered,
            'label': label,
            'labelSource': source,
            'returnLabel': return_label,
            'returnLabelSource': return_source,
            'cvtId': cvt['id'] if cvt else None,
            'beyondCeiling': bool(ceiling is not None and number > ceiling),
        }
        ports.append(port)
        for box in covering:
            box['ports'].append(port)

    # THE BOX DECIDES WHETHER A CARD REACHES ITS OWN CEILING.
    #
    # An H_4xfiber enhanced is four OPTs at 10, so four CVT10s deliver all 40.
    # Two CVT4K-S boxes have 32 sockets between them and eat all four OPTs
    # getting there, because a CVT4K-S is 16 out on 2 OPTs in and those two
    # OPTs were carrying 20. Same box, same card family, eight ports gone - and
    # the very same box is exactly right on a plain H_4xfiber, where 2 x 8 is
    # its full 16.
    #
    # Left as a bare "32", someone who knows the card is a 40 assumes the app
    # is wrong. Told why, they change the box. Nothing is clamped or swapped
    # here: it is reported, and the choice stays theirs.
    delivered = sum(1 for p in ports
                    if p['cvtId'] and not p['beyondCeiling'])
    shortfall = None
    if (cvts and ceiling and trunks
            and used_trunks >= trunks
            and delivered < ceiling
            # Only where the boxes are how the ports get out at all. On a card
            # whose OPTs copy its own RJ45s there is nothing short - the ports
            # are on the front of the card and you patch them there.
            and device.get('trunkDelivery') != 'copy'):
        shortfall = {
            'delivered': delivered,
            'ceiling': ceiling,
            'reachesWith': _fills_the_card(device, ceiling),
        }

    return {
        'id': card.get('id'),
        'deviceId': card.get('deviceId'),
        'deviceName': device.get('name', card.get('deviceId')),
        'vendor': device.get('vendor', ''),
        'name': card.get('name', ''),
        'portLabelTemplate': card.get('portLabelTemplate') or DEFAULT_PORT_LABEL_TEMPLATE,
        # Sent back as typed, so the panel's per-port boxes show what is in
        # them rather than only the label they produced. Keys are strings for
        # the same reason they are stored that way - a JSON round-trip makes
        # them strings whether anyone wanted it or not.
        'portNames': {str(k): v for k, v in
                      (card.get('portNames') or {}).items() if v},
        'returnPortNames': {str(k): v for k, v in
                            (card.get('returnPortNames') or {}).items() if v},
        'fixed': bool(card.get('fixed')),
        'connector': device.get('connector', ''),
        'mode': cap['mode'],
        'modes': (device.get('ports') or {}).get('modes') or [],
        'ceiling': ceiling,
        'ceilingKnown': cap['known'],
        'ceilingReason': cap['reason'],
        'trunks': device.get('trunks'),
        'portsPerTrunk': device.get('portsPerTrunk'),
        # Whether hanging a box on a trunk gets you ports you did not already
        # have. On an H_16xRJ45+2xfiber it does not: the OPTs copy Ethernet
        # 1-8 and 9-16, so a CVT there is somewhere else to plug into the same
        # sixteen. The panel has to say so out loud, because the obvious
        # reading of "16 RJ45 plus 2 fiber plus a breakout box" is that the
        # ports add up, and they do not.
        'trunkDelivery': device.get('trunkDelivery', 'distinct'),
        'trunksCopyOwnPorts': device.get('trunkDelivery') == 'copy',
        # Trunks, not boxes: two CVT4K-S fill a four-trunk card.
        'trunksUsed': used_trunks,
        'trunksFree': max(0, (trunks or 0) - used_trunks),
        'delivered': delivered,
        'shortfall': shortfall,
        'defined': defined,
        # Over on trunks counts as over even where the ports happen to add up:
        # a box with no fiber to plug into is a box that is not connected.
        'over': bool(ceiling is not None and defined > ceiling)
                or bool(trunks and used_trunks > trunks),
        'note': device.get('note', ''),
        'cvts': cvts,
        'ports': ports,
    }


def resolve_processor(proc):
    device = get_device(proc.get('deviceId')) or {}
    slots = []
    cards = []
    for slot in proc.get('slots') or []:
        card = slot.get('card')
        resolved = resolve_card(card, proc) if card else None
        if resolved:
            cards.append(resolved)
        slots.append({'index': slot.get('index'), 'card': resolved})

    # Summed from the cards, never read off the chassis: the table records no
    # source for a chassis-wide total, only per-card capacities. One unknown
    # card makes the whole chassis unknown rather than under-reporting it.
    known = all(c['ceilingKnown'] for c in cards)
    ceiling = sum(c['ceiling'] for c in cards) if known else None
    defined = sum(c['defined'] for c in cards)

    slot_spec = device.get('slots') or {}
    max_cards = slot_spec.get('count')
    by_connector = slot_spec.get('countByConnector') or {}
    if by_connector and cards:
        # The H9 Enhanced is the one chassis whose card limit depends on what
        # is in it: 10 fiber/video cards or 5 RJ45 sending cards.
        connectors = {c.get('connector') for c in cards if c.get('connector')}
        limits = [by_connector[k] for k in connectors if k in by_connector]
        if limits:
            max_cards = min(limits)
    cards_used = len(cards)

    return {
        'id': proc.get('id'),
        'deviceId': proc.get('deviceId'),
        'deviceName': device.get('name', proc.get('deviceId')),
        'vendor': device.get('vendor', ''),
        'form': device.get('form', ''),
        'name': proc.get('name', ''),
        'mode': proc.get('mode'),
        'redundancy': bool(proc.get('redundancy')),
        'redundancySupported': bool((device.get('redundancy') or {}).get('supported')),
        'requiresDistribution': bool(device.get('requiresDistribution')),
        'ceiling': ceiling,
        'ceilingKnown': known,
        'defined': defined,
        'over': bool(ceiling is not None and defined > ceiling)
                or any(c['over'] for c in cards)
                or bool(max_cards is not None and cards_used > max_cards),
        'maxCards': max_cards,
        'cardsUsed': cards_used,
        'cardsOver': bool(max_cards is not None and cards_used > max_cards),
        'note': device.get('note', ''),
        'slots': slots,
    }


def resolve_all(processors):
    return [resolve_processor(p) for p in (processors or [])]
