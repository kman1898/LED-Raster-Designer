"""Saved distro presets on the server (1.5, owner ruling 2026-10-16: "users
can SAVE their own distros as presets, stored ... the way named layouts
are"). One JSON file beside the presets folder, shared by every client;
conftest points it at a scratch file for the session."""

import json
import os

import routes_distro_presets as rdp


def _clear():
    if os.path.exists(rdp.DISTRO_PRESETS_FILE):
        os.remove(rdp.DISTRO_PRESETS_FILE)


BODY = {'system': '230/400', 'input': 'cee63', 'ratingA': 63, 'breakers100': False,
        'phasing': 'whole-ln', 'directPhasing': None,
        'rows': [{'id': 'r1', 'connector': 'soca', 'count': 3, 'coupling': 'ln',
                  'breakerA': 16, 'pairedWith': None}]}


def test_save_list_replace_and_delete(client):
    _clear()
    assert client.get('/api/distro-presets').get_json() == {'presets': []}
    r = client.put('/api/distro-presets', json={'name': '  Our   rack ', 'distro': BODY})
    assert r.status_code == 200
    assert [p['name'] for p in r.get_json()['presets']] == ['Our rack']
    with open(rdp.DISTRO_PRESETS_FILE, encoding='utf-8') as f:
        assert json.load(f)['presets'][0]['distro'] == BODY
    # the same name, any case, replaces
    r = client.put('/api/distro-presets', json={'name': 'our RACK', 'distro': dict(BODY, ratingA=50)})
    presets = r.get_json()['presets']
    assert len(presets) == 1 and presets[0]['distro']['ratingA'] == 50
    r = client.delete('/api/distro-presets', json={'name': 'Our rack'})
    assert r.status_code == 200 and r.get_json()['presets'] == []
    assert client.delete('/api/distro-presets', json={'name': 'Our rack'}).status_code == 404


def test_what_could_not_be_a_distro_is_refused(client):
    _clear()
    bad = [
        {'name': '', 'distro': BODY},
        {'name': 'x' * 61, 'distro': BODY},
        {'name': 'A', 'distro': dict(BODY, system='220/380')},
        {'name': 'A', 'distro': dict(BODY, rows=[])},
        {'name': 'A', 'distro': dict(BODY, rows=[{'connector': 'soca', 'count': 0, 'coupling': 'ln'}])},
        {'name': 'A', 'distro': dict(BODY, rows=[{'connector': 'soca', 'count': 2, 'coupling': 'xx'}])},
        {'name': 'A', 'distro': dict(BODY, rows=[{'connector': 'soca', 'count': 2, 'coupling': 'ln',
                                                  'evil': 1}])},
        {'name': 'A', 'distro': 'nope'},
    ]
    for body in bad:
        assert client.put('/api/distro-presets', json=body).status_code == 400, body
    assert client.get('/api/distro-presets').get_json() == {'presets': []}


def test_a_damaged_file_reads_as_no_presets(client):
    os.makedirs(os.path.dirname(rdp.DISTRO_PRESETS_FILE), exist_ok=True)
    with open(rdp.DISTRO_PRESETS_FILE, 'w', encoding='utf-8') as f:
        f.write('{not json')
    assert client.get('/api/distro-presets').get_json() == {'presets': []}
    _clear()
