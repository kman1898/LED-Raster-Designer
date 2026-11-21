"""The computer's game controller read natively (src/native_pad_reader.py,
src/native_pad.py) for the IDM Locator (owner, 2026-11-17).

What this file pins, with no controller and no browser:

* The reader's normalisation: SDL's controller buttons and axes come out in
  the browser's standard layout (the numbers app-idm-gamepad.js reads), the
  triggers as buttons 6 and 7, the touchpad's click and the mute button
  dropped; a finger's slide comes out as how far it moved (the height
  scaled to the width), a second finger or a jump is not a slide, and the
  first finger lifted hands the glide to the one still down. A held state
  goes out again 30 times a second; a slide is sent once.
* pygame's events turned into those tuples (a stand-in pygame).
* The process: started, its hello checked, its messages passed on; stopped
  on quit; started again when it dies, a bounded number of times;
  "unavailable", and never retried, when pygame cannot load; never started
  at all with pygame missing; only our own reader (its token) can say
  "unavailable"; the reader leaves by itself when the app's end of its
  socket closes. The frozen app runs its own executable with --pad-reader,
  and the launcher hands that flag over before anything else.
* Idle: the reader hears whether a page has the IDM Locator tab open and
  polls quickly only with a controller and such a page; SDL leaves
  Windows' timer resolution alone.
* The bridge: only a page on this computer hears of the controller; the
  states go to ONE page, the one that last opened the IDM Locator tab, and
  a page that closes the tab (or loses the controller to another) gets
  nothing more and is told to let go. A change of target and a change in
  macOS's Input Monitoring go to the log.
* On a Mac the Input Monitoring question goes up once ever, the app's
  settings note it, and no reader asks again (owner, 2026-11-17); never
  off a Mac. It goes up only when a controller connects that macOS keeps
  from the reader (owner, 2026-11-18): never at the start, never with no
  controller, never for a controller SDL reads, never with the registry
  unreadable; a refused controller still there when the permission turns
  on gets a fresh reader.
* The spec keeps SDL and what it links to, and leaves pygame's other
  libraries, its font and its icon out.
* Settings saves from the reader's thread and the launcher's never meet
  half way.

Run locally:
    python -m pytest tests/test_native_pad.py -v -n 4 --dist loadfile
"""
import ast
import json
import os
import secrets
import socket
import subprocess
import sys
import textwrap
import time

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import native_pad  # noqa: E402
import native_pad_reader as reader  # noqa: E402
from native_pad_reader import PadNormaliser  # noqa: E402

READER = os.path.join(SRC, 'native_pad_reader.py')


