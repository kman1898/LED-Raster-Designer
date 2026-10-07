#!/usr/bin/env python3
"""Generate THIRD-PARTY-NOTICES, the notices for what the builds bundle.

WHY THIS EXISTS
    The Windows and macOS builds (src/led_raster_designer.spec) bundle the
    Python packages in src/requirements.txt and everything they depend on.
    Most of those licenses require their notice to ship with the app, and
    the LED Raster Designer License (Section 8) points at this file for
    them. A hand-kept list would fall behind the first time a requirement
    is added, so the list is generated from the installed packages'
    metadata.

WHAT IT LISTS
    The runtime dependency closure of src/requirements.txt (plus rumps,
    which release.yml installs for the macOS build and launcher_mac.py
    imports), walked with importlib.metadata. Environment markers are
    evaluated for BOTH win32 and darwin, so platform-only dependencies
    (the macOS pyobjc packages pywebview and pystray pull) are listed even
    when this script runs on the other platform. A package not installed
    here comes from KNOWN below: its license name and project URL, and
    "license text: see <URL>" in place of the text.

    No versions are written: they differ between machines and builds.

USAGE
    python scripts/build_third_party_notices.py          # write the file
    python scripts/build_third_party_notices.py --check  # exit 1 naming any
        package in the closure that the committed file does not list

tests/test_license.py runs --check, so a new requirement cannot ship
without its notice.
"""
import argparse
import importlib.metadata as md
import os
import re
import sys

try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pip vendors packaging; use it when packaging is absent
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REQUIREMENTS = os.path.join(ROOT, 'src', 'requirements.txt')
RELEASE_YML = os.path.join(ROOT, '.github', 'workflows', 'release.yml')
SOCKETIO_JS = os.path.join(ROOT, 'src', 'static', 'js', 'socket.io.min.js')
OUTPUT = os.path.join(ROOT, 'THIRD-PARTY-NOTICES')

# Bundled by a build but not in requirements.txt: release.yml installs rumps
# for the macOS build, and the spec's hidden import of launcher_mac pulls it.
BUILD_EXTRAS = ['rumps; sys_platform == "darwin"']

# Packages the closure can reach that may not be installed where this runs
# (macOS-only on a Windows PC, and the reverse), and packages whose metadata
# names no license. name -> (display name, SPDX license, project URL,
# runtime requirements).
_PYOBJC = 'https://github.com/ronaldoussoren/pyobjc'
_PYOBJC_FW = ['pyobjc-core', 'pyobjc-framework-Cocoa']
KNOWN = {
    'pyobjc-core': ('pyobjc-core', 'MIT', _PYOBJC, []),
    'pyobjc-framework-cocoa': ('pyobjc-framework-Cocoa', 'MIT', _PYOBJC, ['pyobjc-core']),
    'pyobjc-framework-quartz': ('pyobjc-framework-Quartz', 'MIT', _PYOBJC, _PYOBJC_FW),
    'pyobjc-framework-webkit': ('pyobjc-framework-WebKit', 'MIT', _PYOBJC, _PYOBJC_FW),
    'pyobjc-framework-security': ('pyobjc-framework-Security', 'MIT', _PYOBJC, _PYOBJC_FW),
    'pyobjc-framework-uniformtypeidentifiers': (
        'pyobjc-framework-UniformTypeIdentifiers', 'MIT', _PYOBJC, _PYOBJC_FW),
    'rumps': ('rumps', 'BSD-3-Clause', 'https://github.com/jaredks/rumps',
              ['pyobjc-framework-Cocoa']),
    'clr-loader': ('clr_loader', 'MIT', 'https://github.com/pythonnet/clr-loader', ['cffi']),
}

# Marker environments: one per bundled platform. python_version comes from
# the release workflow (the Python the builds are made with).
PLATFORMS = {
    'win32': {'sys_platform': 'win32', 'platform_system': 'Windows', 'os_name': 'nt'},
    'darwin': {'sys_platform': 'darwin', 'platform_system': 'Darwin', 'os_name': 'posix'},
}

RULE = '-' * 72
LICENSE_FILE = re.compile(r'(LICEN[CS]E|COPYING|NOTICE)', re.I)
_URL_LABELS = ('homepage', 'home', 'source', 'source code', 'repository',
               'sources', 'code')


def build_pythons():
    """The python-version(s) release.yml builds with; this interpreter's if
    none is found."""
    try:
        with open(RELEASE_YML, encoding='utf-8') as f:
            found = re.findall(r'python-version:\s*["\']?([0-9]+\.[0-9]+)', f.read())
    except OSError:
        found = []
    return sorted(set(found)) or ['%d.%d' % sys.version_info[:2]]


def environments():
    for pyver in build_pythons():
        for plat in PLATFORMS.values():
            env = dict(plat)
            env.update({'python_version': pyver,
                        'python_full_version': pyver + '.0',
                        'implementation_name': 'cpython',
                        'platform_python_implementation': 'CPython',
                        'extra': ''})
            yield env


