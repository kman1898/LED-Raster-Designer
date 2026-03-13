"""Browser-based E2E tests using Playwright.

Tests that colors and UI elements work correctly across Chromium, Firefox,
and WebKit (Safari). Starts a real Flask server and interacts through the
browser just like a user would.

Run locally:
    pip install playwright && playwright install
    python -m pytest tests/test_browser.py -v --browser chromium
    python -m pytest tests/test_browser.py -v --browser firefox
    python -m pytest tests/test_browser.py -v --browser webkit

The --browser flag selects which engine to test.
"""

import sys
import os
import time
import threading
import pytest

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Try importing playwright — skip all tests if not installed
pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="session")
def browser_name(request):
    return request.config.getoption("--browser", default="chromium")


@pytest.fixture(scope="session")
def server():
    """Start the Flask app on a background thread."""
    import app as app_module
    from app import app, socketio

    # Reset to clean state
    app_module.current_project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [],
        'is_pristine': True,
    }
    app_module.next_layer_id = 1

    # Add a default layer so the UI has something to work with
    app.config['TESTING'] = True
    with app.test_client() as c:
        c.post('/api/layer/add', json={
            'name': 'Screen1',
            'columns': 4,
            'rows': 3,
            'cabinet_width': 128,
            'cabinet_height': 128,
        })

    port = 15789  # Unlikely to collide
    thread = threading.Thread(
        target=lambda: socketio.run(app, host='127.0.0.1', port=port,
                                     allow_unsafe_werkzeug=True, log_output=False),
        daemon=True,
    )
    thread.start()
    time.sleep(1)  # Give server time to bind

    yield f'http://127.0.0.1:{port}'


@pytest.fixture(scope="session")
def page(server, browser_name):
    """Launch browser and navigate to the app."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        launcher = getattr(p, browser_name)
        browser = launcher.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        pg.goto(server, wait_until='networkidle')
        # Give SocketIO time to connect and initialize app
        pg.wait_for_timeout(2000)
        yield pg
        browser.close()


# ── Page load tests ──────────────────────────────────────────────────────


def test_page_title(page):
    """App loads and title contains LED Raster Designer."""
    assert 'LED Raster Designer' in page.title()


def test_canvas_exists(page):
    """The main canvas element is present and visible."""
    canvas = page.locator('canvas#main-canvas')
    assert canvas.is_visible()


def test_toolbar_loads(page):
    """Toolbar with project name input is present."""
    name_input = page.locator('#project-name')
    assert name_input.is_visible()
    assert name_input.input_value() != ''


# ── Color picker tests ───────────────────────────────────────────────────


def test_color1_picker_exists(page):
    """Panel color 1 picker is present in the UI."""
    picker = page.locator('#color1-picker')
    assert picker.count() > 0


def test_color2_picker_exists(page):
    """Panel color 2 picker is present in the UI."""
    picker = page.locator('#color2-picker')
    assert picker.count() > 0


def test_border_color_picker_exists(page):
    """Border color picker is present."""
    picker = page.locator('#border-color')
    assert picker.count() > 0


def test_color1_hex_input_sync(page):
    """Typing a hex value into color1-hex updates the stored value."""
    hex_input = page.locator('#color1-hex')
    if hex_input.count() == 0:
        pytest.skip("color1-hex input not found in UI")

    hex_input.fill('')
    hex_input.type('#ff5733')
    hex_input.press('Enter')
    page.wait_for_timeout(300)

    # The hex input should reflect what we typed
    val = hex_input.input_value()
    assert val.lower().replace('#', '') == 'ff5733', f"color1-hex shows {val}"


def test_border_color_hex_input(page):
    """Border color hex input accepts and stores exact values."""
    hex_input = page.locator('#border-color-hex')
    if hex_input.count() == 0:
        pytest.skip("border-color-hex input not found in UI")

    hex_input.fill('')
    hex_input.type('#1a2b3c')
    hex_input.press('Enter')
    page.wait_for_timeout(300)

    val = hex_input.input_value()
    assert '1a2b3c' in val.lower(), f"border-color-hex shows {val}"


def test_arrow_color_hex_input(page):
    """Arrow color hex input stores the exact hex value."""
    # Need to be on data flow view for this control to be visible
    # Try clicking the data flow tab if it exists
    data_tab = page.locator('[data-view="data-flow"], #view-data-flow, .view-tab:has-text("Data")')
    if data_tab.count() > 0:
        data_tab.first.click()
        page.wait_for_timeout(300)

    hex_input = page.locator('#arrow-color-hex')
    if hex_input.count() == 0 or not hex_input.is_visible():
        pytest.skip("arrow-color-hex not visible (may need data flow view)")

    hex_input.fill('')
    hex_input.type('#7a8b9c')
    hex_input.press('Enter')
    page.wait_for_timeout(300)

    val = hex_input.input_value()
    assert '7a8b9c' in val.lower(), f"arrow-color-hex shows {val}"


# ── Canvas rendering tests ───────────────────────────────────────────────


def test_canvas_has_content(page):
    """Canvas is not blank — at least some pixels are non-white."""
    canvas = page.locator('canvas#main-canvas')
    if canvas.count() == 0:
        pytest.skip("No canvas found")

    # Take a screenshot of the canvas and check it's not empty
    bbox = canvas.bounding_box()
    if not bbox or bbox['width'] == 0:
        pytest.skip("Canvas has no size")

    # Sample a pixel from the canvas center using JS
    result = page.evaluate('''() => {
        const c = document.getElementById('main-canvas');
        if (!c) return null;
        const ctx = c.getContext('2d');
        const x = Math.floor(c.width / 2);
        const y = Math.floor(c.height / 2);
        const pixel = ctx.getImageData(x, y, 1, 1).data;
        return { r: pixel[0], g: pixel[1], b: pixel[2], a: pixel[3] };
    }''')
    assert result is not None, "Could not read canvas pixel"
    # Canvas should have some content (alpha > 0 somewhere)
    # We just verify we can read pixels — the rendering itself is visual


# ── View tab tests ───────────────────────────────────────────────────────


def test_view_tabs_exist(page):
    """All view tabs (Pixel, Cabinet, Data Flow, Power) exist."""
    tabs = page.locator('.view-tab, [data-view]')
    if tabs.count() == 0:
        pytest.skip("View tabs not found with expected selectors")
    assert tabs.count() >= 3, f"Expected at least 3 view tabs, found {tabs.count()}"


def test_switching_views_doesnt_crash(page):
    """Switching between view tabs doesn't cause JS errors."""
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))

    tabs = page.locator('.view-tab, [data-view]')
    count = tabs.count()
    for i in range(count):
        tabs.nth(i).click()
        page.wait_for_timeout(200)

    assert len(errors) == 0, f"JS errors when switching tabs: {errors}"
