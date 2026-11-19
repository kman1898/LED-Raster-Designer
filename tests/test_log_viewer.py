"""The log as the owner reads it (2026-11-19 logging audit, phase 1).

A held Label Size spinner wrote about five lines a tick, one of them the
whole screen (about 10 KB): thirty ticks were about 150 lines. Now the
screen's save says what changed and is named by the gesture, and the
ticks of one hold fold into one line. The viewer shows readable lines
(time, level, area, message), warnings and errors coloured, debug hidden
until asked for, filters by level, area, text and screen, a line opening
to its details, and Raw for the file's own lines.

Run locally:
    python -m pytest tests/test_log_viewer.py -n 4 --dist loadfile --browser chromium
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import app as app_module  # noqa: E402
import routes_logs  # noqa: E402
from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def log_file(tmp_path_factory):
    """The in-process server's log, pointed at a file of this module's."""
    app_module.flush_log()
    path = tmp_path_factory.mktemp('log') / 'led_raster_designer.log'
    path.write_text('', encoding='utf-8')
    saved = (app_module.LOG_FILE_PATH, app_module.LOG_DIR_PATH,
             routes_logs.LOG_FILE_PATH, routes_logs.LOG_DIR_PATH)
    app_module.LOG_FILE_PATH = routes_logs.LOG_FILE_PATH = str(path)
    app_module.LOG_DIR_PATH = routes_logs.LOG_DIR_PATH = str(path.parent)
    yield path
    app_module.flush_log()
    (app_module.LOG_FILE_PATH, app_module.LOG_DIR_PATH,
     routes_logs.LOG_FILE_PATH, routes_logs.LOG_DIR_PATH) = saved


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser, log_file):
    ctx = pw_browser.new_context(viewport={'width': 1500, 'height': 950})
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
                        "localStorage.removeItem('lrd_logs_viewer');}catch(e){}")
    pg = ctx.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && Array.isArray(window.app.history)", timeout=30000)
    yield pg
    ctx.close()


def _lines(path):
    app_module.flush_log()
    out = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        if raw.strip():
            out.append(json.loads(raw))
    return out


def _clear(path):
    app_module.flush_log()
    path.write_text('', encoding='utf-8')


RESET_JS = """async () => {
    const app = window.app, r = window.canvasRenderer;
    let project = await (await fetch('/api/project')).json();
    project.layers = []; project.groups = [];
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'LogWall', columns: 4, rows: 3, cabinet_width: 128,
            cabinet_height: 128, offset_x: 0, offset_y: 0})});
    app.project = await (await fetch('/api/project')).json();
    const live = app.project.layers.filter(l => (l.type || 'screen') === 'screen');
    live[0].dataFlowLabelSize = 30;
    app.currentLayer = live[0];
    app.selectedLayerIds = new Set([live[0].id]);
    app.lastSelectedLayerId = live[0].id;
    app._flushPendingSaveState();
    app.resetHistory('Log Reset');
    app.renderLayers();
    app.updateLayerProperties ? app.updateLayerProperties() : null;
    r.render();
    return live[0].id;
}"""


def _hold_label_size(page, ms):
    """Hold #label-size's up arrow, the Mac app's way: a change on every
    tick (see test_number_hold_undo)."""
    page.locator('[data-mode="data-flow"]').click()
    settled(page, lambda: page.evaluate("() => window.canvasRenderer.viewMode"), lambda v: v == 'data-flow')
    field = page.locator('#label-size')
    field.scroll_into_view_if_needed()
    page.evaluate("""() => {
        const el = document.getElementById('label-size');
        el.value = '30';
        el.__everyTick = (e) => { if (e.isTrusted) el.dispatchEvent(new Event('change', { bubbles: true })); };
        el.addEventListener('input', el.__everyTick);
    }""")
    try:
        box = field.bounding_box()
        page.mouse.move(box['x'] + box['width'] - 14, box['y'] + box['height'] / 2 - 4)
        page.mouse.down()
        page.wait_for_timeout(ms)
        page.mouse.up()
        page.wait_for_timeout(300)
    finally:
        page.evaluate("""() => {
            const el = document.getElementById('label-size');
            el.removeEventListener('input', el.__everyTick);
        }""")


def test_a_held_spinner_is_a_couple_of_short_lines(page, log_file):
    lid = page.evaluate(RESET_JS)
    _clear(log_file)
    _hold_label_size(page, 1500)
    end = page.evaluate(f"() => window.app.project.layers.find(l => l.id === {lid}).dataFlowLabelSize")
    assert end >= 34, f'the hold stepped only to {end}'
    # Every save of the hold has reached the server before the log is read.
    settled(page, lambda: page.evaluate("() => window.app._layerSavesSettled().then(() => 1)"),
            lambda v: v == 1)
    page.wait_for_timeout(1300)   # the fold window closes
    lines = _lines(log_file)
    edits = [x for x in lines if x['action'] == 'update_layer' and x['details'].get('id') == lid]
    assert 1 <= len(edits) <= 2, [x['msg'] for x in edits]
    last = edits[-1]
    assert last['details']['diff']['dataFlowLabelSize'][1] == end, last
    assert edits[0]['details']['diff']['dataFlowLabelSize'][0] == 30, edits[0]
    assert last['area'] == 'data'
    assert 'Change Data Flow Label Size' in last['msg'] or 'label-size' in last['msg'], last['msg']
    ticks = [x for x in lines if x['action'] == 'ui_change' and x['details'].get('id') == 'label-size']
    assert 1 <= len(ticks) <= 2, [x['msg'] for x in ticks]
    # Short: no whole screen in any line, and the hold is a handful of lines.
    assert max(len(json.dumps(x)) for x in lines) < 3000, max(lines, key=lambda x: len(json.dumps(x)))
    info = [x for x in lines if x['lvl'] != 'debug']
    assert len(info) <= 8, [(x['action'], x['msg']) for x in info]


def _open_viewer(page):
    page.evaluate("() => window.app.openLogsModal()")
    page.wait_for_selector('#logs-readable .logs-row, #logs-readable .logs-empty', timeout=5000)


def _rows(page):
    return page.evaluate("""() => [...document.querySelectorAll('#logs-readable .logs-row')]
        .map(r => ({ text: r.querySelector('.logs-row-head').textContent, cls: r.className }))""")


def _wait_rows(page, pred, what):
    settled(page, lambda: _rows(page), pred, timeout_ms=6000)
    rows = _rows(page)
    assert pred(rows), (what, rows)
    return rows


def test_the_viewer_reads_and_filters(page, log_file):
    page.evaluate(RESET_JS)
    _clear(log_file)
    app_module.log_event('add_layer', {'id': 77, 'name': 'Viewer Wall'})
    app_module.log_event('merge_runs_refused', {'layerId': 77, 'why': 'the screen is locked'})
    app_module.log_event('stage3d_paint_failed', {'id': 78, 'error': 'boom'})
    app_module.log_event('socket_project_data', {'page': 'Z'}, source='client')
    try:
        _open_viewer(page)
        rows = _wait_rows(page, lambda r: any('merge runs refused' in x['text'] for x in r), 'first load')
        texts = '\n'.join(x['text'] for x in rows)
        # readable: time, level, area, message; debug hidden
        assert 'INFO  PIXELMAP  add layer: id=77, name=Viewer Wall' in texts, texts
        assert 'socket project data' not in texts, texts
        warn = next(x for x in rows if 'merge runs refused' in x['text'])
        assert 'lvl-warn' in warn['cls']
        err = next(x for x in rows if 'stage3d paint failed' in x['text'])
        assert 'lvl-error' in err['cls']

        # Warnings off: the warning goes
        page.locator('#logs-levels .logs-chip[data-lvl="warn"]').click()
        _wait_rows(page, lambda r: r and not any('merge runs refused' in x['text'] for x in r), 'warn off')
        page.locator('#logs-levels .logs-chip[data-lvl="warn"]').click()
        # Debug on: the echo shows
        page.locator('#logs-levels .logs-chip[data-lvl="debug"]').click()
        _wait_rows(page, lambda r: any('socket project data' in x['text'] for x in r), 'debug on')
        page.locator('#logs-levels .logs-chip[data-lvl="debug"]').click()

        # An area chip: 3D only
        page.locator('#logs-areas .logs-chip[data-area="3d"]').click()
        _wait_rows(page, lambda r: r and all('3D' in x['text'] for x in r), '3d only')
        page.locator('#logs-areas .logs-chip[data-area="3d"]').click()

        # Search
        page.locator('#logs-search').fill('locked')
        _wait_rows(page, lambda r: len(r) == 1 and 'merge runs refused' in r[0]['text'], 'search')
        page.locator('#logs-search').fill('')
        _wait_rows(page, lambda r: len(r) >= 3, 'search cleared')

        # A line opens to its details
        page.locator('#logs-readable .logs-row', has_text='merge runs refused').click()
        det = page.locator('#logs-readable .logs-row-details').first.text_content()
        assert '"why": "the screen is locked"' in det, det

        # Raw: the file's own lines
        page.locator('#logs-raw').check()
        settled(page, lambda: page.locator('#logs-content').is_visible(), lambda v: v)
        assert not page.locator('#logs-readable').is_visible()
        settled(page, lambda: page.locator('#logs-content').text_content(), lambda t: '"action": "socket_project_data"' in t)
        page.locator('#logs-raw').uncheck()
        settled(page, lambda: page.locator('#logs-readable').is_visible(), lambda v: v)

        # Copy takes the readable lines with their date
        text = page.evaluate("() => window.app._logsShownText()")
        assert 'merge runs refused' in text and '{' not in text.split('\n')[0], text
    finally:
        page.evaluate("""() => { try { localStorage.removeItem('lrd_logs_viewer'); } catch (e) {}
            window.app._logViewState = null; window.app.closeLogsModal(); }""")
