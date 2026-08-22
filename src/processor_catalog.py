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


def redundancy_pairing(device, redundancy_on):
    """The documented backup pairing of one device, or None where none is.

    Only Brompton documents one, and the rule arrived verbatim: "SX40s and
    SQ200, A back up to B, C back up to D automatically - that is the only way
    it works for Brompton." Fixed adjacent pairs, so the pairing is REPORTED
    as a fact, never offered as a choice; there is nothing here for a caller
    to edit and no storage for an alternative arrangement.

    `pairs` letters the device's trunks where it has trunks to letter, and is
    empty where it does not: the SQ200 publishes no output count, and
    lettering outputs nobody has counted would be a guessed ceiling wearing a
    different hat. The statement still states the rule.

    NovaStar carries no entry here - its redundancy is a DEFAULT pair of
    boxes, primary plus backup, built in add_cvt's caller and freely
    rearranged. Megapixel carries none either, deliberately: no pairing rule
    is documented for it, and a default invented in the safe-looking
    direction is still an invented one.
    """
    if not redundancy_on:
        return None
    if ((device or {}).get('redundancy') or {}).get('pairing') != 'adjacent':
        return None
    trunks = device.get('trunks') or 0
    letters = [chr(ord('A') + i) for i in range(trunks)]
    pairs = [{'primary': letters[i], 'backup': letters[i + 1]}
             for i in range(0, trunks - 1, 2)]
    if pairs:
        text = ', '.join(f'{p["primary"]} backs up to {p["backup"]}'
                         for p in pairs)
    else:
        text = 'adjacent outputs back each other (A to B, C to D)'
    return {
        'scheme': 'adjacent',
        'fixed': True,
        'pairs': pairs,
        'statement': f'{text} - automatic, and the only way this device '
                     f'pairs.',
    }


def trunks_in(cvt_device):
    """How many OPT trunks a box takes IN. One unless the table says otherwise.

    This is the number that stops a box being counted by its nameplate. A
    CVT4K-S is 2 OPT in - its four LC connectors are TWO optical ports, because
    LC is duplex, and counting connectors would double every box on the list
    exactly the way counting them doubled the four-fiber cards.
    """
    return (cvt_device or {}).get('trunksIn') or 1


def trunks_used(card):
    """Trunks already spoken for on one card. Trunks, not boxes - a CVT4K-S is
    two of them, so it fills a two-trunk card on its own."""
    return sum(trunks_in(get_device(cvt.get('deviceId')))
               for cvt in (card or {}).get('cvts') or [])


