"""
Project + server-session routes (get / new / save / restore project).

Thin controllers over the project model, which stays in app: current_project and
the model helpers (_build_initial_project, initialize_default_layer, migrations,
sync_next_layer_id) live there. new_project / restore_project REASSIGN the
project, so this blueprint sets it through the app module attribute
(app.current_project = ...) — that keeps app.py's readers and the tests in sync.
"""
import json
import re
import threading
import time

from flask import Blueprint, request, jsonify

import app
import port_assignment
import processor_catalog
from app import log_event, socketio
from updater import get_current_version

project_bp = Blueprint('project', __name__)


def _stamp_app_version(project):
    """The build that last wrote this project. Written on every save (POST)
    and on a new project, never on a load (PUT): a file saved before the
    stamp existed carries none, and that absence is what tells the client
    the file predates a migration (app-naming normalizePowerCircuitColors
    reads it). The client writes the same key into the file it saves, and
    stamps a project it has just opened - after its migrations, before the
    load PUT - so the copy this route stores is that build's from then on;
    a stamp the PUT carries is kept as it came (2026-09-23)."""
    project['app_version'] = get_current_version()


def _fold_fiber_stock(project):
    """A show saved with a fiber list per mode goes on the one fiber list
    (owner, 2026-11-05; routes_cable_stock.fold_fiber_lists), so the copy
    the session edits and every save after it never carry the old keys.
    Logged once: the pass is idempotent."""
    import routes_cable_stock
    if routes_cable_stock.fold_fiber_lists(project.get('cableStock')):
        log_event('cable_stock_fiber_lists_merged', {'name': project.get('name')})


# ── Unsaved changes across a reload (1.6.0) ──
#
# The page reads "unsaved" off its undo history, and a reload starts a new
# history from the project as the server holds it: edits made before the
# reload read as saved, and New, Open or a Recent file then dropped them
# without asking. The page tells the server whenever the answer changes
# (POST /api/project/unsaved) and reads it back with the project (the
# X-Project-Unsaved header on GET /api/project). It lives here, beside the
# project and never in it, so no file or undo snapshot carries it. A new
# project starts saved; a show opened, or a project saved to a file, is
# marked saved by the page that did it; a server restart starts saved with
# the fresh project it builds.
_unsaved = {'value': False}


def project_unsaved():
    return _unsaved['value']


def set_project_unsaved(value):
    _unsaved['value'] = bool(value)


@project_bp.route('/api/project', methods=['GET'])
def get_project():
    log_event('get_project')
    # Every write route keeps this invariant already, so this pass writes
    # nothing on a healthy project; when it does write, the log names the
    # entry point that was missed (2026-09-22: a GET never hands back a
    # screen without a breakout its voltage allows).
    app.normalize_power_breakouts(app.current_project, at='get_project')
    rev = project_rev()   # before the project is read (project_rev)
    response = jsonify(app.current_project)
    response.headers['X-Project-Unsaved'] = '1' if project_unsaved() else '0'
    response.headers['X-Project-Rev'] = str(rev)
    return response


@project_bp.route('/api/project/unsaved', methods=['POST'])
def post_project_unsaved():
    data = request.get_json(silent=True) or {}
    value = data.get('unsaved') is True
    if value != project_unsaved():
        log_event('project_unsaved_changed', {'unsaved': value})
    set_project_unsaved(value)
    return jsonify({'unsaved': value})


@project_bp.route('/api/server-session', methods=['GET'])
def get_server_session():
    """Return unique session ID that changes on server restart"""
    log_event('get_server_session', {'session_id': app.SERVER_SESSION_ID})
    return jsonify({
        'session_id': app.SERVER_SESSION_ID,
        'start_time': app.SERVER_START_TIME
    })


# ── The launch's start page, once per server run (owner, 2026-11-09) ──
#
# "It should only do that on the app originally opening. Treated like a
# live service once it is already running." The start page (and the
# launch's panel picker) is for the app's own first page after the server
# starts. Every later page, another tab, another browser on this computer,
# or a tablet at the computer's address, joins the show as it stands.
#
# The server decides, because only it sees every page. Each page boots
# with an id of its own and asks once (POST /api/launch/claim) before its
# project loads. The first page on THIS computer to ask is the launch page
# (the desktop window opens it, and a person who opens the app in a
# browser first is that page too). A page from another machine never is:
# the start page's Open file and Recent read files on the host, and the
# person at the host is the one launching. The lock makes two pages
# loading at once get one start page between them.
#
# The question stays open until somebody answers it: the launch page's X,
# a pick or Cancel in the startup picker, File > New, or a show opened on
# any page (POST /api/launch/settle). From then on nobody gets the start
# page this run, and a page load no longer puts a startup screen in an
# emptied project (app.index), so a joining page sees that project empty.
#
# While it is open, the launch page keeps it across its own reload: the
# page notes its id with its reload record (app-start-page.js
# _saveReloadPlace) and the reload hands the claim on to its new id. A
# launch page closed with the question open gives it up once its socket
# has been gone LAUNCH_GONE_SECONDS: the next page on this computer to
# load is the launch page then, over the startup project as it was. If
# somebody worked on the show meanwhile it is a live show, and the
# question is closed instead.
LAUNCH_GONE_SECONDS = 5.0

_launch_lock = threading.Lock()
_launch = {}


def reset_launch_state():
    """A fresh server run: nobody has had the start page yet, and no guide
    is running."""
    with _launch_lock:
        _launch.clear()
        _launch.update({
            'owner': None,        # the launch page's id
            'seen': 0.0,          # when it last claimed or lost its last socket
            'settled': False,     # the launch's question has been answered
            'sockets': {},        # page id -> live socket ids
            'guide': None,        # the page running a guide (guide_page)
        })