def _wait(cond, timeout=15.0, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


# ── normalisation ─────────────────────────────────────────────────────────

def _pad(norm=None, name='DualSense Wireless Controller'):
    norm = norm or PadNormaliser()
    norm.handle(('added', 7, name, 'full'))
    return norm, norm.pads[7]


def test_every_sdl_button_lands_on_its_standard_number():
    norm, pad = _pad()
    # SDL a b x y back guide start ls rs lb rb up down left right
    want = {0: 0, 1: 1, 2: 2, 3: 3, 4: 8, 5: 16, 6: 9, 7: 10, 8: 11, 9: 4, 10: 5,
            11: 12, 12: 13, 13: 14, 14: 15}
    for sdl, std in want.items():
        notes = norm.handle(('button', 7, sdl, True))
        assert notes == [('button', pad, std, True)]
        assert pad.buttons[std] == 1.0
        assert sum(pad.buttons) == 1.0, (sdl, pad.buttons)
        norm.handle(('button', 7, sdl, False))
        assert sum(pad.buttons) == 0.0


def test_the_touchpad_click_and_the_mute_button_do_nothing():
    norm, pad = _pad()
    pad.take_state(0.0)
    assert norm.handle(('button', 7, reader.SDL_TOUCHPAD_CLICK, True)) == [('ignored', pad, 'touchpad click')]
    assert norm.handle(('button', 7, 15, True)) == [('ignored', pad, 'misc1')]
    assert sum(pad.buttons) == 0.0
    assert not pad.dirty and not pad.due(1.0)
    msg = pad.take_state(1.0)
    assert len(msg['buttons']) == 17 and not any(msg['buttons'])


def test_sticks_are_axes_and_triggers_are_buttons_six_and_seven():
    norm, pad = _pad()
    norm.handle(('axis', 7, 0, 32767))
    norm.handle(('axis', 7, 1, -32768))
    norm.handle(('axis', 7, 3, 16384))
    norm.handle(('axis', 7, 4, 32767))     # left trigger
    norm.handle(('axis', 7, 5, 8000))      # right trigger, a touch
    assert pad.axes[0] == 1.0 and pad.axes[1] == -1.0
    assert abs(pad.axes[3] - 0.5) < 0.01
    assert pad.buttons[reader.LT] == 1.0
    assert 0.2 < pad.buttons[reader.RT] < 0.3
    msg = pad.take_state(0.0)
    assert msg['t'] == 'state' and msg['id'] == 7
    assert msg['axes'][0] == 1.0 and msg['buttons'][6] == 1.0


def test_a_small_stick_wobble_waits_for_the_next_send():
    norm, pad = _pad()
    pad.take_state(0.0)
    norm.handle(('axis', 7, 0, 300))
    assert not pad.dirty
    norm.handle(('axis', 7, 0, 3000))
    assert pad.dirty and not pad.urgent


def test_a_slide_is_the_distance_the_finger_moved_height_scaled():
    norm, pad = _pad()
    pad.take_state(0.0)
    assert norm.handle(('touch', 7, 'down', 0, 0.50, 0.50)) == []
    notes = norm.handle(('touch', 7, 'motion', 0, 0.60, 0.70))
    assert notes and notes[0][0] == 'glide'
    assert pad.glide == pytest.approx([0.10, 0.20 * reader.TOUCH_ASPECT])
    norm.handle(('touch', 7, 'motion', 0, 0.55, 0.70))
    assert pad.glide == pytest.approx([0.05, 0.10])
    msg = pad.take_state(1.0)
    assert msg['touch'] == pytest.approx([0.05, 0.10])
    # sent once: the next state has no slide in it
    assert pad.take_state(2.0)['touch'] == [0.0, 0.0]


def test_a_jump_or_a_second_finger_is_not_a_slide_and_the_first_lift_hands_over():
    norm, pad = _pad()
    norm.handle(('touch', 7, 'down', 0, 0.2, 0.2))
    norm.handle(('touch', 7, 'down', 1, 0.8, 0.8))
    norm.handle(('touch', 7, 'motion', 1, 0.9, 0.9))      # not the gliding finger
    assert pad.glide == [0.0, 0.0]
    norm.handle(('touch', 7, 'motion', 0, 0.9, 0.2))      # a glitch-sized jump
    assert pad.glide == [0.0, 0.0]
    norm.handle(('touch', 7, 'up', 0, 0.9, 0.2))
    assert pad.primary == 1
    norm.handle(('touch', 7, 'motion', 1, 0.95, 0.9))
    assert pad.glide == pytest.approx([0.05, 0.0])
    norm.handle(('touch', 7, 'up', 1, 0.95, 0.9))
    assert pad.primary is None and not pad.fingers


def test_a_held_state_goes_out_thirty_times_a_second_and_a_rest_does_not():
    norm, pad = _pad()
    assert pad.due(0.0)                         # the first state, at once
    pad.take_state(0.0)
    assert not pad.due(5.0)                     # nothing held: quiet
    norm.handle(('button', 7, 11, True))        # D-pad up
    assert pad.due(5.0)                         # a press: at once
    pad.take_state(5.0)
    assert not pad.due(5.01)
    assert pad.due(5.0 + reader.RESEND_HELD_S + 1e-6)  # still held: again
    norm.handle(('button', 7, 11, False))
    assert pad.due(5.02)                        # the release: at once
    pad.take_state(5.02)
    assert not pad.due(9.0)


def test_status_names_the_pads_battery_and_touchpad():
    norm, pad = _pad()
    norm.handle(('added', 9, 'Xbox Wireless Controller', 'wired'))
    st = norm.status('denied')
    assert st == {'t': 'status', 'inputMonitoring': 'denied', 'pads': [
        {'id': 7, 'name': 'DualSense Wireless Controller', 'battery': 'full', 'touchpad': True},
        {'id': 9, 'name': 'Xbox Wireless Controller', 'battery': 'wired', 'touchpad': False}]}
    norm.handle(('removed', 9))
    assert [p['id'] for p in norm.status()['pads']] == [7]
    # a touch shows a pad has a touchpad whatever its name
    norm.handle(('added', 4, 'Pad', 'unknown'))
    norm.handle(('touch', 4, 'down', 0, 0.1, 0.1))
    assert norm.pads[4].touchpad


def test_pygame_events_become_the_normaliser_s_tuples():
    class Ev:
        def __init__(self, type, **kw):
            self.type = type
            self.__dict__.update(kw)

    class Joy:
        def get_instance_id(self):
            return 3

        def get_name(self):
            return 'Joy'

        def get_power_level(self):
            return 'medium'

    class Ctl:
        rumbled = []

        def __init__(self, index):
            self.name = 'DualSense Wireless Controller'

        def as_joystick(self):
            return Joy()

        def rumble(self, *a):
            Ctl.rumbled.append(a)

        def quit(self):
            pass

    class FakeController:
        Controller = Ctl

        @staticmethod
        def is_controller(i):
            return True

    names = ['CONTROLLERDEVICEADDED', 'CONTROLLERDEVICEREMOVED', 'CONTROLLERBUTTONDOWN',
             'CONTROLLERBUTTONUP', 'CONTROLLERAXISMOTION', 'CONTROLLERTOUCHPADDOWN',
             'CONTROLLERTOUCHPADMOTION', 'CONTROLLERTOUCHPADUP', 'JOYDEVICEADDED']
    pg = type('pg', (), {n: 100 + i for i, n in enumerate(names)})
    sdl = reader.SdlPads(pg, FakeController)
    assert sdl.events(Ev(pg.CONTROLLERDEVICEADDED, device_index=0)) == [
        ('added', 3, 'DualSense Wireless Controller', 'medium')]
    assert Ctl.rumbled, 'the silent rumble that asks for the touchpad report'
    assert sdl.events(Ev(pg.CONTROLLERBUTTONDOWN, instance_id=3, button=0)) == [('button', 3, 0, True)]
    assert sdl.events(Ev(pg.CONTROLLERBUTTONUP, instance_id=3, button=20)) == [('button', 3, 20, False)]
    assert sdl.events(Ev(pg.CONTROLLERAXISMOTION, instance_id=3, axis=1, value=-500)) == [('axis', 3, 1, -500.0)]
    assert sdl.events(Ev(pg.CONTROLLERTOUCHPADMOTION, instance_id=3, touch_id=0, finger_id=1, x=0.25, y=0.5,
                         pressure=1.0)) == [('touch', 3, 'motion', 1, 0.25, 0.5)]
    assert sdl.events(Ev(pg.CONTROLLERDEVICEREMOVED, instance_id=3)) == [('removed', 3)]


# ── the process ───────────────────────────────────────────────────────────

FAKE_READER = textwrap.dedent('''
    import json, os, socket, sys, time
    mode = sys.argv[1]
    if mode == 'crash':
        sys.exit(1)
    if mode == 'unavailable':
        sys.exit(3)
    s = socket.create_connection(('127.0.0.1', int(os.environ['LRD_PAD_PORT'])))
    def send(m):
        s.sendall((json.dumps(m) + '\\n').encode())
    if mode in ('says_unavailable', 'spoofs_unavailable'):
        token = os.environ['LRD_PAD_TOKEN'] if mode == 'says_unavailable' else 'wrong'
        send({'t': 'unavailable', 'token': token, 'why': 'no SDL here'})
        s.close()
        sys.exit(1)
    send({'t': 'hello', 'token': 'wrong' if mode == 'badtoken' else os.environ['LRD_PAD_TOKEN']})
    send({'t': 'status', 'pads': [{'id': 1, 'name': 'Fake Pad', 'battery': 'full', 'touchpad': True}],
          'inputMonitoring': None})
    send({'t': 'state', 'id': 1, 'buttons': [1] + [0] * 16, 'axes': [0, 0, 0, 0], 'touch': [0.1, 0]})
    if mode == 'once':
        time.sleep(0.05)
        sys.exit(1)
    while True:
        d = s.recv(64)
        if not d:
            break
''')


@pytest.fixture
def fake_reader(tmp_path):
    path = tmp_path / 'fake_reader.py'
    path.write_text(FAKE_READER, encoding='utf-8')
    return lambda mode: [sys.executable, str(path), mode]


def _sup(command, **kw):
    msgs, logs = [], []
    kw.setdefault('backoff', (0.01,))
    sup = native_pad.PadReaderSupervisor(msgs.append, log=lambda a, d=None: logs.append((a, d)),
                                         command=command, available=lambda: True, **kw)
    return sup, msgs, logs


def test_started_its_messages_passed_on_and_stopped_on_quit(fake_reader):
    sup, msgs, logs = _sup(fake_reader('stay'))
    try:
        assert sup.start()
        assert _wait(lambda: any(m.get('t') == 'state' for m in msgs))
        assert sup.state == 'running'
        kinds = [m['t'] for m in msgs]
        assert kinds.index('reader') < kinds.index('status') < kinds.index('state')
        assert 'hello' not in kinds          # checked, not passed on
        proc = sup.proc
        assert proc.poll() is None
    finally:
        sup.stop()
    assert proc.poll() is not None, 'the reader ends with the app'
    assert sup.state == 'off'
    assert not sup._thread.is_alive()
    assert ('native_pad_reader', {'state': 'stopped'}) in logs


def test_a_reader_that_dies_is_started_again_a_few_times_then_left_off(fake_reader):
    sup, msgs, logs = _sup(fake_reader('crash'), max_restarts=2)
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'failed')
        assert sup.starts == 3              # the first and two more
        exits = [d for a, d in logs if d.get('state') == 'exited']
        assert len(exits) == 2 and exits[0]['code'] == 1
        assert any(d.get('state') == 'failed' for a, d in logs)
        assert msgs[-1] == {'t': 'reader', 'state': 'failed', 'why': 'it stopped 3 times'}
    finally:
        sup.stop()
    assert sup.state == 'failed'           # a stop keeps why it is down


