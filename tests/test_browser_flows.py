"""Browser E2E flow tests (Playwright): user-level workflows across the
modularized frontend — app boot, screen editing, modals, tours, undo, and the
launcher splash page.

Run locally:
    pip install playwright && playwright install chromium
    python -m pytest tests/test_browser_flows.py -v --browser chromium
"""

import sys
import os
import itertools


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

# ── Port mapping: Organized vs Max Capacity (v0.10.9) ────────────────────
# calculatePortAssignments() is the single source of truth for every port map
# the app emits. These tests drive it directly with synthetic layers through
# the live page (no DOM needed, the method is pure), and independently
# recompute each emitted port's bounding rectangle to prove that a
# rectangle-constraint processor (NovaStar Armor) never over-fills a port in
# EITHER mapping mode. An over-filled port means a dark wall section on site.

PORT_MAP_JS = """(spec) => {
    const hiddenSet = new Set((spec.hidden || []).map(rc => rc[0] + ',' + rc[1]));
    const panels = [];
    let n = 1;
    for (let r = 0; r < spec.rows; r++) {
        for (let c = 0; c < spec.columns; c++) {
            panels.push({
                id: n, number: n, row: r, col: c,
                x: c * spec.cw, y: r * spec.ch,
                width: spec.cw, height: spec.ch,
                hidden: hiddenSet.has(r + ',' + c), blank: false, halfTile: 'none'
            });
            n++;
        }
    }
    const layer = {
        type: 'screen', rows: spec.rows, columns: spec.columns,
        cabinet_width: spec.cw, cabinet_height: spec.ch, panels,
        processorType: spec.processorType,
        portMappingMode: spec.mode,
        flowPattern: spec.pattern || 'tl-h',
        bitDepth: spec.bitDepth || 8,
        frameRate: spec.frameRate || 60
    };
    const assignments = window.app.calculatePortAssignments(layer);
    const capacity = window.app.calculatePortCapacity(
        layer.bitDepth, layer.frameRate, layer.processorType);

    // Regroup the EMITTED assignments and recompute each port's geometry from
    // scratch, so the assertions test the shipped map, not the internal
    // bookkeeping that produced it.
    const byPort = new Map();
    assignments.forEach(a => {
        if (!byPort.has(a.port)) byPort.set(a.port, []);
        byPort.get(a.port).push(a.panel);
    });
    const ports = Array.from(byPort.keys()).sort((a, b) => a - b).map(p => {
        const ps = byPort.get(p);
        const minX = Math.min.apply(null, ps.map(q => q.x));
        const minY = Math.min.apply(null, ps.map(q => q.y));
        const maxX = Math.max.apply(null, ps.map(q => q.x + q.width));
        const maxY = Math.max.apply(null, ps.map(q => q.y + q.height));
        return {
            port: p,
            panels: ps.length,
            cells: ps.map(q => [q.row, q.col]),
            anyHidden: ps.some(q => q.hidden),
            rectArea: (maxX - minX) * (maxY - minY),
            pixelSum: ps.reduce((s, q) => s + q.width * q.height, 0)
        };
    });
    return {
        capacity: capacity,
        ports: ports,
        totalPanels: assignments.length,
        error: !!layer._capacityError,
        errorInfo: layer._capacityError || null
    };
}"""


def port_map(page, **spec):
    spec.setdefault('cw', 200)
    spec.setdefault('ch', 200)
    return page.evaluate(PORT_MAP_JS, spec)


def assert_rect_fits(result, label):
    """No emitted port may reserve more pixels than the port can carry."""
    for p in result['ports']:
        assert p['rectArea'] <= result['capacity'], (
            f"{label}: port {p['port']} reserves {p['rectArea']} px, "
            f"capacity is {result['capacity']} px -- this map would go dark")
        assert not p['anyHidden'], (
            f"{label}: port {p['port']} emitted a hidden cabinet")


def test_armor_max_capacity_is_selectable(page):
    """Armor no longer forces Organized -- max-capacity produces its own map."""
    org = port_map(page, rows=2, columns=20,
                   processorType='novastar-armor', mode='organized')
    mx = port_map(page, rows=2, columns=20,
                  processorType='novastar-armor', mode='max-capacity')
    # A 20-wide row reserves 4000x200 = 800,000 px against a 659,722 px port,
    # so Organized cannot fit a whole row and reports a capacity error.
    assert org['error'], "expected Organized to fail on an over-wide row"
    assert org['ports'] == []
    # Max Capacity splits mid-row and succeeds.
    assert not mx['error'], f"max-capacity unexpectedly errored: {mx['errorInfo']}"
    assert len(mx['ports']) == 3, [p['panels'] for p in mx['ports']]
    assert [p['panels'] for p in mx['ports']] == [16, 12, 12]
    assert [p['rectArea'] for p in mx['ports']] == [640000, 640000, 480000]
    assert mx['totalPanels'] == 40
    assert_rect_fits(mx, 'armor 2x20 max-capacity')


def test_armor_rectangular_wall_both_modes_agree(page):
    """A plain rectangular Armor wall maps identically in both modes.

    10 cols x 4 rows of 200x200: one row reserves 2000x200 = 400,000 px
    (fits the 659,722 px port); two rows reserve 2000x400 = 800,000 px (does
    not). Both modes therefore cut at every row boundary -> 4 ports of 10.
    """
    for mode in ('organized', 'max-capacity'):
        r = port_map(page, rows=4, columns=10,
                     processorType='novastar-armor', mode=mode)
        assert not r['error'], f"{mode} errored: {r['errorInfo']}"
        assert [p['panels'] for p in r['ports']] == [10, 10, 10, 10], mode
        assert [p['rectArea'] for p in r['ports']] == [400000] * 4, mode
        assert r['totalPanels'] == 40, mode
        assert_rect_fits(r, f'armor 4x10 {mode}')


def test_armor_stairstep_max_capacity_respects_rectangle(page):
    """L-shaped Armor wall: every max-capacity port still fits its rectangle.

    Rows shrink 10 / 8 / 5 / 2 cabinets wide. The reserved rectangle -- not the
    lit-pixel sum -- is what has to fit, so ports 1 and 2 carry 400,000 and
    640,000 px of reserved area while lighting only 400,000 and 520,000 px.
    """
    hidden = ([[1, c] for c in range(8, 10)]
              + [[2, c] for c in range(5, 10)]
              + [[3, c] for c in range(2, 10)])
    mx = port_map(page, rows=4, columns=10, hidden=hidden,
                  processorType='novastar-armor', mode='max-capacity')
    assert not mx['error'], f"errored: {mx['errorInfo']}"
    assert [p['panels'] for p in mx['ports']] == [10, 13, 2]
    assert [p['rectArea'] for p in mx['ports']] == [400000, 640000, 80000]
    # Port 2 reserves more than it lights: 13 cabinets = 520,000 lit px inside
    # a 1600x400 = 640,000 px reservation. A pixel-sum accounting would have
    # wrongly packed 3 more cabinets into this port.
    assert mx['ports'][1]['pixelSum'] == 520000
    assert mx['totalPanels'] == 25
    assert_rect_fits(mx, 'armor stairstep max-capacity')

    org = port_map(page, rows=4, columns=10, hidden=hidden,
                   processorType='novastar-armor', mode='organized')
    assert not org['error'], f"errored: {org['errorInfo']}"
    assert [p['panels'] for p in org['ports']] == [10, 13, 2]
    assert_rect_fits(org, 'armor stairstep organized')


def test_armor_hidden_cabinets_inside_span_cost_nothing_extra(page):
    """A hole inside the port's rectangle is already paid for by that rectangle.

    Row 0 has cabinets 4 and 5 removed. The port still spans x 0..2000, so its
    reservation stays 2000x200 = 400,000 px -- the two hidden cabinets neither
    add 80,000 px of their own nor shrink the span.
    """
    hidden = [[0, 4], [0, 5]]
    mx = port_map(page, rows=2, columns=10, hidden=hidden,
                  processorType='novastar-armor', mode='max-capacity')
    assert not mx['error'], f"errored: {mx['errorInfo']}"
    assert [p['panels'] for p in mx['ports']] == [8, 10]
    assert [p['rectArea'] for p in mx['ports']] == [400000, 400000]
    # Reserved 400,000 px while lighting only 320,000 px: the hole is covered
    # by the rectangle and is not double-counted on top of it.
    assert mx['ports'][0]['pixelSum'] == 320000
    assert mx['totalPanels'] == 18
    assert_rect_fits(mx, 'armor hidden-hole max-capacity')


def test_armor_oversized_cabinet_raises_capacity_error(page):
    """One cabinet too big for a port errors out instead of emitting a bad map."""
    # 1200x1200 = 1,440,000 px against a 659,722 px port.
    mx = port_map(page, rows=2, columns=2, cw=1200, ch=1200,
                  processorType='novastar-armor', mode='max-capacity')
    assert mx['error'], "oversized cabinet did not raise a capacity error"
    assert mx['ports'] == []
    assert mx['errorInfo']['unitType'] == 'panel'


def test_non_armor_max_capacity_uses_pixel_sum(page):
    """Non-rectangle processors keep the original pixel-sum packing.

    Brompton 8-bit @60 Hz = 525,000 px per port; a 200x200 cabinet is 40,000 px,
    so 13 cabinets (520,000 px) fill a port and the 40th lands alone.
    """
    mx = port_map(page, rows=4, columns=10,
                  processorType='brompton', mode='max-capacity')
    assert not mx['error'], f"errored: {mx['errorInfo']}"
    assert mx['capacity'] == 525000
    assert [p['panels'] for p in mx['ports']] == [13, 13, 13, 1]
    assert [p['pixelSum'] for p in mx['ports']] == [520000, 520000, 520000, 40000]
    assert mx['totalPanels'] == 40

    org = port_map(page, rows=4, columns=10,
                   processorType='brompton', mode='organized')
    assert [p['panels'] for p in org['ports']] == [10, 10, 10, 10]


def test_non_armor_max_capacity_ignores_bounding_rect(page):
    """The stair-step wall packs by pixel sum on Brompton, not by rectangle."""
    hidden = ([[1, c] for c in range(8, 10)]
              + [[2, c] for c in range(5, 10)]
              + [[3, c] for c in range(2, 10)])
    mx = port_map(page, rows=4, columns=10, hidden=hidden,
                  processorType='brompton', mode='max-capacity')
    assert not mx['error'], f"errored: {mx['errorInfo']}"
    # 25 visible cabinets, 13 per port by pixel sum.
    assert [p['panels'] for p in mx['ports']] == [13, 12]
    assert [p['pixelSum'] for p in mx['ports']] == [520000, 480000]
    assert mx['totalPanels'] == 25


# v0.10.9: Megapixel HELIOS pixels-per-port, pinned against the primary source:
# "HELIOS(R) LED Processing Platform - User Guide" v26.04.0 (2026-04-20),
# Appendix K.14, p.216. These numbers previously came from the rounded switch
# spec sheet and ran up to ~6% HIGH, which under-counts ports and can leave a
# wall section dark on site. Do not "fix" a failure here by editing the
# expected values -- re-check Appendix K.14 first.
MEGAPIXEL_K14 = [
    # (processorType, bitDepth, frameRate, pixels)
    ('megapixel-1g',   10, 24, 1237000),
    ('megapixel-1g',   10, 60, 482000),
    ('megapixel-1g',   10, 240, 104000),
    ('megapixel-1g',   12, 24, 1031000),
    ('megapixel-1g',   12, 60, 401000),
    ('megapixel-1g',   12, 240, 87000),
    ('megapixel-2.5g', 10, 24, 3094000),
    ('megapixel-2.5g', 10, 60, 1205000),
    ('megapixel-2.5g', 10, 240, 261000),
    ('megapixel-2.5g', 12, 24, 2578000),
    ('megapixel-2.5g', 12, 60, 1004000),
    ('megapixel-2.5g', 12, 240, 218000),
]


@pytest.mark.parametrize("processor,bit_depth,frame_rate,expected", MEGAPIXEL_K14)
def test_megapixel_port_capacity_matches_appendix_k14(
        page, processor, bit_depth, frame_rate, expected):
    """Pin Megapixel HELIOS port capacities to the official user guide."""
    capacity = page.evaluate(
        "([b, f, p]) => window.app.calculatePortCapacity(b, f, p)",
        [bit_depth, frame_rate, processor])
    assert capacity == expected, (
        f"{processor} {bit_depth}-bit @{frame_rate}Hz: got {capacity}, "
        f"Appendix K.14 says {expected}")


def test_megapixel_tables_have_no_8bit_row(page):
    """Megapixel publishes no 8-bit HELIOS figures; an invented row would
    silently hand out capacities that do not exist in any spec."""
    keys = page.evaluate("""() => {
        const t = window.app.portCapacityTables;
        return {
            g1: Object.keys(t['megapixel-1g']),
            g25: Object.keys(t['megapixel-2.5g'])
        };
    }""")
    assert keys['g1'] == ['10', '12'], keys
    assert keys['g25'] == ['10', '12'], keys


