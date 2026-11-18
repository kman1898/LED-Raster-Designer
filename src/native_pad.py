"""The computer's game controller, read natively, for the IDM Locator.

Two halves, both in the server's process:

PadReaderSupervisor
    Starts native_pad_reader as a process of its own (the frozen app runs
    its own executable with --pad-reader; from source, the script under this
    Python), opens a socket on 127.0.0.1 for it alone (a random port and a
    token; nothing listens on the network), reads its JSON lines and hands
    each to the bridge. A reader that dies is started again, a few times
    (MAX_RESTARTS, waits growing per RESTART_BACKOFF; one that ran
    STEADY_S counts from zero again), then left off. pygame missing (or SDL
    unable to start) is not a crash: the reader is "unavailable" and is not
    tried again. Every line before the hello must carry the token, so only
    our own reader can say "unavailable". stop() ends it when the app quits;
    if the app dies without a stop, the reader sees its socket close and
    exits by itself. set_watched() tells the reader whether any page has
    the IDM Locator tab open: it polls quickly only then.

NativePadBridge
    Which page gets the controller. Only a designer page on THIS computer
    (a host page; routes_dialog._is_same_machine) ever hears of it: each
    one says when its IDM Locator tab opens or closes and when its window
    takes the focus (native_pad_watch), and the controller's states go to
    ONE page, the host page that most recently opened the tab or took the
    focus with the tab open. Any number of host pages see the reader's
    status (the panel shows a connected pad; with none, nothing). A tablet
    or phone never does, and keeps the browser's Gamepad API. The page drops what the old target
    held when the controller moves to another page (native_pad_idle).

The launchers call start_reader() once the server is up and stop_reader()
when the app quits; app.py wires the socket events.
"""
from __future__ import annotations

import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import OrderedDict

from native_pad_reader import (
    ASK_INPUT_MONITORING_ENV, BATTERY_WORDS, EXIT_UNAVAILABLE, STANDARD_BUTTONS,
)

# The app's settings key (launcher_settings) that says macOS's Input
# Monitoring question was put up once already: never again.
ASKED_KEY = 'pad_input_monitoring_asked'

MAX_RESTARTS = 5
RESTART_BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0)
STEADY_S = 60.0
HELLO_TIMEOUT_S = 20.0
STOP_TIMEOUT_S = 2.0

# The reader's states as the panel reads them. 'off': no launcher started
# one (python app.py, the tests); the page then says nothing and the
# browser reads the pad as before.
RUNNING_STATES = ('starting', 'running', 'restarting')
DOWN_STATES = ('unavailable', 'failed')


def reader_command():
    """The command that runs the reader: the app's own executable with
    --pad-reader when frozen, else the script under this Python."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--pad-reader']
    here = os.path.dirname(os.path.abspath(__file__))
    return [sys.executable, os.path.join(here, 'native_pad_reader.py')]


def pygame_present():
    """Is pygame here to be loaded? Found, never imported: SDL stays out of
    the server's process."""
    try:
        return importlib.util.find_spec('pygame') is not None
    except (ImportError, ValueError):
        return False


def _no_window_flags():
    # From source, the reader would open a console window of its own.
    return 0x08000000 if sys.platform == 'win32' else 0   # CREATE_NO_WINDOW


