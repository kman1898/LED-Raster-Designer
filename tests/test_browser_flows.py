"""Browser E2E flow tests (Playwright): user-level workflows across the
modularized frontend — app boot, screen editing, modals, tours, undo, and the
launcher splash page.

Run locally:
    pip install playwright && playwright install chromium
    python -m pytest tests/test_browser_flows.py -v --browser chromium
"""

import sys
import os


import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))


# Shared session fixtures (one Playwright driver + one live server) live in
# conftest.py: browser_name, e2e_server, pw_browser.

@pytest.fixture(scope="session")
def flows_server(e2e_server):
    return e2e_server


@pytest.fixture(scope="session")
def flows_browser(pw_browser):
    return pw_browser


@pytest.fixture(scope="session")
def page(flows_server, flows_browser):
    """One long-lived page; tests assert deltas rather than absolute state."""
    context = flows_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(flows_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    yield pg
    context.close()


def layer_count(page):
    return page.evaluate("window.app.project.layers.length")


# ── Modular frontend boot ────────────────────────────────────────────────


def test_modular_app_assembles(page):
    """The ES-module split reassembles the full LEDRasterApp at runtime."""
    result = page.evaluate("""() => {
        const app = window.app;
        const proto = app ? Object.getPrototypeOf(app) : null;
        return {
            appExists: !!app,
            className: proto ? proto.constructor.name : null,
            methodCount: proto ? Object.getOwnPropertyNames(proto).length : 0,
            canvasRenderer: !!window.canvasRenderer,
            helpers: typeof window.sendClientLog === 'function'
                  && typeof window.normalizeHex === 'function',
        };
    }""")
    assert result['appExists'], "window.app missing"
    assert result['className'] == 'LEDRasterApp'
    assert result['methodCount'] > 250, (
        f"prototype looks incomplete: {result['methodCount']} members")
    assert result['canvasRenderer'], "canvas renderer missing"
    assert result['helpers'], "shared helpers not exposed for classic scripts"


def test_socket_connects(page):
    """SocketIO client connects to the server."""
    connected = page.evaluate(
        "!!(window.app && window.app.socket && window.app.socket.connected)")
    assert connected, "socket not connected"


def test_no_js_errors_on_fresh_load(page, flows_server):
    """A fresh page load produces zero uncaught JS errors."""
    errors = []
    pg = page.context.new_page()
    pg.on('pageerror', lambda err: errors.append(str(err)))
    pg.goto(flows_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    pg.close()
    assert errors == [], f"JS errors on load: {errors}"


# ── Screen editing flows ─────────────────────────────────────────────────


def test_add_screen_via_preset_picker(page):
    """The Add Screen modal flow adds a layer to the project."""
    before = layer_count(page)
    page.evaluate("window.app.openPresetPicker()")
    page.wait_for_timeout(300)
    modal = page.locator('#preset-picker-modal')
    assert modal.is_visible(), "preset picker modal did not open"
    page.locator('#preset-picker-add').click()
    page.wait_for_timeout(500)
    assert layer_count(page) == before + 1, "layer was not added"


def test_screen_info_columns_roundtrip(page):
    """Editing Columns in Screen Info updates the selected layer."""
    cols = page.locator('#screen-columns')
    cols.fill('6')
    cols.dispatch_event('change')
    page.wait_for_timeout(500)
    value = page.evaluate(
        "window.app.currentLayer ? window.app.currentLayer.columns : null")
    assert value == 6, f"columns did not round-trip (got {value})"


def test_rotation_via_screen_info(page):
    """Setting Rotation to 90 updates the layer (rotation feature)."""
    rot = page.locator('#screen-rotation')
    rot.select_option('90')
    page.wait_for_timeout(500)
    value = page.evaluate(
        "window.app.currentLayer ? window.app.currentLayer.rotation : null")
    assert value == 90, f"rotation did not apply (got {value})"
    # restore
    rot.select_option('0')
    page.wait_for_timeout(300)


def test_undo_restores_layer_count(page):
    """Ctrl/Cmd+Z undoes the last structural change."""
    before = layer_count(page)
    page.evaluate("window.app.addLayer()")
    page.wait_for_timeout(600)
    assert layer_count(page) == before + 1
    page.locator('canvas#main-canvas').click(position={'x': 5, 'y': 5})
    page.keyboard.press('ControlOrMeta+z')
    page.wait_for_timeout(800)
    assert layer_count(page) == before, "undo did not restore layer count"


def test_add_canvas_via_button(page):
    """+ Add Canvas creates a second canvas in the project."""
    before = page.evaluate("window.app.project.canvases.length")
    page.locator('#btn-add-canvas').click()
    page.wait_for_timeout(600)
    after = page.evaluate("window.app.project.canvases.length")
    assert after == before + 1, "canvas was not added"


# ── Modal flows ──────────────────────────────────────────────────────────


def test_export_modal_opens_and_closes(page):
    expected_ids = page.evaluate(
        "window.app.project.canvases.map(canvas => canvas.id)"
    )
    page.locator('#btn-export').click()
    page.wait_for_timeout(300)
    assert page.locator('#export-modal').is_visible(), "export modal not shown"
    actual_ids = page.locator(
        '#export-canvases-list .export-canvas-checkbox'
    ).evaluate_all(
        "(checkboxes) => checkboxes.map(checkbox => checkbox.dataset.canvasId)"
    )
    assert actual_ids == expected_ids
    page.locator('#export-cancel').click()
    page.wait_for_timeout(300)
    assert not page.locator('#export-modal').is_visible()


@pytest.mark.parametrize(
    ('action', 'expected_format'),
    [('export-png', 'png'), ('export-psd', 'psd')],
)
def test_file_menu_export_populates_canvas_picker(page, action, expected_format):
    """File-menu exports rebuild the same canvas picker as the toolbar."""
    expected_ids = page.evaluate(
        "window.app.project.canvases.map(canvas => canvas.id)"
    )
    previous_format = page.locator('#export-format').input_value()
    page.evaluate("""() => {
        document.getElementById('export-modal').style.display = 'none';
        document.getElementById('export-canvases-list').replaceChildren();
    }""")

    page.locator('[data-menu="file"]').click()
    page.locator(f'[data-action="{action}"]').click()
    page.wait_for_timeout(300)

    actual_ids = page.locator(
        '#export-canvases-list .export-canvas-checkbox'
    ).evaluate_all(
        "(checkboxes) => checkboxes.map(checkbox => checkbox.dataset.canvasId)"
    )
    assert actual_ids == expected_ids
    assert page.locator('#export-format').input_value() == expected_format

    page.locator('#export-cancel').click()
    page.wait_for_timeout(300)
    page.evaluate("""(format) => {
        const select = document.getElementById('export-format');
        select.value = format;
        select.dispatchEvent(new Event('change'));
    }""", previous_format)


def test_preferences_modal_opens_and_closes(page):
    page.locator('#btn-preferences').click()
    page.wait_for_timeout(300)
    assert page.locator('#preferences-modal').is_visible(), "prefs modal not shown"
    page.locator('#preferences-cancel').click()
    page.wait_for_timeout(300)
    assert not page.locator('#preferences-modal').is_visible()


def test_logs_viewer_opens(page):
    page.evaluate("window.app.handleMenuAction('show-logs')")
    page.wait_for_timeout(600)
    assert page.locator('#logs-modal').is_visible(), "logs modal not shown"
    page.locator('#logs-close').click()
    page.wait_for_timeout(300)
    assert not page.locator('#logs-modal').is_visible()


# ── Guided tours ─────────────────────────────────────────────────────────


def test_quickstart_auto_show_suppressed_for_webdriver(page, flows_server, flows_browser):
    """The first-run tour must NOT auto-show in automated browsers, even with
    a clean localStorage (this is what keeps E2E clickable)."""
    context = flows_browser.new_context()  # no localStorage flag
    pg = context.new_page()
    pg.goto(flows_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    catch_visible = pg.evaluate(
        "!!document.querySelector('#qs-catch')")
    context.close()
    assert not catch_visible, "tour auto-showed under navigator.webdriver"


def test_quickstart_manual_start_and_navigation(page):
    page.evaluate("window.QuickStart.start()")
    page.wait_for_timeout(400)
    title1 = page.locator('#qs-callout h3').text_content()
    assert title1, "tour callout missing"
    page.locator('#qs-next').click()
    page.wait_for_timeout(400)
    title2 = page.locator('#qs-callout h3').text_content()
    assert title2 and title2 != title1, "tour did not advance"
    page.evaluate("window.QuickStart.end()")
    page.wait_for_timeout(200)
    # end() hides the overlay (display:none) rather than removing it
    assert not page.locator('#qs-catch').is_visible(), "tour overlay still visible"


def test_advanced_guide_switches_views(page):
    """The Advanced Guide's view-switching steps drive the real view tabs."""
    page.evaluate("window.QuickStart.startAdvanced()")
    page.wait_for_timeout(400)
    # advance until the Data view step (step 11 of 19) or give up after 14
    reached_data = False
    for _ in range(14):
        title = page.locator('#qs-callout h3').text_content() or ''
        if 'Data' in title:
            reached_data = True
            break
        page.locator('#qs-next').click()
        page.wait_for_timeout(350)
    assert reached_data, "never reached the Data view step"
    active = page.evaluate(
        "document.querySelector('[data-mode=\"data-flow\"]').classList.contains('active')")
    assert active, "Data view step did not switch the app to the Data view"
    page.evaluate("window.QuickStart.end()")
    # return to pixel map for any later tests
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)


# ── Launcher splash page ─────────────────────────────────────────────────


def test_launcher_splash_demo_boot(page):
    """launcher_window.html boots standalone (demo mode) with all controls."""
    splash = os.path.join(SRC_DIR, 'launcher_window.html')
    pg = page.context.new_page()
    errors = []
    pg.on('pageerror', lambda err: errors.append(str(err)))
    pg.goto('file://' + splash, wait_until='domcontentloaded')
    pg.wait_for_timeout(600)
    state = pg.evaluate("""() => ({
        status: document.getElementById('status-word').textContent,
        ifaceOptions: document.getElementById('iface').options.length,
        browserOptions: document.getElementById('browser').options.length,
        buttons: [...document.querySelectorAll('.btn')].map(b => b.textContent),
    })""")
    pg.close()
    assert errors == [], f"splash JS errors: {errors}"
    assert state['status'] == 'Running'
    assert state['ifaceOptions'] > 0 and state['browserOptions'] > 0
    assert state['buttons'] == ['Launch GUI', 'Hide', 'Quit']


# ── Deep journeys: export, canvas interaction, views, persistence ────────


def test_export_png_produces_download(page):
    """The full export pipeline (modal -> client render -> file) produces a
    real PNG download. Only the OS save-dialog boundary is stubbed with the
    plain browser-download path; rendering and the modal flow are real."""
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)
    page.evaluate("""() => {
        window.app.saveBlobWithPicker = async (blobOrFn, filename) => {
            const blob = typeof blobOrFn === 'function' ? await blobOrFn() : blobOrFn;
            window.app.downloadBlob(blob, filename);
        };
    }""")
    page.locator('#btn-export').click()
    page.wait_for_timeout(300)
    assert page.locator('#export-modal').is_visible()
    # Force exactly ONE canvas and ONE view: multiple selections route to the
    # multi-file (directory picker) path instead of a single browser download.
    page.evaluate("""() => {
        const canvases = [...document.querySelectorAll('#export-canvases-list input[type=checkbox]')];
        canvases.forEach((b, i) => { if (i > 0 && b.checked) b.click(); });
        if (canvases[0] && !canvases[0].checked) canvases[0].click();
        const views = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power'];
        views.forEach((v, i) => {
            const el = document.getElementById('export-' + v);
            if (el && el.checked !== (i === 0)) el.click();
        });
    }""")
    with page.expect_download(timeout=30000) as dl_info:
        page.locator('#export-confirm').click()
    download = dl_info.value
    assert download.suggested_filename.lower().endswith('.png'), (
        f"expected a PNG, got {download.suggested_filename}")
    path = download.path()
    assert path and os.path.getsize(path) > 1000, "downloaded PNG is empty"
    with open(path, 'rb') as f:
        assert f.read(8) == b'\x89PNG\r\n\x1a\n', "not a valid PNG file"
    page.wait_for_timeout(400)


def test_alt_click_blanks_panel(page):
    """Alt+clicking a cabinet on the Pixel Map toggles its blank state."""
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)
    # Self-setup: an earlier test may have left an empty canvas active. Select
    # the first real layer and activate ITS canvas so its panels are on screen.
    page.evaluate("""() => {
        const layer = window.app.project.layers[0];
        window.app._activateCanvasForLayer(layer, { skipSave: true });
        window.app.selectLayer(layer);
        window.canvasRenderer.fitToView();
    }""")
    page.wait_for_timeout(500)
    # Compute a click point over the current layer, then ask the renderer
    # which panel is actually AT that point (layers may overlap), and assert
    # on that exact panel.
    target = page.evaluate("""() => {
        const layer = window.app.currentLayer;
        const p = layer.panels.find(p => !p.hidden);
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        const worldX = p.x + p.width / 2;
        const worldY = p.y + p.height / 2;
        const hit = r.getPanelAt(worldX, worldY);
        if (!hit) return null;
        return {
            layerId: hit.layerId,
            panelId: hit.panel.id,
            x: rect.left + r.panX + worldX * r.zoom,
            y: rect.top + r.panY + worldY * r.zoom,
        };
    }""")
    assert target, "no panel under the intended click point"
    read_hidden = (
        "window.app.project.layers.find(l => l.id === {lid})"
        ".panels.find(p => p.id === {pid}).hidden"
    ).format(lid=target['layerId'], pid=target['panelId'])
    page.keyboard.down('Alt')
    page.mouse.click(target['x'], target['y'])
    page.keyboard.up('Alt')
    page.wait_for_timeout(600)
    assert page.evaluate(read_hidden) is True, "alt-click did not blank the panel"
    # toggle back
    page.keyboard.down('Alt')
    page.mouse.click(target['x'], target['y'])
    page.keyboard.up('Alt')
    page.wait_for_timeout(600)
    assert page.evaluate(read_hidden) is False, "second alt-click did not restore the panel"


