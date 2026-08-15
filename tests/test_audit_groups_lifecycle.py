"""ADVERSARIAL AUDIT (throwaway) - screen groups data model + lifecycle.

Not part of the shipped suite. Written to try to BREAK the v0.11.0 group
model, not to document it.
"""

import copy
import json

import pytest

import app as app_module


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(flask_project_guard):
    """Leave the shared project globals exactly as this module found them -
    the `client` fixture rebuilds them per test, so whatever this module's
    LAST test built is what the live e2e server would serve for the rest of
    the session (see conftest.flask_project_guard)."""


# ── helpers ───────────────────────────────────────────────────────────────

def _add(client, name='S', **extra):
    payload = {'name': name, 'columns': 4, 'rows': 3,
               'cabinet_width': 128, 'cabinet_height': 128}
    payload.update(extra)
    r = client.post('/api/layer/add', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _proj(client):
    r = client.get('/api/project')
    assert r.status_code == 200
    return r.get_json()


def _put(client, project):
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


def _layer(p, lid):
    return next(l for l in p['layers'] if l['id'] == lid)


def _mk_group(p, ids, gid='g1', name='Wall'):
    p.setdefault('groups', []).append(
        {'id': gid, 'name': name, 'layer_ids': list(ids)})
    for lid in ids:
        _layer(p, lid)['group_id'] = gid
    return p


def _strip(p):
    """Compare-able view: drop the transient bits restore always rewrites."""
    q = copy.deepcopy(p)
    q.pop('_migration_notice', None)
    return q


# ══════════════════════════════════════════════════════════════════════════
# 1. degenerate inputs must never 500
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('groups', [
    'notalist',
    123,
    None,
    [None],
    [123],
    ['g1'],
    [{}],
    [{'id': None, 'layer_ids': [1, 2]}],
    [{'id': '', 'layer_ids': [1, 2]}],
    [{'id': 'g1'}],
    [{'id': 'g1', 'layer_ids': 'ab'}],
    [{'id': 'g1', 'layer_ids': 7}],
    [{'id': 'g1', 'layer_ids': None}],
    [{'id': 'g1', 'layer_ids': [1, 1, 1]}],
    [{'id': 'g1', 'layer_ids': [999, 1000]}],
    [{'id': 'g1', 'layer_ids': [1, 2]}, {'id': 'g1', 'layer_ids': [1, 2]}],
])
def test_hostile_groups_never_500(client, groups):
    _add(client, 'A')
    _add(client, 'B')
    p = _proj(client)
    p['groups'] = groups
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:600]
    out = r.get_json()
    assert isinstance(out['groups'], list)


@pytest.mark.parametrize('bad', [
    [{'nested': 1}],           # dict inside layer_ids
    [[2]],                     # list inside layer_ids
    [{'a': 1}, 2],
])
def test_unhashable_layer_id_in_group_500s(client, bad):
    """CONFIRMED 500: `lid in existing_layer_ids` against a SET raises
    TypeError for any unhashable member id."""
    _add(client, 'A'); _add(client, 'B')
    p = _proj(client)
    p['groups'] = [{'id': 'g1', 'name': 'W', 'layer_ids': bad}]
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]


def test_unhashable_layer_id_on_a_layer_500s(client):
    a = _add(client, 'A')['id']
    _add(client, 'B')
    p = _proj(client)
    _layer(p, a)['id'] = {'oops': 1}
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]


def test_unhashable_layerid_in_a_path_step_500s(client):
    """Same class of bug one function down, in _prune_cross_layer_paths:
    `target not in existing_layer_ids`."""
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _mk_group(_proj(client), [a, b])
    _layer(p, a)['customPortPaths'] = {
        '1': [{'row': 0, 'col': 0, 'layerId': {'bad': 1}}]}
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]


@pytest.mark.parametrize('seq', ['x', None, -5, 1.7, [], {'a': 1}])
def test_hostile_next_group_seq_never_500(client, seq):
    _add(client, 'A'); _add(client, 'B')
    p = _proj(client)
    p['next_group_seq'] = seq
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:600]


