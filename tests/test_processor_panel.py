"""The processor tree behind the hardware dock: catalog, ports, labels, storage.

The dock is the one hardware surface (the Signal sidebar and its Processors /
Port Numbering panels retired into it): the tree renders as dock sections whose
headers carry the names inline, each level's configuration lives behind its
header's ⚙ gear popover, the issues render as the strip under the dock's
header, and adding a processor is the header bar's own picker. A processor
drives the wall, and that surface has to model it the way the hardware is
actually built, so these tests are mostly about the four things that make
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
    ('novastar-vx400-pro', 4),
    ('novastar-vx600', 6),
    ('novastar-vx600-pro', 6),
    ('novastar-vx1000', 10),
    ('novastar-vx1000-pro', 10),
    ('novastar-mctrl4k', 16),
    ('novastar-mctrl-r5', 8),
    ('novastar-mctrl700', 6),
    ('novastar-mctrl600', 4),
    ('novastar-mctrl300', 2),
    ('novastar-msd300', 2),
    ('novastar-novapro-uhd', 16),
    ('novastar-novapro-uhd-jr', 16),
    ('novastar-novapro-hd', 4),
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


def test_the_novapro_uhds_opts_copy_their_own_copper():
    """Both NovaPro UHDs are the H_16xRJ45+2xfiber shape, not the H_4xfiber
    one: 16 copper ports on the unit, and every OPT carries ports the copper
    already has. Their spec sheets state the layout verbatim - OPT 1/2 transmit
    Ethernet 1-8 / 9-16, OPT 3/4 are their copy/hot backup - which is exactly
    what copy delivery with four trunks at 8 per trunk produces. No documented
    OPT mode adds a port, so unlike the MX40 Pro there is no mode switch."""
    for device_id in ('novastar-novapro-uhd', 'novastar-novapro-uhd-jr'):
        device = catalog.get_device(device_id)
        assert device['form'] == 'all-in-one', device_id
        assert device['trunkDelivery'] == 'copy', (
            f'{device_id}: its OPTs carry the copper it already has; distinct '
            f'delivery would count the same sixteen ports twice')
        assert device['trunks'] == 4
        assert device['portsPerTrunk'] == 8
        modes = device['ports']['modes']
        assert len(modes) == 1, (
            f'{device_id} grew a mode switch nobody documented: {modes}')
        assert catalog.port_capacity(device_id)['count'] == 16
        assert 'redundancy' not in device, (
            f'{device_id}: OPT 3/4 backing up OPT 1/2 is fixed wiring, not a '
            f'port-halving redundancy mode')


# ── 1b. Matt's CVT rules: attachment is rate-matched, per documented rate ──
#
# Two rulings, both verbatim. The first: "anything that has opt fiber 10g
# ports needs cvt support" - and the 10G qualifier is load-bearing, not
# decoration. The second (2026-08-21): "40g fiber ports only worjks with cvt
# 8 f5 boxes" - a 40G OPT takes the CVT8-5G and ONLY the CVT8-5G, which cuts
# both ways: the 10G boxes stay off 40G trunks, and the CVT8-5G stays off
# 10G ones. A device whose fiber is another rate (NovaPro HD, 1G per Matt)
# or whose sheet states no rate at all (VX400) gets NO trunks, however
# plausible a rate would be - and a documented rate with UNDOCUMENTED
# carriage (KU20 at 10G, CX40 Pro at 40G) still refuses, because there is no
# portsPerTrunk to give the block model. Every entry below was swept against
# the device's own current spec sheet, and the quotes live in
# docs/processor-port-table.md.
#
# These lists are exhaustive on purpose: the exact-set test underneath fails
# both when a swept device loses its trunks AND when any NovaStar device
# grows trunks nobody documented.
NOVASTAR_10G_TRUNKS = [
    # device, trunks, ports per trunk, delivery
    ('novastar-mx40-pro', 4, 10, 'distinct'),
    ('novastar-mx30', 2, 10, 'copy'),
    ('novastar-mx20', 2, 6, 'copy'),
    ('novastar-vx400-pro', 2, 4, 'copy'),
    # VX600 / VX1000 non-Pro: OPT 1 is a documented 10G output copying the
    # copper; OPT 2 copies too but its sheet names NO rate for it, so it is
    # not a trunk - one ruling from Matt away from 2.
    ('novastar-vx600', 1, 6, 'copy'),
    ('novastar-vx600-pro', 2, 6, 'copy'),
    ('novastar-vx1000', 1, 10, 'copy'),
    ('novastar-vx1000-pro', 2, 10, 'copy'),
    ('novastar-vx2000-pro', 4, 10, 'copy'),
    ('novastar-mctrl4k', 4, 8, 'copy'),
    ('novastar-mctrl660-pro', 2, 6, 'copy'),
    ('novastar-mctrl-r5', 2, 8, 'copy'),
    ('novastar-novapro-uhd', 4, 8, 'copy'),
    ('novastar-novapro-uhd-jr', 4, 8, 'copy'),
    ('novastar-card-h-16xrj45-2xfiber', 2, 8, 'copy'),
    ('novastar-card-h-4xfiber', 4, 8, 'distinct'),
    ('novastar-card-h-4xfiber-enhanced', 4, 10, 'distinct'),
    ('novastar-card-mx-4x10g', 4, 10, 'distinct'),
]

# The 40G roster, under the 2026-08-21 ruling. Same sweep standard as the
# 10G list: a trunk only where the device's own sheet documents what the
# fiber carries. The CX80 Pro's sheet does, verbatim - "1 corresponds to
# Ethernet ports 1~8. 2 corresponds to Ethernet ports 9~16." - which is the
# H_16xRJ45+2xfiber shape: OPTs carrying the unit's own copper, so copy
# delivery. The 1x40G card was in the catalog from the first research pass
# with its own documented 8-per-fiber figure. The CX40 Pro is NOT here: its
# sheet states the 40G rate and nothing about carriage, so it stays refused
# the same way the KU20 does at 10G.
NOVASTAR_40G_TRUNKS = [
    # device, trunks, ports per trunk, delivery
    ('novastar-cx80-pro', 2, 8, 'copy'),
    ('novastar-card-mx-1x40g', 1, 8, 'distinct'),
]


@pytest.mark.parametrize('device_id,trunks,per_trunk,delivery',
                         NOVASTAR_10G_TRUNKS)
def test_a_documented_10g_opt_device_accepts_a_box(device_id, trunks,
                                                   per_trunk, delivery):
    device = catalog.get_device(device_id)
    assert device['trunks'] == trunks, device_id
    assert device['portsPerTrunk'] == per_trunk, device_id
    assert device.get('trunkDelivery', 'distinct') == delivery, device_id
    assert device['trunkRate'] == '10G', device_id
    card = catalog.new_card(device_id, 'sweep', fixed=True)
    ok, why = catalog.can_add_cvt(card, 'novastar-cvt10')
    assert ok, f'{device_id} refuses a box despite documented 10G OPTs: {why}'
    # The rate rule's other edge: the 40G box does not hang off a 10G OPT.
    ok, why = catalog.can_add_cvt(card, 'novastar-cvt8-5g')
    assert not ok, f'{device_id} took a CVT8-5G onto a 10G trunk'
    assert '40G' in why and '10G' in why, why


@pytest.mark.parametrize('device_id,trunks,per_trunk,delivery',
                         NOVASTAR_40G_TRUNKS)
def test_a_documented_40g_opt_device_takes_only_the_cvt8_5g(device_id, trunks,
                                                            per_trunk,
                                                            delivery):
    """The ruling, cut both ways on every 40G device: the CVT8-5G attaches,
    and each box of the 10G line - CVT10, CVT10 Pro, CVT4K-S - is refused
    with the rate named in the reason."""
    device = catalog.get_device(device_id)
    assert device['trunks'] == trunks, device_id
    assert device['portsPerTrunk'] == per_trunk, device_id
    assert device.get('trunkDelivery', 'distinct') == delivery, device_id
    assert device['trunkRate'] == '40G', device_id
    card = catalog.new_card(device_id, 'sweep', fixed=True)
    ok, why = catalog.can_add_cvt(card, 'novastar-cvt8-5g')
    assert ok, f'{device_id} refuses the CVT8-5G: {why}'
    for box in ('novastar-cvt10', 'novastar-cvt10-pro', 'novastar-cvt4k-s'):
        ok, why = catalog.can_add_cvt(card, box)
        assert not ok, f'{device_id} took {box} onto a 40G trunk'
        assert '40G' in why and '10G' in why, why


def test_no_novastar_device_carries_trunks_the_sweep_did_not_grant():
    """Both directions at once. Trunks lost: a swept device dropped off the
    lists silently. Trunks grown: someone gave a device CVT support without
    a documented OPT rate AND documented carriage behind it - the KU20 (10G,
    carriage unstated), the CX40 Pro (40G, carriage unstated), the VX400 (no
    rate stated), the NovaPro HD (1G per Matt) and every copper-only sender
    must stay boxless until a sheet or a ruling from Matt says otherwise."""
    pinned = {device_id for device_id, *_ in
              NOVASTAR_10G_TRUNKS + NOVASTAR_40G_TRUNKS}
    actual = {d['id'] for d in catalog.load_catalog()['devices']
              if d.get('vendor') == 'NovaStar' and d.get('trunks')}
    assert actual == pinned, (
        f'grew trunks: {sorted(actual - pinned)}; '
        f'lost trunks: {sorted(pinned - actual)}')


def test_the_cx40_pro_stays_refused_for_carriage_not_rate(client):
    """The CX40 Pro's sheet states its OPT is 40Gbps - a rate the CVT8-5G
    takes - and states nothing about what the OPT carries, so it refuses a
    box exactly the way the KU20 does at 10G: no portsPerTrunk to give the
    block model, no trunks until a sheet or Matt settles the carriage. The
    ruling changed WHY it refuses, not whether."""
    device = catalog.get_device('novastar-cx40-pro')
    assert 'trunks' not in device, (
        'the CX40 Pro grew trunks; its 40G carriage is still undocumented')
    assert 'carries' in device['note'], (
        'the note lost the reason no box hangs off this device')
    state = add_processor(client, 'novastar-cx40-pro')
    proc = only(state)
    pid, card_id = proc['id'], first_card(proc)['id']
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt8-5g'})
    assert resp.status_code == 400, 'a box went onto undocumented carriage'


def test_the_ku20_stays_refused_even_by_the_40g_box(client):
    """The KU20's carriage is still unruled, and no new box changes that: a
    CVT8-5G would not even rate-match its 10G OPT, and the CVT10 that would
    is refused for the carriage, same as before the 40G ruling."""
    device = catalog.get_device('novastar-ku20')
    assert 'trunks' not in device, 'the KU20 grew trunks without a ruling'
    card = catalog.new_card('novastar-ku20', 'sweep', fixed=True)
    for box in ('novastar-cvt10', 'novastar-cvt8-5g'):
        ok, _why = catalog.can_add_cvt(card, box)
        assert not ok, f'the KU20 accepted {box} with carriage unruled'


def test_the_cx80_pro_takes_the_cvt8_5g_end_to_end(client):
    """The whole path on the device the ruling unlocked: a CVT8-5G lands on
    a CX80 Pro and delivers ports 1-8 of the unit's own sixteen (copy
    delivery - the OPTs carry the copper, a box adds nothing), and a CVT10
    is refused by the route with the rates in the reason."""
    state = add_processor(client, 'novastar-cx80-pro')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10', 'pair': False})
    assert resp.status_code == 400, 'a 10G box went onto the 40G OPTs'
    assert '40G' in resp.get_json()['error']
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt8-5g',
                              'pair': False}).get_json()
    card = first_card(only(state))
    assert card['trunkRate'] == '40G'
    box = card['cvts'][0]
    assert (box['firstPort'], box['portCount']) == (1, 8)
    assert card['ceiling'] == 16 and card['defined'] == 16
    assert card['trunksCopyOwnPorts'] is True


def test_the_novapro_hds_fiber_takes_no_box(client):
    """The HD has four real optical outputs and still gets no trunks: no
    sheet maps them to any port or states a rate, and Matt settled the rate
    the sheets left open - "pro HD's are out for opt's they are 1g and
    useless with the cvts". His statement is the recorded source, the same
    way the Brompton pairing rule arrived, and 1G fails the 10G rule."""
    device = catalog.get_device('novastar-novapro-hd')
    assert 'trunks' not in device, (
        'the NovaPro HD grew trunks; its OPTs are 1G per Matt')
    assert '1G' in device['note'], (
        'the note lost the reason no box hangs off this device')
    state = add_processor(client, 'novastar-novapro-hd')
    proc = only(state)
    assert proc['ceiling'] == 4
    pid, card_id = proc['id'], first_card(proc)['id']
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a box went onto the 1G fiber'


def test_the_vx_pairs_are_split_and_each_side_keeps_its_own_sheet():
    """VX400/600/1000 and their Pros are different processors (Matt), so six
    entries, each carrying only its own sheet's fields. The split must not
    leak figures across a pair: the Pros document 2x 10G OPT and 650k per
    port; the non-Pros document no per-port figure, and their second OPT -
    or, on the VX400, both OPTs - carries no stated rate."""
    for plain_id, pro_id in (('novastar-vx400', 'novastar-vx400-pro'),
                             ('novastar-vx600', 'novastar-vx600-pro'),
                             ('novastar-vx1000', 'novastar-vx1000-pro')):
        plain, pro = catalog.get_device(plain_id), catalog.get_device(pro_id)
        assert plain and pro, f'{plain_id} / {pro_id} not both in the catalog'
        assert '/' not in plain['name'] and '/' not in pro['name'], (
            'a folded name survived the split')
        assert pro['trunks'] == 2, pro_id
        assert pro['trunkDelivery'] == 'copy', pro_id
        assert catalog.port_capacity(plain_id)['count'] == \
            catalog.port_capacity(pro_id)['count'], (
            'the pair disagrees on the one figure the sheets agree on')
    assert 'trunks' not in catalog.get_device('novastar-vx400'), (
        'the VX400 grew trunks; its sheet states no optical rate at all')


def test_a_single_trunk_vx_delivers_its_whole_copper_once(client):
    """VX1000: OPT 1 is the documented 10G output and it copies all ten
    Ethernet ports, so ONE box takes the whole unit out on fiber - and there
    is no second trunk for another. The card stays ten ports throughout."""
    state = add_processor(client, 'novastar-vx1000')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10',
                              'pair': False}).get_json()
    card = first_card(only(state))
    box = card['cvts'][0]
    assert (box['firstPort'], box['portCount']) == (1, 10)
    assert card['ceiling'] == 10 and card['defined'] == 10
    assert card['trunksCopyOwnPorts'] is True
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a second box went onto a 1-trunk device'


def test_the_mctrl_r5s_opts_are_two_copies_of_the_same_eight(client):
    """The R5's sheet: OPT 1 copies Ethernet 1-8, and OPT 2 is the copy
    channel of OPT 1 - a copy OF A COPY, so both trunks carry the same block
    and the second box duplicates the first. Eight ports before the boxes,
    eight after both."""
    device = catalog.get_device('novastar-mctrl-r5')
    assert (device['trunks'], device['portsPerTrunk']) == (2, 8)
    assert device['trunkDelivery'] == 'copy'
    assert len(device['ports']['modes']) == 1, (
        'the R5 grew a mode switch nobody documented')
    state = add_processor(client, 'novastar-mctrl-r5')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    for _ in range(2):
        state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                            json={'deviceId': 'novastar-cvt10',
                                  'pair': False}).get_json()
    card = first_card(only(state))
    assert card['ceiling'] == 8 and card['defined'] == 8
    assert [c['firstPort'] for c in card['cvts']] == [1, 1]
    assert [c['portCount'] for c in card['cvts']] == [8, 8]
    assert card['cvts'][1]['duplicateOf'] == card['cvts'][0]['id']


def test_the_legacy_senders_are_copper_only_and_say_so(client):
    """MCTRL700, MCTRL600, MCTRL300 and the MSD300 sending card: RJ45 out,
    no optical anywhere on their sheets, so no trunks and a refused box.
    None of their sheets states a device total either - 4 x 650k is
    arithmetic - so no entry claims one, and each ceiling is the sheet's own
    port count, not a sibling's (600 is 4 and 300 is 2; related products,
    separately documented)."""
    for device_id, expected in (('novastar-mctrl700', 6),
                                ('novastar-mctrl600', 4),
                                ('novastar-mctrl300', 2),
                                ('novastar-msd300', 2)):
        device = catalog.get_device(device_id)
        assert 'trunks' not in device, f'{device_id} grew trunks'
        assert catalog.port_capacity(device_id)['count'] == expected
        card = catalog.new_card(device_id, 'legacy', fixed=True)
        ok, why = catalog.can_add_cvt(card, 'novastar-cvt10')
        assert not ok, f'{device_id} accepted a box with no fiber to carry it'


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


def test_a_boxes_name_beats_the_cards(client):
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


def test_a_box_fans_out_what_its_trunk_carries_not_what_its_lid_says(client):
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

def add_boxes(client, pid, card_id, count, device='novastar-cvt10'):
    state = None
    for _ in range(count):
        state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                            # pair: False declines the NovaStar backup-box
                            # default - these tests build exact box sets, and
                            # the default has tests of its own below.
                            json={'deviceId': device, 'pair': False}).get_json()
    return state


def with_card(client, chassis, card_device):
    state = add_processor(client, chassis)
    pid = only(state)['id']
    state = set_card(client, pid, 0, card_device)
    return pid, first_card(only(state))['id']


def test_a_box_on_a_copy_trunk_card_adds_no_ports_at_all(client):
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
        add_boxes(client, pid, card_id, 1)


def test_a_copy_opts_box_delivers_the_ports_the_card_already_has(client):
    """OPT 1 copies Ethernet 1-8 and OPT 2 copies 9-16, so that is exactly what
    comes out of the boxes hung on them."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = add_boxes(client, pid, card_id, 2)
    card = first_card(only(state))
    assert [c['firstPort'] for c in card['cvts']] == [1, 9]
    assert [c['portCount'] for c in card['cvts']] == [8, 8]
    assert [p['number'] for p in card['cvts'][0]['ports']] == list(range(1, 9))
    assert [p['number'] for p in card['cvts'][1]['ports']] == list(range(9, 17))
    assert card['trunksCopyOwnPorts'] is True, (
        'the card gear has no way to tell the user these OPTs add nothing')


