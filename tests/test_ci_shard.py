"""The CI shard split (ci_shard.py) runs every module exactly once."""

import os
import re
import subprocess
import sys

import pytest

from ci_shard import assign_shards, item_weight, parse_shard

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)


def test_parse_shard():
    assert parse_shard('2/4') == (2, 4)
    for bad in ('0/4', '5/4', '4', 'a/b', ''):
        with pytest.raises(ValueError):
            parse_shard(bad)


def test_browser_tests_weigh_more():
    assert item_weight(['pw_browser', 'request']) > item_weight(['client'])


def test_every_module_lands_in_exactly_one_shard_and_the_split_is_stable():
    weights = {f'tests/test_{i:03}.py': (i * 37) % 50 + 1 for i in range(120)}
    a = assign_shards(weights, 4)
    assert set(a) == set(weights) and set(a.values()) == {1, 2, 3, 4}
    assert a == assign_shards(dict(reversed(list(weights.items()))), 4)
    loads = [sum(w for m, w in weights.items() if a[m] == k) for k in (1, 2, 3, 4)]
    assert max(loads) - min(loads) <= max(weights.values())


def _collected(shard=None):
    env = dict(os.environ)
    env.pop('LRD_CI_SHARD', None)
    if shard:
        env['LRD_CI_SHARD'] = shard
    out = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q',
         '-p', 'no:cacheprovider', '-p', 'no:xdist'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    return {line.split('::', 1)[0] for line in out.stdout.splitlines()
            if re.match(r'tests/\S+\.py::', line)}


def test_the_real_suite_splits_into_four_shards_that_cover_it_once():
    shards = [_collected(f'{k}/4') for k in (1, 2, 3, 4)]
    every = _collected()
    union = set().union(*shards)
    assert sum(len(s) for s in shards) == len(union), 'a module ran in two shards'
    assert union == every, sorted(every ^ union)
