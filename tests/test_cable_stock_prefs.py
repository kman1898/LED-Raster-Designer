"""Preferences > Cable stock: the open show's cable lengths, and the named
presets kept for every show (app-cable-stock.js, routes_cable_stock.py).

Owner rulings, 2026-10-20: "in preferences we need to be able to set cable
lengths available on a show and load presets". The lists are the SHOW's -
Save gives them to it as one undo step, Cancel forgets them - with one
shared list or a list per kind, in feet and meters. Presets (one per shop or
vendor) are saved, loaded into the fields and deleted from the same tab; a
new show starts with the preset named under "New shows start with".

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_cable_stock_prefs.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_cables import SEED_JS  # noqa: E402
from app_dialogs import answer_app_dialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and the preferences) as found."""


@pytest.fixture(scope="module", autouse=True)
def _presets_file():
    """The module's presets start empty and are put back after."""
    import routes_cable_stock
    path = routes_cable_stock.CABLE_STOCK_PRESETS_FILE
    before = open(path, encoding='utf-8').read() if os.path.exists(path) else None
    if os.path.exists(path):
        os.remove(path)
    yield
    if before is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(before)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(500)
    pg.evaluate("""async () => {
        const app = window.app;
        const wall = app.project.layers[0];
        app.setSocaLength(wall, 1, '125', false);
        app.updateLayers([wall]);
        app.project.cableUnit = 'ft';
        delete app.project.cableStock;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cableUnit: 'ft', cableStock: null})});
        app.resetHistory('Prefs Stock Seed');
    }""")
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


def _open(pg):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="stock"]').click()
    pg.wait_for_timeout(300)