def test_port_mapping_buttons_live_for_armor(page):
    """Both Port Mapping buttons stay live on an Armor layer (they used to be
    greyed out with pointer events off, so Max Capacity was unreachable)."""
    state = page.evaluate("""() => {
        const o = document.getElementById('mapping-organized');
        const m = document.getElementById('mapping-max-capacity');
        const saved = window.app.currentLayer;
        // Force a stale greyed state first so a no-op would be caught.
        o.style.opacity = '0.5'; o.style.pointerEvents = 'none';
        m.style.opacity = '0.5'; m.style.pointerEvents = 'none';
        window.app.currentLayer = {
            type: 'screen', rows: 2, columns: 2, cabinet_width: 200,
            cabinet_height: 200, panels: [], processorType: 'novastar-armor',
            portMappingMode: 'max-capacity', flowPattern: 'tl-h',
            bitDepth: 8, frameRate: 60
        };
        window.app.updatePortCapacityDisplay();
        const out = {
            orgOpacity: o.style.opacity, maxOpacity: m.style.opacity,
            orgEvents: o.style.pointerEvents, maxEvents: m.style.pointerEvents,
            orgTitle: o.title, maxTitle: m.title,
            // v0.10.9: the theme's !important rules mean the .active CLASS is
            // the highlight. Reading o.style.background here passed even while
            // the button rendered unhighlighted -- never assert on it.
            orgActive: o.classList.contains('active'),
            maxActive: m.classList.contains('active')
        };
        window.app.currentLayer = saved;
        window.app.updatePortCapacityDisplay();
        return out;
    }""")
    assert state['orgOpacity'] == '1' and state['maxOpacity'] == '1', state
    assert state['orgEvents'] == 'auto' and state['maxEvents'] == 'auto', state
    assert 'always uses rectangle-based mapping' not in state['orgTitle']
    assert 'rectangle' in state['maxTitle'].lower(), state['maxTitle']
    # Armor now reflects the layer's real mode instead of a forced Organized.
    assert state['maxActive'] and not state['orgActive'], state


def test_port_mapping_buttons_not_latched_by_early_return(page):
    """updatePortCapacityDisplay() leaves the buttons live even when it bails
    out early (no current layer / image layer)."""
    state = page.evaluate("""() => {
        const o = document.getElementById('mapping-organized');
        const m = document.getElementById('mapping-max-capacity');
        // Force a stale greyed state, then take the no-current-layer path.
        o.style.opacity = '0.5'; o.style.pointerEvents = 'none';
        m.style.opacity = '0.5'; m.style.pointerEvents = 'none';
        const saved = window.app.currentLayer;
        window.app.currentLayer = null;
        window.app.updatePortCapacityDisplay();
        const afterNull = { o: o.style.opacity, m: m.style.opacity };
        // And again via the image-layer path.
        o.style.opacity = '0.5'; m.style.opacity = '0.5';
        window.app.currentLayer = { type: 'image' };
        window.app.updatePortCapacityDisplay();
        const afterImage = { o: o.style.opacity, m: m.style.opacity };
        window.app.currentLayer = saved;
        window.app.updatePortCapacityDisplay();
        return { afterNull, afterImage };
    }""")
    assert state['afterNull'] == {'o': '1', 'm': '1'}, state
    assert state['afterImage'] == {'o': '1', 'm': '1'}, state


# ── Port Mapping highlight (v0.10.9) ─────────────────────────────────────
# theme.css styles .mapping-mode-btn and .mapping-mode-btn.active with
# !important, so the ONLY thing that can move the highlight is the .active
# class -- inline background/color writes are painted over. These tests
# therefore assert on classList and getComputedStyle. Asserting on
# el.style.background is what let the broken highlight ship: the inline value
# read back correctly while the button rendered unhighlighted.

MAPPING_HIGHLIGHT_JS = """() => {
    const o = document.getElementById('mapping-organized');
    const m = document.getElementById('mapping-max-capacity');
    const paint = el => {
        const cs = getComputedStyle(el);
        // background is a gradient here, so backgroundColor alone is
        // transparent in BOTH states -- fold in the image and text colour.
        return cs.backgroundImage + ' | ' + cs.backgroundColor + ' | ' + cs.color;
    };
    return {
        orgActive: o.classList.contains('active'),
        maxActive: m.classList.contains('active'),
        orgPaint: paint(o),
        maxPaint: paint(m)
    };
}"""


def mapping_highlight(page):
    return page.evaluate(MAPPING_HIGHLIGHT_JS)


def use_screen_for_mapping(page, processor):
    """Show the Data view with one screen layer selected on `processor`,
    reset to Organized. Returns the layer id so tests can re-select it."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(400)
    layer_id = page.evaluate("""(processor) => {
        const app = window.app;
        const screen = app.project.layers.find(
            l => (l.type || 'screen') === 'screen' && l.visible !== false);
        if (!screen) throw new Error('no screen layer available');
        screen.processorType = processor;
        screen.portMappingMode = 'organized';
        app.selectLayer(screen);
        return screen.id;
    }""", processor)
    page.wait_for_timeout(400)
    return layer_id


@pytest.mark.parametrize('processor', ['novastar-armor', 'brompton'])
def test_port_mapping_click_moves_active_class(page, processor):
    """Clicking Max Capacity moves the .active class off Organized, and the
    two buttons then paint differently. Both buttons used to keep whatever
    class the template hardcoded, so Organized stayed lit forever."""
    use_screen_for_mapping(page, processor)

    start = mapping_highlight(page)
    assert start['orgActive'] and not start['maxActive'], start

    page.locator('#mapping-max-capacity').click()
    page.wait_for_timeout(500)
    after_max = mapping_highlight(page)
    assert after_max['maxActive'], f"{processor}: Max Capacity not active: {after_max}"
    assert not after_max['orgActive'], f"{processor}: Organized still active: {after_max}"
    assert after_max['maxPaint'] != after_max['orgPaint'], (
        f"{processor}: both buttons render identically: {after_max}")
    assert page.evaluate("window.app.currentLayer.portMappingMode") == 'max-capacity'

    # ... and back again.
    page.locator('#mapping-organized').click()
    page.wait_for_timeout(500)
    after_org = mapping_highlight(page)
    assert after_org['orgActive'], f"{processor}: Organized not re-activated: {after_org}"
    assert not after_org['maxActive'], f"{processor}: Max Capacity still active: {after_org}"
    assert after_org['orgPaint'] != after_org['maxPaint'], after_org
    assert page.evaluate("window.app.currentLayer.portMappingMode") == 'organized'


@pytest.mark.parametrize('processor', ['novastar-armor', 'brompton'])
def test_port_mapping_highlight_follows_selected_layer(page, processor):
    """Selecting a layer stored as max-capacity lights Max Capacity
    (loadLayerToInputs path), and re-selecting an organized layer flips back."""
    layer_id = use_screen_for_mapping(page, processor)

    page.evaluate("""(id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        layer.portMappingMode = 'max-capacity';
        app.selectLayer(layer);
    }""", layer_id)
    page.wait_for_timeout(400)
    state = mapping_highlight(page)
    assert state['maxActive'] and not state['orgActive'], f"{processor}: {state}"
    assert state['maxPaint'] != state['orgPaint'], state

    page.evaluate("""(id) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === id);
        layer.portMappingMode = 'organized';
        app.selectLayer(layer);
    }""", layer_id)
    page.wait_for_timeout(400)
    state = mapping_highlight(page)
    assert state['orgActive'] and not state['maxActive'], f"{processor}: {state}"


def test_perspective_buttons_highlight_by_class(page):
    """Front/Back share the same !important theme rules as Port Mapping.
    They already toggle .active -- lock that in so they can't regress to
    inline styles."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(300)
    read = """() => {
        const f = document.getElementById('data-flow-perspective-front');
        const b = document.getElementById('data-flow-perspective-back');
        const paint = el => {
            const cs = getComputedStyle(el);
            return cs.backgroundImage + ' | ' + cs.color;
        };
        return {
            frontActive: f.classList.contains('active'),
            backActive: b.classList.contains('active'),
            frontPaint: paint(f), backPaint: paint(b)
        };
    }"""
    page.locator('#data-flow-perspective-back').click()
    page.wait_for_timeout(600)
    state = page.evaluate(read)
    assert state['backActive'] and not state['frontActive'], state
    assert state['backPaint'] != state['frontPaint'], state

    page.locator('#data-flow-perspective-front').click()
    page.wait_for_timeout(600)
    state = page.evaluate(read)
    assert state['frontActive'] and not state['backActive'], state


