"""The binder's CAT SNAKE page.

The owner, 2026-11-18 (beta.7 review): a show whose XD links run on a Cat
snake gets a page for it, in the Fiber page's style and titled for the Cat
snake, listing each channel - the channel, the processor output, the
breakout box input - with the backup links beside their mains as on the
Fiber page. A show with no fiber at all still gets it; a show with fiber
and Cat snakes gets both, each its own page, in the same place (right
after the screens, before the pull sheets, the Fiber page first).

  * The Fiber page draws the fiber links (and single Cat cables) only; the
    Cat snake page draws the snake links only, with each snake's CHANNEL
    map (channel | output | breakout box) and the snakes to pull.
  * Where no Fiber page prints, the Cat snake page also lists the links on
    a Cat cable of their own, under CAT CABLES (owner, 2026-11-19: every
    data cable on some patch page); with a Fiber page they stay on it.
  * The export dialog's tick is offered when either page would print, and
    says what it prints: "Fiber", "Cat snake", or both.

Run locally (each session takes its own free port):
    python -m pytest tests/test_binder_cat_snake_page.py -n 4 --dist loadfile --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402
from test_cat_snake import SEED_JS  # noqa: E402
from test_hidden_screen_binder import FEED_JS  # noqa: E402
from test_binder_sheet_bounds import BOUNDS_JS, TOL, _offenders  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _opts(**kw):
    opts = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
            'fiber': True, 'network': False, 'rigging': True, 'wiring': True, 'titleBlock': True}
    opts.update(kw)
    return opts


# XD A to D each on a channel of one 5 channel Cat6A snake, and XD A's
# backup X2 (off the SX40's backup processor) on its 5th channel.
SNAKE_JS = """async (ids) => {
    const app = window.app;
    const [a, b, c, d] = ids.xds;
    await app.createFiberCable({kind: 'cat-snake', copper: 'Cat6A', strands: 5, ft: 150,
                                link: {boxId: a, key: 'p1'}}, 'New Cat snake');
    const snake = app.getFiberCables().find(x => x.kind === 'cat-snake').id;
    for (const box of [b, c, d]) {
        await app.setFiberLink(app.fiberBoxById(box), 'p1', {cable: snake});
    }
    await app.setFiberLink(app.fiberBoxById(a), 'b1', {cable: snake});
    await app.refreshProcessors();
    app._circuitTailCache = null;
    return snake;
}"""

# A TAC on the H9's CVT10, the show's one fiber link.
TAC_JS = """async (ids) => {
    const app = window.app;
    await app.createFiberCable({kind: 'tac', strands: 12, ft: 300, link: {boxId: ids.cvt, key: 'p1'}},
                               'New Fiber Cable');
    await app.refreshProcessors();
    app._circuitTailCache = null;
    return app.getFiberCables().find(x => x.kind === 'tac').id;
}"""

PLAN_JS = """(opts) => window.app.planBinder(opts).map(p => ({
    number: p.number, kind: p.kind, title: p.title, sheetTitle: p.sheetTitle, fiber: p.fiber || null}))"""

# Each page's facts as the tests read them.
FACTS_JS = """() => {
    const app = window.app;
    return {
        fiber: app.binderUsesFiber(), snake: app.binderUsesCatSnake(),
        fiberPage: app.binderFiberPage(null), snakePage: app.binderCatSnakePage(null),
    };
}"""


def _tick(pg):
    """The export dialog's Fiber tick, the dialog open on the binder."""
    try:
        pg.evaluate("window.app.openExportModal('binder')")
        pg.wait_for_function("document.getElementById('export-format').value === 'binder'")
        return pg.evaluate("""() => {
            const l = document.getElementById('export-binder-fiber-label');
            return {shown: l.style.display !== 'none', text: l.textContent.trim(),
                    opts: window.app.readBinderOptions().fiber};
        }""")
    finally:
        pg.evaluate("document.getElementById('export-modal').style.display = 'none'")

