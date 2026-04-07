"""
LED Raster Designer - Launcher Settings
Handles settings persistence, network interface detection, SSL cert generation,
and Run at Login.
"""
import json
import os
import sys
import socket
import platform
import subprocess

DEFAULTS = {
    'port': 8050,
    'interface': '127.0.0.1',
    'run_at_login': False,
    'https_enabled': False,
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


# ── SSL Certificate Management ──────────────────────────────────────────────

def get_ssl_cert_paths():
    """Return (cert_path, key_path) in the config directory."""
    config_dir = get_config_dir()
    return (
        os.path.join(config_dir, 'server.crt'),
        os.path.join(config_dir, 'server.key'),
    )


def ssl_certs_exist():
    """Check if SSL certificate and key files exist."""
    cert_path, key_path = get_ssl_cert_paths()
    return os.path.exists(cert_path) and os.path.exists(key_path)


def generate_ssl_certs():
    """
    Generate a self-signed SSL certificate and key using openssl.
    The cert is valid for 10 years and includes SANs for localhost and
    common LAN IP ranges so browsers accept it for LAN access.
    Returns (cert_path, key_path) on success, or raises RuntimeError.
    """
    cert_path, key_path = get_ssl_cert_paths()

    # Build SAN entries: localhost + all current LAN IPs
    san_entries = ['DNS:localhost', 'IP:127.0.0.1', 'IP:0.0.0.0']
    for ip, _label in get_network_interfaces():
        entry = f'IP:{ip}'
        if entry not in san_entries:
            san_entries.append(entry)
    san_string = ','.join(san_entries)

    # Find openssl binary
    openssl_bin = _find_openssl()
    if not openssl_bin:
        raise RuntimeError(
            'OpenSSL not found. Install OpenSSL to enable HTTPS.\n'
            'macOS: Already included with the system.\n'
            'Windows: Install Git for Windows (includes OpenSSL) or download from slproweb.com'
        )

    try:
        result = subprocess.run([
            openssl_bin, 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key_path, '-out', cert_path,
            '-days', '3650', '-nodes',
            '-subj', '/CN=LED Raster Designer',
            '-addext', f'subjectAltName={san_string}',
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise RuntimeError(f'OpenSSL failed: {result.stderr.strip()}')

        # Restrict key file permissions (owner-only read/write)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass  # Windows doesn't support chmod the same way

        return cert_path, key_path

    except FileNotFoundError:
        raise RuntimeError('OpenSSL binary not found.')
    except subprocess.TimeoutExpired:
        raise RuntimeError('OpenSSL timed out generating certificate.')


def regenerate_ssl_certs():
    """Delete existing certs and generate new ones."""
    cert_path, key_path = get_ssl_cert_paths()
    for path in (cert_path, key_path):
        if os.path.exists(path):
            os.remove(path)
    return generate_ssl_certs()


def get_ssl_context(settings):
    """
    Return an ssl_context tuple (cert, key) if HTTPS is enabled and certs exist,
    otherwise return None. Auto-generates certs on first use.
    """
    if not settings.get('https_enabled', False):
        return None

    if not ssl_certs_exist():
        try:
            generate_ssl_certs()
        except RuntimeError as e:
            print(f'[HTTPS] Failed to generate SSL certificate: {e}')
            print('[HTTPS] Falling back to HTTP.')
            return None

    cert_path, key_path = get_ssl_cert_paths()
    return (cert_path, key_path)


def _find_openssl():
    """Find the openssl binary on the system."""
    # Check common locations
    candidates = ['openssl']
    if sys.platform == 'win32':
        # Git for Windows includes openssl
        git_ssl = os.path.join(
            os.environ.get('ProgramFiles', 'C:\\Program Files'),
            'Git', 'usr', 'bin', 'openssl.exe'
        )
        candidates.append(git_ssl)
        git_ssl_x86 = os.path.join(
            os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
            'Git', 'usr', 'bin', 'openssl.exe'
        )
        candidates.append(git_ssl_x86)

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, 'version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue

    return None


# ── Network Interface Detection ─────────────────────────────────────────────

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


# ── Run at Login ─────────────────────────────────────────────────────────────

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
