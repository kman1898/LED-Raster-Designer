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


# --- CanvasRenderer mixins -------------------------------------------------
# canvas.js is a classic script that declares `class CanvasRenderer`; the
# canvas-*.js files are classic scripts that `Object.assign(CanvasRenderer.
# prototype, { ... })`. Same name-flat mixing, same silences: a name defined
# twice wins by script order, and a mixin index.html forgets to load (or loads
# before canvas.js / after main.js) either contributes nothing or throws.

CANVAS_JS = os.path.join(JS_DIR, 'canvas.js')
MIXIN_OPEN = 'Object.assign(CanvasRenderer.prototype, {'


def _canvas_mixin_files():
    return sorted(n for n in os.listdir(JS_DIR)
                  if n.startswith('canvas-') and n.endswith('.js'))


def _mixin_method_names(source):
    """Method names at four-space indentation inside the Object.assign literal
    (from the MIXIN_OPEN line to the closing `});` at column zero)."""
    names = []
    in_literal = False
    for line in source.split('\n'):
        if not in_literal:
            if line == MIXIN_OPEN:
                in_literal = True
            continue
        if line == '});':
            in_literal = False
            continue
        m = METHOD_RE.match(line)
        if m:
            names.append(m.group(2))
    return names


def test_canvas_js_still_declares_the_renderer_class():
    source = _read(CANVAS_JS)
    assert re.search(r'^class CanvasRenderer\s*\{', source, re.M), (
        'canvas.js no longer declares `class CanvasRenderer`; the mixins '
        'have nothing to assign onto')
    assert 'window.CanvasRenderer = CanvasRenderer;' in source
    assert _class_method_names(source), 'canvas.js class body declares no methods'


def test_every_canvas_mixin_uses_the_object_assign_idiom():
    for name in _canvas_mixin_files():
        source = _read(os.path.join(JS_DIR, name))
        assert source.count(MIXIN_OPEN) == 1, (
            f'{name} must contain exactly one `{MIXIN_OPEN}` block')
        assert _mixin_method_names(source), (
            f'{name} contributes no methods the guard can see')


def test_canvas_method_names_are_defined_exactly_once_across_the_renderer():
    owners = {}
    for method in _class_method_names(_read(CANVAS_JS)):
        owners.setdefault(method, []).append('canvas.js')
    for name in _canvas_mixin_files():
        for method in _mixin_method_names(_read(os.path.join(JS_DIR, name))):
            owners.setdefault(method, []).append(name)
    clashes = {m: f for m, f in owners.items() if len(f) > 1}
    assert not clashes, (
        'a CanvasRenderer method is defined more than once (the later script '
        'in index.html silently wins):\n' +
        '\n'.join(f'  {m}: {", ".join(f)}' for m, f in sorted(clashes.items())))


def test_index_html_loads_every_canvas_mixin_between_canvas_js_and_main_js():
    srcs = re.findall(r'<script[^>]*\ssrc="/static/js/([^"]+)"', _read(INDEX_HTML))
    assert 'canvas.js' in srcs and 'main.js' in srcs
    lo, hi = srcs.index('canvas.js'), srcs.index('main.js')
    assert lo < hi, 'canvas.js must load before main.js'
    loaded = {s: i for i, s in enumerate(srcs)}
    problems = []
    for name in _canvas_mixin_files():
        pos = loaded.get(name)
        if pos is None:
            problems.append(f'{name}: no <script> tag in index.html')
        elif not (lo < pos < hi):
            problems.append(f'{name}: must load after canvas.js and before main.js')
    assert not problems, '\n'.join(problems)
    phantom = [s for s in srcs if s.startswith('canvas-') and s not in _canvas_mixin_files()]
    assert not phantom, f'index.html loads canvas mixins that do not exist: {phantom}'


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
