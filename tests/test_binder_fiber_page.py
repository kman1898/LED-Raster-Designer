"""The binder's FIBER page (app-binder-fiber.js): every fiber link of the
show on one sheet, processor to breakout box (owner, 2026-11-03: "just a
fiber page if fiber is used. So it can all be shown together processor to
breakout").

Pinned here, on synthetic shows only:

  - the page prints only where a link of the show is on a fiber cable, once,
    right after the screens and before the pull sheets (owner, 2026-11-04:
    "the fiber patch sheet also needs to come before the pull sheets"), and
    only when the dialog's Fiber tick asks for it - never in a single
    screen's set;
  - the sheets number in the order they print: with the page, 1.1, 2.n
    screens, 3.n Fiber, 4.n pull, 5.n hardware; without it, pull 3.n and
    hardware 4.n - never a hole - and the Overview's CONTENTS lists the same;
  - it can never disagree with the rest of the binder: every link it draws
    is a row of the processor page's Fiber connections table (the output,
    the breakout, the strands at either end), its strand maps put each
    strand on the link the processor pages' strand maps do and count the
    same spares, and its pull list is the show pull list's fiber rows;
  - a show with that much fiber draws TWO columns of processors side by
    side, on one sheet where they fit ("two drawings of columns if have
    that much fiber"), and continues only past that;
  - the Border and title block switch, on or off: off, the drawing takes
    the column's room and the bubble names the sheet;
  - nothing it strokes is drawn through anything it writes, and nothing it
    writes is cut.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_binder_fiber_page.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_fiber_connections import SEED_JS  # noqa: E402
from test_binder_ink import RULE_JS, _struck  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _opts(**kw):
    opts = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
            'fiber': True, 'titleBlock': True}
    opts.update(kw)
    return opts


SCREEN_KINDS = ('power', 'data', 'wiring')
HARDWARE_KINDS = ('service', 'distro', 'processor', 'totals')

PLAN_JS = """(opts) => window.app.planBinder(opts).map(p => ({
    number: p.number, kind: p.kind, title: p.title, scale: p.scale, fiber: p.fiber || null}))"""

# Every Fiber sheet painted: its record's ops, the texts it logged and its
# layout log.
PAINT_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    plan.forEach((p, i) => {
        if (p.kind !== 'fiber') return;
        const r = app.renderBinderPage(opts, i);
        out.push({number: p.number, title: p.title, texts: r.texts, textInfo: r.textInfo,
                  fiber: r.fiber, titleBlock: r.titleBlock, bubble: r.bubble,
                  da: r.sheet ? null : null});
    });
    return out;
}"""

