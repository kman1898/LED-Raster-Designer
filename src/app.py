from flask import Flask, render_template, request, jsonify, make_response, send_from_directory
from flask_socketio import SocketIO, emit
import json
import math
import re
import uuid
import time
import os
import sys
import datetime
import platform
import subprocess
from PIL import Image
import port_assignment

# v0.8.7: Pillow's default decompression-bomb guard refuses images larger
# than ~89 megapixels. Our PSD scale feature legitimately produces images
# up to PSD's 30000×30000 limit (~900 megapixels), and the input is our
# own renderer (no untrusted file path). Disable the guard so high-scale
# PSD exports don't fail with "Image size exceeds limit ... could be
# decompression bomb DOS attack".
Image.MAX_IMAGE_PIXELS = None


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
        # Beaches (2026-09-08): the positions a show is pulled to, kept as a
        # LIST on the project in pull-sheet / binder order, picked from
        # everywhere (a screen's Beach, a distro's, a breakout box's). Same
        # shape and same counter discipline as groups - see _normalize_beaches.
        'beaches': [],
        'next_beach_seq': 1,
        # Port attachment state, born with the project so the funnel can
        # tell a new project from a file saved before auto-numbering was
        # retired (2026-09-03): a project WITHOUT this key is a pre-ruling
        # file, and retire_auto freezes its auto-drawn ports into pins once.
        # A project born with the stamp never goes near that path, which is
        # what keeps an undo snapshot of a fresh project from being mistaken
        # for a legacy file and "migrated" onto pins nobody placed.
        port_assignment.STATE_KEY: port_assignment.new_state(),
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
        normalize_power_breakout(default_layer)
        current_project['layers'].append(default_layer)


# ── Power breakout invariant (user ruling, 2026-09-22) ─────────────────────
#
# Every screen carries a breakout its voltage allows, and the server holds
# that invariant itself: no route stores or serves a screen layer whose
# powerBreakoutType is missing, empty, unknown or ineligible. The rule is the
# client's normalizePowerBreakout (app-power.js) rung for rung, so the two
# copies of a screen can never disagree on the plug its paperwork names.
#
# Eligibility (user ruling, 2026-09-22): at 0 < V <= 120 a screen runs
# Multi -> True1, powerCON or Edison; above 120 V Edison is out; the L21-30
# box (3 x 208 V) is 208 V exactly; a blank / non-numeric voltage restricts
# only the L21-30. Nothing is extrapolated past what the ruling names.
#
# The write-in order for a screen whose stored choice fails that gate:
#   1. a stored ELIGIBLE choice stands - it is somebody's paperwork;
#   2. the Preferences breakout (server_preferences['breakoutType'], the key
#      the client's applyNewScreenPowerPreferences reads) when the screen's
#      voltage allows it - "if 208 is default then True1 is default, but
#      that should be set in preferences" (user, 2026-09-22);
#   3. only then the voltage class default: Edison at or below 120 V, True1
#      above (and True1 for a blank voltage).
POWER_BREAKOUT_IDS = (
    'soca-true1', 'soca-powercon', 'soca-edison', 'soca-l620',
    'l2130-true1', 'l2130-powercon',
)
# Mirrors getPreferencesDefaults().breakoutType in app-preferences.js - the
# breakout a client with no saved preference reads - so a server that has
# never been handed the preferences (a fresh install, the test client) falls
# back to the same rung the browser does. tests/test_breakout_invariant.py
# pins the two literals together.
PREF_DEFAULT_BREAKOUT = 'soca-true1'


# JavaScript's parseFloat, as a regex over a string: StrWhiteSpace (the ES
# WhiteSpace and LineTerminator sets - NOT Python's \s, which also takes
# \x1c-\x1f), an optional sign, then the longest StrDecimalLiteral prefix:
# 'Infinity' (case-sensitive) or ASCII digits with an optional fraction and
# exponent ([0-9], never \d - JS does not read Arabic-Indic digits). Whatever
# follows the prefix is ignored ('208V' is 208); no prefix is NaN.
_JS_WHITESPACE = ('\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029'
                  '\u202f\u205f\u3000\ufeff')
