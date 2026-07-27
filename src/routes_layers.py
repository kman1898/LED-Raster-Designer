"""
Layer routes: add (screen/image/text), update, delete, move between canvases,
and per-panel blank/hidden/half-tile toggles. Thin controllers over the
layer model in app (create_layer, _build_panels, geometry helpers stay there).
"""
import json

from flask import Blueprint, request, jsonify

import app
from app import _assign_canvas_id, _build_panels, _find_canvas, _rebuild_layer_geometry_from_panel_states, _seed_data_with_canvas_defaults, create_image_layer, create_layer, create_text_layer, log_event, socketio

layers_bp = Blueprint('layers', __name__)

@layers_bp.route('/api/layer/add', methods=['POST'])
def add_layer():
    data = request.json or {}
    # Slice 8: seed payload with the active canvas's preset bucket BEFORE
    # create_layer so cabinet_width/height flow into panel construction.
    # Only fills fields the caller didn't already set, so duplicate/paste
    # paths (which send full data) are unaffected.
    _seed_data_with_canvas_defaults(data)
    layer = create_layer(
        name=data.get('name', f'Screen{len(app.current_project["layers"]) + 1}'),
        columns=data.get('columns', 8),
        rows=data.get('rows', 5),
        cabinet_width=data.get('cabinet_width', 128),
        cabinet_height=data.get('cabinet_height', 128),
        offset_x=data.get('offset_x', 0),
        offset_y=data.get('offset_y', 0)
    )
    _assign_canvas_id(layer, data)

    # Apply additional settings from request (for duplicate/paste)
    optional_fields = [
        'color1', 'color2', 'panel_width_mm', 'panel_height_mm', 'panel_weight',
        'weight_unit', 'infoLabelSize',
        'halfFirstColumn', 'halfLastColumn', 'halfFirstRow', 'halfLastRow',
        'show_numbers', 'number_size', 'show_panel_borders', 'panel_border_width', 'show_circle_with_x',
        'border_color', 'border_color_pixel', 'border_color_cabinet', 'border_color_data', 'border_color_power',
        'cabinetIdStyle', 'cabinetIdPosition', 'cabinetIdColor',
        'dataFlowPattern', 'arrowLineWidth', 'arrowSize', 'arrowColor', 'primaryColor', 'primaryTextColor', 'backupColor', 'backupTextColor',
        'powerVoltage', 'powerVoltageCustom', 'powerAmperage', 'powerAmperageCustom', 'panelWatts',
        'powerMaximize', 'powerOrganized', 'powerCustomPath', 'powerFlowPattern',
        'powerLineWidth', 'powerLineColor', 'powerArrowColor', 'powerRandomColors',
        'powerLabelSize', 'powerLabelBgColor', 'powerLabelTextColor', 'powerLabelTemplate', 'powerLabelOverrides',
        'powerCustomPaths', 'powerCustomIndex', 'showPowerCircuitInfo',
        'powerColorCodedView',
        'powerCircuitColors',
        'showLabelName', 'showLabelNameCabinet', 'showLabelNameDataFlow', 'showLabelNamePower',
        'showLabelSizePx', 'showLabelSizeM', 'showLabelSizeFt', 'showLabelWeight',
        'showLabelInfo', 'labelsColor', 'labelsFontSize', 'useFractionalInches',
        'showOffsetTL', 'showOffsetTR', 'showOffsetBL', 'showOffsetBR',
        'showDataFlowPortInfo', 'showDataFlowPortLoad',
        'portLabelTemplatePrimary', 'portLabelTemplateReturn',
        'portLabelOverridesPrimary', 'portLabelOverridesReturn',
        'customPortPaths', 'customPortIndex',
        'randomDataColors',
        'showOffsetX', 'showOffsetY',
        # v0.8.5: per-layer override for which canvas the layer belongs to
        # in Show Look (and Data + Power, which render at the show layout).
        # null/missing = mirror canvas_id.
        'show_canvas_id',
    ]

    half_fields = {'halfFirstColumn', 'halfLastColumn', 'halfFirstRow', 'halfLastRow'}
    needs_rebuild = False
    for field in optional_fields:
        if field in data:
            layer[field] = data[field]
            if field in half_fields:
                needs_rebuild = True
    if needs_rebuild:
        layer['panels'] = _build_panels(layer)
    log_event('add_layer', {
        'name': layer.get('name'), 'id': layer.get('id'),
        'type': layer.get('type', 'screen'),
        'columns': layer.get('columns'), 'rows': layer.get('rows'),
        'cabinet_width': layer.get('cabinet_width'), 'cabinet_height': layer.get('cabinet_height'),
        'offset_x': layer.get('offset_x'), 'offset_y': layer.get('offset_y'),
        'total_layers': len(app.current_project['layers'])
    })
    
    # Apply hidden panels (for duplicate)
    if 'hiddenPanels' in data and data['hiddenPanels']:
        hidden_positions = {(hp['row'], hp['col']) for hp in data['hiddenPanels']}
        for panel in layer['panels']:
            if (panel['row'], panel['col']) in hidden_positions:
                panel['hidden'] = True

    # Apply per-panel state (halfTile + hidden + blank) for duplicate. This
    # is the path that preserves half-tile geometry: half-tile width/height
    # change column/row sizing inside _build_panels, so we rebuild the
    # geometry from these states rather than just stamping flags onto
    # already-built panels.
    if 'panelStates' in data and data['panelStates']:
        ps_dict = {}
        for ps in data['panelStates']:
            r = ps.get('row')
            c = ps.get('col')
            if r is None or c is None:
                continue
            entry = {}
            ht = ps.get('halfTile')
            if ht in ('width', 'height'):
                entry['halfTile'] = ht
            if ps.get('hidden'):
                entry['hidden'] = True
            if ps.get('blank'):
                entry['blank'] = True
            if entry:
                ps_dict[(r, c)] = entry
        if ps_dict:
            layer['panels'] = _build_panels(layer, ps_dict)

    app.current_project['layers'].append(layer)
    app.current_project['is_pristine'] = False
    socketio.emit('layer_added', layer)
    return jsonify(layer)