def test_flow_pattern_buttons_highlight_by_class(page):
    """Data Flow pattern tiles carry the same !important theme rules; they
    already toggle .active. Guard against an inline-style regression."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(300)
    page.locator('.flow-pattern-btn[data-pattern="bl-v"]:not(.power-flow-pattern-btn)').click()
    page.wait_for_timeout(500)
    state = page.evaluate("""() => {
        const btns = [...document.querySelectorAll(
            '.flow-pattern-btn:not(.power-flow-pattern-btn)')];
        const active = btns.filter(b => b.classList.contains('active'));
        const other = btns.find(b => !b.classList.contains('active'));
        const paint = el => getComputedStyle(el).backgroundImage;
        return {
            activePatterns: active.map(b => b.getAttribute('data-pattern')),
            activePaint: active.length ? paint(active[0]) : null,
            otherPaint: other ? paint(other) : null
        };
    }""")
    assert state['activePatterns'] == ['bl-v'], state
    assert state['activePaint'] != state['otherPaint'], state
    # Hand the shared page back on Pixel Map, the tab the later tests expect
    # (Screen Info's inputs are hidden while the Data view is up).
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)


# ── Armor Port Mapping normalization on project load (v0.10.9) ───────────


def armor_fixture_project(flows_server, name):
    """A saved-project payload with one Armor/max-capacity screen, one
    Armor/organized screen, and one Brompton/max-capacity screen.

    Built from the live project so every other field is shaped exactly as the
    app writes it (canvas_id, panels, colors, ...).
    """
    import json
    import urllib.request

    with urllib.request.urlopen(flows_server + '/api/project') as resp:
        project = json.load(resp)
    base = project['layers'][0]

    def clone(layer_id, layer_name, processor, mode):
        layer = json.loads(json.dumps(base))
        layer.update({
            'id': layer_id, 'name': layer_name,
            'processorType': processor, 'portMappingMode': mode,
        })
        return layer

    project['name'] = name
    project['layers'] = [
        clone(901, 'ArmorMax', 'novastar-armor', 'max-capacity'),
        clone(902, 'ArmorOrg', 'novastar-armor', 'organized'),
        clone(903, 'BromptonMax', 'brompton', 'max-capacity'),
    ]
    return project


def modes_by_name(page, source='project'):
    src = ('window.app.project' if source == 'project'
           else 'window.app.history[0].project')
    return page.evaluate(
        "() => Object.fromEntries(%s.layers.map("
        "l => [l.name, l.portMappingMode]))" % src)


def test_normalize_armor_port_mapping_only_touches_armor_max_capacity(page):
    """The normalizer rewrites Armor+max-capacity and nothing else."""
    result = page.evaluate("""() => {
        const project = { layers: [
            { id: 1, type: 'screen', processorType: 'novastar-armor',
              portMappingMode: 'max-capacity' },
            { id: 2, type: 'screen', processorType: 'novastar-armor',
              portMappingMode: 'organized' },
            { id: 3, type: 'screen', processorType: 'brompton',
              portMappingMode: 'max-capacity' },
            { id: 4, type: 'screen', processorType: 'novastar-5g',
              portMappingMode: 'max-capacity' },
            { id: 5, type: 'image', processorType: 'novastar-armor',
              portMappingMode: 'max-capacity' },
            { id: 6, type: 'screen', processorType: 'novastar-armor' },
        ]};
        return {
            changed: window.app.normalizeArmorPortMapping(project),
            modes: project.layers.map(l => l.portMappingMode || null),
            nullProject: window.app.normalizeArmorPortMapping(null),
            noLayers: window.app.normalizeArmorPortMapping({}),
        };
    }""")
    assert result['changed'] == 1, result
    assert result['modes'] == [
        'organized',      # Armor + max-capacity -> normalized
        'organized',      # Armor + organized -> untouched
        'max-capacity',   # Brompton -> untouched
        'max-capacity',   # NovaStar 5G -> untouched
        'max-capacity',   # image layer -> untouched
        None,             # no mode set -> left alone
    ], result
    assert result['nullProject'] == 0 and result['noLayers'] == 0, result


def test_armor_max_capacity_survives_undo(page):
    """Undo must NOT re-run the load-time normalization.

    Deliberately choosing Max Capacity on an Armor screen and then undoing a
    LATER edit has to leave Max Capacity in place.
    """
    page.evaluate("""() => {
        window.app.selectLayer(window.app.project.layers[0]);
        const sel = document.getElementById('processor-type');
        sel.value = 'novastar-armor';
        sel.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_timeout(500)
    page.evaluate("document.getElementById('mapping-max-capacity').click()")
    page.wait_for_timeout(600)
    assert page.evaluate(
        "window.app.project.layers[0].portMappingMode") == 'max-capacity'

    # A later, unrelated edit, so undo steps back ONTO the Max Capacity state.
    before_cols = page.evaluate("window.app.project.layers[0].columns")
    cols = page.locator('#screen-columns')
    cols.fill(str(before_cols + 1))
    cols.dispatch_event('change')
    page.wait_for_timeout(600)

    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(900)
    state = page.evaluate("""() => {
        const l = window.app.project.layers[0];
        return { mode: l.portMappingMode, processor: l.processorType,
                 columns: l.columns };
    }""")
    assert state['columns'] == before_cols, (
        f"undo did not step back (columns {state['columns']})")
    assert state['processor'] == 'novastar-armor', state
    assert state['mode'] == 'max-capacity', (
        "undo reverted a deliberate Max Capacity choice on an Armor screen")


def test_armor_max_capacity_normalized_on_file_open(page, flows_server, tmp_path):
    """File > Open rewrites Armor+max-capacity to organized, and the first
    undo snapshot already carries the corrected mode."""
    import json

    project = armor_fixture_project(flows_server, 'ArmorFixtureOpen')
    path = tmp_path / 'armor_fixture.json'
    path.write_text(json.dumps(project))

    with page.expect_file_chooser() as chooser:
        page.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    page.wait_for_function(
        "() => window.app.project"
        " && window.app.project.name === 'ArmorFixtureOpen'"
        " && window.app.project.layers.length === 3",
        timeout=10000)
    page.wait_for_timeout(800)

    modes = modes_by_name(page)
    assert modes['ArmorMax'] == 'organized', (
        f"Armor max-capacity was not normalized on load: {modes}")
    assert modes['ArmorOrg'] == 'organized', modes
    assert modes['BromptonMax'] == 'max-capacity', (
        f"a non-Armor processor was normalized: {modes}")

    # resetHistory('Initial State') ran after the fix-up, so undoing back to
    # the start cannot resurrect the bogus mode.
    assert modes_by_name(page, source='history') == modes


def test_armor_max_capacity_normalized_on_recent_file_load(page, flows_server):
    """The Recent Files path normalizes too (it does not share the file-open
    code, so it needs its own hook)."""
    project = armor_fixture_project(flows_server, 'ArmorFixtureRecent')
    page.evaluate("""(project) => {
        localStorage.setItem('ledRasterRecentFiles', JSON.stringify([{
            name: project.name, timestamp: Date.now(),
            layerCount: project.layers.length, data: project
        }]));
    }""", project)
    page.evaluate("window.app.loadRecentFile(0)")
    page.wait_for_function(
        "() => window.app.project"
        " && window.app.project.name === 'ArmorFixtureRecent'"
        " && window.app.project.layers.length === 3",
        timeout=10000)
    page.wait_for_timeout(800)

    modes = modes_by_name(page)
    assert modes['ArmorMax'] == 'organized', modes
    assert modes['ArmorOrg'] == 'organized', modes
    assert modes['BromptonMax'] == 'max-capacity', modes
    assert modes_by_name(page, source='history') == modes

    # Leave the shared server/page on a clean project for anything after us.
    page.evaluate("localStorage.removeItem('ledRasterRecentFiles')")
    page.evaluate("window.app.createNewProject()")
    page.wait_for_timeout(800)


# ── Per-layer Low Latency (v0.10.9) ──────────────────────────────────────
# Low latency is not one number: it is a different behaviour per processor
# family. Brompton ULL halves pixels-per-port; Megapixel HELIOS costs no
# capacity at all; NovaStar is GEOMETRIC -- a 512 px port width cap on every
# line, plus a (1 - Y/H) derate applied per port on COEX ONLY, never to the
# table. NovaStar Legacy has the width cap and no positional term. An
# over-generous port map is a dark wall, so every assertion below prefers the
# conservative result.


def test_brompton_low_latency_reproduces_legacy_ull_table(page):
    """The lossless-migration proof.

    'brompton-ull' used to be its own 48-cell table. It is now brompton +
    lowLatency, so every published cell has to come back out the other side.
    We floor the halves; Brompton's own manual rounds two 12-bit cells UP by
    1 px, so we may land 1 px LOW there and must never land high --
    understating a port's capacity is safe, overstating it goes dark.
    """
    rows = page.evaluate("""() => {
        const legacy = window.app.portCapacityTables['brompton-ull'];
        const out = [];
        Object.keys(legacy).forEach(bd => {
            Object.keys(legacy[bd]).forEach(fr => {
                out.push({
                    bitDepth: Number(bd), frameRate: Number(fr),
                    legacy: legacy[bd][fr],
                    migrated: window.app.calculatePortCapacity(
                        Number(bd), Number(fr), 'brompton', true),
                    normal: window.app.calculatePortCapacity(
                        Number(bd), Number(fr), 'brompton', false)
                });
            });
        });
        return out;
    }""")
    assert len(rows) == 48, f"expected the 48 published cells, got {len(rows)}"

    off_by_one = []
    for row in rows:
        cell = (row['bitDepth'], row['frameRate'])
        delta = row['migrated'] - row['legacy']
        assert delta <= 0, (
            f"{cell}: brompton+lowLatency gives {row['migrated']} px, the "
            f"legacy ULL table gives {row['legacy']} px -- over-counting a port")
        if delta:
            off_by_one.append((cell, delta))
        # And it really is the normal column halved, not a second table.
        assert row['migrated'] * 2 in (row['normal'], row['normal'] - 1), row

    # The only permitted drift, documented in the descriptor: Brompton rounds
    # these two cells up. Anything else here means the migration lost data.
    assert {c for c, _ in off_by_one} == {(12, 144), (12, 192)}, off_by_one
    assert all(d == -1 for _, d in off_by_one), off_by_one


@pytest.mark.parametrize('processor', ['megapixel-1g', 'megapixel-2.5g'])
def test_megapixel_low_latency_costs_no_capacity(page, processor):
    """HELIOS Tile LL + Processor LL cost daisy-chain length, not pixels."""
    rows = page.evaluate("""([p]) => [[10, 60], [12, 24], [12, 240]].map(
        ([b, f]) => ({
            bitDepth: b, frameRate: f,
            off: window.app.calculatePortCapacity(b, f, p, false),
            on: window.app.calculatePortCapacity(b, f, p, true)
        }))""", [processor])
    for row in rows:
        assert row['off'] > 0, row
        assert row['on'] == row['off'], f"{processor} derated capacity: {row}"


@pytest.mark.parametrize('processor', [
    # NovaStar's own answer: the 512 px single-port loading width is REMOVED in
    # current firmware (NovaPro UHD Jr, MCTRL4K, MCTRL660 Pro) and the manuals
    # are being revised, so no descriptor may carry a width cap. Top alignment
    # and the vertical cabinet formula apply to "any novastar product including
    # legacy and coex", so every line derates.
    'novastar-armor',
    'novastar-coex-1g',
    'novastar-5g',
])
def test_novastar_low_latency_leaves_the_capacity_table_alone(page, processor):
    """The NovaStar behaviour is GEOMETRIC, so the table lookup is the port's
    TOTAL and must come back untouched from the capacity path. Substituting a
    fixed constant here (659,722 / 2,592,000) would freeze the derate at 8-bit
    60 Hz; the geometry is applied per port in calculatePortAssignments."""
    state = page.evaluate("""(p) => {
        const profile = window.app.getLowLatencyProfile(p);
        return {
            pending: window.app.isLowLatencyCapacityPending(p),
            kind: profile.capacity.kind,
            hasWidthCap: 'maxPortWidth' in profile.capacity,
            yDerate: profile.capacity.yDerate,
            note: profile.note,
            cards: profile.cards,
            table: window.app.lookupPortCapacity(8, 60, p),
            off: window.app.calculatePortCapacity(8, 60, p, false),
            on: window.app.calculatePortCapacity(8, 60, p, true)
        };
    }""", processor)
    assert state['pending'] is False, state
    assert state['kind'] == 'novastar-ll', state
    assert state['hasWidthCap'] is False, (
        f"{processor}: the retired 512 px width cap is back: {state}")
    assert state['yDerate'] is True, state
    assert state['off'] == state['table'] > 0, state
    assert state['on'] == state['table'], (
        f"{processor}: the geometric behaviour leaked into the table: {state}")
    assert state['note'], 'the behaviour still has to explain itself'
    # The note states the rule that actually applies now, and nothing about a
    # width cap that no longer exists.
    assert '512' not in state['note'], state
    assert 'vertically' in state['note'], state
    assert 'top of the canvas' in state['note'], state
    # The card trap is the one worth surfacing in the note itself; the full
    # supported list rides along as the tooltip.
    assert 'MRV328 and MRV336' in state['note'], state
    for card in ('A5S Plus', 'A5S Plus-N', 'A8S', 'A8S-N', 'A8S Pro',
                 'A10S Plus', 'A10S Plus-N', 'A10S Pro', 'MRV208-N',
                 'MRV412-N', 'MRV416-N'):
        assert card in state['cards'], (card, state['cards'])
    assert 'MRV328 and MRV336 do NOT support low latency' in state['cards'], state


def test_low_latency_card_list_is_the_note_tooltip(page):
    """We do not model receiving cards, so the list is UI text: it reaches the
    user as the note's tooltip, and only on the NovaStar lines that have one."""
    state = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        const prev = layer.processorType;
        const read = (p) => {
            layer.processorType = p;
            app.selectLayer(layer);
            return document.getElementById('low-latency-note').title;
        };
        const out = {
            armor: read('novastar-armor'),
            coex: read('novastar-coex-1g'),
            fiveG: read('novastar-5g'),
            brompton: read('brompton')
        };
        layer.processorType = prev;
        app.selectLayer(layer);
        return out;
    }""")
    assert state['armor'] == state['coex'] == state['fiveG'], state
    assert 'MRV416-N' in state['armor'], state
    assert 'MRV328 and MRV336 do NOT support low latency' in state['armor'], state
    assert state['brompton'] == '', state


def test_novastar_5g_total_is_the_table_value(page):
    """5G TOTAL comes from NovaStar's published Ethernet Port Load Capacity
    table (XA50 Pro / CA50E), confirmed direct with NovaStar. Their formula is
    capacity x 24 x fps < 5G x 0.85 for 8-bit, x32 / 0.88 for 10-bit and
    x48 / 0.85 for 12-bit -- note 24/32/48, NOT bitDepth x 3. We previously
    used x36 for 12-bit, which overstated it by ~17%. Pinned per bit depth so
    a future edit cannot quietly move any of them back."""
    caps = page.evaluate("""() => ({
        b8:  window.app.lookupPortCapacity(8, 60, 'novastar-5g'),
        b10: window.app.lookupPortCapacity(10, 60, 'novastar-5g'),
        b12: window.app.lookupPortCapacity(12, 60, 'novastar-5g')
    })""")
    assert caps['b8'] == 2951200
    assert caps['b10'] == 2291312
    assert caps['b12'] == 1475600
    # The published table is internally consistent: capacity x mult x fps is a
    # constant per bit depth. Re-derive it rather than trusting the cells alone.
    for bits, mult, cap in ((8, 24, caps['b8']), (10, 32, caps['b10']), (12, 48, caps['b12'])):
        efficiency = (cap * mult * 60) / 5e9
        expected = 0.88 if bits == 10 else 0.85
        assert abs(efficiency - expected) < 0.005, (bits, efficiency)


def test_implemented_low_latency_behaviours_are_not_flagged_pending(page):
    """The flag is about the MATH shipping, not about the derate being zero:
    Megapixel derates nothing and is still fully implemented, and the NovaStar
    geometry ships in calculatePortAssignments rather than in the lookup."""
    flags = page.evaluate("""() => ({
        brompton: window.app.isLowLatencyCapacityPending('brompton'),
        'megapixel-1g': window.app.isLowLatencyCapacityPending('megapixel-1g'),
        'megapixel-2.5g': window.app.isLowLatencyCapacityPending('megapixel-2.5g'),
        'novastar-armor': window.app.isLowLatencyCapacityPending('novastar-armor'),
        'novastar-coex-1g': window.app.isLowLatencyCapacityPending('novastar-coex-1g'),
        'novastar-5g': window.app.isLowLatencyCapacityPending('novastar-5g')
    })""")
    assert flags == {
        'brompton': False, 'megapixel-1g': False, 'megapixel-2.5g': False,
        'novastar-armor': False, 'novastar-coex-1g': False,
        'novastar-5g': False}, flags


@pytest.mark.parametrize('processor,pending', [
    ('brompton', False),
    ('megapixel-1g', False),
    ('novastar-5g', False),
    ('novastar-armor', False),
])
def test_low_latency_note_follows_processor(page, processor, pending):
    """The note beside the control is the descriptor's own text, plus a plain
    statement when the constraint is not in the figures yet."""
    state = page.evaluate("""(processor) => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        layer.processorType = processor;
        app.selectLayer(layer);
        return {
            note: document.getElementById('low-latency-note').textContent,
            profileNote: app.getLowLatencyProfile(processor).note,
            disabled: document.getElementById('low-latency').disabled
        };
    }""", processor)
    assert state['profileNote'] in state['note'], state
    assert state['disabled'] is False, state
    assert ('Not applied to the figures below yet.' in state['note']) is pending, state


# ── NovaStar Low Latency port geometry (v0.10.9, pass 2) ─────────────────
# calculatePortAssignments is the only thing that knows where a port sits, so
# it owns the NovaStar geometry rule. There is exactly ONE rule now: a port's
# capacity is (1 - Y/H) * TOTAL, where TOTAL is the plain table lookup at the
# CURRENT bit depth and frame rate and Y is the port's topmost cabinet. It
# applies to EVERY NovaStar line, legacy and COEX -- NovaStar's own answer,
# which also retired the 512 px port-width cap we used to enforce.
# Every assertion below regroups the EMITTED flat assignment list by .port and
# recomputes the geometry from the panels, so it tests the shipped map rather
# than the internal bookkeeping that produced it.

LL_PORT_MAP_JS = """(spec) => {
    const app = window.app;
    const hiddenSet = new Set((spec.hidden || []).map(rc => rc[0] + ',' + rc[1]));
    const offsetX = spec.offsetX || 0;
    const offsetY = spec.offsetY || 0;
    const panels = [];
    let n = 1;
    for (let r = 0; r < spec.rows; r++) {
        for (let c = 0; c < spec.columns; c++) {
            panels.push({
                id: n, number: n, row: r, col: c,
                // Panel x/y are canvas-relative and already carry the layer
                // offset, exactly as the server builds them.
                x: offsetX + c * spec.cw, y: offsetY + r * spec.ch,
                width: spec.cw, height: spec.ch,
                hidden: hiddenSet.has(r + ',' + c), blank: false, halfTile: 'none'
            });
            n++;
        }
    }
    // A throwaway canvas so H is exactly what the test says it is, removed
    // again before we return so the shared page keeps its own project.
    const canvasId = '__ll_test_canvas__';
    const prevCanvases = app.project.canvases;
    app.project.canvases = (prevCanvases || []).concat([{
        id: canvasId, name: 'LL test',
        raster_width: spec.canvasWidth || 4096,
        raster_height: spec.canvasHeight || 2160
    }]);
    const layer = {
        id: -1, type: 'screen', rows: spec.rows, columns: spec.columns,
        cabinet_width: spec.cw, cabinet_height: spec.ch, panels,
        canvas_id: canvasId, offset_x: offsetX, offset_y: offsetY,
        processorType: spec.processorType,
        portMappingMode: spec.mode || 'organized',
        flowPattern: spec.pattern || 'tl-h',
        bitDepth: spec.bitDepth || 8,
        frameRate: spec.frameRate || 60
    };
    if (spec.lowLatency !== null) layer.lowLatency = !!spec.lowLatency;
    let assignments;
    try {
        assignments = app.calculatePortAssignments(layer);
    } finally {
        app.project.canvases = prevCanvases;
    }

    const byPort = new Map();
    assignments.forEach(a => {
        if (!byPort.has(a.port)) byPort.set(a.port, []);
        byPort.get(a.port).push(a.panel);
    });
    const ports = Array.from(byPort.keys()).sort((a, b) => a - b).map(p => {
        const ps = byPort.get(p);
        const minX = Math.min.apply(null, ps.map(q => q.x));
        const maxX = Math.max.apply(null, ps.map(q => q.x + q.width));
        const minY = Math.min.apply(null, ps.map(q => q.y));
        const maxY = Math.max.apply(null, ps.map(q => q.y + q.height));
        const rowsByCol = {};
        ps.forEach(q => { (rowsByCol[q.col] = rowsByCol[q.col] || []).push(q.row); });
        return {
            port: p,
            panels: ps.length,
            cols: Object.keys(rowsByCol).map(Number).sort((a, b) => a - b),
            rowsByCol: rowsByCol,
            width: maxX - minX,
            minY: minY,
            rectArea: (maxX - minX) * (maxY - minY),
            pixelSum: ps.reduce((s, q) => s + q.width * q.height, 0)
        };
    });
    return {
        total: app.lookupPortCapacity(
            layer.bitDepth, layer.frameRate, layer.processorType),
        ports: ports,
        // The full flat emission, for the byte-identical regression guard.
        flat: assignments.map(a => [a.port, a.panel.row, a.panel.col,
                                    a.isPortStart, a.pixelIndex]),
        totalPanels: assignments.length,
        error: !!layer._capacityError,
        errorInfo: layer._capacityError || null,
        derate: layer._lowLatencyDerate || null
    };
}"""


def ll_port_map(page, **spec):
    spec.setdefault('cw', 128)
    spec.setdefault('ch', 128)
    spec.setdefault('lowLatency', True)
    spec.setdefault('processorType', 'novastar-5g')
    return page.evaluate(LL_PORT_MAP_JS, spec)


def ll_capacity(total, min_y, canvas_height):
    """(1 - Y/H) * TOTAL, floored -- the same operations in the same order as
    lowLatencyPortCapacity, so the two land on the same double."""
    return int(min(1.0, max(0.0, 1 - (min_y / canvas_height))) * total)


def ll_fits(capacity, panel_pixels=128 * 128):
    """Cabinets one port of `capacity` px can carry. The 5G table figures are
    revised on their own schedule, so the tests below derive their splits from
    the TOTAL the app reports instead of pinning the manufacturer's number."""
    return capacity // panel_pixels


