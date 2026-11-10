"""Output to Display in the desktop app: native full-screen output windows.

The launcher's GUI loop owns the output windows (output_native.py), the
server opens them and carries their frames (routes_output.py). pywebview is
stood in for here; what is pinned:

* the displays are pywebview's own list, in its order, with each display's
  resolution as the OS shows it and its top-left corner (a Mac's bottom-up
  frames turned top-down), the main one marked;
* an output opens with create_window(screen=<the chosen display>) on /output
  with its feed id. macOS: the borderless window is laid over the display's
  whole frame once shown, above the menu bar (not macOS full screen, which
  never took on the window pywebview was still building). Windows: opened
  hidden, put on the display's
  own bounds, shown, then full screen (winforms' own screen placement is off
  when Windows scaling is not 100%);
* closing: from the dialog, from Esc in the output (the feed's close), or by
  the OS; each drops the output's frames;
* frames: the latest one only, long-polled by the window; a closed output
  answers 410 to its window and 404 to the designer;
* only the host machine may use any of it;
* the launcher registers the host on its GUI loop, and the fallback (no
  native window) takes it away again.
"""
import os
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import output_native  # noqa: E402
import routes_output  # noqa: E402


class FakeScreen:
    def __init__(self, x, y, width, height, scale=1.0):
        self.x, self.y, self.width, self.height, self.scale = x, y, width, height, scale
        self.frame = None


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def set(self):
        for fn in self.handlers:
            fn()


class FakeEvents:
    def __init__(self):
        self.closed = FakeEvent()
        self.shown = FakeEvent()


class FakeWindow:
    def __init__(self, calls, kwargs):
        self.calls = calls
        self.kwargs = kwargs
        self.events = FakeEvents()
        self.native = object()

    def show(self):
        self.calls.append('show')

    def toggle_fullscreen(self):
        self.calls.append('fullscreen')

    def destroy(self):
        self.calls.append('destroy')
        self.events.closed.set()


class FakeWebview:
    def __init__(self, screens):
        self.screens = screens
        self.settings = {'IGNORE_SSL_ERRORS': False}
        self.calls = []
        self.created = []

    def create_window(self, title, **kwargs):
        self.calls.append('create')
        w = FakeWindow(self.calls, dict(kwargs, title=title))
        self.created.append(w)
        return w


def mac_screens():
    # Main 1920 x 1080 "looks like" at 2x; a 3840 x 2160 display to its right
    # whose top sits 200 points above the main one's (cocoa counts y up).
    return [FakeScreen(0, 0, 1920, 1080, 2.0), FakeScreen(1920, -880, 3840, 2160, 1.0)]


def host_for(platform, screens, url='http://127.0.0.1:8050/'):
    wv = FakeWebview(screens)
    logs = []
    host = output_native.NativeOutputHost(wv, lambda: url, log=lambda a, d: logs.append((a, d)),
                                          platform=platform)
    return host, wv, logs


# ── the launcher side ─────────────────────────────────────────────────────

def test_displays_are_pywebviews_list_at_the_os_resolution():
    host, _wv, _ = host_for('darwin', mac_screens())
    d = host.displays()
    assert [x['index'] for x in d] == [0, 1]
    assert (d[0]['width'], d[0]['height'], d[0]['scale']) == (1920, 1080, 2.0)
    assert (d[1]['width'], d[1]['height']) == (3840, 2160)
    assert d[0]['main'] is True and d[1]['main'] is False
    # cocoa y is bottom-up from the main display's bottom: top-down here.
    assert (d[0]['x'], d[0]['y']) == (0, 0)
    assert (d[1]['x'], d[1]['y']) == (1920, 1080 - (-880 + 2160))
    assert all(x['name'] for x in d)


def test_windows_displays_keep_their_coordinates():
    host, _wv, _ = host_for('win32', [FakeScreen(0, 0, 3840, 2160, 1.5), FakeScreen(-1920, 0, 1920, 1080)])
    d = host.displays()
    assert (d[1]['x'], d[1]['y'], d[1]['width'], d[1]['height']) == (-1920, 0, 1920, 1080)
    assert d[0]['main'] and not d[1]['main']


class FakeRect:
    def __init__(self, x, y, w, h):
        self.origin = type('P', (), {'x': x, 'y': y})()
        self.size = type('S', (), {'width': w, 'height': h})()


