"""Every screen carries a breakout its voltage allows - on the server too.

User ruling, 2026-09-22: "screens need to be set to true1 or powercon or
edison. they have to be set", and the default is a Preferences setting:
"if 208 is default then True1 is default, but that should be set in
preferences". Three rounds of testing kept finding one more client entry
point that stored a bare or ineligible breakout, so the invariant now lives
on the server as well (app.normalize_power_breakout), on every route that
stores or serves a screen layer:

    POST /api/layer/add            PUT /api/layer/<id>
    POST /api/project              PUT /api/project (file load, undo/redo)
    POST /api/project/new          POST /api/canvas/<id>/duplicate
    PUT /api/layer/<id>/canvas     GET /api/project

The write-in order, identical on both sides: a stored ELIGIBLE choice
stands; else the Preferences breakout (server_preferences['breakoutType'] /
prefs.breakoutType) when the screen's voltage allows it; else the voltage
class default - Edison at or below 120 V, True1 above (and for a blank
voltage). Eligibility: at 0 < V <= 120 True1 / powerCON / Edison; above
120 V no Edison; l2130-* at exactly 208 V; a blank or non-numeric voltage
restricts only the L21-30.

The oracle below (EXPECT / _eligible) is written out as a table on purpose
- it never calls the code under test - and every route is driven with
every (voltage, stored breakout) pair: voltages {0, '', 'abc', 100, 110,
120, 121, 200, 208, 230} against {absent, '', 'junk', each of the six
ids}.

The last two tests pin the client to the server: the shipped preference
literal in app-preferences.js is the server's PREF_DEFAULT_BREAKOUT, the
JS catalog ids are POWER_BREAKOUT_IDS, and every JS write of powerVoltage /
powerBreakoutType goes through setScreenVoltage / normalizePowerBreakout
or a gated helper named here - a new write path fails this file.

Run locally:
    python3 -m pytest tests/test_breakout_invariant.py -q
"""
import copy
import os
import re

import pytest

import app as app_module

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')

IDS = ('soca-true1', 'soca-powercon', 'soca-edison', 'soca-l620',
       'l2130-true1', 'l2130-powercon')