def test_a_reader_that_ran_a_while_starts_its_count_again(fake_reader):
    sup, msgs, logs = _sup(fake_reader('once'), max_restarts=1, steady_s=0.0)
    try:
        sup.start()
        assert _wait(lambda: sup.starts >= 4)
        assert sup.state != 'failed'
    finally:
        sup.stop()


def test_a_reader_with_another_token_is_not_listened_to(fake_reader):
    sup, msgs, logs = _sup(fake_reader('badtoken'), max_restarts=0)
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'failed')
        assert not [m for m in msgs if m['t'] in ('status', 'state')]
    finally:
        sup.stop()


def test_no_pygame_means_unavailable_and_never_retried(fake_reader):
    sup, msgs, logs = _sup(fake_reader('unavailable'))
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'unavailable')
        time.sleep(0.3)
        assert sup.starts == 1
    finally:
        sup.stop()
    # and found missing before any process: none is started
    sup2, msgs2, logs2 = _sup(fake_reader('stay'))
    sup2.available = lambda: False
    assert sup2.start() is False
    assert sup2.state == 'unavailable' and sup2.starts == 0 and sup2.proc is None
    assert msgs2 == [{'t': 'reader', 'state': 'unavailable', 'why': 'pygame is not installed'}]


def test_only_our_own_reader_can_say_unavailable(fake_reader):
    """A line before the hello without the reader's token is not ours: it
    is not taken as "unavailable", and the reader counts as having died."""
    sup, msgs, logs = _sup(fake_reader('says_unavailable'))
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'unavailable')
        assert sup.why == 'no SDL here' and sup.starts == 1
    finally:
        sup.stop()
    sup, msgs, logs = _sup(fake_reader('spoofs_unavailable'), max_restarts=1)
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'failed')
        assert sup.starts == 2 and 'no SDL here' not in sup.why
        assert not [m for m in msgs if m.get('state') == 'unavailable']
    finally:
        sup.stop()


def test_a_reader_that_said_unavailable_and_exited_before_the_accept_is_heard(fake_reader):
    """A reader can connect, say "unavailable" and exit before the
    supervisor gets round to accepting it (a slow machine: CI's Windows
    runner, 2026-11-21). Its line is waiting in the listener's backlog; the
    supervisor still reads it rather than seeing only a dead process and
    starting the reader again."""
    sup, msgs, logs = _sup(fake_reader('says_unavailable'))
    accept = sup._accept

    def late_accept(listener, proc):
        proc.wait(15)   # the reader is gone before the first accept
        return accept(listener, proc)

    sup._accept = late_accept
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'unavailable')
        assert sup.why == 'no SDL here' and sup.starts == 1
    finally:
        sup.stop()