def test_data_view_shows_port_calculations(page):
    """The Data view sidebar shows computed port capacity numbers."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(500)
    ports = page.locator('#ports-required').text_content() or ''
    per_port = page.locator('#panels-per-port').text_content() or ''
    assert any(ch.isdigit() for ch in ports), f"ports-required empty: {ports!r}"
    assert any(ch.isdigit() for ch in per_port), f"panels-per-port empty: {per_port!r}"


def test_power_view_renders_sidebar(page):
    """The Power view shows its settings sidebar."""
    page.locator('[data-mode="power"]').click()
    page.wait_for_timeout(500)
    assert page.locator('#power-amperage-select').is_visible(), (
        "power sidebar controls not visible")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)


def test_project_rename_persists_to_server(page, flows_server):
    """Renaming the project in the toolbar persists via the save API."""
    name_input = page.locator('#project-name')
    name_input.fill('E2E Validation Show')
    name_input.dispatch_event('change')
    page.wait_for_timeout(700)
    resp = page.request.get(flows_server + '/api/project')
    assert resp.ok
    assert resp.json().get('name') == 'E2E Validation Show', (
        f"server has name {resp.json().get('name')!r}")


def test_redo_restores_undone_layer(page):
    """Undo then redo round-trips a structural change."""
    before = layer_count(page)
    page.evaluate("window.app.addLayer()")
    page.wait_for_timeout(600)
    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(600)
    assert layer_count(page) == before
    page.evaluate("window.app.handleMenuAction('redo')")
    page.wait_for_timeout(600)
    assert layer_count(page) == before + 1, "redo did not restore the layer"
    page.evaluate("window.app.handleMenuAction('undo')")  # cleanup
    page.wait_for_timeout(400)


def test_zoom_controls_change_zoom(page):
    """Zoom-in and Fit buttons drive the canvas renderer zoom."""
    z0 = page.evaluate("window.canvasRenderer.zoom")
    page.locator('#btn-zoom-in').click()
    page.wait_for_timeout(200)
    z1 = page.evaluate("window.canvasRenderer.zoom")
    assert z1 > z0, f"zoom-in did not increase zoom ({z0} -> {z1})"
    page.locator('#btn-fit').click()
    page.wait_for_timeout(300)
    z2 = page.evaluate("window.canvasRenderer.zoom")
    assert z2 != z1, "Fit did not change the zoom"


# ── UI state persistence across refresh ──────────────────────────────────


def test_panel_state_persists_across_refresh(page, flows_server):
    """Expanded Notes/Help panels stay expanded after a page refresh."""
    pg = page.context.new_page()
    pg.goto(flows_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    # expand both bottom-right panels via their real header click targets
    pg.locator('#help-tooltip-header').click()
    pg.locator('#notes-panel-header').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate(
        "!document.getElementById('help-tooltip-panel').classList.contains('collapsed')")
    # refresh and confirm restored
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    help_expanded = pg.evaluate(
        "!document.getElementById('help-tooltip-panel').classList.contains('collapsed')")
    notes_expanded = pg.evaluate(
        "!document.getElementById('notes-panel').classList.contains('collapsed')")
    # canvas must still lay out and fit correctly after the restore
    pg.wait_for_timeout(800)
    zoom_ok = pg.evaluate("window.canvasRenderer.zoom > 0.05")
    pg.close()
    assert help_expanded, "Help panel collapsed after refresh"
    assert notes_expanded, "Notes panel collapsed after refresh"
    assert zoom_ok, "canvas zoom broken after refresh"


def test_selects_show_dropdown_chevron(page):
    """Data-section selects render the custom dropdown chevron."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(400)
    styles = page.evaluate("""() => {
        const el = document.getElementById('processing-select')
              || document.querySelector('.tab-panel[data-tab="data-flow"] select');
        if (!el) return null;
        const cs = getComputedStyle(el);
        return { bg: cs.backgroundImage, appearance: cs.webkitAppearance || cs.appearance };
    }""")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)
    assert styles, "no select found in the Data sidebar"
    assert 'svg' in styles['bg'], f"chevron background missing: {styles['bg'][:60]}"
    assert styles['appearance'] == 'none'