def test_a_copy_trunk_card_is_offered_boxes_in_the_first_place(client):
    """It is an RJ45 card with fiber OPTs on it, and the OPTs get used. The
    card's gear gates its box picker on the card having trunks, so a card
    with no declared trunks would never offer one."""
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
    state = add_boxes(client, pid, card_id, 4)
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
    state = add_boxes(client, pid, card_id, 4)
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
    state = add_boxes(client, pid, card_id, 4)
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
    add_boxes(client, pid, card_id, 2)
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
    add_boxes(client, pid, card_id, 1, 'novastar-cvt4k-s')
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10'})
    assert resp.status_code == 400, 'a second box went on beside a 2-OPT box'
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunksUsed'] == 2 and card['trunksFree'] == 0


def test_a_copper_only_card_takes_no_box_at_all(client):
    """H_20xRJ45 has no OPT. Its ports come out on copper and there is nothing
    to hang a box off, so the card's gear must not offer one."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-20xrj45')
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['trunks'] == 0, (
        'the card gear gates its box picker on trunks, so this must be a '
        'real zero')
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
    state = add_boxes(client, pid, card_id, 3)
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
    # And it carries them under the same local numbers its main shows
    # (2026-08-27: "Same with default backups for any breakout boxes") -
    # the default backup is a mirror, so the numbers never differ.
    assert [p['localNumber'] for p in card['cvts'][2]['ports']] == \
        list(range(1, 9))


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
    state = add_boxes(client, pid, card_id, 2, 'novastar-cvt4k-s')
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
    add_boxes(client, pid, card_id, 3, 'novastar-cvt10')
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
    state = add_boxes(client, pid, card_id, 1, 'novastar-cvt4k-s')
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
    add_boxes(client, pid, card_id, 1, 'novastar-cvt4k-s')
    state = add_boxes(client, pid, card_id, 2, 'novastar-cvt10')
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
    state = add_boxes(client, pid, card_id, 3, 'megapixel-rs12')
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
    state = add_boxes(client, pid, card_id, 4, 'novastar-cvt10')
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
    state = add_boxes(client, pid, card_id, 2, 'novastar-cvt4k-s')
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
    state = add_boxes(client, pid, card_id, 2, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['ceiling'] == 32 and card['delivered'] == 32
    assert card['shortfall'] is None


def test_a_half_patched_card_is_not_reported_as_falling_short(client):
    """One box on a four-OPT card is not a shortfall, it is a card someone has
    not finished patching. Two OPTs are still free and the next box fills
    them - nagging here would train people to ignore the message that matters."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-4xfiber-enhanced')
    state = add_boxes(client, pid, card_id, 1, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['trunksFree'] == 3
    assert card['shortfall'] is None


def test_a_copy_trunk_card_never_reports_a_shortfall(client):
    """There is nothing short on a card whose OPTs copy its own RJ45s: the
    ports are on the front of the card and you patch them there."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = add_boxes(client, pid, card_id, 1, 'novastar-cvt4k-s')
    card = first_card(only(state))
    assert card['trunksFree'] == 0, 'the box should have taken both OPTs'
    assert card['delivered'] == 16
    assert card['shortfall'] is None

    # And the same card filled with two one-OPT boxes instead.
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    card_id = first_card(only(state))['id']
    state = add_boxes(client, pid, card_id, 2, 'novastar-cvt10')
    card = first_card(only(state))
    assert card['trunksFree'] == 0
    assert card['delivered'] == 16
    assert card['shortfall'] is None


def test_box_owned_ports_number_off_the_boxs_own_face_whoever_names_them(
        client):
    """REVERSED on 2026-08-27, by ruling after live testing: "all cvt's are
    1-10 or 1-16" - every breakout box's face is silkscreened 1..N whichever
    trunk it hangs on, so a label numbered past N points at a socket no box
    has. This test used to pin the opposite (card-wide numbers when the CARD
    names, so two unnamed boxes never print the same labels twice), and the
    duplicates it guarded against are now the physically true reading: both
    boxes really do have a port 1, and telling them apart is the box's job -
    its name, or the trunk letter the resolve stamps on displayTitle. Ports
    on no box still number off the card, whose face IS their silkscreen."""
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
    assert labels[:8] == [f'SR-{n}' for n in range(1, 9)]
    assert labels[8:] == [f'SR-{n}' for n in range(1, 9)], (
        'the second box must read its own 1-8, not the card-wide 9-16')
    # The disambiguators: each box's resolved display name carries its
    # trunk letter, and each port says which local number it wears.
    assert [c['displayTitle'] for c in card['cvts']] == ['CVT10 A', 'CVT10 B']
    assert [p['localNumber'] for p in card['ports'][:16]] == \
        list(range(1, 9)) * 2


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


def test_a_new_card_stores_no_label_template(client):
    """The default template is a fallback, not a value. A card used to be
    stamped with '{name}-#' at birth, which put the app's own fallback into
    every saved file and drew it in the old panel's Label box as text nobody
    could tell from a choice - the same derived-as-value disease a port name
    box would have if it held the resolved label. Unset stores nothing,
    resolves to '' for the gear's Label box (value empty, placeholder
    doing the work),
    and still labels the ports off the default."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card = first_card(only(state))
    assert card['portLabelTemplate'] == ''

    stored = client.get('/api/project').get_json()['processors'][0]
    assert 'portLabelTemplate' not in stored['slots'][0]['card'], (
        'a fresh card carries the default template as if somebody typed it')

    # The fallback still does the labelling exactly as before.
    resp = client.put(f'/api/processors/{pid}/cards/{card["id"]}',
                      json={'name': 'SR'})
    named = first_card(only(resp.get_json()))
    assert named['ports'][0]['label'] == 'SR-1'


def test_clearing_the_label_template_leaves_nothing_behind(client):
    """Same clearing rule as a port name and the return template: blank is
    the absence of a template, the key comes out of the file, and the ladder
    reads exactly as it would had one never been typed."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'name': 'SR', 'portLabelTemplate': '{name}.P#'})
    assert first_card(only(resp.get_json()))['ports'][0]['label'] == 'SR.P1'

    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'portLabelTemplate': '  '})
    card = first_card(only(resp.get_json()))
    assert card['portLabelTemplate'] == ''
    assert card['ports'][0]['label'] == 'SR-1', (
        'a cleared template did not hand the ports back to the default')
    assert card['ports'][0]['labelSource'] == 'card'

    stored = client.get('/api/project').get_json()['processors'][0]
    assert 'portLabelTemplate' not in stored['slots'][0]['card'], (
        'a cleared template left something in the project')


def test_a_birth_stamped_default_template_reads_as_absent(client):
    """Every file saved before v0.11.2 carries '{name}-#' on every card,
    stamped at creation, never chosen. Resolving it as '' is what stops the
    panel showing it as typed text in an old project - and costs nothing,
    because a hand that really typed the default typed what the placeholder
    already promised."""
    state = add_processor(client, 'novastar-mx20')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    name_resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                           json={'name': 'SR'})
    assert name_resp.status_code == 200

    saved = client.get('/api/project').get_json()
    saved['processors'][0]['slots'][0]['card']['portLabelTemplate'] = '{name}-#'
    assert client.post('/api/project', json=saved).status_code == 200

    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['portLabelTemplate'] == '', (
        'the stamp every old file carries came back as a typed value')
    assert card['ports'][0]['label'] == 'SR-1'


def test_a_boxes_label_template_follows_the_same_doctrine(client):
    """The box in front of the card has the same Label box, so it has the
    same rules: nothing stored at birth, a typed template as the value, a
    blank deleting the key and handing the ports back to the default."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    resp = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                       json={'deviceId': 'novastar-cvt10', 'pair': False})
    assert resp.status_code == 201
    cvt = first_card(only(resp.get_json()))['cvts'][0]
    assert cvt['portLabelTemplate'] == ''
    stored = client.get('/api/project').get_json()['processors'][0]
    assert 'portLabelTemplate' not in stored['slots'][0]['card']['cvts'][0]

    url = f'/api/processors/{pid}/cvts/{cvt["id"]}'
    resp = client.put(url, json={'name': 'A', 'portLabelTemplate': '{name}.#'})
    box = first_card(only(resp.get_json()))['cvts'][0]
    assert box['portLabelTemplate'] == '{name}.#'
    assert box['ports'][0]['label'] == 'A.1'

    resp = client.put(url, json={'portLabelTemplate': ''})
    box = first_card(only(resp.get_json()))['cvts'][0]
    assert box['portLabelTemplate'] == ''
    assert box['ports'][0]['label'] == 'A-1', (
        'a cleared box template did not hand the ports back to the default')
    stored = client.get('/api/project').get_json()['processors'][0]
    assert 'portLabelTemplate' not in stored['slots'][0]['card']['cvts'][0], (
        'a cleared box template left something in the project')


def test_one_port_named_by_hand_outranks_the_whole_ladder(client):
    """A rank above the nearest named device upstream, and the only one that
    can be aimed at a single port. The ladder produces a whole card at a time,
    which is what makes naming a card enough to label a wall; what it cannot
    produce is the one port that is not like its neighbours. Since a screen's
    own override no longer reaches an assigned port, this is where that port is
    named. tests/test_processor_labels.py carries the rest of the rule."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-4xfiber')
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'SR'})
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    cvt_id = first_card(only(state))['cvts'][0]['id']
    client.put(f'/api/processors/{pid}/cvts/{cvt_id}', json={'name': 'CVT-A'})

    resp = client.put(f'/api/processors/{pid}/cards/{card_id}/ports/2',
                      json={'name': 'HOUSE-LEFT'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    card = first_card(only(resp.get_json()))
    assert [p['label'] for p in card['ports'][:3]] == \
        ['CVT-A-1', 'HOUSE-LEFT', 'CVT-A-3']
    assert card['ports'][1]['labelSource'] == 'manual'
    assert card['portNames'] == {'2': 'HOUSE-LEFT'}

    reread = first_card(only(client.get('/api/processors').get_json()))
    assert reread['ports'][1]['label'] == 'HOUSE-LEFT'


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
    assert 'trunk' in resp.get_json()['error']

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
    no change - including in the file they save. Reading the tree's endpoint
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


def test_the_dock_declares_its_controls_outside_every_tab_panel():
    """tests/test_all_fields_sweep.py drives every control declared inside a
    .tab-panel straight at the selected LAYER. The processor controls are
    PROJECT state, so their only static declarations - the add picker, the
    Add button and the attachment flag - live on the hardware dock's
    header bar, outside every tab panel, and everything deeper (names,
    templates, modes) is built at render time by app-dock/app-processors.
    A second declaration inside a panel would be swept and would fail for a
    reason that has nothing to do with it."""
    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()
    dock = html[html.index('id="hardware-dock"'):
                html.index('id="hardware-dock-body"')]
    for control in ('id="processor-add-device"', 'id="processor-add-btn"',
                    'id="hw-dock-flag"'):
        assert html.count(control) == 1, (
            f'{control} is declared more than once - the copy outside the '
            f'dock would be swept at the selected layer')
        assert control in dock, (
            f'{control} left the dock header - its one legitimate home')
    # The retired Signal panel hosts stay gone - and so does the retired
    # auto checkbox: a resurrected panel or switch would split the fields
    # between two surfaces again.
    for gone in ('id="processor-list"', '<h2>Processors</h2>',
                 '<h2>Port Numbering</h2>', 'id="port-assignment-auto"',
                 'id="hw-dock-auto-wrap"'):
        assert gone not in html, f'{gone} is back in the template'


# ── 7. The return end on the port row ─────────────────────────────────────
#
# A port row names both ends of its socket now: the primary, and the
# redundancy run that leaves it and comes back. The row lives in the dock
# chip's editor (app-dock.js) - the dock is the one place ports appear -
# and is rebuilt wholesale on every change, so what is pinned here is the
# machinery that keeps two fields usable there: stable focus keys, captions,
# and the wrap that stacks them where they no longer fit abreast.

JS_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')


def js_source(filename):
    with open(os.path.join(JS_DIR, filename), encoding='utf-8') as fh:
        return fh.read()


def test_the_port_row_offers_the_return_end_beside_the_primary():
    """Both fields, each with its own stable focus key (the dock is rebuilt
    under the user's fingers), each captioned (two unlabeled boxes holding
    different ends of the same cable read as noise), sharing a line that
    wraps rather than a grid that overflows a squeezed chip."""
    source = js_source('app-dock.js')
    assert 'processor-port-name-${card.id}-${port.number}' in source
    assert 'processor-port-return-${card.id}-${port.number}' in source
    assert '(card.returnPortNames || {})[String(port.number)]' in source
    assert 'port.returnLabel' in source, (
        'the return placeholder is not the resolved return label')
    body = source[source.index('_buildPortRow(proc, card, port) {'):]
    body = body[:body.index('\n    }')]
    assert "names.style.flexWrap = 'wrap';" in body, (
        'the name fields do not wrap where the chip squeezes them')
    assert "{ returnName: val }" in body
    # The commit goes through the same PUT the primary uses - one route, one
    # rule about what a port-name edit is.
    assert body.count('/ports/${port.number}') == 1


def test_processor_edits_take_post_mutation_history_snapshots():
    """The undo contract: a processor edit lands in history AFTER the server
    answers and the new tree is folded into this.project - the post-mutation
    snapshot every other action takes - and a refused edit takes none. Both
    ends of a port enter history under their own names, identically - the
    port actions living in the dock module now, through the same
    _processorRequest. The ACTIONS live where their drivers live: the
    inline renames and the header's Add on the dock (app-dock.js), the
    gear popovers' remove in the content builders (app-processors.js)."""
    source = js_source('app-processors.js')
    assert 'if (applied && action) this.saveState(action);' in source
    assert "'Remove Processor'" in source, (
        "'Remove Processor' takes no history snapshot")
    dock = js_source('app-dock.js')
    for action in ("'Add Processor'", "'Rename Processor'",
                   "'Rename Card'", "'Rename Processor Port'",
                   "'Rename Processor Port Return'"):
        assert action in dock, f'{action} takes no history snapshot'


# ── 8. The row in a real browser, at both widths ──────────────────────────

# The browser section asserts against the layer the e2e server seeds at ITS
# first boot - a screen literally named Screen1. But when an earlier browser
# module already started that server, this module's own Flask-client tests
# have reset app_module.current_project by the time panel_page opens, and the
# served project holds TestScreen or nothing. So the fixture rebuilds the
# project it asserts against through the real endpoints - the RESET_JS idiom
# test_data_sidebar.py documents - rather than trusting boot order.
RESET_LAYERS_JS = """async () => {
    const project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Screen1', columns: 4, rows: 3,
                               cabinet_width: 128, cabinet_height: 128 }),
    });
    window.app.project = await (await fetch('/api/project')).json();
    const screen = window.app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    // The module's stock machine is a COEX MX20, and since the platform
    // wall (2026-08-28) a screen only lands on gear its Processing setting
    // matches - left unset, selecting it below would stamp the prefs
    // default (Legacy) onto it and its ports would have nowhere to land.
    screen.processorType = 'novastar-coex-1g';
    await fetch(`/api/layer/${screen.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ processorType: 'novastar-coex-1g' }),
    });
    window.app.currentLayer = screen;
    window.app.selectedLayerIds = new Set([screen.id]);
    window.app.lastSelectedLayerId = screen.id;
    window.app.renderLayers();
    window.app.loadLayerToInputs(screen);
    window.app.updatePortCapacityDisplay();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return screen.id;
}"""


