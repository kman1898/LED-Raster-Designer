"""The Power guide (Help > Guides > Power): it starts on its own demo
show, every step takes by Next, and Go to lands on every step.

The guide's demo show is the wall wired for data (the MX40 Pro and the H9
of Mixed redundancy), before any distro. tests/guide_suite.py says what
each check proves; tests/test_guide_windows.py holds the guide's shared
windows open.

Run locally (each session takes its own free port):
    python -m pytest tests/test_guide_power.py -n 4 --dist loadfile
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from guide_suite import (page, _restore_server_project, _guide_closed,  # noqa: E402,F401
                         check_start, drive_whole_guide, go_to_step, step_count)

GUIDE = 'power'
# The guide's steps, its intro and outro among them. A step added or taken
# away changes this; the parametrized Go to below covers every one.
STEPS = 43
DEMO_SHOW = dict(name='Demo Show', screens=['DEMO WALL'], processors=2, distros=0, services=0, beaches=0, groups=0)


def test_the_guide_has_its_steps(page):
    assert step_count(page, GUIDE) == STEPS, f'the {GUIDE} guide has another step count; update STEPS'


def test_it_starts_on_its_own_demo_show(page):
    check_start(page, GUIDE, DEMO_SHOW, via='snapshot')


def test_every_step_takes_by_next(page):
    drive_whole_guide(page, GUIDE)


@pytest.mark.parametrize('i', range(1, STEPS))
def test_go_to_every_step_lands_on_the_snapshot(page, i):
    go_to_step(page, GUIDE, i)
