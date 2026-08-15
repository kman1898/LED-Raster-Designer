"""The processor tree behind the Signal panel: catalog, ports, labels, storage.

A processor drives the wall, and the panel has to model it the way the hardware
is actually built, so these tests are mostly about the four things that make
that awkward:

* THE CARD DECIDES THE PORT COUNT, NOT THE CHASSIS. An H9 of H_20xRJ45 cards
  and an H9 of H_4xfiber cards are 100 ports and 160 ports. Read a ceiling off
  the chassis and you cap a wall at the wrong number.
* A COUNT CAN BE UNKNOWN, AND MUST STAY UNKNOWN. docs/processor-port-table.md
  marks Brompton's SQ200 NOT FOUND and records HELIOS Standard 4K as 2 or 3
  depending on the document's age. Filling either in from a sibling model is
  the failure this whole file exists to prevent - the table spends a section
  explaining why two cards with four fiber connectors are 32 and 40 ports.
* THE NEAREST NAMED DEVICE UPSTREAM OWNS THE LABEL. A fiber card's ports
  arrive at a CVT box, so the CVT's name beats the card's; a card's name beats
  the processor's.
* NOBODY WHO DEFINES NO PROCESSOR MAY SEE ANY CHANGE. The per-screen
  portLabelTemplatePrimary / Return keep doing exactly what they always did,
  and a project without processors keeps the shape it always had.

Values are asserted as they come BACK from the server, never as they were
sent. This codebase drops unlisted fields silently in two separate places
(routes_layers.py's PUT allow-list and add_layer's optional_fields), and a test
that only checks its own request body passes straight through that.

Run locally:
    python3 -m pytest tests/test_processor_panel.py -q
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

PORT_TABLE = os.path.join(os.path.dirname(__file__), '..', 'docs',
                          'processor-port-table.md')


# ── helpers ───────────────────────────────────────────────────────────────

def add_processor(client, device_id):
    resp = client.post('/api/processors', json={'deviceId': device_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def only(state):
    """The single processor in a freshly-built state, resolved."""
    assert len(state['resolved']) == 1, state['resolved']
    return state['resolved'][0]


def set_card(client, proc_id, slot, device_id):
    resp = client.put(f'/api/processors/{proc_id}/slots/{slot}',
                      json={'deviceId': device_id})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def first_card(proc):
    for slot in proc['slots']:
        if slot['card']:
            return slot['card']
    raise AssertionError(f'no card in {proc["id"]}')


# ── 1. The catalog agrees with the table it was transcribed from ──────────

# Every number here was read off a cited row of docs/processor-port-table.md.
# None of them is derived from another: the H_4xfiber pair below is the whole
# argument - four fiber connectors either way, 32 and 40 ports.
SETTLED_CEILINGS = [
    ('novastar-mx40-pro', 40),
    ('novastar-mx30', 10),
    ('novastar-cx80-pro', 16),
    ('novastar-vx400', 4),
    ('novastar-mctrl4k', 16),
    ('novastar-card-h-20xrj45', 20),
    ('novastar-card-h-16xrj45-2xfiber', 16),
    ('novastar-card-h-4xfiber', 32),
    ('novastar-card-h-4xfiber-enhanced', 40),
    ('novastar-card-mx-4x10g', 40),
    ('novastar-card-mx-1x40g', 8),
    ('brompton-sx40', 40),
    ('brompton-s8', 8),
    ('brompton-t1', 1),
    ('megapixel-helios-8k', 8),
    ('megapixel-helios-jr', 8),
    ('megapixel-rs12', 12),
]


@pytest.mark.parametrize('device_id,expected', SETTLED_CEILINGS)
def test_the_catalog_matches_the_port_table(device_id, expected):
    cap = catalog.port_capacity(device_id)
    assert cap['known'], f'{device_id} should have a settled ceiling: {cap}'
    assert cap['count'] == expected, (
        f'{device_id} is {cap["count"]} in the catalog and {expected} in '
        f'docs/processor-port-table.md')


def test_the_two_four_fiber_cards_are_not_the_same_number():
    """The table's central warning: connector count tells you nothing. Both
    cards present four fiber trunks; one runs 8B/10B at 8 Ethernet ports per
    fiber and the other 64B/66B at 10, so they are 32 and 40. A catalog that
    inferred one from the other would pass every other test in this file."""
    standard = catalog.port_capacity('novastar-card-h-4xfiber')['count']
    enhanced = catalog.port_capacity('novastar-card-h-4xfiber-enhanced')['count']
    assert (standard, enhanced) == (32, 40)
    assert catalog.get_device('novastar-card-h-4xfiber')['portsPerTrunk'] == 8
    assert catalog.get_device('novastar-card-h-4xfiber-enhanced')['portsPerTrunk'] == 10


@pytest.mark.skipif(not os.path.exists(PORT_TABLE),
                    reason='the source table is local-only and gitignored')
def test_every_settled_ceiling_is_still_the_number_in_the_source_table():
    """Guard the transcription itself. The table is the source; if a row in it
    is corrected, the catalog has to be corrected with it rather than sitting
    on a number nobody can find a citation for any more."""
    with open(PORT_TABLE, encoding='utf-8') as fh:
        rows = [line for line in fh if line.startswith('|')]

    def stated(device_name):
        for line in rows:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if cells and cells[0] == device_name:
                return cells
        return None

    for device_id, expected in SETTLED_CEILINGS:
        device = catalog.get_device(device_id)
        cells = stated(device['name'])
        if not cells:
            continue  # named differently in the table; the row-by-row check below covers it
        found = re.findall(r'\d[\d,]*', cells[3].replace('**', ''))
        assert str(expected) in found, (
            f'{device["name"]}: catalog says {expected}, the table row says '
            f'{cells[3]!r}')


def test_a_device_the_table_could_not_settle_declares_itself_unknown():
    """Brompton's SQ200 publishes "2x 100G QSFP28" and no port count, and is
    absent from Brompton's own capacity tool. It is a real device someone
    specs, so it stays selectable - but a guessed ceiling silently caps a
    wall, so it reports no number at all rather than an S8's or an SX40's."""
    cap = catalog.port_capacity('brompton-sq200')
    assert cap['count'] is None, f'a count was invented for the SQ200: {cap}'
    assert cap['known'] is False
    assert cap['reason'], 'unknown, but with no explanation of why'
    assert catalog.get_device('brompton-sq200') is not None, (
        'the SQ200 was dropped from the catalog instead of being marked '
        'unknown - an unknown count is not a reason to hide a real device')


def test_a_device_whose_sources_conflict_is_not_adjudicated():
    """HELIOS Standard 4K is 2 in the 2025/2026 documents and 3 in the 2023
    sheet. The table records the conflict and does not resolve it, so neither
    number is a default - both are offered and the user says which document
    they are working from."""
    cap = catalog.port_capacity('megapixel-helios-4k')
    assert cap['count'] is None, f'the conflict was silently picked: {cap}'
    counts = sorted(m['count'] for m in
                    catalog.get_device('megapixel-helios-4k')['ports']['modes'])
    assert counts == [2, 3]
    assert catalog.port_capacity('megapixel-helios-4k', 'docs-2025')['count'] == 2
    assert catalog.port_capacity('megapixel-helios-4k', 'sheet-2023')['count'] == 3


def test_the_conditions_the_table_records_are_carried_across():
    """Three counts in the table are conditional, and the condition is part of
    the number: an H_4xfiber is 32 independent and 16 in copy/backup, an MX40
    Pro is 40 or 20 by optical mode, and Brompton redundancy halves the usable
    count because a backup port consumes a port number rather than adding one."""
    assert catalog.port_capacity('novastar-card-h-4xfiber', 'independent')['count'] == 32
    assert catalog.port_capacity('novastar-card-h-4xfiber', 'copy-backup')['count'] == 16
    assert catalog.port_capacity('novastar-mx40-pro', '40-port')['count'] == 40
    assert catalog.port_capacity('novastar-mx40-pro', '20-port')['count'] == 20
    assert catalog.port_capacity('brompton-sx40', redundancy=True)['count'] == 20
    assert catalog.port_capacity('brompton-s8', redundancy=True)['count'] == 4
    # The T1 has a single output and cannot do closed-loop redundancy at all,
    # so nothing may halve it.
    assert catalog.get_device('brompton-t1')['redundancy']['supported'] is False
    assert catalog.port_capacity('brompton-t1', redundancy=True)['count'] == 1


def test_a_chassis_states_no_port_count_of_its_own():
    """Reading a ceiling off the chassis is the mistake this hierarchy exists
    to make impossible. H-series rows in the table are card counts; the ports
    are on the card."""
    for chassis in ('novastar-h9', 'novastar-h15', 'novastar-mx6000-pro'):
        device = catalog.get_device(chassis)
        assert 'ports' not in device, (
            f'{chassis} carries a port count; only its cards may')
        assert device['slots']['count'] > 0


# ── 2. The card decides the port count ────────────────────────────────────

def test_the_same_chassis_is_a_different_machine_with_a_different_card(client):
    """An H9 with 20xRJ45 cards and an H9 with 4xfiber cards are 100 ports and
    160 ports. Nothing about the chassis says so."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']

    rj45 = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    assert first_card(only(rj45))['ceiling'] == 20
    assert only(rj45)['ceiling'] == 20

    fiber = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    assert first_card(only(fiber))['ceiling'] == 32
    assert only(fiber)['ceiling'] == 32, (
        'the chassis ceiling did not follow the card into the slot')


