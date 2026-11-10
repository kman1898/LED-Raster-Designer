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
# A beta reads the whole list: /releases/latest never returns a prerelease,
# and a beta tester is offered the next beta (owner, 2026-11-08).
RELEASES_LIST_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=30"
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


def _read_build_tag():
    """The tag a release build was made from, when it was a prerelease.

    release.yml writes BUILD_TAG.txt ("1.5.3-beta.1") next to VERSION.txt
    only for a beta tag, so a full release and a source run have none.
    """
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, 'BUILD_TAG.txt'), 'r', encoding='utf-8', errors='ignore') as f:
            tag = f.read().strip().lstrip('\ufeff').strip().lstrip('v')
    except OSError:
        return None
    return tag or None


def get_current_version():
    """Return the current app version string.

    A beta build reads as its tag, "1.5.3-beta.1", so the app says it is a
    beta and the update check offers it the full 1.5.3 when that ships. The
    tag only counts when it is a prerelease of the version in VERSION.txt.
    """
    base = _read_version_file() or "0.0.0"
    tag = _read_build_tag()
    if tag and '-' in tag and tag.split('-', 1)[0] == base:
        return tag
    return base


def _version_key(version_str):
    """Order versions with prereleases: 1.5.2-beta.1 < 1.5.2-beta.2 < 1.5.2.

    The numbers compare as _parse_version reads them; at equal numbers a
    full release sorts above any prerelease of it.
    """
    v = (version_str or '').lstrip('v')
    base, _, pre = v.partition('-')
    nums = _parse_version(base)
    if not pre:
        return (nums, 1, ())
    tail = tuple(int(x) if x.isdigit() else x for x in re.split(r'[.]', pre))
    return (nums, 0, tuple((0, x) if isinstance(x, int) else (1, x) for x in tail))


def is_prerelease(version_str):
    """A beta build's version carries a '-': "1.7.0-beta.2"."""
    return '-' in (version_str or '').lstrip('v')


def pick_release(releases, current):
    """The release a beta is offered, from the GitHub releases list.

    The highest non-draft release above `current` by _version_key, beta or
    full: 1.7.0-beta.2 is offered 1.7.0-beta.3, and 1.7.0 once it ships.
    None when nothing is newer.
    """
    best = None
    for rel in releases or []:
        if not isinstance(rel, dict) or rel.get('draft'):
            continue
        tag = (rel.get('tag_name') or '').lstrip('v')
        if not _parse_version(tag.partition('-')[0]):
            continue
        if _version_key(tag) <= _version_key(current):
            continue
        if best is None or _version_key(tag) > _version_key(best['tag_name'].lstrip('v')):
            best = rel
    return best