# A show with that much fiber: `n` SX40s, each XD on its own processor's
# TAC (12, LC duplex, 300 ft), XD A's link with a 10 ft fan-out.
MANY_JS = """async (n) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 8, rows: 8,
                                       cabinet_width: 200, cabinet_height: 200});
    const last = (st) => st.processors[st.processors.length - 1];
    const cable = (st) => st.fiberCables[st.fiberCables.length - 1];
    for (let i = 0; i < n; i++) {
        let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: `RACK ${i + 1}`});
        const sx = last(st).id;
        const xds = last(st).slots[0].card.cvts.map(b => b.id);
        st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300,
                                                   connector: 'LC duplex', link: {boxId: xds[0], key: 'p1'}});
        const tac = cable(st);
        for (const b of xds.slice(1)) {
            await j('PUT', `/api/processors/${sx}/cvts/${b}/fiber-links/p1`, {cable: tac.id});
        }
        await j('PUT', `/api/processors/${sx}/cvts/${xds[0]}/fiber-links/p1`,
                {extension: {kind: 'fanout', ft: 10}});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Page Seed');
    return (app._processorsResolved || []).length;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    """The Fiber connections module's show - an SX40 with its backup unit
    (TAC A, TAC B, an opticalCON DUO, copper, a link with nothing picked),
    an H9 (a BiDi CVT10 on a TAC in numbers, a CVT4K-S on an MTP), an
    SQ200 with a QD-S and its backup - plus a 10 ft fan-out on XD A's X1."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.evaluate("""async ([sx, box]) => {
        await fetch(`/api/processors/${sx}/cvts/${box}/fiber-links/p1`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({extension: {kind: 'fanout', ft: 10}})});
        await window.app.refreshProcessors();
    }""", [ids['sx'], ids['xds'][0]])
    from conftest import settled
    settled(pg, lambda: pg.evaluate(
        "(sq) => !!(window.app._processorsResolved || []).find(p => p.id === sq)", ids['sq']),
        bool, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


# ── the page is there only with fiber ────────────────────────────────────

def test_the_page_prints_only_with_fiber_once_after_the_screens(page):
    pg, ids = page
    plan = pg.evaluate(PLAN_JS, _opts())
    kinds = [p['kind'] for p in plan]
    assert kinds.count('fiber') == 1, kinds
    at = kinds.index('fiber')
    # right behind the last screen sheet, ahead of every pull and hardware one
    assert at == 1 + max(i for i, k in enumerate(kinds) if k in SCREEN_KINDS), kinds
    assert at < kinds.index('pull') < kinds.index('processor'), kinds
    fiber = plan[at]
    assert fiber['number'] == '3.1' and fiber['title'] == 'Fiber', fiber
    # every processor that feeds a breakout box is drawn, in tray order;
    # the DUAL H9 has boxes but nothing picked, so no link to draw
    drawn = [t for col in fiber['fiber']['procs'] for t in col]
    assert drawn == ['WALL SR', 'NOVA', 'SQ A'], drawn
    # the Fiber tick off, a single screen's set: no page
    assert 'fiber' not in [p['kind'] for p in pg.evaluate(PLAN_JS, _opts(fiber=False))]
    layer = pg.evaluate("window.app.project.layers[0].id")
    assert 'fiber' not in [p['kind'] for p in pg.evaluate(
        PLAN_JS, _opts(scope={'kind': 'screen', 'layerId': layer}))]
    # the same show with no fiber cable (copper and empty links only, read
    # in the page; nothing is written): no page, and no tick offered
    out = pg.evaluate("""(opts) => {
        const app = window.app;
        const keep = app.project.fiberCables;
        app.project.fiberCables = [];
        try {
            return {uses: app.binderUsesFiber(),
                    kinds: app.planBinder(opts).map(p => p.kind)};
        } finally { app.project.fiberCables = keep; }
    }""", _opts())
    assert out['uses'] is False and 'fiber' not in out['kinds'], out
    assert pg.evaluate("window.app.binderUsesFiber()") is True
    assert ids['errors'] == []


def _subject(kind):
    if kind in SCREEN_KINDS:
        return 'screens'
    return 'hardware' if kind in HARDWARE_KINDS else kind


def _series(plan):
    """[(subject, series)] in print order, each series' sheets checked to run
    n.1, n.2 ... with no hole."""
    runs = []
    for p in plan:
        major, minor = p['number'].split('.')
        subject = _subject(p['kind'])
        if not runs or runs[-1][0] != subject:
            runs.append((subject, major, []))
        assert runs[-1][1] == major, (p, plan)
        runs[-1][2].append(int(minor))
    for subject, major, minors in runs:
        assert minors == list(range(1, len(minors) + 1)), (subject, major, minors)
    return [(subject, major) for subject, major, _m in runs]


# The Overview's CONTENTS, every (number, title) row as the sheet prints it,
# in the order it prints them - from its first CONTENTS heading on (it may
# run in columns, "CONTENTS 1", "CONTENTS 2"), each sheet number followed by
# its title - and the plan's own (number, title) to hold them to.
CONTENTS_JS = r"""(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts).map(p => [p.number, p.sheetTitle]);
    const texts = app.renderBinderPage(opts, 0).texts;
    const c = texts.findIndex(t => /^CONTENTS( \d+)?$/.test(t));
    const listed = [];
    if (c >= 0) {
        for (let i = c; i < texts.length - 1; i++) {
            if (/^\d+\.\d+$/.test(texts[i])) listed.push([texts[i], texts[i + 1]]);
        }
    }
    return {plan, listed};
}"""


def test_the_sheets_number_in_print_order_fiber_3_pull_4_hardware_5_and_no_gap_without_it(page):
    """With the Fiber page: 1.1 the Overview, 2.n the screens, 3.n Fiber,
    4.n pull, 5.n hardware. Without it (the tick off) pull stays 3.n and the
    hardware 4.n, as before the page moved; with the pull sheets off the
    hardware follows the Fiber page as 4.n. The CONTENTS lists the same
    numbers in the same order."""
    pg, ids = page
    with_fiber = pg.evaluate(PLAN_JS, _opts())
    assert _series(with_fiber) == [('overview', '1'), ('screens', '2'), ('fiber', '3'),
                                   ('pull', '4'), ('hardware', '5')],         [(p['kind'], p['number']) for p in with_fiber]
    without = pg.evaluate(PLAN_JS, _opts(fiber=False))
    assert _series(without) == [('overview', '1'), ('screens', '2'), ('pull', '3'),
                                ('hardware', '4')], [(p['kind'], p['number']) for p in without]
    # the same sheets either way, the Fiber page aside
    assert [(p['kind'], p['title']) for p in without] ==         [(p['kind'], p['title']) for p in with_fiber if p['kind'] != 'fiber']
    no_pull = pg.evaluate(PLAN_JS, _opts(pull=False))
    assert _series(no_pull) == [('overview', '1'), ('screens', '2'), ('fiber', '3'),
                                ('hardware', '4')], [(p['kind'], p['number']) for p in no_pull]
    # the Overview's contents: every sheet, in this order, by these numbers
    for opts, plan in ((_opts(), with_fiber), (_opts(fiber=False), without)):
        out = pg.evaluate(CONTENTS_JS, opts)
        assert out['listed'] == out['plan'], out
        assert [n for n, _t in out['listed']] == [p['number'] for p in plan], out
    listed = pg.evaluate(CONTENTS_JS, _opts())['listed']
    assert [row for row in listed if row[1] == 'FIBER'] == [['3.1', 'FIBER']], listed
    assert listed.index(['3.1', 'FIBER']) == [p['kind'] for p in with_fiber].index('fiber'), listed
    assert ids['errors'] == []


def test_the_dialog_offers_the_fiber_tick_only_with_fiber(page):
    pg, _ids = page
    try:
        pg.evaluate("window.app.openExportModal('binder')")
        pg.wait_for_function("document.getElementById('export-format').value === 'binder'")
        shown = pg.evaluate("""() => {
            const l = document.getElementById('export-binder-fiber-label');
            return {display: l.style.display, ticked: document.getElementById('export-binder-fiber').checked,
                    opts: window.app.readBinderOptions().fiber};
        }""")
        assert shown == {'display': 'flex', 'ticked': True, 'opts': True}, shown
        hidden = pg.evaluate("""() => {
            const app = window.app;
            const keep = app.project.fiberCables;
            app.project.fiberCables = [];
            try {
                app.syncBinderControls();
                return document.getElementById('export-binder-fiber-label').style.display;
            } finally { app.project.fiberCables = keep; app.syncBinderControls(); }
        }""")
        assert hidden == 'none', hidden
    finally:
        pg.evaluate("document.getElementById('export-modal').style.display = 'none'")


# ── it reads exactly what the rest of the binder reads ───────────────────

COMPARE_JS = """() => {
    const app = window.app;
    const page = app.binderFiberPage();
    const procs = (app._processorsResolved || []).map(proc => {
        const title = app._bProcessorTitle(proc);
        return {title, rows: app._bFiberConnectionRows(proc, title)
            .filter(r => r.link && (r.link.cable || r.link.copper))
            .map(r => ({cells: r.cells,
                        p: ((r.parts || {})[2] || []).map(x => x.text),
                        b: ((r.parts || {})[4] || []).map(x => x.text)}))};
    }).filter(p => p.rows.length);
    // the processor pages' strand maps: strand -> "box · link", and spares
    const maps = {};
    for (const proc of app._processorsResolved || []) {
        for (const m of app._bStrandMaps(proc)) {
            maps[m.title] = m.rows.map(r => r.cells[1]);
        }
    }
    const list = app.buildPullSheet();
    return {page, procs, maps,
            totals: (list.totals || []).map(r => ({type: r.type, length: r.length, qty: r.qty, label: r.label || ''})),
            cables: app.getFiberCables().map(c => ({id: c.id, title: app._bStrandMapTitle(c),
                                                    type: app.fiberCableTypeText(c), strands: c.strands}))};
}"""


def test_every_link_is_a_row_of_the_processor_pages_table(page):
    pg, _ids = page
    got = pg.evaluate(COMPARE_JS)
    page_procs = got['page']['procs']
    assert [p['title'] for p in page_procs] == [p['title'] for p in got['procs']]
    for mine, theirs in zip(page_procs, got['procs']):
        assert len(mine['links']) == len(theirs['rows']), (mine['title'], mine['links'], theirs['rows'])
        for link, row in zip(mine['links'], theirs['rows']):
            assert link['output'] == row['cells'][0], (link, row)
            assert link['breakout'] == row['cells'][3], (link, row)
            if row['cells'][2] in ('Cat6A', 'Cat6', 'Cat5e'):
                # copper plugs in its kind at either end, as the table has it
                kind = row['cells'][2]
                assert link['atProcessor'] == [kind] and link['atBreakout'] == [kind], link
                continue
            assert link['atProcessor'] == row['p'], (link, row)
            # the breakout end is the table's, without the extension's
            # lines (the drawing gives the extension its own column)
            ext = [t for t in row['b'] if t.startswith('ext ') or ' to ' in t]
            assert link['atBreakout'] == [t for t in row['b'] if t not in ext], (link, row)
            if ext:
                assert ext[0].replace('ext ', '', 1) == link['extension'], (link, row)
    # the WALL SR rows: the backup listed with its main, output by output,
    # the TAC pair flipped, the DUO crossing inside, XD A's fan-out
    sr = page_procs[0]
    assert sr['title'] == 'WALL SR' and sr['backup'] == 'WALL SR BU', sr
    first = sr['links'][0]
    assert first['output'] == 'WALL SR · trunk A' and first['breakout'] == 'X1 on XD A', first
    assert first['atProcessor'] == ['1 Blue', '2 Orange'] and first['atBreakout'] == ['2 Orange', '1 Blue'], first
    assert first['extension'] == "Fan-out 10'" and first['cable'] == "TAC A · TAC 12 · 500'", first
    assert sr['links'][1]['output'] == 'WALL SR BU · trunk A', sr['links'][1]
    duo = [x for x in sr['links'] if x['breakout'] == 'X1 on XD C'][0]
    assert duo['atBreakout'][-1] == 'crosses inside' and duo['cable'].endswith('no length'), duo
    # nothing picked is not a link: XD C's X2 is not drawn
    assert not [x for x in sr['links'] if x['breakout'] == 'X2 on XD C'], sr['links']


def test_the_strand_maps_match_the_processor_pages(page):
    """Each cable's strands sit on the same box and link as the processor
    pages' strand maps put them, and the spares are the same strands."""
    pg, _ids = page
    got = pg.evaluate(COMPARE_JS)
    by_id = {c['id']: c for c in got['cables']}
    links = [x for p in got['page']['procs'] for x in p['links']]
    assert got['page']['cables'], 'no strand map'
    for spec in got['page']['cables']:
        cable = by_id[spec['id']]
        assert spec['title'] == cable['title'], spec
        theirs = got['maps'][cable['title']]
        assert len(theirs) == cable['strands'], (cable, theirs)
        # strand -> "box · link" on the processor pages ("XD A · X1", with
        # an extension's note after it)
        want = {n + 1: t.split(' · ext ')[0] for n, t in enumerate(theirs) if t != 'spare'}
        mine = {}
        for x in links:
            if x['cableId'] != spec['id']:
                continue
            for n in x['strands']:
                mine[n] = f"{x['box']} · {x['input']}"
        assert mine == want, (spec['title'], mine, want)
        spares = sum(1 for t in theirs if t == 'spare')
        if spares:
            assert spec['spare'].endswith(f'· spare ({spares})'), spec
        else:
            assert spec['spare'] == '', spec
        # every link on the cable is a row of its map, under its processor
        rows = [r['cells'] for r in spec['rows'] if 'cells' in r]
        assert len(rows) == len([x for x in links if x['cableId'] == spec['id']]), (spec, links)


