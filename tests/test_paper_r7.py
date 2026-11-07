"""Binder paperwork, round 7 (owner ruling, 2026-10-23): a power sheet's
bracket labels, tags plus a key.

  * Each multi's bracket says "<multi name> · <length>". Where every label
    fits whole the sheet prints as it always did. Where one will not fit
    legibly (14 or more) beside the wall, every bracket on the sheet takes
    a short tag ("12", or "SL12" where two distros share a number) and a
    small KEY on the same sheet lists each tag's full label.
  * Layouts are ranked by how many labels fit whole: a 36 x 6 wall's three
    long-named multis grow the gutter a little and print whole, length and
    all, rather than dropping the length.
  * An edge bracket's label may slide inward along its own bracket.
  * A deep stack grows the gutter before it drops every label to the floor.
  * The logged label extent is the drawn one, never clamped to its room.
  * Free-row notes: "->  Tail TAILS" reads "->  Cable TAILS", the app and
    the workbook alike.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_r7.py -q --browser chromium
"""

import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402

SHEETS = ('letter', 'tabloid', 'a4', 'a3', 'archc', 'archd')


# ── 6. free-row notes ────────────────────────────────────────────────────

ARROW_NOTES = {
    '->  Tail TAILS': '->  Cable TAILS',
    '→ TAIL tails': '→ CABLE tails',
    '-> TRUE1 tail': '-> TRUE1 cable',
    'Edison → tail': 'Edison → cable',
    'Tail rope for the Edison → TRUE1 tail': 'Tail rope for the Edison → TRUE1 cable',
}


def test_the_tail_right_after_the_arrow_is_the_adapters_in_the_workbook():
    for typed, want in ARROW_NOTES.items():
        assert pull_sheet.free_row_notes_spelling(typed) == want, (typed, pull_sheet.free_row_notes_spelling(typed))


pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


WALLS = [{'name': 'TALL', 'cols': 10, 'rows': 60, 'x': 0},
         {'name': 'WIDE', 'cols': 36, 'rows': 6, 'x': 3000},
         {'name': 'COLS', 'cols': 6, 'rows': 5, 'x': 11000},
         {'name': 'MAIN', 'cols': 10, 'rows': 6, 'x': 13000}]

SEED_JS = """async (walls) => {
    const app = window.app;
    await app._layerSavesSettled();
    const j = async (method, url, body) => (await fetch(url, {
        method, headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body) })).json();
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.services; delete proj.cableStock;
    await j('PUT', '/api/project', proj);
    for (const w of walls) {
        await j('POST', '/api/layer/add', { name: w.name, columns: w.cols, rows: w.rows,
            cabinet_width: 200, cabinet_height: 200, offset_x: w.x });
    }
    const p = await j('GET', '/api/project');
    app.project = p;
    app.selectLayer(p.layers[0]);
    app.renderLayers();
}"""

# one wall shown, set up as `o.wall` says, the rest hidden
CONFIG_JS = """(o) => {
    const app = window.app;
    for (const l of app.project.layers) {
        for (const p of l.panels || []) delete p.blank;
        Object.assign(l, { powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                           powerFlowPattern: 'tl-h', powerCustomPaths: {}, powerCustomIndex: 1,
                           powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                           powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                           powerLabelOverrides: {}, powerCircuitCables: {},
                           powerJumpV: 1, powerJumpH: 1, powerPanelInput: undefined,
                           powerBreakoutType: 'soca-true1', locked: false },
                      l.name === o.name ? o.wall : {});
        l.visible = l.name === o.name;
        app.normalizePowerBreakout(l);
    }
    app.project.distros = JSON.parse(JSON.stringify(o.distros));
    app.project.cableUnit = 'ft';
    app.project.groups = [];
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app.getDistros();
    app.updateLayers(app.project.layers);
    return app.screenCircuits(app.project.layers.find(l => l.name === o.name)).length;
}"""

