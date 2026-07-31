"""Screen groups (v0.10.9) - manual paths that cross from one member to another.

A hand-drawn data-port path or power circuit can run off one group member and
onto the next, because to the user the group IS one wall. The path never moves
off the layer that owns the port/circuit; only the individual step learns where
it lands:

    layer['customPortPaths']['1']  -> [{'row': 0, 'col': 0},
                                       {'row': 0, 'col': 1, 'layerId': 7}]
    layer['powerCustomPaths']['1'] -> same shape

``layerId`` (camelCase, matching the client) is the only cross-layer thing in
the file, and it is the only thing that can go stale: delete the peer, ungroup
the wall, or move a member into a different group and the step now names a
panel that is not part of this screen. ``app._prune_cross_layer_paths``, called
at the end of ``_enforce_group_integrity``, is the repair.

These tests cover both halves:

* PRESERVATION - a plain path, and a legal cross-layer path, must survive a
  restore byte for byte. test_project_geometry_rebuild.py asserts a lot about
  what restore preserves but never once looked at these two keys.
* PRUNING - dead, foreign and self-referential pointers, empty leftovers,
  garbage that must not 500, and the two canvas routes that could leak a
  pointer at a layer on another canvas entirely.
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


def _layer(project, layer_id):
    return next(l for l in project['layers'] if l['id'] == layer_id)


def _grouped_pair(client, name='Wall'):
    """Two screens joined into one group. Returns (project, group_id, [ids])."""
    ids = [_add_screen(client, 'W0')['id'], _add_screen(client, 'W1', offset_x=600)['id']]
    group = app_module._create_group(app_module.current_project, ids, name=name)
    assert group is not None
    return _get_project(client), group['id'], ids


def _set_paths(client, layer_id, key, paths):
    """Write a path structure straight onto the server-side layer.

    Direct mutation rather than PUT /api/layer/<id>: these tests are about what
    the integrity pass does to an ALREADY stored structure, and the update route
    would only be another way to put it there.
    """
    for layer in app_module.current_project['layers']:
        if layer.get('id') == layer_id:
            layer[key] = paths
            return
    raise AssertionError(f'no layer {layer_id}')


def _paths(project, layer_id, key='customPortPaths'):
    return _layer(project, layer_id).get(key)


# ── 1. PRESERVATION ───────────────────────────────────────────────────────

def test_plain_path_survives_restore_untouched(client):
    """The regression guard for the whole feature: a project that never used a
    group must round-trip exactly as it always did."""
    lid = _add_screen(client, 'Solo')['id']
    drawn = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}, {'row': 1, 'col': 1}]}
    _set_paths(client, lid, 'customPortPaths', json.loads(json.dumps(drawn)))
    _set_paths(client, lid, 'powerCustomPaths', json.loads(json.dumps(drawn)))

    restored = _put(client, _get_project(client))

    assert _paths(restored, lid, 'customPortPaths') == drawn
    assert _paths(restored, lid, 'powerCustomPaths') == drawn


def test_valid_cross_layer_entry_survives_restore(client):
    project, _gid, (a, b) = _grouped_pair(client)
    drawn = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': b}]}
    _set_paths(client, a, 'customPortPaths', json.loads(json.dumps(drawn)))
    _set_paths(client, a, 'powerCustomPaths', json.loads(json.dumps(drawn)))

    restored = _put(client, _get_project(client))

    assert _paths(restored, a, 'customPortPaths') == drawn
    assert _paths(restored, a, 'powerCustomPaths') == drawn


def test_valid_cross_layer_entry_is_idempotent(client):
    """restore runs on every undo; the second pass must change nothing."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths',
               {'1': [{'row': 0, 'col': 0}, {'row': 1, 'col': 2, 'layerId': b}]})

    first = _put(client, _get_project(client))
    second = _put(client, first)
    third = _put(client, second)

    assert _paths(second, a) == _paths(first, a)
    assert _paths(third, a) == _paths(second, a)


def test_layer_with_no_path_structures_is_left_alone(client):
    lid = _add_screen(client, 'Solo')['id']
    before = _layer(_get_project(client), lid).get('customPortPaths')
    restored = _put(client, _get_project(client))
    assert _layer(restored, lid).get('customPortPaths') == before