@layers_bp.route('/api/layer/add-image', methods=['POST'])
def add_image_layer():
    data = request.json or {}
    layer = create_image_layer(
        name=data.get('name', f'Image{len(app.current_project["layers"]) + 1}'),
        image_data=data.get('imageData', ''),
        image_width=data.get('imageWidth', 0),
        image_height=data.get('imageHeight', 0),
        offset_x=data.get('offset_x', 0),
        offset_y=data.get('offset_y', 0)
    )
    if 'imageScale' in data:
        layer['imageScale'] = data['imageScale']
    _assign_canvas_id(layer, data)
    log_event('add_image_layer', {'name': layer.get('name'), 'id': layer.get('id')})
    app.current_project['layers'].append(layer)
    app.current_project['is_pristine'] = False
    socketio.emit('layer_added', layer)
    return jsonify(layer)

@layers_bp.route('/api/layer/add-text', methods=['POST'])
def add_text_layer():
    data = request.json or {}
    layer = create_text_layer(
        name=data.get('name', f'Text{len(app.current_project["layers"]) + 1}'),
        text_content=data.get('textContent', ''),
        offset_x=data.get('offset_x', 0),
        offset_y=data.get('offset_y', 0),
        text_width=data.get('textWidth', 400),
        text_height=data.get('textHeight', 100)
    )
    for key in ('fontSize', 'fontFamily', 'fontColor', 'bgColor', 'bgOpacity',
                'textAlign', 'textPadding', 'showBorder', 'borderColor',
                'showOnPixelMap', 'showOnCabinetId', 'showOnDataFlow', 'showOnPower',
                'showRasterSize', 'dynamicInfoScope'):
        if key in data:
            layer[key] = data[key]
    _assign_canvas_id(layer, data)
    log_event('add_text_layer', {'name': layer.get('name'), 'id': layer.get('id')})
    app.current_project['layers'].append(layer)
    app.current_project['is_pristine'] = False
    socketio.emit('layer_added', layer)
    return jsonify(layer)

