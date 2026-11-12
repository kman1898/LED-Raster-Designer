"""Binder paperwork, round 8: bracket tags, deep stacks and the key.

  * A bracket tag's code comes from the distro's OWN name, never its place
    on the sheet (owner ruling): "B12" is DISTRO B's multi 12 on every
    sheet of the binder, "SL3" is SL's multi 3. Where the codes' tags fit
    nowhere, or no code tells two distros apart, the brackets are counted.
  * A stack too deep for the sheet's width (sixty one-circuit multis across
    a 60 x 6 wall on Letter and A4) prints tags at the floor with a key,
    never cut or overlapping labels, and no empty band reserved for a key.
  * A 12 x 6 wall on A4 whose labels were already whole at the closer step
    keeps its size rather than shrinking for no gain.
  * A key folds a clean run onto one line where that lets it print larger.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_r8.py -q --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

from test_paper_r7 import (CONFIG_JS, SEED_JS, SHEET_JS, SHEETS, check, dist,  # noqa: E402
                           multis, whole)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


WALLS = [{'name': 'TALL', 'cols': 10, 'rows': 60, 'x': 0},
         {'name': 'XWIDE', 'cols': 60, 'rows': 6, 'x': 3000},
         {'name': 'MAIN', 'cols': 12, 'rows': 6, 'x': 16000},
         {'name': 'TALL2', 'cols': 10, 'rows': 60, 'x': 20000}]

# every power sheet of the binder: its title and brackets as logged
SHEETS_JS = """(sheet) => {
    const app = window.app;
    app._circuitTailCache = null;
    const opts = Object.assign(app.readBinderOptions(), { sheet, scope: { kind: 'show' },
        hardware: false, pull: false, cover: false, wiring: false, sides: { power: true, data: false } });
    const plan = app.planBinder(opts);
    const out = [];
    plan.forEach((p, i) => {
        if (p.kind !== 'power') return;
        const r = app.renderBinderPage(opts, i);
        if (r.brackets && r.brackets.length) out.push({ title: p.title, brackets: r.brackets, key: r.bracketKey });
    });
    return out;
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


def configure(pg, name, wall, distros):
    n = pg.evaluate(CONFIG_JS, {'name': name, 'wall': wall, 'distros': distros})
    # the screens' saves answered before anything is read: an echo landing
    # between two sheets' renders must not be what a sheet is checked on
    settle(pg)
    return n


def settle(pg):
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")


def dealt(names, n=60, start=None):
    """`n` one-circuit multis down the TALL wall, dealt to the distros in
    turn, each numbered on its own distro (from `start`, by distro id)."""
    k = len(names)
    start = start or {}
    d, num, lens = {}, {}, {}
    for i in range(1, n + 1):
        did = f'd{(i - 1) % k + 1}'
        d[str(i)] = did
        num[str(i)] = start.get(did, 1) + (i - 1) // k
        lens[str(i)] = '125'
    return {'powerAmperage': 12.5, 'powerSocaSplits': list(range(1, n)), 'powerSocaDistro': d,
            'powerSocaNumber': num, 'powerSocaLengths': lens}


def tagged(pg, sheet):
    out = pg.evaluate(SHEET_JS, sheet)
    br = out['brackets']
    return out, (br if br and all('tag' in b for b in br) else [])


# ── 1. tags from the distro's own name ───────────────────────────────────

@pytest.mark.parametrize('order', [['DISTRO C', 'DISTRO A', 'DISTRO B'],
                                   ['DISTRO B', 'DISTRO C', 'DISTRO A']])
def test_a_tag_names_its_own_distro_whatever_the_show_order(page, order):
    """DISTRO A, B and C in an odd show order: B12 is DISTRO B's multi 12,
    never the second distro's on the sheet."""
    pg, errors = page
    configure(pg, 'TALL', dealt(order), [dist(nm, i + 1) for i, nm in enumerate(order)])
    got = {sheet: check(sheet, pg.evaluate(SHEET_JS, sheet), 60) for sheet in SHEETS}
    assert got['letter'] == got['a4'] == 'tags', got
    for sheet in SHEETS:
        _, br = tagged(pg, sheet)
        for b in br:
            # "DISTRO B12" -> "B12"
            assert b['tag'] == b['name'][len('DISTRO '):], (sheet, b)
    assert errors == [], errors


TAGS_JS = """(boxes) => {
    const app = window.app;
    app._circuitTailCache = null;
    const t = app._bBracketTags(boxes.map(b => ({ box: b })));
    return t.entries.map(e => e.tag);
}"""


def test_short_distro_names_are_their_own_codes(page):
    """SL and SR sharing numbers: "SL3" and "SR3" (their labels print whole
    on the TALL wall, so the tags are asked for directly)."""
    pg, errors = page
    configure(pg, 'TALL', dealt(['SR', 'SL']), [dist('SR', 1), dist('SL', 2)])
    boxes = [{'number': n, 'distroId': d, 'name': f'{nm}{n}'}
             for n in (1, 2, 3) for d, nm in (('d1', 'SR'), ('d2', 'SL'))]
    assert pg.evaluate(TAGS_JS, boxes) == ['SR1', 'SR2', 'SR3', 'SL1', 'SL2', 'SL3']
    # one distro alone on a sheet: its numbers are unique, the plain number
    assert pg.evaluate(TAGS_JS, [b for b in boxes if b['distroId'] == 'd2']) == ['1', '2', '3']
    assert errors == [], errors


@pytest.mark.parametrize('names', [['SR-1', 'SR-2'], ['SR', 'SR']])
def test_duplicate_names_never_share_a_tag(page, names):
    """Two distros named SR read SR-1 and SR-2: their tags are told apart,
    by code ("SR-1-12", the box's own name) or counted where those are too
    long for the sheet - and every tag maps to its own box in the key."""
    pg, errors = page
    configure(pg, 'TALL', dealt(names), [dist(nm, i + 1) for i, nm in enumerate(names)])
    for sheet in SHEETS:
        out = pg.evaluate(SHEET_JS, sheet)
        check(sheet, out, 60)
        for b in out['brackets']:
            assert b['name'].startswith(('SR-1-', 'SR-2-')), b
            if 'tag' in b and '-' in b['tag']:
                assert b['tag'] == b['name'], (sheet, b)
    assert errors == [], errors


def test_a_distro_reads_the_same_code_on_every_sheet(page):
    """TALL holds DISTRO B and DISTRO C, TALL2 DISTRO C and DISTRO D: by
    place on the sheet DISTRO C was "B" on one and "A" on the other."""
    pg, errors = page
    configure(pg, 'TALL', dealt(['DISTRO B', 'DISTRO C']),
              [dist('DISTRO B', 1), dist('DISTRO C', 2), dist('DISTRO D', 3)])
    pg.evaluate("""(w) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.name === 'TALL2');
        Object.assign(l, w);
        l.visible = true;
        app.normalizePowerBreakout(l);
        app._circuitTailCache = null;
        app.updateLayers(app.project.layers);
    }""", {**dealt(['DISTRO C', 'DISTRO D'], start={'d1': 31, 'd2': 31}),
           'powerSocaDistro': {str(i): ('d2' if i % 2 else 'd3') for i in range(1, 61)}})
    settle(pg)
    for sheet in ('letter', 'a4'):
        pages = pg.evaluate(SHEETS_JS, sheet)
        assert len(pages) == 2, (sheet, [p['title'] for p in pages], pg.evaluate("""() => {
            const app = window.app;
            return app.project.layers.map(l => [l.name, l.visible, app.screenCircuits(l).length,
                                                Object.keys(l.powerSocaDistro || {}).length]);
        }"""))
        codes = {}
        for p in pages:
            assert all('tag' in b for b in p['brackets']), (sheet, p['title'])
            for b in p['brackets']:
                assert b['tag'] == b['name'][len('DISTRO '):], (sheet, p['title'], b)
                codes.setdefault(b['name'][len('DISTRO ')], set()).add(p['title'])
        assert len(codes['C']) == 2, codes
    assert errors == [], errors


def test_each_distros_code(page):
    """The shortest code that tells a distro apart: its short last word, a
    short name whole, else its initials from the first two on."""
    pg, errors = page
    names = ['UPSTAGE LEFT POWER DISTRO A', 'UPSTAGE RIGHT POWER DISTRO A', 'STAGE LEFT', 'VIDEO DISTRO',
             'DISTRO B', 'SR', 'DSR']
    got = pg.evaluate("""(names) => {
        const app = window.app;
        app.project.distros = names.map((n, i) => ({ id: 'q' + i, name: n, ratingA: 400, system: '120/208',
                                                     feeder: { ft: 10 } }));
        app._circuitTailCache = null;
        const codes = app._bDistroTagCodes();
        return names.map((n, i) => codes.get('q' + i));
    }""", names)
    assert got == ['UL', 'UR', 'SL', 'VD', 'B', 'SR', 'DSR'], got
    assert errors == [], errors


# ── 2. a stack too deep for the sheet's width ────────────────────────────

@pytest.mark.parametrize('names', [['UPSTAGE LEFT POWER DISTRO A'], ['SR'],
                                   ['UPSTAGE LEFT POWER DISTRO A', 'DOWNSTAGE RIGHT POWER DISTRO B', 'VIDEO WORLD C']])
def test_sixty_multis_across_a_wide_wall_print_tags_never_cut(page, names):
    """60 x 6, the vertical pattern, a multi per column: thirty brackets
    deep a side. Letter and A4 printed cut, overlapping labels, no tags and
    an empty band where a key was to go; now the tags print at the floor
    with the key, on every sheet nothing cut or overlapping."""
    pg, errors = page
    k = len(names)
    wall = {'powerAmperage': 10, 'powerFlowPattern': 'tl-v', 'powerSocaSplits': list(range(1, 60)),
            'powerSocaDistro': {str(i): f'd{(i - 1) % k + 1}' for i in range(1, 61)},
            'powerSocaNumber': {str(i): (i - 1) // k + 1 for i in range(1, 61)},
            'powerSocaLengths': {str(i): '125' for i in range(1, 61)}}
    configure(pg, 'XWIDE', wall, [dist(nm, i + 1, breaker=10) for i, nm in enumerate(names)])
    got = {sheet: check(sheet, pg.evaluate(SHEET_JS, sheet), 60) for sheet in SHEETS}
    assert got['letter'] == got['a4'] == 'tags', got
    for sheet in ('letter', 'a4'):
        out = pg.evaluate(SHEET_JS, sheet)
        assert out['key'] and out['key']['place'] == 'B', (sheet, out['key'])
        # the key sits right under the wall's foot: no band left empty
        # between them
        mp = out['map']
        assert out['key']['y'] - (mp['y'] + mp['h']) < 60, (sheet, out['key'], mp)
    assert errors == [], errors


# ── 3. a wall keeps its size where its labels already fitted ─────────────

def test_a_12_by_6_wall_on_a4_keeps_its_size(page):
    """Seven panels a circuit, a one-circuit multi each, the vertical
    pattern: on A4 every label was whole at the closer step, yet the wall
    shrank by a quarter for labels no larger."""
    pg, errors = page
    configure(pg, 'MAIN', {'panelWatts': 470, 'powerFlowPattern': 'tl-v', 'powerSocaSplits': list(range(1, 11)),
                           **multis(11, length='50')}, [dist('SL')])
    got = {sheet: check(sheet, pg.evaluate(SHEET_JS, sheet), 11) for sheet in SHEETS}
    assert set(got.values()) == {'labels'}, got
    out = pg.evaluate(SHEET_JS, 'a4')
    assert all(whole(b) for b in out['brackets'])
    assert out['map']['w'] > 540, out['map']
    assert errors == [], errors


# ── 4. a run on one line where that lets the key print larger ────────────

@pytest.mark.parametrize('sheet', ['letter', 'a4'])
def test_a_long_key_folds_its_run_onto_one_line(page, sheet):
    """10 x 60, sixty multis of a long name: sixty key lines at 14 become
    "1 to 60  UPSTAGE LEFT POWER DISTRO A1 to A60 · 125'" at 20."""
    pg, errors = page
    configure(pg, 'TALL', {'powerAmperage': 12.5, 'powerSocaSplits': list(range(1, 60)),
                           **multis(60, length='125')}, [dist('UPSTAGE LEFT POWER DISTRO A')])
    out = pg.evaluate(SHEET_JS, sheet)
    assert check(sheet, out, 60) == 'tags'
    key = out['key']
    assert key['size'] == 20 and len(key['entries']) == 1, key
    assert key['entries'][0]['text'] == "UPSTAGE LEFT POWER DISTRO A1 to A60 · 125'", key
    # the tags no closer than before
    assert all(b['compact'] == 0 for b in out['brackets']), out['brackets'][0]
    assert errors == [], errors


def test_a_wide_walls_key_folds_where_its_tags_keep_their_size(page):
    """60 x 6, thirty multis on Tabloid: thirty key lines at 14 across the
    sheet become one at 20, the tags still at 20."""
    pg, errors = page
    configure(pg, 'XWIDE', {'powerAmperage': 20, 'powerFlowPattern': 'tl-v',
                            'powerSocaSplits': list(range(1, 60)), **multis(60, length='125')},
              [dist('UPSTAGE LEFT POWER DISTRO A')])
    out = pg.evaluate(SHEET_JS, 'tabloid')
    assert check('tabloid', out, 30) == 'tags'
    assert out['key']['size'] == 20 and len(out['key']['entries']) == 1, out['key']
    assert min(b['size'] for b in out['brackets']) >= 20
    assert errors == [], errors
