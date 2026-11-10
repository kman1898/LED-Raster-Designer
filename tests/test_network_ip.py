"""IP addresses on the processors (owner, 2026-11-09: "add to the
processors the ability to IP addresses and that would be represented on
the binder").

- network-ip.js, the plain functions: what is an IPv4 address and a subnet
  mask, the words a bad entry's tooltip says, which units there are and
  what each prints (its own subnet and gateway, else the show's), and
  which IPs two units share. No DOM, so it runs under node here; the tests
  skip where node is not installed.
- The routes: a processor's `network` and its backup unit's
  (`backupNetwork`) are patches stored as typed, a blank field no key; the
  show's subnet and gateway on project['network'] through
  PUT /api/processors/network. Nothing is refused for not being an
  address. A show without them opens and reads unchanged.

Run locally:
    python -m pytest tests/test_network_ip.py -v
"""
import copy
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET_JS = os.path.join(ROOT, 'src', 'static', 'js', 'network-ip.js')

needs_node = pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')


def _js(expr, *args):
    """Evaluate `expr` with N bound to NetworkIp and A to the arguments."""
    script = (f"const N = require({json.dumps(NET_JS)}); const A = {json.dumps(list(args))};"
              f"console.log(JSON.stringify({expr}));")
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# ── the plain functions ──────────────────────────────────────────────────

@needs_node
def test_an_ipv4_address_is_four_numbers_from_0_to_255():
    good = ['10.0.0.10', '192.168.1.1', '0.0.0.0', '255.255.255.255', ' 10.0.0.1 ']
    bad = ['10.0.0.300', '10.0.0', '10.0.0.1.5', '010.0.0.1', '10.0.0.-1', '10.0.0.a',
           '10..0.1', '10.0.0.1/24', '', 'ten.zero.zero.one', '1 0.0.0.1']
    assert _js('A[0].map(N.isIPv4)', good) == [True] * len(good)
    assert _js('A[0].map(N.isIPv4)', bad) == [False] * len(bad)


@needs_node
def test_a_subnet_mask_is_contiguous_or_a_prefix_length():
    good = ['255.255.255.0', '255.255.0.0', '255.255.255.252', '255.255.255.255', '128.0.0.0',
            '/24', '24', '/32', '/1']
    bad = ['255.0.255.0', '255.255.255.1', '0.0.0.0', '/0', '/33', '33', '/024', '255.255.255',
           '10.0.0.1x', 'abc']
    assert _js('A[0].map(N.isSubnetMask)', good) == [True] * len(good)
    assert _js('A[0].map(N.isSubnetMask)', bad) == [False] * len(bad)


@needs_node
def test_a_bad_entry_says_why_in_plain_words_and_a_blank_or_a_note_says_nothing():
    out = _js("[N.problem('ip', '10.0.0.300'), N.problem('gateway', '1.2.3'),"
              " N.problem('subnet', '255.0.255.0'), N.problem('ip', ''), N.problem('ip', '10.0.0.1'),"
              " N.problem('note', 'anything at all')]")
    assert out[0].startswith('Not an IP address') and 'prints as typed' in out[0], out
    assert out[1].startswith('Not a gateway address'), out
    assert out[2].startswith('Not a subnet mask'), out
    assert out[3:] == ['', '', '']
    for text in out[:3]:
        assert '—' not in text and '–' not in text and ' - ' not in text


PROCS = [
    {'id': 'p1', 'name': 'SX40 A', 'deviceName': 'SX40',
     'network': {'ip': '10.0.0.10', 'note': 'control laptop port 2'},
     'backupUnit': {'name': 'SX40 A BU', 'network': {'ip': '10.0.0.11', 'subnet': '255.255.0.0'}}},
    {'id': 'p2', 'name': '', 'deviceName': 'H9', 'network': {}},
    {'id': 'p3', 'name': 'IMAG', 'deviceName': 'MX40 Pro', 'network': {'ip': '10.0.0.10'}},
]


@needs_node
def test_every_unit_main_then_backup_reads_its_own_else_the_shows():
    units = _js("N.units(A[0], A[1])", PROCS, {'subnet': '255.255.255.0', 'gateway': '10.0.0.1'})
    rows = [(u['key'], u['role'], u['name'], u['model'], u['ip'], u['subnet'], u['gateway'], u['note'])
            for u in units]
    assert rows == [
        ('p1:main', 'main', 'SX40 A', 'SX40', '10.0.0.10', '255.255.255.0', '10.0.0.1', 'control laptop port 2'),
        ('p1:bu', 'backup', 'SX40 A BU', 'SX40', '10.0.0.11', '255.255.0.0', '10.0.0.1', ''),
        ('p2:main', 'main', 'H9', 'H9', '', '255.255.255.0', '10.0.0.1', ''),
        ('p3:main', 'main', 'IMAG', 'MX40 Pro', '10.0.0.10', '255.255.255.0', '10.0.0.1', ''),
    ]
    # where the show's value stands in, and the unit's own fields as stored
    assert units[0]['shown'] == {'subnet': True, 'gateway': True}
    assert units[1]['shown'] == {'subnet': False, 'gateway': True}
    assert units[1]['own'] == {'ip': '10.0.0.11', 'subnet': '255.255.0.0', 'gateway': '', 'note': ''}
    # no show settings: a blank stays blank
    bare = _js("N.units(A[0], null)", PROCS)
    assert [u['subnet'] for u in bare] == ['', '255.255.0.0', '', '']
    assert _js("N.anyIp(N.units(A[0], {}))", PROCS) is True
    assert _js("N.anyIp(N.units(A[0], {subnet: '255.255.255.0'}))", [PROCS[1]]) is False


