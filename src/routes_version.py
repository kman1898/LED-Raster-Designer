"""
Version, update-check and license routes.

Thin wrappers over the updater module; import log_event from app.
"""
import os
import sys

from flask import Blueprint, Response, request, jsonify

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


def _bundled_path(name):
    """Where a repo-root text file (LICENSE, THIRD-PARTY-NOTICES) lives:
    bundled at the root of the PyInstaller build (led_raster_designer.spec's
    datas), at the repo root from source (one directory above src/)."""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, name)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(src_dir), name)


def _license_path():
    return _bundled_path('LICENSE')


def _notices_path():
    return _bundled_path('THIRD-PARTY-NOTICES')


def _serve_text(path, missing):
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return Response(missing, status=404,
                        content_type='text/plain; charset=utf-8')
    return Response(data, content_type='text/plain; charset=utf-8')


@version_bp.route('/api/license', methods=['GET'])
def api_license():
    """Return the LICENSE text as-is (Help > License)."""
    return _serve_text(_license_path(),
                       'The license file is missing from this build.')


@version_bp.route('/api/third-party-notices', methods=['GET'])
def api_third_party_notices():
    """Return THIRD-PARTY-NOTICES as-is (Help > License, second tab)."""
    return _serve_text(_notices_path(),
                       'The third-party notices are missing from this build.')