RESET_PROCESSORS_JS = """async () => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of (state.processors || [])) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const add = await (await fetch('/api/processors', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'novastar-mx20' }),
    })).json();
    const proc = add.resolved[0];
    const card = proc.slots.map(s => s.card).find(Boolean);
    await fetch(`/api/processors/${proc.id}/cards/${card.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'SR' }),
    });
    await window.app.refreshProcessors();
    // Bracket the seed in history the way live edits are bracketed, so the
    // undo test steps back to "processor present, port unnamed" rather than
    // to a project from before the processor existed.
    window.app.saveState('Seed Processors');
    return { procId: proc.id, cardId: card.id };
}"""

# A gear popover's fields only exist while the popover is open, so a driver
# aiming at one opens the gear first - through the gear button itself, the
# way a user does. Clicking the SAME gear again would toggle it closed, so
# openers check the popover actually came up.
OPEN_GEAR_JS = """(popId) => {
    const gear = document.querySelector(`[data-hwpop="${popId}"]`);
    if (!gear) return false;
    const pop = document.getElementById('hw-gear-popover');
    const open = !!(pop && pop.style.display !== 'none'
        && window.app._hwPopover && window.app._hwPopover.id === popId);
    if (!open) gear.click();
    const after = document.getElementById('hw-gear-popover');
    return !!(after && after.style.display !== 'none');
}"""

# The ports render as dock chips and a port's editor only shows while its
# chip is open, so a driver that measures or types into the editor first
# opens the chip the way a user does - through its face.
OPEN_TILE_JS = """(tileId) => {
    const tile = document.querySelector(`[data-lrd-tile="${tileId}"]`);
    if (!tile) return false;
    if (!tile.classList.contains('lrd-tile-open')) {
        tile.querySelector(':scope > .lrd-tile-face').click();
    }
    return tile.classList.contains('lrd-tile-open');
}"""

MEASURE_ROW_JS = """(args) => {
    const body = document.getElementById('hardware-dock-body');
    const field = (kind) => document.querySelector(
        `[data-lrd-field="processor-port-${kind}-${args.cardId}-1"]`);
    const name = field('name');
    const ret = field('return');
    const vis = (el) => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    const limit = body.getBoundingClientRect().right;
    const inside = (el) => !!el
        && el.getBoundingClientRect().right <= limit + 0.5;
    return {
        nameVisible: vis(name),
        returnVisible: vis(ret),
        nameInside: inside(name),
        returnInside: inside(ret),
        namePlaceholder: name ? name.placeholder : null,
        returnPlaceholder: ret ? ret.placeholder : null,
        listClipped: body.scrollWidth > body.clientWidth,
    };
}"""


@pytest.fixture(scope="module")
def panel_page(e2e_server, pw_browser, server_project_guard):
    # server_project_guard: these tests seed processors into the SHARED live
    # server; the guard hands the project back the way the module found it
    # (see tests/conftest.py).
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    assert pg.evaluate(RESET_LAYERS_JS), "test project was not created"
    pg.wait_for_timeout(600)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    yield pg
    context.close()


@pytest.mark.parametrize('width', [1280, 860])
def test_the_port_row_renders_both_fields(panel_page, width):
    """In the dock chip's open editor, at the usual window and a squeezed
    one: both boxes in layout, both placeholders carrying the RESOLVED
    label for their own end (SR-1 out, SR-1R back), both inside the tray's
    right edge, and the tray not scrolling sideways - scrollWidth over
    clientWidth is exactly the overflow the reflow rule forbids. The dock's
    issue strip is measured by its own test further down."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = panel_page.evaluate(RESET_PROCESSORS_JS)
    panel_page.wait_for_timeout(600)
    panel_page.set_viewport_size({'width': width, 'height': 720})
    panel_page.wait_for_timeout(400)
    try:
        assert panel_page.evaluate(OPEN_TILE_JS, f"port-{ids['cardId']}-1"), (
            'port 1 has no chip to open')
        panel_page.wait_for_timeout(100)
        out = panel_page.evaluate(MEASURE_ROW_JS,
                                  {'cardId': ids['cardId'], 'width': width})
        assert out['nameVisible'] and out['returnVisible'], out
        assert out['nameInside'] and out['returnInside'], out
        assert out['namePlaceholder'] == 'SR-1', out
        assert out['returnPlaceholder'] == 'SR-1R', out
        assert not out['listClipped'], 'the dock body scrolls sideways'
    finally:
        # leave the chip closed for the next test - CLOSE, not toggle-open
        panel_page.evaluate("""(tid) => {
            const tile = document.querySelector(`[data-lrd-tile="${tid}"]`);
            if (tile && tile.classList.contains('lrd-tile-open')) {
                window.app._setTileOpen(tile, false);
            }
        }""", f"port-{ids['cardId']}-1")
        panel_page.set_viewport_size({'width': 1280, 'height': 720})
        panel_page.wait_for_timeout(300)


def test_renaming_either_end_round_trips_through_undo(panel_page):
    """The full circle, driven through the real input: the edit lands on the
    server, earns its own named history entry, and undo/redo walk it back and
    forward one end at a time - the return undone while the primary stands."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = panel_page.evaluate(RESET_PROCESSORS_JS)
    panel_page.wait_for_timeout(600)

    def commit(kind, value):
        panel_page.evaluate("""(args) => {
            const input = document.querySelector(
                `[data-lrd-field="processor-port-${args.kind}-${args.cardId}-1"]`);
            input.value = args.value;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }""", {'kind': kind, 'cardId': ids['cardId'], 'value': value})
        panel_page.wait_for_timeout(800)

    def stored():
        state = panel_page.evaluate(
            "async () => await (await fetch('/api/processors')).json()")
        card = next(c['card'] for c in state['processors'][0]['slots']
                    if c.get('card'))
        return (card.get('portNames') or {}).get('1'), \
               (card.get('returnPortNames') or {}).get('1')

    commit('name', 'HL')
    commit('return', 'BU-1')
    assert stored() == ('HL', 'BU-1')
    actions = panel_page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-2)")
    assert actions == ['Rename Processor Port', 'Rename Processor Port Return']

    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', None), 'undo took the primary with the return'

    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == (None, None)

    panel_page.evaluate("() => window.app.redo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', None)

    panel_page.evaluate("() => window.app.redo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', 'BU-1')

    # CLEARING IS AN EDIT LIKE ANY OTHER. Emptying the box is the one way
    # back from a typed name to the derived label, so it takes its own named
    # step: undo brings the name back, redo clears it again. This is the
    # gesture "reset this port" actually is, and it must round-trip or the
    # only path back to derived is the one path history cannot walk.
    commit('name', '')
    assert stored() == (None, 'BU-1')
    actions = panel_page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-1)")
    assert actions == ['Rename Processor Port']

    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('HL', 'BU-1'), 'undo did not bring the name back'

    panel_page.evaluate("() => window.app.redo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == (None, 'BU-1'), 'redo did not re-clear the name'


# ── 9. The generic device is a breakout box ───────────────────────────────
#
# CVT is NovaStar's name for THEIR breakout box, the way Tessera XD is
# Brompton's. Actual devices keep their model names; every generic surface -
# the add control, helper text, error messages - says breakout box, and the
# shared trunk messages name no vendor's silkscreen ("OPT" is NovaStar's).

def test_the_add_control_offers_a_breakout_box_not_a_cvt():
    source = js_source('app-processors.js')
    assert "'Add a breakout box...'" in source
    assert 'Add a CVT' not in source, (
        'the generic add control wears one vendor\'s product name')
    for action in ("'Add Breakout Box'", "'Remove Breakout Box'",
                   "'Edit Breakout Box Label Template'"):
        assert action in source, f'{action} missing from the history actions'
    # The rename is the dock header's inline field now, so its action lives
    # with its driver - still the generic device, never the vendor's.
    assert "'Rename Breakout Box'" in js_source('app-dock.js'), (
        "'Rename Breakout Box' missing from the dock's history actions")
    assert "'Add CVT'" not in source and "'Rename CVT'" not in source


def test_the_shared_trunk_messages_name_no_vendors_silkscreen():
    """The refusals and the trunk summaries print for every vendor's cards,
    so they say trunks; OPT survives only where it IS the silkscreen - in
    NovaStar device notes and NovaStar-specific explanations."""
    source = js_source('app-processors.js')
    assert 'OPTs are used' not in source and 'OPT left' not in source
    assert 'OPTs in' not in source
    # The server's refusals are the same surface.
    _ok, why = catalog.can_add_cvt(
        {'deviceId': 'brompton-sx40', 'cvts': [
            {'deviceId': 'brompton-xd'} for _ in range(4)]},
        'brompton-xd')
    assert not re.search(r'\bOPTs?\b', why), why
    assert 'trunks' in why


def test_the_dock_markup_says_box_generically():
    """The dock's static markup - the tray's tooltip and its header bar -
    is the generic surface now, so it speaks of boxes and never wears one
    vendor's product name."""
    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()
    assert 'CVT breakout boxes' not in html
    dock = html[html.index('id="hardware-dock"'):
                html.index('id="hardware-dock-body"')]
    assert 'CVT' not in dock, (
        'the dock\'s generic markup wears one vendor\'s product name')
    assert 'box' in dock, (
        'the dock\'s tooltip no longer mentions the boxes it holds')


# ── 10. Redundancy pairing, per vendor, no extrapolation ──────────────────
#
# Three vendors, three answers, each exactly as documented and no further:
#
# * BROMPTON (SX40, SQ200, and its breakout boxes): fixed adjacent pairs -
#   "A back up to B, C back up to D automatically; that is the only way it
#   works" - stated as a fact, wired port-to-port at box granularity (main
#   socket n returns on n + 10 in the paired box), never editable.
# * NOVASTAR: a primary box and a backup box is the DEFAULT when a card's
#   mode has trunks backing trunks - created as a pair, freely overridden.
# * MEGAPIXEL: nothing. No rule is documented, so no default is invented -
#   not even in the safe-looking direction.

def test_brompton_redundancy_states_its_fixed_pairing(client):
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    assert only(state)['redundancyPairing'] is None, (
        'a pairing was claimed with redundancy off')
    resp = client.put(f'/api/processors/{pid}', json={'redundancy': True})
    proc = only(resp.get_json())
    pairing = proc['redundancyPairing']
    assert pairing['fixed'] is True
    assert pairing['scheme'] == 'adjacent'
    assert pairing['pairs'] == [{'primary': 'A', 'backup': 'B'},
                                {'primary': 'C', 'backup': 'D'}]
    assert 'A backs up to B' in pairing['statement']
    assert 'C backs up to D' in pairing['statement']
    # The resolved card carries it too, for the box rows underneath.
    assert first_card(proc)['redundancyPairing']['scheme'] == 'adjacent'


def test_brompton_pairing_is_a_fact_not_a_field(client):
    """Derived on every resolve and stored nowhere, so there is nothing to
    edit: a PUT aiming at it is dropped by the allow-list and the answer
    afterwards is the same answer."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{pid}', json={
        'redundancyPairing': {'scheme': 'free-for-all', 'fixed': False}})
    proc = only(resp.get_json())
    assert proc['redundancyPairing']['scheme'] == 'adjacent'
    assert proc['redundancyPairing']['fixed'] is True
    raw = resp.get_json()['processors'][0]
    assert 'redundancyPairing' not in raw, (
        'the pairing leaked into stored state, where an edit could reach it')


def test_the_sx40_arrives_stocked_with_10_port_xd_boxes(client):
    """The ruling, verbatim (2026-08-25): "The sx40 by default has to use 10
    port breakout boxes." The SX40 has no fixture ports of its own, so a
    fresh one arrives the way it leaves the shop: four 10-port XDs, one per
    trunk, sockets 1-10 / 11-20 / 21-30 / 31-40. A default and nothing more
    - each box deletes like any box - and the 12-port XD-S/XD-T stay
    selectable in its place, still delivering only their first 10 behind
    this device (the trunk cap), so 10 per box is the shape either way."""
    state = add_processor(client, 'brompton-sx40')
    card = first_card(only(state))
    assert [c['deviceId'] for c in card['cvts']] == ['brompton-xd'] * 4
    assert [c['portCount'] for c in card['cvts']] == [10, 10, 10, 10]
    assert [c['firstPort'] for c in card['cvts']] == [1, 11, 21, 31]
    assert card['trunksFree'] == 0
    assert card['ceiling'] == 40 and card['delivered'] == 40
    # Deleting a stocked box and hanging an XD-S on the freed trunk still
    # lands at 10 ports: the sheets allow the box, not a bigger count.
    pid = only(state)['id']
    gone = card['cvts'][3]['id']
    client.delete(f'/api/processors/{pid}/cvts/{gone}')
    state = client.post(
        f'/api/processors/{pid}/cards/{card["id"]}/cvts',
        json={'deviceId': 'brompton-xd-s'}).get_json()
    swapped = first_card(only(state))['cvts'][3]
    assert (swapped['deviceId'], swapped['portCount']) == ('brompton-xd-s', 10)


def test_a_pre_stocking_save_gets_its_default_boxes_back_on_load(client):
    """Projects saved before new_processor stocked the defaults carry an
    SX40 with an empty cvts list. That is never a state anyone chose - the
    device has no fixture ports of its own, so a boxless SX40 drives
    nothing (the 2026-08-25 ruling again: "The sx40 by default has to use
    10 port breakout boxes"). Loading such a file restocks the fixed card
    with exactly what a fresh add gets: four XDs, one per trunk A-D."""
    add_processor(client, 'brompton-sx40')
    saved = client.get('/api/project').get_json()
    saved['processors'][0]['slots'][0]['card']['cvts'] = []
    assert client.put('/api/project', json=saved).status_code == 200

    card = first_card(only(client.get('/api/processors').get_json()))
    assert [c['deviceId'] for c in card['cvts']] == ['brompton-xd'] * 4
    assert [c['trunkLetter'] for c in card['cvts']] == ['A', 'B', 'C', 'D']
    assert [c['firstPort'] for c in card['cvts']] == [1, 11, 21, 31]
    assert card['ceiling'] == 40 and card['delivered'] == 40
    # The heal reached STORED state, not just the resolved answer: the next
    # save writes a stocked file, and this file never heals again.
    stored = client.get('/api/project').get_json()['processors'][0]
    assert len(stored['slots'][0]['card']['cvts']) == 4


def test_a_card_with_even_one_box_is_somebodys_arrangement(client):
    """The heal is exactly as narrow as the birth rule: one box on the card
    means somebody arranged it, and a reload hands back precisely what was
    saved - no topping up to four."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    card = first_card(only(state))
    for box in card['cvts'][1:]:
        client.delete(f'/api/processors/{pid}/cvts/{box["id"]}')
    kept = card['cvts'][0]['id']

    saved = client.get('/api/project').get_json()
    assert client.put('/api/project', json=saved).status_code == 200
    cvts = first_card(only(client.get('/api/processors').get_json()))['cvts']
    assert [c['id'] for c in cvts] == [kept]


def test_a_device_with_no_documented_default_gains_nothing_on_load(client):
    """The HELIOS 8K needs distribution too, but no default box is
    documented for it - and an invented one is still invented on the load
    path. Its empty card is its normal state, before and after."""
    add_processor(client, 'megapixel-helios-8k')
    saved = client.get('/api/project').get_json()
    assert saved['processors'][0]['slots'][0]['card']['cvts'] == []
    assert client.put('/api/project', json=saved).status_code == 200
    assert first_card(only(client.get('/api/processors').get_json()))['cvts'] \
        == []
    stored = client.get('/api/project').get_json()['processors'][0]
    assert stored['slots'][0]['card']['cvts'] == []


def test_healed_ids_never_land_on_ids_the_file_already_holds(client):
    """A legacy file can carry other boxes AND a counter that trails the
    ids in it (or lost it outright, as here). Restocked ids must dodge
    every id already in the tree - a reused id would land edits on the
    wrong box."""
    add_processor(client, 'brompton-sx40')  # keeps its cvt1f0..cvt1f3
    add_processor(client, 'brompton-sx40')  # stripped below
    saved = client.get('/api/project').get_json()
    saved['processors'][1]['slots'][0]['card']['cvts'] = []
    saved.pop('next_processor_seq', None)
    assert client.put('/api/project', json=saved).status_code == 200

    stored = client.get('/api/project').get_json()['processors']
    ids = [c['id'] for proc in stored for slot in proc['slots']
           for c in slot['card']['cvts']]
    assert len(ids) == 8, 'the stripped SX40 was not restocked'
    assert len(set(ids)) == 8, f'an id was minted twice: {sorted(ids)}'
    resolved = client.get('/api/processors').get_json()['resolved']
    assert all(first_card(p)['delivered'] == 40 for p in resolved)


def test_the_heal_runs_at_the_project_funnel_never_on_a_read(client):
    """Deleting every box in one session is an edit in progress - mid-swap
    to a different box type, say - and a GET must not restock behind it.
    The heal lives only where a whole project enters server state."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    for box in first_card(only(state))['cvts']:
        client.delete(f'/api/processors/{pid}/cvts/{box["id"]}')
    assert first_card(only(client.get('/api/processors').get_json()))['cvts'] \
        == []
    stored = client.get('/api/project').get_json()['processors'][0]
    assert stored['slots'][0]['card']['cvts'] == [], (
        'a read restocked the card mid-edit')


def test_redundancy_on_no_longer_limits_the_sx40_to_20_renumbered_primaries(
        client):
    """The reported defect (2026-08-25): "setting redundancy on limits to 20
    primaries but it should be 10 per box." The old model halved the ceiling
    to 20 and renumbered - box C read sockets 11-20 instead of its own
    21-30, box D repeated them, and sockets 21-40 left the drawing, so a
    tech patching socket 21 could not find socket 21. Redundancy is a
    patching plan, never a renumbering: all 40 sockets stay, what halves is
    what is USABLE - 20, ten per primary box."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    state = client.put(f'/api/processors/{pid}',
                       json={'redundancy': True}).get_json()
    proc = only(state)
    card = first_card(proc)
    assert proc['ceiling'] == 40 and card['ceiling'] == 40
    assert [p['number'] for p in card['ports']] == list(range(1, 41))
    assert [c['firstPort'] for c in card['cvts']] == [1, 11, 21, 31], (
        'a box was renumbered off its own sockets')
    assert all(c['duplicateOf'] is None for c in card['cvts']), (
        'a backup box was drawn as a second delivery of its primary\'s ports')
    assert card['redundancyShape'] == {'mode': 'sequential', 'forced': True,
                                       'level': 'trunk', 'usable': 20}


def test_brompton_boxes_pair_adjacent_and_the_pairing_is_enforced(client):
    """The four XDs on a redundant SX40 pair as WHOLE boxes, adjacent - A
    backs up to B, C backs up to D - so the primaries are boxes A (sockets
    1-10) and C (21-30) and each main returns on the same socket of the box
    beside it: 1 on 11, 10 on 20, 21 on 31, 30 on 40. Interleaving them -
    the NovaStar shape - would pair A with C, which is not how Brompton
    runs. Redundancy off, the same four boxes are four plain blocks with no
    roles at all."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    state = client.put(f'/api/processors/{pid}',
                       json={'redundancy': True}).get_json()
    card = first_card(only(state))
    a, b, c, d = card['cvts']
    assert [v['backupOf'] for v in (a, b, c, d)] == [
        None, a['id'], None, c['id']]
    ports = {p['number']: p for p in card['ports']}
    for main in list(range(1, 11)) + list(range(21, 31)):
        assert ports[main]['backedBy']['port'] == main + 10, ports[main]
        assert ports[main + 10]['backsUp']['port'] == main, ports[main + 10]
        # The 1:1 mirror in the numbers a hand can find (2026-08-27: "B is
        # 1-10 and D is 1-10"): A-n returns on B's OWN socket n, so both
        # ends of every link wear the same local number, and the link names
        # the box that number counts on.
        local = (main - 1) % 10 + 1
        assert ports[main]['backedBy']['localPort'] == local, ports[main]
        assert ports[main + 10]['backsUp']['localPort'] == local, \
            ports[main + 10]
    assert [ports[n]['backedBy']['boxTitle'] for n in (1, 21)] == \
        ['Tessera XD B', 'Tessera XD D']
    assert not any(ports[n].get('backedBy') for n in range(11, 21)), (
        'a backing socket was given a backup of its own')
    # The four faces as drawn: every box is 1-10 on its own silkscreen.
    assert all([p['localNumber'] for p in box['ports']] == list(range(1, 11))
               for box in card['cvts'])

    state = client.put(f'/api/processors/{pid}',
                       json={'redundancy': False}).get_json()
    card = first_card(only(state))
    assert [v['firstPort'] for v in card['cvts']] == [1, 11, 21, 31]
    assert all(v['backupOf'] is None for v in card['cvts'])
    assert not any(p.get('backedBy') or p.get('backsUp')
                   for p in card['ports'])


def test_brompton_return_labels_resolve_to_the_backing_boxs_own_sockets(
        client):
    """Name the boxes what the truck calls them and the loom reads itself:
    main A-1 returns on B-1 because socket 11 IS box B's first socket - the
    mapped socket's own label, through the same ladder every mapping uses,
    so a name typed on one return end still wins over it."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    card = first_card(only(state))
    for box, name in zip(card['cvts'], ('A', 'B', 'C', 'D')):
        client.put(f'/api/processors/{pid}/cvts/{box["id"]}',
                   json={'name': name})
    state = client.put(f'/api/processors/{pid}',
                       json={'redundancy': True}).get_json()
    ports = {p['number']: p for p in first_card(only(state))['ports']}
    assert (ports[1]['label'], ports[1]['returnLabel']) == ('A-1', 'B-1')
    assert (ports[10]['label'], ports[10]['returnLabel']) == ('A-10', 'B-10')
    assert (ports[21]['label'], ports[21]['returnLabel']) == ('C-1', 'D-1')
    assert (ports[30]['label'], ports[30]['returnLabel']) == ('C-10', 'D-10')
    # The backing sockets' own primary labels count on their own faces too
    # (2026-08-27: "B is 1-10 and D is 1-10") - B's first socket is B-1,
    # never B-11.
    assert ports[11]['label'] == 'B-1' and ports[31]['label'] == 'D-1'
    assert all(ports[n]['returnLabelSource'] == 'backup'
               for n in (1, 10, 21, 30))
    # A typed return name still beats the mapping - the ladder is untouched.
    resp = client.put(f'/api/processors/{pid}/cards/{card["id"]}/ports/1',
                      json={'returnName': 'SPARE-1'})
    ports = {p['number']: p for p in first_card(only(resp.get_json()))['ports']}
    assert (ports[1]['returnLabel'], ports[1]['returnLabelSource']) == \
        ('SPARE-1', 'manual')
    assert ports[2]['returnLabel'] == 'B-2'


def test_brompton_adds_one_box_per_add(client):
    """The enforcement is the SHAPE, not extra units: Brompton gets no
    auto-created backup box - a box added onto the second trunk of a pair
    IS the backup, because adjacent pairing leaves it nothing else to be.
    Two trunks are freed here so there is room to see exactly one arrive."""
    state = add_processor(client, 'brompton-sx40')
    pid = only(state)['id']
    card = first_card(only(state))
    for box in card['cvts'][2:]:
        client.delete(f'/api/processors/{pid}/cvts/{box["id"]}')
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    state = client.post(f'/api/processors/{pid}/cards/{card["id"]}/cvts',
                        json={'deviceId': 'brompton-xd'}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 3
    raw = state['processors'][0]['slots'][0]['card']
    assert all('backupOf' not in v for v in raw['cvts']), (
        'a pairing fact leaked into stored state')


def test_the_sq200_states_the_rule_without_lettering_unknown_outputs(client):
    """The SQ200 pairs the same fixed way - the user's rule names it - while
    its output count stays unpublished. So the statement states the rule and
    the pairs list stays empty: lettering outputs nobody has counted would be
    a guessed ceiling wearing a different hat."""
    state = add_processor(client, 'brompton-sq200')
    proc = only(state)
    assert proc['redundancySupported'] is True
    pid = proc['id']
    resp = client.put(f'/api/processors/{pid}', json={'redundancy': True})
    proc = only(resp.get_json())
    assert proc['redundancyPairing']['fixed'] is True
    assert proc['redundancyPairing']['pairs'] == []
    assert 'A to B' in proc['redundancyPairing']['statement']
    assert proc['ceilingKnown'] is False, 'the pairing invented a count'


def test_the_s8_pairs_fixed_adjacent_ports_by_the_2026_08_23_ruling(client):
    """The second pairing rule arrived by name (2026-08-23): the SX40 "does
    A to B and C to D on one sx40", "and S8 does 1to2 and so on". Port-level
    this time - the S8 has no trunks to letter, its eight RJ45s pair
    directly - so the statement numbers the ports, the even ports resolve as
    the odd ones' returns, and the ceiling stays 8: port 2 still EXISTS, it
    is the socket main 1's return loom lands on, and a tech patching it
    needs it on the drawing. Usable is what halves."""
    state = add_processor(client, 'brompton-s8')
    pid = only(state)['id']
    resp = client.put(f'/api/processors/{pid}', json={'redundancy': True})
    proc = only(resp.get_json())
    pairing = proc['redundancyPairing']
    assert pairing['fixed'] is True
    assert pairing['pairs'] == [{'primary': '1', 'backup': '2'},
                                {'primary': '3', 'backup': '4'},
                                {'primary': '5', 'backup': '6'},
                                {'primary': '7', 'backup': '8'}]
    assert '1 backs up to 2' in pairing['statement']
    assert proc['ceiling'] == 8
    card = first_card(proc)
    assert card['redundancyShape'] == {'mode': 'sequential', 'forced': True,
                                       'level': 'port', 'usable': 4}
    evens = [p for p in card['ports'] if p['number'] % 2 == 0]
    assert [p['backsUp']['port'] for p in evens] == [1, 3, 5, 7]
    # Fixed means fixed: the mode select's PUT is refused, not stored.
    card_id = card['id']
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'redundancyMode': 'manual'})
    assert resp.status_code == 400
    assert 'fact of the device' in resp.get_json()['error']


def test_the_s4_and_m2_stay_unruled_and_present_the_modes(client):
    """The ruling named the S8 only - "and so on" is the port sequence
    1 to 2, 3 to 4, not the rest of the range - so the S4 and M2 still claim
    no pairing shape, and under the data modes an unforced device presents
    the mode select: 1:1 by default, which consumes a BACKUP unit and halves
    nothing on the main. The documented halving still holds where the
    on-unit loop is chosen: sequential leaves 2 of 4 usable."""
    for device_id in ('brompton-s4', 'brompton-m2'):
        state = add_processor(client, device_id)
        proc = state['resolved'][-1]
        pid = proc['id']
        resp = client.put(f'/api/processors/{pid}', json={'redundancy': True})
        proc = next(p for p in resp.get_json()['resolved'] if p['id'] == pid)
        assert proc['redundancyPairing'] is None, device_id
        card = first_card(proc)
        assert card['redundancyShape']['mode'] == '1to1', device_id
        assert card['redundancyShape']['forced'] is False, device_id
        assert card['ceiling'] == 4, (
            f'{device_id}: 1:1 halved the main - the backup unit is what it '
            f'consumes')
        resp = client.put(f'/api/processors/{pid}/cards/{card["id"]}',
                          json={'redundancyMode': 'sequential'})
        card = first_card(next(p for p in resp.get_json()['resolved']
                               if p['id'] == pid))
        assert card['redundancyShape']['usable'] == 2, device_id


def test_a_novastar_box_in_redundancy_defaults_to_a_pair(client):
    """H_4xfiber in copy/backup and one add: a primary box and a backup box,
    the backup on the trunk that duplicates the primary's (OPT 3 backing
    OPT 1), so the pair really is one set of ports twice - primary box in a
    backup box, unit to unit."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': 'copy-backup'})
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 2, 'the default did not create the pair'
    primary, backup = card['cvts']
    assert backup['backupOf'] == primary['id']
    assert primary['backupOf'] is None
    assert (primary['trunkIndex'], backup['trunkIndex']) == (0, 2)
    assert (primary['firstPort'], backup['firstPort']) == (1, 1)
    assert backup['duplicateOf'] == primary['id']
    # And the link is stored state: it survives a save/reload round trip.
    saved = client.get('/api/project').get_json()
    assert client.put('/api/project', json=saved).status_code == 200
    card = first_card(only(client.get('/api/processors').get_json()))
    assert card['cvts'][1]['backupOf'] == card['cvts'][0]['id']


def test_the_mx40_pro_pairs_only_in_its_copy_mode(client):
    """The same all-in-one is both cases: in 20-port mode OPT 3/4 copy
    OPT 1/2, so a box arrives as a pair; in 40-port mode every trunk is its
    own block and an add is one box."""
    state = add_processor(client, 'novastar-mx40-pro')
    pid = only(state)['id']
    card_id = first_card(only(state))['id']
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    assert len(first_card(only(state))['cvts']) == 1, (
        'a pair was created outside any redundancy mode')

    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': '20-port'})
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    boxes = card['cvts']
    assert len(boxes) == 3
    assert boxes[2]['backupOf'] == boxes[1]['id']


def test_the_novastar_pair_is_freely_overridable(client):
    """"That doesn't mean that you have to do it that way": decline the pair
    up front with pair: false, or delete the backup box afterwards and the
    primary stands alone. Deleting the PRIMARY frees the backup to be a plain
    box - no dangling link survives."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': 'copy-backup'})
    # Declined up front.
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10',
                              'pair': False}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 1 and card['cvts'][0]['backupOf'] is None
    # Taken, then undone by deleting the backup.
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 3
    backup_id = card['cvts'][2]['id']
    state = client.delete(
        f'/api/processors/{pid}/cvts/{backup_id}').get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 2
    assert all(c['backupOf'] is None for c in card['cvts'])
    # Rebuilt, then the PRIMARY deleted: the backup link goes with it.
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    primary_id = card['cvts'][2]['id']
    assert card['cvts'][3]['backupOf'] == primary_id
    state = client.delete(
        f'/api/processors/{pid}/cvts/{primary_id}').get_json()
    card = first_card(only(state))
    assert all(c['backupOf'] is None for c in card['cvts']), (
        'a backup still points at a deleted primary')


