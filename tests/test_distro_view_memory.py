"""A new distro starts with every cable sheet down and every section open.

The power side of test_hardware_view_memory. A multi's cable sheet
(lrd_cable_sheet_<distro>_<n>) and the distro's folds
(ledRasterPanelCollapsed_hwdock-distro-<id>, -multi-<id>-<n>,
-drow-<id>-<row>) are remembered in localStorage under the distro's id,
and distro ids come back: addDistro takes the next number after the
highest, so removing DISTRO 2 and adding one hands out "d2" again, and so
do undo and every new show. Now (app-dock-cable-sheets.js
_forgetDistroViews) every power render forgets the keys of distros not in
the project, an add forgets its new id's, and File > New or opening a
show forgets them all. A page reload keeps them.

Run locally:
    python -m pytest tests/test_distro_view_memory.py -q
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


KEYS_JS = """() => {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k.startsWith('lrd_cable_sheet_')
                || k.startsWith('ledRasterPanelCollapsed_hwdock-distro-')
                || k.startsWith('ledRasterPanelCollapsed_hwdock-multi-')
                || k.startsWith('ledRasterPanelCollapsed_hwdock-drow-')) {
            out[k] = localStorage.getItem(k);
        }
    }
    return out;
}"""

# What a person leaves behind on DISTRO 2: multi 1's cable sheet up, the
# distro and the multi folded.
LEAVE_JS = """(id) => {
    window.app._setCableSheetOpen(id, 1, true);
    localStorage.setItem(`ledRasterPanelCollapsed_hwdock-distro-${id}`, '1');
    localStorage.setItem(`ledRasterPanelCollapsed_hwdock-multi-${id}-1`, '1');
}"""


@pytest.fixture()
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true")
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_function("() => window.app.project && !(window.app.project.distros || []).length")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg
    context.close()


def _distro_keys(pg, distro_id):
    return {k: v for k, v in pg.evaluate(KEYS_JS).items()
            if k.endswith(f'_{distro_id}_1') or f'-{distro_id}' in k}


def test_a_removed_distros_id_comes_back_with_nothing_open(page):
    page.evaluate("() => { window.app.addDistro(); window.app.addDistro(); }")
    assert page.evaluate("() => window.app.getDistros().map(d => d.id)") == ['d1', 'd2']
    page.evaluate(LEAVE_JS, 'd2')
    assert len(_distro_keys(page, 'd2')) == 3
    page.evaluate("() => { window.app.removeDistro('d2'); window.app.renderHardwareDock(); }")
    page.wait_for_timeout(300)
    assert _distro_keys(page, 'd2') == {}, 'the removed distro left its sheet or folds'
    assert page.evaluate("() => window.app.addDistro().id") == 'd2'
    assert page.evaluate("(id) => window.app._cableSheetOpen(id, 1)", 'd2') is False


def test_an_add_never_inherits_a_leftover_and_a_new_show_forgets_all(page):
    page.evaluate("() => window.app.addDistro()")
    # keys left over from another show's d2 (or an undone add)
    page.evaluate(LEAVE_JS, 'd2')
    assert page.evaluate("() => window.app.addDistro().id") == 'd2'
    assert _distro_keys(page, 'd2') == {}, 'the new d2 came up with the old sheet'
    # d1's own memory survives a render while d1 is in the show...
    page.evaluate(LEAVE_JS, 'd1')
    page.evaluate("() => window.app.renderHardwareDock()")
    assert len(_distro_keys(page, 'd1')) == 3
    # ...and File > New forgets it: the next show's d1 is another distro
    page.evaluate("() => window.app.createNewProject()")
    page.wait_for_function("() => !(window.app.project.distros || []).length")
    assert page.evaluate(KEYS_JS) == {}