def default_backup_pair(card):
    """Whether one box added to this card should bring a backup box with it.

    The user's rule, and it names ONE vendor: "For NovaStar typically there
    would be a primary box and a backup box, but that doesn't mean that you
    have to do it that way." So on a NovaStar card whose current mode makes
    some trunks copies of others - an H_4xfiber in copy/backup, an MX40 Pro
    in 20-port mode - a new box defaults to a pair, primary plus backup, and
    stays a plain single box everywhere else. It is a DEFAULT and nothing
    more: the caller may decline it, and the backup deletes like any box.

    Nothing here reaches Brompton, whose pairing is fixed the opposite way
    (redundancy_pairing above), and nothing reaches Megapixel, for which no
    rule is documented at all - "I'm not sure about how megapixel works" is
    an instruction, not a gap to fill in.
    """
    device = get_device((card or {}).get('deviceId')) or {}
    if device.get('vendor') != 'NovaStar':
        return False
    if device.get('trunkDelivery') == 'copy':
        # The trunks copy the card's own copper: a box there is another place
        # to plug into ports the card already delivers, not a backup unit.
        return False
    ceiling = port_capacity(card.get('deviceId'), card.get('mode'))['count']
    per_trunk = device.get('portsPerTrunk')
    trunks = device.get('trunks') or 0
    if not (ceiling and per_trunk and ceiling >= per_trunk):
        return False
    # Some trunks duplicate others exactly when there are more trunks than
    # blocks of ports - which is what "redundancy in play" means on the card.
    return ((ceiling + per_trunk - 1) // per_trunk) < trunks


def can_add_cvt(card, device_id):
    """Whether one more box will physically go on this card.

    A card has a fixed number of trunks and there is no way round it: a
    16xRJ45+2xfiber has two, so two CVT10s fill it and so does one CVT4K-S. A
    third box has nothing to plug into.

    This one is REFUSED rather than reported, which is the opposite of how the
    rest of this feature behaves, and the difference is worth stating. A wall
    that needs more ports than a card has is a real situation with a real
    answer - add a card - so the app shows it and lets someone decide. A box
    hung on a trunk that does not exist is not a situation at all; there is
    nothing to decide and nothing it could mean on site.
    """
    device = get_device((card or {}).get('deviceId')) or {}
    trunks = device.get('trunks') or 0
    name = device.get('name', 'This card')
    if not trunks:
        return False, (f'{name} has no optical trunks - its ports come out on '
                       f'copper, so there is nothing to hang a box off.')
    box = get_device(device_id)
    if not box:
        return False, f'Unknown device: {device_id}'
    # THE TRUNK'S LINE RATE IS PART OF THE METAL, the same way the trunk
    # count is. The user's ruling, verbatim: "40g fiber ports only worjks
    # with cvt 8 f5 boxes" - a 40G OPT takes the CVT8-5G and nothing else,
    # and the CVT8-5G takes a 40G trunk and nothing else, so attachment is
    # rate-matched wherever BOTH rates are documented. Where either side's
    # sheet states no rate, nothing is refused on a rate nobody wrote down -
    # the same no-inference rule the port ceilings live by.
    card_rate = device.get('trunkRate')
    box_rate = box.get('trunkRate')
    if card_rate and box_rate and card_rate != box_rate:
        return False, (f'{box.get("name", device_id)} hangs off a {box_rate} '
                       f'trunk and the OPTs on {name} are {card_rate} - the '
                       f'rates must match.')
    need = trunks_in(box)
    free = trunks - trunks_used(card)
    if need > free:
        if free <= 0:
            return False, (f'All {trunks} trunks on {name} are used. Remove a '
                           f'box before adding another.')
        return False, (f'{box.get("name", device_id)} takes {need} trunks and '
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
        # Never name a box the rate rule refuses: a CVT8-5G's 8-out would
        # arithmetically fill a plain H_4xfiber, and it does not go there.
        rate, box_rate = card_device.get('trunkRate'), box.get('trunkRate')
        if rate and box_rate and rate != box_rate:
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

    A box fans out whatever its trunks carry, so the box's own port count is a
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
    slot / card / breakout box / port shape is the same all the way down and the label
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
    # No portLabelTemplate at birth. The default is what an ABSENT template
    # means (render_port_label falls back to it), so stamping it here wrote
    # the app's own fallback into every saved file as if somebody had typed
    # it - and the panel then drew it as a value nobody could tell from a
    # choice, or clear back out. Same rule as a port name: unset is the
    # normal state, and it stores nothing.
    device = get_device(device_id)
    if not device:
        return None
    return {
        'id': f'card{seq}',
        'deviceId': device_id,
        'name': name or '',
        'mode': (device.get('ports') or {}).get('defaultMode'),
        'fixed': bool(fixed),
        'cvts': [],
    }


def new_cvt(device_id, seq, name=''):
    # Same birth rule as new_card: the default template is a fallback, not a
    # value, and it is not stored.
    device = get_device(device_id)
    if not device:
        return None
    return {
        'id': f'cvt{seq}',
        'deviceId': device_id,
        'name': name or '',
        'mode': (device.get('ports') or {}).get('defaultMode'),
    }


# ── Labels ────────────────────────────────────────────────────────────────

def render_port_label(name, template, number):
    text = template if template else DEFAULT_PORT_LABEL_TEMPLATE
    return text.replace('{name}', name or '').replace('#', str(number))


def derive_return_label(label):
    """The return end's name when nobody typed one: the primary with its
    leading P turned into an R, else the primary with an R after it.

    P is primary and R is redundant - that is what the screen's own templates
    say (P# out, R# back), and a card named P1 has to read the same way: P1-1
    out, R1-1 back. P1-1R is two statements of "primary" wrapped round one of
    "redundant", and it is not what anyone on a loom calls the backup. Case
    follows the name (p1-1 back as r1-1) because the label is the name as the
    hand typed it, not a normalised copy.

    The P is a prefix only when what follows it is not a letter - a digit
    (P1-1), a separator (P-1), or nothing at all (P). A P that begins a word
    - PORT-3, PANEL-2, Px - is the first letter of a name, not a mark of
    "primary", and there is nothing to swap. Those, and every primary with
    no P at all - SR-1, HOUSE-LEFT - keep the R after them, so a drawing
    already issued with SR-1R on it prints SR-1R again. Whether those want
    a rule of their own is an open question, not one to answer by inventing
    it here.

    This is the one statement of the rule. The client has a copy for the
    panel's placeholders and for the frame loop, and a test holds the two
    byte-for-byte - which is why "letter" is spelt out as ASCII here rather
    than asked of str.isalpha(), whose answer the client could not match."""
    if not label:
        return None
    second = label[1:2]
    word = ('a' <= second <= 'z') or ('A' <= second <= 'Z')
    if not word:
        if label[0] == 'P':
            return 'R' + label[1:]
        if label[0] == 'p':
            return 'r' + label[1:]
    return f'{label}R'


def typed_port_label_template(node):
    """The label template somebody CHOSE, or '' - what the panel's Label box
    shows as a value, with the default left to its placeholder.

    A stored copy of the default reads as absent: every card and box created
    before v0.11.2 was stamped with '{name}-#' at birth, so in an old file
    that text is the absence of a choice, not one - and a hand that types the
    default has chosen exactly what the placeholder already promised, so
    nothing is lost by showing it as the placeholder either. Rendering is
    untouched either way; render_port_label falls back to the same default
    whether the key holds it, holds '', or is gone."""
    text = ((node or {}).get('portLabelTemplate') or '').strip()
    return '' if text == DEFAULT_PORT_LABEL_TEMPLATE else text


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
    the port - a breakout box is where it comes out, not a second port. Keys arrive as
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
    call the return end what derive_return_label says: the backup loom is
    often labelled off its own series (BU-1 back for SR-1 out).
    """
    return _stored_port_name(card, 'returnPortNames', number)


def set_return_port_name(card, number, name):
    """Name one port's return end, or hand it back to the derived return
    (derive_return_label) with a blank.

    Same clearing rule as set_port_name, for the same reason: an untyped return
    end is the normal state of every port, and it must leave nothing behind in
    the saved file.
    """
    return _store_port_name(card, 'returnPortNames', number, name)


def _label_owner(cvt, card, proc):
    """The nearest NAMED device upstream of a port, and nothing else.

    A fiber card's ports physically arrive at a breakout box, so that box is what a tech
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
    # This is the rule that stops a breakout box inflating a card, and it has to be one
    # rule rather than a case per device, because the same shape turns up on
    # cards that look nothing alike:
    #
    # * H_4xfiber, independent: 32 ports, 8 per trunk, four trunks. Each OPT
    #   carries its own block - 1-8, 9-16, 17-24, 25-32 - and the boxes on them
    #   are the only way to get copper out of the card at all.
    # * H_4xfiber, copy/backup: the same card at 16 ports. OPT 3 and 4 back up
    #   OPT 1 and 2, so the third box delivers ports 1-8 AGAIN.
    # * H_16xRJ45+2xfiber: 16 ports that are already on the front of the card,
    #   and two OPTs that copy Ethernet 1-8 and 9-16. A box here is a different
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

    # WHICH TRUNK BACKS WHICH IS THE VENDOR'S CALL, NOT A PATTERN. NovaStar
    # documents interleaved copies - OPT 3/4 back up OPT 1/2 - which is what
    # `block = index mod block count` produces. Brompton documents ADJACENT
    # pairs, verbatim: "A back up to B, C back up to D automatically; that is
    # the only way it works" - so under Brompton redundancy a pair of
    # neighbouring trunks carries one block between them, and the box on the
    # second trunk of a pair is the first one's backup by construction.
    # Neither shape is ever applied to the other vendor, and Megapixel gets
    # neither, because none is documented for it.
    adjacent = bool(proc.get('redundancy')) and \
        ((device.get('redundancy') or {}).get('pairing') == 'adjacent')

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
    # A BOX CONSUMES TRUNKS, NOT JUST PORTS. A CVT4K-S takes two trunks, so
    # two of them fill a four-trunk card and a third has nothing left to plug
    # into. Counting boxes instead of trunks would let three of them read as
    # 48 ports off a machine with 32 and four fibers.
    used_trunks = 0
    taken = set()
    placed_by_id = {}
    for cvt in card.get('cvts') or []:
        cvt_device = get_device(cvt.get('deviceId')) or {}
        size = _cvt_port_count(cvt_device, device)
        takes = trunks_in(cvt_device)
        used_trunks += takes
        # A box created as another box's BACKUP sits on the trunk that
        # duplicates its primary's - OPT 3 for a primary on OPT 1 - rather
        # than the next one along, or the "pair" would be two boxes carrying
        # different ports. Everything else takes the lowest free run of
        # trunks, which is exactly the old first-come order whenever no
        # backup has jumped the queue.
        index = None
        primary = placed_by_id.get(cvt.get('backupOf'))
        if primary is not None and block_count:
            want = primary['trunkIndex'] + block_count
            if (want + takes <= trunks
                    and all(t not in taken for t in range(want, want + takes))):
                index = want
        if index is None:
            index = 0
            while any(t in taken for t in range(index, index + takes)):
                index += 1
        taken.update(range(index, index + takes))
        if block_count and index + takes <= trunks:
            block = ((index // 2) if adjacent else index) % block_count
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
            # Only a TYPED template comes back as a value; unset - and the
            # birth-stamped default of old files - reads as '' so the panel
            # shows the derived text where derived text belongs, in the
            # placeholder. Same shape as returnLabelTemplate below it.
            'portLabelTemplate': typed_port_label_template(cvt),
            'returnLabelTemplate': cvt.get('returnLabelTemplate') or '',
            'portCount': size,
            'firstPort': first,
            'trunkIndex': index,
            'trunksIn': takes,
            'trunkBlock': block,
            # A second delivery of ports an earlier box already carries: OPT 3
            # backing up OPT 1, or a copy OPT mirroring the card's own copper.
            'duplicateOf': earlier['id'] if earlier else None,
            # The NovaStar pair link, carried through so the panel can say
            # "backs up X" about the box somebody may want to delete.
            'backupOf': cvt.get('backupOf') or None,
            'beyondTrunks': over_trunk,
            'ports': [],
        }
        cvts.append(resolved)
        placed_by_id[resolved['id']] = resolved
        if size:
            claimed = max(claimed, first + size - 1)

    # A box can only claim past the ceiling by hanging off a trunk that is not
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
        owner, owner_source = _label_owner(cvt, card, proc)
        source = owner_source
        # A port is numbered within whatever is naming it. On the box, because
        # that is what is silkscreened on its face; on the card otherwise -
        # which matters the moment a card carries two unnamed boxes, where
        # numbering both from 1 would print the same eight labels twice.
        numbered = local if owner_source == 'cvt' else number
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
        # one of its own. The ladder, top rung wins:
        #
        #   1. a name typed on THIS port's return end;
        #   2. the return template on the device naming the port - the
        #      "template spot for naming all backups the same way we do for
        #      primary", read off the same owner the primary reads, because
        #      the backup loom is labelled off the same box the primary is;
        #   3. the derived return (derive_return_label): the primary's
        #      leading P turned into an R - P1-1 out, R1-1 back - which is
        #      what P1 / R1 said before a processor was naming anything;
        #      a primary with no P to swap takes an R after it (SR-1R);
        #   4. nothing - an unassigned port, or a card nobody named, leaves
        #      the screen's own R# template doing the work exactly as before.
        manual_return = return_port_name(card, number)
        return_template = ''
        template_name = None
        if owner is not None:
            if owner_source == 'processor':
                # A processor lends its name to the card's templates, return
                # side included - the same loan the primary takes.
                return_template = (card.get('returnLabelTemplate') or '').strip()
                template_name = proc.get('name')
            else:
                return_template = (owner.get('returnLabelTemplate') or '').strip()
                template_name = owner.get('name')
        if manual_return:
            return_label = manual_return
            return_source = 'manual'
        elif return_template:
            return_label = render_port_label(template_name, return_template,
                                             numbered)
            return_source = 'template'
        else:
            return_label = derive_return_label(label)
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
        # A value only where somebody typed one - the default lives in the
        # panel's placeholder, and a stored copy of it (stamped at birth by
        # every version before v0.11.2) reads as absent. See
        # typed_port_label_template.
        'portLabelTemplate': typed_port_label_template(card),
        # The backup side's template. No default: absent means rung 3 of the
        # return ladder - derive_return_label - is doing the work, and the
        # panel's placeholder says so.
        'returnLabelTemplate': card.get('returnLabelTemplate') or '',
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
        # The trunks' line rate, where the sheet states one. The panel's box
        # picker filters on it the same way the server refuses on it - a
        # 40G OPT offers only the 40G box, and vice versa.
        'trunkRate': device.get('trunkRate'),
        # Whether hanging a box on a trunk gets you ports you did not already
        # have. On an H_16xRJ45+2xfiber it does not: the OPTs copy Ethernet
        # 1-8 and 9-16, so a box there is somewhere else to plug into the same
        # sixteen. The panel has to say so out loud, because the obvious
        # reading of "16 RJ45 plus 2 fiber plus a breakout box" is that the
        # ports add up, and they do not.
        'trunkDelivery': device.get('trunkDelivery', 'distinct'),
        'trunksCopyOwnPorts': device.get('trunkDelivery') == 'copy',
        # Trunks, not boxes: two CVT4K-S fill a four-trunk card.
        'trunksUsed': used_trunks,
        'trunksFree': max(0, (trunks or 0) - used_trunks),
        # The vendor's fixed backup pairing, where one is documented and
        # redundancy is on - derived every resolve, stored nowhere, because a
        # fact is not project state and must not become editable by accident.
        'redundancyPairing': redundancy_pairing(device,
                                                proc.get('redundancy')),
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
        # Stated beside the checkbox that turns redundancy on: WHICH output
        # backs which, where the vendor fixes it. A fact the panel displays,
        # never a control - Brompton pairs adjacent outputs automatically and
        # offers no other arrangement.
        'redundancyPairing': redundancy_pairing(device, proc.get('redundancy')),
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