reset_launch_state()


def launch_settled():
    with _launch_lock:
        return _launch['settled'] is True


def _launch_owner_live(now):
    owner = _launch['owner']
    if owner is None:
        return False
    if _launch['sockets'].get(owner):
        return True
    return now - _launch['seen'] < LAUNCH_GONE_SECONDS


def launch_socket_connected(page, sid):
    """socket connect: a page is up (its query names its id)."""
    if not page or not sid:
        return
    with _launch_lock:
        back = page == _launch['guide'] and not _launch['sockets'].get(page)
        _launch['sockets'].setdefault(page, set()).add(sid)
    if back:
        # the guide's page reconnected: its guide holds the show again
        _emit_guide_state()


def launch_socket_gone(sid):
    """socket disconnect: a page closed, reloaded or lost the network."""
    if not sid:
        return
    guide_gone = False
    with _launch_lock:
        for page, sids in list(_launch['sockets'].items()):
            if sid in sids:
                sids.discard(sid)
                if not sids:
                    del _launch['sockets'][page]
                    if page == _launch['owner']:
                        _launch['seen'] = time.time()
                    if page == _launch['guide']:
                        guide_gone = True
    if guide_gone:
        log_event('guide_lock_page_gone')
        _emit_guide_state()


# ── One guide at a time, for every page (2026-11-10) ──
#
# A guide runs on a demo show of its own: it stores it on the server, works
# on it step by step and puts the person's project back when it ends. Every
# other page follows it onto the demo (app-core _onProjectReplaced) and says
# so. Until now nothing stopped another page from opening a show, making a
# new one, or undoing meanwhile: the guide's later saves landed in that
# show, and its end put the pre-guide project back over it. The lock lived
# in one browser's storage, so a tablet or another browser never saw it.
#
# Now the server knows. A guide's demo show (PUT /api/project?reason=guide)
# makes its page the guide's page; while that page's socket is up, a show
# change from any other page is refused with GUIDE_REFUSAL (409, the
# X-LRD-Guide header says why), and the page puts the server's show back
# (app-core _guideRefused). That covers a screen's own edit as well as a
# whole-project replace: the guide's steps read the demo as they built it,
# and a guide never fails. Its end (reason=guide_end), or the page leaving
# the guide another way (an open, a New, an undo of its own), lets go. A
# page that closes, reloads or dies mid-guide lets go with its socket (the
# same presence the launch page is known by), so the next page, or the
# guide page's own reload putting the person's project back, goes ahead.
# A request with no page (a script, a test) is never refused.
GUIDE_REFUSAL = 'A guide is running in another window. Finish it there first.'

# The show's writes: anything else (the log, Preferences, the panel
# library, an export, the unsaved flag, the 3D camera) is not the show.
_SHOW_WRITE = re.compile(r'^/api/(project|layer|canvas|processors|port-assignments|beaches)(/|$)')
_NOT_SHOW_WRITES = ('/api/project/unsaved', '/api/project/stage3d',
                    '/api/port-assignments/resolve', '/api/port-assignments/link-check')


def guide_page():
    """The page whose guide holds the show, while its socket is up."""
    with _launch_lock:
        page = _launch['guide']
        return page if page and _launch['sockets'].get(page) else None


def _emit_guide_state():
    """Every page: which page's guide holds the show now (None: none)."""
    socketio.emit('guide_state', {'page': guide_page()})


def _guide_took_the_show(page, reason):
    """After a whole-project replace stored: the lock follows it."""
    changed = False
    with _launch_lock:
        holder = _launch['guide']
        if reason == 'guide' and page:
            changed = holder != page
            _launch['guide'] = page
        elif holder and (reason == 'guide_end'
                         or (page and page == holder and reason in ('open', 'new'))):
            # the guide ended, or its page left it for another show
            _launch['guide'] = None
            changed = True
    if changed:
        log_event('guide_lock', {'page': page or None, 'reason': reason})
        _emit_guide_state()


@project_bp.route('/api/guide', methods=['GET'])
def get_guide():
    """Which page's guide holds the show (None: no guide is running). A
    page with a guide's stash to put back asks before it does
    (quickstart.js recoverStash)."""
    return jsonify({'page': guide_page()})


def is_show_write(path, method):
    if method in ('GET', 'HEAD', 'OPTIONS'):
        return False
    return bool(_SHOW_WRITE.match(path or '')) and path not in _NOT_SHOW_WRITES


@project_bp.before_app_request
def _refuse_while_a_guide_runs_elsewhere():
    if not is_show_write(request.path, request.method):
        return None
    page = request.headers.get('X-LRD-Page')
    if not page:
        return None
    holder = guide_page()
    if holder is None or holder == page[:64]:
        return None
    log_event('guide_lock_refused', {'method': request.method, 'path': request.path,
                                     'reason': request.args.get('reason')})
    response = jsonify({'error': GUIDE_REFUSAL, 'guideRunning': True})
    response.status_code = 409
    response.headers['X-LRD-Guide'] = 'running'
    return response