def test_the_reader_hears_whether_a_page_has_the_tab_open(tmp_path):
    script = tmp_path / 'listening_reader.py'
    script.write_text(textwrap.dedent('''
        import json, os, socket, sys
        s = socket.create_connection(('127.0.0.1', int(os.environ['LRD_PAD_PORT'])))
        s.sendall((json.dumps({'t': 'hello', 'token': os.environ['LRD_PAD_TOKEN']}) + '\\n').encode())
        with open(sys.argv[1], 'a', encoding='utf-8') as out:
            for line in s.makefile('rb'):
                out.write(line.decode())
                out.flush()
    '''), encoding='utf-8')
    record = tmp_path / 'heard.txt'
    sup, msgs, logs = _sup([sys.executable, str(script), str(record)])
    sup.set_watched(True)          # before the reader is there: said on its hello
    heard = lambda: [json.loads(x) for x in record.read_text(encoding='utf-8').splitlines()] \
        if record.exists() else []
    try:
        sup.start()
        assert _wait(lambda: heard() == [{'t': 'watch', 'on': True}])
        sup.set_watched(False)
        assert _wait(lambda: len(heard()) == 2)
    finally:
        sup.stop()
    assert heard() == [{'t': 'watch', 'on': True}, {'t': 'watch', 'on': False}]


def test_the_reader_polls_quickly_only_with_a_pad_and_a_page_on_the_tab():
    assert reader.SDL_HINTS['SDL_TIMER_RESOLUTION'] == '0'
    assert reader.ACTIVE_WAIT_MS == 8 and reader.IDLE_WAIT_MS == 100
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    link = reader.ServerLink(listener.getsockname()[1], 'tok')
    conn, _ = listener.accept()
    try:
        norm = PadNormaliser()
        wait = lambda: reader.loop_wait_ms(norm, link)
        assert link.alive() and not link.watched
        assert wait() == reader.IDLE_WAIT_MS                 # no pad, no page
        norm.handle(('added', 1, 'DualSense Wireless Controller', 'full'))
        assert wait() == reader.IDLE_WAIT_MS                 # a pad, no page
        conn.sendall(b'{"t": "watch", "on": true}\n{"t": "wat')
        assert _wait(lambda: link.alive() and link.watched)
        assert wait() == reader.ACTIVE_WAIT_MS               # a pad and a page
        conn.sendall(b'ch", "on": false}\n')                 # the rest of the line
        assert _wait(lambda: link.alive() and not link.watched)
        assert wait() == reader.IDLE_WAIT_MS
        conn.sendall(b'{"t": "watch", "on": true}\n')
        assert _wait(lambda: link.alive() and link.watched)
        norm.handle(('removed', 1))
        assert wait() == reader.IDLE_WAIT_MS                 # a page, no pad
        # test mode: no app, quick while a pad is there
        norm.handle(('added', 2, 'Xbox Wireless Controller', 'full'))
        assert reader.loop_wait_ms(norm, None) == reader.ACTIVE_WAIT_MS
        conn.close()
        assert _wait(lambda: not link.alive())
    finally:
        link.close()
        listener.close()


def test_the_real_reader_without_pygame_says_so_and_exits_3():
    code = ("import sys, runpy; sys.modules['pygame'] = None; "
            f"sys.argv = [{READER!r}]; runpy.run_path({READER!r}, run_name='__main__')")
    sup, msgs, logs = _sup([sys.executable, '-c', code])
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'unavailable')
        assert 'ImportError' in sup.why or 'ModuleNotFoundError' in sup.why, sup.why
        assert sup.starts == 1
    finally:
        sup.stop()


