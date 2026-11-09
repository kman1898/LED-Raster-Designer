"""
Version, update-check and license routes.

Thin wrappers over the updater module; import log_event from app.
"""
import os
import sys

from flask import Blueprint, Response, request, jsonify

import updater
from updater import check_for_update, get_current_version
from app import log_event

version_bp = Blueprint('version', __name__)
updater.set_event_logger(log_event)


def _from_host():
    """Only the machine running the app may download or run its update: a
    tablet on the show network must not close the app on the host."""
    from routes_dialog import _is_same_machine
    return _is_same_machine(request.remote_addr or '')


@version_bp.route('/api/update/check', methods=['GET'])
def api_check_update():
    """Check for a newer release on GitHub."""
    try:
        force = request.args.get('force', '').lower() in ('1', 'true', 'yes')
        result = dict(check_for_update(force=force))
        result['can_install'] = bool(result.get('can_install')) and _from_host()
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
            "installer": None,
            "can_install": False,
            "error": f"Internal error: {type(e).__name__}: {e}",
        })


# ── Update in place (installed Windows copies; updater.py does the work) ──

def _not_host():
    log_event('update_rejected_remote', {'remote_addr': request.remote_addr, 'path': request.path})
    return jsonify({'ok': False, 'error': 'Only the computer running the app can update it.'}), 403


@version_bp.route('/api/update/download', methods=['POST'])
def api_update_download():
    """Start downloading the offered setup; a repeat call starts nothing."""
    if not _from_host():
        return _not_host()
    return jsonify(updater.start_download())


@version_bp.route('/api/update/status', methods=['GET'])
def api_update_status():
    """Where the download is: the banner polls this."""
    return jsonify(updater.download_status())


@version_bp.route('/api/update/install', methods=['POST'])
def api_update_install():
    """Run the downloaded setup, then quit; the setup reopens the app.

    Unsaved changes are never dropped here: the page asks Save, Don't Save
    or Cancel first (confirmUnsavedChanges, the same question New and Open
    ask) and says {"discard": true} only once the user answered. Any page
    still holding unsaved changes otherwise refuses the install (409), so
    the page can ask about them.
    """
    if not _from_host():
        return _not_host()
    import routes_project
    data = request.get_json(silent=True) or {}
    if routes_project.project_unsaved() and data.get('discard') is not True:
        log_event('update_install_unsaved', {})
        return jsonify({'ok': False, 'unsaved': True,
                        'error': 'The show has changes that are not saved.'}), 409
    result = updater.install_update()
    log_event('update_install', {'ok': result.get('ok'), 'error': result.get('error')})
    return jsonify(result), (200 if result.get('ok') else 400)


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
