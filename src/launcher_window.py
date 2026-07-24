"""
LED Raster Designer - Branded Launcher Window

A splash/control window (launcher_window.html) rendered in the
OS-native webview via pywebview. Shows server status and exposes the launch
controls (interface, port, browser + open-on-launch, run at login, start
minimized) plus Launch GUI / Hide / Quit.

Pure Python; the UI reuses the app's own web styling so it matches the brand.
This window coexists with the tray / menu-bar launchers and shares the same
settings.json, so a change here is reflected there and vice versa.
"""
import sys
import os
import threading
import time

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BASE_DIR

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from launcher_settings import (
    load_settings, save_settings, get_network_interfaces, set_run_at_login,
    get_ssl_context, get_available_browsers, open_url,
)

HTML_FILE = os.path.join(BASE_DIR, 'launcher_window.html')

_socketio = None
_server_running = False

# .NET Framework 4.7.2. pythonnet's Python.Runtime.dll targets .NET Standard
# 2.0, and 4.7.2 is the first Framework release that can bind the netstandard
# facades in-box. On anything older the CLR opens the DLL but fails to resolve
# its entry point, so the launcher window can't start.
DOTNET_FRAMEWORK_MIN_RELEASE = 461808


def _launcher_log(action, details, source='launcher'):
    """Best-effort write into the app's JSON log (Help -> Show Logs).

    Falls back to a plain file next to the executable when app.py can't be
    imported: a crash that early would otherwise leave nothing on disk at all,
    which is precisely the case this exists for.
    """
    try:
        import app as app_module
        app_module.log_event(action, details, source=source)
        return
    except Exception:
        pass
    try:
        import json as _json
        import datetime as _dt
        line = _json.dumps({
            'timestamp': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': source,
            'action': action,
            'details': details or {},
        }, ensure_ascii=False)
        with open(os.path.join(APP_DIR, 'launcher_crash.log'), 'a',
                  encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def _format_exc(exc):
    import traceback
    return ''.join(
        traceback.format_exception(type(exc), exc, exc.__traceback__))


def _install_crash_logger():
    """Record any uncaught exception, on the main thread or a worker.

    The Windows build is windowed (console=False), so without this a startup
    crash writes its traceback to a stderr nobody can read: the app simply
    dies, or leaves a tray icon behind with no explanation anywhere on disk.
    """
    def _log(exc_type, exc, tb, thread=None):
        try:
            import traceback as _tb
            name = getattr(exc_type, '__name__', str(exc_type))
            _launcher_log('launcher_crash', {
                'error': f'{name}: {exc}',
                'thread': thread or 'main',
                'traceback': ''.join(_tb.format_exception(exc_type, exc, tb)),
            })
        except Exception:
            pass

    def _hook(exc_type, exc, tb):
        _log(exc_type, exc, tb)
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _hook

    # Python 3.8+: an exception that kills a thread never reaches
    # sys.excepthook, so the Flask server thread dying would be silent too.
    try:
        def _thread_hook(args):
            _log(args.exc_type, args.exc_value, args.exc_traceback,
                 thread=getattr(args.thread, 'name', None))
        threading.excepthook = _thread_hook
    except Exception:
        pass


def _windows_dotnet_release():
    """The installed .NET Framework 4.x release number, or None."""
    try:
        import winreg
        path = r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            return int(winreg.QueryValueEx(key, 'Release')[0])
    except Exception:
        return None


def _log_startup_environment():
    """One line in the log describing the machine we're running on.

    Turns "it won't open on my PC" into something answerable from the log
    alone, without a remote debugging session.
    """
    info = {
        'version': _read_version(),
        'platform': sys.platform,
        'frozen': bool(getattr(sys, 'frozen', False)),
        'python': sys.version.split()[0],
    }
    try:
        import platform as _pl
        info['os'] = _pl.platform()
        info['machine'] = _pl.machine()
    except Exception:
        pass
    if sys.platform == 'win32':
        release = _windows_dotnet_release()
        info['dotnet_framework_release'] = release
        info['dotnet_framework_ok'] = bool(
            release is not None and release >= DOTNET_FRAMEWORK_MIN_RELEASE)
        try:
            import importlib.metadata as _md
            for dist in ('pywebview', 'pythonnet', 'clr-loader', 'pystray'):
                try:
                    info[f'{dist}_version'] = _md.version(dist)
                except Exception:
                    pass
        except Exception:
            pass
    _launcher_log('launcher_environment', info)


def _launcher_failure_hint():
    """Plain-language guess at why the native window refused to start."""
    if sys.platform != 'win32':
        return 'See the app log for details.'
    release = _windows_dotnet_release()
    if release is None:
        return ('Microsoft .NET Framework 4.8 does not appear to be '
                'installed. Installing it should restore the window.')
    if release < DOTNET_FRAMEWORK_MIN_RELEASE:
        return ('Microsoft .NET Framework looks older than 4.7.2 '
                f'(release {release}). Updating to 4.8 should restore the '
                'window.')
    return ('The file may be blocked by Windows or antivirus. Right-click '
            'the downloaded .zip, tick Unblock, then extract it again.')


def _show_windows_error(title, message):
    try:
        import ctypes
        MB_OK = 0x0
        MB_ICONWARNING = 0x30
        MB_SETFOREGROUND = 0x10000
        ctypes.windll.user32.MessageBoxW(
            None, message, title, MB_OK | MB_ICONWARNING | MB_SETFOREGROUND)
    except Exception:
        pass


def _read_version():
    # encoding matters: VERSION.txt is UTF-8, but Windows' default open()
    # encoding is cp1252 — the resulting UnicodeDecodeError (which is NOT an
    # OSError!) escaped, made get_state raise over the JS bridge, and left
    # the launcher window stuck on its placeholder data.
    for name in ('VERSION.txt',):
        path = os.path.join(BASE_DIR, name)
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                first = f.read().splitlines()
                for line in first:
                    line = line.strip()
                    if line.lower().startswith('v') and '.' in line:
                        return line.split()[0]
        except Exception:
            pass
    return 'v0.10.0'


def get_display_url(settings):
    host = settings.get('interface', '127.0.0.1')
    port = settings.get('port', 8050)
    display_host = host if host != '0.0.0.0' else '127.0.0.1'
    protocol = 'https' if settings.get('https_enabled', False) else 'http'
    return f'{protocol}://{display_host}:{port}/'


def start_flask_server(settings):
    """Run the Flask app in this thread (called from a background daemon)."""
    global _socketio, _server_running
    host = settings.get('interface', '127.0.0.1')
    port = int(settings.get('port', 8050))

    from app import app, socketio, log_event
    _socketio = socketio

    ssl_ctx = get_ssl_context(settings)
    protocol = 'https' if ssl_ctx else 'http'
    log_event('server_start', {
        'port': port, 'host': host, 'protocol': protocol,
        'launcher': 'window',
    })

    kwargs = dict(host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    if ssl_ctx:
        kwargs['certfile'] = ssl_ctx[0]
        kwargs['keyfile'] = ssl_ctx[1]

    _server_running = True
    try:
        socketio.run(app, **kwargs)
    finally:
        _server_running = False


def restart_flask_server(settings):
    if _socketio:
        try:
            _socketio.stop()
        except Exception:
            pass
        time.sleep(0.5)
    t = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    t.start()


class LauncherAPI:
    """Bridge exposed to the HTML via pywebview (window.pywebview.api)."""

    def __init__(self, settings):
        self.settings = settings
        self._window = None
        # Set when the native window failed to start; show() then falls back
        # to the browser so the tray's "Show Launcher" still does something
        # useful instead of raising into a dead window handle.
        self._window_unavailable = False

    # ── state ──────────────────────────────────────────────────────────────
    def get_state(self):
        s = self.settings
        # A raised exception here rejects the JS promise and the window keeps
        # its placeholder demo data (seen on Windows when the browser scan
        # tripped). Degrade each scan independently instead of failing whole.
        try:
            interfaces = get_network_interfaces()
        except Exception:
            interfaces = [('127.0.0.1', '127.0.0.1 (localhost)'),
                          ('0.0.0.0', 'All Interfaces')]
        try:
            browsers = get_available_browsers()
        except Exception:
            browsers = [('default', 'System default')]
        return {
            'version': _read_version(),
            'url': get_display_url(s),
            'running': _server_running,
            'port': s.get('port', 8050),
            'interfaces': interfaces,
            'interface': s.get('interface', '127.0.0.1'),
            'browsers': browsers,
            'browser': s.get('browser', 'default'),
            'open_browser_on_launch': s.get('open_browser_on_launch', False),
            'start_minimized': s.get('start_minimized', False),
            'run_at_login': s.get('run_at_login', False),
        }

    def _save(self):
        save_settings(self.settings)

    # ── setters ────────────────────────────────────────────────────────────
    def set_interface(self, ip):
        self.settings['interface'] = ip
        self._save()
        restart_flask_server(self.settings)
        return self.get_state()

    def set_port(self, port):
        try:
            p = int(str(port).strip())
        except (TypeError, ValueError):
            return self.get_state()
        if 1024 <= p <= 65535:
            self.settings['port'] = p
            self._save()
            restart_flask_server(self.settings)
        return self.get_state()

    def set_browser(self, key):
        self.settings['browser'] = key
        self._save()
        return self.get_state()

    def set_open_on_launch(self, enabled):
        self.settings['open_browser_on_launch'] = bool(enabled)
        self._save()
        return self.get_state()

    def set_start_minimized(self, enabled):
        self.settings['start_minimized'] = bool(enabled)
        self._save()
        return self.get_state()

    def set_run_at_login(self, enabled):
        self.settings['run_at_login'] = bool(enabled)
        self._save()
        set_run_at_login(bool(enabled))
        return self.get_state()

    # ── actions ────────────────────────────────────────────────────────────
    def launch_gui(self):
        open_url(get_display_url(self.settings), self.settings)

    def open_browser(self):
        open_url(get_display_url(self.settings), self.settings)

    def open_settings(self):
        # Reserved for an advanced settings panel (HTTPS, certs). No-op for now.
        return self.get_state()

    def hide(self):
        # Hide to the menu-bar (macOS) / tray (Windows) icon.
        # The icon's "Show Launcher" brings the window back.
        if self._window:
            self._window.hide()

    def minimize(self):
        # Kept for compatibility; the launcher hides rather than minimizes.
        self.hide()

    def mark_window_unavailable(self):
        """The native launcher window could not be created."""
        self._window = None
        self._window_unavailable = True

    def show(self):
        if self._window_unavailable:
            self.open_browser()
            return
        if self._window:
            self._window.show()
            if sys.platform == 'darwin':
                _mac_bring_window_front()

    def quit(self):
        try:
            if self._window:
                self._window.destroy()
        finally:
            os._exit(0)


def _mac_bring_window_front():
    """Force the launcher window visibly on top (macOS).

    As an Accessory (no-Dock) app, neither launch nor NSApp activation
    reliably raises the window on modern macOS (cooperative activation lets
    the frontmost app keep focus), so the splash could open BEHIND whatever
    the user was working in. orderFrontRegardless() is the documented API for
    exactly this, plus a briefly-floating window level to guarantee it tops
    full-screen-ish stacks; the level is restored right after.
    """
    try:
        import AppKit
        from PyObjCTools import AppHelper

        def raise_window():
            try:
                AppKit.NSApp.activateIgnoringOtherApps_(True)
                for w in AppKit.NSApp.windows():
                    if w.isVisible():
                        w.setLevel_(AppKit.NSFloatingWindowLevel)
                        w.orderFrontRegardless()

                def settle():
                    try:
                        for w in AppKit.NSApp.windows():
                            w.setLevel_(AppKit.NSNormalWindowLevel)
                    except Exception:
                        pass
                AppHelper.callLater(2.0, settle)
            except Exception:
                pass

        AppHelper.callAfter(raise_window)
    except Exception:
        pass


# ── Menu-bar / tray icon (restores the hidden window) ──────────────────────

def _start_tray_windows(api):
    """System tray icon (Windows). pystray supports run_detached() on win32,
    so it runs alongside pywebview's UI loop on the main thread."""
    import pystray
    from pystray import Menu, MenuItem
    from launcher_pc import create_tray_icon_image

    def show(icon, item):
        api.show()

    def open_browser(icon, item):
        api.open_browser()

    def quit_app(icon, item):
        try:
            icon.stop()
        finally:
            api.quit()

    icon = pystray.Icon(
        name='LED Raster Designer',
        icon=create_tray_icon_image(),
        title='LED Raster Designer',
        menu=Menu(
            MenuItem('Show Launcher', show, default=True),
            MenuItem('Open in Browser', open_browser),
            Menu.SEPARATOR,
            MenuItem('Quit LED Raster Designer', quit_app),
        ),
    )
    icon.run_detached()
    return icon


def _start_statusitem_mac(api):
    """Menu-bar status item (macOS), created inside pywebview's own Cocoa app
    via PyObjC (pywebview's cocoa backend already depends on PyObjC). Must be
    scheduled onto the main run loop; safe to call from webview.start(func=)."""
    import AppKit
    import objc
    from PyObjCTools import AppHelper
    from launcher_mac import _create_menubar_icon

    class _StatusDelegate(AppKit.NSObject):
        def initWithAPI_(self, launcher_api):
            self = objc.super(_StatusDelegate, self).init()
            if self is None:
                return None
            self._api = launcher_api
            return self

        def showLauncher_(self, sender):
            self._api.show()

        def openBrowser_(self, sender):
            self._api.open_browser()

        def quitApp_(self, sender):
            self._api.quit()

    def make():
        # No Dock icon at all: pywebview's cocoa backend
        # forces the Regular activation policy at startup (overriding the
        # bundle's LSUIElement), which left a Dock icon that did nothing.
        # Drop to Accessory: menu-bar item + window only.
        AppKit.NSApp.setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)
        bar = AppKit.NSStatusBar.systemStatusBar()
        item = bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(_create_menubar_icon())
        if image is not None:
            image.setSize_(AppKit.NSMakeSize(18, 18))
            image.setTemplate_(True)  # macOS recolors for light/dark menu bars
            item.button().setImage_(image)
        else:
            item.button().setTitle_('LRD')
        delegate = _StatusDelegate.alloc().initWithAPI_(api)
        menu = AppKit.NSMenu.alloc().init()
        for title, selector in (
            ('Show Launcher', 'showLauncher:'),
            ('Open in Browser', 'openBrowser:'),
            (None, None),
            ('Quit LED Raster Designer', 'quitApp:'),
        ):
            if title is None:
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                continue
            mi = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, selector, '')
            mi.setTarget_(delegate)
            menu.addItem_(mi)
        item.setMenu_(menu)
        # Keep strong references or ObjC releases the item and it vanishes.
        api._status_refs = (item, delegate, image, menu)
        # Bring the splash visibly to the front on launch (unless it
        # deliberately started hidden) — see _mac_bring_window_front.
        if not api.settings.get('start_minimized', False):
            _mac_bring_window_front()

    AppHelper.callAfter(make)


