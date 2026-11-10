"""
Output to Display, the desktop side: native full-screen output windows.

The designer runs in a browser, and a browser cannot put a window full screen
on a display of its choosing (some browsers cannot even list them). The
desktop app's launcher already runs pywebview's GUI loop, so it owns the
output windows instead: the designer asks the server (routes_output.py), the
server asks this host, and the host opens /output as a native window, full
screen, on the display the crew picked. No dragging, no click.

The window is fed through the server (routes_output.py keeps the latest frame
of each output), because a native window is not a popup child of the
designer's browser and has no reference the designer could draw into.

pywebview 6.2.1, read for this:
* webview.screens lists the displays in the GUI library's own order and
  units: macOS (cocoa) gives NSScreen frames in points with the backing scale
  (a display macOS runs "looks like 1920 x 1080" at 2x reads 1920 x 1080,
  scale 2); Windows (winforms) gives Screen.AllScreens bounds.
* create_window() called off the main thread after start() creates the window
  at once: cocoa queues it on the main run loop (AppHelper.callAfter), winforms
  Invokes it on the GUI thread. Both are safe from a Flask request thread.
* cocoa puts a window with `screen=` on that screen (setFrameOrigin to the
  screen's origin, then centers on it) and `fullscreen=True` sends it into
  macOS full screen there (toggleFullScreen_, its own Space on that display).
* winforms with `screen=` multiplies the screen's coordinates by the new
  window's DPI scale, which lands on the wrong display when Windows scaling is
  not 100%; its full screen then covers whichever display holds the window. So
  on Windows the window is opened hidden, its bounds are set to the chosen
  display's own bounds (the same coordinate space, whatever the scaling), and
  only then shown and sent full screen.
"""
import re
import sys
import threading

OUTPUT_ID = re.compile(r'^[a-z0-9]{6,32}$')


class NativeOutputHost:
    """Opens, tracks and closes the native output windows.

    `webview` is the pywebview module (a stand-in in tests); `base_url` a
    callable returning the server's own address ('http://127.0.0.1:8050/');
    `log` a log_event-style callable.
    """

    def __init__(self, webview, base_url, log=None, platform=None):
        self._webview = webview
        self._base_url = base_url
        self._log = log or (lambda action, details: None)
        self._platform = platform or sys.platform
        self._windows = {}
        self._lock = threading.Lock()
        # Told when a window goes by any road (Esc, the dialog, the OS's own
        # close), so the server drops that output's frames (routes_output).
        self.on_closed = None

    # ---- displays -----------------------------------------------------------

    def _screens(self):
        return list(self._webview.screens or [])

    def displays(self):
        """The displays, in pywebview's order, at the resolution the OS shows
        (points on a Mac, the display's pixels on Windows), each with its
        top-left corner in a top-down desktop frame."""
        screens = self._screens()
        names = self._display_names(len(screens))
        out = []
        # cocoa frames count y up from the bottom of the main display; turn
        # them top-down so a display above reads as y < 0, as on Windows.
        main_h = screens[0].height if screens else 0
        for i, s in enumerate(screens):
            x, y = int(s.x), int(s.y)
            if self._platform == 'darwin':
                y = int(main_h - (s.y + s.height))
            out.append({
                'index': i,
                'name': names[i] or f'Display {i + 1}',
                'x': x,
                'y': y,
                'width': int(s.width),
                'height': int(s.height),
                'scale': float(getattr(s, 'scale', 1.0) or 1.0),
                'main': int(s.x) == 0 and int(s.y) == 0,
            })
        return out

    def _display_names(self, count):
        names = [''] * count
        try:
            if self._platform == 'darwin':
                import AppKit  # noqa: N813 (pyobjc)
                for i, ns in enumerate(list(AppKit.NSScreen.screens())[:count]):
                    try:
                        names[i] = str(ns.localizedName())
                    except Exception:
                        pass
            elif self._platform == 'win32':
                from System.Windows.Forms import Screen  # pythonnet, loaded by pywebview
                for i, ws in enumerate(list(Screen.AllScreens)[:count]):
                    m = re.search(r'(\d+)\s*$', str(ws.DeviceName))
                    if m:
                        names[i] = f'Display {m.group(1)}'
        except Exception:
            pass
        return names

    # ---- windows ------------------------------------------------------------

    def open(self, output_id, display_index, path, title='Output'):
        """Open `path` (the /output address of this output) full screen on
        display `display_index`. Returns that display's entry."""
        if not OUTPUT_ID.match(output_id or ''):
            raise ValueError('bad output id')
        screens = self._screens()
        if not (0 <= int(display_index) < len(screens)):
            raise IndexError('no such display')
        index = int(display_index)
        screen = screens[index]
        display = self.displays()[index]
        url = self._base_url().rstrip('/') + path
        # The server's own HTTPS certificate is self-signed; this window only
        # ever loads that server.
        if url.startswith('https://'):
            try:
                self._webview.settings['IGNORE_SSL_ERRORS'] = True
            except Exception:
                pass
        windows = self._platform == 'win32'
        w = max(320, min(960, int(screen.width)))
        h = max(180, min(540, int(screen.height)))
        window = self._webview.create_window(
            title, url=url, screen=screen, width=w, height=h,
            fullscreen=not windows, hidden=windows,
            frameless=True, easy_drag=False, resizable=True,
            background_color='#000000', text_select=False,
        )
        if window is None:
            raise RuntimeError('the window was not created')
        with self._lock:
            self._windows[output_id] = window
        try:
            window.events.closed += lambda: self._forget(output_id, window)
        except Exception:
            pass
        if windows:
            self._place_on_windows(window, index)
            window.show()
            window.toggle_fullscreen()
        self._log('output_native_open', {
            'id': output_id, 'display': display, 'url': path,
            'platform': self._platform,
        })
        return display

    def _place_on_windows(self, window, index):
        """Put the (hidden) form exactly on display `index`, in WinForms'
        own coordinates, so its full screen covers that display."""
        try:
            from System import Func, Type  # pythonnet
            from System.Windows.Forms import Screen, FormWindowState
            form = window.native
            target = list(Screen.AllScreens)[index]

            def place():
                form.WindowState = FormWindowState.Normal
                form.Bounds = target.Bounds
                return None

            form.Invoke(Func[Type](place))
        except Exception as exc:
            self._log('output_native_place_failed', {'error': f'{type(exc).__name__}: {exc}'})

    def _forget(self, output_id, window):
        with self._lock:
            if self._windows.get(output_id) is window:
                del self._windows[output_id]
        if self.on_closed is not None:
            try:
                self.on_closed(output_id)
            except Exception:
                pass
        self._log('output_native_closed', {'id': output_id})

    def is_open(self, output_id):
        with self._lock:
            return output_id in self._windows

    def open_ids(self):
        with self._lock:
            return list(self._windows)

    def close(self, output_id):
        with self._lock:
            window = self._windows.pop(output_id, None)
        if window is None:
            return False
        try:
            window.destroy()
        except Exception as exc:
            self._log('output_native_close_failed', {'id': output_id, 'error': str(exc)})
        return True

    def close_all(self):
        for output_id in self.open_ids():
            self.close(output_id)