def _shown(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#preferences-modal [data-cable-stock-list]')]
        .filter(r => getComputedStyle(r).display !== 'none').map(r => r.dataset.cableStockList)""")


def _presets(pg):
    return pg.evaluate("async () => (await (await fetch('/api/cable-stock-presets')).json()).presets")


def test_the_tab_shows_the_show_s_lists_and_save_gives_them_to_the_show(page):
    """A show with no stock opens on blank lists and the one shared row.
    Typed lists and Save: the show holds them (one 'Set Cable Stock' step,
    served), the multi's 125 is written 100'+25'. Cancel after an edit
    changes nothing; a Save that touched no list records nothing."""
    pg, errors = page
    _open(pg)
    assert _shown(pg) == ['all']
    assert pg.input_value('#pref-cable-stock-all-ft') == ''
    n0 = pg.evaluate("() => window.app.history.length")
    pg.fill('#pref-cable-stock-all-ft', '100, 25 50')
    pg.fill('#pref-cable-stock-all-m', '10; 30')
    pg.click('#preferences-save')
    pg.wait_for_timeout(600)
    st = pg.evaluate("""async () => {
        const app = window.app;
        await app._pullSheetStateSettled();
        return { stock: app.cableStock(), steps: app.history.length,
                 action: app.history[app.historyIndex].action,
                 served: (await (await fetch('/api/project')).json()).cableStock,
                 text: app.pullLengthText(125, 'multi') };
    }""")
    assert st['stock']['ft']['all'] == [25, 50, 100] and st['stock']['m']['all'] == [10, 30], st
    assert st['steps'] == n0 + 1 and st['action'] == 'Set Cable Stock', st
    assert st['served']['ft']['all'] == [25, 50, 100], st
    assert st['text'] == "100'+25'", st
    # reopened, the fields show the show's lists
    _open(pg)
    assert pg.input_value('#pref-cable-stock-all-ft') == '25, 50, 100'
    pg.fill('#pref-cable-stock-all-ft', '5')
    pg.click('#preferences-cancel')
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.app.cableStock().ft.all") == [25, 50, 100]
    # a Save for another tab leaves the stock (and history) alone
    n1 = pg.evaluate("() => window.app.history.length")
    _open(pg)
    pg.click('#preferences-save')
    pg.wait_for_timeout(400)
    assert pg.evaluate("() => window.app.history.length") == n1
    assert errors == [], errors


def test_a_list_per_kind(page):
    """The toggle swaps the shared row for one row per kind - multis,
    data, power, and since 2026-10-21 L21-30 and Harting home runs,
    direct-output cables and feeders; the kinds' lists are the show's after
    Save and each kind reads its own."""
    pg, errors = page
    _open(pg)
    pg.check('#pref-cable-stock-per-kind')
    assert _shown(pg) == ['multi', 'data', 'circuit', 'l2130', 'harting', 'direct', 'feeder']
    pg.fill('#pref-cable-stock-multi-ft', '50, 100')
    pg.fill('#pref-cable-stock-data-ft', '25, 50')
    pg.fill('#pref-cable-stock-circuit-ft', '')
    pg.fill('#pref-cable-stock-l2130-ft', '30, 60')
    pg.fill('#pref-cable-stock-harting-ft', '')
    pg.fill('#pref-cable-stock-direct-ft', '10, 25')
    pg.fill('#pref-cable-stock-feeder-ft', '50, 100')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    got = pg.evaluate("""() => { const a = window.app;
        return [a.cableStock().perKind, a.cableStockText(125, 'multi'), a.cableStockText(125, 'data'),
                a.cableStockText(125, 'circuit'), a.cableStockText(125, 'l2130'),
                a.cableStockText(125, 'harting'), a.cableStockText(35, 'direct'),
                a.cableStockText(125, 'feeder')]; }""")
    assert got == [True, "100'+50'", "50'+50'+25'", "125'", "60'+60'+30'",
                   "125'", "25'+10'", "100'+50'"], got
    _open(pg)
    assert pg.is_checked('#pref-cable-stock-per-kind') and _shown(pg) == ['multi', 'data', 'circuit', 'l2130', 'harting', 'direct', 'feeder']
    pg.uncheck('#pref-cable-stock-per-kind')
    assert _shown(pg) == ['all']
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.cableStockText(125, 'data')") == "100'+25'"
    assert errors == [], errors


def test_presets_save_load_and_delete(page):
    """Save as preset asks a name and saves the fields' lists for every show;
    Load fills the fields from the picked preset (Save then gives them to
    the show); Delete asks first and removes it."""
    pg, errors = page
    _open(pg)
    pg.fill('#pref-cable-stock-all-ft', '20, 40, 80')
    pg.fill('#pref-cable-stock-all-m', '6, 12')
    pg.click('#pref-cable-stock-save-preset')
    answer_app_dialog(pg, text='Shop B')
    pg.wait_for_timeout(500)
    presets = _presets(pg)
    assert [p['name'] for p in presets] == ['Shop B'], presets
    assert presets[0]['stock']['ft']['all'] == [20, 40, 80] and presets[0]['stock']['m']['all'] == [6, 12]
    assert pg.input_value('#pref-cable-stock-preset') == 'Shop B'
    assert 'Saved preset "Shop B"' in pg.text_content('#pref-cable-stock-status')
    # saving a preset does not touch the show until Save
    assert pg.evaluate("() => window.app.cableStock().ft.all") == [25, 50, 100]
    pg.click('#preferences-cancel')
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.app.cableStock().ft.all") == [25, 50, 100]

    # Load into the fields, then Save gives it to the show
    _open(pg)
    assert pg.input_value('#pref-cable-stock-all-ft') == '25, 50, 100'
    pg.wait_for_function("() => document.querySelectorAll('#pref-cable-stock-preset option').length > 1")
    pg.select_option('#pref-cable-stock-preset', 'Shop B')
    pg.click('#pref-cable-stock-load')
    assert pg.input_value('#pref-cable-stock-all-ft') == '20, 40, 80'
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    assert pg.evaluate("() => window.app.cableStockText(125, 'multi')") == "80'+40'+20'"

    # Delete asks first; No keeps it, Yes removes it
    _open(pg)
    pg.wait_for_function("() => document.querySelectorAll('#pref-cable-stock-preset option').length > 1")
    pg.select_option('#pref-cable-stock-preset', 'Shop B')
    pg.click('#pref-cable-stock-delete')
    answer_app_dialog(pg, accept=False)
    pg.wait_for_timeout(300)
    assert [p['name'] for p in _presets(pg)] == ['Shop B']
    pg.click('#pref-cable-stock-delete')
    answer_app_dialog(pg)
    pg.wait_for_timeout(500)
    assert _presets(pg) == []
    assert pg.evaluate("() => document.querySelectorAll('#pref-cable-stock-preset option').length") == 1
    assert pg.is_disabled('#pref-cable-stock-load') and pg.is_disabled('#pref-cable-stock-delete')
    pg.click('#preferences-cancel')
    # the show keeps the lengths it took from the deleted preset
    assert pg.evaluate("() => window.app.cableStock().ft.all") == [20, 40, 80]
    assert errors == [], errors


def test_a_new_show_starts_with_the_default_preset(page):
    """New shows start with: a preset picked there is a preference
    (cableStockDefault); File > New then carries its stock, and No stock
    puts new shows back to none. Undo of a new show is not involved: the
    stock is the new show's own."""
    pg, errors = page
    pg.evaluate("""async () => {
        await fetch('/api/cable-stock-presets', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Vendor', stock: {perKind: false, ft: {all: [50, 100]}, m: {all: [15]}}})});
    }""")
    _open(pg)
    pg.wait_for_function("() => [...document.querySelectorAll('#pref-cable-stock-default option')].some(o => o.value === 'Vendor')")
    pg.select_option('#pref-cable-stock-default', 'Vendor')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert served['cableStockDefault'] == 'Vendor', served
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    st = pg.evaluate("() => [window.app.cableStock() && window.app.cableStock().ft.all, window.app.cableStockText(125, 'multi')]")
    assert st == [[50, 100], "100'+50'"], st
    # reopened, the default shows; back to No stock and the next show has none
    _open(pg)
    assert pg.input_value('#pref-cable-stock-default') == 'Vendor'
    assert pg.input_value('#pref-cable-stock-all-ft') == '50, 100'
    pg.select_option('#pref-cable-stock-default', '')
    pg.click('#preferences-save')
    pg.wait_for_timeout(500)
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    assert pg.evaluate("() => window.app.cableStock()") is None
    assert pg.evaluate("async () => (await (await fetch('/api/preferences')).json()).cableStockDefault") == ''
    assert errors == [], errors
