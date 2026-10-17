"""Saved distro presets hold up (1.5 fixes): two saves at once both land,
a damaged presets file is kept rather than overwritten, an entry a newer
version wrote survives this version's saves, and a new save is checked
against the values the app can open - with the allow-lists pinned to the
browser's own constants so the two cannot drift apart.

Every test points the presets file at its own scratch path."""

import json
import os
import re
import threading

import pytest

import routes_distro_presets as rdp
from app import app

JS = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js')

BODY = {'system': '230/400', 'input': 'cee63', 'ratingA': 63, 'breakers100': False,
        'phasing': 'whole-ln', 'directPhasing': None,
        'rows': [{'id': 'r1', 'connector': 'soca', 'count': 3, 'coupling': 'ln',
                  'breakerA': 16, 'pairedWith': None}]}


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(autouse=True)
def presets_file(tmp_path, monkeypatch):
    path = str(tmp_path / 'distro_presets' / 'distro_presets.json')
    monkeypatch.setattr(rdp, 'DISTRO_PRESETS_FILE', path)
    return path


def _stored(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)['presets']


# ── two saves at once ─────────────────────────────────────────────────────

def test_parallel_saves_all_land_and_none_fails(presets_file):
    n = 16
    gate = threading.Barrier(n)
    codes = [None] * n

    def save(i):
        with app.test_client() as c:
            gate.wait()
            codes[i] = c.put('/api/distro-presets',
                             json={'name': f'Rack {i}', 'distro': BODY}).status_code

    threads = [threading.Thread(target=save, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200] * n, codes
    assert sorted(p['name'] for p in _stored(presets_file)) == sorted(f'Rack {i}' for i in range(n))
    # no temp file left behind
    assert os.listdir(os.path.dirname(presets_file)) == ['distro_presets.json']


# ── what is sent ──────────────────────────────────────────────────────────

def test_a_body_that_is_not_an_object_is_refused(client):
    for raw in ('[1, 2]', '"x"', '3', 'null'):
        r = client.put('/api/distro-presets', data=raw, content_type='application/json')
        assert r.status_code == 400, raw
        r = client.delete('/api/distro-presets', data=raw, content_type='application/json')
        assert r.status_code in (400, 404), raw


def test_values_the_app_cannot_open_are_refused(client, presets_file):
    row = BODY['rows'][0]
    bad = [
        dict(BODY, input='cam999'),
        dict(BODY, phasing='sideways'),
        dict(BODY, directPhasing='rotating'),
        dict(BODY, breakers100='yes'),
        dict(BODY, rows=[dict(row, connector='nema99')]),
        dict(BODY, rows=[dict(row, pairedWith='r' * 50)]),
        dict(BODY, system='240/415'),
    ]
    for distro in bad:
        r = client.put('/api/distro-presets', json={'name': 'A', 'distro': distro})
        assert r.status_code == 400, distro
        assert 'error' in r.get_json()
    assert not os.path.exists(presets_file)
    # the allowed empties
    for distro in (dict(BODY, input=None, phasing='', directPhasing=''),
                   dict(BODY, phasing=None, directPhasing='paired')):
        assert client.put('/api/distro-presets', json={'name': 'A', 'distro': distro}).status_code == 200


def test_unknown_keys_on_a_new_save_are_dropped_and_size_is_capped(client, presets_file):
    r = client.put('/api/distro-presets',
                   json={'name': 'A', 'distro': dict(BODY, extra='x' * 1000, notes=[1, 2])})
    assert r.status_code == 200
    assert _stored(presets_file)[0]['distro'] == BODY
    # a 100 KB body is not a preset
    r = client.put('/api/distro-presets',
                   json={'name': 'B', 'distro': dict(BODY, junk='x' * 100_000)})
    assert r.status_code == 413
    assert [p['name'] for p in _stored(presets_file)] == ['A']
    # the name cap holds
    assert client.put('/api/distro-presets',
                      json={'name': 'n' * (rdp.MAX_NAME + 1), 'distro': BODY}).status_code == 400


# ── what is stored ────────────────────────────────────────────────────────

def test_a_damaged_file_is_moved_aside_not_overwritten(client, presets_file):
    os.makedirs(os.path.dirname(presets_file), exist_ok=True)
    with open(presets_file, 'w', encoding='utf-8') as f:
        f.write('{"presets": [ {"name": "Half writ')
    assert client.get('/api/distro-presets').get_json() == {'presets': []}
    # deleting from it touches nothing
    assert client.delete('/api/distro-presets', json={'name': 'x'}).status_code == 404
    assert os.path.exists(presets_file)
    r = client.put('/api/distro-presets', json={'name': 'New', 'distro': BODY})
    assert r.status_code == 200
    folder = os.path.dirname(presets_file)
    aside = [n for n in os.listdir(folder) if n.startswith('distro_presets.json.corrupt-')]
    assert len(aside) == 1, os.listdir(folder)
    with open(os.path.join(folder, aside[0]), encoding='utf-8') as f:
        assert f.read() == '{"presets": [ {"name": "Half writ'
    assert [p['name'] for p in _stored(presets_file)] == ['New']


def test_entries_this_version_cannot_fully_read_survive_a_save(client, presets_file):
    newer = {'name': 'From a newer version',
             'distro': dict(BODY, system='230/400', futureField={'a': 1},
                            rows=[dict(BODY['rows'][0], connector='cee125', newRowKey=1)]),
             'tag': 'kept'}
    odd = {'something': 'else entirely'}
    os.makedirs(os.path.dirname(presets_file), exist_ok=True)
    with open(presets_file, 'w', encoding='utf-8') as f:
        json.dump({'presets': [newer, odd]}, f)
    assert client.put('/api/distro-presets', json={'name': 'Ours', 'distro': BODY}).status_code == 200
    assert client.delete('/api/distro-presets', json={'name': 'Ours'}).status_code == 200
    assert _stored(presets_file) == [newer, odd]
    # the browser is still offered the newer one by name (it cleans rows itself)
    assert [p['name'] for p in client.get('/api/distro-presets').get_json()['presets']] \
        == ['From a newer version']
    # and saving over it by name replaces it
    client.put('/api/distro-presets', json={'name': 'from a NEWER version', 'distro': BODY})
    assert _stored(presets_file) == [odd, {'name': 'from a NEWER version', 'distro': BODY}]


# ── the allow-lists match the browser ─────────────────────────────────────

def _read_js(name):
    with open(os.path.join(JS, name), encoding='utf-8') as f:
        return f.read()


def _block(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i)]