class FakeNSWindow:
    """The AppKit calls _cover_on_mac makes, in order."""
    def __init__(self):
        self.calls = []
        self._frame = FakeRect(0, 0, 960, 540)

    def setCollectionBehavior_(self, v):
        self.calls.append(('behavior', v))

    def setLevel_(self, v):
        self.calls.append(('level', v))

    def setHasShadow_(self, v):
        self.calls.append(('shadow', v))

    def setMovable_(self, v):
        self.calls.append(('movable', v))

    def setFrame_display_(self, frame, display):
        self.calls.append(('frame', frame))
        self._frame = frame

    def orderFrontRegardless(self):
        self.calls.append(('front',))

    def frame(self):
        return self._frame


def test_mac_lays_the_window_over_the_whole_chosen_display(monkeypatch):
    """Not macOS full screen (asked while pywebview builds the window it
    never took: beta.4 on a Mac stayed a 960 x 540 box). Once shown, the
    borderless window is set to the display's own frame, above the menu bar
    and Dock, on every Space, on the main thread."""
    screens = mac_screens()
    screens[1].frame = FakeRect(1920, -880, 3840, 2160)
    host, wv, logs = host_for('darwin', screens)
    main = []
    monkeypatch.setattr(host, '_on_mac_main', lambda fn: main.append(fn))
    shown = host.open('abc123def456', 1, '/output?canvas=c1&view=pixel-map&feed=abc123def456', 'Out')
    assert shown['index'] == 1 and shown['width'] == 3840
    (w,) = wv.created
    assert w.kwargs['screen'] is wv.screens[1]
    assert w.kwargs['fullscreen'] is False
    assert w.kwargs['hidden'] is False
    assert w.kwargs['frameless'] is True
    assert (w.kwargs['width'], w.kwargs['height']) == (3840, 2160)
    assert w.kwargs['background_color'] == '#000000'
    assert w.kwargs['url'] == 'http://127.0.0.1:8050/output?canvas=c1&view=pixel-map&feed=abc123def456'
    assert w.kwargs['title'] == 'Out'
    assert wv.calls == ['create']
    assert host.is_open('abc123def456')
    assert logs[-1][0] == 'output_native_open'
    # nothing touches AppKit until the window is up
    assert main == []
    w.native = FakeNSWindow()
    w.events.shown.set()
    assert len(main) == 1
    main[0]()
    calls = w.native.calls
    assert ('level', 25) in calls                       # over the menu bar
    assert ('behavior', 1 | 16 | 64 | 256) in calls     # every Space, stays put
    assert ('frame', screens[1].frame) in calls         # the display's own frame
    assert calls[-1] == ('front',)
    covered = [d for a, d in logs if a == 'output_native_covered']
    assert covered and covered[-1]['frame'] == [1920, -880, 3840, 2160]
    assert covered[-1]['display'] == [3840, 2160]


def test_mac_cover_failing_is_logged_not_raised(monkeypatch):
    host, wv, logs = host_for('darwin', mac_screens())
    monkeypatch.setattr(host, '_on_mac_main', lambda fn: fn())
    host.open('abc123def457', 0, '/output?feed=abc123def457')
    (w,) = wv.created
    w.native = object()   # no AppKit methods
    w.events.shown.set()
    assert any(a == 'output_native_cover_failed' for a, _ in logs)


def test_windows_places_the_hidden_window_then_goes_full_screen(monkeypatch):
    host, wv, _ = host_for('win32', [FakeScreen(0, 0, 2560, 1440, 1.5), FakeScreen(2560, 0, 1920, 1080)])
    placed = []
    monkeypatch.setattr(host, '_place_on_windows',
                        lambda window, index: (placed.append(index), wv.calls.append('place')))
    host.open('feed00000001', 1, '/output?feed=feed00000001')
    (w,) = wv.created
    assert w.kwargs['screen'] is wv.screens[1]
    assert w.kwargs['hidden'] is True and w.kwargs['fullscreen'] is False
    assert placed == [1]
    assert wv.calls == ['create', 'place', 'show', 'fullscreen']


def test_https_lets_the_window_take_the_servers_own_certificate():
    host, wv, _ = host_for('darwin', mac_screens(), url='https://127.0.0.1:8050/')
    host.open('feed00000002', 0, '/output?feed=feed00000002')
    assert wv.settings['IGNORE_SSL_ERRORS'] is True
    assert wv.created[0].kwargs['url'].startswith('https://127.0.0.1:8050/output')


