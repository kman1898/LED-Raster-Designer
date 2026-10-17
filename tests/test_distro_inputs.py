"""The distro's INPUT list (1.5): what can feed a distro, filtered by its
system.

Cams 100 to 800 A feed the US systems (a cam connector does not set the
rating - the distro's main or feeder does, so the Rating box stays
typeable); L21-30 feeds 120/208 only; CEE red (5-pin, 3φ with a neutral)
feeds 230/400, CEE blue (1φ) feeds 230; Powerlock feeds both EU systems.
The gear's Input select lists only what fits the distro's system, except an
input the distro already has: that one stays listed and selected even when
it no longer fits, and changing the system never changes the input or the
rating behind the reader's back.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_distro_inputs.py -q --browser chromium
"""

import json

import pytest

import app as app_module

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

DISTRO = {'id': 'd1', 'name': 'IN', 'system': '120/208', 'voltage': 208, 'phase': 3,
          'ratingA': 400}

CAMS = ['Cam 100 A', 'Cam 200 A', 'Cam 400 A', 'Cam 600 A', 'Cam 800 A']
POWERLOCKS = ['Powerlock 400 A', 'Powerlock 630 A']
EXPECTED = {
    '120/208': CAMS + ['L21-30'],
    '120/240': CAMS,
    '120': CAMS,
    '230/400': ['CEE 16 A red', 'CEE 32 A red', 'CEE 63 A red', 'CEE 125 A red'] + POWERLOCKS,
    '230': ['CEE 16 A blue', 'CEE 32 A blue', 'CEE 63 A blue', 'CEE 125 A blue'] + POWERLOCKS,
}

SELECT = '#hw-gear-popover [data-lrd-field="distro-input-d1"]'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    app_module.current_project['distros'] = [json.loads(json.dumps(DISTRO))]
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& (window.app.project.distros || []).some(d => d.id === 'd1')",
                         timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


def _set(pg, patch):
    """Patch d1 the way the app does and re-open its gear."""
    pg.evaluate("""(patch) => {
        const app = window.app;
        app._hwPopoverClose();
        const d = app.getDistros().find(x => x.id === 'd1');
        Object.keys(patch).forEach(k => {
            if (patch[k] === null) delete d[k]; else d[k] = patch[k];
        });
        if (patch.system) app.updateDistro('d1', { system: patch.system });
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
    }""", patch)
    pg.wait_for_selector(SELECT)


def _shown(pg):
    return pg.eval_on_selector(SELECT, """s => ({
        options: [...s.options].map(o => o.textContent),
        value: s.value,
    })""")


@pytest.mark.parametrize('system', list(EXPECTED))
def test_the_input_list_shows_only_what_fits_the_system(page, system):
    pg, errors = page
    _set(pg, {'system': system, 'input': None})
    shown = _shown(pg)
    assert shown == {'options': ['—'] + EXPECTED[system], 'value': ''}, shown
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


def test_picking_cam_100_sets_the_rating_to_100_and_it_stays_typeable(page):
    pg, errors = page
    _set(pg, {'system': '120/208', 'input': None, 'ratingA': 400})
    pg.select_option(SELECT, 'cam100')
    got = pg.evaluate("() => { const d = window.app.getDistros().find(x => x.id === 'd1');"
                      " return {input: d.input, ratingA: d.ratingA}; }")
    assert got == {'input': 'cam100', 'ratingA': 100}, got
    rating = '#hw-gear-popover [data-lrd-field="distro-rating-d1"]'
    pg.wait_for_selector(rating)
    assert pg.eval_on_selector(rating, 'el => el.value') == '100'
    assert pg.eval_on_selector(rating, 'el => !el.disabled && !el.readOnly')
    pg.fill(rating, '150')
    pg.press(rating, 'Enter')
    pg.locator(rating).blur()
    pg.wait_for_function("() => window.app.getDistros().find(x => x.id === 'd1').ratingA === 150")
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


def test_an_input_that_no_longer_fits_stays_shown_and_nothing_changes_by_itself(page):
    pg, errors = page
    # an old record: a CEE red input on a US system
    _set(pg, {'system': '120/208', 'input': 'cee63', 'ratingA': 63})
    shown = _shown(pg)
    assert shown['value'] == 'cee63', shown
    assert shown['options'] == ['—'] + CAMS + ['L21-30', 'CEE 63 A red'], shown
    # the system changes after the pick: the input and the rating stay
    _set(pg, {'system': '230', 'input': 'cam400', 'ratingA': 400})
    _set(pg, {'system': '120'})
    got = pg.evaluate("() => { const d = window.app.getDistros().find(x => x.id === 'd1');"
                      " return {system: d.system, input: d.input, ratingA: d.ratingA}; }")
    assert got == {'system': '120', 'input': 'cam400', 'ratingA': 400}, got
    shown = _shown(pg)
    assert shown == {'options': ['—'] + CAMS, 'value': 'cam400'}, shown
    _set(pg, {'system': '230'})
    shown = _shown(pg)
    assert shown['value'] == 'cam400', shown
    assert 'Cam 400 A' in shown['options'] and 'Cam 200 A' not in shown['options'], shown
    pg.evaluate("() => window.app._hwPopoverClose()")
    assert not errors, errors


# ── the server's preset check knows the new ids ───────────────────────────

BODY = {'system': '230/400', 'input': 'cee63', 'ratingA': 63, 'breakers100': False,
        'phasing': None, 'directPhasing': None,
        'rows': [{'id': 'r1', 'connector': 'soca', 'count': 2, 'coupling': 'ln',
                  'breakerA': 16, 'pairedWith': None}]}

NEW_IDS = [('120/208', 'cam100'), ('120/240', 'cam600'), ('120', 'cam800'),
           ('230/400', 'cee16r'), ('230/400', 'cee32r'), ('230/400', 'cee125r'),
           ('230', 'cee16b'), ('230', 'cee32b'), ('230', 'cee63b'), ('230', 'cee125b'),
           ('230/400', 'powerlock630')]


@pytest.mark.parametrize('system,input_id', NEW_IDS)
def test_a_preset_with_a_new_input_saves(client, system, input_id):
    body = dict(BODY, system=system, input=input_id,
                rows=[dict(BODY['rows'][0], coupling='ln')])
    r = client.put('/api/distro-presets', json={'name': f'With {input_id}', 'distro': body})
    assert r.status_code == 200, r.get_json()
    saved = [p for p in r.get_json()['presets'] if p['name'] == f'With {input_id}']
    assert saved and saved[0]['distro']['input'] == input_id
    client.delete('/api/distro-presets', json={'name': f'With {input_id}'})


def test_an_unknown_input_is_still_refused(client):
    r = client.put('/api/distro-presets',
                   json={'name': 'Nope', 'distro': dict(BODY, input='cam1000')})
    assert r.status_code == 400
