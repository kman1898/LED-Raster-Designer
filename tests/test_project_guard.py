"""The guard that keeps one test module from poisoning the next.

The browser suites all talk to ONE live server, so whatever a module
leaves behind is what the next module starts from. conftest's
`server_project_guard` / `flask_project_guard` snapshot that shared state
on the way in and put it back on the way out, and every browser module
that mutates it opts in.

It used to snapshot the project alone. Preferences are shared the same
way and leaked straight through: test_pull_list types an engineer into
the pull-sheet dialog, which is stored as a PREFERENCE and not on the
project, and from then on every binder sheet in the session printed that
engineer's initials in its revision row and his name in the overview's
contents. Two binder tests failed in a full run and passed on their own,
which is the worst shape a failure can take - it looks like flake and it
is not.

These tests hold the guard to restoring BOTH, by calling its snapshot and
restore directly rather than staging a two-module run.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module  # noqa: E402

from conftest import _restore_project, _snapshot_project  # noqa: E402


def test_the_guard_puts_the_project_back():
    """The layers a module adds, and the id counter it advanced."""
    before = copy.deepcopy(app_module.current_project)
    before_id = app_module.next_layer_id
    snapshot = _snapshot_project()
    try:
        app_module.current_project['layers'] = [{'id': 9999, 'name': 'LEAKED'}]
        app_module.next_layer_id = before_id + 500
    finally:
        _restore_project(snapshot)
    assert app_module.current_project == before
    assert app_module.next_layer_id == before_id


def test_the_guard_puts_the_preferences_back():
    """A preference is shared state too - see the module docstring."""
    before = copy.deepcopy(getattr(app_module, 'server_preferences', None))
    assert before is not None, 'the server has no preferences to guard'
    snapshot = _snapshot_project()
    try:
        # save_preferences REASSIGNS the dict, so leak it the way the route
        # does rather than by mutating in place.
        app_module.server_preferences = dict(before, engineerName='Test Engineer')
        assert app_module.server_preferences['engineerName'] == 'Test Engineer'
    finally:
        _restore_project(snapshot)
    assert app_module.server_preferences == before, (
        'the engineer leaked out of the module that typed him')


def test_the_snapshot_is_a_copy_not_a_handle():
    """A snapshot that aliased the live objects would restore the very
    mutations it exists to undo, and every one of these tests would pass
    while guarding nothing."""
    snapshot = _snapshot_project()
    project, _next_id, prefs = snapshot
    assert project is not app_module.current_project
    if prefs is not None:
        assert prefs is not app_module.server_preferences
