"""
Output to Display, the server side of a native output window.

In the desktop app the launcher registers a NativeOutputHost (output_native.py)
here. The designer, running in a browser on the same machine, then:

  GET  /api/output/native          the displays, when native outputs are on
  POST /api/output/native/open     open one output full screen on a display
  POST /api/output/native/close    close outputs (the dialog, the designer leaving)
  GET  /api/output/native/list     which outputs are still open

and feeds each one:

  POST /api/output/feed/<id>/frame    the latest frame, a PNG at the raster size
  POST /api/output/feed/<id>/message  a line to show instead (a deleted canvas)

while the output window itself (/output?feed=<id>) waits for frames with

  GET  /api/output/feed/<id>?after=N  long poll: the next frame after N
  POST /api/output/feed/<id>/close    Esc in the output window

The server keeps only the latest frame of each output, so a slow display skips
frames instead of queueing them, and a window that reloads gets the picture
back at once. Everything here is for the host machine only, like the native
dialogs: another machine on the network cannot open windows on this one.
"""
import threading
import time
import uuid
from urllib.parse import quote, unquote, urlencode

from flask import Blueprint, Response, jsonify, request

from app import log_event
from output_native import OUTPUT_ID
from routes_dialog import _is_same_machine

output_bp = Blueprint('output', __name__)

# The launcher's NativeOutputHost, or None (tests, a plain server, a launcher
# whose native window failed: the browser opens the outputs then).
_native_host = None

_feeds = {}
_cond = threading.Condition()
POLL_SECONDS = 10.0
MAX_FRAME_BYTES = 256 * 1024 * 1024


class _Feed:
    __slots__ = ('seq', 'data', 'title', 'message', 'closed')

    def __init__(self):
        self.seq = 0
        self.data = None
        self.title = ''
        self.message = ''
        self.closed = False


def set_native_host(host):
    """Called by the desktop launcher once its GUI loop owns the windows."""
    global _native_host
    _native_host = host
    if host is not None:
        host.on_closed = _drop_feed


def native_host():
    return _native_host


def _drop_feed(output_id):
    with _cond:
        feed = _feeds.pop(output_id, None)
        if feed is not None:
            feed.closed = True
        _cond.notify_all()
    return feed is not None


@output_bp.before_request
def _local_only():
    addr = request.remote_addr or ''
    if not _is_same_machine(addr):
        log_event('output_native_rejected_remote', {'remote_addr': addr, 'path': request.path})
        return jsonify({'ok': False, 'error': 'Outputs open on the host machine only.'}), 403


# ---- native windows ----------------------------------------------------------

@output_bp.route('/api/output/native', methods=['GET'])
def native_available():
    host = _native_host
    if host is None:
        return jsonify({'available': False, 'displays': []})
    try:
        displays = host.displays()
    except Exception as exc:
        log_event('output_native_displays_failed', {'error': f'{type(exc).__name__}: {exc}'})
        return jsonify({'available': False, 'displays': []})
    return jsonify({'available': bool(displays), 'displays': displays})


@output_bp.route('/api/output/native/open', methods=['POST'])
def native_open():
    host = _native_host
    if host is None:
        return jsonify({'ok': False, 'error': 'Native outputs are not available.'}), 409
    data = request.get_json(silent=True) or {}
    try:
        display = int(data.get('display'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Pick a display.'}), 400
    output_id = uuid.uuid4().hex[:16]
    path = '/output?' + urlencode({
        'canvas': str(data.get('canvas') or ''),
        'view': str(data.get('view') or 'pixel-map'),
        'feed': output_id,
    })
    with _cond:
        _feeds[output_id] = _Feed()
    try:
        shown = host.open(output_id, display, path, str(data.get('title') or 'Output'))
    except Exception as exc:
        _drop_feed(output_id)
        log_event('output_native_open_failed', {
            'display': display, 'error': f'{type(exc).__name__}: {exc}'})
        return jsonify({'ok': False, 'error': 'The output window could not be opened.'}), 500
    return jsonify({'ok': True, 'id': output_id, 'display': shown})


@output_bp.route('/api/output/native/close', methods=['POST'])
def native_close():
    # sendBeacon posts text/plain: read the body whatever its type.
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get('ids')
    if ids is None and data.get('id'):
        ids = [data.get('id')]
    closed = []
    for output_id in ids or []:
        output_id = str(output_id)
        if not OUTPUT_ID.match(output_id):
            continue
        host = _native_host
        if host is not None:
            host.close(output_id)
        _drop_feed(output_id)
        closed.append(output_id)
    return jsonify({'ok': True, 'closed': closed})


@output_bp.route('/api/output/native/list', methods=['GET'])
def native_list():
    host = _native_host
    open_ids = host.open_ids() if host is not None else []
    with _cond:
        live = [i for i in open_ids if i in _feeds]
    return jsonify({'open': live})


# ---- frames ------------------------------------------------------------------

@output_bp.route('/api/output/feed/<output_id>/frame', methods=['POST'])
def feed_frame(output_id):
    data = request.get_data(cache=False)
    if not data or len(data) > MAX_FRAME_BYTES:
        return jsonify({'ok': False, 'error': 'No frame.'}), 400
    title = unquote(request.headers.get('X-Output-Title', ''))
    with _cond:
        feed = _feeds.get(output_id)
        if feed is None:
            return jsonify({'ok': False, 'closed': True}), 404
        feed.seq += 1
        feed.data = data
        feed.title = title or feed.title
        feed.message = ''
        _cond.notify_all()
        seq = feed.seq
    return jsonify({'ok': True, 'seq': seq})


@output_bp.route('/api/output/feed/<output_id>/message', methods=['POST'])
def feed_message(output_id):
    data = request.get_json(silent=True) or {}
    with _cond:
        feed = _feeds.get(output_id)
        if feed is None:
            return jsonify({'ok': False, 'closed': True}), 404
        feed.seq += 1
        feed.data = None
        feed.message = str(data.get('message') or 'Nothing to show.')
        feed.title = str(data.get('title') or feed.title)
        _cond.notify_all()
        seq = feed.seq
    return jsonify({'ok': True, 'seq': seq})


@output_bp.route('/api/output/feed/<output_id>', methods=['GET'])
def feed_wait(output_id):
    try:
        after = int(request.args.get('after', '0'))
    except ValueError:
        after = 0
    deadline = time.monotonic() + POLL_SECONDS
    with _cond:
        while True:
            feed = _feeds.get(output_id)
            if feed is None or feed.closed:
                return jsonify({'closed': True}), 410
            if feed.seq > after and (feed.data is not None or feed.message):
                seq, data, title, message = feed.seq, feed.data, feed.title, feed.message
                break
            left = deadline - time.monotonic()
            if left <= 0:
                return Response(status=204)
            _cond.wait(left)
    headers = {
        'X-Frame-Seq': str(seq),
        'X-Output-Title': quote(title or ''),
        'Cache-Control': 'no-store',
    }
    if data is None:
        res = jsonify({'seq': seq, 'message': message, 'title': title})
        res.headers.update(headers)
        return res
    return Response(data, mimetype='image/png', headers=headers)


@output_bp.route('/api/output/feed/<output_id>/close', methods=['POST'])
def feed_close(output_id):
    if not OUTPUT_ID.match(output_id or ''):
        return jsonify({'ok': False}), 400
    host = _native_host
    if host is not None:
        host.close(output_id)
    _drop_feed(output_id)
    log_event('output_native_escape', {'id': output_id})
    return jsonify({'ok': True})