def test_the_real_reader_runs_with_no_controller_and_leaves_when_the_app_goes():
    pytest.importorskip('pygame')
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(30)
    token = secrets.token_hex(8)
    env = dict(os.environ, LRD_PAD_PORT=str(listener.getsockname()[1]), LRD_PAD_TOKEN=token)
    proc = subprocess.Popen([sys.executable, READER], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        conn, _ = listener.accept()
        f = conn.makefile('rb')
        hello = json.loads(f.readline())
        assert hello['t'] == 'hello' and hello['token'] == token
        assert hello['sdl'].startswith('2.')
        status = json.loads(f.readline())
        assert status['t'] == 'status' and status['pads'] == []
        assert proc.poll() is None
        # the app quits without a word: its end closes
        f.close()
        conn.close()
        assert proc.wait(10) == 0
    finally:
        listener.close()
        if proc.poll() is None:
            proc.kill()


def test_test_mode_prints_and_sends_nothing():
    pytest.importorskip('pygame')
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    env.pop('LRD_PAD_PORT', None)
    out = subprocess.run([sys.executable, READER, '--test', '--seconds', '0.5'], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert 'Controller test: pygame' in out.stdout
    assert 'Nothing is sent to the app' in out.stdout


def test_without_the_app_the_reader_does_not_run():
    env = dict(os.environ)
    env.pop('LRD_PAD_PORT', None)
    out = subprocess.run([sys.executable, READER], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 2 and '--test' in out.stderr


def test_the_frozen_app_runs_itself_with_the_flag(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert native_pad.reader_command() == [sys.executable, '--pad-reader']
    monkeypatch.delattr(sys, 'frozen')
    assert native_pad.reader_command() == [sys.executable, READER]


def test_the_launcher_hands_the_flag_over_before_anything_else(monkeypatch):
    launcher_window = pytest.importorskip('launcher_window')
    seen = []
    monkeypatch.setattr(reader, 'main', lambda argv=None: seen.append(argv) or 0)
    monkeypatch.setattr(launcher_window, '_install_crash_logger',
                        lambda: pytest.fail('the reader must not start the launcher'))
    monkeypatch.setattr(sys, 'argv', ['LED Raster Designer', '--pad-reader', '--test'])
    with pytest.raises(SystemExit) as ex:
        launcher_window.main()
    assert ex.value.code == 0
    assert seen == [['--pad-reader', '--test']]


def test_the_reader_takes_the_flag_and_quits_quietly_with_no_server(monkeypatch):
    monkeypatch.setenv('LRD_PAD_PORT', '1')

    def no_server(*a, **k):
        raise OSError('no server')

    monkeypatch.setattr(reader, 'ServerLink', no_server)
    monkeypatch.setattr(reader, 'run', lambda **kw: pytest.fail('nothing to report to'))
    assert reader.main(['--pad-reader']) == 0


def test_start_reader_never_raises_and_stop_is_safe(monkeypatch):
    calls = []
    monkeypatch.setattr(native_pad, '_SUPERVISOR', None)

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError('no')

    monkeypatch.setattr(native_pad, 'PadReaderSupervisor', Boom)
    assert native_pad.start_reader(log=lambda a, d=None: calls.append((a, d))) is None
    assert calls and calls[0][1]['state'] == 'failed'
    native_pad.stop_reader()
    native_pad.stop_reader()


def test_on_a_mac_input_monitoring_is_asked_for_once_ever(fake_reader, tmp_path):
    """Owner, 2026-11-17: macOS asks the first time ever, then never again."""
    saved = []
    settings = {'port': 8050}
    env, asked = native_pad.input_monitoring_ask(settings, saved.append, platform='darwin')
    assert env == {reader.ASK_INPUT_MONITORING_ENV: '1'}
    # the reader asks when told to, on a Mac only
    calls = []
    msg = reader.ask_input_monitoring_once(None, env=env, platform='darwin',
                                           request=lambda: calls.append(1) or True)
    assert msg == {'t': 'input_monitoring_asked', 'granted': True} and calls == [1]
    assert reader.ask_input_monitoring_once(None, env=env, platform='win32', request=lambda: 1 / 0) is None
    assert reader.ask_input_monitoring_once(None, env={}, platform='darwin', request=lambda: 1 / 0) is None
    # the supervisor: the first reader is told, says it asked, the settings
    # note it; a reader started again is not told
    script = tmp_path / 'asking_reader.py'
    script.write_text(textwrap.dedent('''
        import json, os, socket, sys
        s = socket.create_connection(('127.0.0.1', int(os.environ['LRD_PAD_PORT'])))
        send = lambda m: s.sendall((json.dumps(m) + '\\n').encode())
        send({'t': 'hello', 'token': os.environ['LRD_PAD_TOKEN']})
        told = os.environ.get('LRD_PAD_ASK_INPUT_MONITORING') == '1'
        with open(sys.argv[1], 'a') as f:
            f.write('told\\n' if told else 'quiet\\n')
        if told:
            send({'t': 'input_monitoring_asked', 'granted': False})
        sys.exit(1)
    '''), encoding='utf-8')
    record = tmp_path / 'record.txt'
    msgs, logs = [], []
    sup = native_pad.PadReaderSupervisor(msgs.append, log=lambda a, d=None: logs.append((a, d)),
                                         command=[sys.executable, str(script), str(record)],
                                         available=lambda: True, backoff=(0.01,), max_restarts=2,
                                         extra_env=env, on_asked=asked)
    try:
        sup.start()
        assert _wait(lambda: sup.state == 'failed')
    finally:
        sup.stop()
    assert record.read_text().split() == ['told', 'quiet', 'quiet']
    assert settings[native_pad.ASKED_KEY] is True and saved == [settings]
    assert ('native_pad_input_monitoring', {'asked': True, 'granted': False}) in logs
    # asked once: never again, and never off a Mac
    assert native_pad.input_monitoring_ask(settings, saved.append, platform='darwin') == ({}, None)
    assert native_pad.input_monitoring_ask({}, saved.append, platform='win32') == ({}, None)
    assert native_pad.input_monitoring_ask(None, saved.append, platform='darwin') == ({}, None)


def test_the_reader_never_asks_at_the_start():
    """Owner, 2026-11-18: not at first launch and not on opening the IDM
    Locator tab. run() puts no question up itself; only AskOnConnect
    does, from inside the loop."""
    tree = ast.parse(open(READER, encoding='utf-8').read())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    called = {c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, 'attr', None)
              for c in ast.walk(run) if isinstance(c, ast.Call)}
    assert 'ask_input_monitoring_once' not in called
    assert 'request_input_monitoring' not in called
    assert 'AskOnConnect' in called and 'tick' in called


ASK_ENV = {reader.ASK_INPUT_MONITORING_ENV: '1'}
DUALSENSE = {'name': 'DualSense Wireless Controller', 'guarded': False}
GUARDED = {'name': 'Pad With Keys', 'guarded': True}


def _asker(registry, env=ASK_ENV, platform='darwin'):
    """An AskOnConnect over a stand-in registry (a list of lists, one per
    look; the last repeats) and a stand-in question."""
    asked = []
    looks = list(registry)

    def seen():
        item = looks.pop(0) if len(looks) > 1 else looks[0]
        if isinstance(item, Exception):
            raise item
        return item
    a = reader.AskOnConnect(None, env=env, platform=platform, seen=seen,
                            request=lambda: asked.append(1) or False)
    return a, asked


def test_the_question_waits_for_a_controller_macos_keeps_from_the_reader():
    """Apple's HID code: a process with no Input Monitoring is still told a
    device connected; only a keyboard, mouse or touchpad needs it to be
    opened. The reader asks when such a controller connects, once."""
    assert reader.GAME_USAGES == {(1, 4), (1, 5), (1, 8)}
    assert reader.GUARDED_USAGES == {(1, 6), (1, 2), (0x0D, 5)}
    step = reader.CONNECT_LOOK_S
    # nothing connected: looks, never asks, however long
    a, asked = _asker([[]])
    for i in range(30):
        assert a.tick(i * step, False) is None
    assert asked == [] and a.pending
    # one connects that macOS guards: asked at the next look, once
    a, asked = _asker([[], [], [GUARDED]])
    assert a.tick(0.0, False) is None
    assert a.tick(step / 2, False) is None                     # between looks: no read
    assert a.tick(step, False) is None
    assert a.tick(2 * step, False) == {'t': 'input_monitoring_asked', 'granted': False}
    assert asked == [1] and not a.pending
    for i in range(3, 20):
        assert a.tick(i * step, False) is None
    assert asked == [1]


def test_a_controller_the_reader_can_open_is_never_a_reason_to_ask():
    step = reader.CONNECT_LOOK_S
    # a game pad SDL reads: never asked
    a, asked = _asker([[DUALSENSE]])
    for i in range(30):
        assert a.tick(i * step, True) is None
    assert asked == [] and a.pending
    # one SDL still has not opened after the grace: asked, once
    a, asked = _asker([[DUALSENSE]])
    t = 0.0
    while t < reader.CONNECT_GRACE_S:
        assert a.tick(t, False) is None
        t += step
    assert a.tick(t, False) == {'t': 'input_monitoring_asked', 'granted': False}
    assert asked == [1]
    # SDL opening it inside the grace ends the wait; a later unplug and
    # replug starts it again
    a, asked = _asker([[DUALSENSE], [DUALSENSE], [], [DUALSENSE]])
    assert a.tick(0.0, False) is None
    assert a.tick(step, True) is None
    assert a.tick(2 * step, False) is None                     # unplugged
    assert a.tick(3 * step, False) is None                     # back: the wait starts over
    assert a.tick(3 * step + reader.CONNECT_GRACE_S - 0.01, False) is None
    assert asked == []


def test_no_question_off_a_mac_already_asked_or_with_the_registry_unreadable():
    for kw in ({'platform': 'win32'}, {'env': {}}):
        a, asked = _asker([[GUARDED]], **kw)
        assert not a.pending
        assert a.tick(0.0, False) is None and a.tick(10.0, False) is None
        assert asked == []
    # the registry cannot be read: never ask blind
    for broken in (None, OSError('no IOKit')):
        a, asked = _asker([broken, [GUARDED]])
        assert a.tick(0.0, False) is None
        assert not a.pending
        assert a.tick(10.0, False) is None
        assert asked == []
    # and off a Mac the registry reader says so without touching IOKit
    if sys.platform != 'darwin':
        assert reader.mac_game_controllers() is None


def test_permission_turned_on_with_a_refused_controller_gets_a_fresh_reader():
    there, none = (lambda: [GUARDED]), (lambda: [])
    restart = reader.restart_for_permission
    assert restart('unknown', 'granted', False, seen=there)
    assert restart('denied', 'granted', False, seen=there)
    assert not restart('unknown', 'granted', True, seen=there)     # SDL has it
    assert not restart('unknown', 'granted', False, seen=none)     # nothing connected
    assert not restart('granted', 'granted', False, seen=there)    # no change
    assert not restart('unknown', 'denied', False, seen=there)
    assert not restart(None, None, False, seen=there)              # off a Mac
    assert not restart('unknown', 'granted', False, seen=lambda: None)


def test_start_reader_passes_the_mac_question_on(monkeypatch):
    made = []

    class Fake:
        def __init__(self, on_message, **kw):
            made.append(kw)

        def start(self):
            return True

        def stop(self):
            pass

        def set_watched(self, on):
            pass

    monkeypatch.setattr(native_pad, '_SUPERVISOR', None)
    monkeypatch.setattr(native_pad, 'PadReaderSupervisor', Fake)
    monkeypatch.setattr(native_pad.sys, 'platform', 'darwin')
    try:
        sup = native_pad.start_reader(settings={}, save=lambda s: None)
        assert made[0]['extra_env'] == {reader.ASK_INPUT_MONITORING_ENV: '1'}
        assert callable(made[0]['on_asked'])
        assert native_pad.BRIDGE.on_watch.__self__ is sup     # the bridge tells this reader
    finally:
        native_pad.stop_reader()
    assert native_pad.BRIDGE.on_watch is None
    monkeypatch.setattr(native_pad, '_SUPERVISOR', None)
    try:
        native_pad.start_reader(settings={native_pad.ASKED_KEY: True}, save=lambda s: None)
        assert 'extra_env' not in made[1]
    finally:
        native_pad.stop_reader()


# ── the bridge ────────────────────────────────────────────────────────────

class Sent:
    def __init__(self):
        self.out = []

    def __call__(self, event, data, to=None):
        self.out.append((event, to, data))

    def to(self, sid, event=None):
        return [d for e, t, d in self.out if t == sid and (event is None or e == event)]


STATE = {'t': 'state', 'id': 1, 'buttons': [0] * 12 + [1] + [0] * 4, 'axes': [0, 0, 0, 0], 'touch': [0.02, 0]}


def _bridge():
    sent = Sent()
    return native_pad.NativePadBridge(emit=sent), sent


def test_states_go_to_the_one_page_that_last_opened_the_tab():
    b, sent = _bridge()
    b.watch('A', True)
    b.watch('B', False)          # another page on this computer, another tab
    b.handle(STATE)
    assert len(sent.to('A', 'native_pad_state')) == 1
    assert not sent.to('B', 'native_pad_state')
    got = sent.to('A', 'native_pad_state')[0]
    assert got['id'] == '1' and got['buttons'][12] == 1.0 and got['touch'] == [0.02, 0.0]
    # B opens the tab: B has it now, and A is told to let go
    b.watch('B', True)
    assert sent.to('A', 'native_pad_idle')
    b.handle(STATE)
    assert len(sent.to('A', 'native_pad_state')) == 1
    assert len(sent.to('B', 'native_pad_state')) == 1
    # A takes the focus with its tab open: back to A
    b.watch('A', True)
    b.handle(STATE)
    assert len(sent.to('A', 'native_pad_state')) == 2
    # B leaves; A closes its tab: nobody gets the controller
    b.forget('B')
    b.watch('A', False)
    assert b.target is None
    b.handle(STATE)
    assert len(sent.to('A', 'native_pad_state')) == 2


def test_status_goes_to_every_host_page_and_the_reader_down_clears_the_pads():
    logs = []
    b, sent = _bridge()
    b.log = lambda a, d=None: logs.append((a, d))
    b.watch('A', True)
    b.watch('B', False)
    b.handle({'t': 'reader', 'state': 'running'})
    b.handle({'t': 'status', 'pads': [{'id': 2, 'name': 'DualSense Wireless Controller', 'battery': 'low',
                                       'touchpad': True}], 'inputMonitoring': 'denied'})
    for sid in ('A', 'B'):
        st = sent.to(sid, 'native_pad_status')[-1]
        assert st['reader'] == 'running' and st['inputMonitoring'] == 'denied'
        assert st['pads'] == [{'id': '2', 'name': 'DualSense Wireless Controller', 'battery': 'low',
                               'touchpad': True}]
    assert ('native_pad_connected', {'name': 'DualSense Wireless Controller', 'battery': 'low'}) in logs
    b.handle({'t': 'reader', 'state': 'restarting', 'why': 'exited with 1'})
    assert sent.to('A', 'native_pad_status')[-1]['pads'] == []
    assert b.watch('C', False)['reader'] == 'restarting'


def test_a_target_change_and_input_monitoring_go_to_the_log_and_the_reader_hears():
    logs, said = [], []
    b, sent = _bridge()
    b.log = lambda a, d=None: logs.append((a, d))
    b.on_watch = said.append
    b.watch('AAAAAAAAAA', False)
    b.watch('AAAAAAAAAA', True)
    b.watch('BBBBBBBBBB', True)
    b.watch('AAAAAAAAAA', False)        # not the target: no change
    b.forget('BBBBBBBBBB')
    targets = [d for a, d in logs if a == 'native_pad_target']
    assert targets == [
        {'page': True, 'to': 'AAAAAA', 'from': None, 'on_tab': 1, 'pages': 1},
        {'page': True, 'to': 'BBBBBB', 'from': 'AAAAAA', 'on_tab': 2, 'pages': 2},
        {'page': False, 'to': None, 'from': 'BBBBBB', 'on_tab': 0, 'pages': 1},
    ]
    # the reader hears each change between "a page watches" and "none does"
    assert said == [False, True, False]
    # Input Monitoring: every change, denied too; the same value again is quiet
    for value in ('unknown', 'unknown', 'denied', 'granted', None):
        b.handle({'t': 'status', 'pads': [], 'inputMonitoring': value})
    assert [d for a, d in logs if a == 'native_pad_input_monitoring'] == [
        {'value': 'unknown', 'was': None}, {'value': 'denied', 'was': 'unknown'},
        {'value': 'granted', 'was': 'denied'}, {'value': None, 'was': 'granted'}]


def test_states_are_cleaned_before_a_page_sees_them():
    clean = native_pad.clean_state({'id': 5, 'buttons': [2, -1, 'x'], 'axes': [9, float('nan')],
                                    'touch': [0.5]})
    assert clean == {'id': '5', 'buttons': [1.0, 0.0, 0.0] + [0.0] * 14, 'axes': [1.0, 0.0, 0.0, 0.0],
                     'touch': [0.5, 0.0]}
    assert native_pad.clean_state({'id': None}) is None
    assert native_pad.clean_pads([{'id': 1, 'name': 'x' * 200, 'battery': 'nuclear'}, 'junk']) == [
        {'id': '1', 'name': 'x' * 80, 'battery': 'unknown', 'touchpad': False}]


@pytest.fixture
def bridge_clean():
    saved = (native_pad.BRIDGE.emit, native_pad.BRIDGE.log)
    native_pad.BRIDGE.reset()
    yield native_pad.BRIDGE
    native_pad.BRIDGE.reset()
    native_pad.BRIDGE.emit, native_pad.BRIDGE.log = saved


def test_over_the_socket_only_a_page_on_this_computer_is_heard(bridge_clean, monkeypatch):
    import app as app_module
    import routes_dialog
    # The socket test client brings no address: which machine each page is
    # on is said here (routes_dialog._is_same_machine is the real test).
    here = {'same': True}
    monkeypatch.setattr(routes_dialog, '_is_same_machine', lambda addr: here['same'])
    host = app_module.socketio.test_client(app_module.app)
    other = app_module.socketio.test_client(app_module.app)
    try:
        host.get_received()
        other.get_received()
        host.emit('native_pad_watch', {'idm': True})
        got = [r for r in host.get_received() if r['name'] == 'native_pad_status']
        assert got and got[0]['args'][0]['reader'] == 'off'
        # a tablet: never registered, never told
        here['same'] = False
        other.emit('native_pad_watch', {'idm': True})
        assert not [r for r in other.get_received() if r['name'] == 'native_pad_status']
        here['same'] = True
        assert len(bridge_clean.watchers) == 1
        bridge_clean.handle({'t': 'reader', 'state': 'running'})
        bridge_clean.handle({'t': 'status', 'pads': [{'id': 1, 'name': 'Pad'}]})
        bridge_clean.handle(STATE)
        h = host.get_received()
        assert [r['args'][0]['id'] for r in h if r['name'] == 'native_pad_state'] == ['1']
        assert [r['args'][0]['pads'] for r in h if r['name'] == 'native_pad_status'][-1][0]['name'] == 'Pad'
        assert not [r for r in other.get_received() if r['name'].startswith('native_pad')]
        # the page goes: forgotten
        host.disconnect()
        assert not bridge_clean.watchers and bridge_clean.target is None
    finally:
        for c in (host, other):
            if c.is_connected():
                c.disconnect()


# ── the build ─────────────────────────────────────────────────────────────

SPEC = os.path.join(SRC, 'led_raster_designer.spec')


def _spec_function(name):
    with open(SPEC, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {'os': os, 'sys': sys}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), SPEC, 'exec'), ns)
    return ns[name]


def test_the_spec_keeps_sdl_and_what_it_links_to_and_leaves_the_rest_out(capsys):
    keep = _spec_function('pygame_sdl_only')
    site = 'C:\\py\\Lib\\site-packages\\pygame\\'
    mac = '/py/site-packages/pygame/.dylibs/'
    binaries = [
        ('SDL2.dll', site + 'SDL2.dll', 'BINARY'),
        ('SDL2_ttf.dll', site + 'SDL2_ttf.dll', 'BINARY'),
        ('libpng16-16.dll', site + 'libpng16-16.dll', 'BINARY'),
        ('pygame/base.cp311-win_amd64.pyd', site + 'base.cp311-win_amd64.pyd', 'EXTENSION'),
        ('pygame/.dylibs/libSDL2-2.0.0.dylib', mac + 'libSDL2-2.0.0.dylib', 'BINARY'),
        ('pygame/.dylibs/libfreetype.6.dylib', mac + 'libfreetype.6.dylib', 'BINARY'),
        ('pygame/.dylibs/libz.1.3.dylib', mac + 'libz.1.3.dylib', 'BINARY'),
        ('pygame/.dylibs/libiconv.2.dylib', mac + 'libiconv.2.dylib', 'BINARY'),
        ('libpng16-16.dll', 'C:\\py\\Lib\\site-packages\\PIL\\libpng16-16.dll', 'BINARY'),
    ]
    # SDL needs a library of pygame's (and it needs another): both stay.
    # What links the font library is not in the bundle, so it goes.
    links = {
        site + 'SDL2.dll': {'kernel32.dll', 'user32.dll'},
        site + 'base.cp311-win_amd64.pyd': {'sdl2.dll', 'python311.dll'},
        mac + 'libSDL2-2.0.0.dylib': {'libsdl2-2.0.0.dylib', 'libiconv.2.dylib', 'corefoundation'},
        mac + 'libiconv.2.dylib': {'libiconv.2.dylib', 'libz.1.3.dylib', 'libsystem.b.dylib'},
        mac + 'libz.1.3.dylib': {'libz.1.3.dylib', 'libsystem.b.dylib'},
    }
    asked = []

    def linked(path):
        asked.append(path)
        return links[path]

    got = [b[0] for b in keep(binaries, linked)]
    assert got == [
        'pygame/base.cp311-win_amd64.pyd', 'libpng16-16.dll',
        'pygame/.dylibs/libiconv.2.dylib', 'pygame/.dylibs/libSDL2-2.0.0.dylib',
        'pygame/.dylibs/libz.1.3.dylib', 'SDL2.dll']
    assert len(asked) == len(set(asked)), 'each library is read once'
    out = capsys.readouterr().out
    assert 'left out libfreetype.6.dylib, libpng16-16.dll, sdl2_ttf.dll' in out, out
    # a library whose links cannot be read: everything of pygame's stays
    assert keep(binaries, lambda path: None) == binaries
    with open(SPEC, encoding='utf-8') as f:
        text = f.read()
    for name in ("'native_pad_reader'", "'pygame._sdl2.controller'", 'excludes=PYGAME_UNUSED',
                 'a.binaries = pygame_sdl_only(a.binaries)', 'a.datas = pygame_unused_datas(a.datas)'):
        assert name in text, name


def test_the_spec_leaves_pygame_s_font_and_icon_out():
    drop = _spec_function('pygame_unused_datas')
    datas = [
        ('pygame/freesansbold.ttf', '/py/pygame/freesansbold.ttf', 'DATA'),
        ('pygame/pygame_icon.bmp', '/py/pygame/pygame_icon.bmp', 'DATA'),
        ('pygame\\pygame_icon_mac.bmp', '/py/pygame/pygame_icon_mac.bmp', 'DATA'),
        ('static/fonts/freesansbold.ttf', 'static/fonts/freesansbold.ttf', 'DATA'),
        ('templates/index.html', 'templates/index.html', 'DATA'),
    ]
    assert [d[0] for d in drop(datas)] == ['static/fonts/freesansbold.ttf', 'templates/index.html']


def test_pygame_is_pinned_in_the_requirements():
    with open(os.path.join(SRC, 'requirements.txt'), encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith('#')]
    assert 'pygame==2.6.1' in lines