def assert_ll_ports_legal(result, canvas_height, label, uses_rectangle=False):
    """Independent re-check of every rule against the emitted map.

    Every NovaStar line derates now, so there is no y_derate switch left."""
    assert not result['error'], f"{label}: unexpected capacity error {result['errorInfo']}"
    assert result['ports'], f"{label}: no ports emitted"
    for p in result['ports']:
        # The traversal is the layer's FLOW PATTERN run over the whole screen,
        # and every one of the eight is a serpentine, so a port is an unbroken
        # run either way you slice it: the grid columns it touches are adjacent
        # and the rows it takes from each are contiguous. Width is NOT checked
        # -- the 512 px cap is gone.
        assert p['cols'] == list(range(p['cols'][0], p['cols'][-1] + 1)), (
            f"{label}: port {p['port']} skips a column: {p['cols']}")
        for col, rows in p['rowsByCol'].items():
            got = sorted(rows)
            assert got == list(range(got[0], got[-1] + 1)), (
                f"{label}: port {p['port']} column {col} is not vertically "
                f"contiguous: {got}")
        cap = ll_capacity(result['total'], p['minY'], canvas_height)
        load = p['rectArea'] if uses_rectangle else p['pixelSum']
        assert load <= cap, (
            f"{label}: port {p['port']} carries {load} px against a derated "
            f"capacity of {cap} px -- this map would go dark")


@pytest.mark.parametrize('cw,columns,rows', [
    # These three used to be split into 512 px bands: 2, 4 and 3 ports.
    (128, 8, 4),    # 1,024 px wide
    (256, 8, 2),    # 2,048 px wide
    (200, 6, 2),    # 1,200 px wide
])
def test_low_latency_ports_are_no_longer_width_capped(page, cw, columns, rows):
    """INVERTED from test_low_latency_ports_stay_within_512_px. NovaStar told
    us the 512 px single-port loading width is removed in current firmware and
    the manuals are wrong, so nothing may cap a port by width: a wide wall that
    fits the pixel budget is ONE port, however many pixels across it is."""
    r = ll_port_map(page, rows=rows, columns=columns, cw=cw, ch=cw,
                    canvasHeight=2160)
    assert_ll_ports_legal(r, 2160, f'5G LL {columns}x{rows} @{cw}px')
    assert len(r['ports']) == 1, [p['panels'] for p in r['ports']]
    assert r['ports'][0]['width'] == columns * cw > 512, r['ports']
    assert r['totalPanels'] == columns * rows


def test_low_latency_column_wider_than_512_px_maps_fine(page):
    """INVERTED from test_low_latency_column_wider_than_the_cap_raises_capacity_error.
    A 600 px cabinet column had no legal band under the retired cap and raised
    a hard error; with the cap gone it is an ordinary port."""
    r = ll_port_map(page, rows=2, columns=2, cw=600, ch=200, canvasHeight=2160)
    assert not r['error'], r['errorInfo']
    assert len(r['ports']) == 1, r['ports']
    assert r['ports'][0]['width'] == 1200, r['ports']
    assert r['totalPanels'] == 4


def test_low_latency_oversized_cabinet_raises_capacity_error(page):
    """512x1400 = 716,800 px against an Armor port's 659,722 px. One cabinet
    that cannot be carried at all is still a hard error, not a bad map."""
    r = ll_port_map(page, rows=2, columns=2, cw=512, ch=1400,
                    processorType='novastar-armor', canvasHeight=4000)
    assert r['error'], 'an oversized cabinet emitted a map anyway'
    assert r['ports'] == []
    assert r['errorInfo']['unitType'] == 'panel', r['errorInfo']


def test_low_latency_cabinet_below_the_canvas_joins_the_port_above_it(page):
    """A cabinet past the bottom of the canvas has a (1 - Y/H) of its own that
    clamps to 0, but it is not opening the port -- it joins one that started at
    Y=0 and is judged by THAT port's capacity. Testing a lone cabinet first
    would fail a wall that simply hangs below the raster."""
    r = ll_port_map(page, rows=10, columns=4, canvasHeight=1080)
    assert_ll_ports_legal(r, 1080, '5G LL 4x10 overhanging the canvas')
    assert len(r['ports']) == 1, [p['panels'] for p in r['ports']]
    assert r['ports'][0]['panels'] == 40
    assert r['totalPanels'] == 40
    assert r['derate'] is None, r['derate']


def test_low_latency_at_y_zero_uses_the_plain_table_value(page):
    """Top-aligned columns: Y is 0, the factor is 1, and the port carries the
    full table figure -- floor(TOTAL / 16,384) of the 128 x 128 px cabinets.

    tl-v: a column serpentine down the wall, so both ports still reach row 0
    and neither is derated. The arithmetic below is the derate's, not the
    pattern's -- see the flow-pattern tests for what the other seven do."""
    r = ll_port_map(page, rows=50, columns=4, canvasHeight=6400, pattern='tl-v')
    fit = ll_fits(r['total'])
    assert 150 < fit < 200, (
        f"a 4 x 50 wall no longer splits inside its last column: {fit}")
    assert_ll_ports_legal(r, 6400, '5G LL 4x50 at Y=0')
    assert fit * 16384 <= r['total'] < (fit + 1) * 16384
    assert [p['panels'] for p in r['ports']] == [fit, 200 - fit], r['ports']
    assert [p['minY'] for p in r['ports']] == [0, 0], r['ports']
    assert r['ports'][0]['pixelSum'] == fit * 16384
    assert r['totalPanels'] == 200
    assert r['derate'] is None, (
        f"a top-aligned wall must not be derated: {r['derate']}")


def test_low_latency_screen_pushed_down_the_canvas_is_derated(page):
    """The same wall 640 px down an 8192 px canvas.

    factor   = 1 - 640/8192 = 0.921875
    capacity = floor(0.921875 * TOTAL)
    and the port carries floor(capacity / 16,384) cabinets.

    tl-v so the wall's own geometry is the only thing moving the numbers: a
    column serpentine brings every port back to the top of the wall, which
    isolates the OFFSET's derate from the derate a pattern picks up by
    starting its later ports further down.
    """
    r = ll_port_map(page, rows=50, columns=4, offsetY=640, canvasHeight=8192,
                    pattern='tl-v')
    derated = ll_capacity(r['total'], 640, 8192)
    fit = ll_fits(derated)
    assert derated < r['total'], (derated, r['total'])
    assert 150 < fit < 200, (
        f"a 4 x 50 wall no longer splits inside its last column: {fit}")
    assert fit * 16384 <= derated < (fit + 1) * 16384
    assert_ll_ports_legal(r, 8192, '5G LL 4x50 at Y=640')
    assert [p['panels'] for p in r['ports']] == [fit, 200 - fit], r['ports']
    assert [p['minY'] for p in r['ports']] == [640, 640], r['ports']
    assert r['ports'][0]['pixelSum'] == fit * 16384
    assert r['totalPanels'] == 200
    # ...and the same wall at Y=0 carries MORE per port, which is exactly the
    # surprise the on-screen note has to explain.
    top = ll_port_map(page, rows=50, columns=4, offsetY=0, canvasHeight=8192,
                      pattern='tl-v')
    assert top['ports'][0]['panels'] == ll_fits(top['total']) > fit, top['ports']
    assert r['derate'] == {
        'deratedPorts': 2, 'totalPorts': 2, 'canvasHeight': 8192,
        'worstCapacity': derated, 'portCapacity': r['total']}, r['derate']


@pytest.mark.parametrize('processor', ['novastar-coex-1g', 'novastar-5g'])
def test_coex_low_latency_still_derates_by_position(page, processor):
    """The (1 - Y/H) rule is the COEX wiki's, so BOTH COEX entries keep it: a
    wall 640 px down an 8192 px canvas carries less per port than the same wall
    at Y=0, and the figure the UI reports is exactly floor((1 - Y/H) * TOTAL)
    at the current bit depth and frame rate."""
    spec = dict(rows=50, columns=4, processorType=processor, canvasHeight=8192)
    top = ll_port_map(page, offsetY=0, **spec)
    down = ll_port_map(page, offsetY=640, **spec)
    assert top['total'] == down['total'] > 0, (top['total'], down['total'])
    assert_ll_ports_legal(top, 8192, f'{processor} LL at Y=0')
    assert_ll_ports_legal(down, 8192, f'{processor} LL at Y=640')

    # The top-aligned wall's FIRST port starts at Y=0 and gets the plain table
    # figure. (Later ports on a tall wall start further down and are derated in
    # their own right, which is the formula doing its job, not the offset.)
    assert top['ports'][0]['minY'] == 0, top['ports'][0]
    assert down['ports'][0]['minY'] == 640, down['ports'][0]
    assert ll_capacity(top['total'], 640, 8192) < top['total']
    # Every derated port reports exactly floor((1 - minY/H) * TOTAL), and the
    # note quotes the worst of them.
    derated = [p for p in down['ports'] if p['minY'] > 0]
    assert derated, down['ports']
    worst = min(ll_capacity(down['total'], p['minY'], 8192) for p in derated)
    assert down['derate'] == {
        'deratedPorts': len(derated), 'totalPorts': len(down['ports']),
        'canvasHeight': 8192, 'worstCapacity': worst,
        'portCapacity': down['total']}, down['derate']
    # The first port is the one the derate actually bites on: fewer cabinets
    # than the same port carries at the top of the canvas.
    assert down['ports'][0]['panels'] < top['ports'][0]['panels'], (
        f"{processor}: the derate did not reach the map")