def _get_json(url, ctx, current):
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"LED-Raster-Designer/{current}",
    })
    with urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(force=False):
    """
    Check GitHub for a newer release.

    A full release reads /releases/latest, which never names a beta. A beta
    build reads the releases list and is offered the highest release above
    it, beta or full (pick_release).

    Returns dict with keys:
        available (bool): True if a newer version exists
        current_version (str): Current app version
        latest_version (str): Latest release version (or None)
        download_url (str): Browser URL for the release (or None)
        release_notes (str): Release body text (or None)
        checksums (dict): {filename: sha256} from checksums.txt asset (or None)
        installer (dict): the release's Windows setup asset, {name, url,
            size}, or None
        can_install (bool): this copy can download and run that setup
            itself (an installed Windows copy and a setup to run)
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
        "installer": None,
        "can_install": False,
        "error": None,
    }

    try:
        ctx = _get_ssl_context()
        if is_prerelease(current):
            data = pick_release(_get_json(RELEASES_LIST_URL, ctx, current), current)
        else:
            data = _get_json(RELEASES_URL, ctx, current)
        if not data:
            # A beta with nothing newer published: it is the latest.
            data = {"tag_name": current}

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
                result["checksums_url"] = asset["browser_download_url"]
                break

        # Compare versions
        if _version_key(latest) > _version_key(current):
            result["available"] = True
            result["installer"] = installer_asset(data, latest)
            result["can_install"] = bool(result["installer"]) and is_installed_copy()

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
                # release.yml runs sha256sum over windows-build/<file>, so
                # a line names the folder too; the asset is the file name.
                filename = parts[-1].lstrip('*').replace('\\', '/').rsplit('/', 1)[-1]
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


# ── Installing an update on Windows (owner, 2026-11-08) ─────────────────
#
# An installed Windows copy downloads the release's setup itself, checks it
# against the release's checksums.txt, and on "Install and restart" runs it
# with /RELAUNCH and quits; the setup reopens the app when it is done
# (build/led_raster_designer.iss). macOS, the Windows .zip copy and a source
# run keep the link to the release page.
#
# The setup is fetched with urllib into a folder under %TEMP%. Only a
# browser (or a zip tool) writes the Zone.Identifier stream that makes
# Windows warn about a downloaded file; nothing here writes one, so the
# setup runs without the "Windows protected your PC" prompt. release.yml
# proves a file fetched this way carries no Zone.Identifier.

APP_ID = '{7D7BC445-209D-4629-A5D7-1C0B7EDC0C94}'   # build/led_raster_designer.iss
UNINSTALL_KEY = (r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
                 '\\' + APP_ID + '_is1')

INSTALLER_NAME_RE = re.compile(
    r'^led_raster_designer_v(\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)_windows_setup\.exe$')
# The asset link the API names, and the hosts GitHub redirects it to.
_ASSET_HOST = 'github.com'
_REDIRECT_HOSTS = ('github.com', 'objects.githubusercontent.com',
                   'release-assets.githubusercontent.com')
_MAX_SETUP_BYTES = 1024 * 1024 * 1024
# Inno Setup: a progress window only, no questions, no reboot. RELAUNCH is
# our own flag; the .iss reopens the app only when it is given.
INSTALLER_ARGS = ('/SILENT', '/SP-', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH')

MSG_NETWORK = 'The update could not be downloaded. Check the internet connection and try again.'
# Each says what happened and what to do next. "Could not be verified"
# is a missing checksum; "did not match the release" a wrong one.
MSG_NO_CHECKSUM = ('The update was not installed because it could not be verified, so the '
                   'download was deleted. Click Download to get it from the release page.')
MSG_BAD_CHECKSUM = ('The update was not installed because the download did not match the '
                    'release, so it was deleted. Click Update to try again.')
MSG_CANNOT_INSTALL = 'This copy cannot update itself. Click Download to get the new version from the release page.'
MSG_NO_UPDATE = 'There is no update to download.'
MSG_NOT_READY = 'The update has not finished downloading. Click Update to try again.'

_event_logger = None


def set_event_logger(fn):
    """routes_version hands in the app's log_event."""
    global _event_logger
    _event_logger = fn


def _event(name, details=None):
    fn = _event_logger
    if fn:
        try:
            fn(name, details or {})
        except Exception:
            pass


# ── Is this an installed copy? ──────────────────────────────────────────
#
# Setup records the folder it installed to in the uninstall key Settings >
# Apps reads (InstallLocation). This copy is "installed" when it is a frozen
# Windows build running from exactly that folder. The registry, not a file
# beside the exe, because it is the record setup itself keeps and reuses
# (UsePreviousAppDir): the update lands where the running copy is. A .zip
# copy unpacked anywhere else, or an install folder copied somewhere, does
# not match it and keeps the link to the release page.

