"""Go to ahead is one restore of a shipped snapshot, for every step.

src/static/data/tour_snapshots.json (built by scripts/build_tour_snapshots.py)
holds each tour step's entry snapshot - the scratch show exactly as the
step finds it - so a number typed into the callout's Go to box lands on
that step at once: the snapshot is restored the way Back restores one, and
the step's own act then plays (Matt, 2026-09-16: "an instant skip to step,
not any waiting"). Three things are pinned here:

  - the file is CURRENT: it parses, carries every tour, and each tour's
    signature (app version + step keys and titles, QuickStart.signature)
    equals the live tour's - a step added, removed, renamed or reordered,
    or a version bump, fails with "run python3 scripts/build_tour_snapshots.py";
  - the file is TRUE: the Quick tour, driven again here on this session's
    server, gives the shipped bytes - the rot guard for a step whose act
    changes what the show looks like;
  - the jump WORKS: from a fresh tour, Go to every Advanced step (and all
    of Quick, and every fifth What's New step) lands within three seconds
    via the snapshot, with no shade, and the step's act then finishes done
    - a later "add" step minting ids past the restored show, a step past
    the preference-writing ones still leaving the person's preferences
    alone at Done, and a changed tour falling back to applying the steps.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_tour_snapshots.py -v --browser chromium
"""

import json
import os
import sys
import time

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import build_tour_snapshots as builder                      # noqa: E402
from test_tour_anchors import (_start, _end, _wait_step,    # noqa: E402
                               _step_index, STATE_JS)

