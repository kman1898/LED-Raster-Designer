"""
Named panel layouts (persisted to disk, shared across all clients).

A layout is where each panel sits, its sizes and its folds - the shape
layout.js snapshots. Each screen keeps its own CURRENT arrangement in its
browser; these are the named ones anyone connected can switch to, kept in
one JSON file beside the presets folder, so they survive a restart and a
new version. The browser re-checks a layout before it applies one; this end
only refuses what could not be one, so a bad file or request can never
reach a screen as something it cannot read.
"""
import json
import os
import re

from flask import Blueprint, request, jsonify

from app import PRESETS_DIR_PATH, log_event

layouts_bp = Blueprint('layouts', __name__)

# Beside the presets folder: per-user data for a frozen build, next to the
# source when run from it. Tests point this at a scratch file.
LAYOUTS_FILE = os.path.join(os.path.dirname(PRESETS_DIR_PATH), 'layouts', 'layouts.json')

MAX_LAYOUTS = 50
MAX_NAME = 60
PANELS = {'settings', 'screens', 'hardware'}
BARS = {'menu', 'status', 'tabs'}
EDGES = {'left', 'right', 'top', 'bottom'}
FOLD_KEYS = {'left', 'right', 'dock'}
SIZE_KEY = re.compile(r'^lrd_[a-z_]+$')


def _clean_name(name):
    if not isinstance(name, str):
        return None
    name = ' '.join(name.split())
    if not name or len(name) > MAX_NAME:
        return None
    return name


def _valid_layout(layout):
    if not isinstance(layout, dict) or layout.get('v') != 1:
        return False
    rings = layout.get('rings')
    if not isinstance(rings, list) or not rings or len(rings) > 12:
        return False
    for r in rings:
        if not isinstance(r, dict) or r.get('edge') not in EDGES:
            return False
        if not (r.get('panel') in PANELS or r.get('bar') in BARS):
            return False
    sizes = layout.get('sizes', {})
    if not isinstance(sizes, dict) or len(sizes) > 20:
        return False
    for k, v in sizes.items():
        if not SIZE_KEY.match(str(k)):
            return False
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 < v < 5000):
            return False
    folds = layout.get('folds', {})
    if not isinstance(folds, dict):
        return False
    return all(k in FOLD_KEYS and isinstance(v, bool) for k, v in folds.items())


def _read():
    try:
        with open(LAYOUTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get('layouts') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [i for i in items
            if isinstance(i, dict) and _clean_name(i.get('name')) and _valid_layout(i.get('layout'))]


def _write(items):
    os.makedirs(os.path.dirname(LAYOUTS_FILE), exist_ok=True)
    tmp = LAYOUTS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'layouts': items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LAYOUTS_FILE)


def _sorted(items):
    return sorted(items, key=lambda i: i['name'].lower())


@layouts_bp.route('/api/layouts', methods=['GET'])
def list_layouts():
    return jsonify({'layouts': _sorted(_read())})


@layouts_bp.route('/api/layouts', methods=['PUT'])
def save_layout():
    """Save under a name; a layout already under that name is replaced."""
    data = request.get_json(silent=True) or {}
    name = _clean_name(data.get('name'))
    layout = data.get('layout')
    if not name:
        return jsonify({'error': f'a layout needs a name of 1 to {MAX_NAME} characters'}), 400
    if not _valid_layout(layout):
        log_event('layout_save_rejected', {'name': name})
        return jsonify({'error': 'that is not a layout this app can open'}), 400
    items = [i for i in _read() if i['name'].lower() != name.lower()]
    if len(items) >= MAX_LAYOUTS:
        return jsonify({'error': f'{MAX_LAYOUTS} layouts are saved already - delete one first'}), 400
    items.append({'name': name, 'layout': layout})
    _write(items)
    log_event('layout_saved', {'name': name})
    return jsonify({'layouts': _sorted(items)})


@layouts_bp.route('/api/layouts', methods=['DELETE'])
def delete_layout():
    data = request.get_json(silent=True) or {}
    name = _clean_name(data.get('name'))
    items = _read()
    kept = [i for i in items if not name or i['name'].lower() != name.lower()]
    if len(kept) == len(items):
        return jsonify({'error': 'no layout by that name'}), 404
    _write(kept)
    log_event('layout_deleted', {'name': name})
    return jsonify({'layouts': _sorted(kept)})