def test_legacy_low_latency_derates_by_vertical_position(page):
    """INVERTED from test_legacy_low_latency_ignores_vertical_position.
    NovaStar: "for any novastar product including legacy and coex, when
    low-latency mode is enabled, the screen connection must meet the required
    conditions, including top alignment and vertical cabinet formula". So the
    legacy line derates too, and moving a legacy screen down the canvas MUST
    change its map.

    20 rows of 128 px = 2,560 px tall, tl-v so the reserved Armor rectangle
    grows a COLUMN at a time.

    Y = 0:      capacity = 659,722 px.
                1 column  = 128 x 2,560 =   327,680  fits
                2 columns = 256 x 2,560 =   655,360  fits
                3 columns = 384 x 2,560 =   983,040  does not
                -> 2 ports of 40 cabinets, 655,360 px each.

    Y = 3,000 on an 8,192 px canvas:
                factor   = 1 - 3000/8192 = 0.6337890625
                capacity = floor(0.6337890625 x 659,722) = 418,124 px
                1 column  = 327,680  fits
                2 columns = 655,360  does not
                -> 4 ports of 20 cabinets, 327,680 px each."""
    spec = dict(rows=20, columns=4, cw=128, ch=128, pattern='tl-v',
                processorType='novastar-armor', canvasHeight=8192)
    top = ll_port_map(page, offsetY=0, **spec)
    down = ll_port_map(page, offsetY=3000, **spec)
    assert top['total'] == down['total'] == 659722, top['total']
    assert 2 * 128 * 2560 <= 659722 < 3 * 128 * 2560

    assert_ll_ports_legal(top, 8192, 'Legacy LL Y=0', uses_rectangle=True)
    assert [p['panels'] for p in top['ports']] == [40, 40], top['ports']
    assert [p['rectArea'] for p in top['ports']] == [655360, 655360], top
    assert [p['width'] for p in top['ports']] == [256, 256], top['ports']
    assert [p['minY'] for p in top['ports']] == [0, 0], top['ports']
    assert top['derate'] is None, top['derate']

    derated = ll_capacity(659722, 3000, 8192)
    assert derated == 418124, derated
    assert 128 * 2560 <= derated < 256 * 2560
    assert_ll_ports_legal(down, 8192, 'Legacy LL Y=3000', uses_rectangle=True)
    assert [p['panels'] for p in down['ports']] == [20, 20, 20, 20], down['ports']
    assert [p['rectArea'] for p in down['ports']] == [327680] * 4, down
    assert [p['width'] for p in down['ports']] == [128] * 4, down['ports']
    assert down['derate'] == {
        'deratedPorts': 4, 'totalPorts': 4, 'canvasHeight': 8192,
        'worstCapacity': 418124, 'portCapacity': 659722}, down['derate']

    assert top['flat'] != down['flat'], (
        'a legacy screen kept its port map after moving down the canvas')
    # ...and a legacy port is free to be wider than the retired 512 px cap:
    # 4 rows of 128 px are short enough that six columns share one port.
    wide = ll_port_map(page, rows=4, columns=8, cw=128, ch=128, offsetY=3000,
                       pattern='tl-v', processorType='novastar-armor',
                       canvasHeight=8192)
    assert_ll_ports_legal(wide, 8192, 'Legacy LL 8 columns', uses_rectangle=True)
    assert 6 * 128 * 512 <= derated < 7 * 128 * 512
    assert [p['width'] for p in wide['ports']] == [768, 256], wide['ports']
    assert [p['cols'] for p in wide['ports']] == [[0, 1, 2, 3, 4, 5], [6, 7]]


def test_low_latency_total_follows_bit_depth_not_a_constant(page):
    """A port's TOTAL is the table lookup at the CURRENT bit depth and frame
    rate, never a constant frozen at 8-bit/60: 10-bit 5G is smaller than 8-bit
    5G, and the first port shrinks to floor(TOTAL / 16,384) with it.

    tl-v keeps the first port's top edge at row 0, so the only thing moving
    that count is the table figure, which is what the test is about."""
    eight = ll_port_map(page, rows=50, columns=4, canvasHeight=6400,
                        pattern='tl-v')
    ten = ll_port_map(page, rows=50, columns=4, bitDepth=10, canvasHeight=6400,
                      pattern='tl-v')
    assert 0 < ten['total'] < eight['total'], (ten['total'], eight['total'])
    assert_ll_ports_legal(ten, 6400, '5G LL 10-bit')
    assert ten['ports'][0]['panels'] == ll_fits(ten['total']), ten['ports']
    assert ten['ports'][0]['panels'] < eight['ports'][0]['panels'], (
        '10-bit carried as much per port as 8-bit')

    # ...and with the frame rate, on the same table row.
    fast = ll_port_map(page, rows=50, columns=4, frameRate=120, canvasHeight=6400,
                       pattern='tl-v')
    assert 0 < fast['total'] < eight['total'], (fast['total'], eight['total'])
    assert_ll_ports_legal(fast, 6400, '5G LL 120 Hz')
    assert fast['ports'][0]['panels'] == ll_fits(fast['total']), fast['ports']
    assert len(fast['ports']) > len(eight['ports']), (
        '120 Hz needed no more ports than 60 Hz')


def test_low_latency_load_accounting_stays_per_processor(page):
    """Low latency changes the GEOMETRY, not how a port's load is measured.
    Armor and COEX 1G publish the same 659,722 px at 8-bit/60, so the same wall
    isolates the difference: Armor pays for the rectangle it reserves, COEX
    pays a pixel sum. 4 columns x 12 rows of 128 px with the top half of the
    last column removed -- 42 lit cabinets inside a 512 x 1536 footprint.

    tl-v so the rectangle grows one COLUMN at a time and the 384 px figure
    below is the one under test; the pixel sum is pattern-blind either way."""
    hidden = [[r, 3] for r in range(6)]
    armor = ll_port_map(page, rows=12, columns=4, hidden=hidden, pattern='tl-v',
                        processorType='novastar-armor', canvasHeight=2160)
    coex = ll_port_map(page, rows=12, columns=4, hidden=hidden, pattern='tl-v',
                       processorType='novastar-coex-1g', canvasHeight=2160)
    assert armor['total'] == coex['total'] == 659722, (armor['total'], coex['total'])
    assert_ll_ports_legal(armor, 2160, 'Armor LL', uses_rectangle=True)
    assert_ll_ports_legal(coex, 2160, 'COEX 1G LL')

    # Armor: three full columns reserve 384 x 1536 = 589,824 px; the fourth
    # would push the rectangle to 512 x 1536 = 786,432 px and cannot join.
    assert [p['panels'] for p in armor['ports']] == [36, 6], armor['ports']
    assert [p['rectArea'] for p in armor['ports']] == [589824, 98304], armor['ports']
    # COEX: 16,384 px a cabinet, so 40 fit (655,360 px) and 41 do not.
    assert 40 * 16384 <= 659722 < 41 * 16384
    assert [p['panels'] for p in coex['ports']] == [40, 2], coex['ports']
    assert [p['pixelSum'] for p in coex['ports']] == [40 * 16384, 2 * 16384]


# ── Flow patterns under low latency (v0.10.9) ────────────────────────────
# With the 512 px cap retired, the only NovaStar rule left is the per-port
# (1 - Y/H) derate, and it says nothing about the ROUTE: it prices a port that
# starts low on the canvas, which is what a horizontal-first pattern does from
# its second port onwards. So the traversal stays the layer's flow pattern, the
# same eight the screen uses without low latency, walked over the whole screen.
# These tests are the regression guard for "the patterns do nothing".

LL_FLOW_PATTERNS = ['tl-h', 'tl-v', 'tr-h', 'tr-v', 'bl-h', 'bl-v', 'br-h', 'br-v']


def ll_cable_order(result):
    """The cabinets in emission order -- the cable route the map ships."""
    return [(row, col) for _port, row, col, _start, _px in result['flat']]


def ll_port_starts(result):
    """The cabinet each port begins on, in port order."""
    return [(row, col) for _port, row, col, start, _px in result['flat'] if start]


@pytest.mark.parametrize('processor', ['novastar-5g', 'novastar-armor'])
def test_low_latency_honours_every_flow_pattern(page, processor):
    """All eight patterns reach the map, and all eight reach it DIFFERENTLY.

    A tall 8 x 50 wall, so every pattern needs several ports and the orders
    have to differ pairwise rather than merely start somewhere else. Every
    emission is re-checked against the capacity rules as well -- honouring the
    pattern may not cost the hardware rule."""
    uses_rectangle = processor == 'novastar-armor'
    orders = {}
    for pattern in LL_FLOW_PATTERNS:
        r = ll_port_map(page, rows=50, columns=8, pattern=pattern,
                        processorType=processor, canvasHeight=8192)
        assert_ll_ports_legal(r, 8192, f'{processor} LL {pattern}',
                              uses_rectangle=uses_rectangle)
        assert r['totalPanels'] == 400, (pattern, r['totalPanels'])
        orders[pattern] = ll_cable_order(r)
        # ...and every cabinet is still emitted exactly once.
        assert len(set(orders[pattern])) == 400, pattern

    for a, b in itertools.combinations(LL_FLOW_PATTERNS, 2):
        assert orders[a] != orders[b], (
            f"{processor}: {a} and {b} emit the same cabinet order -- the flow "
            f"pattern is not reaching the low latency map")


@pytest.mark.parametrize('pattern,expect', [
    ('tl-h', (0, 0)), ('tl-v', (0, 0)),
    ('tr-h', (0, 7)), ('tr-v', (0, 7)),
    ('bl-h', (5, 0)), ('bl-v', (5, 0)),
    ('br-h', (5, 7)), ('br-v', (5, 7)),
])
def test_low_latency_first_cabinet_is_the_pattern_corner(page, pattern, expect):
    """Port 1 opens on the corner the pattern names -- the same corner the
    screen starts from without low latency."""
    r = ll_port_map(page, rows=6, columns=8, pattern=pattern, canvasHeight=2160)
    assert_ll_ports_legal(r, 2160, f'5G LL {pattern}')
    assert ll_cable_order(r)[0] == expect, (pattern, ll_cable_order(r)[:4])


def test_low_latency_both_axes_are_honoured_inside_one_port(page):
    """A 4 x 6 wall fits one port, so a horizontal-first pattern and its
    vertical-first twin can only differ by the ROUTE. Both still open on the
    same corner -- it is the axis that moved, not the start."""
    for corner in ('tl', 'tr', 'bl', 'br'):
        h = ll_port_map(page, rows=6, columns=4, pattern=f'{corner}-h',
                        canvasHeight=2160)
        v = ll_port_map(page, rows=6, columns=4, pattern=f'{corner}-v',
                        canvasHeight=2160)
        assert len(h['ports']) == len(v['ports']) == 1, (corner, h['ports'], v['ports'])
        assert h['ports'][0]['width'] == v['ports'][0]['width'] == 4 * 128, corner
        ho, vo = ll_cable_order(h), ll_cable_order(v)
        assert ho[0] == vo[0], (
            f"{corner}: the two axes disagree about the starting corner")
        assert ho != vo, (
            f"{corner}-h and {corner}-v snake the wall identically -- "
            f"only the corner is being honoured, not the axis")


def test_low_latency_flow_pattern_moves_the_port_starts(page):
    """The owner's symptom, stated as an assertion: with low latency on, the
    Flow Pattern has to change the emitted MAP -- ports beginning on different
    cabinets -- not merely the order within a port that was already fixed."""
    starts = {p: ll_port_starts(ll_port_map(
        page, rows=50, columns=8, pattern=p, canvasHeight=8192))
        for p in LL_FLOW_PATTERNS}
    for p, s in starts.items():
        assert len(s) > 1, f'{p}: a single-port wall proves nothing here'
    assert len({tuple(s) for s in starts.values()}) == len(LL_FLOW_PATTERNS), starts


@pytest.mark.parametrize('processor', [
    'novastar-armor', 'novastar-coex-1g', 'novastar-5g',
    'brompton', 'megapixel-1g'])
@pytest.mark.parametrize('mode', ['organized', 'max-capacity'])
def test_low_latency_off_is_unchanged(page, processor, mode):
    """Regression guard: with low latency off, the emitted map must be exactly
    what it was before pass 2 -- same for a layer that has never heard of the
    flag as for one that carries it set to false."""
    spec = dict(rows=4, columns=10, cw=200, ch=200, bitDepth=10,
                processorType=processor, mode=mode, canvasHeight=2160)
    off = ll_port_map(page, lowLatency=False, **spec)
    absent = ll_port_map(page, lowLatency=None, **spec)
    assert off['flat'] == absent['flat'], processor
    assert off['error'] == absent['error']
    assert off['derate'] is None and absent['derate'] is None
    # None of these may be pushed into vertical columns: without low latency
    # the flow pattern still owns the geometry, so tl-h fills rows.
    if not off['error']:
        first = off['ports'][0]
        assert len(first['cols']) > 1, (
            f"{processor}/{mode}: normal mode emitted a single-column port")


@pytest.mark.parametrize('processor,expect_note', [
    # Every NovaStar entry feeds the note from the same layer._lowLatencyDerate,
    # so one COEX and one legacy processor cover the UI path; each line's own
    # derate is pinned at the map level in
    # test_coex_low_latency_still_derates_by_position and
    # test_legacy_low_latency_derates_by_vertical_position, where the wall's
    # size is the test's to choose rather than the page's.
    ('novastar-5g', True),
    # INVERTED: the legacy line used to have no (1 - Y/H) term and had to keep
    # the note off the screen. NovaStar since confirmed the rule covers legacy
    # too, so a pushed-down legacy screen must explain itself the same way.
    ('novastar-armor', True),
])
def test_low_latency_derate_note_appears_only_when_derated(page, processor,
                                                           expect_note):
    """Moving a NovaStar screen down the canvas changes the port count; without
    this note on screen that looks like a bug rather than the formula.

    Pinned to tl-v and to a push that keeps the whole wall on the canvas: a
    horizontal-first pattern starts its later ports further down and so derates
    a wall that IS top-aligned, and a wall hanging off the bottom has ports at
    a factor of 0. Both are the formula working - they are just not what this
    test is about, which is the note appearing exactly when a port is derated."""
    state = page.evaluate("""(processor) => {
        const app = window.app;
        const el = () => document.getElementById('low-latency-derate-note');
        const read = () => ({ text: el().textContent,
                              shown: el().style.display !== 'none' });
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        const prev = { proc: layer.processorType, ll: layer.lowLatency,
                       pattern: layer.flowPattern,
                       ys: layer.panels.map(p => p.y) };
        layer.processorType = processor;
        layer.lowLatency = true;
        layer.flowPattern = 'tl-v';
        app.selectLayer(layer);
        const h = app.getLayerCanvasHeight(layer);
        const top = Math.min.apply(null, prev.ys);
        const wall = Math.max.apply(null, layer.panels.map(
            (p, i) => prev.ys[i] - top + (Number(p.height) || 0)));
        const push = Math.floor((h - wall) / 2);
        try {
            layer.panels.forEach((p, i) => { p.y = prev.ys[i] - top; });
            app.updatePortCapacityDisplay();
            const aligned = read();
            layer.panels.forEach((p, i) => { p.y = prev.ys[i] - top + push; });
            app.updatePortCapacityDisplay();
            const pushedDown = read();
            return { h: h, wall: wall, push: push,
                     aligned: aligned, pushedDown: pushedDown,
                     // A capacity error would empty the map and suppress the
                     // note for a reason that has nothing to do with the
                     // derate; surface it so a failure says which it was.
                     err: layer._capacityError || null };
        } finally {
            layer.panels.forEach((p, i) => { p.y = prev.ys[i]; });
            layer.processorType = prev.proc;
            layer.lowLatency = prev.ll;
            layer.flowPattern = prev.pattern;
            app.updatePortCapacityDisplay();
        }
    }""", processor)
    assert state['h'] > 0, state
    assert state['push'] > 0, (
        f"the page's wall leaves no room to push it down the canvas: {state}")
    assert state['err'] is None, state
    assert state['aligned'] == {'text': '', 'shown': False}, state
    assert state['pushedDown']['shown'] is expect_note, state
    if expect_note:
        assert 'below the top of the' in state['pushedDown']['text'], state
    else:
        assert state['pushedDown'] == {'text': '', 'shown': False}, state
    assert page.evaluate(
        "document.getElementById('low-latency-derate-note').style.display"
    ) == 'none', 'the note outlived the layer that caused it'


