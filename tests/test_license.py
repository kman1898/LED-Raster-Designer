"""The app's LICENSE and THIRD-PARTY-NOTICES, and Help > License that shows
them offline.

Static (no browser):
  - LICENSE sits at the repo root: the LED Raster Designer License, naming
    the licensor and the contact, with its twelve sections in order and no
    Creative Commons text;
  - THIRD-PARTY-NOTICES sits at the repo root, lists every top-level
    requirement, and scripts/build_third_party_notices.py --check passes
    (no package in the dependency closure is missing from it);
  - GET /api/license and GET /api/third-party-notices serve exactly those
    files as UTF-8 plain text, 404 when a file is missing;
  - the PyInstaller spec bundles both (the built app serves the same
    routes from sys._MEIPASS), and the README section names the license,
    both files and the contact;
  - index.html carries the Help item, the modal and its two tabs,
    app-menubar.js dispatches it.

Browser (Playwright, shared e2e server):
  - Help > License opens on the License tab with the license title; the
    Third-party notices tab shows the notices; Close, Escape and the
    backdrop close it; a reopen starts on License and refetches nothing;
    the About line reads as written; no page errors.

Run: python -m pytest tests/test_license.py -q --browser chromium
"""
import os
import re
import subprocess
import sys

import pytest

from conftest import settled

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LICENSE = os.path.join(ROOT, 'LICENSE')
NOTICES = os.path.join(ROOT, 'THIRD-PARTY-NOTICES')
NOTICES_SCRIPT = os.path.join(ROOT, 'scripts', 'build_third_party_notices.py')
REQUIREMENTS = os.path.join(ROOT, 'src', 'requirements.txt')
README = os.path.join(ROOT, 'README.md')
SPEC = os.path.join(ROOT, 'src', 'led_raster_designer.spec')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
MENUBAR_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-menubar.js')

TITLE = 'LED RASTER DESIGNER LICENSE'
NOTICES_TITLE = 'THIRD-PARTY NOTICES'
CONTACT = 'kman1898@gmail.com'
ABOUT_LINE = ('Free to use, including on paid shows. '
              'LED Raster Designer License — Help → License.')
SECTIONS = [
    'DEFINITIONS', 'FREE USE', 'YOUR OUTPUT', 'RESTRICTIONS',
    'SHARING AND DERIVATIVES', 'COMMERCIAL LICENSES', 'CONTRIBUTIONS',
    'THIRD-PARTY COMPONENTS', 'NO WARRANTY', 'LIMITATION OF LIABILITY',
    'TERMINATION', 'GENERAL',
]


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _canon(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def _requirement_names():
    names = []
    for line in _read(REQUIREMENTS).splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            names.append(re.match(r'[A-Za-z0-9][A-Za-z0-9._-]*', line).group(0))
    return names


# ── LICENSE ──────────────────────────────────────────────────────────────

def test_license_file_at_repo_root():
    assert os.path.isfile(LICENSE), 'LICENSE missing from the repo root'


def test_license_names_the_licensor_and_contact():
    text = _read(LICENSE)
    assert text.startswith(TITLE)
    assert 'kman1898' in text
    assert CONTACT in text


def test_license_has_its_twelve_sections_in_order():
    lines = [ln.strip() for ln in _read(LICENSE).splitlines()]
    at = []
    for n, heading in enumerate(SECTIONS, start=1):
        line = f'{n}. {heading}'
        assert line in lines, f'LICENSE section heading missing: {line!r}'
        at.append(lines.index(line))
    assert at == sorted(at), f'LICENSE sections out of order: {at}'


def test_license_carries_no_creative_commons_text():
    text = _read(LICENSE)
    assert 'Creative Commons' not in text
    assert 'creativecommons' not in text.lower()
    assert 'CC BY' not in text


# ── THIRD-PARTY-NOTICES ──────────────────────────────────────────────────

def test_notices_file_at_repo_root():
    assert os.path.isfile(NOTICES), 'THIRD-PARTY-NOTICES missing from the repo root'
    assert _read(NOTICES).startswith(NOTICES_TITLE)


def test_notices_check_passes():
    """--check exits non-zero naming any package in the requirements'
    dependency closure (Windows and macOS) the committed file does not
    list. Regenerate with: python scripts/build_third_party_notices.py"""
    result = subprocess.run(
        [sys.executable, NOTICES_SCRIPT, '--check'],
        capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_notices_list_every_top_level_requirement():
    listed = {_canon(m) for m in
              re.findall(r'^Package: (.+?)\s*$', _read(NOTICES), re.M)}
    for name in _requirement_names():
        assert _canon(name) in listed, f'THIRD-PARTY-NOTICES does not list {name}'


def test_notices_name_the_runtime_and_bootloader():
    text = _read(NOTICES)
    assert 'Python runtime' in text and 'PSF License Agreement' in text
    assert 'PyInstaller bootloader' in text and 'bootloader exception' in text
    assert 'LED Raster Designer License' in text


# ── the routes ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('route, path', [
    ('/api/license', LICENSE),
    ('/api/third-party-notices', NOTICES),
])
def test_route_serves_the_file(client, route, path):
    resp = client.get(route)
    assert resp.status_code == 200
    assert resp.mimetype == 'text/plain'
    assert resp.mimetype_params.get('charset', '').lower() == 'utf-8'
    with open(path, 'rb') as f:
        assert resp.data == f.read()


