from flask import Flask, render_template, request, jsonify, make_response, send_from_directory, send_file
from flask_socketio import SocketIO, emit
import json
import uuid
import time
import io
import zipfile
import os
import sys
import datetime
import platform
import subprocess
from PIL import Image
import numpy as np

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
# Logs go next to the executable (or script), not inside the bundle
if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
    # macOS .app bundle: exe is inside Foo.app/Contents/MacOS/
    # Put logs next to the .app, not buried inside it
    if '.app/Contents/MacOS' in _APP_DIR:
        _APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_APP_DIR)))
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR_PATH = os.path.join(_APP_DIR, 'logs')
LOG_FILE_PATH = os.path.join(LOG_DIR_PATH, 'led_raster_designer.log')
LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUPS = 2
os.environ['_LRD_LOG_DIR'] = LOG_DIR_PATH
print(f'[LED Raster Designer] Log directory: {LOG_DIR_PATH}')

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

def _panel_width(layer, col):
    width = layer.get('cabinet_width', 0)
    cols = int(layer.get('columns', 0) or 0)
    if cols <= 0:
        return width
    if col == 0 and layer.get('halfFirstColumn', False):
        return width / 2
    if col == cols - 1 and layer.get('halfLastColumn', False):
        return width / 2
    return width

def _panel_height(layer, row):
    height = layer.get('cabinet_height', 0)
    rows = int(layer.get('rows', 0) or 0)
    if rows <= 0:
        return height
    if row == 0 and layer.get('halfFirstRow', False):
        return height / 2
    if row == rows - 1 and layer.get('halfLastRow', False):
        return height / 2
    return height

def _build_panels(layer, panel_states=None):
    rows = int(layer.get('rows', 0) or 0)
    cols = int(layer.get('columns', 0) or 0)
    offset_x = float(layer.get('offset_x', 0) or 0)
    offset_y = float(layer.get('offset_y', 0) or 0)

    col_x = []
    x_cursor = offset_x
    for col in range(cols):
        col_x.append(x_cursor)
        x_cursor += _panel_width(layer, col)

    row_y = []
    y_cursor = offset_y
    for row in range(rows):
        row_y.append(y_cursor)
        y_cursor += _panel_height(layer, row)

    panels = []
    panel_num = 1
    for row in range(rows):
        for col in range(cols):
            state = panel_states.get(panel_num, {}) if panel_states else {}
            panel = {
                'id': panel_num,
                'number': panel_num,
                'row': row,
                'col': col,
                'x': col_x[col],
                'y': row_y[row],
                'width': _panel_width(layer, col),
                'height': _panel_height(layer, row),
                'blank': state.get('blank', False),
                'hidden': state.get('hidden', False),
                'is_color1': (row + col) % 2 == 0
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

current_project = {
    'name': 'Untitled Project',
    'raster_width': 1920,
    'raster_height': 1080,
    'layers': [],
    'is_pristine': True
}

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
        current_project['layers'].append(default_layer)

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

@app.route('/')
def index():
    # Initialize default layer if project is empty
    initialize_default_layer()
    log_event('page_load', {'path': '/'})
    response = make_response(render_template('index.html'))
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

@app.route('/api/project', methods=['GET'])
def get_project():
    log_event('get_project')
    return jsonify(current_project)

@app.route('/api/server-session', methods=['GET'])
def get_server_session():
    """Return unique session ID that changes on server restart"""
    log_event('get_server_session', {'session_id': SERVER_SESSION_ID})
    return jsonify({
        'session_id': SERVER_SESSION_ID,
        'start_time': SERVER_START_TIME
    })

# ── Server-side preferences (shared across all clients) ──
server_preferences = {}

@app.route('/api/preferences', methods=['GET'])
def get_preferences():
    log_event('get_preferences')
    return jsonify(server_preferences)

@app.route('/api/preferences', methods=['PUT'])
def save_preferences():
    global server_preferences
    data = request.json or {}
    server_preferences = data
    log_event('save_preferences', {'keys': list(data.keys())})
    socketio.emit('preferences_updated', server_preferences)
    return jsonify({'status': 'success'})

@app.route('/api/project/new', methods=['POST'])
def new_project():
    global current_project, next_layer_id
    next_layer_id = 1  # Reset counter for new project
    current_project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [],
        'is_pristine': True
    }
    # Add default layer to new projects
    initialize_default_layer()
    log_event('new_project')
    socketio.emit('project_cleared')
    return jsonify(current_project)