def root_requirements():
    reqs = []
    with open(REQUIREMENTS, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if line:
                reqs.append(Requirement(line))
    return reqs + [Requirement(r) for r in BUILD_EXTRAS]


def _dist(key):
    try:
        return md.distribution(key)
    except md.PackageNotFoundError:
        return None


def _requires(key):
    dist = _dist(key)
    if dist is not None:
        return [Requirement(r) for r in (dist.requires or [])]
    if key in KNOWN:
        return [Requirement(r) for r in KNOWN[key][3]]
    return []


def closure():
    """Canonical names of every package any bundled platform can reach."""
    seen = set()
    for env in environments():
        queue = [r for r in root_requirements()
                 if r.marker is None or r.marker.evaluate(env)]
        visited = set()
        while queue:
            req = queue.pop()
            key = canonicalize_name(req.name)
            if key in visited:
                continue
            visited.add(key)
            for dep in _requires(key):
                if dep.marker is None or dep.marker.evaluate(env):
                    queue.append(dep)
        seen |= visited
    return seen


def _license_name(meta, key):
    expr = (meta.get('License-Expression') or '').strip()
    if expr:
        return expr
    loose = (meta.get('License') or '').strip()
    if loose and '\n' not in loose and len(loose) <= 40:
        return loose
    classifiers = [c.split(' :: ')[-1] for c in (meta.get_all('Classifier') or [])
                   if c.startswith('License ::')]
    if classifiers:
        return ', '.join(classifiers)
    if key in KNOWN:
        return KNOWN[key][1]
    return 'see the project page'


def _project_url(meta, key):
    urls = {}
    for entry in meta.get_all('Project-URL') or []:
        label, _, url = entry.partition(',')
        urls.setdefault(label.strip().lower(), url.strip())
    home = (meta.get('Home-page') or '').strip()
    if home:
        return home
    for label in _URL_LABELS:
        if label in urls:
            return urls[label]
    if urls:
        return next(iter(urls.values()))
    return KNOWN[key][2] if key in KNOWN else ''


def _clean(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\f', '')
    return '\n'.join(line.rstrip() for line in text.split('\n')).strip('\n')


def _license_files(dist):
    """(path inside dist-info, text) of every license or notice file."""
    out = []
    for f in dist.files or []:
        parts = f.parts
        if len(parts) < 2 or not parts[0].endswith('.dist-info'):
            continue
        if not LICENSE_FILE.search(parts[-1]):
            continue
        rel = '/'.join(parts[1:])
        try:
            data = dist.locate_file(f).read_bytes()
        except OSError:
            continue
        out.append((rel, _clean(data.decode('utf-8', errors='replace'))))
    out.sort(key=lambda item: (item[0].count('/'), item[0].lower()))
    return out


def entry(key):
    dist = _dist(key)
    if dist is None:
        if key not in KNOWN:
            raise SystemExit(
                f'{key} is in the dependency closure but is not installed and '
                f'not in KNOWN: add it to KNOWN in {os.path.basename(__file__)}')
        name, lic, url, _ = KNOWN[key]
        return name, lic, url, []
    meta = dist.metadata
    return meta['Name'], _license_name(meta, key), _project_url(meta, key), _license_files(dist)


HEADER = """\
THIRD-PARTY NOTICES
LED Raster Designer

LED Raster Designer includes the following third-party software, each
under its own license. Nothing in the LED Raster Designer License changes
those licenses or limits the rights they give you.

The packages listed below are the ones the Windows and macOS builds
bundle: the requirements in src/requirements.txt, rumps on macOS, and
everything they depend on at run time on either platform. Their versions
are those pinned or resolved at build time, so no versions are given
here. Each entry names the package's license and project page, followed
by the license and notice files the package itself ships. Where a
package does not ship them, the entry says where the license text can be
found.

The builds also include:

  The Python runtime
  License: PSF License Agreement (with the licenses of the libraries the
  Python runtime itself includes, listed on the same page)
  https://docs.python.org/3/license.html

  The PyInstaller bootloader
  License: GPL-2.0 with the bootloader exception, which permits
  distributing the bundled application under its own terms
  https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt
"""


def _socketio_block():
    """The Socket.IO JavaScript client in src/static/js, when it is there."""
    try:
        with open(SOCKETIO_JS, encoding='utf-8', errors='replace') as f:
            head = f.read(400)
    except OSError:
        return ''
    holder = re.search(r'\(c\)\s*([^\n*]+)', head)
    lines = ['', '  The Socket.IO JavaScript client (src/static/js/socket.io.min.js)']
    if holder:
        lines.append('  Copyright (c) ' + holder.group(1).strip())
    lines += ['  License: MIT',
              '  license text: see https://github.com/socketio/socket.io/blob/main/LICENSE']
    return '\n'.join(lines) + '\n'


def render():
    blocks = [HEADER + _socketio_block()]
    entries = sorted((entry(k) for k in closure()), key=lambda e: e[0].lower())
    for name, lic, url, files in entries:
        lines = [RULE, f'Package: {name}', f'License: {lic}']
        if url:
            lines.append(f'Project: {url}')
        lines += [RULE, '']
        if files:
            for rel, text in files:
                lines += [f'[{rel}]', '', text, '']
        else:
            lines += [f'license text: see {url}' if url else
                      'license text: not shipped with the package', '']
        blocks.append('\n'.join(lines))
    return '\n\n'.join(b.rstrip('\n') for b in blocks) + '\n'


def listed_names(path=OUTPUT):
    """Canonical names of the packages the notices file lists."""
    with open(path, encoding='utf-8') as f:
        return {canonicalize_name(m.group(1).strip())
                for m in re.finditer(r'^Package: (.+)$', f.read(), re.M)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='fail if a package in the closure is not listed')
    args = parser.parse_args(argv)

    if args.check:
        try:
            listed = listed_names()
        except OSError:
            print(f'{OUTPUT} is missing: run {os.path.basename(__file__)}')
            return 1
        missing = sorted(closure() - listed)
        if missing:
            print('THIRD-PARTY-NOTICES does not list: ' + ', '.join(missing))
            print(f'Regenerate it: python scripts/{os.path.basename(__file__)}')
            return 1
        print(f'OK: THIRD-PARTY-NOTICES lists all {len(listed)} packages')
        return 0

    text = render()
    with open(OUTPUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    count = len(re.findall(r'^Package: ', text, re.M))
    print(f'Wrote {OUTPUT} ({count} packages)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
