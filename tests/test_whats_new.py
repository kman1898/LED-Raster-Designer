"""The "What's New" window: shown once after an update that has something
to say (a new MAJOR.MINOR's highlights, or Advanced Guide steps added by
any release, patches included), with Show me running exactly those steps;
never stacked on the first-run guide; reopenable from Help.

Two halves:

  Static (no browser) - the rot guard and the wiring:
    - VERSION.txt's top version MUST have an entry in whatsnew_content.js.
      This is the test that FAILS when a new MAJOR.MINOR ships without its
      curated highlights.
    - every entry is 4-8 items, plain text, no emoji;
    - index.html loads both scripts and carries ONE Help menu item for What's
      New, and app-menubar.js dispatches it.

  Browser (Playwright, shared e2e server) - the gating matrix and the modal:
    - newSteps() filters the Advanced steps by `since`, in guide order;
    - decide(): a patch with new steps offers them, a patch without is
      silent, skipped versions get every step since, a minor/major change
      shows its entry, first run stamps silently, older versions are quiet;
    - autoRun(): a patch update with steps opens the window with Show me,
      Close stamps and skips, a patch with none is not offered;
    - Show me runs only the new steps, each from its entry snapshot;
    - Help -> What's New reopens it regardless of the stamp.

Run the browser half ALONE (the harness pins one port):
    python -m pytest tests/test_whats_new.py -v --browser chromium
"""

import contextlib
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')

CONTENT_JS = os.path.join(SRC, 'static', 'js', 'whatsnew_content.js')
LOGIC_JS = os.path.join(SRC, 'static', 'js', 'whatsnew.js')
INDEX_HTML = os.path.join(SRC, 'templates', 'index.html')
MENUBAR_JS = os.path.join(SRC, 'static', 'js', 'app-menubar.js')
VERSION_TXT = os.path.join(SRC, 'VERSION.txt')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _top_version():
    """First vX.Y[.Z] heading in VERSION.txt - the shipped version."""
    m = re.search(r'^v(\d+)\.(\d+)(?:\.\d+)*\s*-', _read(VERSION_TXT), re.M)
    assert m, 'VERSION.txt has no vX.Y version heading'
    return '%s.%s' % (m.group(1), m.group(2))


def _content_entries():
    """{key: entry-source} parsed from whatsnew_content.js; a key is a
    MAJOR.MINOR ('1.5') or a patch's full version ('1.5.3')."""
    src = _read(CONTENT_JS)
    keys = [(m.group(1), m.start())
            for m in re.finditer(r"^\s{4}'(\d+\.\d+(?:\.\d+)?)':", src, re.M)]
    assert keys, 'whatsnew_content.js defines no version entries'
    entries = {}
    for i, (key, start) in enumerate(keys):
        end = keys[i + 1][1] if i + 1 < len(keys) else len(src)
        entries[key] = src[start:end]
    return entries


# ── the rot guard ────────────────────────────────────────────────────────

def test_top_version_has_a_whatsnew_entry():
    """A new MAJOR.MINOR cannot ship without curated highlights.

    When VERSION.txt's top version moves to a new feature version (0.13,
    1.0, ...) this fails until whatsnew_content.js gets that entry.
    """
    top = _top_version()
    assert top in _content_entries(), (
        "VERSION.txt ships v%s but whatsnew_content.js has no '%s' entry - "
        "write the highlights before releasing a new MAJOR.MINOR." % (top, top))


def test_entries_are_4_to_8_items():
    for key, body in _content_entries().items():
        n = len(re.findall(r'\{\s*h:', body))
        assert 4 <= n <= 8, '%s entry has %d items; the splash wants 4-8' % (key, n)
        assert re.search(r"title:\s*'", body), '%s entry has no title' % key


def test_content_is_plain_text_no_emoji():
    src = _read(CONTENT_JS)
    # No emoji / pictographs anywhere in the file.
    for ch in src:
        assert not (0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF), (
            'emoji %r in whatsnew_content.js; the splash is plain text' % ch)
    # No HTML markup inside item strings (textContent rendering, plain voice).
    for key, body in _content_entries().items():
        for m in re.finditer(r"[hd]:\s*'([^']*)'", body):
            assert '<' not in m.group(1), '%s entry contains markup: %r' % (key, m.group(1))


def test_content_never_says_retired_words():
    """The splash is pure display text, so the whole file must stay clean
    of the words the app no longer says: 'tails' (circuits, not tails -
    user ruling, 2026-08-30), 'Signal + Power' (the tick is Wiring; Power
    Wiring and Data Wiring are sheets of their own), 'N-way' (a snake is an
    N channel snake) and 'Halves' (the port shape is OPT Split / Split).
    Same guard as tests/test_tour_anchors.py runs over the tours."""
    from test_tour_anchors import _retired_wording_hits
    hits = _retired_wording_hits(_read(CONTENT_JS))
    assert not hits, 'whatsnew_content.js still says:\n' + '\n'.join(hits)