# Every text the plan's `kind` sheets paint, by sheet.
TEXTS_JS = """([opts, kind]) => {
    const app = window.app;
    const out = [];
    app.planBinder(opts).forEach((p, i) => {
        if (p.kind === kind) out.push(app.renderBinderPage(opts, i).texts);
    });
    return out;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.route('**/api/native-dialog**', lambda route: route.fulfill(
        status=200, content_type='application/json', body='{"cancelled": true}'))
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.evaluate(FEED_JS)
    pg.wait_for_timeout(800)
    ids['snake'] = pg.evaluate(SNAKE_JS, ids)
    settled(pg, lambda: pg.evaluate("() => window.app.binderUsesCatSnake()"), lambda v: v is True, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def test_a_cat_snake_show_with_no_fiber_gets_a_cat_snake_page(page):
    """No fiber at all: no Fiber page, one CAT SNAKE page in its place -
    after the screens, before the pull sheets, numbered 3.1 - and the
    dialog's tick offered as "Cat snake"."""
    pg, ids = page
    plan = pg.evaluate(PLAN_JS, _opts())
    kinds = [p['kind'] for p in plan]
    assert 'fiber' not in kinds and kinds.count('catsnake') == 1, kinds
    at = kinds.index('catsnake')
    assert max(i for i, k in enumerate(kinds) if k in ('power', 'data', 'wiring')) < at < kinds.index('pull'), kinds
    sheet = plan[at]
    assert (sheet['number'], sheet['title'], sheet['sheetTitle']) == ('3.1', 'Cat snake', 'CAT SNAKE'), sheet
    facts = pg.evaluate(FACTS_JS)
    assert facts['fiber'] is False and facts['snake'] is True, facts
    assert facts['fiberPage']['procs'] == [] and facts['fiberPage']['cables'] == [], facts['fiberPage']
    assert _tick(pg) == {'shown': True, 'text': 'Cat snake', 'opts': True}
    # the Fiber tick off: neither page
    assert 'catsnake' not in [p['kind'] for p in pg.evaluate(PLAN_JS, _opts(fiber=False))]
    # one screen's export: no page (as the Fiber page)
    lid = pg.evaluate("() => String(window.app.project.layers.find(l => l.name === 'WALL').id)")
    assert 'catsnake' not in [p['kind'] for p in pg.evaluate(
        PLAN_JS, _opts(cover=False, pull=False, hardware=False, scope={'kind': 'screen', 'layerId': lid}))]
    assert ids['errors'] == []


def test_the_page_lists_each_channel_with_its_output_and_box_input(page):
    """Each snake link is a row - output, the snake, the channel at either
    end, the box and its input - its backup X2 straight after XD A's X1;
    the channel map lists every channel: channel, output, breakout box;
    the pull list is the snake's own pull row."""
    pg, ids = page
    sp = pg.evaluate(FACTS_JS)['snakePage']
    links = [l for p in sp['procs'] for l in p['links']]
    assert links and all('Cat6A snake A' in l['cable'] for l in links), links
    by_box = [(l['box'], l['input'], l['atProcessor'], l['atBreakout']) for l in links]
    assert ('XD A', 'X1', ['Ch 1'], ['Ch 1']) in by_box and ('XD A', 'X2', ['Ch 5'], ['Ch 5']) in by_box, by_box
    i = by_box.index(('XD A', 'X1', ['Ch 1'], ['Ch 1']))
    assert by_box[i + 1][:2] == ('XD A', 'X2'), by_box
    assert sorted(b[0] for b in by_box) == ['XD A', 'XD A', 'XD B', 'XD C', 'XD D'], by_box
    assert len(sp['cables']) == 1, sp['cables']
    cmap = sp['cables'][0]
    assert cmap['title'] == "Channel map · Cat6A snake A · 5 channel · 150'", cmap
    rows = [r['cells'] for r in cmap['rows'] if 'cells' in r]
    assert sorted(r[0] for r in rows) == ['1', '2', '3', '4', '5'], rows
    # each channel's output and breakout box input, as the link rows say
    for l in links:
        ch = l['atProcessor'][0].replace('Ch ', '')
        row = next(r for r in rows if r[0] == ch)
        assert row[1] == l['output'] and row[2] == f"{l['input']} on {l['box']}", (row, l)
    assert cmap['spare'] == '', cmap
    assert [(r['type'], r['qty']) for r in sp['pull']] == [('Cat6A snake · 5 channel', 1)], sp['pull']
    assert ids['errors'] == []