@needs_node
def test_a_designated_backup_processor_reads_as_a_backup():
    units = _js("N.units(A[0], {}, {backupOf: p => p.id === 'p3'})", PROCS)
    assert [(u['key'], u['role']) for u in units] == [
        ('p1:main', 'main'), ('p1:bu', 'backup'), ('p2:main', 'main'), ('p3:main', 'backup')]


@needs_node
def test_two_units_on_one_ip_are_named_together():
    dups = _js("N.duplicates(N.units(A[0], {}))", PROCS)
    assert [(d['ip'], [u['name'] for u in d['units']]) for d in dups] == [('10.0.0.10', ['SX40 A', 'IMAG'])]
    assert _js("N.duplicates(N.units(A[0], {})).map(N.duplicateText)", PROCS) == [
        'SX40 A and IMAG have the same IP, 10.0.0.10. Give each unit its own.']
    three = copy.deepcopy(PROCS)
    three[1]['network'] = {'ip': ' 10.0.0.10 '}
    assert _js("N.duplicates(N.units(A[0], {})).map(N.duplicateText)", three) == [
        'SX40 A, H9 and IMAG have the same IP, 10.0.0.10. Give each unit its own.']
    # blanks are never a shared IP
    none = [{'id': 'a', 'deviceName': 'S8'}, {'id': 'b', 'deviceName': 'S8'}]
    assert _js("N.duplicates(N.units(A[0], {}))", none) == []


# ── the routes ───────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _sx40(client, name='SX40 A'):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40', 'name': name}), 201)
    return st['processors'][-1]['id']


def _raw(client, pid):
    return next(p for p in client.get('/api/processors').get_json()['processors'] if p['id'] == pid)


def _res(client, pid):
    return next(p for p in client.get('/api/processors').get_json()['resolved'] if p['id'] == pid)


def test_a_units_network_is_a_patch_stored_as_typed(client):
    pid = _sx40(client)
    assert 'network' not in _raw(client, pid)
    assert _res(client, pid)['network'] == {}
    st = _ok(client.put(f'/api/processors/{pid}', json={'network': {'ip': ' 10.0.0.300 ', 'note': 'VLAN 20'}}))
    raw = next(p for p in st['processors'] if p['id'] == pid)
    # not an address, stored all the same (the field is marked, never refused)
    assert raw['network'] == {'ip': '10.0.0.300', 'note': 'VLAN 20'}
    assert next(p for p in st['resolved'] if p['id'] == pid)['network'] == raw['network']
    # one field at a time; the others kept
    _ok(client.put(f'/api/processors/{pid}', json={'network': {'ip': '10.0.0.10', 'gateway': '10.0.0.1'}}))
    assert _raw(client, pid)['network'] == {'ip': '10.0.0.10', 'note': 'VLAN 20', 'gateway': '10.0.0.1'}
    # a blank or null field goes, and the key with the last one
    _ok(client.put(f'/api/processors/{pid}', json={'network': {'note': '', 'gateway': None}}))
    assert _raw(client, pid)['network'] == {'ip': '10.0.0.10'}
    _ok(client.put(f'/api/processors/{pid}', json={'network': {'ip': '  '}}))
    assert 'network' not in _raw(client, pid)


def test_a_bad_shape_is_refused_and_nothing_is_written(client):
    pid = _sx40(client)
    _ok(client.put(f'/api/processors/{pid}', json={'network': {'ip': '10.0.0.10'}}))
    for body in ({'network': 'nope'}, {'network': {'ip': 5}}, {'network': {'mac': 'x'}},
                 {'network': {'note': 'x' * 201}}, {'name': 'X', 'network': {'ip': ['a']}}):
        resp = client.put(f'/api/processors/{pid}', json=body)
        assert resp.status_code == 400, body
    raw = _raw(client, pid)
    assert raw['network'] == {'ip': '10.0.0.10'} and raw['name'] == 'SX40 A', raw