def test_a_pair_that_does_not_fit_degrades_to_one_box(client):
    """Three trunks already spoken for on a copy/backup card: the add still
    lands, as one box - a pair that will not fit is not a reason to refuse
    the primary."""
    pid, card_id = with_card(client, 'novastar-h9', 'novastar-card-h-4xfiber')
    client.put(f'/api/processors/{pid}/cards/{card_id}',
               json={'mode': 'copy-backup'})
    add_boxes(client, pid, card_id, 3)
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 4
    assert card['cvts'][3]['backupOf'] is None
    assert card['trunksUsed'] == 4


def test_a_copy_own_ports_card_gets_no_pair(client):
    """The H_16xRJ45+2xfiber's trunks copy its own copper - a box there is
    another place to plug into ports the card already delivers, not a backup
    unit, so no pair is created."""
    pid, card_id = with_card(client, 'novastar-h9',
                             'novastar-card-h-16xrj45-2xfiber')
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'novastar-cvt10'}).get_json()
    assert len(first_card(only(state))['cvts']) == 1


def test_megapixel_gets_no_default_and_no_claimed_pairing(client):
    """"I'm not sure about how megapixel works" is an instruction: no
    pairing statement, no auto-created backup unit, no device rule invented.
    The redundancy TOGGLE does appear now - with the data modes it stopped
    being a claim about the device and became a plan for the loom (any unit
    can be mirrored 1:1 by a second unit) - but everything vendor-documented
    stays absent, and that absence is asserted so nobody fills it in as a
    tidy-up. Only an explicit "supported: false" (the T1) keeps the toggle
    away."""
    assert 'redundancy' not in catalog.get_device('megapixel-helios-8k')
    assert catalog.default_backup_pair(
        {'deviceId': 'megapixel-helios-8k'}) is False
    state = add_processor(client, 'megapixel-helios-8k')
    proc = only(state)
    assert proc['redundancySupported'] is True, (
        'the loom-level toggle should reach every device not documented '
        'unable')
    assert proc['redundancyPairing'] is None
    pid = proc['id']
    card_id = first_card(proc)['id']
    state = client.post(f'/api/processors/{pid}/cards/{card_id}/cvts',
                        json={'deviceId': 'megapixel-rs12'}).get_json()
    card = first_card(only(state))
    assert len(card['cvts']) == 1, 'a pair was invented for Megapixel'
    assert card['cvts'][0]['backupOf'] is None
    assert card['redundancyPairing'] is None


def test_the_gear_states_the_pairing_and_offers_no_control_for_it():
    """The pairing renders as text under the redundancy switch inside the
    processor's gear popover - the server's statement, verbatim - and as a
    'backs up X' line in the backup box's gear. No select, no input, no
    lrd-field: a fact, not a setting."""
    source = js_source('app-processors.js')
    assert 'proc.redundancyPairing' in source
    assert 'pairing.statement' in source or \
        'redundancyPairing.statement' in source
    assert 'backs up ${who}' in source
    # The statement lives in the PROCESSOR gear's content, under the switch.
    assert source.index('_buildProcGearContent') \
        < source.index('redundancyPairing') \
        < source.index('_buildCardGearContent'), (
        'the pairing statement left the processor gear popover')
    section = source[source.index('redundancyPairing'):]
    head = section[:section.index('_buildCardGearContent')]
    assert 'lrdField' not in head.split('appendChild(fact)')[0].rsplit(
        'const fact', 1)[-1], 'the pairing fact grew a focus key - a control'


