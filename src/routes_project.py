"""
Project + server-session routes (get / new / save / restore project).

Thin controllers over the project model, which stays in app: current_project and
the model helpers (_build_initial_project, initialize_default_layer, migrations,
sync_next_layer_id) live there. new_project / restore_project REASSIGN the
project, so this blueprint sets it through the app module attribute
(app.current_project = ...) — that keeps app.py's readers and the tests in sync.
"""
from flask import Blueprint, request, jsonify

import app
import port_assignment
import processor_catalog
from app import log_event, socketio

project_bp = Blueprint('project', __name__)


@project_bp.route('/api/project', methods=['GET'])
def get_project():
    log_event('get_project')
    return jsonify(app.current_project)


@project_bp.route('/api/server-session', methods=['GET'])
def get_server_session():
    """Return unique session ID that changes on server restart"""
    log_event('get_server_session', {'session_id': app.SERVER_SESSION_ID})
    return jsonify({
        'session_id': app.SERVER_SESSION_ID,
        'start_time': app.SERVER_START_TIME
    })


@project_bp.route('/api/project/new', methods=['POST'])
def new_project():
    app.next_layer_id = 1  # Reset counter for new project
    app.current_project = app._build_initial_project()
    # Add default layer to new projects
    app.initialize_default_layer()
    log_event('new_project')
    socketio.emit('project_cleared')
    return jsonify(app.current_project)


@project_bp.route('/api/project', methods=['POST'])
def save_project():
    data = request.json or {}
    # Slice 6: source-of-truth for raster lives on the active canvas. If the
    # client sent root-level raster_* fields without a canvases payload
    # (backwards-compat clients / older tests), propagate those into the
    # active canvas so the canvas object reflects the new values. Then
    # re-mirror canvas → root so root stays consistent.
    canvases = app.current_project.get('canvases') or []
    if canvases and not data.get('canvases'):
        active_id = app.current_project.get('active_canvas_id')
        active = next(
            (c for c in canvases if isinstance(c, dict) and c.get('id') == active_id),
            canvases[0],
        )
        for key in (
            'raster_width', 'raster_height',
            'show_raster_width', 'show_raster_height',
            'data_flow_perspective', 'power_perspective',
        ):
            if key in data and data[key] is not None:
                active[key] = data[key]
    app.current_project.update(data)
    app.current_project['is_pristine'] = False
    app._mirror_active_canvas_to_root(app.current_project)
    # v0.11.0: the same repair PUT has always run. This route is not just
    # "save as" - every sidebar reorder comes through it with the whole layers
    # array - and without the pass it would happily store two groups both
    # called g1, a group naming a layer that does not exist, or a groups array
    # with no group_id mirror written back onto the layers. Whatever bad shape
    # it stored then survived until the next undo, and the export read it in
    # the meantime. Idempotent, so a well-formed save is untouched.
    app._enforce_group_integrity(app.current_project)
    # Same funnel duty for the processor tree: a payload can carry a
    # pre-stocking SX40 through this route too, and a boxless one is a
    # legacy shape, never a choice. Idempotent like the pass above it.
    # The seq sync runs FIRST so the heal's boxes mint above every id the
    # payload already holds.
    processor_catalog.sync_next_processor_seq(app.current_project)
    processor_catalog.stock_default_cvts(app.current_project)
    # Same funnel duty for port attachment: see restore_project below.
    if port_assignment.retire_auto(app.current_project):
        log_event('port_assignment_auto_retired', {'at': 'save_project'})
    app.sync_next_layer_id()
    log_event('save_project', {'name': app.current_project.get('name')})
    return jsonify({'status': 'success'})


