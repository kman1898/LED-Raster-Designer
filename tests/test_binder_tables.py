"""The binder's TABLES, read off two real shows: no cell cut off, no name
printed twice, no cell stacked on itself, no half-empty sheet.

Measured on the user's own export of live show A, its binder rev 1.1 PDF
(2026-09-09, "the data and power pages are hard to read or cut off"):

  * 69 cells ended in an ellipsis across ten sheets - a circuit name cut in
    half on a pull sheet is worse than useless;
  * the unit a port lands on was named TWICE ("IMAG SR IMAG SR", the
    processor's name and its card's - a NovaPro UHD Jr's card IS the
    processor), and where nobody typed a name the MODEL stood in for it and
    was then printed again as the model ("NovaPro UHD Jr WALL A · NovaPro UHD
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

The fixtures are two frozen saves in the git-ignored tests/fixtures-local
(conftest.private_fixture), SKIPPED when absent (they are the user's shows -
they are never committed, so CI skips them); each env var overrides its file:
    LRD_LIVE_SHOW_A_JSON  live-show-a-live.json
    LRD_LIVE_SHOW_B_JSON  live-show-b.json

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

from test_binder import DA, W, H  # noqa: E402
from conftest import private_fixture, private_fixture_missing  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The two shows. Live show A is the export the user marked up: five
# processors, two of them unnamed, six-port IMAG walls on snakes, a 22 x 7
# upstage wall. Live show B is the show test_binder.py already smokes.
SHOW_A_FIXTURE = private_fixture('live-show-a-live.json', 'LRD_LIVE_SHOW_A_JSON')
# The user's own save of live show B, where it is given.
SHOW_B_FIXTURE = private_fixture('live-show-b.json', 'LRD_LIVE_SHOW_B_JSON')
FIXTURES = {'show a': SHOW_A_FIXTURE, 'show b': SHOW_B_FIXTURE}

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
                                 y: Math.round(o.y * 100) / 100, size: o.size,
                                 weight: o.weight, align: o.align })),
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
        pytest.skip(' / '.join(private_fixture_missing(p) for p in FIXTURES.values()))
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
        with open(path, encoding='utf-8') as fh:
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

    Before: show A 69 (Overview 1, SR · DATA 6, SL · DATA 6, UPSTAGE · DATA 14,
    PULL 23, the two processor sheets 6 + 13), show B 57.
    """
    bad = {}
    for name, page, op in _every_text(shows):
        if _cut(op['t']):
            bad.setdefault(f"{name} {page['number']} {page['title']}", []).append(op['t'])
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)


# ── 2. a name is said once ───────────────────────────────────────────────