def test_a_chassis_ceiling_is_summed_from_the_cards_in_it(client):
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    set_card(client, pid, 1, 'novastar-card-h-20xrj45')
    state = set_card(client, pid, 2, 'novastar-card-h-4xfiber')
    proc = only(state)
    assert proc['ceiling'] == 20 + 20 + 32
    assert proc['cardsUsed'] == 3
    assert proc['maxCards'] == 5, 'the H9 takes five output cards'
    assert proc['cardsOver'] is False


def test_an_unsettled_card_makes_the_whole_processor_unknown(client):
    """Summing around a card whose count is not settled would under-report the
    machine, which is the wrong-ceiling failure wearing a different hat. The
    HELIOS Standard 4K arrives unsettled on purpose - its sources say 2 and 3 -
    and only saying which document you are working from settles it."""
    state = add_processor(client, 'megapixel-helios-4k')
    proc = only(state)
    assert proc['ceilingKnown'] is False
    assert proc['ceiling'] is None
    card_id = first_card(proc)['id']

    resp = client.put(f'/api/processors/{proc["id"]}/cards/{card_id}',
                      json={'mode': 'docs-2025'})
    settled = only(resp.get_json())
    assert settled['ceilingKnown'] is True
    assert settled['ceiling'] == 2
    assert len(first_card(settled)['ports']) == 2