def test_layer_drag_indicator_visible(page):
    """The drag-over insertion line on layer cards survives the tile styling
    (regression: the reskin's !important box-shadow silently erased it)."""
    shadow = page.evaluate("""() => {
        const li = document.querySelector('.layer-item');
        if (!li) return null;
        li.classList.add('drag-over-top');
        const s = getComputedStyle(li).boxShadow;
        li.classList.remove('drag-over-top');
        return s;
    }""")
    assert shadow, "no layer card found"
    # the accent inset line: a 3px spread inset shadow must be present
    assert 'inset' in shadow and '3px' in shadow, f"indicator shadow missing: {shadow}"


def test_wheel_zoom_on_canvas(page):
    """Scroll-wheel over the canvas zooms in and out (regression guard for
    the trackpad/wheel zoom path)."""
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)
    box = page.locator('canvas#main-canvas').bounding_box()
    cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    page.mouse.move(cx, cy)
    z0 = page.evaluate("window.canvasRenderer.zoom")
    page.mouse.wheel(0, -240)  # scroll up = zoom in
    page.wait_for_timeout(300)
    z1 = page.evaluate("window.canvasRenderer.zoom")
    assert z1 > z0, f"wheel up did not zoom in ({z0} -> {z1})"
    page.mouse.wheel(0, 240)   # scroll down = zoom out
    page.wait_for_timeout(300)
    z2 = page.evaluate("window.canvasRenderer.zoom")
    assert z2 < z1, f"wheel down did not zoom out ({z1} -> {z2})"