FIXTURE = builder.FIXTURE
REBUILD = 'run: python3 scripts/build_tour_snapshots.py'
TOURS = ('quick', 'whatsNew', 'advanced')


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """The tours and the regeneration mutate the shared server project and
    its preferences; leave both as this module found them."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """The generator's own viewport, so the regenerated Quick tour is the
    shipped one to the byte (a drop lands on the same cabinet)."""
    context = pw_browser.new_context(viewport=builder.VIEWPORT)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def _fixture():
    assert os.path.isfile(FIXTURE), f'{FIXTURE} is missing - {REBUILD}'
    with open(FIXTURE, encoding='utf-8') as f:
        return json.load(f)


# ── the file is current ──────────────────────────────────────────────────

def test_fixture_exists_parses_and_has_every_tour():
    data = _fixture()
    assert isinstance(data.get('version'), str) and data['version'], data.get('version')
    assert set(TOURS) <= set(data.get('tours', {})), \
        f"tours in the file: {sorted(data.get('tours', {}))} - {REBUILD}"
    for name in TOURS:
        t = data['tours'][name]
        assert isinstance(t.get('signature'), str) and t['signature'], (name, t.get('signature'))
        snaps = builder.decode_tour(t)
        assert snaps, f'{name}: no snapshots'
        for i, s in enumerate(snaps):
            assert isinstance(s, dict) and isinstance(s.get('layers'), list), \
                f'{name} step {i + 1}: entry {t["steps"][i]!r} is not a project'
    with open(FIXTURE, encoding='utf-8') as f:
        raw = f.read()
    assert '\n' not in raw.strip() and ': ' not in raw[:200], 'the file is not compact JSON'


def test_fixture_signatures_match_the_live_tours(page):
    data = _fixture()
    live_version = page.evaluate(
        "() => (/\\bv(\\d+(?:\\.\\d+)+)/.exec(document.title) || [])[1] || null")
    assert data['version'] == live_version, \
        f'the file was built for v{data["version"]}, the app is v{live_version} - {REBUILD}'
    for name in TOURS:
        live = page.evaluate("(n) => window.QuickStart.signature(n)", name)
        count = page.evaluate("(n) => window.QuickStart.tours()[n].length", name)
        shipped = data['tours'][name]['signature']
        assert shipped == live, \
            f'{name}: the shipped snapshots are for {shipped}, the tour is {live} ' \
            f'(a step was added, removed, renamed or reordered, or the version bumped) - {REBUILD}'
        assert len(data['tours'][name]['steps']) == count, \
            f'{name}: {len(data["tours"][name]["steps"])} snapshots for {count} steps - {REBUILD}'


def _fnv1a(text):
    h = 0x811c9dc5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xffffffff
    return '%08x' % h


def _signature(version, keyed_steps):
    return 'v%s:%d:%s' % (version, len(keyed_steps),
                          _fnv1a('\n'.join('%s|%s' % (k, t) for k, t in keyed_steps)))


def _live_inputs(page, name):
    version = page.evaluate(
        "() => (/\\bv(\\d+(?:\\.\\d+)+)/.exec(document.title) || [])[1] || '?'")
    keyed = page.evaluate("""(n) => {
        const S = window.QuickStart.steps();
        return window.QuickStart.tours()[n].map(s => [Object.keys(S).find(k => S[k] === s), s.title]);
    }""", name)
    return version, [tuple(k) for k in keyed]


def test_signature_is_reproducible_and_trips_on_every_kind_of_change(page):
    """The scheme, redone here: FNV-1a over 'key|title' per step, behind
    the app version and the step count. The same inputs give the browser's
    signature; a step added, removed, renamed, reordered, or a version
    bump, each gives another."""
    version, steps = _live_inputs(page, 'advanced')
    assert all(k for k, _ in steps), steps
    live = page.evaluate("() => window.QuickStart.signature('advanced')")
    assert _signature(version, steps) == live
    base = _signature(version, steps)
    added = steps + [('helpMenu', 'Help')]
    removed = steps[:-1]
    renamed = steps[:5] + [(steps[5][0], steps[5][1] + ' x')] + steps[6:]
    rekeyed = steps[:5] + [(steps[5][0] + '2', steps[5][1])] + steps[6:]
    reordered = [steps[1], steps[0]] + steps[2:]
    bumped = _signature(version + '.1', steps)
    others = {_signature(version, v) for v in (added, removed, renamed, rekeyed, reordered)} | {bumped}
    assert base not in others and len(others) == 6, others


# ── the file is true ─────────────────────────────────────────────────────

def test_quick_tour_regenerated_here_equals_the_shipped_bytes(page):
    """The generator's core, run for the Quick tour on this session's
    server (reset to what a fresh server holds, the way the generator
    starts one): the ten entry snapshots equal the shipped ones byte for
    byte, after the same volatile-field stripping. A step whose act
    changed what the show looks like fails here with its number."""
    import app as app_module
    from app import _build_initial_project
    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1
    app_module.server_preferences = {}
    # The page's own copy of the preferences follows the server's: reload.
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer && window.QuickStart)")
    page.wait_for_timeout(1500)
    data = _fixture()
    shipped = data['tours']['quick']
    collected = builder.collect_tour(page, 'quick')
    assert collected['signature'] == shipped['signature'], REBUILD
    want = builder.decode_tour(shipped)
    got = collected['steps']
    assert len(got) == len(want), (len(got), len(want), REBUILD)
    for i, (a, b) in enumerate(zip(got, want)):
        ca, cb = builder.canonical(builder.strip_volatile(a)), builder.canonical(builder.strip_volatile(b))
        if ca != cb:
            ja, jb = json.loads(ca), json.loads(cb)
            keys = sorted(k for k in set(ja) | set(jb) if ja.get(k) != jb.get(k))
            pytest.fail(f'quick step {i + 1}: the regenerated snapshot differs from the shipped one '
                        f'in {keys} - {REBUILD}')
    assert builder.canonical(builder.encode_tour(collected)) == builder.canonical(shipped), REBUILD


# ── the jump works ───────────────────────────────────────────────────────

LANDING_JS = """() => ({
    index: window.QuickStart.state().index,
    via: window.QuickStart.state().jumpedVia,
    shade: getComputedStyle(document.getElementById('qs-fast')).display,
    jumping: document.body.classList.contains('qs-jumping'),
    callout: getComputedStyle(document.getElementById('qs-callout')).visibility,
})"""


def _jump(page, tour, i, within=3.0):
    """From a fresh `tour`, type step i+1 into Go to and press Enter.
    Returns (seconds until the engine was on step i, the landing, the
    settled step state)."""
    st = _start(page, tour)
    assert st['qs']['index'] == 0, st
    page.fill('#qs-jump', str(i + 1))
    t0 = time.time()
    page.press('#qs-jump', 'Enter')
    landed = None
    while time.time() - t0 < within:
        if page.evaluate("window.QuickStart.state().index") == i:
            landed = time.time() - t0
            break
        time.sleep(0.02)
    landing = page.evaluate(LANDING_JS)
    st = _wait_step(page, i)
    return landed, landing, st


def _assert_landed(tour, i, landed, landing, st):
    where = f"{tour} step {i + 1} ({st['title'] if st else '?'!r})"
    assert landed is not None, f'{where}: not on the step within 3 s ({landing})'
    assert landing['via'] == 'snapshot', f'{where}: landed via {landing["via"]!r}, not the snapshot'
    assert landing['shade'] == 'none' and not landing['jumping'], f'{where}: the shade was up: {landing}'
    assert st and st['qs']['index'] == i, f'{where}: the engine never settled ({st})'
    assert st['state'] in ('done', 'idle') and not st['fail'], f"{where}: {st['state']} - {st['note']!r}"
    if st['state'] == 'done':
        assert st['note'].strip(), f'{where}: done, but no result note'


def _indices(tour, n, every=1):
    return [i for i in range(1, n) if (i % every == 0 or i == n - 1)]


ADVANCED_STEPS = 62
WHATS_NEW_STEPS = 36
QUICK_STEPS = 10


@pytest.mark.parametrize('i', range(1, ADVANCED_STEPS))
def test_go_to_every_advanced_step_lands_on_the_snapshot(page, i):
    n = page.evaluate("() => window.QuickStart.tours().advanced.length")
    assert n == ADVANCED_STEPS, f'the Advanced tour has {n} steps; update ADVANCED_STEPS'
    landed, landing, st = _jump(page, 'advanced', i)
    try:
        _assert_landed('advanced', i, landed, landing, st)
    finally:
        _end(page)


@pytest.mark.parametrize('i', _indices('whatsNew', WHATS_NEW_STEPS, every=5))
def test_go_to_every_fifth_whats_new_step_lands_on_the_snapshot(page, i):
    n = page.evaluate("() => window.QuickStart.tours().whatsNew.length")
    assert n == WHATS_NEW_STEPS, f"the What's New tour has {n} steps; update WHATS_NEW_STEPS"
    landed, landing, st = _jump(page, 'whatsNew', i)
    try:
        _assert_landed('whatsNew', i, landed, landing, st)
    finally:
        _end(page)


@pytest.mark.parametrize('i', range(1, QUICK_STEPS))
def test_go_to_every_quick_step_lands_on_the_snapshot(page, i):
    n = page.evaluate("() => window.QuickStart.tours().quick.length")
    assert n == QUICK_STEPS, f'the Quick tour has {n} steps; update QUICK_STEPS'
    landed, landing, st = _jump(page, 'quick', i)
    try:
        _assert_landed('quick', i, landed, landing, st)
    finally:
        _end(page)


def test_ids_after_a_restored_show_do_not_collide(page):
    """The restore PUT re-seeds the server's counters above the restored
    show, so a step that ADDS after a jump mints a fresh id: the second
    screen is layer 2 beside layer 1, the distro is d1 (none before it),
    and a processor added after the jump is a new run of the counter."""
    i = _step_index(page, 'advanced', 'A second screen')
    landed, landing, st = _jump(page, 'advanced', i)
    try:
        _assert_landed('advanced', i, landed, landing, st)
        ids = page.evaluate("() => window.app.project.layers.map(l => l.id)")
        assert ids == [1, 2], ids
        server = page.evaluate("() => fetch('/api/project').then(r => r.json()).then(p => p.layers.map(l => l.id))")
        assert server == [1, 2], server
    finally:
        _end(page)
    i = _step_index(page, 'advanced', 'Add a distro')
    landed, landing, st = _jump(page, 'advanced', i)
    try:
        _assert_landed('advanced', i, landed, landing, st)
        assert page.evaluate("() => window.app.getDistros().map(d => d.id)") == ['d1']
        procs = page.evaluate("() => (window.app._processorsResolved || []).map(p => p.id)")
        assert len(procs) == 1, procs
        fresh = page.evaluate("""() => fetch('/api/processors', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({deviceId: 'novastar-h9'})})
            .then(r => r.json()).then(st => st.processors.map(p => p.id))""")
        assert len(fresh) == 2 and len(set(fresh)) == 2, fresh
    finally:
        _end(page)


PREFS_JS = """async (patch) => {
    const r = await fetch('/api/preferences');
    const prefs = await r.json();
    if (patch) {
        Object.assign(prefs, patch);
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(prefs)});
        window.app._serverPreferences = prefs;
    }
    return prefs;
}"""


def test_a_jump_past_the_preference_steps_still_puts_preferences_back(page):
    """Border and title block writes a preference; a jump past it to
    Preferences, then Done, leaves the person's title block as it was -
    off - on the server and in the app's cache."""
    original = page.evaluate(PREFS_JS, None)
    page.evaluate(PREFS_JS, {'binderTitleBlock': False})
    page.wait_for_timeout(200)
    try:
        i = _step_index(page, 'advanced', 'Preferences')
        assert i > _step_index(page, 'advanced', 'Border and title block')
        landed, landing, st = _jump(page, 'advanced', i)
        _assert_landed('advanced', i, landed, landing, st)
        page.locator('#qs-next').click()      # Next from Preferences: Help
        st = _wait_step(page, i + 1)
        assert st['state'] == 'done', st
        page.locator('#qs-next').click()      # the outro
        _wait_step(page, i + 2)
        page.locator('#qs-next').click()      # Done
        page.wait_for_timeout(1500)
        assert not page.evaluate("window.QuickStart.state().visible")
        prefs = page.evaluate(PREFS_JS, None)
        assert prefs.get('binderTitleBlock') is False, prefs.get('binderTitleBlock')
        assert page.evaluate("window.app.getPreferences().binderTitleBlock") is False
    finally:
        _end(page)
        page.evaluate(PREFS_JS, {'binderTitleBlock': original.get('binderTitleBlock', True)})
        page.wait_for_timeout(200)


