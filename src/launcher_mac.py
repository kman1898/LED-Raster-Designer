"""
LED Raster Designer - macOS Menu Bar Launcher
Runs the Flask server in the background and provides a menu bar icon
with Open Browser, status info, and Quit.
"""
import sys
import os
import threading
import webbrowser
import signal
import time

# Resolve paths for PyInstaller bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BASE_DIR

PORT = 8050
URL = f'http://localhost:{PORT}'

def start_flask_server():
    """Import and run the Flask app in a background thread."""
    # Add base dir to path so app module can be found
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    
    from app import app, socketio, log_event
    log_event('server_start', {'port': PORT, 'launcher': 'mac_menubar', 'log_dir': os.environ.get('_LRD_LOG_DIR', 'unknown')})
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)

def run_menubar():
    """Set up the macOS menu bar icon using rumps."""
    import rumps

    class LEDRasterDesignerApp(rumps.App):
        def __init__(self):
            super().__init__(
                name="LED Raster Designer",
                title="💡",  # Menu bar icon (emoji for now, can swap for .icns later)
                quit_button=None,  # We'll make our own quit button
            )
            self.menu = [
                rumps.MenuItem('Open in Browser', callback=self.open_browser),
                None,  # Separator
                rumps.MenuItem(f'Server running on port {PORT}'),
                None,  # Separator
                rumps.MenuItem('Quit LED Raster Designer', callback=self.quit_app),
            ]
            # Disable the status item so it's not clickable
            self.menu[f'Server running on port {PORT}'].set_callback(None)

        def open_browser(self, _):
            webbrowser.open(URL)

        def quit_app(self, _):
            rumps.quit_application()
            # Force kill to ensure Flask thread dies
            os._exit(0)

    app = LEDRasterDesignerApp()
    app.run()

def main():
    # Start Flask in a background daemon thread
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()
    
    # Give the server a moment to start
    time.sleep(1.0)
    
    # Auto-open browser on first launch
    webbrowser.open(URL)
    
    # Run the menu bar app (this blocks on the main thread)
    run_menubar()

if __name__ == '__main__':
    main()