def test_bad_ids_and_displays_are_refused():
    host, wv, _ = host_for('darwin', mac_screens())
    with pytest.raises(ValueError):
        host.open('../etc', 0, '/output')
    with pytest.raises(IndexError):
        host.open('feed00000003', 5, '/output')
    assert wv.created == []


def test_closing_destroys_the_window_and_tells_the_server():
    host, wv, _ = host_for('darwin', mac_screens())
    told = []
    host.on_closed = told.append
    host.open('feed00000004', 0, '/output')
    host.open('feed00000005', 1, '/output')
    assert sorted(host.open_ids()) == ['feed00000004', 'feed00000005']
    assert host.close('feed00000004') is True
    assert 'destroy' in wv.calls and not host.is_open('feed00000004')
    assert told == ['feed00000004']
    assert host.close('feed00000004') is False
    # The OS closing the other one (Cmd+W, Alt+F4) is heard the same way.
    wv.created[1].events.closed.set()
    assert host.open_ids() == [] and told == ['feed00000004', 'feed00000005']


def test_launcher_registers_the_host_and_the_fallback_removes_it(monkeypatch):
    import launcher_window as lw

    class Api:
        settings = {'interface': '0.0.0.0', 'port': 8123, 'https_enabled': False}

    wv = FakeWebview(mac_screens())
    try:
        lw._register_native_outputs(wv, Api())
        host = routes_output.native_host()
        assert isinstance(host, output_native.NativeOutputHost)
        assert host._base_url() == 'http://127.0.0.1:8123/'
        assert host.on_closed is routes_output._drop_feed
        monkeypatch.setattr(lw, 'open_url', lambda *a, **k: None)
        monkeypatch.setattr(lw, '_show_windows_error', lambda *a, **k: None, raising=False)
        # The fallback then holds the main thread for good; stop it there
        # (not with KeyboardInterrupt: that path calls os._exit).

        class Held(Exception):
            pass

        def hold(*_):
            raise Held()
        monkeypatch.setattr(lw.time, 'sleep', hold)

        class FallbackApi:
            settings = Api.settings

            def mark_window_unavailable(self):
                pass
        try:
            lw._launcher_window_fallback(Api.settings, FallbackApi(), RuntimeError('no window'))
        except Held:
            pass
        assert routes_output.native_host() is None
    finally:
        routes_output.set_native_host(None)


# ── the server side ───────────────────────────────────────────────────────

class FakeHost:
    def __init__(self):
        self.opened = []
        self.closed = []
        self._open = set()
        self.on_closed = None

    def displays(self):
        return [
            {'index': 0, 'name': 'Built-in', 'x': 0, 'y': 0, 'width': 1512, 'height': 982, 'scale': 2.0, 'main': True},
            {'index': 1, 'name': 'Wall', 'x': 1512, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1.0, 'main': False},
        ]

    def open(self, output_id, display, path, title):
        self.opened.append((output_id, display, path, title))
        self._open.add(output_id)
        return self.displays()[display]

    def close(self, output_id):
        self.closed.append(output_id)
        self._open.discard(output_id)
        return True

    def open_ids(self):
        return list(self._open)


@pytest.fixture
def host(client):
    h = FakeHost()
    routes_output.set_native_host(h)
    old = routes_output.POLL_SECONDS
    routes_output.POLL_SECONDS = 0.3
    yield h
    routes_output.POLL_SECONDS = old
    routes_output.set_native_host(None)
    with routes_output._cond:
        routes_output._feeds.clear()


def test_no_host_means_browser_windows(client):
    routes_output.set_native_host(None)
    assert client.get('/api/output/native').get_json() == {'available': False, 'displays': []}
    assert client.post('/api/output/native/open', json={'display': 0}).status_code == 409