def test_the_pull_list_is_the_pull_sheets_fiber_rows(page):
    pg, _ids = page
    got = pg.evaluate(COMPARE_JS)
    pull = got['page']['pull']
    assert pull, 'no fiber rows'
    # each row is a row of the show pull list, as it stands
    for r in pull:
        assert r in got['totals'], (r, got['totals'])
    # every fiber cable a link takes is pulled, the extension too
    types = {r['type'] for r in pull}
    for c in got['cables']:
        if any(x['cableId'] == c['id'] for p in got['page']['procs'] for x in p['links']):
            assert c['type'] in types, (c, types)
    assert any(t.startswith('Fan-out') for t in types), types
    # and nothing that is not fiber
    assert not [r for r in pull if r['type'].startswith('Cat')], pull


# ── on the sheet ─────────────────────────────────────────────────────────

def test_the_sheet_draws_every_link_whole_and_strikes_nothing(page):
    pg, _ids = page
    for palette in ('colour', 'printer'):
        pages = pg.evaluate(PAINT_JS, _opts(palette=palette))
        assert len(pages) == 1, [p['title'] for p in pages]
        sheet = pages[0]
        texts = sheet['texts']
        for head in ('PROCESSOR', 'OUTPUT', 'AT THE PROCESSOR', 'CABLE', 'EXTENSION',
                     'AT THE BREAKOUT', 'BREAKOUT BOX', 'FIBER CABLES · PULL LIST'):
            assert head in texts, (head, texts[:40])
        assert 'FIBER · PROCESSOR TO BREAKOUT BOX' in texts, texts
        assert "TAC A · TAC 12 · 500'" in texts and "Fan-out 10'" in texts, texts
        assert any(t.startswith('STRAND MAP · TAC A') for t in texts), texts
        # nothing cut, no em dash
        assert not [t for t in texts if t.endswith(chr(0x2026))], [t for t in texts if t.endswith(chr(0x2026))]
        assert not [t for t in texts if chr(0x2014) in t], texts
        report = pg.evaluate(RULE_JS, [_opts(palette=palette, cover=False)])
        bad = _struck([p for p in report if p['kind'] == 'fiber'])
        assert not bad, '\n' + '\n'.join(bad)


