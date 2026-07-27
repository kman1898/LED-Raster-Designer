from flask import Flask, render_template, request, jsonify, make_response, send_from_directory, send_file
from flask_socketio import SocketIO, emit
import json
import uuid
import time
import io
import os
import sys
import datetime
import platform
import subprocess
from PIL import Image
import numpy as np

# v0.8.7: Pillow's default decompression-bomb guard refuses images larger
# than ~89 megapixels. Our PSD scale feature legitimately produces images
# up to PSD's 30000×30000 limit (~900 megapixels), and the input is our
# own renderer (no untrusted file path). Disable the guard so high-scale
# PSD exports don't fail with "Image size exceeds limit ... could be
# decompression bomb DOS attack".
Image.MAX_IMAGE_PIXELS = None


def _empty_psd_layer_mask(psd_layers):
    """Create a no-op layer mask that serializes as absent mask data."""
    class EmptyLayerMask(psd_layers.LayerMask):
        def length(self, header):
            return 0

        def total_length(self, header):
            return 4

        def write(self, fd, header):
            fd.write(b'\x00\x00\x00\x00')

    return EmptyLayerMask()


# Support PyInstaller --onedir bundle: resolve templates/static from _MEIPASS
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.config['SECRET_KEY'] = 'led-raster-designer-secret'
socketio = SocketIO(app, cors_allowed_origins="*")
APP_NAME = 'LED Raster Designer'


def _user_data_paths():
    """Return (log_dir, presets_dir).

    For a FROZEN build we write to the OS-standard per-user locations so the
    .app bundle stays read-only / notarizable and can simply be dropped into
    /Applications (it never writes next to itself, which previously forced a
    containing folder and broke writing from /Applications). Running from
    source keeps logs/presets next to the script for easy dev access.
    """
    frozen = getattr(sys, 'frozen', False)
    home = os.path.expanduser('~')
    if frozen and sys.platform == 'darwin':
        # macOS standard: ~/Library/Logs/<App> and ~/Library/Application Support/<App>
        log_dir = os.path.join(home, 'Library', 'Logs', APP_NAME)
        presets_dir = os.path.join(home, 'Library', 'Application Support', APP_NAME, 'presets')
    elif frozen and sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(home, 'AppData', 'Local')
        log_dir = os.path.join(base, APP_NAME, 'logs')
        presets_dir = os.path.join(base, APP_NAME, 'presets')
    elif frozen:
        # Linux frozen: XDG state/data dirs
        state = os.environ.get('XDG_STATE_HOME') or os.path.join(home, '.local', 'state')
        data = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
        log_dir = os.path.join(state, APP_NAME, 'logs')
        presets_dir = os.path.join(data, APP_NAME, 'presets')
    else:
        d = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(d, 'logs')
        presets_dir = os.path.join(d, 'presets')
    return log_dir, presets_dir


LOG_DIR_PATH, PRESETS_DIR_PATH = _user_data_paths()
LOG_FILE_PATH = os.path.join(LOG_DIR_PATH, 'led_raster_designer.log')
LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUPS = 2
os.makedirs(LOG_DIR_PATH, exist_ok=True)
os.environ['_LRD_LOG_DIR'] = LOG_DIR_PATH
print(f'[LED Raster Designer] Log directory: {LOG_DIR_PATH}')

os.makedirs(PRESETS_DIR_PATH, exist_ok=True)
print(f'[LED Raster Designer] Presets directory: {PRESETS_DIR_PATH}')

def prune_log_files():
    try:
        if not os.path.isdir(LOG_DIR_PATH):
            return

        timestamp_archives = []
        legacy_candidates = []
        for name in os.listdir(LOG_DIR_PATH):
            if not name.startswith('led_raster_designer'):
                continue
            full_path = os.path.join(LOG_DIR_PATH, name)
            if os.path.abspath(full_path) == os.path.abspath(LOG_FILE_PATH):
                continue
            if name.startswith('led_raster_designer_') and name.endswith('.log'):
                timestamp_archives.append(full_path)
            else:
                legacy_candidates.append(full_path)

        for path in legacy_candidates:
            try:
                os.remove(path)
            except Exception:
                pass

        timestamp_archives.sort(reverse=True)
        for path in timestamp_archives[LOG_BACKUPS:]:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass

def rotate_logs():
    try:
        if not os.path.exists(LOG_FILE_PATH):
            prune_log_files()
            return
        if os.path.getsize(LOG_FILE_PATH) <= LOG_MAX_BYTES:
            prune_log_files()
            return
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_path = os.path.join(LOG_DIR_PATH, f'led_raster_designer_{ts}.log')
        suffix = 1
        while os.path.exists(archive_path):
            archive_path = os.path.join(LOG_DIR_PATH, f'led_raster_designer_{ts}_{suffix}.log')
            suffix += 1
        os.replace(LOG_FILE_PATH, archive_path)
        prune_log_files()
    except Exception:
        pass

def _migrate_screen_half_flags_to_panel_states(layer, panel_states):
    """Convert legacy screen-level halfFirstColumn/halfLastColumn/halfFirstRow/
    halfLastRow flags into per-panel halfTile values stamped onto panel_states.

    panel_states is keyed by (row, col) tuples so state survives grid resizes.

    Mutates panel_states in place and returns it.
    """
    rows = int(layer.get('rows', 0) or 0)
    cols = int(layer.get('columns', 0) or 0)
    if rows <= 0 or cols <= 0:
        return panel_states
    if panel_states is None:
        panel_states = {}
    half_first_col = bool(layer.get('halfFirstColumn', False))
    half_last_col = bool(layer.get('halfLastColumn', False))
    half_first_row = bool(layer.get('halfFirstRow', False))
    half_last_row = bool(layer.get('halfLastRow', False))
    if not (half_first_col or half_last_col or half_first_row or half_last_row):
        return panel_states
    for r in range(rows):
        for c in range(cols):
            key = (r, c)
            state = panel_states.setdefault(key, {})
            if state.get('halfTile') in ('width', 'height'):
                continue
            if (half_first_row and r == 0) or (half_last_row and r == rows - 1):
                state['halfTile'] = 'height'
            elif (half_first_col and c == 0) or (half_last_col and c == cols - 1):
                state['halfTile'] = 'width'
    # Clear the legacy flags so they don't double-apply on subsequent rebuilds
    layer['halfFirstColumn'] = False
    layer['halfLastColumn'] = False
    layer['halfFirstRow'] = False
    layer['halfLastRow'] = False
    return panel_states


def _build_panels(layer, panel_states=None):
    rows = int(layer.get('rows', 0) or 0)
    cols = int(layer.get('columns', 0) or 0)
    offset_x = float(layer.get('offset_x', 0) or 0)
    offset_y = float(layer.get('offset_y', 0) or 0)
    cabinet_width = float(layer.get('cabinet_width', 0) or 0)
    cabinet_height = float(layer.get('cabinet_height', 0) or 0)

    # One-time migration of legacy screen-level half flags into per-panel state.
    panel_states = _migrate_screen_half_flags_to_panel_states(layer, panel_states or {})

    def _half_at(r, c):
        ps = panel_states.get((r, c), {}) if panel_states else {}
        return ps.get('halfTile', 'none')

    # Per-panel width/height, half-tiles render at half cabinet size.
    def panel_w(r, c):
        return cabinet_width / 2 if _half_at(r, c) == 'width' else cabinet_width

    def panel_h(r, c):
        return cabinet_height / 2 if _half_at(r, c) == 'height' else cabinet_height

    # Column width = max width across all panels in that column. Row height = max
    # across the row. So a row where every panel is half-height collapses to
    # half-height (matching the legacy halfFirstRow behavior); a mixed row stays
    # full-height with the half panels rendering shorter inside their slot.
    col_widths = []
    for c in range(cols):
        widths = [panel_w(r, c) for r in range(rows)] or [cabinet_width]
        col_widths.append(max(widths))
    row_heights = []
    for r in range(rows):
        heights = [panel_h(r, c) for c in range(cols)] or [cabinet_height]
        row_heights.append(max(heights))

    col_x = []
    x_cursor = offset_x
    for c in range(cols):
        col_x.append(x_cursor)
        x_cursor += col_widths[c]

    row_y = []
    y_cursor = offset_y
    for r in range(rows):
        row_y.append(y_cursor)
        y_cursor += row_heights[r]

    # Helper: is the panel at (r, c) a visible (non-hidden) cabinet?
    def _has_visible_neighbor(r, c):
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return False
        ps = panel_states.get((r, c), {}) if panel_states else {}
        return not ps.get('hidden', False)

    panels = []
    panel_num = 1
    for r in range(rows):
        for c in range(cols):
            state = panel_states.get((r, c), {}) if panel_states else {}
            half_tile = state.get('halfTile', 'none')
            if half_tile not in ('width', 'height'):
                half_tile = 'none'

            pw = panel_w(r, c)
            ph = panel_h(r, c)
            slot_w = col_widths[c]
            slot_h = row_heights[r]
            x = col_x[c]
            y = row_y[r]

            # Anchor half-tiles to their neighbor side so the visible cabinet
            # connects to the rest of the wall, the "missing" half sits on
            # the wall's outer edge (no neighbor side), not between this
            # cabinet and its neighbor.
            if half_tile == 'height' and ph < slot_h:
                has_above = _has_visible_neighbor(r - 1, c)
                has_below = _has_visible_neighbor(r + 1, c)
                if not has_above and has_below:
                    # Missing half on top, anchor to bottom of slot.
                    y = row_y[r] + (slot_h - ph)
                # else: anchor to top (default; covers top-anchored top edges
                # and the interior/all-neighbors fallback).
            elif half_tile == 'width' and pw < slot_w:
                has_left = _has_visible_neighbor(r, c - 1)
                has_right = _has_visible_neighbor(r, c + 1)
                if not has_left and has_right:
                    # Missing half on left, anchor to right of slot.
                    x = col_x[c] + (slot_w - pw)
                # else: anchor to left (default).

            panel = {
                'id': panel_num,
                'number': panel_num,
                'row': r,
                'col': c,
                'x': x,
                'y': y,
                'width': pw,
                'height': ph,
                'blank': state.get('blank', False),
                'hidden': state.get('hidden', False),
                'halfTile': half_tile,
                'is_color1': (r + c) % 2 == 0
            }
            panels.append(panel)
            panel_num += 1
    return panels

def _layer_bounds(layer):
    panels = layer.get('panels') or []
    if panels:
        min_x = min(p.get('x', 0) for p in panels)
        min_y = min(p.get('y', 0) for p in panels)
        max_x = max((p.get('x', 0) + p.get('width', 0)) for p in panels)
        max_y = max((p.get('y', 0) + p.get('height', 0)) for p in panels)
        return {
            'x': min_x,
            'y': min_y,
            'width': max(0, max_x - min_x),
            'height': max(0, max_y - min_y),
        }
    width = (layer.get('columns', 0) or 0) * (layer.get('cabinet_width', 0) or 0)
    height = (layer.get('rows', 0) or 0) * (layer.get('cabinet_height', 0) or 0)
    return {'x': layer.get('offset_x', 0), 'y': layer.get('offset_y', 0), 'width': width, 'height': height}

def log_event(action, details=None, source='server'):
    try:
        os.makedirs(LOG_DIR_PATH, exist_ok=True)
        rotate_logs()
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        payload = {
            'timestamp': ts,
            'source': source,
            'action': action,
            'details': details or {}
        }
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(payload, ensure_ascii=False) + '\n')
    except Exception:
        pass

@app.before_request
def log_request():
    try:
        # Skip logging static files, the log endpoint, and routine API calls to reduce noise
        # The individual API handlers log their own meaningful events
        if request.path == '/api/log' or request.path.startswith('/static/'):
            return
        if request.path == '/' :
            log_event('http_request', {
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr
            })
    except Exception:
        pass


@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """Catch all unhandled exceptions and log them to the log file."""
    import traceback
    error_detail = traceback.format_exc()
    log_event('unhandled_exception', {
        'error': str(e),
        'type': type(e).__name__,
        'path': request.path if request else 'unknown',
        'method': request.method if request else 'unknown',
        'traceback': error_detail,
    })
    return jsonify({'error': f'Internal server error: {type(e).__name__}'}), 500


@app.errorhandler(404)
def handle_not_found(e):
    """Log 404s for API routes (helps catch typos in client code)."""
    if request.path.startswith('/api/'):
        log_event('api_not_found', {
            'path': request.path,
            'method': request.method,
        })
        return jsonify({'error': f'Not found: {request.path}'}), 404
    return e

# Unique session ID generated on server start - changes each time server restarts
SERVER_SESSION_ID = str(uuid.uuid4())
SERVER_START_TIME = int(time.time() * 1000)  # milliseconds

# Counter for unique layer IDs - never reuses IDs
next_layer_id = 1

# Multi-canvas (v0.8) support. The project file format gains a `canvases`
# array, a `format_version` string, and an `active_canvas_id`. v0.7 projects
# are auto-migrated on load. Slice 1 is additive only, root-level
# raster_width/raster_height/show_raster_*/perspectives are still written so
# the existing single-canvas client keeps working until later slices switch
# the source-of-truth to per-canvas fields.
CURRENT_FORMAT_VERSION = "0.8"
DEFAULT_CANVAS_PALETTE = [
    "#4A90E2", "#F5A623", "#7ED321", "#BD10E0",
    "#D0021B", "#50E3C2", "#F8E71C", "#9013FE",
]


def _make_default_canvas(project, idx=0):
    """Build a canvas dict from a project's current root-level raster fields.

    Used both when constructing a fresh project (idx=0) and when migrating a
    v0.7 project. The canvas inherits the project's existing raster /
    perspective values so the migration is loss-free.
    """
    return {
        'id': f'c{idx + 1}',
        'name': f'Canvas {idx + 1}',
        'color': DEFAULT_CANVAS_PALETTE[idx % len(DEFAULT_CANVAS_PALETTE)],
        'workspace_x': 0,
        'workspace_y': 0,
        'raster_width': project.get('raster_width', 1920),
        'raster_height': project.get('raster_height', 1080),
        'show_raster_width': project.get(
            'show_raster_width', project.get('raster_width', 1920)
        ),
        'show_raster_height': project.get(
            'show_raster_height', project.get('raster_height', 1080)
        ),
        'data_flow_perspective': project.get('data_flow_perspective', 'front'),
        'power_perspective': project.get('power_perspective', 'front'),
        'visible': True,
    }


def _migrate_to_v0_8(project):
    """Idempotent additive migrator from v0.7 to v0.8.

    - If the project already declares format_version 0.8 AND has canvases AND
      every layer has a canvas_id, this is a no-op.
    - Otherwise: build a default canvas from the project's existing raster
      fields, assign every layer to it, set format_version/active_canvas_id.
      Root-level raster fields are intentionally left in place, Slice 1 is
      additive so the existing single-canvas client keeps reading them.

    Returns (project, did_migrate). did_migrate is True only when the
    structure actually changed, so callers can avoid noisy log spam.
    """
    if not isinstance(project, dict):
        return project, False
    canvases = project.get('canvases')
    layers = project.get('layers') or []
    has_canvases = isinstance(canvases, list) and len(canvases) > 0
    all_layers_assigned = all(
        isinstance(l, dict) and l.get('canvas_id') for l in layers
    )
    if (
        project.get('format_version') == CURRENT_FORMAT_VERSION
        and has_canvases
        and all_layers_assigned
    ):
        return project, False

    if not has_canvases:
        canvas = _make_default_canvas(project, 0)
        project['canvases'] = [canvas]
        project['active_canvas_id'] = canvas['id']
    else:
        # Canvases exist but format_version may be older or layers unassigned.
        if not project.get('active_canvas_id'):
            project['active_canvas_id'] = project['canvases'][0]['id']

    default_canvas_id = project['canvases'][0]['id']
    for layer in layers:
        if isinstance(layer, dict) and not layer.get('canvas_id'):
            layer['canvas_id'] = default_canvas_id

    project['format_version'] = CURRENT_FORMAT_VERSION
    _mirror_active_canvas_to_root(project)
    return project, True


def _mirror_active_canvas_to_root(project):
    """Slice 6 compatibility shim.

    Source-of-truth for raster fields moved to the per-canvas object. The
    server keeps writing the mirrored values back onto the project root
    (raster_width, raster_height, show_raster_*, *_perspective) so that:
      - Older test code reading project['raster_width'] keeps working.
      - A client that hasn't yet upgraded to per-canvas reads still sees
        sane numbers (the active canvas's raster).
      - The PNG / PDF / PSD export paths (which still read root raster
        for the export size) keep working until they're rewritten per
        canvas in a later slice.

    No-op on projects with no canvases (pre-Slice-1 legacy state).
    """
    if not isinstance(project, dict):
        return project
    canvases = project.get('canvases') or []
    if not canvases:
        return project
    active_id = project.get('active_canvas_id')
    active = next((c for c in canvases if isinstance(c, dict) and c.get('id') == active_id), None)
    if active is None:
        active = canvases[0]
    for key in (
        'raster_width', 'raster_height',
        'show_raster_width', 'show_raster_height',
        'data_flow_perspective', 'power_perspective',
    ):
        val = active.get(key)
        if val is not None:
            project[key] = val
    return project


def _build_initial_project():
    """Build the in-memory project dict used at app startup and by /new."""
    project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        # Show Look has its own raster size, defaults to the same as the
        # processor raster so existing projects open identically. The Show
        # Look raster is used as the export canvas size for the Show Look /
        # Data / Power views (which all render at the show position).
        'show_raster_width': 1920,
        'show_raster_height': 1080,
        # Wiring view perspective per tab. 'front' shows the layout as the
        # audience sees it (matching Show Look). 'back' horizontally mirrors
        # the geometry so the techs working behind the wall see it from their
        # perspective. Labels stay readable in either view. Per-tab so a Data
        # tech and a Power tech can configure independently.
        'data_flow_perspective': 'front',
        'power_perspective': 'front',
        'layers': [],
        'is_pristine': True,
    }
    # Pre-populate v0.8 fields so a fresh project already passes the
    # migrator as a no-op. Root raster fields are still present for the
    # client's current single-canvas code paths.
    _migrate_to_v0_8(project)
    return project


current_project = _build_initial_project()

# Add a default layer on startup
def initialize_default_layer():
    """Add a default layer when the app starts"""
    if len(current_project['layers']) == 0:
        default_layer = create_layer(
            name='Screen1',
            columns=8,
            rows=5,
            cabinet_width=128,
            cabinet_height=128,
            offset_x=0,
            offset_y=0
        )
        # Assign to the active canvas. _build_initial_project / migrator
        # guarantees at least one canvas exists at this point.
        canvases = current_project.get('canvases') or []
        if canvases:
            default_layer['canvas_id'] = current_project.get(
                'active_canvas_id', canvases[0]['id']
            )
        current_project['layers'].append(default_layer)

def _assign_canvas_id(layer, data=None):
    """Stamp a layer with a canvas_id (caller-provided or active canvas).

    Centralised so all add-layer paths (screen / image / text) get the same
    behaviour: respect a client-supplied canvas_id if it matches an existing
    canvas, otherwise fall back to the project's active canvas. Guarantees
    layer['canvas_id'] is set to a non-empty string when at least one
    canvas exists.
    """
    canvases = current_project.get('canvases') or []
    if not canvases:
        return
    valid_ids = {c.get('id') for c in canvases if isinstance(c, dict)}
    requested = (data or {}).get('canvas_id') if isinstance(data, dict) else None
    if requested and requested in valid_ids:
        layer['canvas_id'] = requested
    else:
        layer['canvas_id'] = current_project.get(
            'active_canvas_id', canvases[0].get('id')
        )


