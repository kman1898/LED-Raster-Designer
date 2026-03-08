"""
LED Raster Designer - Windows System Tray Launcher
Runs the Flask server in the background and provides a system tray icon
with Open Browser, status info, and Quit.
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

PORT = 8050
URL = f'http://localhost:{PORT}'

def start_flask_server():
    """Import and run the Flask app in a background thread."""
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    
    from app import app, socketio, log_event
    log_event('server_start', {'port': PORT, 'launcher': 'pc_systray', 'log_dir': os.environ.get('_LRD_LOG_DIR', 'unknown')})
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)

def create_tray_icon():
    """Create a lightbulb icon programmatically (no external image needed)."""
    from PIL import Image, ImageDraw
    
    # Create a 64x64 icon with a lightbulb shape
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

def run_tray():
    """Set up the Windows system tray icon using pystray."""
    import pystray
    from pystray import MenuItem, Menu
    
    def open_browser(icon, item):
        webbrowser.open(URL)
    
    def quit_app(icon, item):
        icon.stop()
        os._exit(0)
    
    icon = pystray.Icon(
        name="LED Raster Designer",
        icon=create_tray_icon(),
        title="LED Raster Designer",
        menu=Menu(
            MenuItem('Open in Browser', open_browser, default=True),
            Menu.SEPARATOR,
            MenuItem(f'Server running on port {PORT}', None, enabled=False),
            Menu.SEPARATOR,
            MenuItem('Quit LED Raster Designer', quit_app),
        )
    )
    
    # icon.run() blocks on the main thread
    icon.run()

def main():
    # Start Flask in a background daemon thread
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()
    
    # Give the server a moment to start
    time.sleep(1.5)
    
    # Auto-open browser on first launch
    webbrowser.open(URL)
    
    # Run the system tray (blocks main thread)
    run_tray()

if __name__ == '__main__':
    main()