def test_the_backup_units_network_rides_its_own_key_and_survives_a_rename(client):
    pid = _sx40(client)
    resp = client.put(f'/api/processors/{pid}', json={'backupNetwork': {'ip': '10.0.0.11'}})
    assert resp.status_code == 400 and 'no backup processor' in resp.get_json()['error']
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {}}))
    _ok(client.put(f'/api/processors/{pid}', json={'backupNetwork': {'ip': '10.0.0.11', 'subnet': '/24'}}))
    assert _raw(client, pid)['backupUnit'] == {'name': '', 'network': {'ip': '10.0.0.11', 'subnet': '/24'}}
    assert _res(client, pid)['backupUnit']['network'] == {'ip': '10.0.0.11', 'subnet': '/24'}
    # the main's own are untouched
    assert 'network' not in _raw(client, pid)
    # renamed, it keeps them
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {'name': 'SX40 A BU'}}))
    assert _raw(client, pid)['backupUnit'] == {'name': 'SX40 A BU',
                                               'network': {'ip': '10.0.0.11', 'subnet': '/24'}}
    # switched off, they go with it
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': None}))
    assert 'backupUnit' not in _raw(client, pid)


def test_the_shows_subnet_and_gateway_live_on_the_project(client):
    import app as app_module
    pid = _sx40(client)
    assert client.get('/api/processors').get_json()['network'] == {}
    st = _ok(client.put('/api/processors/network', json={'subnet': '255.255.255.0', 'gateway': '10.0.0.1'}))
    assert st['network'] == {'subnet': '255.255.255.0', 'gateway': '10.0.0.1'}
    assert app_module.current_project['network'] == st['network']
    assert client.get('/api/processors').get_json()['network'] == st['network']
    # the route is the show's, not a processor's
    assert 'network' not in _raw(client, pid)
    assert client.put('/api/processors/network', json={'ip': '10.0.0.1'}).status_code == 400
    assert client.put('/api/processors/network', json={'gateway': 3}).status_code == 400
    _ok(client.put('/api/processors/network', json={'gateway': ''}))
    assert app_module.current_project['network'] == {'subnet': '255.255.255.0'}
    _ok(client.put('/api/processors/network', json={'subnet': None}))
    assert 'network' not in app_module.current_project


def test_the_fields_round_trip_through_the_undo_and_file_funnel(client):
    pid = _sx40(client)
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {'name': 'BU'}}))
    _ok(client.put(f'/api/processors/{pid}', json={'network': {'ip': '10.0.0.10', 'note': 'port 2'}}))
    _ok(client.put(f'/api/processors/{pid}', json={'backupNetwork': {'ip': '10.0.0.11'}}))
    _ok(client.put('/api/processors/network', json={'subnet': '255.255.255.0'}))
    saved = copy.deepcopy(client.get('/api/project').get_json())
    _ok(client.post('/api/project/new'))
    assert 'network' not in client.get('/api/project').get_json()
    _ok(client.put('/api/project', json=saved))
    st = client.get('/api/processors').get_json()
    raw = next(p for p in st['processors'] if p['id'] == pid)
    assert raw['network'] == {'ip': '10.0.0.10', 'note': 'port 2'}
    assert raw['backupUnit'] == {'name': 'BU', 'network': {'ip': '10.0.0.11'}}
    assert st['network'] == {'subnet': '255.255.255.0'}
    res = next(p for p in st['resolved'] if p['id'] == pid)
    assert res['network'] == raw['network'] and res['backupUnit']['network'] == {'ip': '10.0.0.11'}
    # and through the save route too
    _ok(client.post('/api/project', json=saved))
    assert client.get('/api/processors').get_json()['network'] == {'subnet': '255.255.255.0'}


def test_a_show_without_them_opens_and_reads_unchanged(client):
    pid = _sx40(client)
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {}}))
    old = copy.deepcopy(client.get('/api/project').get_json())
    assert 'network' not in old
    assert 'network' not in old['processors'][0] and 'network' not in old['processors'][0]['backupUnit']
    _ok(client.put('/api/project', json=old))
    after = client.get('/api/project').get_json()
    assert 'network' not in after
    assert after['processors'] == old['processors']
    st = client.get('/api/processors').get_json()
    assert st['network'] == {}
    assert st['resolved'][0]['network'] == {} and st['resolved'][0]['backupUnit']['network'] == {}
    # a hand-edited broken entry reads as none and is never a crash
    broken = copy.deepcopy(old)
    broken['network'] = 'x'
    broken['processors'][0]['network'] = ['10.0.0.1']
    broken['processors'][0]['backupUnit']['network'] = {'ip': 7, 'note': 'kept'}
    _ok(client.put('/api/project', json=broken))
    st = client.get('/api/processors').get_json()
    assert st['network'] == {} and st['resolved'][0]['network'] == {}
    assert st['resolved'][0]['backupUnit']['network'] == {'note': 'kept'}
