"""Undo's restore funnel keeps the processor tree's ids and keys honest.

The 2026-08-29 undo/redo audit ("people complaining of undo and redo being
broken") found the server half of two client-visible failures:

* ``next_processor_seq`` lived only server-side. The mutating processor
  routes answer with just the resolved tree, so the client's project copy -
  the one undo/redo PUTs back through ``restore_project`` - never carries
  the counter. The PUT is a total replace, the counter vanished, and
  ``_next_seq()`` fell back to 1: add proc1 and proc2, undo once, add again,
  and the new machine minted ``proc1`` - colliding with the survivor, so
  every later edit landed on whichever one ``_find_processor`` met first.
  The groups model already solved exactly this with ``sync_next_group_seq``
  (app.py documents the delete-g3/undo resurrection); the fix is its
  processor twin, ``sync_next_processor_seq``, run on both /api/project
  funnels before the SX40 box heal so healed boxes also mint above every id
  the payload holds.

* The funnels must never STAMP keys onto a project that never had them -
  the same read-must-not-create rule routes_port_assignment.py states three
  times. A processor-less project with no counter stays byte-for-byte
  untouched.

Run locally:
    python3 -m pytest tests/test_undo_audit_server.py -q
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


def _tree_ids(processors):
    ids = []
    for proc in processors or []:
        ids.append(proc.get('id'))
        for slot in proc.get('slots') or []:
            card = slot.get('card')
            if card:
                ids.append(card.get('id'))
                for cvt in card.get('cvts') or []:
                    ids.append(cvt.get('id'))
    return ids


# ── the unit itself ───────────────────────────────────────────────────────

def test_sync_seeds_above_every_id_in_the_tree():
    project = {
        'processors': [{
            'id': 'proc7',
            'slots': [{'index': 0, 'card': {
                'id': 'card7f',
                'cvts': [{'id': 'cvt9f2'}],
            }}],
        }],
    }
    assert catalog.sync_next_processor_seq(project) == 10
    assert project['next_processor_seq'] == 10


def test_sync_never_lowers_a_counter_that_is_ahead():
    project = {'processors': [{'id': 'proc2', 'slots': []}],
               'next_processor_seq': 40}
    assert catalog.sync_next_processor_seq(project) == 40


def test_sync_is_idempotent():
    project = {'processors': [{'id': 'proc3', 'slots': []}]}
    first = catalog.sync_next_processor_seq(project)
    assert catalog.sync_next_processor_seq(project) == first


def test_sync_does_not_stamp_a_clean_project():
    """A project with no processors and no counter stays untouched - the
    read-must-not-create rule, applied to a repair pass."""
    project = {'layers': [], 'name': 'Untitled Project'}
    catalog.sync_next_processor_seq(project)
    assert 'next_processor_seq' not in project


# ── the user-shaped repro, through the real routes ────────────────────────

def test_undo_put_cannot_make_the_next_processor_collide(client):
    """A LEGACY snapshot - one taken by a client from before the counter was
    echoed, so it carries the tree but no counter - PUT back through the
    funnel must still leave a tree a later add cannot collide with."""
    stale_copy = client.get('/api/project').get_json()
    assert 'next_processor_seq' not in stale_copy

    for _ in range(2):
        resp = client.post('/api/processors',
                           json={'deviceId': 'brompton-sx40'})
        assert resp.status_code == 201
    tree = client.get('/api/processors').get_json()['processors']

    # Undo to the one-processor state, counter dropped (the legacy shape).
    snapshot = copy.deepcopy(stale_copy)
    snapshot['processors'] = copy.deepcopy(tree[:1])
    snapshot.pop('next_processor_seq', None)
    resp = client.put('/api/project', json=snapshot)
    assert resp.status_code == 200

    resp = client.post('/api/processors', json={'deviceId': 'brompton-sx40'})
    assert resp.status_code == 201
    after = client.get('/api/processors').get_json()['processors']
    ids_after = _tree_ids(after)
    # Without sync_next_processor_seq the add minted a second 'proc1' and
    # _find_processor sent every later edit to whichever it met first.
    assert len(ids_after) == len(set(ids_after)), ids_after


def test_deleted_processor_id_stays_retired_across_undo(client):
    """The groups lesson, on processors: delete proc2, undo something (the
    whole-project PUT), add a machine - the new one must NOT answer to
    proc2, or every stale reference to the deleted machine (pins, backup
    links in old snapshots) springs back to life on unrelated hardware.
    Works because the mutating routes echo next_processor_seq, the client
    stores it on its project copy, and the funnel never lowers it."""
    for _ in range(2):
        resp = client.post('/api/processors',
                           json={'deviceId': 'brompton-sx40'})
        assert resp.status_code == 201
    full_copy = client.get('/api/project').get_json()
    assert full_copy.get('next_processor_seq'), 'counter must be stored'
    retired = full_copy['processors'][1]['id']

    resp = client.delete(f'/api/processors/{retired}')
    assert resp.status_code == 200
    body = resp.get_json()
    # The echo the client folds into its project copy (and so into every
    # undo snapshot taken after the delete).
    assert body.get('next_processor_seq') == full_copy['next_processor_seq']

    # The client snapshot of the post-delete state: pre-delete copy, tree
    # and counter folded in from the delete response.
    snapshot = copy.deepcopy(full_copy)
    snapshot['processors'] = body['processors']
    snapshot['next_processor_seq'] = body['next_processor_seq']
    resp = client.put('/api/project', json=snapshot)
    assert resp.status_code == 200

    resp = client.post('/api/processors', json={'deviceId': 'brompton-sx40'})
    assert resp.status_code == 201
    after = client.get('/api/processors').get_json()['processors']
    assert retired not in {p['id'] for p in after}, after
    ids_after = _tree_ids(after)
    assert len(ids_after) == len(set(ids_after)), ids_after


def test_restore_funnel_does_not_stamp_processor_keys(client):
    """Undo's PUT of a project that never defined processors leaves it with
    neither the key nor the counter."""
    snapshot = client.get('/api/project').get_json()
    snapshot.pop('processors', None)
    snapshot.pop('next_processor_seq', None)
    resp = client.put('/api/project', json=snapshot)
    assert resp.status_code == 200
    stored = client.get('/api/project').get_json()
    assert 'processors' not in stored
    assert 'next_processor_seq' not in stored


def test_heal_mints_above_the_synced_counter(client):
    """The boxless-SX40 heal runs AFTER the seq sync on the restore funnel,
    so the boxes it stocks can never reuse an id the payload already holds.
    (The heal itself re-stocking a boxless card is the 2026-08-25 ruling -
    'a boxless SX40 is never a state somebody chose' - pinned as behavior
    here so the undo story around it stays understood.)"""
    resp = client.post('/api/processors', json={'deviceId': 'brompton-sx40'})
    assert resp.status_code == 201
    project = client.get('/api/project').get_json()
    proc = project['processors'][-1]
    card = next(s['card'] for s in proc['slots'] if s.get('card'))
    stocked_ids = [c['id'] for c in card['cvts']]
    assert stocked_ids, 'a fresh SX40 arrives with its default boxes'

    # An undo snapshot holding the boxless arrangement, counter dropped the
    # way the client's copy drops it.
    snapshot = copy.deepcopy(project)
    snap_proc = snapshot['processors'][-1]
    snap_card = next(s['card'] for s in snap_proc['slots'] if s.get('card'))
    snap_card['cvts'] = []
    snapshot.pop('next_processor_seq', None)
    resp = client.put('/api/project', json=snapshot)
    assert resp.status_code == 200

    healed = resp.get_json()
    healed_proc = next(p for p in healed['processors']
                       if p['id'] == proc['id'])
    healed_card = next(s['card'] for s in healed_proc['slots']
                       if s.get('card'))
    healed_ids = [c['id'] for c in healed_card['cvts']]
    assert healed_ids, 'the funnel re-stocked the boxless SX40 (the ruling)'
    all_ids = _tree_ids(healed['processors'])
    assert len(all_ids) == len(set(all_ids)), all_ids
    # And the funnel's response IS the healed body - the client adopts it
    # (app-history's _adoptRestoredProjectRepair), so what this returns is
    # what undo shows.
    assert healed_ids == [c['id'] for c in healed_card['cvts']]