def test_the_strands_stand_centered_in_their_plugs(page):
    # Matt 2026-11-03: "the colors arent center justified in the fiber
    # drawing". Each plug's strand block (swatch and name) sits on the plug's
    # middle, not against its left edge.
    pg, _ids = page
    sheet = pg.evaluate(PAINT_JS, _opts())[0]
    plugs = sheet['fiber']['plugs']
    assert plugs, sheet['fiber']
    for p in plugs:
        mid, block = (p['a'] + p['b']) / 2, (p['left'] + p['right']) / 2
        assert abs(mid - block) < 0.5, p
        assert p['left'] >= p['a'] and p['right'] <= p['b'], p


def test_the_title_block_on_or_off(page):
    """On, the sheet wears the title block and names itself FIBER in it;
    off, there is no block, the drawing gets the whole width and is drawn
    at least as large, and the view bubble names the sheet."""
    pg, _ids = page
    on = pg.evaluate(PAINT_JS, _opts(titleBlock=True))[0]
    off = pg.evaluate(PAINT_JS, _opts(titleBlock=False))[0]
    assert on['titleBlock'] and 'FIBER' in on['texts'] and 'Sheet Number' in on['texts'], on['texts'][-30:]
    assert not off['titleBlock'] and 'Sheet Number' not in off['texts'], off['texts'][-30:]
    assert off['bubble'] and off['bubble']['name'] == 'FIBER · PROCESSOR TO BREAKOUT BOX', off['bubble']
    assert off['fiber']['scale'] >= on['fiber']['scale'], (on['fiber'], off['fiber'])