def test_hostile_paths_never_500(client):
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _mk_group(_proj(client), [a, b])
    _layer(p, a)['customPortPaths'] = {
        '1': 'notalist',
        '2': [None, 5, 'x', {'layerId': b}, {'row': 0, 'col': 0, 'layerId': None}],
        '3': {'nope': 1},
    }
    _layer(p, a)['powerCustomPaths'] = 'garbage'
    r = client.put('/api/project', json=p)
    assert r.status_code == 200, r.get_data(as_text=True)[:600]


# ══════════════════════════════════════════════════════════════════════════
# 2. duplicate group ids  --  the mirror is allowed to lie
# ══════════════════════════════════════════════════════════════════════════

def test_two_groups_sharing_an_id_are_given_distinct_ids(client):
    """WAS: two DISTINCT groups both called g1 survived the repair unchanged.

    Rule 4 ("group_id is single-valued") was enforced per LAYER, never per
    GROUP ID, so all four layers ended up with group_id 'g1' while groups[0]
    listed only two of them. Every consumer resolved 'g1' to the FIRST match,
    so members 3+4 reported as belonging to a group that did not list them -
    and it was STABLE, so no number of restores converged.

    NOW rule 5 re-issues the second claimant a fresh id from the project
    counter. Both walls survive with their own members: which of two colliding
    groups is "the real g1" is unknowable, and dropping one would silently
    destroy a grouping the user made.
    """
    ids = [_add(client, f'S{i}')['id'] for i in range(4)]
    p = _proj(client)
    p['groups'] = [
        {'id': 'g1', 'name': 'Wall A', 'layer_ids': [ids[0], ids[1]]},
        {'id': 'g1', 'name': 'Wall B', 'layer_ids': [ids[2], ids[3]]},
    ]
    for lid in ids[:2]:
        _layer(p, lid)['group_id'] = 'g1'
    for lid in ids[2:]:
        _layer(p, lid)['group_id'] = 'g1'
    out = _put(client, p)

    gids = [g['id'] for g in out['groups']]
    assert len(gids) == 2 and len(set(gids)) == 2, gids
    assert gids[0] == 'g1'                       # first claimant keeps the id
    assert gids[1] not in ('g1', None) and gids[1]
    # both sides agree, for both walls
    assert app_module._find_group(out, 'g1')['name'] == 'Wall A'
    assert app_module._find_group(out, gids[1])['name'] == 'Wall B'
    assert _layer(out, ids[0])['group_id'] == 'g1'
    assert _layer(out, ids[2])['group_id'] == gids[1]
    assert out['groups'][1]['layer_ids'] == [ids[2], ids[3]]
    # and it CONVERGES - a second restore changes nothing at all
    out2 = _put(client, out)
    assert [g['id'] for g in out2['groups']] == gids
    assert out2['groups'] == out['groups']


def test_groups_that_shared_an_id_export_as_two_units(client):
    """WAS: the duplicate-id drift reached the export as one unit of four
    members. _export_units keyed groups by id into a dict, so the LAST
    duplicate won - Wall A disappeared entirely and its two screens were
    exported inside a single unit carrying Wall B's name.
    """
    ids = [_add(client, f'S{i}')['id'] for i in range(4)]
    p = _proj(client)
    p['groups'] = [
        {'id': 'g1', 'name': 'Wall A', 'layer_ids': [ids[0], ids[1]]},
        {'id': 'g1', 'name': 'Wall B', 'layer_ids': [ids[2], ids[3]]},
    ]
    for lid in ids:
        _layer(p, lid)['group_id'] = 'g1'
    out = _put(client, p)
    units = app_module._export_units(out, out['layers'])
    assert [u[0] for u in units] == ['Wall A', 'Wall B']
    assert [len(u[1]) for u in units] == [2, 2]
    assert [[l['id'] for l in u[1]] for u in units] == [ids[:2], ids[2:]]


# ══════════════════════════════════════════════════════════════════════════
# 3. a layer claimed by two DIFFERENT groups
# ══════════════════════════════════════════════════════════════════════════

