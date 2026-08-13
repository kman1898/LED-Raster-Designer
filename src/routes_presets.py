"""
Screen-layer preset routes (persisted to disk, shared across all clients).

Presets are small JSON files in the per-user presets directory. Imports the
presets dir, log_event, and socketio from app (late-registration pattern).
"""
import os
import json

from flask import Blueprint, request, jsonify

from app import PRESETS_DIR_PATH, log_event, socketio

presets_bp = Blueprint('presets', __name__)


def _sanitize_preset_name(name):
    """Strip path separators and control chars. Returns (safe_name, error_msg|None)."""
    if not isinstance(name, str):
        return None, 'Preset name must be a string'
    name = name.strip()
    if not name:
        return None, 'Preset name cannot be empty'
    if len(name) > 80:
        return None, 'Preset name too long (max 80 chars)'
    # Disallow path traversal and filesystem-unsafe chars
    for ch in ('/', '\\', '..', '\x00'):
        if ch in name:
            return None, f'Preset name cannot contain "{ch}"'
    # Strip control chars
    if any(ord(c) < 32 for c in name):
        return None, 'Preset name cannot contain control characters'
    return name, None


def _preset_path(safe_name):
    return os.path.join(PRESETS_DIR_PATH, f'{safe_name}.json')


@presets_bp.route('/api/presets', methods=['GET'])
def list_presets():
    """Return preset summaries (name + key dimensions) sorted alphabetically.
    Each entry: {name, columns, rows, cabinet_width, cabinet_height, panel_width_mm, panel_height_mm}."""
    entries = []
    try:
        for fname in os.listdir(PRESETS_DIR_PATH):
            if not fname.endswith('.json'):
                continue
            name = fname[:-5]
            summary = {'name': name}
            try:
                with open(os.path.join(PRESETS_DIR_PATH, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for key in ('columns', 'rows', 'cabinet_width', 'cabinet_height',
                            'panel_width_mm', 'panel_height_mm', 'panelWatts'):
                    if key in data:
                        summary[key] = data[key]
            except (OSError, json.JSONDecodeError):
                pass  # Keep the name even if the file is corrupt; frontend handles missing fields
            entries.append(summary)
    except FileNotFoundError:
        pass
    entries.sort(key=lambda e: e['name'].lower())
    log_event('list_presets', {'count': len(entries)})
    # Backwards-compat: keep `presets` as list of names; add `entries` with summaries.
    return jsonify({'presets': [e['name'] for e in entries], 'entries': entries})


@presets_bp.route('/api/presets/<name>', methods=['GET'])
def get_preset(name):
    safe_name, err = _sanitize_preset_name(name)
    if err:
        return jsonify({'error': err}), 400
    path = _preset_path(safe_name)
    if not os.path.isfile(path):
        return jsonify({'error': 'Preset not found'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({'error': f'Failed to read preset: {e}'}), 500
    log_event('get_preset', {'name': safe_name})
    return jsonify({'name': safe_name, 'data': data})


@presets_bp.route('/api/presets/<name>', methods=['PUT'])
def save_preset(name):
    safe_name, err = _sanitize_preset_name(name)
    if err:
        return jsonify({'error': err}), 400
    payload = request.json or {}
    data = payload.get('data')
    if not isinstance(data, dict):
        return jsonify({'error': 'Preset data must be an object'}), 400
    path = _preset_path(safe_name)
    existed = os.path.isfile(path)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        return jsonify({'error': f'Failed to write preset: {e}'}), 500
    log_event('save_preset', {'name': safe_name, 'overwrote': existed, 'keys': list(data.keys())})
    socketio.emit('presets_updated')
    return jsonify({'status': 'success', 'name': safe_name, 'overwrote': existed})


@presets_bp.route('/api/presets/<name>', methods=['DELETE'])
def delete_preset(name):
    safe_name, err = _sanitize_preset_name(name)
    if err:
        return jsonify({'error': err}), 400
    path = _preset_path(safe_name)
    if not os.path.isfile(path):
        return jsonify({'error': 'Preset not found'}), 404
    try:
        os.remove(path)
    except OSError as e:
        return jsonify({'error': f'Failed to delete preset: {e}'}), 500
    log_event('delete_preset', {'name': safe_name})
    socketio.emit('presets_updated')
    return jsonify({'status': 'success'})