@pytest.mark.parametrize('route, attr, message', [
    ('/api/license', '_license_path',
     b'The license file is missing from this build.'),
    ('/api/third-party-notices', '_notices_path',
     b'The third-party notices are missing from this build.'),
])
def test_route_missing_file_is_404(client, monkeypatch, route, attr, message):
    import routes_version
    monkeypatch.setattr(routes_version, attr,
                        lambda: os.path.join(ROOT, 'no-such-file'))
    resp = client.get(route)
    assert resp.status_code == 404
    assert resp.mimetype == 'text/plain'
    assert resp.data == message


def test_frozen_build_reads_both_files_from_the_bundle(monkeypatch, tmp_path):
    """In the PyInstaller build the spec puts both files at the bundle root."""
    import routes_version
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert routes_version._license_path() == os.path.join(str(tmp_path), 'LICENSE')
    assert routes_version._notices_path() == os.path.join(
        str(tmp_path), 'THIRD-PARTY-NOTICES')


# ── the build, the README, the wiring ────────────────────────────────────

@pytest.mark.parametrize('name', ['LICENSE', 'THIRD-PARTY-NOTICES'])
def test_spec_bundles_file_at_the_bundle_root(name):
    spec = _read(SPEC)
    datas = spec[spec.index('datas=['):spec.index('hiddenimports=')]
    # The spec is built from src/, so the repo-root file is one level up,
    # and it lands at the bundle root where _bundled_path() looks.
    assert re.search(
        r"\(\s*os\.path\.join\(\s*'\.\.'\s*,\s*'" + re.escape(name)
        + r"'\s*\)\s*,\s*'\.'\s*\)", datas), \
        f'led_raster_designer.spec does not bundle ../{name} into "."'


def _readme_section():
    readme = _read(README)
    assert '## License' in readme
    section = readme[readme.index('## License'):]
    nxt = section.find('\n## ', 1)
    return section if nxt < 0 else section[:nxt]


def test_readme_section_names_license_files_and_contact():
    section = _readme_section()
    assert 'LED Raster Designer License' in section
    assert '(LICENSE)' in section, 'README License section must link LICENSE'
    assert '(THIRD-PARTY-NOTICES)' in section, \
        'README License section must link THIRD-PARTY-NOTICES'
    assert CONTACT in section
    assert 'Creative Commons' not in section and 'CC BY' not in section


def test_help_menu_and_modal_wired():
    html = _read(INDEX_HTML)
    help_menu = html[html.index('id="menu-help"'):]
    help_menu = help_menu[:re.search(r'</div>\r?\n\r?\n', help_menu).start()]
    lic = help_menu.index('data-action="license"')
    about = help_menu.index('data-action="about"')
    assert lic < about, 'License must sit directly above About'
    assert 'menu-divider' not in help_menu[lic:about]
    assert 'id="license-modal"' in html
    assert 'id="license-content"' in html and 'id="license-close"' in html
    modal = html[html.index('id="license-modal"'):]
    modal = modal[:modal.index('id="license-close"')]
    # Two tabs reusing the Preferences tab strip (no data-mode: the
    # workspace's view-tab wiring binds only [data-mode] tabs).
    assert re.search(r'class="pm-tabstrip"', modal)
    assert re.search(r'class="view-tab active" data-key="license"', modal)
    assert re.search(r'class="view-tab" data-key="notices"', modal)
    assert 'data-mode' not in modal
    assert ABOUT_LINE in html
    js = _read(MENUBAR_JS)
    assert re.search(r"case 'license':\s*this\.openLicenseModal\(\);", js)
    assert "'/api/license'" in js and "'/api/third-party-notices'" in js