def test_a_changed_tour_falls_back_to_applying_the_steps(page):
    """A tour whose steps no longer match the shipped signature must not
    land on a stale show: with one title changed under it, Go to ahead
    applies the steps between (jumpedVia 'apply') and still lands done."""
    i = _step_index(page, 'quick', 'Add a processor')
    page.evaluate("() => { window.__qsTitle = window.QuickStart.steps().cabinetSize.title; "
                  "window.QuickStart.steps().cabinetSize.title += ' (changed)'; }")
    try:
        assert page.evaluate("() => window.QuickStart.signature('quick')") != _fixture()['tours']['quick']['signature']
        st = _start(page, 'quick')
        assert st['qs']['index'] == 0, st
        page.fill('#qs-jump', str(i + 1))
        page.press('#qs-jump', 'Enter')
        page.wait_for_function("(i) => window.QuickStart.state().index === i", arg=i, timeout=120000)
        st = _wait_step(page, i)
        assert st['state'] == 'done' and not st['fail'], st
        assert page.evaluate("window.QuickStart.state().jumpedVia") == 'apply'
        assert page.evaluate("getComputedStyle(document.getElementById('qs-fast')).display") == 'none'
    finally:
        _end(page)
        page.evaluate("() => { window.QuickStart.steps().cabinetSize.title = window.__qsTitle; }")
    assert page.evaluate("() => window.QuickStart.signature('quick')") == _fixture()['tours']['quick']['signature']