# ── 11. The ports live on the dock; its body is their scroll context ──────

def test_the_processors_module_builds_no_port_grid():
    """The dock is the one place ports appear, so the processors module
    (which owns the state side and the gear popovers' content) builds no
    port list, no port tile and no port field - a second grid would be the
    same data twice, and it must not quietly come back and split the focus
    keys between two surfaces."""
    source = js_source('app-processors.js')
    for gone in ('_buildPortList', '_buildPortTile', '_buildPortRow',
                 'processor-port-name-', 'processor-port-return-',
                 'processor-port-backup-'):
        assert gone not in source, (
            f'{gone!r} is back in the processors module - ports belong to '
            f'the dock now')


PORT_LIST_SEED_JS = """async () => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of (state.processors || [])) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const add = await (await fetch('/api/processors', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'novastar-h9' }),
    })).json();
    const proc = add.resolved[0];
    const slot = await (await fetch(`/api/processors/${proc.id}/slots/0`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'novastar-card-h-20xrj45' }),
    })).json();
    await window.app.refreshProcessors();
    return { procId: proc.id,
             cardId: slot.resolved[0].slots[0].card.id };
}"""

MEASURE_PORT_LIST_JS = """(args) => {
    const body = document.getElementById('hardware-dock-body');
    const rows = document.querySelectorAll(
        `[data-lrd-field^="processor-port-name-${args.cardId}-"]`);
    const last = rows[rows.length - 1];
    // Any scrolling ancestor STRICTLY between a port chip and the dock body
    // is a nested scrollbox - the double scroll this test exists to forbid.
    const nested = [];
    for (let el = last.parentElement; el && el !== body;
         el = el.parentElement) {
        const cs = getComputedStyle(el);
        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                && el.scrollHeight > el.clientHeight + 1) {
            nested.push(el.id || el.className || el.tagName);
        }
    }
    // Reaching port 20 must be the DOCK BODY's scroll and nobody else's:
    // scroll the field into view, then check it landed inside the body's
    // box and that the body is the thing that moved.
    body.scrollTop = 0;
    last.scrollIntoView({ block: 'nearest' });
    const s = body.getBoundingClientRect();
    const r = last.getBoundingClientRect();
    return {
        ports: rows.length,
        nested: nested,
        bodyScrolls: body.scrollHeight > body.clientHeight + 1,
        bodyMoved: body.scrollTop > 0,
        lastReachable: r.top >= s.top - 0.5 && r.bottom <= s.bottom + 0.5,
    };
}"""


def test_dock_scroll_alone_reaches_all_twenty_ports(panel_page):
    """A 20-port card in the tray: every port chip - the open editor at the
    far end included - is reached by scrolling the DOCK BODY, and nothing
    between a chip and the body scrolls on its own. The tray is squeezed to
    its resize floor first so it actually has something to scroll."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = panel_page.evaluate(PORT_LIST_SEED_JS)
    panel_page.wait_for_timeout(600)
    # the dock's own height var (theme.js's resize row), floored at 100px
    panel_page.evaluate("""() => document.documentElement.style
        .setProperty('--lrd-dock-h', '100px')""")
    panel_page.wait_for_timeout(400)
    try:
        # port 20's editor is the far end of the walk, so it is the one opened
        assert panel_page.evaluate(OPEN_TILE_JS, f"port-{ids['cardId']}-20"), (
            'port 20 has no chip to open')
        panel_page.wait_for_timeout(100)
        out = panel_page.evaluate(MEASURE_PORT_LIST_JS,
                                  {'cardId': ids['cardId']})
        assert out['ports'] == 20, out
        assert not out['nested'], (
            f"a scrollbox sits between the port chips and the dock body: "
            f"{out['nested']}")
        assert out['bodyScrolls'], (
            'the dock body has nothing to scroll at its 100px floor, so '
            'this test proves nothing')
        assert out['bodyMoved'], (
            'port 20 came into view without the dock body scrolling - '
            'something else is doing the scrolling')
        assert out['lastReachable'], (
            'scrolling the dock body does not bring port 20 into view')
    finally:
        panel_page.evaluate("""() => document.documentElement.style
            .removeProperty('--lrd-dock-h')""")
        panel_page.wait_for_timeout(300)


# ── 12. The issue strip is the refuse-and-offer surface ───────────────────
#
# The Port Numbering panel's issue boxes and foot re-homed: the issues are
# the slim strip rows under the dock's header (#hw-dock-issues, offers as
# inline buttons, same wording from the server) and the per-card usage
# foot is the card headers' used/capacity glance. The auto toggle is
# retired from the UI entirely - the strip's amber auto-off row (and its
# turn-back-on offer) is the one recovery path for a legacy project saved
# with auto off, and per-screen overflow lives under the header's
# attachment flag (test_hardware_dock.py owns that surface).

ASSIGNMENT_FIT_JS = """(hostId) => {
    const host = document.getElementById(hostId);
    if (!host) return null;
    const box = host.getBoundingClientRect();
    const strays = [];
    host.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
            strays.push({ tag: el.tagName,
                          key: el.getAttribute('data-lrd-field')
                              || el.className || el.textContent.slice(0, 24),
                          over: Math.round(Math.max(r.right - box.right,
                                                    box.left - r.left)) });
        }
    });
    return { rows: host.children.length, scrollW: host.scrollWidth,
             clientW: host.clientWidth, strays: strays };
}"""


@pytest.mark.parametrize('width', [1280, 860])
def test_the_issue_strip_fits_at_both_widths(panel_page, width):
    """The strip with a real issue in it - the auto-off row and its offer
    button - measured at the usual window and a squeezed one: nothing hangs
    past the strip's edge and nothing scrolls sideways. (The old widths
    were the retired sidebar's clamp; the strip spans the window now, so
    the squeeze is the viewport's.)"""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    panel_page.evaluate(RESET_PROCESSORS_JS)
    panel_page.wait_for_timeout(800)
    panel_page.set_viewport_size({'width': width, 'height': 720})
    panel_page.wait_for_timeout(400)
    try:
        # auto off raises the one issue every seeded project can have. The
        # UI no longer offers the trip (the toggle is retired), so this
        # drives the endpoint the way a legacy project's saved state would
        # arrive - and the amber row is exactly the recovery path for that.
        panel_page.evaluate(
            "() => window.app._assignmentRequest("
            "'/api/port-assignments', 'PUT', {auto: false})")
        panel_page.wait_for_timeout(800)
        m = panel_page.evaluate(ASSIGNMENT_FIT_JS, 'hw-dock-issues')
        assert m, '#hw-dock-issues is not in the document'
        assert m['rows'] > 0, (
            'the strip rendered nothing - the auto-off issue never came up, '
            'so this test proves nothing')
        assert not m['strays'], (
            f"strip content hangs outside the tray at {width}px: "
            f"{m['strays']} (host clientWidth {m['clientW']}px)")
        assert m['scrollW'] <= m['clientW'], (
            f"the strip scrolls sideways at {width}px: content "
            f"{m['scrollW']}px in a {m['clientW']}px tray")
    finally:
        panel_page.evaluate(
            "() => window.app._assignmentRequest("
            "'/api/port-assignments', 'PUT', {auto: true})")
        panel_page.wait_for_timeout(800)
        panel_page.set_viewport_size({'width': 1280, 'height': 720})
        panel_page.wait_for_timeout(300)


