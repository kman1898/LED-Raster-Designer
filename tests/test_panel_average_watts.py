"""The panel picker shows a panel's average watts beside its max (owner,
2026-10-30).

The catalog has carried `watts_ave` for some panels all along, but the app
never showed it. The picker now reads "340W max · 120W avg" where the sheet
gives an average, and "340W" where it doesn't. Only the max is planned on:
the screen still takes watts_max as its panel watts. A hearted favorite
keeps the average too, and a spec correction report lists it.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_panel_average_watts.py -v --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    yield pg, errors
    pg.evaluate("() => window.app.setAddLayerFavorites([])")
    context.close()


def test_the_picker_reads_max_and_average(page):
    pg, errors = page
    got = pg.evaluate("""() => [
        window.app._panelWattsText({ watts_max: 340, watts_ave: 120 }),
        window.app._panelWattsText({ watts_max: 340, watts_ave: null }),
        window.app._panelWattsText({ watts_max: 340 }),
        window.app._panelWattsText({ watts_max: null, watts_ave: 50 }),
    ]""")
    assert got == ['340W max · 120W avg', '340W', '340W', '']
    assert errors == []


def test_a_hearted_panel_keeps_its_average_and_the_screen_still_plans_on_max(page):
    pg, _ = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        await app._ensurePanelCatalogData();
        let panel = null;
        for (const [mfr, list] of Object.entries(app._panelCatalog)) {
            const p = list.find(x => x.watts_ave != null && x.watts_max != null
                                     && x.watts_ave !== x.watts_max);
            if (p) { panel = { ...p, _mfr: mfr }; break; }
        }
        app.setAddLayerFavorites([]);
        app._toggleCatalogFavorite(panel);
        const fav = app.getAddLayerFavorites()[0];
        const data = app._panelToPresetData(panel);
        return { max: panel.watts_max, ave: panel.watts_ave, favAve: fav.watts_ave,
                 panelWatts: data.panelWatts };
    }""")
    assert out['favAve'] == out['ave'], out
    assert out['panelWatts'] == out['max'], out
