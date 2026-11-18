"""Esc closes what is drawn on top, one thing per key press (1.7.0).

A dock gear panel open over Preferences kept its Esc from the dialog under
it: the menu bar's Esc closed the top open dialog before anything else had
a say, so Preferences closed and the panel stayed. And a dialog drawn over
an open panel (Output to Display opened from the keyboard) closed together
with the panel on the one Esc.

Every dialog, panel, popover and menu that closes on Esc now asks whether
another of them is drawn over it (helpers.js escapeCovered, read from the
page's real stacking once per key press) and stands aside when one is: the
top one closes, the one under it on the next Esc. Where nothing overlaps,
each closes on Esc as it always did.

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest tests/test_escape_closes_top.py -q --browser chromium
"""

import json

import pytest

import app as app_module

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

DISTRO = {'id': 'd1', 'name': 'DISTRO 1', 'system': '120/208', 'voltage': 208, 'phase': 3,
          'ratingA': 400}


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    app_module.current_project['distros'] = [json.loads(json.dumps(DISTRO))]
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project && window.LRD_LAYOUT "
                         "&& (window.app.project.distros || []).some(d => d.id === 'd1')",
                         timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer && window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


@pytest.fixture(autouse=True)
def _clean(page):
    """Each test starts and ends with nothing open."""
    pg, _ = page
    _reset(pg)
    yield
    _reset(pg)


def _reset(pg):
    pg.evaluate("""() => {
        const app = window.app;
        app._hwPopoverClose();
        const od = document.getElementById('output-display-modal');
        if (od && od.style.display !== 'none') app.closeOutputDisplayDialog();
        const prefs = document.getElementById('preferences-modal');
        if (prefs.style.display !== 'none') document.getElementById('preferences-cancel').click();
        for (const m of [od, prefs]) if (m) m.style.zIndex = '';
        const pop = document.getElementById('hw-gear-popover');
        if (pop) pop.style.zIndex = '';
    }""")


def _open_panel(pg):
    """The gear's own click handler, dispatched: with a dialog up, the
    dialog's backdrop is over the tray, as it is for a keyboard user who
    Tabs to the gear behind the dialog and presses Enter."""
    pg.evaluate("""() => {
        const app = window.app;
        app.renderHardwareDock();
        document.querySelector('[data-hwpop="distro-d1"]').click();
    }""")
    pg.wait_for_function("() => { const p = document.getElementById('hw-gear-popover');"
                         " return p && p.style.display === 'block'"
                         " && p.style.visibility === 'visible'; }")


def _panel_open(pg):
    return pg.evaluate("() => !!window.app._hwPopover && "
                       "document.getElementById('hw-gear-popover').style.display === 'block'")


def _shown(pg, modal_id):
    return pg.evaluate("""(id) => { const m = document.getElementById(id);
        return !!m && m.style.display !== 'none' && getComputedStyle(m).display !== 'none'; }""",
                       modal_id)


def _open_preferences(pg):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_function("() => document.getElementById('preferences-modal').style.display === 'block'")


def _on_top_at_panel(pg, modal_id):
    """Which of the panel and the dialog the browser paints on top, at the
    panel's middle."""
    return pg.evaluate("""(id) => {
        const pop = document.getElementById('hw-gear-popover');
        const modal = document.getElementById(id);
        const r = pop.getBoundingClientRect();
        const hit = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2)
            .find(n => pop.contains(n) || modal.contains(n));
        return hit ? (pop.contains(hit) ? 'panel' : 'dialog') : null;
    }""", modal_id)


def _press_escape(pg):
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(150)


def test_a_panel_over_preferences_closes_first_then_preferences(page):
    pg, errors = page
    _open_preferences(pg)
    _open_panel(pg)
    assert _on_top_at_panel(pg, 'preferences-modal') == 'panel'
    _press_escape(pg)
    assert not _panel_open(pg), "Esc did not close the panel drawn over Preferences"
    assert _shown(pg, 'preferences-modal'), "Esc closed Preferences under the panel too"
    _press_escape(pg)
    assert not _shown(pg, 'preferences-modal'), "the next Esc did not close Preferences"
    assert not errors, errors


def test_preferences_over_a_panel_closes_first_then_the_panel(page):
    """The other stacking: Preferences drawn over the panel."""
    pg, errors = page
    _open_panel(pg)
    _open_preferences(pg)
    pg.evaluate("() => { document.getElementById('preferences-modal').style.zIndex = '1001'; }")
    assert _on_top_at_panel(pg, 'preferences-modal') == 'dialog'
    _press_escape(pg)
    assert not _shown(pg, 'preferences-modal'), "Esc did not close Preferences on top"
    assert _panel_open(pg), "Esc closed the panel under Preferences too"
    _press_escape(pg)
    assert not _panel_open(pg), "the next Esc did not close the panel"
    assert not errors, errors


def test_output_to_display_over_a_panel_closes_alone(page):
    """A dialog with its own Esc (Output to Display) drawn over the panel:
    the one Esc closed both."""
    pg, errors = page
    _open_panel(pg)
    # Output to Display from the keyboard (Tab to the toolbar button, Enter):
    # no press of the mouse, so the panel stays open under it.
    pg.evaluate("() => window.app.handleMenuAction('output-to-display')")
    pg.wait_for_function("() => { const m = document.getElementById('output-display-modal');"
                         " return !!m && m.style.display !== 'none'; }")
    assert _panel_open(pg)
    assert _on_top_at_panel(pg, 'output-display-modal') == 'dialog'
    _press_escape(pg)
    assert not _shown(pg, 'output-display-modal'), "Esc did not close Output to Display"
    assert _panel_open(pg), "the one Esc closed the panel under the dialog too"
    _press_escape(pg)
    assert not _panel_open(pg), "the next Esc did not close the panel"
    assert not errors, errors


