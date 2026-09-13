"""The binder's TABLES, read off two real shows: no cell cut off, no name
printed twice, no cell stacked on itself, no half-empty sheet.

Measured on the user's own export, "2026 Kelly Clarkson - binder rev 1.1.pdf"
(2026-09-09, "the data and power pages are hard to read or cut off"):

  * 69 cells ended in an ellipsis across ten sheets - a circuit name cut in
    half on a pull sheet is worse than useless;
  * the unit a port lands on was named TWICE ("IMAG SR IMAG SR", the
    processor's name and its card's - a NovaPro UHD Jr's card IS the
    processor), and where nobody typed a name the MODEL stood in for it and
    was then printed again as the model ("NovaPro UHD Jr USC A · NovaPro UHD
    Jr · 16 ports"). That doubling is what pushed most of those 69 cells past
    their column;
  * the data sheet's HOME RUN cell, holding both ends, was drawn as two
    stacked lines with the " / " between them gone, so the two ends read as
    one thing said twice;
  * SR · DATA put a 1243 x 1240 map in the top left of a 3400 x 2200 sheet
    and left the bottom half empty - the fill that covers the other sheets
    was not covering this one.

These are the rules, not the numbers: every page of both shows is rendered
and every text op is read, so a new long string cannot quietly bring the
ellipsis back.

The fixtures are two frozen saves in the scratch dir, read by env var and
SKIPPED when absent (they are the user's shows - they are never copied into
the repo):
    LRD_KELLY_LIVE_JSON   kelly-live-fixture.json
    LRD_PULL_SMOKE_JSON   experts-only-fixture.json

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_binder_tables.py -v --browser chromium
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from test_binder import DA, SCRATCH_FIXTURE, W, H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The two shows. Kelly Clarkson is the export the user marked up: five
# processors, two of them unnamed, six-port IMAG walls on snakes, a 22 x 7
# upstage wall. Experts Only is the show test_binder.py already smokes.
KELLY_FIXTURE = os.environ.get('LRD_KELLY_LIVE_JSON') or os.path.join(
    os.path.dirname(SCRATCH_FIXTURE), 'kelly-live-fixture.json')
# The user's own save, "2026 Experts Only.json", where it is given.
EXPERTS_FIXTURE = os.environ.get('LRD_EXPERTS_JSON') or SCRATCH_FIXTURE
FIXTURES = {'kelly': KELLY_FIXTURE, 'experts only': EXPERTS_FIXTURE}

# The whole set, both sides, every extra sheet on.
OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True, 'wiring': True}

# Every sheet of a show as the recorder wrote it: the plan's fill numbers and
# every text op with its own x, y and size - the ops /api/export/pdf-from-pages
# replays, so what is asserted here is what the PDF prints.
SHEETS_JS = """async ([project, opts]) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('PUT', '/api/project', project);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_tables');
    app.selectLayer(app.project.layers.find(l => (l.type || 'screen') === 'screen'));
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    // The snakes a screen's ports actually ride, both ends, read off the
    // show's own helpers (app-processors.js) rather than off the sheet -
    // so what the sheet says can be held against them.
    const snakesOn = (page) => {
        const layer = (app.project.layers || [])
            .find(l => String(l.id) === String(page.layerId));
        if (!layer) return [];
        const scr = ((app._assignment && app._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        const out = new Map();
        for (const p of ((scr && scr.ports) || [])) {
            for (const c of [app.dataPortCableForScreen(layer, p.number),
                             app.dataPortBackupCableForScreen(layer, p.number)]) {
                if (!c || c.kind !== 'snake' || !c.snake) continue;
                const ft = Number(c.snake.ft);
                if (!(ft > 0) || !c.snake.name) continue;
                out.set(c.snake.id, { id: c.snake.id, name: c.snake.name,
                                      ft, ftText: app.cableText(ft, '') });
            }
        }
        return [...out.values()];
    };
    const plan = app.planBinder(opts);
    const pages = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        pages.push({
            number: plan[i].number, title: plan[i].title, kind: plan[i].kind,
            layout: plan[i].layout, scale: plan[i].scale, extent: plan[i].extent,
            snakes: plan[i].kind === 'data' ? snakesOn(plan[i]) : [],
            texts: r.record.ops.filter(o => o.op === 'text' && String(o.text).trim())
                    .map(o => ({ t: o.text, x: Math.round(o.x * 100) / 100,
                                 y: Math.round(o.y * 100) / 100, size: o.size })),
        });
    }
    const models = new Set();
    for (const p of (app._processorsResolved || [])) {
        if (p.deviceName) models.add(p.deviceName);
        for (const s of (p.slots || [])) {
            if (s.card && s.card.deviceName) models.add(s.card.deviceName);
        }
    }
    return { pages, models: [...models] };
}"""


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def shows(e2e_server, pw_browser):
    """Both shows' sheets, rendered once for the whole module."""
    present = {k: v for k, v in FIXTURES.items() if os.path.exists(v)}
    if not present:
        pytest.skip('neither show fixture is present: %s' % list(FIXTURES.values()))
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    out = {}
    for name, path in present.items():
        with open(path) as fh:
            project = json.load(fh)
        out[name] = pg.evaluate(SHEETS_JS, [project, OPTS])
        assert out[name]['pages'], (name, 'the show planned no sheet at all')
    assert not errors, errors[:3]
    yield out
    context.close()