def test_content_reads_like_release_notes():
    """Plain release-note voice: no em dashes and none of the words that
    make a note read like an advert."""
    src = _read(CONTENT_JS)
    assert '\u2014' not in src, 'whatsnew_content.js has an em dash'
    for word in ('seamless', 'powerful', 'effortless'):
        assert not re.search(r'\b%s' % word, src, re.I), word


def test_the_running_patch_has_its_own_entry():
    """VERSION.txt's top version, when it is a patch that added guide
    steps (a step with its `since`), carries an entry of its own; the
    window would otherwise describe 1.5.0 or list bare step titles. A
    feature release (X.Y.0) is led by its MAJOR.MINOR entry instead
    (test_top_version_has_a_whatsnew_entry)."""
    m = re.search(r'^v(\d+\.\d+\.(\d+))\s*-', _read(VERSION_TXT), re.M)
    assert m
    running = m.group(1)
    with open(os.path.join(SRC, 'static', 'js', 'quickstart.js'), encoding='utf-8') as f:
        added_steps = ("since: '%s'" % running) in f.read()
    if added_steps and int(m.group(2)) > 0:
        assert running in _content_entries(), (
            "VERSION.txt ships v%s, a patch that added guide steps, but "
            "whatsnew_content.js has no '%s' entry" % (running, running))
    # The shipped 1.5.3 entry stays for anyone who skips it.
    assert "title: '2fers and 3fers in custom mode" in _content_entries()['1.5.3']


def test_every_item_is_its_own_subject():
    """One entry per thing that changed for the user, none twice: no two
    items share a heading, and no item is the run-on that grew by
    accretion - each d stays under a short paragraph."""
    for key, body in _content_entries().items():
        heads = re.findall(r"h:\s*'([^']*)'", body)
        assert len(heads) == len(set(heads)), '%s repeats a heading: %r' % (key, heads)
        for m in re.finditer(r"d:\s*'([^']*)'", body):
            d = m.group(1)
            assert len(d) <= 1000, (
                '%s item %r runs to %d characters; split it into entries a '
                'reader can scan' % (key, d[:40], len(d)))


# ── the wiring (new files must not rot) ──────────────────────────────────

def test_index_loads_splash_scripts():
    html = _read(INDEX_HTML)
    assert '/static/js/whatsnew_content.js' in html
    assert '/static/js/whatsnew.js' in html
    # Content loads before the logic that reads it.
    assert html.index('whatsnew_content.js') < html.index('/static/js/whatsnew.js')
    # The splash defers to the tour, so it must load after quickstart.js.
    assert html.index('quickstart.js') < html.index('/static/js/whatsnew.js')


def test_help_menu_has_whats_new():
    html = _read(INDEX_HTML)
    m = re.search(r'data-action="whats-new"[^>]*data-label="([^"]+)"', html)
    assert m, 'Help menu has no whats-new option'
    assert 'New' in m.group(1)


def test_menu_action_dispatches_to_whatsnew():
    src = _read(MENUBAR_JS)
    assert "case 'whats-new':" in src
    assert 'WhatsNew.open()' in src


def test_help_menu_has_one_whats_new_entry():
    """The What's New in 1.0 guide is gone: its menu item and handler with
    it. One entry opens the window; Show me lives inside it."""
    html = _read(INDEX_HTML)
    help_menu = html[html.index('id="menu-help"'):]
    help_menu = help_menu[:help_menu.index('</div>\n\n')] if '</div>\n\n' in help_menu else help_menu
    labels = re.findall(r'data-label="([^"]*New[^"]*)"', help_menu)
    assert labels == ['What’s New…'], labels
    assert 'whats-new-tour' not in html
    assert 'whats-new-tour' not in _read(MENUBAR_JS)


def test_logic_uses_its_own_storage_key():
    src = _read(LOGIC_JS)
    assert "lrd_whatsnew_seen" in src
    # It must not touch the tour's key except to read whether the tour runs.
    assert "localStorage.setItem('lrd_quickstart_first_run_done'" not in src


# ── browser: gating matrix + modal behavior ──────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def _decide(page, current, stamped):
    return page.evaluate(
        "([c, s]) => window.WhatsNew.decide(c, s)", [current, stamped])


def _new_steps(page, after, up_to):
    return page.evaluate(
        "([a, u]) => window.QuickStart.newSteps(a, u)", [after, up_to])


def _since_table(page):
    """[(key, since)] of the Advanced Guide, in guide order."""
    return [tuple(x) for x in page.evaluate("""() => {
        const S = window.QuickStart.steps();
        return window.QuickStart.tours().advanced.map(s =>
            [Object.keys(S).find(k => S[k] === s), s.since || null]);
    }""")]


def _v(s):
    return tuple(int(x) for x in s.split('.'))


