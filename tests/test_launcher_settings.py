"""Tests for launcher_settings module."""
import json
import os
import sys
import tempfile
import pytest

# Add src to path so we can import launcher_settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import launcher_settings


class TestGetConfigDir:
    """Tests for config directory resolution."""

    def test_returns_string(self):
        result = launcher_settings.get_config_dir()
        assert isinstance(result, str)

    def test_directory_exists(self):
        result = launcher_settings.get_config_dir()
        assert os.path.isdir(result)

    def test_contains_app_name(self):
        result = launcher_settings.get_config_dir()
        assert launcher_settings.APP_NAME in result


class TestLoadSaveSettings:
    """Tests for settings persistence."""

    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher_settings, 'get_config_dir', lambda: str(tmp_path))
        settings = launcher_settings.load_settings()
        assert settings['port'] == 8050
        assert settings['interface'] == '127.0.0.1'
        assert settings['run_at_login'] is False

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher_settings, 'get_config_dir', lambda: str(tmp_path))
        settings = {
            'port': 9090,
            'interface': '192.168.1.100',
            'run_at_login': False,
        }
        launcher_settings.save_settings(settings)
        loaded = launcher_settings.load_settings()
        assert loaded['port'] == 9090
        assert loaded['interface'] == '192.168.1.100'
        assert loaded['run_at_login'] is False

    def test_load_handles_corrupted_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher_settings, 'get_config_dir', lambda: str(tmp_path))
        settings_path = os.path.join(str(tmp_path), 'settings.json')
        with open(settings_path, 'w') as f:
            f.write('not valid json {{{')
        settings = launcher_settings.load_settings()
        # Should fall back to defaults
        assert settings['port'] == 8050

    def test_load_merges_partial_settings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher_settings, 'get_config_dir', lambda: str(tmp_path))
        # Save only port
        settings_path = os.path.join(str(tmp_path), 'settings.json')
        with open(settings_path, 'w') as f:
            json.dump({'port': 1234}, f)
        loaded = launcher_settings.load_settings()
        assert loaded['port'] == 1234
        # Other fields should have defaults
        assert loaded['interface'] == '127.0.0.1'

    def test_save_creates_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher_settings, 'get_config_dir', lambda: str(tmp_path))
        launcher_settings.save_settings({'port': 5555, 'interface': '0.0.0.0'})
        settings_path = os.path.join(str(tmp_path), 'settings.json')
        with open(settings_path, 'r') as f:
            data = json.load(f)
        assert data['port'] == 5555
        assert data['interface'] == '0.0.0.0'


class TestGetNetworkInterfaces:
    """Tests for network interface detection.

    Uses a class-level fixture to call get_network_interfaces() only once,
    since socket.getaddrinfo can be very slow (~35s) on macOS CI runners.
    """

    @pytest.fixture(scope='class')
    def interfaces(self):
        return launcher_settings.get_network_interfaces()

    def test_returns_list(self, interfaces):
        assert isinstance(interfaces, list)

    def test_always_includes_localhost(self, interfaces):
        ips = [ip for ip, _ in interfaces]
        assert '127.0.0.1' in ips

    def test_always_includes_all_interfaces(self, interfaces):
        ips = [ip for ip, _ in interfaces]
        assert '0.0.0.0' in ips

    def test_localhost_is_first(self, interfaces):
        assert interfaces[0][0] == '127.0.0.1'

    def test_all_interfaces_is_second(self, interfaces):
        assert interfaces[1][0] == '0.0.0.0'

    def test_returns_tuples_of_ip_and_label(self, interfaces):
        for item in interfaces:
            assert len(item) == 2
            ip, label = item
            assert isinstance(ip, str)
            assert isinstance(label, str)

    def test_no_duplicate_ips(self, interfaces):
        ips = [ip for ip, _ in interfaces]
        assert len(ips) == len(set(ips))


class TestDefaults:
    """Tests for default values."""

    def test_default_port(self):
        assert launcher_settings.DEFAULTS['port'] == 8050

    def test_default_interface(self):
        assert launcher_settings.DEFAULTS['interface'] == '127.0.0.1'

    def test_default_run_at_login(self):
        assert launcher_settings.DEFAULTS['run_at_login'] is False


class TestRunAtLogin:
    """Tests for Run at Login functionality."""

    @pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only')
    def test_mac_plist_creation(self, tmp_path, monkeypatch):
        home = str(tmp_path)
        plist_dir = os.path.join(home, 'Library', 'LaunchAgents')
        plist_path = os.path.join(plist_dir, f'{launcher_settings.BUNDLE_ID}.plist')
        original_expanduser = os.path.expanduser
        monkeypatch.setattr(os.path, 'expanduser',
                            lambda p: p.replace('~', home) if p.startswith('~') else original_expanduser(p))
        launcher_settings.set_run_at_login(True, '/usr/bin/python3')
        assert os.path.exists(plist_path)
        with open(plist_path, 'r') as f:
            content = f.read()
        assert 'RunAtLoad' in content
        assert launcher_settings.BUNDLE_ID in content

    @pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only')
    def test_mac_plist_removal(self, tmp_path, monkeypatch):
        home = str(tmp_path)
        plist_dir = os.path.join(home, 'Library', 'LaunchAgents')
        os.makedirs(plist_dir, exist_ok=True)
        plist_path = os.path.join(plist_dir, f'{launcher_settings.BUNDLE_ID}.plist')
        with open(plist_path, 'w') as f:
            f.write('<plist></plist>')
        original_expanduser = os.path.expanduser
        monkeypatch.setattr(os.path, 'expanduser',
                            lambda p: p.replace('~', home) if p.startswith('~') else original_expanduser(p))
        launcher_settings.set_run_at_login(False, '/usr/bin/python3')
        assert not os.path.exists(plist_path)

    @pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only')
    def test_mac_app_bundle_path_detection(self, tmp_path, monkeypatch):
        home = str(tmp_path)
        plist_dir = os.path.join(home, 'Library', 'LaunchAgents')
        plist_path = os.path.join(plist_dir, f'{launcher_settings.BUNDLE_ID}.plist')
        original_expanduser = os.path.expanduser
        monkeypatch.setattr(os.path, 'expanduser',
                            lambda p: p.replace('~', home) if p.startswith('~') else original_expanduser(p))
        exe_path = '/Applications/LED Raster Designer.app/Contents/MacOS/LED Raster Designer'
        launcher_settings.set_run_at_login(True, exe_path)
        with open(plist_path, 'r') as f:
            content = f.read()
        assert 'open' in content
        assert '.app' in content
