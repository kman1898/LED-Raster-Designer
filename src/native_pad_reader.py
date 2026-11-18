"""The game controller reader for the IDM Locator, run as its own process.

WHY A PROCESS OF ITS OWN
    A browser's Gamepad API gives the buttons and sticks of a PlayStation or
    Xbox controller, but never where a finger is on a PlayStation pad's
    touchpad. SDL does (through pygame). SDL wants its event loop on the
    main thread on macOS, and the launcher's window or tray icon owns that
    thread, so the reader runs as a small process of its own, started and
    watched by the server (native_pad.PadReaderSupervisor). It sends no
    keystrokes anywhere, so it needs no Accessibility permission.

WHAT IT SENDS
    One JSON object per line over a socket to 127.0.0.1, to a port the
    server opened for it alone (LRD_PAD_PORT) and with the token it was
    given (LRD_PAD_TOKEN); nothing listens on the network for it. The server
    passes it on to the designer page on this computer that has the IDM
    Locator tab open (native_pad.NativePadBridge).

      {"t": "hello", "token": ..., "pygame": "2.6.1", "sdl": "2.28.4"}
      {"t": "status", "pads": [{"id", "name", "battery", "touchpad"}],
       "inputMonitoring": "granted" | "denied" | "unknown" | null}
      {"t": "state", "id": <pad>, "buttons": [17 numbers],
       "axes": [4 numbers], "touch": [dx, dy]}
      {"t": "input_monitoring_asked", "granted": true | false}
      {"t": "unavailable", "token": ..., "why": ...}   (then exit 3)

    The server sends one thing back, a line saying whether any page has
    the IDM Locator tab open:

      {"t": "watch", "on": true | false}

    macOS's Input Monitoring is asked for ONCE ever (owner, 2026-11-17):
    the server starts the first reader with LRD_PAD_ASK_INPUT_MONITORING=1,
    the reader puts up the system's question (IOHIDRequestAccess) and says
    so, and the server notes it in the app's settings, which outlast
    updates. macOS remembers the answer from then on; the app never asks
    again and says nothing about it.

    The buttons and axes are in the browser's "standard" layout (the same
    numbers app-idm-gamepad.js reads from navigator.getGamepads), so ONE
    button table drives the browser's pad and this one. "touch" is how far
    the finger slid since the last state, in touchpad widths (the height
    scaled to the same length); the page turns it into module steps at the
    speed set in the panel. The touchpad's click is not sent: it does
    nothing (owner, 2026-11-17).

    A state goes out when something changed, and again 30 times a second
    while a button or stick is held, so the page's held-direction repeat
    keeps time even while its window is hidden behind another.

    The loop turns every ACTIVE_WAIT_MS while a controller is connected and
    a page watches the IDM Locator tab, and every IDLE_WAIT_MS otherwise
    (no controller, or no page on the tab): SDL keeps the events in
    between, and the reader costs next to nothing the rest of the day.

TRY IT WITH A CONTROLLER
    From source:   python src/native_pad_reader.py --test
    The app:       "LED Raster Designer.exe" --pad-reader --test   (Windows)
                   "LED Raster Designer.app/Contents/MacOS/LED Raster Designer" --pad-reader --test
    It prints every controller event and what the app would make of it, and
    sends nothing. --raw adds SDL's own joystick events.

Exit codes: 0 when the server went away or Ctrl+C, EXIT_UNAVAILABLE when
pygame (SDL) cannot be loaded here, anything else a crash (restarted by the
supervisor a few times).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

EXIT_UNAVAILABLE = 3

# SDL hints, set before pygame loads.
SDL_HINTS = {
    # No window of ours ever has the focus: read the pad anyway.
    'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS': '1',
    # A PlayStation pad over Bluetooth starts in a simple report mode with
    # no touchpad in it; these switch it to the full report that has it.
    'SDL_JOYSTICK_HIDAPI_PS5_RUMBLE': '1',
    'SDL_JOYSTICK_HIDAPI_PS4_RUMBLE': '1',
    'SDL_JOYSTICK_HIDAPI_PS5': '1',
    'SDL_JOYSTICK_HIDAPI_PS4': '1',
    # No window and no Dock icon: SDL's events without a display.
    'SDL_VIDEODRIVER': 'dummy',
    'PYGAME_HIDE_SUPPORT_PROMPT': '1',
    # SDL raises Windows' timer resolution to 1 ms for as long as it runs,
    # which keeps the whole computer waking up more often: leave it be.
    'SDL_TIMER_RESOLUTION': '0',
}

# The browser's standard layout (app-idm-gamepad.js PAD_BUTTONS).
STANDARD_BUTTONS = 17
LT, RT = 6, 7
# SDL_GameControllerButton -> standard button. SDL's order: a b x y back
# guide start leftstick rightstick leftshoulder rightshoulder dpup dpdown
# dpleft dpright misc1 paddle1-4 touchpad. misc1 (the mute button), the
# paddles and the touchpad click have no standard number and are dropped.
SDL_TO_STANDARD = {
    0: 0,    # a: A / Cross
    1: 1,    # b: B / Circle
    2: 2,    # x: X / Square
    3: 3,    # y: Y / Triangle
    4: 8,    # back: View / Share / Create
    5: 16,   # guide: the home button
    6: 9,    # start: Menu / Options
    7: 10,   # left stick press
    8: 11,   # right stick press
    9: 4,    # left shoulder: LB / L1
    10: 5,   # right shoulder: RB / R1
    11: 12,  # D-pad up
    12: 13,  # D-pad down
    13: 14,  # D-pad left
    14: 15,  # D-pad right
}
SDL_TOUCHPAD_CLICK = 20
SDL_BUTTON_NAMES = [
    'a', 'b', 'x', 'y', 'back', 'guide', 'start', 'leftstick', 'rightstick',
    'leftshoulder', 'rightshoulder', 'dpup', 'dpdown', 'dpleft', 'dpright',
    'misc1', 'paddle1', 'paddle2', 'paddle3', 'paddle4', 'touchpad',
]
STANDARD_NAMES = [
    'A / Cross', 'B / Circle', 'X / Square', 'Y / Triangle', 'LB / L1',
    'RB / R1', 'LT / L2', 'RT / R2', 'View / Share', 'Menu / Options',
    'Left stick press', 'Right stick press', 'D-pad up', 'D-pad down',
    'D-pad left', 'D-pad right', 'Home',
]
# SDL axis -> standard axis (sticks) or standard button (triggers).
SDL_AXIS_TO_STANDARD = {0: ('axis', 0), 1: ('axis', 1), 2: ('axis', 2), 3: ('axis', 3),
                        4: ('button', LT), 5: ('button', RT)}
AXIS_MAX = 32767.0

# The touchpad is about twice as wide as it is tall, but SDL gives both as
# 0..1: the height is scaled so a finger moving a centimetre goes as far
# either way.
TOUCH_ASPECT = 0.5
# A jump larger than this between two reports is a finger swap or a glitch,
# not a slide.
TOUCH_GLITCH = 0.3

HELD_BUTTON = 0.5
HELD_AXIS = 0.25
AXIS_CHANGE = 0.04          # smaller stick changes wait for the next send
RESEND_HELD_S = 1 / 30      # a held state goes out again this often
MIN_SEND_S = 1 / 60         # stick and touch changes, at most this often
BATTERY_EVERY_S = 15.0
PERMISSION_EVERY_S = 5.0
# How long the loop waits between turns: quick while a controller is in use
# on the IDM Locator tab, slow otherwise.
ACTIVE_WAIT_MS = 8
IDLE_WAIT_MS = 100

_PLAYSTATION_HINTS = ('ps5', 'ps4', 'dualsense', 'dualshock', 'playstation', 'wireless controller')
# SDL's power levels, as the panel words them.
BATTERY_WORDS = {'empty': 'battery empty', 'low': 'battery low', 'medium': 'battery medium',
                 'full': 'battery full', 'max': 'battery full', 'wired': 'on a cable'}


def has_touchpad_name(name):
    """A PlayStation pad by its name (an Xbox pad's name has "Wireless
    Controller" in it too). A touch on the pad settles it either way."""
    n = (name or '').lower()
    return 'xbox' not in n and any(h in n for h in _PLAYSTATION_HINTS)


class PadState:
    """One controller: its standard-layout buttons and axes, the finger on
    its touchpad, and how far that finger slid since the last send."""

    def __init__(self, pad_id, name='Controller', battery='unknown', touchpad=None):
        self.id = pad_id
        self.name = name or 'Controller'
        self.battery = battery
        self.touchpad = has_touchpad_name(self.name) if touchpad is None else bool(touchpad)
        self.buttons = [0.0] * STANDARD_BUTTONS
        self.axes = [0.0, 0.0, 0.0, 0.0]
        self.fingers = {}          # finger -> (x, y)
        self.primary = None        # the finger that glides
        self.last = (0.0, 0.0)
        self.glide = [0.0, 0.0]    # slid since the last send
        self.sent_axes = [0.0, 0.0, 0.0, 0.0]
        self.sent_buttons = [0.0] * STANDARD_BUTTONS
        self.dirty = True
        self.urgent = True         # a button changed: send without waiting
        self.sent_at = 0.0

    def held(self):
        return (any(b > HELD_BUTTON for b in self.buttons)
                or any(abs(a) > HELD_AXIS for a in self.axes))

    def info(self):
        return {'id': self.id, 'name': self.name, 'battery': self.battery,
                'touchpad': bool(self.touchpad)}

    def take_state(self, now):
        """The state message, and the glide reset: what slid is sent once."""
        msg = {'t': 'state', 'id': self.id,
               'buttons': [round(b, 3) for b in self.buttons],
               'axes': [round(a, 3) for a in self.axes],
               'touch': [round(self.glide[0], 5), round(self.glide[1], 5)]}
        self.glide = [0.0, 0.0]
        self.sent_axes = list(self.axes)
        self.sent_buttons = list(self.buttons)
        self.dirty = self.urgent = False
        self.sent_at = now
        return msg

    def due(self, now):
        """Should a state go out now?"""
        if self.urgent:
            return True
        if self.dirty and now - self.sent_at >= MIN_SEND_S:
            return True
        return self.held() and now - self.sent_at >= RESEND_HELD_S


class PadNormaliser:
    """SDL controller events, as plain tuples, to standard-layout pads.

    Events (the pygame adapter, from_pygame, makes these):
      ('added', id, name, battery)   ('removed', id)
      ('button', id, sdl_button, down)   ('axis', id, sdl_axis, raw_value)
      ('touch', id, phase, finger, x, y)   phase: down | motion | up

    handle() returns what changed for the log: [('added', pad) |
    ('removed', pad) | ('button', pad, std, down) | ('ignored', pad, what) |
    ('glide', pad, dx, dy)]."""

    def __init__(self):
        self.pads = {}

    def handle(self, ev):
        kind = ev[0]
        if kind == 'added':
            _, pid, name, battery = ev
            if pid in self.pads:
                return []
            pad = PadState(pid, name, battery)
            self.pads[pid] = pad
            return [('added', pad)]
        if kind == 'removed':
            pad = self.pads.pop(ev[1], None)
            return [('removed', pad)] if pad else []
        pad = self.pads.get(ev[1])
        if pad is None:
            return []
        if kind == 'button':
            _, _, sdl_button, down = ev
            std = SDL_TO_STANDARD.get(sdl_button)
            if std is None:
                what = 'touchpad click' if sdl_button == SDL_TOUCHPAD_CLICK else (
                    SDL_BUTTON_NAMES[sdl_button] if 0 <= sdl_button < len(SDL_BUTTON_NAMES) else f'button {sdl_button}')
                return [('ignored', pad, what)]
            value = 1.0 if down else 0.0
            if pad.buttons[std] != value:
                pad.buttons[std] = value
                pad.dirty = pad.urgent = True
            return [('button', pad, std, bool(down))]
        if kind == 'axis':
            _, _, sdl_axis, raw = ev
            where = SDL_AXIS_TO_STANDARD.get(sdl_axis)
            if where is None:
                return []
            value = max(-1.0, min(1.0, float(raw) / AXIS_MAX))
            slot, i = where
            if slot == 'button':
                value = max(0.0, value)
                was = pad.buttons[i]
                pad.buttons[i] = value
                if (was > HELD_BUTTON) != (value > HELD_BUTTON):
                    pad.dirty = pad.urgent = True
                elif abs(value - pad.sent_buttons[i]) >= AXIS_CHANGE:
                    pad.dirty = True
            else:
                pad.axes[i] = value
                if abs(value - pad.sent_axes[i]) >= AXIS_CHANGE:
                    pad.dirty = True
            return []
        if kind == 'touch':
            _, _, phase, finger, x, y = ev
            return self._touch(pad, phase, finger, float(x), float(y))
        return []

    def _touch(self, pad, phase, finger, x, y):
        pad.touchpad = True
        if phase == 'up':
            pad.fingers.pop(finger, None)
            if finger == pad.primary:
                pad.primary = None
                if pad.fingers:      # another finger still down glides on
                    pad.primary, pad.last = next(iter(pad.fingers.items()))
            return []
        pad.fingers[finger] = (x, y)
        if pad.primary is None:
            pad.primary, pad.last = finger, (x, y)
            return []
        if phase == 'down' or finger != pad.primary:
            return []
        dx, dy = x - pad.last[0], y - pad.last[1]
        pad.last = (x, y)
        if abs(dx) > TOUCH_GLITCH or abs(dy) > TOUCH_GLITCH:
            return []
        dy *= TOUCH_ASPECT
        if not dx and not dy:
            return []
        pad.glide[0] += dx
        pad.glide[1] += dy
        pad.dirty = True
        return [('glide', pad, dx, dy)]

    def status(self, input_monitoring=None):
        return {'t': 'status', 'pads': [p.info() for p in self.pads.values()],
                'inputMonitoring': input_monitoring}


# ── pygame ────────────────────────────────────────────────────────────────

def apply_sdl_hints(env=None):
    env = os.environ if env is None else env
    for k, v in SDL_HINTS.items():
        env.setdefault(k, v)


def load_pygame():
    """(pygame, controller module), or raises ImportError."""
    apply_sdl_hints()
    import pygame  # noqa: WPS433 (loaded here: the app runs without it)
    from pygame._sdl2 import controller
    return pygame, controller


def _ev_attr(ev, names, default):
    for n in names:
        if hasattr(ev, n):
            return getattr(ev, n)
    return default


class SdlPads:
    """Opens controllers as SDL reports them and turns pygame's events into
    PadNormaliser tuples."""

    def __init__(self, pygame, controller):
        self.pg = pygame
        self.ctl = controller
        self.open = {}          # instance id -> (Controller, Joystick)

    def start(self):
        self.pg.display.init()   # the dummy driver: no window
        self.pg.joystick.init()
        self.ctl.init()

    def battery(self, pid):
        try:
            return self.open[pid][1].get_power_level() or 'unknown'
        except Exception:
            return 'unknown'

    def events(self, ev):
        pg = self.pg
        t = ev.type
        if t == pg.CONTROLLERDEVICEADDED:
            try:
                c = self.ctl.Controller(ev.device_index)
                joy = c.as_joystick()
                pid = joy.get_instance_id()
            except Exception as exc:
                return [('error', f'could not open controller {ev.device_index}: {exc}')]
            if pid in self.open:
                return []
            self.open[pid] = (c, joy)
            # A silent rumble also nudges a PlayStation pad over Bluetooth
            # into the full report that carries the touchpad.
            try:
                c.rumble(0.0, 0.0, 1)
            except Exception:
                pass
            name = getattr(c, 'name', None) or joy.get_name() or 'Controller'
            return [('added', pid, name, self.battery(pid))]
        if t == pg.CONTROLLERDEVICEREMOVED:
            pid = _ev_attr(ev, ('instance_id',), None)
            pair = self.open.pop(pid, None)
            if pair:
                try:
                    pair[0].quit()
                except Exception:
                    pass
            return [('removed', pid)]
        pid = _ev_attr(ev, ('instance_id',), None)
        if t in (pg.CONTROLLERBUTTONDOWN, pg.CONTROLLERBUTTONUP):
            return [('button', pid, int(ev.button), t == pg.CONTROLLERBUTTONDOWN)]
        if t == pg.CONTROLLERAXISMOTION:
            return [('axis', pid, int(ev.axis), float(ev.value))]
        phases = {pg.CONTROLLERTOUCHPADDOWN: 'down', pg.CONTROLLERTOUCHPADMOTION: 'motion',
                  pg.CONTROLLERTOUCHPADUP: 'up'}
        if t in phases:
            return [('touch', pid, phases[t], int(_ev_attr(ev, ('finger_id', 'finger'), 0)),
                     float(_ev_attr(ev, ('x',), 0.0)), float(_ev_attr(ev, ('y',), 0.0)))]
        if t == pg.JOYDEVICEADDED:
            try:
                if not self.ctl.is_controller(ev.device_index):
                    name = pg.joystick.Joystick(ev.device_index).get_name()
                    return [('error', f'{name} is not a controller SDL knows the buttons of; it is not used')]
            except Exception:
                pass
        return []


# ── macOS ─────────────────────────────────────────────────────────────────

ASK_INPUT_MONITORING_ENV = 'LRD_PAD_ASK_INPUT_MONITORING'
_IOKIT = '/System/Library/Frameworks/IOKit.framework/IOKit'


def input_monitoring():
    """macOS's Input Monitoring for this app: 'granted', 'denied',
    'unknown', or None off macOS. Read only (for the log)."""
    if sys.platform != 'darwin':
        return None
    try:
        import ctypes
        iokit = ctypes.cdll.LoadLibrary(_IOKIT)
        fn = iokit.IOHIDCheckAccess
        fn.argtypes = [ctypes.c_uint32]
        fn.restype = ctypes.c_uint32
        # kIOHIDRequestTypeListenEvent = 1; kIOHIDAccessTypeGranted = 0,
        # Denied = 1, Unknown = 2
        return {0: 'granted', 1: 'denied'}.get(int(fn(1)), 'unknown')
    except Exception:
        return 'unknown'


def request_input_monitoring():
    """Put up macOS's Input Monitoring question (IOHIDRequestAccess, with
    ctypes: nothing to bundle). True if granted; macOS shows its question
    only while the app has no answer yet."""
    import ctypes
    iokit = ctypes.cdll.LoadLibrary(_IOKIT)
    fn = iokit.IOHIDRequestAccess
    fn.argtypes = [ctypes.c_uint32]
    fn.restype = ctypes.c_bool
    return bool(fn(1))           # kIOHIDRequestTypeListenEvent


def ask_input_monitoring_once(link, env=None, platform=None, request=None):
    """The first reader ever on a Mac asks, when the server says to.
    Returns the message sent, or None."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform != 'darwin' or env.get(ASK_INPUT_MONITORING_ENV) != '1':
        return None
    try:
        granted = (request or request_input_monitoring)()
    except Exception:
        granted = False
    msg = {'t': 'input_monitoring_asked', 'granted': bool(granted)}
    if link is not None:
        link.send(msg)
    return msg


class _MacRunLoop:
    """SDL's video driver is the dummy one here, so nothing else turns the
    main run loop: a controller macOS's own controller framework reports is
    announced through it. One turn per loop of the reader."""

    def __init__(self):
        self.fn = None
        if sys.platform != 'darwin':
            return
        try:
            import ctypes
            cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            self.mode = ctypes.c_void_p.in_dll(cf, 'kCFRunLoopDefaultMode')
            fn = cf.CFRunLoopRunInMode
            fn.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
            fn.restype = ctypes.c_int32
            self.fn = fn
        except Exception:
            self.fn = None

    def turn(self):
        if self.fn is not None:
            try:
                self.fn(self.mode, 0.0, True)
            except Exception:
                self.fn = None


# ── the link to the server ────────────────────────────────────────────────

class ServerLink:
    """JSON lines to the server's socket on 127.0.0.1. gone is True once
    the server closed it (the app quit): the reader then exits. watched is
    the server's last word on whether a page has the IDM Locator tab open
    (False until it says)."""

    def __init__(self, port, token, timeout=5.0):
        self.sock = socket.create_connection(('127.0.0.1', int(port)), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(timeout)
        self.token = token
        self.timeout = timeout
        self.gone = False
        self.watched = False
        self._inbox = b''

    def send(self, msg):
        if self.gone:
            return False
        try:
            self.sock.sendall((json.dumps(msg, separators=(',', ':')) + '\n').encode('utf-8'))
            return True
        except OSError:
            self.gone = True
            return False

    def alive(self):
        """False once the server end closed (a read of nothing). Takes in
        what the server sent meanwhile (read_lines)."""
        if self.gone:
            return False
        try:
            self.sock.setblocking(False)
            try:
                while True:
                    data = self.sock.recv(4096)
                    if data == b'':
                        self.gone = True
                        break
                    self._inbox += data
                    if len(self._inbox) > 65536:     # never a server of ours
                        self._inbox = b''
            finally:
                self.sock.settimeout(self.timeout)
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            self.gone = True
        self.read_lines()
        return not self.gone

    def read_lines(self):
        """The whole lines in the inbox: a watch line sets watched."""
        *lines, self._inbox = self._inbox.split(b'\n')
        for raw in lines:
            try:
                msg = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(msg, dict) and msg.get('t') == 'watch':
                self.watched = bool(msg.get('on'))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ── test mode: print, send nothing ────────────────────────────────────────

class TestPrinter:
    def __init__(self, raw=False, out=None):
        self.out = out or sys.stdout
        self.raw = raw
        self._axis = {}
        self._glide_at = {}

    def line(self, text):
        print(time.strftime('%H:%M:%S') + '  ' + text, file=self.out, flush=True)

    def note(self, note, now):
        kind = note[0]
        if kind == 'added':
            p = note[1]
            self.line(f'CONNECTED  {p.name}  ({BATTERY_WORDS.get(p.battery, "battery " + str(p.battery))}, '
                      f'touchpad {"yes" if p.touchpad else "not yet seen"})')
        elif kind == 'removed':
            self.line(f'DISCONNECTED  {note[1].name}')
        elif kind == 'button':
            _, p, std, down = note
            self.line(f'button  {STANDARD_NAMES[std]:<18} {"DOWN" if down else "up"}  (standard {std})')
        elif kind == 'ignored':
            self.line(f'button  {note[2]} (the app does nothing with it)')
        elif kind == 'glide':
            _, p, dx, dy = note
            if now - self._glide_at.get(p.id, 0.0) >= 0.1:
                self._glide_at[p.id] = now
                self.line(f'touch   glide dx {dx:+.4f}  dy {dy:+.4f}')
        elif kind == 'error':
            self.line(note[1])

    def axes(self, pad):
        for i, v in enumerate(pad.axes):
            last = self._axis.get((pad.id, i), 0.0)
            if abs(v - last) >= 0.2 or (abs(v) < 0.05 and abs(last) >= 0.05):
                self._axis[(pad.id, i)] = 0.0 if abs(v) < 0.05 else v
                self.line(f'axis    {["left stick x", "left stick y", "right stick x", "right stick y"][i]:<14} {v:+.2f}')
        for i in (LT, RT):
            v = pad.buttons[i]
            last = self._axis.get((pad.id, 'b', i), 0.0)
            if abs(v - last) >= 0.2 or (v < 0.05 <= last):
                self._axis[(pad.id, 'b', i)] = 0.0 if v < 0.05 else v
                self.line(f'trigger {STANDARD_NAMES[i]:<14} {v:.2f}')


def _windows_console():
    """The frozen Windows app has no console: test mode opens one, unless
    it was started with its output sent somewhere (a file, as the release
    build's check does)."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    if sys.stdout is not None:
        return
    try:
        import ctypes
        ctypes.windll.kernel32.AllocConsole()
        sys.stdout = open('CONOUT$', 'w', buffering=1, encoding='utf-8')
        sys.stderr = sys.stdout
    except Exception:
        pass


# ── the loop ──────────────────────────────────────────────────────────────

def loop_wait_ms(norm, link):
    """Quick while a controller is connected and a page has the IDM Locator
    tab open (test mode: while a controller is connected); slow otherwise."""
    if norm.pads and (link is None or link.watched):
        return ACTIVE_WAIT_MS
    return IDLE_WAIT_MS


def run(link=None, test=None, clock=time.monotonic, stop_after=None):
    """Read controllers until the server goes away (or Ctrl+C in test
    mode). link: a ServerLink (None in test mode); test: a TestPrinter."""
    try:
        pygame, controller = load_pygame()
    except Exception as exc:
        why = f'{type(exc).__name__}: {exc}'
        if link:
            link.send({'t': 'unavailable', 'token': link.token, 'why': why})
        if test:
            test.line(f'pygame (SDL) could not be loaded: {why}')
        return EXIT_UNAVAILABLE
    sdl = '.'.join(str(n) for n in pygame.get_sdl_version())
    pads = SdlPads(pygame, controller)
    try:
        pads.start()
    except Exception as exc:
        why = f'SDL could not start: {type(exc).__name__}: {exc}'
        if link:
            link.send({'t': 'unavailable', 'token': link.token, 'why': why})
        if test:
            test.line(why)
        return EXIT_UNAVAILABLE
    if link:
        link.send({'t': 'hello', 'token': link.token, 'pygame': pygame.version.ver, 'sdl': sdl})
        ask_input_monitoring_once(link)
    if test:
        test.line(f'Controller test: pygame {pygame.version.ver}, SDL {sdl}. Nothing is sent to the app. Ctrl+C stops.')
        test.line('Pair a PlayStation or Xbox controller, press its buttons and slide a finger on the touchpad.')
    norm = PadNormaliser()
    runloop = _MacRunLoop()
    perm = input_monitoring()
    sent_status = None
    battery_at = perm_at = clock()
    started = clock()
    if test and perm == 'denied':
        test.line('macOS: Input Monitoring is off for this app. If no controller shows, turn it on in '
                  'System Settings, Privacy and Security, Input Monitoring.')
    try:
        while True:
            now = clock()
            runloop.turn()
            for ev in pygame.event.get():
                if test and test.raw and pygame.JOYAXISMOTION <= ev.type <= pygame.JOYDEVICEREMOVED:
                    test.line(f'raw     {pygame.event.event_name(ev.type)} {ev.dict}')
                for tup in pads.events(ev):
                    if tup[0] == 'error':
                        if test:
                            test.note(tup, now)
                        continue
                    for note in norm.handle(tup):
                        if test:
                            test.note(note, now)
            if now - battery_at >= BATTERY_EVERY_S:
                battery_at = now
                for pad in norm.pads.values():
                    pad.battery = pads.battery(pad.id)
            if perm is not None and not norm.pads and now - perm_at >= PERMISSION_EVERY_S:
                perm_at = now
                perm = input_monitoring()
            status = norm.status(perm)
            if status != sent_status:
                sent_status = status
                if link and not link.send(status):
                    return 0
            for pad in norm.pads.values():
                if test:
                    test.axes(pad)
                if pad.due(now):
                    msg = pad.take_state(now)
                    if link and not link.send(msg):
                        return 0
            if link and not link.alive():
                return 0
            if stop_after is not None and now - started >= stop_after:
                return 0
            pygame.time.wait(loop_wait_ms(norm, link))
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog='native_pad_reader',
                                 description='Reads a game controller for the IDM Locator.')
    ap.add_argument('--pad-reader', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--test', action='store_true',
                    help='print every controller event and send nothing')
    ap.add_argument('--raw', action='store_true', help='with --test: SDL joystick events too')
    ap.add_argument('--seconds', type=float, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.test:
        _windows_console()
        return run(test=TestPrinter(raw=args.raw), stop_after=args.seconds)
    port = os.environ.get('LRD_PAD_PORT')
    token = os.environ.get('LRD_PAD_TOKEN', '')
    if not port:
        print('native_pad_reader: started without the app (no LRD_PAD_PORT); try --test', file=sys.stderr)
        return 2
    try:
        link = ServerLink(port, token)
    except OSError:
        return 0         # the server is not there: nothing to report to
    try:
        return run(link=link, stop_after=args.seconds)
    finally:
        link.close()


if __name__ == '__main__':
    sys.exit(main())