# The power sheet as printed: its brackets and key as logged, every text
# op measured (rotated ones included), the drawing area, the page.
SHEET_JS = """(sheet) => {
    const app = window.app;
    app._circuitTailCache = null;
    const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
        hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'power');
    const r = app.renderBinderPage(opts, i);
    const c = document.createElement('canvas').getContext('2d');
    const texts = r.record.ops.filter(op => op.op === 'text' && String(op.text).trim()).map(op => {
        c.font = app._bFont(op.size, op.weight);
        return { t: op.text, x: op.x, y: op.y, size: op.size, w: c.measureText(op.text).width,
                 align: op.align || 'left', baseline: op.baseline || 'alphabetic', rot: op.rotate || 0 };
    });
    return { brackets: r.brackets, key: r.bracketKey, map: r.map, texts,
             da: app._bGeo(r.sheet, true).da, W: r.record.width, H: r.record.height };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate(SEED_JS, WALLS)
    pg.wait_for_function("() => window.app.project.layers.length === 4")
    yield pg, errors
    context.close()


def dist(name, i=1):
    return {'id': f'd{i}', 'name': name, 'ratingA': 400, 'system': '120/208',
            'outputRows': [{'id': f'r{i}', 'connector': 'soca', 'count': 130, 'coupling': 'll', 'breakerA': 20}]}


def multis(n, did='d1', start=1, length=None):
    return {'powerSocaDistro': {str(i): did for i in range(1, n + 1)},
            'powerSocaNumber': {str(i): start + i - 1 for i in range(1, n + 1)},
            'powerSocaLengths': {str(i): length for i in range(1, n + 1)} if length else {}}


def configure(pg, name, wall, distros):
    return pg.evaluate(CONFIG_JS, {'name': name, 'wall': wall, 'distros': distros})


# ── the checks, on the drawn ink ─────────────────────────────────────────

def box(t):
    """A text op's ink box on the page, rotation and all."""
    w, s = t['w'], t['size']
    x0 = -w / 2 if t['align'] == 'center' else -w if t['align'] in ('right', 'end') else 0
    b = t['baseline']
    ly0, ly1 = ((-0.36 * s, 0.36 * s) if b == 'middle' else (0, 0.9 * s) if b in ('top', 'hanging')
                else (-0.72 * s, 0.05 * s))
    c, sn = math.cos(t['rot']), math.sin(t['rot'])
    pts = [(t['x'] + c * lx - sn * ly, t['y'] + sn * lx + c * ly) for lx in (x0, x0 + w) for ly in (ly0, ly1)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def meets(a, b, tol=0.5):
    return min(a[2], b[2]) - max(a[0], b[0]) > tol and min(a[3], b[3]) - max(a[1], b[1]) > tol


def whole(b):
    """The label says the name and its length, never cut."""
    ls = b['lines']
    if any(t.endswith('…') for t in ls):
        return False
    if len(ls) == 1:
        return ls[0].startswith(b['name'] + ' · ')
    return ' '.join(ls[:-1]) == b['name'] or ''.join(ls[:-1]).replace(' ', '') == b['name'].replace(' ', '')


def _num(tag):
    """A tag's number: "12" of "12", "SL12", "SR-1-12"."""
    return re.search(r'(\d+)$', tag).group(1)


def key_map(key):
    """tag -> full label, a run's line ("1 to 36", "SR1 to SR36 · 125'")
    read back tag by tag."""
    out = {}
    for e in key['entries']:
        if 'tags' not in e:
            assert e['tag'] not in out, e
            out[e['tag']] = e['text']
            continue
        assert e['tag'] == f"{e['tags'][0]} to {e['tags'][-1]}", e
        first, rest = e['text'].split(' to ', 1)
        length = rest.split(' · ', 1)[1]
        n0 = _num(e['tags'][0])
        assert first.endswith(n0), e
        stem = first[:len(first) - len(n0)]
        for t in e['tags']:
            assert t not in out, e
            out[t] = f"{stem}{_num(t)} · {length}"
    return out


def check(sheet, out, n):
    """Every rule of the ruling on one printed sheet; returns 'tags' or
    'labels'."""
    br, key, da = out['brackets'], out['key'], out['da']
    assert len(br) == n, (sheet, len(br))
    tagged = [b for b in br if 'tag' in b]
    assert not tagged or len(tagged) == len(br), (sheet, 'every bracket tagged, or none')
    if tagged:
        # the key, and every tag in it once, mapping to its full label
        assert key, (sheet, 'tags with no key')
        m = key_map(key)
        for b in br:
            assert b['lines'] == [b['tag']], (sheet, b)
            assert b['full'].startswith(b['name'] + ' · '), (sheet, b)
            assert m.get(b['tag']) == b['full'], (sheet, b['tag'], b['full'], m.get(b['tag']))
        names = {}
        for b in br:
            assert names.setdefault(b['tag'], b['name']) == b['name'], (sheet, 'a tag on two multis', b)
        # the key inside the drawing area, clear of the wall and the brackets
        k = (key['x'], key['y'], key['x'] + key['w'], key['y'] + key['h'])
        assert da['x'] - 0.5 <= k[0] and k[2] <= da['x'] + da['w'] + 0.5, (sheet, key, da)
        assert da['y'] - 0.5 <= k[1] and k[3] <= da['y'] + da['h'] + 0.5, (sheet, key, da)
        mp = out['map']
        assert not meets(k, (mp['x'], mp['y'], mp['x'] + mp['w'], mp['y'] + mp['h'])), (sheet, key, mp)
        for b in br:
            assert not meets(k, (b['inkX1'], min(b['labelY1'], b['y1']), b['inkX2'], max(b['labelY2'], b['y2']))), \
                (sheet, key, b)
    else:
        assert key is None, (sheet, 'a key only where tags print')
        for b in br:
            assert whole(b), (sheet, b)
    for b in br:
        # legible, inside its room, inside the drawing area
        assert b['size'] >= 14, (sheet, b)
        assert b['labelY2'] - b['labelY1'] <= b['room'] + 0.5, (sheet, b)
        assert da['x'] <= b['inkX1'] and b['inkX2'] <= da['x'] + da['w'], (sheet, b, da)
        assert da['y'] <= b['labelY1'] and b['labelY2'] <= da['y'] + da['h'], (sheet, b, da)
    # the logged extents never overlap, and no label reaches another
    # bracket's line
    for a in br:
        ra = (a['inkX1'], a['labelY1'], a['inkX2'], a['labelY2'])
        for b in br:
            if a is b or a['side'] != b['side']:
                continue
            assert not meets(ra, (b['inkX1'], b['labelY1'], b['inkX2'], b['labelY2'])), (sheet, a, b)
            if a['depth'] != b['depth']:
                assert not meets(ra, (b['x'] - 1.5, b['y1'], b['x'] + 1.5, b['y2'])), (sheet, a, b)
    # the drawn ink: the rotated labels and the key's lines, measured
    rot = [t for t in out['texts'] if t['rot']]
    keyed = []
    if key:
        k = (key['x'] - 1, key['y'] - 1, key['x'] + key['w'] + 1, key['y'] + key['h'] + 1)
        keyed = [t for t in out['texts'] if not t['rot'] and meets(box(t), k, 0)]
        assert len(keyed) == 1 + 2 * len(key['entries']), (sheet, len(keyed), key)
    ink = rot + keyed
    for t in ink:
        assert not t['t'].endswith('…') and t['size'] >= 14, (sheet, t)
        x0, y0, x1, y1 = box(t)
        assert x0 >= -1 and y0 >= -1 and x1 <= out['W'] + 1 and y1 <= out['H'] + 1, (sheet, 'off the page', t)
    boxes = [box(t) for t in ink]
    for i in range(len(ink)):
        for j in range(i + 1, len(ink)):
            same_key_line = ink[i] in keyed and ink[j] in keyed
            if not same_key_line:
                assert not meets(boxes[i], boxes[j], 1), (sheet, ink[i], ink[j])
    return 'tags' if tagged else 'labels'


def run_all(pg, n):
    return {sheet: check(sheet, pg.evaluate(SHEET_JS, sheet), n) for sheet in SHEETS}


# ── 1. a dense map with ordinary names ───────────────────────────────────

NAMES = ['DISTRO A', 'VIDEO DISTRO', 'STAGE LEFT DISTRO', 'UPSTAGE LEFT POWER DISTRO A',
         'UPSTAGELEFTPOWERDISTROALPHA']


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('length', [None, '125'])
def test_a_dense_map_prints_tags_and_a_key(page, name, length):
    """10 x 60, a circuit per multi, sixty multis: every label reads "D…"
    no longer - each bracket takes its number, the key lists each one's
    full label, on every sheet."""
    pg, errors = page
    configure(pg, 'TALL', {'powerAmperage': 12.5, 'powerSocaSplits': list(range(1, 60)),
                           **multis(60, length=length)}, [dist(name)])
    got = run_all(pg, 60)
    assert got['letter'] == got['a4'] == 'tags', got
    out = pg.evaluate(SHEET_JS, 'letter')
    assert sorted(int(b['tag']) for b in out['brackets']) == list(range(1, 61))
    want = "125'" if length else 'no length'
    assert all(b['full'] == f"{name}{b['tag']} · {want}" for b in out['brackets'])
    assert errors == [], errors


def test_two_distros_sharing_numbers_tag_by_distro(page):
    pg, errors = page
    a = multis(30, 'd1')
    wall = {'powerAmperage': 12.5, 'powerSocaSplits': list(range(1, 60)),
            'powerSocaDistro': {**a['powerSocaDistro'],
                                **{str(i + 30): 'd2' for i in range(1, 31)}},
            'powerSocaNumber': {**a['powerSocaNumber'], **{str(i + 30): i for i in range(1, 31)}}}
    configure(pg, 'TALL', wall, [dist('STAGE LEFT', 1), dist('STAGE RIGHT', 2)])
    run_all(pg, 60)
    out = pg.evaluate(SHEET_JS, 'letter')
    # (round 8) each distro's code from its own name: SL, SR
    tags = sorted(b['tag'] for b in out['brackets'])
    assert tags == sorted([f'SL{i}' for i in range(1, 31)] + [f'SR{i}' for i in range(1, 31)]), tags
    for b in out['brackets']:
        assert b['name'].startswith('STAGE LEFT' if b['tag'].startswith('SL') else 'STAGE RIGHT'), b
    assert errors == [], errors


# ── 2. ranked by whole labels ────────────────────────────────────────────

def test_three_long_names_on_a_wide_wall_print_whole(page):
    """36 x 6, the vertical pattern, three multis of a long-named distro:
    on Letter every label prints its name and its length, the gutter grown
    a little rather than the length dropped."""
    pg, errors = page
    configure(pg, 'WIDE', {'powerFlowPattern': 'tl-v', **multis(40, length='125')},
              [dist('UPSTAGE LEFT POWER DISTRO A')])
    got = run_all(pg, 3)
    assert got['letter'] == 'labels', got
    out = pg.evaluate(SHEET_JS, 'letter')
    for b in out['brackets']:
        assert whole(b) and b['lines'][-1].endswith("125'"), b
    assert errors == [], errors


@pytest.mark.parametrize('name', ['SR', 'UPSTAGE LEFT POWER DISTRO A'])
def test_a_deep_stack_of_single_circuit_multis(page, name):
    """36 x 6, a multi per column: they stack eighteen deep. Long names
    print tags plus a key wherever their labels would be cut."""
    pg, errors = page
    configure(pg, 'WIDE', {'powerFlowPattern': 'tl-v', 'powerAmperage': 12.5,
                           'powerSocaSplits': list(range(1, 36)), **multis(36, length='125')}, [dist(name)])
    got = run_all(pg, 36)
    if name != 'SR':
        assert got['letter'] == 'tags', got
    assert errors == [], errors


# ── 3. an edge label slides inward ───────────────────────────────────────

def test_the_last_multi_slides_inward_rather_than_being_cut(page):
    """10 x 60, a multi per two circuits, "DISTRO A": the thirtieth label
    had read "DIST…" against the map's edge while every other one fitted."""
    pg, errors = page
    configure(pg, 'TALL', {'powerAmperage': 12.5, 'powerSocaSplits': list(range(2, 60, 2)),
                           **multis(30, length='125')}, [dist('DISTRO A')])
    got = run_all(pg, 30)
    assert got['letter'] == 'labels', got
    out = pg.evaluate(SHEET_JS, 'letter')
    last = max(out['brackets'], key=lambda b: b['y1'])
    assert last['name'] == 'DISTRO A30' and whole(last), last
    assert last['shift'] < 0, last
    # every other label sits on its own bracket's middle
    for b in out['brackets']:
        if b is not last and 'shift' not in b:
            mid = (b['y1'] + b['y2']) / 2
            assert abs((b['labelY1'] + b['labelY2']) / 2 - mid) < 1, b
    assert errors == [], errors


NOSPACE = 'UPSTAGELEFTDISTRIBUTIONRACKFORVIDEOWALLNUMBERONEALPHABRAVO'


def test_a_long_name_with_no_spaces_never_prints_cut(page):
    """Four multis of a 58-letter name with no spaces: whole where it fits,
    else tags and a key - never "UPSTAGELEFTDIS…", ARCH D included."""
    pg, errors = page
    assert len(NOSPACE) == 58
    configure(pg, 'MAIN', {'powerSocaSplits': [1, 2, 3], **multis(4, length='100')}, [dist(NOSPACE)])
    run_all(pg, 4)
    assert errors == [], errors


# ── 4. a deep stack grows its gutter before the floor ────────────────────

def test_a_stack_that_overflowed_keeps_its_type(page):
    """6 x 5, a circuit per column, a multi per circuit: three brackets a
    side across the whole wall. Every label had dropped to the floor; the
    gutter grows a little and they print at full size, whole."""
    pg, errors = page
    configure(pg, 'COLS', {'powerFlowPattern': 'tl-v', 'panelWatts': 660, 'powerSocaSplits': list(range(1, 6)),
                           **multis(6, length='125')}, [dist('DSR DISTRO')])
    got = run_all(pg, 6)
    assert set(got.values()) == {'labels'}, got
    for sheet in SHEETS:
        out = pg.evaluate(SHEET_JS, sheet)
        assert min(b['size'] for b in out['brackets']) >= 20, (sheet, out['brackets'])
        assert max(b['compact'] for b in out['brackets']) <= 2, (sheet, out['brackets'])
    assert errors == [], errors


# ── normal maps print as they did ────────────────────────────────────────

def test_a_normal_map_has_no_tags_and_no_key(page):
    pg, errors = page
    configure(pg, 'MAIN', {'powerSocaSplits': [1, 2, 3], **multis(4, length='100')}, [dist('SL')])
    for sheet in SHEETS:
        out = pg.evaluate(SHEET_JS, sheet)
        assert check(sheet, out, 4) == 'labels'
        for b in out['brackets']:
            assert whole(b) and b['lines'][-1].endswith("100'"), (sheet, b)
            assert b['compact'] == 0 and b['depth'] == 0, (sheet, b)
            assert not {'tag', 'full', 'shift'} & set(b), (sheet, b)
    assert errors == [], errors


# ── the logged extent is the drawn one ───────────────────────────────────

def test_the_logged_label_extent_is_never_clamped_to_its_room(page):
    """Asked for a room no label fits, the label is cut - and the log says
    how wide the cut label really drew."""
    pg, errors = page
    configure(pg, 'MAIN', {'powerSocaSplits': [1, 2, 3], **multis(4, length='100')}, [dist('SL')])
    got = pg.evaluate("""() => {
        const app = window.app;
        const orig = app._bBracketLayout;
        app._bBracketLayout = function (...a) {
            const L = orig.apply(this, a);
            for (const side of ['L', 'R']) for (const b of L.placed[side]) b.room = 2;
            return L;
        };
        try {
            app._circuitTailCache = null;
            const opts = Object.assign(app.readBinderOptions(), { sheet: 'letter', scope: { kind: 'show' },
                hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
            const i = app.planBinder(opts).findIndex(p => p.kind === 'power');
            return app.renderBinderPage(opts, i).brackets;
        } finally { app._bBracketLayout = orig; }
    }""")
    assert got
    for b in got:
        assert b['lines'][0].endswith('…'), b
        assert b['labelY2'] - b['labelY1'] > b['room'] + 1, b
    assert errors == [], errors


# ── 6. the app reads notes as the workbook does ──────────────────────────

def test_the_tail_right_after_the_arrow_is_the_adapters_in_the_app(page):
    pg, errors = page
    got = pg.evaluate("(notes) => notes.map(t => window.app.pullFreeRowNotes(t))", list(ARROW_NOTES))
    assert got == list(ARROW_NOTES.values()), got
    assert errors == [], errors