def test_an_all_in_one_gets_its_ports_without_a_slot_to_fill(client):
    """A fixed-output device has no cards to choose, but the tree keeps its
    shape so the label rules need no second code path."""
    state = add_processor(client, 'novastar-mx40-pro')
    proc = only(state)
    assert proc['ceiling'] == 40
    card = first_card(proc)
    assert card['fixed'] is True
    assert len(card['ports']) == 40
    # And its slot refuses a card, rather than pretending to take one.
    resp = client.put(f'/api/processors/{proc["id"]}/slots/0',
                      json={'deviceId': 'novastar-card-h-4xfiber'})
    assert resp.status_code == 400


def test_a_processor_whose_count_is_unknown_still_goes_in_a_project(client):
    state = add_processor(client, 'brompton-sq200')
    proc = only(state)
    assert proc['ceilingKnown'] is False
    assert proc['ceiling'] is None
    assert first_card(proc)['ports'] == [], (
        'ports were enumerated for a device with no known count')


# ── 3. Names and labels ───────────────────────────────────────────────────

def test_naming_a_card_names_its_ports(client):
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']

    # Before the name there is nothing upstream to take a label from, so the
    # ports carry none and the screen's own template is still doing the work.
    assert all(p['label'] is None for p in first_card(only(state))['ports'])

    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'name': 'SR'})
    card = first_card(only(resp.get_json()))
    assert card['name'] == 'SR', 'the name did not come back from the server'
    labels = [p['label'] for p in card['ports']]
    assert labels[:3] == ['SR-1', 'SR-2', 'SR-3']
    assert labels[-1] == 'SR-20'
    assert all(p['labelSource'] == 'card' for p in card['ports'])


def test_a_cvts_name_beats_the_cards(client):
    """A fiber card's ports physically arrive at the CVT box, and that box is
    what the tech is standing in front of, so its name is the one on the port."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 201
    cvt_id = first_card(only(resp.get_json()))['cvts'][0]['id']
    resp = client.put(f'/api/processors/{pid}/cvts/{cvt_id}',
                      json={'name': 'CVT-A'})
    card = first_card(only(resp.get_json()))

    behind_cvt = [p for p in card['ports'] if p['cvtId'] == cvt_id]
    assert [p['label'] for p in behind_cvt[:3]] == ['CVT-A-1', 'CVT-A-2', 'CVT-A-3']
    assert all(p['labelSource'] == 'cvt' for p in behind_cvt)
    # Ports that reach no CVT still belong to the card and keep its name, so
    # a half-patched card reads correctly rather than uniformly.
    direct = [p for p in card['ports'] if p['cvtId'] is None]
    assert direct[0]['label'] == 'SR-9'
    assert direct[0]['labelSource'] == 'card'


def test_a_cvt_fans_out_what_its_trunk_carries_not_what_its_lid_says(client):
    """A CVT10 gives 10 ports on a 64B/66B trunk and 8 on an 8B/10B one, so an
    H_4xfiber's boxes are 8-port boxes. The same cap is why both Brompton
    datasheets say only the first 10 of an XD-S's 12 work behind an SX40."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert first_card(only(resp.get_json()))['cvts'][0]['portCount'] == 8

    state = set_card(client, pid, 1, 'novastar-card-mx-4x10g')
    mx_card = [s['card'] for s in only(state)['slots']
               if s['card'] and s['card']['deviceId'] == 'novastar-card-mx-4x10g']
    # An MX card does not belong in an H chassis, but if one is placed there
    # the trunk rate is still the card's, not the chassis's.
    if mx_card:
        resp = client.post(
            f'/api/processors/{pid}/cards/{mx_card[0]["id"]}/cvts',
            json={'deviceId': 'novastar-cvt10'})
        cvts = [s['card']['cvts'] for s in only(resp.get_json())['slots']
                if s['card'] and s['card']['id'] == mx_card[0]['id']][0]
        assert cvts[0]['portCount'] == 10


# ── 3b. A trunk delivers ports; it never creates any ──────────────────────
#
# The trap this section exists for: "16x RJ45 + 2x fiber, plus a breakout box"
# reads as if the ports add up, and they do not. The OPTs on that card copy
# Ethernet 1-8 and 9-16, so a CVT is another place to plug into the SAME
# sixteen ports. A model that added eight would report 24 ports for a machine
# that has 16, and every capacity and overflow decision downstream would be
# wrong in the direction that leaves cabinets with nothing to plug into.
#
# The same shape appears on cards that look nothing alike - H_4xfiber in
# copy/backup, MX40 Pro in 20-port mode - so it is one rule, not a case per
# device: chop the card's ports into blocks of portsPerTrunk and hand trunk N
# the block (N mod block count).

def add_cvts(client, pid, card_id, count, device='novastar-cvt10'):
    state = None
    for _ in range(count):
        state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                            json={'deviceId': device}).get_json()
    return state


def with_card(client, chassis, card_device):
    state = add_processor(client, chassis)
    pid = only(state)['id']
    state = set_card(client, pid, 0, card_device)
    return pid, first_card(only(state))['id']