def _every_text(shows):
    """(show, sheet number, sheet title, text op) over every sheet of every
    show - the sweep these rules are made of."""
    for name, show in shows.items():
        for page in show['pages']:
            for op in page['texts']:
                yield name, page, op


def _column(page, heading):
    """The cells under a left-aligned column heading: the heading is drawn at
    the very x its cells are, so the x picks the column out. Returns
    (heading op, [cell ops below it])."""
    head = next((o for o in page['texts'] if o['t'] == heading), None)
    if not head:
        return None, []
    return head, [o for o in page['texts']
                  if abs(o['x'] - head['x']) < 0.5 and o['y'] > head['y'] + 1]


# ── 1. no cell is cut off ────────────────────────────────────────────────

# _bFit cuts by APPENDING the ellipsis, so a cut string always ends in one.
# The pull list's own summary of a long label set - "S1-3-1 … S1-2-6 (11)",
# first, last and how many (app-pull-list.js) - is the one string that
# carries an ellipsis on purpose, and it is whole.
SUMMARY = re.compile(r'^\S.* … \S.* \(\d+\)$')


def _cut(text):
    return text.endswith('…') or ('…' in text and not SUMMARY.match(text))


def test_no_cell_on_any_sheet_is_cut_off(shows):
    """THE GENERAL RULE. Every sheet of both shows, every text op: nothing
    ends in the ellipsis _bFit cuts with. A string that grows past its column
    has to be made honest or given the room - it may not be halved.

    Before: Kelly 69 (Overview 1, SR · DATA 6, SL · DATA 6, UPSTAGE · DATA 14,
    PULL 23, the two processor sheets 6 + 13), Experts Only 57.
    """
    bad = {}
    for name, page, op in _every_text(shows):
        if _cut(op['t']):
            bad.setdefault(f"{name} {page['number']} {page['title']}", []).append(op['t'])
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)


# ── 2. a name is said once ───────────────────────────────────────────────

# "IMAG SR IMAG SR", "SR SR", "USC A USC A" - a run of words immediately
# repeating itself inside one cell.
DOUBLED = re.compile(r'(?<![^\s·])(\S+(?: \S+){0,3}) \1(?![^\s·])')


def test_no_cell_says_a_name_twice(shows):
    """The processor's name and its card's are ONE unit's name where the card
    is the processor's own face: "IMAG SR", never "IMAG SR IMAG SR"."""
    bad = {}
    for name, page, op in _every_text(shows):
        m = DOUBLED.search(op['t'])
        if m:
            bad.setdefault(f"{name} {page['number']} {page['title']}", []).append(op['t'])
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)


def test_no_cell_prints_a_model_twice(shows):
    """A blank name must not become the MODEL only for the model to be printed
    beside it: "NovaPro UHD Jr USC A · NovaPro UHD Jr · 16 ports" says one
    device's model twice and its name not at all."""
    bad = {}
    for nm, show in shows.items():
        models = [m for m in show['models'] if m and len(m) > 2]
        for page in show['pages']:
            for op in page['texts']:
                for model in models:
                    if op['t'].count(model) > 1:
                        bad.setdefault(f"{nm} {page['number']} {page['title']}",
                                       []).append(op['t'])
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)


# ── 3. the home run cell says its run once, on its own line ──────────────