def _pad(t):
    return t + (0,) * (4 - len(t))


# 1.5.4 only ever shipped as betas (the release became 1.6.0), so 1.5.3 is
# the one real patch entry. The patch logic that needs a second one (a
# skipped patch, the entries that follow) runs on this stand-in, put in the
# page as a 1.5.4 entry and taken out again.
FAKE_PATCH = {'title': 'A stand-in patch entry', 'items': [
    {'h': 'Stand-in one', 'd': 'The first stand-in item.'},
    {'h': 'Stand-in two', 'd': 'The second stand-in item.'},
    {'h': 'Stand-in three', 'd': 'The third stand-in item.'},
    {'h': 'Stand-in four', 'd': 'The fourth stand-in item.'}]}


@contextlib.contextmanager
def _patch_entry(page, key='1.5.4'):
    page.evaluate("""([k, e]) => { window.__wnHeld = [k in window.WHATS_NEW_CONTENT,
        window.WHATS_NEW_CONTENT[k]]; window.WHATS_NEW_CONTENT[k] = e; }""", [key, FAKE_PATCH])
    try:
        yield
    finally:
        page.evaluate("""(k) => { const [had, v] = window.__wnHeld;
            if (had) window.WHATS_NEW_CONTENT[k] = v; else delete window.WHATS_NEW_CONTENT[k]; }""", key)


# ── the steps the walkthrough runs ───────────────────────────────────────

def test_new_steps_filter_by_since(page):
    """newSteps(after, upTo) is every Advanced step whose `since` is newer
    than `after` and not newer than `upTo`, in guide order, checked
    against the step table for several windows, and by name for the 1.5.3
    and 1.6.0 steps."""
    table = _since_table(page)
    assert any(s for _, s in table), 'no Advanced step carries since'
    for after, up_to in (('1.4.9', '1.5.0'), ('1.5.0', '1.5.2'), ('1.5.2', '1.5.3'),
                         ('1.5', '1.5.3'), ('1.0', '1.5.3'), ('1.5.3', '1.5.3'),
                         ('1.5.3', '1.6.0'), ('1.5.2', '1.6.0'), ('1.5.4', '1.6.0'),
                         ('1.5.99999', '1.6.0'), ('1.6.0', '1.6.0'), ('1.5', '1.6')):
        want = [k for k, s in table if s
                and _pad(_v(after)) < _pad(_v(s)) <= _pad(_v(up_to))]
        assert _new_steps(page, after, up_to) == want, (after, up_to)
    assert _new_steps(page, '1.5.2', '1.5.3') == [
        'cableStock', 'cableStockPieces', 'takeOver', 'customPower', 'customDraw', 'sweepShare',
        'addService', 'serviceRating', 'serviceDistro']
    assert _new_steps(page, '1.5.3', '1.6.0') == [
        'panelName', 'startPage', 'startPanel', 'sameAsLast', 'avgPower', 'zPattern', 'mixedRedundancy',
        'cardNames', 'fiberMode', 'fiberExtension', 'procCableList', 'panelInput',
        'jumperNames', 'pullPanels', 'cableStockPerKind', 'feederLength', 'groupNames', 'fiberPage',
        'mirrorScreen',
        'portPlug', 'portNumbers', 'portsMinimum', 'powerZPattern', 'circuitNumbers', 'redrawAsOne',
        'sweepPorts']
    # 1.5.4 never shipped in full: no step is marked with it, and the
    # steps its betas brought are 1.6.0's.
    assert _new_steps(page, '1.5.3', '1.5.4') == []
    assert _new_steps(page, '1.5.4', '1.6.0') == _new_steps(page, '1.5.3', '1.6.0')
    # A step is never newer than the running version.
    assert not set(_new_steps(page, '1.5.2', '1.5.2'))
    assert _new_steps(page, 'junk', '1.5.3') == []


# ── decide(): the gating matrix ──────────────────────────────────────────

def test_decide_patch_update_with_new_steps_offers_them(page):
    """1.5.2 -> 1.5.3: 1.5.3's own entry and its new steps, both."""
    d = _decide(page, '1.5.3', '1.5.2')
    assert d['show'] is True and d['stamp'] is None, d
    assert d['window'] == {'key': '1.5.3', 'also': [], 'after': '1.5.2', 'upTo': '1.5.3',
                           'steps': _new_steps(page, '1.5.2', '1.5.3'), 'stamp': '1.5.3'}, d
    assert d['window']['steps'], d
    # A patch with an entry of its own and no steps still shows it.
    with _patch_entry(page):
        d = _decide(page, '1.5.4', '1.5.3')
        assert d['window'] == {'key': '1.5.4', 'also': [], 'after': '1.5.3', 'upTo': '1.5.4',
                               'steps': [], 'stamp': '1.5.4'}, d