def test_low_latency_checkbox_reflects_selected_layer(page):
    """Hydration through loadLayerToInputs -- the box must never show a stale
    layer's setting."""
    state = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        layer.processorType = 'brompton';
        layer.lowLatency = true;
        app.selectLayer(layer);
        const on = document.getElementById('low-latency').checked;
        layer.lowLatency = false;
        app.selectLayer(layer);
        return { on, off: document.getElementById('low-latency').checked };
    }""")
    assert state == {'on': True, 'off': False}, state


def test_low_latency_toggle_is_one_undo_step_and_survives_undo(page):
    """Toggling records exactly ONE history entry, and a LATER undo must not
    quietly discard the choice (mirrors the Armor Max Capacity guard)."""
    before = page.evaluate("""() => {
        const app = window.app;
        app.selectLayer(app.project.layers[0]);
        const sel = document.getElementById('processor-type');
        sel.value = 'brompton';
        sel.dispatchEvent(new Event('change'));
        return null;
    }""")
    assert before is None
    page.wait_for_timeout(600)

    history_before = page.evaluate("window.app.history.length")
    page.evaluate("""() => {
        const box = document.getElementById('low-latency');
        box.checked = true;
        box.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_timeout(700)

    state = page.evaluate("""() => {
        const l = window.app.project.layers[0];
        return {
            historyLength: window.app.history.length,
            lastAction: window.app.history[window.app.history.length - 1].action,
            lowLatency: l.lowLatency,
            capacity: window.app.calculatePortCapacity(
                l.bitDepth, l.frameRate, l.processorType, l.lowLatency),
            normal: window.app.calculatePortCapacity(
                l.bitDepth, l.frameRate, l.processorType, false)
        };
    }""")
    assert state['historyLength'] == history_before + 1, (
        f"expected exactly one undo step, history went "
        f"{history_before} -> {state['historyLength']}")
    assert state['lastAction'] == 'Change Low Latency', state
    assert state['lowLatency'] is True, state
    assert state['capacity'] == state['normal'] // 2, state

    # A later, unrelated edit, so undo steps back ONTO the low-latency state.
    before_cols = page.evaluate("window.app.project.layers[0].columns")
    cols = page.locator('#screen-columns')
    cols.fill(str(before_cols + 1))
    cols.dispatch_event('change')
    page.wait_for_timeout(700)

    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(900)
    after_undo = page.evaluate("""() => {
        const l = window.app.project.layers[0];
        return { columns: l.columns, lowLatency: l.lowLatency,
                 checked: document.getElementById('low-latency').checked };
    }""")
    assert after_undo['columns'] == before_cols, after_undo
    assert after_undo['lowLatency'] is True, (
        'undo threw away a deliberate Low Latency choice')
    assert after_undo['checked'] is True, after_undo

    # One more undo steps off it, and redo brings it back.
    page.evaluate("window.app.handleMenuAction('undo')")
    page.wait_for_timeout(900)
    assert page.evaluate("!!window.app.project.layers[0].lowLatency") is False
    page.evaluate("window.app.handleMenuAction('redo')")
    page.wait_for_timeout(900)
    assert page.evaluate("!!window.app.project.layers[0].lowLatency") is True

    # Hand the shared page back with the flag off.
    page.evaluate("""() => {
        const box = document.getElementById('low-latency');
        box.checked = false;
        box.dispatchEvent(new Event('change'));
    }""")
    page.wait_for_timeout(600)


def test_low_latency_round_trips_through_the_server(page):
    """Per-layer PUT + whole-project PUT both have to carry the flag. The
    per-layer whitelist drops unlisted keys silently, so a missed entry looks
    exactly like the toggle not working."""
    result = page.evaluate("""async () => {
        const app = window.app;
        const wait = ms => new Promise(r => setTimeout(r, ms));
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        const readStored = async () => {
            const project = await fetch('/api/project').then(r => r.json());
            return project.layers.find(l => l.id === layer.id).lowLatency;
        };

        // The app's own per-layer PUT (updateLayer sends the whole layer, so
        // the server-side whitelist is the only gate).
        app.selectLayer(layer);
        app.currentLayer.processorType = 'brompton';
        app.currentLayer.lowLatency = true;
        app.updateLayer();
        await wait(500);
        const afterSingle = await readStored();

        // ...and the bulk path used by every multi-select edit.
        app.currentLayer.lowLatency = false;
        app.updateLayers([app.currentLayer]);
        await wait(500);
        const afterBulk = await readStored();

        // Whole-project restore (undo/redo + file load path).
        const project = await fetch('/api/project').then(r => r.json());
        project.layers.forEach(l => { l.lowLatency = true; });
        const restored = await fetch('/api/project', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(project)
        }).then(r => r.json());

        return {
            afterSingle: afterSingle,
            afterBulk: afterBulk,
            preserved: app.currentLayer.lowLatency,
            afterRestore: restored.layers.map(l => l.lowLatency)
        };
    }""")
    assert result['afterSingle'] is True, result
    assert result['afterBulk'] is False, result
    assert result['preserved'] is False, (
        'the server round-trip clobbered the client value')
    assert all(v is True for v in result['afterRestore']), result


def test_low_latency_survives_localstorage_and_duplicate(page):
    """saveClientSideProperties / extractClientSideProps / the duplicate
    clientProps blob all have to list the field."""
    state = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        layer.processorType = 'brompton';
        layer.lowLatency = true;
        app.saveClientSideProperties();
        const saved = JSON.parse(
            localStorage.getItem('ledRasterClientProps') || '{}');
        return {
            extracted: app.extractClientSideProps(layer).lowLatency,
            stored: saved[layer.id] ? saved[layer.id].lowLatency : null
        };
    }""")
    assert state['extracted'] is True, state
    assert state['stored'] is True, state

    before = layer_count(page)
    page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen' && l.lowLatency === true);
        app.duplicateLayer(layer);
    }""")
    page.wait_for_timeout(900)
    assert layer_count(page) == before + 1, 'duplicate did not add a layer'
    assert page.evaluate(
        "!!window.app.currentLayer.lowLatency") is True, (
        'the duplicate lost the Low Latency flag')


def test_low_latency_round_trips_through_a_preset(page):
    """Presets are a whole-layer blob, so the field rides along -- and a preset
    saved before this feature can still carry the retired brompton-ull, which
    has to migrate on the way in."""
    state = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        layer.processorType = 'brompton';
        layer.lowLatency = true;
        const preset = app.serializeLayerAsPreset(layer);

        const fresh = { id: -1, type: 'screen' };
        app.applyPresetClientProps(fresh, preset);

        // A preset authored before the migration.
        const legacyPreset = Object.assign({}, preset, {
            processorType: 'brompton-ull'
        });
        delete legacyPreset.lowLatency;
        const migrated = { id: -2, type: 'screen' };
        app.applyPresetClientProps(migrated, legacyPreset);

        return {
            presetFlag: preset.lowLatency,
            applied: fresh.lowLatency,
            appliedProcessor: fresh.processorType,
            migratedFlag: migrated.lowLatency,
            migratedProcessor: migrated.processorType
        };
    }""")
    assert state['presetFlag'] is True, state
    assert state['applied'] is True and state['appliedProcessor'] == 'brompton', state
    assert state['migratedProcessor'] == 'brompton', state
    assert state['migratedFlag'] is True, state


def test_brompton_ull_is_no_longer_selectable(page):
    """It has to be gone from BOTH pickers so it can't be newly chosen, while
    the capacity table keeps the row so a stale value still resolves."""
    state = page.evaluate("""() => {
        const values = id => [...document.getElementById(id).options]
            .map(o => o.value);
        return {
            sidebar: values('processor-type'),
            prefs: values('pref-processor-type'),
            tableStillThere: !!window.app.portCapacityTables['brompton-ull'],
            staleResolves: window.app.calculatePortCapacity(
                8, 60, 'brompton-ull', false)
        };
    }""")
    assert 'brompton-ull' not in state['sidebar'], state['sidebar']
    assert 'brompton-ull' not in state['prefs'], state['prefs']
    assert 'brompton' in state['sidebar'] and 'brompton' in state['prefs'], state
    assert state['tableStillThere'], 'a stale brompton-ull would now read N/A'
    assert state['staleResolves'] == 262500, state


def brompton_ull_fixture_project(flows_server, name):
    """A saved project whose screen still carries the retired processor."""
    import json
    import urllib.request

    with urllib.request.urlopen(flows_server + '/api/project') as resp:
        project = json.load(resp)
    base = project['layers'][0]

    layer = json.loads(json.dumps(base))
    layer.update({
        'id': 911, 'name': 'LegacyULL',
        'processorType': 'brompton-ull',
        'portMappingMode': 'organized',
        'bitDepth': 8, 'frameRate': 60,
    })
    layer.pop('lowLatency', None)
    project['name'] = name
    project['layers'] = [layer]
    return project


def test_brompton_ull_project_migrates_on_file_open(page, flows_server, tmp_path):
    """Opening an old file rewrites brompton-ull to brompton + lowLatency, and
    the capacity it computes afterwards is IDENTICAL to what that file used to
    produce. A drift here would silently re-map a wall that is already rigged.
    """
    import json

    project = brompton_ull_fixture_project(flows_server, 'LegacyULLOpen')
    path = tmp_path / 'legacy_ull.json'
    path.write_text(json.dumps(project))

    legacy_capacity = page.evaluate(
        "() => window.app.portCapacityTables['brompton-ull'][8][60]")

    with page.expect_file_chooser() as chooser:
        page.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    page.wait_for_function(
        "() => window.app.project"
        " && window.app.project.name === 'LegacyULLOpen'"
        " && window.app.project.layers.length === 1",
        timeout=10000)
    page.wait_for_timeout(800)

    state = page.evaluate("""() => {
        const l = window.app.project.layers[0];
        return {
            processor: l.processorType,
            lowLatency: l.lowLatency,
            capacity: window.app.calculatePortCapacity(
                l.bitDepth, l.frameRate, l.processorType, l.lowLatency),
            checked: document.getElementById('low-latency').checked
        };
    }""")
    assert state['processor'] == 'brompton', state
    assert state['lowLatency'] is True, state
    assert state['capacity'] == legacy_capacity, (
        f"migrated capacity {state['capacity']} != legacy {legacy_capacity}")
    assert state['checked'] is True, state

    # Leave the shared page on a clean project for anything after us.
    page.evaluate("window.app.createNewProject()")
    page.wait_for_timeout(800)


def test_brompton_ull_migrates_on_recent_file_load(page, flows_server):
    """Recent Files does not share the file-open code, so it needs its own
    pass through the migration."""
    project = brompton_ull_fixture_project(flows_server, 'LegacyULLRecent')
    page.evaluate("""(project) => {
        localStorage.setItem('ledRasterRecentFiles', JSON.stringify([{
            name: project.name, timestamp: Date.now(),
            layerCount: project.layers.length, data: project
        }]));
    }""", project)
    page.evaluate("window.app.loadRecentFile(0)")
    page.wait_for_function(
        "() => window.app.project"
        " && window.app.project.name === 'LegacyULLRecent'"
        " && window.app.project.layers.length === 1",
        timeout=10000)
    page.wait_for_timeout(800)

    state = page.evaluate("""() => {
        const l = window.app.project.layers[0];
        return { processor: l.processorType, lowLatency: l.lowLatency };
    }""")
    assert state == {'processor': 'brompton', 'lowLatency': True}, state

    page.evaluate("localStorage.removeItem('ledRasterRecentFiles')")
    page.evaluate("window.app.createNewProject()")
    page.wait_for_timeout(800)


# ── Themed state cues actually reach the screen (v0.10.9) ────────────────
# theme.css is loaded last and paints with !important, so any UI state the JS
# indicated via an INLINE style, or that style.css declared without
# !important, was silently overridden and never rendered. Every assertion
# below reads getComputedStyle (never el.style), and checks backgroundImage as
# well as backgroundColor - the theme paints with gradients, so backgroundColor
# alone is rgba(0,0,0,0) in both states and proves nothing.

# Copied into each page.evaluate that needs it.
SNAP_JS = """
const snap = el => { const c = getComputedStyle(el); return {
  color: c.color, bg: c.backgroundColor, bgi: c.backgroundImage,
  bc: c.borderColor, bs: c.boxShadow, op: c.opacity,
  h: c.height, br: c.borderRadius }; };
