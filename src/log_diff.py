"""What a log line says: the change an edit made (a diff, never the whole
object), which area of the app and which level it belongs to, its one
plain-English message, and the redaction a log copied for a bug report
gets.

Used by app.log_event (every line written), routes_layers / routes_canvas /
routes_processors / routes_preferences (the diff of an edit) and
routes_logs (the viewer's filters, the fill-in of older lines and the
"Copy for a bug report" redaction). tests/test_log_diff.py holds it to
all of that.

House rules for every message: no em or en dash, "to" for a change, the
words the app shows ("circuits", "Power in").
"""
import json
import re

MISSING = object()

# ── values that never reach the log ─────────────────────────────────────
#
# Image payloads (a screen's imageData, the binder logo, any data URL or
# long base64 run) are logged as their size. A key that names a secret is
# hidden whatever it holds (there are no password fields in the app
# today; this keeps one added later out of the log).
_SECRET_KEY_RE = re.compile(r'(password|passwd|secret|token|api_?key)', re.I)
_PAYLOAD_KEY_RE = re.compile(r'(imagedata|dataurl|data_url|logo$|thumbnail|bitmap|png_?bytes)', re.I)
_BASE64_RE = re.compile(r'^[A-Za-z0-9+/]{200,}={0,2}$')
_STR_MAX = 80


def is_payload(key, value):
    """True for a value that is an image or file payload."""
    if not isinstance(value, str):
        return False
    if value.startswith('data:') and len(value) > 64:
        return True
    if key and _PAYLOAD_KEY_RE.search(str(key)) and len(value) > 64:
        return True
    if len(value) < 200 or not _BASE64_RE.match(value[:4096]):
        return False
    # Real encoded bytes mix cases and digits; a run of one letter does not.
    head = value[:512]
    return (any(c.isdigit() for c in head) and any(c.isupper() for c in head)
            and any(c.islower() for c in head))


def scrub(value, key=None, depth=0):
    """`value` with every payload replaced by its size and every secret
    hidden. Containers are copied only when something in them changed."""
    if key is not None and _SECRET_KEY_RE.search(str(key)) and value not in (None, '', False):
        return '[hidden]'
    if isinstance(value, str):
        return f'<{len(value)} chars>' if is_payload(key, value) else value
    if depth >= 6:
        return value
    if isinstance(value, dict):
        out = None
        for k, v in value.items():
            nv = scrub(v, k, depth + 1)
            if nv is not v:
                if out is None:
                    out = dict(value)
                out[k] = nv
        return value if out is None else out
    if isinstance(value, list):
        out = None
        for i, v in enumerate(value):
            nv = scrub(v, key, depth + 1)
            if nv is not v:
                if out is None:
                    out = list(value)
                out[i] = nv
        return value if out is None else out
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def short(value, limit=_STR_MAX):
    """A value as it reads in a message: strings cut at `limit`, lists and
    objects summarized once they are long."""
    if value is MISSING or value is None:
        return '(none)'
    if isinstance(value, bool):
        return 'on' if value else 'off'
    if isinstance(value, float):
        return f'{value:g}'
    if isinstance(value, str):
        if is_payload(None, value):
            return f'<{len(value)} chars>'
        return value if len(value) <= limit else value[:limit - 3] + '...'
    text = _json(value)
    if len(text) <= limit:
        return text
    if isinstance(value, list):
        return f'{len(value)} items'
    if isinstance(value, dict):
        return f'{len(value)} fields'
    return text[:limit - 3] + '...'


# ── diffs ─────────────────────────────────────────────────────────────────

_PATH_KEYS = ('customPortPaths', 'powerCustomPaths')


def _panels_summary(panels):
    if not isinstance(panels, list):
        return None
    hidden = sum(1 for p in panels if isinstance(p, dict) and p.get('hidden'))
    blank = sum(1 for p in panels if isinstance(p, dict) and p.get('blank'))
    half = sum(1 for p in panels if isinstance(p, dict)
               and p.get('halfTile') not in (None, '', 'none'))
    return {'n': len(panels), 'hidden': hidden, 'blank': blank, 'half': half}