@app.route('/api/project', methods=['POST'])
def save_project():
    data = request.json
    current_project.update(data)
    current_project['is_pristine'] = False
    sync_next_layer_id()
    log_event('save_project', {'name': current_project.get('name')})
    return jsonify({'status': 'success'})

@app.route('/api/project', methods=['PUT'])
def restore_project():
    """Restore entire project state (used by undo/redo and file load)"""
    global current_project
    data = request.json
    current_project = data
    current_project['is_pristine'] = False
    sync_next_layer_id()
    log_event('restore_project', {
        'name': current_project.get('name', '?'),
        'layers': len(current_project.get('layers', [])),
        'layer_names': [l.get('name', '?') for l in current_project.get('layers', [])]
    })
    socketio.emit('project_updated', current_project)
    return jsonify(current_project)

@app.route('/api/layer/add', methods=['POST'])
def add_layer():
    data = request.json
    layer = create_layer(
        name=data.get('name', f'Screen{len(current_project["layers"]) + 1}'),
        columns=data.get('columns', 8),
        rows=data.get('rows', 5),
        cabinet_width=data.get('cabinet_width', 128),
        cabinet_height=data.get('cabinet_height', 128),
        offset_x=data.get('offset_x', 0),
        offset_y=data.get('offset_y', 0)
    )
    
    # Apply additional settings from request (for duplicate/paste)
    optional_fields = [
        'color1', 'color2', 'panel_width_mm', 'panel_height_mm', 'panel_weight',
        'weight_unit', 'infoLabelSize',
        'halfFirstColumn', 'halfLastColumn', 'halfFirstRow', 'halfLastRow',
        'show_numbers', 'number_size', 'show_panel_borders', 'show_circle_with_x', 
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
        'showDataFlowPortInfo',
        'portLabelTemplatePrimary', 'portLabelTemplateReturn',
        'portLabelOverridesPrimary', 'portLabelOverridesReturn',
        'customPortPaths', 'customPortIndex',
        'randomDataColors',
        'scrExportEnabled', 'scrScreenNumber', 'scrScreenX', 'scrScreenY',
        'scrPortSendingCards', 'scrPortNumbers',
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
        'total_layers': len(current_project['layers'])
    })
    
    # Apply hidden panels (for duplicate)
    if 'hiddenPanels' in data and data['hiddenPanels']:
        hidden_positions = {(hp['row'], hp['col']) for hp in data['hiddenPanels']}
        for panel in layer['panels']:
            if (panel['row'], panel['col']) in hidden_positions:
                panel['hidden'] = True
    
    current_project['layers'].append(layer)
    current_project['is_pristine'] = False
    socketio.emit('layer_added', layer)
    return jsonify(layer)

@app.route('/api/layer/add-image', methods=['POST'])
def add_image_layer():
    data = request.json or {}
    layer = create_image_layer(
        name=data.get('name', f'Image{len(current_project["layers"]) + 1}'),
        image_data=data.get('imageData', ''),
        image_width=data.get('imageWidth', 0),
        image_height=data.get('imageHeight', 0),
        offset_x=data.get('offset_x', 0),
        offset_y=data.get('offset_y', 0)
    )
    if 'imageScale' in data:
        layer['imageScale'] = data['imageScale']
    log_event('add_image_layer', {'name': layer.get('name'), 'id': layer.get('id')})
    current_project['layers'].append(layer)
    current_project['is_pristine'] = False
    socketio.emit('layer_added', layer)
    return jsonify(layer)