def _registered_install_dir():
    """InstallLocation from the setup's uninstall key, or None."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, 'InstallLocation')
    except OSError:
        return None
    return value if isinstance(value, str) and value.strip() else None


# Both sides are Windows paths, so they are read with ntpath whatever runs
# this (the tests run it on Linux and macOS too): os.path there is posixpath,
# which knows neither backslashes nor that Windows ignores case.

def _windows_folder(p):
    """A Windows folder path in one comparable form: no quotes, one kind of
    separator, no trailing separator, lower case."""
    import ntpath
    return ntpath.normcase(ntpath.normpath(p.strip().strip('"').strip()))


def _same_folder(a, b):
    return _windows_folder(a) == _windows_folder(b)


def is_installed_copy(platform=None, frozen=None, executable=None):
    import ntpath
    platform = sys.platform if platform is None else platform
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    if platform != 'win32' or not frozen:
        return False
    where = _registered_install_dir()
    if not where:
        return False
    return _same_folder(where, ntpath.dirname(_windows_folder(executable)))


# ── The setup asset ─────────────────────────────────────────────────────

def _asset_url_ok(url, name):
    """The API's browser_download_url for `name` on this repo, over HTTPS."""
    from urllib.parse import urlparse
    try:
        p = urlparse(url or '')
        port = p.port
    except ValueError:
        return False
    return (p.scheme == 'https' and p.hostname == _ASSET_HOST and port in (None, 443)
            and not p.username and not p.query
            and p.path.startswith(f'/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/')
            and p.path.rsplit('/', 1)[-1] == name)


def installer_asset(release, version):
    """{name, url, size} for the release's Windows setup, or None."""
    name = f'led_raster_designer_v{version}_windows_setup.exe'
    if not INSTALLER_NAME_RE.match(name):
        return None
    for asset in (release or {}).get('assets') or []:
        if asset.get('name') != name:
            continue
        url = asset.get('browser_download_url') or ''
        if not _asset_url_ok(url, name):
            return None
        try:
            size = int(asset.get('size') or 0)
        except (TypeError, ValueError):
            size = 0
        return {'name': name, 'url': url, 'size': size}
    return None


# ── Downloading it (one at a time, on a background thread) ──────────────

_dl_lock = threading.Lock()
_dl = {'state': 'idle', 'percent': 0, 'version': None, 'error': None,
       'path': None, 'sha256': None}
_BUSY = ('downloading', 'verifying', 'installing')


def _public():
    return {k: _dl[k] for k in ('state', 'percent', 'version', 'error')}


def download_status():
    """What the banner shows: idle, downloading, verifying, ready,
    installing or error, with a percent and a plain error."""
    with _dl_lock:
        return _public()


def _set(**kw):
    with _dl_lock:
        _dl.update(kw)


def _remove_download(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        os.rmdir(os.path.dirname(path))
    except OSError:
        pass


def _clean_old_downloads():
    """Setups left in %TEMP% by earlier updates."""
    import shutil
    base = tempfile.gettempdir()
    try:
        names = os.listdir(base)
    except OSError:
        return
    for name in names:
        if name.startswith('lrd-update-'):
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)