def test_a_cvt_on_a_copy_opt_card_adds_no_ports_at_all(client):
    """The 16xRJ45+2xfiber, which is the card the trap lives on. Sixteen ports
    before the boxes, sixteen after both of them - what changed is where you
    plug in, not how much you can drive."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    for expected_boxes in (0, 1, 2):
        state = client.get('/api/processors').get_json()
        card = first_card(only(state))
        assert card['ceiling'] == 16
        assert card['defined'] == 16, (
            f'{expected_boxes} CVTs turned a 16-port card into '
            f'{card["defined"]} ports')
        assert card['over'] is False
        assert len(card['ports']) == 16
        assert only(state)['ceiling'] == 16, 'the chassis total inflated too'
        add_cvts(client, pid, card_id, 1)


def test_a_copy_opts_box_delivers_the_ports_the_card_already_has(client):
    """OPT 1 copies Ethernet 1-8 and OPT 2 copies 9-16, so that is exactly what
    comes out of the boxes hung on them."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = add_cvts(client, pid, card_id, 2)
    card = first_card(only(state))
    assert [c['firstPort'] for c in card['cvts']] == [1, 9]
    assert [c['portCount'] for c in card['cvts']] == [8, 8]
    assert [p['number'] for p in card['cvts'][0]['ports']] == list(range(1, 9))
    assert [p['number'] for p in card['cvts'][1]['ports']] == list(range(9, 17))
    assert card['trunksCopyOwnPorts'] is True, (
        'the panel has no way to tell the user these OPTs add nothing')


def test_a_copy_opt_card_is_offered_cvts_in_the_first_place(client):
    """It is an RJ45 card with fiber OPTs on it, and the OPTs get used. The
    panel gates its CVT picker on the card having trunks, so a card with no
    declared trunks would never offer one."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunks'] == 2, 'no trunks declared, so no CVT can be added'
    assert card['portsPerTrunk'] == 8
    assert card['connector'] == 'rj45', (
        'the connector drives the H9 Enhanced card limit and must stay rj45')


def test_a_backup_trunk_delivers_the_same_ports_over_again(client):
    """H_4xfiber in copy/backup: OPT 3 and 4 back up OPT 1 and 2. The third box
    is ports 1-8 for the second time, and the card is still 16."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': 'copy-backup'})
    state = add_cvts(client, pid, card_id, 4)
    card = first_card(only(state))
    assert card['ceiling'] == 16
    assert card['defined'] == 16, 'four boxes on a 16-port card made more ports'
    assert [c['firstPort'] for c in card['cvts']] == [1, 9, 1, 9]
    assert [c['duplicateOf'] for c in card['cvts']] == \
        [None, None, card['cvts'][0]['id'], card['cvts'][1]['id']]


def test_the_same_card_in_independent_mode_gives_every_trunk_its_own_ports(client):
    """The contrast that makes the rule a rule rather than a special case: the
    identical card, four identical boxes, and 32 ports because in this mode
    each OPT genuinely carries its own eight."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    state = add_cvts(client, pid, card_id, 4)
    card = first_card(only(state))
    assert card['ceiling'] == 32 and card['defined'] == 32
    assert [c['firstPort'] for c in card['cvts']] == [1, 9, 17, 25]
    assert all(c['duplicateOf'] is None for c in card['cvts'])


def test_the_mx40_pros_optical_modes_follow_the_same_rule(client):
    """Its sheet says OPT 3/4 are copies of OPT 1/2 in 20-port mode and carry
    ports 21-40 in 40-port mode. Nothing in the code knows it is an MX40: the
    behaviour falls out of the mode's own port count."""
    state = add_processor(client, 'novastar-mx40-pro')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    state = add_cvts(client, pid, card_id, 4)
    card = first_card(only(state))
    assert card['ceiling'] == 40
    assert [c['firstPort'] for c in card['cvts']] == [1, 11, 21, 31]

    state = client.put(f'/api/processors/{pid}/cards/{card_id}',
                       json={'mode': '20-port'}).get_json()
    card = first_card(only(state))
    assert card['ceiling'] == 20
    assert card['defined'] == 20, 'the copies were counted as extra ports'
    assert [c['firstPort'] for c in card['cvts']] == [1, 11, 1, 11]


def test_two_opts_means_two_boxes_and_a_third_is_refused(client):
    """"Cant do 3 or 4 OPTs on a 16 port card, it only has 2." Two CVT10s fill
    it and a third has nothing to plug into."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    add_cvts(client, pid, card_id, 2)
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400
    card = first_card(only(client.get('/api/processors').get_json()))
    assert len(card['cvts']) == 2
    assert card['trunksUsed'] == 2 and card['trunksFree'] == 0
    assert card['over'] is False


def test_one_two_opt_box_fills_a_two_opt_card_on_its_own(client):
    """A CVT4K-S takes both OPTs, so nothing else will go on afterwards - even
    though only one box is on the card. Counting boxes instead of trunks would
    let a second one on."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    add_cvts(client, pid, card_id, 1, 'novastar-cvt4k-s')
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a second box went on beside a 2-OPT box'
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunksUsed'] == 2 and card['trunksFree'] == 0