# "IMAG SR IMAG SR", "SR SR", "WALL A WALL A" - a run of words immediately
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
    beside it: "NovaPro UHD Jr WALL A · NovaPro UHD Jr · 16 ports" says one
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
    "WALL A 100' +10' / SNAKE A 100' +10'" on four rows in a row: A-1..A-4
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

    A map fills its area when it reaches the threshold in EITHER dimension:
    a wall is as large as the area allows at its own aspect ratio once its
    width (or its height) is the bound. A 9 x 2 DJ Booth wall spans the
    width and stands 0.531 of the height on Power, 0.616 on Data - the
    owner, shown both (2026-09-24): "Fine as is". A map short in BOTH
    dimensions is still the half-empty sheet this test is here for.
    """
    thin = {}
    for nm, show in shows.items():
        for page in show['pages']:
            if page['kind'] not in ('power', 'data'):
                continue
            ext = page['extent']
            assert ext, (nm, page['title'])
            assert ext['w'] <= DA['w'] + 1 and ext['h'] <= DA['h'] + 1, (nm, page['title'], ext)
            # measured: every show B sheet 1.0; show A's SR/SL · DATA
            # 0.954 - a 9 x 6 wall of tall panels beside a 1020-wide Ports
            # table, the tightest the fill can be pulled - against 0.676
            # before (the map in the top left, the bottom half empty).
            if ext['h'] < DA['h'] * 0.93 and ext['w'] < DA['w'] * 0.93:
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



# ── 5. a port and its backup end are one row, in two halves ─────────────
#
# 2026-09-12 gave a backup unit its own section ("They should be different
# sections as if it was a second cvt, since it is"); 2026-09-26 folded it
# back beside its primary: "we can fit XD A and B next to each other in the
# same table you already put what it's backing up", then "break the table
# up half and half the xd A and b being directly on top of each other is
# confusing". So a sheet with a backup end prints its Ports table as two
# halves under PRIMARY and BACKUP - each its own PORT, OUTPUT and HOME RUN,
# both runs even where they read the same ("that only shows one
# extension") - with each unit's band over its own half (the box, then its
# fiber) and each half's snake heading its own rows; PANELS once, at the
# end; no PX ("we dont need to be putting the amount of pixels each port
# has"). OUTPUT is left out where every row repeats its port's name
# (2026-10-18, section 5b), so a half is PORT and HOME RUN alone there.

PORT_KEYS = ('PORT', 'OUTPUT', 'HOME RUN')


def _ports_table(page):
    """The Ports table of a data sheet, read off its text ops: a list of
    sections {band: [lines], backup: [lines], groups: [{head: (primary,
    backup), rows}]}, a row being a dict keyed by the column headings, the
    backup half's prefixed "B ". Every column stands centred (2026-10-18),
    each heading and its cells on one x; a band's lines read from their
    half's left edge and a snake heading indented past it, both drawn
    left-aligned. A table without OUTPUT reads the same, its rows without
    the key."""
    texts = page['texts']
    port = next(o for o in texts if o['t'] == 'PORT')
    heads = sorted([o for o in texts if abs(o['y'] - port['y']) < 0.5
                    and o['t'] in PORT_KEYS + ('PANELS', 'PX')], key=lambda o: o['x'])
    names = [h['t'] for h in heads]
    per_half = [k for k in PORT_KEYS if k != 'OUTPUT' or 'OUTPUT' in names]
    split = names.count('PORT') >= 2
    want = per_half + (per_half if split else []) + ['PANELS']
    assert names[:len(want)] == want, names
    heads = heads[:len(want)]
    last = heads[-1]['x']
    keys = per_half + (['B ' + k for k in per_half] if split else []) + ['PANELS']
    xs = {round(h['x'], 1): k for h, k in zip(heads, keys)}
    # the table's left edge is its title's; each centred heading then
    # gives its column's width (twice its centre's distance from the
    # column's left), so the backup half's left edge is exact
    title = max((o for o in texts if o['t'] == 'PORTS' and o['y'] < port['y']), key=lambda o: o['y'])
    edge, lefts = title['x'], []
    for h in heads:
        lefts.append(edge)
        edge += 2 * (h['x'] - edge)
    bx = lefts[len(per_half)] if split else float('inf')
    s = port['size'] / 21                     # the sheet's fill
    # the next table's column starts where its own headings do, on the
    # same line as these
    right = min([o['x'] for o in texts if o['x'] > last + 1 and (
                     abs(o['y'] - port['y']) < 0.5 or o['t'] in ('CABLES THIS SCREEN', 'FACTS'))]
                + [float('inf')])
    # a band reads ABOVE its headings (2026-09-26), so the table starts
    # at its title, and a headings line - repeated under every band - is
    # skipped; nothing of this table stands right of PANELS' centre
    right = min(right, last + 1)
    ops = [o for o in texts if o['y'] > title['y'] + 1 and title['x'] - 1 <= o['x'] < right
           and o['t'] not in ('PRIMARY', 'BACKUP')]
    stop = next((o['y'] for o in sorted(texts, key=lambda o: o['y'])
                 if o['y'] > port['y'] and o['x'] < right
                 and o['t'] in ('CABLES THIS SCREEN', 'FACTS')), None)
    if stop is not None:
        ops = [o for o in ops if o['y'] < stop]
    lines = {}
    for o in ops:
        lines.setdefault(round(o['y'], 1), []).append(o)
    sections, prev = [], None
    for y in sorted(lines):
        line = sorted(lines[y], key=lambda o: o['x'])
        if [o['t'] for o in line] == names[:len(want)]:
            prev = 'heads'
            continue
        # a band starts at its half's edge and its pad, a snake heading set
        # in 22 past that; nothing else of the sheet stands there
        inset = lambda o: (o['x'] - (bx if o['x'] >= bx else title['x'])) / s
        left = [o for o in line if o['align'] == 'left' and min(abs(inset(o) - 12), abs(inset(o) - 34)) < 1.5]
        line = [o for o in line if o['align'] != 'left' or o in left]
        if not line:
            continue
        half = lambda b: next((o['t'] for o in left if (o['x'] >= bx) == b), None)
        if left:
            assert len(left) == len(line), ('a band line holds no cell', line)
            if max(inset(o) for o in left) > 12 + 11:
                assert sections, (y, line)
                sections[-1]['groups'].append({'head': (half(False), half(True)), 'rows': []})
                prev = 'head'
                continue
            # a band line: a new band, or its second (fiber) line
            if prev != 'band':
                sections.append({'band': [], 'backup': [], 'groups': [{'head': None, 'rows': []}]})
            if half(False) is not None:
                sections[-1]['band'].append(half(False))
            if half(True) is not None:
                sections[-1]['backup'].append(half(True))
            prev = 'band'
            continue
        cells = {xs.get(round(o['x'], 1)): o['t'] for o in line}
        assert None not in cells, ('every cell stands under its heading', line)
        assert set(cells) >= set(per_half) | {'PANELS'}, ('a row fills its primary half', line)
        sections[-1]['groups'][-1]['rows'].append(cells)
        prev = 'row'
    for sec in sections:
        sec['groups'] = [g for g in sec['groups'] if g['head'] or g['rows']]
    return sections


def _assert_backup_half(sections, a, b, a_head, b_head, a_runs, b_runs, panels):
    """SR A's band over the primary half and SR B's over the backup half of
    ONE section, each half's snake over its own rows, the ports side by
    side, each end's own run - and no OUTPUT: every socket ("SR A · 1")
    only repeats its port's name ("SR A-1")."""
    sec = next(s for s in sections if s['band'] and s['band'][0].startswith(f'CVT4K-S {a} · '))
    assert sec['backup'] and sec['backup'][0].startswith(f'CVT4K-S {b} · '), sec
    assert not [s for s in sections if s['band'] and s['band'][0].startswith(f'CVT4K-S {b} · ')], (
        'the backup box has no section of its own', sections)
    assert [g['head'] for g in sec['groups']] == [(a_head, b_head)], sec
    rows = sec['groups'][0]['rows']
    n = len(a_runs)
    assert [r['PORT'] for r in rows] == [f'{a}-{i}' for i in range(1, n + 1)], rows
    assert not [r for r in rows if 'OUTPUT' in r or 'B OUTPUT' in r], rows
    assert [r['HOME RUN'] for r in rows] == a_runs, rows
    assert [r['B PORT'] for r in rows] == [f'{b}-{i}' for i in range(1, n + 1)], rows
    assert [r['B HOME RUN'] for r in rows] == b_runs, rows
    assert [r['PANELS'] for r in rows] == panels, rows