def _download_opener(ctx):
    from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler
    from urllib.parse import urlparse

    class _GitHubRedirectsOnly(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            p = urlparse(newurl)
            if p.scheme != 'https' or p.hostname not in _REDIRECT_HOSTS:
                raise HTTPError(newurl, code, 'redirected away from GitHub', headers, fp)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return build_opener(HTTPSHandler(context=ctx), _GitHubRedirectsOnly())


def start_download():
    """Start downloading the offered setup. A repeat call while one runs,
    or once one is ready, starts nothing and says where it is."""
    with _dl_lock:
        if _dl['state'] in _BUSY:
            return _public()
    result = check_for_update()
    if not result.get('available'):
        return {'state': 'error', 'percent': 0, 'version': None, 'error': MSG_NO_UPDATE}
    inst = result.get('installer')
    if not inst or not is_installed_copy():
        return {'state': 'error', 'percent': 0, 'version': None, 'error': MSG_CANNOT_INSTALL}
    version = result.get('latest_version')
    with _dl_lock:
        if _dl['state'] in _BUSY:
            return _public()
        if (_dl['state'] == 'ready' and _dl['version'] == version
                and _dl['path'] and os.path.isfile(_dl['path'])):
            return _public()
        _dl.update(state='downloading', percent=0, version=version, error=None,
                   path=None, sha256=None)
        started = _public()
    _event('update_download_started', {'version': version, 'asset': inst['name']})
    threading.Thread(target=_download_worker, name='lrd-update-download',
                     args=(inst, version, dict(result.get('checksums') or {}),
                           result.get('checksums_url')),
                     daemon=True).start()
    return started


def _fail(path, message, event, details=None):
    _remove_download(path)
    _set(state='error', error=message, path=None, sha256=None)
    _event(event, details or {})


def _download_worker(inst, version, checksums, checksums_url):
    _clean_old_downloads()
    path = None
    got = 0
    try:
        folder = tempfile.mkdtemp(prefix='lrd-update-')
        path = os.path.join(folder, inst['name'])
        ctx = _get_ssl_context()
        req = Request(inst['url'], headers={
            'Accept': 'application/octet-stream',
            'User-Agent': f'LED-Raster-Designer/{get_current_version()}',
        })
        with _download_opener(ctx).open(req, timeout=30) as resp:
            try:
                total = int(resp.headers.get('Content-Length') or 0)
            except (TypeError, ValueError):
                total = 0
            total = total or inst.get('size') or 0
            if total > _MAX_SETUP_BYTES:
                raise OSError(f'the setup is {total} bytes')
            # A plain file write: no Zone.Identifier stream is ever made.
            with open(path, 'wb') as out:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > _MAX_SETUP_BYTES:
                        raise OSError('the setup is larger than any release')
                    out.write(chunk)
                    if total:
                        _set(percent=min(99, int(got * 100 / total)))
        _set(state='verifying', percent=100)
        expected = checksums.get(inst['name'])
        if not expected and checksums_url:
            expected = (_fetch_checksums(checksums_url, ctx) or {}).get(inst['name'])
        if not expected:
            _fail(path, MSG_NO_CHECKSUM, 'update_download_refused',
                  {'reason': 'no checksum', 'asset': inst['name']})
            return
        if not verify_download(path, expected):
            _fail(path, MSG_BAD_CHECKSUM, 'update_download_refused',
                  {'reason': 'checksum mismatch', 'asset': inst['name']})
            return
        _set(state='ready', percent=100, path=path, sha256=expected.lower(), error=None)
        _event('update_download_ready', {'version': version, 'bytes': got})
    except Exception as e:
        logger.warning('Update download failed: %s', e)
        _fail(path, MSG_NETWORK, 'update_download_failed',
              {'error': f'{type(e).__name__}: {e}'})


# ── Running it ──────────────────────────────────────────────────────────

_quit_handler = None


def set_quit_handler(fn):
    """The launcher's own Quit, so an update closes the app the way the
    tray's Quit does (launcher_window.run_window, launcher_pc.run_tray)."""
    global _quit_handler
    _quit_handler = fn


def quit_available():
    """Is there a launcher to quit? A server run on its own (from source,
    the CI smoke run, the tests) has none, and File > Quit is not offered
    there (routes_version api_app_quit)."""
    return _quit_handler is not None


def schedule_app_quit(delay=1.0):
    """File > Quit: quit the way the launcher's Quit does, once the route
    has answered the page. False when there is no launcher to quit."""
    if _quit_handler is None:
        return False
    _schedule_quit(delay)
    return True


def _quit_app():
    fn = _quit_handler
    try:
        if fn:
            fn()
    finally:
        os._exit(0)


def _schedule_quit(delay=1.0):
    """Quit once the route has answered the page."""
    def later():
        time.sleep(delay)
        _quit_app()
    threading.Thread(target=later, name='lrd-update-quit', daemon=True).start()


def _installer_env():
    """This process's environment without the frozen bundle's own entries,
    so the app the setup reopens starts as clean as one from the Start menu."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('_PYI_', '_MEIPASS')) or key == '_LRD_LOG_DIR':
            del env[key]
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        low = os.path.normcase(bundle)
        for key in list(env):
            if key.upper() == 'PATH':
                parts = [p for p in env[key].split(os.pathsep)
                         if not os.path.normcase(p).startswith(low)]
                env[key] = os.pathsep.join(parts)
            elif low in os.path.normcase(env[key]):
                del env[key]
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def installer_command(path):
    log = os.path.join(os.path.dirname(path), 'install.log')
    return [path, *INSTALLER_ARGS, f'/LOG={log}']


def _spawn_installer(cmd):
    """Start the setup detached, so it outlives the app it is replacing."""
    import subprocess
    detached = getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
    group = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x00000200)
    breakaway = getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0x01000000)
    kw = dict(cwd=os.path.dirname(cmd[0]), env=_installer_env(), close_fds=True,
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL)
    try:
        subprocess.Popen(cmd, creationflags=detached | group | breakaway, **kw)
    except OSError:
        # A job that does not allow breakaway: detached is enough there.
        subprocess.Popen(cmd, creationflags=detached | group, **kw)


def install_update():
    """Run the downloaded setup and quit. The file is checked again first:
    a setup that no longer matches its checksum is deleted, never run."""
    with _dl_lock:
        state, path, sha, version = _dl['state'], _dl['path'], _dl['sha256'], _dl['version']
    if state != 'ready' or not path or not sha:
        return {'ok': False, 'error': MSG_NOT_READY}
    if not is_installed_copy():
        return {'ok': False, 'error': MSG_CANNOT_INSTALL}
    if not os.path.isfile(path) or not verify_download(path, sha):
        _fail(path, MSG_BAD_CHECKSUM, 'update_install_refused', {'reason': 'checksum mismatch'})
        return {'ok': False, 'error': MSG_BAD_CHECKSUM}
    cmd = installer_command(path)
    try:
        _spawn_installer(cmd)
    except OSError as e:
        _event('update_install_failed', {'error': f'{type(e).__name__}: {e}'})
        return {'ok': False, 'error': f'The update could not be started: {e}'}
    _set(state='installing')
    _event('update_install_started', {'version': version, 'args': cmd[1:]})
    mark_page_waiting()
    _schedule_quit()
    return {'ok': True, 'version': version}


# ── One browser tab across the restart ──────────────────────────────────
#
# The page that clicked Install and restart waits for the new version and
# reloads itself (updater.js reloadWhenUpdated). So the launch the setup
# makes must not open a second tab, even with Open Browser on Launch on.
# install_update leaves a time-stamped note beside the settings; the next
# launch reads it once, deletes it, and skips its browser open while it is
# fresh. Ten minutes, as long as the page waits: a slow install still
# counts, and a stale note (setup failed, the app opened by hand next
# week) opens the browser as usual.

PAGE_WAITING_FILE = 'update-page-waiting'
PAGE_WAITING_SECONDS = 600


def _page_waiting_path():
    from launcher_settings import get_config_dir
    return os.path.join(get_config_dir(), PAGE_WAITING_FILE)


def mark_page_waiting(now=None):
    try:
        with open(_page_waiting_path(), 'w', encoding='utf-8') as fh:
            fh.write(repr(time.time() if now is None else now))
    except Exception as e:
        logger.warning('Could not note the waiting page: %s', e)


def take_page_waiting(now=None):
    """True when a page was left waiting for this launch. Reads the note
    once and deletes it, fresh or not."""
    try:
        path = _page_waiting_path()
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read().strip()
    except Exception:
        return False          # no note: the usual launch
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        stamp = float(text)
    except ValueError:
        return False
    age = (time.time() if now is None else now) - stamp
    return 0 <= age <= PAGE_WAITING_SECONDS


def open_browser_on_launch(settings):
    """The launchers' "open the browser now?" (launcher_window.main,
    launcher_pc.main): the setting, unless the page from before an update
    is already waiting to reload."""
    waiting = take_page_waiting()
    return bool(settings.get('open_browser_on_launch', False)) and not waiting