# ── never wider than the sheet ──────────────────────────────────────────

SHEETS = ('letter', 'a4', 'tabloid', 'a3', 'archc', 'archd')
SHEET_IN = {'letter': (11, 8.5), 'a4': (11.69, 8.27), 'tabloid': (17, 11),
            'a3': (16.54, 11.69), 'archc': (24, 18), 'archd': (36, 24)}
# app-binder.js: 200 px/in, the border's PAD, the title block, the drawing
# area's pad, the table gap; app-binder-fiber.js: the drawing columns' gap
PX_IN, PAD, TB_W, DA_PAD, COL_GAP, DRAW_GAP = 200, 50, 480, 30, 30, 70


def _da(sheet, tb):
    w, h = SHEET_IN[sheet]
    W, H = w * PX_IN, h * PX_IN
    tbx = W - PAD - (TB_W if tb else 0)
    return tbx - PAD - DA_PAD * 2, H - PAD * 2 - DA_PAD * 2


def _overflow(plan, sheet, tb):
    """Every Fiber sheet's drawing and tables, at its scale, against the
    drawing area: what runs past its right or its foot."""
    da_w, da_h = _da(sheet, tb)
    bad = []
    for p in plan:
        f, s = p['fiber'], p['scale']
        draw = f['drawCols'] * f['drawW'] + max(0, f['drawCols'] - 1) * DRAW_GAP if f['drawCols'] else 0
        tables = f['tableCols'] * f['tableW'] + max(0, f['tableCols'] - 1) * COL_GAP if f['tableCols'] else 0
        across = max(draw, tables) if f['under'] or not draw else draw + (COL_GAP * 2 + tables if tables else 0)
        if across * s > da_w + 1:
            bad.append((p['title'], 'wide', round(across * s), round(da_w)))
        ext = p.get('extent')
        if ext and (ext['w'] * s > da_w + 1 or ext['h'] * s > da_h + 1):
            bad.append((p['title'], 'extent', ext, s))
    return bad