def _claim_launch(page, prior, remote_addr):
    """(start_page, why) for a page asking at boot. `prior` lists the ids
    this tab's reload record names (the page before it, and the one before
    that when it went before its own claim was answered)."""
    from routes_dialog import _is_same_machine
    now = time.time()
    with _launch_lock:
        if _launch['settled']:
            return False, 'settled'
        owner = _launch['owner']
        if owner is not None and owner in (prior or ()):
            _launch['owner'], _launch['seen'] = page, now
            return True, 'reload'
        if owner == page:
            return True, 'again'
        if not _is_same_machine(remote_addr or ''):
            return False, 'remote'
        if owner is None:
            _launch['owner'], _launch['seen'] = page, now
            return True, 'first'
        if _launch_owner_live(now):
            return False, 'joined'
        # The launch page went without an answer. Over the startup project
        # this page takes its place; over a show somebody worked on, the
        # app is running and the question is closed.
        if app.current_project.get('is_pristine') is not True:
            _launch['settled'] = True
            return False, 'moved_on'
        _launch['owner'], _launch['seen'] = page, now
        return True, 'took_over'


@project_bp.route('/api/launch/claim', methods=['POST'])
def post_launch_claim():
    data = request.get_json(silent=True) or {}
    page = data.get('page') if isinstance(data.get('page'), str) else ''
    prior = data.get('prior')
    if isinstance(prior, str):
        prior = [prior]
    prior = [p[:64] for p in prior[:4] if isinstance(p, str) and p] if isinstance(prior, list) else []
    if not page:
        return jsonify({'startPage': False, 'why': 'no_page'}), 400
    start, why = _claim_launch(page[:64], prior, request.remote_addr)
    log_event('launch_claim', {'startPage': start, 'why': why, 'remote_addr': request.remote_addr})
    return jsonify({'startPage': start, 'why': why})


@project_bp.route('/api/launch/settle', methods=['POST'])
def post_launch_settle():
    data = request.get_json(silent=True) or {}
    why = data.get('why') if isinstance(data.get('why'), str) else None
    with _launch_lock:
        was = _launch['settled']
        _launch['settled'] = True
    if not was:
        log_event('launch_settled', {'why': why, 'remote_addr': request.remote_addr})
    return jsonify({'settled': True})


# ── A whole project replaced, told to every page (2026-11-09) ──
#
# The app runs as a live service: every tab, browser and tablet on it shows
# the one show the server holds. A screen's edit reaches the other pages as
# its layer_updated echo. A show opened, File > New, an undo or a redo, a
# group change and a guide's demo show (and its end) replace the WHOLE
# project, and the pages follow that through `project_updated` carrying
# `_replace`: why it was replaced (`reason`), the page whose request did
# it (`client`, the X-LRD-Page header every page's own requests carry,
# app-core.js), that page's number for the request (`token`), and the
# server's "unsaved" answer at that moment. The page that asked already
# holds the project and lets its own echo go (app-core
# _onProjectReplaced). A request with no page (a script, a test) is every
# page's news.
REPLACE_REASONS = ('open', 'new', 'undo', 'redo', 'group', 'guide', 'guide_end', 'restore')


def _replace_marker(default):
    reason = request.args.get('reason')
    if reason not in REPLACE_REASONS:
        reason = default
    client = request.headers.get('X-LRD-Page')
    client = client[:64] if isinstance(client, str) else ''
    try:
        token = int(request.args.get('token'))
    except (TypeError, ValueError):
        token = None
    return {'reason': reason, 'client': client, 'token': token}


_rev_lock = threading.Lock()
_rev = {'n': 0}


def project_rev():
    """How many times the pages have been sent the whole project. GET
    /api/project says it (X-Project-Rev), read before the project is, so a
    page can tell a message its own read already holds from a newer one
    (app-core _onProjectEdited)."""
    return _rev['n']


def _emit_project_replaced(marker):
    # Numbered and copied in one step, so a higher number never carries an
    # older project, whichever request thread's message goes out first.
    with _rev_lock:
        _rev['n'] += 1
        payload = dict(app.current_project, _rev=_rev['n'], _replace=dict(
            marker, unsaved=project_unsaved()))
        try:
            payload = json.loads(json.dumps(payload))
        except (TypeError, ValueError):
            pass
    socketio.emit('project_updated', payload)


# ── Any other change to the show, told to every page (2026-11-10) ──
#
# A screen added, deleted, duplicated or pasted, a processor, a canvas, the
# port map, a beach, and everything that rides POST /api/project (the
# Screens list's order, the distros and services, the binder, the pull
# sheet, the cable stock, the raster a New gives its show) change the show
# without replacing it. The routes restated the project through the same
# message with no mark, and every page dropped it: the other pages never
# saw the change until they reloaded. Now it carries `_replace` with reason
# 'edit' and the page that made it, and every other page takes it in as
# the same show (app-core _onProjectEdited). The page that made it already
# holds it.
def emit_project_edited():
    page = ''
    try:
        page = request.headers.get('X-LRD-Page') or ''
    except RuntimeError:
        page = ''   # outside a request: every page's news
    _emit_project_replaced({'reason': 'edit', 'client': page[:64], 'token': None})


@project_bp.route('/api/project/new', methods=['POST'])
def new_project():
    app.next_layer_id = 1  # Reset counter for new project
    app.current_project = app._build_initial_project()
    # A new show starts in the Preferences' cable unit (2026-10-16); its
    # screens read the jumper lengths of that unit from the Preferences. A
    # file saved before the setting has no key and reads as feet; only a
    # NEW show is written one here.
    app.current_project['cableUnit'] = app.preferred_cable_unit()
    # And with the cable stock of the preset the Preferences name as the
    # default (2026-10-20, routes_cable_stock.py), when one is set and still
    # saved. None set: the show has no stock and writes lengths as typed.
    import routes_cable_stock
    stock = routes_cable_stock.default_stock(app.server_preferences)
    if stock is not None:
        app.current_project['cableStock'] = stock
    # Add default layer to new projects
    app.initialize_default_layer()
    _stamp_app_version(app.current_project)
    set_project_unsaved(False)
    log_event('new_project')
    socketio.emit('project_cleared')
    marker = _replace_marker('new')
    _emit_project_replaced(marker)
    _guide_took_the_show(marker['client'], marker['reason'])
    return jsonify(app.current_project)


