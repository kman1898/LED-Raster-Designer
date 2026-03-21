"""
LED Raster Designer - macOS Menu Bar Launcher
Runs the Flask server in the background and provides a menu bar icon
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
        'launcher': 'mac_menubar',
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


def run_menubar(settings):
    """Set up the macOS menu bar icon using rumps."""
    import rumps

    class LEDRasterDesignerApp(rumps.App):
        def __init__(self):
            super().__init__(
                name='LED Raster Designer',
                title='💡',
                quit_button=None,
            )
            self.settings = settings
            self._build_menu()

        def _build_menu(self):
            """Build the full menu with current settings."""
            url = get_display_url(self.settings)

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

            # Status (disabled)
            host = self.settings.get('interface', '127.0.0.1')
            display_host = host if host != '0.0.0.0' else '127.0.0.1'
            status_item = rumps.MenuItem(f'Running on {display_host}:{port}')
            status_item.set_callback(None)

            # Toggles
            run_login = rumps.MenuItem('Run at Login', callback=self._toggle_run_at_login)
            run_login.state = 1 if self.settings.get('run_at_login', False) else 0

            self.menu.clear()
            self.menu = [
                rumps.MenuItem('Open in Browser', callback=self._open_browser),
                None,  # separator
                network_menu,
                port_item,
                None,  # separator
                status_item,
                None,  # separator
                run_login,
                None,  # separator
                rumps.MenuItem('Quit LED Raster Designer', callback=self._quit_app),
            ]

        def _open_browser(self, _):
            webbrowser.open(get_display_url(self.settings))

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
                rumps.notification(
                    'LED Raster Designer',
                    'Network interface changed',
                    f'Restart the app for the change to take effect.\nNew interface: {ip}',
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
                        rumps.notification(
                            'LED Raster Designer',
                            'Port changed',
                            f'Restart the app for the change to take effect.\nNew port: {new_port}',
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

    # Auto-open browser on launch
    webbrowser.open(get_display_url(settings))

    # Run the menu bar app (blocks on main thread — required by macOS)
    run_menubar(settings)


if __name__ == '__main__':
    main()