def run_window(settings):
    """Create and run the launcher window (blocks the main thread)."""
    import webview  # pywebview

    api = LauncherAPI(settings)

    # Position explicitly: in the frozen menu-bar (LSUIElement) app, default
    # placement put the window off-screen (observed at x=-922 on a single-
    # display Mac). Center horizontally, upper third vertically.
    # Height: pywebview's height includes the OS window chrome, so the page
    # viewport comes out shorter than requested. The layout needs ~489px of
    # content. macOS chrome is ~28px (518 fits exactly); Windows title bar +
    # borders are ~40 logical px and vary a little across versions, so give it
    # generous headroom — the footer is bottom-pinned in CSS, so extra slack
    # renders as clean spacing instead of clipped buttons.
    win_w = 468
    win_h = 518 if sys.platform == 'darwin' else 552
    pos = {}
    try:
        screen = webview.screens[0]
        pos['x'] = max(0, (screen.width - win_w) // 2)
        pos['y'] = max(0, (screen.height - win_h) // 3)
    except Exception:
        pass  # fall back to backend default placement

    window = webview.create_window(
        'LED Raster Designer',
        url=HTML_FILE,
        js_api=api,
        width=win_w,
        height=win_h,
        resizable=False,
        # Hidden start is safe: the tray / menu-bar icon can always restore it.
        hidden=settings.get('start_minimized', False),
        **pos,
    )
    api._window = window

    # Close-to-hide: the window's X hides to the tray / menu-bar icon
    # instead of quitting — closing the launcher would stop the server for
    # every connected device. Quit lives in the window and the icon menu.
    def on_closing():
        api.hide()
        return False  # cancel the close

    window.events.closing += on_closing

    # A failure in any of this used to escape main() entirely. With no console
    # on the frozen Windows build the traceback went nowhere, and because
    # pystray's detached icon runs on a non-daemon thread the process then sat
    # wedged in interpreter shutdown: a tray icon the user could neither open
    # nor quit. Every path below now degrades instead of dying.
    try:
        if sys.platform == 'win32':
            try:
                _start_tray_windows(api)
            except Exception as exc:
                _launcher_log('launcher_tray_failed', {
                    'error': f'{type(exc).__name__}: {exc}',
                    'traceback': _format_exc(exc),
                })
            webview.start()
        elif sys.platform == 'darwin':
            # The status item must be created after the Cocoa app starts;
            # start() runs the callback once the window/run loop are up.
            webview.start(func=_start_statusitem_mac, args=(api,))
        else:
            webview.start()
    except Exception as exc:
        _launcher_window_fallback(settings, api, exc)
        return
    # webview.start() only returns when the window is destroyed (Quit path).
    # Exit so the background Flask thread doesn't keep a headless server alive.
    os._exit(0)


def _launcher_window_fallback(settings, api, exc):
    """Keep the app usable when the native launcher window can't start.

    The window is only a control panel; the Flask server behind it is the
    actual app and is already running by this point. So log what happened,
    tell the user, hand them the browser, and hold the process open so the
    tray icon (including its Quit) keeps working.
    """
    hint = _launcher_failure_hint()
    _launcher_log('launcher_window_failed', {
        'error': f'{type(exc).__name__}: {exc}',
        'traceback': _format_exc(exc),
        'hint': hint,
    })
    api.mark_window_unavailable()

    url = get_display_url(settings)
    try:
        open_url(url, settings)
    except Exception:
        pass

    if sys.platform == 'win32':
        _show_windows_error(
            'LED Raster Designer',
            "The launcher window couldn't start, so the app opened in your "
            'browser instead.\n\n'
            f'Address: {url}\n\n'
            f'{hint}\n\n'
            'Full details were saved to the app log (Help → Show Logs).')

    # Hold the main thread. The tray icon's menu runs on its own thread and
    # needs a live interpreter to call back into; letting main() return here
    # would drop us into the same wedged shutdown this fix exists to prevent.
    # Quit from the tray calls os._exit().
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        os._exit(0)


def _setup_launcher_debug_log():
    """Route pywebview's logger into the app's main JSON log (log_event), so
    launcher/bridge diagnostics land in the same file as everything else and
    show up in Help -> Show Logs. The frozen window app has no console, so
    without this, bridge failures are invisible (this is how the dead js_api
    on Windows was finally diagnosed)."""
    try:
        import logging

        class _AppLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    # Lazy import: by the time pywebview logs anything, the
                    # server thread has already imported app.
                    import app as app_module
                    app_module.log_event('launcher_debug', {
                        'level': record.levelname,
                        # format() appends the traceback when exc_info is set
                        'message': self.format(record),
                    }, source='launcher')
                except Exception:
                    pass

        handler = _AppLogHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger = logging.getLogger('pywebview')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.debug('launcher debug logging -> app log (platform=%s, frozen=%s)',
                     sys.platform, getattr(sys, 'frozen', False))
    except Exception:
        pass


def main():
    # First thing: from here on, nothing can fail silently.
    _install_crash_logger()
    settings = load_settings()
    _setup_launcher_debug_log()

    # Packaged-build smoke mode (CI): run the server only — no launcher
    # window, no tray/menu-bar icon, no browser. Lets the release workflow
    # launch the frozen binary on a headless runner and probe the HTTP API.
    if os.environ.get('LRD_NO_WINDOW'):
        port = os.environ.get('LRD_SMOKE_PORT')
        if port:
            try:
                settings['port'] = int(port)
            except ValueError:
                pass
        print('[LED Raster Designer] LRD_NO_WINDOW set: server-only mode '
              f"(port {settings.get('port', 8050)})")
        start_flask_server(settings)  # blocks on the main thread
        return

    server_thread = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    server_thread.start()
    time.sleep(1.0)
    # Logged after the server thread so app.py (which owns the log file) is
    # already imported, and before the window so it lands even if that fails.
    _log_startup_environment()

    if settings.get('open_browser_on_launch', False):
        open_url(get_display_url(settings), settings)

    run_window(settings)


if __name__ == '__main__':
    main()
