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
  copy/backup; MX40 Pro is 40 or 20 by optical mode. Those are modes on the
  device, chosen per instance, not separate devices. A redundant Brompton
  keeps every socket on the drawing and halves only what is USABLE - the
  vendor's own capacity tool says half, and the halving lands on roles
  (resolve_card's `usable`, the backup mapping), never on socket numbers.
"""
import json
import math
import os
import re

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


def is_chassis(device):
    """Whether a catalog device is a card chassis - a unit whose outputs are
    the cards in its slots - as opposed to a one-box unit whose face IS its
    outputs. Read off the catalog's `form` and nothing else: the ruling
    (2026-09-24) is "the H series and MX6000 and 2000 are the only card
    based processors. all others should only have 1 name slot", and the
    catalog is the one statement of which devices those are."""
    return (device or {}).get('form') == 'chassis'


def unit_is_chassis(proc):
    return is_chassis(get_device((proc or {}).get('deviceId')))


def is_box_fed(device):
    """Whether a catalog device has NO fixture ports of its own - every port
    it will ever drive comes out of a breakout box on one of its trunks.
    Read off the catalog's `requiresDistribution` and nothing else. On such
    a device a port outside a box does not exist: the ruling (2026-09-24)
    is "SX40's can't use ports outside of an XD box ... we need to remove
    that functionality" and "same goes for Helios", and the catalog is the
    one statement of which devices those are (the SX40 and the HELIOS
    Standard 8K / 4K carry the flag; the HELIOS Jr, 1G copper straight to
    tiles, does not and keeps its own ports)."""
    return bool((device or {}).get('requiresDistribution'))


def box_fed_device_ids():
    """The ids of every catalog processor that is_box_fed - the set the
    rule applies to, taken from the catalog so a test can name the rule
    without naming the models."""
    return sorted(d['id'] for d in devices('processor') if is_box_fed(d))


def card_is_unit_face(card, proc):
    """Whether this card IS its processor - the fixed card new_processor
    gives a one-box unit so the slot / card / box / port shape holds all the
    way down. Such a card has no name of its own: the unit has exactly one
    name slot, the processor's, and anything typed on the card is not read
    (adopt_fixed_card_names moves a legacy card name up on load). Decided
    by the catalog's form when the device is known; a card born fixed says
    the same thing when it is not."""
    device = get_device((proc or {}).get('deviceId'))
    if device:
        return not is_chassis(device)
    return bool((card or {}).get('fixed'))


def card_display_name(card, proc):
    """The name a card goes by in a message or a tag: its own typed name on
    a chassis, the unit's name for a one-box's fixed card, else the model."""
    if card_is_unit_face(card, proc):
        typed = ((proc or {}).get('name') or '').strip()
    else:
        typed = ((card or {}).get('name') or '').strip()
    return typed or (card or {}).get('deviceName') \
        or (get_device((card or {}).get('deviceId')) or {}).get('name') \
        or (card or {}).get('id') or ''



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

    Only Brompton documents one, and each rule arrived verbatim, per device.
    The first: "SX40s and SQ200, A back up to B, C back up to D automatically
    - that is the only way it works for Brompton." The second (2026-08-23)
    named one more: the S8 "does 1to2 and so on" - adjacent PORTS this time,
    because the S8 has no trunks to letter, its eight RJ45s pair directly.
    Fixed adjacent pairs either way, so the pairing is REPORTED as a fact,
    never offered as a choice; there is nothing here for a caller to edit and
    no storage for an alternative arrangement. The S4 and M2 stay out: the
    ruling named the S8 only, and the plausible extension is still an
    invented one.

    `pairs` letters the device's trunks where it has trunks to letter, and
    numbers its ports where it has no trunks but a settled port count (the
    S8). Where neither holds - the SQ200 publishes no output count - `pairs`
    is empty: lettering outputs nobody has counted would be a guessed ceiling
    wearing a different hat. The statement still states the rule.

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
    if trunks:
        marks = [chr(ord('A') + i) for i in range(trunks)]
    else:
        count = port_capacity(device.get('id'))['count'] or 0
        marks = [str(n) for n in range(1, count + 1)]
    pairs = [{'primary': marks[i], 'backup': marks[i + 1]}
             for i in range(0, len(marks) - 1, 2)]
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


# The data-redundancy shapes a card can run. The first three per the user's
# design (verbatim): "by default do redundancy as 1 to 1 aka the way brompton
# does it and novastar when using a second sending card and then give the
# option for sequential where 1 is backed up by 2 on the same unit/sending
# card and also give the option for say 1 is backed up to whatever port you
# want." The fourth, 'halves', per the 2026-08-27 ruling: "say i have 1-8 on
# processor 1 and 9-16 as backups? i need to be able to set those to backup"
# - within one card, the back half of the ports carries the front half's
# returns (port N returned on port N + half). It is the one arrangement whose
# main and return genuinely wear DIFFERENT numbers, which is why it exists as
# a mode of its own rather than eight manual picks.
REDUNDANCY_MODES = ('1to1', 'sequential', 'halves', 'manual')


def card_redundancy_shape(card, proc, device=None):
    """The data-redundancy shape in force on one card, or None with it off.

    Returns {'mode', 'forced', 'level'}:

    * mode '1to1' - the default: this card is mirrored by a designated
      backup card/unit (card['backupCardId']), main port N returned on the
      backup's port N. The main keeps every port; the backup unit is what
      redundancy consumes.
    * mode 'sequential' - within the card: 1 backed by 2, 3 by 4. Odd ports
      are mains, even ports are their returns, so half the ports are usable.
    * mode 'halves' - within the card: the back half backs the front half,
      1 returned on 9 of 16. Same cost as sequential - half the ports are
      usable - but the pairs sit half a card apart instead of adjacent.
    * mode 'manual' - per port, sparse (card['backupPorts']): a main is
      backed only where somebody named a backup port, and by exactly the
      port they named. Nothing is derived for the rest - manual is explicit.

    `forced` is True where the VENDOR fixes the shape - Brompton's adjacent
    pairing - and there the stored mode is never consulted: a documented rule
    is a fact, not a default. `level` says what the fixed pairing pairs:
    'trunk' where the device has trunks (SX40 - A backs up to B, enforced in
    the trunk blocks), 'port' where it does not (S8 - 1 backed by 2, the
    same shape sequential mode chooses). A device whose sheet says
    redundancy is not supported at all (T1) gets no shape, ever.
    """
    if not (proc or {}).get('redundancy'):
        return None
    if device is None:
        device = get_device((card or {}).get('deviceId')) or {}
    red = device.get('redundancy') or {}
    if red.get('supported') is False:
        return None
    if red.get('pairing') == 'adjacent':
        return {'mode': 'sequential', 'forced': True,
                'level': 'trunk' if device.get('trunks') else 'port'}
    mode = (card or {}).get('redundancyMode') or '1to1'
    if mode not in REDUNDANCY_MODES:
        mode = '1to1'
    return {'mode': mode, 'forced': False, 'level': 'port'}


def trunks_in(cvt_device):
    """How many OPT trunks a box takes IN. One unless the table says otherwise.

    This is the number that stops a box being counted by its nameplate. A
    CVT4K-S is 2 OPT in - its four LC connectors are TWO optical ports, because
    LC is duplex, and counting connectors would double every box on the list
    exactly the way counting them doubled the four-fiber cards.
    """
    return (cvt_device or {}).get('trunksIn') or 1


def held_trunk(cvt):
    """The trunk a box record holds, 0-based, or None where it holds none.
    Stamped by hold_box_trunks (a box delete on a box-fed device) and
    honored by resolve_card's pre-pass; never typed, never settable over
    the box PUT."""
    t = (cvt or {}).get('trunk')
    if isinstance(t, bool) or not isinstance(t, int) or t < 0:
        return None
    return t


def hold_box_trunks(card, resolved_card):
    """Stamp every box on a card with the trunk it resolves to right now,
    so a delete beside it cannot slide it. Skips a box hanging past the
    trunks (it has no trunk to hold). In place, idempotent."""
    where = {b.get('id'): b for b in (resolved_card or {}).get('cvts') or []}
    for cvt in (card or {}).get('cvts') or []:
        box = where.get(cvt.get('id'))
        if not box or box.get('beyondTrunks') \
                or not isinstance(box.get('trunkIndex'), int):
            continue
        cvt['trunk'] = box['trunkIndex']


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


def vendor_mismatch(card_device, box_device):
    """Whether these two are different vendors' metal, with both sheets
    saying so.

    The rule is one sentence and this is the one place it is written: a box
    only hangs off its own vendor's trunks, because - as _fills_the_card has
    always put it - "naming a Brompton box on a NovaStar card would be advice
    nobody can take". It reads the same whether the answer stops the picker
    OFFERING the box (app-processors.js's box picker) or stops can_add_cvt
    TAKING it.

    Both vendors must be stated. Where either sheet names none, nothing is
    refused on a vendor nobody wrote down - the same no-inference rule the
    trunk rates and the port ceilings live by.
    """
    card_vendor = (card_device or {}).get('vendor')
    box_vendor = (box_device or {}).get('vendor')
    return bool(card_vendor and box_vendor and card_vendor != box_vendor)


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
    # A BOX ONLY HANGS OFF ITS OWN VENDOR'S TRUNKS - vendor_mismatch above,
    # the same rule _fills_the_card declines to advise by, now refusing the
    # add as well. Both vendors go in the reason: which side is the wrong one
    # is the whole question, and the answer might be "swap the card".
    if vendor_mismatch(device, box):
        return False, (f'{box.get("name", device_id)} is a '
                       f'{box.get("vendor")} box and {name} is '
                       f'{device.get("vendor")} - a box only hangs off its '
                       f'own vendor’s trunks.')
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
    would be advice nobody can take - and that rule is vendor_mismatch, shared
    with can_add_cvt so the list advises by exactly what the server takes.
    """
    trunks = card_device.get('trunks') or 0
    if not trunks or not ceiling:
        return []
    out = []
    for box in devices('cvt'):
        if vendor_mismatch(card_device, box):
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
        card = new_card(device_id, f'{seq}f', fixed=True)
        # A device with no fixture ports of its own arrives WITH its boxes
        # where the catalog names a default one. The SX40 is the case, by
        # ruling (2026-08-25): "The sx40 by default has to use 10 port
        # breakout boxes" - so a fresh SX40 is four XDs, ports 1-10 to
        # 31-40, the way one leaves the shop. A default and nothing more:
        # each box deletes like any box, and another documented box type
        # can take its trunk (though behind an SX40 every documented box
        # still delivers 10 - the trunk cap sees to that).
        default_box = device.get('defaultCvt')
        if device.get('requiresDistribution') and default_box:
            for i in range(device.get('trunks') or 0):
                box = new_cvt(default_box, f'{seq}f{i}')
                if box:
                    card['cvts'].append(box)
        proc['slots'].append({'index': 0, 'card': card})
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


def sync_next_processor_seq(project):
    """Rebase ``project['next_processor_seq']`` so no tree id is ever reused.

    The processor counterpart to app.py's sync_next_group_seq, for the same
    reason: the counter lives ON the project, but the mutating routes answer
    with only the resolved tree, so the client's copy - the one undo/redo
    PUTs back through the restore funnel - can carry a stale counter or none
    at all. Without this, add proc1 and proc2, undo once, add again: _next_seq
    falls back to 1 and mints a second ``proc1``, and every edit after that
    lands on whichever of the two _find_processor meets first.

    Seeds above the highest run already minted anywhere in the tree - proc,
    card and cvt ids all draw from the one counter (so do the show's snake
    and fiber cable ids, snk and fib), and the heal's boxes
    carry it inside a ``cvt<N>f<i>`` id. Never lowers a counter that is
    ahead, so restoring the same project twice does not change it. A project
    with no processors and no counter is left byte-for-byte untouched - the
    same read-must-not-stamp rule the processor routes hold themselves to.
    """
    if not isinstance(project, dict):
        return 1
    processors = project.get('processors') or []
    snakes = project.get('snakes') or []
    fibers = project.get('fiberCables') or []
    if not processors and not snakes and not fibers \
            and 'next_processor_seq' not in project:
        return 1
    max_n = 0

    def _note(raw_id):
        nonlocal max_n
        m = re.match(r'^(?:proc|card|cvt|snk|fib)(\d+)', raw_id or '')
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n

    for proc in processors:
        _note((proc or {}).get('id'))
        for slot in (proc or {}).get('slots') or []:
            card = (slot or {}).get('card')
            if card:
                _note(card.get('id'))
                for snake in card.get('snakes') or []:
                    _note((snake or {}).get('id'))
                for cvt in card.get('cvts') or []:
                    _note((cvt or {}).get('id'))
                    for snake in (cvt or {}).get('snakes') or []:
                        _note((snake or {}).get('id'))
    # The show's own snakes draw from the same counter (they hold sockets
    # from several devices now, so they cannot live on any one of them).
    for snake in snakes:
        _note((snake or {}).get('id'))
    # ...and so do the show's fiber cables (``fib<N>`` - a TAC is shared by
    # several boxes, so it lives on the show beside the snakes).
    for cable in fibers:
        _note((cable or {}).get('id'))
    try:
        stored = int(project.get('next_processor_seq'))
    except (TypeError, ValueError):
        stored = 0
    project['next_processor_seq'] = max(stored, max_n + 1)
    return project['next_processor_seq']


# ── Data cables: snakes and port home runs ────────────────────────────────
#
# "we need to have the same option for data homeruns. we can combine ports
# into a snake as well as adding lengths to each if not snakes." (user,
# 2026-09-06). The shape mirrors power's distro → multi (one home run) →
# circuit cable: a card or box → a SNAKE (one name, one home run, N ports)
# → a port's own cable. Both stores live on the HARDWARE record - the
# processor card for the ports it carries on its own face, the breakout
# box (``cvt``) for the ports it delivers - because a home run belongs to
# the socket, not to the screen plugged into it. That is the one place this
# differs from power, where a circuit cable is per-screen programming and a
# clear forgets it: a port released from a screen KEEPS its snake and cable,
# since the loom is still hanging off that socket whatever the wall does.
#
#   node['portCables'] = {str(socket): {ft?, connector?}}
#
# A SNAKE is no longer one of those stores. "Any sockets, any device"
# (user, 2026-09-09): one snake carries A-1..A-4 and B-1..B-4 together, so
# it belongs to the SHOW and names its members (project['snakes'] - see the
# show-snake section below). A device PUT may still carry ``snakes`` - old
# clients, old undo snapshots - and that door is honoured by folding the
# list straight into the show (apply_cable_store stores it, the route
# migrates it, and the per-device key never survives the request).
#
# Sockets are the CARD-WIDE port numbers (port['number']) - the same key the
# assignment, the chips and the port-name stores run on - so a box that
# delivers the card's 1-8 again stores against 1-8 like the box before it,
# each in its own record. A port is in at most one snake. A port in a snake
# rides the snake's home run; its own ``portCables`` entry, where it has
# one, is the EXTENSION from the snake's fan-out to that panel - "when i
# use a snake i need to be able to add a secondary cable length incase i
# need an extension" (2026-09-07) - the same shape as power's per-circuit
# cable under a multi. ``connector`` null means "follows the port" - the
# connector the catalog documents for the device the port comes out of
# (data_port_connector), and NOTHING where the catalog is silent: a
# reading that guessed copper for an undocumented box would be a hardware
# assumption, so it prints the length alone instead. A snake's way count
# is whatever was put in it - no 4/6/12-way shapes are assumed.
#
# Fiber is NOT a port's or a snake's connector: "panels dont take fiber.
# what would take fiber is processor to breakout box" (2026-09-07). The
# fiber trunk is the breakout box's - its links onto the show's fiber
# cables (the fiber-cable section below) - and the list here is copper
# only. A file saved with a 'fiber' pick on a port or
# a snake reads as "follows the port" (resolved_port_cables,
# resolved_show_snakes).

DATA_CABLE_CONNECTORS = (
    {'id': 'cat', 'name': 'CAT'},
)

# The catalog's connector words, mapped to the cable connector they imply.
# Only documented copper maps: 'rj45' is CAT. A fiber-kind card's loose
# ports follow nothing - the plug on a panel lead off a fiber card is not
# documented, so no plug is guessed.
_PORT_KIND_CONNECTOR = {'rj45': 'cat'}

SNAKE_NAME_PREFIX = 'SNAKE '


def data_cable_connectors():
    return [dict(c) for c in DATA_CABLE_CONNECTORS]


def data_cable_connector_ids():
    return [c['id'] for c in DATA_CABLE_CONNECTORS]


def data_port_connector(cvt_device, card_device, proc_device):
    """The cable connector a port FOLLOWS, from the catalog alone.

    The nearest device downstream that documents a ``connector`` answers:
    the breakout box the port comes out of, else the card, else the
    processor. None where none of them says - the reading then carries no
    connector name rather than an invented one.
    """
    for device in (cvt_device, card_device, proc_device):
        kind = (device or {}).get('connector')
        if kind in _PORT_KIND_CONNECTOR:
            return _PORT_KIND_CONNECTOR[kind]
    return None


def _snake_letter_name(taken, prefix=SNAKE_NAME_PREFIX):
    """The first free default name - SNAKE A, SNAKE B, ... SNAKE Z, SNAKE AA.
    The fiber cables letter the same way under their own prefix ("TAC A",
    "MTP A")."""
    n = 0
    while True:
        letters = ''
        k = n
        while True:
            letters = chr(ord('A') + k % 26) + letters
            k = k // 26 - 1
            if k < 0:
                break
        name = prefix + letters
        if name not in taken:
            return name
        n += 1


def _cable_ft(value):
    """A stored length: a positive finite number, else None (no length).

    Zero and blank both mean "no length" - the same reading the power sheet
    gives a blank field - so nothing stores a 0 that later prints as 0'.
    """
    if value is None or value == '':
        return None
    try:
        ft = float(value)
    except (TypeError, ValueError):
        return None
    if ft != ft or ft in (float('inf'), float('-inf')) or ft <= 0:
        return None
    return int(ft) if ft == int(ft) else ft


def check_cable_store(data, port_numbers, what='card'):
    """Why a PUT's ``snakes`` / ``portCables`` cannot be stored, or None.

    Every refusal names its reason: a socket the card or box does not have,
    a port in two snakes, a length that is not a non-negative number, a
    connector the list does not know. Nothing is stored on a refusal.
    """
    allowed = set(int(n) for n in port_numbers)
    ids = set(data_cable_connector_ids())

    def _check_cable(rec, where):
        if rec is None:
            return None
        if not isinstance(rec, dict):
            return f'{where}: a cable is an object with ft and connector.'
        if 'ft' in rec and rec['ft'] not in (None, ''):
            try:
                ft = float(rec['ft'])
            except (TypeError, ValueError):
                return f'{where}: ft must be a number of feet.'
            if ft != ft or ft < 0 or ft in (float('inf'), float('-inf')):
                return f'{where}: ft must be a non-negative number.'
        conn = rec.get('connector')
        if conn not in (None, '') and conn not in ids:
            return (f'{where}: unknown connector {conn!r} - one of '
                    f'{", ".join(sorted(ids))}, or null to follow the port.')
        return None

    if 'snakes' in data:
        snakes = data.get('snakes')
        if snakes is None:
            snakes = []
        if not isinstance(snakes, list):
            return 'snakes must be a list.'
        seen = set()
        for i, snake in enumerate(snakes):
            where = f'snake {i + 1}'
            if not isinstance(snake, dict):
                return f'{where}: a snake is an object with name, ft and ports.'
            if (snake.get('name') is not None
                    and not isinstance(snake.get('name'), str)):
                return f'{where}: name must be text.'
            ports = snake.get('ports')
            if not isinstance(ports, list):
                return f'{where}: ports must be a list of socket numbers.'
            for raw in ports:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    return f'{where}: port {raw!r} is not a socket number.'
                if n not in allowed:
                    return (f'{where}: there is no socket {n} on this {what}'
                            + (f' (sockets {min(allowed)}-{max(allowed)})'
                               if allowed else '') + '.')
                if n in seen:
                    return (f'{where}: socket {n} is already in another '
                            f'snake - a port rides one snake.')
                seen.add(n)
            why = _check_cable(snake, where)
            if why:
                return why
    if 'portCables' in data:
        cables = data.get('portCables')
        if cables is None:
            cables = {}
        if not isinstance(cables, dict):
            return 'portCables must be an object keyed by socket number.'
        for key, rec in cables.items():
            try:
                n = int(key)
            except (TypeError, ValueError):
                return f'portCables: {key!r} is not a socket number.'
            if n not in allowed:
                return (f'portCables: there is no socket {n} on this {what}'
                        + (f' (sockets {min(allowed)}-{max(allowed)})'
                           if allowed else '') + '.')
            why = _check_cable(rec, f'port {n}')
            if why:
                return why
    return None


def apply_cable_store(node, data, port_numbers, next_seq):
    """Store a checked ``snakes`` / ``portCables`` payload on a card or box.

    Normalises as it stores: sockets sorted and unique per snake, an empty
    snake dropped. A ``portCables`` entry on a snaked socket is KEPT: it is
    that socket's extension from the snake's fan-out (the module comment
    above). Either key alone is a valid PUT; the other store is left as it
    was and re-pruned against the result.

    ``snakes`` is the LEGACY door (the show owns snakes now): the list is
    parked on the record for the caller to fold into project['snakes']
    straight away - migrate_device_snakes mints the id and the default name
    there, show-wide, because ``SNAKE A`` has to be free across the show and
    not just on this one card.
    """
    if 'snakes' in data:
        out = []
        for snake in data.get('snakes') or []:
            ports = sorted({int(p) for p in (snake.get('ports') or [])})
            if not ports:
                continue
            rec = {'ports': ports}
            stored_id = (snake.get('id') or '').strip()
            if stored_id:
                rec['id'] = stored_id
            name = (snake.get('name') or '').strip()
            if name:
                rec['name'] = name
            ft = _cable_ft(snake.get('ft'))
            if ft is not None:
                rec['ft'] = ft
            conn = snake.get('connector')
            if conn in data_cable_connector_ids():
                rec['connector'] = conn
            out.append(rec)
        if out:
            node['snakes'] = out
        else:
            node.pop('snakes', None)
    if 'portCables' in data:
        out = {}
        for key, rec in (data.get('portCables') or {}).items():
            if rec is None:
                continue
            ft = _cable_ft(rec.get('ft'))
            conn = rec.get('connector')
            conn = conn if conn in data_cable_connector_ids() else None
            if ft is None and conn is None:
                continue
            cable = {}
            if ft is not None:
                cable['ft'] = ft
            if conn is not None:
                cable['connector'] = conn
            out[str(int(key))] = cable
        if out:
            node['portCables'] = out
        else:
            node.pop('portCables', None)
    prune_cable_store(node, port_numbers)


def prune_cable_store(node, port_numbers):
    """Drop what the device no longer has: sockets past its port range (a
    card whose mode halved it, a box whose trunk cap shrank it). A cable on
    a snaked socket stays - it is the socket's extension off the snake, not
    a second home run. Keys vanish when nothing is left, so a plain card
    stays a plain card in the file. (The show's snakes are pruned against
    the same ranges by prune_show_snakes.)
    """
    allowed = set(int(n) for n in port_numbers)
    cables = {}
    for key, rec in (node.get('portCables') or {}).items():
        try:
            n = int(key)
        except (TypeError, ValueError):
            continue
        if n not in allowed or not rec:
            continue
        cables[str(n)] = rec
    if cables:
        node['portCables'] = cables
    else:
        node.pop('portCables', None)


def _stored_connector(rec):
    """A stored connector the list still offers, else None - "follows the
    port". A 'fiber' pick from before 2026-09-07 reads as None, so an old
    file opens without a plug the sheet cannot show."""
    conn = (rec or {}).get('connector') or None
    return conn if conn in set(data_cable_connector_ids()) else None


def resolved_port_cables(node):
    """One device's port cables as the panel reads them: always present
    (empty when absent) so no reader has to guard the key, keys as strings -
    the JSON shape either way."""
    cables = {}
    for key, rec in (node.get('portCables') or {}).items():
        cables[str(key)] = {
            'ft': (rec or {}).get('ft'),
            'connector': _stored_connector(rec),
        }
    return cables


# ── Show snakes: one snake, sockets from any device ───────────────────────
#
# "also when i pair things in snakes they need to be able to be able to be
# grouped together as well as done across cvt's" (user, 2026-09-09), and
# asked what one snake may hold: "Any sockets, any device". An 8-way carries
# a card's A-1..A-4 and its backup box's B-1..B-4 in ONE loom, so a snake
# cannot live on either device - it lives on the show and names its members:
#
#   project['snakes'] = [{id, name, ft?, connector?,
#                         members: [{kind: 'card'|'cvt', id, socket}, ...]}]
#
# `socket` is the CARD-WIDE port number, the same key portCables and the
# chips run on, and `kind`/`id` is the device that DELIVERS that socket
# right now: the breakout box where one carries it, the card otherwise.
# That normalisation (prune_show_snakes) is the whole reason a member is a
# pair rather than a socket: before it, a snake typed on a card went
# invisible the moment a box was hung on that card, because every reader is
# routed to the box and the box's store had never heard of it.
#
# A socket rides ONE snake. A member's own portCables entry stays where it
# always was - on its device - and is that socket's EXTENSION from the
# snake's fan-out.

SNAKE_MEMBER_KINDS = ('card', 'cvt')


def show_snakes(project):
    """The show's snakes, never creating the key on a read."""
    return (project or {}).get('snakes') or []


def snake_device_index(processors):
    """Every device a snake may name, off the RESOLVED tree.

    Returns (devices, delivers):
      devices  {(kind, id): {'sockets', 'title', 'cardId', 'procId', 'order'}}
      delivers {(cardId, socket): boxId} - the box a reader is routed to
               for that socket (the FIRST box carrying it, resolve_card's
               own order, which is what _dataPortOwner picks).
    """
    devices = {}
    delivers = {}
    order = 0
    for proc in resolve_all(processors or []):
        for slot in proc.get('slots') or []:
            card = (slot or {}).get('card')
            if not card:
                continue
            devices[('card', card['id'])] = {
                'sockets': {p['number'] for p in card.get('ports') or []},
                'title': card_display_name(card, proc),
                'cardId': card['id'], 'procId': proc.get('id'),
                'order': order,
            }
            order += 1
            for box in card.get('cvts') or []:
                nums = {p['number'] for p in box.get('ports') or []}
                devices[('cvt', box['id'])] = {
                    'sockets': nums,
                    'title': box.get('displayTitle')
                             or (box.get('name') or '').strip()
                             or box.get('deviceName') or box['id'],
                    'cardId': card['id'], 'procId': proc.get('id'),
                    'order': order,
                }
                order += 1
                for n in nums:
                    delivers.setdefault((card['id'], n), box['id'])
    return devices, delivers


def _member(raw):
    """One member as stored, or None where the shape is not one."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get('kind')
    ident = raw.get('id')
    if kind not in SNAKE_MEMBER_KINDS or not isinstance(ident, str) \
            or not ident:
        return None
    try:
        socket = int(raw.get('socket'))
    except (TypeError, ValueError):
        return None
    return {'kind': kind, 'id': ident, 'socket': socket}


def check_snake_members(raw_members, devices, taken, what='snake'):
    """Why these members cannot form a snake, or None.

    `taken` maps (kind, id, socket) -> the name of the snake already on it,
    so the refusal can say which one. Every refusal names its reason, the
    cable stores' rule.
    """
    if not isinstance(raw_members, list) or not raw_members:
        return (f'{what}: members must be a list of '
                f'{{kind, id, socket}} - a snake holds at least one socket.')
    seen = set()
    for raw in raw_members:
        member = _member(raw)
        if member is None:
            return (f'{what}: a member is {{kind: "card" or "cvt", id, '
                    f'socket}} - got {raw!r}.')
        device = devices.get((member['kind'], member['id']))
        if device is None:
            word = 'breakout box' if member['kind'] == 'cvt' else 'card'
            return (f'{what}: there is no {word} {member["id"]} in this '
                    f'project.')
        if member['socket'] not in device['sockets']:
            sockets = device['sockets']
            return (f'{what}: there is no socket {member["socket"]} on '
                    f'{device["title"]}'
                    + (f' (sockets {min(sockets)}-{max(sockets)})'
                       if sockets else '') + '.')
        key = (member['kind'], member['id'], member['socket'])
        if key in seen:
            return (f'{what}: {device["title"]} socket {member["socket"]} '
                    f'is named twice.')
        seen.add(key)
        if key in taken:
            return (f'{what}: {device["title"]} socket {member["socket"]} '
                    f'is already in {taken[key]} - a socket rides one '
                    f'snake.')
    return None


def snake_sockets_taken(project, skip_id=None):
    """{(kind, id, socket): snake name} over the show, one snake skipped."""
    taken = {}
    for snake in show_snakes(project):
        if skip_id is not None and snake.get('id') == skip_id:
            continue
        name = snake.get('name') or 'a snake'
        for raw in snake.get('members') or []:
            member = _member(raw)
            if member:
                taken[(member['kind'], member['id'], member['socket'])] = name
    return taken


def normalise_snake_members(raw_members, devices):
    """Members as they are stored: shaped, deduped, in tray order."""
    out = []
    seen = set()
    for raw in raw_members or []:
        member = _member(raw)
        if not member:
            continue
        key = (member['kind'], member['id'], member['socket'])
        if key in seen:
            continue
        seen.add(key)
        out.append(member)
    out.sort(key=lambda m: (devices.get((m['kind'], m['id']), {})
                            .get('order', 0), m['socket']))
    return out


def snake_letter_name(project):
    """The first free SNAKE letter across the SHOW (not one device)."""
    taken = {(s.get('name') or '').strip()
             for s in show_snakes(project)}
    return _snake_letter_name(taken)


def store_show_snake(project, rec, devices, next_seq, snake=None):
    """Write one show snake's fields onto `snake` (a new one when None).

    Only what the body carried moves; a blank name is given the first free
    show-wide letter, and an id is minted off the processor counter
    (``snk<N>`` - one counter, so undo cannot resurrect a collision).
    """
    fresh = snake is None
    if fresh:
        snake = {'id': (rec.get('id') or '').strip() or f'snk{next_seq()}',
                 'members': []}
    if 'members' in rec:
        snake['members'] = normalise_snake_members(rec.get('members'),
                                                   devices)
    if 'name' in rec or fresh:
        name = (rec.get('name') or '').strip()
        snake['name'] = name or snake.get('name') \
            or snake_letter_name(project)
    if 'ft' in rec or fresh:
        ft = _cable_ft(rec.get('ft'))
        if ft is None:
            snake.pop('ft', None)
        else:
            snake['ft'] = ft
    if 'connector' in rec or fresh:
        conn = rec.get('connector')
        if conn in data_cable_connector_ids():
            snake['connector'] = conn
        else:
            snake.pop('connector', None)
    if fresh:
        project.setdefault('snakes', []).append(snake)
    return snake


def prune_show_snakes(project, processors=None):
    """Re-home every member onto the device that DELIVERS its socket, drop
    what no device delivers any more, and keep a socket on one snake.

    Three jobs, one walk, and idempotent so a project restored twice does
    not change:

    - RE-HOME. A member on a card whose socket a breakout box now carries
      becomes that box's, because that is where every reader looks (a box
      names the sockets it delivers - resolve_card). This is the fix for a
      snake typed on a card before its box existed, which used to vanish
      whole. (A box DELETED takes its members with it - the loom was
      hanging off the box - which is the DROP rule below, not this one.)
    - DROP. A member naming a device that is not there (a deleted box, a
      cleared slot) or a socket the device no longer has (a mode that
      halved the card, a trunk cap that shrank the box) goes, and a snake
      left with no members goes with it.
    - ONE SNAKE PER SOCKET. Where re-homing lands two snakes on one socket
      - a card's leftover snake meeting the box's own - the one already
      sitting on that device keeps it and the re-homed member is dropped.

    Returns True where anything changed.
    """
    snakes = show_snakes(project)
    if not snakes:
        if 'snakes' in project and not project['snakes']:
            return False
        return False
    devices, delivers = snake_device_index(project.get('processors') or []
                                           if processors is None
                                           else processors)
    before = json.dumps(snakes, sort_keys=True)
    taken = set()
    # Two passes: everything already sitting on the device that delivers it
    # is placed first, so a re-homed member never displaces a member that
    # was right where it belongs.
    placed = {}
    for pas in (0, 1):
        for snake in snakes:
            keep = placed.setdefault(id(snake), [])
            for raw in snake.get('members') or []:
                member = _member(raw)
                if member is None:
                    continue
                device = devices.get((member['kind'], member['id']))
                if device is None:
                    continue
                socket = member['socket']
                if socket not in device['sockets']:
                    continue
                box = delivers.get((device['cardId'], socket))
                home = ('cvt', box) if box else ('card', device['cardId'])
                at_home = (member['kind'], member['id']) == home
                if at_home != (pas == 0):
                    continue
                key = (home[0], home[1], socket)
                if key in taken:
                    continue
                taken.add(key)
                keep.append({'kind': home[0], 'id': home[1],
                             'socket': socket})
    out = []
    for snake in snakes:
        members = normalise_snake_members(placed.get(id(snake)) or [],
                                          devices)
        if not members:
            continue
        snake['members'] = members
        out.append(snake)
    if out:
        project['snakes'] = out
    else:
        project.pop('snakes', None)
    return json.dumps(out, sort_keys=True) != before


def migrate_device_snakes(project):
    """Fold every per-device ``snakes`` list into the show's own list.

    The 2026-09-09 migration, run on the load funnels (and after the legacy
    device PUT, which is the same shape arriving live): a card's or a box's
    snakes become show snakes whose members are that device's sockets, and
    the per-device key is dropped. Old saves open unchanged in effect - what
    changes is that a snake typed on a card whose sockets a box now delivers
    is re-homed onto the box (prune_show_snakes) instead of staying
    invisible.

    Returns True where anything moved.
    """
    if not isinstance(project, dict):
        return False
    moved = False
    seq = [None]

    def next_seq():
        if seq[0] is None:
            seq[0] = sync_next_processor_seq(project)
        n = seq[0]
        seq[0] = n + 1
        project['next_processor_seq'] = seq[0]
        return n

    devices, _delivers = snake_device_index(project.get('processors') or [])
    known = {s.get('id') for s in show_snakes(project)}
    for kind, ident, node in _snake_bearing_nodes(project):
        for snake in node.pop('snakes', None) or []:
            members = [{'kind': kind, 'id': ident, 'socket': int(p)}
                       for p in (snake.get('ports') or [])]
            if not members:
                continue
            rec = dict(snake, members=members)
            if rec.get('id') in known:
                rec.pop('id', None)
            store_show_snake(project, rec, devices, next_seq)
            known.add(project['snakes'][-1]['id'])
            moved = True
    if prune_show_snakes(project):
        moved = True
    return moved


def _snake_bearing_nodes(project):
    """(kind, id, record) for every card and box that could carry a
    per-device ``snakes`` list."""
    for proc in project.get('processors') or []:
        for slot in (proc or {}).get('slots') or []:
            card = (slot or {}).get('card')
            if not card:
                continue
            yield 'card', card.get('id'), card
            for cvt in card.get('cvts') or []:
                yield 'cvt', cvt.get('id'), cvt


def resolved_show_snakes(project):
    """The show's snakes as every reader takes them: members shaped, a
    connector the list no longer offers read as "follows the port"."""
    out = []
    for snake in show_snakes(project):
        members = [m for m in (_member(r) for r in snake.get('members') or [])
                   if m]
        out.append({
            'id': snake.get('id'),
            'name': snake.get('name') or '',
            'ft': snake.get('ft'),
            'connector': _stored_connector(snake),
            'members': members,
        })
    return out


# ── Fiber cables: TAC, MTP and opticalCON, processor to breakout box ──────
#
# "tac is just for stranded fiber" (owner, 2026-09-25). The fiber that
# feeds a breakout box is a CABLE the show owns, and a box's trunk links
# each take strands of one:
#
#   project['fiberCables'] = [{id: 'fib<N>', name, kind, strands, ft?,
#                              connector?, labels, subunits, strandNames,
#                              ownerBoxId?}]
#   cvt['fiberLinks'] = {'p1': {cable, strands: [1, 2]}, 'b1': {...}}
#
# - A TAC or an MTP ("mtp is basically a packaged tac"; its OWN kind by
#   the 2026-09-25 ruling "If i choose tac 12 call it that if i choose mtp
#   12 choose that") has any number of strands and is SHARED: several
#   boxes' links take different strands of one cable. Nothing here keys
#   strand assignment off a connector - every stranded cable, whatever its
#   ends, assigns strands per link.
# - An opticalCON DUO is 2 fibers and a QUAD 4, and each is ONE box's:
#   ownerBoxId names it, and only that box's links (its bound backup's
#   included) take its fibers.
# - A box's links are p1..pK, K = trunks_in (a CVT4K-S takes 2), and
#   b1..bK only where a backup record is BOUND to it - the backup is the
#   same physical box taking a second fiber, so its picks live here, on
#   the primary. A link takes 2 strands, 1 on a box switched to BiDi.
# - A strand is used by one link show-wide.
# - The list is absent when empty, and a read never creates it. A cable
#   no link uses any more goes, the way an emptied snake goes: when the
#   last link lets go of it (settle_fiber, with the cables in use before
#   the request), or its owner box is deleted.
#
# The typed fiberType / fiberFt of 1.3 stay on the box as a NOTE, printed
# as before until any link on that box has a cable; nothing migrates.

FIBER_KINDS = ('tac', 'mtp', 'opticalcon-duo', 'opticalcon-quad')
# The kinds whose strand count is the user's: any positive whole number.
FIBER_STRANDED_KINDS = ('tac', 'mtp')
# The kinds whose fiber count is the connector's.
FIBER_KIND_FIBERS = {'opticalcon-duo': 2, 'opticalcon-quad': 4}
# (A TAC's ends are free text - app-fiber.js offers ST and LC duplex - and
# an MTP names none. The New TAC step's suggested counts live there too.)
FIBER_LABELS = ('colors', 'numbers')
# TIA-598-D, in order, with the swatch the app paints for each.
FIBER_COLORS = (
    ('Blue', '#1F5FA8'), ('Orange', '#F28020'), ('Green', '#1A9A48'),
    ('Brown', '#7A4A2E'), ('Slate', '#777777'), ('White', '#F5F5F5'),
    ('Red', '#B82535'), ('Black', '#1A1A1A'), ('Yellow', '#EDD31C'),
    ('Violet', '#7A3F9E'), ('Rose', '#E09BA8'), ('Aqua', '#5EBFC2'),
)
# BiDi is offered on these vendors' boxes only (the owner's list), read off
# the catalog's vendor - never a model special-cased.
BIDI_VENDORS = ('NovaStar', 'Megapixel')
_FIBER_NAME_PREFIX = {'tac': 'TAC ', 'mtp': 'MTP ',
                      'opticalcon-duo': 'DUO ', 'opticalcon-quad': 'QUAD '}


def fiber_bidi_allowed(cvt_device):
    """Whether this box's catalog vendor is one BiDi is offered for."""
    return (cvt_device or {}).get('vendor') in BIDI_VENDORS


def fiber_link_keys(trunks, bound):
    """A box's link keys: p1..pK, then b1..bK where a backup is bound."""
    try:
        k = max(1, int(trunks or 1))
    except (TypeError, ValueError):
        k = 1
    keys = [f'p{i}' for i in range(1, k + 1)]
    if bound:
        keys += [f'b{i}' for i in range(1, k + 1)]
    return keys


def fiber_link_title(key):
    """'p1' -> 'Primary 1', 'b2' -> 'Backup 2'."""
    key = str(key or '')
    word = 'Backup' if key.startswith('b') else 'Primary'
    return f'{word} {key[1:]}'


def fiber_strand_name(n, cable=None):
    """One strand as the paper says it (TIA-598-D).

    Blue, Orange, ... Aqua for 1-12; past 12 the colors repeat with a black
    tracer ("14 Orange/Black" - the Black strand takes a WHITE one, "20
    Black/White"), then a double tracer ("26 Orange/Black x2"), a triple,
    and on. A cable in sub-units reads "Orange unit · 2 Orange" - the unit
    is ceil(N/12) in the same colors, the strand its plain color. A cable
    labelled in numbers reads "14". A typed rename wins over all of it.
    The JS twin is fiberStrandName in app-fiber.js; a test pins that the
    two agree.
    """
    cable = cable or {}
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    typed = ((cable.get('strandNames') or {}).get(str(n)) or '')
    if isinstance(typed, str) and typed.strip():
        return typed.strip()
    if n < 1:
        return str(n)
    if cable.get('labels') == 'numbers':
        return str(n)
    color = FIBER_COLORS[(n - 1) % 12][0]
    if cable.get('subunits'):
        unit = FIBER_COLORS[(math.ceil(n / 12) - 1) % 12][0]
        return f'{unit} unit · {(n - 1) % 12 + 1} {color}'
    tier = (n - 1) // 12
    if tier == 0:
        return f'{n} {color}'
    tracer = 'White' if color == 'Black' else 'Black'
    return f'{n} {color}/{tracer}' + (f' x{tier}' if tier > 1 else '')


def show_fiber_cables(project):
    """The show's fiber cables, never creating the key on a read."""
    return (project or {}).get('fiberCables') or []


def fiber_cable_strand_count(cable):
    """How many strands a cable has: the connector's for an opticalCON, the
    stored count for a TAC or an MTP, 0 where none is stored."""
    kind = (cable or {}).get('kind')
    if kind in FIBER_KIND_FIBERS:
        return FIBER_KIND_FIBERS[kind]
    n = (cable or {}).get('strands')
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 \
        else 0


def fiber_cable_type_text(cable):
    """The pull sheet's words for a cable: "TAC 12 · ST", "MTP 24",
    "opticalCON QUAD"."""
    kind = (cable or {}).get('kind')
    if kind == 'opticalcon-duo':
        return 'opticalCON DUO'
    if kind == 'opticalcon-quad':
        return 'opticalCON QUAD'
    word = 'MTP' if kind == 'mtp' else 'TAC'
    text = f'{word} {fiber_cable_strand_count(cable)}'
    conn = ((cable or {}).get('connector') or '').strip() \
        if kind == 'tac' else ''
    return f'{text} · {conn}' if conn else text


def _fiber_link(raw):
    """One stored link, shaped: {cable, strands: [int, ...]}, else None."""
    if not isinstance(raw, dict):
        return None
    cable = raw.get('cable')
    strands = raw.get('strands')
    if not isinstance(cable, str) or not cable or not isinstance(strands,
                                                                 list):
        return None
    out = []
    for s in strands:
        if isinstance(s, bool) or not isinstance(s, int):
            return None
        out.append(s)
    return {'cable': cable, 'strands': out}


def resolved_fiber_links(cvt):
    """A box's links as every reader takes them - always a dict."""
    out = {}
    for key, raw in ((cvt or {}).get('fiberLinks') or {}).items():
        link = _fiber_link(raw)
        if link:
            out[str(key)] = link
    return out


def fiber_link_need(cvt):
    """Strands per link on this box: 1 with BiDi, else 2."""
    return 1 if (cvt or {}).get('bidi') else 2


def fiber_default_name(project, kind):
    """The first free default name for a new cable of `kind`, show-wide:
    TAC A, TAC B ... and MTP A ... each on its own letters (the snakes'
    lettering), DUO 1, QUAD 1 ... numbered."""
    taken = {(c.get('name') or '').strip() for c in show_fiber_cables(project)}
    prefix = _FIBER_NAME_PREFIX.get(kind, 'TAC ')
    if kind in FIBER_KIND_FIBERS:
        n = 1
        while f'{prefix}{n}' in taken:
            n += 1
        return f'{prefix}{n}'
    return _snake_letter_name(taken, prefix)


def fiber_box_index(processors, resolved=None):
    """Every box, raw and resolved side by side, in tree order:
    {boxId: {'raw', 'res', 'procId', 'cardId', 'order'}}."""
    if resolved is None:
        resolved = resolve_all(processors or [])
    raw_boxes = {}
    for proc in processors or []:
        for slot in (proc or {}).get('slots') or []:
            card = (slot or {}).get('card')
            for cvt in (card or {}).get('cvts') or []:
                if cvt and cvt.get('id'):
                    raw_boxes[cvt['id']] = cvt
    out = {}
    order = 0
    for rproc in resolved or []:
        for slot in rproc.get('slots') or []:
            card = (slot or {}).get('card')
            for box in (card or {}).get('cvts') or []:
                raw = raw_boxes.get(box.get('id'))
                if raw is None:
                    continue
                out[box['id']] = {'raw': raw, 'res': box,
                                  'procId': rproc.get('id'),
                                  'cardId': card.get('id'), 'order': order}
                order += 1
    return out


def fiber_box_title(entry):
    res = (entry or {}).get('res') or {}
    return res.get('displayTitle') or (res.get('name') or '').strip() \
        or res.get('deviceName') or res.get('id') or 'a box'


def _apply_fiber_binding(processors, resolved):
    """Bind each backup record to the box it physically IS, tree-wide.

    - Same processor, automatic: a box that backs up another on its card
      (`backupOf` - NovaStar's copy/backup pair, or Brompton's adjacent
      pairing, "an SX40's backup XD on the next trunk is the SAME XD taking
      a second fiber") is bound to it, unless its record says `unbound`.
    - Backup processor, by hand: a box on a card that backs up another
      processor's card (backupFor) carries `boundTo` - one of that
      processor's boxes, picked on its Fiber section - honoured only while
      that relation stands.

    A primary takes one bound backup (the first claim in tree order) and a
    bound backup is nobody's primary. The bound record reads `boundTo` and
    carries no links of its own; its primary reads `boundBackup` and gains
    the backup link keys b1..bK.
    """
    boxes = fiber_box_index(processors, resolved)
    backs = {}
    for rproc in resolved or []:
        for slot in rproc.get('slots') or []:
            card = (slot or {}).get('card')
            if card and card.get('backupFor'):
                backs[card['id']] = card['backupFor'].get('processorId')
    wants = {}
    for bid, entry in boxes.items():
        raw, res = entry['raw'], entry['res']
        if res.get('backupOf'):
            if not raw.get('unbound') and res['backupOf'] in boxes \
                    and res['backupOf'] != bid:
                wants[bid] = (res['backupOf'], False)
            continue
        target = raw.get('boundTo')
        main_proc = backs.get(entry['cardId'])
        if isinstance(target, str) and target in boxes \
                and boxes[target]['cardId'] != entry['cardId'] \
                and main_proc and boxes[target]['procId'] == main_proc:
            wants[bid] = (target, True)
    claimed = {}
    for bid, (target, manual) in wants.items():
        if target in wants or target in claimed:
            continue
        claimed[target] = bid
        res, tres = boxes[bid]['res'], boxes[target]['res']
        res['boundTo'] = target
        res['boundManual'] = manual
        res['boundTitle'] = fiber_box_title(boxes[target])
        res['fiberLinks'] = {}
        res['fiberLinkKeys'] = []
        tres['boundBackup'] = bid
        tres['boundBackupTitle'] = fiber_box_title(boxes[bid])
        tres['fiberLinkKeys'] = fiber_link_keys(tres.get('trunksIn'), True)
    # The boxes a backup-processor box may be bound to by hand: the backed
    # processor's boxes (off its own card) that are neither bound nor
    # already someone else's.
    for bid, entry in boxes.items():
        res = entry['res']
        main_proc = backs.get(entry['cardId'])
        if res.get('backupOf') or not main_proc:
            res['fiberBindTargets'] = None
            continue
        res['fiberBindTargets'] = [
            {'id': tid, 'title': fiber_box_title(t)}
            for tid, t in boxes.items()
            if t['procId'] == main_proc and t['cardId'] != entry['cardId']
            and not t['res'].get('boundTo')
            and t['res'].get('boundBackup') in (None, bid)]


def fiber_cables_in_use(project):
    """The ids of every cable some box's link names right now."""
    used = set()
    for proc in (project or {}).get('processors') or []:
        for slot in (proc or {}).get('slots') or []:
            card = (slot or {}).get('card')
            for cvt in (card or {}).get('cvts') or []:
                for link in resolved_fiber_links(cvt).values():
                    used.add(link['cable'])
    return used


def fiber_strands_taken(boxes, skip=None):
    """{(cableId, strand): (boxId, key)} over the show's links, one link
    (`skip` = (boxId, key)) left out. A bound record's own leftovers are
    not links and take nothing."""
    taken = {}
    for bid, entry in sorted(boxes.items(), key=lambda kv: kv[1]['order']):
        if entry['res'].get('boundTo'):
            continue
        for key, link in resolved_fiber_links(entry['raw']).items():
            if skip and (bid, key) == tuple(skip):
                continue
            for s in link['strands']:
                taken.setdefault((link['cable'], s), (bid, key))
    return taken


def fiber_next_free(cable, taken, need):
    """The lowest `need` strands of `cable` no link holds, else None."""
    total = fiber_cable_strand_count(cable)
    out = [s for s in range(1, total + 1)
           if (cable.get('id'), s) not in taken][:need]
    return out if len(out) == need else None


def check_fiber_link(boxes, cables, box_id, key, cable_id, strands,
                     taken=None, need=None):
    """Why this link cannot be stored, or None.

    The rules, each refused with its reason: the key must be one of the
    box's links; the cable must exist and, if it is an opticalCON, belong
    to this box; the strands must be as many as the link needs (2, 1 with
    BiDi), each within the cable, none twice, none held by another link.
    `strands` None checks everything but the strands (the route then picks
    the next free ones).
    """
    entry = boxes.get(box_id)
    if entry is None:
        return 'There is no such breakout box in this project.'
    res, raw = entry['res'], entry['raw']
    title = fiber_box_title(entry)
    if res.get('boundTo'):
        return (f'{title} is bound to {res.get("boundTitle") or "its primary"}'
                f' - its fiber is set there.')
    if key not in (res.get('fiberLinkKeys') or []):
        return (f'{title} has no link {fiber_link_title(key)} - its links '
                f'are {", ".join(fiber_link_title(k) for k in res.get("fiberLinkKeys") or [])}.')
    cable = cables.get(cable_id)
    if cable is None:
        return 'That fiber cable is not in this project.'
    name = cable.get('name') or 'That cable'
    if cable.get('kind') in FIBER_KIND_FIBERS \
            and cable.get('ownerBoxId') != box_id:
        owner = boxes.get(cable.get('ownerBoxId'))
        return (f'{name} is {fiber_box_title(owner) if owner else "another box"}'
                f'’s opticalCON - an opticalCON feeds its own box only.')
    if strands is None:
        return None
    if need is None:
        need = fiber_link_need(raw)
    if not isinstance(strands, list) or any(
            isinstance(s, bool) or not isinstance(s, int) for s in strands):
        return 'strands must be a list of strand numbers.'
    if len(strands) != need:
        why = 'a BiDi link takes 1' if need == 1 else 'a link takes 2'
        return (f'{title} {fiber_link_title(key)} needs {need} '
                f'strand{"" if need == 1 else "s"} - {why}.')
    if len(set(strands)) != len(strands):
        return 'A strand is named twice.'
    total = fiber_cable_strand_count(cable)
    for s in strands:
        if s < 1 or s > total:
            return (f'{name} has strands 1-{total} - there is no strand '
                    f'{s}.')
    if taken is None:
        taken = fiber_strands_taken(boxes, (box_id, key))
    for s in strands:
        held = taken.get((cable_id, s))
        if held:
            other = boxes.get(held[0])
            return (f'{name} strand {fiber_strand_name(s, cable)} is already '
                    f'used by {fiber_box_title(other)} '
                    f'{fiber_link_title(held[1])} - a strand carries one '
                    f'link.')
    return None


def settle_fiber(project, used_before=None):
    """Hold the fiber store to its rules against the tree as it now is.

    Idempotent, and a project with no fiber anywhere is left untouched:
    - binding records a relation no longer backs go (`boundTo` whose
      backup relation or primary is gone, `unbound` on a box that backs
      up nothing);
    - a link that no longer holds (a bound record's own, a key the box no
      longer has, a cable that is gone, an opticalCON on another box, a
      strand out of range or held twice, a count its BiDi no longer takes)
      goes - the first holder in tree order keeps a contested strand;
    - an opticalCON whose owner box is gone goes;
    - a cable that a link named before this request (`used_before`) and
      none names now goes - the last link let go of it.

    Returns True where anything changed.
    """
    if not isinstance(project, dict):
        return False
    processors = project.get('processors') or []
    has_cables = bool(show_fiber_cables(project))
    stored = any(
        cvt.get('fiberLinks') is not None or 'boundTo' in cvt
        or 'unbound' in cvt
        for proc in processors for slot in (proc or {}).get('slots') or []
        for cvt in ((slot or {}).get('card') or {}).get('cvts') or [])
    if not has_cables and not stored:
        # An emptied list leaves no key behind.
        if 'fiberCables' in project:
            project.pop('fiberCables', None)
            return True
        return False
    boxes = fiber_box_index(processors)
    changed = False
    for entry in boxes.values():
        raw, res = entry['raw'], entry['res']
        if 'boundTo' in raw and (not res.get('boundManual')
                                 or res.get('boundTo') != raw['boundTo']):
            raw.pop('boundTo', None)
            changed = True
        if 'unbound' in raw and (not raw.get('unbound')
                                 or not res.get('backupOf')):
            raw.pop('unbound', None)
            changed = True
    cables = {c.get('id'): c for c in show_fiber_cables(project)
              if isinstance(c, dict)}
    taken = set()
    for bid, entry in sorted(boxes.items(), key=lambda kv: kv[1]['order']):
        raw, res = entry['raw'], entry['res']
        if 'fiberLinks' not in raw:
            continue
        keys = [] if res.get('boundTo') else (res.get('fiberLinkKeys') or [])
        need = fiber_link_need(raw)
        kept = {}
        links = raw.get('fiberLinks') if isinstance(raw.get('fiberLinks'),
                                                    dict) else {}
        for key in keys:
            link = _fiber_link(links.get(key))
            if not link:
                continue
            cable = cables.get(link['cable'])
            if cable is None:
                continue
            if cable.get('kind') in FIBER_KIND_FIBERS \
                    and cable.get('ownerBoxId') != bid:
                continue
            total = fiber_cable_strand_count(cable)
            strands = link['strands']
            if len(strands) != need or len(set(strands)) != len(strands) \
                    or any(s < 1 or s > total for s in strands) \
                    or any((link['cable'], s) in taken for s in strands):
                continue
            taken.update((link['cable'], s) for s in strands)
            kept[key] = link
        if kept != links:
            changed = True
        if kept:
            raw['fiberLinks'] = kept
        else:
            raw.pop('fiberLinks', None)
    used = fiber_cables_in_use(project)
    out = []
    for cable in show_fiber_cables(project):
        if not isinstance(cable, dict):
            changed = True
            continue
        if cable.get('kind') in FIBER_KIND_FIBERS \
                and cable.get('ownerBoxId') not in boxes:
            changed = True
            continue
        if used_before is not None and cable.get('id') in used_before \
                and cable.get('id') not in used:
            changed = True
            continue
        out.append(cable)
    if out:
        project['fiberCables'] = out
    elif 'fiberCables' in project:
        project.pop('fiberCables', None)
        changed = True
    return changed


def check_fiber_cable(rec, cable=None, used_strands=0):
    """Why this body cannot make (cable None) or edit `cable`, or None.

    `used_strands` is the highest strand a link holds on the cable, which
    a smaller strand count may not cut under.
    """
    if not isinstance(rec, dict):
        return 'The body must be a JSON object.'
    kind = rec.get('kind') if cable is None else cable.get('kind')
    if cable is None and kind not in FIBER_KINDS:
        return ('kind must be one of tac, mtp, opticalcon-duo or '
                'opticalcon-quad.')
    if cable is not None and 'kind' in rec and rec['kind'] != kind:
        return 'A cable’s kind cannot change - make a new cable instead.'
    if 'strands' in rec or (cable is None and kind in FIBER_STRANDED_KINDS):
        value = rec.get('strands')
        if kind in FIBER_KIND_FIBERS:
            if value not in (None, FIBER_KIND_FIBERS[kind]):
                return (f'An opticalCON {"DUO" if kind.endswith("duo") else "QUAD"}'
                        f' has {FIBER_KIND_FIBERS[kind]} fibers.')
        else:
            if isinstance(value, bool) or not isinstance(value, int) \
                    or value < 1:
                return 'The strand count must be a whole number, 1 or more.'
            if value < used_strands:
                return (f'Strand {used_strands} is in use - the count cannot '
                        f'go below it. Move that link first.')
    if 'ft' in rec and rec['ft'] not in (None, ''):
        if isinstance(rec['ft'], bool):
            return 'ft must be a number of feet.'
        try:
            ft = float(rec['ft'])
        except (TypeError, ValueError):
            return 'ft must be a number of feet.'
        if not math.isfinite(ft) or ft < 0:
            return 'ft must be a number of feet, 0 or more.'
    if 'connector' in rec and rec['connector'] not in (None, ''):
        if kind != 'tac':
            return 'Only a TAC names a connector.'
        if not isinstance(rec['connector'], str):
            return 'connector must be text.'
    if 'name' in rec and rec['name'] is not None \
            and not isinstance(rec['name'], str):
        return 'name must be text.'
    if 'labels' in rec and rec['labels'] not in FIBER_LABELS:
        return 'labels must be colors or numbers.'
    if 'subunits' in rec and not isinstance(rec['subunits'], bool):
        return 'subunits must be true or false.'
    if 'strandName' in rec:
        spec = rec['strandName']
        if not isinstance(spec, dict):
            return 'strandName must be {strand, name}.'
        n = spec.get('strand')
        total = rec.get('strands') if isinstance(rec.get('strands'), int) \
            else fiber_cable_strand_count(cable or rec)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1 \
                or n > total:
            return f'There is no strand {n} on this cable.'
        if spec.get('name') is not None \
                and not isinstance(spec.get('name'), str):
            return 'A strand’s name must be text.'
    return None


def store_fiber_cable(project, rec, next_seq, cable=None):
    """Write a checked body onto `cable` (a new one when None)."""
    fresh = cable is None
    if fresh:
        kind = rec.get('kind')
        cable = {'id': f'fib{next_seq()}', 'kind': kind,
                 'labels': 'colors', 'subunits': False, 'strandNames': {}}
        if kind in FIBER_KIND_FIBERS:
            cable['strands'] = FIBER_KIND_FIBERS[kind]
            cable['ownerBoxId'] = rec.get('ownerBoxId')
    kind = cable['kind']
    if 'name' in rec or fresh:
        name = (rec.get('name') or '').strip()
        cable['name'] = name or cable.get('name') \
            or fiber_default_name(project, kind)
    if kind in FIBER_STRANDED_KINDS and 'strands' in rec:
        cable['strands'] = rec['strands']
        names = cable.get('strandNames') or {}
        cable['strandNames'] = {k: v for k, v in names.items()
                                if k.isdigit() and int(k) <= rec['strands']}
    if 'ft' in rec or fresh:
        ft = _cable_ft(rec.get('ft'))
        if ft is None:
            cable.pop('ft', None)
        else:
            cable['ft'] = ft
    if kind == 'tac' and ('connector' in rec or fresh):
        conn = (rec.get('connector') or '').strip()
        if conn:
            cable['connector'] = conn
        else:
            cable.pop('connector', None)
    if 'labels' in rec:
        cable['labels'] = rec['labels']
    if 'subunits' in rec:
        cable['subunits'] = rec['subunits']
    if 'strandName' in rec:
        spec = rec['strandName']
        text = (spec.get('name') or '').strip()
        names = cable.setdefault('strandNames', {})
        if text:
            names[str(spec['strand'])] = text
        else:
            names.pop(str(spec['strand']), None)
    if fresh:
        project.setdefault('fiberCables', []).append(cable)
    return cable


def refit_fiber_bidi(boxes, cables, box_id, on):
    """Re-fit one box's links to its BiDi switch, in place.

    Switched ON, each link keeps its first strand. Switched OFF, each tries
    the strand after its own; a link that cannot have it (past the cable's
    count, or held by any link - this box's own included) is cleared.
    Returns the keys cleared.
    """
    raw = boxes[box_id]['raw']
    links = resolved_fiber_links(raw)
    cleared = []
    if on:
        for link in links.values():
            link['strands'] = link['strands'][:1]
    else:
        taken = fiber_strands_taken(boxes)
        for key in list(links):
            link = links[key]
            cable = cables.get(link['cable'])
            first = link['strands'][0] if link['strands'] else None
            nxt = first + 1 if first else None
            if cable is None or nxt is None \
                    or nxt > fiber_cable_strand_count(cable) \
                    or (link['cable'], nxt) in taken:
                links.pop(key)
                cleared.append(key)
            else:
                link['strands'] = [first, nxt]
    if links:
        raw['fiberLinks'] = links
    else:
        raw.pop('fiberLinks', None)
    return cleared


def resolved_fiber_cables(project):
    """The show's cables as every reader takes them, in their stored order."""
    out = []
    for cable in show_fiber_cables(project):
        if not isinstance(cable, dict):
            continue
        rec = {
            'id': cable.get('id'),
            'name': cable.get('name') or '',
            'kind': cable.get('kind'),
            'strands': fiber_cable_strand_count(cable),
            'ft': cable.get('ft'),
            'labels': cable.get('labels') if cable.get('labels')
            in FIBER_LABELS else 'colors',
            'subunits': bool(cable.get('subunits')),
            'strandNames': dict(cable.get('strandNames') or {}),
        }
        if cable.get('kind') == 'tac' and cable.get('connector'):
            rec['connector'] = cable['connector']
        if cable.get('kind') in FIBER_KIND_FIBERS:
            rec['ownerBoxId'] = cable.get('ownerBoxId')
        out.append(rec)
    return out



def stock_default_cvts(project):
    """Put the shop-default boxes back on a boxless requires-distribution
    device, in a project saved before new_processor stocked them at birth.

    A boxless SX40 is never a state somebody chose: the device has no
    fixture ports of its own, so every port it will ever drive comes out of
    a box (the 2026-08-25 ruling: "The sx40 by default has to use 10 port
    breakout boxes"). An empty cvts list on its fixed card is therefore a
    pre-stocking save, and it gets exactly what a fresh add gets - one
    default box per trunk. The same narrowness as the birth rule holds: a
    card with even ONE box is somebody's arrangement and stays theirs, a
    device with no documented default gains nothing, and a chassis's cards
    are picked by hand so its emptiness means empty slots, not a legacy
    file. Runs where a whole project ENTERS server state, never on a read -
    a GET must not mutate, and the file must heal whether or not the panel
    is ever opened. Idempotent: the boxes it stocks are the boxes that stop
    it stocking any next time through.
    """
    for proc in (project or {}).get('processors') or []:
        device = get_device(proc.get('deviceId'))
        if not device or device.get('form') == 'chassis':
            continue
        default_box = device.get('defaultCvt')
        trunks = device.get('trunks') or 0
        if not (device.get('requiresDistribution') and default_box and trunks):
            continue
        # A non-chassis processor holds one slot with its fixed card in it.
        card = next((s.get('card') for s in proc.get('slots') or []
                     if s.get('card')), None)
        if card is None or card.get('cvts'):
            continue
        # Ids come off the project's own counter, the way every hand-added
        # box's do - but a legacy file's counter can trail the ids already
        # in it (or be missing outright), so each candidate run is checked
        # against every id in the tree and a taken run is skipped, never
        # reused: a reused id would land edits on the wrong box.
        taken = set()
        for p in project.get('processors') or []:
            taken.add(p.get('id'))
            for slot in p.get('slots') or []:
                if slot.get('card'):
                    taken.add(slot['card'].get('id'))
                    for cvt in slot['card'].get('cvts') or []:
                        taken.add(cvt.get('id'))
        while True:
            seq = project.get('next_processor_seq') or 1
            project['next_processor_seq'] = seq + 1
            minted = [f'{seq}f{i}' for i in range(trunks)]
            if all(f'cvt{m}' not in taken for m in minted):
                break
        card['cvts'] = [box for box in
                        (new_cvt(default_box, m) for m in minted) if box]


def adopt_fixed_card_names(project):
    """Move a name typed on a one-box unit's fixed card up to the unit.

    Until 1.3.0 the tray drew two name fields for a one-box unit - the
    processor's strip and its fixed card's strip - and a name typed on the
    card silently outranked the unit's own (a port's label took the nearest
    named level upstream). The ruling (2026-09-24) leaves such a unit ONE
    name slot, the processor's, and the card's name is no longer read. So a
    file saved with the name on the card would come back unlabeled: this
    pass adopts the card's name as the unit's where the unit has none, and
    clears the card's either way, so the file carries nothing invisible. A
    chassis's slot cards are parts with names of their own and are left
    alone. Runs where a whole project ENTERS server state (the same funnel
    as stock_default_cvts), never on a read. Idempotent: a cleared card is
    what stops it acting next time through. Returns one record per unit it
    touched, for the caller to log.
    """
    moved = []
    for proc in (project or {}).get('processors') or []:
        if unit_is_chassis(proc) or not get_device(proc.get('deviceId')):
            continue
        for slot in proc.get('slots') or []:
            card = (slot or {}).get('card')
            if not card:
                continue
            typed = (card.get('name') or '').strip()
            if not typed:
                continue
            adopted = not (proc.get('name') or '').strip()
            if adopted:
                proc['name'] = typed
            card['name'] = ''
            moved.append({'processorId': proc.get('id'),
                          'deviceId': proc.get('deviceId'),
                          'cardId': card.get('id'), 'cardName': typed,
                          'adopted': adopted,
                          'unitName': proc.get('name') or ''})
    return moved


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
        # A one-box unit's fixed card IS the processor, and the unit has one
        # name slot - the processor's (ruling, 2026-09-24). Whatever a legacy
        # file or a stray PUT left on the card is not a name the tray offers
        # or a label reads; the processor's name is the unit's.
        if source == 'card' and card_is_unit_face(node, proc):
            continue
        if node and (node.get('name') or '').strip():
            return node, source
    return None, None


# ── Resolution ────────────────────────────────────────────────────────────

def _fiber_ft(value):
    """A stored fiber length as a positive number of feet, else None."""
    try:
        ft = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(ft) or ft <= 0:
        return None
    return int(ft) if ft == int(ft) else ft


def resolve_card(card, proc):
    """Expand one card into its ports, with the label each port carries."""
    device = get_device(card.get('deviceId')) or {}
    shape = card_redundancy_shape(card, proc, device)
    # REDUNDANCY NEVER RENUMBERS A SOCKET. The ceiling stays the datasheet
    # count under every shape, because the backing ports still EXIST: they
    # are the returns of the mains, and a tech patching a backup loom into
    # socket 21 needs socket 21 on the drawing (the S8 said this first -
    # port 2 is main 1's return, and it stays port 2). The trunk-level fixed
    # pairing (SX40) used to halve the ceiling here instead, which is what
    # the user reported as "limits to 20 primaries but it should be 10 per
    # box" (2026-08-25): halving renumbered box C from sockets 21-30 down to
    # 11-20 and erased 21-40 from the drawing. Now every shape says the same
    # thing - usable capacity halves (`usable` below), the numbering never
    # does, and the pairing lands port-to-port in _apply_backup_mapping. A
    # 1to1 card halves nothing - the backup UNIT is what redundancy consumes
    # - and manual takes only the ports somebody named.
    cap = port_capacity(card.get('deviceId'), card.get('mode'))
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
    # documents interleaved copies - OPT 3/4 back up OPT 1/2 - expressed in
    # the card's own MODE: copy-backup halves the block count, so
    # `block = index mod block count` really does deliver ports 1-8 again on
    # OPT 3. Brompton documents ADJACENT pairs, verbatim: "A back up to B,
    # C back up to D automatically; that is the only way it works" - whole
    # boxes, and every box keeps its own sockets: B is 11-20 carrying the
    # returns of A's 1-10, never a second delivery of 1-10. So Brompton's
    # pairing takes nothing from the block arithmetic; it is stated below
    # (paired_backs_up) and wired port-to-port in _apply_backup_mapping.
    paired = bool(shape and shape['forced'] and shape['level'] == 'trunk')

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
    # A BOX THAT HOLDS ITS TRUNK KEEPS IT. Boxes take the lowest free run
    # of trunks in list order, so removing box B used to slide C down onto
    # B's trunk - C's sockets renumbered 21-30 to 11-20, its letter changed,
    # and a screen pinned on C's sockets landed on the box that had been D.
    # On a box-fed device the box IS the trunk's ports (there are no others),
    # so a box delete there stamps the survivors' trunks onto their records
    # (hold_box_trunks) and this pre-pass reserves them before anything
    # else is placed: the removed trunk stays empty, its sockets are gone,
    # and a box added afterwards takes it as the lowest free run. A record
    # without a stamp - every box on an unflagged card, and every box of a
    # fresh unit - is placed exactly as before.
    held = {}
    for cvt in card.get('cvts') or []:
        want = held_trunk(cvt)
        takes = trunks_in(get_device(cvt.get('deviceId')) or {})
        if want is None or want + takes > trunks:
            continue
        run = range(want, want + takes)
        if any(t in taken for t in run):
            continue
        taken.update(run)
        held[cvt.get('id')] = want
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
        index = held.get(cvt.get('id'))
        primary = placed_by_id.get(cvt.get('backupOf'))
        if index is None and primary is not None and block_count:
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
            # The box's fiber trunk, as typed on it (update_cvt): what the
            # fiber is and how long its home run is. '' / None when unset -
            # the pull list lists no fiber for a box without a length, and
            # the binder's band says so.
            'fiberType': (cvt.get('fiberType') or '').strip(),
            'fiberFt': _fiber_ft(cvt.get('fiberFt')),
            # Where the box sits (update_cvt), '' when nobody said: the pull
            # list files the box's rows under this name.
            'location': (cvt.get('location') or '').strip(),
            # The beach the box sits on (update_cvt), None when nobody
            # picked one: the pull list files the box's rows under that
            # beach's name; `location` above is only a record nobody
            # migrated yet.
            'beachId': cvt.get('beachId') or None,
            # The box's fiber links (the fiber-cable section below): which
            # show cable and which strands each of its trunk links takes.
            # `bidi` halves a link to one strand, and is only offered where
            # the catalog's vendor makes BiDi optics (bidiAllowed). The
            # binding fields - boundTo on a backup record that IS its
            # primary's metal, boundBackup on that primary, and the backup
            # link keys that come with it - are filled in by resolve_all
            # (_apply_fiber_binding), because a backup processor's box can
            # be bound to a box on another processor.
            'fiberLinks': resolved_fiber_links(cvt),
            'fiberLinkKeys': fiber_link_keys(takes, False),
            'bidi': bool(cvt.get('bidi')),
            'bidiAllowed': fiber_bidi_allowed(cvt_device),
            'unbound': bool(cvt.get('unbound')),
            'boundTo': None,
            'boundManual': False,
            'boundBackup': None,
            'ports': [],
        }
        # The box's port cables ride the resolved box, with the connector
        # its sockets FOLLOW (the catalog's word for the box, else the
        # card's, else nothing - see data_port_connector). Snakes are the
        # show's now (project['snakes']) and ride no device.
        resolved['portCables'] = resolved_port_cables(cvt)
        resolved['portConnector'] = data_port_connector(
            cvt_device, device, get_device(proc.get('deviceId')))
        cvts.append(resolved)
        placed_by_id[resolved['id']] = resolved
        if size:
            claimed = max(claimed, first + size - 1)

    # The fixed pairing pairs WHOLE BOXES: the box on the second trunk of an
    # adjacent pair is the first one's backup - B carries A's returns, D
    # carries C's - by construction, not by anyone's pick. Said on the
    # resolved box (the same `backupOf` the NovaStar pair stores) so the
    # panel's "backs up A" line reads off one field either way; derived here
    # every resolve and stored nowhere, because a fact of the device is not
    # project state.
    if paired:
        on_trunk = {c['trunkIndex']: c for c in cvts
                    if c['trunksIn'] == 1 and not c['beyondTrunks']}
        for index, box in on_trunk.items():
            primary = on_trunk.get(index - 1)
            if index % 2 == 1 and primary and not box['backupOf']:
                box['backupOf'] = primary['id']

    # WHAT A MESSAGE CALLS EACH BOX, stated once for every reader. Since the
    # 2026-08-27 ruling every box numbers its own sockets from 1, so a bare
    # number only means something beside its box's name - and four boxes all
    # reading "Tessera XD" are four sections nobody can tell apart. An
    # unnamed box on a trunked card therefore wears its trunk letter ("A",
    # or "A-B" for one eating two trunks) - the letters the pairing rule
    # itself is written in ("A backs up to B") - while a hand-named box is
    # already told apart by its name. No letter where there is nothing to
    # letter: a card without two trunks, or a box hanging past them.
    for box in cvts:
        letter = ''
        if (trunks >= 2 and not box['beyondTrunks']
                and isinstance(box['trunkIndex'], int)
                and box['trunkIndex'] >= 0):
            first = chr(ord('A') + box['trunkIndex'])
            takes = box['trunksIn'] or 1
            letter = (f'{first}-{chr(ord("A") + box["trunkIndex"] + takes - 1)}'
                      if takes > 1 else first)
        box['trunkLetter'] = letter
        box['displayTitle'] = (box['name'] or '').strip() \
            or (box['deviceName'] + (f' {letter}' if letter else ''))
        # THE TRUNK AS THE CARD'S FACE PRINTS IT, for paper that names where
        # a box hangs: "OPT 1" ("OPT 1-2" for a box eating two) on a card
        # whose catalog entry documents that word (trunkWord - the NovaStar
        # H cards' notes say OPT), else the app's own letter, "trunk A".
        # Nothing where there is nothing to name.
        box['trunkTitle'] = ''
        if letter:
            word = (device.get('trunkWord') or '').strip()
            if word:
                first = box['trunkIndex'] + 1
                last = first + (box['trunksIn'] or 1) - 1
                box['trunkTitle'] = (f'{word} {first}-{last}' if last > first
                                     else f'{word} {first}')
            else:
                box['trunkTitle'] = f'trunk {letter}'

    # A box can only claim past the ceiling by hanging off a trunk that is not
    # there - five CVT10s on a four-trunk card. That stays visible rather than
    # being clamped away, because it is a real mistake to make on paper.
    #
    # ON A BOX-FED DEVICE A PORT OUTSIDE A BOX DOES NOT EXIST. The SX40 has
    # no 1G fixture ports of its own - every port it drives comes out of an
    # XD on one of its trunks - and the HELIOS Standard is the same shape
    # behind its RS12s. So on such a card (is_box_fed: the catalog's
    # requiresDistribution, and only that) the enumeration is the boxes'
    # spans and nothing else: `defined` is what the boxes claim, and a
    # number no box covers is skipped rather than listed as a socket of the
    # card's own face. It used to fall through to the ceiling - delete box
    # B off an SX40 and sockets 11-20 came back as loose ports of the unit,
    # took pins, printed on labels and counted in the summaries - which is
    # the ruling (2026-09-24): "I can remove boxes from SX40's but then it
    # adds those ports back to the SX40 outside of an XD box. SX40's can't
    # use ports outside of an XD box. So that makes no sense and we need to
    # remove that functionality" and "same goes for Helios". A card that is
    # not flagged keeps its own ports exactly as before.
    box_fed = is_box_fed(device)
    top = claimed if box_fed else max(ceiling or 0, claimed)

    ports = []
    for number in range(1, top + 1):
        # More than one box can reach the same port now that a trunk can be a
        # copy of an earlier one. They all list it, because a port really does
        # come out of both boxes - but the FIRST one names it, since the backup
        # is not what anyone patches to or reads a number off.
        covering = [c for c in cvts
                    if c['portCount']
                    and c['firstPort'] <= number < c['firstPort'] + c['portCount']]
        cvt = covering[0] if covering else None
        if box_fed and cvt is None:
            continue
        local = number - cvt['firstPort'] + 1 if cvt else number
        owner, owner_source = _label_owner(cvt, card, proc)
        source = owner_source
        # A BOX'S SOCKETS ARE NUMBERED BY ITS OWN SILKSCREEN, whoever names
        # them. The user's ruling (2026-08-27): "If i have redundancy enabled
        # for an SX40 then B is 1-10 and D is 1-10" and "all cvt's are 1-10 or
        # 1-16" - the face of every breakout box reads 1..N whichever trunk it
        # hangs on, so a label numbered past N points at a socket no box has.
        # It used to number off the CARD when the card was doing the naming, to
        # keep two unnamed boxes from printing the same labels twice - but a
        # label a tech cannot find beside any socket is the worse trade, and
        # telling the boxes apart is the box's job (its name, or the trunk
        # letter the dock hangs on it). Ports that reach no box keep the
        # card's own numbering: the card's face IS their silkscreen.
        numbered = local if cvt else number
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
            # Whether the return end fell to the DERIVED rung - no typed
            # return name, no return template. That is the one rung a
            # redundancy mapping may replace (resolve_all): the mapped
            # physical port's own label beats P-to-R guesswork, but never
            # beats a name somebody typed or a template somebody set.
            # returnLabelSource cannot answer this - the derived rung
            # reports the PRIMARY's source, which is 'manual' whenever the
            # primary was hand-named.
            'returnDerived': not manual_return and not return_template,
            'cvtId': cvt['id'] if cvt else None,
            'beyondCeiling': bool(ceiling is not None and number > ceiling),
        }
        ports.append(port)
        for box in covering:
            box['ports'].append(port)

    # What the card DEFINES is a count - the panel prints it as "n / N
    # ports". Everywhere but a box-fed card the enumeration is 1..top, so
    # the count is top; on a box-fed card the enumeration has gaps (A, C
    # and D with B removed is thirty sockets numbered up to 40), so the
    # count is the sockets actually listed.
    defined = len(ports) if box_fed else top

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

    out = {
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
        # THE TRUNK AS THE CARD'S OWN FACE PRINTS IT, or blank where no sheet
        # prints a word - the same field, and the same rule, box['trunkTitle']
        # names a box's trunk by ("OPT 1-2" on a NovaStar H card, "trunk A"
        # where the word is not documented, nothing where there is nothing to
        # name). The panel's port-shape chip needs it to say "OPT Split"
        # without ever saying OPT about a trunk nobody silkscreens OPT.
        'trunkWord': (device.get('trunkWord') or '').strip(),
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
        # The data-redundancy shape in force, with what it leaves usable.
        # Derived every resolve like the pairing above it; the STORED pieces
        # (redundancyMode, backupCardId, backupPorts) echo back beside it so
        # the panel shows what was chosen, not only what it produced. The
        # port-to-port consequences - backedBy, backsUp, mapped return
        # labels - land in resolve_all, because a 1to1 backup can live on
        # another processor and one card cannot see that far.
        # Sequential halves what is USABLE at either level - odd ports on a
        # port-level card, boxes A and C on a trunk-level one (the SX40's
        # 20: 10 per primary box) - and never the ceiling, which is the
        # socket count. Halves costs the same half, taken off the back of
        # the card instead of the evens. 1to1 and manual leave usable at
        # the ceiling: what they consume is a backup unit, or exactly the
        # ports picked.
        'redundancyShape': dict(shape, usable=(
            ceiling - ceiling // 2
            if (ceiling and shape['mode'] in ('sequential', 'halves'))
            else ceiling)) if shape else None,
        'redundancyMode': card.get('redundancyMode') or '',
        'backupCardId': card.get('backupCardId') or None,
        'backupPorts': {str(k): v for k, v in
                        (card.get('backupPorts') or {}).items() if v},
        'delivered': delivered,
        'shortfall': shortfall,
        'defined': defined,
        # Whether every socket of this card is a box's (is_box_fed): the
        # assignment reads it to bound fills and hand placements to the
        # sockets the boxes deliver, and the box delete reads it to drop
        # the pins that went with a box.
        'boxFed': box_fed,
        # Over on trunks counts as over even where the ports happen to add up:
        # a box with no fiber to plug into is a box that is not connected.
        'over': bool(ceiling is not None and defined > ceiling)
                or bool(trunks and used_trunks > trunks),
        'note': device.get('note', ''),
        'cvts': cvts,
        'ports': ports,
    }
    # The card's own port cables, for the ports on its face; the connector
    # those sockets follow is the card's documented kind, else the
    # processor's, else nothing. Snakes belong to the show, not the card.
    out['portCables'] = resolved_port_cables(card)
    out['portConnector'] = data_port_connector(
        None, device, get_device(proc.get('deviceId')))
    return out


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
        # Whether the panel offers the redundancy toggle at all. Everything
        # except an explicit "supported: false" (the T1: one output, nothing
        # to loop) does - because with the data modes, redundancy stopped
        # being a claim about the device and became a plan for the loom: any
        # unit can be mirrored 1 to 1 by a second unit, whatever its vendor
        # documents, which is the user's own NovaStar second-sending-card
        # case. What stays vendor-documented stays vendor-gated: fixed
        # pairing statements, halved ceilings, default box pairs.
        'redundancySupported': (device.get('redundancy') or {})
                               .get('supported') is not False,
        # Stated beside the checkbox that turns redundancy on: WHICH output
        # backs which, where the vendor fixes it. A fact the panel displays,
        # never a control - Brompton pairs adjacent outputs automatically and
        # offers no other arrangement.
        'redundancyPairing': redundancy_pairing(device, proc.get('redundancy')),
        # The processor that mirrors this one whole, card for card - filled
        # in by resolve_all once every card's 1:1 link has resolved, because
        # the partner is another processor and one cannot see that far from
        # here. DERIVED, never stored: a whole-processor pairing IS its
        # cards' 1:1 picks, and a second copy of that fact would be one
        # more thing to drift.
        'backupProcessorId': None,
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


