"""
Server-side preference routes (shared across all clients).

server_preferences stays defined in app (it's also read by the canvas
auto-placement logic and reset by tests). save_preferences REASSIGNS it, so
this blueprint accesses it through the app module attribute (app.server_preferences)
rather than a `from app import` binding — otherwise a reassignment here wouldn't
be visible to app.py or the tests.
"""
from flask import Blueprint, request, jsonify

import app
from app import log_event, socketio

preferences_bp = Blueprint('preferences', __name__)


@preferences_bp.route('/api/preferences', methods=['GET'])
def get_preferences():
    log_event('get_preferences')
    return jsonify(app.server_preferences)


@preferences_bp.route('/api/preferences', methods=['PUT'])
def save_preferences():
    # Only a JSON object is a preferences record. Until 2026-09-23 any JSON
    # body was stored as-is - a list, a string, a number - and the first
    # reader to call .get() on it (POST /api/canvas reading canvasGap,
    # preferred_power_breakout reading breakoutType) answered 500. A body
    # that is not an object is refused and the stored record stands.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        log_event('save_preferences_rejected', {'type': type(data).__name__})
        return jsonify({'error': 'preferences must be a JSON object'}), 400
    app.server_preferences = data
    log_event('save_preferences', {'keys': list(data.keys())})
    socketio.emit('preferences_updated', app.server_preferences)
    return jsonify({'status': 'success'})