# ── browser ──────────────────────────────────────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    settled(pg, lambda: pg.evaluate("!!(window.app && window.app.project)"),
            bool, 10000)
    pg.page_errors = errors
    yield pg
    context.close()


def _visible(page):
    return page.evaluate(
        "() => { const m = document.getElementById('license-modal');"
        " return !!m && m.style.display === 'block'; }")


def _content(page):
    return page.evaluate("document.getElementById('license-content').textContent")


def _active_tab(page):
    return page.evaluate(
        "() => { const t = document.querySelector("
        "'#license-modal .pm-tabstrip .view-tab.active');"
        " return t ? t.dataset.key : null; }")


def _open_from_help(page):
    page.click('.menu-item[data-menu="help"]')
    page.click('#menu-help [data-action="license"]')
    assert settled(page, lambda: _visible(page), bool, 3000), \
        'Help > License did not open the modal'
    assert _active_tab(page) == 'license', 'Help > License must open on License'
    return settled(page, lambda: _content(page),
                   lambda t: t.startswith(TITLE), 5000)


def test_help_license_opens_on_the_license_tab(page):
    text = _open_from_help(page)
    assert text.startswith(TITLE), text[:80]
    assert '12. GENERAL' in text
    assert page.evaluate(
        "document.querySelector('#license-modal h2').textContent") == 'License'
    tabs = page.evaluate(
        "[...document.querySelectorAll('#license-modal .pm-tabstrip .view-tab')]"
        ".map(t => t.textContent.trim())")
    assert tabs == ['License', 'Third-party notices']
    # Monospace, pre-wrapped, scrolls inside the panel, fits the window.
    style = page.evaluate(
        "() => { const el = document.getElementById('license-content');"
        " const cs = getComputedStyle(el); const p = el.closest('.modal-content')"
        ".getBoundingClientRect();"
        " return { ws: cs.whiteSpace, ff: cs.fontFamily, of: cs.overflowY,"
        "   bottom: p.bottom, vh: window.innerHeight,"
        "   scrolls: el.scrollHeight > el.clientHeight }; }")
    assert style['ws'] == 'pre-wrap'
    assert re.search(r'mono|consolas|menlo', style['ff'], re.I), style['ff']
    assert style['of'] == 'auto' and style['scrolls']
    assert style['bottom'] <= style['vh'], 'license panel runs off the window'
    page.click('#license-close')
    assert settled(page, lambda: _visible(page), lambda v: not v, 2000) is False


def test_notices_tab_shows_the_notices(page):
    _open_from_help(page)
    page.click('#license-modal .view-tab[data-key="notices"]')
    assert settled(page, lambda: _active_tab(page),
                   lambda k: k == 'notices', 2000) == 'notices'
    text = settled(page, lambda: _content(page),
                   lambda t: t.startswith(NOTICES_TITLE), 5000)
    assert text.startswith(NOTICES_TITLE), text[:80]
    assert 'Package: Flask' in text
    # Back to License: the cached text, at once.
    page.click('#license-modal .view-tab[data-key="license"]')
    assert settled(page, lambda: _content(page),
                   lambda t: t.startswith(TITLE), 2000).startswith(TITLE)
    page.keyboard.press('Escape')
    assert settled(page, lambda: _visible(page), lambda v: not v, 2000) is False


def test_reopen_starts_on_license_and_refetches_nothing(page):
    # Leave the dialog on the notices tab...
    _open_from_help(page)
    page.click('#license-modal .view-tab[data-key="notices"]')
    settled(page, lambda: _content(page),
            lambda t: t.startswith(NOTICES_TITLE), 5000)
    page.keyboard.press('Escape')
    assert settled(page, lambda: _visible(page), lambda v: not v, 2000) is False
    # ...a reopen starts on License, and both tabs read their cached text.
    requests = []
    page.on('request', lambda r: requests.append(r.url)
            if '/api/license' in r.url or '/api/third-party-notices' in r.url
            else None)
    _open_from_help(page)
    page.click('#license-modal .view-tab[data-key="notices"]')
    assert _content(page).startswith(NOTICES_TITLE)
    assert requests == [], f'text fetched again: {requests}'
    # Backdrop click closes too, like About.
    page.mouse.click(5, 5)
    assert settled(page, lambda: _visible(page), lambda v: not v, 2000) is False


def test_about_line(page):
    page.evaluate("window.app.openAboutModal()")
    line = page.evaluate(
        "document.getElementById('about-license').textContent")
    assert line == ABOUT_LINE
    page.click('#about-close')


def test_no_page_errors(page):
    assert page.page_errors == [], page.page_errors
