"""A fiber extension names its mode, the way the trunk it extends does.

QA of 1.6.0 beta.6: a CVT10-S and a CVT10-M, each on a TAC with a 120' fan-out,
printed ONE totals row, "Fan-out · ST to LC duplex", qty 2: a single mode piece
and a multimode piece counted as one cable, on the pull list, the xlsx and the
binder. The changelog says the pull sheet, binder and box sheet name the mode
on every fiber cable (owner, 2026-11-04). So every extension reads its mode off
the cable it extends, and S and M never merge. Two of one mode still do. The
typed length stays as typed: an extension is not rounded to stock.

A loop strip folded over a single mode box and a multimode box reads both, as
the sheet under it does.

Run locally:
    python -m pytest tests/test_fiber_extension_mode.py -q
"""
import base64
import io
import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")
openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()

    # No real dialog on the desktop. The open answers "unavailable", so the
    # page takes its own file input.
    def answer(body):
        return lambda r: r.fulfill(status=200, content_type='application/json',
                                   body=body)

    for kind, body in (('save-file', '{"cancelled": true, "path": null}'),
                       ('select-directory', '{"cancelled": true, "path": null}'),
                       ('open-file', '{"ok": false, "cancelled": false}')):
        pg.route(f'**/api/native-dialog/{kind}', answer(body))
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => window.app && window.app._initialLoadComplete === true",
        timeout=20000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


# H9, H_4xfiber, the boxes asked for, a screen on each box's first ports.
SEED_JS = """async ([mode, devices]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables; delete proj.snakes;
    proj.cableStock = null;
    await j('PUT', '/api/project', proj);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    if (mode) await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode});
    for (const body of devices) {
        st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, body);
    }
    const boxes = st.processors[0].slots[0].card.cvts.map(b => b.id);
    for (const [i, id] of boxes.entries()) {
        await j('POST', '/api/layer/add', {name: `W${i + 1}`, columns: 4,
            rows: 4, cabinet_width: 200, cabinet_height: 200,
            processorType: 'novastar-armor', offset_x: i * 1000});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_ext_mode_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    const card = app._processorsResolved.find(p => p.id === pid).slots[0].card;
    if (!mode) {
        for (const [i, id] of boxes.entries()) {
            const first = card.cvts.find(b => b.id === id).ports[0].number;
            await app._assignmentRequest('/api/port-assignments/place-overflow',
                'POST', {layerId: String(app.project.layers[i].id), cardId: cid,
                         firstPort: first, lastPort: first + 3});
        }
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Extension Mode Seed');
    return {pid, cid, boxes};
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullList()));
}"""

XLSX_JS = """async () => {
    const app = window.app;
    app._circuitTailCache = null;
    const pullList = app.buildPullSheet();
    const r = await fetch('/api/export/pull-sheet', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({project_name: 'Mode', pull_list: pullList})});
    const bytes = new Uint8Array(await r.arrayBuffer());
    let text = '';
    bytes.forEach(b => { text += String.fromCharCode(b); });
    return btoa(text);
}"""

SINGLE = 'Fan-out · ST to LC duplex · Single mode'
MULTI = 'Fan-out · ST to LC duplex · Multimode'


def _seed(pg, mode, devices):
    ids = pg.evaluate(SEED_JS, [mode, devices])
    pg.wait_for_timeout(500)
    return ids


def _field(pg, key):
    return pg.locator(f'[data-lrd-field="{key}"]')


def _tac_with_a_fan_out(pg, box, ft='120'):
    """New TAC, 12, ST, then + Extension, Fan-out, the length, in the box's
    cable sheet with the person's own clicks and keys."""
    _field(pg, f'data-cable-sheet-{box}').first.click()
    _field(pg, f'fiber-link-cable-{box}-p1').select_option('new:tac')
    _field(pg, f'fiber-new-{box}-p1-strands-12').click()
    ask = _field(pg, f'fiber-new-{box}-p1-ft')
    ask.fill('1000')
    ask.press('Enter')
    _field(pg, f'fiber-new-{box}-p1-conn-ST').click()
    _field(pg, f'fiber-ext-add-{box}-p1').click()
    kind = _field(pg, f'fiber-ext-kind-{box}-p1')
    kind.wait_for()
    assert kind.input_value() == 'fanout'
    length = _field(pg, f'fiber-ext-ft-{box}-p1')
    length.fill(ft)
    length.press('Enter')
    pg.wait_for_timeout(500)


def _close_sheet(pg, box):
    _field(pg, f'data-cable-sheet-{box}').first.click()
    pg.wait_for_timeout(200)


def _extension_rows(rows):
    return sorted([r['type'], r['length'], r['qty'], r['label']] for r in rows
                  if r['type'].startswith('Fan-out'))


def _open_as_saved(pg, tmp_path, name):
    saved = pg.evaluate("() => JSON.parse(window.app.serializeProjectForFile())")
    saved['name'] = name
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(saved), encoding='utf-8')
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    pg.wait_for_function(
        f"() => window.app.project && window.app.project.name === {json.dumps(name)}",
        timeout=10000)
    pg.wait_for_timeout(1000)
    pg.evaluate("() => window.app.refreshProcessors()")
    pg.wait_for_timeout(300)