def test_a_panel_raised_over_output_to_display_closes_first(page):
    """The same pair stacked the other way: the panel on top closes, the
    dialog waits for the next Esc."""
    pg, errors = page
    _open_panel(pg)
    pg.evaluate("() => window.app.handleMenuAction('output-to-display')")
    pg.wait_for_function("() => { const m = document.getElementById('output-display-modal');"
                         " return !!m && m.style.display !== 'none'; }")
    pg.evaluate("() => { document.getElementById('hw-gear-popover').style.zIndex = '1001'; }")
    assert _on_top_at_panel(pg, 'output-display-modal') == 'panel'
    _press_escape(pg)
    assert not _panel_open(pg), "Esc did not close the panel on top"
    assert _shown(pg, 'output-display-modal'), "the one Esc closed the dialog under the panel too"
    _press_escape(pg)
    assert not _shown(pg, 'output-display-modal')
    assert not errors, errors


def test_alone_each_still_closes_on_escape(page):
    """Nothing over anything: Esc closes the panel, and Preferences, as before."""
    pg, errors = page
    _open_panel(pg)
    _press_escape(pg)
    assert not _panel_open(pg)
    _open_preferences(pg)
    _press_escape(pg)
    assert not _shown(pg, 'preferences-modal')
    assert not errors, errors


# ── a dialog opened from the canvas's right-click menu ───────────────────
# QA (1.7.0): on the Pixel Map, right-click a screen, pick Output to
# Display, Esc: the first Esc cleared the cabinet the right-click had picked
# (the canvas's own Esc, a step behind the dialog) and only the second
# closed the dialog. Esc closes the dialog, and nothing behind it reacts.

SCREEN_POINT_JS = """() => {
    const r = window.canvasRenderer, l = window.app.project.layers[0];
    const box = r.canvas.getBoundingClientRect();
    const show = r.viewMode !== 'pixel-map' && r.viewMode !== 'cabinet-id';
    const x0 = show && l.showOffsetX != null ? l.showOffsetX : l.offset_x;
    const y0 = show && l.showOffsetY != null ? l.showOffsetY : l.offset_y;
    return [box.left + r.panX + (x0 + l.cabinet_width * 1.5) * r.zoom,
            box.top + r.panY + (y0 + l.cabinet_height * 1.5) * r.zoom];
}"""

MENU_DIALOGS = [
    ('output-canvas-to-display', 'output-display-modal'),
    ('export-screen-binder', 'export-modal'),
    ('change-cabinet', 'preset-picker-modal'),
]
TABS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power', 'rigging']


@pytest.mark.parametrize('tab', TABS)
def test_a_dialog_from_the_right_click_menu_closes_on_the_first_esc(page, tab):
    pg, errors = page
    assert pg.evaluate("() => (window.app.project.layers || []).length") >= 1
    pg.locator(f'[data-mode="{tab}"]').click()
    pg.wait_for_function("(m) => window.canvasRenderer.viewMode === m", arg=tab)
    pg.evaluate("() => window.canvasRenderer.fitToView && window.canvasRenderer.fitToView()")
    pg.wait_for_timeout(150)
    tried = []
    try:
        for action, modal_id in MENU_DIALOGS:
            x, y = pg.evaluate(SCREEN_POINT_JS)
            pg.mouse.click(x, y, button='right')
            pg.wait_for_function("() => document.getElementById('context-menu').style.display === 'block'")
            item = pg.locator(f'#context-menu [data-action="{action}"]')
            if not item.is_visible() or 'menu-disabled' in (item.get_attribute('class') or ''):
                pg.keyboard.press('Escape')
                pg.wait_for_timeout(100)
                continue
            tried.append(action)
            picked = pg.evaluate("() => window.app.pixelMapSelection ? window.app.pixelMapSelection.size : 0")
            item.click()
            pg.wait_for_function("(id) => { const m = document.getElementById(id);"
                                 " return !!m && getComputedStyle(m).display !== 'none'; }", arg=modal_id)
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(150)
            assert not _shown(pg, modal_id), f"{tab}: the first Esc did not close {modal_id} ({action})"
            # nothing behind the dialog answered that Esc
            assert pg.evaluate("() => window.app.pixelMapSelection ? window.app.pixelMapSelection.size : 0") \
                == picked, f"{tab}: the Esc that closed {modal_id} also cleared the picked cabinets"
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(100)
        assert 'output-canvas-to-display' in tried, (tab, tried)
    finally:
        pg.keyboard.press('Escape')
        pg.locator('[data-mode="power"]').click()
    assert not errors, errors


def test_with_no_dialog_up_esc_still_clears_the_picked_cabinets(page):
    pg, errors = page
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'pixel-map'")
    try:
        x, y = pg.evaluate(SCREEN_POINT_JS)
        pg.mouse.click(x, y, button='right')
        pg.wait_for_function("() => document.getElementById('context-menu').style.display === 'block'")
        assert pg.evaluate("() => window.app.pixelMapSelection.size") >= 1
        pg.keyboard.press('Escape')      # the menu
        pg.wait_for_timeout(100)
        assert pg.evaluate("() => window.app.pixelMapSelection.size") >= 1
        pg.keyboard.press('Escape')      # then the cabinets
        pg.wait_for_timeout(100)
        assert pg.evaluate("() => window.app.pixelMapSelection.size") == 0
    finally:
        pg.locator('[data-mode="power"]').click()
    assert not errors, errors
