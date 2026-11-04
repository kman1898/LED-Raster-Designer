"""
Saved cable stock presets (persisted to disk, shared across all clients).

A show's CABLE STOCK is the cable lengths it has on hand (owner ruling,
2026-10-20: "in preferences we need to be able to set cable lengths
available on a show and load presets"). The stock itself lives in the show
file (project['cableStock'], app-cable-units.js); a preset is a stock saved
under a name - one per shop or vendor - that Preferences loads into the open
show, and that a NEW show starts with when the Preferences name it as the
default (server_preferences['cableStockDefault']).

Kept the way distro presets are (routes_distro_presets.py): one JSON file
beside the presets folder, so they survive a restart and a new version.
Every read-modify-write holds one lock and writes through a temp file of
its own; a file that is not JSON is moved aside
(cable_stock_presets.json.corrupt-<time>) before the next save, never
overwritten.

A stock is { perKind, ft: {all, multi, data, circuit, l2130, harting,
direct, feeder, fiberSingle, fiberMulti}, m: {...} }: one shared list, or a list per kind of cable,
in feet and in meters. Each list is lengths, ascending, once each. The
L21-30, Harting, direct-output and feeder lists came on 2026-10-21; a preset
saved before then has none, and reads the L21-30 and Harting lists from its
multi list and the direct-output list from its circuit list (FALLBACK), the
lists those cables were pulled from then.

FIBER (owner, 2026-11-04: single mode and multimode NovaStar boxes): two
more lists, fiberSingle and fiberMulti - a TAC, MTP or opticalCON is pulled
from the list of its boxes' mode. They are their own lists whatever perKind
says, and a stock saved before them has none: its fiber is written as typed.
"""
import json
import os
import tempfile
import threading
import time

from flask import Blueprint, request, jsonify

from app import PRESETS_DIR_PATH, log_event

cable_stock_bp = Blueprint('cable_stock', __name__)

# Beside the presets folder, like distro presets. Tests point this at a
# scratch file.
CABLE_STOCK_PRESETS_FILE = os.path.join(os.path.dirname(PRESETS_DIR_PATH),
                                        'cable_stock_presets', 'cable_stock_presets.json')

MAX_PRESETS = 100
MAX_NAME = 60
MAX_LENGTHS = 40          # lengths in one list
MAX_LENGTH = 100000       # past any cable a show pulls
MAX_BODY = 16 * 1024

# Mirrors app-cable-units.js CABLE_UNITS / CABLE_STOCK_ALL / CABLE_STOCK_KINDS
# / CABLE_STOCK_FIBER / CABLE_STOCK_FALLBACK.
UNITS = ('ft', 'm')
LISTS = ('all', 'multi', 'data', 'circuit', 'l2130', 'harting', 'direct', 'feeder',
         'fiberSingle', 'fiberMulti')
FALLBACK = {'l2130': 'multi', 'harting': 'multi', 'direct': 'circuit'}

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


def _clean_list(values):
    """Positive lengths, ascending, once each; None when `values` is not a
    list of lengths (a non-number, a zero, too many)."""
    if not isinstance(values, list) or len(values) > MAX_LENGTHS:
        return None
    out = set()
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        if not 0 < v <= MAX_LENGTH:
            return None
        v = round(float(v), 6)
        out.add(int(v) if v.is_integer() else v)
    return sorted(out)


def normalize_stock(stock):
    """A stock as stored, or None when `stock` is not one. A missing unit or
    list is empty; anything present must be a list of lengths."""
    if not isinstance(stock, dict):
        return None
    per_kind = stock.get('perKind', False)
    if not isinstance(per_kind, bool):
        return None
    out = {'perKind': per_kind}
    for unit in UNITS:
        lists = stock.get(unit, {})
        if lists is None:
            lists = {}
        if not isinstance(lists, dict):
            return None
        out[unit] = {}
        for key in LISTS:
            raw = lists.get(key)
            if key not in lists and key in FALLBACK:
                raw = lists.get(FALLBACK[key])
            cleaned = _clean_list(raw or [])
            if cleaned is None:
                return None
            out[unit][key] = cleaned
    return out