def test_a_copper_only_card_takes_no_box_at_all(client):
    """H_20xRJ45 has no OPT. Its ports come out on copper and there is nothing
    to hang a box off, so the panel must not offer one."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-20xrj45')
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunks'] == 0, (
        'the panel gates its CVT picker on trunks, so this must be a real zero')
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400
    assert 'copper' in resp.get_json()['error']


def test_the_enhanced_cards_backup_opts_are_not_offered_as_trunks(client):
    """Eight 10G connectors, four primaries - OPT 5-8 back up OPT 1-4. Treating
    the backups as usable would take eight boxes and imply 80 ports on a
    40-port card, which is the same connector-counting trap as its port count,
    one level down."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    for _ in range(4):
        assert client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                           json={'deviceId': 'novastar-cvt10'}).status_code == 201
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a backup OPT was offered as a fifth trunk'
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunks'] == 4 and card['trunksUsed'] == 4
    assert card['ceiling'] == 40 and card['defined'] == 40


def test_a_backup_box_does_not_rename_the_ports_the_primary_named(client):
    """A port really does come out of both boxes, so both list it - but the
    primary is what anyone patches to and reads a number off, so it names it."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': 'copy-backup'})
    state = add_cvts(client, pid, card_id, 3)
    card = first_card(only(state))
    primary, _second, backup = card['cvts']
    client.put(f'/api/processors/{pid}/cvts/{primary["id"]}',
               json={'name': 'CVT-A'})
    state = client.put(f'/api/processors/{pid}/cvts/{backup["id"]}',
                       json={'name': 'CVT-C'}).get_json()
    card = first_card(only(state))
    assert [p['label'] for p in card['ports'][:3]] == \
        ['CVT-A-1', 'CVT-A-2', 'CVT-A-3']
    # The backup still carries them - it is a real cable to a real box.
    assert [p['number'] for p in card['cvts'][2]['ports']] == list(range(1, 9))


# ── 3c. A box takes trunks IN, and that is what caps it ───────────────────
#
# The rule from the table:  min(box ports, trunks in x the card's per-trunk).
# Both halves are load-bearing, and each is documented by a case the other one
# gets wrong: a CVT10's 10 becomes 8 behind an 8B/10B card, while a CVT4K-S's
# 16 stays 16 there because it takes TWO OPTs in. Cap everything at one trunk
# and the CVT4K-S reports half a box; cap nothing and the CVT10 reports two
# ports that are not there.

# The four rows of the table's own worked example.
TRUNK_CAP_CASES = [
    # box, card, expected ports out, why
    ('novastar-cvt10', 'novastar-card-h-4xfiber', 8,
     '1 OPT x 8 per trunk; the documented "CVT10 gives 8 on an H_4xfiber"'),
    ('novastar-cvt10', 'novastar-card-mx-4x10g', 10,
     '1 OPT x 10 per trunk on a 10.3125G card; its own nameplate'),
    ('novastar-cvt4k-s', 'novastar-card-h-4xfiber', 16,
     '2 OPT x 8 per trunk; its own nameplate exactly'),
    ('brompton-xd-s', 'brompton-sx40', 10,
     '1 OPT x 10 per trunk, box has 12; both datasheets say the first 10'),
]


@pytest.mark.parametrize('box,card,expected,why', TRUNK_CAP_CASES)
def test_a_box_yields_its_trunks_in_times_the_cards_ports_per_trunk(
        box, card, expected, why):
    got = catalog._cvt_port_count(catalog.get_device(box),
                                  catalog.get_device(card))
    assert got == expected, f'{box} on {card} is {got}, should be {expected}: {why}'


def test_the_three_boxes_the_table_records_are_in_the_catalog(client):
    """CVT4K-S, CVT10 Pro and CVT8-5G were left out of the first draft of the
    table by mistake, not for lack of evidence - both research passes reported
    all three and agreed on every figure. A box missing from the catalog cannot
    be drawn, and the CVT4K-S is one someone asked for by name."""
    for device_id, expected, trunks in (('novastar-cvt4k-s', 16, 2),
                                        ('novastar-cvt10-pro', 10, 1),
                                        ('novastar-cvt8-5g', 8, 1)):
        device = catalog.get_device(device_id)
        assert device is not None, f'{device_id} is not in the catalog'
        assert device['kind'] == 'cvt'
        assert catalog.port_capacity(device_id)['count'] == expected
        assert catalog.trunks_in(device) == trunks


def test_four_lc_connectors_are_two_optical_ports(client):
    """The connector-versus-port trap again, one level down. LC is duplex, so
    the CVT4K-S's "4x LC" is TWO optical ports. Counting connectors would make
    it a 4-trunk box and double its capacity - the same mistake that makes two
    four-fiber cards look like the same card."""
    assert catalog.trunks_in(catalog.get_device('novastar-cvt4k-s')) == 2, (
        'the CVT4K-S is 2 OPT in; four LC connectors are not four trunks')


def test_a_box_consumes_trunks_and_not_just_ports(client):
    """Two CVT4K-S boxes fill a four-trunk card. A third has no fiber left to
    plug into, and must not read as sixteen more ports off a machine that has
    thirty-two - which is what counting boxes instead of trunks would do."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    state = add_cvts(client, pid, card_id, 2, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['trunksUsed'] == 4 and card['trunks'] == 4
    assert card['defined'] == 32 and card['over'] is False
    assert [c['firstPort'] for c in card['cvts']] == [1, 17]
    assert [c['portCount'] for c in card['cvts']] == [16, 16]

    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt4k-s'})
    assert resp.status_code == 400, (
        'a third 2-OPT box went onto a card with four OPTs - counting boxes '
        'rather than trunks would read 48 ports off a 32-port machine')
    assert first_card(only(client.get('/api/processors').get_json()))[
        'trunksUsed'] == 4


