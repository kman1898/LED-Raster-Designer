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
        # v0.11.0: screen groups. Same shape as `canvases`: an array of
        # {id, name, layer_ids} objects, with membership mirrored onto each
        # member layer as `group_id`. Empty on a fresh project; a group only
        # exists once the user makes one.
        'groups': [],
        # Monotonic group-id counter, saved with the project. See
        # sync_next_group_seq: a freed id is never reused, so an undo that
        # resurrects a deleted group cannot collide with a newer one.
        'next_group_seq': 1,
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
    # v0.11.0: `group_id` is deliberately NOT inheritable. Everything in this
    # tuple is a *setting* the user would have to retype; group membership is a
    # structural decision about which screens are one wall. Adding a second
    # screen next to a grouped one must not silently enrol it in that group -
    # the totals, export and numbering that later steps hang off the group
    # would change under the user without them asking. Joining a group stays
    # an explicit action.
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
        # v0.11.0: per-layer Low Latency. Off by default; the client overlays
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
        # v0.11.0: screen group membership. null = not in a group, which is
        # every freshly created layer. Mirrors the owning group's layer_ids.
        'group_id': None,
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


# ---------------------------------------------------------------------------
# Screen groups (v0.11.0).
#
# A group makes a set of layers behave as one screen for totals, export,
# naming and movement. It exists because the per-layer grid is uniform: a wall
# built from 1m JP5 cabinets AND 0.5m standard cabinets has to be two layers,
# and today those two layers calculate as two screens.
#
# The model deliberately mirrors the multi-canvas one:
#     project['groups']   -> [{id, name, layer_ids: [...]}, ...]   (cf. canvases)
#     layer['group_id']   -> 'g1' | None                           (cf. canvas_id)
#
# It is purely additive. Nothing here touches the per-layer grid, (row, col)
# panel identity, _build_panels, the rebuild funnel or any traversal.
#
# `layer_ids` is the authoritative side of the relationship and `group_id` is
# the mirror, which is what _enforce_group_integrity repairs towards. That
# matches how the rest of the app reads membership (walk the group, collect
# its layers) and gives a single answer when the two disagree.
# ---------------------------------------------------------------------------

# The settings every member of a group must agree on. A group is one screen,
# so a port that crosses a member boundary needs one rule set to be checked
# against - two members on different processors have no single answer.
GROUP_SHARED_SETTINGS = ('processorType', 'bitDepth', 'frameRate')


