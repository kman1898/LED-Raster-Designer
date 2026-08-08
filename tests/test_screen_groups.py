"""Screen groups (v0.10.9) - data model, persistence and integrity.

A group makes a set of layers behave as one screen (a wall built from 1m JP5
cabinets AND 0.5m standard cabinets has to be two layers, because the grid is
uniform per layer). Step 1 is the model only:

    project['groups']  -> [{id, name, layer_ids: [...]}, ...]
    layer['group_id']  -> 'g1' | None

mirroring the multi-canvas model (project['canvases'] / layer['canvas_id']).

These tests cover three things:

* PERSISTENCE - group_id has to survive every path canvas_id survives, and be
  absent from the paths canvas_id is absent from (presets, duplicates).
* INTEGRITY - restore_project repairs a broken model, and because it runs on
  EVERY undo and file load, each repair must converge on the first pass.
* VALIDATION - the pure helper a later step's resolve dialog is driven from.
"""

import json

import pytest

import app as app_module


# ── helpers ───────────────────────────────────────────────────────────────

def _add_screen(client, name='S1', columns=4, rows=3, cw=128, ch=128, **extra):
    payload = {
        'name': name, 'columns': columns, 'rows': rows,
        'cabinet_width': cw, 'cabinet_height': ch,
    }
    payload.update(extra)
    resp = client.post('/api/layer/add', json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _get_project(client):
    resp = client.get('/api/project')
    assert resp.status_code == 200
    return resp.get_json()


def _put(client, project):
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _clean(project):
    p = json.loads(json.dumps(project))
    p.pop('_migration_notice', None)
    return p


def _group_of(project, group_id):
    return next((g for g in project.get('groups') or []
                 if g.get('id') == group_id), None)


def _layer(project, layer_id):
    return next(l for l in project['layers'] if l['id'] == layer_id)


def _grouped_project(client, member_count=2):
    """Two (or more) screens on the server, joined into one group, returned as
    the project dict the client would hold."""
    ids = [
        _add_screen(client, f'W{i}', offset_x=i * 600)['id']
        for i in range(member_count)
    ]
    group = app_module._create_group(app_module.current_project, ids, name='Wall')
    assert group is not None
    return _get_project(client), group['id'], ids


def _assert_idempotent(client, project, label):
    """PUT three times; runs 2 and 3 must be byte-identical to run 1."""
    r1 = _clean(_put(client, project))
    r2 = _clean(_put(client, r1))
    r3 = _clean(_put(client, r2))
    assert r2 == r1, (
        f'{label}: second restore changed the project\n'
        f'  1st groups: {json.dumps(r1.get("groups"), sort_keys=True)}\n'
        f'  2nd groups: {json.dumps(r2.get("groups"), sort_keys=True)}\n'
        f'  1st group_ids: {[l.get("group_id") for l in r1.get("layers", [])]}\n'
        f'  2nd group_ids: {[l.get("group_id") for l in r2.get("layers", [])]}'
    )
    assert r3 == r2, f'{label}: third restore drifted'
    return r1


# ── 1. THE MODEL ──────────────────────────────────────────────────────────

def test_new_project_has_an_empty_groups_array(client):
    resp = client.post('/api/project/new')
    assert resp.get_json()['groups'] == []


def test_fresh_screen_layer_is_in_no_group(client):
    layer = _add_screen(client, 'Solo')
    assert 'group_id' in layer, 'create_layer did not declare group_id'
    assert layer['group_id'] is None


def test_find_group(client):
    project, gid, _ = _grouped_project(client)
    assert app_module._find_group(project, gid)['name'] == 'Wall'
    assert app_module._find_group(project, 'nope') is None
    assert app_module._find_group({}, gid) is None
    assert app_module._find_group(None, gid) is None


def test_create_group_writes_both_sides(client):
    project, gid, ids = _grouped_project(client)
    assert _group_of(project, gid)['layer_ids'] == ids
    for lid in ids:
        assert _layer(project, lid)['group_id'] == gid


def test_create_group_refuses_fewer_than_two_real_layers(client):
    a = _add_screen(client, 'A')['id']
    project = app_module.current_project
    assert app_module._create_group(project, [a]) is None
    assert app_module._create_group(project, []) is None
    assert app_module._create_group(project, [a, 999]) is None, (
        'a group whose second member does not exist is a group of one')
    assert app_module._create_group(project, [a, a]) is None, (
        'the same layer twice is still one layer')
    assert project['groups'] == []
    assert _get_project(client)['layers'][0]['group_id'] is None


def test_group_ids_are_handed_out_in_order(client):
    ids = [_add_screen(client, f'S{i}')['id'] for i in range(4)]
    project = app_module.current_project
    g1 = app_module._create_group(project, ids[:2])
    g2 = app_module._create_group(project, ids[2:])
    assert (g1['id'], g2['id']) == ('g1', 'g2')
    assert project['next_group_seq'] == 3


def test_a_deleted_groups_id_is_never_handed_out_again(client):
    """The whole point of the counter. With a scan-for-max-suffix allocator,
    deleting g2 frees 'g2' and the next group takes it - and an undo that
    resurrects the deleted g2 then leaves two different groups answering to
    the same id."""
    ids = [_add_screen(client, f'S{i}')['id'] for i in range(4)]
    project = app_module.current_project
    app_module._create_group(project, ids[:2])
    g2 = app_module._create_group(project, ids[2:])
    project['groups'] = [g for g in project['groups'] if g['id'] != g2['id']]
    for lid in ids[2:]:
        _layer(project, lid)['group_id'] = None

    fresh = app_module._create_group(project, ids[2:])
    assert fresh['id'] == 'g3', 'a freed group id was reused'
    assert fresh['id'] != g2['id']


def test_the_counter_survives_a_project_round_trip(client):
    """Reuse would come straight back if the counter lived only in memory:
    the client PUTs the project back on every undo and file load."""
    project, gid, ids = _grouped_project(client)
    assert project['next_group_seq'] == 2
    restored = _put(client, _clean(project))
    assert restored['next_group_seq'] == 2

    # ...and a save/load cycle through a file carries it too.
    on_disk = json.loads(json.dumps(restored))
    client.post('/api/project/new')
    reloaded = _put(client, on_disk)
    assert reloaded['next_group_seq'] == 2
    assert app_module._next_group_id(app_module.current_project) == 'g2'


def test_deleting_a_member_does_not_free_the_groups_id(client):
    """The realistic route: the group dies because a member was deleted, which
    is exactly the state an undo can resurrect."""
    project, gid, ids = _grouped_project(client)
    after = client.delete(f'/api/layer/{ids[0]}').get_json()
    assert after['groups'] == []
    assert after['next_group_seq'] == 2, 'the dropped group freed its id'


def test_a_project_without_the_counter_seeds_it_above_its_groups(client):
    """Migration: a file written before the counter existed. Its highest group
    id sets the floor, so nothing already in the file is re-issued."""
    project, gid, ids = _grouped_project(client)
    legacy = _clean(project)
    legacy.pop('next_group_seq')
    legacy['groups'][0]['id'] = 'g7'
    for layer in legacy['layers']:
        if layer.get('group_id') == gid:
            layer['group_id'] = 'g7'

    restored = _put(client, legacy)
    assert restored['next_group_seq'] == 8
    assert _group_of(restored, 'g7')['layer_ids'] == ids


def test_a_counter_already_ahead_is_never_pulled_back(client):
    """Idempotence guard: restore runs on every undo, and a counter that
    walked backwards would start re-issuing ids mid-session."""
    project, gid, ids = _grouped_project(client)
    project['next_group_seq'] = 42
    restored = _put(client, project)
    assert restored['next_group_seq'] == 42
    _assert_idempotent(client, project, 'counter already ahead')


def test_counter_survives_junk(client):
    """A hand-edited or third-party file can carry anything here."""
    project, gid, ids = _grouped_project(client)
    for junk in (None, 'x', [], {'a': 1}, -5):
        broken = _broken(project, lambda p: p.__setitem__('next_group_seq', junk))
        restored = _put(client, broken)
        assert restored['next_group_seq'] == 2, f'junk {junk!r} broke the seed'
    assert app_module.sync_next_group_seq(None) == 1
    assert app_module.sync_next_group_seq('nope') == 1


# ── 2. PERSISTENCE - every path canvas_id survives ────────────────────────

def test_group_id_round_trips_through_per_layer_put(client):
    project, gid, ids = _grouped_project(client)
    # Exactly what the client does: PUT the whole layer object back.
    layer = _layer(project, ids[0])
    resp = client.put(f'/api/layer/{ids[0]}', json=layer)
    assert resp.status_code == 200
    assert resp.get_json()['group_id'] == gid, (
        'group_id dropped by the PUT whitelist - every layer save would '
        'silently leave the group')
    assert _get_project(client)['layers'][0]['group_id'] == gid


def test_per_layer_put_can_clear_group_id(client):
    project, gid, ids = _grouped_project(client)
    resp = client.put(f'/api/layer/{ids[0]}', json={'group_id': None})
    assert resp.get_json()['group_id'] is None


def test_group_id_round_trips_through_a_bulk_layer_save(client):
    """There is no bulk layer endpoint - the client's updateLayers() fans out
    one PUT per layer - so the bulk path is N per-layer PUTs. All of them must
    keep membership, not just the first."""
    project, gid, ids = _grouped_project(client, member_count=3)
    for lid in ids:
        resp = client.put(f'/api/layer/{lid}', json=_layer(project, lid))
        assert resp.status_code == 200
    after = _get_project(client)
    assert [l['group_id'] for l in after['layers']] == [gid] * 3
    assert _group_of(after, gid)['layer_ids'] == ids


def test_group_survives_post_api_project(client):
    """POST /api/project (save_project) is a wholesale update - the groups
    array has to come back out again."""
    project, gid, ids = _grouped_project(client)
    assert client.post('/api/project', json=project).status_code == 200
    after = _get_project(client)
    assert _group_of(after, gid)['layer_ids'] == ids


def test_group_survives_put_api_project(client):
    project, gid, ids = _grouped_project(client)
    restored = _put(client, project)
    assert _group_of(restored, gid)['layer_ids'] == ids
    assert [l['group_id'] for l in restored['layers']] == [gid, gid]


def test_group_survives_undo_redo(client):
    """Undo and redo are both PUT /api/project with an older snapshot."""
    project, gid, ids = _grouped_project(client)
    snapshot = _clean(project)
    _add_screen(client, 'Later')          # an edit to undo
    undone = _put(client, snapshot)       # undo
    assert _group_of(undone, gid)['layer_ids'] == ids
    redone = _put(client, _clean(_get_project(client)))  # redo
    assert _group_of(redone, gid)['layer_ids'] == ids


def test_group_survives_a_file_load(client):
    """File load = PUT /api/project with a payload the server never built."""
    project, gid, ids = _grouped_project(client)
    on_disk = json.loads(json.dumps(project))  # what save-to-file writes
    client.post('/api/project/new')            # simulate a restart
    loaded = _put(client, on_disk)
    assert _group_of(loaded, gid)['layer_ids'] == ids
    for lid in ids:
        assert _layer(loaded, lid)['group_id'] == gid


def test_grouped_project_restore_is_idempotent(client):
    project, _, _ = _grouped_project(client, member_count=3)
    _assert_idempotent(client, project, 'healthy group')


# ── 3. PERSISTENCE - paths group membership must NOT travel ───────────────

def test_add_layer_does_not_accept_group_id(client):
    """Nothing in the add payload can enrol a new screen in a group; joining
    is an explicit action, not a side effect of creating a layer."""
    project, gid, ids = _grouped_project(client)
    created = _add_screen(client, 'Sneaky', group_id=gid)
    assert created['group_id'] is None
    assert _group_of(_get_project(client), gid)['layer_ids'] == ids


def test_a_duplicate_does_not_join_the_group(client):
    """The client's duplicate/paste payload carries no group_id (see
    app-history.js), and the server would ignore it anyway."""
    project, gid, ids = _grouped_project(client)
    source = _layer(project, ids[0])
    payload = {k: v for k, v in source.items()
               if k not in ('id', 'panels', 'group_id')}
    payload['name'] = 'W0 copy'
    clone = client.post('/api/layer/add', json=payload).get_json()
    assert clone['group_id'] is None
    after = _get_project(client)
    assert _group_of(after, gid)['layer_ids'] == ids, 'group grew on duplicate'
    assert _layer(after, ids[0])['group_id'] == gid, 'source lost its group'


def test_cross_canvas_duplicate_does_not_carry_group_id(client):
    """/api/layer/<id>/canvas?mode=duplicate deep-copies the layer, so it
    would carry group_id into a group that does not list it."""
    project, gid, ids = _grouped_project(client)
    target = client.post('/api/canvas', json={}).get_json()['canvases'][-1]['id']
    resp = client.put(f'/api/layer/{ids[0]}/canvas',
                      json={'canvas_id': target, 'mode': 'duplicate'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = resp.get_json()
    clone = after['layers'][-1]
    assert clone['canvas_id'] == target
    assert clone['group_id'] is None
    assert _group_of(after, gid)['layer_ids'] == ids


def test_a_new_sibling_screen_does_not_inherit_group_membership(client):
    """_seed_data_with_canvas_defaults copies the donor's hardware settings
    onto a new screen in the same canvas. Group membership is structural, not
    a setting, so it must NOT be in that inheritable tuple."""
    project, gid, ids = _grouped_project(client)
    # The donor (most recent screen in the canvas) is a group member and has
    # a distinctive setting, so we can prove seeding ran at all.
    client.put(f'/api/layer/{ids[-1]}', json={'panelWatts': 333})
    fresh = _add_screen(client, 'Next')
    assert fresh['panelWatts'] == 333, 'canvas seeding did not run'
    assert fresh['group_id'] is None, 'a new sibling was silently grouped'
    assert _group_of(_get_project(client), gid)['layer_ids'] == ids


def test_deleting_a_member_leaves_no_stale_membership(client):
    """A two-member group loses a member -> the group is gone and the
    survivor is ungrouped, in the delete response itself."""
    project, gid, ids = _grouped_project(client)
    after = client.delete(f'/api/layer/{ids[0]}').get_json()
    assert _group_of(after, gid) is None
    assert _layer(after, ids[1])['group_id'] is None


# ── 4. INTEGRITY - each rule proven to actually fire, and to converge ──────

def _broken(project, mutate):
    """Deep-copy a project and break it, so the fixture stays reusable."""
    p = json.loads(json.dumps(project))
    mutate(p)
    return p


def test_rule1_prunes_layer_ids_for_deleted_layers(client):
    project, gid, ids = _grouped_project(client, member_count=3)

    def _break(p):
        p['layers'] = [l for l in p['layers'] if l['id'] != ids[2]]
        # layer_ids still names the deleted layer
        assert ids[2] in _group_of(p, gid)['layer_ids']

    broken = _broken(project, _break)
    restored = _put(client, broken)
    assert _group_of(restored, gid)['layer_ids'] == ids[:2]
    _assert_idempotent(client, broken, 'rule1 prune')


def test_rule2_drops_a_group_of_one_and_ungroups_its_layer(client):
    project, gid, ids = _grouped_project(client)

    def _break(p):
        _group_of(p, gid)['layer_ids'] = [ids[0]]

    broken = _broken(project, _break)
    restored = _put(client, broken)
    assert _group_of(restored, gid) is None, 'a group of one survived'
    assert restored['groups'] == []
    assert _layer(restored, ids[0])['group_id'] is None
    assert _layer(restored, ids[1])['group_id'] is None
    _assert_idempotent(client, broken, 'rule2 group of one')


def test_rule2_fires_via_a_deleted_layer_too(client):
    """The realistic route into a group of one: delete a member out of a
    two-member group, in a snapshot the client PUTs back."""
    project, gid, ids = _grouped_project(client)
    broken = _broken(project, lambda p: p.__setitem__(
        'layers', [l for l in p['layers'] if l['id'] != ids[1]]))
    restored = _put(client, broken)
    assert restored['groups'] == []
    assert _layer(restored, ids[0])['group_id'] is None
    _assert_idempotent(client, broken, 'rule2 via delete')


def test_rule3_clears_a_group_id_naming_a_missing_group(client):
    project, gid, ids = _grouped_project(client)
    broken = _broken(project, lambda p: p.__setitem__('groups', []))
    restored = _put(client, broken)
    assert [l['group_id'] for l in restored['layers']] == [None, None]
    _assert_idempotent(client, broken, 'rule3 dangling group_id')


def test_rule3_clears_a_group_id_the_group_does_not_list(client):
    """The other half of rule 3: the group exists but has never heard of this
    layer. layer_ids is the authoritative side, so the layer is ungrouped."""
    project, gid, ids = _grouped_project(client)
    outsider = _add_screen(client, 'Outsider')['id']
    project = _get_project(client)

    def _break(p):
        _layer(p, outsider)['group_id'] = gid

    broken = _broken(project, _break)
    restored = _put(client, broken)
    assert _layer(restored, outsider)['group_id'] is None
    assert _group_of(restored, gid)['layer_ids'] == ids
    _assert_idempotent(client, broken, 'rule3 not-a-member')


def test_rule4_keeps_the_first_group_when_a_layer_is_listed_twice(client):
    ids = [_add_screen(client, f'S{i}', offset_x=i * 600)['id'] for i in range(4)]
    live = app_module.current_project
    app_module._create_group(live, ids[:2], name='Left')
    app_module._create_group(live, ids[2:], name='Right')
    project = _get_project(client)

    def _break(p):
        # The second group now also claims a layer the first one owns.
        p['groups'][1]['layer_ids'] = [ids[0]] + p['groups'][1]['layer_ids']
        assert ids[0] in p['groups'][0]['layer_ids']

    broken = _broken(project, _break)
    restored = _put(client, broken)
    first, second = restored['groups']
    assert ids[0] in first['layer_ids'], 'first group did not keep the layer'
    assert ids[0] not in second['layer_ids'], 'layer left in two groups'
    assert _layer(restored, ids[0])['group_id'] == first['id']
    _assert_idempotent(client, broken, 'rule4 double membership')


def test_rule4_does_not_let_a_group_of_one_starve_a_real_group(client):
    """Ordering trap: a one-member group listed FIRST must not claim the
    layer on its way to being dropped, or the real group behind it collapses
    too and the user loses a wall they built."""
    project, gid, ids = _grouped_project(client)

    def _break(p):
        p['groups'].insert(0, {'id': 'gX', 'name': 'Stub',
                               'layer_ids': [ids[0]]})

    broken = _broken(project, _break)
    restored = _put(client, broken)
    assert [g['id'] for g in restored['groups']] == [gid]
    assert _group_of(restored, gid)['layer_ids'] == ids
    _assert_idempotent(client, broken, 'rule4 vs rule2 ordering')


def test_rule5_two_groups_sharing_an_id_are_given_distinct_ids(client):
    """Rule 4 is enforced per LAYER, so it never noticed two DIFFERENT groups
    both called 'g1'. Both survived, all four layers mirrored 'g1', _find_group
    resolved it to the first and _export_units keyed groups by id into a dict -
    last duplicate won, so one whole wall vanished from the export and its
    screens were drawn under the other wall's name."""
    ids = [_add_screen(client, f'S{i}', offset_x=i * 600)['id'] for i in range(4)]
    project = _get_project(client)

    def _break(p):
        p['groups'] = [
            {'id': 'g1', 'name': 'Wall A', 'layer_ids': ids[:2]},
            {'id': 'g1', 'name': 'Wall B', 'layer_ids': ids[2:]},
        ]
        for lid in ids:
            _layer(p, lid)['group_id'] = 'g1'

    broken = _broken(project, _break)
    restored = _put(client, broken)
    gids = [g['id'] for g in restored['groups']]
    assert len(gids) == 2 and len(set(gids)) == 2, gids
    assert gids[0] == 'g1'          # the first claimant keeps the id
    assert _group_of(restored, gids[1])['layer_ids'] == ids[2:]
    assert _layer(restored, ids[2])['group_id'] == gids[1]
    # Both walls reach the export, with their own members and their own names.
    units = app_module._export_units(restored, restored['layers'])
    assert [u[0] for u in units] == ['Wall A', 'Wall B']
    assert [len(u[1]) for u in units] == [2, 2]
    _assert_idempotent(client, broken, 'rule5 duplicate group id')


@pytest.mark.parametrize('bad', [
    {'nested': 1},      # a dict where a layer id belongs
    [2],                # a list
])
def test_an_unhashable_id_does_not_500_the_restore(client, bad):
    """Every membership test runs against a SET, so a dict or a list where an
    id belongs raised TypeError - a 500 on PUT /api/project, i.e. on every
    undo, redo and file open of such a file. The guards checked the CONTAINER's
    type, never the ELEMENT's."""
    project, gid, ids = _grouped_project(client)

    def _break(p):
        _group_of(p, gid)['layer_ids'] = list(ids) + [bad]
        _layer(p, ids[0])['customPortPaths'] = {
            '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': bad}]}

    broken = _broken(project, _break)
    restored = _put(client, broken)
    assert _group_of(restored, gid)['layer_ids'] == ids
    assert _layer(restored, ids[0])['customPortPaths'] == {
        '1': [{'row': 0, 'col': 0}]}
    _assert_idempotent(client, broken, 'unhashable id')


def test_an_unhashable_layer_id_does_not_500_the_restore(client):
    project, gid, ids = _grouped_project(client)
    broken = _broken(project, lambda p: _layer(p, ids[0]).__setitem__(
        'id', {'oops': 1}))
    resp = client.put('/api/project', json=broken)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    # The layer can no longer be named, so the group is left with one member
    # and dissolves - the same outcome as a deleted member.
    assert resp.get_json()['groups'] == []


def test_post_save_repairs_the_group_model_too(client):
    """POST /api/project is not just "save as" - every sidebar reorder goes
    through it with the whole layers array - and it used to merge the payload
    with no repair at all."""
    a = _add_screen(client, 'A')['id']
    b = _add_screen(client, 'B', offset_x=600)['id']
    resp = client.post('/api/project', json={
        'groups': [{'id': 'g1', 'name': 'W', 'layer_ids': [a, b, 99999]}],
    })
    assert resp.status_code == 200
    out = _get_project(client)
    assert out['groups'] == [{'id': 'g1', 'name': 'W', 'layer_ids': [a, b]}]
    assert _layer(out, a)['group_id'] == 'g1'      # the mirror IS written
    assert _layer(out, b)['group_id'] == 'g1'


def test_put_layer_will_not_invent_a_group(client):
    """group_id is the one whitelisted field that names another object, and it
    was taken on trust: a layer could claim membership of a group that does not
    exist and the export then built a unit around it."""
    a = _add_screen(client, 'A')['id']
    resp = client.put(f'/api/layer/{a}', json={'group_id': 'g-nope'})
    assert resp.status_code == 200
    assert resp.get_json().get('group_id') is None
    assert _layer(_get_project(client), a).get('group_id') is None


def test_put_layer_joins_a_real_group_on_both_sides(client):
    project, gid, ids = _grouped_project(client)
    loose = _add_screen(client, 'Loose', offset_x=2000)['id']
    assert client.put(f'/api/layer/{loose}',
                      json={'group_id': gid}).status_code == 200
    out = _get_project(client)
    assert _layer(out, loose)['group_id'] == gid
    assert _group_of(out, gid)['layer_ids'] == list(ids) + [loose]
    # null leaves on both sides
    assert client.put(f'/api/layer/{loose}',
                      json={'group_id': None}).status_code == 200
    out = _get_project(client)
    assert _layer(out, loose)['group_id'] is None
    assert _group_of(out, gid)['layer_ids'] == list(ids)


def test_duplicate_layer_id_inside_one_group_is_deduped(client):
    project, gid, ids = _grouped_project(client)
    broken = _broken(project, lambda p: _group_of(p, gid).__setitem__(
        'layer_ids', [ids[0], ids[0], ids[1]]))
    restored = _put(client, broken)
    assert _group_of(restored, gid)['layer_ids'] == ids
    _assert_idempotent(client, broken, 'dup member id')


MALFORMED_GROUPS = {
    'groups_missing': None,
    'groups_null': None,
    'groups_not_a_list': {'g1': ['a']},
    'group_not_a_dict': ['nonsense'],
    'group_without_id': [{'name': 'X', 'layer_ids': [1, 2]}],
    'group_without_layer_ids': [{'id': 'g1', 'name': 'X'}],
    'group_layer_ids_null': [{'id': 'g1', 'name': 'X', 'layer_ids': None}],
    'group_layer_ids_not_a_list': [{'id': 'g1', 'name': 'X', 'layer_ids': 7}],
    'unknown_layer_ids': [{'id': 'g1', 'name': 'X', 'layer_ids': [98, 99]}],
}


@pytest.mark.parametrize('name', sorted(MALFORMED_GROUPS))
def test_malformed_groups_do_not_500_and_converge(client, name):
    project, _, _ = _grouped_project(client)
    broken = json.loads(json.dumps(project))
    if name == 'groups_missing':
        broken.pop('groups')
    else:
        broken['groups'] = MALFORMED_GROUPS[name]
    resp = client.put('/api/project', json=broken)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert isinstance(resp.get_json()['groups'], list)
    _assert_idempotent(client, broken, name)


def test_group_layer_ids_not_a_list_does_not_crash_on_a_string(client):
    """A JSON string is iterable, which would silently produce one-character
    'layer ids' rather than an error. It must simply yield no members."""
    project, gid, _ = _grouped_project(client)
    broken = _broken(project, lambda p: _group_of(p, gid).__setitem__(
        'layer_ids', 'abc'))
    restored = _put(client, broken)
    assert restored['groups'] == []


def test_integrity_helper_is_a_no_op_on_junk(client):
    for junk in (None, [], 'x', 42):
        assert app_module._enforce_group_integrity(junk) == junk


# ── 5. LEGACY PROJECTS (no groups key) LOAD UNCHANGED ─────────────────────

def test_pre_group_project_layers_are_byte_identical_after_restore(client):
    """A project saved before groups existed must come back with its layers
    untouched - no group_id key invented on any of them."""
    _add_screen(client, 'A', columns=3, rows=2)
    _add_screen(client, 'B', columns=2, rows=2, offset_x=500)
    client.post('/api/layer/add-text', json={'name': 'Note', 'textContent': 'x'})
    # One restore first, so the unrelated backfills restore_project performs
    # (showOffsetX/Y on the text layer) are already applied and cannot be
    # mistaken for a group-related change below.
    _put(client, _get_project(client))
    legacy = _clean(_get_project(client))
    legacy.pop('groups')
    for layer in legacy['layers']:
        layer.pop('group_id', None)

    restored = _clean(_put(client, legacy))
    assert json.dumps(restored['layers'], sort_keys=True) == \
        json.dumps(legacy['layers'], sort_keys=True), (
            'restoring a pre-groups project changed its layers')
    for layer in restored['layers']:
        assert 'group_id' not in layer, (
            f"layer {layer['id']} had group_id invented on load")
    # The project itself gains the empty array, same as the canvas migrator
    # gives a v0.7 file a canvases array.
    assert restored['groups'] == []
    _assert_idempotent(client, legacy, 'legacy pre-groups project')


def test_pre_group_project_with_a_hand_written_group_id_is_cleared(client):
    """Hand-edited / third-party file: a layer claims membership but the file
    has no groups array at all."""
    _add_screen(client, 'A')
    legacy = _clean(_get_project(client))
    legacy.pop('groups')
    legacy['layers'][0]['group_id'] = 'g7'
    restored = _put(client, legacy)
    assert restored['layers'][0]['group_id'] is None
    assert restored['groups'] == []


# ── 6. THE VALIDATION HELPER ──────────────────────────────────────────────

def _l(**kw):
    return dict(kw)


def test_validate_all_match():
    layers = [_l(processorType='brompton', bitDepth=10, frameRate=60)] * 3
    assert app_module.validate_group_settings(layers) == {
        'ok': True, 'conflicts': {}}


def test_validate_one_field_differs():
    result = app_module.validate_group_settings([
        _l(processorType='brompton', bitDepth=10, frameRate=60),
        _l(processorType='brompton', bitDepth=12, frameRate=60),
    ])
    assert result['ok'] is False
    assert result['conflicts'] == {'bitDepth': [10, 12]}


def test_validate_several_fields_differ():
    result = app_module.validate_group_settings([
        _l(processorType='brompton', bitDepth=10, frameRate=60),
        _l(processorType='novastar-armor', bitDepth=12, frameRate=60),
        _l(processorType='megapixel', bitDepth=12, frameRate=50),
    ])
    assert result['ok'] is False
    assert result['conflicts'] == {
        'processorType': ['brompton', 'novastar-armor', 'megapixel'],
        'bitDepth': [10, 12],
        'frameRate': [60, 50],
    }, 'distinct values must arrive in first-seen order, ready for a dialog'


def test_validate_single_layer_always_agrees():
    result = app_module.validate_group_settings(
        [_l(processorType='brompton', bitDepth=10, frameRate=60)])
    assert result == {'ok': True, 'conflicts': {}}


def test_validate_empty_set_agrees():
    assert app_module.validate_group_settings([]) == {'ok': True, 'conflicts': {}}
    assert app_module.validate_group_settings(None) == {'ok': True, 'conflicts': {}}


def test_validate_layers_missing_the_fields_entirely():
    """Two layers that both predate the field agree with each other."""
    assert app_module.validate_group_settings([_l(name='A'), _l(name='B')]) == {
        'ok': True, 'conflicts': {}}


def test_validate_a_missing_field_conflicts_with_a_set_one():
    """One layer on Brompton and one with no processorType at all genuinely
    do not agree - the second would fall back to a different default."""
    result = app_module.validate_group_settings([
        _l(processorType='brompton', bitDepth=10, frameRate=60),
        _l(bitDepth=10, frameRate=60),
    ])
    assert result['conflicts'] == {'processorType': ['brompton', None]}


def test_validate_ignores_non_dict_entries():
    assert app_module.validate_group_settings([None, 'x', 7])['ok'] is True


def test_validate_reads_the_real_layers_of_a_group(client):
    """End to end against server-built layers, which is how a later step will
    call it: same defaults agree, a changed processor does not."""
    project, gid, ids = _grouped_project(client)
    members = [_layer(project, lid) for lid in ids]
    assert app_module.validate_group_settings(members)['ok'] is True
    client.put(f'/api/layer/{ids[0]}', json={'processorType': 'brompton'})
    client.put(f'/api/layer/{ids[1]}', json={'processorType': 'megapixel'})
    project = _get_project(client)
    result = app_module.validate_group_settings(
        [_layer(project, lid) for lid in ids])
    assert result['ok'] is False
    assert result['conflicts'] == {'processorType': ['brompton', 'megapixel']}


def test_validate_does_not_mutate_its_input():
    layers = [_l(processorType='brompton'), _l(processorType='megapixel')]
    before = json.dumps(layers, sort_keys=True)
    app_module.validate_group_settings(layers)
    assert json.dumps(layers, sort_keys=True) == before