def _ids(block):
    return set(re.findall(r"\bid: '([^']+)'", block))


def test_the_server_allow_lists_match_the_browser_constants():
    ds = _read_js('app-distro-systems.js')
    pb = _read_js('app-phase-balance.js')
    assert rdp.SYSTEMS == _ids(_block(ds, 'export const DISTRO_SYSTEMS = [', '];'))
    assert rdp.CONNECTORS == _ids(_block(ds, 'export const DISTRO_CONNECTORS = [', '];'))
    assert rdp.INPUTS == _ids(_block(ds, 'export const DISTRO_INPUTS = [', '];'))
    whole = re.search(r"const WHOLE_MULTI_SCHEME = \{\s*id: '([^']+)'", ds).group(1)
    assert rdp.PHASINGS == _ids(_block(pb, 'powerPhasingSchemes() {', '].map(named)')) | {whole}
    assert rdp.DIRECT_PHASINGS == set(re.findall(r"directPhasing === '(\w+)'", ds))
    # what a preset carries, and a row's fields
    body = re.search(r'_distroPresetBody\(d\) \{\s*return \{(.*?)\};', ds, re.S).group(1)
    assert rdp.DISTRO_KEYS == set(re.findall(r'(\w+):', body))
    push = re.search(r'out\.push\(\{(.*?)\}\);', _block(ds, '_normalizeOutputRows(rows, sys) {',
                                                        'distroRows(d) {'), re.S).group(1)
    assert rdp.ROW_KEYS == {re.match(r'\s*(\w+)', part).group(1) for part in push.split(',')}
