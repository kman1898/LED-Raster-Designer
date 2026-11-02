"""Binder and pull-sheet paperwork, round 6 (owner rulings, 2026-10-23).

  * Dense bracket maps stay legible: never under the binder's 14 floor,
    never overlapping, never cut to "S…". A label that will not fit steps
    out by turns; one that will not fit whole even so takes a tag, the
    sheet a key (round 7, tests/test_paper_r7.py); a deep stack closes
    its depth step (and, only where it must, the wall draws smaller) so
    every bracket stays inside the drawing area. A lone bracket's label
    may use the free space beside it.
  * Sheet titles: a 12-processor combined title keeps its "PULL LIST"
    (five lines at 14, then its list cut, never its kind); a 52-letter
    name with no spaces breaks at its letters as the last resort.
  * Free rows, the app and the workbook alike: "TRU-1S", "Tru-1s-50",
    "Tru-1-to-Ether-con", "Edison tails", "Edison → tail" in notes, and a
    non-ASCII letter before an old word.
  * The can't-fit warning says "This wall" for a group.
  * The template dash comment says what dash_spelling does.
  * A service with no distro that prints is off the binder.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_r6.py -q --browser chromium
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402


# ── the xlsx ─────────────────────────────────────────────────────────────

FREE_TYPES = {
    'TRU-1S': 'TRUE1s',
    '4 TRU-1S SPARE': '4 TRUE1s SPARE',
    'Tru-1s-50': 'TRUE1s-50',
    'Tru-1-to-Ether-con': 'TRUE1-to-etherCON',
    'ETHER-CONS': 'etherCONs',
    'Edison tails': 'Edison cables',
    'EDISON TAILS': 'EDISON CABLES',
    'L6-20 Tails': 'L6-20 Cables',
    'Edison -> TRUE1 tails': 'Edison -> TRUE1 cables',
    'Edison → True1 tails': 'Edison → TRUE1 cables',
    'éTru-1': 'éTRUE1',
    'éEther-con': 'éetherCON',
    'Tail rope': 'Tail rope',
    'Safety tail': 'Safety tail',
    'Safety tails': 'Safety tails',
    'Trust': 'Trust',
    'True1st': 'True1st',
    'xTru-1': 'xTru-1',
    'Tru-1s': 'TRUE1s',
    'Ether-con-50': 'etherCON-50',
}

FREE_NOTES = {
    'Edison → tail': 'Edison → cable',
    'Edison -> tails': 'Edison -> cables',
    'spare Edison → tail · Tail rope': 'spare Edison → cable · Tail rope',
    'Tail rope for the Edison → TRUE1 tail': 'Tail rope for the Edison → TRUE1 cable',
    'Safety tail, Edison tails': 'Safety tail, Edison cables',
    '2 TRU-1S; Tru-1-to-Ether-con': '2 TRUE1s; TRUE1-to-etherCON',
    'Tail rope': 'Tail rope',
    'Safety tail': 'Safety tail',
}


def test_free_row_edge_cases_in_the_workbook():
    for typed, want in FREE_TYPES.items():
        assert pull_sheet.free_row_spelling(typed) == want, (typed, pull_sheet.free_row_spelling(typed))
    for typed, want in FREE_NOTES.items():
        assert pull_sheet.free_row_notes_spelling(typed) == want, \
            (typed, pull_sheet.free_row_notes_spelling(typed))
    # \w is ASCII-only, as in JS
    assert pull_sheet._OLD_FREE_TRUE1.flags & re.ASCII
    assert pull_sheet._OLD_FREE_ETHERCON.flags & re.ASCII


def test_dash_spelling_rewrites_its_phrases_inside_a_cell_only():
    d = pull_sheet.dash_spelling
    assert d('Click it. Or use the one-click button - see APPS SCRIPT.') \
        == 'Click it. Or use the one-click button (see APPS SCRIPT).'
    # any other spaced hyphen is the user's
    assert d('SL - SR feed') == 'SL - SR feed'
    src = open(os.path.join(HERE, '..', 'src', 'pull_sheet.py'), encoding='utf-8').read()
    assert 'Exact texts only' not in src


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_paper_r4 import BINDER_JS, SHEETS  # noqa: E402
from test_power_naming import DIST, ev, setup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = async (method, url, body) => (await fetch(url, {
        method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body) })).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', { name: 'WALL A', columns: 10, rows: 6,
        cabinet_width: 200, cabinet_height: 200 });
    await j('POST', '/api/layer/add', { name: 'WALL B', columns: 6, rows: 3,
        cabinet_width: 200, cabinet_height: 200, offset_x: 2600 });
    await j('POST', '/api/layer/add', { name: 'TALL', columns: 10, rows: 60,
        cabinet_width: 200, cabinet_height: 200, offset_x: 5000 });
    await j('POST', '/api/layer/add', { name: 'WIDE', columns: 36, rows: 6,
        cabinet_width: 200, cabinet_height: 200, offset_x: 8000 });
    const p = await j('GET', '/api/project');
    for (const l of p.layers) if (l.name === 'TALL' || l.name === 'WIDE') l.visible = false;
    app.project = p;
    app.selectLayer(p.layers[0]);
    app.renderLayers();
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate(SEED_JS)
    pg.wait_for_function("() => window.app.project.layers.length === 4")
    yield pg, errors
    context.close()


def _reset(pg):
    ev(pg, """for (const l of app.project.layers) {
            l.visible = l.name === 'WALL A' || l.name === 'WALL B'; delete l.group_id; }
        app.project.groups = []; delete app.project.groupNameDisplayByView;
        delete app.project.services; app._distroFaceMemo = null; app._circuitTailCache = null;
        return null;""")


def _only(pg, name, **props):
    ev(pg, """const [name, props] = arg;
        for (const l of app.project.layers) l.visible = l.name === name;
        Object.assign(app.project.layers.find(l => l.name === name), props);
        app._circuitTailCache = null; return null;""", [name, props])


# ── 1. free rows in the app ──────────────────────────────────────────────

def test_free_row_edge_cases_in_the_app_match_the_workbook(page):
    pg, errors = page
    got = ev(pg, """return { types: arg[0].map(t => app.pullFreeRowType(t)),
                             notes: arg[1].map(t => app.pullFreeRowNotes(t)) };""",
             [list(FREE_TYPES), list(FREE_NOTES)])
    assert got['types'] == list(FREE_TYPES.values()), got['types']
    assert got['notes'] == list(FREE_NOTES.values()), got['notes']
    # a non-ASCII letter, a no-break space: the two read alike
    for t in ('éTru-1s', 'Edison tail', 'Edison → tail', 'Edison tails', 'Edison\x1ctail'):
        assert ev(pg, "return app.pullFreeRowType(arg);", t) == pull_sheet.free_row_spelling(t), t
        assert ev(pg, "return app.pullFreeRowNotes(arg);", t) == pull_sheet.free_row_notes_spelling(t), t
    assert errors == [], errors


# ── 2. the can't-fit warning for a group ─────────────────────────────────
# Since 1.6.0 Organized power cuts a row too long for one circuit into
# several, so only a cabinet bigger than a circuit can't fit: these walls'
# 2000 W cabinets are over a 120 V / 10 A circuit on their own.

OPTS_JS = ("Object.assign(app.readBinderOptions(), { scope: { kind: 'show' }, "
           "sides: { power: true, data: false } })")


@pytest.mark.parametrize('mode,sheets', [('group', 'its power sheet says so'),
                                         ('screens', 'its power sheets say so')])
def test_the_cannot_fit_warning_calls_a_group_this_wall(page, mode, sheets):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 2000},
                                     'b': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 2000}})
    ev(pg, """A.group_id = 'g1'; B.group_id = 'g1';
        app.project.groups = [{ id: 'g1', name: 'MAIN WALL', layer_ids: [A.id, B.id] }];
        app.project.groupNameDisplayByView = { power: arg };
        app._circuitTailCache = null; return null;""", mode)
    try:
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert warn.startswith(f"This wall can't fit its circuits, so {sheets}: MAIN WALL (WALL A, WALL B): "), warn
        assert 'This screen' not in warn, warn
        # a one-screen binder of a member prints that member's sheet alone
        warn = ev(pg, "return app.binderCannotFitWarning(Object.assign(app.readBinderOptions(), "
                      "{ scope: { kind: 'screen', layerId: B.id }, sides: { power: true, data: false } }));")
        assert warn.startswith("This wall can't fit its circuits, so its power sheet says so: MAIN WALL"), warn
    finally:
        _reset(pg)
    assert errors == [], errors


def test_the_cannot_fit_warning_for_screens_is_unchanged(page):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 2000},
                                     'b': {'powerVoltage': 120, 'powerAmperage': 10, 'panelWatts': 2000}})
    try:
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert warn.startswith("These screens can't fit their circuits, so their power sheets say so: "), warn
        ev(pg, "B.visible = false; app._circuitTailCache = null; return null;")
        warn = ev(pg, f"return app.binderCannotFitWarning({OPTS_JS});")
        assert warn.startswith("This screen can't fit its circuits, so its power sheet says so: WALL A: "), warn
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 3. titles ────────────────────────────────────────────────────────────

TITLE_JS = """([sheet, title]) => {
    const app = window.app;
    const orig = app._bTitleBlock;
    app._bTitleBlock = function (book, page) { return orig.call(this, book, { ...page, sheetTitle: title }); };
    try {
        const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
            hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
        const plan = app.planBinder(opts);
        const r = app.renderBinderPage(opts, plan.findIndex(p => p.kind === 'power'));
        const tb = r.titleBlock;
        const box = tb.sections.title;
        const drawn = r.record.ops.filter(op => op.op === 'text' && !op.rotate
            && op.x > tb.x && op.x < tb.x + tb.w && op.y > box.y && op.y < box.y + box.h).map(op => ({ text: op.text, y: op.y, size: op.size }));
        return { info: r.textInfo.filter(t => t.text.startsWith(title.split(' ')[0])), drawn, box };
    } finally { app._bTitleBlock = orig; }
}"""

UNITS = [f'H9 {p} {k}' for p in ('SL', 'SR', 'CENTER', 'FLOWN', 'DSL', 'DSR') for k in ('MAIN', 'BACKUP')]
TWELVE = 'PROCESSORS · ' + ', '.join(UNITS) + ' · PULL LIST'
FORTY = 'PROCESSORS · ' + ', '.join(f'H9 STAGE LEFT UNIT {i}' for i in range(1, 41)) + ' · PULL LIST'
NAME52 = 'NORTHUPSTAGELEFTVIDEOWALLSECTIONALPHABRAVOCHARLIE123'


def test_a_twelve_processor_title_keeps_its_kind(page):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    try:
        for sheet in SHEETS:
            got = pg.evaluate(TITLE_JS, [sheet, TWELVE])
            assert len(got['info']) == 1, (sheet, got['info'])
            info = got['info'][0]
            assert info['text'] == TWELVE and info['size'] >= 14, (sheet, info)
            assert got['drawn'][-1]['text'].endswith('PULL LIST'), (sheet, got['drawn'])
            assert not [d for d in got['drawn'] if d['text'].endswith('…')], (sheet, got['drawn'])
            assert len(got['drawn']) <= 5, (sheet, got['drawn'])
            # inside the title's box, the lines apart
            for d in got['drawn']:
                assert got['box']['y'] + d['size'] * 0.7 <= d['y'] <= got['box']['y'] + got['box']['h'] - 2, (sheet, d)
            ys = [d['y'] for d in got['drawn']]
            assert all(b - a >= info['size'] for a, b in zip(ys, ys[1:])), (sheet, ys)
            # far too long even for five lines: the list is cut, the kind kept
            got = pg.evaluate(TITLE_JS, [sheet, FORTY])
            lines = [d['text'] for d in got['drawn']]
            assert len(lines) <= 5 and lines[-1] == 'PULL LIST', (sheet, lines)
            assert lines[-2].endswith('…'), (sheet, lines)
            assert all(d['size'] >= 14 for d in got['drawn']), (sheet, got['drawn'])
    finally:
        _reset(pg)
    assert errors == [], errors


def test_a_long_name_with_no_spaces_breaks_at_its_letters(page):
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[DIST], walls={'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    title = f'{NAME52} · POWER · FRONT VIEW'
    assert len(NAME52) == 52
    try:
        for sheet in SHEETS:
            got = pg.evaluate(TITLE_JS, [sheet, title])
            info = got['info'][0]
            assert info['text'] == title and info['size'] >= 14, (sheet, info)
            lines = [d['text'] for d in got['drawn']]
            assert not [t for t in lines if t.endswith('…')], (sheet, lines)
            assert ''.join(lines).replace(' ', '') == title.replace(' ', ''), (sheet, lines)
            assert lines[-1].endswith('FRONT VIEW'), (sheet, lines)
            # the name alone, too
            got = pg.evaluate(TITLE_JS, [sheet, NAME52])
            assert got['info'][0]['text'] == NAME52, (sheet, got['info'])
            assert not [d for d in got['drawn'] if d['text'].endswith('…')], (sheet, got['drawn'])
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 4. brackets ──────────────────────────────────────────────────────────

SR = {'id': 'd1', 'name': 'SR', 'ratingA': 400, 'system': '120/208',
      'outputRows': [{'id': 'r1', 'connector': 'soca', 'count': 6, 'coupling': 'll', 'breakerA': 20}]}

BRACKETS_JS = """(sheet) => {
    const app = window.app;
    const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
        hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'power');
    const r = app.renderBinderPage(opts, i);
    const da = app._bGeo(r.sheet, true).da;
    const labels = r.record.ops.filter(op => op.op === 'text' && op.rotate)
        .map(op => ({ text: op.text, size: op.size }));
    return { brackets: r.brackets, da, map: r.map, labels };
}"""


def _check_brackets(sheet, out, n):
    br, da = out['brackets'], out['da']
    assert len(br) == n, (sheet, len(br))
    for b in br:
        # legible and whole: the floor, the name never cut - or, where a
        # label will not fit whole (round 7), its tag, the key saying the
        # rest (tests/test_paper_r7.py)
        assert b['size'] >= 14, (sheet, b)
        if 'tag' in b:
            assert b['lines'] == [b['tag']] and b['full'].startswith(b['name'] + ' · '), (sheet, b)
        else:
            assert b['lines'][0].startswith(b['name'][:3]), (sheet, b)
            assert ''.join(b['lines']).replace(' ', '').startswith(b['name'].replace(' ', '')), (sheet, b)
        assert not [t for t in b['lines'] if t.endswith('…')], (sheet, b)
        # inside its room, centred on its bracket (an edge label slid
        # inward along it, round 7, says how far)
        assert b['labelY2'] - b['labelY1'] <= b['room'] + 0.5, (sheet, b)
        mid = (b['y1'] + b['y2']) / 2 + b.get('shift', 0)
        assert abs((b['labelY1'] + b['labelY2']) / 2 - mid) < 1, (sheet, b)
        # inside the drawing area
        assert da['x'] <= b['inkX1'] and b['inkX2'] <= da['x'] + da['w'], (sheet, b, da)
        assert da['y'] <= b['labelY1'] and b['labelY2'] <= da['y'] + da['h'], (sheet, b, da)
    assert not [t for t in out['labels'] if t['text'].endswith('…') or t['size'] < 14], (sheet, out['labels'])
    # never overlapping: along a distance, and across distances where they
    # stand side by side
    for a in br:
        for b in br:
            if a is b or a['side'] != b['side']:
                continue
            ya = (min(a['labelY1'], a['y1']), max(a['labelY2'], a['y2']))
            yb = (min(b['labelY1'], b['y1']), max(b['labelY2'], b['y2']))
            if a['depth'] == b['depth']:
                if a['y1'] < b['y1']:
                    assert a['labelY2'] <= b['labelY1'] + 0.5, (sheet, a, b)
                continue
            if min(ya[1], yb[1]) - max(ya[0], yb[0]) <= 0:
                continue
            assert min(a['inkX2'], b['inkX2']) - max(a['inkX1'], b['inkX1']) <= 0.5, (sheet, a, b)


@pytest.mark.parametrize('splits,n', [(list(range(1, 60)), 60), (list(range(2, 60, 2)), 30)])
def test_a_dense_bracket_map_stays_legible(page, splits, n):
    """A 10 x 60 wall, a circuit per row, a multi per circuit (or per two):
    every label at 14 or more, whole, never overlapping, on every sheet -
    where they will not all fit whole, every bracket a tag and the sheet a
    key (round 7)."""
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[], walls={})
    _only(pg, 'TALL', powerAmperage=12.5, powerSocaSplits=splits)
    try:
        for sheet in SHEETS:
            out = pg.evaluate(BRACKETS_JS, sheet)
            _check_brackets(sheet, out, n)
            # the whole label (its length nearer the bracket where it takes
            # two lines), else tags on every bracket - never "S…", never the
            # name with its length dropped
            tagged = [b for b in out['brackets'] if 'tag' in b]
            assert len(tagged) in (0, n), (sheet, out['brackets'])
            for b in out['brackets']:
                assert b['lines'] == [b['tag']] if tagged else (
                    b['lines'] in ([f"{b['name']} · no length"], [b['name'], 'no length'])), (sheet, b)
    finally:
        _reset(pg)
    assert errors == [], errors


def test_the_owners_two_distro_case_is_kept(page):
    """Two SR distros, 10 x 60, six-row multis: the wall the same size as a
    map without brackets would draw it, every label legible - and whole,
    its length with it (round 7), a crowded label stepping out a turn."""
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[SR, dict(SR, id='d2')], walls={})
    dist = {str(i): ('d1' if i <= 5 else 'd2') for i in range(1, 11)}
    num = {str(i): (i if i <= 5 else i - 5) for i in range(1, 11)}
    _only(pg, 'TALL', powerAmperage=12.5, powerSocaDistro=dist, powerSocaNumber=num, powerSocaSplits=[])
    try:
        for sheet in SHEETS:
            out = pg.evaluate(BRACKETS_JS, sheet)
            _check_brackets(sheet, out, 10)
            # at most one turn out, the brackets' room left as it was
            assert {b['depth'] for b in out['brackets']} <= {0, 1}, (sheet, out['brackets'])
            assert {b['compact'] for b in out['brackets']} == {0}, (sheet, out['brackets'])
            for b in out['brackets']:
                assert b['lines'] in ([f"{b['name']} · no length"], [b['name'], 'no length']), (sheet, b)
            if sheet in ('archc', 'archd'):
                assert all(b['lines'] == [f"{b['name']} · no length"] for b in out['brackets']), out['brackets']
    finally:
        _reset(pg)
    assert errors == [], errors


@pytest.mark.parametrize('splits,n', [(list(range(1, 36)), 36), (list(range(1, 19)), 21)])
def test_a_deep_bracket_stack_stays_on_the_sheet(page, splits, n):
    """A 36 x 6 wall, the vertical pattern, a circuit per column, single
    circuit multis: every bracket spans the same rows, so they stack 18
    deep. Nothing leaves the drawing area or reaches the title block."""
    pg, errors = page
    _reset(pg)
    setup(pg, distros=[], walls={})
    _only(pg, 'WIDE', powerAmperage=10, powerFlowPattern='tl-v', powerSocaSplits=splits)
    try:
        for sheet in SHEETS:
            out = pg.evaluate(BRACKETS_JS, sheet)
            _check_brackets(sheet, out, n)
            assert max(b['depth'] for b in out['brackets']) >= 8, (sheet, out['brackets'])
            m = out['map']
            assert m['x'] >= out['da']['x'] and m['x'] + m['w'] <= out['da']['x'] + out['da']['w'], (sheet, m)
    finally:
        _reset(pg)
    assert errors == [], errors


LONG = 'UPSTAGE LEFT DISTRIBUTION RACK FOR VIDEO WALL NUMBER ONE A'


@pytest.mark.parametrize('name', [LONG, LONG.replace(' ', '')])
def test_a_lone_bracket_uses_the_free_space(page, name):
    pg, errors = page
    _reset(pg)
    assert len(LONG) == 58
    setup(pg, distros=[dict(SR, name=name)], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    try:
        ev(pg, "B.visible = false; app._circuitTailCache = null; return null;")
        for sheet in SHEETS:
            out = pg.evaluate(BRACKETS_JS, sheet)
            _check_brackets(sheet, out, 1)
            b = out['brackets'][0]
            assert b['name'].startswith(name), b
            assert b['size'] >= 14 and ' '.join(b['lines']).startswith(b['name']), (sheet, b)
    finally:
        _reset(pg)
    assert errors == [], errors


# ── 5. an empty service ──────────────────────────────────────────────────

def test_a_service_with_nothing_printing_is_off_the_binder(page):
    pg, errors = page
    _reset(pg)
    sl = dict(DIST, id='d1', name='SL', serviceId='s1')
    spare = {'id': 'd2', 'name': 'SPARE', 'ratingA': 100, 'system': '120/208', 'serviceId': 's2'}
    setup(pg, distros=[sl, spare], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 2}}})
    svc = ("app.project.services = [{ id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208', voltage: 208, phase: 3 },"
           " { id: 's2', name: 'GENNY', ratingA: 400, system: '120/208', voltage: 208, phase: 3 },"
           " { id: 's3', name: 'SHORE', ratingA: 200, system: '120/208', voltage: 208, phase: 3 }];"
           " app._distroFaceMemo = null; app._circuitTailCache = null; return null;")
    try:
        ev(pg, svc)
        b = pg.evaluate(BINDER_JS, {'cover': True, 'kinds': ['overview', 'service']})
        services = [p for p in b['plan'] if p['kind'] == 'service']
        assert [p['title'] for p in services] == ['Service - HOUSE'], b['plan']
        texts = ' '.join(t for p in b['pages'] for t in p['logged'])
        assert 'GENNY' not in texts and 'SHORE' not in texts, \
            [t for p in b['pages'] for t in p['logged'] if 'GENNY' in t or 'SHORE' in t]
        # the 4.n sheets close up: no gap where the services were
        nums = ev(pg, """const opts = Object.assign(app.readBinderOptions(), { sheet: 'tabloid',
                scope: { kind: 'show' }, hardware: true, pull: true, cover: true, wiring: false,
                sides: { power: true, data: false } });
            return app.planBinder(opts).filter(p => String(p.number).startsWith('4.')).map(p => [p.number, p.kind]);""")
        assert nums and nums[0] == ['4.1', 'service'], nums
        assert [n for n, _ in nums] == [f'4.{i}' for i in range(1, len(nums) + 1)], nums
        # a feeder set on SPARE brings GENNY back
        ev(pg, "app.project.distros.find(d => d.id === 'd2').feeder = { ft: 50 };"
               " app._distroFaceMemo = null; app.getDistros(); return null;")
        b = pg.evaluate(BINDER_JS, {'kinds': ['service']})
        titles = [p['title'] for p in b['plan'] if p['kind'] == 'service']
        assert titles and 'GENNY' in ' '.join(titles) and 'SHORE' not in ' '.join(titles), titles
    finally:
        _reset(pg)
    assert errors == [], errors
