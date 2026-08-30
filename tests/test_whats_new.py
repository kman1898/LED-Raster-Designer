"""The "What's New" splash: shown once when MAJOR.MINOR changes, never on a
patch, never stacked on the first-run tour, reopenable from Help.

Two halves:

  Static (no browser) - the rot guard and the wiring:
    - VERSION.txt's top version MUST have an entry in whatsnew_content.js.
      This is the test that FAILS when a new MAJOR.MINOR ships without its
      curated highlights - bump VERSION.txt to 0.13/1.0 and this trips until
      someone writes the 0.13/1.0 entry.
    - every entry is 4-8 items, plain text, no emoji;
    - index.html loads both scripts and carries the Help menu item, and
      app-export-io.js dispatches it - the new files cannot silently rot.

  Browser (Playwright, shared e2e server) - the gating matrix and the modal:
    - decide(): patch change silent, minor/major change shows, first run
      stamps silently (the Quick Start tour keeps the first launch), a
      feature version with no entry stamps silently;
    - autoRun(): update shows the splash, dismissing stamps, a second run
      stays quiet; first run never shows;
    - Help -> What's New reopens it regardless of the stamp;
    - fit/theme sanity: panel inside the viewport, opaque, both buttons.

Run the browser half ALONE (the harness pins one port):
    python -m pytest tests/test_whats_new.py -v --browser chromium
"""

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
EXPORT_IO_JS = os.path.join(SRC, 'static', 'js', 'app-export-io.js')
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
    """{major.minor: entry-source} parsed from whatsnew_content.js."""
    src = _read(CONTENT_JS)
    keys = [(m.group(1), m.start())
            for m in re.finditer(r"^\s{4}'(\d+\.\d+)':", src, re.M)]
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
    src = _read(EXPORT_IO_JS)
    assert "case 'whats-new':" in src
    assert 'WhatsNew.open()' in src


def test_logic_uses_its_own_storage_key():
    src = _read(LOGIC_JS)
    assert "lrd_whatsnew_seen" in src
    # It must not touch the tour's key except to read whether the tour runs.
    assert "localStorage.setItem('lrd_quickstart_disabled'" not in src


# ── browser: gating matrix + modal behavior ──────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def _decide(page, current, stamped):
    return page.evaluate(
        "([c, s]) => window.WhatsNew.decide(c, s)", [current, stamped])


def test_decide_patch_change_is_silent(page):
    assert _decide(page, '0.12.2', '0.12') == {'show': False, 'stamp': None}
    assert _decide(page, '0.12.2', '0.12.0') == {'show': False, 'stamp': None}


def test_decide_minor_change_shows(page):
    assert _decide(page, '0.12.0', '0.11') == {'show': True, 'stamp': None}


def test_decide_major_change_shows(page):
    # 1.0 has no entry yet, so use versions the content covers: the rule is
    # the same code path either way, and 0.11 -> 0.12 crosses MAJOR.MINOR.
    d = page.evaluate("window.WhatsNew._majorMinor('1.0.3')")
    assert d == '1.0'
    assert _decide(page, '0.12.1', '0.11.2') == {'show': True, 'stamp': None}


def test_decide_first_run_stamps_silently(page):
    """No stamp = brand-new install: never show (the tour owns first run)."""
    assert _decide(page, '0.12.0', None) == {'show': False, 'stamp': '0.12'}


def test_decide_unknown_version_stamps_silently(page):
    """Feature version changed but no curated entry: quiet, stamped."""
    assert _decide(page, '0.99.0', '0.12') == {'show': False, 'stamp': '0.99'}


def test_decide_garbage_version_is_silent(page):
    assert _decide(page, 'not-a-version', '0.11') == {'show': False, 'stamp': None}


def _modal_visible(page):
    return page.evaluate(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display !== 'none'; }")


def test_autorun_update_shows_then_stamp_silences(page):
    """Stamp behind the running version -> splash; dismiss stamps; quiet after."""
    page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '0.10')")
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_function(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display === 'block'; }")
    # It announces the running feature version (server ships 0.x).
    heading = page.evaluate(
        "document.querySelector('#whatsnew-modal .modal-content').textContent")
    server_mm = page.evaluate(
        "fetch('/api/version').then(r => r.json())"
        ".then(d => window.WhatsNew._majorMinor(d.version))")
    assert ('v' + server_mm) in heading
    # Dismissing stamps the version...
    page.click('#whatsnew-close')
    assert not _modal_visible(page)
    assert page.evaluate(
        "localStorage.getItem(window.WhatsNew.LS_KEY)") == server_mm
    # ...so the next launch is silent.
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_timeout(400)
    assert not _modal_visible(page)


def test_autorun_first_run_never_stacks_on_tour(page):
    """Fresh install: no splash, stamp written silently."""
    page.evaluate("localStorage.removeItem(window.WhatsNew.LS_KEY)")
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_function(
        "() => !!localStorage.getItem(window.WhatsNew.LS_KEY)")
    assert not _modal_visible(page)


def test_help_reopens_regardless_of_stamp(page):
    """The stamp silences auto-show only; Help -> What's New always opens."""
    page.evaluate("window.WhatsNew.open()")
    page.wait_for_function(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display === 'block'; }")
    assert _modal_visible(page)


def test_modal_fits_theme_and_offers_walkthrough(page):
    """Open panel sits inside the viewport, opaque, with both buttons."""
    box = page.evaluate(
        "() => { const p = document.querySelector('#whatsnew-modal .modal-content');"
        " const r = p.getBoundingClientRect();"
        " const bg = getComputedStyle(p).backgroundColor;"
        " return { top: r.top, left: r.left, right: r.right, bottom: r.bottom,"
        "   vw: window.innerWidth, vh: window.innerHeight, bg }; }")
    assert box['top'] >= 0 and box['left'] >= 0
    assert box['right'] <= box['vw'] and box['bottom'] <= box['vh']
    assert box['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent')
    # The tour has a stable entry point, so the walkthrough button is there.
    assert page.evaluate("!!document.getElementById('whatsnew-tour')")
    assert page.evaluate("!!document.getElementById('whatsnew-close')")
    # And the walkthrough button hands off to the what's-new TOUR - the
    # splash's natural continuation - not the Advanced Guide (which stays
    # the fallback for a quickstart without the tour registry).
    page.click('#whatsnew-tour')
    assert not _modal_visible(page)
    # The catch overlay shows a beat before the callout paints, so wait for
    # the title itself, not the catch.
    page.wait_for_function(
        "() => { const h = document.querySelector('#qs-callout h3');"
        " return !!h && h.textContent.length > 0; }")
    first_title = page.evaluate(
        "() => document.querySelector('#qs-callout h3').textContent")
    assert "What's new" in first_title, (
        f'the splash handed off to the wrong tour: {first_title!r}')
    page.evaluate("window.QuickStart.end()")