def _highest_group_seq(project):
    """Highest ``N`` across the project's existing ``g<N>`` ids, or 0."""
    groups = (project or {}).get('groups') or []
    max_n = 0
    if not isinstance(groups, list):
        return max_n
    for g in groups:
        gid = (g or {}).get('id', '') if isinstance(g, dict) else ''
        if isinstance(gid, str) and gid.startswith('g'):
            try:
                n = int(gid[1:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return max_n


def sync_next_group_seq(project):
    """Rebase ``project['next_group_seq']`` so no group id is ever reused.

    The counterpart to sync_next_layer_id, with one deliberate difference: the
    layer counter is a module global, this one lives ON THE PROJECT. It has to,
    because the alternative - scanning the existing groups for the highest
    ``g<N>`` - hands a deleted group's id straight back out. Delete g3, make a
    new group, get g3 again; then undo the delete and two different groups both
    answer to g3. A stored counter never goes backwards when a group is
    removed, so the resurrected group and the new one stay distinct.

    Migration: a project that predates the counter (or one hand-edited without
    it) seeds it above its highest existing group id, so ids already in the
    file are never handed out a second time. Never lowers a counter that is
    already ahead, which is what makes this safe to run on the restore funnel:
    restoring the same project twice must not change it.

    Returns the counter value, i.e. the ``N`` the next group will be given.
    """
    if not isinstance(project, dict):
        return 1
    floor_seq = _highest_group_seq(project) + 1
    try:
        stored = int(project.get('next_group_seq'))
    except (TypeError, ValueError):
        stored = 0
    project['next_group_seq'] = max(stored, floor_seq)
    return project['next_group_seq']


def _next_group_id(project):
    """Take the next group id of the form ``g<N>``, consuming the counter.

    Takes the project explicitly (unlike the canvas helpers, which read the
    module global) because restore_project reassigns app.current_project and
    has to run this against the incoming payload.
    """
    seq = sync_next_group_seq(project)
    if isinstance(project, dict):
        project['next_group_seq'] = seq + 1
    return f'g{seq}'


def _find_group(project, group_id):
    for g in (project or {}).get('groups') or []:
        if isinstance(g, dict) and g.get('id') == group_id:
            return g
    return None


def _create_group(project, layer_ids, name=None):
    """Create a group over ``layer_ids`` and stamp membership on those layers.

    The counterpart to _assign_canvas_id: one place every add-a-group path
    goes through, so membership is always written to BOTH sides. Returns the
    new group, or None when fewer than two of the requested layers exist (a
    group of one is not a group).
    """
    if not isinstance(project, dict):
        return None
    by_id = {
        l.get('id'): l for l in (project.get('layers') or [])
        if isinstance(l, dict)
    }
    members = []
    for lid in layer_ids or []:
        if lid in by_id and lid not in members:
            members.append(lid)
    if len(members) < 2:
        return None
    if not isinstance(project.get('groups'), list):
        project['groups'] = []
    group = {
        'id': _next_group_id(project),
        'name': name or f'Group {len(project["groups"]) + 1}',
        'layer_ids': members,
    }
    project['groups'].append(group)
    for lid in members:
        by_id[lid]['group_id'] = group['id']
    return group


def _is_hashable(value):
    """Can ``value`` be put in a set or used as a dict key?

    A hand-edited or truncated project file can carry a dict or a list where an
    id belongs (``layer['id']``, a group's ``layer_ids`` entry, a path step's
    ``layerId``). Every membership test below runs against a SET, and
    ``{'a': 1} in some_set`` raises ``TypeError: unhashable type`` - which came
    out as a 500 on PUT /api/project, i.e. on every undo, redo and file open of
    such a file. The existing guards checked the CONTAINER's type (is this a
    list?) and never the ELEMENT's, so they let those values straight through.

    Unhashable means "not an id we can ever match", so callers treat it exactly
    the way they treat an id that names nothing.
    """
    try:
        hash(value)
    except TypeError:
        return False
    return True


def _hashable_id_set(values):
    """The hashable members of ``values`` as a set, skipping the rest."""
    return {v for v in values if _is_hashable(v)}


def _enforce_group_integrity(project):
    """Repair the group model in place, idempotently.

    restore_project runs on EVERY undo, redo and file load, so this has to
    converge on the first pass: restoring twice must not change anything.

    Rules, in order:
      1. layer_ids that name a layer which no longer exists are pruned (the
         layer was deleted while the group still listed it).
      2. a group left with fewer than 2 members is dropped, and its remaining
         member loses its group_id. A group of one is not a group.
      3. a layer whose group_id names a group that does not exist - or that
         exists but does not list it - has group_id cleared.
      4. group_id is single-valued: a layer listed by more than one group
         stays with the first group that survives rule 2, and is removed from
         the others' layer_ids.
      5. a group id is single-valued too: the SECOND group to claim an id is
         re-issued a fresh one from the project counter. Rule 4 is enforced
         per layer and so never noticed two DIFFERENT groups both called 'g1':
         both survived, every member of both mirrored group_id 'g1',
         _find_group resolved it to the first, and _export_units keyed groups
         by id into a dict - so the last duplicate won and one whole wall
         vanished from the export, its screens drawn under the other wall's
         name. Re-issuing rather than dropping keeps both walls: which of two
         colliding groups is "the real g1" is unknowable, and deleting one
         silently destroys a grouping the user made.

    Layers that never had a group_id key are left completely untouched, so a
    project saved before groups existed round-trips byte for byte.
    """
    if not isinstance(project, dict):
        return project
    if not isinstance(project.get('groups'), list):
        # Missing (pre-v0.11.0 file) or malformed. Normalise to the empty
        # array so every consumer can assume the shape, same as the canvas
        # migrator does for `canvases`.
        project['groups'] = []
    # Before any pruning below, so a group about to be dropped still counts
    # towards the floor and its id can never be handed out again. Seeds the
    # counter on a project that predates it; never lowers one already ahead.
    sync_next_group_seq(project)

    layers = [l for l in (project.get('layers') or []) if isinstance(l, dict)]
    # Unhashable ids (a dict/list where an id belongs) can never match a real
    # layer, so they are simply absent from the lookup - see _is_hashable.
    existing_layer_ids = _hashable_id_set(l.get('id') for l in layers)

    kept = []
    claimed = set()
    seen_group_ids = set()
    for group in project['groups']:
        if not isinstance(group, dict) or not group.get('id'):
            continue
        if not _is_hashable(group.get('id')):
            continue  # an id nothing can ever resolve is not an id
        # Anything that is not a list is treated as no members at all. A JSON
        # string would otherwise iterate into single-character "layer ids",
        # and an int would raise straight into a 500 on every undo.
        raw_ids = group.get('layer_ids')
        if not isinstance(raw_ids, list):
            raw_ids = []
        members = []
        for lid in raw_ids:
            # Rule 1 (layer gone), rule 4 (already owned by an earlier group),
            # and plain duplicates inside one group's own list. The hashable
            # test comes first because the three that follow are set lookups.
            if not _is_hashable(lid):
                continue
            if lid in existing_layer_ids and lid not in claimed and lid not in members:
                members.append(lid)
        if len(members) < 2:
            continue  # rule 2 - and it claims nothing, so a one-member group
                      # listed first cannot starve a real group listed later
        # Rule 5. The first group to claim an id keeps it; a later collision is
        # re-issued from the counter, which never hands out an id already in
        # the file (sync_next_group_seq seeds itself above the highest one).
        if group['id'] in seen_group_ids:
            group['id'] = _next_group_id(project)
        seen_group_ids.add(group['id'])
        group['layer_ids'] = members
        claimed.update(members)
        kept.append(group)
    project['groups'] = kept

    owner = {}
    for group in kept:
        for lid in group['layer_ids']:
            owner[lid] = group['id']
    for layer in layers:
        layer_id = layer.get('id')
        group_id = owner.get(layer_id) if _is_hashable(layer_id) else None
        if group_id is not None:
            layer['group_id'] = group_id  # mirror the authoritative side
        elif layer.get('group_id'):
            layer['group_id'] = None  # rule 3
    # Last, because it reads the membership the rules above just repaired: a
    # path step is only legal if it points at a CURRENT group peer, and "the
    # group" means the group as of this repair, not as of when the user drew.
    _prune_cross_layer_paths(project)
    return project


def _prune_cross_layer_paths(project):
    """Drop manually drawn path steps that point outside the owner's group.

    v0.11.0: a hand-drawn data-port path or power circuit may cross from one
    group member onto another. The path itself never moves - it stays on the
    layer that OWNS the port/circuit, in ``layer['customPortPaths'][port]`` /
    ``layer['powerCustomPaths'][circuit]`` - so the only cross-layer thing in
    the file is a pointer on the individual step:

        {'row': r, 'col': c}                    -> a panel in the owning layer
        {'row': r, 'col': c, 'layerId': <id>}   -> a panel in a group peer

    That pointer is the part that rots. Delete the peer, ungroup the wall, or
    move one member into a different group and the step now names a panel that
    is not part of this screen at all - it would draw a cable onto an unrelated
    layer, or onto nothing. Nobody re-draws paths on those actions, so the
    repair has to happen here, on the funnel every undo, redo and file load
    already passes through.

    Steps WITHOUT a layerId are the shape every project written before this
    feature has, and they are never touched: a pre-v0.11.0 file round-trips
    unchanged. ``layerId`` is camelCase because the client writes it.
    """
    if not isinstance(project, dict):
        return project
    layers = [l for l in (project.get('layers') or []) if isinstance(l, dict)]
    existing_layer_ids = _hashable_id_set(l.get('id') for l in layers)
    # group_id is the mirror _enforce_group_integrity just rewrote, so reading
    # it here is the same as reading project['groups']. A layer outside every
    # group maps to None, and None is deliberately never a legal target: two
    # groupless layers are two separate screens, not a wall.
    group_of = {
        l.get('id'): l.get('group_id') for l in layers
        if _is_hashable(l.get('id'))
    }

    for layer in layers:
        own_id = layer.get('id')
        own_group = group_of.get(own_id) if _is_hashable(own_id) else None
        for key in ('customPortPaths', 'powerCustomPaths'):
            paths = layer.get(key)
            if not isinstance(paths, dict):
                continue  # absent (most layers), None, or hand-edited garbage
            for path_key in list(paths.keys()):
                steps = paths.get(path_key)
                if not isinstance(steps, list):
                    continue  # same reasoning as layer_ids above: a string
                              # would iterate into single characters
                kept = []
                dropped = False
                for step in steps:
                    if not isinstance(step, dict) or 'layerId' not in step:
                        # Plain step, or something we do not understand. Either
                        # way it is not ours to judge - leave it exactly as is.
                        kept.append(step)
                        continue
                    target = step.get('layerId')
                    if not _is_hashable(target):
                        # A dict/list where a layer id belongs. It can never
                        # name a peer, so it is undrawable - same outcome as a
                        # deleted peer below, reached without a set lookup that
                        # would raise TypeError and 500 the restore.
                        dropped = True
                        continue
                    if target == own_id:
                        # Points at its own layer, which is just the plain form
                        # written the long way (the client does this when a
                        # path starts on the owner and the user later drags the
                        # whole thing back). Normalise instead of dropping so
                        # the stored shape is identical to a never-crossed
                        # path, and so restoring twice cannot keep churning.
                        plain = {k: v for k, v in step.items() if k != 'layerId'}
                        kept.append(plain)
                        dropped = True  # the entry changed, so rewrite below
                        continue
                    if (target not in existing_layer_ids
                            or own_group is None
                            or group_of.get(target) != own_group):
                        # Peer deleted, owner ungrouped, or the two layers are
                        # no longer in the same group. Any of those makes the
                        # step undrawable; keeping it would render onto a panel
                        # that belongs to a different screen.
                        dropped = True
                        continue
                    if step.get('row') is None or step.get('col') is None:
                        # A cross-layer step with no cell to land on. Rare
                        # enough that it means a hand-edited or truncated file;
                        # drop it rather than let the renderer trip over it.
                        dropped = True
                        continue
                    kept.append(step)
                if not dropped:
                    continue  # untouched path - do not rewrite it at all
                if kept:
                    paths[path_key] = kept
                else:
                    # Every step pointed somewhere dead. An empty path is not a
                    # path: leaving the key behind would show the user a port
                    # or circuit that claims a custom route and draws nothing.
                    del paths[path_key]
    return project


def validate_group_settings(layers):
    """Do these layers agree on the settings a group has to share?

    Pure: reads nothing, mutates nothing, so the UI in a later step can call
    it on a candidate selection before any group exists.

    Returns ``{'ok': bool, 'conflicts': {field: [distinct values, ...]}}``.
    ``conflicts`` lists only the fields that actually disagree, in the order
    the values were first seen, so a resolve dialog can offer them as-is. A
    field missing from a layer reads as None and is a value like any other:
    one layer on 'brompton' and one with no processorType at all genuinely do
    not agree. Fewer than two layers can never disagree.
    """
    seen = {field: [] for field in GROUP_SHARED_SETTINGS}
    for layer in layers or []:
        if not isinstance(layer, dict):
            continue
        for field in GROUP_SHARED_SETTINGS:
            value = layer.get(field)
            if value not in seen[field]:
                seen[field].append(value)
    conflicts = {f: v for f, v in seen.items() if len(v) > 1}
    return {'ok': not conflicts, 'conflicts': conflicts}


def _export_units(project, layers):
    """Split ``layers`` into the units an export draws and names as ONE screen.

    v0.11.0: the whole point of a group is that an outside viewer - Resolume,
    Photoshop, the person holding the print - sees one screen, so a group's
    members must produce a single shape carrying the GROUP's name, not one per
    member.

    Returns ``[(name, [layer, ...]), ...]``. A group takes the slot of its
    FIRST member so the drawing order does not shuffle, and only the members
    present in ``layers`` join it - a member scoped to another canvas exports
    with that canvas, which is the same rule the Resolume screen loop already
    applies. A project with no groups yields one unit per layer in the order
    given, which is exactly the pre-group list and is what keeps every
    existing export byte-identical.

    ``name`` is None when nothing named the unit, so each caller keeps its own
    fallback (Resolume says "Layer", the PSD says "Screen <id>").
    """
    # FIRST duplicate wins, which is the group _find_group resolves and the one
    # _enforce_group_integrity leaves holding the id. This used to be a dict
    # comprehension, so the LAST group with a given id won instead: two groups
    # called 'g1' meant one wall disappeared from the export and its screens
    # were drawn inside the other wall's unit, under the other wall's name.
    # Rule 5 of the integrity pass now prevents the collision upstream; this is
    # the export refusing to differ from _find_group even if one slips through.
    groups = {}
    for g in (project or {}).get('groups') or []:
        if not isinstance(g, dict) or not g.get('id') or not _is_hashable(g.get('id')):
            continue
        groups.setdefault(g['id'], g)
    units = []
    emitted = set()
    for layer in layers or []:
        group_id = layer.get('group_id')
        if not _is_hashable(group_id):
            group_id = None
        group = groups.get(group_id) if group_id else None
        if group is None:
            units.append((layer.get('name'), [layer]))
            continue
        if group_id in emitted:
            continue  # already emitted with its first member
        emitted.add(group_id)
        members = [l for l in layers if l.get('group_id') == group_id]
        units.append((group.get('name') or layer.get('name'), members))
    return units


def _export_unit_bounds(layers):
    """Bounding box of one export unit - a lone layer, or a whole group.

    One layer in, and this is _layer_bounds verbatim, including its
    no-panels fallback to rows/columns * cabinet size.
    """
    members = [l for l in (layers or []) if isinstance(l, dict)]
    if not members:
        return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    if len(members) == 1:
        return _layer_bounds(members[0])
    boxes = [_layer_bounds(l) for l in members]
    min_x = min(b['x'] for b in boxes)
    min_y = min(b['y'] for b in boxes)
    max_x = max(b['x'] + b['width'] for b in boxes)
    max_y = max(b['y'] + b['height'] for b in boxes)
    return {
        'x': min_x,
        'y': min_y,
        'width': max(0, max_x - min_x),
        'height': max(0, max_y - min_y),
    }


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


def _export_unit_drawn_members(members):
    """The members of an export unit that actually put ink on the page.

    A hidden member contributes nothing: Resolume already filters on
    layer.visible before units are built, and an ungrouped hidden screen has
    always reached Photoshop as its own record at opacity 0. Grouping broke
    that - render_unit_to_image composited every member without ever reading
    visible, so a group of two with the second hidden arrived as ONE record at
    opacity 255, bounds covering both, the hidden member's pixels fully there.
    The PSD handed to graphics showed a section the designer was told had been
    struck from the build.

    A unit with NO visible member keeps all of them, which is what makes the
    ungrouped case identical to what it always was: the record is emitted at
    opacity 0 (invisible in Photoshop) with its pixels intact, so switching it
    back on in Photoshop still shows the screen.
    """
    members = [l for l in (members or []) if isinstance(l, dict)]
    drawn = [l for l in members if l.get('visible', True)]
    return drawn or members


def render_unit_to_image(members, raster_width, raster_height, include_borders=True):
    """Render one export unit - a lone layer, or every member of a screen
    group - onto a single raster-sized RGBA image.

    v0.11.0: a group has to reach Photoshop as ONE Photoshop layer, so its
    members composite into one image first. A single member returns exactly
    what render_layer_to_image returned before groups existed.
    """
    members = _export_unit_drawn_members(members)
    if not members:
        return Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 0))
    img = render_layer_to_image(members[0], raster_width, raster_height, include_borders)
    for member in members[1:]:
        member_img = render_layer_to_image(member, raster_width, raster_height, include_borders)
        img = Image.alpha_composite(img, member_img)
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

    # v0.11.0: one Photoshop layer per export unit. A screen group is one
    # screen, so it gets ONE Photoshop layer named for the group - anything
    # else and the person opening the PSD sees the seam we exist to hide.
    for unit_name, members in _export_units(current_project, current_project['layers']):
        layer = members[0]
        # Render the unit to image (a group composites its members first)
        layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

        # Get unit bounds. Hidden members neither draw nor widen the record -
        # see _export_unit_drawn_members.
        bounds = _export_unit_bounds(_export_unit_drawn_members(members))
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

        # Layer name from the group's name, or the screen's when ungrouped
        layer_name = unit_name if unit_name is not None else f"Screen {layer['id']}"

        # Create layer record
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if any(m.get('visible', True) for m in members) else 0,
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
    
    # Add each export unit (in reverse order so first layer is on bottom in a
    # layer panel). v0.11.0: a screen group is ONE Photoshop layer, named for
    # the group - see create_psd_for_view.
    for unit_name, members in _export_units(current_project, current_project['layers']):
        layer = members[0]
        # Render the unit to image (full raster size with transparency)
        layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

        # Get unit bounds (where the actual content is). Hidden members neither
        # draw nor widen the record - see _export_unit_drawn_members.
        bounds = _export_unit_bounds(_export_unit_drawn_members(members))
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
        
        # Get layer name from the group's name, or the screen's when ungrouped
        layer_name = unit_name if unit_name is not None else f"Screen {layer['id']}"

        # Create layer record with position
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if any(m.get('visible', True) for m in members) else 0,
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
    
    # v0.11.0: one PNG per export unit, so a screen group leaves one file
    # named for the group rather than one file per member.
    units = _export_units(current_project, current_project['layers'])

    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add each unit as a separate PNG
        for unit_name, members in units:
            layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

            # Convert to RGB with transparency info preserved
            img_bytes = io.BytesIO()
            layer_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            layer_name = unit_name if unit_name is not None else f"Layer_{members[0]['id']}"
            # Sanitize filename
            safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).strip()
            zf.writestr(f"{safe_name}.png", img_bytes.getvalue())

        # Add a manifest with unit info
        def manifest_entry(unit_name, members):
            bounds = _export_unit_bounds(_export_unit_drawn_members(members))
            # A lone layer keeps reporting its own nominal offset, as it always
            # has; a group has no single offset, so it reports the union's.
            offset = (members[0] if len(members) == 1 else None)
            return {
                'name': unit_name if unit_name is not None else f"Layer_{members[0]['id']}",
                'offset_x': offset.get('offset_x', 0) if offset else bounds['x'],
                'offset_y': offset.get('offset_y', 0) if offset else bounds['y'],
                'width': bounds['width'],
                'height': bounds['height'],
                'visible': any(m.get('visible', True) for m in members)
            }

        manifest = {
            'project_name': current_project['name'],
            'raster_width': raster_width,
            'raster_height': raster_height,
            'layers': [manifest_entry(n, ms) for n, ms in units]
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
    return _compute_layers_contour([layer])


def _compute_layers_contour(layers):
    """The outline of ONE connected region of these layers' visible panels.

    v0.11.0: a screen group is one screen, so its members trace a SINGLE
    outline rather than one per member. Nothing else changes - the lattice
    below was already built from each panel's own rectangle, so panels of
    different cabinet sizes coming from different layers union exactly the
    way half tiles inside one layer already did. One layer in, and this is
    _compute_panel_contour as it stood before groups existed, point for point.

    A union that is NOT connected - two walls with air between them, or a
    screen cut in half by a column of deleted cabinets - has no single outline,
    and this returns the first island's only. Anything that has to be RIGHT
    about such a unit must call _compute_layers_islands, which returns every
    island; this stays for the connected case and for the callers (and pinned
    tests) that predate islands.
    """
    islands = _compute_layers_islands(layers)
    return islands[0] if islands else []


def _compute_layers_islands(layers):
    """Every connected region of these layers' visible panels, outline traced.

    Returns ``[[(x, y), ...], ...]`` - one closed, axis-aligned, counter-
    clockwise ring per island, in reading order (top to bottom, then left to
    right). A connected union gives exactly one ring and that ring is what
    _compute_layers_contour has always returned.

    Why islands at all: the trace below walks the boundary from one starting
    vertex and stops the moment it closes that ring. On a disconnected union it
    therefore returned ONE island and silently dropped the rest - two walls
    with a gap traced as the right-hand wall alone, which then read as "this is
    a rectangle" and shipped as a plain Slice spanning the gap, and a screen
    split by a hidden column shipped a polygon that masked its left-hand
    cabinets to black. Corner-touching members were worse: the shared vertex
    was reachable from both, so one ring passed through it twice and the result
    was a figure-of-eight, which no warper defines a fill for.

    Cells are grouped 4-connected, so members meeting only at a corner are two
    islands - which is exactly what they physically are.

    Holes are not islands and are not returned: a ring is the OUTER boundary of
    its island. A Resolume contour is a single closed loop and cannot express a
    hole, and it does not need to - the cabinets around a hole still map to
    their own coordinates. Only DISCONNECTED surface needs its own shape.

    Known limit: one CONNECTED island can still pinch shut to a point (a wall
    with knockouts arranged so a notch narrows to nothing, e.g. a bay closed
    off by a single diagonal pair). Its boundary genuinely visits that vertex
    twice and the ring says so, because splitting it there would hand the
    notch back to whichever half kept it. That is one piece of LED with one
    honest outline; it is not the two-separate-walls case above.
    """
    panels = []
    for layer in layers or []:
        panels.extend((layer or {}).get('panels') or [])
    if not panels:
        return []

    # v0.11.0: trace the union of the visible panels' REAL rectangles. The old
    # code walked a uniform row/col * cabinet-size grid, which is a whole
    # cabinet too tall/wide whenever a half tile shrinks a row or column.
    # Every rect comes from the panel's own x/y/width/height, which is where
    # the geometry actually lives (_build_panels collapses a wholly-half row or
    # column and anchors a half tile inside its full-size slot otherwise).
    rects = []
    for p in panels:
        # v0.11.0: exclude blank as well as hidden. The contour is "where the
        # LED surface actually is", and every count that answers that question
        # - cabinet totals, weight, power - filters on `not blank and not
        # hidden` (canvas.js:4640, app-presets.js:1329, app-power.js:1517).
        # The contour used to consider only `hidden`, so a blank cabinet was
        # traced as if it were lit.
        if p.get('hidden', False) or p.get('blank', False):
            continue
        # Contour points ship as integer pixel coordinates in the Resolume XML.
        x1 = int(round(p.get('x', 0)))
        y1 = int(round(p.get('y', 0)))
        x2 = int(round(p.get('x', 0) + p.get('width', 0)))
        y2 = int(round(p.get('y', 0) + p.get('height', 0)))
        if x2 <= x1 or y2 <= y1:
            continue  # zero/negative-size panel covers no area
        rects.append((x1, y1, x2, y2))

    if not rects:
        return []

    # Non-uniform coordinate lattice: every rect edge becomes a grid line, so
    # each band [xs[i], xs[i+1]] x [ys[j], ys[j+1]] is either wholly inside a
    # panel or wholly outside every panel. This degenerates to the plain
    # cabinet grid on a uniform wall and generalises to mixed panel sizes.
    xs = sorted({v for (x1, _y1, x2, _y2) in rects for v in (x1, x2)})
    ys = sorted({v for (_x1, y1, _x2, y2) in rects for v in (y1, y2)})
    x_index = {v: i for i, v in enumerate(xs)}
    y_index = {v: i for i, v in enumerate(ys)}

    # Mark every band cell covered by at least one visible panel.
    visible = set()
    for (x1, y1, x2, y2) in rects:
        for c in range(x_index[x1], x_index[x2]):
            for r in range(y_index[y1], y_index[y2]):
                visible.add((r, c))

    if not visible:
        return []

    # Band index -> real pixel coordinate (was col * cab_w / row * cab_h)
    def panel_x(col):
        """Get pixel X position for band column index."""
        return xs[col]

    def panel_y(row):
        """Get pixel Y position for band row index."""
        return ys[row]

    # Trace the boundary of the visible bands using grid edge walking.
    # This handles concavities and arbitrary shapes correctly.
    # Each ring walks counter-clockwise (matching Resolume convention):
    #   top-right → across top going left → down left side → across bottom → up right side

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

    # Walk every ring, not just the first. The old code took ONE starting
    # vertex, walked until it closed that ring and returned - so a second
    # island was never visited at all. Each pass below starts from the
    # top-right-most vertex among the edges nobody has walked yet, so a
    # disconnected union yields one ring per piece.
    used = set()
    remaining = set(range(len(edges)))
    rings = []
    while remaining:
        start_pt = max((edges[i][0] for i in remaining),
                       key=lambda p: (p[0], -p[1]))
        ring = [start_pt]
        current = start_pt
        # Implied arrival direction at a top-right corner: up the right-hand
        # side, which is how a closed ring really does arrive back there.
        in_dir = (0, -1)
        for _ in range(len(edges) + 1):
            candidates = [(end, idx) for end, idx in adj[current] if idx not in used]
            if not candidates:
                break
            # A simple ring offers exactly one unused edge here and the sort is
            # a no-op. More than one means a PINCH: two parts of the shape meet
            # at a single vertex (two cabinets touching corner to corner is the
            # everyday case). Taking either one at random is how the old walk
            # produced a figure-of-eight that passed through the shared vertex
            # twice - undefined for a warper. Turning towards the surface we are
            # already tracing keeps each lobe a separate, simple ring.
            def turn(candidate, _in_dir=in_dir, _cur=current):
                end = candidate[0]
                out_dir = (_sign(end[0] - _cur[0]), _sign(end[1] - _cur[1]))
                return (_in_dir[0] * out_dir[1] - _in_dir[1] * out_dir[0],
                        out_dir)
            next_pt, edge_idx = min(candidates, key=turn)
            used.add(edge_idx)
            remaining.discard(edge_idx)
            in_dir = (_sign(next_pt[0] - current[0]), _sign(next_pt[1] - current[1]))
            ring.append(next_pt)
            current = next_pt
            if current == start_pt:
                break
        # Remove the closing duplicate
        if len(ring) > 1 and ring[-1] == ring[0]:
            ring.pop()
        # A ring wound the other way is a HOLE, not an island: the surface
        # around a missing cabinet in the middle of a wall still maps to its own
        # coordinates, and a Resolume contour is one closed loop with no way to
        # say "except here". Outer rings come back negative under this edge
        # orientation (see the shoelace sign below).
        if len(ring) >= 4 and _ring_signed_area(ring) < 0:
            rings.append(_simplify_ring(ring))

    # Reading order: top to bottom, then left to right. Deterministic, and it
    # puts the shapes in the Resolume layer list the way the operator reads the
    # wall. A single-island unit is unaffected - there is only one ring.
    rings.sort(key=lambda ring: (min(y for _x, y in ring),
                                 min(x for x, _y in ring)))
    return rings


def _sign(value):
    return 1 if value > 0 else (-1 if value < 0 else 0)


def _ring_signed_area(ring):
    """Twice the shoelace area of a closed ring; negative for an outer ring."""
    total = 0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total


def _simplify_ring(ring):
    """Drop the intermediate points of every straight run."""
    if len(ring) < 3:
        return ring
    simplified = []
    n = len(ring)
    for i in range(n):
        prev = ring[(i - 1) % n]
        curr = ring[i]
        nxt = ring[(i + 1) % n]
        # Keep point if direction changes
        d1 = (_sign(curr[0] - prev[0]), _sign(curr[1] - prev[1]))
        d2 = (_sign(nxt[0] - curr[0]), _sign(nxt[1] - curr[1]))
        if d1 != d2:
            simplified.append(curr)
    return simplified


def _ring_bounds(ring):
    """The bounding box of one traced ring, in the export's bounds shape."""
    if not ring:
        return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    xs = [x for x, _y in ring]
    ys = [y for _x, y in ring]
    return {
        'x': float(min(xs)), 'y': float(min(ys)),
        'width': float(max(xs) - min(xs)), 'height': float(max(ys) - min(ys)),
    }


def _layer_has_knockouts(layer):
    """Does this layer have any cabinet missing from its grid?

    Hidden (deleted) OR blank. v0.11.0 taught the CONTOUR that a blank cabinet
    is not LED surface but left the SHAPE DECISION on the old hidden-only test,
    so a lone screen with a blanked corner traced a correct six-vertex outline
    and then threw it away and shipped a full rectangle - while the same wall
    grouped with a neighbour correctly became a polygon. Two crews with the
    same wall got two different Resolume files depending on whether anyone had
    pressed Group Screens.
    """
    panels = layer.get('panels', []) if isinstance(layer, dict) else []
    return any(p.get('hidden', False) or p.get('blank', False)
               for p in panels if isinstance(p, dict))


def _export_unit_needs_polygon(members):
    """Does this export unit need a Polygon, or is a plain Slice enough?

    A lone layer keeps the pre-v0.11.0 test: a cabinet missing anywhere in the
    grid and it is a Polygon, so every mapping already in the field re-exports
    unchanged. (What CHANGED in v0.11.0: "missing" now means blank as well as
    hidden, matching the contour - see _layer_has_knockouts.)

    v0.11.0: a group is judged on the union it actually traces, because no
    member can answer the question on its own. Two rectangular members that
    tile into a rectangle ARE a rectangle and ship as a Slice; two that tile
    into an L are a polygon even though neither member has a hidden panel.
    A traced contour with four vertices is a rectangle: the trace is
    axis-aligned and collinear points are already simplified away, so a
    concave shape can never come back with fewer than six.

    Disconnected units do not go through here at all - they ship one shape per
    island (see _export_unit_shapes), and each island answers this question for
    itself on its own ring.
    """
    if len(members) == 1 and len(_compute_layers_islands(members)) <= 1:
        return _layer_has_knockouts(members[0])
    return len(_compute_layers_contour(members)) != 4


def _export_unit_shapes(members):
    """The shape(s) one export unit ships as: ``[(needs_polygon, contour, bounds), ...]``.

    Normally one entry - a lone screen, or a group whose members tile into one
    connected wall. That entry carries the unit's own bounds (_export_unit_bounds,
    i.e. _layer_bounds for a lone layer, nominal fallback and all), so every
    export that worked before is byte-for-byte what it was.

    More than one entry when the unit's LED surface is DISCONNECTED: two group
    members with air between them, three members with one parked off to the
    side, or a single screen cut in two by a column of deleted cabinets. One
    shape cannot honestly describe two separate walls:

      * as a Slice it claims the gap, so a third of the picture is mapped onto
        empty air between the walls and neither wall can be positioned on its
        own afterwards;
      * as a Polygon it can only carry ONE closed contour, so whichever island
        is not in it is masked off and those cabinets go black. That is exactly
        what a screen split by a hidden column did.

    So each island gets its own shape, at its own coordinates, all carrying the
    unit's name - which is what two ungrouped walls already produce today and
    what an operator expects to find in the Resolume layer list. Input and
    output rectangles stay equal, so content still lands pixel-for-pixel where
    the pixel map says it does; nothing is shifted and nothing is invented.
    An island that is a plain rectangle is a Slice, one that is not is a
    Polygon, judged per island on its own ring.
    """
    islands = _compute_layers_islands(members)
    if len(islands) <= 1:
        contour = islands[0] if islands else []
        return [(_export_unit_needs_polygon(members), contour,
                 _export_unit_bounds(members))]
    return [(len(ring) != 4, ring, _ring_bounds(ring)) for ring in islands]


def _xml_attr(value):
    """Escape a value for use inside a double-quoted XML attribute.

    "Left & Right" is a completely normal name for a wall, and interpolating it
    raw produced a file Resolume simply cannot open. The canvas name has always
    been escaped here; the shape names were not.
    """
    return (str(value)
            .replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _resolume_polygon(layer, unique_id, members=None, name=None,
                      bounds=None, contour=None):
    """Generate a Resolume Polygon XML block for a non-rectangular layer.

    v0.11.0: ``members`` is the export unit this shape covers - a screen
    group's members, or just ``layer``. ``name`` overrides the shape's name so
    a group is named once, for the group.

    ``bounds``/``contour`` override the geometry, which is how a unit whose
    surface is disconnected ships one shape per island (_export_unit_shapes).
    Omitted, they are computed exactly as before.
    """
    members = members or [layer]
    bounds = _export_unit_bounds(members) if bounds is None else bounds
    x1 = int(bounds['x'])
    y1 = int(bounds['y'])
    x2 = x1 + int(bounds['width'])
    y2 = y1 + int(bounds['height'])
    name = _xml_attr(layer.get('name', 'Layer') if name is None else name)

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

    # Compute contour (over the whole unit - a group traces one outline)
    contour_pts = _compute_layers_contour(members) if contour is None else contour

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


def _resolume_slice(layer, unique_id, members=None, name=None, bounds=None,
                    contour=None):
    """Generate a Resolume Slice XML block for a layer.

    v0.11.0: ``members``/``name`` as in _resolume_polygon - a group that tiles
    into a plain rectangle is one Slice over the union, named for the group.
    ``bounds`` overrides the rectangle (one island of a disconnected unit);
    ``contour`` is accepted and ignored so both shape builders take the same
    call.
    """
    members = members or [layer]
    bounds = _export_unit_bounds(members) if bounds is None else bounds
    x1 = float(bounds['x'])
    y1 = float(bounds['y'])
    x2 = x1 + float(bounds['width'])
    y2 = y1 + float(bounds['height'])
    name = _xml_attr(layer.get('name', 'Layer') if name is None else name)
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

        # v0.11.0: one shape per export unit, not per layer. A screen group's
        # members become a single Slice/Polygon over their union, carrying the
        # group's name; an ungrouped project yields the old per-layer list.
        slices_xml = ""
        for unit_name, members in _export_units(project, canvas_layers):
            # Usually one shape. A unit whose LED surface is in two or more
            # disconnected pieces ships one shape per piece, all named for the
            # unit - see _export_unit_shapes for why one shape cannot do it.
            for needs_polygon, contour, bounds in _export_unit_shapes(members):
                slice_id = random.randint(1000000000000, 9999999999999)
                build = _resolume_polygon if needs_polygon else _resolume_slice
                slices_xml += build(members[0], slice_id, members, unit_name,
                                    bounds=bounds, contour=contour)

        screen_unique_id = random.randint(1000000000000, 9999999999999)
        device_hash = random.randint(1000000000000000000, 9999999999999999999)
        # Escape any "&", quote chars in the canvas name for XML attributes.
        safe_name = _xml_attr(canvas_name)

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


@app.route('/api/export/scr', methods=['POST'])
def export_novastar_scr():
    """Export the project as a NovaStar .scr screen connection file.

    One canvas becomes one section on one sending card - a NovaLCT "screen" is
    a canvas here, not a screen layer. The mapping lives in scr_project so the
    Export button and tools/scr_export.py cannot disagree about that.

    Warnings are returned in a header rather than swallowed: the exporter knows
    where it is approximating (the origin row's column shift, port renumbering
    when one canvas carries several layers) and the operator needs to see that
    before trusting the file on a wall.
    """
    try:
        import scr_project
        from scr_encoder import build_multi_screen_scr

        data = request.get_json() or {}
        project_name = data.get('project_name', current_project.get('name', 'Untitled Project'))

        warnings = scr_project.Warnings()
        sections = scr_project.build_sections(current_project, warnings)
        if not sections:
            return jsonify({'error': 'No canvas has any screen layers to export.'}), 400
        scr_bytes = build_multi_screen_scr(sections)

        log_event('export_scr', {
            'project_name': project_name,
            'sections': len(sections),
            'bytes': len(scr_bytes),
            'warnings': len(warnings),
        })
        resp = make_response(scr_bytes)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['X-Scr-Sections'] = str(len(sections))
        if len(warnings):
            resp.headers['X-Scr-Warnings'] = json.dumps(warnings.items)
        return resp
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


# The address the server was told to listen on, recorded so the native
# dialog routes can tell "this machine reached at its own LAN IP" apart from
# a genuine remote client. Set by whichever launcher binds the socket; None
# means unknown, and routes_dialog then trusts loopback only (fails closed).
BOUND_HOST = None


def run_server(host='127.0.0.1', port=8050):
    """Start the Flask-SocketIO server. Called by the launcher or __main__."""
    global BOUND_HOST
    BOUND_HOST = host
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