@layers_bp.route('/api/layer/<int:layer_id>', methods=['PUT'])
def update_layer(layer_id):
    data = request.json
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    previous_offset_x = layer.get('offset_x', 0)
    previous_offset_y = layer.get('offset_y', 0)

    for key in ['name', 'columns', 'rows', 'cabinet_width', 'cabinet_height',
                'offset_x', 'offset_y', 'rotation', 'color1', 'color2',
                'panel_width_mm', 'panel_height_mm', 'panel_weight', 'weight_unit', 'visible',
                'halfFirstColumn', 'halfLastColumn', 'halfFirstRow', 'halfLastRow',
                'show_numbers', 'number_size', 'show_panel_borders', 'panel_border_width', 'show_circle_with_x', 'border_color',
                'border_color_pixel', 'border_color_cabinet', 'border_color_data', 'border_color_power',
                'cabinetIdStyle', 'cabinetIdPosition', 'cabinetIdColor',
                'dataFlowPattern', 'arrowLineWidth', 'arrowSize', 'arrowColor', 'primaryColor', 'primaryTextColor', 'backupColor', 'backupTextColor',
                'showLabelName', 'showLabelNameCabinet', 'showLabelNameDataFlow', 'showLabelNamePower',
                'showLabelSizePx', 'showLabelSizeM', 'showLabelSizeFt', 'showLabelWeight', 'showLabelInfo',
                'labelsColor', 'labelsFontSize', 'infoLabelSize', 'useFractionalInches',
                'showOffsetTL', 'showOffsetTR', 'showOffsetBL', 'showOffsetBR',
                'powerVoltage', 'powerVoltageCustom', 'powerAmperage', 'powerAmperageCustom', 'panelWatts',
                'powerMaximize', 'powerOrganized', 'powerCustomPath', 'powerFlowPattern', 'powerLineWidth',
                'powerLineColor', 'powerArrowColor', 'powerRandomColors', 'powerColorCodedView', 'powerCircuitColors', 'powerLabelSize', 'powerLabelBgColor', 'powerLabelTextColor',
                'powerLabelTemplate', 'powerLabelOverrides', 'powerCustomPaths', 'powerCustomIndex',
                'lastPowerFlowPattern', 'type', 'imageData', 'imageWidth', 'imageHeight', 'imageScale',
                'locked', 'screenNameSizeCabinet', 'screenNameSizeDataFlow', 'screenNameSizePower',
                'textContent', 'textContentPixelMap', 'textContentCabinetId',
                'textContentShowLook', 'textContentDataFlow', 'textContentPower',
                'textContentOverridePixelMap', 'textContentOverrideCabinetId',
                'textContentOverrideShowLook', 'textContentOverrideDataFlow',
                'textContentOverridePower',
                'textWidth', 'textHeight', 'fontSize', 'fontFamily',
                'fontColor', 'bgColor', 'bgOpacity', 'textAlign', 'textPadding',
                'showBorder', 'borderColor', 'showOnPixelMap', 'showOnCabinetId',
                'showOnDataFlow', 'showOnPower', 'showOnShowLook', 'showRasterSize',
                'showProjectName', 'showDate',
                'showPrimaryPorts', 'showBackupPorts',
                'showCircuits', 'showSinglePhase', 'showThreePhase',
                'dynamicInfoScope',
                'fontBold', 'fontItalic', 'fontUnderline',
                # Data flow / processing settings (previously silently dropped on PUT
                # which broke preset application and label updates on re-fetch)
                # v0.10.9: lowLatency rides with processorType - leaving it out
                # would drop the flag on every per-layer PUT.
                'flowPattern', 'bitDepth', 'frameRate', 'processorType', 'lowLatency',
                'portMappingMode',
                'dataFlowColor', 'dataFlowLabelSize', 'randomDataColors',
                'portLabelTemplatePrimary', 'portLabelTemplateReturn',
                'portLabelOverridesPrimary', 'portLabelOverridesReturn',
                'customPortPaths', 'customPortIndex',
                'screenNameOffsetX', 'screenNameOffsetY',
                'screenNameOffsetXCabinet', 'screenNameOffsetYCabinet',
                'screenNameOffsetXDataFlow', 'screenNameOffsetYDataFlow',
                'screenNameOffsetXPower', 'screenNameOffsetYPower',
                'screenNameSize',
                # Show Look position (separate from offset_x/y).
                'showOffsetX', 'showOffsetY',
                # v0.8.5: per-layer Show Look canvas override. null clears.
                'show_canvas_id',
                'showDataFlowPortInfo', 'showDataFlowPortLoad',
                'showPowerCircuitInfo']:
        if key in data:
            layer[key] = data[key]

    # Log with actual changed values (exclude large arrays for readability)
    changed_values = {}
    for key in data.keys():
        val = data[key]
        if key == 'panels':
            changed_values[key] = f'{len(val)} panels' if isinstance(val, list) else str(val)[:50]
        elif key == 'customPortPaths' or key == 'powerCustomPaths':
            changed_values[key] = f'{len(val)} paths' if isinstance(val, dict) else str(val)[:50]
        elif key == 'imageData':
            changed_values[key] = f'{len(str(val))} chars'
        elif isinstance(val, (list, dict)) and len(str(val)) > 200:
            changed_values[key] = f'{type(val).__name__}({len(val)} items)'
        else:
            changed_values[key] = val
    log_event('update_layer', {'id': layer_id, 'name': layer.get('name', '?'), 'changed': changed_values})
    
    # Only regenerate panels if grid size or cabinet size changes (not offset)
    if layer.get('type') not in ('image', 'text') and (
        'columns' in data or 'rows' in data or 'cabinet_width' in data or 'cabinet_height' in data
            or 'halfFirstColumn' in data or 'halfLastColumn' in data
            or 'halfFirstRow' in data or 'halfLastRow' in data):
        # Save existing panel states (hidden, blank, halfTile) before regenerating.
        # Key by (row, col) so state stays anchored to its grid cell when columns
        # or rows change, keying by sequential id meant a column resize would
        # shuffle blanks/half-tiles across the wall.
        old_panel_states = {}
        if 'panels' in layer:
            for p in layer['panels']:
                old_panel_states[(p.get('row', 0), p.get('col', 0))] = {
                    'hidden': p.get('hidden', False),
                    'blank': p.get('blank', False),
                    'halfTile': p.get('halfTile', 'none'),
                }
        layer['panels'] = _build_panels(layer, old_panel_states)
    elif layer.get('type') != 'image' and ('offset_x' in data or 'offset_y' in data):
        # If only offset changed, shift existing panel positions.
        old_x = float(data.get('_prev_offset_x', previous_offset_x) or 0)
        old_y = float(data.get('_prev_offset_y', previous_offset_y) or 0)
        dx = float(layer.get('offset_x', 0) or 0) - old_x
        dy = float(layer.get('offset_y', 0) or 0) - old_y
        if dx != 0 or dy != 0:
            for panel in layer.get('panels', []):
                panel['x'] = panel.get('x', 0) + dx
                panel['y'] = panel.get('y', 0) + dy
    
    app.current_project['is_pristine'] = False
    socketio.emit('layer_updated', layer)
    return jsonify(layer)