def test_decide_a_skipped_patch_shows_every_patch_entry_since(page):
    """1.5.2 -> 1.5.4 (a stand-in patch entry): 1.5.4's own entry, then
    1.5.3's, newest first, and Show me has the steps of both."""
    with _patch_entry(page):
        d = _decide(page, '1.5.4', '1.5.2')
        assert d['show'] and d['window']['key'] == '1.5.4' and d['window']['also'] == ['1.5.3'], d
        assert d['window']['steps'] == _new_steps(page, '1.5.2', '1.5.4'), d
        assert {'cableStock', 'takeOver'} <= set(d['window']['steps']), d
        # Only patches of the running MAJOR.MINOR newer than the stamp.
        assert _decide(page, '1.5.4', '1.5.3')['window']['also'] == [], d
    # Without its own entry the steps lead, the older entry still follows.
    d = _decide(page, '1.5.4', '1.5.2')
    assert d['window']['key'] is None and d['window']['also'] == ['1.5.3'], d


def test_decide_1_5_3_to_1_6_0_shows_the_1_6_entry_and_its_steps(page):
    """1.5.3 -> 1.6.0, the feature release: the '1.6' entry leads, no patch
    entry follows (1.5.3's is older than the stamp, and 1.6 has none yet),
    and Show me has exactly the steps marked 1.6.0."""
    d = _decide(page, '1.6.0', '1.5.3')
    steps = _new_steps(page, '1.5.3', '1.6.0')
    assert d == {'show': True, 'stamp': None, 'window': {
        'key': '1.6', 'also': [], 'after': '1.5.3', 'upTo': '1.6.0',
        'steps': steps, 'stamp': '1.6.0'}}, d
    assert steps and all(page.evaluate(
        "(k) => window.QuickStart.steps()[k].since", k) == '1.6.0' for k in steps), steps
    # The steps marked 1.5.x are not news to a 1.5.3 user.
    assert not {'cableStock', 'takeOver', 'fileExports'} & set(steps), steps
    # From further back the 1.6 entry still leads, with every step since.
    d = _decide(page, '1.6.0', '1.5.2')
    assert d['window']['key'] == '1.6' and d['window']['also'] == [], d
    assert d['window']['steps'] == _new_steps(page, '1.5.2', '1.6.0'), d
    assert {'cableStock', 'mirrorScreen'} <= set(d['window']['steps']), d


def test_decide_skipped_versions_get_every_step_since(page):
    """1.5.0 -> 1.5.3: every step added in 1.5.1, 1.5.2 and 1.5.3, in
    guide order. A stamp from before 1.5.3 holds MAJOR.MINOR only ('1.5'),
    which reads as 1.5.0."""
    d = _decide(page, '1.5.3', '1.5.0')
    assert d['show'] and d['window']['steps'] == _new_steps(page, '1.5.0', '1.5.3'), d
    assert 'fileExports' in d['window']['steps'], d
    assert _decide(page, '1.5.3', '1.5')['window']['steps'] == d['window']['steps']


def test_decide_patch_without_new_steps_is_silent(page):
    assert _decide(page, '1.5.5', '1.5.4') == {'show': False, 'stamp': '1.5.5', 'window': None}
    assert _decide(page, '1.0.2', '1.0.1') == {'show': False, 'stamp': '1.0.2', 'window': None}
    assert _decide(page, '1.6.1', '1.6.0') == {'show': False, 'stamp': '1.6.1', 'window': None}


def test_decide_minor_change_shows_the_entry_and_its_steps(page):
    d = _decide(page, '1.5.0', '1.4.2')
    assert d['show'] and d['window']['key'] == '1.5', d
    assert d['window']['also'] == [], d
    assert d['window']['steps'] == _new_steps(page, '1.4.2', '1.5.0'), d
    # Straight to 1.5.3: the 1.5 highlights lead, 1.5.3's own entry
    # follows, and Show me has every step since 1.4.2.
    d = _decide(page, '1.5.3', '1.4.2')
    assert d['show'] and d['window']['key'] == '1.5' and d['window']['also'] == ['1.5.3'], d
    assert d['window']['steps'] == _new_steps(page, '1.4.2', '1.5.3'), d
    # Straight to a 1.5.4 (a stand-in patch entry): the 1.5 highlights,
    # then 1.5.4's and 1.5.3's.
    with _patch_entry(page):
        d = _decide(page, '1.5.4', '1.4.2')
        assert d['window']['key'] == '1.5' and d['window']['also'] == ['1.5.4', '1.5.3'], d
        assert d['window']['steps'] == _new_steps(page, '1.4.2', '1.5.4'), d
    # Straight to 1.6.0: the 1.6 highlights lead; no 1.6 patch entry
    # follows, and Show me has every step since 1.4.2.
    d = _decide(page, '1.6.0', '1.4.2')
    assert d['show'] and d['window']['key'] == '1.6' and d['window']['also'] == [], d
    assert d['window']['steps'] == _new_steps(page, '1.4.2', '1.6.0'), d
    # A feature version with an entry and no steps still shows (no Show me).
    d = _decide(page, '1.4.0', '1.3.2')
    assert d['show'] and d['window']['key'] == '1.4' and d['window']['steps'] == [], d


