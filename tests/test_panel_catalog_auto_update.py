"""The panel catalog updates itself on launch.

New cabinets reach main as panel_catalog.json alone, never ahead in a build
(CI fails dev/draft when its copy is not main's), so the copy on main is the
newest any version can have. A few seconds after the app opens it asks for
that copy, the way it asks whether a newer app is out; when it differs from
what the user has, it is applied straight away and a toast says so. Before,
it only lit an "Update available" badge and waited for a click. The Refresh
button still pulls on demand.

GitHub is never reached here: the browser's request to the app's own proxy
(/api/panel-catalog/refresh) is answered by the test.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402

CATALOG = os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'data', 'panel_catalog.json')

STATE_JS = """() => ({
    sha: localStorage.getItem('panelCatalog.cachedSha'),
    cached: !!localStorage.getItem('panelCatalog.cached'),
    hasNew: (window.app._panelCatalogFlat || []).some(p => p.name === 'TEST-NEW-CABINET'),
    toasts: Array.from(document.querySelectorAll('#app-toast-host > div')).map(t => t.textContent),
})"""


def _open(e2e_server, pw_browser, answer):
    """A fresh profile (no cached catalog) whose refresh request gets ANSWER:
    a dict to send as JSON, or None for a failed request."""
    ctx = pw_browser.new_context(viewport={'width': 1500, 'height': 900})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))

    def reply(route):
        if answer is None:
            route.fulfill(status=502, content_type='application/json', body='{"error": "network: offline"}')
        else:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(answer))
    page.route('**/api/panel-catalog/refresh', reply)
    page.goto(e2e_server, wait_until='domcontentloaded')
    return ctx, page, errors


def _bundled_sha(page):
    return page.evaluate("() => fetch('/api/panel-catalog/info').then(r => r.json()).then(d => d.bundledSha)")


def _upstream(sha):
    with open(CATALOG, encoding='utf-8') as fh:
        catalog = json.load(fh)
    catalog['Absen'] = catalog['Absen'] + [dict(catalog['Absen'][0], name='TEST-NEW-CABINET')]
    return {'catalog': catalog, 'sha': sha, 'panelCount': sum(len(v) for v in catalog.values()),
            'mfrCount': len(catalog), 'fetchedAt': '2026-10-04T12:00:00Z'}


def test_line_endings_do_not_make_a_catalog_different():
    """A Windows checkout writes the catalog with CRLF. Hashing its bytes
    made every Windows build's copy differ from GitHub's identical one, so
    those builds always saw an update. The identity is the content."""
    import app  # noqa: F401  (registers the blueprint routes_panel_catalog imports from)
    import routes_panel_catalog as rpc
    with open(CATALOG, 'rb') as fh:
        lf = fh.read().replace(b'\r\n', b'\n')
    crlf = lf.replace(b'\n', b'\r\n')
    assert lf != crlf
    assert rpc._catalog_sha(lf) == rpc._catalog_sha(crlf)
    changed = json.loads(lf)
    changed['Absen'][0]['weight_kg'] = changed['Absen'][0]['weight_kg'] + 1
    assert rpc._catalog_sha(json.dumps(changed).encode('utf-8')) != rpc._catalog_sha(lf)
    assert rpc._bundled_panel_catalog_sha() == rpc._catalog_sha(lf)


def test_a_newer_catalog_on_main_is_applied_on_launch_with_a_toast(e2e_server, pw_browser):
    upstream = _upstream('f' * 64)
    ctx, page, errors = _open(e2e_server, pw_browser, upstream)
    try:
        state = settled(page, lambda: page.evaluate(STATE_JS), lambda s: s['hasNew'], timeout_ms=10000)
        assert state['hasNew'], f'the newer catalog was not applied: {state}'
        assert state['sha'] == 'f' * 64 and state['cached'], state
        count = f"{upstream['panelCount']:,}"
        assert f'Panel catalog updated, {count} panels' in state['toasts'], state
        # It sticks: the next launch starts from the applied copy.
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(500)
        assert page.evaluate("() => localStorage.getItem('panelCatalog.cachedSha')") == 'f' * 64
        assert errors == [], errors
    finally:
        ctx.close()


def test_the_same_catalog_as_bundled_changes_nothing(e2e_server, pw_browser):
    ctx, page, errors = _open(e2e_server, pw_browser, None)
    sha = _bundled_sha(page)
    ctx.close()
    ctx, page, errors = _open(e2e_server, pw_browser, dict(_upstream(sha), catalog=None))
    try:
        page.wait_for_timeout(3500)
        state = page.evaluate(STATE_JS)
        assert state['sha'] is None and not state['cached'], f'an unchanged catalog was re-applied: {state}'
        assert not any('catalog' in t.lower() for t in state['toasts']), state
        assert errors == [], errors
    finally:
        ctx.close()


def test_offline_keeps_the_current_catalog_quietly(e2e_server, pw_browser):
    ctx, page, errors = _open(e2e_server, pw_browser, None)
    try:
        page.wait_for_timeout(3500)
        state = page.evaluate(STATE_JS)
        assert state['sha'] is None and not state['cached'], state
        assert state['toasts'] == [], f'an offline launch should say nothing: {state}'
        assert errors == [], errors
    finally:
        ctx.close()