def _seed_data_with_canvas_defaults(data):
    """v0.8 Slice 8: when the client adds a NEW screen layer to a canvas that
    already has screens, seed the request payload with hardware/processor
    settings from the most recently added screen in that canvas. Mutates
    and returns ``data``. This makes each canvas behave like its own preset
    bucket, adding a second SR cabinet inherits SR's voltage/amperage/
    panel size/etc. without the user reconfiguring.

    Runs BEFORE create_layer() so positional args (cabinet_width/height)
    flow through correctly and panels are built at the right size. Only
    fills fields the caller did NOT explicitly provide, so duplicates and
    pastes (which carry full settings) are unaffected.
    """
    if not isinstance(data, dict):
        return data
    canvas_id = data.get('canvas_id') or current_project.get('active_canvas_id')
    if not canvas_id:
        return data
    siblings = [
        l for l in current_project.get('layers', [])
        if isinstance(l, dict)
        and l.get('canvas_id') == canvas_id
        and (l.get('type') or 'screen') == 'screen'
    ]
    if not siblings:
        return data
    # Most recently added sibling = highest id.
    try:
        donor = max(siblings, key=lambda l: int(l.get('id') or 0))
    except Exception:
        donor = siblings[-1]
    inheritable = (
        'processorType', 'lowLatency', 'bitDepth', 'frameRate',
        'powerVoltage', 'powerVoltageCustom', 'powerAmperage', 'powerAmperageCustom',
        'panelWatts',
        'panel_width_mm', 'panel_height_mm', 'panel_weight', 'weight_unit',
        'cabinet_width', 'cabinet_height',
        'border_color', 'border_color_pixel', 'border_color_cabinet',
        'border_color_data', 'border_color_power',
    )
    for field in inheritable:
        if field in data:
            continue  # caller specified, respect it
        if field in donor and donor[field] is not None:
            data[field] = donor[field]
    return data


def sync_next_layer_id():
    """Rebase next_layer_id to avoid duplicate IDs after project load/restore."""
    global next_layer_id
    layers = current_project.get('layers', []) if isinstance(current_project, dict) else []
    max_id = 0
    for layer in layers:
        try:
            layer_id = int(layer.get('id', 0))
        except Exception:
            layer_id = 0
        if layer_id > max_id:
            max_id = layer_id
    next_layer_id = max_id + 1

def create_layer(name, columns, rows, cabinet_width, cabinet_height, offset_x=0, offset_y=0):
    global next_layer_id
    layer = {
        'id': next_layer_id,
        'type': 'screen',
        'name': name,
        'visible': True,
        'columns': columns,
        'rows': rows,
        'cabinet_width': cabinet_width,
        'cabinet_height': cabinet_height,
        'offset_x': offset_x,
        'offset_y': offset_y,
        # Show Look position, used by the Show Look / Data / Power tabs.
        # Defaults to the same values as offset_x/offset_y until the user
        # rearranges the layer in the Show Look view, at which point the
        # two positions diverge: pixel-map / cabinet-id keep using
        # offset_x/y (the processor's expected layout) while show-look /
        # data / power use showOffsetX/Y (the real-world stage layout).
        'showOffsetX': offset_x,
        'showOffsetY': offset_y,
        'panel_width_mm': 500.0,
        'panel_height_mm': 500.0,
        'panel_weight': 20.0,
        'halfFirstColumn': False,
        'halfLastColumn': False,
        'halfFirstRow': False,
        'halfLastRow': False,
        'weight_unit': 'kg',
        'rotation': 0,
        'color1': {'r': 64, 'g': 70, 'b': 128},
        'color2': {'r': 149, 'g': 156, 'b': 184},
        'show_numbers': True,
        'number_size': 30,
        'show_panel_borders': True,  # Default ON
        'panel_border_width': 2,     # LED pixels
        'border_color': '#ffffff',
        'border_color_pixel': '#ffffff',
        'border_color_cabinet': '#ffffff',
        'border_color_data': '#ffffff',
        'border_color_power': '#ffffff',
        'show_circle_with_x': True,  # New toggle, default ON
        # Cabinet ID settings
        'cabinetIdStyle': 'column-row',  # 'column-row' | 'row-column' | 'row-col'
        'cabinetIdPosition': 'center',   # 'top-left' | 'center'
        'cabinetIdColor': '#ffffff',
        # Data Flow settings
        'dataFlowPattern': 's-tl-rd',  # S-shape pattern
        'arrowLineWidth': 6,
        'arrowSize': 12,
        'arrowColor': '#0042AA',
        'dataFlowColor': '#FFFFFF',
        'dataFlowLabelSize': 30,
        'primaryColor': '#00FF00',
        'primaryTextColor': '#000000',
        'backupColor': '#FF0000',
        'backupTextColor': '#FFFFFF',
        'flowPattern': 'tl-h',
        'bitDepth': 8,
        'frameRate': 60,
        # v0.10.9: per-layer Low Latency. Off by default; the client overlays
        # the user's preference on top, same as bitDepth/frameRate.
        'lowLatency': False,
        # Power settings defaults
        'powerVoltage': 110,
        'powerVoltageCustom': 110,
        'powerAmperage': 15,
        'powerAmperageCustom': 15,
        'panelWatts': 200,
        'powerMaximize': False,
        'powerOrganized': True,
        'powerCustomPath': False,
        'powerFlowPattern': 'tl-h',
        'powerLineWidth': 8,
        'powerLineColor': '#FF0000',
        'powerArrowColor': '#0042AA',
        'powerRandomColors': False,
        'powerColorCodedView': False,
        'powerCircuitColors': {
            'A': '#BC382F',
            'B': '#CC6B30',
            'C': '#D2E94D',
            'D': '#2CF82B',
            'E': '#2145DC',
            'F': '#7414F5'
        },
        'powerLabelSize': 14,
        'powerLabelBgColor': '#D95000',
        'powerLabelTextColor': '#000000',
        'powerLabelTemplate': 'S1-#',
        'powerLabelOverrides': {},
        'powerCustomPaths': {},
        'powerCustomIndex': 1,
        # Per-layer label settings
        'showLabelName': True,
        'showLabelSizePx': True,  # Default ON - shows pixel dimensions
        'showLabelSizeM': False,
        'showLabelSizeFt': False,
        'showLabelWeight': False,
        'showLabelInfo': False,
        'infoLabelSize': 14,
        'labelsColor': '#ffffff',
        'labelsFontSize': 30,
        # Screen name sizes per tab
        'screenNameSizeCabinet': 30,
        'screenNameSizeDataFlow': 30,
        'screenNameSizePower': 30,
        # Per-layer offset settings
        'showOffsetTL': False,
        'showOffsetTR': False,
        'showOffsetBL': False,
        'showOffsetBR': False,
        'panels': []
    }
    
    layer['panels'] = _build_panels(layer)
    
    next_layer_id += 1  # Increment for next layer
    return layer

def create_image_layer(name, image_data, image_width, image_height, offset_x=0, offset_y=0):
    global next_layer_id
    layer = {
        'id': next_layer_id,
        'type': 'image',
        'name': name,
        'visible': True,
        'offset_x': offset_x,
        'offset_y': offset_y,
        'imageData': image_data,
        'imageWidth': image_width,
        'imageHeight': image_height,
        'imageScale': 1.0,
        # Keep labels hidden by default for image layers
        'showLabelName': False,
        'showLabelSizePx': False,
        'showLabelSizeM': False,
        'showLabelSizeFt': False,
        'showLabelWeight': False,
        'showLabelInfo': False,
        'labelsColor': '#ffffff',
        'labelsFontSize': 30,
        'infoLabelSize': 14,
        # Keep panel-related fields empty to avoid accidental use
        'panels': []
    }
    next_layer_id += 1
    return layer

def create_text_layer(name, text_content='', offset_x=0, offset_y=0, text_width=400, text_height=100):
    global next_layer_id
    layer = {
        'id': next_layer_id,
        'type': 'text',
        'name': name,
        'visible': True,
        'offset_x': offset_x,
        'offset_y': offset_y,
        'textContent': text_content,
        'textContentPixelMap': '',
        'textContentCabinetId': '',
        'textContentShowLook': '',
        'textContentDataFlow': '',
        'textContentPower': '',
        # v0.8.3: by default the shared `textContent` field is used on every
        # tab. The user can flip an override per tab to break out a tab's
        # content into its own `textContent<Tab>` field.
        'textContentOverridePixelMap': False,
        'textContentOverrideCabinetId': False,
        'textContentOverrideShowLook': False,
        'textContentOverrideDataFlow': False,
        'textContentOverridePower': False,
        'textWidth': text_width,
        'textHeight': text_height,
        'fontSize': 24,
        'fontFamily': 'Arial',
        'fontColor': '#ffffff',
        'bgColor': '#000000',
        'bgOpacity': 0.7,
        'textAlign': 'left',
        'textPadding': 12,
        'showBorder': True,
        'borderColor': '#555555',
        'showOnPixelMap': True,
        'showOnCabinetId': True,
        'showOnDataFlow': True,
        'showOnPower': True,
        'showOnShowLook': True,
        'showRasterSize': False,
        'showProjectName': False,
        'showDate': False,
        'showPrimaryPorts': False,
        'showBackupPorts': False,
        'showCircuits': False,
        'showSinglePhase': False,
        'showThreePhase': False,
        'fontBold': False,
        'fontItalic': False,
        'fontUnderline': False,
        # Keep label/panel fields empty
        'showLabelName': False,
        'showLabelSizePx': False,
        'showLabelSizeM': False,
        'showLabelSizeFt': False,
        'showLabelWeight': False,
        'showLabelInfo': False,
        'labelsColor': '#ffffff',
        'labelsFontSize': 30,
        'infoLabelSize': 14,
        'panels': []
    }
    next_layer_id += 1
    return layer