def _listable(item):
    return (isinstance(item, dict) and _clean_name(item.get('name'))
            and normalize_stock(item.get('stock')) is not None)


def _name_key(item):
    name = _clean_name(item.get('name')) if isinstance(item, dict) else None
    return name.lower() if name else None


def _read_raw():
    """Every stored entry, as stored. Missing file: none. A file that is
    not a presets file: None."""
    try:
        with open(CABLE_STOCK_PRESETS_FILE, 'r', encoding='utf-8') as f:
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
    aside = f'{CABLE_STOCK_PRESETS_FILE}.corrupt-{stamp}'
    n = 1
    while os.path.exists(aside):
        n += 1
        aside = f'{CABLE_STOCK_PRESETS_FILE}.corrupt-{stamp}-{n}'
    os.replace(CABLE_STOCK_PRESETS_FILE, aside)
    log_event('cable_stock_presets_file_moved_aside', {'to': os.path.basename(aside)})
    return []


def _write(items):
    folder = os.path.dirname(CABLE_STOCK_PRESETS_FILE)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='.cable_stock_presets-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'presets': items}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CABLE_STOCK_PRESETS_FILE)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _sorted(items):
    return [{'name': i['name'], 'stock': normalize_stock(i['stock'])}
            for i in sorted((i for i in items if _listable(i)), key=lambda i: i['name'].lower())]


def preset_stock(name):
    """The stock of the preset called `name` (any case), or None."""
    key = _clean_name(name)
    if not key:
        return None
    for item in _read():
        if _name_key(item) == key.lower():
            return normalize_stock(item['stock'])
    return None


def default_stock(prefs):
    """The stock a NEW show starts with: the preset the Preferences name as
    the default (cableStockDefault), or None - no default, or a default
    whose preset is gone."""
    if not isinstance(prefs, dict):
        return None
    return preset_stock(prefs.get('cableStockDefault'))


def _request_body():
    if (request.content_length or 0) > MAX_BODY or len(request.get_data(cache=True)) > MAX_BODY:
        return None, (jsonify({'error': 'that preset is too large to save'}), 413)
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'that is not a cable stock this app can open'}), 400)
    return data, None


def _unreadable_reply():
    return jsonify({'error': 'the saved presets file could not be opened'}), 500


@cable_stock_bp.route('/api/cable-stock-presets', methods=['GET'])
def list_cable_stock_presets():
    return jsonify({'presets': _sorted(_read())})


@cable_stock_bp.route('/api/cable-stock-presets', methods=['PUT'])
def save_cable_stock_preset():
    """Save under a name; a preset already under that name is replaced."""
    data, err = _request_body()
    if err:
        return err
    name = _clean_name(data.get('name'))
    if not name:
        return jsonify({'error': f'a preset needs a name of 1 to {MAX_NAME} characters'}), 400
    stock = normalize_stock(data.get('stock'))
    if stock is None:
        log_event('cable_stock_preset_rejected', {'name': name})
        return jsonify({'error': 'that is not a cable stock this app can open'}), 400
    with _lock:
        try:
            stored = _read_for_write()
        except _Unreadable:
            return _unreadable_reply()
        items = [i for i in stored if _name_key(i) != name.lower()]
        if len(items) >= MAX_PRESETS:
            return jsonify({'error': f'{MAX_PRESETS} presets are saved already - delete one first'}), 400
        items.append({'name': name, 'stock': stock})
        _write(items)
    log_event('cable_stock_preset_saved', {'name': name})
    return jsonify({'presets': _sorted(items)})


@cable_stock_bp.route('/api/cable-stock-presets', methods=['DELETE'])
def delete_cable_stock_preset():
    data, err = _request_body()
    if err:
        return err
    name = _clean_name(data.get('name'))
    if not name:
        return jsonify({'error': 'no preset by that name'}), 404
    with _lock:
        try:
            items = _read_raw() or []
        except _Unreadable:
            return _unreadable_reply()
        kept = [i for i in items if _name_key(i) != name.lower()]
        if len(kept) == len(items):
            return jsonify({'error': 'no preset by that name'}), 404
        _write(kept)
    log_event('cable_stock_preset_deleted', {'name': name})
    return jsonify({'presets': _sorted(kept)})