def test_a_single_mode_and_a_multimode_extension_never_merge(page, tmp_path):
    pg, errors = page
    ids = _seed(pg, None, [{'deviceId': 'novastar-cvt10', 'pair': False},
                           {'deviceId': 'novastar-cvt10-m', 'pair': False}])
    s, m = ids['boxes']
    _tac_with_a_fan_out(pg, s)
    cap = pg.locator(f'[data-lrd-fiber-ext="{s}:p1"] .hw-dock-fiber-ext-cap')
    assert cap.text_content() == 'OPT 1 extension · Single mode'
    _close_sheet(pg, s)
    _tac_with_a_fan_out(pg, m)
    cap = pg.locator(f'[data-lrd-fiber-ext="{m}:p1"] .hw-dock-fiber-ext-cap')
    assert cap.text_content() == 'OPT 1 extension · Multimode'
    _close_sheet(pg, m)

    want = [[MULTI, "120'", 1, 'CVT10-M B (OPT 1)'],
            [SINGLE, "120'", 1, 'CVT10-S A (OPT 1)']]
    out = pg.evaluate(LIST_JS)
    assert _extension_rows(out['totals']) == want, out['totals']
    # the hardware's own list and every position read the same
    hardware = [r for h in out['hardware'] for r in h['rows']]
    assert _extension_rows(hardware) == want, out['hardware']
    placed = [r for p in out['positions'] for r in p['rows']]
    assert _extension_rows(placed) == want, out['positions']

    # the xlsx
    book = openpyxl.load_workbook(io.BytesIO(base64.b64decode(
        pg.evaluate(XLSX_JS))))
    cells = {str(c.value) for ws in book.worksheets for row in ws.iter_rows()
             for c in row if c.value is not None}
    assert SINGLE in cells and MULTI in cells, sorted(
        c for c in cells if 'Fan-out' in c)
    assert 'Fan-out · ST to LC duplex' not in cells

    # the binder: the pull rows of the Fiber page, its extension labels, and
    # the processor page's Fiber connections
    binder = pg.evaluate("""(pid) => {
        const app = window.app;
        const page = app.binderFiberPage();
        const proc = app._processorsResolved.find(p => p.id === pid);
        return { pull: page.pull,
                 labels: page.procs[0].links.map(l => [l.box, l.extension]),
                 rows: app._bFiberConnectionRows(proc).map(r => r.cells[4]) };
    }""", ids['pid'])
    assert sorted([r['type'], r['length'], r['qty']] for r in binder['pull']
                  if r['type'].startswith('Fan-out')) == [
        [MULTI, "120'", 1], [SINGLE, "120'", 1]], binder
    assert ['CVT10-S A', "Fan-out 120' · Single mode"] in binder['labels'], binder
    assert ['CVT10-M B', "Fan-out 120' · Multimode"] in binder['labels'], binder
    assert any(r.endswith("ext Fan-out 120' · ST to LC duplex · Single mode")
               for r in binder['rows']), binder
    assert any(r.endswith("ext Fan-out 120' · ST to LC duplex · Multimode")
               for r in binder['rows']), binder

    # undo takes the length back, redo brings the row back whole
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(800)
    assert _extension_rows(pg.evaluate(LIST_JS)['totals']) == [
        [MULTI, '', 1, 'CVT10-M B (OPT 1)'],
        [SINGLE, "120'", 1, 'CVT10-S A (OPT 1)']]
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(800)
    assert _extension_rows(pg.evaluate(LIST_JS)['totals']) == want

    # a save and a reopen read the same
    _open_as_saved(pg, tmp_path, 'FiberExtMode')
    assert _extension_rows(pg.evaluate(LIST_JS)['totals']) == want
    assert errors == []


def test_two_of_one_mode_are_one_row_and_the_length_stays_as_typed(page):
    """Identical extensions of one mode still count up. A typed 123' stays
    123': stock lengths round a trunk, never an extension."""
    pg, errors = page
    ids = _seed(pg, None, [{'deviceId': 'novastar-cvt10', 'pair': False},
                           {'deviceId': 'novastar-cvt10', 'pair': False},
                           {'deviceId': 'novastar-cvt10-m', 'pair': False}])
    a, b, m = ids['boxes']
    for box in (a, b, m):
        _tac_with_a_fan_out(pg, box, '123')
        _close_sheet(pg, box)
    rows = _extension_rows(pg.evaluate(LIST_JS)['totals'])
    assert [r[:3] for r in rows] == [[MULTI, "123'", 1], [SINGLE, "123'", 2]], rows
    assert errors == []


OLD_KEY = "Fan-out · ST to LC duplex|120'"