def test_a_home_run_cell_never_says_one_run_twice(shows):
    """HOME RUN holds both ends of a redundant port ("SR A 250' +10' / SR B
    200'"). It may not say the same run twice - a port whose two ends ride ONE
    snake states that snake once - and where the cell will not fit on one line
    the " / " must stay with it: two ends stacked with the separator dropped
    is what made two different snakes read as one thing repeated.

    Every op in the column either sits on its row's own baseline (the one the
    PORT label sits on) or is the second line of a cell whose first line ends
    in the separator that says so.
    """
    stacked, repeats = {}, {}
    for nm, show in shows.items():
        for page in show['pages']:
            if page['kind'] != 'data':
                continue
            port, labels = _column(page, 'PORT')
            run, cells = _column(page, 'HOME RUN')
            assert port and run, (nm, page['title'], 'the Ports table has both columns')
            rows = sorted({o['y'] for o in labels})
            for o in cells:
                if o['y'] in rows:
                    continue
                # a continuation: the line above it, in this column, carries
                # the separator
                above = [c for c in cells if c['y'] < o['y']]
                first = max(above, key=lambda c: c['y'], default=None)
                if not first or not first['t'].rstrip().endswith('/'):
                    stacked.setdefault(f"{nm} {page['number']} {page['title']}",
                                       []).append([first and first['t'], o['t']])
            for o in cells:
                ends = [e.strip().rstrip('/').strip() for e in o['t'].split(' / ')]
                if len(ends) == 2 and ends[0] == ends[1]:
                    repeats.setdefault(f"{nm} {page['number']} {page['title']}",
                                       []).append(o['t'])
    assert not stacked, 'a home run cell was stacked with its separator lost: ' + json.dumps(
        stacked, indent=1, ensure_ascii=False)
    assert not repeats, 'a home run cell said one run twice: ' + json.dumps(
        repeats, indent=1, ensure_ascii=False)


def test_a_snake_states_its_home_run_once_on_a_data_sheet(shows):
    """A SNAKE IS ONE HOME RUN, SO THE SHEET SAYS IT ONCE.

    "Why is the same data written multiple times under the snake under a
    specific port number" (2026-09-09). The UPSTAGE data sheet printed
    "USC A 100' +10' / SNAKE A 100' +10'" on four rows in a row: A-1..A-4
    all ride the one 4-way, and its return end all rides the one backup
    4-way, so the pair of runs was printed four times over. The ports on a
    snake belong under a GROUP HEADING that names it once - the way the
    circuits table already heads a multi's circuits - and each port row
    then carries only what is its own (its extension).

    The rule: for every snake either end of a screen's ports rides, its
    reading - the name and the run together - appears on that sheet
    EXACTLY ONCE. More than once is the repetition; none at all would mean
    the run had been dropped rather than stated.
    """
    bad = {}
    for nm, show in shows.items():
        for page in show['pages']:
            for snake in page.get('snakes', []):
                hits = [o['t'] for o in page['texts']
                        if snake['name'] in o['t'] and snake['ftText'] in o['t']]
                if len(hits) != 1:
                    bad.setdefault(f"{nm} {page['number']} {page['title']}", {})[
                        f"{snake['name']} {snake['ftText']}"] = hits
    assert not bad, ("a snake's home run must be stated once, as a heading: "
                     + json.dumps(bad, indent=1, ensure_ascii=False))


# ── 4. a map sheet fills its sheet ───────────────────────────────────────

def test_every_map_sheet_fills_its_drawing_area(shows):
    """A screen's POWER and DATA sheets cover the drawing area: the map takes
    the room that is actually free rather than sitting small in a corner over
    an empty half-sheet. The extent is the fill's own measure, in page units,
    and it never overshoots the area either.
    """
    thin = {}
    for nm, show in shows.items():
        for page in show['pages']:
            if page['kind'] not in ('power', 'data'):
                continue
            ext = page['extent']
            assert ext, (nm, page['title'])
            assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, (nm, page['title'], ext)
            # measured: every Experts Only sheet 1.0; Kelly's SR/SL · DATA
            # 0.954 - a 9 x 6 wall of tall panels beside a 1020-wide Ports
            # table, the tightest the fill can be pulled - against 0.676
            # before (the map in the top left, the bottom half empty).
            if ext['h'] < DA['h'] * 0.93 or ext['w'] < DA['w'] * 0.93:
                thin[f"{nm} {page['number']} {page['title']}"] = [
                    round(ext['w'] / DA['w'], 3), round(ext['h'] / DA['h'], 3),
                    page['layout'], page['scale']]
    assert not thin, 'half-empty sheets (w, h as a share of the area): ' + json.dumps(
        thin, indent=1)


