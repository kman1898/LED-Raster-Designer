"""Drive the app's own updater (src/updater.py) the way Update does.

release.yml's installer smoke test runs this on the Windows runner:

    python scripts/update_smoke.py fetch <setup.exe> <version> <out.txt>
        Serves <setup.exe> on 127.0.0.1 and downloads it with the updater's
        own download code (the same urllib fetch, file write and SHA-256
        check Update runs), then proves the downloaded copy carries no
        Zone.Identifier (Mark of the Web), on a folder that can carry one.
        Writes the downloaded path to <out.txt>.

    python scripts/update_smoke.py install <downloaded setup.exe>
        Starts that setup the way Install and restart does (detached, with
        the updater's own arguments, /RELAUNCH included) and exits at once,
        the way the app quits; the workflow then waits for setup to finish
        and reopen the app.

tests/test_update_in_place.py runs the fetch half on every CI test run, so
this script cannot drift from the updater it drives.
"""
import functools
import hashlib
import http.server
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import updater  # noqa: E402


def has_zone_identifier(path):
    """True when `path` carries a Zone.Identifier stream (Windows only)."""
    try:
        with open(path + ':Zone.Identifier', 'rb'):
            return True
    except OSError:
        return False


def folder_can_carry_a_zone_tag(folder):
    """A control file in the same folder, tagged on purpose. A folder whose
    filesystem drops alternate streams would make "no tag" mean nothing."""
    probe = os.path.join(folder, 'zone-probe.txt')
    with open(probe, 'w', encoding='utf-8') as fh:
        fh.write('probe')
    try:
        with open(probe + ':Zone.Identifier', 'w', encoding='utf-8') as fh:
            fh.write('[ZoneTransfer]\nZoneId=3\n')
    except OSError:
        pass
    try:
        return has_zone_identifier(probe)
    finally:
        os.remove(probe)


def fetch(setup, version):
    """Download `setup` through the updater. Returns (path, problems)."""
    name = os.path.basename(setup)
    with open(setup, 'rb') as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=os.path.dirname(os.path.abspath(setup)))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        inst = {'name': name, 'size': os.path.getsize(setup),
                'url': f'http://127.0.0.1:{server.server_port}/{name}'}
        updater._download_worker(inst, version, {name: sha}, None)
    finally:
        server.shutdown()
    with updater._dl_lock:
        state = dict(updater._dl)
    problems = []
    path = state.get('path')
    if state.get('state') != 'ready' or not path or not os.path.isfile(path):
        return None, [f'the updater did not finish the download: {state}']
    if not updater.verify_download(path, sha):
        problems.append('the downloaded copy does not match the setup')
    if sys.platform == 'win32':
        if not folder_can_carry_a_zone_tag(os.path.dirname(path)):
            problems.append('the download folder cannot carry a Zone.Identifier, so its absence proves nothing')
        elif has_zone_identifier(path):
            problems.append('the downloaded setup carries a Zone.Identifier (Mark of the Web)')
    return path, problems


def main(argv):
    if len(argv) == 4 and argv[0] == 'fetch':
        path, problems = fetch(argv[1], argv[2])
        for p in problems:
            print(f'FAILED: {p}')
        if problems:
            return 1
        print(f'ok: downloaded and checked by the updater: {path}')
        print('ok: no Zone.Identifier on the downloaded setup')
        with open(argv[3], 'w', encoding='utf-8') as fh:
            fh.write(path)
        return 0
    if len(argv) == 2 and argv[0] == 'install':
        cmd = updater.installer_command(argv[1])
        updater._spawn_installer(cmd)
        print('started: ' + ' '.join(cmd))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