def test_decide_major_change_shows(page):
    assert page.evaluate("window.WhatsNew._majorMinor('1.0.3')") == '1.0'
    d = _decide(page, '1.0.1', '0.11.2')
    assert d['show'] and d['window']['key'] == '1.0', d


def test_decide_first_run_stamps_silently(page):
    """No stamp = brand-new install: never show (the guide owns first run)."""
    assert _decide(page, '1.5.3', None) == {'show': False, 'stamp': '1.5.3', 'window': None}


def test_decide_same_or_older_version_is_silent(page):
    assert _decide(page, '1.5.3', '1.5.3') == {'show': False, 'stamp': None, 'window': None}
    assert _decide(page, '1.5.2', '1.5.3') == {'show': False, 'stamp': '1.5.2', 'window': None}


def test_decide_full_release_after_its_betas_shows_once(page):
    """Owner, 2026-10-21: the first launch of a new version always shows
    the window. A beta stamps its whole tag, so the full release it led to
    is still news; between betas of one version it stays quiet."""
    d = _decide(page, '1.5.3', '1.5.3-beta.11')
    assert d['show'] and d['window']['key'] == '1.5.3', d
    assert d['window']['steps'] == _new_steps(page, '1.5.2', '1.5.3'), d
    assert d['window']['after'] is None and d['window']['stamp'] == '1.5.3', d
    assert _decide(page, '1.5.3-beta.11', '1.5.3-beta.10') == {
        'show': False, 'stamp': '1.5.3-beta.11', 'window': None}
    assert _decide(page, '1.5.3-beta.11', '1.5.3-beta.11') == {
        'show': False, 'stamp': None, 'window': None}
    assert _decide(page, '1.5.3-beta.11', '1.5.3') == {
        'show': False, 'stamp': '1.5.3-beta.11', 'window': None}
    up = _decide(page, '1.5.3-beta.2', '1.5.2')
    assert up['show'] and up['window']['stamp'] == '1.5.3-beta.2', up


def test_decide_a_beta_straight_to_a_later_version_shows_its_own_version_too(page):
    """1.5.3-beta.11 -> 1.5.4 (a stand-in patch entry): the beta never ran
    the full 1.5.3, so the window shows 1.5.4's entry, then 1.5.3's, and
    the steps of both. A bare stamp no full release could write (a 1.5.3
    beta's, before the mark) reads the same; a bare 1.5.2 stamp is a full
    release's and only steps back to itself. The real case: a 1.5.4 beta
    (1.5.4 never shipped in full) straight to 1.6.0 gets the 1.6 entry and
    every 1.6.0 step, and so does a 1.6.0 beta reaching 1.6.0."""
    want = _new_steps(page, '1.5.2', '1.5.4')
    with _patch_entry(page):
        for stamped in ('1.5.3-beta.11', '1.5.3-legacy'):
            d = _decide(page, '1.5.4', stamped)
            assert d['show'] and d['window']['key'] == '1.5.4', (stamped, d)
            assert d['window']['also'] == ['1.5.3'] and d['window']['steps'] == want, (stamped, d)
            assert d['window']['after'] is None and d['window']['stamp'] == '1.5.4', (stamped, d)
        d = _decide(page, '1.5.4', '1.5.2-legacy')
        assert d['window']['steps'] == want and d['window']['after'] == '1.5.2', d
        d = _decide(page, '1.5.4', '1.5.4-beta.3')
        assert d['window']['key'] == '1.5.4' and d['window']['also'] == [], d
        assert d['window']['steps'] == _new_steps(page, '1.5.3', '1.5.4'), d
    steps = _new_steps(page, '1.5.3', '1.6.0')
    for stamped in ('1.5.4-beta.2', '1.5.4-beta.3', '1.6.0-beta.1'):
        d = _decide(page, '1.6.0', stamped)
        assert d == {'show': True, 'stamp': None, 'window': {
            'key': '1.6', 'also': [], 'after': None, 'upTo': '1.6.0',
            'steps': steps, 'stamp': '1.6.0'}}, (stamped, d)


def test_autorun_shows_the_full_release_to_a_bare_beta_stamp(page):
    """Betas up to 1.5.3 stamped the bare version. Without the mark this
    build writes, a stamp equal to the full release reads as a beta's: the
    window opens once, and dismissing it marks the stamp as a full one."""
    _serve_version(page, '1.5.3')
    try:
        page.evaluate("""() => { localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.3');
            localStorage.removeItem(window.WhatsNew.MARK_KEY); }""")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        page.click('#whatsnew-close')
        assert page.evaluate("[localStorage.getItem(window.WhatsNew.LS_KEY), localStorage.getItem(window.WhatsNew.MARK_KEY)]") == ['1.5.3', '1']
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_timeout(400)
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_decide_unknown_version_stamps_silently(page):
    """Feature version changed but no curated entry and no steps: quiet."""
    assert _decide(page, '1.99.0', '1.98.0') == {'show': False, 'stamp': '1.99.0', 'window': None}