_JS_FLOAT_PREFIX = re.compile(
    '^[' + _JS_WHITESPACE + r']*([+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?))')


def _power_voltage_number(value):
    """The voltage as the client's voltageNumber (app-power.js) reads it,
    so the two copies of a screen agree on its breakout. A string is read
    the way JavaScript parseFloat reads it - leading whitespace, a sign, a
    leading number ('208V' and '208 V' and '208,0' are 208; '1_000' is 1;
    '0x10' is 0; 'abc' and '' are NaN) - and a number is itself. Anything
    else (None, a bool, a list, a dict) is no voltage, and so is a result
    that is not finite ('Infinity', '1e400'): 0, which restricts only the
    L21-30. tests/test_breakout_invariant.py drives one table through both
    readers."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        try:
            v = float(value)
        except OverflowError:
            return 0.0
    elif isinstance(value, str):
        m = _JS_FLOAT_PREFIX.match(value)
        if not m:
            return 0.0
        v = float(m.group(1))
    else:
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return v


def power_breakout_eligible(breakout_id, voltage):
    """Whether breakout `breakout_id` may sit on a screen at `voltage`."""
    bid = breakout_id if isinstance(breakout_id, str) else ''
    if bid not in POWER_BREAKOUT_IDS:
        return False
    v = _power_voltage_number(voltage)
    if 0 < v <= 120:
        return bid in ('soca-true1', 'soca-powercon', 'soca-edison')
    if bid == 'soca-edison':
        return v <= 0
    if bid.startswith('l2130-'):
        return v == 208
    return True


def default_power_breakout(voltage):
    """Rung 3: the voltage class default - Edison for 0 < V <= 120, True1
    otherwise."""
    v = _power_voltage_number(voltage)
    return 'soca-edison' if 0 < v <= 120 else 'soca-true1'


def preferred_power_breakout(voltage, prefs=None):
    """Rungs 2 and 3: the Preferences breakout when the voltage allows it,
    else the class default. `prefs` defaults to the live server preferences;
    a preferences record with no breakoutType key reads the client's shipped
    default, while one holding a blank or unknown id falls to rung 3."""
    if prefs is None:
        prefs = server_preferences
    want = PREF_DEFAULT_BREAKOUT
    if isinstance(prefs, dict) and 'breakoutType' in prefs:
        want = prefs.get('breakoutType')
    if power_breakout_eligible(want, voltage):
        return want
    return default_power_breakout(voltage)


def normalize_power_breakout(layer, prefs=None):
    """Write an eligible powerBreakoutType onto a screen layer that lacks one.
    A stored eligible choice is never touched. Returns True when it wrote.
    Non-screen layers (image, text) are left alone."""
    if not isinstance(layer, dict):
        return False
    if (layer.get('type') or 'screen') != 'screen':
        return False
    if power_breakout_eligible(layer.get('powerBreakoutType'), layer.get('powerVoltage')):
        return False
    layer['powerBreakoutType'] = preferred_power_breakout(layer.get('powerVoltage'), prefs)
    return True


def normalize_power_breakouts(project, at=None):
    """Run normalize_power_breakout over every layer of `project`. Returns the
    ids it wrote; logs them under `at` when given (a route naming itself), so
    a write on a path that should already be clean - GET /api/project - shows
    up in the log as the missed entry point it is."""
    wrote = []
    layers = project.get('layers') if isinstance(project, dict) else None
    for layer in (layers or []):
        if normalize_power_breakout(layer):
            wrote.append(layer.get('id') if isinstance(layer, dict) else None)
    if wrote and at:
        log_event('power_breakout_normalized', {'at': at, 'layers': wrote})
    return wrote


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
    # A request that names its own voltage runs at that voltage: the donor's
    # cached custom figure is not inherited beside it (a 208 V donor's
    # powerVoltageCustom under a 120 V request would be a figure the screen
    # never ran at), and the add route normalizes the breakout at the
    # request's voltage, never the donor's (2026-09-23: with a 120 V / junk
    # breakout preference and a 208 V donor the new screen was normalized
    # at 208 to True1, which then stood at 120 on the client, where the
    # class default is Edison).
    skip = set()
    if 'powerVoltage' in data:
        skip.add('powerVoltageCustom')
    for field in inheritable:
        if field in data or field in skip:
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
        'powerCircuitCables': {},
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
        # Layer opacity, 0-100. 100 = the image and its drop shadow drawn
        # exactly as before this existed.
        'imageOpacity': 100,
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


# ---------------------------------------------------------------------------
# Beaches (2026-09-08).
#
# "beach locations need to be addable for data" / "you can either create a
# beach or you can pick one from the drop-down of one that you created earlier
# in the project". A beach is a POSITION on the pull sheet and the order the
# binder runs the screens in. The project keeps them as a list:
#
#     project['beaches']      -> [{id: 'b1', name: 'SR'}, ...]   in ORDER
#     layer['beachId']        -> 'b1' | None   (where the screen's gear is pulled)
#     distro['beachId']       -> 'b1' | None   (where the distro sits)
#     cvt['beachId']          -> 'b1' | None   (where the breakout box sits)
#
# Names are trimmed, non-empty and unique case-blind; ids come off a project
# counter (next_beach_seq) that never goes backwards, for the reason
# sync_next_group_seq gives. The typed free-text `location` the distro and
# box gears used to carry is MIGRATED on load: a record with a location and
# no beachId gets a beach of that name (matched case-blind, created if
# absent), and the location key is dropped.
# ---------------------------------------------------------------------------

def _highest_beach_seq(project):
    """Highest ``N`` across the project's existing ``b<N>`` ids, or 0."""
    beaches = (project or {}).get('beaches') or []
    max_n = 0
    if not isinstance(beaches, list):
        return max_n
    for b in beaches:
        bid = (b or {}).get('id', '') if isinstance(b, dict) else ''
        if isinstance(bid, str) and bid.startswith('b'):
            try:
                n = int(bid[1:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return max_n


def sync_next_beach_seq(project):
    """Rebase ``project['next_beach_seq']`` so no beach id is ever reused.

    Same contract as sync_next_group_seq: seeds a project that predates the
    counter above its highest existing id, never lowers a counter already
    ahead, and so is safe on the restore funnel."""
    if not isinstance(project, dict):
        return 1
    floor_seq = _highest_beach_seq(project) + 1
    try:
        stored = int(project.get('next_beach_seq'))
    except (TypeError, ValueError):
        stored = 0
    project['next_beach_seq'] = max(stored, floor_seq)
    return project['next_beach_seq']


def _next_beach_id(project):
    seq = sync_next_beach_seq(project)
    if isinstance(project, dict):
        project['next_beach_seq'] = seq + 1
    return f'b{seq}'


def _beach_norm(name):
    """The case-blind key a beach name is matched under."""
    return str(name if name is not None else '').strip().lower()


def _find_beach(project, beach_id):
    if not _is_hashable(beach_id) or beach_id is None:
        return None
    for b in (project or {}).get('beaches') or []:
        if isinstance(b, dict) and b.get('id') == beach_id:
            return b
    return None


def _find_beach_by_name(project, name):
    norm = _beach_norm(name)
    if not norm:
        return None
    for b in (project or {}).get('beaches') or []:
        if isinstance(b, dict) and _beach_norm(b.get('name')) == norm:
            return b
    return None


def _create_beach(project, name):
    """The beach called ``name``: the existing one (case-blind) or a new one
    appended to the list. Returns (beach, created); (None, False) for a
    blank name."""
    text = str(name if name is not None else '').strip()
    if not text or not isinstance(project, dict):
        return None, False
    found = _find_beach_by_name(project, text)
    if found:
        return found, False
    if not isinstance(project.get('beaches'), list):
        project['beaches'] = []
    beach = {'id': _next_beach_id(project), 'name': text}
    project['beaches'].append(beach)
    return beach, True


def _beach_records(project):
    """Every record that carries a beachId: the layers, the distros, the
    breakout boxes (processors -> slots -> card -> cvts)."""
    if not isinstance(project, dict):
        return []
    out = [l for l in (project.get('layers') or []) if isinstance(l, dict)]
    out += [d for d in (project.get('distros') or []) if isinstance(d, dict)]
    for proc in project.get('processors') or []:
        if not isinstance(proc, dict):
            continue
        for slot in proc.get('slots') or []:
            card = slot.get('card') if isinstance(slot, dict) else None
            if not isinstance(card, dict):
                continue
            out += [c for c in (card.get('cvts') or []) if isinstance(c, dict)]
    return out


def _normalize_beaches(project):
    """Repair the beach model in place, idempotently, and migrate typed
    locations into beaches.

    Runs on the same funnel _enforce_group_integrity does (file load, undo,
    redo, every project POST), so restoring twice must change nothing.

      1. ``beaches`` is a list of {id, name}; anything else is dropped. A
         blank name is dropped; a second beach with the same name (case-blind)
         folds into the first, and every beachId that pointed at it is moved
         over. A missing or duplicate id is re-issued from the counter.
      2. a beachId that names no beach is cleared.
      3. MIGRATION: a distro or box with a typed ``location`` and no beachId
         gets the beach of that name (created if absent) and its id; the
         ``location`` key is then dropped. A beachId already set wins over a
         leftover location, which is dropped too.

    A record that never had a beachId key and has no location is left
    untouched, so a file saved before beaches round-trips byte for byte.
    """
    if not isinstance(project, dict):
        return project
    raw = project.get('beaches')
    if not isinstance(raw, list):
        raw = []
    project['beaches'] = raw
    sync_next_beach_seq(project)   # before pruning: a dropped id stays spent
    kept = []
    seen_ids = set()
    by_norm = {}
    remap = {}
    for b in raw:
        if not isinstance(b, dict):
            continue
        name = str(b.get('name') if b.get('name') is not None else '').strip()
        if not name:
            continue
        bid = b.get('id')
        if not isinstance(bid, str) or not bid:
            bid = None
        norm = name.lower()
        if norm in by_norm:
            if bid is not None:
                remap[bid] = by_norm[norm]
            continue
        if bid is None or bid in seen_ids:
            bid = _next_beach_id(project)
        kept.append({'id': bid, 'name': name})
        seen_ids.add(bid)
        by_norm[norm] = bid
    project['beaches'] = kept

    for rec in _beach_records(project):
        had_key = 'beachId' in rec
        bid = rec.get('beachId')
        if _is_hashable(bid) and bid in remap:
            bid = remap[bid]
        if bid is not None and not _find_beach(project, bid):
            bid = None
        location = rec.get('location')
        if bid is None and isinstance(location, str) and location.strip():
            beach, _created = _create_beach(project, location)
            if beach:
                bid = beach['id']
        if bid is not None:
            rec.pop('location', None)
        if had_key or bid is not None:
            rec['beachId'] = bid
    return project


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
# Moved out in the 1.0 modularization; tests import these from `app`, so
# they are re-exported here by name. Nothing in this file calls them.
from resolume_geometry import (  # noqa: E402,F401
    _export_units, _export_unit_bounds, _compute_panel_contour,
    _compute_layers_contour, _compute_layers_islands, _layer_has_hidden_panels,
    _export_unit_needs_polygon, _export_unit_shapes, _resolume_polygon,
    _resolume_slice, generate_resolume_xml,
)
from routes_export import (  # noqa: E402,F401
    export_bp, create_psd_for_view, decode_base64_image, render_layer_to_image,
    render_unit_to_image, _export_unit_drawn_members,
)
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
from routes_processors import processors_bp  # noqa: E402
from routes_port_assignment import port_assignment_bp  # noqa: E402
from routes_pull_sheet import pull_sheet_bp  # noqa: E402
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
app.register_blueprint(processors_bp)
app.register_blueprint(port_assignment_bp)
app.register_blueprint(pull_sheet_bp)
app.register_blueprint(export_bp)


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
