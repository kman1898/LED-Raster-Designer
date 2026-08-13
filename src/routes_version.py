"""
Version + update-check routes.

Thin wrappers over the updater module; import log_event from app.
"""
from flask import Blueprint, request, jsonify

from updater import check_for_update, get_current_version
from app import log_event

version_bp = Blueprint('version', __name__)


@version_bp.route('/api/update/check', methods=['GET'])
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


@version_bp.route('/api/version', methods=['GET'])
def api_version():
    """Return the current app version."""
    return jsonify({"version": get_current_version()})