LOW = ('soca-true1', 'soca-powercon', 'soca-edison')
VOLTAGES = (0, '', 'abc', 100, 110, 120, 121, 200, 208, 230)
ABSENT = object()
STORED = (ABSENT, '', 'junk') + IDS
PREFS = (ABSENT, '', 'junk') + IDS


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave app.current_project and app.server_preferences as found. The
    e2e server's guard, not the Flask one: the last test here opens a page
    on that server, and the snapshot has to be taken after the server has
    seeded its project or the restore would hand the next browser suite a
    bare one."""


@pytest.fixture()
def prefs():
    """Set server_preferences for one test; the module guard restores."""
    saved = copy.deepcopy(app_module.server_preferences)

    def _set(breakout=ABSENT):
        app_module.server_preferences = {} if breakout is ABSENT else {'breakoutType': breakout}
    _set()
    yield _set
    app_module.server_preferences = saved


# ── the oracle ──────────────────────────────────────────────────────────

def _volts(v):
    if isinstance(v, bool):
        return 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0


def _eligible(bid, voltage):
    v = _volts(voltage)
    if bid not in IDS:
        return False
    if 0 < v <= 120:
        return bid in LOW
    if bid == 'soca-edison':
        return v <= 0
    if bid.startswith('l2130-'):
        return v == 208
    return True


def _class_default(voltage):
    v = _volts(voltage)
    return 'soca-edison' if 0 < v <= 120 else 'soca-true1'


def EXPECT(voltage, stored, pref=ABSENT):
    """What the store must hold afterwards."""
    if stored is not ABSENT and _eligible(stored, voltage):
        return stored
    want = 'soca-true1' if pref is ABSENT else pref   # the shipped preference
    if _eligible(want, voltage):
        return want
    return _class_default(voltage)


def _fields(voltage, stored):
    d = {'powerVoltage': voltage}
    if stored is not ABSENT:
        d['powerBreakoutType'] = stored
    return d


def _layer(client, layer_id):
    p = client.get('/api/project').get_json()
    return next(l for l in p['layers'] if l['id'] == layer_id)


def _add(client, **fields):
    body = {'name': 'S', 'columns': 2, 'rows': 2, 'cabinet_width': 100,
            'cabinet_height': 100}
    body.update(fields)
    r = client.post('/api/layer/add', json=body)
    assert r.status_code == 200, r.data
    return r.get_json()


def test_the_oracle_is_the_ruling():
    """The table above says what the ruling says (a sanity check on the
    test itself, so a typo in the oracle cannot pass the code)."""
    assert _eligible('soca-edison', 110) and _eligible('soca-edison', 120)
    assert not _eligible('soca-edison', 121) and not _eligible('soca-edison', 208)
    assert _eligible('soca-edison', 0) and _eligible('soca-edison', 'abc')
    assert _eligible('l2130-true1', 208) and not _eligible('l2130-true1', 200)
    assert not _eligible('l2130-powercon', 0) and not _eligible('l2130-powercon', 120)
    assert _eligible('soca-l620', 121) and _eligible('soca-l620', 0)
    assert not _eligible('soca-l620', 120) and not _eligible('soca-l620', 100)
    assert _eligible('soca-true1', 100) and _eligible('soca-powercon', 230)
    assert not _eligible('junk', 208) and not _eligible('', 110)
    assert EXPECT(110, ABSENT) == 'soca-true1'          # the shipped preference
    assert EXPECT(110, ABSENT, 'l2130-true1') == 'soca-edison'
    assert EXPECT(208, ABSENT, 'l2130-true1') == 'l2130-true1'
    assert EXPECT(230, 'soca-edison', 'soca-edison') == 'soca-true1'
    assert EXPECT(120, 'soca-powercon', 'soca-edison') == 'soca-powercon'


# ── the helper itself ───────────────────────────────────────────────────

@pytest.mark.parametrize('pref', PREFS, ids=lambda p: 'absent' if p is ABSENT else (p or 'blank'))
def test_normalize_power_breakout_follows_the_write_in_order(prefs, pref):
    prefs(pref)
    for voltage in VOLTAGES:
        for stored in STORED:
            layer = {'type': 'screen', **_fields(voltage, stored)}
            wrote = app_module.normalize_power_breakout(layer)
            want = EXPECT(voltage, stored, pref)
            assert layer['powerBreakoutType'] == want, (voltage, stored, pref, layer)
            assert _eligible(layer['powerBreakoutType'], voltage), (voltage, stored, pref, layer)
            stood = stored is not ABSENT and _eligible(stored, voltage)
            assert wrote is (not stood), (voltage, stored, pref, wrote)
            # idempotent
            assert app_module.normalize_power_breakout(layer) is False
    # never a non-screen layer
    for kind in ('image', 'text'):
        other = {'type': kind, 'powerVoltage': 208, 'powerBreakoutType': 'soca-edison'}
        assert app_module.normalize_power_breakout(other) is False
        assert other['powerBreakoutType'] == 'soca-edison'
    assert app_module.normalize_power_breakout(None) is False


def test_a_bool_voltage_reads_as_blank(prefs):
    """JS parseFloat(true) is NaN; Python float(True) is 1.0. Both sides
    read a bool as no voltage (only the L21-30 restricted)."""
    prefs('l2130-true1')
    layer = {'powerVoltage': True, 'powerBreakoutType': 'l2130-true1'}
    app_module.normalize_power_breakout(layer)
    assert layer['powerBreakoutType'] == 'soca-true1', layer
    layer = {'powerVoltage': True, 'powerBreakoutType': 'soca-edison'}
    assert app_module.normalize_power_breakout(layer) is False


# ── every route, every pair ─────────────────────────────────────────────

@pytest.mark.parametrize('pref', (ABSENT, 'soca-powercon', 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'powercon', 'l2130', 'edison'))
def test_layer_add_stores_an_eligible_breakout(client, prefs, pref):
    prefs(pref)
    for voltage in VOLTAGES:
        for stored in STORED:
            made = _add(client, **_fields(voltage, stored))
            want = EXPECT(voltage, stored, pref)
            assert made['powerBreakoutType'] == want, (voltage, stored, pref, made['powerBreakoutType'])
            assert _layer(client, made['id'])['powerBreakoutType'] == want


def test_layer_add_with_no_voltage_at_all_takes_the_default_voltage_rung(client, prefs):
    """No powerVoltage in the payload: create_layer's 110 V stands, and
    the breakout follows it (the preference when it runs at 110 V)."""
    prefs('l2130-powercon')
    made = _add(client)
    assert (made['powerVoltage'], made['powerBreakoutType']) == (110, 'soca-edison'), made
    prefs('soca-powercon')
    made = _add(client)
    assert (made['powerVoltage'], made['powerBreakoutType']) == (110, 'soca-powercon'), made


@pytest.mark.parametrize('pref', (ABSENT, 'soca-powercon', 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'powercon', 'l2130', 'edison'))
def test_layer_put_keeps_the_breakout_eligible(client, prefs, pref):
    prefs(pref)
    made = _add(client, powerVoltage=208, powerBreakoutType='l2130-true1')
    lid = made['id']
    for voltage in VOLTAGES:
        for stored in STORED:
            # start from a known eligible pair so the PUT is the thing under test
            client.put(f'/api/layer/{lid}', json={'powerVoltage': 208, 'powerBreakoutType': 'l2130-true1'})
            r = client.put(f'/api/layer/{lid}', json=_fields(voltage, stored))
            assert r.status_code == 200, r.data
            got = r.get_json()['powerBreakoutType']
            # a PUT that names no breakout keeps the L21-30 only where it is eligible
            want = EXPECT(voltage, 'l2130-true1' if stored is ABSENT else stored, pref)
            assert got == want, (voltage, stored, pref, got)
            assert _layer(client, lid)['powerBreakoutType'] == want
    # a voltage-only PUT on an eligible choice leaves it alone
    client.put(f'/api/layer/{lid}', json={'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon'})
    r = client.put(f'/api/layer/{lid}', json={'powerVoltage': 230})
    assert r.get_json()['powerBreakoutType'] == 'soca-powercon'
    # ... and rewrites one the new voltage refuses
    r = client.put(f'/api/layer/{lid}', json={'powerBreakoutType': 'soca-edison', 'powerVoltage': 120})
    assert r.get_json()['powerBreakoutType'] == 'soca-edison'
    r = client.put(f'/api/layer/{lid}', json={'powerVoltage': 208})
    assert r.get_json()['powerBreakoutType'] == EXPECT(208, 'soca-edison', pref)


@pytest.mark.parametrize('route', ('POST', 'PUT'))
@pytest.mark.parametrize('pref', (ABSENT, 'soca-powercon', 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'powercon', 'l2130', 'edison'))
def test_project_save_and_restore_heal_every_screen(client, prefs, pref, route):
    prefs(pref)
    made = _add(client, powerVoltage=208)
    lid = made['id']
    base = client.get('/api/project').get_json()
    for voltage in VOLTAGES:
        for stored in STORED:
            proj = copy.deepcopy(base)
            layer = next(l for l in proj['layers'] if l['id'] == lid)
            layer.pop('powerBreakoutType', None)
            layer.update(_fields(voltage, stored))
            if route == 'POST':
                r = client.post('/api/project', json=proj)
            else:
                r = client.put('/api/project', json=proj)
            assert r.status_code == 200, (route, r.data)
            want = EXPECT(voltage, stored, pref)
            assert _layer(client, lid)['powerBreakoutType'] == want, (route, voltage, stored, pref)
            if route == 'PUT':
                echoed = next(l for l in r.get_json()['layers'] if l['id'] == lid)
                assert echoed['powerBreakoutType'] == want, (voltage, stored, pref, echoed['powerBreakoutType'])


def test_a_new_project_s_default_screen_carries_one(client, prefs):
    prefs('l2130-true1')
    r = client.post('/api/project/new')
    layer = r.get_json()['layers'][0]
    assert (layer['powerVoltage'], layer['powerBreakoutType']) == (110, 'soca-edison'), layer
    prefs('soca-powercon')
    r = client.post('/api/project/new')
    layer = r.get_json()['layers'][0]
    assert layer['powerBreakoutType'] == 'soca-powercon', layer
    prefs()
    r = client.post('/api/project/new')
    assert r.get_json()['layers'][0]['powerBreakoutType'] == 'soca-true1'


def _corrupt(lid, voltage, stored):
    """Write straight into the store, past every route, the way a stale
    client or a hand-edited file would."""
    layer = next(l for l in app_module.current_project['layers'] if l['id'] == lid)
    layer.pop('powerBreakoutType', None)
    layer.update(_fields(voltage, stored))
    return layer


@pytest.mark.parametrize('pref', (ABSENT, 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'l2130', 'edison'))
def test_canvas_duplicate_clones_carry_an_eligible_breakout(client, prefs, pref):
    prefs(pref)
    made = _add(client, powerVoltage=208)
    lid = made['id']
    canvas_id = made['canvas_id']
    for voltage in VOLTAGES:
        for stored in STORED:
            _corrupt(lid, voltage, stored)
            r = client.post(f'/api/canvas/{canvas_id}/duplicate')
            assert r.status_code == 200, r.data
            proj = r.get_json()
            new_canvas = proj['active_canvas_id']
            clones = [l for l in proj['layers'] if l.get('canvas_id') == new_canvas]
            assert len(clones) == 1, (voltage, stored, [l['id'] for l in clones])
            want = EXPECT(voltage, stored, pref)
            assert clones[0]['powerBreakoutType'] == want, (voltage, stored, pref, clones[0]['powerBreakoutType'])
            client.delete(f'/api/canvas/{new_canvas}')
            client.put(f'/api/canvas/{canvas_id}/active')


@pytest.mark.parametrize('pref', (ABSENT, 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'l2130', 'edison'))
def test_layer_duplicate_to_another_canvas_carries_an_eligible_breakout(client, prefs, pref):
    prefs(pref)
    made = _add(client, powerVoltage=208)
    lid = made['id']
    other = client.post('/api/canvas', json={'name': 'Two'}).get_json()
    canvases = other.get('canvases') or other.get('project', {}).get('canvases')
    target = [c for c in canvases if c.get('name') == 'Two'][0]['id']
    for voltage in VOLTAGES:
        for stored in STORED:
            _corrupt(lid, voltage, stored)
            r = client.put(f'/api/layer/{lid}/canvas', json={'canvas_id': target, 'mode': 'duplicate'})
            assert r.status_code == 200, r.data
            proj = r.get_json()
            clone = max((l for l in proj['layers'] if l['id'] != lid), key=lambda l: l['id'])
            want = EXPECT(voltage, stored, pref)
            assert clone['powerBreakoutType'] == want, (voltage, stored, pref, clone['powerBreakoutType'])
            client.delete(f'/api/layer/{clone["id"]}')


@pytest.mark.parametrize('pref', (ABSENT, 'l2130-true1', 'soca-edison'),
                         ids=('absent', 'l2130', 'edison'))
def test_get_never_hands_back_an_ineligible_breakout(client, prefs, pref):
    prefs(pref)
    made = _add(client, powerVoltage=208)
    lid = made['id']
    for voltage in VOLTAGES:
        for stored in STORED:
            _corrupt(lid, voltage, stored)
            got = _layer(client, lid)['powerBreakoutType']
            assert got == EXPECT(voltage, stored, pref), (voltage, stored, pref, got)
            assert _eligible(got, voltage)


def test_the_preferences_route_does_not_rewrite_an_eligible_choice(client, prefs):
    """Changing the breakout preference is for screens that lack one: a
    stored eligible choice on an existing screen stands."""
    prefs()
    made = _add(client, powerVoltage=120, powerBreakoutType='soca-edison')
    client.put('/api/preferences', json={'breakoutType': 'soca-powercon'})
    assert _layer(client, made['id'])['powerBreakoutType'] == 'soca-edison'
    # ... and reaches the next screen that needs one
    made2 = _add(client, powerVoltage=120)
    assert made2['powerBreakoutType'] == 'soca-powercon'


# ── the client and the server agree ─────────────────────────────────────

def _read(name):
    with open(os.path.join(JS_DIR, name), encoding='utf-8') as fh:
        return fh.read()


def test_the_shipped_preference_and_the_catalog_match_the_client():
    prefs_src = _read('app-preferences.js')
    m = re.search(r"^\s*breakoutType:\s*'([^']+)',", prefs_src, re.M)
    assert m, 'getPreferencesDefaults().breakoutType not found'
    assert m.group(1) == app_module.PREF_DEFAULT_BREAKOUT
    power_src = _read('app-power.js')
    start = power_src.index('getPowerBreakoutTypes() {')
    body = power_src[start:power_src.index('\n    }', start)]
    ids = re.findall(r"\{\s*id:\s*'([^']+)'", body)
    assert tuple(ids) == app_module.POWER_BREAKOUT_IDS, ids
    # the class default the client writes is the server's
    assert "types.find(t => t.id === 'soca-edison')" in power_src
    assert app_module.default_power_breakout(120) == 'soca-edison'
    assert app_module.default_power_breakout(121) == 'soca-true1'


# The JS source contract: every write of a screen's voltage or breakout is
# either inside one of these helpers or is followed within WINDOW lines by
# a normalize / setScreenVoltage call. A helper listed as gated must read
# _breakoutEligible itself.
WINDOW = 6
METHOD_RE = re.compile(r'^\s{4}(async\s+)?([A-Za-z_$][\w$]*)\s*\(')
VOLT_WRITE_RE = re.compile(r'\.powerVoltage\s*=(?!=)')
BREAKOUT_WRITE_RE = re.compile(r'\.powerBreakoutType\s*=(?!=)')
VOLT_KEY_RE = re.compile(r'(?<![\w$.])powerVoltage\s*:\s*(?P<rhs>.*)$')
COVER_RE = re.compile(r'\b(normalizePowerBreakout|setScreenVoltage)\s*\(')
HELPERS = {
    # (file, enclosing method): 'gated' (reads _breakoutEligible) or 'normalizer'
    ('app-power.js', 'setScreenVoltage'): 'normalizer',
    ('app-power.js', 'normalizePowerBreakout'): 'normalizer',
    ('app-power.js', 'setPowerBreakout'): 'gated',
    ('app-power.js', '_wireScreenPowerKnobs'): 'gated',
    ('app-core.js', 'applyNewScreenPowerPreferences'): 'gated',
    # writes the client-props snapshot (not a layer); the re-fetch loop
    # that puts it back normalizes every layer it lands on
    ('app-screen-info.js', 'deleteLayer'): 'normalizer',
}
# app-preferences.js holds the preference record (prefs.powerVoltage), not
# a screen: its `powerVoltage:` keys are never a layer write.
NOT_LAYER_FILES = {'app-preferences.js'}


def _enclosing_method(lines, idx):
    for i in range(idx, -1, -1):
        m = METHOD_RE.match(lines[i])
        if m and not lines[i].startswith('     '):
            return m.group(2)
    return None


def _covered(lines, idx):
    return any(COVER_RE.search(lines[j]) for j in range(idx, min(len(lines), idx + WINDOW + 1)))


def _method_body(lines, idx):
    start = idx
    while start >= 0 and not (METHOD_RE.match(lines[start]) and not lines[start].startswith('     ')):
        start -= 1
    end = idx
    while end < len(lines) and not lines[end].startswith('    }'):
        end += 1
    return '\n'.join(lines[start:end + 1])


def test_every_js_write_path_goes_through_the_helpers():
    offenders = []
    seen_helpers = set()
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js'):
            continue
        lines = _read(name).split('\n')
        for idx, line in enumerate(lines):
            code = line.split('//')[0]
            is_write = VOLT_WRITE_RE.search(code) or BREAKOUT_WRITE_RE.search(code)
            key = None if name in NOT_LAYER_FILES else VOLT_KEY_RE.search(code)
            if key:
                rhs = key.group('rhs').strip()
                # a copy of another object's voltage, or a label / id string,
                # is not a write of a screen's voltage
                if re.search(r'\.powerVoltage\b', rhs) or rhs[:1] in ("'", '"', '`'):
                    key = None
            if not is_write and not key:
                continue
            method = _enclosing_method(lines, idx)
            kind = HELPERS.get((name, method))
            if kind:
                seen_helpers.add((name, method))
                if kind == 'gated':
                    assert '_breakoutEligible(' in _method_body(lines, idx), (name, method, 'not gated')
                continue
            if _covered(lines, idx):
                continue
            offenders.append(f'{name}:{idx + 1}: {line.strip()}')
    assert not offenders, (
        'a screen voltage / breakout is written outside setScreenVoltage / '
        'normalizePowerBreakout and nothing normalizes within '
        f'{WINDOW} lines:\n  ' + '\n  '.join(offenders))
    missing = set(HELPERS) - seen_helpers
    assert not missing, f'HELPERS names methods that no longer write: {sorted(missing)}'


def test_set_screen_voltage_is_the_one_voltage_writer():
    """Every bare `.powerVoltage =` in the front end is either the helper
    itself or the one Preferences overlay that normalizes on the next
    line - the list is closed."""
    bare = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js'):
            continue
        for idx, line in enumerate(_read(name).split('\n')):
            if VOLT_WRITE_RE.search(line.split('//')[0]):
                bare.append((name, _enclosing_method(_read(name).split('\n'), idx)))
    assert sorted(set(bare)) == [
        ('app-core.js', 'applyPreferencesToCurrentLayer'),
        ('app-power.js', 'setScreenVoltage'),
    ], bare


# ── one voltage reader on both sides ────────────────────────────────────
#
# PUT /api/layer/<id> with powerVoltage '208V' and l2130-true1 stored the
# True1 while the client kept the L21-30 (2026-09-23): the server read the
# figure with float() - '208V' raised, so 0 - and the client with
# parseFloat, which reads the leading number. One table, hand-written,
# drives both readers: app._power_voltage_number below and, in the last
# test, the page's app.voltageNumber over the very same entries. The
# oracle values are what JavaScript parseFloat gives (checked against node),
# with a non-finite result and anything that is not a string or a number
# read as no voltage on both sides.

VOLTAGE_TABLE = [
    # (value, what both sides read)
    ('208', 208), ('208V', 208), ('208 V', 208), ('208,0', 208), (' 208', 208),
    ('\t208', 208), (' 208', 208), (' 208', 208), ('﻿208', 208),
    ('\x1c208', 0),                       # \x1c is Python \s, not JS whitespace
    ('208\n', 208), ('\n208', 208), ('2 08', 2),
    ('+208', 208), ('-208', -208), ('- 208', 0), ('--208', 0), ('+-208', 0),
    ('1_000', 1),                         # no underscores
    ('Infinity', 0), ('+Infinity', 0), ('-Infinity', 0), ('Infinityx', 0),
    ('infinity', 0), ('1e400', 0), ('1' + '0' * 400, 0),   # not finite: no voltage
    ('1e2', 100), ('1E2', 100), ('1e-1', 0.1), ('1.2e1V', 12),
    ('.5', 0.5), ('5.', 5), ('1e', 1), ('1e+', 1),
    ('120abc', 120), ('1.2.3', 1.2), ('1,5', 1), ('00208', 208), ('0208.50', 208.5),
    ('0x10', 0), ('0b1', 0),              # a hex / binary prefix is 0, not 16 / 1
    ('abc', 0), ('', 0), ('   ', 0), ('NaN', 0),
    ('١٢٣', 0), ('٢08', 0), ('12٣', 12),   # ASCII digits only
    (208, 208), (208.0, 208), (120.5, 120.5), (0, 0), (-5, -5), (1e21, 1e21),
    (True, 0), (False, 0), (None, 0),
    ([208], 0), (['208'], 0), ([208, 1], 0), ([], 0), ({}, 0), ({'v': 208}, 0),
]
VOLTAGE_INPUTS = [v for v, _ in VOLTAGE_TABLE]
VOLTAGE_EXPECT = [want for _, want in VOLTAGE_TABLE]


def test_the_server_reads_a_voltage_the_way_parsefloat_does():
    got = [app_module._power_voltage_number(v) for v in VOLTAGE_INPUTS]
    bad = [(v, g, w) for v, g, w in zip(VOLTAGE_INPUTS, got, VOLTAGE_EXPECT) if g != w]
    assert not bad, bad
    assert all(isinstance(g, float) for g in got)
    # and the figure decides the breakout: '208V' is 208, so the L21-30 stands
    for voltage in ('208V', '208 V', '208,0', ' 208', '+208'):
        layer = {'powerVoltage': voltage, 'powerBreakoutType': 'l2130-true1'}
        assert app_module.normalize_power_breakout(layer) is False, voltage
    for voltage in ('Infinity', '1e400', [208], ['208'], '1_000'):
        layer = {'powerVoltage': voltage, 'powerBreakoutType': 'l2130-true1'}
        assert app_module.normalize_power_breakout(layer) is True, voltage
        assert layer['powerBreakoutType'] == 'soca-true1', (voltage, layer)


def test_the_add_route_normalizes_at_the_request_s_voltage_not_the_donor_s(client, prefs):
    """Preferences at 120 V with a breakout the catalog does not know, and
    a 208 V screen already on the canvas: a request that names 120 V lands
    at 120 V on Edison (the class default), not on the True1 the donor's
    208 V would give, and the donor's custom figure is not inherited beside
    the request's voltage."""
    app_module.server_preferences = {'powerVoltage': 120, 'breakoutType': 'junk'}
    donor = _add(client, powerVoltage=208, powerVoltageCustom=208)
    assert (donor['powerVoltage'], donor['powerBreakoutType']) == (208, 'soca-true1'), donor
    # a request naming no voltage inherits the donor's (the canvas is a
    # preset bucket), and the breakout follows THAT figure
    made = _add(client)
    assert (made['powerVoltage'], made['powerBreakoutType']) == (208, 'soca-true1'), made
    # one naming 120 V is normalized at 120 V, whatever the donor runs at
    made = _add(client, powerVoltage=120)
    assert (made['powerVoltage'], made['powerBreakoutType']) == (120, 'soca-edison'), made
    assert made.get('powerVoltageCustom') != 208, made.get('powerVoltageCustom')
    assert _layer(client, made['id'])['powerBreakoutType'] == 'soca-edison'


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """A page on the e2e server with one 208 V screen of its own (the Flask
    tests above leave the shared project bare)."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        made = c.post('/api/layer/add', json={
            'name': 'Reader', 'columns': 2, 'rows': 2, 'cabinet_width': 100,
            'cabinet_height': 100, 'powerVoltage': 208}).get_json()
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e) + '\n' + str(getattr(e, 'stack', ''))))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, made['id'], errors
    context.close()


def test_the_client_reads_the_same_table_the_server_does(page):
    """The page's voltageNumber over the table above gives, entry for
    entry, what app._power_voltage_number gave; a non-finite figure is no
    voltage class on the client (before, parseFloat('Infinity') put a
    screen in the 208 class); and the breakout the two sides settle on for
    every entry - the client's normalizePowerBreakout on a probe against
    PUT /api/layer/<id> on the server - is the same one."""
    pg, layer_id, errors = page
    # the same preference on both sides (the module guard restores the server's)
    pg.evaluate("""async () => {
        const app = window.app;
        const prefs = { ...app.getPreferences(), breakoutType: 'l2130-true1' };
        app._serverPreferences = prefs;
        try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (e) {}
        await fetch('/api/preferences', { method: 'PUT',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(prefs) });
    }""")
    assert app_module.server_preferences.get('breakoutType') == 'l2130-true1'
    server = [app_module._power_voltage_number(v) for v in VOLTAGE_INPUTS]
    assert server == VOLTAGE_EXPECT
    client_read = pg.evaluate("(table) => table.map(v => window.app.voltageNumber(v))", VOLTAGE_INPUTS)
    bad = [(v, c, s) for v, c, s in zip(VOLTAGE_INPUTS, client_read, server) if c != s]
    assert not bad, bad
    classes = pg.evaluate("""() => ['Infinity', '1e400', '-Infinity', 'Infinityx'].map(v => [
        window.app._voltageClass(v), window.app._breakoutEligible({ id: 'soca-edison' }, v)])""")
    assert classes == [[None, True]] * 4, classes
    # the breakout each side stores for each entry, with the L21-30 stored
    # and preferred: the same answer everywhere, and '208V' keeps the box
    settled = pg.evaluate("""async ([id, table]) => {
        const app = window.app;
        const out = [];
        for (const v of table) {
            const probe = { type: 'screen', powerVoltage: v, powerBreakoutType: 'l2130-true1' };
            app.normalizePowerBreakout(probe);
            const srv = await (await fetch(`/api/layer/${id}`, { method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ powerVoltage: v, powerBreakoutType: 'l2130-true1' }) })).json();
            out.push([probe.powerBreakoutType, srv.powerBreakoutType]);
        }
        return out;
    }""", [layer_id, VOLTAGE_INPUTS])
    disagree = [(v, c, s) for v, (c, s) in zip(VOLTAGE_INPUTS, settled) if c != s]
    assert not disagree, disagree
    want = ['l2130-true1' if w == 208 else ('soca-edison' if 0 < w <= 120 else 'soca-true1')
            for w in VOLTAGE_EXPECT]
    assert [c for c, _ in settled] == want, list(zip(VOLTAGE_INPUTS, settled, want))
    assert errors == [], errors