@pytest.mark.parametrize('sheet', SHEETS)
def test_the_page_never_runs_past_the_drawing_area(page, sheet):
    """Owner, 2026-11-13: at letter the Fiber drawing was laid out at the
    base size, wider than the room beside the title block, and its
    breakout boxes ran under the logo and the revisions. On every sheet,
    with the block on or off, the drawing and its tables stand inside the
    drawing area - scaled down to its width where it is wider."""
    pg, _ids = page
    for tb in (True, False):
        plan = [p for p in pg.evaluate(PLAN_JS, _opts(sheet=sheet, titleBlock=tb)) if p['kind'] == 'fiber']
        assert plan, (sheet, tb)
        assert not _overflow(plan, sheet, tb), (sheet, tb, _overflow(plan, sheet, tb), plan)


def test_at_letter_the_drawing_fills_the_width_and_the_tables_start_under_it(page):
    """The seeded show at letter: the drawing as wide as the drawing area
    lets it (not left at the base size and cut by the block), and the
    tables start in the room under it on the same sheet rather than
    leaving that blank."""
    pg, _ids = page
    plan = [p for p in pg.evaluate(PLAN_JS, _opts(sheet='letter')) if p['kind'] == 'fiber']
    f, s = plan[0]['fiber'], plan[0]['scale']
    da_w, _ = _da('letter', True)
    assert f['drawW'] > da_w, f  # wider than the sheet at the base size
    assert s < 1 and f['drawW'] * s <= da_w + 1, (s, f)
    assert f['tableCols'] >= 1 and f['under'], f
    sheets = pg.evaluate(PAINT_JS, _opts(sheet='letter'))
    texts = [t for sh in sheets for t in sh['texts']]
    assert 'BREAKOUT BOX' in sheets[0]['texts'], sheets[0]['texts'][:40]
    assert any(t.startswith('STRAND MAP') for t in sheets[0]['texts']), sheets[0]['texts']
    assert 'FIBER CABLES · PULL LIST' in texts
    assert not [t for t in texts if t.endswith(chr(0x2026))]
    report = pg.evaluate(RULE_JS, [_opts(sheet='letter', cover=False)])
    bad = _struck([p for p in report if p['kind'] == 'fiber'])
    assert not bad, '\n' + '\n'.join(bad)