def test_layer_in_two_groups_starves_the_second_group(client):
    ids = [_add(client, f'S{i}')['id'] for i in range(3)]
    p = _proj(client)
    p['groups'] = [
        {'id': 'g1', 'name': 'A', 'layer_ids': [ids[0], ids[1]]},
        {'id': 'g2', 'name': 'B', 'layer_ids': [ids[1], ids[2]]},
    ]
    for lid in ids:
        _layer(p, lid)['group_id'] = 'g2'
    out = _put(client, p)
    assert [g['id'] for g in out['groups']] == ['g1']
    assert _layer(out, ids[2])['group_id'] is None
    assert _layer(out, ids[1])['group_id'] == 'g1'


# ══════════════════════════════════════════════════════════════════════════
# 4. next_group_seq / id reuse
# ══════════════════════════════════════════════════════════════════════════

def test_seq_never_lowers_across_restores(client):
    _add(client, 'A'); _add(client, 'B')
    p = _proj(client)
    p['next_group_seq'] = 50
    out = _put(client, p)
    assert out['next_group_seq'] == 50
    out['next_group_seq'] = 2          # client hands back an OLD counter
    out2 = _put(client, out)
    # a lower stored counter with no groups present IS accepted
    assert out2['next_group_seq'] == 2


def test_undo_to_a_stale_counter_can_hand_out_a_live_id(client):
    """A snapshot taken before a group existed carries the OLD counter.

    Restoring it lowers next_group_seq back below an id that a LATER
    snapshot still uses, so the two histories can both mint the same id.
    """
    ids = [_add(client, f'S{i}')['id'] for i in range(4)]
    p0 = _proj(client)                       # seq = 1, no groups
    assert p0['next_group_seq'] == 1

    p1 = _mk_group(copy.deepcopy(p0), ids[:2], gid='g1')
    p1['next_group_seq'] = 2
    _put(client, p1)

    # undo back to p0
    back = _put(client, copy.deepcopy(p0))
    assert back['next_group_seq'] == 1, back['next_group_seq']
    # the freed id g1 is handed straight back out
    assert app_module._next_group_id(app_module.current_project) == 'g1'


def test_next_group_id_is_unique_within_one_project(client):
    _add(client, 'A'); _add(client, 'B')
    p = _proj(client)
    seen = {app_module._next_group_id(p) for _ in range(200)}
    assert len(seen) == 200


# ══════════════════════════════════════════════════════════════════════════
# 5. lifecycle: delete member / delete canvas / duplicate canvas / move
# ══════════════════════════════════════════════════════════════════════════

def _wired_pair(client):
    """Two grouped screens with a port path crossing from A onto B."""
    a = _add(client, 'A')['id']
    b = _add(client, 'B', offset_x=600)['id']
    p = _mk_group(_proj(client), [a, b])
    _layer(p, a)['customPortPaths'] = {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}]}
    _layer(p, a)['powerCustomPaths'] = {
        '1': [{'row': 1, 'col': 0}, {'row': 1, 'col': 1, 'layerId': b}]}
    return _put(client, p), a, b


def test_delete_member_dissolves_group_and_prunes_paths(client):
    p, a, b = _wired_pair(client)
    r = client.delete(f'/api/layer/{b}')
    assert r.status_code == 200
    out = r.get_json()
    assert out['groups'] == []
    assert _layer(out, a)['group_id'] is None
    # the CROSS step goes; the owner's own step stays (documented behaviour)
    assert _layer(out, a).get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}
    assert _layer(out, a).get('powerCustomPaths') == {'1': [{'row': 1, 'col': 0}]}


def test_three_member_group_survives_one_delete(client):
    ids = [_add(client, f'S{i}', offset_x=600 * i)['id'] for i in range(3)]
    p = _mk_group(_proj(client), ids)
    _layer(p, ids[0])['customPortPaths'] = {
        '1': [{'row': 0, 'col': 0},
              {'row': 0, 'col': 1, 'layerId': ids[1]},
              {'row': 0, 'col': 2, 'layerId': ids[2]}]}
    _put(client, p)
    out = client.delete(f'/api/layer/{ids[2]}').get_json()
    assert [g['layer_ids'] for g in out['groups']] == [[ids[0], ids[1]]]
    steps = _layer(out, ids[0])['customPortPaths']['1']
    assert steps == [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': ids[1]}]


def test_delete_canvas_holding_one_member(client):
    p, a, b = _wired_pair(client)
    c2 = client.post('/api/canvas', json={}).get_json()
    c2id = c2['active_canvas_id']
    assert client.put(f'/api/layer/{b}/canvas',
                      json={'canvas_id': c2id, 'mode': 'move'}).status_code == 200
    out = client.delete(f'/api/canvas/{c2id}').get_json()
    assert out['groups'] == []
    # the CROSS step goes; the owner's own step stays (documented behaviour)
    assert _layer(out, a).get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}