def test_the_dock_strip_reports_offers_and_recovers_auto(panel_page):
    """The Port Numbering panel's remains, in their dock homes: the issue
    rows with their offer buttons on the strip, the per-card usage as the
    card headers' used/capacity glance, the attachment flag on the header
    bar - and no per-port rows and no auto toggle at all (assignment is
    the dock's drag, and the UI never offers the auto:false trip). The
    refuse-and-offer surface is the part a drag cannot replace, so the
    legacy path is proven live end to end: a project arriving with auto
    off (driven at the endpoint, the way a saved file arrives) raises the
    amber auto-off row with its offer, and taking the offer turns auto
    back on."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = panel_page.evaluate(RESET_PROCESSORS_JS)
    panel_page.wait_for_timeout(800)

    shape = panel_page.evaluate("""(cardId) => {
        const strip = document.getElementById('hw-dock-issues');
        const flag = document.getElementById('hw-dock-flag');
        const head = document.querySelector(
            `[data-lrd-sec="hwdock-card-${cardId}"]`);
        const use = head && head.querySelector('.hw-dock-unit-use');
        return {
            stripInDock: !!strip && !!strip.closest('#hardware-dock'),
            retiredHosts: ['processor-list', 'port-assignment-issues',
                           'port-assignment-foot', 'port-assignment-list',
                           'port-assignment-auto', 'hw-dock-auto-wrap']
                .filter(id => document.getElementById(id)),
            flagInHeader: !!(flag && flag.closest('.hw-dock-head')),
            cardGlance: use ? use.textContent : null,
            rowButtons: [...(strip ? strip.querySelectorAll('button') : [])]
                .map(b => b.textContent.trim())
                .filter(t => ['move', 'pin', 'release', 'close',
                              'Move whole block',
                              'Release all pins'].includes(t)),
        };
    }""", ids['cardId'])
    assert shape['stripInDock'], shape
    assert shape['retiredHosts'] == [], (
        f"retired Signal panel hosts (or the retired auto toggle) are "
        f"back: {shape['retiredHosts']}")
    assert shape['rowButtons'] == [], (
        f"per-port assignment controls are back: {shape['rowButtons']}")
    assert shape['flagInHeader'], (
        f'the attachment flag left the dock header: {shape}')
    assert shape['cardGlance'] and '/' in shape['cardGlance'], (
        f'the per-card usage glance is gone from the card header: {shape}')

    # a legacy project's auto:false raises the auto-off issue and its offer
    panel_page.evaluate(
        "() => window.app._assignmentRequest("
        "'/api/port-assignments', 'PUT', {auto: false})")
    panel_page.wait_for_timeout(800)
    issue = panel_page.evaluate("""() => {
        const strip = document.getElementById('hw-dock-issues');
        const offer = [...strip.querySelectorAll('button')]
            .find(b => b.textContent.includes('auto-numbering on'));
        const row = offer && offer.closest('.hw-dock-issue');
        return {text: strip.textContent, offer: !!offer,
                mild: !!(row && row.classList.contains(
                    'hw-dock-issue-mild'))};
    }""")
    assert issue['offer'], f'the auto-off issue carries no offer: {issue}'
    assert issue['mild'], (
        f'auto-off is a condition, not a question - it wears the amber '
        f'row: {issue}')

    # taking the offer is the recovery path - auto back on, issue gone
    panel_page.evaluate("""() => {
        [...document.querySelectorAll('#hw-dock-issues button')]
            .find(b => b.textContent.includes('auto-numbering on')).click();
    }""")
    panel_page.wait_for_timeout(800)
    after = panel_page.evaluate("""() => ({
        on: !!(window.app._assignment && window.app._assignment.auto),
        issues: document.getElementById('hw-dock-issues').textContent,
    })""")
    assert after['on'], f'the offer did not turn auto back on: {after}'
    assert 'auto' not in after['issues'].lower() or after['issues'] == '', (
        f'the auto-off issue is still up: {after}')


def test_the_return_template_round_trips_through_undo(panel_page):
    """The backup template through the real input - which lives in the
    card's gear popover now, so the driver opens the gear the way a user
    does: the edit lands on the server, earns its own named history entry,
    survives the dock rebuild the round trip causes (the popover re-renders
    in place while it stays open), and undo/redo walk the whole card's
    returns back to <primary>R and forward to the template again."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = panel_page.evaluate(RESET_PROCESSORS_JS)
    panel_page.wait_for_timeout(600)

    assert panel_page.evaluate(OPEN_GEAR_JS, f"card-{ids['cardId']}"), (
        'the card gear did not open')
    panel_page.wait_for_timeout(200)
    panel_page.evaluate("""(args) => {
        const input = document.querySelector(
            `[data-lrd-field="processor-card-return-template-${args.cardId}"]`);
        input.value = 'BU-#';
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }""", {'cardId': ids['cardId']})
    panel_page.wait_for_timeout(800)

    # The rebuild the round trip caused re-rendered the popover in place:
    # still open, the field back under its key with the stored value.
    survived = panel_page.evaluate("""(cardId) => {
        const pop = document.getElementById('hw-gear-popover');
        const input = pop && pop.querySelector(
            `[data-lrd-field="processor-card-return-template-${cardId}"]`);
        return { open: !!pop && pop.style.display !== 'none',
                 field: !!input, value: input ? input.value : null };
    }""", ids['cardId'])
    assert survived['open'], f'the rebuild closed the open popover: {survived}'
    assert survived['field'] and survived['value'] == 'BU-#', survived

    def stored():
        state = panel_page.evaluate(
            "async () => await (await fetch('/api/processors')).json()")
        card = next(s['card'] for s in state['processors'][0]['slots']
                    if s.get('card'))
        resolved = next(s['card'] for s in state['resolved'][0]['slots']
                        if s.get('card'))
        return (card.get('returnLabelTemplate'),
                resolved['ports'][0]['returnLabel'])

    assert stored() == ('BU-#', 'BU-1')
    action = panel_page.evaluate(
        "() => window.app.history[window.app.history.length - 1].action")
    assert action == 'Edit Card Return Label Template'

    panel_page.evaluate("() => window.app.undo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == (None, 'SR-1R'), 'undo did not clear the template'

    panel_page.evaluate("() => window.app.redo()")
    panel_page.wait_for_timeout(1000)
    assert stored() == ('BU-#', 'BU-1'), 'redo did not restore the template'
    # leave the popover closed for the next test - Escape is its teardown
    panel_page.keyboard.press('Escape')
    panel_page.wait_for_timeout(100)


def test_the_reporting_left_the_retired_hosts_for_the_strip():
    """The old pinned-grid-track assertion has no home any more: the
    sidebar hosts it measured (#processor-list, #port-assignment-issues,
    the foot) retired with the Signal sidebar, and the strip rows are flex
    lines with nothing to pin. What replaces the pin is the consolidation
    itself, asserted as source: the assignment module renders ONLY the
    strip (no foot builder, no per-screen list), and the template declares
    the strip between the dock's header and its body."""
    source = js_source('app-port-assignment.js')
    for gone in ('_buildAssignmentFoot', 'port-assignment-foot',
                 'port-assignment-list', 'processor-list'):
        assert gone not in source, (
            f'{gone!r} is back in the assignment module - the strip is the '
            f'one reporting surface')
    assert "getElementById('hw-dock-issues')" in source, (
        'the assignment render no longer writes the dock strip')
    template = os.path.join(os.path.dirname(__file__), '..', 'src',
                            'templates', 'index.html')
    with open(template, encoding='utf-8') as fh:
        html = fh.read()
    assert html.index('id="hardware-dock"') \
        < html.index('id="hw-dock-issues"') \
        < html.index('id="hardware-dock-body"'), (
        'the issue strip left its slot between the dock header and body')
    for host in ('id="processor-list"', 'id="port-assignment-issues"',
                 'id="port-assignment-foot"'):
        assert host not in html, f'the retired host {host} is back'


# ── 13. Each hardware section folds on the dock ───────────────────────────
#
# Eight screens is eight processors, and eight expanded SX40 trees - boxes
# and a 40-chip grid each - is a tray no scroll makes readable. The dock's
# sections fold by the SAME machinery the sidebar blocks use (app-core.js
# _wireSectionCollapse): single click on the arrow, double-click on the
# head, state per section under ledRasterPanelCollapsed_hwdock-card-<id> /
# hwdock-box-<id>. The header never swaps anything out: it always carries
# the model text, the inline name field and the used/capacity glance
# (.hw-dock-unit-use + .hw-dock-headbar fill), so a folded card still says
# what it is and how full it is - the retired panel's summary line and
# usage foot, worn permanently.

def test_the_dock_wires_the_shared_fold_machinery():
    """One mechanism, not a copy: the dock's sections go through
    _wireSectionCollapse on every rebuild, keyed per card/box id, and the
    gear's Remove takes the deleted machine's keys with it - every other
    way a processor leaves (undo, a project loading over this one) merely
    orphans a key, which nothing can inherit because ids never recur
    within a project."""
    source = js_source('app-dock.js')
    assert 'this._wireSectionCollapse(body)' in source
    assert 'head.dataset.lrdSec = secId' in source
    assert "body.className = 'lrd-sec-body'" in source
    assert 'hwdock-card-${card.id}' in source
    assert 'hwdock-box-${cvt.id}' in source
    # The remove lives in the gear popovers' content, so the key cleanup
    # lives with it in the processors module.
    procs = js_source('app-processors.js')
    assert 'ledRasterPanelCollapsed_hwdock-card-' in procs, (
        'the deleted card key is not cleaned up')
    assert 'ledRasterPanelCollapsed_hwdock-box-' in procs, (
        'the deleted box key is not cleaned up')


FOLD_SEED_JS = """async () => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of (state.processors || [])) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const mk = async (deviceId, body) => {
        const add = await (await fetch('/api/processors', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deviceId }),
        })).json();
        const proc = add.resolved[add.resolved.length - 1];
        if (body) {
            await fetch(`/api/processors/${proc.id}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        }
        return proc.id;
    };
    // The user's own shape: a named, redundant SX40 - and a second machine
    // so independence is provable.
    const sx = await mk('brompton-sx40', { name: 'SL IMAG', redundancy: true });
    const mx = await mk('novastar-mx20', null);
    // These tests need the live screen ON the SX40 (used > 0) and OFF the
    // MX20 (0/6). Since the platform wall (2026-08-28) that is the
    // Processing setting's call, so re-stamp the module's screen from the
    // stock COEX to Brompton for this section.
    const screen = window.app.project.layers.find(
        l => (l.type || 'screen') === 'screen');
    screen.processorType = 'brompton';
    await fetch(`/api/layer/${screen.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ processorType: 'brompton' }),
    });
    const resolved = (await (await fetch('/api/processors')).json()).resolved;
    const cardOf = (p) => p.slots.map(s => s.card).find(Boolean);
    const sxCard = cardOf(resolved[0]);
    const mxCard = cardOf(resolved[1]);
    // Ids can RECUR here: the reload test PUTs a saved project back, which
    // rewinds next_processor_seq, so a card minted now can wear an id whose
    // fold key an earlier test stored as collapsed. Shed any inherited key
    // BEFORE the render applies it.
    try {
        for (const c of [sxCard, mxCard]) {
            localStorage.removeItem(
                'ledRasterPanelCollapsed_hwdock-card-' + c.id);
            for (const v of (c.cvts || [])) {
                localStorage.removeItem(
                    'ledRasterPanelCollapsed_hwdock-box-' + v.id);
            }
        }
    } catch (e) { /* blocked storage never held the keys */ }
    await window.app.refreshProcessors();
    return { sx, mx, sxCard: sxCard.id, mxCard: mxCard.id, resolved };
}"""

FOLD_STATE_JS = """(secId) => {
    const head = document.querySelector(`[data-lrd-sec="${secId}"]`);
    if (!head) return null;
    const box = head.parentElement;
    const body = box.querySelector(':scope > .lrd-sec-body');
    const arrow = head.querySelector('.lrd-sec-arrow');
    const use = head.querySelector('.hw-dock-unit-use');
    const bar = head.querySelector('.hw-dock-headbar');
    const name = head.querySelector('input.hw-dock-name');
    const vis = (el) => !!el && el.getClientRects().length > 0;
    return {
        wired: !!(arrow && body),
        collapsed: body ? getComputedStyle(body).display === 'none' : null,
        bodyInDom: !!body && body.isConnected,
        arrowVisible: vis(arrow),
        glanceText: use ? use.textContent : null,
        glanceVisible: vis(use) && vis(bar),
        nameVisible: vis(name),
        nameKey: name ? name.dataset.lrdField : null,
        headFits: head.scrollWidth <= head.clientWidth + 1,
        boxHeight: Math.round(box.getBoundingClientRect().height),
        stored: localStorage.getItem('ledRasterPanelCollapsed_' + secId),
    };
}"""


def fold_state(page, sec_id):
    return page.evaluate(FOLD_STATE_JS, sec_id)


def sec_arrow(page, sec_id):
    return page.locator(f'[data-lrd-sec="{sec_id}"] .lrd-sec-arrow')


def card_sec(ids, which):
    return f'hwdock-card-{ids[which]}'


def seed_fold(panel_page):
    ids = panel_page.evaluate(FOLD_SEED_JS)
    panel_page.wait_for_timeout(600)
    return ids


def test_the_arrow_folds_a_card_and_nothing_leaves_the_dom(panel_page):
    """Fresh ids have no stored state, so both machines' cards arrive
    expanded; the arrow folds one while the other stands, the folded body
    hides but never detaches (the focus keys must keep resolving), and the
    state lands under the card's own key. The header keeps its inline name
    field and glance either way - the consolidation put the editors ON the
    header, so folding hides the chips, never the identity (the old panel
    swapped editors for a summary line; that swap retired with it)."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    for which in ('sxCard', 'mxCard'):
        sec = card_sec(ids, which)
        s = fold_state(panel_page, sec)
        assert s and s['wired'], f'{sec} was not wired for folding: {s}'
        assert s['collapsed'] is False, f'a NEW card arrived folded: {s}'
        assert s['arrowVisible'], f'{sec} has no visible arrow: {s}'
        assert s['glanceVisible'], (
            f'the glance is permanent header furniture, open or folded: {s}')
        assert s['nameKey'] == f'processor-card-name-{ids[which]}', s

    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)
    s = fold_state(panel_page, card_sec(ids, 'sxCard'))
    assert s['collapsed'] is True, f'the arrow did not fold the card: {s}'
    assert s['bodyInDom'], 'the folded body left the DOM'
    assert s['nameVisible'] and s['glanceVisible'], (
        f'the folded header lost its inline name or glance: {s}')
    assert s['stored'] == '1', f'the fold did not persist: {s}'
    assert fold_state(panel_page,
                      card_sec(ids, 'mxCard'))['collapsed'] is False, (
        'folding one card took its neighbour')
    # hidden, never detached: a port field inside the folded body still
    # answers the focus-restore lookup by its unchanged key
    assert panel_page.evaluate(
        """(cardId) => !!document.querySelector(
               `#hardware-dock [data-lrd-field=`
               + `"processor-port-name-${cardId}-1"]`)""",
        ids['sxCard']), 'a folded card\'s port field no longer resolves'

    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)
    s = fold_state(panel_page, card_sec(ids, 'sxCard'))
    assert s['collapsed'] is False and s['stored'] == '0', s


def test_the_glance_reads_the_occupancy_and_never_renumbers(panel_page):
    """The header's glance, read off the assignment summary and nothing
    else: used over capacity, on the same header that carries the model
    text and the inline name. The redundant SX40 reads /40 - redundancy is
    a patching plan, never a renumbering, so the socket count stands (the
    'redundant' flag of the retired summary line lives in the gear's
    checkbox now). The used side is the occupancy's answer, never a
    one-to-one assumption: the live screen sits on the first machine's
    card, so the second machine's card reads 0/6 - an unused box stated as
    such."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    summary = panel_page.evaluate("""(ids) => {
        const byCard = {};
        (window.app._assignment.cards || []).forEach(c => {
            byCard[c.cardId] = c;
        });
        const strip = document.querySelector(
            `[data-lrd-field="processor-name-${ids.sx}"]`)
            .closest('.hw-dock-proc-name');
        return {
            sx: byCard[ids.sxCard] || null,
            mx: byCard[ids.mxCard] || null,
            stripModel: strip.querySelector('span').textContent,
            stripName: strip.querySelector('input').value,
        };
    }""", ids)
    assert summary['sx'], 'the assignment resolved no summary for the SX40'
    sx_glance = fold_state(panel_page, card_sec(ids, 'sxCard'))['glanceText']
    assert sx_glance == (f"{summary['sx']['used']}/"
                         f"{summary['sx']['capacity']}"), (
        f'the glance is not the assignment summary\'s own count: '
        f'{sx_glance} vs {summary["sx"]}')
    assert sx_glance.endswith('/40'), (
        f'redundancy renumbered the sockets out of the glance: {sx_glance}')
    assert summary['sx']['used'] > 0, (
        'the live screen never landed on the first machine, so this test '
        'proves nothing')
    mx_glance = fold_state(panel_page, card_sec(ids, 'mxCard'))['glanceText']
    assert mx_glance == '0/6', f'an unused card should read 0/6: {mx_glance}'
    # The identity half of the retired summary line: the processor strip
    # speaks the model as static text and the name in its inline field.
    assert summary['stripModel'] == ids['resolved'][0]['deviceName']
    assert summary['stripName'] == 'SL IMAG'


def test_the_glance_follows_the_occupancy_as_screens_arrive(panel_page):
    """One machine, more screens - the glance follows the occupancy as they
    arrive, because the occupancy change is what re-renders the dock. (The
    retired summary's screen-NAMES segment has no dock home - the chips
    themselves say who sits where - so what is pinned is the count moving
    with the resolution.)"""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    snapshot = panel_page.evaluate(
        "async () => await (await fetch('/api/project')).json()")
    try:
        before = panel_page.evaluate(
            """(ids) => (window.app._assignment.cards || [])
                   .find(c => c.cardId === ids.sxCard)""", ids)
        panel_page.evaluate("""async () => {
            await fetch('/api/layer/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'WallB', columns: 2, rows: 2,
                                       cabinet_width: 128,
                                       cabinet_height: 128 }),
            });
            window.app.project =
                await (await fetch('/api/project')).json();
            await window.app.refreshPortAssignment();
        }""")
        panel_page.wait_for_timeout(500)
        after = panel_page.evaluate(
            """(ids) => (window.app._assignment.cards || [])
                   .find(c => c.cardId === ids.sxCard)""", ids)
        assert after['used'] > before['used'], (
            f'the new screen took no ports: {before} -> {after}')
        glance = fold_state(panel_page,
                            card_sec(ids, 'sxCard'))['glanceText']
        assert glance == f"{after['used']}/{after['capacity']}", (
            f'the glance did not follow the occupancy: {glance} vs {after}')
    finally:
        # the added layer would haunt every later seed's occupancy
        panel_page.evaluate("""async (project) => {
            await fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(project),
            });
            window.app.project = await (await fetch('/api/project')).json();
            await window.app.refreshPortAssignment();
        }""", snapshot)
        panel_page.wait_for_timeout(400)


@pytest.mark.parametrize('width', [1280, 860])
def test_the_folded_header_fits_both_widths(panel_page, width):
    """The folded card is its header alone - one glance row that never
    scrolls sideways, at the usual window and a squeezed one. (The old
    widths were the retired sidebar's clamp; the dock spans the window, so
    the squeeze is the viewport's.) Eight of these is a tray of glance
    rows, not a wall."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    sec_arrow(panel_page, card_sec(ids, 'mxCard')).click()
    panel_page.wait_for_timeout(200)
    panel_page.set_viewport_size({'width': width, 'height': 720})
    panel_page.wait_for_timeout(400)
    try:
        for which in ('sxCard', 'mxCard'):
            sec = card_sec(ids, which)
            s = fold_state(panel_page, sec)
            assert s['collapsed'] is True, f'{sec} lost its fold: {s}'
            assert s['headFits'], (
                f'{sec} header clips sideways at {width}px: {s}')
            # Header furniture only - name, glance, gear on one wrappable
            # row - against a few hundred px of chips expanded.
            assert s['boxHeight'] <= 90, (
                f'{sec} folded is not a glance row at {width}px: {s}')
    finally:
        panel_page.set_viewport_size({'width': 1280, 'height': 720})
        panel_page.wait_for_timeout(300)


def test_a_single_click_is_inert_and_the_names_edit_inline(panel_page):
    """The head holds the inline name field and is the unit's drag handle,
    so the fold must never eat a click: a single click on head surface does
    nothing, and typing into the header fields commits through the same
    PUTs the panel's editors made - the processor's name on its strip, the
    card's name on its section head."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec = card_sec(ids, 'sxCard')
    # the static model span is head surface that is neither arrow nor input
    panel_page.locator(
        f'[data-lrd-sec="{sec}"] .hw-dock-unit-name').first.click()
    panel_page.wait_for_timeout(100)
    assert fold_state(panel_page, sec)['collapsed'] is False, (
        'a single click on the header folded the card')

    field = panel_page.locator(
        f'[data-lrd-field="processor-name-{ids["sx"]}"]')
    field.click()
    field.fill('')
    panel_page.keyboard.type('SL WALL')
    panel_page.keyboard.press('Tab')
    panel_page.wait_for_timeout(800)
    stored = panel_page.evaluate(
        "async () => (await (await fetch('/api/processors')).json())"
        ".processors[0].name")
    assert stored == 'SL WALL', 'the rename never reached the server'
    assert fold_state(panel_page, sec)['collapsed'] is False, (
        'editing the name folded the card')

    # the card's own inline name, on the section head itself
    field = panel_page.locator(
        f'[data-lrd-field="processor-card-name-{ids["sxCard"]}"]')
    field.click()
    field.fill('SL')
    panel_page.keyboard.press('Tab')
    panel_page.wait_for_timeout(800)
    stored = panel_page.evaluate(
        "async () => (await (await fetch('/api/processors')).json())"
        ".processors[0].slots.map(s => s.card).find(Boolean).name")
    assert stored == 'SL', 'the card rename never reached the server'
    assert fold_state(panel_page, sec)['collapsed'] is False, (
        'editing the card name folded the section')


def test_double_click_toggles_except_on_the_name_field(panel_page):
    """Double-click on head surface folds; the head stays painted while
    folded (it IS the folded card), so double-click there unfolds too; a
    double-click that lands IN the inline name input is the input's
    word-select, never a fold."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec = card_sec(ids, 'sxCard')
    head = panel_page.locator(f'[data-lrd-sec="{sec}"]')

    head.locator('.hw-dock-unit-name').first.dblclick()
    panel_page.wait_for_timeout(200)
    assert fold_state(panel_page, sec)['collapsed'] is True, (
        'double-click on the header did not fold the card')

    head.locator('.hw-dock-unit-name').first.dblclick()
    panel_page.wait_for_timeout(200)
    assert fold_state(panel_page, sec)['collapsed'] is False, (
        'double-click on the folded header did not unfold the card')

    head.locator(
        f'[data-lrd-field="processor-card-name-{ids["sxCard"]}"]').dblclick()
    panel_page.wait_for_timeout(200)
    assert fold_state(panel_page, sec)['collapsed'] is False, (
        'double-click inside the name field folded the card under the caret')


def test_fold_state_survives_reload_and_new_cards_arrive_open(panel_page):
    """Per-section persistence: the folded SX40 card comes back folded, its
    open neighbour open, and a processor added afterwards - about to be
    configured - arrives with its card expanded without touching either."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)

    panel_page.reload(wait_until='domcontentloaded')
    panel_page.wait_for_timeout(2000)
    panel_page.locator('[data-mode="data-flow"]').click()
    panel_page.wait_for_timeout(600)
    assert fold_state(panel_page,
                      card_sec(ids, 'sxCard'))['collapsed'] is True, (
        'the folded card came back expanded after a reload')
    assert fold_state(panel_page,
                      card_sec(ids, 'mxCard'))['collapsed'] is False, (
        'the open card came back folded after a reload')

    new_card = panel_page.evaluate("""async () => {
        const add = await (await fetch('/api/processors', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deviceId: 'brompton-s8' }),
        })).json();
        const proc = add.resolved[add.resolved.length - 1];
        const card = proc.slots.map(s => s.card).find(Boolean);
        // shed any fold key an earlier test left on this recycled id -
        // the seed's rule, applied to the card minted mid-test
        try {
            localStorage.removeItem(
                'ledRasterPanelCollapsed_hwdock-card-' + card.id);
        } catch (e) { /* blocked storage never held the key */ }
        await window.app.refreshProcessors();
        return card.id;
    }""")
    panel_page.wait_for_timeout(400)
    assert fold_state(panel_page,
                      f'hwdock-card-{new_card}')['collapsed'] is False, (
        'a brand-new card arrived folded')
    assert fold_state(panel_page,
                      card_sec(ids, 'sxCard'))['collapsed'] is True, (
        'adding a processor unfolded an existing card')


def test_a_rebuild_keeps_each_sections_own_state(panel_page):
    """The dock is rebuilt wholesale on every change; the fold rides the
    per-id keys through the wipe, both on a bare re-render (through
    renderProcessorPanel, which every "the tree changed" path still calls
    and which delegates to the dock) and on a real server round-trip that
    changes the tree."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)

    panel_page.evaluate("() => window.app.renderProcessorPanel()")
    panel_page.wait_for_timeout(200)
    assert fold_state(panel_page,
                      card_sec(ids, 'sxCard'))['collapsed'] is True, (
        'a bare re-render dropped the fold')
    assert fold_state(panel_page,
                      card_sec(ids, 'mxCard'))['collapsed'] is False

    panel_page.evaluate("""async (args) => {
        await fetch(`/api/processors/${args.sx}/cards/${args.sxCard}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'SL' }),
        });
        await window.app.refreshProcessors();
    }""", {'sx': ids['sx'], 'sxCard': ids['sxCard']})
    panel_page.wait_for_timeout(400)
    assert fold_state(panel_page,
                      card_sec(ids, 'sxCard'))['collapsed'] is True, (
        'a server round-trip re-expanded the folded card')
    assert fold_state(panel_page,
                      card_sec(ids, 'mxCard'))['collapsed'] is False