class PadReaderSupervisor:
    def __init__(self, on_message, log=None, command=None, available=None,
                 max_restarts=MAX_RESTARTS, backoff=RESTART_BACKOFF,
                 steady_s=STEADY_S, hello_timeout=HELLO_TIMEOUT_S, extra_env=None,
                 on_asked=None):
        self.on_message = on_message
        self.log = log or (lambda action, details=None: None)
        self.command = command or reader_command()
        self.available = available or pygame_present
        self.max_restarts = max_restarts
        self.backoff = tuple(backoff) or (1.0,)
        self.steady_s = steady_s
        self.hello_timeout = hello_timeout
        self.extra_env = dict(extra_env or {})
        self.on_asked = on_asked
        self.state = 'off'
        self.why = ''
        self.starts = 0          # processes started, all told
        self.restarts = 0        # restarts since the last steady run
        self.proc = None
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._conn = None
        self._live = False       # the reader on _conn said hello
        self._send_lock = threading.Lock()
        self.watched = False     # a page has the IDM Locator tab open
        self._listener = None
        self._err_tail = b''

    # ── public ───────────────────────────────────────────────────────────
    def start(self):
        """Start watching a reader. False (and 'unavailable') when pygame
        is not here."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            if not self.available():
                self._set('unavailable', 'pygame is not installed')
                self.log('native_pad_reader', {'state': 'unavailable', 'why': self.why})
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='lrd-pad-reader', daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout=STOP_TIMEOUT_S):
        """End the reader (the app is quitting)."""
        self._stop.set()
        for s in (self._conn, self._listener):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass
        self._end_proc(timeout)
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout)
        if self.state not in DOWN_STATES:
            self._set('off', 'stopped')
        self.log('native_pad_reader', {'state': 'stopped'})

    def running(self):
        p = self.proc
        return p is not None and p.poll() is None

    def set_watched(self, on):
        """Whether a page has the IDM Locator tab open (the bridge says so
        on every change): the reader polls quickly only while one does."""
        with self._send_lock:
            self.watched = bool(on)
            self._tell_watched()

    # ── inside ───────────────────────────────────────────────────────────
    def _set(self, state, why=''):
        self.state, self.why = state, why
        try:
            self.on_message({'t': 'reader', 'state': state, 'why': why})
        except Exception:
            pass

    def _end_proc(self, timeout):
        p = self.proc
        if p is None or p.poll() is not None:
            return
        try:
            p.terminate()
            p.wait(timeout)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
                p.wait(timeout)
            except Exception:
                pass
        except Exception:
            pass

    def _drain(self, stream):
        try:
            for chunk in iter(lambda: stream.read(512), b''):
                self._err_tail = (self._err_tail + chunk)[-2000:]
        except Exception:
            pass

    def _spawn(self, port, token):
        env = dict(os.environ)
        env.update(self.extra_env)
        env['LRD_PAD_PORT'] = str(port)
        env['LRD_PAD_TOKEN'] = token
        self._err_tail = b''
        proc = subprocess.Popen(self.command, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                creationflags=_no_window_flags())
        threading.Thread(target=self._drain, args=(proc.stderr,), name='lrd-pad-reader-err',
                         daemon=True).start()
        self.starts += 1
        return proc

    def _tell_watched(self):
        """Under _send_lock: the watch line to a reader that said hello."""
        conn = self._conn if self._live else None
        if conn is None:
            return
        try:
            conn.sendall((json.dumps({'t': 'watch', 'on': self.watched}) + '\n').encode('utf-8'))
        except OSError:
            pass

    def _accept(self, listener, proc):
        """The reader's connection, or None if it died or never called."""
        deadline = time.monotonic() + self.hello_timeout
        listener.settimeout(0.2)
        while not self._stop.is_set() and time.monotonic() < deadline:
            if proc.poll() is not None:
                return None
            try:
                conn, addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return None
            if addr[0] not in ('127.0.0.1', '::1'):
                conn.close()
                continue
            return conn
        return None

    def _serve(self, conn, token):
        """Pass the reader's lines on until it hangs up. True when it said
        it cannot run here."""
        unavailable = False
        conn.settimeout(None)
        f = conn.makefile('rb')
        hello = False
        try:
            for raw in f:
                if self._stop.is_set():
                    break
                try:
                    msg = json.loads(raw.decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get('t')
                if not hello:
                    # Before the hello, every line carries the token: a
                    # process that is not our reader can neither start the
                    # stream nor say pygame cannot load.
                    if not _token_ok(msg, token):
                        break             # not our reader
                    if kind == 'unavailable':
                        unavailable = True
                        self.why = str(msg.get('why', ''))[:300]
                        continue
                    if kind != 'hello':
                        break
                    hello = True
                    self._set('running')
                    self.log('native_pad_reader', {'state': 'running', 'pid': self.proc.pid,
                                                   'pygame': msg.get('pygame'), 'sdl': msg.get('sdl')})
                    with self._send_lock:
                        self._live = True
                        self._tell_watched()
                    continue
                if kind == 'input_monitoring_asked':
                    # asked once: a reader started again never asks
                    self.extra_env.pop(ASK_INPUT_MONITORING_ENV, None)
                    self.log('native_pad_input_monitoring', {'asked': True, 'granted': bool(msg.get('granted'))})
                    if self.on_asked is not None:
                        try:
                            self.on_asked()
                        except Exception:
                            pass
                    continue
                try:
                    self.on_message(msg)
                except Exception:
                    pass
        except OSError:
            pass
        finally:
            with self._send_lock:
                self._live = False
            try:
                f.close()
                conn.close()
            except OSError:
                pass
        return unavailable

    def _wait_backoff(self):
        wait = self.backoff[min(self.restarts - 1, len(self.backoff) - 1)]
        self._stop.wait(wait)

    def _run(self):
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
        except OSError as exc:
            self._set('failed', f'no local socket: {exc}')
            self.log('native_pad_reader', {'state': 'failed', 'why': self.why})
            return
        self._listener = listener
        port = listener.getsockname()[1]
        try:
            while not self._stop.is_set():
                token = secrets.token_hex(16)
                began = time.monotonic()
                self._set('starting' if self.starts == 0 else 'restarting')
                try:
                    self.proc = self._spawn(port, token)
                except OSError as exc:
                    self._set('failed', f'could not start: {exc}')
                    self.log('native_pad_reader', {'state': 'failed', 'why': self.why})
                    return
                self.log('native_pad_reader', {'state': 'started', 'pid': self.proc.pid,
                                               'command': os.path.basename(self.command[-1])})
                unavailable = False
                conn = self._accept(listener, self.proc)
                if conn is not None:
                    self._conn = conn
                    unavailable = self._serve(conn, token)
                    self._conn = None
                if self._stop.is_set():
                    return
                # Hung up or never called: let the process finish.
                try:
                    code = self.proc.wait(STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    self._end_proc(STOP_TIMEOUT_S)
                    code = self.proc.poll()
                if self._stop.is_set():
                    return
                if unavailable or code == EXIT_UNAVAILABLE:
                    self._set('unavailable', self.why or 'pygame could not start here')
                    self.log('native_pad_reader', {'state': 'unavailable', 'why': self.why, 'code': code})
                    return
                if time.monotonic() - began >= self.steady_s:
                    self.restarts = 0
                self.restarts += 1
                tail = self._err_tail.decode('utf-8', errors='replace').strip()[-600:]
                if self.restarts > self.max_restarts:
                    self._set('failed', f'it stopped {self.restarts} times')
                    self.log('native_pad_reader', {'state': 'failed', 'code': code, 'why': self.why,
                                                   'stderr': tail})
                    return
                self.log('native_pad_reader', {'state': 'exited', 'code': code,
                                               'restart': self.restarts, 'stderr': tail})
                self._set('restarting', f'exited with {code}')
                self._wait_backoff()
        finally:
            try:
                listener.close()
            except OSError:
                pass
            self._listener = None


def _token_ok(msg, token):
    got = msg.get('token')
    return isinstance(got, str) and secrets.compare_digest(got.encode('utf-8'), token.encode('utf-8'))


# ── the bridge ────────────────────────────────────────────────────────────

def _num(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f:           # NaN
        return 0.0
    return max(lo, min(hi, f))


def clean_state(msg):
    """A reader state as the page gets it, or None."""
    pid = msg.get('id')
    if not isinstance(pid, (int, str)) or isinstance(pid, bool):
        return None
    buttons = msg.get('buttons') if isinstance(msg.get('buttons'), list) else []
    axes = msg.get('axes') if isinstance(msg.get('axes'), list) else []
    touch = msg.get('touch') if isinstance(msg.get('touch'), list) else []
    return {
        'id': str(pid),
        'buttons': [_num(b, 0.0, 1.0) for b in buttons[:STANDARD_BUTTONS]]
        + [0.0] * max(0, STANDARD_BUTTONS - len(buttons)),
        'axes': [_num(a, -1.0, 1.0) for a in axes[:4]] + [0.0] * max(0, 4 - len(axes)),
        'touch': [_num(t, -1.0, 1.0) for t in touch[:2]] + [0.0] * max(0, 2 - len(touch)),
    }


def clean_pads(pads):
    out = []
    for p in pads if isinstance(pads, list) else []:
        if not isinstance(p, dict):
            continue
        pid = p.get('id')
        if not isinstance(pid, (int, str)) or isinstance(pid, bool):
            continue
        battery = p.get('battery') if p.get('battery') in BATTERY_WORDS else 'unknown'
        out.append({'id': str(pid), 'name': str(p.get('name') or 'Controller')[:80],
                    'battery': battery, 'touchpad': bool(p.get('touchpad'))})
    return out


class NativePadBridge:
    def __init__(self, emit=None, log=None):
        self._lock = threading.RLock()
        self.emit = emit                  # emit(event, data, to=sid)
        self.log = log                    # log(action, details)
        self.watchers = OrderedDict()     # host page sid -> its IDM tab is open
        self.target = None
        self.on_watch = None              # on_watch(bool): a page has the tab open, or none
        self._watched_said = None
        self.reader = 'off'
        self.why = ''
        self.pads = []
        self.input_monitoring = None

    def status(self):
        with self._lock:
            return {'reader': self.reader, 'why': self.why, 'pads': [dict(p) for p in self.pads],
                    'inputMonitoring': self.input_monitoring, 'platform': sys.platform}

    def _send(self, event, data, sid):
        if self.emit is None or sid is None:
            return
        try:
            self.emit(event, data, to=sid)
        except Exception:
            pass

    def _log(self, action, details):
        if self.log is not None:
            try:
                self.log(action, details)
            except Exception:
                pass

    def watch(self, sid, idm):
        """A host page's IDM tab opened (or its window took the focus with
        it open), or closed. Returns the status for that page."""
        with self._lock:
            if idm:
                self.watchers.pop(sid, None)
                self.watchers[sid] = True        # the newest goes last
            else:
                self.watchers[sid] = False
            self._retarget()
            return self.status()

    def forget(self, sid):
        with self._lock:
            if self.watchers.pop(sid, None) is not None:
                self._retarget()

    def _retarget(self):
        new = None
        for sid, idm in self.watchers.items():
            if idm:
                new = sid
        old = self.target
        if new != old:
            self.target = new
            self._log('native_pad_target', {
                'page': new is not None, 'to': _short(new), 'from': _short(old),
                'on_tab': sum(1 for on in self.watchers.values() if on),
                'pages': len(self.watchers)})
            if old is not None and old in self.watchers:
                # what the controller held there is let go
                self._send('native_pad_idle', {}, old)
        watched = new is not None
        if watched != self._watched_said:
            self._watched_said = watched
            if self.on_watch is not None:
                try:
                    self.on_watch(watched)
                except Exception:
                    pass

    def _broadcast_status(self):
        st = self.status()
        for sid in list(self.watchers):
            self._send('native_pad_status', st, sid)

    def handle(self, msg):
        """One message from the reader (or the supervisor's own 'reader')."""
        if not isinstance(msg, dict):
            return
        kind = msg.get('t')
        if kind == 'state':
            clean = clean_state(msg)
            with self._lock:
                target = self.target
            if clean is not None and target is not None:
                self._send('native_pad_state', clean, target)
            return
        with self._lock:
            if kind == 'status':
                pads = clean_pads(msg.get('pads'))
                before = {p['id']: p for p in self.pads}
                after = {p['id']: p for p in pads}
                for pid in after.keys() - before.keys():
                    self._log('native_pad_connected', {'name': after[pid]['name'],
                                                       'battery': after[pid]['battery']})
                for pid in before.keys() - after.keys():
                    self._log('native_pad_disconnected', {'name': before[pid]['name']})
                self.pads = pads
                im = msg.get('inputMonitoring')
                im = im if im in ('granted', 'denied', 'unknown') else None
                if im != self.input_monitoring:
                    self._log('native_pad_input_monitoring', {'value': im, 'was': self.input_monitoring})
                self.input_monitoring = im
            elif kind == 'reader':
                self.reader = str(msg.get('state') or 'off')
                self.why = str(msg.get('why') or '')[:300]
                if self.reader != 'running':
                    self.pads = []
            else:
                return
            self._broadcast_status()

    def reset(self):
        """Back to no reader and no pages (the tests)."""
        with self._lock:
            self.watchers.clear()
            self.target = None
            self._watched_said = None
            self.reader, self.why = 'off', ''
            self.pads = []
            self.input_monitoring = None


def _short(sid):
    """A page's socket id, cut short for the log."""
    return None if sid is None else str(sid)[:6]


BRIDGE = NativePadBridge()
_SUPERVISOR = None
_SUP_LOCK = threading.Lock()


def input_monitoring_ask(settings, save, platform=None):
    """(extra_env, on_asked) for the reader: on a Mac whose settings say
    the Input Monitoring question was never put up, the reader asks, and
    the settings remember it (the launcher's own settings dict, so its
    next save keeps the note). Elsewhere, nothing. asked() runs on the
    supervisor's thread: the launchers hand in launcher_settings.save_settings,
    which takes one lock for every save, theirs and this one."""
    platform = sys.platform if platform is None else platform
    if platform != 'darwin' or settings is None or settings.get(ASKED_KEY):
        return {}, None

    def asked():
        settings[ASKED_KEY] = True
        if save is not None:
            save(settings)
    return {ASK_INPUT_MONITORING_ENV: '1'}, asked


def start_reader(log=None, settings=None, save=None, **kwargs):
    """Start the reader beside the server (the launchers, once, with
    their settings and save_settings). Never raises: the app runs without
    a controller."""
    global _SUPERVISOR
    try:
        with _SUP_LOCK:
            if _SUPERVISOR is not None:
                return _SUPERVISOR
            if log is not None and BRIDGE.log is None:
                BRIDGE.log = log
            env, asked = input_monitoring_ask(settings, save)
            if env:
                kwargs['extra_env'] = dict(kwargs.get('extra_env') or {}, **env)
                kwargs['on_asked'] = asked
            sup = PadReaderSupervisor(BRIDGE.handle, log=log, **kwargs)
            _SUPERVISOR = sup
            with BRIDGE._lock:
                sup.watched = BRIDGE.target is not None
                BRIDGE._watched_said = sup.watched
                BRIDGE.on_watch = sup.set_watched
        sup.start()
        import atexit
        atexit.register(stop_reader)
        return sup
    except Exception as exc:
        if log is not None:
            try:
                log('native_pad_reader', {'state': 'failed', 'why': f'{type(exc).__name__}: {exc}'})
            except Exception:
                pass
        return None


def stop_reader():
    """End the reader (Quit). Safe to call any number of times."""
    global _SUPERVISOR
    with _SUP_LOCK:
        sup, _SUPERVISOR = _SUPERVISOR, None
    if sup is not None:
        with BRIDGE._lock:
            if getattr(BRIDGE.on_watch, '__self__', None) is sup:
                BRIDGE.on_watch = None
        try:
            sup.stop()
        except Exception:
            pass