def test_open_feed_and_close(client, host):
    j = client.get('/api/output/native').get_json()
    assert j['available'] is True and [d['name'] for d in j['displays']] == ['Built-in', 'Wall']

    res = client.post('/api/output/native/open',
                      json={'canvas': 'c1', 'view': 'idm', 'display': 1, 'title': 'Canvas 1 · IDM'})
    j = res.get_json()
    assert res.status_code == 200 and j['ok'] and j['display']['name'] == 'Wall'
    feed = j['id']
    (oid, display, path, title) = host.opened[0]
    assert oid == feed and display == 1 and title == 'Canvas 1 · IDM'
    assert path.startswith('/output?') and 'canvas=c1' in path and 'view=idm' in path and f'feed={feed}' in path
    assert client.get('/api/output/native/list').get_json() == {'open': [feed]}

    # Nothing yet: the window's wait ends empty.
    assert client.get(f'/api/output/feed/{feed}?after=0').status_code == 204
    png = b'\x89PNG\r\n\x1a\n' + b'x' * 64
    r = client.post(f'/api/output/feed/{feed}/frame', data=png,
                    headers={'Content-Type': 'image/png', 'X-Output-Title': 'Canvas%201%20%C2%B7%20IDM'})
    assert r.get_json()['seq'] == 1
    r = client.get(f'/api/output/feed/{feed}?after=0')
    assert r.status_code == 200 and r.mimetype == 'image/png' and r.data == png
    assert r.headers['X-Frame-Seq'] == '1'
    assert r.headers['X-Output-Title'] == 'Canvas%201%20%C2%B7%20IDM'
    # Seen it: the next wait ends empty, the latest frame only.
    assert client.get(f'/api/output/feed/{feed}?after=1').status_code == 204
    client.post(f'/api/output/feed/{feed}/frame', data=b'a', headers={'Content-Type': 'image/png'})
    client.post(f'/api/output/feed/{feed}/frame', data=b'b', headers={'Content-Type': 'image/png'})
    r = client.get(f'/api/output/feed/{feed}?after=1')
    assert r.data == b'b' and r.headers['X-Frame-Seq'] == '3'

    # A line in place of the picture.
    client.post(f'/api/output/feed/{feed}/message', json={'message': 'This canvas is no longer in the project.'})
    r = client.get(f'/api/output/feed/{feed}?after=3')
    assert r.get_json()['message'] == 'This canvas is no longer in the project.'

    # Esc in the window.
    assert client.post(f'/api/output/feed/{feed}/close').get_json()['ok']
    assert host.closed == [feed]
    assert client.get(f'/api/output/feed/{feed}?after=0').status_code == 410
    assert client.post(f'/api/output/feed/{feed}/frame', data=b'c',
                       headers={'Content-Type': 'image/png'}).status_code == 404
    assert client.get('/api/output/native/list').get_json() == {'open': []}


def test_a_waiting_window_gets_the_frame_as_it_comes(client, host):
    routes_output.POLL_SECONDS = 5.0
    feed = client.post('/api/output/native/open', json={'display': 0}).get_json()['id']
    got = {}

    def wait():
        from app import app
        with app.test_client() as c:
            got['res'] = c.get(f'/api/output/feed/{feed}?after=0')

    t = threading.Thread(target=wait)
    t.start()
    t.join(0.3)
    assert t.is_alive(), 'the wait should still be waiting for a frame'
    client.post(f'/api/output/feed/{feed}/frame', data=b'now', headers={'Content-Type': 'image/png'})
    t.join(3)
    assert not t.is_alive() and got['res'].data == b'now'


def test_the_dialog_and_the_designer_leaving_close_outputs(client, host):
    a = client.post('/api/output/native/open', json={'display': 0}).get_json()['id']
    b = client.post('/api/output/native/open', json={'display': 1}).get_json()['id']
    # sendBeacon posts text/plain.
    r = client.post('/api/output/native/close', data='{"ids": ["%s", "%s", "../x"]}' % (a, b),
                    headers={'Content-Type': 'text/plain'})
    assert sorted(r.get_json()['closed']) == sorted([a, b])
    assert sorted(host.closed) == sorted([a, b])
    assert client.get(f'/api/output/feed/{a}?after=0').status_code == 410


def test_the_os_closing_the_window_drops_its_frames(client, host):
    feed = client.post('/api/output/native/open', json={'display': 1}).get_json()['id']
    host._open.discard(feed)
    host.on_closed(feed)
    assert client.get(f'/api/output/feed/{feed}?after=0').status_code == 410


def test_a_failed_window_leaves_no_feed(client, host):
    def boom(*a):
        raise RuntimeError('no GUI')
    host.open = boom
    r = client.post('/api/output/native/open', json={'display': 0})
    assert r.status_code == 500 and r.get_json()['ok'] is False
    assert routes_output._feeds == {}


def test_another_machine_cannot_open_or_feed(client, host):
    env = {'REMOTE_ADDR': '10.99.88.77'}
    assert client.get('/api/output/native', environ_base=env).status_code == 403
    assert client.post('/api/output/native/open', json={'display': 0}, environ_base=env).status_code == 403
    assert client.post('/api/output/feed/abcdef123456/frame', data=b'x', environ_base=env).status_code == 403
    assert host.opened == []