# ── 2. PRUNING ────────────────────────────────────────────────────────────

def test_entry_naming_a_nonexistent_layer_is_dropped(client):
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': 9999}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a) == {'1': [{'row': 0, 'col': 0}]}


def test_entry_naming_a_layer_in_another_group_is_dropped(client):
    """Two walls, four layers. A path on wall 1 must not reach into wall 2."""
    project, _g1, (a, b) = _grouped_pair(client, name='Wall 1')
    c = _add_screen(client, 'X0', offset_x=1200)['id']
    d = _add_screen(client, 'X1', offset_x=1800)['id']
    assert app_module._create_group(app_module.current_project, [c, d], name='Wall 2')
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0},
              {'row': 0, 'col': 1, 'layerId': b},  # same group - legal
              {'row': 0, 'col': 2, 'layerId': c}],  # other group - not
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a) == {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
    }


def test_entry_naming_a_groupless_layer_is_dropped(client):
    project, _gid, (a, b) = _grouped_pair(client)
    loner = _add_screen(client, 'Loner', offset_x=1200)['id']
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': loner}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a) == {'1': [{'row': 0, 'col': 0}]}


def test_owner_losing_its_group_drops_its_cross_layer_entries(client):
    """The wall is ungrouped after the path was drawn: two screens again, so
    the step has nowhere legal to land even though both layers still exist."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': b}],
    })
    project = _get_project(client)
    project['groups'] = []  # what an ungroup action hands back

    restored = _put(client, project)

    assert _layer(restored, a)['group_id'] is None
    assert _paths(restored, a) == {'1': [{'row': 0, 'col': 0}]}


def test_entry_pointing_at_its_own_layer_is_normalised(client):
    """Not an error - just the plain form written the long way."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0, 'layerId': a}, {'row': 0, 'col': 1, 'layerId': b}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a) == {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
    }


def test_self_reference_is_normalised_even_without_a_group(client):
    lid = _add_screen(client, 'Solo')['id']
    _set_paths(client, lid, 'powerCustomPaths', {
        '2': [{'row': 1, 'col': 1, 'layerId': lid}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, lid, 'powerCustomPaths') == {'2': [{'row': 1, 'col': 1}]}


def test_path_left_empty_by_pruning_is_removed_entirely(client):
    """An empty path is not a path: the port would claim a custom route and
    then draw nothing."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0, 'layerId': 9999}],
        '2': [{'row': 2, 'col': 2}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a) == {'2': [{'row': 2, 'col': 2}]}
    assert '1' not in _paths(restored, a)


def test_power_paths_are_pruned_on_the_same_rules(client):
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'powerCustomPaths', {
        'A': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': 9999}],
    })

    restored = _put(client, _get_project(client))

    assert _paths(restored, a, 'powerCustomPaths') == {'A': [{'row': 0, 'col': 0}]}


def test_a_peer_deleted_via_the_layer_route_prunes_immediately(client):
    """delete_layer already calls _enforce_group_integrity, so the response it
    returns must already be free of the dangling pointer."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 0, 'layerId': b}],
    })

    resp = client.delete(f'/api/layer/{b}')
    assert resp.status_code == 200
    after = resp.get_json()

    assert after['groups'] == []
    assert _paths(after, a) == {'1': [{'row': 0, 'col': 0}]}


# ── 3. GARBAGE MUST NOT 500 ───────────────────────────────────────────────