@app.route('/')
def index():
    # Initialize default layer if project is empty
    initialize_default_layer()
    log_event('page_load', {'path': '/'})
    # Expose the host OS so the client can show the custom (Apple-style) color
    # picker on Windows while leaving the native picker in place on macOS.
    response = make_response(render_template('index.html', server_platform=sys.platform))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/static/<path:filename>')
def static_files(filename):
    response = send_from_directory('static', filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ── Server-side preferences (shared across all clients) ──
# The GET/PUT routes live in routes_preferences.py; this stays the authoritative
# store because the canvas auto-placement logic below also reads it. The
# blueprint reassigns it via the app module attribute so changes stay visible here.
server_preferences = {}



# ---------------------------------------------------------------------------
# Multi-canvas (v0.8) Slice 2: canvas CRUD endpoints.
#
# These mutate ``current_project['canvases']`` in place. The sidebar UI
# routes all canvas operations through these endpoints; layer rendering in
# the workspace is unchanged in Slice 2.
# ---------------------------------------------------------------------------


def _next_canvas_id():
    """Pick the next free canvas id of the form ``c<N>``.

    Scans existing canvases, finds the max numeric suffix, and returns one
    above. Falls back to ``c1`` if the array is empty.
    """
    canvases = current_project.get('canvases') or []
    max_n = 0
    for c in canvases:
        cid = (c or {}).get('id', '')
        if isinstance(cid, str) and cid.startswith('c'):
            try:
                n = int(cid[1:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f'c{max_n + 1}'


def _next_canvas_color():
    """Pick the first palette color not already used by another canvas.

    If all 8 palette colors are taken, falls back to palette[N % 8] where N
    is the count of existing canvases (so we still pick a sensible default
    without surprising the user with random hex values).
    """
    canvases = current_project.get('canvases') or []
    used = {(c or {}).get('color') for c in canvases}
    for color in DEFAULT_CANVAS_PALETTE:
        if color not in used:
            return color
    return DEFAULT_CANVAS_PALETTE[len(canvases) % len(DEFAULT_CANVAS_PALETTE)]


def _find_canvas(canvas_id):
    for c in current_project.get('canvases') or []:
        if c.get('id') == canvas_id:
            return c
    return None


def _next_canvas_workspace_position():
    """Pick a workspace position for a freshly created canvas.

    Auto-places the new canvas to the right of the existing rightmost
    canvas, leaving a horizontal gap controlled by the ``canvasGap``
    server preference (default 50 px). Vertical position resets to 0
    so canvases line up along the workspace's top edge by default.

    Returns ``(workspace_x, workspace_y)``.
    """
    canvases = current_project.get('canvases') or []
    # v0.8 Slice 9: default gap is 0, most LED installs are abutting walls,
    # not floating screens. Server preference still wins when set.
    gap = 0
    try:
        pref_gap = (server_preferences or {}).get('canvasGap')
        if pref_gap is not None:
            pref_gap = float(pref_gap)
            if pref_gap >= 0:
                gap = pref_gap
    except (TypeError, ValueError):
        pass
    if not canvases:
        return (0, 0)
    rightmost = max(
        (c.get('workspace_x') or 0) + (c.get('raster_width') or 0)
        for c in canvases
    )
    return (rightmost + gap, 0)


def _next_duplicate_canvas_name(src_name):
    """Pick a name for the duplicate of a canvas named ``src_name``.

    Strips a trailing " <number>" from the source name to get the base,
    then finds the highest existing trailing-number across all canvases
    sharing that base, and returns "<base> <max+1>". Examples:

        "Canvas 2" + ["Canvas 1", "Canvas 2"] → "Canvas 3"
        "EDC"      + ["EDC"]                  → "EDC 1"
        "EDC 1"    + ["EDC", "EDC 1"]         → "EDC 2"
    """
    import re
    name = (src_name or 'Canvas').strip()
    m = re.match(r'^(.*?)\s+(\d+)$', name)
    base = (m.group(1) if m else name).strip() or 'Canvas'
    canvases = current_project.get('canvases') or []
    pat = re.compile(r'^' + re.escape(base) + r'(?:\s+(\d+))?$')
    max_n = 0
    for c in canvases:
        cm = pat.match((c.get('name') or '').strip())
        if cm:
            n = int(cm.group(1)) if cm.group(1) else 0
            if n > max_n:
                max_n = n
    return f"{base} {max_n + 1}"


def _rebuild_layer_geometry_from_panel_states(layer):
    """Re-run _build_panels using the layer's current panel states so per-panel
    halfTile changes propagate into x/y/width/height (column widths and row
    heights may collapse when an entire row/column becomes half).
    """
    states = {}
    # v0.10.8.1: `or []` not a `.get` default - a layer whose 'panels' key is
    # present but null reaches here from restore_project, and the default only
    # applies when the key is missing.
    for p in (layer.get('panels') or []):
        if not isinstance(p, dict):
            continue  # a null/garbage entry in the array must not 500 a restore
        states[(p.get('row', 0), p.get('col', 0))] = {
            'hidden': p.get('hidden', False),
            'blank': p.get('blank', False),
            'halfTile': p.get('halfTile', 'none'),
        }
    layer['panels'] = _build_panels(layer, states)


def render_layer_to_image(layer, raster_width, raster_height, include_borders=True):
    """Render a single layer to a PIL Image with transparency"""
    # Create RGBA image (transparent background)
    img = Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 0))
    pixels = img.load()
    
    # Get layer colors
    color1 = layer.get('color1', {'r': 64, 'g': 70, 'b': 128})
    color2 = layer.get('color2', {'r': 149, 'g': 156, 'b': 184})
    border_color_hex = layer.get('border_color', '#ffffff')
    
    # Parse border color
    border_color = (255, 255, 255)  # default white
    if border_color_hex.startswith('#') and len(border_color_hex) == 7:
        border_color = (
            int(border_color_hex[1:3], 16),
            int(border_color_hex[3:5], 16),
            int(border_color_hex[5:7], 16)
        )
    
    show_borders = layer.get('show_panel_borders', True) and include_borders
    
    # Render each panel
    for panel in layer['panels']:
        if panel.get('hidden', False):
            continue
            
        px = int(panel['x'])
        py = int(panel['y'])
        pw = int(panel['width'])
        ph = int(panel['height'])
        
        # Get panel color
        color = color1 if panel.get('is_color1', True) else color2
        rgb = (color['r'], color['g'], color['b'], 255)
        
        # Fill panel pixels
        for y in range(max(0, py), min(raster_height, py + ph)):
            for x in range(max(0, px), min(raster_width, px + pw)):
                pixels[x, y] = rgb
        
        # Draw borders (2 pixels wide, inside the panel)
        if show_borders:
            border_rgba = (border_color[0], border_color[1], border_color[2], 255)
            # Top and bottom borders (2 pixels each)
            for y in range(max(0, py), min(raster_height, py + 2)):
                for x in range(max(0, px), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
            for y in range(max(0, py + ph - 2), min(raster_height, py + ph)):
                for x in range(max(0, px), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
            # Left and right borders (2 pixels each)
            for y in range(max(0, py), min(raster_height, py + ph)):
                for x in range(max(0, px), min(raster_width, px + 2)):
                    pixels[x, y] = border_rgba
                for x in range(max(0, px + pw - 2), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
    
    return img


# View name mapping
VIEW_NAMES = {
    'pixel-map': 'Pixel Map',
    'cabinet-id': 'Cabinet ID',
    'data-flow': 'Data',
    'power': 'Power'
}


def render_view_to_image(view_mode, include_borders=True):
    """Render a specific view mode to an image"""
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    # Create base image (black background)
    final_img = Image.new('RGB', (raster_width, raster_height), (0, 0, 0))
    
    # For now, render the pixel map view (panels with colors)
    # TODO: Implement different rendering for each view mode
    for layer in current_project['layers']:
        if layer.get('visible', True):
            layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
            # Composite onto final
            final_img.paste(layer_img, mask=layer_img.split()[3])
    
    return final_img


@app.route('/api/export', methods=['POST'])
def export_unified():
    """Unified export endpoint handling PNG, PSD, and PDF formats"""
    import zipfile
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    format_type = data.get('format', 'png')
    views = data.get('views', ['pixel-map'])
    include_borders = data.get('include_borders', True)
    
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    if format_type == 'pdf':
        # PDF: All views combined into one multi-page document
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.pdfgen import canvas as pdf_canvas
            from reportlab.lib.utils import ImageReader
        except ImportError:
            return jsonify({'error': 'PDF export requires reportlab library'}), 500
        
        pdf_bytes = io.BytesIO()
        
        # Calculate page size to match raster aspect ratio
        page_width = raster_width
        page_height = raster_height
        
        c = pdf_canvas.Canvas(pdf_bytes, pagesize=(page_width, page_height))
        
        for view in views:
            # Render this view
            img = render_view_to_image(view, include_borders)
            
            # Add title
            view_name = VIEW_NAMES.get(view, view)
            
            # Draw the image
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
            
            # Add label at top
            c.setFillColorRGB(1, 1, 1)  # White text
            c.setFont("Helvetica-Bold", 24)
            c.drawString(20, page_height - 40, f"{project_name} - {view_name}")
            
            c.showPage()
        
        c.save()
        pdf_bytes.seek(0)
        
        return send_file(
            pdf_bytes,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{project_name}.pdf"
        )
    
    elif format_type == 'psd':
        # PSD: Each view as a separate file with screen layers
        # If multiple views, package in ZIP
        try:
            import pytoshop
            from pytoshop import layers as psd_layers
            from pytoshop.enums import ColorMode
        except ImportError:
            return jsonify({'error': 'PSD export requires pytoshop library. Install with: pip3 install pytoshop'}), 500
        
        if len(views) == 1:
            # Single PSD file
            psd_bytes = create_psd_for_view(views[0], project_name, include_borders)
            view_name = VIEW_NAMES.get(views[0], views[0])
            
            return send_file(
                psd_bytes,
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=f"{project_name} - {view_name}.psd"
            )
        else:
            # Multiple PSDs in a ZIP
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
                for view in views:
                    psd_bytes = create_psd_for_view(view, project_name, include_borders)
                    view_name = VIEW_NAMES.get(view, view)
                    zf.writestr(f"{project_name} - {view_name}.psd", psd_bytes.getvalue())
            
            zip_bytes.seek(0)
            return send_file(
                zip_bytes,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{project_name} - PSD Files.zip"
            )
    
    else:
        # PNG: Each view as a separate file
        if len(views) == 1:
            # Single PNG file
            img = render_view_to_image(views[0], include_borders)
            view_name = VIEW_NAMES.get(views[0], views[0])
            
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return send_file(
                img_bytes,
                mimetype='image/png',
                as_attachment=True,
                download_name=f"{project_name} - {view_name}.png"
            )
        else:
            # Multiple PNGs in a ZIP
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
                for view in views:
                    img = render_view_to_image(view, include_borders)
                    view_name = VIEW_NAMES.get(view, view)
                    
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='PNG')
                    zf.writestr(f"{project_name} - {view_name}.png", img_bytes.getvalue())
            
            zip_bytes.seek(0)
            return send_file(
                zip_bytes,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{project_name} - PNG Files.zip"
            )


def create_psd_for_view(view_mode, project_name, include_borders):
    """Create a PSD file for a specific view with screen layers"""
    import pytoshop
    from pytoshop import layers as psd_layers
    from pytoshop.enums import ColorMode, Compression
    
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    # Create PSD
    psd = pytoshop.PsdFile(num_channels=3, height=raster_height, width=raster_width, color_mode=ColorMode.rgb)
    
    layer_records = []
    
    # Add each screen layer
    for layer in current_project['layers']:
        # Render layer to image
        layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
        
        # Get layer bounds
        bounds = _layer_bounds(layer)
        offset_x = bounds['x']
        offset_y = bounds['y']
        layer_width = bounds['width']
        layer_height = bounds['height']
        
        # Clamp to raster bounds (int() ensures native Python ints for pytoshop)
        left = int(max(0, offset_x))
        top = int(max(0, offset_y))
        right = int(min(raster_width, offset_x + layer_width))
        bottom = int(min(raster_height, offset_y + layer_height))

        if right <= left or bottom <= top:
            continue

        # Crop to content bounds
        cropped_img = layer_img.crop((left, top, right, bottom))
        img_array = np.array(cropped_img.convert('RGB'))

        # Layer name from screen name
        layer_name = layer.get('name', f"Screen {layer['id']}")

        # Create layer record
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if layer.get('visible', True) else 0,
            channels={
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
        )
        layer_records.append(layer_record)

    psd.layer_and_mask_info.layer_info.layer_records = layer_records

    psd_bytes = io.BytesIO()
    psd.write(psd_bytes)
    psd_bytes.seek(0)

    return psd_bytes


@app.route('/api/export/png', methods=['POST'])
def export_png():
    """Export as flattened PNG"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    # Create base image (black background)
    final_img = Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 255))
    
    # Render and composite each visible layer
    for layer in current_project['layers']:
        if layer.get('visible', True):
            layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
            final_img = Image.alpha_composite(final_img, layer_img)
    
    # Convert to RGB for PNG (no transparency needed for final)
    final_rgb = Image.new('RGB', final_img.size, (0, 0, 0))
    final_rgb.paste(final_img, mask=final_img.split()[3])
    
    # Save to bytes
    img_bytes = io.BytesIO()
    final_rgb.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return send_file(
        img_bytes,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"{current_project['name']}.png"
    )


@app.route('/api/export/psd', methods=['POST'])
def export_psd():
    """Export as PSD with layers - each screen as a named layer at correct position"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    try:
        import pytoshop
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError:
        # Fall back to creating a ZIP of individual layer PNGs
        return export_layers_as_zip(include_borders, raster_width, raster_height)
    
    # Create PSD using pytoshop
    psd = pytoshop.PsdFile(num_channels=3, height=raster_height, width=raster_width, color_mode=ColorMode.rgb)
    
    # We need to build layer list
    layer_records = []
    
    # Add each layer (in reverse order so first layer is on bottom in a layer panel)
    for layer in current_project['layers']:
        # Render layer to image (full raster size with transparency)
        layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
        
        # Get layer bounds (where the actual content is)
        bounds = _layer_bounds(layer)
        offset_x = bounds['x']
        offset_y = bounds['y']
        layer_width = bounds['width']
        layer_height = bounds['height']
        
        # Crop to just the layer content area for efficiency
        # But clamp to raster bounds (int() ensures native Python ints for pytoshop)
        left = int(max(0, offset_x))
        top = int(max(0, offset_y))
        right = int(min(raster_width, offset_x + layer_width))
        bottom = int(min(raster_height, offset_y + layer_height))
        
        if right <= left or bottom <= top:
            continue  # Layer is completely outside raster
        
        # Crop the layer image to content bounds
        cropped_img = layer_img.crop((left, top, right, bottom))
        
        # Convert to numpy array (RGB only, no alpha for simplicity)
        img_array = np.array(cropped_img.convert('RGB'))
        
        # Get layer name from screen name
        layer_name = layer.get('name', f"Screen {layer['id']}")
        
        # Create layer record with position
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if layer.get('visible', True) else 0,
            channels={
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
        )
        layer_records.append(layer_record)
    
    # Add layers to PSD
    psd.layer_and_mask_info.layer_info.layer_records = layer_records
    
    # Save to bytes
    psd_bytes = io.BytesIO()
    psd.write(psd_bytes)
    psd_bytes.seek(0)
    
    return send_file(
        psd_bytes,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=f"{current_project['name']}.psd"
    )


def export_layers_as_zip(include_borders, raster_width, raster_height):
    """Fallback: Export layers as individual PNGs in a ZIP file"""
    import zipfile
    
    zip_bytes = io.BytesIO()
    
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add each layer as a separate PNG
        for layer in current_project['layers']:
            layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
            
            # Convert to RGB with transparency info preserved
            img_bytes = io.BytesIO()
            layer_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            layer_name = layer.get('name', f"Layer_{layer['id']}")
            # Sanitize filename
            safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).strip()
            zf.writestr(f"{safe_name}.png", img_bytes.getvalue())
        
        # Add a manifest with layer info
        manifest = {
            'project_name': current_project['name'],
            'raster_width': raster_width,
            'raster_height': raster_height,
            'layers': [
                {
                    'name': l.get('name', f"Layer_{l['id']}"),
                    'offset_x': l.get('offset_x', 0),
                    'offset_y': l.get('offset_y', 0),
                    'width': _layer_bounds(l)['width'],
                    'height': _layer_bounds(l)['height'],
                    'visible': l.get('visible', True)
                }
                for l in current_project['layers']
            ]
        }
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    
    zip_bytes.seek(0)
    
    return send_file(
        zip_bytes,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{current_project['name']}_layers.zip"
    )


@app.route('/api/export/zip', methods=['POST'])
def export_zip():
    """Export as ZIP of individual layer PNGs"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = current_project.get('raster_width', 1920)
    raster_height = current_project.get('raster_height', 1080)
    
    return export_layers_as_zip(include_borders, raster_width, raster_height)


# ============================================================================
# CLIENT-RENDERED IMAGE EXPORT ENDPOINTS
# These accept base64 PNG data from client-side canvas capture
# ============================================================================

import base64

def decode_base64_image(data_url):
    """Decode a base64 data URL to PIL Image"""
    # Remove the data:image/png;base64, prefix
    if ',' in data_url:
        data_url = data_url.split(',')[1]
    img_data = base64.b64decode(data_url)
    return Image.open(io.BytesIO(img_data))


@app.route('/api/export/zip-images', methods=['POST'])
def export_zip_images():
    """Create a ZIP file from client-rendered images"""
    import zipfile
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    images = data.get('images', [])
    
    zip_bytes = io.BytesIO()
    
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        for img_info in images:
            img = decode_base64_image(img_info['data'])
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            zf.writestr(img_info['name'], img_bytes.getvalue())
    
    zip_bytes.seek(0)
    
    return send_file(
        zip_bytes,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{project_name} - PNG Files.zip"
    )


@app.route('/api/export/pdf-from-images', methods=['POST'])
def export_pdf_from_images():
    """Create a multi-page PDF from client-rendered images"""
    try:
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        return jsonify({'error': 'PDF export requires reportlab library'}), 500
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    images = data.get('images', [])
    default_width = data.get('width', 1920)
    default_height = data.get('height', 1080)
    
    pdf_bytes = io.BytesIO()
    c = pdf_canvas.Canvas(pdf_bytes, pagesize=(default_width, default_height))
    
    for img_info in images:
        img = decode_base64_image(img_info['data'])
        page_width = int(img_info.get('width') or img.width or default_width)
        page_height = int(img_info.get('height') or img.height or default_height)
        c.setPageSize((page_width, page_height))
        img_reader = ImageReader(img)
        
        # Draw image filling the page
        c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
        
        # Add view name label at top
        c.setFillColorRGB(1, 1, 1)  # White
        c.setFont("Helvetica-Bold", 24)
        c.drawString(20, page_height - 40, f"{project_name} - {img_info['name']}")
        
        c.showPage()
    
    c.save()
    pdf_bytes.seek(0)
    
    return send_file(
        pdf_bytes,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{project_name}.pdf"
    )


@app.route('/api/export/psd-from-image', methods=['POST'])
def export_psd_from_image():
    """Create a PSD from client-rendered image with screen layers"""
    try:
        from pytoshop import PsdFile
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError as e:
        print(f"PSD export error - pytoshop import failed: {e}")
        return jsonify({'error': f'PSD export requires pytoshop library: {e}'}), 500
    
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', 'Project')
        view_name = data.get('view_name', 'View')
        image_data = data.get('image_data', '')
        width = data.get('width', 1920)
        height = data.get('height', 1080)
        layers_info = data.get('layers', [])
        
        print(f"PSD export: {project_name} - {view_name}, {width}x{height}, {len(layers_info)} layers")
        
        # Decode the full image
        full_img = decode_base64_image(image_data)
        full_img = full_img.convert('RGBA')  # Convert to RGBA for alpha support
        
        # Keep the merged document RGB; layer transparency is stored in each
        # layer's -1 channel. Advertising a document alpha channel without
        # merged alpha data triggers warnings in some PSD readers.
        psd = PsdFile(num_channels=3, height=height, width=width, color_mode=ColorMode.rgb)
        
        layer_records = []
        
        # Create a layer for each screen by cropping the full image
        # Each layer is ONLY the size of the screen, positioned correctly
        for layer_info in layers_info:
            layer_name = layer_info.get('name', 'Screen')
            offset_x = int(layer_info.get('offset_x', 0))
            offset_y = int(layer_info.get('offset_y', 0))
            layer_width = int(layer_info.get('width', 100))
            layer_height = int(layer_info.get('height', 100))
            visible = layer_info.get('visible', True)
            
            if not visible:
                continue
            
            # Calculate actual bounds (clamped to raster)
            left = max(0, offset_x)
            top = max(0, offset_y)
            right = min(width, offset_x + layer_width)
            bottom = min(height, offset_y + layer_height)
            
            if right <= left or bottom <= top:
                continue
            
            # Crop ONLY this layer's region from the full image
            cropped = full_img.crop((left, top, right, bottom))
            img_array = np.array(cropped)
            
            actual_width = right - left
            actual_height = bottom - top
            
            print(f"  Layer '{layer_name}': pos({left},{top}) size({actual_width}x{actual_height}), array shape: {img_array.shape}")
            
            # Create ChannelImageData for RGB + Alpha
            # Channel -1 is the alpha/transparency mask
            channels = {
                -1: psd_layers.ChannelImageData(image=img_array[:, :, 3].copy(), compression=Compression.raw),
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
            
            # Create layer record - bounds define position AND size
            layer_record = psd_layers.LayerRecord(
                name=layer_name,
                top=top,
                left=left,
                bottom=bottom,
                right=right,
                opacity=255,
                channels=channels
            )
            layer_record.mask = _empty_psd_layer_mask(psd_layers)
            layer_records.append(layer_record)
        
        psd.layer_and_mask_info.layer_info.layer_records = layer_records
        
        psd_bytes = io.BytesIO()
        psd.write(psd_bytes)
        psd_bytes.seek(0)
        
        print(f"PSD export complete: {psd_bytes.getbuffer().nbytes} bytes, {len(layer_records)} layers")
        
        return send_file(
            psd_bytes,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f"{project_name} - {view_name}.psd"
        )
    except Exception as e:
        print(f"PSD export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'PSD export failed: {str(e)}'}), 500


@app.route('/api/export/psd-zip-from-images', methods=['POST'])
def export_psd_zip_from_images():
    """Create multiple PSDs from client-rendered images, packaged in a ZIP"""
    import zipfile
    
    try:
        from pytoshop import PsdFile
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError as e:
        return jsonify({'error': f'PSD export requires pytoshop library: {e}'}), 500
    
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', 'Project')
        images = data.get('images', [])
        width = data.get('width', 1920)
        height = data.get('height', 1080)
        layers_info = data.get('layers', [])
        
        zip_bytes = io.BytesIO()
        
        with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_info in images:
                view_name = img_info['name']
                full_img = decode_base64_image(img_info['data']).convert('RGBA')
                
                # Keep the merged document RGB; layer transparency is stored in
                # each layer's -1 channel.
                psd = PsdFile(num_channels=3, height=height, width=width, color_mode=ColorMode.rgb)
                layer_records = []
                
                # Create a layer for each screen
                for layer_info in layers_info:
                    layer_name = layer_info.get('name', 'Screen')
                    offset_x = int(layer_info.get('offset_x', 0))
                    offset_y = int(layer_info.get('offset_y', 0))
                    layer_width = int(layer_info.get('width', 100))
                    layer_height = int(layer_info.get('height', 100))
                    visible = layer_info.get('visible', True)
                    
                    if not visible:
                        continue
                    
                    left = max(0, offset_x)
                    top = max(0, offset_y)
                    right = min(width, offset_x + layer_width)
                    bottom = min(height, offset_y + layer_height)
                    
                    if right <= left or bottom <= top:
                        continue
                    
                    cropped = full_img.crop((left, top, right, bottom))
                    img_array = np.array(cropped)
                    
                    actual_width = right - left
                    actual_height = bottom - top
                    
                    # Create ChannelImageData for RGB + Alpha
                    channels = {
                        -1: psd_layers.ChannelImageData(image=img_array[:, :, 3].copy(), compression=Compression.raw),
                        0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                        1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                        2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
                    }
                    
                    layer_record = psd_layers.LayerRecord(
                        name=layer_name,
                        top=top,
                        left=left,
                        bottom=bottom,
                        right=right,
                        opacity=255,
                        channels=channels
                    )
                    layer_record.mask = _empty_psd_layer_mask(psd_layers)
                    layer_records.append(layer_record)
                
                psd.layer_and_mask_info.layer_info.layer_records = layer_records
                
                psd_bytes_inner = io.BytesIO()
                psd.write(psd_bytes_inner)
                zf.writestr(f"{project_name} - {view_name}.psd", psd_bytes_inner.getvalue())
        
        zip_bytes.seek(0)
        
        return send_file(
            zip_bytes,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{project_name} - PSD Files.zip"
        )
    except Exception as e:
        print(f"PSD ZIP export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'PSD export failed: {str(e)}'}), 500


# ── Resolume Advanced Output XML Export ─────────────────────────────

def _resolume_param_range(name, default="0", value="0", min_val="-1", max_val="1", alt_name=None):
    """Generate a Resolume ParamRange XML block."""
    alt = f' altName="{alt_name}"' if alt_name else ''
    return (
        f'\t\t\t\t\t\t\t<ParamRange name="{name}"{alt} T="DOUBLE" default="{default}" value="{value}">\n'
        f'\t\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
        f'\t\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t</ParamRange>\n'
    )

def _layer_has_hidden_panels(layer):
    """Check if a layer has any hidden (deleted) panels."""
    panels = layer.get('panels', [])
    return any(p.get('hidden', False) for p in panels)


def _compute_panel_contour(layer):
    """Compute the outer boundary contour of visible panels as pixel coordinates.

    Returns a list of (x, y) vertices tracing the boundary clockwise.
    The contour follows the outer edges of the visible panel grid,
    stepping at panel boundaries where the shape changes.
    """
    panels = layer.get('panels', [])
    if not panels:
        return []

    cab_w = int(layer.get('cabinet_width', 192))
    cab_h = int(layer.get('cabinet_height', 384))
    off_x = int(layer.get('offset_x', 0))
    off_y = int(layer.get('offset_y', 0))

    # Build a grid of visible panels: grid[row][col] = True/False
    visible = set()
    max_row = 0
    max_col = 0
    for p in panels:
        if not p.get('hidden', False):
            r, c = p['row'], p['col']
            visible.add((r, c))
            if r > max_row: max_row = r
            if c > max_col: max_col = c

    if not visible:
        return []

    # Determine panel pixel dimensions (accounting for half panels)
    def panel_x(col):
        """Get pixel X position for column index."""
        return off_x + col * cab_w

    def panel_y(row):
        """Get pixel Y position for row index."""
        return off_y + row * cab_h

    # Use marching squares on the grid to trace the boundary.
    # Each visible panel occupies grid cell (row, col).
    # We trace edges between visible and non-visible cells.

    # Trace the outer boundary of visible panels using grid edge walking.
    # This handles concavities and arbitrary shapes correctly.
    # The contour walks counter-clockwise (matching Resolume convention):
    #   top-right → across top going left → down left side → across bottom → up right side

    # Build a set for O(1) lookup
    # visible is already a set of (row, col)

    # Collect all boundary edges between visible and non-visible cells.
    # An edge is on the boundary if one side is visible and the other is not.
    # Edges are stored as ((x1,y1),(x2,y2)) oriented so the visible cell
    # is on the right side (counter-clockwise winding).

    edges = []
    for (r, c) in visible:
        px = panel_x(c)
        py = panel_y(r)
        px2 = panel_x(c + 1)
        py2 = panel_y(r + 1)

        # Top edge: if cell above (r-1, c) is not visible
        if (r - 1, c) not in visible:
            edges.append(((px2, py), (px, py)))  # right to left (CCW)
        # Bottom edge: if cell below (r+1, c) is not visible
        if (r + 1, c) not in visible:
            edges.append(((px, py2), (px2, py2)))  # left to right (CCW)
        # Left edge: if cell left (r, c-1) is not visible
        if (r, c - 1) not in visible:
            edges.append(((px, py), (px, py2)))  # top to bottom (CCW)
        # Right edge: if cell right (r, c+1) is not visible
        if (r, c + 1) not in visible:
            edges.append(((px2, py2), (px2, py)))  # bottom to top (CCW)

    if not edges:
        return []

    # Build adjacency: for each vertex, map start_point -> [(end_point, edge_idx)]
    from collections import defaultdict
    adj = defaultdict(list)
    for i, (start, end) in enumerate(edges):
        adj[start].append((end, i))

    # Walk the boundary starting from the topmost-rightmost point
    # Find the starting point: among all edge start points, pick the one
    # with the largest x, then smallest y (top-right corner)
    all_starts = set(e[0] for e in edges)
    start_pt = max(all_starts, key=lambda p: (p[0], -p[1]))

    contour = [start_pt]
    used = set()
    current = start_pt

    for _ in range(len(edges) + 1):
        candidates = [(end, idx) for end, idx in adj[current] if idx not in used]
        if not candidates:
            break
        # Pick the next edge (for simple polygons there should be exactly one unused)
        next_pt, edge_idx = candidates[0]
        used.add(edge_idx)
        contour.append(next_pt)
        current = next_pt
        if current == start_pt:
            break

    # Remove the closing duplicate
    if len(contour) > 1 and contour[-1] == contour[0]:
        contour.pop()

    # Simplify: remove collinear intermediate points (points on straight lines)
    if len(contour) < 3:
        return contour

    simplified = []
    n = len(contour)
    for i in range(n):
        prev = contour[(i - 1) % n]
        curr = contour[i]
        nxt = contour[(i + 1) % n]
        # Keep point if direction changes
        dx1 = curr[0] - prev[0]
        dy1 = curr[1] - prev[1]
        dx2 = nxt[0] - curr[0]
        dy2 = nxt[1] - curr[1]
        # Normalize to direction signs
        d1 = (1 if dx1 > 0 else (-1 if dx1 < 0 else 0),
              1 if dy1 > 0 else (-1 if dy1 < 0 else 0))
        d2 = (1 if dx2 > 0 else (-1 if dx2 < 0 else 0),
              1 if dy2 > 0 else (-1 if dy2 < 0 else 0))
        if d1 != d2:
            simplified.append(curr)

    return simplified


def _resolume_polygon(layer, unique_id):
    """Generate a Resolume Polygon XML block for a non-rectangular layer."""
    bounds = _layer_bounds(layer)
    x1 = int(bounds['x'])
    y1 = int(bounds['y'])
    x2 = x1 + int(bounds['width'])
    y2 = y1 + int(bounds['height'])
    name = layer.get('name', 'Layer')

    # Output params (no BRed/BGreen/BBlue for Polygon)
    output_params = (
        _resolume_param_range("Brightness") +
        _resolume_param_range("Contrast") +
        _resolume_param_range("Red") +
        _resolume_param_range("Green") +
        _resolume_param_range("Blue") +
        f'\t\t\t\t\t\t\t<Param name="Is Key" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Black BG" T="BOOL" default="0" value="0"/>\n'
    )

    # Compute contour
    contour_pts = _compute_panel_contour(layer)

    def contour_xml(pts, indent):
        lines = f'{indent}<points>\n'
        for x, y in pts:
            lines += f'{indent}\t<v x="{x}" y="{y}"/>\n'
        lines += f'{indent}</points>\n'
        lines += f'{indent}<segments>{"L" * len(pts)}</segments>\n'
        return lines

    input_contour = contour_xml(contour_pts, '\t\t\t\t\t\t\t')
    output_contour = contour_xml(contour_pts, '\t\t\t\t\t\t\t')

    return (
        f'\t\t\t\t\t<Polygon uniqueId="{unique_id}" IsVirgin="0">\n'
        f'\t\t\t\t\t\t<Params name="Common">\n'
        f'\t\t\t\t\t\t\t<Param name="Name" T="STRING" default="Layer" value="{name}"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Input">\n'
        f'\t\t\t\t\t\t\t<ParamChoice name="Input Source" default="0:1" value="0:1" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Opacity" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Bypass/Solo" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Output">\n'
        f'\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'{output_params}'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<InputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</InputRect>\n'
        f'\t\t\t\t\t\t<OutputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</OutputRect>\n'
        f'\t\t\t\t\t\t<InputContour closed="1">\n'
        f'{input_contour}'
        f'\t\t\t\t\t\t</InputContour>\n'
        f'\t\t\t\t\t\t<OutputContour closed="1">\n'
        f'{output_contour}'
        f'\t\t\t\t\t\t</OutputContour>\n'
        f'\t\t\t\t\t</Polygon>\n'
    )


def _resolume_slice(layer, unique_id):
    """Generate a Resolume Slice XML block for a layer."""
    bounds = _layer_bounds(layer)
    x1 = float(bounds['x'])
    y1 = float(bounds['y'])
    x2 = x1 + float(bounds['width'])
    y2 = y1 + float(bounds['height'])
    name = layer.get('name', 'Layer')
    w = x2 - x1
    h = y2 - y1

    # Output params block (Brightness, Contrast, RGB, etc.)
    output_params = (
        _resolume_param_range("Brightness") +
        _resolume_param_range("Contrast") +
        _resolume_param_range("Red") +
        _resolume_param_range("Green") +
        _resolume_param_range("Blue") +
        f'\t\t\t\t\t\t\t<Param name="Is Key" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Black BG" T="BOOL" default="0" value="0"/>\n' +
        _resolume_param_range("BRed", alt_name="Red", min_val="0", max_val="0.4000000000000000222") +
        _resolume_param_range("BGreen", alt_name="Green", min_val="0", max_val="0.4000000000000000222") +
        _resolume_param_range("BBlue", alt_name="Blue", min_val="0", max_val="0.4000000000000000222")
    )

    # 4x4 BezierWarper grid (linear, 3 divisions)
    bezier_verts = ""
    for ry in range(4):
        for rx in range(4):
            bx = x1 + (w * rx / 3.0)
            by = y1 + (h * ry / 3.0)
            bezier_verts += f'\t\t\t\t\t\t\t\t\t<v x="{bx}" y="{by}"/>\n'

    return (
        f'\t\t\t\t\t<Slice uniqueId="{unique_id}">\n'
        f'\t\t\t\t\t\t<Params name="Common">\n'
        f'\t\t\t\t\t\t\t<Param name="Name" T="STRING" default="Layer" value="{name}"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Input">\n'
        f'\t\t\t\t\t\t\t<ParamChoice name="Input Source" default="0:1" value="0:1" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Opacity" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Bypass/Solo" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="SoftEdgeEnable" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Output">\n'
        f'\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'{output_params}'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<InputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</InputRect>\n'
        f'\t\t\t\t\t\t<OutputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</OutputRect>\n'
        f'\t\t\t\t\t\t<Warper>\n'
        f'\t\t\t\t\t\t\t<Params name="Warper">\n'
        f'\t\t\t\t\t\t\t\t<ParamChoice name="Point Mode" default="PM_LINEAR" value="PM_LINEAR" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t\t<BezierWarper controlWidth="4" controlHeight="4">\n'
        f'\t\t\t\t\t\t\t\t<vertices>\n'
        f'{bezier_verts}'
        f'\t\t\t\t\t\t\t\t</vertices>\n'
        f'\t\t\t\t\t\t\t</BezierWarper>\n'
        f'\t\t\t\t\t\t\t<Homography>\n'
        f'\t\t\t\t\t\t\t\t<src>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t</src>\n'
        f'\t\t\t\t\t\t\t\t<dst>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t</dst>\n'
        f'\t\t\t\t\t\t\t</Homography>\n'
        f'\t\t\t\t\t\t</Warper>\n'
        f'\t\t\t\t\t</Slice>\n'
    )

def generate_resolume_xml(project, project_name, raster_w, raster_h):
    """Generate Resolume Arena Advanced Output XML from project layers.

    v0.8 (Slice 11): one <Screen> per project canvas. Each Screen's layers
    are the screen-type layers belonging to that canvas; coordinates inside
    the Polygon/Slice are CANVAS-LOCAL (panel.x/y are stored that way after
    Slice 6), which matches the per-canvas Resolume composition model. The
    OutputDeviceVirtual for each Screen is sized to that canvas's raster.

    The project-wide CurrentCompositionTextureSize is the workspace bounding
    box of all visible canvases, that's the source-composition size the
    user would feed in Resolume to drive every canvas at once.

    Legacy projects (no canvases array) fall through to a single synthetic
    Screen using the project-root raster dimensions, byte-equivalent to the
    pre-Slice-11 export so v0.7 workflows aren't disrupted.
    """
    import random

    layers = project.get('layers', [])
    # Filter to visible screen layers only
    screen_layers = [l for l in layers if l.get('type') == 'screen' and l.get('visible', True)]

    # Build panels for layers that don't have them
    for layer in screen_layers:
        if not layer.get('panels'):
            layer['panels'] = _build_panels(layer)

    # Resolve canvases. Visible only, hiding a canvas in the sidebar is
    # the user's signal that it shouldn't appear in the export. Legacy:
    # synthetic single canvas at (0, 0) using project-root raster.
    project_canvases = project.get('canvases') or []
    if project_canvases:
        export_canvases = [
            c for c in project_canvases
            if isinstance(c, dict) and c.get('visible', True) is not False
        ]
    else:
        export_canvases = [{
            'id': None,
            'name': 'Screen 1',
            'workspace_x': 0,
            'workspace_y': 0,
            'raster_width': raster_w,
            'raster_height': raster_h,
        }]

    # Workspace bounding box -> CurrentCompositionTextureSize. If no canvases
    # have content yet, fall back to the client-supplied raster_w/h (which
    # comes from the toolbar, i.e. the active canvas).
    if export_canvases:
        min_x = min((c.get('workspace_x') or 0) for c in export_canvases)
        min_y = min((c.get('workspace_y') or 0) for c in export_canvases)
        max_x = max((c.get('workspace_x') or 0) + (c.get('raster_width') or 0)
                    for c in export_canvases)
        max_y = max((c.get('workspace_y') or 0) + (c.get('raster_height') or 0)
                    for c in export_canvases)
        composition_w = max(int(max_x - min_x), int(raster_w))
        composition_h = max(int(max_y - min_y), int(raster_h))
    else:
        composition_w, composition_h = int(raster_w), int(raster_h)

    # Screen-level output params (used for every Screen block)
    def screen_param_range(name, default="0", value="0", min_val="-1", max_val="1"):
        return (
            f'\t\t\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t</ParamRange>\n'
        )

    screen_output = (
        screen_param_range("Opacity", "1", "1", "0", "1") +
        screen_param_range("Brightness") +
        screen_param_range("Contrast") +
        screen_param_range("Red") +
        screen_param_range("Green") +
        screen_param_range("Blue")
    )

    # Virtual output device params
    def device_param_range(name, default, value, max_val="16384"):
        return (
            f'\t\t\t\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="minMax" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="startStop" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t</ParamRange>\n'
        )

    # Build one <Screen> per canvas with its scoped layers.
    screens_xml = ""
    for canvas in export_canvases:
        canvas_id = canvas.get('id')
        canvas_name = canvas.get('name') or 'Screen'
        canvas_w = int(canvas.get('raster_width') or raster_w)
        canvas_h = int(canvas.get('raster_height') or raster_h)
        # Screen-scoped layers: visible screen-type layers in this canvas.
        # Legacy synthetic canvas (id=None) takes every visible layer so
        # pre-multi-canvas projects export identically to v0.7.
        if canvas_id:
            canvas_layers = [l for l in screen_layers if l.get('canvas_id') == canvas_id]
        else:
            canvas_layers = screen_layers

        slices_xml = ""
        for layer in canvas_layers:
            slice_id = random.randint(1000000000000, 9999999999999)
            if _layer_has_hidden_panels(layer):
                slices_xml += _resolume_polygon(layer, slice_id)
            else:
                slices_xml += _resolume_slice(layer, slice_id)

        screen_unique_id = random.randint(1000000000000, 9999999999999)
        device_hash = random.randint(1000000000000000000, 9999999999999999999)
        # Escape any "&", quote chars in the canvas name for XML attributes.
        safe_name = (str(canvas_name)
                     .replace('&', '&amp;').replace('<', '&lt;')
                     .replace('>', '&gt;').replace('"', '&quot;'))

        screens_xml += (
            f'\t\t\t<Screen name="{safe_name}" uniqueId="{screen_unique_id}">\n'
            f'\t\t\t\t<Params name="Params">\n'
            f'\t\t\t\t\t<Param name="Name" T="STRING" default="" value="{safe_name}"/>\n'
            f'\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
            f'\t\t\t\t\t<Param name="Hidden" T="BOOL" default="0" value="0"/>\n'
            f'\t\t\t\t</Params>\n'
            f'\t\t\t\t<Params name="Output">\n'
            f'{screen_output}'
            f'\t\t\t\t</Params>\n'
            f'\t\t\t\t<guides>\n'
            f'\t\t\t\t\t<ScreenGuide name="ScreenGuide" type="0">\n'
            f'\t\t\t\t\t\t<Params name="Params">\n'
            f'\t\t\t\t\t\t\t<ParamPixels name="Image"/>\n'
            f'\t\t\t\t\t\t\t<ParamRange name="Opacity" T="DOUBLE" default="0.25" value="0.25">\n'
            f'\t\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="minMax" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="startStop" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t</ParamRange>\n'
            f'\t\t\t\t\t\t</Params>\n'
            f'\t\t\t\t\t</ScreenGuide>\n'
            f'\t\t\t\t</guides>\n'
            f'\t\t\t\t<layers>\n'
            f'{slices_xml}'
            f'\t\t\t\t</layers>\n'
            f'\t\t\t\t<OutputDevice>\n'
            f'\t\t\t\t\t<OutputDeviceVirtual name="{safe_name}" deviceId="Virtual{safe_name}" idHash="{device_hash}" width="{canvas_w}" height="{canvas_h}">\n'
            f'\t\t\t\t\t\t<Params name="Params">\n'
            f'{device_param_range("Width", "800", str(canvas_w))}'
            f'{device_param_range("Height", "600", str(canvas_h))}'
            f'\t\t\t\t\t\t</Params>\n'
            f'\t\t\t\t\t</OutputDeviceVirtual>\n'
            f'\t\t\t\t</OutputDevice>\n'
            f'\t\t\t</Screen>\n'
        )

    # SoftEdging params
    def soft_edge_param(name, default, value, min_val, max_val):
        return (
            f'\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t</ParamRange>\n'
        )

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<XmlState name="{project_name}">\n'
        f'\t<versionInfo name="Resolume Arena" majorVersion="7" minorVersion="24" microVersion="3" revision="63742"/>\n'
        f'\t<ScreenSetup name="ScreenSetup">\n'
        f'\t\t<Params name="ScreenSetupParams"/>\n'
        f'\t\t<CurrentCompositionTextureSize width="{composition_w}" height="{composition_h}"/>\n'
        f'\t\t<screens>\n'
        f'{screens_xml}'
        f'\t\t</screens>\n'
        f'\t\t<SoftEdging>\n'
        f'\t\t\t<Params name="Soft Edge">\n'
        f'{soft_edge_param("Gamma Red", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma Green", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma Blue", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma", "1", "1", "0", "1")}'
        f'{soft_edge_param("Luminance", "0.5", "0.5", "0", "1")}'
        f'{soft_edge_param("Power", "2", "1.999999999999999778", "0.10000000000000000555", "7")}'
        f'\t\t\t</Params>\n'
        f'\t\t</SoftEdging>\n'
        f'\t</ScreenSetup>\n'
        f'</XmlState>\n'
    )
    return xml


@app.route('/api/export/resolume', methods=['POST'])
def export_resolume_xml():
    """Export project as Resolume Arena Advanced Output XML."""
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', current_project.get('name', 'Untitled Project'))
        raster_w = int(data.get('raster_width', current_project.get('raster_width', 3840)))
        raster_h = int(data.get('raster_height', current_project.get('raster_height', 2160)))

        xml_content = generate_resolume_xml(current_project, project_name, raster_w, raster_h)

        log_event('export_resolume', {
            'project_name': project_name,
            'raster': f'{raster_w}x{raster_h}',
            'layers': len([l for l in current_project.get('layers', []) if l.get('type') == 'screen' and l.get('visible', True)])
        })

        return send_file(
            io.BytesIO(xml_content.encode('utf-8')),
            mimetype='application/xml',
            as_attachment=True,
            download_name=f"{project_name}.xml"
        )
    except Exception as e:
        print(f"Resolume export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Resolume export failed: {str(e)}'}), 500


@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('project_data', current_project)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


# ── Modularized route blueprints ──────────────────────────────────────────
# Registered late (after this module's own helpers/state are defined) so that
# blueprints which import from app.py resolve without a circular-import error.
#
# When this file runs as a script (python app.py) it executes under the name
# '__main__', so the blueprints' `from app import ...` would re-execute app.py
# a SECOND time as module 'app' and recurse back into these imports. Alias the
# module first so both names refer to this same instance.
if 'app' not in sys.modules:
    sys.modules['app'] = sys.modules[__name__]
from routes_system import system_bp  # noqa: E402
from routes_dialog import dialog_bp  # noqa: E402
from routes_presets import presets_bp  # noqa: E402
from routes_version import version_bp  # noqa: E402
from routes_logs import logs_bp  # noqa: E402
from routes_panel_catalog import panel_catalog_bp  # noqa: E402
from routes_preferences import preferences_bp  # noqa: E402
from routes_project import project_bp  # noqa: E402
from routes_canvas import canvas_bp  # noqa: E402
from routes_layers import layers_bp  # noqa: E402
app.register_blueprint(system_bp)
app.register_blueprint(dialog_bp)
app.register_blueprint(presets_bp)
app.register_blueprint(version_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(panel_catalog_bp)
app.register_blueprint(preferences_bp)
app.register_blueprint(project_bp)
app.register_blueprint(canvas_bp)
app.register_blueprint(layers_bp)


def run_server(host='127.0.0.1', port=8050):
    """Start the Flask-SocketIO server. Called by the launcher or __main__."""
    socketio.run(app, host=host, port=port, debug=not getattr(sys, 'frozen', False), allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    import socket as _socket

    # Get local IP address for display
    def get_local_ip():
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return 'unknown'

    local_ip = get_local_ip()

    # Allow `--port N` (or `--port=N`) on the command line to override 8050.
    # Useful when running alongside other Flask apps on the same machine.
    _port = 8050
    _argv = sys.argv[1:]
    for i, a in enumerate(_argv):
        if a == '--port' and i + 1 < len(_argv):
            try: _port = int(_argv[i + 1])
            except ValueError: pass
        elif a.startswith('--port='):
            try: _port = int(a.split('=', 1)[1])
            except ValueError: pass

    print('=' * 60)
    print('LED RASTER DESIGNER')
    print('=' * 60)
    print('Server starting...')
    print(f'Local access:   http://127.0.0.1:{_port}')
    print(f'Network access: http://{local_ip}:{_port}')
    print('=' * 60)

    # Auto-open browser when running as bundled executable
    if getattr(sys, 'frozen', False):
        import webbrowser
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{_port}')).start()

    run_server(host='0.0.0.0', port=_port)
