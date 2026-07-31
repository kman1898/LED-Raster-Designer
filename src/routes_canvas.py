"""
Canvas (multi-canvas) routes. Thin controllers over the project model in app;
canvas helpers stay in app and are imported here.
"""
import json

from flask import Blueprint, request, jsonify

import app
from app import _find_canvas, _mirror_active_canvas_to_root, _next_canvas_color, _next_canvas_id, _next_canvas_workspace_position, _next_duplicate_canvas_name, log_event, socketio

canvas_bp = Blueprint('canvas', __name__)

@canvas_bp.route('/api/canvas', methods=['POST'])
def create_canvas():
    data = request.json or {}
    canvases = app.current_project.setdefault('canvases', [])
    new_id = _next_canvas_id()
    # Default name: "Canvas <N>" where N matches the numeric id suffix.
    default_name = f'Canvas {new_id[1:]}'
    # Inherit raster defaults from the active canvas so a freshly added
    # canvas feels like a clone of the user's current setup. Slice 5 will
    # add real workspace placement; for now stack at 0,0.
    active = _find_canvas(app.current_project.get('active_canvas_id')) or (
        canvases[0] if canvases else None
    )
    ws_x, ws_y = _next_canvas_workspace_position()
    # Resolve raster dimensions: explicit request body wins (so the client can
    # honor the user's "Default Canvas Size" preference), otherwise fall back
    # to the active canvas's raster, otherwise the hard-coded 1920x1080.
    def _pos_int(value, fallback):
        try:
            n = int(value)
            return n if n > 0 else fallback
        except (TypeError, ValueError):
            return fallback
    rw_default = (active or {}).get('raster_width', 1920)
    rh_default = (active or {}).get('raster_height', 1080)
    sw_default = (active or {}).get('show_raster_width', rw_default)
    sh_default = (active or {}).get('show_raster_height', rh_default)
    raster_w = _pos_int(data.get('raster_width'), rw_default)
    raster_h = _pos_int(data.get('raster_height'), rh_default)
    show_w = _pos_int(data.get('show_raster_width'), sw_default if 'show_raster_width' not in data else raster_w)
    show_h = _pos_int(data.get('show_raster_height'), sh_default if 'show_raster_height' not in data else raster_h)
    canvas = {
        'id': new_id,
        'name': data.get('name') or default_name,
        'color': data.get('color') or _next_canvas_color(),
        'workspace_x': ws_x,
        'workspace_y': ws_y,
        'raster_width': raster_w,
        'raster_height': raster_h,
        'show_raster_width': show_w,
        'show_raster_height': show_h,
        'data_flow_perspective': (active or {}).get('data_flow_perspective', 'front'),
        'power_perspective': (active or {}).get('power_perspective', 'front'),
        'visible': True,
    }
    canvases.append(canvas)
    app.current_project['active_canvas_id'] = new_id
    app.current_project['is_pristine'] = False
    log_event('canvas_create', {'id': new_id, 'name': canvas['name']})
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@canvas_bp.route('/api/canvas/<canvas_id>', methods=['PUT'])
def update_canvas(canvas_id):
    canvas = _find_canvas(canvas_id)
    if not canvas:
        return jsonify({'error': 'Canvas not found'}), 404
    data = request.json or {}
    allowed = {
        'name', 'color', 'visible',
        'workspace_x', 'workspace_y',
        # v0.8.5.3: per-canvas Show Look workspace position (independent
        # from Pixel Map's workspace_x/y). null clears.
        'show_workspace_x', 'show_workspace_y',
        'raster_width', 'raster_height',
        'show_raster_width', 'show_raster_height',
        'data_flow_perspective', 'power_perspective',
    }
    changed = {}
    for key, val in data.items():
        if key in allowed:
            canvas[key] = val
            changed[key] = val
    app.current_project['is_pristine'] = False
    # Slice 6: keep the project-root raster mirror in sync so any
    # client/test still reading root sees the latest active-canvas values.
    _mirror_active_canvas_to_root(app.current_project)
    log_event('canvas_update', {'id': canvas_id, 'changed': changed})
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@canvas_bp.route('/api/canvas/<canvas_id>', methods=['DELETE'])
def delete_canvas(canvas_id):
    canvases = app.current_project.get('canvases') or []
    if len(canvases) <= 1:
        return jsonify({
            'error': 'Cannot delete the last remaining canvas. '
                     'A project must contain at least one canvas.'
        }), 400
    canvas = _find_canvas(canvas_id)
    if not canvas:
        return jsonify({'error': 'Canvas not found'}), 404
    deleted_name = canvas.get('name', '?')
    # Remove the canvas itself.
    app.current_project['canvases'] = [c for c in canvases if c.get('id') != canvas_id]
    # Remove all layers belonging to this canvas.
    layers_before = len(app.current_project.get('layers', []))
    app.current_project['layers'] = [
        l for l in app.current_project.get('layers', [])
        if l.get('canvas_id') != canvas_id
    ]
    layers_removed = layers_before - len(app.current_project['layers'])
    # v0.10.9: deleting a canvas deletes every layer on it, which is the same
    # group-integrity event as a single layer delete (routes_layers.delete_layer)
    # only in bulk - a group can be left naming dead layers, reduced to one
    # surviving member, or holding manual path steps that point at a panel on
    # the canvas we just removed. Repair now so the response we return is
    # already consistent, instead of waiting for the next undo/file load.
    app._enforce_group_integrity(app.current_project)
    # Reassign active_canvas_id to the next remaining canvas.
    if app.current_project.get('active_canvas_id') == canvas_id:
        app.current_project['active_canvas_id'] = app.current_project['canvases'][0]['id']
    app.current_project['is_pristine'] = False
    log_event('canvas_delete', {
        'id': canvas_id, 'name': deleted_name,
        'layers_removed': layers_removed,
    })
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@canvas_bp.route('/api/canvas/<canvas_id>/duplicate', methods=['POST'])
def duplicate_canvas(canvas_id):
    src = _find_canvas(canvas_id)
    if not src:
        return jsonify({'error': 'Canvas not found'}), 404
    new_id = _next_canvas_id()
    new_canvas = json.loads(json.dumps(src))
    new_canvas['id'] = new_id
    new_canvas['name'] = _next_duplicate_canvas_name(src.get('name', 'Canvas'))
    new_canvas['color'] = _next_canvas_color()
    # Auto-place the duplicate to the right of the existing canvases so it
    # doesn't visually overlap its source. (Computed BEFORE the duplicate is
    # appended, so the rightmost-edge calc covers existing canvases only.)
    ws_x, ws_y = _next_canvas_workspace_position()
    new_canvas['workspace_x'] = ws_x
    new_canvas['workspace_y'] = ws_y
    app.current_project['canvases'].append(new_canvas)
    # Clone every layer in the source canvas, with a new layer id.
    src_layers = [
        l for l in app.current_project.get('layers', [])
        if l.get('canvas_id') == canvas_id
    ]
    for src_layer in src_layers:
        clone = json.loads(json.dumps(src_layer))
        clone['id'] = app.next_layer_id
        app.next_layer_id += 1
        clone['canvas_id'] = new_id
        # v0.10.9: same reason routes_layers.move_layer_to_canvas clears this -
        # the clone is a deep copy, so it would otherwise carry the source's
        # group_id while that group's layer_ids knows nothing about it.
        # Duplicating a canvas makes new screens, not new members of the
        # original's groups.
        clone['group_id'] = None
        app.current_project['layers'].append(clone)
    app.current_project['active_canvas_id'] = new_id
    # v0.10.9: the clones also carry verbatim customPortPaths /
    # powerCustomPaths, so any cross-layer step in them still names a layer id
    # on the ORIGINAL canvas - wiring drawn onto someone else's screen. We do
    # NOT remap those ids onto the corresponding clones, even though the id
    # mapping is right here: the clones are deliberately groupless (above), and
    # a cross-layer step is only legal between members of one group, so a
    # remapped step would be pruned again by the very next undo or file load.
    # Remapping would buy a wire that vanishes on the user's next keystroke.
    # Dropping it is the honest, stable answer, and _enforce_group_integrity is
    # the one implementation of that rule. (If a later step decides that
    # duplicating a canvas should duplicate its groups too, the remap becomes
    # correct and belongs here alongside that change.)
    app._enforce_group_integrity(app.current_project)
    app.current_project['is_pristine'] = False
    log_event('canvas_duplicate', {
        'src_id': canvas_id, 'new_id': new_id,
        'layers_cloned': len(src_layers),
    })
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@canvas_bp.route('/api/canvas/reorder', methods=['POST'])
def reorder_canvases():
    data = request.json or {}
    canvas_ids = data.get('canvas_ids') or []
    canvases = app.current_project.get('canvases') or []
    by_id = {c.get('id'): c for c in canvases}
    if set(canvas_ids) != set(by_id.keys()):
        return jsonify({
            'error': 'canvas_ids must be a permutation of existing canvas ids',
        }), 400
    app.current_project['canvases'] = [by_id[cid] for cid in canvas_ids]
    app.current_project['is_pristine'] = False
    log_event('canvas_reorder', {'order': canvas_ids})
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@canvas_bp.route('/api/canvas/<canvas_id>/active', methods=['PUT'])
def set_active_canvas(canvas_id):
    if not _find_canvas(canvas_id):
        return jsonify({'error': 'Canvas not found'}), 404
    app.current_project['active_canvas_id'] = canvas_id
    # Note: not flagging pristine, active canvas is a UI cursor, not data.
    log_event('canvas_set_active', {'id': canvas_id})
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)