@pytest.mark.parametrize('bad', [
    None,
    'nonsense',
    42,
    [],
    {'1': None},
    {'1': 'not-a-list'},
    {'1': 7},
    {'1': [None, 'x', 5]},
    {'1': [{'col': 0, 'layerId': 2}]},          # cross-layer, no row
    {'1': [{'row': 0, 'layerId': 2}]},          # cross-layer, no col
    {'1': [{'row': 0, 'col': 0, 'layerId': None}]},
    {'1': [{'row': 0, 'col': 0, 'layerId': 'seven'}]},
    {'1': [{'layerId': 2}]},
])
def test_malformed_path_structures_do_not_raise(client, bad):
    """This runs on every undo, redo and file load. It may drop garbage; it may
    never 500 on it."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', bad)
    _set_paths(client, a, 'powerCustomPaths', bad)

    resp = client.put('/api/project', json=_get_project(client))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    # And again, on its own output - garbage must converge like everything else.
    assert client.put('/api/project', json=resp.get_json()).status_code == 200


def test_plain_entries_missing_row_are_left_alone(client):
    """A malformed step WITHOUT a layerId is not ours to judge - it is exactly
    the shape a pre-group project could already hold."""
    lid = _add_screen(client, 'Solo')['id']
    _set_paths(client, lid, 'customPortPaths', {'1': [{'col': 3}]})

    restored = _put(client, _get_project(client))

    assert _paths(restored, lid) == {'1': [{'col': 3}]}


def test_pruning_helper_tolerates_a_non_project(client):
    assert app_module._prune_cross_layer_paths(None) is None
    assert app_module._prune_cross_layer_paths('nope') == 'nope'
    assert app_module._prune_cross_layer_paths({}) == {}
    assert app_module._prune_cross_layer_paths({'layers': 'nonsense'}) == {'layers': 'nonsense'}


# ── 4. THE CANVAS ROUTES ──────────────────────────────────────────────────

def test_canvas_duplicate_does_not_leak_layer_ids_from_the_original(client):
    """The clones are deep copies, so without the fix each cloned path would
    still point at a layer on the SOURCE canvas."""
    project, _gid, (a, b) = _grouped_pair(client)
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
    })
    _set_paths(client, a, 'powerCustomPaths', {
        'A': [{'row': 1, 'col': 0}, {'row': 1, 'col': 1, 'layerId': b}],
    })
    src_canvas = project['active_canvas_id']

    resp = client.post(f'/api/canvas/{src_canvas}/duplicate')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = resp.get_json()

    clones = [l for l in after['layers'] if l['canvas_id'] != src_canvas]
    assert len(clones) == 2, 'both members should have been cloned'
    for clone in clones:
        assert clone['group_id'] is None, 'clone leaked the source layer group_id'
        for key in ('customPortPaths', 'powerCustomPaths'):
            for steps in (clone.get(key) or {}).values():
                for step in steps:
                    assert 'layerId' not in step, (
                        f'{key} on clone {clone["id"]} still points at a layer '
                        f'on the original canvas')
    # The source's own wiring is untouched by its duplicate.
    assert _paths(after, a) == {'1': [{'row': 0, 'col': 0},
                                      {'row': 0, 'col': 1, 'layerId': b}]}
    # Only the cross-layer step goes: the clone keeps the part of the route
    # that lives on its own panels, so the user gets everything that can still
    # legally be drawn.
    clone_of_a = next(l for l in clones if l['name'] == _layer(after, a)['name'])
    assert clone_of_a['customPortPaths'] == {'1': [{'row': 0, 'col': 0}]}
    assert clone_of_a['powerCustomPaths'] == {'A': [{'row': 1, 'col': 0}]}


def test_canvas_delete_repairs_group_integrity(client):
    """A group spanning two canvases loses two of its three members when one
    canvas goes. The group must go with them, and so must the pointer at them."""
    a = _add_screen(client, 'A')['id']
    c2 = client.post('/api/canvas', json={'name': 'Second'}).get_json()
    c2_id = c2['active_canvas_id']
    b = _add_screen(client, 'B', canvas_id=c2_id)['id']
    c = _add_screen(client, 'C', canvas_id=c2_id, offset_x=600)['id']
    assert app_module._create_group(app_module.current_project, [a, b, c], name='Wall')
    _set_paths(client, a, 'customPortPaths', {
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1, 'layerId': b}],
    })

    resp = client.delete(f'/api/canvas/{c2_id}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = resp.get_json()

    assert [l['id'] for l in after['layers']] == [a]
    assert after['groups'] == [], 'group kept naming layers on the deleted canvas'
    assert _layer(after, a)['group_id'] is None
    assert _paths(after, a) == {'1': [{'row': 0, 'col': 0}]}
