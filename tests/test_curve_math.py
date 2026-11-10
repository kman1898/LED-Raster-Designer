"""The Header/Footer tab's Curve: the curve calculator's math (curve-math.js)
and the OBJ writer (obj-export.js), under node.

Both are plain ES modules with no DOM. Their tests are JavaScript, in
tests/js/*.test.mjs (the curve calculator's own tests, ported, plus its
worked examples and the screen adapter); each file prints one JSON line,
{passed, total, failed: [{name, error}]}, which this reads. Every file in
tests/js that ends in .test.mjs is run, so a new one cannot be forgotten.
The tests skip where node is not installed.
"""
import glob
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_TESTS = sorted(glob.glob(os.path.join(ROOT, 'tests', 'js', '*.test.mjs')))

needs_node = pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')


def test_the_js_tests_are_found():
    names = {os.path.basename(p) for p in JS_TESTS}
    for want in ('curve_geometry.test.mjs', 'curve_targets.test.mjs', 'curve_snap.test.mjs',
                 'curve_footers.test.mjs', 'curve_solve.test.mjs', 'curve_invariants.test.mjs',
                 'curve_units.test.mjs', 'curve_pinned.test.mjs', 'curve_screen.test.mjs',
                 'obj_export.test.mjs'):
        assert want in names, f'{want} is missing from tests/js'


@needs_node
@pytest.mark.parametrize('path', JS_TESTS, ids=[os.path.basename(p) for p in JS_TESTS])
def test_js_file_passes(path):
    out = subprocess.run(['node', path], capture_output=True, text=True, timeout=600,
                         encoding='utf-8', cwd=ROOT)
    assert out.returncode == 0, out.stderr[-4000:]
    lines = [l for l in out.stdout.splitlines() if l.startswith('{')]
    assert lines, f'no report from {path}: {out.stdout[-2000:]} {out.stderr[-2000:]}'
    report = json.loads(lines[-1])
    assert report['total'] > 0, report
    failed = '\n'.join(f"- {f['name']}: {f['error']}" for f in report['failed'])
    assert not report['failed'], f"{len(report['failed'])} of {report['total']} failed:\n{failed}"