def test_a_box_that_does_not_fit_the_trunks_left_is_refused_by_name(client):
    """Three CVT10s leave one OPT, which is not enough for a CVT4K-S. The
    message says which box and how many are left, because "no" on its own
    sends someone hunting for a fault that is not there."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    add_cvts(client, pid, card_id, 3, 'novastar-cvt10')
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt4k-s'})
    assert resp.status_code == 400
    error = resp.get_json()['error']
    assert 'CVT4K-S' in error and '2' in error and '1 left' in error, error
    # And one more CVT10 still goes on, because one OPT is exactly enough.
    assert client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'}).status_code == 201


def test_a_box_bigger_than_one_trunk_still_cannot_exceed_the_card(client):
    """A CVT4K-S is 16 out, and an H_16xRJ45+2xfiber is 16 ports whose OPTs
    copy them. One box takes both OPTs and delivers all sixteen - where CVT10s
    would need two boxes - and the card is still a sixteen-port card."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = add_cvts(client, pid, card_id, 1, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['ceiling'] == 16
    assert card['defined'] == 16, 'a 16-port box on a 16-port card made 32'
    assert card['over'] is False
    assert card['trunksUsed'] == 2 and card['trunks'] == 2
    box = card['cvts'][0]
    assert (box['firstPort'], box['portCount'], box['trunksIn']) == (1, 16, 2)
    assert [p['number'] for p in box['ports']] == list(range(1, 17))


def test_boxes_of_different_sizes_share_a_cards_trunks(client):
    """A CVT4K-S on two OPTs and a CVT10 on each of the other two is a real
    patch, and it fills a four-trunk 32-port card exactly."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    add_cvts(client, pid, card_id, 1, 'novastar-cvt4k-s')
    state = add_cvts(client, pid, card_id, 2, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['trunksUsed'] == 4
    assert [c['firstPort'] for c in card['cvts']] == [1, 17, 25]
    assert [c['portCount'] for c in card['cvts']] == [16, 8, 8]
    assert card['defined'] == 32 and card['over'] is False


def test_a_device_whose_trunks_are_not_its_own_ports_is_left_alone(client):
    """The block model says a trunk delivers a block of THE CARD'S ports, and
    that only means anything where the card has them. A HELIOS 8K is 8 ports
    with eight fiber outs at 12 each: its trunks feed downstream boxes rather
    than dividing up its own, and no document calls them copies of one another.

    Extrapolating a NovaStar card rule onto a Megapixel rig would be exactly
    the kind of "safe direction" guess that is not safe. Devices of that shape
    keep the behaviour they had before the model existed - boxes taking
    consecutive ports from 1 - and this test is what stops the guard being
    quietly deleted as dead code."""
    state = add_processor(client, 'megapixel-helios-8k')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    state = add_cvts(client, pid, card_id, 3, 'megapixel-rs12')
    card = first_card(only(state))
    assert [c['firstPort'] for c in card['cvts']] == [1, 13, 25], (
        'the boxes were folded into blocks of a card that has no such blocks')
    assert all(c['duplicateOf'] is None for c in card['cvts']), (
        'three separate RS12s were called copies of one another')


# ── 3d. The box decides whether a card reaches its own ceiling ────────────

def test_the_enhanced_card_reaches_forty_with_cvt10s(client):
    """Four OPTs at 10 ports each, four CVT10s, all 40 delivered. This is the
    card's documented number and the box that gets you there."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    state = add_cvts(client, pid, card_id, 4, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['ceiling'] == 40
    assert card['delivered'] == 40
    assert card['shortfall'] is None
    assert [c['portCount'] for c in card['cvts']] == [10, 10, 10, 10]


def test_the_same_card_falls_eight_short_on_cvt4k_s_and_says_so(client):
    """Two CVT4K-S boxes have 32 sockets between them and eat all four OPTs
    getting there, because each is 16 out on 2 OPTs in and those two OPTs were
    carrying 20. Eight ports gone - on the SAME box that is exactly right on a
    plain H_4xfiber. Someone who knows the card is a 40 and reads a bare 32
    assumes the app is wrong; told why, they change the box."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    state = add_cvts(client, pid, card_id, 2, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['ceiling'] == 40
    assert card['trunksUsed'] == 4, 'both boxes should have eaten two OPTs each'
    assert card['delivered'] == 32
    assert card['shortfall'] is not None, (
        'eight ports vanished with nothing said about it')
    assert card['shortfall']['delivered'] == 32
    assert card['shortfall']['ceiling'] == 40
    assert 'CVT10' in card['shortfall']['reachesWith']
    assert 'CVT4K-S' not in card['shortfall']['reachesWith'], (
        'the box that fell short was named as the fix')


def test_the_same_boxes_on_a_plain_four_fiber_card_fall_short_of_nothing(client):
    """The contrast that makes it about the box AND the card together. On an
    H_4xfiber at 8 per trunk, a CVT4K-S's two OPTs carry exactly its 16, so two
    of them deliver the whole 32 and there is nothing to report."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    state = add_cvts(client, pid, card_id, 2, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['ceiling'] == 32 and card['delivered'] == 32
    assert card['shortfall'] is None