"""


def accent_rgb(page):
    """--ps-accent as the 'rgb(r, g, b)' string computed styles report."""
    return page.evaluate("""() => {
        const hex = getComputedStyle(document.documentElement)
                      .getPropertyValue('--ps-accent').trim();
        const p = document.createElement('span');
        p.style.color = hex; document.body.appendChild(p);
        const c = getComputedStyle(p).color; p.remove();
        return c;
    }""")


def test_slider_accent_fill_is_painted(page):
    """theme.js writes the slider fill inline; theme.css must not eat it.
    A filled track and a bare track have to compute differently."""
    res = page.evaluate(SNAP_JS + """() => {
        const rs = [...document.querySelectorAll('input[type=range]:not(.lrd-cw-range)')];
        const r = rs.find(x => x.offsetParent !== null) || rs[0];
        if (!r) return null;
        const keep = r.getAttribute('style');
        const filled = snap(r);
        r.style.background = '';       // what the bug looked like: no fill
        const empty = snap(r);
        r.setAttribute('style', keep || '');
        return {n: rs.length, filled, empty, wrapped: !!r.closest('.ps-slider-wrap')};
    }""")
    assert res, "no range input found"
    assert res['wrapped'], "theme.js did not enhance the slider"
    assert 'linear-gradient' in res['filled']['bgi'], (
        f"slider fill not painted: {res['filled']['bgi']}")
    assert accent_rgb(page) in res['filled']['bgi'], (
        f"fill is not the themed accent: {res['filled']['bgi']}")
    assert res['filled']['bgi'] != res['empty']['bgi'], (
        "a filled track computes the same as an empty one")


def test_color_picker_channel_tracks_show_their_ramp(page):
    """The picker's per-channel gradients are written inline and its track
    sizing lives in color_picker.css; the theme's range rules must not
    flatten either, and theme.js must not bolt its accent fill on top."""
    page.evaluate("window.LRDColorWindow.open(null, '#3366cc');"
                  "window.LRDColorWindow.selectTab('sliders', true);")
    page.wait_for_timeout(300)
    res = page.evaluate(SNAP_JS + """() => {
        const rs = [...document.querySelectorAll('.lrd-cw-range')];
        if (!rs.length) return null;
        return {n: rs.length, track: snap(rs[0]),
                wrapped: rs.some(r => !!r.closest('.ps-slider-wrap'))};
    }""")
    page.evaluate("window.LRDColorWindow.close();")
    assert res, "colour picker channel sliders did not render"
    assert res['n'] >= 3, f"expected RGB channel sliders, got {res['n']}"
    assert 'linear-gradient(to right' in res['track']['bgi'], (
        f"channel ramp flattened: {res['track']['bgi']}")
    # the picker's own sizing, not the theme's chunky 22px/4px track
    assert res['track']['h'] == '12px', f"track height: {res['track']['h']}"
    assert res['track']['br'] == '6px', f"track radius: {res['track']['br']}"
    assert not res['wrapped'], (
        "theme.js enhanced a picker channel slider and repainted its ramp")


def test_layer_primary_and_hidden_cues_paint(page):
    """.primary (primary of a multi-selection) and .hidden (screen visibility
    off) must each render differently from a plain card - both were fully
    erased by the theme's !important tile rule."""
    res = page.evaluate(SNAP_JS + """() => {
        const it = document.querySelector('.layer-item');
        if (!it) return null;
        const had = it.className;
        it.className = 'layer-item';         const normal  = snap(it);
        it.className = 'layer-item primary'; const primary = snap(it);
        it.className = 'layer-item hidden';  const hidden  = snap(it);
        it.className = had;
        return {normal, primary, hidden};
    }""")
    assert res, "no layer card found"
    normal, primary, hidden = res['normal'], res['primary'], res['hidden']

    assert primary['bc'] != normal['bc'], (
        f"primary border identical to normal: {primary['bc']}")
    assert primary['bs'] != normal['bs'], "primary ring not painted"
    assert '0, 204, 255' in primary['bc'], f"primary is not the cyan ring: {primary['bc']}"

    assert hidden['bgi'] != normal['bgi'], (
        f"hidden stripe not painted: {hidden['bgi']}")
    assert 'repeating-linear-gradient' in hidden['bgi'], hidden['bgi']
    assert hidden['bg'] != normal['bg'], (
        f"hidden background identical to normal: {hidden['bg']}")
    assert hidden['bc'] != normal['bc'], "hidden border identical to normal"
    assert float(hidden['op']) < 1.0, "hidden card is not dimmed"


def test_disabled_layer_arrow_reads_dead_on_selected_card(page):
    """.layer-item.active forces on-accent white on every descendant, so a
    disabled reorder arrow looked live on the card you are about to click."""
    res = page.evaluate(SNAP_JS + """() => {
        const it = document.querySelector('.layer-item');
        const up = it && it.querySelector('.layer-move-up');
        if (!up) return null;
        const had = it.className, wasDisabled = up.disabled;
        it.classList.add('active');
        up.disabled = false; const enabled  = snap(up);
        up.disabled = true;  const disabled = snap(up);
        up.disabled = wasDisabled; it.className = had;
        return {enabled, disabled};
    }""")
    assert res, "no reorder arrow found"
    assert res['disabled']['color'] != res['enabled']['color'], (
        f"disabled arrow paints the same as an enabled one: {res['disabled']['color']}")
    assert float(res['disabled']['op']) < float(res['enabled']['op']), (
        "disabled arrow is not dimmed")


def test_disabled_btn_paints_differently(page):
    """.btn had no disabled rule at all, so inert buttons (palette Remove,
    gradient-stop Remove) looked fully live."""
    res = page.evaluate(SNAP_JS + """() => {
        const el = document.getElementById('palette-remove');
        if (!el) return null;
        const was = el.disabled;
        el.disabled = false; const enabled  = snap(el);
        el.disabled = true;  const disabled = snap(el);
        el.disabled = was;
        return {enabled, disabled};
    }""")
    assert res, "#palette-remove not found"
    assert res['disabled']['bgi'] != res['enabled']['bgi'], (
        f"disabled button keeps the enabled gradient: {res['disabled']['bgi']}")
    assert res['disabled']['color'] != res['enabled']['color'], "disabled text colour unchanged"
    assert float(res['disabled']['op']) < float(res['enabled']['op']), "disabled button not dimmed"


def test_visibility_button_keeps_hidden_glyph_on_selected_card(page):
    res = page.evaluate(SNAP_JS + """() => {
        const it = document.querySelector('.layer-item');
        const v = it && it.querySelector('.layer-visibility-btn');
        if (!v) return null;
        const had = it.className, hadV = v.className;
        it.classList.add('active');
        v.classList.remove('is-hidden'); const plain = snap(v);
        v.classList.add('is-hidden');    const off   = snap(v);
        it.className = had; v.className = hadV;
        return {plain, off};
    }""")
    assert res, "no visibility button found"
    assert res['off']['color'] != res['plain']['color'], (
        f"is-hidden glyph colour overridden: {res['off']['color']}")
    assert res['off']['bg'] != res['plain']['bg'], "is-hidden background not painted"


def test_rename_edit_cue_paints(page):
    """Layer and canvas rename cues moved from inline styles to classes,
    because the themed field rule sets background/border with !important."""
    res = page.evaluate(SNAP_JS + """() => {
        const li = document.querySelector('.layer-name-input');
        const ci = document.querySelector('.canvas-name-input');
        if (!li || !ci) return null;
        li.classList.remove('editing'); const lPlain = snap(li);
        li.classList.add('editing');    const lEdit  = snap(li);
        li.classList.remove('editing');
        ci.readOnly = true;  const cPlain = snap(ci);
        ci.readOnly = false; const cEdit  = snap(ci);
        ci.readOnly = true;
        return {lPlain, lEdit, cPlain, cEdit};
    }""")
    assert res, "rename inputs not found"
    accent = accent_rgb(page)
    for plain, edit, what in ((res['lPlain'], res['lEdit'], 'layer'),
                              (res['cPlain'], res['cEdit'], 'canvas')):
        assert edit['bc'] != plain['bc'], f"{what} rename border unchanged: {edit['bc']}"
        assert accent in edit['bc'], f"{what} rename cue is not the accent: {edit['bc']}"
        assert edit['bg'] != plain['bg'], f"{what} rename background unchanged"


def test_invalid_watts_cue_shows_while_focused(page):
    """Enter fires `change` while the field still has focus, and theme.css
    forces `input:focus { outline:none !important }` - so the old inline
    outline was invisible in exactly the case that mattters."""
    page.locator('[data-mode="power"]').click()
    page.wait_for_timeout(400)
    field = page.locator('#power-panel-watts')
    field.click()
    field.fill('not a number')
    field.press('Enter')
    page.wait_for_timeout(200)

    res = page.evaluate(SNAP_JS + """() => {
        const i = document.getElementById('power-panel-watts');
        return {focused: document.activeElement === i,
                invalid: i.classList.contains('invalid'), s: snap(i)};
    }""")
    assert res['focused'], "field lost focus, so this is not the reported case"
    assert res['invalid'], "the invalid class was never applied"
    assert 'rgb(204, 85, 85)' in res['s']['bc'], f"invalid border missing: {res['s']['bc']}"
    assert 'rgb(204, 85, 85)' in res['s']['bs'], f"invalid ring missing: {res['s']['bs']}"

    field.fill('200')
    field.press('Enter')
    page.wait_for_timeout(200)
    cleared = page.evaluate(SNAP_JS + """() => {
        const i = document.getElementById('power-panel-watts');
        return {invalid: i.classList.contains('invalid'), s: snap(i)};
    }""")
    assert not cleared['invalid'], "the invalid cue never cleared"
    assert 'rgb(204, 85, 85)' not in cleared['s']['bc'], "invalid border stuck"
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)


def test_accent_readouts_are_renderable(page):
    """The export filename preview used to carry the legacy blue inline, which
    theme.css then overrode to plain text - the healthy value was unrenderable
    while the error colours still showed. It is the only thing in its box, so
    the accent reads as a highlight there and it keeps .value-accent."""
    accent = accent_rgb(page)
    res = page.evaluate("""() => ['export-preview']
        .map(id => { const e = document.getElementById(id);
            return {id, found: !!e,
                    color: e ? getComputedStyle(e).color : null,
                    cls: e ? e.classList.contains('value-accent') : false}; })""")
    for r in res:
        assert r['found'], f"#{r['id']} missing"
        assert r['cls'], f"#{r['id']} lost the value-accent class"
        assert r['color'] == accent, (
            f"#{r['id']} is {r['color']}, not the themed accent {accent}")


def test_healthy_port_readouts_do_not_look_like_an_error(page):
    """v0.10.9 correction: Pixels/Port and Panels/Port sit in the same box as
    #ff0000 (Panels/Port ERROR) and #ff6600 (N/A), and the default accent is
    red, so an accent-coloured healthy figure read as a fault. A healthy value
    renders in the ordinary text colour and nothing else in that box does."""
    res = page.evaluate("""() => {
        const probe = (css) => { const p = document.createElement('span');
            p.style.color = css; document.body.appendChild(p);
            const c = getComputedStyle(p).color; p.remove(); return c; };
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        app.selectLayer(layer);
        app.updatePortCapacityDisplay();
        const read = (id) => { const e = document.getElementById(id);
            return { found: !!e, text: e ? e.textContent : null,
                     color: e ? getComputedStyle(e).color : null }; };
        return {
            capacity: read('port-capacity'),
            panels: read('panels-per-port'),
            text: probe(getComputedStyle(document.documentElement)
                          .getPropertyValue('--ps-text').trim()),
            panelsError: probe('#ff0000'),
            capacityError: probe('#ff6600')
        };
    }""")
    accent = accent_rgb(page)
    for key in ('capacity', 'panels'):
        r = res[key]
        assert r['found'], f"{key} readout missing"
        # A healthy figure, not one of the error strings.
        assert r['text'] not in ('N/A', 'ERROR', '-'), (key, r)
        assert r['color'] == res['text'], (
            f"{key} is {r['color']}, not the ordinary text colour {res['text']}")
        assert r['color'] != res['panelsError'], (key, r)
        assert r['color'] != res['capacityError'], (key, r)
        assert r['color'] != accent, (
            f"{key} still rides the accent, which is what read as an error")


def test_text_style_buttons_follow_the_accent(page):
    """B/I/U were the only segmented toggle still hard-coded blue."""
    accent = accent_rgb(page)
    res = page.evaluate(SNAP_JS + """() => {
        const el = document.getElementById('text-layer-bold');
        if (!el) return null;
        const had = el.className;
        el.classList.remove('active'); const off = snap(el);
        el.classList.add('active');    const on  = snap(el);
        el.className = had;
        return {off, on};
    }""")
    assert res, "#text-layer-bold not found"
    assert res['on']['bgi'] != res['off']['bgi'], "active B/I/U looks like inactive"
    assert accent in res['on']['bgi'], (
        f"active B/I/U is not the themed accent: {res['on']['bgi']}")
    assert '42, 109, 212' not in res['on']['bgi'], "still the hard-coded blue"


# ── Port load percentage (v0.10.9) ───────────────────────────────────────
# The Data Flow tab can print how full each port is, as a percentage of THAT
# port's capacity. The figure has to come from the same accounting the port
# map itself used, which differs per processor: NovaStar Armor pays for the
# reserved bounding RECTANGLE, everything else pays the pixel sum. The tests
# below re-derive every percentage from the EMITTED map and compare, so a
# renderer that quietly reinvented the arithmetic fails here.