@project_bp.route('/api/project', methods=['POST'])
def save_project():
    data = dict(request.json or {})
    # The client's own raster sync on every page load of the pristine
    # startup project comes through here too (app-client-props
    # loadClientSideProperties, and createNewProject's twin). Until
    # 2026-09-22 that POST cleared is_pristine, so the startup screen
    # followed the Preferences dialog's Save only inside the session that
    # made it, never after a relaunch. That sync says so with
    # `keep_pristine: true`; it is a request marker, never stored. A user
    # save, a sidebar reorder - any other POST - clears the flag as before.
    # Read the way PUT /api/layer/<id> reads ?edited: only true / 1 / yes
    # keep the flag. bool() took the string 'false' as true (2026-09-23).
    keep_pristine = str(data.pop('keep_pristine', False)).lower() in ('1', 'true', 'yes')
    # What the show was, so the other pages hear of a real change only
    # (emit_project_edited below): every page's load re-sends a raster the
    # show already has.
    before = _show_text(app.current_project)
    # The IDM Locator's live highlight is written by its socket event alone
    # (app.handle_idm_highlight): a save carries whatever copy that client
    # last had, which another client may have moved on since.
    data.pop('idmHighlight', None)
    # Slice 6: source-of-truth for raster lives on the active canvas. If the
    # client sent root-level raster_* fields without a canvases payload
    # (backwards-compat clients / older tests), propagate those into the
    # active canvas so the canvas object reflects the new values. Then
    # re-mirror canvas → root so root stays consistent.
    canvases = app.current_project.get('canvases') or []
    if canvases and not data.get('canvases'):
        active_id = app.current_project.get('active_canvas_id')
        active = next(
            (c for c in canvases if isinstance(c, dict) and c.get('id') == active_id),
            canvases[0],
        )
        for key in (
            'raster_width', 'raster_height',
            'show_raster_width', 'show_raster_height',
            'data_flow_perspective', 'power_perspective',
        ):
            if key in data and data[key] is not None:
                active[key] = data[key]
    app.current_project.update(data)
    if not keep_pristine:
        app.current_project['is_pristine'] = False
    _stamp_app_version(app.current_project)
    app._mirror_active_canvas_to_root(app.current_project)
    # v0.11.0: the same repair PUT has always run. This route is not just
    # "save as" - every sidebar reorder comes through it with the whole layers
    # array - and without the pass it would happily store two groups both
    # called g1, a group naming a layer that does not exist, or a groups array
    # with no group_id mirror written back onto the layers. Whatever bad shape
    # it stored then survived until the next undo, and the export read it in
    # the meantime. Idempotent, so a well-formed save is untouched.
    app._enforce_group_integrity(app.current_project)
    # Beaches ride this route too (the distro tray's fire-and-forget POST
    # carries `distros`): repair the list and migrate a typed location.
    app._normalize_beaches(app.current_project)
    # So do the services (the same push carries `services` once a show has
    # one): unique ids, and no distro left on a service that is gone.
    app._normalize_services(app.current_project)
    # A stock saved with the list per mode rides this route too.
    _fold_fiber_stock(app.current_project)
    # Same funnel duty for the processor tree: a payload can carry a
    # pre-stocking SX40 through this route too, and a boxless one is a
    # legacy shape, never a choice. Idempotent like the pass above it.
    # The seq sync runs FIRST so the heal's boxes mint above every id the
    # payload already holds.
    processor_catalog.sync_next_processor_seq(app.current_project)
    processor_catalog.stock_default_cvts(app.current_project)
    # An SQ200 saved as a one-box unit (before 2026-09-28) gets its two
    # empty OUT slots; logged, once - the pass is idempotent.
    for proc_id in processor_catalog.reslot_chassis_units(app.current_project):
        log_event('processor_reslotted', {'processorId': proc_id})
    # A one-box unit has ONE name slot (2026-09-24); a name a 1.3 file left
    # on its fixed card moves up to the unit here, once, and is logged.
    for moved in processor_catalog.adopt_fixed_card_names(app.current_project):
        log_event('processor_name_adopted_from_card', moved)
    # A card mode saved under its old id opens as the mode it names now:
    # an H_4xfiber's combined copy-backup is Backup, the enhanced card's
    # one "default" mode is Backup (NovaStar's modes, 2026-10-30). Logged,
    # once - the pass is idempotent.
    for moved in processor_catalog.migrate_card_modes(app.current_project):
        log_event('processor_card_mode_migrated', moved)
    # Snakes moved to the SHOW (2026-09-09: "Any sockets, any device"), so a
    # file - or an undo snapshot - that carries them per card or per box is
    # folded into project['snakes'] here, and every member is re-homed onto
    # the device that delivers its socket. Idempotent: a project already in
    # the new shape passes through untouched.
    processor_catalog.migrate_device_snakes(app.current_project)
    # Backup processors (2026-09-25): a chassis mirrored card for card by
    # one same-model unit reads as that Backup processor, a 1.4.0 beta
    # file's loop links move onto the loop's far box, and every backup
    # follows its main's redundancy. Before the fiber settle, which would
    # otherwise drop the links the move keeps. Idempotent.
    processor_catalog.migrate_backup_processors(app.current_project)
    # The bar's remembered Mixed pick held to its one shape (True, with
    # redundancy on, on a chassis that can mix). Idempotent.
    processor_catalog.settle_redundancy_mixed(app.current_project)
    # The fiber store held to its rules the same way (links that no longer
    # hold, a 1.4.0 opticalCON's ownerBoxId) - never a cable pruned for
    # being unused here: a restore is what it restores.
    processor_catalog.settle_fiber(app.current_project)
    # Same funnel duty for port attachment: see restore_project below.
    if port_assignment.retire_auto(app.current_project):
        log_event('port_assignment_auto_retired', {'at': 'save_project'})
    app.sync_next_layer_id()
    # A whole-layers payload can carry a screen with no breakout, or one its
    # voltage no longer allows: it lands eligible (2026-09-22).
    app.normalize_power_breakouts(app.current_project)
    # The 3D placement on every screen held to its shape (joint bends within
    # +/-20 degrees). Idempotent; see app.sanitize_stage3d.
    app.normalize_stage3d(app.current_project)
    # The IDM Locator's marks held to the screens as they stand (no mark on
    # a blanked cabinet or a module that is not there). Idempotent.
    app.normalize_idm(app.current_project)
    # The IDM Locator's field colour and border style held to their shape.
    app.normalize_idm_field(app.current_project)
    # ... and its stored highlight to a module the screens still have.
    app.normalize_idm_highlight(app.current_project)
    log_event('save_project', {'name': app.current_project.get('name')})
    if before is None or _show_text(app.current_project) != before:
        emit_project_edited()
    return jsonify({'status': 'success'})