def test_the_sheet_paints_the_cat_snake_and_never_the_word_fiber(page):
    """The sheet heads itself CAT SNAKE and its map CHANNEL MAP; it never
    says fiber or copper, has no em or en dash, and nothing runs past the
    drawing area on any sheet size, title block on or off."""
    pg, ids = page
    texts = pg.evaluate(TEXTS_JS, [_opts(), 'catsnake'])
    assert len(texts) == 1, texts
    t = texts[0]
    assert 'CAT SNAKE' in t, t
    assert any(x.startswith('CHANNEL MAP') for x in t), t
    assert 'CAT SNAKES · PULL LIST' in t, t
    joined = ' '.join(t).lower()
    assert 'fiber' not in joined and 'copper' not in joined and 'strand' not in joined, t
    assert not [x for x in t if '—' in x or '–' in x], t
    for sheet in ('letter', 'tabloid', 'a4'):
        for tb in (True, False):
            report = pg.evaluate(BOUNDS_JS, [_opts(sheet=sheet, titleBlock=tb), TOL])
            bad = _offenders([p for p in report if p['kind'] == 'catsnake'])
            assert not bad, (sheet, tb, bad)
    assert ids['errors'] == []


def test_fiber_and_a_cat_snake_each_get_their_own_page(page):
    """With a TAC on the H9's CVT10 too: the Fiber page (3.1) draws the TAC
    only and the Cat snake page (3.2) the snake only, both before the pull
    sheets; the tick reads "Fiber, Cat snake"."""
    pg, ids = page
    tac = pg.evaluate(TAC_JS, ids)
    try:
        settled(pg, lambda: pg.evaluate("() => window.app.binderUsesFiber()"), lambda v: v is True, 5000)
        plan = pg.evaluate(PLAN_JS, _opts())
        kinds = [p['kind'] for p in plan]
        assert kinds.count('fiber') == 1 and kinds.count('catsnake') == 1, kinds
        f, c = kinds.index('fiber'), kinds.index('catsnake')
        assert f + 1 == c and c < kinds.index('pull'), kinds
        assert [(plan[i]['number'], plan[i]['sheetTitle']) for i in (f, c)] == [('3.1', 'FIBER'), ('3.2', 'CAT SNAKE')]
        facts = pg.evaluate(FACTS_JS)
        fl = [l for p in facts['fiberPage']['procs'] for l in p['links']]
        sl = [l for p in facts['snakePage']['procs'] for l in p['links']]
        assert fl and all(l['cableId'] == tac for l in fl), fl
        assert sl and all(l['cableId'] == ids['snake'] for l in sl), sl
        assert [m['id'] for m in facts['fiberPage']['cables']] == [tac], facts['fiberPage']['cables']
        assert [m['id'] for m in facts['snakePage']['cables']] == [ids['snake']], facts['snakePage']['cables']
        assert not [r for r in facts['fiberPage']['pull'] if 'snake' in r['type']], facts['fiberPage']['pull']
        assert _tick(pg) == {'shown': True, 'text': 'Fiber, Cat snake', 'opts': True}
        ftext = pg.evaluate(TEXTS_JS, [_opts(), 'fiber'])
        assert ftext and not [x for s in ftext for x in s if 'snake' in x.lower()], ftext
    finally:
        pg.evaluate("() => window.app.undo()")
        settled(pg, lambda: pg.evaluate("() => window.app.binderUsesFiber()"), lambda v: v is False, 5000)
    assert ids['errors'] == []


