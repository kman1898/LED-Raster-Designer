"""
Saved distro presets (persisted to disk, shared across all clients).

A distro preset is what a distro's face is - its system, input, rating per
leg, breaker and main settings, phasing, output rows and Type - saved under a
name so the next show can start from it (owner ruling, 2026-10-16: "users can SAVE their
own distros as presets"). Kept the way named layouts are: one JSON file
beside the presets folder, so they survive a restart and a new version. The
browser cleans a preset again before it applies one (app-distro-systems.js
_normalizeOutputRows); this end refuses a NEW save that could not be one,
and leaves what is already stored alone - an entry a newer version wrote
stays in the file as it was, even where this version cannot read all of it.

Every read-modify-write holds one lock and writes through a temp file of
its own, so two saves at once both land and neither fails. A file that is
not JSON is moved aside (distro_presets.json.corrupt-<time>) before the
next save, never overwritten.
"""
import json
import os
import tempfile
import threading
import time

from flask import Blueprint, request, jsonify

from app import PRESETS_DIR_PATH, log_event

distro_presets_bp = Blueprint('distro_presets', __name__)

# Beside the presets folder, like layouts. Tests point this at a scratch file.
DISTRO_PRESETS_FILE = os.path.join(os.path.dirname(PRESETS_DIR_PATH),
                                   'distro_presets', 'distro_presets.json')

MAX_PRESETS = 100
MAX_NAME = 60
MAX_ROWS = 40
MAX_ID = 20
# A full 40-row preset is about 6 KB; anything far past that is not one.
MAX_BODY = 32 * 1024

# ── Allowed values. These mirror the browser's constants; keep them in step
# (tests/test_distro_presets_robustness.py fails when they drift):
#   SYSTEMS     - DISTRO_SYSTEMS ids        (src/static/js/app-distro-systems.js)
#   CONNECTORS  - DISTRO_CONNECTORS ids     (src/static/js/app-distro-systems.js)
#   INPUTS      - DISTRO_INPUTS ids         (src/static/js/app-distro-systems.js)
#   PHASINGS    - powerPhasingSchemes() ids (src/static/js/app-phase-balance.js)
#                 plus WHOLE_MULTI_SCHEME.id (src/static/js/app-distro-systems.js)
#   DIRECT_PHASINGS - the direct-phasing select's values (app-distro-systems.js)
SYSTEMS = {'120/208', '120/240', '120', '230/400', '230'}
CONNECTORS = {'soca', 'harting', 'l2130', 'true1', 'powercon20', 'powerconxx',
              'edison', 'l520', 'l620', 'stagepin', 'cee16', 'cee32', 'schuko'}
INPUTS = {'cam100', 'cam200', 'cam400', 'cam600', 'cam800', 'l2130',
          'cee16r', 'cee32r', 'cee63', 'cee125r', 'cee16b', 'cee32b', 'cee63b', 'cee125b',
          'powerlock400', 'powerlock630'}
PHASINGS = {'rotating-ln', 'paired-ln', 'paired-ll', 'paired-ll-alt', 'rotating-ll',
            'whole-ln'}
DIRECT_PHASINGS = {'paired'}
COUPLINGS = {'ln', 'll'}
# What _distroPresetBody (app-distro-systems.js) sends; anything else on a
# new save is dropped.
DISTRO_KEYS = {'typeName', 'system', 'input', 'ratingA', 'breakers100', 'main100',
               'phasing', 'directPhasing', 'rows'}
ROW_KEYS = {'id', 'connector', 'count', 'coupling', 'breakerA', 'connectorA', 'pairedWith'}

_lock = threading.Lock()


class _Unreadable(Exception):
    """The presets file is there but could not be opened."""


def _clean_name(name):
    if not isinstance(name, str):
        return None
    name = ' '.join(name.split())
    if not name or len(name) > MAX_NAME:
        return None
    return name


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _short_str(v):
    return isinstance(v, str) and 0 < len(v) <= MAX_ID


def _valid_row(r):
    if not isinstance(r, dict) or not set(r) <= ROW_KEYS:
        return False
    if r.get('connector') not in CONNECTORS:
        return False
    if not _number(r.get('count')) or not 0 < r['count'] < 100:
        return False
    if r.get('coupling') not in COUPLINGS:
        return False
    if 'id' in r and r['id'] is not None and not _short_str(r['id']):
        return False
    if 'breakerA' in r and not (_number(r['breakerA']) and 0 < r['breakerA'] < 1000):
        return False
    # the row's connector rating override; null (or absent) is the default
    if r.get('connectorA') is not None and not (_number(r['connectorA'])
                                                and 0 < r['connectorA'] < 1000):
        return False
    if r.get('pairedWith') is not None and not _short_str(r['pairedWith']):
        return False
    return True