def _show_text(project):
    """The show as text, for telling a change from none (is_pristine is the
    server's own bookkeeping, not the show)."""
    try:
        return json.dumps({k: v for k, v in project.items() if k != 'is_pristine'},
                          sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None


@project_bp.route('/api/project', methods=['PUT'])
def restore_project():
    """Restore entire project state (used by undo/redo and file load)"""
    data = request.json or {}
    # Refuse to load projects authored by a newer app version. Simple string
    # comparison is fine for the foreseeable "0.x" range; revisit if we ever
    # ship a 0.10 / 1.0.
    incoming_version = data.get('format_version') if isinstance(data, dict) else None
    if incoming_version and incoming_version > app.CURRENT_FORMAT_VERSION:
        return jsonify({
            'error': (
                f'Project format {incoming_version} is newer than this '
                f'version supports ({app.CURRENT_FORMAT_VERSION}). '
                f'Please update the app.'
            )
        }), 400
    # `keep_pristine`: the guide's exit (and its recovery after a reload)
    # puts the user's own project back through this route - the world as
    # it was before the guide touched anything. When that snapshot is still
    # pristine the client says so, and the snapshot's flag is what the
    # project ends on (the guide's own adds and edits had cleared the
    # server's copy meanwhile). A request marker, never stored. Undo, redo
    # and a file load never send it: any other PUT clears the flag as
    # before (2026-09-23).
    # Read the way save_project and PUT /api/layer/<id> read their markers.
    keep_pristine = (isinstance(data, dict)
                     and str(data.pop('keep_pristine', False)).lower() in ('1', 'true', 'yes'))
    # `release_screens_ports`: Delete Group commits through this route (the
    # whole project, members already gone), and a deleted screen's sockets
    # forget their port cables exactly as a released port does (owner,
    # 2026-10-17). The pins the body still names for those screens are read
    # here, before the integrity pass below prunes them, and compared after
    # it. A request marker, never stored: undo, redo and a file load never
    # send it, so they restore exactly what they carry.
    release_ports = (isinstance(data, dict)
                     and str(data.pop('release_screens_ports', False)).lower() in ('1', 'true', 'yes'))
    pins_before = port_assignment.pins_of(data) if release_ports else None
    app.current_project = data
    app.current_project['is_pristine'] = bool(keep_pristine and data.get('is_pristine') is True)
    # Backfill showOffsetX/Y on layers from older projects that pre-date the
    # Show Look feature, default them to the layer's processor offset so
    # existing projects open with the show layout = pixel layout.
    for layer in app.current_project.get('layers', []):
        if layer.get('showOffsetX') is None:
            layer['showOffsetX'] = layer.get('offset_x', 0)
        if layer.get('showOffsetY') is None:
            layer['showOffsetY'] = layer.get('offset_y', 0)
    # Backfill the Show Look raster size to match the processor raster for
    # projects saved before the Show Look feature.
    if app.current_project.get('show_raster_width') is None:
        app.current_project['show_raster_width'] = app.current_project.get('raster_width', 1920)
    if app.current_project.get('show_raster_height') is None:
        app.current_project['show_raster_height'] = app.current_project.get('raster_height', 1080)
    # Wiring perspective defaults: older projects render front-facing,
    # matching how they appeared before the perspective toggle existed.
    if app.current_project.get('data_flow_perspective') not in ('front', 'back'):
        app.current_project['data_flow_perspective'] = 'front'
    if app.current_project.get('power_perspective') not in ('front', 'back'):
        app.current_project['power_perspective'] = 'front'
    # The NAMES switch is per tab since 2026-10-01 and per group since
    # 2026-11-04: a file carrying the one project-wide groupNameDisplay
    # starts every tab on it, and every group on its tabs' values.
    # Idempotent.
    app._migrate_group_name_display(app.current_project)
    # Multi-canvas migration. Additive: leaves root-level raster fields in
    # place so the existing single-canvas client keeps working. Slice 6 will
    # switch the source-of-truth to per-canvas fields.
    migrated, did_migrate = app._migrate_to_v0_8(app.current_project)
    app.current_project = migrated
    if did_migrate:
        log_event('project_migrated', {
            'from_version': '<0.8',
            'to_version': app.CURRENT_FORMAT_VERSION,
        })
    # v0.10.8.1: re-derive panel geometry from the per-panel states the client
    # sent, rather than trusting the x/y/width/height it sent alongside them.
    # Half-tiles resize the whole screen (a fully-half row collapses to half
    # height and everything below reflows), and that math only exists here. A
    # client that mutates panel states without a round-trip - as the bulk
    # half-tile path did before v0.10.8 - would otherwise write flags that
    # disagree with the geometry, and restore_project would store that as
    # truth. _build_panels derives every panel field from (columns, rows,
    # offsets, cabinet size, states), so this is a no-op when the incoming
    # geometry already agrees, and self-heals it when it does not.
    # A missing 'type' means screen everywhere else in the app (see app.py's
    # _seed_data_with_canvas_defaults), so legacy type-less layers get rebuilt
    # - and migrated - too.
    for layer in app.current_project.get('layers', []):
        if (layer.get('type') or 'screen') == 'screen':
            app._rebuild_layer_geometry_from_panel_states(layer)
    # v0.11.0: same reasoning as the geometry rebuild above, for the screen
    # group model. Membership lives on two sides (project['groups'][n]
    # ['layer_ids'] and layer['group_id']) and the client can hand back a
    # payload where they disagree - a layer deleted while its group still
    # lists it, an undo snapshot taken mid-edit, a hand-edited file. This is
    # the funnel every undo/redo and file load passes through, so it is the
    # one place that can guarantee the two sides agree. Idempotent by design:
    # restoring the same project twice must not change it.
    app._enforce_group_integrity(app.current_project)
    # Beaches (2026-09-08): the list is repaired and a distro's or box's
    # typed `location` becomes a beach of that name on load - see
    # _normalize_beaches. Idempotent like the pass above it.
    app._normalize_beaches(app.current_project)
    # Services (2026-10-20): the same repair the save route runs - see
    # _normalize_services. A file with no services is left as it came.
    app._normalize_services(app.current_project)
    # A show saved with a fiber list per mode opens on the one list.
    _fold_fiber_stock(app.current_project)
    # A requires-distribution device saved before new_processor stocked its
    # default boxes arrives with an empty cvts list - a pre-stocking save,
    # not an arrangement. This funnel (file load, undo/redo) is where it is
    # healed, because a read must not mutate and the panel may never open.
    # Before it runs, re-seed the processor id counter: an undo snapshot can
    # carry a stale counter or none at all (snapshots taken before the routes
    # echoed it, hand-edited files), and _next_seq falling back would mint a
    # duplicate proc/card/cvt id - the resurrection sync_next_group_seq
    # exists for.
    processor_catalog.sync_next_processor_seq(app.current_project)
    processor_catalog.stock_default_cvts(app.current_project)
    # An SQ200 saved as a one-box unit (before 2026-09-28) gets its two
    # empty OUT slots; logged, once - the pass is idempotent.
    for proc_id in processor_catalog.reslot_chassis_units(app.current_project):
        log_event('processor_reslotted', {'processorId': proc_id})
    # A one-box unit has ONE name slot (2026-09-24); a name a 1.3 file left
    # on its fixed card moves up to the unit here, once, and is logged.
    for moved in processor_catalog.adopt_fixed_card_names(app.current_project):
        log_event('processor_name_adopted_from_card', moved)
    # A card mode saved under its old id opens as the mode it names now:
    # an H_4xfiber's combined copy-backup is Backup, the enhanced card's
    # one "default" mode is Backup (NovaStar's modes, 2026-10-30). Logged,
    # once - the pass is idempotent.
    for moved in processor_catalog.migrate_card_modes(app.current_project):
        log_event('processor_card_mode_migrated', moved)
    # Snakes moved to the SHOW (2026-09-09: "Any sockets, any device"), so a
    # file - or an undo snapshot - that carries them per card or per box is
    # folded into project['snakes'] here, and every member is re-homed onto
    # the device that delivers its socket. Idempotent: a project already in
    # the new shape passes through untouched.
    processor_catalog.migrate_device_snakes(app.current_project)
    # Backup processors (2026-09-25): a chassis mirrored card for card by
    # one same-model unit reads as that Backup processor, a 1.4.0 beta
    # file's loop links move onto the loop's far box, and every backup
    # follows its main's redundancy. Before the fiber settle, which would
    # otherwise drop the links the move keeps. Idempotent.
    processor_catalog.migrate_backup_processors(app.current_project)
    # The bar's remembered Mixed pick held to its one shape (True, with
    # redundancy on, on a chassis that can mix). Idempotent.
    processor_catalog.settle_redundancy_mixed(app.current_project)
    # The fiber store held to its rules the same way (links that no longer
    # hold, a 1.4.0 opticalCON's ownerBoxId) - never a cable pruned for
    # being unused here: a restore is what it restores.
    processor_catalog.settle_fiber(app.current_project)
    # Auto-numbering retired (user ruling, 2026-09-03): a file saved before
    # it carries no `autoRetired` mark, and its auto-drawn ports have to be
    # frozen into pins ONCE so the drawing does not change on load. The
    # counts that decide where those ports were live on the client, so this
    # funnel settles only what it can without them (no hardware, no
    # screens, auto already off: stamp and done) and the first
    # port-assignment request after the load - which carries the screens -
    # settles the rest. Idempotent by the mark; see retire_auto.
    if port_assignment.retire_auto(app.current_project):
        log_event('port_assignment_auto_retired', {'at': 'restore_project'})
    app.sync_next_layer_id()
    # The load funnel (file load, undo/redo): every screen lands with a
    # breakout its voltage allows - a file saved before the ruling, or an
    # undo snapshot holding an ineligible id, is healed here (2026-09-22).
    app.normalize_power_breakouts(app.current_project)
    # The 3D placement on every screen held to its shape: a hand-edited file
    # with a 40-degree joint lands at 15. A file without it loads unchanged.
    app.normalize_stage3d(app.current_project)
    # The IDM Locator's module counts and marks held to the screens as they
    # now stand (after the geometry rebuild above). A file without the key
    # loads unchanged.
    app.normalize_idm(app.current_project)
    # ... and the tab's field colour and border style (a file without the
    # key loads without it and draws white with shaded borders).
    app.normalize_idm_field(app.current_project)
    # ... and its live highlight, kept as the file (or the undo snapshot,
    # which carries the one on screen) has it, on a module that is there.
    app.normalize_idm_highlight(app.current_project)
    if release_ports:
        released = port_assignment.forget_released_port_cables(
            app.current_project, pins_before)
        if released:
            log_event('port_cables_forgotten', {
                'at': 'delete_group',
                'sockets': [f'{c}:{n}' for c, n in sorted(released)]})
    log_event('restore_project', {
        'name': app.current_project.get('name', '?'),
        'layers': len(app.current_project.get('layers', [])),
        'layer_names': [l.get('name', '?') for l in app.current_project.get('layers', [])]
    })
    marker = _replace_marker('restore')
    _emit_project_replaced(marker)
    _guide_took_the_show(marker['client'], marker['reason'])
    # Slice 12: surface a one-time migration notice to the client when the
    # incoming file lacked a v0.8 format_version. Carried as a top-level
    # transient field on the response only, never stored on disk because
    # the next save will write the now-present format_version, and future
    # loads of that same file won't re-migrate (and won't re-toast).
    response = dict(app.current_project)
    if did_migrate:
        response['_migration_notice'] = True
    return jsonify(response)


@project_bp.route('/api/project/stage3d', methods=['PUT'])
def save_stage3d_view():
    """The 3D view's own state on the project: the last camera, the length
    units its panel shows, the floor grid switch and the header and footer
    bars switch. View state, not an
    edit - nothing is broadcast, no undo entry is made on the client, and
    the pristine startup project stays pristine (an orbit is not a change
    to the show). Each key is optional; a camera that does not hold its
    shape is refused and the stored one kept."""
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'expected an object'}), 400
    proj = app.current_project
    if 'camera' in data:
        camera = app.sanitize_stage3d_camera(data.get('camera'))
        if camera is not None:
            proj['stage3dCamera'] = camera
    if data.get('units') in app.STAGE3D_UNITS:
        proj['stage3dUnits'] = data['units']
    if isinstance(data.get('grid'), bool):
        proj['stage3dGrid'] = data['grid']
    if isinstance(data.get('bars'), bool):
        proj['stage3dBars'] = data['bars']
    return jsonify({
        'stage3dCamera': proj.get('stage3dCamera'),
        'stage3dUnits': proj.get('stage3dUnits'),
        'stage3dGrid': proj.get('stage3dGrid'),
        'stage3dBars': proj.get('stage3dBars'),
    })