def test_decide_garbage_version_is_silent(page):
    assert _decide(page, 'not-a-version', '0.11') == {'show': False, 'stamp': None, 'window': None}


# ── autoRun(): what the first launch after an update does ───────────────

def _modal_visible(page):
    return page.evaluate(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display !== 'none'; }")


def _serve_version(page, version):
    page.unroute('**/api/version')
    page.route('**/api/version', lambda r: r.fulfill(json={'version': version}))


def _wait_modal(page):
    page.wait_for_function(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display === 'block'; }")


def test_autorun_update_shows_then_stamp_silences(page):
    """Stamp behind the running version -> window; dismiss stamps the
    running version; quiet after."""
    page.unroute('**/api/version')
    page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '0.10')")
    page.evaluate("window.WhatsNew.autoRun(true)")
    _wait_modal(page)
    heading = page.evaluate(
        "document.querySelector('#whatsnew-modal .modal-content').textContent")
    server = page.evaluate("fetch('/api/version').then(r => r.json()).then(d => d.version)")
    server_mm = page.evaluate("(v) => window.WhatsNew._majorMinor(v)", server)
    assert ('v' + server_mm) in heading
    page.click('#whatsnew-close')
    assert not _modal_visible(page)
    assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == server
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_timeout(400)
    assert not _modal_visible(page)


def _entry(page, key):
    return page.evaluate("(k) => window.WHATS_NEW_CONTENT[k]", key)


def _panel_text(page):
    return page.evaluate("document.querySelector('#whatsnew-modal .modal-content').textContent")


def _step_titles(page, keys):
    return page.evaluate("""(keys) => keys.map(k => {
        const t = document.createElement('textarea');
        t.innerHTML = window.QuickStart.steps()[k].title; return t.value; })""", keys)


def test_autorun_patch_update_with_new_steps_offers_show_me(page):
    """1.5.2 -> 1.5.3: the window opens on a patch release that added
    guide steps, shows 1.5.3's own title and items under "What's new in
    v1.5.3", offers Show me for the steps added in 1.5.3, and Close skips
    them (stamped, quiet after)."""
    _serve_version(page, '1.5.3')
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        text = _panel_text(page)
        entry = _entry(page, '1.5.3')
        assert 'What’s new in v1.5.3' in text, text
        assert page.evaluate("document.querySelector('#whatsnew-modal h2').textContent") == entry['title']
        assert 6 <= len(entry['items']) <= 8, entry
        for item in entry['items']:
            assert item['h'] in text and item['d'] in text, (item, text)
        assert 'v1.5 ' not in text and 'And in' not in text, text
        show = page.evaluate("""() => { const b = document.getElementById('whatsnew-show-me');
            return b && { text: b.textContent, title: b.title }; }""")
        keys = _new_steps(page, '1.5.2', '1.5.3')
        assert show == {'text': 'Show me',
                        'title': 'Play the %d new steps of the Advanced Guide' % len(keys)}, show
        assert keys and all(page.evaluate(
            "(k) => window.QuickStart.steps()[k].since", k) == '1.5.3' for k in keys), keys
        page.click('#whatsnew-close')
        assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.3'
        assert not page.evaluate("window.QuickStart.state().visible")
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_timeout(400)
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_patch_without_an_entry_lists_the_step_titles(page):
    """Without 1.5.3's own entry the window falls back to the new steps'
    titles, still with Show me."""
    _serve_version(page, '1.5.3')
    page.evaluate("window.__wn153 = window.WHATS_NEW_CONTENT['1.5.3'];"
                  " delete window.WHATS_NEW_CONTENT['1.5.3']")
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        text = _panel_text(page)
        assert 'New in the Advanced Guide' in text, text
        for t in _step_titles(page, _new_steps(page, '1.5.2', '1.5.3')):
            assert t in text, (t, text)
        assert page.evaluate("!!document.getElementById('whatsnew-show-me')")
        page.click('#whatsnew-close')
    finally:
        page.evaluate("window.WHATS_NEW_CONTENT['1.5.3'] = window.__wn153")
        page.unroute('**/api/version')