def test_focus_restore_into_a_folded_section_unfolds_it(panel_page):
    """The stated rule from the section machinery, on the dock: a field the
    app is putting the caret back into must not be display:none, so the
    restore opens the folded card section - and persists the opening, or
    the next rebuild folds the field away again. Driven through a port
    Name field, a field that actually lives in the foldable body (the
    header's own inline name never folds away, so it cannot prove this)."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    assert panel_page.evaluate(OPEN_TILE_JS, f"port-{ids['mxCard']}-1"), (
        'port 1 has no chip to open')
    panel_page.wait_for_timeout(100)
    out = panel_page.evaluate("""async (args) => {
        const app = window.app;
        const el = document.querySelector(
            `[data-lrd-field="processor-port-name-${args.mxCard}-1"]`);
        if (!el) return { skipped: true };
        el.focus();
        app._preserveEditorFocus();            // captures key + schedules restore
        const box = document.querySelector(
            `[data-lrd-sec-id="hwdock-card-${args.mxCard}"]`);
        app._setSectionCollapsed(box, true);   // fold before the restore lands
        if (document.activeElement) document.activeElement.blur();
        await new Promise(r => setTimeout(r, 20));
        const body = box.querySelector(':scope > .lrd-sec-body');
        return {
            reopened: getComputedStyle(body).display !== 'none',
            focusedBack: document.activeElement === el,
            stored: localStorage.getItem(
                'ledRasterPanelCollapsed_hwdock-card-' + args.mxCard),
        };
    }""", {'mxCard': ids['mxCard']})
    assert not out.get('skipped'), 'the chip built no name field to focus'
    assert out['reopened'], (
        f'the restore left the section folded around the field: {out}')
    assert out['focusedBack'], f'focus was not restored into the field: {out}'
    assert out['stored'] == '0', f'the auto-expansion did not persist: {out}'
    # leave the chip closed for the next test
    panel_page.evaluate("""(tid) => {
        const tile = document.querySelector(`[data-lrd-tile="${tid}"]`);
        if (tile && tile.classList.contains('lrd-tile-open')) {
            window.app._setTileOpen(tile, false);
        }
    }""", f"port-{ids['mxCard']}-1")


def test_the_chips_are_the_assignment_surface_and_no_chooser_survives(
        panel_page):
    """The set/place chooser is gone - assignment is the dock's drag - so
    no chooser field exists anywhere, and every port chip is armed as a
    drag handle. Folding the card section hides its chips (the old
    'panel fold never touches the dock' outcome retired with the panel:
    the dock section IS the visibility now) but detaches nothing - and the
    folded HEADER still drags the whole card, which test_hardware_dock.py
    pins as a live drop."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    out = panel_page.evaluate("""(args) => {
        const tile = document.querySelector(
            `#hardware-dock [data-hwdock="port-${args.sxCard}-1"]`);
        return {
            pickerAnywhere: !!document.querySelector(
                '[data-lrd-field^="processor-port-assign-"]'),
            tilePainted: !!tile && tile.getClientRects().length > 0,
            tileArmed: !!(tile && tile.dataset.hwdockPayload),
        };
    }""", {'sxCard': ids['sxCard']})
    assert not out['pickerAnywhere'], f'the old chooser survives: {out}'
    assert out['tilePainted'] and out['tileArmed'], (
        f'the open card\'s chip is not a drawn drag handle: {out}')

    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)
    out = panel_page.evaluate("""(args) => {
        const tile = document.querySelector(
            `#hardware-dock [data-hwdock="port-${args.sxCard}-1"]`);
        const head = document.querySelector(
            `[data-lrd-sec="hwdock-card-${args.sxCard}"]`);
        return {
            tileInDom: !!tile,
            tileHidden: !!tile && tile.getClientRects().length === 0,
            headArmed: !!(head && head.dataset.hwdockPayload
                && head.getClientRects().length > 0),
        };
    }""", {'sxCard': ids['sxCard']})
    assert out['tileInDom'] and out['tileHidden'], (
        f'the folded body detached or kept painting its chips: {out}')
    assert out['headArmed'], (
        f'the folded header lost its whole-card drag arming: {out}')


def test_the_dock_fold_hides_all_and_gives_each_section_back_its_state(
        panel_page):
    """Two levels, two sets of keys: the header's chevron folds the WHOLE
    tray (proxying the one dock collapse the hanging tab owns), and
    unfolding it is not a reset - the folded SX40 card is still folded,
    its open neighbour still open."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec_arrow(panel_page, card_sec(ids, 'sxCard')).click()
    panel_page.wait_for_timeout(200)

    try:
        panel_page.locator('#hw-dock-fold').click()
        panel_page.wait_for_timeout(300)
        dock = panel_page.evaluate("""() => {
            const el = document.getElementById('hardware-dock');
            return {
                collapsed: el.classList.contains('collapsed'),
                height: Math.round(el.getBoundingClientRect().height),
            };
        }""")
        assert dock['collapsed'] and dock['height'] == 0, (
            f'the chevron did not fold the tray to nothing: {dock}')
    finally:
        # the hanging tab is the way back - the same toggle the chevron
        # proxies, so this exercises the round trip either way
        panel_page.evaluate("""() => {
            if (document.getElementById('hardware-dock')
                    .classList.contains('collapsed')) {
                document.getElementById('hardware-dock-toggle').click();
            }
        }""")
        panel_page.wait_for_timeout(300)

    assert not panel_page.evaluate(
        """() => document.getElementById('hardware-dock')
               .classList.contains('collapsed')"""), (
        'the tray did not come back')
    assert fold_state(panel_page,
                      card_sec(ids, 'sxCard'))['collapsed'] is True, (
        'unfolding the tray reset a folded card')
    assert fold_state(panel_page,
                      card_sec(ids, 'mxCard'))['collapsed'] is False, (
        'unfolding the tray folded an open card')


def test_deleting_a_processor_takes_its_fold_keys_with_it(panel_page):
    """The id never comes back, so the key must not sit in localStorage
    forever. The gear's Remove takes the machine's card and box keys with
    it; every other leaving path just orphans a key, which no later
    processor can inherit."""
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    ids = seed_fold(panel_page)
    sec = card_sec(ids, 'mxCard')
    sec_arrow(panel_page, sec).click()
    sec_arrow(panel_page, sec).click()   # key now exists, card open
    panel_page.wait_for_timeout(200)
    assert fold_state(panel_page, sec)['stored'] == '0'

    assert panel_page.evaluate(OPEN_GEAR_JS, f"proc-{ids['mx']}"), (
        'the processor gear did not open')
    panel_page.locator('#hw-gear-popover .hw-pop-remove').click()
    panel_page.wait_for_timeout(800)
    assert fold_state(panel_page, sec) is None, (
        'the deleted processor\'s card is still drawn')
    left = panel_page.evaluate(
        """(sec) => localStorage.getItem(
               'ledRasterPanelCollapsed_' + sec)""", sec)
    assert left is None, f'the deleted card left its fold key: {left}'


# ── 14. The data-redundancy modes, as stored and as refused ───────────────
#
# The user's design, verbatim: "so for data by default do redundancy as 1 to
# 1 aka the way brompton does it and novastar when using a second sending
# card and then give the option for sequential where 1 is backed up by 2 on
# the same unit/ sending card and also give the option for say 1 is backed
# up to whatever port you want". Three modes per card, 1:1 the default; the
# mode is stored on the card, the 1:1 partner is a per-main pick, manual is
# a sparse per-port map. Every impossible arrangement is refused with the
# reason, never stored.

def add_two(client, device='novastar-mx20'):
    state = add_processor(client, device)
    a_pid = state['resolved'][0]['id']
    a_card = first_card(state['resolved'][0])['id']
    state = add_processor(client, device)
    b_pid = state['resolved'][1]['id']
    b_card = first_card(state['resolved'][1])['id']
    return a_pid, a_card, b_pid, b_card


def card_of(state, pid):
    return first_card(next(p for p in state['resolved'] if p['id'] == pid))


def test_1to1_is_the_default_and_is_stored_as_absence(client):
    """The default mode is what an ABSENT key means, exactly like the label
    templates: choosing sequential stores it, choosing 1:1 back deletes it,
    and an untouched card stores nothing at all."""
    a_pid, a_card, _b, _bc = add_two(client)
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    state = client.get('/api/processors').get_json()
    assert card_of(state, a_pid)['redundancyShape']['mode'] == '1to1'
    assert 'redundancyMode' not in state['processors'][0]['slots'][0]['card']

    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'redundancyMode': 'sequential'})
    state = client.get('/api/processors').get_json()
    assert state['processors'][0]['slots'][0]['card']['redundancyMode'] == \
        'sequential'
    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'redundancyMode': '1to1'})
    state = client.get('/api/processors').get_json()
    assert 'redundancyMode' not in state['processors'][0]['slots'][0]['card']

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'redundancyMode': 'free-for-all'})
    assert resp.status_code == 400
    assert 'Unknown redundancy mode' in resp.get_json()['error']


def test_the_1to1_partner_pick_is_validated_with_the_counts(client):
    """A 1:1 backup mirrors port for port, so the pick is refused where the
    mirror cannot hold: itself, a card that is not there, a count that does
    not match (both counts in the reason), a count nobody settled."""
    a_pid, a_card, _b_pid, b_card = add_two(client)
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': a_card})
    assert resp.status_code == 400
    assert 'cannot back itself' in resp.get_json()['error']

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': 'card999'})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'That card is not in this project.'

    state = add_processor(client, 'novastar-mx40-pro')
    big_card = first_card(state['resolved'][2])['id']
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': big_card})
    assert resp.status_code == 400
    why = resp.get_json()['error']
    assert 'has 40 ports' in why and 'has 6' in why, why
    assert 'counts must match' in why, why

    state = add_processor(client, 'brompton-sq200')
    unknown_card = first_card(state['resolved'][3])['id']
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': unknown_card})
    assert resp.status_code == 400
    assert 'no settled port count' in resp.get_json()['error']

    # The valid pick stores, and clears back to nothing.
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': b_card})
    assert resp.status_code == 200
    assert client.get('/api/processors').get_json()['processors'][0][
        'slots'][0]['card']['backupCardId'] == b_card
    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'backupCardId': ''})
    assert 'backupCardId' not in client.get('/api/processors').get_json()[
        'processors'][0]['slots'][0]['card']


def test_a_backup_unit_backs_one_main_and_takes_no_backup_of_its_own(client):
    """Consumed means consumed: a unit already backing a main is refused to
    a second main by the role it holds, and cannot name a backup for itself
    while it holds it - both stated, neither stored."""
    a_pid, a_card, b_pid, b_card = add_two(client)
    state = add_processor(client, 'novastar-mx20')
    c_pid = state['resolved'][2]['id']
    c_card = first_card(state['resolved'][2])['id']
    client.put(f'/api/processors/{a_pid}/cards/{a_card}', json={'name': 'A'})
    client.put(f'/api/processors/{b_pid}/cards/{b_card}', json={'name': 'B'})
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    client.put(f'/api/processors/{c_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'backupCardId': b_card})
    assert resp.status_code == 200

    resp = client.put(f'/api/processors/{c_pid}/cards/{c_card}',
                      json={'backupCardId': b_card})
    assert resp.status_code == 400
    assert 'B already backs up A' in resp.get_json()['error']

    client.put(f'/api/processors/{b_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{b_pid}/cards/{b_card}',
                      json={'backupCardId': c_card})
    assert resp.status_code == 400
    assert 'cannot take a backup of its own' in resp.get_json()['error']


def test_backup_links_never_dangle(client):
    """Deleting the backup's processor clears the pick, exactly as deleting
    a primary box clears backupOf - a link into reused ids is a trap."""
    a_pid, a_card, b_pid, b_card = add_two(client)
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'backupCardId': b_card})
    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'redundancyMode': 'manual'})
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/1',
                      json={'backup': {'cardId': b_card, 'port': 2}})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    client.delete(f'/api/processors/{b_pid}')
    stored = client.get('/api/processors').get_json()['processors'][0][
        'slots'][0]['card']
    assert 'backupCardId' not in stored, 'the 1:1 pick outlived its unit'
    assert 'backupPorts' not in stored, 'a manual pick outlived its unit'