def test_the_sheets_are_the_sheet_size(shows):
    """Every sheet is the Tabloid page these numbers are measured on."""
    for nm, show in shows.items():
        for page in show['pages']:
            for op in page['texts']:
                assert -1 <= op['x'] <= W + 1 and -1 <= op['y'] <= H + 1, (
                    nm, page['title'], op)



# ── 5. a backup unit is its own section ──────────────────────────────────
#
# "this doesn't really differentiate between CVT A and B. They should be
# different sections as if it was a second cvt, since it is" (2026-09-12,
# Experts Only rev 1.1, SR - MAIN - DATA). Every unit that carries a port -
# a backup box or card exactly as a primary one - is its own band, with its
# own snake heading and its own rows. The pairing is said from both sides
# ("backup SR B-1" / "backs up SR A-1"); PANELS and PX are counted once, on
# the primary's row, so a total down PX is never doubled; HOME RUN on a row
# is that end's own extension; the backup's section follows its primary's.

def _ports_table(page):
    """The Ports table of a data sheet, read off its text ops: a list of
    sections {band, groups: [{head, rows}]}, a row being a dict keyed by the
    column headings. The band is drawn at the PORT column's x, a snake
    heading indented past it, and a row puts a cell under every heading."""
    texts = page['texts']
    port = next(o for o in texts if o['t'] == 'PORT')
    heads = [o for o in texts if abs(o['y'] - port['y']) < 0.5
             and o['t'] in ('PORT', 'PRIMARY', 'BACKUP', 'PANELS', 'PX', 'HOME RUN')]
    assert [h['t'] for h in heads] == ['PORT', 'PRIMARY', 'BACKUP', 'PANELS', 'PX', 'HOME RUN'], heads
    xs = {round(h['x'], 1): h['t'] for h in heads}
    # the next table's column starts where its own headings do, on the
    # same line as these
    last = max(h['x'] for h in heads)
    right = min([o['x'] for o in texts if o['x'] > last + 1 and (
                     abs(o['y'] - port['y']) < 0.5 or o['t'] in ('CABLES THIS SCREEN', 'FACTS'))]
                + [float('inf')])
    # the table's own ops: below the headings, left of the next column's
    ops = [o for o in texts if o['y'] > port['y'] + 1 and port['x'] - 1 <= o['x'] < right]
    stop = next((o['y'] for o in sorted(texts, key=lambda o: o['y'])
                 if o['y'] > port['y'] and o['x'] < right
                 and o['t'] in ('CABLES THIS SCREEN', 'FACTS')), None)
    if stop is not None:
        ops = [o for o in ops if o['y'] < stop]
    lines = {}
    for o in ops:
        lines.setdefault(round(o['y'], 1), []).append(o)
    sections = []
    for y in sorted(lines):
        line = sorted(lines[y], key=lambda o: o['x'])
        cells = {xs.get(round(o['x'], 1)): o['t'] for o in line}
        if len(line) == 1 and None not in cells and len(cells) == 1 and 'PORT' in cells:
            sections.append({'band': line[0]['t'], 'groups': [{'head': None, 'rows': []}]})
        elif len(line) == 1 and None in cells:
            assert sections, (y, line)
            sections[-1]['groups'].append({'head': line[0]['t'], 'rows': []})
        else:
            assert None not in cells and len(cells) == 6, ('a row puts a cell under every heading', line)
            sections[-1]['groups'][-1]['rows'].append(cells)
    for sec in sections:
        sec['groups'] = [g for g in sec['groups'] if g['head'] or g['rows']]
    return sections


def _px(cell):
    return int(cell.replace(',', ''))