@project_bp.route('/api/project/rigging-tool', methods=['PUT'])
def put_rigging_tool():
    """The Header/Footer tab's Auto | Custom choice, one for the show
    (app-rigging.js _riggingToolNow). View state, not an edit: no undo
    entry on the client and a pristine project stays pristine, but it is
    saved with the show so reopening it or reloading the page comes back
    on the same choice. Anything but 'custom' is Auto, which is also what a
    show without it opens on."""
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'expected an object'}), 400
    tool = 'custom' if data.get('tool') == 'custom' else 'auto'
    app.current_project['riggingTool'] = tool
    log_event('rigging_tool', {'tool': tool})
    return jsonify({'riggingTool': tool})


@project_bp.route('/api/project/idm-field', methods=['PUT'])
def put_idm_field():
    """The IDM Locator's field: one solid colour for every screen and the
    border style drawn into it, whether each module's label is drawn, and
    the tab's Colours - labels, edges, the shade level and the saved mark
    colours (app.sanitize_idm_field). View state, not an
    edit - no undo entry on the client and a pristine project stays
    pristine - but saved with the show and told to every client on the LAN
    through `idm_field_updated`, so a tablet at the wall changes what the
    machine driving the wall puts out. The sender's own echo carries its
    `origin` so it can be skipped."""
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'expected an object'}), 400
    field = app.sanitize_idm_field(data.get('field'))
    if field is None:
        return jsonify({'error': 'field must be an object'}), 400
    app.current_project['idmField'] = field
    log_event('idm_field', field)
    socketio.emit('idm_field_updated', {
        'field': field,
        'origin': str(data.get('origin') or '')[:64],
    })
    return jsonify({'idmField': field})