def _valid_distro(body):
    """A NEW save: every field this version knows checked against what the
    app can open. Unknown top-level keys are not checked here - they are
    dropped by _clean_distro."""
    if not isinstance(body, dict) or body.get('system') not in SYSTEMS:
        return False
    rows = body.get('rows')
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        return False
    if not all(_valid_row(r) for r in rows):
        return False
    rating = body.get('ratingA')
    if rating is not None and not (_number(rating) and 0 < rating < 10000):
        return False
    if body.get('input') is not None and body['input'] not in INPUTS:
        return False
    if body.get('phasing') not in (None, '') and body['phasing'] not in PHASINGS:
        return False
    if body.get('directPhasing') not in (None, '') and body['directPhasing'] not in DIRECT_PHASINGS:
        return False
    # The distro's Type (what the pull sheet names it): text or nothing.
    t = body.get('typeName')
    if t is not None and not (isinstance(t, str) and len(t) <= MAX_NAME):
        return False
    # The two 100% switches: the circuits' breakers, and the main (its
    # continuous limit, 2026-10-18). Either may be absent (off).
    for key in ('breakers100', 'main100'):
        if key in body and not isinstance(body[key], bool):
            return False
    return True


def _clean_distro(body):
    return {k: v for k, v in body.items() if k in DISTRO_KEYS}


def _listable(item):
    """What GET hands the browser: a name and something shaped like a
    distro. The browser cleans the rows again before it applies one."""
    return (isinstance(item, dict) and _clean_name(item.get('name'))
            and isinstance(item.get('distro'), dict)
            and item['distro'].get('system') in SYSTEMS
            and isinstance(item['distro'].get('rows'), list))


def _name_key(item):
    name = _clean_name(item.get('name')) if isinstance(item, dict) else None
    return name.lower() if name else None


def _read_raw():
    """Every stored entry, as stored. Missing file: none. A file that is
    not a presets file: None (the caller decides what to do with it)."""
    try:
        with open(DISTRO_PRESETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except ValueError:
        return None
    except OSError as e:
        raise _Unreadable(str(e))
    items = data.get('presets') if isinstance(data, dict) else None
    return items if isinstance(items, list) else None


def _read():
    try:
        items = _read_raw()
    except _Unreadable:
        return []
    return [i for i in (items or []) if _listable(i)]


def _read_for_write():
    """The stored entries for a save or delete. A damaged file is moved
    aside first, so the save after it never overwrites what was in it."""
    items = _read_raw()
    if items is not None:
        return items
    stamp = time.strftime('%Y%m%d-%H%M%S')
    aside = f'{DISTRO_PRESETS_FILE}.corrupt-{stamp}'
    n = 1
    while os.path.exists(aside):
        n += 1
        aside = f'{DISTRO_PRESETS_FILE}.corrupt-{stamp}-{n}'
    os.replace(DISTRO_PRESETS_FILE, aside)
    log_event('distro_presets_file_moved_aside', {'to': os.path.basename(aside)})
    return []


def _write(items):
    folder = os.path.dirname(DISTRO_PRESETS_FILE)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='.distro_presets-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'presets': items}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, DISTRO_PRESETS_FILE)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _sorted(items):
    return sorted((i for i in items if _listable(i)), key=lambda i: i['name'].lower())


def _request_body():
    """The JSON object sent, or an error reply."""
    if (request.content_length or 0) > MAX_BODY or len(request.get_data(cache=True)) > MAX_BODY:
        return None, (jsonify({'error': 'that preset is too large to save'}), 413)
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'that is not a preset this app can open'}), 400)
    return data, None


def _unreadable_reply():
    return jsonify({'error': 'the saved presets file could not be opened'}), 500


@distro_presets_bp.route('/api/distro-presets', methods=['GET'])
def list_distro_presets():
    return jsonify({'presets': _sorted(_read())})


@distro_presets_bp.route('/api/distro-presets', methods=['PUT'])
def save_distro_preset():
    """Save under a name; a preset already under that name is replaced."""
    data, err = _request_body()
    if err:
        return err
    name = _clean_name(data.get('name'))
    body = data.get('distro')
    if not name:
        return jsonify({'error': f'a preset needs a name of 1 to {MAX_NAME} characters'}), 400
    if not _valid_distro(body):
        log_event('distro_preset_rejected', {'name': name})
        return jsonify({'error': 'that is not a distro this app can open'}), 400
    with _lock:
        try:
            stored = _read_for_write()
        except _Unreadable:
            return _unreadable_reply()
        items = [i for i in stored if _name_key(i) != name.lower()]
        if len(items) >= MAX_PRESETS:
            return jsonify({'error': f'{MAX_PRESETS} presets are saved already - delete one first'}), 400
        items.append({'name': name, 'distro': _clean_distro(body)})
        _write(items)
    log_event('distro_preset_saved', {'name': name})
    return jsonify({'presets': _sorted(items)})


@distro_presets_bp.route('/api/distro-presets', methods=['DELETE'])
def delete_distro_preset():
    data, err = _request_body()
    if err:
        return err
    name = _clean_name(data.get('name'))
    if not name:
        return jsonify({'error': 'no preset by that name'}), 404
    with _lock:
        try:
            # A damaged file has nothing to delete; leave it for the next save.
            items = _read_raw() or []
        except _Unreadable:
            return _unreadable_reply()
        kept = [i for i in items if _name_key(i) != name.lower()]
        if len(kept) == len(items):
            return jsonify({'error': 'no preset by that name'}), 404
        _write(kept)
    log_event('distro_preset_deleted', {'name': name})
    return jsonify({'presets': _sorted(kept)})