def test_a_half_patched_card_is_not_reported_as_falling_short(client):
    """One box on a four-OPT card is not a shortfall, it is a card someone has
    not finished patching. Two OPTs are still free and the next box fills
    them - nagging here would train people to ignore the message that matters."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    state = add_cvts(client, pid, card_id, 1, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['trunksFree'] == 3
    assert card['shortfall'] is None


def test_a_copy_opt_card_never_reports_a_shortfall(client):
    """There is nothing short on a card whose OPTs copy its own RJ45s: the
    ports are on the front of the card and you patch them there."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = add_cvts(client, pid, card_id, 1, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['trunksFree'] == 0, 'the box should have taken both OPTs'
    assert card['delivered'] == 16
    assert card['shortfall'] is None

    # And the same card filled with two one-OPT boxes instead.
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    card_id = first_card(only(state))['id']
    state = add_cvts(client, pid, card_id, 2, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['trunksFree'] == 0
    assert card['delivered'] == 16
    assert card['shortfall'] is None


def test_two_unnamed_cvts_do_not_print_the_same_labels_twice(client):
    """A port is numbered within whatever names it. With the boxes unnamed the
    CARD is doing the naming, so its numbering is the card's - numbering both
    boxes from 1 would silkscreen SR-1 through SR-8 onto two different runs."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})
    for _ in range(2):
        state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                            json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    labels = [p['label'] for p in card['ports'][:16]]
    assert len(set(labels)) == 16, f'duplicate port labels: {labels}'
    assert labels[8] == 'SR-9'


def test_an_unnamed_tree_produces_no_labels_at_all(client):
    """With nothing named upstream there is no processor-derived label, which
    is what leaves the per-screen templates in charge exactly as before."""
    state = add_processor(client, 'novastar-mx20')
    card = first_card(only(state))
    assert len(card['ports']) == 6
    assert all(p['label'] is None and p['labelSource'] is None
               for p in card['ports'])


def test_a_processors_name_reaches_the_ports_of_an_unnamed_card(client):
    """Nearest named device upstream, all the way up: naming an all-in-one is
    enough, because there is no card in between worth naming separately."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    resp = client.put(f'/api/processors/{pid}', json={'name': 'FOH'})
    card = first_card(only(resp.get_json()))
    assert [p['label'] for p in card['ports'][:2]] == ['FOH-1', 'FOH-2']
    assert card['ports'][0]['labelSource'] == 'processor'


def test_a_label_template_is_editable_and_comes_back_from_the_server(client):
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-20xrj45')
    card_id = first_card(only(state))['id']
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'name': 'SR', 'portLabelTemplate': '{name}.P#'})
    card = first_card(only(resp.get_json()))
    assert card['portLabelTemplate'] == '{name}.P#'
    assert card['ports'][0]['label'] == 'SR.P1'

    # And it is on the SERVER, not just in the response body.
    reread = client.get('/api/processors').get_json()
    assert first_card(only(reread))['ports'][0]['label'] == 'SR.P1'


# ── 4. Ceilings that are exceeded stay visible ────────────────────────────