# ── Beaches ──────────────────────────────────────────────────────────────
#
# "you can either create a beach or you can pick one from the drop-down of
# one that you created earlier in the project" (2026-09-08). The list lives
# on the project (app._normalize_beaches documents the shape); these routes
# are the only writers besides the load funnel, and every one answers with
# the whole project the way the canvas routes do, so the client adopts one
# truth rather than patching its copy.

def _beach_response(beach=None, created=False, status=200):
    app.current_project['is_pristine'] = False
    body = {'project': app.current_project}
    if beach is not None:
        body['beach'] = {'id': beach['id'], 'name': beach['name']}
        body['created'] = bool(created)
    emit_project_edited()
    return jsonify(body), status


def _beach_name_from(data):
    value = (data or {}).get('name')
    if value is not None and not isinstance(value, str):
        return None, 'Beach name must be text'
    text = (value or '').strip()
    if not text:
        return None, 'Beach name must not be blank'
    return text, None


@project_bp.route('/api/beaches', methods=['GET'])
def list_beaches():
    app._normalize_beaches(app.current_project)
    return jsonify({'beaches': app.current_project.get('beaches') or []})


@project_bp.route('/api/beaches', methods=['POST'])
def add_beach():
    """name -> {id, name}. A name the project already has (case-blind)
    answers with THAT beach, never a second one."""
    app._normalize_beaches(app.current_project)
    name, why = _beach_name_from(request.json)
    if why:
        return jsonify({'error': why}), 400
    beach, created = app._create_beach(app.current_project, name)
    log_event('beach_add', {'id': beach['id'], 'name': beach['name'],
                            'created': created})
    return _beach_response(beach, created, 201 if created else 200)


