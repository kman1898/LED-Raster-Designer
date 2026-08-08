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
    """Extract a version like 1.0, 0.6.5, 0.6.3.6, or 0.8.7.7.1 from text
    (with or without v prefix). Allows up to 5 parts so hotfix-of-a-hotfix
    naming (e.g. 0.8.7.7.1) parses cleanly."""
    # Try v-prefixed version first (e.g. v0.6.5, v1.0, v0.8.7.7.1)
    m = re.search(r'v(\d+\.\d+(?:\.\d+){0,3})', text)
    if m:
        return m.group(1)
    # Fall back to non-prefixed 3+ part versions to avoid matching CSS like "0.6em"
    m = re.search(r'(\d+\.\d+\.\d+(?:\.\d+){0,2})', text)
    return m.group(1) if m else None


def _read_version_from_file(rel_path, line_number=None):
    """Read a version string from a file, optionally from a specific line."""
    path = os.path.join(ROOT, rel_path)
    with open(path, 'r', encoding='utf-8') as f:
        if line_number is not None:
            lines = f.readlines()
            return _extract_version(lines[line_number - 1])
        return _extract_version(f.read())


def test_version_txt_is_valid():
    """VERSION.txt must use a 2 to 5-part version (e.g. 1.0, 0.6.5, 0.6.3.6,
    or hotfix-of-a-hotfix like 0.8.7.7.1)."""
    version = _read_version_from_file('src/VERSION.txt')
    assert version is not None, "No version found in VERSION.txt"
    parts = version.split('.')
    assert 2 <= len(parts) <= 5, (
        f"VERSION.txt has {len(parts)}-part version '{version}', expected 2-5 parts"
    )


def test_all_version_sources_match():
    """All four version locations must report the same version string."""
    version_txt = _read_version_from_file('src/VERSION.txt')
    index_title = _read_version_from_file('src/templates/index.html', line_number=6)
    # Find h1 line dynamically instead of hardcoding line number
    index_h1 = None
    index_path = os.path.join(ROOT, 'src/templates/index.html')
    with open(index_path, 'r', encoding='utf-8') as f:
        for line in f:
            if '<h1>' in line and 'LED Raster Designer' in line:
                index_h1 = _extract_version(line)
                break
    readme = _read_version_from_file('README.md', line_number=1)

    sources = {
        'src/VERSION.txt': version_txt,
        'index.html <title> (line 6)': index_title,
        'index.html <h1> (line 70)': index_h1,
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


# ── CI selector hygiene ─────────────────────────────────────────────
#
# v0.10.9: the version-consistency job selects its tests with
# `pytest -k "a or b or c"`. A clause that matches NOTHING is not an error in
# pytest - it silently selects fewer tests and the job still goes green. One
# clause, "version_txt_is_four_part", named a test that has never existed
# (test_version_txt_is_valid is the real one), so the version-shape check was
# dead in CI for as long as that line had been in the file. Nothing could
# notice: a dead clause and a passing test look identical from outside.
#
# This reads the workflows and holds every selector to naming something real.
# It deliberately scans EVERY workflow rather than just ci.yml, and accepts
# either quote style, because a guard with the same blind spot as the bug it
# guards against is not a guard.

WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')


def _test_names(rel_path=None):
    """Every test function name in a file, or across tests/ when None.

    Matches at ANY indentation: tests/test_launcher_settings.py keeps 21 of
    its tests as methods inside `class Test*` blocks, and an anchored `^def`
    would miss all of them - reporting a live selector as dead.
    """
    if rel_path:
        paths = [os.path.join(ROOT, rel_path)]
    else:
        paths = [os.path.join(WORKFLOWS, '..', '..', 'tests', f)
                 for f in sorted(os.listdir(os.path.join(ROOT, 'tests')))
                 if f.startswith('test_') and f.endswith('.py')]
    names = []
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as fh:
            names.extend(re.findall(r'^\s*def (test_\w+)', fh.read(), re.M))
    return names


def _workflow_pytest_lines():
    """(workflow, lineno, line) for every pytest invocation in .github."""
    out = []
    for name in sorted(os.listdir(WORKFLOWS)):
        if not name.endswith(('.yml', '.yaml')):
            continue
        path = os.path.join(WORKFLOWS, name)
        with open(path, encoding='utf-8') as fh:
            for lineno, line in enumerate(fh.read().splitlines(), 1):
                # `security -k` / `ditto -c -k` also use -k; requiring the
                # word pytest on the line keeps those out.
                if re.search(r'\bpytest\b', line):
                    out.append((name, lineno, line))
    return out


def test_ci_selectors_all_name_something_real():
    """Every pytest selector in every workflow must resolve to a real test.

    pytest treats an unmatched -k clause as "select nothing extra" rather than
    an error, and a --deselect path that does not exist is likewise quiet, so
    a typo removes a guard from CI without ever failing a build. This is the
    only place that can catch that.
    """
    lines = _workflow_pytest_lines()
    assert lines, 'found no pytest invocations in .github/workflows - moved?'

    problems = []
    for wf, lineno, line in lines:
        where = f'{wf}:{lineno}'
        target = re.search(r'(tests/[\w/]+\.py)(?!::)', line)
        target = target.group(1) if target else None

        # -k "a or b", or -k 'a or b'
        k_expr = re.search(r'-k\s+"([^"]+)"', line) or \
            re.search(r"-k\s+'([^']+)'", line)
        if k_expr:
            names = _test_names(target)
            for clause in re.split(r'\bor\b|\band\b', k_expr.group(1)):
                clause = clause.strip()
                if not clause or clause.startswith('not '):
                    continue
                if not any(clause in n for n in names):
                    near = [n for n in names if clause.split('_')[0] in n][:3]
                    problems.append(
                        f'{where}: -k clause "{clause}" matches no test in '
                        f'{target or "tests/"}'
                        + (f' (closest: {", ".join(near)})' if near else ''))

        # Explicit node ids: tests/test_x.py::test_y
        for node in re.findall(r'(tests/[\w/]+\.py)::(\w+)', line):
            path, func = node
            if func not in _test_names(path):
                problems.append(
                    f'{where}: node id {path}::{func} names no such test')

        # --deselect <path>
        for target_path in re.findall(r'--deselect[= ]+(\S+)', line):
            bare = target_path.split('::')[0]
            if not os.path.exists(os.path.join(ROOT, bare)):
                problems.append(
                    f'{where}: --deselect {target_path} - {bare} does not exist')

        # --ignore <path>
        for target_path in re.findall(r'--ignore[= ]+(\S+)', line):
            if not os.path.exists(os.path.join(ROOT, target_path)):
                problems.append(
                    f'{where}: --ignore {target_path} does not exist')

    assert not problems, (
        'these CI selectors silently select nothing, so the checks they were '
        'meant to run are not running:\n  ' + '\n  '.join(problems))