def test_move_member_to_another_canvas_takes_it_out_of_the_group(client):
    """WAS: the route left membership alone and never ran the integrity pass,
    so a group ended up spanning two canvases, still carrying a cross-member
    path step pointing at a peer in another workspace - a step the client's own
    canPathReachLayer refuses to draw.

    NOW: a group is one physical wall driven by one canvas, so moving a member
    off it takes the member out of the wall. The two-member group is left with
    one and dissolves, and the undrawable step goes with it.
    """
    p, a, b = _wired_pair(client)
    c2id = client.post('/api/canvas', json={}).get_json()['active_canvas_id']
    out = client.put(f'/api/layer/{b}/canvas',
                     json={'canvas_id': c2id, 'mode': 'move'}).get_json()
    assert out['groups'] == []
    assert _layer(out, a)['group_id'] is None
    assert _layer(out, b)['group_id'] is None
    assert _layer(out, a)['canvas_id'] != _layer(out, b)['canvas_id']
    # the owner's own step stays; the cross step is gone, in the FIRST response
    assert _layer(out, a).get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}
    # and a restore does not resurrect anything
    out2 = _put(client, out)
    assert out2['groups'] == []
    assert _layer(out2, a).get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}


def test_moving_a_whole_group_to_another_canvas_keeps_it_together(client):
    """Only a group that WOULD be split is broken up. Move every member and
    the wall arrives on the new canvas intact, wiring and all."""
    p, a, b = _wired_pair(client)
    c2id = client.post('/api/canvas', json={}).get_json()['active_canvas_id']
    client.put(f'/api/layer/{b}/canvas', json={'canvas_id': c2id, 'mode': 'move'})
    # a rejoins b: b is already the only other member and it is on c2
    p2 = _proj(client)
    _mk_group(p2, [a, b])
    _layer(p2, a)['customPortPaths'] = {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}]}
    _put(client, p2)
    out = client.put(f'/api/layer/{a}/canvas',
                     json={'canvas_id': c2id, 'mode': 'move'}).get_json()
    assert out['groups'][0]['layer_ids'] == [a, b]
    assert _layer(out, a)['canvas_id'] == _layer(out, b)['canvas_id'] == c2id
    assert _layer(out, a)['customPortPaths']['1'][1] == {
        'row': 0, 'col': 1, 'layerId': b}


def test_duplicate_layer_to_canvas_no_longer_leaves_a_dangling_pointer(client):
    """WAS: mode=duplicate cleared group_id but did NOT run the integrity pass,
    so the response handed the client a clone whose wiring named a layer in a
    group the clone is not in - and only the NEXT restore cleaned it up.
    """
    p, a, b = _wired_pair(client)
    c2id = client.post('/api/canvas', json={}).get_json()['active_canvas_id']
    out = client.put(f'/api/layer/{a}/canvas',
                     json={'canvas_id': c2id, 'mode': 'duplicate'}).get_json()
    clone = out['layers'][-1]
    assert clone['group_id'] is None
    assert clone.get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}
    # the source wall is untouched: still grouped, still wired across
    assert out['groups'][0]['layer_ids'] == [a, b]
    assert _layer(out, a)['customPortPaths']['1'][1]['layerId'] == b
    # and a restore changes nothing further
    out2 = _put(client, out)
    assert _layer(out2, clone['id']).get('customPortPaths') == {
        '1': [{'row': 0, 'col': 0}]}