PORT_LOAD_JS = """(spec) => {
    const app = window.app;
    const renderer = window.canvasRenderer;
    const hiddenSet = new Set((spec.hidden || []).map(rc => rc[0] + ',' + rc[1]));
    const offsetX = spec.offsetX || 0;
    const offsetY = spec.offsetY || 0;
    const panels = [];
    let n = 1;
    for (let r = 0; r < spec.rows; r++) {
        for (let c = 0; c < spec.columns; c++) {
            panels.push({
                id: n, number: n, row: r, col: c,
                x: offsetX + c * spec.cw, y: offsetY + r * spec.ch,
                width: spec.cw, height: spec.ch,
                hidden: hiddenSet.has(r + ',' + c), blank: false, halfTile: 'none'
            });
            n++;
        }
    }
    // Throwaway canvas so H in the Low Latency (1 - Y/H) derate is exactly
    // what the test says it is; removed again before returning.
    const canvasId = '__load_test_canvas__';
    const prevCanvases = app.project.canvases;
    app.project.canvases = (prevCanvases || []).concat([{
        id: canvasId, name: 'load test',
        raster_width: spec.canvasWidth || 4096,
        raster_height: spec.canvasHeight || 2160
    }]);
    const layer = {
        id: -2, type: 'screen', rows: spec.rows, columns: spec.columns,
        cabinet_width: spec.cw, cabinet_height: spec.ch, panels,
        canvas_id: canvasId, offset_x: offsetX, offset_y: offsetY,
        processorType: spec.processorType,
        portMappingMode: spec.mode || 'organized',
        flowPattern: spec.pattern || 'tl-h',
        bitDepth: spec.bitDepth || 8,
        frameRate: spec.frameRate || 60,
        lowLatency: !!spec.lowLatency
    };
    let assignments;
    let out;
    try {
        assignments = app.calculatePortAssignments(layer);
        const byPort = new Map();
        assignments.forEach(a => {
            if (!byPort.has(a.port)) byPort.set(a.port, []);
            byPort.get(a.port).push(a.panel);
        });
        const ports = Array.from(byPort.keys()).sort((a, b) => a - b).map(p => {
            const ps = byPort.get(p);
            const minX = Math.min.apply(null, ps.map(q => q.x));
            const maxX = Math.max.apply(null, ps.map(q => q.x + q.width));
            const minY = Math.min.apply(null, ps.map(q => q.y));
            const maxY = Math.max.apply(null, ps.map(q => q.y + q.height));
            const stats = renderer.getPortLoadStats(layer, ps);
            // The same port re-scored under a pixel-sum processor, so the
            // rectangle rule can be shown to be the thing that differs.
            const asPixelSum = renderer.getPortPixelLoad(
                Object.assign({}, layer, { processorType: 'brompton' }), ps);
            return {
                port: p,
                panels: ps.length,
                minY: minY,
                rectArea: (maxX - minX) * (maxY - minY),
                pixelSum: ps.reduce((s, q) => s + q.width * q.height, 0),
                asPixelSum: asPixelSum,
                stats: stats
            };
        });
        out = {
            baseCapacity: app.calculatePortCapacity(
                layer.bitDepth, layer.frameRate, layer.processorType,
                layer.lowLatency),
            canvasHeight: spec.canvasHeight || 2160,
            ports: ports,
            // Every panel handed over as ONE port, the way a hand-drawn
            // custom path can over-fill one.
            wholeWall: renderer.getPortLoadStats(
                layer, panels.filter(q => !q.hidden)),
            error: !!layer._capacityError,
            errorInfo: layer._capacityError || null
        };
    } finally {
        app.project.canvases = prevCanvases;
    }
    return out;
}"""


def port_load(page, **spec):
    spec.setdefault('cw', 200)
    spec.setdefault('ch', 200)
    return page.evaluate(PORT_LOAD_JS, spec)


def js_round(value):
    """Math.round rounds .5 UP; Python's round() goes to even. The displayed
    number has to match the browser's, so mirror the browser."""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def test_port_load_percent_matches_the_emitted_map(page):
    """Every percentage re-derives from the shipped map: pixel sum over the
    port's own capacity, for a pixel-sum processor."""
    res = port_load(page, rows=3, columns=8, processorType='brompton',
                    mode='max-capacity')
    assert not res['error'], res['errorInfo']
    assert res['ports'], 'no ports emitted'
    capacity = res['baseCapacity']
    assert capacity > 0
    for p in res['ports']:
        stats = p['stats']
        assert stats, f"port {p['port']} produced no load figure"
        # Pixel-sum accounting, and no Low Latency, so capacity is the table
        # figure untouched.
        assert stats['load'] == p['pixelSum'], p
        assert stats['capacity'] == capacity, p
        expected = js_round(p['pixelSum'] / capacity * 100)
        assert stats['shown'] == expected, (
            f"port {p['port']}: showed {stats['shown']}%, "
            f"{p['pixelSum']}/{capacity} is {expected}%")
        # The colour state follows the number the user reads, so the two can
        # never disagree: 90%+ warns, 100%+ is over, healthy is neither.
        expected_state = ('over' if expected >= 100
                          else ('warn' if expected >= 90 else 'ok'))
        assert stats['state'] == expected_state, p


def test_port_load_armor_charges_the_rectangle_not_the_pixel_sum(page):
    """Stair-step wall: Armor's reserved rectangle is bigger than the lit
    pixels, so its percentage MUST be the higher of the two. Scoring Armor on
    a pixel sum would tell the user a full port has room left."""
    hidden = ([[1, c] for c in range(8, 10)]
              + [[2, c] for c in range(5, 10)]
              + [[3, c] for c in range(2, 10)])
    res = port_load(page, rows=4, columns=10, hidden=hidden,
                    processorType='novastar-armor', mode='max-capacity')
    assert not res['error'], res['errorInfo']
    assert [p['panels'] for p in res['ports']] == [10, 13, 2], res['ports']

    middle = res['ports'][1]
    # 13 cabinets light 520,000 px inside a 1600x400 = 640,000 px reservation.
    assert middle['rectArea'] == 640000
    assert middle['pixelSum'] == 520000
    assert middle['stats']['load'] == 640000, (
        'Armor was scored on the pixel sum, not the reserved rectangle')
    # The same cabinets under a pixel-sum processor cost the lit pixels only.
    assert middle['asPixelSum'] == 520000
    assert middle['stats']['load'] != middle['asPixelSum'], (
        'the two accountings have to differ on a stair-step wall')

    capacity = res['baseCapacity']
    assert middle['stats']['capacity'] == capacity
    assert middle['stats']['shown'] == js_round(640000 / capacity * 100)
    # Ranking the ports by percentage must follow the rectangle too.
    assert middle['stats']['shown'] > js_round(520000 / capacity * 100)


def test_port_load_over_capacity_is_flagged(page):
    """A hand-drawn path that puts the whole wall on one port reads over
    100% and is flagged, rather than silently topping out at a healthy
    looking number."""
    res = port_load(page, rows=4, columns=10,
                    processorType='novastar-armor', mode='max-capacity')
    assert not res['error'], res['errorInfo']
    # Every emitted port fits, so none of them is flagged.
    for p in res['ports']:
        assert p['stats']['state'] == 'ok', p
        assert p['stats']['shown'] < 100, p

    whole = res['wholeWall']
    # 2000 x 800 = 1,600,000 px reserved against a 659,722 px port.
    assert whole['load'] == 1600000, whole
    assert whole['percent'] > 100, whole
    assert whole['shown'] >= 100, whole
    assert whole['state'] == 'over', whole


def test_port_load_uses_the_low_latency_derated_capacity(page):
    """A NovaStar Low Latency port that starts below the top of the canvas
    keeps only (1 - Y/H) of the table figure. Scoring it against the table
    figure would understate how full it is."""
    # A 4 x 50 wall of 128 px cabinets fills its canvas top to bottom. Walked
    # horizontally, port 1 runs out partway down and every port after it
    # starts on a lower row -- which is exactly what the derate charges for.
    res = port_load(page, rows=50, columns=4, cw=128, ch=128,
                    processorType='novastar-5g', mode='organized',
                    pattern='tl-h', lowLatency=True,
                    canvasHeight=6400, offsetY=0)
    assert not res['error'], res['errorInfo']
    base = res['baseCapacity']
    height = res['canvasHeight']
    derated = [p for p in res['ports'] if p['minY'] > 0]
    assert derated, 'expected at least one port starting below the top'
    for p in res['ports']:
        expected_capacity = int(
            min(1.0, max(0.0, 1 - (p['minY'] / height))) * base)
        assert p['stats']['capacity'] == expected_capacity, (
            f"port {p['port']} at Y={p['minY']} scored against "
            f"{p['stats']['capacity']}, not its derated {expected_capacity}")
        assert p['stats']['shown'] == js_round(
            p['stats']['load'] / expected_capacity * 100), p
    for p in derated:
        assert p['stats']['capacity'] < base, (
            'a derated port was scored against the undertated table figure')


def test_port_load_toggle_defaults_off_and_gates_the_drawing(page):
    """Default OFF (no existing export changes), on draws the percentages in
    both the interactive view and the export pass, and the flag round-trips
    through the server."""
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(400)

    setup = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        app.selectLayer(layer);
        const box = document.getElementById('show-data-flow-port-load');
        const row = box ? box.closest('.info-row') : null;
        return {
            found: !!box,
            checked: box ? box.checked : null,
            flag: !!layer.showDataFlowPortLoad,
            rowDisplay: row ? getComputedStyle(row).display : null,
            rowVisibility: row ? getComputedStyle(row).visibility : null,
            isCheckboxRow: row ? row.classList.contains('checkbox-row') : null,
            layerId: layer.id
        };
    }""")
    assert setup['found'], '#show-data-flow-port-load is missing from the Data sidebar'
    assert setup['checked'] is False, 'the toggle did not default OFF'
    assert setup['flag'] is False, 'the layer flag did not default OFF'
    assert setup['rowDisplay'] != 'none', setup
    assert setup['rowVisibility'] != 'hidden', setup
    assert setup['isCheckboxRow'], 'the toggle does not follow the checkbox-row markup'

    # Count the percentages the real render pass paints, with the flag off
    # and on, interactively and in the export pass (same renderer, so the
    # exported map carries whatever the screen does).
    COUNT_JS = """(on) => {
        const app = window.app;
        const renderer = window.canvasRenderer;
        const layer = app.project.layers.find(
            l => (l.type || 'screen') === 'screen');
        layer.showDataFlowPortLoad = on;
        const ctx = renderer.ctx;
        const original = ctx.fillText;
        const painted = [];
        ctx.fillText = function (text, x, y, w) {
            painted.push(String(text));
            return original.call(this, text, x, y, w);
        };
        const prevMode = renderer.viewMode;
        const prevExport = renderer.exportMode;
        let interactive, exported;
        try {
            renderer.viewMode = 'data-flow';
            renderer.render();
            interactive = painted.filter(t => /^\\d+%$/.test(t)).length;
            painted.length = 0;
            renderer.exportMode = true;
            renderer.render();
            exported = painted.filter(t => /^\\d+%$/.test(t)).length;
        } finally {
            ctx.fillText = original;
            renderer.exportMode = prevExport;
            renderer.viewMode = prevMode;
            renderer.render();
        }
        return { interactive: interactive, exported: exported };
    }"""
    off = page.evaluate(COUNT_JS, False)
    on = page.evaluate(COUNT_JS, True)
    assert off['interactive'] == 0, 'percentages drawn while the toggle is OFF'
    assert off['exported'] == 0, 'percentages exported while the toggle is OFF'
    assert on['interactive'] > 0, 'toggle ON drew no percentages'
    assert on['exported'] == on['interactive'], (
        f"export drew {on['exported']} percentages, the screen drew "
        f"{on['interactive']} -- the two views disagree")

    # Round-trip: the toggle's own change handler (the path a user takes),
    # then read the stored project back.
    stored = page.evaluate("""async (layerId) => {
        const app = window.app;
        const wait = ms => new Promise(r => setTimeout(r, ms));
        const layer = app.project.layers.find(l => l.id === layerId);
        app.selectLayer(layer);
        const box = document.getElementById('show-data-flow-port-load');
        box.checked = true;
        box.dispatchEvent(new Event('change'));
        let server = null;
        for (let i = 0; i < 20 && server !== true; i++) {
            await wait(200);
            const project = await fetch('/api/project').then(r => r.json());
            const saved = project.layers.find(l => l.id === layerId);
            server = saved ? saved.showDataFlowPortLoad : null;
        }
        const props = JSON.parse(
            localStorage.getItem('ledRasterClientProps') || '{}');
        return {
            server: server,
            flag: !!app.project.layers.find(
                l => l.id === layerId).showDataFlowPortLoad,
            extracted: app.extractClientSideProps(layer).showDataFlowPortLoad,
            local: props[layerId] ? props[layerId].showDataFlowPortLoad : null
        };
    }""", setup['layerId'])
    assert stored['flag'] is True, 'the change handler did not set the layer flag'
    assert stored['server'] is True, (
        'the server dropped showDataFlowPortLoad -- missing from the whitelist')
    assert stored['extracted'] is True, stored
    assert stored['local'] is True, stored

    # Reload: the stored flag has to come back on, and hydrate the checkbox.
    pg = page.context.new_page()
    pg.goto(page.url, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    reloaded = pg.evaluate("""(layerId) => {
        const app = window.app;
        const layer = app.project.layers.find(l => l.id === layerId);
        if (!layer) return null;
        app.selectLayer(layer);
        const box = document.getElementById('show-data-flow-port-load');
        return { flag: !!layer.showDataFlowPortLoad,
                 checked: box ? box.checked : null };
    }""", setup['layerId'])
    pg.close()
    assert reloaded, 'the layer vanished across the reload'
    assert reloaded['flag'] is True, 'the flag did not survive the reload'
    assert reloaded['checked'] is True, (
        'loadLayerToInputs did not hydrate the checkbox after the reload')

    # Leave the shared project as we found it.
    page.evaluate("""(layerId) => {
        const app = window.app;
        app.selectLayer(app.project.layers.find(l => l.id === layerId));
        const box = document.getElementById('show-data-flow-port-load');
        box.checked = false;
        box.dispatchEvent(new Event('change'));
    }""", setup['layerId'])
    page.wait_for_timeout(600)
