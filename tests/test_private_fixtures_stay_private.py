"""The private show fixtures stay out of the (public) repo.

tests/fixtures-local/ holds frozen saves of real client shows - client
data. conftest.private_fixture() reads them from there, and the tests that
need them skip when they are absent (as they always are in CI). Two ways
they could leak, both caught here:

  * a file under the folder is tracked (force-added, or added before the
    ignore rule existed);
  * .gitignore stops ignoring the folder, so the next `git add .` takes
    every show in it.

Run:
    python3 -m pytest tests/test_private_fixtures_stay_private.py -q
"""

import os
import shutil
import subprocess

import pytest

from conftest import PRIVATE_FIXTURES, TESTS_DIR

REPO = os.path.dirname(TESTS_DIR)
FOLDER = 'tests/fixtures-local'

pytestmark = pytest.mark.skipif(
    shutil.which('git') is None or not os.path.exists(os.path.join(REPO, '.git')),
    reason='not a git checkout')


def _git(*args):
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True)


def test_nothing_under_the_private_fixtures_folder_is_tracked():
    out = _git('ls-files', '--', FOLDER)
    assert out.returncode == 0, out.stderr
    tracked = out.stdout.split('\n')
    tracked = [t for t in tracked if t]
    assert tracked == [], (
        'client show data is tracked in the public repo - `git rm --cached` it: %s' % tracked)


@pytest.mark.parametrize('name', ['experts-only-fixture.json', 'kelly.json',
                                  'kelly-live-fixture.json', 'any-new-show.json'])
def test_gitignore_keeps_the_folder_out(name):
    """check-ignore judges the path whether or not the file exists, so this
    holds in CI too, where the folder is empty."""
    path = f'{FOLDER}/{name}'
    out = _git('check-ignore', '--no-index', '-q', path)
    assert out.returncode == 0, f'.gitignore no longer ignores {path} ({out.stderr.strip()})'


def test_the_default_folder_is_the_ignored_one():
    """With no LRD_PRIVATE_FIXTURES override the tests read the folder the
    two checks above guard."""
    if os.environ.get('LRD_PRIVATE_FIXTURES'):
        pytest.skip('LRD_PRIVATE_FIXTURES moves the folder for this run')
    assert os.path.normpath(PRIVATE_FIXTURES) == os.path.normpath(os.path.join(REPO, FOLDER))
