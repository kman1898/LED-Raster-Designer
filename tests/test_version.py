"""Tests for version endpoint and updater module."""

import sys
import os
import re
import tempfile
import hashlib
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')

from updater import _parse_version, verify_download, get_current_version


# ── _parse_version ──────────────────────────────────────────────────

def test_parse_version_standard():
    assert _parse_version('0.6.2') == (0, 6, 2)


def test_parse_version_four_part():
    assert _parse_version('0.6.2.1') == (0, 6, 2, 1)


def test_parse_version_with_v_prefix():
    assert _parse_version('v1.2.3') == (1, 2, 3)


def test_parse_version_none():
    assert _parse_version(None) == ()


def test_parse_version_empty():
    assert _parse_version('') == ()


def test_parse_version_invalid():
    assert _parse_version('abc.def') == ()


def test_parse_version_comparison():
    """Newer version tuples compare correctly."""
    assert _parse_version('0.6.3') > _parse_version('0.6.2')
    assert _parse_version('1.0.0') > _parse_version('0.99.99')
    assert _parse_version('0.6.2.1') > _parse_version('0.6.2')


# ── verify_download ─────────────────────────────────────────────────

def test_verify_download_valid():
    """File with matching SHA-256 returns True."""
    content = b'hello world'
    expected = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        f.flush()
        assert verify_download(f.name, expected) is True
    os.unlink(f.name)


def test_verify_download_mismatch():
    """File with wrong checksum returns False."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'some data')
        f.flush()
        assert verify_download(f.name, 'deadbeef' * 8) is False
    os.unlink(f.name)


def test_verify_download_missing_file():
    """Non-existent file returns False."""
    assert verify_download('/tmp/nonexistent_test_file_12345.bin', 'abc') is False


def test_verify_download_case_insensitive():
    """SHA-256 comparison is case-insensitive."""
    content = b'test'
    expected = hashlib.sha256(content).hexdigest().upper()

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        f.flush()
        assert verify_download(f.name, expected) is True
    os.unlink(f.name)


# ── get_current_version ─────────────────────────────────────────────

def test_get_current_version_returns_string():
    """get_current_version returns a non-empty string."""
    version = get_current_version()
    assert isinstance(version, str)
    assert len(version) > 0


# ── /api/version endpoint ──────────────────────────────────────────

def test_api_version(client):
    """GET /api/version returns version string."""
    resp = client.get('/api/version')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'version' in data
    assert isinstance(data['version'], str)


# ── /api/update/check endpoint ─────────────────────────────────────

def test_api_update_check(client):
    """GET /api/update/check returns expected fields."""
    with patch('updater.check_for_update') as mock_check:
        mock_check.return_value = {
            'available': False,
            'current_version': '0.6.2',
            'latest_version': '0.6.2',
            'download_url': None,
            'release_notes': None,
            'checksums': None,
            'error': None,
        }
        resp = client.get('/api/update/check')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'available' in data
        assert 'current_version' in data


def test_api_update_check_force(client):
    """GET /api/update/check?force=true passes force flag."""
    with patch('updater.check_for_update') as mock_check:
        mock_check.return_value = {
            'available': False,
            'current_version': '0.6.2',
            'latest_version': None,
            'download_url': None,
            'release_notes': None,
            'checksums': None,
            'error': None,
        }
        resp = client.get('/api/update/check?force=true')
        assert resp.status_code == 200


# ── Version consistency across all sources ────────────────────────

def _extract_version(text):
    """Extract a version like 0.6.3.6 from text (with or without v prefix)."""
    m = re.search(r'v?(\d+\.\d+\.\d+(?:\.\d+)?)', text)
    return m.group(1) if m else None


def _read_version_from_file(rel_path, line_number=None):
    """Read a version string from a file, optionally from a specific line."""
    path = os.path.join(ROOT, rel_path)
    with open(path, 'r', encoding='utf-8') as f:
        if line_number is not None:
            lines = f.readlines()
            return _extract_version(lines[line_number - 1])
        return _extract_version(f.read())


def test_version_txt_is_four_part():
    """VERSION.txt must use a 4-part version (e.g. 0.6.3.6), not 3-part."""
    version = _read_version_from_file('src/VERSION.txt')
    assert version is not None, "No version found in VERSION.txt"
    parts = version.split('.')
    assert len(parts) == 4, (
        f"VERSION.txt has {len(parts)}-part version '{version}', expected 4-part (e.g. 0.6.3.6)"
    )


def test_all_version_sources_match():
    """All four version locations must report the same version string."""
    version_txt = _read_version_from_file('src/VERSION.txt')
    index_title = _read_version_from_file('src/templates/index.html', line_number=6)
    index_h1 = _read_version_from_file('src/templates/index.html', line_number=69)
    readme = _read_version_from_file('README.md', line_number=1)

    sources = {
        'src/VERSION.txt': version_txt,
        'index.html <title> (line 6)': index_title,
        'index.html <h1> (line 69)': index_h1,
        'README.md (line 1)': readme,
    }

    # Make sure every source has a version
    for name, ver in sources.items():
        assert ver is not None, f"Could not extract version from {name}"

    # Make sure they all match
    versions = set(sources.values())
    assert len(versions) == 1, (
        f"Version mismatch across sources:\n"
        + "\n".join(f"  {name}: {ver}" for name, ver in sources.items())
    )


def test_updater_reads_correct_version():
    """The updater's get_current_version() must match what's in VERSION.txt."""
    version_txt = _read_version_from_file('src/VERSION.txt')
    updater_version = get_current_version()
    assert updater_version == version_txt, (
        f"Updater reports '{updater_version}' but VERSION.txt has '{version_txt}'"
    )


def test_api_version_matches_version_txt(client):
    """The /api/version endpoint must return the same version as VERSION.txt."""
    version_txt = _read_version_from_file('src/VERSION.txt')
    resp = client.get('/api/version')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['version'] == version_txt, (
        f"/api/version returned '{data['version']}' but VERSION.txt has '{version_txt}'"
    )