# ── that much fiber: two columns ─────────────────────────────────────────

@pytest.fixture(scope="module")
def many(page):
    """Eight SX40s, four XDs each, every XD on its processor's TAC (the
    seeded show is replaced; the module's guard puts the project back)."""
    pg, ids = page
    assert pg.evaluate(MANY_JS, 8) == 8
    return pg


def test_that_much_fiber_draws_two_columns_on_one_sheet(many):
    pg = many
    for tb in (True, False):
        plan = [p for p in pg.evaluate(PLAN_JS, _opts(titleBlock=tb)) if p['kind'] == 'fiber']
        assert len(plan) == 1, (tb, plan)
        f = plan[0]['fiber']
        assert f['drawCols'] == 2, (tb, f)
        left, right = f['procs']
        assert left and right and left + right == [f'RACK {i}' for i in range(1, 9)], f
        # a little under the base size at most, to stay on one sheet
        assert plan[0]['scale'] >= 0.8, plan[0]
    painted = pg.evaluate(PAINT_JS, _opts(titleBlock=False))[0]
    xs = painted['fiber']['drawX']
    assert len(xs) == 2 and xs[1] > xs[0], painted['fiber']
    assert painted['texts'].count('PROCESSOR') == 2, painted['texts'][:30]
    assert not [t for t in painted['texts'] if t.endswith('…')]


def test_past_two_columns_it_continues_onto_the_next_sheet(many):
    pg = many
    assert pg.evaluate(MANY_JS, 16) == 16
    plan = [p for p in pg.evaluate(PLAN_JS, _opts()) if p['kind'] == 'fiber']
    assert len(plan) >= 2, plan
    assert plan[0]['title'] == 'Fiber' and all(p['title'] == 'Fiber (cont.)' for p in plan[1:]), plan
    drawn = [t for p in plan for col in p['fiber']['procs'] for t in col]
    assert drawn == [f'RACK {i}' for i in range(1, 17)], drawn
    assert plan[0]['fiber']['drawCols'] == 2, plan[0]
    assert all(p['scale'] >= 0.8 for p in plan), plan


@pytest.mark.parametrize('sheet', SHEETS)
def test_that_much_fiber_never_runs_past_the_drawing_area(many, sheet):
    pg = many
    for n in (8, 16):
        assert pg.evaluate(MANY_JS, n) == n
        for tb in (True, False):
            plan = [p for p in pg.evaluate(PLAN_JS, _opts(sheet=sheet, titleBlock=tb)) if p['kind'] == 'fiber']
            drawn = [t for p in plan for col in p['fiber']['procs'] for t in col]
            assert [t.replace(' (cont.)', '') for t in drawn if not t.endswith('(cont.)')] == \
                [f'RACK {i}' for i in range(1, n + 1)], (sheet, tb, drawn)
            assert not _overflow(plan, sheet, tb), (sheet, tb, _overflow(plan, sheet, tb))