def _assert_two_sections(sections, a, b, a_head, b_head, a_runs, b_runs, panels, px):
    """SR A's band, then SR B's, each with its own snake heading and its own
    rows, the pairing said from both sides, the pixels counted once."""
    bands = [s['band'] for s in sections]
    ia = next(i for i, t in enumerate(bands) if t.startswith(f'CVT4K-S {a} · '))
    ib = next(i for i, t in enumerate(bands) if t.startswith(f'CVT4K-S {b} · '))
    assert ib == ia + 1, ('the backup section follows its primary', bands)
    sa, sb = sections[ia], sections[ib]
    assert [g['head'] for g in sa['groups']] == [a_head], sa
    assert [g['head'] for g in sb['groups']] == [b_head], sb
    ra, rb = sa['groups'][0]['rows'], sb['groups'][0]['rows']
    n = len(a_runs)
    assert [r['PORT'] for r in ra] == [f'{a}-{i}' for i in range(1, n + 1)], ra
    assert [r['PRIMARY'] for r in ra] == [f'CVT4K-S {a} · {i}' for i in range(1, n + 1)], ra
    assert [r['BACKUP'] for r in ra] == [f'backup {b}-{i}' for i in range(1, n + 1)], ra
    assert [r['PANELS'] for r in ra] == panels, ra
    assert [r['PX'] for r in ra] == px, ra
    assert [r['HOME RUN'] for r in ra] == a_runs, ra
    assert [r['PORT'] for r in rb] == [f'{b}-{i}' for i in range(1, n + 1)], rb
    assert [r['PRIMARY'] for r in rb] == [f'CVT4K-S {b} · {i}' for i in range(1, n + 1)], rb
    assert [r['BACKUP'] for r in rb] == [f'backs up {a}-{i}' for i in range(1, n + 1)], rb
    assert [r['PANELS'] for r in rb] == ['—'] * n, rb
    assert [r['PX'] for r in rb] == ['—'] * n, rb
    assert [r['HOME RUN'] for r in rb] == b_runs, rb


def _all_rows(sections):
    return [r for s in sections for g in s['groups'] for r in g['rows']]


def test_a_backup_box_is_its_own_section_on_experts_only(shows):
    """The user's own show: one H9, per-card 1:1, Card 1's box SR A backed
    by Card 3's box SR B. SR - MAIN's Ports table is the shape he chose -
    SR A's band, its own snake, rows that say "backup SR B-n"; then SR B's
    band, its own snake, rows that say "backs up SR A-n" with "—" for
    PANELS and PX; each end's own extension on its own row. The same for
    SL A / SL B on SL - MAIN. The PX column sums to the wall once."""
    if 'experts only' not in shows:
        pytest.skip('the Experts Only save is not present (LRD_EXPERTS_JSON)')
    pages = {p['title']: p for p in shows['experts only']['pages']}
    sr = _ports_table(pages['SR - MAIN - Data'])
    _assert_two_sections(
        sr, 'SR A', 'SR B', "SR A · 4 channel snake · 150'", "SR B · 4 channel snake · 100'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+75'"],
        ['84', '84', '84', '56'], ['604,800', '604,800', '604,800', '403,200'])
    assert sum(_px(r['PX']) for r in _all_rows(sr) if r['PX'] != '—') == 1680 * 1320
    sl = _ports_table(pages['SL - MAIN - Data'])
    _assert_two_sections(
        sl, 'SL A', 'SL B', "SL A · 4 channel snake · 100'", "SL B · 4 channel snake · 150'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+100'"],
        ['84', '84', '84', '56'], ['604,800', '604,800', '604,800', '403,200'])
    # the loose return: SR - Return's one port, a cable at each end
    ret = _ports_table(pages['SR - Return - Data'])
    assert [s['band'].split(' · ')[0] for s in ret] == ['CVT4K-S SR A', 'CVT4K-S SR B'], ret
    (a5,), (b5,) = [_all_rows([s]) for s in ret]
    assert (a5['PORT'], a5['BACKUP'], b5['PORT'], b5['BACKUP']) == (
        'SR A-5', 'backup SR B-5', 'SR B-5', 'backs up SR A-5'), ret
    assert b5['PANELS'] == '—' and b5['PX'] == '—' and a5['PX'] != '—', ret
    # no heading anywhere names the other end's snake
    for page in shows['experts only']['pages']:
        if page['kind'] != 'data':
            continue
        for sec in _ports_table(page):
            for g in sec['groups']:
                assert not g['head'] or (' / ' not in g['head'] and not g['head'].startswith('backup ')
                                         and 'both ends' not in g['head']), (page['title'], g['head'])