def _all_rows(sections):
    return [r for s in sections for g in s['groups'] for r in g['rows']]


def test_a_backup_box_is_the_backup_half_on_live_show_b(shows):
    """The user's own show: one H9, per-card 1:1, Card 1's box SR A backed
    by Card 3's box SR B. SR - MAIN's Ports table is one section in two
    halves - SR A's band and snake over the primary half, SR B's over the
    backup half, each port's two ends side by side with each end's own
    extension. The same for SL A / SL B on SL - MAIN. No sheet prints PX."""
    if 'show b' not in shows:
        pytest.skip(private_fixture_missing(SHOW_B_FIXTURE))
    pages = {p['title']: p for p in shows['show b']['pages']}
    sr = _ports_table(pages['SR - MAIN - Data - Front View'])
    _assert_backup_half(
        sr, 'SR A', 'SR B', "SR A · 4 channel snake · 150'", "SR B · 4 channel snake · 100'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+75'"], ['84', '84', '84', '56'])
    sl = _ports_table(pages['SL - MAIN - Data - Front View'])
    _assert_backup_half(
        sl, 'SL A', 'SL B', "SL A · 4 channel snake · 100'", "SL B · 4 channel snake · 150'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+100'"], ['84', '84', '84', '56'])
    # the loose return: SR - Return's one port, a cable at each end
    ret = _ports_table(pages['SR - Return - Data - Front View'])
    assert [s['band'][0].split(' · ')[0] for s in ret] == ['CVT4K-S SR A'], ret
    assert ret[0]['backup'][0].split(' · ')[0] == 'CVT4K-S SR B', ret
    (a5,) = _all_rows(ret)
    assert (a5['PORT'], a5['B PORT']) == ('SR A-5', 'SR B-5') and 'B OUTPUT' not in a5, ret
    for page in shows['show b']['pages']:
        if page['kind'] == 'data':
            assert 'PX' not in [o['t'] for o in page['texts']], page['title']


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