def test_an_edit_on_the_old_row_follows_it_and_a_hide_covers_both(page):
    """A beta's pull sheet edit is keyed on the row as it printed, with no
    mode (owner, 2026-10-21: edits follow their rows when the rows are
    renamed). On a position with one mode it is that row. Where the old row
    is two rows now, a hide covers both, and a count, which can't say which
    it meant, is stale."""
    pg, errors = page
    ids = _seed(pg, None, [{'deviceId': 'novastar-cvt10', 'pair': False},
                           {'deviceId': 'novastar-cvt10-m', 'pair': False}])
    s, m = ids['boxes']
    for box in (s, m):
        _tac_with_a_fan_out(pg, box)
        _close_sheet(pg, box)
    out = pg.evaluate("""([key, single, multi]) => {
        const app = window.app;
        app._circuitTailCache = null;
        const list = app.buildPullList();
        const pos = list.positions.find(p => p.rows.some(r => r.type === single));
        const pk = app.pullPositionKey(pos);
        const rowsOf = (type) => {
            app._circuitTailCache = null;
            const sheet = app.buildPullSheet();
            const at = sheet.positions.find(p => app.pullPositionKey(p) === pk);
            return at.rows.filter(r => r.type === type).map(r => r.qty);
        };
        const put = (rows) => {
            app.project.pullSheetEdits = {positions: {[pk]: {rows, added: []}}};
        };
        put([{key, qty: 5}]);
        const counted = rowsOf(single);
        put([{key, removed: true}]);
        const hidden = rowsOf(single);
        delete app.project.pullSheetEdits;
        const both = new Set([`${single}|120'`, `${multi}|120'`]);
        const one = new Set([`${single}|120'`]);
        const noMode = new Set([key]);
        return {counted, hidden, both: app._pullEditHits(key, both),
                one: app._pullEditHits(key, one),
                noMode: app._pullEditHits(key, noMode),
                today: app._pullEditNeedsRows(`${single}|120'`),
                trunk: app._pullEditNeedsRows("TAC 12 · ST|1000'")};
    }""", [OLD_KEY, SINGLE, MULTI])
    assert out['counted'] == [5], out
    assert out['hidden'] == [], out
    assert sorted(out['both']) == sorted([f"{SINGLE}|120'", f"{MULTI}|120'"]), out
    assert out['one'] == [f"{SINGLE}|120'"], out
    assert out['noMode'] == [OLD_KEY], out
    assert out['today'] is False and out['trunk'] is False, out
    assert errors == []


def test_a_box_with_no_stated_mode_says_none(page):
    """A cable whose boxes state no mode prints as it did: nothing guessed."""
    pg, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const ext = {kind: 'fanout', boxEnd: 'LC duplex', ft: 10};
        const cable = {id: 'nobody-on-it', kind: 'tac', strands: 12, connector: 'ST'};
        return [app.fiberExtensionType(ext, cable), app.fiberExtensionText(ext, cable)];
    }""")
    assert out == ['Fan-out · ST to LC duplex', "Fan-out · ST to LC duplex · 10'"]
    assert errors == []


def test_a_folded_loop_of_both_modes_reads_both(page):
    """H_4xfiber in Backup: a CVT10-S on OPT 1 and its backup a CVT10-M on
    OPT 3 are one strip. Folded it is all that shows, so its tag says what
    the sheet says. A loop of one mode still reads the one word."""
    pg, errors = page
    ids = _seed(pg, 'backup', [{'deviceId': 'novastar-cvt10', 'pair': False},
                               {'deviceId': 'novastar-cvt10', 'pair': False},
                               {'deviceId': 'novastar-cvt10-m', 'pair': False}])
    near = ids['boxes'][0]
    sec = f'hwdock-box-{near}'
    strip = pg.locator(f'[data-hwdock="loop-{near}"]')
    strip.wait_for()
    arrow = pg.locator(f'[data-lrd-sec-id="{sec}"] > .lrd-sec-head .lrd-sec-arrow')
    if not pg.evaluate("""(sec) => document.querySelector(`[data-lrd-sec-id="${sec}"]`)
            .classList.contains('lrd-sec-collapsed')""", sec):
        arrow.click()
        pg.wait_for_timeout(400)
    tag = strip.locator('.hw-dock-fiber-mode')
    assert tag.count() == 1 and tag.is_visible()
    words = 'CVT10-S A Single mode, CVT10-M C Multimode'
    assert tag.text_content() == words
    assert tag.get_attribute('data-fiber-mode') == 'mixed'
    # the sheet under the same strip says the same: the folded header's own
    # sheet button, the open rows' being hidden with them
    button = _field(pg, f'data-cable-sheet-fold-{near}')
    button.click()
    sheet = _field(pg, f'fiber-mode-{near}')
    sheet.wait_for()
    assert sheet.text_content() == words
    button.click()
    pg.wait_for_timeout(300)
    arrow.click()
    pg.wait_for_timeout(300)

    ids = _seed(pg, 'backup', [{'deviceId': 'novastar-cvt10', 'pair': True}])
    near = ids['boxes'][0]
    tag = pg.locator(f'[data-hwdock="loop-{near}"] .hw-dock-fiber-mode')
    tag.wait_for()
    assert tag.text_content() == 'Single mode'
    assert tag.get_attribute('data-fiber-mode') == 'single'
    assert errors == []
