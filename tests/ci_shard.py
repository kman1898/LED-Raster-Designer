"""Split the test modules into CI shards (2026-10-16).

CI's browser job runs as several parallel jobs; each sets
LRD_CI_SHARD="k/n" and conftest keeps only the modules that land in shard
k. A module is never split, so the module-scoped project guards still hold,
and every module lands in exactly one shard, so the shards together run the
whole suite.

The split is computed from the collected tests, not from a stored timing
file that would go stale: a browser test (one that drives the shared server
or a Playwright browser) weighs BROWSER_WEIGHT, any other test 1, and the
modules are packed heaviest first onto the lightest shard.
"""

BROWSER_WEIGHT = 10
BROWSER_FIXTURES = frozenset({'e2e_server', 'pw_browser', 'server_project_guard'})


def parse_shard(spec):
    """(k, n) from "k/n" with 1 <= k <= n, else ValueError."""
    try:
        k, n = (int(part) for part in str(spec).split('/'))
    except ValueError:
        raise ValueError(f'LRD_CI_SHARD must look like "2/4", not {spec!r}')
    if not 1 <= k <= n:
        raise ValueError(f'LRD_CI_SHARD {spec!r}: shard must be 1..{n}')
    return k, n


def item_weight(fixturenames):
    return BROWSER_WEIGHT if BROWSER_FIXTURES.intersection(fixturenames) else 1


def assign_shards(weights, n):
    """{module: shard 1..n} for WEIGHTS {module: weight}: heaviest module
    first onto the lightest shard, ties broken by name and shard number so
    every worker and every job computes the same split."""
    loads = [0] * n
    out = {}
    for module in sorted(weights, key=lambda m: (-weights[m], m)):
        shard = min(range(n), key=lambda i: (loads[i], i))
        out[module] = shard + 1
        loads[shard] += weights[module]
    return out