@layers_bp.route('/api/layer/<int:layer_id>', methods=['DELETE'])
def delete_layer(layer_id):
    deleted_name = None
    for l in app.current_project['layers']:
        if l['id'] == layer_id:
            deleted_name = l.get('name', '?')
            break
    app.current_project['layers'] = [l for l in app.current_project['layers'] if l['id'] != layer_id]
    app.current_project['is_pristine'] = False
    log_event('delete_layer', {'id': layer_id, 'name': deleted_name, 'remaining_layers': len(app.current_project['layers'])})
    socketio.emit('layer_deleted', {'id': layer_id})
    return jsonify(app.current_project)


@layers_bp.route('/api/layer/<int:layer_id>/canvas', methods=['PUT'])
def move_layer_to_canvas(layer_id):
    """Move or duplicate a layer onto a different canvas.

    Body: ``{canvas_id: "...", mode: "move" | "duplicate"}``. For "move",
    the layer's ``canvas_id`` is updated and offset_x/y + showOffsetX/Y are
    reset to 0,0 (per design Section 5.7). For "duplicate", a clone with a
    fresh layer id is appended at 0,0 in the target canvas.
    """
    data = request.json or {}
    target_id = data.get('canvas_id')
    mode = data.get('mode', 'move')
    if not _find_canvas(target_id):
        return jsonify({'error': 'Target canvas not found'}), 404
    layer = next((l for l in app.current_project['layers'] if l.get('id') == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    if mode == 'duplicate':
        clone = json.loads(json.dumps(layer))
        clone['id'] = app.next_layer_id
        app.next_layer_id += 1
        clone['canvas_id'] = target_id
        clone['offset_x'] = 0
        clone['offset_y'] = 0
        clone['showOffsetX'] = 0
        clone['showOffsetY'] = 0
        # Re-anchor panel coordinates to the clone's new (0, 0) origin in
        # the target canvas. Without this rebuild, panel.x / panel.y stay
        # at their pre-drag absolute positions and the layer renders far
        # off in the new canvas instead of snapping to the top-left.
        # _rebuild_layer_geometry_from_panel_states preserves per-panel
        # hidden / blank / halfTile state.
        _rebuild_layer_geometry_from_panel_states(clone)
        app.current_project['layers'].append(clone)
        log_event('layer_duplicate_to_canvas', {
            'src_layer_id': layer_id, 'new_layer_id': clone['id'],
            'target_canvas_id': target_id,
        })
    else:
        layer['canvas_id'] = target_id
        layer['offset_x'] = 0
        layer['offset_y'] = 0
        layer['showOffsetX'] = 0
        layer['showOffsetY'] = 0
        # Same panel re-anchor as the duplicate branch above.
        _rebuild_layer_geometry_from_panel_states(layer)
        log_event('layer_move_to_canvas', {
            'layer_id': layer_id, 'target_canvas_id': target_id,
        })
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@layers_bp.route('/api/layer/<int:layer_id>/show_canvas', methods=['PUT'])
def move_layer_to_show_canvas(layer_id):
    """v0.8.5: Reassign a layer's *Show Look* canvas without touching its
    Pixel Map / Cabinet ID canvas membership or its panel geometry.

    Body: ``{show_canvas_id: "..." | null}``. ``null`` clears the override
    so Show Look falls back to mirroring ``canvas_id``. Does NOT mutate
    ``canvas_id``, ``offset_x/y``, ``panels``, or ``showOffsetX/Y`` (the
    drag has already updated showOffsetX/Y in-place via the regular PUT
    path; this endpoint only stamps the new show-canvas membership).
    """
    data = request.json or {}
    target_id = data.get('show_canvas_id')  # may be None
    if target_id is not None and not _find_canvas(target_id):
        return jsonify({'error': 'Target canvas not found'}), 404
    layer = next((l for l in app.current_project['layers'] if l.get('id') == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    layer['show_canvas_id'] = target_id
    log_event('layer_move_to_show_canvas', {
        'layer_id': layer_id, 'target_show_canvas_id': target_id,
    })
    app.current_project['is_pristine'] = False
    socketio.emit('project_updated', app.current_project)
    return jsonify(app.current_project)


@layers_bp.route('/api/layer/<int:layer_id>/panel/<int:panel_id>/toggle', methods=['POST'])
def toggle_panel_blank(layer_id, panel_id):
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    panel = next((p for p in layer['panels'] if p['id'] == panel_id), None)
    if not panel:
        return jsonify({'error': 'Panel not found'}), 404
    
    panel['blank'] = not panel['blank']
    log_event('toggle_panel_blank', {'layer_id': layer_id, 'panel_id': panel_id, 'blank': panel['blank']})
    socketio.emit('panel_updated', {'layer_id': layer_id, 'panel': panel})
    return jsonify(panel)

@layers_bp.route('/api/layer/<int:layer_id>/panel/<int:panel_id>/toggle_hidden', methods=['POST'])
def toggle_panel_hidden(layer_id, panel_id):
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    panel = next((p for p in layer['panels'] if p['id'] == panel_id), None)
    if not panel:
        return jsonify({'error': 'Panel not found'}), 404
    
    hidden = not panel.get('hidden', False)
    panel['hidden'] = hidden
    # v0.10.8.1: hiding feeds _has_visible_neighbor, which anchors half-tiles,
    # so the geometry has to be re-derived here too. Without it the server's
    # own state keeps the old anchoring and restore_project re-anchors it on
    # the next unrelated undo/redo/file load - the panel jumps half a cabinet
    # long after the edit that caused it.
    _rebuild_layer_geometry_from_panel_states(layer)
    log_event('toggle_panel_hidden', {'layer_id': layer_id, 'panel_id': panel_id, 'hidden': hidden})
    # The rebuild regenerates the panels array, so `panel` is now stale. Send
    # the rebuilt layer instead, matching the half-tile routes below.
    socketio.emit('layer_updated', layer)
    return jsonify(layer)

@layers_bp.route('/api/layer/<int:layer_id>/panels/set_hidden', methods=['POST'])
def set_panels_hidden(layer_id):
    """Bulk set hidden state for multiple panels."""
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404

    data = request.json or {}
    panel_states = data.get('panels', [])

    updated = []
    for ps in panel_states:
        panel = next((p for p in layer['panels'] if p['id'] == ps.get('id')), None)
        if panel:
            panel['hidden'] = ps.get('hidden', False)
            updated.append(panel)

    # v0.10.8.1: same as the single toggle - hidden state feeds half-tile
    # anchoring, so re-derive the geometry before anyone sees the layer.
    _rebuild_layer_geometry_from_panel_states(layer)
    log_event('bulk_set_panels_hidden', {'layer_id': layer_id, 'count': len(updated)})
    socketio.emit('layer_updated', layer)
    # Return the rebuilt layer so the client can merge it before snapshotting,
    # the same contract as set_panels_half_tile below.
    return jsonify({'updated': len(updated), 'layer': layer})


@layers_bp.route('/api/layer/<int:layer_id>/panel/<int:panel_id>/set_half_tile', methods=['POST'])
def set_panel_half_tile(layer_id, panel_id):
    """Set a single panel's halfTile value ('none' | 'width' | 'height')."""
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404

    panel = next((p for p in layer['panels'] if p['id'] == panel_id), None)
    if not panel:
        return jsonify({'error': 'Panel not found'}), 404

    data = request.json or {}
    value = data.get('halfTile', 'none')
    if value not in ('none', 'width', 'height'):
        value = 'none'
    panel['halfTile'] = value

    _rebuild_layer_geometry_from_panel_states(layer)
    log_event('set_panel_half_tile', {'layer_id': layer_id, 'panel_id': panel_id, 'halfTile': value})
    socketio.emit('layer_updated', layer)
    return jsonify(layer)


@layers_bp.route('/api/layer/<int:layer_id>/panels/set_half_tile', methods=['POST'])
def set_panels_half_tile(layer_id):
    """Bulk set halfTile state for multiple panels.

    Body: { panels: [{ id, halfTile: 'none' | 'width' | 'height' }, ...] }
    """
    layer = next((l for l in app.current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404

    data = request.json or {}
    panel_states = data.get('panels', [])

    updated = 0
    for ps in panel_states:
        panel = next((p for p in layer['panels'] if p['id'] == ps.get('id')), None)
        if not panel:
            continue
        value = ps.get('halfTile', 'none')
        if value not in ('none', 'width', 'height'):
            value = 'none'
        panel['halfTile'] = value
        updated += 1

    _rebuild_layer_geometry_from_panel_states(layer)
    log_event('bulk_set_panels_half_tile', {'layer_id': layer_id, 'count': updated})
    socketio.emit('layer_updated', layer)
    # v0.10.8: return the rebuilt layer alongside the count. The rebuild
    # above resizes every panel, so a client that only gets `updated` holds
    # new halfTile flags on stale geometry until the socket event lands -
    # long enough for an undo snapshot to capture the mismatch.
    return jsonify({'updated': updated, 'layer': layer})
