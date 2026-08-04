"""
Log routes: in-app log viewer, clear, reveal-in-file-manager, and the client
log ingest endpoint. Log paths + log_event come from app; the logging
infrastructure itself (rotation, startup setup) stays in app.
"""
import os
import re
import sys
import subprocess
from collections import deque
from datetime import datetime

from flask import Blueprint, request, jsonify

from app import LOG_FILE_PATH, LOG_DIR_PATH, log_event

logs_bp = Blueprint('logs', __name__)

# The outer "timestamp" is always the FIRST one in a log line; details.clientTime
# is UTC and must never be what the time filter matches.
_LINE_TIMESTAMP_RE = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
_TIMESTAMP_PARTS_RE = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})')


def _log_line_epoch_ms(line):
    """Epoch-ms of a log line's outer timestamp, or None if unreadable.

    Log timestamps are written in server-LOCAL time, so they are rebuilt as
    local time here (naive datetime.timestamp() uses the local zone).
    """
    m = _LINE_TIMESTAMP_RE.search(line)
    if not m:
        return None
    parts = _TIMESTAMP_PARTS_RE.match(m.group(1))
    if not parts:
        return None
    try:
        dt = datetime(*(int(p) for p in parts.groups()))
        return int(dt.timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        return None


def _epoch_ms_arg(name):
    """Read an optional epoch-ms query param. Missing/blank/garbage -> None.

    Ignoring a non-numeric value (rather than erroring) keeps the viewer
    showing the unfiltered log instead of a 500.
    """
    raw = (request.args.get(name) or '').strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _reject_if_not_host():
    """403 unless the request came from the machine running the app.

    Shares routes_dialog's definition rather than re-testing loopback here.
    A loopback-only test is wrong the moment the launcher binds the server to
    a network interface so the drawing can be opened from another machine -
    the HOST then reaches its own app at that LAN address, and a loopback test
    locks it out of its own logs. Returns a response to return, or None.
    """
    from routes_dialog import _is_same_machine
    addr = request.remote_addr or ''
    if _is_same_machine(addr):
        return None
    log_event('logs_host_action_rejected_remote',
              {'remote_addr': addr, 'path': request.path})
    return jsonify({'error': 'Only available on the host machine.'}), 403


@logs_bp.route('/api/logs', methods=['GET'])
def get_logs():
    """Return last N lines of the current log file (most recent at bottom).

    Optional `since` / `until` query params (epoch milliseconds, inclusive on
    both ends) filter by each line's outer timestamp across the WHOLE file, not
    just the tail; `lines` then caps the result to the most recent N matches.
    """
    try:
        lines_arg = int(request.args.get('lines', '500'))
    except ValueError:
        lines_arg = 500
    lines_arg = max(50, min(lines_arg, 20000))
    since_ms = _epoch_ms_arg('since')
    until_ms = _epoch_ms_arg('until')
    filtering = since_ms is not None or until_ms is not None
    result_lines = []
    matched_count = None
    file_size = 0
    try:
        if os.path.isfile(LOG_FILE_PATH):
            file_size = os.path.getsize(LOG_FILE_PATH)
            if filtering:
                # Whole-file scan, streamed a line at a time and kept in a
                # bounded deque, so a 20 MB log never lands in memory at once.
                kept = deque(maxlen=lines_arg)
                matched_count = 0
                try:
                    with open(LOG_FILE_PATH, 'r', encoding='utf-8',
                              errors='replace') as f:
                        for raw_line in f:
                            line = raw_line.rstrip('\r\n')
                            if not line:
                                continue
                            ts = _log_line_epoch_ms(line)
                            if ts is None:
                                continue  # no readable timestamp: not in range
                            if since_ms is not None and ts < since_ms:
                                continue
                            if until_ms is not None and ts > until_ms:
                                continue
                            matched_count += 1
                            kept.append(line)
                except OSError:
                    pass
                result_lines = list(kept)
            else:
                tail_bytes = b''
                chunk_size = 0
                # Read up to 4 MB from the end (plenty for ~20k lines)
                max_chunk = 4 * 1024 * 1024
                try:
                    with open(LOG_FILE_PATH, 'rb') as f:
                        f.seek(0, os.SEEK_END)
                        pos = f.tell()
                        chunk_size = min(pos, max_chunk)
                        f.seek(pos - chunk_size, os.SEEK_SET)
                        tail_bytes = f.read()
                except OSError:
                    pass
                text = tail_bytes.decode('utf-8', errors='replace')
                # Drop a partial first line if we didn't read from byte 0
                if 0 < chunk_size < file_size and text:
                    nl = text.find('\n')
                    if nl != -1:
                        text = text[nl + 1:]
                all_lines = text.splitlines()
                result_lines = all_lines[-lines_arg:]
    except OSError:
        pass
    # Count archived log files in the same directory
    archive_count = 0
    try:
        for fname in os.listdir(LOG_DIR_PATH):
            if fname.startswith('led_raster_designer_') and fname.endswith('.log'):
                archive_count += 1
    except OSError:
        pass
    return jsonify({
        'lines': result_lines,
        'file_size_bytes': file_size,
        'file_path': LOG_FILE_PATH,
        'dir_path': LOG_DIR_PATH,
        'archive_count': archive_count,
        'returned_count': len(result_lines),
        # None when no time filter was applied; otherwise how many lines in the
        # whole file matched, so the viewer can say "most recent N of M".
        'matched_count': matched_count,
        'filtered': filtering
    })


@logs_bp.route('/api/logs', methods=['DELETE'])
def clear_logs():
    """Truncate the active log file. Archived (rotated) logs are preserved."""
    # Host only. This had NO check at all while its sibling `reveal` did, so an
    # unauthenticated LAN peer could wipe the host's diagnostic trail - the
    # same log used to diagnose bugs like the one that led here.
    denied = _reject_if_not_host()
    if denied:
        return denied
    try:
        os.makedirs(LOG_DIR_PATH, exist_ok=True)
        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write('')
    except OSError as e:
        return jsonify({'error': f'Failed to clear logs: {e}'}), 500
    log_event('clear_logs')
    return jsonify({'status': 'success'})


@logs_bp.route('/api/logs/reveal', methods=['POST'])
def reveal_logs_folder():
    """Open the logs directory in the OS file manager (Finder / Explorer / xdg-open)."""
    # Host-machine action: opening windows on the host must not be remotely
    # triggerable by an unauthenticated LAN peer.
    denied = _reject_if_not_host()
    if denied:
        return denied
    try:
        os.makedirs(LOG_DIR_PATH, exist_ok=True)
        if sys.platform == 'darwin':
            subprocess.Popen(['open', LOG_DIR_PATH])
        elif sys.platform == 'win32':
            os.startfile(LOG_DIR_PATH)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(['xdg-open', LOG_DIR_PATH])
    except Exception as e:
        return jsonify({'error': f'Failed to open logs folder: {e}'}), 500
    return jsonify({'status': 'success', 'path': LOG_DIR_PATH})


@logs_bp.route('/api/log', methods=['POST'])
def client_log():
    data = request.json or {}
    action = data.get('action', 'client_log')
    details = data.get('details', {})
    log_event(action, details, source='client')
    return jsonify({'status': 'ok'})