def test_the_manual_pick_is_validated_like_a_placement(client):
    """The same situations read the same way: a port past the ceiling, a
    port backing itself, a port already spoken for by another main."""
    a_pid, a_card, _b, _bc = add_two(client)
    client.put(f'/api/processors/{a_pid}/cards/{a_card}', json={'name': 'SR'})
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    client.put(f'/api/processors/{a_pid}/cards/{a_card}',
               json={'redundancyMode': 'manual'})

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/1',
                      json={'backup': {'cardId': a_card, 'port': 9}})
    assert resp.status_code == 400
    assert 'has 6 ports, so there is no port 9' in resp.get_json()['error']

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/1',
                      json={'backup': {'cardId': a_card, 'port': 1}})
    assert resp.status_code == 400
    assert 'cannot back itself' in resp.get_json()['error']

    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/1',
                      json={'backup': {'cardId': a_card, 'port': 5}})
    assert resp.status_code == 200
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/2',
                      json={'backup': {'cardId': a_card, 'port': 5}})
    assert resp.status_code == 400
    assert 'already backs up SR-1' in resp.get_json()['error']
    # Re-stating the same pick is a no-op, not a conflict with itself.
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}/ports/1',
                      json={'backup': {'cardId': a_card, 'port': 5}})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_the_halves_mode_backs_the_front_half_with_the_back_half(client):
    """The 2026-08-27 arrangement, in the user's own numbers: "say i have
    1-8 on processor 1 and 9-16 as backups? i need to be able to set those
    to backup and add then accordingly" - a MODE, one gesture, not eight
    manual picks. Within one card, port N returns on port N + half: 1 on 9,
    8 on 16. This is the one shape whose main and return genuinely wear
    DIFFERENT numbers, so the mapping states both ends plainly - and the
    return labels resolve to the backing sockets' own labels through the
    same ladder every mapping uses."""
    state = add_processor(client, 'novastar-h9')
    pid = only(state)['id']
    state = set_card(client, pid, 0, 'novastar-card-h-16xrj45-2xfiber')
    card_id = first_card(only(state))['id']
    client.put(f'/api/processors/{pid}/cards/{card_id}', json={'name': 'P1'})
    client.put(f'/api/processors/{pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{pid}/cards/{card_id}',
                      json={'redundancyMode': 'halves'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    state = resp.get_json()
    assert state['processors'][0]['slots'][0]['card']['redundancyMode'] == \
        'halves'
    card = first_card(only(state))
    assert card['redundancyShape'] == {'mode': 'halves', 'forced': False,
                                       'level': 'port', 'usable': 8}
    ports = {p['number']: p for p in card['ports']}
    for main in range(1, 9):
        assert ports[main]['backedBy']['port'] == main + 8, ports[main]
        assert ports[main + 8]['backsUp']['port'] == main, ports[main + 8]
    assert not any(ports[n].get('backedBy') for n in range(9, 17)), (
        'a backing socket was given a backup of its own')
    # P1-1 out, P1-9 back: the mapped socket's own label, exactly the
    # sequential and SX40 treatment.
    assert (ports[1]['label'], ports[1]['returnLabel']) == ('P1-1', 'P1-9')
    assert ports[1]['returnLabelSource'] == 'backup'
    assert (ports[8]['label'], ports[8]['returnLabel']) == ('P1-8', 'P1-16')


def test_the_halves_mode_splits_smaller_cards_the_same_way(client):
    """The split is the card's own ceiling, not a fixed 8/8: an MX20's six
    ports go 1-3 mains, 4-6 returns, and the usable arithmetic matches
    sequential's (an odd count would round the mains up, leaving the middle
    port a main with no backup - the same way sequential leaves the last
    odd port unpaired)."""
    a_pid, a_card, _b, _bc = add_two(client)
    client.put(f'/api/processors/{a_pid}', json={'redundancy': True})
    resp = client.put(f'/api/processors/{a_pid}/cards/{a_card}',
                      json={'redundancyMode': 'halves'})
    card = card_of(resp.get_json(), a_pid)
    assert card['redundancyShape']['usable'] == 3
    ports = {p['number']: p for p in card['ports']}
    assert [ports[n + 3]['backsUp']['port'] for n in (1, 2, 3)] == [1, 2, 3]
    assert not ports[1].get('backsUp') and not ports[3].get('backsUp')


def test_the_toggle_reaches_every_vendor_except_a_documented_no(client):
    """Redundancy became a plan for the loom, so the switch is offered
    everywhere - the user's own 1:1 case is NovaStar with a second sending
    card - except where the sheet says the device cannot (T1)."""
    state = add_processor(client, 'novastar-mx40-pro')
    assert state['resolved'][0]['redundancySupported'] is True
    state = add_processor(client, 'brompton-t1')
    assert state['resolved'][1]['redundancySupported'] is False
    pid = state['resolved'][1]['id']
    resp = client.put(f'/api/processors/{pid}', json={'redundancy': True})
    t1 = next(p for p in resp.get_json()['resolved'] if p['id'] == pid)
    assert first_card(t1)['redundancyShape'] is None, (
        'a shape appeared on a device documented unable')


def test_the_gear_wires_the_modes_the_house_way():
    """Source-text pins, same register as sections 7 and 10: the mode row
    (built for the card's gear popover) never draws for a vendor-fixed
    pairing, every new edit takes a named history snapshot, and a
    refusal's reason is surfaced instead of swallowed."""
    source = js_source('app-processors.js')
    body = source[source.index('_buildCardRedundancyRow(proc, card) {'):]
    body = body[:body.index('\n    }')]
    assert 'if (!shape || shape.forced) return null;' in body, (
        'a fixed pairing grew a mode select')
    for action in ("'Change Redundancy Mode'", "'Change Backup Unit'"):
        assert action in source, f'{action} takes no history snapshot'
    # the per-port manual pick lives in the dock chip's editor now
    assert "'Change Port Backup'" in js_source('app-dock.js'), (
        "'Change Port Backup' takes no history snapshot")
    assert 'data.error' in source, 'refusals are swallowed silently again'


# ── 14b. The mode row in the real gear popover ────────────────────────────
#
# The redundancy controls kept their keys and moved into the card's ⚙ gear
# popover, so every driver here opens the gear first (OPEN_GEAR_JS) and
# reads the popover, not a panel list. The popover closes on outside
# mousedown and Escape, and re-renders in place across the dock rebuilds
# each commit causes.

REDUNDANCY_SEED_JS = """
async () => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of state.processors) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const send = (url, method, body) => fetch(url, {
        method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }).then(r => r.json());
    let st = await send('/api/processors', 'POST',
                        { deviceId: 'novastar-mx20' });
    const mx = st.resolved[st.resolved.length - 1];
    const mxCard = mx.slots[0].card;
    await send(`/api/processors/${mx.id}/cards/${mxCard.id}`, 'PUT',
               { name: 'SR' });
    await send(`/api/processors/${mx.id}`, 'PUT', { redundancy: true });
    st = await send('/api/processors', 'POST',
                    { deviceId: 'novastar-mx20' });
    const bk = st.resolved[st.resolved.length - 1];
    const bkCard = bk.slots[0].card;
    await send(`/api/processors/${bk.id}/cards/${bkCard.id}`, 'PUT',
               { name: 'BK' });
    st = await send('/api/processors', 'POST',
                    { deviceId: 'brompton-sx40' });
    const sx = st.resolved[st.resolved.length - 1];
    await send(`/api/processors/${sx.id}`, 'PUT', { redundancy: true });
    // A NEW machine's sections must arrive open - but ids can RECUR here:
    // the reload test above PUTs a saved project back, which rewinds
    // next_processor_seq, so a card minted now can wear an id whose fold
    // key an earlier fold test stored as collapsed. Shed any inherited
    // key BEFORE the render applies it, or which test fails depends on
    // how many machines every test before it happened to seed.
    for (const card of [mxCard, bkCard, sx.slots[0].card]) {
        try {
            localStorage.removeItem(
                'ledRasterPanelCollapsed_hwdock-card-' + card.id);
            for (const v of (card.cvts || [])) {
                localStorage.removeItem(
                    'ledRasterPanelCollapsed_hwdock-box-' + v.id);
            }
        } catch (e) { /* blocked storage never held the key */ }
    }
    await window.app.refreshProcessors();
    window.app.saveState('Seed Redundancy');
    return { mxId: mx.id, mxCardId: mxCard.id, bkId: bk.id,
             bkCardId: bkCard.id, sxId: sx.id,
             sxCardId: sx.slots[0].card.id };
}
"""

STORED_CARD_JS = """
async (pid) => {
    const state = await (await fetch('/api/processors')).json();
    const proc = state.processors.find(p => p.id === pid);
    return proc.slots.find(s => s.card).card;
}
"""


def test_the_mode_select_draws_only_where_the_vendor_does_not_fix(panel_page):
    """The MX20's card gear gets the four modes; the SX40's card gear gets
    NO select, and its processor gear states the fixed pairing under the
    redundancy switch - a fact is not a setting, in the DOM either."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright is not installed")
    page = panel_page
    ids = page.evaluate(REDUNDANCY_SEED_JS)
    page.wait_for_timeout(800)
    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['mxCardId']}"), (
        'the MX20 card gear did not open')
    out = page.evaluate("""(ids) => {
        const pop = document.getElementById('hw-gear-popover');
        const mx = pop.querySelector(
            `[data-lrd-field="processor-card-redundancy-${ids.mxCardId}"]`);
        const partner = pop.querySelector(
            `[data-lrd-field="processor-card-backup-${ids.mxCardId}"]`);
        return {
            mxSelect: !!mx,
            mxOptions: mx ? Array.from(mx.options).map(o => o.value) : [],
            partner: !!partner,
            partnerTexts: partner
                ? Array.from(partner.options).map(o => o.textContent) : [],
        };
    }""", ids)
    assert out['mxSelect'], out
    assert out['mxOptions'] == ['1to1', 'sequential', 'halves', 'manual'], out
    assert out['partner'], 'the default 1:1 offers no partner pick'
    assert any('BK - 6 ports' in t for t in out['partnerTexts']), out

    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['sxCardId']}"), (
        'the SX40 card gear did not open')
    out = page.evaluate("""(ids) => {
        const pop = document.getElementById('hw-gear-popover');
        return {
            sxSelect: !!pop.querySelector(
                `[data-lrd-field="processor-card-redundancy-`
                + `${ids.sxCardId}"]`),
        };
    }""", ids)
    assert not out['sxSelect'], 'the fixed pairing grew a mode select'

    assert page.evaluate(OPEN_GEAR_JS, f"proc-{ids['sxId']}"), (
        'the SX40 processor gear did not open')
    out = page.evaluate("""() => {
        const pop = document.getElementById('hw-gear-popover');
        const texts = Array.from(pop.querySelectorAll('div'))
            .map(d => d.textContent || '');
        return {
            statement: texts.some(t => t.includes('A backs up to B')),
            control: !!pop.querySelector(
                'select[data-lrd-field*="redundancy"], '
                + 'input[data-lrd-field*="pairing"]'),
        };
    }""")
    assert out['statement'], (
        f'the fixed pairing statement left the processor gear: {out}')
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)


def test_the_mode_change_round_trips_through_undo(panel_page):
    """Same contract as every processor edit, driven through the gear:
    a named post-mutation snapshot, walked back and forward with the
    stored key following."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright is not installed")
    page = panel_page
    ids = page.evaluate(REDUNDANCY_SEED_JS)
    page.wait_for_timeout(800)
    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['mxCardId']}"), (
        'the card gear did not open')
    page.evaluate("""(ids) => {
        const sel = document.getElementById('hw-gear-popover').querySelector(
            `[data-lrd-field="processor-card-redundancy-${ids.mxCardId}"]`);
        sel.value = 'sequential';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""", ids)
    page.wait_for_timeout(800)
    assert page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-1)") == \
        ['Change Redundancy Mode']
    assert page.evaluate(STORED_CARD_JS, ids['mxId']).get(
        'redundancyMode') == 'sequential'
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1000)
    assert 'redundancyMode' not in page.evaluate(STORED_CARD_JS, ids['mxId'])
    page.evaluate("() => window.app.redo()")
    page.wait_for_timeout(1000)
    assert page.evaluate(STORED_CARD_JS, ids['mxId']).get(
        'redundancyMode') == 'sequential'
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)


def test_the_halves_mode_commits_from_the_select_and_states_its_split(
        panel_page):
    """The 2026-08-27 arrangement as ONE gesture: pick "Halves" in the
    card gear's mode select and the back half backs the front half -
    stored, mapped (an MX20's port 4 carries port 1's return), and stated
    under the select with both spans, because this is the one mode whose
    main and return wear different numbers. The popover re-renders in
    place across the commit's rebuild, so the statement is read from the
    same open popover the select lives in."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright is not installed")
    page = panel_page
    ids = page.evaluate(REDUNDANCY_SEED_JS)
    page.wait_for_timeout(800)
    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['mxCardId']}"), (
        'the card gear did not open')
    page.evaluate("""(ids) => {
        const sel = document.getElementById('hw-gear-popover').querySelector(
            `[data-lrd-field="processor-card-redundancy-${ids.mxCardId}"]`);
        sel.value = 'halves';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""", ids)
    page.wait_for_timeout(800)
    assert page.evaluate(STORED_CARD_JS, ids['mxId']).get(
        'redundancyMode') == 'halves'
    assert page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-1)") == \
        ['Change Redundancy Mode']
    out = page.evaluate("""(ids) => {
        const card = window.app._processorsResolved
            .find(p => p.id === ids.mxId).slots[0].card;
        const ports = Object.fromEntries(
            card.ports.map(p => [p.number, p]));
        const pop = document.getElementById('hw-gear-popover');
        const texts = Array.from(pop.querySelectorAll('div'))
            .map(d => d.textContent || '');
        return {
            popOpen: pop.style.display !== 'none',
            fourBacks: ports[4] && ports[4].backsUp
                ? ports[4].backsUp.port : null,
            oneBackedOn: ports[1] && ports[1].backedBy
                ? ports[1].backedBy.port : null,
            stated: texts.some(t =>
                t.includes('Ports 4-6 carry the returns of 1-3')),
        };
    }""", ids)
    assert out['popOpen'], f'the commit\'s rebuild closed the popover: {out}'
    assert out['fourBacks'] == 1 and out['oneBackedOn'] == 4, out
    assert out['stated'], out
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)
    # Leave the module's shared server the way this test found it: the
    # later pair-presentation test folds a nested unit under live refresh
    # traffic, and every extra machine in the list stretches that window.
    page.evaluate("""async (ids) => {
        for (const id of [ids.sxId, ids.bkId, ids.mxId]) {
            await fetch(`/api/processors/${id}`, { method: 'DELETE' });
        }
        await window.app.refreshProcessors();
    }""", ids)
    page.wait_for_timeout(600)


def test_the_partner_pick_and_the_manual_picker_commit(panel_page):
    """The 1:1 partner select (in the card's gear) stores the pick and the
    consumed unit states its role on its own dock header; manual mode
    unfolds a per-port picker in the port's DOCK CHIP that stores the
    sparse map - each through its own named action."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright is not installed")
    page = panel_page
    ids = page.evaluate(REDUNDANCY_SEED_JS)
    page.wait_for_timeout(800)
    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['mxCardId']}"), (
        'the card gear did not open')
    page.evaluate("""(ids) => {
        const sel = document.getElementById('hw-gear-popover').querySelector(
            `[data-lrd-field="processor-card-backup-${ids.mxCardId}"]`);
        sel.value = ids.bkCardId;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""", ids)
    page.wait_for_timeout(800)
    assert page.evaluate(STORED_CARD_JS, ids['mxId']).get(
        'backupCardId') == ids['bkCardId']
    assert page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-1)") == \
        ['Change Backup Unit']
    # The consumed unit says so where it reads: its card header wears the
    # role tag (the old panel's 'Backs up SR' line, on the dock header).
    consumed = page.evaluate("""(ids) => {
        const head = document.querySelector(
            `[data-lrd-sec="hwdock-card-${ids.bkCardId}"]`);
        return !!head && head.textContent.includes('backs up SR');
    }""", ids)
    assert consumed, 'the consumed unit does not state its role'

    # Manual mode: the mode select stays in the still-open gear; the pick
    # itself lives in the port's dock chip editor.
    page.evaluate("""(ids) => {
        const sel = document.getElementById('hw-gear-popover').querySelector(
            `[data-lrd-field="processor-card-redundancy-${ids.mxCardId}"]`);
        sel.value = 'manual';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""", ids)
    page.wait_for_timeout(800)
    page.evaluate(
        "(tid) => document.querySelector(`[data-lrd-tile=\"${tid}\"]`)"
        + ".querySelector('.lrd-tile-face').click()",
        f"port-{ids['mxCardId']}-1")
    page.wait_for_timeout(400)
    box = page.locator(
        f'[data-lrd-field="processor-port-backup-port-{ids["mxCardId"]}-1"]')
    assert box.count() == 1, 'manual mode drew no per-port picker'
    box.click()
    box.fill('5')
    page.keyboard.press('Tab')
    page.wait_for_timeout(800)
    stored = page.evaluate(STORED_CARD_JS, ids['mxId'])
    assert stored.get('backupPorts', {}).get('1') == \
        {'cardId': ids['mxCardId'], 'port': 5}
    assert page.evaluate(
        "() => window.app.history.map(h => h.action).slice(-1)") == \
        ['Change Port Backup']


def test_a_redundant_pair_presents_as_one_group_on_the_dock(panel_page):
    """A redundant pair is ONE loom and draws as ONE group, at both levels
    that state a backup: the redundant SX40's boxes nest as A-with-B and
    C-with-D pairs inside the card - two brackets, not four sibling boxes
    - and a designated 1:1 backup unit nests whole (proc strip and all)
    under its main's block in the tray. One presentation rule for "X backs
    up Y", never an SX40 special case - and layout only: the fold
    machinery keeps working on the nested unit's card."""
    pytest.importorskip("playwright.sync_api",
                        reason="playwright is not installed")
    page = panel_page
    ids = page.evaluate(REDUNDANCY_SEED_JS)
    page.wait_for_timeout(800)
    # Designate BK as SR's 1:1 backup through the real partner select,
    # opened in the card's gear the way a user reaches it.
    assert page.evaluate(OPEN_GEAR_JS, f"card-{ids['mxCardId']}"), (
        'the card gear did not open')
    page.evaluate("""(ids) => {
        const sel = document.getElementById('hw-gear-popover').querySelector(
            `[data-lrd-field="processor-card-backup-${ids.mxCardId}"]`);
        sel.value = ids.bkCardId;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }""", ids)
    page.wait_for_timeout(1000)
    page.keyboard.press('Escape')
    page.wait_for_timeout(100)
    out = page.evaluate("""(ids) => {
        const sxCvts = window.app._processorsResolved
            .find(p => p.id === ids.sxId).slots[0].card.cvts.map(c => c.id);
        const field = (id) => document.querySelector(
            `[data-lrd-field="processor-cvt-name-${id}"]`);
        const [a, b, c, d] = sxCvts.map(field);
        const pairOf = (el) => el && el.closest('.lrd-red-pair');
        const wrapOf = (pid) => {
            const strip = document.querySelector(
                `[data-lrd-field="processor-name-${pid}"]`);
            return strip && strip.closest('.hw-dock-proc');
        };
        const bkWrap = wrapOf(ids.bkId);
        const mxWrap = wrapOf(ids.mxId);
        const bkCardHead = document.querySelector(
            `[data-lrd-sec="hwdock-card-${ids.bkCardId}"]`);
        return {
            built: !!(a && b && c && d && bkWrap && mxWrap && bkCardHead),
            bNested: !!(b && b.closest('.lrd-red-backup')),
            aPlain: !!(a && !a.closest('.lrd-red-backup')),
            abPaired: !!(pairOf(a) && pairOf(a) === pairOf(b)),
            cdPaired: !!(pairOf(c) && pairOf(c) === pairOf(d)),
            pairsDistinct: !!(pairOf(a) && pairOf(a) !== pairOf(c)),
            unitNested: !!(bkWrap
                && bkWrap.classList.contains('lrd-red-backup')),
            unitPairHoldsMain: !!(bkWrap
                && bkWrap.parentElement.classList.contains('lrd-red-pair')
                && bkWrap.parentElement.contains(mxWrap)),
            nestedArrow: !!(bkCardHead
                && bkCardHead.querySelector('.lrd-sec-arrow')),
        };
    }""", ids)
    assert out['built'], out
    assert out['bNested'] and out['aPlain'], out
    assert out['abPaired'] and out['cdPaired'], out
    assert out['pairsDistinct'], (
        f'A/B and C/D collapsed into one bracket: {out}')
    assert out['unitNested'] and out['unitPairHoldsMain'], out
    assert out['nestedArrow'], 'the nested unit lost its fold machinery'
    # The nested unit's card still folds: the pair is presentation, not
    # state.
    page.locator(f'[data-lrd-sec="hwdock-card-{ids["bkCardId"]}"] '
                 '.lrd-sec-arrow').click()
    page.wait_for_timeout(200)
    folded = page.evaluate("""(ids) => {
        const head = document.querySelector(
            `[data-lrd-sec="hwdock-card-${ids.bkCardId}"]`);
        const body = head.parentElement
            .querySelector(':scope > .lrd-sec-body');
        return getComputedStyle(body).display === 'none';
    }""", ids)
    assert folded, 'the nested backup unit\'s card no longer folds'