def test_duplicate_canvas_clones_group_and_remaps_paths(client):
    p, a, b = _wired_pair(client)
    src = p['active_canvas_id']
    out = client.post(f'/api/canvas/{src}/duplicate').get_json()
    assert len(out['groups']) == 2
    g2 = out['groups'][1]
    assert g2['id'] != out['groups'][0]['id']
    ca, cb = g2['layer_ids']
    assert _layer(out, ca)['customPortPaths']['1'][1]['layerId'] == cb
    assert _layer(out, ca)['powerCustomPaths']['1'][1]['layerId'] == cb


def test_duplicate_canvas_twice_does_not_collide(client):
    p, a, b = _wired_pair(client)
    src = p['active_canvas_id']
    client.post(f'/api/canvas/{src}/duplicate')
    out = client.post(f'/api/canvas/{src}/duplicate').get_json()
    gids = [g['id'] for g in out['groups']]
    assert len(set(gids)) == len(gids), gids
    lids = [l['id'] for l in out['layers']]
    assert len(set(lids)) == len(lids), lids


def test_duplicate_canvas_after_a_member_moved_away_leaves_clones_loose(client):
    """Moving b to another canvas now dissolves the group (it would otherwise
    span two canvases), so there is nothing left on the source canvas to clone
    as a group and the clone stays loose with no cross-member wiring."""
    p, a, b = _wired_pair(client)
    src = p['active_canvas_id']
    c2id = client.post('/api/canvas', json={}).get_json()['active_canvas_id']
    client.put(f'/api/layer/{b}/canvas', json={'canvas_id': c2id, 'mode': 'move'})
    client.put(f'/api/canvas/{src}/active')
    out = client.post(f'/api/canvas/{src}/duplicate').get_json()
    assert out['groups'] == []
    clone = out['layers'][-1]
    assert clone['group_id'] is None
    assert clone.get('customPortPaths') == {'1': [{'row': 0, 'col': 0}]}


def test_duplicate_canvas_on_a_project_with_no_groups_key(client):
    """A pre-v0.11.0 file has no 'groups'. duplicate_canvas appends to
    current_project['groups'] directly."""
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _proj(client)
    p.pop('groups', None)
    p.pop('next_group_seq', None)
    _put(client, p)
    # restore normalises groups back to []; drop it again the way a POST save
    # of a hand-edited file would
    app_module.current_project.pop('groups', None)
    src = app_module.current_project['active_canvas_id']
    r = client.post(f'/api/canvas/{src}/duplicate')
    assert r.status_code == 200, r.get_data(as_text=True)[:600]


# ══════════════════════════════════════════════════════════════════════════
# 6. persistence / idempotency
# ══════════════════════════════════════════════════════════════════════════

def test_restore_is_idempotent_for_groups_and_paths(client):
    p, a, b = _wired_pair(client)
    one = _put(client, p)
    two = _put(client, copy.deepcopy(one))
    assert _strip(one) == _strip(two)


def test_save_load_save_round_trip(client):
    p, a, b = _wired_pair(client)
    first = _put(client, p)
    blob = json.loads(json.dumps(first))       # "write the file"
    second = _put(client, blob)                # "open the file"
    assert _strip(first)['groups'] == _strip(second)['groups']
    for lid in (a, b):
        assert _layer(first, lid).get('customPortPaths') == \
            _layer(second, lid).get('customPortPaths')
        assert _layer(first, lid).get('group_id') == \
            _layer(second, lid).get('group_id')
    assert _strip(first) == _strip(second)


def test_pre_group_file_round_trips_untouched(client):
    a = _add(client, 'A')['id']
    p = _proj(client)
    p.pop('groups', None)
    p.pop('next_group_seq', None)
    for l in p['layers']:
        l.pop('group_id', None)
    l0 = _layer(p, a)
    l0['customPortPaths'] = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}
    out = _put(client, p)
    assert out['groups'] == []
    assert out['next_group_seq'] == 1
    assert 'group_id' not in _layer(out, a)
    assert _layer(out, a)['customPortPaths'] == \
        {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}