@project_bp.route('/api/project', methods=['PUT'])
def restore_project():
    """Restore entire project state (used by undo/redo and file load)"""
    data = request.json or {}
    # Refuse to load projects authored by a newer app version. Simple string
    # comparison is fine for the foreseeable "0.x" range; revisit if we ever
    # ship a 0.10 / 1.0.
    incoming_version = data.get('format_version') if isinstance(data, dict) else None
    if incoming_version and incoming_version > app.CURRENT_FORMAT_VERSION:
        return jsonify({
            'error': (
                f'Project format {incoming_version} is newer than this '
                f'version supports ({app.CURRENT_FORMAT_VERSION}). '
                f'Please update the app.'
            )
        }), 400
    app.current_project = data
    app.current_project['is_pristine'] = False
    # Backfill showOffsetX/Y on layers from older projects that pre-date the
    # Show Look feature, default them to the layer's processor offset so
    # existing projects open with the show layout = pixel layout.
    for layer in app.current_project.get('layers', []):
        if layer.get('showOffsetX') is None:
            layer['showOffsetX'] = layer.get('offset_x', 0)
        if layer.get('showOffsetY') is None:
            layer['showOffsetY'] = layer.get('offset_y', 0)
    # Backfill the Show Look raster size to match the processor raster for
    # projects saved before the Show Look feature.
    if app.current_project.get('show_raster_width') is None:
        app.current_project['show_raster_width'] = app.current_project.get('raster_width', 1920)
    if app.current_project.get('show_raster_height') is None:
        app.current_project['show_raster_height'] = app.current_project.get('raster_height', 1080)
    # Wiring perspective defaults: older projects render front-facing,
    # matching how they appeared before the perspective toggle existed.
    if app.current_project.get('data_flow_perspective') not in ('front', 'back'):
        app.current_project['data_flow_perspective'] = 'front'
    if app.current_project.get('power_perspective') not in ('front', 'back'):
        app.current_project['power_perspective'] = 'front'
    # Multi-canvas migration. Additive: leaves root-level raster fields in
    # place so the existing single-canvas client keeps working. Slice 6 will
    # switch the source-of-truth to per-canvas fields.
    migrated, did_migrate = app._migrate_to_v0_8(app.current_project)
    app.current_project = migrated
    if did_migrate:
        log_event('project_migrated', {
            'from_version': '<0.8',
            'to_version': app.CURRENT_FORMAT_VERSION,
        })
    # v0.10.8.1: re-derive panel geometry from the per-panel states the client
    # sent, rather than trusting the x/y/width/height it sent alongside them.
    # Half-tiles resize the whole screen (a fully-half row collapses to half
    # height and everything below reflows), and that math only exists here. A
    # client that mutates panel states without a round-trip - as the bulk
    # half-tile path did before v0.10.8 - would otherwise write flags that
    # disagree with the geometry, and restore_project would store that as
    # truth. _build_panels derives every panel field from (columns, rows,
    # offsets, cabinet size, states), so this is a no-op when the incoming
    # geometry already agrees, and self-heals it when it does not.
    # A missing 'type' means screen everywhere else in the app (see app.py's
    # _seed_data_with_canvas_defaults), so legacy type-less layers get rebuilt
    # - and migrated - too.
    for layer in app.current_project.get('layers', []):
        if (layer.get('type') or 'screen') == 'screen':
            app._rebuild_layer_geometry_from_panel_states(layer)
    # v0.11.0: same reasoning as the geometry rebuild above, for the screen
    # group model. Membership lives on two sides (project['groups'][n]
    # ['layer_ids'] and layer['group_id']) and the client can hand back a
    # payload where they disagree - a layer deleted while its group still
    # lists it, an undo snapshot taken mid-edit, a hand-edited file. This is
    # the funnel every undo/redo and file load passes through, so it is the
    # one place that can guarantee the two sides agree. Idempotent by design:
    # restoring the same project twice must not change it.
    app._enforce_group_integrity(app.current_project)
    # A requires-distribution device saved before new_processor stocked its
    # default boxes arrives with an empty cvts list - a pre-stocking save,
    # not an arrangement. This funnel (file load, undo/redo) is where it is
    # healed, because a read must not mutate and the panel may never open.
    # Before it runs, re-seed the processor id counter: an undo snapshot can
    # carry a stale counter or none at all (snapshots taken before the routes
    # echoed it, hand-edited files), and _next_seq falling back would mint a
    # duplicate proc/card/cvt id - the resurrection sync_next_group_seq
    # exists for.
    processor_catalog.sync_next_processor_seq(app.current_project)
    processor_catalog.stock_default_cvts(app.current_project)
    # Auto-numbering retired (user ruling, 2026-09-03): a file saved before
    # it carries no `autoRetired` mark, and its auto-drawn ports have to be
    # frozen into pins ONCE so the drawing does not change on load. The
    # counts that decide where those ports were live on the client, so this
    # funnel settles only what it can without them (no hardware, no
    # screens, auto already off: stamp and done) and the first
    # port-assignment request after the load - which carries the screens -
    # settles the rest. Idempotent by the mark; see retire_auto.
    if port_assignment.retire_auto(app.current_project):
        log_event('port_assignment_auto_retired', {'at': 'restore_project'})
    app.sync_next_layer_id()
    log_event('restore_project', {
        'name': app.current_project.get('name', '?'),
        'layers': len(app.current_project.get('layers', [])),
        'layer_names': [l.get('name', '?') for l in app.current_project.get('layers', [])]
    })
    socketio.emit('project_updated', app.current_project)
    # Slice 12: surface a one-time migration notice to the client when the
    # incoming file lacked a v0.8 format_version. Carried as a top-level
    # transient field on the response only, never stored on disk because
    # the next save will write the now-present format_version, and future
    # loads of that same file won't re-migrate (and won't re-toast).
    response = dict(app.current_project)
    if did_migrate:
        response['_migration_notice'] = True
    return jsonify(response)
