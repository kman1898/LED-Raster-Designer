"""
Panel-catalog routes.

The bundled static/data/panel_catalog.json is the source of truth shipped with
each release. To let users get newer panels between releases, the client can
call /api/panel-catalog/refresh and we proxy a fetch of the canonical file from
GitHub raw (server-side, to sidestep browser CORS / corporate firewalls) and
cache it in-process for a few minutes. Self-contained except for log_event.
"""
import os
import json
import time
import datetime
import hashlib
import urllib.request
import urllib.error
import ssl

from flask import Blueprint, jsonify

from app import log_event

try:
    import certifi
    _CERTIFI_PATH = certifi.where()
except Exception:
    _CERTIFI_PATH = None

panel_catalog_bp = Blueprint('panel_catalog', __name__)

_PANEL_CATALOG_RAW_URL = 'https://raw.githubusercontent.com/kman1898/LED-Raster-Designer/main/src/static/data/panel_catalog.json'
_panel_catalog_cache = {'fetched_at': 0, 'payload': None}
_PANEL_CATALOG_CACHE_TTL = 300  # seconds


def _make_ssl_context():
    """Build an SSL context using certifi's CA bundle when available.
    Fixes outbound HTTPS calls from the PyInstaller-bundled .app, where
    Python's stdlib ssl module can't find the system cert store and every
    handshake fails with URLError("CERTIFICATE_VERIFY_FAILED")."""
    if _CERTIFI_PATH:
        try:
            return ssl.create_default_context(cafile=_CERTIFI_PATH)
        except Exception:
            pass
    return ssl.create_default_context()


def _bundled_panel_catalog_path():
    return os.path.join(os.path.dirname(__file__), 'static', 'data', 'panel_catalog.json')


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _bundled_panel_catalog_sha():
    try:
        with open(_bundled_panel_catalog_path(), 'rb') as f:
            return _sha256_bytes(f.read())
    except Exception:
        return ''


@panel_catalog_bp.route('/api/panel-catalog/info', methods=['GET'])
def panel_catalog_info():
    """Lightweight metadata used on app boot to compare against the upstream
    catalog without forcing a full GitHub fetch every time."""
    try:
        with open(_bundled_panel_catalog_path(), 'rb') as f:
            data = f.read()
        catalog = json.loads(data)
        panel_count = sum(len(v) for v in catalog.values() if isinstance(v, list))
        return jsonify({
            'bundledSha': _sha256_bytes(data),
            'panelCount': panel_count,
            'mfrCount': len(catalog),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@panel_catalog_bp.route('/api/panel-catalog/refresh', methods=['GET'])
def panel_catalog_refresh():
    """Fetch the canonical panel_catalog.json from GitHub raw and return it
    along with a SHA the client uses to detect changes. Cached in-process for
    a few minutes."""
    now = time.time()
    cached = _panel_catalog_cache
    if cached['payload'] and (now - cached['fetched_at']) < _PANEL_CATALOG_CACHE_TTL:
        log_event('panel_catalog_refresh_cache_hit', {'age_s': round(now - cached['fetched_at'], 1)})
        payload = dict(cached['payload'])
        payload['fromCache'] = True
        return jsonify(payload)
    log_event('panel_catalog_refresh_start', {'url': _PANEL_CATALOG_RAW_URL, 'cafile': _CERTIFI_PATH or 'system'})
    try:
        req = urllib.request.Request(
            _PANEL_CATALOG_RAW_URL,
            headers={'User-Agent': 'led-raster-designer'}
        )
        with urllib.request.urlopen(req, timeout=10, context=_make_ssl_context()) as resp:
            data = resp.read()
        catalog = json.loads(data)
        if not isinstance(catalog, dict):
            raise ValueError('unexpected catalog shape')
        sha = _sha256_bytes(data)
        panel_count = sum(len(v) for v in catalog.values() if isinstance(v, list))
        payload = {
            'catalog': catalog,
            'sha': sha,
            'panelCount': panel_count,
            'mfrCount': len(catalog),
            'fetchedAt': datetime.datetime.utcnow().isoformat() + 'Z',
            'bundledSha': _bundled_panel_catalog_sha(),
        }
        _panel_catalog_cache['payload'] = payload
        _panel_catalog_cache['fetched_at'] = now
        log_event('panel_catalog_refresh_done', {'panels': panel_count, 'sha': sha[:8]})
        return jsonify(dict(payload, fromCache=False))
    except urllib.error.URLError as e:
        log_event('panel_catalog_refresh_error', {'kind': 'network', 'detail': str(e)})
        return jsonify({'error': f'network: {e}'}), 502
    except Exception as e:
        log_event('panel_catalog_refresh_error', {'kind': 'other', 'detail': str(e)})
        return jsonify({'error': str(e)}), 500