# XD B's X2 on a Cat6A cable of its own, 50'.
COPPER_JS = """async (ids) => {
    const app = window.app;
    await app.setFiberLink(app.fiberBoxById(ids.xds[1]), 'b1', {copper: 'Cat6A', ft: 50});
    await app.refreshProcessors();
    app._circuitTailCache = null;
}"""

COPPER_ON_JS = """(ids) => { const b = window.app.fiberBoxById(ids.xds[1]);
    return !!(b && b.fiberLinks && b.fiberLinks.b1 && b.fiberLinks.b1.copper); }"""


def test_a_cat_cable_of_its_own_is_listed_under_cat_cables_with_no_fiber_page(page):
    """XD B's X2 on a Cat6A cable of its own: with no Fiber page it is on
    the Cat snake page - a row of the drawing and a CAT CABLES row (output,
    cable, breakout box); with a TAC making a Fiber page, it moves back to
    the Fiber page and the Cat snake page has no CAT CABLES."""
    pg, ids = page
    pg.evaluate(COPPER_JS, ids)
    try:
        settled(pg, lambda: pg.evaluate(COPPER_ON_JS, ids), lambda v: v is True, 5000)
        facts = pg.evaluate(FACTS_JS)
        sp = facts['snakePage']
        rows = [r['cells'] for r in sp['catCables'] if 'cells' in r]
        assert len(rows) == 1 and rows[0][2] == 'X2 on XD B', sp['catCables']
        assert 'Cat6A' in rows[0][1] and "50'" in rows[0][1], sp['catCables']
        assert [r for r in sp['catCables'] if 'band' in r], sp['catCables']
        drawn = [(l['box'], l['input']) for p in sp['procs'] for l in p['links']]
        assert ('XD B', 'X2') in drawn, drawn
        # its output is the processor page's own for that link
        link = next(l for p in sp['procs'] for l in p['links'] if (l['box'], l['input']) == ('XD B', 'X2'))
        assert rows[0][0] == link['output'], (rows, link)
        # (no fiber: no Fiber page prints, so this is its only patch page)
        assert facts['fiber'] is False, facts['fiber']
        assert 'fiber' not in [p['kind'] for p in pg.evaluate(PLAN_JS, _opts())]
        t = pg.evaluate(TEXTS_JS, [_opts(), 'catsnake'])
        assert len(t) == 1 and 'CAT CABLES' in t[0], t
        for sheet in ('letter', 'tabloid'):
            report = pg.evaluate(BOUNDS_JS, [_opts(sheet=sheet), TOL])
            bad = _offenders([p for p in report if p['kind'] == 'catsnake'])
            assert not bad, (sheet, bad)
        # a Fiber page: the Cat cable is back on it, none under CAT CABLES
        pg.evaluate(TAC_JS, ids)
        try:
            settled(pg, lambda: pg.evaluate("() => window.app.binderUsesFiber()"), lambda v: v is True, 5000)
            facts = pg.evaluate(FACTS_JS)
            assert facts['snakePage']['catCables'] == [], facts['snakePage']['catCables']
            on_fiber = [(l['box'], l['input']) for p in facts['fiberPage']['procs'] for l in p['links']]
            on_snake = [(l['box'], l['input']) for p in facts['snakePage']['procs'] for l in p['links']]
            assert ('XD B', 'X2') in on_fiber and ('XD B', 'X2') not in on_snake, (on_fiber, on_snake)
            t = pg.evaluate(TEXTS_JS, [_opts(), 'catsnake'])
            assert len(t) == 1 and 'CAT CABLES' not in t[0], t
        finally:
            pg.evaluate("() => window.app.undo()")
            settled(pg, lambda: pg.evaluate("() => window.app.binderUsesFiber()"), lambda v: v is False, 5000)
    finally:
        pg.evaluate("() => window.app.undo()")
        settled(pg, lambda: pg.evaluate(COPPER_ON_JS, ids), lambda v: v is False, 5000)
    assert ids['errors'] == []
