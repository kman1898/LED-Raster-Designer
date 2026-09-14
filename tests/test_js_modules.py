"""Guards for the front end's module layout.

LEDRasterApp is assembled by prototype mixing: app-core.js declares the
class, and every app-*.js module declares a private `class _X` whose own
method names are copied onto LEDRasterApp.prototype when main.js imports it.
That mixing is name-flat and collision-silent - a module imported later
overwrites an earlier module's same-named method with no warning - and a
module main.js forgets to import simply contributes nothing. These checks
turn both silences into failures, and pin two build facts the modularization
work leans on: index.html only names scripts that exist, and no source file
carries a NUL byte (grep, eslint and codemods skip a file that does).
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')
STATIC_DIR = os.path.join(ROOT, 'src', 'static')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
MAIN_JS = os.path.join(JS_DIR, 'main.js')

# A method definition at class-body indentation: `    name(` or
# `    async name(`. Keyword statements never sit at four spaces INSIDE a
# class body, so the only exclusion needed is the constructor.
METHOD_RE = re.compile(r'^\s{4}(async\s+)?([A-Za-z_$][\w$]*)\s*\(')
CLASS_OPEN_RE = re.compile(r'^(export\s+)?class\s+([A-Za-z_$][\w$]*)\b.*\{\s*$')


def _app_module_files():
    names = sorted(n for n in os.listdir(JS_DIR)
                   if n.startswith('app-') and n.endswith('.js'))
    assert names, 'no app-*.js modules found'
    return names


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _class_method_names(source):
    """Method names declared inside every top-level class body in `source`.

    A class body runs from its `class X {` line to the first line that is a
    bare `}` at column zero. Only lines inside such a body are read, so the
    prototype-copy loop after the class (which also indents four spaces)
    contributes nothing.
    """
    names = []
    in_class = False
    for line in source.split('\n'):
        if not in_class:
            if CLASS_OPEN_RE.match(line):
                in_class = True
            continue
        if line == '}':
            in_class = False
            continue
        m = METHOD_RE.match(line)
        if m and m.group(2) != 'constructor':
            names.append(m.group(2))
    return names


def test_every_app_module_declares_a_class():
    for name in _app_module_files():
        assert _class_method_names(_read(os.path.join(JS_DIR, name))), (
            f'{name} declares no class-body methods - the guard cannot see '
            f'it, so its mixin idiom has changed; update this test with it')


def test_method_names_are_defined_in_exactly_one_app_module():
    owners = {}
    for name in _app_module_files():
        for method in _class_method_names(_read(os.path.join(JS_DIR, name))):
            owners.setdefault(method, []).append(name)
    collisions = {m: files for m, files in owners.items() if len(set(files)) > 1}
    duplicates = {m: files for m, files in owners.items()
                  if len(files) > 1 and len(set(files)) == 1}
    assert not collisions, (
        'a method is defined in more than one app-*.js; the later import in '
        'main.js silently overwrites the earlier one:\n' +
        '\n'.join(f'  {m}: {", ".join(f)}' for m, f in sorted(collisions.items())))
    assert not duplicates, (
        'a method is defined twice in the same class body (the second wins):\n' +
        '\n'.join(f'  {m}: {f[0]}' for m, f in sorted(duplicates.items())))


def test_main_js_imports_every_app_module():
    imported = set(re.findall(r"""import\s+(?:\{[^}]*\}\s+from\s+)?['"]\./(app-[\w-]+\.js)['"]""",
                              _read(MAIN_JS)))
    on_disk = set(_app_module_files())
    missing = sorted(on_disk - imported)
    assert not missing, (
        f'app-*.js modules on disk that main.js never imports (their methods '
        f'never reach LEDRasterApp.prototype): {missing}')
    phantom = sorted(imported - on_disk)
    assert not phantom, f'main.js imports modules that do not exist: {phantom}'


def test_index_html_script_sources_exist():
    srcs = re.findall(r'<script[^>]*\ssrc="(/static/[^"]+)"', _read(INDEX_HTML))
    assert srcs, 'index.html names no /static/ scripts'
    missing = [s for s in srcs
               if not os.path.isfile(os.path.join(STATIC_DIR, s[len('/static/'):]))]
    assert not missing, f'index.html script src that does not exist on disk: {missing}'


def test_no_js_source_contains_a_nul_byte():
    offenders = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js'):
            continue
        with open(os.path.join(JS_DIR, name), 'rb') as fh:
            data = fh.read()
        if b'\x00' in data:
            line = data[:data.index(b'\x00')].count(b'\n') + 1
            offenders.append(f'{name}:{line}')
    assert not offenders, (
        f'NUL byte in a JS source (grep/eslint/codemods skip the file): {offenders}')


def test_no_mock_pages_ship_under_static():
    """Design mocks live in the repo-root mocks/ directory (gitignored).
    PyInstaller copies src/static wholesale, so anything left here ships in
    every build."""
    offenders = []
    for dirpath, _dirs, files in os.walk(STATIC_DIR):
        for name in files:
            if name.endswith('-mock.html') or name.endswith('-proto.html'):
                offenders.append(os.path.relpath(os.path.join(dirpath, name), ROOT))
    assert not offenders, f'mock pages under src/static (move them to mocks/): {offenders}'