# The suite's own show, so the rule runs where the user's save is absent: a
# 28 x 11 wall of 60 x 120 panels (four ports: 84, 84, 84, 56 panels) on
# one H9, card 1's CVT4K-S "SR A" backed 1:1 by card 2's CVT4K-S "SR B",
# each box's sockets 1-4 on its own snake with extensions where the user's
# show has them; and a second wall on a card in HALVES mode, whose returns
# come back on the same card - one unit, one section.
SEED_BACKUP_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'MAIN', columns: 28, rows: 11, cabinet_width: 60, cabinet_height: 120,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 100, flowPattern: 'tl-h',
            processorType: 'novastar-armor'});
    await j('POST', '/api/layer/add', {name: 'SOLO', columns: 10, rows: 5, cabinet_width: 100, cabinet_height: 100,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 100, flowPattern: 'tl-h',
            processorType: 'novastar-armor', offset_x: 2000});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    const card = 'novastar-card-h-16xrj45-2xfiber';
    await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: card});
    await j('PUT', `/api/processors/${pid}/slots/1`, {deviceId: card});
    st = await j('PUT', `/api/processors/${pid}/slots/2`, {deviceId: 'novastar-card-h-20xrj45'});
    const [c1, c2, c3] = st.processors[0].slots.slice(0, 3).map(s => s.card.id);
    st = await j('POST', `/api/processors/${pid}/cards/${c1}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
    const boxA = st.processors[0].slots[0].card.cvts[0].id;
    st = await j('POST', `/api/processors/${pid}/cards/${c2}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
    const boxB = st.processors[0].slots[1].card.cvts[0].id;
    await j('PUT', `/api/processors/${pid}/cvts/${boxA}`, {name: 'SR A'});
    await j('PUT', `/api/processors/${pid}/cvts/${boxB}`, {name: 'SR B'});
    await j('PUT', `/api/processors/${pid}/cards/${c3}`, {name: 'SOLO'});
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${c1}`, {backupCardId: c2});
    await j('PUT', `/api/processors/${pid}/cards/${c3}`, {redundancyMode: 'halves'});
    let p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('binder_tables_seed');
    const main = app.project.layers.find(l => l.name === 'MAIN');
    const solo = app.project.layers.find(l => l.name === 'SOLO');
    app.selectLayer(main);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {layerId: String(main.id), cardId: c1});
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {layerId: String(solo.id), cardId: c3});
    await j('PUT', `/api/processors/${pid}/cvts/${boxA}`,
            {snakes: [{ports: [1, 2, 3, 4], ft: 150, name: 'SR A'}],
             portCables: {'1': {ft: 10}, '3': {ft: 25}, '4': {ft: 25}}});
    await j('PUT', `/api/processors/${pid}/cvts/${boxB}`,
            {snakes: [{ports: [1, 2, 3, 4], ft: 100, name: 'SR B'}],
             portCables: {'1': {ft: 10}, '3': {ft: 10}, '4': {ft: 75}}});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    return await j('GET', '/api/project');
}"""


@pytest.fixture(scope="module")
def seeded(e2e_server, pw_browser):
    """The suite's own backup show, every sheet rendered once."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    project = pg.evaluate(SEED_BACKUP_JS)
    out = pg.evaluate(SHEETS_JS, [project, OPTS])
    assert not errors, errors[:3]
    yield {p['title']: p for p in out['pages']}
    context.close()


def test_a_backup_box_is_its_own_section(seeded):
    """The rule on the suite's own show: two sections, SR B's after SR A's,
    each snake heading its own, the pairing from both sides, PANELS and PX
    "—" on the backup's rows and summing to the wall once, each end's own
    extension on its own row."""
    sections = _ports_table(seeded['MAIN - Data'])
    assert len(sections) == 2, sections
    _assert_two_sections(
        sections, 'SR A', 'SR B', "SR A · 4 channel snake · 150'", "SR B · 4 channel snake · 100'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+75'"],
        ['84', '84', '84', '56'], ['604,800', '604,800', '604,800', '403,200'])
    rows = _all_rows(sections)
    assert sum(_px(r['PX']) for r in rows if r['PX'] != '—') == 28 * 60 * 11 * 120
    assert sum(int(r['PANELS']) for r in rows if r['PANELS'] != '—') == 28 * 11


def test_a_same_unit_pairing_is_one_section(seeded):
    """A card in HALVES mode returns each port on its own other half: the
    primary and the return are ONE unit, so the sheet has one section - no
    second band is invented - and every row counts its own pixels."""
    sections = _ports_table(seeded['SOLO - Data'])
    assert len(sections) == 1, sections
    rows = _all_rows(sections)
    assert rows and all(r['PANELS'] != '—' and r['PX'] != '—' for r in rows), rows
    # every port has its return - on the same card, SOLO's other half
    assert all(r['BACKUP'] != '—' and 'SOLO' in r['BACKUP'] for r in rows), rows
    assert not [r for r in rows if r['BACKUP'].startswith('backs up')], rows
    assert sum(_px(r['PX']) for r in rows) == 10 * 100 * 5 * 100
