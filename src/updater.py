"""
Secure update checker for LED Raster Designer.

Checks GitHub Releases API over HTTPS for newer versions.
All network requests use certificate verification via certifi.
"""

import os
import sys
import re
import json
import hashlib
import logging
import ssl
import tempfile
import threading
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import certifi

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
GITHUB_OWNER = "kman1898"
GITHUB_REPO = "LED-Raster-Designer"
RELEASES_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

# Cache update checks for this many seconds (default: 1 hour)
_CHECK_INTERVAL = 3600
_cache = {"result": None, "timestamp": 0}
_cache_lock = threading.Lock()


def _get_ssl_context():
    """Create a strict SSL context pinned to certifi's CA bundle."""
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        # Fallback: use system default CA certificates (e.g. if certifi
        # data file is missing in a frozen build)
        logger.warning("certifi CA bundle not found, using system defaults")
        ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _read_version_file():
    """Read the current app version from VERSION.txt."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    version_path = os.path.join(base, 'VERSION.txt')
    try:
        with open(version_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = re.match(r'^v?(\d+\.\d+(?:\.\d+)*)', line.strip())
                if m:
                    return m.group(1)
    except FileNotFoundError:
        logger.warning("VERSION.txt not found at %s", version_path)
    return None


def _parse_version(version_str):
    """Parse a version string like '0.6.2.4' into a tuple of ints."""
    if not version_str:
        return ()
    parts = version_str.lstrip('v').split('.')
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return ()


def get_current_version():
    """Return the current app version string."""
    return _read_version_file() or "0.0.0"


def check_for_update(force=False):
    """
    Check GitHub for a newer release.

    Returns dict with keys:
        available (bool): True if a newer version exists
        current_version (str): Current app version
        latest_version (str): Latest release version (or None)
        download_url (str): Browser URL for the release (or None)
        release_notes (str): Release body text (or None)
        checksums (dict): {filename: sha256} from checksums.txt asset (or None)
        error (str): Error message if check failed (or None)

    Results are cached for _CHECK_INTERVAL seconds unless force=True.
    """
    now = time.time()
    with _cache_lock:
        if not force and _cache["result"] and (now - _cache["timestamp"]) < _CHECK_INTERVAL:
            return _cache["result"]

    current = get_current_version()
    result = {
        "available": False,
        "current_version": current,
        "latest_version": None,
        "download_url": None,
        "release_notes": None,
        "checksums": None,
        "error": None,
    }

    try:
        ctx = _get_ssl_context()
        req = Request(RELEASES_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LED-Raster-Designer/{current}",
        })

        with urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")
        result["latest_version"] = latest
        result["download_url"] = data.get("html_url")
        result["release_notes"] = data.get("body", "")

        # Parse checksums from attached checksums.txt asset
        for asset in data.get("assets", []):
            if asset.get("name") == "checksums.txt":
                checksums = _fetch_checksums(asset["browser_download_url"], ctx)
                if checksums:
                    result["checksums"] = checksums
                break

        # Compare versions
        if _parse_version(latest) > _parse_version(current):
            result["available"] = True

    except HTTPError as e:
        if e.code == 404:
            # No published releases yet, not an error, just nothing to update to
            logger.debug("No published releases found (404)")
        elif e.code == 403:
            result["error"] = "Rate limited, try again later"
            logger.warning("Update check HTTP error: %s", e)
        else:
            result["error"] = f"GitHub API error: {e.code}"
            logger.warning("Update check HTTP error: %s", e)
    except (URLError, OSError) as e:
        result["error"] = f"Network error: {e}"
        logger.warning("Update check network error: %s", e)
    except (json.JSONDecodeError, KeyError) as e:
        result["error"] = f"Invalid response: {e}"
        logger.warning("Update check parse error: %s", e)

    with _cache_lock:
        _cache["result"] = result
        _cache["timestamp"] = now

    return result


def _fetch_checksums(url, ssl_context):
    """Download and parse checksums.txt from a release asset."""
    try:
        req = Request(url, headers={
            "User-Agent": f"LED-Raster-Designer/{get_current_version()}",
        })
        with urlopen(req, timeout=10, context=ssl_context) as resp:
            text = resp.read().decode("utf-8")

        checksums = {}
        for line in text.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                sha256 = parts[0]
                filename = parts[-1].lstrip('*')
                checksums[filename] = sha256
        return checksums
    except Exception as e:
        logger.warning("Failed to fetch checksums: %s", e)
        return None


def verify_download(file_path, expected_sha256):
    """
    Verify a downloaded file against its expected SHA-256 checksum.

    Returns True if the hash matches, False otherwise.
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest().lower() == expected_sha256.lower()
    except (OSError, IOError) as e:
        logger.error("Failed to verify download: %s", e)
        return False