def _paths_summary(paths):
    if not isinstance(paths, dict):
        return None
    out = {}
    for port, entries in paths.items():
        out[str(port)] = len(entries) if isinstance(entries, (list, dict)) else 1
    return out


def freeze(key, value):
    """A copy of `value` that a later state can be compared with. Big
    values keep only what their diff reports (panel counts, cabinets per
    port), so a snapshot of a whole screen stays cheap."""
    if value is MISSING:
        return MISSING
    if key == 'panels':
        s = _panels_summary(value)
        if s is not None:
            return ('panels', s)
    if key in _PATH_KEYS:
        s = _paths_summary(value)
        if s is not None:
            return ('paths', s)
    if isinstance(value, str) and is_payload(key, value):
        return ('payload', len(value), hash(value))
    if isinstance(value, (dict, list)):
        try:
            return _canon(json.loads(json.dumps(value, default=str)))
        except (TypeError, ValueError):
            return repr(value)
    return _canon(value)


def _canon(v):
    """500.0 and 500 are one number: a page sending a whole number as a
    float must not read as a change ("500 to 500")."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    return v


def snapshot(obj, keys):
    """{key: frozen value} of `obj` for `keys`, taken before an edit."""
    obj = obj or {}
    return {k: freeze(k, obj.get(k, MISSING)) for k in keys}


def _panels_text(a, b):
    parts = []
    for name, label in (('n', 'panels'), ('hidden', 'hidden'), ('blank', 'blank'), ('half', 'half tiles')):
        x = (a or {}).get(name, 0)
        y = (b or {}).get(name, 0)
        if x != y:
            parts.append(f'{label} {x} to {y}')
    return ', '.join(parts) or 'panels rebuilt'


def _paths_text(a, b):
    a = a or {}
    b = b or {}
    parts = []
    for port in sorted(set(a) | set(b), key=lambda p: (len(p), p)):
        x, y = a.get(port), b.get(port)
        if x == y:
            continue
        if x is None:
            parts.append(f'port {port} added ({y} cabinets)')
        elif y is None:
            parts.append(f'port {port} removed')
        else:
            parts.append(f'port {port}: {x} to {y} cabinets')
    if len(parts) > 5:
        parts = parts[:5] + [f'{len(parts) - 5} more']
    return '; '.join(parts) or 'paths reordered'


def _plain(v):
    """A frozen value back to something JSON can hold, short."""
    if v is MISSING:
        return None
    if isinstance(v, tuple) and v and v[0] == 'payload':
        return f'<{v[1]} chars>'
    if isinstance(v, str):
        return short(v)
    if isinstance(v, (dict, list)):
        text = _json(v)
        if len(text) <= 120:
            return scrub(v)
        return short(v, 120)
    return v


def _pair_or_text(key, a, b, out, depth):
    if isinstance(a, tuple) and a and a[0] == 'panels' or isinstance(b, tuple) and b and b[0] == 'panels':
        out[key] = _panels_text(a[1] if isinstance(a, tuple) else None,
                                b[1] if isinstance(b, tuple) else None)
        return
    if isinstance(a, tuple) and a and a[0] == 'paths' or isinstance(b, tuple) and b and b[0] == 'paths':
        out[key] = _paths_text(a[1] if isinstance(a, tuple) else None,
                               b[1] if isinstance(b, tuple) else None)
        return
    if depth == 0 and isinstance(a, dict) and isinstance(b, dict):
        sub = {}
        for k in sorted(set(a) | set(b), key=str):
            x, y = a.get(k, MISSING), b.get(k, MISSING)
            if _json(x) != _json(y):
                _pair_or_text(f'{key}.{k}', x, y, sub, depth + 1)
        if len(sub) > 5:
            names = [k.split('.', 1)[1] for k in sub]
            out[key] = f'{len(sub)} fields changed: ' + ', '.join(names[:5]) + ', ...'
        else:
            out.update(sub)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(_json(a)) > 120 or len(_json(b)) > 120:
            out[key] = (f'{len(a)} to {len(b)} items' if len(a) != len(b)
                        else f'{len(a)} items, changed')
            return
    out[key] = [_plain(a), _plain(b)]


def diff(before, after_obj, keys=None):
    """{key: [old, new]} for what changed between a snapshot and the object
    now; a big value gets a short text instead of the pair ("port 4: 12 to
    15 cabinets", "hidden 0 to 2"), a dict names up to five changed fields
    a level down ("stage3d.x": [100, 340]). Keys that did not change are
    left out, so an edit that changed nothing gives {}."""
    after_obj = after_obj or {}
    keys = list(before.keys()) if keys is None else list(keys)
    out = {}
    for k in keys:
        if k.startswith('_'):
            continue
        a = before.get(k, MISSING)
        b = freeze(k, after_obj.get(k, MISSING))
        if a is MISSING and b is MISSING:
            continue
        if a is not MISSING and b is not MISSING and _json(a) == _json(b):
            continue
        _pair_or_text(k, a, b, out, 0)
    return out


def diff_dicts(old, new, keys=None):
    """diff() of two plain dicts (preferences, a canvas before and after)."""
    old = old or {}
    new = new or {}
    keys = sorted(set(old) | set(new), key=str) if keys is None else keys
    return diff(snapshot(old, keys), new, keys)


def merge_diffs(first, last):
    """Two diffs of one gesture as one: each key from where it started to
    where it ended."""
    out = dict(first or {})
    for k, v in (last or {}).items():
        a = out.get(k)
        if isinstance(a, list) and len(a) == 2 and isinstance(v, list) and len(v) == 2:
            out[k] = [a[0], v[1]]
        else:
            out[k] = v
    return out


def diff_text(d, limit=6):
    """"x 100 to 340, y 0 to 20" for a diff."""
    parts = []
    for k, v in list(d.items())[:limit]:
        if isinstance(v, list) and len(v) == 2:
            parts.append(f'{k} {short(v[0], 40)} to {short(v[1], 40)}')
        else:
            parts.append(f'{k}: {short(v, 80)}')
    if len(d) > limit:
        parts.append(f'and {len(d) - limit} more')
    return ', '.join(parts)


# ── area and level ────────────────────────────────────────────────────────

AREAS = ('pixelmap', 'cabinet', 'data', 'power', 'rigging', '3d', 'idm', 'phone', 'pad',
         'output', 'binder', 'export', 'processor', 'fiber', 'distro', 'history', 'sync',
         'file', 'prefs', 'guide', 'render', 'app')
LEVELS = ('debug', 'info', 'warn', 'error')

_AREA_PREFIXES = sorted([
    ('stage3d', '3d'), ('s3d', '3d'), ('idm_phone', 'phone'), ('phone_', 'phone'),
    ('idm_pad', 'pad'), ('native_pad', 'pad'), ('pad_', 'pad'), ('idm', 'idm'),
    ('output', 'output'), ('native_output', 'output'), ('native_dialog', 'file'),
    ('render', 'render'),
    ('socket', 'sync'), ('follow_', 'sync'), ('foreign_', 'sync'), ('layer_put', 'sync'),
    ('sync', 'sync'), ('live_', 'sync'),
    ('restore', 'history'), ('undo', 'history'), ('redo', 'history'), ('save_state', 'history'),
    ('history', 'history'), ('number_hold', 'history'),
    ('export_binder', 'binder'), ('binder', 'binder'), ('export', 'export'), ('save_blob', 'export'),
    ('pull_', 'export'), ('resolume', 'export'), ('obj_', 'export'), ('svg', 'export'),
    ('processor', 'processor'), ('network', 'processor'), ('card', 'processor'),
    ('snake', 'data'), ('dock', 'data'), ('port', 'data'), ('data', 'data'), ('mirror', 'data'),
    ('merge_runs', 'data'), ('custom_', 'data'), ('pattern', 'data'), ('pins', 'data'),
    ('frame_rate', 'data'), ('capacity', 'data'), ('copy_mode', 'data'),
    ('fiber', 'fiber'), ('box_power', 'power'), ('box', 'fiber'), ('tac', 'fiber'), ('cat_snake', 'fiber'),
    ('power', 'power'), ('older_show_power', 'power'), ('circuit', 'power'), ('soca', 'power'),
    ('nfer', 'power'), ('merge_circuits', 'power'), ('override', 'power'), ('phase', 'power'),
    ('neutral', 'power'), ('jumper', 'power'), ('cable', 'power'), ('redraw', 'power'),
    ('distro', 'distro'), ('multi', 'distro'), ('service', 'distro'),
    ('rigging', 'rigging'), ('curve', 'rigging'), ('corner', 'rigging'), ('header', 'rigging'),
    ('footer', 'rigging'), ('bars', 'rigging'), ('bend', 'rigging'),
    ('name_display', 'cabinet'), ('label', 'cabinet'), ('naming', 'cabinet'), ('cabinet', 'cabinet'),
    ('canvas', 'pixelmap'), ('raster', 'pixelmap'), ('layer', 'pixelmap'), ('add_', 'pixelmap'),
    ('update_layer', 'pixelmap'), ('delete_layer', 'pixelmap'), ('duplicate', 'pixelmap'),
    ('paste', 'pixelmap'), ('copy', 'pixelmap'), ('panel', 'pixelmap'), ('toggle_panel', 'pixelmap'),
    ('bulk_set', 'pixelmap'), ('set_panel', 'pixelmap'), ('beach', 'pixelmap'),
    ('group', 'pixelmap'), ('screen', 'pixelmap'), ('select', 'pixelmap'), ('palette', 'pixelmap'),
    ('quick_palette', 'pixelmap'), ('color', 'pixelmap'), ('hue', 'pixelmap'), ('image', 'pixelmap'),
    ('text_layer', 'pixelmap'), ('move', 'pixelmap'),
    ('save_preferences', 'prefs'), ('preferences', 'prefs'), ('get_preferences', 'prefs'),
    ('controls', 'prefs'), ('prefs', 'prefs'),
    ('guide', 'guide'), ('quickstart', 'guide'), ('tour', 'guide'), ('whatsnew', 'guide'),
    ('save_project', 'file'), ('open', 'file'), ('load', 'file'), ('recent', 'file'),
    ('new_project', 'file'), ('project', 'file'), ('get_project', 'file'), ('unsaved', 'file'),
    ('quit', 'file'), ('start_page', 'file'), ('startup', 'file'), ('migration', 'file'),
    ('older_show', 'file'), ('old_show', 'file'), ('save_as', 'file'), ('reload', 'file'),
], key=lambda pair: -len(pair[0]))

# Echo bookkeeping and per-request reads: kept, but at debug (hidden in
# the viewer by default) and folded into one line a second.
_DEBUG_EXACT = {
    'socket_connect', 'socket_project_data', 'socket_project_edited_own',
    'socket_project_replaced_own', 'socket_project_replaced_older',
    'socket_project_edited_older', 'socket_project_edited_waits_for_own',
    'socket_project_edited_held_for_gesture', 'socket_project_replaced_held_for_gesture',
    'socket_layer_updated_held_for_gesture', 'socket_layer_updated_suppressed_older_put',
    'socket_layer_updated_suppressed_same_copy', 'socket_layer_updated_suppressed_gone',
    'socket_project_replaced_own_after_other', 'socket_project_replaced_during_load',
    'get_project', 'get_preferences', 'get_server_session', 'get_preset', 'http_request',
    'save_state', 'save_state_skipped_noop', 'update_layers', 'follow_write_kept_local',
    'layer_save_noop',
}
# Bookkeeping lines folded into one "sync" summary line per page a second.
SYNC_FOLD = {a for a in _DEBUG_EXACT if a.startswith('socket_')} | {'socket_layer_updated_own'}

_ERROR_EXACT = {'client_error', 'unhandled_exception', 'client_unhandled_rejection', 'launcher_crash'}
_ERROR_RE = re.compile(r'(_failed|_error|_crash|_exception)(_|$)')
_WARN_RE = re.compile(r'(_refused|_rejected|_stale_dropped|_mismatch|mismatch_|_dropped|_too_large'
                      r'|_invalid|_not_found|_over_|_over$|_warning|_warn$|_blocked|_clamped'
                      r'|_cannot|_denied|_missing)')


def area_for(action, details=None):
    """The area a line belongs to: an explicit one, else by the event
    name's prefix; a screen edit by the fields it changed."""
    if isinstance(details, dict):
        given = details.get('_area') or details.get('area')
        if isinstance(given, str) and given in AREAS:
            return given
    a = str(action or '')
    if a in ('update_layer', 'layer_edit') and isinstance(details, dict):
        keys = list((details.get('diff') or details.get('changed') or {}).keys())
        return area_for_keys(keys)
    if a in ('ui_change', 'ui_click', 'toast_error', 'client_error', 'client_unhandled_rejection',
             'unhandled_exception', 'api_not_found', 'clear_logs', 'client_log_dropped'):
        return 'app'
    for prefix, area in _AREA_PREFIXES:
        if a.startswith(prefix):
            return area
    return 'app'


_KEY_AREAS = (
    ('stage3d', '3d'), ('idm', 'idm'),
    ('power', 'power'), ('circuit', 'power'), ('breakout', 'power'), ('distro', 'power'),
    ('soca', 'power'), ('jumper', 'power'),
    ('data', 'data'), ('port', 'data'), ('customPort', 'data'), ('processor', 'data'),
    ('flow', 'data'), ('frameRate', 'data'), ('bitDepth', 'data'), ('lowLatency', 'data'),
    ('mirror', 'data'), ('card', 'data'),
    ('rigging', 'rigging'), ('header', 'rigging'), ('footer', 'rigging'), ('curve', 'rigging'),
    ('bars', 'rigging'), ('bend', 'rigging'), ('corner', 'rigging'),
    ('label', 'cabinet'), ('cabinetId', 'cabinet'), ('nameDisplay', 'cabinet'),
)


def area_for_keys(keys):
    """The area of a screen edit, by the first changed field that says."""
    for k in keys or []:
        head = str(k).split('.', 1)[0]
        low = head.lower()
        for prefix, area in _KEY_AREAS:
            if low.startswith(prefix.lower()):
                return area
    return 'pixelmap'


def level_for(action, details=None):
    """error, warn, info or debug for a line."""
    if isinstance(details, dict):
        given = details.get('_lvl')
        if isinstance(given, str) and given in LEVELS:
            return given
        if details.get('level') in LEVELS and details.get('level') != 'info':
            return details.get('level')
    a = str(action or '')
    if a == 'client_error' and isinstance(details, dict) and details.get('opaque'):
        return 'warn'
    if a == 'toast_error':
        return 'warn'
    if a in _ERROR_EXACT or _ERROR_RE.search(a):
        return 'error'
    if _WARN_RE.search(a):
        return 'warn'
    if a in _DEBUG_EXACT:
        return 'debug'
    if a == 'socket_layer_updated' and isinstance(details, dict) and details.get('own'):
        return 'debug'
    return 'info'


# ── messages ─────────────────────────────────────────────────────────────

# Keys a generic message leaves out: they say who wrote the line, not what
# happened.
_QUIET_KEYS = {'page', 'browser', 'path', 'url', 'clientTime', 'steps', 'ms', 'folded', 'from'}

_SYNC_WORDS = {
    'socket_layer_updated_suppressed_same_copy': 'same copy',
    'socket_layer_updated_held_for_gesture': 'held for a gesture',
    'socket_layer_updated_suppressed_older_put': 'older save',
    'socket_layer_updated_suppressed_gone': 'screen gone',
    'socket_layer_updated_own': 'own save taken',
    'socket_project_edited_own': 'own project edit',
    'socket_project_replaced_own': 'own replace',
    'socket_project_edited_older': 'older project edit',
    'socket_project_replaced_older': 'older replace',
    'socket_project_edited_held_for_gesture': 'project edit held for a gesture',
    'socket_project_replaced_held_for_gesture': 'replace held for a gesture',
    'socket_project_edited_waits_for_own': 'waits for own save',
    'socket_project_data': 'project data',
    'socket_connect': 'connected',
}


def _screen(d):
    name = d.get('name') or d.get('layerName')
    lid = d.get('id', d.get('layerId'))
    if name and lid is not None:
        return f'{name} (#{lid})'
    if name:
        return str(name)
    return f'#{lid}' if lid is not None else 'a screen'


def _generic(action, d):
    parts = []
    for k, v in d.items():
        if k in _QUIET_KEYS or k.startswith('_'):
            continue
        parts.append(f'{k}={short(v, 40)}')
        if len(parts) >= 6:
            break
    text = action.replace('_', ' ')
    return f'{text}: ' + ', '.join(parts) if parts else text


def _m_update_layer(d):
    label = d.get('label')
    diff_ = d.get('diff')
    head = f'{label}: ' if label else ''
    if diff_:
        return f'{head}{_screen(d)} {diff_text(diff_)}'
    if diff_ is not None:
        return f'{head}{_screen(d)} saved, nothing changed'
    changed = d.get('changed')
    if isinstance(changed, dict):
        return f'{head}{_screen(d)} saved: ' + ', '.join(list(changed)[:8])
    return f'{head}{_screen(d)} saved'


def _m_ui_change(d):
    v = d.get('value')
    if d.get('type') == 'checkbox':
        return f"Set {d.get('id') or 'a field'} {'on' if v else 'off'}"
    start = d['from'].get('value', MISSING) if isinstance(d.get('from'), dict) else MISSING
    was = f' (from {short(start, 40)})' if start is not MISSING else ''
    return f"Set {d.get('id') or 'a field'} to {short(v, 60)}{was}"


def _m_ui_click(d):
    what = d.get('text') or d.get('id') or d.get('data') or 'a button'
    extra = f" ({d['data']})" if d.get('data') and d.get('data') != what else ''
    return f'Clicked {short(what, 60)}{extra}'


def _m_client_error(d):
    where = ''
    if d.get('filename'):
        where = f" at {str(d['filename']).rsplit('/', 1)[-1]}:{d.get('lineno', '?')}"
    if d.get('opaque'):
        return f"Page error from outside the app: {short(d.get('message'), 120)}"
    return f"Page error: {short(d.get('message'), 160)}{where}"


def _m_unhandled(d):
    return (f"Server error on {d.get('method', '?')} {d.get('path', '?')}: "
            f"{d.get('type', '?')}: {short(d.get('error'), 160)}")


def _m_history(word):
    def fmt(d):
        text = f"{word} {d.get('action') or ''}".strip()
        ch = d.get('changed')
        if isinstance(ch, dict):
            bits = []
            for lay in (ch.get('layers') or [])[:4]:
                keys = ', '.join((lay.get('keys') or [])[:5])
                bits.append(f"{lay.get('name') or '#' + str(lay.get('id'))} ({keys})")
            if ch.get('added'):
                bits.append(f"{len(ch['added'])} screens back")
            if ch.get('removed'):
                bits.append(f"{len(ch['removed'])} screens gone")
            if ch.get('project'):
                bits.append('project ' + ', '.join(ch['project'][:5]))
            if bits:
                text += ': ' + '; '.join(bits)
        return text
    return fmt


def _m_select(d):
    tab = d.get('tab')
    n = len(d.get('selectedLayerIds') or [])
    more = f', {n} selected' if n > 1 else ''
    return f"Selected {_screen(d)}" + (f' ({tab} tab{more})' if tab else '')


def _m_diff_owner(noun, id_key='id'):
    def fmt(d):
        diff_ = d.get('diff')
        who = f"{noun} {d.get('name') or d.get(id_key) or ''}".strip()
        if diff_:
            return f'{who}: {diff_text(diff_)}'
        if diff_ is not None:
            return f'{who} saved, nothing changed'
        return _generic(noun.lower() + ' update', d)
    return fmt


def _m_prefs(d):
    diff_ = d.get('diff')
    if diff_:
        return 'Preferences saved: ' + diff_text(diff_)
    if diff_ is not None:
        return 'Preferences saved, nothing changed'
    return 'Preferences saved'


def _m_sync_fold(d):
    counts = d.get('counts') or {}
    total = sum(counts.values())
    parts = [f'{n} {_SYNC_WORDS.get(a, a)}' for a, n in sorted(counts.items(), key=lambda p: -p[1])]
    return f'sync: {total} echoes settled ({", ".join(parts)})'


def _m_socket_layer(d):
    if d.get('own'):
        return f"sync: own save of #{d.get('id')} taken back"
    return f"Screen #{d.get('id')} changed on another page, taken in"


def _m_toast(d):
    return f"Error shown: {short(d.get('message'), 200)}"


# What an export wrote (2026-11-19 logging audit, phase 2): the lines that
# were here before it, said plainly. The new render and export lines name
# their own message.
def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _m_pull_sheet(d):
    text = f"Pull sheet written: {_plural(d.get('positions') or 0, 'position')}"
    if d.get('rows') is not None:
        text += f", {_plural(d.get('rows'), 'row')}"
    if d.get('bytes') is not None:
        text += f", {d.get('bytes'):,} bytes"
    if d.get('warnings'):
        text += f", {_plural(len(d.get('warnings')), 'warning')}"
    return text


def _m_xml_export(d):
    text = f"Advanced Output XML written: {d.get('raster') or '?'}, {_plural(d.get('layers') or 0, 'screen')}"
    if d.get('slices') is not None:
        text += f", {_plural(d.get('slices'), 'slice')}"
    return text


def _m_svg(d):
    each = d.get('each') or []
    views = sorted({str(e.get('view')) for e in each if isinstance(e, dict) and e.get('view')})
    return (f"SVG export: {_plural(d.get('files') or 0, 'file')}, {(d.get('bytes') or 0):,} bytes"
            + (f" ({', '.join(views)})" if views else ''))


_FORMATTERS = {
    'update_layer': _m_update_layer,
    'layer_save_noop': _m_update_layer,
    'ui_change': _m_ui_change,
    'ui_click': _m_ui_click,
    'client_error': _m_client_error,
    'client_unhandled_rejection': lambda d: f"Unhandled page rejection: {short(d.get('reason'), 160)}",
    'unhandled_exception': _m_unhandled,
    'toast_error': _m_toast,
    'undo': _m_history('Undo'),
    'redo': _m_history('Redo'),
    'save_state': lambda d: f"Undo step: {d.get('action') or '?'}",
    'select_layer': _m_select,
    'canvas_update': _m_diff_owner('Raster'),
    'processor_update': _m_diff_owner('Processor'),
    'processor_card_update': _m_diff_owner('Card'),
    'processor_cvt_update': _m_diff_owner('Breakout box'),
    'snake_update': _m_diff_owner('Snake'),
    'save_preferences': _m_prefs,
    'sync_echoes_folded': _m_sync_fold,
    'socket_layer_updated': _m_socket_layer,
    'export_pull_sheet': _m_pull_sheet,
    'export_resolume': _m_xml_export,
    'export_svg': _m_svg,
}


def register(action, formatter):
    """Give an event kind its own message (formatter(details) -> str)."""
    _FORMATTERS[action] = formatter


def message(action, details):
    """The one plain-English line for an event."""
    d = details if isinstance(details, dict) else {}
    given = d.get('_msg')
    if isinstance(given, str) and given:
        text = given
    else:
        fmt = _FORMATTERS.get(action)
        try:
            text = fmt(d) if fmt else _generic(str(action), d)
        except Exception:
            text = _generic(str(action), d)
    steps = d.get('steps')
    if isinstance(steps, int) and steps > 1:
        secs = (d.get('ms') or 0) / 1000.0
        text += f' ({steps} steps, {secs:.1f} s)'
    return text.replace('—', ' - ').replace('–', ' - ')


# ── folding repeated lines (the log writer's coalescer) ─────────────────

def default_fold_key(action, details, source):
    """The key a line folds under when the caller gave none: a held
    spinner's ui_change ticks, the undo-step and save bookkeeping, and the
    echo bookkeeping a page writes for its own saves. None: never folded."""
    d = details if isinstance(details, dict) else {}
    page = d.get('page') or source
    if action == 'ui_change':
        return f"ui:{page}:{d.get('id')}"
    if action in ('save_state', 'save_state_skipped_noop', 'update_layers',
                  'follow_write_kept_local', 'get_project', 'http_request', 'get_preferences'):
        return f'{action}:{page}'
    if action in SYNC_FOLD or (action == 'socket_layer_updated' and d.get('own')):
        return f'sync:{page}'
    return None


def fold(first_action, first, last_action, last, steps, ms, counts):
    """The summary line of a folded run: (action, details)."""
    if len(counts) > 1 or (first_action in SYNC_FOLD or first_action == 'socket_layer_updated'):
        return 'sync_echoes_folded', {'counts': dict(counts), 'steps': steps, 'ms': ms,
                                      'page': (last or {}).get('page'), 'folded': True}
    merged = dict(last or {})
    if isinstance((first or {}).get('diff'), dict) or isinstance(merged.get('diff'), dict):
        merged['diff'] = merge_diffs((first or {}).get('diff'), merged.get('diff'))
    else:
        start = {}
        for k, v in (first or {}).items():
            if k in _QUIET_KEYS or k.startswith('_'):
                continue
            if not isinstance(v, (dict, list)) and merged.get(k) != v:
                start[k] = v
        if start:
            merged['from'] = start
    merged['steps'] = steps
    merged['ms'] = ms
    merged['folded'] = True
    return last_action, merged


# ── the viewer: older lines, filters, redaction ─────────────────────────

def normalize(entry):
    """A parsed log line with lvl, area and msg filled in when an older
    line has none. Returns the same dict, changed in place."""
    if not isinstance(entry, dict):
        return entry
    action = entry.get('action', '')
    details = entry.get('details')
    if 'lvl' not in entry:
        entry['lvl'] = level_for(action, details)
    if 'area' not in entry:
        entry['area'] = area_for(action, details)
    if 'msg' not in entry:
        entry['msg'] = message(action, details)
    return entry


_ID_KEYS = ('id', 'layerId', 'layer_id', 'layer', 'source', 'screenId')
_IDS_KEYS = ('ids', 'layerIds', 'layer_ids', 'selectedLayerIds', 'mirrors', 'screens')


def mentions_layer(entry, layer_id):
    """True when a line is about screen `layer_id`."""
    d = entry.get('details') if isinstance(entry, dict) else None
    if not isinstance(d, dict):
        return False
    want = str(layer_id)
    for k in _ID_KEYS:
        if k in d and str(d.get(k)) == want and not (k == 'id' and entry.get('area') in (
                'processor', 'fiber', 'distro')):
            return True
    for k in _IDS_KEYS:
        v = d.get(k)
        if isinstance(v, list) and any(str(x) == want for x in v):
            return True
    return False


_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
# (555) 123-4567, 555-123-4567, 555.123.4567, +1 555 123 4567, and an
# international +44 20 7946 0958. Never a date (2026-11-18) or a size.
_PHONE_RE = re.compile(
    r'(?<![\w.:/-])(?:'
    r'(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}'
    r'|\+\d{1,3}(?:[ .-]\d{1,4}){2,5}'
    r')(?![\w.:/-])')
_IPV4_RE = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
_USER_PATH_RES = (
    (re.compile(r'([A-Za-z]:[\\/]+Users[\\/]+)[^\\/"]+', re.I), r'\1<user>'),
    (re.compile(r'(/Users/)[^/"]+'), r'\1<user>'),
    (re.compile(r'(/home/)[^/"]+'), r'\1<user>'),
)
_PERSONAL_KEY_RE = re.compile(r'(projectmanager|binderpm|email|phone|contact)', re.I)


def redact_text(text):
    """A log line made safe to paste into a public bug report: emails,
    phone numbers, network addresses and the user name in file paths are
    masked."""
    s = str(text)
    for rx, rep in _USER_PATH_RES:
        s = rx.sub(rep, s)
    s = _EMAIL_RE.sub('<email>', s)
    s = _IPV4_RE.sub('<ip>', s)
    s = _PHONE_RE.sub('<phone>', s)
    return s


def redact(value, key=None, depth=0):
    """redact_text over a parsed line; a field that names a person's
    contact (projectManager, email, phone) is hidden whole."""
    if key is not None and _PERSONAL_KEY_RE.search(str(key)) and value not in (None, '', False):
        if isinstance(value, (str, int, float)):
            return '[hidden]'
    if isinstance(value, str):
        return redact_text(value)
    if depth > 8:
        return value
    if isinstance(value, dict):
        out = {k: redact(v, k, depth + 1) for k, v in value.items()}
        # A field's value logged by its id (ui_change): the binder's
        # project manager phone and email fields.
        fid = value.get('id')
        if isinstance(fid, str) and _PERSONAL_KEY_RE.search(fid.replace('-', '')) \
                and out.get('value') not in (None, '', False):
            out['value'] = '[hidden]'
        return out
    if isinstance(value, list):
        return [redact(v, key, depth + 1) for v in value]
    return value