def test_a_backup_box_is_the_backup_half(seeded):
    """The rule on the suite's own show: ONE section, SR A's band and snake
    over the primary half and SR B's over the backup half, each port's two
    ends on one row with each end's own extension, PANELS once and summing
    to the wall, and no PX column."""
    page = seeded['MAIN - Data - Front View']
    sections = _ports_table(page)
    assert len(sections) == 1, sections
    _assert_backup_half(
        sections, 'SR A', 'SR B', "SR A · 4 channel snake · 150'", "SR B · 4 channel snake · 100'",
        ["+10'", '—', "+25'", "+25'"], ["+10'", '—', "+10'", "+75'"], ['84', '84', '84', '56'])
    rows = _all_rows(sections)
    assert sum(int(r['PANELS']) for r in rows) == 28 * 11
    assert 'PX' not in [o['t'] for o in page['texts']]


def test_a_same_unit_pairing_is_one_section(seeded):
    """A card in HALVES mode returns each port on its own other half: the
    primary and the return are ONE unit, so the sheet has one section with
    no band over the backup half - no second unit is invented - and every
    row carries its return end beside it."""
    sections = _ports_table(seeded['SOLO - Data - Front View'])
    assert len(sections) == 1 and sections[0]['backup'] == [], sections
    rows = _all_rows(sections)
    assert rows and all(r['PANELS'] != '—' for r in rows), rows
    # every port has its return - on the same card, SOLO's other half
    assert all('SOLO' in r.get('B OUTPUT', '') for r in rows), rows
    assert sum(int(r['PANELS']) for r in rows) == 10 * 5



# ── 5b. OUTPUT only where it says something; columns their content's ──
#
# "my only issue with 2.3 is the non centered home runs, and the waste of
# space in the same table so we can look at examples of cleaning that up
# and sizing it dynamically" (owner, 2026-10-18, picking the merged
# layout): every column of the Ports table is its content's width, HOME RUN
# and PANELS stand centred under their headings, and OUTPUT is left out
# where every row of the sheet, both halves, only repeats its port's name
# ("SR A-1" landing on "SR A · 1"). A custom label, a sending card's name or
# "—" where nothing is placed keeps OUTPUT - for every row - and a table
# that runs on to a "(cont.)" sheet reads the same there, at the same
# widths.