@app.route('/api/layer/<int:layer_id>', methods=['PUT'])
def update_layer(layer_id):
    data = request.json
    layer = next((l for l in current_project['layers'] if l['id'] == layer_id), None)
    
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    previous_offset_x = layer.get('offset_x', 0)
    previous_offset_y = layer.get('offset_y', 0)

    for key in ['name', 'columns', 'rows', 'cabinet_width', 'cabinet_height', 
                'offset_x', 'offset_y', 'rotation', 'color1', 'color2', 
                'panel_width_mm', 'panel_height_mm', 'panel_weight', 'weight_unit', 'visible',
                'halfFirstColumn', 'halfLastColumn', 'halfFirstRow', 'halfLastRow',
                'show_numbers', 'number_size', 'show_panel_borders', 'show_circle_with_x', 'border_color',
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
                'scrExportEnabled', 'scrScreenNumber', 'scrScreenX', 'scrScreenY',
                'scrPortSendingCards', 'scrPortNumbers']:
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
    if layer.get('type') != 'image' and (
        'columns' in data or 'rows' in data or 'cabinet_width' in data or 'cabinet_height' in data
            or 'halfFirstColumn' in data or 'halfLastColumn' in data
            or 'halfFirstRow' in data or 'halfLastRow' in data):
        # Save existing panel states (hidden, blank) before regenerating
        old_panel_states = {}
        if 'panels' in layer:
            for p in layer['panels']:
                old_panel_states[p['id']] = {
                    'hidden': p.get('hidden', False),
                    'blank': p.get('blank', False)
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
    
    current_project['is_pristine'] = False
    socketio.emit('layer_updated', layer)
    return jsonify(layer)

@app.route('/api/layer/<int:layer_id>', methods=['DELETE'])
def delete_layer(layer_id):
    deleted_name = None
    for l in current_project['layers']:
        if l['id'] == layer_id:
            deleted_name = l.get('name', '?')
            break
    current_project['layers'] = [l for l in current_project['layers'] if l['id'] != layer_id]
    current_project['is_pristine'] = False
    log_event('delete_layer', {'id': layer_id, 'name': deleted_name, 'remaining_layers': len(current_project['layers'])})
    socketio.emit('layer_deleted', {'id': layer_id})
    return jsonify(current_project)

@app.route('/api/layer/<int:layer_id>/panel/<int:panel_id>/toggle', methods=['POST'])
def toggle_panel_blank(layer_id, panel_id):
    layer = next((l for l in current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    panel = next((p for p in layer['panels'] if p['id'] == panel_id), None)
    if not panel:
        return jsonify({'error': 'Panel not found'}), 404
    
    panel['blank'] = not panel['blank']
    log_event('toggle_panel_blank', {'layer_id': layer_id, 'panel_id': panel_id, 'blank': panel['blank']})
    socketio.emit('panel_updated', {'layer_id': layer_id, 'panel': panel})
    return jsonify(panel)

@app.route('/api/layer/<int:layer_id>/panel/<int:panel_id>/toggle_hidden', methods=['POST'])
def toggle_panel_hidden(layer_id, panel_id):
    layer = next((l for l in current_project['layers'] if l['id'] == layer_id), None)
    if not layer:
        return jsonify({'error': 'Layer not found'}), 404
    
    panel = next((p for p in layer['panels'] if p['id'] == panel_id), None)
    if not panel:
        return jsonify({'error': 'Panel not found'}), 404
    
    panel['hidden'] = not panel.get('hidden', False)
    log_event('toggle_panel_hidden', {'layer_id': layer_id, 'panel_id': panel_id, 'hidden': panel['hidden']})
    socketio.emit('panel_updated', {'layer_id': layer_id, 'panel': panel})
    return jsonify(panel)

@app.route('/api/layer/<int:layer_id>/panels/set_hidden', methods=['POST'])
def set_panels_hidden(layer_id):
    """Bulk set hidden state for multiple panels."""
    layer = next((l for l in current_project['layers'] if l['id'] == layer_id), None)
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

    log_event('bulk_set_panels_hidden', {'layer_id': layer_id, 'count': len(updated)})
    socketio.emit('layer_updated', layer)
    return jsonify({'updated': len(updated)})


@app.route('/api/log', methods=['POST'])
def client_log():
    data = request.json or {}
    action = data.get('action', 'client_log')
    details = data.get('details', {})
    log_event(action, details, source='client')
    return jsonify({'status': 'ok'})


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
    
    # Add each layer (in reverse order so first layer is on bottom in Photoshop layer panel)
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

def decode_base64_bytes(data_url):
    if ',' in data_url:
        data_url = data_url.split(',', 1)[1]
    return base64.b64decode(data_url)

def _run_dialog_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return None
        value = (result.stdout or '').strip()
        return value or None
    except Exception:
        return None

def _native_choose_save_file(suggested_name):
    system = platform.system()
    if system == 'Darwin':
        script = f'POSIX path of (choose file name with prompt "Save File" default name "{suggested_name}")'
        return _run_dialog_command(['osascript', '-e', script])
    if system == 'Windows':
        script = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$d=New-Object System.Windows.Forms.SaveFileDialog;'
            f'$d.FileName="{suggested_name}";'
            'if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $d.FileName}'
        )
        return _run_dialog_command(['powershell', '-NoProfile', '-Command', script])
    # Linux fallback (if zenity is installed)
    return _run_dialog_command(['zenity', '--file-selection', '--save', '--confirm-overwrite', f'--filename={suggested_name}'])

def _native_choose_directory():
    system = platform.system()
    if system == 'Darwin':
        script = 'POSIX path of (choose folder with prompt "Select Export Folder")'
        return _run_dialog_command(['osascript', '-e', script])
    if system == 'Windows':
        script = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$d=New-Object System.Windows.Forms.FolderBrowserDialog;'
            'if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $d.SelectedPath}'
        )
        return _run_dialog_command(['powershell', '-NoProfile', '-Command', script])
    return _run_dialog_command(['zenity', '--file-selection', '--directory'])

@app.route('/api/native-dialog/save-file', methods=['POST'])
def native_dialog_save_file():
    data = request.get_json() or {}
    suggested_name = data.get('suggested_name', 'output.bin')
    try:
        log_event('native_dialog_save_file_start', {'suggested_name': suggested_name})
        file_path = _native_choose_save_file(suggested_name)
        if not file_path:
            log_event('native_dialog_save_file_cancelled', {'suggested_name': suggested_name})
            return jsonify({'ok': False, 'cancelled': True})
        log_event('native_dialog_save_file', {'path': file_path})
        return jsonify({'ok': True, 'path': file_path})
    except Exception as e:
        log_event('native_dialog_save_file_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/native-dialog/select-directory', methods=['POST'])
def native_dialog_select_directory():
    try:
        log_event('native_dialog_select_directory_start', {})
        directory = _native_choose_directory()
        if not directory:
            log_event('native_dialog_select_directory_cancelled', {})
            return jsonify({'ok': False, 'cancelled': True})
        log_event('native_dialog_select_directory', {'directory': directory})
        return jsonify({'ok': True, 'path': directory})
    except Exception as e:
        log_event('native_dialog_select_directory_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/native-dialog/write-file', methods=['POST'])
def native_dialog_write_file():
    data = request.get_json() or {}
    file_path = data.get('path')
    data_url = data.get('data_url')
    if not file_path or not data_url:
        log_event('native_dialog_write_file_invalid', {'has_path': bool(file_path), 'has_data': bool(data_url)})
        return jsonify({'ok': False, 'error': 'path and data_url are required'}), 400
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        content = decode_base64_bytes(data_url)
        with open(file_path, 'wb') as f:
            f.write(content)
        exists = os.path.exists(file_path)
        size = os.path.getsize(file_path) if exists else 0
        log_event('native_dialog_write_file', {'path': file_path, 'bytes': len(content), 'exists': exists, 'size': size})
        return jsonify({'ok': True})
    except Exception as e:
        log_event('native_dialog_write_file_error', {'path': file_path, 'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/native-dialog/write-multiple', methods=['POST'])
def native_dialog_write_multiple():
    data = request.get_json() or {}
    directory = data.get('directory')
    files = data.get('files', [])
    if not directory or not isinstance(files, list):
        return jsonify({'ok': False, 'error': 'directory and files are required'}), 400
    try:
        os.makedirs(directory, exist_ok=True)
        written = 0
        for item in files:
            filename = item.get('filename')
            data_url = item.get('data_url')
            if not filename or not data_url:
                continue
            safe_name = os.path.basename(filename)
            file_path = os.path.join(directory, safe_name)
            content = decode_base64_bytes(data_url)
            with open(file_path, 'wb') as f:
                f.write(content)
            written += 1
        log_event('native_dialog_write_multiple', {'directory': directory, 'requested': len(files), 'written': written})
        return jsonify({'ok': True, 'written': written})
    except Exception as e:
        log_event('native_dialog_write_multiple_error', {'directory': directory, 'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500


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
        
        # Create PSD with alpha channel (4 channels: RGB + Alpha)
        psd = PsdFile(num_channels=4, height=height, width=width, color_mode=ColorMode.rgb)
        
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
                -1: psd_layers.ChannelImageData(image=np.full((actual_height, actual_width), 255, dtype=np.uint8), compression=Compression.raw),  # Full opacity
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
                
                # Create PSD with alpha channel
                psd = PsdFile(num_channels=4, height=height, width=width, color_mode=ColorMode.rgb)
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
                        -1: psd_layers.ChannelImageData(image=np.full((actual_height, actual_width), 255, dtype=np.uint8), compression=Compression.raw),
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
    """Generate Resolume Arena Advanced Output XML from project layers."""
    import random
    screen_id = random.randint(1000000000000, 9999999999999)

    layers = project.get('layers', [])
    # Filter to visible screen layers only
    screen_layers = [l for l in layers if l.get('type') == 'screen' and l.get('visible', True)]

    # Build panels for layers that don't have them
    for layer in screen_layers:
        if not layer.get('panels'):
            layer['panels'] = _build_panels(layer)

    slices_xml = ""
    for layer in screen_layers:
        slice_id = random.randint(1000000000000, 9999999999999)
        if _layer_has_hidden_panels(layer):
            slices_xml += _resolume_polygon(layer, slice_id)
        else:
            slices_xml += _resolume_slice(layer, slice_id)

    # Screen-level output params
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

    device_hash = random.randint(1000000000000000000, 9999999999999999999)

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
        f'\t\t<CurrentCompositionTextureSize width="{raster_w}" height="{raster_h}"/>\n'
        f'\t\t<screens>\n'
        f'\t\t\t<Screen name="Screen 1" uniqueId="{screen_id}">\n'
        f'\t\t\t\t<Params name="Params">\n'
        f'\t\t\t\t\t<Param name="Name" T="STRING" default="" value="Screen 1"/>\n'
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
        f'\t\t\t\t\t<OutputDeviceVirtual name="Screen 1" deviceId="VirtualScreen 1" idHash="{device_hash}" width="{raster_w}" height="{raster_h}">\n'
        f'\t\t\t\t\t\t<Params name="Params">\n'
        f'{device_param_range("Width", "800", str(raster_w))}'
        f'{device_param_range("Height", "600", str(raster_h))}'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t</OutputDeviceVirtual>\n'
        f'\t\t\t\t</OutputDevice>\n'
        f'\t\t\t</Screen>\n'
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


# ── NovaStar SCR Export ─────────────────────────────────────────────
from scr_encoder import generate_scr_files

@app.route('/api/export/scr', methods=['POST'])
def export_scr():
    """Export project as NovaStar SCR sending card mapping file(s)."""
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', current_project.get('name', 'Untitled Project'))
        layers = data.get('layers', [])

        if not layers:
            return jsonify({'error': 'No SCR-enabled layers provided'}), 400

        results = generate_scr_files(project_name, layers)

        if not results:
            return jsonify({'error': 'No SCR data generated'}), 400

        log_event('export_scr', {
            'project_name': project_name,
            'files': len(results),
            'layers': len(layers),
        })

        if len(results) == 1:
            filename, scr_data = results[0]
            return send_file(
                io.BytesIO(scr_data),
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=filename
            )
        else:
            # Multiple sending cards — return ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename, scr_data in results:
                    zf.writestr(filename, scr_data)
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{project_name}_SCR.zip"
            )
    except Exception as e:
        print(f"SCR export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'SCR export failed: {str(e)}'}), 500


# ── Update Checker ──────────────────────────────────────────────────
from updater import check_for_update, get_current_version

@app.route('/api/update/check', methods=['GET'])
def api_check_update():
    """Check for a newer release on GitHub."""
    try:
        force = request.args.get('force', '').lower() in ('1', 'true', 'yes')
        result = check_for_update(force=force)
        if result.get('error'):
            log_event('update_check_error', {'error': result['error'], 'force': force})
        elif result.get('available'):
            log_event('update_available', {
                'current': result.get('current_version'),
                'latest': result.get('latest_version'),
            })
        else:
            log_event('update_check_ok', {'version': result.get('current_version')})
        return jsonify(result)
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        log_event('update_check_crash', {
            'error': str(e),
            'type': type(e).__name__,
            'traceback': error_detail,
        })
        return jsonify({
            "available": False,
            "current_version": get_current_version(),
            "latest_version": None,
            "download_url": None,
            "release_notes": None,
            "checksums": None,
            "error": f"Internal error: {type(e).__name__}: {e}",
        })

@app.route('/api/version', methods=['GET'])
def api_version():
    """Return the current app version."""
    return jsonify({"version": get_current_version()})


@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('project_data', current_project)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

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

    print('=' * 60)
    print('LED RASTER DESIGNER')
    print('=' * 60)
    print('Server starting...')
    print(f'Local access:   http://127.0.0.1:8050')
    print(f'Network access: http://{local_ip}:8050')
    print('=' * 60)

    # Auto-open browser when running as bundled executable
    if getattr(sys, 'frozen', False):
        import webbrowser
        import threading
        threading.Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:8050')).start()

    run_server(host='0.0.0.0', port=8050)
