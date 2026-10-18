"""The binder's fiber strands by colour, its title block's people, and a
new Rev logging its row as it is committed (2026-10-17).

"why don't the colors come through on the binder for fiber?" The
processor sheet's FIBER CONNECTIONS and STRAND MAP already swatched each
strand; the data sheet's band and the Breakout boxes table named the
strands by number only ("X1 TAC A (TAC 8) 1-2 · X2 TAC A 3-4"). Now:

  A  the data sheet's band over a box: the box on its line, then each
     input's strands a line each - "X1 TAC A (TAC 24)  [] 1 Blue" over
     "[] 2 Orange" - named and swatched as the strand map names them;
  B  the Breakout boxes table's FIBER: the input on its line, then each
     strand on a line of its own, swatched;
  C  the swatches bigger (24 px), STRAND MAP's strand cell tinted its own
     colour and its name bold - the name stays, so black and white still
     reads - and the tracer past 12 a stripe that reaches the PDF;
  FIBER CONNECTIONS puts one strand to a line, every row alike.

A cable labelled by number prints its strands as numbers in A and B with
no swatch beside them; sub-unit labels read as the strand map reads them.

The title block: the Engineer (the preference, getEngineerName) under the
Drafter, only where one is set; the project manager's phone and email
take a line only where typed, so a blank one leaves no gap above Drafter.

The Rev field: committing a new Rev (change - blur or Enter - never a
keystroke) adds its REVISIONS row there and then, in the same undo entry
as the rev; a Rev that has a row adds nothing; the note committed after
it lands in that row; an export at that Rev logs nothing more.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_binder_fiber_and_title.py -v --browser chromium
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL: a Brompton wall on an SX40 running both loops with its backup
# processor (WALL BU). TAC A, 24 strands, feeds XD A's X1 (1-2) and X2
# (3-4); the loop's far box XD B takes 13-14 on its X1, past 12 - each with
# its black tracer.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 4,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'WALL'});
    const sx = st.processors[0];
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${sx.id}`, {redundancy: true, backupUnit: {name: 'WALL BU'}});
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 24, ft: 300, connector: 'LC duplex',
                                               link: {boxId: xds[0], key: 'p1'}});
    const cable = st.fiberCables[0].id;
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[0]}/fiber-links/b1`, {cable});
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[1]}/fiber-links/p1`, {cable, strands: [13, 14]});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_title_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 9});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.resetHistory('Fiber Title Seed');
    return {sx: sx.id, xds, cable, wall: wall.id};
}"""

# One sheet of the set, as the recorder wrote it: its text and rect ops (in
# page units, the fill scale already through them), its fill scale and the
# title block's sections.
SHEET_JS = """(kind) => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                   scope: {kind: 'show'}, cover: false, pull: false, hardware: true, wiring: false };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === kind);
    if (i < 0) return null;
    const r = app.renderBinderPage(opts, i);
    return { scale: plan[i].scale || 1, title: plan[i].title,
             texts: r.record.ops.filter(o => o.op === 'text'),
             rects: r.record.ops.filter(o => o.op === 'rect'),
             sections: (r.titleBlock || {}).sections || null };
}"""

PUT_CABLE_JS = """async ([id, body]) => {
    await fetch(`/api/fiber-cables/${id}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    await window.app.refreshProcessors();
    await window.app.refreshPortAssignment();
}"""

BLUE, ORANGE, WHITE, BLACK = '#1f5fa8', '#f28020', '#f5f5f5', '#1a1a1a'
FIBER_HEXES = {'#1f5fa8', '#f28020', '#1a9a48', '#7a4a2e', '#777777', '#f5f5f5',
               '#b82535', '#1a1a1a', '#edd31c', '#7a3f9e', '#e09ba8', '#5ebfc2'}


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _sheet(pg, kind):
    out = pg.evaluate(SHEET_JS, kind)
    assert out, f'no {kind} sheet'
    return out


def _words(sheet):
    return [t['text'] for t in sheet['texts']]


def _run(words, run):
    """Where `run` stands in `words` as consecutive texts, else -1."""
    for i in range(len(words) - len(run) + 1):
        if words[i:i + len(run)] == run:
            return i
    return -1


def _fill(r):
    return str(r.get('fill') or '').lower()


def _swatch_before(sheet, text_op):
    """The filled square drawn just left of a strand's name, on its line."""
    side = 24 * sheet['scale']
    hits = [r for r in sheet['rects']
            if r.get('fill') and abs(r['w'] - side) < 0.6 and abs(r['h'] - side) < 0.6
            and 0 < text_op['x'] - r['x'] <= 34 * sheet['scale']
            and r['y'] <= text_op['y'] <= r['y'] + r['h'] + 6 * sheet['scale']]
    return hits[0] if hits else None


def _line_centre(pg, sheet, text_op):
    """The middle of a swatched strand's line - its swatch, the gap the
    swatch keeps, then its name - where a centred cell stands it."""
    sw = _swatch_before(sheet, text_op)
    assert sw, text_op
    w = pg.evaluate("""([t, size, weight]) => {
        const ctx = document.createElement('canvas').getContext('2d');
        ctx.font = window.app._bFont(size, weight);
        return ctx.measureText(t).width; }""", [text_op['text'], text_op['size'], text_op['weight']])
    return (sw['x'] + text_op['x'] + w) / 2


def _tint(hex_colour, k=0.24):
    n = int(hex_colour.lstrip('#'), 16)
    ch = lambda v: f'{round(255 - (255 - v) * k):02x}'  # noqa: E731
    return '#' + ch((n >> 16) & 255) + ch((n >> 8) & 255) + ch(n & 255)


def _outline_round(sheet, texts):
    """The thin stroked rect drawn round these texts - the group outline -
    or None: one rect holding every text's line, swatches included."""
    s = sheet['scale']
    xs = [t['x'] for t in texts]
    ys = [t['y'] for t in texts]
    for r in sheet['rects']:
        # the group outline's own ink (the binder's MUTED), not a border
        if str(r.get('stroke') or '').lower() != '#666666' or r.get('fill'):
            continue
        if r['w'] < 60 * s or r['h'] < 20 * s:
            continue
        if r['x'] < min(xs) and r['x'] + r['w'] > max(xs) \
                and r['y'] < min(ys) - 18 * s and r['y'] + r['h'] > max(ys):
            return r
    return None


# ── A: the data sheet's band ─────────────────────────────────────────────

def test_the_data_sheets_band_names_each_strand_by_its_colour_a_line_each(page):
    """Over XD A's ports: the box on its line, then each input as a group
    (2026-10-17: "group each strand pair with its input") - "X1" over
    "TAC A (TAC 24)" centred beside "1 Blue" over "2 Orange", then X2's 3
    Green and 4 Brown - the strands in one column, each with its 24 px
    swatch, each input in its own thin outline; the backup half's XD B
    reads 13 Blue/Black and 14 Orange/Black, each swatch carrying its black
    tracer stripe. The one-line summary "1-2 · X2 TAC A 3-4" is gone."""
    pg, ids = page
    sheet = _sheet(pg, 'data')
    words = _words(sheet)
    at = _run(words, ['X1', 'TAC A (TAC 24)', '1 Blue', '2 Orange', 'X2', 'TAC A', '3 Green', '4 Brown'])
    assert at >= 0, words[:80]
    ops = sheet['texts'][at:at + 8]
    s = sheet['scale']
    head, sub, blue, orange = ops[0], ops[1], ops[2], ops[3]
    # the label centred on its strands: its two lines on the strands' two
    assert abs((head['y'] + sub['y']) / 2 - (blue['y'] + orange['y']) / 2) < 0.6, (head, sub, blue, orange)
    assert abs((orange['y'] - blue['y']) - 30 * s) < 0.6, (blue, orange)  # a strand to a line
    assert abs(orange['x'] - blue['x']) < 0.5 and abs(ops[6]['x'] - blue['x']) < 0.5, ops
    assert head['x'] < blue['x'], (head, blue)                           # the label to their left
    assert _fill(_swatch_before(sheet, blue) or {}) == BLUE, blue
    assert _fill(_swatch_before(sheet, orange) or {}) == ORANGE, orange
    # each input its own outline, round its label and its strands
    assert _outline_round(sheet, [head, sub, blue, orange]), 'X1 is not outlined'
    assert _outline_round(sheet, ops[4:8]), 'X2 is not outlined'
    assert not _outline_round(sheet, [blue, ops[6]]), 'X1 and X2 share an outline'
    assert not [w for w in words if '1-2 · X2 TAC A 3-4' in w], words
    # the backup half: past 12, each swatch with its tracer stripe
    i13 = words.index('13 Blue/Black')
    t13 = sheet['texts'][i13]
    sw = _swatch_before(sheet, t13)
    assert sw and _fill(sw) == BLUE, t13
    stripes = [r for r in sheet['rects'] if _fill(r) == BLACK and abs(r['x'] - sw['x']) < 0.5
               and abs(r['w'] - sw['w']) < 0.5 and sw['y'] < r['y'] < sw['y'] + sw['h']]
    assert stripes and stripes[0]['h'] < sw['h'] / 2, stripes
    assert words[i13 + 1] == '14 Orange/Black', words[i13:i13 + 3]
    assert ids['errors'] == []


# ── B and C: the processor sheet ─────────────────────────────────────────

def test_the_processor_sheet_stacks_and_swatches_every_strand(page):
    """B: Breakout boxes' FIBER - "X1 TAC A (TAC 24)", then 1 Blue and 2
    Orange each on its own line, swatched. FIBER CONNECTIONS: one strand to
    a line in AT THE PROCESSOR and AT THE BREAKOUT, every row alike, no
    " ·" after a strand. C:
    the swatches 24 px; STRAND MAP's strand cell tinted its own colour, its
    name bold; White keeps its ink ring."""
    pg, ids = page
    sheet = _sheet(pg, 'processor')
    words = _words(sheet)
    s = sheet['scale']
    # B, grouped (2026-10-17): "X1" over "TAC A (TAC 24)" centred beside 1
    # Blue over 2 Orange, outlined; X2 its own group
    at = _run(words, ['X1', 'TAC A (TAC 24)', '1 Blue', '2 Orange', 'X2', 'TAC A', '3 Green', '4 Brown'])
    assert at >= 0, words[:120]
    head, sub, blue, orange = sheet['texts'][at:at + 4]
    assert abs((head['y'] + sub['y']) / 2 - (blue['y'] + orange['y']) / 2) < 0.6, (head, sub, blue, orange)
    assert abs((orange['y'] - blue['y']) - 30 * s) < 0.6, (blue, orange)
    assert head['x'] < blue['x'] and abs(blue['x'] - orange['x']) < 0.5, (head, blue, orange)
    assert _fill(_swatch_before(sheet, blue) or {}) == BLUE
    assert _outline_round(sheet, [head, sub, blue, orange]), 'X1 is not outlined'
    assert _outline_round(sheet, sheet['texts'][at + 4:at + 8]), 'X2 is not outlined'
    # FIBER CONNECTIONS: at the processor 1 Blue over 2 Orange; at the
    # breakout the TAC pair flipped, 2 Orange over 1 Blue - never side by
    # side, and no " ·" trailing a strand that has a line of its own. Each
    # line - its swatch and its name - stands on the cell's middle
    # (2026-10-18), so the two lines share a centre, not a left edge.
    pairs = [(a, b) for a, b in zip(sheet['texts'], sheet['texts'][1:])
             if (a['text'], b['text']) in (('1 Blue', '2 Orange'), ('2 Orange', '1 Blue'),
                                           ('13 Blue/Black', '14 Orange/Black'),
                                           ('14 Orange/Black', '13 Blue/Black'))]
    assert len(pairs) >= 5, words                      # B's pair and Fiber connections' four
    for a, b in pairs:
        # an outlined input group (Breakout boxes) keeps its strands in one
        # column inside the outline; a strand list cell centres each line
        grouped = abs(a['x'] - b['x']) < 0.5 and _outline_round(sheet, [a, b])
        assert grouped or abs(_line_centre(pg, sheet, a) - _line_centre(pg, sheet, b)) < 0.6, (a, b)
        assert abs((b['y'] - a['y']) - 30 * s) < 0.6, (a, b)
    assert not [w for w in words if w.endswith(' ·') and w.split(' ')[0].isdigit()], words
    # STRAND MAP: the names bold, the cell tinted, the swatch 24 px
    bold = {t['text']: t for t in sheet['texts'] if t['weight'] == 700}
    for name, colour in (('1 Blue', BLUE), ('2 Orange', ORANGE), ('6 White', WHITE), ('13 Blue/Black', BLUE)):
        t = bold.get(name)
        assert t, (name, sorted(bold))
        assert _fill(_swatch_before(sheet, t) or {}) == colour, name
        tint = [r for r in sheet['rects'] if _fill(r) == _tint(colour) and r['x'] < t['x'] and r['y'] < t['y']
                and r['y'] + r['h'] > t['y'] - 10 * s and r['w'] > 100 * s]
        assert tint, (name, _tint(colour))
    white = _swatch_before(sheet, bold['6 White'])
    rings = [r for r in sheet['rects'] if r.get('stroke') and abs(r['x'] - white['x']) < 0.5
             and abs(r['y'] - white['y']) < 0.5 and abs(r['w'] - white['w']) < 0.5]
    assert rings, white
    assert ids['errors'] == []


# ── numbers and sub-units ────────────────────────────────────────────────

def test_a_cable_read_in_numbers_prints_numbers_and_no_swatch_in_the_band_and_the_table(page):
    """Labels 'numbers' ("If it is numbers only then don't use colors as
    they won't have colors in real life"): the band's X1 group reads "1"
    over "2", the Breakout boxes table "1" and "2" a line each, and
    neither sheet carries a strand swatch anywhere - not in STRAND MAP, not
    in FIBER CONNECTIONS, no strand map tint. Sub-units read as the strand
    map reads them, "Blue unit · 1 Blue", swatched."""
    pg, ids = page
    try:
        pg.evaluate(PUT_CABLE_JS, [ids['cable'], {'labels': 'numbers'}])
        sheet = _sheet(pg, 'data')
        words = _words(sheet)
        assert _run(words, ['X1', 'TAC A (TAC 24)', '1', '2', 'X2', 'TAC A', '3', '4']) >= 0, words[:80]
        side = 24 * sheet['scale']
        squares = [r for r in sheet['rects'] if _fill(r) in FIBER_HEXES
                   and abs(r['w'] - side) < 0.6 and abs(r['h'] - side) < 0.6]
        assert squares == [], squares
        parts = pg.evaluate("""(ids) => {
            const app = window.app;
            const box = app._dockFindCvt(ids.xds[0]).cvt;
            return { parts: app._bBoxFiberParts(box), lines: app._bBoxBandLines(box) };
        }""", ids)
        assert [p['text'] for p in parts['parts']] == ['X1 TAC A (TAC 24)', '1', '2', 'X2 TAC A', '3', '4']
        assert all(not p.get('swatch') for p in parts['parts']), parts
        assert all(not (isinstance(t, dict) and any(st['swatch'] for st in t['group']['strands']))
                   for t in parts['lines']), parts
        proc = _sheet(pg, 'processor')
        pw = _words(proc)
        assert _run(pw, ['X1', 'TAC A (TAC 24)', '1', '2', 'X2', 'TAC A', '3', '4']) >= 0, pw[:120]
        side = 24 * proc['scale']
        squares = [r for r in proc['rects'] if _fill(r) in FIBER_HEXES
                   and abs(r['w'] - side) < 0.6 and abs(r['h'] - side) < 0.6]
        assert squares == [], squares
        tints = {_tint(h) for h in FIBER_HEXES}
        assert not [r for r in proc['rects'] if _fill(r) in tints], 'a strand map tint in numbers mode'
        # FIBER CONNECTIONS: 1 over 2 at the processor, 2 over 1 at the box
        assert _run(pw, ['1', '2']) >= 0 and _run(pw, ['2', '1']) >= 0, pw
        # STRAND MAP: the numbers, plain
        maps = pg.evaluate("(sx) => window.app._bStrandMaps(window.app._processorsResolved"
                           ".find(p => p.id === sx))[0].rows.slice(0, 3)"
                           ".map(r => [r.cells[0], r.swatch])", ids['sx'])
        assert maps == [['1', None], ['2', None], ['3', None]], maps
        # sub-units, coloured again
        pg.evaluate(PUT_CABLE_JS, [ids['cable'], {'labels': 'colors', 'subunits': True}])
        sheet = _sheet(pg, 'data')
        words = _words(sheet)
        at = _run(words, ['X1', 'TAC A (TAC 24)', 'Blue unit · 1 Blue', 'Blue unit · 2 Orange'])
        assert at >= 0, words[:80]
        assert _fill(_swatch_before(sheet, sheet['texts'][at + 2]) or {}) == BLUE
        assert 'Orange unit · 1 Blue' in words, words      # strand 13 in the second unit
    finally:
        pg.evaluate(PUT_CABLE_JS, [ids['cable'], {'labels': 'colors', 'subunits': False}])
    assert ids['errors'] == []


# ── the title block's people ─────────────────────────────────────────────

PEOPLE_JS = """async ([engineer, pm, drafter]) => {
    const app = window.app;
    await app.setEngineerName(engineer);
    app.project.binder = { projectManager: pm, drafter };
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: false, data: true},
                   scope: {kind: 'show'}, cover: false, pull: false, hardware: false, wiring: false };
    const r = app.renderBinderPage(opts, 0);
    const texts = r.record.ops.filter(o => o.op === 'text').map(o => ({ t: o.text, y: o.y }));
    return { texts, people: r.titleBlock.sections.people };
}"""


def _people(pg, engineer, pm, drafter=''):
    out = pg.evaluate(PEOPLE_JS, [engineer, pm, drafter])
    words = [t['t'] for t in out['texts']]
    y = {t['t']: t['y'] for t in out['texts']}
    return out, words, y


def test_a_blank_phone_or_email_leaves_no_gap_above_drafter(page):
    """The project manager's name always has its line; the phone and the
    email take one only where typed. Drafter stands 78 under the
    manager's label with neither, 106 with one, 134 with both - the
    section 274, 302 and the 330 it always was."""
    pg, ids = page
    try:
        for pm, gap, h in (({'name': 'Jordan Reyes'}, 78, 274),
                           ({'name': 'Jordan Reyes', 'email': 'jr@example.com'}, 106, 302),
                           ({'name': 'Jordan Reyes', 'phone': '(555) 010-2030',
                             'email': 'jr@example.com'}, 134, 330)):
            out, words, y = _people(pg, '', pm)
            assert y['Drafter:'] - y['Project Manager:'] == gap, (pm, y['Drafter:'] - y['Project Manager:'])
            assert out['people']['h'] == h, (pm, out['people'])
            at = words.index('Project Manager:')
            assert words[at + 1:at + 1 + len(pm)] == list(pm.values()) or \
                words[at + 1:at + 1 + len(pm)] == [pm.get(k) for k in ('name', 'phone', 'email') if pm.get(k)]
        # a manager with no name still prints the label and its blank line
        out, words, y = _people(pg, '', {})
        assert y['Drafter:'] - y['Project Manager:'] == 78 and out['people']['h'] == 274
    finally:
        pg.evaluate("async () => { delete window.app.project.binder; await window.app.setEngineerName(''); }")
    assert ids['errors'] == []


def test_the_engineer_prints_under_the_drafter_only_where_one_is_set(page):
    """The engineer set: "Engineer:" and the name, 78 under the Drafter,
    the people's section 78 taller; with no drafter typed the Drafter
    still reads the engineer. No engineer: no Engineer line at all, not
    an empty label."""
    pg, ids = page
    pm = {'name': 'Jordan Reyes', 'phone': '(555) 010-2030', 'email': 'jr@example.com'}
    try:
        out, words, y = _people(pg, 'Morgan Keller', pm, 'Sam Okafor')
        at = words.index('Engineer:')
        assert words[at + 1] == 'Morgan Keller', words[at - 2:at + 2]
        assert y['Engineer:'] - y['Drafter:'] == 78
        assert words[words.index('Drafter:') + 1] == 'Sam Okafor'
        assert out['people']['h'] == 330 + 78, out['people']
        out, words, y = _people(pg, 'Morgan Keller', pm, '')
        assert words[words.index('Drafter:') + 1] == 'Morgan Keller'
        assert words[words.index('Engineer:') + 1] == 'Morgan Keller'
        out, words, y = _people(pg, '', pm, 'Sam Okafor')
        assert 'Engineer:' not in words, words
        assert out['people']['h'] == 330
    finally:
        pg.evaluate("async () => { delete window.app.project.binder; await window.app.setEngineerName(''); }")
    assert ids['errors'] == []


# ── the Rev logs its row as it is committed ──────────────────────────────

def _today():
    import datetime
    d = datetime.date.today()
    return f"{d.month}/{d.day}/{d.year % 100:02d}"


REV_SETUP_JS = """async () => {
    const app = window.app;
    delete app.project.binder;
    await app._persistBinderInfo();
    app.setPullSheetSetting('rev', '1.0', 'Set Pull Sheet Revision');
    await app.setEngineerName('Morgan Keller');
    app.openExportModal('binder');
    app.syncBinderControls();
    document.getElementById('export-binder-revision-note').value = '';
    app._binderRevOpen = null;
    app.resetHistory('Rev Test');
}"""

REV_TEARDOWN_JS = """async () => {
    const app = window.app;
    delete app.project.binder;
    await app._persistBinderInfo();
    app.setPullSheetSetting('rev', '1.0', 'Set Pull Sheet Revision');
    document.getElementById('export-binder-revision-note').value = '';
    await app.setEngineerName('');
    const modal = document.getElementById('export-modal');
    if (modal) modal.style.display = 'none';
}"""

STATE_JS = """async () => {
    const app = window.app;
    await app._binderPushQueue;
    await new Promise(r => setTimeout(r, 300));
    const served = await fetch('/api/project').then(r => r.json());
    return { revs: app.getBinderInfo().revisions, rev: app.getPullSheetSettings().rev,
             servedRevs: ((served.binder || {}).revisions) || [],
             servedRev: (served.pullSheet || {}).rev || null,
             note: document.getElementById('export-binder-revision-note').value,
             listed: [...document.querySelectorAll('#export-binder-revisions .binder-rev-row')].map(r =>
                 r.querySelector('.binder-rev-description').value),
             actions: app.history.slice(1, app.historyIndex + 1).map(h => h.action) };
}"""

COMMIT_JS = """([id, v]) => { const el = document.getElementById(id); el.value = v;
                              el.dispatchEvent(new Event('change')); }"""


def test_committing_a_new_rev_logs_its_row_once_and_one_undo_takes_both_back(page):
    """Rev 1.0 -> 1.1 committed: one row - No. 1, rev 1.1, today, MK, the
    note - in the dialog's list and on the server, one undo entry ('Log
    Revision'). Back to a rev that has its row: nothing logged. Undo of
    the 1.1 commit takes the rev AND its row back in one step."""
    pg, ids = page
    today = _today()
    try:
        pg.evaluate(REV_SETUP_JS)
        pg.evaluate(COMMIT_JS, ['export-binder-revision-note', 'Fiber colours'])
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '1.1'])
        st = pg.evaluate(STATE_JS)
        row = {'no': 1, 'rev': '1.1', 'date': today, 'by': 'MK', 'description': 'Fiber colours'}
        assert st['revs'] == [row] and st['servedRevs'] == [row], st
        assert st['rev'] == '1.1' and st['servedRev'] == '1.1', st
        assert st['listed'] == ['Fiber colours'] and st['actions'] == ['Log Revision'], st
        # the same rev again, and a rev that already has its row: nothing
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '1.1'])
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '1.2'])
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '1.1'])
        st = pg.evaluate(STATE_JS)
        assert [r['rev'] for r in st['revs']] == ['1.1', '1.2'], st['revs']
        assert st['actions'] == ['Log Revision', 'Log Revision', 'Set Pull Sheet Revision'], st['actions']
        # undo twice: back to 1.2, then the 1.2 commit - rev and row - gone
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(400)
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(600)
        st = pg.evaluate(STATE_JS)
        assert st['rev'] == '1.1' and [r['rev'] for r in st['revs']] == ['1.1'], st
        assert st['servedRev'] == '1.1' and [r['rev'] for r in st['servedRevs']] == ['1.1'], st
    finally:
        pg.evaluate(REV_TEARDOWN_JS)
    assert ids['errors'] == []


def test_typing_a_rev_logs_only_the_committed_value(page):
    """Typed key by key into the Rev field, "2.0" logs 2.0 once the field
    commits (Enter) - never "2" or "2." on the way."""
    pg, ids = page
    try:
        pg.evaluate(REV_SETUP_JS)
        field = pg.locator('#export-binder-rev')
        field.click()
        field.press('Control+a' if not pg.evaluate("navigator.platform").startswith('Mac') else 'Meta+a')
        field.press('Backspace')
        field.press_sequentially('2.0', delay=40)
        mid = pg.evaluate("() => window.app.getBinderInfo().revisions.length")
        field.press('Enter')
        pg.locator('#export-binder-revision-note').click()
        st = pg.evaluate(STATE_JS)
        assert mid == 0, mid
        assert [r['rev'] for r in st['revs']] == ['2.0'] and st['rev'] == '2.0', st
        assert st['actions'] == ['Log Revision'], st['actions']
    finally:
        pg.evaluate(REV_TEARDOWN_JS)
    assert ids['errors'] == []


def test_the_note_lands_in_the_row_just_logged_and_the_export_adds_no_second(page):
    """The rule: the note box belongs to the newest row a Rev commit
    logged, while its rev is the Rev - a note committed after the Rev
    lands in that row's description. A new Rev does not carry the last
    row's note onto its own row: the box clears and the new row starts
    blank. An export at a Rev that has its row logs nothing."""
    pg, ids = page
    try:
        pg.evaluate(REV_SETUP_JS)
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '3.0'])
        pg.evaluate(COMMIT_JS, ['export-binder-revision-note', 'Strand colours'])
        st = pg.evaluate(STATE_JS)
        assert [(r['rev'], r['description']) for r in st['revs']] == [('3.0', 'Strand colours')], st
        assert st['servedRevs'][0]['description'] == 'Strand colours'
        assert st['actions'] == ['Log Revision', 'Edit Revision'], st['actions']
        # the export at 3.0: no second row, no history entry
        out = pg.evaluate("""async () => {
            const app = window.app;
            const realFetch = window.fetch, saved = app.saveBlobWithPicker;
            window.fetch = async (url, init) => String(url).includes('/api/export/pdf-from-')
                ? { ok: true, blob: async () => new Blob(['%PDF-fake'], {type: 'application/pdf'}) }
                : realFetch(url, init);
            app.saveBlobWithPicker = async () => {};
            const h = app.historyIndex;
            try { await app.exportBinder('Fiber Title'); }
            finally { window.fetch = realFetch; app.saveBlobWithPicker = saved; }
            return { added: app.history.slice(h + 1).map(x => x.action),
                     revs: app.getBinderInfo().revisions.map(r => r.rev) };
        }""")
        assert out == {'added': [], 'revs': ['3.0']}, out
        # 3.1: the note box still mirrors 3.0's row, so 3.1 starts blank
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '3.1'])
        st = pg.evaluate(STATE_JS)
        assert [(r['rev'], r['description']) for r in st['revs']] == \
            [('3.0', 'Strand colours'), ('3.1', '')], st['revs']
        assert st['note'] == ''
        # a row that is no longer the Rev's takes no note: back on 3.0
        pg.evaluate(COMMIT_JS, ['export-binder-rev', '3.0'])
        pg.evaluate(COMMIT_JS, ['export-binder-revision-note', 'for the next rev'])
        st = pg.evaluate(STATE_JS)
        assert [r['description'] for r in st['revs']] == ['Strand colours', ''], st['revs']
    finally:
        pg.evaluate(REV_TEARDOWN_JS)
    assert ids['errors'] == []
