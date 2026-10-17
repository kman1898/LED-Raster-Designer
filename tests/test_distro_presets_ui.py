"""Saved distro presets in the distro's gear (1.5 fixes): a saved preset
can be deleted from the gear - the built-in ones cannot - and only after
saying yes; and a save the server refuses says why in plain words, even
when the reply is an error page rather than JSON.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_presets_ui.py -q --browser chromium
"""

import json
import os

import pytest

import app as app_module
import routes_distro_presets as rdp

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

DISTRO = {'id': 'd1', 'name': 'SL', 'system': '230/400', 'input': 'cee63', 'ratingA': 63,
          'outputRows': [{'id': 'r1', 'connector': 'schuko', 'count': 4, 'coupling': 'ln',
                          'breakerA': 16, 'pairedWith': None}]}
SAVED = {'name': 'Our rack',
         'distro': {'system': '230/400', 'input': 'cee63', 'ratingA': 63,
                    'rows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'ln',
                              'breakerA': 16, 'pairedWith': None}]}}


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def presets_file(tmp_path_factory):
    before = rdp.DISTRO_PRESETS_FILE
    rdp.DISTRO_PRESETS_FILE = str(tmp_path_factory.mktemp('ui_presets') / 'distro_presets.json')
    yield rdp.DISTRO_PRESETS_FILE
    rdp.DISTRO_PRESETS_FILE = before


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser, presets_file):
    app_module.current_project['distros'] = [json.loads(json.dumps(DISTRO))]
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& (window.app.project.distros || []).some(d => d.id === 'd1')",
                         timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


def _write(path, presets):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'presets': presets}, f)


def _stored_names(path):
    with open(path, encoding='utf-8') as f:
        return [p['name'] for p in json.load(f)['presets']]


def _open_gear(pg):
    pg.evaluate("""async () => {
        const app = window.app;
        app._hwPopoverClose && app._hwPopoverClose();
        await app.loadCustomDistroPresets(true);
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
    }""")
    pg.wait_for_selector('#hw-gear-popover [data-lrd-field="distro-preset-d1"]')


def _status_is(pg, text):
    pg.wait_for_function(
        "(t) => (document.getElementById('status-message') || {}).textContent === t", arg=text)


DELETE = '#hw-gear-popover [data-lrd-field="distro-preset-delete-d1"]'


def test_a_saved_preset_is_deleted_from_the_gear_after_saying_yes(page, presets_file):
    pg, errors = page
    _write(presets_file, [SAVED])
    _open_gear(pg)
    shown = pg.evaluate(f"""() => {{
        const del = document.querySelector('{DELETE}');
        return {{ options: [...del.options].map(o => o.textContent),
                  visible: del.parentElement.style.display !== 'none' }};
    }}""")
    # saved presets only - the built-in ones cannot be deleted
    assert shown == {'options': ['Delete a saved preset…', 'Our rack'], 'visible': True}, shown

    # No: nothing changes
    asked = []
    pg.once('dialog', lambda d: (asked.append(d.message), d.dismiss()))
    pg.select_option(DELETE, 'Our rack')
    assert asked and 'Our rack' in asked[0], asked
    assert _stored_names(presets_file) == ['Our rack']
    assert pg.eval_on_selector(DELETE, 'el => el.value') == ''

    # Yes: it is gone from the file and from both lists
    pg.once('dialog', lambda d: d.accept())
    pg.select_option(DELETE, 'Our rack')
    _status_is(pg, 'Deleted preset "Our rack".')
    assert _stored_names(presets_file) == []
    after = pg.evaluate(f"""() => {{
        const pop = document.getElementById('hw-gear-popover');
        const del = document.querySelector('{DELETE}');
        return {{ groups: [...pop.querySelectorAll('[data-lrd-field="distro-preset-d1"] optgroup')]
                      .map(g => g.label),
                  visible: del.parentElement.style.display !== 'none' }};
    }}""")
    assert after == {'groups': ['Presets'], 'visible': False}, after
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


def test_with_no_saved_presets_there_is_nothing_to_delete(page, presets_file):
    pg, _ = page
    _write(presets_file, [])
    _open_gear(pg)
    assert pg.eval_on_selector(DELETE, 'el => el.parentElement.style.display') == 'none'
    pg.evaluate("() => window.app._hwPopoverClose()")


def test_a_refused_save_says_why_in_plain_words(page, presets_file):
    pg, errors = page
    _write(presets_file, [])
    _open_gear(pg)

    def fail_put(route):
        if route.request.method == 'PUT':
            route.fulfill(status=500, content_type='text/html',
                          body='<!doctype html><title>500</title><h1>Internal Server Error</h1>')
        else:
            route.continue_()

    pg.route('**/api/distro-presets', fail_put)
    try:
        pg.once('dialog', lambda d: d.accept('Rack X'))
        pg.click('#hw-gear-popover [data-lrd-field="distro-preset-save-d1"]')
        _status_is(pg, 'Preset not saved - the server said 500.')
    finally:
        pg.unroute('**/api/distro-presets', fail_put)
    assert not os.path.exists(presets_file) or _stored_names(presets_file) == []

    # the server's own reason, when it gives one
    said = pg.evaluate("""() => window.app.saveDistroPreset('d1', 'x'.repeat(80))
                                   .then(() => 'saved', e => e.message)""")
    assert said == 'Preset not saved - a preset needs a name of 1 to 60 characters.', said
    said = pg.evaluate("""() => window.app.deleteDistroPreset('Nobody')
                                   .then(() => 'deleted', e => e.message)""")
    assert said == 'Preset not deleted - no preset by that name.', said
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors
