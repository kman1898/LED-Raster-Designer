"""
LED Raster Designer - Launcher Settings
Handles settings persistence, network interface detection, and Run at Login.
"""
import json
import os
import sys
import socket
import platform

DEFAULTS = {
    'port': 8050,
    'interface': '127.0.0.1',
    'start_minimized': False,
    'run_at_login': False,
}

APP_NAME = 'LED Raster Designer'
BUNDLE_ID = 'com.ledrasterdesigner.app'


def get_config_dir():
    """Return the platform-appropriate config directory, creating it if needed."""
    if sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    elif sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.expanduser('~/.config')
    config_dir = os.path.join(base, APP_NAME)
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _settings_path():
    return os.path.join(get_config_dir(), 'settings.json')


def load_settings():
    """Load settings from disk, falling back to defaults."""
    path = _settings_path()
    settings = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, IOError):
            pass
    return settings


def save_settings(settings):
    """Save settings to disk."""
    path = _settings_path()
    try:
        with open(path, 'w') as f:
            json.dump(settings, f, indent=2)
    except IOError:
        pass


def get_network_interfaces():
    """
    Return a list of (ip, label) tuples for available network interfaces.
    Always includes 127.0.0.1 first and 0.0.0.0 (All Interfaces) second.
    """
    interfaces = [
        ('127.0.0.1', '127.0.0.1 (localhost)'),
        ('0.0.0.0', 'All Interfaces'),
    ]
    seen = {'127.0.0.1', '0.0.0.0'}

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in seen:
                seen.add(ip)
                interfaces.append((ip, f'{ip} ({hostname})'))
    except (socket.gaierror, OSError):
        pass

    # Also try the connect-to-8.8.8.8 trick to find the default route IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        route_ip = s.getsockname()[0]
        s.close()
        if route_ip not in seen:
            seen.add(route_ip)
            interfaces.append((route_ip, f'{route_ip} (default route)'))
    except (OSError, socket.error):
        pass

    return interfaces


def set_run_at_login(enabled, exe_path=None):
    """Enable or disable Run at Login for the current platform."""
    if exe_path is None:
        exe_path = sys.executable

    if sys.platform == 'darwin':
        _set_run_at_login_mac(enabled, exe_path)
    elif sys.platform == 'win32':
        _set_run_at_login_win(enabled, exe_path)


def _set_run_at_login_mac(enabled, exe_path):
    """Manage macOS LaunchAgent plist."""
    plist_dir = os.path.expanduser('~/Library/LaunchAgents')
    plist_path = os.path.join(plist_dir, f'{BUNDLE_ID}.plist')

    if enabled:
        # If inside a .app bundle, reference the .app itself
        if '.app/' in exe_path:
            app_path = exe_path[:exe_path.index('.app/') + 4]
            program_args = ['open', app_path]
        else:
            program_args = [exe_path]

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{BUNDLE_ID}</string>
    <key>ProgramArguments</key>
    <array>
        {''.join(f'<string>{a}</string>' for a in program_args)}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        os.makedirs(plist_dir, exist_ok=True)
        with open(plist_path, 'w') as f:
            f.write(plist_content)
    else:
        if os.path.exists(plist_path):
            os.remove(plist_path)


def _set_run_at_login_win(enabled, exe_path):
    """Manage Windows registry Run key."""
    try:
        import winreg
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                             winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except ImportError:
        pass  # winreg not available (not on Windows)
    except OSError:
        pass