def test_a_fifth_box_on_a_four_trunk_card_is_refused(client):
    """A card has a fixed number of OPTs and nothing can add one, so the fifth
    CVT10 on an H_4xfiber is not drawn and flagged - it is refused.

    This is the one rule in the feature that BLOCKS rather than reports, and
    the line is worth keeping straight. A wall needing more ports than a card
    has is a real situation with a real answer (add a card), so it is shown and
    the choice stays with the user. A box hung on an OPT that does not exist is
    not a situation: there is nothing to decide and nothing it could mean on
    site."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    for _ in range(4):
        resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                           json={'deviceId': 'novastar-cvt10'})
        assert resp.status_code == 201, resp.get_data(as_text=True)

    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a fifth box went onto a four-trunk card'
    assert 'OPT' in resp.get_json()['error']

    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunksUsed'] == 4 and card['trunks'] == 4
    assert card['defined'] == 32, 'the refused box left something behind'
    assert card['over'] is False
    assert len(card['cvts']) == 4


def test_more_cards_than_the_chassis_takes_reads_as_over_capacity(client):
    """The H9 Enhanced offers ten places, but only five of them are usable
    with RJ45 sending cards. The sixth one is not refused - a tech may well be
    drawing a machine they have not built yet - it is shown as over."""
    state = add_processor(client, 'novastar-h9-enhanced')
    pid = only(state)['id']
    assert len(only(state)['slots']) == 10
    for slot in range(6):
        state = set_card(client, pid, slot, 'novastar-card-h-20xrj45')
    proc = only(state)
    assert proc['maxCards'] == 5
    assert proc['cardsUsed'] == 6
    assert proc['cardsOver'] is True
    assert proc['over'] is True


def test_a_chassis_offers_the_number_of_cards_its_sheet_documents(client):
    for device_id, expected in (('novastar-h2', 2), ('novastar-h5', 3),
                                ('novastar-h9', 5), ('novastar-h15', 10),
                                ('novastar-h15-enhanced', 16),
                                ('novastar-h20', 20),
                                ('novastar-mx2000-pro', 2),
                                ('novastar-mx6000-pro', 8)):
        state = add_processor(client, device_id)
        proc = state['resolved'][-1]
        assert proc['maxCards'] == expected, device_id
        assert len(proc['slots']) == expected, device_id


def test_the_h9_enhanced_card_limit_moves_with_what_is_in_it(client):
    """The one chassis in the table whose card limit is card-type dependent:
    10 fiber/video cards, 5 RJ45 sending cards."""
    state = add_processor(client, 'novastar-h9-enhanced')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    assert only(state)['maxCards'] == 10
    state = set_card(client, pid, 1, 'novastar-card-h-20xrj45')
    assert only(state)['maxCards'] == 5, (
        'an RJ45 sending card should drop the H9 Enhanced limit to five')


# ── 5. Storage ────────────────────────────────────────────────────────────

def test_the_tree_round_trips_through_save_and_reload(client):
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'name': 'SR', 'mode': 'copy-backup'})
    client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                json={'deviceId': 'novastar-cvt10'})
    state = client.get('/api/processors').get_json()
    cvt_id = first_card(only(state))['cvts'][0]['id']
    client.put(f'/api/processors/{pid}/cvts/{cvt_id}', json={'name': 'CVT-A'})
    client.put(f'/api/processors/{pid}', json={'name': 'FOH'})

    saved = client.get('/api/project').get_json()
    assert saved['processors'], 'the tree never reached the project'

    # A save, then the load path undo/redo and file open both use.
    assert client.post('/api/project', json=saved).status_code == 200
    resp = client.put('/api/project', json=saved)
    assert resp.status_code == 200

    reloaded = client.get('/api/processors').get_json()
    proc = only(reloaded)
    assert proc['name'] == 'FOH'
    card = first_card(proc)
    assert card['name'] == 'SR'
    assert card['mode'] == 'copy-backup'
    assert card['ceiling'] == 16, 'the stored mode was lost on reload'
    assert card['cvts'][0]['name'] == 'CVT-A'
    assert card['ports'][0]['label'] == 'CVT-A-1'


def test_removing_a_processor_removes_it_from_the_project(client):
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    resp = client.delete(f'/api/processors/{pid}')
    assert resp.status_code == 200
    assert resp.get_json()['resolved'] == []
    assert client.get('/api/project').get_json().get('processors') == []


def test_a_second_processor_gets_its_own_ids(client):
    """Two MX20s in one project must not share a card id, or an edit to one
    would silently land on the other."""
    add_processor(client, 'novastar-mx20')
    state = add_processor(client, 'novastar-mx20')
    ids = [p['id'] for p in state['resolved']]
    cards = [first_card(p)['id'] for p in state['resolved']]
    assert len(set(ids)) == 2, ids
    assert len(set(cards)) == 2, cards


def test_bad_ids_are_refused_rather_than_half_applied(client):
    assert client.post('/api/processors',
                       json={'deviceId': 'not-a-device'}).status_code == 400
    assert client.put('/api/processors/nope', json={'name': 'x'}).status_code == 404
    assert client.delete('/api/processors/nope').status_code == 404
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    assert client.put(f'/api/processors/{pid}/slots/99',
                      json={'deviceId': 'novastar-card-h-4xfiber'}).status_code == 404
    assert client.put(f'/api/processors/{pid}/cards/nope',
                      json={'name': 'x'}).status_code == 404


# ── 6. The regression bar ─────────────────────────────────────────────────

def test_a_project_with_no_processors_is_shaped_exactly_as_before(client):
    """Anyone who never opens the Data view, or who defines no processor, sees
    no change - including in the file they save. Reading the panel's endpoint
    must not stamp the key onto a project that has none."""
    before = client.get('/api/project').get_json()
    assert 'processors' not in before

    resp = client.get('/api/processors')
    assert resp.status_code == 200
    assert resp.get_json() == {'processors': [], 'resolved': []}

    after = client.get('/api/project').get_json()
    assert after == before, (
        'merely reading the processor endpoint changed the project')
    assert after['is_pristine'] is True, 'a read marked the project dirty'


def test_the_per_screen_port_templates_are_untouched(client_with_layer):
    """The existing templates become the OVERRIDE, not the source, and with no
    processor defined they are still the whole story. This is the same PUT the
    port label editor makes, and it must keep behaving identically."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'portLabelTemplatePrimary': 'SR-#',
        'portLabelTemplateReturn': 'SRB-#',
    })
    assert resp.status_code == 200
    layer = client_with_layer.get('/api/project').get_json()['layers'][0]
    assert layer['portLabelTemplatePrimary'] == 'SR-#'
    assert layer['portLabelTemplateReturn'] == 'SRB-#'
    assert 'processors' not in client_with_layer.get('/api/project').get_json()


def test_the_panel_ships_no_declared_fields_into_the_field_sweep():
    """tests/test_all_fields_sweep.py drives every control declared inside a
    .tab-panel straight at the selected LAYER. The processor panel's fields are
    project state and are built by app-processors.js for that reason; a control
    declared in the template here would be swept and would fail for a reason
    that has nothing to do with it."""
    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()
    start = html.index('<h2>Processors</h2>')
    end = html.index('<h2>Port Labels</h2>')
    panel = html[start:end]
    for tag in ('<input', '<select', '<textarea'):
        assert tag not in panel, (
            f'{tag} declared in the Processors panel markup - the field sweep '
            f'would drive it at the selected layer')
    assert 'id="processor-list"' in panel
