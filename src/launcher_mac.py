"""
LED Raster Designer - macOS Menu Bar Launcher
Runs the Flask server in the background and provides a menu bar icon
with settings for network interface, port, HTTPS, start minimized, and run at login.
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
        'launcher': 'mac_menubar',
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


def _create_menubar_icon():
    """Draw the LED Raster Designer mark as a monochrome menu-bar template
    icon (black pixels; macOS recolors it for light/dark menu bars). Returns
    a temp file path."""
    from PIL import Image, ImageDraw
    import tempfile, os
    S = 44
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    k = S / 48.0
    lit = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0, 2), (2, 2)}
    for col in range(3):
        for row in range(3):
            if (col, row) not in lit:
                continue
            x = (11 + col * 9) * k
            y = (11 + row * 9) * k
            s = 8 * k
            try:
                draw.rounded_rectangle([x, y, x + s, y + s], radius=2 * k, fill=(0, 0, 0, 255))
            except AttributeError:
                draw.rectangle([x, y, x + s, y + s], fill=(0, 0, 0, 255))
    path = os.path.join(tempfile.gettempdir(), 'lrd_menubar.png')
    img.save(path)
    return path


def run_menubar(settings):
    """Set up the macOS menu bar icon using rumps."""
    import rumps

    class LEDRasterDesignerApp(rumps.App):
        def __init__(self):
            kwargs = dict(name='LED Raster Designer', quit_button=None)
            try:
                kwargs['icon'] = _create_menubar_icon()
                kwargs['template'] = True
            except Exception:
                kwargs['title'] = 'LRD'  # fallback if drawing fails
            super().__init__(**kwargs)
            self.settings = settings
            self._build_menu()

        def _build_menu(self):
            """Build the full menu with current settings."""
            # Network interface submenu
            interfaces = get_network_interfaces()
            current_iface = self.settings.get('interface', '127.0.0.1')
            iface_items = []
            for ip, label in interfaces:
                item = rumps.MenuItem(label, callback=self._make_iface_callback(ip))
                item.state = 1 if ip == current_iface else 0
                iface_items.append(item)

            network_menu = rumps.MenuItem('Network')
            for item in iface_items:
                network_menu.add(item)

            # Port item
            port = self.settings.get('port', 8050)
            port_item = rumps.MenuItem(f'Port: {port}', callback=self._change_port)

            # HTTPS toggle
            https_item = rumps.MenuItem('HTTPS (SSL)', callback=self._toggle_https)
            https_item.state = 1 if self.settings.get('https_enabled', False) else 0

            # Status (disabled)
            protocol = 'https' if self.settings.get('https_enabled', False) else 'http'
            host = self.settings.get('interface', '127.0.0.1')
            display_host = host if host != '0.0.0.0' else '127.0.0.1'
            status_item = rumps.MenuItem(f'Running on {protocol}://{display_host}:{port}')
            status_item.set_callback(None)

            # Browser selection submenu
            current_browser = self.settings.get('browser', 'default')
            browser_menu = rumps.MenuItem('Open With')
            for key, label in get_available_browsers():
                b_item = rumps.MenuItem(label, callback=self._make_browser_callback(key))
                b_item.state = 1 if key == current_browser else 0
                browser_menu.add(b_item)

            open_on_launch = rumps.MenuItem('Open Browser on Launch',
                                            callback=self._toggle_open_on_launch)
            open_on_launch.state = 1 if self.settings.get('open_browser_on_launch', False) else 0

            # Toggles
            run_login = rumps.MenuItem('Run at Login', callback=self._toggle_run_at_login)
            run_login.state = 1 if self.settings.get('run_at_login', False) else 0

            self.menu.clear()
            self.menu = [
                rumps.MenuItem('Open in Browser', callback=self._open_browser),
                browser_menu,
                open_on_launch,
                None,  # separator
                network_menu,
                port_item,
                https_item,
                None,  # separator
                status_item,
                None,  # separator
                run_login,
                None,  # separator
                rumps.MenuItem('Quit LED Raster Designer', callback=self._quit_app),
            ]

        def _open_browser(self, _):
            open_url(get_display_url(self.settings), self.settings)

        def _make_browser_callback(self, key):
            def callback(sender):
                self.settings['browser'] = key
                save_settings(self.settings)
                for item in sender.parent.values():
                    if isinstance(item, rumps.MenuItem):
                        item.state = 0
                sender.state = 1
            return callback

        def _toggle_open_on_launch(self, sender):
            sender.state = not sender.state
            self.settings['open_browser_on_launch'] = bool(sender.state)
            save_settings(self.settings)

        def _make_iface_callback(self, ip):
            """Create a callback for a specific interface selection."""
            def callback(sender):
                self.settings['interface'] = ip
                save_settings(self.settings)
                # Update menu checkmarks
                for item in sender.parent.values():
                    if isinstance(item, rumps.MenuItem):
                        item.state = 0
                sender.state = 1
                # Restart server with new interface
                restart_flask_server(self.settings)
                # Update status in menu
                self._build_menu()
                rumps.notification(
                    'LED Raster Designer',
                    'Network interface changed',
                    f'Server restarted on {ip}',
                )
            return callback

        def _change_port(self, sender):
            """Prompt for a new port number."""
            response = rumps.Window(
                message='Enter a port number (1024-65535):',
                title='Change Port',
                default_text=str(self.settings.get('port', 8050)),
                ok='Change',
                cancel='Cancel',
                dimensions=(200, 24),
            ).run()

            if response.clicked:
                try:
                    new_port = int(response.text.strip())
                    if 1024 <= new_port <= 65535:
                        self.settings['port'] = new_port
                        save_settings(self.settings)
                        # Restart server with new port
                        restart_flask_server(self.settings)
                        self._build_menu()
                        rumps.notification(
                            'LED Raster Designer',
                            'Port changed',
                            f'Server restarted on port {new_port}',
                        )
                    else:
                        rumps.notification(
                            'LED Raster Designer',
                            'Invalid port',
                            'Port must be between 1024 and 65535.',
                        )
                except ValueError:
                    rumps.notification(
                        'LED Raster Designer',
                        'Invalid port',
                        'Please enter a valid number.',
                    )

        def _toggle_https(self, sender):
            """Toggle HTTPS on/off."""
            sender.state = not sender.state
            enabled = bool(sender.state)
            self.settings['https_enabled'] = enabled
            save_settings(self.settings)

            if enabled:
                # Generate certs if needed
                try:
                    from launcher_settings import ssl_certs_exist, generate_ssl_certs
                    if not ssl_certs_exist():
                        generate_ssl_certs()
                except RuntimeError as e:
                    sender.state = 0
                    self.settings['https_enabled'] = False
                    save_settings(self.settings)
                    rumps.notification(
                        'LED Raster Designer',
                        'HTTPS setup failed',
                        str(e),
                    )
                    return

            # Restart server with new protocol
            restart_flask_server(self.settings)
            self._build_menu()
            protocol = 'HTTPS' if enabled else 'HTTP'
            rumps.notification(
                'LED Raster Designer',
                f'{protocol} enabled',
                f'Server restarted with {protocol}',
            )

        def _toggle_run_at_login(self, sender):
            sender.state = not sender.state
            enabled = bool(sender.state)
            self.settings['run_at_login'] = enabled
            save_settings(self.settings)
            set_run_at_login(enabled)

        def _quit_app(self, _):
            rumps.quit_application()
            os._exit(0)

    app = LEDRasterDesignerApp()
    app.run()


def main():
    settings = load_settings()

    # Start Flask in a background daemon thread
    server_thread = threading.Thread(target=start_flask_server, args=(settings,), daemon=True)
    server_thread.start()

    # Give the server a moment to start
    time.sleep(1.0)

    # Auto-open the GUI in the chosen browser, unless the user turned that off
    if settings.get('open_browser_on_launch', False):
        open_url(get_display_url(settings), settings)

    # Run the menu bar app (blocks on main thread, required by macOS)
    run_menubar(settings)


if __name__ == '__main__':
    main()
