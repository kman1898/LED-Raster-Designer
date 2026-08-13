"""
LED Raster Designer - Windows/Linux System Tray Launcher
Runs the Flask server in the background and provides a system tray icon
with settings for network interface, port, start minimized, and run at login.
"""
import sys
import os
import threading
import time

# Resolve paths for PyInstaller bundle
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
    get_ssl_context, regenerate_ssl_certs, get_available_browsers, open_url
)

# Global reference to socketio for server restart
_socketio = None
_app = None


def start_flask_server(settings):
    """Import and run the Flask app in a background thread."""
    global _socketio, _app
    host = settings.get('interface', '127.0.0.1')
    port = int(settings.get('port', 8050))

    import app as _app_module
    from app import app, socketio, log_event
    _socketio = socketio
    _app = app

    ssl_ctx = get_ssl_context(settings)
    protocol = 'https' if ssl_ctx else 'http'

    log_event('server_start', {
        'port': port,
        'host': host,
        'protocol': protocol,
        'launcher': 'pc_systray',
        'log_dir': os.environ.get('_LRD_LOG_DIR', 'unknown'),
    })

    kwargs = dict(host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    if ssl_ctx:
        kwargs['certfile'] = ssl_ctx[0]
        kwargs['keyfile'] = ssl_ctx[1]

    # Tell the app which address it is reachable at, so the native
    # dialog routes can recognise this machine when the user opens it
    # at that address rather than at localhost.
    _app_module.BOUND_HOST = host
    socketio.run(app, **kwargs)


def restart_flask_server(settings):
    """Stop the current server and start a new one with updated settings."""
    if _socketio:
        _socketio.stop()
        # Give it a moment to release the port
        time.sleep(0.5)
    server_thread = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    server_thread.start()


def get_display_url(settings):
    """Build the display URL from settings."""
    host = settings.get('interface', '127.0.0.1')
    port = settings.get('port', 8050)
    display_host = host if host != '0.0.0.0' else '127.0.0.1'
    protocol = 'https' if settings.get('https_enabled', False) else 'http'
    return f'{protocol}://{display_host}:{port}'


def create_tray_icon_image():
    """LED Raster Designer mark, a small LED cabinet of pixels."""
    from PIL import Image, ImageDraw

    S = 64
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    k = S / 48.0  # the mark is authored on a 48-unit grid

    def cell(col, row, color):
        x = (11 + col * 9) * k
        y = (11 + row * 9) * k
        s = 8 * k
        try:
            draw.rounded_rectangle([x, y, x + s, y + s], radius=3 * k, fill=color)
        except AttributeError:  # very old Pillow
            draw.rectangle([x, y, x + s, y + s], fill=color)

    # Cabinet tile
    try:
        draw.rounded_rectangle([4, 4, 60, 60], radius=13, fill=(22, 22, 22, 255),
                               outline=(70, 70, 70, 255), width=2)
    except AttributeError:
        draw.rectangle([4, 4, 60, 60], fill=(22, 22, 22, 255), outline=(70, 70, 70, 255), width=2)

    GRAY = (90, 90, 90, 255)
    ACCENT = (226, 35, 48, 255)
    LIGHT = (207, 207, 207, 255)
    # 3x3 raster (matches the app's logo.svg)
    grid = [
        [GRAY, ACCENT, GRAY],
        [ACCENT, LIGHT, GRAY],
        [GRAY, GRAY, ACCENT],
    ]
    for row in range(3):
        for col in range(3):
            cell(col, row, grid[row][col])
    return img


def run_tray(settings):
    """Set up the system tray icon using pystray."""
    import pystray
    from pystray import MenuItem, Menu

    # Mutable container so callbacks can update the icon reference
    icon_ref = [None]

    def open_browser(icon, item):
        open_url(get_display_url(settings), settings)

    def quit_app(icon, item):
        icon.stop()
        os._exit(0)

    # Network interface submenu
    def make_iface_callback(ip):
        def callback(icon, item):
            settings['interface'] = ip
            save_settings(settings)
            # Restart server with new interface
            restart_flask_server(settings)
            # Rebuild tray menu to update status and checkmarks
            if icon_ref[0]:
                icon_ref[0].menu = build_menu()
                icon_ref[0].update_menu()
        return callback

    def iface_checked(ip):
        def check(item):
            return settings.get('interface', '127.0.0.1') == ip
        return check

    def toggle_https(icon, item):
        enabled = not settings.get('https_enabled', False)
        settings['https_enabled'] = enabled
        save_settings(settings)

        if enabled:
            # Generate certs if needed
            try:
                from launcher_settings import ssl_certs_exist, generate_ssl_certs
                if not ssl_certs_exist():
                    generate_ssl_certs()
            except RuntimeError as e:
                settings['https_enabled'] = False
                save_settings(settings)
                print(f'[HTTPS] Setup failed: {e}')
                return

        # Restart server with new protocol
        restart_flask_server(settings)
        # Rebuild tray menu to update status
        if icon_ref[0]:
            icon_ref[0].menu = build_menu()
            icon_ref[0].update_menu()

    def https_checked(item):
        return settings.get('https_enabled', False)

    # Browser selection submenu
    def make_browser_callback(key):
        def callback(icon, item):
            settings['browser'] = key
            save_settings(settings)
            if icon_ref[0]:
                icon_ref[0].menu = build_menu()
                icon_ref[0].update_menu()
        return callback

    def browser_checked(key):
        def check(item):
            return settings.get('browser', 'default') == key
        return check

    def toggle_open_on_launch(icon, item):
        settings['open_browser_on_launch'] = not settings.get('open_browser_on_launch', False)
        save_settings(settings)

    def open_on_launch_checked(item):
        return settings.get('open_browser_on_launch', False)

    def build_menu():
        interfaces = get_network_interfaces()
        iface_items = []
        for ip, label in interfaces:
            iface_items.append(
                MenuItem(label, make_iface_callback(ip), checked=iface_checked(ip))
            )

        browser_items = [
            MenuItem(label, make_browser_callback(key), checked=browser_checked(key), radio=True)
            for key, label in get_available_browsers()
        ]

        host = settings.get('interface', '127.0.0.1')
        port = settings.get('port', 8050)
        display_host = host if host != '0.0.0.0' else '127.0.0.1'
        protocol = 'https' if settings.get('https_enabled', False) else 'http'

        def toggle_run_at_login(icon, item):
            enabled = not settings.get('run_at_login', False)
            settings['run_at_login'] = enabled
            save_settings(settings)
            set_run_at_login(enabled)

        def run_at_login_checked(item):
            return settings.get('run_at_login', False)

        return Menu(
            MenuItem('Open in Browser', open_browser, default=True),
            MenuItem('Open With', Menu(*browser_items)),
            MenuItem('Open Browser on Launch', toggle_open_on_launch,
                     checked=open_on_launch_checked),
            Menu.SEPARATOR,
            MenuItem('Network', Menu(*iface_items)),
            MenuItem(f'Port: {port}', None, enabled=False),
            MenuItem('HTTPS (SSL)', toggle_https, checked=https_checked),
            Menu.SEPARATOR,
            MenuItem(f'Running on {protocol}://{display_host}:{port}', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Run at Login', toggle_run_at_login,
                     checked=run_at_login_checked),
            Menu.SEPARATOR,
            MenuItem('Quit LED Raster Designer', quit_app),
        )

    icon = pystray.Icon(
        name='LED Raster Designer',
        icon=create_tray_icon_image(),
        title='LED Raster Designer',
        menu=build_menu()
    )
    icon_ref[0] = icon

    # icon.run() blocks on the main thread
    icon.run()


def main():
    settings = load_settings()

    # Start Flask in a background daemon thread
    server_thread = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    server_thread.start()

    # Give the server a moment to start
    time.sleep(1.5)

    # Auto-open the GUI in the chosen browser, unless the user turned that off
    if settings.get('open_browser_on_launch', False):
        open_url(get_display_url(settings), settings)

    # Run the system tray (blocks main thread)
    run_tray(settings)


if __name__ == '__main__':
    main()