@project_bp.route('/api/beaches/order', methods=['PUT'])
def reorder_beaches():
    """{ids}: a permutation of the beach ids - the pull-sheet and binder
    order."""
    app._normalize_beaches(app.current_project)
    data = request.json or {}
    ids = data.get('ids')
    beaches = app.current_project.get('beaches') or []
    by_id = {b['id']: b for b in beaches}
    if (not isinstance(ids, list)
            or len(ids) != len(beaches)
            or any(not app._is_hashable(i) for i in ids)
            or set(ids) != set(by_id.keys())):
        return jsonify({'error': 'ids must be a permutation of the beach ids'}), 400
    app.current_project['beaches'] = [by_id[i] for i in ids]
    log_event('beach_reorder', {'order': ids})
    return _beach_response()


@project_bp.route('/api/beaches/<beach_id>', methods=['PUT'])
def rename_beach(beach_id):
    app._normalize_beaches(app.current_project)
    beach = app._find_beach(app.current_project, beach_id)
    if not beach:
        return jsonify({'error': 'Beach not found'}), 404
    name, why = _beach_name_from(request.json)
    if why:
        return jsonify({'error': why}), 400
    other = app._find_beach_by_name(app.current_project, name)
    if other and other['id'] != beach['id']:
        return jsonify({'error': f'There is already a beach called {other["name"]}'}), 400
    beach['name'] = name
    log_event('beach_rename', {'id': beach['id'], 'name': name})
    return _beach_response(beach)


@project_bp.route('/api/beaches/<beach_id>', methods=['DELETE'])
def delete_beach(beach_id):
    """Removes the beach and clears every beachId that pointed at it - the
    screens, distros and boxes fall back to their own positions."""
    app._normalize_beaches(app.current_project)
    beach = app._find_beach(app.current_project, beach_id)
    if not beach:
        return jsonify({'error': 'Beach not found'}), 404
    app.current_project['beaches'] = [
        b for b in app.current_project.get('beaches') or [] if b is not beach]
    cleared = 0
    for rec in app._beach_records(app.current_project):
        if rec.get('beachId') == beach_id:
            rec['beachId'] = None
            cleared += 1
    log_event('beach_delete', {'id': beach_id, 'cleared': cleared})
    return _beach_response()


# ── Notes checklist ──────────────────────────────────────────────────────
#
# The show to-do list under the free-text notes (app-notes-checklist.js):
# project['notesChecklist'] = [{id, text, done}], in order. A project
# without the key has an empty list; nothing migrates. The client writes the
# whole list here after each edit, and every other client is told through
# `notes_checklist_updated` (the sender's own echo carries its `origin` so
# it can be skipped). Undo and file load ride PUT /api/project like every
# other project field.

NOTES_CHECKLIST_MAX_ITEMS = 500
NOTES_CHECKLIST_MAX_TEXT = 500


def _clean_notes_checklist(items):
    """The list as stored, or None when the payload is not a list. Rows
    that are not objects are dropped; text is a string cut to length; done
    is a bool; a missing or repeated id gets a fresh one."""
    if not isinstance(items, list):
        return None
    out, seen = [], set()
    for n, raw in enumerate(items[:NOTES_CHECKLIST_MAX_ITEMS]):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get('id') or '')[:64]
        if not item_id or item_id in seen:
            item_id = f'ck{n}x{len(out)}'
            while item_id in seen:
                item_id += 'x'
        seen.add(item_id)
        text = raw.get('text')
        out.append({
            'id': item_id,
            'text': (text if isinstance(text, str) else '')[:NOTES_CHECKLIST_MAX_TEXT],
            'done': raw.get('done') is True,
        })
    return out


@project_bp.route('/api/project/notes-checklist', methods=['PUT'])
def put_notes_checklist():
    data = request.json or {}
    items = _clean_notes_checklist(data.get('items'))
    if items is None:
        return jsonify({'error': 'items must be a list'}), 400
    # Only a real change ends a pristine project: undo, a file load or a new
    # project re-send a list the server already holds (the client cannot tell
    # those apart), and the broadcast still goes so every client follows.
    if (app.current_project.get('notesChecklist') or []) != items:
        app.current_project['is_pristine'] = False
    # A project that never had a list keeps its shape for an empty one.
    if items or 'notesChecklist' in app.current_project:
        app.current_project['notesChecklist'] = items
    log_event('notes_checklist', {'items': len(items), 'done': sum(1 for i in items if i['done'])})
    socketio.emit('notes_checklist_updated', {
        'items': items,
        'origin': str(data.get('origin') or ''),
    })
    return jsonify({'items': items})
