"""
LED Raster Designer - Windows/Linux System Tray Launcher
Runs the Flask server in the background and provides a system tray icon
with settings for network interface, port, start minimized, and run at login.
"""
import sys
import os
import threading
import webbrowser
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
    load_settings, save_settings, get_network_interfaces, set_run_at_login
)


def start_flask_server(settings):
    """Import and run the Flask app in a background thread."""
    host = settings.get('interface', '127.0.0.1')
    port = int(settings.get('port', 8050))

    from app import app, socketio, log_event
    log_event('server_start', {
        'port': port,
        'host': host,
        'launcher': 'pc_systray',
        'log_dir': os.environ.get('_LRD_LOG_DIR', 'unknown'),
    })
    socketio.run(app, host=host, port=port, debug=False,
                 allow_unsafe_werkzeug=True)


def get_display_url(settings):
    """Build the display URL from settings."""
    host = settings.get('interface', '127.0.0.1')
    port = settings.get('port', 8050)
    display_host = host if host != '0.0.0.0' else '127.0.0.1'
    return f'http://{display_host}:{port}'


def create_tray_icon_image():
    """Create a lightbulb icon programmatically."""
    from PIL import Image, ImageDraw

    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Bulb (yellow circle)
    draw.ellipse([16, 4, 48, 36], fill='#FFD700', outline='#FFA500', width=2)
    # Base (gray rectangle)
    draw.rectangle([22, 34, 42, 44], fill='#808080', outline='#606060', width=1)
    draw.rectangle([24, 44, 40, 48], fill='#707070', outline='#606060', width=1)
    # Screw tip
    draw.polygon([(28, 48), (36, 48), (32, 56)], fill='#606060')
    # Light rays
    draw.line([32, 0, 32, 4], fill='#FFD700', width=2)
    draw.line([8, 20, 14, 20], fill='#FFD700', width=2)
    draw.line([50, 20, 56, 20], fill='#FFD700', width=2)
    draw.line([14, 8, 18, 12], fill='#FFD700', width=2)
    draw.line([50, 8, 46, 12], fill='#FFD700', width=2)

    return img


def run_tray(settings):
    """Set up the system tray icon using pystray."""
    import pystray
    from pystray import MenuItem, Menu

    def open_browser(icon, item):
        webbrowser.open(get_display_url(settings))

    def quit_app(icon, item):
        icon.stop()
        os._exit(0)

    # Network interface submenu
    interfaces = get_network_interfaces()
    current_iface = settings.get('interface', '127.0.0.1')

    def make_iface_callback(ip):
        def callback(icon, item):
            settings['interface'] = ip
            save_settings(settings)
            # Can't easily restart server from tray — notify user
        return callback

    def iface_checked(ip):
        def check(item):
            return settings.get('interface', '127.0.0.1') == ip
        return check

    iface_items = []
    for ip, label in interfaces:
        iface_items.append(
            MenuItem(label, make_iface_callback(ip), checked=iface_checked(ip))
        )

    # Port display
    host = settings.get('interface', '127.0.0.1')
    port = settings.get('port', 8050)
    display_host = host if host != '0.0.0.0' else '127.0.0.1'

    # Toggle callbacks
    def toggle_run_at_login(icon, item):
        enabled = not settings.get('run_at_login', False)
        settings['run_at_login'] = enabled
        save_settings(settings)
        set_run_at_login(enabled)

    def run_at_login_checked(item):
        return settings.get('run_at_login', False)

    icon = pystray.Icon(
        name='LED Raster Designer',
        icon=create_tray_icon_image(),
        title='LED Raster Designer',
        menu=Menu(
            MenuItem('Open in Browser', open_browser, default=True),
            Menu.SEPARATOR,
            MenuItem('Network', Menu(*iface_items)),
            MenuItem(f'Port: {port}', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(f'Running on {display_host}:{port}', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Run at Login', toggle_run_at_login,
                     checked=run_at_login_checked),
            Menu.SEPARATOR,
            MenuItem('Quit LED Raster Designer', quit_app),
        )
    )

    # icon.run() blocks on the main thread
    icon.run()


def main():
    settings = load_settings()

    # Start Flask in a background daemon thread
    server_thread = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    server_thread.start()

    # Give the server a moment to start
    time.sleep(1.5)

    # Auto-open browser on launch
    webbrowser.open(get_display_url(settings))

    # Run the system tray (blocks main thread)
    run_tray(settings)


if __name__ == '__main__':
    main()
