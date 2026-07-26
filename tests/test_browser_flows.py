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