def test_post_save_runs_group_integrity(client):
    """WAS: POST /api/project (save_project) merged the payload with NO repair,
    and every sidebar reorder goes through it. It would store two groups both
    called g1, one naming a layer that does not exist, and never write the
    group_id mirror - and that stood until the next undo, with the export
    reading it in the meantime.
    """
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    r = client.post('/api/project', json={
        'groups': [{'id': 'g1', 'layer_ids': [a, b, 99999]},
                   {'id': 'g1', 'layer_ids': ['x']}],
    })
    assert r.status_code == 200
    out = _proj(client)
    # the dead member is pruned, the one-member duplicate is dropped, and the
    # mirror is written onto both layers
    assert out['groups'] == [{'id': 'g1', 'layer_ids': [a, b]}]
    assert _layer(out, a)['group_id'] == 'g1'
    assert _layer(out, b)['group_id'] == 'g1'


def test_put_layer_cannot_forge_membership(client):
    """WAS: PUT /api/layer/<id> whitelisted group_id with zero validation, so a
    layer could claim to belong to a group that does not exist and the export
    then built a unit around a group nobody could resolve.
    """
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    r = client.put(f'/api/layer/{a}', json={'group_id': 'g-does-not-exist'})
    assert r.status_code == 200
    assert _layer(_proj(client), a).get('group_id') is None
    units = app_module._export_units(app_module.current_project,
                                     app_module.current_project['layers'])
    assert len(units) == 2      # two loose screens, not one phantom group

    # A group that DOES exist is accepted, and both sides are written.
    _put(client, _mk_group(_proj(client), [a, b]))
    c = _add(client, 'C')['id']
    assert client.put(f'/api/layer/{c}', json={'group_id': 'g1'}).status_code == 200
    out = _proj(client)
    assert _layer(out, c)['group_id'] == 'g1'
    assert out['groups'][0]['layer_ids'] == [a, b, c]
    # ...and null clears both sides.
    assert client.put(f'/api/layer/{c}', json={'group_id': None}).status_code == 200
    out = _proj(client)
    assert _layer(out, c)['group_id'] is None
    assert out['groups'][0]['layer_ids'] == [a, b]


# ══════════════════════════════════════════════════════════════════════════
# 7. non-screen members
# ══════════════════════════════════════════════════════════════════════════

def test_image_layer_can_be_a_group_member(client):
    a = _add(client, 'A')['id']
    r = client.post('/api/layer/add-image', json={
        'name': 'Logo', 'imageData': 'data:image/png;base64,AA',
        'imageWidth': 10, 'imageHeight': 10})
    assert r.status_code == 200
    img = r.get_json()['id']
    p = _mk_group(_proj(client), [a, img])
    out = _put(client, p)
    assert out['groups'][0]['layer_ids'] == [a, img]
    units = app_module._export_units(out, out['layers'])
    assert len(units) == 1 and len(units[0][1]) == 2
    bounds = app_module._export_unit_bounds(units[0][1])
    assert isinstance(bounds, dict)


def test_group_member_retyped_to_image_via_put(client):
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _mk_group(_proj(client), [a, b])
    _put(client, p)
    r = client.put(f'/api/layer/{b}', json={'type': 'image'})
    assert r.status_code == 200
    out = _put(client, _proj(client))
    assert out['groups'][0]['layer_ids'] == [a, b]


# ══════════════════════════════════════════════════════════════════════════
# 8. export endpoints must not 500 on a degenerate group
# ══════════════════════════════════════════════════════════════════════════

def test_all_members_hidden_group(client):
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _mk_group(_proj(client), [a, b])
    for lid in (a, b):
        _layer(p, lid)['visible'] = False
    out = _put(client, p)
    units = app_module._export_units(out, out['layers'])
    assert len(units) == 1
    assert app_module._export_unit_bounds(units[0][1])['width'] >= 0


def test_group_with_zero_panels_bounds(client):
    a = _add(client, 'A')['id']
    b = _add(client, 'B')['id']
    p = _mk_group(_proj(client), [a, b])
    for lid in (a, b):
        _layer(p, lid)['panels'] = []
    out = _put(client, p)
    units = app_module._export_units(out, out['layers'])
    assert app_module._export_unit_bounds(units[0][1])