# The seeded show, then: LOOSE, a wall placed nowhere; LONG, 32 ports on a
# second H9 - boxes LG A (backed by LG B) and LG C (backed by LG D), sixteen
# sockets each - so its Ports table outgrows a Letter sheet.
VARIANTS_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await j('POST', '/api/layer/add', {name: 'LOOSE', columns: 4, rows: 2, cabinet_width: 100, cabinet_height: 100,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 100, flowPattern: 'tl-h',
            processorType: 'novastar-armor', offset_x: 4000});
    await j('POST', '/api/layer/add', {name: 'LONG', columns: 10, rows: 32, cabinet_width: 250, cabinet_height: 250,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 100, flowPattern: 'tl-h',
            processorType: 'novastar-armor', offset_x: 6000});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const proc = st.processors[st.processors.length - 1];
    const pid = proc.id;
    const card = 'novastar-card-h-16xrj45-2xfiber';
    for (let s = 0; s < 4; s++) st = await j('PUT', `/api/processors/${pid}/slots/${s}`, {deviceId: card});
    const cards = st.processors.find(p => p.id === pid).slots.slice(0, 4).map(s => s.card.id);
    const names = ['LG A', 'LG B', 'LG C', 'LG D'];
    for (let k = 0; k < 4; k++) {
        st = await j('POST', `/api/processors/${pid}/cards/${cards[k]}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const box = st.processors.find(p => p.id === pid).slots[k].card.cvts[0].id;
        await j('PUT', `/api/processors/${pid}/cvts/${box}`, {name: names[k]});
    }
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${cards[0]}`, {backupCardId: cards[1]});
    await j('PUT', `/api/processors/${pid}/cards/${cards[2]}`, {backupCardId: cards[3]});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('binder_tables_variants');
    const long = app.project.layers.find(l => l.name === 'LONG');
    app.selectLayer(long);
    await app.refreshProcessors();
    for (const c of [cards[0], cards[2]]) {
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', {layerId: String(long.id), cardId: c});
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    return await j('GET', '/api/project');
}"""

# MAIN's first port named by hand: one row says more than its socket.
NAME_PORT_JS = """async ([n, name]) => {
    const app = window.app;
    const proj = await fetch('/api/project').then(r => r.json());
    const proc = proj.processors[0];
    const c1 = proc.slots[0].card.id;
    await fetch(`/api/processors/${proc.id}/cards/${c1}/ports/${n}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    return await fetch('/api/project').then(r => r.json());
}"""

# What the binder measures a cell and a heading with.
MEASURE_JS = """(items) => {
    const ctx = document.createElement('canvas').getContext('2d');
    return items.map(([t, size, weight]) => { ctx.font = window.app._bFont(size, weight); return ctx.measureText(t).width; });
}"""


@pytest.fixture(scope="module")
def variants(e2e_server, pw_browser):
    """The seeded show with LOOSE and LONG beside it, every sheet rendered
    on Tabloid and on Letter; then with MAIN's port 1 named "FEED 1"."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(SEED_BACKUP_JS)
    project = pg.evaluate(VARIANTS_JS)
    out = {'tabloid': pg.evaluate(SHEETS_JS, [project, OPTS])['pages'],
           'letter': pg.evaluate(SHEETS_JS, [project, {**OPTS, 'sheet': 'letter'}])['pages']}
    named = pg.evaluate(NAME_PORT_JS, [1, 'FEED 1'])
    out['named'] = pg.evaluate(SHEETS_JS, [named, OPTS])['pages']
    out['measure'] = lambda items: pg.evaluate(MEASURE_JS, items)
    assert not errors, errors[:3]
    yield out
    context.close()


def _sheet(pages, title):
    return next(p for p in pages if p['title'] == title)


def _heads_line(page):
    """The Ports table's headings, left to right, on the first line of them."""
    port = next(o for o in page['texts'] if o['t'] == 'PORT')
    return sorted([o for o in page['texts'] if abs(o['y'] - port['y']) < 0.5
                   and o['t'] in PORT_KEYS + ('PANELS',)], key=lambda o: o['x'])


def test_output_is_left_out_where_every_row_repeats_its_port(seeded):
    """MAIN: every socket - "SR A · 1" on the primary half, "SR B · 1" on the
    backup half - only repeats its port's name, so neither half prints an
    OUTPUT column and no socket is printed; each half is PORT and HOME RUN."""
    page = seeded['MAIN - Data - Front View']
    assert [o['t'] for o in _heads_line(page)] == ['PORT', 'HOME RUN', 'PORT', 'HOME RUN', 'PANELS']
    texts = [o['t'] for o in page['texts']]
    assert 'OUTPUT' not in texts
    assert not [t for t in texts if re.fullmatch(r'SR [AB] · \d+', t)], texts
    rows = _all_rows(_ports_table(page))
    assert [(r['PORT'], r['B PORT']) for r in rows] == [(f'SR A-{n}', f'SR B-{n}') for n in (1, 2, 3, 4)], rows


def test_output_stays_where_it_names_the_sending_card(seeded):
    """SOLO's ports land on a card, not a box: OUTPUT names the processor and
    the card ("H9 SOLO · 1"), which its port's name does not - so it stays."""
    page = seeded['SOLO - Data - Front View']
    rows = _all_rows(_ports_table(page))
    assert rows and all(r['OUTPUT'] and r['OUTPUT'] != r['PORT'] for r in rows), rows
    assert all(r.get('B OUTPUT') for r in rows), rows


def test_output_stays_on_every_row_where_one_port_is_named_by_hand(variants):
    """MAIN with port 1 named "FEED 1": that row's socket says something its
    name does not, so the sheet keeps OUTPUT - on EVERY row, both halves,
    the three that still repeat their names included."""
    page = _sheet(variants['named'], 'MAIN - Data - Front View')
    assert [o['t'] for o in _heads_line(page)] == ['PORT', 'OUTPUT', 'HOME RUN', 'PORT', 'OUTPUT',
                                                   'HOME RUN', 'PANELS']
    rows = _all_rows(_ports_table(page))
    assert [r['PORT'] for r in rows] == ['FEED 1', 'SR A-2', 'SR A-3', 'SR A-4'], rows
    assert [r['OUTPUT'] for r in rows] == [f'SR A · {n}' for n in (1, 2, 3, 4)], rows
    assert [r['B OUTPUT'] for r in rows] == [f'SR B · {n}' for n in (1, 2, 3, 4)], rows


def test_output_stays_where_nothing_is_placed(variants):
    """LOOSE is on no processor: every OUTPUT is "—", which repeats nothing,
    so the column stays - one half, no backup."""
    page = _sheet(variants['tabloid'], 'LOOSE - Data - Front View')
    assert [o['t'] for o in _heads_line(page)] == ['PORT', 'OUTPUT', 'HOME RUN', 'PANELS']
    rows = _all_rows(_ports_table(page))
    assert rows and all(r['OUTPUT'] == '—' for r in rows), rows


def test_every_column_stands_centred_under_its_heading(seeded, variants):
    """Every column is drawn centred (2026-10-18: "center every column in
    every binder table"), each heading and every cell under it on one x -
    never a short "25'" stranded at the left of a wide column; PORT and
    OUTPUT, which read from the left before, stand centred too."""
    want = 'center'
    for page in (seeded['MAIN - Data - Front View'], _sheet(variants['tabloid'], 'LOOSE - Data - Front View')):
        heads = _heads_line(page)
        for h in heads:
            assert h['align'] == want, (page['title'], h)
            cells = [o for o in page['texts'] if abs(o['x'] - h['x']) < 0.5 and o['y'] > h['y'] + 1
                     and o['size'] == page_cell_size(page)]
            assert cells, (page['title'], h)
            assert all(o['align'] == want for o in cells), (page['title'], h, cells)


def page_cell_size(page):
    """A Ports row's type size on this sheet (the cells' size, the sheet's
    fill applied): the size its PORT cells are drawn at."""
    port = next(o for o in page['texts'] if o['t'] == 'PORT')
    return next(o['size'] for o in page['texts'] if abs(o['x'] - port['x']) < 0.5 and o['y'] > port['y'] + 1
                and o['weight'] == 400)


def test_each_column_is_its_contents_width(variants):
    """LOOSE's one-half table: each column exactly as wide as its heading or
    its widest cell and the pad either side - every heading on its
    column's centre, so PORT's centre to OUTPUT's is half of each one's
    need, and so on - so the table is far narrower than the old fixed
    1020."""
    page = _sheet(variants['tabloid'], 'LOOSE - Data - Front View')
    heads = {o['t']: o for o in _heads_line(page)}
    rows = _all_rows(_ports_table(page))
    s = page_cell_size(page) / 24            # the sheet's fill
    measure = variants['measure']
    pad = 12 * 2

    def need(title, key):
        cells = [r[key] for r in rows]
        w = measure([[title, 21, 700]] + [[c, 24, 400] for c in cells])
        return max(w) + pad

    port, out, home, panels = (need('PORT', 'PORT'), need('OUTPUT', 'OUTPUT'),
                               need('HOME RUN', 'HOME RUN'), need('PANELS', 'PANELS'))
    near = lambda a, b: abs(a - b) <= 1.5 * s
    assert near(heads['OUTPUT']['x'] - heads['PORT']['x'], (port / 2 + out / 2) * s), (heads, port, s)
    assert near(heads['HOME RUN']['x'] - heads['OUTPUT']['x'], (out / 2 + home / 2) * s), (heads, out, home)
    assert near(heads['PANELS']['x'] - heads['HOME RUN']['x'], (home / 2 + panels / 2) * s), (heads, home, panels)
    assert port + out + home + panels < 700, (port, out, home, panels)


def test_a_long_table_reads_the_same_on_its_cont_sheet(variants):
    """LONG on Letter: its 32-port table runs on to "(cont.)" - and there it
    keeps the choice made for the whole table (no OUTPUT: every socket
    repeats its port's name) and its widths: the column it asked for comes
    with it, where the run-on used to be squeezed into the tables' column."""
    pages = [p for p in variants['letter'] if p['title'].startswith('LONG - Data - Front View')]
    with_ports = [p for p in pages if any(o['t'] == 'PORT' for o in p['texts'])]
    assert len(with_ports) >= 2 and with_ports[1]['title'].endswith('(cont.)'), [p['title'] for p in pages]
    lines = [_heads_line(p) for p in with_ports]
    for heads in lines:
        assert [o['t'] for o in heads] == ['PORT', 'HOME RUN', 'PORT', 'HOME RUN', 'PANELS'], heads
    # the same column widths on both sheets (each at its own fill)
    offsets = [[round((o['x'] - heads[0]['x']) / (heads[0]['size'] / 21), 1) for o in heads] for heads in lines]
    assert all(abs(a - b) <= 1 for o in offsets[1:] for a, b in zip(offsets[0], o)), offsets
    labels = [o['t'] for p in with_ports for o in p['texts'] if re.fullmatch(r'LG [AC]-\d+', o['t'])]
    assert len(labels) == 32, labels
    assert not [o for p in with_ports for o in p['texts'] if re.fullmatch(r'LG [A-D] · \d+', o['t'])]


# ── 6. the tables wrap around a wall that leaves the sheet half empty ────
#
# "look at page 3 here we are wasting tons of space due to the shape of the
# screen" (2026-09-26): side and stack keep every block whole in its column,
# so a long table beside a wide wall held the wall to the width it left, and
# under it to the height it left. The wrap layout runs the tables down the
# columns beside the map, as tall as the map and its bubble, then across the
# full width under it - taken only where it makes the wall 10% larger - and
# a short block (the Facts, the Cables) is never split to get there.

def test_the_tables_wrap_around_the_map(seeded):
    """MAIN's power sheet on Tabloid: the 28 x 11 wall over the tables, its
    circuit table - too long for one column under the wall at a size
    worth having - running on from one column to the next, the Cables and
    the Facts whole in the third, each once, everything under the view."""
    page = seeded['MAIN - Power - Front View']
    assert page['layout'] == 'wrap', (page['layout'], page['extent'])
    t = [o['t'] for o in page['texts']]
    assert t.count('FACTS') == 1 and t.count('CABLES THIS SCREEN') == 1, t
    view = next(o for o in page['texts'] if o['t'] == 'MAIN · POWER · FRONT VIEW' and o['x'] < 1000)
    at = lambda name: [(o['x'], o['y']) for o in page['texts'] if o['t'] == name]
    circuits, cables, facts = at('CIRCUITS'), at('CABLES THIS SCREEN'), at('FACTS')
    # the circuits table in two columns, side by side, its heading repeated
    assert len(circuits) == 2 and circuits[0][1] == circuits[1][1] and circuits[0][0] < circuits[1][0], circuits
    # the short blocks whole, together, in the next column
    assert cables[0][0] == facts[0][0] > circuits[1][0] and cables[0][1] < facts[0][1], (cables, facts)
    assert all(y > view['y'] for _x, y in circuits + cables + facts), view