def test_update_across_a_feature_version_shows_both_entries(page):
    """1.4.2 -> 1.5.3: the 1.5 highlights, then "And in v1.5.3" with
    1.5.3's own entry, and Show me for every step since 1.4.2."""
    _serve_version(page, '1.5.3')
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.4.2')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        text = _panel_text(page)
        heads = page.evaluate(
            "[...document.querySelectorAll('#whatsnew-modal h2')].map(h => h.textContent)")
        assert heads == [_entry(page, '1.5')['title'], _entry(page, '1.5.3')['title']], heads
        assert 'What’s new in v1.5' in text and 'And in v1.5.3' in text, text
        n = len(_new_steps(page, '1.4.2', '1.5.3'))
        assert page.evaluate("document.getElementById('whatsnew-show-me').title") == \
            'Play the %d new steps of the Advanced Guide' % n
        page.click('#whatsnew-close')
        assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.3'
    finally:
        page.unroute('**/api/version')


def test_autorun_patch_update_without_new_steps_is_not_offered(page):
    _serve_version(page, '1.5.5')
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.4')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_function(
            "() => localStorage.getItem(window.WhatsNew.LS_KEY) === '1.5.5'")
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_update_over_a_skipped_patch_shows_both_patch_entries(page):
    """1.5.2 -> 1.5.4 (a stand-in patch entry): "What's new in v1.5.4"
    with 1.5.4's entry, then "And in v1.5.3" with 1.5.3's, and Show me for
    every step since 1.5.2."""
    _serve_version(page, '1.5.4')
    try:
        with _patch_entry(page):
            page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
            page.evaluate("window.WhatsNew.autoRun(true)")
            _wait_modal(page)
            text = _panel_text(page)
            heads = page.evaluate(
                "[...document.querySelectorAll('#whatsnew-modal h2')].map(h => h.textContent)")
            assert heads == [FAKE_PATCH['title'], _entry(page, '1.5.3')['title']], heads
            assert 'What’s new in v1.5.4' in text and 'And in v1.5.3' in text, text
            for item in FAKE_PATCH['items'] + _entry(page, '1.5.3')['items']:
                assert item['h'] in text and item['d'] in text, (item, text)
            n = len(_new_steps(page, '1.5.2', '1.5.4'))
            assert page.evaluate("document.getElementById('whatsnew-show-me').title") == \
                'Play the %d new steps of the Advanced Guide' % n
            page.click('#whatsnew-close')
            assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.4'
    finally:
        page.unroute('**/api/version')


def test_help_on_a_patch_shows_its_entry_then_the_earlier_patches(page):
    """Help > What's New on 1.5.4 (a stand-in patch entry), nothing owed:
    1.5.4's entry, then 1.5.3's, and Show me runs the steps those two
    versions added."""
    _serve_version(page, '1.5.4')
    try:
        with _patch_entry(page):
            page.evaluate("""() => { localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.4');
                localStorage.setItem(window.WhatsNew.MARK_KEY, '1'); }""")
            page.evaluate("window.WhatsNew.open()")
            _wait_modal(page)
            heads = page.evaluate(
                "[...document.querySelectorAll('#whatsnew-modal h2')].map(h => h.textContent)")
            assert heads == [FAKE_PATCH['title'], _entry(page, '1.5.3')['title']], heads
            text = _panel_text(page)
            assert 'What’s new in v1.5.4' in text and 'And in v1.5.3' in text, text
            n = len(_new_steps(page, '1.5.2', '1.5.4'))
            assert page.evaluate("document.getElementById('whatsnew-show-me').title") == \
                'Play the %d new steps of the Advanced Guide' % n
            page.click('#whatsnew-close')
    finally:
        page.unroute('**/api/version')


def test_autorun_1_5_3_to_1_6_0_shows_the_1_6_entry(page):
    """1.5.3 -> 1.6.0: "What's new in v1.6" with the '1.6' entry alone,
    Show me for the 1.6.0 steps, and Close stamps 1.6.0."""
    _serve_version(page, '1.6.0')
    try:
        page.evaluate("""() => { localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.3');
            localStorage.setItem(window.WhatsNew.MARK_KEY, '1'); }""")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        text = _panel_text(page)
        entry = _entry(page, '1.6')
        heads = page.evaluate(
            "[...document.querySelectorAll('#whatsnew-modal h2')].map(h => h.textContent)")
        assert heads == [entry['title']], heads
        assert 'What’s new in v1.6' in text and 'And in' not in text, text
        for item in entry['items']:
            assert item['h'] in text and item['d'] in text, (item, text)
        n = len(_new_steps(page, '1.5.3', '1.6.0'))
        assert n and page.evaluate("document.getElementById('whatsnew-show-me').title") == \
            'Play the %d new steps of the Advanced Guide' % n
        page.click('#whatsnew-close')
        assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.6.0'
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_timeout(400)
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_help_on_1_6_0_shows_the_1_6_entry_and_its_steps(page):
    """Help > What's New on 1.6.0, nothing owed: the '1.6' entry, and Show
    me runs every step 1.6 brought (no 1.5.x step)."""
    _serve_version(page, '1.6.0')
    try:
        page.evaluate("""() => { localStorage.setItem(window.WhatsNew.LS_KEY, '1.6.0');
            localStorage.setItem(window.WhatsNew.MARK_KEY, '1'); }""")
        page.evaluate("window.WhatsNew.open()")
        _wait_modal(page)
        heads = page.evaluate(
            "[...document.querySelectorAll('#whatsnew-modal h2')].map(h => h.textContent)")
        assert heads == [_entry(page, '1.6')['title']], heads
        text = _panel_text(page)
        assert 'What’s new in v1.6' in text and 'And in' not in text, text
        n = len(_new_steps(page, '1.5.3', '1.6.0'))
        assert n and page.evaluate("document.getElementById('whatsnew-show-me').title") == \
            'Play the %d new steps of the Advanced Guide' % n
        page.click('#whatsnew-close')
    finally:
        page.unroute('**/api/version')