def _apply_backup_mapping(processors, resolved):
    """Wire every card's redundancy shape into port-to-port facts, tree-wide.

    This runs AFTER every card has resolved, and it is the only place the
    mapping happens, because a 1to1 backup can be a card on another
    processor entirely - the user's "second sending card" - and resolve_card
    cannot see that far. Three consequences land on the resolved ports:

    * a main port gains `backedBy` - the physical port its return comes
      back on;
    * that port gains `backsUp` - it is consumed as a return, which is what
      the assignment resolver and the dock refuse on;
    * where the main's return label was DERIVED (returnDerived - no typed
      name, no template), it is replaced by the mapped port's own primary
      label, because the return end physically IS that socket: a main card
      P1 mirrored by a card R1 reads P1-1 out, R1-1 back, off the backup's
      own name. Typed names and templates still win - the mapping replaces
      only the derived rung of the ladder.

    A port backs at most one main: the first claim in panel order stands and
    a later one is skipped, so a degenerate file (hand-edited, or stale
    after deletes) resolves deterministically instead of flapping. The fixed
    trunk-level pairing (SX40) maps here too, a block at a time: trunk pairs
    carry box pairs, so main n in an even block returns on n + portsPerTrunk
    in the odd block beside it - socket 1 returns on 11, 21 on 31 - and the
    backing box's sockets keep their own numbers on the drawing.
    """
    raw_cards = {}
    res_cards = {}
    order = []
    for proc, rproc in zip(processors or [], resolved):
        for slot in proc.get('slots') or []:
            if slot.get('card'):
                raw_cards[slot['card']['id']] = (slot['card'], proc)
        for rslot in rproc.get('slots') or []:
            rcard = rslot.get('card')
            if rcard:
                res_cards[rcard['id']] = (rcard, rproc)
                order.append(rcard['id'])

    ports_of = {cid: {p['number']: p for p in res_cards[cid][0]['ports']}
                for cid in res_cards}

    def box_title(cid, port):
        """The display name of the box delivering one port, or None off any
        box. Rides the link below so a message can say WHICH box a bare
        local number counts on - two boxes both have a port 3 now."""
        if not port.get('cvtId'):
            return None
        return next((c.get('displayTitle')
                     for c in res_cards[cid][0].get('cvts') or []
                     if c['id'] == port['cvtId']), None)

    def link(main_id, n, target_id, t):
        mcard, mproc = res_cards[main_id]
        tcard, tproc = res_cards[target_id]
        mport = ports_of[main_id].get(n)
        tport = ports_of[target_id].get(t)
        if not mport or not tport or mport is tport:
            return
        # Claimed is claimed: a port that already backs a main cannot back
        # another, and a port consumed as a return is no main.
        if tport.get('backsUp') or mport.get('backsUp') \
                or mport.get('backedBy'):
            return
        # `port` is the card-wide socket the bookkeeping runs on; `localPort`
        # is the number written beside that socket - the box's own 1..N where
        # a box delivers it (the 2026-08-27 silkscreen ruling), the card's
        # where none does. Anything SAYING which socket a return lands on
        # says the local number, because that is the number a hand can find.
        mport['backedBy'] = {
            'processorId': tproc['id'], 'cardId': tcard['id'],
            'cardTitle': tcard['name'] or tcard['deviceName'],
            'boxTitle': box_title(target_id, tport),
            'port': t, 'localPort': tport['localNumber'],
            'label': tport['label'],
        }
        tport['backsUp'] = {
            'processorId': mproc['id'],
            'processorName': mproc['name'] or mproc['deviceName'],
            'cardId': mcard['id'],
            'cardTitle': card_display_name(mcard, mproc),
            'boxTitle': box_title(main_id, mport),
            'port': n, 'localPort': mport['localNumber'],
            'label': mport['label'],
        }
        if mport.get('returnDerived') and tport['label']:
            mport['returnLabel'] = tport['label']
            mport['returnLabelSource'] = 'backup'

    def shape_of(cid):
        rcard, _rproc = res_cards[cid]
        return rcard.get('redundancyShape')

    # 1to1 first: it consumes whole units, and a consumed unit's own choices
    # go quiet - a backup card is its main's return end, not a main itself.
    consumed = set()
    for cid in order:
        shape = shape_of(cid)
        if not shape or shape['forced'] or shape['mode'] != '1to1':
            continue
        if cid in consumed:
            continue
        raw, _proc = raw_cards[cid]
        backup_id = raw.get('backupCardId')
        if not backup_id or backup_id == cid or backup_id not in res_cards:
            continue
        if backup_id in consumed or res_cards[backup_id][0].get('backupFor'):
            continue
        rcard, rproc = res_cards[cid]
        res_cards[backup_id][0]['backupFor'] = {
            'processorId': rproc['id'],
            'cardId': cid,
            'title': card_display_name(rcard, rproc),
        }
        consumed.add(backup_id)
        for n in sorted(ports_of[cid]):
            link(cid, n, backup_id, n)

    for cid in order:
        shape = shape_of(cid)
        if not shape or cid in consumed:
            continue
        if shape['mode'] == 'sequential' and shape['level'] == 'port':
            numbers = sorted(ports_of[cid])
            for n in numbers:
                if n % 2 == 1 and (n + 1) in ports_of[cid]:
                    link(cid, n, cid, n + 1)
        elif shape['mode'] == 'sequential' and shape['level'] == 'trunk':
            # The SX40's box-level pairing, in socket numbers: trunk pairs
            # A/B and C/D each carry a portsPerTrunk-sized block twice over
            # in ROLE, never in numbering - the mains are the even blocks
            # (sockets 1-10, 21-30) and each returns on the same socket of
            # the block beside it (11-20, 31-40). "10 per box", per the
            # 2026-08-25 ruling.
            per_trunk = res_cards[cid][0].get('portsPerTrunk')
            if per_trunk:
                for n in sorted(ports_of[cid]):
                    if ((n - 1) // per_trunk) % 2 == 0 \
                            and (n + per_trunk) in ports_of[cid]:
                        link(cid, n, cid, n + per_trunk)
        elif shape['mode'] == 'halves':
            # The 2026-08-27 arrangement: "1-8 on processor 1 and 9-16 as
            # backups" - the back half of the card carries the front half's
            # returns, port N returned on N + half. The split is taken off
            # the CEILING, never off `defined`: boxes past their trunks can
            # inflate the enumeration, and a mapping computed off a drawing
            # mistake would move with it. Rounding the mains UP on an odd
            # count leaves the middle port a main with no backup, the same
            # way sequential leaves the last odd port unpaired. A card with
            # no settled count maps nothing - guessing where its half falls
            # is the guessed-ceiling mistake wearing a redundancy hat.
            ceiling = res_cards[cid][0].get('ceiling')
            if ceiling:
                half = ceiling - ceiling // 2
                for n in sorted(ports_of[cid]):
                    if n <= ceiling // 2 and (n + half) in ports_of[cid]:
                        link(cid, n, cid, n + half)
        elif shape['mode'] == 'manual' and not shape['forced']:
            raw, _proc = raw_cards[cid]
            entries = raw.get('backupPorts') or {}
            for key in sorted(entries, key=lambda k: int(k)):
                spec = entries[key] or {}
                target_id = spec.get('cardId') or cid
                if target_id not in res_cards:
                    continue
                try:
                    n, t = int(key), int(spec.get('port'))
                except (TypeError, ValueError):
                    continue
                link(cid, n, target_id, t)


def _derive_backup_processors(resolved):
    """Name, on each main, the processor that backs it WHOLE.

    The unit-level reading of the card-level facts, the same rule the
    dock uses to nest a backup unit under its main: a processor whose
    every card is consumed backing the cards of ONE other processor, card
    N for card N in slot order, with no card left over on either side, is
    that processor's backup unit. The reading drops the moment any one
    card is repointed - a half-mirror is a per-card arrangement, and the
    panel's level select follows this value.
    """
    by_id = {p['id']: p for p in resolved}

    def cards_of(p):
        return [s['card'] for s in p.get('slots') or [] if s.get('card')]

    for backup in resolved:
        cards = cards_of(backup)
        if not cards or not all(c.get('backupFor') for c in cards):
            continue
        main_id = cards[0]['backupFor']['processorId']
        if main_id == backup['id'] \
                or any(c['backupFor']['processorId'] != main_id
                       for c in cards):
            continue
        main = by_id.get(main_id)
        if not main:
            continue
        main_cards = cards_of(main)
        if len(main_cards) != len(cards):
            continue
        if any(bc['backupFor']['cardId'] != mc['id']
               for mc, bc in zip(main_cards, cards)):
            continue
        main['backupProcessorId'] = backup['id']


def resolve_all(processors):
    resolved = [resolve_processor(p) for p in (processors or [])]
    _apply_backup_mapping(processors, resolved)
    _derive_backup_processors(resolved)
    _apply_fiber_binding(processors, resolved)
    return resolved