def test_autorun_first_run_never_stacks_on_tour(page):
    """Fresh install: no window, stamp written silently."""
    page.evaluate("localStorage.removeItem(window.WhatsNew.LS_KEY)")
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_function(
        "() => !!localStorage.getItem(window.WhatsNew.LS_KEY)")
    assert not _modal_visible(page)


def test_help_reopens_regardless_of_stamp(page):
    """The stamp silences auto-show only; Help -> What's New always opens."""
    page.evaluate("window.WhatsNew.open()")
    _wait_modal(page)
    assert _modal_visible(page)


def test_modal_fits_theme_and_offers_show_me(page):
    """Open panel sits inside the viewport, opaque, with Show me (the
    running feature version brought guide steps) and Close."""
    box = page.evaluate(
        "() => { const p = document.querySelector('#whatsnew-modal .modal-content');"
        " const r = p.getBoundingClientRect();"
        " const bg = getComputedStyle(p).backgroundColor;"
        " return { top: r.top, left: r.left, right: r.right, bottom: r.bottom,"
        "   vw: window.innerWidth, vh: window.innerHeight, bg }; }")
    assert box['top'] >= 0 and box['left'] >= 0
    assert box['right'] <= box['vw'] and box['bottom'] <= box['vh']
    assert box['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent')
    assert page.evaluate("document.getElementById('whatsnew-show-me').textContent") == 'Show me'
    assert page.evaluate("!!document.getElementById('whatsnew-close')")
    page.click('#whatsnew-close')
    assert not _modal_visible(page)


# ── Show me runs exactly the new steps ───────────────────────────────────

@pytest.fixture
def guide_page(e2e_server, pw_browser):
    """The snapshot builder's viewport, so the steps play on the walls the
    shipped snapshots frame."""
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer"
        " && window.QuickStart && window.WhatsNew)")
    pg.wait_for_timeout(1500)
    yield pg
    pg.evaluate("() => window.QuickStart.end()")
    context.close()


def test_show_me_runs_only_the_new_steps(guide_page):
    """1.5.2 -> 1.5.3, Show me under 1.5.3's own entry: the walkthrough is
    exactly the steps added in 1.5.3 (since '1.5.3'), in guide order, each landing on its own entry snapshot and
    taking; Done puts the person's project back."""
    from test_tour_anchors import _wait_step
    pg = guide_page
    _serve_version(pg, '1.5.3')
    keys = _new_steps(pg, '1.5.2', '1.5.3')
    before = pg.evaluate("() => window.app._canonicalJson(window.app.project)")
    assert keys and all(pg.evaluate("(k) => window.QuickStart.steps()[k].since", k) == '1.5.3'
                        for k in keys), keys
    pg.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
    pg.evaluate("window.WhatsNew.autoRun(true)")
    _wait_modal(pg)
    # The curated entry is up, and Show me is still there under it.
    assert pg.evaluate("document.querySelector('#whatsnew-modal h2').textContent") == \
        pg.evaluate("window.WHATS_NEW_CONTENT['1.5.3'].title")
    pg.evaluate("window.QuickStart.setSpeed(3)")
    pg.click('#whatsnew-show-me')
    assert not _modal_visible(pg)
    assert pg.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.3'
    titles = pg.evaluate("(keys) => keys.map(k => window.QuickStart.steps()[k].title)", keys)
    for i, key in enumerate(keys):
        if i:
            pg.locator('#qs-next').click()
        st = _wait_step(pg, i)
        qs = pg.evaluate("window.QuickStart.state()")
        assert qs['tour'] == 'whatsNew' and qs['steps'] == keys, qs
        assert st['qs']['index'] == i and st['state'] == 'done' and not st['fail'], (key, st)
        assert qs['jumpedVia'] == 'snapshot', (key, qs)
        assert pg.evaluate("document.querySelector('#qs-callout h3').innerHTML") == titles[i]
    assert pg.evaluate("document.getElementById('qs-next').textContent") == 'Done'
    pg.locator('#qs-next').click()
    pg.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running")
    assert pg.evaluate("() => window.app._canonicalJson(window.app.project)") == before
